# Lựa chọn hàm chuỗi, số và ngày giờ theo phiên bản đặc tả JPQL

## 1. Tại sao phải nhìn phiên bản Jakarta Persistence trước khi viết hàm JPQL?

Trong JPA, **JPQL** (*Java/Jakarta Persistence Query Language*) truy vấn **entity và thuộc tính ánh xạ**, không truy vấn trực tiếp tên bảng như SQL thuần. Ngoài việc lọc, join và sắp xếp, JPQL hỗ trợ những **biểu thức hàm** để xử lý chuỗi, số và ngày giờ ngay trong truy vấn.

Ví dụ một ứng dụng bán hàng có nhu cầu:

- Tìm khách hàng không phân biệt chữ hoa/chữ thường.
- Lấy phần tiền làm tròn, tính độ chênh lệch, hoặc phân loại đơn theo số tiền.
- Lấy năm/tháng từ thời điểm đặt hàng.
- Hiển thị ba ký tự đầu của mã đơn.
- Lọc đơn đặt trong ngày hôm nay.
- Chuẩn hóa một mã chứa dấu cách và dấu gạch ngang.

Một developer quen SQL có thể viết:

```sql
-- Đây là ví dụ SQL phụ thuộc dialect, không phải JPQL portable.
SELECT DATE_TRUNC('month', placed_at), SUM(total_amount)
FROM sales_orders
GROUP BY DATE_TRUNC('month', placed_at);
```

Rồi đưa nguyên văn `DATE_TRUNC` vào JPQL. Truy vấn có thể chạy trên một provider/database nhưng **không được đặc tả JPA bảo đảm portable**.

Một ví dụ khác:

```sql
SELECT ROUND(o.totalAmount, 2)
FROM SalesOrder o
```

Ở **Jakarta Persistence 3.1 trở lên**, `ROUND` là hàm số **được chuẩn hóa** trong JPQL. Ở các phiên bản trước, một provider có thể hỗ trợ như phần mở rộng, nhưng không được coi là bảo đảm của đặc tả cũ.

Tương tự, biểu thức:

```sql
SELECT REPLACE(o.code, '-', '')
FROM SalesOrder o
```

chỉ trở thành hàm chuỗi **chuẩn JPQL từ Jakarta Persistence 3.2**. Nếu chạy trên 3.0/3.1, cú pháp này có thể được provider cụ thể chấp nhận nhưng không mang tính portable theo mức đặc tả đó.

**Mục tiêu của bài:** biết **hàm nào được đặc tả nào bảo đảm**, lựa chọn cách viết phù hợp với phiên bản thực tế, phân biệt phần mở rộng của provider/database với JPQL chuẩn, và biết khi nào nên đưa một phép biến đổi về Java, Criteria API, native SQL hoặc dùng `FUNCTION(...)`.

---

## 2. Ba lớp tương thích cần kiểm tra

Một truy vấn chạy thành công phụ thuộc đồng thời vào ít nhất ba tầng:

```text
Ứng dụng Java
  |
  | JPQL / Criteria API sử dụng cú pháp và hàm nào?
  v
Phiên bản đặc tả JPA / Jakarta Persistence
  |
  | Provider triển khai chuẩn + extension nào?
  v
Provider: Hibernate / EclipseLink / ...
  |
  | SQL dialect chuyển đổi sang biểu thức DB nào?
  v
Database: PostgreSQL / MySQL / Oracle / H2 / ...
```

Không nên đánh đồng:

1. **Đặc tả**: quy định phần ngôn ngữ và API portable tối thiểu.
2. **Provider**: trình phân tích JPQL/Criteria, dịch AST sang SQL và có thể hỗ trợ nhiều hàm mở rộng.
3. **Database/dialect**: nơi thực thi SQL cuối cùng, có quy tắc kiểu dữ liệu, collation, timezone, rounding và index riêng.

Một ví dụ quan trọng: provider hiện đại có thể hỗ trợ `ROUND` dù dự án vẫn khai báo persistence API cũ. Điều đó **không biến `ROUND` thành hàm chuẩn của phiên bản JPA cũ**.

Ngược lại, chỉ thêm dependency `jakarta.persistence-api:3.2` không bảo đảm provider thực sự triển khai toàn bộ JPQL 3.2 hoặc dialect database hỗ trợ biểu thức cần thiết.

### 2.1. Phiên bản API và phiên bản provider phải tương thích

Có ba câu hỏi riêng:

- Dự án biên dịch theo **API nào**: `javax.persistence` hay `jakarta.persistence`, bản 3.0, 3.1, 3.2?
- Provider đang dùng **phiên bản nào**, có công bố hỗ trợ mức đặc tả đó không?
- Database/dialect có thực thi và trả về kiểu dữ liệu như mong đợi không?

Tài liệu của provider có thể mô tả **HQL** hoặc một query language mở rộng, không phải tất cả tính năng đó đều thuộc JPQL chuẩn. Một mẫu HQL chạy trên Hibernate **không tự là JPQL portable** trên EclipseLink.

## 3. Các mốc phiên bản cần nhớ

| Phiên bản | Đặc điểm liên quan hàm chuỗi/số/ngày giờ | Quy tắc chọn |
|---|---|---|
| **JPA 2.2** (`javax.persistence`) | Có bộ hàm chuỗi/số/ngày giờ cổ điển: `CONCAT`, `SUBSTRING`, `TRIM`, `LOWER`, `UPPER`, `LENGTH`, `LOCATE`, `ABS`, `SQRT`, `MOD`, `CURRENT_DATE`, `CURRENT_TIME`, `CURRENT_TIMESTAMP`; cùng `FUNCTION` cho DB functions. | Dùng bộ cơ bản khi cần chạy trên nền legacy. |
| **Jakarta Persistence 3.0** (`jakarta.persistence`) | Chủ yếu chuyển namespace từ `javax.persistence` sang `jakarta.persistence`; nhóm hàm JPQL nền tảng về cơ bản kế thừa JPA 2.2. | **Không mặc định** có mọi hàm mới của 3.1 chỉ vì đã chuyển sang `jakarta`. |
| **Jakarta Persistence 3.1** | Bổ sung `CEILING`, `EXP`, `FLOOR`, `LN`, `POWER`, `ROUND`, `SIGN`; `LOCAL DATE`, `LOCAL TIME`, `LOCAL DATETIME`; `EXTRACT`. Criteria API có các phương thức tương ứng cho nhóm số và local date/time. | Có thể chọn thêm nhóm hàm toán học và thời gian mới như **hàm chuẩn**. |
| **Jakarta Persistence 3.2** | Bổ sung `REPLACE`, `LEFT`, `RIGHT`, toán tử nối chuỗi `||`, `CAST`; Criteria API mở rộng tương ứng, bổ sung `extract(...)` và một số overload. | Có thêm lựa chọn chuẩn cho xử lý chuỗi và chuyển kiểu; vẫn phải xét dialect/type semantics. |
| **Jakarta Persistence 4.0 đang phát triển** | Có bản dự thảo/milestone, nhưng chưa nên dùng cú pháp từ draft như một cam kết tương thích của bản phát hành ổn định. | Tách rõ chuẩn **đã phát hành** với bản phát triển khi lập chính sách portable. |

Tính tới **tháng 11/2026**, phiên bản **3.2** là một mốc chuẩn đã phát hành phù hợp để so sánh các hàm trong bài; phiên bản 4.0 còn có tài liệu phát triển. Khi dự án nâng cấp, phải dựa vào bản API/provider được triển khai thực tế chứ không suy luận theo “phiên bản mới nhất trên web”.

### 3.1. Ma trận chọn nhanh

Ký hiệu:

- **Có** = thuộc tập hàm/toán tử chuẩn trong phiên bản đó.
- **Chưa** = không được phiên bản đó bảo đảm; provider extension có thể hỗ trợ.
- **Có từ 3.1/3.2** = có trong những phiên bản từ mốc ghi chú trở đi.

| Hàm/biểu thức JPQL | JPA 2.2 | Jakarta 3.0 | Jakarta 3.1 | Jakarta 3.2 |
|---|:---:|:---:|:---:|:---:|
| `CONCAT`, `SUBSTRING`, `TRIM`, `LOWER`, `UPPER` | Có | Có | Có | Có |
| `LENGTH`, `LOCATE` | Có | Có | Có | Có |
| `ABS`, `SQRT`, `MOD` | Có | Có | Có | Có |
| `SIZE`, `INDEX` | Có | Có | Có | Có |
| `CURRENT_DATE`, `CURRENT_TIME`, `CURRENT_TIMESTAMP` | Có | Có | Có | Có |
| `FUNCTION('db_function', ...)` | Có | Có | Có | Có |
| `CEILING`, `FLOOR`, `ROUND` | Chưa | Chưa | Có | Có |
| `POWER`, `EXP`, `LN`, `SIGN` | Chưa | Chưa | Có | Có |
| `LOCAL DATE`, `LOCAL TIME`, `LOCAL DATETIME` | Chưa | Chưa | Có | Có |
| `EXTRACT(... FROM ...)` | Chưa | Chưa | Có | Có |
| `REPLACE`, `LEFT`, `RIGHT` | Chưa | Chưa | Chưa | Có |
| Toán tử chuỗi `||` | Chưa | Chưa | Chưa | Có |
| `CAST(... AS STRING/INTEGER/LONG/FLOAT/DOUBLE)` | Chưa | Chưa | Chưa | Có |

**Lưu ý:** `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` là **aggregate functions** đã có từ lâu, không phải nhóm số mới chỉ xuất hiện ở 3.1. Tương tự, `CASE`, `COALESCE`, `NULLIF` giúp xây biểu thức từ nhiều giá trị nhưng không phải các hàm chuỗi mới của 3.2.

### 3.2. Không lấy package name làm bằng chứng duy nhất

`import jakarta.persistence.EntityManager;` chỉ cho thấy ứng dụng dùng namespace Jakarta. Nó không cho biết provider đang thực thi JPQL 3.0, 3.1 hay 3.2.

Ví dụ:

```java
import jakarta.persistence.EntityManager;
```

Trong dự án chỉ triển khai Jakarta Persistence 3.0, `REPLACE(...)` vẫn chưa là cú pháp chuẩn theo mức đặc tả 3.0.

---

## 4. Entity và dữ liệu mẫu

Để minh họa nhất quán, dùng entity `SalesOrder` có tên khách, mã đơn, số tiền và thời gian tạo.

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;

@Entity
@Table(name = "sales_orders")
public class SalesOrder {

    public enum Status {
        DRAFT, PAID, CANCELLED
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true,
            length = 40)
    private String code;

    @Column(name = "customer_name", nullable = false, length = 150)
    private String customerName;

    @Column(name = "total_amount", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "placed_at", nullable = false)
    private LocalDateTime placedAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 16)
    private Status status;

    protected SalesOrder() {
        // Constructor không tham số dành cho JPA.
    }

    public SalesOrder(
            String code,
            String customerName,
            BigDecimal totalAmount,
            LocalDateTime placedAt,
            Status status
    ) {
        this.code = Objects.requireNonNull(code).trim();
        this.customerName = Objects.requireNonNull(customerName).trim();
        this.totalAmount = Objects.requireNonNull(totalAmount);
        this.placedAt = Objects.requireNonNull(placedAt);
        this.status = Objects.requireNonNull(status);

        if (this.code.isEmpty() || this.customerName.isEmpty()
                || totalAmount.signum() < 0) {
            throw new IllegalArgumentException(
                "Dữ liệu đơn hàng không hợp lệ"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getCustomerName() {
        return customerName;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public LocalDateTime getPlacedAt() {
        return placedAt;
    }

    public Status getStatus() {
        return status;
    }
}
```

Một schema SQL minh họa:

```sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL UNIQUE,
    customer_name VARCHAR(150) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    placed_at TIMESTAMP NOT NULL,
    status VARCHAR(16) NOT NULL
);
```

Bảng dữ liệu để suy luận:

| Mã | Tên khách | Tiền | Thời điểm đặt | Trạng thái |
|---|---|---:|---|---|
| `SO-2026-001` | `  An  ` | 120000.50 | 2026-10-30 09:15:00 | PAID |
| `SO-2026-002` | `Bình` | 250000.00 | 2026-10-31 22:30:00 | PAID |
| `SO-2026-003` | `chi` | 75000.25 | 2026-11-01 00:05:00 | DRAFT |
| `SO-2026-004` | `Dũng` | 0.00 | 2026-11-02 14:20:00 | CANCELLED |

Tên có khoảng trắng ở hàng đầu là dữ liệu để ví dụ `TRIM`; trong entity constructor ở trên có bước trim, nên nếu seed qua constructor, tên sẽ được chuẩn hóa trước khi lưu. Để test chính xác `TRIM` với khoảng trắng lưu trong DB, fixture phải cố ý tạo dữ liệu thô hoặc có migration riêng; **đừng nhầm dữ liệu minh họa trên bảng với một lời cam kết constructor sẽ giữ khoảng trắng**.

Tất cả JPQL dưới đây dùng `SalesOrder`, `code`, `customerName`, `totalAmount`, `placedAt`, `status` là **entity name và property name**, không dùng trực tiếp `sales_orders` hay `placed_at` trong câu JPQL.

## 5. Nhóm hàm chuỗi cơ bản: portable từ JPA 2.2

### 5.1. `LOWER` và `UPPER`

```sql
SELECT o
FROM SalesOrder o
WHERE LOWER(o.customerName) = LOWER(:name)
```

Java:

```java
List<SalesOrder> orders = em.createQuery(
    """
    SELECT o
    FROM SalesOrder o
    WHERE LOWER(o.customerName) = LOWER(:name)
    """,
    SalesOrder.class
)
.setParameter("name", "AN")
.getResultList();
```

`LOWER` và `UPPER` là chuẩn lâu đời. Chúng chuyển kiểu chữ theo ngữ nghĩa collation/locale của database, không phải luôn có kết quả hoàn toàn giống `String.toLowerCase(Locale.ROOT)` trong Java.

Nếu ứng dụng có yêu cầu tìm kiếm không dấu, chuẩn hóa Unicode đặc biệt hoặc ngôn ngữ có quy tắc case folding phức tạp, chỉ dùng `LOWER` không phải giải pháp bảo đảm mọi so sánh đều thống nhất.

### 5.2. `TRIM`

Các cú pháp điển hình:

```sql
SELECT TRIM(o.customerName)
FROM SalesOrder o
```

```sql
SELECT TRIM(BOTH FROM o.customerName)
FROM SalesOrder o
```

```sql
SELECT TRIM(LEADING FROM o.customerName)
FROM SalesOrder o
```

```sql
SELECT TRIM(TRAILING FROM o.customerName)
FROM SalesOrder o
```

Khi không khai báo ký tự trim, mặc định là dấu cách; nếu không chỉ định `LEADING`/`TRAILING`, mặc định `BOTH`. Cũng có thể chỉ định **một ký tự** cần loại bỏ theo cú pháp chuẩn:

```sql
SELECT TRIM(BOTH '-' FROM o.code)
FROM SalesOrder o
```

`TRIM` loại ký tự ở **đầu/cuối**; nó không thay mọi dấu gạch ngang nằm giữa chuỗi. Nếu muốn thay tất cả dấu gạch ngang, `REPLACE` là lựa chọn chuẩn từ 3.2.

### 5.3. `CONCAT`

```sql
SELECT CONCAT(o.code, ' - ', o.customerName)
FROM SalesOrder o
```

`CONCAT` hỗ trợ nối các string expressions. Cú pháp chuẩn ở các đặc tả sau cho phép từ hai đối số; khi hỗ trợ đúng mốc chuẩn, có thể dùng nhiều đối số như ví dụ trên.

Đối với nền legacy có provider hạn chế hoặc nếu muốn đơn giản hóa:

```sql
SELECT CONCAT(CONCAT(o.code, ' - '), o.customerName)
FROM SalesOrder o
```

Đây là cách ghép lồng nhau chỉ với hai đối số mỗi lần.

Nếu một đối số có thể `NULL`, đừng giả định mọi database đều nối null thành chuỗi rỗng. Muốn thể hiện rõ giá trị thay thế:

```sql
SELECT CONCAT(o.code, COALESCE(o.customerName, ''))
FROM SalesOrder o
```

`COALESCE` chọn giá trị không-null đầu tiên, nhưng còn phải xét các quy tắc null/kiểu dữ liệu của hệ quản trị.

### 5.4. `SUBSTRING`

```sql
SELECT SUBSTRING(o.code, 1, 2)
FROM SalesOrder o
```

Với `code = 'SO-2026-001'`, kết quả là `SO`.

Cú pháp:

```text
SUBSTRING(chuoi, vi_tri_bat_dau [, so_ky_tu])
```

- **Vị trí đầu tiên là 1**, không phải 0 như Java `String.substring`.
- Tham số thứ ba là **độ dài**, không phải endIndex.
- Tham số độ dài có thể bỏ qua ở cú pháp chuẩn hiện hành; khi đó lấy từ vị trí bắt đầu đến cuối chuỗi.

Ví dụ:

```sql
SELECT SUBSTRING(o.code, 4, 4)
FROM SalesOrder o
```

Với `SO-2026-001`, bắt đầu từ vị trí 4 và lấy 4 ký tự cho ra `2026`.

**Lỗi quen thuộc:**

```sql
-- Sai ý định nếu muốn bốn ký tự từ vị trí 4:
SUBSTRING(o.code, 4, 8)
```

Tham số `8` không có nghĩa “đến vị trí 8”, mà là “lấy 8 ký tự”.

### 5.5. `LENGTH`

```sql
SELECT o
FROM SalesOrder o
WHERE LENGTH(o.code) > 10
```

`LENGTH` trả số ký tự của một chuỗi, về mặt query type là số nguyên. Không nên đồng nhất độ dài ký tự với số byte UTF-8: một ký tự Unicode có thể chiếm nhiều byte.

### 5.6. `LOCATE`: thứ tự đối số dễ bị đảo

Cú pháp JPQL:

```text
LOCATE(chuoi_can_tim, chuoi_nguon [, vi_tri_bat_dau])
```

Ví dụ:

```sql
SELECT LOCATE('-', o.code)
FROM SalesOrder o
```

Với `SO-2026-001`, dấu gạch ngang đầu tiên ở **vị trí 3**, nên giá trị là 3.

Đặc biệt:

- `LOCATE` **trả 0 nếu không tìm thấy**.
- Vị trí bắt đầu mặc định là **1**.
- Thứ tự là **needle trước, haystack sau** trong JPQL.
- Cách đặt tham số khác với một số biến thể API Criteria hoặc các hàm SQL provider-specific.

Ví dụ lọc mã có chứa dấu gạch ngang:

```sql
SELECT o
FROM SalesOrder o
WHERE LOCATE('-', o.code) > 0
```

Nếu chỉ muốn so khớp mẫu tiền tố/hậu tố, `LIKE` có thể dễ hiểu hơn; nếu muốn so chuỗi thông thường, dùng `=` hoặc `LOWER` theo yêu cầu.

### 5.7. `LIKE` không phải hàm nhưng rất hay đi kèm xử lý chuỗi

```sql
SELECT o
FROM SalesOrder o
WHERE LOWER(o.customerName) LIKE :pattern
```

```java
.setParameter("pattern", "%an%")
```

Lưu ý:

- `%` đại diện chuỗi ký tự bất kỳ.
- `_` đại diện một ký tự.
- Nếu input người dùng được dùng như **literal search**, cần escape wildcard thay vì vô tình biến input thành pattern.
- Tham số hóa query giúp tránh chèn cấu trúc JPQL từ dữ liệu người dùng; không tự nối query string bằng input không tin cậy.

Đừng dùng `FUNCTION('lower', ...)` nếu `LOWER` chuẩn đã đáp ứng yêu cầu.

## 6. Hàm chuỗi mới ở Jakarta Persistence 3.2

Jakarta Persistence 3.2 bổ sung những hàm vốn quen thuộc trong nhiều SQL dialect nhưng **trước đó không thuộc JPQL core portable**.

### 6.1. `REPLACE`

```sql
SELECT REPLACE(o.code, '-', '')
FROM SalesOrder o
```

Với `SO-2026-001` → `SO2026001`.

Ba đối số:

```text
REPLACE(chuoi_nguon, chuoi_can_thay, chuoi_thay_the)
```

Nó thay **mọi lần xuất hiện** của chuỗi cần thay theo ngữ nghĩa được xác định; không giống `TRIM` chỉ xử lý hai đầu.

Ứng dụng:

```sql
SELECT o
FROM SalesOrder o
WHERE REPLACE(o.code, '-', '') = :normalizedCode
```

Tuy nhiên, lọc bằng hàm trên cột có thể khiến index thường trên `order_code` không được khai thác tối ưu. Nếu mã chuẩn hóa được dùng tìm kiếm nhiều lần, cân nhắc lưu một `normalizedCode` riêng với unique/index phù hợp.

### 6.2. `LEFT` và `RIGHT`

```sql
SELECT LEFT(o.code, 2)
FROM SalesOrder o
```

```sql
SELECT RIGHT(o.code, 3)
FROM SalesOrder o
```

Với `SO-2026-001`:

- `LEFT(..., 2)` → `SO`.
- `RIGHT(..., 3)` → `001`.

Trước 3.2, lấy tiền tố có thể viết bằng `SUBSTRING(o.code, 1, 2)`. Lấy hậu tố portable khó đọc hơn nếu không có `RIGHT`, nhưng có thể kết hợp `LENGTH` với `SUBSTRING` nếu yêu cầu và vị trí hợp lệ.

Ví dụ ý tưởng hậu tố dài ba ký tự ở nền cũ:

```sql
SELECT SUBSTRING(o.code, LENGTH(o.code) - 2, 3)
FROM SalesOrder o
WHERE LENGTH(o.code) >= 3
```

Cần điều kiện `LENGTH >= 3` để tránh vị trí bắt đầu không hợp lệ với chuỗi ngắn. Khi 3.2 đã được hỗ trợ, `RIGHT` diễn đạt ý định trực tiếp hơn.

### 6.3. Toán tử nối chuỗi `||`

Từ 3.2, JPQL chuẩn có toán tử nối chuỗi:

```sql
SELECT o.code || ' - ' || o.customerName
FROM SalesOrder o
```

Trong các phiên bản cũ, dùng `CONCAT`:

```sql
SELECT CONCAT(o.code, ' - ', o.customerName)
FROM SalesOrder o
```

**Không lấy việc database có `||` làm bằng chứng JPQL 3.0 hỗ trợ.** Provider có thể nhận cú pháp extension, nhưng khi viết query cần portable giữa provider hoặc phù hợp mức đặc tả cũ, `CONCAT` là lựa chọn an toàn.

### 6.4. `CAST`

Jakarta Persistence 3.2 chuẩn hóa những phép cast nhất định:

```sql
SELECT CAST(o.id AS STRING)
FROM SalesOrder o
```

Trả kết quả biểu thức kiểu `String`.

Ví dụ database có cột chuỗi chứa mã số ASCII hợp lệ:

```sql
SELECT CAST(o.externalNumericCode AS LONG)
FROM SalesOrder o
```

Đây là ví dụ **giả định entity có thuộc tính `externalNumericCode` kiểu String**, không phải thuộc tính của `SalesOrder` mẫu ở phần 4.

Các kiểu cast tối thiểu mà 3.2 yêu cầu provider chấp nhận gồm:

| Từ → sang | Cú pháp |
|---|---|
| Một scalar expression → String | `CAST(expression AS STRING)` |
| String expression → Integer | `CAST(expression AS INTEGER)` |
| String expression → Long | `CAST(expression AS LONG)` |
| String expression → Float | `CAST(expression AS FLOAT)` |
| String expression → Double | `CAST(expression AS DOUBLE)` |

Không tự suy ra rằng 3.2 chuẩn hóa **mọi** SQL cast như `CAST(... AS DECIMAL(18,2))` hoặc `CAST(... AS DATE)`. Một số provider/dialect có extension nhưng mức chuẩn tối thiểu không bao gồm tất cả kiểu đích SQL tùy ý.

**Chú ý dữ liệu bẩn:** nếu nguồn chuỗi chứa `'N/A'` mà cast sang số, database có thể báo lỗi hoặc có semantics riêng. Nếu đã biết field thực sự là số, nên **ánh xạ nó thành numeric Java type ngay từ đầu** thay vì cast chuỗi ở mọi query.

## 7. Nhóm hàm số cơ bản: từ JPA 2.2

### 7.1. `ABS`: trị tuyệt đối

```sql
SELECT ABS(o.totalAmount - :expected)
FROM SalesOrder o
```

Ứng dụng: lấy độ chênh lệch tuyệt đối giữa số tiền thực tế và số tiền mục tiêu.

Nếu `totalAmount = 120000.50` và `expected = 120000.00`, chênh lệch là `0.50`.

`ABS` có trong tập hàm số chuẩn từ các phiên bản JPA trước 3.1.

### 7.2. `SQRT`: căn bậc hai

```sql
SELECT SQRT(o.someMetric)
FROM SalesOrder o
```

Ví dụ giả định entity có `someMetric` là giá trị số không âm. `SQRT` trả kết quả kiểu số thực phù hợp theo đặc tả.

Không áp dụng căn bậc hai cho số âm rồi giả định mọi database sẽ trả cùng giá trị; với biểu thức ngoài miền hợp lệ, hành vi/error tùy database.

### 7.3. `MOD`: phép chia lấy dư số nguyên

```sql
SELECT o
FROM SalesOrder o
WHERE MOD(o.id, 2) = 0
```

Ví dụ chọn các đơn có ID chẵn để minh họa cú pháp. `MOD` nhận hai **integer arguments** theo đặc tả; không dùng trực tiếp để tính phần lẻ của `BigDecimal`.

Phép chia lấy dư với số âm hoặc chia cho 0 có thể chịu semantics/error của database; không nên dùng `MOD` để định nghĩa những quy tắc số học ngoài miền thông thường mà chưa kiểm thử.

### 7.4. Toán tử số học

Các toán tử số học có thể dùng ngay trong JPQL:

```sql
SELECT o.totalAmount * :taxRate
FROM SalesOrder o
```

```sql
SELECT o
FROM SalesOrder o
WHERE o.totalAmount - :discount >= :minimum
```

Những toán tử `+`, `-`, `*`, `/` và quy tắc numeric promotion không phải chỉ mới xuất hiện ở 3.1.

Đừng nhầm các **hàm số mới** với khả năng làm số học căn bản đã có từ trước.

## 8. Nhóm hàm số được thêm ở Jakarta Persistence 3.1

Jakarta Persistence 3.1 mở rộng bộ hàm để xử lý dữ liệu số phong phú hơn mà không phải gọi hàm riêng của database.

| Hàm | Ý nghĩa | Ví dụ JPQL |
|---|---|---|
| `CEILING(x)` | Làm tròn lên đến số nguyên gần nhất theo hướng +∞. | `CEILING(o.totalAmount)` |
| `FLOOR(x)` | Làm tròn xuống đến số nguyên gần nhất theo hướng -∞. | `FLOOR(o.totalAmount)` |
| `ROUND(x, n)` | Làm tròn số `x` tới vị trí/thang `n`. | `ROUND(o.totalAmount, 0)` |
| `POWER(x, y)` | Lũy thừa `x^y`. | `POWER(o.someScore, 2)` |
| `EXP(x)` | Hàm mũ cơ số `e`. | `EXP(o.someRate)` |
| `LN(x)` | Logarithm tự nhiên. | `LN(o.positiveMetric)` |
| `SIGN(x)` | Dấu của số: âm, 0 hoặc dương. | `SIGN(o.totalAmount - :target)` |

Những biểu thức `someScore`, `someRate`, `positiveMetric` là thuộc tính giả định để minh họa toán học; entity `SalesOrder` mẫu chỉ khai báo những field ở phần 4.

### 8.1. `CEILING` và `FLOOR` không phải “round gần nhất”

Với `x = 12.3`:

```text
CEILING(12.3) = 13
FLOOR(12.3)   = 12
```

Với `x = -12.3`:

```text
CEILING(-12.3) = -12
FLOOR(-12.3)   = -13
```

Cách nhớ:

- `CEILING` đi về **+∞**.
- `FLOOR` đi về **-∞**.

Nếu dùng để định giá, phải định nghĩa rõ rounding policy. `CEILING` không tương đương `RoundingMode.HALF_UP` trong Java.

### 8.2. `ROUND` có hai đối số

```sql
SELECT ROUND(o.totalAmount, 0)
FROM SalesOrder o
```

Đối số thứ hai là số nguyên xác định precision/scale cho phép làm tròn theo semantics hàm. Ví dụ `ROUND(120000.50, 0)` biểu diễn yêu cầu làm tròn tới đơn vị.

**Cẩn thận:** quy tắc xử lý đúng điểm giữa `x.5`, kiểu trả về và các khác biệt ở database/dialect cần được kiểm thử cho nghiệp vụ tài chính. Đừng tự cho rằng `ROUND` trong database luôn giống chính sách `BigDecimal.setScale(..., RoundingMode.HALF_EVEN)` trong Java.

Nếu hệ thống tính tiền cần kết quả chính xác qua nhiều môi trường, thường phù hợp hơn khi định nghĩa thuật toán, precision, scale và rounding ở domain Java/decimal arithmetic, rồi lưu giá trị đã tính. Dùng JPQL `ROUND` cho báo cáo có thể được, nhưng phải xác định nó có là nguồn sự thật của nghiệp vụ hay không.

### 8.3. `POWER`, `EXP`, `LN` và kiểu số thực

```sql
SELECT POWER(2, 3)
FROM SalesOrder o
```

`POWER(2,3)` cho giá trị toán học bằng 8, nhưng theo đặc tả nhóm hàm này có quy tắc kiểu kết quả khác một phép nhân integer thông thường; `POWER`, `EXP`, `LN` và `SQRT` có thể trả kiểu số thực `Double`.

Với toán học độ chính xác cao, thao tác floating-point có sai số biểu diễn. Đặc biệt khi xử lý `BigDecimal`, không nên đưa phép toán lãi suất/tiền tệ quan trọng vào lũy thừa floating-point nếu nghiệp vụ cần một thuật toán decimal xác định.

`LN` chỉ có giá trị thực khi đối số dương. `EXP` với giá trị lớn có thể overflow. Chọn kiểu dữ liệu và điều kiện miền xác định trước khi đưa vào SQL.

### 8.4. `SIGN`

```sql
SELECT SIGN(o.totalAmount - :target)
FROM SalesOrder o
```

Với `target = 100000`:

- Tổng nhỏ hơn mục tiêu → -1.
- Bằng mục tiêu → 0.
- Lớn hơn mục tiêu → 1.

Có thể phân loại trực tiếp bằng `CASE WHEN` ở những phiên bản cũ:

```sql
SELECT CASE
         WHEN o.totalAmount < :target THEN -1
         WHEN o.totalAmount > :target THEN 1
         ELSE 0
       END
FROM SalesOrder o
```

Đây là một fallback portable khi chưa có `SIGN` chuẩn. Nếu `totalAmount` nullable, cần quyết định rõ cách xử lý null trước khi dùng `ELSE 0`; ví dụ entity mẫu khai báo NOT NULL.

### 8.5. Chọn fallback khi chỉ có JPA 2.2/3.0

| Muốn thực hiện | Có thể thay bằng cách nào ở mức cũ? | Đánh đổi |
|---|---|---|
| `CEILING`/`FLOOR` | Tính ở Java khi dữ liệu nhỏ/không cần lọc DB; hoặc DB function có chủ đích. | Không thay được đơn giản bằng cast integer trong mọi trường hợp, nhất là số âm. |
| `SIGN` | `CASE WHEN x < 0 THEN -1 WHEN x > 0 THEN 1 ELSE 0 END`. | Dài hơn nhưng dễ hiểu/portable. |
| `ROUND` | Xử lý decimal ở Java hoặc `FUNCTION('round', ...)` nếu DB hỗ trợ. | Cần xác nhận rounding semantics. |
| `POWER`/`EXP`/`LN` | Tính ở Java hoặc DB-specific function. | Chi phí truyền dữ liệu hoặc khóa vào dialect. |

Không nên tự “mô phỏng” một hàm số bằng biểu thức sai toán học chỉ để tránh nâng phiên bản. Ví dụ lấy phần nguyên không tự đồng nghĩa với `FLOOR` cho số âm.

## 9. `SIZE` và `INDEX`: số học liên quan collection

Ngoài hàm số xử lý thuộc tính numeric, JPQL có hai hàm liên quan collection/ordered list:

### 9.1. `SIZE`

Giả sử `Customer` có:

```java
@OneToMany(mappedBy = "customer")
private List<SalesOrder> orders;
```

```sql
SELECT c
FROM Customer c
WHERE SIZE(c.orders) > 3
```

`SIZE` trả số phần tử trong collection association. Nếu collection rỗng, giá trị là 0 theo đặc tả.

Đừng nhầm `SIZE(c.orders)` với `LENGTH(c.name)`:

- `SIZE` đo **collection**.
- `LENGTH` đo **chuỗi**.

Hiệu năng của `SIZE` có thể được provider thực thi bằng subquery/count hoặc cách khác. Nếu query report lớn, so sánh execution plan với `JOIN + GROUP BY`/`EXISTS` theo nhu cầu.

### 9.2. `INDEX`

`INDEX` dùng với identification variable của một **ordered list có `@OrderColumn`**.

Ví dụ:

```java
@OneToMany(mappedBy = "course")
@OrderColumn(name = "position_index")
private List<Student> waitlist;
```

JPQL:

```sql
SELECT s
FROM Course c JOIN c.waitlist s
WHERE INDEX(s) = 0
```

Giá trị index thường bắt đầu từ 0 theo semantics của order column. `INDEX` không phải hàm lấy ký tự thứ N của chuỗi và không nên dùng với một `List` không có order column chỉ vì Java collection có index.

## 10. Null, `COALESCE`, `NULLIF` và `CASE` khi gọi hàm

Các biểu thức JPQL áp dụng quy tắc null. Nếu đối số hàm là null/unknown, kết quả thường không có giá trị thông thường như khi truyền chuỗi/số hợp lệ.

Ví dụ:

```sql
SELECT LOWER(o.customerName)
FROM SalesOrder o
```

Nếu field nullable và bằng `null`, không nên mong `LOWER` trả `''`. Ở entity demo field có `nullable = false`, nhưng ở hệ thống thực có thể có dữ liệu legacy hoặc mapping khác.

Một số lựa chọn:

```sql
SELECT LOWER(COALESCE(o.customerName, ''))
FROM SalesOrder o
```

`COALESCE` trả biểu thức không-null đầu tiên.

```sql
SELECT NULLIF(o.code, '')
FROM SalesOrder o
```

`NULLIF` trả null nếu hai biểu thức bằng nhau.

```sql
SELECT CASE
         WHEN o.totalAmount IS NULL THEN 0
         ELSE o.totalAmount
       END
FROM SalesOrder o
```

Với `CASE`, xác định kiểu kết quả nhất quán. Không nên trộn bừa `String`, `Double` và `BigDecimal` trong các nhánh khi constructor DTO yêu cầu một kiểu cụ thể.

### 10.1. `COUNT` và `SUM` không có cùng null behavior

Giả sử một nhóm không có giá trị số phù hợp:

- `COUNT(expression)` cho số lượng, có thể là 0.
- `SUM(expression)` có thể trả null khi không có giá trị để cộng.

Để hiển thị 0:

```sql
SELECT COALESCE(SUM(o.totalAmount), 0)
FROM SalesOrder o
WHERE o.status = :status
```

Nếu kết quả kỳ vọng là `BigDecimal`, cần kiểm tra type inference/constructor DTO khi dùng literal `0`. Có thể map null về `BigDecimal.ZERO` tại tầng Java để tránh phụ thuộc subtle type promotion giữa provider.

---

## 11. Hàm ngày giờ cổ điển: `CURRENT_DATE`, `CURRENT_TIME`, `CURRENT_TIMESTAMP`

Trong JPA 2.2/3.0, JPQL có bộ ba:

```sql
SELECT CURRENT_DATE
FROM SalesOrder o
```

```sql
SELECT CURRENT_TIME
FROM SalesOrder o
```

```sql
SELECT CURRENT_TIMESTAMP
FROM SalesOrder o
```

Các hàm này lấy ngày/giờ hiện tại theo **database server** (và quy tắc phiên/SQL tương ứng), không phải nhất thiết theo `Clock.systemDefaultZone()` của JVM.

Theo đặc tả, kiểu kết quả:

| Biểu thức | Kiểu Java của kết quả |
|---|---|
| `CURRENT_DATE` | `java.sql.Date` |
| `CURRENT_TIME` | `java.sql.Time` |
| `CURRENT_TIMESTAMP` | `java.sql.Timestamp` |

Lưu ý `CURRENT_DATE` là keyword/function không có dấu ngoặc bắt buộc trong cú pháp JPQL chuẩn. Không nên tự đồng nhất với `LocalDate.now()` mà không xem xét timezone.

### 11.1. Lọc dữ liệu trước thời điểm hiện tại

```sql
SELECT o
FROM SalesOrder o
WHERE o.placedAt <= CURRENT_TIMESTAMP
```

Đây là ý tưởng query. Tuy nhiên, trong entity demo `placedAt` có kiểu `LocalDateTime`, còn `CURRENT_TIMESTAMP` theo đặc tả trả kiểu `java.sql.Timestamp`. Khả năng so sánh trực tiếp và type inference phải được kiểm thử theo provider/version; nếu mục tiêu là thiết kế mới dùng `java.time`, xem `LOCAL DATETIME` từ 3.1 hoặc cách truyền `LocalDateTime` bằng parameter.

Không nên giấu nguy cơ mismatch Java temporal types chỉ vì SQL backend thực chất đều lưu TIMESTAMP.

### 11.2. Hàm “hiện tại” có phụ thuộc timezone không?

Có thể. Sự phân biệt quan trọng:

- JVM có default timezone.
- JDBC driver có quy tắc chuyển đổi giá trị thời gian.
- Database session/server có timezone.
- Cột `TIMESTAMP WITHOUT TIME ZONE` không lưu instant/timezone.
- Cột có timezone hoặc ứng dụng lưu UTC cần quy ước rõ.

Bài toán “đơn trong ngày hôm nay” phụ thuộc **ngày theo timezone nghiệp vụ**, không chỉ giờ hệ điều hành máy chủ.

## 12. Các hàm `LOCAL DATE`, `LOCAL TIME`, `LOCAL DATETIME` từ 3.1

Jakarta Persistence 3.1 bổ sung bộ hàm hiện tại tương ứng với `java.time`:

```sql
SELECT LOCAL DATE
FROM SalesOrder o
```

```sql
SELECT LOCAL TIME
FROM SalesOrder o
```

```sql
SELECT LOCAL DATETIME
FROM SalesOrder o
```

Bảng kết quả:

| Biểu thức JPQL 3.1+ | Kiểu Java |
|---|---|
| `LOCAL DATE` | `java.time.LocalDate` |
| `LOCAL TIME` | `java.time.LocalTime` |
| `LOCAL DATETIME` | `java.time.LocalDateTime` |

**Rất quan trọng về cú pháp:** theo đặc tả, viết **`LOCAL DATE`** với dấu cách, không phải tự đổi thành `LOCAL_DATE` chỉ vì nhiều SQL dialect có hàm tương tự.

Ví dụ:

```java
LocalDate dbToday = em.createQuery(
    "SELECT LOCAL DATE FROM SalesOrder o",
    LocalDate.class
)
.setMaxResults(1)
.getSingleResult();
```

Mẫu trên cần lưu ý: vì `FROM SalesOrder o` có thể có **0 hàng**, query `getSingleResult()` có thể ném `NoResultException` dù biểu thức ngày giờ có nghĩa. Nếu chỉ muốn lấy ngày giờ hiện tại của database độc lập với entity, nên cân nhắc SQL native một-row, API/clock do tầng ứng dụng cung cấp hoặc query JPQL gắn với entity theo use case có dữ liệu bảo đảm.

Một ví dụ phù hợp hơn với thực tế:

```sql
SELECT o
FROM SalesOrder o
WHERE o.placedAt <= LOCAL DATETIME
```

Với mapping `LocalDateTime placedAt`, biểu thức `LOCAL DATETIME` cùng nhóm kiểu Java nên diễn đạt ý định rõ hơn `CURRENT_TIMESTAMP` legacy. Tuy nhiên, phải hiểu nó dùng **đồng hồ database**, không phải Clock của application.

### 12.1. Khi nào dùng Java `Clock` thay vì `LOCAL DATETIME`?

Khi nghiệp vụ yêu cầu:

- Test deterministic theo thời điểm cố định.
- Đồng bộ “now” giữa nhiều phép tính ở tầng application.
- Quy định timezone nghiệp vụ.
- Không phụ thuộc đồng hồ DB.
- Thực hiện nhiều điều kiện trên nhiều nguồn dữ liệu không cùng DB.

Một service có thể nhận `Clock` và truyền giá trị cutoff bằng parameter:

```java
LocalDateTime now = LocalDateTime.now(clock);

List<SalesOrder> orders = em.createQuery(
    """
    SELECT o
    FROM SalesOrder o
    WHERE o.placedAt <= :now
    """,
    SalesOrder.class
)
.setParameter("now", now)
.getResultList();
```

`Clock` có thể được inject trong test. Nhưng cần rõ `LocalDateTime` không mang timezone: `Clock` phải phản ánh cùng quy ước timezone đã dùng để lưu `placedAt`.

Nếu lưu timestamp UTC hoặc `Instant`, tốt hơn nên sử dụng tham số kiểu phù hợp mapping và timezone policy; đừng tùy tiện convert qua default timezone.

## 13. `EXTRACT` trong Jakarta Persistence 3.1

Trước 3.1, lấy `YEAR`, `MONTH` từ timestamp thường cần:

- Provider extension như `YEAR(...)`.
- Hàm DB qua `FUNCTION(...)`.
- Lọc theo khoảng thời gian tính ở Java.
- Native SQL.

Từ 3.1, **`EXTRACT`** được chuẩn hóa:

```sql
SELECT EXTRACT(YEAR FROM o.placedAt)
FROM SalesOrder o
```

```sql
SELECT EXTRACT(MONTH FROM o.placedAt)
FROM SalesOrder o
```

```sql
SELECT EXTRACT(DAY FROM o.placedAt)
FROM SalesOrder o
```

Cú pháp:

```text
EXTRACT(thanh_phan FROM bieu_thuc_ngay_gio)
```

**Không đồng nhất với SQL Server `DATEPART('year', ...)` hoặc PostgreSQL `DATE_TRUNC('month', ...)`**, dù provider có thể dịch biểu thức JPQL sang SQL phù hợp.

### 13.1. Các thành phần được chuẩn hóa

| Thành phần | Ý nghĩa | Dạng kết quả |
|---|---|---|
| `YEAR` | Năm dương lịch. | Số nguyên. |
| `QUARTER` | Quý, 1 tới 4. | Số nguyên. |
| `MONTH` | Tháng, bắt đầu từ 1. | Số nguyên. |
| `WEEK` | Tuần theo ISO-8601. | Số nguyên. |
| `DAY` | Ngày trong tháng, bắt đầu từ 1. | Số nguyên. |
| `HOUR` | Giờ 0 tới 23. | Số nguyên. |
| `MINUTE` | Phút 0 tới 59. | Số nguyên. |
| `SECOND` | Giây, có thể gồm phần thập phân. | Số thực. |
| `DATE` | Phần ngày của datetime. | Thành phần ngày theo temporal mapping. |
| `TIME` | Phần thời gian trong ngày của datetime. | Thành phần thời gian theo temporal mapping. |

Không phải mọi loại temporal đều có mọi thành phần. Ví dụ `LocalDate` không có `HOUR`, `LocalTime` không có `YEAR`. Đặc tả không cho phép trích xuất thành phần mà biểu thức temporal không chứa.

### 13.2. Truy vấn tổng doanh thu theo tháng

```sql
SELECT
    EXTRACT(YEAR FROM o.placedAt),
    EXTRACT(MONTH FROM o.placedAt),
    SUM(o.totalAmount)
FROM SalesOrder o
WHERE o.status = :status
GROUP BY
    EXTRACT(YEAR FROM o.placedAt),
    EXTRACT(MONTH FROM o.placedAt)
ORDER BY
    EXTRACT(YEAR FROM o.placedAt),
    EXTRACT(MONTH FROM o.placedAt)
```

Bài toán này đòi hỏi ít nhất **Jakarta Persistence 3.1** nếu muốn `EXTRACT` là JPQL chuẩn; provider và dialect vẫn phải hỗ trợ cách dịch và kiểu dữ liệu đúng.

Nếu đang dùng JPA 2.2/3.0 mà provider chấp nhận `YEAR(o.placedAt)`, đó là khả năng riêng của provider, không phải cú pháp portable ở mức 2.2/3.0.

### 13.3. Lấy ngày và giờ bằng `EXTRACT`

```sql
SELECT
    EXTRACT(DATE FROM o.placedAt),
    EXTRACT(TIME FROM o.placedAt)
FROM SalesOrder o
```

Đây là cú pháp chuẩn từ 3.1. Nó giúp phân biệt hai nhóm:

- `EXTRACT(YEAR|MONTH|DAY|...)` trả thành phần số.
- `EXTRACT(DATE|TIME)` lấy phần ngày/thời gian.

Cần xác nhận kiểu Java của projection theo mapping và provider khi xây DTO typed query; không tự ép mọi kết quả temporal về `java.sql.Date` nếu entity dùng `java.time.LocalDate`.

### 13.4. Một lưu ý về `WEEK` và ranh giới năm

Tuần ISO-8601 có thể bắt đầu từ những ngày cuối tháng 12 và kết thúc ở đầu tháng 1. **Số tuần** và **năm dương lịch** không tự tạo thành cùng khái niệm với **ISO week-based year**.

Nếu báo cáo theo tuần ISO và năm ISO, cần định nghĩa rõ cách tính “năm tuần”, tránh ghép đơn giản `EXTRACT(YEAR ...)` với `EXTRACT(WEEK ...)` rồi nghĩ đó luôn là một định danh tuần đúng ở ranh giới năm.

Nếu use case yêu cầu chính xác ISO week-based year và đặc tả JPQL không cung cấp trường tương ứng, nên đánh giá biểu thức database-specific hoặc tính lịch ở tầng ứng dụng với timezone đã chốt.

## 14. Lọc theo ngày: khoảng nửa mở thường tốt hơn gọi hàm lên cột

Một yêu cầu phổ biến:

> Tìm mọi order tạo trong ngày 01/11/2026 theo timezone nghiệp vụ.

Cách viết dễ được nghĩ tới ở 3.1:

```sql
SELECT o
FROM SalesOrder o
WHERE EXTRACT(DATE FROM o.placedAt) = :targetDate
```

Nó ngắn gọn, nhưng có hai vấn đề:

1. DB có thể cần áp hàm lên **mọi giá trị trong cột `placed_at`**; index thường trên cột đó có thể khó dùng tối ưu.
2. Với dữ liệu có timezone hoặc yêu cầu theo ngày địa phương, nghĩa của `DATE` phụ thuộc quy ước lưu và chuyển đổi.

Một cách portable từ các phiên bản cũ:

```sql
SELECT o
FROM SalesOrder o
WHERE o.placedAt >= :startInclusive
  AND o.placedAt < :endExclusive
```

Java:

```java
LocalDate day = LocalDate.of(2026, 11, 1);

LocalDateTime start = day.atStartOfDay();
LocalDateTime end = day.plusDays(1).atStartOfDay();

List<SalesOrder> orders = em.createQuery(
    """
    SELECT o
    FROM SalesOrder o
    WHERE o.placedAt >= :start
      AND o.placedAt < :end
    """,
    SalesOrder.class
)
.setParameter("start", start)
.setParameter("end", end)
.getResultList();
```

Điểm mạnh:

- Không cần `EXTRACT` chuẩn của 3.1.
- Query có thể dùng index trên `placed_at` hiệu quả hơn, tùy DB/query plan.
- Không phụ thuộc độ chính xác timestamp microsecond/nanosecond để tính “cuối ngày”.
- Biểu diễn đúng khoảng **[đầu ngày, đầu ngày tiếp theo)**.

**Nhưng** với `LocalDateTime`, ví dụ trên giả định thời điểm DB lưu theo cùng **local wall-clock convention** của ngày nghiệp vụ. Nếu lưu `Instant` UTC hoặc timezone-aware timestamp, phải chuyển **hai ranh giới ngày trong zone nghiệp vụ** thành instant tương ứng thay vì lấy `LocalDateTime` không có zone.

### 14.1. Ngày có DST không nhất thiết dài 24 giờ

Ở timezone có daylight saving time:

```java
ZoneId businessZone = ZoneId.of("Europe/Berlin");
LocalDate targetDay = LocalDate.of(2026, 3, 29);

Instant from = targetDay
        .atStartOfDay(businessZone)
        .toInstant();

Instant to = targetDay.plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();
```

Thời lượng giữa `from` và `to` có thể khác 24 giờ vào ngày đổi giờ. Nếu đơn hàng lưu `Instant` theo UTC và provider hỗ trợ mapping tương ứng, dùng hai `Instant` này làm parameters cho khoảng half-open.

Không nên thay `plusDays(1)` theo lịch bằng `plusSeconds(86400)` khi tìm **một ngày địa phương** trong zone có DST.

### 14.2. So sánh “hôm nay” ở database với “hôm nay” của người dùng

`LOCAL DATE` và `CURRENT_DATE` lấy ngày hiện tại theo DB; người dùng ở timezone khác DB có thể đang ở một ngày khác. Nếu báo cáo theo ngày của người dùng, **định nghĩa timezone tại application boundary** rồi chuyển sang khoảng thời gian chuẩn. Không dựa mù quáng vào default timezone database server.

---

## 15. Kiểu temporal trong entity và các thay đổi ở 3.2

`java.time` đã có vai trò quan trọng trong mapping JPA trước 3.1. Khi lựa chọn hàm, cần tách:

1. **Kiểu Java mà entity lưu**.
2. **Hàm JPQL nào tạo/trích xuất giá trị temporal**.
3. **Cách JDBC/dialect ánh xạ và so sánh**.

Ví dụ:

```java
@Column(name = "placed_at")
private LocalDateTime placedAt;
```

Không có timezone trong kiểu `LocalDateTime`. Nó mô tả ngày giờ theo lịch, không phải một thời điểm tuyệt đối toàn cầu.

### 15.1. Các kiểu thời gian thường gặp

| Kiểu Java | Ý nghĩa | Điểm cần cân nhắc |
|---|---|---|
| `LocalDate` | Ngày không có giờ/zone. | Hợp cho birthday, ngày theo lịch. |
| `LocalTime` | Giờ trong ngày, không có ngày/zone. | Hợp cho giờ mở cửa theo lịch. |
| `LocalDateTime` | Ngày + giờ local, không có zone. | Cần quy định timezone nếu nó thực tế biểu diễn event time. |
| `Instant` | Một thời điểm tuyệt đối theo UTC timeline. | Thích hợp audit/event time khi provider/DB mapping hỗ trợ. |
| `OffsetDateTime` | Date/time gắn với offset. | Cần xem cách database bảo toàn offset và so sánh. |
| `java.sql.Date/Time/Timestamp` | Các kiểu JDBC legacy. | API cũ vẫn tồn tại nhưng 3.2 khuyến nghị dùng java.time cho code mới. |

Jakarta Persistence 3.2 bổ sung hỗ trợ chuẩn thêm cho `java.time.Instant` và `java.time.Year`, đồng thời **deprecate** nhiều API temporal legacy (ví dụ `Temporal`, `TemporalType`, các kiểu `java.sql.Date/Time/Timestamp` cho ứng dụng mới) theo định hướng chuyển sang `java.time`.

**Hỗ trợ mapping một kiểu Java** không có nghĩa JPQL có hàm “`CURRENT_INSTANT`” chuẩn tương ứng. Phải kiểm tra riêng nhóm hàm JPQL.

### 15.2. Dùng parameter type phù hợp

Nếu entity field là `LocalDateTime`:

```java
LocalDateTime cutoff = LocalDateTime.of(
    2026, 11, 1, 0, 0
);

List<SalesOrder> result = em.createQuery(
    """
    SELECT o
    FROM SalesOrder o
    WHERE o.placedAt >= :cutoff
    """,
    SalesOrder.class
)
.setParameter("cutoff", cutoff)
.getResultList();
```

Không nên chuyển tùy tiện `cutoff` sang `java.util.Date` hoặc `String` nếu provider hiểu rõ mapping Java temporal đúng từ thuộc tính.

### 15.3. Chính sách timezone cần được nhất quán

Một thiết kế thường dùng:

- Lưu các thời điểm sự kiện bằng UTC/`Instant`.
- Tính ranh giới ngày/tháng theo **ZoneId nghiệp vụ**.
- Truyền start/end đã chuyển sang UTC instant vào query.
- Hiển thị theo zone của người dùng tại tầng presentation.

Một hệ khác có thể cố ý lưu `LocalDateTime` theo timezone cửa hàng, nhưng phải viết rõ contract; không thể suy ra timezone từ một giá trị LocalDateTime đơn độc.

## 16. Criteria API tương ứng với nhóm hàm nền tảng

JPQL string query là một lựa chọn; **Criteria API** giúp xây biểu thức typed/dynamic hơn, nhất là khi điều kiện tìm kiếm thay đổi theo input.

Giả sử cần lọc tên khách không phân biệt chữ hoa/chữ thường:

```java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;
import java.util.List;
import java.util.Locale;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<SalesOrder> query =
        cb.createQuery(SalesOrder.class);

Root<SalesOrder> order = query.from(SalesOrder.class);

query.select(order).where(
    cb.equal(
        cb.lower(order.get("customerName")),
        "an"
    )
);

List<SalesOrder> rows = em.createQuery(query).getResultList();
```

`cb.lower(...)` tương ứng `LOWER` của JPQL.

Một số hàm Criteria API có từ lâu:

| JPQL | Criteria API thường dùng |
|---|---|
| `LOWER(x)` | `cb.lower(x)` |
| `UPPER(x)` | `cb.upper(x)` |
| `LENGTH(x)` | `cb.length(x)` |
| `SUBSTRING(x, start, length)` | `cb.substring(x, start, length)` |
| `TRIM(x)` | `cb.trim(x)` |
| `CONCAT(a,b)` | `cb.concat(a,b)` |
| `ABS(x)` | `cb.abs(x)` |
| `SQRT(x)` | `cb.sqrt(x)` |
| `MOD(a,b)` | `cb.mod(a,b)` |
| `CURRENT_DATE` | `cb.currentDate()` |
| `CURRENT_TIME` | `cb.currentTime()` |
| `CURRENT_TIMESTAMP` | `cb.currentTimestamp()` |

**Chú ý thứ tự của `LOCATE`:** JPQL sử dụng `LOCATE(needle, haystack)`; Criteria API dạng `cb.locate(x, pattern)` thường nhận **chuỗi nguồn trước, mẫu cần tìm sau**. Ví dụ:

```java
// JPQL: LOCATE('-', o.code)
cb.locate(order.get("code"), "-");
```

Đừng copy nguyên thứ tự tham số của JPQL sang Criteria API.

## 17. Criteria API được bổ sung theo phiên bản

### 17.1. Jakarta Persistence 3.1: numeric functions

Từ 3.1, CriteriaBuilder có thêm các phương thức tương ứng như:

```java
cb.ceiling(order.get("totalAmount"));
cb.floor(order.get("totalAmount"));
cb.round(order.get("totalAmount"), 0);
cb.sign(order.get("totalAmount"));
```

Các phương thức khác gồm `exp`, `ln` và `power`. Cú pháp generic/type inference cụ thể tùy Java expression type; khi dùng trong code production, nên để compiler và typed Criteria API kiểm tra thay vì ép kiểu `Expression` thô.

Ví dụ truy vấn chọn đơn có phần tiền tuyệt đối chênh lệch trên ngưỡng:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<SalesOrder> query =
        cb.createQuery(SalesOrder.class);

Root<SalesOrder> order =
        query.from(SalesOrder.class);

var diff = cb.diff(
        order.<BigDecimal>get("totalAmount"),
        new BigDecimal("100000.00")
);

query.select(order).where(
    cb.greaterThan(
        cb.abs(diff),
        new BigDecimal("50000.00")
    )
);

List<SalesOrder> result =
        em.createQuery(query).getResultList();
```

`cb.abs` và `cb.diff` đã có từ trước 3.1; ví dụ nhằm minh họa cách dùng typed numeric expressions, không ngụ ý `ABS` mới ở 3.1.

### 17.2. Jakarta Persistence 3.1: local date/time

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

var dbDate = cb.localDate();
var dbTime = cb.localTime();
var dbDateTime = cb.localDateTime();
```

Các expression tương ứng kiểu `LocalDate`, `LocalTime`, `LocalDateTime`.

Ví dụ:

```java
CriteriaQuery<SalesOrder> query =
        cb.createQuery(SalesOrder.class);

Root<SalesOrder> order = query.from(SalesOrder.class);

query.select(order).where(
    cb.lessThanOrEqualTo(
        order.<LocalDateTime>get("placedAt"),
        cb.localDateTime()
    )
);
```

### 17.3. `EXTRACT` trong Criteria API: chú ý mốc 3.2

Một điểm dễ nhầm:

- **JPQL `EXTRACT` được chuẩn hóa từ 3.1.**
- Phương thức **`CriteriaBuilder.extract(...)`** được bổ sung ở **3.2**.

Vì vậy, trong ứng dụng dùng **Jakarta 3.1**, JPQL string `EXTRACT(YEAR FROM ...)` có thể chuẩn, nhưng đừng tự giả định CriteriaBuilder 3.1 đã có method `extract(...)`.

Nếu cần tạo Criteria dynamic với YEAR trên nền 3.1:

- Có thể sử dụng `cb.function("...", resultType, ...)` với dialect đã kiểm chứng.
- Hoặc đưa ranh giới thời gian thành parameters, thường portable và index-friendly hơn.
- Hoặc chuyển phần report đặc thù thành JPQL string query có `EXTRACT` chuẩn 3.1.

Từ 3.2, có thể dùng `CriteriaBuilder.extract(...)` với temporal field/value type phù hợp theo API version, nhưng cần xây đúng generic typing. Không giả định nó tồn tại trong artifact `jakarta.persistence-api:3.1`.

### 17.4. Hàm chuỗi và cast Criteria 3.2

Theo bản 3.2, Criteria API được mở rộng đồng bộ với `LEFT`, `RIGHT`, `REPLACE`, `CAST` và các overload liên quan `CONCAT`. Nếu codebase phải tương thích 3.1, không gọi các method mới bằng cách “import đúng class” — class name `CriteriaBuilder` vẫn giống nhau nhưng **signature của version API cũ không có method mới**.

Khi chỉ cần lắp ghép biểu thức từ hai chuỗi, `cb.concat(a,b)` cổ điển vẫn là lựa chọn tương thích rộng.

## 18. `FUNCTION('...')`: escape hatch cho database functions

Từ những phiên bản JPA trước 3.1, JPQL hỗ trợ dạng gọi hàm DB:

```text
FUNCTION('ten_ham_database', arg1, arg2, ...)
```

Ví dụ một database có `DATE_TRUNC`:

```sql
SELECT FUNCTION('date_trunc', 'month', o.placedAt)
FROM SalesOrder o
```

Đây là ví dụ **đặc thù database/dialect**, không phải hàm date truncation được JPQL chuẩn bảo đảm trên mọi RDBMS.

### 18.1. Khi nào FUNCTION hợp lý?

- Dự án bị khóa ở JPA 2.2/3.0 nhưng database có một hàm chuẩn SQL mà use case cần gấp.
- Database có extension như full-text search, regex, JSON, geospatial hoặc date bucketing.
- Provider không có JPQL function tương đương và không muốn chuyển toàn bộ truy vấn sang native SQL.
- Báo cáo phụ thuộc một dialect cố định, có integration tests phù hợp.

Ví dụ lọc một mã có chứa ký tự đặc biệt qua hàm DB:

```sql
SELECT o
FROM SalesOrder o
WHERE FUNCTION('my_normalize', o.code) = :normalized
```

Đòi hỏi database thật sự có hàm `my_normalize` hoặc provider có cơ chế translate/registry thích hợp.

### 18.2. Ba loại không tương thích cần tách

Giả sử:

```sql
WHERE FUNCTION('date_trunc', 'month', o.placedAt) = :bucket
```

Có thể gặp:

1. **JPQL parsing/type error**: provider không biết kiểu trả về hoặc không cho gọi hàm ở vị trí đó.
2. **SQL generation error**: provider dịch cú pháp sai dialect.
3. **Database execution error**: hàm không tồn tại, argument type không đúng hoặc user DB không có quyền.

Cú pháp `FUNCTION` có trong JPA không bảo đảm **tên hàm, bộ tham số và kiểu kết quả** đều portable.

### 18.3. Criteria `cb.function(...)`

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<SalesOrder> query =
        cb.createQuery(SalesOrder.class);

Root<SalesOrder> root = query.from(SalesOrder.class);

// Ví dụ giả định database/provider có hàm my_normalize(String).
var normalized = cb.function(
    "my_normalize",
    String.class,
    root.get("code")
);

query.select(root).where(
    cb.equal(normalized, "SO2026001")
);
```

Tham số `String.class` giúp chỉ định **Java result type** mà Criteria mong đợi; nó không chứng minh mọi backend có hàm đó.

### 18.4. Không đưa tên hàm trực tiếp từ input người dùng

Dữ liệu người dùng nên đi qua **query parameters**. Tên hàm và cú pháp query là phần của **query structure**, nên phải được lựa chọn từ danh sách được ứng dụng kiểm soát.

Không tạo:

```java
String jpql = "SELECT FUNCTION('" + userInput
        + "', o.code) FROM SalesOrder o";
```

nếu `userInput` không tin cậy. Điều đó có nguy cơ tạo query không hợp lệ, mở rộng quyền tính toán không chủ đích hoặc dẫn tới injection tùy provider.

Dùng whitelist cho danh mục thao tác hợp lệ; giá trị tham số đi qua `setParameter(...)`.

### 18.5. Khi nào dùng native SQL thay vì FUNCTION?

Native SQL phù hợp hơn khi cần:

- Window functions hoặc SQL constructs không được bản JPQL đang dùng hỗ trợ.
- CTE/recursive query hay thao tác analytic phụ thuộc database.
- Function return type phức tạp và projection native rõ ràng hơn.
- Join tới table/view không được mapping trong entity model.
- Query plan đặc thù đã được kiểm chứng.

Đánh đổi: tên bảng/cột SQL, dialect, mapping result và test migration cần được duy trì; không còn portability kiểu JPQL.

## 19. Chọn hàm hay xử lý ở Java?

Không có câu trả lời cố định rằng “cứ tính ở DB” hoặc “cứ tính ở Java” luôn tốt.

| Yêu cầu | Nên cân nhắc DB/JPQL khi | Nên cân nhắc Java khi |
|---|---|---|
| `LOWER`/`TRIM` để lọc | Cần lọc ngay trên hàng triệu row, muốn DB trả đúng tập. | Chuẩn hóa dữ liệu đầu vào trước khi persist, tránh gọi hàm lặp. |
| `ROUND` tiền tệ | Report dùng chính sách rounding đã kiểm chứng trên dialect. | Business calculation cần precision/scale/rounding chính xác, có test deterministic. |
| `EXTRACT(YEAR)` | Cần group báo cáo trực tiếp ở DB và chấp nhận query plan. | Chỉ cần hiển thị năm từ vài DTO đã truy xuất. |
| `LOCAL DATETIME` | “Now” phải theo đồng hồ DB. | Cần fake clock/test deterministic hoặc timezone nghiệp vụ. |
| `REPLACE` mã định danh | Data cleanup/report ad hoc. | Chuẩn hóa code một lần khi nhập, lưu normalized field có index. |
| `POWER/EXP/LN` | Phân tích số học lượng dữ liệu lớn, không yêu cầu decimal exact. | Thuật toán miền ứng dụng phức tạp, floating-point policy rõ. |

**Một phép biến đổi nhỏ trên vài trăm object đã được tải** không nhất thiết cần một vòng truy vấn SQL khác. Nhưng **lọc hàng triệu row bằng Java sau khi tải toàn bộ** cũng là lựa chọn tốn bộ nhớ. Phân biệt **filter/aggregate tại DB** với **presentation transformation** ở Java.

## 20. Chỉ mục và cách đặt hàm trong `WHERE`

Một truy vấn:

```sql
SELECT o
FROM SalesOrder o
WHERE LOWER(o.customerName) = :search
```

có thể làm optimizer khó dùng index thường trên `customer_name`, tùy database. Tương tự:

```sql
WHERE EXTRACT(YEAR FROM o.placedAt) = 2026
```

có thể làm giảm khả năng dùng index thường trên `placed_at`.

Đừng coi cú pháp chuẩn JPQL đồng nghĩa tự tối ưu.

### 20.1. Giải pháp cho chuỗi

- Dùng **collation/case-insensitive index** nếu DB hỗ trợ và semantics phù hợp.
- Lưu một field chuẩn hóa (nếu bài toán cần normalized search) với constraint và lifecycle cập nhật rõ ràng.
- Dùng functional/expression index nếu DB hỗ trợ và query expression khớp.
- Xem execution plan thực tế.

Ví dụ expression index là **SQL dialect-specific**, không phải annotation `@Column` portable tự tạo được ở mọi database.

### 20.2. Giải pháp cho ngày giờ

Thay:

```sql
WHERE EXTRACT(YEAR FROM o.placedAt) = :year
```

bằng khoảng nửa mở:

```sql
WHERE o.placedAt >= :startOfYear
  AND o.placedAt < :startOfNextYear
```

khi mục tiêu là **lọc theo năm** và đã xác định timezone. Cách này thường rõ ràng hơn, ít ép DB tính hàm trên mọi row hơn.

### 20.3. Group theo tháng vẫn có giá trị của `EXTRACT`

Đối với báo cáo:

```sql
SELECT EXTRACT(YEAR FROM o.placedAt),
       EXTRACT(MONTH FROM o.placedAt),
       SUM(o.totalAmount)
FROM SalesOrder o
GROUP BY EXTRACT(YEAR FROM o.placedAt),
         EXTRACT(MONTH FROM o.placedAt)
```

nhóm tại DB có thể hiệu quả hơn đưa toàn bộ order về Java rồi group. Nhưng so sánh performance thực tế phải xét số hàng, index, memory và query plan. **Lọc theo range trước, group trên tập đã được giới hạn** là một hướng kết hợp thường hợp lý.

## 21. Sử dụng hàm trong `SELECT`, `WHERE`, `GROUP BY` và `HAVING`

### 21.1. `SELECT`: projection có tính toán

```sql
SELECT
    o.code,
    UPPER(o.customerName),
    ROUND(o.totalAmount, 0)
FROM SalesOrder o
```

Yêu cầu **3.1** vì `ROUND`; `UPPER` đã có trước.

Kết quả là một tuple/projection, không tự động là managed `SalesOrder` entity khi chỉ select scalar expressions.

### 21.2. `WHERE`: lọc

```sql
SELECT o
FROM SalesOrder o
WHERE LENGTH(o.code) >= :minimum
  AND ABS(o.totalAmount - :target) <= :tolerance
```

Những hàm trên đều thuộc bộ nền tảng, có thể dùng trên JPA 2.2 khi argument types phù hợp.

### 21.3. `GROUP BY` và `HAVING`: nhóm và lọc nhóm

Ví dụ nhóm doanh thu theo năm:

```sql
SELECT EXTRACT(YEAR FROM o.placedAt), SUM(o.totalAmount)
FROM SalesOrder o
WHERE o.status = :paid
GROUP BY EXTRACT(YEAR FROM o.placedAt)
HAVING SUM(o.totalAmount) > :minimumRevenue
```

`EXTRACT` yêu cầu 3.1; `SUM` và `HAVING` đã tồn tại trước.

### 21.4. `ORDER BY`: xét phiên bản và expression

Ví dụ:

```sql
SELECT o
FROM SalesOrder o
ORDER BY LOWER(o.customerName)
```

Hành vi chuẩn về cách đưa một scalar expression bất kỳ vào `ORDER BY` được làm rõ/mở rộng ở 3.2; với JPQL cũ, các giới hạn cú pháp `ORDER BY` cần được kiểm tra theo đặc tả/provider. Một provider có thể hỗ trợ `ORDER BY LOWER(...)` dù ứng dụng dùng mức JPA cũ, nhưng nếu yêu cầu portability nghiêm ngặt, cần xác nhận truy vấn trong bản chuẩn đích.

Nếu cần sắp theo một expression phức tạp, một DTO query rõ expression trong `SELECT`, hoặc cột sắp xếp được chuẩn hóa, có thể giảm bất định.

## 22. Constructor DTO và kiểu trả về của hàm

Khi dùng JPQL `SELECT NEW`, constructor Java phải khớp **số lượng và kiểu dữ liệu** của biểu thức.

Ví dụ DTO:

```java
package com.example.orders;

import java.math.BigDecimal;

public record MonthlyRevenue(
    Integer year,
    Integer month,
    BigDecimal total
) {}
```

JPQL:

```java
List<MonthlyRevenue> rows = em.createQuery(
    """
    SELECT NEW com.example.orders.MonthlyRevenue(
        EXTRACT(YEAR FROM o.placedAt),
        EXTRACT(MONTH FROM o.placedAt),
        SUM(o.totalAmount)
    )
    FROM SalesOrder o
    WHERE o.status = :status
    GROUP BY
        EXTRACT(YEAR FROM o.placedAt),
        EXTRACT(MONTH FROM o.placedAt)
    """,
    MonthlyRevenue.class
)
.setParameter("status", SalesOrder.Status.PAID)
.getResultList();
```

Ví dụ yêu cầu **3.1** trở lên, provider hỗ trợ kết quả numeric/temporal đúng theo đặc tả, và mapping `BigDecimal totalAmount`.

### 22.1. Kiểu trả về nên được nhìn từ đặc tả

| Biểu thức | Kiểu kết quả thường cần chú ý |
|---|---|
| `LENGTH`, `LOCATE` | Số nguyên. |
| `MOD`, `SIZE`, `INDEX` | Số nguyên. |
| `SIGN` | Số nguyên. |
| `SQRT`, `EXP`, `LN`, `POWER` | Số thực/`Double`. |
| `ROUND(x,n)` | Theo kiểu numeric của đối số `x` theo quy tắc chuẩn. |
| `EXTRACT(YEAR|MONTH|DAY|...)` | Integer (trừ `SECOND` là số thực). |
| `LOCAL DATE` | `LocalDate`. |
| `LOCAL TIME` | `LocalTime`. |
| `LOCAL DATETIME` | `LocalDateTime`. |
| `CURRENT_DATE` | `java.sql.Date`. |
| `CURRENT_TIME` | `java.sql.Time`. |
| `CURRENT_TIMESTAMP` | `java.sql.Timestamp`. |
| `CAST(expr AS LONG)` (3.2) | `Long`. |
| `CAST(expr AS STRING)` (3.2) | `String`. |

Không ép mọi kết quả số vào `BigDecimal` chỉ vì cột nguồn là decimal; một số hàm có **return type riêng theo đặc tả**.

### 22.2. `ROUND` và tính tiền

Ví dụ:

```java
BigDecimal databaseResult = em.createQuery(
    """
    SELECT ROUND(o.totalAmount, 0)
    FROM SalesOrder o
    WHERE o.id = :id
    """,
    BigDecimal.class
)
.setParameter("id", orderId)
.getSingleResult();
```

Trong hệ thống dùng BigDecimal, hãy integration test kiểu kết quả và rounding behavior trên provider/database đang triển khai trước khi dựa vào câu này cho xử lý tiền thật.

Nếu domain rule là `BigDecimal.setScale(0, RoundingMode.HALF_EVEN)`, thì **đừng mặc định `ROUND` của database luôn có đúng tie-breaking đó**.

## 23. Một chiến lược có thể dùng trên nhiều phiên bản

Khi thư viện cần chạy trên các mức JPA khác nhau, thiết kế API query theo **mức tương thích thấp nhất bắt buộc**.

### 23.1. Chuỗi prefix: dùng SUBSTRING cho nhiều bản

Nếu chỉ cần hai ký tự đầu của code:

```sql
SELECT SUBSTRING(o.code, 1, 2)
FROM SalesOrder o
```

Có thể dùng ở JPA 2.2/3.0/3.1/3.2. Không cần ép dùng `LEFT` của 3.2 trừ khi codebase đã chọn 3.2 và muốn biểu đạt trực tiếp hơn.

### 23.2. Lọc theo năm: dùng range khi chưa có EXTRACT

```java
LocalDateTime start = LocalDateTime.of(
    2026, 1, 1, 0, 0
);
LocalDateTime end = LocalDateTime.of(
    2027, 1, 1, 0, 0
);

List<SalesOrder> orders = em.createQuery(
    """
    SELECT o FROM SalesOrder o
    WHERE o.placedAt >= :from
      AND o.placedAt < :to
    """,
    SalesOrder.class
)
.setParameter("from", start)
.setParameter("to", end)
.getResultList();
```

Đây là cách không cần `EXTRACT`, dễ index-friendly hơn cho thao tác filter. Khi cần **GROUP BY năm** ngay ở DB, `EXTRACT` của 3.1 có giá trị riêng.

### 23.3. Nối chuỗi: CONCAT thay `||`

```sql
SELECT CONCAT(o.code, o.customerName)
FROM SalesOrder o
```

để hỗ trợ những bản trước 3.2.

### 23.4. `SIGN`: dùng CASE khi cần hỗ trợ JPA 2.2

```sql
SELECT CASE
         WHEN o.totalAmount > :target THEN 1
         WHEN o.totalAmount < :target THEN -1
         ELSE 0
       END
FROM SalesOrder o
```

Không cần function extension.

### 23.5. `REPLACE`: cân nhắc normalize từ lúc ghi

Nếu cần bỏ dấu `-` khỏi mã order trong mọi phiên bản, thường tốt hơn là xây rule chuẩn hóa trong application:

```java
public static String normalizeOrderCode(String code) {
    return code.replace("-", "").trim();
}
```

và lưu/truy vấn một field normalized riêng có index nếu dùng nhiều. `REPLACE` 3.2 thích hợp khi cần phép biến đổi trên dữ liệu hiện có ở DB; không phải mọi use case đều cần đẩy logic chuẩn hóa xuống SQL.

## 24. Ma trận quyết định cụ thể theo yêu cầu nghiệp vụ

| Yêu cầu | Phiên bản tối thiểu cho cú pháp JPQL chuẩn | Cách viết / fallback |
|---|---|---|
| Tìm tên không phân biệt hoa/thường | JPA cổ điển | `LOWER(name) = LOWER(:name)`. |
| Lấy hai ký tự đầu | JPA cổ điển | `SUBSTRING(code, 1, 2)`; 3.2 có `LEFT(code, 2)`. |
| Lấy ba ký tự cuối | 3.2 nếu dùng `RIGHT` | Bản cũ cân nhắc `SUBSTRING` + `LENGTH` với guard. |
| Xóa mọi dấu gạch ngang | 3.2 nếu dùng `REPLACE` | Bản cũ dùng Java normalize hoặc `FUNCTION` có chủ đích. |
| Nối các field | JPA cổ điển | `CONCAT`; 3.2 thêm `||`. |
| Độ dài/position trong chuỗi | JPA cổ điển | `LENGTH`, `LOCATE`. |
| Trị tuyệt đối/căn/mod | JPA cổ điển | `ABS`, `SQRT`, `MOD`. |
| Làm tròn số/lũy thừa/log | 3.1 | `ROUND`/`POWER`/`LN`; bản cũ dùng Java hoặc DB function. |
| Phân loại âm/0/dương | 3.1 cho `SIGN` | Bản cũ dùng `CASE WHEN`. |
| Ngày giờ DB kiểu java.sql | JPA cổ điển | `CURRENT_DATE`/`CURRENT_TIME`/`CURRENT_TIMESTAMP`. |
| Ngày giờ DB kiểu java.time | 3.1 | `LOCAL DATE`/`LOCAL TIME`/`LOCAL DATETIME`. |
| Lấy năm/tháng/quý từ timestamp | 3.1 | `EXTRACT`; bản cũ dùng range filter/DB-specific function. |
| Criteria API trích xuất trường temporal bằng method chuẩn | 3.2 | `CriteriaBuilder.extract(...)`; bản 3.1 đã có JPQL `EXTRACT` nhưng chưa có Criteria method này. |
| Ép scalar sang chuỗi hoặc chuỗi sang kiểu số cho phép | 3.2 | `CAST`; bản cũ xử lý mapping/Java hoặc DB-specific function. |
| Truy vấn full-text/regex/date_trunc của DB | Không phải hàm core ở các bản nêu trên | `FUNCTION` hoặc native SQL, kiểm thử dialect và type. |

**Đọc cột "phiên bản tối thiểu" theo nghĩa "được đặc tả bảo đảm", không phải "mọi provider cũ tuyệt đối không parse được".**

## 25. Đặt tên query và tập trung phần không portable

Một kiến trúc đơn giản là gom query đặc thù vào repository/query adapter thay vì rải `FUNCTION` ở tất cả service.

```text
Application Service
        |
        v
SalesOrderRepository
        |
        +-- JPQL portable
        |     - filter theo range
        |     - CONCAT / LOWER / LENGTH
        |     - ABS / MOD
        |
        +-- Analytics adapter cho dialect cụ thể
              - DATE_TRUNC
              - regex normalization
              - window functions
```

Lợi ích:

- Dễ xác định điểm cần sửa khi nâng cấp provider.
- Dễ tạo integration test riêng cho dialect.
- Business service không phải biết tên hàm PostgreSQL/MySQL/Oracle.
- Có thể chuyển một query về JPQL chuẩn khi nâng mức đặc tả mà không đổi service contract.

### 25.1. Nếu nhiều database khác nhau cùng được hỗ trợ

Thay vì giả định `DATE_TRUNC` giống nhau, có thể xây interface:

```java
public interface MonthlyRevenueQuery {
    List<MonthlyRevenue> find(
        LocalDateTime from,
        LocalDateTime to
    );
}
```

Mỗi adapter triển khai bằng JPQL `EXTRACT` chuẩn (nếu đủ) hoặc native SQL theo dialect; tầng service chỉ nhận DTO. Không cần tạo abstraction phức tạp nếu sản phẩm chỉ hỗ trợ một database cố định, nhưng **portability là một quyết định kiến trúc** chứ không phải thuộc tính tự động của câu query.

## 26. Kiểm thử tương thích theo ma trận, không chỉ chạy trên H2

Một câu JPQL có thể chạy trên H2 in-memory nhưng thất bại ở production database vì:

- Function name khác.
- Cách dùng tham số / kiểu implicit cast khác.
- Cách xử lý null khác.
- Locale/collation khác.
- Cách round tie-breaking khác.
- Timezone của session khác.
- Query optimizer hoặc index không giống nhau.
- Provider version của test và production không giống nhau.

### 26.1. Tạo ba nhóm test

**Nhóm A — Cú pháp và semantics chuẩn**

Chạy các truy vấn `LOWER`, `SUBSTRING`, `LOCATE`, `ABS`, `CURRENT_DATE` theo API/provider chuẩn tối thiểu đã chọn.

**Nhóm B — Những hàm mới theo phiên bản**

Với 3.1: `ROUND`, `POWER`, `LOCAL DATE`, `EXTRACT`.

Với 3.2: `REPLACE`, `LEFT`, `RIGHT`, `CAST`, `||`.

**Nhóm C — Provider/dialect extensions**

Mọi `FUNCTION('date_trunc',...)`, regex, JSON, timezone conversion hoặc hàm ngoài danh sách chuẩn.

Không chạy test của một cú pháp 3.2 rồi kết luận bản JPA 2.2 bắt buộc phải chấp nhận.

### 26.2. Chọn fixture chứa những giá trị khó

| Loại | Fixture | Muốn xác nhận |
|---|---|---|
| Chuỗi | `"  An  "` | `TRIM` có bỏ đúng khoảng trắng đầu/cuối? |
| Chuỗi | `"SO-2026-001"` | `SUBSTRING` bắt đầu từ 1; `LOCATE('-',...) = 3`. |
| Chuỗi | `"X"` | Lấy ba ký tự cuối có làm lỗi khi chuỗi ngắn? |
| Chuỗi | `null` ở field cho phép null | `COALESCE` và predicate xử lý ra sao? |
| Số | `12.3` và `-12.3` | `CEILING` khác `FLOOR` ở số âm. |
| Số | `2.5`, `-2.5` | Chính sách `ROUND` tại điểm giữa. |
| Số | `0` | `SIGN` và phép chia lấy dư. |
| Thời gian | `2026-12-31 23:59:59` | Nhóm năm/ngày, tránh lệch ranh giới. |
| Thời gian | Ngày DST theo zone nghiệp vụ | Khoảng ngày địa phương có thể không dài 24 giờ. |
| Thời gian | Thời điểm gần ranh giới năm ISO | Không gộp sai `WEEK` với năm dương lịch. |

### 26.3. Kiểm tra kiểu dữ liệu của projection

Một integration test có thể đọc `Object[]` trước để quan sát kiểu kết quả:

```java
List<Object[]> rows = em.createQuery(
    """
    SELECT
        o.code,
        LENGTH(o.code),
        ABS(o.totalAmount)
    FROM SalesOrder o
    """,
    Object[].class
).getResultList();

for (Object[] row : rows) {
    String code = (String) row[0];
    Integer length = (Integer) row[1];
    Number absolute = (Number) row[2];

    System.out.println(code + " / " + length + " / " + absolute);
}
```

Đây là phép kiểm tra giúp tránh ép mọi numeric expression sang `BigDecimal` hoặc `Double` khi chưa xem return type.

### 26.4. Test phải quan sát SQL thực sự

Bật SQL logging/metrics trong môi trường test khi phù hợp để xác nhận:

- `FUNCTION(...)` được chuyển sang hàm DB nào?
- `EXTRACT` dịch thành SQL gì trên dialect?
- Query sử dụng index hay scan?
- `LOWER(column)` có làm query plan đổi không?
- Có implicit casts ảnh hưởng số học/rounding không?

**Không cần tự suy đoán SQL từ JPQL** vì provider quyết định cách sinh SQL cuối cùng.

## 27. Các lỗi thường gặp khi chọn hàm không theo phiên bản

| Hiện tượng | Nguyên nhân khả dĩ | Hướng giải quyết |
|---|---|---|
| `ROUND(...)` không parse trên stack cũ | Chưa hỗ trợ JPQL chuẩn 3.1; provider cũ không có extension. | Nâng API/provider hoặc dùng Java/`FUNCTION`/native SQL có kiểm chứng. |
| `EXTRACT(YEAR FROM ...)` bị báo syntax error | Chạy JPA 2.2/3.0 hoặc provider chưa hỗ trợ 3.1. | Dùng range lọc cho date filters; nâng phiên bản nếu cần group theo thành phần. |
| `LOCAL_DATE` không hợp lệ | Dùng sai tên/hình thức; chuẩn là `LOCAL DATE`. | Viết đúng keyword có dấu cách và dùng stack 3.1+. |
| `LOCAL DATETIME` không có kết quả như JVM clock | Hàm dựa vào thời gian DB/session và timezone. | Định nghĩa clock/timezone policy; cân nhắc truyền parameter. |
| `REPLACE` chạy ở Hibernate nhưng fail ở provider khác trên mức JPA cũ | Hàm chỉ thành chuẩn JPQL ở 3.2. | Nâng 3.2 hoặc dùng abstraction DB-specific. |
| Toán tử `||` chạy ở SQL nhưng fail trong JPQL 3.1 | `||` chỉ thành toán tử JPQL chuẩn từ 3.2. | Dùng `CONCAT` để portable. |
| `CAST(... AS DECIMAL(18,2))` không portable | JPA 3.2 chỉ yêu cầu tập target cast tối thiểu. | Dùng mapping numeric chuẩn hoặc native SQL được kiểm thử. |
| `SUBSTRING(..., 0, 3)` cho kết quả khó hiểu | JPQL đếm vị trí từ 1, không phải 0. | Dùng `SUBSTRING(..., 1, 3)`. |
| `LOCATE(o.code, '-')` trả kết quả sai | Đảo vị trí needle/haystack. | JPQL `LOCATE('-', o.code)`. |
| `LOCATE` không tìm thấy nhưng code kiểm tra `-1` | Theo JPQL, không tìm thấy trả 0. | Kiểm tra `= 0` hoặc `> 0`. |
| `TRIM` không bỏ dấu gạch ngang ở giữa chuỗi | TRIM chỉ xử lý đầu/cuối. | `REPLACE` 3.2 hoặc chuẩn hóa ở Java. |
| `LOWER` trả kết quả khác giữa DB | Collation/locale/case folding khác. | Thiết kế collation và normalization thống nhất. |
| `ROUND` số tiền khác Java | Rounding mode, tie-breaking, numeric type khác. | Định nghĩa chuẩn tiền tệ và test DB/Java; ưu tiên domain decimal. |
| `POWER` có sai số thập phân | Hàm trả floating-point, không phải decimal exact. | Không dùng cho quy tắc tài chính yêu cầu exact. |
| `LN(0)` hoặc số âm lỗi | Đầu vào ngoài miền xác định. | Kiểm tra điều kiện `x > 0` hoặc policy xử lý lỗi. |
| `MOD` trên `BigDecimal` không hợp lệ | `MOD` chuẩn nhận integer arguments. | Chọn phép toán/kiểu đúng và policy domain. |
| `CURRENT_TIMESTAMP` trả `java.sql.Timestamp`, DTO muốn `LocalDateTime` | Khác kiểu temporal giữa legacy và java.time. | Dùng `LOCAL DATETIME` 3.1+ hoặc parameter typed. |
| Báo cáo theo ngày bị lệch do timezone | Dùng ngày DB thay ngày nghiệp vụ/user. | Định nghĩa ZoneId, chuyển ranh giới thời gian. |
| Lọc theo `EXTRACT(YEAR FROM column)` rất chậm | Expression trên cột làm giảm khả năng dùng index thường. | Chuyển sang range predicates hoặc expression index có chủ đích. |
| `CriteriaBuilder.extract(...)` không compile với API 3.1 | JPQL EXTRACT có ở 3.1 nhưng Criteria method thêm ở 3.2. | Nâng API hoặc dùng JPQL/function/range. |
| `cb.locate(...)` tìm sai | Criteria `locate` nhận source rồi pattern, khác thứ tự JPQL. | Kiểm tra signature CriteriaBuilder. |
| `FUNCTION('date_trunc',...)` lỗi trên database khác | Hàm DB-specific, không portable. | Tách adapter theo dialect hoặc query chuẩn. |
| Query dùng `FUNCTION` trả kiểu lạ | Provider không suy ra return type chuẩn cho hàm ngoài. | Kiểm chứng type/projection, đăng ký function nếu provider hỗ trợ. |
| `COUNT` và `SUM` có cùng default 0 | Nhầm aggregate semantics. | `COUNT` đếm, `SUM` có thể null; dùng `COALESCE` khi cần. |
| Chỉ nâng dependency API nhưng query mới vẫn lỗi runtime | Provider/dialect chưa nâng tương ứng. | Nâng stack theo compatibility matrix, chạy integration tests. |
| Code từ HQL docs không chạy ở EclipseLink | HQL có extension ngoài JPQL chuẩn. | Đối chiếu với đặc tả mục tiêu, viết JPQL portable hoặc adapter. |

## 28. Bài tập thực hành

### Bài 1 — Chuỗi mã đơn bắt đầu bằng `SO`, hỗ trợ JPA 2.2

Viết truy vấn không cần `LEFT` 3.2.

**Lời giải:**

```sql
SELECT o
FROM SalesOrder o
WHERE SUBSTRING(o.code, 1, 2) = 'SO'
```

Có thể dùng `LIKE 'SO%'` nếu semantics chỉ là tiền tố cố định và không cần lấy substring.

### Bài 2 — Mã đơn không có dấu gạch ngang, bắt buộc 3.2

**Lời giải:**

```sql
SELECT REPLACE(o.code, '-', '')
FROM SalesOrder o
```

Nếu stack cũ, cân nhắc normalized field hoặc Java transformation thay vì giả định REPLACE portable.

### Bài 3 — Lấy hai ký tự cuối, stack 3.2

**Lời giải:**

```sql
SELECT RIGHT(o.code, 2)
FROM SalesOrder o
```

### Bài 4 — Lấy trị tuyệt đối của chênh lệch số tiền, hỗ trợ JPA 2.2

**Lời giải:**

```sql
SELECT ABS(o.totalAmount - :target)
FROM SalesOrder o
```

### Bài 5 — Lấy dấu chênh lệch không có SIGN

**Lời giải:**

```sql
SELECT CASE
    WHEN o.totalAmount > :target THEN 1
    WHEN o.totalAmount < :target THEN -1
    ELSE 0
END
FROM SalesOrder o
```

### Bài 6 — Báo cáo doanh thu theo năm và tháng, stack 3.1

**Lời giải:**

```sql
SELECT
    EXTRACT(YEAR FROM o.placedAt),
    EXTRACT(MONTH FROM o.placedAt),
    SUM(o.totalAmount)
FROM SalesOrder o
WHERE o.status = :paid
GROUP BY
    EXTRACT(YEAR FROM o.placedAt),
    EXTRACT(MONTH FROM o.placedAt)
```

### Bài 7 — Lọc đơn trong tháng 11/2026, phải chạy trên stack cũ

**Lời giải:**

```sql
SELECT o
FROM SalesOrder o
WHERE o.placedAt >= :start
  AND o.placedAt < :end
```

Đặt `start = 2026-11-01T00:00` và `end = 2026-12-01T00:00` theo quy ước thời gian của cột. Không dùng `EXTRACT(MONTH ...) = 11` mà bỏ năm.

### Bài 8 — Truy vấn timestamp “đến thời điểm DB hiện tại” nhưng entity dùng LocalDateTime

Nếu stack **3.1+**:

```sql
SELECT o
FROM SalesOrder o
WHERE o.placedAt <= LOCAL DATETIME
```

Nếu cần test bằng fixed Clock hoặc timezone của ứng dụng, dùng tham số `:now` đã tính ở Java thay vì phụ thuộc DB.

### Bài 9 — Sử dụng hàm làm tròn ở mức JPA 3.0

**Câu hỏi:** viết `ROUND(o.totalAmount, 0)` có được bảo đảm portable không?

**Đáp án:** không. `ROUND` là hàm số chuẩn được thêm ở 3.1. Với 3.0, provider có thể hỗ trợ extension, nhưng nếu portability là yêu cầu, dùng Java decimal rounding theo quy tắc nghiệp vụ hoặc một DB function/native SQL có kiểm thử.

### Bài 10 — Criteria API EXTRACT trên 3.1

**Câu hỏi:** vì sao có thể viết `EXTRACT(YEAR FROM o.placedAt)` trong JPQL mà `cb.extract(...)` không compile?

**Đáp án:** JPQL EXTRACT được thêm vào 3.1, còn method `CriteriaBuilder.extract(...)` được bổ sung ở 3.2. Cần nâng API, dùng JPQL string hoặc dùng một hướng fallback.

## 29. Câu hỏi tự kiểm tra

**1. `java.persistence` và `jakarta.persistence` khác nhau ở đâu?**

Không có package `java.persistence` chuẩn trong ngữ cảnh này. JPA 2.x dùng `javax.persistence`, Jakarta Persistence 3.x dùng `jakarta.persistence`.

**2. Việc đổi namespace sang Jakarta Persistence 3.0 có tự bổ sung `ROUND` và `EXTRACT` chuẩn không?**

Không. Những hàm đó được chuẩn hóa từ 3.1.

**3. `REPLACE` và `LEFT` thuộc JPQL chuẩn từ phiên bản nào?**

Jakarta Persistence 3.2.

**4. `CURRENT_DATE` khác `LOCAL DATE` thế nào?**

Cả hai biểu diễn ngày hiện tại theo DB; `CURRENT_DATE` trả kiểu legacy `java.sql.Date`, `LOCAL DATE` (3.1+) trả `java.time.LocalDate`.

**5. Cú pháp đúng là `LOCAL_DATE` hay `LOCAL DATE`?**

Theo JPQL 3.1/3.2 chuẩn, dùng `LOCAL DATE`.

**6. `LOCATE('-', o.code)` tìm gì và nếu không có thì trả gì?**

Tìm ký tự `-` trong `o.code`, trả vị trí từ 1; nếu không thấy trả 0.

**7. `SUBSTRING(o.code, 1, 2)` dùng index 0 hay 1?**

Bắt đầu từ 1; lấy 2 ký tự.

**8. `TRIM` có thay thế `REPLACE` không?**

Không. TRIM xử lý đầu/cuối, REPLACE xử lý các lần xuất hiện trong chuỗi.

**9. `POWER` và `LN` có nên dùng trực tiếp để tính tiền yêu cầu decimal exact không?**

Cần hết sức thận trọng; nhóm hàm này có semantics kết quả floating-point. Tính tiền quan trọng nên dùng chính sách decimal/rounding rõ ràng và kiểm thử.

**10. Có thể dùng `EXTRACT(MONTH FROM o.placedAt) = 11` để lấy tháng 11/2026 không?**

Không đủ vì sẽ lấy tháng 11 của mọi năm. Cần thêm năm hoặc dùng khoảng thời gian [2026-11-01, 2026-12-01).

**11. Vì sao filter theo range có thể tốt hơn EXTRACT trên cột?**

Vì tránh áp hàm lên mỗi giá trị cột và có thể giúp optimizer sử dụng index thường hiệu quả hơn.

**12. JPQL `FUNCTION('date_trunc', ...)` có portable không?**

Cú pháp FUNCTION là chuẩn, nhưng **hàm date_trunc cụ thể** không được JPQL bảo đảm trên mọi DB.

**13. `CriteriaBuilder.extract` có cùng mốc xuất hiện với JPQL `EXTRACT` không?**

Không: JPQL 3.1, Criteria method 3.2.

**14. Trong Criteria API, thứ tự `cb.locate(source, pattern)` giống JPQL `LOCATE(pattern, source)` không?**

Không; thứ tự khác nhau, cần đọc đúng signature.

**15. Đã dùng Jakarta Persistence API 3.2 thì mọi provider có chạy `CAST` không?**

Không thể kết luận chỉ từ dependency API. Provider phải thực thi mức đặc tả và dialect database phù hợp.

**16. `CAST(o.id AS STRING)` có nghĩa mọi kiểu SQL cast khác đều được chuẩn hóa ở 3.2 không?**

Không; 3.2 chỉ yêu cầu một tập phép chuyển kiểu nhất định. Những cast khác cần kiểm tra provider/dialect.

**17. Khi nào nên dùng DTO projection thay vì fetch entity rồi biến đổi?**

Khi chỉ cần các giá trị hiển thị/tổng hợp hoặc số lượng hàng lớn; DTO có thể giảm dữ liệu phải truyền và state JPA không cần quản lý.

**18. Vì sao phải test cùng database production khi dùng `ROUND` hay xử lý timezone?**

Vì kiểu số, quy tắc làm tròn, đồng hồ DB/session, collation và SQL dialect có thể khác giữa test DB và production.

## 30. Tổng kết: chọn hàm bằng một thứ tự ưu tiên rõ ràng

Việc chọn hàm trong JPQL nâng cao không chỉ là “viết cú pháp nào ngắn nhất”. Một quyết định đúng nên xét:

1. **Mức đặc tả thấp nhất dự án cam kết hỗ trợ.**
2. **Provider có triển khai hàm chuẩn đó không.**
3. **Database/dialect có semantics kết quả mong muốn không.**
4. **Kiểu Java/projection có khớp hàm không.**
5. **Hàm ở WHERE/GROUP BY có ảnh hưởng index và hiệu năng không.**
6. **Có phương án portable hơn bằng range predicate, CASE, CONCAT hoặc DTO không.**
7. **Phần nào cần chính xác nghiệp vụ (tiền/timezone), phần nào chỉ để hiển thị/report.**

Bảng ghi nhớ:

```text
JPA 2.2 / Jakarta 3.0
  Chuỗi: CONCAT, SUBSTRING, TRIM, LOWER, UPPER, LENGTH, LOCATE
  Số:    ABS, SQRT, MOD (+ SIZE, INDEX và arithmetic operators)
  Time:  CURRENT_DATE, CURRENT_TIME, CURRENT_TIMESTAMP
  Khác:  CASE, COALESCE, NULLIF, FUNCTION('db_name', ...)

Jakarta Persistence 3.1
  + CEILING, FLOOR, ROUND, POWER, EXP, LN, SIGN
  + LOCAL DATE, LOCAL TIME, LOCAL DATETIME
  + EXTRACT(YEAR|MONTH|...|DATE|TIME FROM datetime)

Jakarta Persistence 3.2
  + REPLACE, LEFT, RIGHT
  + toán tử nối chuỗi ||
  + CAST trong tập chuyển kiểu được quy định
  + CriteriaBuilder.extract(...) và các Criteria enhancements
```

Hai quy tắc thực hành hữu ích nhất:

- **Ưu tiên hàm JPQL chuẩn ở đúng phiên bản** khi truy vấn thực sự cần xử lý tại database.
- **Khi chức năng chưa được chuẩn hóa**, lựa chọn có chủ đích giữa **viết khác đi bằng tính năng cũ**, **chuyển xử lý về Java**, **`FUNCTION(...)`**, hoặc **native SQL**, rồi kiểm thử trên provider/database mục tiêu.

Với ngày giờ, luôn **quy định timezone và type**; với số tiền, luôn **quy định precision/rounding**; với chuỗi, luôn **xác định collation/normalization**. Chỉ khi đó một câu JPQL chạy thành công mới thực sự cho kết quả nghiệp vụ đúng.

### Tài liệu tham khảo chính thức

- [Jakarta Persistence — các phiên bản đặc tả](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence 3.0 — tài liệu đặc tả](https://jakarta.ee/specifications/persistence/3.0/)
- [Jakarta Persistence 3.1 — toàn văn đặc tả](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Jakarta Persistence 3.1 — thông tin thay đổi của bản phát hành](https://projects.eclipse.org/projects/ee4j.jpa/releases/3.1)
- [Jakarta Persistence 3.2 — toàn văn đặc tả](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Persistence 3.2 — danh sách tính năng mới](https://jakarta.ee/specifications/persistence/3.2/)
- [Jakarta Persistence 4.0 — trạng thái phát triển](https://jakarta.ee/specifications/persistence/4.0/)
