# Đọc kết quả nhiều cột bằng Tuple và kiểu dữ liệu rõ ràng trong JPA

Trong Java Persistence API (JPA), không phải truy vấn nào cũng cần trả về cả một entity. Một trang danh sách đơn hàng có thể chỉ cần mã đơn, tên khách hàng, trạng thái và tổng tiền. Một báo cáo có thể chỉ cần trạng thái, số đơn và tổng doanh thu. Nếu tải nguyên entity graph cho các nhu cầu này, ứng dụng có thể phải đọc nhiều cột, quản lý nhiều entity và vô tình phát sinh truy vấn phụ khi truy cập quan hệ.

Một lựa chọn là **projection nhiều cột**: câu truy vấn chỉ chọn những biểu thức cần thiết. Với Criteria API của Jakarta Persistence, **`Tuple`** cung cấp một cách đọc các cột kết quả thông qua **alias**, **chỉ số** hoặc chính **`TupleElement<T>`**, thay vì phải tự nhớ vị trí trong mảng `Object[]`.

Ví dụ cơ bản:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> order = cq.from(SalesOrder.class);

cq.multiselect(
    order.get("id").alias("orderId"),
    order.get("status").alias("status"),
    order.get("totalAmount").alias("totalAmount")
);

List<Tuple> rows = em.createQuery(cq).getResultList();

for (Tuple row : rows) {
    Long id = row.get("orderId", Long.class);
    OrderStatus status = row.get("status", OrderStatus.class);
    BigDecimal amount = row.get("totalAmount", BigDecimal.class);

    System.out.println(id + " | " + status + " | " + amount);
}
```

Thay vì viết `(Long) row[0]`, `(OrderStatus) row[1]` và `(BigDecimal) row[2]`, ta có thể đọc theo **tên cột logic** và nêu rõ **kiểu Java mong đợi**. Dẫu vậy, typed getter **không tự chuyển mọi kiểu dữ liệu**, cũng không loại bỏ nhu cầu kiểm tra `null`, thiết kế alias nhất quán và xác minh hành vi provider.

Bài học thuộc chương **DTO và phân trang** của module *Data Persistence Relational Access ORM JPA*. Nội dung tập trung vào cách tạo và đọc nhiều cột với `Tuple`, phân biệt `Tuple` với `Object[]` và DTO, xử lý alias/index/type/null, JOIN, GROUP BY, aggregate, pagination và các lỗi thường gặp.

> Mã minh họa sử dụng `jakarta.persistence.*` và `jakarta.persistence.criteria.*`. Với dự án JPA cũ, namespace có thể là `javax.persistence.*`. Các đoạn mã được trình bày như những ví dụ độc lập để người học lắp vào persistence unit và entity model tương ứng.

---

## 1. Vì sao cần kết quả nhiều cột?

Giả sử người dùng mở trang “Đơn hàng của tôi”. API chỉ cần:

- Order ID.
- Mã đơn.
- Trạng thái.
- Tên khách hàng.
- Tổng tiền.
- Ngày tạo.

Nếu truy vấn `select o from SalesOrder o`, JPA thường tải những thuộc tính persistent của Order cần thiết để dựng entity. Sau đó gọi `order.getCustomer().getName()` có thể kích hoạt lazy loading hoặc cần fetch plan riêng.

Một projection phù hợp hơn về ý định:

```jpql
select
    o.id,
    o.orderNumber,
    o.status,
    c.name,
    o.totalAmount,
    o.createdAt
from SalesOrder o
join o.customer c
where o.tenantId = :tenant
order by o.createdAt desc, o.id desc
```

Truy vấn này không yêu cầu nhận nguyên một đối tượng Order để sửa và quản lý vòng đời; nó yêu cầu **sáu giá trị trên mỗi dòng kết quả**.

Có ba kiểu biểu diễn phổ biến ở tầng JPA:

| Dạng kết quả | Ví dụ | Khi nào phù hợp |
|---|---|---|
| `Object[]` | `row[0]`, `row[1]` | Truy vấn nhỏ/legacy, chấp nhận cast và phụ thuộc vị trí |
| `Tuple` | `row.get("orderId", Long.class)` | Criteria projection động, tập cột có alias, xử lý kết quả linh hoạt |
| DTO/record | `new OrderSummary(...)` | Contract ổn định giữa repository và service/API |

**Tuple nằm giữa mảng giá trị thô và DTO có cấu trúc rõ.** Nó giúp đọc từng biểu thức có tên/kiểu, nhưng không thay thế hoàn toàn DTO trong thiết kế API dài hạn.

## 2. Mô hình dữ liệu xuyên suốt bài học

Ta sử dụng Customer và SalesOrder; một Order có thể có nhiều OrderLine để giải thích tình huống JOIN làm nhân bản dòng.

```text
           Customer
      +-------------------+
      | id : Long         |
      | name : String     |
      | email : String    |
      +---------+---------+
                |
                | 1:N
                v
           SalesOrder
      +-------------------------+
      | id : Long               |
      | orderNumber : String    |
      | tenantId : String       |
      | status : OrderStatus    |
      | totalAmount : BigDecimal|
      | createdAt : Instant     |
      | customer : Customer     |
      | lines : List<OrderLine> |
      +-----------+-------------+
                  |
                  | 1:N
                  v
             OrderLine
      +-------------------------+
      | id : Long               |
      | sku : String            |
      | quantity : int          |
      | order : SalesOrder      |
      +-------------------------+
```

### 2.1. Customer

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "crm_customer")
public class Customer {

    @Id
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String name;

    @Column(name = "email_address", nullable = false)
    private String email;

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
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity(name = "SalesOrder")
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    private Long id;

    @Column(name = "order_no", nullable = false)
    private String orderNumber;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected SalesOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Enum:

```java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

### 2.3. OrderLine

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id")
    private SalesOrder order;

    @Column(name = "product_sku", nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }
}
```

Các quan hệ trong ví dụ:

- `SalesOrder.customer` là association đơn (many-to-one).
- `SalesOrder.lines` là collection (one-to-many).
- `SalesOrder.totalAmount` là `BigDecimal`, không phải `double`.
- `SalesOrder.createdAt` là `Instant`.
- `SalesOrder.status` là enum `OrderStatus` được lưu dạng chuỗi qua `@Enumerated`.

### 2.4. Dữ liệu mẫu

Giả sử database có:

| ID | Mã đơn | Khách hàng | Trạng thái | Tổng tiền |
|---:|---|---|---|---:|
| 101 | SO-101 | An | PAID | 250000.00 |
| 102 | SO-102 | Bình | NEW | 80000.00 |
| 103 | SO-103 | An | PAID | 340000.00 |
| 104 | SO-104 | Chi | CANCELLED | 50000.00 |

Và:

| Order ID | Số OrderLine |
|---:|---:|
| 101 | 2 |
| 102 | 0 |
| 103 | 3 |
| 104 | 1 |

Từ đây ta có thể kiểm tra các projection đơn giản, phép tổng hợp và tác động của JOIN collection.

---

## 3. Chọn nhiều cột bằng JPQL thường trả Object[]

Một JPQL query chọn nhiều biểu thức:

```java
List<?> rows = em.createQuery(
    """
    select o.id, o.orderNumber, o.totalAmount
    from SalesOrder o
    order by o.id
    """
).getResultList();

for (Object item : rows) {
    Object[] row = (Object[]) item;

    Long id = (Long) row[0];
    String number = (String) row[1];
    BigDecimal amount = (BigDecimal) row[2];
}
```

Hình dạng một dòng:

```text
Object[]
 +-- [0] Long        -> orderId
 +-- [1] String      -> orderNumber
 +-- [2] BigDecimal  -> totalAmount
```

Đây là cách tiếp cận hợp lệ cho kết quả nhiều biểu thức trong JPQL. Tuy nhiên:

1. Phải nhớ **vị trí** từng field.
2. Đổi thứ tự SELECT nhưng quên đổi chỉ số đọc có thể gây lỗi khó phát hiện.
3. Mỗi lần đọc thường phải **cast thủ công**.
4. Người đọc code không thấy ngay `row[2]` có ý nghĩa gì.
5. Nếu hai cột cùng kiểu, đảo vị trí có thể không gây `ClassCastException` mà dữ liệu vẫn sai.
6. Khi kết quả có nhiều trường tùy chọn, logic đọc `Object[]` thường khó bảo trì.

Chẳng hạn:

```jpql
select o.orderNumber, c.name
from SalesOrder o join o.customer c
```

Hai giá trị đều là `String`. Nếu code vô tình đọc `row[0]` như tên khách hàng và `row[1]` như mã đơn, chương trình có thể chạy nhưng hiển thị dữ liệu đảo ngược.

**`Tuple` giúp làm rõ kết quả nhiều cột bằng tên logic của selection, giảm phụ thuộc vào vị trí mảng.**

### 3.1. JPQL và Tuple: lựa chọn portable

Một số provider hỗ trợ lấy `Tuple` trực tiếp từ JPQL thông qua những API/overload hoặc extension nhất định. Tuy nhiên, để hướng dẫn **cách xây Tuple rõ ràng theo Jakarta Persistence Criteria API**, bài này ưu tiên:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
```

Đây là con đường chuẩn và dễ kiểm soát cho `Tuple` projection trong Criteria API. Không coi mọi cách viết `createQuery(jpql, Tuple.class)` đều tương thích như nhau với mọi JPA provider/version mà chưa kiểm chứng.

Nếu query JPQL đã có contract cố định, **constructor expression** để trả DTO cũng là lựa chọn chuẩn và thường dễ đọc hơn.

## 4. Tuple là gì?

`Tuple` là interface thuộc:

```java
import jakarta.persistence.Tuple;
import jakarta.persistence.TupleElement;
```

Mỗi `Tuple` biểu diễn **một dòng kết quả của một projection nhiều selection**, và cung cấp các thao tác truy cập giá trị:

| API | Vai trò |
|---|---|
| `tuple.get(int index)` | Lấy giá trị theo vị trí |
| `tuple.get(int index, Class<X> type)` | Lấy theo vị trí và kiểm tra kiểu |
| `tuple.get(String alias)` | Lấy theo alias |
| `tuple.get(String alias, Class<X> type)` | Lấy theo alias với kiểu mong đợi |
| `tuple.get(TupleElement<X> element)` | Lấy theo selection/tuple element tương ứng |
| `tuple.toArray()` | Chuyển các giá trị thành `Object[]` theo thứ tự |
| `tuple.getElements()` | Xem metadata của các phần tử trong Tuple |

**Tuple không phải entity.** Nó không có `@Id`, không được `EntityManager.persist` và không được dirty-check như entity. Nó chỉ là vật chứa các giá trị kết quả.

### 4.1. Một Tuple không phải toàn bộ kết quả

Một query trả 100 rows sẽ tạo `List<Tuple>` có 100 phần tử theo contract kết quả, mỗi Tuple là **một row**:

```text
List<Tuple>
  |
  +-- Tuple row 1: orderId, number, amount
  |
  +-- Tuple row 2: orderId, number, amount
  |
  +-- Tuple row 3: orderId, number, amount
  |
  ...
```

Không dùng một Tuple để đại diện cho toàn bộ tập dữ liệu.

### 4.2. Tuple không phải Map<String,Object>

Mặc dù có thể truy cập bằng alias, `Tuple` không kế thừa `Map` và không có đầy đủ hợp đồng của Map như `keySet()`, `put()` hay `remove()`. Cũng không nên kỳ vọng có thể sửa các phần tử của Tuple rồi JPA tự cập nhật database.

### 4.3. Tuple không tự có tên thuộc tính khi chưa đặt alias

Một selection có thể có alias explicit hoặc không. Không nên phụ thuộc vào những alias provider tự sinh nếu cần đọc kết quả theo tên trong code lâu dài.

**Nguyên tắc:** Nếu sẽ đọc bằng `tuple.get("orderId", ...)`, hãy chủ động khai báo `.alias("orderId")` trên selection tương ứng.

---

## 5. Tạo CriteriaQuery<Tuple> bằng createTupleQuery()

Đây là cách minh họa trực tiếp nhất.

```java
import jakarta.persistence.*;
import jakarta.persistence.criteria.*;
import java.math.BigDecimal;
import java.util.List;

CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> o = cq.from(SalesOrder.class);

cq.multiselect(
    o.get("id").alias("orderId"),
    o.get("orderNumber").alias("orderNumber"),
    o.get("totalAmount").alias("totalAmount")
);

List<Tuple> results = em.createQuery(cq).getResultList();
```

Giải thích:

1. `em.getCriteriaBuilder()` tạo builder.
2. `cb.createTupleQuery()` khai báo result type là `Tuple`.
3. `Root<SalesOrder>` biểu diễn entity nguồn ở FROM.
4. `multiselect(...)` xác định **những biểu thức trả về**.
5. `alias(...)` đặt tên logic cho từng selection.
6. `em.createQuery(cq)` tạo typed query.
7. `getResultList()` trả `List<Tuple>`.

Đọc:

```java
for (Tuple row : results) {
    Long id = row.get("orderId", Long.class);
    String number = row.get("orderNumber", String.class);
    BigDecimal amount =
        row.get("totalAmount", BigDecimal.class);

    System.out.println(
        id + " | " + number + " | " + amount
    );
}
```

### 5.1. createQuery(Tuple.class) và createTupleQuery()

Có thể khai báo theo dạng:

```java
CriteriaQuery<Tuple> cq = cb.createQuery(Tuple.class);
```

Nhưng `cb.createTupleQuery()` làm ý định “truy vấn nhiều selection trả Tuple” rõ hơn và được thiết kế cho use case này.

### 5.2. multiselect là phần cấu thành của SELECT

`cq.multiselect(...)` khác với `cq.where(...)`:

- `multiselect` quyết định cột/biểu thức nào đi vào một Tuple.
- `where` quyết định rows nào được trả về.
- `orderBy` quyết định thứ tự.
- `groupBy` quyết định mức độ tổng hợp.

Ví dụ có điều kiện:

```java
cq.multiselect(
    o.get("id").alias("orderId"),
    o.get("totalAmount").alias("amount")
);

cq.where(
    cb.equal(o.get("status"), OrderStatus.PAID)
);
```

Kết quả mỗi Tuple có hai giá trị, không phải mọi trường của SalesOrder.

### 5.3. Dùng select(cb.tuple(...))

CriteriaBuilder có thể tạo compound selection `Tuple`:

```java
cq.select(
    cb.tuple(
        o.get("id").alias("orderId"),
        o.get("orderNumber").alias("number"),
        o.get("totalAmount").alias("amount")
    )
);
```

`cb.tuple(...)` và `cq.multiselect(...)` đều dùng để diễn đạt nhiều selection trong một query kiểu Tuple. Nên chọn một phong cách thống nhất trong module/repository để code dễ bảo trì.

Không cố lồng một compound tuple selection vào `multiselect` theo cách không được Criteria contract hỗ trợ; mỗi selection của `multiselect` nên là những biểu thức phù hợp result shape mong muốn.

## 6. Đọc theo alias: cách dễ hiểu nhất

Khi query:

```java
cq.multiselect(
    o.get("id").alias("orderId"),
    o.get("orderNumber").alias("number"),
    o.get("totalAmount").alias("amount")
);
```

bạn đọc:

```java
Long id = row.get("orderId", Long.class);
String orderNo = row.get("number", String.class);
BigDecimal amount = row.get("amount", BigDecimal.class);
```

Cách này làm rõ **ngữ nghĩa từng selection**.

### 6.1. Alias là tên logic trong kết quả Criteria

Đoạn:

```java
o.get("totalAmount").alias("amount")
```

không đổi tên field Java `totalAmount`, không đổi tên cột SQL `total_amount` và không cập nhật entity mapping.

`"amount"` chỉ là alias dùng để nhận diện selection trong kết quả Tuple.

Bốn tên khác nhau có thể đồng thời tồn tại:

| Tầng | Ví dụ |
|---|---|
| Java entity attribute | `totalAmount` |
| SQL column | `total_amount` |
| Criteria Tuple alias | `amount` |
| DTO field/API JSON field | `amount` hoặc `total` |

Chúng có thể được đặt giống nhau cho dễ hiểu nhưng không bắt buộc phải giống.

### 6.2. Đọc sai alias

Nếu query khai báo:

```java
o.get("totalAmount").alias("amount")
```

nhưng service đọc:

```java
row.get("total", BigDecimal.class);
```

thì `"total"` không phải alias đã khai báo. `Tuple` có thể ném `IllegalArgumentException` khi không tìm thấy alias.

**Không nên** catch lỗi alias rồi trả `null` một cách im lặng. Đó là lỗi hợp đồng giữa phần build query và phần đọc kết quả.

### 6.3. Alias nên duy nhất trong cùng Tuple

Không viết:

```java
cq.multiselect(
    o.get("id").alias("value"),
    o.get("totalAmount").alias("value")
);
```

Các selection cùng compound selection có alias explicit bị trùng là tình huống không hợp lệ và có thể làm Criteria query bị từ chối.

Nên dùng tên rõ:

```java
cq.multiselect(
    o.get("id").alias("orderId"),
    o.get("totalAmount").alias("totalAmount")
);
```

### 6.4. Đặt alias ổn định qua thay đổi SELECT order

`cq.multiselect(...)` có thể được sắp xếp lại vì tối ưu/cải tiến query:

```java
cq.multiselect(
    o.get("totalAmount").alias("amount"),
    o.get("id").alias("orderId")
);
```

Code đọc bằng alias:

```java
Long id = row.get("orderId", Long.class);
BigDecimal amount = row.get("amount", BigDecimal.class);
```

vẫn diễn đạt đúng ý định, trong khi code `row.get(0)`/`row.get(1)` sẽ cần cập nhật vì chỉ số thay đổi.

**Lợi ích lớn của alias là giảm phụ thuộc vào thứ tự SELECT, không phải loại bỏ mọi loại lỗi.**

## 7. Đọc theo chỉ số: hợp lệ nhưng cần kiểm soát thứ tự

`Tuple` cũng hỗ trợ truy cập theo vị trí:

```java
cq.multiselect(
    o.get("id").alias("orderId"),
    o.get("status").alias("status"),
    o.get("totalAmount").alias("amount")
);
```

Đọc:

```java
Long id = row.get(0, Long.class);
OrderStatus status = row.get(1, OrderStatus.class);
BigDecimal amount = row.get(2, BigDecimal.class);
```

Chỉ số bắt đầu từ **0**, theo thứ tự các selection được khai báo.

### 7.1. Khi nào dùng index?

- Viết một helper generic xử lý Tuple theo metadata/thứ tự cột.
- Đọc một query rất nhỏ, có kết quả được kiểm soát tại cùng method.
- Tương thích với code xử lý `Object[]` đã tồn tại.
- Phân tích kết quả linh hoạt với một vòng lặp theo `getElements()`.

### 7.2. Nhược điểm của index

`row.get(2, BigDecimal.class)` không tự nói đó là tổng tiền hay thuế. Nếu đổi thứ tự mà hai cột cùng type, compiler không nhận ra logic sai.

Ví dụ:

```java
cq.multiselect(
    o.get("orderNumber"),
    o.get("tenantId")
);

String orderNumber = row.get(1, String.class);
```

Code biên dịch và runtime có thể vẫn thành công, nhưng `row.get(1)` đang đọc **tenantId**, không phải orderNumber.

Với code nghiệp vụ, **ưu tiên alias hoặc đọc qua `TupleElement<T>`**.

### 7.3. Chỉ số không tồn tại

Nếu Tuple có hai selections, gọi:

```java
row.get(2);
```

là truy cập vị trí ngoài phạm vi. JPA có thể ném `IllegalArgumentException` theo contract Tuple, không phải trả `null` như một giá trị “không tồn tại”.

## 8. Đọc bằng TupleElement<T>: gắn kết quả với selection ban đầu

`Tuple` có overload nhận chính **`TupleElement<X>`**:

```java
<X> X get(TupleElement<X> tupleElement);
```

Đây là một cách hay khi code tạo và đọc query trong cùng phạm vi. Ta giữ lại các selection variables.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> o = cq.from(SalesOrder.class);

Path<Long> idPath = o.get("id");
Path<String> numberPath = o.get("orderNumber");
Path<BigDecimal> amountPath = o.get("totalAmount");

cq.multiselect(
    idPath.alias("orderId"),
    numberPath.alias("number"),
    amountPath.alias("amount")
);

List<Tuple> rows = em.createQuery(cq).getResultList();

for (Tuple row : rows) {
    Long id = row.get(idPath);
    String number = row.get(numberPath);
    BigDecimal amount = row.get(amountPath);
}
```

Vì `Path<T>` là một selection/tuple element của Criteria API, generic type của biến `idPath` và `amountPath` giúp Java suy luận kiểu kết quả.

### 8.1. Ưu điểm so với alias String

- Không phải lặp literal `"orderId"` giữa phần tạo và phần đọc.
- Kiểu được suy ra từ `Path<T>`.
- Kết quả gắn với selection tương ứng, dễ đọc trong một method.
- Khi dùng static metamodel, type information còn được lấy từ metadata entity.

### 8.2. Hạn chế

`TupleElement` phải **tương ứng với selection trong Tuple kết quả**. Không tạo một Path tương tự từ CriteriaQuery khác rồi mong `row.get(pathMới)` hoạt động.

Ví dụ:

```java
// Sai tư duy: lấy Path của query A để đọc Tuple do query B trả.
Tuple rowB = ...;
Path<Long> idPathFromQueryA = ...;

Long id = rowB.get(idPathFromQueryA);
```

Điều này không có hợp đồng phù hợp. Mỗi Root/Path/Selection gắn với cấu trúc query được tạo ra.

### 8.3. Chọn cách nào?

| Cách đọc | Ưu điểm | Điểm cần chú ý |
|---|---|---|
| `get("amount", BigDecimal.class)` | Rõ nghĩa, dễ map sang DTO | Alias String vẫn có thể gõ sai |
| `get(2, BigDecimal.class)` | Ngắn, hữu ích cho generic processing | Phụ thuộc thứ tự SELECT |
| `get(amountPath)` | Suy luận generic từ Selection | Phải giữ đúng selection của query |
| `get("amount")` | Linh hoạt | Trả `Object`, phải cast/kiểm tra riêng |

**Trong một repository method cố định**, đọc bằng alias typed hoặc giữ Selection thường là lựa chọn dễ bảo trì. Với bộ truy vấn động, người viết có thể dùng danh sách selection descriptors.

## 9. Typed getter kiểm tra kiểu, nhưng không phải converter tổng quát

Một ưu điểm của:

```java
BigDecimal amount = row.get("amount", BigDecimal.class);
```

là **diễn đạt rõ kiểu mong đợi**. Nếu giá trị không thể gán cho kiểu đó, API có thể ném `IllegalArgumentException`.

Tuy nhiên, đừng hiểu method này như:

```java
// Không có bảo đảm generic rằng API sẽ chuyển String "250000"
// thành BigDecimal chỉ vì bạn yêu cầu BigDecimal.class.
BigDecimal amount = row.get("amount", BigDecimal.class);
```

Nếu query thực sự chọn một `String`, typed getter không phải lời hứa chuyển nó thành `BigDecimal`.

### 9.1. Ví dụ mismatch

Query:

```java
cq.multiselect(
    o.get("orderNumber").alias("number")
);
```

Sai:

```java
Long number = row.get("number", Long.class);
```

`orderNumber` được mapping là `String`, nên yêu cầu `Long.class` không tương thích giá trị.

Đúng:

```java
String number = row.get("number", String.class);
```

### 9.2. Dùng wrapper types thay primitive

Với một thuộc tính số lượng `int` trong entity, Criteria path khi biểu diễn giá trị thường dùng kiểu wrapper `Integer`.

```java
Integer quantity = row.get("quantity", Integer.class);
```

Điều này đặc biệt cần thiết khi projection từ LEFT JOIN có thể tạo giá trị null. Một biến `int` không thể nhận null.

### 9.3. Typed getter không thay kiểm tra null

`BigDecimal.class` mô tả kiểu của một giá trị **nếu nó tồn tại**. Nếu database/query trả SQL NULL, giá trị Java có thể là `null`.

```java
BigDecimal amount =
    row.get("amount", BigDecimal.class);

if (amount == null) {
    // Xử lý null theo hợp đồng nghiệp vụ.
}
```

Không làm:

```java
BigDecimal amount = row.get("amount", BigDecimal.class);
amount.add(BigDecimal.TEN);
```

khi selection có thể null mà chưa kiểm tra.

## 10. Dùng static metamodel để làm kiểu selection rõ hơn

`get("attributeName")` dựa trên String tên thuộc tính; generic type có thể do code tự suy luận hoặc khẳng định.

Nếu project có **static metamodel** được annotation processor sinh:

```java
// Các class SalesOrder_, Customer_ được sinh bởi metamodel generator.
Path<Long> orderId = o.get(SalesOrder_.id);
Path<BigDecimal> amount =
    o.get(SalesOrder_.totalAmount);
```

Mỗi metadata field gắn với entity attribute type. Code:

```java
Path<String> wrong = o.get(SalesOrder_.totalAmount);
```

sẽ gặp bất tương thích generic type tại compile time khi metadata đúng và được cập nhật.

Một query đầy đủ:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> o = cq.from(SalesOrder.class);

Path<Long> id = o.get(SalesOrder_.id);
Path<OrderStatus> status = o.get(SalesOrder_.status);
Path<BigDecimal> amount = o.get(SalesOrder_.totalAmount);

cq.multiselect(
    id.alias("orderId"),
    status.alias("status"),
    amount.alias("amount")
);

for (Tuple tuple : em.createQuery(cq).getResultList()) {
    Long orderId = tuple.get(id);
    OrderStatus orderStatus = tuple.get(status);
    BigDecimal totalAmount = tuple.get(amount);
}
```

### 10.1. Static metamodel và Tuple giải quyết hai lớp khác nhau

- **Static metamodel** giúp kiểm tra **đường dẫn và kiểu thuộc tính entity** khi build Criteria.
- **Tuple** giúp nhận và đọc **các selection của kết quả** theo alias/index/selection.

Dùng cả hai giúp giảm nhiều lỗi tên field và type, nhưng không thay thế kiểm thử semantics SQL, JOIN cardinality, aggregate và các kết quả có null.

### 10.2. get(String) không được đảm bảo type-safe chỉ vì khai báo Path<T>

```java
Path<BigDecimal> wrong =
    o.<BigDecimal>get("orderNumber");
```

Mã có thể compile vì người viết tự chỉ định generic type, nhưng persistent attribute thật là String. Trong khi đó `o.get(SalesOrder_.orderNumber)` mang metadata Java type tương ứng.

Không quảng cáo generic của `get(String)` như bằng chứng mapping hợp lệ.

---

## 11. Truy vấn Tuple với JOIN @ManyToOne

Một trang danh sách Orders cần tên Customer:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> order = cq.from(SalesOrder.class);
Join<SalesOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

cq.multiselect(
    order.get("id").alias("orderId"),
    order.get("orderNumber").alias("orderNumber"),
    customer.get("name").alias("customerName"),
    order.get("status").alias("status"),
    order.get("totalAmount").alias("totalAmount")
);

cq.where(
    cb.equal(order.get("tenantId"), authorizedTenantId)
);

cq.orderBy(
    cb.desc(order.get("createdAt")),
    cb.desc(order.get("id"))
);

List<Tuple> rows = em.createQuery(cq).getResultList();
```

Đọc:

```java
for (Tuple row : rows) {
    Long id = row.get("orderId", Long.class);
    String number = row.get("orderNumber", String.class);
    String customerName =
        row.get("customerName", String.class);
    OrderStatus status =
        row.get("status", OrderStatus.class);
    BigDecimal amount =
        row.get("totalAmount", BigDecimal.class);

    // Ánh xạ sang response phù hợp.
}
```

### 11.1. JOIN ở đây không phải JOIN FETCH

Query trên chỉ cần **`customer.name`** trong kết quả projection. Không cần hydrate toàn bộ Customer entity và không cần `JOIN FETCH`.

`JOIN` thông thường cho phép chọn field từ bảng liên quan. `JOIN FETCH` phù hợp khi trả entity owner và cần association được nạp, không phải cách mặc định để xây mọi Tuple.

### 11.2. To-one thường giữ một row cho một Order

Với `SalesOrder.customer` là many-to-one và khóa ngoại hợp lệ, mỗi Order trỏ tới một Customer. JOIN to-one không tự nhân bản một Order thành nhiều rows do chính quan hệ này.

Nhưng nếu relationship optional, `INNER JOIN` có thể loại Order không có Customer; cân nhắc `LEFT JOIN` khi cần giữ Order và cho phép `customerName = null`.

### 11.3. LEFT JOIN và giá trị null

Giả sử mô hình khác có `SalesOrder.coupon` optional:

```java
Join<SalesOrder, Coupon> coupon =
    order.join("coupon", JoinType.LEFT);

cq.multiselect(
    order.get("id").alias("orderId"),
    coupon.get("code").alias("couponCode")
);
```

Nếu một Order không có Coupon, `couponCode` có thể null:

```java
String couponCode =
    tuple.get("couponCode", String.class);

String label = couponCode == null
    ? "Không dùng mã giảm giá"
    : couponCode;
```

Ví dụ này giả định dự án đã khai báo entity `Coupon` và association `SalesOrder.coupon` phù hợp. Trong mô hình mẫu ban đầu không có `Coupon`; đây là tình huống mở rộng độc lập để minh họa nullable JOIN.

### 11.4. Không để WHERE vô tình biến LEFT thành INNER

Nếu viết:

```java
cq.where(
    cb.equal(coupon.get("code"), requestedCode)
);
```

thì những Orders không có Coupon thường không qua được WHERE, dù JOIN là LEFT. Nếu muốn giữ mọi Order nhưng chỉ đọc Coupon thỏa điều kiện, cần thiết kế JOIN ON/predicate và projection theo semantics mong muốn.

Đây là lỗi logic query, không phải lỗi cách đọc Tuple.

## 12. Khi projection chứa entity cùng scalar

Có thể chọn:

```java
cq.multiselect(
    order.alias("orderEntity"),
    customer.get("name").alias("customerName")
);
```

Đọc:

```java
SalesOrder entity =
    tuple.get("orderEntity", SalesOrder.class);

String customerName =
    tuple.get("customerName", String.class);
```

Nếu selection chứa một entity từ query JPA, entity đó có thể là **managed entity** trong persistence context đang hoạt động. Trong khi đó Tuple chỉ là vật chứa kết quả.

### 12.1. Ưu điểm và rủi ro

Ưu điểm: service có thể vừa sử dụng object entity vừa nhận một scalar tính toán.

Rủi ro:

- Entity mang theo lifecycle/dirty checking.
- Association lazy có thể vẫn chưa tải.
- Khi serialize cả entity có thể vô tình phát sinh N+1 hoặc lộ trường nội bộ.
- Chọn entity đầy đủ tăng lượng state phải hydrate.
- Không còn là projection nhẹ nếu entity có nhiều fields/associations eager.

Nếu mục tiêu chỉ là response chỉ đọc, nên cân nhắc chọn các scalar rồi xây DTO.

### 12.2. Tuple không tự detach entity được chọn

`tuple.get("orderEntity", SalesOrder.class)` không biến entity thành detached snapshot. Cần hiểu context và transaction tương ứng.

**Kết luận:** Có thể trộn entity và scalar, nhưng không nên làm vậy chỉ để né khai báo DTO hoặc để serializer tự duyệt entity graph.

## 13. Chuyển Tuple sang DTO/record ở ranh giới repository

Tuple thuận tiện cho cách xây query. Nhưng trả `Tuple` từ service/REST API khiến tầng gọi biết alias như `"orderId"`, `"customerName"` và phải cast kiểu.

Để giữ contract ổn định, định nghĩa một DTO:

```java
package com.example.shop.readmodel;

import java.math.BigDecimal;
import java.time.Instant;
import com.example.shop.domain.OrderStatus;

public record OrderSummary(
    Long id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) { }
```

Sau đó chuyển ngay trong repository:

```java
private static OrderSummary toOrderSummary(Tuple row) {
    return new OrderSummary(
        row.get("orderId", Long.class),
        row.get("orderNumber", String.class),
        row.get("customerName", String.class),
        row.get("status", OrderStatus.class),
        row.get("totalAmount", BigDecimal.class),
        row.get("createdAt", Instant.class)
    );
}
```

Và:

```java
List<OrderSummary> summaries = em.createQuery(cq)
    .getResultList()
    .stream()
    .map(MyRepository::toOrderSummary)
    .toList();
```

`MyRepository` ở đây là tên giả định của lớp chứa helper. Sử dụng tên class thực tế trong dự án.

### 13.1. Lợi ích tách Tuple khỏi public API

- Alias tồn tại trong repository, không tràn ra controller.
- DTO cung cấp field names và kiểu rõ.
- Service không phải biết chỉ số/alias query.
- Khi sửa query projection, chỉ mapper/repository cần đồng bộ.
- API có thể kiểm soát fields trả ra, tránh lộ dữ liệu entity.
- Dễ unit-test mapping row→DTO độc lập với controller.

### 13.2. Khi nào giữ Tuple ở tầng cao hơn?

Với công cụ report ad-hoc, mỗi report có tập cột động, `Tuple` hoặc một abstraction `List<ColumnValue>` có thể phù hợp hơn DTO cố định. Tuy nhiên vẫn nên chuyển metadata/values sang một định dạng report tự thiết kế tại ranh giới ứng dụng thay vì để JPA-specific type trở thành public API lâu dài.

### 13.3. DTO constructor invariants

Một record có thể kiểm tra đầu vào:

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) {
    public OrderSummary {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(orderNumber, "orderNumber");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(totalAmount, "totalAmount");
    }
}
```

Khi đó nếu Tuple có null ở field bắt buộc, mapper phát hiện sớm. Cần `import java.util.Objects;`. Không thêm non-null rule cho một field thực sự optional, chẳng hạn couponCode từ LEFT JOIN.

---

## 14. Constructor projection: khi không cần Tuple

Với một DTO cố định, Criteria có thể dựng kết quả trực tiếp:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<OrderSummary> cq =
    cb.createQuery(OrderSummary.class);

Root<SalesOrder> order = cq.from(SalesOrder.class);
Join<SalesOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

cq.select(
    cb.construct(
        OrderSummary.class,
        order.get("id"),
        order.get("orderNumber"),
        customer.get("name"),
        order.get("status"),
        order.get("totalAmount"),
        order.get("createdAt")
    )
);

List<OrderSummary> results =
    em.createQuery(cq).getResultList();
```

Ở đây không phải đọc `Tuple`, mà JPA cố dựng `OrderSummary` qua constructor có tham số tương ứng.

### 14.1. So sánh Tuple→DTO và cb.construct

| Tiêu chí | Tuple→DTO | `cb.construct(...)` |
|---|---|---|
| Kiểu query result | `Tuple` | DTO |
| Đọc theo alias | Có | Không cần |
| Mapping ở Java repository | Tường minh | Thông qua constructor result |
| Truy vấn động với nhiều shape | Linh hoạt | Cần constructor/DTO phù hợp mỗi shape |
| Sai thứ tự columns | Alias giúp giảm lỗi nếu mapper đọc theo tên | Thứ tự constructor selection rất quan trọng |
| Sai kiểu selection | Typed Tuple getter giúp phát hiện khi đọc | Có thể lỗi ở query construction/execution khi constructor không khớp |
| Dễ expose tầng service | Nên map thành DTO trước | Có DTO trực tiếp |
| Mang theo entity lifecycle | Không nếu chỉ scalar | Không nếu DTO thường |

### 14.2. Constructor phải khớp thứ tự và kiểu

Với:

```java
record OrderSummary(Long id, String number, BigDecimal amount) {}
```

thì:

```java
cb.construct(
    OrderSummary.class,
    order.get("id"),
    order.get("orderNumber"),
    order.get("totalAmount")
)
```

phải tương thích constructor `(Long, String, BigDecimal)`.

Đảo `orderNumber` và `amount` sẽ tạo mismatch, hoặc nếu hai fields cùng kiểu thì có thể gây dữ liệu sai mà compiler không phát hiện đầy đủ.

### 14.3. JPQL constructor expression

Không cần Criteria khi query cố định:

```java
List<OrderSummary> rows = em.createQuery(
    """
    select new com.example.shop.readmodel.OrderSummary(
        o.id,
        o.orderNumber,
        c.name,
        o.status,
        o.totalAmount,
        o.createdAt
    )
    from SalesOrder o
    join o.customer c
    where o.tenantId = :tenant
    """,
    OrderSummary.class
)
.setParameter("tenant", authorizedTenantId)
.getResultList();
```

JPQL `new ...` là constructor expression. Sử dụng đúng tên class đủ package và constructor công khai/phù hợp mà provider có thể gọi. Java records có public canonical constructor khi khai báo `public record`, nhưng vẫn cần kiểm chứng trên stack JPA/Java thực tế.

### 14.4. Chọn cách theo độ ổn định của shape

- **Shape cố định, business API rõ:** DTO projection thường tốt.
- **Shape thay đổi theo tùy chọn report:** Tuple có alias và metadata hữu ích.
- **Code khảo sát, prototyping ngắn:** Object[] có thể đủ, nhưng nên tránh lan vào nhiều tầng.
- **Cần sửa entity managed:** Truy vấn entity và fetch plan thích hợp, không nhầm DTO với entity.

## 15. Phép tổng hợp COUNT: kiểu Java của kết quả

Tuples thường gặp trong báo cáo:

- Số đơn.
- Tổng tiền.
- Giá trị trung bình.
- Giá trị nhỏ nhất/lớn nhất.

Một quy tắc quan trọng trong JPQL/Criteria: **`COUNT` trả về `Long`**.

Ví dụ:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> o = cq.from(SalesOrder.class);

Expression<Long> countOrders = cb.count(o);

cq.multiselect(
    o.get("status").alias("status"),
    countOrders.alias("orderCount")
);

cq.groupBy(o.get("status"));

List<Tuple> stats = em.createQuery(cq).getResultList();

for (Tuple row : stats) {
    OrderStatus status =
        row.get("status", OrderStatus.class);

    Long count =
        row.get("orderCount", Long.class);
}
```

Không đọc:

```java
Integer count = row.get("orderCount", Integer.class);
```

vì result type của `COUNT` trong JPA không phải mặc định Integer.

### 15.1. SUM, AVG, MIN và MAX

Giá trị aggregate cần nắm kiểu:

| Hàm | Kiểu kết quả JPQL/Criteria điển hình |
|---|---|
| `COUNT(...)` | `Long` |
| `SUM(...)` trên số nguyên thông thường | `Long` theo quy tắc JPQL cho integral types |
| `SUM(...)` trên `BigInteger` | `BigInteger` |
| `SUM(...)` trên `BigDecimal` | `BigDecimal` |
| `SUM(...)` trên floating-point | `Double` |
| `AVG(...)` | `Double` |
| `MIN(...)` / `MAX(...)` | Cùng kiểu của biểu thức được tổng hợp |

Ví dụ tổng tiền:

```java
Expression<BigDecimal> sumAmount =
    cb.sum(o.<BigDecimal>get("totalAmount"));

cq.multiselect(
    o.get("status").alias("status"),
    sumAmount.alias("totalAmount")
);
```

Đọc bằng:

```java
BigDecimal total =
    row.get("totalAmount", BigDecimal.class);
```

### 15.2. AVG không mặc định trả BigDecimal

```java
Expression<Double> average =
    cb.avg(o.<BigDecimal>get("totalAmount"));
```

Đọc:

```java
Double avg = row.get("average", Double.class);
```

Nếu cần tính toán tài chính với precision/rounding nghiêm ngặt, phải định nghĩa quy tắc làm tròn/loại dữ liệu và có thể cần cách tổng hợp khác. Không tự coi `Double` là kiểu tiền tệ chính xác.

### 15.3. Aggregate và tập kết quả rỗng

Với một truy vấn aggregate không GROUP BY:

- `COUNT` trên tập rỗng thường trả `0L`.
- `SUM`, `AVG`, `MIN`, `MAX` có thể trả **null** nếu không có giá trị phù hợp.

Ví dụ:

```java
BigDecimal total =
    row.get("totalAmount", BigDecimal.class);

BigDecimal safeTotal =
    total == null ? BigDecimal.ZERO : total;
```

Chỉ đổi null thành zero khi **đúng ý nghĩa nghiệp vụ**. Ví dụ “không có giao dịch” có thể được hiển thị 0 doanh thu; nhưng “không có giá trị để tính trung bình” không tương đương trung bình bằng 0.

### 15.4. SUM trên field nullable

Nếu `totalAmount` nullable, SQL aggregate `SUM` bỏ qua các giá trị NULL theo semantics thông thường. Nếu mọi row có giá trị null, SUM có thể vẫn null.

Typed Tuple getter cho BigDecimal không tự thay đổi logic NULL của database.

## 16. GROUP BY và HAVING với Tuple

Một báo cáo số đơn và doanh thu theo trạng thái:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<SalesOrder> order = cq.from(SalesOrder.class);

Path<OrderStatus> status =
    order.get("status");

Expression<Long> orderCount =
    cb.count(order);

Expression<BigDecimal> totalAmount =
    cb.sum(order.<BigDecimal>get("totalAmount"));

cq.multiselect(
    status.alias("status"),
    orderCount.alias("orderCount"),
    totalAmount.alias("revenue")
);

cq.groupBy(status);
cq.orderBy(cb.asc(status));

List<Tuple> report =
    em.createQuery(cq).getResultList();
```

Đọc:

```java
for (Tuple t : report) {
    OrderStatus group =
        t.get("status", OrderStatus.class);
    Long count =
        t.get("orderCount", Long.class);
    BigDecimal revenue =
        t.get("revenue", BigDecimal.class);
}
```

Với fixture minh họa ban đầu:

| Status | orderCount | revenue |
|---|---:|---:|
| NEW | 1 | 80000.00 |
| PAID | 2 | 590000.00 |
| CANCELLED | 1 | 50000.00 |

Bảng giả định các đơn không bị thay đổi bởi transaction khác và query không thêm filter.

### 16.1. HAVING lọc nhóm, WHERE lọc rows

Chỉ lấy nhóm có ít nhất hai đơn:

```java
cq.having(
    cb.greaterThanOrEqualTo(orderCount, 2L)
);
```

`WHERE` lọc các Order trước khi nhóm; `HAVING` lọc các nhóm sau khi tổng hợp theo logic query.

Ví dụ:

```java
cq.where(
    cb.equal(order.get("tenantId"), authorizedTenantId)
);

cq.groupBy(status);

cq.having(
    cb.greaterThanOrEqualTo(orderCount, 2L)
);
```

Tổng tiền và số đơn được tính **trong phạm vi tenant** vì WHERE đã giới hạn tập đầu vào.

### 16.2. GROUP BY phải tương thích SELECT

Nếu SELECT vừa lấy status vừa lấy customerName chưa tổng hợp, nhưng chỉ GROUP BY status, query có thể không hợp lệ hoặc cho kết quả không xác định tùy dialect.

Không dùng Tuple như cách “lách” quy tắc SQL/JPQL GROUP BY. Những biểu thức không được aggregate trong SELECT phải có grouping phù hợp theo hợp đồng truy vấn.

### 16.3. Aggregate nhiều biểu thức vẫn có alias riêng

```java
cq.multiselect(
    status.alias("status"),
    orderCount.alias("count"),
    totalAmount.alias("revenue"),
    cb.avg(order.<BigDecimal>get("totalAmount"))
      .alias("average")
);
```

Đọc:

```java
Long count = row.get("count", Long.class);
BigDecimal revenue = row.get("revenue", BigDecimal.class);
Double average = row.get("average", Double.class);
```

Không dùng một generic type duy nhất như Number cho mọi trường khi các loại dữ liệu đã biết rõ và có ý nghĩa nghiệp vụ khác nhau.

## 17. LEFT JOIN và COUNT: phân biệt không có child với một child

Giả sử báo cáo cần Customer và **số Orders** của họ. Muốn giữ cả Customer chưa từng đặt hàng, dùng LEFT JOIN:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<Customer> customer =
    cq.from(Customer.class);

Join<Customer, SalesOrder> orders =
    customer.join("orders", JoinType.LEFT);

Expression<Long> orderCount =
    cb.count(orders);

cq.multiselect(
    customer.get("id").alias("customerId"),
    customer.get("name").alias("customerName"),
    orderCount.alias("orderCount")
);

cq.groupBy(
    customer.get("id"),
    customer.get("name")
);
```

Nếu Customer không có Orders, LEFT JOIN vẫn tạo một joined row chứa `orders = NULL`; `COUNT(orders)` không đếm phần tử null đó nên trả **0**, đúng với “không có Order”.

### 17.1. Vì sao COUNT(root) có thể sai?

Nếu viết:

```java
cb.count(customer)
```

trong LEFT JOIN, root Customer vẫn tồn tại trên joined row. Với Customer không có Order, `COUNT(customer)` có thể trả 1, **không phải 0**.

Muốn đếm child, dùng `COUNT(child)` hoặc expression/ID của child có nghĩa phù hợp:

```java
cb.count(orders);
```

### 17.2. COUNT DISTINCT khi join nhiều relations

Nếu Customer có nhiều Orders và còn JOIN một collection khác, một Order có thể xuất hiện nhiều lần. Khi cần đếm Orders **duy nhất**, cân nhắc:

```java
cb.countDistinct(orders.get("id"));
```

Với aggregate, phải phân biệt **grain**:

- Một row per Customer.
- Một row per Order.
- Một row per OrderLine.

Tuple chỉ là vật chứa kết quả; nó không tự biết business grain và không sửa được phép đếm sai.

## 18. Bẫy nhân bản dữ liệu khi JOIN collection

Một trang danh sách Order chỉ cần Order ID, number, amount và Customer name. JOIN tới Customer (to-one) thường không nhân bản rows. Nhưng nếu thêm:

```java
Join<SalesOrder, OrderLine> line =
    order.join("lines", JoinType.INNER);
```

thì Order#101 có hai lines có thể xuất hiện **hai SQL joined rows**, Order#103 có ba lines thành ba rows.

Nếu query:

```java
cq.multiselect(
    order.get("id").alias("orderId"),
    order.get("totalAmount").alias("amount")
);
```

thì Tuple list có thể có:

```text
(101, 250000.00)
(101, 250000.00)
(103, 340000.00)
(103, 340000.00)
(103, 340000.00)
```

Không được mặc định vì chọn field từ Order nên Tuple mỗi Order chỉ xuất hiện một lần. **Cardinality do FROM/JOIN/WHERE quyết định, không do kiểu container Tuple.**

### 18.1. DISTINCT có thể giải quyết lặp projection đơn giản

```java
cq.distinct(true);
```

với selection chỉ gồm Order ID và amount có thể loại các Tuple trùng nhau. Nhưng:

- DISTINCT có chi phí.
- Nếu SELECT thêm Line SKU, mỗi row có thể khác, nên không còn trùng.
- DISTINCT không thay đổi business grain cho phép tính tổng.
- DISTINCT kết hợp pagination và ORDER BY có thể có ràng buộc SQL/dialect riêng.

### 18.2. EXISTS có thể rõ hơn khi chỉ cần kiểm tra child tồn tại

Tìm Orders chứa ít nhất một Line với SKU BOOK-01:

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<SalesOrder> order = cq.from(SalesOrder.class);

Subquery<Long> subquery = cq.subquery(Long.class);
Root<OrderLine> line = subquery.from(OrderLine.class);

subquery.select(line.<Long>get("id"));

subquery.where(
    cb.equal(line.get("order"), order),
    cb.equal(line.get("sku"), "BOOK-01")
);

cq.multiselect(
    order.get("id").alias("orderId"),
    order.get("orderNumber").alias("orderNumber")
);

cq.where(cb.exists(subquery));
```

`EXISTS` chỉ quyết định root Order có child matching hay không, không JOIN child vào outer result, do đó không nhân bản Order theo số Lines matching.

### 18.3. SUM DISTINCT không phải cách khử trùng entity

Giả sử Order#101 có tổng tiền 250000 và Order#105 cũng có tổng tiền 250000. `SUM(DISTINCT totalAmount)` chỉ cộng một lần giá trị 250000, **không phải một lần mỗi Order**.

Nếu muốn tổng tiền của Orders duy nhất, hãy thiết kế nguồn dữ liệu ở grain Order thay vì dùng DISTINCT trên giá trị amount.

Đây là một lỗi báo cáo rất dễ tồn tại mà không ném exception.

## 19. Phân trang Tuple: setFirstResult và setMaxResults

Khi danh sách có hàng chục nghìn Orders, không đọc tất cả rồi mới lấy 20 dòng ở Java.

Ví dụ:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<SalesOrder> o = cq.from(SalesOrder.class);
Join<SalesOrder, Customer> customer =
    o.join("customer", JoinType.INNER);

cq.multiselect(
    o.get("id").alias("orderId"),
    o.get("orderNumber").alias("orderNumber"),
    customer.get("name").alias("customerName"),
    o.get("totalAmount").alias("amount"),
    o.get("createdAt").alias("createdAt")
);

cq.where(
    cb.equal(o.get("tenantId"), authorizedTenantId)
);

cq.orderBy(
    cb.desc(o.get("createdAt")),
    cb.desc(o.get("id"))
);

int pageIndex = 2;   // Trang thứ ba, tính từ 0.
int pageSize = 20;

List<Tuple> rows = em.createQuery(cq)
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize)
    .getResultList();
```

Ở đây:

- `setFirstResult(40)` bỏ qua 40 kết quả đầu.
- `setMaxResults(20)` giới hạn tối đa 20 kết quả.
- Result vẫn là `List<Tuple>`.
- Chỉ những fields trong multiselect được trả về.
- `ORDER BY createdAt DESC, id DESC` tạo thứ tự rõ hơn nếu nhiều Orders có cùng thời gian.

### 19.1. Vì sao cần tie-breaker ID?

Giả sử hai Orders có cùng `createdAt`. Nếu chỉ sắp theo createdAt, database không bắt buộc trả thứ tự cố định giữa chúng. Khi client đi từ trang này sang trang khác, có thể xảy ra lặp hoặc mất record do thứ tự không ổn định, nhất là khi dữ liệu thay đổi.

Thêm ID vào ORDER BY thường giúp tạo **thứ tự toàn phần** trong tập dữ liệu, miễn ID duy nhất.

### 19.2. Offset phải hợp lệ

Nếu client yêu cầu `pageIndex` âm hoặc `pageSize` cực lớn, cần validate:

```java
int safePage = Math.max(0, requestedPage);
int safeSize = Math.min(Math.max(1, requestedSize), 100);
long offset = (long) safePage * safeSize;

if (offset > Integer.MAX_VALUE) {
    throw new IllegalArgumentException(
        "Requested page offset is too large"
    );
}
```

Sau đó:

```java
.setFirstResult((int) offset)
.setMaxResults(safeSize)
```

Dùng phép nhân `long` trước khi cast để tránh overflow kiểu `int`.

### 19.3. Đừng phân trang sau JOIN collection một cách vô thức

Nếu mỗi Order có nhiều Lines, một JOIN to-many có thể làm một Order chiếm nhiều joined rows. `setMaxResults(20)` có thể giới hạn 20 kết quả Tuple **ở mức joined rows**, không phải 20 Orders duy nhất.

Nếu API cần trang 20 Orders:

- Tránh JOIN collection không cần thiết.
- Dùng `EXISTS` khi chỉ lọc theo child.
- Tổng hợp trước ở grain Order nếu cần chỉ số child.
- Hoặc phân trang Order IDs trước rồi query dữ liệu bổ sung theo IDs.

**Tuple không loại bỏ bẫy pagination theo JOIN cardinality.**

## 20. Truy vấn COUNT riêng cho một trang Tuple

API phân trang thường cần:

- `items`: List DTO của trang hiện tại.
- `totalElements`: tổng số Orders thỏa filter.
- `pageIndex` và `pageSize`.

Không dùng:

```java
long total = rows.size();
```

để suy ra tổng số Orders. `rows.size()` chỉ là số kết quả **trong trang**, có thể nhỏ hơn pageSize ở trang cuối.

Để lấy tổng:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Long> countCq =
    cb.createQuery(Long.class);

Root<SalesOrder> o =
    countCq.from(SalesOrder.class);

countCq.select(cb.count(o));

countCq.where(
    cb.equal(o.get("tenantId"), authorizedTenantId)
);

Long totalElements =
    em.createQuery(countCq).getSingleResult();
```

Đây là query khác, với result type `Long`.

### 20.1. Count query phải có cùng điều kiện lọc

Nếu query trang có:

```java
where tenantId = :tenant
  and status = :status
  and createdAt >= :from
```

mà count query chỉ có tenantId, totalElements sẽ mô tả **tập dữ liệu khác** và API trả thông tin sai.

Giải pháp:

- Có một filter object chứa typed conditions.
- Tái sử dụng logic tạo predicates một cách an toàn trên **Root riêng của từng query**.
- Không tái sử dụng `Predicate`/`Path` được gắn với CriteriaQuery A cho CriteriaQuery B.
- Có tests xác nhận query page và count thống nhất.

### 20.2. Count theo root grain

Nếu filter có JOIN to-many, count query có thể cần `cb.countDistinct(root.get("id"))` hoặc `EXISTS` để đếm Orders duy nhất.

Không mặc định `cb.count(root)` sau JOIN collection là tổng số Orders.

### 20.3. Total count có thể khác snapshot trang

Hai query (page và count) thường là hai SQL statements. Với concurrent inserts/updates/deletes, chúng có thể quan sát những trạng thái dữ liệu khác nhau tùy isolation/transaction.

Nếu cần snapshot nhất quán nghiêm ngặt, phải thiết kế transaction isolation/locking thích hợp. Nếu API chỉ cần pagination thông thường, hiểu và chấp nhận mức biến động phù hợp với sản phẩm.

## 21. Một ví dụ repository hoàn chỉnh: Tuple → DTO → Page

Giả sử API có filter:

```java
public record OrderSearchFilter(
    String authorizedTenantId,
    OrderStatus status,
    Instant fromInclusive,
    Instant toExclusive
) { }
```

Và result page:

```java
public record PageResult<T>(
    List<T> items,
    long totalElements,
    int pageIndex,
    int pageSize
) { }
```

DTO:

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) { }
```

Repository method:

```java
public PageResult<OrderSummary> searchOrders(
        EntityManager em,
        OrderSearchFilter filter,
        int pageIndex,
        int pageSize
) {
    if (pageIndex < 0 || pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException(
            "Invalid page request"
        );
    }

    long offset = (long) pageIndex * pageSize;
    if (offset > Integer.MAX_VALUE) {
        throw new IllegalArgumentException(
            "Page offset is too large"
        );
    }

    CriteriaBuilder cb = em.getCriteriaBuilder();

    // Query #1: trang dữ liệu dưới dạng Tuple.
    CriteriaQuery<Tuple> dataQuery = cb.createTupleQuery();

    Root<SalesOrder> order =
        dataQuery.from(SalesOrder.class);

    Join<SalesOrder, Customer> customer =
        order.join("customer", JoinType.INNER);

    List<Predicate> dataFilters = new ArrayList<>();

    dataFilters.add(
        cb.equal(
            order.get("tenantId"),
            filter.authorizedTenantId()
        )
    );

    if (filter.status() != null) {
        dataFilters.add(
            cb.equal(order.get("status"), filter.status())
        );
    }

    if (filter.fromInclusive() != null) {
        dataFilters.add(
            cb.greaterThanOrEqualTo(
                order.<Instant>get("createdAt"),
                filter.fromInclusive()
            )
        );
    }

    if (filter.toExclusive() != null) {
        dataFilters.add(
            cb.lessThan(
                order.<Instant>get("createdAt"),
                filter.toExclusive()
            )
        );
    }

    dataQuery.multiselect(
        order.get("id").alias("orderId"),
        order.get("orderNumber").alias("orderNumber"),
        customer.get("name").alias("customerName"),
        order.get("status").alias("status"),
        order.get("totalAmount").alias("totalAmount"),
        order.get("createdAt").alias("createdAt")
    );

    dataQuery.where(
        dataFilters.toArray(new Predicate[0])
    );

    dataQuery.orderBy(
        cb.desc(order.get("createdAt")),
        cb.desc(order.get("id"))
    );

    List<OrderSummary> items = em.createQuery(dataQuery)
        .setFirstResult((int) offset)
        .setMaxResults(pageSize)
        .getResultList()
        .stream()
        .map(row -> new OrderSummary(
            row.get("orderId", Long.class),
            row.get("orderNumber", String.class),
            row.get("customerName", String.class),
            row.get("status", OrderStatus.class),
            row.get("totalAmount", BigDecimal.class),
            row.get("createdAt", Instant.class)
        ))
        .toList();

    // Query #2: count, với Root và Predicate riêng.
    CriteriaQuery<Long> countQuery =
        cb.createQuery(Long.class);

    Root<SalesOrder> countRoot =
        countQuery.from(SalesOrder.class);

    List<Predicate> countFilters = new ArrayList<>();

    countFilters.add(
        cb.equal(
            countRoot.get("tenantId"),
            filter.authorizedTenantId()
        )
    );

    if (filter.status() != null) {
        countFilters.add(
            cb.equal(countRoot.get("status"), filter.status())
        );
    }

    if (filter.fromInclusive() != null) {
        countFilters.add(
            cb.greaterThanOrEqualTo(
                countRoot.<Instant>get("createdAt"),
                filter.fromInclusive()
            )
        );
    }

    if (filter.toExclusive() != null) {
        countFilters.add(
            cb.lessThan(
                countRoot.<Instant>get("createdAt"),
                filter.toExclusive()
            )
        );
    }

    countQuery.select(cb.count(countRoot));
    countQuery.where(
        countFilters.toArray(new Predicate[0])
    );

    long totalElements =
        em.createQuery(countQuery).getSingleResult();

    return new PageResult<>(
        items,
        totalElements,
        pageIndex,
        pageSize
    );
}
```

Các imports có thể cần:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.Tuple;
import jakarta.persistence.criteria.*;
import java.util.ArrayList;
import java.util.List;
import java.math.BigDecimal;
import java.time.Instant;
```

### 21.1. Vì sao query này chỉ JOIN Customer?

Trang chỉ cần `customer.name`, nên JOIN to-one là đủ. Không JOIN `order.lines` vì API không hiển thị Lines và không dùng Lines để lọc.

Đây là cách tránh nhân bản rows và giữ pagination theo root Order rõ ràng.

### 21.2. Root của count query phải khác Root của data query

`CriteriaQuery<Tuple>` và `CriteriaQuery<Long>` là hai cây query khác nhau. Không lấy những `Predicate` hoặc `Root` được dựng cho query trang rồi gắn nguyên sang query count.

Trong dự án thật, có thể refactor phần tạo filter bằng helper nhận `CriteriaBuilder` và `Root<SalesOrder>`, sau đó tạo mới predicates cho từng query. Ví dụ code trên viết hai lần để thể hiện ranh giới rõ ràng.

### 21.3. Tên authorizedTenantId là ràng buộc quan trọng

Đối số `filter.authorizedTenantId()` phải được xác định từ security context/authorization rules đáng tin, không chỉ nhận từ request input tùy ý. Projection có thể làm lộ thông tin như tổng tiền, tên khách hàng dù không trả toàn bộ entity.

### 21.4. count và page phải cùng grain

Data query chọn một row per SalesOrder nhờ JOIN Customer to-one. Count query đếm SalesOrder. Nếu tương lai thêm filter JOIN OrderLine, cả hai query cần được thiết kế lại để tránh pagination và count sai.

### 21.5. Không nên coi ví dụ là một framework pagination hoàn chỉnh

Trong production còn có thể cần:

- Kiểm tra null cho filter object và tenant ID.
- Sort key whitelist.
- Stable keyset pagination khi dữ liệu lớn.
- Max offset và query timeout.
- Cơ chế consistency/snapshot rõ theo domain.
- API contract cho trang trống.
- Observability và index.
- Test dưới concurrent modifications.

Nhưng nền tảng vẫn là: **query Tuple chỉ chọn cột cần đọc, count query riêng, DTO trả ra khỏi repository**.

---

## 22. Keyset pagination với Tuple

Khi người dùng cuộn nhiều trang sâu, offset pagination có thể phải duyệt/bỏ qua lượng dữ liệu lớn. Với sort ổn định:

```text
createdAt DESC, id DESC
```

có thể dùng **keyset pagination** dựa trên cursor của dòng cuối trang trước.

Giả sử cursor gồm:

```java
public record OrderCursor(
    Instant createdAt,
    Long id
) { }
```

Điều kiện “sau cursor” theo thứ tự giảm dần:

```text
createdAt < cursorCreatedAt
OR
(createdAt = cursorCreatedAt AND id < cursorId)
```

Criteria:

```java
Path<Instant> createdAt =
    order.get("createdAt");

Path<Long> id =
    order.get("id");

Predicate afterCursor = cb.or(
    cb.lessThan(createdAt, cursor.createdAt()),
    cb.and(
        cb.equal(createdAt, cursor.createdAt()),
        cb.lessThan(id, cursor.id())
    )
);

dataQuery.where(
    cb.equal(order.get("tenantId"), authorizedTenantId),
    afterCursor
);

dataQuery.orderBy(
    cb.desc(createdAt),
    cb.desc(id)
);
```

Sau đó:

```java
List<Tuple> tuples = em.createQuery(dataQuery)
    .setMaxResults(pageSize)
    .getResultList();
```

Vì một Tuple chứa `createdAt` và `orderId`, code có thể xây cursor tiếp theo từ **dòng cuối**:

```java
if (!tuples.isEmpty()) {
    Tuple last = tuples.get(tuples.size() - 1);

    OrderCursor next = new OrderCursor(
        last.get("createdAt", Instant.class),
        last.get("orderId", Long.class)
    );
}
```

### 22.1. Keyset cần điều kiện tiên quyết

- Các cột sort có thể so sánh ổn định; xử lý NULL rõ.
- ID là tie-breaker duy nhất.
- Cursor phải được xác thực/định dạng an toàn.
- Filter của trang tiếp theo phải nhất quán với filter trước.
- Tính bất biến của sort key và concurrent inserts/updates ảnh hưởng trải nghiệm cuộn.
- Có index phù hợp khi cần tối ưu.
- Không dùng JOIN collection làm nhân bản dòng root.

**Tuple rất hợp để mang các khóa cursor**, nhưng keyset pagination là chiến lược truy vấn; nó không tự được Tuple thực hiện.

## 23. Đọc metadata của Tuple qua getElements()

Đôi khi cần xây công cụ report hiển thị cột động. `Tuple` cung cấp:

```java
List<TupleElement<?>> elements = tuple.getElements();
```

Có thể duyệt:

```java
for (TupleElement<?> element : tuple.getElements()) {
    String alias = element.getAlias();
    Class<?> javaType = element.getJavaType();

    Object value = tuple.get(element);

    System.out.println(
        "alias=" + alias +
        ", type=" + javaType.getSimpleName() +
        ", value=" + value
    );
}
```

### 23.1. getAlias có thể null

Nếu selection không được đặt alias explicit, `getAlias()` có thể null. Không coi alias tự sinh là contract ổn định để export JSON/CSV.

Nếu cần cột báo cáo có tên rõ, đặt alias nhất quán ngay trong Criteria selection.

### 23.2. getJavaType phản ánh metadata biểu thức

`element.getJavaType()` thể hiện kiểu Java của selection, **không phải kiểu dữ liệu runtime của mỗi giá trị khác null** và cũng không phải tên SQL column.

Ví dụ:

- Selection `order.get("id")` có type `Long`.
- `cb.count(order)` có type `Long`.
- `cb.avg(...)` có type `Double`.
- `customer.get("name")` có type `String`.

Với expression phức tạp/provider extension, cần kiểm chứng metadata type và actual values trên provider đang sử dụng.

### 23.3. Phân biệt metadata và contract public report

Nếu export báo cáo có cột `amount`, không nhất thiết lộ nguyên `javaType.getName()` cho người dùng. Nên chuyển sang metadata API riêng:

```java
public record ReportColumn(
    String key,
    String label,
    String dataType
) { }
```

Sau đó định nghĩa cách hiển thị theo domain:

- `totalAmount` → “Tổng tiền”, định dạng tiền tệ.
- `createdAt` → “Ngày tạo”, có timezone và format.
- `status` → nhãn trạng thái bản địa hóa.

`Tuple` cung cấp thông tin kỹ thuật; UI/report contract nên được quản lý riêng.

## 24. Chuyển Tuple sang Object[] bằng toArray()

Khi cần kết nối với code cũ:

```java
Object[] values = tuple.toArray();
```

Thứ tự tương ứng với các selection của Tuple. Tuy nhiên cách này mất lợi ích đọc theo alias và kiểu rõ:

```java
Long id = (Long) values[0];
```

Cân nhắc dùng `toArray()` khi:

- Giao diện report generic thật sự làm việc theo cột tuần tự.
- Một thư viện nội bộ chấp nhận row arrays.
- Cần debug/trình bày bảng với column schema được quản lý riêng.

Không dùng nó chỉ vì quen với `Object[]` nếu code có alias/typed selection sẵn.

### 24.1. Không lẫn thứ tự với tên alias

Hai Tuple có cùng aliases nhưng thứ tự `multiselect` khác sẽ tạo `toArray()` với thứ tự khác. Muốn export theo schema ổn định, xây cột theo danh sách alias/column descriptors, không tùy tiện đổi thứ tự SELECT giữa các phiên bản.

## 25. Null và LEFT JOIN: thiết kế DTO an toàn

Một report có thể chọn:

```java
Join<SalesOrder, Coupon> coupon =
    order.join("coupon", JoinType.LEFT);

cq.multiselect(
    order.get("id").alias("orderId"),
    coupon.get("code").alias("couponCode")
);
```

Nếu không có Coupon:

```java
String couponCode =
    row.get("couponCode", String.class); // null hợp lệ.
```

### 25.1. Không nhầm alias không tồn tại với giá trị null

Hai tình huống hoàn toàn khác:

1. Query có alias `couponCode`, nhưng SQL result là NULL → `get` trả null.
2. Query **không có alias** `couponCode` → `get("couponCode", ...)` có thể ném `IllegalArgumentException`.

Không catch exception ở tình huống 2 rồi trả null, vì như vậy một regression khi sửa SELECT bị che khuất.

### 25.2. Dùng CASE/COALESCE khi đúng nghiệp vụ

Có thể tạo một selection fallback:

```java
Expression<String> couponLabel =
    cb.coalesce(
        coupon.<String>get("code"),
        "Không có"
    );

cq.multiselect(
    order.get("id").alias("orderId"),
    couponLabel.alias("couponLabel")
);
```

Nếu nullable column không có giá trị, query trả chuỗi thay thế.

Nhưng:

- “Không có Coupon” và “Coupon code NULL” có thể khác nhau về dữ liệu.
- Fallback text bản địa hóa có thể thuộc UI layer hơn là repository.
- Với aggregate, `COALESCE(SUM(...), 0)` cần chọn literal có kiểu phù hợp BigDecimal/Number để tránh type inference kỳ lạ.

### 25.3. Nullable primitive projection

Không khai báo DTO constructor nhận primitive `int` cho một cột có thể null từ LEFT JOIN. Dùng wrapper `Integer` và xử lý null theo domain.

## 26. Enum, Instant và BigDecimal trong Tuple

Một tập cột có nhiều kiểu:

```java
cq.multiselect(
    order.get("status").alias("status"),
    order.get("createdAt").alias("createdAt"),
    order.get("totalAmount").alias("totalAmount")
);
```

Đọc:

```java
OrderStatus status =
    tuple.get("status", OrderStatus.class);

Instant createdAt =
    tuple.get("createdAt", Instant.class);

BigDecimal totalAmount =
    tuple.get("totalAmount", BigDecimal.class);
```

### 26.1. Enum

Nếu entity có `@Enumerated(EnumType.STRING)`, Criteria projection qua entity attribute thường có Java type là enum `OrderStatus` theo mapping. Không tự ép thành String chỉ vì database lưu tên enum dạng VARCHAR.

Muốn API trả String:

```java
String statusName =
    status == null ? null : status.name();
```

Đó là một quyết định serialization/domain riêng.

### 26.2. Instant

`Instant` là mốc thời gian, không phải chuỗi đã format. Trong DTO, giữ Instant; tại boundary API có thể serialize theo chuẩn thời gian được định nghĩa rõ.

Khi hiển thị ngày theo địa phương, cần timezone. Không dùng `Instant.toString()` rồi giả định nó là ngày theo timezone của người dùng.

### 26.3. BigDecimal

Với tiền:

```java
BigDecimal amount =
    tuple.get("totalAmount", BigDecimal.class);
```

Không chuyển thành `double` chỉ để tiết kiệm một vài dòng code:

```java
double amount = tuple.get("totalAmount", BigDecimal.class)
                     .doubleValue();
```

Có thể mất tính chính xác nhị phân, không phù hợp cho các phép cộng và đối soát tiền tệ nghiêm ngặt.

So sánh `BigDecimal`:

```java
amount.compareTo(new BigDecimal("250000.00")) == 0
```

thường phù hợp khi quan tâm giá trị số học mà không muốn scale khác nhau (`250000.0` và `250000.00`) làm `equals` trả false.

### 26.4. Native scalar query không luôn có cùng type inference

Nếu cùng các cột được chọn bằng **native SQL** mà không có entity/typed result mapping, driver có thể trả `Timestamp`, `Long`, `BigInteger` hoặc kiểu riêng tùy DB.

`Tuple` từ **Criteria projection** trên entity path có metadata JPA type rõ hơn trong nhiều trường hợp. Không dùng những giả định về native JDBC scalar values để ép kết quả Criteria, và ngược lại.

## 27. Khi nào dùng Tuple với native SQL?

Bài tập trung vào JPA Criteria API. Với native SQL:

```java
List<?> rows = em.createNativeQuery(
    """
    SELECT id, order_no, total_amount
    FROM sales_order
    """
).getResultList();
```

Kết quả nhiều cột thường có dạng `Object[]` theo API native query mặc định, hoặc được ánh xạ theo `@SqlResultSetMapping`.

**Không mặc định** một native `createNativeQuery(sql, Tuple.class)` sẽ hoạt động portable ở mọi provider. Một số implementation cung cấp tiện ích transformer/alias-to-tuple riêng, nhưng đó cần được đánh giá theo version/provider.

### 27.1. @ConstructorResult cho native DTO

Nếu muốn hợp đồng DTO rõ:

```java
@SqlResultSetMapping(
    name = "OrderBriefMapping",
    classes = @ConstructorResult(
        targetClass = OrderBrief.class,
        columns = {
            @ColumnResult(name = "order_id", type = Long.class),
            @ColumnResult(name = "order_no", type = String.class),
            @ColumnResult(
                name = "total_amount",
                type = BigDecimal.class
            )
        }
    )
)
```

DTO:

```java
public record OrderBrief(
    Long id,
    String orderNumber,
    BigDecimal totalAmount
) { }
```

SQL:

```sql
SELECT
    id AS order_id,
    order_no,
    total_amount
FROM sales_order;
```

`@ConstructorResult` dùng **thứ tự cột và kiểu** để gọi constructor. Đây là cách JPA chuẩn cho một số native projections, không phụ thuộc vào giả định provider trả `Tuple` từ native SQL.

### 27.2. Phân biệt ba loại alias

- JPQL/Criteria selection alias `"orderId"`.
- Native SQL result label `order_id`.
- Java DTO property `id`.

Chúng có thể khác nhau; mapping layer phải quy định rõ. Không cho rằng alias từ Criteria query là một SQL column name tương ứng trong native query.

## 28. Filter động không có nghĩa alias được chọn tùy ý từ client

Một màn hình báo cáo cho phép chọn cột:

- orderNumber.
- status.
- totalAmount.
- createdAt.

Có thể xây Criteria `multiselect` động. Nhưng **không nhận tùy ý chuỗi field name** do client nhập rồi gọi `root.get(clientField)` mà không kiểm soát.

Ví dụ whitelist:

```java
public enum OrderReportColumn {
    NUMBER,
    STATUS,
    TOTAL_AMOUNT,
    CREATED_AT
}
```

Map mỗi lựa chọn tới typed selection:

```java
private static Selection<?> selectionFor(
        Root<SalesOrder> order,
        OrderReportColumn column
) {
    return switch (column) {
        case NUMBER ->
            order.get("orderNumber").alias("orderNumber");
        case STATUS ->
            order.get("status").alias("status");
        case TOTAL_AMOUNT ->
            order.get("totalAmount").alias("totalAmount");
        case CREATED_AT ->
            order.get("createdAt").alias("createdAt");
    };
}
```

Dùng:

```java
List<Selection<?>> selections = requestedColumns.stream()
    .distinct()
    .map(col -> selectionFor(order, col))
    .toList();

cq.multiselect(selections);
```

Lưu ý:

- Danh sách selection không nên trống nếu query contract yêu cầu ít nhất một cột.
- Aliases explicit phải duy nhất.
- Dùng danh sách cột được whitelist, không cho client truy cập mọi thuộc tính nội bộ.
- Nếu một query chọn tập cột thay đổi, **DTO cố định có thể không phù hợp**; sử dụng cấu trúc report row với metadata riêng.
- Kiểu Java của từng cột phải được khai báo/diễn giải rõ.
- Không cho client chọn JOIN sâu tùy ý làm thay cardinality hoặc vượt permission boundary.

### 28.1. Generic result schema

Một report động có thể trả:

```java
public record ReportColumn(
    String key,
    String label,
    Class<?> javaType
) { }

public record ReportRow(
    Map<String, Object> values
) { }
```

Repository có thể ánh xạ các Tuple values theo danh sách alias được kiểm soát, sau đó chuyển sang JSON/CSV theo schema report.

Nhưng cần lưu ý `Map<String,Object>` ở boundary có ít static type safety hơn DTO. Đổi lại, nó thích hợp khi tập cột không cố định. Với API nghiệp vụ ổn định, ưu tiên DTO typed.

## 29. SQL injection và authorization trong các projection

Criteria API tạo cấu trúc query bằng các đối tượng, nhưng không có nghĩa mọi thao tác động đều an toàn nếu bạn cho client tự quyết định paths và permissions.

Ví dụ:

```java
cq.where(
    cb.equal(order.get("tenantId"), authorizedTenantId)
);
```

`authorizedTenantId` phải lấy từ nguồn đã xác thực. Không để client gửi tenantId bất kỳ rồi dùng trực tiếp mà không kiểm tra quyền.

### 29.1. Tuple có thể làm lộ cột không cần thiết

Nếu một endpoint chỉ cần mã đơn và trạng thái, không chọn email khách hàng, số điện thoại, dữ liệu thanh toán hoặc internal flags rồi trả chúng ra generic Tuple JSON chỉ vì code “có sẵn”.

Cần xác định **allowed selections** trước khi build query.

### 29.2. Tham số giá trị và tên attribute là hai thứ khác nhau

Criteria:

```java
cb.equal(
    order.get("status"),
    requestedStatus
);
```

dùng giá trị request như một expression parameter/literal được provider xử lý theo API, khác với việc nối SQL/JPQL string thủ công.

Nhưng tên path `"status"` là một phần cấu trúc query. Nếu dùng dynamic field names, hãy whitelist thay vì tin input.

### 29.3. Multi-tenant aggregate vẫn nhạy cảm

Một báo cáo chỉ trả:

```text
status = PAID, revenue = 500000000
```

vẫn có thể làm lộ dữ liệu tenant khác nếu thiếu WHERE tenant. Kết quả aggregate không tự an toàn hơn entity result.

## 30. Query động: alias constants và typed extraction

Khi cùng một projection được xây ở nhiều nơi, các alias String có thể bị gõ sai. Có thể nhóm alias thành constants:

```java
public final class OrderTupleAliases {

    public static final String ID = "orderId";
    public static final String NUMBER = "orderNumber";
    public static final String CUSTOMER = "customerName";
    public static final String STATUS = "status";
    public static final String AMOUNT = "totalAmount";
    public static final String CREATED_AT = "createdAt";

    private OrderTupleAliases() {
    }
}
```

Sử dụng:

```java
cq.multiselect(
    order.get("id").alias(OrderTupleAliases.ID),
    order.get("totalAmount").alias(OrderTupleAliases.AMOUNT)
);
```

Đọc:

```java
Long id =
    row.get(OrderTupleAliases.ID, Long.class);

BigDecimal amount =
    row.get(OrderTupleAliases.AMOUNT, BigDecimal.class);
```

Đây là cách giảm lỗi typo alias, nhưng không biến String-based path `order.get("id")` thành compile-time metadata access. Nếu muốn typed paths tốt hơn, kết hợp static metamodel.

### 30.1. Helper đọc Tuple có tên và kiểu

Có thể định nghĩa:

```java
private static <T> T required(
        Tuple tuple,
        String alias,
        Class<T> type
) {
    T value = tuple.get(alias, type);

    if (value == null) {
        throw new IllegalStateException(
            "Required tuple value is null: " + alias
        );
    }

    return value;
}
```

Dùng:

```java
Long id = required(
    tuple,
    OrderTupleAliases.ID,
    Long.class
);
```

Helper này **chỉ phù hợp cho cột bắt buộc**. Đừng áp nó cho mọi selection nullable từ LEFT JOIN/aggregate.

### 30.2. Không che lỗi kiểu

Tránh helper:

```java
private static String readAny(Tuple row, String alias) {
    Object value = row.get(alias);
    return String.valueOf(value);
}
```

nếu domain cần giữ `BigDecimal`, `Instant` hoặc enum. Cách ép mọi thứ thành String làm mất type information và dễ gây lỗi serialization/tính toán sau đó.

## 31. Tuple và hiệu năng: ít cột hơn không tự bảo đảm nhanh

Một projection chỉ chọn bốn cột có thể tiết kiệm hơn việc hydrate entity đầy đủ, nhưng hiệu năng còn phụ thuộc:

- Số rows.
- JOIN cardinality.
- Cấu trúc WHERE, ORDER BY, GROUP BY.
- Index và query plan.
- Chi phí sorting/aggregation.
- DTO mapping overhead.
- Database/network RTT.
- Cấu trúc pagination.
- Số query bổ sung do code sau đó truy cập entity relationships.
- Khả năng tận dụng covering index hoặc expression index.

### 31.1. Projection tốt khi chỉ cần dữ liệu đọc

Một trang có 20 Orders × 6 cột thường nhẹ hơn tải 20 Order entities với các association không cần thiết. Nhưng nếu query JOIN một collection lớn, có thể vẫn trả hàng nghìn joined rows.

**Tối ưu SELECT columns và tối ưu FROM/JOIN cardinality là hai việc khác nhau.**

### 31.2. Không gom mọi truy vấn thành một báo cáo “siêu Tuple”

Một query chọn:

- Đơn hàng.
- Tên khách hàng.
- Tất cả SKU.
- Tổng tiền.
- Số comments.
- Số sản phẩm hoàn trả.

có thể bị nhân bản dữ liệu qua nhiều JOIN collections. Đôi khi tách thành:

1. Query Order summary page.
2. Query các aggregates đã nhóm theo Order IDs.
3. Assemble DTO in memory.

sẽ rõ và hiệu quả hơn một query rất rộng.

### 31.3. Count query có thể là bottleneck riêng

Với pagination, `COUNT(*)` trên tập dữ liệu rất lớn và filter phức tạp có thể tốn chi phí. Nếu product không cần exact total mỗi request, cân nhắc response kiểu slice/“hasMore” (đọc pageSize+1 rows) hoặc keyset pagination.

Đó là quyết định API product, không phải tính năng riêng của Tuple.

### 31.4. Không giữ List<Tuple> khổng lồ khi export

Với report hàng triệu rows, `getResultList()` có thể làm tăng memory. Cân nhắc phân trang/chunk, cơ chế stream/cursor thích hợp theo provider và transaction, hoặc đọc theo batch sang output writer. `getResultStream()` có thể tồn tại trong API nhưng hành vi memory/streaming thật phụ thuộc provider/driver; không mặc định nó là cursor tiết kiệm bộ nhớ trong mọi môi trường.

## 32. Tuple và EntityGraph/JOIN FETCH

Khi query **chỉ chọn scalar projection**:

```java
cq.multiselect(
    order.get("id").alias("id"),
    customer.get("name").alias("customerName")
);
```

không cần `JOIN FETCH`; `JOIN` thường là công cụ đúng.

Nếu query trả entity owner, fetch plan có thể cần EntityGraph/`JOIN FETCH` theo use case. Nhưng **không thêm `JOIN FETCH` vào tuple projection chỉ gồm scalar/DTO mà không chọn owner**; trong JPQL, fetched association phải thuộc entity owner có mặt trong kết quả theo semantics tương ứng.

### 32.1. Một lựa chọn tốt cho màn hình danh sách

- Tuple/DTO: Order ID, status, amount, customerName.
- JOIN Customer to-one.
- Pagination root stable.
- Không fetch Lines.
- Không serialize entity.

### 32.2. Một lựa chọn tốt cho màn hình chi tiết

- Truy vấn một SalesOrder entity.
- Fetch Customer và có thể một collection Lines có kích thước hợp lý.
- Map sang detail DTO trong transaction.
- Không phải mọi endpoint đều dùng một projection giống nhau.

Kế hoạch tải và projection phải được chọn theo **dữ liệu service cần sử dụng**, không chỉ theo thói quen code.

## 33. Những lỗi thường gặp khi dùng Tuple

### 33.1. Dùng Object[] nhưng đọc nhầm thứ tự

`(String) row[0]` có thể được dùng cho orderNumber trong khi SELECT thứ tự đầu là customerName. Tuple alias giúp làm rõ.

### 33.2. Tạo CriteriaQuery<Entity> rồi multiselect nhiều scalar

`CriteriaQuery<SalesOrder>` yêu cầu result type SalesOrder, không phải Tuple nhiều cột. Dùng `cb.createTupleQuery()` khi muốn `List<Tuple>`.

### 33.3. Không đặt alias nhưng gọi get(String)

Nếu chưa khai báo `.alias("amount")`, không nên kỳ vọng alias `"amount"` tự xuất hiện.

### 33.4. Gõ sai alias

`row.get("total", BigDecimal.class)` không khớp `.alias("totalAmount")`. Đây là lỗi hợp đồng, không phải giá trị null.

### 33.5. Trùng alias

Hai selection cùng alias explicit là không hợp lệ. Đặt tên duy nhất.

### 33.6. Đọc index ngoài phạm vi

Tuple có hai selections nhưng gọi `get(2)`. Chỉ số bắt đầu từ 0.

### 33.7. Khẳng định sai type

`row.get("orderCount", Integer.class)` trong khi `COUNT` trả Long. Dùng `Long.class`.

### 33.8. Cho rằng get(alias, Class) tự parse String

Typed getter không phải JSON parser/converter tổng quát. Không mặc định biến `"250000"` thành `BigDecimal`.

### 33.9. Quên nullable values

LEFT JOIN hoặc aggregate trên tập rỗng có thể trả null. Dùng wrapper/reference types và validation phù hợp.

### 33.10. Cho rằng Tuple là entity managed

Tuple là result container, không được `persist`/dirty-check; entity được chọn như một giá trị bên trong Tuple có thể managed nhưng bản thân Tuple thì không.

### 33.11. Dùng Tuple làm public API contract lâu dài

Điều này làm service/controller phụ thuộc JPA aliases. Thường nên chuyển sang DTO/record ở repository boundary.

### 33.12. Dùng JOIN FETCH để chọn scalar

Không cần tải entity graph khi chỉ cần một số cột. Dùng JOIN thường/DTO.

### 33.13. JOIN to-many khiến một Order thành nhiều Tuple rows

Đúng SQL cardinality nhưng sai kỳ vọng pagination theo Order. Dùng EXISTS/grouping/tách query.

### 33.14. COUNT(o) sau LEFT JOIN khi muốn đếm children

Root luôn tồn tại, có thể cho 1 ở parent không có child. Dùng `COUNT(child)`.

### 33.15. SUM(DISTINCT amount) để khử trùng Orders

Khử trùng **giá trị amount**, không khử trùng entity Order. Thiết kế query đúng grain.

### 33.16. AVG được đọc như BigDecimal

Theo JPQL/Criteria aggregate semantics phổ biến, `AVG` trả Double. Cần xử lý precision/rounding có chủ đích.

### 33.17. getResultList().size() là totalElements

Đó chỉ là kích thước list kết quả hiện tại/trang hiện tại. Cần count query hoặc contract pagination khác.

### 33.18. ORDER BY chỉ createdAt

Các Orders cùng timestamp có thể không có thứ tự ổn định. Thêm tie-breaker ID.

### 33.19. Chỉ đổi SELECT fields nhưng quên mapper

Alias hoặc type mới không tương thích DTO constructor. Viết mapper tập trung và có tests.

### 33.20. Dùng cùng Predicate/Root cho hai CriteriaQuery

Root/Predicate gắn với query hiện tại. Build riêng cho data và count queries.

### 33.21. Dùng TupleElement từ query khác

`tuple.get(element)` phải dùng element tương ứng với selection của Tuple đó; không tái dùng Path từ query khác.

### 33.22. Tự tạo query shape từ user fields không whitelist

Có thể lộ attributes nội bộ hoặc JOIN paths không được phép. Dùng enum/whitelist/authorization.

### 33.23. Phân trang sau JOIN collection và nghĩ DISTINCT luôn cứu được

Nếu JOIN làm rows nhân bản, DISTINCT có thể không giải quyết mọi nhu cầu phân trang/performance và aggregate. Tránh JOIN collection khi chỉ cần root page.

### 33.24. Nhầm native JDBC scalar với Criteria entity-path type

Native `COUNT(*)` có thể trả subtype Number theo driver, trong khi JPQL/Criteria `COUNT` có contract Long. Không ép mọi loại query result bằng một quy tắc.

### 33.25. Truy vấn mỗi trang nhưng không giới hạn pageSize

Có thể đọc nhiều dữ liệu ngoài kiểm soát. Validate và cap pageSize.

### 33.26. Ghi log toàn bộ Tuple values

Tuple có thể chứa email, tổng tiền, thông tin cá nhân hoặc trường nhạy cảm. Chỉ log metadata/counters khi phù hợp, tránh log payload production không cần thiết.

### 33.27. Tự động biến mọi Tuple thành Map rồi deserialize lại thành DTO

Cách này làm mất static type safety, tăng bước chuyển đổi và có thể lỗi numeric/temporal serialization. Với DTO cố định, map typed trực tiếp.

### 33.28. Coi compile thành công là đủ

Java compiler không xác minh mọi alias, SQL semantics, join cardinality hoặc constructor projection; integration test vẫn cần.

---

## 34. Kiểm thử Tuple projection

Để kiểm tra chính xác một projection, nên dùng integration test với provider/database mục tiêu thay vì chỉ mock `EntityManager`.

### 34.1. Kiểm thử alias và type

Fixture có Order#101:

```text
orderId     = 101
orderNumber = SO-101
status      = PAID
totalAmount = 250000.00
```

Query:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<SalesOrder> order = cq.from(SalesOrder.class);

cq.multiselect(
    order.get("id").alias("orderId"),
    order.get("orderNumber").alias("number"),
    order.get("totalAmount").alias("amount")
);

cq.where(cb.equal(order.get("id"), 101L));

Tuple row = em.createQuery(cq).getSingleResult();
```

Assertions gợi ý:

```java
assertEquals(101L, row.get("orderId", Long.class));
assertEquals("SO-101", row.get("number", String.class));
assertEquals(
    0,
    row.get("amount", BigDecimal.class)
       .compareTo(new BigDecimal("250000.00"))
);
```

Các assertions minh họa theo phong cách JUnit; setup fixture/import/transaction của test phụ thuộc dự án.

### 34.2. Kiểm thử đọc theo index

Với select orderId, number, amount:

```java
assertEquals(101L, row.get(0, Long.class));
assertEquals("SO-101", row.get(1, String.class));
```

Kiểm thử để hiểu contract index, nhưng code nghiệp vụ dài hạn thường nên đọc alias.

### 34.3. Kiểm thử TupleElement

Giữ selection:

```java
Path<Long> idPath = order.get("id");

cq.multiselect(
    idPath.alias("orderId")
);
```

Sau khi query thực thi:

```java
Long id = tuple.get(idPath);
```

Kỳ vọng id bằng fixture. Không tạo Root/Path mới sau khi đã lấy Tuple để dùng trong `get`.

### 34.4. Kiểm thử NULL

Dùng optional LEFT JOIN fixture không có association, assert alias vẫn tồn tại nhưng value null:

```java
assertNull(row.get("optionalLabel", String.class));
```

Phân biệt với alias không tồn tại:

```java
assertThrows(
    IllegalArgumentException.class,
    () -> row.get("unknownAlias", String.class)
);
```

### 34.5. Kiểm thử GROUP BY và COUNT type

Fixture có:

```text
PAID: 2 orders
NEW: 1 order
```

Assert `row.get("orderCount", Long.class)` trả 2L hoặc 1L theo status; không assume Integer.

### 34.6. Kiểm thử SUM/AVG nullable

Tạo tenant không có Order phù hợp, thử aggregate không GROUP BY và kiểm tra COUNT=0/SUM có thể null. Nếu dùng COALESCE, kiểm tra kiểu kết quả và giá trị fallback theo contract.

### 34.7. Kiểm thử LEFT JOIN child count

Tạo một Customer không có Orders. Query LEFT JOIN + `COUNT(orders)` phải cho 0, không phải 1.

### 34.8. Kiểm thử pagination và count query

Tạo 53 Orders với createdAt và ID kiểm soát:

- Trang 0, size 20 → tối đa 20 rows.
- Trang 1, size 20 → tối đa 20 rows.
- Trang 2, size 20 → 13 rows.
- Count query → 53.
- Không lặp IDs giữa các trang trong fixture bất biến.
- Thứ tự theo `createdAt DESC, id DESC` đúng.

### 34.9. Kiểm thử JOIN to-many không gây count sai

Tạo Order#101 có ba Lines. Query JOIN child có thể tạo ba Tuple rows. Nếu API mong mỗi Order một row, test phải phát hiện để sửa query (EXISTS/grouping hoặc data shape khác).

### 34.10. Kiểm thử security tenant

Tạo shop-a và shop-b có Orders. Query với `authorizedTenantId="shop-a"` không được trả Order của shop-b. Với aggregate doanh thu, kiểm tra số tổng cũng chỉ tính shop-a.

### 34.11. Kiểm thử kiểu trên database thật

Các loại như `BigDecimal`, `Instant`, UUID, enum và aggregate có thể bị ảnh hưởng bởi JPA provider, JDBC driver và SQL dialect. Với báo cáo quan trọng, dùng integration test trên stack tương thích production để khẳng định type conversion và kết quả.

Các kiểm thử trên là **hướng dẫn thực hành trong bài học**, không phải lượt QA tự động đối với Markdown này.

## 35. Bài tập thực hành có gợi ý

### Bài 1 — Tạo Tuple ba cột

**Yêu cầu:** Tạo Criteria query trả Order ID, orderNumber, totalAmount dưới dạng `Tuple`.

**Gợi ý:**

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<SalesOrder> o = cq.from(SalesOrder.class);

cq.multiselect(
    o.get("id").alias("id"),
    o.get("orderNumber").alias("number"),
    o.get("totalAmount").alias("amount")
);
```

### Bài 2 — Đọc alias typed

**Yêu cầu:** Đọc kết quả bài 1.

**Gợi ý:**

```java
Long id = row.get("id", Long.class);
String number = row.get("number", String.class);
BigDecimal amount = row.get("amount", BigDecimal.class);
```

### Bài 3 — Đọc theo index

**Câu hỏi:** Với multiselect ID, number, amount, index của amount là bao nhiêu?

**Gợi ý:** `2`, vì index bắt đầu từ 0.

### Bài 4 — Không có alias

Query chọn `o.get("totalAmount")` mà không alias.

**Câu hỏi:** Có nên mặc định `tuple.get("totalAmount", BigDecimal.class)` chạy không?

**Gợi ý:** Không. Đặt `.alias("totalAmount")` nếu muốn đọc theo tên.

### Bài 5 — Trùng alias

Hai selection đều có `.alias("value")`.

**Câu hỏi:** Có vấn đề gì?

**Gợi ý:** Alias explicit trùng trong một compound selection là không hợp lệ.

### Bài 6 — Sai type

`status` là `OrderStatus`, nhưng code:

```java
String s = row.get("status", String.class);
```

**Gợi ý:** Criteria projection trên enum path có Java type enum; dùng `OrderStatus.class`, rồi đổi sang String tại DTO boundary nếu cần.

### Bài 7 — Đọc qua TupleElement

**Yêu cầu:** Giữ `Path<BigDecimal> amountPath` từ Criteria query và đọc value mà không dùng alias.

**Gợi ý:**

```java
Path<BigDecimal> amountPath = o.get("totalAmount");

cq.multiselect(amountPath.alias("amount"));

BigDecimal amount = row.get(amountPath);
```

### Bài 8 — JPQL nhiều cột

```jpql
select o.id, o.orderNumber from SalesOrder o
```

**Câu hỏi:** Dạng result mặc định của query nhiều expression là gì?

**Gợi ý:** Thông thường `Object[]` per row nếu dùng JPQL Query không có constructor projection.

### Bài 9 — Tuple khác Entity?

**Câu hỏi:** Có thể `em.persist(tuple)` để lưu thay đổi trên Tuple không?

**Gợi ý:** Không. Tuple không phải entity.

### Bài 10 — JOIN Customer

**Yêu cầu:** Thêm customerName vào Tuple nhưng không tải toàn bộ Customer graph.

**Gợi ý:**

```java
Join<SalesOrder, Customer> c = o.join("customer");
cq.multiselect(
    o.get("id").alias("orderId"),
    c.get("name").alias("customerName")
);
```

### Bài 11 — LEFT JOIN nullable

**Yêu cầu:** Đọc couponCode khi Order có thể không có Coupon.

**Gợi ý:** `JoinType.LEFT`, `row.get("couponCode", String.class)` và xử lý null.

### Bài 12 — COUNT là kiểu gì?

**Câu hỏi:** `cb.count(o)` trả `Expression<Integer>` hay `Expression<Long>`?

**Đáp án:** `Expression<Long>`.

### Bài 13 — SUM BigDecimal

**Yêu cầu:** Tính tổng `totalAmount` trong một status group.

**Gợi ý:**

```java
Expression<BigDecimal> total =
    cb.sum(o.<BigDecimal>get("totalAmount"));
```

Đọc bằng `BigDecimal.class`.

### Bài 14 — AVG

**Câu hỏi:** Đọc `cb.avg(...)` bằng kiểu nào?

**Gợi ý:** `Double.class` theo JPQL/Criteria aggregate semantics.

### Bài 15 — Tập rỗng và SUM

**Câu hỏi:** Vì sao `SUM` có thể null nhưng `COUNT` trả 0?

**Gợi ý:** Aggregate semantics khác nhau trên tập không có giá trị để tính.

### Bài 16 — GROUP BY

**Yêu cầu:** Trả Tuple gồm status, orderCount, sumAmount.

**Gợi ý:** `multiselect` ba biểu thức có alias; `groupBy(o.get("status"))`.

### Bài 17 — Đếm child khi LEFT JOIN

Một Customer chưa có Order.

**Câu hỏi:** `COUNT(customer)` hay `COUNT(ordersJoin)` biểu diễn số Orders?

**Đáp án:** `COUNT(ordersJoin)`.

### Bài 18 — JOIN làm nhân bản

Order#101 có ba Lines. Query chọn Order ID sau JOIN Lines không DISTINCT.

**Câu hỏi:** Có thể nhận bao nhiêu Tuple rows cho Order#101?

**Gợi ý:** Ba joined rows, không tự thành một chỉ vì chọn ID root.

### Bài 19 — EXISTS thay JOIN

**Yêu cầu:** Tìm Orders có Line SKU BOOK-01 nhưng không nhân bản Order theo số Lines thỏa.

**Gợi ý:** Subquery `EXISTS` kết hợp outer query chọn Order ID/fields.

### Bài 20 — SUM DISTINCT amount

Hai Orders cùng amount 250000.

**Câu hỏi:** `SUM(DISTINCT amount)` có cộng hai Order không?

**Gợi ý:** Không; DISTINCT áp dụng lên **giá trị** amount. Không dùng để khử trùng entity.

### Bài 21 — DTO mapping

**Yêu cầu:** Chuyển Tuple có alias id, number, amount thành `OrderBrief` record.

**Gợi ý:** Gọi constructor với typed `tuple.get`, map ngay tại repository.

### Bài 22 — Constructor projection

**Yêu cầu:** Thay Tuple bằng `cb.construct(OrderBrief.class, ...)`.

**Gợi ý:** `CriteriaQuery<OrderBrief>` và đúng thứ tự constructor parameters.

### Bài 23 — Pagination

**Yêu cầu:** Lấy trang 3 (zero-based index 2), pageSize 20.

**Gợi ý:** `setFirstResult(40)` và `setMaxResults(20)`, có `ORDER BY` ổn định.

### Bài 24 — Total count

**Câu hỏi:** Trang chỉ có 13 rows có nghĩa database tổng cộng 13 Orders?

**Gợi ý:** Không. Dùng count query riêng cùng filter.

### Bài 25 — Sort ổn định

Hai Orders cùng createdAt.

**Gợi ý:** Thêm `ORDER BY createdAt DESC, id DESC`.

### Bài 26 — CountRoot khác dataRoot

**Câu hỏi:** Có nên dùng cùng `Root<SalesOrder>` từ CriteriaQuery<Tuple> để xây CriteriaQuery<Long> count?

**Gợi ý:** Không. Root/Predicates gắn với cây Criteria riêng; tạo mới trong query count.

### Bài 27 — Keyset cursor

**Yêu cầu:** Lấy createdAt và id của Tuple cuối để xây cursor trang tiếp.

**Gợi ý:**

```java
Tuple last = rows.get(rows.size() - 1);

OrderCursor cursor = new OrderCursor(
    last.get("createdAt", Instant.class),
    last.get("orderId", Long.class)
);
```

Nhớ xử lý rows rỗng.

### Bài 28 — getElements

**Yêu cầu:** In alias và Java type của mỗi Tuple element.

**Gợi ý:**

```java
for (TupleElement<?> element : row.getElements()) {
    System.out.println(
        element.getAlias() + " : " +
        element.getJavaType()
    );
}
```

### Bài 29 — Native SQL và Tuple

**Câu hỏi:** Mọi provider có hỗ trợ `createNativeQuery(sql, Tuple.class)` như một cách portable để đọc alias không?

**Gợi ý:** Không giả định; native queries thường dùng Object[]/scalar hoặc `@SqlResultSetMapping`, tùy yêu cầu và provider.

### Bài 30 — Security report

Một Tuple report chỉ trả aggregate revenue nhưng không lọc tenant.

**Câu hỏi:** Có an toàn không?

**Gợi ý:** Không; aggregates vẫn có thể lộ thông tin của tenant khác. Điều kiện tenant phải lấy từ authorization context.

---

## 36. Bảng tra cứu nhanh

| Mục đích | Cách làm |
|---|---|
| Tạo Criteria query trả Tuple | `cb.createTupleQuery()` |
| Tạo root | `cq.from(SalesOrder.class)` |
| Chọn nhiều cột | `cq.multiselect(...)` |
| Chọn Tuple bằng CriteriaBuilder | `cq.select(cb.tuple(...))` |
| Đặt alias | `selection.alias("orderId")` |
| Đọc theo alias typed | `tuple.get("orderId", Long.class)` |
| Đọc theo alias raw | `tuple.get("orderId")` |
| Đọc theo index typed | `tuple.get(0, Long.class)` |
| Đọc theo TupleElement | `tuple.get(idPath)` |
| Chuyển thành Object[] | `tuple.toArray()` |
| Lấy metadata selection | `tuple.getElements()` |
| Lấy alias metadata | `element.getAlias()` |
| Lấy Java type metadata | `element.getJavaType()` |
| JOIN Customer để chọn name | `order.join("customer")` |
| Giữ Order với optional relation | `JoinType.LEFT` |
| Đếm Orders | `cb.count(order)`, kiểu Long |
| Đếm unique Orders khi JOIN | `cb.countDistinct(order.get("id"))` |
| Tổng tiền BigDecimal | `cb.sum(order.<BigDecimal>get("totalAmount"))` |
| Trung bình | `cb.avg(...)`, kiểu Double |
| Nhóm dữ liệu | `cq.groupBy(path)` |
| Lọc nhóm | `cq.having(predicate)` |
| Distinct kết quả | `cq.distinct(true)` |
| Sắp xếp | `cq.orderBy(cb.desc(path), cb.desc(id))` |
| Offset trang | `query.setFirstResult(offset)` |
| Kích thước trang | `query.setMaxResults(pageSize)` |
| Total count | Query `CriteriaQuery<Long>` riêng |
| DTO trực tiếp từ Criteria | `cb.construct(Dto.class, ...)` |
| DTO trực tiếp từ JPQL | `select new package.Dto(...)` |
| Native SQL DTO mapping | `@ConstructorResult` |
| Filter child mà tránh JOIN duplicate | `EXISTS` |
| Tránh trả JPA Tuple ra API | Map Tuple thành DTO trong repository |

## 37. Quy trình chọn Tuple hay DTO

```text
              Cần đọc kết quả truy vấn?
                         |
                         v
              Kết quả là entity đầy đủ?
                  /               \
                 Có               Không
                 |                  |
                 v                  v
            Entity query       Chỉ một scalar?
            + fetch plan         /       \
                                Có       Không
                                 |          |
                                 v          v
                           Typed scalar   Nhiều cột
                                              |
                                   Shape cố định?
                                     /       \
                                   Có        Không
                                    |           |
                                    v           v
                              DTO projection   Tuple
                              hoặc Tuple→DTO     |
                                    |            v
                                    |       Alias + type
                                    |       + metadata schema
                                    +------------+
                                                 |
                                                 v
                                       Có pagination?
                                          /    \
                                         Có    Không
                                          |      |
                                          v      |
                                       Stable   |
                                       ORDER BY |
                                       page/count
                                          |      |
                                          +------+
                                             |
                                             v
                                       Kiểm tra JOIN
                                       cardinality, NULL,
                                       types và tenant
                                             |
                                             v
                                       Tạo response
```

Một quy trình thực tế:

1. **Xác định fields cần trả** trước khi quyết định query.
2. **Chọn root grain**: mỗi dòng là một Order, một Customer hay một nhóm aggregate?
3. **Chọn result type**: entity, scalar, Tuple hay DTO.
4. **Nếu dùng Tuple, khai báo alias duy nhất và có nghĩa** cho các selection được đọc theo tên.
5. **Dùng kiểu Java phù hợp**: Long cho COUNT, BigDecimal cho tiền, enum cho status, Instant cho mốc thời gian.
6. **Xử lý NULL chủ đích** từ LEFT JOIN/aggregate.
7. **Tránh JOIN collection không cần thiết** khi pagination phải theo root.
8. **Sắp thứ tự ổn định** khi có pagination.
9. **Xây count query riêng** với cùng filter và đúng grain.
10. **Map Tuple sang DTO** tại repository boundary nếu API shape cố định.
11. **Giữ tenant/authorization scope** ở mọi query, kể cả aggregate.
12. **Kiểm thử cùng database/provider mục tiêu** với dữ liệu có null, duplicate rows, nhiều trạng thái và các kiểu số/thời gian khác nhau.

## 38. Tổng kết

Những điểm quan trọng nhất:

1. **`Tuple` là vật chứa một dòng kết quả projection**, không phải entity managed hay DTO mặc định.
2. **`CriteriaBuilder.createTupleQuery()`** là cách rõ ràng để tạo Criteria query trả `Tuple`.
3. **`multiselect(...)`** quyết định các biểu thức được trả; **`alias(...)`** giúp đọc bằng tên thay vì nhớ chỉ số.
4. **`tuple.get("alias", Type.class)`** làm rõ kiểu mong đợi và phát hiện một số lỗi mismatch, nhưng không tự chuyển mọi giá trị sang kiểu bất kỳ.
5. **`tuple.get(index, Type.class)`** hợp lệ nhưng phụ thuộc thứ tự SELECT; index bắt đầu từ 0.
6. **`tuple.get(TupleElement<T>)`** giúp đọc qua selection gốc có generic type rõ, miễn là element thực sự thuộc Tuple kết quả.
7. **`TupleElement.getAlias()` và `getJavaType()`** hữu ích cho report động, nhưng alias không được đặt có thể null.
8. **Static metamodel** cải thiện kiểm tra type ở đường dẫn entity, còn Tuple giúp đọc kết quả projection; hai lớp bổ trợ nhau.
9. **`COUNT` là Long, `AVG` thường là Double, `SUM(BigDecimal)` là BigDecimal** theo aggregate semantics; luôn lưu ý `null` trên tập rỗng.
10. **JOIN to-many có thể nhân bản Tuple rows**, khiến SUM/COUNT và pagination sai nếu không xác định đúng grain.
11. **Tuple không tự giải quyết pagination**: vẫn cần ORDER BY ổn định, giới hạn pageSize và count query riêng.
12. **DTO/record thường phù hợp hơn làm contract dịch vụ/API**; Tuple hữu ích ở repository/query builder hoặc báo cáo có shape động.
13. **Tuple trong native SQL không mặc nhiên portable** như Tuple trong Criteria API; với native projections có thể dùng Object[]/`@SqlResultSetMapping`.
14. **Bảo mật và hiệu năng không tự đến từ projection**: cần tenant scope, whitelist, query plan và integration tests.

**Kết luận:** `Tuple` là lựa chọn mạnh khi ứng dụng JPA cần **đọc nhiều cột với tên và kiểu dữ liệu minh bạch**, đặc biệt trong Criteria API và những bộ lọc/báo cáo có cấu trúc động. Thay vì truyền những mảng `Object[]` khó hiểu xuyên suốt hệ thống, hãy đặt alias có nghĩa, đọc qua typed getters hoặc `TupleElement<T>`, xử lý null và aggregate types cẩn thận, rồi chuyển thành DTO nếu response cần một contract ổn định. Kết hợp cách đọc này với JOIN đúng cardinality, phân trang ổn định và count query riêng sẽ giúp tầng truy cập dữ liệu **dễ kiểm soát, dễ bảo trì và chính xác hơn**.
