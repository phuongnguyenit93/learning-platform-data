# Phân biệt kế hoạch tải và số câu SQL thực tế được thực thi

## 1. Vì sao hiểu fetch plan chưa đủ để dự đoán số SQL?

Trong Jakarta Persistence (JPA), ứng dụng có thể yêu cầu tải một entity và các mối quan hệ của nó bằng nhiều cách: `FetchType.EAGER`, `FetchType.LAZY`, `JOIN FETCH`, `EntityGraph`, projection hoặc cấu hình đặc thù của ORM. Những lựa chọn này thuộc **kế hoạch tải** (*fetch plan*): mô tả dữ liệu nào cần có và những quan hệ nào có thể được tải cùng lúc hoặc khi truy cập.

Nhưng **kế hoạch tải không phải bảng kê cố định số câu SQL**.

Ví dụ:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 101L);
```

Một developer có thể hỏi:

> `find` chỉ gọi một lần, vậy database chỉ chạy một câu `SELECT` phải không?

Không thể kết luận như vậy chỉ từ dòng Java. Tùy mapping, graph, cache, proxy, các association đã có trong persistence context, cấu hình ORM và hành vi thực tế:

- Có thể chạy **một SELECT** lấy Order.
- Có thể chạy **thêm SELECT** để thỏa yêu cầu tải các quan hệ EAGER.
- Có thể **không chạy SELECT** nếu Order đã nằm trong persistence context.
- Có thể tải quan hệ bằng **JOIN**, hoặc dùng **secondary SELECT**.
- Có thể lúc đầu chỉ có một SELECT, nhưng khi gọi `order.getLines().size()` lại phát sinh thêm SQL.
- Có thể một lần truy cập collection kích hoạt cơ chế **batch fetch** hay **subselect fetch**, làm thay đổi số statement.
- Có thể code hiển thị danh sách gây hiện tượng **N+1**, dù câu JPQL ban đầu trông đơn giản.

Ngược lại, một câu SQL có nhiều JOIN không có nghĩa nó rẻ hơn vài câu SQL nhỏ: tập kết quả có thể bị nhân bản, rất rộng hoặc làm tăng bộ nhớ và chi phí truyền dữ liệu.

**Thông điệp chính:** hãy phân biệt ba lớp:

1. **Fetch requirement:** đối tượng và thuộc tính nào ứng dụng cần có?
2. **Execution strategy:** ORM thực hiện nhu cầu ấy bằng join, select bổ sung, batch, cache hay tải chậm?
3. **Observed SQL:** số câu SQL thực sự đi tới database trong **toàn bộ đoạn code đang đo**, với dữ liệu và transaction cụ thể.

Bài học thuộc chương **Kế hoạch tải** trong chủ đề **Data Persistence Relational Access ORM JPA**, tập trung vào sự khác nhau giữa **cấu hình/tuyên bố tải** và **hành vi SQL thực tế**.

## 2. Một sơ đồ tư duy trước khi đi vào code

```text
      Annotation / JPQL / EntityGraph / Repository API
                           |
                           v
                  Yêu cầu tải dữ liệu
                     (fetch plan)
                           |
                           v
                    JPA provider / ORM
                           |
             +-------------+--------------+
             |             |              |
             v             v              v
        JOIN FETCH    Secondary SELECT   Lazy proxy/
             |             |             collection
             |             |              |
             +-------------+--------------+
                           |
             Persistence context / L1 cache
                           |
                    Shared L2 cache?
                           |
                           v
                  JDBC / database SQL
                           |
                           v
            Kết quả thật trong transaction
                           |
              +------------+------------+
              |                         |
              v                         v
       Ứng dụng đọc getter        Ứng dụng không đọc
         / serialize DTO          association còn lazy
              |
              v
       Có thể phát sinh SQL
       tiếp theo trong lúc đọc
```

Sơ đồ cho thấy cùng một fetch plan có thể được provider thực hiện bằng nhiều chiến lược, còn thời điểm ứng dụng **chạm vào dữ liệu lazy** quyết định liệu các SQL tiếp theo có xảy ra không.

Ta không đoán số SQL bằng cách chỉ đọc annotation. Ta cần quan sát **một đoạn xử lý hoàn chỉnh**, từ lúc query chạy cho đến khi dữ liệu cần dùng đã được truy cập.

## 3. Mô hình dữ liệu ví dụ

Giả sử hệ thống bán hàng có bốn entity:

```text
Customer 1 -------- N PurchaseOrder 1 -------- N OrderLine
                          |                           |
                          |                           N
                          |                           |
                          |                           1
                          |                         Product
                          |
                        status
                        placedAt
```

Mục tiêu nghiệp vụ:

- Trang danh sách hiển thị mã đơn, trạng thái và tên khách hàng.
- Trang chi tiết hiển thị đơn hàng, các dòng hàng và tên sản phẩm.
- Báo cáo chỉ hiển thị số lượng đơn của mỗi khách.
- Job tính số câu SQL khi tải 20 đơn hàng.

### 3.1. Customer

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_name", nullable = false)
    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public List<PurchaseOrder> getOrders() { return orders; }
}
```

### 3.2. PurchaseOrder

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String code;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getCode() { return code; }
    public OrderStatus getStatus() { return status; }
    public Instant getPlacedAt() { return placedAt; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }
}
```

### 3.3. OrderLine và Product

```java
package com.example.shop.domain;

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

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public int getQuantity() { return quantity; }
    public Product getProduct() { return product; }
}
```

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "product_name", nullable = false)
    private String name;

    protected Product() {}

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
```

Enum:

```java
package com.example.shop.domain;

public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

### 3.4. Vì sao ví dụ đặt LAZY tường minh?

Theo mặc định JPA:

| Quan hệ | Default `fetch` | Ghi chú |
|---|---|---|
| `@ManyToOne` | `EAGER` | Có thể dẫn tới tải target ngoài ý định |
| `@OneToOne` | `EAGER` | Tùy hướng quan hệ và khả năng proxy |
| `@OneToMany` | `LAZY` | Thường là collection proxy/wrapper |
| `@ManyToMany` | `LAZY` | Tương tự collection |
| `@Basic` | `EAGER` | `LAZY` với basic có thể cần enhancement/provider support |

Trong mô hình này, các quan hệ được ghi `LAZY` rõ ràng để tiện quan sát. Đây **không phải lời hứa sẽ không bao giờ có SQL bổ sung**. LAZY nghĩa là ORM có thể trì hoãn tải dữ liệu; khi ứng dụng truy cập, SQL vẫn có thể được gửi.

### 3.5. Tập dữ liệu minh họa

Giả sử có:

- 10 Order với 10 Customer **khác nhau**.
- Mỗi Order có 3 OrderLine.
- Mỗi Line có một Product; một số Line có thể cùng Product.
- Mọi association chưa được tải trong persistence context.
- Đang đọc primary database; trước mắt bỏ qua L2 cache.

Đây là tình huống để suy luận các mô hình `1 + N`, `1 + U` và một JOIN cho nhiều hàng. Những con số trong bài chỉ là **dự đoán theo điều kiện thí nghiệm**, không phải cam kết cố định của mọi provider.

## 4. Phân biệt ba khái niệm: fetch plan, query và SQL statement

### 4.1. Fetch plan

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Đây là một phần của **kế hoạch tải mặc định** ở mapping. Nó cho biết provider **có thể trì hoãn** việc lấy trạng thái của Customer cho tới khi ứng dụng cần.

Hoặc:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.customer
WHERE o.status = :status
```

Đây là một fetch plan **theo query**, yêu cầu tải Customer cùng việc trả Order.

### 4.2. Lời gọi query ở Java

```java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();
```

Đoạn code là **một lời gọi truy vấn JPA**. Nó có thể tạo một SQL SELECT chính, nhưng các quan hệ EAGER hoặc lazy access tiếp theo có thể tạo thêm SQL.

### 4.3. SQL statements thực thi

Một trace có thể trông như sau:

```sql
SELECT o.id, o.order_code, o.customer_id, o.status, o.placed_at
FROM purchase_orders o;

SELECT c.id, c.customer_name
FROM customers c
WHERE c.id = ?;

SELECT c.id, c.customer_name
FROM customers c
WHERE c.id = ?;
```

Đó là **ba SQL SELECT** từ một query root và hai lần tải Customer ở một tình huống cụ thể. JPA provider có thể sinh alias, JOIN và SQL khác tùy mapping, database và fetch strategy.

**Không so số câu `createQuery` trong source code với số câu SELECT quan sát trên JDBC như thể chúng là cùng một đại lượng.**

### 4.4. Một SQL có thể trả nhiều hàng

```sql
SELECT o.*, l.*
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
WHERE o.id = ?;
```

Dù chỉ là **một SQL statement**, một Order có 100 Lines có thể tạo 100 hàng result set. Hibernate/JPA sẽ cần xử lý nhân bản dữ liệu Order ở các hàng.

Vì vậy các chỉ số cần phân biệt:

- Số SQL statements.
- Số database round-trips.
- Số hàng trả về.
- Số bytes truyền.
- Thời gian database thực thi.
- Thời gian hydrate entity.
- Số managed entities/collections.
- Bộ nhớ và thời gian serialization.

**Ít SQL không tự động đồng nghĩa ít chi phí hoặc nhanh hơn.**

## 5. EAGER và LAZY: yêu cầu tải không phải số câu SQL

### 5.1. EAGER là yêu cầu tải, không đồng nghĩa JOIN

Giả sử đổi mapping:

```java
@ManyToOne(fetch = FetchType.EAGER)
@JoinColumn(name = "customer_id")
private Customer customer;
```

`EAGER` nói rằng Customer phải sẵn sàng theo contract fetch eager của entity. Nhưng provider có thể đáp ứng bằng:

```sql
-- Phương án A: join ngay trong SQL tải Order.
SELECT o.*, c.*
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = ?;
```

hoặc:

```sql
-- Phương án B: SQL riêng để tải Order rồi Customer.
SELECT o.*
FROM purchase_orders o
WHERE o.id = ?;

SELECT c.*
FROM customers c
WHERE c.id = ?;
```

Hai ví dụ đều có thể phù hợp với yêu cầu tải Customer, nhưng **số câu SQL khác nhau**.

### 5.2. EAGER không thể được dùng làm cách tối ưu N+1 mặc định

Nếu query root trả 100 Order có Customer EAGER, provider có thể chọn query root rồi các SELECT bổ sung cho các Customer chưa có trong context. Trường hợp nhiều Customer riêng biệt có thể dẫn tới `1 + N`, dù annotation là EAGER.

Trong một số cấu hình, `EntityManager.find` theo khóa chính có thể dùng JOIN, còn JPQL `SELECT o FROM PurchaseOrder o` có thể dùng secondary selects để đáp ứng association EAGER. Vì vậy không chuyển `LAZY` thành `EAGER` chỉ để “giảm số query”.

### 5.3. LAZY không đồng nghĩa không có SQL

```java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();

for (PurchaseOrder o : orders) {
    System.out.println(o.getCustomer().getName());
}
```

Nếu `customer` LAZY, việc gọi `getCustomer().getName()` thường buộc ORM tải trạng thái Customer cho những identity chưa có sẵn. Khi có N Customer riêng và chưa có cache, có thể xuất hiện N secondary SELECT.

### 5.4. LAZY là một hint/khả năng, không phải tuyệt đối

Đối với nhiều mapping, `FetchType.LAZY` được chuẩn diễn đạt như một gợi ý; provider được phép tải sớm. Khả năng trì hoãn thực tế còn phụ thuộc:

- Proxy và bytecode enhancement.
- Kiểu association và phía owning/inverse.
- Fetch plan hiệu lực của query.
- Provider/version.
- Những entity đã được materialize.
- Graph, custom fetch mode và cache.

Do đó **không nên viết test kiểu “LAZY phải luôn sinh chính xác hai SELECT”** cho mọi môi trường.

### 5.5. Đọc giá trị identifier khác với đọc thuộc tính khác

Một proxy cho Customer có thể biết `id` qua foreign key của Order, nên `getCustomer().getId()` đôi khi không phải truy vấn DB. Nhưng `getCustomer().getName()` thường cần state của Customer.

Không dựa vào hành vi getter ID này như một bảo đảm portable: proxy, enhancement, composite ID và provider có thể xử lý khác.

## 6. Một phương thức `find`, nhiều biến thể SQL

### 6.1. Context trống, chỉ tải Order

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 101L);
```

Với Customer/Lines LAZY, context trống và cache chưa có, provider thường có thể tải Order bằng một SELECT. Nhưng đó là **một kịch bản**, không phải định nghĩa của `find`.

### 6.2. Context đã có Order

```java
PurchaseOrder a =
    em.find(PurchaseOrder.class, 101L);

PurchaseOrder b =
    em.find(PurchaseOrder.class, 101L);

System.out.println(a == b); // true trong cùng context.
```

Lần `find` thứ hai thường lấy từ L1 identity map, không cần thêm SELECT cho Order. Kết quả quan sát có thể là:

```text
find lần 1: 1 SELECT
find lần 2: 0 SELECT thêm
```

Đây là ví dụ cho thấy **cùng API, cùng fetch mapping, nhưng số SQL thay đổi theo trạng thái context**.

### 6.3. Context mới nhưng L2 cache có dữ liệu

Nếu shared second-level cache được bật và Product/Order được cache hợp lệ, một `find` trong context mới cũng có thể không cần query DB cho entity gốc.

Không kết luận rằng `em.clear()` rồi `find` sẽ bắt buộc tạo một SQL SELECT: `clear` xóa L1, không nhất thiết bỏ qua L2.

### 6.4. Một `find` có graph

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    101L,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
```

Cần import `jakarta.persistence.EntityGraph` và `java.util.Map`. Graph yêu cầu Customer trong kế hoạch tải. Nó **không hứa** rằng provider chỉ thực thi một SQL; provider có thể dùng join hoặc các SELECT phù hợp để materialize graph.

### 6.5. Kết luận cho find

Khi đo, cần ghi lại:

- EntityManager có mới hay không?
- Entity gốc đã managed chưa?
- Association target có sẵn trong L1 không?
- Shared cache có bật không?
- Có entity graph/hint không?
- Các getter nào được gọi **sau find**?
- SQL logger thu thập ở đoạn nào?

Không có câu trả lời đúng về số SQL nếu thiếu các điều kiện này.

## 7. JPQL `JOIN FETCH`: yêu cầu tải trong cùng truy vấn

### 7.1. Tải Order cùng Customer

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.status = :status
ORDER BY o.id
```

Code:

```java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "JOIN FETCH o.customer " +
        "WHERE o.status = :status " +
        "ORDER BY o.id",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
```

Câu này yêu cầu fetch Customer trong query root. Nếu mapping đơn giản và không có quan hệ EAGER khác cần tải riêng, provider thường có thể dùng một SQL với JOIN.

### 7.2. INNER và LEFT FETCH JOIN

```jpql
JOIN FETCH o.customer
```

tương đương ý định **inner fetch join**: nếu association optional và thiếu target phù hợp, root có thể bị loại.

```jpql
LEFT JOIN FETCH o.customer
```

giữ root kể cả khi association không có giá trị, theo semantics left join. Trong entity mẫu `customer optional=false`, hai câu thường cùng tập Order hợp lệ; nhưng ở các quan hệ optional, lựa chọn join có thể thay đổi kết quả root.

### 7.3. Fetch join không phải phép lọc child một cách tùy tiện

```jpql
SELECT o FROM PurchaseOrder o
JOIN FETCH o.lines
```

mục tiêu là tải collection `lines`. Trong JPQL portable, fetch join không được dùng như một ordinary join alias để tùy tiện lọc các phần tử rồi tuyên bố collection đã hoàn chỉnh. Với điều kiện trên child, có thể dùng một join riêng hoặc query khác tùy use case.

Ví dụ lọc Order có ít nhất một Line quantity lớn:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.quantity >= :minimum
)
```

Nếu cần đồng thời hiển thị toàn bộ Lines, thiết kế một bước fetch riêng hoặc graph phù hợp. **Filtering và fetching là hai trách nhiệm khác nhau.**

### 7.4. JOIN FETCH không bảo đảm một SQL cho mọi nhu cầu

Giả sử query fetch Customer nhưng code tiếp tục truy cập `o.getLines()` của từng Order. Collection `lines` vẫn LAZY nếu không được fetch:

```java
for (PurchaseOrder o : orders) {
    System.out.println(o.getCustomer().getName());
    System.out.println(o.getLines().size());
}
```

SQL root có thể đã fetch Customer, nhưng mỗi collection Lines chưa khởi tạo vẫn có thể phát sinh SELECT. Do đó, phải xem **toàn bộ các association ứng dụng thực sự chạm tới**, không chỉ một JOIN FETCH trong JPQL.

## 8. To-many JOIN FETCH và hiện tượng nhân bản hàng

### 8.1. Một Order có nhiều Line

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

Nếu Order có ba Lines, SQL join có thể trả ba hàng:

```text
order_id | order_code | line_id
---------+------------+--------
101      | ORD-101    | 1001
101      | ORD-101    | 1002
101      | ORD-101    | 1003
```

Một câu SELECT chứa nhiều hàng trùng thông tin Order. JPA provider có thể hydrate một managed Order và gắn ba OrderLine vào collection, nhưng chi phí đọc rows vẫn tồn tại.

### 8.2. Cùng Order xuất hiện bao nhiêu lần trong List?

Với collection fetch join, semantics của duplicates ở result list có khác biệt giữa phiên bản JPA/provider. Một cách diễn đạt JPQL thường dùng để tránh bản sao root là:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.id
```

Trong một số phiên bản Hibernate hiện đại, các root duplicates do join fetch có thể được loại trong quá trình materialization; tuy vậy không nên lấy hành vi cụ thể đó làm lý do bỏ qua **multiplicity của SQL rows**.

### 8.3. DISTINCT không xóa chi phí join

`SELECT DISTINCT o` ở mức JPQL hoặc SQL có thể giúp kiểm soát trùng root, nhưng **database vẫn cần tạo/đọc dữ liệu tương ứng với các Line** để ORM khởi tạo collection.

Nếu Order có 100 Lines, SQL tải chung có thể truyền nhiều lần cột Order. Không được kết luận “JOIN FETCH một SQL chắc chắn rẻ hơn SELECT Order rồi SELECT Lines”.

### 8.4. Fetch nhiều collection có thể phình nở

Giả sử Order có:

- 5 Lines.
- 4 PaymentRecords.

Nếu fetch join hai collection cùng lúc:

```text
5 lines × 4 payments = 20 hàng SQL cho một Order
```

Hàng result set có thể tăng theo tích số phần tử các collection. Đây là dạng *Cartesian multiplication* dù các JOIN đều có điều kiện quan hệ hợp lệ.

Một số ORM/provider còn có giới hạn khi fetch đồng thời nhiều bag collections. Ví dụ Hibernate có thể ném lỗi `MultipleBagFetchException` trong các cấu hình nhất định; đây là hành vi đặc thù Hibernate, không phải một exception portable của JPA.

### 8.5. Quyết định phù hợp

- Fetch một collection nhỏ ở trang chi tiết có thể hợp lý.
- Với nhiều collection lớn, cân nhắc tải có chọn lọc bằng các truy vấn riêng.
- Nếu chỉ cần số Lines, dùng aggregate/projection thay vì fetch toàn bộ.
- Nếu cần báo cáo, DTO thường phù hợp hơn entity graph sâu.
- Hãy đo **rows/bytes/latency**, không chỉ đếm SELECT.

## 9. N+1: một query danh sách và nhiều query theo từng root

### 9.1. Kịch bản đơn giản

```java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Nếu có N Order, mỗi Lines collection còn lazy và chưa initialized, provider có thể thực thi:

```text
1 SELECT lấy N Order
N SELECT lấy Lines của từng Order
--------------------------------
N + 1 SELECT
```

Với N = 10, một mô hình thường gặp là 11 SELECT.

### 9.2. N+1 là mô hình hành vi, không phải định luật cố định

Số SELECT thực tế có thể thấp hơn nếu:

- Một số collection đã initialized trong L1.
- Batch fetching gom nhiều collection vào một câu SQL.
- Provider dùng SUBSELECT fetch.
- Cache chứa các collection/associations liên quan.
- Code không truy cập hết các collection.
- Query root đã fetch collection bằng một kế hoạch khác.

N+1 mô tả nguy cơ **số lần tải child tăng theo N**, không khẳng định mỗi lần chạy đoạn code sẽ có đúng N+1 câu.

### 9.3. Một ví dụ đối với to-one

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder o : orders) {
    System.out.println(o.getCustomer().getName());
}
```

Nếu 10 Order thuộc 10 Customer khác nhau, có thể là 1 SELECT root + 10 SELECT Customer. Nhưng nếu cả 10 Order đều thuộc **cùng một Customer**, L1 identity map có thể khiến chỉ cần **một** secondary SELECT cho Customer đó.

Thay vì luôn ghi `1 + N`, đôi khi nên mô tả số SQL theo **U = số distinct association targets chưa có trong context**:

```text
1 SELECT Order + tối đa U SELECT Customer theo kiểu lazy từng target
```

Cấu hình provider và cache vẫn có thể thay đổi con số này.

### 9.4. N+1 có thể ẩn trong serializer

```java
return orderRepository.findAll();
```

Nếu controller trả entity trực tiếp cho JSON serializer, Jackson hoặc framework khác có thể gọi getter của `customer` hoặc `lines` sau lúc repository trả về.

Lúc query chạy, log mới có một SELECT. Đến lúc serialize, các association bị truy cập và thêm SQL được phát sinh.

Nếu persistence context còn mở, điều này có thể tạo N+1 không thấy trong đoạn repository. Nếu context đã đóng, nó có thể gây lazy initialization error thay vì SELECT.

**Đo đến lúc output được tạo xong**, không chỉ kết thúc `getResultList()`.

## 10. Thời điểm SQL chạy quan trọng như số lượng

### 10.1. LAZY và hai thời điểm khác nhau

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 101L);

// Thời điểm A.
String code = order.getCode();

// Thời điểm B.
int lineCount = order.getLines().size();
```

Nếu Lines chưa initialized:

- Ở A, đọc `code` có thể không gây SQL thêm.
- Ở B, gọi `size()` có thể kích hoạt SELECT collection.

Tùy provider/collection optimization, một phép `size()` đôi khi có thể dùng cơ chế đếm riêng mà không hydrate toàn bộ collection, nhưng không được mặc định hành vi đó là portable JPA.

### 10.2. Query đã chạy không đồng nghĩa toàn bộ graph đã loaded

```java
List<PurchaseOrder> orders =
    em.createQuery("SELECT o FROM PurchaseOrder o",
            PurchaseOrder.class)
      .getResultList();
```

Sau dòng này, có thể mới chỉ hoàn tất các yêu cầu eager thực tế của query. Những association lazy chưa truy cập vẫn có thể chờ.

### 10.3. Transaction boundary

```java
PurchaseOrder order = loadOrder();

em.close();

order.getLines().size();
```

Nếu collection chưa được khởi tạo, provider có thể ném lỗi lazy initialization vì entity/context đã detached/closed. Đây không phải dấu hiệu rằng số SQL đã được tối ưu thành 0; nó là **không còn context để thực hiện tải lazy**.

Một giải pháp đúng là chủ động fetch/projection các dữ liệu cần dùng **trước khi kết thúc transaction**.

### 10.4. Open Session in View

Một số ứng dụng Spring/Hibernate bật cơ chế giữ persistence context mở qua tầng web, thường được gọi là *Open Session in View*. Điều này có thể cho phép serializer kích hoạt lazy SELECT ngoài transaction nghiệp vụ chính.

Nó không tự tối ưu N+1 và có thể che khuất query phát sinh ở controller/view. Cần quyết định rõ chính sách transaction và fetch plan của application, thay vì phụ thuộc mặc định của framework.

## 11. EntityGraph: chỉ định thuộc tính cần tải

### 11.1. Tạo graph động

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o WHERE o.status = :status",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getResultList();
```

Graph yêu cầu Customer theo fetch plan của query. Dù thường có thể được thực hiện bằng JOIN, **graph không bảo đảm một số SELECT cụ thể**.

### 11.2. `fetchgraph` và `loadgraph`

Hai hint chuẩn:

```java
"jakarta.persistence.fetchgraph"
"jakarta.persistence.loadgraph"
```

Khác biệt khái quát:

- **Fetch graph:** những thuộc tính được nêu trong graph được yêu cầu tải eager; thuộc tính không nêu được xử lý theo semantics fetch graph, về cơ bản là lazy.
- **Load graph:** thuộc tính trong graph được yêu cầu tải eager; thuộc tính không nêu vẫn theo fetch type mặc định hoặc mapping.
- JPA provider có thể tải **thêm trạng thái** so với các thuộc tính yêu cầu, nên không coi graph là lời cam kết SQL/column tối thiểu tuyệt đối.

Điều này đặc biệt quan trọng khi entity có association `EAGER` mặc định: loadgraph không phải công cụ để ẩn chúng. Fetchgraph có thể thể hiện nhu cầu tải chặt hơn, nhưng hành vi thực tế vẫn cần xác minh theo provider.

### 11.3. Graph có collection

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer", "lines");
```

Kế hoạch này yêu cầu Customer và Lines. Provider có thể dùng join, secondary select hoặc các chiến lược thích hợp. Nếu Lines có rất nhiều phần tử, graph sâu có thể tốn dữ liệu hơn nhu cầu màn hình.

### 11.4. Subgraph cho Product của Line

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<OrderLine> linesGraph =
    graph.addSubgraph("lines", OrderLine.class);

linesGraph.addAttributeNodes("product");
```

Cần import `jakarta.persistence.Subgraph`. Graph biểu diễn ý định:

```text
PurchaseOrder
   |
   +-- lines
        |
        +-- product
```

Nó không biến `lines` thành một collection bằng DTO hay luôn ép ORM chạy một SQL ba bảng. Số statement còn phụ thuộc implementation, cache và các association khác.

### 11.5. Named entity graph

Có thể khai báo một plan có tên trên entity:

```java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
@Entity
public class PurchaseOrder {
    // ... fields như mô hình trên ...
}
```

Sau đó:

```java
EntityGraph<?> graph =
    em.getEntityGraph("PurchaseOrder.withCustomer");

List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).setHint("jakarta.persistence.loadgraph", graph)
 .getResultList();
```

Named graph giúp **tái sử dụng ý định tải**, không chứng minh SQL thực thi của mọi repository/query sử dụng graph giống nhau.

## 12. Fetch plan tĩnh và fetch plan theo từng use case

### 12.1. Khó khăn của EAGER ở mapping

Nếu khai báo:

```java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
```

nhiều use case chỉ cần Order ID cũng bị ràng buộc bởi nhu cầu eager ở mapping, trừ khi dùng cách ghi đè/điều chỉnh hiệu lực được provider hỗ trợ theo JPA.

Ví dụ API chỉ cần:

```json
{"orderId": 101, "status": "PAID"}
```

Nếu query trả entity PurchaseOrder, provider vẫn có thể phải xử lý eager associations dù response không dùng Customer.

### 12.2. Định hướng mặc định

Một thiết kế phổ biến là:

- Cân nhắc `LAZY` cho những association có thể trì hoãn.
- Khai báo fetch plan ở nơi biết nhu cầu cụ thể: query, graph, projection.
- Không fetch tất cả collection mặc định.
- Không trả entity graph sâu trực tiếp ra API khi DTO đủ dùng.
- Dùng benchmark/trace xác định strategy thực thi thực tế.

Đây là **nguyên tắc thiết kế**, không phải yêu cầu mọi ứng dụng phải đánh dấu mọi association là LAZY. Một số entity nhỏ và quan hệ luôn cần dùng có thể có lý do cho EAGER.

### 12.3. Tối ưu theo màn hình

| Use case | Dữ liệu cần | Phương án thường cân nhắc |
|---|---|---|
| Danh sách Order | ID, code, status, tên Customer | DTO projection hoặc fetch to-one Customer |
| Chi tiết Order | Order, Lines, tên Product | Graph/fetch join có giới hạn hoặc 2 bước |
| Báo cáo Order theo tháng | Count/SUM, nhóm theo kỳ | Aggregate DTO; không fetch graph |
| Job archive Order cũ | ID và status | Bulk DML nếu không cần callback/lifecycle |
| Form sửa Order | Managed Order và quan hệ cần thiết | Entity fetch plan theo thao tác ghi |

**Kế hoạch tải là công cụ đáp ứng dữ liệu mà use case cần, không phải một cuộc thi giảm SQL xuống 1.**

## 13. Projection DTO: có thể loại nhu cầu tải entity graph

### 13.1. Danh sách chỉ cần vài cột

Nếu trang danh sách cần code và Customer name, không nhất thiết tải toàn bộ PurchaseOrder và Customer entity.

```java
package com.example.shop.readmodel;

public record OrderRow(
    Long id,
    String code,
    String customerName
) {}
```

JPQL constructor projection:

```jpql
SELECT new com.example.shop.readmodel.OrderRow(
    o.id, o.code, c.name
)
FROM PurchaseOrder o
JOIN o.customer c
ORDER BY o.id
```

JPA trả DTO gồm các trường được chọn. Không cần tạo managed Order và Customer đầy đủ chỉ để đọc hai chuỗi và một ID.

### 13.2. Vì sao DTO giúp tránh N+1 của view?

```java
List<OrderRow> rows = em.createQuery(
        "SELECT new com.example.shop.readmodel.OrderRow(" +
        "o.id, o.code, c.name) " +
        "FROM PurchaseOrder o JOIN o.customer c " +
        "ORDER BY o.id",
        OrderRow.class
    )
    .getResultList();
```

Controller chỉ serialize `OrderRow` có các giá trị thuần, không có lazy association để vô tình truy cập sau đó.

Điều này không bảo đảm query luôn nhanh, nhưng làm **ranh giới dữ liệu được tải** rõ ràng.

### 13.3. Projection cũng có thể tạo SQL phức tạp

Nếu DTO cần 20 field, nhiều aggregate và join, database vẫn phải xử lý. Projection giảm việc materialize entity không cần thiết, nhưng hiệu năng còn phụ thuộc SQL và indexes.

### 13.4. DTO không trở thành managed entity

`OrderRow` là object kết quả độc lập:

- Không được `EntityManager.contains` quản lý như entity.
- Sửa DTO không tự flush vào DB.
- Phù hợp API read model.

Đừng dùng DTO projection rồi kỳ vọng callback, cascade và dirty checking giống entity.

## 14. Batch fetching: nhiều lazy loads có thể gom thành ít SQL

### 14.1. Vấn đề ban đầu

Có 40 Order, mỗi Order có collection Lines chưa initialized. Một cấu hình tải từng collection có thể tạo:

```text
1 SELECT Orders
40 SELECT Lines
```

### 14.2. Hibernate `@BatchSize`

Một cấu hình đặc thù Hibernate:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 20)
private List<OrderLine> lines = new ArrayList<>();
```

Khi truy cập một collection, Hibernate có thể gom việc tải các collections pending của nhiều Order theo batch:

```sql
SELECT l.*
FROM order_lines l
WHERE l.order_id IN (?, ?, ?, ...);
```

Mục đích là giảm số SELECT thứ cấp. Trong một thí nghiệm 40 Order, batch size 20 có thể tạo cỡ vài SELECT tải Lines thay vì 40, nhưng **không có công thức portable “chính xác = ceil(N / 20)”**: thứ tự access, cache, batch algorithm, batch style, giới hạn parameter và trạng thái context đều ảnh hưởng.

### 14.3. Batch fetching không phải JPQL chuẩn

`@BatchSize` là annotation riêng của Hibernate, không phải `jakarta.persistence`. Một provider khác có thể có phương án batching khác hoặc không có tính năng tương đương.

Dùng annotation này cần ghi nhận dependency, version và kiểm thử trên môi trường thực.

### 14.4. Batch size lớn không luôn tốt hơn

Với batch quá lớn:

- Câu SQL có nhiều bind parameters.
- DB có thể có giới hạn tham số hoặc kích thước `IN`.
- Tập kết quả lớn có thể gây tốn bộ nhớ.
- Nhiều collection không được sử dụng vẫn có thể bị tải trước.

Chọn batch size dựa trên workload và số associations được truy cập, không đơn thuần lấy số lớn nhất cho phép.

### 14.5. Batch fetching cho to-one

Hibernate còn có thể batch-load các proxy của Customer/Product khi chúng được truy cập. Từ đó, một lần gọi `getCustomer().getName()` có thể kéo thêm một số Customer khác mà context đang giữ proxy chưa initialized.

Do vậy số SQL quan sát không nhất thiết bằng số getter được gọi.

## 15. Subselect fetching: một chiến lược khác

### 15.1. Ý tưởng

Thay vì dùng nhiều `SELECT ... WHERE order_id = ?`, một ORM có thể nạp collections cho một nhóm Order bằng một truy vấn con tham chiếu tập Order đã tải:

```sql
SELECT l.*
FROM order_lines l
WHERE l.order_id IN (
    SELECT o.id
    FROM purchase_orders o
    WHERE o.status = ?
);
```

Đây là SQL minh họa, không phải câu SQL Hibernate bắt buộc sinh nguyên văn.

### 15.2. Hibernate `@Fetch(SUBSELECT)`

Một lựa chọn đặc thù Hibernate:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@org.hibernate.annotations.Fetch(
    org.hibernate.annotations.FetchMode.SUBSELECT
)
private List<OrderLine> lines = new ArrayList<>();
```

Khi một collection được truy cập, Hibernate có thể tải các collection liên quan của tập parent đã được query trước đó bằng subselect.

### 15.3. Khi nào cần thận trọng?

Subselect fetching có thể có lợi khi một trang/nhóm parent đều cần collection, nhưng cũng có nguy cơ kéo nhiều child không thật sự cần hoặc dựa trên tập parent khác dự đoán.

Nó **không phải tính năng chuẩn JPA** và không tương đương một câu `JOIN FETCH`. Nên xác minh SQL/rows/transaction scope và quan sát query count dưới dữ liệu thực.

### 15.4. So sánh các chiến lược

| Chiến lược | Dấu hiệu phổ biến | Đánh đổi |
|---|---|---|
| Lazy từng association | N secondary SELECT | Đơn giản, có N+1 risk |
| JOIN FETCH | Một SQL có JOIN nhiều bảng | Có thể nhân bản hàng/cartesian multiplication |
| Batch fetch | `WHERE id IN (...)` | Ít SELECT hơn nhưng cần batching config |
| Subselect fetch | Secondary SELECT dựa trên tập parents | Có thể tải nhiều collection theo nhóm |
| DTO projection | SELECT đúng các field/cột cần | Không có managed entity graph |
| L2 cache | Một số load không cần DB | Cache invalidation và freshness |

Bảng là các **mô hình thường gặp**, không phải quy tắc số SQL bất biến.

## 16. Phân trang và collection fetch join

### 16.1. Vấn đề

```java
List<PurchaseOrder> page = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "ORDER BY o.id",
        PurchaseOrder.class
    )
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Một Order có thể tạo nhiều hàng SQL do join với Lines. Nếu database áp dụng `LIMIT 20` trên các hàng join, tập Order root có thể bị cắt dở collection hoặc không đủ 20 Order.

### 16.2. Hành vi provider

Một số provider có thể:

- Phân trang trong bộ nhớ thay vì đẩy giới hạn xuống SQL khi fetch collection.
- Cảnh báo hoặc ném lỗi ở cấu hình nghiêm ngặt.
- Có chiến lược riêng tùy query/provider.

Ví dụ Hibernate có cấu hình liên quan đến việc fail khi phân trang trên collection fetch join. Không nên dựa vào một kế hoạch “một SQL + LIMIT 20” như điều chắc chắn.

### 16.3. Giải pháp hai bước

**Bước 1:** lấy IDs của đúng 20 Order root cần hiển thị:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.placedAt DESC, o.id DESC
```

Áp dụng `setFirstResult`/`setMaxResults` ở bước này.

**Bước 2:** fetch dữ liệu cần thiết theo ID:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Trong code, giữ `ids` và sắp kết quả về đúng thứ tự trang theo danh sách ID, vì `IN :ids` **không bảo toàn thứ tự đầu vào**.

### 16.4. Hai SQL có thể tốt hơn một SQL

Hai bước có thể tạo **ít nhất hai SELECT chính**, nhiều hơn một câu SQL root ở ví dụ đơn giản. Nhưng nó cho phép:

- Phân trang root đúng.
- Chỉ tải collections cho các Order trong trang.
- Tránh in-memory pagination trên tập join rất lớn.
- Kiểm soát số Order trả về.

Nếu có EAGER associations hoặc lazy accesses khác, vẫn có thể xuất hiện SQL bổ sung. **Đúng semantics và chi phí tổng thể quan trọng hơn mục tiêu “một câu SQL”.**

### 16.5. Offset và dữ liệu thay đổi

Phân trang hai bước cũng cần cân nhắc dữ liệu thay đổi giữa các query và giữa các trang. Với báo cáo hay feed biến động, keyset pagination/snapshot phù hợp có thể cần thiết; không chỉ chọn fetch plan là đủ.

## 17. Caching: SQL thực thi còn tùy dữ liệu đã có sẵn

### 17.1. L1 cache / persistence context

```java
PurchaseOrder one =
    em.find(PurchaseOrder.class, 101L);

PurchaseOrder two =
    em.find(PurchaseOrder.class, 101L);
```

Trong cùng context, `one == two` thường true. Lần thứ hai không nhất thiết truy vấn DB, vì root đã managed.

### 17.2. L2/shared cache

JPA cho phép shared cache với cách cấu hình tùy provider. Một context mới có thể lấy entity từ shared cache khi policy cho phép. Từ đó:

```text
Một lời find có thể:
  -> SELECT database
  -> hoặc cache hit, không SELECT cho root
```

Để đánh giá số câu SQL của fetch plan riêng, cần kiểm soát cache, nếu không các phép đo có thể khác theo lần chạy.

### 17.3. Query cache

Một số provider có query result cache riêng. Đây không phải tính năng portable mặc định của mọi JPA provider. Một câu JPQL có thể dùng kết quả cache nếu được cấu hình, làm số SELECT giảm.

Tuy nhiên, cache hit không có nghĩa tập entity/associations đều đã initialized; provider còn có thể phải nạp state của những entity/cache misses.

### 17.4. Clear L1 không xóa L2

```java
em.clear();
```

Lệnh này detach entities trong context hiện tại; không đồng nghĩa shared cache của `EntityManagerFactory` đã được xóa.

JPA cache API:

```java
emf.getCache().evictAll();
```

có thể được dùng trong thí nghiệm có kiểm soát để loại cache entries, nếu provider hỗ trợ cache. Không nên đưa `evictAll()` vào production mỗi khi cần đo hoặc tối ưu query.

### 17.5. Cache bypass khi cần kiểm tra

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    101L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
```

Cần import `jakarta.persistence.CacheRetrieveMode`. Hint bypass shared cache; nó không biến một entity **đã managed trong L1** thành entity chưa từng được tải. Muốn bảo đảm đối tượng đọc mới, cần context mới hoặc refresh, và phân biệt transaction snapshot.

### 17.6. Đừng dùng cache “làm đẹp” N+1

Nếu app chỉ nhanh ở lần thứ hai vì shared cache đã nóng, cold-start hoặc các khóa ít truy cập vẫn có thể N+1 nghiêm trọng.

Khi đo, nên tách kết quả:

- Cold context/cold cache.
- Warm L1.
- Warm L2/query cache.
- Các request thực tế có phân bố cache hit.

**Cache có thể che biểu hiện N+1, nhưng không sửa cấu trúc truy cập không phù hợp.**

## 18. Dirty checking và flush cũng tạo SQL bên ngoài fetch plan

### 18.1. Fetch plan chỉ nói về đọc

Nếu trong một transaction, ứng dụng sửa entity:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 101L);

// Giả sử entity có domain method thay đổi status.
order.changeStatus(OrderStatus.PAID);
```

sau đó thực hiện query, provider có thể flush các thay đổi pending trước khi SELECT tùy flush mode và consistency requirements.

Trace có thể có:

```sql
UPDATE purchase_orders
SET status = ?
WHERE id = ?;

SELECT o.*
FROM purchase_orders o
WHERE o.status = ?;
```

Nếu đếm **mọi SQL statements** trong transaction, UPDATE là một statement thực thi, dù nó không phải truy vấn fetch.

Ví dụ `changeStatus` giả định được bổ sung vào entity khi làm thí nghiệm; entity mẫu ban đầu chỉ hiển thị getters.

### 18.2. INSERT lấy generated IDs

Khi seed dữ liệu, `persist` có thể dẫn tới INSERT để lấy ID, tùy chiến lược sinh khóa. Nếu bắt đầu bộ đếm trước khi chuẩn bị fixture, số SQL quan sát sẽ chứa cả INSERT, sequence calls hoặc SELECT metadata không liên quan fetch plan.

Do đó khi so sánh các chiến lược tải, cần **chuẩn bị dữ liệu trước và cô lập cửa sổ đo**.

### 18.3. FlushModeType.AUTO và COMMIT

Các flush mode ảnh hưởng lúc nào ORM đồng bộ pending changes với database. Không cấu hình `COMMIT` chỉ để làm log ít SQL hơn nếu điều đó làm semantics đọc sau ghi sai yêu cầu.

Tương tự, gọi `em.flush()` thủ công tạo SQL UPDATE/INSERT cần thiết tại một thời điểm cụ thể, nhưng không bảo đảm mọi dữ liệu liên quan sẽ nằm trong cùng một SELECT.

### 18.4. Phải phân biệt đếm SELECT và đếm toàn bộ SQL

Một test có thể hỏi:

- “Có bao nhiêu **SELECT** do màn hình này kích hoạt?”
- “Có bao nhiêu **SQL statements** gồm INSERT/UPDATE/DELETE/SELECT?”
- “Có bao nhiêu **round-trips**?”
- “Có bao nhiêu **prepared statements** được tạo?”
- “Có bao nhiêu **JPA queries** được thực thi?”

Đây là các chỉ số khác nhau. Một statement có thể được prepare một lần nhưng execute nhiều lần với các tham số khác nhau; JDBC batching có thể làm số round-trip khác số logical updates.

## 19. Đo SQL thực tế bằng logging

### 19.1. Bật SQL logs khi phát triển

Với Hibernate 6 qua Spring Boot, một cấu hình thường dùng:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

`org.hibernate.SQL` ghi SQL statements do Hibernate tạo; `org.hibernate.orm.jdbc.bind` có thể hiển thị bind parameters trên Hibernate 6.

Cấu hình logger ở Hibernate 5 hoặc provider khác có thể khác. Cần đối chiếu phiên bản thực tế.

### 19.2. Lưu ý dữ liệu nhạy cảm

Bind logs có thể chứa dữ liệu cá nhân, identifier, dữ liệu nghiệp vụ nhạy cảm. Chỉ bật `TRACE` trong môi trường phát triển/kiểm thử có kiểm soát, ẩn dữ liệu cần bảo vệ, không vô tình ghi password/token hoặc thông tin khách hàng vào production logs.

### 19.3. Trích SQL trong một request

Một log giả định:

```text
Hibernate:
  select ... from purchase_orders ...
Hibernate:
  select ... from customers where id=?
Hibernate:
  select ... from customers where id=?
Hibernate:
  select ... from order_lines where order_id=?
```

Khi phân tích:

1. Xác định query root.
2. Nhóm các SELECT theo entity/association.
3. Kiểm tra WHERE khác nhau theo ID hay `IN` theo batch.
4. Xác định SQL xảy ra trong repository hay sau khi serializer đọc getter.
5. Kiểm tra có SELECT trùng hay không, và vì sao cache không phục vụ.
6. Gắn với request/transaction cụ thể, tránh lẫn logs của thread khác.

### 19.4. Log SQL không tự nói số hàng

SQL logger thường hiển thị **câu SQL**, không thể hiện tổng bytes và số hàng database đã trả trong mọi cấu hình.

Muốn so sánh JOIN FETCH vs nhiều SELECT ở mức chi phí thực, có thể cần database execution plan, driver metrics, datasource instrumentation hoặc profiler chuyên dụng.

### 19.5. SQL logging và actual execution

Một số logger ghi lúc chuẩn bị hoặc phát lệnh; việc quan sát chuẩn xác số lần **thực thi** nên dựa trên instrumentation ở tầng JDBC/DB khi cần độ chính xác cao. Không coi số dòng log là thước đo tuyệt đối nếu framework/provider có batching, reuse hoặc logging policy đặc thù.

## 20. Hibernate Statistics: quan sát có hệ thống

### 20.1. Bật statistics

Một cấu hình Hibernate:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Hoặc cấu hình Hibernate `hibernate.generate_statistics=true` theo cơ chế bootstrap của dự án.

### 20.2. Đọc từ SessionFactory

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics statistics =
    sessionFactory.getStatistics();

long before = statistics.getPrepareStatementCount();

List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder o : orders) {
    o.getCustomer().getName();
}

long after = statistics.getPrepareStatementCount();

System.out.println("Prepared statements delta = " +
    (after - before));
```

Cần import `jakarta.persistence.EntityManagerFactory` nếu dùng `emf` trong class.

### 20.3. Hiểu đúng tên metric

`getPrepareStatementCount()` đếm **các statement được chuẩn bị** theo thống kê của Hibernate. Đây là proxy hữu ích cho việc quan sát activity, nhưng **không đồng nghĩa tuyệt đối số lần execute trên DB** trong mọi trường hợp statement reuse/batching.

Một số metrics khác:

- `getEntityLoadCount()`: số lượt entity load theo định nghĩa của Hibernate.
- `getEntityFetchCount()`: số entity fetch theo định nghĩa statistics.
- `getCollectionFetchCount()`: số collection fetch.
- `getSecondLevelCacheHitCount()`: cache hit L2.
- `getQueryExecutionCount()`: các lần thực thi query được Hibernate thống kê theo phạm vi query statistics.

**`getQueryExecutionCount()` không phải tổng số SELECT SQL**: secondary SELECT tải association và entity load có thể không trùng với cách đếm query-level execution.

### 20.4. Khi nào cần reset counters?

`statistics.clear()` đặt lại counters để một test dễ quan sát, nhưng statistics gắn với `SessionFactory` và có thể được dùng bởi **nhiều thread/test**. Reset trong một test chạy song song có thể làm kết quả của test khác sai.

Trong integration test, nên:

- Chạy serial hoặc cô lập `SessionFactory`/dataset.
- Bắt đầu đo sau seed/flush/clear.
- Ghi lại baseline và delta.
- Giữ query plan và lượng data giống nhau giữa các phương án.
- Xem cả logs SQL thực tế khi cần biết statement nào được phát ra.

### 20.5. Statistics là đặc thù provider

`SessionFactory`, `Statistics` và `@BatchSize` là API Hibernate, **không phải Jakarta Persistence portable**. Nếu dự án dùng EclipseLink hoặc provider khác, cần chọn công cụ theo provider hoặc instrumentation độc lập ở tầng datasource.

## 21. Đếm ở tầng JDBC/DataSource

### 21.1. Vì sao cần instrumentation?

Nếu câu hỏi chính là **“Có bao nhiêu SQL SELECT thực sự được thực thi trong request?”**, bộ đếm ở tầng JDBC có thể phân biệt statement executions tốt hơn việc chỉ nhìn số lệnh `createQuery`.

Các lựa chọn thực tế bao gồm:

- DataSource proxy có khả năng đếm câu SQL/loại statement.
- P6Spy hoặc công cụ theo dõi JDBC phù hợp.
- APM/tracing instrument driver.
- Metrics phía database.
- Hibernate SQL logs kết hợp statistics.

Tên thư viện, phiên bản và API chi tiết phụ thuộc môi trường; đây không phải khả năng chuẩn do JPA `EntityManager` trực tiếp cung cấp.

### 21.2. Cần đo đúng khoảng thời gian

Quy trình cho một bài test:

```text
[Seed fixture và commit]
       |
[EntityManager mới; cache policy xác định]
       |
[Bắt đầu JDBC counter]
       |
[Chạy query root]
       |
[Truy cập chính xác getters mà use case cần]
       |
[Chuyển dữ liệu thành DTO / serialize nếu thuộc phạm vi]
       |
[Dừng counter]
       |
[Phân loại SELECT/INSERT/UPDATE/DELETE và báo cáo]
```

Nếu chỉ đếm ở dòng `getResultList()` nhưng UI tiếp tục đọc getter lazy sau đó, test sẽ bỏ sót những SELECT quan trọng.

### 21.3. Test đếm query là test của hành vi cụ thể

Ví dụ pseudocode theo một wrapper recorder giả định:

```java
// Pseudocode: SqlRecorder do dự án/test utility cung cấp.
sqlRecorder.reset();

List<OrderRow> rows =
    orderReadService.listPaidOrders();

long selects = sqlRecorder.selectExecutionCount();

assertTrue(selects <= expectedBudget);
```

`SqlRecorder` ở đây **không phải class chuẩn của JPA**. Một integration test thật cần cài đặt bằng datasource instrumentation thích hợp.

Một budget SQL hợp lý phải gắn với:

- Cấu hình mapping và provider/version.
- Số entity và association distinct.
- Cache state.
- Access pattern của service.
- Kiểu truy vấn (DTO/fetch).
- Ranh giới transaction.
- Mức ổn định mong muốn của bài test.

### 21.4. Đừng biến budget thành số kỳ vọng vô căn cứ

Một test `assertEquals(1, sqlCount)` có thể quá chặt nếu provider cần thêm query hợp lệ, hoặc quá lỏng nếu một JOIN tạo một triệu hàng. Nên kết hợp:

- Correctness của output.
- Giới hạn query growth khi N tăng.
- Latency/rows đo được.
- Giải thích rõ phạm vi đo.

Ví dụ, kiểm tra rằng số SELECT **không tăng tuyến tính theo số Order** có thể phản ánh mục tiêu chống N+1 tốt hơn một con số đúng duy nhất.

## 22. Bảng thí nghiệm: cùng use case, nhiều fetch plans

Giả sử cần hiển thị **10 Order, tên 10 Customer khác nhau và số Line của từng Order**. Ban đầu context/cache lạnh.

| Cách triển khai | Kế hoạch tải | SQL có thể quan sát | Cảnh báo |
|---|---|---|---|
| `SELECT o` rồi đọc Customer, Lines | Cả hai association LAZY | Root + loads cho Customer và Lines, có thể gần `1+10+10` | N+1 ở hai loại quan hệ |
| `JOIN FETCH o.customer` rồi đọc Lines | Customer join, Lines LAZY | Root có join + các SELECT Lines | Vẫn N+1 cho collection |
| `JOIN FETCH o.lines` rồi đọc Customer | Lines join, Customer LAZY | Root join + các SELECT Customer | Nhiều SQL rows do join Lines |
| EntityGraph customer + lines | Yêu cầu tải cả hai | Provider quyết định join/secondary | Không hứa đúng một SQL |
| Batch fetch Lines | Lines LAZY có batching | Root + vài SELECT batch Lines | Cần provider config |
| DTO cho code, name, count Lines | Không trả managed Order graph | Một query tổng hợp hoặc vài query được thiết kế | Query shape/aggregate khác |
| Two-step IDs + fetch | Paginate IDs rồi fetch collection | Ít nhất hai SELECT chính; có thể thêm | Đúng pagination root hơn |

**Các con số chỉ minh họa mô hình**. Với 10 Order thuộc 2 Customer, có cache hit, hoặc app chỉ đọc một số Lines, số SQL có thể khác rất nhiều. Từ đó, muốn trả lời “fetch plan nào tạo ít SQL hơn” phải cố định **dataset và access pattern** trước.

## 23. Một thí nghiệm thực tế từng bước

### 23.1. Chuẩn bị bộ dữ liệu

Tạo:

- 20 PurchaseOrder PAID.
- Mỗi Order có Customer riêng.
- Mỗi Order có 3 OrderLine.
- Mỗi Line có Product; ID Product có thể lặp.
- Commit fixture trước khi đo.

Mục tiêu màn hình: render `orderCode`, `customerName` và `lineCount`.

### 23.2. Phiên bản A: entity query và lazy access

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :paid ORDER BY o.id",
    PurchaseOrder.class
).setParameter("paid", OrderStatus.PAID)
 .getResultList();

List<String> output = new ArrayList<>();

for (PurchaseOrder o : orders) {
    output.add(
        o.getCode() + " | " +
        o.getCustomer().getName() + " | " +
        o.getLines().size()
    );
}
```

Cần import `java.util.ArrayList` và `java.util.List`.

Với provider tải từng association, có thể có root SELECT, nhiều Customer SELECT và nhiều Lines SELECT. Quan sát là cần thiết vì cache/batch có thể làm khác.

### 23.3. Phiên bản B: fetch join Customer

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "JOIN FETCH o.customer " +
    "WHERE o.status = :paid ORDER BY o.id",
    PurchaseOrder.class
).setParameter("paid", OrderStatus.PAID)
 .getResultList();
```

Dùng cùng logic render như A. So sánh:

- Số SELECT Customer.
- Số SELECT Lines.
- Thời gian query và render.
- Số Order/root rows.

Nếu Lines vẫn lazy, B chỉ giải quyết một phần access graph.

### 23.4. Phiên bản C: DTO projection

Định nghĩa:

```java
public record OrderListRow(
    Long id,
    String code,
    String customerName,
    Long lineCount
) {}
```

Truy vấn:

```jpql
SELECT new com.example.shop.readmodel.OrderListRow(
    o.id, o.code, c.name, COUNT(l.id)
)
FROM PurchaseOrder o
JOIN o.customer c
LEFT JOIN o.lines l
WHERE o.status = :paid
GROUP BY o.id, o.code, c.name
ORDER BY o.id
```

Query trả mỗi Order cùng số Line. Dữ liệu trả là DTO nên render không cần lazy-load Lines chỉ để tính size.

### 23.5. So sánh công bằng

Đo cả ba phiên bản trong điều kiện giống nhau:

1. Cùng 20 Orders và 3 Lines mỗi Order.
2. Cùng thuộc tính được hiển thị.
3. Cùng cache policy.
4. Mỗi phép đo dùng context mới.
5. Không để fixture inserts lọt vào counter.
6. Đo tới khi output đã tạo xong.
7. Quan sát SQL count, rows, latency, memory.
8. Không dùng kết quả run đầu của phương án A làm cache warm cho B nếu không có chủ đích.

**Một phương án có nhiều SELECT hơn vẫn có thể nhanh hơn trong một dataset; một JOIN lớn vẫn có thể tệ hơn nhiều batch nhỏ.**

## 24. SQL thực tế không phải lúc nào nhìn giống JPQL

### 24.1. SQL alias và JOIN

JPQL:

```jpql
SELECT o FROM PurchaseOrder o JOIN FETCH o.customer
```

SQL có thể có alias do provider tự đặt:

```sql
SELECT o1_.id, o1_.order_code, c1_.id, c1_.customer_name, ...
FROM purchase_orders o1_
JOIN customers c1_ ON c1_.id = o1_.customer_id;
```

Không dùng alias SQL cụ thể làm contract giữa các phiên bản provider.

### 24.2. Secondary SELECT cho eager association

JPQL không chứa JOIN FETCH nhưng entity mapping có EAGER. Provider vẫn phải đáp ứng yêu cầu eager; một số cấu hình thực hiện thêm secondary SELECT. Vì vậy chỉ nhìn JPQL thấy một `FROM` không đủ.

### 24.3. SQL để check FK/proxy/optional association

Một số provider có thể cần truy vấn bổ sung để biết association nullable/inverse side có tồn tại hay không, nhất là những mapping `@OneToOne` không sở hữu FK hoặc khi không có enhancement. Số statement có thể thay đổi theo kiểu mapping.

### 24.4. Inheritance

Entity dùng `JOINED` inheritance có thể cần join các bảng subclass hoặc truy vấn bổ sung theo cách provider. Không suy luận fetch SQL của một entity đơn giản là bất biến khi chuyển sang inheritance mapping.

### 24.5. Query hints

Hints như cache bypass, fetch size, graph và provider-specific fetch mode có thể ảnh hưởng plan, nhưng không có một hint chuẩn “chạy đúng một SELECT trong mọi tình huống”.

## 25. Truy vấn theo lô và đường truy cập tốt hơn cho danh sách

### 25.1. Đừng loop find từng ID nếu có thể query tập ID

Ví dụ:

```java
for (Long id : ids) {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, id);
    // ...
}
```

Với N ID chưa có trong context/cache, cách này có thể tạo N SELECT Order.

Nếu muốn một tập Order:

```java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.id IN :ids",
        PurchaseOrder.class
    )
    .setParameter("ids", ids)
    .getResultList();
```

Query tập ID có thể giảm số statement root, nhưng `IN :ids` rỗng cần xử lý ở service và kết quả **không bảo toàn thứ tự IDs đầu vào**.

### 25.2. Nhu cầu và dữ liệu là yếu tố quyết định

Nếu `ids` chỉ có một phần tử và entity đã cached, `em.find` có thể không gửi SELECT. Vì vậy `IN` không mặc định nhanh hơn trong mọi ngữ cảnh.

### 25.3. Chọn chiến lược cho một màn hình

- Nếu cần 20 parent cùng 1 to-one Customer: có thể dùng fetch join to-one hoặc DTO.
- Nếu cần 20 parent với vài to-many collection lớn: cân nhắc two-phase query hoặc batch fetching.
- Nếu chỉ cần số lượng child: aggregate projection thay vì fetch collection.
- Nếu cần chỉnh sửa một parent: managed entity theo command transaction.
- Nếu cần streaming khối lượng lớn: projection/batch và quản lý persistence context phù hợp.

## 26. Chẩn đoán các kết luận sai thường gặp

| Kết luận sai | Vì sao sai | Cách kiểm chứng hoặc sửa |
|---|---|---|
| “Một `createQuery` = một SQL.” | EAGER hoặc lazy access tạo secondary SELECT | Đo toàn bộ flow tới output |
| “EAGER luôn dùng JOIN.” | Provider có thể dùng secondary SELECT | Xem SQL thực tế |
| “LAZY luôn không tải quan hệ.” | Getter có thể kích hoạt SQL | Theo dõi access pattern |
| “LAZY luôn gây N+1.” | Join fetch, batch, cache, subselect có thể thay đổi | Kiểm tra configuration và SQL |
| “`find` luôn query DB.” | L1/L2 có thể trả entity | Thử context/cache lạnh và ấm |
| “`clear` bắt buộc mọi entity đọc từ DB.” | Shared L2 còn có thể phục vụ | Kiểm tra cache policy |
| “EntityGraph bảo đảm đúng một SELECT.” | Graph mô tả thuộc tính cần tải, không phải statement count | Đo provider/dataset |
| “Graph chỉ định một field sẽ cấm provider tải field khác.” | Provider có thể fetch thêm state | Hiểu fetchgraph/loadgraph semantics |
| “JOIN FETCH collection không có N+1 nên luôn nhanh.” | Có thể nhân bản hàng, chi phí rows/memory | So rows, bytes và latency |
| “DISTINCT loại hết chi phí join.” | Database vẫn xử lý nhiều child rows | Xem execution plan |
| “Một Order với nhiều Lines chỉ trả một SQL row.” | JOIN 1-n nhân bản cột parent | Quan sát result set |
| “Fetch hai collections vẫn chỉ tăng theo tổng số child.” | Có thể tăng theo tích kích thước collections | Xem cartesian multiplication |
| “Fetch join collection + pagination luôn đúng.” | SQL LIMIT có thể áp vào joined rows | Two-step ID pagination |
| “`getLines().size()` luôn là truy cập bộ nhớ.” | Lazy collection có thể phát SQL | Đo sau getter |
| “Cứ đặt EAGER cho mọi quan hệ để tối ưu.” | Tải thừa; secondary SELECT và N+1 | Chọn fetch theo use case |
| “Không thấy SQL trong repository là không có N+1.” | Serializer/view có thể đọc getter | Instrument hết request |
| “Hibernate queryExecutionCount = SQL count.” | Thống kê cấp query không tính mọi load như SQL | Xem prepared count/JDBC instrumentation |
| “Prepared count luôn bằng execute count.” | Prepare, reuse, batching khác nhau | Instrument actual JDBC executions |
| “Đếm 1 SELECT nghĩa là tốt.” | SELECT có thể trả hàng triệu rows | Đo rows, bytes, time |
| “DTO luôn nhanh hơn managed entity.” | Tùy SQL shape, index và data | Benchmark đúng workload |
| “Một test cold cache đại diện production.” | Cache hits và phân bố request thay đổi | Đo cold/warm và production metrics |
| “Transaction kết thúc sẽ load lazy association bình thường.” | Entity detached/context đóng có thể báo lỗi | Fetch/projection trước boundary |
| “SQL count thấp nghĩa không có vấn đề locking.” | Query có thể lock lâu hoặc chờ DB | Đo latency/lock/plan |
| “Cùng JPQL luôn sinh cùng SQL ở mọi DB.” | Provider/dialect/version/hints khác | Log trên DB mục tiêu |

## 27. Quy trình lựa chọn và kiểm chứng một fetch plan

### Bước 1 — Xác định output

Viết rõ UI/service cần field nào:

```text
Order list item:
  - order.id
  - order.code
  - order.status
  - customer.name
  - lineCount
```

Không chọn fetch graph trước khi hiểu output.

### Bước 2 — Xác định cardinality

Quan hệ:

- Order → Customer: to-one.
- Order → Lines: to-many.
- Line → Product: to-one.

To-many fetch join có nguy cơ nhân bản rows lớn; to-one join thường không có nhân bản kiểu 1-n nếu FK đúng.

### Bước 3 — Chọn query shape

Có thể là:

- Entity root + fetch join.
- Entity graph.
- Two-step fetch IDs/children.
- Batch/subselect lazy fetch.
- DTO projection với join/aggregate.

### Bước 4 — Chọn transaction boundary

Nên biết:

- Dữ liệu được render trong transaction hay ngoài?
- EntityManager có mở trong serializer không?
- Có extended context không?
- Có cache L2 không?

### Bước 5 — Thiết lập bộ đo

Đặt dataset đại diện, cache state rõ ràng, SQL logging/Statistics/JDBC counter và điểm bắt đầu-kết thúc.

### Bước 6 — Chạy toàn bộ flow

Đừng dừng phép đo ngay sau `getResultList` khi caller còn truy cập association.

### Bước 7 — So cả số SQL và chi phí dữ liệu

Ghi nhận:

```text
SQL SELECT count
SQL row count
JDBC/database latency
Hydration/serialization time
Heap/memory
Entity/collection loads
Cache hits/misses
```

### Bước 8 — Điều chỉnh tối thiểu cần thiết

Chỉ thay fetch plan/annotation theo nút thắt đã đo; không biến một endpoint ít dùng thành một graph EAGER lớn áp dụng cho toàn hệ thống.

### Bước 9 — Kiểm tra tính đúng đắn

Tối ưu không được làm thiếu child, sai pagination, trùng root hoặc để lazy exception. Đó là bài toán correctness độc lập với số SQL.

### Bước 10 — Theo dõi khi lên production

Các phép đo trong test không thay thế hoàn toàn workload production. Dữ liệu lớn, cache nóng và network latency thật có thể thay đổi cách so sánh.

## 28. Các bài thực hành

### Bài 1 — Một find và hai find

Tạo Order ID 101 và Customer tương ứng. Trong cùng EntityManager:

```java
PurchaseOrder first =
    em.find(PurchaseOrder.class, 101L);

PurchaseOrder second =
    em.find(PurchaseOrder.class, 101L);
```

Ghi số SQL của từng lần và giải thích vai trò của L1 identity map. Sau đó mở EntityManager mới và thực hiện lại.

### Bài 2 — EAGER không phải JOIN

Tạo biến thể mapping `Order.customer` thành EAGER. So sánh:

1. `em.find(PurchaseOrder.class, id)`.
2. JPQL `SELECT o FROM PurchaseOrder o`.

Ghi SQL thực tế, đặc biệt các secondary SELECT. Không dự đoán số query chỉ từ annotation.

### Bài 3 — N+1 to-one

Tạo 20 Order với 20 Customer riêng. Query danh sách Order, sau đó đọc `o.getCustomer().getName()`.

Đếm SQL root và SQL Customer. Lặp lại khi cả 20 Order chỉ thuộc 2 Customer; giải thích vì sao số SELECT có thể thay đổi.

### Bài 4 — N+1 collection

Tạo 20 Order, mỗi Order 3 Lines. Query Order rồi gọi `getLines().size()` cho tất cả.

Đo SQL và thử thay bằng JPQL fetch join. So sánh số SELECT với số hàng join trả về.

### Bài 5 — EntityGraph

Tạo một graph chỉ định `customer` và một graph chỉ định `customer` cùng `lines`. Chạy cùng JPQL root.

Kiểm tra getter nào kích hoạt thêm SQL và giải thích vì sao graph không là cam kết “một SQL”.

### Bài 6 — Fetchgraph và loadgraph

Tạo mapping có association EAGER mặc định rồi áp hai hint `jakarta.persistence.fetchgraph` và `jakarta.persistence.loadgraph`.

Quan sát SQL của provider mục tiêu và mô tả semantic khác nhau giữa hai graph. Phân biệt yêu cầu graph với việc provider có thể fetch thêm.

### Bài 7 — DTO chỉ đọc

Xây `OrderRow` gồm ID, code và Customer name. Trả DTO bằng JPQL constructor expression.

So sánh với entity query + gọi `getCustomer().getName()`. Đo SQL, số entity managed và lượng cột dữ liệu đọc.

### Bài 8 — COUNT thay fetch collection

Một màn hình chỉ hiển thị `Order.code` và số Lines. So sánh:

- Fetch `o.lines` rồi gọi `size()`.
- JPQL `LEFT JOIN o.lines l GROUP BY ... COUNT(l.id)` trả DTO.

Giải thích vì sao lấy đầy đủ Lines có thể lãng phí cho một con số.

### Bài 9 — BatchSize

Nếu dùng Hibernate, thêm `@BatchSize(size = 10)` lên collection Lines. Với 50 Order, đọc tất cả Lines.

Quan sát các SQL `WHERE order_id IN (...)`, số SELECT và số bind parameters. Không giả định kết quả chính xác luôn là `1 + ceil(50/10)`.

### Bài 10 — SUBSELECT

Với Hibernate, thử `@Fetch(FetchMode.SUBSELECT)` trên Lines, tải 20 Order và truy cập một collection.

Quan sát liệu provider tải collections của tập parent như thế nào, và tổng số child rows. So với BatchSize.

### Bài 11 — Collection fetch join và phân trang

Tạo 30 Order, mỗi Order số Lines khác nhau. Thử fetch join Lines kết hợp `setMaxResults(10)`.

Quan sát cảnh báo/provider behavior. Thiết kế lại bằng query IDs rồi fetch collection, xác minh trả đúng 10 Order root và đầy đủ Lines.

### Bài 12 — Nhiều collections

Giả lập Order có 5 Lines và 4 PaymentRecords. Thử fetch join cả hai collection nếu provider/mapping cho phép.

Đếm rows SQL và phân tích nguy cơ nhân bản theo tích `5×4`. Đề xuất thiết kế hai query hoặc read model phù hợp.

### Bài 13 — L1/L2 cache

Chạy cùng query trong:

1. Context mới, cache lạnh.
2. Cùng context sau một lần load.
3. Context mới, shared cache có dữ liệu.
4. Context mới với cache bypass phù hợp.

Ghi số SELECT và chú ý rằng `clear` chỉ tác động L1.

### Bài 14 — Hibernate statistics

Bật `hibernate.generate_statistics`, ghi delta `getPrepareStatementCount`, `getEntityLoadCount` và `getCollectionFetchCount` cho một use case.

Giải thích vì sao `queryExecutionCount` không nhất thiết bằng số SELECT JDBC và vì sao counters toàn `SessionFactory` không tiện đo khi test chạy song song.

### Bài 15 — Query count ở tầng request

Bọc datasource bằng một công cụ đếm SQL thực thi, gọi endpoint có JSON serializer truy cập association lazy.

So sánh số SELECT khi đo **chỉ repository method** với số SELECT khi đo **hết request**. Xác định query nào sinh ở serialization.

### Bài 16 — Tối ưu thực tế

Với màn hình 50 Order, mỗi Order có 10 Lines, một số Product lặp, đặt ba giải pháp:

1. Entity query + lazy.
2. JOIN FETCH Customer và Lines.
3. DTO projection/two-step pagination.

Ghi một bảng gồm số SELECT, SQL rows, tổng thời gian, bộ nhớ và tính đúng của pagination. Chọn cách dựa trên toàn bộ chi phí, không chỉ số SQL.

## 29. Kết luận: đọc fetch plan và đo SQL là hai việc bổ sung nhau

**Fetch plan diễn đạt những dữ liệu cần có và cách ORM được hướng dẫn tải chúng; số câu SQL là hành vi quan sát được khi chạy code với provider, context, cache, dataset và access pattern cụ thể.** `EAGER` không mặc định là JOIN, `LAZY` không có nghĩa không phát sinh SELECT, `EntityGraph` không bảo đảm một câu SQL, và một lời gọi `createQuery` không đồng nghĩa một round-trip database.

Một query fetch join có thể giảm N+1 nhưng tăng số hàng và bytes truyền; batch fetch có thể đổi N secondary SELECT thành vài query; DTO projection có thể bỏ hoàn toàn nhu cầu materialize graph; cache có thể làm SQL biến mất trong một lần đo nhưng không sửa thiết kế truy cập chưa tốt.

Khi tối ưu, hãy **xác định output → chọn query shape/fetch plan → chạy toàn bộ flow → đo SQL thực thi cùng rows, latency và memory → kiểm chứng kết quả**. Đặc biệt với to-many, pagination, serializer và transaction boundary, **ít SELECT không tự động đồng nghĩa giải pháp nhanh, đúng hoặc an toàn hơn**.

Điểm quan trọng nhất cần ghi nhớ: **đừng suy ra số câu SQL từ annotation hoặc một dòng Java; hãy đo đúng hành vi thực thi, trong đúng phạm vi và điều kiện dữ liệu mà ứng dụng thật sự sử dụng.**
