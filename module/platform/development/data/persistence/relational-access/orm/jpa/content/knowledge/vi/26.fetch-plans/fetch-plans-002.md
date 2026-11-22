# Giá trị fetch mặc định của từng loại quan hệ theo đặc tả JPA

Khi ánh xạ quan hệ giữa các entity trong **Jakarta Persistence (JPA)**, một câu hỏi quan trọng là: **Nếu không khai báo `fetch`, dữ liệu liên quan sẽ được tải ngay hay chỉ tải khi cần?** Câu trả lời không giống nhau giữa `@ManyToOne`, `@OneToOne`, `@OneToMany` và `@ManyToMany`.

Đây là các giá trị mặc định do đặc tả JPA quy định:

| Annotation quan hệ | Giá trị mặc định của `fetch` | Ý nghĩa ở mức hợp đồng JPA |
| --- | --- | --- |
| `@ManyToOne` | **`FetchType.EAGER`** | Entity liên quan phải được lấy theo chiến lược tải chủ động của provider, trừ khi một fetch plan có hiệu lực thay đổi yêu cầu theo quy tắc của nó. |
| `@OneToOne` | **`FetchType.EAGER`** | Quan hệ đơn trị mặc định được yêu cầu tải chủ động. |
| `@OneToMany` | **`FetchType.LAZY`** | Quan hệ tập hợp mặc định được yêu cầu trì hoãn tải; `LAZY` là gợi ý cho provider. |
| `@ManyToMany` | **`FetchType.LAZY`** | Tập hợp nhiều-nhiều mặc định được yêu cầu trì hoãn tải; `LAZY` là gợi ý cho provider. |

Hai câu cần ghi nhớ ngay từ đầu:

> **Quan hệ đơn trị** `@ManyToOne` và `@OneToOne` mặc định **EAGER**. **Quan hệ đa trị** `@OneToMany` và `@ManyToMany` mặc định **LAZY**.

> **EAGER không đồng nghĩa SQL JOIN. LAZY không phải lời hứa rằng provider tuyệt đối không tải dữ liệu sớm.** Đây là các yêu cầu/gợi ý về kế hoạch tải entity, không phải cú pháp SQL cố định.

Bài học này giải thích chuẩn mặc định, ngữ nghĩa hợp đồng, tác động tới SQL và hiệu năng, các cách ghi đè kế hoạch tải theo use case, cách tránh N+1, hiện tượng `LazyInitializationException`, giới hạn pagination và thực hành với `JOIN FETCH`, entity graphs, Criteria API, DTO projection và Spring Data JPA.

## 1. Fetch plan là gì?

Một entity thường liên kết với nhiều entity khác. Ví dụ một đơn hàng có khách hàng, địa chỉ giao hàng, các dòng hàng và các nhãn phân loại:

```text
                           PurchaseOrder
                           /     |      \
                          /      |       \
                    Customer  Shipment   OrderLine (nhiều)
                                          |
                                        Product

                    PurchaseOrder ---- Tag (nhiều-nhiều)
```

Giả sử ứng dụng gọi:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 100L);
```

Câu hỏi không chỉ là “có lấy được PurchaseOrder hay không?” mà còn là:

- Có tải ngay `Customer` của đơn không?
- Có tải ngay `Shipment` hay chưa?
- Có tải toàn bộ `OrderLine` khi chỉ cần xem mã đơn không?
- Có tải tất cả `Tag` của đơn không?
- Nếu dòng hàng liên kết đến `Product`, có tải tiếp product không?
- Nếu entity được đọc qua một câu JPQL khác, chiến lược có thay đổi không?

**Fetch plan** là cách mô tả những association hoặc thuộc tính nào được tải cùng entity và ở mức độ nào. Nó có thể được hình thành từ:

1. **Fetch metadata tĩnh** trên entity: `@ManyToOne(fetch = ...)`, `@OneToMany(fetch = ...)` và tương tự.
2. **Yêu cầu tải của truy vấn**: ví dụ `JOIN FETCH` trong JPQL hoặc Criteria.
3. **Entity graph**: `fetchgraph` hoặc `loadgraph`.
4. **Cấu hình và chiến lược của provider**: batch loading, secondary SELECT, cache, bytecode enhancement, các tối ưu riêng.
5. **Trạng thái persistence context và cache**: entity liên quan đã managed hoặc đã được tải chưa.

Fetch plan ảnh hưởng đến **thời điểm và phạm vi dữ liệu được cung cấp cho entity graph Java**. Còn kế hoạch SQL cụ thể — JOIN, SELECT riêng, batch query — là quyết định thực thi của provider/database.

### 1.1. Hai kiểu yêu cầu tải

`FetchType` trong JPA có hai giá trị:

```java
public enum FetchType {
    LAZY,
    EAGER
}
```

Ý nghĩa:

- **`EAGER`**: yêu cầu provider phải lấy dữ liệu một cách chủ động theo hợp đồng fetch đang có hiệu lực.
- **`LAZY`**: gợi ý rằng provider có thể trì hoãn việc tải dữ liệu đến khi được truy cập; provider vẫn được phép tải sớm hơn.

Đây là sự **bất đối xứng quan trọng** của đặc tả: `LAZY` mang tính *hint*, còn `EAGER` mang tính *requirement* trong ngữ cảnh mapping tĩnh. Vì vậy không nên viết test mặc định đòi hỏi “LAZY luôn chưa tải khi `find` trả về” trên tất cả provider, nhưng có thể thiết kế code dựa vào những ràng buộc eager theo fetch plan.

### 1.2. Fetch type không bảo đảm số lượng SQL

Hai provider có thể cùng thỏa một mapping:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
```

nhưng tạo các cách tải khác nhau:

**Cách A — SQL JOIN:**

```sql
SELECT o.id, o.customer_id, c.id, c.name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = ?;
```

**Cách B — hai SELECT:**

```sql
SELECT o.id, o.customer_id
FROM purchase_orders o
WHERE o.id = ?;

SELECT c.id, c.name
FROM customers c
WHERE c.id = ?;
```

Cả hai đều có thể thỏa yêu cầu **eager association** nếu khi entity được cung cấp cho ứng dụng, relationship đã được tải theo hợp đồng. Việc SQL có `JOIN` hay không là một vấn đề khác.

## 2. Bảng mặc định chuẩn của bốn loại quan hệ

Đây là bảng cốt lõi, cần phân biệt rõ với gợi ý hiệu năng:

| Loại quan hệ | Java-side cardinality | `fetch()` mặc định trong annotation | Có khai báo lại rõ được không? |
| --- | --- | --- | --- |
| `@ManyToOne` | Một entity đích | `FetchType.EAGER` | Có: `fetch = FetchType.LAZY` |
| `@OneToOne` | Một entity đích | `FetchType.EAGER` | Có: `fetch = FetchType.LAZY` |
| `@OneToMany` | Collection các entity đích | `FetchType.LAZY` | Có: `fetch = FetchType.EAGER` |
| `@ManyToMany` | Collection các entity đích | `FetchType.LAZY` | Có: `fetch = FetchType.EAGER` |

Ví dụ viết rõ giá trị mặc định nhưng **không làm thay đổi hành vi theo annotation**:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;

@OneToOne(fetch = FetchType.EAGER)
private Shipment shipment;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;

@ManyToMany(fetch = FetchType.LAZY)
private Set<Tag> tags;
```

Tương đương về **giá trị `fetch` tĩnh** với:

```java
@ManyToOne
private Customer customer;

@OneToOne
private Shipment shipment;

@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@ManyToMany
private Set<Tag> tags;
```

Không nên nhầm “mặc định của JPA” với “mặc định của một dự án dùng Hibernate”. Provider có thể có tối ưu riêng, nhưng các giá trị mặc định của **annotation** vẫn được xác định bởi đặc tả.

### 2.1. Vì sao thường dễ nhớ nhầm?

Nhiều hướng dẫn thực hành khuyến nghị **chủ động cấu hình LAZY cho `@ManyToOne` và `@OneToOne`** để tránh tải dữ liệu không cần thiết. Đó là **khuyến nghị thiết kế**, không phải mô tả mặc định chuẩn.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

là một lựa chọn rõ ràng, **khác** với:

```java
@ManyToOne
private Customer customer; // Mặc định EAGER.
```

Nếu bài kiểm tra hỏi “JPA đặc tả mặc định gì?”, đáp án phải lấy từ annotation specification, không lấy từ convention dự án.

## 3. @ManyToOne mặc định EAGER

Quan hệ nhiều-một thường xuất hiện ở phía chứa khóa ngoại:

```java
@Entity
public class PurchaseOrder {

    @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
```

Không khai báo `fetch` nên:

```java
@ManyToOne(fetch = FetchType.EAGER)
```

là giá trị tương đương.

### 3.1. Ý nghĩa của MANY_TO_ONE

Nhiều PurchaseOrder có thể cùng tham chiếu một Customer:

```text
PurchaseOrder#101 ----+
PurchaseOrder#102 ----+--> Customer#10
PurchaseOrder#103 ----+
```

Khi đọc một PurchaseOrder, metadata mặc định yêu cầu association Customer được tải chủ động. Nó **không** nói rằng:

- Customer phải được trả thành một cột nằm trong cùng SQL row.
- Provider chỉ được tạo đúng một SQL SELECT.
- Mọi association khác của Customer cũng phải được tải hết vô hạn.
- Mọi quan hệ trong object graph đều phải eager theo đường truyền tự động.

### 3.2. Vì sao EAGER có thể gây N+1?

Giả sử ứng dụng truy vấn 100 đơn hàng:

```jpql
SELECT o
FROM PurchaseOrder o
ORDER BY o.id
```

Nếu `o.customer` là EAGER, provider phải bảo đảm có Customer liên quan theo fetch plan. Một chiến lược có thể là:

```text
1 SELECT lấy 100 PurchaseOrder
+ nhiều SELECT để lấy các Customer liên quan
= nguy cơ N+1 hoặc N + số Customer riêng biệt
```

Nếu nhiều đơn cùng khách, first-level cache, second-level cache hoặc batching có thể giảm số truy vấn phụ. **Nhưng mặc định EAGER không đồng nghĩa đã loại bỏ N+1.** Nó thậm chí có thể khiến provider phải nạp những Customer mà màn hình không dùng.

### 3.3. Chủ động chọn LAZY khi phù hợp

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Cấu hình này yêu cầu trì hoãn tải Customer. Khi ứng dụng truy cập `order.getCustomer().getName()`, provider có thể thực hiện truy vấn bổ sung nếu Customer chưa được tải.

**Nhưng `LAZY` chỉ là hint**, và hành vi dựa vào proxy/bytecode enhancement có thể khác giữa provider/mapping. Không nên xem “field Java đang là proxy” là một bảo đảm tuyệt đối từ đặc tả.

### 3.4. optional không quyết định fetch

```java
@ManyToOne(optional = false)
```

khác với:

```java
@ManyToOne(fetch = FetchType.LAZY)
```

- `optional = false` mô tả association bắt buộc về mặt ánh xạ.
- `fetch = LAZY` mô tả kế hoạch tải.
- `@JoinColumn(nullable = false)` mô tả cột khóa ngoại ở schema/mapping.

Cả ba phục vụ những mục đích riêng. Một `@ManyToOne(optional = false)` **vẫn mặc định EAGER** nếu không khai báo fetch.

## 4. @OneToOne mặc định EAGER

Quan hệ một-một có thể là profile của user, hóa đơn của một đơn hàng hoặc shipment của đơn.

```java
@Entity
public class PurchaseOrder {

    @OneToOne(mappedBy = "order")
    private Shipment shipment;
}
```

Không khai báo `fetch` tương đương:

```java
@OneToOne(
    mappedBy = "order",
    fetch = FetchType.EAGER
)
private Shipment shipment;
```

### 4.1. Phía giữ khóa ngoại và phía mappedBy

Ví dụ hai chiều:

```java
@Entity
public class Shipment {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", unique = true)
    private PurchaseOrder order;
}
```

`Shipment.order` là owning side của liên kết vì giữ FK `order_id`. `PurchaseOrder.shipment` là inverse side do có `mappedBy = "order"`.

**Owning side của mapping không phải yếu tố quyết định fetch mặc định.** Cả hai association `@OneToOne` đều có mặc định EAGER nếu không chỉ rõ, dù khóa ngoại nằm ở phía nào.

### 4.2. Vì sao LAZY ở OneToOne có thể khó hơn ManyToOne?

Khi khóa ngoại `shipment.order_id` nằm ở bảng Shipment, từ một PurchaseOrder provider có thể **chưa biết có Shipment hay không** nếu chưa truy vấn bảng shipment. Với association tùy chọn/inverse side, một số provider hoặc mapping có thể cần SELECT để xác định null, hoặc dùng bytecode enhancement để trì hoãn tốt hơn.

Vì vậy:

```java
@OneToOne(
    mappedBy = "order",
    fetch = FetchType.LAZY
)
private Shipment shipment;
```

là yêu cầu LAZY hợp lệ về mặt annotation, nhưng **không bảo đảm** mỗi provider sẽ tránh truy vấn tới Shipment khi tải PurchaseOrder. Hãy kiểm tra provider/version và cân nhắc kỹ thuật enhancement khi trường hợp này là điểm nóng về hiệu năng.

### 4.3. @MapsId hoặc shared primary key

Với mô hình `@OneToOne` dùng `@MapsId`, entity phụ thuộc có khóa chính chia sẻ với owner. Việc biết ID liên quan có thể thuận tiện cho một số chiến lược tải, nhưng **giá trị fetch mặc định vẫn EAGER theo `@OneToOne`**.

Không đánh đồng “shared primary key giúp provider có thông tin nhận diện” với “JPA tự đổi fetch thành LAZY”.

## 5. @OneToMany mặc định LAZY

Quan hệ một-nhiều thường biểu diễn tập phần tử:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
```

Giá trị fetch mặc định là:

```java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.LAZY
)
```

Một đơn có thể có 0, 1 hoặc hàng nghìn dòng. Nếu mỗi lần đọc đơn mà tự động nạp tất cả lines, số hàng truyền qua mạng và số object Java có thể tăng mạnh.

### 5.1. Truy cập collection có thể kích hoạt query

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

// Tùy trạng thái tải và chiến lược provider:
List<OrderLine> lines = order.getLines();
int size = lines.size();

for (OrderLine line : lines) {
    System.out.println(line.getQuantity());
}
```

Provider có thể trì hoãn dữ liệu lines cho đến khi ứng dụng sử dụng collection. **Không phải cứ gọi getter là chắc chắn xảy ra SELECT ngay**; một số provider trả một persistent collection wrapper, sau đó mới khởi tạo khi cần. Có thể có tối ưu đặc thù cho phép đếm hoặc truy cập một phần mà không tải toàn bộ.

Điều đúng theo đặc tả là `LAZY` là **hint**. Điều cụ thể “SQL chạy ở dòng nào” phải quan sát trên provider.

### 5.2. Collection rỗng không đồng nghĩa null

Một đơn không có lines có thể có collection rỗng:

```java
order.getLines().isEmpty(); // true nếu không có dòng
```

Không nên kiểm tra:

```java
if (order.getLines() == null) { ... }
```

để xác định “đơn chưa có dòng”. Collection được khởi tạo trong entity bằng `new ArrayList<>()` phục vụ mô hình Java; dữ liệu persistent rỗng là **không có phần tử liên kết**, không phải điều kiện “association single-valued bằng null”.

### 5.3. Cố chuyển EAGER cần thận trọng

```java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.EAGER
)
private List<OrderLine> lines;
```

Mapping này yêu cầu tải lines chủ động cho mọi lần tải PurchaseOrder theo fetch plan tĩnh. Nếu nghiệp vụ thường chỉ hiển thị danh sách đơn gồm ID/trạng thái, EAGER có thể tốn chi phí lớn mà không đem lại lợi ích.

Thay vì bật EAGER toàn cục, thường nên để LAZY và yêu cầu tải trong **truy vấn cần dùng dòng hàng**.

## 6. @ManyToMany mặc định LAZY

Ví dụ đơn hàng liên kết với nhiều tag, và một tag có thể xuất hiện ở nhiều đơn hàng:

```java
@ManyToMany
@JoinTable(
    name = "order_tags",
    joinColumns = @JoinColumn(name = "order_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
```

Giá trị fetch mặc định là `LAZY`.

### 6.1. Vì sao quan hệ nhiều-nhiều thường rất lớn?

Từ Order sang Tag có thể đi qua **join table**, và từ Tag lại có những Order khác:

```text
Order#100 ---- tag: sale ---- Order#101
    |                         |
    +------ tag: autumn ------+
```

Nếu mọi association nhiều-nhiều đều EAGER, graph dữ liệu có thể trở nên lớn hoặc lặp qua nhiều tầng. Mặc định LAZY giúp trì hoãn tải collection khi chưa cần.

### 6.2. Không bật EAGER để chữa lỗi lazy ngoài transaction

Một lỗi phổ biến:

```text
Cannot initialize lazy collection ...
```

Người viết chuyển:

```java
@ManyToMany(fetch = FetchType.EAGER)
```

và thấy màn hình tạm hết lỗi. Nhưng toàn bộ ứng dụng giờ phải trả chi phí tải tags ở những use case không cần. Cách thiết kế tốt hơn thường là **tải có chủ đích trong service transaction**, hoặc trả DTO từ query phù hợp.

### 6.3. Fetch không liên quan cascade

```java
@ManyToMany(fetch = FetchType.LAZY)
```

không có nghĩa liên kết này tự cascade PERSIST/MERGE/REMOVE, và:

```java
@ManyToMany(cascade = CascadeType.PERSIST)
```

không có nghĩa nó trở thành EAGER. Fetch và cascade là hai nhóm cấu hình độc lập.

## 7. Mô hình hoàn chỉnh: Order, Customer, Shipment, Line, Tag

Để quan sát tác động của bốn loại relationship, ta dùng một mô hình nhất quán. Các class bên dưới thuộc package `com.example.orders`, dùng `jakarta.persistence.*` và được đặt trong các file Java riêng nếu triển khai.

### 7.1. Entity Customer

```java
package com.example.orders;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String displayName;

    protected Customer() {}

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
}
```

### 7.2. Entity PurchaseOrder

```java
package com.example.orders;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "ordered_at", nullable = false)
    private LocalDateTime orderedAt;

    // Mặc định JPA: EAGER.
    @ManyToOne(optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    // Mặc định JPA: EAGER.
    @OneToOne(mappedBy = "order")
    private Shipment shipment;

    // Mặc định JPA: LAZY.
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    // Mặc định JPA: LAZY.
    @ManyToMany
    @JoinTable(
        name = "order_tags",
        joinColumns = @JoinColumn(name = "order_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new HashSet<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getStatus() { return status; }
    public LocalDateTime getOrderedAt() { return orderedAt; }
    public Customer getCustomer() { return customer; }
    public Shipment getShipment() { return shipment; }
    public List<OrderLine> getLines() { return lines; }
    public Set<Tag> getTags() { return tags; }
}
```

Các chú thích “mặc định” là **mặc định của annotation tại thời điểm dựng static fetch plan**. Một query có `JOIN FETCH` hoặc một entity graph có thể bổ sung/chỉnh các yêu cầu tải trong lần truy vấn cụ thể.

### 7.3. Entity Shipment

```java
package com.example.orders;

import jakarta.persistence.*;

@Entity
@Table(name = "shipments")
public class Shipment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String trackingCode;

    @OneToOne(optional = false)
    @JoinColumn(
        name = "order_id",
        nullable = false,
        unique = true
    )
    private PurchaseOrder order;

    protected Shipment() {}

    public Long getId() { return id; }
    public String getTrackingCode() { return trackingCode; }
    public PurchaseOrder getOrder() { return order; }
}
```

`Shipment.order` cũng là `@OneToOne` nên **mặc định EAGER**. Hai chiều cùng EAGER có thể khiến graph/phép tải phức tạp; provider quản lý entity identity để tránh tạo vô hạn Java objects, nhưng số SELECT và đường đi nạp dữ liệu vẫn cần được đo.

### 7.4. Entity OrderLine

```java
package com.example.orders;

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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
}
```

Ở đây cố ý khai báo **`fetch = LAZY`** trên hai association `@ManyToOne`. Điều này cho thấy một dự án có thể **ghi đè mặc định EAGER** theo quyết định hiệu năng, còn giá trị theo đặc tả vẫn không đổi.

### 7.5. Entity Product và Tag

```java
package com.example.orders;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private String name;

    protected Product() {}

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
```

```java
package com.example.orders;

import jakarta.persistence.*;

@Entity
@Table(name = "tags")
public class Tag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String code;

    protected Tag() {}

    public Long getId() { return id; }
    public String getCode() { return code; }
}
```

### 7.6. Schema quan hệ minh họa

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE tags (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    ordered_at TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE shipments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE,
    tracking_code VARCHAR(100) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE order_tags (
    order_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (order_id, tag_id),
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);
```

Ví dụ dùng tên bảng/cột SQL. JPQL dùng **tên entity và property Java**, không phải những tên bảng/cột này.

## 8. Điều gì xảy ra khi gọi EntityManager.find()?

Giả sử `PurchaseOrder#100` tồn tại, có một Customer, một Shipment, ba OrderLine và hai Tag.

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 100L);
```

Theo **static fetch metadata** của entity ví dụ:

| Association | Default fetch | Kỳ vọng ở mức fetch plan |
| --- | --- | --- |
| `order.customer` | EAGER | Customer phải được tải chủ động theo plan. |
| `order.shipment` | EAGER | Shipment phải được tải chủ động theo plan. |
| `order.lines` | LAZY | Lines có thể được trì hoãn đến khi được truy cập. |
| `order.tags` | LAZY | Tags có thể được trì hoãn đến khi được truy cập. |

Có thể hình dung:

```text
find(PurchaseOrder#100)
    |
    +-- order base fields
    |
    +-- customer    [EAGER theo annotation]
    |
    +-- shipment    [EAGER theo annotation]
    |
    +-- lines       [LAZY hint]
    |
    +-- tags        [LAZY hint]
```

Đây là mô tả **mức độ tải theo metadata**, không phải sơ đồ SQL. Provider có thể xử lý Customer và Shipment bằng JOIN, SELECT riêng hoặc chiến lược khác.

### 8.1. Tại sao không dự đoán chính xác số query?

Giả sử `Customer#10` đã managed trong EntityManager trước khi gọi `find`:

```java
Customer customer = em.find(Customer.class, 10L);
PurchaseOrder order = em.find(PurchaseOrder.class, 100L);
```

Provider có thể tái sử dụng Customer đã tồn tại trong persistence context. Nếu Customer chưa managed, provider có thể cần tải. Second-level cache, entity graph, truy vấn trước đó và batch configuration cũng ảnh hưởng.

**Một mapping EAGER không đồng nghĩa “luôn thêm một SELECT”**, và một mapping LAZY không đồng nghĩa “luôn phát SELECT mới khi truy cập”. Dữ liệu có thể đã có trong cache/context.

### 8.2. LAZY không cam kết getter an toàn ngoài transaction

Nếu entity đã detached và collection còn chưa được khởi tạo, việc truy cập dữ liệu cần lazy load có thể thất bại vì không còn persistence context khả dụng.

Ví dụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 100L);

em.close();

// Nếu lines chưa được nạp, truy cập có thể thất bại.
int count = order.getLines().size();
```

Trong Hibernate, thường gặp ngoại lệ provider-specific như `LazyInitializationException`. Đặc tả JPA không yêu cầu mọi provider dùng đúng tên exception ấy.

Giải pháp không phải mặc định chuyển tất cả associations sang EAGER, mà là **xác định dữ liệu cần dùng trước khi kết thúc đơn vị công việc**.

## 9. Truy vấn JPQL SELECT và mặc định EAGER

Một giả định sai phổ biến là:

> “Tôi chỉ viết `SELECT o FROM PurchaseOrder o` nên chắc chỉ có dữ liệu bảng orders được tải.”

Nếu `o.customer` và `o.shipment` mặc định EAGER, provider có nghĩa vụ xử lý các association đó theo fetch plan có hiệu lực ngay cả khi JPQL không viết `JOIN FETCH`.

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
```

Kết quả là entity `PurchaseOrder` và những association được yêu cầu bởi fetch plan. Nhà phát triển không nên coi “JPQL không nhắc đến Customer” là bằng chứng Customer không bị tải.

### 9.1. N+1 từ association EAGER

Một implementation có thể tạo:

```sql
SELECT o.id, o.customer_id, o.status, o.ordered_at
FROM purchase_orders o
WHERE o.status = ?;

-- Các câu truy vấn tiếp theo, nếu cần:
SELECT c.* FROM customers c WHERE c.id = ?;
SELECT s.* FROM shipments s WHERE s.order_id = ?;
```

Lặp lại các SELECT bổ sung cho nhiều orders có thể dẫn tới hiệu năng kém. Query kế hoạch cụ thể khác nhau theo provider, nhưng **nguy cơ** là có thật.

### 9.2. Không dùng EAGER toàn cục để chắc chắn không N+1

Một entity có nhiều quan hệ EAGER có thể:

- Phát nhiều secondary SELECT.
- Tạo JOIN trên những bảng không cần.
- Làm tăng số hàng/kích thước dữ liệu truyền.
- Khởi tạo graph lớn, tốn memory.
- Gây khó kiểm soát latency khi thay đổi mapping.

Nếu một màn hình cần danh sách đơn và tên khách, hãy thiết kế truy vấn **theo màn hình đó** thay vì đổi mọi association sang EAGER.

## 10. Vì sao JOIN thường khác JOIN FETCH?

Một query có thể JOIN Customer để **lọc**:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.displayName LIKE :namePattern
```

`JOIN` thông thường tham gia vào **điều kiện, projection và tập kết quả**. Nó không tự mang nghĩa “hãy khởi tạo association cho những entity trả về”.

Với `@ManyToOne` mặc định EAGER, Customer sẽ vẫn cần được xử lý theo fetch plan, nhưng là do yêu cầu fetch, không chỉ vì query có `JOIN`.

Ngược lại:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.status = :status
```

`JOIN FETCH` yêu cầu nạp Customer như một phần của truy vấn.

### 10.1. Bảng phân biệt

| Cấu trúc | Vai trò |
| --- | --- |
| `JOIN o.customer c` | Ghép Customer để truy vấn được lọc/chọn theo `c`. |
| `LEFT JOIN o.lines l` | Ghép từng dòng hàng, giữ order khi không có dòng. |
| `JOIN FETCH o.customer` | Yêu cầu fetch Customer qua fetch join. |
| `LEFT JOIN FETCH o.lines` | Yêu cầu fetch collection lines và giữ order không có lines. |
| `WHERE o.customer.id = :id` | Lọc theo association; không tự quyết định fetch plan SQL. |

**JOIN FETCH** là công cụ thiết kế fetch plan cho **một truy vấn**. Nó thường hữu ích hơn việc thay annotation thành EAGER trên toàn entity vì chỉ những nơi cần dữ liệu mới chịu chi phí tải.

### 10.2. FETCH JOIN không bảo đảm đúng một câu SQL trong mọi trường hợp phức tạp

Thông thường fetch join được provider biểu diễn bằng SQL JOIN. Tuy nhiên, những fetch plan lớn, inheritance, association khác, caching và giới hạn provider vẫn có thể kéo theo SQL bổ sung. Không lấy `JOIN FETCH` làm cam kết rằng mọi property liên quan trong toàn bộ graph đều được giải quyết bằng một round-trip duy nhất.

## 11. Tải collection theo nhu cầu bằng LEFT JOIN FETCH

Giả sử trang chi tiết đơn cần tất cả OrderLine:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

Lý do chọn `LEFT JOIN`: đơn hàng không có lines vẫn phải được trả về.

Java:

```java
List<PurchaseOrder> rows = em.createQuery(
        "SELECT DISTINCT o " +
        "FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "WHERE o.id = :id",
        PurchaseOrder.class
    )
    .setParameter("id", 100L)
    .getResultList();

PurchaseOrder order =
    rows.isEmpty() ? null : rows.get(0);
```

Theo truy vấn, `lines` được fetch trong lần đọc này, dù static mapping `@OneToMany` là LAZY.

### 11.1. Vì sao cần cân nhắc DISTINCT?

Một order có ba lines có thể tạo ba SQL rows trong join:

```text
order_id | line_id
---------+--------
100      | 1001
100      | 1002
100      | 1003
```

Persistence context chỉ có một managed identity cho Order#100, nhưng việc có bao nhiêu occurrences trong result list phụ thuộc semantics/version/provider và `DISTINCT`.

`SELECT DISTINCT o` biểu đạt ý định trả mỗi entity root một lần. Một số phiên bản Hibernate loại trùng các entity từ collection fetch join tự động khi materialize, nhưng không nên đem hành vi của một provider áp làm quy tắc SQL chung.

### 11.2. LAZY mapping vẫn có thể được fetch chủ động trong query

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

và:

```jpql
LEFT JOIN FETCH o.lines
```

không mâu thuẫn nhau:

- Annotation nói **mặc định tĩnh** nên trì hoãn.
- Query nói **riêng lần truy vấn này** cần tải lines.

Đây là nguyên lý quan trọng của kế hoạch tải theo use case.

## 12. Khi JOIN FETCH làm dữ liệu bùng nổ

Nếu một order có:

- 20 OrderLine.
- 15 Tag.

và query fetch cùng lúc cả hai collection:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.tags
WHERE o.id = :id
```

SQL có thể tạo số hàng trung gian xấp xỉ:

```text
20 lines × 15 tags = 300 joined rows
```

cho chỉ một order.

Nếu có 100 orders tương tự, chi phí truyền dữ liệu và xử lý duplicate có thể rất lớn. Ngoài ra, provider có thể hạn chế một số hình dạng join fetch nhiều collection. Chẳng hạn một số cấu hình Hibernate khi fetch đồng thời nhiều bag có thể phát sinh lỗi `MultipleBagFetchException` — đây là **hạn chế provider-specific**, không phải tên lỗi chuẩn JPA.

### 12.1. Chiến lược thay thế

Có thể:

1. Fetch một collection cần thiết nhất.
2. Load collection còn lại bằng query riêng theo các root IDs.
3. Dùng DTO projection khi UI không cần managed entity graph.
4. Cân nhắc batch fetching/subselect fetching theo provider.
5. Thiết kế endpoint tách thông tin tổng quan và chi tiết.

Không nên giải quyết N+1 bằng cách thêm `JOIN FETCH` cho mọi association mà không xét **tích số hàng**.

## 13. Phân trang và collection fetch join

Giả sử cần trang 20 orders:

```java
List<PurchaseOrder> page = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "ORDER BY o.orderedAt DESC, o.id DESC",
        PurchaseOrder.class
    )
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Khi fetch collection bằng JOIN:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.orderedAt DESC, o.id DESC
```

mỗi order có thể chiếm nhiều SQL rows. Nếu đặt LIMIT/OFFSET vào hàng SQL join, ta không chắc nhận đủ **20 root orders và toàn bộ lines**. Provider có thể phải phân trang trong memory, cảnh báo, hoặc áp hạn chế khác.

### 13.1. Phân trang root trước, fetch sau

Mẫu hai bước:

**Bước 1: Lấy ID của trang orders**

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.orderedAt DESC, o.id DESC
```

Áp `setFirstResult/setMaxResults` lên query ID.

**Bước 2: Fetch lines cho các orders trong trang**

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Lưu ý:

- Nếu `ids` rỗng, trả kết quả rỗng thay vì giả định `IN ()` portable.
- Query bước 2 không mặc nhiên giữ đúng thứ tự ID của bước 1; sắp xếp lại khi cần.
- Dưới cạnh tranh, hai bước có thể thấy những snapshot khác nhau nếu không có transaction/isolation phù hợp.
- Với danh sách IDs lớn, cần xét giới hạn bind parameters/database.

Cách này thường ổn định hơn việc fetch collection trước rồi phân trang root.

## 14. Entity graph: thay đổi fetch plan theo use case

JPA hỗ trợ **entity graphs** để diễn đạt những association cần tải khi thực thi một truy vấn hoặc `find`.

Giả sử ứng dụng muốn đọc PurchaseOrder cùng Customer và Lines, nhưng không muốn mặc định toàn ứng dụng luôn fetch lines.

Một entity graph:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer", "lines");
```

Áp cho `find`:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.loadgraph",
    graph
);

PurchaseOrder order =
    em.find(PurchaseOrder.class, 100L, hints);
```

Đoạn code cần import `jakarta.persistence.EntityGraph`, `java.util.Map`; giả định Jakarta Persistence sử dụng hint namespace `jakarta.persistence.*`.

### 14.1. loadgraph và fetchgraph khác nhau

Hai hint chuẩn thường gặp:

- **`jakarta.persistence.loadgraph`**: những attributes có trong graph được yêu cầu tải; những attributes không có trong graph tiếp tục tuân theo static fetch metadata.
- **`jakarta.persistence.fetchgraph`**: những attributes có trong graph được yêu cầu tải; những attributes không có được xử lý theo mặc định LAZY của fetch graph.

Đặt trong bối cảnh Order có:

```text
customer  = EAGER tĩnh
shipment  = EAGER tĩnh
lines     = LAZY tĩnh
tags      = LAZY tĩnh
```

Giả sử graph chỉ liệt kê `lines`.

| Association | `loadgraph(lines)` | `fetchgraph(lines)` theo ngữ nghĩa đặc tả |
| --- | --- | --- |
| `lines` | EAGER theo graph | EAGER theo graph |
| `customer` | Theo static EAGER | Xử lý như LAZY nếu không chỉ định |
| `shipment` | Theo static EAGER | Xử lý như LAZY nếu không chỉ định |
| `tags` | Theo static LAZY | Xử lý như LAZY nếu không chỉ định |

**Cần phân biệt yêu cầu fetch graph và kết quả thực thi tối thiểu.** Đặc tả cho phép provider lấy thêm state ngoài những gì graph yêu cầu, nên `fetchgraph` không phải bảo đảm tuyệt đối rằng những association bị bỏ qua sẽ chưa được tải. Bên cạnh đó, khả năng thực tế của một provider có thể có giới hạn, đặc biệt với những mapping `EAGER` tĩnh hoặc LAZY trên inverse `@OneToOne`; phải kiểm chứng với phiên bản đang dùng.

### 14.2. Khi nào dùng graph thay JOIN FETCH?

Entity graph hữu ích khi:

- Muốn giữ JPQL chủ yếu mô tả **điều kiện và projection**, còn fetch plan là một cấu hình riêng.
- Cần tái sử dụng một fetch plan cho nhiều query.
- Muốn mô tả nhiều cấp association bằng subgraphs.
- Dùng `EntityManager.find(..., properties)` hoặc repository có hỗ trợ entity graph.

JOIN FETCH hữu ích khi muốn thể hiện fetch ngay trong truy vấn cụ thể và dễ nhìn thấy association đang được yêu cầu.

Hai công cụ không nhất thiết có cùng SQL/performance trên mọi provider.

### 14.3. Subgraph nhiều cấp

Giả sử cần tải Order, Lines và Product của mỗi Line:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<OrderLine> lineGraph =
    graph.addSubgraph("lines");

lineGraph.addAttributeNodes("product");
```

Áp graph cho query phù hợp để yêu cầu:

```text
PurchaseOrder
    |
    +-- lines
          |
          +-- product
```

Đây là yêu cầu tải theo graph, **không phải tuyên bố mỗi provider sẽ tạo đúng một SQL JOIN gồm ba bảng**. Kế hoạch SQL cần được đo.

## 15. @NamedEntityGraph và việc tái sử dụng cấu hình

Có thể khai báo graph trên entity:

```java
@NamedEntityGraph(
    name = "PurchaseOrder.withLines",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode("lines")
    }
)
@Entity
public class PurchaseOrder {
    // Các field mapping như ví dụ trước.
}
```

Đoạn trên minh họa phần annotation; trong code thật phải đặt `@NamedEntityGraph` trên cùng class entity PurchaseOrder và không định nghĩa hai class trùng tên.

Lấy graph:

```java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.withLines");
```

Gắn hint vào query:

```java
TypedQuery<PurchaseOrder> query = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.id = :id",
    PurchaseOrder.class
);

query.setHint("jakarta.persistence.loadgraph", graph);
query.setParameter("id", 100L);

PurchaseOrder order =
    query.getResultStream().findFirst().orElse(null);
```

Ưu điểm là tên graph có thể biểu đạt use case cụ thể. Nhưng graph quá rộng vẫn có thể tạo nhiều dữ liệu/SQL không cần thiết.

## 16. Fetch plan bằng Criteria API

Criteria API cung cấp `fetch` để khai báo fetch join trên một path.

Ví dụ:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> o =
    cq.from(PurchaseOrder.class);

o.fetch("customer", JoinType.INNER);
o.fetch("lines", JoinType.LEFT);

cq.select(o)
  .distinct(true)
  .where(cb.equal(o.get("id"), 100L));

List<PurchaseOrder> orders =
    em.createQuery(cq).getResultList();
```

Đoạn code cần các import từ `jakarta.persistence.criteria.*`.

Ở đây:

- `fetch("customer", JoinType.INNER)` yêu cầu fetch Customer.
- `fetch("lines", JoinType.LEFT)` yêu cầu fetch Lines, giữ Order không có Lines.
- `distinct(true)` diễn đạt mong muốn không trùng root entity.

### 16.1. join() khác fetch()

Trong Criteria API:

```java
Join<PurchaseOrder, Customer> c =
    o.join("customer", JoinType.INNER);
```

được dùng để **lọc/chọn** theo Customer.

Còn:

```java
o.fetch("customer", JoinType.INNER);
```

được dùng để **yêu cầu tải association**.

Không mặc định rằng `join()` thường đồng nghĩa `fetch()`. Nếu query chỉ cần lọc theo tên khách, `join()` là đúng mục đích. Nếu cần tiếp tục sử dụng Customer sau khi tải orders, hãy chọn fetch plan phù hợp.

## 17. DTO projection: tránh tải entity graph khi chỉ cần vài trường

Một màn hình liệt kê đơn hàng có thể chỉ cần:

- ID đơn.
- Tên khách.
- Trạng thái đơn.
- Thời gian tạo.

Không cần tải tất cả OrderLine, Tag hoặc Shipment.

### 17.1. Dùng constructor expression

Giả sử DTO:

```java
package com.example.orders.dto;

import java.time.LocalDateTime;

public record OrderListItem(
    Long id,
    String customerName,
    String status,
    LocalDateTime orderedAt
) {}
```

JPQL:

```jpql
SELECT new com.example.orders.dto.OrderListItem(
    o.id,
    c.displayName,
    o.status,
    o.orderedAt
)
FROM PurchaseOrder o
JOIN o.customer c
ORDER BY o.orderedAt DESC, o.id DESC
```

Truy vấn trả **DTO scalar projection**, không yêu cầu provider trả một managed PurchaseOrder đầy đủ chỉ để hiển thị những field đó.

### 17.2. Khi nào DTO phù hợp hơn fetch join?

- Danh sách dài, mỗi hàng chỉ cần vài cột.
- API read-only, không cần sửa entity.
- Muốn tránh lazy loading trong quá trình serialize response.
- Không cần persistence context theo dõi những đối tượng trả về.
- Muốn kiểm soát chính xác dữ liệu trả cho client.

Nếu use case cần sửa OrderLine hoặc thao tác domain trên aggregate, managed entities với fetch plan phù hợp có thể hợp lý hơn. Không có một cách đúng cho mọi thao tác.

## 18. N+1: vấn đề quan trọng hơn chỉ nhớ EAGER/LAZY

Một ví dụ N+1 với LAZY:

```java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();

for (PurchaseOrder o : orders) {
    System.out.println(o.getLines().size());
}
```

Nếu lines chưa được nạp và provider tải collection cho mỗi Order riêng, ta có thể gặp:

```text
1 SELECT lấy danh sách Order
N SELECT để tải lines cho từng Order
```

Nhưng N+1 **cũng có thể xảy ra với EAGER** khi provider dùng secondary SELECT để thỏa quan hệ đơn trị mặc định.

Vì thế câu “chỉ cần đổi tất cả sang LAZY là không còn N+1” là sai. LAZY có thể tránh tải thứ không dùng, nhưng nếu code lặp và truy cập nó ở N entities, vẫn có thể tạo N query phụ.

### 18.1. Các cách giảm N+1

1. **DTO projection:** nếu chỉ cần một số field, không tải graph.
2. **JOIN FETCH:** yêu cầu nạp association trong truy vấn thích hợp.
3. **Entity graph:** mô tả fetch plan theo use case.
4. **Batch fetching:** provider có thể gom nhiều association loading thành ít truy vấn hơn.
5. **Subselect fetching:** một số provider hỗ trợ tối ưu collection loading sau truy vấn gốc.
6. **Truy vấn hai bước:** fetch IDs theo trang rồi nạp associations cần dùng.

Những cơ chế như `@BatchSize` (Hibernate) hoặc `@Fetch(FetchMode.SUBSELECT)` là **provider-specific**, không phải `fetch()` mặc định của JPA. Khi dùng, phải ghi rõ phụ thuộc vào provider.

### 18.2. Không tối ưu bằng cảm giác

Giả sử một endpoint trước đây chạy 31 SQL queries và sau khi thêm một fetch graph chỉ còn 2. Điều đó là kết quả có thể đo được trong môi trường đó.

Nhưng không suy ra rằng cùng annotation sẽ tạo đúng 2 SQL trên mọi database/provider. Cần theo dõi số query, thời gian thực thi, rows, heap allocation và latency thực tế.

## 19. LAZY bên ngoài persistence context và transaction boundary

Đây là vấn đề ứng dụng thường gặp.

Ví dụ:

```java
public PurchaseOrder loadOrder(Long id) {
    EntityManager em = factory.createEntityManager();
    try {
        return em.find(PurchaseOrder.class, id);
    } finally {
        em.close();
    }
}
```

Sau đó:

```java
PurchaseOrder order = service.loadOrder(100L);
int count = order.getLines().size();
```

Vì `lines` là LAZY và EntityManager đã đóng, ứng dụng có thể không còn cách khởi tạo collection. Với Hibernate thường là `LazyInitializationException`.

### 19.1. Giải pháp ở service

Nếu API cần lines:

```java
@Transactional(readOnly = true)
public OrderDetails getDetails(Long id) {
    // Tải Order + lines theo fetch plan rõ ràng.
    // Map sang DTO trong transaction.
    // Trả DTO đã chứa những field cần thiết.
}
```

Đoạn trên là phác thảo design; `OrderDetails` và logic map cần được định nghĩa trong ứng dụng. Ý chính: **xác định và tải dữ liệu cần dùng trước khi rời transaction/persistence context**, rồi trả DTO ổn định.

### 19.2. @Transactional không tự đổi LAZY thành EAGER

Một method có `@Transactional` giúp giữ bối cảnh giao dịch/persistence context theo cấu hình, nhưng không biến mọi association thành EAGER và không tự ngăn N+1.

Nếu vòng lặp trong transaction gọi `getLines()` cho 100 orders, N+1 vẫn có thể xảy ra. Transaction giải quyết **vòng đời truy cập**, còn fetch plan giải quyết **chi phí tải**.

### 19.3. Open Session in View không phải giải pháp fetch plan

Một số ứng dụng Spring/Hibernate bật mô hình Open Session in View để giữ persistence context mở đến giai đoạn render/serialize HTTP response. Khi đó lazy loading có thể xảy ra ở tầng view.

Tuy nhiên, việc để serialization tự kích hoạt SQL thường khiến:

- Query count khó dự đoán.
- N+1 lộ ở nơi không thể hiện rõ trong service.
- Khó kiểm soát dữ liệu quan hệ vô tình được serialize.
- Khó đo boundary transaction/lỗi runtime.

Không nên chỉ dựa vào Open Session in View thay vì thiết kế DTO/fetch plan theo use case.

## 20. Các loại fetch bên ngoài bốn association

Để không nhầm khái niệm “mọi thuộc tính JPA đều mặc định LAZY”, cần phân biệt thêm những mapping khác.

| Annotation | Mặc định fetch | Ghi chú |
| --- | --- | --- |
| `@Basic` | **EAGER** | Cho thuộc tính cơ bản, ví dụ String, số; LAZY có thể được khai báo nhưng cũng là hint. |
| `@ElementCollection` | **LAZY** | Cho collection giá trị cơ bản hoặc embeddable, không phải entity association trực tiếp. |
| `@ManyToOne` | **EAGER** | Quan hệ đơn trị tới entity. |
| `@OneToOne` | **EAGER** | Quan hệ đơn trị tới entity. |
| `@OneToMany` | **LAZY** | Collection entity. |
| `@ManyToMany` | **LAZY** | Collection entity qua join table hoặc mapping tương ứng. |

### 20.1. @Basic(fetch = LAZY)

```java
@Basic(fetch = FetchType.LAZY)
@Lob
private byte[] documentData;
```

Ở đây LAZY có thể cần cơ chế enhancement để thực sự trì hoãn tải một basic field. Annotation **không bảo đảm** provider tự phân tách dữ liệu LOB thành một SELECT sau.

Ngược lại, không khai báo `@Basic(fetch = ...)` thì field basic có mặc định EAGER.

### 20.2. @ElementCollection

```java
@ElementCollection
@CollectionTable(
    name = "order_notes",
    joinColumns = @JoinColumn(name = "order_id")
)
@Column(name = "note")
private List<String> notes;
```

`@ElementCollection` mặc định LAZY, gần với các association đa trị về nhu cầu trì hoãn collection; tuy nhiên phần tử của nó là **giá trị**, không phải entity có identity độc lập.

Không nhầm `@ElementCollection(fetch=LAZY)` với `@OneToMany(fetch=LAZY)` về semantics vòng đời phần tử.

### 20.3. @Embedded

`@Embedded` biểu diễn một embeddable value object, không có thuộc tính `fetch` riêng như bốn association ở trên. Các field bên trong embeddable có thể chứa basic state hoặc relationship mappings với quy tắc tải của chính chúng.

Không nói “`@Embedded` mặc định EAGER/LAZY như `@ManyToOne`” một cách máy móc; phải xét mapping từng thuộc tính.

## 21. Giá trị mặc định có phụ thuộc optional, cascade, mappedBy không?

Không. Những thuộc tính này độc lập với `fetch`.

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

**Vẫn mặc định LAZY.**

Tương tự:

```java
@ManyToOne(
    optional = false,
    cascade = CascadeType.PERSIST
)
private Customer customer;
```

**Vẫn mặc định EAGER.**

Bảng phân biệt:

| Annotation attribute | Điều nó điều khiển | Có thay đổi giá trị fetch mặc định không? |
| --- | --- | --- |
| `fetch` | Kế hoạch tải | Đây chính là thuộc tính điều khiển fetch. |
| `cascade` | Lan truyền PERSIST/MERGE/REMOVE/... | Không. |
| `orphanRemoval` | Xử lý child bị rời quan hệ phụ thuộc | Không. |
| `optional` | Association đơn trị có được null hay không | Không. |
| `mappedBy` | Phía inverse của association hai chiều | Không. |
| `@JoinColumn` | Cách ánh xạ FK và ràng buộc cột | Không. |
| `@OrderBy` | Thứ tự kết quả của collection | Không. |
| `@OrderColumn` | Cột lưu vị trí của List | Không. |

Một annotation có thể cấu hình nhiều thuộc tính, nhưng không có nghĩa giá trị của một thuộc tính ngầm thay đổi giá trị mặc định của thuộc tính khác.

## 22. FetchType.LAZY không giống lazy loading ở Java thông thường

Một field Java:

```java
private List<OrderLine> lines = new ArrayList<>();
```

được khởi tạo bằng `new ArrayList<>()`, nhưng khi entity được JPA load, provider có thể thay thế/quản lý nó bằng persistent collection wrapper/proxy phù hợp.

Điều quan trọng:

- **Thực thể Java** có thể chứa wrapper chưa được khởi tạo.
- **Database** có thể chứa nhiều rows của association.
- **Persistence context** theo dõi entity và những collection đang managed.
- **Provider** quyết định thời điểm truy vấn bổ sung, có thể dựa trên cache hoặc enhancement.

Không sử dụng tên lớp triển khai của một proxy như hợp đồng portable. Ví dụ `PersistentBag` hoặc `HibernateProxy` là chi tiết Hibernate, không phải kiểu bắt buộc của JPA.

### 22.1. getReference() không phải một chiến lược fetch mặc định mới

`EntityManager.getReference(EntityClass.class, id)` có thể tạo reference đến entity mà chưa tải toàn bộ state ngay lập tức theo cơ chế provider.

Nhưng nó **không thay đổi giá trị mặc định của `@ManyToOne` hay `@OneToMany` trong annotation**. Đó là một API lấy entity reference, khác với việc thiết kế fetch plan cho toàn bộ truy vấn.

### 22.2. Proxy không có nghĩa relation được tải

Một đối tượng proxy có thể biểu diễn entity đích nhưng chưa nạp field của entity đó. Ngược lại, một provider có thể dùng bytecode enhancement thay vì proxy class riêng.

Khi quan sát bằng debugger, gọi `toString()`, `equals()` hoặc một getter có thể vô tình kích hoạt lazy initialization. Không dùng “debugger hiện object thế nào” làm thước đo duy nhất cho fetch semantics.

## 23. Dùng PersistenceUnitUtil để quan sát trạng thái tải

JPA cung cấp API chuẩn:

```java
PersistenceUnitUtil util =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil();
```

Ví dụ:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 100L);

boolean loadedEntity = util.isLoaded(order);
boolean linesLoaded = util.isLoaded(order, "lines");
boolean tagsLoaded = util.isLoaded(order, "tags");
boolean customerLoaded = util.isLoaded(order, "customer");
```

Cần import `jakarta.persistence.PersistenceUnitUtil`.

`isLoaded(entity, "propertyName")` giúp kiểm tra một thuộc tính đã được xem là loaded theo API JPA.

### 23.1. Một phép kiểm tra không phải bảo đảm cấu hình lâu dài

Ví dụ, `linesLoaded` có thể là true dù `@OneToMany` mặc định LAZY nếu:

- Entity đã được tải trước đó với JOIN FETCH/entity graph.
- Provider đã chủ động khởi tạo collection.
- Một đoạn code trước đã truy cập collection.
- Data/cache/provider có chiến lược tải đặc thù.

Do đó **LAZY mặc định không tương đương isLoaded luôn false**.

### 23.2. Kiểm thử đúng mục tiêu

Nếu muốn xác nhận fetch plan trong môi trường cụ thể, có thể tạo EntityManager mới, tải dữ liệu trong một transaction đọc, kiểm tra `PersistenceUnitUtil` và quan sát SQL.

Nhưng tránh kết luận:

```java
assertFalse(util.isLoaded(order, "lines"));
```

là một yêu cầu portable tuyệt đối từ đặc tả cho association LAZY. Do LAZY là hint, provider có thể tải sớm.

Khi triển khai ứng dụng, test thường nên tập trung vào **hành vi nghiệp vụ và giới hạn SQL/performance đã đo được theo provider** thay vì áp một chi tiết nội bộ của proxy thành quy tắc chuẩn JPA.

## 24. Fetch plan với truy vấn native SQL

Nếu dùng:

```java
List<PurchaseOrder> orders = em.createNativeQuery(
    "SELECT * FROM purchase_orders WHERE status = ?",
    PurchaseOrder.class
).setParameter(1, "PAID").getResultList();
```

native SQL nói trực tiếp tới bảng/cột, nhưng entity kết quả vẫn có JPA mappings và có thể chịu yêu cầu fetch associations theo provider/fetch plan.

Không suy từ câu SQL root rằng provider **chắc chắn sẽ không tải Customer/Shipment bổ sung**. Cách hiện thực EAGER qua native query có thể khác với `find()` hoặc JPQL.

Đồng thời một SQL JOIN thủ công chưa chắc provider hiểu rằng một association đã được fetch đầy đủ, trừ khi result mapping/query contract được xây đúng. Nếu cần projection cụ thể, có thể map scalar/DTO thay vì cố khởi tạo entity graph từ SQL thiếu các cột cần thiết.

### 24.1. Native query không hủy quy tắc lazy outside context

Một managed entity được tạo từ native query vẫn có thể chứa LAZY associations. Sau khi EntityManager đóng, truy cập association chưa khởi tạo có thể thất bại tương tự các truy vấn entity khác.

## 25. Spring Data JPA: mặc định và @EntityGraph

Spring Data JPA làm việc trên JPA provider. Nó **không thay đổi giá trị fetch mặc định của bốn relationship annotations** chỉ vì dùng `JpaRepository`.

Giả sử repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Nếu `PurchaseOrder.customer` không khai báo `fetch`, nó vẫn có default EAGER; `PurchaseOrder.lines` vẫn default LAZY.

### 25.1. Dùng @EntityGraph theo method

Ví dụ trang chi tiết:

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer", "lines"})
    Optional<PurchaseOrder> findDetailedById(Long id);
}
```

Đoạn này minh họa Spring Data repository method và yêu cầu graph theo tên attributes. Tên method `findDetailedById` phải được provider Spring Data phân tích đúng theo entity model/query lookup của phiên bản dự án; nếu muốn chắc chắn hơn, có thể khai báo `@Query("SELECT o FROM PurchaseOrder o WHERE o.id = :id")` và bind `@Param` tương ứng.

Một ví dụ có JPQL rõ:

```java
@EntityGraph(attributePaths = {"customer", "lines"})
@Query("SELECT o FROM PurchaseOrder o WHERE o.id = :id")
Optional<PurchaseOrder> findDetails(@Param("id") Long id);
```

Các import bổ sung:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
```

### 25.2. FetchGraph và LoadGraph trong Spring Data

Spring Data JPA `@EntityGraph` cho phép chọn graph type tương ứng với JPA fetch/load graph. Khi dự án cần xử lý khác nhau giữa “chỉ những attributes có trong graph” và “graph cộng static EAGER”, phải đọc đúng cấu hình `EntityGraphType.FETCH` hoặc `LOAD` mà method sử dụng.

Không nên nói `@EntityGraph` luôn tải **đúng và chỉ đúng** những field liệt kê. Provider có thể tải thêm state và các eager associations khác tùy graph semantics/provider.

### 25.3. @Transactional(readOnly = true) không phải fetch plan

`@Transactional(readOnly = true)` thường diễn đạt transaction đọc và có thể có các tối ưu theo framework/provider, nhưng không làm:

```java
@OneToMany
private List<OrderLine> lines;
```

tự đổi từ LAZY sang EAGER. Việc tải lines vẫn theo query graph và cách truy cập trong persistence context.

## 26. Fetch graph không tự thay thế quyền truy cập và bảo mật

Một query có fetch graph rộng có thể kéo thêm dữ liệu nhạy cảm:

```text
User -> Roles -> Permissions
Order -> Customer -> Addresses
Invoice -> PaymentDetails
```

Nếu DTO/serialization tự đưa mọi field đã fetch ra JSON, ứng dụng có nguy cơ trả dữ liệu ngoài nhu cầu.

Fetch plan là công cụ tối ưu/tổ chức truy xuất **không phải** cơ chế phân quyền.

Cần bảo đảm:

- Caller được phép xem entity root và dữ liệu liên quan.
- Query có filter tenant/ownership khi cần.
- DTO chỉ chứa những trường API được phép trả.
- Tránh serialize trực tiếp managed graph có quan hệ hai chiều, dễ tạo vòng lặp hoặc dữ liệu quá lớn.
- Không cho client tự chọn một chuỗi graph/path tùy ý không whitelist.

## 27. Cách chọn fetch policy khi thiết kế hệ thống

Giá trị mặc định do đặc tả cung cấp một điểm khởi đầu, **không bắt buộc là tối ưu cho mọi domain**.

Một cách tổ chức thường hiệu quả:

1. Nhận diện những association nào được sử dụng thường xuyên và association nào có thể lớn.
2. Chủ động ghi rõ fetch trên những quan hệ quan trọng để code dễ đọc.
3. Với `@ManyToOne`/`@OneToOne`, cân nhắc LAZY khi không phải use case nào cũng cần entity đích và provider hỗ trợ tốt.
4. Với `@OneToMany`/`@ManyToMany`, thường giữ LAZY để tránh tải nhiều collection ngoài ý muốn.
5. Dùng query-specific fetch: JOIN FETCH/entity graph khi service thực sự cần associations.
6. Dùng DTO khi đọc báo cáo/danh sách chỉ cần vài cột.
7. Quan sát SQL và hiệu năng thực tế trước khi tối ưu provider-specific.

### 27.1. Ma trận theo use case

| Use case | Dữ liệu thực sự cần | Gợi ý tiếp cận |
| --- | --- | --- |
| Danh sách 100 orders: ID, trạng thái, tên khách | Vài scalar fields | DTO projection với JOIN Customer |
| Chi tiết một order và từng dòng hàng | Order + Lines, có thể thêm Product | JOIN FETCH/entity graph có kiểm soát |
| Trang chỉnh sửa order | Managed Order và những association nghiệp vụ cần sửa | Fetch plan theo transaction, tránh graph dư |
| Báo cáo tổng doanh thu theo tháng | Aggregates/scalar | JPQL/native aggregate, không fetch entity graph |
| Batch cập nhật trạng thái orders | IDs và điều kiện update | Bulk DML theo nghiệp vụ, không tải collections vô ích |
| Xuất danh sách tags của một order | Tag projection | Truy vấn riêng Tags hoặc fetch collection phù hợp |
| Giao dịch xem Shipment của một Order | Order + Shipment | Fetch join/graph cho association này |
| API mobile chỉ cần số lượng lines | COUNT aggregate | Không fetch toàn bộ lines chỉ để lấy size |

Đừng chọn `EAGER` chỉ vì một endpoint cụ thể cần dữ liệu đó; hãy cân nhắc xem **mọi** endpoint tải entity root có cần không.

### 27.2. Khi nào EAGER có thể hợp lý?

EAGER có thể phù hợp với association nhỏ, luôn cần thiết trong mọi ngữ cảnh tải entity và chi phí được đo chấp nhận được.

Nhưng điều kiện “luôn cần” phải được kiểm tra trên các use case thật. Một entity có thể được tải trong nhiều tình huống:

- Hiển thị danh sách.
- Lấy một chi tiết.
- Xử lý batch.
- Xác thực.
- Kiểm tra tồn tại.
- Thực thi business rule.

EAGER ở mapping tĩnh ảnh hưởng tới **nhiều con đường tải**, không chỉ code nơi bạn vừa thêm annotation.

## 28. Các lỗi và ngộ nhận thường gặp

### 28.1. “@ManyToOne mặc định LAZY”

Sai theo đặc tả. Nó mặc định **EAGER**. Nếu muốn LAZY, viết:

```java
@ManyToOne(fetch = FetchType.LAZY)
```

### 28.2. “@OneToOne mặc định LAZY vì chỉ có một đối tượng”

Sai. `@OneToOne` mặc định **EAGER**. Số lượng một hay nhiều không tự quyết định giá trị fetch theo cảm tính.

### 28.3. “@OneToMany mặc định EAGER vì parent sở hữu children”

Sai. `@OneToMany` mặc định **LAZY**. Sở hữu vòng đời/cascade/orphanRemoval không làm tự đổi fetch.

### 28.4. “@ManyToMany mặc định EAGER vì có join table”

Sai. Nó mặc định **LAZY**. Join table chỉ là cách ánh xạ quan hệ.

### 28.5. “EAGER = SQL JOIN”

Sai. Provider có thể dùng secondary SELECT, batching hoặc cache. EAGER là yêu cầu nạp state, không phải cú pháp SQL cố định.

### 28.6. “LAZY = tuyệt đối không được tải sớm”

Sai. `LAZY` là hint. Provider được phép fetch sớm hơn theo đặc tả.

### 28.7. “LAZY bảo đảm không N+1”

Sai. N+1 có thể xuất hiện khi truy cập một collection lazy trong vòng lặp qua nhiều root entities.

### 28.8. “EAGER loại bỏ mọi N+1”

Sai. Secondary SELECT để thỏa eager associations cũng có thể tạo N+1.

### 28.9. “@Transactional sẽ fetch mọi association”

Sai. Transaction cung cấp một phạm vi thực thi thích hợp; fetch plan vẫn phải được thiết kế.

### 28.10. “JOIN o.lines l sẽ làm order.getLines() luôn initialized”

Không được giả định. `JOIN` thường phục vụ lọc/chọn; muốn fetch association, dùng `JOIN FETCH` hoặc graph.

### 28.11. “FETCH JOIN collection không ảnh hưởng số hàng”

Sai. Một-to-nhiều có thể tạo nhiều SQL rows cho cùng root entity và làm chi phí tăng.

### 28.12. “FETCH JOIN hai collection luôn tốt hơn một”

Sai. Có nguy cơ tích số hàng và hạn chế provider.

### 28.13. “Dùng collection fetch join với LIMIT/OFFSET luôn phân trang đúng số root”

Sai. Root có thể lặp qua nhiều SQL rows, khiến provider phải phân trang trong memory hoặc áp hạn chế khác.

### 28.14. “CascadeType.ALL làm association EAGER”

Sai. Cascade quản lý lifecycle operations; fetch quản lý kế hoạch tải.

### 28.15. “optional = false tự chuyển EAGER sang LAZY”

Sai. `optional` là metadata về tính bắt buộc, không phải fetch.

### 28.16. “Đã cấu hình LAZY thì không cần kiểm tra provider”

Sai. Đặc biệt với inverse optional `@OneToOne` và basic lazy attributes, hiệu quả trì hoãn có thể phụ thuộc bytecode enhancement/provider.

### 28.17. “EntityGraph chỉ fetch đúng những field đã liệt kê”

Không bảo đảm tuyệt đối. Fetch graph mô tả tập tối thiểu yêu cầu/treatment các attributes; provider có thể lấy thêm state.

### 28.18. “isLoaded(..., 'lines') == true chứng minh @OneToMany mặc định EAGER”

Sai. Collection LAZY vẫn có thể đã được fetch bởi query/graph, cache hoặc provider.

### 28.19. “DTO projection luôn giống entity SELECT”

Sai. DTO chỉ lấy giá trị do projection chọn; không phải managed entity graph đầy đủ.

### 28.20. “Spring Data JPA tự đổi mặc định FetchType”

Sai. Spring Data dựa trên JPA mappings/provider; bốn default annotation không đổi.

### 28.21. “Đổi mọi relation sang EAGER để tránh lỗi JSON serialization”

Nguy hiểm. Có thể tạo graph lớn, N+1, dữ liệu nhạy cảm và vòng lặp quan hệ hai chiều. Nên dùng DTO và fetch plan rõ ràng.

### 28.22. “Một entity được fetch có nghĩa mọi quan hệ của nó cũng được fetch tiếp”

Không. Mỗi association có fetch metadata/graph riêng. Fetch một Customer không đồng nghĩa fetch mọi Orders, Addresses, Roles của Customer.

## 29. Ví dụ thực hành 1: xác định mặc định của các annotation

Cho class:

```java
@Entity
public class Department {

    @ManyToOne
    private Company company;

    @OneToOne
    private DepartmentSettings settings;

    @OneToMany(mappedBy = "department")
    private List<Employee> employees;

    @ManyToMany
    private Set<Project> projects;
}
```

**Câu hỏi:** Quan hệ nào EAGER, quan hệ nào LAZY theo đặc tả nếu không khai báo `fetch`?

**Đáp án:**

| Field | Mapping | Default |
| --- | --- | --- |
| `company` | `@ManyToOne` | EAGER |
| `settings` | `@OneToOne` | EAGER |
| `employees` | `@OneToMany` | LAZY |
| `projects` | `@ManyToMany` | LAZY |

Tên field và business semantics không đổi bảng mặc định.

## 30. Ví dụ thực hành 2: chọn FetchType cho trang danh sách

Một endpoint:

```text
GET /api/orders
```

chỉ trả:

```json
[
  {"id": 101, "status": "PAID", "customerName": "An"},
  {"id": 102, "status": "DRAFT", "customerName": "Binh"}
]
```

**Bài toán:** Có cần đặt `@OneToMany(fetch = EAGER)` lên `lines`?

**Giải thích:** Không. API không sử dụng lines. Một truy vấn DTO:

```jpql
SELECT new com.example.orders.dto.OrderListItem(
    o.id, c.displayName, o.status, o.orderedAt
)
FROM PurchaseOrder o
JOIN o.customer c
```

chỉ lấy những field thực sự cần, tránh fetch collection.

## 31. Ví dụ thực hành 3: trang chi tiết cần lines

Endpoint:

```text
GET /api/orders/101
```

cần toàn bộ dòng hàng. Mapping vẫn:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

**Giải pháp JPQL:**

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

**Giải pháp graph:** tạo entity graph có `lines` rồi áp cho `find/query`.

Không cần đổi static mapping thành EAGER trên mọi use case.

## 32. Ví dụ thực hành 4: quan hệ đơn trị không bắt buộc luôn dùng EAGER

Giả sử Invoice có:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

**Câu hỏi:** Có vi phạm đặc tả vì `@ManyToOne` mặc định EAGER không?

**Đáp án:** Không. Default chỉ áp khi không khai báo. Annotation cho phép người viết **chủ động chọn LAZY**. Provider được phép tải sớm hơn vì LAZY là hint, nhưng khai báo đó hợp lệ.

## 33. Ví dụ thực hành 5: tìm nguyên nhân của 101 SQL queries

Một endpoint đọc 100 orders rồi trong vòng lặp gọi:

```java
for (PurchaseOrder o : orders) {
    for (OrderLine line : o.getLines()) {
        // Hiển thị chi tiết.
    }
}
```

**Câu hỏi:** Vì sao có thể có 101 SELECTs dù `@OneToMany` mặc định LAZY?

**Giải thích:** Một SELECT lấy 100 orders, sau đó mỗi order kích hoạt tải collection riêng. LAZY trì hoãn việc tải, không tự gom các truy vấn. Nên dùng fetch join/graph/batch loading/truy vấn chi tiết theo use case và đo số SQL thực tế.

## 34. Ví dụ thực hành 6: kiểm tra EAGER và số SQL

Một `@ManyToOne` mặc định EAGER. Query lấy 50 Order có 50 Customer khác nhau.

**Câu hỏi:** Có chắc chỉ có một SQL JOIN không?

**Đáp án:** Không. Provider có thể dùng JOIN hoặc nhiều SELECTs. Muốn biết thực tế phải đo SQL. EAGER mô tả yêu cầu tải, không mô tả thuật toán.

## 35. Ví dụ thực hành 7: LEFT JOIN FETCH và đơn không có con

Truy vấn:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.lines
WHERE o.id = :id
```

Nếu order không có lines, inner join có thể **không trả order**.

**Cách sửa nếu muốn giữ order không có lines:**

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

Chọn join type theo ý nghĩa nghiệp vụ; `JOIN FETCH` không tự ngầm là LEFT JOIN.

## 36. Ví dụ thực hành 8: quan hệ một-một phía inverse

Một User có Profile, FK nằm trong Profile. Trong User:

```java
@OneToOne(mappedBy = "user", fetch = FetchType.LAZY)
private Profile profile;
```

**Câu hỏi:** Có chắc provider không truy vấn Profile khi tải User?

**Đáp án:** Không. LAZY là hint; với inverse `@OneToOne` optional, provider có thể cần kiểm tra Profile tồn tại hay không hoặc cần enhancement để trì hoãn hiệu quả. Phải xem provider/version.

## 37. Ví dụ thực hành 9: phân trang root và fetch lines

Query:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.orderedAt DESC
```

được áp `setMaxResults(20)`.

**Câu hỏi:** Có chắc nhận đúng 20 orders đầy đủ lines từ một SQL LIMIT 20 không?

**Đáp án:** Không. Mỗi root có thể tạo nhiều rows. Cân nhắc page IDs trước, rồi fetch những Orders trong page và sắp xếp lại.

## 38. Ví dụ thực hành 10: so sánh @ElementCollection và @ManyToOne

Class:

```java
@ElementCollection
private List<String> labels;

@ManyToOne
private Category category;
```

**Đáp án:** `labels` mặc định LAZY do `@ElementCollection`; `category` mặc định EAGER do `@ManyToOne`. Kiểu Java `List` vs entity reference phản ánh hai mapping khác nhau.

## 39. Ví dụ thực hành 11: fetchgraph và loadgraph

Static mapping:

```text
customer: EAGER
shipment: EAGER
lines: LAZY
tags: LAZY
```

Graph liệt kê chỉ `lines`.

**Câu hỏi:** Khác biệt về semantics khi áp `loadgraph` và `fetchgraph`?

**Đáp án:** `loadgraph` yêu cầu lines được tải và giữ static fetch behavior cho các field khác. `fetchgraph` yêu cầu lines, những field không có graph được xử lý như LAZY theo graph semantics; provider vẫn có thể tải thêm state nên không bảo đảm những field ấy đều chưa loaded.

## 40. Ví dụ thực hành 12: sau khi đóng EntityManager

Service tải Order với LAZY lines rồi đóng EntityManager, controller gọi `getLines().size()`.

**Câu hỏi:** Cách sửa bền vững là gì?

**Đáp án:** Trong service có persistence context phù hợp, dùng fetch plan để lấy lines hoặc truy vấn DTO cần thiết, rồi trả dữ liệu đã dựng. Không đổi mọi quan hệ sang EAGER chỉ để tránh lazy exception ngoài transaction.

## 41. Ví dụ thực hành 13: @Basic và @OneToMany

Entity:

```java
@Basic
private String title;

@OneToMany(mappedBy = "article")
private List<Comment> comments;
```

**Câu hỏi:** Default fetch là gì?

**Đáp án:** `title` EAGER theo `@Basic`, `comments` LAZY theo `@OneToMany`. Đây là hai loại mapping khác nhau.

## 42. Ví dụ thực hành 14: mapping fetch và cascade

Entity:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

**Câu hỏi:** `lines` có bị chuyển sang EAGER không?

**Đáp án:** Không. Fetch mặc định vẫn LAZY. `CascadeType.ALL` liên quan tới lifecycle propagation; `orphanRemoval` liên quan xử lý child bị rời quan hệ sở hữu.

## 43. Câu hỏi tự kiểm tra

**1. Giá trị mặc định của `@ManyToOne.fetch`?**

`FetchType.EAGER`.

**2. Giá trị mặc định của `@OneToOne.fetch`?**

`FetchType.EAGER`.

**3. Giá trị mặc định của `@OneToMany.fetch`?**

`FetchType.LAZY`.

**4. Giá trị mặc định của `@ManyToMany.fetch`?**

`FetchType.LAZY`.

**5. `FetchType.LAZY` là yêu cầu bắt buộc trì hoãn hay một hint?**

Là hint: provider được phép lấy dữ liệu sớm hơn.

**6. `FetchType.EAGER` có buộc dùng SQL JOIN?**

Không. Provider có thể dùng SQL JOIN, secondary SELECT hoặc chiến lược khác để thực hiện yêu cầu tải.

**7. Một `@ManyToOne(optional = false)` nhưng không ghi `fetch` sẽ có giá trị gì?**

EAGER.

**8. Một `@OneToMany(cascade = ALL)` nhưng không ghi `fetch` sẽ có giá trị gì?**

LAZY.

**9. `@ElementCollection` mặc định gì?**

LAZY.

**10. `@Basic` mặc định gì?**

EAGER.

**11. `@OrderBy` có đổi LAZY thành EAGER không?**

Không. Nó mô tả thứ tự, không mô tả chiến lược fetch.

**12. Vì sao N+1 vẫn có thể xảy ra với EAGER?**

Provider có thể dùng secondary SELECT cho những association cần eager loading, dẫn tới nhiều truy vấn phụ khi có nhiều root entities.

**13. Vì sao N+1 vẫn có thể xảy ra với LAZY?**

Ứng dụng truy cập mỗi collection/entity đích trong vòng lặp, khiến provider phải tải riêng từng association.

**14. JOIN thường khác JOIN FETCH ở điểm nào?**

JOIN dùng để ghép kết quả/điều kiện; JOIN FETCH yêu cầu nạp association.

**15. Vì sao LEFT JOIN FETCH hữu ích với collection có thể rỗng?**

Nó giữ entity root ngay cả khi không có phần tử liên kết.

**16. Tại sao không nên fetch hai collection lớn trong một query mà không kiểm tra?**

Có thể tạo tích số rows, tăng chi phí memory/SQL và gặp giới hạn provider.

**17. Có nên collection fetch join trực tiếp với phân trang không?**

Cần hết sức thận trọng vì SQL rows nhân bản theo số child, có thể dẫn tới pagination trong memory hoặc kết quả không đúng kỳ vọng.

**18. Entity graph `loadgraph` khác `fetchgraph` ở đâu?**

`loadgraph` giữ static fetch defaults cho attributes không có trong graph; `fetchgraph` xử lý những attributes không liệt kê như LAZY theo graph semantics, nhưng provider có thể fetch thêm.

**19. Một association LAZY có thể đã được loaded khi `find` trả về không?**

Có. LAZY là hint và dữ liệu cũng có thể đến từ graph, query khác, cache hoặc cơ chế provider.

**20. Dùng API JPA nào để hỏi attribute đã loaded chưa?**

`PersistenceUnitUtil.isLoaded(entity, "attributeName")`.

**21. Vì sao mapping inverse optional `@OneToOne(fetch=LAZY)` có thể vẫn phát SQL sớm?**

Provider có thể cần xác định có entity bên kia hay không và tùy khả năng proxy/enhancement.

**22. `@Transactional` có làm mọi association LAZY thành EAGER không?**

Không. Nó liên quan tới transaction; fetch plan vẫn được xác định riêng.

**23. Vì sao DTO projection thích hợp với danh sách orders?**

Nó lấy những field cần thiết mà không phải tải entity graph chỉ để hiển thị.

**24. Có thể tự thay mặc định EAGER của `@ManyToOne` thành LAZY không?**

Có, bằng `fetch = FetchType.LAZY`, với lưu ý LAZY là hint.

**25. Giá trị fetch mặc định có thay đổi vì `mappedBy` hay FK nằm ở phía khác không?**

Không. Default theo loại relationship annotation, không theo vị trí FK.

## 44. Tình huống phân tích tổng hợp

Giả sử hệ thống có các quan hệ:

```java
@Entity
class BlogPost {

    @ManyToOne
    private Author author;

    @OneToOne
    private SeoMetadata seo;

    @OneToMany(mappedBy = "post")
    private List<Comment> comments;

    @ManyToMany
    private Set<Tag> tags;

    @ElementCollection
    private List<String> keywords;
}
```

Ứng dụng có ba use case:

1. **Danh sách 50 bài viết**: chỉ cần `id`, `title`, `author.displayName`.
2. **Chi tiết một bài viết**: cần bài viết, tác giả, SEO metadata, 20 bình luận đầu tiên và tags.
3. **Thống kê**: đếm bình luận theo bài viết trong một tháng.

### 44.1. Xác định giá trị mặc định

| Association | Default |
| --- | --- |
| `author` (`@ManyToOne`) | EAGER |
| `seo` (`@OneToOne`) | EAGER |
| `comments` (`@OneToMany`) | LAZY |
| `tags` (`@ManyToMany`) | LAZY |
| `keywords` (`@ElementCollection`) | LAZY |

### 44.2. Thiết kế query cho danh sách

Thay vì trả managed BlogPost rồi serialize cả graph, dùng DTO projection theo các field thực sự cần. Có thể chủ động chuyển `author`/`seo` tĩnh thành LAZY nếu provider hỗ trợ tốt và màn hình danh sách thường không cần SEO metadata, rồi dùng fetch graph ở nơi cần.

### 44.3. Thiết kế query cho chi tiết

Với comments cần **phân trang riêng**, không nên fetch toàn bộ collection rồi tự cắt 20 phần tử trong Java. Tốt hơn có thể:

- Lấy BlogPost cùng author/seo theo fetch plan rõ ràng.
- Truy vấn 20 Comment theo `post.id` và sort ổn định.
- Truy vấn Tags khi UI cần, hoặc dùng fetch graph nhỏ nếu kích thước hợp lý.

### 44.4. Thiết kế query cho thống kê

Dùng `COUNT`, `GROUP BY` hoặc aggregate SQL trên Comment, **không fetch mọi comments** rồi đếm trong Java.

Bài toán này cho thấy: **Giá trị fetch mặc định là kiến thức cần nhớ, còn fetch plan phù hợp là quyết định phải đưa ra cho từng use case.**

## 45. Ghi nhớ cuối bài

Đối với **bốn loại relationship mappings của JPA**, quy tắc mặc định là:

```text
SINGLE-VALUED ENTITY RELATIONSHIPS
    @ManyToOne  -> EAGER
    @OneToOne   -> EAGER

COLLECTION-VALUED ENTITY RELATIONSHIPS
    @OneToMany  -> LAZY
    @ManyToMany -> LAZY
```

Đừng đảo ngược hai nhóm chỉ vì dự án của bạn chủ động cấu hình nhiều quan hệ đơn trị thành LAZY. **Đặc tả mặc định EAGER cho `@ManyToOne` và `@OneToOne`; LAZY cho `@OneToMany` và `@ManyToMany`.**

Nhưng học thuộc bảng mặc định chỉ là bước đầu. Cần hiểu rằng:

- **EAGER** là yêu cầu tải theo fetch plan, **không phải cam kết SQL JOIN**.
- **LAZY** là hint, **không bảo đảm** dữ liệu chưa được fetch và không bảo đảm không có SQL bổ sung.
- **Fetch** độc lập với cascade, orphanRemoval, optional, mappedBy và quyền sở hữu FK.
- **N+1** có thể xuất hiện với cả EAGER và LAZY, tùy cách provider thực thi và cách ứng dụng truy cập dữ liệu.
- **JOIN FETCH, entity graphs, Criteria fetch và DTO projection** giúp xác định dữ liệu cần cho từng use case, tránh buộc cả ứng dụng phải tải graph quá rộng.
- **Collection fetch join** phải được cân nhắc khi có nhiều collection hoặc phân trang.
- **PersistenceUnitUtil**, SQL logging và integration/performance tests trên provider thật giúp xác định hành vi thực tế, không thay đổi mặc định của đặc tả.

Một kế hoạch tải tốt không dựa vào khẩu hiệu “mọi thứ LAZY” hay “mọi thứ EAGER”. Nó bắt đầu từ **hợp đồng JPA**, tiếp tục bằng **dữ liệu mỗi chức năng thực sự cần**, rồi được kiểm chứng bằng **SQL và hiệu năng quan sát được** trên môi trường chạy.
