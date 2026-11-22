# Biểu diễn điều kiện bằng CASE, COALESCE và NULLIF

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** JPQL nâng cao

Khi viết truy vấn JPA, nhiều tình huống nghiệp vụ cần **tính ra một giá trị dựa trên điều kiện** ngay ở phía truy vấn: hiển thị tên ưu tiên, phân loại khách hàng theo điểm, hiển thị nhãn theo trạng thái đơn hàng, thay giá trị `NULL` bằng một mặc định, hoặc coi một chuỗi rỗng như dữ liệu chưa có.

JPQL (Jakarta Persistence Query Language) hỗ trợ ba nhóm biểu thức đặc biệt hữu ích:

- **`CASE`**: chọn kết quả theo một hoặc nhiều điều kiện.
- **`COALESCE`**: trả về biểu thức đầu tiên không phải `NULL`.
- **`NULLIF`**: trả về `NULL` nếu hai biểu thức bằng nhau, ngược lại trả về biểu thức thứ nhất.

Chúng giúp biểu đạt logic **phục vụ truy vấn** mà không bắt buộc tải toàn bộ entity rồi mới dùng `if/else` trong Java. Tuy nhiên, cần hiểu đúng **logic ba giá trị của SQL**, khả năng xử lý `NULL`, kiểu trả về, phép JOIN và các giới hạn khi chuyển JPQL sang SQL. Một biểu thức ngắn có thể làm kết quả không đúng hoặc làm index kém hiệu quả nếu đặt không phù hợp.

Bài này sử dụng các ví dụ thống nhất với `Customer` và `PurchaseOrder`, giải thích từ cú pháp đến cách dùng với `SELECT`, `WHERE`, `ORDER BY`, aggregate, DTO và Spring Data JPA.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Viết đúng **searched CASE**: `CASE WHEN ... THEN ... ELSE ... END`.
2. Viết đúng **simple CASE**: `CASE expression WHEN value THEN ... END`.
3. Phân biệt điều kiện theo thứ tự, nhánh `ELSE` và kết quả `NULL`.
4. Dùng `COALESCE` để chọn giá trị dự phòng có kiểu phù hợp.
5. Dùng `NULLIF` để biến một giá trị đặc biệt thành `NULL` khi so sánh bằng.
6. Kết hợp `TRIM`, `NULLIF` và `COALESCE` để chuẩn hóa dữ liệu hiển thị.
7. Giải thích `IS NULL`, `IS NOT NULL`, logic `TRUE/FALSE/UNKNOWN` và khác biệt giữa `NULL`, chuỗi trống và số không.
8. Đặt biểu thức điều kiện trong `SELECT`, `WHERE`, `ORDER BY`, `HAVING` và các câu truy vấn tổng hợp phù hợp.
9. Dùng `LEFT JOIN` để bảo toàn bản ghi không có association và tránh nhầm `NULL` do join.
10. Tạo DTO projection từ JPQL constructor expression có `CASE` hoặc `COALESCE`.
11. Dùng tham số truy vấn an toàn và kiểm soát kiểu của enum, số, chuỗi.
12. Đánh giá việc dùng biểu thức trong điều kiện lọc/sắp xếp ảnh hưởng ra sao tới index và query plan.
13. Nhận diện các khác biệt provider/database cần kiểm tra trước khi dùng trên production.

## 2. Bối cảnh nghiệp vụ xuyên suốt

Giả sử hệ thống bán hàng có hai entity:

```text
Customer
  id: Long
  fullName: String
  nickname: String?             (có thể NULL hoặc chuỗi trắng)
  phone: String?                (có thể NULL)
  loyaltyPoints: Integer?       (có thể NULL)
  status: CustomerStatus
  orders: List<PurchaseOrder>

PurchaseOrder
  id: Long
  customer: Customer
  status: OrderStatus
  totalAmount: BigDecimal
```

Một số yêu cầu:

- Hiển thị `nickname` nếu đã có, nếu không thì `fullName`.
- Nếu nickname chỉ có dấu cách, cũng coi như chưa có.
- Điểm loyalty chưa xác định được hiển thị bằng 0 **trong báo cáo**.
- Chuyển `CustomerStatus` thành nhãn dễ đọc.
- Phân loại khách hàng thành **GOLD**, **SILVER**, **BRONZE** theo ngưỡng điểm.
- Hiển thị tổng tiền của các đơn đã thanh toán; khách chưa có đơn thanh toán hiển thị 0.
- Ưu tiên sắp xếp khách hàng hoạt động lên trước.
- Biết sự khác nhau giữa **thiếu dữ liệu** và **giá trị 0 thật sự**.

Các biểu thức `CASE`, `COALESCE`, `NULLIF` giải quyết những yêu cầu này theo những cách khác nhau.

### 2.1. Dữ liệu mẫu

| Customer ID | fullName | nickname | phone | loyaltyPoints | status |
|---|---|---|---|---:|---|
| 1 | Nguyễn An | An | NULL | 80 | ACTIVE |
| 2 | Trần Bình | NULL | 0902000000 | NULL | SUSPENDED |
| 3 | Lê Chi | chuỗi gồm dấu cách | NULL | 0 | ACTIVE |
| 4 | Phạm Dung | NULL | NULL | 35 | INACTIVE |

Một số đơn hàng:

| Order ID | customer_id | status | totalAmount |
|---|---:|---|---:|
| 101 | 1 | PAID | 150.00 |
| 102 | 1 | NEW | 60.00 |
| 103 | 2 | CANCELLED | 90.00 |

Customer 3 và 4 chưa có đơn hàng. Chúng ta sẽ dùng dữ liệu này để dự đoán kết quả truy vấn. Các trạng thái được khai báo bằng Java enum; trong database, ví dụ dùng `EnumType.STRING`.

## 3. JPQL không phải SQL thuần

Ví dụ JPQL:

```jpql
SELECT c.fullName
FROM Customer c
WHERE c.status = :status
```

Trong đó:

- `Customer` là **tên entity JPA**, không phải tên bảng `customers`.
- `c.fullName` là **tên persistent attribute Java**, không phải cột `full_name`.
- `:status` là **named parameter**.
- JPA provider phân tích JPQL rồi tạo SQL theo mapping và SQL dialect.

SQL tương đương có thể gần như:

```sql
SELECT c.full_name
FROM customers c
WHERE c.customer_status = ?;
```

Với biểu thức điều kiện cũng vậy: viết theo cú pháp **JPQL**, không viết tên bảng/cột trực tiếp trừ khi dùng native SQL.

## 4. Mô hình entity để chạy ví dụ

### 4.1. Enum trạng thái

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

### 4.2. Customer

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

    @Column(name = "nickname", length = 80)
    private String nickname;

    @Column(name = "phone", length = 30)
    private String phone;

    @Column(name = "loyalty_points")
    private Integer loyaltyPoints;

    @Enumerated(EnumType.STRING)
    @Column(name = "customer_status", nullable = false, length = 20)
    private CustomerStatus status;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(String fullName, CustomerStatus status) {
        this.fullName = Objects.requireNonNull(fullName);
        this.status = Objects.requireNonNull(status);
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getNickname() {
        return nickname;
    }

    public String getPhone() {
        return phone;
    }

    public Integer getLoyaltyPoints() {
        return loyaltyPoints;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public void setPhone(String phone) {
        this.phone = phone;
    }

    public void setLoyaltyPoints(Integer points) {
        if (points != null && points < 0) {
            throw new IllegalArgumentException("Negative points");
        }
        this.loyaltyPoints = points;
    }
}
```

### 4.3. PurchaseOrder

```java
package demo.domain;

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
import jakarta.persistence.Table;

import java.math.BigDecimal;
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

    @Column(
        name = "total_amount",
        nullable = false,
        precision = 19,
        scale = 2
    )
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
        // JPA
    }

    public PurchaseOrder(
            Customer customer,
            OrderStatus status,
            BigDecimal totalAmount) {

        this.customer = Objects.requireNonNull(customer);
        this.status = Objects.requireNonNull(status);
        this.totalAmount = Objects.requireNonNull(totalAmount);

        if (totalAmount.signum() < 0) {
            throw new IllegalArgumentException(
                "Total amount cannot be negative");
        }
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Với quan hệ hai chiều, `PurchaseOrder.customer` là owning side của foreign key. Phần lớn ví dụ JPQL dưới đây chỉ đọc dữ liệu; chúng không phụ thuộc việc cascade persist/remove.

### 4.4. Schema minh họa

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    nickname VARCHAR(80),
    phone VARCHAR(30),
    loyalty_points INTEGER,
    customer_status VARCHAR(20) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(19, 2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

DDL mang tính minh họa cho một hệ quản trị quan hệ phù hợp. Production cần migration, constraint, index và cách lưu enum đúng với database thực tế.

---

## 5. Trước hết: hiểu NULL trong JPQL

`NULL` diễn đạt **không có giá trị được xác định**. Nó khác:

- Chuỗi rỗng `''`.
- Chuỗi chỉ gồm dấu cách `'   '`.
- Số 0.
- Boolean `false`.
- Một enum có giá trị đặc biệt như `UNKNOWN` được ứng dụng định nghĩa.

Trong SQL và JPQL, các phép so sánh có `NULL` thường tuân theo **logic ba giá trị**:

| Biểu thức | Kết quả về mặt logic |
|---|---|
| `5 = 5` | TRUE |
| `5 = 6` | FALSE |
| `5 = NULL` | UNKNOWN |
| `NULL = NULL` | UNKNOWN |
| `NULL <> 5` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `5 IS NOT NULL` | TRUE |

`UNKNOWN` không phải Java `false`, dù trong `WHERE` chỉ những hàng có predicate TRUE được giữ lại. Trong `CASE WHEN`, nhánh chỉ được chọn khi điều kiện TRUE; FALSE và UNKNOWN đều không kích hoạt nhánh đó.

### 5.1. Không so sánh NULL bằng dấu bằng

Sai:

```jpql
SELECT c
FROM Customer c
WHERE c.nickname = NULL
```

Đúng:

```jpql
SELECT c
FROM Customer c
WHERE c.nickname IS NULL
```

Tương tự, dùng `IS NOT NULL` thay vì `<> NULL`.

### 5.2. UNKNOWN ảnh hưởng đến CASE như thế nào?

Giả sử `loyaltyPoints` là NULL:

```jpql
CASE
    WHEN c.loyaltyPoints >= 50 THEN 'HIGH'
    ELSE 'OTHER'
END
```

Điều kiện `NULL >= 50` có kết quả UNKNOWN, nên nhánh `WHEN` **không chạy** và kết quả là `'OTHER'`.

Nếu nghiệp vụ cần phân biệt **chưa có điểm** với **điểm thấp**, phải viết nhánh `IS NULL` tường minh hoặc dùng `COALESCE` theo chính sách có chủ đích.

---

## 6. CASE dạng điều kiện: searched CASE

Searched CASE là cách diễn đạt gần với chuỗi `if / else if / else` trong Java:

```jpql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE default_result
END
```

JPA lần lượt xét các điều kiện. **Nhánh WHEN đầu tiên có điều kiện TRUE** quyết định giá trị trả về. Nếu không điều kiện nào TRUE thì dùng `ELSE`; khi không viết ELSE, kết quả mặc định là `NULL`.

### 6.1. Phân loại khách hàng theo điểm

```jpql
SELECT
    c.id,
    c.fullName,
    CASE
        WHEN c.loyaltyPoints >= :goldMin
            THEN 'GOLD'
        WHEN c.loyaltyPoints >= :silverMin
            THEN 'SILVER'
        ELSE 'BRONZE'
    END
FROM Customer c
ORDER BY c.id
```

Binding tham số:

```java
List<Object[]> rows = em.createQuery(
    "SELECT c.id, c.fullName, " +
    "CASE " +
    "  WHEN c.loyaltyPoints >= :goldMin THEN 'GOLD' " +
    "  WHEN c.loyaltyPoints >= :silverMin THEN 'SILVER' " +
    "  ELSE 'BRONZE' END " +
    "FROM Customer c ORDER BY c.id",
    Object[].class)
    .setParameter("goldMin", 70)
    .setParameter("silverMin", 30)
    .getResultList();

for (Object[] row : rows) {
    Long id = (Long) row[0];
    String name = (String) row[1];
    String tier = (String) row[2];

    System.out.println(id + " " + name + " " + tier);
}
```

Với dữ liệu mẫu:

| Customer | Điểm | Kết quả |
|---|---:|---|
| Nguyễn An | 80 | GOLD |
| Trần Bình | NULL | BRONZE |
| Lê Chi | 0 | BRONZE |
| Phạm Dung | 35 | SILVER |

Kết quả của Trần Bình rất đáng chú ý: `NULL` không được phân loại riêng mà rơi vào ELSE. Điều này **chỉ đúng nếu nghiệp vụ thực sự muốn coi “chưa có điểm” là BRONZE**.

### 6.2. Xử lý NULL tường minh trong CASE

Nếu muốn nhãn `UNRATED`:

```jpql
CASE
    WHEN c.loyaltyPoints IS NULL THEN 'UNRATED'
    WHEN c.loyaltyPoints >= :goldMin THEN 'GOLD'
    WHEN c.loyaltyPoints >= :silverMin THEN 'SILVER'
    ELSE 'BRONZE'
END
```

Khi đó Trần Bình có hạng `UNRATED` thay vì BRONZE.

### 6.3. Thứ tự WHEN quyết định kết quả

Sai logic:

```jpql
CASE
    WHEN c.loyaltyPoints >= 30 THEN 'SILVER'
    WHEN c.loyaltyPoints >= 70 THEN 'GOLD'
    ELSE 'BRONZE'
END
```

Khách hàng có 80 điểm sẽ vào `SILVER` ngay ở điều kiện đầu. Nhánh GOLD không còn cơ hội được chọn.

Đúng:

```jpql
CASE
    WHEN c.loyaltyPoints >= 70 THEN 'GOLD'
    WHEN c.loyaltyPoints >= 30 THEN 'SILVER'
    ELSE 'BRONZE'
END
```

**Searched CASE chọn nhánh phù hợp đầu tiên**, không tự chọn nhánh “cụ thể nhất”.

---

## 7. CASE dạng so khớp: simple CASE

Simple CASE dùng khi muốn so sánh **một biểu thức** với nhiều giá trị:

```jpql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ELSE default_result
END
```

Ví dụ chuyển trạng thái Customer sang nhãn hiển thị:

```jpql
SELECT
    c.fullName,
    CASE c.status
        WHEN :activeStatus THEN 'Đang hoạt động'
        WHEN :suspendedStatus THEN 'Tạm khóa'
        ELSE 'Không hoạt động'
    END
FROM Customer c
```

Java:

```java
List<Object[]> rows = em.createQuery(
    "SELECT c.fullName, " +
    "CASE c.status " +
    "  WHEN :active THEN 'Đang hoạt động' " +
    "  WHEN :suspended THEN 'Tạm khóa' " +
    "  ELSE 'Không hoạt động' END " +
    "FROM Customer c",
    Object[].class)
    .setParameter("active", CustomerStatus.ACTIVE)
    .setParameter("suspended", CustomerStatus.SUSPENDED)
    .getResultList();
```

`CustomerStatus.ACTIVE` và `CustomerStatus.SUSPENDED` là enum values. Dùng parameter binding giúp JPQL tách biệt giá trị enum với chuỗi người dùng nhập và tránh phụ thuộc cách ghi tên enum literal trong JPQL của provider.

### 7.1. Simple CASE và searched CASE khác nhau thế nào?

Hai biểu thức:

```jpql
CASE c.status
    WHEN :active THEN 'ACTIVE'
    ELSE 'OTHER'
END
```

và:

```jpql
CASE
    WHEN c.status = :active THEN 'ACTIVE'
    ELSE 'OTHER'
END
```

có ý nghĩa tương tự với trường hợp so sánh bằng một enum value.

Nhưng searched CASE linh hoạt hơn vì mỗi điều kiện có thể là một predicate khác:

```jpql
CASE
    WHEN c.status = :suspended THEN 'BLOCKED'
    WHEN c.loyaltyPoints >= :threshold THEN 'VIP'
    WHEN c.phone IS NULL THEN 'NO_PHONE'
    ELSE 'STANDARD'
END
```

Simple CASE chỉ thích hợp khi so sánh một biểu thức với những giá trị cần so khớp.

### 7.2. Simple CASE không dùng WHEN NULL để xét null

Không nên viết:

```jpql
CASE c.nickname
    WHEN NULL THEN c.fullName
    ELSE c.nickname
END
```

Vì `NULL = NULL` không trả TRUE, nhánh này không phải cách đáng tin cậy để nhận diện null.

Hãy dùng searched CASE:

```jpql
CASE
    WHEN c.nickname IS NULL THEN c.fullName
    ELSE c.nickname
END
```

Hoặc ngắn hơn: `COALESCE(c.nickname, c.fullName)`.

---

## 8. Nhánh ELSE và kết quả NULL

`ELSE` trong CASE có thể được bỏ qua:

```jpql
CASE
    WHEN c.status = :active THEN 'ENABLED'
END
```

Khi điều kiện không TRUE, kết quả là `NULL`.

Đôi khi đó là ý định hợp lệ, chẳng hạn dùng biểu thức như một nhãn chỉ xuất hiện ở một loại bản ghi. Nhưng nếu DTO hoặc Java code luôn kỳ vọng String không null, bỏ ELSE có thể gây lỗi hoặc hiển thị thiếu.

Một nguyên tắc đơn giản:

- Nếu mọi bản ghi phải có nhãn, dùng `ELSE` tường minh.
- Nếu `NULL` mang ý nghĩa “không áp dụng”, có thể bỏ ELSE, nhưng DTO phải cho phép null.
- Không đặt một giá trị mặc định ngẫu nhiên chỉ để tránh NULL nếu điều đó làm mất khác biệt nghiệp vụ.

### 8.1. CASE có thể trả giá trị số

```jpql
CASE
    WHEN c.status = :active THEN 0
    WHEN c.status = :suspended THEN 1
    ELSE 2
END
```

Biểu thức này trả một thứ hạng số, hữu ích cho sắp xếp.

### 8.2. CASE có thể trả chuỗi

```jpql
CASE
    WHEN c.phone IS NULL THEN 'Chưa cung cấp'
    ELSE c.phone
END
```

Các nhánh nên có kiểu kết quả tương thích. Không trộn một nhánh String với một nhánh Integer rồi kỳ vọng provider tự xử lý portable.

### 8.3. CASE lồng nhau

JPQL có thể biểu đạt một quyết định nhiều tầng:

```jpql
CASE
    WHEN c.status = :active THEN
        CASE
            WHEN c.loyaltyPoints >= :vipMin
                THEN 'ACTIVE_VIP'
            ELSE 'ACTIVE_REGULAR'
        END
    WHEN c.status = :suspended THEN 'SUSPENDED'
    ELSE 'INACTIVE'
END
```

CASE lồng nhau hợp lệ về mặt ý tưởng, nhưng nếu nhiều tầng làm truy vấn khó đọc, nên cân nhắc:

- Tách biểu thức thành các bước báo cáo.
- Thiết kế một projection DTO có thuộc tính đơn giản.
- Đưa business policy phức tạp vào domain service khi cần test/quản lý version.
- Tránh nhân bản công thức ở nhiều repository.

Không dùng JPQL CASE để thay thế toàn bộ business rules của hệ thống.

---

## 9. COALESCE: chọn giá trị đầu tiên không NULL

Cú pháp:

```jpql
COALESCE(expression_1, expression_2, ..., expression_n)
```

Kết quả là **biểu thức đầu tiên có giá trị khác `NULL`**. Nếu tất cả đều NULL, kết quả NULL.

Ví dụ:

```jpql
SELECT
    c.id,
    COALESCE(c.nickname, c.fullName)
FROM Customer c
ORDER BY c.id
```

Với dữ liệu mẫu:

| Customer | nickname | fullName | COALESCE |
|---|---|---|---|
| 1 | An | Nguyễn An | An |
| 2 | NULL | Trần Bình | Trần Bình |
| 3 | chuỗi dấu cách | Lê Chi | chuỗi dấu cách |
| 4 | NULL | Phạm Dung | Phạm Dung |

**COALESCE chỉ kiểm tra NULL, không kiểm tra nội dung có rỗng hoặc chỉ chứa dấu cách hay không.**

### 9.1. Nhiều mức fallback

```jpql
COALESCE(c.nickname, c.fullName, :unknownName)
```

Nó thử lần lượt:

1. `nickname` nếu không NULL.
2. Nếu nickname NULL, dùng `fullName` nếu không NULL.
3. Nếu cả hai NULL, dùng tham số `:unknownName`.

Với mapping hiện tại `fullName` không cho NULL, fallback thứ ba thường không được dùng nếu dữ liệu tuân thủ schema. Nhưng ví dụ cho thấy ý nghĩa của chuỗi fallback.

### 9.2. COALESCE với số

```jpql
SELECT
    c.fullName,
    COALESCE(c.loyaltyPoints, 0)
FROM Customer c
```

Nếu `loyaltyPoints` là NULL, kết quả của biểu thức là 0.

**Nhưng cần phân biệt tầng dữ liệu với tầng hiển thị:**

- `NULL` có thể nghĩa là **chưa xác định điểm**.
- 0 có thể nghĩa là **điểm đã xác định và bằng 0**.

Dùng `COALESCE(..., 0)` trong báo cáo có thể thuận tiện nhưng **không tự sửa dữ liệu gốc thành 0**, và có thể làm hai trạng thái nghiệp vụ trông giống nhau. Nếu cần phân biệt, dùng CASE hoặc thêm cột/field mô tả trạng thái.

### 9.3. COALESCE không giống OR

`COALESCE` chọn **giá trị**, không phải chọn predicate đúng đầu tiên. Nó không phải cú pháp tương đương cho một loạt điều kiện Boolean dùng `OR`.

Nếu muốn kiểm tra “có số điện thoại hoặc tên”, dùng predicate thích hợp:

```jpql
WHERE c.phone IS NOT NULL
   OR c.nickname IS NOT NULL
```

Không thay bằng `COALESCE(c.phone, c.nickname)` đứng trần trong WHERE rồi giả định nó là Boolean.

---

## 10. NULLIF: trả NULL khi hai biểu thức bằng nhau

Cú pháp:

```jpql
NULLIF(expression_1, expression_2)
```

Ngữ nghĩa:

- Nếu `expression_1 = expression_2` là TRUE, trả `NULL`.
- Ngược lại, trả giá trị `expression_1`.
- Kết quả có kiểu tương ứng với biểu thức thứ nhất theo khả năng tương thích của provider.

Ví dụ:

```jpql
SELECT
    c.fullName,
    NULLIF(c.nickname, '')
FROM Customer c
```

Với nickname `''`, biểu thức trả NULL. Với nickname `'An'`, trả `'An'`. Nếu nickname đầu vào đã NULL, kết quả cũng NULL.

### 10.1. NULLIF tương đương CASE nào?

Về ngữ nghĩa so sánh:

```jpql
NULLIF(c.nickname, '')
```

tương đương ý tưởng:

```jpql
CASE
    WHEN c.nickname = '' THEN NULL
    ELSE c.nickname
END
```

Nếu nickname NULL thì phép so sánh bằng chuỗi rỗng có kết quả UNKNOWN, nhánh ELSE trả chính nickname NULL.

### 10.2. NULLIF không có chức năng chọn fallback

`NULLIF` có thể **tạo ra NULL**, nhưng nó không tự chọn giá trị thay thế. Muốn có fallback, kết hợp với `COALESCE`:

```jpql
COALESCE(NULLIF(c.nickname, ''), c.fullName)
```

Ý nghĩa:

1. Nếu nickname bằng chuỗi rỗng, biến nó thành NULL.
2. Nếu nickname NULL sau bước đó, dùng fullName.

### 10.3. NULLIF với một mã đặc biệt

Giả sử dữ liệu cũ có `phone='N/A'`. Nếu nghiệp vụ coi `'N/A'` là không có số điện thoại:

```jpql
NULLIF(c.phone, :missingMarker)
```

Binding:

```java
.setParameter("missingMarker", "N/A")
```

Khi phone đúng bằng marker, biểu thức trả NULL. Đây là phép biến đổi trong kết quả query, **không cập nhật cột phone trong DB**.

---

## 11. Kết hợp TRIM, NULLIF và COALESCE để xử lý chuỗi trắng

Một công thức thực tế:

```jpql
COALESCE(
    NULLIF(TRIM(c.nickname), ''),
    c.fullName
)
```

Các bước:

1. `TRIM(c.nickname)` bỏ dấu cách đầu/cuối theo ngữ nghĩa TRIM của JPQL/database.
2. `NULLIF(..., '')` biến nickname rỗng sau trim thành NULL.
3. `COALESCE(..., c.fullName)` chọn fullName nếu nickname không có giá trị sử dụng được.

### 11.1. Kết quả với dữ liệu mẫu

| nickname | TRIM(nickname) | NULLIF(TRIM(...), '') | Kết quả cuối |
|---|---|---|---|
| `"An"` | `"An"` | `"An"` | An |
| NULL | NULL | NULL | fullName |
| `"   "` | `""` | NULL | fullName |
| `"  Binh  "` | `"Binh"` | `"Binh"` | Binh |

Công thức này chỉ giải quyết **dấu cách** theo quy tắc TRIM mặc định. Các trường hợp tab, newline, Unicode whitespace hoặc quy tắc chuẩn hóa tên riêng có thể cần xử lý khác ở application layer hoặc database.

### 11.2. Query hoàn chỉnh

```jpql
SELECT
    c.id,
    COALESCE(
        NULLIF(TRIM(c.nickname), ''),
        c.fullName
    )
FROM Customer c
ORDER BY c.id
```

Ứng dụng có thể dùng kết quả làm tên hiển thị mà không phải tự viết fallback ở từng màn hình.

### 11.3. Cẩn thận với database coi chuỗi rỗng như NULL

Một số DBMS có semantics riêng về chuỗi rỗng (ví dụ Oracle thường coi chuỗi rỗng trong cột VARCHAR2 như NULL). Khi chạy thực tế, nên kiểm tra kết quả `TRIM` và `NULLIF` trên database đang dùng, nhất là với dữ liệu legacy.

Không phải database nào cũng phân biệt `''` với `NULL` giống nhau ở tất cả kiểu cột.

---

## 12. Kết hợp CASE với COALESCE

Một yêu cầu điển hình: phân hạng theo điểm, nhưng NULL nghĩa là 0 **chỉ trong công thức phân hạng**.

```jpql
CASE
    WHEN COALESCE(c.loyaltyPoints, 0) >= :goldMin
        THEN 'GOLD'
    WHEN COALESCE(c.loyaltyPoints, 0) >= :silverMin
        THEN 'SILVER'
    ELSE 'BRONZE'
END
```

Không cần viết `IS NULL` riêng nếu nghiệp vụ đã quyết định NULL được xử lý như 0.

Ngược lại, nếu muốn phân biệt “chưa có điểm”:

```jpql
CASE
    WHEN c.loyaltyPoints IS NULL THEN 'UNRATED'
    WHEN c.loyaltyPoints >= :goldMin THEN 'GOLD'
    WHEN c.loyaltyPoints >= :silverMin THEN 'SILVER'
    ELSE 'BRONZE'
END
```

Hai câu query **không tương đương về nghiệp vụ**. Công thức đúng là công thức phản ánh rõ chính sách mong muốn.

### 12.1. Nên chọn cách nào?

| Nhu cầu | Gợi ý |
|---|---|
| Thiếu điểm được xem là 0 khi tính hạng | `COALESCE(points, 0)` |
| Thiếu điểm phải là trạng thái riêng | `CASE WHEN points IS NULL ...` |
| Chỉ muốn hiển thị 0 trong báo cáo | `SELECT COALESCE(points, 0)` |
| Cần sửa dữ liệu lưu trữ để hết NULL | Migration/update có kiểm soát, không chỉ COALESCE |
| Logic phân hạng phức tạp, thay đổi thường xuyên | Cân nhắc domain service/rule engine hoặc một policy được quản lý tập trung |

---

## 13. Dùng CASE trong SELECT

Một cách phổ biến là tính cột hiển thị thay vì trả toàn bộ entity.

```jpql
SELECT
    c.id,
    c.fullName,
    CASE
        WHEN c.status = :active THEN 'Hoạt động'
        WHEN c.status = :suspended THEN 'Tạm khóa'
        ELSE 'Không hoạt động'
    END
FROM Customer c
```

Nếu dùng `Object[]`, các vị trí lần lượt:

```text
row[0] -> Long ID
row[1] -> String fullName
row[2] -> String label được tính từ CASE
```

Dữ liệu do CASE tạo ra **không tự trở thành một persistent field** của entity. Nếu gọi `SELECT c` và c có entity mapping như trước, một CASE trong query khác không làm thêm cột `statusLabel` vào entity.

### 13.1. Dùng constructor expression thay Object[]

Để tránh cast theo vị trí, định nghĩa DTO:

```java
package demo.dto;

public record CustomerCard(
    Long id,
    String displayName,
    String statusLabel,
    Integer displayedPoints
) {}
```

JPQL:

```jpql
SELECT NEW demo.dto.CustomerCard(
    c.id,
    COALESCE(
        NULLIF(TRIM(c.nickname), ''),
        c.fullName
    ),
    CASE c.status
        WHEN :active THEN 'Hoạt động'
        WHEN :suspended THEN 'Tạm khóa'
        ELSE 'Không hoạt động'
    END,
    COALESCE(c.loyaltyPoints, 0)
)
FROM Customer c
ORDER BY c.id
```

Java:

```java
List<CustomerCard> cards = em.createQuery(
    """
    SELECT NEW demo.dto.CustomerCard(
        c.id,
        COALESCE(NULLIF(TRIM(c.nickname), ''), c.fullName),
        CASE c.status
            WHEN :active THEN 'Hoạt động'
            WHEN :suspended THEN 'Tạm khóa'
            ELSE 'Không hoạt động'
        END,
        COALESCE(c.loyaltyPoints, 0)
    )
    FROM Customer c
    ORDER BY c.id
    """,
    CustomerCard.class)
    .setParameter("active", CustomerStatus.ACTIVE)
    .setParameter("suspended", CustomerStatus.SUSPENDED)
    .getResultList();
```

Ví dụ dùng Java text block (Java 15+) và record (Java 16+); trên Java cũ có thể dùng String ghép và DTO class có constructor public tương ứng.

### 13.2. Điều kiện để constructor projection hoạt động

- Dùng tên class đầy đủ `demo.dto.CustomerCard` trong `NEW`.
- Class có constructor truy cập được với đúng số lượng và kiểu tham số.
- Type của CASE và COALESCE tương thích với kiểu constructor.
- Nếu một biểu thức có thể trả NULL, DTO nên dùng wrapper/reference type thay vì primitive không chấp nhận null.
- Provider cần hỗ trợ cú pháp/kiểu của constructor expression đúng phiên bản JPA/Jakarta Persistence đang dùng.

Record có canonical constructor public khi record public; nhưng nếu dùng provider/phiên bản cũ không tương thích, có thể thay bằng POJO DTO truyền thống.

---

## 14. Kiểu kết quả của CASE, COALESCE và NULLIF

JPQL là ngôn ngữ truy vấn có hệ thống kiểu. Không nên tạo các nhánh hoàn toàn không tương thích:

```jpql
CASE
    WHEN c.status = :active THEN 'ACTIVE'
    ELSE 0
END
```

Một nhánh String, một nhánh Integer dễ gây lỗi phân tích hoặc chuyển kiểu không portable.

Nên chọn cùng loại:

```jpql
CASE
    WHEN c.status = :active THEN 'ACTIVE'
    ELSE 'OTHER'
END
```

hoặc:

```jpql
CASE
    WHEN c.status = :active THEN 1
    ELSE 0
END
```

### 14.1. Số và BigDecimal

Giả sử Order có `totalAmount: BigDecimal`:

```jpql
COALESCE(o.totalAmount, :zeroAmount)
```

Java:

```java
.setParameter("zeroAmount", BigDecimal.ZERO)
```

Điều này giúp bảo toàn ý định dùng số thập phân. Không nhất thiết mọi provider/dialect sẽ xử lý giống nhau khi trộn literal Integer `0` với `BigDecimal`; nên ràng buộc tham số đúng kiểu cho biểu thức quan trọng.

### 14.2. NULLIF giữ ý nghĩa kiểu của biểu thức đầu

Ví dụ:

```jpql
NULLIF(o.totalAmount, :zeroAmount)
```

Trả giá trị số của `o.totalAmount` nếu khác zero, hoặc NULL nếu bằng zero. Không dùng một String parameter để so sánh với `BigDecimal` rồi mong tự chuyển kiểu đáng tin cậy.

### 14.3. Kiểu trả về aggregate

Khi `SUM` trên thuộc tính BigDecimal, kết quả thường là BigDecimal theo quy tắc JPQL aggregate. Khi `COUNT`, kiểu kết quả là Long. Nếu dùng các kết quả đó trong constructor projection, phải khai báo kiểu constructor phù hợp.

### 14.4. Literal NULL trong CASE

```jpql
CASE
    WHEN c.status = :active THEN c.phone
    ELSE NULL
END
```

Kết quả có thể NULL; DTO nên dùng `String` (reference type). Với các CASE số có ELSE NULL, không dùng primitive `int` trong constructor nếu có khả năng nhận NULL.

---

## 15. Dùng biểu thức trong WHERE

Trong `WHERE`, CASE, COALESCE hoặc NULLIF có thể tham gia một predicate.

### 15.1. Lọc theo điểm với NULL mặc định bằng 0

```jpql
SELECT c
FROM Customer c
WHERE COALESCE(c.loyaltyPoints, 0) >= :minimum
```

Nếu `minimum = 30`:

- Nguyễn An (80) được chọn.
- Phạm Dung (35) được chọn.
- Trần Bình (NULL → 0) không được chọn.
- Lê Chi (0) không được chọn.

### 15.2. Lọc khách có nickname dùng được

```jpql
SELECT c
FROM Customer c
WHERE NULLIF(TRIM(c.nickname), '') IS NOT NULL
```

Khách có nickname NULL, rỗng hoặc chỉ toàn dấu cách bị loại, theo semantics TRIM và database.

### 15.3. CASE trả số cho một phép so sánh

```jpql
SELECT c
FROM Customer c
WHERE
    CASE
        WHEN c.status = :active THEN
            COALESCE(c.loyaltyPoints, 0)
        ELSE 0
    END >= :threshold
```

Về nghiệp vụ, chỉ khách ACTIVE đạt ngưỡng điểm mới được chọn. Nhưng câu này **khó đọc hơn** một predicate Boolean tương đương:

```jpql
SELECT c
FROM Customer c
WHERE c.status = :active
  AND COALESCE(c.loyaltyPoints, 0) >= :threshold
```

Thường nên ưu tiên predicate Boolean trực tiếp cho `WHERE` vì dễ giải thích và có thể giúp optimizer hơn, thay vì đưa mọi điều kiện vào CASE.

### 15.4. CASE không phải predicate Boolean mặc định

Không nên viết một CASE trả String trong `WHERE`:

```jpql
WHERE CASE
    WHEN c.status = :active THEN 'YES'
    ELSE 'NO'
END
```

`WHERE` cần một điều kiện; một String không phải predicate. Có thể so sánh kết quả CASE với giá trị:

```jpql
WHERE (
    CASE
        WHEN c.status = :active THEN 'YES'
        ELSE 'NO'
    END
) = 'YES'
```

Nhưng đây thường là cách viết vòng vèo so với:

```jpql
WHERE c.status = :active
```

---

## 16. Dùng CASE trong ORDER BY

Một nhu cầu thực tế là sắp xếp theo thứ tự nghiệp vụ thay vì thứ tự alphabet.

Ví dụ trạng thái ưu tiên:

1. ACTIVE.
2. SUSPENDED.
3. INACTIVE.

```jpql
SELECT c
FROM Customer c
ORDER BY
    CASE
        WHEN c.status = :active THEN 0
        WHEN c.status = :suspended THEN 1
        ELSE 2
    END ASC,
    c.id ASC
```

Đây là sắp xếp theo **biểu thức hạng số**. Thêm `c.id ASC` làm khóa phụ để có thứ tự ổn định hơn khi nhiều Customer cùng hạng, rất quan trọng nếu có phân trang.

### 16.1. COALESCE trong ORDER BY

```jpql
SELECT c
FROM Customer c
ORDER BY COALESCE(c.loyaltyPoints, 0) DESC,
         c.id ASC
```

Khách chưa có điểm được xem như 0 trong thứ tự sắp xếp.

Nếu muốn NULL luôn đứng cuối mà không trộn với 0:

```jpql
SELECT c
FROM Customer c
ORDER BY
    CASE WHEN c.loyaltyPoints IS NULL THEN 1 ELSE 0 END,
    c.loyaltyPoints DESC,
    c.id ASC
```

Nhờ rank `0/1`, hàng có điểm thật được đặt trước hàng NULL; trong nhóm có điểm thật, thứ tự giảm dần.

### 16.2. Những lưu ý về ORDER BY

- Tên field JPQL là thuộc tính Java.
- Biểu thức sort có thể khiến DB phải tính giá trị cho nhiều hàng.
- Có trường hợp index trên cột gốc không được dùng trực tiếp để đáp ứng thứ tự tính toán.
- Hỗ trợ biểu thức phức tạp và cách sinh SQL phụ thuộc provider/dialect; nên thử query trên stack đang dùng.
- Khi phân trang, nên có tie-breaker như ID để tránh thứ tự thay đổi khó dự đoán giữa các trang.

---

## 17. CASE, COALESCE và aggregation

Biểu thức điều kiện đặc biệt hữu ích trong báo cáo, nhưng cần phân biệt `NULL` do không có hàng ghép với `NULL` từ dữ liệu cột.

### 17.1. SUM khi không có hàng phù hợp

Giả sử muốn tổng `totalAmount` của các đơn đã thanh toán, theo từng Customer. Một cách dùng JPQL association join với điều kiện ON:

```jpql
SELECT
    c.id,
    c.fullName,
    COALESCE(SUM(o.totalAmount), :zeroAmount)
FROM Customer c
LEFT JOIN c.orders o
    ON o.status = :paid
GROUP BY c.id, c.fullName
ORDER BY c.id
```

Binding:

```java
.setParameter("paid", OrderStatus.PAID)
.setParameter("zeroAmount", BigDecimal.ZERO)
```

Kết quả mong muốn:

| Customer | Đơn PAID | SUM trước COALESCE | Kết quả cuối |
|---|---|---|---:|
| Nguyễn An | 150.00 | 150.00 | 150.00 |
| Trần Bình | Không có | NULL | 0.00 |
| Lê Chi | Không có | NULL | 0.00 |
| Phạm Dung | Không có | NULL | 0.00 |

`SUM` trên tập giá trị rỗng/thực chất không có giá trị non-null thường trả NULL; `COALESCE` đưa về 0 cho mục đích báo cáo.

### 17.2. Tại sao dùng LEFT JOIN?

`LEFT JOIN` giữ Customer ngay cả khi không có đơn tương ứng:

```text
Customer ---- LEFT JOIN ---- PurchaseOrder
     |
     +-- Có order  -> lấy các hàng ghép
     |
     +-- Không order -> vẫn giữ Customer
                         cột phía Order có thể NULL
```

Nếu dùng `INNER JOIN`, Customer không có Order có thể biến mất khỏi kết quả hoàn toàn. `COALESCE(SUM(...), 0)` **không tự tạo lại những Customer đã bị INNER JOIN loại bỏ**.

### 17.3. Tại sao đặt điều kiện PAID trong ON thay vì WHERE?

So sánh:

```jpql
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
```

với:

```jpql
FROM Customer c
LEFT JOIN c.orders o
WHERE o.status = :paid
```

Trong cách thứ hai, khi không có Order PAID, `o.status` có thể NULL, điều kiện WHERE không TRUE, dẫn tới **loại bỏ Customer**. LEFT JOIN lúc ấy không còn bảo toàn nhóm khách không có đơn thanh toán như mong muốn.

Đây là một nguyên nhân phổ biến khiến báo cáo “tổng bằng 0” bỏ mất khách hàng.

### 17.4. COUNT khác SUM

`COUNT` thường trả `Long` và bằng 0 khi không có giá trị/hàng phù hợp trong nhóm. `SUM` có thể trả NULL khi không có giá trị phù hợp.

Vì thế:

```jpql
COUNT(o)
```

không cần `COALESCE(..., 0)` chỉ để xử lý “nhóm có 0 order” nếu nhóm Customer vẫn tồn tại do LEFT JOIN. Nhưng khi nhóm đã bị loại bởi WHERE/INNER JOIN thì cả COUNT và COALESCE đều không thể trả ra nhóm đó.

---

## 18. CASE với kết quả aggregate

Một ví dụ phân loại khách hàng theo số đơn:

```jpql
SELECT
    c.id,
    c.fullName,
    CASE
        WHEN COUNT(o) = 0 THEN 'NO_ORDERS'
        WHEN COUNT(o) >= :frequentMin THEN 'FREQUENT'
        ELSE 'OCCASIONAL'
    END
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id, c.fullName
ORDER BY c.id
```

Kết quả với `frequentMin = 2`:

- Nguyễn An có hai đơn → `FREQUENT`.
- Trần Bình có một đơn → `OCCASIONAL`.
- Lê Chi không có đơn → `NO_ORDERS`.
- Phạm Dung không có đơn → `NO_ORDERS`.

### 18.1. Aggregate trước, CASE sau

`COUNT(o)` tính số order của nhóm, CASE sử dụng kết quả đó để chọn nhãn.

Không phải cùng một công thức với “đếm số đơn PAID”. Muốn đếm chỉ đơn PAID, hãy đặt điều kiện phù hợp ở JOIN hoặc dùng một truy vấn khác thể hiện rõ loại đơn nào được đếm.

### 18.2. Biểu thức trong GROUP BY và tính portable

JPQL yêu cầu các biểu thức chọn ngoài aggregate được group hợp lệ. Trong ví dụ, `c.id` và `c.fullName` xuất hiện ở `GROUP BY` để query portable và rõ ý nghĩa.

Một số SQL dialect cho phép group theo biểu thức phức tạp, alias hoặc chỉ primary key dựa trên functional dependency; nhưng JPQL và provider có những giới hạn riêng. **Không mặc định** mọi biểu thức CASE/COALESCE đều được phép viết trực tiếp trong `GROUP BY` hoặc dùng alias SELECT ở đó trên mọi JPA provider.

Nếu cần report group theo “hạng điểm” tính bằng CASE, đôi khi giải pháp dễ quản lý hơn là:

- Query các thành phần cần thiết và group ở application với tập dữ liệu đủ nhỏ.
- Dùng native SQL hoặc view khi report nặng/cần cú pháp DB cụ thể.
- Thiết kế field hạng lưu riêng nếu dữ liệu cần index và có lifecycle cập nhật rõ.
- Thử query JPQL trên provider trước khi quyết định hỗ trợ.

---

## 19. Dùng CASE hoặc COALESCE trong HAVING

`HAVING` lọc **nhóm sau aggregation**, khác `WHERE` lọc từng hàng trước aggregation.

Ví dụ lấy Customer có tổng tiền PAID đủ ngưỡng:

```jpql
SELECT
    c.id,
    c.fullName,
    COALESCE(SUM(o.totalAmount), :zeroAmount)
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
GROUP BY c.id, c.fullName
HAVING COALESCE(SUM(o.totalAmount), :zeroAmount)
       >= :minimumTotal
```

Binding:

```java
.setParameter("paid", OrderStatus.PAID)
.setParameter("zeroAmount", BigDecimal.ZERO)
.setParameter("minimumTotal", new BigDecimal("100.00"))
```

Một biểu thức CASE cũng có thể dựa vào kết quả aggregate trong SELECT/HAVING theo những gì JPQL provider hỗ trợ. Tuy nhiên, nếu chỉ cần điều kiện “tổng >= ngưỡng”, so sánh aggregate trực tiếp như trên dễ đọc hơn so với thêm CASE không cần thiết.

### 19.1. WHERE và HAVING khác nhau

| Vị trí | Thời điểm logic | Ví dụ |
|---|---|---|
| WHERE | Lọc hàng trước khi group | `WHERE c.status = :active` |
| JOIN ON | Hạn chế hàng ghép theo điều kiện join | `LEFT JOIN c.orders o ON o.status = :paid` |
| HAVING | Lọc nhóm sau khi aggregate | `HAVING SUM(o.totalAmount) >= :min` |

Không đặt điều kiện lên Order trong WHERE khi muốn giữ những Customer không có Order phù hợp, trừ khi đã phân tích semantics mong muốn.

---

## 20. NULLIF trong công thức số

Một cách dùng `NULLIF` là coi một giá trị số đặc biệt là “không thể dùng làm mẫu số”.

Giả sử một entity báo cáo có:

```text
totalAmount: BigDecimal
discountAmount: BigDecimal
```

Tỷ lệ giảm giá thường là:

```text
discountAmount / totalAmount
```

Nhưng với `totalAmount = 0`, phép chia có thể lỗi hoặc trả kết quả không phù hợp.

Biểu thức minh họa:

```jpql
o.discountAmount / NULLIF(o.totalAmount, :zeroAmount)
```

Nếu mẫu số bằng 0, `NULLIF` trả NULL, từ đó phép tính có thể trả NULL theo semantics số học của database thay vì chia cho zero.

**Lưu ý tính portable:** phép chia số thập phân, kiểu kết quả, độ chính xác và cách database xử lý biểu thức chứa NULL có thể khác nhau. Cần thử với dialect thật, đặc biệt trong báo cáo tài chính. Trong ví dụ entity trước đó chưa có field `discountAmount`; đoạn này mô tả một mapping mở rộng giả định.

Nếu chỉ muốn diễn đạt kết quả bằng CASE:

```jpql
CASE
    WHEN o.totalAmount = :zeroAmount THEN NULL
    ELSE o.discountAmount / o.totalAmount
END
```

Nhưng không dùng CASE như cơ chế chắc chắn để tránh mọi lỗi đánh giá sớm trên mọi DBMS; cách optimizer xử lý biểu thức có thể khác nhau. Với nghiệp vụ quan trọng, dùng validation dữ liệu đầu vào và công thức được kiểm thử trên DB thật.

### 20.1. NULLIF với một giá trị “sentinel”

Ngoài 0, NULLIF có thể đổi những giá trị quy ước như `'N/A'`, `'-'` hoặc `'UNKNOWN'` thành NULL trong projection.

Tuy nhiên, nếu sentinel tồn tại trong database do legacy design, giải pháp dài hạn có thể là migration và constraint đúng, không chỉ bọc mọi query bằng NULLIF mãi mãi.

---

## 21. Kết hợp biểu thức trong một báo cáo tổng hợp

Giả sử muốn danh sách Customer với:

- ID.
- Tên hiển thị đã chuẩn hóa.
- Nhãn trạng thái.
- Điểm hiển thị.
- Tổng tiền các đơn PAID.

Định nghĩa DTO:

```java
package demo.dto;

import java.math.BigDecimal;

public record CustomerSummary(
    Long id,
    String displayName,
    String statusLabel,
    Integer displayedPoints,
    BigDecimal paidTotal
) {}
```

JPQL:

```jpql
SELECT NEW demo.dto.CustomerSummary(
    c.id,
    COALESCE(
        NULLIF(TRIM(c.nickname), ''),
        c.fullName
    ),
    CASE c.status
        WHEN :active THEN 'Hoạt động'
        WHEN :suspended THEN 'Tạm khóa'
        ELSE 'Không hoạt động'
    END,
    COALESCE(c.loyaltyPoints, 0),
    COALESCE(SUM(o.totalAmount), :zeroAmount)
)
FROM Customer c
LEFT JOIN c.orders o
    ON o.status = :paid
GROUP BY
    c.id,
    c.fullName,
    c.nickname,
    c.status,
    c.loyaltyPoints
ORDER BY c.id
```

Ở đây:

1. `NULLIF(TRIM(...), '')` xử lý nickname trắng.
2. `COALESCE` chọn tên hiển thị.
3. `CASE` đổi enum sang nhãn.
4. `COALESCE(loyaltyPoints, 0)` cho điểm mặc định trong DTO.
5. `LEFT JOIN ... ON ...` bảo toàn Customer không có đơn PAID.
6. `COALESCE(SUM(...), zeroAmount)` cho tổng PAID bằng 0 trong DTO.
7. `GROUP BY` liệt kê các thuộc tính Customer ngoài aggregate được dùng trong projection.

### 21.1. Vì sao không GROUP BY ngay nickname đã COALESCE?

Một số provider/DBMS cho phép group theo biểu thức phức tạp hoặc alias; nhưng cách portable hơn trong JPQL là group theo các state-valued path expressions tương ứng, sau đó dùng biểu thức tính toán trong SELECT. Đối với báo cáo phức tạp, luôn kiểm tra JPQL trên phiên bản provider dự kiến triển khai.

### 21.2. Có bị nhân số hàng do JOIN không?

Mỗi Customer có thể có nhiều Order; SQL JOIN sẽ tạo nhiều hàng trước aggregation. Vì vậy:

- Không chọn các cột Order không nằm trong aggregate hoặc GROUP BY nếu chúng làm thay đổi hạt dữ liệu của báo cáo.
- Phân biệt tổng theo toàn bộ order với tổng chỉ PAID.
- Nếu join thêm một collection khác (ví dụ Customer có nhiều Address), có thể tạo phép nhân hàng, khiến `SUM` bị tính lặp.
- Không xử lý bằng `DISTINCT` một cách máy móc; cần thiết kế query theo đúng mức dữ liệu muốn group.

Đây là một vấn đề độc lập với CASE/COALESCE, nhưng rất quan trọng khi các biểu thức được đưa vào report.

---

## 22. Spring Data JPA với @Query

Trong Spring Data JPA, có thể khai báo query và DTO projection trực tiếp ở repository.

```java
package demo.repository;

import demo.domain.Customer;
import demo.domain.CustomerStatus;
import demo.dto.CustomerCard;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        SELECT NEW demo.dto.CustomerCard(
            c.id,
            COALESCE(NULLIF(TRIM(c.nickname), ''), c.fullName),
            CASE c.status
                WHEN :active THEN 'Hoạt động'
                WHEN :suspended THEN 'Tạm khóa'
                ELSE 'Không hoạt động'
            END,
            COALESCE(c.loyaltyPoints, 0)
        )
        FROM Customer c
        ORDER BY c.id
        """)
    List<CustomerCard> findCustomerCards(
        @Param("active") CustomerStatus active,
        @Param("suspended") CustomerStatus suspended
    );
}
```

Gọi từ service:

```java
@Service
public class CustomerQueryService {

    private final CustomerRepository repository;

    public CustomerQueryService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<CustomerCard> listCards() {
        return repository.findCustomerCards(
            CustomerStatus.ACTIVE,
            CustomerStatus.SUSPENDED
        );
    }
}
```

Các import Spring `@Service` và `@Transactional` được bỏ khỏi snippet service cho gọn; class cần import `org.springframework.stereotype.Service` và `org.springframework.transaction.annotation.Transactional` khi chạy.

### 22.1. Tại sao DTO phù hợp với biểu thức tính toán?

Nếu API chỉ cần những field hiển thị, DTO tránh:

- Trả entity managed ra khỏi transaction.
- Lazy loading ngoài ý muốn khi serialize.
- Tính đi tính lại fallback ở nhiều tầng.
- Tải các association không cần cho danh sách.
- Ràng buộc response schema trực tiếp với entity schema.

Tuy nhiên, logic tính ở JPQL không tự biến thành một business invariant. Nếu hệ thống cần cùng một quy tắc ở nơi khác, hãy quản lý định nghĩa policy nhất quán.

### 22.2. Named parameter thay vì ghép chuỗi

Tốt:

```java
.setParameter("active", CustomerStatus.ACTIVE)
.setParameter("minimum", 30)
```

Không nối input người dùng trực tiếp vào JPQL:

```java
String jpql = "SELECT c FROM Customer c WHERE c.fullName = '"
    + userInput + "'";
```

Ghép chuỗi làm tăng nguy cơ JPQL injection, lỗi dấu nháy và mất khả năng tái sử dụng query plan. Hãy dùng bound parameters, bao gồm với giá trị so sánh trong CASE và NULLIF.

---

## 23. Hiệu năng: biểu thức có thể làm index khó dùng hơn

Giả sử bảng `customers` có index:

```sql
CREATE INDEX idx_customers_loyalty
ON customers (loyalty_points);
```

Query:

```jpql
WHERE COALESCE(c.loyaltyPoints, 0) >= :min
```

có thể khiến database phải tính biểu thức trên cột trước khi so sánh, thay vì dùng trực tiếp index trên cột theo cách tối ưu. Một số DBMS có function-based/expression index hoặc optimizer rewrite, nhưng đó là hành vi DB-specific.

### 23.1. Có thể viết lại predicate

Nếu `:min` luôn dương và NULL được coi như 0, thì:

```jpql
WHERE c.loyaltyPoints >= :min
```

cho cùng tập kết quả về mặt chọn hàng: giá trị NULL không thỏa điều kiện, 0 cũng không đạt ngưỡng dương.

Nếu `:min = 0`, hai biểu thức không còn giống nhau:

- `COALESCE(NULL, 0) >= 0` là TRUE.
- `NULL >= 0` là UNKNOWN, row bị loại.

Vì vậy không thể bỏ COALESCE mà không chứng minh điều kiện biên.

Một cách viết minh bạch nếu muốn cả NULL được xem như 0 cho ngưỡng không âm:

```jpql
WHERE c.loyaltyPoints >= :min
   OR (c.loyaltyPoints IS NULL AND :min <= 0)
```

Cách nào nhanh hơn còn phụ thuộc dữ liệu, index, kế hoạch thực thi và loại tham số. Cần benchmark chứ không có quy tắc “OR luôn tốt hơn COALESCE”.

### 23.2. CASE trong ORDER BY có thể cần sort

```jpql
ORDER BY
    CASE
        WHEN c.status = :active THEN 0
        ELSE 1
    END,
    c.id
```

Sắp xếp theo rank tính toán có thể khiến DB không dùng trực tiếp index đơn giản trên `customer_status` cho toàn bộ thứ tự. Với query lớn, cần xem `EXPLAIN` và cân nhắc index biểu thức hoặc cột rank có chiến lược cập nhật rõ nếu workload đòi hỏi.

### 23.3. Lặp công thức trong nhiều nơi

Nếu cùng `CASE` xuất hiện trong SELECT, ORDER BY, HAVING và nhiều endpoint:

- Truy vấn khó đọc/khó bảo trì.
- Business policy thay đổi dễ gây lệch giữa endpoint.
- Nhà phát triển có thể quên cập nhật một nơi.
- Optimizer có thể xử lý biểu thức lặp theo cách khác nhau.

Cân nhắc xây query builder/repository abstraction, materialized/reporting view, hoặc đưa policy sang service nếu dữ liệu nhỏ và không cần lọc/sắp xếp ở database.

Không tạo cột computed/index một cách tự động cho mọi CASE: hãy đo xem truy vấn thực sự là bottleneck.

---

## 24. Giới hạn portable của JPQL và provider

Các hàm `CASE`, `COALESCE`, `NULLIF` thuộc phần cú pháp điều kiện của JPQL. Tuy nhiên, khi kết hợp với những vị trí phức tạp, database và JPA provider có thể tạo ra khác biệt:

- **Kiểu literal:** Integer, Long, BigDecimal, String, enum cần tương thích.
- **Enum mapping:** cách so sánh parameter/literal khác giữa mapping STRING và ORDINAL.
- **NULL và chuỗi rỗng:** Oracle và một số database có hành vi đáng chú ý.
- **TRIM/chuỗi Unicode:** không tự chuẩn hóa mọi whitespace/diacritics.
- **ORDER BY expressions:** khả năng đẩy sort xuống DB và hỗ trợ vị trí/alias khác nhau.
- **GROUP BY expressions:** cú pháp hợp lệ trên một database không mặc nhiên là JPQL portable.
- **Nested CASE trong aggregate:** provider có thể hỗ trợ khác nhau, nhất là khi aggregate nhận biểu thức phức tạp.
- **HQL riêng của Hibernate:** có những extension không phải cú pháp JPA chuẩn.
- **Native SQL functions:** chỉ dùng nếu đã quyết định chấp nhận phụ thuộc dialect.
- **Parameter inference:** COALESCE với nhiều kiểu khác nhau hoặc NULL parameter có thể gây lỗi type inference.

**Nguyên tắc:** viết JPQL với entity attributes, các giá trị tương thích và cấu trúc chuẩn trước. Khi yêu cầu query vượt khả năng portable, hãy dùng extension/native SQL có chủ đích, ghi rõ phụ thuộc và kiểm thử trên database triển khai.

---

## 25. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `CASE` cho kết quả không mong muốn khi field NULL | Predicate có NULL trả UNKNOWN | Dùng `IS NULL` hoặc COALESCE có chủ đích |
| Khách có 80 điểm thành SILVER thay vì GOLD | WHEN ít nghiêm ngặt đứng trước | Sắp xếp điều kiện từ ưu tiên cao xuống |
| `CASE nickname WHEN NULL` không hoạt động | Simple CASE không dùng so sánh NULL đúng cách | Dùng searched CASE với `IS NULL` |
| COALESCE trả chuỗi gồm dấu cách | Chuỗi trắng khác NULL | `NULLIF(TRIM(...), '')` |
| Query thiếu khách không có đơn | INNER JOIN hoặc WHERE trên phía LEFT JOIN | Dùng LEFT JOIN và ON đúng chỗ |
| Tổng doanh thu trả NULL | SUM không có giá trị | `COALESCE(SUM(...), zeroAmount)` |
| Dùng COALESCE nhưng Customer vẫn biến mất | Hàng bị loại bởi JOIN/WHERE | Phân tích cardinality trước khi fallback |
| DTO constructor lỗi | Số/kiểu tham số không khớp | Khớp Long/Integer/BigDecimal/String, xử lý NULL |
| CASE trả String ở một nhánh, số ở nhánh khác | Type không tương thích | Dùng cùng kiểu kết quả |
| Truy vấn lọc chậm | Hàm bọc cột làm giảm sử dụng index | Kiểm tra EXPLAIN, cân nhắc rewrite/index |
| JPQL báo unknown column | Dùng tên cột SQL trong JPQL | Dùng attribute Java và entity name |
| GROUP BY lỗi | Chọn thuộc tính không aggregate và không group hợp lệ | Group theo state-valued paths tương ứng |
| COUNT trả 0 còn SUM trả NULL | Semantics aggregate khác nhau | Dùng fallback đúng trên SUM |
| NULLIF không ghi NULL xuống DB | NULLIF chỉ là biểu thức query | Muốn sửa dữ liệu phải update/migrate |
| Dùng query nối chuỗi input | Injection/cú pháp lỗi | Named parameters |
| Sort phân trang thiếu ổn định | Nhiều hàng cùng rank CASE | Thêm khóa phụ như c.id |
| Kết quả sai khi tên không có dấu cách chuẩn | TRIM không xử lý mọi whitespace | Thiết kế chuẩn hóa đầu vào |
| Query chạy ở Hibernate nhưng lỗi ở provider khác | Dùng extension ngoài JPQL portable | Kiểm tra spec, đổi query hoặc ghi rõ phụ thuộc |

### 25.1. CASE không thay thế validation dữ liệu

Một query `COALESCE(loyaltyPoints, 0)` không khiến cột `loyalty_points` luôn hợp lệ. Nếu domain cấm điểm âm, vẫn cần validation và constraint thích hợp.

### 25.2. Không dùng CASE để cố ép những type không tương thích

`CASE WHEN ... THEN c.fullName ELSE c.loyaltyPoints END` không có kiểu kết quả rõ ràng, dễ lỗi ngay khi provider phân tích hoặc DB thực thi. Nếu cần hai loại dữ liệu, trả hai cột hoặc chuyển đổi có chủ đích ở application/DB theo công nghệ đã chọn.

### 25.3. Không giả định tất cả trường hợp NULL đều giống nhau

`COALESCE(phone, 'Chưa có')` có nghĩa thay thế NULL trong **kết quả**, không có nghĩa số điện thoại thiếu đã được cập nhật vào database. Đừng dùng kết quả projection đó để ghi ngược lên entity mà không phân biệt giá trị gốc.

---

## 26. Thực hành A — CASE phân loại khách hàng

1. Tạo `Customer` và dữ liệu mẫu trong phần 2.
2. Query `CASE WHEN points >= 70 THEN GOLD ...`.
3. Ghi kết quả cho 80, 35, 0, NULL.
4. Đảo ngược thứ tự WHEN để xem tác động.
5. Bổ sung `WHEN points IS NULL THEN 'UNRATED'`.
6. So sánh với `COALESCE(points, 0)`.
7. Giải thích vì sao UNRATED và BRONZE không luôn có cùng ý nghĩa.

**Bảng ghi kết quả:**

| Điểm | CASE không xử lý NULL riêng | CASE có nhánh IS NULL |
|---:|---|---|
| 80 | GOLD | GOLD |
| 35 | SILVER | SILVER |
| 0 | BRONZE | BRONZE |
| NULL | BRONZE | UNRATED |

## 27. Thực hành B — Simple CASE với enum

1. Tạo các trạng thái ACTIVE, SUSPENDED, INACTIVE.
2. Viết `CASE c.status WHEN :active ...`.
3. Binding enum parameters đúng type.
4. Đọc kết quả nhãn cho từng trạng thái.
5. Viết biểu thức tương đương bằng searched CASE.
6. Thử một field nullable trong simple CASE và xem vì sao `WHEN NULL` không thay thế `IS NULL`.

## 28. Thực hành C — Tên hiển thị

Tạo nickname:

```text
"An"
NULL
""
"   "
"  Chi  "
```

So sánh ba công thức:

```jpql
COALESCE(c.nickname, c.fullName)
```

```jpql
COALESCE(NULLIF(c.nickname, ''), c.fullName)
```

```jpql
COALESCE(NULLIF(TRIM(c.nickname), ''), c.fullName)
```

Yêu cầu:

1. Dự đoán kết quả từng trường hợp.
2. Chạy query và đối chiếu.
3. Xác định công thức nào xử lý được chuỗi dấu cách.
4. Kiểm tra cách database được chọn xử lý chuỗi rỗng.
5. Giải thích vì sao COALESCE một mình chưa đủ cho blank nickname.

## 29. Thực hành D — WHERE và chỉ số

1. Tạo index trên `customers.loyalty_points`.
2. Dùng `WHERE COALESCE(c.loyaltyPoints, 0) >= :min`.
3. So sánh với `WHERE c.loyaltyPoints >= :min` khi min = 30.
4. So sánh khi min = 0.
5. Kiểm tra bản ghi NULL.
6. Chạy `EXPLAIN` cho SQL do JPA provider phát.
7. Ghi lại row count và cách dùng index, không suy đoán từ cú pháp.

## 30. Thực hành E — Tổng tiền PAID và LEFT JOIN

1. Tạo khách có nhiều loại Order: PAID, NEW, CANCELLED.
2. Tạo thêm khách không có Order.
3. Chạy `LEFT JOIN c.orders o ON o.status = :paid`.
4. Group theo `c.id, c.fullName`.
5. Query `SUM(o.totalAmount)` và ghi kết quả NULL.
6. Dùng `COALESCE(SUM(...), :zeroAmount)`.
7. Đổi JOIN thành INNER JOIN và so sánh số Customer.
8. Đưa điều kiện PAID từ ON xuống WHERE và giải thích vì sao khách không có PAID bị loại.

## 31. Thực hành F — CASE và COUNT trong báo cáo

1. Dùng `COUNT(o)` theo Customer với LEFT JOIN.
2. CASE phân loại `NO_ORDERS`, `OCCASIONAL`, `FREQUENT`.
3. Thay `frequentMin` từ 2 sang 3 để thấy tác động.
4. Tạo thêm một Order ở Customer 2 và kiểm tra nhóm.
5. Dùng `HAVING COUNT(o) >= :min` để chỉ lấy nhóm đủ đơn.
6. So sánh kết quả với việc lọc trước bằng WHERE.

## 32. Thực hành G — DTO projection

1. Tạo record `CustomerCard` trong phần 13.
2. Viết JPQL `SELECT NEW` với COALESCE, NULLIF và CASE.
3. Kiểm tra constructor types.
4. Chạy query bằng `EntityManager.createQuery(..., CustomerCard.class)`.
5. Đối chiếu với query trả `Object[]`.
6. Thêm một CASE không có ELSE và quan sát NULL khi DTO field cho phép.
7. Thử dùng primitive không phù hợp với NULL và lý giải lỗi.
8. Cân nhắc vì sao DTO tiện hơn trả managed entity trực tiếp cho API.

## 33. Thực hành H — ORDER BY theo ưu tiên

1. Viết CASE xếp ACTIVE trước, SUSPENDED thứ hai, INACTIVE cuối.
2. Thêm khóa phụ `c.id`.
3. Phân trang danh sách bằng `setFirstResult` và `setMaxResults`.
4. Thử bỏ khóa phụ và quan sát thứ tự khi nhiều Customer cùng trạng thái.
5. So sánh CASE sort với sort alphabet theo enum string.
6. Với tập dữ liệu đủ lớn, quan sát SQL sort và index.

## 34. Bài tập tổng hợp

Yêu cầu viết một truy vấn JPQL cho dashboard:

- Chỉ lấy Customer đang ACTIVE.
- Tên hiển thị: nickname đã trim và không rỗng; nếu không có, dùng fullName.
- Hiển thị điểm 0 nếu loyaltyPoints NULL.
- Nhãn phân hạng: GOLD từ 70 điểm, SILVER từ 30 điểm, BRONZE còn lại.
- Tổng tiền chỉ tính Order PAID.
- Khách ACTIVE chưa có Order PAID vẫn phải xuất hiện với tổng 0.
- Sắp xếp GOLD trước SILVER trước BRONZE, sau đó theo ID.
- Kết quả trả DTO, không phải entity.
- Phải suy nghĩ về index và tính ổn định khi phân trang.

**Gợi ý phân tích:**

- `WHERE c.status = :active`.
- Tên: `COALESCE(NULLIF(TRIM(c.nickname), ''), c.fullName)`.
- Điểm: `COALESCE(c.loyaltyPoints, 0)`.
- Hạng: searched CASE theo ngưỡng từ cao xuống thấp.
- Doanh thu: `LEFT JOIN c.orders o ON o.status = :paid` và `COALESCE(SUM(o.totalAmount), :zeroAmount)`.
- Group theo những thuộc tính Customer không nằm trong aggregate.
- Order theo CASE rank và ID; kiểm tra provider khi kết hợp CASE sort với grouped query.

Với dashboard dữ liệu lớn, hãy xem query plan thực tế. Một JPQL duy nhất không luôn nhanh hơn hai query có mục đích rõ ràng; tối ưu cần dựa trên workload chứ không chỉ số lượng dòng code.

---

## 35. Câu hỏi ôn tập

1. JPQL `CASE` có hai dạng cú pháp chính nào?
2. Searched CASE khác simple CASE về cách chọn điều kiện ra sao?
3. Khi nhiều WHEN TRUE, nhánh nào được chọn?
4. Nếu không có ELSE và không WHEN nào TRUE, CASE trả giá trị gì?
5. Vì sao `CASE c.nickname WHEN NULL` không phải cách nhận diện nickname NULL?
6. Sự khác biệt giữa `NULL`, chuỗi rỗng và chuỗi chỉ chứa dấu cách là gì?
7. `COALESCE(a, b, c)` chọn giá trị theo thứ tự nào?
8. Nếu tất cả tham số COALESCE đều NULL, kết quả là gì?
9. `NULLIF(a, b)` trả NULL khi nào?
10. `NULLIF` khác `COALESCE` về hướng biến đổi dữ liệu như thế nào?
11. Vì sao `COALESCE(nickname, fullName)` có thể trả một chuỗi chỉ gồm dấu cách?
12. Biểu thức `COALESCE(NULLIF(TRIM(nickname), ''), fullName)` xử lý vấn đề gì?
13. Vì sao `NULL = NULL` không TRUE trong logic ba giá trị?
14. Khi `points=NULL`, `points >= 70` có giá trị logic gì?
15. Khi nào nên coi NULL points là 0 và khi nào nên giữ trạng thái UNRATED?
16. Vì sao các nhánh CASE nên có kiểu kết quả tương thích?
17. Có nên trộn String và Integer trong cùng CASE không?
18. Sử dụng CASE trong `ORDER BY` giúp giải quyết loại sắp xếp nào?
19. Tại sao cần thêm khóa phụ ổn định khi phân trang?
20. COALESCE trong WHERE có thể ảnh hưởng khả năng sử dụng index ra sao?
21. Vì sao bỏ COALESCE khỏi một điều kiện có thể thay đổi kết quả khi ngưỡng bằng 0?
22. SUM và COUNT xử lý nhóm không có giá trị như nhau không?
23. Vì sao cần `LEFT JOIN` khi muốn giữ Customer không có Order?
24. Tại sao điều kiện Order trong WHERE có thể làm mất hàng từ LEFT JOIN?
25. `GROUP BY` và `HAVING` khác `WHERE` như thế nào?
26. Constructor expression `SELECT NEW` có lợi gì so với `Object[]`?
27. DTO nên dùng wrapper hay primitive khi biểu thức có thể trả NULL?
28. Query dùng CASE có tự cập nhật cột persistent entity hay không?
29. NULLIF có sửa dữ liệu legacy trong database không?
30. Khi nào nên chuyển một công thức báo cáo phức tạp từ JPQL sang native SQL/view hoặc domain service?
31. Vì sao query chạy được trên một provider không chắc portable với provider khác?
32. Nếu COALESCE(SUM(...), 0) vẫn không trả khách không có đơn, bạn sẽ kiểm tra phần nào của query?

---

## 36. Bảng ghi nhớ

| Bài toán | Biểu thức JPQL |
|---|---|
| Phân loại theo nhiều điều kiện | `CASE WHEN condition THEN value ELSE value END` |
| Ánh xạ enum sang nhãn | `CASE c.status WHEN :active THEN 'Hoạt động' ELSE 'Khác' END` |
| Chọn giá trị không NULL đầu tiên | `COALESCE(c.nickname, c.fullName)` |
| Biến chuỗi rỗng thành NULL | `NULLIF(c.nickname, '')` |
| Xử lý chuỗi chỉ có dấu cách | `NULLIF(TRIM(c.nickname), '')` |
| Tên hiển thị có fallback | `COALESCE(NULLIF(TRIM(c.nickname), ''), c.fullName)` |
| Điểm hiển thị mặc định bằng 0 | `COALESCE(c.loyaltyPoints, 0)` |
| Phân biệt chưa có điểm | `CASE WHEN c.loyaltyPoints IS NULL THEN 'UNRATED' ... END` |
| Tổng tiền không có order | `COALESCE(SUM(o.totalAmount), :zeroAmount)` |
| Hạng sắp xếp ưu tiên | `ORDER BY CASE WHEN ... THEN 0 ELSE 1 END, c.id` |
| Kiểm tra missing nickname sau chuẩn hóa | `NULLIF(TRIM(c.nickname), '') IS NULL` |
| Tránh chia mẫu số bằng 0 | `NULLIF(denominator, :zero)`, kiểm tra dialect và kiểu |
| Trả về DTO | `SELECT NEW demo.dto.CustomerCard(...)` |
| Bảo toàn bản ghi không có child | `LEFT JOIN` cùng điều kiện `ON` phù hợp |

### Sơ đồ tổng hợp

```text
                  DỮ LIỆU JPQL
                       |
          +------------+------------+
          |            |            |
         CASE       COALESCE       NULLIF
          |            |            |
   Chọn nhánh theo    Chọn giá trị  Trả NULL khi
   điều kiện hoặc     không NULL   hai giá trị bằng
   giá trị so khớp    đầu tiên     nhau
          |            |            |
          +------------+------------+
                       |
             SELECT / WHERE / ORDER BY
               HAVING / REPORT / DTO
                       |
                SQL do JPA sinh
                       |
             DATABASE xử lý NULL,
             kiểu dữ liệu, JOIN, index
```

**Nguyên tắc cuối cùng:** dùng **`CASE`** khi cần *quyết định theo điều kiện*, **`COALESCE`** khi cần *fallback cho giá trị NULL*, và **`NULLIF`** khi cần *biến một giá trị đặc biệt thành NULL*. Phối hợp chúng với `IS NULL`, JOIN và aggregation có chủ đích; luôn phân biệt **NULL với số 0/chuỗi trống**, kiểm soát kiểu trả về và đo SQL trên provider/database thực tế. Những biểu thức này làm truy vấn rõ ràng và mạnh hơn khi chúng mô tả đúng semantics dữ liệu, không phải khi chúng che đi các quy tắc nghiệp vụ chưa được xác định.

