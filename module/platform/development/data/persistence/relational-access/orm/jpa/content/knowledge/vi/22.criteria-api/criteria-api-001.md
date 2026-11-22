# Khi nào nên xây dựng truy vấn động bằng Criteria API trong JPA

Trong một ứng dụng JPA, nhiều truy vấn có cấu trúc cố định: tìm đơn hàng theo ID, lấy tất cả đơn hàng đã thanh toán, hoặc liệt kê sản phẩm theo danh mục. Với những yêu cầu như vậy, JPQL thường ngắn gọn và dễ đọc.

Tình huống thay đổi khi người dùng mở màn hình **tìm kiếm nâng cao**. Có người chỉ chọn trạng thái đơn hàng; có người lọc thêm khoảng ngày; người khác nhập tên khách hàng, khoảng tổng tiền, sản phẩm nằm trong đơn và cách sắp xếp. Các điều kiện có thể xuất hiện hoặc vắng mặt độc lập.

Nếu cố viết một câu JPQL riêng cho mọi tổ hợp, số biến thể tăng rất nhanh. Nếu ghép chuỗi JPQL tùy tiện, ứng dụng dễ tạo ra mã khó bảo trì, điều kiện sai, phân trang không nhất quán và các rủi ro khi xử lý đầu vào động.

**Criteria API** là một API chuẩn của Jakarta Persistence giúp xây dựng cây biểu thức truy vấn bằng Java thay vì tạo toàn bộ JPQL bằng chuỗi văn bản. Đây là một công cụ rất phù hợp khi **hình dạng truy vấn phụ thuộc vào điều kiện tại runtime**, đặc biệt khi có nhiều bộ lọc tùy chọn và cần tái sử dụng logic tạo điều kiện.

Bài học này tập trung vào câu hỏi **khi nào nên sử dụng Criteria API**, đồng thời hướng dẫn xây dựng truy vấn động một cách có cấu trúc: thêm điều kiện tùy chọn, kết hợp AND/OR, JOIN, EXISTS, khoảng thời gian, tìm kiếm LIKE, sắp xếp, phân trang, COUNT, projection và kiểm thử. Mục tiêu không phải thay thế mọi câu JPQL bằng Criteria, mà là biết **chọn công cụ có độ phức tạp phù hợp với nghiệp vụ**.

## 1. Bắt đầu từ bài toán: Màn hình tìm kiếm đơn hàng

Giả sử hệ thống thương mại điện tử có một màn hình tìm kiếm đơn hàng với các trường:

- Trạng thái: NEW, PAID, CANCELLED.
- Khách hàng: lọc theo ID.
- Từ ngày và đến ngày tạo đơn.
- Tổng tiền nhỏ nhất và lớn nhất.
- Từ khóa tìm theo mã đơn hoặc tên khách hàng.
- Sản phẩm xuất hiện trong ít nhất một dòng của đơn.
- Có hoặc không có dòng hàng.
- Sắp xếp theo ngày tạo, tổng tiền hoặc mã đơn.
- Phân trang theo số trang và kích thước trang.

Người dùng không phải nhập tất cả. Ví dụ:

~~~text
Request A:
  status = PAID
  page = 0
  size = 20

Request B:
  customerId = 42
  createdFrom = 2026-01-01T00:00:00Z
  createdTo   = 2026-02-01T00:00:00Z
  minTotal = 500000
  sort = TOTAL_DESC

Request C:
  keyword = "nguyen"
  productId = 17
  hasLines = true
~~~

Với mỗi request, cấu trúc `WHERE` thực sự khác nhau:

~~~sql
-- Request A
WHERE status = 'PAID'
~~~

~~~sql
-- Request B
WHERE customer_id = 42
  AND created_at >= :from
  AND created_at < :to
  AND total_amount >= 500000
~~~

~~~sql
-- Request C, ý tưởng
WHERE (
    LOWER(order_number) LIKE :keyword
    OR LOWER(customer_name) LIKE :keyword
)
AND EXISTS (
    SELECT 1
    FROM order_line l
    WHERE l.order_id = o.id
      AND l.product_id = 17
)
~~~

Hệ thống có thể thêm bộ lọc mới theo thời gian. Đây chính là **động lực thực tế** để dùng Criteria API: tạo cấu trúc truy vấn bằng các thành phần có điều kiện, không duy trì một tập lớn JPQL biến thể.

### 1.1. Số tổ hợp điều kiện tăng như thế nào?

Nếu có \(n\) bộ lọc độc lập và mỗi bộ lọc có hai trạng thái — được cung cấp hoặc không — thì về mặt lý thuyết có tới:

\[
2^n
\]

tổ hợp hiện diện/vắng mặt. Với 8 bộ lọc, có tới 256 tổ hợp; với 10 bộ lọc, có tới 1.024 tổ hợp.

Điều đó **không** có nghĩa phải viết 1.024 câu JPQL, bởi có những cách khác như điều kiện null hoặc query builder. Nhưng nó minh họa lý do mã xử lý từng tổ hợp bằng `if/else` thủ công có thể trở nên rất khó kiểm soát.

Criteria API cho phép tạo **một quy trình xây dựng truy vấn** với mỗi filter đóng góp một `Predicate` khi cần.

## 2. Trường hợp không cần Criteria API

Không nên dùng Criteria chỉ vì ứng dụng có JPA.

Ví dụ truy vấn cố định:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.status = :status " +
        "ORDER BY o.createdAt DESC",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
~~~

Trong trường hợp này JPQL rõ, ngắn và dễ rà soát. Phiên bản Criteria tương đương thường dài hơn:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

cq.select(root)
  .where(cb.equal(root.get("status"), OrderStatus.PAID))
  .orderBy(cb.desc(root.get("createdAt")));

List<PurchaseOrder> orders =
    em.createQuery(cq).getResultList();
~~~

Hai đoạn diễn đạt cùng mục tiêu. Nếu truy vấn không có phần động đáng kể, Criteria tạo thêm code mà chưa đem lại lợi ích rõ ràng.

### 2.1. Quy tắc lựa chọn ban đầu

| Đặc điểm use case | Thường cân nhắc |
|---|---|
| Truy vấn có cấu trúc cố định, ít điều kiện | JPQL hoặc named query |
| Một hoặc hai tham số luôn có | JPQL với `setParameter` |
| Nhiều bộ lọc có thể bỏ trống, thêm/bớt độc lập | Criteria API |
| Điều kiện AND/OR lồng nhau theo cấu hình | Criteria API hoặc query DSL phù hợp |
| Cần ghép nhiều nhóm predicate dùng chung | Criteria API, Specification hoặc predicate builder |
| Phần JOIN/EXISTS thay đổi theo bộ lọc | Criteria API đáng cân nhắc |
| Query SQL rất đặc thù với CTE/window/vendor feature | Native SQL, jOOQ hoặc giải pháp phù hợp |
| Chỉ cần lấy entity theo khóa chính | `EntityManager.find` / repository |
| Truy vấn báo cáo cố định, projection đơn giản | JPQL constructor expression có thể ngắn hơn |
| Dự án dùng Spring Data và có bộ lọc tùy chọn | Specification xây trên Criteria có thể thuận tiện |

**Tiêu chí quyết định không phải “Criteria nhanh hơn JPQL”, mà là “việc xây truy vấn động bằng Java có giúp giảm độ phức tạp và lỗi không?”** Cả JPQL và Criteria đều được provider dịch thành SQL; hiệu năng chủ yếu phụ thuộc SQL sinh ra, dữ liệu, index và execution plan.

## 3. Bốn thành phần cốt lõi của Criteria API

API chính nằm trong `jakarta.persistence.criteria`.

~~~java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;
import jakarta.persistence.criteria.Predicate;
~~~

Một truy vấn điển hình được xây bằng:

1. **`CriteriaBuilder`**: factory tạo biểu thức, predicate, phép toán và query.
2. **`CriteriaQuery<T>`**: cây truy vấn có kiểu kết quả `T`.
3. **`Root<T>`**: entity root trong mệnh đề FROM, tương đương alias ở JPQL.
4. **`Predicate`**: biểu thức điều kiện dùng trong WHERE/HAVING.

Ví dụ:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

Predicate paid =
    cb.equal(order.get("status"), OrderStatus.PAID);

cq.select(order);
cq.where(paid);

List<PurchaseOrder> result =
    em.createQuery(cq).getResultList();
~~~

JPQL tương đương:

~~~sql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
~~~

Ở ví dụ Criteria, `OrderStatus.PAID` là giá trị trong biểu thức Criteria; provider chịu trách nhiệm chuyển thành SQL và bind theo cơ chế của nó.

### 3.1. CriteriaQuery khác TypedQuery

Hai dòng này thường bị nhầm:

~~~java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
~~~

~~~java
TypedQuery<PurchaseOrder> query =
    em.createQuery(cq);
~~~

`CriteriaQuery` là **mô tả cấu trúc truy vấn**. Nó chưa thực thi SQL. `TypedQuery` là đối tượng JPA dùng để đặt các option runtime như pagination, hint, lock mode và thực thi bằng `getResultList()`.

Có thể hình dung:

~~~text
CriteriaBuilder
       |
       v
CriteriaQuery<T>  -- tạo expression tree
       |
       +-- Root<T>
       +-- Predicate
       +-- Selection
       +-- Order
       +-- GroupBy
       |
       v
EntityManager.createQuery(criteriaQuery)
       |
       v
TypedQuery<T>
       |
       +-- setFirstResult(...)
       +-- setMaxResults(...)
       +-- setParameter(...)
       +-- setHint(...)
       |
       v
getResultList() / getSingleResult()
       |
       v
JPA provider -> SQL -> Database
~~~

### 3.2. Criteria không phải thao tác SQL trực tiếp

`root.get("status")` là truy cập thuộc tính **entity Java**, không phải tên cột SQL. JPA provider ánh xạ thuộc tính đó sang `status` hoặc tên cột được khai báo bằng annotation.

Tương tự, `root.join("customer")` làm việc với quan hệ entity, không nhất thiết có một câu SQL JOIN đúng hệt cú pháp Java trong mọi cấu hình.

## 4. Mô hình entity dùng xuyên suốt bài học

Giả sử có các entity `Customer`, `Product`, `PurchaseOrder` và `OrderLine`.

### 4.1. Enum trạng thái

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

### 4.2. Customer

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### 4.3. Product

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 50)
    private String sku;

    protected Product() {
    }

    public Long getId() {
        return id;
    }
}
~~~

### 4.4. PurchaseOrder

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(name = "order_number", nullable = false,
            unique = true, length = 40)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }
}
~~~

### 4.5. OrderLine

~~~java
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
@Table(name = "order_line")
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

    private int quantity;

    protected OrderLine() {
    }
}
~~~

Các entity được rút gọn nhằm minh họa Criteria. Trong dự án thực, cần thêm constructor nghiệp vụ, validation, migration, các method và ràng buộc thích hợp.

Quan hệ chính:

~~~text
Customer (1) ---- (N) PurchaseOrder
                           |
                           | 1
                           v
                      OrderLine (N) ---- (1) Product
~~~

## 5. Định nghĩa đối tượng chứa bộ lọc

Trước khi viết Criteria, nên gom các tham số tìm kiếm vào một kiểu dữ liệu rõ ràng thay vì truyền mười tham số rời rạc.

Ví dụ Java record:

~~~java
package com.example.shop.search;

import com.example.shop.domain.OrderStatus;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderSearchFilter(
    OrderStatus status,
    Long customerId,
    Instant createdFromInclusive,
    Instant createdToExclusive,
    BigDecimal minTotal,
    BigDecimal maxTotal,
    String keyword,
    Long productId,
    Boolean hasLines,
    int page,
    int size,
    OrderSort sort,
    boolean descending
) {}
~~~

Enum sắp xếp:

~~~java
package com.example.shop.search;

public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    ORDER_NUMBER
}
~~~

**Điểm quan trọng:** Các trường null thể hiện bộ lọc **không được áp dụng**. Riêng `page`, `size`, `sort` nên được chuẩn hóa và xác thực trước khi repository xây query.

Ví dụ:

~~~text
OrderSearchFilter:
    status                 = PAID
    customerId             = null
    createdFromInclusive   = 2026-01-01T00:00:00Z
    createdToExclusive     = 2026-02-01T00:00:00Z
    minTotal               = 500000
    maxTotal               = null
    keyword                = "hanoi"
    productId              = null
    hasLines               = null
    page                   = 0
    size                   = 20
    sort                   = CREATED_AT
    descending             = true
~~~

Trong trường hợp này, repository không tạo điều kiện cho `customerId`, `maxTotal`, `productId` hay `hasLines`.

### 5.1. Phân biệt null, rỗng và giá trị hợp lệ

Một số quy tắc nên quyết định ở tầng input:

- `status = null`: không lọc theo trạng thái.
- `keyword = null` hoặc blank: không lọc theo từ khóa.
- `minTotal = 0`: **có thể là điều kiện hợp lệ**, không được bỏ qua chỉ vì là giá trị zero.
- `hasLines = false`: **có nghĩa nghiệp vụ**, khác hoàn toàn với null.
- `customerId = 0`: có thể không hợp lệ, không nên tự coi là “không lọc”.
- `page < 0` hoặc `size <= 0`: phải bị từ chối hoặc chuẩn hóa theo hợp đồng API.

Một query builder tốt không tự ý diễn giải mọi giá trị “falsy” thành vắng mặt.

## 6. Cách tạo danh sách Predicate động

Kỹ thuật nền tảng là tạo `List<Predicate>`, thêm điều kiện khi một giá trị lọc có mặt, rồi kết hợp tất cả bằng `cb.and(...)`.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

List<Predicate> predicates = new ArrayList<>();

if (filter.status() != null) {
    predicates.add(
        cb.equal(root.get("status"), filter.status())
    );
}

if (filter.customerId() != null) {
    predicates.add(
        cb.equal(
            root.get("customer").get("id"),
            filter.customerId()
        )
    );
}

if (filter.minTotal() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            root.get("totalAmount"),
            filter.minTotal()
        )
    );
}

cq.select(root);
cq.where(predicates.toArray(Predicate[]::new));

List<PurchaseOrder> orders =
    em.createQuery(cq).getResultList();
~~~

Khi một filter không được cung cấp, **không có predicate tương ứng**. Kết quả SQL là một tập điều kiện gọn hơn, thay vì cố dùng một số lượng lớn biểu thức null.

### 6.1. Tại sao `List<Predicate>` là một mô hình tốt?

Mỗi khối `if` có một trách nhiệm:

~~~text
status có mặt?       ---> thêm status = ?
customerId có mặt?   ---> thêm customer_id = ?
minTotal có mặt?     ---> thêm total_amount >= ?
keyword có mặt?      ---> thêm nhóm điều kiện LIKE
productId có mặt?    ---> thêm EXISTS subquery
~~~

Với n bộ lọc, code có xu hướng tăng tuyến tính theo n thay vì phải viết riêng từng tổ hợp.

### 6.2. Nếu danh sách Predicate rỗng?

~~~java
cq.where(predicates.toArray(Predicate[]::new));
~~~

Khi không có predicate, việc truyền mảng rỗng nghĩa là không có restriction tương ứng. Lưu ý: phương thức `where` thay thế các restriction đã đặt trước đó; đừng gọi `where` nhiều lần với ý nghĩ nó tự nối AND mọi lần.

Ví dụ **sai về kỳ vọng**:

~~~java
cq.where(cb.equal(root.get("status"), OrderStatus.PAID));
cq.where(cb.equal(root.get("customer").get("id"), 42L));
~~~

Lời gọi `where` thứ hai **thay thế** restriction được thiết lập bởi lời gọi thứ nhất; không tự động thành:

~~~sql
status = 'PAID' AND customer_id = 42
~~~

Cách đúng là kết hợp:

~~~java
cq.where(
    cb.and(
        cb.equal(root.get("status"), OrderStatus.PAID),
        cb.equal(root.get("customer").get("id"), 42L)
    )
);
~~~

hoặc gom predicate vào list và gọi `where` một lần.

## 7. `cb.conjunction()` và `cb.disjunction()`

Có những trường hợp query builder cần một predicate khởi tạo.

~~~java
Predicate all = cb.conjunction();
~~~

`cb.conjunction()` đại diện cho một điều kiện **đúng** nếu không có operand. Nó hữu ích khi bắt đầu xây một tập AND:

~~~java
Predicate combined = cb.conjunction();

if (filter.status() != null) {
    combined = cb.and(
        combined,
        cb.equal(root.get("status"), filter.status())
    );
}
~~~

Tương tự:

~~~java
Predicate none = cb.disjunction();
~~~

`cb.disjunction()` không có operand mang ý nghĩa **sai**; có thể dùng làm điểm bắt đầu cho một tập OR.

### 7.1. Không nhầm AND rỗng với OR rỗng

Về logic:

~~~text
AND với 0 điều kiện -> TRUE
OR  với 0 điều kiện -> FALSE
~~~

Do đó, nếu yêu cầu “có ít nhất một trạng thái thuộc danh sách” nhưng danh sách trạng thái rỗng, việc trả về tất cả bản ghi là một quyết định khác hoàn toàn với trả về không bản ghi nào.

Ứng dụng phải xác định semantics của collection rỗng theo nghiệp vụ, không vô tình để một query builder rơi vào kết quả rộng hơn dự kiến.

## 8. Kết hợp AND và OR theo nhóm rõ ràng

Tình huống:

> Lấy đơn hàng PAID, và từ khóa phải khớp **mã đơn hoặc tên khách hàng**.

Logic mong muốn:

~~~text
status = PAID
AND (
    orderNumber LIKE keyword
    OR customer.name LIKE keyword
)
~~~

Criteria:

~~~java
Join<PurchaseOrder, Customer> customer =
    root.join("customer", JoinType.INNER);

Path<String> orderNumber =
    root.get("orderNumber");

Path<String> customerName =
    customer.get("name");

String pattern = "%hanoi%";

Predicate matchOrderNumber =
    cb.like(cb.lower(orderNumber), pattern);

Predicate matchCustomerName =
    cb.like(cb.lower(customerName), pattern);

Predicate keywordGroup = cb.or(
    matchOrderNumber,
    matchCustomerName
);

Predicate finalFilter = cb.and(
    cb.equal(root.get("status"), OrderStatus.PAID),
    keywordGroup
);

cq.where(finalFilter);
~~~

SQL ý tưởng:

~~~sql
WHERE status = 'PAID'
  AND (
      LOWER(order_number) LIKE '%hanoi%'
      OR LOWER(customer.name) LIKE '%hanoi%'
  )
~~~

### 8.1. Sai lầm về độ ưu tiên toán tử

Nếu vô tình diễn đạt:

~~~text
(status = PAID AND orderNumber LIKE keyword)
OR customerName LIKE keyword
~~~

một đơn hàng CANCELLED cũng có thể xuất hiện chỉ vì tên khách hàng khớp từ khóa.

Khi xây Criteria, dùng `cb.and` và `cb.or` có cấu trúc rõ ràng để tránh nhầm vị trí dấu ngoặc trong chuỗi JPQL.

### 8.2. OR giữa nhiều nhóm điều kiện

Ví dụ lấy:

- Đơn PAID có tổng tiền từ một triệu trở lên; **hoặc**
- Đơn NEW được tạo trong ngày hiện tại.

~~~java
Predicate paidHighValue = cb.and(
    cb.equal(root.get("status"), OrderStatus.PAID),
    cb.greaterThanOrEqualTo(
        root.get("totalAmount"),
        new BigDecimal("1000000.00")
    )
);

Predicate newToday = cb.and(
    cb.equal(root.get("status"), OrderStatus.NEW),
    cb.greaterThanOrEqualTo(root.get("createdAt"), dayStart),
    cb.lessThan(root.get("createdAt"), nextDayStart)
);

cq.where(cb.or(paidHighValue, newToday));
~~~

Tương đương:

~~~text
(PAID AND total >= 1_000_000)
OR
(NEW AND createdAt >= dayStart AND createdAt < nextDayStart)
~~~

Đây là trường hợp Criteria có lợi khi các nhóm logic được bật/tắt hoặc lồng nhau theo cấu hình ứng dụng.

## 9. Lọc khoảng số và khoảng thời gian

Một yêu cầu phổ biến:

> Tổng tiền từ min tới max, thời gian tạo từ from tới to.

### 9.1. Khoảng số

~~~java
if (filter.minTotal() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            root.get("totalAmount"),
            filter.minTotal()
        )
    );
}

if (filter.maxTotal() != null) {
    predicates.add(
        cb.lessThanOrEqualTo(
            root.get("totalAmount"),
            filter.maxTotal()
        )
    );
}
~~~

Nếu cả hai có mặt, cần xác thực:

~~~java
if (minTotal != null && maxTotal != null
        && minTotal.compareTo(maxTotal) > 0) {
    throw new IllegalArgumentException(
        "minTotal must be <= maxTotal"
    );
}
~~~

Không nên silently swap min/max vì điều đó có thể che lỗi nhập liệu hoặc thay ý định người dùng.

### 9.2. Khoảng thời gian nửa mở

Một cách dễ quản lý:

~~~java
if (filter.createdFromInclusive() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            root.get("createdAt"),
            filter.createdFromInclusive()
        )
    );
}

if (filter.createdToExclusive() != null) {
    predicates.add(
        cb.lessThan(
            root.get("createdAt"),
            filter.createdToExclusive()
        )
    );
}
~~~

Bộ lọc:

~~~text
createdAt >= 2026-01-01T00:00:00Z
createdAt <  2026-02-01T00:00:00Z
~~~

chọn đúng các thời điểm trong tháng 1 theo UTC. Khoảng nửa mở `[from, to)` tránh phải tự tạo “23:59:59.999999” và tránh phụ thuộc độ chính xác của cột timestamp.

### 9.3. Ngày local và múi giờ

Nếu UI gửi `2026-01-01` theo múi giờ doanh nghiệp, service phải chuyển ngày local thành `Instant` thích hợp rồi mới truyền vào Criteria.

Ví dụ ý tưởng:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = LocalDate.of(2026, 1, 1)
    .atStartOfDay(businessZone)
    .toInstant();

Instant toExclusive = LocalDate.of(2026, 2, 1)
    .atStartOfDay(businessZone)
    .toInstant();
~~~

Không dùng trực tiếp ngày local như thể nó luôn tương ứng 00:00 UTC. Quy tắc timezone phải thuộc hợp đồng dữ liệu/API, không để repository Criteria tự đoán.

## 10. Tìm kiếm LIKE động và vấn đề ký tự đại diện

Ví dụ người dùng nhập từ khóa và muốn tìm trong mã đơn hoặc tên khách hàng.

~~~java
String keyword =
    filter.keyword().trim().toLowerCase(Locale.ROOT);

String pattern = "%" + keyword + "%";

Predicate matched = cb.or(
    cb.like(cb.lower(root.get("orderNumber")), pattern),
    cb.like(cb.lower(customerJoin.get("name")), pattern)
);
~~~

Đây là dạng cơ bản. Nhưng `%` và `_` có ý nghĩa đặc biệt trong SQL LIKE:

- `%` khớp chuỗi bất kỳ.
- `_` khớp đúng một ký tự.

Nếu người dùng gõ `10%` và mong tìm **dấu % thật**, đoạn code trên sẽ vô tình xem nó là wildcard.

### 10.1. Escape wildcard nếu nghiệp vụ tìm chuỗi literal

Có thể dùng escape character:

~~~java
private static String escapeLike(String input) {
    return input
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
~~~

Rồi:

~~~java
String normalized =
    filter.keyword().trim().toLowerCase(Locale.ROOT);

String pattern = "%" + escapeLike(normalized) + "%";

Predicate matchesOrder = cb.like(
    cb.lower(root.get("orderNumber")),
    pattern,
    '\\'
);
~~~

`CriteriaBuilder.like` có overload nhận ký tự escape. Dấu backslash trong ví dụ là lựa chọn minh họa; database/driver/provider phải chuyển cách escape phù hợp. Nếu provider/dialect có hạn chế, kiểm chứng bằng integration test với input chứa `%`, `_` và `\`.

### 10.2. LIKE và SQL injection không hoàn toàn là một vấn đề

Khi Criteria dùng giá trị đầu vào như operand biểu thức:

~~~java
cb.equal(root.get("status"), userStatus)
~~~

provider có cơ chế parameter binding phù hợp, tránh phải ghép trực tiếp input vào cú pháp JPQL. Nhưng **LIKE wildcard** là vấn đề semantics: người dùng có thể làm điều kiện khớp rộng hơn nếu ứng dụng không escape.

Đồng thời, Criteria **không tự bảo vệ** những phần mà ứng dụng ghép thủ công vào JPQL/native SQL hoặc chọn path/sort expression từ tên do client gửi mà không validate.

### 10.3. Hiệu năng của tìm kiếm không có tiền tố cố định

Điều kiện:

~~~sql
LOWER(name) LIKE '%abc%'
~~~

khó tận dụng một số loại B-tree index thông thường. Nếu dữ liệu lớn, có thể cần search index, full-text search hoặc chức năng DB-specific. Criteria giúp **xây dựng biểu thức**, không tự giải quyết kế hoạch truy vấn.

## 11. Lọc theo danh sách bằng IN

Yêu cầu:

> Tìm đơn hàng thuộc một trong các trạng thái NEW hoặc PAID.

~~~java
List<OrderStatus> statuses =
    List.of(OrderStatus.NEW, OrderStatus.PAID);

Predicate statusFilter =
    root.get("status").in(statuses);

cq.where(statusFilter);
~~~

Tương đương JPQL:

~~~sql
WHERE o.status IN (:statuses)
~~~

### 11.1. Trường hợp danh sách rỗng

Không nên giả định:

~~~java
root.get("status").in(Collections.emptyList())
~~~

sẽ được mọi provider chuyển thành SQL hợp lệ theo cùng cách. Một số DB không chấp nhận `IN ()`.

Hãy định nghĩa semantics:

- Nếu list vắng mặt/null nghĩa là không lọc → không thêm Predicate.
- Nếu list rỗng nghĩa là không có kết quả nào → dùng `cb.disjunction()` hoặc trả danh sách rỗng theo cách nghiệp vụ cho phép.
- Nếu list rỗng là input không hợp lệ → trả validation error.

Ví dụ:

~~~java
if (filter.statuses() != null) {
    if (filter.statuses().isEmpty()) {
        predicates.add(cb.disjunction());
    } else {
        predicates.add(
            root.get("status").in(filter.statuses())
        );
    }
}
~~~

Đoạn này giả định một DTO khác có `statuses()` là collection; record dùng xuyên suốt bài chỉ có một `status()`. Đây là ví dụ mở rộng cách thêm bộ lọc đa giá trị.

### 11.2. IN cực lớn không phải lúc nào tốt

Nếu client gửi hàng chục nghìn ID, Criteria có thể sinh một câu SQL chứa quá nhiều parameter, vượt giới hạn provider/driver/DB hoặc tạo query plan kém. Có thể cần:

- Giới hạn kích thước list.
- Chia batch theo nghiệp vụ.
- Sử dụng bảng tạm/bảng tham chiếu.
- JOIN vào bảng lưu filter.
- Native SQL hoặc cơ chế vendor-specific khi phù hợp.

Đừng coi việc Criteria có thể tạo Predicate IN là bảo đảm query luôn hiệu quả.

## 12. Khi cần JOIN động

Nếu lọc theo một thuộc tính trên entity liên quan, có thể thêm JOIN khi bộ lọc xuất hiện.

Ví dụ tìm theo tên Customer:

~~~java
if (filter.keyword() != null
        && !filter.keyword().isBlank()) {

    Join<PurchaseOrder, Customer> customer =
        root.join("customer", JoinType.INNER);

    String pattern =
        "%" + filter.keyword().trim().toLowerCase(Locale.ROOT) + "%";

    predicates.add(
        cb.like(
            cb.lower(customer.get("name")),
            pattern
        )
    );
}
~~~

JOIN chỉ cần được tạo khi điều kiện liên quan tới Customer. Với quan hệ bắt buộc từ Order sang Customer, INNER JOIN thường phù hợp.

### 12.1. Chọn INNER hay LEFT JOIN

- **INNER JOIN:** chỉ giữ các Order có row Customer khớp liên kết.
- **LEFT JOIN:** giữ Order ngay cả khi không có Customer tương ứng, nếu mapping/điều kiện cho phép.

Nếu Customer là optional association nhưng bộ lọc chỉ khớp tên Customer, INNER JOIN có thể đúng vì muốn loại Order không có Customer. Nếu query cần **trả cả Order không có Customer** và có thêm logic OR, LEFT JOIN có thể cần thiết.

Ví dụ:

~~~java
Join<PurchaseOrder, Customer> customer =
    root.join("customer", JoinType.LEFT);
~~~

Nhưng đặt điều kiện:

~~~java
cb.equal(customer.get("name"), "A")
~~~

ở WHERE có thể loại các hàng không có Customer vì SQL NULL semantics. Vì vậy **LEFT JOIN không tự bảo đảm luôn giữ row gốc** nếu WHERE hạn chế cột bên phải.

### 12.2. Tránh tạo cùng một JOIN quá nhiều lần

Nếu nhiều filter cùng cần Customer:

~~~java
root.join("customer", JoinType.INNER);
root.join("customer", JoinType.INNER);
~~~

không nên mặc định provider tự gộp mọi JOIN giống nhau tối ưu. Có thể quản lý reference:

~~~java
Join<PurchaseOrder, Customer> customer =
    root.join("customer", JoinType.INNER);
~~~

rồi dùng cho các điều kiện, projection hoặc sắp xếp.

Một predicate builder lớn có thể cần một đối tượng **query context** giữ các join đã tạo, nhưng chỉ thêm mức trừu tượng ấy khi nó thực sự giảm trùng lặp.

### 12.3. JOIN không phải FETCH JOIN

~~~java
root.join("customer", JoinType.INNER);
~~~

là join để lọc/đọc dữ liệu liên quan. Nó **không đồng nghĩa** Customer đã được eager fetch để sử dụng trên tất cả entity trả về.

Nếu cần fetch:

~~~java
root.fetch("customer", JoinType.INNER);
~~~

nhưng fetch join có ràng buộc riêng, nhất là khi truy vấn COUNT hoặc pagination. Không tự động chuyển mọi join lọc thành fetch join.

## 13. Bộ lọc qua collection: JOIN và bản ghi trùng lặp

Tình huống:

> Tìm các đơn hàng có ít nhất một dòng mang Product #17.

Một cách trực tiếp:

~~~java
Join<PurchaseOrder, OrderLine> line =
    root.join("lines", JoinType.INNER);

predicates.add(
    cb.equal(line.get("product").get("id"), 17L)
);
~~~

Vấn đề: một PurchaseOrder có thể có nhiều OrderLine khớp điều kiện. SQL JOIN nhân row Order theo số dòng tương ứng.

Ví dụ:

~~~text
Order 10 có 2 OrderLine đều trỏ Product 17

SQL JOIN có thể trả:
  Order 10 + Line 101
  Order 10 + Line 102
~~~

Trong một số ngữ cảnh, kết quả root entity có thể xuất hiện trùng hoặc cần distinct. Nếu truy vấn phân trang, nhân bản row càng dễ gây kết quả không như kỳ vọng.

### 13.1. Dùng DISTINCT khi thật sự JOIN to-many

~~~java
cq.select(root).distinct(true);
~~~

Đây là yêu cầu loại trùng entity root theo kết quả query. Nhưng DISTINCT có thể làm SQL/DB xử lý tốn chi phí hơn, nhất là khi còn ORDER BY, paging hoặc nhiều collection.

### 13.2. COUNT khi có JOIN to-many

Nếu dùng:

~~~java
countQuery.select(cb.count(countRoot));
~~~

sau JOIN to-many, mỗi Order có thể bị đếm nhiều lần.

Cần xem:

~~~java
countQuery.select(cb.countDistinct(countRoot));
~~~

khi logic query là đếm **các Order duy nhất** và có join nhân bản. Tuy nhiên COUNT DISTINCT có chi phí, nên đôi khi thiết kế bộ lọc bằng EXISTS thay vì JOIN còn tự nhiên hơn.

## 14. Dùng EXISTS khi chỉ cần biết “có ít nhất một con”

Với bộ lọc Product xuất hiện trong OrderLine, ứng dụng chỉ muốn biết **có ít nhất một dòng thỏa điều kiện**, chứ không cần lấy từng dòng.

Một subquery EXISTS phù hợp:

~~~java
Subquery<Integer> subquery =
    cq.subquery(Integer.class);

Root<OrderLine> line =
    subquery.from(OrderLine.class);

subquery.select(cb.literal(1));

subquery.where(
    cb.equal(line.get("order"), root),
    cb.equal(line.get("product").get("id"), productId)
);

Predicate hasProduct =
    cb.exists(subquery);

predicates.add(hasProduct);
~~~

SQL ý tưởng:

~~~sql
SELECT o.*
FROM purchase_order o
WHERE EXISTS (
    SELECT 1
    FROM order_line l
    WHERE l.order_id = o.id
      AND l.product_id = ?
);
~~~

**Ưu điểm logic:** EXISTS không nhân bản row Order ở query ngoài; mỗi Order xuất hiện một lần theo root selection nếu không có join to-many khác.

### 14.1. EXISTS phù hợp với điều kiện phụ thuộc parent

Dùng EXISTS khi:

- “Có ít nhất một dòng hàng với Product X”.
- “Có ít nhất một thanh toán thành công”.
- “Có ít nhất một đăng ký còn hiệu lực”.
- “Có ít nhất một dòng vi phạm một điều kiện”.

Dùng NOT EXISTS khi:

- “Không có dòng hàng nào”.
- “Chưa có thanh toán thành công”.
- “Không có bản ghi con đang active”.

~~~java
Predicate noMatchingLine =
    cb.not(cb.exists(subquery));
~~~

### 14.2. EXISTS khác JOIN FETCH

EXISTS chỉ kiểm tra sự tồn tại. Nó không yêu cầu provider tải collection `lines` của từng Order. Nếu UI thật sự cần nội dung các dòng, cần fetch plan hoặc truy vấn riêng.

### 14.3. Không phải EXISTS luôn nhanh hơn JOIN

Query optimizer của DB có thể chuyển cả hai thành semi-join hoặc một kế hoạch tương đương. Hiệu năng thực sự phụ thuộc index, số row và thống kê dữ liệu. Chọn EXISTS trước tiên vì **ngữ nghĩa và tránh nhân bản root**, sau đó kiểm chứng SQL plan.

## 15. Lọc collection rỗng hoặc không rỗng

CriteriaBuilder có các toán tử trên collection:

~~~java
Predicate hasNoLines =
    cb.isEmpty(root.get("lines"));
~~~

~~~java
Predicate hasAtLeastOneLine =
    cb.isNotEmpty(root.get("lines"));
~~~

Ví dụ:

~~~java
if (Boolean.TRUE.equals(filter.hasLines())) {
    predicates.add(
        cb.isNotEmpty(root.get("lines"))
    );
} else if (Boolean.FALSE.equals(filter.hasLines())) {
    predicates.add(
        cb.isEmpty(root.get("lines"))
    );
}
~~~

Điểm quan trọng:

- `hasLines = null`: không lọc.
- `hasLines = true`: chỉ Order có ít nhất một Line.
- `hasLines = false`: chỉ Order không có Line.

Đây là ví dụ điển hình vì một boolean nullable biểu diễn ba trạng thái. Không được viết:

~~~java
if (filter.hasLines()) {
    ...
}
~~~

vì có thể gây `NullPointerException` khi không cung cấp filter.

### 15.1. isEmpty và EXISTS

Về mặt logic, `isNotEmpty(root.get("lines"))` gần với một EXISTS trên OrderLine. Provider quyết định SQL thực thi. Nếu cần điều kiện cụ thể trên từng dòng (ví dụ Product ID, số lượng tối thiểu), EXISTS subquery tường minh linh hoạt hơn.

## 16. Sắp xếp động an toàn

Màn hình cho phép sắp xếp theo:

- Ngày tạo.
- Tổng tiền.
- Mã đơn.

Không nên nhận tên field bất kỳ từ client rồi chuyển trực tiếp vào:

~~~java
root.get(userSuppliedSortField)
~~~

Về bảo mật và tính ổn định API, nên dùng một whitelist:

~~~java
public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    ORDER_NUMBER
}
~~~

Ánh xạ enum vào path được phép:

~~~java
private static Path<?> selectSortPath(
        Root<PurchaseOrder> root,
        OrderSort sort) {

    OrderSort effective =
        sort == null ? OrderSort.CREATED_AT : sort;

    return switch (effective) {
        case CREATED_AT -> root.get("createdAt");
        case TOTAL_AMOUNT -> root.get("totalAmount");
        case ORDER_NUMBER -> root.get("orderNumber");
    };
}
~~~

Sau đó:

~~~java
Path<?> sortPath = selectSortPath(root, filter.sort());

Order primaryOrder = filter.descending()
    ? cb.desc(sortPath)
    : cb.asc(sortPath);

cq.orderBy(
    primaryOrder,
    cb.desc(root.get("id"))
);
~~~

### 16.1. Vì sao cần tie-breaker ổn định?

Nếu hai đơn cùng `createdAt`, chỉ:

~~~sql
ORDER BY created_at DESC
~~~

không xác định thứ tự giữa hai row có timestamp bằng nhau. Khi phân trang offset, một Order có thể xuất hiện lại hoặc bị bỏ qua trong những tình huống dữ liệu/plan thay đổi.

Thêm khóa ổn định:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

giúp thứ tự có tính xác định hơn khi dữ liệu không thay đổi. Tuy nhiên, trong hệ thống có insert/update đồng thời, offset pagination vẫn có thể dịch vị trí giữa các trang; keyset pagination có thể phù hợp hơn với feed lớn.

### 16.2. Không truyền nguyên chuỗi ORDER BY từ client

Một query builder đúng không cho phép:

~~~java
String orderBy = request.getSortExpression();
// Ghép trực tiếp orderBy vào SQL/JPQL.
~~~

Client chỉ chọn một giá trị enum đã định nghĩa. Repository chuyển enum thành path Criteria; hướng tăng/giảm cũng là boolean hoặc enum được kiểm soát. Nhờ vậy API không lộ trực tiếp tên field entity hoặc một biểu thức SQL tùy ý.

### 16.3. Sort theo relation cần JOIN thích hợp

Nếu cho phép sắp xếp theo Customer.name, repository có thể cần một JOIN to-one:

~~~java
Join<PurchaseOrder, Customer> customer =
    root.join("customer", JoinType.INNER);

cq.orderBy(
    cb.asc(customer.get("name")),
    cb.asc(root.get("id"))
);
~~~

Không nên mặc định sắp xếp theo to-many collection như `lines.quantity` sẽ tạo thứ tự duy nhất cho mỗi Order; cần xác định aggregate/criteria phù hợp.

## 17. Phân trang với Criteria

Sau khi có `CriteriaQuery`, sử dụng API chuẩn của `TypedQuery`:

~~~java
TypedQuery<PurchaseOrder> query =
    em.createQuery(cq);

query.setFirstResult(page * size);
query.setMaxResults(size);

List<PurchaseOrder> orders =
    query.getResultList();
~~~

`page` ở đây là trang bắt đầu từ 0, `size` là số Order mỗi trang.

### 17.1. Xác thực trang và size

Không nên nhận mọi giá trị:

~~~java
if (filter.page() < 0) {
    throw new IllegalArgumentException("Page must be >= 0");
}

if (filter.size() < 1 || filter.size() > 100) {
    throw new IllegalArgumentException(
        "Page size must be in range 1..100"
    );
}
~~~

Giới hạn kích thước trang giúp ngăn một request thông thường tải quá nhiều entity vào memory. Ngưỡng 100 chỉ là ví dụ; sản phẩm thật có thể chọn số khác.

### 17.2. Tránh overflow khi tính offset

~~~java
int offset = Math.multiplyExact(
    filter.page(),
    filter.size()
);

query.setFirstResult(offset);
query.setMaxResults(filter.size());
~~~

`Math.multiplyExact` ném exception nếu phép nhân vượt phạm vi Integer. Có thể xử lý thành validation error ở tầng API. Không để một offset âm vì overflow đi thẳng vào Query.

### 17.3. Pageable của Spring không phải API Criteria chuẩn

Trong Spring Data, có `Pageable` và `Page<T>`. Chúng tiện lợi nhưng không thuộc `jakarta.persistence.criteria`. Nếu viết JPA thuần, phải tự gọi `setFirstResult`/`setMaxResults` và tạo count query khi cần tổng số.

## 18. Query COUNT riêng cho màn hình phân trang

Một trang kết quả thường cần cả:

- Danh sách tối đa 20 Order.
- Tổng số Order phù hợp bộ lọc để tính tổng số trang.

Query lấy dữ liệu:

~~~java
CriteriaQuery<PurchaseOrder> dataQuery =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> dataRoot =
    dataQuery.from(PurchaseOrder.class);

dataQuery.select(dataRoot);
// Build predicates, sort, execute with paging.
~~~

Query đếm:

~~~java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

Root<PurchaseOrder> countRoot =
    countQuery.from(PurchaseOrder.class);

countQuery.select(cb.count(countRoot));
// Build same logical filter, execute without paging.
~~~

**Không thể tùy tiện tái sử dụng một `Predicate` đã tạo từ `dataRoot` vào `countQuery`**, vì predicate/path gắn với cây truy vấn và root cụ thể.

### 18.1. Tái sử dụng *logic tạo predicate*, không phải Predicate instance

Một cách tổ chức:

~~~java
private Predicate buildWhere(
        CriteriaBuilder cb,
        CriteriaQuery<?> cq,
        Root<PurchaseOrder> root,
        OrderSearchFilter filter) {

    List<Predicate> predicates = new ArrayList<>();

    // Tạo predicate từ root và cq được truyền vào.

    return cb.and(predicates.toArray(Predicate[]::new));
}
~~~

Khi build data query:

~~~java
dataQuery.where(
    buildWhere(cb, dataQuery, dataRoot, filter)
);
~~~

Khi build count query:

~~~java
countQuery.where(
    buildWhere(cb, countQuery, countRoot, filter)
);
~~~

Mỗi lần gọi tạo **các đối tượng Criteria mới gắn với query/root tương ứng**. Đây là thiết kế dễ tái sử dụng và tránh nhiều lỗi khi cố copy expression tree.

### 18.2. Count query không nên chứa fetch join

Nếu data query cần:

~~~java
dataRoot.fetch("customer", JoinType.INNER);
~~~

đừng tự động thực hiện y hệt trên count query. COUNT chỉ cần đếm Order; fetch association vào query trả về Long thường không hợp lý, và một số provider sẽ báo lỗi vì fetch owner không có trong selection.

Tách:

- **Phần filter chung**.
- **Phần selection/fetch/sort/paging cho data query**.
- **Phần count() hoặc countDistinct() cho count query**.

Đây là nguyên tắc rất quan trọng khi thiết kế predicate builder.

### 18.3. Count có JOIN to-many

Nếu filter dùng JOIN tới `lines`, có thể phải:

~~~java
countQuery.select(cb.countDistinct(countRoot));
~~~

để đếm Order duy nhất. Nếu filter dùng EXISTS thay JOIN to-many, query ngoài thường không bị nhân bản row và có thể dùng `cb.count(countRoot)`.

## 19. Ví dụ repository hoàn chỉnh: Builder có thể tái sử dụng

Phần này ghép các kỹ thuật thành một repository JPA thuần.

### 19.1. Result wrapper

~~~java
package com.example.shop.search;

import java.util.List;

public record SearchPage<T>(
    List<T> items,
    long totalElements,
    int page,
    int size
) {}
~~~

Đây là DTO trả kết quả ở tầng ứng dụng, không phải interface của JPA.

### 19.2. Repository

~~~java
package com.example.shop.search;

import com.example.shop.domain.Customer;
import com.example.shop.domain.OrderLine;
import com.example.shop.domain.PurchaseOrder;

import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.Order;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import jakarta.persistence.criteria.Subquery;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class OrderSearchRepository {

    private final EntityManager em;

    public OrderSearchRepository(EntityManager em) {
        this.em = em;
    }

    public SearchPage<PurchaseOrder> search(
            OrderSearchFilter filter) {

        validate(filter);

        CriteriaBuilder cb = em.getCriteriaBuilder();

        // 1. Query lấy dữ liệu.
        CriteriaQuery<PurchaseOrder> dataCq =
            cb.createQuery(PurchaseOrder.class);

        Root<PurchaseOrder> dataRoot =
            dataCq.from(PurchaseOrder.class);

        dataCq.select(dataRoot);
        dataCq.where(
            buildWhere(cb, dataCq, dataRoot, filter)
        );

        Path<?> sortPath =
            selectSortPath(dataRoot, filter.sort());

        Order primaryOrder = filter.descending()
            ? cb.desc(sortPath)
            : cb.asc(sortPath);

        dataCq.orderBy(
            primaryOrder,
            cb.desc(dataRoot.get("id"))
        );

        TypedQuery<PurchaseOrder> dataQuery =
            em.createQuery(dataCq);

        int offset = Math.multiplyExact(
            filter.page(), filter.size()
        );

        dataQuery.setFirstResult(offset);
        dataQuery.setMaxResults(filter.size());

        List<PurchaseOrder> items =
            dataQuery.getResultList();

        // 2. Query đếm, tạo Root/Predicate riêng.
        CriteriaQuery<Long> countCq =
            cb.createQuery(Long.class);

        Root<PurchaseOrder> countRoot =
            countCq.from(PurchaseOrder.class);

        countCq.select(cb.count(countRoot));
        countCq.where(
            buildWhere(cb, countCq, countRoot, filter)
        );

        long totalElements =
            em.createQuery(countCq).getSingleResult();

        return new SearchPage<>(
            items,
            totalElements,
            filter.page(),
            filter.size()
        );
    }

    private static Predicate buildWhere(
            CriteriaBuilder cb,
            CriteriaQuery<?> cq,
            Root<PurchaseOrder> root,
            OrderSearchFilter filter) {

        List<Predicate> parts = new ArrayList<>();

        if (filter.status() != null) {
            parts.add(
                cb.equal(root.get("status"), filter.status())
            );
        }

        if (filter.customerId() != null) {
            parts.add(
                cb.equal(
                    root.get("customer").get("id"),
                    filter.customerId()
                )
            );
        }

        if (filter.createdFromInclusive() != null) {
            parts.add(
                cb.greaterThanOrEqualTo(
                    root.get("createdAt"),
                    filter.createdFromInclusive()
                )
            );
        }

        if (filter.createdToExclusive() != null) {
            parts.add(
                cb.lessThan(
                    root.get("createdAt"),
                    filter.createdToExclusive()
                )
            );
        }

        if (filter.minTotal() != null) {
            parts.add(
                cb.greaterThanOrEqualTo(
                    root.get("totalAmount"),
                    filter.minTotal()
                )
            );
        }

        if (filter.maxTotal() != null) {
            parts.add(
                cb.lessThanOrEqualTo(
                    root.get("totalAmount"),
                    filter.maxTotal()
                )
            );
        }

        if (filter.keyword() != null
                && !filter.keyword().isBlank()) {

            Join<PurchaseOrder, Customer> customer =
                root.join("customer", JoinType.INNER);

            String normalized = filter.keyword()
                .trim()
                .toLowerCase(Locale.ROOT);

            String pattern =
                "%" + escapeLike(normalized) + "%";

            Path<String> orderNumber =
                root.get("orderNumber");

            Path<String> customerName =
                customer.get("name");

            Predicate matchesOrderNumber = cb.like(
                cb.lower(orderNumber),
                pattern,
                '\\'
            );

            Predicate matchesCustomerName = cb.like(
                cb.lower(customerName),
                pattern,
                '\\'
            );

            parts.add(
                cb.or(
                    matchesOrderNumber,
                    matchesCustomerName
                )
            );
        }

        if (filter.productId() != null) {
            Subquery<Integer> sq =
                cq.subquery(Integer.class);

            Root<OrderLine> line =
                sq.from(OrderLine.class);

            sq.select(cb.literal(1));
            sq.where(
                cb.equal(line.get("order"), root),
                cb.equal(
                    line.get("product").get("id"),
                    filter.productId()
                )
            );

            parts.add(cb.exists(sq));
        }

        if (Boolean.TRUE.equals(filter.hasLines())) {
            parts.add(
                cb.isNotEmpty(root.get("lines"))
            );
        } else if (Boolean.FALSE.equals(filter.hasLines())) {
            parts.add(
                cb.isEmpty(root.get("lines"))
            );
        }

        return cb.and(parts.toArray(Predicate[]::new));
    }

    private static Path<?> selectSortPath(
            Root<PurchaseOrder> root,
            OrderSort sort) {

        OrderSort effective = sort == null
            ? OrderSort.CREATED_AT
            : sort;

        return switch (effective) {
            case CREATED_AT -> root.get("createdAt");
            case TOTAL_AMOUNT -> root.get("totalAmount");
            case ORDER_NUMBER -> root.get("orderNumber");
        };
    }

    private static String escapeLike(String value) {
        return value
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_");
    }

    private static void validate(OrderSearchFilter filter) {
        if (filter == null) {
            throw new IllegalArgumentException(
                "Search filter is required"
            );
        }

        if (filter.page() < 0) {
            throw new IllegalArgumentException(
                "page must be non-negative"
            );
        }

        if (filter.size() < 1 || filter.size() > 100) {
            throw new IllegalArgumentException(
                "size must be between 1 and 100"
            );
        }

        if (filter.minTotal() != null
                && filter.maxTotal() != null
                && filter.minTotal().compareTo(
                    filter.maxTotal()
                ) > 0) {
            throw new IllegalArgumentException(
                "minTotal is greater than maxTotal"
            );
        }

        if (filter.createdFromInclusive() != null
                && filter.createdToExclusive() != null
                && !filter.createdFromInclusive().isBefore(
                    filter.createdToExclusive()
                )) {
            throw new IllegalArgumentException(
                "createdFrom must precede createdTo"
            );
        }

        // Kiểm tra overflow offset trước khi query.
        Math.multiplyExact(filter.page(), filter.size());
    }
}
~~~

### 19.3. Ý nghĩa của thiết kế

Repository có ba phần tách bạch:

**Phần 1 — Data query:** tạo `CriteriaQuery<PurchaseOrder>`, áp dụng filter, sort và pagination.

**Phần 2 — Count query:** tạo `CriteriaQuery<Long>` mới, áp dụng cùng logic filter, không fetch và không paginate.

**Phần 3 — Predicate builder:** nhận `CriteriaBuilder`, query và root hiện tại, rồi tạo toàn bộ `Predicate` tương ứng các filter có mặt.

Cách chia này giúp:

- Tránh copy nhiều khối điều kiện giữa data/count query.
- Tránh tái sử dụng Predicate từ root khác.
- Đưa điều kiện mới vào một điểm chung.
- Không cần viết câu JPQL riêng cho mỗi tổ hợp.
- Hạn chế duplicate root bằng EXISTS khi lọc theo OrderLine.
- Đảm bảo sort chỉ dùng các field đã whitelist.
- Bảo đảm query có ordering ổn định bằng ID làm tie-breaker.

### 19.4. Giới hạn của ví dụ

Đây là repository minh họa cách xây truy vấn. Hệ thống production còn cần:

- Phân quyền dữ liệu theo tenant/customer.
- Giới hạn tổng số bản ghi khi user không có filter.
- Cấu hình transaction và EntityManager lifecycle.
- DTO projection thay vì trả entity ở API.
- Index cho các điều kiện thường dùng.
- Cơ chế tìm kiếm full-text nếu keyword phức tạp.
- Kiểm thử các tổ hợp filter và query plan.
- Chính sách pagination nhất quán khi dữ liệu thay đổi đồng thời.

Không xem một query builder đúng cú pháp là toàn bộ yêu cầu để triển khai một endpoint tìm kiếm an toàn.

## 20. Mỗi điều kiện cần có một semantics rõ ràng

Khi thêm filter mới, trước hết viết câu nghiệp vụ.

Ví dụ:

> “Lọc những đơn hàng có Product X, và chỉ lấy các đơn chưa bị hủy.”

Điều kiện:

~~~text
EXISTS line with product X
AND status <> CANCELLED
~~~

Một số người có thể viết:

~~~java
if (productId != null) {
    // Thêm JOIN OrderLine.
}

if (includeCancelled == false) {
    // Thêm status != CANCELLED.
}
~~~

Nhưng cần hỏi:

- Nếu Product X không tồn tại thì trả rỗng hay lỗi?
- Có tính cả OrderLine đã bị hủy/soft-deleted không?
- Nếu Order CANCELLED nhưng Line vẫn còn, có bị loại không?
- Nếu một Order có nhiều Line Product X, có trả trùng không?
- Nếu không nhập Product X, có vẫn join lines không?
- Nếu client không gửi includeCancelled, mặc định là gì?

Criteria làm cho việc **lắp ráp biểu thức** dễ hơn, nhưng không tự định nghĩa các quy tắc này.

### 20.1. Security predicate không được tùy chọn

Một endpoint đa tenant thường bắt buộc có:

~~~java
parts.add(
    cb.equal(root.get("tenantId"), currentTenantId)
);
~~~

dù request không gửi tenantId. Đây là predicate bắt buộc lấy từ identity/authorization của server, không phải filter tùy chọn mà client có thể xóa.

Không thiết kế:

~~~java
if (filter.tenantId() != null) {
    // Chỉ kiểm tra tenant khi client tự gửi!
}
~~~

Điều đó có thể làm lộ dữ liệu tenant khác khi request bỏ filter.

Cần phân biệt:

- **Predicate bảo vệ dữ liệu:** luôn có, lấy từ server-side authorization.
- **Predicate tùy chọn nghiệp vụ:** thêm theo input đã validate.
- **Predicate tối ưu:** hỗ trợ query plan nhưng không thay đổi phạm vi dữ liệu được phép thấy.

## 21. Criteria API và type safety: Có lợi nhưng không tuyệt đối

Một số người nói:

> “Criteria hoàn toàn type-safe vì nó là API Java.”

Điều này chỉ đúng khi sử dụng đúng kiểu và tránh chuỗi tên field.

Ví dụ:

~~~java
root.get("createdAt");
~~~

vẫn chứa một String. Nếu rename field `createdAt` thành `createdOn` mà không sửa String, Java compiler có thể không phát hiện.

### 21.1. Static metamodel

JPA hỗ trợ một mô hình metamodel để truy cập thuộc tính qua những member được sinh tại compile-time.

Ví dụ entity:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    private Instant createdAt;

    private BigDecimal totalAmount;
}
~~~

Metamodel sinh ra có thể có dạng ý tưởng:

~~~java
@StaticMetamodel(PurchaseOrder.class)
public abstract class PurchaseOrder_ {
    public static volatile SingularAttribute<
        PurchaseOrder, Long
    > id;

    public static volatile SingularAttribute<
        PurchaseOrder, Instant
    > createdAt;

    public static volatile SingularAttribute<
        PurchaseOrder, BigDecimal
    > totalAmount;
}
~~~

Code Criteria:

~~~java
Path<Instant> created =
    root.get(PurchaseOrder_.createdAt);

Predicate laterThan =
    cb.greaterThanOrEqualTo(created, from);
~~~

Nếu dùng annotation processor sinh metamodel đúng cách, đổi tên property có thể làm lỗi compile ở code tham chiếu tên cũ.

### 21.2. Đổi lại, build cần cấu hình processor

Tùy stack/provider, dự án có thể cần một annotation processor như Hibernate JPAModelGen hoặc công cụ tương đương để sinh các class metamodel.

Không tự viết metamodel bằng tay khi đã có generator phù hợp; cần đảm bảo:

- Processor dùng namespace Jakarta phù hợp.
- Generated source được đưa vào compile.
- IDE nhận đúng generated sources.
- Build CI chạy generator đồng nhất.
- Không trộn metamodel cũ `javax.persistence` với entity mới `jakarta.persistence`.

### 21.3. Metamodel không sửa mọi lỗi logic

Dù path compile được:

~~~java
cb.greaterThanOrEqualTo(root.get(
    PurchaseOrder_.totalAmount
), new BigDecimal("1000"))
~~~

ứng dụng vẫn có thể sai vì:

- Dùng `>=` khi nghiệp vụ yêu cầu `>`.
- Ghép OR ngoài AND sai vị trí.
- Dùng INNER JOIN làm mất các row optional.
- Đếm trùng khi JOIN to-many.
- Không áp dụng tenant predicate.
- Dùng sai timezone.

Type safety giúp giảm một nhóm lỗi, không thay thế kiểm thử ngữ nghĩa.

## 22. Tái sử dụng predicate bằng Specification trong Spring Data JPA

Nếu dự án dùng Spring Data JPA, `Specification<T>` là một abstraction phổ biến xây trên Criteria API.

Ví dụ:

~~~java
import org.springframework.data.jpa.domain.Specification;

public final class OrderSpecifications {

    private OrderSpecifications() {}

    public static Specification<PurchaseOrder> hasStatus(
            OrderStatus status) {

        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrder> createdFrom(
            Instant from) {

        return (root, query, cb) ->
            from == null
                ? cb.conjunction()
                : cb.greaterThanOrEqualTo(
                    root.get("createdAt"), from
                );
    }

    public static Specification<PurchaseOrder> minTotal(
            BigDecimal value) {

        return (root, query, cb) ->
            value == null
                ? cb.conjunction()
                : cb.greaterThanOrEqualTo(
                    root.get("totalAmount"), value
                );
    }
}
~~~

Cấu hình repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                JpaSpecificationExecutor<PurchaseOrder> {
}
~~~

Dùng:

~~~java
Specification<PurchaseOrder> spec =
    Specification.where(
        OrderSpecifications.hasStatus(filter.status())
    )
    .and(
        OrderSpecifications.createdFrom(
            filter.createdFromInclusive()
        )
    )
    .and(
        OrderSpecifications.minTotal(filter.minTotal())
    );

Page<PurchaseOrder> page =
    repository.findAll(spec, pageable);
~~~

**Lưu ý tương thích phiên bản:** một số phiên bản Spring Data mới thay đổi cách khuyến nghị dùng `Specification.where(...)`; có thể dùng API khởi tạo/composition hiện hành phù hợp version. Ví dụ diễn đạt mô hình, cần đối chiếu version thực tế.

### 22.1. Khi Specification có lợi

- Nhiều module cần bộ lọc tái sử dụng.
- Query search là tập các điều kiện AND/OR composable.
- Hệ thống đã dùng Spring Data repository.
- Cần tích hợp pageable/sort và count query do framework quản lý.
- Có test độc lập cho từng specification.

### 22.2. Khi Specification có thể gây khó

- Specification tùy tiện thêm fetch join vào count query.
- Một spec giả định join đã có, spec khác tạo join trùng.
- Các spec tự sửa `orderBy`, `distinct` hoặc selection và gây xung đột.
- Logic permission bị đặt thành spec tùy chọn rồi caller vô tình bỏ qua.
- Bộ lọc chứa nhiều subquery/correlation phức tạp mà abstraction che mất các ràng buộc.

Nếu query đã rất phức tạp, một repository Criteria builder rõ ràng có thể dễ hiểu hơn chuỗi specification lồng nhau dài.

### 22.3. Không coi Specification là JPA chuẩn

`Specification<T>` và `JpaSpecificationExecutor` là API **Spring Data JPA**. JPA chuẩn có `CriteriaBuilder`, `CriteriaQuery`, `Predicate` và các loại related. Trong ứng dụng không dùng Spring, có thể viết một interface predicate builder riêng hoặc dùng thư viện query DSL thích hợp.

## 23. Fetch plan động trong Criteria: Cẩn thận với COUNT và pagination

Một trang chi tiết có thể cần Customer:

~~~java
root.fetch("customer", JoinType.INNER);
~~~

Nhưng một trang danh sách phân trang có thể chỉ cần mã khách hàng hoặc tên. Nếu fetch cả collection:

~~~java
root.fetch("lines", JoinType.LEFT);
~~~

query có thể tạo nhiều row SQL cho một Order. Với `setFirstResult`/`setMaxResults`, việc phân trang theo root có thể trở nên khó hoặc provider phải xử lý trong bộ nhớ.

### 23.1. Không dùng fetch collection trực tiếp trong page query một cách mặc định

Ví dụ nguy hiểm:

~~~java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

root.fetch("lines", JoinType.LEFT);

cq.select(root);

TypedQuery<PurchaseOrder> query =
    em.createQuery(cq);

query.setFirstResult(0);
query.setMaxResults(20);
~~~

Nếu một Order có 100 Lines, SQL JOIN có 100 row cho riêng một Order. Cách provider xử lý pagination có thể không như kỳ vọng ở tầng root.

Một thiết kế thường ổn định hơn:

1. Query phân trang danh sách **ID** Order.
2. Query thứ hai tải đúng những Order trong page và các association cần thiết.
3. Sắp xếp kết quả theo thứ tự page đã xác định (không giả định IN giữ thứ tự).
4. Query COUNT riêng khi cần.

### 23.2. Tải to-one khác to-many

Fetch to-one như Customer thường không nhân bản số root theo cardinality 1:1 hoặc N:1. Fetch to-many như Lines có thể nhân bản row.

Điều này không có nghĩa fetch mọi to-one đều tốt; nhiều to-one có thể kéo theo join rộng, làm tăng payload và latency. Chỉ fetch theo use case.

### 23.3. Entity graph là một lựa chọn khác

Có thể dùng:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

TypedQuery<PurchaseOrder> query =
    em.createQuery(cq);

query.setHint("jakarta.persistence.loadgraph", graph);
~~~

Entity graph cho phép xác định fetch plan ngoài cấu trúc Criteria. Nhưng provider không cam kết đúng một SQL, và count query vẫn phải được thiết kế riêng.

## 24. CriteriaQuery hỗ trợ projection khi không cần cả entity

Một màn hình list chỉ cần:

- ID.
- Mã đơn.
- Tổng tiền.
- Trạng thái.

Không nhất thiết tải toàn bộ `PurchaseOrder` và association.

### 24.1. Dùng tuple

~~~java
CriteriaQuery<Tuple> cq =
    cb.createTupleQuery();

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

cq.multiselect(
    root.get("id").alias("id"),
    root.get("orderNumber").alias("orderNumber"),
    root.get("totalAmount").alias("totalAmount")
);

List<Tuple> rows =
    em.createQuery(cq).getResultList();

for (Tuple row : rows) {
    Long id = row.get("id", Long.class);
    String number =
        row.get("orderNumber", String.class);
    BigDecimal amount =
        row.get("totalAmount", BigDecimal.class);
}
~~~

### 24.2. Constructor projection

DTO:

~~~java
public record OrderSummary(
    Long id,
    String orderNumber,
    BigDecimal totalAmount
) {}
~~~

Criteria:

~~~java
CriteriaQuery<OrderSummary> cq =
    cb.createQuery(OrderSummary.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

cq.select(
    cb.construct(
        OrderSummary.class,
        root.get("id"),
        root.get("orderNumber"),
        root.get("totalAmount")
    )
);

List<OrderSummary> rows =
    em.createQuery(cq).getResultList();
~~~

`cb.construct` yêu cầu constructor có kiểu/số tham số tương thích. Một Java record có constructor canonical phù hợp như ví dụ.

### 24.3. Projection không cần entity graph

Khi query chỉ chọn vài cột scalar/DTO, fetch graph dành cho entity loading thường không mang lợi ích tương ứng. Chọn **projection** khi yêu cầu đọc là những trường cụ thể; dùng entity fetch khi cần xử lý managed entity.

### 24.4. Sort và filter vẫn dùng chung Criteria

Có thể tái sử dụng logic filter với query projection nếu helper nhận root/query tương ứng. Tuy nhiên không được giả định mọi predicate hoặc join phù hợp cho mọi selection; cần xây lại expression tree theo query mục tiêu.

## 25. Criteria với GROUP BY và HAVING động

Một use case khác:

> Báo cáo tổng số đơn theo Customer, có thể lọc theo trạng thái và chỉ lấy Customer có từ N đơn trở lên.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Tuple> cq =
    cb.createTupleQuery();

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

Path<Long> customerId =
    root.get("customer").get("id");

Expression<Long> orderCount =
    cb.count(root);

cq.multiselect(
    customerId.alias("customerId"),
    orderCount.alias("orderCount")
);

cq.groupBy(customerId);

if (status != null) {
    cq.where(
        cb.equal(root.get("status"), status)
    );
}

if (minimumOrders != null) {
    cq.having(
        cb.greaterThanOrEqualTo(
            orderCount,
            minimumOrders
        )
    );
}
~~~

`WHERE` lọc **row đầu vào trước nhóm**; `HAVING` lọc **nhóm sau aggregation**.

### 25.1. Criteria không biến báo cáo phức tạp thành đơn giản

Với grouping, CTE, window functions, rollups hoặc nhiều phép tính DB-specific, Criteria có thể dài và khó đọc hơn một câu SQL/named query được viết rõ ràng.

Nếu báo cáo cố định, JPQL hoặc native SQL chuyên biệt có thể tốt hơn. Lựa chọn Criteria khi **cấu trúc điều kiện/aggregation thực sự động**, không chỉ vì query dài.

### 25.2. COUNT trong GROUP BY khác COUNT tổng số bản ghi

`cb.count(root)` trong GROUP BY đếm số Order của từng nhóm Customer. Nó khác COUNT query dùng để tính tổng số Order khớp filter cho phân trang danh sách Order. Không dùng nhầm hai mục tiêu trong repository.

## 26. CriteriaUpdate và CriteriaDelete không phải biến thể của truy vấn SELECT thông thường

JPA cũng có bulk Criteria operations:

~~~java
CriteriaUpdate<PurchaseOrder> update =
    cb.createCriteriaUpdate(PurchaseOrder.class);

Root<PurchaseOrder> root =
    update.from(PurchaseOrder.class);

update.set("status", OrderStatus.CANCELLED);

update.where(
    cb.equal(root.get("status"), OrderStatus.NEW)
);

int changed =
    em.createQuery(update).executeUpdate();
~~~

Và:

~~~java
CriteriaDelete<PurchaseOrder> delete =
    cb.createCriteriaDelete(PurchaseOrder.class);

Root<PurchaseOrder> root =
    delete.from(PurchaseOrder.class);

delete.where(
    cb.lessThan(root.get("createdAt"), cutoff)
);

int deleted =
    em.createQuery(delete).executeUpdate();
~~~

Đây là **bulk DML**. Nó khác việc lặp từng managed entity rồi gọi setter/remove:

- Không tự cập nhật state của mọi entity đã managed trong persistence context.
- Có thể bỏ qua lifecycle callback/cascade theo cơ chế entity-level thông thường.
- Có thể không tự áp dụng optimistic locking như update managed entity.
- Vẫn bị ràng buộc FK/constraint tại DB.
- Cần transaction phù hợp.
- Sau bulk DML, persistence context có thể stale.

Vì vậy, **không nên tái sử dụng một cơ chế predicate builder SELECT rồi tùy tiện biến nó thành bulk DELETE** mà không xem semantics vòng đời dữ liệu.

## 27. Criteria không giải quyết mọi vấn đề SQL

Criteria API là cách mô tả query object-oriented; nó không tự tạo index, không tự sửa dữ liệu lệch schema và không đảm bảo query nhanh.

Ví dụ query:

~~~java
cb.like(
    cb.lower(root.get("orderNumber")),
    "%abc%"
)
~~~

có thể khó tận dụng index thông thường. Query:

~~~java
root.join("lines")
~~~

có thể tạo nhiều row và làm COUNT sai. Query:

~~~java
cq.orderBy(cb.desc(root.get("createdAt")))
~~~

không có tie-breaker có thể không ổn định khi phân trang.

Do đó một quy trình thực tế:

~~~text
Nghiệp vụ
   |
   v
Định nghĩa filter và semantics
   |
   v
Xây Criteria predicates/joins/projection
   |
   v
JPA provider dịch thành SQL
   |
   v
Kiểm tra SQL, EXPLAIN và index
   |
   v
Integration test và benchmark theo workload
~~~

**Độ đúng logic đứng trước hiệu năng; hiệu năng phải đo trên SQL/DB thật, không suy ra từ độ dài source Java.**

## 28. Khi nào nên dùng JPQL động bằng chuỗi thay vì Criteria?

Không phải mọi truy vấn có một vài điều kiện tùy chọn đều cần Criteria. Có thể viết JPQL với điều kiện tham số null:

~~~java
String jpql = """
    SELECT o
    FROM PurchaseOrder o
    WHERE (:status IS NULL OR o.status = :status)
      AND (:customerId IS NULL
           OR o.customer.id = :customerId)
    """;
~~~

Sau đó bind cả `status` và `customerId`. Cách này có thể rất gọn khi số filter ít.

Nhưng cũng có đánh đổi:

- Một câu OR lớn có thể khó tối ưu trong một số DB so với SQL chỉ chứa điều kiện thật sự.
- Kiểu null parameter có thể cần xử lý provider/driver cẩn thận.
- Khi thêm nhiều JOIN/subquery động, câu query khó đọc.
- Kết hợp nhiều nhóm OR tùy chọn dễ tạo nhầm lẫn.
- Tái sử dụng một số nhóm điều kiện giữa nhiều query khó khăn hơn.

**Không có quy tắc “luôn dùng Criteria nếu có filter tùy chọn”.** Với 1–3 filter đơn giản, một JPQL cố định có thể là lựa chọn dễ duy trì. Khi tổ hợp đa dạng, JOIN/EXISTS thay đổi và query builder được chia sẻ, Criteria trở nên đáng giá hơn.

### 28.1. Ghép chuỗi JPQL bằng if/else có phải luôn sai?

Không. Một số trường hợp có thể tạo JPQL an toàn khi:

- Phần cú pháp được xây từ các fragment cố định do server kiểm soát.
- Giá trị đầu vào luôn bind qua `setParameter`.
- Sort field được whitelist.
- Các tổ hợp filter được kiểm thử.
- Độ phức tạp vẫn thấp.

Nhưng khi code xuất hiện nhiều dấu cách, `WHERE 1=1`, nối AND/OR và string fragment khó kiểm soát, Criteria hoặc một query DSL chuyên dụng có thể giúp tạo cấu trúc rõ hơn.

### 28.2. Criteria không tự động loại bỏ lỗi injection nếu tự ghép SQL

Nếu repository vẫn nhận fragment từ client rồi đưa vào native SQL, dùng Criteria ở những đoạn khác không giúp truy vấn đó an toàn. Phải phân tách dữ liệu đầu vào và cú pháp, bind tham số và chỉ cho phép những biểu thức được định nghĩa.

## 29. Criteria và QueryDSL, jOOQ, Specification: Chọn mức trừu tượng phù hợp

Có nhiều công cụ cho truy vấn động:

| Công cụ | Đặc điểm chính | Phù hợp khi |
|---|---|---|
| JPQL | Chuỗi query hướng entity, ngắn cho truy vấn tĩnh | Điều kiện ổn định, dễ đọc |
| JPA Criteria API | API chuẩn JPA, expression tree xây bằng Java | Bộ lọc/joins/nhóm điều kiện động |
| Spring Data Specification | Ghép predicate qua interface dựa trên Criteria | Ứng dụng Spring có nhiều filter tái sử dụng |
| QueryDSL | Query DSL typed/fluent, cần tích hợp thư viện và code generation phù hợp | Muốn truy vấn động dễ đọc và type-safe hơn |
| jOOQ | DSL gần với SQL và nhiều feature DB | Query SQL/reporting phong phú, chấp nhận dependency |
| Native SQL | Truy cập trực tiếp tính năng database | CTE/window/vendor feature, query được tối ưu thủ công |

JPA Criteria có ưu thế **thuộc chuẩn JPA**, không bắt buộc thêm query DSL library. Nhưng code verbose, đặc biệt khi dùng nhiều chuỗi tên field. QueryDSL hoặc jOOQ có thể phù hợp hơn ở một số dự án; cần cân nhắc chi phí dependency, license, build/codegen và mức độ phụ thuộc database.

Không dùng đồng thời mọi công cụ chỉ vì chúng tồn tại. Một nhóm nên có conventions: dùng JPQL cho query tĩnh, Criteria/Specification cho search động và native SQL/DSL cho những truy vấn thực sự cần tính năng DB.

## 30. Thiết kế reusable predicate builder đúng ranh giới

Khi code tăng lên, dễ muốn tạo một “query builder toàn năng” có hàng trăm field và option.

Một kiểu builder quá tổng quát:

~~~java
QueryBuilder builder = new QueryBuilder();
builder.addRawPath(clientPath);
builder.addRawOperator(clientOperator);
builder.addRawValue(clientValue);
builder.addRawJoin(clientJoin);
~~~

có thể trở thành ngôn ngữ query tùy ý từ client, khó kiểm soát security và hiệu năng.

Thường tốt hơn là chia theo **use case/domain**:

~~~text
OrderSearchFilter
  |
  +-- OrderPredicateBuilder
  |
  +-- OrderSearchRepository

ProductSearchFilter
  |
  +-- ProductPredicateBuilder
  |
  +-- ProductSearchRepository
~~~

### 30.1. Predicate builder nên không giữ trạng thái qua request

Tránh giữ `Root`, `CriteriaQuery` hoặc `List<Predicate>` ở field singleton dùng lại cho nhiều request. Các object đó gắn với cây query cụ thể và không phải state dùng chung an toàn cho mọi thread.

Tốt hơn:

~~~java
private Predicate buildFilter(
        CriteriaBuilder cb,
        CriteriaQuery<?> query,
        Root<PurchaseOrder> root,
        OrderSearchFilter filter) {
    // Tạo tất cả Predicate mới ở scope lần gọi.
}
~~~

### 30.2. Không tái sử dụng Root của query khác

Sai:

~~~java
Root<PurchaseOrder> dataRoot =
    dataQuery.from(PurchaseOrder.class);

// Sai nếu cố dùng dataRoot cho countQuery:
countQuery.where(
    cb.equal(dataRoot.get("status"), status)
);
~~~

Đúng:

~~~java
Root<PurchaseOrder> countRoot =
    countQuery.from(PurchaseOrder.class);

countQuery.where(
    cb.equal(countRoot.get("status"), status)
);
~~~

### 30.3. Tách fetch, order, selection khỏi filter

Một helper có thể trả Predicate:

~~~java
Predicate where = buildFilter(cb, cq, root, filter);
~~~

Nhưng nên tránh để helper âm thầm gọi:

~~~java
root.fetch("lines");
cq.orderBy(...);
cq.select(...);
~~~

nếu nó được dùng cả ở COUNT query hoặc projection. **Filter** là phần logic có thể dùng chung; **fetch/selection/order/paging** là phần riêng của từng mục đích truy vấn.

## 31. Kiểm thử truy vấn động theo từng nhóm thay vì mọi tổ hợp

Với 10 filter có thể có 1.024 tổ hợp presence/absence. Không nhất thiết test thủ công tất cả bằng 1.024 case, nhưng phải kiểm tra các nhóm nguy cơ cao.

### 31.1. Fixture có thể phân biệt các logic

Ví dụ database test:

~~~text
Customer A: "Nguyễn An"
Customer B: "Trần Bình"

Order #101:
  status = PAID
  customer = A
  total = 600000
  createdAt = 2026-01-10
  Line Product X

Order #102:
  status = NEW
  customer = A
  total = 200000
  createdAt = 2026-01-20
  Line Product Y

Order #103:
  status = CANCELLED
  customer = B
  total = 700000
  createdAt = 2026-02-01
  Không có Line
~~~

Dữ liệu cần có các trường hợp không khớp để phát hiện:

- OR sai dấu ngoặc.
- Khoảng thời gian sai biên.
- NULL filter được hiểu nhầm.
- LEFT/INNER JOIN làm mất row.
- EXISTS trả sai.
- Count trùng.
- Sort/tie-breaker sai.
- Bỏ sót predicate bảo vệ tenant.

### 31.2. Các lớp test hữu ích

| Nhóm test | Mục tiêu |
|---|---|
| Không filter | Trả phạm vi dữ liệu được phép, đúng phân trang |
| Mỗi filter đơn lẻ | Xác minh semantics từng điều kiện |
| Nhiều filter AND | Chỉ giữ giao của các điều kiện |
| Một nhóm OR | Tránh lỗi dấu ngoặc |
| Keyword có `%`/`_` | Kiểm tra escape literal |
| Date from/to | Kiểm tra biên inclusive/exclusive |
| Product EXISTS | Không trùng Order khi nhiều Lines khớp |
| HasLines true/false/null | Kiểm tra ba trạng thái |
| Count + page | Total khớp tập root duy nhất |
| Sort tie | Kết quả ổn định khi giá trị sort bằng nhau |
| Invalid input | Chặn size, page, min/max sai |
| Permission/tenant | Không lộ dữ liệu không được phép |
| Query performance | Kiểm tra SQL/index và giới hạn tài nguyên |

### 31.3. Test tích hợp với DB/provider thật

Criteria được JPA provider dịch thành SQL. Nếu dùng H2 cho test nhưng production là PostgreSQL hoặc MySQL, một số behavior có thể khác:

- LIKE/collation/case sensitivity.
- Timestamp/precision và timezone.
- NULL ordering.
- Pagination.
- JOIN handling.
- SQL syntax cho subquery/aggregation.
- Execution plan và index.

Những use case quan trọng nên kiểm thử trên database mục tiêu hoặc môi trường tương thích đủ tốt.

### 31.4. Test count query riêng

Ví dụ Order #101 có hai Line đều khớp Product X. Khi filter product X:

~~~text
Kết quả đúng:
  items = [Order #101]
  totalElements = 1
~~~

Nếu query data dùng JOIN to-many và count query dùng `count(root)` không DISTINCT, total có thể thành 2. Đây là lỗi phổ biến gây sai UI phân trang dù danh sách entity trông đúng.

### 31.5. Tránh test chỉ kiểm tra số SQL nhưng bỏ nội dung

Một query trả nhanh và dùng một SQL chưa chắc đúng nghiệp vụ. Phải assert tập entity/DTO, thứ tự, tổng số và quyền truy cập. Sau khi đúng, mới đo SQL/latency và tối ưu.

## 32. Hiệu năng: Criteria không phải tự thân là tối ưu

Cùng một yêu cầu, Criteria:

~~~java
cb.equal(root.get("status"), OrderStatus.PAID)
~~~

và JPQL:

~~~java
"WHERE o.status = :status"
~~~

có thể dẫn tới SQL tương tự. Không có lý do chung để kết luận Criteria nhanh hơn chỉ vì nó là Java API.

### 32.1. Những yếu tố thường quyết định hiệu năng

- Cột có index phù hợp không.
- Số bản ghi và độ chọn lọc của filter.
- Có JOIN to-many nhân row không.
- EXISTS có kế hoạch tốt không.
- Query cần projection hay full entity.
- Có N+1 từ lazy association không.
- Có pagination sâu bằng OFFSET không.
- Có ORDER BY nhiều cột hay function trên cột index không.
- COUNT query có đắt không.
- Có transaction/lock cạnh tranh không.

### 32.2. Query dynamic có thể tạo nhiều SQL shape

Một lợi ích của Criteria động là chỉ thêm các điều kiện cần thiết, tránh mệnh đề OR chứa nhiều parameter null. Nhưng query shape thay đổi cũng có thể tạo nhiều SQL text khác nhau, ảnh hưởng plan caching.

Không có lựa chọn tối ưu chung cho mọi DB. Hãy kiểm tra các filter phổ biến, đo trong môi trường giống production và ghi lại kế hoạch thực thi của những tổ hợp nặng nhất.

### 32.3. Giới hạn và timeout cho tìm kiếm rộng

Nếu user không gửi filter nào:

~~~text
status = null
keyword = null
productId = null
...
~~~

query có thể tìm trong toàn bộ bảng. Repository vẫn nên giới hạn page size. Với dữ liệu rất lớn, có thể yêu cầu ít nhất một tiêu chí hoặc giới hạn khoảng thời gian tìm kiếm, nếu phù hợp nghiệp vụ.

Timeout JPA:

~~~java
query.setHint(
    "jakarta.persistence.query.timeout",
    3000
);
~~~

có thể là một hàng rào bổ sung nhưng khả năng áp dụng phụ thuộc provider/driver/DB. Không dùng timeout thay cho thiết kế query có giới hạn và index phù hợp.

## 33. Những lỗi thường gặp khi dùng Criteria API

| Lỗi hoặc hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Điều kiện đầu tiên biến mất | Gọi `where` nhiều lần và ghi đè restriction | Gom Predicate, gọi `where` một lần |
| Query trả cả CANCELLED dù lọc PAID | Nhóm OR/AND sai | Xây nhóm bằng `cb.or` rồi AND với status |
| Bộ lọc false không hoạt động | Chỉ xử lý `Boolean.TRUE`, bỏ qua false | Phân biệt true/false/null rõ ràng |
| Count lớn hơn số Order | JOIN to-many nhân row | EXISTS hoặc `countDistinct` |
| Page trả ít Order hơn size | Fetch join collection + pagination | Page ID trước, fetch sau |
| JPQL/SQL báo field không tồn tại | `root.get("...")` sai tên property Java | Dùng đúng field hoặc static metamodel |
| Nhập `%` tìm ra quá nhiều kết quả | LIKE coi `%` là wildcard | Escape nếu yêu cầu literal search |
| Filter date thiếu ngày cuối | Dùng `<= midnight` sai | Khoảng nửa mở `[from,to)` |
| Sort theo field bất kỳ gây exception | Client truyền field không được mapping | Whitelist enum/path |
| Offset âm hoặc overflow | page/size không validate | Validate và `Math.multiplyExact` |
| Count query lỗi khi fetch | Reuse fetch của data query | Không fetch trong count query |
| Reuse Predicate bị lỗi root | Predicate gắn với query trước | Rebuild từ helper trên root mới |
| Test chạy H2 đúng nhưng production sai | Dialect/collation/timezone khác | Integration test DB mục tiêu |
| Query chậm dù Criteria gọn | SQL plan/index/payload chưa tốt | EXPLAIN, projection, index |
| Các join bị tạo trùng | Mỗi filter tạo join riêng | Reuse Join trong query context |
| Query trả dữ liệu tenant khác | Permission predicate bị xem là tùy chọn | Thêm security predicate bắt buộc |
| N+1 sau khi lấy danh sách | Query tải Order nhưng DTO truy cập association LAZY | Projection/fetch plan theo use case |
| Bulk CriteriaUpdate để lại entity cũ | Bulk DML bỏ qua managed state synchronization | Flush/clear/refresh có kiểm soát |
| `IN ()` không hợp lệ | List filter rỗng | Xác định semantics và xử lý trước khi tạo IN |
| Kết quả page trôi khi có insert đồng thời | Offset pagination trên dữ liệu biến động | Stable sort, xem xét keyset/cursor |

Không xử lý các lỗi này bằng cách đổi sang native SQL ngay lập tức. Trước tiên phân biệt **lỗi business semantics, lỗi Criteria tree, lỗi mapping** và **vấn đề SQL plan**.

## 34. Bài tập thực hành

### Bài 1: Chọn JPQL hay Criteria

Yêu cầu: luôn tìm Customer theo ID, không có filter khác.

**Câu hỏi:** Có nhất thiết dùng Criteria API không?

**Đáp án:** Không. `em.find(Customer.class, id)` hoặc một JPQL/repository method rõ ràng thường đơn giản hơn. Criteria chỉ có ích nếu có nhu cầu cấu trúc query động thực tế.

### Bài 2: Ba bộ lọc tùy chọn

Màn hình có status, minTotal và customerId; cả ba có thể null.

**Câu hỏi:** Thiết kế Criteria thế nào?

**Đáp án gợi ý:** Tạo `List<Predicate>`, chỉ thêm `cb.equal` cho status/customerId có mặt và `cb.greaterThanOrEqualTo` cho minTotal có mặt; gọi `cq.where(predicates.toArray(Predicate[]::new))` một lần.

### Bài 3: Cú pháp AND/OR

Nghiệp vụ yêu cầu:

~~~text
status = PAID AND (orderNumber LIKE x OR customerName LIKE x)
~~~

**Câu hỏi:** Vì sao hai nhóm điều kiện cần có ngoặc?

**Đáp án:** Nếu viết `(PAID AND orderNumber LIKE x) OR customerName LIKE x`, một Order không phải PAID vẫn có thể xuất hiện do Customer khớp keyword. Dùng `cb.and(statusPredicate, cb.or(numberPredicate, namePredicate))`.

### Bài 4: Hai lời gọi `where`

~~~java
cq.where(cb.equal(root.get("status"), OrderStatus.PAID));
cq.where(cb.equal(root.get("customer").get("id"), 42L));
~~~

**Câu hỏi:** Có phải cả hai điều kiện đều được giữ?

**Đáp án:** Không. Lời gọi thứ hai thay thế restriction trước. Phải kết hợp Predicate trước khi gọi `where`.

### Bài 5: Lọc Product ở Line

Order #10 có ba Lines, trong đó hai Lines trỏ Product #17.

**Câu hỏi:** Vì sao JOIN trực tiếp có thể gây duplicate root? Cách khác là gì?

**Đáp án:** JOIN trả nhiều SQL row tương ứng hai Lines; có thể dùng DISTINCT. Nếu chỉ kiểm tra sự tồn tại, EXISTS subquery phù hợp hơn về ngữ nghĩa và tránh nhân root ở query ngoài.

### Bài 6: Count query

Data query được xây trên `dataRoot`, count query được xây trên `countRoot`.

**Câu hỏi:** Có nên đưa một Predicate object từ data query sang count query không?

**Đáp án:** Không. Predicate/path gắn với cây query/root nguồn. Tái sử dụng **hàm xây predicate** và gọi với countRoot mới.

### Bài 7: HasLines bằng Boolean

Input `hasLines` có thể null, true hoặc false.

**Câu hỏi:** Diễn giải ba trạng thái?

**Đáp án:** Null không lọc; true dùng `cb.isNotEmpty(root.get("lines"))`; false dùng `cb.isEmpty(root.get("lines"))`.

### Bài 8: Keyword có dấu phần trăm

Người dùng tìm mã đơn chứa chuỗi literal `OFF%20`.

**Câu hỏi:** Vì sao nối `"%" + keyword + "%"` có thể sai?

**Đáp án:** Dấu `%` bên trong input được SQL LIKE hiểu là wildcard. Nếu nghiệp vụ muốn literal substring, escape `%`, `_` và escape character theo quy tắc/dialect được kiểm chứng.

### Bài 9: Date range

Muốn tìm các đơn trong ngày 15/11/2026 theo múi giờ doanh nghiệp.

**Câu hỏi:** Nên tạo predicate ra sao?

**Đáp án:** Chuyển start-of-day 15/11 và start-of-day 16/11 ở timezone nghiệp vụ thành Instant; dùng `createdAt >= from` và `createdAt < toExclusive`. Không dùng `<= 23:59:59` để đoán precision.

### Bài 10: Sort động

Client gửi `sortField="customer.passwordHash"`.

**Câu hỏi:** Có truyền trực tiếp cho `root.get(sortField)` không?

**Đáp án:** Không. Chỉ chấp nhận enum/whitelist những field được phép sắp xếp, ví dụ CREATED_AT/TOTAL_AMOUNT/ORDER_NUMBER, rồi ánh xạ vào Criteria Path phía server.

### Bài 11: Fetch collection khi phân trang

Một query dùng `root.fetch("lines")` và `setMaxResults(20)`.

**Câu hỏi:** Vì sao có rủi ro?

**Đáp án:** JOIN to-many có thể nhân nhiều SQL row cho một Order; provider có thể phải phân trang trong memory hoặc không trả đúng số root mong muốn. Cân nhắc query page ID rồi fetch association sau.

### Bài 12: Static metamodel

Dự án thường rename field nhưng Criteria viết nhiều `root.get("fieldName")`.

**Câu hỏi:** Làm thế nào tăng compile-time safety?

**Đáp án:** Cấu hình annotation processor sinh JPA static metamodel và dùng `root.get(PurchaseOrder_.createdAt)`. Nhưng vẫn phải test ngữ nghĩa AND/OR/JOIN/count.

### Bài 13: Specification trong Spring Data

Một service có 15 bộ lọc và nhiều repository cần tái sử dụng các predicate nhỏ.

**Câu hỏi:** Có nên cân nhắc Specification?

**Đáp án:** Có thể. `Specification<T>` xây trên Criteria và hỗ trợ composition trong Spring Data JPA. Cần giữ rõ security predicate, tránh spec tự thêm fetch khi count query và kiểm tra phiên bản Spring Data.

### Bài 14: Criteria có nhanh hơn JPQL không?

Hai query logic giống nhau, một dùng JPQL và một dùng Criteria.

**Câu hỏi:** Có thể kết luận Criteria nhanh hơn?

**Đáp án:** Không. Provider có thể sinh SQL giống nhau. Hiệu năng phụ thuộc SQL, index, data distribution, fetch plan và DB execution plan; phải đo thực tế.

### Bài 15: Query không filter trên bảng lớn

User không chọn filter, database có 20 triệu Order.

**Câu hỏi:** Có nên cho trả tất cả entity mà không giới hạn?

**Đáp án:** Không. Cần giới hạn page size, sort ổn định, xem quyền truy cập và có thể yêu cầu filter bắt buộc theo nghiệp vụ. Criteria không thay thế kiểm soát tài nguyên.

### Bài 16: Bulk update và persistence context

CriteriaUpdate đổi trạng thái 1.000 Order trong DB.

**Câu hỏi:** Entity đã managed trước đó có chắc cập nhật field ngay trong memory?

**Đáp án:** Không. Bulk Criteria DML có thể để persistence context stale, tương tự bulk JPQL. Cần thiết kế flush/clear/refresh và transaction phù hợp.

## 35. Quy trình quyết định trong dự án thật

Khi nhận user story liên quan truy vấn dữ liệu, có thể đi theo chuỗi bước:

### Bước 1: Liệt kê mọi bộ lọc và semantics của chúng

Với mỗi field:

- Có thể vắng mặt không?
- Null, rỗng, false và zero có ý nghĩa gì?
- Điều kiện bằng, khoảng, danh sách, LIKE hay EXISTS?
- AND/OR theo nhóm nào?
- Có filter bắt buộc về quyền truy cập không?

### Bước 2: Xác định hình dạng query có thật sự động không

Nếu tất cả biến thể chỉ là giá trị tham số, JPQL có thể đủ. Nếu chính **số lượng hoặc cấu trúc Predicate/JOIN/Subquery** thay đổi mạnh, Criteria đáng cân nhắc.

### Bước 3: Xác định kết quả cần entity hay DTO

Nếu màn hình chỉ cần 5 cột, projection có thể tốt hơn full entity. Không mặc định query search phải trả entity managed.

### Bước 4: Tách logic filter khỏi selection/fetch/sort

Thiết kế helper tạo predicate dùng cho data/count query với root riêng, còn selection và pagination dành cho từng query.

### Bước 5: Chọn cơ chế tổ hợp

- List Predicate cho AND đơn giản.
- `cb.or` cho keyword và nhóm lựa chọn.
- `cb.exists` cho kiểm tra có con.
- Join to-one cho filter liên quan.
- Join to-many kèm hiểu biết về duplicate.
- `cb.isEmpty`/`isNotEmpty` cho collection rỗng.

### Bước 6: Xác thực và chuẩn hóa đầu vào

Validate page/size, range min/max, keyword length, enum sort và collection size. Chuyển LocalDate/timezone sang Instant rõ ràng.

### Bước 7: Xây COUNT query riêng nếu cần

Không copy Root/Predicate instance từ data query. Không fetch association trong count query. Xem `countDistinct` nếu có join to-many.

### Bước 8: Thiết kế fetch plan và pagination

Không fetch collection lớn cùng OFFSET page một cách mặc định. Có thể dùng page ID trước, entity graph/to-one fetch hoặc projection.

### Bước 9: Kiểm tra SQL thực tế

Bật logging có kiểm soát, xem generated SQL, execution plan và index. Đối chiếu kết quả query với yêu cầu nghiệp vụ.

### Bước 10: Kiểm thử các nhánh có nguy cơ cao

AND/OR, NULL, boolean false, LIKE wildcard, date boundary, duplicate join, permission, count và tie-breaker. Không chỉ test filter đơn lẻ.

### Bước 11: Đánh giá chi phí bảo trì

Nếu Criteria builder dài hơn nghiệp vụ và không có nhiều phần động, JPQL có thể hợp lý hơn. Nếu đã có Spring Data và nhiều bộ lọc composable, Specification có thể giảm code. Nếu dùng SQL đặc thù sâu, xem query DSL/native SQL.

### Bước 12: Theo dõi khi yêu cầu thay đổi

Khi thêm filter mới:

1. Viết semantics rõ.
2. Validate input.
3. Thêm Predicate vào một builder chung.
4. Kiểm tra data/count consistency.
5. Cập nhật integration tests.
6. Xem SQL/index và giới hạn request.

Không sửa query bằng cách thêm điều kiện vào một chỗ và quên count query hoặc security scope ở chỗ khác.

## 36. Những nguyên tắc cuối cùng

~~~text
                       YÊU CẦU TRUY VẤN
                               |
                               v
                Cấu trúc query có cố định?
                         /           \
                       Có             Không
                       |                |
                       v                v
                JPQL / find()      Bộ lọc/JOIN động?
                                        |
                              +---------+---------+
                              |                   |
                              v                   v
                         Ít biến thể         Nhiều tổ hợp
                              |                   |
                              v                   v
                         JPQL có thể          Criteria API /
                         vẫn phù hợp          Specification
                                                  |
                                                  v
                                      Predicate builder dùng lại
                                                  |
                                   +--------------+-------------+
                                   |                            |
                                   v                            v
                              Data query                    Count query
                                   |                            |
                              Sort, paging                Count đúng root
                                   |                            |
                                   +-------------+--------------+
                                                 |
                                                 v
                                   Kiểm chứng SQL + DB + tests
~~~

Ghi nhớ:

1. **Criteria API hữu ích nhất khi cấu trúc truy vấn thay đổi theo runtime**, không phải chỉ vì muốn thay cú pháp JPQL bằng Java.
2. **Bộ lọc tùy chọn nên tạo Predicate theo điều kiện có mặt**, thay vì viết mọi tổ hợp query bằng `if/else` hoặc nối chuỗi khó kiểm soát.
3. **`where(...)` thay thế restriction trước đó**; hãy kết hợp Predicate bằng `and`/`or` và gọi có chủ đích.
4. **Nhóm AND/OR theo semantics nghiệp vụ**, nhất là khi một filter keyword tìm ở nhiều field.
5. **JOIN to-many có thể nhân row và gây count sai.** Nếu chỉ kiểm tra có child, EXISTS thường diễn đạt tốt hơn.
6. **Đếm trang phải tạo CriteriaQuery và Root riêng**, dùng lại *logic tạo Predicate* chứ không chia sẻ Predicate instance.
7. **Sort field phải whitelist** và nên có tie-breaker để kết quả phân trang ổn định hơn.
8. **Khoảng thời gian nửa mở** thường dễ kiểm soát hơn việc đoán thời điểm cuối ngày, nhưng phải chuyển múi giờ theo hợp đồng nghiệp vụ.
9. **LIKE cần xử lý wildcard nếu muốn tìm literal substring**; query động cũng phải validate size, enum, danh sách và quyền truy cập.
10. **Static metamodel giúp tăng an toàn kiểu ở compile-time**, nhưng không bảo đảm mọi logic query đều đúng.
11. **Spring Data Specification là abstraction dựa trên Criteria**, hữu ích khi nhiều predicate nhỏ cần tái sử dụng; nó không thuộc JPA chuẩn.
12. **Không fetch collection to-many tùy tiện trong query phân trang**, và không mang fetch join của data query sang count query.
13. **Criteria không mặc nhiên nhanh hơn JPQL.** SQL thực tế, index, projection, fetch plan và workload mới quyết định hiệu năng.
14. **Đừng dùng Criteria chỉ vì truy vấn dài.** Với query cố định, JPQL hoặc native SQL rõ ràng có thể dễ đọc và bảo trì hơn.
15. **Kiểm thử đủ các nhánh quan trọng**: null/false/zero, AND/OR, EXISTS, duplicate, count, sort, timezone và security predicate.

Một lựa chọn Criteria API thành công là lựa chọn giúp code phản ánh rõ các quy tắc tìm kiếm đang thay đổi: mỗi bộ lọc có semantics riêng, các nhóm điều kiện được lắp ráp có cấu trúc, data/count không lệch nhau, và SQL được kiểm chứng trên database thực tế. **Hãy dùng Criteria khi tính động của truy vấn thực sự xứng đáng với mức trừu tượng mà nó mang lại.**
