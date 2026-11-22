# Xử lý DISTINCT khi truy vấn entity và giá trị

Trong JPQL (Jakarta Persistence Query Language), từ khóa `DISTINCT` được dùng để yêu cầu **loại bỏ những kết quả trùng lặp** trong danh sách trả về. Nhưng khái niệm “trùng” không có cùng ý nghĩa khi câu `SELECT` trả về entity, một thuộc tính, nhiều biểu thức, hay một DTO.

Đây là hai câu truy vấn khác nhau về bản chất:

~~~jpql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
~~~

~~~jpql
SELECT DISTINCT c.fullName
FROM Customer c
JOIN c.orders o
~~~

Câu thứ nhất hướng tới **các entity Customer phân biệt theo identity**. Câu thứ hai hướng tới **các chuỗi tên khách hàng không trùng giá trị**. Hai khách hàng khác ID nhưng cùng tên sẽ được giữ tách biệt trong kết quả entity, còn kết quả tên có thể chỉ chứa một chuỗi.

Khi JOIN một quan hệ một-nhiều hoặc nhiều-nhiều, nhiều hàng SQL có thể cùng tương ứng với một entity gốc. `DISTINCT` khi đó còn liên quan đến cách Hibernate/JPA dựng entity từ SQL, persistence context, sự khác nhau giữa việc khử trùng lặp **ở database** và **trong kết quả Java**, cùng các hạn chế của `JOIN FETCH` và phân trang.

Bài học đi theo từng dạng kết quả, chỉ ra cách viết JPQL, cách đọc Java type, các tình huống `DISTINCT` có và không có tác dụng, cách đếm đúng, lưu ý hiệu năng, và cách lựa chọn query phù hợp với use case.

---

## 1. Ý nghĩa của DISTINCT trong JPQL

Cú pháp cơ bản:

~~~jpql
SELECT DISTINCT <selection>
FROM <entity> <alias>
WHERE <condition>
~~~

Ví dụ:

~~~jpql
SELECT DISTINCT o.status
FROM PurchaseOrder o
~~~

Nếu bảng có trạng thái:

~~~text
NEW
PAID
PAID
CANCELLED
PAID
~~~

thì kết quả cần biểu diễn các giá trị khác nhau:

~~~text
NEW
PAID
CANCELLED
~~~

Thứ tự trên chỉ là minh họa. **Nếu không có `ORDER BY`, thứ tự trả về không được bảo đảm.**

Với một câu `SELECT` có nhiều mục:

~~~jpql
SELECT DISTINCT o.status, o.totalAmount
FROM PurchaseOrder o
~~~

“Trùng” được xét theo **toàn bộ bộ giá trị của một hàng kết quả**, không phải từng cột độc lập:

| status | totalAmount |
|---|---:|
| PAID | 100000 |
| PAID | 100000 |
| PAID | 150000 |
| NEW | 100000 |

Kết quả phân biệt về mặt giá trị là:

| status | totalAmount |
|---|---:|
| PAID | 100000 |
| PAID | 150000 |
| NEW | 100000 |

Chỉ có hàng `(PAID, 100000)` lặp lại bị gộp. Trạng thái `PAID` vẫn có thể xuất hiện ở nhiều hàng vì `totalAmount` khác nhau.

### 1.1. Phân biệt DISTINCT với các ý niệm gần giống

| Cơ chế | Giải quyết điều gì? |
|---|---|
| `DISTINCT` | Loại các kết quả trùng theo các biểu thức được chọn và semantics truy vấn |
| `GROUP BY` | Gom các hàng theo nhóm để tính aggregate hoặc trả kết quả theo nhóm |
| `ORDER BY` | Sắp xếp kết quả, không tự loại trùng |
| `WHERE` | Lọc hàng thỏa điều kiện, không tự bảo đảm không trùng |
| `EXISTS` | Kiểm tra điều kiện tồn tại; có thể tránh nhân hàng khi chỉ cần lọc entity gốc |
| `Set<T>` trong Java | Loại trùng theo `equals/hashCode` của phần tử ở tầng Java, khác với DISTINCT của JPQL |
| Identity map JPA | Duy trì một instance managed cho mỗi entity identity trong một persistence context, **không đồng nghĩa danh sách kết quả không chứa cùng reference nhiều lần** |

Không nên dùng `DISTINCT` để “sửa” mọi kết quả có nhiều hàng mà chưa hiểu tại sao những hàng đó được tạo ra.

---

## 2. Mô hình dữ liệu minh họa

Xét hệ thống bán hàng gồm `Customer`, `PurchaseOrder` và `OrderLine`:

~~~text
Customer (1) -------- (N) PurchaseOrder
                              |
                              | (1)
                              |
                              +------ (N) OrderLine
~~~

### 2.1. Entity Customer

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false)
    private String email;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

### 2.2. Entity PurchaseOrder

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

~~~java
package com.example.sales.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

### 2.3. Entity OrderLine

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Các class ở ví dụ tách thành file tương ứng; các phần truy vấn giả định `EntityManager em` hợp lệ và dữ liệu đã được persist. Ví dụ tập trung vào đọc, không trình bày constructor tạo dữ liệu và các thao tác persist để giữ rõ ý nghĩa `DISTINCT`.

### 2.4. Dữ liệu mẫu

**customers**

| id | full_name | email |
|---:|---|---|
| 1 | An | an1@example.test |
| 2 | Bình | binh@example.test |
| 3 | An | an3@example.test |

Có **ba Customer khác nhau**, nhưng chỉ **hai giá trị fullName**.

**purchase_orders**

| id | customer_id | status | total_amount |
|---:|---:|---|---:|
| 101 | 1 | NEW | 120000 |
| 102 | 1 | PAID | 200000 |
| 103 | 2 | PAID | 180000 |
| 104 | 3 | PAID | 200000 |

**order_lines**

| id | order_id | product_code | quantity |
|---:|---:|---|---:|
| 501 | 101 | BOOK-1 | 1 |
| 502 | 101 | PEN-1 | 2 |
| 503 | 102 | BOOK-1 | 1 |
| 504 | 104 | BOOK-1 | 2 |

Order 101 có hai dòng, Order 102 có một dòng, Order 103 không có dòng, Order 104 có một dòng.

Với dữ liệu này, ta sẽ nhìn rõ bốn dạng trùng lặp khác nhau:

1. Một Customer xuất hiện trong nhiều Order.
2. Hai Customer khác nhau cùng tên An.
3. Một Order xuất hiện trên nhiều hàng khi JOIN OrderLine.
4. Hai Order khác nhau cùng giá trị `status=PAID` và `totalAmount=200000`.

---

## 3. Vì sao JOIN có thể tạo hàng lặp?

Truy vấn:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
~~~

Ở mức quan hệ, JOIN tạo một hàng trung gian cho mỗi cặp `(PurchaseOrder, OrderLine)` khớp điều kiện.

Từ dữ liệu mẫu:

| Hàng JOIN | Order ID | Line ID |
|---:|---:|---:|
| 1 | 101 | 501 |
| 2 | 101 | 502 |
| 3 | 102 | 503 |
| 4 | 104 | 504 |

Order 101 xuất hiện hai lần vì nó có hai OrderLine. Order 103 không xuất hiện vì `JOIN` mặc định là inner join và Order 103 không có line.

Điều đáng chú ý: có **bốn hàng JOIN** nhưng chỉ **ba Order identity**: 101, 102 và 104.

### 3.1. DISTINCT trên entity root

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
~~~

Về mặt kết quả JPQL, truy vấn cần trả mỗi PurchaseOrder tương ứng **một lần**:

~~~text
Order 101
Order 102
Order 104
~~~

Không có Order 103 bởi điều kiện INNER JOIN đã loại nó từ trước. `DISTINCT` không thể làm một hàng đã bị JOIN loại bỏ xuất hiện trở lại.

### 3.2. DISTINCT trên cột ID

~~~jpql
SELECT DISTINCT o.id
FROM PurchaseOrder o
JOIN o.lines l
~~~

Kết quả là các `Long`:

~~~text
101
102
104
~~~

Ở đây câu truy vấn **không trả về entity**, chỉ trả về scalar ID. Mặc dù số lượng ID giống số entity phân biệt ở ví dụ, hai kiểu kết quả không giống nhau.

### 3.3. DISTINCT trên tên sản phẩm

~~~jpql
SELECT DISTINCT l.productCode
FROM PurchaseOrder o
JOIN o.lines l
~~~

Kết quả:

~~~text
BOOK-1
PEN-1
~~~

Mã `BOOK-1` xuất hiện ở ba OrderLine nhưng chỉ được trả một lần trong tập giá trị phân biệt.

### 3.4. DISTINCT trên cả ID và mã sản phẩm

~~~jpql
SELECT DISTINCT o.id, l.productCode
FROM PurchaseOrder o
JOIN o.lines l
~~~

Kết quả:

| o.id | l.productCode |
|---:|---|
| 101 | BOOK-1 |
| 101 | PEN-1 |
| 102 | BOOK-1 |
| 104 | BOOK-1 |

Truy vấn vẫn có **bốn hàng** vì không có cặp `(orderId, productCode)` trùng trong dữ liệu mẫu. Việc thêm `DISTINCT` không bảo đảm chỉ còn một hàng mỗi Order khi `SELECT` chứa cả các giá trị ở phía “many”.

---

## 4. DISTINCT khi chọn entity

Đây là dạng được dùng nhiều khi query entity qua một quan hệ một-nhiều hoặc nhiều-nhiều.

### 4.1. JPQL và Java

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        JOIN o.lines l
        ORDER BY o.id
        """,
        PurchaseOrder.class
    )
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getId());
}
~~~

Theo dữ liệu mẫu, dãy ID mong đợi là:

~~~text
101
102
104
~~~

Giải thích:

- `o` là một entity-valued expression.
- `DISTINCT o` yêu cầu loại kết quả entity trùng identity.
- `PurchaseOrder.class` là kiểu result của `TypedQuery`.
- `ORDER BY o.id` giúp kết quả có thứ tự rõ ràng.
- Mỗi entity trong danh sách được JPA quản lý khi nằm trong persistence context còn hoạt động.

### 4.2. Entity identity là gì?

Một entity JPA có identity được xác định qua kiểu entity và khóa chính. Hai Order có ID 101 và 102 là **hai entity khác nhau**, dù tất cả thuộc tính không phải ID của chúng có cùng giá trị.

Ví dụ:

~~~text
Order 102:
  id=102, status=PAID, totalAmount=200000

Order 104:
  id=104, status=PAID, totalAmount=200000
~~~

Dù `status` và `totalAmount` giống nhau, `SELECT DISTINCT o` **không gộp** hai entity này thành một. Chúng khác primary key.

Ngược lại, Order 101 lặp hai lần qua hai hàng JOIN nhưng vẫn là **một entity identity**.

### 4.3. Persistence context không phải DISTINCT

Trong một persistence context:

~~~java
PurchaseOrder first =
    em.find(PurchaseOrder.class, 101L);

PurchaseOrder second =
    em.find(PurchaseOrder.class, 101L);

System.out.println(first == second); // true
~~~

JPA duy trì một managed instance cho identity `(PurchaseOrder, 101)` trong cùng context. Tuy nhiên điều đó **không nhất thiết cấm một List chứa tham chiếu ấy nhiều lần**.

Một result list có thể về nguyên tắc chứa:

~~~text
[
  reference-to-Order-101,
  reference-to-Order-101,
  reference-to-Order-102
]
~~~

Cả hai phần tử đầu có thể trỏ cùng một Java object, nhưng danh sách vẫn có ba phần tử. **Trùng reference trong List** và **trùng managed instance trong persistence context** là hai vấn đề khác nhau.

Một số provider/version tự loại các root entity trùng trong các loại truy vấn nhất định, đặc biệt collection fetch join. Không dựa vào hành vi nội bộ ấy để suy ra rằng identity map của JPA tự động khử mọi duplicate result row.

### 4.4. Không dùng equals/hashCode để định nghĩa DISTINCT entity

Nếu một entity có `equals()` so sánh theo mã khách hàng hoặc một trường khác, nó không thay đổi câu hỏi `SELECT DISTINCT o` đang xét trong JPQL theo **entity identity**.

Ví dụ hai `PurchaseOrder` khác ID nhưng có cùng totalAmount vẫn là hai entity. Đó không phải lúc để lấy `HashSet<PurchaseOrder>` rồi kết luận rằng kết quả ORM đúng theo JPA.

`HashSet` sử dụng `equals/hashCode` của Java; `DISTINCT` trong JPQL tuân theo semantics của query và provider, và SQL có thể thực hiện phần loại trùng theo tập cột được chọn.

---

## 5. DISTINCT khi chọn thuộc tính scalar

Một scalar projection có một biểu thức trả về giá trị Java thay vì entity.

### 5.1. Chọn trạng thái khác nhau

~~~java
List<OrderStatus> statuses = em.createQuery(
        """
        SELECT DISTINCT o.status
        FROM PurchaseOrder o
        ORDER BY o.status
        """,
        OrderStatus.class
    )
    .getResultList();
~~~

Kết quả về mặt tập giá trị:

~~~text
NEW
PAID
~~~

Nếu có Order bị CANCELLED, trạng thái CANCELLED sẽ được thêm vào. `@Enumerated(EnumType.STRING)` làm database lưu tên trạng thái nhưng JPQL projection vẫn trả Java enum `OrderStatus`.

### 5.2. Chọn tên khách hàng

~~~java
List<String> names = em.createQuery(
        """
        SELECT DISTINCT c.fullName
        FROM Customer c
        ORDER BY c.fullName
        """,
        String.class
    )
    .getResultList();
~~~

Có ba Customer nhưng chỉ có hai tên:

~~~text
An
Bình
~~~

Đây chính là lý do không nên coi truy vấn này là “lấy mọi khách hàng không trùng”. Nó lấy các **chuỗi tên không trùng**, nên hai người trùng tên bị gộp.

### 5.3. Chọn ID khách hàng

~~~java
List<Long> ids = em.createQuery(
        """
        SELECT DISTINCT c.id
        FROM Customer c
        ORDER BY c.id
        """,
        Long.class
    )
    .getResultList();
~~~

Kết quả:

~~~text
1
2
3
~~~

Nếu query chỉ lấy `Customer` từ bảng customers mà không JOIN gây nhân hàng, `c.id` vốn đã là primary key duy nhất, nên `DISTINCT` có thể không cần thiết. Nó thường hữu ích hơn khi JOIN với bảng con hoặc khi biểu thức thực sự có khả năng lặp.

### 5.4. DISTINCT trên một biểu thức tính toán

~~~java
List<String> normalizedNames = em.createQuery(
        """
        SELECT DISTINCT UPPER(c.fullName)
        FROM Customer c
        ORDER BY UPPER(c.fullName)
        """,
        String.class
    )
    .getResultList();
~~~

Kết quả là **giá trị sau khi áp dụng UPPER**, không phải tên gốc. Vì vậy các biến thể chữ hoa/thường có thể cùng trở thành một chuỗi đầu ra.

Tuy nhiên, collation và so sánh chuỗi của DBMS vẫn có thể ảnh hưởng tới những giá trị được coi là bằng nhau trong SQL; `UPPER` không phải giải pháp chuẩn hóa Unicode/tên người cho mọi ngôn ngữ.

### 5.5. DISTINCT với NULL

Nếu thuộc tính được chọn có thể null:

~~~jpql
SELECT DISTINCT c.middleName
FROM Customer c
~~~

nhiều hàng null trong dữ liệu thường được biểu diễn bằng **một giá trị null** ở kết quả DISTINCT theo ngữ nghĩa SQL. Đây không phải biểu thức `NULL = NULL` trong điều kiện WHERE; đó là quy tắc loại các hàng duplicate của DISTINCT.

Cần phân biệt thêm:

~~~jpql
SELECT COUNT(DISTINCT c.middleName)
FROM Customer c
~~~

`COUNT(DISTINCT ...)` thường **không đếm các giá trị null**. Vì vậy số phần tử của `SELECT DISTINCT ...` có thể khác `COUNT(DISTINCT ...)` nếu danh sách có null.

Ví dụ các giá trị:

~~~text
null
null
"Văn"
"Thị"
"Văn"
~~~

- `SELECT DISTINCT middleName` có thể trả `null, "Văn", "Thị"`: ba giá trị khi nhìn kết quả list.
- `COUNT(DISTINCT middleName)` trả 2 vì giá trị null không được đếm.

Trong schema Customer minh họa không có `middleName`; ví dụ này áp dụng cho entity khác có field nullable tương ứng.

---

## 6. DISTINCT khi chọn nhiều biểu thức

Khi một câu `SELECT` có nhiều mục, một hàng kết quả thông thường là `Object[]` hoặc được ánh xạ thành DTO/Tuple.

### 6.1. Cặp status và totalAmount

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT DISTINCT o.status, o.totalAmount
        FROM PurchaseOrder o
        ORDER BY o.status, o.totalAmount
        """,
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    OrderStatus status = (OrderStatus) row[0];
    BigDecimal amount = (BigDecimal) row[1];

    System.out.printf("%s: %s%n", status, amount);
}
~~~

Với dữ liệu mẫu:

| status | totalAmount |
|---|---:|
| NEW | 120000 |
| PAID | 180000 |
| PAID | 200000 |

Order 102 và 104 có cùng status và totalAmount nên tạo cùng một cặp kết quả. `DISTINCT` gộp chúng, **dù đó là hai Order khác nhau**.

### 6.2. Thêm ID làm thay đổi tiêu chí trùng

~~~jpql
SELECT DISTINCT o.id, o.status, o.totalAmount
FROM PurchaseOrder o
~~~

Bây giờ kết quả sẽ giữ cả Order 102 và 104 vì ID khác:

~~~text
(101, NEW, 120000)
(102, PAID, 200000)
(103, PAID, 180000)
(104, PAID, 200000)
~~~

Khi cần một hàng cho mỗi Order, đưa ID vào projection giúp không gộp các Order khác nhau vì tình cờ giống thuộc tính khác.

### 6.3. Trùng theo tuple, không theo từng cột

Ví dụ:

~~~text
(A, 1)
(A, 2)
(B, 1)
(A, 1)
~~~

`DISTINCT` loại hàng `(A, 1)` lặp lại, không xóa tất cả hàng có cột đầu là A hoặc cột hai bằng 1. Một sai lầm thường gặp là nghĩ:

~~~jpql
SELECT DISTINCT o.status, o.totalAmount
~~~

nghĩa là “mỗi status đúng một hàng, kèm totalAmount bất kỳ”. Không đúng.

Nếu muốn **mỗi status đúng một hàng và tổng tiền**, dùng:

~~~jpql
SELECT o.status, SUM(o.totalAmount)
FROM PurchaseOrder o
GROUP BY o.status
~~~

### 6.4. Kết hợp entity và scalar

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT DISTINCT o, l.productCode
        FROM PurchaseOrder o
        JOIN o.lines l
        ORDER BY o.id, l.productCode
        """,
        Object[].class
    )
    .getResultList();
~~~

Mỗi hàng gồm một entity `o` và một scalar `l.productCode`. Nếu Order 101 có BOOK-1 và PEN-1, hai tuple khác nhau:

~~~text
(Order 101, BOOK-1)
(Order 101, PEN-1)
~~~

Cả hai sẽ được giữ. **`DISTINCT` không bảo đảm một hàng mỗi Order vì biểu thức thứ hai khác nhau.**

Nếu chỉ muốn các Order có dòng hàng, bỏ biểu thức `l.productCode` khỏi SELECT:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
~~~

Hoặc cân nhắc `EXISTS` khi chỉ cần kiểm tra tồn tại quan hệ.

---

## 7. SELECT DISTINCT NEW DTO

Trong ứng dụng, nhiều câu query trả DTO thay vì entity. Ví dụ:

~~~java
package com.example.sales.dto;

import com.example.sales.domain.OrderStatus;
import java.math.BigDecimal;

public record OrderSnapshot(
    OrderStatus status,
    BigDecimal totalAmount
) {}
~~~

JPQL:

~~~java
List<OrderSnapshot> snapshots = em.createQuery(
        """
        SELECT DISTINCT NEW com.example.sales.dto.OrderSnapshot(
            o.status,
            o.totalAmount
        )
        FROM PurchaseOrder o
        ORDER BY o.status, o.totalAmount
        """,
        OrderSnapshot.class
    )
    .getResultList();
~~~

Ý nghĩa projection:

- Mỗi DTO chứa status và totalAmount.
- Hai Order có cùng cặp giá trị không cần tạo hai bản ghi kết quả phân biệt.
- `OrderSnapshot` không phải entity managed.
- Thay đổi DTO không được dirty checking để sửa PurchaseOrder.

### 7.1. DISTINCT không dựa đơn giản vào equals() của DTO

Không nên suy luận rằng `SELECT DISTINCT NEW ...` có nghĩa JPA chỉ việc tạo tất cả DTO rồi gọi `HashSet<DTO>` theo `equals/hashCode` Java.

Semantics DISTINCT thuộc JPQL; provider có thể chuyển nó thành SQL DISTINCT trên các biểu thức cơ sở, xử lý ở kết quả trung gian hoặc kết hợp các cơ chế. Việc record có `equals()` theo giá trị là tiện ích Java, **không phải điều kiện bắt buộc để khai báo JPQL DISTINCT**.

Tùy cấu trúc projection và provider, cần xem SQL thực tế khi tối ưu hiệu năng.

### 7.2. Đưa ID vào DTO nếu cần phân biệt entity

DTO:

~~~java
package com.example.sales.dto;

import com.example.sales.domain.OrderStatus;
import java.math.BigDecimal;

public record OrderRow(
    Long orderId,
    OrderStatus status,
    BigDecimal totalAmount
) {}
~~~

JPQL:

~~~jpql
SELECT DISTINCT NEW com.example.sales.dto.OrderRow(
    o.id, o.status, o.totalAmount
)
FROM PurchaseOrder o
~~~

Hai Order 102 và 104 không bị gộp vì ID khác. Trong query từ một bảng Order không nhân hàng, DISTINCT có thể dư thừa vì `o.id` vốn duy nhất.

### 7.3. Không kỳ vọng DTO được đồng bộ như entity

~~~java
OrderRow row = ...; // Kết quả projection.
~~~

DTO chỉ đại diện cho dữ liệu đọc. Nó không mang entity identity trong persistence context và không thể được lưu thay đổi bằng dirty checking. Nếu cần thay đổi trạng thái Order:

~~~java
PurchaseOrder managed =
    em.find(PurchaseOrder.class, row.orderId());
~~~

sau đó thực hiện business method trong transaction phù hợp.

### 7.4. DISTINCT trên projection có aggregate

Có thể viết:

~~~jpql
SELECT DISTINCT NEW com.example.sales.dto.OrderSnapshot(
    o.status,
    o.totalAmount
)
FROM PurchaseOrder o
~~~

nhưng nếu mục tiêu là **báo cáo theo status**, dùng `GROUP BY` để biểu đạt nhóm và phép tổng hợp. `DISTINCT` và `GROUP BY` không được thay thế cho nhau chỉ vì đôi khi chúng đều giảm số hàng.

---

## 8. COUNT và COUNT DISTINCT

Khi cần đếm, không nên tải tất cả entity về Java rồi gọi `distinct().count()` nếu chỉ cần con số. JPQL có aggregate `COUNT` và `COUNT(DISTINCT ...)`.

### 8.1. Đếm số hàng JOIN

~~~java
Long joinRows = em.createQuery(
        """
        SELECT COUNT(o)
        FROM PurchaseOrder o
        JOIN o.lines l
        """,
        Long.class
    )
    .getSingleResult();
~~~

Với dữ liệu mẫu, kết quả là `4L`:

- Order 101 đóng góp 2 hàng.
- Order 102 đóng góp 1 hàng.
- Order 104 đóng góp 1 hàng.
- Order 103 đóng góp 0 hàng.

Đây là **số hàng quan hệ sau JOIN**, không phải số Order có ít nhất một line.

### 8.2. Đếm entity gốc không trùng

~~~java
Long orderCount = em.createQuery(
        """
        SELECT COUNT(DISTINCT o.id)
        FROM PurchaseOrder o
        JOIN o.lines l
        """,
        Long.class
    )
    .getSingleResult();
~~~

Kết quả là `3L`: các Order 101, 102 và 104.

Trong một số trường hợp JPQL còn cho phép `COUNT(DISTINCT o)` trên entity-valued expression theo quy tắc/provider tương ứng. Dùng `o.id` khi mục tiêu là đếm identity đơn khóa sẽ thể hiện rõ cột định danh; với khóa ghép, cần xác minh hỗ trợ SQL/dialect và cú pháp truy vấn thích hợp.

### 8.3. Đếm các giá trị scalar khác nhau

~~~java
Long distinctStatuses = em.createQuery(
        """
        SELECT COUNT(DISTINCT o.status)
        FROM PurchaseOrder o
        """,
        Long.class
    )
    .getSingleResult();
~~~

Với trạng thái NEW và PAID: trả `2L`.

Tương tự:

~~~jpql
SELECT COUNT(DISTINCT c.fullName)
FROM Customer c
~~~

trả 2 cho các tên An và Bình, dù có 3 Customer.

### 8.4. COUNT(DISTINCT ...) không tương đương luôn với size của SELECT DISTINCT

Với field nullable:

~~~jpql
SELECT DISTINCT c.middleName
FROM Customer c
~~~

có thể trả một phần tử null.

Nhưng:

~~~jpql
SELECT COUNT(DISTINCT c.middleName)
FROM Customer c
~~~

không đếm giá trị null như một giá trị riêng trong aggregate COUNT.

Ngoài ra, không thể suy ra số Order không trùng từ `COUNT(DISTINCT status)` nếu nhiều Order chia sẻ trạng thái.

### 8.5. Không có COUNT DISTINCT nhiều cột portable đơn giản

Một số DBMS có extension:

~~~sql
-- Cú pháp đa cột phụ thuộc DBMS:
COUNT(DISTINCT column_a, column_b)
~~~

Nhưng JPQL portable không cung cấp cơ chế phổ quát cho việc viết `COUNT(DISTINCT a, b)` giống nhau trên mọi provider/dialect.

Nếu cần **đếm số cặp phân biệt**, có thể cân nhắc:

- Điều chỉnh mô hình dữ liệu để biểu thức cần đếm có khóa tự nhiên/duy nhất.
- JPQL `GROUP BY` rồi đếm kết quả theo yêu cầu khi dữ liệu vừa phải.
- Native SQL subquery `SELECT COUNT(*) FROM (SELECT DISTINCT a,b ...)` trong DBMS phù hợp.
- Một query chuyên biệt do provider hỗ trợ, có kiểm chứng portability.

Không thay bằng `COUNT(DISTINCT a)` nếu `b` cũng là thành phần xác định tính duy nhất của cặp.

---

## 9. DISTINCT và GROUP BY

Hai câu:

~~~jpql
SELECT DISTINCT o.status
FROM PurchaseOrder o
~~~

và:

~~~jpql
SELECT o.status
FROM PurchaseOrder o
GROUP BY o.status
~~~

có thể trả cùng tập trạng thái. Nhưng chúng có **mục đích** khác:

- `DISTINCT`: chọn các giá trị status không trùng.
- `GROUP BY`: tạo nhóm để có thể tính các giá trị aggregate theo status.

Ví dụ:

~~~jpql
SELECT o.status, COUNT(o), SUM(o.totalAmount)
FROM PurchaseOrder o
GROUP BY o.status
~~~

Với dữ liệu mẫu:

| status | count | total |
|---|---:|---:|
| NEW | 1 | 120000 |
| PAID | 3 | 580000 |

Ở đây `GROUP BY` biểu diễn đúng ý nghĩa “một hàng cho mỗi status”, kèm số lượng/tổng tiền. Không cần viết thêm `DISTINCT` một cách máy móc nếu nhóm đã xác định duy nhất các hàng kết quả.

### 9.1. DISTINCT không tự chọn một bản ghi đại diện mỗi nhóm

Nếu muốn “Order mới nhất của mỗi Customer”, không thể viết:

~~~jpql
SELECT DISTINCT o.customer
FROM PurchaseOrder o
ORDER BY o.createdAt DESC
~~~

rồi trông đợi Order mới nhất sẽ được chọn cho mỗi khách hàng. Câu SELECT chỉ trả Customer, không trả Order đại diện; việc thêm DISTINCT không định nghĩa lựa chọn một Order trong từng nhóm.

Để lấy Order mới nhất mỗi khách hàng, cần một truy vấn được thiết kế riêng:

- Correlated subquery với `MAX(createdAt)` và quy tắc tie-breaker khi trùng thời gian.
- Window function qua native SQL trên DBMS phù hợp.
- Query theo ID của các Order được chọn bởi một bước truy vấn riêng.

Không dùng DISTINCT như phiên bản thay thế của `ROW_NUMBER() OVER (PARTITION BY ...)`. JPA JPQL chuẩn không định nghĩa cú pháp window function theo cách SQL hiện đại ở mọi phiên bản/provider.

### 9.2. DISTINCT không sửa dữ liệu trùng trong bảng

Nếu bảng có hai bản ghi nghiệp vụ trùng không mong muốn, SELECT DISTINCT có thể che giấu sự cố ở màn hình. Nhưng nó không tạo constraint và không ngăn request đồng thời ghi trùng lần sau.

Ví dụ `Customer.email` cần unique:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Dữ liệu phải được dọn và ràng buộc triển khai đúng trước khi thêm constraint vào production. `DISTINCT` là công cụ truy vấn, còn unique constraint bảo vệ **tính duy nhất của dữ liệu**.

---

## 10. DISTINCT và JOIN FETCH collection

Đây là một trong những tình huống dễ gây nhầm lẫn nhất trong Hibernate/JPA.

Giả sử muốn tải PurchaseOrder cùng tất cả OrderLine:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        ORDER BY o.id
        """,
        PurchaseOrder.class
    )
    .getResultList();
~~~

Chọn `LEFT JOIN FETCH` vì muốn giữ cả Order không có line, đồng thời nạp collection `lines` trong cùng fetch plan.

### 10.1. SQL JOIN cần nhiều hàng để tạo collection

Một câu SQL tương đương về ý nghĩa có thể là:

~~~sql
SELECT o.id, o.status, o.total_amount,
       l.id, l.product_code, l.quantity
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
ORDER BY o.id;
~~~

Order 101 có hai dòng, nên SQL trả hai hàng với cùng Order ID nhưng khác Line ID.

Provider cần dùng cả hai hàng để tạo:

~~~text
PurchaseOrder 101
  ├─ OrderLine 501
  └─ OrderLine 502
~~~

Nếu database dùng `DISTINCT` trên **toàn bộ các cột SELECT**, hai hàng không giống nhau vì Line ID 501 khác 502. SQL DISTINCT không thể xóa một hàng mà vẫn giữ cả hai OrderLine cần thiết cho collection.

### 10.2. Khử trùng lặp root entity ở tầng ORM

Sau khi đọc các hàng SQL, ORM có thể lắp ráp:

~~~text
Danh sách root muốn trả:
  Order 101
  Order 102
  Order 103
  Order 104

Collections:
  101 -> [501,502]
  102 -> [503]
  103 -> []
  104 -> [504]
~~~

Ở đây root entity được trả một lần, còn collection giữ đúng các phần tử liên quan.

Khử trùng lặp root result **khác** với SQL DISTINCT loại các hàng giống nhau của toàn bộ SELECT. Hai tầng có mục đích riêng.

### 10.3. Lưu ý Hibernate 5 và Hibernate 6

Hành vi cụ thể của Hibernate đã thay đổi giữa các thế hệ:

- **Hibernate 5**: khi fetch join một collection, result list có thể chứa cùng root reference nhiều lần nếu không dùng JPQL `DISTINCT`. Dùng `SELECT DISTINCT o` là cách thường gặp để loại các root entity trùng trong kết quả.
- **Hibernate 6**: Hibernate có cơ chế tự loại duplicate root entities trong kết quả của các truy vấn collection `JOIN FETCH`, nên không nhất thiết phải viết `DISTINCT` chỉ để khử trùng root trong tình huống này.
- Việc JPQL `DISTINCT` được đẩy xuống SQL và những tùy chọn kiểm soát nó cũng khác theo phiên bản. Hint `hibernate.query.passDistinctThrough` từng xuất hiện trong các phiên bản Hibernate 5; không được coi là giải pháp portable hoặc còn dùng nguyên dạng trong Hibernate 6.

**Không chuyển nguyên một “mẹo Hibernate 5” sang Hibernate 6** mà không kiểm tra SQL và semantics của phiên bản đang chạy.

Dù Hibernate 6 có thể tự loại root duplicate trong collection fetch join, không được suy ra nó tự khử mọi giá trị scalar trùng hoặc mọi tuple trùng trong mọi câu JPQL khi không viết DISTINCT.

### 10.4. Vì sao thêm SQL DISTINCT có thể tốn chi phí?

Database có thể phải xử lý sort/hash để loại các hàng trùng. Với fetch join một-nhiều, nhiều hàng vốn khác Line ID, nên `DISTINCT` ở SQL có thể không giảm đáng kể số hàng SQL được trả.

Chi phí có thể bao gồm:

- Sort hoặc hash aggregate.
- Bộ nhớ tạm và đọc/ghi đĩa cho tập kết quả lớn.
- Network transfer cho nhiều hàng join.
- ORM materialization của entity graph lớn.

Lợi ích phụ thuộc số cột được chọn, cardinality và execution plan. Không kết luận `DISTINCT` luôn tăng tốc hoặc luôn làm chậm; hãy xem SQL generated và `EXPLAIN ANALYZE` phù hợp với DBMS.

### 10.5. Không dùng JOIN FETCH chỉ để lọc dữ liệu

Nếu chỉ cần Order có một Line sản phẩm BOOK-1:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.productCode = :sku
~~~

Đây là **JOIN thường** để lọc các Order, không yêu cầu nạp tất cả lines. Nếu thay bằng `JOIN FETCH o.lines l` rồi `WHERE l.productCode = :sku`, có nguy cơ chỉ fetch **một phần collection** theo điều kiện, khiến object graph trong persistence context mang nghĩa khó dùng tùy provider.

Khi cần lọc Order nhưng nạp **toàn bộ lines** của các Order thỏa, có thể dùng query hai bước hoặc thiết kế fetch plan riêng. Đừng dùng DISTINCT để giải quyết việc collection bị giới hạn sai do fetch join có điều kiện.

---

## 11. DISTINCT và phân trang: cẩn trọng với JOIN FETCH

Giả sử màn hình cần 20 Order mỗi trang và mỗi Order có 1–10 lines. Một truy vấn như:

~~~java
List<PurchaseOrder> page = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        PurchaseOrder.class
    )
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

có thể gặp vấn đề:

- SQL JOIN tạo nhiều hàng cho cùng Order.
- Nếu áp dụng `LIMIT 20` trực tiếp ở mức SQL join rows, trang có thể chỉ chứa vài Order và collection có thể không đầy đủ.
- Một số phiên bản Hibernate chọn phân trang **trong bộ nhớ** khi collection fetch join để bảo vệ tính đúng đắn, dẫn đến tải rất nhiều hàng trước khi lấy 20 root entities.
- JPQL DISTINCT không tự sửa được xung đột giữa số hàng SQL và số root entity cần phân trang.

Với Hibernate, có thể cấu hình để cảnh báo hoặc biến tình huống pagination over collection fetch thành lỗi, tùy phiên bản; ứng dụng nên chủ động tránh lối truy vấn nguy hiểm thay vì chỉ dựa vào cảnh báo.

### 11.1. Cách 1 — Phân trang theo ID entity trước

Bước 1: lấy 20 Order IDs bằng query không fetch collection:

~~~java
List<Long> orderIds = em.createQuery(
        """
        SELECT o.id
        FROM PurchaseOrder o
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        Long.class
    )
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Bước 2: tải Order và collection cho tập ID nhỏ:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        WHERE o.id IN :ids
        """,
        PurchaseOrder.class
    )
    .setParameter("ids", orderIds)
    .getResultList();
~~~

Sau đó nếu cần đúng thứ tự của trang, sắp lại **theo thứ tự orderIds** ở tầng Java; câu `IN (...)` không bảo đảm giữ thứ tự ID truyền vào.

Ví dụ đơn giản:

~~~java
Map<Long, Integer> positions = new HashMap<>();

for (int i = 0; i < orderIds.size(); i++) {
    positions.put(orderIds.get(i), i);
}

orders.sort(Comparator.comparingInt(
    o -> positions.get(o.getId())
));
~~~

Nếu `orderIds` rỗng, không gọi query `IN :ids` với danh sách rỗng mà không biết provider xử lý thế nào; có thể trả `List.of()` ngay.

Hai query có thể nhìn thấy trạng thái database ở hai thời điểm khác nhau tùy isolation/transaction; khi yêu cầu snapshot nghiêm ngặt, cần thiết kế transaction isolation hoặc cơ chế đọc nhất quán thích hợp.

### 11.2. Cách 2 — Trang DTO thay vì entity graph

Nếu màn hình chỉ cần ID, tên khách, số tiền:

~~~java
List<OrderListRow> page = em.createQuery(
        """
        SELECT NEW com.example.sales.dto.OrderListRow(
            o.id,
            c.fullName,
            o.totalAmount
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderListRow.class
    )
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

DTO:

~~~java
package com.example.sales.dto;

import java.math.BigDecimal;

public record OrderListRow(
    Long orderId,
    String customerName,
    BigDecimal totalAmount
) {}
~~~

Vì quan hệ từ Order tới Customer là nhiều-một, JOIN này không nhân hàng root theo cách JOIN collection. Không cần fetch toàn bộ lines chỉ để vẽ bảng danh sách đơn.

### 11.3. Cách 3 — EXISTS khi chỉ cần lọc theo collection

Nếu muốn các Order có ít nhất một dòng BOOK-1 mà mỗi Order chỉ xuất hiện một lần, có thể tránh JOIN root với collection:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE EXISTS (
            SELECT l.id
            FROM OrderLine l
            WHERE l.order = o
              AND l.productCode = :sku
        )
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        PurchaseOrder.class
    )
    .setParameter("sku", "BOOK-1")
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Mỗi Order của outer query được xét theo điều kiện tồn tại. Query không nhân root row chỉ vì một Order có nhiều dòng cùng SKU.

Không phải lúc nào EXISTS nhanh hơn JOIN DISTINCT: optimizer có thể biến đổi tương đương hoặc chọn plan khác. Nhưng EXISTS thường diễn đạt trực tiếp ý định “có ít nhất một record liên quan” và tránh vấn đề duplicate root từ outer join.

---

## 12. DISTINCT và COUNT cho phân trang

Với danh sách entity lọc qua JOIN collection:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.productCode = :sku
ORDER BY o.id
~~~

câu đếm tương ứng thường là:

~~~jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.productCode = :sku
~~~

Không dùng:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.productCode = :sku
~~~

nếu một Order có thể có nhiều OrderLine cùng SKU. `COUNT(o)` đếm các hàng sau JOIN, nên có thể lớn hơn số Order phân biệt.

### 12.1. Count query không nên fetch join

Một truy vấn:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN FETCH o.lines
~~~

không phải cách đúng để đếm. `FETCH JOIN` dùng để nạp association của owner entity được chọn, trong khi `COUNT(o)` trả scalar. Provider có thể từ chối hoặc cho hành vi không phù hợp.

Cách đếm đúng là `JOIN` thường với COUNT tương ứng, hoặc `EXISTS`:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.productCode = :sku
)
~~~

### 12.2. Count DISTINCT o.id với khóa ghép

Nếu entity có `@EmbeddedId`, `COUNT(DISTINCT e.id)` có thể cần nhiều cột SQL. Không phải mọi DBMS/provider diễn dịch biểu thức distinct trên composite key giống nhau.

Khi ứng dụng có composite PK và muốn đếm entity phân biệt, nên kiểm tra SQL generated hoặc dùng truy vấn theo một thuộc tính định danh unique phù hợp, subquery/native SQL nếu cần. Không áp đặt một cú pháp `COUNT(DISTINCT a,b)` không portable cho mọi JPA dialect.

---

## 13. DISTINCT và ORDER BY: hạn chế cần hiểu

Với scalar đơn:

~~~jpql
SELECT DISTINCT o.status
FROM PurchaseOrder o
ORDER BY o.status
~~~

đây là cách dùng rõ ràng: sắp xếp theo chính biểu thức được chọn.

Nhưng với:

~~~jpql
SELECT DISTINCT o.status
FROM PurchaseOrder o
ORDER BY o.createdAt
~~~

một status có thể tương ứng với nhiều giá trị `createdAt` khác nhau. Nên “thời điểm nào” được dùng để sắp xếp một hàng status đã gộp?

Nhiều DBMS giới hạn `ORDER BY` trên những biểu thức không nằm trong SELECT khi có DISTINCT; JPQL cũng có các quy tắc về ordered expressions. Truy vấn này có thể bị provider/database từ chối hoặc không có ngữ nghĩa như người viết mong muốn.

### 13.1. Nếu muốn các trạng thái theo thời điểm mới nhất

Thay vì dựa vào DISTINCT không xác định được representative row:

~~~jpql
SELECT o.status, MAX(o.createdAt)
FROM PurchaseOrder o
GROUP BY o.status
ORDER BY MAX(o.createdAt) DESC
~~~

Giờ mỗi hàng có:

- Trạng thái.
- Thời điểm lớn nhất của Order thuộc trạng thái đó.

Mục tiêu sắp xếp được biểu diễn rõ bằng `MAX` và `GROUP BY`.

### 13.2. DISTINCT với DTO có ORDER BY

~~~jpql
SELECT DISTINCT NEW com.example.sales.dto.OrderSnapshot(
    o.status,
    o.totalAmount
)
FROM PurchaseOrder o
ORDER BY o.status, o.totalAmount
~~~

Đây là kiểu sắp xếp dựa trên các biểu thức nằm trong projection. Nếu đổi `ORDER BY o.createdAt` trong khi DTO chỉ có status và amount, có thể gặp vấn đề portability hoặc ý nghĩa thứ tự khi nhiều Order gộp thành cùng một DTO.

### 13.3. DISTINCT và phân trang ổn định

Khi dùng `setFirstResult()/setMaxResults()`, một query cần thứ tự xác định, ưu tiên có khóa phân biệt cuối cùng:

~~~jpql
ORDER BY o.createdAt DESC, o.id DESC
~~~

Nhưng nếu SELECT DISTINCT chỉ lấy trạng thái, không thể tùy tiện thêm ID vào ORDER BY mà không xét semantics DISTINCT. Nếu cần **mỗi status một hàng**, hãy dùng nhóm và aggregate thích hợp thay vì cố lấy ID tie-breaker của nhiều entity khác nhau.

---

## 14. DISTINCT, database collation và kiểu dữ liệu

Với giá trị scalar, “bằng nhau” trong `DISTINCT` thường được xác định ở SQL/database hoặc cách provider thực thi. So sánh chuỗi có thể chịu ảnh hưởng bởi:

- Collation phân biệt hay không phân biệt chữ hoa/thường.
- Quy tắc dấu, Unicode normalization, khoảng trắng.
- Kiểu dữ liệu và hàm `LOWER/UPPER/TRIM`.
- DBMS/dialect.

Ví dụ, tùy collation, `"AN"` và `"An"` có thể được coi là tương đương hoặc khác nhau ở kết quả `SELECT DISTINCT name`.

Nếu nghiệp vụ yêu cầu chuẩn hóa email hoặc username, không nên chỉ dựa vào DISTINCT query. Cần một chính sách chuẩn hóa trước khi lưu và constraint unique ở database tương thích với quy tắc business.

### 14.1. DISTINCT trên số thập phân

Với DECIMAL/NUMERIC:

~~~jpql
SELECT DISTINCT o.totalAmount
FROM PurchaseOrder o
~~~

Các giá trị số bằng nhau theo semantics database có thể bị gộp dù biểu diễn chuỗi có số chữ số thập phân khác nhau. Ví dụ `200000.0` và `200000.00` có thể được xem là cùng giá trị số ở SQL.

Ở tầng Java, `BigDecimal.equals()` lại phân biệt scale trong nhiều tình huống. Vì vậy kết quả DISTINCT do database thực thi không nhất thiết tương ứng với việc đưa một List<BigDecimal> vào HashSet Java, vì hai tầng dùng quy tắc so sánh khác nhau.

Đây là một ví dụ thực tế cho thấy **JPQL DISTINCT không tương đương Java equals() trên mọi kiểu scalar**.

### 14.2. DISTINCT trên kiểu phức tạp hoặc cột lớn

Một số DBMS hạn chế `DISTINCT` trên kiểu dữ liệu lớn, JSON, LOB hoặc kiểu không có toán tử so sánh hỗ trợ. Nếu entity chứa các trường như `@Lob`, SQL DISTINCT trên toàn bộ projection của entity/fetch join có thể gây chi phí hoặc lỗi dialect.

Đừng mặc định `SELECT DISTINCT e` sẽ luôn là phép SQL DISTINCT rẻ trên mọi entity. Khi cần lọc identity, có thể cân nhắc query riêng lấy ID hoặc EXISTS, rồi tải entity theo ID.

---

## 15. DISTINCT có luôn chạy ở database không?

Không nên đưa ra một lời khẳng định tuyệt đối cho mọi provider/version.

Theo JPQL, `DISTINCT` là **semantics của kết quả truy vấn**: loại những phần tử được coi là trùng theo loại result. Provider có thể sử dụng các chiến lược triển khai khác nhau, tùy cấu trúc query:

1. Sinh SQL `SELECT DISTINCT ...` để database loại hàng giống nhau.
2. Tạo entity instances hoặc tái sử dụng managed entity qua identity map.
3. Khử trùng root entity references trong result list khi một fetch join tạo nhiều hàng.
4. Kết hợp các cơ chế trên.

### 15.1. Scalar projection thường thuận lợi cho SQL DISTINCT

Ví dụ:

~~~jpql
SELECT DISTINCT c.fullName
FROM Customer c
~~~

có thể chuyển thành SQL dạng:

~~~sql
SELECT DISTINCT c.full_name
FROM customers c;
~~~

Database có thể loại các tên trùng trước khi trả dữ liệu. Nếu chỉ cần vài giá trị scalar, đây có thể là cách trực tiếp và hiệu quả.

### 15.2. Entity fetch join phức tạp hơn

Ví dụ:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
~~~

SQL có thể chứa cột Order và cả OrderLine. Mỗi line khác nhau khiến hàng SQL khác nhau ngay cả khi cùng Order. Provider cần duy trì toàn bộ lines trong object graph nhưng kết quả root list không nên lặp theo yêu cầu distinct.

Vì vậy **SQL DISTINCT không nhất thiết giảm số hàng join SQL** và **khử trùng entity results có thể xảy ra sau khi provider đọc nhiều hàng**.

### 15.3. Hibernate 5 và passDistinctThrough

Một số phiên bản Hibernate 5 cung cấp hint provider-specific để biểu đạt ý định khử trùng JPA result mà không nhất thiết đẩy DISTINCT xuống SQL. Cách dùng, tên hint và sự hỗ trợ phụ thuộc Hibernate version.

Hibernate 6 không hỗ trợ dùng lại nguyên cơ chế hint `passDistinctThrough` của Hibernate 5; không nên sao chép các đoạn code tối ưu cũ mà không đọc hướng dẫn migration của chính version.

Bài học về kiến trúc: **cấu hình tối ưu SQL là chi tiết của provider, không phải quy tắc portable của JPQL**. Code nghiệp vụ phải đúng về tập kết quả trước, rồi mới tối ưu dựa trên SQL log và phép đo.

### 15.4. Không suy từ SQL log ra số object Java

SQL log có thể hiển thị năm hàng được trả từ JOIN, nhưng Hibernate có thể tạo hoặc tái sử dụng chỉ vài entity instance theo primary key. Ngược lại, một result list có thể chứa cùng reference nhiều lần trước khi được khử trùng.

Khi phân tích, quan sát đủ ba tầng:

~~~text
SQL result rows
    |
    v
Persistence context / entity materialization
    |
    v
JPQL result list / projection
~~~

Ba con số “hàng SQL”, “instance managed” và “phần tử List” không bắt buộc bằng nhau.

---

## 16. Phân biệt DISTINCT với khử trùng trong Java

Một developer đôi khi viết:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        JOIN o.lines l
        """,
        PurchaseOrder.class
    )
    .getResultList();

List<PurchaseOrder> unique =
    orders.stream().distinct().toList();
~~~

Cách này có thể loại phần tử Java trùng theo `equals()` của entity. Nhưng có những đánh đổi:

- Query có thể tải nhiều hàng dữ liệu không cần thiết.
- `stream().distinct()` không thay đổi SQL đã chạy.
- Equality của entity có thể được triển khai theo business key, ID hoặc object reference; nếu không đúng với identity mong muốn, kết quả Java có thể khác ý nghĩa JPQL.
- Có thể phát sinh lazy load nếu `equals/hashCode` không được thiết kế tốt.
- Nếu phân trang trước khi distinct ở Java, mỗi trang có thể thiếu phần tử mong đợi.

Vì vậy, khi mục tiêu là **tập kết quả query phân biệt**, nên biểu đạt nó trong JPQL hoặc sửa cấu trúc query, không dựa vào một bước lọc Java như phương án mặc định.

### 16.1. HashSet không phải thay thế mọi lúc

~~~java
Set<PurchaseOrder> unique = new HashSet<>(orders);
~~~

Những vấn đề tương tự tồn tại:

- Không bảo đảm thứ tự nếu dùng HashSet.
- Dựa vào `equals/hashCode`.
- Không giúp giảm dữ liệu truy xuất từ DB.
- Có thể làm mất những phần tử bị coi là bằng nhau theo business-key equality dù primary key khác.
- Với entity ID tự sinh, hashCode thay đổi theo vòng đời có thể làm Set hoạt động không như mong đợi.

Không dùng `HashSet` như bằng chứng rằng JPQL DISTINCT đang đúng hay sai.

### 16.2. Khi nào lọc Java vẫn phù hợp?

Lọc Java có thể hợp lý khi:

- Tập dữ liệu đã rất nhỏ.
- Các đối tượng không phải entity JPA và quy tắc uniqueness rõ ràng.
- Cần loại trùng theo một quy tắc Java khác semantics SQL, chẳng hạn so sánh normalized business key đặc thù.
- Dữ liệu đã tải để phục vụ công việc khác, không phát sinh truy vấn lớn thêm.

Nhưng hãy diễn đạt rõ lý do: đó là **post-processing**, không phải semantics DISTINCT của JPQL.

---

## 17. DISTINCT và nhiều JOIN collection

Khi JOIN đồng thời hai collection, số hàng trung gian có thể tăng theo tích số phần tử.

Giả sử một Order có:

- 4 OrderLine.
- 3 PaymentAttempt.

Nếu query join cả hai collection:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
JOIN o.paymentAttempts p
~~~

một Order có thể đóng góp tới **4 × 3 = 12 hàng SQL** nếu dữ liệu và điều kiện join tương ứng.

`DISTINCT o` giúp result list root không trùng nhưng **không làm mất chi phí 12 tổ hợp JOIN ở database**.

Với `JOIN FETCH` hai collection, còn có các hạn chế của provider và cách mapping `List`/bag. Ví dụ Hibernate có thể từ chối fetch đồng thời nhiều bag collection bằng lỗi `MultipleBagFetchException`. Đây là vấn đề riêng với mô hình fetch nhiều collection, không thể sửa bằng cách thêm DISTINCT.

Các hướng thiết kế:

- Chỉ fetch một collection trong một query.
- Tách query thành các bước, để persistence context ghép entity theo identity.
- Dùng batch fetching/subselect fetching nếu thích hợp.
- Dùng DTO projection cho báo cáo cần các aggregate thay vì graph đầy đủ.
- Tránh đưa tất cả association vào một SQL JOIN chỉ vì muốn “một lần truy vấn”.

### 17.1. COUNT sau multiple JOIN có thể bị nhân số

Nếu muốn đếm line và payment attempts của mỗi Order, câu:

~~~jpql
SELECT o.id, COUNT(l), COUNT(p)
FROM PurchaseOrder o
JOIN o.lines l
JOIN o.paymentAttempts p
GROUP BY o.id
~~~

có thể đếm mỗi line nhiều lần do tích Cartesian của hai collection. Trong một số trường hợp phải dùng `COUNT(DISTINCT l.id)` và `COUNT(DISTINCT p.id)`, hoặc query riêng, tùy mục tiêu, tính portable và cardinality.

Đây là ví dụ mà DISTINCT bên trong aggregate giúp giải quyết **nhân hàng khi đếm**, chứ `SELECT DISTINCT` ở ngoài không thay được.

---

## 18. DISTINCT và các toán tử EXISTS, IN

Một quy tắc thiết kế quan trọng: **chỉ JOIN khi cần dùng giá trị của đối tượng liên quan trong kết quả hoặc điều kiện thật sự cần join**. Nếu chỉ cần biết một liên kết tồn tại, `EXISTS` thường diễn đạt tốt hơn.

### 18.1. Dùng JOIN + DISTINCT

~~~jpql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :paid
~~~

Mục tiêu: tìm các Customer có ít nhất một Order PAID. Nếu Customer có nhiều Order PAID, JOIN nhân hàng rồi DISTINCT khử trùng root Customer.

### 18.2. Dùng EXISTS

~~~jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
~~~

Mỗi Customer outer row chỉ được trả một lần, vì câu hỏi là “có tồn tại Order PAID hay không”.

Java:

~~~java
List<Customer> customers = em.createQuery(
        """
        SELECT c
        FROM Customer c
        WHERE EXISTS (
            SELECT o.id
            FROM PurchaseOrder o
            WHERE o.customer = c
              AND o.status = :paid
        )
        ORDER BY c.id
        """,
        Customer.class
    )
    .setParameter("paid", OrderStatus.PAID)
    .getResultList();
~~~

Không cần DISTINCT nếu outer query chỉ đi từ Customer và không có join khác nhân hàng.

### 18.3. Dùng IN-subquery

Một lựa chọn khác:

~~~jpql
SELECT c
FROM Customer c
WHERE c.id IN (
    SELECT o.customer.id
    FROM PurchaseOrder o
    WHERE o.status = :paid
)
~~~

Truy vấn ngoài vẫn chọn mỗi Customer entity một lần từ bảng Customer. DB optimizer có thể tối ưu các kiểu semi-join/EXISTS/IN khác nhau tùy index và dữ liệu.

**Đừng coi EXISTS luôn nhanh hơn JOIN DISTINCT.** Dùng nó vì nó biểu đạt ngữ nghĩa tồn tại rõ ràng, rồi đo plan nếu cần tối ưu.

---

## 19. DISTINCT và hiệu năng: phải đo đúng thứ cần tối ưu

Một truy vấn có `DISTINCT` có thể tiết kiệm dữ liệu trả về, hoặc có thể làm database thêm bước sort/hash tốn kém. Kết quả phụ thuộc vào:

- Kích thước dữ liệu và số giá trị phân biệt.
- Index, collation và kiểu dữ liệu được chọn.
- Có JOIN to-many hay không.
- Có GROUP BY, ORDER BY, pagination hay không.
- SQL generated từ JPQL và provider.
- Độ rộng hàng, số lượng cột trong SELECT.
- Thống kê optimizer, bộ nhớ sort/hash và disk spill.
- Bộ nhớ của persistence context khi materialize nhiều entity.

### 19.1. Một bảng tình huống

| Query | DISTINCT thường giúp gì? | Điều cần cảnh giác |
|---|---|---|
| `SELECT DISTINCT c.fullName FROM Customer c` | Chỉ trả các tên phân biệt | Hai khách trùng tên bị gộp |
| `SELECT DISTINCT c FROM Customer c JOIN c.orders o` | Không trả trùng root Customer theo identity | JOIN vẫn có thể tạo nhiều hàng SQL |
| `SELECT DISTINCT o.id, o.status FROM PurchaseOrder o` | Có thể dư thừa vì ID đã unique | DISTINCT có thể tạo thao tác SQL không cần thiết |
| `SELECT DISTINCT o FROM PurchaseOrder o LEFT JOIN FETCH o.lines` | Định nghĩa kết quả root phân biệt; hành vi auto-dedup tùy Hibernate version | SQL DISTINCT có thể không giảm số hàng fetch, pagination nguy hiểm |
| `SELECT DISTINCT o.status, o.totalAmount` | Gộp cặp giá trị trùng | Không phải mỗi status một hàng |
| `COUNT(DISTINCT o.id)` sau JOIN collection | Đếm Order identity thực sự | Có thể phát sinh chi phí aggregate/unique |
| EXISTS lọc Order theo line | Tránh nhân root rows ở outer query | Cần index/filter tốt và plan phù hợp |

### 19.2. Quan sát SQL

Trong ứng dụng Hibernate, có thể bật logger phù hợp cho SQL:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
spring.jpa.show-sql=false
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Ví dụ trên phù hợp với ứng dụng Spring Boot có Hibernate và cần điều chỉnh theo phiên bản. SQL logger cho biết câu lệnh được sinh; thống kê và DB execution plan giúp hiểu số statement/hàng/chi phí.

Không bật bind-parameter TRACE trong production mà không kiểm soát vì log có thể chứa dữ liệu nhạy cảm.

### 19.3. Cần xem gì ở query plan?

Đối với PostgreSQL hoặc DBMS có công cụ tương tự, kiểm tra:

- Join method: nested loop, hash join, merge join.
- Số hàng estimated và actual ở từng bước.
- Sort / HashAggregate / Unique cho DISTINCT.
- Có sử dụng index cho join/filter không.
- Memory/disk spill và thời gian thực thi.
- Lượng dữ liệu từ DB tới ứng dụng.
- Số root entity trong List và số collection element thực sự cần.

Nếu SELECT DISTINCT chỉ trả 10 Order nhưng SQL phải duyệt 10 triệu tổ hợp join, vấn đề không được giải quyết chỉ bằng việc kết quả Java ngắn.

### 19.4. Không dùng DISTINCT như công cụ sửa N+1

N+1 xảy ra khi ứng dụng tải nhiều entity rồi truy cập association lazy khiến nhiều SQL phát sinh. Thêm DISTINCT vào query root:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
~~~

không tự tải `o.customer` hoặc `o.lines` theo fetch plan mong muốn. Nó chỉ thay semantics loại kết quả trùng.

Muốn xử lý N+1, cần thiết kế JOIN FETCH (có kiểm soát), entity graph, batch fetch hoặc DTO projection. DISTINCT có thể là một phần của query fetch nhưng không phải lời giải thay thế fetch planning.

---

## 20. Những lỗi thường gặp

### Lỗi 1: Nghĩ DISTINCT tên đồng nghĩa DISTINCT khách hàng

~~~jpql
SELECT DISTINCT c.fullName FROM Customer c
~~~

Nếu hai Customer cùng tên An, kết quả chỉ có một An. Muốn các entity khác nhau, chọn `DISTINCT c`; muốn DTO riêng từng khách, chọn ID kèm tên.

### Lỗi 2: Nghĩ persistence context tự loại phần tử lặp trong List

Identity map giữ một managed instance theo PK, nhưng một List có thể chứa cùng reference nhiều lần. Hành vi auto-dedup của Hibernate tùy loại query/version; cần hiểu quy tắc của chính truy vấn.

### Lỗi 3: Thêm DISTINCT cho query từ một bảng có PK unique rồi tin rằng tốt hơn

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
~~~

Nếu không có JOIN gây nhân hàng và không có lý do khác, DISTINCT có thể không thêm giá trị chức năng, nhưng có thể thêm chi phí SQL.

### Lỗi 4: Trộn entity và scalar rồi mong mỗi entity một hàng

~~~jpql
SELECT DISTINCT o, l.productCode
FROM PurchaseOrder o
JOIN o.lines l
~~~

Một Order có nhiều productCode khác nhau sẽ xuất hiện trong nhiều tuple. Muốn mỗi Order một hàng, chỉ chọn entity root hoặc viết aggregate/DTO theo đúng nhóm.

### Lỗi 5: Dùng DISTINCT để lấy “record mới nhất từng nhóm”

`SELECT DISTINCT c FROM ... ORDER BY o.createdAt DESC` không xác định Order mới nhất của mỗi Customer. Cần query theo MAX hoặc cơ chế top-per-group có tie-breaker rõ ràng.

### Lỗi 6: Dùng DISTINCT với JOIN FETCH rồi nghĩ pagination sẽ đúng và nhanh

Collection fetch join có thể tạo nhiều hàng cho một root; limit/offset ở SQL có thể làm trang/collection không chính xác. Provider có thể phân trang trong memory. Dùng hai bước ID-then-fetch hoặc DTO projection.

### Lỗi 7: Dùng COUNT(o) sau join rồi gọi đó là số entity

Một Order có ba lines đóng góp ba hàng join. Dùng `COUNT(DISTINCT o.id)` khi mục tiêu là số Order duy nhất, hoặc `EXISTS` để tránh nhân hàng.

### Lỗi 8: Cho rằng COUNT DISTINCT đếm null như SELECT DISTINCT

`SELECT DISTINCT nullableValue` có thể trả null một lần, trong khi `COUNT(DISTINCT nullableValue)` không đếm null.

### Lỗi 9: Cho rằng DISTINCT là unique constraint

SELECT DISTINCT chỉ làm kết quả truy vấn khác đi. Nó không cấm trùng lặp trong database hay ngăn transaction song song ghi dữ liệu trùng. Cần database constraints.

### Lỗi 10: Khử trùng bằng HashSet trên entity không có equality phù hợp

Entity có equality theo business key hoặc ID tự sinh có thể gây tập Java khác semantics entity identity mong muốn. Ngoài ra, dữ liệu trùng đã được tải từ DB trước khi lọc.

### Lỗi 11: Copy cấu hình passDistinctThrough từ Hibernate 5 sang Hibernate 6

Các hint tối ưu này là provider-specific và đã thay đổi. Cần phân biệt JPQL semantics với đường đi SQL của version đang dùng.

### Lỗi 12: Không chú ý collation và BigDecimal scale

DISTINCT ở database có thể coi hai chuỗi theo collation hoặc hai số DECIMAL là tương đương trong khi Java `String.equals()/BigDecimal.equals()` có quy tắc khác.

### Lỗi 13: Dùng JOIN FETCH nhiều collection và kỳ vọng DISTINCT giải quyết mọi vấn đề

JOIN nhiều collection có thể tạo sản phẩm số hàng lớn, thậm chí Hibernate từ chối multiple bags. DISTINCT root không xóa chi phí nhân hàng hoặc làm fetch plan trở nên hợp lý.

### Lỗi 14: SELECT DISTINCT status nhưng ORDER BY field bất kỳ không thuộc projection

Một nhóm status có nhiều createdAt khác nhau; thứ tự không xác định rõ. Một số DBMS từ chối SQL. Dùng aggregate `MAX(createdAt)`/GROUP BY nếu cần thời gian đại diện.

### Lỗi 15: Dùng DISTINCT để che dữ liệu JOIN sai

Nếu JOIN không đúng association hoặc điều kiện FK, nó có thể tạo số hàng sai rất lớn. DISTINCT có thể làm result cuối trông “đúng” nhưng che lỗi cấu trúc truy vấn. Cần hiểu cardinality, join path và condition trước.

---

## 21. Quy trình lựa chọn DISTINCT theo mục tiêu

Thay vì thêm `DISTINCT` vì thấy danh sách dài, hãy trả lời lần lượt:

1. **Mỗi hàng kết quả đại diện cho cái gì?** Entity, giá trị scalar, tuple, DTO hay nhóm aggregate?
2. **Nguồn trùng nằm ở đâu?** Dữ liệu có giá trị lặp, JOIN to-many, hay query đang chọn nhiều cột với cardinality lớn?
3. **Tiêu chí unique thật sự là gì?** Primary key entity, tên, status, cặp thuộc tính, hay một business key?
4. **Có cần giá trị của phía many trong SELECT không?** Nếu không, dùng `EXISTS` hoặc chọn chỉ root có thể tốt hơn.
5. **Có dùng JOIN FETCH collection không?** Xem provider/version và chiến lược phân trang.
6. **Có cần COUNT tổng trang?** `COUNT(DISTINCT id)` hoặc `EXISTS` có thể tương ứng hơn `COUNT(root)` sau JOIN.
7. **Có yêu cầu ORDER BY ổn định?** Đừng sắp xếp theo field không có một giá trị rõ cho một hàng đã distinct.
8. **Có cần DTO hay entity managed?** DTO cho read model, entity cho use case chỉnh sửa.
9. **Có cần tối ưu hiệu năng?** Xem SQL, execution plan, số hàng trung gian và số round-trip.
10. **Có phải dữ liệu trùng là lỗi domain?** Nếu có, thiết kế unique constraint chứ không chỉ SELECT DISTINCT.

### 21.1. Bảng quyết định nhanh

| Nhu cầu | Cách viết nên cân nhắc |
|---|---|
| Mọi Customer có Order PAID, không trùng Customer | `SELECT DISTINCT c ... JOIN c.orders o ...` hoặc `SELECT c WHERE EXISTS (...)` |
| Danh sách tên Customer phân biệt | `SELECT DISTINCT c.fullName` |
| Danh sách Customer phân biệt theo PK | `SELECT DISTINCT c` hoặc `SELECT c` nếu query không nhân hàng |
| Mỗi Order một hàng khi JOIN lines để lọc | `SELECT DISTINCT o` hoặc `EXISTS` |
| Một hàng cho mỗi `(status, amount)` | `SELECT DISTINCT o.status, o.totalAmount` |
| Một hàng cho mỗi status với tổng tiền | `GROUP BY o.status` + `SUM(o.totalAmount)` |
| Đếm Order có lines sau JOIN | `COUNT(DISTINCT o.id)` |
| Trang Order 20 phần tử có đầy đủ lines | Phân trang ID trước, fetch lines ở query sau |
| Trang chỉ có ID, tên khách, số tiền | DTO projection, không JOIN FETCH collection |
| Xử lý hai Customer trùng email trong DB | Ràng buộc UNIQUE, data migration; không dùng DISTINCT để che |
| Tải Order và lines với Hibernate 6 | Hiểu auto-dedup root fetch-join, kiểm tra version/SQL; không thêm DISTINCT như nghi thức bắt buộc |

---

## 22. Bài tập vận dụng

### Bài tập 1 — Hai khách hàng cùng tên

Dữ liệu:

~~~text
Customer(id=1, name=An)
Customer(id=2, name=An)
Customer(id=3, name=Bình)
~~~

Hỏi: `SELECT DISTINCT c FROM Customer c` trả bao nhiêu entity? `SELECT DISTINCT c.fullName FROM Customer c` trả bao nhiêu giá trị? Vì sao khác nhau?

**Gợi ý:** entity phân biệt theo identity, scalar phân biệt theo giá trị tên.

### Bài tập 2 — Order có hai dòng

Order 101 có Line 501 và 502. Query:

~~~jpql
SELECT o
FROM PurchaseOrder o JOIN o.lines l
WHERE o.id = 101
~~~

Về quan hệ, JOIN tạo bao nhiêu hàng? `SELECT DISTINCT o` nên biểu diễn bao nhiêu Order identity? Vì sao cùng entity instance có thể xuất hiện nhiều lần trong một List khi không khử trùng theo semantics truy vấn?

### Bài tập 3 — DISTINCT nhiều biểu thức

Có:

~~~text
(NEW, 120000)
(PAID, 200000)
(PAID, 200000)
(PAID, 180000)
~~~

Query `SELECT DISTINCT o.status, o.totalAmount` giữ bao nhiêu tuple? Nếu thêm `o.id` vào SELECT thì điều gì thay đổi?

### Bài tập 4 — COUNT khác COUNT DISTINCT

Trong một JOIN Order–Line, Order 101 có 2 line, Order 102 có 1 line, Order 103 không có line.

Hãy tính:

~~~jpql
SELECT COUNT(o) FROM PurchaseOrder o JOIN o.lines l
~~~

và:

~~~jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o JOIN o.lines l
~~~

**Gợi ý:** 3 hàng JOIN nhưng 2 Order identity.

### Bài tập 5 — NULL

Giả sử một thuộc tính nullable có giá trị:

~~~text
null, null, A, B, A
~~~

So sánh kết quả `SELECT DISTINCT value` và `COUNT(DISTINCT value)`. Vì sao số lượng phần tử trong danh sách không nhất thiết bằng count distinct?

### Bài tập 6 — DTO projection

Thiết kế DTO chứa `orderId`, `status` và `totalAmount`. Viết `SELECT DISTINCT NEW ...` để tránh trùng các hàng khi JOIN collection. Vì sao cần có `orderId` nếu muốn giữ hai Order khác ID nhưng giống status và amount?

### Bài tập 7 — EXISTS thay JOIN DISTINCT

Viết lại:

~~~jpql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :paid
~~~

thành truy vấn dùng `EXISTS` với ý nghĩa “có ít nhất một Order PAID”. Giải thích vì sao outer query không bị nhân hàng bởi số Order.

### Bài tập 8 — JOIN FETCH và trang 20 Order

Một Order có 10 lines. Vì sao `JOIN FETCH o.lines` kết hợp `setMaxResults(20)` có thể khó phân trang đúng/nhanh? Đề xuất quy trình hai bước ID-then-fetch và cách khôi phục thứ tự Order.

### Bài tập 9 — Hóa đơn mới nhất theo trạng thái

Bạn cần mỗi status một hàng gồm thời điểm Order mới nhất. Vì sao `SELECT DISTINCT status ORDER BY createdAt DESC` chưa diễn đạt đúng? Viết query `GROUP BY status` và `MAX(createdAt)`.

### Bài tập 10 — Nhiều quan hệ to-many

Một Order có 4 lines và 3 payment attempts. JOIN cả hai có thể tạo bao nhiêu tổ hợp? Vì sao `SELECT DISTINCT o` vẫn có thể rất tốn kém? Nếu cần đếm riêng số line và payment, nên thay đổi biểu thức aggregate hoặc cấu trúc query thế nào?

### Bài tập 11 — Mã sản phẩm

Các OrderLine có productCode:

~~~text
BOOK-1, PEN-1, BOOK-1, BOOK-1
~~~

Viết JPQL chọn các productCode phân biệt. Sau đó viết JPQL `COUNT(DISTINCT ...)` để biết có bao nhiêu mã khác nhau.

### Bài tập 12 — Kiểm tra query plan

Một query `SELECT DISTINCT o LEFT JOIN FETCH o.lines` trả 100 Order nhưng database xử lý 50.000 hàng JOIN. Hãy mô tả những chỉ số cần quan sát và ba lựa chọn thiết kế giảm chi phí mà không phụ thuộc vào việc thêm DISTINCT nhiều lần.

---

## 23. Ghi nhớ

- **`DISTINCT` loại trùng theo kết quả được chọn**, không phải cứ có DISTINCT là “một hàng cho mỗi entity trong FROM”.
- **Entity-valued DISTINCT** hướng tới entity identity; hai entity khác PK không bị gộp dù giống các field khác.
- **Scalar DISTINCT** hướng tới giá trị thuộc tính/biểu thức; hai Customer khác ID nhưng cùng tên có thể cho một chuỗi tên.
- **Nhiều biểu thức DISTINCT** xét **cả tuple**. `DISTINCT status, totalAmount` không có nghĩa mỗi status một hàng.
- **Persistence context identity map** chỉ đảm bảo một managed instance cho mỗi identity trong context, không tự định nghĩa số phần tử của result list.
- **JOIN to-many** nhân số hàng trung gian. `SELECT DISTINCT root` có thể giúp loại root duplicate, nhưng không xóa toàn bộ chi phí JOIN.
- **`COUNT(DISTINCT id)`** dùng để đếm entity phân biệt sau JOIN khi `COUNT(root)` có thể đếm nhiều hàng cho một root.
- **COUNT DISTINCT bỏ qua NULL**, trong khi SELECT DISTINCT có thể trả một giá trị null duy nhất.
- **DTO projection** cũng có thể dùng DISTINCT; việc loại trùng không được hiểu đơn giản là HashSet của DTO.
- **`GROUP BY`** phù hợp khi cần một hàng mỗi nhóm với aggregate; DISTINCT không tự chọn “bản ghi đại diện mới nhất” của nhóm.
- **Hibernate 5 và 6 có khác biệt** về duplicate root results của collection fetch join và các hint kiểm soát SQL DISTINCT.
- **JOIN FETCH collection + pagination** là tình huống đặc biệt cần thiết kế hai bước hoặc DTO; DISTINCT không tự sửa được.
- **EXISTS** thường diễn đạt tốt điều kiện “có ít nhất một đối tượng liên quan” và tránh nhân outer root rows.
- **ORDER BY với DISTINCT** cần semantics rõ ràng; sắp xếp theo trường không nằm trong projection có thể không portable.
- **DISTINCT không thay unique constraint**, không sửa N+1 và không phải công cụ tối ưu hiệu năng mặc định.
- Muốn chọn đúng giữa `DISTINCT`, `GROUP BY`, `EXISTS`, fetch graph và DTO, phải xác định **đơn vị kết quả và tiêu chí duy nhất thực sự của use case**.

**Kết luận:** Khi viết JPQL nâng cao, đừng thêm `DISTINCT` chỉ vì nhìn thấy dữ liệu lặp. Hãy hỏi đang muốn một entity phân biệt theo primary key, một giá trị scalar phân biệt, hay một tuple/DTO phân biệt theo toàn bộ biểu thức. Sau đó hiểu rõ cách JOIN nhân hàng, cách provider dựng entity từ SQL và giới hạn phân trang/fetch join. Một câu truy vấn đúng về semantics thường bắt đầu từ **mô hình dữ liệu và cardinality**, còn tối ưu DISTINCT cần dựa trên SQL, provider version và phép đo thực tế.
