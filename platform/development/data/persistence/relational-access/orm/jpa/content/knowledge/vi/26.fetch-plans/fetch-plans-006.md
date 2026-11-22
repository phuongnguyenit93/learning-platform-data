# Nhận diện N+1 từ hành vi truy cập đồ thị đối tượng trong JPA

## 1. Từ một truy vấn đơn giản tới hàng trăm truy vấn không nhìn thấy trong repository

Khi sử dụng JPA, code Java thường làm việc với **đồ thị đối tượng** (*object graph*) thay vì các bảng và khóa ngoại. Một entity tham chiếu entity khác qua `@ManyToOne`, `@OneToOne` hoặc tham chiếu tập entity qua `@OneToMany`, `@ManyToMany`.

Ví dụ:

```text
PurchaseOrder
   |
   +-- customer ------------------> Customer
   |
   +-- lines ---------------------> List<OrderLine>
                                         |
                                         +-- product --> Product
```

Một truy vấn rất gọn:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o ORDER BY o.id",
    PurchaseOrder.class
).getResultList();
```

Nhưng phía sau repository, service tạo response như sau:

```java
for (PurchaseOrder order : orders) {
    System.out.println("Đơn: " + order.getId());

    for (OrderLine line : order.getLines()) {
        System.out.println(
            line.getProduct().getName()
        );
    }
}
```

Nếu `lines` và `product` đang được tải LAZY, mỗi lần đi qua một cạnh chưa được khởi tạo của đồ thị có thể dẫn tới một truy vấn SQL bổ sung.

Với 100 đơn, repository có thể chỉ chạy **1 SELECT** để lấy đơn hàng nhưng vòng lặp có thể khiến hệ thống thực thi hàng trăm SELECT khác. Đây là hiện tượng thường được gọi là **N+1 query problem**.

Điểm cốt lõi của bài học:

> **N+1 không nằm riêng trong câu JPQL ban đầu. Nó xuất hiện từ sự phối hợp giữa fetch plan, trạng thái các object đã được nạp và đường đi mà code thực sự truy cập trên đồ thị đối tượng.**

Muốn nhận diện N+1 hiệu quả, cần biết **tại dòng code nào** một thuộc tính LAZY được đọc, **trong vòng lặp nào** nó được đọc, **những SQL nào** phát sinh theo từng entity, và **bao nhiêu identity/collection thật sự chưa được tải**.

---

## 2. Khái niệm N+1: một truy vấn lấy N root, nhiều truy vấn lấy dữ liệu liên quan

Một mô hình phổ biến:

```text
Repository:
    SELECT các PurchaseOrder                -> 1 query

Service:
    for (mỗi PurchaseOrder):
        order.getLines()                    -> ~N queries

Tổng: 1 + N
```

Với N = 5:

```sql
-- Q1: root query
SELECT id, status, customer_id, ordered_at
FROM purchase_orders
ORDER BY id;

-- Q2: truy cập order 101.lines
SELECT * FROM order_lines WHERE order_id = 101;

-- Q3: truy cập order 102.lines
SELECT * FROM order_lines WHERE order_id = 102;

-- Q4: truy cập order 103.lines
SELECT * FROM order_lines WHERE order_id = 103;

-- Q5: truy cập order 104.lines
SELECT * FROM order_lines WHERE order_id = 104;

-- Q6: truy cập order 105.lines
SELECT * FROM order_lines WHERE order_id = 105;
```

Tổng cộng **6 SELECT = 1 + 5**.

N+1 không có nghĩa “truy vấn thứ nhất luôn đi ngay trước N truy vấn còn lại”. Trên thực tế, chúng có thể bị ngăn cách bởi nhiều method calls, mapper, template, serializer hoặc logic nghiệp vụ.

### 2.1. Dấu hiệu định lượng

Nếu số root entities tăng, số SQL phát sinh cho một endpoint cũng tăng gần tuyến tính theo số root:

| Số đơn hàng N | Root queries | Secondary SELECTs (minh họa) | Tổng |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 5 | 1 | 5 | 6 |
| 20 | 1 | 20 | 21 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |

Bảng giả định: mỗi order có một collection LAZY chưa loaded; provider thực hiện một SELECT riêng cho mỗi collection, không batch, không cache hit và không có fetch plan khác. **Đó là kịch bản minh họa, không phải số SQL JPA bắt buộc tạo.**

### 2.2. Dấu hiệu trong code

Dạng dễ nghi ngờ nhất:

```java
List<Parent> parents = repository.findParents();

for (Parent parent : parents) {
    parent.getChildren().size();
}
```

Nhưng N+1 cũng có thể ẩn trong:

```java
return parents.stream()
    .map(mapper::toDto)
    .toList();
```

nếu `mapper.toDto` đọc `parent.getChildren()` hoặc `parent.getCustomer().getName()`.

### 2.3. Không phải cứ nhiều SQL là N+1

Một ứng dụng có thể cố ý chạy 5 truy vấn:

- Một query lấy orders.
- Một query lấy tổng tiền.
- Một query lấy tỷ lệ thanh toán.
- Một query lấy cấu hình.
- Một query lấy quyền truy cập.

Đây **không tự động** là N+1. N+1 đòi hỏi mối quan hệ nhân quả đặc trưng: **một tập root objects được tải, sau đó thao tác lặp lại trên các root/related objects gây thêm các SELECT tương tự, thường chỉ khác bind parameter (ID/FK)**.

Để chẩn đoán, phải nối **SQL pattern** với **đường truy cập object graph**.

---

## 3. N+1 là vấn đề về đồ thị đối tượng, không phải chỉ về `LAZY`

JPA hỗ trợ các kiểu fetch:

- `FetchType.LAZY`: cho phép trì hoãn nạp association/attribute cho đến khi cần, tùy mapping/provider.
- `FetchType.EAGER`: yêu cầu có dữ liệu theo eager fetch semantics, **không bảo đảm** sử dụng một SQL JOIN duy nhất.

Các mặc định thường gặp:

| Loại mapping | Giá trị fetch mặc định |
|---|---|
| `@ManyToOne` | `EAGER` |
| `@OneToOne` | `EAGER` |
| `@OneToMany` | `LAZY` |
| `@ManyToMany` | `LAZY` |
| `@ElementCollection` | `LAZY` |
| `@Basic` | `EAGER` |

**LAZY không có nghĩa chắc chắn gây N+1**, vì association có thể được query fetch sẵn hoặc lấy nhờ batch/cache.

**EAGER không có nghĩa miễn nhiễm N+1**, vì provider có thể tải association EAGER bằng những secondary SELECTs.

### 3.1. Hai yếu tố tạo N+1

```text
     Fetch plan không gộp/tối ưu các quan hệ cần dùng
                           +
       Code truy cập quan hệ trên nhiều root objects
                           |
                           v
                   N+1 query pattern
```

Một query lấy 100 orders rồi chỉ đọc `order.getId()` không nhất thiết gây N+1 trên `lines`. Chỉ khi code bắt đầu cần dữ liệu `lines` mà provider chưa nạp, SQL phụ có thể xuất hiện.

### 3.2. Thời điểm truy cập là một phần của chẩn đoán

```text
T0  Repository trả 100 PurchaseOrder
T1  Service lặp 100 orders và gọi getLines()
T2  Mapper lặp các lines và gọi getProduct()
T3  JSON serializer đọc customer.fullName
```

Mỗi mốc có thể làm tăng SQL count. Nếu chỉ xem truy vấn tại T0, bạn có thể không biết tại sao endpoint lại chậm.

---

## 4. Mô hình dữ liệu xuyên suốt bài học

Để quan sát chính xác đường truy cập, ta dùng mô hình bán hàng:

```text
customers
  id
  full_name

purchase_orders
  id
  customer_id  -> customers.id
  order_code
  status

order_lines
  id
  order_id     -> purchase_orders.id
  product_id   -> products.id
  quantity

products
  id
  name
  unit_price
```

Một order thuộc về một customer, mỗi order có nhiều order lines, mỗi line tham chiếu một product.

### 4.1. DDL minh họa

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    unit_price DECIMAL(15, 2) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_code VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id),
    CONSTRAINT fk_lines_product
        FOREIGN KEY (product_id)
        REFERENCES products(id)
);

CREATE INDEX ix_lines_order ON order_lines(order_id);
CREATE INDEX ix_lines_product ON order_lines(product_id);
CREATE INDEX ix_orders_customer ON purchase_orders(customer_id);
```

`GENERATED BY DEFAULT AS IDENTITY` là một cú pháp ví dụ; sản phẩm thực tế phải chọn migration phù hợp SQL dialect.

### 4.2. Dữ liệu mẫu

**Customers**

| ID | Tên |
|---:|---|
| 1 | An |
| 2 | Bình |
| 3 | Chi |

**Products**

| ID | Sản phẩm |
|---:|---|
| 10 | Keyboard |
| 20 | Mouse |
| 30 | Monitor |

**Orders**

| ID | Code | Customer | Status |
|---:|---|---:|---|
| 101 | SO-101 | 1 | NEW |
| 102 | SO-102 | 1 | PAID |
| 103 | SO-103 | 2 | NEW |
| 104 | SO-104 | 3 | PAID |
| 105 | SO-105 | 3 | NEW |

**Order lines**

| Line ID | Order ID | Product ID | Quantity |
|---:|---:|---:|---:|
| 1001 | 101 | 10 | 1 |
| 1002 | 101 | 20 | 2 |
| 1003 | 102 | 20 | 1 |
| 1004 | 104 | 30 | 1 |
| 1005 | 105 | 10 | 1 |

Order#103 **không có dòng hàng**. Hai orders dùng chung Customer#1 hoặc Customer#3; nhiều lines dùng chung Product#10 hoặc Product#20.

Điều này giúp phân biệt:

- Truy vấn theo **mỗi collection parent**.
- Truy vấn theo **mỗi distinct to-one target identity**.
- Tác dụng của first-level cache khi related entities được dùng lại.

---

## 5. Các entity và fetch settings dùng để tái hiện N+1

### 5.1. `Customer`

```java
package com.example.nplusone;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {}

    public Customer(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("Tên rỗng");
        }
        this.fullName = fullName;
    }

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
}
```

### 5.2. `Product`

```java
package com.example.nplusone;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    @Column(name = "unit_price", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal unitPrice;

    protected Product() {}

    public Product(String name, BigDecimal unitPrice) {
        this.name = Objects.requireNonNull(name);
        this.unitPrice = Objects.requireNonNull(unitPrice);
        if (name.isBlank() || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Product không hợp lệ");
        }
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
```

### 5.3. `PurchaseOrder`

```java
package com.example.nplusone;

import jakarta.persistence.*;
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

    @Column(name = "order_code", nullable = false,
            unique = true, length = 40)
    private String code;

    @Column(name = "status", nullable = false, length = 20)
    private String status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        fetch = FetchType.LAZY
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
            String code,
            String status,
            Customer customer
    ) {
        this.code = Objects.requireNonNull(code);
        this.status = Objects.requireNonNull(status);
        this.customer = Objects.requireNonNull(customer);
    }

    public void addLine(Product product, int quantity) {
        lines.add(new OrderLine(this, product, quantity));
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getStatus() { return status; }
    public Customer getCustomer() { return customer; }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

### 5.4. `OrderLine`

```java
package com.example.nplusone;

import jakarta.persistence.*;
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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    OrderLine(
            PurchaseOrder order,
            Product product,
            int quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity phải > 0");
        }
        this.order = Objects.requireNonNull(order);
        this.product = Objects.requireNonNull(product);
        this.quantity = quantity;
    }

    public Long getId() { return id; }
    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
}
```

### 5.5. Vì sao đặt `LAZY` cho `@ManyToOne`?

`@ManyToOne` mặc định `EAGER` trong JPA. Trong ví dụ, ta đặt `LAZY` rõ ràng để minh họa lúc code thực sự cần customer và product.

Tuy nhiên, `LAZY` là hint và có thể phụ thuộc proxy/bytecode enhancement/provider. **Không được hiểu các SQL trace của bài là thứ tự SQL bắt buộc của mọi provider.** Mục tiêu là nhận ra pattern và tự kiểm chứng với stack thực tế.

### 5.6. Vì sao collection không tự chứa Product?

`PurchaseOrder.lines` chỉ nói “tôi cần các OrderLine objects”. Mỗi `OrderLine.product` là một cạnh khác của đồ thị.

```text
Order#101                       Product#10
   |                                ^
   +-- Line#1001 -------------------+
   |
   +-- Line#1002 ----------------------> Product#20
```

Nếu lines đã loaded, Products có thể vẫn chưa loaded. Đây là nguyên nhân **N+1 nhiều tầng**.

---

## 6. Nhận diện N+1 loại A: một-nhiều collection

Query:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    ORDER BY o.id
    """,
    PurchaseOrder.class
).getResultList();
```

Code tiếp theo:

```java
for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCode() + ": " + order.getLines().size()
    );
}
```

Khi các collections chưa được tải, provider có thể chạy:

```sql
-- Lúc getResultList():
SELECT id, order_code, status, customer_id
FROM purchase_orders
ORDER BY id;

-- Lúc đi qua vòng lặp:
SELECT ... FROM order_lines WHERE order_id = 101;
SELECT ... FROM order_lines WHERE order_id = 102;
SELECT ... FROM order_lines WHERE order_id = 103;
SELECT ... FROM order_lines WHERE order_id = 104;
SELECT ... FROM order_lines WHERE order_id = 105;
```

Dù Order#103 **không có line**, provider vẫn có thể cần truy vấn để biết collection rỗng nếu thông tin đó chưa có.

### 6.1. Truy cập lần đầu và lần sau

```java
int first = order.getLines().size();
int second = order.getLines().size();
```

Nếu lời gọi đầu đã khởi tạo collection, lời gọi sau thường dùng dữ liệu trong collection đang managed, không cần SELECT lại.

Tuy nhiên, một số providers có extension **extra-lazy**, cho phép `size()` thực hiện `COUNT(*)` mà không khởi tạo toàn bộ collection. Không đưa ra kết luận tuyệt đối rằng **“gọi size một lần là tất cả lines loaded”**.

### 6.2. Duyệt phần tử thường rõ hơn việc chỉ hỏi size

```java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        System.out.println(line.getQuantity());
    }
}
```

Đoạn này thật sự cần các phần tử OrderLine, nên trên collection chưa loaded thường khiến provider tải dữ liệu collection, trừ khi đã được fetch hoặc cache.

### 6.3. Dấu hiệu trên log SQL

```text
select ... from purchase_orders ...          -- 1 lần
select ... from order_lines where order_id=? -- nhiều lần
select ... from order_lines where order_id=?
select ... from order_lines where order_id=?
...
```

Truy vấn lặp có **cùng cấu trúc SQL** nhưng **bind parameter order_id khác nhau**.

Nếu log chỉ ghi `?` mà không ghi bind values, hãy dùng an toàn và vừa đủ logging trong dev/test để thấy sự khác biệt về ID. Không bật log chứa thông tin nhạy cảm vô hạn ở production.

---

## 7. Nhận diện N+1 loại B: nhiều-một/từng Customer

Một câu SELECT root:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

Vòng lặp:

```java
for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getFullName()
    );
}
```

Nếu customer association LAZY và chưa có trong persistence context, truy cập `getFullName()` có thể kích hoạt SELECT Customer.

### 7.1. 5 orders nhưng chỉ 3 distinct customers

Dữ liệu mẫu:

```text
Order#101 -> Customer#1
Order#102 -> Customer#1
Order#103 -> Customer#2
Order#104 -> Customer#3
Order#105 -> Customer#3
```

SQL khả dĩ:

```sql
SELECT ... FROM purchase_orders;

SELECT ... FROM customers WHERE id = 1;
SELECT ... FROM customers WHERE id = 2;
SELECT ... FROM customers WHERE id = 3;
```

Ở cùng persistence context, Customer#1 và Customer#3 có thể được tái sử dụng cho nhiều orders.

**Tổng ở ví dụ này là 1 + 3**, không phải 1 + 5.

Từ đó, một định nghĩa vận hành chính xác hơn:

> Với to-one LAZY, số secondary SELECTs thường gắn với số **related entity identities chưa loaded**, không nhất thiết bằng số root objects.

### 7.2. N+1 cũng có thể xảy ra với `EAGER`

Nếu đổi:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
```

provider phải đáp ứng eager load semantics, nhưng có thể dùng:

```sql
SELECT ... FROM purchase_orders;
SELECT ... FROM customers WHERE id = 1;
SELECT ... FROM customers WHERE id = 2;
SELECT ... FROM customers WHERE id = 3;
```

ngay khi root query được thực hiện, thay vì đợi getter.

**Đổi LAZY thành EAGER không đảm bảo hết N+1**; nó chỉ có thể chuyển thời điểm truy vấn sang lúc fetch root.

### 7.3. Quan sát thời gian log quan trọng

Nếu các secondary SELECTs xảy ra trước khi repository trả về, nguyên nhân có thể là EAGER fetch bằng secondary selects.

Nếu chúng xảy ra khi mapper gọi `getCustomer().getFullName()`, nguyên nhân có thể là to-one LAZY.

Cùng pattern “nhiều SELECT customers theo ID”, nhưng vị trí và giải pháp có thể khác.

---

## 8. Nhận diện N+1 loại C: truy cập đồ thị hai hoặc ba tầng

Xét:

```java
List<PurchaseOrder> orders = repository.findRecentOrders();

for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        System.out.println(line.getProduct().getName());
    }
}
```

Có ba tầng:

```text
Root query: PurchaseOrder                       1
    |
    +-- mỗi PurchaseOrder.lines                  +N_order
           |
           +-- mỗi OrderLine.product              +N_product_chua_loaded
```

Tổng truy vấn có thể gần:

\[
Q \approx 1 + N_{\text{orders}} + N_{\text{products chưa loaded}}
\]

Nếu còn truy cập `order.getCustomer().getFullName()`:

\[
Q \approx 1 + N_{\text{orders}} +
N_{\text{products chưa loaded}} +
N_{\text{customers chưa loaded}}
\]

Đây là mô hình khái niệm. Những số này có thể thấp hơn nhờ cache, batch fetching, fetch plan hoặc cao hơn do EAGER associations/những queries khác.

### 8.1. Với dữ liệu mẫu

Có:

- 5 PurchaseOrders.
- 5 OrderLines thuộc 4 orders, một order rỗng.
- 3 distinct Products.
- 3 distinct Customers.

Một trace minh họa **không có batch fetch**, cold persistence context, các quan hệ đều LAZY:

```text
Q1:  SELECT purchase_orders
Q2:  SELECT order_lines WHERE order_id = 101
Q3:  SELECT product WHERE id = 10
Q4:  SELECT product WHERE id = 20
Q5:  SELECT order_lines WHERE order_id = 102
     Product#20 đã managed -> không cần Q mới
Q6:  SELECT order_lines WHERE order_id = 103
Q7:  SELECT order_lines WHERE order_id = 104
Q8:  SELECT product WHERE id = 30
Q9:  SELECT order_lines WHERE order_id = 105
     Product#10 đã managed -> không cần Q mới
```

Trong trace này có **9 SELECTs = 1 root + 5 collections + 3 distinct products**.

Nếu code còn đọc customers, có thể thêm tới 3 SELECTs, thành **12 SELECTs**.

### 8.2. Vì sao không phải “mỗi line thêm một query” trong mọi trường hợp?

Vì 5 lines chỉ tham chiếu 3 products; trong cùng persistence context các products đã loaded có thể được tái sử dụng.

Nếu dữ liệu thật có 10.000 lines, mỗi line dùng một product khác, số secondary SQL có thể rất lớn. Nếu 10.000 lines cùng dùng 5 products và cache tốt, số query product có thể thấp hơn nhiều.

**N+1 là nguy cơ mở rộng theo số đơn vị lazy-loading khác nhau**, không nhất thiết bằng số getter invocations.

### 8.3. N+1 lồng nhau có thể nghiêm trọng hơn N+1 đơn lẻ

Nếu hai collections nhiều-nhiều tầng cùng LAZY, query count có thể tăng theo:

- Số orders cần load lines.
- Số lines cần load discounts/taxes.
- Số related products/customers cần load.

Trong ứng dụng thực, đây có thể là **1 + N + M** hoặc nhiều tầng, không nên cố ép mọi trường hợp thành đúng con số “N+1”.

---

## 9. Nhận diện N+1 ẩn trong MapStruct, ModelMapper hoặc mapper thủ công

Rất nhiều service có code trông vô hại:

```java
List<PurchaseOrder> entities =
    orderRepository.findRecentOrders();

return entities.stream()
    .map(orderMapper::toDto)
    .toList();
```

Mapper:

```java
public OrderDto toDto(PurchaseOrder order) {
    return new OrderDto(
        order.getId(),
        order.getCode(),
        order.getCustomer().getFullName(),
        order.getLines().stream()
            .map(line -> new LineDto(
                line.getProduct().getName(),
                line.getQuantity()
            ))
            .toList()
    );
}
```

Lệnh `stream().map(...)` không tự thực thi SQL do Java Stream API. **Các getters được mapper gọi** có thể khiến provider fetch associations.

### 9.1. Đường đi truy cập thực tế

```text
OrderService.listOrders
    |
    +-- repository.findRecentOrders
    |      |
    |      +-- SELECT orders (Q1)
    |
    +-- mapper.toDto(order #101)
    |      +-- getCustomer().getFullName()  -> SELECT Customer#1?
    |      +-- getLines()                   -> SELECT Lines#101?
    |             +-- getProduct().getName()-> SELECT Product#10?
    |
    +-- mapper.toDto(order #102)
           +-- getCustomer().getFullName()  -> cache?
           +-- getLines()                   -> SELECT Lines#102?
                  +-- getProduct().getName()-> cache?
```

**Dấu hỏi** nhắc rằng thực tế còn phụ thuộc loaded state/cache/provider.

### 9.2. MapStruct compile-time không làm query “miễn phí”

MapStruct có thể sinh Java code đọc getters. Cách map có type safety/compile-time generated code nhưng không làm JPA biết rằng nên batch/fetch các associations.

Tương tự, reflection-based mappers như ModelMapper có thể duyệt nested paths mà developer không nhận ra ngay.

### 9.3. Cách phát hiện

Khi xem số SQL tăng trong API:

1. Tìm query lấy root entities.
2. Tìm mapper được gọi cho từng entity.
3. Liệt kê tất cả property paths mapper sử dụng.
4. So khớp paths đó với fetch mapping.
5. Quan sát SQL phát ngay khi mapper chạy.
6. Thiết kế query/DTO phù hợp.

Đừng chỉ sửa query root mà không hiểu mapper thật sự cần gì.

---

## 10. N+1 do JSON serialization, GraphQL resolver và view rendering

Một controller trả thẳng JPA entity:

```java
@GetMapping("/orders")
public List<PurchaseOrder> list() {
    return service.findOrders();
}
```

JSON serializer có thể truy cập getters:

```text
getId()
getCode()
getStatus()
getCustomer()
  getFullName()
getLines()
  for each line:
    getProduct()
      getName()
```

Nếu persistence context vẫn mở (chẳng hạn nhờ Open Session in View), serializer có thể tạo hàng loạt SQL ở tầng web.

Nếu context đã đóng, serializer có thể gặp lỗi do association chưa khởi tạo; với Hibernate, lỗi phổ biến là `LazyInitializationException`.

### 10.1. Bật OSIV không chữa N+1

OSIV (*Open Session/EntityManager in View*) cho phép context tồn tại qua một phần chu kỳ render response.

Nó có thể làm lỗi lazy initialization ít xuất hiện hơn, nhưng nếu serializer vẫn duyệt 100 associations chưa loaded thì **những SELECT phụ vẫn có thể chạy**.

Tệ hơn, SQL giờ nằm ngoài service transaction boundary mong muốn, làm khó dự đoán hiệu năng và thời điểm đọc dữ liệu.

### 10.2. GraphQL dễ gặp trường hợp tương tự

Một GraphQL query:

```graphql
{
  orders {
    id
    customer {
      fullName
    }
    lines {
      product {
        name
      }
    }
  }
}
```

Resolvers có thể được gọi theo từng order và từng line. Nếu mỗi resolver thực hiện repository lookup hoặc lazy-load relation riêng lẻ, pattern N+1 có thể xuất hiện dù không dùng `@OneToMany` trực tiếp.

GraphQL DataLoader/batching có thể là giải pháp ở resolver layer; còn JPA fetch join/entity graph/DTO có thể giải quyết ở persistence layer. Cần xem chính xác đường truy cập, không cho rằng một công cụ giải quyết mọi tầng.

### 10.3. Template engine cũng có thể kích hoạt truy vấn

Ví dụ HTML view:

```text
for order in orders:
    order.customer.fullName
    order.lines.size
```

Nếu view access đi qua getters của managed JPA objects, nó cũng có thể sinh secondary queries.

**N+1 là vấn đề của mọi nơi đọc graph**, không độc quyền Java controller hay Hibernate.

---

## 11. Logging, `toString`, `equals` và debugger có thể vô tình gây N+1

### 11.1. Logging entity nguyên vẹn

```java
for (PurchaseOrder order : orders) {
    log.debug("Order: {}", order);
}
```

Nếu `toString` được implement theo toàn graph:

```java
@Override
public String toString() {
    return "Order[" + code + ", customer="
        + customer.getFullName()
        + ", lines=" + lines + "]";
}
```

thì chỉ riêng debug logging có thể đọc `customer` và `lines`.

An toàn hơn:

```java
log.debug(
    "Order id={}, code={}, status={}",
    order.getId(),
    order.getCode(),
    order.getStatus()
);
```

### 11.2. Lombok `@Data` và relation fields

Lombok `@Data` có thể sinh `toString`, `equals` và `hashCode` dựa trên fields theo cấu hình/defaults. Với entity quan hệ hai chiều, điều này có thể:

- Dẫn tới duyệt LAZY associations.
- Gây N+1 khi log/so sánh collection.
- Tạo đệ quy vô hạn (`order.lines -> line.order -> order.lines`).
- Làm equality phụ thuộc mutable state.

Với JPA entity, nên thiết kế `toString`/`equals`/`hashCode` có chủ đích, thường tránh đệ quy vào associations.

### 11.3. Debugger watch/evaluate

IDE debugger có thể gọi getter/`toString` khi hiển thị object, tùy cài đặt. Nếu bật auto evaluation, quan sát object đôi khi phát SQL.

Đừng kết luận một dòng code chủ động kích hoạt SQL chỉ từ một lần step-debug có thêm SELECT. Chạy lại không có auto-evaluation hoặc dùng query count ở integration test.

---

## 12. `@PostLoad` và entity listeners: công việc ẩn lúc load entity

JPA có lifecycle callback:

```java
@PostLoad
private void afterLoad() {
    // Xử lý nhẹ sau khi entity được load.
}
```

Nếu callback truy cập association:

```java
@PostLoad
private void afterLoad() {
    int count = lines.size(); // Có thể kích hoạt tải collection.
}
```

thì một query tải hàng trăm orders có thể bị kích hoạt thêm các lazy reads ngay trong quá trình load. N+1 có thể xuất hiện **trước khi service nhận kết quả**.

### 12.1. Cần phân biệt nguyên nhân

- N+1 do **EAGER secondary selects**.
- N+1 do **`@PostLoad` / listener code**.
- N+1 do **mapper/service**.
- N+1 do **serializer/rendering**.

Cả bốn có thể tạo nhiều SQL tương tự. Cách sửa đúng phụ thuộc nguồn truy cập.

### 12.2. Callback không phải công cụ cấu hình fetch plan

`@PostLoad` không có nghĩa tất cả nested relationships đã loaded. Đừng lạm dụng callback để duyệt graph hoặc phát network requests. Nếu cần dữ liệu liên quan cho use case, khai báo trong query/graph hoặc projection.

---

## 13. Một quy trình thực tế để chẩn đoán N+1

Có thể điều tra theo **sáu bước**.

### Bước 1 — Xác định use case chậm

Ví dụ:

```text
GET /api/orders?status=NEW&page=0
```

Đầu tiên phải xác định toàn bộ request đã thực hiện bao nhiêu DB statements, không chỉ repository method.

### Bước 2 — Khoanh vùng query root

Tìm câu SQL lấy list orders:

```sql
SELECT ... FROM purchase_orders
WHERE status = 'NEW'
ORDER BY id
LIMIT ...
```

Ghi nhận: số root rows, số root entities thực sự nhận, thời gian query.

### Bước 3 — Gom những SQL có cùng cấu trúc

Ví dụ:

```text
SELECT ... FROM order_lines WHERE order_id = ?    x 50
SELECT ... FROM products WHERE id = ?             x 37
SELECT ... FROM customers WHERE id = ?            x 22
```

Nhóm theo **normalized SQL shape** và bind parameters.

### Bước 4 — Tìm association mapping

`order_lines WHERE order_id=?` → `PurchaseOrder.lines`.

`products WHERE id=?` → `OrderLine.product`.

`customers WHERE id=?` → `PurchaseOrder.customer`.

Đây là cách nối SQL tables/FKs về graph paths.

### Bước 5 — Tìm nơi truy cập path

```text
OrderController
  -> OrderService.list
     -> repository.findAll
     -> mapper.toDto
        -> order.getLines()
        -> line.getProduct().getName()
```

Dòng code đọc association là nơi cần kiểm tra fetch plan.

### Bước 6 — Xác nhận bằng thử nghiệm cô lập

- Dùng fixture có nhiều roots.
- Tạo persistence context mới.
- Kiểm soát second-level/query cache.
- Bật SQL logging/query counter.
- Chạy baseline.
- Loại bỏ một access path hoặc fetch path có chủ đích.
- Quan sát secondary SQL tương ứng có giảm không.

Đây là cách xây **bằng chứng quan hệ nhân quả** thay vì chỉ đoán dựa trên tên annotation.

---

## 14. Đọc SQL log đúng cách: dấu hiệu và những “false positives”

### 14.1. Dấu hiệu mạnh của N+1

```text
12:00:00.101 SELECT ... FROM purchase_orders ...
12:00:00.130 SELECT ... FROM order_lines WHERE order_id=?
12:00:00.132 SELECT ... FROM order_lines WHERE order_id=?
12:00:00.134 SELECT ... FROM order_lines WHERE order_id=?
...
```

Có query root và một loạt secondary SQL với cùng cấu trúc theo ID liên quan.

### 14.2. Đừng chỉ nhìn số dấu `?`

Nếu provider batch collection reads:

```sql
SELECT ...
FROM order_lines
WHERE order_id IN (?, ?, ?, ?, ?)
```

đó có thể là **một batch SQL** cho năm parents, không phải năm SELECT riêng.

Một query `IN` có nhiều parameters khác với năm SQL lần lượt.

### 14.3. N+1 vẫn có thể xảy ra với queries nhanh

Mỗi secondary SELECT chỉ tốn 1–2 ms nhưng 500 queries có thể khiến request trễ đáng kể vì:

- Network round trips.
- Connection/pool scheduling.
- JDBC statement overhead.
- Database CPU và lock contention.
- Tăng serialization/transaction duration.

Đừng bỏ qua N+1 chỉ vì query plan của mỗi SELECT có index và thời gian nhỏ.

### 14.4. Nhưng số SELECT lớn không nhất thiết là nguyên nhân chính

Một query duy nhất trả 2 triệu rows cũng có thể nghiêm trọng hơn 100 SELECT nhỏ. N+1 là một vấn đề cần đánh giá bằng tổng thể số queries, rows/bytes, memory và latency.

### 14.5. Truy vấn lặp có thể có chủ đích

Nếu service gọi audit API/database 50 lần theo 50 input khác nhau, đó có thể là một thiết kế không tối ưu khác, nhưng không nhất thiết là **JPA graph traversal N+1**. Bài này tập trung vào secondary selects phát sinh từ **dữ liệu liên quan chưa loaded trong object graph**.

---

## 15. Phân biệt N+1 với fetch có chủ đích, collection initialization và query cache

Để không sửa sai:

| Hiện tượng | Có phải N+1? | Câu hỏi cần hỏi |
|---|---|---|
| Một SELECT orders, rồi SELECT lines theo từng order trong vòng lặp | Rất có thể. | Có thể batch/fetch/project không? |
| Một SELECT orders, rồi một SELECT lấy lines cho tất cả order IDs | Không phải pattern 1+N truyền thống. | Query này tải đúng lượng dữ liệu không? |
| Một SELECT orders JOIN FETCH lines trả nhiều rows | Không phải N+1 trên lines; có thể row explosion. | Có quá nhiều rows/duplicate roots không? |
| Một SELECT root, vài SELECT customers do EAGER secondary fetch | Có thể là biến thể N+1. | Số SELECT tăng theo distinct customers? |
| Dùng cache nên 0 SELECT thêm nhưng graph được initialize | Không có observed DB N+1 trong lượt đó. | Cold cache có khác? |
| Một query COUNT riêng để tính số order lines cho cả page | Không. | Query có tính aggregate đúng không? |
| Dùng `getLines().size()` trên mỗi order, provider chạy COUNT từng collection | Có thể vẫn là N+1. | Có N queries COUNT theo order_id không? |
| Một batch job cố ý xử lý từng ID bằng SQL khác nhau | Có thể là per-item query anti-pattern khác. | Có liên quan lazy graph access? |
| Fetch graph có nhiều secondary SELECT nhưng gom batch | Cần đo. | Có tăng gần tuyến tính theo roots không? |

---

## 16. Phương pháp đo 1: SQL logging và bind parameters

Trong development/test, bật SQL logging của provider.

Với Hibernate, tùy phiên bản có thể cấu hình:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.highlight_sql=false
```

Khi dùng framework logging, thường tốt hơn cấu hình category SQL logger của Hibernate thay vì chỉ `show_sql`. Ví dụ với Hibernate 6 có thể ghi:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Tên logger/setting là **provider/version-specific**, không phải cấu hình JPA chuẩn. Với Hibernate 5, category bind parameters thường khác.

### 16.1. Không nên ghi bind values tùy tiện trong production

Bind parameters có thể chứa PII/secret. Bật TRACE bind logging có chủ đích trong local/test hoặc môi trường được kiểm soát; tránh ghi thông tin nhạy cảm vào log ngoài ý muốn.

### 16.2. Đánh dấu các mốc T0/T1/T2

```java
log.info("T0 before repository query");

List<PurchaseOrder> orders =
    repository.findRecentOrders();

log.info("T1 after repository query");

for (PurchaseOrder order : orders) {
    log.info("T2 before access lines of {}", order.getId());
    int size = order.getLines().size();
    log.info("T3 after access lines: {}", size);
}
```

So sánh thứ tự SQL trong log với T0/T1/T2/T3 để biết truy vấn chạy lúc fetch root hay lúc caller dùng association.

Lưu ý chính việc log entity/collection nguyên vẹn có thể khiến lazy loading; chỉ log IDs/basic fields để tránh thay đổi hành vi đang đo.

---

## 17. Phương pháp đo 2: Hibernate Statistics

Nếu dự án dùng Hibernate, có thể bật statistics:

```properties
hibernate.generate_statistics=true
```

Sau đó:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics statistics =
    sessionFactory.getStatistics();

statistics.clear();

long before = statistics.getPrepareStatementCount();

List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

long afterRoot = statistics.getPrepareStatementCount();

for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        line.getQuantity();
    }
}

long afterGraph = statistics.getPrepareStatementCount();

System.out.println(
    "root statements = " + (afterRoot - before)
);

System.out.println(
    "graph access statements = " + (afterGraph - afterRoot)
);
```

Nếu root query dùng một statement và graph access dùng gần N statements, đó là bằng chứng cho N+1 collection loads.

### 17.1. Tại sao không khẳng định đếm luôn chính xác?

- Statistics thường ở phạm vi `SessionFactory`, có thể bị tác động bởi tests/requests khác chạy song song.
- JDBC batching, L2 cache, EAGER secondary selects, fetch graph làm số thay đổi.
- `getPrepareStatementCount()` đếm prepared statements, không phải “số domain entities loaded”.
- Provider có thể phát additional queries vì ID generation/flush nếu test không cô lập.

Hãy tách fixture setup khỏi phần đo và đo theo kịch bản ổn định.

### 17.2. API trên không thuộc Jakarta Persistence

`SessionFactory` và `Statistics` là **Hibernate extension**. Nếu cần portability giữa Hibernate và EclipseLink, dùng SQL logging/JDBC instrumentation hoặc abstraction metrics của project.

---

## 18. Phương pháp đo 3: JDBC instrumentation và query fingerprint

Một cách không gắn chặt Hibernate là đặt instrumentation ở tầng DataSource/JDBC để đếm SQL executions.

Một bộ query metrics có thể ghi:

```text
Request: GET /orders
Total SELECTs: 86

Fingerprint                                     Count
---------------------------------------------------
SELECT ... FROM purchase_orders ...              1
SELECT ... FROM order_lines WHERE order_id=?     50
SELECT ... FROM customers WHERE id=?             20
SELECT ... FROM products WHERE id=?              15
```

Từ bảng này có thể suy ra cần điều tra:

- `PurchaseOrder.lines`.
- `PurchaseOrder.customer`.
- `OrderLine.product`.

### 18.1. Đừng dựa vào chuỗi SQL nguyên văn chưa chuẩn hóa

SQL có whitespace/alias khác nhau nhưng cùng dạng truy vấn. Instrumentation nên normalize hoặc fingerprint SQL trước khi nhóm, trong phạm vi phù hợp.

### 18.2. Span/call stack giúp nối SQL về code

Nếu tracing cho phép gắn DB spans với request/service call, một chuỗi như sau rất hữu ích:

```text
HTTP GET /orders
  OrderService.list()
    Repository.findAll() -> Q1
    OrderMapper.toDto()
      PurchaseOrder.getLines() -> Q2..Q51
      Product.getName()        -> Q52..Q86
```

Trong production, chọn mức sampling và dữ liệu log an toàn; đo ít nhất trên staging/test với dữ liệu đủ lớn để thấy vấn đề.

---

## 19. Phương pháp quan sát loaded state: `PersistenceUnitUtil.isLoaded`

JPA cung cấp API chuẩn:

```java
import jakarta.persistence.PersistenceUnitUtil;

PersistenceUnitUtil util =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil();

PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

boolean linesLoaded =
    util.isLoaded(order, "lines");

boolean customerLoaded =
    util.isLoaded(order, "customer");
```

Nó cho biết provider đánh giá association đã loaded hay chưa. Đây là một manh mối giúp giải thích SQL phát sinh khi caller truy cập.

### 19.1. Quan sát trước/sau khi dùng collection

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class, orderId
);

boolean before = util.isLoaded(order, "lines");

for (OrderLine line : order.getLines()) {
    System.out.println(line.getQuantity());
}

boolean after = util.isLoaded(order, "lines");

System.out.println("Before: " + before);
System.out.println("After: " + after);
```

Nếu provider đang thực hiện LAZY collection loading thực tế, có thể thấy `before = false` và `after = true`.

### 19.2. Một phép kiểm tra loaded không phải phép đo SQL

`isLoaded` không nói dữ liệu đến từ SQL hay cache. Nó cũng không khẳng định nested `line.product` đã loaded khi `order.lines` loaded.

Không viết assertion portable:

```java
assertFalse(util.isLoaded(order, "lines"));
```

cho mọi LAZY mapping/provider trước access, vì LAZY có thể được load sớm hợp lệ.

### 19.3. Phân biệt root và nested associations

```text
isLoaded(order, "lines") == true
```

không suy ra:

```text
isLoaded(line, "product") == true
```

Nếu response cần nested path, kiểm tra từng association level hoặc thiết kế query graph phù hợp.

---

## 20. Tái hiện N+1 trong một integration test đáng tin cậy

Unit test mock repository có thể kiểm tra mapping DTO, nhưng **không thể chứng minh số SQL do Hibernate/EclipseLink phát**.

Một integration test nên có:

1. JPA provider thực.
2. Database tương thích (ưu tiên cùng loại production cho test quan trọng).
3. Fixture có đủ nhiều root entities và các child.
4. Persistence context mới cho mỗi lần đo.
5. Query counter/SQL logging.
6. Không có setup inserts/flush làm nhiễu số SELECT cần kiểm tra.
7. Cache policy được kiểm soát.
8. Đo query tại cả trước và sau thao tác traversing graph.

### 20.1. Pseudocode tích hợp Hibernate Statistics

```java
@Test
void accessingLazyLinesShowsSecondaryQueries() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        SessionFactory sf =
            emf.unwrap(SessionFactory.class);

        Statistics stats = sf.getStatistics();
        stats.clear();

        List<PurchaseOrder> orders = em.createQuery(
            """
            SELECT o FROM PurchaseOrder o
            WHERE o.status = :status
            ORDER BY o.id
            """,
            PurchaseOrder.class
        )
        .setParameter("status", "NEW")
        .getResultList();

        long afterRoot = stats.getPrepareStatementCount();

        for (PurchaseOrder order : orders) {
            for (OrderLine line : order.getLines()) {
                line.getQuantity();
            }
        }

        long afterTraversal =
            stats.getPrepareStatementCount();

        assertTrue(afterRoot >= 1);
        assertTrue(afterTraversal >= afterRoot);

        tx.rollback();
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
}
```

Các imports JUnit 5/JPA/Hibernate tương ứng cần được thêm vào test class. `emf` là `EntityManagerFactory` đã cấu hình và fixture được seed trước khi bắt đầu thống kê.

**Vì sao test ở trên chưa khẳng định N+1 bằng một con số cứng?** Vì N+1 là điều cần quan sát và provider được quyền sử dụng batch/cache/fetch sớm. Muốn viết performance regression test cụ thể, hãy khóa stack/config, tắt hoặc xác định cache, và đặt **query budget** thích hợp với thiết kế được chọn.

### 20.2. Test cải tiến sau khi fix

Nếu repository chi tiết dùng fetch join:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    WHERE o.status = :status
    """,
    PurchaseOrder.class
)
.setParameter("status", "NEW")
.getResultList();
```

Khi duyệt `lines` trong cùng context, không nên có một SELECT collection riêng cho mỗi order như baseline.

Một test trên provider xác định có thể assert rằng số queries khi traversing lines sau fetch join **không tăng tuyến tính với N**.

### 20.3. Chạy với số lượng root thay đổi

Thử N = 1, 10, 50, 100. Nếu khi tăng N gấp 10 lần, SQL count cũng tăng gần 10 lần dù use case chỉ là một list page, đó là tín hiệu mạnh.

Với fix đúng, SQL count có thể gần như hằng số hoặc tăng theo số **batch** chứ không theo từng parent.

### 20.4. Không để second-level cache làm test sai kết luận

Nếu cache đã warm từ fixture/setup, test có thể không hiện N+1 dù production cold cache có vấn đề.

Có thể:

- Dùng DB/test schema riêng.
- Dùng persistence context mới.
- Chủ động kiểm soát L2 cache trong môi trường test.
- Evict cache có chủ đích khi đo cold-load scenario.
- Phân biệt query count với entity/collection cache hit.

Không tắt cache trong production chỉ vì muốn test N+1 dễ hơn.

---

## 21. Cách khắc phục 1: `JOIN FETCH` cho quan hệ to-one

Nếu API list orders luôn cần tên khách:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    ORDER BY o.id
    """,
    PurchaseOrder.class
).getResultList();
```

Với quan hệ `customer` bắt buộc, INNER JOIN FETCH phù hợp. Nếu association tùy chọn và vẫn cần giữ orders thiếu customer, dùng `LEFT JOIN FETCH`.

### 21.1. Vì sao tránh N+1?

Query yêu cầu provider fetch `customer` cùng root results, nên sau đó:

```java
for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getFullName()
    );
}
```

không cần một vòng lazy SELECT riêng cho mỗi Customer chưa loaded theo hướng query đã yêu cầu.

### 21.2. JOIN FETCH khác JOIN thường

```sql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.fullName LIKE :pattern
```

JOIN thường giúp lọc/truy cập field Customer trong query. Nó **không tự đảm bảo** `o.customer` đã được initialized khi ứng dụng duyệt kết quả.

```sql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
```

JOIN FETCH yêu cầu nạp association.

### 21.3. To-one fetch join và pagination

Fetch join một quan hệ to-one thông thường **không nhân số rows parent như collection** (mỗi order có tối đa một customer), nên thường phù hợp hơn với phân trang so với fetch join one-to-many. Vẫn phải xem joins, filters và query plan cụ thể.

---

## 22. Cách khắc phục 2: `LEFT JOIN FETCH` collection

Nếu endpoint cần orders cùng toàn bộ lines:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    WHERE o.status = :status
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setParameter("status", "NEW")
.getResultList();
```

### 22.1. Vì sao LEFT?

Order#103 không có lines. Nếu dùng:

```sql
JOIN FETCH o.lines
```

đó là INNER join và Order#103 có thể bị loại khỏi kết quả.

`LEFT JOIN FETCH` giữ cả parent có collection rỗng.

### 22.2. Vì sao `DISTINCT`?

Khi Order#101 có hai lines, SQL join tạo hai rows cho cùng order.

`SELECT DISTINCT o` diễn đạt ý định danh sách root entities không trùng ở mức query JPA. Cách provider khử duplicate references trong phiên bản cụ thể có thể khác nhau; Hibernate hiện đại có tối ưu riêng, nhưng không nên mặc định mọi provider/version xử lý trùng giống nhau.

**Quan trọng:** dù chỉ trả một Java PurchaseOrder#101, SQL vẫn có thể mang nhiều rows để nạp collection. `DISTINCT` không phải giải pháp tự động cho row explosion.

### 22.3. N+1 được chữa nhưng có đánh đổi

Nếu một order có 10.000 lines, fetch join có thể trả lượng dữ liệu lớn. Nếu một query fetch hai collection một-nhiều, số SQL rows có thể tăng theo tích số phần tử của các collections.

Do đó, “giảm 101 SELECT thành 1 SELECT” không phải luôn là mục tiêu cuối cùng. Cần kiểm tra rows, bytes và memory.

---

## 23. Cách khắc phục 3: Entity graph theo nhu cầu thực sự

Khi nhiều endpoints cần fetch paths khác nhau, **Entity Graph** giúp khai báo load plan theo use case.

### 23.1. Graph chỉ chứa Customer

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o FROM PurchaseOrder o
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
```

Đây là API Jakarta Persistence. Với stack JPA 2.x cũ dùng `javax.persistence.fetchgraph`; không copy nhầm hint giữa các namespace.

### 23.2. Graph có nested path lines.product

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

Subgraph<OrderLine> linesGraph =
    graph.addSubgraph("lines", OrderLine.class);

linesGraph.addAttributeNodes("product");
```

Graph biểu diễn:

```text
PurchaseOrder
  +-- customer
  +-- lines
        +-- product
```

Nếu use case thật sự đọc `order.lines[*].product.name`, graph yêu cầu provider tải những paths ấy theo semantics graph.

### 23.3. Không đồng nhất graph với một SQL

Entity graph xác định **những thuộc tính cần được fetch**, không ép provider phải chuyển tất cả thành một SQL JOIN. Provider có thể dùng JOIN, secondary selects hoặc batch theo chiến lược triển khai.

Do đó, sau khi thêm entity graph vẫn phải **quan sát SQL**; graph không phải một nút “tắt N+1” thần kỳ.

### 23.4. `fetchgraph` so với `loadgraph`

- `fetchgraph`: attributes nằm trong graph là EAGER; attributes không nằm trong graph được đối xử LAZY theo graph semantics, mặc dù provider vẫn có thể tải thêm.
- `loadgraph`: attributes nằm trong graph là EAGER, các attributes khác theo static fetch setting.

Cả hai có use case riêng; chọn theo dữ liệu thực sự cần và kiểm tra behavior provider.

### 23.5. Named entity graph

Có thể đặt trên `PurchaseOrder`:

```java
@NamedEntityGraph(
    name = "Order.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
```

Sau đó:

```java
EntityGraph<?> graph =
    em.getEntityGraph("Order.withCustomer");
```

Khi khai báo, giữ mapping tại entity class được persistence unit nhận diện, không tự tạo entity trùng tên chỉ để đặt graph.

---

## 24. Cách khắc phục 4: DTO projection bỏ hẳn nhu cầu lazy traversal

Nhiều use cases không cần managed entity.

Ví dụ màn hình order list chỉ hiển thị:

- Code.
- Status.
- Customer name.

DTO:

```java
package com.example.nplusone;

public record OrderListRow(
    Long id,
    String code,
    String status,
    String customerName
) {}
```

JPQL:

```java
List<OrderListRow> rows = em.createQuery(
    """
    SELECT NEW com.example.nplusone.OrderListRow(
        o.id,
        o.code,
        o.status,
        c.fullName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    ORDER BY o.id
    """,
    OrderListRow.class
).getResultList();
```

### 24.1. Vì sao không có lazy Customer traversal ở caller?

DTO đã chứa `customerName`. Caller không cần:

```java
order.getCustomer().getFullName()
```

nên không có một đường access tới managed Customer từ response list.

### 24.2. Projection khác fetch join

- `JOIN FETCH`: lấy managed entity và nạp association.
- `SELECT NEW`: tạo DTO từ scalar expressions.

Nếu chỉ đọc thông tin hiển thị, projection thường đơn giản, dễ serialize và ít phụ thuộc persistence context.

### 24.3. Count child bằng aggregate, đừng tải collection chỉ để đếm

Nếu cần số lines trên mỗi order:

```java
public record OrderCountRow(
    Long orderId,
    String code,
    Long lineCount
) {}
```

```java
List<OrderCountRow> rows = em.createQuery(
    """
    SELECT NEW com.example.nplusone.OrderCountRow(
        o.id,
        o.code,
        COUNT(l)
    )
    FROM PurchaseOrder o
    LEFT JOIN o.lines l
    GROUP BY o.id, o.code
    ORDER BY o.id
    """,
    OrderCountRow.class
).getResultList();
```

`COUNT(l)` cho Order#103 bằng 0 vì không có child.

Thay vì:

```java
orders.stream()
    .map(o -> new OrderCountRow(
        o.getId(), o.getCode(),
        (long) o.getLines().size()
    ))
    .toList();
```

Nếu `lines` chưa loaded, cách thứ hai có thể kích hoạt N collection loads.

---

## 25. Cách khắc phục 5: batch fetching trên provider

Khi không tiện fetch join hoặc graph lớn, một provider có thể hỗ trợ **batch fetching**.

### 25.1. Ý tưởng

Không batch:

```sql
SELECT * FROM order_lines WHERE order_id = 101;
SELECT * FROM order_lines WHERE order_id = 102;
SELECT * FROM order_lines WHERE order_id = 103;
SELECT * FROM order_lines WHERE order_id = 104;
```

Có batch:

```sql
SELECT *
FROM order_lines
WHERE order_id IN (101,102,103,104);
```

Về mặt SQL executions, 4 collections có thể được nạp bằng ít hơn 4 SELECT.

### 25.2. Hibernate `@BatchSize`

Ví dụ **provider-specific**:

```java
@org.hibernate.annotations.BatchSize(size = 32)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Khi một collection bị truy cập, Hibernate có thể batch-load các collections chưa initialized của những parents phù hợp.

Có thể có cấu hình global batch fetch size, tùy Hibernate version.

### 25.3. Không coi batch fetching là tính năng chuẩn của JPA

`@BatchSize` thuộc Hibernate, không thuộc Jakarta Persistence core. EclipseLink có các fetch optimization riêng.

Nếu cần chạy trên nhiều JPA providers, cân nhắc fetch join, entity graph hoặc DTO projection với test cụ thể.

### 25.4. Batch size không nên chọn tùy tiện

Batch lớn:

- Giảm số round trips.
- Có thể tăng kích thước `IN` list và SQL result.
- Có thể chạm giới hạn bind parameters của DB.
- Có thể tải nhiều related entities hơn cần thiết.
- Không bảo đảm luôn được gom đủ số parents.

Dựa trên số roots/child, page size và DB performance để quyết định.

### 25.5. Subselect fetching

Một số providers, như Hibernate, hỗ trợ subselect fetch cho collections.

Ví dụ Hibernate-specific:

```java
@org.hibernate.annotations.Fetch(
    org.hibernate.annotations.FetchMode.SUBSELECT
)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Provider có thể dùng một truy vấn phụ để fetch collections cho nhóm parents đã được truy vấn.

Đây cũng là extension, cần kiểm thử SQL thực tế và memory footprint. Không coi nó là giải pháp tốt cho mọi query.

---

## 26. Cách khắc phục 6: hai bước khi cần phân trang parent kèm collection

Một bài toán rất thường gặp:

> API cần trang 20 orders, mỗi order kèm lines.

Câu query:

```java
List<PurchaseOrder> page = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.id
    """,
    PurchaseOrder.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

**Có rủi ro phân trang sai/tốn bộ nhớ** vì một root có thể tạo nhiều SQL rows. Tùy provider, nó có thể phân trang trong memory, cảnh báo, hoặc có chiến lược đặc thù.

### 26.1. Bước 1: phân trang IDs của root

```java
List<Long> pageIds = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.status = :status
    ORDER BY o.id
    """,
    Long.class
)
.setParameter("status", "NEW")
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
```

### 26.2. Bước 2: fetch collection cho page roots

```java
List<PurchaseOrder> pageOrders;

if (pageIds.isEmpty()) {
    pageOrders = List.of();
} else {
    pageOrders = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        WHERE o.id IN :ids
        """,
        PurchaseOrder.class
    )
    .setParameter("ids", pageIds)
    .getResultList();
}
```

Kết quả:

- Bước 1 giới hạn **số parent IDs**.
- Bước 2 tải collection cho những parents đó.
- Không còn vấn đề đặt `setMaxResults` trực tiếp trên query fetch collection.

### 26.3. Những caveats quan trọng

- `WHERE id IN :ids` **không bảo đảm thứ tự giống `pageIds`**. Sắp xếp lại theo thứ tự IDs hoặc có ORDER BY rõ ràng.
- Nếu DB có limit danh sách parameters, chia IDs theo batch phù hợp.
- Hai statements có thể quan sát dữ liệu khác nhau nếu transaction khác thay đổi ở giữa; transaction isolation cần phù hợp business requirement.
- SQL bước 2 vẫn có thể nhân số rows theo số lines trong mỗi order.
- Nếu cần nested `line.product.name`, phải chọn fetch strategy bổ sung; chỉ fetch `lines` chưa đủ.

### 26.4. Khi list page chỉ cần số line

Đừng fetch toàn bộ lines. Query DTO aggregate theo page IDs có thể tiết kiệm hơn.

Đây là cách chọn giải pháp dựa trên **nhu cầu đọc** chứ không chỉ tối thiểu số SQL.

---

## 27. N+1 khi JOIN hai collections: tránh chuyển thành Cartesian explosion

Giả sử entity `PurchaseOrder` có:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderComment> comments;
```

Một query:

```sql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.comments
```

có thể tạo số SQL rows lớn:

```text
1 order có 10 lines và 20 comments
    -> tối đa 10 x 20 = 200 joined rows
       để đại diện cho 1 order
```

N+1 trên hai collections có thể được giảm, nhưng đổi lại là **row multiplication** rất tốn kém.

Trong Hibernate, fetch nhiều bag collections còn có thể gặp provider-specific restriction như `MultipleBagFetchException`, tùy mapping và phiên bản.

### 27.1. Không chỉ theo đuổi “1 query”

Có thể tốt hơn khi:

- Fetch root + một collection ở query 1.
- Fetch collection còn lại bằng batch/query 2.
- Hoặc tạo DTO projections/aggregates.
- Hoặc load theo hai bước/page IDs.

Điểm đo đúng là **tổng latency, số rows, bytes, memory và SQL count**, không phải một con số SELECT càng nhỏ càng tốt.

### 27.2. Không sử dụng `Set` chỉ để tránh một exception

Đổi một collection từ `List` sang `Set` có ảnh hưởng domain semantics, ordering và equality. Không đổi kiểu collection chỉ để provider cho phép query fetch nhiều associations; hãy xem chính thiết kế fetch plan và domain data model.

---

## 28. Vì sao cache làm N+1 khó tái hiện?

### 28.1. First-level cache

Trong cùng EntityManager/persistence context, một entity có cùng type + ID thường tương ứng một managed identity. Khi đã tải Product#10, truy cập nó từ một line khác có thể không cần SQL nữa.

Do đó:

```text
5 lines tham chiếu 3 products
    -> không nhất thiết 5 SELECT products
```

### 28.2. Second-level cache

Nếu provider bật shared cache cho Product, việc tải Product#10 có thể được phục vụ từ cache ở những persistence contexts khác nhau.

N+1 **về số lazy object initialization** vẫn có thể tồn tại trong logic, nhưng số SELECT quan sát có thể giảm do cache hits.

### 28.3. Query cache khác entity cache

Query cache có thể giữ danh sách IDs/kết quả của query theo provider, còn entity/collection cache giữ state đối tượng. Không mặc định query cache giải quyết N+1 của mọi LAZY association.

### 28.4. Cold cache vs warm cache

Một bài test chạy sau một lượt đã khởi tạo associations có thể không còn thấy SQL phụ.

Để đo N+1, cần nêu rõ:

- Context mới hay reused?
- Second-level cache bật/tắt?
- Related entities đã từng loaded trong context chưa?
- Query đang dùng fetch plan nào?
- Test setup có làm warm associations trước khi đo không?

### 28.5. Không “fix” N+1 chỉ bằng cache

Nếu pattern thật là 1 + 100 lazy loads, cache có thể giảm round trips khi dữ liệu lặp; nhưng với cold cache hoặc nhiều unique IDs vẫn có nguy cơ.

Cache là một lớp tối ưu khác, không thay thế thiết kế fetch plan phù hợp.

---

## 29. Thời điểm truy cập, persistence context và detached entities

### 29.1. Trong EntityManager đang mở

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    ).getResultList();

    for (PurchaseOrder order : orders) {
        // Nếu chưa loaded, có thể phát SELECT ở đây.
        order.getLines().size();
    }

    tx.commit();
} finally {
    if (tx.isActive()) tx.rollback();
    em.close();
}
```

N+1 có thể xảy ra **trong transaction** nếu fetch plan không phù hợp.

### 29.2. Sau khi đóng EntityManager

```java
List<PurchaseOrder> orders;

EntityManager em = emf.createEntityManager();

try {
    orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    ).getResultList();
} finally {
    em.close();
}

// Entity detached, collections có thể chưa loaded.
for (PurchaseOrder order : orders) {
    order.getLines().size();
}
```

Ở Hibernate, một lazy collection chưa initialized có thể gây `LazyInitializationException` vì session/context cũ không còn.

**N+1 và lazy initialization error có cùng nguồn gốc có thể là thiếu dữ liệu cần dùng trong fetch plan**, nhưng biểu hiện khác nhau tùy context còn mở không.

### 29.3. Không chữa lỗi bằng cách EAGER tất cả

Nếu chỉ mở màn hình danh sách đơn và không cần lines, đổi `lines` sang EAGER có thể khiến mọi danh sách phải tải lines. Điều đó có thể làm giảm exception nhưng làm hiệu năng tổng thể kém hơn.

Giải pháp thường là **nạp đúng paths cần dùng khi còn context hợp lệ hoặc trả DTO**, không phải mở rộng fetch vô điều kiện.

### 29.4. Persistence context mới không đồng nghĩa transaction mới trong mọi cấu hình

JPA có resource-local/JTA và các loại persistence context; thời điểm close/commit/transaction visibility khác nhau theo môi trường. Khi chẩn đoán, ghi rõ ranh giới:

```text
EntityManager opened
Transaction started
Root query executed
Mapper executed
Transaction committed
EntityManager closed
Serializer executed
```

Đường thời gian này giúp xác định liệu vấn đề là N+1, detached LAZY hay cả hai.

---

## 30. Spring Data JPA: `findAll`, derived query và `@EntityGraph`

Một repository đơn giản:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(String status);
}
```

Method này không tự hứa `customer` hoặc `lines` được fetch theo nhu cầu DTO. Nếu service lặp và đọc associations, có thể N+1.

### 30.1. Khai báo entity graph trên repository method

Ví dụ Spring Data JPA-specific:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer", "lines"})
    List<PurchaseOrder> findByStatus(String status);
}
```

Annotation `@EntityGraph` trong ví dụ là của **Spring Data JPA**, dựa trên JPA entity graph semantics. Kết quả SQL cụ thể phụ thuộc provider.

### 30.2. Thêm nested path khi cần

```java
@EntityGraph(attributePaths = {
    "customer",
    "lines",
    "lines.product"
})
List<PurchaseOrder> findByStatus(String status);
```

Không dùng graph này cho mọi endpoint nếu nhiều nơi chỉ cần order code/status.

### 30.3. Spring projection interface/record

Spring Data hỗ trợ projections theo cơ chế riêng. Chúng có thể giảm dữ liệu tải khi query/closed projection phù hợp, nhưng **nested projection** có thể vẫn tạo joins/fetch theo cách không tối ưu tùy implementation.

Không suy luận chỉ từ việc return type có tên `OrderDto` rằng SQL chắc chắn không có N+1. Hãy kiểm tra query thực tế và getters mà projection/materialization sử dụng.

### 30.4. `@Transactional(readOnly = true)` không tự tối ưu graph

Transaction read-only không làm `@OneToMany` tự batch fetch hay JOIN FETCH. Nó giải quyết ranh giới transaction/intent, không trực tiếp quyết định fetch shape.

---

## 31. Phân tích N+1 trong Criteria API

Một query Criteria:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

cq.select(order).where(
    cb.equal(order.get("status"), "NEW")
);

List<PurchaseOrder> orders =
    em.createQuery(cq).getResultList();
```

Nếu code sau đó gọi `getLines()` trên mỗi order, N+1 có thể xuất hiện như JPQL.

### 31.1. Criteria `join` không tự là fetch

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);
```

Join phục vụ predicates/projection. Nó không đồng nghĩa yêu cầu fetch association.

### 31.2. Criteria `fetch`

```java
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

order.fetch("customer", JoinType.INNER);
order.fetch("lines", JoinType.LEFT);

cq.select(order).distinct(true);
```

`fetch` diễn đạt fetch association theo Criteria API.

Tuy nhiên, một query Criteria fetch to-many vẫn có **row multiplication** và **pagination caveats** tương tự JPQL fetch join.

### 31.3. Type-safe query builder không tự tránh N+1

Criteria API giúp xây truy vấn động, không tự hiểu caller sau đó sẽ truy cập những paths nào. Truy vấn Criteria trả entities mà mapper duyệt associations LAZY vẫn có thể gây N+1.

---

## 32. Dùng JPQL SELECT JOIN nhưng lại trả entity: bẫy rất phổ biến

Query:

```sql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.fullName LIKE :pattern
```

Bạn đã JOIN customer trong SQL, nhưng sau query:

```java
for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getFullName()
    );
}
```

provider vẫn có thể cần tải `Customer` nếu association chưa initialized. **JOIN thường chỉ cho điều kiện lọc và projection**, không phải cam kết nạp association vào entity result.

Nếu caller cần Customer managed:

```sql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.status = :status
```

Nếu caller chỉ cần tên Customer:

```sql
SELECT NEW com.example.nplusone.OrderListRow(
    o.id, o.code, o.status, c.fullName
)
FROM PurchaseOrder o
JOIN o.customer c
```

Hai đường có mục đích khác nhau. Không biến JOIN thành JOIN FETCH một cách máy móc nếu query chỉ cần scalar DTO.

---

## 33. `@OneToOne` LAZY và truy vấn bổ sung ngay cả khi chưa gọi getter

Một trường hợp dễ gây nhầm:

```java
@Entity
public class Account {

    @Id
    private Long id;

    @OneToOne(
        mappedBy = "account",
        fetch = FetchType.LAZY
    )
    private AccountProfile profile;
}
```

Ở phía inverse `mappedBy`, bảng Account có thể không mang foreign key để biết Profile có tồn tại hay không.

Tùy provider, `optional`, shared primary key và bytecode enhancement, provider có thể phải kiểm tra bảng Profile hoặc fetch sớm. Nếu lấy N accounts, có thể có N secondary SELECTs **trước khi bất kỳ `getProfile()` nào được gọi**.

### 33.1. Dấu hiệu chẩn đoán

- Truy vấn root Accounts.
- Log ngay sau query đã có nhiều SELECTs tới AccountProfile.
- Mapper chưa chạy.
- Mapping có inverse one-to-one LAZY/EAGER tùy provider.

Trong trường hợp này, nguyên nhân không phải vòng lặp `getProfile()` tại service, mà là **provider's association loading behavior**.

### 33.2. Hướng đánh giá

- Xác định owning/inverse side và FK location.
- Xem xét mapping shared primary key/`@MapsId` nếu đúng domain.
- Kiểm tra khả năng enhancement của provider.
- Dùng projection hoặc graph/query phù hợp nếu use case không cần profile.
- Test SQL trên provider/version thật.

Đừng sửa bằng một giả thuyết rằng `fetch=LAZY` luôn trì hoãn mọi query.

---

## 34. N+1 với `@ElementCollection` và Map collections

Không phải collection nào cũng chứa entity.

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "product_tags",
    joinColumns = @JoinColumn(name = "product_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

Nếu code:

```java
for (Product product : products) {
    if (product.getTags().contains("sale")) {
        ...
    }
}
```

mỗi `product.tags` chưa loaded có thể kích hoạt SQL tới `product_tags`, giống N+1.

### 34.1. Query theo điều kiện thay vì duyệt Java

Nếu muốn tìm products có tag:

```sql
SELECT DISTINCT p
FROM Product p
JOIN p.tags t
WHERE t = :tag
```

Đây là JPQL khi `Product` thực sự có `tags` như mapping giả định. Nó lọc tại DB, tránh tải `tags` cho mọi Product chỉ để kiểm tra `contains`.

### 34.2. Map associations

```java
@ElementCollection
@CollectionTable(...)
@MapKeyColumn(name = "locale")
@Column(name = "description")
private Map<String, String> descriptions;
```

Truy cập:

```java
for (Product product : products) {
    String desc = product.getDescriptions().get("vi");
}
```

cũng có thể phát một truy vấn trên mỗi product tùy provider/loaded state.

Đừng giả định Java `Map.get` luôn O(1) và không liên quan database: đối tượng ở đây có thể là **persistent collection wrapper**.

---

## 35. Truy cập thuộc tính qua getter vs field access có thay đổi N+1 không?

JPA cho phép **field access** hoặc **property access** dựa trên vị trí mapping annotations. Điều đó khác với việc **người dùng code truy cập dữ liệu**.

Ví dụ:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;

public List<OrderLine> getLines() {
    return lines;
}
```

Với provider sử dụng persistent collection wrapper/bytecode enhancement, việc lặp danh sách có thể kích hoạt SQL dù getter không tự gọi repository.

### 35.1. Không lấy tên getter làm bằng chứng

`getLines()` có thể trả wrapper, còn `iterator()`/`size()` là thao tác cần dữ liệu. Một provider khác có thể load collection tại bước trước đó.

Khi chẩn đoán, ghi rõ:

- Caller gọi method nào?
- Method có thực sự đọc phần tử không?
- Collection initialized từ trước chưa?
- Có provider-specific extra-lazy optimization không?

### 35.2. Domain method có thể ẩn association traversal

```java
public boolean containsExpensiveProduct() {
    return lines.stream()
        .anyMatch(line ->
            line.getProduct()
                .getUnitPrice()
                .compareTo(new BigDecimal("1000000")) > 0
        );
}
```

Một lời gọi:

```java
for (PurchaseOrder order : orders) {
    if (order.containsExpensiveProduct()) {
        ...
    }
}
```

trông không giống getter nhưng có thể gây N+1 ở cả `lines` và `product`.

Điều tra theo **đường truy cập sâu thực tế**, không chỉ tìm keyword `getLines`.

---

## 36. N+1 và transaction isolation: truy vấn LAZY có thể đọc thời điểm khác

Giả sử:

```text
T0: SELECT PurchaseOrder#101
T1: Transaction khác thêm OrderLine cho #101, commit
T2: Lần đầu truy cập order.getLines()
      -> SELECT order_lines WHERE order_id=101
```

Nếu transaction isolation cho phép các statements đọc committed state tại những thời điểm khác nhau, collection được nạp ở T2 có thể chứa dòng được thêm sau khi root entity được đọc ở T0.

### 36.1. Không chỉ là hiệu năng

Việc nhiều SELECT xảy ra khác thời điểm có thể ảnh hưởng:

- Snapshot consistency.
- Validation của business logic phụ thuộc nhiều entities.
- Lock duration.
- Dữ liệu hiển thị có tính nhất quán giữa header và lines.

### 36.2. JOIN FETCH không bảo đảm mọi vấn đề consistency biến mất

Khi query tải order + lines trong một statement, DB có thể cung cấp snapshot nhất quán cho dữ liệu đó theo isolation/DB semantics. Nhưng products/customers chưa fetched vẫn có thể được load sau.

Nếu invariant business mạnh, cần transaction isolation/locking/version policy chứ không chỉ giảm query count.

---

## 37. Đưa công việc về đúng boundary: repository, service, response

Một luồng dễ gây N+1:

```text
Repository.findAllOrders()
   -> trả List<PurchaseOrder>

Controller
   -> JSON serializer duyệt toàn graph

SQL lazy loads xảy ra sau repository call
```

Một thiết kế rõ hơn:

```text
OrderService.listOrderSummaries()
   -> Repository query projection
   -> List<OrderListRow>
   -> Controller trả DTO

Không còn graph JPA để serializer duyệt ngoài ý muốn
```

Hoặc nếu thật sự cần entity + lines:

```text
OrderService.getOrderDetails(id)
   -> Repository query với fetch plan chi tiết
   -> Mapper tạo OrderDetailsDto trong transaction
   -> Controller trả DTO
```

### 37.1. DTO example

```java
public record OrderDetailsDto(
    Long id,
    String code,
    String status,
    String customerName,
    List<LineDto> lines
) {}

public record LineDto(
    String productName,
    int quantity
) {}
```

Service mapping:

```java
OrderDetailsDto toDto(PurchaseOrder order) {
    List<LineDto> lines = order.getLines().stream()
        .map(line -> new LineDto(
            line.getProduct().getName(),
            line.getQuantity()
        ))
        .toList();

    return new OrderDetailsDto(
        order.getId(),
        order.getCode(),
        order.getStatus(),
        order.getCustomer().getFullName(),
        lines
    );
}
```

Đoạn mapper này **không tự giải quyết N+1**. Repository phải fetch/provide paths `customer`, `lines` và `lines.product` hiệu quả **trước khi mapper chạy**.

### 37.2. Tránh “all-purpose entity” làm API contract

Một entity có thể có hàng chục associations. API chỉ nên expose dữ liệu thuộc response contract, không phó mặc serializer traverse bất kỳ getter nào được nó nhìn thấy.

---

## 38. Chẩn đoán hiệu năng: số query, số rows và chiều rộng graph

Một endpoint A:

```text
1 SELECT orders
100 SELECT lines
Total: 101 SELECTs
~500 lines retrieved
```

Endpoint B sau fetch join:

```text
1 SELECT orders LEFT JOIN lines
Total: 1 SELECT
~500 joined rows retrieved
```

Endpoint C theo batch:

```text
1 SELECT orders
4 SELECT batched lines (25 parents/batch)
Total: 5 SELECTs
~500 lines retrieved
```

Endpoint D chỉ cần line count:

```text
1 SELECT orders + COUNT(lines) grouped
Total: 1 SELECT
~100 aggregate rows
```

Không có lựa chọn tối ưu cho mọi use case. Nếu chỉ cần count, D thường hiệu quả hơn nạp 500 line entities. Nếu cần sửa OrderLine managed objects, C hoặc B có thể phù hợp hơn. Nếu chỉ cần một order chi tiết nhỏ, B đơn giản.

### 38.1. Chi phí không chỉ là SQL count

Các metric hữu ích:

- Prepared statement count.
- Network round trips.
- Database execution time.
- Số rows trả về.
- Tổng bytes nhận.
- Thời gian hydrate entities.
- Heap memory/GC.
- Transaction/connection duration.
- Cache hit ratio.
- Request p95/p99 latency.

Một fetch join “1 query” trả hàng trăm nghìn SQL rows có thể chậm hơn 5 batch queries trả số rows cần thiết.

---

## 39. Quy trình chọn giải pháp theo dạng N+1

| Pattern phát hiện | Đường truy cập gây ra | Giải pháp thường cân nhắc | Cần tránh |
|---|---|---|---|
| 1 + N SELECT lines | `order.getLines()` trong vòng lặp | `LEFT JOIN FETCH o.lines`, entity graph, batch fetch | `@OneToMany(EAGER)` mọi nơi |
| 1 + D SELECT customers | `order.getCustomer().getName()` | To-one fetch join, DTO projection | Nghĩ EAGER tự bảo đảm JOIN |
| 1 + N + M ở lines/products | `order.lines[*].product.name` | Graph nested, fetch có chủ đích, DTO/batch | Chỉ fetch lines rồi cho rằng đã đủ |
| COUNT per order | `order.getLines().size()` | `COUNT(l) GROUP BY`, DTO aggregate | Load toàn collection chỉ để đếm |
| SQL từ serializer | Trả entity trực tiếp | DTO, bounded fetch plan | OSIV như phương án duy nhất |
| SQL do `toString` | Logging entity/collection | Log ID/basic fields | Lombok/string hóa toàn graph |
| EAGER secondary SELECTs | Provider load associations trước getters | Query-level fetch plan, projection | Đổi sang EAGER nhiều hơn |
| Inverse `@OneToOne` probes | Provider xác định existence | Xem mapping/bytecode enhancement, projection | Tin `LAZY` luôn không có SQL |
| Collection fetch + pagination | To-many JOIN nhân rows | Page root IDs trước, fetch sau | `setMaxResults` trực tiếp không kiểm chứng |
| Fetch hai collections làm row explosion | Hai to-many joins | Fetch theo bước, batch/subselect | Bám mục tiêu “chỉ một SQL” |
| N+1 chỉ lộ cold cache | Cache che secondary SQL | Cold-load integration test, fetch fix | Chỉ benchmark warm cache |

---

## 40. Những lỗi hiểu nhầm thường gặp

### 40.1. “Repository chạy một query nên không thể N+1”

Sai. Repository có thể chạy một root query; N secondary queries xảy ra khi mapper/service/serializer truy cập graph sau đó.

### 40.2. “Đã `JOIN` trong JPQL thì relationship luôn loaded”

Sai. `JOIN` thường khác `JOIN FETCH`.

### 40.3. “Tất cả `LAZY` đều gây N+1”

Sai. LAZY chỉ trì hoãn khi có thể; nếu caller không truy cập relation hoặc query đã fetch sẵn thì không có secondary load ở path đó.

### 40.4. “Dùng `EAGER` là giải pháp”

Không bảo đảm. Provider có thể dùng secondary queries và gây N+1 sớm hơn.

### 40.5. “Nếu N = 100 thì có đúng 101 SQL”

Không. Số secondary queries phụ thuộc số distinct associations chưa loaded, cache, batching, graph depth và provider.

### 40.6. “Dữ liệu đã loaded trong Hibernate lần trước nên không cần fix”

Cold cache/một persistence context khác vẫn có thể tái hiện. Cache hit không tự chứng minh fetch plan tốt.

### 40.7. “`isLoaded` có thể đếm SQL”

Không. Nó kiểm tra trạng thái loaded theo provider, không phải JDBC execution count.

### 40.8. “Chỉ cần giảm query count về một”

Không. Một JOIN rộng có thể trả số rows khổng lồ, tốn memory và phá pagination.

### 40.9. “Chỉ cần tăng batch size rất lớn”

Không. Batch quá lớn có thể chạm giới hạn parameters và tải dư dữ liệu; phải đo hiệu năng theo workload.

### 40.10. “`@Transactional(readOnly=true)` tránh N+1”

Không. Transaction mode không thay fetch plan.

### 40.11. “OSIV giải quyết lazy loading nên performance ổn”

Không. OSIV có thể khiến SQL ẩn phát tại web layer.

### 40.12. “Nếu controller không gọi getter thì không thể có N+1”

Sai. Mapper, serializer, logger, domain method, `@PostLoad` và debugger đều có thể đọc associations.

### 40.13. “Object graph loaded một cấp là toàn bộ graph loaded”

Sai. `order.lines` loaded không đồng nghĩa `line.product` loaded.

### 40.14. “`@ElementCollection` không phải entity nên không có N+1”

Sai. Đọc một collection table riêng cho từng owner có thể tạo N+1.

### 40.15. “JOIN FETCH collection và phân trang là mặc định an toàn”

Không. To-many fetch join có row multiplication và có thể làm phân trang sai/kém hiệu quả tùy provider.

---

## 41. Các bài tập thực hành

### Bài 1 — Dự đoán SQL collection

Có 20 orders, mỗi order có `lines` LAZY chưa loaded, không cache/batch. Code:

```java
List<PurchaseOrder> orders = repo.findAllOrders();

for (PurchaseOrder order : orders) {
    order.getLines().size();
}
```

**Câu hỏi:** mô hình SQL thường gặp?

**Lời giải:** một root SELECT và tới khoảng 20 secondary SELECT/count queries cho collection; mô hình **1 + N**. Extra-lazy/provider-specific optimization có thể thay SQL shape, nhưng vẫn có nguy cơ một query trên mỗi parent.

### Bài 2 — Đếm distinct Customers

Có 20 orders nhưng chỉ thuộc 3 customers. Cùng persistence context, mỗi order truy cập `customer.fullName` lần đầu; Customers LAZY, không được fetch ban đầu.

**Lời giải:** có thể là một root SELECT và khoảng 3 SELECTs cho 3 Customer identities, không nhất thiết 20 queries.

### Bài 3 — Nhận diện nested N+1

Code:

```java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        line.getProduct().getName();
    }
}
```

**Lời giải:** có thể N secondary collection queries theo orders và M secondary product queries theo products chưa loaded; công thức khái niệm `1 + N + M`.

### Bài 4 — JOIN thường có đủ không?

```sql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.fullName = :name
```

Sau query có cần SQL khi gọi `o.getCustomer().getFullName()`?

**Lời giải:** có thể có; JOIN thường không cam kết association initialized. Dùng `JOIN FETCH` nếu cần managed Customer, hoặc DTO projection nếu chỉ cần tên.

### Bài 5 — Vì sao `LEFT JOIN FETCH`?

Đơn #103 không có lines. Query cần mọi orders cùng lines.

**Lời giải:**

```sql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

LEFT JOIN giữ order không có children; INNER JOIN FETCH có thể loại nó.

### Bài 6 — Chỉ cần count

```java
for (PurchaseOrder order : orders) {
    dto.setLineCount(order.getLines().size());
}
```

**Lời giải:** cân nhắc query aggregate `COUNT(l) GROUP BY o.id` hoặc DTO projection; không tải toàn bộ lines khi chỉ cần số lượng.

### Bài 7 — Mapper bị nghi gây N+1

Service:

```java
return orders.stream().map(mapper::toDto).toList();
```

Trong mapper có `order.getCustomer().getFullName()` và `order.getLines()`.

**Lời giải:** quan sát SQL trước/sau mapper và liệt kê fetch paths; query root đơn giản chưa đủ để đáp ứng mapper. Chọn entity graph/fetch join/projection đúng nhu cầu.

### Bài 8 — Tại sao Hibernate statistics vẫn thấy nhiều SQL với `EAGER`?

**Lời giải:** EAGER có thể được provider đáp ứng bằng secondary SELECTs, không nhất thiết JOIN. Đánh giá query-level fetch plan.

### Bài 9 — Số SQL giảm nhưng request chậm hơn

Sau khi fetch join hai collections, query count giảm từ 200 xuống 1 nhưng rows tăng mạnh.

**Lời giải:** có thể là Cartesian multiplication. Đo SQL rows/bytes/heap và cân nhắc fetch theo bước/batch/projection.

### Bài 10 — Lazy initialization error ở REST controller

Service trả entity; JSON serializer đọc `lines` sau khi EntityManager đóng.

**Lời giải:** thiết kế response DTO hoặc fetch dữ liệu cần thiết trong boundary được kiểm soát. Đừng bật EAGER trên mọi relation như phản xạ mặc định.

### Bài 11 — Test không tái hiện N+1

Một test dùng cùng EntityManager sau khi seed dữ liệu; các Orders/Products đã managed.

**Lời giải:** dùng persistence context mới, kiểm soát L2 cache, tách seed khỏi phần đo và dùng fixture nhiều roots.

### Bài 12 — Có thể kết luận bằng `isLoaded(order,"lines") == true` rằng không có SQL mới không?

**Lời giải:** không. Nó cho biết loaded state, không phải số SQL trước đó hay nguồn dữ liệu (SQL/cache).

### Bài 13 — Inverse one-to-one phát SELECT ngay lúc load root

**Lời giải:** xem khả năng xác định tồn tại association, ownership/FK, optionality/enhancement; N+1 có thể xảy ra trước khi getter được gọi.

### Bài 14 — Phân trang 20 orders kèm lines

**Lời giải:** phân trang IDs trước; query thứ hai fetch collection cho tập IDs; xử lý thứ tự và consistency phù hợp.

### Bài 15 — N+1 từ logging

Log `order.toString()` trong vòng lặp; `toString` đọc `customer` và `lines`.

**Lời giải:** thay bằng log ID/basic fields và không để entity methods duyệt associations ngoài ý muốn.

---

## 42. Một kịch bản sửa N+1 từ đầu đến cuối

**Yêu cầu:** API trả các OrderSummary gồm order code, status, customer name và number of lines.

### 42.1. Bản đầu gây N+1

```java
public List<OrderSummaryDto> list() {
    List<PurchaseOrder> orders =
        em.createQuery(
            "SELECT o FROM PurchaseOrder o",
            PurchaseOrder.class
        ).getResultList();

    return orders.stream()
        .map(o -> new OrderSummaryDto(
            o.getCode(),
            o.getStatus(),
            o.getCustomer().getFullName(),
            o.getLines().size()
        ))
        .toList();
}
```

Những đường truy cập:

```text
o.customer.fullName
o.lines.size
```

Có thể sinh:

```text
1 SELECT orders
D SELECT customers
N SELECT/count lines
```

với D là số distinct customers chưa loaded, N là số order collections chưa loaded.

### 42.2. Hướng sửa bằng DTO aggregate

DTO:

```java
package com.example.nplusone;

public record OrderSummaryDto(
    String code,
    String status,
    String customerName,
    Long lineCount
) {}
```

JPQL:

```java
List<OrderSummaryDto> rows = em.createQuery(
    """
    SELECT NEW com.example.nplusone.OrderSummaryDto(
        o.code,
        o.status,
        c.fullName,
        COUNT(l)
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    LEFT JOIN o.lines l
    GROUP BY o.id, o.code, o.status, c.fullName
    ORDER BY o.id
    """,
    OrderSummaryDto.class
).getResultList();
```

Ý nghĩa:

- Lấy customer name từ JOIN.
- Tính count tại DB.
- Không dựng entity graph chỉ để map sang DTO.
- Không truy cập LAZY associations ở caller.

### 42.3. Lưu ý về SQL và GROUP BY

Một số RDBMS có khác biệt về biểu thức được phép trong `ORDER BY`/`GROUP BY` của aggregate projection và khả năng tối ưu dựa trên functional dependency.

Query JPQL ở trên dùng các fields rõ ràng trong `GROUP BY`. Nếu có yêu cầu portability giữa providers/DBs, hãy integration test cú pháp generated SQL và ordering theo target stack.

Nếu response cần **phân trang ổn định theo order ID**, aggregate query phải được kiểm tra semantics pagination; khi join nhiều collections sẽ phải xét row multiplication và count distinct phù hợp.

### 42.4. Hướng sửa nếu vẫn cần managed entity

Nếu use case cần sửa PurchaseOrder bằng domain method sau query, DTO có thể không phù hợp. Chọn:

- Query fetch `customer` và `lines` có chủ đích.
- Có thể dùng entity graph.
- Hoặc fetch to-one join + batch collections.

Thiết kế theo **mục đích sử dụng kết quả**, không áp dụng DTO như một quy tắc tuyệt đối.

---

## 43. Câu hỏi tự kiểm tra

**1. Dấu hiệu quan trọng nhất để xác nhận N+1 là gì?**

Một root query tạo N objects, sau đó việc truy cập các associations của chúng gây nhiều secondary queries lặp cấu trúc theo IDs.

**2. N+1 có thể nằm ngoài repository method không?**

Có. Mapper, service, serializer, logger, callback, view và GraphQL resolver đều có thể truy cập association.

**3. `@ManyToOne` mặc định LAZY hay EAGER?**

EAGER.

**4. `@OneToMany` mặc định LAZY hay EAGER?**

LAZY.

**5. Vì sao EAGER không bảo đảm tránh N+1?**

Provider có thể đáp ứng EAGER bằng secondary selects thay vì một JOIN.

**6. Vì sao LAZY không luôn gây N+1?**

Caller có thể không đọc association; hoặc data đã fetch/cache/batch.

**7. Số secondary SELECT ở to-one luôn bằng số orders không?**

Không. Có thể gần số distinct related entity IDs chưa loaded.

**8. Một order có 5 lines, có bao nhiêu query product?**

Phụ thuộc distinct products, loaded state, batching/cache và fetch plan; không nhất thiết đúng 5.

**9. `JOIN` khác `JOIN FETCH` thế nào?**

JOIN thường phục vụ lọc/projection; JOIN FETCH yêu cầu tải association.

**10. `LEFT JOIN FETCH` có ưu điểm nào so với INNER JOIN FETCH cho collection?**

Giữ cả parents có collection rỗng.

**11. `SELECT DISTINCT` có xóa hết SQL row multiplication không?**

Không chắc. Nó diễn đạt root uniqueness nhưng SQL vẫn có thể phải truyền nhiều joined rows để dựng collection.

**12. Vì sao không fetch join hai to-many collections mặc định?**

Nguy cơ Cartesian product, memory overhead, pagination khó và provider restrictions.

**13. Khi chỉ cần child count, nên tải collection hay tính aggregate?**

Thường nên dùng `COUNT`/projection tại DB.

**14. Entity graph có cam kết một SQL duy nhất không?**

Không. Nó là fetch plan, không bắt buộc provider dùng một SQL shape duy nhất.

**15. `@BatchSize` có phải chuẩn JPA không?**

Không; đây là Hibernate extension.

**16. PersistenceUnitUtil giúp kiểm tra gì?**

Trạng thái loaded của entity/attribute, không phải số SQL.

**17. Vì sao SQL log trên cold cache và warm cache khác nhau?**

Related entities/collections có thể đã được nạp trong context hoặc shared cache.

**18. Vì sao mapper code compile-time không bảo đảm tránh N+1?**

Nó vẫn có thể gọi getters LAZY trên từng entity.

**19. Trả entity trực tiếp ở REST controller gây những rủi ro gì?**

Lazy queries trong serializer, lỗi detached, vòng lặp graph và response vượt kích thước cần thiết.

**20. Khi fetch join collection cùng pagination phải chú ý gì?**

SQL rows bị nhân theo children, limit trên rows không tương đương limit root entities; có thể dùng hai bước page IDs rồi fetch.

**21. N+1 có thể ảnh hưởng tính nhất quán dữ liệu không?**

Có. Secondary SELECTs xảy ra muộn có thể nhìn thấy trạng thái khác theo transaction isolation.

**22. Có nên chữa N+1 chỉ bằng bật OSIV không?**

Không. Nó có thể cho phép SQL ẩn chạy trong web layer và che khuất vấn đề.

**23. Có phải mỗi lần gọi getter luôn tạo SQL không?**

Không; chỉ khi provider cần dữ liệu chưa có theo fetch strategy tại thời điểm ấy, hoặc có truy vấn chủ động trong getter.

**24. Khi có 101 SELECTs thay vì 1, kết luận gì trước khi sửa?**

Cần xác nhận 100 SELECTs phụ đến từ graph traversal nào, SQL pattern và dữ liệu liên quan; sau đó chọn fetch/DTO/batch phù hợp.

**25. Một benchmark tốt phải đo gì ngoài SQL count?**

Rows/bytes, SQL latency, tổng request latency, memory, cache, transaction duration và behavior trên workload thực.

---

## 44. Tổng kết: điều tra N+1 bằng đường đi trên đồ thị đối tượng

N+1 không được nhận diện chính xác chỉ bằng việc nhìn một annotation `@OneToMany(fetch = LAZY)` hay việc repository có một `SELECT`.

Hãy bắt đầu bằng **hành vi truy cập dữ liệu**:

```text
1. Query trả danh sách root entities.
   |
2. Code tiếp tục duyệt:
   order.customer.fullName
   order.lines[*].product.name
   |
3. Mỗi cạnh LAZY chưa loaded có thể yêu cầu SQL.
   |
4. Những SELECT tương tự lặp theo parent ID hoặc target ID.
   |
5. Tổng query tăng gần theo kích thước graph được dùng.
   |
6. Chẩn đoán và chọn fetch plan/projection/batching.
```

**Mô hình nhớ nhanh:**

\[
Q \approx Q_{\text{root}} +
Q_{\text{lazy collections}} +
Q_{\text{lazy to-one}} +
Q_{\text{nested associations}}
\]

Đây là mô hình lập luận, không phải công thức chính xác cho mọi provider/cache/workload.

Để xử lý:

- Dùng **`JOIN FETCH`** khi cần entity cùng association cụ thể.
- Dùng **Entity Graph** để khai báo fetch paths theo use case.
- Dùng **DTO projection/aggregate** nếu chỉ cần vài trường hoặc count.
- Dùng **batch/subselect fetching** khi thích hợp và provider hỗ trợ.
- Dùng **hai bước phân trang root IDs rồi fetch children** với collections lớn.
- Đo **SQL statements, rows và latency** thay vì chỉ số câu query.
- Tránh để **mapper, serializer, logging, callback** vô tình quyết định fetch plan.

**Câu hỏi review thiết thực nhất:**

> **Sau khi query trả các root entities, code sẽ lần lượt đọc những đường thuộc tính nào — và mỗi đường đó đã được tải theo kế hoạch, hay sẽ tạo một truy vấn mới cho từng object?**

Khi trả lời được câu hỏi này và kiểm chứng bằng SQL trace, bạn có thể phát hiện N+1 ngay từ cấu trúc code, kể cả khi hệ thống chưa có cảnh báo hiệu năng rõ ràng.

### Tài liệu tham khảo chính thức và chuyên sâu

- [Jakarta Persistence — các phiên bản đặc tả](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence 3.1 — đặc tả, phần Fetching và Fetch Joins](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Jakarta Persistence 3.2 — đặc tả](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Persistence API — `FetchType`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/fetchtype)
- [Jakarta Persistence API — `PersistenceUnitUtil`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/persistenceunitutil)
- [Jakarta Persistence API — `EntityGraph`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitygraph)
- [Jakarta Persistence API — `EntityManager`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
# Nhận diện N+1 từ hành vi truy cập đồ thị đối tượng

Một truy vấn JPA có thể trả về đúng dữ liệu, viết rất ngắn gọn và vẫn gây ra hàng trăm hoặc hàng nghìn lượt truy cập database. Vấn đề này thường được gọi là **N+1 query problem**. Nguyên nhân không chỉ nằm ở câu JPQL ban đầu mà còn nằm ở **hành vi ứng dụng truy cập các association trong đồ thị đối tượng sau khi nhận kết quả**.

Ví dụ:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b ORDER BY b.id",
    Book.class
).getResultList();

for (Book book : books) {
    System.out.println(book.getAuthor().getName());
}
```

Nếu truy vấn đầu tiên tải 100 sách nhưng chưa tải tác giả, vòng lặp có thể kích hoạt thêm nhiều SQL `SELECT` để tải tác giả. Trong trường hợp mỗi sách liên kết một tác giả khác nhau, có thể xảy ra:

```text
1 SELECT lấy 100 sách
100 SELECT lấy tác giả của từng sách
----------------------------------
101 SELECT
```

Đó là một biểu hiện của N+1: **một truy vấn ban đầu cộng thêm nhiều truy vấn phát sinh khi duyệt kết quả và truy cập quan hệ**.

Tuy nhiên, **không nên giả định mọi vòng lặp truy cập quan hệ đều tạo đúng 1+N SQL**. Persistence context identity map, cache, batch fetching, fetch join, entity graph, dữ liệu dùng chung và provider-specific optimization có thể khiến số câu SQL ít hơn hoặc khác. Điều quan trọng của bài này là học cách **quan sát đúng hành vi truy cập object graph**, khoanh vùng vị trí gây query, đo và sửa có mục tiêu.

Bài **“Nhận diện N+1 từ hành vi truy cập đồ thị đối tượng”** thuộc chương **Kế hoạch tải** (*Fetch Plan*) của **Data Persistence Relational Access ORM JPA**. Chúng ta sẽ phân tích quan hệ giữa fetch strategy và access pattern, cách đọc SQL log, các trường hợp to-one/to-many, tác động của mapping EAGER/LAZY, serializer, transaction, giải pháp bằng fetch join, entity graph, projection, batch fetching và cách viết integration test để phát hiện hồi quy.

Ví dụ dùng Jakarta Persistence (`jakarta.persistence`) và Java 17+. Một số công cụ đo SQL và annotation tối ưu được nêu rõ là tính năng của Hibernate hoặc Spring Data JPA, không phải API JPA chuẩn.

---

## 1. N+1 là vấn đề của đường đi khi truy cập dữ liệu

Xét các entity:

```text
Author 1 ──┐
           ├─ Book 1
           └─ Book 2

Author 2 ──┐
           ├─ Book 3
           └─ Book 4

Author 3 ───── Book 5
```

Một thao tác nghiệp vụ:

```java
List<Book> books = repository.findAllBooks();

for (Book book : books) {
    String authorName = book.getAuthor().getName();
    render(book.getTitle(), authorName);
}
```

Ứng dụng trông như đang thao tác với những Java objects. Nhưng property `book.author` có thể là lazy association chưa được khởi tạo. Khi gọi `getName()`, provider phải tải dữ liệu của Author nếu chưa có trong persistence context/cache.

Có thể xảy ra:

```text
T0: SELECT * FROM books
T1: SELECT * FROM authors WHERE id = 1
T2: SELECT * FROM authors WHERE id = 2
T3: SELECT * FROM authors WHERE id = 3
```

Ở đây 5 Book chỉ có 3 Author khác nhau, nên số secondary SELECT có thể là 3 chứ không phải 5. Đây vẫn là **mẫu query tăng theo số association cần khởi tạo**, thay vì một kế hoạch tải có chủ đích.

**N+1 được nhận diện qua số lần đi database tăng theo kích thước đồ thị và hành vi traversal**, không phải chỉ qua công thức đúng 101 câu lệnh.

### Vì sao gọi là N+1?

Trong ví dụ lý tưởng:

- `1`: truy vấn lấy N root entities.
- `N`: mỗi root gây một query phụ lấy association.

Nhưng thực tế có thể có:

- `1 + K`, với `K` là số target khác nhau.
- `1 + ceil(K / batchSize)` nếu provider batch fetch.
- `1 + N + M` khi code truy cập nhiều tầng quan hệ.
- Hàng trăm query do collection, to-one, nested traversal và cache state khác nhau.

Vì thế công thức N+1 là **tên của dạng hiệu năng kém**, không phải một cam kết về con số SQL chính xác.

## 2. Mô hình entity minh họa

Ta dùng `Author`, `Book` và `Review`.

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "authors")
public class Author {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Author() {}

    public Author(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    @OneToMany(mappedBy = "book", fetch = FetchType.LAZY)
    private List<Review> reviews = new ArrayList<>();

    protected Book() {}

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public BigDecimal getPrice() { return price; }
    public Author getAuthor() { return author; }
    public List<Review> getReviews() { return reviews; }
}

@Entity
@Table(name = "reviews")
public class Review {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "book_id", nullable = false)
    private Book book;

    @Column(nullable = false)
    private int rating;

    protected Review() {}

    public int getRating() { return rating; }
}
```

Đoạn code lược bỏ constructor và các helper khởi tạo dữ liệu ở Book/Review để tập trung vào fetch plan. Trong project chạy thật cần khai báo constructor nghiệp vụ, đồng bộ hai phía của quan hệ khi sửa association, transaction và schema tương thích.

Schema ý tưởng:

```sql
CREATE TABLE authors (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(14, 2) NOT NULL,
    author_id BIGINT NOT NULL REFERENCES authors(id)
);

CREATE TABLE reviews (
    id BIGINT PRIMARY KEY,
    book_id BIGINT NOT NULL REFERENCES books(id),
    rating INTEGER NOT NULL
);
```

Ở sơ đồ này, một Book có một Author và nhiều Reviews. Khi query Book, `author` và `reviews` là hai hướng traversal có thể kích hoạt tải dữ liệu bổ sung.

## 3. FetchType.LAZY và EAGER không phải số câu SQL

JPA định nghĩa:

```java
FetchType.LAZY
FetchType.EAGER
```

Khái quát:

- **LAZY**: provider được phép trì hoãn tải association cho tới khi ứng dụng cần; trong nhiều trường hợp là hint, mức độ triển khai phụ thuộc mapping/provider, đặc biệt với to-one enhancement/proxy.
- **EAGER**: provider phải bảo đảm association được tải theo ngữ nghĩa eager, nhưng **không bắt buộc dùng một SQL JOIN duy nhất**.

Vì vậy:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Author author;
```

**không bảo đảm** JPQL:

```java
SELECT b FROM Book b
```

chỉ chạy một SQL với JOIN. Provider có thể thực hiện một SELECT lấy Books rồi các secondary SELECT lấy Authors để đáp ứng yêu cầu eager. Khi danh sách dài, vẫn có nguy cơ N+1.

### Những mặc định dễ bị bỏ quên

| Annotation | Fetch mặc định theo JPA |
| --- | --- |
| `@ManyToOne` | EAGER |
| `@OneToOne` | EAGER |
| `@OneToMany` | LAZY |
| `@ManyToMany` | LAZY |

Mặc định EAGER cho to-one là một trong các nguyên nhân khiến ứng dụng tưởng không truy cập quan hệ mà SQL vẫn tăng khi load root entities.

Ví dụ:

```java
@ManyToOne
private Author author; // EAGER theo default.
```

Nếu query lấy 50 Book mà provider chọn secondary selects để tải Authors, N+1 có thể xuất hiện ngay khi `getResultList()` hoàn tất, chưa cần vòng lặp `getAuthor().getName()`.

**Cách nhận diện N+1 luôn dựa trên SQL thực tế, không suy từ annotation một cách máy móc.**

## 4. Truy vấn root có thể nhanh, truy cập association mới đắt

Đây là mẫu N+1 do lazy loading:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b ORDER BY b.id",
    Book.class
).getResultList();

System.out.println("Loaded " + books.size() + " books");

// Secondary queries có thể chỉ bắt đầu ở đây:
for (Book book : books) {
    System.out.println(book.getAuthor().getName());
}
```

Mô hình log:

```sql
SELECT b.id, b.title, b.price, b.author_id
FROM books b
ORDER BY b.id;

SELECT a.id, a.name FROM authors a WHERE a.id = ?;
SELECT a.id, a.name FROM authors a WHERE a.id = ?;
SELECT a.id, a.name FROM authors a WHERE a.id = ?;
-- Các SELECT tương tự...
```

Đừng chỉ đo thời gian của `getResultList()`:

```java
long start = System.nanoTime();
List<Book> books = query.getResultList();
long queryMillis = ...;
```

Nếu business loop chạy sau đó mới lazy-load, phép đo query ban đầu không bao gồm phần lớn chi phí. Cần đo **toàn bộ use case** từ load đến render/DTO conversion/serialization.

## 5. N+1 trên collection: một SELECT cho mỗi parent

Một ví dụ khác:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b ORDER BY b.id",
    Book.class
).getResultList();

for (Book book : books) {
    System.out.println(
        book.getTitle() + ": " + book.getReviews().size()
    );
}
```

Nếu collection `reviews` chưa được khởi tạo, provider có thể gửi:

```sql
SELECT * FROM books ORDER BY id;

SELECT * FROM reviews WHERE book_id = ?;  -- Book 1
SELECT * FROM reviews WHERE book_id = ?;  -- Book 2
SELECT * FROM reviews WHERE book_id = ?;  -- Book 3
-- ...
```

Tại sao chỉ gọi `size()` mà vẫn query?

Với một persistent collection lazy, provider cần biết số phần tử. Nó có thể:

- Tải collection rồi lấy kích thước.
- Dùng count query riêng trong một số chế độ/provider extensions.
- Đã có dữ liệu trong cache/context nên không cần query.

Không được suy rằng `size()` luôn chỉ đọc một con số đã có sẵn trong heap, cũng không suy rằng nó luôn load toàn bộ collection. Hãy xem mapping và SQL log.

### Hidden traversal trong business logic

N+1 có thể ẩn sau:

```java
book.getReviews().stream()
    .filter(review -> review.getRating() >= 4)
    .count();
```

Nhìn như Java Stream, nhưng nó có thể buộc khởi tạo collection Reviews cho từng Book, tạo hàng trăm SELECT.

## 6. N+1 nhiều tầng (nested graph traversal)

Một service hiển thị danh sách Book, Author và Review's User:

```java
for (Book book : books) {
    String author = book.getAuthor().getName();

    for (Review review : book.getReviews()) {
        String reviewer = review.getUser().getDisplayName();
        render(book, author, reviewer);
    }
}
```

Nếu các association chưa được tải và mỗi bước phát query riêng:

```text
1 query lấy Books
+ query tải Authors
+ query tải Reviews cho từng Book
+ query tải Users cho từng Review
--------------------------------
Có thể tăng mạnh theo kích thước nhiều cấp của graph.
```

Đó không chỉ là một N+1 đơn lẻ. Có thể có **nhiều chuỗi N+1 lồng nhau**.

Ví dụ 100 Book, mỗi Book có 10 Review:

- 1 query lấy Books.
- Tới 100 query lấy Reviews nếu không batching.
- Tới 1.000 query lấy User nếu mỗi Review có User khác nhau và chưa cache.
- Thêm truy vấn Author nếu chưa tải.

Số SQL có thể thành hàng nghìn. Khi phát hiện một N+1, hãy xem tiếp **những association nào trong vòng lặp thứ hai/thứ ba đang được truy cập** thay vì sửa riêng một join rồi dừng.

## 7. N+1 không nhất thiết nằm trong code repository

Các vị trí thường gây lazy traversal:

- Service chuyển entity thành DTO.
- Controller xây response.
- JSON serializer đọc getters.
- Template engine render view.
- `toString()`, `equals()`, `hashCode()` do ứng dụng tự viết.
- Log debug cả object graph.
- Validation hoặc business rule duyệt collections.
- GraphQL resolver đọc từng field.
- Mapping library tự động truy cập nested properties.
- Unit-of-work logic tính tổng/kiểm tra trạng thái sau truy vấn.
- Debugger/IDE hiển thị property bằng cách gọi getters (tùy cấu hình).

Ví dụ:

```java
public record BookDto(Long id, String title, String authorName) {}

public BookDto map(Book book) {
    return new BookDto(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName()
    );
}
```

Repository có thể chỉ chạy một SELECT để lấy Book. Nhưng:

```java
books.stream().map(this::map).toList();
```

gây thêm các SELECT tới Authors. Nếu chỉ đo repository method mà không đo DTO mapping, N+1 bị bỏ sót.

## 8. Persistence context và cache có thể che giấu N+1

Giả sử 100 Books cùng trỏ một Author:

```text
Book 1 ─┐
Book 2 ─┤
...     ├── Author A
Book100 ┘
```

Khi truy cập Book 1, Author A được load. Các Book sau có thể dùng cùng managed instance của Author A trong persistence context, không cần 99 SQL SELECT nữa.

Kết quả có thể là:

```text
1 SELECT Books + 1 SELECT Author
```

Vẫn có lazy access nhưng không thành một N+1 nặng ở fixture này.

Nếu test chỉ có một Author dùng chung, test rất dễ **xanh giả**.

### Một fixture tốt hơn

Tạo ít nhất:

- N Book với **N Author khác nhau**.
- Một vài Book dùng chung Author để quan sát identity map.
- Books có số Reviews khác nhau.
- Một vài Book không có Review.
- Associations không được load trong fixture persistence context khi chạy test.

Sau khi seed dữ liệu, hãy **commit và đóng EntityManager**, rồi thực hiện bài test với persistence context mới để không tận dụng trạng thái đã load sẵn trong quá trình seed.

### Second-level cache

Shared cache có thể giảm truy vấn trong lần chạy thứ hai nhưng không bảo đảm vấn đề đã được giải quyết. Nếu SQL log khác nhau giữa chạy đầu và chạy lại, xem:

- First-level context còn dữ liệu không?
- Second-level cache đã warm chưa?
- Query cache có bật không?
- Bài test có reset/evict cache một cách có mục đích không?
- Có giống chính sách cache ở production không?

**Một fixture nhỏ, một context đã warm và một lần chạy duy nhất thường không đủ để phát hiện N+1.**

## 9. Làm thế nào quan sát SQL trong thực tế?

Cách đơn giản là bật SQL logging của JPA provider/ORM và chạy một use case.

Với Hibernate, những cấu hình quen thuộc có thể là:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.generate_statistics=true
```

Trong ứng dụng Spring Boot dùng Hibernate, có thể cấu hình logger SQL và binding tương ứng với phiên bản framework/provider, ví dụ Hibernate 6 thường có:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Đây là cấu hình **phụ thuộc provider/version**, không phải thuộc tính chuẩn áp dụng cho mọi JPA implementation. Không nên bật trace giá trị bind chứa dữ liệu nhạy cảm trong production.

### Dấu hiệu điển hình

1. Một SELECT chính lấy danh sách root.
2. Nhiều SELECT gần giống nhau chỉ khác điều kiện `WHERE author_id = ?` hoặc `WHERE book_id = ?`.
3. Số SELECT tăng khi page size hoặc số root records tăng.
4. SELECT phụ xuất hiện sau khi code bắt đầu truy cập getter của association.
5. Truy vấn ở DB mỗi cái khá nhanh, nhưng tổng số round trip lớn.

Ví dụ:

```sql
SELECT b.id, b.title, b.author_id FROM books b LIMIT 100;

SELECT a.id, a.name FROM authors a WHERE a.id = 11;
SELECT a.id, a.name FROM authors a WHERE a.id = 12;
SELECT a.id, a.name FROM authors a WHERE a.id = 13;
...
```

Cũng cần biết: N+1 có thể gây trễ mạnh hơn khi DB ở khác máy/vùng mạng, dù mỗi query chỉ mất vài mili-giây. Chi phí network latency, connection use và ORM hydration cộng dồn đáng kể.

## 10. Đếm statement bằng statistics thay vì nhìn bằng mắt

Nếu dự án dùng Hibernate, có thể dùng thống kê truy cập JDBC như:

```java
SessionFactory sessionFactory = emf.unwrap(SessionFactory.class);
Statistics statistics = sessionFactory.getStatistics();

statistics.setStatisticsEnabled(true);
statistics.clear();

runBusinessUseCase();

long statements = statistics.getPrepareStatementCount();
System.out.println("Prepared statements: " + statements);
```

Đây là **Hibernate API extension** (`org.hibernate.SessionFactory` và `org.hibernate.stat.Statistics`), không thuộc `jakarta.persistence` chuẩn. Ví dụ cần import đúng phiên bản Hibernate và transaction/context được quản lý phù hợp.

Một số lưu ý:

- `getPrepareStatementCount()` là chỉ số số prepared statements theo thống kê Hibernate, không phải phép phân loại “số SELECT N+1” tự động.
- Các thao tác khác trong cùng session/factory có thể ảnh hưởng số liệu.
- Chạy test song song trên cùng `SessionFactory` có thể làm statistics bị nhiễu.
- Fixture setup, flush và truy vấn phụ khác phải được loại khỏi cửa sổ đo.
- Provider cache và batching có thể thay đổi số statement.
- Nếu muốn đếm chính xác SQL SELECT, dùng SQL datasource proxy/test instrumentation phù hợp với transaction.

Chỉ số là bằng chứng hữu ích, nhưng cần gắn với **đường code và truy vấn thực tế**.

## 11. So sánh khi N thay đổi để nhận diện xu hướng

Một cách mạnh hơn việc đếm ở một kích thước fixture là chạy use case với các kích thước khác nhau:

| Số Book | Truy vấn root | Secondary queries nếu mỗi Book có Author riêng, chưa batching/cache | Tổng gần đúng |
| ---: | ---: | ---: | ---: |
| 5 | 1 | 5 | 6 |
| 20 | 1 | 20 | 21 |
| 50 | 1 | 50 | 51 |
| 100 | 1 | 100 | 101 |

Đây là **kịch bản minh họa chưa tối ưu**, không phải con số provider nào cũng bắt buộc phát.

Nếu số query tăng gần tuyến tính theo số Book, đó là dấu hiệu N+1. Nếu chỉ 1–3 query dù N tăng từ 10 lên 100, rất có thể fetch plan/batching/projection đang giới hạn round trips tốt hơn.

### Đừng nhầm chi phí một query lớn với việc không có vấn đề

Một `JOIN FETCH` có thể giảm số query xuống 1 nhưng làm result set tăng cực lớn vì nhân bản hàng theo collection. Chỉ tối ưu số query **mà không đo số hàng/băng thông/bộ nhớ** cũng có thể dẫn đến hiệu năng kém.

Vì vậy hãy xem đồng thời:

- Số round trips.
- Số hàng DB trả.
- Thời gian thực thi.
- Data bytes và object allocations.
- Số entity/collection được load.
- Độ dài transaction và mức giữ connection.

---

## 12. Giải pháp 1: JOIN FETCH association to-one

Nếu luôn cần Author khi hiển thị Book, JPQL có thể mô tả fetch plan ngay tại query:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b " +
    "JOIN FETCH b.author " +
    "ORDER BY b.id",
    Book.class
).getResultList();

for (Book book : books) {
    System.out.println(book.getAuthor().getName());
}
```

Ý nghĩa:

- `JOIN` liên kết bảng/association.
- `FETCH` yêu cầu tải association như một phần fetch plan.
- Provider có thể sử dụng một join SQL phù hợp để nạp Book và Author.

Đối với nhiều-to-one/to-one, fetch join thường là cách hiệu quả để tránh N+1 khi phần lớn root records cần cùng association.

### Khi nào LEFT JOIN FETCH?

Nếu `Book.author` là association tùy chọn:

```java
"SELECT b FROM Book b LEFT JOIN FETCH b.author"
```

có thể giữ Book ngay cả khi không có Author (tùy WHERE). Với `JOIN FETCH` inner, Book thiếu Author có thể bị loại khỏi kết quả; cần chọn đúng semantics nghiệp vụ.

### Điều kiện lọc và fetch join

`JOIN FETCH` không phải phương tiện thay thế mọi điều kiện lọc. Khi cần lọc theo Author, có thể dùng normal JOIN để diễn đạt predicate và fetch plan riêng. Kiểm thử SQL do provider tạo ra, đặc biệt tránh join trùng không cần thiết.

### Không fetch mọi quan hệ chỉ vì có thể

Nếu màn hình chỉ cần title/price, fetch Author là dữ liệu thừa. Fetch plan nên phù hợp **use case cụ thể**.

## 13. Giải pháp 2: LEFT JOIN FETCH collection, nhưng coi chừng hàng nhân bản

Truy vấn:

```java
List<Book> books = em.createQuery(
    "SELECT DISTINCT b FROM Book b " +
    "LEFT JOIN FETCH b.reviews " +
    "ORDER BY b.id",
    Book.class
).getResultList();
```

Mục tiêu là tải Reviews cùng Books, tránh một SELECT Reviews riêng cho từng Book.

Nhưng với một-to-many:

```text
Book A có 20 Reviews
Book B có 10 Reviews
Book C có  0 Reviews
```

SQL join có thể trả khoảng 31 hàng, dù chỉ có 3 Book root (LEFT JOIN tạo một hàng cho Book C không có Review). Nếu Book có 100 Reviews, số hàng SQL có thể rất lớn.

### DISTINCT có làm giảm mọi chi phí không?

`SELECT DISTINCT b` trong JPQL biểu đạt loại trùng root results theo semantics provider, nhưng không nhất thiết giảm số hàng vật lý DB truyền về như ta tưởng khi collection columns khác nhau.

Đừng kết luận “đã thêm DISTINCT thì JOIN FETCH collection sẽ luôn nhanh”.

### Pagination + collection fetch join

Đoạn nguy hiểm:

```java
em.createQuery(
    "SELECT b FROM Book b " +
    "LEFT JOIN FETCH b.reviews ORDER BY b.id",
    Book.class
).setMaxResults(20)
 .getResultList();
```

Vì mỗi Book có thể nhân thành nhiều SQL rows, provider khó giới hạn chính xác 20 root Book chỉ bằng một SQL LIMIT trên join result. Một số provider có thể paginating in memory, cảnh báo hoặc từ chối tùy config/version.

Nếu mục tiêu là phân trang root entities, thường cần chiến lược **two-phase pagination**: lấy IDs của page trước, sau đó fetch collections cho đúng IDs.

## 14. Giải pháp 3: EntityGraph cho từng use case

JPA hỗ trợ `EntityGraph` để mô tả những attribute cần tải mà không phải ghi FETCH JOIN trực tiếp trong JPQL.

Ví dụ:

```java
EntityGraph<Book> graph = em.createEntityGraph(Book.class);
graph.addAttributeNodes("author");

TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b ORDER BY b.id",
    Book.class
);

query.setHint("jakarta.persistence.fetchgraph", graph);

List<Book> books = query.getResultList();
```

Với JPA cũ dùng `javax.persistence.fetchgraph`. Chọn namespace hint theo Jakarta/JPA version đang dùng.

### Fetch graph và load graph

- **`fetchgraph`**: diễn đạt những attribute cần tải eager theo graph; chi tiết mặc định/primary-key/version và các quy tắc của specification cần hiểu theo phiên bản.
- **`loadgraph`**: các attribute trong graph được yêu cầu tải; những attribute khác theo fetch mapping mặc định của entity.

Ví dụ:

```java
query.setHint("jakarta.persistence.loadgraph", graph);
```

Trong thực tế có provider vẫn tải eager associations ngoài graph vì ràng buộc chuẩn/hành vi implementation; không nên tin rằng graph luôn tuyệt đối ngăn mọi tải dữ liệu khác.

### EntityGraph có bảo đảm một SQL không?

Không. EntityGraph diễn đạt **nhu cầu fetch**, còn provider quyết định cơ chế join/batch/secondary selects. Nó có thể giải quyết N+1 trong use case cụ thể nhưng phải đo query count.

### Named EntityGraph

Có thể khai báo trên entity:

```java
@NamedEntityGraph(
    name = "Book.withAuthor",
    attributeNodes = @NamedAttributeNode("author")
)
@Entity
public class Book {
    // ...
}
```

Rồi dùng graph qua `em.getEntityGraph("Book.withAuthor")`.

Graph hữu ích khi nhiều truy vấn cần cùng fetch shape nhưng không muốn lặp `JOIN FETCH` trong JPQL.

## 15. Spring Data JPA: @EntityGraph không phải JPA annotation chuẩn

Nếu dùng Spring Data JPA:

```java
public interface BookRepository
        extends JpaRepository<Book, Long> {

    @EntityGraph(attributePaths = "author")
    @Query("SELECT b FROM Book b ORDER BY b.id")
    List<Book> findAllWithAuthor();
}
```

`@EntityGraph` ở repository là tiện ích của **Spring Data JPA**, không phải annotation cùng vai trò như `@NamedEntityGraph` chuẩn được khai báo trên JPA entity.

Nó có thể giúp dịch fetch requirement vào query hint và tránh N+1 khi chuyển Book sang DTO có Author name.

Tuy nhiên, với pageable result hoặc collection graph, vẫn phải xét count query, join multiplication, memory và SQL thực tế. Không phải cứ thêm annotation là mọi access pattern được tối ưu.

## 16. Giải pháp 4: DTO projection — tránh tạo graph không cần thiết

Nếu response chỉ cần:

```json
{
  "id": 101,
  "title": "JPA căn bản",
  "authorName": "An"
}
```

không nhất thiết load `Book` rồi truy cập `book.author`.

Định nghĩa DTO:

```java
public record BookCard(
    Long id,
    String title,
    String authorName
) {}
```

JPQL constructor projection:

```java
List<BookCard> cards = em.createQuery(
    "SELECT NEW com.example.dto.BookCard(" +
    "b.id, b.title, a.name) " +
    "FROM Book b JOIN b.author a " +
    "ORDER BY b.id",
    BookCard.class
).getResultList();
```

Trong một query, database trả đúng các cột cần cho mỗi `BookCard`, thay vì tạo managed Book/Author graph rồi lặp getter để biến thành DTO.

Ưu điểm:

- Giảm managed entity hydration khi chỉ đọc.
- Tránh lazy association traversal trong mapper.
- DTO tách khỏi persistence context.
- Dễ kiểm soát số cột và dữ liệu trả API.
- Có thể kết hợp `setFirstResult`/`setMaxResults` khi phù hợp.

Nhưng nếu DTO chứa một danh sách Reviews của mỗi Book, constructor projection đơn giản không tự tổng hợp collection. Khi đó có thể dùng hai query theo batch IDs rồi gộp trong bộ nhớ, hoặc DB aggregation phù hợp.

### Đẩy dữ liệu cần thiết vào query

Code có N+1:

```java
books.stream()
    .map(b -> new BookCard(
        b.getId(),
        b.getTitle(),
        b.getAuthor().getName()
    ))
    .toList();
```

Code chủ động chọn giá trị:

```java
SELECT NEW ...BookCard(b.id, b.title, b.author.name)
FROM Book b
```

Trong phương án DTO, provider có thể xây SQL join để lấy author name theo mapping, thay vì tạo từng Author lazy proxy rồi truy cập sau query.

## 17. Giải pháp 5: Batch fetching provider-specific

Khi không muốn/không thể join fetch collection, một số provider hỗ trợ batch-fetch các lazy associations.

Với Hibernate, có thể gặp cấu hình:

```properties
hibernate.default_batch_fetch_size=32
```

hoặc annotation mở rộng:

```java
@BatchSize(size = 32)
@OneToMany(mappedBy = "book")
private List<Review> reviews;
```

`@BatchSize` là **Hibernate-specific**, không phải annotation JPA chuẩn. Khả năng áp dụng cho entity/collection, số câu SQL, hiệu ứng cache và cách batch dựa vào provider/version.

Ý tưởng:

```text
Không batching:
  SELECT reviews WHERE book_id = 1
  SELECT reviews WHERE book_id = 2
  ...
  SELECT reviews WHERE book_id = 100

Batch size 32 (minh họa):
  SELECT reviews WHERE book_id IN (1, 2, ..., 32)
  SELECT reviews WHERE book_id IN (33, ..., 64)
  SELECT reviews WHERE book_id IN (65, ..., 96)
  SELECT reviews WHERE book_id IN (97, ..., 100)
```

Nhờ đó secondary SELECT có thể giảm đáng kể, dù chưa chắc còn đúng 4 câu do provider chọn chiến lược khác.

### Trade-off

- Batch fetch có thể tải thêm association chưa thật sự cần ngay.
- Mệnh đề IN lớn có giới hạn tham số SQL của một số database.
- Batch size quá lớn gây lượng dữ liệu/object lớn.
- Cache và số entity targets khác nhau tác động kết quả.
- Không thay thế tốt cho một DTO projection chỉ cần vài cột.

Batch fetching là một công cụ tuning cần đo, không phải giải pháp luôn đúng cho mọi association.

## 18. Subselect fetching và những extension khác

Một số Hibernate mapping hỗ trợ subselect fetching cho collections. Ý tưởng là khi một collection của nhóm parent được khởi tạo, provider có thể tải các collections khác trong nhóm bằng một subselect thay vì từng `book_id` riêng.

Ưu điểm có thể giảm N+1. Nhược điểm:

- Phụ thuộc Hibernate.
- SQL có thể tải nhiều collection rows cùng lúc.
- Chi phí bộ nhớ phụ thuộc kích thước tập parent/child.
- Dễ bị ảnh hưởng khi query parent có filter/pagination phức tạp.

Vì vậy nếu sử dụng `@Fetch(FetchMode.SUBSELECT)` hoặc API tương tự, cần ghi rõ provider và test đúng access pattern. Không viết tài liệu/dự án coi nó là một cấu hình chuẩn portable của Jakarta Persistence.

## 19. Không luôn giải quyết bằng cách đổi LAZY thành EAGER

Giả sử gặp N+1 khi gọi `book.getAuthor().getName()`. Một phản ứng thường thấy là:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Author author;
```

Nhưng:

1. EAGER không bảo đảm SQL JOIN duy nhất.
2. Mọi use case tải Book đều có thể bị buộc tải Author, kể cả nơi không cần.
3. Một graph nhiều EAGER associations dễ phát sinh các secondary selects phức tạp.
4. Nhiều collection EAGER có thể làm dữ liệu rất lớn.
5. Mapping cố định không thể diễn đạt chính xác nhu cầu khác nhau của từng API endpoint.

Nếu ứng dụng có hai use case:

- Trang danh sách Book chỉ cần title và giá.
- Trang chi tiết cần Author và Reviews.

thì một mapping EAGER chung cho mọi nơi hiếm khi là cách tối ưu nhất.

**Chiến lược tốt là mặc định có thể trì hoãn hợp lý và xác định fetch plan theo từng truy vấn/use case, đồng thời đo SQL thực tế.**

## 20. Không phải mọi trường hợp đều cần fetch toàn bộ collection

Trang danh sách có thể chỉ cần:

```text
Book.title + số Reviews
```

Nếu load toàn bộ Reviews chỉ để gọi `getReviews().size()`, có thể tốn nhiều dữ liệu.

Một query aggregate:

```java
List<Object[]> rows = em.createQuery(
    "SELECT b.id, b.title, COUNT(r) " +
    "FROM Book b LEFT JOIN b.reviews r " +
    "GROUP BY b.id, b.title " +
    "ORDER BY b.id",
    Object[].class
).getResultList();
```

hoặc DTO projection với `COUNT`:

```java
public record BookReviewCount(
    Long id,
    String title,
    Long reviewCount
) {}

List<BookReviewCount> cards = em.createQuery(
    "SELECT NEW com.example.dto.BookReviewCount(" +
    "b.id, b.title, COUNT(r)) " +
    "FROM Book b LEFT JOIN b.reviews r " +
    "GROUP BY b.id, b.title " +
    "ORDER BY b.id",
    BookReviewCount.class
).getResultList();
```

Điều này có thể tránh N lần khởi tạo `reviews` và không phải tải Review objects.

Cần kiểm tra grouping/dialect và hiệu năng. Nếu trang có 100.000 Books, vẫn cần phân trang và index phù hợp.

**Tối ưu không chỉ là tải association nhanh hơn, mà còn là không tải association khi chỉ cần một phép tính từ DB.**

## 21. Phân trang root IDs rồi fetch associations theo batch

Một vấn đề điển hình: muốn lấy trang 20 Book cùng Reviews, nhưng collection fetch join không phân trang tốt.

Một chiến lược hai bước:

### Bước 1: lấy IDs của trang

```java
List<Long> ids = em.createQuery(
    "SELECT b.id FROM Book b " +
    "WHERE b.price >= :minPrice " +
    "ORDER BY b.id",
    Long.class
).setParameter("minPrice", new BigDecimal("100000"))
 .setFirstResult(page * size)
 .setMaxResults(size)
 .getResultList();
```

### Bước 2: fetch Books và Reviews cho những IDs

```java
List<Book> books = ids.isEmpty()
    ? List.of()
    : em.createQuery(
        "SELECT DISTINCT b FROM Book b " +
        "LEFT JOIN FETCH b.reviews " +
        "WHERE b.id IN :ids",
        Book.class
      ).setParameter("ids", ids)
       .getResultList();
```

### Bước 3: phục hồi thứ tự page

Không được giả định query thứ hai tự trả kết quả theo thứ tự `ids` trong Java list. Có thể tạo map theo ID và reorder:

```java
Map<Long, Book> byId = books.stream()
    .collect(Collectors.toMap(Book::getId, Function.identity()));

List<Book> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
```

Nếu query dữ liệu có filter/version/permission thay đổi giữa hai bước, một số IDs có thể không còn tương ứng; ứng dụng phải xác định consistency policy.

### Trade-off

- Thường cần hai SQL, nhưng số query có thể ổn định theo page.
- Có thể nhân SQL rows theo số Reviews.
- Phải xử lý thứ tự, duplicates, empty ID list.
- Nếu cần thêm nhiều collections, tránh fetch nhiều bag collections cùng lúc trên Hibernate mà không hiểu giới hạn/provider.
- Khi transaction khác ghi đồng thời, cần quy tắc về snapshot/isolation hoặc chấp nhận eventual consistency ở màn hình.

Đây là cách đối phó N+1 và pagination thường tốt hơn việc fetch toàn graph rồi cắt trang ở Java.

## 22. N+1 khi dùng Spring Data repository

Một repository có:

```java
Page<Book> findByPublishedTrue(Pageable pageable);
```

Query dữ liệu của page có thể chỉ tải Books. Service:

```java
Page<BookCard> cards = page.map(book ->
    new BookCard(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName()
    )
);
```

có thể tạo N+1 trên số Books của trang.

Có thể giải quyết bằng:

- Repository method dùng `@EntityGraph(attributePaths = "author")`.
- JPQL constructor projection thẳng sang BookCard.
- JPQL fetch join to-one với pagination phù hợp.
- Spring Data projection theo khả năng framework.
- Batch fetching nếu có nhu cầu graph đa use case.

**Một Page<Book> không tự bảo đảm access associations hiệu quả**, dù page size chỉ 20. 20 + 1 query mỗi request vẫn có thể là gánh nặng khi lưu lượng lớn.

## 23. N+1 trong GraphQL resolver

GraphQL có trường hợp điển hình:

```text
Query: books { id title author { name } }
```

Nếu resolver `books` trả 100 Books và resolver `author` gọi repository lấy Author riêng cho từng Book:

```text
1 query lấy Books
100 calls/load Authors
```

Ngay cả khi không dùng lazy JPA association, cách tổ chức resolver cũng có thể tạo N+1 ở tầng ứng dụng.

Các giải pháp:

- Batch loader/DataLoader gom author IDs rồi truy vấn theo `IN`.
- Projection query lấy đúng graph field cần thiết.
- EntityGraph/fetch join nếu resolver và JPA persistence context phù hợp.
- Cache per request để tránh lấy lặp cùng author.

Vấn đề N+1 là **access pattern**, nên nó có thể xuất hiện ở GraphQL, REST DTO mapping, server-side rendering hoặc một service batch, không chỉ một vòng lặp `book.getAuthor()`.

## 24. JSON serialization có thể gây N+1 và LazyInitializationException

Ví dụ controller trả thẳng entities:

```java
@GetMapping("/books")
public List<Book> books() {
    return bookRepository.findAll();
}
```

JSON serializer có thể gọi:

```java
book.getAuthor().getName();
book.getReviews();
```

để serialize nested fields. Nếu persistence context còn mở, nó có thể kích hoạt N+1. Nếu context đã đóng, nó có thể gặp lazy-loading exception (tùy provider).

Hai vấn đề cần phân biệt:

- **N+1:** có context và load được, nhưng số SQL tăng quá nhiều.
- **LazyInitializationException:** association chưa tải nhưng context/session cần thiết đã đóng.

Giải pháp không phải lúc nào cũng là mở context lâu hơn để serializer tự tải toàn graph. Một thiết kế an toàn hơn là **tạo DTO được xác định bởi use case** trong transaction, sử dụng projection/fetch plan có kiểm soát, rồi trả DTO.

Nếu ứng dụng dùng Open Session in View, nó có thể làm lazy loading diễn ra trong quá trình render và che giấu N+1. Vì vậy cần đo toàn bộ HTTP request và cân nhắc tắt/mô tả rõ policy khi vận hành.

## 25. Một ORM getter có thể sinh SQL ở đâu?

Không phải mọi getter đều phát SQL:

```java
book.getTitle();                 // Basic field đã load: thường không SQL.
book.getAuthor();                // Có thể trả lazy proxy, chưa cần SQL.
book.getAuthor().getId();        // Có provider proxy lấy ID không SQL.
book.getAuthor().getName();      // Có thể khởi tạo proxy → SELECT.
book.getReviews();               // Có thể trả persistent collection wrapper.
book.getReviews().size();        // Có thể khởi tạo/count → SELECT.
book.getReviews().iterator();    // Có thể load collection → SELECT.
```

Các ví dụ “có thể” là chủ ý: mức độ lazy, bytecode enhancement, query plan, cache và access pattern thay đổi theo provider.

Cách phát hiện chắc chắn là:

1. Seed DB fixture.
2. Dùng context mới và làm sạch cache theo mục tiêu test.
3. Bật SQL capture.
4. Đo riêng sau `getResultList()`.
5. Đo sau từng đoạn getter/mapper/render.
6. Đối chiếu số statement.

Đừng đoán chỉ từ tên getter.

## 26. Test tích hợp cho tình huống N+1

Bộ test muốn chứng minh một method truy vấn tối ưu không phát sinh số SELECT tăng theo số Book.

Một ý tưởng JUnit:

```java
@Test
void bookCardsShouldNotFetchOneAuthorPerBook() {
    seedBooksWithDistinctAuthors(30);

    entityManager.clear();
    statistics.clear();

    List<BookCard> cards = bookReportRepository.findCards();

    assertEquals(30, cards.size());

    long statements = statistics.getPrepareStatementCount();

    assertTrue(statements <= 3,
        "Unexpected statement count: " + statements);
}
```

Ở đây:

- `seedBooksWithDistinctAuthors`, `statistics` và repository là fixture/harness giả định.
- Nếu dùng Hibernate Statistics, phải đảm bảo không có test/operation khác cùng tăng số liệu trong cửa sổ đo.
- Ngưỡng `<= 3` là một **ví dụ hợp đồng hiệu năng** của phương án cụ thể, không phải tiêu chuẩn JPA.
- Test phải seed và commit trước rồi dùng persistence context mới; `clear` một mình không xóa second-level cache.
- Cần ít nhất một test chạy trên provider/database thực tế.

Một cách test bền hơn nữa: chạy cùng use case ở N=5 và N=30 rồi so sánh số SQL với query plan dự kiến. Nếu số query tăng gần 25 khi N tăng 25, có khả năng N+1.

### Test một query không đủ

`assertEquals(1, statements)` có thể quá cứng nhắc nếu solution hợp lý dùng 2–3 query theo batch. Mục tiêu là phát hiện hồi quy theo **độ dốc số query khi N tăng**, không biến mọi giải pháp thành “phải đúng một SELECT”.

## 27. Cô lập cache và fixture cho kiểm thử N+1

Một fixture có Author dùng chung là hữu ích để kiểm tra identity map, nhưng **không đủ** để tạo N+1 to-one:

```text
30 Books → 1 Author
```

Nếu provider chỉ SELECT Author một lần, test pass dù code vẫn dựa trên lazy loading.

Fixture có độ phân biệt tốt:

```text
Book 1  → Author 1
Book 2  → Author 2
...
Book 30 → Author 30
```

Nếu kiểm thử Reviews:

```text
Book 1  → 2 Reviews
Book 2  → 0 Reviews
Book 3  → 5 Reviews
...
Book 30 → 1 Review
```

Các lưu ý:

- Seed trong transaction khác rồi commit.
- Kết thúc EntityManager setup.
- Mở EntityManager test mới.
- Nếu muốn “cold cache”, vô hiệu hóa/evict shared cache có chủ đích hoặc dùng factory/database cô lập.
- Không chạy song song các test đo thống kê global trên cùng SessionFactory.
- Đảm bảo test xử lý **toàn bộ DTO mapping** chứ không chỉ gọi repository trả entities.

## 28. Kiểm tra profile API trước và sau sửa

Khi sửa N+1, đo:

| Chỉ số | Trước | Sau |
| --- | --- | --- |
| Số Book trên page | 50 | 50 |
| Số SELECT | Có thể 51 | Ví dụ 1 hoặc 2 |
| Tổng SQL rows | 50 Books + 50 Authors | Có thể 50 joined rows |
| DB round trips | Cao | Thấp |
| Memory | Phụ thuộc managed graph | Phụ thuộc fetch/projection |
| Response time | Đo thực tế | Đo thực tế |

Các con số “trước/sau” phải do hệ thống đo, không nên lấy minh họa làm kết quả benchmark.

### Không bỏ qua số row khi join collection

Nếu fetch tất cả Reviews bằng join:

- SQL SELECT có thể chỉ một.
- Nhưng 50 Books × trung bình 100 Reviews có thể tạo 5.000 rows.
- Java phải hydrate/ghép object graph.
- Trang web chỉ cần Book title và review count thì truy vấn vẫn tải quá nhiều.

N+1 là một trong nhiều anti-pattern cần phát hiện; giải pháp phải cân bằng số query, data volume và use-case needs.

## 29. Khi nào EAGER vẫn tạo N+1?

Ví dụ:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Author author;
```

Sau:

```java
em.createQuery("SELECT b FROM Book b", Book.class)
  .getResultList();
```

Provider có thể tải Books trong một SQL và Authors qua secondary SELECTs để bảo đảm eager state. Điều này thường không được nhìn thấy trong Java business loop, vì query phụ có thể xảy ra ngay khi materialize result.

Vì thế, khi SQL log có nhiều SELECT Authors nhưng code không gọi getter, hãy kiểm tra:

- EAGER mapping mặc định hoặc khai báo.
- EntityGraph/loadgraph.
- JPQL query không ghi fetch join.
- Cache/identity map.
- Entity mappings lồng các eager associations.
- Provider fetch plan.

**EAGER nói về thời điểm state cần sẵn sàng, không bảo đảm cách thực hiện bằng một SQL duy nhất.**

## 30. Khi nào batch fetching không cứu được?

Batch fetching hiệu quả khi provider biết một nhóm pending proxies/collections cùng loại cần được nạp và có thể ghép keys vào truy vấn batch. Nó không tự giải quyết mọi trường hợp:

- Mỗi lần mở một EntityManager mới cho một Book rồi đóng ngay.
- Query chạy ngoài phạm vi batch/session mà provider có thể gom.
- Custom repository query được gọi một lần mỗi item theo vòng lặp.
- GraphQL resolver tự gửi N HTTP requests đến một microservice khác.
- Một collection cần xử lý có kích thước khổng lồ, dù số query giảm.
- Database giới hạn IN list/parameter.
- Cache/query shapes thay đổi liên tục.

Nếu code:

```java
for (Long bookId : ids) {
    try (EntityManager em = emf.createEntityManager()) {
        Book book = em.find(Book.class, bookId);
        process(book.getAuthor().getName());
    }
}
```

thì mỗi vòng có context khác, không có một nhóm managed proxies lớn để ORM batch-fetch hiệu quả. Cần **thiết kế truy vấn theo batch IDs** thay vì chỉ bật một setting.

## 31. Tránh N+1 trong thao tác cập nhật

N+1 không chỉ ở màn hình đọc. Một batch job:

```java
for (Long bookId : ids) {
    Book book = em.find(Book.class, bookId);
    book.changePrice(calculateNewPrice(book));
}
```

có thể tạo N SELECT để tải Book, rồi N UPDATE khi flush. Đây là vấn đề nhiều round trips, mặc dù khác với association N+1 cổ điển.

Có thể cải thiện bằng:

- SELECT Books theo `IN` hoặc range ở các batch.
- Bulk JPQL UPDATE nếu business semantics cho phép và không cần lifecycle per-entity.
- JDBC batch write configuration.
- Dùng projection chỉ lấy dữ liệu cần tính.
- Giới hạn persistence context và transaction size.

Nếu `calculateNewPrice` còn đọc `book.author` hoặc `book.reviews`, lại có thêm association N+1. Cần nhìn toàn bộ traversal, không chỉ method `find`.

### Không chọn bulk DML bừa bãi

Bulk JPQL/native UPDATE bỏ qua một số managed entity lifecycle/callback/optimistic-locking behavior thông thường. Nếu nghiệp vụ cần chúng, phải cân nhắc giữ per-entity updates nhưng cải thiện loading và batching.

## 32. Một quy trình chẩn đoán có thể áp dụng ngay

Khi nghi vấn N+1, thực hiện các bước:

1. **Định nghĩa use case:** danh sách/chi tiết/export/batch làm gì, cần những dữ liệu nào?
2. **Ghi lại điểm bắt đầu truy vấn root:** JPQL, Criteria, repository hoặc GraphQL resolver.
3. **Xác định object graph được truy cập:** Author, Reviews, User, Publisher, Address...
4. **Bật SQL capture và statistics phù hợp.**
5. **Tạo fixture đủ lớn với association khác nhau**, seed và commit trước đo.
6. **Dùng context mới và kiểm soát cache.**
7. **Ghi số SQL trước và sau truy cập từng association**, không chỉ thời gian `getResultList()`.
8. **Tăng N** để xem số query có tăng cùng N không.
9. **Khoanh vùng association gây secondary SELECT.**
10. **Chọn fetch plan theo mục đích:** to-one fetch join, entity graph, DTO projection, batch fetching hoặc two-step page.
11. **Đo lại** SQL count, rows, memory và latency.
12. **Thêm regression integration test** với fixture phân biệt và ngưỡng phù hợp.
13. **Đánh giá cả transaction/serialization layer** để tránh N+1 chuyển sang vị trí khác.
14. **Không tối ưu toàn bộ entity mapping một cách global** nếu use case chỉ cần một phần graph.
15. **Tài liệu hóa query shape và fetch assumptions** để lần refactor sau không làm hồi quy.

## 33. Những lỗi thường gặp

### Lỗi 1: Chỉ đếm SQL của repository method

Mapper hoặc serializer mới là nơi lazy loading diễn ra. Đo toàn bộ business request.

### Lỗi 2: Dùng một Author chung cho 100 Books trong test

First-level cache có thể khiến chỉ một secondary SELECT. Dùng nhiều Author khác nhau để kiểm tra xu hướng.

### Lỗi 3: Chuyển mọi association sang EAGER

Có thể tăng tải thừa và vẫn gặp secondary SELECTs. Dùng fetch plan theo use case.

### Lỗi 4: Dùng fetch join tất cả collections

Có thể gây row multiplication, memory lớn, hoặc giới hạn provider như nhiều bag collections. Chọn chiến lược theo graph.

### Lỗi 5: Cho rằng `@EntityGraph` bảo đảm một SQL

Entity graph mô tả nhu cầu fetch; provider chọn phương thức tải. Đo SQL thực tế.

### Lỗi 6: Gọi `getReviews().size()` rồi nghĩ chắc chắn không query

Lazy persistent collection có thể cần SELECT hoặc COUNT. Kiểm tra SQL.

### Lỗi 7: Đo trên context đã load sẵn

Không tái hiện cold-cache behavior. Seed/commit rồi test ở context khác.

### Lỗi 8: Chỉ nhìn số SQL, không nhìn số row

Một fetch join collection có thể ít SQL nhưng trả rất nhiều hàng. Đo data volume và memory.

### Lỗi 9: Trả thẳng entities qua JSON

Serializer duyệt graph ngoài tầm kiểm soát, có thể tạo N+1 hoặc lazy-init error. Trả DTO.

### Lỗi 10: Ngỡ N+1 chỉ xuất hiện với LAZY

EAGER cũng có thể dùng secondary SELECTs và phát nhiều SQL.

### Lỗi 11: Lạm dụng parallel stream trên managed entities

EntityManager không thread-safe; parallel traversal có thể gây lỗi hoặc hiệu năng xấu hơn.

### Lỗi 12: Bật batch fetch nhưng mỗi item ở một EntityManager riêng

Provider không có context chung để gom proxy/collection. Thiết kế batch query/context phù hợp.

### Lỗi 13: Dùng pageable + collection fetch join mà không quan sát SQL

Provider có thể xử lý pagination trong memory hoặc cảnh báo. Dùng two-step pagination khi cần.

### Lỗi 14: Cache warm khiến test xanh

Lần chạy đầu production vẫn chịu N+1. Test cả cold-cache và warm-cache theo yêu cầu.

### Lỗi 15: Coi ngưỡng SQL = 1 là chỉ số chất lượng tuyệt đối

Hai query batch có thể hiệu quả hơn một query join trả hàng triệu rows. Chọn ngưỡng phản ánh use case.

## 34. Bài tập thực hành

### Bài tập 1: Đếm N+1 cơ bản

Một truy vấn trả 40 Books, mỗi Book có Author khác nhau, chưa cache/batch. Sau đó gọi `book.getAuthor().getName()` cho từng Book.

**Câu hỏi:** Có thể phát bao nhiêu SELECT?

**Đáp án:** Một SELECT Books cộng tối đa 40 SELECT Authors, tức khoảng 41, trong giả định được nêu.

### Bài tập 2: Nhiều Book dùng chung Author

40 Books cùng một Author, trong cùng persistence context.

**Câu hỏi:** Có nhất thiết 41 SELECT không?

**Đáp án:** Không. Identity map/cache có thể giúp chỉ load Author một lần. Đó là lý do fixture nên có nhiều Author khác nhau.

### Bài tập 3: EAGER có đủ không?

`@ManyToOne(fetch = EAGER)` trên Book.author.

**Câu hỏi:** Có bảo đảm một SELECT JOIN không?

**Đáp án:** Không. EAGER không quy định số SQL; provider có thể dùng secondary selects.

### Bài tập 4: Lazy collection

`for (Book b : books) { b.getReviews().size(); }`

**Câu hỏi:** Vì sao có thể gây N+1?

**Đáp án:** Mỗi Book có collection lazy chưa khởi tạo, và provider có thể phải SELECT/COUNT Reviews riêng cho từng Book.

### Bài tập 5: Thay đổi truy vấn to-one

**Yêu cầu:** Trả Books và Author name với ít secondary SELECT hơn.

**Gợi ý đáp án:** Dùng `SELECT b FROM Book b JOIN FETCH b.author` khi cần managed Book/Author graph; hoặc DTO projection `SELECT NEW ...BookCard(b.id,b.title,a.name) FROM Book b JOIN b.author a` khi chỉ cần dữ liệu hiển thị.

### Bài tập 6: Trang 20 Books có Reviews

**Câu hỏi:** Vì sao không nên mặc định `LEFT JOIN FETCH b.reviews` rồi `setMaxResults(20)`?

**Đáp án:** Join collection nhân SQL rows; provider có thể pagination in memory hoặc không hỗ trợ theo cách mong muốn. Dùng page IDs rồi fetch association theo batch.

### Bài tập 7: Log không thấy N+1 ở repository

Repository trả List<Book> bằng một SELECT; response API chậm và log có nhiều SELECT Author sau đó.

**Đáp án:** Kiểm tra DTO mapper hoặc JSON serializer đang truy cập `getAuthor()`. N+1 xảy ra ở traversal ngoài repository.

### Bài tập 8: Count Reviews

Trang chỉ cần số Reviews của mỗi Book.

**Câu hỏi:** Có nên tải tất cả Reviews không?

**Đáp án:** Thường không. Dùng query aggregate `COUNT(r)` theo Book ID hoặc batch aggregation để giảm dữ liệu.

### Bài tập 9: BatchSize 32

100 Book có lazy Review collections và provider batch fetching hỗ trợ batch size 32.

**Câu hỏi:** Có thể kỳ vọng hướng tối ưu ra sao?

**Đáp án:** Có thể gom nhiều collection loads thành vài SELECT với IN/subselect thay vì 100 SELECT riêng. Số câu cụ thể cần đo, không bảo đảm đúng 4 trên mọi provider.

### Bài tập 10: Test chống hồi quy

**Yêu cầu:** Thiết kế fixture đủ mạnh để phát hiện N+1 to-one.

**Gợi ý đáp án:** Seed 30 Books với 30 Authors, commit và đóng context, chạy truy vấn ở context mới, đo SQL cho cả mapping/serialization; so sánh với fixture N nhỏ hơn; assert query count không tăng gần tuyến tính theo N.

### Bài tập 11: GraphQL resolver

Mỗi Book resolver gọi `findAuthorById`.

**Câu hỏi:** Vấn đề có phụ thuộc annotation LAZY không?

**Đáp án:** Không. N+1 có thể ở tầng resolver/service vì gọi truy vấn lặp theo từng item. Batch loader hoặc query projection phù hợp.

### Bài tập 12: Join fetch một query nhưng chậm

Một Book có 50.000 Reviews; query join fetch tất cả Reviews.

**Câu hỏi:** Vì sao vẫn chậm dù chỉ một SELECT?

**Đáp án:** Số SQL rows, băng thông, hydration và memory có thể rất lớn. Tối ưu bằng projection, paging hoặc chỉ lấy dữ liệu cần thiết.

## 35. Checklist đánh giá một fetch plan

Trước khi kết luận đã giải quyết N+1, hãy xác nhận:

1. Use case thật sự truy cập những association nào?
2. Có đo toàn bộ request/mapper/serializer không?
3. Có SQL SELECT phụ lặp lại với điều kiện PK/FK khác nhau không?
4. Số SELECT có tăng theo N không?
5. Fixture có đủ Author/target khác nhau không?
6. Persistence context test có mới và second-level cache được kiểm soát không?
7. Mapping mặc định EAGER có tạo secondary SELECT không?
8. `JOIN FETCH` có cần thiết cho to-one association không?
9. Có collection fetch join làm nhân rows không?
10. Pagination có bị thực thi trong memory không?
11. DTO projection có phù hợp hơn entity graph không?
12. Có thể dùng aggregate query thay vì load collection không?
13. EntityGraph chỉ tải attributes cần thiết không?
14. Batch fetching có thực sự chạy trên provider đang dùng không?
15. Có sử dụng nhiều EntityManager làm mất khả năng batch không?
16. N+1 có ẩn trong GraphQL resolvers hoặc JSON serialization không?
17. Có N+1 đa tầng giữa Book, Review, User không?
18. Cần kiểm tra số SQL, số rows và latency cùng nhau không?
19. Có test hồi quy chống N+1 ở fixture đủ lớn không?
20. Fetch plan có ổn khi page size và dữ liệu production tăng không?

## Kết luận

**N+1 trong JPA là hệ quả của mối quan hệ giữa truy vấn gốc, fetch plan và hành vi truy cập đồ thị đối tượng.** Một câu `SELECT b FROM Book b` có thể chạy nhanh, nhưng khi mapper, vòng lặp hoặc serializer lần lượt gọi `book.getAuthor()` hay `book.getReviews()`, provider có thể gửi thêm nhiều câu SELECT theo từng entity hoặc collection.

Không thể nhận diện N+1 chỉ bằng cách nhìn `FetchType.LAZY` hay `FetchType.EAGER`. EAGER vẫn có thể dùng secondary SELECTs; LAZY có thể không tạo thêm SQL nếu dữ liệu đã có trong context/cache hoặc được batch fetch. Bằng chứng đáng tin cậy là **SQL trace, statement count và số query khi N tăng**, đo trong toàn bộ use case.

Tùy nhu cầu, hãy chọn **fetch join cho association cần dùng, entity graph theo use case, DTO projection khi chỉ cần một số cột, batch/subselect fetching có kiểm chứng hoặc phân trang hai giai đoạn cho collection**. Đừng tối ưu mỗi số câu SQL mà bỏ qua row multiplication, memory và transaction duration.

Bài học cốt lõi là: **khi một đoạn code duyệt nhiều entity, hãy luôn hỏi mỗi lần truy cập getter nào có thể kích hoạt SQL, có cần tải cả association hay chỉ cần giá trị tổng hợp, và liệu chi phí có tăng theo số phần tử đang duyệt hay không**. Trả lời được những câu hỏi đó là nền tảng để nhận diện và xử lý N+1 một cách có hệ thống.
