# Gán tham số và đọc giá trị đầu ra

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Thủ tục lưu trữ

Trong JPA, phần lớn thao tác dữ liệu được thực hiện bằng `EntityManager`, JPQL, Criteria API hoặc repository. Tuy nhiên, có những hệ thống đã sở hữu **stored procedure (thủ tục lưu trữ)** ở database để xử lý thống kê, kiểm soát một quy trình ghi dữ liệu, tích hợp hệ thống cũ hoặc thực hiện phép tính chuyên biệt cho hệ quản trị.

Để gọi thủ tục đó từ Java, không chỉ cần biết **tên procedure**. Ứng dụng còn phải hiểu **loại và thứ tự của các tham số**, **giá trị nào truyền vào**, **giá trị nào đọc lại**, thời điểm **thực thi**, cách xử lý **result set**, ranh giới **transaction**, và những khác biệt giữa JPA provider/SQL dialect/JDBC driver.

Jakarta Persistence cung cấp `StoredProcedureQuery` cùng `ParameterMode` để biểu diễn các chế độ tham số thông dụng:

- **`IN`:** Java truyền giá trị vào procedure.
- **`OUT`:** procedure trả một giá trị qua tham số đầu ra.
- **`INOUT`:** Java truyền giá trị ban đầu và procedure trả giá trị đã xử lý.
- **`REF_CURSOR`:** procedure trả cursor chứa nhiều dòng; khả năng hỗ trợ tùy database và provider.

Bài học đi từ ví dụ database và Java nhất quán đến các trường hợp kết quả phức tạp, lỗi thường gặp và bài thực hành. Mục tiêu là **biết đọc chính xác output của một lời gọi procedure bằng JPA**, không nhầm output parameter với kết quả `SELECT` hoặc với số hàng được cập nhật.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khi nào dùng `StoredProcedureQuery` thay vì JPQL hoặc native query.
2. Phân biệt tham số `IN`, `OUT`, `INOUT` và `REF_CURSOR` theo chiều dữ liệu.
3. Gọi một stored procedure bằng `EntityManager.createStoredProcedureQuery()`.
4. Khai báo tham số bằng tên hoặc vị trí với `registerStoredProcedureParameter`.
5. Truyền giá trị bằng `setParameter` và đọc output bằng `getOutputParameterValue`.
6. Hiểu rõ `execute()` trả về `boolean` có nghĩa gì và tại sao nó **không phải** kết quả nghiệp vụ.
7. Phân biệt **output parameter**, **result set** và **update count**.
8. Xử lý nhiều result sets/update counts trước khi đọc output để tăng tính portable.
9. Dùng `@NamedStoredProcedureQuery` để khai báo metadata thay vì lặp cấu hình ở từng lời gọi.
10. Xử lý kiểu `Integer`, `Long`, `BigDecimal`, `String`, giá trị `NULL` và những conversion có thể phụ thuộc driver.
11. Biết khi nào `REF_CURSOR` cần cách xử lý riêng và vì sao không thể áp dụng một ví dụ cursor cho mọi DBMS.
12. Đặt lời gọi procedure ghi dữ liệu trong transaction phù hợp và không nhầm `flush` với `commit`.
13. Xử lý exception, rollback, đóng `EntityManager` và kiểm soát quyền thực thi procedure.
14. Tổ chức lời gọi trong service/Spring Data JPA với API rõ ràng, dễ kiểm thử.
15. Kiểm tra SQL/database behavior thực tế trước khi triển khai production.

## 2. Stored procedure khác query thông thường thế nào?

Một câu JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :paidStatus
```

trả về danh sách các entity `PurchaseOrder` theo mapping JPA.

Stored procedure là đối tượng được **định nghĩa ở database**. Nó có thể chứa nhiều câu SQL, biến cục bộ, nhánh điều kiện và tham số đầu ra.

Một lời gọi có thể nhận:

```text
ĐẦU VÀO:
  customerId = 15
  reportLabel = "API"

DATABASE:
  CALL sp_customer_paid_stats(...)

ĐẦU RA:
  paidCount = 3
  paidTotal = 420.00
  reportLabel = "API:CUSTOMER-15"
```

Nó có thể **không trả về một bảng kết quả nào** dù vẫn trả ba giá trị qua OUT/INOUT. Ngược lại, một procedure có thể trả nhiều result sets nhưng **không có OUT parameter**.

**Ba kênh kết quả cần phân biệt**:

| Kênh | Cách hiểu | API JPA thường dùng |
|---|---|---|
| **OUT/INOUT parameter** | Giá trị gắn với tham số đầu ra | `getOutputParameterValue(name/position)` |
| **Result set** | Tập hàng kết quả do procedure trả ra | `getResultList()`, đôi khi `getSingleResult()` |
| **Update count** | Số hàng chịu ảnh hưởng bởi một thao tác cập nhật được trả về như kết quả của procedure | `getUpdateCount()` |

Một result set có nhiều dòng không tự động trở thành một OUT parameter. Tương tự, `execute()` không trả về tổng tiền hoặc số lượng bản ghi; nó chỉ cung cấp thông tin ban đầu về loại kết quả.

## 3. Các kiểu ParameterMode

Import:

```java
import jakarta.persistence.ParameterMode;
```

| Chế độ | Java có truyền giá trị ban đầu? | Java có đọc output? | Ví dụ |
|---|---|---|---|
| `ParameterMode.IN` | Có | Không phải OUT | Mã khách hàng |
| `ParameterMode.OUT` | Không đặt input như IN | Có | Tổng tiền thanh toán |
| `ParameterMode.INOUT` | Có | Có | Nhãn được chuẩn hóa |
| `ParameterMode.REF_CURSOR` | Thường không theo nghĩa scalar IN/OUT | Kết quả cursor, hỗ trợ tùy provider | Danh sách đơn hàng |

### 3.1. IN

```text
Java -- customer_id = 15 --> Stored procedure
```

`IN` là giá trị đầu vào. Thông thường sẽ có:

```java
sp.registerStoredProcedureParameter(
    "p_customer_id", Long.class, ParameterMode.IN);

sp.setParameter("p_customer_id", customerId);
```

Không dùng `getOutputParameterValue("p_customer_id")` để đọc lại như một OUT parameter.

### 3.2. OUT

```text
Stored procedure -- paid_total = 420.00 --> Java
```

`OUT` được đăng ký:

```java
sp.registerStoredProcedureParameter(
    "p_paid_total", BigDecimal.class, ParameterMode.OUT);
```

Sau khi procedure thực thi và các kết quả trung gian được xử lý phù hợp, đọc:

```java
BigDecimal total =
    (BigDecimal) sp.getOutputParameterValue("p_paid_total");
```

### 3.3. INOUT

```text
Java -- label="API" --> procedure
Java <-- label="API:CUSTOMER-15" -- procedure
```

Phải đăng ký `INOUT`, đặt giá trị ban đầu rồi đọc giá trị đầu ra:

```java
sp.registerStoredProcedureParameter(
    "p_label", String.class, ParameterMode.INOUT);

sp.setParameter("p_label", "API");

sp.execute();

String processed =
    (String) sp.getOutputParameterValue("p_label");
```

Một lỗi thường gặp là đăng ký `INOUT` nhưng **quên `setParameter`** trước khi execute.

### 3.4. REF_CURSOR

`REF_CURSOR` không phải một chuỗi hoặc số đơn. Nó đại diện cho con trỏ/tập kết quả từ database, được hỗ trợ bởi các cơ sở dữ liệu và provider cụ thể. Việc đọc các result sets từ cursor, vị trí của nó trong trình tự kết quả và cách database khai báo cursor cần được kiểm chứng trên stack thực tế.

Không nên áp dụng một công thức Oracle, PostgreSQL hoặc SQL Server cho tất cả DBMS.

---

## 4. Ví dụ xuyên suốt: tính thống kê đơn hàng đã thanh toán

Ta giả định có hai bảng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(19, 2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

Dữ liệu mẫu:

```sql
INSERT INTO customers (id, full_name) VALUES
    (10, 'Nguyen An'),
    (20, 'Tran Binh');

INSERT INTO purchase_orders
    (id, customer_id, order_status, total_amount)
VALUES
    (101, 10, 'PAID', 150.00),
    (102, 10, 'PAID', 270.00),
    (103, 10, 'NEW', 60.00),
    (104, 20, 'CANCELLED', 90.00);
```

Yêu cầu procedure:

- Nhận `p_customer_id` là mã khách.
- Trả `p_paid_count` là số đơn `PAID`.
- Trả `p_paid_total` là tổng tiền đơn `PAID`.
- Nhận và cập nhật `p_label` là một nhãn dùng trong báo cáo.

Với khách 10, kết quả dự kiến:

```text
customerId = 10
paidCount = 2
paidTotal = 420.00
label input = "API"
label output = "API:CUSTOMER-10"
```

Với khách 20, không có đơn PAID:

```text
paidCount = 0
paidTotal = 0.00
```

**Điểm quan trọng:** `COUNT` có thể bằng 0, còn `SUM` khi không có giá trị thường là `NULL`. Procedure sẽ dùng `COALESCE` để biểu diễn tổng bằng 0 trong ví dụ nghiệp vụ này.

## 5. Định nghĩa procedure ở database

Đoạn sau minh họa cú pháp **MySQL**. Nó không phải SQL portable cho PostgreSQL, Oracle hoặc SQL Server. Trong MySQL CLI/Workbench, `DELIMITER` là lệnh của công cụ client, không phải phần của SQL procedure gửi qua JDBC.

```sql
DELIMITER $$

CREATE PROCEDURE sp_customer_paid_stats(
    IN p_customer_id BIGINT,
    OUT p_paid_count BIGINT,
    OUT p_paid_total DECIMAL(19, 2),
    INOUT p_label VARCHAR(255)
)
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(o.total_amount), 0)
    INTO
        p_paid_count,
        p_paid_total
    FROM purchase_orders o
    WHERE o.customer_id = p_customer_id
      AND o.order_status = 'PAID';

    SET p_label = CONCAT(
        COALESCE(p_label, 'REPORT'),
        ':CUSTOMER-',
        p_customer_id
    );
END $$

DELIMITER ;
```

Đặc điểm:

1. `p_customer_id` chỉ đưa dữ liệu **vào**.
2. `p_paid_count` chỉ đưa thống kê **ra**.
3. `p_paid_total` chỉ đưa tổng **ra**.
4. `p_label` có giá trị đầu vào và được procedure **thay thế bằng giá trị đầu ra**.
5. `SELECT ... INTO` trong MySQL gán giá trị vào biến OUT; **không phát một result set riêng ra client** ở ví dụ này.
6. Procedure không sửa bảng, chỉ đọc và tính toán.
7. Tên tham số phải khớp với cách ứng dụng đăng ký theo tên nếu driver/provider hỗ trợ named registration.

### 5.1. Thử procedure trực tiếp trong MySQL

```sql
SET @count_value = NULL;
SET @total_value = NULL;
SET @label_value = 'API';

CALL sp_customer_paid_stats(
    10,
    @count_value,
    @total_value,
    @label_value
);

SELECT @count_value, @total_value, @label_value;
```

Nếu thủ tục chưa hoạt động đúng ngay trong database, **đừng vội tìm lỗi ở JPA**. Hãy kiểm tra schema, dữ liệu, quyền EXECUTE và tham số ở database trước.

### 5.2. Giá trị của ví dụ

Dùng một procedure chỉ trả scalar OUT/INOUT giúp cô lập bài học về **đăng ký, gán và đọc tham số** khỏi một vấn đề khác: mapping result sets thành entity hoặc DTO.

Ở các phần sau, ta mới xét result sets, update counts, cursor và multi-result procedures.

---

## 6. API StoredProcedureQuery

Các type cần import:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

import java.math.BigDecimal;
```

Tạo query:

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_customer_paid_stats");
```

Tên `"sp_customer_paid_stats"` là **tên procedure vật lý ở database**. Nó không phải tên entity và không phải JPQL query.

Các bước làm việc thông thường:

```text
1. createStoredProcedureQuery(procedureName)
           |
2. registerStoredProcedureParameter(...)
           |
3. setParameter(...) cho IN/INOUT
           |
4. execute()
           |
5. consume result sets/update counts nếu có
           |
6. getOutputParameterValue(...) cho OUT/INOUT
```

### 6.1. Vì sao phải register?

JPA cần biết:

- Tham số nào tồn tại.
- Tham số ở **vị trí hoặc tên** nào.
- Java type tương ứng.
- Tham số là IN, OUT, INOUT hay REF_CURSOR.

Chỉ gọi `setParameter("p_customer_id", 10L)` mà chưa đăng ký các tham số thích hợp không phải mẫu portable cho `StoredProcedureQuery`.

### 6.2. Tên procedure và tên named query không giống nhau

```java
em.createStoredProcedureQuery("sp_customer_paid_stats");
```

dùng procedure name ở database.

```java
em.createNamedStoredProcedureQuery("Customer.paidStats");
```

dùng **tên đã khai báo trong `@NamedStoredProcedureQuery`**. Hai tên có thể khác nhau và phục vụ hai tầng metadata khác nhau.

---

## 7. Ví dụ Java hoàn chỉnh: đăng ký tham số theo tên

Giả sử bạn có một `EntityManager em` và driver/provider hỗ trợ named procedure parameters.

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_customer_paid_stats");

sp.registerStoredProcedureParameter(
    "p_customer_id", Long.class, ParameterMode.IN);

sp.registerStoredProcedureParameter(
    "p_paid_count", Long.class, ParameterMode.OUT);

sp.registerStoredProcedureParameter(
    "p_paid_total", BigDecimal.class, ParameterMode.OUT);

sp.registerStoredProcedureParameter(
    "p_label", String.class, ParameterMode.INOUT);

// Chỉ gán input cho IN và INOUT.
sp.setParameter("p_customer_id", 10L);
sp.setParameter("p_label", "API");

// Thực thi procedure.
sp.execute();

// Procedure mẫu không trả result set hay update count.
Number rawCount =
    (Number) sp.getOutputParameterValue("p_paid_count");

BigDecimal paidTotal =
    (BigDecimal) sp.getOutputParameterValue("p_paid_total");

String label =
    (String) sp.getOutputParameterValue("p_label");

long paidCount = rawCount.longValue();

System.out.println("Count: " + paidCount);
System.out.println("Total: " + paidTotal);
System.out.println("Label: " + label);
```

Với dữ liệu mẫu của customer 10, dự kiến:

```text
Count: 2
Total: 420.00
Label: API:CUSTOMER-10
```

**Lưu ý:** đoạn trên giả định procedure chỉ có output parameters, **không có result sets hoặc update counts cần consume**. Với procedure tạo thêm kết quả, nên duyệt và xử lý chúng trước khi đọc OUT để có tính portable cao hơn; xem phần về multi-result.

### 7.1. Vì sao dùng Number cho COUNT?

Java type thực tế của output số nguyên có thể chịu ảnh hưởng SQL type, JDBC driver và provider. Một số nền tảng trả `Long`, nền tảng khác có thể trả một `Number` khác. Với dữ liệu COUNT, có thể dùng:

```java
Object raw = sp.getOutputParameterValue("p_paid_count");

if (!(raw instanceof Number number)) {
    throw new IllegalStateException(
        "Expected numeric paid count but got: " + raw);
}

long count = number.longValue();
```

Nếu chạy Java cũ chưa hỗ trợ pattern matching cho `instanceof`, viết:

```java
if (!(raw instanceof Number)) {
    throw new IllegalStateException("Invalid count output");
}
long count = ((Number) raw).longValue();
```

Tuy nhiên, phải chú ý **quy mô giá trị và precision**. Không chuyển `BigInteger` rất lớn thành `long` mà không kiểm tra overflow nếu domain có khả năng vượt giới hạn.

### 7.2. Kiểu BigDecimal cần nhất quán

`DECIMAL(19,2)` tương ứng hợp lý với `BigDecimal`. Không dùng `double` cho số tiền chỉ để ép cast đơn giản.

Nếu database procedure trả DECIMAL nhưng driver/provider trả type khác trong một cấu hình đặc biệt, hãy xử lý conversion có kiểm soát và kiểm thử. Không dùng `new BigDecimal(double)` rồi giả định biểu diễn thập phân luôn chính xác.

---

## 8. Đăng ký tham số theo vị trí

Ngoài theo tên, JPA hỗ trợ đăng ký theo vị trí:

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_customer_paid_stats");

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN);

sp.registerStoredProcedureParameter(
    2, Long.class, ParameterMode.OUT);

sp.registerStoredProcedureParameter(
    3, BigDecimal.class, ParameterMode.OUT);

sp.registerStoredProcedureParameter(
    4, String.class, ParameterMode.INOUT);

sp.setParameter(1, 10L);
sp.setParameter(4, "API");

sp.execute();

Number count =
    (Number) sp.getOutputParameterValue(2);

BigDecimal total =
    (BigDecimal) sp.getOutputParameterValue(3);

String label =
    (String) sp.getOutputParameterValue(4);
```

Các vị trí `1,2,3,4` tương ứng với thứ tự khai báo trong procedure mẫu. Trong API JPA về stored procedure, positional parameters thường bắt đầu từ **1**.

### 8.1. Nên chọn tên hay vị trí?

| Tiêu chí | Theo tên | Theo vị trí |
|---|---|---|
| Đọc code | Dễ hiểu `p_paid_total` là gì | Cần nhớ vị trí 3 |
| Thay đổi thứ tự DB parameters | Có thể ít tác động nếu driver/provider hỗ trợ tên chính xác | Dễ sai khi thứ tự thay đổi |
| Tính tương thích | Driver/database có thể giới hạn named binding | Một số hệ thống dễ xử lý positional hơn |
| Cần review contract | Tên và kiểu phải khớp | Số vị trí, kiểu và thứ tự phải khớp |
| Cách gọi JPA | `setParameter("name", value)` | `setParameter(1, value)` |

Không nên tự tin rằng named registration luôn hoạt động trên mọi stored procedure/database. Với hệ quản trị hoặc driver không hỗ trợ named parameters trong callable statement theo cách provider sử dụng, positional registration có thể là lựa chọn thực tế hơn.

### 8.2. Đừng trộn hai cơ chế tùy tiện

Cần dùng **một quy ước rõ ràng cho mỗi procedure call**. Nếu đăng ký bằng vị trí nhưng lại gọi `getOutputParameterValue("p_paid_total")` khi query không biết tên này, có thể nhận `IllegalArgumentException`.

Nên nhất quán: đăng ký, set và đọc output theo cùng hệ tên/vị trí.

---

## 9. Một class dịch vụ đóng gói lời gọi

Thay vì để controller thao tác trực tiếp trên `StoredProcedureQuery`, ta định nghĩa kiểu kết quả rõ ràng.

```java
package demo.dto;

import java.math.BigDecimal;

public record PaidStats(
    Long customerId,
    long paidCount,
    BigDecimal paidTotal,
    String reportLabel
) {}
```

Một DAO/service dùng `EntityManager` do caller quản lý:

```java
package demo.repository;

import demo.dto.PaidStats;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

import java.math.BigDecimal;
import java.util.Objects;

public final class CustomerStatisticsProcedure {

    public PaidStats fetch(
            EntityManager em,
            long customerId,
            String inputLabel) {

        Objects.requireNonNull(em, "em");
        Objects.requireNonNull(inputLabel, "inputLabel");

        StoredProcedureQuery query = em.createStoredProcedureQuery(
            "sp_customer_paid_stats");

        query.registerStoredProcedureParameter(
            "p_customer_id", Long.class, ParameterMode.IN);

        query.registerStoredProcedureParameter(
            "p_paid_count", Long.class, ParameterMode.OUT);

        query.registerStoredProcedureParameter(
            "p_paid_total", BigDecimal.class, ParameterMode.OUT);

        query.registerStoredProcedureParameter(
            "p_label", String.class, ParameterMode.INOUT);

        query.setParameter("p_customer_id", customerId);
        query.setParameter("p_label", inputLabel);

        query.execute();

        Object rawCount =
            query.getOutputParameterValue("p_paid_count");

        if (!(rawCount instanceof Number)) {
            throw new IllegalStateException(
                "Stored procedure returned nonnumeric count");
        }

        long paidCount = ((Number) rawCount).longValue();

        BigDecimal total = (BigDecimal)
            query.getOutputParameterValue("p_paid_total");

        String label = (String)
            query.getOutputParameterValue("p_label");

        return new PaidStats(
            customerId,
            paidCount,
            total,
            label
        );
    }
}
```

Đoạn mã dành cho **procedure mẫu chỉ dùng scalar parameters**. Nếu database trả thêm result sets hoặc update counts, phải bổ sung xử lý trước khi lấy output.

### 9.1. Vì sao đưa về DTO?

- Caller không cần nhớ vị trí OUT parameter.
- Output được đặt tên và type rõ ràng.
- Có thể kiểm tra giá trị bất thường tập trung tại một điểm.
- Service có thể chuyển exception DB/provider sang lỗi ứng dụng phù hợp.
- Tránh trả `StoredProcedureQuery` ra ngoài unit of work rồi mới đọc kết quả khi EntityManager đã đóng.

### 9.2. Không dùng entity JPA để chứa tất cả output tùy ý

Output scalar như thống kê thường phù hợp với DTO/record. Một `Customer` entity nên biểu diễn trạng thái persistent được mapping thật sự, không nên nhồi thêm các field tạm tương ứng với output procedure rồi coi chúng đã được database quản lý.

---

## 10. @NamedStoredProcedureQuery

JPA cho phép khai báo trước metadata procedure bằng annotation `@NamedStoredProcedureQuery`.

Ví dụ đặt trên entity `Customer`:

```java
package demo.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;

@NamedStoredProcedureQuery(
    name = "Customer.paidStats",
    procedureName = "sp_customer_paid_stats",
    parameters = {
        @StoredProcedureParameter(
            name = "p_customer_id",
            mode = ParameterMode.IN,
            type = Long.class
        ),
        @StoredProcedureParameter(
            name = "p_paid_count",
            mode = ParameterMode.OUT,
            type = Long.class
        ),
        @StoredProcedureParameter(
            name = "p_paid_total",
            mode = ParameterMode.OUT,
            type = java.math.BigDecimal.class
        ),
        @StoredProcedureParameter(
            name = "p_label",
            mode = ParameterMode.INOUT,
            type = String.class
        )
    }
)
@Entity
public class Customer {
    @Id
    private Long id;

    protected Customer() {}
}
```

Class trên là **minh họa metadata tối thiểu**; nếu dự án đã có entity Customer thực tế, hãy đặt annotation vào entity đó thay vì định nghĩa thêm một entity trùng tên trong cùng persistence unit.

Gọi named procedure:

```java
StoredProcedureQuery sp =
    em.createNamedStoredProcedureQuery("Customer.paidStats");

sp.setParameter("p_customer_id", 10L);
sp.setParameter("p_label", "API");

sp.execute();

Number count =
    (Number) sp.getOutputParameterValue("p_paid_count");

BigDecimal total =
    (BigDecimal) sp.getOutputParameterValue("p_paid_total");
```

Vì metadata đã được khai báo, không cần lặp `registerStoredProcedureParameter` ở từng lời gọi.

### 10.1. Hai tên cần phân biệt

```java
name = "Customer.paidStats"
procedureName = "sp_customer_paid_stats"
```

- `name` là tên **named stored procedure query** trong JPA metadata.
- `procedureName` là tên procedure ở **database**.

Gọi `createNamedStoredProcedureQuery("sp_customer_paid_stats")` sẽ sai nếu annotation chỉ khai báo tên `Customer.paidStats`.

### 10.2. Khi nào dùng named metadata?

Phù hợp khi:

- Một procedure được gọi từ nhiều vị trí.
- Muốn contract tham số được khai báo ở một nơi.
- Đã có convention quản lý named queries trong dự án.
- Muốn dùng mapping cho result set cùng với metadata thủ tục.

Không phải mọi ứng dụng đều cần annotation. Với procedure chỉ được gọi ở một DAO và thay đổi thường xuyên, đăng ký bằng code có thể đơn giản và rõ hơn.

---

## 11. INOUT và sự khác biệt giữa giá trị đầu vào/đầu ra

Một ví dụ nhỏ chỉ có INOUT trên MySQL:

```sql
DELIMITER $$

CREATE PROCEDURE sp_normalize_points(
    INOUT p_points INT
)
BEGIN
    IF p_points IS NULL OR p_points < 0 THEN
        SET p_points = 0;
    END IF;
END $$

DELIMITER ;
```

Java:

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_normalize_points");

sp.registerStoredProcedureParameter(
    1, Integer.class, ParameterMode.INOUT);

sp.setParameter(1, -5);
sp.execute();

Integer normalizedPoints =
    (Integer) sp.getOutputParameterValue(1);

System.out.println(normalizedPoints); // 0
```

Chú ý:

- Đầu vào là `-5`.
- Procedure xử lý và trả `0` qua cùng tham số.
- Giá trị ban đầu mà Java truyền vào không tự trở thành output: phải gọi `getOutputParameterValue`.
- Procedure chỉ xử lý tham số, không nhất thiết sửa bất kỳ bảng database nào.
- Nếu `NULL` được phép truyền vào, cần cân nhắc cách provider/driver xử lý null input của `INOUT`; hãy kiểm tra trên stack thật.

### 11.1. Không dùng INOUT khi chỉ cần OUT

Nếu Java không cần cung cấp giá trị khởi tạo, dùng OUT. Việc khai báo INOUT chỉ để “biết chắc đọc được output” có thể khiến procedure yêu cầu giá trị đầu vào không cần thiết và tăng độ phức tạp.

---

## 12. execute() trả boolean gì?

Một điểm dễ nhầm:

```java
boolean result = sp.execute();
```

**`result` không cho biết nghiệp vụ thành công hay thất bại theo kiểu true/false.**

Nó phản ánh **loại kết quả đầu tiên** của stored procedure call:

- `true` nếu kết quả đầu tiên là một **result set**.
- `false` nếu kết quả đầu tiên là **update count** hoặc không có result set đầu tiên.

Vì vậy:

```java
if (!sp.execute()) {
    throw new IllegalStateException("Stored procedure failed");
}
```

là **sai**. Một procedure chỉ có OUT parameters có thể execute thành công và trả `false`.

Để biết gọi thành công về mặt JPA/JDBC, cần quan sát xem `execute()` có ném exception hay không và kiểm tra **output nghiệp vụ** theo contract của procedure. Với giao dịch ghi dữ liệu, commit thành công cũng là một phần của outcome.

### 12.1. Result set là gì?

Procedure có thể phát một tập hàng:

```sql
SELECT id, customer_id, total_amount
FROM purchase_orders
WHERE customer_id = p_customer_id;
```

Nếu procedure trả result set đầu tiên, `execute()` có thể trả `true` và `getResultList()` dùng để lấy các hàng đó.

### 12.2. Update count là gì?

Một procedure có thể thực hiện `UPDATE` và database/driver phát một **update count** như kết quả. `getUpdateCount()` trả số đếm cho update count hiện tại nếu có, hoặc giá trị chỉ ra không có update count theo API.

Một stored procedure có thể có **nhiều kết quả** thay vì một result set duy nhất.

---

## 13. Đọc nhiều result sets và update counts

Đối với thủ tục trả nhiều kết quả, JPA cung cấp:

```java
boolean execute();
List<?> getResultList();
int getUpdateCount();
boolean hasMoreResults();
Object getOutputParameterValue(...);
```

Một vòng lặp khái niệm:

```java
boolean isResultSet = sp.execute();

while (true) {
    if (isResultSet) {
        List<?> rows = sp.getResultList();

        System.out.println(
            "Result set rows: " + rows.size());

        // Xử lý/đưa rows vào DTO ở đây.
    } else {
        int updateCount = sp.getUpdateCount();

        if (updateCount == -1) {
            // Không còn result set/update count hiện hành.
            break;
        }

        System.out.println(
            "Updated rows: " + updateCount);
    }

    isResultSet = sp.hasMoreResults();
}

// Lấy OUT/INOUT sau khi xử lý kết quả.
Object output =
    sp.getOutputParameterValue("p_paid_total");
```

**Mục tiêu:** không giả định một procedure chỉ trả đúng một result set. Với một số database/driver, cần **consume result sets và update counts trước khi đọc OUT parameters** để portable.

### 13.1. Vì sao đọc OUT quá sớm có thể gặp vấn đề?

Có driver/procedure protocol mà OUT values chỉ sẵn sàng sau khi các kết quả trước đó đã được xử lý. JPA khuyến nghị việc lấy output parameter khi đã xử lý result sets/update counts để tránh phụ thuộc thứ tự riêng của provider.

Với procedure mẫu `sp_customer_paid_stats` dùng `SELECT ... INTO` và không phát result set, ta có thể gọi `execute` rồi lấy OUT trực tiếp. Nhưng với stored procedure có SELECT trả rows, hãy thiết kế trình tự rõ ràng.

### 13.2. Result set không tự tạo entity

Nếu stored procedure trả `id, customer_id, total_amount`, `getResultList()` có thể trả Object arrays hoặc entity objects tùy mapping và overload `createStoredProcedureQuery`.

Đừng cast mọi kết quả thành `PurchaseOrder` khi chưa cấu hình result mapping.

### 13.3. Vấn đề update count với database khác nhau

Một số DBMS phát update count cho SQL bên trong procedure; một số driver hoặc cấu hình dùng `SET NOCOUNT ON` (SQL Server) để giảm các thông báo số hàng. Những chi tiết đó thay đổi số lượng kết quả phải xử lý.

Không lấy số lần gọi `hasMoreResults()` làm bằng chứng procedure đã chạy đúng logic nghiệp vụ.

---

## 14. Đọc result set bằng resultClasses

Nếu procedure có kết quả là các hàng khớp mapping entity, có thể tạo:

```java
StoredProcedureQuery sp = em.createStoredProcedureQuery(
    "sp_find_paid_orders",
    PurchaseOrder.class
);
```

Sau khi đăng ký IN parameter thích hợp:

```java
sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN);

sp.setParameter(1, customerId);

boolean firstIsResultSet = sp.execute();

if (firstIsResultSet) {
    @SuppressWarnings("unchecked")
    List<PurchaseOrder> orders = sp.getResultList();

    for (PurchaseOrder order : orders) {
        System.out.println(order.getId());
    }
}
```

Điều kiện quan trọng: result set phải có cột/mapping phù hợp để provider dựng đúng entity (bao gồm identity và các field cần thiết). Nếu chỉ trả vài cột tổng hợp, không nên ánh xạ thành managed entity đầy đủ.

### 14.1. Dùng @SqlResultSetMapping cho DTO hoặc kết quả phức tạp

JPA hỗ trợ `@SqlResultSetMapping` và `@ConstructorResult` cho một số tình huống native result set mapping. Ví dụ một procedure trả:

```text
order_id (BIGINT)
total_amount (DECIMAL)
```

Bạn có thể định nghĩa DTO `PaidOrderRow(Long id, BigDecimal amount)` và result mapping tương thích, rồi tạo stored procedure query tham chiếu resultSetMapping name theo API.

Cần chú ý constructor parameter order và JDBC type. Không dùng constructor mapping giả định các cột trả về có alias khác với metadata.

### 14.2. Output parameters vẫn độc lập

Dù đã dùng `resultClasses` hoặc `resultSetMappings`, OUT/INOUT parameters vẫn phải được đăng ký/đọc theo contract. Mapping result set **không tự bind** các tham số OUT thành fields trên DTO nếu chưa có logic riêng.

---

## 15. REF_CURSOR: kết quả dạng cursor

`ParameterMode.REF_CURSOR` dùng cho stored procedure trả cursor trên database/provider hỗ trợ. Khác OUT `BigDecimal` hoặc `String`, cursor chứa nhiều hàng.

Ví dụ biểu diễn khái niệm:

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_open_customer_orders");

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN);

sp.registerStoredProcedureParameter(
    2, void.class, ParameterMode.REF_CURSOR);

sp.setParameter(1, customerId);

sp.execute();

// Cách lấy các hàng từ cursor phải phù hợp với
// mapping/result handling mà provider hỗ trợ.
List<?> rows = sp.getResultList();
```

**Không sao chép ví dụ này như một công thức chạy được trên mọi DBMS.** Định nghĩa procedure mở cursor, vị trí REF_CURSOR, JDBC registration, result mapping và việc đọc result sets khác nhau giữa Oracle, PostgreSQL và các hệ quản trị khác.

### 15.1. PostgreSQL function và procedure là hai khái niệm khác nhau

PostgreSQL có **functions** và **procedures**, với cú pháp `SELECT ...` và `CALL ...` tương ứng trong những ngữ cảnh phù hợp. Cách trả refcursor, transaction requirements, việc driver chuyển callable syntax và hỗ trợ của JPA provider cần được kiểm tra cẩn thận.

Một function trả `SETOF` hoặc `TABLE(...)` có thể phù hợp hơn với native SELECT query thay vì gọi như một stored procedure có OUT cursor. Đừng giả định mọi function trong database đều được gọi qua `createStoredProcedureQuery()` giống MySQL procedure.

### 15.2. Khi nào nên dùng REF_CURSOR?

Khi:

- Hệ thống legacy đã định nghĩa procedure trả cursor.
- Provider/driver đã hỗ trợ và team có test tích hợp.
- Cần tuân thủ contract DB hiện có.
- Đã có mapping rõ cho hàng được cursor trả.

Nếu nhu cầu chỉ là query một danh sách entity thông thường, JPQL/Criteria/native query có thể đơn giản và portable hơn.

---

## 16. Gán NULL làm input

Với IN parameter nullable:

```java
sp.registerStoredProcedureParameter(
    "p_filter", String.class, ParameterMode.IN);

sp.setParameter("p_filter", null);
```

Đây là một vấn đề cần kiểm tra trên stack cụ thể:

- Procedure có chấp nhận `NULL` cho tham số đó không?
- Provider có truyền SQL NULL hay bỏ qua binding theo policy? Một số provider có cấu hình riêng cho truyền null parameters của procedure.
- DB procedure có default parameter và phân biệt “không truyền” với “truyền NULL” không?
- Nếu INOUT input NULL, driver có registration/binding phù hợp không?
- Với overloaded procedures, có cần type rõ để database chọn đúng overload không?

### 16.1. Không nhầm NULL OUT với lỗi

Một OUT parameter có thể hợp pháp trả `NULL`:

```java
Object raw =
    sp.getOutputParameterValue("p_optional_value");

if (raw == null) {
    // Phân biệt theo contract: "không có dữ liệu",
    // hay lỗi mà procedure đã ghi bằng mã trạng thái khác?
}
```

Không nên ép cast rồi gọi `.toString()` ngay mà không kiểm tra null.

### 16.2. NULL và 0 có thể mang ý nghĩa khác nhau

Ví dụ:

- `paidCount = 0`: xác nhận không có đơn PAID.
- `paidTotal = 0.00`: tổng tiền PAID bằng 0.
- `paidTotal = NULL`: có thể do procedure không có giá trị/không tính được.

Đừng tự `COALESCE` mọi output thành 0 nếu nghiệp vụ cần phân biệt “không tính được” với “không có”.

---

## 17. Kiểu dữ liệu và việc chuyển đổi output

Ví dụ mapping nên thống nhất:

| SQL/Database type | Java type thường chọn | Lưu ý |
|---|---|---|
| BIGINT | `Long` | Driver có thể trả Number khác trong một số tình huống |
| INT | `Integer` | Không lẫn với Long |
| DECIMAL(p,s) | `BigDecimal` | Không dùng double cho tiền |
| VARCHAR | `String` | Có thể NULL |
| DATE | `java.sql.Date` hoặc kiểu ngày hỗ trợ bởi provider | Phụ thuộc driver/version và mapping |
| TIMESTAMP | `java.sql.Timestamp` hoặc `LocalDateTime` theo hỗ trợ | Timezone và precision cần kiểm tra |
| BOOLEAN/BIT | `Boolean` | Cách mapping DBMS khác nhau |
| REF_CURSOR | Result set/cursor mapping | Không phải scalar cast đơn giản |

### 17.1. Đừng cast số nguyên mù quáng

Sai:

```java
Long count = (Long)
    sp.getOutputParameterValue("p_paid_count");
```

Nếu provider trả `BigInteger` hoặc `Integer`, cast có thể thất bại. Khi cần xử lý các biến thể, dùng `Number` và chuyển đổi sau khi kiểm tra:

```java
Object value = sp.getOutputParameterValue("p_paid_count");

if (value == null) {
    throw new IllegalStateException(
        "Procedure did not return paid_count");
}

if (!(value instanceof Number)) {
    throw new IllegalStateException(
        "Expected numeric output");
}

long count = ((Number) value).longValue();
```

Nhưng việc dùng Number không thay thế kiểm tra giới hạn của domain. Nếu giá trị có thể quá lớn, dùng conversion có kiểm soát như `longValueExact()` trên `BigInteger`/`BigDecimal` tương ứng.

### 17.2. Đừng hard-code output type chỉ từ SELECT expression

Ví dụ `COUNT(*)` ở database có thể được provider/driver suy ra kiểu khác với số nguyên Java thông dụng. Contract tốt nhất là kiểm tra SQL parameter type thực tế của procedure, JDBC metadata và test tích hợp.

---

## 18. Stored procedure có transaction thế nào?

Stored procedure đọc dữ liệu có thể được gọi ngoài transaction rõ ràng trong một số cấu hình. Nhưng khi procedure **ghi dữ liệu** hoặc business use case yêu cầu nhất quán, cần transaction phù hợp.

Ví dụ trong Java SE dùng persistence unit `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("sp_update_loyalty_points");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN);

        sp.registerStoredProcedureParameter(
            2, Integer.class, ParameterMode.IN);

        sp.setParameter(1, customerId);
        sp.setParameter(2, extraPoints);

        sp.execute();

        tx.commit();
    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw failure;
    }
} finally {
    em.close();
}
```

Procedure `sp_update_loyalty_points` chỉ là ví dụ giả định: database phải định nghĩa procedure với contract khớp thì đoạn code mới chạy được.

### 18.1. Gọi procedure không tự thay commit

`sp.execute()` thành công không nhất thiết có nghĩa transaction đã commit. Nếu transaction có rollback sau đó, thay đổi database thuộc transaction có thể bị hủy.

### 18.2. Procedure có tự commit không?

Một số DBMS/procedure settings cho phép hoặc hạn chế thao tác transaction control bên trong procedure. Với PostgreSQL, SQL Server, MySQL hoặc Oracle, quy tắc có thể khác nhau và còn phụ thuộc việc procedure được gọi trong transaction do client quản lý.

Không thiết kế một lời gọi JPA như thể database procedure “luôn tự commit” nếu muốn ứng dụng giữ quyền điều khiển unit of work. Cần quy định rõ **ai sở hữu transaction boundary**: Java transaction manager hay procedure/database.

### 18.3. Procedure có thể tham gia nhiều câu SQL

Một procedure có thể UPDATE nhiều bảng trong cùng database transaction. Nếu DBMS hỗ trợ transaction semantics tương ứng, rollback sẽ hủy những UPDATE chưa commit. Nhưng tác động ngoài database hoặc autonomous transaction do vendor hỗ trợ có thể không tuân theo cùng rollback.

---

## 19. Flush trước khi gọi procedure

Một tình huống tinh vi: application đã sửa managed entity trong persistence context nhưng chưa flush, sau đó gọi procedure đọc dữ liệu database.

```java
Customer customer = em.find(Customer.class, customerId);
customer.changeStatus(CustomerStatus.ACTIVE);

// Không giả định procedure tự nhìn thấy field mới
// nếu thay đổi chỉ còn trong persistence context.

StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_customer_paid_stats");
```

Ở đây procedure dùng SQL trực tiếp tại database. Nếu business result phụ thuộc những thay đổi managed entity vừa thực hiện, cần nghĩ tới **flush ordering**.

### 19.1. Flush có chủ đích trong transaction

```java
tx.begin();

Customer customer = em.find(Customer.class, customerId);
customer.changeStatus(CustomerStatus.ACTIVE);

em.flush(); // Đồng bộ state phù hợp vào DB trong TX.

// Procedure có thể đọc dữ liệu vừa flush
// theo visibility của chính transaction.
callProcedure(em, customerId);

tx.commit();
```

Không kết luận rằng một stored procedure call luôn kích hoạt flush chính xác giống mọi JPQL query trên tất cả provider/configuration. Có thể dùng flush tường minh khi logic phụ thuộc vào dữ liệu mới được ghi trong cùng transaction.

### 19.2. Flush vẫn chưa commit

Nếu `em.flush()` đã phát SQL rồi procedure thất bại và transaction rollback, thay đổi chưa commit bị hủy. Đừng gửi sự kiện ngoài hệ thống như “đã lưu thành công” chỉ vì procedure đọc được dữ liệu vừa flush trong cùng transaction.

### 19.3. Cẩn thận khi procedure sửa hàng của managed entity

Nếu procedure UPDATE một row mà EntityManager đang giữ managed instance của row đó:

```text
Persistence context:
  Customer#10.points = 20

Procedure:
  UPDATE customers SET points = 30 WHERE id = 10

Persistence context vẫn có thể giữ:
  Customer#10.points = 20
```

JPA **không tự động đồng bộ mọi managed entity** với những SQL được procedure thực hiện trực tiếp ngoài dirty checking của nó.

Có thể cần `em.refresh(customer)` trong tình huống thích hợp, hoặc `em.clear()`/context mới. Tránh flush pending changes cũ đè ngược kết quả procedure. Thiết kế thứ tự thao tác, locking/version và invalidate cache rõ ràng.

---

## 20. @NamedStoredProcedureQuery và nhiều kết quả

Annotation có thể khai báo:

- `name` và `procedureName`.
- Danh sách `parameters`.
- `resultClasses` và/hoặc `resultSetMappings` theo contract JPA.
- Các `hints` nếu provider hỗ trợ.

Ví dụ cấu trúc:

```java
@NamedStoredProcedureQuery(
    name = "PurchaseOrder.findPaidByCustomer",
    procedureName = "sp_find_paid_orders",
    parameters = {
        @StoredProcedureParameter(
            name = "p_customer_id",
            mode = ParameterMode.IN,
            type = Long.class
        )
    },
    resultClasses = PurchaseOrder.class
)
```

Procedure phải trả columns phù hợp với entity `PurchaseOrder` và provider phải hiểu mapping result set. Đây là metadata khai báo; ứng dụng vẫn cần gọi `createNamedStoredProcedureQuery`, `setParameter`, `execute` và xử lý result set.

Không thêm `resultClasses` vào một procedure chỉ trả output scalar rồi mong JPA tự tạo entity từ các OUT values.

---

## 21. Spring Data JPA và stored procedure

Spring Data JPA có hỗ trợ khai báo stored procedure qua `@Procedure` và các cơ chế repository. Nhưng khả năng mapping nhiều OUT/INOUT/result sets phụ thuộc phiên bản Spring Data, JPA provider và contract procedure.

Ví dụ đơn giản, procedure trả một OUT scalar:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Procedure(procedureName = "sp_count_paid_orders")
    Long countPaidOrders(
        @Param("p_customer_id") Long customerId
    );
}
```

Ví dụ này giả định **database đã định nghĩa** `sp_count_paid_orders` với IN `p_customer_id` và một OUT count theo contract mà Spring Data/provider có thể map thành return value. Đây không phải implementation của `sp_customer_paid_stats` nhiều OUT parameters ở phần trước.

### 21.1. Khi procedure phức tạp, dùng custom repository

Nếu procedure có:

- Nhiều OUT parameters.
- INOUT.
- Nhiều result sets/update counts.
- REF_CURSOR.
- Mapping DTO đặc biệt.
- Thứ tự đọc kết quả quan trọng.

thì một custom repository dùng `EntityManager.createStoredProcedureQuery` thường cho phép kiểm soát rõ hơn.

Ví dụ service:

```java
@Service
public class CustomerReportService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public PaidStats getPaidStats(long customerId) {
        return procedure.fetch(em, customerId, "API");
    }
}
```

`procedure` ở đây là dependency `CustomerStatisticsProcedure` được inject/cấp thích hợp trong application; snippet tập trung vào ranh giới service. Cần import Spring `@Service`, `@Transactional` và Jakarta `@PersistenceContext` trong code chạy thật.

### 21.2. @Transactional(readOnly=true) không bảo vệ tuyệt đối khỏi procedure ghi

Spring `readOnly = true` là ý định read-only và có thể dẫn đến optimization/hint đối với connection/provider. Nó không phải chính sách bảo mật đảm bảo database sẽ từ chối mọi thủ tục ghi. Nếu procedure có side effect, hãy phân loại service là write operation, dùng transaction phù hợp và giới hạn quyền EXECUTE.

### 21.3. Không gọi em.getTransaction() trên JTA-managed EM

Nếu Spring/Jakarta EE đang quản lý EntityManager theo JTA hoặc transaction manager, đừng sao chép code RESOURCE_LOCAL để tự gọi `EntityTransaction.begin()`. Dùng transaction manager/framework API đúng cấu hình.

---

## 22. Các lỗi thường gặp khi gán tham số

### 22.1. Quên register parameter

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("sp_customer_paid_stats");

sp.setParameter("p_customer_id", 10L);
```

Nếu query không biết parameter này, có thể nhận `IllegalArgumentException` hoặc lỗi binding. Đăng ký đủ tham số bằng API hoặc dùng named metadata.

### 22.2. Đăng ký sai ParameterMode

Ví dụ DB khai báo `INOUT p_label` nhưng Java đăng ký `IN`:

```java
sp.registerStoredProcedureParameter(
    "p_label", String.class, ParameterMode.IN);
```

Ứng dụng sẽ không có contract đúng để đọc output; driver có thể báo lỗi. Chế độ Java phải khớp signature của procedure.

### 22.3. Quên set giá trị INOUT

```java
sp.registerStoredProcedureParameter(
    "p_label", String.class, ParameterMode.INOUT);

sp.execute();
```

Nếu input cần được khởi tạo, việc không `setParameter` có thể gây lỗi hoặc giá trị không mong muốn. Hãy đặt input rõ ràng.

### 22.4. Truyền sai type

```java
sp.registerStoredProcedureParameter(
    "p_customer_id", Long.class, ParameterMode.IN);

sp.setParameter("p_customer_id", "10");
```

`"10"` là String, không phải Long. Đừng dựa vào database tự ép kiểu trên mọi driver.

### 22.5. Sai vị trí

```java
sp.setParameter(2, 10L);
```

Trong ví dụ, vị trí 2 là OUT count, không phải IN customerId. Gán nhầm position có thể báo lỗi hoặc khiến procedure nhận dữ liệu sai.

### 22.6. Lấy output trước execute

```java
sp.getOutputParameterValue("p_paid_total");
sp.execute();
```

Output thường chưa sẵn sàng trước khi procedure được thực thi. Hãy execute trước và xử lý các kết quả trước khi đọc output.

### 22.7. Nhầm execute() false là thất bại

`boolean first = sp.execute()` không phải cờ success của nghiệp vụ; `false` vẫn có thể là procedure call hoàn toàn thành công.

### 22.8. Đọc output như result set

```java
List<?> rows = sp.getResultList();
```

không phải cách lấy `p_paid_total` từ OUT parameter của procedure mẫu vốn không có result set. Dùng `getOutputParameterValue`.

### 22.9. Cast output sai type

`(Long) output` có thể ném `ClassCastException` nếu provider/driver trả kiểu Number khác. Kiểm tra type thực tế trên database triển khai.

### 22.10. Lấy OUT khi result sets chưa xử lý

Với multi-result procedures, có driver yêu cầu consume result sets/update counts trước khi output có thể được truy cập. Thiết kế một bước đọc kết quả rõ ràng.

### 22.11. Quên transaction khi procedure ghi

Nếu procedure UPDATE/INSERT/DELETE, phải xét transaction boundary và quyền rollback. Gọi execute không đồng nghĩa commit.

### 22.12. Không flush managed state trước khi procedure đọc

Procedure đọc database có thể không thấy những thay đổi vẫn chỉ nằm trong persistence context. Dùng flush có chủ đích trong transaction nếu business logic yêu cầu.

### 22.13. Nghĩ procedure update tự refresh entity

Nếu procedure sửa row mà EntityManager đang quản lý, managed entity có thể stale. Cần refresh/clear/context mới theo policy.

---

## 23. Lỗi portability giữa database và provider

### 23.1. MySQL/MariaDB

Stored procedures thường được khai báo bằng `CREATE PROCEDURE` với IN/OUT/INOUT. Cú pháp `DELIMITER` thuộc client script. Driver/JPA provider cần có quyền truy cập metadata phù hợp; kiểm tra named parameter support, OUT handling và transaction.

### 23.2. SQL Server

Có T-SQL procedures với `OUTPUT` parameters và đôi khi return status. SQL Server có thể phát nhiều update counts từ statements trong procedure; `SET NOCOUNT ON` thường được dùng khi không muốn gửi các rowcount messages không cần thiết. Nhưng kết hợp JPA/provider phải được thử trên JDBC driver thật.

Một procedure có **return code** cũng không đồng nghĩa một OUT parameter thông thường trong mọi API; cần xác định signature/callable syntax mà provider hỗ trợ.

### 23.3. Oracle

PL/SQL packages, procedures, functions và `SYS_REFCURSOR` có quy tắc gọi và mapping riêng. REF_CURSOR thường cần kiểm tra result mapping, parameter position và transaction. Không suy từ cú pháp MySQL cho Oracle.

### 23.4. PostgreSQL

Phân biệt procedures `CALL` với functions `SELECT`. Đặc biệt refcursor, result sets, INOUT, transaction control và JDBC callable statement handling có thể khác nhiều so với MySQL.

### 23.5. Hibernate và các JPA providers khác

Hibernate ORM có các extension và quy tắc riêng cho CallableStatement và procedure results. EclipseLink hoặc provider khác có thể sinh SQL hoặc xử lý cursor khác nhau.

**Không cam kết rằng chỉ cần đổi JDBC URL là mọi stored procedure JPQL/JPA hoạt động trên DBMS mới.** Stored procedure là điểm phụ thuộc database mạnh; cần integration test theo tổ hợp provider + driver + DBMS + version.

---

## 24. Xử lý exception và rollback

Lời gọi procedure có thể thất bại tại:

- `createStoredProcedureQuery` nếu tên/cấu hình không hợp lệ.
- `registerStoredProcedureParameter` nếu khai báo sai.
- `setParameter` nếu tên/vị trí/type không đúng.
- `execute` vì procedure không tồn tại, thiếu quyền, SQL error hoặc constraint.
- `getResultList`/`hasMoreResults` vì result handling.
- `getOutputParameterValue` vì mode, position, lifecycle hoặc type.
- `commit` vì lỗi database/locking.

Mẫu RESOURCE_LOCAL:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("sp_update_loyalty_points");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN);

        sp.registerStoredProcedureParameter(
            2, Integer.class, ParameterMode.IN);

        sp.setParameter(1, customerId);
        sp.setParameter(2, delta);

        sp.execute();

        tx.commit();
    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    }
} finally {
    em.close();
}
```

Ví dụ này giả định `sp_update_loyalty_points` là procedure ghi dữ liệu được định nghĩa ở DB. Nếu `commit()` thất bại do mất kết nối đúng thời điểm xác nhận, ứng dụng có thể không biết chính xác database đã commit hay chưa. Với write procedures có side effects, cần **idempotency key** và policy retry/reconciliation thay vì retry vô điều kiện.

### 24.1. Không giấu lỗi gốc

Nếu rollback cũng lỗi, đừng thay exception gốc bằng exception cleanup mà không giữ context. `Throwable.addSuppressed` có thể giúp chẩn đoán. Nếu lỗi xảy ra sau khi procedure đã thay đổi một hệ thống bên ngoài DB, rollback database cũng không hủy được tác động ngoài đó.

### 24.2. Resource lifecycle

`StoredProcedureQuery` gắn với EntityManager/context và tài nguyên JDBC liên quan. Đừng trả một object `StoredProcedureQuery` ra khỏi scope của một EntityManager đã đóng rồi kỳ vọng vẫn có thể đọc kết quả sau đó. Hãy thu thập output, chuyển sang DTO và đóng tài nguyên đúng thời điểm.

---

## 25. Quyền EXECUTE và an toàn dữ liệu

Ứng dụng production cần một database principal có quyền tối thiểu cần thiết:

- Chỉ `EXECUTE` những procedures ứng dụng thực sự sử dụng.
- Nếu procedure ghi dữ liệu, xác định quyền của procedure owner/definer/execution context tùy DBMS.
- Không cho tài khoản ứng dụng quyền tạo/sửa procedure nếu không cần.
- Không ghi password hoặc dữ liệu nhạy cảm vào log.
- Không dùng procedure để bỏ qua các quy tắc phân quyền nghiệp vụ ở service.
- Không nối tên procedure/SQL từ input người dùng mà chưa có allowlist được kiểm soát.

### 25.1. Parameter binding giúp ngăn injection ở tầng gọi

Đúng:

```java
sp.setParameter("p_customer_id", customerId);
```

Không xây câu SQL gọi procedure bằng nối chuỗi giá trị do người dùng nhập:

```java
String sql = "CALL sp_customer_paid_stats(" +
    userInput + ", ...)";
```

Tuy nhiên, **binding an toàn ở Java không tự bảo đảm code bên trong procedure an toàn** nếu procedure lại nối dynamic SQL từ tham số mà không validate/bind đúng cách.

### 25.2. Không xem procedure là “hộp đen an toàn”

Hãy hiểu dữ liệu procedure đọc/ghi, locking, transaction control, SQL dynamic, log và side effects. Procedure có thể ẩn một lượng công việc lớn sau một lệnh `execute()` ngắn trong Java.

---

## 26. Theo dõi và tối ưu hiệu năng

Một lời gọi stored procedure có thể bao gồm nhiều câu SQL, JOIN, cursor và bước tính toán. Vì vậy:

- Đo **tổng thời gian execute và đọc kết quả**, không chỉ thời gian tạo `StoredProcedureQuery`.
- Theo dõi query plan của SQL bên trong procedure.
- Kiểm tra index trên cột lọc/ghép như `customer_id`, `order_status`.
- Kiểm tra kích thước result set/cursor.
- Tránh procedure trả hàng triệu dòng khi API chỉ cần vài số thống kê.
- Không giả định procedure nhanh hơn JPQL chỉ vì được lưu ở database.
- Không gọi procedure nặng hàng trăm lần trong loop nếu có thể batch/group hoặc query hợp lý.

Ví dụ index phù hợp với truy vấn thống kê:

```sql
CREATE INDEX idx_orders_customer_status
ON purchase_orders(customer_id, order_status);
```

Index giúp một số kế hoạch thực thi, nhưng hiệu quả phụ thuộc phân phối dữ liệu và database optimizer. Cần kiểm tra `EXPLAIN`/execution plan trên DB thật.

---

## 27. Bài thực hành A — OUT cơ bản

1. Tạo schema và dữ liệu mẫu.
2. Định nghĩa `sp_customer_paid_stats` trong MySQL.
3. Gọi procedure trực tiếp bằng MySQL CLI/Workbench để xác minh contract.
4. Tạo `StoredProcedureQuery` bằng tên vật lý.
5. Đăng ký đầy đủ bốn tham số.
6. Đặt `p_customer_id=10` và `p_label='API'`.
7. Gọi `execute()`.
8. Đọc `p_paid_count`, `p_paid_total`, `p_label`.
9. Ghi kết quả dự kiến là 2, 420.00 và `API:CUSTOMER-10`.
10. Thử customer 20, ghi kết quả 0 và 0.00.

## 28. Bài thực hành B — Gọi theo vị trí

1. Gọi cùng procedure nhưng đăng ký tham số ở vị trí 1–4.
2. Set input vị trí 1 và 4.
3. Đọc output vị trí 2, 3 và 4.
4. So sánh kết quả với cách gọi theo tên.
5. Cố ý đổi nhầm position trong một thử nghiệm lỗi.
6. Quan sát thông báo provider/driver và giải thích vì sao thứ tự procedure contract quan trọng.

## 29. Bài thực hành C — INOUT

1. Tạo `sp_normalize_points(INOUT p_points INT)`.
2. Truyền `-5`, đọc kết quả 0.
3. Truyền 50, đọc kết quả 50.
4. Thử input NULL nếu driver/provider hỗ trợ.
5. Đăng ký nhầm `IN`, quan sát khả năng lấy output.
6. Giải thích sự khác nhau giữa việc truyền input và lấy output của cùng tham số.

## 30. Bài thực hành D — @NamedStoredProcedureQuery

1. Đặt annotation trên entity Customer hiện có.
2. Khai báo `name="Customer.paidStats"`.
3. Khai báo `procedureName="sp_customer_paid_stats"`.
4. Khai báo đủ tham số và mode.
5. Gọi `em.createNamedStoredProcedureQuery("Customer.paidStats")`.
6. Set input, execute và đọc output.
7. Thử gọi nhầm bằng procedureName trong named API để thấy khác biệt.
8. Cân nhắc nên giữ metadata ở annotation hay DAO trong dự án của bạn.

## 31. Bài thực hành E — Result set và OUT khác nhau

Thiết kế một procedure thử thứ hai:

```sql
-- Pseudocode: syntax chính xác phụ thuộc DBMS.
PROCEDURE sp_report(
    IN customer_id,
    OUT total_paid
):
    SELECT ...;           -- phát result set
    SET total_paid = ...; -- output scalar
```

1. Thực thi bằng `StoredProcedureQuery`.
2. Ghi lại giá trị boolean từ `execute()`.
3. Dùng `getResultList()` với result set đầu.
4. Dùng `hasMoreResults()` và `getUpdateCount()` khi có nhiều kết quả.
5. Sau khi xử lý xong, đọc OUT parameter.
6. Giải thích vì sao `execute()==false` không chứng minh procedure thất bại.

## 32. Bài thực hành F — Null output và conversion

1. Tạo procedure có OUT VARCHAR có thể trả NULL.
2. Kiểm tra `getOutputParameterValue` trả null.
3. Không gọi `toString()` trước khi null check.
4. Tạo OUT DECIMAL với các giá trị có phần thập phân.
5. Xác minh BigDecimal giữ precision.
6. Tạo OUT BIGINT với số lớn, kiểm tra Number conversion.
7. Thử result mapping/constructor type không phù hợp và ghi nhận lỗi.

## 33. Bài thực hành G — Procedure ghi và transaction

1. Tạo procedure cập nhật loyalty points.
2. Bắt đầu resource-local transaction.
3. Gọi procedure tăng điểm.
4. Rollback thay vì commit.
5. Mở EntityManager mới, kiểm tra điểm không đổi.
6. Thực hiện lại và commit thành công.
7. Tải cùng Customer trong context còn giữ state cũ, quan sát stale state khi procedure sửa row.
8. Chủ động refresh hoặc dùng context mới để đọc đúng dữ liệu.
9. Đưa vào một constraint/error để quan sát exception và xử lý rollback.

**Lưu ý:** nếu procedure tự thực hiện transaction control theo cơ chế vendor, phải xem lại giả định ở bài này. Thí nghiệm nên sử dụng procedure không tự commit để ứng dụng kiểm soát transaction.

## 34. Bài thực hành H — Kiểm tra portability

Nếu có nhiều môi trường database:

1. Chạy procedure MySQL với driver MySQL tương thích.
2. Ghi nhận named/positional parameter support.
3. Đối chiếu SQL type được driver trả cho OUT BIGINT/DECIMAL.
4. Thiết kế một procedure tương đương trên DBMS khác theo cú pháp riêng.
5. Thử result sets và update counts.
6. Xác minh cách xử lý cursor nếu hệ quản trị hỗ trợ.
7. Không chỉ thay JDBC URL rồi coi procedure definition là portable.
8. Ghi lại phiên bản database, JDBC driver và JPA provider.

---

## 35. Checklist trước khi hoàn thiện một procedure call

| Câu hỏi | Cần xác nhận |
|---|---|
| Procedure tồn tại ở schema nào? | Tên, schema, package nếu DBMS cần |
| Java có quyền EXECUTE không? | DB principal và execution context |
| Đăng ký theo tên hay vị trí? | Nhất quán, đúng với driver/provider |
| Signature có những tham số nào? | Tên/vị trí/type/mode |
| INOUT đã được set input chưa? | Không chỉ register rồi đọc |
| OUT có thể NULL không? | Null handling và contract nghiệp vụ |
| Kiểu số có thể khác nhau không? | Number/BigDecimal conversion có kiểm soát |
| Procedure trả result sets không? | Mapping và consume đúng thứ tự |
| Có update counts không? | `getUpdateCount`/`hasMoreResults` |
| OUT được đọc sau khi xử lý các kết quả chưa? | Tính portable của protocol |
| Có REF_CURSOR không? | Provider/DBMS-specific mapping |
| Procedure ghi dữ liệu không? | Transaction boundary và rollback |
| Có managed entities bị procedure UPDATE không? | Flush ordering, refresh/clear |
| Có tác động ngoài DB không? | Idempotency và phân biệt rollback |
| Có kiểm thử trên DB thật chưa? | Không chỉ unit test với mock |
| Có log đủ thông tin không? | Không lộ dữ liệu nhạy cảm |
| Có limit kết quả và timeouts không? | Hiệu năng và an toàn tài nguyên |

---

## 36. Câu hỏi ôn tập

1. `StoredProcedureQuery` khác JPQL query thông thường về contract kết quả như thế nào?
2. Tham số `IN` có chiều dữ liệu ra sao?
3. Tham số `OUT` được đọc bằng phương thức nào?
4. `INOUT` cần cả thao tác nào ở phía Java?
5. `REF_CURSOR` khác OUT `BigDecimal` ở điểm nào?
6. `registerStoredProcedureParameter` cần những thông tin gì?
7. Khi dùng positional parameters, vị trí đầu tiên là 0 hay 1?
8. Vì sao đăng ký theo tên có thể không portable trên mọi driver?
9. `setParameter` nên dùng cho những ParameterMode nào?
10. Tại sao procedure có thể thành công dù `execute()` trả false?
11. `getResultList` và `getOutputParameterValue` có đọc cùng một loại dữ liệu không?
12. `getUpdateCount` biểu thị gì?
13. Vì sao phải quan tâm thứ tự xử lý result sets/update counts trước OUT?
14. Khi nào cần `resultClasses` hoặc `@SqlResultSetMapping`?
15. `@NamedStoredProcedureQuery.name` khác `procedureName` thế nào?
16. Một procedure chỉ có OUT scalar có cần resultClasses không?
17. Vì sao không ép `COUNT(*)` luôn là `Long` mà không kiểm tra driver?
18. Vì sao `DECIMAL` nên dùng `BigDecimal`?
19. OUT có thể trả NULL không, và cần xử lý thế nào?
20. Vì sao `execute` không tự commit giao dịch RESOURCE_LOCAL?
21. `flush()` khác `commit()` ở điểm nào trước khi gọi procedure?
22. Khi procedure sửa row mà JPA giữ managed entity cũ, nguy cơ nào xuất hiện?
23. Vì sao refresh/clear có thể cần thiết sau procedure ghi dữ liệu?
24. Vì sao stored procedure không mặc nhiên portable khi đổi DBMS?
25. PostgreSQL function và procedure có thể được gọi khác nhau ra sao?
26. Vì sao REF_CURSOR cần kiểm tra provider/driver?
27. Spring `@Transactional(readOnly=true)` có cấm tuyệt đối procedure ghi không?
28. Nếu rollback sau procedure, side effect ngoài database có tự mất đi không?
29. Vì sao không trả `StoredProcedureQuery` ra khỏi scope EntityManager đã đóng?
30. Những lỗi nào thường xuất hiện tại `getOutputParameterValue`?
31. Khi procedure trả nhiều kết quả, tại sao không nên chỉ gọi `getResultList` một lần?
32. Làm sao xác minh một procedure call đúng mà không nhầm lỗi database với lỗi JPA mapping?

---

## 37. Bảng ghi nhớ nhanh

| Nhu cầu | API/JPA |
|---|---|
| Tạo lời gọi procedure theo tên vật lý | `em.createStoredProcedureQuery("sp_name")` |
| Dùng named metadata | `em.createNamedStoredProcedureQuery("Query.name")` |
| Đăng ký IN theo tên | `registerStoredProcedureParameter("p", Type.class, ParameterMode.IN)` |
| Đăng ký OUT theo vị trí | `registerStoredProcedureParameter(2, Type.class, ParameterMode.OUT)` |
| Đăng ký INOUT | `ParameterMode.INOUT` |
| Đăng ký cursor | `ParameterMode.REF_CURSOR` nếu DB/provider hỗ trợ |
| Truyền input | `setParameter(nameOrPosition, value)` |
| Thực thi procedure | `execute()` |
| Lấy OUT | `getOutputParameterValue(nameOrPosition)` |
| Đọc current result set | `getResultList()` |
| Đọc current update count | `getUpdateCount()` |
| Chuyển sang kết quả tiếp theo | `hasMoreResults()` |
| Khai báo named procedure | `@NamedStoredProcedureQuery` |
| Ghi dữ liệu nguyên tử | Transaction boundary phù hợp |
| Đồng bộ pending managed state trước procedure | `em.flush()` khi cần và transaction hợp lệ |
| Tải lại entity sau procedure sửa row | `em.refresh` hoặc context mới theo policy |

### Sơ đồ tổng hợp

```text
            JAVA / JPA
                |
                | createStoredProcedureQuery
                v
       StoredProcedureQuery
                |
     +----------+----------+
     | register parameters |
     +----------+----------+
                |
           set IN/INOUT
                |
             execute
                |
        +-------+-------+
        |               |
    Result sets      Update counts
    getResultList    getUpdateCount
        |               |
        +-------+-------+
                |
          hasMoreResults
                |
        getOutputParameterValue
                |
                v
          DTO / Service result
                |
                v
         commit / rollback
          (nếu có write TX)
```

**Nguyên tắc cuối bài:** để gọi stored procedure an toàn từ JPA, hãy **khớp đúng signature** (tên/vị trí/Java type/ParameterMode), **gán rõ input**, **thực thi**, **xử lý các result sets/update counts nếu có**, rồi **đọc OUT/INOUT** theo contract. Đừng xem `execute()` như cờ thành công nghiệp vụ, đừng nhầm OUT với result set và đừng giả định stored procedures portable giữa các database. Với procedure ghi dữ liệu, transaction, flush ordering, trạng thái managed entity và idempotency quan trọng không kém việc đọc đúng tham số.

