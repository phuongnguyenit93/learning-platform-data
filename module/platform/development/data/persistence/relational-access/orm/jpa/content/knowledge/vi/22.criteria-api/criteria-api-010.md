# Sử dụng biểu thức điều kiện và hàm trong Criteria

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Criteria API

Khi truy vấn bằng JPQL, lập trình viên có thể viết `WHERE c.status = :status`, `CASE WHEN ... THEN ... END`, `COALESCE(...)` hoặc `LOWER(...)` dưới dạng chuỗi. Với **JPA Criteria API**, những biểu thức đó được tạo bằng các đối tượng Java: `CriteriaBuilder`, `CriteriaQuery`, `Root`, `Path`, `Expression` và `Predicate`.

Criteria API đặc biệt hữu ích khi người dùng có thể gửi nhiều bộ lọc tùy chọn: trạng thái khách hàng, khoảng điểm, tên chứa từ khóa, ngày đặt hàng, mức doanh thu. Thay vì nối chuỗi JPQL thủ công, ứng dụng xây dựng một **cây biểu thức có cấu trúc** rồi giao cho JPA provider chuyển thành SQL.

Các nhóm biểu thức trọng tâm của bài:

- **Điều kiện:** `equal`, `notEqual`, `greaterThan`, `between`, `like`, `isNull`, `in`, `and`, `or`, `not`.
- **Lựa chọn giá trị:** `selectCase`, `coalesce`, `nullif`.
- **Hàm chuỗi:** `lower`, `upper`, `trim`, `concat`, `substring`, `length`, `locate`.
- **Hàm số và aggregate:** `sum`, `diff`, `prod`, `quot`, `abs`, `count`, `avg`, `min`, `max`.
- **Thời gian:** `currentDate`, `currentTime`, `currentTimestamp`, so sánh `LocalDateTime`.
- **Hàm đặc thù DB:** `function` với giới hạn về tính portable.

Dù được viết bằng Java, một Criteria query vẫn chạy theo **ngữ nghĩa truy vấn quan hệ**. Cần hiểu đúng `NULL`, JOIN, GROUP BY, cardinality, index và SQL dialect để kết quả chính xác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Expression<T>`, `Predicate`, `Path<T>` và `Root<T>`.
2. Dùng `CriteriaBuilder` để tạo điều kiện so sánh, NULL, LIKE và IN.
3. Kết hợp AND/OR/NOT đúng thứ tự.
4. Xây bộ lọc động từ request mà không ghép chuỗi JPQL không an toàn.
5. Tạo searched CASE và simple CASE, hiểu thứ tự các nhánh.
6. Dùng COALESCE, NULLIF và TRIM để xử lý giá trị mặc định và chuỗi rỗng.
7. Dùng hàm chuỗi, số, ngày và hàm mở rộng của database một cách có chủ đích.
8. Kết hợp biểu thức trong SELECT, WHERE, ORDER BY, JOIN ON và HAVING.
9. Tạo conditional aggregation bằng CASE kết hợp SUM.
10. Trả DTO bằng `CriteriaBuilder.construct`, thay vì chỉ trả entity.
11. Xây truy vấn có GROUP BY và giữ record không có association bằng LEFT JOIN.
12. Đánh giá tác động của biểu thức lên SQL generated, index và phân trang.
13. Biết khi nào nên dùng Criteria API, JPQL tĩnh hoặc native SQL.

---

## 2. Các thành phần trong Criteria API

| Thành phần | Chức năng |
|---|---|
| `EntityManager` | Cấp builder và thực thi query |
| `CriteriaBuilder` | Tạo biểu thức, hàm, điều kiện và query |
| `CriteriaQuery<T>` | Biểu diễn truy vấn SELECT trả kiểu T |
| `Root<T>` | Đối tượng gốc trong mệnh đề FROM |
| `Path<T>` | Đường dẫn đến persistent attribute |
| `Expression<T>` | Một biểu thức có giá trị kiểu T |
| `Predicate` | Biểu thức điều kiện đúng/sai/UNKNOWN theo SQL |
| `Join<X,Y>` | Association JOIN giữa root/entity |
| `ParameterExpression<T>` | Tham số có kiểu được bind lúc thực thi |
| `Order` | Yêu cầu sắp xếp trong ORDER BY |
| `Selection<T>` | Thành phần trong phần kết quả SELECT |

Ví dụ JPQL:

```jpql
SELECT c
FROM Customer c
WHERE c.status = :status
  AND c.loyaltyPoints >= :minimum
ORDER BY c.id
```

Criteria tương đương:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> c = cq.from(Customer.class);

Predicate statusMatches = cb.equal(
    c.get("status"),
    CustomerStatus.ACTIVE
);

Predicate enoughPoints = cb.ge(
    c.<Integer>get("loyaltyPoints"),
    50
);

cq.select(c)
  .where(cb.and(statusMatches, enoughPoints))
  .orderBy(cb.asc(c.get("id")));

List<Customer> result =
    em.createQuery(cq).getResultList();
```

`cq.select`, `where`, `orderBy` chỉ xây mô hình truy vấn. Khi gọi `getResultList()`, provider chuyển Criteria thành SQL và thực thi. Một số thay đổi pending trong persistence context có thể được flush trước query, tùy transaction và flush mode.

### 2.1. Root và Path

```java
Root<Customer> c = cq.from(Customer.class);

Path<String> name = c.get("fullName");
Path<Integer> points = c.get("loyaltyPoints");
Path<CustomerStatus> status = c.get("status");
```

Vì `get(String)` nhận tên field dạng chuỗi, có thể khai báo type tường minh khi lồng expression:

```java
c.<Integer>get("loyaltyPoints")
c.<String>get("fullName")
c.<CustomerStatus>get("status")
```

Điều này giúp Java chọn overload thích hợp cho `greaterThan`, `lower` hoặc `selectCase`.

**Quan trọng:** dùng **tên persistent attribute Java** trong Criteria, không dùng tên cột database. `c.get("loyaltyPoints")` đúng nếu entity field là `loyaltyPoints`, dù SQL column là `loyalty_points`.

---

## 3. Mô hình ví dụ xuyên suốt

Ta xét một hệ thống bán hàng:

```text
Customer 1 -------- N PurchaseOrder

Customer:
  id: Long
  fullName: String
  nickname: String?
  city: String?
  email: String?
  loyaltyPoints: Integer?
  status: CustomerStatus

PurchaseOrder:
  id: Long
  customer: Customer
  status: OrderStatus
  totalAmount: BigDecimal
  createdAt: LocalDateTime
  shippedAt: LocalDateTime?
```

Hai enum:

```java
package demo.domain;

public enum CustomerStatus {
    ACTIVE,
    SUSPENDED,
    INACTIVE
}
```

```java
package demo.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

### 3.1. Entity Customer

```java
package demo.domain;

import jakarta.persistence.*;
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

    @Column(name = "nickname", length = 80)
    private String nickname;

    @Column(name = "city", length = 100)
    private String city;

    @Column(name = "email", length = 180)
    private String email;

    @Column(name = "loyalty_points")
    private Integer loyaltyPoints;

    @Enumerated(EnumType.STRING)
    @Column(name = "customer_status", nullable = false, length = 20)
    private CustomerStatus status;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Customer(String fullName, CustomerStatus status) {
        this.fullName = Objects.requireNonNull(fullName);
        this.status = Objects.requireNonNull(status);
    }

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
    public String getNickname() { return nickname; }
    public String getCity() { return city; }
    public String getEmail() { return email; }
    public Integer getLoyaltyPoints() { return loyaltyPoints; }
    public CustomerStatus getStatus() { return status; }
    public List<PurchaseOrder> getOrders() { return orders; }

    public void setNickname(String value) { nickname = value; }
    public void setCity(String value) { city = value; }
    public void setEmail(String value) { email = value; }

    public void setLoyaltyPoints(Integer value) {
        if (value != null && value < 0) {
            throw new IllegalArgumentException("Negative points");
        }
        loyaltyPoints = value;
    }
}
```

### 3.2. Entity PurchaseOrder

```java
package demo.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "shipped_at")
    private LocalDateTime shippedAt;

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer,
                         OrderStatus status,
                         BigDecimal totalAmount,
                         LocalDateTime createdAt) {
        this.customer = Objects.requireNonNull(customer);
        this.status = Objects.requireNonNull(status);
        this.totalAmount = Objects.requireNonNull(totalAmount);
        this.createdAt = Objects.requireNonNull(createdAt);
    }

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getShippedAt() { return shippedAt; }
}
```

### 3.3. Dữ liệu minh họa

| Customer | nickname | city | points | status |
|---|---|---|---:|---|
| Nguyễn An | An | Hà Nội | 80 | ACTIVE |
| Trần Bình | NULL | Đà Nẵng | NULL | SUSPENDED |
| Lê Chi | chuỗi toàn dấu cách | Hà Nội | 0 | ACTIVE |
| Phạm Dung | NULL | NULL | 35 | INACTIVE |
| Hoàng Em | Em | Huế | 60 | ACTIVE |

| Order | Customer | status | totalAmount |
|---|---|---|---:|
| 101 | Nguyễn An | PAID | 150.00 |
| 102 | Nguyễn An | NEW | 70.00 |
| 103 | Trần Bình | CANCELLED | 100.00 |
| 104 | Hoàng Em | PAID | 250.00 |

Khách Lê Chi và Phạm Dung chưa có Order; Trần Bình chưa có Order PAID. Những trường hợp này rất hữu ích khi học LEFT JOIN và aggregate.

### 3.4. Import cơ bản

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Expression;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.ParameterExpression;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
```

Các snippet sau giả định entity `Customer`/`PurchaseOrder` và enum nằm trong package `demo.domain`, và `em` là EntityManager hợp lệ trong unit of work.

---

## 4. Điều kiện so sánh cơ bản

### 4.1. equal và notEqual

```java
Predicate active = cb.equal(
    c.get("status"),
    CustomerStatus.ACTIVE
);

Predicate notSuspended = cb.notEqual(
    c.get("status"),
    CustomerStatus.SUSPENDED
);
```

Điều kiện JPQL tương ứng:

```jpql
c.status = :active
c.status <> :suspended
```

Vì `status` là enum, hãy truyền giá trị `CustomerStatus.ACTIVE` thay vì String `"ACTIVE"` tùy tiện.

### 4.2. So sánh số

```java
Predicate min50 = cb.ge(
    c.<Integer>get("loyaltyPoints"),
    50
);

Predicate lessThan100 = cb.lt(
    c.<Integer>get("loyaltyPoints"),
    100
);
```

Nhóm phép toán:

| Ý nghĩa | CriteriaBuilder |
|---|---|
| Bằng | `equal` |
| Khác | `notEqual` |
| Lớn hơn | `gt` hoặc `greaterThan` |
| Lớn hơn/bằng | `ge` hoặc `greaterThanOrEqualTo` |
| Nhỏ hơn | `lt` hoặc `lessThan` |
| Nhỏ hơn/bằng | `le` hoặc `lessThanOrEqualTo` |
| Trong khoảng | `between` |

Các overload `gt/ge/lt/le` dùng cho số; nhóm `greaterThan/lessThan` dùng cho kiểu comparable được JPA hỗ trợ như số, chuỗi, thời gian.

### 4.3. BETWEEN

```java
Predicate midTier = cb.between(
    c.<Integer>get("loyaltyPoints"),
    30,
    69
);
```

Tương đương `loyaltyPoints BETWEEN 30 AND 69`, bao gồm cả hai đầu mút. Nếu points NULL, predicate không TRUE.

### 4.4. IN

```java
List<CustomerStatus> allowed = List.of(
    CustomerStatus.ACTIVE,
    CustomerStatus.SUSPENDED
);

Predicate allowedStatus =
    c.get("status").in(allowed);
```

Hoặc:

```java
CriteriaBuilder.In<CustomerStatus> inStatus =
    cb.in(c.<CustomerStatus>get("status"));

inStatus.value(CustomerStatus.ACTIVE);
inStatus.value(CustomerStatus.SUSPENDED);
```

Với danh sách lọc trống, cần xác định semantics:

- “Không chọn filter” → bỏ predicate.
- “Chọn một tập rỗng hợp lệ” → query không trả bản ghi → dùng `cb.disjunction()`.

Không giả định mọi provider đều xử lý `IN ()` như nhau.

---

## 5. NULL và logic ba giá trị

`NULL` không phải 0, chuỗi rỗng hay false. Trong logic SQL:

| Biểu thức | Kết quả |
|---|---|
| `5 = 5` | TRUE |
| `5 = 6` | FALSE |
| `5 = NULL` | UNKNOWN |
| `NULL = NULL` | UNKNOWN |
| `NULL >= 30` | UNKNOWN |
| `NULL IS NULL` | TRUE |

Trong `WHERE`, chỉ hàng có predicate TRUE được giữ lại. FALSE và UNKNOWN đều không đạt.

### 5.1. isNull và isNotNull

```java
Predicate emailMissing = cb.isNull(
    c.get("email")
);

Predicate hasCity = cb.isNotNull(
    c.get("city")
);
```

Không dùng:

```java
cb.equal(c.get("email"), null);
```

rồi kỳ vọng luôn được dịch thành `IS NULL`. Dùng `cb.isNull` là cách rõ nghĩa và portable.

### 5.2. NOT không tự bao gồm NULL

```java
Predicate notHanoi = cb.notEqual(
    c.get("city"),
    "Hà Nội"
);
```

Một Customer có city NULL không tự được chọn vì `NULL <> 'Hà Nội'` là UNKNOWN.

Nếu muốn giữ Customer city NULL:

```java
Predicate otherOrUnknown = cb.or(
    cb.notEqual(c.get("city"), "Hà Nội"),
    cb.isNull(c.get("city"))
);
```

**Nhận xét:** NULL được diễn giải theo truy vấn. Có báo cáo muốn xem NULL là “chưa xác định”, có báo cáo muốn mặc định bằng một giá trị; không có một cách xử lý đúng cho mọi nghiệp vụ.

---

## 6. AND, OR, NOT và thứ tự điều kiện

### 6.1. AND

```java
Predicate active = cb.equal(
    c.get("status"), CustomerStatus.ACTIVE);

Predicate atLeast50 = cb.ge(
    c.<Integer>get("loyaltyPoints"), 50);

cq.where(cb.and(active, atLeast50));
```

### 6.2. OR

```java
Predicate hanoi = cb.equal(
    c.get("city"), "Hà Nội");

Predicate hue = cb.equal(
    c.get("city"), "Huế");

cq.where(cb.or(hanoi, hue));
```

### 6.3. NOT

```java
cq.where(
    cb.not(cb.equal(
        c.get("status"),
        CustomerStatus.SUSPENDED
    ))
);
```

### 6.4. Nhóm đúng ý nghĩa

Nhu cầu: ACTIVE và (ở Hà Nội hoặc Huế):

```java
cq.where(
    cb.and(
        cb.equal(
            c.get("status"),
            CustomerStatus.ACTIVE
        ),
        cb.or(
            cb.equal(c.get("city"), "Hà Nội"),
            cb.equal(c.get("city"), "Huế")
        )
    )
);
```

Sơ đồ:

```text
              AND
             /   \
         ACTIVE    OR
                  /  \
               HANOI  HUE
```

Nếu đổi thành `cb.or(cb.and(active, hanoi), hue)` thì toàn bộ Customer ở Huế đều có thể được chọn, bất kể status. Criteria là cây biểu thức, nhưng vẫn cần logic Boolean đúng.

### 6.5. conjunction và disjunction

```java
Predicate trueCondition = cb.conjunction();
Predicate falseCondition = cb.disjunction();
```

- `conjunction()` biểu diễn TRUE, thuận tiện khởi tạo một chuỗi AND.
- `disjunction()` biểu diễn FALSE, thuận tiện khởi tạo một chuỗi OR.

Đừng dùng `disjunction()` khi muốn “không áp dụng bộ lọc”: nó có thể khiến kết quả rỗng.

---

## 7. Bộ lọc động bằng List<Predicate>

Một tình huống thực tế: API nhận các trường tùy chọn.

```java
public record CustomerFilter(
    CustomerStatus status,
    String nameContains,
    Integer minPoints,
    String city
) {}
```

Repository method:

```java
public List<Customer> search(
        EntityManager em,
        CustomerFilter filter) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Customer> cq =
        cb.createQuery(Customer.class);
    Root<Customer> c = cq.from(Customer.class);

    List<Predicate> predicates = new ArrayList<>();

    if (filter.status() != null) {
        predicates.add(
            cb.equal(c.get("status"), filter.status())
        );
    }

    if (filter.minPoints() != null) {
        predicates.add(
            cb.ge(
                c.<Integer>get("loyaltyPoints"),
                filter.minPoints()
            )
        );
    }

    if (filter.city() != null
            && !filter.city().isBlank()) {
        predicates.add(
            cb.equal(c.get("city"), filter.city().trim())
        );
    }

    if (filter.nameContains() != null
            && !filter.nameContains().isBlank()) {

        String term = escapeLike(
            filter.nameContains()
                .trim()
                .toLowerCase(java.util.Locale.ROOT)
        );

        predicates.add(
            cb.like(
                cb.lower(c.<String>get("fullName")),
                "%" + term + "%",
                '\\'
            )
        );
    }

    cq.select(c)
      .where(predicates.toArray(Predicate[]::new))
      .orderBy(cb.asc(c.get("id")));

    return em.createQuery(cq).getResultList();
}

private static String escapeLike(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
```

Khi không có filter nào, danh sách predicates rỗng; query giữ nguyên tất cả Customer thay vì ép một điều kiện `field = NULL`.

### 7.1. Tại sao escape LIKE?

- `%` khớp một chuỗi ký tự bất kỳ.
- `_` khớp đúng một ký tự.

Nếu người dùng tìm ký tự `%` theo nghĩa đen mà không escape, query có thể trả mọi tên. Hàm `escapeLike` xử lý dấu gạch chéo, phần trăm và gạch dưới để chúng được hiểu là literal; overload `cb.like(..., '\\')` chỉ ra escape character.

### 7.2. Không tự ghép raw JPQL từ request

Không đưa tên cột, operator hay SQL fragment do client gửi trực tiếp vào query. Với trường sort động, lập danh sách field được phép và ánh xạ sang `Path` tương ứng.

### 7.3. Khi nào dùng ParameterExpression?

`CriteriaBuilder.parameter` có thể tạo tham số có kiểu:

```java
ParameterExpression<Integer> minimum =
    cb.parameter(Integer.class, "minimum");

cq.where(
    cb.ge(
        c.<Integer>get("loyaltyPoints"),
        minimum
    )
);

List<Customer> customers = em.createQuery(cq)
    .setParameter("minimum", 50)
    .getResultList();
```

Nên bind giá trị theo kiểu phù hợp, nhất là enum, ngày và BigDecimal. Khi input filter NULL nghĩa là “không lọc”, bỏ predicate thường rõ hơn truyền NULL rồi so sánh.

---

## 8. Searched CASE bằng selectCase()

JPQL có:

```jpql
CASE
    WHEN condition_1 THEN value_1
    WHEN condition_2 THEN value_2
    ELSE default_value
END
```

CriteriaBuilder:

```java
Expression<Integer> points =
    c.<Integer>get("loyaltyPoints");

Expression<String> tier =
    cb.<String>selectCase()
        .when(cb.ge(points, 70), "GOLD")
        .when(cb.ge(points, 30), "SILVER")
        .otherwise("BRONZE");
```

Với dữ liệu mẫu:

| Customer | points | tier |
|---|---:|---|
| Nguyễn An | 80 | GOLD |
| Trần Bình | NULL | BRONZE |
| Lê Chi | 0 | BRONZE |
| Phạm Dung | 35 | SILVER |
| Hoàng Em | 60 | SILVER |

### 8.1. Chỉ nhánh WHEN đầu tiên TRUE được chọn

Sai:

```java
cb.<String>selectCase()
    .when(cb.ge(points, 30), "SILVER")
    .when(cb.ge(points, 70), "GOLD")
    .otherwise("BRONZE");
```

80 điểm sẽ vào SILVER ngay vì `>=30` đúng. Phải viết các điều kiện có ưu tiên cao trước.

### 8.2. NULL rơi vào ELSE

Khi points NULL, `points >= 70` và `points >= 30` đều UNKNOWN. Không điều kiện nào TRUE nên trả BRONZE.

Nếu nghiệp vụ cần nhãn UNRATED:

```java
Expression<String> tierWithUnknown =
    cb.<String>selectCase()
        .when(cb.isNull(points), "UNRATED")
        .when(cb.ge(points, 70), "GOLD")
        .when(cb.ge(points, 30), "SILVER")
        .otherwise("BRONZE");
```

Đây là thay đổi **ý nghĩa nghiệp vụ**, không chỉ cách viết.

### 8.3. CASE có thể trả số

```java
Expression<Integer> priority =
    cb.<Integer>selectCase()
        .when(
            cb.equal(c.get("status"), CustomerStatus.ACTIVE), 0)
        .when(
            cb.equal(c.get("status"), CustomerStatus.SUSPENDED), 1)
        .otherwise(2);
```

Nó hữu ích trong ORDER BY theo thứ tự ưu tiên thay vì thứ tự alphabet.

### 8.4. ELSE không bắt buộc nhưng có hệ quả

Nếu không có `otherwise(...)`, CASE có thể trả NULL khi không có WHEN nào khớp. Nếu DTO cần một số primitive `int` hoặc một nhãn non-null, việc thiếu ELSE có thể gây lỗi hoặc dữ liệu không mong muốn.

---

## 9. Simple CASE bằng selectCase(expression)

Simple CASE so sánh **một biểu thức** với những giá trị:

```java
CriteriaBuilder.SimpleCase<CustomerStatus, String> statusCase =
    cb.<CustomerStatus, String>selectCase(
        c.<CustomerStatus>get("status")
    );

Expression<String> label = statusCase
    .when(CustomerStatus.ACTIVE, "Hoạt động")
    .when(CustomerStatus.SUSPENDED, "Tạm khóa")
    .when(CustomerStatus.INACTIVE, "Ngừng hoạt động")
    .otherwise("Không xác định");
```

JPQL tương đương:

```jpql
CASE c.status
    WHEN :active THEN 'Hoạt động'
    WHEN :suspended THEN 'Tạm khóa'
    ELSE 'Ngừng hoạt động'
END
```

### 9.1. Khi nào dùng simple CASE?

Dùng khi tất cả nhánh dựa trên một thuộc tính được so sánh bằng với các giá trị khác nhau.

Nếu các điều kiện khác loại, dùng searched CASE:

```java
Expression<String> description =
    cb.<String>selectCase()
        .when(cb.isNull(c.get("email")), "Thiếu email")
        .when(cb.ge(points, 70), "Khách VIP")
        .otherwise("Khách thông thường");
```

### 9.2. Không dùng WHEN NULL thay IS NULL

Nếu muốn kiểm tra nickname NULL, dùng:

```java
cb.<String>selectCase()
    .when(
        cb.isNull(c.get("nickname")),
        "Chưa có biệt danh"
    )
    .otherwise("Đã có biệt danh");
```

Simple CASE dùng so sánh bằng; `NULL = NULL` không TRUE. Vì vậy đừng dựa vào `when(null, ...)` để nhận diện NULL.

---

## 10. COALESCE: giá trị không NULL đầu tiên

JPQL:

```jpql
COALESCE(c.nickname, c.fullName)
```

Criteria:

```java
Expression<String> displayName = cb.coalesce(
    c.<String>get("nickname"),
    c.<String>get("fullName")
);
```

Kết quả là nickname nếu không NULL, ngược lại fullName.

### 10.1. COALESCE không xử lý chuỗi trắng

Với nickname chứa ba dấu cách, COALESCE trả chính ba dấu cách vì đó không phải NULL. Nếu cần coi chuỗi trắng như dữ liệu thiếu, kết hợp `trim` và `nullif`.

### 10.2. Nhiều mức fallback

```java
CriteriaBuilder.Coalesce<String> fallback =
    cb.<String>coalesce();

fallback.value(c.<String>get("nickname"));
fallback.value(c.<String>get("fullName"));
fallback.value(cb.literal("Khách hàng"));

Expression<String> result = fallback;
```

Builder `Coalesce<String>` thêm các lựa chọn theo thứ tự. Nếu tất cả đều NULL, kết quả NULL; ở đây có literal cuối nên có fallback rõ ràng.

### 10.3. COALESCE với số

```java
Expression<Integer> displayedPoints =
    cb.coalesce(
        c.<Integer>get("loyaltyPoints"),
        0
    );
```

Điểm NULL được hiển thị bằng 0 trong expression. **Nó không sửa entity và không UPDATE dữ liệu trong database**.

Nếu NULL có nghĩa “chưa chấm điểm”, hãy cân nhắc CASE UNRATED thay vì gộp với 0.

---

## 11. NULLIF: chuyển sentinel thành NULL

JPQL:

```jpql
NULLIF(c.nickname, '')
```

Criteria:

```java
Expression<String> cleaned = cb.nullif(
    c.<String>get("nickname"),
    ""
);
```

Nếu hai biểu thức bằng nhau, trả NULL; ngược lại trả biểu thức thứ nhất.

Các ví dụ:

| nickname | NULLIF(nickname, "") |
|---|---|
| An | An |
| chuỗi rỗng | NULL |
| NULL | NULL |
| chuỗi gồm dấu cách | vẫn là chuỗi dấu cách |

### 11.1. Kết hợp TRIM + NULLIF + COALESCE

```java
Expression<String> displayName = cb.coalesce(
    cb.nullif(
        cb.trim(c.<String>get("nickname")),
        ""
    ),
    c.<String>get("fullName")
);
```

Dòng dữ liệu:

```text
nickname = "   "
      |
      v
TRIM -> ""
      |
      v
NULLIF("", "") -> NULL
      |
      v
COALESCE(NULL, fullName) -> fullName
```

Với nickname `"  An  "`, kết quả là `"An"` sau TRIM. Với nickname NULL, kết quả là fullName.

### 11.2. NULLIF với giá trị số

```java
Expression<BigDecimal> nonZeroAmount =
    cb.nullif(
        o.<BigDecimal>get("totalAmount"),
        BigDecimal.ZERO
    );
```

Có thể dùng trong công thức mà 0 không phải mẫu số hợp lệ, nhưng cần thử chính xác semantics chia số, kiểu trả về và rounding trên provider/database thực tế. Không coi NULLIF là validation cho dữ liệu tiền tệ.

### 11.3. Phân biệt CASE, COALESCE, NULLIF

| Cơ chế | Mục đích chính |
|---|---|
| `selectCase` | Chọn giá trị dựa trên điều kiện |
| `coalesce` | Chọn biểu thức đầu tiên không NULL |
| `nullif` | Trả NULL nếu hai biểu thức bằng nhau |
| `isNull` | Kiểm tra một biểu thức có NULL không |
| `trim` | Loại khoảng trắng theo quy tắc chuỗi |

---

## 12. Hàm chuỗi trong CriteriaBuilder

| Method | Ý nghĩa |
|---|---|
| `lower` | Chuyển chữ thường |
| `upper` | Chuyển chữ hoa |
| `trim` | Xóa khoảng trắng đầu/cuối theo semantics DB |
| `concat` | Ghép chuỗi |
| `substring` | Lấy chuỗi con |
| `length` | Độ dài chuỗi |
| `locate` | Tìm vị trí của chuỗi con |

### 12.1. LOWER, UPPER

```java
Expression<String> lowerName = cb.lower(
    c.<String>get("fullName")
);

Expression<String> upperName = cb.upper(
    c.<String>get("fullName")
);
```

LOWER giúp xây tìm kiếm không phân biệt chữ hoa/thường trong một số collation, nhưng không tự giải quyết việc tìm không dấu tiếng Việt. Unicode normalization và collation cần được thiết kế riêng.

### 12.2. CONCAT

```java
Expression<String> caption = cb.concat(
    c.<String>get("fullName"),
    cb.literal(" - Khách hàng")
);
```

Nếu nối với field nullable, cần hiểu semantics NULL của database. Có thể dùng COALESCE cho những phần cần fallback.

### 12.3. SUBSTRING

```java
Expression<String> prefix = cb.substring(
    c.<String>get("fullName"),
    1,
    3
);
```

Trong JPQL, chỉ số bắt đầu của SUBSTRING là **1**, khác `String.substring` của Java bắt đầu từ 0.

### 12.4. LENGTH

```java
Predicate longName = cb.gt(
    cb.length(c.<String>get("fullName")),
    20
);
```

Độ dài ở database không nhất thiết tương ứng với số grapheme/đơn vị hiển thị ở UI trong các ngôn ngữ Unicode.

### 12.5. LOCATE

```java
Expression<Integer> index = cb.locate(
    c.<String>get("fullName"),
    "An"
);
```

Vị trí và cách xử lý không tìm thấy/NULL theo semantics JPQL và database. Nếu mục tiêu chỉ lọc có chứa một chuỗi, LIKE hoặc full-text search thường diễn đạt trực tiếp hơn.

### 12.6. TRIM theo hướng

```java
Expression<String> trimmed = cb.trim(
    CriteriaBuilder.Trimspec.LEADING,
    '-',
    c.<String>get("nickname")
);
```

`LEADING` xóa ký tự chỉ định ở đầu. Có `TRAILING` và `BOTH`. TRIM không thay thế một bộ xử lý regex hoặc chuẩn hóa dữ liệu Unicode tổng quát.

---

## 13. LIKE và wildcard

`cb.like` tạo predicate chuỗi:

```java
Predicate nameContainsAn = cb.like(
    c.<String>get("fullName"),
    "%An%"
);
```

Hai wildcard:

- `%`: khớp một chuỗi ký tự bất kỳ, kể cả rỗng.
- `_`: khớp một ký tự.

Đối với input người dùng, dùng escape character để tìm `%` hoặc `_` theo nghĩa literal:

```java
String escaped = input
    .replace("\\", "\\\\")
    .replace("%", "\\%")
    .replace("_", "\\_");

Predicate predicate = cb.like(
    cb.lower(c.<String>get("fullName")),
    "%" + escaped.toLowerCase(java.util.Locale.ROOT) + "%",
    '\\'
);
```

Mặc dù Criteria API giúp tránh ghép raw JPQL, các giá trị vẫn nên được bind có kiểm soát, và những phần dynamic như tên cột/sort/function cần whitelist.

**Hiệu năng:** `LIKE '%text%'` có thể không dùng B-tree index thông thường vì wildcard ở đầu. Trên bảng lớn, cân nhắc full-text search hoặc loại index chuyên biệt.

---

## 14. Hàm số và biểu thức số học

Với `PurchaseOrder.totalAmount` là `BigDecimal`:

```java
Expression<BigDecimal> amount =
    o.<BigDecimal>get("totalAmount");

Expression<BigDecimal> afterDiscount = cb.diff(
    amount,
    new BigDecimal("10.00")
);

Predicate over100 = cb.ge(
    amount,
    new BigDecimal("100.00")
);
```

| Method | Ý nghĩa |
|---|---|
| `sum(x, y)` | Cộng hai số |
| `diff(x, y)` | Trừ |
| `prod(x, y)` | Nhân |
| `quot(x, y)` | Chia |
| `mod(x, y)` | Phần dư số nguyên |
| `abs(x)` | Giá trị tuyệt đối |
| `sqrt(x)` | Căn bậc hai |
| `neg(x)` | Số đối |

### 14.1. sum hai toán hạng và aggregate sum

`cb.sum(x, y)` là phép cộng hai biểu thức. Trong khi:

```java
cb.sum(o.<BigDecimal>get("totalAmount"))
```

là aggregate SUM trên nhiều hàng của nhóm hoặc tập kết quả. Hai overload khác nhau về ý nghĩa dù cùng tên.

### 14.2. Kiểu số trong biểu thức

- `BigDecimal` dùng cho giá trị thập phân chính xác theo định nghĩa domain.
- Tránh trộn String và số trong cùng CASE rồi mong provider tự ép kiểu.
- Cẩn thận với literal Integer 0 khi so với BigDecimal; tham số `BigDecimal.ZERO` thường rõ nghĩa hơn.
- Phép chia và AVG có kiểu kết quả/precision tùy quy tắc JPA và database; phải kiểm tra scale và rounding khi có yêu cầu tài chính.

### 14.3. NULL trong số học

Nếu một toán hạng NULL, phép tính thông thường có thể trả NULL. `coalesce` giúp đưa ra mặc định **trong query** khi nghiệp vụ thật sự cho phép, không tự sửa dữ liệu gốc.

---

## 15. Hàm thời gian và khoảng ngày

CriteriaBuilder có các hàm thời gian:

```java
Expression<java.sql.Date> today =
    cb.currentDate();

Expression<java.sql.Time> timeNow =
    cb.currentTime();

Expression<java.sql.Timestamp> timestampNow =
    cb.currentTimestamp();
```

Đây là biểu thức phía database/provider, không phải chính xác `LocalDateTime.now()` trong JVM.

### 15.1. Điều kiện theo LocalDateTime

Với Order.createdAt kiểu `LocalDateTime`:

```java
LocalDateTime start = LocalDateTime.of(
    2026, 11, 1, 0, 0);

LocalDateTime endExclusive = LocalDateTime.of(
    2026, 12, 1, 0, 0);

Predicate withinNovember = cb.and(
    cb.greaterThanOrEqualTo(
        o.<LocalDateTime>get("createdAt"),
        start
    ),
    cb.lessThan(
        o.<LocalDateTime>get("createdAt"),
        endExclusive
    )
);
```

Khoảng **[start, endExclusive)** là lựa chọn phổ biến: bao gồm thời điểm bắt đầu, loại thời điểm đầu tháng sau. Điều này tránh phải đoán timestamp cuối ngày với precision cụ thể.

### 15.2. Múi giờ và kiểu thời gian

`LocalDateTime` không có timezone/offset. Nếu các server và database lưu thời gian với quy ước khác nhau, báo cáo theo ngày có thể sai. Hãy xác định rõ chính sách UTC/local time, JDBC mapping, database type và thời điểm chuyển đổi timezone.

### 15.3. Tránh bọc cột timestamp bằng hàm không cần thiết

Một query dùng `DATE(created_at) = :day` có thể phụ thuộc dialect và hạn chế sử dụng index. So sánh theo khoảng thời gian trên cột timestamp thường portable và dễ tối ưu hơn.

---

## 16. Hàm database-specific với function()

CriteriaBuilder có:

```java
Expression<T> value = cb.function(
    "function_name",
    ResultType.class,
    expression1,
    expression2
);
```

Ví dụ database có cài hàm `unaccent`:

```java
Expression<String> normalizedName =
    cb.function(
        "unaccent",
        String.class,
        c.<String>get("fullName")
    );
```

Có thể kết hợp với `lower` và `like` để tìm kiếm. Nhưng:

- `unaccent` không phải hàm JPA portable trên mọi DBMS.
- Database phải cài function và provider/dialect phải biết xử lý.
- Kiểu kết quả phải được khai báo đúng.
- Function đặt trên cột có thể ảnh hưởng index.
- Không lấy function name trực tiếp từ input của client.

Không dùng `function(...)` cho mọi trường hợp có API chuẩn như `lower`, `trim`, `coalesce`.

---

## 17. CASE trong ORDER BY

Ví dụ muốn ưu tiên Customer ACTIVE, sau đó SUSPENDED, cuối cùng INACTIVE:

```java
Expression<Integer> priority =
    cb.<Integer>selectCase()
        .when(
            cb.equal(c.get("status"), CustomerStatus.ACTIVE),
            0
        )
        .when(
            cb.equal(c.get("status"), CustomerStatus.SUSPENDED),
            1
        )
        .otherwise(2);

cq.select(c)
  .orderBy(
      cb.asc(priority),
      cb.asc(c.get("id"))
  );
```

`id` làm khóa phụ để tạo thứ tự tương đối ổn định khi nhiều Customer cùng priority, đặc biệt quan trọng khi dùng OFFSET/LIMIT để phân trang.

### 17.1. NULL đứng cuối

Muốn sắp điểm giảm dần nhưng không gộp NULL với 0:

```java
Expression<Integer> missingRank =
    cb.<Integer>selectCase()
        .when(
            cb.isNull(c.get("loyaltyPoints")),
            1
        )
        .otherwise(0);

cq.orderBy(
    cb.asc(missingRank),
    cb.desc(c.get("loyaltyPoints")),
    cb.asc(c.get("id"))
);
```

Dùng CASE xử lý NULL position có thể tiện hơn phụ thuộc cú pháp `NULLS FIRST/LAST` riêng của một dialect.

---

## 18. LEFT JOIN và điều kiện ON

Báo cáo: tổng doanh thu của Order PAID theo từng Customer, **bao gồm Customer chưa có đơn PAID**.

JPQL tương đương:

```jpql
SELECT c.id, c.fullName,
       COALESCE(SUM(o.totalAmount), :zero)
FROM Customer c
LEFT JOIN c.orders o
    ON o.status = :paid
GROUP BY c.id, c.fullName
```

Criteria:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<CustomerRevenue> cq =
    cb.createQuery(CustomerRevenue.class);

Root<Customer> c = cq.from(Customer.class);

Join<Customer, PurchaseOrder> o =
    c.join("orders", JoinType.LEFT);

o.on(
    cb.equal(o.get("status"), OrderStatus.PAID)
);

Expression<BigDecimal> paidTotal = cb.coalesce(
    cb.sum(o.<BigDecimal>get("totalAmount")),
    BigDecimal.ZERO
);

cq.select(
    cb.construct(
        CustomerRevenue.class,
        c.get("id"),
        c.get("fullName"),
        paidTotal
    )
);

cq.groupBy(c.get("id"), c.get("fullName"));
cq.orderBy(cb.asc(c.get("id")));

List<CustomerRevenue> rows =
    em.createQuery(cq).getResultList();
```

DTO:

```java
package demo.dto;

import java.math.BigDecimal;

public record CustomerRevenue(
    Long customerId,
    String customerName,
    BigDecimal paidTotal
) {}
```

Kết quả từ dữ liệu mẫu:

| Customer | paidTotal |
|---|---:|
| Nguyễn An | 150.00 |
| Trần Bình | 0.00 |
| Lê Chi | 0.00 |
| Phạm Dung | 0.00 |
| Hoàng Em | 250.00 |

### 18.1. Tại sao không đặt o.status vào WHERE?

Nếu viết:

```java
cq.where(
    cb.equal(o.get("status"), OrderStatus.PAID)
);
```

thay vì `o.on(...)`, Customer không có Order PAID có thể bị loại khỏi kết quả. Trong LEFT JOIN, hàng không ghép được có `o.status=NULL`; predicate WHERE không TRUE.

**COALESCE không tạo lại Customer đã bị loại bởi WHERE/JOIN.** Nó chỉ thay giá trị NULL của một biểu thức trong những hàng còn tồn tại.

### 18.2. Cardinality và tổng bị nhân

Một Customer có ba Order tạo ba hàng sau JOIN trước GROUP BY. Nếu query join thêm một collection khác, số hàng có thể nhân lên; SUM có thể bị tính lặp.

Đừng dùng `distinct(true)` như “cách chữa chung”. Cần thiết kế lại cardinality, dùng subquery hoặc tách báo cáo theo nhu cầu.

---

## 19. Aggregate: COUNT, SUM, AVG, MIN, MAX

`CriteriaBuilder` hỗ trợ aggregate:

```java
Expression<Long> countOrders = cb.count(o);

Expression<Long> countDistinctIds =
    cb.countDistinct(o.get("id"));

Expression<BigDecimal> total =
    cb.sum(o.<BigDecimal>get("totalAmount"));

Expression<Double> average =
    cb.avg(o.<BigDecimal>get("totalAmount"));

Expression<BigDecimal> minAmount =
    cb.min(o.<BigDecimal>get("totalAmount"));

Expression<BigDecimal> maxAmount =
    cb.max(o.<BigDecimal>get("totalAmount"));
```

| Hàm | Kết quả thường gặp |
|---|---|
| COUNT | Long |
| COUNT DISTINCT | Long |
| SUM(BigDecimal) | BigDecimal |
| AVG | Double |
| MIN/MAX | Kiểu biểu thức tương ứng |

### 19.1. SUM và COUNT với nhóm không có child

`COUNT(o)` thường là 0 cho Customer không có Order ghép được, nếu Customer vẫn được giữ bởi LEFT JOIN.

`SUM(o.totalAmount)` có thể NULL khi nhóm không có giá trị non-null, nên dùng:

```java
cb.coalesce(
    cb.sum(o.<BigDecimal>get("totalAmount")),
    BigDecimal.ZERO
);
```

### 19.2. GROUP BY

```java
cq.groupBy(
    c.get("id"),
    c.get("fullName")
);
```

Khi SELECT cả thuộc tính Customer và aggregate, group theo những thuộc tính chưa aggregate được dùng trong projection. Các extension SQL cho phép group chỉ theo PK không tự bảo đảm cùng cách dùng trên mọi JPA provider.

### 19.3. HAVING

Chỉ lấy Customer có tổng doanh thu PAID ít nhất 100:

```java
cq.having(
    cb.ge(
        paidTotal,
        new BigDecimal("100.00")
    )
);
```

`WHERE` lọc từng hàng trước aggregation; `HAVING` lọc nhóm sau aggregation.

---

## 20. Conditional aggregation bằng CASE

Nếu cần trong cùng báo cáo cả:

- Số Order tất cả trạng thái.
- Số Order PAID.
- Tổng tiền PAID.

Thì JOIN ON lọc chỉ PAID sẽ làm mất các Order NEW/CANCELLED cho các aggregate khác. Có thể JOIN tất cả Order rồi dùng CASE trong aggregate.

### 20.1. Đếm đơn PAID

```java
Expression<Integer> paidFlag =
    cb.<Integer>selectCase()
        .when(
            cb.equal(o.get("status"), OrderStatus.PAID),
            1
        )
        .otherwise(0);

Expression<Long> paidCount =
    cb.sumAsLong(paidFlag);
```

`cb.sumAsLong` trả Long cho tổng của Integer expressions. Đừng nhầm với `cb.count(o)`, vốn đếm mọi Order được join.

### 20.2. Tổng tiền PAID

```java
Expression<BigDecimal> paidValue =
    cb.<BigDecimal>selectCase()
        .when(
            cb.equal(o.get("status"), OrderStatus.PAID),
            o.<BigDecimal>get("totalAmount")
        )
        .otherwise(BigDecimal.ZERO);

Expression<BigDecimal> paidTotal =
    cb.sum(paidValue);
```

Thao tác:

```text
Order PAID       -> trả amount
Order NEW        -> trả 0
Order CANCELLED  -> trả 0

SUM các giá trị đó theo Customer.
```

Nếu JOIN tạo hàng rỗng cho Customer không có Order, CASE thường rơi vào ELSE 0, nhưng cần kiểm tra kết quả và semantics của provider. Có thể dùng COALESCE bên ngoài SUM nếu muốn biểu thức luôn trả BigDecimal 0 trong DTO.

### 20.3. Không dùng hai cách tùy tiện như thể luôn tương đương

`LEFT JOIN ... ON status=PAID + SUM` và `LEFT JOIN mọi Order + SUM(CASE...)` có thể cho cùng tổng PAID, nhưng **không cùng tập hàng đầu vào** cho COUNT, AVG hoặc các aggregate khác. Chọn cấu trúc dựa trên toàn bộ báo cáo.

---

## 21. EXISTS và subquery

Criteria API có thể diễn đạt “Customer có ít nhất một Order PAID” bằng `EXISTS`, tránh JOIN tạo nhiều hàng cho Customer có nhiều Order.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> c = cq.from(Customer.class);

jakarta.persistence.criteria.Subquery<Long> sq =
    cq.subquery(Long.class);

Root<PurchaseOrder> o =
    sq.from(PurchaseOrder.class);

sq.select(o.get("id"))
  .where(
      cb.equal(o.get("customer"), c),
      cb.equal(o.get("status"), OrderStatus.PAID)
  );

cq.select(c)
  .where(cb.exists(sq));
```

Để chọn Customer **không có** Order PAID:

```java
cq.where(cb.not(cb.exists(sq)));
```

`EXISTS` biểu diễn rõ “có hay không”, trong khi JOIN có thể làm lặp hàng. Hiệu năng thực tế phụ thuộc optimizer và index, nên vẫn cần kiểm tra query plan.

---

## 22. Collection predicates

CriteriaBuilder hỗ trợ điều kiện trên collection-valued associations.

### 22.1. Không có Order

```java
Predicate noOrders = cb.isEmpty(
    c.<List<PurchaseOrder>>get("orders")
);
```

### 22.2. Có Order

```java
Predicate hasOrders = cb.isNotEmpty(
    c.<List<PurchaseOrder>>get("orders")
);
```

### 22.3. Membership

`cb.isMember(element, collectionExpression)` kiểm tra một element có thuộc collection không, theo mapping của collection.

Nếu mục tiêu là tìm Order có ID xác định và xem nó thuộc Customer nào, truy vấn trên `PurchaseOrder.customer` thường rõ hơn việc dựng một entity tạm rồi kiểm tra member. Lưu ý entity identity, managed/detached state và tính hợp lệ của input.

---

## 23. Trả kết quả DTO bằng construct()

DTO:

```java
package demo.dto;

public record CustomerCard(
    Long id,
    String displayName,
    String statusLabel,
    Integer displayedPoints,
    String tier
) {}
```

Xây biểu thức:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<CustomerCard> cq =
    cb.createQuery(CustomerCard.class);

Root<Customer> c = cq.from(Customer.class);

Expression<String> displayName = cb.coalesce(
    cb.nullif(
        cb.trim(c.<String>get("nickname")),
        ""
    ),
    c.<String>get("fullName")
);

Expression<String> statusLabel =
    cb.<CustomerStatus, String>selectCase(
        c.<CustomerStatus>get("status")
    )
    .when(CustomerStatus.ACTIVE, "Hoạt động")
    .when(CustomerStatus.SUSPENDED, "Tạm khóa")
    .otherwise("Ngừng hoạt động");

Expression<Integer> points = cb.coalesce(
    c.<Integer>get("loyaltyPoints"),
    0
);

Expression<String> tier = cb.<String>selectCase()
    .when(cb.ge(points, 70), "GOLD")
    .when(cb.ge(points, 30), "SILVER")
    .otherwise("BRONZE");

cq.select(
    cb.construct(
        CustomerCard.class,
        c.get("id"),
        displayName,
        statusLabel,
        points,
        tier
    )
).orderBy(cb.asc(c.get("id")));

List<CustomerCard> cards =
    em.createQuery(cq).getResultList();
```

### 23.1. Vì sao DTO hữu ích?

- Chỉ lấy những cột cần thiết.
- Dùng giá trị tính toán mà không thêm field persistent giả.
- Không phụ thuộc trạng thái managed/detached sau khi service kết thúc.
- Giảm nguy cơ lazy loading ngoài transaction lúc serialize JSON.
- Kiểm soát schema của API response.

### 23.2. Constructor phải đúng kiểu

`cb.construct` cần constructor có đúng số lượng, thứ tự và type phù hợp:

```text
Long, String, String, Integer, String
```

Nếu expression có thể NULL, đừng dùng primitive không cho phép NULL ở vị trí tương ứng. Record public có canonical constructor; với provider/phiên bản JPA khác nhau cần kiểm tra tương thích constructor projection.

### 23.3. Điều kiện GROUP BY khi projection có aggregate

Nếu DTO còn thêm `SUM(o.totalAmount)`, CriteriaQuery cần `groupBy` theo các customer attributes chưa aggregate. Không dùng `construct` để bỏ qua quy tắc aggregation SQL.

---

## 24. Spring Data JPA Specification

Spring Data JPA cung cấp `Specification<T>`, dựa trên Criteria API để ghép điều kiện.

```java
import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {

    private CustomerSpecifications() {}

    public static Specification<Customer> hasStatus(
            CustomerStatus status) {

        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<Customer> minimumPoints(
            Integer minimum) {

        return (root, query, cb) ->
            minimum == null
                ? cb.conjunction()
                : cb.ge(
                    root.<Integer>get("loyaltyPoints"),
                    minimum
                );
    }
}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

Ghép:

```java
Specification<Customer> spec =
    CustomerSpecifications
        .hasStatus(CustomerStatus.ACTIVE)
        .and(CustomerSpecifications.minimumPoints(50));

List<Customer> customers =
    repository.findAll(spec);
```

`Specification` là API Spring Data, **không phải Jakarta Persistence Criteria API thuần**. Nó phù hợp với nhiều bộ lọc độc lập. Khi report cần complex JOIN ON, GROUP BY, HAVING, DTO và conditional aggregates, custom repository dùng CriteriaQuery trực tiếp có thể dễ kiểm soát hơn.

### 24.1. Không để các Specification thay đổi query ngoài ý muốn

Nếu một Specification tự đặt `fetch`, `distinct` hay `orderBy`, một Specification khác cũng thay đổi các phần đó, có thể sinh query khó dự đoán, nhất là count query trong pagination. Nên có ranh giới: filter specs tạo Predicate; repository/query layer điều khiển projection, join và sort khi use case phức tạp.

---

## 25. Static metamodel để tránh lỗi tên field

Cách viết string:

```java
c.get("loyaltyPoints")
```

dễ gõ nhưng lỗi chính tả chỉ phát hiện ở runtime.

Với JPA static metamodel đã được annotation processor sinh ra:

```java
Path<Integer> points =
    c.get(Customer_.loyaltyPoints);

Predicate enough = cb.ge(points, 50);
```

Lợi ích:

- Compiler nhận diện tên attribute generated.
- IDE hỗ trợ refactor tốt hơn.
- Type information rõ hơn.
- Giảm lỗi runtime do sai tên field.

Cần cấu hình annotation processor phù hợp với provider/build. Không giả định `Customer_` tồn tại chỉ vì đã thêm `@Entity`.

---

## 26. Tái sử dụng biểu thức đúng cách

Một lỗi thường gặp là giữ đối tượng `Predicate` hay `Expression` được xây với `Root` của query A rồi dùng trực tiếp trong query B.

```java
// Predicate được gắn với root của một query cụ thể.
Predicate active = cb.equal(
    rootA.get("status"),
    CustomerStatus.ACTIVE
);
```

Không đem nguyên `active` dùng với `rootB` của count query khác.

**Cách đúng:** tái sử dụng phương thức tạo biểu thức:

```java
private static Predicate activeCustomer(
        CriteriaBuilder cb,
        Root<Customer> root) {

    return cb.equal(
        root.get("status"),
        CustomerStatus.ACTIVE
    );
}
```

Dùng:

```java
dataQuery.where(activeCustomer(cb, dataRoot));
countQuery.where(activeCustomer(cb, countRoot));
```

Tái sử dụng **logic xây predicate**, không tái sử dụng object predicate gắn với root cũ.

---

## 27. Phân trang và count query

```java
TypedQuery<Customer> typed =
    em.createQuery(cq);

typed.setFirstResult(0);
typed.setMaxResults(20);

List<Customer> page =
    typed.getResultList();
```

Với danh sách phân trang, `ORDER BY` nên có khóa phụ ổn định như ID.

### 27.1. Count query riêng

```java
CriteriaQuery<Long> countCq =
    cb.createQuery(Long.class);

Root<Customer> countRoot =
    countCq.from(Customer.class);

countCq.select(cb.count(countRoot));

Long total =
    em.createQuery(countCq).getSingleResult();
```

Nếu cần cùng bộ lọc, tạo lại Predicate cho countRoot. Nếu JOIN nhiều Order khiến một Customer xuất hiện nhiều hàng, có thể cần `countDistinct(countRoot)` tùy ngữ nghĩa count; không đưa DISTINCT một cách máy móc khi không hiểu cardinality.

### 27.2. Fetch join collection và pagination

Dùng `root.fetch("orders", JoinType.LEFT)` cùng offset pagination có thể gây cảnh báo hoặc phân trang trong memory theo provider do một Customer xuất hiện nhiều hàng sau JOIN. Khi cần trang Customer và một collection của họ, cân nhắc query ID theo trang rồi fetch dữ liệu hoặc dùng DTO/projection phù hợp.

---

## 28. Hiệu năng của biểu thức

### 28.1. Hàm bọc cột có thể ảnh hưởng index

Giả sử có index:

```sql
CREATE INDEX idx_customers_points
ON customers(loyalty_points);
```

`WHERE COALESCE(points,0)>=:min` có thể khó tận dụng trực tiếp index trên cột hơn `WHERE points>=:min`, tùy optimizer.

Hai predicate này chỉ tương đương trong những điều kiện nhất định. Nếu min=30 thì NULL/0 đều không đạt; nếu min=0 thì `COALESCE(NULL,0)>=0` TRUE nhưng `NULL>=0` UNKNOWN. Không rewrite mà bỏ qua edge case.

### 28.2. LOWER và LIKE

`LOWER(full_name) LIKE '%an%'` có thể không dùng được index B-tree thông thường do function trên cột và wildcard đầu chuỗi. Khi dữ liệu lớn, thử collation, expression index hoặc full-text search phù hợp.

### 28.3. CASE trong ORDER BY

Sắp xếp theo rank CASE có thể yêu cầu sort một giá trị tính toán. Đừng đoán rằng index trên status sẽ tự phục vụ thứ tự CASE; xem SQL generated và query plan.

### 28.4. JOIN làm nhân số hàng

Nếu Customer có 5 Orders và 3 Addresses, join đồng thời hai collections có thể tạo tới 15 hàng cho Customer trước GROUP BY. SUM(amount) có thể bị nhân ba. Phải thiết kế query theo đúng cardinality, không giải quyết tùy tiện bằng DISTINCT.

### 28.5. Khi nào dùng native SQL?

Với báo cáo cực phức tạp cần window functions, vendor-specific aggregates, CTE hoặc function/index đặc thù, native SQL/view có thể phù hợp hơn. Đổi lại phải chấp nhận phụ thuộc database và kiểm soát mapping kết quả.

---

## 29. Tính portable và provider

Những điểm cần lưu ý:

- Hàm chuẩn `lower`, `trim`, `coalesce` portable hơn `function` tự đặt tên.
- DBMS có thể khác về chuỗi rỗng và NULL.
- Kiểu số của CASE, COALESCE, NULLIF cần tương thích.
- Quy tắc TRIM và collation Unicode khác nhau.
- `currentTimestamp()` với `LocalDateTime` cần kiểm tra kiểu/múi giờ.
- `groupBy` và `having` với biểu thức phức tạp có thể bị provider giới hạn.
- `Join.on` hoạt động theo mapping, không phải raw JOIN SQL tùy ý.
- Với Hibernate, HQL/Criteria extensions có thể vượt chuẩn JPA; không tự coi extension là portable.
- SQL được sinh từ Criteria vẫn có thể chứa subquery, JOIN, sort và aggregate tốn tài nguyên.

Khi dùng một function không chuẩn, hãy mô tả phụ thuộc và chạy integration test trên chính DB/provid­er/version dự kiến sử dụng.

---

## 30. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| `get("loyalty_points")` thay vì `get("loyaltyPoints")` | Sai attribute mapping | Dùng tên Java hoặc static metamodel |
| `equal(path, null)` | Không chắc là IS NULL | Dùng `isNull` |
| Đặt điều kiện child trong WHERE sau LEFT JOIN | Mất parent không có child | Đặt điều kiện JOIN trong `on` khi cần |
| CASE xếp nhánh mức thấp trước mức cao | Nhãn hạng sai | Xếp WHEN theo mức ưu tiên |
| Dùng simple CASE để thử WHEN NULL | Không TRUE theo SQL | Dùng `isNull` trong searched CASE |
| COALESCE nickname nhưng nickname trắng | Hiển thị trống | TRIM + NULLIF + COALESCE |
| CASE trộn String và Integer | Lỗi kiểu/runtime | Thống nhất type |
| SUM không có giá trị trả NULL | DTO không nhận được số mong muốn | COALESCE SUM với zero đúng kiểu |
| Join hai collections rồi SUM | Tổng bị nhân | Phân tích cardinality |
| Dùng Predicate query A cho query B | Criteria tree không hợp lệ | Build lại theo root |
| Dùng function name từ request | Rủi ro injection/lỗi DB | Whitelist function |
| Không escape LIKE wildcard | Kết quả quá rộng | Escape % và _ |
| Sort CASE mà không có khóa phụ | Phân trang không ổn định | Thêm ID |
| Dùng LocalDateTime không có chính sách timezone | Lọc ngày sai | Thiết kế quy ước thời gian |
| Nghĩ Criteria luôn nhanh hơn JPQL | Kế hoạch SQL vẫn có thể đắt | Đo SQL/EXPLAIN |
| Dùng COALESCE để “sửa” giá trị DB | Dữ liệu thực không đổi | Migration/update riêng |
| Fetch join collection rồi phân trang | Có thể phân trang sai/ở memory | Dùng query 2 bước/DTO |

---

## 31. Thực hành A — Bộ lọc động

Xây `CustomerFilter` gồm status, city, minPoints, nameContains.

1. Tạo `List<Predicate>`.
2. Chỉ thêm điều kiện khi field filter có giá trị.
3. Dùng AND để kết hợp.
4. Kiểm tra filter rỗng có trả mọi Customer không.
5. Thử `status=ACTIVE` và city Hà Nội/ Huế theo OR.
6. Thử LIKE với ký tự `%` và `_`.
7. Kiểm tra SQL query thực tế.
8. Bổ sung whitelist cho sort field.

## 32. Thực hành B — CASE và xử lý NULL

Dữ liệu điểm: 80, 60, 35, 0, NULL.

1. CASE với GOLD >=70, SILVER >=30, BRONZE còn lại.
2. Dự đoán NULL rơi vào nhánh nào.
3. Thêm `when(isNull(points), UNRATED)`.
4. Viết CASE tương đương dùng `coalesce(points,0)`.
5. Đảo thứ tự WHEN để quan sát sai khác.
6. Đưa tier vào DTO.
7. Sort tier ưu tiên và thêm ID làm khóa phụ.

## 33. Thực hành C — Tên hiển thị

Nickname:

```text
"An"
NULL
""
"   "
"  Chi  "
```

So sánh:

```java
cb.coalesce(nickname, fullName)
```

```java
cb.coalesce(cb.nullif(nickname, ""), fullName)
```

```java
cb.coalesce(
    cb.nullif(cb.trim(nickname), ""),
    fullName
)
```

Giải thích khác biệt giữa NULL, chuỗi rỗng và chuỗi dấu cách, và kiểm tra hành vi trên database thật.

## 34. Thực hành D — String functions

1. Tìm tên không phân biệt hoa/thường bằng `lower + like`.
2. Escape wildcard của input.
3. Dùng `length` lọc tên dài.
4. Dùng `substring` lấy ba ký tự đầu, chú ý vị trí bắt đầu từ 1.
5. Dùng `concat` tạo nhãn.
6. Dùng `trim` với nickname.
7. Kiểm tra SQL generated và ảnh hưởng index.

## 35. Thực hành E — LEFT JOIN và SUM

1. Persist Customer/Order mẫu.
2. Join `c.orders` bằng LEFT.
3. Đặt `OrderStatus.PAID` trong `Join.on`.
4. Group theo Customer ID/name.
5. Dùng `sum(totalAmount)` rồi `coalesce(..., BigDecimal.ZERO)`.
6. Kiểm tra khách không có Order PAID vẫn có tổng 0.
7. Đổi điều kiện từ ON sang WHERE, quan sát số Customer.
8. Thêm Order PAID và kiểm tra tổng.

## 36. Thực hành F — Conditional aggregation

Yêu cầu cùng lúc:

- COUNT tất cả Orders.
- COUNT Orders PAID.
- SUM paid total.

Thực hiện:

1. LEFT JOIN toàn bộ orders.
2. `COUNT(o)` cho tổng đơn.
3. `CASE WHEN status=PAID THEN 1 ELSE 0 END`.
4. `sumAsLong` cho paid count.
5. `CASE WHEN paid THEN amount ELSE 0 END`, rồi SUM.
6. So sánh với LEFT JOIN ON chỉ PAID.
7. Giải thích sự khác nhau của các tập hàng đầu vào.

## 37. Thực hành G — Date range

1. Tạo Order trong và ngoài tháng 11/2026.
2. Tạo `start=2026-11-01T00:00`.
3. Tạo `endExclusive=2026-12-01T00:00`.
4. Kết hợp `greaterThanOrEqualTo` và `lessThan`.
5. Thử Order đúng mốc đầu và đúng mốc cuối.
6. Giải thích ưu điểm của khoảng nửa mở.
7. Xem index và timezone của dữ liệu thực tế.

## 38. Thực hành H — DTO và phân trang

1. Tạo `CustomerCard`.
2. Kết hợp displayName, statusLabel, points và tier.
3. `cb.construct` trả DTO.
4. Sắp xếp theo CASE rank rồi ID.
5. Phân trang bằng `setFirstResult`/`setMaxResults`.
6. Tạo count CriteriaQuery khác, dựng lại predicates bằng countRoot.
7. Giải thích vì sao không dùng lại Predicate cũ.
8. So sánh với trả entity và serialize lazy graph.

## 39. Thực hành I — Static metamodel và function

1. Cấu hình annotation processor sinh `Customer_`.
2. Viết query dùng `Customer_.loyaltyPoints`.
3. Đổi tên field và quan sát compile-time check.
4. Với DB hỗ trợ `unaccent`, thử `cb.function`.
5. Kiểm tra function đã tồn tại và kiểu trả về.
6. Chạy EXPLAIN, ghi rõ phụ thuộc DB.
7. Tạo phiên bản portable nếu ứng dụng cần hỗ trợ nhiều DBMS.

## 40. Bài tập tổng hợp: dashboard khách hàng

Thiết kế một CriteriaQuery trả DTO với:

- ID và tên hiển thị bằng `trim+nullif+coalesce`.
- Nhãn trạng thái bằng simple CASE.
- Điểm hiển thị bằng COALESCE.
- Hạng bằng searched CASE.
- Tổng tiền PAID bằng LEFT JOIN ON + SUM + COALESCE.
- Chỉ lọc ACTIVE khi activeOnly=true.
- Chỉ lọc city nếu request có city.
- Giữ khách không có đơn PAID.
- Sắp xếp GOLD trước SILVER trước BRONZE, rồi theo ID.
- Phân trang với một count query riêng.
- Không nhân tổng tiền nếu có thêm nhiều association.

### Gợi ý

```text
CriteriaBuilder
    |
    +-- Root<Customer>
    |       |
    |       +-- LEFT JOIN orders
    |                  +-- ON status = PAID
    |
    +-- Expressions
    |       +-- displayName = COALESCE(NULLIF(TRIM(...), ''), fullName)
    |       +-- points = COALESCE(loyaltyPoints, 0)
    |       +-- tier = CASE points thresholds
    |       +-- statusLabel = CASE status
    |       +-- paidTotal = COALESCE(SUM(totalAmount), 0)
    |
    +-- Predicates
    |       +-- status nếu được yêu cầu
    |       +-- city nếu được yêu cầu
    |
    +-- GROUP BY customer attributes
    +-- construct(CustomerDashboardRow, ...)
    +-- ORDER BY tierPriority, id
    +-- TypedQuery pagination
```

Hãy giải thích: nếu thay ON bằng WHERE thì vì sao mất khách không có PAID? Nếu thêm một JOIN khác làm SUM tăng sai, nguyên nhân là gì? COALESCE points NULL thành 0 có cùng nghĩa nghiệp vụ với UNRATED không?

---

## 41. Câu hỏi ôn tập

1. `CriteriaBuilder` tạo những loại đối tượng nào?
2. `Expression<T>` khác `Predicate` ra sao?
3. `Root<T>` và `Path<T>` đóng vai trò gì?
4. `get("fieldName")` sử dụng tên cột DB hay attribute Java?
5. Vì sao `isNull` rõ nghĩa hơn `equal(path, null)`?
6. NULL kết hợp với phép so sánh thông thường cho kết quả gì?
7. `and` và `or` cần được nhóm thế nào khi có nhiều điều kiện?
8. `conjunction` và `disjunction` có giá trị logic gì?
9. Vì sao bộ lọc động không nên thêm predicate khi input không có giá trị?
10. Khi danh sách IN trống, có thể có hai semantics nghiệp vụ nào?
11. Searched CASE tạo bằng overload nào?
12. Simple CASE tạo bằng overload nào?
13. Vì sao thứ tự WHEN quan trọng?
14. Vì sao `CASE field WHEN NULL` không phải `IS NULL`?
15. `coalesce` chọn giá trị nào?
16. `nullif` trả NULL khi nào?
17. Vì sao COALESCE không xử lý nickname chỉ có dấu cách?
18. Công thức TRIM + NULLIF + COALESCE hoạt động theo thứ tự nào?
19. `coalesce(points,0)` có sửa field database không?
20. Khi nào phải giữ NULL points như trạng thái riêng?
21. Hàm `lower` có tự xóa dấu tiếng Việt không?
22. Vì sao cần escape wildcard trong LIKE?
23. `substring` bắt đầu từ index 0 hay 1?
24. `sum(x,y)` khác `sum(x)` thế nào?
25. `SUM` và `COUNT` có cùng kết quả khi không có giá trị không?
26. `LEFT JOIN` khác `INNER JOIN` ở trường hợp không có child nào?
27. Vì sao ON và WHERE ảnh hưởng kết quả LEFT JOIN?
28. `GROUP BY` và `HAVING` dùng khi nào?
29. `CASE` có thể dùng trong ORDER BY ra sao?
30. Vì sao thêm ID giúp phân trang ổn định?
31. `CriteriaBuilder.construct` yêu cầu điều gì từ DTO?
32. Vì sao không tái dùng Predicate từ dataRoot sang countRoot?
33. `Specification` là API của JPA hay Spring Data?
34. Static metamodel giúp phát hiện loại lỗi nào?
35. `function` có bảo đảm chạy trên mọi database không?
36. Vì sao không dùng raw function name từ input?
37. Nguyên nhân nào khiến SUM bị nhân khi join nhiều collections?
38. Vì sao `DISTINCT` không phải giải pháp tổng quát cho mọi SUM sai?
39. CASE/COALESCE đặt trên cột có thể ảnh hưởng index thế nào?
40. Khi nào nên chọn JPQL tĩnh, Criteria động hoặc native SQL?

---

## 42. Bảng ghi nhớ

| Mục tiêu | API |
|---|---|
| Bằng/khác | `equal`, `notEqual` |
| So sánh | `gt`, `ge`, `lt`, `le`, `greaterThan` |
| Khoảng giá trị | `between` |
| NULL | `isNull`, `isNotNull` |
| Tập giá trị | `in` |
| Chuỗi mẫu | `like`, `notLike` |
| Logic | `and`, `or`, `not` |
| Luôn TRUE/FALSE | `conjunction`, `disjunction` |
| CASE theo điều kiện | `selectCase()` |
| CASE theo giá trị | `selectCase(expression)` |
| Chọn fallback NULL | `coalesce` |
| Sentinel thành NULL | `nullif` |
| Hàm chuỗi | `lower`, `upper`, `trim`, `concat`, `substring`, `length` |
| Hàm số học | `sum`, `diff`, `prod`, `quot`, `mod`, `abs` |
| Aggregate | `count`, `sum`, `avg`, `min`, `max` |
| Hàm thời gian | `currentDate`, `currentTime`, `currentTimestamp` |
| Hàm DB riêng | `function` |
| JOIN có điều kiện | `Join.on` |
| Có row phù hợp | `exists` |
| Collection rỗng | `isEmpty`, `isNotEmpty` |
| Trả DTO | `construct` |
| Sắp xếp | `asc`, `desc` |
| Nhóm/lọc nhóm | `groupBy`, `having` |

### Sơ đồ cuối bài

```text
              CRITERIA BUILDER
                    |
        +-----------+-----------+
        |           |           |
     PREDICATE   EXPRESSION   FUNCTION
        |           |           |
    AND/OR/NOT     CASE       LOWER/TRIM
    EQUAL/LIKE     COALESCE   SUM/AVG
    IS NULL/IN     NULLIF     DATE/FUNCTION
        |           |           |
        +-----------+-----------+
                    |
                CriteriaQuery
               /      |      \
           SELECT    WHERE   ORDER BY
                \    GROUP BY   /
                 \   HAVING    /
                  \           /
                     TypedQuery
                         |
                     DATABASE
```

**Nguyên tắc trọng tâm:** Criteria API biểu diễn truy vấn dưới dạng **cây các biểu thức có kiểu**. Dùng `Predicate` cho điều kiện, `selectCase` cho quyết định theo nhánh, `coalesce` cho fallback NULL, `nullif` cho sentinel, và các hàm chuỗi/số/thời gian khi chúng thực sự phục vụ nghiệp vụ. Khi kết hợp với JOIN và aggregate, phải hiểu cách SQL tạo hàng, xử lý NULL và sử dụng index. Tiện ích xây query bằng Java không thay thế việc kiểm tra ngữ nghĩa và hiệu năng của SQL trên database thật.

