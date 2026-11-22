# Phân biệt thay đổi liên kết và thay đổi vòng đời entity

Trong JPA, khi hai entity có quan hệ với nhau, một thao tác đơn giản như `order.setCustomer(otherCustomer)` hay `order.getLines().remove(line)` có thể mang những ý nghĩa rất khác nhau. Có thao tác chỉ **đổi liên kết** giữa hai bản ghi, chẳng hạn cập nhật khóa ngoại hoặc xóa một hàng của bảng nối. Có thao tác lại **đổi vòng đời** một entity: tạo mới, chuyển sang managed, đánh dấu xóa, hoặc đồng bộ trạng thái từ detached. Một số cấu hình như `cascade` và `orphanRemoval` có thể khiến hai loại thay đổi tác động lẫn nhau, nhưng chúng không phải là một khái niệm.

Nắm được ranh giới này đặc biệt quan trọng với **`@ManyToOne`, `@OneToMany`, `@OneToOne` và `@ManyToMany`**: một sai lầm trong mapping có thể khiến dữ liệu không đổi như mong đợi, gây lỗi khóa ngoại, hoặc xóa cả một entity mà nhiều đối tượng khác còn cần.

Mục tiêu của bài học là nhận diện chính xác **đang thay đổi đường nối giữa hai entity hay đang thay đổi sự tồn tại/trạng thái của một entity**, và biết cách thể hiện ý định đó một cách nhất quán trong Java, JPA và cơ sở dữ liệu.

## 1. Hai lớp ý nghĩa khác nhau

### 1.1. Thay đổi liên kết (association change)

Một **liên kết** cho biết entity A tham chiếu entity B như thế nào. Trong database quan hệ, liên kết thường được biểu diễn bằng **foreign key** hoặc **bảng nối (join table)**.

Ví dụ một đơn hàng thuộc về khách hàng:

```text
customers                         orders
+----+----------+                 +----+-------------+-------+
| id | name     |                 | id | customer_id | total |
+----+----------+                 +----+-------------+-------+
|  1 | Mai      | <-------------- | 10 |           1 |   200 |
|  2 | Nam      |                 +----+-------------+-------+
+----+----------+
```

Nếu chuyển đơn 10 từ khách hàng 1 sang khách hàng 2, kết quả mong muốn là:

```sql
UPDATE orders
SET customer_id = 2
WHERE id = 10;
```

**Không có hàng nào của `customers` hoặc `orders` bị tạo mới hay xóa.** Chỉ giá trị `orders.customer_id` đổi. Đó là **thay đổi liên kết**.

Tương tự, trong quan hệ nhiều-nhiều giữa `students` và `courses`, việc hủy đăng ký một môn học có thể chỉ cần:

```sql
DELETE FROM student_courses
WHERE student_id = 5 AND course_id = 9;
```

Hàng trong bảng nối bị xóa, nhưng **student 5 và course 9 vẫn tồn tại**. Đây vẫn là thay đổi liên kết, không phải xóa entity khóa học.

### 1.2. Thay đổi vòng đời (entity lifecycle change)

Vòng đời entity là trạng thái liên quan đến một **persistence context** và sự tồn tại của bản ghi:

- **Transient/new:** object vừa tạo bằng `new`, chưa được JPA quản lý; thường chưa có bản ghi tương ứng.
- **Managed:** object đang được một persistence context theo dõi, có thể được đồng bộ với database khi flush.
- **Detached:** object từng managed nhưng hiện không còn được context theo dõi; bản ghi database có thể vẫn tồn tại.
- **Removed:** một managed entity được đánh dấu xóa trong persistence context; SQL `DELETE` thường phát sinh khi flush và thay đổi thực sự được xác nhận khi transaction commit.

Ví dụ:

```java
em.persist(newCustomer); // Đưa entity mới vào vòng đời managed.
em.remove(oldCustomer);  // Đánh dấu một managed entity cần xóa.
```

Hai thao tác này khác bản chất với `order.setCustomer(otherCustomer)`. Khi xóa một customer, hàng `customers` có thể bị xóa; khi chỉ chuyển order sang customer khác, customer cũ vẫn tồn tại.

### 1.3. Bảng phân biệt nhanh

| Thao tác nghiệp vụ | Loại thay đổi chính | SQL minh họa | Hàng entity còn tồn tại? |
|---|---|---|---|
| Chuyển đơn sang khách hàng khác | Liên kết | `UPDATE orders SET customer_id = ...` | Đơn và cả hai khách hàng vẫn tồn tại |
| Gỡ đơn khỏi khách hàng, FK cho phép null | Liên kết | `UPDATE orders SET customer_id = NULL` | Đơn vẫn còn |
| Học viên bỏ một khóa học `@ManyToMany` | Liên kết | `DELETE FROM enrollment_join ...` | Học viên và khóa học vẫn còn |
| Tạo khách hàng mới | Vòng đời | `INSERT INTO customers ...` | Có hàng mới |
| Xóa đơn hàng | Vòng đời | `DELETE FROM orders WHERE id = ...` | Hàng đơn được xóa sau commit thành công |
| Gỡ dòng hàng ra khỏi đơn có `orphanRemoval=true` | Liên kết **kèm** thay đổi vòng đời phụ thuộc | `DELETE FROM order_lines ...` | Dòng hàng bị xóa nếu thuộc tính orphan removal được áp dụng |
| Xóa đơn có `cascade=REMOVE` tới dòng hàng | Vòng đời lan truyền theo quan hệ | `DELETE` dòng hàng, rồi `DELETE` đơn | Cả đơn và các dòng được xóa nếu transaction thành công |

Một câu lệnh SQL `DELETE` không đủ để kết luận “entity bị xóa”: xóa một **hàng của bảng nối** là gỡ liên kết; xóa **hàng đại diện entity** là xóa entity. Cần biết bảng nào đại diện cho đối tượng nào.

## 2. Vòng đời JPA không đồng nhất với trạng thái liên kết

Hãy nhìn hai chiều độc lập:

```text
                 ENTITY LIFECYCLE
new --persist--> managed --detach/close--> detached
                  |
                  +---remove---> removed
                  |
                  +---dirty checking / flush / commit---> SQL cập nhật

                 ASSOCIATION GRAPH
Order #10 ----customer----> Customer #1
     |
     +---setCustomer(Customer #2)--->
Order #10 ----customer----> Customer #2
```

Một entity managed có thể đổi từ liên kết A sang B **mà không đổi trạng thái managed**. Ngược lại, một entity có thể chuyển managed → detached **mà không đổi liên kết nào ở database**.

Một số điểm dễ nhầm:

- `em.detach(order)` chỉ đưa `order` ra khỏi persistence context (và có thể lan truyền `DETACH` theo cascade). Nó **không đặt `customer_id` về null**.
- `em.clear()` giải phóng tất cả managed entity khỏi context hiện tại; không xóa hàng.
- `em.merge(detachedOrder)` tạo/tìm managed instance rồi sao chép trạng thái từ detached object. Nó **có thể** làm đổi liên kết khi trạng thái association được merge, nhưng bản thân `merge` không đồng nghĩa với `persist` hoặc `remove`.
- `em.flush()` đồng bộ các thay đổi đang quản lý thành SQL trong transaction. `flush` không tự commit; một transaction rollback sẽ hủy tác động chưa được commit.

Để hiểu hành vi cuối cùng, cần xét cùng lúc: **trạng thái entity, bên sở hữu quan hệ, cấu hình cascade/orphanRemoval và ràng buộc database**.

## 3. Owning side quyết định ai ghi khóa ngoại

Trong quan hệ hai chiều của JPA, hai entity có thể cùng giữ tham chiếu đến nhau, nhưng chỉ **một phía sở hữu mapping của quan hệ (owning side)** chịu trách nhiệm cập nhật khóa ngoại hoặc bảng nối.

### 3.1. Ví dụ `Customer` – `PurchaseOrder`

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }

    // Helper đồng bộ hai phía của object graph.
    public void addOrder(PurchaseOrder order) {
        if (order == null) {
            throw new IllegalArgumentException("Order không được null");
        }
        order.setCustomer(this);
    }
}
```

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {}

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer next) {
        if (this.customer == next) {
            return;
        }

        Customer previous = this.customer;

        if (previous != null) {
            previous.getOrders().remove(this);
        }
        this.customer = next;
        if (next != null && !next.getOrders().contains(this)) {
            next.getOrders().add(this);
        }
    }
}
```

Trong mapping này:

- `PurchaseOrder.customer` là **owning side** vì `@ManyToOne` có `@JoinColumn(name="customer_id")`. Giá trị field này điều khiển cột `purchase_orders.customer_id`.
- `Customer.orders` là **inverse side** vì `mappedBy="customer"` chỉ về tên field sở hữu quan hệ trong `PurchaseOrder`.
- Một helper như `setCustomer` giữ **hai mặt trong bộ nhớ** nhất quán; phần cập nhật database vẫn dựa trên owning side.

Đoạn helper minh họa dùng `contains` và `remove` trên collection; trong hệ thống thật, thao tác này cần thiết kế theo semantics `equals`/`hashCode` và hành vi collection lazy. Nếu collection lớn, không nên tùy tiện tải toàn bộ chỉ để sửa một liên kết; có thể dùng service chuyên biệt hoặc repository.

### 3.2. Chỉ sửa inverse side chưa đủ

Giả sử đã tải hai customer và order trong cùng transaction:

```java
Customer mai = em.find(Customer.class, 1L);
Customer nam = em.find(Customer.class, 2L);
PurchaseOrder order = em.find(PurchaseOrder.class, 10L);

// Không đủ để chuyển liên kết:
mai.getOrders().remove(order);
nam.getOrders().add(order);
```

Nếu `order.customer` vẫn là `mai`, JPA không có cơ sở từ owning side để ghi `customer_id = 2`. Tập hợp Java ở inverse side có vẻ đổi nhưng database có thể vẫn giữ liên kết cũ.

Cách thể hiện ý định rõ hơn:

```java
order.setCustomer(nam);
```

Helper cập nhật owning side, đồng thời phản ánh thay đổi ở hai collection. Khi flush trong transaction, JPA có thể phát sinh:

```sql
UPDATE purchase_orders
SET customer_id = 2
WHERE id = 10;
```

**Quy tắc trọng tâm:** Với quan hệ hai chiều, hãy xác định owning side; một thay đổi ở inverse side `mappedBy` đơn thuần không phải căn cứ đáng tin cậy để thay đổi liên kết trong database.

## 4. Thay đổi liên kết không đồng nghĩa với xóa entity được tham chiếu

### 4.1. Nhiều đơn hàng cùng tham chiếu một khách hàng

Giả sử một customer có 100 orders. Nếu một đơn hàng được chuyển sang customer khác, không có lý do gì để gọi:

```java
em.remove(oldCustomer);  // Sai ý định nếu chỉ chuyển một đơn hàng.
```

Điều cần làm là cập nhật field quan hệ của chính đơn hàng:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
Customer next = em.find(Customer.class, nextCustomerId);

if (order == null || next == null) {
    throw new IllegalArgumentException("Order hoặc Customer không tồn tại");
}
order.setCustomer(next);
```

Customer cũ có thể vẫn đang được hàng trăm đơn khác tham chiếu. Gọi `remove` có thể thất bại vì foreign key hoặc xóa dữ liệu không mong muốn nếu cascade database đang bật.

### 4.2. Gỡ liên kết về `null`

Nếu mối quan hệ là tùy chọn:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "assignee_id", nullable = true)
private Employee assignee;
```

có thể dùng:

```java
task.setAssignee(null);
```

Kết quả logic là:

```sql
UPDATE tasks
SET assignee_id = NULL
WHERE id = ?;
```

Task vẫn tồn tại; Employee vẫn tồn tại. Nhưng nếu mapping dùng `optional=false`, cột FK `NOT NULL`, hoặc có ràng buộc khác, thao tác gỡ về null có thể thất bại. Muốn hỗ trợ “chưa có người phụ trách”, thiết kế database và domain phải cho phép trạng thái đó.

### 4.3. Chuyển liên kết là thao tác trên một hàng chứa FK

Đặt lại một association `@ManyToOne` hay owning `@OneToOne` thường là một phép **UPDATE khóa ngoại**. Gỡ association nhiều-nhiều thường là **DELETE hàng bảng nối**. Sự khác nhau về SQL không làm thay đổi nguyên tắc: nếu không có cascade/orphan removal tác động vòng đời, hai entity đầu cuối vẫn tồn tại.

## 5. `cascade` là lan truyền thao tác vòng đời, không quyết định owning side

Thuộc tính `cascade` ở annotation quan hệ cho biết **khi thực hiện một thao tác JPA lên entity nguồn, thao tác nào được lan truyền sang entity liên quan**.

### 5.1. Các loại cascade

| CascadeType | Thao tác có thể lan truyền | Khi hữu ích |
|---|---|---|
| `PERSIST` | `persist(parent)` lan truyền `persist` sang đối tượng con phù hợp | Tạo aggregate cha cùng các con mới |
| `MERGE` | `merge(parent)` lan truyền merge state sang đối tượng liên quan | Hợp nhất một object graph detached có kiểm soát |
| `REMOVE` | `remove(parent)` lan truyền remove sang các entity đích | Xóa các entity con chỉ tồn tại cùng cha |
| `REFRESH` | `refresh(parent)` đọc lại trạng thái từ database của đối tượng liên quan | Khi thật sự cần làm mới graph |
| `DETACH` | `detach(parent)` tách các entity liên quan khỏi context | Điều khiển phạm vi managed state |
| `ALL` | Tập hợp `PERSIST, MERGE, REMOVE, REFRESH, DETACH` | Chỉ khi thực sự muốn lan truyền tất cả thao tác trên quan hệ đó |

**Cascade không chỉ định phía ghi FK.** Ví dụ `cascade=PERSIST` trên `Customer.orders` có thể làm các Order mới được persist khi Customer được persist, nhưng cột `customer_id` vẫn do owning side `PurchaseOrder.customer` chi phối.

### 5.2. `cascade=PERSIST` không tự gán quan hệ

Giả sử:

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderLine> lines = new ArrayList<>();
```

Thêm line mới vào danh sách:

```java
order.getLines().add(new OrderLine("Keyboard", 1));
em.persist(order);
```

Cascade có thể lan truyền `persist` tới line, nhưng nếu `OrderLine.order` vẫn `null` thì owning side không được thiết lập. Khi FK bắt buộc không null, lệnh INSERT của line có thể thất bại; nếu FK nullable, line có thể không được gắn vào order trong database.

Khi dùng quan hệ hai chiều, thao tác thêm phải thiết lập **cả hai phía** để graph nhất quán:

```java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setOrder(this); // Bên sở hữu FK.
}
```

Ý nghĩa:

- `addLine`: cập nhật liên kết đối tượng.
- `cascade=PERSIST`: có thể khiến line mới đi từ transient sang managed khi persist order.
- `flush`: tạo SQL `INSERT` cho entity mới và điền FK theo owning side.

Đây là ba trách nhiệm riêng biệt.

### 5.3. `cascade=REMOVE` có thể rất nguy hiểm trên quan hệ chia sẻ

Nếu `PurchaseOrder.customer` có `cascade = CascadeType.REMOVE`, xóa một order có thể yêu cầu xóa luôn Customer. Nhưng cùng customer có thể thuộc hàng trăm order khác. Đây hiếm khi là ý định nghiệp vụ đúng.

Tương tự, trên `@ManyToMany`, không nên thường xuyên dùng `CascadeType.REMOVE` hoặc `ALL` nếu hai entity đầu cuối được chia sẻ. Ví dụ xóa một student **không được tự xóa course** mà những student khác đang học.

Một quy tắc thiết kế: chỉ cascade thao tác **xóa entity** khi đối tượng đích thực sự có vòng đời phụ thuộc vào đối tượng nguồn, không dùng cho quan hệ chia sẻ độc lập.

## 6. `orphanRemoval`: khi gỡ liên kết có thể kéo theo xóa entity con

### 6.1. Ý nghĩa của orphan removal

`orphanRemoval=true` là cơ chế JPA dành cho quan hệ `@OneToOne` hoặc `@OneToMany`, khi một entity con **được sở hữu về mặt vòng đời** và không còn thuộc quan hệ cha. JPA có thể đánh dấu entity con để xóa khi nó bị loại khỏi association.

Ví dụ: dòng đơn hàng thường không có ý nghĩa tồn tại độc lập nếu bị loại khỏi đơn.

```text
PurchaseOrder #42
   |--- OrderLine #1 (Keyboard)
   |--- OrderLine #2 (Mouse)
   |--- OrderLine #3 (Monitor)

removeLine(#2) + orphanRemoval=true

PurchaseOrder #42
   |--- OrderLine #1 (Keyboard)
   |--- OrderLine #3 (Monitor)

Database: xóa hàng OrderLine #2, giữ nguyên PurchaseOrder #42.
```

**Orphan removal liên kết hai khái niệm:** thao tác khởi đầu là *gỡ phần tử khỏi quan hệ*, nhưng JPA áp dụng thêm *thao tác xóa vòng đời của phần tử con*.

### 6.2. Mapping điển hình

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.setOrder(null);
        }
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
```

Ví dụ sử dụng các import JPA và `java.util.*` phù hợp. Quan hệ cha quản lý vòng đời dòng hàng. Khi order và line đang managed, sau lời gọi:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
OrderLine toRemove = order.getLines().get(0);

order.removeLine(toRemove);
```

JPA xử lý orphan theo mapping trong lúc flush, thường sinh `DELETE FROM order_lines WHERE id = ...`. Order không bị xóa. `line.setOrder(null)` trong helper giữ object graph nhất quán; đối với trường hợp orphan removal, JPA thực hiện **DELETE dòng con** thay vì một UPDATE giữ hàng con mồ côi với FK null.

### 6.3. Không có `orphanRemoval` thì sao?

Nếu mapping là:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
```

và chỉ gọi:

```java
order.getLines().remove(line);
```

thì thay đổi inverse collection **không mặc nhiên xóa line** hoặc cập nhật FK. Nếu thiết lập owning side:

```java
line.setOrder(null);
```

JPA có thể cố cập nhật `order_id = NULL`. Nhưng nếu schema đặt `order_id NOT NULL`, transaction sẽ gặp lỗi constraint. Khi nghiệp vụ cần xóa line, phải **gọi `em.remove(line)`** hoặc cấu hình `orphanRemoval` theo đúng mô hình vòng đời.

### 6.4. Đừng hiểu orphanRemoval như một cách “chuyển chủ”

Với entity con thật sự bị ràng buộc vòng đời vào cha, gỡ nó khỏi cha cũ rồi thêm vào cha mới trong cùng một lần flush có thể làm provider đánh dấu nó là orphan cần xóa. Đặc tả JPA không khuyến khích việc **chuyển một orphan sang quan hệ khác**, nên không được dựa vào chuyện “remove rồi add vào cha khác” để chắc chắn chỉ phát sinh UPDATE FK.

Nếu nghiệp vụ cho phép **chuyển một line/task/address từ owner A sang B và vẫn giữ nguyên entity**, mô hình orphan removal có thể không phù hợp. Có thể chọn association không có orphanRemoval và cập nhật owning side, hoặc thiết kế một thao tác chuyển chủ có kiểm soát đúng theo mapping/provider và constraint thực tế.

## 7. So sánh `orphanRemoval` với `CascadeType.REMOVE`

Hai cơ chế có kết quả SQL xóa con tương tự trong một số tình huống, nhưng **trigger khác nhau**.

| Tình huống | `orphanRemoval=true` | `cascade=REMOVE` |
|---|---|---|
| Gỡ một con khỏi collection của cha đang managed | Có thể xóa con khi relationship bị phá | Không tự xóa con chỉ vì gỡ collection |
| Gọi `em.remove(parent)` | Entity con thuộc quan hệ sẽ được xử lý xóa theo semantics orphan removal | Lan truyền thao tác remove từ parent sang con |
| Giữ parent, chỉ xóa một child thuộc quyền sở hữu | Phù hợp | Thường cần `em.remove(child)` nếu không có orphanRemoval |
| Xóa cả aggregate cha–con | Thường phù hợp với owned children | Phù hợp nếu cha có trách nhiệm vòng đời của con |
| Dùng trên `@ManyToMany` | Không hỗ trợ | REMOVE có thể lan sang entity chia sẻ, thường không mong muốn |
| Dùng khi con có thể thuộc nhiều cha độc lập | Thường không phù hợp | REMOVE cũng thường không phù hợp |

Ví dụ mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.REMOVE},
    orphanRemoval = false
)
private List<OrderLine> lines;
```

Khi `order.getLines().remove(line)`, chỉ thao tác trên collection không dẫn tới xóa con bởi `REMOVE` cascade. Nhưng khi `em.remove(order)`, thao tác remove được lan truyền đến những line liên quan.

Với:

```java
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderLine> lines;
```

gỡ line khỏi order đang managed có thể xóa line dù không khai báo `cascade=REMOVE`. Các loại cascade khác như `PERSIST` hoặc `MERGE` có trách nhiệm riêng; `orphanRemoval` không thay thế mọi cascade.

**Câu nhớ ngắn:** `cascade=REMOVE` phản ứng với **lệnh xóa cha**; `orphanRemoval` phản ứng với **việc con bị rời khỏi quan hệ sở hữu vòng đời** (và cũng ảnh hưởng khi cha bị xóa theo semantics JPA).

## 8. Ba thao tác trên Order và Line: SQL và kết quả khác nhau

Xét schema:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ordered_at TIMESTAMP NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL
);
```

### Trường hợp A — Thêm line mới vào order

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);
OrderLine line = new OrderLine("MOUSE", 2);
order.addLine(line);
```

Nếu association có `cascade=PERSIST` hoặc `ALL` và entity cha managed, provider có thể quản lý line mới theo cascade khi flush; cũng có thể gọi `em.persist(line)` tường minh theo yêu cầu use case.

SQL logic thường là:

```sql
INSERT INTO order_lines(order_id, sku, quantity)
VALUES (42, 'MOUSE', 2);
```

**Có một entity line mới được tạo và được liên kết với order.** Đây là thay đổi vòng đời (new → managed) **kèm** thiết lập liên kết.

### Trường hợp B — Đổi số lượng trên line

```java
OrderLine line = em.find(OrderLine.class, lineId);
line.changeQuantity(3);
```

Với method thay đổi số lượng hợp lệ, SQL logic:

```sql
UPDATE order_lines
SET quantity = 3
WHERE id = ?;
```

Entity còn tồn tại, order không đổi, quan hệ không đổi. Đây là **thay đổi thuộc tính**, một chiều thay đổi khác cần tách khỏi quan hệ và vòng đời.

### Trường hợp C — Gỡ line khỏi order

Nếu dùng `orphanRemoval=true`:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);
order.removeLine(line);
```

JPA có thể xóa:

```sql
DELETE FROM order_lines
WHERE id = ?;
```

Nếu không có orphan removal và `order_id` nullable:

```sql
UPDATE order_lines
SET order_id = NULL
WHERE id = ?;
```

Nếu không có orphan removal nhưng FK bắt buộc non-null, thao tác gỡ sẽ không tạo một trạng thái database hợp lệ. Phải chọn **xóa line**, **chuyển sang order khác**, hoặc thay đổi domain/schema để cho phép line không có order. Không thể xử lý đúng chỉ bằng cách xóa một phần tử khỏi list Java.

## 9. `@ManyToMany`: xóa hàng join table, giữ entity đầu cuối

Một ví dụ quản lý khóa học và sinh viên:

```java
@Entity
@Table(name = "students")
public class Student {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    protected Student() {}

    public Set<Course> getCourses() {
        return courses;
    }

    public void enroll(Course course) {
        courses.add(course);
    }

    public void withdraw(Course course) {
        courses.remove(course);
    }
}
```

```java
@Entity
@Table(name = "courses")
public class Course {

    @Id
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();

    protected Course() {}
}
```

`Student.courses` là owning side vì có `@JoinTable`. Khi đang managed:

```java
Student student = em.find(Student.class, 5L);
Course course = em.find(Course.class, 9L);
student.withdraw(course);
```

JPA có thể xóa một liên kết trong `student_courses`. **Không có thao tác `em.remove(course)`**, nên course vẫn tồn tại và sinh viên khác vẫn có thể học.

Sơ đồ:

```text
students           student_courses            courses
id = 5 ---------- student_id=5  course_id=9 -- id = 9
                       |
                       +-- withdraw --> DELETE join row

students(id=5) và courses(id=9): vẫn còn.
```

Đối với quan hệ hai chiều, nên đồng bộ cả collection inverse để tránh object graph bất nhất. Tuy nhiên, cùng nguyên tắc owning side, collection `Course.students` là inverse và không trực tiếp quyết định bảng nối.

### Vì sao `CascadeType.REMOVE` thường sai trên many-to-many?

`Course` là một thực thể độc lập được chia sẻ bởi nhiều `Student`. Nếu dùng `cascade=REMOVE` từ student tới courses, xóa một sinh viên có nguy cơ yêu cầu xóa các course đó, dẫn tới lỗi khóa ngoại hoặc mất dữ liệu. Đa số mô hình enrollment chỉ cần xóa các liên kết join table.

Nếu quan hệ đăng ký có thuộc tính riêng như `enrolledAt`, `grade`, `status` hoặc `fee`, cân nhắc ánh xạ **Enrollment** thành entity riêng thay vì `@ManyToMany` trực tiếp. Khi ấy việc rút khỏi khóa học có thể xóa một **Enrollment entity**, nhưng không xóa Student hoặc Course.

## 10. `@OneToOne`: gỡ quan hệ có thể xóa đối tượng phụ thuộc

Giả sử `User` có `UserProfile` riêng, và profile không có ý nghĩa nếu user không còn dùng nó:

```java
@Entity
public class UserAccount {

    @Id
    private Long id;

    @OneToOne(
        mappedBy = "user",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private UserProfile profile;

    public void attachProfile(UserProfile next) {
        if (profile == next) return;

        if (profile != null) {
            profile.setUser(null);
        }
        profile = next;
        if (next != null) {
            next.setUser(this);
        }
    }
}
```

```java
@Entity
public class UserProfile {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", unique = true)
    private UserAccount user;

    void setUser(UserAccount user) {
        this.user = user;
    }
}
```

Nếu profile đang managed và được gỡ khỏi `UserAccount.profile`, `orphanRemoval=true` có thể làm JPA xóa bản ghi profile. UserAccount vẫn còn.

Nhưng nếu `UserProfile` có thể chuyển sang một user khác hoặc được chia sẻ/giữ lại độc lập, không nên mặc định orphan removal. Nếu cần thay profile mới, thao tác xóa profile cũ và thêm profile mới có thể liên quan ràng buộc `UNIQUE(user_id)`, thứ tự SQL và việc flush. Mô hình domain phải xác định **profile là một phần phụ thuộc vòng đời hay entity độc lập**.

## 11. Thứ tự thực thi SQL, flush và ràng buộc database

JPA thường **hoãn SQL** cho đến thời điểm flush; nó có thể sắp xếp INSERT, UPDATE, DELETE theo khả năng và nhu cầu của provider. Vì vậy, thay đổi Java object graph không đồng nghĩa một câu SQL ngay lập tức đã chạy.

### 11.1. Gỡ liên kết hợp lệ hay không do constraint quyết định

Ví dụ `order_lines.order_id NOT NULL` không chấp nhận “dòng đơn không có đơn”:

```sql
UPDATE order_lines
SET order_id = NULL
WHERE id = 11;
-- Sẽ vi phạm NOT NULL nếu dòng tồn tại.
```

Với orphan removal, hành vi phù hợp hơn là xóa line. Nhưng JPA phải có metadata và trạng thái entity tương ứng để hiểu ý định đó. **Không được giả định database sẽ tự xóa line khi FK được đặt null**.

### 11.2. Foreign key có thể từ chối xóa entity cha

Nếu cố:

```java
Customer customer = em.find(Customer.class, 1L);
em.remove(customer);
```

trong khi vẫn có `PurchaseOrder` tham chiếu tới customer, database có thể từ chối `DELETE FROM customers ...` vì ràng buộc FK. Đó là dấu hiệu quan hệ vẫn tồn tại, không phải lý do để mặc định thêm `CascadeType.REMOVE` xóa mọi order.

Các lựa chọn nghiệp vụ rõ ràng hơn: không cho xóa customer khi còn order; anonymize thông tin cá nhân nhưng giữ bản ghi tham chiếu; chuyển order sang một owner hợp lệ; hoặc thiết kế cách lưu lịch sử đơn hàng phù hợp.

### 11.3. Delete cascade của database khác cascade của JPA

Database có thể định nghĩa:

```sql
FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
ON DELETE CASCADE
```

Khi xóa hàng `purchase_orders` bằng SQL, database tự xóa các hàng con liên quan. Đây là **referential action của database**, khác với `cascade=CascadeType.REMOVE` của JPA:

| Cơ chế | Tầng thực thi | Có đi qua lifecycle callback/entity listener? | Tác động tới persistence context |
|---|---|---|---|
| JPA `CascadeType.REMOVE` | ORM/persistence context | Thao tác remove JPA trên entity đích có thể kích hoạt callback theo lifecycle | Provider theo dõi các entity liên quan theo cơ chế ORM |
| SQL `ON DELETE CASCADE` | Database | Không chạy các callback JPA của entity con bị database xóa | ORM có thể không biết từng hàng con đã bị xóa |
| JPQL bulk `DELETE` | Trực tiếp trên database qua query | Không áp dụng vòng đời remove của từng entity như `em.remove` | Các entity đang managed có thể bị stale |

Nếu dự án kết hợp DB cascade và JPA cascade, cần hiểu thứ tự thực thi và tránh giữ stale entity trong context. Không dùng một cơ chế thay cho cơ chế kia chỉ vì cả hai cùng có chữ “cascade”.

### 11.4. Transaction quyết định kết quả cuối cùng

```text
begin transaction
   |
   |  order.setCustomer(nextCustomer)
   |  order.removeLine(line)       // Có orphanRemoval
   v
flush:
   UPDATE purchase_orders ...
   DELETE FROM order_lines ...
   |
   +--- rollback ---> cả hai thay đổi bị hủy trong DB
   |
   +--- commit ----> thay đổi được xác nhận
```

Nếu transaction rollback, object Java trong bộ nhớ không tự quay về trạng thái trước thao tác theo cách có thể tin cậy. Thông thường nên bỏ persistence context/session liên quan và tải lại trạng thái khi cần.

## 12. Detached graph, `merge` và rủi ro cập nhật liên kết ngoài ý muốn

Một ví dụ dễ gặp là API nhận entity từ client hoặc giữ entity qua nhiều request:

```java
PurchaseOrder detached = ...; // Đối tượng đã tách context
detached.setCustomer(otherCustomer);

PurchaseOrder managed = em.merge(detached);
```

`merge` sao chép trạng thái của detached object sang managed instance. Nếu relationship được merge theo metadata và cascade phù hợp, thao tác có thể làm thay đổi FK. Tuy nhiên, object truyền vào `merge` **không trở thành managed**, và việc thiếu/tải chưa đầy đủ association trong detached graph có thể khiến cách đọc trạng thái phức tạp.

### 12.1. Đừng nhầm “client không gửi field” với “xóa association”

Một payload JSON không có `customerId` có thể chỉ có nghĩa “không cập nhật customer”, nhưng nếu biến payload thành entity detached có field `customer = null` rồi merge, ứng dụng có nguy cơ diễn giải thành “gỡ customer”.

Thay vì merge object graph không kiểm soát, với thao tác đổi liên kết nên xử lý rõ tại service:

```java
@Transactional
public void reassignOrder(Long orderId, Long nextCustomerId) {
    PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

    Customer next = customerRepository.findById(nextCustomerId)
        .orElseThrow();

    order.setCustomer(next);
}
```

Đây là ví dụ Spring với `@Transactional` và repository tương ứng; logic lõi vẫn áp dụng với EntityManager thuần. Service **tải managed entity hiện có**, kiểm tra target, rồi đổi đúng association được phép.

### 12.2. Khi nào dùng cascade MERGE?

`cascade=MERGE` hợp lý khi aggregate thực sự sở hữu graph con và cần sao chép thay đổi từ một graph detached có phạm vi rõ. Không nên tự động cascade merge qua mọi relation, đặc biệt với entity dùng chung như Customer, Country, Category. Cập nhật một Order không nên vô tình ghi đè dữ liệu Customer chỉ vì DTO chứa object Customer cũ.

Có thể tách thao tác nghiệp vụ thành command/DTO như `ChangeOrderCustomer(orderId, customerId)`. Khi đó mã làm rõ ý định: **đổi liên kết**, không “thay toàn bộ trạng thái entity”.

## 13. Những tình huống không thể giải quyết chỉ bằng sửa collection

### 13.1. Collection là ảnh nhìn của quan hệ, không nhất thiết là nguồn ghi

Với `@OneToMany(mappedBy="customer")`, thêm/xóa phần tử trong collection chưa chắc thay FK nếu owning side không được cập nhật. Đó là lý do cần helper và quy ước ở domain model.

### 13.2. Collection đang lazy

Gọi `order.getLines().remove(line)` có thể tải collection, tùy provider và loại collection. Trong hệ thống có hàng chục nghìn line, thao tác này có thể gây chi phí không cần thiết.

Nếu nghiệp vụ “xóa line theo ID” có tần suất lớn, service có thể tải đúng line và kiểm tra nó thuộc order trước khi xóa, thay vì tải cả collection:

```java
OrderLine line = em.find(OrderLine.class, lineId);

if (line == null || !line.getOrder().getId().equals(orderId)) {
    throw new IllegalArgumentException("Line không thuộc order");
}
em.remove(line);
```

Ở đây mục tiêu là **xóa entity line**, nên `em.remove(line)` truyền đạt ý định rõ. Nếu muốn chỉ chuyển line sang order khác, phải cập nhật owning association và bảo đảm mapping không tự xóa orphan.

### 13.3. Collection dùng `Set` cần equality ổn định

Với `Set<OrderLine>`, `remove(line)` dựa trên `equals`/`hashCode`. Nếu hash của entity thay đổi sau khi được sinh ID, collection có thể không tìm lại được phần tử, và việc gỡ association sẽ không diễn ra như dự kiến.

Vì vậy, khi dùng entity trong `HashSet`, cần lựa chọn quy tắc equality/hash theo vòng đời định danh hoặc dùng cấu trúc/logic phù hợp. Không nên chẩn đoán nhầm đây là “JPA không xóa quan hệ” khi thực tế lệnh `Set.remove` đã thất bại ở Java.

### 13.4. Bulk query bỏ qua thao tác vòng đời thông thường

Ví dụ:

```java
em.createQuery(
    "delete from OrderLine l where l.order.id = :orderId"
)
.setParameter("orderId", orderId)
.executeUpdate();
```

Đây là **JPQL bulk delete**, không tương đương vòng đời của hàng loạt lần `em.remove(line)`:

- Không chạy cascade REMOVE/orphanRemoval cho từng managed entity theo cách thông thường.
- Các entity đã nạp trong persistence context có thể giữ trạng thái cũ.
- Lifecycle callback của từng entity không được áp dụng như khi gọi `remove` từng instance.
- Database constraints vẫn có hiệu lực.

Nó có thể phù hợp cho thao tác batch nếu được thiết kế có chủ đích, nhưng cần giải quyết stale state và ràng buộc, thường bằng cách thực hiện trong một transaction riêng hoặc clear/refresh context theo nhu cầu.

## 14. Ví dụ nghiệp vụ: “xóa khỏi danh sách” có thể mang ba ý nghĩa

Giả sử giao diện người dùng có nút **Remove** bên cạnh một item. Từ “Remove” không xác định đủ thao tác persistence.

| Màn hình | Ý nghĩa nghiệp vụ | Tác động dữ liệu hợp lý |
|---|---|---|
| Xóa khóa học khỏi danh sách đăng ký của student | Student không còn tham gia course | Xóa hàng trong bảng nối/Enrollment; giữ Student và Course |
| Xóa sản phẩm khỏi một giỏ hàng | Giỏ hàng không còn dòng sản phẩm đó | Xóa CartItem hoặc gỡ liên kết tùy mô hình; không xóa Product |
| Xóa dòng trong đơn hàng nháp | Dòng hàng không còn tồn tại độc lập | `orphanRemoval` hoặc `em.remove(OrderLine)` |
| Bỏ người phụ trách khỏi task | Task vẫn tồn tại, chưa có assignee | Đặt FK `assignee_id = NULL` nếu schema cho phép |
| Chuyển task sang người phụ trách khác | Liên kết Task → Employee thay đổi | UPDATE FK; không xóa Employee cũ |
| Xóa danh mục sản phẩm | Cần chính sách với các sản phẩm đang dùng danh mục | Từ chối, chuyển danh mục, hoặc xử lý theo domain; không cascade xóa tùy tiện |
| Xóa tài khoản và profile riêng tư | Cả hai thuộc cùng vòng đời | Xóa Account, có thể cascade REMOVE profile |
| Gỡ avatar riêng của tài khoản | Có thể xóa file/metadata avatar riêng | Xóa entity avatar nếu ownership độc quyền; xử lý file ngoài DB riêng |

Trước khi thêm `cascade` hoặc `orphanRemoval`, hãy trả lời: **đối tượng bị gỡ có cần tiếp tục tồn tại ở nơi khác không?** Nếu câu trả lời là “có”, không nên tự động xóa entity đó khi liên kết biến mất.

## 15. Thiết kế aggregate và quyền sở hữu vòng đời

Một gợi ý hữu ích là phân biệt **quan hệ tham chiếu** với **quan hệ sở hữu vòng đời**:

- **Tham chiếu:** `Order → Customer`, `Booking → Venue`, `Product → Category`. Entity được tham chiếu có vòng đời độc lập; chỉ thay đổi liên kết thường không được làm thay đổi sự tồn tại của entity đó.
- **Sở hữu vòng đời:** `Order → OrderLine`, `Account → PrivateProfile` khi line/profile không tồn tại độc lập. Tạo/xóa cha hoặc gỡ con có thể quản lý vòng đời con bằng cascade/orphanRemoval.

Không phải mọi `@OneToMany` đều là ownership vòng đời, và không phải mọi `@OneToOne` đều là quan hệ phụ thuộc. **Cardinality (một–nhiều, một–một) không quyết định quyền xóa**. Đây là quyết định miền dữ liệu.

Ví dụ, `Department → Employee` có thể là quan hệ một-nhiều, nhưng giải thể Department không được tự xóa mọi Employee. Ngược lại, `PurchaseOrder → OrderLine` cũng là một-nhiều nhưng các OrderLine thường có vòng đời gắn với Order.

Mục tiêu của mapping là phản ánh quy tắc này, không dùng một công thức `cascade=ALL, orphanRemoval=true` cho mọi collection.

## 16. Đảm bảo đồng thời và nhất quán

### 16.1. Hai transaction cùng thay liên kết

Nếu transaction A chuyển Order sang Customer 2 trong khi transaction B chuyển cùng Order sang Customer 3, kết quả có thể là **last write wins** nếu không có kiểm soát đồng thời. JPA không tự phát hiện mọi xung đột chỉ vì association là quan hệ.

Có thể dùng `@Version` ở Order:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

Khi update được ORM kiểm soát và phiên bản được kiểm tra, một transaction có thể thất bại với optimistic-lock exception nếu phiên bản đã đổi. Ứng dụng cần quyết định báo xung đột, tải lại hay retry theo nghiệp vụ. Cần nhớ rằng hành vi tăng version khi chỉ sửa collection/bảng nối có thể phụ thuộc mapping và provider; không mặc định mọi liên kết sẽ làm tăng version của mọi entity liên quan.

### 16.2. Ràng buộc DB vẫn là tuyến bảo vệ cuối

Một association có thể đặt `optional = false` trong Java, nhưng dữ liệu phải được bảo vệ bằng `NOT NULL` và `FOREIGN KEY` thực trong database. Hai transaction cạnh tranh khi xóa target và tạo association có thể gặp FK violations. Thiết kế transaction, isolation, locking và lỗi phản hồi vẫn cần được xử lý.

### 16.3. Không để vòng đời database khác vòng đời domain mà không có thiết kế

Nếu dùng `ON DELETE CASCADE` để database tự xóa children, ORM có thể chưa cập nhật mọi managed instance ngay lập tức. Khi dùng event, audit hoặc lifecycle callback của JPA, cần quyết định rõ sự khác biệt này. Với hệ thống có domain event gửi ra ngoài, transaction database và cơ chế outbox/idempotency cũng quan trọng; `cascade` của JPA **không phải** một cơ chế điều phối xóa dữ liệu qua nhiều dịch vụ.

## 17. Checklist suy luận khi sửa quan hệ

Với một thao tác cụ thể, có thể đi theo trình tự sau:

1. **Định danh thao tác:** tạo entity mới, sửa thuộc tính, đổi liên kết, gỡ liên kết hay xóa entity?
2. **Xác định biểu diễn database:** FK nằm ở bảng nào? Hay có join table? Bảng nào tương ứng với chính entity?
3. **Xác định owning side:** field nào điều khiển FK/join table? Có `mappedBy` không?
4. **Xác định vòng đời:** entity đích độc lập hay chỉ tồn tại cùng cha? Có nên bị xóa khi gỡ không?
5. **Kiểm tra cascade:** thao tác `PERSIST/MERGE/REMOVE` nào cần lan truyền? Có đang lan sang entity chia sẻ không?
6. **Kiểm tra orphan removal:** gỡ collection có phải thật sự là ý định xóa child? Có nhu cầu chuyển child sang parent khác không?
7. **Kiểm tra DB constraints:** FK có nullable không, có unique, ON DELETE action, khóa ngoài và transaction phù hợp không?
8. **Kiểm tra object graph:** hai phía quan hệ hai chiều có được đồng bộ trong Java không? Có Set equality, lazy loading hoặc detached state không?
9. **Xác định SQL mong đợi:** UPDATE FK, INSERT/DELETE join row, INSERT entity hay DELETE entity?
10. **Quan sát tại flush/commit:** SQL và lỗi constraint chỉ có ý nghĩa cuối cùng khi transaction được xử lý; rollback phải được tính đến.

Ví dụ, yêu cầu “chuyển đơn hàng sang khách hàng khác” dẫn tới **UPDATE FK** trên owning `Order.customer`, không cần `CascadeType.REMOVE`. Yêu cầu “xóa một dòng khỏi đơn nháp” dẫn tới **DELETE OrderLine** nếu domain định nghĩa line phụ thuộc vòng đời vào order, thích hợp với `orphanRemoval` hoặc `remove` tường minh.

## 18. Bài thực hành có hướng dẫn

### Bài 1 — Chuyển khách hàng của đơn hàng

Tạo ba entity: `Customer(1)`, `Customer(2)` và `PurchaseOrder(10)` đang tham chiếu `Customer(1)`. Sử dụng quan hệ `@ManyToOne` và `@OneToMany(mappedBy="customer")`.

Lần lượt thực hiện:

1. Chỉ gọi `customer2.getOrders().add(order)`.
2. Tải lại database để quan sát `orders.customer_id`.
3. Khôi phục trạng thái, rồi gọi `order.setCustomer(customer2)` ở owning side.
4. Theo dõi SQL UPDATE của order và bảo đảm hai customer vẫn tồn tại.

Tự giải thích: tại sao sửa inverse collection không đủ để đổi FK?

### Bài 2 — Gỡ dòng đơn hàng có và không có orphan removal

Tạo `PurchaseOrder(42)` với hai `OrderLine` và cột `order_lines.order_id NOT NULL`.

- Bước A: bỏ `orphanRemoval`, gỡ line khỏi collection và đặt `line.order = null`. Quan sát ràng buộc FK.
- Bước B: bật `orphanRemoval=true`, gỡ line bằng helper đồng bộ hai phía. Theo dõi `DELETE` của line.
- Bước C: giữ line, đổi `quantity`. Quan sát `UPDATE quantity`; không có thay đổi quan hệ.

Xác định ba thao tác tương ứng với **liên kết**, **vòng đời** và **thuộc tính** thế nào.

### Bài 3 — Đăng ký khóa học nhiều-nhiều

Tạo `Student`, `Course` và `student_courses`. Đăng ký sinh viên vào hai khóa học; rút khỏi một khóa học; sau đó xóa sinh viên.

Kiểm tra: khi xóa một row của `student_courses`, Course có bị xóa không? Điều gì nguy hiểm nếu thêm `cascade=REMOVE` từ Student tới Course?

### Bài 4 — Cascading persist không tự thiết lập owning side

Tạo một `OrderLine` mới và chỉ thêm nó vào `order.lines` khi `mappedBy="order"`. Gọi `persist(order)` với cascade `PERSIST`. Quan sát kết quả hoặc lỗi khi `order_id` không null.

Sau đó thiết lập `line.setOrder(order)` trong helper và lặp lại. Giải thích vai trò khác nhau của cascade và owning side.

### Bài 5 — Detached object từ API

Giả sử API PATCH gửi:

```json
{
  "orderId": 10,
  "total": 280000
}
```

Payload không chứa `customerId`. So sánh hai cách xử lý:

- Biến payload thành detached `Order` với `customer == null` rồi `merge` toàn bộ.
- Tải managed `Order`, chỉ cập nhật `total` theo command của API.

Phân tích rủi ro cách thứ nhất làm mất association ngoài ý muốn.

### Bài 6 — Bulk delete và managed state

Trong cùng persistence context, nạp ba dòng đơn hàng rồi chạy bulk JPQL:

```java
em.createQuery(
    "delete from OrderLine l where l.order.id = :orderId"
)
.setParameter("orderId", orderId)
.executeUpdate();
```

Sau đó thử đọc lại các object đã managed. Giải thích vì sao chúng có thể stale, và vì sao bulk delete khác gọi `em.remove` từng entity.

## 19. Những nhận định dễ nhầm

| Nhận định | Cách hiểu đúng hơn |
|---|---|
| “Xóa phần tử khỏi `@OneToMany` là xóa entity.” | Chỉ khi mapping và thao tác cho phép xóa vòng đời, ví dụ orphanRemoval; inverse side đơn thuần có thể không ghi FK. |
| “`cascade=ALL` là cấu hình nên dùng mặc định.” | Nó lan truyền cả REMOVE và các thao tác khác; nguy hiểm với entity dùng chung. |
| “`mappedBy` nghĩa là phía đó nắm quyền quản lý FK.” | `mappedBy` đánh dấu phía inverse, trỏ tới field sở hữu quan hệ ở phía kia. |
| “Đổi association chắc chắn gọi INSERT/DELETE entity.” | Nhiều trường hợp chỉ UPDATE FK hoặc INSERT/DELETE hàng join table. |
| “`orphanRemoval` chỉ xóa khi xóa cả cha.” | Nó có thể xóa child ngay khi child bị gỡ khỏi association sở hữu vòng đời. |
| “`cascade=REMOVE` khiến gỡ một item khỏi list sẽ xóa nó.” | Cascade REMOVE phản ứng với thao tác remove entity nguồn, không tự động mọi thay đổi collection. |
| “Xóa student trong many-to-many thì cần xóa course.” | Phần lớn trường hợp chỉ xóa các hàng liên kết, course là entity độc lập. |
| “`em.detach` là xóa liên kết của entity.” | Detach thay đổi trạng thái theo dõi trong persistence context, không đổi FK. |
| “JPA cascade giống `ON DELETE CASCADE`.” | Một cơ chế thuộc ORM lifecycle; một cơ chế do database thực thi. |
| “`flush` là commit.” | Flush gửi SQL trong transaction, kết quả vẫn có thể rollback. |
| “`merge` chỉ cập nhật scalar field.” | Merge có thể ảnh hưởng association và graph theo mapping; cần kiểm soát dữ liệu detached. |
| “Nếu code Java đổi list thì chắc chắn DB sẽ theo.” | Phải xem owning side, state, transaction và constraints. |

## 20. Ghi nhớ cốt lõi

Trong JPA, **thay đổi liên kết** là thay đổi quan hệ giữa các entity, thường biểu diễn bằng **UPDATE khóa ngoại** hoặc **INSERT/DELETE hàng join table**. **Thay đổi vòng đời entity** là tạo, quản lý, tách hoặc xóa một entity, thường được thể hiện bằng `persist`, `remove`, `detach`, `merge` và các cơ chế liên quan.

Khi hai thao tác kết hợp, hãy phân biệt nguyên nhân: `cascade` lan truyền các **thao tác vòng đời**; `orphanRemoval` có thể biến việc **gỡ một liên kết sở hữu vòng đời** thành thao tác **xóa entity con**; `mappedBy` chỉ ra phía inverse, còn owning side điều khiển **ghi quan hệ**. Cuối cùng, database vẫn thực thi PRIMARY KEY, FOREIGN KEY, NOT NULL, UNIQUE và các referential action.

Thiết kế đúng bắt đầu từ câu hỏi nghiệp vụ: **“Đối tượng này chỉ không còn liên hệ với đối tượng kia, hay nó thực sự không còn được phép tồn tại?”** Câu trả lời quyết định nên cập nhật association, xóa một join row, gọi `remove` hay dùng `orphanRemoval`—và giúp tránh xóa nhầm dữ liệu hoặc tạo ra liên kết không nhất quán.
