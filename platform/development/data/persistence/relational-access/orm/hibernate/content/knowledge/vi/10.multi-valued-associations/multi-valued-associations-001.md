# @OneToMany hai chiều và vai trò khóa ngoại ở phía nhiều trong Hibernate

Trong các ứng dụng dùng Hibernate ORM, quan hệ **một–nhiều** xuất hiện ở rất nhiều nơi: một đơn hàng có nhiều dòng hàng, một phòng ban có nhiều nhân viên, một bài viết có nhiều bình luận, hoặc một khách hàng có nhiều địa chỉ. Khi thiết kế quan hệ **hai chiều (bidirectional)**, Java cho phép đi từ cha đến các con và đi ngược từ một con đến cha. Tuy nhiên, **hai hướng tham chiếu trong Java không đồng nghĩa có hai quan hệ khóa ngoại trong database**.

Đối với ánh xạ phổ biến `@OneToMany(mappedBy = "...")` kết hợp `@ManyToOne`, **khóa ngoại (foreign key, FK) nằm ở bảng phía nhiều**. Trong Hibernate/JPA, **phía nhiều, tức thuộc tính `@ManyToOne`, là owning side** của quan hệ: nó quyết định cột FK sẽ chứa giá trị nào. Danh sách `@OneToMany(mappedBy = "...")` ở phía một là **inverse side**, dùng để điều hướng quan hệ và biểu diễn tập các phần tử liên quan.

Hiểu đúng điểm này giúp tránh các lỗi thường gặp: thêm con vào collection của cha nhưng FK vẫn `NULL`; gọi `setParent()` mà collection cha hiển thị dữ liệu cũ; Hibernate sinh thêm câu `UPDATE` không mong muốn; xóa phần tử khỏi collection nhưng bản ghi con vẫn tồn tại; hoặc cascade xóa hàng loạt bản ghi mà nghiệp vụ không định xóa.

> **Phạm vi:** Ví dụ dùng Jakarta Persistence (`jakarta.persistence`) và Hibernate ORM 6.x, theo mô hình relational database thông thường. Hibernate 5 sử dụng `javax.persistence` và có một số khác biệt triển khai. SQL dưới đây là ví dụ giải thích cơ chế; thứ tự/cột/thời điểm chính xác còn phụ thuộc chiến lược cấp ID, flush, schema, mapping, dialect và phiên bản Hibernate.

## 1. Quan hệ một–nhiều hai chiều là gì?

Giả sử nghiệp vụ quản lý đơn hàng có hai thực thể:

- `PurchaseOrder` đại diện **một đơn hàng**.
- `OrderLine` đại diện **một dòng hàng** trong đơn.

Một đơn có thể chứa nhiều dòng hàng; mỗi dòng thuộc về đúng một đơn hàng. Code cần truy cập được cả hai chiều:

~~~java
PurchaseOrder order = ...;
List<OrderLine> lines = order.getLines(); // cha -> nhiều con

OrderLine line = ...;
PurchaseOrder parent = line.getOrder();  // con -> một cha
~~~

Sơ đồ ý tưởng:

~~~mermaid
erDiagram
    PURCHASE_ORDER ||--o{ ORDER_LINE : "chứa"
    PURCHASE_ORDER {
        bigint id PK
        varchar order_code UK
        bigint version
    }
    ORDER_LINE {
        bigint id PK
        bigint order_id FK
        varchar sku
        int quantity
    }
~~~

Ở database:

~~~text
purchase_order
+------+------------+
| id   | order_code |
+------+------------+
| 101  | PO-101     |
| 102  | PO-102     |
+------+------------+

order_line
+------+----------+---------+----------+
| id   | order_id | sku     | quantity |
+------+----------+---------+----------+
| 1001 | 101      | BOOK-01 | 2        |
| 1002 | 101      | PEN-02  | 5        |
| 1003 | 102      | BAG-07  | 1        |
+------+----------+---------+----------+
~~~

Hai dòng `1001` và `1002` thuộc về đơn `101` do **`order_line.order_id = 101`**. Trong bảng `purchase_order` không có một cột chứa danh sách ID con. Quan hệ được lưu bằng **một cột FK ở phía nhiều**, còn Hibernate tập hợp các dòng con thành collection khi ứng dụng truy cập `order.getLines()`.

### “Hai chiều” có ý nghĩa ở lớp Java

Với cùng hai bảng và một FK, ta có thể ánh xạ một chiều từ con đến cha, hoặc thêm chiều từ cha đến con. Chiều Java bổ sung giúp thao tác trên object model thuận tiện, nhưng không tạo thêm một FK nếu mapping `mappedBy` được khai báo đúng.

## 2. Owning side và inverse side: quyết định ai ghi khóa ngoại

Trong JPA, mỗi quan hệ hai chiều có một phía **owning** và một phía **inverse**:

| Phía Java | Annotation | Vai trò | Tác động trực tiếp đến FK |
|---|---|---|---|
| `OrderLine.order` | `@ManyToOne` + `@JoinColumn(name = "order_id")` | **Owning side** | Thuộc tính này quyết định giá trị cột `order_line.order_id`. |
| `PurchaseOrder.lines` | `@OneToMany(mappedBy = "order")` | **Inverse side** | Phản ánh các dòng thuộc đơn; tự thay đổi collection mà không đồng bộ owning side không đủ để cập nhật FK đúng. |

`mappedBy = "order"` nói rằng: “Quan hệ này đã được ánh xạ/sở hữu bởi thuộc tính Java có tên `order` bên entity `OrderLine`.” Nó **không phải** tên bảng, tên cột FK hay tên khóa chính:

~~~java
// Ở entity cha:
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

// Ở entity con:
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
~~~

Cặp trên diễn tả cùng một quan hệ; không nên thêm `@JoinColumn(name = "order_id")` lên collection đã có `mappedBy` rồi mong cả hai phía đồng thời làm chủ. Với quan hệ hai chiều này, **`OrderLine.order` là nơi duy nhất Hibernate đọc giá trị association để quyết định FK**.

### Đừng nhầm owning side với “thực thể quan trọng hơn”

Về nghiệp vụ, `PurchaseOrder` có thể là aggregate root và kiểm soát việc tạo/xóa các `OrderLine`. Tuy vậy, trong **mapping quan hệ**, `OrderLine` vẫn là owning side vì nó giữ cột FK. “Aggregate ownership” của thiết kế domain và “relationship ownership” của JPA là hai khái niệm có mục đích khác nhau.

## 3. Schema SQL thể hiện FK ở phía nhiều

Ví dụ DDL PostgreSQL:

~~~sql
CREATE SEQUENCE purchase_order_seq START WITH 1 INCREMENT BY 1;
CREATE SEQUENCE order_line_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_code VARCHAR(50) NOT NULL UNIQUE,
    version BIGINT NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,

    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id),
    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0)
);

CREATE INDEX ix_order_line_order_id ON order_line(order_id);
~~~

Cột `order_id` phải tham chiếu một ID đang tồn tại ở `purchase_order`. Điều kiện `NOT NULL` thể hiện quy tắc “mọi dòng hàng phải thuộc một đơn hàng”. Foreign key đảm bảo không có dòng tham chiếu đơn hàng không tồn tại; index ở `order_id` có thể hỗ trợ truy vấn các dòng của một đơn và thao tác kiểm tra FK, tùy database và execution plan.

**Điều kiện quan hệ không được diễn đạt chỉ bằng annotation Java.** Nếu migration tạo `order_id` nullable nhưng entity khai báo `nullable = false`, có sự không nhất quán giữa ứng dụng và schema. Ngược lại, nếu DB áp dụng `NOT NULL`, Hibernate không thể ghi một dòng con có `order = null` thành công, bất kể trong Java đang có danh sách `order.lines` chứa đối tượng đó.

### Nếu quan hệ là tùy chọn

Một mô hình khác có thể cho phép nhân viên chưa thuộc phòng ban:

~~~sql
employee.department_id BIGINT NULL
~~~

Khi đó `@ManyToOne(optional = true)` và `@JoinColumn(nullable = true)` có thể phù hợp. Ví dụ đơn hàng ở bài này cố ý dùng **bắt buộc** để làm rõ invariant và hành vi xóa.

## 4. Mapping hai chiều đầy đủ bằng Jakarta Persistence

Tạo hai file entity Java trong cùng package. Ví dụ dùng hai sequence để làm rõ thời điểm lấy khóa; có thể đổi chiến lược ID nếu schema của dự án yêu cầu.

### 4.1. Entity cha: `PurchaseOrder`

~~~java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @SequenceGenerator(
        name = "purchase_order_gen",
        sequenceName = "purchase_order_seq",
        allocationSize = 1
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_gen"
    )
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true, length = 50)
    private String orderCode;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {} // JPA yêu cầu constructor không tham số

    public PurchaseOrder(String orderCode) {
        this.orderCode = Objects.requireNonNull(orderCode);
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line");
        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalArgumentException(
                "Line already belongs to another order"
            );
        }
        if (!lines.contains(line)) {
            lines.add(line);
        }
        line.attachTo(this); // đồng bộ owning side
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.attachTo(null); // orphanRemoval: con bị bỏ khỏi quan hệ
        }
    }
}
~~~

### 4.2. Entity con: `OrderLine`

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "order_line")
public class OrderLine {
    @Id
    @SequenceGenerator(
        name = "order_line_gen",
        sequenceName = "order_line_seq",
        allocationSize = 1
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_line_gen"
    )
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "order_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_order_line_order")
    )
    private PurchaseOrder order; // owning side của quan hệ

    @Column(nullable = false, length = 100)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku);
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    // Package-private: chỉ aggregate helper nên thay đổi quan hệ.
    void attachTo(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Hai class phải nằm trong cùng package nếu `attachTo()` giữ quyền package-private. Trong ví dụ, `PurchaseOrder.addLine()/removeLine()` là API công khai duy nhất để thay đổi membership. Điều này giúp đảm bảo cả **collection ở phía một** và **reference ở phía nhiều** luôn trỏ đến nhau.

### Ý nghĩa của bốn lựa chọn mapping quan trọng

| Khai báo | Ý nghĩa |
|---|---|
| `mappedBy = "order"` | `PurchaseOrder.lines` là phía inverse; field `OrderLine.order` sở hữu FK. |
| `@ManyToOne(fetch = LAZY)` | Khi tải dòng hàng, Hibernate không nhất thiết tải toàn bộ đơn ngay; điều kiện lazy còn phụ thuộc runtime/proxy và transaction. |
| `cascade = ALL` | Các thao tác vòng đời từ cha có thể lan sang con: persist, merge, remove, refresh, detach theo semantics JPA. |
| `orphanRemoval = true` | Một con bị loại khỏi quan hệ cha–con sẽ được lên lịch xóa khi đồng bộ theo mapping thích hợp. |

`CascadeType.ALL` và `orphanRemoval = true` là **quyết định nghiệp vụ** của ví dụ: một dòng hàng thuộc riêng một đơn, bị bỏ khỏi đơn thì không còn tồn tại. Không nên copy hai cấu hình này vào quan hệ chia sẻ con giữa nhiều cha, hoặc quan hệ mà con cần sống độc lập.

## 5. Vì sao phải đồng bộ cả hai phía trong Java?

Giả sử lập trình viên chỉ thay đổi collection:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-001");
OrderLine line = new OrderLine("BOOK-01", 2);

order.getLines().add(line); // ví dụ này còn bị chặn bởi unmodifiableList
// line.getOrder() vẫn là null nếu collection cho phép sửa trực tiếp.
~~~

Nếu một class khác cho phép `lines.add(line)` trực tiếp mà không gán `line.order`, Hibernate nhìn thấy **owning side vẫn là null**. Với `order_line.order_id NOT NULL`, kết quả có thể là lỗi not-null constraint hoặc Hibernate từ chối nullability ở flush. Với FK nullable, hàng con có thể bị lưu mà không liên kết đến cha như mong đợi.

Ngược lại, chỉ sửa owning side:

~~~java
line.attachTo(order);
// line.getOrder() == order
// Nhưng order.getLines() có thể chưa chứa line.
~~~

FK của bản ghi con có thể được ghi đúng theo `line.order`, nhưng object graph trong Java **không nhất quán**: nơi khác đọc `order.getLines()` trong cùng persistence context có thể không thấy con vừa gán. Hibernate không mặc định tự sửa mọi collection inverse mỗi khi bạn thay một reference sở hữu.

Vì thế, helper:

~~~java
order.addLine(line);
~~~

cần duy trì cùng lúc:

~~~java
order.getLines().contains(line) == true
line.getOrder() == order
~~~

**Nguyên tắc:** owning side quyết định giá trị FK được lưu, nhưng code domain nên cập nhật **cả hai hướng** để object graph nhất quán ngay trong bộ nhớ.

### Vì sao getter trả về unmodifiable list?

Nếu trả collection mutable trực tiếp, code bên ngoài có thể gọi `order.getLines().clear()` mà không cập nhật `OrderLine.order`. Getter read-only buộc người dùng thao tác qua `addLine()/removeLine()`. Đây là một cách thiết kế domain, không phải yêu cầu bắt buộc của JPA.

Hibernate vẫn cần truy cập được collection field để thực hiện dirty checking và lazy initialization; trong ví dụ access type là **field access** vì `@Id` được đặt trên field. Không thay collection instance bằng `List.of(...)` hoặc một collection immutable sau khi entity đã managed nếu mapping cần Hibernate quản lý nó.

## 6. Insert: từ hai đối tượng Java đến một FK ở bảng con

Với mô hình đã định nghĩa:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

PurchaseOrder order = new PurchaseOrder("PO-001");
OrderLine book = new OrderLine("BOOK-01", 2);
OrderLine pen = new OrderLine("PEN-02", 5);

order.addLine(book);
order.addLine(pen);

entityManager.persist(order); // cascade PERSIST sang hai dòng
tx.commit();
~~~

Khi `persist(order)`, Hibernate quản lý `order` rồi nhờ `cascade = ALL` mà cũng quản lý `book` và `pen`. Với `SEQUENCE`, Hibernate có thể lấy ID cho các entity trước khi tạo `INSERT`. Đến flush/commit, SQL có thể có dạng:

~~~sql
-- Cấp ID bằng sequence, số lần/cách lấy tùy generator:
SELECT nextval('purchase_order_seq'); -- ví dụ 101
SELECT nextval('order_line_seq');      -- ví dụ 1001
SELECT nextval('order_line_seq');      -- ví dụ 1002

INSERT INTO purchase_order (order_code, version, id)
VALUES ('PO-001', 0, 101);

INSERT INTO order_line (order_id, sku, quantity, id)
VALUES (101, 'BOOK-01', 2, 1001);

INSERT INTO order_line (order_id, sku, quantity, id)
VALUES (101, 'PEN-02', 5, 1002);
~~~

SQL thực tế thông thường dùng placeholders `?` và JDBC bind parameters, không ghép trực tiếp literal như đoạn minh họa. Điều quan trọng là **`order_id` được lấy từ owning side `OrderLine.order`**. Không cần bảng nối `purchase_order_order_line` cho mapping hai chiều `mappedBy` + `@ManyToOne @JoinColumn` này.

### Tại sao thường chèn cha trước?

DB có FK từ `order_line.order_id` đến `purchase_order.id`. Nếu không có ràng buộc trì hoãn đặc biệt, hàng cha cần tồn tại trong transaction trước khi hàng con tham chiếu đến nó. Hibernate lập lịch thao tác theo mapping và dependency để tạo các bản ghi tương thích constraint.

Không nên suy luận “chèn cha trước” chỉ từ thứ tự code `order.addLine()`; thứ tự SQL thực tế do flush/ActionQueue/generator/database quyết định. Với `GenerationType.IDENTITY`, Hibernate thường phải insert cha sớm để nhận khóa sinh bởi DB, rồi sử dụng ID đó cho con.

### Nếu không có cascade PERSIST?

~~~java
@OneToMany(mappedBy = "order") // không cascade
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi ấy `entityManager.persist(order)` chỉ đăng ký cha; các con mới chưa nhất thiết được persist. Với `OrderLine.order` bắt buộc, cần persist con riêng trong cùng transaction:

~~~java
entityManager.persist(order);
entityManager.persist(book);
entityManager.persist(pen);
~~~

Không dựa vào việc Hibernate “nhìn thấy list” và tự động persist mọi entity transient nếu mapping không bật cascade.

## 7. Update: thay đổi field thường so với thay đổi FK

Có hai loại thay đổi cần phân biệt:

**A. Sửa nội dung của con:** ví dụ tăng `quantity` của một dòng hàng.

~~~java
OrderLine line = entityManager.find(OrderLine.class, lineId);
line.changeQuantity(4); // giả định domain method đổi field quantity
~~~

Hibernate có thể phát sinh:

~~~sql
UPDATE order_line
SET quantity = ?
WHERE id = ?;
~~~

**B. Thay đổi cha mà con đang tham chiếu:** ví dụ chuyển một nhân viên sang phòng ban khác (trong mô hình cho phép reparent).

~~~java
employee.setDepartment(newDepartment); // owning side thay đổi
~~~

Hibernate có thể phát sinh:

~~~sql
UPDATE employee
SET department_id = ?
WHERE id = ?;
~~~

Trong cả hai trường hợp, không có lý do bắt buộc phải tạo bảng join trung gian nếu FK nằm ở bảng con. Với quan hệ một-nhiều hai chiều, thay đổi association được thể hiện thông qua **cột FK trên một hàng phía nhiều**.

> Ví dụ `PurchaseOrder` ở phần trước có `orphanRemoval = true` và helper chủ động từ chối gán một `OrderLine` cho cha khác. Quy tắc đó phản ánh nghiệp vụ “dòng hàng thuộc riêng một đơn”. Chuyển con sang cha mới cần một mô hình cho phép di chuyển, cùng helper đồng bộ hai phía; không áp dụng nguyên xi ví dụ reparent vào aggregate đang bật orphan removal.

### Cập nhật managed entity không cần gọi update()

Khi `OrderLine` đang managed, Hibernate theo dõi dirty state và tạo SQL lúc flush nếu cần. `session.update()` là một API lịch sử của Hibernate cho tình huống khác; không cần gọi nó sau mỗi setter. Với entity detached, chỉ sửa field không làm database cập nhật tự động; phải thực hiện nghiệp vụ trong persistence context phù hợp hoặc dùng `merge()` theo ngữ nghĩa của JPA.

## 8. Xóa một con: khác biệt giữa bỏ khỏi collection và xóa row

Tác động của thao tác:

~~~java
order.removeLine(line);
~~~

phụ thuộc mapping và schema.

### Với `orphanRemoval = true`

Trong ví dụ ở trên, khi `OrderLine` bị loại khỏi quan hệ cha–con, Hibernate có thể lập lịch **`DELETE`**:

~~~sql
DELETE FROM order_line WHERE id = ?;
~~~

Việc `line.attachTo(null)` giúp đồng bộ object graph trong Java; do orphan removal, ý định nghiệp vụ là **xóa hẳn dòng hàng**, thay vì giữ nó tồn tại với FK null. Trường hợp `order_id NOT NULL` phù hợp với chính sách dòng hàng không được sống ngoài đơn.

### Nếu `orphanRemoval = false`

Nếu bạn bỏ phần tử khỏi list nhưng **không thay đổi owning side**, Hibernate không có lý do đủ để thay đổi FK. Nếu helper đồng thời gán `line.order = null`, Hibernate có thể phát sinh:

~~~sql
UPDATE order_line SET order_id = NULL WHERE id = ?;
~~~

Trong schema `order_id NOT NULL`, lệnh này sẽ thất bại. Nếu nghiệp vụ muốn “tháo liên kết nhưng vẫn giữ con”, phải cho phép nullable FK (`optional = true` và schema phù hợp) hoặc chuyển con sang một cha khác theo logic nghiệp vụ rõ ràng.

### So sánh cascade REMOVE và orphanRemoval

| Cơ chế | Khi nào có ý nghĩa | Tác động thường thấy |
|---|---|---|
| `CascadeType.REMOVE` | Khi xóa **entity cha** bằng `remove(parent)`. | Truyền thao tác remove sang con theo mapping. |
| `orphanRemoval = true` | Khi một con bị loại khỏi quan hệ cha–con; ngoài ra JPA áp dụng semantics xóa con khi cha bị remove. | Xóa hàng con không còn thuộc cha, ngay cả khi cha vẫn sống. |
| `ON DELETE CASCADE` ở DB | Khi DB nhận `DELETE` hàng cha có FK cascade. | Database tự xóa hàng phụ thuộc; ORM phải phối hợp tránh stale context. |

`CascadeType.REMOVE` **không thay thế** `orphanRemoval` để xử lý `order.getLines().remove(line)`. Ngược lại, `orphanRemoval` không có nghĩa một child vừa bị thêm vào collection rồi bị bỏ ra trước khi trở thành managed/persisted phải luôn sinh một câu SQL delete; các quy tắc ORM và trạng thái entity vẫn áp dụng.

## 9. Xóa cha: bảo toàn khóa ngoại

Trong mô hình đơn hàng sở hữu toàn bộ dòng hàng:

~~~java
tx.begin();
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
entityManager.remove(order);
tx.commit();
~~~

Với `cascade = ALL` và `orphanRemoval = true`, Hibernate phải xử lý việc xóa các dòng hàng trước khi xóa hàng cha, hoặc dùng một cơ chế phù hợp constraint. Một chuỗi SQL minh họa:

~~~sql
DELETE FROM order_line WHERE id = 1001;
DELETE FROM order_line WHERE id = 1002;
DELETE FROM purchase_order WHERE id = 101 AND version = 0;
~~~

Số statement và thứ tự thực thi chính xác tùy Hibernate, action queue, batching, cascade và ràng buộc DB. Nếu không bật cascade remove và FK mặc định không có `ON DELETE CASCADE`, database thường chặn xóa cha đang có con bằng foreign-key violation.

### Không tự động xóa con nếu con có vòng đời độc lập

Với ví dụ `Department` – `Employee`, xóa phòng ban không nhất thiết được xóa tất cả nhân viên. Khi đó nên cân nhắc:

- từ chối xóa phòng nếu còn nhân viên;
- chuyển nhân viên sang phòng khác trong transaction trước;
- cho phép `department_id = NULL` nếu nghiệp vụ cho phép chưa phân phòng.

Không bật `CascadeType.REMOVE` chỉ vì muốn tiện cleanup, nếu thực thể phía nhiều có ý nghĩa và đời sống độc lập.

### Database cascade và Hibernate cascade không phải cùng một thứ

`@OnDelete(action = OnDeleteAction.CASCADE)` là mở rộng của Hibernate có thể hỗ trợ DDL foreign key `ON DELETE CASCADE` trong các trường hợp phù hợp. Còn `CascadeType.REMOVE` là chính sách truyền thao tác entity ở lớp ORM. Sử dụng DB cascade có thể giảm số SQL, nhưng ORM caches, persistence context và callbacks/lifecycle cần được tính đến. Không mặc định hai cơ chế có tác dụng thay thế hoàn toàn nhau.

## 10. Di chuyển con sang cha khác: ví dụ cần thận trọng

Trong một hệ thống quản lý nhân viên, có thể chuyển nhân viên từ phòng ban A sang B. Khác với dòng đơn hàng, nhân viên cần tiếp tục tồn tại khi đổi phòng. Mapping thường là:

~~~java
@Entity
class Department {
    @Id
    Long id;

    @OneToMany(mappedBy = "department")
    List<Employee> employees = new ArrayList<>();
}

@Entity
class Employee {
    @Id
    Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    Department department;
}
~~~

Giả sử cả hai department và employee đang managed trong một transaction, code phải đồng bộ:

~~~java
Department oldDepartment = employee.department;
Department newDepartment = ...;

if (oldDepartment != null) {
    oldDepartment.employees.remove(employee);
}

employee.department = newDepartment;             // owning side
newDepartment.employees.add(employee);           // inverse side
~~~

Ví dụ minh họa thao tác từ trong cùng package hoặc qua domain methods tương ứng. SQL thường là:

~~~sql
UPDATE employee
SET department_id = :newDepartmentId
WHERE id = :employeeId;
~~~

Không nên làm hai bước “đặt FK null rồi gán FK mới” nếu FK `NOT NULL` và có thể cập nhật trực tiếp. Tương tự, **đừng chuyển một child đã managed giữa hai collection đang bật orphanRemoval** rồi mong chắc chắn ORM hiểu đó chỉ là chuyển FK: việc remove khỏi cha cũ có thể khiến con bị xem là orphan và lên lịch xóa. Với domain cho phép reparent thường không bật orphan removal, hoặc thiết kế thao tác chuyển một cách rõ ràng phù hợp mapping/phiên bản.

## 11. FetchType: lúc nào Hibernate tải collection và cha?

JPA quy định mặc định khác nhau cho hai annotation:

| Quan hệ | Default JPA | Hành vi |
|---|---|---|
| `@OneToMany` | `FetchType.LAZY` | Collection phía cha thường được tải khi truy cập, nếu chưa initialize. |
| `@ManyToOne` | `FetchType.EAGER` | Quan hệ tới cha mặc định yêu cầu tải eager theo semantics JPA; có thể là join hoặc select bổ sung. |

Vì thế, trong các ứng dụng thực tế thường khai báo tường minh:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();

@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
~~~

`LAZY` là chiến lược tải, **không thay đổi ownership hay vị trí FK**. Kể cả collection chưa tải, FK vẫn nằm ở bảng con. Khi gọi `order.getLines().size()`, Hibernate có thể cần chạy SQL để tải collection hoặc dùng cơ chế tối ưu phù hợp.

### Lazy loading và vòng đời Session

~~~java
PurchaseOrder order;
try (Session session = sessionFactory.openSession()) {
    order = session.find(PurchaseOrder.class, orderId);
}

// Session đã đóng; collection chưa khởi tạo có thể lỗi:
int count = order.getLines().size();
// org.hibernate.LazyInitializationException
~~~

Để tránh lỗi, lấy dữ liệu cần thiết khi persistence context còn hoạt động, hoặc dùng query projection/DTO. Không giải quyết vấn đề bằng cách bật EAGER trên mọi association; nhiều EAGER relationship có thể gây truy vấn nặng hoặc N+1.

### Có cần mở transaction khi đọc?

Một service nên sử dụng transaction phù hợp, kể cả chỉ đọc, để đảm bảo ranh giới tài nguyên và isolation nhất quán. Với Spring, `@Transactional(readOnly = true)` có thể đặt ở service. Nếu framework quản lý transaction/session, không tự đóng EntityManager/Session do nó cấp.

## 12. N+1 query và các chiến lược tải nhiều con

Một query lấy 100 đơn hàng:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
~~~

Nếu collection được tải lazy riêng cho từng đơn hàng, Hibernate có thể chạy:

~~~sql
SELECT ... FROM purchase_order;             -- 1 query lấy 100 đơn
SELECT ... FROM order_line WHERE order_id=?; -- cho đơn thứ nhất
SELECT ... FROM order_line WHERE order_id=?; -- cho đơn thứ hai
-- ... có thể thêm 98 query
~~~

Đây là **N+1 query problem**: một query ban đầu cộng thêm N query phụ. Vị trí FK không phải nguyên nhân duy nhất; N+1 xuất hiện vì fetch plan và cách truy cập collection.

### 12.1. Fetch join khi thực sự cần đầy đủ collection

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    """
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    where o.orderCode like :prefix
    """,
    PurchaseOrder.class
).setParameter("prefix", "PO-%")
 .getResultList();
~~~

SQL conceptually JOIN `purchase_order.id = order_line.order_id`, tải cùng các dòng con. Vì mỗi đơn có nhiều dòng, kết quả SQL có thể lặp phần cột của đơn; Hibernate hợp nhất các entity trong persistence context. Với Hibernate 6, duplicate entity results của join fetch được xử lý theo cơ chế de-duplication của phiên bản, còn `distinct` trong HQL/JPQL và SQL có ngữ nghĩa riêng; dùng khi phù hợp.

**Lưu ý pagination:** Kết hợp collection fetch join với `setFirstResult()/setMaxResults()` có thể dẫn đến in-memory pagination hoặc cảnh báo/lỗi tùy cấu hình Hibernate. Nếu cần phân trang đơn hàng, một cách thiết kế là query trước các ID của cha theo page, sau đó tải collection cần thiết cho nhóm ID đó.

### 12.2. Batch fetching

Hibernate có `@BatchSize` hoặc thuộc tính `hibernate.default_batch_fetch_size` để tải nhiều lazy collections/entities trong những nhóm, giảm số query so với từng collection một.

~~~java
@org.hibernate.annotations.BatchSize(size = 20)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

Hibernate có thể tải các collection chưa khởi tạo cho nhiều parent ID bằng một SQL chứa nhiều giá trị `IN` hoặc chiến lược tương đương phù hợp dialect.

### 12.3. Subselect fetching

`@Fetch(FetchMode.SUBSELECT)` là cơ chế riêng của Hibernate có thể tải collection của nhiều entity cha dựa trên subselect chứa truy vấn cha ban đầu. Nó có thể hữu ích cho một số workload, nhưng không mặc định phù hợp mọi truy vấn.

### 12.4. Projection thay vì load full graph

Nếu API chỉ cần số lượng dòng của mỗi đơn, query aggregate có thể phù hợp hơn:

~~~java
List<Object[]> counts = entityManager.createQuery(
    """
    select o.id, count(l)
    from PurchaseOrder o
    left join o.lines l
    group by o.id
    """,
    Object[].class
).getResultList();
~~~

Truy vấn không nhất thiết phải khởi tạo toàn bộ `List<OrderLine>`. Chọn fetch plan theo dữ liệu endpoint cần, không theo mong muốn tránh mọi lazy exception bằng cách tải tất cả.

## 13. JPQL JOIN nhìn thấy owning side như thế nào?

JPQL/HQL dùng **tên entity và thuộc tính**, không dùng trực tiếp tên cột FK:

~~~java
// Tìm các dòng hàng theo mã đơn:
List<OrderLine> lines = entityManager.createQuery(
    """
    select l
    from OrderLine l
    where l.order.orderCode = :code
    """,
    OrderLine.class
).setParameter("code", "PO-001")
 .getResultList();
~~~

Hibernate hiểu `l.order` là `@ManyToOne`, từ đó có thể join bảng `purchase_order` hoặc tối ưu theo mapping. Ở chiều ngược lại:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    """
    select distinct o
    from PurchaseOrder o
    join o.lines l
    where l.sku = :sku
    """,
    PurchaseOrder.class
).setParameter("sku", "BOOK-01")
 .getResultList();
~~~

`join o.lines` đi qua collection inverse nhưng vẫn là quan hệ được xác định bởi `order_line.order_id` ở database. `mappedBy` không hề cấm query JOIN từ phía cha; nó chỉ nói phía nào ghi FK khi đồng bộ state.

### JOIN và JOIN FETCH khác nhau

- `join o.lines l` phục vụ điều kiện truy vấn, select/filter/order; nó không mặc định ép Hibernate initialize toàn bộ collection.
- `join fetch o.lines` yêu cầu fetch association như một phần kết quả, giảm lazy select sau đó nhưng có thể nhân bản row SQL.

Cả hai đều dùng cùng metadata quan hệ. Đừng dùng fetch join trong mọi query chỉ vì có thể viết được.

## 14. `List`, `Set` và ý nghĩa của thứ tự

`@OneToMany` có thể dùng `List<OrderLine>`, `Set<OrderLine>` hoặc collection khác được JPA hỗ trợ. Chọn kiểu collection vì semantics nghiệp vụ:

| Kiểu | Điểm nổi bật | Lưu ý |
|---|---|---|
| `List<OrderLine>` | Có thứ tự phần tử trong Java. | Thứ tự query sau reload không tự đảm bảo nếu không có `@OrderBy`/`@OrderColumn`. |
| `Set<OrderLine>` | Không muốn phần tử trùng theo `equals()/hashCode()`. | Equality/hash code của entity có ID sinh tự động cần thiết kế cẩn thận. |
| `Collection<OrderLine>` | Mô tả tập phần tử khi không cần API theo index. | Provider vẫn có lựa chọn concrete collection; không nên tùy ý thay collection managed. |

### `@OrderBy`: sắp xếp theo thuộc tính khi đọc

~~~java
@OneToMany(mappedBy = "order")
@OrderBy("sku ASC")
private List<OrderLine> lines = new ArrayList<>();
~~~

Hibernate sử dụng ordering trong SQL hoặc kế hoạch load phù hợp, nhưng `@OrderBy` không tự tạo cột vị trí phần tử.

### `@OrderColumn`: lưu vị trí của phần tử

~~~java
@OneToMany(mappedBy = "order")
@OrderColumn(name = "line_position")
private List<OrderLine> lines = new ArrayList<>();
~~~

`@OrderColumn` yêu cầu cột vị trí trong schema và phát sinh thao tác ghi để đồng bộ thứ tự. Khi reorder/insert giữa danh sách, Hibernate có thể phải update nhiều giá trị `line_position`. Với quan hệ hai chiều, mapping vị trí list cần được thiết kế đúng theo schema, owning/inverse semantics và khả năng provider; **không xem `@OrderColumn` chỉ là annotation đổi cách sort**.

### `Set` và ID sinh tự động

Nếu `hashCode()` của một entity được tính hoàn toàn từ `id` và `id` thay đổi từ null sang số khi persist, phần tử trong `HashSet` có thể không còn được tìm thấy đúng bucket. Cách viết equality phải tính đến transient/managed/detached lifecycle, immutable business key hoặc chiến lược ổn định thích hợp. Dùng `List` không có nghĩa có thể bỏ qua việc tránh thêm trùng một object trong helper.

## 15. Cascades: truyền thao tác vòng đời, không truyền quyền sở hữu FK

`cascade = CascadeType.ALL` thường khiến người mới học tưởng rằng phía cha trở thành owning side. Thực tế:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

**Cascade** quyết định thao tác `persist/merge/remove/refresh/detach` nào trên cha có thể lan đến con. **mappedBy/owning side** quyết định nơi FK được ánh xạ. Hai cơ chế giải quyết hai vấn đề khác nhau.

| CascadeType | Ý nghĩa khái quát | Trường hợp thường dùng |
|---|---|---|
| `PERSIST` | Persist cha lan sang con mới. | Tạo đơn cùng các dòng hàng. |
| `MERGE` | Merge cha lan sang trạng thái con theo semantics JPA. | Đồng bộ aggregate detached có chủ đích. |
| `REMOVE` | Xóa cha lan sang xóa con. | Con thuộc trọn vòng đời cha. |
| `REFRESH` | Refresh cha lan sang con nếu cấu hình. | Đọc lại graph khi thật sự cần. |
| `DETACH` | Detach cha lan sang con. | Tách aggregate khỏi persistence context. |
| `ALL` | Bao gồm các cascade trên. | Aggregate mà cha chịu trách nhiệm toàn bộ vòng đời con. |

Không bật `REMOVE` hoặc `ALL` tùy tiện trên `@ManyToOne`:

~~~java
// Nguy hiểm về nghiệp vụ nếu xóa một line lại xóa cả order:
@ManyToOne(cascade = CascadeType.REMOVE)
private PurchaseOrder order;
~~~

Trong mô hình nhiều con cùng tham chiếu một cha, cascade REMOVE **từ con lên cha** có thể làm xóa cha khi chỉ muốn xóa một con, hoặc vi phạm FK với những con khác. Thường xuyên cần cascade từ aggregate root xuống owned children, chứ không cascade xóa từ từng child lên shared parent.

## 16. Nullable FK, `optional` và giá trị `null`

Hai annotation thường gặp trên phía nhiều:

~~~java
@ManyToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
~~~

- `optional = false` biểu diễn association bắt buộc ở mức mapping JPA.
- `@JoinColumn(nullable = false)` mô tả nullability cột FK trong schema/mapping.
- `order_line.order_id NOT NULL` là constraint thực tế của database.

Ba lớp này nên nhất quán. Một annotation không thay thế hoàn toàn constraint ở DB. Nếu ứng dụng gọi setter làm `order = null`, Hibernate hoặc database có thể từ chối khi flush; việc collection ở cha vẫn chứa con không cứu được owning side `null`.

Với association tùy chọn:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "department_id", nullable = true)
private Department department;
~~~

Trong schema cho phép FK null, việc detach từ phòng ban có thể được biểu diễn bằng `UPDATE employee SET department_id = NULL`. Hành vi có phải là “xóa employee” hay không vẫn phụ thuộc `orphanRemoval` và nghiệp vụ.

## 17. `mappedBy` phải là tên field/property ở entity con

Đây là lỗi cấu hình phổ biến:

~~~java
@OneToMany(mappedBy = "order_id") // SAI: đây là tên cột SQL
private List<OrderLine> lines;
~~~

Nếu entity con là:

~~~java
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder purchaseOrder;
~~~

thì `mappedBy` phải là `"purchaseOrder"`:

~~~java
@OneToMany(mappedBy = "purchaseOrder")
private List<OrderLine> lines;
~~~

Hibernate/JPA kiểm tra mapping khi khởi động; tên `mappedBy` sai hoặc tham chiếu thuộc tính không biểu diễn quan hệ tương ứng thường gây mapping exception. Không cần tạo field `orderId` trong entity con chỉ để `mappedBy` trỏ đến nó; Hibernate có thể quản lý FK qua object association `PurchaseOrder order`.

### Nếu muốn đọc ID cha mà không initialize association?

Thông thường có thể truy cập `line.getOrder().getId()` với proxy và identifier known mà không cần tải toàn bộ cha trong nhiều cấu hình Hibernate, nhưng không xem đó là bảo đảm tuyệt đối cho mọi access type/provider/runtime. Một lựa chọn là projection lấy ID theo query. Nếu thêm một field `orderId` ánh xạ cùng cột `order_id`, cần tránh mapping hai nguồn cùng ghi cột:

~~~java
@Column(name = "order_id", insertable = false, updatable = false)
private Long orderId;
~~~

Field chỉ đọc như trên có thể hữu ích trong trường hợp thật sự cần, nhưng trạng thái `orderId` trong cùng entity có thể không được cập nhật tức thời khi đổi `line.order` cho đến khi Hibernate đồng bộ/refresh. Không mặc định nhân đôi mapping nếu không có nhu cầu thực tế.

## 18. Sơ đồ flush: ai tạo SQL cho quan hệ?

~~~mermaid
sequenceDiagram
    participant App as Java Service
    participant P as PurchaseOrder
    participant L as OrderLine
    participant H as Hibernate Session
    participant DB as Database

    App->>P: addLine(line)
    P->>P: lines.add(line)
    P->>L: attachTo(this)
    Note over L: order reference là owning side
    App->>H: persist(order)
    H->>H: cascade persist tới line
    App->>H: flush() / commit()
    H->>DB: INSERT purchase_order(...)
    DB-->>H: parent row exists
    H->>DB: INSERT order_line(order_id, ...)
    DB-->>H: FK hợp lệ
    H-->>App: flush kết thúc
~~~

Sơ đồ diễn tả bản chất, không phải trình tự lời gọi nội bộ cố định. Hibernate có persistence context, ActionQueue, entity insert/update/delete actions, SQL generation và JDBC coordinator; ID generator có thể lấy sequence trước các bước insert. Với entity đã managed và association đổi, owning side dirty checking giúp Hibernate tạo `UPDATE` FK thích hợp khi flush.

### Khi nào SQL chạy?

Gọi `order.addLine(line)` chỉ cập nhật Java references. Khi session/context đang quản lý các entity liên quan, Hibernate sẽ phát hiện các thay đổi cần ghi và đồng bộ ở flush. Flush có thể xảy ra khi gọi tường minh `entityManager.flush()`, trước commit, hoặc trước một số query theo flush mode và query spaces.

**Flush không phải commit.** Sau flush thành công, transaction vẫn có thể rollback; khi đó cả row cha và row con mới insert đều bị hủy nếu chúng thuộc cùng transaction database.

## 19. Trường hợp entity con đã tồn tại hoặc detached

Không phải mọi `OrderLine` đưa vào list đều là entity mới:

| Trạng thái con | Ý nghĩa | Điều cần chú ý |
|---|---|---|
| **Transient** | Object mới chưa được quản lý; chưa có hàng DB. | Cần persist con hoặc cascade PERSIST từ cha. |
| **Managed** | Đang được persistence context quản lý. | Đổi `line.order` có thể được dirty checked và ghi FK ở flush. |
| **Detached** | Object từng managed nhưng đã tách khỏi context. | Thay field không tự ghi; `persist()` có thể không hợp lệ, merge có ngữ nghĩa khác. |
| **Removed** | Entity đã được đánh dấu xóa. | Không nên “cứu” bằng cách thêm lại vào collection và mong ORM bỏ lệnh DELETE trong mọi tình huống. |

### Vì sao `merge()` cần thận trọng?

~~~java
PurchaseOrder managed = entityManager.merge(detachedOrder);
~~~

`merge()` sao chép trạng thái của detached graph vào **managed instance được trả về**; nó không biến object `detachedOrder` ban đầu thành managed. Với `cascade = MERGE`, Hibernate còn duyệt các association liên quan. Nếu detached graph có collection thiếu con vì API client gửi danh sách không đầy đủ, việc merge cùng `orphanRemoval` có thể dẫn đến những thay đổi ngoài ý định.

Đối với API cập nhật đơn hàng, thường dễ kiểm soát hơn khi:

1. Tải entity managed hiện tại trong transaction.
2. Kiểm tra quyền và điều kiện nghiệp vụ.
3. Gọi domain methods để thêm/sửa/xóa từng dòng có chủ đích.
4. Commit transaction.

Không coi request DTO chứa một danh sách ID là toàn bộ trạng thái quan hệ rồi gọi merge một cách máy móc, đặc biệt với aggregate có orphan removal.

## 20. Optimistic locking và xung đột khi sửa danh sách

Ví dụ `PurchaseOrder` đã có `@Version`:

~~~java
@Version
private long version;
~~~

Version giúp Hibernate phát hiện các cập nhật cạnh tranh theo mapping và optimistic-locking semantics. Tuy nhiên, thay đổi một **inverse collection** `@OneToMany(mappedBy = "order")` không nên bị coi là luôn chắc chắn tăng version của cha ở mọi provider/configuration. Cột FK do phía con sở hữu; versioning đối với thay đổi collection/phía inverse phụ thuộc phạm vi optimistic locking và chi tiết mapping Hibernate.

Ví dụ hai người cùng thêm dòng vào một đơn:

~~~text
Transaction A: đọc order 101, thêm line A
Transaction B: đọc order 101, thêm line B
Transaction A: commit
Transaction B: commit
~~~

Trong nhiều mô hình DB, cả hai dòng mới có thể được insert thành công nếu không vi phạm ràng buộc riêng; điều này chưa chắc là lỗi. Nhưng nếu nghiệp vụ yêu cầu “mỗi đơn chỉ tối đa N dòng” hoặc “không cho hai dòng cùng SKU”, transaction phải phối hợp concurrency control:

- Constraint UNIQUE phù hợp, ví dụ `UNIQUE(order_id, sku)` nếu nghiệp vụ thực sự cấm trùng SKU.
- Optimistic/pessimistic locking tại aggregate hoặc bản ghi phù hợp.
- Atomic update hoặc transaction isolation phù hợp khi kiểm tra điều kiện đếm.

**Chỉ có `@Version` trên cha không tự bảo vệ tất cả invariant ở bảng con** nếu thay đổi FK/collection không dẫn đến kiểm tra version theo cách ứng dụng tưởng. Nên thiết kế và kiểm chứng một đường ghi duy nhất phù hợp quy tắc nghiệp vụ.

## 21. Khi collection lớn: không cần tải tất cả con để biết số lượng

Một `PurchaseOrder` có hàng nghìn `OrderLine` sẽ tạo collection lớn trong persistence context nếu bạn gọi `getLines()` để tải hết. Các thao tác như `contains()`/`size()` trên collection lazy có thể kích hoạt SQL hoặc initialization tùy Hibernate và collection implementation.

Nếu UI chỉ cần số dòng:

~~~java
Long count = entityManager.createQuery(
    """
    select count(l)
    from OrderLine l
    where l.order.id = :orderId
    """,
    Long.class
).setParameter("orderId", orderId)
 .getSingleResult();
~~~

Nếu chỉ muốn xóa một con đã biết ID, có thể tải con trong transaction, xác minh nó thuộc cha dự kiến, rồi xóa qua domain method/`remove()` phù hợp. Đừng bắt buộc load toàn bộ collection trong mọi endpoint nếu không cần.

### Xử lý batch

Khi thêm hàng nghìn con, batching có thể hữu ích:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
~~~

Generator ID kiểu `SEQUENCE` và các lệnh insert cùng shape giúp cơ hội JDBC batching cao hơn. Với `IDENTITY`, insert batching entity thường bị hạn chế vì DB sinh khóa khi insert. Khả năng batching còn phụ thuộc mapping, driver và flush boundaries. `@OneToMany(mappedBy)` tự nó không đảm bảo mọi insert được gom batch.

Khi xử lý batch lớn, cân nhắc `flush()`/`clear()` theo lô và việc tách entity khỏi persistence context. Với graph cha–con, clear giữa chừng có thể tách parent mà phần code sau vẫn cần cascade; phải tổ chức transaction và object state cẩn thận, không áp dụng một vòng lặp flush/clear máy móc.

## 22. Serialization API và vòng tham chiếu hai chiều

Nếu trả thẳng entity cho JSON serializer, quan hệ hai chiều có thể tạo một chuỗi đệ quy:

~~~text
Order -> lines[0] -> order -> lines[0] -> order -> ...
~~~

Ngoài vấn đề vòng tham chiếu, serializer có thể kích hoạt lazy loading sau khi session đã đóng. Do đó với API nên cân nhắc chuyển sang DTO:

~~~java
public record OrderLineView(Long id, String sku, int quantity) {}

public record OrderView(
    Long id,
    String orderCode,
    List<OrderLineView> lines
) {}
~~~

Tạo DTO khi còn trong transaction:

~~~java
OrderView view = new OrderView(
    order.getId(),
    order.getOrderCode(),
    order.getLines().stream()
        .map(line -> new OrderLineView(
            line.getId(), line.getSku(), line.getQuantity()
        ))
        .toList()
);
~~~

Có thể cấu hình Jackson với các annotation xử lý back-reference hoặc identity, nhưng chúng liên quan đến serialization, **không thay đổi owning side/FK của JPA**. DTO còn giúp giới hạn dữ liệu API, tránh lộ thông tin nhạy cảm và kiểm soát truy vấn được thực hiện ở service layer.

## 23. Test quan hệ hai chiều như thế nào?

Trong một integration test dùng database thật hoặc test database tương thích, hãy tạo một cha và hai con, flush, clear, rồi đọc lại để xác minh **cả dữ liệu database và object graph**:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

PurchaseOrder order = new PurchaseOrder("PO-TEST");
OrderLine first = new OrderLine("A", 1);
OrderLine second = new OrderLine("B", 2);

order.addLine(first);
order.addLine(second);

entityManager.persist(order);
entityManager.flush();
Long orderId = order.getId();

entityManager.clear(); // lần đọc tiếp không dùng object managed cũ

PurchaseOrder reloaded =
    entityManager.find(PurchaseOrder.class, orderId);

assert reloaded != null;
assert reloaded.getLines().size() == 2;
for (OrderLine line : reloaded.getLines()) {
    assert line.getOrder().getId().equals(orderId);
}

tx.commit();
~~~

Nếu môi trường tắt Java assertions, cần dùng assertion API của JUnit/AssertJ để kết quả test không phụ thuộc cờ `-ea`. Đoạn mã trên minh họa trình tự và invariant, không thay thế một test class/framework hoàn chỉnh.

### Xác minh cột FK trực tiếp

~~~sql
SELECT l.id, l.order_id, l.sku
FROM order_line l
WHERE l.order_id = :order_id
ORDER BY l.id;
~~~

Kết quả phải có hai dòng cùng `order_id` trùng khóa cha. Đây là bằng chứng rõ ràng rằng FK được lưu ở **bảng nhiều**. Nếu chỉ nhìn collection trong bộ nhớ, bạn có thể bỏ sót trường hợp hai phía Java chưa đồng bộ.

### Test remove/orphanRemoval

Trong transaction mới, tải đơn và collection, gọi `removeLine(first)` trên một phần tử managed, flush, clear và query lại:

- Collection cha giảm một phần tử.
- Với `orphanRemoval = true`, row con bị xóa khỏi `order_line`.
- Hàng cha vẫn tồn tại.
- Không có dòng con nào tham chiếu FK sai.

### Test constraint

Thử persist `OrderLine` có `order = null` trong schema `order_id NOT NULL`. Dự kiến Hibernate hoặc DB từ chối khi flush. Sau lỗi, rollback và kết thúc persistence context; không tiếp tục dùng một session/transaction vừa gặp lỗi constraint.

## 24. Các lỗi mapping và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Thêm child vào list nhưng DB ghi `order_id = NULL` | Chỉ sửa inverse collection, không gán `child.order` | Dùng helper cập nhật cả hai phía; kiểm tra owning side trước flush. |
| Hibernate báo lỗi `mappedBy` | Tên trong `mappedBy` không đúng property ở child | Dùng tên field Java của `@ManyToOne`, không dùng tên cột SQL. |
| Có bảng nối ngoài dự kiến | Ánh xạ one-to-many một chiều hoặc cấu hình không khai báo đúng `mappedBy`/`JoinColumn` | Kiểm tra mapping cả hai entity và schema generation. |
| Xóa khỏi list nhưng row vẫn còn | `orphanRemoval = false` hoặc owning side không đổi | Xác định nghiệp vụ detach hay delete; mapping/schema nullability phải khớp. |
| Xóa child làm lỗi FK hoặc xóa nhầm cha | Cascade REMOVE đặt từ child lên parent hoặc phụ thuộc khác | Kiểm tra chiều cascade, delete constraints và graph liên quan. |
| Query 100 cha phát sinh hơn 100 câu SQL | N+1 lazy collections | Dùng fetch join/batch fetching/projection phù hợp. |
| `LazyInitializationException` ở controller | Collection chưa tải sau khi session đóng | Load dữ liệu/DTO trong transaction. |
| JSON serialize đệ quy vô hạn | Hai chiều parent -> children -> parent | Dùng DTO hoặc cấu hình serializer có chủ đích. |
| Vừa chuyển child sang cha mới đã bị xóa | `orphanRemoval` ở cha cũ làm child thành orphan | Dùng mô hình không orphan removal nếu cho phép reparent, hoặc thiết kế chuyển khác. |
| `ConstraintViolationException` khi persist child | FK chưa có parent, FK null, schema constraint không khớp | Kiểm tra `child.order`, thứ tự flush và cascade persist/ID strategy. |
| Collection trong Java khác DB mặc dù FK đúng | Chỉ sửa owning side mà không cập nhật inverse collection đang loaded | Dùng domain helper và refresh/reload khi cần. |

### Sai lầm: đặt `@JoinColumn` trên phía inverse

~~~java
@OneToMany(mappedBy = "order")
@JoinColumn(name = "order_id") // Cấu hình chồng lấn ownership
private List<OrderLine> lines;
~~~

Đây không phải cách chuẩn để mô hình hóa quan hệ hai chiều một FK. `mappedBy` nói rằng collection không sở hữu association; `@JoinColumn` thường dùng tại owning side. Hãy đặt `@JoinColumn(name = "order_id")` ở field `OrderLine.order` và để collection phía cha chỉ dùng `mappedBy = "order"`.

### Sai lầm: nhầm `mappedBy` với cascade

`mappedBy` là metadata **quan hệ**. Nó không tự bật cascade persist/remove, không tự xóa orphan và không tự điều khiển fetch mode. Các hành vi này cần được quyết định bằng annotation riêng.

## 25. So sánh ba cách biểu diễn one-to-many

| Mô hình | Mapping | FK/Join table | Điểm đáng chú ý |
|---|---|---|---|
| Chỉ một chiều từ con | `@ManyToOne @JoinColumn` ở con | FK ở bảng con | Đơn giản nếu không cần `parent.getChildren()`. |
| Hai chiều | `@OneToMany(mappedBy)` ở cha + `@ManyToOne @JoinColumn` ở con | FK ở bảng con | Điều hướng hai chiều; owning side là con; phải đồng bộ Java references. |
| Một chiều từ cha | `@OneToMany` ở cha, không có `mappedBy` | Có thể dùng join table mặc định hoặc FK nếu chỉ rõ `@JoinColumn` | SQL/lifecycle/chi phí có thể khác; cha là phía sở hữu theo mapping cụ thể. |

### Khi chỉ cần truy vấn từ cha, có nhất thiết phải khai báo collection?

Không. Có thể giữ quan hệ chỉ ở phía con:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "order_id")
private PurchaseOrder order;
~~~

Khi cần các dòng của đơn:

~~~java
List<OrderLine> lines = entityManager.createQuery(
    "select l from OrderLine l where l.order.id = :orderId",
    OrderLine.class
).setParameter("orderId", orderId)
 .getResultList();
~~~

Cách này bỏ bớt việc quản lý collection inverse trong Java. Chỉ thêm `@OneToMany(mappedBy)` khi object graph cần truy cập/điều khiển collection một cách thực chất, không chỉ vì database có FK.

## 26. Quy trình thiết kế quan hệ một–nhiều hai chiều

Trước khi viết annotation, xác định:

1. **Mối quan hệ trong domain:** Một cha có bao nhiêu con? Mỗi con có bắt buộc có cha? Có được di chuyển con giữa các cha không?
2. **Schema:** FK nằm ở bảng con, có `NOT NULL` không, có cần index/unique/check constraint không?
3. **Owning side:** Field `@ManyToOne` trên con, `@JoinColumn` chỉ đúng cột FK.
4. **Inverse side:** `@OneToMany(mappedBy = "tênFieldChaTrongCon")` trên cha.
5. **Đồng bộ references:** Domain methods cập nhật cả list và field `child.parent`; hạn chế public mutation ở hai nơi khác nhau.
6. **Lifecycle:** Con sống độc lập hay thuộc hoàn toàn cha? Chọn cascade và orphanRemoval theo nghiệp vụ.
7. **Fetch plan:** Mặc định lazy ở phía collection, chủ động fetch cha hoặc con khi cần, tránh N+1 và lazy loading ngoài transaction.
8. **Transaction và concurrency:** Persist/update/delete trong transaction; kiểm tra optimistic locking, FK, unique constraint và các invariant có đồng thời.
9. **Kiểm chứng:** Flush, clear, load lại, đối chiếu SQL/DB và kiểm tra cả hai hướng Java sau mỗi thao tác tạo, đổi cha và xóa.

### Mô hình ghi nhớ

~~~text
Java phía một                    Java phía nhiều
PurchaseOrder.lines              OrderLine.order
@OneToMany(mappedBy="order")     @ManyToOne
        |                         @JoinColumn(name="order_id")
        |                                  |
        +------ cùng một association ------+
                                           |
                                           v
                                Database: order_line.order_id
                                      FOREIGN KEY
                                           |
                                           v
                                purchase_order.id
~~~

**Hai chiều** có nghĩa cả cha và con đều có đường tham chiếu trong Java. **Một owning side** có nghĩa Hibernate dùng phía `@ManyToOne` để xác định giá trị FK ở database. Khi cả hai phía Java được đồng bộ, cascade/orphanRemoval được chọn theo vòng đời nghiệp vụ và transaction bảo vệ thao tác ghi, `@OneToMany(mappedBy)` trở thành một ánh xạ rõ ràng, dễ kiểm soát và hiệu quả cho quan hệ một–nhiều trong Hibernate.
