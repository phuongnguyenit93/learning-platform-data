# Tải quan hệ có chủ đích bằng JOIN FETCH trong JPA

Trong ứng dụng dùng Jakarta Persistence (JPA), một entity thường có các quan hệ như `@ManyToOne`, `@OneToOne`, `@OneToMany` hoặc `@ManyToMany`. Việc truy vấn entity gốc không có nghĩa mọi quan hệ của nó đều được tải bằng cùng một câu SQL. Khi chương trình truy cập association chưa được khởi tạo, provider có thể gửi thêm truy vấn đến database. Nếu điều này lặp lại trong vòng lặp, ứng dụng có thể gặp **N+1 queries**: một truy vấn lấy danh sách ban đầu cộng thêm nhiều truy vấn lấy quan hệ của từng phần tử.

**`JOIN FETCH`** trong JPQL là một cách khai báo **kế hoạch tải có chủ đích cho từng truy vấn**: ngoài entity gốc, yêu cầu JPA tải association được chỉ định ngay trong truy vấn ấy.

Ví dụ:

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.status = :status
```

Câu này trả về các entity `SalesOrder`, đồng thời yêu cầu tải association `o.customer`. Khi service cần hiển thị tên khách hàng của từng đơn, việc chọn fetch plan phù hợp có thể tránh một loạt truy vấn bổ sung.

Tuy nhiên, **`JOIN FETCH` không phải mẹo tối ưu luôn đúng**. Nó có thể tăng lượng dữ liệu truyền về, làm nhân bản dòng SQL với collection, khiến phân trang sai/đắt, và tạo vấn đề khi tải nhiều collection cùng lúc. Chọn `JOIN FETCH` cần dựa trên **những quan hệ sẽ thực sự được dùng**, số lượng entity, kích thước collection, transaction boundary và kết quả đo đạc.

Bài học thuộc chương **Kế hoạch tải** của module *Data Persistence Relational Access ORM JPA*. Nội dung giải thích cách dùng `JOIN FETCH` cho quan hệ đơn và collection, phân biệt `JOIN` thông thường, `INNER JOIN FETCH` với `LEFT JOIN FETCH`, phân tích N+1, `DISTINCT`, phân trang hai bước, các giới hạn JPQL portable, Criteria API, EntityGraph và cách kiểm thử truy vấn thực tế.

---

## 1. Kế hoạch tải (fetch plan) là gì?

**Fetch plan** là quyết định về **dữ liệu entity và những association nào phải được sẵn sàng trong một thao tác đọc**. Ví dụ API trả trang danh sách đơn hàng chỉ cần:

- Mã đơn.
- Tổng tiền.
- Trạng thái.
- Tên khách hàng.

Nếu màn hình không hiển thị từng dòng hàng, không cần tải toàn bộ `OrderLine` của mọi đơn. Ngược lại, khi mở trang **chi tiết đơn**, ứng dụng có thể cần cả Customer và các OrderLine.

Hai use case cần hai kế hoạch tải khác nhau:

```text
Use case A: Danh sách đơn
  SalesOrder
    ├── id
    ├── status
    ├── totalAmount
    └── customer.name       ← cần
        lines               ← chưa cần

Use case B: Chi tiết đơn
  SalesOrder
    ├── id
    ├── status
    ├── totalAmount
    ├── customer            ← cần
    └── lines               ← cần
         ├── productSku
         ├── quantity
         └── unitPrice
```

Dùng một fetch plan “tải tất cả” cho cả hai use case thường không hiệu quả.

### 1.1. Hai cấp quyết định tải

JPA có ít nhất hai nơi ảnh hưởng đến fetch plan:

1. **Mapping-level fetch strategy**: ví dụ `@OneToMany(fetch = FetchType.LAZY)` hoặc `@ManyToOne(fetch = FetchType.EAGER)`.
2. **Query-level fetch plan**: ví dụ JPQL `JOIN FETCH` hoặc EntityGraph để chọn association cần tải trong một thao tác đọc cụ thể.

`FetchType.EAGER` biểu thị nghĩa vụ tải eager theo contract mapping, nhưng **không đảm bảo provider luôn dùng SQL JOIN**; provider có thể tải bằng các SELECT bổ sung. `FetchType.LAZY` là yêu cầu tải trì hoãn, với mức khả thi còn phụ thuộc mapping/provider, đặc biệt ở một số quan hệ to-one.

**`JOIN FETCH` là lựa chọn tường minh ở cấp truy vấn**, giúp người viết query diễn đạt trực tiếp use case cần association nào.

### 1.2. Fetch plan khác kết quả SELECT

Câu:

```jpql
select o
from SalesOrder o
join fetch o.customer
```

vẫn có **result type `SalesOrder`**. Nó **không tự trả một phần tử `Object[]` gồm Order và Customer**. `customer` được nạp để dùng thông qua association của Order.

Đây là khác biệt quan trọng so với:

```jpql
select o, c
from SalesOrder o
join o.customer c
```

Câu sau chọn hai biểu thức: result row thông thường chứa `SalesOrder` và `Customer`, và việc JOIN không tự mang contract fetch như `JOIN FETCH`.

## 2. Mô hình ví dụ: Customer, SalesOrder và OrderLine

Giả sử một cửa hàng có ba entity.

```text
          Customer                      SalesOrder
       +----------------+           +-----------------------+
       | id : Long      | 1       N | id : Long             |
       | name : String  |<----------| customer : Customer   |
       | email : String |           | status : OrderStatus  |
       | orders : List  |           | totalAmount : Decimal |
       +----------------+           | createdAt : Instant   |
                                    | lines : List          |
                                    +-----------+-----------+
                                                | 1
                                                |
                                                | N
                                    +-----------v-----------+
                                    | OrderLine             |
                                    | id : Long             |
                                    | lineNumber : int      |
                                    | productSku : String   |
                                    | quantity : int        |
                                    | unitPrice : Decimal   |
                                    +-----------------------+
```

### 2.1. Customer

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "crm_customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String name;

    @Column(name = "email_address", nullable = false)
    private String email;

    @OneToMany(
        mappedBy = "customer",
        fetch = FetchType.LAZY
    )
    private List<SalesOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

### 2.2. SalesOrder

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity(name = "SalesOrder")
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY
    )
    @OrderBy("lineNumber ASC")
    private List<OrderLine> lines = new ArrayList<>();

    protected SalesOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

Enum:

```java
package com.example.shop.persistence;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

### 2.3. OrderLine

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "line_number", nullable = false)
    private int lineNumber;

    @Column(name = "product_sku", nullable = false)
    private String productSku;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public String getProductSku() {
        return productSku;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
```

Các quan hệ cần hiểu:

| Quan hệ | Cardinality | Chiến lược được khai báo trong ví dụ |
|---|---|---|
| `SalesOrder.customer` | N:1, mỗi order một customer | `LAZY` |
| `SalesOrder.lines` | 1:N, mỗi order nhiều lines | `LAZY` |
| `Customer.orders` | 1:N, mỗi customer nhiều orders | `LAZY` |
| `OrderLine.order` | N:1, mỗi line một order | `LAZY` |

`@OrderBy("lineNumber ASC")` chỉ định thứ tự collection theo thuộc tính `lineNumber` khi tải collection; nó **không giống** `@OrderColumn` và không tự biến một List thành collection được đánh chỉ số bằng cột quản lý vị trí.

### 2.4. Dữ liệu mẫu

Giả sử:

**Customer**

| ID | Name |
|---:|---|
| 1 | An |
| 2 | Bình |

**SalesOrder**

| ID | Customer | Status | Số OrderLine |
|---:|---|---|---:|
| 101 | An | PAID | 2 |
| 102 | An | NEW | 0 |
| 103 | Bình | PAID | 3 |

Tập dữ liệu có cả:

- Association to-one luôn tồn tại trong mô hình.
- Collection có nhiều phần tử.
- Collection rỗng (Order#102).
- Hai orders trỏ cùng Customer.
- Các trạng thái khác nhau.

Dữ liệu như vậy giúp thấy sự khác biệt giữa INNER/LEFT fetch và việc nhân bản SQL rows.

## 3. Vấn đề N+1 xảy ra như thế nào?

Một query tải đơn:

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    where o.tenantId = :tenantId
    order by o.id
    """,
    SalesOrder.class
)
.setParameter("tenantId", "shop-a")
.getResultList();
```

Sau đó:

```java
for (SalesOrder order : orders) {
    System.out.println(
        order.getId() + " - " +
        order.getCustomer().getName()
    );
}
```

Nếu `customer` chưa được khởi tạo và provider cần query riêng cho từng Customer chưa có trong persistence context, có thể xuất hiện:

```text
SQL #1: SELECT ... FROM sales_order WHERE tenant_id = ?
SQL #2: SELECT ... FROM crm_customer WHERE id = ?
SQL #3: SELECT ... FROM crm_customer WHERE id = ?
SQL #4: SELECT ... FROM crm_customer WHERE id = ?
...
```

Trong trường hợp có N orders trỏ N Customers khác nhau và không có cache/batching, tổng số SELECT gần **1 + N**.

Đó là N+1.

### 3.1. Không phải lúc nào đúng bằng 1 + N

Số SQL thực tế phụ thuộc:

- Có bao nhiêu Customer **khác nhau**?
- Những Customer nào đã có trong first-level persistence context?
- Second-level cache có được bật/hit hay không?
- Provider có batch fetching hay không?
- Mapping EAGER/LAZY và bytecode enhancement.
- Các truy vấn khác đã tải association trước đó hay chưa.

Vì vậy **N+1 là mẫu rủi ro truy vấn**, không phải công thức khẳng định chính xác mọi lần.

### 3.2. N+1 với collection

```java
List<SalesOrder> orders = em.createQuery(
    "select o from SalesOrder o",
    SalesOrder.class
).getResultList();

for (SalesOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Nếu mỗi `lines` là lazy collection chưa khởi tạo, provider có thể gửi thêm SELECT cho từng Order. N+1 không chỉ xảy ra với `@ManyToOne`; quan hệ `@OneToMany` thường còn nặng hơn vì mỗi truy vấn con trả nhiều rows.

### 3.3. Mục tiêu không phải “đưa mọi truy vấn về một SQL”

Một SQL với quá nhiều JOIN có thể trả hàng trăm nghìn rows và nhiều cột trùng lặp. Đôi khi **hai hoặc ba SQL có kế hoạch tải hợp lý** lại tốt hơn một câu SQL cực lớn.

Mục tiêu thực tế là **giảm tổng chi phí đọc dữ liệu và quản lý entity** trên use case, không phải cực tiểu hóa số câu SQL bằng mọi giá.

## 4. JOIN FETCH là gì?

Cú pháp JPQL thông thường:

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.status = :status
```

`JOIN FETCH` yêu cầu fetch association `customer` cùng với Order được trả về. Đây là một **fetch join**: nó có tính chất JOIN về dữ liệu nguồn nhưng còn điều khiển cách association được tải.

Với SQL, provider có thể sinh một truy vấn khái niệm như:

```sql
SELECT
    o.id,
    o.tenant_id,
    o.order_status,
    o.total_amount,
    o.created_at,
    o.customer_id,
    c.id,
    c.display_name,
    c.email_address
FROM sales_order o
JOIN crm_customer c
  ON c.id = o.customer_id
WHERE o.order_status = ?;
```

Đây là **SQL minh họa**, không phải SQL provider bắt buộc phải sinh giống từng cột/alias. JPQL `JOIN FETCH` là yêu cầu về fetch semantics; SQL cụ thể phụ thuộc mapping, provider và dialect.

### 4.1. Giá trị trả về vẫn là root entity

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    join fetch o.customer
    where o.status = :status
    """,
    SalesOrder.class
)
.setParameter("status", OrderStatus.PAID)
.getResultList();
```

Mỗi phần tử của List là **`SalesOrder`**, không phải `Object[]`. Association được truy cập qua:

```java
for (SalesOrder order : orders) {
    String customerName = order.getCustomer().getName();
}
```

Khi query và fetch plan được thực hiện đúng, `Customer` cần cho vòng lặp đã được tải, nên vòng lặp này không còn phải gây một truy vấn riêng cho từng Customer chỉ để lấy tên trong use case đó.

### 4.2. JOIN FETCH không sửa metadata lâu dài

Việc dùng:

```jpql
join fetch o.customer
```

trong query A **không đổi** annotation của entity thành `FetchType.EAGER` cho mọi query khác. Query B không có fetch join vẫn hoạt động theo kế hoạch tải của chính nó, mapping và provider.

Đó là lợi ích quan trọng: **tải theo nhu cầu từng thao tác** thay vì bật EAGER trên mapping toàn ứng dụng.

## 5. JOIN thông thường và JOIN FETCH khác nhau thế nào?

So sánh:

**JOIN thông thường để lọc:**

```jpql
select o
from SalesOrder o
join o.customer c
where c.email = :email
```

**JOIN FETCH để nạp association:**

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.status = :status
```

| Đặc điểm | `JOIN` | `JOIN FETCH` |
|---|---|---|
| Mục đích chính | Liên kết dữ liệu để lọc/chọn/sắp xếp | Yêu cầu tải association cùng entity owner |
| Có biến alias cho relation? | Có, ví dụ `c` | **Không khai báo alias trong JPQL portable** |
| Có thể tham chiếu field của alias? | Có: `c.email` | Không qua fetch-join alias chuẩn |
| Có tự bảo đảm association được loaded? | Không | Fetch association được chỉ định |
| Có thể làm thay đổi tập roots? | Có, tùy INNER/LEFT và WHERE | Có, tương tự tác động cardinality |
| Dùng trong SELECT count/DTO? | Có, khi query hợp lệ | Không dùng fetch join nếu owner không được trả |
| Có thể nhân bản dòng từ collection? | Có | Có, và còn hydrate collection |

Ví dụ JOIN thường:

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    join o.customer c
    where c.name = :name
    """,
    SalesOrder.class
)
.setParameter("name", "An")
.getResultList();
```

Query dùng Customer trong WHERE nhưng **không yêu cầu fetch Customer**. Nếu sau đó service truy cập `order.getCustomer().getName()`, association có thể vẫn cần tải thêm.

### 5.1. Cùng một query có thể vừa cần lọc vừa cần fetch

Với association đơn, có thể viết query dùng path trong predicate và fetch association:

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.customer.email = :email
```

Đây là cách diễn đạt ý định “lấy Order của Customer có email này và tải Customer” mà không gắn alias vào fetch join.

Provider có thể tạo SQL tối ưu hoặc thêm join tùy cách xử lý implicit path, do đó vẫn nên quan sát SQL thực tế khi query nằm trên hot path.

Nếu cần alias cho điều kiện phức tạp, một `JOIN` riêng với alias và một `JOIN FETCH` riêng có thể diễn đạt ngữ nghĩa, nhưng có khả năng tạo redundant joins; cân nhắc DTO/EntityGraph hoặc thiết kế truy vấn thay thế.

## 6. INNER JOIN FETCH: chỉ giữ root có association tương ứng

Cú pháp:

```jpql
select o
from SalesOrder o
join fetch o.customer
```

`JOIN FETCH` không ghi loại join thường có ý nghĩa như **INNER JOIN FETCH**.

Viết đầy đủ:

```jpql
select o
from SalesOrder o
inner join fetch o.customer
```

Với association `SalesOrder.customer` được khai báo `optional = false` và dữ liệu hợp lệ, mọi Order đều có Customer. INNER FETCH phù hợp nếu nghiệp vụ chắc chắn muốn những Order có relation tương ứng.

Nếu relation **có thể NULL**, INNER FETCH loại những root không có match.

Ví dụ một mô hình `Ticket.assignee` optional:

```jpql
select t
from Ticket t
join fetch t.assignee
```

Nếu Ticket#50 chưa được phân công, nó không xuất hiện trong kết quả query này. Đó là hệ quả của INNER JOIN, **không phải lỗi JPA**.

### 6.1. Khi nào chọn INNER FETCH?

- Association bắt buộc theo schema và business rule.
- Chỉ quan tâm roots thực sự có relation.
- Muốn loại bỏ roots không có child trong collection fetch (nếu đó là ý định).
- Có bằng chứng INNER cho query plan tốt hơn và đáp ứng semantics.

Không dùng INNER FETCH chỉ vì viết ngắn hơn LEFT. Với association optional hoặc collection rỗng, nó có thể âm thầm loại dữ liệu mà API cần trả.

## 7. LEFT JOIN FETCH: giữ root dù association rỗng/không tồn tại

Cú pháp:

```jpql
select o
from SalesOrder o
left join fetch o.lines
```

`LEFT JOIN FETCH` giữ SalesOrder kể cả khi `o.lines` rỗng. Với dữ liệu mẫu, Order#102 vẫn có trong kết quả, và collection `lines` được tải là rỗng.

So sánh:

```jpql
-- Chỉ những Order có ít nhất một Line:
select distinct o
from SalesOrder o
join fetch o.lines
```

```jpql
-- Mọi Order, kể cả không có Line:
select distinct o
from SalesOrder o
left join fetch o.lines
```

### 7.1. Số roots khác nhau

Theo fixture:

| SalesOrder | Số lines | INNER JOIN FETCH | LEFT JOIN FETCH |
|---:|---:|---|---|
| 101 | 2 | Có | Có |
| 102 | 0 | Không | Có |
| 103 | 3 | Có | Có |

Sau khi xét distinct entity roots:

- INNER: **2 SalesOrder** (101, 103).
- LEFT: **3 SalesOrder** (101, 102, 103).

### 7.2. LEFT không bảo đảm mọi root sau WHERE

Nếu WHERE có điều kiện về child:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
where o.lines is not empty
```

thì vẫn loại root có collection rỗng do predicate. Với điều kiện dựa trên JOIN alias của child, việc lọc child cũng có thể làm LEFT JOIN mang hiệu ứng INNER. Phần về **lọc collection khi fetch** sẽ giải thích vì sao cần tránh những query tạo collection tải một phần.

### 7.3. LEFT OUTER JOIN FETCH

JPQL có thể viết:

```jpql
select o
from SalesOrder o
left outer join fetch o.lines
```

Từ `OUTER` thể hiện rõ loại join nhưng không đổi ý nghĩa so với `LEFT JOIN FETCH`.

## 8. Tải quan hệ @ManyToOne có chủ đích

Dùng `JOIN FETCH` với to-one thường là trường hợp đơn giản và hiệu quả nhất.

```java
public List<SalesOrder> findPaidOrdersWithCustomer(
        EntityManager em,
        String authorizedTenantId
) {
    return em.createQuery(
        """
        select o
        from SalesOrder o
        join fetch o.customer
        where o.tenantId = :tenant
          and o.status = :status
        order by o.createdAt desc, o.id desc
        """,
        SalesOrder.class
    )
    .setParameter("tenant", authorizedTenantId)
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
}
```

Sau query, service có thể xử lý:

```java
for (SalesOrder order : orders) {
    String name = order.getCustomer().getName();

    // Dùng order ID, status, total và name cho response.
}
```

### 8.1. Vì sao to-one thường ít nguy cơ nhân bản roots?

Với `@ManyToOne`, mỗi Order có tối đa một Customer được tham chiếu, nên JOIN tới Customer không biến một Order thành nhiều rows vì **chính quan hệ này**. Dĩ nhiên nếu query còn JOIN các collection khác, vẫn có thể phát sinh row multiplication.

Với `@OneToOne`, mức độ tương tự: join một relation tối đa một đối tượng thường không tự nhân bản parent.

### 8.2. Nên dùng INNER hay LEFT cho to-one?

- `@ManyToOne(optional = false)` với FK hợp lệ: INNER thường đúng ngữ nghĩa.
- Quan hệ optional: LEFT nếu muốn giữ parent có association NULL.
- Muốn chỉ những parent có association: INNER có chủ đích.
- Muốn lấy dữ liệu bất kể association có hay không: LEFT.

Ví dụ đơn hàng có một `coupon` optional (giả định entity được bổ sung thuộc tính coupon):

```jpql
select o
from SalesOrder o
left join fetch o.coupon
where o.tenantId = :tenant
```

Không dùng JOIN thông thường nếu use case cần `coupon` đã được tải, và không dùng INNER khi API phải trả cả đơn không có coupon.

### 8.3. Một số quan hệ to-one khác nhau trong cùng query

Nếu entity có nhiều association to-one cần hiển thị:

```jpql
select o
from SalesOrder o
join fetch o.customer
left join fetch o.shippingAddressEntity
left join fetch o.paymentMethod
where o.tenantId = :tenant
```

Đây là ví dụ khái niệm **chỉ áp dụng nếu các thuộc tính đó thực sự tồn tại trong entity model**. Fetch nhiều to-one thường ít tạo tích số dòng hơn fetch nhiều to-many, nhưng vẫn tăng độ rộng ResultSet, chi phí JOIN và dữ liệu hydrate.

Chỉ fetch những association thực sự dùng.

## 9. Tải @OneToMany bằng JOIN FETCH

Truy vấn chi tiết đơn cần OrderLine:

```java
SalesOrder order = em.createQuery(
    """
    select distinct o
    from SalesOrder o
    left join fetch o.lines
    where o.id = :orderId
      and o.tenantId = :tenant
    """,
    SalesOrder.class
)
.setParameter("orderId", orderId)
.setParameter("tenant", authorizedTenantId)
.getSingleResult();
```

Với Order#101 có hai OrderLine, SQL join sẽ thường tạo **hai dòng vật lý** mang dữ liệu Order#101, mỗi dòng đi với một OrderLine khác nhau.

JPA dùng mapping và identity để dựng một managed SalesOrder và collection OrderLine tương ứng. `DISTINCT` trong JPQL diễn đạt yêu cầu **trả root entity không trùng lặp**.

### 9.1. SQL minh họa

```sql
SELECT
    o.id AS order_id,
    o.order_status,
    o.total_amount,
    l.id AS line_id,
    l.product_sku,
    l.quantity,
    l.unit_price
FROM sales_order o
LEFT JOIN order_line l
  ON l.order_id = o.id
WHERE o.id = ?;
```

ResultSet giả định:

```text
order_id | status | line_id | product_sku
---------+--------+---------+------------
101      | PAID   | 7001    | BOOK-01
101      | PAID   | 7002    | PEN-02
```

Từ **hai SQL rows**, provider hydrate một Order entity có hai Line entities trong collection. Cơ chế mapping exact columns/aliases của SQL do provider tạo từ JPQL không nhất thiết giống mẫu minh họa.

### 9.2. Đúng dữ liệu nhưng có thể đắt

Một Order có 1.000 lines sẽ khiến một fetch join collection trả khoảng 1.000 SQL rows cho Order ấy (trong trường hợp chỉ join collection này). Các cột của Order có thể bị lặp trên mỗi row, làm tăng:

- Network bytes.
- Thời gian xử lý ResultSet.
- Bộ nhớ quản lý OrderLine instances.
- Chi phí de-duplication.
- Thời gian lock/transaction nếu query nặng.
- Độ trễ API nếu UI chỉ cần 10 dòng đầu.

**JOIN FETCH có thể giảm round trips nhưng tăng kích thước ResultSet.** Cần chọn theo lượng dữ liệu thực.

## 10. DISTINCT và hiện tượng root trùng khi fetch collection

Ví dụ:

```jpql
select o
from SalesOrder o
left join fetch o.lines
```

Nếu Order#101 có hai lines, Order#103 có ba lines, joined SQL rows chứa nhiều lần cùng Order root.

Tùy phiên bản/provider, result list của một query fetch collection có thể chứa lặp reference tới cùng root hoặc provider có cơ chế de-duplicate tự động.

Để biểu đạt **ngữ nghĩa không lặp root entity** rõ ràng trong JPQL portable, thường viết:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
```

### 10.1. DISTINCT không làm mất dòng OrderLine hợp lệ

`DISTINCT` của JPQL nhằm loại bỏ **kết quả root duplicate** theo biểu thức SELECT. Provider vẫn cần các SQL rows tương ứng để hydrate collection đầy đủ. Không nên hiểu rằng DISTINCT có thể cắt bỏ các dòng OrderLine hợp lệ rồi vẫn tạo đủ collection một cách thần kỳ.

Chi tiết cách provider đẩy DISTINCT xuống SQL và de-dup ở Java có thể khác nhau. Một số bản Hibernate hiện đại tự loại trùng các root trong kết quả fetch join, nhưng **không dùng chi tiết triển khai đó làm cơ sở áp đặt cho mọi JPA provider/version**.

### 10.2. DISTINCT không khắc phục tích số dòng của nhiều collection

Nếu query join hai collection có lần lượt 10 và 5 phần tử, SQL có thể tạo tới **10 × 5 = 50** dòng cho một root. `DISTINCT` có thể giúp kết quả root List không lặp nhưng không nhất thiết loại bỏ chi phí DB/network của 50 tổ hợp đó.

### 10.3. Đừng suy ra có bao nhiêu SQL rows từ result.size()

`List<SalesOrder>.size()` sau DISTINCT thể hiện số roots được trả về, **không phải số SQL rows đã truyền** và không phải số entity instances mọi loại được hydrate.

Muốn đánh giá chi phí, quan sát SQL/row counts/execution plan hoặc metrics thích hợp, không chỉ nhìn `orders.size()`.

## 11. Kích thước ResultSet: cách ước lượng rủi ro

Giả sử tải 100 SalesOrder:

- Mỗi Order có trung bình 8 OrderLine.
- Câu query chỉ fetch `o.lines`.
- Mỗi Order giữ nhiều cột có tổng độ rộng đáng kể.

Số joined rows có thể vào khoảng **800** nếu mọi Order có 8 lines. Các cột SalesOrder lặp lại 8 lần mỗi Order. Điều này có thể chấp nhận được hoặc quá lớn, tùy kích thước và use case.

So sánh hai kế hoạch:

**Kế hoạch A — một JOIN FETCH collection:**

```text
1 SQL
~800 joined rows
Order columns lặp nhiều lần
Hydrate 100 Orders + 800 Lines
```

**Kế hoạch B — hai truy vấn theo batch:**

```text
SQL #1: 100 Order rows
SQL #2: 800 OrderLine rows với order_id IN (...)
Order columns không bị lặp ở mỗi Line row
Assembly/association handling bổ sung
```

Hai câu SQL không nhất thiết chậm hơn một câu. Quyết định dựa trên:

- RTT tới database.
- Row width.
- Số children trung bình và cực đại.
- Bộ nhớ heap và persistence context.
- Filter/sort ở database.
- Index và execution plan.
- Khả năng provider batch fetch.

Đó là lý do **kế hoạch tải** quan trọng hơn khẩu hiệu “càng ít câu SQL càng tốt”.

## 12. Tải nhiều collection cùng lúc: Cartesian explosion

Giả sử SalesOrder có:

- `lines` gồm 10 phần tử.
- `comments` gồm 5 phần tử.

Query giả định:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
left join fetch o.comments
where o.id = :id
```

Nếu các association tồn tại trong entity, hai LEFT JOIN collections có thể tạo **10 × 5 = 50** SQL rows cho chỉ một Order.

Dù hai collections sau cùng có đúng 10 và 5 phần tử, provider vẫn phải đọc nhiều tổ hợp rows, loại trùng và dựng object graph.

### 12.1. Không chỉ là lỗi duplicate ở Java

`DISTINCT` không làm mất chi phí:

```text
SalesOrder
   |
   +-- 10 OrderLine
   |
   +-- 5 Comment

JOIN cả hai collection
   |
   v
50 tổ hợp joined rows
   |
   v
Hydrate collections + de-duplicate
```

Khi số lượng là 1.000 lines và 200 comments, tích số có thể rất lớn. Đây là một **chi phí kiến trúc**, không chỉ là vấn đề định dạng result list.

### 12.2. Hibernate MultipleBagFetchException

Trong một số tình huống, Hibernate không cho fetch đồng thời nhiều **bag-valued associations** và có thể ném `MultipleBagFetchException`.

Đây là **hành vi/exception của Hibernate**, không phải exception chung được mọi JPA provider yêu cầu. Nó xuất hiện do semantics của các bag collections và khả năng dựng collections chính xác từ joined rows.

Không sửa bằng cách đổi `List` sang `Set` một cách máy móc chỉ để exception biến mất; cách đó có thể làm thay đổi domain semantics và **không giải quyết chi phí Cartesian product**.

### 12.3. Phương án tốt hơn

- Fetch một collection quan trọng nhất bằng JOIN FETCH.
- Tải collection khác bằng query riêng.
- Dùng batch fetching hoặc `@Fetch(FetchMode.SUBSELECT)` nếu provider hỗ trợ và đã đo.
- Dùng DTO với query phù hợp cho màn hình thay vì luôn xây cả entity graph.
- Xem lại liệu UI có thực sự cần tất cả collections cùng lúc không.

Nếu một API muốn hiển thị **tổng số comments**, không cần fetch toàn bộ Comment entities; có thể SELECT một aggregate `COUNT` vào DTO.

## 13. Phân trang và collection JOIN FETCH: bẫy quan trọng

Một API danh sách 20 đơn mỗi trang:

```java
List<SalesOrder> page = em.createQuery(
    """
    select distinct o
    from SalesOrder o
    left join fetch o.lines
    where o.tenantId = :tenant
    order by o.createdAt desc, o.id desc
    """,
    SalesOrder.class
)
.setParameter("tenant", authorizedTenantId)
.setFirstResult(40)
.setMaxResults(20)
.getResultList();
```

Truy vấn này **có rủi ro cao**.

### 13.1. Tại sao?

SQL JOIN tạo nhiều rows trên một Order. Nếu database áp `LIMIT 20` trực tiếp lên joined rows:

- Một Order có 30 lines có thể chiếm phần lớn trang.
- Collection của Order có thể chỉ được lấy một phần.
- Số Order duy nhất trên trang có thể nhỏ hơn 20.

JPA provider không được coi một collection nạp dở là kết quả fetch hoàn chỉnh hợp lệ theo ý định. Một số provider có thể **phân trang trong memory** sau khi đọc nhiều rows, cảnh báo hoặc từ chối tùy cấu hình.

**Không mặc định `setMaxResults(20)` + collection JOIN FETCH đồng nghĩa 20 root entities với graph đầy đủ được giới hạn hiệu quả tại database.**

### 13.2. Hậu quả thực tế

- Query kéo lượng dữ liệu lớn về app.
- Performance tăng nhanh khi số OrderLine lớn.
- Phân trang sai kỳ vọng hoặc bị chặn.
- Sorting/pagination khó dự đoán khi JOIN nhiều collections.
- Count query của framework có thể bị lỗi nếu vô tình mang `FETCH` vào.

### 13.3. Giải pháp phổ biến: hai bước

**Bước 1:** Lấy trang **ID của root entity** theo điều kiện và sort ổn định, không fetch collection.

**Bước 2:** Lấy những root entities đã chọn và collection bằng JOIN FETCH, chỉ cho tập IDs của trang.

Chi tiết ở phần tiếp theo.

## 14. Phân trang hai bước: IDs trước, fetch sau

Một ví dụ đầy đủ:

```java
public List<SalesOrder> findOrderPageWithLines(
        EntityManager em,
        String authorizedTenantId,
        OrderStatus status,
        int offset,
        int pageSize
) {
    int safeOffset = Math.max(offset, 0);
    int safeSize = Math.min(Math.max(pageSize, 1), 100);

    // Bước 1: Phân trang root IDs, chưa fetch collection.
    List<Long> ids = em.createQuery(
        """
        select o.id
        from SalesOrder o
        where o.tenantId = :tenant
          and o.status = :status
        order by o.createdAt desc, o.id desc
        """,
        Long.class
    )
    .setParameter("tenant", authorizedTenantId)
    .setParameter("status", status)
    .setFirstResult(safeOffset)
    .setMaxResults(safeSize)
    .getResultList();

    if (ids.isEmpty()) {
        return List.of();
    }

    // Bước 2: Fetch đầy đủ collection cho roots thuộc trang.
    List<SalesOrder> fetched = em.createQuery(
        """
        select distinct o
        from SalesOrder o
        left join fetch o.lines
        where o.id in :ids
          and o.tenantId = :tenant
          and o.status = :status
        """,
        SalesOrder.class
    )
    .setParameter("ids", ids)
    .setParameter("tenant", authorizedTenantId)
    .setParameter("status", status)
    .getResultList();

    // IN (...) không bảo đảm cùng thứ tự với List ids.
    Map<Long, SalesOrder> byId = fetched.stream()
        .collect(Collectors.toMap(
            SalesOrder::getId,
            Function.identity()
        ));

    return ids.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();
}
```

Các imports Java ngoài JPA:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;
```

Đây là mô hình phân trang theo **root entity**, không phải theo joined SQL rows.

### 14.1. Vì sao bước 2 có thể trả thứ tự khác?

`WHERE o.id IN :ids` chỉ giới hạn tập Order, không cam kết thứ tự bằng danh sách ID đầu vào. Ngay cả khi `ids` là `[103, 101, 102]`, database có thể trả `[101, 102, 103]`.

Dùng `Map` và sắp lại theo `ids` giúp giữ đúng thứ tự trang đã xác định ở bước 1.

### 14.2. Cần xử lý trạng thái thay đổi giữa hai bước

Nếu một Order đổi status hoặc bị xóa sau bước 1 nhưng trước bước 2, tập `fetched` có thể thiếu phần tử. Mẫu trên chọn lọc theo cả tenant và status ở bước 2, bảo vệ scope nhưng có thể trả trang thiếu phần tử.

Nếu cần **snapshot nhất quán** giữa hai query, phải xác định transaction isolation/locking phù hợp. Không coi hai query liên tiếp mặc định nhìn thấy cùng một snapshot trên mọi database.

### 14.3. Thêm Customer nếu use case cần

Có thể kết hợp fetch một to-one và một collection:

```jpql
select distinct o
from SalesOrder o
join fetch o.customer
left join fetch o.lines
where o.id in :ids
  and o.tenantId = :tenant
```

Cách này vẫn có row multiplication theo `lines`, nhưng chỉ cho root IDs của trang. Nên thử trên dữ liệu có collection lớn vì pageSize nhỏ không bảo đảm số joined rows nhỏ nếu mỗi Order có rất nhiều Lines.

### 14.4. Không chỉ cần query trang mà còn cần query total count

Một API `Page<SalesOrder>` thường cần tổng số Orders phù hợp:

```jpql
select count(o)
from SalesOrder o
where o.tenantId = :tenant
  and o.status = :status
```

Count query **không chứa JOIN FETCH**. Việc ghép `JOIN FETCH` vào count query là lỗi phổ biến vì owner entity không được select.

## 15. Truy vấn COUNT không dùng JOIN FETCH

Sai về ý định:

```jpql
select count(o)
from SalesOrder o
left join fetch o.lines
```

`COUNT(o)` trả scalar `Long`, không trả `SalesOrder` owner của fetch association. Theo JPQL portable, fetch join không được sử dụng khi **entity owner không xuất hiện trong result**.

Đúng:

```jpql
select count(o)
from SalesOrder o
where o.tenantId = :tenant
```

Nếu query có điều kiện child:

```jpql
select count(distinct o)
from SalesOrder o
join o.lines l
where l.productSku = :sku
  and o.tenantId = :tenant
```

hoặc dùng EXISTS:

```jpql
select count(o)
from SalesOrder o
where o.tenantId = :tenant
  and exists (
      select l.id
      from OrderLine l
      where l.order = o
        and l.productSku = :sku
  )
```

Cách `EXISTS` tránh nhân bản root trong nguồn tính COUNT khi một Order có nhiều lines trùng SKU.

### 15.1. Đừng tính page count theo số joined rows

`COUNT(o)` sau `JOIN o.lines l` có thể đếm mỗi Order nhiều lần nếu nó có nhiều lines. Nếu muốn đếm Orders duy nhất, dùng `COUNT(DISTINCT o)` hoặc `EXISTS` tùy ngữ nghĩa.

### 15.2. Với Spring Data Pageable

Spring Data JPA có thể tự xây count query từ repository `@Query`. Nếu query chính chứa `JOIN FETCH`, việc tạo count query tự động có thể không phù hợp hoặc gây lỗi.

Có thể khai báo count query riêng:

```java
@Query(
    value = """
        select o
        from SalesOrder o
        join fetch o.customer
        where o.tenantId = :tenant
        order by o.id
        """,
    countQuery = """
        select count(o)
        from SalesOrder o
        where o.tenantId = :tenant
        """
)
Page<SalesOrder> findOrdersWithCustomer(
    @Param("tenant") String tenant,
    Pageable pageable
);
```

Mẫu trên dùng **to-one fetch** (`customer`), không fetch collection; dễ kết hợp phân trang hơn. `@Query`, `Page`, `Pageable` thuộc Spring Data, không phải API Jakarta Persistence chuẩn.

**Không tự áp dụng mẫu repository pageable này cho collection JOIN FETCH** mà không giải quyết vấn đề joined rows/phân trang đã phân tích ở trên.

## 16. Owner phải được chọn: giới hạn quan trọng của JPQL fetch join

Trong JPQL portable, association được fetch phải thuộc về entity có mặt trong kết quả SELECT.

Ví dụ hợp lệ:

```jpql
select o
from SalesOrder o
join fetch o.customer
```

Ví dụ không phù hợp:

```jpql
select o.id
from SalesOrder o
join fetch o.customer
```

Ở ví dụ sau, SELECT chỉ trả `Long` ID, **không trả Order entity owner**. Không có Order instance trong result để dùng association được fetch theo đúng nghĩa.

Tương tự, không nên:

```jpql
select new com.example.shop.dto.OrderRow(
    o.id, o.totalAmount
)
from SalesOrder o
join fetch o.lines
```

vì SELECT trả DTO, không trả owner `SalesOrder`.

### 16.1. DTO thì JOIN thông thường, không JOIN FETCH

Nếu DTO cần tên Customer:

```java
public record OrderRow(
    Long id,
    String customerName,
    BigDecimal totalAmount
) { }
```

JPQL:

```jpql
select new com.example.shop.dto.OrderRow(
    o.id,
    c.name,
    o.totalAmount
)
from SalesOrder o
join o.customer c
where o.tenantId = :tenant
```

DTO projection chọn đúng fields, không cần JPA hydrate Customer association vào Order managed. Đây thường là giải pháp rất phù hợp cho bảng danh sách chỉ đọc.

### 16.2. Không dùng fetch join để chuyển một entity thành tuple

`JOIN FETCH` không có nhiệm vụ trả row dạng `[Order, Customer]`. Nếu cần tuple/DTO có hai đối tượng hoặc fields, viết SELECT và JOIN bình thường với kiểu kết quả tương ứng.

## 17. Fetch join không có alias trong JPQL chuẩn

JOIN thường có alias:

```jpql
select o
from SalesOrder o
join o.lines l
where l.productSku = :sku
```

Nhưng với fetch join portable:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
```

**Không gắn identification variable cho association được fetch** theo ngữ pháp JPQL chuẩn. Một số provider (như Hibernate trong các ngữ cảnh/version nhất định) cho phép biến thể:

```jpql
-- Provider extension, không nên coi là JPQL portable.
select distinct o
from SalesOrder o
left join fetch o.lines l
where l.productSku = :sku
```

Ngay cả khi parser cho phép alias, query này còn có vấn đề **lọc collection được fetch** mà phần sau sẽ giải thích.

### 17.1. Vì sao hạn chế alias có ý nghĩa?

Fetch join có mục đích **tải association**, không tạo một nguồn dữ liệu có thể tùy ý định danh để lọc ra một tập con rồi gán tập con ấy cho collection managed. Việc dùng alias vào WHERE có thể làm collection trông như đã được tải đủ trong khi thực tế chỉ có những children thỏa filter.

### 17.2. Không dùng ON với fetch join theo JPQL portable

Ví dụ:

```jpql
-- Không coi đây là JPQL portable:
select distinct o
from SalesOrder o
left join fetch o.lines l on l.productSku = :sku
```

Fetch join chuẩn không khai báo identification variable hoặc join condition tùy ý như JOIN thường. Một số provider có cú pháp extension, nhưng dễ dẫn đến **partial collection** hoặc hành vi không được JPA bảo đảm.

Nếu cần chỉ tải children thỏa predicate, hãy dùng projection/association query riêng thay vì cố “lọc fetch” theo cú pháp không chuẩn.

## 18. Không fetch collection một phần bằng WHERE một cách vô thức

Giả sử Order#101 có hai lines:

```text
Order#101
  ├── BOOK-01
  └── PEN-02
```

Nghiệp vụ muốn **tìm những Orders có ít nhất một line SKU BOOK-01**, rồi vẫn hiển thị **tất cả lines** của mỗi Order.

Một cách viết nguy hiểm (dựa vào alias fetch join extension):

```jpql
select distinct o
from SalesOrder o
join fetch o.lines l
where l.productSku = :sku
```

Nếu provider chấp nhận, ResultSet có thể chỉ chứa BOOK-01. Khi ấy `o.lines` có nguy cơ bị coi là collection đã được nạp nhưng **thiếu PEN-02**.

Hậu quả có thể rất nghiêm trọng:

- UI hiển thị thiếu dòng hàng.
- Tính tổng số lượng/số tiền từ collection sai.
- Code nghiệp vụ tin collection đã đầy đủ.
- Persistence context có trạng thái collection không phản ánh toàn bộ association.
- Việc thay đổi collection sau đó có thể gây tác động không mong muốn tùy mapping/provider.

**Đừng dùng fetched association như một collection bị lọc** nếu mục tiêu là quản lý entity graph đầy đủ.

### 18.1. Giải pháp: EXISTS lọc root, FETCH toàn bộ collection

JPQL portable:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
where o.tenantId = :tenant
  and exists (
      select l.id
      from OrderLine l
      where l.order = o
        and l.productSku = :sku
  )
```

Ý nghĩa:

1. Subquery `EXISTS` quyết định **Order nào đủ điều kiện**.
2. `LEFT JOIN FETCH o.lines` tải **toàn bộ OrderLine association** của từng Order được chọn.
3. Không dùng filter `productSku` trực tiếp lên fetched rows.

Nếu Order có ba lines trong đó hai lines cùng SKU BOOK-01, EXISTS vẫn chỉ quyết định Order có match, không nhân bản root theo số lines matching bên trong subquery.

### 18.2. Nếu chỉ cần những lines khớp SKU

Khi use case thực sự cần **danh sách các OrderLine khớp điều kiện**, truy vấn trực tiếp `OrderLine`:

```jpql
select l
from OrderLine l
join fetch l.order
where l.productSku = :sku
```

Hoặc dùng DTO projection từ `OrderLine` với fields cần hiển thị.

Không ép collection `SalesOrder.lines` managed trở thành tập con “đã fetch đầy đủ” chỉ để phục vụ một màn hình tìm kiếm.

### 18.3. Nếu chỉ cần biết có SKU đó

Không cần fetch bất kỳ collection nào:

```jpql
select o
from SalesOrder o
where exists (
    select l.id
    from OrderLine l
    where l.order = o
      and l.productSku = :sku
)
```

Use case không đọc `lines` thì fetch thêm toàn bộ lines chỉ làm tăng chi phí.

## 19. N+1 và thời điểm truy cập Lazy association

Ví dụ service:

```java
@Transactional(readOnly = true)
public List<OrderDetailDto> getOrderDetails(String tenantId) {
    List<SalesOrder> orders = em.createQuery(
        """
        select distinct o
        from SalesOrder o
        join fetch o.customer
        left join fetch o.lines
        where o.tenantId = :tenant
        """,
        SalesOrder.class
    )
    .setParameter("tenant", tenantId)
    .getResultList();

    return orders.stream()
        .map(OrderDetailDto::fromEntity)
        .toList();
}
```

Ở đây `@Transactional(readOnly = true)` là Spring annotation; nó giữ transaction/persistence context phù hợp cho use case đọc và ánh xạ DTO bên trong service. Class `OrderDetailDto` là DTO do dự án định nghĩa.

### 19.1. Vì sao chuyển DTO ngay trong service thường hữu ích?

Nếu service trả entity trực tiếp ra REST controller và JSON serializer tự động duyệt association:

- Serializer có thể truy cập lazy collection ngoài transaction.
- Có thể gặp `LazyInitializationException` trong Hibernate hoặc lỗi truy cập association đã detached theo provider.
- Nếu session còn mở, serializer có thể vô tình phát sinh N+1.
- Entity graph sâu có thể làm serialization đệ quy/vòng lặp.
- Không kiểm soát được trường nào bị lộ ra ngoài API.

Đổi sang DTO có các fields được phép, được xây trong transaction, giúp xác định rõ dữ liệu cần fetch và ranh giới serialization.

### 19.2. JOIN FETCH không phải lý do mở session xuyên suốt request

Một số ứng dụng dùng Open Session in View (OSIV) để lazy load trong view layer. OSIV có thể che N+1 vì query bổ sung chạy khi serializer/render view truy cập association.

Nên thiết kế **fetch plan ở service/repository theo use case** thay vì dựa vào OSIV để “đụng đâu tải đó”. Nếu dự án có OSIV, cần đo query ở cả giai đoạn view serialization.

### 19.3. Tải association trước khi detach

Sau khi EntityManager đóng, một entity detached không thể giả định sẽ lazy load những association chưa khởi tạo. `JOIN FETCH` giúp những association **được yêu cầu fetch và thực sự đã tải** có dữ liệu sẵn cho việc đọc phù hợp, nhưng không đảm bảo mọi quan hệ sâu hơn đã được tải.

Ví dụ fetch `o.customer` không tự đảm bảo `o.customer.orders` cũng sẵn sàng.

## 20. Persistence context và identity map khi JOIN FETCH

`JOIN FETCH` vẫn làm việc trong hệ thống quản lý entity của JPA.

Ví dụ:

```java
SalesOrder first = em.find(SalesOrder.class, orderId);

SalesOrder second = em.createQuery(
    """
    select o
    from SalesOrder o
    join fetch o.customer
    where o.id = :id
    """,
    SalesOrder.class
)
.setParameter("id", orderId)
.getSingleResult();
```

Nếu cùng EntityManager/persistence context quản lý cùng persistent identity, `first` và `second` thông thường tham chiếu tới **cùng một managed SalesOrder instance**. `JOIN FETCH` không tạo một bản snapshot detached độc lập chỉ vì query có JOIN.

### 20.1. JOIN FETCH không tự refresh toàn bộ state đã loaded

Nếu SalesOrder/Customer đã được quản lý trong context với state cũ, một query mới không mặc định ghi đè mọi thuộc tính đã có như lệnh `EntityManager.refresh`.

Khi cần dữ liệu mới tuyệt đối theo transaction semantics:

- Xem mức isolation.
- Xác định có pending local changes không.
- Cân nhắc `refresh` nếu thật sự muốn overwrite state bằng dữ liệu database.
- Hoặc dùng context/transaction mới khi phù hợp.
- Không dùng `clear` tùy tiện khi còn thay đổi chưa flush.

**Fetch plan và data freshness là hai vấn đề khác nhau.**

### 20.2. Fetch join không làm entity read-only tự động

Entity được load từ JPQL fetch join vẫn là managed entity theo persistence context. Nếu thay đổi persistent attributes trong transaction ghi, JPA có thể dirty-check và flush như bình thường.

Nếu use case chỉ hiển thị dữ liệu, DTO projection hoặc chính sách read-only/transaction rõ ràng giúp giới hạn side effects.

### 20.3. First-level và second-level cache

Một query JOIN FETCH thường liên quan SQL để lấy associations, nhưng số truy vấn cụ thể có thể ảnh hưởng bởi cache, provider và context. Không suy diễn rằng cứ có JOIN FETCH thì **đúng một SQL** trong mọi trường hợp, đặc biệt khi graph còn những association EAGER khác hoặc provider thực hiện query bổ sung.

Quan sát SQL thực tế với dữ liệu/hệ thống đang chạy.

## 21. FetchType.LAZY/EAGER và JOIN FETCH: không phải hai khái niệm đối lập

Một nhầm lẫn phổ biến:

> Đã có `fetch = FetchType.LAZY` thì không thể JOIN FETCH.

**Sai.** Mapping LAZY là chiến lược mặc định cho association; query JOIN FETCH thể hiện rằng **trong use case cụ thể này** cần nạp association.

Ví dụ:

```java
@OneToMany(fetch = FetchType.LAZY, mappedBy = "order")
private List<OrderLine> lines;
```

và:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
where o.id = :id
```

là một kết hợp hợp lý.

### 21.1. Vì sao không bật EAGER khắp nơi?

Nếu cấu hình:

```java
@OneToMany(fetch = FetchType.EAGER, mappedBy = "order")
private List<OrderLine> lines;
```

mọi thao tác tải SalesOrder có thể phải đảm bảo lines được tải theo eager semantics, ngay cả khi use case chỉ cần ID/status. Provider có thể dùng JOIN hoặc SELECT bổ sung.

Hệ quả tiềm ẩn:

- Fetch thừa dữ liệu.
- Tăng số SQL statements hoặc tăng row width.
- N+1 với eager to-one/to-many được provider xử lý bằng secondary selects trong một số truy vấn.
- Khó tối ưu truy vấn theo từng màn hình.
- Pagination/filter phức tạp.

Đặt LAZY ở các association thích hợp rồi dùng query-specific fetch plan thường cho quyền kiểm soát tốt hơn.

### 21.2. EAGER mặc định ở to-one

JPA mặc định `FetchType.EAGER` cho `@ManyToOne` và `@OneToOne` nếu không khai báo. Vì vậy, để thiết kế to-one tải khi cần, nên cân nhắc cấu hình LAZY tường minh nếu mô hình/provider đáp ứng nhu cầu.

`FetchType.LAZY` có thể chỉ là hint trong một số ngữ cảnh/provider, đặc biệt với một số cấu trúc `@OneToOne`. Việc mọi to-one đều lazy chính xác không phải điều có thể đảm bảo chỉ bằng annotation trong mọi stack; cần kiểm tra thực tế.

## 22. EntityGraph là giải pháp thay thế cho query-specific fetch plan

JPA có **EntityGraph** để khai báo association cần tải mà không nhất thiết viết `JOIN FETCH` trong JPQL.

Ví dụ dynamic graph:

```java
EntityGraph<SalesOrder> graph =
    em.createEntityGraph(SalesOrder.class);

graph.addAttributeNodes("customer", "lines");

List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    where o.tenantId = :tenant
    """,
    SalesOrder.class
)
.setParameter("tenant", authorizedTenantId)
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
```

EntityGraph cho phép tách một phần **fetch shape** khỏi JPQL predicate.

### 22.1. EntityGraph không đồng nghĩa SQL JOIN

**Quan trọng:** EntityGraph là chỉ dẫn về những attributes cần tải; provider có thể dùng:

- SQL joins.
- Secondary selects.
- Batch fetching.
- Các chiến lược riêng khác đáp ứng yêu cầu fetch semantics.

Không nên nhận xét rằng “`@EntityGraph` luôn tương đương một `JOIN FETCH` trong SQL”.

### 22.2. Khi nào EntityGraph hữu ích?

- Một query JPQL có nhiều biến thể fetch plan.
- Service cần fetch associations theo use case mà không muốn sửa cú pháp JPQL.
- Cần khai báo graph tái sử dụng bằng named entity graph.
- Repository framework hỗ trợ EntityGraph thuận tiện.
- Muốn fetch subgraph có cấu trúc rõ.

### 22.3. Named entity graph

Có thể khai báo trên entity:

```java
@NamedEntityGraph(
    name = "SalesOrder.withCustomer",
    attributeNodes = {
        @NamedAttributeNode("customer")
    }
)
@Entity(name = "SalesOrder")
public class SalesOrder {
    // ...
}
```

Sau đó:

```java
EntityGraph<?> graph =
    em.getEntityGraph("SalesOrder.withCustomer");

List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    where o.status = :status
    """,
    SalesOrder.class
)
.setParameter("status", OrderStatus.PAID)
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
```

Đoạn annotation là minh họa **thêm vào entity SalesOrder đã có**, không tạo thêm một class trùng tên trong source thực tế.

### 22.4. fetchgraph và loadgraph

JPA có hai hints phổ biến:

- `jakarta.persistence.fetchgraph`.
- `jakarta.persistence.loadgraph`.

Chúng ảnh hưởng cách provider diễn giải graph và những attributes không được chỉ định, theo semantics của Jakarta Persistence và provider. Tuy nhiên, **đừng mặc định một graph nhỏ loại bỏ mọi truy vấn khác**: mapping EAGER, provider behavior, entity inheritance và association được truy cập sau đó vẫn cần quan sát.

### 22.5. EntityGraph không tự giải quyết collection pagination

Nếu graph yêu cầu fetch collection cho một query pageable, provider có thể vẫn gặp vấn đề row multiplication và phân trang. Đừng dùng EntityGraph như cách “lách” vấn đề pagination của collection JOIN FETCH mà không đo trên provider/dialect thực tế.

## 23. Criteria API: Root.fetch thay cho JPQL JOIN FETCH

Criteria API cũng có fetch join:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<SalesOrder> cq =
    cb.createQuery(SalesOrder.class);

Root<SalesOrder> order = cq.from(SalesOrder.class);

order.fetch("customer", JoinType.INNER);

cq.select(order)
  .where(
      cb.equal(
          order.get("status"),
          OrderStatus.PAID
      )
  );

List<SalesOrder> orders =
    em.createQuery(cq).getResultList();
```

Các imports:

```java
import jakarta.persistence.criteria.*;
```

### 23.1. Fetch và Join có vai trò khác nhau

Trong Criteria:

```java
Join<SalesOrder, Customer> join =
    order.join("customer", JoinType.INNER);
```

và:

```java
Fetch<SalesOrder, Customer> fetch =
    order.fetch("customer", JoinType.INNER);
```

không trả về cùng interface type:

- `Join` dùng để điều hướng/đặt predicate hoặc điều khiển JOIN query.
- `Fetch` mô tả việc fetch association.
- `Fetch` không có contract `get(...)` giống `Path`/`Join`.

**Không ép kiểu Fetch sang Join** chỉ để lọc thuộc tính liên quan; cách cast có thể là extension provider và không portable.

### 23.2. Fetch collection với Criteria

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<SalesOrder> cq =
    cb.createQuery(SalesOrder.class);

Root<SalesOrder> o = cq.from(SalesOrder.class);

o.fetch("lines", JoinType.LEFT);

cq.select(o)
  .distinct(true)
  .where(cb.equal(o.get("tenantId"), authorizedTenantId));

List<SalesOrder> result =
    em.createQuery(cq).getResultList();
```

Ở đây `distinct(true)` diễn đạt mong muốn không lặp root trong result. Các giới hạn về collection size, nhiều collections, filtering và pagination **vẫn như JPQL JOIN FETCH**.

### 23.3. Static metamodel

Nếu annotation processor đã sinh `SalesOrder_`:

```java
o.fetch(SalesOrder_.lines, JoinType.LEFT);
o.fetch(SalesOrder_.customer, JoinType.INNER);

cq.where(
    cb.equal(o.get(SalesOrder_.tenantId), authorizedTenantId)
);
```

Các metadata có kiểu giúp giảm lỗi tên thuộc tính khi refactor, nhưng **không tự giảm SQL rows** hoặc tránh N+1 ở association chưa được fetch.

### 23.4. Criteria COUNT cần một query riêng không fetch

Không tái sử dụng cùng root/fetch structure để xây count query rồi chỉ thay SELECT bằng `cb.count(o)`. Hãy tạo một `CriteriaQuery<Long>` và Root riêng, có predicates tương đương nhưng **không thêm collection fetch**.

## 24. Spring Data JPA và @EntityGraph

Trong Spring Data JPA, có thể khai báo:

```java
public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    @Query("""
        select o
        from SalesOrder o
        where o.tenantId = :tenant
        order by o.id
        """)
    List<SalesOrder> findWithCustomer(
        @Param("tenant") String tenant
    );
}
```

`@EntityGraph` và `@Query` trong đoạn này thuộc Spring Data, **không phải annotation JPA chuẩn**. Fetch semantics được truyền tới provider, còn SQL cụ thể vẫn cần kiểm chứng.

### 24.1. Dùng JOIN FETCH trực tiếp trong @Query

```java
@Query("""
    select o
    from SalesOrder o
    join fetch o.customer
    where o.tenantId = :tenant
    """)
List<SalesOrder> findOrdersWithCustomer(
    @Param("tenant") String tenant
);
```

Với to-one association, cả `@EntityGraph` và JPQL JOIN FETCH đều có thể phù hợp. Chọn cách dễ duy trì theo repository/khả năng mở rộng use case.

### 24.2. Cẩn thận với collection fetch và Pageable

```java
// Dễ gây vấn đề hiệu năng/phân trang:
@Query("""
    select distinct o
    from SalesOrder o
    left join fetch o.lines
    where o.tenantId = :tenant
    """)
Page<SalesOrder> findOrdersWithLines(
    @Param("tenant") String tenant,
    Pageable pageable
);
```

Không mặc định framework có thể phân trang root đúng và rẻ. Nên dùng **query IDs theo Page**, sau đó fetch associations cho tập IDs của trang, hoặc trả DTO.

### 24.3. Không để repository quyết định thay domain use case

Repository có thể cung cấp các phương thức:

- `findOrderSummaryPage(...)`: DTO, không fetch lines.
- `findDetailByIdWithCustomerAndLines(...)`: fetch to-one + one collection.
- `findOrdersForExport(...)`: xử lý theo batch, tránh tải toàn bộ graph.
- `findOrdersForBackgroundJob(...)`: chọn fields/IDs cần xử lý.

Dùng tên phương thức thể hiện **fetch contract** để người gọi không vô tình sử dụng query nặng trong một use case nhẹ.

## 25. Batch fetching và subselect fetching: khi JOIN FETCH quá nặng

Khi cần đọc nhiều parent và thường xuyên truy cập collections, nhưng JOIN FETCH tạo quá nhiều SQL rows, cân nhắc **batch fetching**.

Thay vì:

```text
SELECT Orders
SELECT Lines WHERE order_id = 101
SELECT Lines WHERE order_id = 102
SELECT Lines WHERE order_id = 103
...
```

Provider có thể gom nhiều order IDs:

```sql
SELECT ...
FROM order_line
WHERE order_id IN (?, ?, ?, ...);
```

### 25.1. Hibernate @BatchSize là extension

Ví dụ Hibernate-specific:

```java
@org.hibernate.annotations.BatchSize(size = 32)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
```

Đây là annotation Hibernate, **không thuộc Jakarta Persistence chuẩn**. Tùy provider/version, có thể dùng cấu hình batch fetch tương ứng như `hibernate.default_batch_fetch_size`.

Batch fetching có thể giảm N+1 mà không làm lặp Order columns trong cùng SQL ResultSet với mọi Line.

### 25.2. Hibernate SUBSELECT fetching

Một số phiên bản Hibernate có chiến lược:

```java
@org.hibernate.annotations.Fetch(
    org.hibernate.annotations.FetchMode.SUBSELECT
)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Khi kích hoạt, provider có thể tải collections của tập parent bằng subselect dựa trên query gốc/managed state. Đây là **provider-specific optimization**, cần kiểm tra SQL thật và tác động lên bộ nhớ.

### 25.3. Batch fetching không tự luôn tốt hơn JOIN FETCH

Nếu use case chỉ có một SalesOrder và năm lines, một `LEFT JOIN FETCH` có thể rất hợp lý. Nếu 5.000 SalesOrder, mỗi đơn có nhiều lines, batch fetch hoặc truy vấn hai bước có thể phù hợp hơn.

Chọn theo cardinality và số liệu đo.

## 26. DTO projection: không cần fetch entity graph khi chỉ đọc dữ liệu

Giả sử bảng danh sách chỉ cần:

- Order ID.
- Status.
- Total amount.
- Customer name.

DTO:

```java
package com.example.shop.readmodel;

import java.math.BigDecimal;

public record OrderSummaryDto(
    Long id,
    String customerName,
    BigDecimal totalAmount,
    OrderStatus status
) { }
```

JPQL:

```java
List<OrderSummaryDto> rows = em.createQuery(
    """
    select new com.example.shop.readmodel.OrderSummaryDto(
        o.id,
        c.name,
        o.totalAmount,
        o.status
    )
    from SalesOrder o
    join o.customer c
    where o.tenantId = :tenant
    order by o.createdAt desc, o.id desc
    """,
    OrderSummaryDto.class
)
.setParameter("tenant", authorizedTenantId)
.setMaxResults(50)
.getResultList();
```

Không dùng `JOIN FETCH` vì kết quả là DTO, không phải SalesOrder entity owner. `JOIN` thường đủ để chọn thuộc tính Customer.

### 26.1. Lợi ích

- Không tạo cả entity graph chỉ để đọc một vài fields.
- Giảm kích thước mỗi result row.
- Không gây lazy loading khi serialize DTO.
- Dễ kiểm soát fields được công khai.
- Phân trang root/scalar thường đơn giản hơn.
- Không đặt thêm managed entities vào persistence context nếu chỉ projection scalar.

### 26.2. Khi nào nên giữ entity + JOIN FETCH?

- Use case thực sự thao tác với entity graph.
- Domain logic cần duyệt/kiểm tra relations.
- Service cần sửa managed entity trong transaction.
- Chi tiết một Order có kích thước collection hợp lý.
- ORM association mappings mang lại lợi ích về identity/lifecycle.

Chọn DTO không phải lời kêu gọi loại bỏ entity; đó là **read model phù hợp từng nhu cầu**.

## 27. Có cần fetch mọi tầng quan hệ không?

Một graph có thể sâu:

```text
SalesOrder
  ├── customer
  │    └── addresses
  └── lines
       └── product
            └── category
```

Không nên mặc định tải tất cả vì API cần một Order.

Mỗi tầng:

- Có thể thêm JOIN.
- Có thể thêm collection và tăng rows.
- Có thể kích hoạt thêm tải qua EAGER mappings.
- Có thể tăng nguy cơ vòng lặp khi serialize.
- Có thể kéo dữ liệu không được phép công bố.
- Có thể làm rõ ràng ranh giới transaction khó hơn.

### 27.1. Xác định dữ liệu theo use case

Ví dụ detail response cần:

```text
Order id, status, total
Customer name
Lines: product SKU, quantity, unit price
```

Không cần tự động tải `Customer.orders`, `Product.category` hoặc `Product.reviews`. Hãy mô tả DTO response trước, rồi thiết kế fetch plan theo fields đó.

### 27.2. EAGER graph có thể làm N+1 lan sang quan hệ khác

Giảm N+1 ở `SalesOrder.customer` không có nghĩa toàn query không còn N+1 nếu Customer có EAGER associations hoặc service sau đó duyệt sâu. Cần quan sát **tổng số SQL statements của toàn use case**, không chỉ khẳng định một query chính có JOIN FETCH.

### 27.3. Nested fetch joins và portability

Một số provider hỗ trợ các biến thể nested fetch joins hoặc fetch aliases cho phép điều hướng sâu. Tuy nhiên mức hỗ trợ alias và điều kiện trên fetched associations không hoàn toàn giống JPQL chuẩn. Khi cần graph sâu, cân nhắc EntityGraph với subgraphs, nhiều query riêng hoặc DTO. Đừng phụ thuộc vào cú pháp extension mà không ghi rõ provider.

## 28. ORDER BY collection và thứ tự phần tử

Khi fetch collection kiểu List, thứ tự là một yêu cầu nghiệp vụ riêng.

Trong entity mẫu:

```java
@OneToMany(mappedBy = "order")
@OrderBy("lineNumber ASC")
private List<OrderLine> lines;
```

`@OrderBy` nói rằng khi collection được truy cập, các phần tử được sắp theo thuộc tính `lineNumber`. Nó không cần alias cho fetch join.

Tránh dựa trên:

```jpql
-- Không portable: alias fetched association để ORDER BY child.
select distinct o
from SalesOrder o
left join fetch o.lines l
order by l.lineNumber
```

nếu mục tiêu là chuẩn JPQL, vì alias của fetch join không được khai báo như JOIN thông thường.

### 28.1. @OrderBy và @OrderColumn khác nhau

| Cơ chế | Ý nghĩa |
|---|---|
| `@OrderBy("lineNumber ASC")` | Sắp xếp theo thuộc tính persistent của element |
| `@OrderColumn(name="position")` | Lưu vị trí List do JPA quản lý ở cột thứ tự |
| `ORDER BY o.createdAt` trong JPQL | Sắp xếp root query results |
| `ORDER BY child...` trong query JOIN thường | Sắp xếp joined rows, không mặc nhiên định nghĩa persistent List order |

Nếu thứ tự dòng hàng là phần quan trọng của domain, chọn mapping phù hợp và có integration test. Không giả định thứ tự tự nhiên của rows trong database sẽ được giữ nếu không có quy tắc rõ.

## 29. JOIN FETCH và các phép aggregate

Một số người muốn lấy Order và số lines bằng:

```jpql
select o, count(l)
from SalesOrder o
left join fetch o.lines l
group by o
```

Đây không phải cách portable để dùng fetch join. Nó trộn:

- Fetch toàn bộ collection.
- Chọn aggregate scalar.
- Alias cho fetched collection không chuẩn.
- GROUP BY entity có nhiều mapped attributes.

Nếu mục tiêu là **đếm số lines**, dùng aggregate riêng:

```jpql
select o.id, count(l)
from SalesOrder o
left join o.lines l
where o.tenantId = :tenant
group by o.id
```

Hoặc DTO projection có cấu trúc phù hợp.

Nếu mục tiêu là tải Order và toàn bộ lines, dùng fetch join không GROUP BY:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
where o.tenantId = :tenant
```

Đừng cố gom một query giải quyết mọi nhu cầu nếu chi phí/semantics không rõ.

## 30. JOIN FETCH có làm mất dữ liệu do bộ lọc tenant không?

Fetch join không phải cơ chế phân quyền. Nếu query:

```jpql
select o
from SalesOrder o
join fetch o.customer
```

trong hệ thống nhiều tenant, câu này có thể đọc orders của **nhiều tenant** nếu mapping/database không áp chính sách tách dữ liệu thích hợp.

Cần:

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.tenantId = :authorizedTenantId
```

với `authorizedTenantId` từ security context đáng tin.

### 30.1. Quan hệ cũng cần đảm bảo ranh giới tenant

Nếu cùng bảng chứa nhiều tenant, FK/unique constraints và domain rules phải bảo đảm SalesOrder của shop-a không trỏ tới Customer của shop-b. `JOIN FETCH` có thể hiển thị association theo FK đã lưu; bản thân nó không kiểm chứng ownership giữa hai entity.

### 30.2. Soft delete và provider filters

Một số dự án có soft-delete/tenant filter ở mức provider extension. Không giả định mọi SQL, fetch strategy, native query hoặc bulk DML đều được lọc giống nhau. Cần test data isolation và trạng thái soft-delete khi chuyển fetch plan.

### 30.3. N+1 không biện minh cho việc lộ dữ liệu

Không fetch `Customer.orders` của toàn bộ khách chỉ để tránh một N+1 trong màn hình hiển thị tên Customer. Đó là tập dữ liệu khác và có thể chứa thông tin không được phép trả cho user hiện tại.

## 31. Đọc query plan và SQL để đánh giá hiệu quả

Trước khi tối ưu, hãy xác định query nào gây N+1.

Một chuỗi chẩn đoán:

```text
API chậm
   |
   v
Ghi số SQL statements cho một request/use case
   |
   +-- 1 SELECT root + N SELECT association?
   |       |
   |       v
   |    N+1 candidate
   |       |
   |       v
   |    Xem association có thực sự cần trong use case?
   |       |
   |       +-- Không -> tránh truy cập/tạo DTO
   |       |
   |       +-- Có    -> JOIN FETCH / EntityGraph / batch
   |
   +-- Ít SQL nhưng rows lớn?
           |
           v
        Xem JOIN collection, row width,
        Cartesian product, indexes, pagination
```

### 31.1. Những chỉ số nên xem

- Số SELECT mỗi request.
- Latency p50/p95 của repository/service.
- Số joined rows.
- Số entity/collection elements được hydrate.
- Kích thước response DTO.
- Network bytes giữa app và DB.
- Heap/memory và GC pressure.
- Query plan, index usage, sort/hash operations.
- Transaction duration.
- Tốc độ biến đổi khi số roots và children tăng.

### 31.2. Quan sát SQL

Với Hibernate, có thể bật SQL logging và statistics trong môi trường test/dev theo cấu hình phù hợp. Các thuộc tính/công cụ logging cụ thể phụ thuộc phiên bản Hibernate và framework. Không bật log toàn bộ bind params chứa dữ liệu nhạy cảm ở production.

Một số người thấy chỉ **một SELECT** sau JOIN FETCH rồi kết luận tối ưu thành công. Cần xem SQL đó trả **bao nhiêu rows và cột**, đặc biệt với nhiều collection.

### 31.3. Index foreign key

Với schema minh họa, index trên `order_line.order_id` thường có thể giúp tải collection theo Order:

```sql
CREATE INDEX ix_order_line_order_id
ON order_line(order_id);
```

Nhưng đây chỉ là một gợi ý, không phải mệnh lệnh tạo index trong mọi môi trường. Hãy đo query plan, chỉ số selectivity và chi phí ghi/index maintenance theo database thật.

## 32. Kiểm thử fetch plan: không chỉ kiểm tra dữ liệu đúng

Một query có thể trả dữ liệu đúng nhưng tạo N+1. Vì vậy nên kết hợp:

1. **Kiểm thử ngữ nghĩa**: entity và association có đúng phần tử không?
2. **Kiểm thử số truy vấn/độ lớn**: có tránh N+1 hoặc Cartesian explosion không?
3. **Kiểm thử transaction boundary**: dữ liệu cần dùng có sẵn khi DTO mapping diễn ra không?
4. **Kiểm thử phân trang**: số roots/thứ tự/total count đúng không?
5. **Kiểm thử bảo mật**: tenant và soft-delete filter đúng không?

### 32.1. Fixture cho INNER/LEFT

Tạo:

```text
Order#101: 2 lines
Order#102: 0 lines
Order#103: 3 lines
```

Query:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
order by o.id
```

Kỳ vọng:

- Có ba Order.
- Order#101 có hai lines.
- Order#102 có collection rỗng.
- Order#103 có ba lines.

Query INNER JOIN FETCH sẽ không trả Order#102.

### 32.2. Kiểm tra dữ liệu trong collection

Ví dụ integration test phác thảo:

```java
List<SalesOrder> orders = em.createQuery(
    """
    select distinct o
    from SalesOrder o
    left join fetch o.lines
    where o.tenantId = :tenant
    order by o.id
    """,
    SalesOrder.class
)
.setParameter("tenant", "shop-a")
.getResultList();

assertEquals(3, orders.size());

SalesOrder empty = orders.stream()
    .filter(o -> o.getId().equals(102L))
    .findFirst()
    .orElseThrow();

assertTrue(empty.getLines().isEmpty());
```

Ví dụ dùng assertions theo phong cách JUnit; dự án thực cần setup fixture, imports và transaction/persistence context thích hợp.

### 32.3. Đo N+1 bằng instrumentation

Tạo N Orders trỏ tới N Customer khác nhau, với context sạch, rồi so sánh:

**Query A:**

```jpql
select o from SalesOrder o
```

**Query B:**

```jpql
select o from SalesOrder o join fetch o.customer
```

Trong cả hai case, sau query đều duyệt `order.getCustomer().getName()`.

Dùng SQL statement counter hoặc Hibernate Statistics (nếu dự án chọn Hibernate) để quan sát số SQL thực tế. Không khẳng định một số cố định nếu cache/batch/mapping chưa được kiểm soát.

### 32.4. Tách EntityManager giữa các test

Nếu test A đã tải Customer vào first-level cache, test B không fetch join vẫn có thể ít SQL hơn mong đợi. Để đo công bằng:

- Dùng EntityManager/transaction độc lập.
- Kiểm soát second-level cache hoặc ghi nhận trạng thái của cache.
- Dùng dữ liệu với các association identities rõ.
- Warm-up thống nhất khi benchmark.
- Không so sánh số SQL từ hai test có context state khác nhau.

### 32.5. Test phân trang hai bước

- Tạo Orders có số lines khác nhau.
- Query bước 1 có `ORDER BY createdAt DESC, id DESC`.
- Kiểm tra IDs trang đúng và không lặp.
- Query bước 2 có đủ lines.
- Bảo đảm trả về đúng **thứ tự từ IDs**.
- Kiểm tra case IDs rỗng.
- Kiểm tra dữ liệu đổi giữa hai bước theo isolation contract.

### 32.6. Test association lọc theo SKU

Tạo Order#101 có BOOK-01 và PEN-02. Dùng `EXISTS` để chọn Order có BOOK-01, đồng thời fetch collection.

Assert:

- Query có Order#101.
- `order.getLines()` vẫn chứa **cả BOOK-01 và PEN-02**.
- Không chỉ chứa BOOK-01.

### 32.7. Test hiệu năng tăng theo dữ liệu

Khi số Orders tăng từ 10 lên 1.000, một query LAZY truy cập từng Customer có thể tăng gần tuyến tính theo số SELECT nếu không có batching/cache. Một query JOIN FETCH to-one có thể giữ số round trips thấp hơn, nhưng số rows/bytes vẫn tăng theo số Orders.

Đo cả truy vấn lẫn memory/latency để không đổi N+1 lấy một vấn đề khác.

## 33. Những lỗi thường gặp khi dùng JOIN FETCH

### 33.1. “JOIN nào cũng tự fetch association”

**Sai.** `JOIN` thường giúp truy vấn điều kiện hoặc chọn dữ liệu; `JOIN FETCH` mới thể hiện yêu cầu nạp association cùng owner.

### 33.2. “JOIN FETCH trả Object[] gồm root và child”

**Sai.** `select o ... join fetch o.customer` vẫn trả `SalesOrder`, association được tải trong graph.

### 33.3. “Không thể JOIN FETCH quan hệ LAZY”

**Sai.** Query-level fetch là cách ghi đè kế hoạch tải mặc định cho use case cụ thể.

### 33.4. “JOIN FETCH làm mọi quan hệ từ đây về sau EAGER”

**Sai.** Nó không thay đổi annotation/mapping globally.

### 33.5. “JOIN FETCH lúc nào cũng đúng một SQL”

**Không đảm bảo.** Graph và các EAGER relations khác, provider/cache/inheritance có thể gây thêm SQL; cần quan sát thực tế.

### 33.6. “INNER và LEFT FETCH luôn cho cùng roots”

**Sai.** INNER loại roots không có association match; LEFT giữ roots đó theo semantics join trước WHERE.

### 33.7. “JOIN FETCH collection không bao giờ trùng root”

**Không nên giả định portable.** SQL rows bị nhân bản theo children; dùng `SELECT DISTINCT root` khi cần root uniqueness và hiểu provider/version behavior.

### 33.8. “DISTINCT khắc phục mọi chi phí của nhiều collection”

**Sai.** Cartesian product vẫn có thể khiến database gửi lượng dữ liệu lớn.

### 33.9. “Fetch hai bags cùng lúc luôn được”

**Không đúng trên một số provider/mapping.** Hibernate có thể ném `MultipleBagFetchException`. Dù không ném, Cartesian explosion vẫn tồn tại.

### 33.10. “Đổi List thành Set luôn chữa được fetch performance”

**Sai.** Có thể đổi domain semantics, vẫn không giảm số tổ hợp SQL rows.

### 33.11. “JOIN FETCH collection + setMaxResults an toàn”

**Sai ở khía cạnh hiệu năng và ngữ nghĩa pagination nếu chưa thiết kế phù hợp.** Có thể phân trang trong memory hoặc gây lỗi. Ưu tiên IDs trước, fetch sau.

### 33.12. “Count query cũng phải JOIN FETCH”

**Sai.** Count trả scalar, owner của fetched association không được select. Viết count query riêng.

### 33.13. “Có thể select DTO và JOIN FETCH owner không nằm trong SELECT”

**Không portable.** Dùng JOIN thường và DTO projection.

### 33.14. “Alias fetched collection là JPQL chuẩn”

**Không.** JPQL portable không đặt identification variable cho fetched association; một số provider có extensions.

### 33.15. “JOIN FETCH ... ON child condition là portable”

**Không theo ngữ pháp fetch join chuẩn.** Dùng `EXISTS` lọc root và fetch collection toàn bộ, hoặc projection riêng.

### 33.16. “Lọc fetched child trong WHERE luôn cho collection đầy đủ”

**Nguy hiểm.** Có thể làm collection được hydrate một phần. Tách điều kiện chọn root khỏi việc fetch children.

### 33.17. “Fetch graph càng sâu càng tốt”

**Sai.** Thêm association làm tăng chi phí và có thể kéo dữ liệu không cần thiết.

### 33.18. “@EntityGraph luôn tạo một JOIN SQL”

**Sai.** Provider chọn cách tải phù hợp; graph không cam kết một statement.

### 33.19. “@BatchSize là annotation JPA chuẩn”

**Sai.** Đây là extension Hibernate (trong ví dụ), cần quản lý phụ thuộc provider.

### 33.20. “Fetch join làm entity detached”

**Sai.** Entity query results thường được quản lý trong persistence context, theo identity map.

### 33.21. “JOIN FETCH tự refresh state đã managed”

**Không nên giả định.** Fetch semantics khác data freshness/refresh semantics.

### 33.22. “LAZY sau khi đóng EntityManager vẫn luôn tải được”

**Sai.** Association chưa được khởi tạo thường không thể lazy-load ngoài persistence context phù hợp.

### 33.23. “OSIV là cách tốt nhất để tránh N+1”

**Sai.** OSIV có thể làm N+1 diễn ra muộn ở view/serializer. Thiết kế fetch plan theo use case.

### 33.24. “Fetch join không liên quan bảo mật”

**Sai.** Tải thêm relations có thể kéo dữ liệu nhạy cảm; phải bảo đảm tenant/authorization và DTO fields.

### 33.25. “Một SQL trả nhiều rows nghĩa sẽ tạo nhiều root Java objects cùng ID”

**Không đúng trong cùng persistence context.** Identity map quản lý entity identity; result list row multiplicity và instance identity là hai khái niệm khác nhau.

### 33.26. “ORDER BY root sẽ luôn sắp từng phần tử của collection”

**Sai.** Root ordering không thay thế `@OrderBy` hoặc `@OrderColumn` cho persistent List.

### 33.27. “Fetch join vừa là công cụ aggregate vừa là công cụ pagination”

**Không phù hợp.** Aggregate và pagination cần grain/result contract riêng; dùng JOIN thường/COUNT/DTO và phân trang IDs khi cần.

### 33.28. “Không có N+1 là chắc chắn nhanh”

**Sai.** Một query fetch 10.000 Orders × 1.000 Lines có thể rất nặng dù số SQL thấp.

## 34. Bài tập thực hành có hướng dẫn

### Bài 1: Nhận diện N+1

Code:

```java
List<SalesOrder> orders =
    em.createQuery("select o from SalesOrder o", SalesOrder.class)
      .getResultList();

for (SalesOrder o : orders) {
    System.out.println(o.getCustomer().getName());
}
```

**Câu hỏi:** Vì sao có thể xuất hiện N+1?

**Gợi ý:** `customer` là LAZY, mỗi Customer chưa có trong context/cache có thể cần SELECT riêng.

### Bài 2: JOIN FETCH Customer

**Yêu cầu:** Viết JPQL trả Order và tải Customer để hiển thị tên.

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.tenantId = :tenant
```

**Gợi ý:** Query vẫn trả `SalesOrder`.

### Bài 3: INNER và LEFT

Order#102 không có OrderLine. Hai truy vấn:

```jpql
select distinct o from SalesOrder o join fetch o.lines
```

```jpql
select distinct o from SalesOrder o left join fetch o.lines
```

**Câu hỏi:** Query nào trả Order#102?

**Đáp án:** Query LEFT.

### Bài 4: Tại sao DISTINCT?

Một Order có ba Lines.

**Gợi ý:** JOIN collection tạo ba SQL rows chứa cùng root; SELECT DISTINCT yêu cầu root result không lặp.

### Bài 5: JOIN thường hay JOIN FETCH?

Chỉ cần lọc Order theo email Customer, DTO không cần entity Customer.

**Gợi ý:** JOIN thường với alias để đọc email/fields, không cần JOIN FETCH nếu không cần loaded association.

### Bài 6: Trang danh sách đơn

Cần 50 Order IDs, trạng thái, tổng tiền, tên Customer.

**Gợi ý:** Dùng DTO projection thay vì fetch toàn bộ lines.

### Bài 7: Chi tiết một đơn

Cần SalesOrder, Customer và tất cả Lines.

```jpql
select distinct o
from SalesOrder o
join fetch o.customer
left join fetch o.lines
where o.id = :id
  and o.tenantId = :tenant
```

**Gợi ý:** Theo dõi số Lines; đây là một root nên fetch collection có thể phù hợp khi collection không quá lớn.

### Bài 8: MultipleBagFetchException

Hibernate báo lỗi khi fetch hai bag collections.

**Câu hỏi:** Có nên chỉ đổi mọi List thành Set?

**Gợi ý:** Không. Giải quyết thiết kế fetch plan và Cartesian product, cân nhắc một collection fetch + query/batch khác.

### Bài 9: Đếm Orders cho pagination

**Yêu cầu:** Viết count query cho list Orders theo tenant mà không có JOIN FETCH.

```jpql
select count(o)
from SalesOrder o
where o.tenantId = :tenant
```

### Bài 10: Pagination theo root

**Yêu cầu:** Lấy trang 20 Orders với Lines đầy đủ.

**Gợi ý:** Query ID page trước, query `select distinct o ... left join fetch o.lines where o.id in :ids` sau; khôi phục thứ tự IDs.

### Bài 11: IN không giữ thứ tự

`ids = [103,101,102]`; query fetch `WHERE o.id IN :ids` có thể trả `[101,102,103]`.

**Gợi ý:** Dùng Map keyed by ID rồi map theo danh sách IDs của trang.

### Bài 12: Truy vấn lọc một SKU nhưng vẫn fetch toàn collection

Order#101 chứa BOOK-01 và PEN-02.

**Yêu cầu:** Lọc Order có BOOK-01 và vẫn tải cả hai Lines.

**Gợi ý:** `WHERE EXISTS (...)` trên OrderLine, kết hợp `LEFT JOIN FETCH o.lines` không filter fetched children.

### Bài 13: Partial collection

Một query dùng alias fetch join và `WHERE l.productSku=:sku`.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** Collection có thể chỉ chứa matched lines nhưng được coi là đã tải; không portable và không đúng khi cần graph đầy đủ.

### Bài 14: Fetch join và DTO

```jpql
select new com.example.shop.dto.OrderRow(o.id)
from SalesOrder o
join fetch o.customer
```

**Câu hỏi:** Sai điều gì?

**Gợi ý:** Entity owner không nằm trong SELECT result. JOIN thường/DTO là phù hợp.

### Bài 15: Criteria fetch

**Yêu cầu:** Sử dụng Criteria API fetch `o.customer`.

```java
Root<SalesOrder> o = cq.from(SalesOrder.class);
o.fetch("customer", JoinType.INNER);
cq.select(o);
```

### Bài 16: Join hay Fetch trong Criteria?

**Câu hỏi:** Có nên cast `Fetch` thành `Join` để gọi `get("email")`?

**Gợi ý:** Không portable; dùng JOIN riêng/đường dẫn phù hợp cho predicates hoặc chuyển cách thiết kế.

### Bài 17: EntityGraph

**Yêu cầu:** Tải `customer` khi query Order bằng graph.

**Gợi ý:** `EntityGraph<SalesOrder> graph = em.createEntityGraph(SalesOrder.class)`, `graph.addAttributeNodes("customer")`, đặt hint `jakarta.persistence.fetchgraph`.

### Bài 18: EntityGraph có bảo đảm JOIN SQL không?

**Đáp án:** Không. Graph yêu cầu attributes được fetch, provider có thể chọn SQL strategy.

### Bài 19: Batch fetching

Tải 1.000 Orders, mỗi Order có 100 Lines. JOIN FETCH quá nặng.

**Gợi ý:** Đo batch fetching/secondary queries và so sánh network bytes + heap, không chỉ SQL count.

### Bài 20: Tải sâu nhiều tầng

Một màn hình chỉ cần Customer name; có nên fetch Customer.orders và Product.reviews không?

**Gợi ý:** Không nếu use case không dùng. Xác định response fields trước.

### Bài 21: Lazy loading ngoài transaction

Service trả SalesOrder entity chưa fetch lines, controller serialize sau khi context đóng.

**Gợi ý:** Có thể lỗi lazy initialization. Dùng fetch plan/DTO mapping trong transaction.

### Bài 22: N+1 trong serializer

OSIV bật, service query không fetch Customer, JSON serializer truy cập Customer name từng Order.

**Gợi ý:** SQL có thể phát sinh ở serialization. Đo toàn request và dùng DTO/fetch plan có chủ đích.

### Bài 23: @OrderBy

`@OrderBy("lineNumber ASC")` có ý nghĩa gì?

**Gợi ý:** Sắp collection khi load theo thuộc tính; không đồng nghĩa persistent list index `@OrderColumn`.

### Bài 24: First-level cache

Cùng persistence context, `em.find` và `JOIN FETCH` trả Order cùng ID.

**Câu hỏi:** Có tạo hai managed Order instances khác nhau không?

**Gợi ý:** Identity map giữ một managed instance theo persistent identity.

### Bài 25: Dữ liệu cũ trong managed entity

Query JOIN FETCH chạy lại sau transaction khác thay Customer name.

**Câu hỏi:** Có đảm bảo làm mới mọi field đã loaded không?

**Gợi ý:** Không. Fetch plan khác refresh; xem isolation/refresh/context boundary.

### Bài 26: Bảo mật tenant

Query fetch Customer của mọi Orders nhưng quên `WHERE tenantId`.

**Gợi ý:** JOIN FETCH không tự xác thực tenant. Cần scope authorization ở query/DB theo policy.

### Bài 27: Kiểm thử N+1

**Yêu cầu:** Lập test chứng minh query có JOIN FETCH giảm các SELECT phụ khi duyệt customer name.

**Gợi ý:** Dùng EntityManager sạch, dữ liệu nhiều Customer khác nhau và SQL statement instrumentation, đo cả toàn use case.

### Bài 28: Không chỉ tối ưu số SQL

Một SQL fetch 5.000 Orders và 500.000 Lines.

**Câu hỏi:** Vì sao có thể chậm hơn hai query theo batch?

**Gợi ý:** Row width, lặp cột parent, network, hydration, memory và GC.

## 35. Bảng quyết định nhanh

| Nhu cầu | Cách tải nên cân nhắc | Lý do |
|---|---|---|
| Trang danh sách có Customer name | JOIN FETCH to-one hoặc DTO projection | Giảm N+1, tránh lines không cần |
| Chi tiết một Order có ít Lines | `JOIN FETCH` Customer + `LEFT JOIN FETCH` Lines | Fetch graph đúng use case |
| Order có thể không có Lines | `LEFT JOIN FETCH o.lines` | Giữ roots rỗng |
| Chỉ Orders có ít nhất một Line | INNER JOIN FETCH nếu cần tải lines, hoặc EXISTS | Đúng semantics chọn root |
| Chỉ đếm Orders | `COUNT(o)`, không JOIN FETCH | Scalar result |
| Chỉ đọc ít fields để gửi API | DTO projection, JOIN thường | Không cần managed graph |
| Query pageable có collection | Page IDs rồi fetch association theo IDs | Phân trang đúng root |
| Nhiều collections lớn | Batch/secondary queries/DTO | Tránh Cartesian explosion |
| Cần fetch graph tùy use case | EntityGraph | Tách fetch description khỏi JPQL |
| Query động Criteria | `Root.fetch(...)` | Thể hiện fetch query-level |
| Lọc Order có line SKU nhưng cần mọi Lines | `EXISTS` lọc root + JOIN FETCH collection | Tránh partial collection |
| Dữ liệu cần fresh từ database | Refresh/context/isolation strategy | JOIN FETCH không phải refresh |
| Xuất báo cáo hàng triệu rows | Chunk/stream/DTO phù hợp | Tránh context/graph phình to |
| Truy cập association sau transaction | Map DTO hoặc fetch trước boundary | Tránh lazy access detached |
| API multi-tenant | Scope tenant/authorization rõ | Fetch không phải security filter |

## 36. Quy trình thiết kế kế hoạch tải trong dự án

Một quy trình thực hành:

1. **Xác định response/use case.** Liệt kê fields thực sự cần, không chọn graph theo thói quen.
2. **Vẽ association graph.** Phân biệt to-one và to-many, optional hay required.
3. **Xác định cardinality.** Một root có bao nhiêu children ở mức trung bình và lớn nhất?
4. **Bắt đầu từ JPQL/DTO đơn giản.** Không thêm fetch join khi chưa cần.
5. **Phát hiện N+1.** Theo dõi SQL statements trong toàn bộ service/serialization.
6. **Thử fetch to-one.** Nếu UI đọc Customer của mỗi Order, `JOIN FETCH o.customer` thường là lựa chọn rõ ràng.
7. **Thử fetch đúng một collection khi cần.** Dùng `LEFT` nếu phải giữ roots có collection rỗng.
8. **Thêm DISTINCT cho root result khi thích hợp.** Hiểu SQL rows có thể vẫn nhiều.
9. **Không fetch nhiều collection lớn bằng một query.** Cân nhắc query riêng hoặc batch.
10. **Nếu có pagination, tách ID page và collection fetch.** Đừng phụ thuộc memory pagination.
11. **Nếu filter trên child, tách điều kiện chọn root khỏi collection được fetch.** Dùng `EXISTS` khi phù hợp.
12. **Giữ transaction boundary rõ.** Map DTO khi context còn hợp lệ, không để serializer vô tình kích lazy loads.
13. **Kiểm tra count query và sorting.** Không mang fetch join vào SELECT COUNT.
14. **Kiểm tra tenant/security scope.** Đảm bảo fetched associations không vượt quyền.
15. **Đo SQL rows, latency và memory.** Không chỉ SQL statement count.
16. **Test với fixture có collection rỗng, nhiều children và nhiều associations.**

Sơ đồ:

```text
                 Cần dữ liệu từ relation?
                           |
                 +---------+---------+
                 |                   |
                Không                 Có
                 |                   |
                 v                   v
           Không JOIN FETCH   Cần entity graph hay DTO?
                                      |
                           +----------+----------+
                           |                     |
                          DTO                 Entity graph
                           |                     |
                           v                     v
                    JOIN/projection        To-one hay to-many?
                                             /         \
                                          To-one       To-many
                                             |            |
                                             v            v
                                         JOIN FETCH    Có pagination?
                                            |           /      \
                                            |         Có        Không
                                            |          |           |
                                            |          v           v
                                            |      Page IDs,   Collection nhỏ?
                                            |      fetch sau    /        \
                                            |                  Có        Không
                                            |                   |           |
                                            |                   v           v
                                            |             LEFT/INNER   Batch/query
                                            |             JOIN FETCH   riêng/DTO
                                            |                   |           |
                                            +-------------------+-----------+
                                                                |
                                                                v
                                                    Test + đo SQL rows
                                                    + latency + memory
```

## 37. Tổng kết

Những điều quan trọng nhất cần nhớ:

1. **`JOIN FETCH` là công cụ thiết kế fetch plan ở cấp truy vấn**, không phải cách thay đổi mapping toàn hệ thống.
2. **N+1** xuất hiện khi code truy cập nhiều associations chưa tải; `JOIN FETCH` là một cách giảm N+1 khi dữ liệu liên quan thực sự cần dùng.
3. **JOIN thường khác JOIN FETCH**: JOIN phục vụ liên kết/lọc/chọn, còn fetch join yêu cầu nạp association cùng entity owner.
4. **Kết quả `select o ... join fetch o.customer` vẫn là `SalesOrder`**, không tự là `Object[]`.
5. **INNER JOIN FETCH** loại roots không có association match; **LEFT JOIN FETCH** giữ roots không có child/relation theo semantics join.
6. **To-one fetch thường ít nhân bản roots**, còn **to-many fetch có thể tạo nhiều joined SQL rows** trên mỗi root.
7. **`SELECT DISTINCT root`** giúp biểu đạt result không trùng khi fetch collection, nhưng không làm mất chi phí Cartesian product.
8. **Fetch nhiều collections** có thể gây tích số dòng lớn; một số provider còn có hạn chế như Hibernate `MultipleBagFetchException`.
9. **Pagination + collection JOIN FETCH là tổ hợp nguy hiểm**; thường nên page root IDs trước rồi fetch collections theo tập IDs.
10. **Không dùng JOIN FETCH trong count/DTO projection** khi owner entity không được trả về trong SELECT.
11. **Fetch join không có alias hoặc ON tùy ý trong JPQL portable**; tránh dựa vào provider extensions ngoài ý muốn.
12. **Không lọc collection được fetch thành tập con mà vẫn coi nó đầy đủ**; dùng `EXISTS` lọc root rồi fetch toàn association nếu cần.
13. **Criteria `Root.fetch(...)` và EntityGraph** là các cách khai báo fetch plan khác; chúng vẫn cần quan sát SQL và cardinality.
14. **Batch fetching hoặc nhiều truy vấn có chủ đích đôi khi tốt hơn một fetch join cực lớn**.
15. **JOIN FETCH không tự làm entity read-only, refresh hay bypass persistence context**.
16. **Kế hoạch tải phải đặt trong transaction, authorization và API serialization boundary**; tránh lazy loading ngoài context và dữ liệu thừa.
17. **Đo toàn use case**, gồm số SELECT, số rows, thời gian, bộ nhớ và response size, trước khi kết luận fetch plan tối ưu.

**Kết luận:** `JOIN FETCH` hiệu quả nhất khi dùng **có chủ đích**: chọn đúng association mà use case thực sự cần, phân biệt to-one với to-many, giữ đầy đủ collection, không trộn fetch join với count/projection không phù hợp và tránh phân trang trực tiếp trên joined collection rows. Khi hiểu cả lợi ích lẫn chi phí, bạn có thể kết hợp JOIN FETCH, EntityGraph, batch loading và DTO projection để tạo những **kế hoạch tải JPA đúng dữ liệu, rõ ranh giới và có hiệu năng kiểm chứng được**.
