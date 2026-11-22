# Phân biệt yêu cầu EAGER và gợi ý LAZY trong phạm vi chuẩn

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Kế hoạch tải

Khi ánh xạ quan hệ trong JPA, một câu hỏi quan trọng là: **khi lấy entity từ database, các thuộc tính và entity liên quan sẽ được tải vào bộ nhớ vào lúc nào?** Nếu tải quá nhiều dữ liệu, hệ thống tốn SQL, bộ nhớ và thời gian phản hồi. Nếu tải quá ít, code có thể phát sinh hàng loạt truy vấn khi truy cập association hoặc gặp lỗi khi persistence context đã đóng.

JPA cung cấp enum `FetchType` với hai giá trị:

- **`FetchType.EAGER`:** một **yêu cầu đối với persistence provider** rằng dữ liệu liên quan phải được tải sớm theo ngữ nghĩa fetch của mapping.
- **`FetchType.LAZY`:** một **gợi ý (*hint*) đối với persistence provider** rằng dữ liệu liên quan nên được trì hoãn đến khi cần truy cập.

Khác biệt này có tính **chuẩn (specification-level)**, không chỉ là thói quen của Hibernate. Provider được phép tải sớm một association được khai báo `LAZY` trong các tình huống phù hợp; trái lại, `EAGER` thể hiện cam kết mạnh hơn về việc dữ liệu phải được tải.

Một hiểu nhầm phổ biến khác: `EAGER` **không đồng nghĩa với một SQL JOIN**. Provider có thể tải bằng JOIN, SELECT riêng, batch fetching hoặc chiến lược khác. Vì vậy, một mapping EAGER vẫn có thể tạo ra hiện tượng **N+1 queries**, và một mapping LAZY không bảo đảm rằng lúc truy vấn ban đầu sẽ không đụng đến bảng liên quan.

Bài này tập trung vào cách hiểu chuẩn JPA, giá trị mặc định của các association, cách xây **fetch plan theo từng use case**, phương pháp quan sát SQL và giới hạn portable của các annotation.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt về **mức độ ràng buộc** giữa `FetchType.EAGER` và `FetchType.LAZY`.
2. Kể đúng giá trị fetch mặc định của `@Basic`, `@ManyToOne`, `@OneToOne`, `@OneToMany`, `@ManyToMany` và `@ElementCollection`.
3. Phân biệt **thời điểm tải** với **cách tải** (JOIN, SELECT riêng, batch, subselect).
4. Hiểu tại sao EAGER **có thể** gây N+1 và LAZY **cũng có thể** dẫn đến N+1.
5. Biết khi nào một trường LAZY hoặc association chưa tải có thể gặp vấn đề sau khi context đóng.
6. Phân biệt fetch với cascade, orphanRemoval và quyền sở hữu foreign key.
7. Dùng JPQL `JOIN FETCH` để tải association có chủ đích trong một query.
8. Dùng JPA Entity Graph với `jakarta.persistence.fetchgraph` và `jakarta.persistence.loadgraph` để thiết kế fetch plan động.
9. Hiểu giới hạn của fetch join trên collection kết hợp pagination.
10. Dùng `PersistenceUnitUtil.isLoaded` và SQL logging để quan sát trạng thái tải mà không dựa vào giả định.
11. Biết các trường hợp LAZY không được hỗ trợ hiệu quả nếu thiếu bytecode enhancement/proxy phù hợp.
12. Đưa ra quyết định mapping dựa trên use case, kích thước object graph và transaction boundary.

## 2. Khái niệm fetch plan

**Fetch plan** là kế hoạch xác định **những dữ liệu nào cần được đưa vào persistence context trong một thao tác truy vấn hoặc truy cập entity**.

Giả sử:

```text
Customer
   |
   +-- orders: List<PurchaseOrder>
                      |
                      +-- lines: List<OrderLine>
                      |
                      +-- customer: Customer
```

Khi cần màn hình danh sách Customer, ứng dụng có thể chỉ cần:

```text
customer.id
customer.fullName
```

Khi xem chi tiết một PurchaseOrder, ứng dụng lại cần:

```text
order.id
order.orderNumber
order.customer.fullName
order.lines[].sku
order.lines[].quantity
```

Nếu cấu hình mọi association là EAGER để “khỏi lỗi lazy”, màn hình danh sách có thể vô tình tải hàng nghìn Order và OrderLine không sử dụng. Ngược lại, nếu mọi association LAZY nhưng code đi qua chúng từng entity, có thể phát sinh N+1 SELECT.

**Không có một fetch plan cố định phù hợp với mọi use case.** Static fetch type là điểm khởi đầu; JPQL, entity graph và DTO projection giúp điều chỉnh đường tải ở từng truy vấn.

## 3. Hai ý nghĩa khác nhau của EAGER và LAZY

### 3.1. EAGER là yêu cầu

Khi một association được khai báo:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
```

JPA provider phải thực hiện yêu cầu **eagerly fetch** association theo ngữ nghĩa của chuẩn và bối cảnh tải. Điều này không chỉ là gợi ý mà provider được tự do bỏ qua như LAZY.

Tuy nhiên, **JPA không bắt provider dùng đúng một SQL JOIN**. Nó có thể:

- JOIN bảng `customers` vào câu SELECT của `purchase_orders`.
- SELECT `PurchaseOrder` trước rồi SELECT `Customer` riêng.
- Dùng batch loading hoặc một chiến lược phù hợp khác.
- Tái sử dụng một Customer đã managed trong cùng persistence context thay vì query thêm.
- Áp dụng hint/entity graph phù hợp với context và provider.

Kết quả là **EAGER nói về việc dữ liệu cần sẵn sàng, không mô tả cụ thể số SQL statement**.

### 3.2. LAZY là gợi ý

Khi khai báo:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

ứng dụng yêu cầu provider **nên trì hoãn** việc tải Customer đến khi association được truy cập.

Nhưng trong chuẩn JPA, LAZY là **hint**, không phải bảo đảm tuyệt đối rằng provider không được tải Customer ngay. Provider có thể eagerly fetch association mặc dù mapping chỉ định LAZY.

Các lý do thường gặp:

- Provider không hỗ trợ lazy hiệu quả cho loại attribute/mapping đó.
- Không có bytecode enhancement cần thiết.
- Cấu trúc proxy không phù hợp với một trường hợp quan hệ.
- Query có `JOIN FETCH` hoặc entity graph yêu cầu tải.
- Persistence context đã chứa entity liên quan, không cần query mới.
- Provider chọn một kế hoạch tải sớm mà nó được phép theo chuẩn.

Vì vậy, đừng viết test với giả định: “annotation LAZY thì `isLoaded` **bắt buộc false** ngay sau `find`”. Cần kiểm tra hành vi của provider thực tế và diễn giải đúng rằng LAZY không tạo một ràng buộc bắt buộc.

### 3.3. Bảng so sánh cốt lõi

| Tiêu chí | FetchType.EAGER | FetchType.LAZY |
|---|---|---|
| Mức độ theo chuẩn | **Yêu cầu** của mapping/provider | **Gợi ý** tối ưu hóa |
| Ý định | Tải association/attribute sớm | Trì hoãn đến khi cần |
| Provider được tự ý chọn tải sớm? | Đã yêu cầu tải sớm | Có thể |
| Bắt buộc JOIN? | **Không** | **Không** |
| Bắt buộc một SQL? | **Không** | **Không** |
| Bảo đảm tránh N+1? | Không | Không |
| Bảo đảm không có SELECT liên quan ban đầu? | Không | Không |
| Có thể điều chỉnh theo query? | Có, qua các công cụ fetch plan theo chuẩn và hỗ trợ provider | Có |
| Bảo đảm context đóng mà toàn graph dùng được? | Không, chỉ trong phạm vi attribute đã được tải | Không |
| Có liên quan cascade PERSIST/REMOVE? | Không trực tiếp | Không trực tiếp |

**Ghi nhớ:** **EAGER không bằng JOIN; LAZY không bằng “chắc chắn chưa được load”.**

---

## 4. Giá trị fetch mặc định theo annotation

Khi không khai báo `fetch = ...`, JPA dùng giá trị mặc định do mapping annotation quy định.

| Annotation | FetchType mặc định | Ghi chú |
|---|---|---|
| `@Basic` | **EAGER** | Bao gồm nhiều basic attributes như String, Integer |
| `@ManyToOne` | **EAGER** | Quan hệ nhiều-một |
| `@OneToOne` | **EAGER** | Quan hệ một-một |
| `@OneToMany` | **LAZY** | Collection một-nhiều |
| `@ManyToMany` | **LAZY** | Collection nhiều-nhiều |
| `@ElementCollection` | **LAZY** | Collection chứa basic/embeddable values |

Ví dụ:

```java
@ManyToOne
private Customer customer;
```

tương đương khai báo default `fetch = FetchType.EAGER` về mặt metadata.

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
```

có default `fetch = FetchType.LAZY`.

### 4.1. @ManyToOne và @OneToOne mặc định EAGER

Điều này có thể gây bất ngờ vì nhiều ứng dụng nghiệp vụ có quan hệ một-nhiều/nhiều-một rất dày đặc. Một câu query lấy 100 Order với customer EAGER có thể yêu cầu provider lấy Customer cho các Order, ngay cả khi màn hình chỉ hiển thị số đơn.

Không nên kết luận rằng mọi Order đều thực hiện một SELECT riêng; nếu Customer trùng ID, first-level cache hoặc một fetch strategy khác có thể giảm số SELECT. Nhưng nguy cơ SQL phụ không mong muốn là có thật.

### 4.2. @OneToMany và @ManyToMany mặc định LAZY

Với collection, việc tự động tải mọi phần tử liên quan thường rất tốn kém. Vì vậy default là LAZY hint.

Nhưng nếu query dùng fetch join hoặc entity graph, collection vẫn có thể được tải ngay. Annotation LAZY không cấm một fetch plan động chỉ định EAGER cho use case cụ thể.

### 4.3. @Basic mặc định EAGER

`@Basic` áp dụng cho các basic fields:

```java
@Basic
@Column(name = "display_name")
private String displayName;
```

`@Basic` có default EAGER. Nếu có field rất lớn:

```java
@Lob
@Basic(fetch = FetchType.LAZY)
private String largeDescription;
```

đây là yêu cầu **gợi ý trì hoãn**, nhưng không nhất thiết hoạt động hiệu quả trên mọi provider. Với một số Hibernate mappings, cần **bytecode enhancement** để basic attribute lazy loading hoạt động như dự kiến.

Không coi `@Lob` tự động tương đương LAZY. Annotation `@Lob` mô tả kiểu dữ liệu lớn; nó không thay thế việc xác định fetch plan.

### 4.4. @Embedded có fetch không?

`@Embedded` mô tả embeddable được nhúng vào entity, không có thuộc tính `fetch` như association annotations kể trên. Các persistent attributes bên trong embeddable có mapping/semantics riêng. Không nên xem một object value `@Embedded` giống một entity association cần SELECT riêng chỉ vì Java code có object reference.

---

## 5. Ví dụ entity để quan sát kế hoạch tải

Ta dùng ba entity:

- `Customer`.
- `PurchaseOrder`.
- `OrderLine`.

Schema:

```text
customers
  id (PK)
  full_name

purchase_orders
  id (PK)
  order_number
  customer_id (FK -> customers.id)
  status

order_lines
  id (PK)
  order_id (FK -> purchase_orders.id)
  sku
  quantity
```

Quan hệ:

```text
Customer 1 ------ N PurchaseOrder
PurchaseOrder 1 -- N OrderLine

PurchaseOrder.customer     @ManyToOne
Customer.orders            @OneToMany
PurchaseOrder.lines        @OneToMany
OrderLine.order            @ManyToOne
```

### 5.1. Entity Customer

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
        // JPA
    }

    public Customer(String fullName) {
        this.fullName = Objects.requireNonNull(fullName);
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
```

Không ghi `fetch` ở `Customer.orders`, nên annotation mặc định là **LAZY**.

### 5.2. Entity PurchaseOrder: đặt ManyToOne LAZY có chủ đích

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
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // JPA
    }

    public PurchaseOrder(String orderNumber, Customer customer) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.customer = Objects.requireNonNull(customer);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

Trong ví dụ này, `@ManyToOne(fetch=LAZY)` là **quyết định tường minh** thay default EAGER. Nó giúp mô tả ý định phần lớn truy vấn Order không cần Customer.

Tuy nhiên, JPA vẫn cho phép provider eagerly fetch Customer. Muốn đo tải thực tế, cần kiểm tra SQL hoặc trạng thái load trên provider đã chọn.

### 5.3. Entity OrderLine

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

    @Column(name = "sku", nullable = false, length = 60)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {
        // JPA
    }

    public OrderLine(
            PurchaseOrder order,
            String sku,
            int quantity) {

        this.order = Objects.requireNonNull(order);
        this.sku = Objects.requireNonNull(sku);

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        this.quantity = quantity;
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

    public PurchaseOrder getOrder() {
        return order;
    }
}
```

Trong code minh họa, chưa khai báo cascade persist và chưa cung cấp helper quản lý quan hệ hai chiều. Khi tạo dữ liệu thử, cần persist Customer/Order/Line theo thứ tự phù hợp và đặt cả hai phía Java reference/collection nhất quán nếu ứng dụng dùng cả hai phía. Điều đó không làm thay đổi bài học fetch plan.

### 5.4. SQL DDL tham khảo

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

DDL dùng cú pháp identity minh họa; các DBMS có thể khác. Kế hoạch tải là cơ chế ORM, không phải một constraint trong schema.

---

## 6. FetchType quyết định gì, không quyết định gì?

### 6.1. FetchType quyết định ý định tải

Ví dụ:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
```

ý định: Customer sẵn sàng sớm khi Order được tải theo mapping.

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

ý định: có thể trì hoãn Customer cho đến khi cần truy cập.

### 6.2. FetchType không quyết định SQL phải là JOIN

EAGER có thể tạo:

```sql
SELECT o.id, o.order_number, c.id, c.full_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = ?;
```

Nhưng cũng có thể:

```sql
SELECT o.id, o.order_number, o.customer_id
FROM purchase_orders o
WHERE o.id = ?;

SELECT c.id, c.full_name
FROM customers c
WHERE c.id = ?;
```

Cả hai là SQL mô phỏng, không phải cam kết câu SQL của provider. Ngữ nghĩa EAGER không bắt buộc một JOIN duy nhất.

### 6.3. FetchType không quy định transaction

Dù dùng EAGER hay LAZY, việc đọc dữ liệu vẫn phụ thuộc EntityManager, transaction/connection và database isolation. `fetch=EAGER` không tự tạo transaction dài; `fetch=LAZY` không tự giữ EntityManager mở sau khi caller đóng nó.

### 6.4. FetchType không phải cascade

`fetch` quyết định **khi nào tải dữ liệu liên quan**. `cascade` quyết định **thao tác lifecycle nào được lan truyền**:

```java
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.MERGE
)
private Customer customer;
```

Ở đây:

- LAZY mô tả gợi ý fetch.
- MERGE mô tả việc lan truyền thao tác merge.
- Hai thuộc tính không thay thế nhau.

Tương tự, `orphanRemoval` liên quan xóa child khi rời association, không tự quyết định fetch type.

---

## 7. EAGER vẫn có thể gây N+1

Giả sử `PurchaseOrder.customer` được để mặc định EAGER:

```java
@ManyToOne
private Customer customer;
```

Ứng dụng chạy:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

Nếu provider chọn SELECT Order rồi SELECT Customer theo từng association chưa có trong context, SQL có thể trông như:

```text
SELECT orders                           1 query
SELECT customer for order 1            1 query
SELECT customer for order 2            1 query
SELECT customer for order 3            1 query
...
SELECT customer for order N            N queries

Tổng: có thể ~ 1 + N queries
```

Cần nói chính xác:

- Đây là **kịch bản có thể xảy ra**, không phải bảo đảm mọi EAGER mapping đều gây N+1.
- Nếu nhiều Order cùng tham chiếu một Customer, first-level cache có thể giảm số query.
- Nếu provider chọn JOIN/batch, query count khác.
- EAGER là yêu cầu tải sớm; provider vẫn tự quyết định fetch strategy.

### 7.1. Vì sao N+1 không chỉ là vấn đề LAZY?

Nhiều người nghĩ “N+1 là do LAZY nên đổi hết sang EAGER”. Nhưng chính default EAGER trên `@ManyToOne` cũng có thể tạo secondary SELECTs. Đổi toàn bộ mapping sang EAGER có thể **tăng** số query và dữ liệu tải ngoài ý muốn.

### 7.2. Cách thiết kế tốt hơn

Nếu danh sách Order chỉ cần:

```text
id, orderNumber
```

dùng DTO projection thay vì load đầy đủ entity graph.

Nếu cần cả Customer name, dùng fetch join hoặc projection chỉ lấy đúng cột đó.

**Tối ưu phải dựa trên dữ liệu thực sự cần của use case**, không dựa vào giả định LAZY hay EAGER luôn nhanh hơn.

---

## 8. LAZY cũng có thể gây N+1

Giả sử `PurchaseOrder.customer` đặt LAZY:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Query lấy danh sách Order:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

Sau đó code:

```java
for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getFullName());
}
```

Khi Customer chưa được tải sớm, mỗi lần truy cập `getFullName()` có thể kích hoạt SELECT liên quan. Với nhiều Customer khác nhau, có thể tạo N+1.

### 8.1. Vấn đề không phải “lười” hay “tham” tải

- LAZY hữu ích khi association **ít được dùng**.
- Khi một use case **biết chắc cần association**, nên đưa nó vào fetch plan của query đó.
- EAGER hữu ích với attribute thật sự luôn cần theo contract, nhưng mapping static EAGER trên graph sâu dễ gây tải dư.

Một cấu hình hợp lý thường là:

1. Static mapping giữ những quan hệ lớn ít cần là LAZY.
2. Query cụ thể dùng `JOIN FETCH`, entity graph hoặc DTO để lấy đúng dữ liệu.
3. Đo SQL để xác nhận hiệu quả.

---

## 9. JPQL JOIN khác JOIN FETCH

Đây là khác biệt cơ bản.

### 9.1. JOIN thường

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.fullName LIKE :prefix
```

`JOIN` ở đây cho phép **điều kiện lọc** theo Customer. Nó không tự là yêu cầu chuẩn bắt provider phải khởi tạo toàn bộ `o.customer` khi trả Order.

Provider có thể dùng SQL JOIN để lọc nhưng vẫn giữ association ở trạng thái LAZY theo fetch plan.

### 9.2. JOIN FETCH

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.id = :orderId
```

`JOIN FETCH` biểu diễn yêu cầu tải association `customer` cùng kết quả Order trong query này. Đây là cách viết **fetch plan theo use case**, không cần đổi static mapping của `PurchaseOrder.customer`.

### 9.3. LEFT JOIN FETCH

Nếu association có thể không tồn tại:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.customer
WHERE o.id = :orderId
```

LEFT JOIN FETCH giữ Order kể cả khi không có Customer phù hợp (với mapping optional cho phép). Với entity ví dụ `optional=false`, Customer phải tồn tại; nhưng cú pháp LEFT JOIN FETCH vẫn giúp minh họa khác biệt giữa inner/outer join.

### 9.4. JOIN FETCH không phải SQL JOIN duy nhất được cam kết

`JOIN FETCH` là directive trong JPQL cho association được tải cùng kết quả. Thực tế SQL có thể được provider xây dựng theo chiến lược phù hợp, nhưng ý định là explicit fetch. Nó cũng có thể làm result set lớn nếu fetch collection.

### 9.5. Không dùng alias của fetch join như JOIN thường trong JPQL portable

Cách chuẩn đơn giản:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
```

Một số HQL extensions cho phép alias trên fetch join hoặc lọc trực tiếp collection được fetch. Không nên dựa vào những cú pháp mở rộng đó nếu bài toán yêu cầu JPQL portable.

Để lọc entity liên quan, có thể dùng JOIN thường riêng hoặc biểu thức path phù hợp; phải cân nhắc semantics và chi phí.

---

## 10. JOIN FETCH collection: hữu ích nhưng có giới hạn

Ví dụ tải Order cùng các Line:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :orderId
```

Kết quả là một Order có collection Lines được tải cho use case chi tiết.

### 10.1. Vì sao có DISTINCT?

SQL JOIN một-nhiều tạo nhiều hàng:

```text
Order#10 + Line#100
Order#10 + Line#101
Order#10 + Line#102
```

Ở mức SQL, cùng cột Order lặp lại cho mỗi Line. Trong JPQL, `DISTINCT` yêu cầu khử trùng lặp ở kết quả entity. Cách provider xử lý SQL DISTINCT và de-duplication in-memory có thể khác theo version.

Điều quan trọng hơn là số hàng SQL vẫn có thể tăng theo số child. `DISTINCT` trong JPQL **không tự xóa chi phí JOIN**.

### 10.2. JOIN FETCH nhiều collection có thể gây Cartesian explosion

Nếu Order có:

```text
Order.lines: 20 phần tử
Order.events: 15 phần tử
```

và query fetch join cả hai collection trong cùng một SQL, số hàng có thể lên tới:

```text
20 × 15 = 300 hàng cho một Order
```

Đây là hệ quả của phép nhân các collection trong JOIN. Provider còn có những giới hạn riêng, ví dụ Hibernate có thể không cho fetch nhiều bag collections cùng lúc trong một số mapping.

**Không dùng JOIN FETCH cho mọi collection chỉ để tránh lazy loading.** Cân nhắc tách query, batch loading, entity graph hợp lý và DTO aggregation.

---

## 11. Phân trang với JOIN FETCH collection

Một truy vấn danh sách:

```java
List<PurchaseOrder> page = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.id
    """,
    PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

có thể gặp vấn đề:

- SQL JOIN tạo nhiều hàng cho mỗi root Order.
- Áp dụng LIMIT/OFFSET trực tiếp lên SQL rows có thể làm collection chưa đầy đủ hoặc số root trên trang không đúng.
- Một số provider có thể áp dụng pagination trong memory hoặc báo warning/error.
- Kết quả hiệu năng không portable và thường tốn hơn dự kiến.

### 11.1. Mô hình hai bước

Một chiến lược thực tế:

**Bước 1:** lấy đúng IDs root theo trang.

```jpql
SELECT o.id
FROM PurchaseOrder o
ORDER BY o.id
```

Dùng `setFirstResult`/`setMaxResults` cho ID page.

**Bước 2:** tải Orders và Lines theo IDs đã chọn:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Sau đó sắp xếp kết quả theo thứ tự của ID page ở application nếu cần, vì `IN` **không tự bảo toàn** thứ tự danh sách IDs.

Đây chỉ là một strategy; với tập dữ liệu lớn, page keyset, collection batch fetching hoặc query DTO có thể tốt hơn. Không nên giả định có một “mẹo” fetch join luôn giải quyết được mọi nhu cầu phân trang.

---

## 12. Entity Graph: kế hoạch tải động theo chuẩn JPA

JPA cung cấp **Entity Graph** để chỉ định những attributes nào cần fetch theo từng thao tác.

Ví dụ trong Java:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer", "lines");
```

Graph này biểu thị Order cần có Customer và Lines trong fetch plan.

### 12.1. Dùng với EntityManager.find()

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer", "lines");

Map<String, Object> hints = new HashMap<>();
hints.put("jakarta.persistence.fetchgraph", graph);

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId, hints);
```

Cần import:

```java
import jakarta.persistence.EntityGraph;
import java.util.HashMap;
import java.util.Map;
```

Đây là cách dùng **dynamic fetch graph** cho đúng một thao tác `find`, không cần sửa annotation fetch static trên entity.

### 12.2. Dùng với JPQL query

```java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.id = :id",
    PurchaseOrder.class);

query.setParameter("id", orderId);

query.setHint("jakarta.persistence.loadgraph", graph);

PurchaseOrder result = query.getSingleResult();
```

Với Jakarta Persistence, tên hint dùng prefix `jakarta.persistence`. Trong ứng dụng JPA cũ dùng namespace `javax.persistence`, tên hint và imports khác. Không trộn hai namespace tùy tiện trong cùng cấu hình.

---

## 13. fetchgraph và loadgraph khác nhau thế nào?

Hai hint chuẩn:

- `jakarta.persistence.fetchgraph`
- `jakarta.persistence.loadgraph`

Chúng có ngữ nghĩa khác nhau.

### 13.1. fetchgraph

Khi dùng `fetchgraph`:

- Các attributes được liệt kê làm **attribute nodes** trong graph được xem là EAGER cho fetch plan.
- Các attributes **không được liệt kê** được xem là LAZY theo ngữ nghĩa fetch graph.
- Tuy nhiên, provider **được phép fetch thêm state** ngoài graph, nên một graph tối thiểu không có nghĩa đảm bảo tuyệt đối về SQL hoặc trạng thái not-loaded của mọi field không liệt kê.

Ví dụ graph chỉ có Customer:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

query.setHint("jakarta.persistence.fetchgraph", graph);
```

Ý định: cần Customer cho use case, không yêu cầu Lines.

### 13.2. loadgraph

Khi dùng `loadgraph`:

- Attributes được liệt kê được tải theo EAGER.
- Attributes không được liệt kê **tuân theo fetch mapping tĩnh của chúng** (EAGER/LAZY).
- Provider vẫn có thể fetch thêm state theo khả năng tối ưu.

Ví dụ:

```java
query.setHint("jakarta.persistence.loadgraph", graph);
```

Nếu mapping có một association EAGER không được liệt kê, `loadgraph` vẫn tuân theo yêu cầu EAGER của mapping đó. `fetchgraph` có ngữ nghĩa khác về attributes không liệt kê.

### 13.3. Bảng phân biệt

| Thuộc tính | fetchgraph | loadgraph |
|---|---|---|
| Có trong graph | EAGER theo graph | EAGER theo graph |
| Không có trong graph, static EAGER | Được xem là LAZY theo fetch-graph semantics, subject to provider extra fetching | Vẫn EAGER theo static mapping |
| Không có trong graph, static LAZY | Được xem là LAZY | Tiếp tục LAZY hint |
| Có bảo đảm provider không fetch gì ngoài graph? | **Không** | **Không** |
| Có bắt buộc một SQL JOIN? | Không | Không |

**Điểm tinh tế:** chuẩn cho phép provider tải thêm state. Vì thế, entity graph giúp **diễn đạt nhu cầu tải**, nhưng không phải cơ chế bảo mật để ẩn dữ liệu, cũng không bảo đảm một số SQL cố định.

### 13.4. Fetch graph có thể được dùng để giảm static EAGER không?

Về ngữ nghĩa graph, attributes không được liệt kê được xem là LAZY. Nhưng hiệu quả thực tế còn phụ thuộc provider, association và khả năng trì hoãn. Không nên viết test mặc định rằng mọi static EAGER association bị loại khỏi SQL chỉ vì bạn không đưa nó vào fetchgraph.

Khi cần một response tối thiểu, một **DTO projection** vẫn có thể cho phép kiểm soát chính xác hơn những cột được chọn, thay vì bắt provider load đầy đủ entity và hy vọng mọi EAGER mapping được bỏ qua.

---

## 14. Named Entity Graph

Có thể khai báo graph cùng entity metadata.

Trên `PurchaseOrder`:

```java
@NamedEntityGraph(
    name = "PurchaseOrder.details",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode("lines")
    }
)
@Entity
public class PurchaseOrder {
    // ...
}
```

Imports:

```java
import jakarta.persistence.NamedEntityGraph;
import jakarta.persistence.NamedAttributeNode;
```

Sử dụng:

```java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.details");

Map<String, Object> hints = new HashMap<>();
hints.put("jakarta.persistence.loadgraph", graph);

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId, hints);
```

### 14.1. Vì sao named graph hữu ích?

- Một fetch plan có tên rõ ràng như `PurchaseOrder.details`.
- Dùng lại ở nhiều repository methods.
- Hạn chế lặp chuỗi attribute path.
- Gắn fetch plan với use case cụ thể thay vì luôn EAGER ở mapping.

Nhưng nếu graph quá lớn hoặc được dùng sai cho màn hình danh sách, vẫn tải thừa dữ liệu. Named graph **không tự động tối ưu**.

### 14.2. Subgraph cho quan hệ lồng nhau

Nếu cần từ Order qua Customer rồi lấy một vài thuộc tính/association của Customer, JPA hỗ trợ subgraph.

Ví dụ cấu trúc:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<Customer> customerGraph =
    graph.addSubgraph("customer", Customer.class);

customerGraph.addAttributeNodes("fullName");
```

Cần import `jakarta.persistence.Subgraph`. Ví dụ thể hiện cách cấu hình graph nested; các basic attributes như `fullName` thường default EAGER và việc đưa chúng vào graph ở đây giúp minh họa kỹ thuật. Với association khác sâu hơn, subgraph thể hiện nhu cầu tải từng tầng.

Không cần tạo subgraph chỉ để yêu cầu một basic field đã default EAGER, trừ khi use case/graph semantics thực sự cần.

---

## 15. Spring Data JPA @EntityGraph

Spring Data JPA cung cấp annotation riêng `org.springframework.data.jpa.repository.EntityGraph` để khai báo fetch graph cho repository method.

Ví dụ:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    Optional<PurchaseOrder> findWithCustomerById(Long id);
}
```

Import:

```java
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
```

Đây là **công cụ của Spring Data JPA**, không phải annotation `@EntityGraph` trong Jakarta Persistence API. Nó dùng khả năng Entity Graph của JPA dưới lớp repository.

Một repository method khác cần Order và Lines:

```java
@EntityGraph(attributePaths = {"customer", "lines"})
@Query("SELECT o FROM PurchaseOrder o WHERE o.id = :id")
Optional<PurchaseOrder> findDetails(@Param("id") Long id);
```

Cần import `@Query` và `@Param` của Spring Data. Query phải được thiết kế phù hợp với mapping và framework method.

### 15.1. Khi nào chọn Spring @EntityGraph thay vì JOIN FETCH?

Có thể chọn Entity Graph khi:

- Muốn tách fetch plan khỏi JPQL predicate.
- Có query method Spring Data gọn.
- Cần reuse named/dynamic graph.
- Muốn thay đổi association tải mà ít sửa business predicate.

Có thể chọn JOIN FETCH khi:

- Muốn thể hiện fetch association trực tiếp ngay trong JPQL.
- Cần phối hợp JOIN với query cụ thể và hiểu rõ cardinality.
- Cần dễ nhìn plan trong một câu query.

Cả hai đều không miễn nhiễm với N+1 hoặc Cartesian explosion khi graph có nhiều collections.

---

## 16. DTO projection: không phải lúc nào cũng cần entity graph

Nếu màn hình chỉ hiển thị:

```text
orderId, orderNumber, customerName
```

có thể dùng constructor projection:

```java
public record OrderListItem(
    Long id,
    String number,
    String customerName
) {}
```

JPQL:

```jpql
SELECT NEW demo.dto.OrderListItem(
    o.id,
    o.orderNumber,
    c.fullName
)
FROM PurchaseOrder o
JOIN o.customer c
ORDER BY o.id
```

Với projection này:

- Không nhất thiết materialize cả `PurchaseOrder` và `Customer` như managed entities.
- Không cần yêu cầu `o.customer` EAGER toàn hệ thống.
- Tránh đưa lazy proxy trực tiếp ra API.
- Có thể giảm cột và association được tải.

Cần DTO class/record có constructor khớp kiểu và đường dẫn Java đầy đủ ở `NEW`. Trong code chạy thực tế, định nghĩa class tại `demo.dto.OrderListItem` như JPQL tham chiếu.

### 16.1. EAGER không đồng nghĩa phải SELECT mọi cột trong mọi query

Nếu query chọn scalar/DTO, provider không nhất thiết tải entity graph đầy đủ chỉ vì mapping entity có EAGER association. Ý nghĩa static fetch type được xét trong ngữ cảnh **tải entity**, còn projection chọn những giá trị cụ thể.

Vì vậy, với API danh sách nhiều hàng, DTO thường là lựa chọn tốt hơn tranh luận “có nên đổi mọi association sang LAZY không”.

---

## 17. Lazy loading và ranh giới persistence context

Một Lazy association có thể được tải khi entity còn managed và context hỗ trợ truy cập dữ liệu:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

String customerName =
    order.getCustomer().getFullName();
```

Nếu provider chưa tải Customer và đang có context/connection hợp lệ, thao tác trên có thể kích hoạt query.

Nhưng sau:

```java
em.close();
```

truy cập association chưa khởi tạo:

```java
order.getCustomer().getFullName();
```

có thể thất bại. Trong Hibernate, lỗi thường gặp là `LazyInitializationException`. Đây là exception Hibernate-specific, không phải một tên lỗi JPA portable cho mọi provider.

### 17.1. Vì sao LAZY không đảm bảo sẽ phát lỗi sau close?

Vì LAZY chỉ là hint. Provider có thể đã tải Customer sớm, hoặc association đã được access trước close, hoặc đang dùng cache/context theo một cơ chế phù hợp. Khi đó field có thể đọc được.

Do vậy, **một test mong đợi chắc chắn lỗi sau close không phải cách chứng minh chuẩn LAZY**. Điều cần thiết là thiết kế use case tự lấy dữ liệu trước khi kết thúc context.

### 17.2. EAGER không đảm bảo toàn object graph an toàn sau close

Nếu `Order.customer` là EAGER, điều đó không có nghĩa:

```text
Order.customer.orders[].lines[].customer...
```

đều được tải đệ quy. EAGER gắn với **attribute/association được mapping hoặc yêu cầu trong graph**, không phải “mọi entity liên quan sâu vô hạn”.

### 17.3. Cách làm bền vững

- Chọn fetch plan trong service/repository.
- Tải những association cần dùng.
- Chuyển sang DTO trong transaction/context.
- Trả DTO cho API.
- Không để JSON serializer tự quét graph không giới hạn rồi phát sinh query.

---

## 18. Open EntityManager in View (OSIV)

Trong một số ứng dụng Spring web, OSIV giữ EntityManager mở đến cuối request, dù service transaction đã commit.

```text
HTTP request
   |
   +-- Open EntityManager
   |
   +-- Service @Transactional
   |     query Order
   |     commit transaction
   |
   +-- Controller / JSON serialization
   |     Lazy field có thể được truy cập khi EM còn mở
   |
   +-- Close EntityManager
```

### 18.1. Vì sao OSIV không giải quyết bản chất fetch plan?

Một serializer có thể chạm đến `orders`, `lines`, `customer` và phát hàng chục query ngoài transaction service. Điều này che N+1 ở tầng presentation và có thể đọc dữ liệu không đồng nhất về thời điểm.

**Context còn mở không đồng nghĩa transaction vẫn mở.** OSIV cũng không làm LAZY thành một yêu cầu bắt buộc theo chuẩn.

### 18.2. Lựa chọn nên cân nhắc

Với API stateless, dùng DTO và fetch plan rõ trong service thường dễ kiểm soát hơn việc dựa vào OSIV. Tuy nhiên, việc bật/tắt OSIV là quyết định framework/application, cần đánh giá những màn hình hiện tại, boundary và việc lazy loading đã được dựa vào ở đâu.

---

## 19. PersistenceUnitUtil.isLoaded: kiểm tra trạng thái tải

JPA cung cấp API để hỏi provider xem một entity/attribute đã được tải hay chưa.

```java
PersistenceUnitUtil util =
    emf.getPersistenceUnitUtil();

boolean customerLoaded =
    util.isLoaded(order, "customer");

boolean linesLoaded =
    util.isLoaded(order, "lines");
```

Import:

```java
import jakarta.persistence.PersistenceUnitUtil;
```

Ngoài ra có thể kiểm tra entity nói chung:

```java
boolean orderLoaded = util.isLoaded(order);
```

### 19.1. Diễn giải đúng

Nếu `isLoaded(order, "lines")` là `false`, provider cho biết attribute chưa được coi là loaded theo contract API. Nếu là `true`, nó đã loaded theo đánh giá của provider.

Nhưng **isLoaded không cam kết số SQL đã chạy**:

- Có thể được tải từ first-level cache.
- Có thể dùng second-level cache.
- Có thể được fetch join.
- Có thể được provider tải sớm dù mapping LAZY.
- Có thể attribute đã được truy cập trước khi bạn kiểm tra.

### 19.2. Ví dụ kiểm tra trước/sau access

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

PersistenceUnitUtil util =
    emf.getPersistenceUnitUtil();

System.out.println(
    "Before access: " + util.isLoaded(order, "lines"));

int count = order.getLines().size();

System.out.println(
    "After access: " + util.isLoaded(order, "lines"));
```

Với một provider lazy loading collection thông dụng, bạn có thể thấy `false` trước access và `true` sau đó. Nhưng vì LAZY là hint, kết quả đầu tiên **có thể đã true** mà không vi phạm JPA.

### 19.3. Test SQL vẫn quan trọng

`isLoaded` phù hợp để kiểm tra trạng thái JPA, nhưng để phát hiện N+1, cần đo:

- Số SQL SELECT.
- Thời gian query.
- Số hàng trả về.
- Số association instances.
- Cache hits/misses.
- Query plan và index.

Đừng dùng riêng `isLoaded` để kết luận một query đã tối ưu.

---

## 20. First-level cache ảnh hưởng quan sát thế nào?

Trong một persistence context, JPA giữ identity map. Nếu hai Order tham chiếu cùng Customer, provider có thể chỉ cần một managed `Customer` instance.

Ví dụ:

```text
Order#101.customer_id = 10
Order#102.customer_id = 10
Order#103.customer_id = 20
```

Nếu tất cả Order được tải trong một context, số query phụ cần thiết cho Customers không nhất thiết bằng ba; Customer#10 có thể được tái sử dụng.

### 20.1. Vì sao test N+1 cần context sạch?

Nếu trước đó test đã load tất cả Customers trong cùng EntityManager, một query Order có thể không phát SELECT bổ sung, khiến người học tưởng mapping hoàn toàn không có N+1.

Để quan sát:

1. Tạo dữ liệu nền và commit.
2. Đóng EntityManager cũ.
3. Mở EntityManager mới.
4. Chạy đúng một use case.
5. Ghi SQL.
6. Lặp lại với cùng tập dữ liệu và một fetch plan khác.

Second-level cache nếu được bật cũng có thể ảnh hưởng kết quả; cần hiểu cách cache được cấu hình và kiểm soát trong benchmark.

---

## 21. @Basic(fetch = LAZY) và bytecode enhancement

Fetch strategy trên association entity thường có thể dựa vào proxy hoặc cơ chế instrumentation. Với một **basic field**, provider có thể cần khả năng theo dõi truy cập field để chỉ tải giá trị lúc cần.

Ví dụ:

```java
@Lob
@Basic(fetch = FetchType.LAZY)
@Column(name = "document_body")
private String documentBody;
```

Khi tải Document:

```java
Document document =
    em.find(Document.class, documentId);
```

Ứng dụng có thể muốn chỉ tải `id/title`, chưa tải `documentBody`. Nhưng **LAZY trên basic attribute là hint**, không có bảo đảm portable rằng LOB sẽ bị trì hoãn.

### 21.1. Provider có thể cần enhancement

Với một số cấu hình Hibernate ORM, bytecode enhancement là yếu tố cần để lazy basic attributes hoạt động theo kỳ vọng. Nếu không có enhancement, provider có thể tải field ngay.

Không suy luận rằng chỉ thêm annotation:

```java
@Basic(fetch = FetchType.LAZY)
```

là chắc chắn database không SELECT cột LOB.

### 21.2. Khi field lớn thật sự quan trọng

Một mô hình thay thế:

```text
Document
  id
  title
  createdAt

DocumentContent
  document_id
  body
```

Tách nội dung lớn sang entity/bảng riêng có thể cho phép query danh sách Document tải ít dữ liệu hơn và yêu cầu nội dung theo use case. Nhưng điều đó tạo thêm mapping/schema/transaction considerations, nên chỉ chọn khi có lợi ích đã được đánh giá.

### 21.3. @OneToOne(fetch=LAZY) cũng có giới hạn

Đặc biệt ở inverse side của quan hệ một-một, provider đôi khi phải xác định association có tồn tại hay không và gặp khó khăn khi dùng proxy thuần. Một số tình huống cần bytecode enhancement để lazy loading hoạt động tối ưu.

Do đó, không biến việc `@OneToOne(fetch=LAZY)` vẫn phát SELECT thành kết luận chắc chắn provider vi phạm chuẩn. LAZY là hint; hãy kiểm tra giải pháp mapping và enhancement của provider đang dùng.

---

## 22. @ElementCollection và fetch

`@ElementCollection` dùng cho collection các basic/embeddable values, có default LAZY:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tags",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

Khi load Customer, tags có thể chưa được tải; khi code gọi `customer.getTags()`, provider có thể truy vấn collection table.

Nếu cần tags cho use case:

- Có thể dùng fetch join hoặc entity graph theo hỗ trợ JPQL/provider.
- Có thể truy vấn tags riêng nếu cần lọc/sắp xếp theo collection.
- Đừng tự động chuyển tất cả `@ElementCollection` sang EAGER vì một màn hình cần tags.

### 22.1. Collection lớn có chi phí đặc thù

Tải một Customer có 50.000 tags không giống tải một association nhỏ. Dù có thể fetch được bằng JOIN, kết quả SQL có thể lớn. Hãy phân biệt “muốn đầy đủ collection” với “muốn top 20 tags” — JPA collection fetch không phải API phân trang phần tử một cách tự nhiên.

---

## 23. Fetch plan khi query nhiều root entities

Giả sử query:

```jpql
SELECT c
FROM Customer c
ORDER BY c.id
```

Nếu `Customer.orders` là LAZY, provider có thể chỉ tải Customers trước, tùy kế hoạch.

Nhưng code:

```java
for (Customer c : customers) {
    System.out.println(c.getOrders().size());
}
```

có thể kích hoạt một SELECT collection cho mỗi Customer.

Nếu mục tiêu chỉ là đếm đơn hàng, tốt hơn là **aggregate query**:

```jpql
SELECT c.id, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id
ORDER BY c.id
```

Ở đây không cần materialize `c.orders` cho từng Customer. Kết quả `COUNT(o)` là `Long` theo JPQL aggregate semantics.

### 23.1. Không fetch cả collection chỉ để count

Thay vì:

```java
customer.getOrders().size();
```

cho hàng nghìn Customers, query count theo nhóm có thể đọc ít dữ liệu hơn, đặc biệt với collection rất lớn. Nhưng SQL plan và index vẫn cần đo.

### 23.2. Khi cần tổng hoặc thống kê

Tương tự, có thể dùng:

```jpql
SELECT c.id, SUM(o.totalAmount)
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id
```

nếu entity `PurchaseOrder` có persistent attribute `totalAmount`. Entity ví dụ ở phần 5 chưa khai báo field này; đây là một minh họa mở rộng của domain. Không tải toàn bộ Orders chỉ để tính tổng khi database có thể aggregate hiệu quả.

---

## 24. Mapping EAGER có phải luôn sai?

Không. EAGER là yêu cầu có mục đích.

Một số tình huống có thể cân nhắc EAGER:

- Association nhỏ và gần như mọi use case cần.
- Entity chỉ dùng trong ngữ cảnh đã được kiểm soát, không nằm ở graph lớn.
- Provider/database đã được benchmark và có kế hoạch tải phù hợp.
- Một field basic cần sẵn sàng để sử dụng gần như luôn luôn.
- Hệ thống legacy có contract yêu cầu dữ liệu liên quan luôn sẵn sàng khi entity được truy xuất.

Nhưng cần nhận thức:

- EAGER ở static mapping áp dụng rộng cho nhiều đường truy vấn entity.
- Một association “luôn cần” ở use case này có thể không cần ở use case khác.
- EAGER có thể kéo theo SQL phụ khi query trên hàng loạt root.
- EAGER không tự giới hạn depth của object graph theo business boundary.
- Thay đổi EAGER sang LAZY có thể ảnh hưởng code hiện đang dựa vào association sẵn sàng sau context close.

**Quy tắc thực tế:** với hệ thống có nhiều endpoints, thường nên giữ association có khả năng phình to hoặc ít được dùng ở LAZY, rồi bổ sung fetch plan cho use case cụ thể. Đây là khuyến nghị thiết kế, không phải một ràng buộc chuẩn bắt buộc mọi association phải LAZY.

---

## 25. Có nên đổi tất cả @ManyToOne thành LAZY?

Không thể trả lời “luôn luôn”, nhưng cần biết `@ManyToOne` mặc định EAGER nên có nguy cơ tải thừa.

Một hướng phổ biến:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

sau đó ở query cần Customer:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.id = :orderId
```

Cách này làm fetch behavior **rõ ở use case**. Tuy vậy:

- LAZY vẫn là hint, provider có thể fetch sớm.
- Cần bảo đảm dữ liệu cần dùng đã được tải trước khi context đóng.
- Query riêng có thể phải điều chỉnh khi màn hình thay đổi.
- Nếu code cũ ngầm dựa trên EAGER, chuyển mapping cần migration/test ở service boundary.

### 25.1. Không biến LAZY thành cách che N+1

Chỉ đổi EAGER sang LAZY có thể chuyển chi phí từ lúc query sang lúc serialize hoặc loop qua associations. Muốn tối ưu, phải kiểm tra **cả đường đi request**.

---

## 26. EAGER, LAZY và @Version/locking

Fetch strategy liên quan dữ liệu nào được tải, không trực tiếp quyết định concurrency control.

Nếu entity có:

```java
@Version
private Long version;
```

provider có thể dùng version để phát hiện concurrent updates. Nhưng:

- EAGER không tự thêm optimistic lock cho association.
- LAZY không tự làm dữ liệu luôn mới.
- Entity đã managed trong context dài có thể giữ stale state bất kể fetch type.
- `refresh()` là thao tác yêu cầu nạp lại state; nó cũng không thay thế transaction isolation hay xử lý conflict.

Một query fetch join Customer không làm toàn bộ object graph “được khóa” nếu không có lock mode phù hợp. Đừng xem fetch plan như cơ chế transaction locking.

---

## 27. EAGER, LAZY và cache

First-level cache thuộc persistence context; second-level cache có thể được provider cấu hình để tái sử dụng entity state qua contexts.

Khi quan sát:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);
```

SQL count có thể khác nếu:

- Order/Customer đã managed trong context.
- Second-level cache chứa data.
- Query cache hoặc batch fetching được bật.
- Truy vấn có entity graph.
- SQL provider dùng JOIN hoặc secondary SELECTs.

FetchType không định nghĩa chính xác cache policy. Một association LAZY có thể được giải quyết từ cache khi access; một association EAGER có thể không tạo SQL nếu đã có trong context/cache.

### 27.1. SQL count không phải tiêu chí duy nhất

Một query JOIN lớn tải 100.000 hàng có thể tệ hơn 10 query nhỏ có index tốt. Ngược lại, N+1 qua mạng cũng có thể gây độ trễ rất lớn.

Cần đo:

- SQL query count.
- Rows/bytes returned.
- Time spent in database và network.
- Memory retention của persistence context.
- Latency thực tế của endpoint.
- Cache hit rate.
- Correctness của result set.

**Không tối ưu theo một con số N+1 duy nhất mà bỏ qua số hàng và nghiệp vụ.**

---

## 28. Batch fetching và subselect fetching

Một số provider, đặc biệt Hibernate, có tùy chọn batch fetching giúp giảm N+1 khi nhiều associations LAZY được truy cập.

Ví dụ riêng Hibernate:

```java
@BatchSize(size = 32)
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
```

`@BatchSize` thuộc `org.hibernate.annotations`, **không phải annotation chuẩn Jakarta Persistence**.

Một provider có thể biến nhiều SELECT riêng thành các SELECT xử lý nhóm IDs:

```sql
SELECT ...
FROM purchase_orders
WHERE customer_id IN (?, ?, ?, ...);
```

Hibernate cũng có những chế độ fetch khác như subselect fetching, nhưng chúng là **implementation-specific optimizations**. Khi bài toán yêu cầu portability, hãy tách rõ:

- **Chuẩn JPA:** FetchType, JPQL JOIN FETCH, Entity Graph, `PersistenceUnitUtil`.
- **Provider extension:** Hibernate `@BatchSize`, `@Fetch`, bytecode enhancement options, các cấu hình batch/subselect.

Không nên dùng API provider-specific mà gọi là “bảo đảm của JPA”.

---

## 29. Cách đọc SQL để hiểu fetch plan

### 29.1. Tình huống A: EAGER to-one qua JOIN

```text
Query JPQL: SELECT o FROM PurchaseOrder o

SQL:
  SELECT ... FROM purchase_orders o
  JOIN customers c ON ...
```

Association Customer được tải cùng SQL theo một kế hoạch.

### 29.2. Tình huống B: EAGER to-one qua SELECTs riêng

```text
Query JPQL: SELECT o FROM PurchaseOrder o

SQL:
  SELECT ... FROM purchase_orders
  SELECT ... FROM customers WHERE id=?
  SELECT ... FROM customers WHERE id=?
  ...
```

Association vẫn có thể thỏa EAGER requirement nhưng có nhiều round trips.

### 29.3. Tình huống C: LAZY collection

```text
SELECT o FROM PurchaseOrder o
    |
    +-- SELECT purchase_orders

Sau:
  order.getLines().size()
    |
    +-- SELECT order_lines WHERE order_id=?
```

Đây là cách lazy collection thường được triển khai, nhưng provider có quyền tải sớm dù LAZY.

### 29.4. Tình huống D: JOIN FETCH collection

```text
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines

SQL:
  SELECT ...
  FROM purchase_orders o
  LEFT JOIN order_lines l ON l.order_id = o.id
```

Lệnh JPQL yêu cầu association được fetch; số rows SQL có thể tăng theo số Lines.

### 29.5. Điều phải ghi lại khi thử nghiệm

| Thông tin | Vì sao cần? |
|---|---|
| JPQL query | Biết đường truy vấn thực sự |
| Entity mappings | Biết static EAGER/LAZY |
| Entity Graph/hints | Biết fetch plan động |
| Dữ liệu mẫu | Đếm số root và child |
| Context có sạch không | First-level cache ảnh hưởng SQL |
| Second-level cache | Có thể che queries |
| SQL statements | Nhận diện JOIN, secondary SELECT, batch |
| Rows returned | Nhận diện JOIN explosion |
| Loaded-state | Kiểm tra `isLoaded` |
| Endpoint latency | Đo ảnh hưởng thực tế |

Không suy ra hiệu năng chỉ từ annotation hoặc một SQL snapshot chưa có dữ liệu đủ lớn.

---

## 30. Thực hành A — Kiểm tra fetch defaults

1. Tạo `Customer`, `PurchaseOrder`, `OrderLine` như ví dụ.
2. Kiểm tra `@ManyToOne` khi **không** khai báo `fetch`.
3. Kiểm tra `@OneToMany` khi không khai báo `fetch`.
4. Viết bảng default của `@OneToOne`, `@ManyToMany`, `@ElementCollection` và `@Basic`.
5. Giải thích vì sao default EAGER và LAZY có mức độ bảo đảm khác nhau.
6. Không dùng số SQL quan sát được để thay định nghĩa của chuẩn.

## 31. Thực hành B — EAGER không bắt buộc JOIN

1. Tạo 50 Orders thuộc 10 Customers.
2. Trong một mapping thử, để `@ManyToOne` mặc định EAGER.
3. Mở EntityManager mới và chạy `SELECT o FROM PurchaseOrder o`.
4. Bật SQL log.
5. Ghi xem Customer được tải bằng JOIN, SELECTs riêng hay batch.
6. Ghi số Customers khác nhau và số SELECT phụ.
7. Nếu chỉ thấy một SQL, giải thích vì sao điều đó **không có nghĩa** mọi provider đều bắt buộc JOIN.
8. Nếu có nhiều SQL, giải thích vì sao EAGER vẫn có thể đúng chuẩn.

## 32. Thực hành C — LAZY không phải ràng buộc tuyệt đối

1. Đổi `PurchaseOrder.customer` thành `fetch=LAZY`.
2. Tạo EntityManager mới.
3. Load một Order.
4. Gọi `emf.getPersistenceUnitUtil().isLoaded(order, "customer")`.
5. Quan sát SQL log trước khi truy cập Customer.
6. Truy cập `order.getCustomer().getFullName()`.
7. Kiểm tra isLoaded lần nữa.
8. Giải thích nếu provider đã tải sớm ngay từ đầu.
9. Không viết assertion portable bắt buộc isLoaded ban đầu là false.

## 33. Thực hành D — Phân biệt JOIN và JOIN FETCH

Chạy hai query:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.fullName LIKE :prefix
```

và:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.orderNumber LIKE :prefix
```

1. Ghi tên cột và association được tải.
2. So sánh SQL.
3. Kiểm tra `isLoaded(order, "customer")`.
4. Giải thích vì sao JOIN để filter không đồng nghĩa FETCH.
5. Không đặt điều kiện liên quan đến Customer theo cú pháp alias fetch join không portable; dùng query riêng phù hợp nếu cần.
6. Đối chiếu kết quả business trước khi so sánh hiệu năng vì hai WHERE trong ví dụ lọc các thuộc tính khác nhau.

## 34. Thực hành E — Fetch join một collection

1. Tạo Order có 10 Lines.
2. Dùng `LEFT JOIN FETCH o.lines`.
3. Ghi số hàng SQL.
4. So sánh số root entities được trả.
5. Dùng `DISTINCT` trong JPQL.
6. Quan sát xem SQL DISTINCT và de-duplication hoạt động thế nào trên provider.
7. Thử hai collections để thấy nguy cơ nhân hàng, nhưng không dùng trên production.
8. Giải thích vì sao fetch join một collection lớn không phải luôn tối ưu.

## 35. Thực hành F — Entity Graph

1. Tạo dynamic graph có `customer`.
2. Dùng `jakarta.persistence.fetchgraph` khi `em.find`.
3. Kiểm tra Customer và Lines đã loaded hay chưa.
4. Dùng `jakarta.persistence.loadgraph` với cùng graph.
5. Thêm một association static EAGER khác trong một mô hình thử.
6. So sánh ngữ nghĩa **unspecified attributes** giữa fetchgraph và loadgraph.
7. Kiểm tra SQL thực tế và ghi chú provider được phép fetch thêm.
8. Tạo named graph `PurchaseOrder.details` gồm customer và lines.
9. Gọi named graph bằng `em.getEntityGraph`.
10. Giải thích khi nào entity graph dễ bảo trì hơn JOIN FETCH.

## 36. Thực hành G — Phân trang và collection fetch

1. Tạo 100 Orders, mỗi Order có 5–20 Lines.
2. Query `LEFT JOIN FETCH o.lines`.
3. Áp dụng `setFirstResult(0)` và `setMaxResults(20)`.
4. Ghi warning/log hoặc hành vi provider; không coi chúng là portable.
5. Dùng chiến lược hai bước: query 20 IDs rồi fetch Lines theo IDs.
6. Sắp xếp kết quả đúng thứ tự ID page.
7. So sánh số hàng SQL và thời gian.
8. Thảo luận khi nào dùng DTO projection hoặc batch fetching tốt hơn.

## 37. Thực hành H — Đóng EntityManager

1. Tạo Order có Customer và Lines.
2. Tải Order trong EM mới với mapping LAZY.
3. Kiểm tra loaded-state trước khi đóng.
4. Đóng EntityManager.
5. Thử truy cập association chưa loaded trong môi trường Hibernate.
6. Quan sát `LazyInitializationException` nếu xảy ra.
7. Lặp lại với JOIN FETCH hoặc entity graph để tải dữ liệu cần thiết trước close.
8. Chuyển sang DTO trong transaction và đọc DTO sau close.
9. Giải thích vì sao EAGER ở một association không có nghĩa mọi nested association đã được tải.

## 38. Thực hành I — @Basic LAZY

1. Tạo entity Document có title và `@Lob` body.
2. Thêm `@Basic(fetch=LAZY)` cho body.
3. Kiểm tra SQL khi `find` và khi đọc body.
4. Thử với provider/enhancement config khác nếu có.
5. Giải thích vì sao LAZY trên basic field không phải bảo đảm chuẩn rằng cột LOB không được SELECT ban đầu.
6. So sánh với mô hình tách DocumentContent riêng để tải theo use case.

## 39. Checklist quyết định fetch plan

| Câu hỏi | Gợi ý |
|---|---|
| Association được dùng trong bao nhiêu use case? | Đừng bật EAGER chỉ vì một màn hình cần |
| Association là to-one hay to-many? | Cân nhắc kích thước và cardinality |
| Default hiện tại là gì? | To-one EAGER, to-many LAZY |
| Có cần entity đầy đủ không? | Nếu không, cân nhắc DTO |
| Có query theo danh sách hàng trăm root không? | Kiểm tra N+1 và join explosion |
| Có truy cập association sau khi context đóng không? | Tải trước hoặc dùng DTO |
| Có collection lớn không? | Tránh fetch join bừa bãi |
| Có phân trang không? | Tránh collection fetch join không kiểm soát |
| Có nhiều collections được fetch cùng lúc không? | Coi chừng Cartesian multiplication |
| Có entity graph không? | Chọn fetchgraph/loadgraph đúng semantics |
| Có @Basic LAZY field lớn không? | Kiểm tra enhancement/provider support |
| Có OSIV bật không? | SQL có thể chạy ở view/serializer |
| Có cache/batch fetching không? | Kết quả SQL count phụ thuộc cấu hình |
| Có đo SQL và rows không? | Không đoán theo annotation |
| Có test trên provider/database thật không? | Spec không quy định chiến lược SQL chính xác |
| Có lock/concurrency requirements không? | Fetch không thay thế locking |
| Có share entity across threads không? | EntityManager không được dùng đồng thời tùy tiện |

---

## 40. Những hiểu lầm thường gặp

### 40.1. “EAGER luôn JOIN”

Sai. EAGER chỉ yêu cầu eager fetch; provider có thể dùng SELECT phụ, JOIN hoặc chiến lược khác.

### 40.2. “LAZY bắt buộc chưa tải cho đến khi getter được gọi”

Sai theo mức độ bảo đảm của chuẩn: LAZY là **hint**, provider được phép tải sớm.

### 40.3. “Cứ EAGER hết sẽ hết N+1”

Sai. EAGER to-one có thể dùng secondary SELECTs, dẫn đến N+1. EAGER to-many có thể tải quá nhiều dữ liệu.

### 40.4. “Cứ LAZY hết sẽ nhanh”

Không chắc. Nếu use case loop qua mọi child, LAZY có thể tạo N+1 queries.

### 40.5. “JOIN trong JPQL tự là JOIN FETCH”

Sai. JOIN thường phục vụ truy vấn/lọc; JOIN FETCH là yêu cầu tải association.

### 40.6. “JOIN FETCH collection luôn phù hợp phân trang”

Không. Một root có nhiều child rows, LIMIT/OFFSET có thể không còn áp dụng đúng hạt dữ liệu; provider có thể phân trang trong memory.

### 40.7. “fetchgraph bảo đảm không fetch thêm field nào”

Sai. Provider được phép tải thêm state, dù graph không yêu cầu.

### 40.8. “loadgraph bỏ qua static EAGER”

Sai. Unspecified attributes trong loadgraph vẫn theo static mapping.

### 40.9. “@Basic(fetch=LAZY) chắc chắn trì hoãn LOB”

Không portable; provider có thể cần bytecode enhancement và được phép fetch sớm.

### 40.10. “EAGER nghĩa toàn bộ graph được load”

Sai. EAGER áp dụng cho những attributes được mapping hoặc yêu cầu cụ thể, không tự fetch đệ quy toàn bộ nested associations.

### 40.11. “EAGER/LAZY quyết định cascade”

Không. Fetch strategy và cascade lifecycle là hai khía cạnh độc lập.

### 40.12. “EAGER đảm bảo transaction vẫn hoạt động sau khi service trả về”

Không. Fetch plan không kéo dài transaction/context.

### 40.13. “OSIV là giải pháp tối ưu lazy loading”

Không nhất thiết. OSIV có thể che N+1 và cho phép SQL ở view ngoài transaction service. DTO/fetch plan rõ ràng có thể dễ kiểm soát hơn.

### 40.14. “isLoaded false là thước đo duy nhất của hiệu năng”

Không. isLoaded chỉ cho biết loaded state theo provider, không phản ánh rows, latency hoặc query plan.

### 40.15. “Một SELECT luôn nhanh hơn nhiều SELECT”

Không luôn đúng. Một JOIN lớn với hàng trăm nghìn rows có thể tốn hơn một kế hoạch batch nhỏ. Cần đo workload.

### 40.16. “Thay đổi static fetch từ EAGER sang LAZY không ảnh hưởng API”

Có thể ảnh hưởng code đang truy cập association ngoài context. Cần test service/serialization boundary, không chỉ compile.

---

## 41. Câu hỏi ôn tập

1. Theo chuẩn JPA, EAGER là yêu cầu hay gợi ý?
2. LAZY là yêu cầu hay gợi ý?
3. Provider có được phép eagerly fetch một association có `fetch=LAZY` không?
4. EAGER có bắt buộc sử dụng SQL JOIN không?
5. Vì sao EAGER có thể tạo N+1?
6. Vì sao LAZY có thể tạo N+1?
7. `@ManyToOne` mặc định EAGER hay LAZY?
8. `@OneToOne` mặc định EAGER hay LAZY?
9. `@OneToMany` mặc định EAGER hay LAZY?
10. `@ManyToMany` mặc định EAGER hay LAZY?
11. `@ElementCollection` mặc định EAGER hay LAZY?
12. `@Basic` mặc định EAGER hay LAZY?
13. Vì sao LAZY trên basic field có thể cần bytecode enhancement?
14. Vì sao inverse `@OneToOne(fetch=LAZY)` có thể khó triển khai tối ưu?
15. JOIN và JOIN FETCH khác nhau thế nào trong JPQL?
16. Khi nào nên dùng LEFT JOIN FETCH thay JOIN FETCH?
17. Vì sao fetch join to-many tăng số SQL rows?
18. `DISTINCT` có loại bỏ chi phí JOIN không?
19. Vì sao phân trang trên collection fetch join dễ gặp vấn đề?
20. Chiến lược hai bước IDs rồi fetch associations hoạt động ra sao?
21. Entity Graph là gì và được dùng ở đâu?
22. `fetchgraph` xử lý unspecified attributes theo semantics nào?
23. `loadgraph` xử lý unspecified attributes theo semantics nào?
24. Provider có được phép fetch thêm state ngoài entity graph không?
25. Khi nào nên dùng DTO projection thay vì load entity?
26. Vì sao DTO thường phù hợp danh sách lớn?
27. `PersistenceUnitUtil.isLoaded` cho biết điều gì và không cho biết điều gì?
28. Vì sao một context đã load Customer có thể che hiện tượng N+1?
29. Second-level cache ảnh hưởng benchmark ra sao?
30. Hibernate `@BatchSize` có phải annotation JPA chuẩn không?
31. OSIV có kéo dài transaction service đến hết request không?
32. Vì sao truy cập LAZY sau close có thể gây lỗi?
33. Nếu LAZY association đã được tải sớm, truy cập sau close có thể thành công không?
34. EAGER có tự khóa entity hoặc bảo đảm dữ liệu mới nhất không?
35. Khi nào EAGER static mapping có thể là lựa chọn có chủ đích?
36. Vì sao không nên mặc định chuyển mọi association sang EAGER?
37. Vì sao static fetch plan cần được bổ sung bằng kế hoạch theo use case?
38. Với Customer có 10.000 Orders, bạn có nên fetch join toàn bộ để hiển thị tên Customer không?
39. Nếu chỉ muốn đếm Orders, bạn dùng LAZY collection iteration hay COUNT query?
40. Những số liệu nào cần theo dõi khi tối ưu fetch plan?

---

## 42. Bảng ghi nhớ cuối bài

| Câu hỏi | Trả lời ngắn |
|---|---|
| **EAGER có nghĩa gì?** | Provider được yêu cầu fetch sớm attribute/association |
| **LAZY có nghĩa gì?** | Provider được gợi ý trì hoãn, nhưng có thể fetch sớm |
| **EAGER đồng nghĩa JOIN?** | Không |
| **LAZY bảo đảm không có SELECT ban đầu?** | Không |
| **EAGER loại bỏ N+1?** | Không |
| **LAZY loại bỏ N+1?** | Không |
| **Mặc định @ManyToOne/@OneToOne?** | EAGER |
| **Mặc định @OneToMany/@ManyToMany?** | LAZY |
| **Mặc định @ElementCollection?** | LAZY |
| **Mặc định @Basic?** | EAGER |
| **Muốn fetch association cho một query?** | JPQL JOIN FETCH hoặc Entity Graph |
| **Muốn chỉ lấy vài cột?** | DTO/scalar projection |
| **fetchgraph?** | Graph nodes EAGER, unspecified LAZY theo semantics, provider có thể fetch thêm |
| **loadgraph?** | Graph nodes EAGER, unspecified theo static mapping |
| **Muốn biết attribute đã loaded?** | `PersistenceUnitUtil.isLoaded` |
| **Muốn biết có N+1?** | SQL log/metrics trên workload thật |
| **Có phân trang + to-many collection?** | Thận trọng với JOIN FETCH; cân nhắc hai bước |
| **Lazy loading sau close?** | Có thể thất bại nếu chưa loaded |
| **FetchType có thay thế transaction?** | Không |
| **FetchType có thay thế cascade?** | Không |
| **Hibernate batch/subselect?** | Optimization riêng provider, không phải bảo đảm JPA |

### Sơ đồ tổng hợp

```text
                       ENTITY MAPPING
                            |
                  +---------+---------+
                  |                   |
               EAGER                 LAZY
                  |                   |
          Yêu cầu tải sớm       Gợi ý trì hoãn
                  |                   |
           Không bắt JOIN      Có thể tải sớm
                  |                   |
                  +---------+---------+
                            |
                     QUERY USE CASE
                            |
                 +----------+----------+
                 |          |          |
             JOIN FETCH  EntityGraph  DTO query
                 |          |          |
                 +----------+----------+
                            |
                      PROVIDER SQL
                            |
                 JOIN / SELECT / BATCH
                            |
                   ĐO SQL, ROWS, TIME
                            |
                 CONTEXT / TRANSACTION
```

**Nguyên tắc cuối bài:** trong phạm vi **chuẩn Jakarta Persistence**, **EAGER là yêu cầu tải sớm**, còn **LAZY chỉ là gợi ý trì hoãn** mà provider được phép thực hiện theo khả năng. Hai giá trị này không chỉ định số SQL statement hay bắt buộc JOIN. Một fetch plan tốt phải dựa trên **đường truy cập thực tế của use case**: dùng static mapping hợp lý, chủ động chọn `JOIN FETCH`, Entity Graph hoặc DTO, kiểm soát collection size/pagination và xác minh bằng SQL thực tế thay vì suy luận tuyệt đối từ annotation.

