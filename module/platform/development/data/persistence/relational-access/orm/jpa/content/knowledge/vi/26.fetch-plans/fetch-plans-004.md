# Tác động của thời điểm truy cập thuộc tính đến việc tải dữ liệu trong JPA

## 1. Cùng một entity nhưng thời điểm truy cập có thể quyết định SQL nào được chạy

Trong ứng dụng Java sử dụng **Jakarta Persistence (JPA)**, lệnh truy vấn trả về một entity không có nghĩa **toàn bộ object graph** liên quan đến entity đó đã được đưa vào bộ nhớ.

Giả sử hệ thống đặt hàng có entity `PurchaseOrder`:

```text
PurchaseOrder
  |
  +-- id
  +-- status
  +-- orderedAt
  +-- customer --------------> Customer
  |
  +-- lines -----------------> List<OrderLine>
                                 |
                                 +-- product --> Product
```

Tầng repository lấy danh sách đơn:

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

Sau đó một đoạn code chỉ in ID:

```java
for (PurchaseOrder order : orders) {
    System.out.println(order.getId());
}
```

Một đoạn code khác in số dòng hàng:

```java
for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Một đoạn code thứ ba in tên sản phẩm:

```java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        System.out.println(line.getProduct().getName());
    }
}
```

**Ba đoạn code nhận cùng một danh sách entity nhưng có thể tạo ra số câu SQL rất khác nhau.**

Nguyên nhân là **fetch plan** (kế hoạch tải) và **thời điểm ứng dụng truy cập dữ liệu** phối hợp quyết định lúc nào provider phải đưa association hoặc một thuộc tính còn chưa được nạp vào bộ nhớ.

Có thể hình dung:

```text
T0: getResultList()
      |
      | SQL tải PurchaseOrder
      v
    PurchaseOrder #101, #102, #103
      |
T1: order.getId()
      |
      | Trường đã có sẵn -> thông thường không cần SQL bổ sung
      v
    101
      |
T2: order.getLines().size()
      |
      | Collection chưa khởi tạo -> có thể phát SELECT lines
      v
    2
      |
T3: line.getProduct().getName()
      |
      | Quan hệ tới Product chưa có dữ liệu -> có thể phát SELECT product
      v
    "Bàn phím"
```

Bài học tập trung vào câu hỏi cốt lõi:

> **Ở thời điểm nào dữ liệu của một thuộc tính/quan hệ được yêu cầu, và tại thời điểm đó JPA provider có thể lấy dữ liệu từ đâu?**

Để trả lời chính xác, cần phân biệt **kiểu tải EAGER/LAZY**, **fetch plan của query**, **trạng thái persistence context**, **phần dữ liệu đã được tải/cached**, và **hành vi thực tế của code gọi thuộc tính**.

---

## 2. Bốn khái niệm không nên đánh đồng

### 2.1. Entity đã được truy vấn

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
```

Từ thời điểm này, `order` là managed entity nếu tìm thấy và vẫn thuộc persistence context đang mở. Tuy nhiên, những quan hệ đặt `LAZY` của `order` có thể vẫn chưa được tải.

### 2.2. Thuộc tính đã được nạp

Một thuộc tính/association **loaded** nghĩa là provider đã có giá trị đủ để trả theo trạng thái nạp hiện tại mà không cần truy xuất dữ liệu bổ sung cho chính thuộc tính đó.

Ví dụ:

- `order.id` thường đã có khi root entity được lấy từ SQL.
- `order.status` thường được tải cùng các basic columns mặc định EAGER.
- `order.lines` có thể chưa được khởi tạo vì là collection LAZY.
- `line.product` có thể mới chỉ có khóa ngoại hoặc reference; `product.name` chưa được lấy.

**Loaded** không đồng nghĩa “mọi entity có thể đi tới từ field này đều loaded”.

### 2.3. Managed hay detached

**Managed** nghĩa là entity thuộc một persistence context. **Detached** nghĩa là entity không còn được quản lý bởi context đó.

Một entity detached có thể chứa một số dữ liệu đã nạp trước đó, nhưng không thể trông đợi nó tự tải phần dữ liệu còn thiếu qua context cũ đã đóng.

### 2.4. EAGER hay LAZY

- **EAGER** mô tả yêu cầu/hint về dữ liệu cần được lấy theo fetch strategy, không bắt buộc provider phải dùng đúng **một SQL JOIN**.
- **LAZY** mô tả ý định trì hoãn truy xuất dữ liệu cho tới lúc cần; với nhiều loại mapping, đó là **hint**, không phải lời hứa tuyệt đối rằng provider sẽ không tải sớm.

Một entity có thể được fetch theo LAZY mapping nhưng vẫn có dữ liệu association trong bộ nhớ vì query đã `JOIN FETCH`, entity graph yêu cầu tải, association được tải ở lần truy cập trước hoặc entity đã có trong cache.

---

## 3. Fetch plan và thời điểm truy cập là hai trục độc lập

Giả sử:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
```

Có hai câu hỏi:

1. **Khi lấy PurchaseOrder, fetch plan yêu cầu nạp lines ngay không?**
2. **Sau khi có PurchaseOrder, khi nào code lần đầu cần dữ liệu lines?**

Nếu query không yêu cầu fetch lines và provider trì hoãn nạp collection:

```text
getResultList()                -> SELECT orders
getStatus()                   -> Không cần SELECT lines
getLines()                    -> Trả collection wrapper; có thể chưa nạp
getLines().iterator()         -> Thường cần SELECT lines
getLines().size()             -> Có thể SELECT lines hoặc COUNT tùy provider
getLines().get(0)             -> Thường cần dữ liệu phần tử
```

Nếu query có fetch join:

```sql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

thì **lines** đã được query yêu cầu tải trước lúc trả kết quả root. Lần duyệt `getLines()` sau đó, trong cùng state không bị refresh/evict, thông thường không cần một câu SELECT collection riêng nữa.

Đó là lý do **cùng một đoạn Java truy cập `getLines()`** có thể phát SQL trong request này nhưng không phát SQL trong request khác.

### 3.1. Một bảng ghi nhớ

| Trạng thái trước khi truy cập | Lệnh truy cập | Điều thường xảy ra |
|---|---|---|
| Basic field EAGER đã nạp | `order.getStatus()` | Đọc từ Java object, không cần SELECT riêng. |
| LAZY collection chưa khởi tạo | Duyệt `order.getLines()` | Có thể phát SELECT các lines. |
| LAZY collection đã được fetch join | Duyệt `order.getLines()` | Đọc từ collection đã nạp. |
| LAZY association đã có managed entity trong context | `getCustomer().getName()` | Có thể không cần SQL mới do identity map. |
| Association chưa nạp, context đã đóng | Truy cập field cần load | Có thể thất bại vì không có context phục vụ tải. |
| Entity còn managed nhưng provider chưa cần dữ liệu | `getId()` hoặc thao tác đã có state | Có thể không cần SQL mới. |
| `getReference()` trả proxy/reference chưa khởi tạo | Truy cập non-ID state | Có thể cần SELECT hoặc phát lỗi nếu context không sẵn sàng. |

Bảng mô tả hành vi điển hình, **không phải bảo đảm số SQL của mọi provider**. Số câu query thực tế còn phụ thuộc fetch plans, batching, cache, enhancement và dữ liệu.

---

## 4. Mặc định fetch của các annotation quan hệ

Chỉ riêng việc viết `@ManyToOne` hay `@OneToMany` đã có ý nghĩa về mặc định tải.

| Mapping | Fetch mặc định theo JPA | Điều cần nhớ |
|---|---|---|
| `@ManyToOne` | **EAGER** | Đọc order có thể dẫn tới việc nạp customer dù code chưa gọi getter. |
| `@OneToOne` | **EAGER** | Đọc một phía có thể dẫn tới việc nạp phía kia. |
| `@OneToMany` | **LAZY** | Collection thường được nạp khi cần. |
| `@ManyToMany` | **LAZY** | Collection thường được nạp khi cần. |
| `@ElementCollection` | **LAZY** | Collection các basic/embeddable values thường bị trì hoãn. |
| `@Basic` | **EAGER** | Các scalar fields thông thường được tải cùng entity. |

Theo ngữ nghĩa JPA, **EAGER là yêu cầu đối với provider**, còn **LAZY là hint** ở những trường hợp tương ứng; provider có thể fetch sớm hơn điều lập trình viên mong muốn.

### 4.1. Ví dụ default to-one khiến “truy vấn nhỏ” thành truy vấn nhiều dữ liệu

```java
@ManyToOne
private Customer customer;
```

Nếu không ghi `fetch = FetchType.LAZY`, default là **EAGER**.

Một query:

```sql
SELECT o FROM PurchaseOrder o
```

có thể khiến provider:

- JOIN trực tiếp bảng Customer vào SELECT ban đầu; **hoặc**
- SELECT orders trước, rồi dùng thêm các SELECT để đáp ứng EAGER association; **hoặc**
- tận dụng cache/chiến lược khác.

**EAGER không đồng nghĩa một SQL JOIN.** Một tập entity có EAGER to-one vẫn có thể gây vấn đề N+1 nếu provider dùng secondary selects.

### 4.2. Khai báo rõ LAZY cho to-one khi phù hợp

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Mục đích là tránh nạp Customer chỉ vì đọc danh sách PurchaseOrder, khi use case chưa cần customer.

Tuy nhiên, **LAZY trên to-one có thể cần proxy hoặc bytecode enhancement** và không phải là lời hứa cứng về SQL timing ở mọi provider/mapping.

### 4.3. Vì sao không đặt EAGER cho mọi thứ?

```java
@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
```

Nếu mỗi order có 100 dòng hàng, việc lấy 1.000 orders có thể kéo theo việc tải số lượng lớn OrderLine chỉ để hiển thị mã/status.

Ngoài chi phí truyền dữ liệu và bộ nhớ, EAGER có thể làm:

- Mở rộng số hàng JOIN.
- Tạo các secondary SELECT không mong muốn.
- Khó tối ưu theo từng màn hình.
- Phức tạp hóa pagination.
- Tải tiếp quan hệ EAGER khác của child.

EAGER là lựa chọn phải có **lý do nghiệp vụ ổn định**, không phải cách mặc định chữa mọi lỗi lazy loading.

---

## 5. Ví dụ entity xuyên suốt bài học

Ta dùng bốn entity: `Customer`, `PurchaseOrder`, `OrderLine`, `Product`.

### 5.1. Entity `Customer`

```java
package com.example.fetch;

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

### 5.2. Entity `Product`

```java
package com.example.fetch;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal price;

    protected Product() {}

    public Product(String name, BigDecimal price) {
        if (name == null || name.isBlank() ||
                price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Product không hợp lệ");
        }
        this.name = name;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
```

### 5.3. Entity `PurchaseOrder`

```java
package com.example.fetch;

import jakarta.persistence.*;
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

    @Column(nullable = false, length = 30)
    private String status;

    @Column(name = "ordered_at", nullable = false)
    private LocalDateTime orderedAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY,
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
            Customer customer,
            String status,
            LocalDateTime orderedAt
    ) {
        this.customer = Objects.requireNonNull(customer);
        this.status = Objects.requireNonNull(status);
        this.orderedAt = Objects.requireNonNull(orderedAt);
    }

    public void addLine(Product product, int quantity) {
        lines.add(new OrderLine(this, product, quantity));
    }

    public Long getId() { return id; }
    public String getStatus() { return status; }
    public LocalDateTime getOrderedAt() { return orderedAt; }
    public Customer getCustomer() { return customer; }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

**Điểm về collection wrapper:** ví dụ `getLines()` trả một unmodifiable view của collection persistent. `Collections.unmodifiableList` không ép khởi tạo toàn bộ collection chỉ bởi việc tạo view theo contract Java, nhưng một số thao tác trên view sẽ được chuyển cho persistent collection gốc và có thể kích hoạt tải dữ liệu. Nếu cần kiểm tra trạng thái loaded, không dùng việc đoán SQL qua getter/view; sử dụng công cụ ở phần sau.

### 5.4. Entity `OrderLine`

```java
package com.example.fetch;

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

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    OrderLine(PurchaseOrder order, Product product, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải > 0"
            );
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

To-one associations được đánh dấu `LAZY` rõ ràng. Nếu bỏ `fetch` trong `@ManyToOne`, JPA default sẽ là EAGER và dấu vết SQL ban đầu có thể khác nhiều.

### 5.5. DDL tham khảo

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    price DECIMAL(15, 2) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    ordered_at TIMESTAMP NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id)
        REFERENCES products(id)
);

CREATE INDEX ix_lines_order ON order_lines(order_id);
CREATE INDEX ix_lines_product ON order_lines(product_id);
CREATE INDEX ix_orders_customer ON purchase_orders(customer_id);
```

DDL có tính minh họa; cú pháp IDENTITY và column types có thể khác theo database.

---

## 6. Dữ liệu mẫu và ba thời điểm quan sát

Giả sử database có:

| Đơn hàng | Khách | Status | Lines |
|---|---|---|---|
| Order#101 | An | NEW | Keyboard × 1; Mouse × 2 |
| Order#102 | An | PAID | Không có line |
| Order#103 | Bình | NEW | Monitor × 1 |

Và ba products:

```text
Product#1: Keyboard
Product#2: Mouse
Product#3: Monitor
```

**T0 — Truy vấn root entities**

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o FROM PurchaseOrder o
    ORDER BY o.id
    """,
    PurchaseOrder.class
).getResultList();
```

Trong một provider chọn LAZY thực tế cho `lines` và `customer`, SQL khái niệm:

```sql
SELECT
    o.id,
    o.status,
    o.ordered_at,
    o.customer_id
FROM purchase_orders o
ORDER BY o.id;
```

**T1 — Chỉ đọc basic fields**

```java
for (PurchaseOrder order : orders) {
    System.out.println(order.getId() + " " + order.getStatus());
}
```

Vì `id`, `status` đã nạp ở root query, thông thường không phát thêm SQL.

**T2 — Đọc lines**

```java
for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Nếu collection chưa khởi tạo, provider có thể phát:

```sql
SELECT * FROM order_lines WHERE order_id = 101;
SELECT * FROM order_lines WHERE order_id = 102;
SELECT * FROM order_lines WHERE order_id = 103;
```

Với provider có “extra-lazy”/collection size optimization, nó có thể phát `SELECT COUNT(*)` thay vì tải toàn bộ lines cho thao tác `size()`. **JPA không quy định chính xác chiến lược SQL cho `size()` của mọi provider.**

**T3 — Đọc tên product**

```java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        System.out.println(line.getProduct().getName());
    }
}
```

Provider có thể tiếp tục fetch Products nếu chưa có trong persistence context hoặc cache.

### 6.1. Kết luận từ ví dụ

Không phải chỉ `getResultList()` mới tạo SQL. **Vị trí trong call stack nơi lần đầu cần một thuộc tính chưa nạp** có thể là điểm provider phát query.

Điều này tác động tới:

- Số round trips DB.
- Độ trễ của API.
- Thời gian giữ persistence context/connection.
- Khả năng gặp lỗi khi entity detached.
- Dữ liệu nhìn thấy nếu các truy vấn xảy ra ở những thời điểm khác nhau.
- Khả năng dự đoán hiệu năng khi refactor code.

---

## 7. “Truy cập thuộc tính” nghĩa là những thao tác nào?

Không phải chỉ việc gọi getter trực tiếp mới đọc dữ liệu. Nhiều thao tác gián tiếp cũng có thể khiến một association được sử dụng.

| Thao tác | Có thể cần nạp dữ liệu chưa có? | Vì sao |
|---|---|---|
| `order.getId()` | Thường không | ID thường đã biết, kể cả trên một số proxy. |
| `order.getStatus()` | Thường không nếu basic đã loaded | Basic field mặc định EAGER. |
| `order.getCustomer()` | Phụ thuộc provider/mapping | Có thể trả proxy/reference hoặc khởi tạo association. |
| `order.getCustomer().getFullName()` | Có | Cần trường non-ID của Customer. |
| `order.getLines()` | Phụ thuộc cách triển khai getter | Có thể trả wrapper chưa khởi tạo. |
| `order.getLines().size()` | Có | Cần kích thước; có thể load collection hoặc query COUNT. |
| `order.getLines().iterator()` | Có | Cần phần tử để duyệt. |
| `order.getLines().stream().map(...)` | Có | Terminal operation thường cần duyệt elements. |
| `order.toString()` | Có nếu method đọc relations | Logging/debug vô tình gọi getter. |
| `Objects.equals(order.getLines(), ...)` | Có thể | So sánh collection có thể cần phần tử. |
| `hashCode()/equals()` của entity | Có thể nếu code đọc relations | Equality implementation có thể kích hoạt tải. |
| JSON/XML serialization | Có | Serializer có thể gọi getters đệ quy. |
| Mapping entity sang DTO | Có | Mapper đọc từng field được cấu hình. |
| Template engine / UI view | Có | Truy cập nested property trong rendering. |
| IDE debugger object inspection | Có thể | Evaluating getters/toString có thể phát SQL. |
| `PersistenceUnitUtil.isLoaded(...)` | Dùng để quan sát loaded state | Không được hiểu như hành động fetch dữ liệu. |

Một quy tắc thực tế:

> **Truy cập đến nơi cần giá trị thực của association là ranh giới có thể kích hoạt SQL, không phải nhất thiết nơi entity ban đầu được lấy.**

### 7.1. Đừng phụ thuộc “getter đầu tiên không query”

Một provider có thể:

- Dùng proxy.
- Dùng bytecode enhancement.
- Dùng persistent collection wrapper.
- Đã fetch association từ query.
- Có entry trong first-level/second-level cache.
- Fetch sớm dù mapping đánh dấu LAZY.

Vì vậy, không nên viết business logic phụ thuộc vào giả định rằng **“gọi `getCustomer()` luôn miễn phí nhưng `getCustomer().getName()` luôn phát một SELECT”**. Đó chỉ là mô hình minh họa thường gặp với proxy.

### 7.2. Thay đổi nhỏ trong logging có thể thay đổi hiệu năng

Ví dụ:

```java
log.debug("Processing order {}", order);
```

Nếu `PurchaseOrder.toString()` chứa:

```java
@Override
public String toString() {
    return "PurchaseOrder{id=" + id
        + ", lines=" + lines
        + ", customer=" + customer
        + "}";
}
```

thì việc format object có thể khiến provider phải đọc associations.

Hậu quả là chỉ bật debug logging cũng có thể làm tăng số SQL. Một cách an toàn hơn:

```java
log.debug(
    "Processing order id={}, status={}",
    order.getId(),
    order.getStatus()
);
```

Không đưa collection hoặc nhiều nested entities vào `toString` mặc định của entity.

---

## 8. `@PostLoad` và entity listeners không bảo đảm mọi association đã loaded

Một lifecycle callback:

```java
@PostLoad
private void afterLoad() {
    // Được gọi khi JPA load/refresh entity theo lifecycle.
}
```

Có thể gây hiểu lầm:

> “Nếu `@PostLoad` đã chạy thì mọi thuộc tính của entity và các quan hệ đã nạp xong.”

**Không đúng.** `@PostLoad` của root entity không đồng nghĩa toàn bộ LAZY associations của graph đã được khởi tạo.

### 8.1. Callback có thể vô tình kích hoạt tải thêm

Ví dụ không nên lạm dụng:

```java
@PostLoad
private void afterLoad() {
    int count = lines.size(); // Có thể đòi load collection.
    // ...
}
```

Nếu callback của mọi PurchaseOrder đều chạm vào `lines`, một query tải 100 orders có thể kích hoạt nhiều SELECT để đọc lines.

Ngoài hiệu năng, callback làm việc với relationship graph có các hạn chế về lifecycle, khả năng truy vấn, portability và side effects. Trong ứng dụng cần rõ ràng, nên để callback thực hiện việc nhẹ liên quan state tại entity, còn việc chọn dữ liệu tải là trách nhiệm của repository/use case.

### 8.2. Khi nào @PostLoad xảy ra?

Nó gắn với việc load/refresh managed entity theo JPA lifecycle. Nó **không phải callback “mỗi lần getter được gọi”** và không tự chạy lại chỉ vì collection LAZY được truy cập.

### 8.3. Đừng thiết kế event theo “association vừa được lazy load”

JPA callback chuẩn không cung cấp một sự kiện phổ quát như `@PostLazyCollectionInitialize` cho mọi association. Các hooks chi tiết về collection initialization là phần mở rộng của provider, nếu có, chứ không phải API JPA portable.

Nếu use case cần đo những lần lazy loads, dùng SQL logging/metrics hoặc provider instrumentation thay vì cố gắn domain event vào getter.

---

## 9. Persistence context: nơi lazy loading diễn ra

Một persistence context quản lý identity, state và lifecycle của entity. Thông thường nó gắn với một `EntityManager`.

### 9.1. Trong context đang mở

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

    // Nếu lines LAZY và chưa nạp, có thể load tại đây.
    int lineCount = order.getLines().size();

    tx.commit();
} finally {
    if (tx.isActive()) tx.rollback();
    em.close();
}
```

Ở thời điểm `getLines().size()`, entity đang managed và context có điều kiện thực hiện truy vấn SQL bổ sung.

### 9.2. Sau khi context đóng

```java
PurchaseOrder order;

EntityManager em = emf.createEntityManager();

try {
    order = em.find(PurchaseOrder.class, orderId);
} finally {
    em.close();
}

// Entity nay detached; lines có thể chưa loaded.
System.out.println(order.getLines().size());
```

Nếu `lines` chưa được khởi tạo trước lúc close, provider không còn một persistence context mở để tải dữ liệu. Với Hibernate, một lỗi thường gặp là:

```text
org.hibernate.LazyInitializationException:
failed to lazily initialize a collection ... no Session
```

`LazyInitializationException` là exception của **Hibernate**, không phải tên exception chuẩn do JPA áp dụng cho mọi provider.

### 9.3. Transaction và persistence context không hoàn toàn đồng nghĩa

Một transaction là ranh giới nhất quán/commit/rollback; một persistence context là nơi entity được quản lý.

Trong một số môi trường, persistence context có thể vẫn mở sau khi transaction kết thúc, hoặc là extended persistence context. Khả năng lazy loading ở ngoài transaction sẽ phụ thuộc provider, kiểu EntityManager, connection/transaction policy và cấu hình.

Vì vậy:

- **Không tuyên bố** “commit luôn làm entity detached ngay”.
- **Không tuyên bố** “còn Java EntityManager reference thì lazy load luôn được”.
- **Không khuyến khích** phụ thuộc vào lazy loading phát SQL ngoài transaction có chủ đích.

Chiến lược an toàn là **nạp những dữ liệu use case cần trong boundary được kiểm soát**, rồi trả DTO cho layer bên ngoài khi thích hợp.

### 9.4. `em.clear()` làm entities detached

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.clear();

order.getLines().size(); // Có thể lỗi nếu lines chưa nạp.
```

`clear` không xóa object Java. Nó detach các managed entities và pending changes chưa được flush có thể mất, nên không dùng `clear` tùy tiện để “tăng tốc”. Bài học ở đây là **còn object reference không đồng nghĩa còn đường nạp association**.

### 9.5. `em.detach(order)`

```java
em.detach(order);
```

chỉ detach entity cụ thể, với những quy tắc cascade DETACH nếu mapping có. Một LAZY association chưa được nạp của detached entity không nên được kỳ vọng có thể fetch thêm theo context cũ.

---

## 10. Điều gì xảy ra khi đã nạp association trước khi detach?

Ví dụ:

```java
PurchaseOrder order;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    order = em.find(PurchaseOrder.class, orderId);

    // Cố ý initialize lines trong persistence context.
    order.getLines().size();

    tx.commit();
} finally {
    if (tx.isActive()) tx.rollback();
    em.close();
}

// Các phần tử lines đã được lấy trước khi detach.
for (OrderLine line : order.getLines()) {
    System.out.println(line.getQuantity());
}
```

Ở ví dụ provider thực sự đã initialize collection, việc duyệt list đã loaded sau khi detach có thể hoạt động vì dữ liệu nằm trong Java memory.

Nhưng:

```java
line.getProduct().getName()
```

vẫn có thể thất bại nếu association `product` của từng line chưa được tải.

### 10.1. “Đã tải collection” không đồng nghĩa “đã tải toàn graph”

```text
PurchaseOrder                 loaded
  |
  +-- lines                   loaded
        |
        +-- Line#1            loaded
        |     |
        |     +-- product     có thể chưa loaded
        |
        +-- Line#2            loaded
              |
              +-- product     có thể chưa loaded
```

Nếu API cần hiển thị tên sản phẩm, phải làm rõ **đường đi thuộc tính**:

```text
PurchaseOrder.lines[*].product.name
```

và đưa fetch plan tương ứng, thay vì chỉ initialize `PurchaseOrder.lines`.

### 10.2. Merge không phải cơ chế “tải hết mọi dữ liệu thiếu”

```java
PurchaseOrder managedCopy = em.merge(detachedOrder);
```

`merge` dùng để sao chép state của detached entity theo semantics JPA vào managed entity; nó **không phải một lời hứa** rằng toàn bộ LAZY associations của graph được initialize.

Nếu cần tải dữ liệu để đọc, nên query/fetch theo use case thay vì dùng `merge` như một thủ thuật khôi phục lazy loading.

---

## 11. `getReference()` và thời điểm truy vấn

JPA cho phép lấy một reference:

```java
PurchaseOrder reference =
    em.getReference(PurchaseOrder.class, orderId);
```

Mục tiêu API là có thể nhận reference tới identity mà không cần tải ngay toàn bộ state.

Trong một số provider:

```java
Long id = reference.getId();
```

có thể không cần SELECT, vì ID đã biết.

Nhưng khi gọi:

```java
String status = reference.getStatus();
```

provider có thể phải truy vấn entity. Nếu ID không tồn tại, một lỗi `EntityNotFoundException` có thể được báo tại thời điểm truy cập state, hoặc provider có thể kiểm tra sớm hơn.

### 11.1. Không dùng getReference để bảo đảm “không chạm DB”

`getReference` có thể trả proxy/reference; mức trì hoãn truy vấn, các phương thức kích hoạt khởi tạo và thời điểm phát hiện identity không tồn tại phụ thuộc provider.

Trong trường hợp chỉ muốn gán FK tới entity đã biết ID:

```java
Customer customerRef =
    em.getReference(Customer.class, customerId);
```

có thể hữu ích để gán association mà không cần tải đầy đủ Customer, nếu quan hệ và transaction hợp lệ. Tuy nhiên, khi cần xác thực customer có tồn tại hoặc kiểm tra business rules từ Customer, phải thực hiện kiểm tra thích hợp; reference không thay thế xác minh nghiệp vụ.

---

## 12. `@Basic(fetch = LAZY)` và thuộc tính không phải association

Không chỉ relationship mới có fetch strategy. Basic fields cũng có `@Basic(fetch=...)`.

Ví dụ document content lớn:

```java
@Entity
@Table(name = "documents")
public class Document {

    @Id
    private Long id;

    @Column(name = "title", nullable = false)
    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "body_text")
    private String bodyText;

    protected Document() {}

    public String getTitle() { return title; }
    public String getBodyText() { return bodyText; }
}
```

Ý định:

- Truy vấn danh sách documents chỉ hiển thị `title`.
- `bodyText` lớn chỉ được nạp khi người dùng mở chi tiết.

**Nhưng:** `@Basic(fetch = FetchType.LAZY)` là hint. Một provider có thể cần bytecode enhancement/instrumentation để lazy-load basic field. Nếu chưa cấu hình đúng, SQL ban đầu vẫn có thể SELECT `body_text`.

### 12.1. Phương án chắc chắn hơn khi field rất lớn

Tách dữ liệu vào entity phụ:

```text
Document
  id
  title

DocumentBody
  id / document_id
  body_text
```

Rồi truy vấn danh sách `Document` không chứa cột body ngay từ thiết kế schema, hoặc dùng projection chỉ SELECT id/title.

### 12.2. Projection là cách kiểm soát SELECT columns rõ ràng

```java
List<DocumentListRow> rows = em.createQuery(
    """
    SELECT NEW com.example.fetch.DocumentListRow(
        d.id,
        d.title
    )
    FROM Document d
    ORDER BY d.id
    """,
    DocumentListRow.class
).getResultList();
```

DTO:

```java
package com.example.fetch;

public record DocumentListRow(Long id, String title) {}
```

Cách này không yêu cầu tạo entity `Document` đầy đủ rồi hy vọng provider bỏ qua `bodyText`. Query chỉ chọn những scalar expressions được dùng cho DTO.

### 12.3. Embedded values

Một `@Embedded` thường là nhóm fields nằm trong state entity. Không nên suy luận rằng chỉ vì Java có object `Address address` thì nó được fetch giống một to-one entity association. Quy tắc basic/embeddable loading tùy mapping và provider enhancement, không giống mặc định LAZY của collection relationships.

---

## 13. `@OneToOne` và trường hợp LAZY khó hơn tưởng tượng

Ví dụ:

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

Và bên sở hữu FK:

```java
@Entity
public class AccountProfile {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", unique = true)
    private Account account;
}
```

Ở phía `AccountProfile.account`, khóa ngoại có thể giúp provider tạo reference tới Account.

Ở phía `Account.profile` với `mappedBy`, bảng Account không có FK tới profile. Provider có thể cần kiểm tra **có profile hay không** mới biết property có null hay tạo proxy được. Tùy provider, optionality, ID strategy và bytecode enhancement, nó có thể phát SQL sớm dù `fetch = LAZY`.

### 13.1. Bài học về thời điểm truy cập

`@OneToOne(fetch = LAZY)` không chứng minh rằng:

```java
Account account = em.find(Account.class, id);
```

chỉ chạy **một SQL** và không bao giờ hỏi bảng profile. Hãy đo SQL thực tế.

### 13.2. Các phương án khi cần trì hoãn chắc chắn hơn

- Xem lại phía FK và ownership.
- Xem mapping shared primary key với `@MapsId` khi đúng domain.
- Sử dụng bytecode enhancement/provider feature nếu được hỗ trợ.
- Tách query danh sách account khỏi query lấy profile.
- Dùng DTO cho màn hình không cần profile.
- Viết integration test với provider/dialect mục tiêu.

Không cố thay đổi thiết kế quan hệ chỉ vì muốn giảm một SQL mà làm sai mô hình dữ liệu.

---

## 14. Quan hệ LAZY đã có sẵn trong identity map hoặc cache

Giả sử:

```java
Customer customer = em.find(Customer.class, customerId);

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

String name = order.getCustomer().getFullName();
```

Nếu `order.customer` trỏ đúng Customer đã managed, provider có thể tái sử dụng entity cùng identity trong persistence context. Khi đó truy cập `getFullName()` có thể không cần SELECT bổ sung.

Nếu gọi cùng code trong một context mới chưa có Customer, provider có thể phát SELECT.

### 14.1. First-level cache

Persistence context giữ một managed instance cho một entity identity. Nó có thể làm biến mất những SQL bạn mong sẽ thấy khi kiểm thử “lần thứ hai”, nhưng điều đó không có nghĩa query/fetch plan hoàn toàn khác.

### 14.2. Second-level cache

Nếu provider bật shared cache, dữ liệu có thể được phục vụ từ cache mà không cần round trip DB, ngay cả khi association cần được khởi tạo tại thời điểm truy cập.

Lưu ý:

- “Không có SQL” không đồng nghĩa “không có load/initialization work”.
- Cache hit rate phụ thuộc dữ liệu, policy và invalidation.
- Entity có thể được lấy từ second-level cache nhưng collection chưa có cache entry.
- Query cache khác với entity/collection cache.

### 14.3. Cách test đúng

Để quan sát SQL fetch timing:

1. Tạo fixture xác định.
2. Dùng persistence context **mới**.
3. Xác định cache policy/test setup.
4. Thực hiện query và đánh dấu thời điểm.
5. Quan sát SQL trước/sau khi truy cập field.
6. Lặp lại theo use case, không chỉ theo một entity từng được load trong cùng context.

Không dùng việc test case A đã làm nóng cache để kết luận test case B “không có N+1”.

---

## 15. N+1: thời điểm truy cập trong vòng lặp biến 1 query thành nhiều query

Một trong những tác động nghiêm trọng nhất của LAZY loading xuất hiện khi code duyệt nhiều root entities.

### 15.1. Ví dụ một query ban đầu

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o FROM PurchaseOrder o
    ORDER BY o.id
    """,
    PurchaseOrder.class
).getResultList();
```

Provider có thể chạy một SELECT root.

### 15.2. Một vòng lặp truy cập association

```java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        // xử lý line
    }
}
```

Nếu mỗi `order.lines` ban đầu chưa được tải, provider có thể thực hiện:

```sql
SELECT ... FROM purchase_orders ORDER BY id;  -- 1 query

SELECT ... FROM order_lines WHERE order_id = 101;
SELECT ... FROM order_lines WHERE order_id = 102;
SELECT ... FROM order_lines WHERE order_id = 103;
-- thêm query theo mỗi order cần lazy load
```

Đây là mô hình **N+1**: một query lấy N root entities, rồi có thể thêm khoảng N queries để nạp từng collection.

### 15.3. N+1 ở nested association

Sau khi có lines:

```java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        System.out.println(line.getProduct().getName());
    }
}
```

Có thể xuất hiện thêm nhiều queries cho `Product` chưa loaded.

Với product được chia sẻ giữa nhiều lines, first-level/second-level cache có thể giúp tránh lặp SELECT cho cùng product identity; nhưng nếu mỗi line có product khác nhau, vẫn có nguy cơ query nhiều.

### 15.4. Vì sao lỗi xuất hiện ở service/serializer chứ không ở repository?

Repository chạy query root ở T0. SQL bổ sung lại phát tại T1 khi code gọi getter:

```text
OrderRepository.findRecentOrders()
   |
   +-- SELECT orders (1 query)
   |
   v
OrderService.buildResponse()
   |
   +-- for each order -> getLines()
                          |
                          +-- SELECT lines per order
```

Nếu chỉ profile SQL trong repository method rồi kết luận “query rất nhanh”, bạn có thể bỏ sót toàn bộ chi phí phát sinh ở tầng dùng kết quả.

**Đo theo toàn bộ use case/request**, không chỉ theo một method lấy list.

---

## 16. Giải pháp 1: `JOIN FETCH` khi biết trước cần association

Khi màn hình cần Order cùng danh sách lines:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.id
    """,
    PurchaseOrder.class
).getResultList();
```

`LEFT JOIN FETCH` yêu cầu provider tải `lines` cùng kết quả Order. Sử dụng LEFT thay vì INNER để vẫn giữ order không có line.

### 16.1. `JOIN` khác `JOIN FETCH`

```sql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
```

JOIN thường phục vụ **lọc/kết hợp dữ liệu**, không đảm bảo `o.lines` đã khởi tạo.

```sql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.lines
```

JOIN FETCH yêu cầu **tải association**. Vì là INNER JOIN, các PurchaseOrder không có lines có thể bị loại.

```sql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

LEFT JOIN FETCH giúp giữ cả orders không có lines.

### 16.2. Không dùng INNER FETCH JOIN nếu phải giữ parent trống

Với dữ liệu mẫu:

```text
Order#101 có 2 lines
Order#102 có 0 lines
Order#103 có 1 line
```

`JOIN FETCH o.lines` (inner) không giữ Order#102 trong kết quả join.

`LEFT JOIN FETCH o.lines` giữ Order#102 cùng một collection rỗng.

### 16.3. Tại sao cần chú ý DISTINCT?

Khi join collection, một Order có nhiều lines tạo nhiều **hàng SQL kết hợp**:

```text
Order#101 + Line#1
Order#101 + Line#2
Order#102 + NULL
Order#103 + Line#3
```

`SELECT DISTINCT o` diễn đạt mong muốn danh sách root entities không trùng về mặt JPQL. Tuy nhiên, cách provider loại trùng entity và cách SQL DISTINCT tương tác với các cột child có thể khác nhau; SQL vẫn có thể trả nhiều hàng cho cùng Order để tạo collection.

Không cho rằng `DISTINCT` luôn làm giảm toàn bộ dữ liệu phải truyền về từ DB.

### 16.4. Fetch join không phải “càng nhiều càng tốt”

```sql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines l
LEFT JOIN FETCH l.product
```

Đoạn trên chỉ minh họa ý tưởng fetch nested association; trong **JPQL portable**, fetch join có các hạn chế về alias của đối tượng được fetch, nên không nên sử dụng alias `l` trong một fetch join rồi tiếp tục điều hướng như cú pháp được mọi provider bảo đảm.

Thực tế có thể:

- Query root với `LEFT JOIN FETCH o.lines`.
- Dùng entity graph subgraph để yêu cầu tải `lines.product`.
- Query projections theo dữ liệu thực sự cần.
- Dùng provider-specific HQL extension có kiểm chứng nếu quyết định phụ thuộc Hibernate.

### 16.5. Fetch join và filtering collection

Truy vấn muốn chỉ fetch lines có quantity lớn:

```sql
-- Không coi đây là mẫu JPQL portable để tải collection đầy đủ:
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines l
WHERE l.quantity > 5
```

Ngoài giới hạn alias/predicate của fetch join chuẩn, việc filter child ngay trên fetch join có thể khiến collection được nạp **không đầy đủ**, gây nhầm lẫn giữa “toàn bộ lines” và “lines thỏa điều kiện”.

Nếu cần dữ liệu được lọc trong API, một DTO projection có thể phù hợp hơn:

```sql
SELECT NEW com.example.fetch.OrderLineRow(
    o.id,
    l.id,
    l.quantity
)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity > :minimum
```

`OrderLineRow` là DTO được thiết kế cho projection này; constructor phải khớp types/arguments.

---

## 17. Giải pháp 2: Entity graph chọn dữ liệu cần tải theo use case

Đôi khi cần cùng entity nhưng mỗi màn hình có nhu cầu khác nhau.

- Danh sách orders: chỉ status, date, customer name.
- Chi tiết order: customer, lines, product.
- Báo cáo tài chính: order ID + aggregate totals.

Thay vì đặt tất cả relationships là EAGER, dùng **entity graph** theo use case.

### 17.1. Khai báo graph

```java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomerAndLines",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode("lines")
    }
)
public class PurchaseOrder {
    // Những fields như ví dụ trước.
}
```

Nếu entity đã có `@Entity` và mappings, chỉ thêm `@NamedEntityGraph` trên cùng class; đoạn trên minh họa placement, không yêu cầu khai báo hai class PurchaseOrder.

### 17.2. Áp dụng `fetchgraph` vào `find`

```java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.withCustomerAndLines");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
```

Ý định: khi lấy root, fetch những thuộc tính đã khai báo trong graph; các attributes không được chỉ rõ được xử lý theo semantics của fetch graph.

### 17.3. `fetchgraph` và `loadgraph`

Hai hint chuẩn:

- `jakarta.persistence.fetchgraph`: những attributes trong graph được yêu cầu **EAGER**; attributes không có trong graph được đối xử **LAZY** theo graph semantics (provider vẫn có thể fetch thêm, và có khác biệt triển khai với static EAGER mappings).
- `jakarta.persistence.loadgraph`: những attributes trong graph được yêu cầu **EAGER**; attributes không có trong graph giữ **static/default fetch strategy** của mapping.

Ví dụ:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.loadgraph",
    graph
);

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId, hints);
```

Trong codebase cũ JPA 2.x dùng namespace `javax.persistence.fetchgraph`/`javax.persistence.loadgraph`; chọn hint name theo nền tảng và version thực tế.

### 17.4. Dynamic entity graph

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer", "lines");
```

Có thể kết hợp subgraph cho nested relationship:

```java
Subgraph<OrderLine> linesGraph =
    graph.addSubgraph("lines", OrderLine.class);

linesGraph.addAttributeNodes("product");
```

Với provider hỗ trợ chuẩn tương ứng, graph mô tả:

```text
PurchaseOrder
  +-- customer
  +-- lines
        +-- product
```

**Mục tiêu của graph là yêu cầu những attributes cần loaded**, không bảo đảm provider dùng một SQL JOIN duy nhất. Provider có thể tải bằng JOIN, secondary selects hoặc nhiều bước khác để tuân thủ fetch semantics.

### 17.5. Graph áp dụng khi truy vấn

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.status = :status
    """,
    PurchaseOrder.class
)
.setParameter("status", "PAID")
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
```

Sau khi query, những paths nằm trong graph được kỳ vọng loaded theo graph semantics, dù SQL shape tùy provider.

### 17.6. Entity graph không tự giải quyết mọi vấn đề

Nếu graph chứa collection lớn:

- Có thể vẫn tạo nhiều SQL rows.
- Có thể bị ảnh hưởng bởi pagination.
- Có thể làm quá tải memory.
- Có thể fetch nhiều hơn nhu cầu thực tế.
- Nếu root entity đã managed trước đó, identity-map state và fetch behavior cần được kiểm thử.

Không tạo một “graph toàn bộ domain” rồi dùng cho mọi request.

---

## 18. Giải pháp 3: Projection/DTO cho use case chỉ cần vài trường

Nếu màn hình danh sách chỉ cần:

```text
orderId
status
customerName
```

không nhất thiết trả entity `PurchaseOrder` rồi truy cập `order.getCustomer().getFullName()` trong vòng lặp.

DTO:

```java
package com.example.fetch;

public record OrderSummary(
    Long orderId,
    String status,
    String customerName
) {}
```

JPQL:

```java
List<OrderSummary> summaries = em.createQuery(
    """
    SELECT NEW com.example.fetch.OrderSummary(
        o.id,
        o.status,
        c.fullName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    ORDER BY o.id
    """,
    OrderSummary.class
).getResultList();
```

Với `PurchaseOrder.customer` bắt buộc (`optional=false`, FK NOT NULL), INNER JOIN có thể phù hợp. Nếu quan hệ tùy chọn và cần giữ orders không có customer, dùng LEFT JOIN/nullable DTO field tương ứng.

### 18.1. Vì sao DTO giải quyết một phần câu hỏi fetch timing?

Result trả những scalar values đã select. Code sau query đọc `summary.customerName()` trực tiếp; nó không cần trì hoãn tải một entity Customer.

Lợi ích:

- SQL projection gần với nhu cầu màn hình.
- Không trả graph managed entity ra API.
- Tránh lazy loading ngoài transaction do serializer.
- Dễ phân trang parent rows khi projection đúng grain.
- Giảm nguy cơ vô tình truy cập associations không cần.

### 18.2. DTO không phải cách tránh SQL nếu query vẫn join vô hạn

Nếu projection join nhiều collection, số rows vẫn có thể nhân bội. DTO chỉ kiểm soát **dữ liệu được chọn**, không tự bảo đảm aggregation/pagination đúng.

### 18.3. Chỉ cần số line, dùng aggregate thay vì initialize collection

```java
public record OrderLineCount(Long orderId, Long lineCount) {}
```

```java
List<OrderLineCount> counts = em.createQuery(
    """
    SELECT NEW com.example.fetch.OrderLineCount(
        o.id,
        COUNT(l)
    )
    FROM PurchaseOrder o
    LEFT JOIN o.lines l
    GROUP BY o.id
    ORDER BY o.id
    """,
    OrderLineCount.class
).getResultList();
```

Với order không có line, `COUNT(l)` là 0.

Cách này tránh tải toàn bộ `OrderLine` entities chỉ để gọi `order.getLines().size()`. Nếu có nhiều associations join cùng lúc, phải kiểm tra row multiplication và chọn đúng phép đếm.

---

## 19. Giải pháp 4: batch fetching và subselect fetching

Nếu không thể JOIN FETCH tất cả collections, có thể tối ưu số secondary queries bằng **batch fetching**.

### 19.1. Ý tưởng

Thay vì:

```sql
SELECT ... FROM order_lines WHERE order_id = 101;
SELECT ... FROM order_lines WHERE order_id = 102;
SELECT ... FROM order_lines WHERE order_id = 103;
```

provider có thể gom:

```sql
SELECT ...
FROM order_lines
WHERE order_id IN (101, 102, 103);
```

Mục tiêu: vẫn trì hoãn collection đến khi cần, nhưng lấy nhiều collection theo batch để giảm round trips.

### 19.2. Đó có phải API JPA chuẩn không?

**Chiến lược batch fetch và subselect fetch chi tiết thường là extension của provider**, không phải một annotation `@BatchSize` do Jakarta Persistence chuẩn hóa.

Ví dụ Hibernate:

```java
// Hibernate-specific:
@org.hibernate.annotations.BatchSize(size = 32)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Hoặc cấu hình default batch size của Hibernate tùy phiên bản.

Không mặc định code trên chạy với EclipseLink hoặc mọi JPA provider.

### 19.3. Subselect fetching

Một số provider có thể nạp collections cho nhiều parent bằng truy vấn phụ dựa trên tập parent đã lấy trước. SQL cụ thể, thời điểm kích hoạt và memory footprint khác nhau theo provider.

Với Hibernate, `@Fetch(FetchMode.SUBSELECT)` là một extension có thể liên quan tới trường hợp này.

### 19.4. Chọn giữa JOIN FETCH và batch

| Chiến lược | Phù hợp khi | Rủi ro |
|---|---|---|
| `JOIN FETCH` | Cần association ngay, số child vừa phải. | SQL rows nhân bội, pagination khó. |
| Entity graph | Muốn khai báo fetch theo use case. | Không kiểm soát trực tiếp SQL shape, có thể fetch quá nhiều. |
| Batch fetching | Nhiều root, associations LAZY được truy cập sau. | Provider-specific; vẫn có nhiều queries theo batch. |
| Subselect fetching | Collections của tập roots liên quan. | SQL/memory phụ thuộc provider, có thể tải quá rộng. |
| DTO projection | Chỉ cần vài fields/aggregates. | Không có managed entity graph để thao tác domain tiếp. |

**Đừng tối ưu bằng số queries duy nhất:** một query JOIN trả một triệu rows có thể tệ hơn ba SELECT nhỏ trả đúng dữ liệu cần.

---

## 20. Pagination và thời điểm tải collection

Giả sử API cần **trang 20 đơn**, mỗi đơn kèm lines.

Một ý tưởng:

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

Vấn đề: một order có thể tạo nhiều hàng SQL. Giới hạn SQL rows và giới hạn root entities không tương đương. Một số providers có thể cảnh báo, phân trang trong memory hoặc có cơ chế khác.

### 20.1. Hai bước để phân trang root trước khi fetch collection

**Bước 1 — lấy IDs của trang:**

```java
List<Long> ids = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    ORDER BY o.id
    """,
    Long.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
```

**Bước 2 — fetch dữ liệu của những IDs ấy:**

```java
List<PurchaseOrder> orders;

if (ids.isEmpty()) {
    orders = List.of();
} else {
    orders = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        WHERE o.id IN :ids
        """,
        PurchaseOrder.class
    ).setParameter("ids", ids)
     .getResultList();
}
```

Những điểm phải xem xét:

- `IN :ids` **không bảo đảm giữ thứ tự IDs của trang**. Sắp xếp lại theo danh sách IDs hoặc thêm ORDER BY thích hợp.
- Với trang lớn, DB có giới hạn số parameters/IN-list, cần batch.
- Hai queries có thể nhìn thấy dữ liệu khác nhau nếu transaction khác cập nhật ở giữa; isolation cần đáp ứng nghiệp vụ.
- Nếu cần cả `lines.product`, phải chọn fetch plan bổ sung; chỉ fetch lines không đảm bảo products loaded.
- Query fetch collection vẫn có thể trả nhiều SQL rows nhưng **không còn giới hạn row trực tiếp trước khi phân biệt root IDs**.

### 20.2. Không dùng LAZY làm cái cớ paginate tùy tiện

Nếu chỉ muốn hiển thị trang danh sách, một query DTO cho 20 orders có thể rẻ hơn tải toàn bộ lines. Khi người dùng mở chi tiết, dùng query riêng cho đơn đó.

Đây là cách thiết kế **fetch timing theo tương tác người dùng** chứ không chỉ theo một annotation.

---

## 21. Tác động của thời điểm truy cập đến độ nhất quán dữ liệu

LAZY loading có thể phát SQL **sau** truy vấn root, đôi khi ở một transaction boundary hoặc snapshot khác nếu ứng dụng tổ chức không cẩn thận.

Ví dụ:

```text
T1: SELECT PurchaseOrder#101, status=NEW
T2: Transaction khác INSERT thêm OrderLine cho #101, COMMIT
T3: Ứng dụng duyệt order.getLines()
    -> SELECT lines của #101
```

Nếu isolation của transaction cho phép quan sát thay đổi mới giữa các SELECT, lần truy cập lines ở T3 có thể thấy dữ liệu không thuộc cùng snapshot với root ở T1.

Điều này không phải lỗi riêng của Hibernate; nó liên quan tới **nhiều truy vấn xảy ra ở nhiều thời điểm và transaction isolation**.

### 21.1. Transaction snapshot thay đổi theo mức isolation

Với `READ COMMITTED` ở nhiều RDBMS, mỗi SQL statement có thể nhìn thấy tập dữ liệu đã commit tại thời điểm statement; behavior cụ thể phụ thuộc database.

Với các mức isolation/snapshot khác, khả năng đọc lại có thể nhất quán hơn trong một transaction.

Không tự kết luận từ `fetch = LAZY` rằng mọi dữ liệu của graph được chụp tại cùng lúc với root query.

### 21.2. JOIN FETCH giải quyết toàn bộ consistency không?

Không hoàn toàn.

- JOIN FETCH có thể tải root và association trong một SQL statement, giúp dữ liệu được quan sát trong cùng statement ở database có snapshot semantics tương ứng.
- Nhưng những associations khác chưa fetch vẫn có thể được tải sau.
- Business workflow có thể cần locks/version checks trên nhiều rows.
- Một SQL không tự giải quyết tất cả concurrent updates hoặc phức tạp của aggregate.

Muốn invariant mạnh, cần phối hợp fetch plan với **transaction isolation, locking và domain model**.

### 21.3. Tránh trộn request rendering với DB loading không kiểm soát

Nếu HTML template hoặc JSON serializer âm thầm phát query sau khi service business logic hoàn tất, code có thể không xác định rõ lúc nào data snapshot được lấy.

Ưu tiên tạo DTO trong transaction/service boundary với dữ liệu đúng nhu cầu và trả kết quả bất biến ra tầng presentation.

---

## 22. Truy cập sau transaction trong Spring: hiểu đúng `@Transactional`

Một service:

```java
@Service
public class OrderService {

    private final EntityManager em;

    public OrderService(EntityManager em) {
        this.em = em;
    }

    @Transactional(readOnly = true)
    public OrderSummaryDto getSummary(Long id) {
        PurchaseOrder order =
            em.find(PurchaseOrder.class, id);

        return new OrderSummaryDto(
            order.getId(),
            order.getStatus(),
            order.getCustomer().getFullName()
        );
    }
}
```

Ở đây DTO được tạo **bên trong transaction**. Quan hệ `customer` có thể lazy-load tại thời điểm gọi `getFullName()`, trước khi method hoàn tất.

Nếu service trả entity:

```java
@Transactional(readOnly = true)
public PurchaseOrder getOrder(Long id) {
    return em.find(PurchaseOrder.class, id);
}
```

và controller/serializer sau đó duyệt `order.getLines()`, behavior tùy persistence context có còn mở hay không. Có thể gặp lazy initialization failure hoặc phát SQL ngoài transaction service như mong đợi.

### 22.1. `readOnly = true` không có nghĩa mọi thuộc tính tự tải

`@Transactional(readOnly = true)` là metadata/framework behavior liên quan transaction optimization/intent. Nó **không làm LAZY associations tự biến thành EAGER**, không thay fetch plan và không xác định số SQL.

### 22.2. Open Session In View (OSIV)

Một số ứng dụng Spring/Hibernate sử dụng **Open Session/EntityManager In View**, giữ persistence context mở tới lúc render response.

Lợi ích: serializer/template có thể lazy-load ngay cả sau khi service method kết thúc.

Đánh đổi:

- SQL có thể phát bất ngờ ở web layer.
- Dễ che khuất N+1.
- Transaction/connection behavior khó dự đoán hơn.
- Response latency phụ thuộc số nested associations được truy cập.
- Tầng presentation phụ thuộc persistence behavior.

OSIV không giải quyết bản chất **fetch plan không rõ ràng**. Một API quy mô lớn thường có lợi khi query/DTO trả đúng dữ liệu trước khi render.

### 22.3. Self-invocation không tự tạo transaction mới

Trong Spring proxy-based transaction management, gọi `this.someTransactionalMethod()` từ cùng object có thể không đi qua proxy advice. Nếu bạn nghĩ một đoạn access LAZY đang nằm trong transaction vì method nội bộ có annotation, nhưng thực tế transaction advice không được kích hoạt, behavior có thể khác kỳ vọng.

Thiết kế transaction boundary ở service được gọi qua framework đúng cách và kiểm thử integration theo luồng thực tế.

---

## 23. JSON serialization là một “người truy cập thuộc tính” nguy hiểm

Giả sử REST controller trả entity:

```java
@GetMapping("/orders/{id}")
public PurchaseOrder getOrder(@PathVariable Long id) {
    return orderService.findById(id);
}
```

JSON serializer có thể gọi:

```text
getId()
getStatus()
getCustomer()
getLines()
  -> for each line:
       getProduct()
       getOrder()
       ...
```

Nếu graph hai chiều:

```text
PurchaseOrder.lines -> OrderLine.order -> PurchaseOrder.lines ...
```

có thể gặp:

- N+1 và nhiều lazy SELECT.
- Lazy initialization exception nếu detached.
- Vòng lặp serialization.
- Response quá lớn.
- Lộ dữ liệu nội bộ không intended.
- Timeout khi graph nhiều tầng.

### 23.1. Annotation JSON ignore không đồng nghĩa fetch tuning

Một annotation của thư viện serializer như `@JsonIgnore` có thể ngăn serializer đi vào field cụ thể, nhưng nó không thay đổi semantics JPA hay làm query fetch plan tối ưu cho mọi use case.

Tương tự, việc serializer có module hỗ trợ Hibernate proxy có thể thay behavior lỗi/N+1, nhưng không thay nhu cầu thiết kế response contract.

### 23.2. Tạo DTO rõ dữ liệu được dùng

```java
public record OrderDetailsDto(
    Long id,
    String status,
    String customerName,
    List<LineDto> lines
) {}

public record LineDto(
    Long productId,
    String productName,
    int quantity
) {}
```

Trong service, xác định rõ cần:

```text
PurchaseOrder.id
PurchaseOrder.status
PurchaseOrder.customer.fullName
PurchaseOrder.lines[*].product.id
PurchaseOrder.lines[*].product.name
PurchaseOrder.lines[*].quantity
```

Sau đó query/graph phù hợp và chuyển entity → DTO **trước khi persistence context đóng**, hoặc dùng DTO projection riêng.

Đây là cách đưa thời điểm truy cập thuộc tính từ nơi ẩn (serializer) vào nơi chủ động (service/query).

---

## 24. Dùng `PersistenceUnitUtil.isLoaded` để quan sát trạng thái

JPA cung cấp API portable để kiểm tra loaded state.

```java
import jakarta.persistence.PersistenceUnitUtil;

PersistenceUnitUtil util =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil();
```

Kiểm tra entity:

```java
boolean loadedEntity = util.isLoaded(order);
```

Kiểm tra một thuộc tính:

```java
boolean linesLoaded =
    util.isLoaded(order, "lines");

boolean customerLoaded =
    util.isLoaded(order, "customer");
```

### 24.1. Hai ý nghĩa khác nhau

- `isLoaded(order)`: trạng thái loaded của entity theo semantics JPA.
- `isLoaded(order, "lines")`: thuộc tính **lines** đã được loaded hay chưa.

Một entity có thể có root/basic state loaded nhưng `lines` vẫn chưa loaded.

### 24.2. Ví dụ quan sát trước và sau access

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

PersistenceUnitUtil util =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil();

System.out.println(
    "lines loaded before = " +
    util.isLoaded(order, "lines")
);

// Truy cập collection để lấy dữ liệu.
for (OrderLine line : order.getLines()) {
    System.out.println(line.getQuantity());
}

System.out.println(
    "lines loaded after = " +
    util.isLoaded(order, "lines")
);
```

Với provider đang trì hoãn collection đúng như mapping, trước access có thể là `false` và sau là `true`.

**Nhưng:** nếu graph/fetch/cache đã tải collection sớm, kết quả ban đầu có thể là `true`. Đừng biến ví dụ thành một assertion cứng rằng LAZY **bắt buộc** phải trả `false` trước khi access trên mọi provider.

### 24.3. `isLoaded` không được dùng để đo số SQL

`isLoaded` cho biết trạng thái theo provider, **không trả số SELECT đã phát**. Cũng không chứng minh object graph transitively loaded tới mọi tầng.

Để đo N+1 và query count, dùng SQL logging, JDBC observability hoặc provider statistics.

### 24.4. Cẩn thận với tên thuộc tính

`util.isLoaded(order, "lines")` dùng tên **persistent property/attribute của entity**, không dùng tên cột SQL `order_lines` hay getter name `getLines`.

### 24.5. Hibernate-specific checks

Trong Hibernate, có thể gặp:

```java
org.hibernate.Hibernate.isInitialized(
    order.getLines()
);
```

hoặc:

```java
org.hibernate.Hibernate.initialize(
    order.getLines()
);
```

Đây là API Hibernate-specific, không portable JPA. `Hibernate.initialize` cần session/context thích hợp và có thể truy cập DB. Nếu dự án cam kết JPA portability, ưu tiên thiết kế fetch plan bằng JPQL/entity graph và dùng API chuẩn khi có thể.

---

## 25. Phân biệt “đã load một phần” với “đã có proxy/reference”

Một mô hình thường gặp:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

Customer customer = order.getCustomer();
```

Có ba khả năng đáng nhớ:

1. Customer đã managed trong context → reference có thể trỏ tới entity đã có.
2. Customer chưa loaded nhưng provider tạo proxy/reference theo customer ID.
3. Provider quyết định fetch sớm Customer → entity đã loaded.

Trong trường hợp proxy:

```java
customer.getId();        // Có thể lấy ID từ proxy.
customer.getFullName();  // Có thể kích hoạt SELECT.
```

Nhưng không nên xây logic correctness dựa vào việc `getId()` luôn không query hoặc `getFullName()` luôn query. Bytecode enhancement, inheritance, provider strategy, cache và method implementation có thể thay đổi điều đó.

### 25.1. Proxy không phải entity dữ liệu rỗng

Một proxy/reference là một cách provider đại diện cho entity identity và khả năng lazy initialization. Nó **không có nghĩa** entity thật không tồn tại. Nếu ID không tồn tại, lỗi có thể xuất hiện khi buộc tải state.

### 25.2. `equals`/`hashCode` có thể tác động

Một implementation như:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof PurchaseOrder o)) return false;

    return Objects.equals(customer.getFullName(),
                          o.customer.getFullName());
}
```

là thiết kế rủi ro: equality có thể phát SQL, đụng LAZY association, gây N+1 hoặc lỗi detached.

Với entity, cân nhắc equality theo stable identity phù hợp domain và lifecycle; không đưa collection hay các quan hệ LAZY vào `equals`/`hashCode` một cách máy móc.

---

## 26. Khai báo EAGER có thể tải sớm nhưng vẫn sinh N+1

Ví dụ:

```java
@ManyToOne(fetch = FetchType.EAGER)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Một query:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

Một provider có thể thực hiện:

```sql
SELECT ... FROM purchase_orders;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
```

để đáp ứng yêu cầu EAGER trong một tình huống truy vấn cụ thể.

**Bài học:** `FetchType.EAGER` đảm bảo ý định dữ liệu cần được nạp theo semantics, không đảm bảo **hình dạng SQL tối ưu**.

### 26.1. Tối ưu EAGER vẫn cần query-level plan

Nếu màn hình luôn cần customer name, có thể chủ động:

```sql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
```

với association bắt buộc. Nếu có orders không có customer và cần giữ chúng, cân nhắc `LEFT JOIN FETCH`.

### 26.2. Tại sao nhiều dự án ưu tiên LAZY cho associations?

Vì nó giảm tình huống **một query đơn giản vô tình kéo toàn bộ graph**. Use case nào cần dữ liệu thì thể hiện nhu cầu đó bằng fetch join, entity graph hoặc projection.

Nhưng đây là **nguyên tắc thiết kế phổ biến**, không phải luật rằng mọi relationship phải LAZY bất kể domain. Cần xem hợp đồng sử dụng và provider support, đặc biệt inverse one-to-one.

---

## 27. Quan hệ `@ElementCollection` và thời điểm truy cập

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

Truy cập:

```java
product.getTags().contains("new");
```

có thể cần truy vấn bảng `product_tags`.

Tùy provider có extension tối ưu chứa/size, thao tác `contains` có thể không phải load toàn collection, hoặc có thể load toàn bộ. Không thể suy luận chính xác SQL chỉ từ API Java Collection.

### 27.1. Khi chỉ cần lọc theo tag, dùng JPQL

Thay vì tải hàng nghìn Products rồi:

```java
products.stream()
    .filter(p -> p.getTags().contains("new"))
    .toList();
```

hãy cân nhắc:

```sql
SELECT DISTINCT p
FROM Product p
JOIN p.tags t
WHERE t = :tag
```

Truy vấn thực hiện lọc tại DB, tránh một vòng lặp truy cập collection LAZY của mọi product.

### 27.2. Collection embeddables

`@ElementCollection` có thể chứa `@Embeddable`. Khi collection được nạp, các giá trị embeddable đi kèm; không được tự coi mỗi embeddable là managed entity có khóa chính độc lập.

Nếu giá trị embeddable chứa quan hệ, khả năng fetch nested fields còn phụ thuộc mapping tương ứng.

---

## 28. Fetch plan thay đổi theo đường gọi ứng dụng

Một endpoint:

```text
GET /orders
  -> danh sách gọn
```

có thể chỉ cần:

```text
id, status, orderedAt
```

Một endpoint khác:

```text
GET /orders/101
  -> chi tiết đơn
```

cần:

```text
order.customer.fullName
order.lines[*].product.name
order.lines[*].quantity
```

Hai endpoint cùng dùng entity `PurchaseOrder` nhưng **không nên có một fetch plan cố định tải toàn graph cho cả hai**.

### 28.1. Thiết kế repository theo use case

Ví dụ API:

```java
interface OrderReadRepository {

    List<OrderSummary> findSummaries(int offset, int limit);

    PurchaseOrder findForDetails(Long orderId);

    List<OrderLineCount> countLinesByOrder();
}
```

- `findSummaries` dùng DTO projection.
- `findForDetails` dùng fetch plan phù hợp.
- `countLinesByOrder` dùng aggregate query.

Không chỉ có một method `findAll` rồi để mọi caller tùy ý duyệt object graph sau đó.

### 28.2. “Kế hoạch tải” là hợp đồng giữa repository và caller

Repository phải biết caller sẽ dùng những paths nào để tránh:

- Lỗi detached LAZY.
- N+1 ngoài dự kiến.
- Tải quá nhiều dữ liệu.
- Query phát sinh không kiểm soát từ view/serializer.

Viết rõ nhu cầu đọc trong method name, DTO type hoặc query spec giúp team review nhanh hơn.

---

## 29. Trường hợp nào việc truy cập LAZY không tạo SQL?

Không nên đưa ra kết luận “LAZY = SELECT mới mỗi lần getter”.

Ví dụ không phát SQL mới nếu:

- Association đã được `JOIN FETCH` trong cùng query.
- Entity graph đã yêu cầu tải association.
- Association được truy cập và nạp ở lần trước.
- Related entity đã ở persistence context theo cùng ID.
- Provider phục vụ dữ liệu từ second-level cache.
- Association null và provider xác định được điều đó từ FK/mapping.
- Provider đã fetch sớm dù mapping LAZY.
- Provider tối ưu operation mà không cần truy vấn riêng.
- Dữ liệu association đã được đưa vào parent/collection bởi một plan/provider extension khác.

### 29.1. Không phải mọi LAZY access đều load toàn collection

Ví dụ `getLines().size()` trong một số provider có chế độ extra-lazy có thể dùng `COUNT(*)` để trả kích thước mà chưa nạp mọi OrderLine objects.

Ví dụ `contains` có thể được tối ưu thành câu kiểm tra existence. Những hành vi này **không thuộc bảo đảm chung** của JPA collection API; cần xác nhận trên provider/version và test.

### 29.2. Không phải mọi EAGER access đều tạo SQL tại thời điểm getter

Nếu EAGER requirement đã được xử lý trong root loading, getter chỉ đọc memory.

Điểm phân biệt: **khi nào dữ liệu được nạp** và **vì sao nó được nạp**, không chỉ có từ khóa LAZY/EAGER.

---

## 30. Một bài thực hành quan sát SQL theo từng mốc

Mục tiêu là nhìn thấy sự khác nhau giữa query ban đầu và truy cập association.

### 30.1. Thiết lập dữ liệu

Trong một database test cô lập, tạo Customer, Products và PurchaseOrders theo entity ví dụ.

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer an = new Customer("An");
    Customer binh = new Customer("Bình");

    Product keyboard = new Product(
        "Keyboard", new BigDecimal("900000.00")
    );
    Product mouse = new Product(
        "Mouse", new BigDecimal("300000.00")
    );
    Product monitor = new Product(
        "Monitor", new BigDecimal("3500000.00")
    );

    em.persist(an);
    em.persist(binh);
    em.persist(keyboard);
    em.persist(mouse);
    em.persist(monitor);

    PurchaseOrder first = new PurchaseOrder(
        an, "NEW", LocalDateTime.of(2026, 11, 1, 9, 0)
    );
    first.addLine(keyboard, 1);
    first.addLine(mouse, 2);

    PurchaseOrder second = new PurchaseOrder(
        an, "PAID", LocalDateTime.of(2026, 11, 2, 10, 30)
    );

    PurchaseOrder third = new PurchaseOrder(
        binh, "NEW", LocalDateTime.of(2026, 11, 3, 15, 45)
    );
    third.addLine(monitor, 1);

    // CascadeType.PERSIST của PurchaseOrder.lines
    // persist OrderLine mới cùng order.
    em.persist(first);
    em.persist(second);
    em.persist(third);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
} finally {
    em.close();
}
```

Chú ý: test dùng dữ liệu được tạo mới, nên ID không nhất thiết là 101/102/103 như bảng minh họa; những số đó chỉ là ví dụ giúp đọc SQL.

### 30.2. Mở context mới để tránh identity map đã có

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PersistenceUnitUtil util =
        emf.getPersistenceUnitUtil();

    System.out.println("T0: before root query");

    List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        ORDER BY o.id
        """,
        PurchaseOrder.class
    ).getResultList();

    System.out.println("T1: after root query");

    for (PurchaseOrder order : orders) {
        System.out.println(
            "id=" + order.getId()
            + ", lines loaded="
            + util.isLoaded(order, "lines")
        );
    }

    System.out.println("T2: before accessing lines");

    for (PurchaseOrder order : orders) {
        System.out.println(
            order.getId()
            + " has lines=" + order.getLines().size()
        );
    }

    System.out.println("T3: after accessing lines");

    for (PurchaseOrder order : orders) {
        System.out.println(
            "id=" + order.getId()
            + ", lines loaded="
            + util.isLoaded(order, "lines")
        );
    }

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
} finally {
    em.close();
}
```

Khi quan sát log SQL:

- Ghi nhận câu SQL từ T0 đến T1.
- Ghi nhận câu SQL giữa T1 và T2 (nếu có; `isLoaded` không phải thao tác ép fetch).
- Ghi nhận câu SQL từ T2 đến T3.
- Ghi nhận loaded state trước/sau.

Không đặt kỳ vọng cứng là **chính xác 1 + N SQL** vì provider có thể batch, cache, dùng extra-lazy count, fetch sớm hoặc kế hoạch khác.

### 30.3. Chạy lần hai với `LEFT JOIN FETCH`

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.id
    """,
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    // Lines được query yêu cầu fetch.
    System.out.println(order.getLines().size());
}
```

So sánh SQL log và số rows được trả giữa hai phương án. Nếu đo trong cùng EntityManager ngay sau lần thử trước, dữ liệu có thể đã loaded, khiến so sánh không công bằng. Dùng context mới/cấu hình cache thích hợp cho mỗi lượt.

---

## 31. Viết integration test với `isLoaded`

Một test cơ bản kiểm tra nhu cầu fetch tường minh:

```java
@Test
void fetchJoinMakesLinesAvailableAfterDetach() {
    Long id = knownOrderId;
    PurchaseOrder order;

    EntityManager em = emf.createEntityManager();

    try {
        order = em.createQuery(
            """
            SELECT o
            FROM PurchaseOrder o
            LEFT JOIN FETCH o.lines
            WHERE o.id = :id
            """,
            PurchaseOrder.class
        )
        .setParameter("id", id)
        .getSingleResult();

        assertTrue(
            emf.getPersistenceUnitUtil()
                .isLoaded(order, "lines")
        );
    } finally {
        em.close();
    }

    // Collection được yêu cầu fetch trước khi detach.
    assertNotNull(order.getLines());
    assertFalse(order.getLines().isEmpty());
}
```

`knownOrderId` là fixture ID của order có ít nhất một line; nếu fixture có zero lines, assertion `assertFalse(isEmpty())` sẽ không phù hợp.

### 31.1. Test LAZY nên tránh áp đặt điều provider không hứa

Một test:

```java
assertFalse(util.isLoaded(order, "customer"));
```

ngay sau `em.find` có thể thất bại trên provider được phép fetch association sớm dù khai báo LAZY.

Nếu mục tiêu test là **đúng semantics nghiệp vụ** và không bị lỗi ngoài transaction, nên kiểm tra attributes cần dùng được loaded theo fetch plan hoặc DTO trả đủ dữ liệu.

Nếu mục tiêu test là **hiệu năng trên provider cụ thể**, có thể thêm assertions query count/loaded state theo bản provider đã chọn, nhưng không mô tả chúng như luật bắt buộc của JPA chuẩn.

### 31.2. Test số SQL là integration test, không phải unit test đơn thuần

Một unit test mock `EntityManager` không thể chứng minh thời điểm JDBC thực thi SQL.

Để kiểm chứng thực tế cần:

- JPA provider thật.
- Database test phù hợp.
- Fixture xác định.
- SQL logging hoặc query counter.
- Kiểm soát cache.
- Transaction/context boundaries chính xác.

---

## 32. Theo dõi số SQL bằng provider instrumentation

### 32.1. SQL logging

Bật SQL logging qua cấu hình provider trong môi trường development/test để quan sát:

```text
T0  SELECT orders
T1  order.getId()
T2  SELECT order_lines WHERE order_id = ?
T3  SELECT products WHERE id = ?
```

Không dựa vào log SQL trong production ở mức quá chi tiết nếu nó gây lộ dữ liệu hoặc tạo overhead lớn.

### 32.2. Hibernate Statistics (extension)

Trong dự án Hibernate, có thể dùng statistics:

```java
org.hibernate.SessionFactory sessionFactory =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics statistics =
    sessionFactory.getStatistics();

statistics.clear();

long before =
    statistics.getPrepareStatementCount();

// Thực thi use case cần đo.

long executedStatements =
    statistics.getPrepareStatementCount() - before;
```

Để statistics hoạt động đúng, cần cấu hình bật metrics phù hợp (ví dụ `hibernate.generate_statistics`). Các counter có thể thuộc phạm vi SessionFactory, nên test chạy song song có thể ảnh hưởng kết quả.

Đây là **Hibernate-specific**, không phải API JPA portable.

### 32.3. JDBC-level metrics

Có thể đo round trips bằng proxy datasource hoặc instrumentation/tracing JDBC trong integration tests.

Ưu điểm: quan sát SQL thực tế, kể cả query phát sinh từ serializer hoặc lazy collections, thay vì chỉ xem một JPQL string ban đầu.

### 32.4. Số SQL ít không phải mục tiêu cuối

Ngoài statement count, còn cần quan sát:

- SQL execution time.
- Số rows và bytes trả về.
- Kích thước entity graph.
- Memory và garbage collection.
- Database lock/connection usage.
- Cache hit/miss.
- Tổng request latency.

Một JOIN FETCH khổng lồ có thể chỉ phát một SQL nhưng vẫn chậm.

---

## 33. Cách xử lý lỗi lazy initialization đúng tầng

Khi gặp:

```text
could not initialize proxy - no Session
```

đừng chỉ sửa nhanh bằng cách đổi:

```java
@OneToMany(fetch = FetchType.EAGER)
```

vì có thể biến mọi query load parent thành tải collection lớn.

### 33.1. Hỏi use case cần trường nào

Nếu response chỉ cần `customerName`, dùng query DTO có join `Customer`.

Nếu response cần `lines`, dùng fetch join hoặc entity graph cho query chi tiết.

Nếu response cần nested `lines.product.name`, khai báo fetch path hoặc DTO thích hợp cho Product.

### 33.2. Giữ việc mapping DTO trong transaction có chủ đích

```java
@Transactional(readOnly = true)
public OrderDetailsDto getDetails(Long id) {
    PurchaseOrder order = repository.findForDetails(id);
    return mapper.toDto(order);
}
```

`findForDetails` phải được thiết kế để trả dữ liệu cần cho mapper, không để mapper vô tình gây N+1.

### 33.3. Không dùng “bật session mọi nơi” làm giải pháp mặc định

Các kỹ thuật mở session trong view, mở temporary session hoặc cho phép lazy loading ngoài transaction có thể khiến lỗi biến mất nhưng chi phí/truy vấn ẩn vẫn tồn tại.

Chúng có thể có use case phù hợp, nhưng nên hiểu rõ consistency, connection use và layering trước khi bật.

---

## 34. Những lỗi thường gặp khi đánh giá thời điểm tải dữ liệu

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `findAll()` nhanh nhưng API rất chậm | Serializer/service lần đầu duyệt LAZY associations. | Đo toàn request, dùng DTO/query fetch plan theo use case. |
| `getLines().size()` sinh SQL | Collection chưa loaded; size cần dữ liệu. | Aggregate query nếu chỉ cần count; fetch khi cần toàn collection. |
| `getCustomer().getName()` sinh SQL | To-one LAZY/proxy chưa initialized. | DTO JOIN, fetch join hoặc graph khi caller cần name. |
| Không thấy SQL khi truy cập LAZY | Association đã loaded/cache hoặc provider fetch sớm. | Kiểm tra context/cache/query plan; đừng coi đó là sai. |
| `@ManyToOne` tự tải Customer dù chưa gọi getter | Default EAGER. | Đánh dấu LAZY khi phù hợp và verify provider. |
| `@OneToOne(fetch=LAZY)` vẫn query sớm | Inverse side/optional null detection/enhancement hạn chế. | Đánh giá mapping, enhancement, DTO và provider behavior. |
| `@Basic(fetch=LAZY)` vẫn SELECT LOB | Provider chưa/defer basic lazy không được thực hiện. | Bytecode enhancement, tách entity hoặc projection. |
| `@PostLoad` làm query tăng nhiều | Callback chạm vào LAZY association. | Tránh traversing object graph trong lifecycle callback. |
| `toString()` làm chậm logging | Method đọc collection hoặc nested properties. | Chỉ log ID/basic fields. |
| JSON trả entity gây N+1 | Serializer gọi getters theo graph. | DTO response, fetch plan và giới hạn depth. |
| JSON serialize vòng lặp | Bidirectional associations. | DTO, serializer policies; không trả toàn graph. |
| `LazyInitializationException` sau controller | Context đóng trước khi access LAZY. | Fetch/projection trong service boundary. |
| Trong cùng `EntityManager`, `find` lần hai không query | First-level cache trả managed instance. | Đo bằng context mới nếu cần. |
| Test `LAZY` đôi khi loaded = true | LAZY là hint; provider/cache/fetch graph. | Không assert false portable, kiểm thử semantics cần bảo đảm. |
| `JOIN` không tránh N+1 | JOIN thường không yêu cầu initialization. | `JOIN FETCH`/entity graph/DTO. |
| `JOIN FETCH` không lấy order không có line | Dùng INNER fetch join. | Dùng `LEFT JOIN FETCH`. |
| Page 20 orders chỉ có vài root | Collection fetch join nhân SQL rows trước pagination. | Phân trang IDs rồi fetch. |
| Query fetch nhiều collections trả quá nhiều rows | Cartesian multiplication giữa collections. | Fetch từng phần, batch/DTO. |
| `EAGER` nhưng vẫn N+1 | Provider dùng secondary selects để đáp ứng EAGER. | Query-level fetch plan/DTO. |
| Truy cập lại association vẫn phát SQL trên context mới | First-level cache chỉ sống trong context cũ. | Hiểu boundaries, không giả định cache toàn hệ thống. |
| Association loaded nhưng child.product chưa loaded | Fetch chỉ một cấp trong graph. | Xác định nested paths cần thiết. |
| `getReference` không tránh SELECT | Truy cập non-ID state hoặc provider kiểm tra sớm. | Không dùng getReference như cam kết zero queries. |
| Sau `em.clear()` không load được LAZY | Entity đã detached. | Nạp trước khi detach hoặc query lại. |
| `merge` không “mở khóa” toàn LAZY graph | Merge state không phải fetch-all. | Query theo use case. |
| Count lines bằng Java rất tốn kém | Load nhiều collections chỉ để tính size. | `COUNT` + `GROUP BY`/projection. |
| N+1 không lộ trong test | Fixture ít dữ liệu, cache đã warm. | Nhiều roots, context mới, đo query count. |
| Một request thấy dữ liệu root và lines ở thời điểm khác | LAZY SQL chạy sau; isolation cho phép thay đổi. | Transaction/snapshot policy phù hợp. |
| `@Transactional(readOnly=true)` không giải quyết N+1 | Transaction mode không thay fetch plan. | Query-level fetch planning. |
| Chỉ tối ưu xuống một SQL nhưng chậm hơn | JOIN rows quá lớn, memory cao. | Đo rows/latency; batch fetch hoặc DTO. |

---

## 35. Quy trình thiết kế fetch plan từ nhu cầu truy cập thuộc tính

Thay vì bắt đầu bằng việc sửa annotation EAGER/LAZY, hãy thực hiện theo thứ tự.

### Bước 1 — Liệt kê những thuộc tính caller thật sự dùng

Ví dụ màn hình Order detail:

```text
o.id
o.status
o.orderedAt
o.customer.fullName
o.lines[*].quantity
o.lines[*].product.name
```

Đừng dùng mô tả mơ hồ “cần order và các thứ liên quan”.

### Bước 2 — Xác định lúc nào caller truy cập

- Ngay trong repository?
- Trong service mapper?
- Trong controller?
- Trong JSON serializer?
- Sau khi context đóng?
- Trong vòng lặp hàng nghìn entities?
- Trong logger/toString?

Tác động tới nơi SQL có thể chạy.

### Bước 3 — Chọn kết quả cần trả

- **DTO** nếu chỉ đọc.
- **Entity** nếu cần managed lifecycle/domain method.
- **Aggregate** nếu chỉ cần count/sum.
- **Paged root IDs** nếu kết quả là trang danh sách.

### Bước 4 — Chọn công cụ fetch

- `JOIN FETCH` nếu association cần và kích thước graph phù hợp.
- Entity graph nếu cần reuse fetch paths theo use case.
- Batch/subselect fetch nếu lazy associations được truy cập theo nhóm và provider hỗ trợ.
- Query projection nếu cần vài trường.
- Query theo bước nếu cần pagination + collection.

### Bước 5 — Chỉ định transaction/context boundary

Không để thành công của request phụ thuộc ngẫu nhiên vào việc serializer còn session mở hay không.

### Bước 6 — Đo SQL và rows

Đo tại:

```text
root query
  -> service mapping
  -> nested properties
  -> serialization
```

Không chỉ đo phương thức repository.

### Bước 7 — Kiểm thử dữ liệu không đồng đều

Fixture nên có:

- Order không có line.
- Order chỉ có một line.
- Order có nhiều lines.
- Nhiều orders dùng chung Product.
- Nhiều orders cùng Customer.
- Quan hệ tùy chọn null (ở mô hình có optional association).
- Trang dữ liệu có root sở hữu nhiều children.

Bằng cách đó, N+1, duplicate roots, LEFT/INNER fetch differences và lỗi detached dễ xuất hiện hơn.

---

## 36. Bài tập thực hành có lời giải

### Bài 1 — Truy cập basic field

**Đề:** truy vấn `SELECT o FROM PurchaseOrder o`, sau đó gọi `o.getStatus()`. Nếu `status` là basic field EAGER đã nạp, có bắt buộc SELECT mới không?

**Lời giải:** Không. Thông thường getter đọc state sẵn có. Nhưng code instrumentation vẫn cần phân biệt SQL root query từ trước và bất kỳ provider fetch phát sinh khác.

### Bài 2 — Tại sao `getLines().size()` có thể phát SQL?

**Lời giải:** Vì size phụ thuộc collection chưa loaded. Provider có thể tải collection hoặc dùng một COUNT optimization riêng. Không thể kết luận một SQL shape duy nhất chỉ từ JPA annotation.

### Bài 3 — Hai orders không có line bị mất sau query

**Query:**

```sql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.lines
```

**Lời giải:** INNER FETCH JOIN chỉ giữ orders có join match; dùng `LEFT JOIN FETCH` nếu cần cả orders có collection rỗng.

### Bài 4 — Service trả entity, controller đọc lines sau khi context đóng

**Lời giải:** Có nguy cơ lazy initialization failure. Query/fetch dữ liệu cần trong service boundary và map sang DTO, hoặc quản lý context/transaction phù hợp; không chữa mặc định bằng EAGER mọi relations.

### Bài 5 — Chỉ cần tên customer cho 500 orders

**Lời giải:** Dùng projection:

```sql
SELECT NEW com.example.fetch.OrderSummary(
    o.id, o.status, c.fullName
)
FROM PurchaseOrder o
JOIN o.customer c
```

Tránh duyệt 500 orders rồi lazy-load customer name ở Java nếu không cần entity graph.

### Bài 6 — Chỉ cần số line của mỗi order

**Lời giải:**

```sql
SELECT o.id, COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
GROUP BY o.id
```

Với order không có line, `COUNT(l)` trả 0. Nếu chỉ cần count, không cần khởi tạo toàn bộ collection.

### Bài 7 — Đã JOIN nhưng collection vẫn LAZY

**Query:**

```sql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity > 2
```

**Lời giải:** JOIN thường dùng để lọc, không phải fetch declaration. Muốn fetch collection cần query-level fetch plan, nhưng không tùy tiện filter JOIN FETCH gây partial collection.

### Bài 8 — EAGER to-one vẫn nhiều SQL

**Lời giải:** EAGER yêu cầu nạp association, không chỉ định số JOIN SQL. Provider có thể dùng secondary queries; dùng fetch join/graph/projection khi use case cần SQL shape tốt hơn.

### Bài 9 — `@Basic(fetch=LAZY)` của LOB không hoạt động

**Lời giải:** LAZY basic field là hint và có thể cần bytecode enhancement. Nếu bắt buộc không đọc LOB trong list view, dùng scalar/DTO projection hoặc tách LOB thành entity/bảng riêng.

### Bài 10 — Cùng code getter chạy nhanh trong test, chậm ở production

**Lời giải:** Test có ít data và warm cache, còn production có nhiều roots và cold cache. Đo query count/rows theo use case với context mới và fixture đủ lớn.

### Bài 11 — Hai requests cùng order nhưng SQL khác nhau

**Lời giải:** Một request đã fetch association bằng entity graph hoặc có cache entry, request kia chưa; hoặc transaction/context/provider plan khác. Không chỉ xem entity annotation, phải xem **query và môi trường truy cập**.

### Bài 12 — `@PostLoad` của root làm nạp collection

**Lời giải:** Callback của root có thể truy cập LAZY field và kích hoạt SQL. Callback không phải nơi phù hợp để duyệt mọi relationships nếu muốn điều khiển fetch plan tường minh.

### Bài 13 — Muốn phân trang orders kèm lines

**Lời giải:** Chọn page IDs trước; sau đó fetch lines cho page roots. Không phân trang trực tiếp collection fetch join một cách máy móc.

### Bài 14 — Một order đã nạp lines, có chắc `product.name` đọc được sau detach?

**Lời giải:** Không. `lines` loaded chỉ nói collection đã nạp; `line.product` có thể vẫn LAZY. Cần fetch nested path hoặc DTO.

### Bài 15 — Có thể dùng `PersistenceUnitUtil.isLoaded` để chứng minh không có SQL?

**Lời giải:** Không. Nó quan sát loaded state. Dữ liệu có thể được nạp từ cache mà không SQL, hoặc đã được nạp bởi query trước đó. Để đo SQL dùng instrumentation.

### Bài 16 — Truy cập LAZY ở thời điểm khác nhau có thể thấy dữ liệu khác không?

**Lời giải:** Có thể, nếu các SELECT xảy ra khác thời điểm và transaction isolation cho phép nhìn thấy commits mới. Fetch plan và transaction consistency cần được thiết kế cùng nhau.

---

## 37. Câu hỏi tự kiểm tra

**1. LAZY có nghĩa mọi association getter luôn phát SELECT riêng?**

Không. Getter có thể trả wrapper/reference, dữ liệu có thể đã loaded/cached, hoặc provider dùng chiến lược khác.

**2. EAGER có nghĩa một câu `JOIN` SQL?**

Không. Provider có thể dùng secondary selects.

**3. `@ManyToOne` mặc định gì?**

EAGER.

**4. `@OneToMany` mặc định gì?**

LAZY.

**5. `@Basic(fetch=LAZY)` có bảo đảm không đọc LOB trong SELECT đầu tiên không?**

Không tuyệt đối; LAZY basic là hint, phụ thuộc provider/enhancement.

**6. Vì sao một vòng lặp `getLines()` gây N+1?**

Mỗi root có LAZY collection chưa loaded có thể kích hoạt SELECT riêng khi lần đầu sử dụng.

**7. `JOIN o.lines` và `JOIN FETCH o.lines` khác gì?**

JOIN tạo kết hợp để lọc/projection; JOIN FETCH yêu cầu nạp association.

**8. Nếu phải giữ orders chưa có lines, chọn loại fetch join nào?**

LEFT JOIN FETCH.

**9. Vì sao không JOIN FETCH tất cả collection?**

Có thể nhân bội SQL rows, khó pagination, tốn memory và tải quá dữ liệu cần.

**10. Khi nào DTO là giải pháp fetch timing đơn giản nhất?**

Khi caller chỉ cần vài scalar fields và không cần managed entity graph.

**11. `em.close()` có làm dữ liệu đã loaded biến mất khỏi object Java không?**

Không. Dữ liệu đã nạp có thể còn trong object; nhưng phần chưa loaded không thể mặc nhiên fetch qua context đã đóng.

**12. Tại sao detached order đã có lines vẫn có thể lỗi khi đọc product name?**

Nested product association của từng line có thể chưa loaded.

**13. `getReference()` có luôn không phát SQL?**

Không có bảo đảm tuyệt đối về thời điểm tải/kiểm tra tồn tại.

**14. `@PostLoad` có nghĩa mọi associations loaded?**

Không. Nó là lifecycle callback của entity load, không phải sự kiện toàn graph đã nạp.

**15. `PersistenceUnitUtil.isLoaded(order,"lines")` kiểm tra điều gì?**

Trạng thái loaded của attribute `lines` theo JPA/provider.

**16. Có thể dùng `isLoaded` để đếm SQL?**

Không.

**17. Khi nào `refresh` hữu ích?**

Khi cần tải lại state của một managed entity; nhưng có thể ghi đè pending local changes và chịu fetch/transaction semantics riêng.

**18. `clear` có làm managed entities detached không?**

Có. Không dùng tùy tiện khi còn unflushed changes.

**19. Spring `@Transactional(readOnly=true)` có tự fetch LAZY collections không?**

Không.

**20. OSIV có tự giải quyết N+1 không?**

Không. Nó có thể để lazy SQL chạy ở view layer và che giấu vấn đề.

**21. Nếu chỉ đếm số child, nên initialize collection hay dùng aggregate?**

Thường dùng query `COUNT` khi chỉ cần số lượng, trừ khi collection đã cần nạp cho mục đích khác và chi phí đã chấp nhận.

**22. First-level cache thuộc scope nào?**

Persistence context/EntityManager, không phải toàn ứng dụng.

**23. LAZY loading ảnh hưởng snapshot consistency thế nào?**

Association có thể được nạp bằng một SELECT sau root query, và isolation quyết định dữ liệu nào nhìn thấy.

**24. Một query JOIN FETCH có đảm bảo hoàn toàn graph không?**

Không. Nó chỉ yêu cầu các paths được fetch theo query; nested associations khác vẫn có thể LAZY.

**25. Vì sao nên đo SQL ở cả serializer?**

Vì serializer có thể truy cập getters lần đầu và gây thêm queries/lỗi detached.

---

## 38. Tổng kết: truy cập thuộc tính là một phần của kế hoạch tải

Trong JPA, việc một entity đã tồn tại dưới dạng Java object **không bảo đảm mọi dữ liệu liên quan đã được tải**.

Cách ứng dụng truy cập thuộc tính sau khi query quyết định phần lớn thời điểm LAZY associations được khởi tạo:

```text
Query root
   |
   +-- basic fields cần thiết     -> thường loaded
   |
   +-- to-one LAZY               -> có thể là proxy/reference
   |
   +-- collections LAZY           -> có thể chưa initialized
   |
   +-- getCustomer().getName()    -> có thể load Customer
   |
   +-- getLines().iterator()      -> có thể load Lines
   |
   +-- line.getProduct().getName()-> có thể load Product
```

### Các nguyên tắc cần nhớ

1. **Fetch mapping và fetch timing khác nhau.** `LAZY` thường trì hoãn tải đến khi cần, nhưng là hint trong những trường hợp theo đặc tả; `EAGER` không hứa số SQL tối ưu.
2. **Thời điểm truy cập thuộc tính nằm ở bất kỳ tầng nào gọi getter**: service, mapper, logger, serializer, callback hay debugger.
3. **Persistence context mở và trạng thái loaded quyết định có thể tải thêm hay không.** Entity detached với LAZY association chưa nạp có thể gây lỗi.
4. **N+1 thường xuất hiện khi duyệt nhiều root entities rồi chạm vào association chưa tải.** Đo toàn use case, không chỉ root query.
5. **JOIN FETCH/entity graph/projection là công cụ đặt rõ nhu cầu dữ liệu.** Chọn theo use case; không tăng EAGER toàn bộ quan hệ một cách máy móc.
6. **Tải một collection không đồng nghĩa tải nested associations**, nên phải nêu rõ paths cần cho response.
7. **Fetch nhiều collection và phân trang cần cẩn thận** vì JOIN làm nhân bội SQL rows; có thể phân trang root IDs trước.
8. **Cache làm thay đổi việc có phát SQL hay không**, nhưng không thay thế việc hiểu loaded state và fetch plan.
9. **LAZY SELECT xảy ra muộn có thể ảnh hưởng consistency**, vì đó có thể là một database read tại thời điểm khác với root query.
10. **Thiết kế API/repository theo dữ liệu caller thật sự truy cập** giúp loại bỏ phần lớn SQL ẩn và lỗi detached.

Câu hỏi nên dùng khi review một màn hình:

> **Caller sẽ đọc những attribute paths nào, đọc ở thời điểm nào, và query có bảo đảm dữ liệu cần thiết được nạp trước khi persistence context không còn sẵn sàng hay không?**

Nếu trả lời được ba vế này, bạn có thể chủ động lựa chọn kế hoạch tải, dự đoán chi phí SQL và tránh cả **N+1** lẫn **LazyInitializationException** mà không cần biến mọi association thành EAGER.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence 3.1 — toàn văn đặc tả](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Jakarta Persistence 3.2 — toàn văn đặc tả](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Persistence API — `FetchType`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/fetchtype)
- [Jakarta Persistence API — `PersistenceUnitUtil`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/persistenceunitutil)
- [Jakarta Persistence API — `EntityGraph`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitygraph)
- [Jakarta Persistence API — `EntityManager`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Hibernate ORM User Guide — fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
