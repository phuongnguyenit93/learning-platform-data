# Xử lý quan hệ tới entity mới chưa được lưu

## 1. Tình huống: entity A tham chiếu entity B chưa được lưu

Trong ứng dụng dùng Jakarta Persistence (JPA), các entity thường liên kết với nhau qua `@ManyToOne`, `@OneToOne`, `@OneToMany` hoặc `@ManyToMany`. Một tình huống thường gặp là chương trình tạo **hai object mới** bằng `new`, nối chúng với nhau trong bộ nhớ, nhưng chỉ gọi `EntityManager.persist()` cho **một** object.

Ví dụ, một đơn hàng mới tham chiếu một khách hàng mới:

```java
Customer customer = new Customer("Mai Nguyen");
PurchaseOrder order = new PurchaseOrder(customer);

// Chỉ yêu cầu JPA lưu Order:
entityManager.persist(order);
```

Nếu `PurchaseOrder.customer` là quan hệ `@ManyToOne` **không khai báo cascade `PERSIST`**, JPA không mặc nhiên lưu `Customer`. Đến lúc ORM cần ghi khóa ngoại, nó có thể gặp một đối tượng **transient/new** chưa có hàng tương ứng và chưa được quản lý. Kết quả có thể là ngoại lệ liên quan “unsaved transient instance”, lỗi ràng buộc khóa ngoại hoặc lỗi đồng bộ khác, tùy mapping, provider và thời điểm flush.

**Điểm cốt lõi:** tạo một object Java và gán nó vào thuộc tính quan hệ **không đồng nghĩa** object đó đã được persist.

```text
Bộ nhớ Java                                 Database
─────────────────────────                   ──────────────────────
new PurchaseOrder                              purchase_orders
    customer ──────────> new Customer           customers
                          (chưa persist)

em.persist(order), không cascade PERSIST
          |
          v
Order có thể được quản lý
Customer vẫn NEW (chưa managed)
          |
          v
Khi đồng bộ FK: thiếu bản ghi/ID hợp lệ cho Customer
```

Để xử lý đúng, phải biết **vòng đời của từng entity**, **phía sở hữu quan hệ** và **chính sách lan truyền thao tác persistence**. Bài học tập trung vào cách xử lý quan hệ trỏ tới entity mới chưa được lưu, đặc biệt khi kết hợp entity mới với entity đã tồn tại trong cơ sở dữ liệu.

## 2. Phân biệt ba loại đối tượng trước khi xử lý quan hệ

Trước khi quyết định gọi `persist`, `merge` hay `find`, cần xác định đối tượng đầu cuối của quan hệ thực sự ở trạng thái nào.

| Trạng thái | Cách xuất hiện phổ biến | Có đang được EntityManager hiện tại theo dõi? | Điều cần nhớ |
|---|---|---|---|
| **New/transient** | `new Customer(...)` | Không | Chưa được đưa vào persistence context; không tự được INSERT chỉ vì bị tham chiếu |
| **Managed** | `em.find(...)`, `em.persist(newEntity)` | Có | Provider theo dõi thay đổi; có thể sử dụng làm target của association trong cùng context |
| **Detached** | Được tải ở context cũ, sau `detach`/`clear`/`close` | Không | Có thể đại diện hàng đã tồn tại, nhưng object không đang managed |
| **Removed** | `em.remove(managedEntity)` | Không ở trạng thái managed bình thường | Đang được đánh dấu xóa; tham chiếu mới đến nó có thể không hợp lệ |

Một object có ID khác null **chưa đủ** để suy ra nó là managed hay thậm chí đã tồn tại trong database. Ngược lại, một entity mới dùng UUID tự gán có thể đã có giá trị ID trước khi persist nhưng vẫn là transient.

### 2.1. Kiểm tra managed state bằng `contains`

```java
Customer customer = new Customer("Mai Nguyen");

System.out.println(em.contains(customer)); // false.

em.persist(customer);

System.out.println(em.contains(customer)); // true.
```

`EntityManager.contains(entity)` kiểm tra **chính instance đó** đang được quản lý trong persistence context hiện tại hay không. Nó **không** kiểm tra hàng database có tồn tại hoặc một entity khác có cùng ID hay không.

`contains=false` có thể là new, detached, removed hoặc managed trong context khác. Vì vậy, không được dùng quy tắc đơn giản “nếu !contains thì persist” khi dữ liệu có thể là detached.

### 2.2. Tại sao quan hệ tới transient entity là vấn đề?

Trong cơ sở dữ liệu quan hệ, một association thường tương ứng với **foreign key** hoặc **join table**. Để lưu `Order.customer`, database cần một giá trị khóa ngoại hợp lệ:

```text
customers
+----+--------------+
| id | full_name    |
+----+--------------+
| 10 | Mai Nguyen   |
+----+--------------+

purchase_orders
+----+-------------+
| id | customer_id |
+----+-------------+
| 42 |          10 |------> customers.id
+----+-------------+
```

Nếu `Customer` chưa được persist và ID do database sinh, tại lúc dựng graph:

```java
Customer customer = new Customer("Mai Nguyen");
System.out.println(customer.getId()); // null với generated Long ID.
```

Không có một `customer_id` đã được xác lập để ORM điền vào hàng order. JPA cần hoặc **persist Customer trước/đồng thời theo một kế hoạch phù hợp**, hoặc **dùng một Customer managed đã tồn tại**, hoặc thay đổi mô hình để quan hệ có thể tạm thời không có target.

## 3. Một ví dụ lỗi điển hình với `@ManyToOne`

Xét hai entity sau.

**`Customer.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {
    }

    public Customer(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng không hợp lệ");
        }
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }
}
```

**`PurchaseOrder.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.Entity;
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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        if (customer == null) {
            throw new IllegalArgumentException("Cần có khách hàng");
        }
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

Schema PostgreSQL minh họa:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
```

### 3.1. Code chỉ persist Order

```java
Customer customer = new Customer("Mai Nguyen"); // transient
PurchaseOrder order = new PurchaseOrder(customer); // transient

em.getTransaction().begin();

em.persist(order); // Order được yêu cầu persist.

em.flush();         // Tình huống thiếu Customer rất dễ lộ ra ở đây.
em.getTransaction().commit();
```

Không có `cascade=PERSIST` trên `PurchaseOrder.customer`, cũng không có `em.persist(customer)`. Vì vậy, việc gọi `em.persist(order)` **không được hiểu là yêu cầu JPA tạo cả khách hàng**.

Trong Hibernate, một biến thể lỗi thường được mô tả bằng thông điệp kiểu:

```text
object references an unsaved transient instance
save the transient instance before flushing
```

Provider có thể dùng loại exception/thông báo khác, hoặc phát hiện lỗi ngay ở `persist` thay vì đợi `flush`. Với khóa ngoại `NOT NULL`, database cũng có thể từ chối câu INSERT không có FK hợp lệ. Không nên phụ thuộc một tên exception Hibernate cụ thể khi viết logic JPA portable.

### 3.2. Vì sao lỗi có thể xuất hiện lúc flush?

`persist` trước hết thay đổi **vòng đời JPA**: entity từ new thành managed. ORM có thể chưa gửi SQL ngay ở dòng gọi phương thức. Khi `flush` hoặc transaction commit, provider mới cần đồng bộ object graph thành `INSERT`/`UPDATE` và phải có khóa ngoại hợp lệ.

Với `GenerationType.IDENTITY`, ORM thường cần INSERT để nhận ID từ database, nên một số thao tác có thể xảy ra sớm hơn. Với `SEQUENCE`, ORM thường có thể lấy ID trước INSERT. **Không được kết luận mọi provider sẽ báo lỗi tại cùng một điểm.**

```text
new Customer + new Order
          |
    em.persist(Order)
          |
          v
Persistence context nhận Order
          |
          +--- có cascade PERSIST tới Customer? --- Có ---> Persist Customer
          |                                           |
          Không                                       |
          |                                           |
          v                                           v
Khi flush cần customer_id                       Có thể xác lập FK
          |
          v
Lỗi transient reference/constraint nếu không có target hợp lệ
```

Trong ví dụ này, cách sửa nên dựa trên **ý nghĩa nghiệp vụ của Customer**, không phải chỉ dựa trên cách tránh exception.

## 4. Giải pháp 1: persist entity đích một cách tường minh

Nếu service có trách nhiệm **tạo mới cả Customer lẫn PurchaseOrder**, có thể quản lý hai thao tác persistence rõ ràng:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    Customer customer = new Customer("Mai Nguyen");
    em.persist(customer);

    PurchaseOrder order = new PurchaseOrder(customer);
    em.persist(order);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đoạn mã minh họa Java SE với `EntityManager` được cấu hình transaction `RESOURCE_LOCAL`. Để chạy cần import `jakarta.persistence.EntityTransaction` và một `EntityManager em` đang mở. Trong Jakarta EE hoặc Spring, transaction có thể do container/framework quản lý.

Giải thích thứ tự logic:

1. Tạo Customer transient.
2. Gọi `persist(customer)`, khiến Customer trở thành managed.
3. Tạo Order với tham chiếu tới Customer **đang managed**.
4. Gọi `persist(order)`.
5. Khi flush/commit, ORM có thể sắp xếp thao tác tạo Customer và Order sao cho FK trỏ đến hàng hợp lệ.

Không bắt buộc phải gọi `em.flush()` sau `persist(customer)` trong mọi trường hợp để lấy ID. Với `IDENTITY`, nhà cung cấp xử lý thời điểm cần INSERT; với `SEQUENCE`, ID có thể được cấp trước. Khi cả hai object đang managed trong cùng một context và quan hệ được mapping đúng, ORM có đủ thông tin để lập kế hoạch lưu phụ thuộc.

### 4.1. Ưu điểm của persist tường minh

- **Rõ ý định nghiệp vụ:** service tạo Customer thật, sau đó tạo Order.
- **Không thay đổi chính sách cascade toàn cục:** phù hợp khi Customer là entity có vòng đời độc lập.
- **Kiểm soát thao tác:** có thể validate uniqueness, phân quyền và các quy tắc trước khi lưu.
- **Dễ phân biệt tạo mới với sử dụng lại:** khách hàng mới được persist; khách hàng cũ được tải bằng ID.

Ví dụ thực tế: Order có thể bị xóa nhưng Customer vẫn phải tồn tại để xem lịch sử hoặc tạo đơn tiếp. Vì vậy, không nên gắn `CascadeType.ALL` vào `Order.customer` chỉ để tự động lưu khách hàng mới; `ALL` bao gồm cả `REMOVE`, có thể khiến xóa một Order dẫn đến yêu cầu xóa Customer.

### 4.2. Phân biệt “đích mới” và “đích đã tồn tại”

Nếu request cung cấp `customerId` của khách hàng hiện có, **không tạo `new Customer(...)` giả rồi cố persist**:

```java
// Không phải cách an toàn để liên kết khách hàng đã tồn tại:
Customer customer = new Customer("Tên từ client");
// customer chỉ là object mới, không được nhận diện là hàng đã tồn tại.
```

Thay vào đó:

```java
Customer customer = em.find(Customer.class, customerId);

if (customer == null) {
    throw new IllegalArgumentException("Khách hàng không tồn tại");
}

PurchaseOrder order = new PurchaseOrder(customer);
em.persist(order);
```

Với `find`, Customer được managed trong context hiện tại. Ứng dụng cũng có thể sử dụng `getReference` khi chỉ cần FK và có chính sách xử lý hàng không tồn tại phù hợp, nhưng reference **không phải** bằng chứng database đã có hàng.

## 5. Giải pháp 2: dùng `cascade=PERSIST` cho entity phụ thuộc vòng đời

Trong một số quan hệ, việc persist cha và các con mới **là một thao tác nghiệp vụ duy nhất**. Ví dụ một Order được tạo cùng nhiều dòng OrderLine; line không có ý nghĩa nếu không thuộc Order.

Khi đó, `cascade=CascadeType.PERSIST` có thể diễn đạt đúng quy tắc:

> Khi yêu cầu persist Order, hãy lan truyền persist tới các OrderLine mới đang thuộc quan hệ.

### 5.1. Mapping Order–OrderLine hai chiều

**`PurchaseOrder.java` — các phần chính của ví dụ này**

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public void addLine(OrderLine line) {
        if (line == null) {
            throw new IllegalArgumentException("Line không hợp lệ");
        }
        lines.add(line);
        line.setOrder(this);
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

**`OrderLine.java`**

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

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Dữ liệu line không hợp lệ");
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
```

Ví dụ dùng các import `jakarta.persistence.*` và `java.util.List`, `java.util.ArrayList`, `java.util.Collections` tương ứng.

**Hai điểm độc lập phải đúng:**

- `cascade=PERSIST` ở `PurchaseOrder.lines` giúp lan truyền thao tác lưu từ cha sang con.
- `OrderLine.order` là **owning side** của FK `order_lines.order_id` vì khai báo `@ManyToOne` và `@JoinColumn`. Helper `addLine` phải thiết lập trường này.

Chỉ có cascade mà bỏ gán `line.order = order` **không bảo đảm khóa ngoại được ghi**. Chỉ gán `line.order` mà không persist child/cascade **không bảo đảm child được lưu**. Cả hai trách nhiệm cần được giải quyết.

### 5.2. Tạo cả graph rồi persist một lần

```java
PurchaseOrder order = new PurchaseOrder();

OrderLine keyboard = new OrderLine("KEYBOARD", 1);
OrderLine mouse = new OrderLine("MOUSE", 2);

order.addLine(keyboard);
order.addLine(mouse);

em.getTransaction().begin();
try {
    em.persist(order); // PERSIST cascade tới keyboard và mouse.
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
```

Với mapping trên, ý định là **một Order mới cùng hai OrderLine mới**. Cả cha và con được đưa vào vòng đời persistence thông qua `persist(order)` và cascade.

Một schema tương ứng:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);
```

ORM cần tạo Order để xác lập ID rồi ghi các dòng hàng với `order_id` phù hợp. Chuỗi SQL cụ thể tùy generator, dialect và provider; về mặt logic, chỉ nên commit khi các ràng buộc FK được thỏa mãn.

### 5.3. Tại sao cascade thường đặt từ cha sang con?

Vì OrderLine **thuộc vòng đời của Order**, việc tạo Order cùng các dòng hàng là một use case nhất quán. Ngược lại, một Order tham chiếu Customer thường chỉ là **quan hệ tới thực thể dùng lại**. Hai mối quan hệ đều có thể biểu diễn bằng các annotation JPA, nhưng **cascade phải phản ánh lifecycle ownership**, không chỉ hướng foreign key.

| Quan hệ | Entity đích có vòng đời độc lập? | Chính sách persist khởi đầu |
|---|---|---|
| Order → Customer | Thường có | Persist Customer tường minh nếu tạo mới; tìm Customer managed nếu có sẵn |
| Order → OrderLine | Thường không | Cascade `PERSIST` từ Order sang các line có thể hợp lý |
| UserAccount → UserPreferences riêng | Thường không | Cascade `PERSIST` qua `@OneToOne` có thể hợp lý |
| BlogPost → Tag dùng chung | Có | Tìm/persist Tag riêng, không tự cascade `ALL` |
| Project → ProjectMembership | Membership phụ thuộc Project, User độc lập | Có thể cascade tới Membership; không cascade remove tới User |

Các gợi ý trên phụ thuộc domain. Một hệ thống có thể có quy tắc khác, nhưng **không nên bật cascade chỉ để làm hết lỗi transient** khi vòng đời dữ liệu không cho phép.

## 6. Hiểu đúng `CascadeType.PERSIST`, `ALL` và các loại cascade khác

Annotation quan hệ JPA có thể khai báo:

```java
@OneToMany(cascade = CascadeType.PERSIST)
private List<OrderLine> lines;
```

Các loại cascade liên quan:

| CascadeType | Thao tác trên entity nguồn | Tác động lan truyền |
|---|---|---|
| `PERSIST` | `em.persist(parent)` | Persist entity đích mới theo association |
| `MERGE` | `em.merge(parent)` | Merge trạng thái entity đích theo semantics merge |
| `REMOVE` | `em.remove(parent)` | Remove entity đích có quan hệ phù hợp |
| `REFRESH` | `em.refresh(parent)` | Làm mới entity liên quan |
| `DETACH` | `em.detach(parent)` | Detach entity liên quan |
| `ALL` | Mọi thao tác trên | Bao gồm `PERSIST`, `MERGE`, `REMOVE`, `REFRESH` và `DETACH` |

**`CascadeType.ALL` không phải đồng nghĩa `PERSIST`.** Nó còn lan truyền `REMOVE`, có thể gây xóa dữ liệu ngoài ý định.

Ví dụ:

```java
// Cần đánh giá kỹ: xóa Order có thể kéo theo xóa Customer.
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
```

Nếu Customer được nhiều Order tham chiếu, chính sách này thường không phù hợp.

### 6.1. Cascade chỉ tác động qua quan hệ được khai báo

Nếu `Order` tham chiếu `Customer` nhưng cascade chỉ được khai báo từ `Customer` đến `Address`, việc persist Order **không tự lan truyền** qua mọi đường trong object graph.

JPA xét cascade theo những association được mapping và theo từng loại thao tác. Nó không thực hiện `persist` đệ quy cho mọi object có thể truy cập bằng Java reference bất kể annotation.

### 6.2. Cascade và owning side là hai khái niệm khác nhau

```text
Persist cha ─────────────> CascadeType.PERSIST ───> Entity con trở thành managed

Ghi foreign key ─────────> Owning side của association ─> Cột FK đúng
```

Ví dụ `@OneToMany(mappedBy="order", cascade=PERSIST)` nằm ở phía inverse vẫn có thể lan truyền persist, nhưng **FK được quyết định bởi `OrderLine.order`**. Cascade không “đổi ownership” sang phía khai báo nó.

### 6.3. Orphan removal không phải cách lưu entity mới

`orphanRemoval=true` là cơ chế xóa entity con **khi bị gỡ khỏi quan hệ sở hữu vòng đời**, không phải phương án thay thế `cascade=PERSIST`.

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Trong ví dụ này:

- `cascade=PERSIST` hỗ trợ **tạo** OrderLine cùng Order.
- `orphanRemoval=true` hỗ trợ **xóa** OrderLine khi line đang được quản lý và bị gỡ khỏi association theo semantics thích hợp.

Một OrderLine mới bị thêm rồi gỡ khỏi list trước khi được persist không nên được coi là một managed orphan mà JPA chắc chắn sẽ xóa. Orphan removal có các giới hạn với entity new/detached/removed. Hãy nắm rõ trạng thái thay vì trông chờ annotation tự giải quyết mọi biến thể.

## 7. Khi entity cha đã managed và bổ sung entity con mới

Không phải lúc nào Order và OrderLine cũng được tạo trong một lần. Có thể Order đã nằm trong database và đã managed:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);

OrderLine newLine = new OrderLine("HEADSET", 1);
order.addLine(newLine);
```

Tại đây:

- `order` là managed nếu `find` tìm thấy và context còn hoạt động.
- `newLine` ban đầu là transient.
- `order.addLine(newLine)` đổi **object graph trong bộ nhớ**, thiết lập owning side qua helper.
- Nếu mapping có cascade `PERSIST`, JPA có thể lan truyền persistence tới child theo quy tắc cascade khi `persist`/flush được thực hiện.
- Không nên dựa vào `em.contains(newLine)` chắc chắn thành `true` ngay **sau lời gọi addLine**: chỉ thêm collection Java không phải một lệnh EntityManager trực tiếp.

Nếu service muốn quản lý chính xác thời điểm child trở thành managed, cách rõ ràng là:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);

if (order == null) {
    throw new IllegalArgumentException("Order không tồn tại");
}

OrderLine newLine = new OrderLine("HEADSET", 1);
order.addLine(newLine);

em.persist(newLine); // Tường minh, không phụ thuộc điểm cascade được duyệt.
```

Đoạn này diễn ra trong transaction phù hợp và vẫn cần helper thiết lập `newLine.order`. Nếu `em.persist(order)` được gọi khi Order đã managed, quy tắc cascade PERSIST cũng có thể được áp dụng qua relation; nhưng gọi persist trên managed parent không phải thao tác tạo parent mới.

**Một thực hành dễ kiểm soát:** khi thêm child mới vào aggregate đã tồn tại, chọn rõ một trong hai convention: cascade qua aggregate được thiết kế đúng hoặc persist child tường minh trong service. Đừng lẫn lộn giữa “thêm phần tử vào list” và “đảm bảo row child được INSERT”.

## 8. `@ManyToOne` tới entity mới: vì sao phải thận trọng với cascade?

### 8.1. Trường hợp target có vòng đời độc lập

Ví dụ nhân viên mới được gán vào một phòng ban cũng vừa được tạo. Hai entity này cùng mới, nhưng `Department` có vòng đời độc lập với `Employee`. Nếu đặt `cascade=ALL` trên `Employee.department`, khi xóa Employee có thể yêu cầu xóa Department đang có nhiều nhân viên khác.

```java
@Entity
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;
}
```

Một service tạo phòng ban rồi tạo nhân viên có thể làm:

```java
Department department = new Department("Engineering");
em.persist(department);

Employee employee = new Employee("An", department);
em.persist(employee);
```

Trường hợp chọn phòng ban đã tồn tại:

```java
Department department =
    em.find(Department.class, requestedDepartmentId);

if (department == null) {
    throw new IllegalArgumentException("Department không tồn tại");
}

Employee employee = new Employee("An", department);
em.persist(employee);
```

Hai đoạn chỉ minh họa thứ tự thao tác; `Department` và `Employee` cần constructor/mapping phù hợp trong dự án. Ý chính: **service quyết định khi nào tạo Department**, thay vì mặc định Employee chịu trách nhiệm lifecycle của Department.

### 8.2. Có được đặt cascade PERSIST lên ManyToOne không?

Về mặt annotation JPA, cascade `PERSIST` có thể được khai báo trên `@ManyToOne` nếu đúng semantics. Nhưng điều đó có nghĩa persist Employee có thể yêu cầu persist Department được tham chiếu. Cần trả lời:

- Employee có thực sự “sở hữu việc tạo” Department không?
- Department có thể đã tồn tại và được dùng chung không?
- Mã nghiệp vụ có lúc nhận Department detached thay vì new không?
- Có muốn Employee tự tạo Department khi chưa tìm thấy một mã? Điều này có đúng quy tắc unique/concurrency không?

Đặc biệt, cascade `PERSIST` không phải công cụ upsert mặc định. Một Department detached cùng ID không tự trở thành “một Department mới cần tạo”; cố persist nó có thể ném lỗi hoặc vi phạm PK, tùy trạng thái và provider.

## 9. `@OneToOne`: entity mới phụ thuộc cha

Một trường hợp phù hợp với cascade là tài khoản mới có hồ sơ riêng. `UserProfile` không được chia sẻ bởi nhiều `UserAccount`.

**`UserAccount` sở hữu FK tới profile (một phương án đơn giản):**

```java
@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(
        cascade = CascadeType.PERSIST,
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(
        name = "profile_id",
        unique = true,
        nullable = false
    )
    private UserProfile profile;

    protected UserAccount() {
    }

    public UserAccount(UserProfile profile) {
        this.profile = Objects.requireNonNull(profile);
    }
}
```

**`UserProfile` không cần reference ngược nếu mapping đơn hướng:**

```java
@Entity
@Table(name = "user_profiles")
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected UserProfile() {
    }

    public UserProfile(String displayName) {
        this.displayName = displayName;
    }
}
```

Tạo mới:

```java
UserProfile profile = new UserProfile("Mai");
UserAccount account = new UserAccount(profile);

em.persist(account); // PERSIST cascade tới profile.
```

Provider có thể lưu Profile trước để nhận `profile.id` rồi lưu Account với `profile_id`; giao dịch phải bảo đảm FK hợp lệ. Cột `profile_id` ở bảng `user_accounts` có `UNIQUE` để một Profile không bị liên kết như profile của nhiều account.

Không nên suy ra `@OneToOne` tự động sinh cascade; nếu bỏ `cascade=PERSIST`, account tham chiếu profile mới có thể gặp cùng bài toán transient như các quan hệ khác. Ngoài ra, một mô hình `@OneToOne` chia sẻ primary key dùng `@MapsId` có cách mapping khác và đòi hỏi quản lý derived identity phù hợp.

## 10. `@ManyToMany`: liên kết với đối tượng mới trong tập dùng chung

Ví dụ một bài viết có nhiều thẻ và một thẻ gắn được với nhiều bài viết. Quan hệ:

```java
@Entity
public class Article {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "article_tags",
        joinColumns = @JoinColumn(name = "article_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new HashSet<>();

    public void addTag(Tag tag) {
        tags.add(tag);
    }
}
```

`Tag` có khóa và tên duy nhất:

```java
@Entity
@Table(name = "tags",
       uniqueConstraints = @UniqueConstraint(
           name = "uq_tag_code",
           columnNames = "code"))
public class Tag {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String code;

    protected Tag() {
    }

    public Tag(String code) {
        this.code = code;
    }
}
```

Khi tạo Article với Tag chưa được lưu:

```java
Article article = new Article();
Tag tag = new Tag("jpa");

article.addTag(tag);

em.persist(article); // Không cascade PERSIST tới Tag trong mapping này.
```

Lúc ghi bảng nối, provider cần `tag_id` hợp lệ. Nếu Tag là transient, đây cũng là tình huống association tới entity mới chưa được persist.

### 10.1. Cách xử lý khi Tag thực sự mới

```java
Tag tag = new Tag("jpa");
em.persist(tag);

Article article = new Article();
article.addTag(tag);
em.persist(article);
```

Entity Tag được quản lý riêng và Article chỉ tham chiếu nó. Khi flush, JPA có thể ghi hàng `tags`, `articles` và `article_tags` theo quan hệ phụ thuộc.

### 10.2. Cách xử lý khi Tag đã tồn tại

Không nên cố tạo Tag mới mỗi lần người dùng nhập `"jpa"`. Nên tìm Tag bằng mã đã chuẩn hóa trong giao dịch, dùng instance managed:

```java
Tag tag = em.createQuery(
        "select t from Tag t where t.code = :code",
        Tag.class
    )
    .setParameter("code", "jpa")
    .getSingleResult();

article.addTag(tag);
em.persist(article);
```

`getSingleResult()` có thể ném `NoResultException` nếu không tìm thấy, nên service thực tế phải xử lý nhánh “không có tag” và tạo Tag mới **theo chính sách nghiệp vụ**. Với nhiều transaction cùng tạo cùng tag code, constraint `UNIQUE(code)` ở database phải bảo vệ dữ liệu; kiểm tra ở Java không loại bỏ race condition.

### 10.3. Vì sao thường không cascade REMOVE trên ManyToMany?

Tag có thể thuộc hàng nghìn Article. Nếu thêm `cascade=ALL` vào `Article.tags`, xóa một Article có thể lan truyền `REMOVE` tới Tag; đây thường là sai semantics.

Tạo mới một Tag trong cùng service rồi thêm vào Article **không đòi hỏi** bật cascade xóa. Với quan hệ chia sẻ, ưu tiên lưu target tường minh hoặc lấy managed target; giữ vòng đời của Article và Tag độc lập.

## 11. Entity mới và detached entity là hai vấn đề khác nhau

Một nguồn lỗi phổ biến là API đưa vào một object có ID nhưng không được quản lý trong context hiện tại.

### 11.1. Detached có thể mang ID của hàng đã lưu

```java
Customer detached;

EntityManager em1 = emf.createEntityManager();
try {
    detached = em1.find(Customer.class, 10L);
} finally {
    em1.close();
}

// Ở persistence context khác:
EntityManager em2 = emf.createEntityManager();
```

`detached` có thể mang ID 10 và dữ liệu đầy đủ, nhưng `em2.contains(detached)` là false. Đây **không phải** một Customer mới cần gọi `em2.persist(detached)`.

Nếu chỉ muốn Order tham chiếu khách hàng ID 10, có thể tải managed instance:

```java
Customer managedCustomer =
    em2.find(Customer.class, detached.getId());

if (managedCustomer == null) {
    throw new IllegalArgumentException("Khách hàng không tồn tại");
}

PurchaseOrder order = new PurchaseOrder(managedCustomer);
em2.persist(order);
```

Cách này tránh việc persist một detached object và tránh merge toàn bộ trạng thái Customer chỉ để lấy khóa ngoại.

### 11.2. `merge` sao chép trạng thái, không biến đối số thành managed

```java
Customer detached = /* lấy từ context đã đóng */ ...;

Customer managed = em.merge(detached);

System.out.println(em.contains(detached)); // false.
System.out.println(em.contains(managed));  // true.
```

`merge` trả về instance managed tương ứng. Đối số vẫn detached. Với graph có association, `cascade=MERGE` có thể lan truyền merge tới các entity liên quan theo mapping. Với entity new, merge có thể tạo managed copy và insert sau đó theo semantics của JPA.

Nhưng **`merge` không phải cách sửa mặc định cho mọi lỗi “unsaved transient instance”**. Khi application chỉ muốn tạo Customer mới, `persist` thể hiện ý định trực tiếp hơn. Khi chỉ muốn tham chiếu Customer đã tồn tại, `find`/`getReference` hoặc một reference managed tương ứng thường phù hợp hơn việc merge Customer từ JSON client.

### 11.3. `getReference` cho target đã biết ID

```java
Customer customerReference =
    em.getReference(Customer.class, customerId);

PurchaseOrder order = new PurchaseOrder(customerReference);
em.persist(order);
```

`getReference` có thể tránh SELECT tức thì để tải toàn bộ Customer. Nhưng provider có thể trả lazy proxy và **không phải lúc nào kiểm tra sự tồn tại ngay**. Nếu ID không tồn tại, lỗi có thể xảy ra khi truy cập proxy hoặc khi FK được ghi. Cần kiểm tra authorization và xử lý ID không tồn tại theo yêu cầu nghiệp vụ.

Không dùng `getReference` với một ID tùy ý chưa có hàng rồi tưởng rằng JPA sẽ tự tạo Customer mới.

## 12. ID tự cấp, ID tự sinh và hiện tượng “có ID nhưng chưa lưu”

### 12.1. Generated ID

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Với một entity mới:

```java
Customer customer = new Customer("An");
// customer.getId() thường null lúc này.
```

Trước persist, target mới không được quản lý. Lưu entity đích hoặc cascade PERSIST phù hợp giúp JPA tạo khóa hợp lệ theo database.

### 12.2. Assigned ID hoặc UUID tự cấp

```java
@Entity
public class ApiClient {

    @Id
    private UUID id;

    public ApiClient() {
        this.id = UUID.randomUUID();
    }
}
```

Entity mới này **đã có ID** ngay sau constructor nhưng chưa được persist. Nếu một entity khác tham chiếu `ApiClient`, vấn đề transient vẫn tồn tại:

```java
ApiClient client = new ApiClient(); // ID khác null.
System.out.println(em.contains(client)); // false.
```

Một foreign key có giá trị UUID vẫn sẽ vi phạm FK nếu hàng đích chưa tồn tại và không được INSERT trong transaction. Không kiểm tra “`id != null`” để quyết định target chắc chắn đã được lưu.

### 12.3. Khi biết ID nhưng chưa biết target tồn tại

Một ID đến từ API chỉ là **giá trị đầu vào**. Service cần xác minh nó đại diện đúng entity có thể được liên kết. Các lựa chọn gồm:

- `find` để đọc và kiểm tra target trong persistence context.
- `getReference` khi phù hợp và cho phép để FK/việc truy cập sau xác nhận, kèm xử lý lỗi rõ ràng.
- Truy vấn theo business key như `email`/`code` với unique constraint.
- Tạo entity mới có chủ đích, `persist` và xử lý trường hợp trùng unique key.

**Không tự diễn dịch ID tùy ý thành một entity managed.**

## 13. `@OneToMany` đơn hướng, bảng nối và các ràng buộc trung gian

Trong quan hệ `@OneToMany` **đơn hướng**, parent chỉ có collection các child:

```java
@Entity
public class Project {

    @Id
    private Long id;

    @OneToMany(cascade = CascadeType.PERSIST)
    @JoinTable(
        name = "project_tasks",
        joinColumns = @JoinColumn(name = "project_id"),
        inverseJoinColumns = @JoinColumn(name = "task_id")
    )
    private List<Task> tasks = new ArrayList<>();
}
```

Khi `Project` và `Task` đều mới, cascade `PERSIST` có thể giúp JPA tạo Task mới rồi ghi các hàng trong `project_tasks`. Vẫn cần schema bảo vệ cardinality và FK như mong muốn.

Nếu thay bằng `@JoinColumn(name="project_id")` trên collection, FK được lưu ở bảng Task; provider có thể dùng thứ tự `INSERT`/`UPDATE` phụ thuộc vào cách mapping. Với FK `NOT NULL`, có thể gặp lỗi nếu provider INSERT Task khi cột FK chưa được điền rồi UPDATE sau.

Điều cần phân biệt:

1. **Entity mới chưa được lưu:** cần persist/cascade để có hàng Task.
2. **Association chưa được thiết lập đúng:** cần mapping owning side hoặc join table/FK phù hợp.
3. **Schema cấm trạng thái trung gian:** cần chọn mapping và chuỗi ghi tương thích ràng buộc.

Một lỗi về FK `NOT NULL` không phải lúc nào cũng được sửa bằng cách thêm cascade; đôi khi cascade đã có, nhưng **owning side** hoặc cách tổ chức SQL mới là vấn đề. Với quan hệ cha–con thường xuyên cần FK non-null, mô hình hai chiều `@ManyToOne` ở child làm owning side có thể dễ dự đoán hơn.

## 14. Những lỗi và thông báo thường gặp

Tên exception cụ thể phụ thuộc JPA provider, thời điểm thao tác và cách framework bọc lỗi. Một số kiểu gặp với Hibernate:

| Triệu chứng | Nguyên nhân có thể | Điều nên xem |
|---|---|---|
| “object references an unsaved transient instance” | Entity đang lưu tham chiếu tới transient target không được persist | Quan hệ nào trỏ tới object mới, có cascade PERSIST hoặc persist tường minh không |
| `TransientPropertyValueException` | Property/association tham chiếu transient entity trong tình huống không lưu được | Field quan hệ, nullability, target lifecycle |
| `TransientObjectException` | Provider gặp transient entity tại thao tác cần reference persistent | Trạng thái object, cách gọi thao tác, mapping |
| Lỗi `not-null property references a null or transient value` | FK hoặc property bắt buộc chưa có giá trị hợp lệ | `@JoinColumn(nullable=false)`, owning side và schema |
| Database FK violation | FK được ghi không trỏ đến hàng hợp lệ | Target có tồn tại và được commit/insert trong cùng transaction không |
| Duplicate primary/unique key | Persist object mới nhưng hàng tương ứng đã tồn tại | Phân biệt new với existing; unique constraint; race condition |
| “detached entity passed to persist” | Object cũ có ID, đang detached nhưng bị xử lý như new | Tải managed target hoặc dùng merge đúng ý định |
| “multiple representations of same entity” | Graph có nhiều object khác nhau đại diện cùng identity | Không trộn managed/detached duplicate cùng context/merge một cách tùy tiện |
| Lỗi khi flush dù persist không báo | SQL được hoãn hoặc cascade được xử lý khi flush | Quan sát toàn bộ chuỗi thao tác và ràng buộc DB |
| SQL INSERT child thiếu parent FK | Chỉ sửa inverse collection, không thiết lập owning side | Helper đồng bộ hai phía, `line.setOrder(order)` |

Một số thông báo trên là **đặc thù Hibernate**, không phải một bộ exception thống nhất mà mọi JPA provider phải phát ra. Trong ứng dụng portable, việc hiểu **quan hệ, lifecycle và lỗi dữ liệu** quan trọng hơn việc chỉ bắt một tên exception.

### 14.1. Đừng chữa triệu chứng bằng cascade bừa bãi

Nếu thấy:

```text
save the transient instance before flushing
```

không nên ngay lập tức thêm:

```java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
```

Cách này có thể làm INSERT hoạt động nhưng tạo nguy cơ xóa Customer khi Order bị xóa, hoặc cascade các thao tác khác tới đối tượng dùng chung. Hãy xác định target cần tạo mới hay phải được tìm trong database; chỉ thêm **đúng loại cascade** nếu nó phản ánh ranh giới vòng đời nghiệp vụ.

### 14.2. Đừng coi ngoại lệ thiếu FK là lỗi duy nhất

Một entity có thể được persist thành công nhưng quan hệ không như ý nếu mapping không đồng bộ hai phía. Ví dụ:

```java
order.getLines().add(line);
// Thiếu line.setOrder(order) ở owning side.
```

Với FK nullable, dòng hàng có thể tồn tại mà `order_id` là null. Với FK not-null, flush có thể thất bại. Sửa cascade không giải quyết việc **chưa gán phía sở hữu**.

## 15. Điều gì xảy ra với transaction khi flush thất bại?

Giả sử flow:

```java
em.getTransaction().begin();

try {
    em.persist(order);
    em.flush(); // Ném lỗi vì transient association / FK.
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
```

Khi một thao tác persistence thất bại, transaction có thể bị đánh dấu rollback-only hoặc trở nên không thể tiếp tục theo cách an toàn. **Không cố sửa object rồi tiếp tục commit chính transaction bị lỗi** như một cách hồi phục phổ quát.

Một hướng an toàn là:

1. Ghi nhận ngoại lệ và thông tin association gây lỗi.
2. Rollback transaction đang thất bại.
3. Không dùng lại một persistence context đã bị lỗi như thể chưa có gì xảy ra.
4. Mở transaction/context hợp lệ cho một lần xử lý mới theo quy ước framework.
5. Sửa nguyên nhân: persist target, dùng managed target, thay mapping owning side hoặc điều chỉnh schema/logic.

Sau rollback, object Java có thể vẫn có ID hoặc field đã đổi trong bộ nhớ dù database không commit. Không dựa vào giá trị ID trên Java object để kết luận một hàng đã được lưu thành công.

### 15.1. `flush` khác `commit`

- `persist`: đưa entity new vào quản lý theo semantics JPA.
- `flush`: yêu cầu đồng bộ các thao tác chờ sang database trong transaction.
- `commit`: hoàn tất transaction và xác nhận thay đổi nếu thành công.

Một transient association có thể bị phát hiện ở một trong các bước này tùy provider. `flush` hữu ích trong **môi trường thử nghiệm** để thấy lỗi sớm hơn, nhưng không phải một cách tự động sửa quan hệ.

### 15.2. Không dựa vào SQL ordering ngẫu nhiên

Việc tự gọi `em.flush()` sau mỗi `persist` có thể làm luồng chậm và không cần thiết. Với mapping hợp lệ và graph được quản lý đúng, ORM thường có thể lập kế hoạch thứ tự thao tác theo dependency.

Nhưng nếu schema đòi hỏi những trạng thái trung gian không thể đáp ứng bởi mapping đang dùng (ví dụ FK NOT NULL trong unidirectional OneToMany được ghi qua nhiều bước), cần **đổi mapping hoặc quy trình ghi** thay vì rải `flush` khắp service.

## 16. Xử lý tạo mới trong Spring Data JPA

### 16.1. `save()` không tự cứu mọi transient association

Trong Spring Data JPA, repository có `save(entity)`. Tùy trạng thái new của entity và cơ chế phát hiện ID/version, việc lưu thường được thực hiện qua `persist` hoặc `merge`.

Nhưng:

```java
PurchaseOrder order = new PurchaseOrder(new Customer("Mai"));

orderRepository.save(order);
```

không có nghĩa framework chắc chắn sẽ tạo Customer mới. Nó vẫn dựa vào **mapping JPA và cascade**, cùng trạng thái entity và đường thực thi cụ thể.

Cũng không nên coi `@Transactional` là phép bật tự động persist toàn bộ object graph. Transaction đảm bảo ranh giới công việc, chứ **không thay thế chính sách cascade hoặc persist target tường minh**.

### 16.2. Service tách hai use case: khách hàng mới và khách hàng hiện có

**Use case A — tạo khách hàng mới cùng đơn hàng:**

```java
@Service
public class PurchaseOrderService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createWithNewCustomer(String customerName) {
        Customer customer = new Customer(customerName);
        em.persist(customer);

        PurchaseOrder order = new PurchaseOrder(customer);
        em.persist(order);

        // Với IDENTITY, provider có thể phải INSERT để biết ID;
        // giá trị ID được sử dụng theo vòng đời của generator.
        em.flush();
        return order.getId();
    }
}
```

Đây là ví dụ với Spring `@Service`, `@Transactional` và `jakarta.persistence.PersistenceContext`; trong ứng dụng thật cần imports và ràng buộc dữ liệu thích hợp.

**Use case B — tạo đơn cho khách hàng đã tồn tại:**

```java
@Transactional
public Long createForExistingCustomer(Long customerId) {
    Customer customer = em.find(Customer.class, customerId);

    if (customer == null) {
        throw new IllegalArgumentException("Customer không tồn tại");
    }

    PurchaseOrder order = new PurchaseOrder(customer);
    em.persist(order);
    em.flush();
    return order.getId();
}
```

Hai đường xử lý cho thấy rõ: **tạo mới** và **tham chiếu dữ liệu có sẵn** không phải một việc. Điều này tránh API vô tình tạo trùng customer do client gửi object chưa managed.

### 16.3. DTO/command giúp tránh graph không rõ trạng thái

Thay vì nhận nguyên một entity graph từ HTTP request:

```json
{
  "customer": {
    "id": 10,
    "fullName": "Mai"
  },
  "lines": [
    {"sku": "MOUSE", "quantity": 2}
  ]
}
```

có thể dùng command rõ nghĩa:

```json
{
  "customerId": 10,
  "lines": [
    {"sku": "MOUSE", "quantity": 2}
  ]
}
```

Service sẽ:

1. Kiểm tra quyền với customer ID 10.
2. Tải `Customer` managed hiện có.
3. Tạo `PurchaseOrder` mới.
4. Tạo các `OrderLine` transient mới thuộc Order.
5. Persist Order và cascade PERSIST tới các line theo mapping phù hợp.

Thiết kế này không yêu cầu deserialize một `Customer` detached hoặc transient rồi nhờ JPA đoán “tạo mới hay tham chiếu hàng cũ”.

## 17. Ràng buộc database và tính nhất quán

### 17.1. `@JoinColumn(nullable=false)` không phải toàn bộ bảo vệ

```java
@ManyToOne(optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Metadata JPA thể hiện association bắt buộc, nhưng database vẫn nên có:

```sql
customer_id BIGINT NOT NULL
    REFERENCES customers(id)
```

**NOT NULL** bảo đảm FK không trống. **FOREIGN KEY** bảo đảm giá trị FK trỏ đến hàng hợp lệ. Cả hai có nhiệm vụ khác nhau, và không annotation nào tự biến transient entity thành một target đã lưu.

### 17.2. Bean Validation khác cascade persistence

Có thể gặp:

```java
@NotNull
@Valid
@ManyToOne(optional = false)
private Customer customer;
```

`@NotNull` và `@Valid` thuộc Bean Validation, không phải tương đương `cascade=CascadeType.PERSIST` của JPA.

- `@NotNull` xác nhận tham chiếu không null theo validation.
- `@Valid` có thể yêu cầu validation đệ quy vào object liên quan.
- `cascade=PERSIST` quyết định có lan truyền thao tác lưu JPA hay không.

Một Customer transient có thể vượt qua validation tên/email nhưng **vẫn chưa được persist**. Validation hợp lệ không bảo đảm khóa ngoại hợp lệ.

### 17.3. Unique constraint và race condition

Nếu hai transaction cùng tạo Customer với email giống nhau, cả hai có thể kiểm tra “chưa có” trước khi insert. Chỉ kiểm tra ở Java không giải quyết concurrency. Hãy đặt unique constraint trên natural key cần duy nhất và xử lý lỗi tạo trùng theo domain.

```sql
ALTER TABLE customers
ADD COLUMN email VARCHAR(255);

CREATE UNIQUE INDEX uq_customers_email
    ON customers(email);
```

Nếu muốn tái sử dụng Customer đã tồn tại, nên xác định khóa nghiệp vụ phù hợp và một quy trình lookup/create được bảo vệ khỏi race, không cứ gặp transient exception là thêm cascade PERSIST.

## 18. Khi nào nên đổi thiết kế thay vì tự động persist?

Một số object “chưa được lưu” là dấu hiệu mô hình dữ liệu chưa rõ.

### 18.1. Entity con có thật sự là entity độc lập?

Nếu một `Address` chỉ chứa street/city/zip và hoàn toàn phụ thuộc vào `Customer`, cân nhắc `@Embeddable` thay vì `@OneToOne` hoặc `@ManyToOne`:

```java
@Embeddable
public class Address {
    private String street;
    private String city;
    private String zipCode;
}

@Entity
public class Customer {
    @Id
    private Long id;

    @Embedded
    private Address address;
}
```

`Address` ở đây là **value object được nhúng**, không phải entity riêng. Khi tạo Customer, không cần `persist(address)` vì JPA lưu các field Address như một phần hàng Customer.

Không phải cứ có class Java riêng thì phải tạo `@Entity` với ID và cascade.

### 18.2. Dùng business key tham chiếu thay vì entity mới

Nếu `Order` tham chiếu một quốc gia đã có trong bảng `countries`, API gửi `countryCode="VN"` không có nghĩa nên tạo `new Country("VN")` rồi cascade persist. Nên tìm Country theo mã hoặc tham chiếu existing entity đúng cách; ràng buộc unique ở bảng countries bảo vệ tính duy nhất.

### 18.3. Association có metadata riêng

Nếu Order và Product liên kết với số lượng/đơn giá/trạng thái, một `@ManyToMany` trực tiếp không đủ. Tạo một `OrderItem` entity trung gian với hai `@ManyToOne`. Khi Order mới có Item mới:

- OrderItem có thể được persist theo cascade từ Order.
- Product thường là entity shared, được tìm managed theo ID.
- Không cascade REMOVE từ OrderItem tới Product.

Mô hình đúng làm luồng persist dễ hiểu hơn và tránh transient Product được tạo nhầm từ dữ liệu client.

### 18.4. Các entity được tạo ở nhiều hệ thống khác nhau

Nếu target được tạo ở dịch vụ khác và chỉ có external ID, JPA không thể cascade qua ranh giới microservice để “persist” một entity ở database bên ngoài. Cần lưu reference/foreign ID theo thiết kế tích hợp, xác thực sự tồn tại qua API/event nếu cần, và xử lý tính nhất quán cuối cùng. `CascadeType.PERSIST` chỉ nói về **persistence context/JPA mapping hiện tại**, không phải distributed transaction hoặc cơ chế tạo object từ xa.

## 19. Một quy trình suy luận khi gặp transient association

Khi gặp thông báo “unsaved transient instance” hoặc flush thất bại vì liên kết tới entity mới, có thể đi theo trình tự:

1. **Xác định field quan hệ** được nêu trong lỗi, ví dụ `PurchaseOrder.customer` hoặc `OrderLine.order`.
2. **Xác định target instance** là new, managed, detached hay removed; không chỉ xem ID null hay không.
3. **Xác định intent nghiệp vụ:** có muốn tạo target mới không, hay phải sử dụng một entity đã tồn tại?
4. **Xác định ownership vòng đời:** target là child độc quyền, entity chia sẻ hay một value object?
5. **Chọn thao tác tạo:** gọi `persist(target)` tường minh hoặc chỉ định `cascade=PERSIST` trên association phù hợp.
6. **Kiểm tra owning side:** FK được điều khiển bởi field nào? Với `mappedBy` cần gán phía owning side, không chỉ đổi inverse collection.
7. **Kiểm tra ID:** generated/assigned/derived identity, thời điểm ID được tạo và khả năng provider định tuyến INSERT.
8. **Kiểm tra schema:** FK, NOT NULL, UNIQUE, JOIN TABLE và dữ liệu có sẵn.
9. **Kiểm tra transaction:** tất cả thao tác có nằm trong cùng transaction/persistence context hợp lệ không?
10. **Xử lý lỗi và rollback:** không tiếp tục commit transaction đã thất bại; sửa logic rồi thử lại trong context phù hợp.
11. **Nếu từ API:** tránh merge/persist nguyên object graph không rõ trạng thái; dùng DTO/command và tải target managed.
12. **Nếu lỗi tái diễn:** quan sát SQL thực tế, xác định đó là thiếu persist, thiếu owning side hay constraint/ordering issue.

### Bảng quyết định nhanh

| Tình huống | Cách xử lý khởi đầu | Tránh |
|---|---|---|
| Order mới tham chiếu Customer mới được tạo hợp lệ | `persist(customer)` rồi `persist(order)` trong cùng transaction | Thêm `cascade=ALL` vào ManyToOne chỉ để hết lỗi |
| Order mới tham chiếu Customer đã có ID | `find`/managed reference cho Customer, rồi persist Order | Tạo Customer transient giả và persist |
| Order mới có các OrderLine mới thuộc quyền sở hữu | `@OneToMany(cascade=PERSIST)` và helper set owning side | Chỉ thêm line vào inverse list |
| Order đã managed được thêm một line mới | `persist(line)` tường minh hoặc sử dụng cascade đúng cơ chế | Giả định `list.add` tự lưu line ngay |
| Article mới có Tag mới nhưng Tag là shared | Persist hoặc resolve Tag riêng trước khi liên kết | `CascadeType.REMOVE`/`ALL` trên ManyToMany |
| Entity nhận từ context khác có cùng ID | Tải managed target hoặc merge có chủ đích | `persist(detached)` như entity mới |
| Target có UUID assigned nhưng chưa persist | Persist target hoặc cascade PERSIST phù hợp | Cho rằng ID khác null chứng minh row đã có |
| Target chỉ là value object phụ thuộc entity | Cân nhắc `@Embeddable` | Tạo entity và cascade phức tạp không cần thiết |
| FK bắt buộc và INSERT child thiếu parent | Thiết lập owning side, mapping và thứ tự ghi phù hợp | Bỏ NOT NULL vô điều kiện ở production |

## 20. Các lỗi tư duy thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “Có tham chiếu Java thì ORM tự lưu object đích.” | Chỉ lưu khi target được persist tường minh hoặc thao tác persistence được cascade đúng. |
| “`@ManyToOne` tự động cascade PERSIST.” | Mặc định không tự lan truyền persist nếu không cấu hình cascade tương ứng. |
| “`cascade=ALL` là cách sửa mọi lỗi transient.” | ALL bao gồm REMOVE và các thao tác khác, có thể gây mất dữ liệu shared entity. |
| “`@OneToMany(mappedBy=...)` đã đủ thiết lập FK.” | Phải cập nhật owning side, thường là `@ManyToOne` ở child. |
| “Có ID khác null thì chắc chắn đã lưu.” | Assigned ID/UUID có thể tồn tại trên transient object; detached cũng có ID. |
| “`em.contains(entity)==false` thì cứ `persist(entity)`.” | False còn gồm detached, removed và object từ context khác. |
| “Không cần transaction nếu đã bật cascade.” | Cascade không thay thế transaction và rollback. |
| “`em.persist(parent)` trả về bình thường thì toàn graph hợp lệ.” | Lỗi có thể chỉ lộ ra ở flush/commit. |
| “`@Valid` cũng là cascade persistence.” | Bean Validation cascade và JPA cascade là hai cơ chế khác nhau. |
| “`merge` biến object detached đầu vào thành managed.” | Managed object là giá trị trả về; input vẫn detached. |
| “`getReference` chắc chắn hàng target có thật.” | Proxy có thể chưa kiểm tra existence; FK/lazy access có thể báo lỗi sau. |
| “Gỡ child khỏi list thì child mới chưa lưu sẽ bị ORM xóa.” | Orphan removal có giới hạn trạng thái và không phải cách quản lý new entity nói chung. |
| “FK lỗi thì chỉ cần cho nullable.” | Cần xét domain invariants, owning side, SQL sequencing và transaction. |
| “Cùng một cascade dùng cho mọi quan hệ.” | Quyền sở hữu vòng đời của OrderLine khác Customer, Tag, Department. |

## 21. Bài thực hành

### Bài 1 — Cố ý tạo lỗi transient ở ManyToOne

Tạo `Customer` và `PurchaseOrder` như phần 3, FK `purchase_orders.customer_id NOT NULL`. Trong transaction:

```java
Customer customer = new Customer("Mai");
PurchaseOrder order = new PurchaseOrder(customer);

em.persist(order);
em.flush();
```

Quan sát thời điểm và loại lỗi provider. Giải thích vì sao JPA không tự tạo Customer.

### Bài 2 — Sửa bằng persist tường minh

Chạy lại tình huống trên nhưng thêm:

```java
em.persist(customer);
em.persist(order);
```

trong cùng transaction. Kiểm tra dữ liệu sau commit: phải có Customer và Order, với FK trỏ đúng ID. So sánh số SQL được phát và thời điểm ID xuất hiện.

### Bài 3 — Tạo OrderLine bằng cascade

Tạo `PurchaseOrder` mới, hai `OrderLine` mới, khai báo `cascade=PERSIST` tại `Order.lines` và `mappedBy="order"`. Dùng helper `order.addLine(line)` đồng bộ hai phía rồi gọi `em.persist(order)`.

Đối chiếu ba kết quả:

1. Đã bật cascade và set owning side.
2. Có cascade nhưng không set `line.order`.
3. Đã set owning side nhưng bỏ cascade và không persist line.

Tự giải thích ba tác dụng khác nhau của cascade, owning side và database FK.

### Bài 4 — Thêm child vào parent đã managed

Tải một Order đã có ID bằng `em.find`; tạo một OrderLine transient, thêm vào collection và quan sát `em.contains(newLine)` trước/sau `em.persist(newLine)` và sau flush.

Thử phương án dựa vào cascade PERSIST theo mapping provider đang dùng. Giải thích vì sao một lệnh Java `list.add` không phải lệnh persist.

### Bài 5 — Existing target và detached target

Tải Customer bằng `em1` rồi đóng context, giữ object detached. Trong `em2`, thử phân biệt việc:

- Lấy managed Customer qua `em2.find(Customer.class, detached.getId())`.
- Gọi `em2.merge(detached)` và sử dụng **giá trị trả về**.
- Gọi `em2.persist(detached)` như thể object mới.

Quan sát khác biệt trạng thái và xử lý ngoại lệ trong môi trường thử nghiệm. Không coi ba cách là tương đương.

### Bài 6 — Tag shared và ManyToMany

Tạo hai Article cùng tham chiếu một Tag `"jpa"`. Persist Tag một lần rồi gắn instance managed cho các Article. Đặt unique constraint theo `tag.code`.

Giải thích vì sao không nên bật `cascade=REMOVE` từ Article tới Tag; xóa một Article không được xóa Tag mà Article khác vẫn sử dụng.

### Bài 7 — Assigned UUID vẫn là transient

Tạo một `ApiClient` có UUID cấp trong constructor nhưng chưa persist. Một entity khác trỏ tới ApiClient đó qua association. Kiểm tra `id != null`, `em.contains(client)` và tác động khi flush nếu không persist client.

Giải thích vì sao ID đã tồn tại trong Java không bảo đảm foreign key hợp lệ.

### Bài 8 — So sánh lỗi FK với lỗi thiếu cascade

Tạo hai thí nghiệm:

- Một Order trỏ tới Customer transient, không cascade PERSIST.
- Một Order đã persist, nhưng collection OrderLine phía inverse được thêm child không thiết lập `line.order`.

Quan sát lỗi và SQL. Xác định lỗi nào do **target chưa được persist**, lỗi nào do **owning side chưa thiết lập**. Cả hai có thể dẫn đến ràng buộc FK thất bại, nhưng cách sửa khác nhau.

### Bài 9 — API command

Thiết kế endpoint tạo Order với payload chỉ có `customerId` và danh sách dòng hàng `sku/quantity`. Mô tả service:

1. Validate quyền và dữ liệu.
2. Tải Customer managed.
3. Tạo Order mới.
4. Tạo OrderLine mới bằng helper.
5. Persist Order và cascade PERSIST tới các line.
6. Commit và trả về ID.

Vì sao dùng ID thay vì deserialize toàn bộ Customer từ client sẽ làm vòng đời entity rõ ràng hơn?

## 22. Ghi nhớ cốt lõi

**Một entity mới được gán vào trường quan hệ vẫn là transient cho đến khi JPA nhận được thao tác persist thích hợp.** Muốn lưu quan hệ hợp lệ, cần **tạo/lấy entity đích đúng vòng đời**, đồng thời **thiết lập phía sở hữu quan hệ** để foreign key hoặc join table được ghi chính xác.

Hai cách xử lý chính là **`em.persist(target)` tường minh** khi service chủ động tạo entity đích, hoặc **`cascade=CascadeType.PERSIST`** khi entity đích thật sự phụ thuộc vào vòng đời entity nguồn. Với entity dùng chung như Customer, Department, Product hoặc Tag, thường nên tìm target đã tồn tại hoặc persist nó theo một use case riêng, không bật `CascadeType.ALL` bừa bãi.

Hãy phân biệt rõ **new** với **detached**, **managed state** với **database existence**, **cascade** với **owning side**, và **flush** với **commit**. Khi gặp lỗi transient reference, đừng chỉ sửa annotation: hãy truy ra ý định nghiệp vụ, trạng thái từng object, cấu trúc FK và transaction để chọn một cách lưu nhất quán, tránh tạo trùng hoặc xóa nhầm dữ liệu.
