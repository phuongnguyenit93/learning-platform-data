# Đăng ký tham số IN, OUT và INOUT

## 1. Vì sao phải đăng ký tham số khi gọi thủ tục lưu trữ?

Trong Jakarta Persistence (JPA), một **thủ tục lưu trữ** (*stored procedure*) là chương trình được định nghĩa và thực thi trong hệ quản trị cơ sở dữ liệu. Khác với một câu `SELECT` thông thường, procedure có thể vừa nhận dữ liệu đầu vào, vừa trả một hoặc nhiều giá trị qua **tham số đầu ra**, cập nhật nhiều bảng hoặc trả các tập kết quả.

Ví dụ, ứng dụng cần tính giá trị đơn hàng sau chiết khấu bằng logic lưu ở database:

- Nhận **mã đơn hàng**.
- Nhận **tỷ lệ chiết khấu**.
- Nhận một **bộ đếm lời gọi** và cập nhật nó.
- Trả **tổng tiền trước chiết khấu**.
- Trả **tổng tiền sau chiết khấu**.

Chữ ký procedure minh họa:

```sql
CREATE PROCEDURE quote_order(
    IN    p_order_id          BIGINT,
    IN    p_discount_percent  DECIMAL(5,2),
    INOUT p_call_count        INT,
    OUT   p_subtotal          DECIMAL(14,2),
    OUT   p_total             DECIMAL(14,2)
)
...
```

Khi gọi bằng JPA, ta cần cho provider biết **tham số nào là đầu vào, tham số nào là đầu ra, tham số nào vừa đọc vừa ghi**, đồng thời đăng ký kiểu Java tương ứng.

JPA cung cấp:

- `EntityManager.createStoredProcedureQuery(...)` để tạo lời gọi procedure.
- `StoredProcedureQuery.registerStoredProcedureParameter(...)` để đăng ký từng tham số.
- `ParameterMode.IN`, `ParameterMode.OUT`, `ParameterMode.INOUT` để khai báo hướng tham số.
- `setParameter(...)` để truyền giá trị của tham số đầu vào.
- `execute()` để thực thi.
- `getOutputParameterValue(...)` để lấy giá trị đầu ra.
- `@NamedStoredProcedureQuery` để khai báo metadata procedure có tên và tái sử dụng.

**Đăng ký tham số không đồng nghĩa đã gọi procedure.** Đó là bước chuẩn bị contract giữa Java và database; procedure chỉ thực thi khi application kích hoạt theo API tương ứng.

## 2. Nhìn tổng thể luồng gọi stored procedure

```text
Ứng dụng Java
    |
    | 1. createStoredProcedureQuery("quote_order")
    v
StoredProcedureQuery
    |
    | 2. register parameter 1: Long, IN
    |    register parameter 2: BigDecimal, IN
    |    register parameter 3: Integer, INOUT
    |    register parameter 4: BigDecimal, OUT
    |    register parameter 5: BigDecimal, OUT
    |
    | 3. setParameter(1, 101L)
    |    setParameter(2, 10.00)
    |    setParameter(3, 4)
    v
JPA provider / JDBC driver
    |
    | 4. execute()
    v
Database procedure
    |
    | Đọc tham số IN
    | Đọc và thay đổi INOUT
    | Gán giá trị cho OUT
    v
JPA provider
    |
    | 5. getOutputParameterValue(3) -> 5
    |    getOutputParameterValue(4) -> 920000.00
    |    getOutputParameterValue(5) -> 828000.00
    v
Ứng dụng đọc kết quả
```

Điểm cần nhớ:

1. **Đăng ký:** mô tả vị trí hoặc tên, kiểu và hướng của tham số.
2. **Truyền:** đặt giá trị ban đầu cho `IN` và `INOUT`.
3. **Thực thi:** procedure chạy trong database theo transaction và quyền của kết nối.
4. **Nhận:** đọc tham số `OUT` và giá trị sau xử lý của `INOUT`.

Với những procedure còn trả result set hoặc update count, phải hiểu thêm thứ tự **tiêu thụ kết quả** trước khi đọc OUT; phần sau sẽ giải thích.

## 3. Ba hướng tham số: IN, OUT và INOUT

### 3.1. Ý nghĩa

| Hướng | Database nhận gì? | Database có thể trả gì? | Java cần thực hiện |
|---|---|---|---|
| `IN` | Giá trị đầu vào do caller cung cấp | Không lấy kết quả bằng OUT của tham số này | Đăng ký `IN` và `setParameter` |
| `OUT` | Không yêu cầu giá trị đầu vào từ caller | Giá trị procedure gán để trả về | Đăng ký `OUT`, thực thi, gọi `getOutputParameterValue` |
| `INOUT` | Giá trị đầu vào ban đầu | Giá trị sau khi procedure xử lý | Đăng ký `INOUT`, `setParameter` trước, `getOutputParameterValue` sau |

`IN` dùng cho giá trị chỉ được đọc bởi procedure. `OUT` dùng cho giá trị do procedure tính ra. `INOUT` đóng cả hai vai trò.

### 3.2. IN: đầu vào chỉ đọc theo contract

Ví dụ:

```sql
IN p_order_id BIGINT
```

Java:

```java
procedure.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
procedure.setParameter(1, 101L);
```

Điều này nói với provider rằng tham số vị trí 1 là một `Long` và phải được cung cấp trước khi thực thi.

### 3.3. OUT: đầu ra

Ví dụ:

```sql
OUT p_subtotal DECIMAL(14,2)
```

Java:

```java
procedure.registerStoredProcedureParameter(
    4, BigDecimal.class, ParameterMode.OUT
);

// Không setParameter(4, ...) cho OUT thuần.
procedure.execute();

BigDecimal subtotal = (BigDecimal)
    procedure.getOutputParameterValue(4);
```

Caller **không cần và không nên** đặt giá trị ban đầu cho tham số chỉ có hướng OUT. Procedure phải gán giá trị hoặc trả NULL theo contract database.

### 3.4. INOUT: đầu vào được cập nhật

Ví dụ:

```sql
INOUT p_call_count INT
```

Java:

```java
procedure.registerStoredProcedureParameter(
    3, Integer.class, ParameterMode.INOUT
);

procedure.setParameter(3, 4);
procedure.execute();

Integer nextCount = (Integer)
    procedure.getOutputParameterValue(3);
```

Nếu procedure tăng một đơn vị, giá trị trả về là 5. Điều quan trọng: **biến Java truyền vào không tự bị thay đổi bằng phép gán trong procedure**. Ta nhận giá trị mới qua `getOutputParameterValue`.

### 3.5. Không nhầm INOUT với biến tham chiếu Java

```java
Integer count = 4;
procedure.setParameter(3, count);
procedure.execute();

System.out.println(count); // Vẫn là 4.
```

`Integer` là giá trị đầu vào cho lời gọi. Database không “sửa biến Java” của ứng dụng.

```java
count = (Integer) procedure.getOutputParameterValue(3);
System.out.println(count); // Giá trị trả về từ procedure.
```

Cách hiểu đúng là **hai chiều trao đổi giá trị qua JDBC/JPA**, không phải truyền một con trỏ trực tiếp sang database.

## 4. API chuẩn trong Jakarta Persistence

### 4.1. Các import

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

import java.math.BigDecimal;
```

Với code dùng Jakarta Persistence, package là `jakarta.persistence`. Trong dự án legacy JPA 2.x, package thường là `javax.persistence`. **Không trộn annotation/API của hai namespace** trong cùng cấu hình nếu dependencies không tương thích.

### 4.2. Tạo lời gọi

```java
StoredProcedureQuery procedure =
    em.createStoredProcedureQuery("quote_order");
```

Chuỗi `"quote_order"` là **tên procedure trong database**, không phải tên entity hoặc tên một JPQL query. Tùy schema/catalog và provider, có thể phải dùng tên có định danh schema hoặc cấu hình database search path.

### 4.3. Đăng ký theo vị trí

```java
procedure.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    2, BigDecimal.class, ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    3, Integer.class, ParameterMode.INOUT
);

procedure.registerStoredProcedureParameter(
    4, BigDecimal.class, ParameterMode.OUT
);

procedure.registerStoredProcedureParameter(
    5, BigDecimal.class, ParameterMode.OUT
);
```

Trong phương án dùng vị trí, thứ tự đăng ký phải phù hợp **thứ tự trong chữ ký procedure** mà database/provider sử dụng.

### 4.4. Đăng ký theo tên

```java
procedure.registerStoredProcedureParameter(
    "p_order_id", Long.class, ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    "p_discount_percent",
    BigDecimal.class,
    ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    "p_call_count",
    Integer.class,
    ParameterMode.INOUT
);

procedure.registerStoredProcedureParameter(
    "p_subtotal",
    BigDecimal.class,
    ParameterMode.OUT
);

procedure.registerStoredProcedureParameter(
    "p_total",
    BigDecimal.class,
    ParameterMode.OUT
);
```

JPA có API đăng ký bằng tên, nhưng mức độ hỗ trợ **named parameters cho stored procedures** phụ thuộc database, JDBC driver và provider. Không coi việc provider chấp nhận tên trong một môi trường là bảo đảm mọi DB khác hoạt động tương tự.

### 4.5. Không trộn tên và vị trí tùy tiện

Nên chọn **một phong cách nhất quán** cho từng lời gọi:

- Đăng ký vị trí 1–5, dùng `setParameter(1, ...)` và `getOutputParameterValue(4)`.
- Hoặc đăng ký tên, dùng `setParameter("p_order_id", ...)` và `getOutputParameterValue("p_subtotal")`.

Việc pha trộn tên và vị trí có thể gây lỗi ánh xạ, đặc biệt với JDBC driver không hỗ trợ named binding cho stored procedures.

### 4.6. JPA còn có `REF_CURSOR`

`ParameterMode` còn có `REF_CURSOR` dành cho một số kiểu kết quả cursor của procedure. **Nó không phải INOUT và không thay cho OUT scalar**. Các database có mô hình cursor khác nhau, nên bài này tập trung ba hướng `IN`, `OUT` và `INOUT`.

## 5. Chuẩn bị database: procedure ví dụ có đủ ba hướng

Để ví dụ Java có thể chạy và kiểm tra kết quả dự đoán được, ta dùng **MySQL 8.x**. Phần DDL/SQL dưới đây là cú pháp minh họa của MySQL, không phải SQL portable cho mọi hệ quản trị.

### 5.1. Tạo bảng

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    CONSTRAINT fk_lines_orders
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_price_nonnegative CHECK (unit_price >= 0)
);
```

### 5.2. Dữ liệu ví dụ

```sql
INSERT INTO purchase_orders (id)
VALUES (101);

INSERT INTO order_lines (id, order_id, quantity, unit_price)
VALUES
    (1, 101, 2, 400000.00),
    (2, 101, 1, 120000.00);
```

Tổng tiền của Order 101:

```text
2 × 400000.00 = 800000.00
1 × 120000.00 = 120000.00
--------------------------
Subtotal        = 920000.00

Giảm giá 10%
Total           = 828000.00
```

### 5.3. Tạo procedure `quote_order`

```sql
DELIMITER //

CREATE PROCEDURE quote_order(
    IN    p_order_id BIGINT,
    IN    p_discount_percent DECIMAL(5,2),
    INOUT p_call_count INT,
    OUT   p_subtotal DECIMAL(14,2),
    OUT   p_total DECIMAL(14,2)
)
BEGIN
    IF p_order_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order ID is required';
    END IF;

    IF p_discount_percent IS NULL
       OR p_discount_percent < 0
       OR p_discount_percent > 100 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid discount percent';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM purchase_orders o
        WHERE o.id = p_order_id
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order not found';
    END IF;

    SELECT COALESCE(
        SUM(l.quantity * l.unit_price),
        0
    )
    INTO p_subtotal
    FROM order_lines l
    WHERE l.order_id = p_order_id;

    SET p_call_count =
        COALESCE(p_call_count, 0) + 1;

    SET p_total = ROUND(
        p_subtotal * (100 - p_discount_percent) / 100,
        2
    );
END //

DELIMITER ;
```

**Lưu ý về MySQL:**

- `DELIMITER` là chỉ thị cho một số **SQL client** như MySQL CLI để nhập toàn bộ khối `CREATE PROCEDURE`; nó không phải câu SQL chạy qua JDBC như một phần của JPA.
- Cú pháp `IN`, `OUT` và `INOUT` ở đây theo MySQL. PostgreSQL, SQL Server, Oracle có quy tắc thủ tục, kiểu dữ liệu và cách gọi khác.
- `SELECT ... INTO p_subtotal` gán vào biến procedure, **không tạo một result set SELECT để Java duyệt** trong ví dụ này.
- `p_call_count` chỉ là tham số được cập nhật rồi trả về, **không phải bộ đếm lưu vĩnh viễn** trong bảng.
- Procedure này tính báo giá chứ không ghi Order mới; nếu procedure dùng DML, cần thiết kế transaction và concurrency tương ứng.

### 5.4. Thử bằng SQL client

```sql
SET @call_count = 4;
SET @subtotal = NULL;
SET @total = NULL;

CALL quote_order(
    101,
    10.00,
    @call_count,
    @subtotal,
    @total
);

SELECT
    @call_count AS call_count,
    @subtotal AS subtotal,
    @total AS total;
```

Kỳ vọng:

| call_count | subtotal | total |
|---:|---:|---:|
| 5 | 920000.00 | 828000.00 |

Các biến `@call_count`, `@subtotal` và `@total` là **biến phiên kết nối MySQL** cho ví dụ SQL client. Trong Java/JPA nên dùng `StoredProcedureQuery` để database/JDBC trả output, **không dựa vào biến session tự tạo rồi chia sẻ qua connection pool**.

## 6. Ví dụ JPA đầy đủ: đăng ký theo vị trí

### 6.1. Khởi tạo StoredProcedureQuery

```java
StoredProcedureQuery procedure =
    em.createStoredProcedureQuery("quote_order");

procedure.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
procedure.registerStoredProcedureParameter(
    2, BigDecimal.class, ParameterMode.IN
);
procedure.registerStoredProcedureParameter(
    3, Integer.class, ParameterMode.INOUT
);
procedure.registerStoredProcedureParameter(
    4, BigDecimal.class, ParameterMode.OUT
);
procedure.registerStoredProcedureParameter(
    5, BigDecimal.class, ParameterMode.OUT
);
```

### 6.2. Truyền đầu vào

```java
procedure.setParameter(1, 101L);
procedure.setParameter(2, new BigDecimal("10.00"));
procedure.setParameter(3, 4);
```

Không gọi `setParameter(4, ...)` hoặc `setParameter(5, ...)` vì đây là OUT thuần.

### 6.3. Thực thi và lấy đầu ra

```java
procedure.execute();

Integer count = (Integer)
    procedure.getOutputParameterValue(3);

BigDecimal subtotal = (BigDecimal)
    procedure.getOutputParameterValue(4);

BigDecimal total = (BigDecimal)
    procedure.getOutputParameterValue(5);

System.out.println(count);     // 5
System.out.println(subtotal);  // 920000.00
System.out.println(total);     // 828000.00
```

Procedure ví dụ không tạo result set trả về nên có thể đọc OUT ngay sau khi `execute()` hoàn thành, theo provider/driver phù hợp. **Nếu procedure có result set hoặc update counts, cần xử lý chúng trước khi lấy OUT để tương thích với những driver/database yêu cầu thứ tự đó.**

### 6.4. Phương thức Java đóng gói kết quả

Định nghĩa record:

```java
package com.example.shop.reporting;

import java.math.BigDecimal;

public record OrderQuote(
    long orderId,
    int callCount,
    BigDecimal subtotal,
    BigDecimal total
) {}
```

Tạo helper gọi procedure:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

import java.math.BigDecimal;
import java.util.Objects;

public final class OrderQuoteProcedure {

    private OrderQuoteProcedure() {
    }

    public static OrderQuote calculate(
            EntityManager em,
            long orderId,
            BigDecimal discountPercent,
            int initialCallCount) {

        Objects.requireNonNull(em, "em");
        Objects.requireNonNull(
            discountPercent, "discountPercent");

        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("quote_order");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            2, BigDecimal.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            3, Integer.class, ParameterMode.INOUT
        );
        sp.registerStoredProcedureParameter(
            4, BigDecimal.class, ParameterMode.OUT
        );
        sp.registerStoredProcedureParameter(
            5, BigDecimal.class, ParameterMode.OUT
        );

        sp.setParameter(1, orderId);
        sp.setParameter(2, discountPercent);
        sp.setParameter(3, initialCallCount);

        sp.execute();

        Number countValue =
            (Number) sp.getOutputParameterValue(3);

        BigDecimal subtotal =
            (BigDecimal) sp.getOutputParameterValue(4);

        BigDecimal total =
            (BigDecimal) sp.getOutputParameterValue(5);

        return new OrderQuote(
            orderId,
            countValue.intValue(),
            subtotal,
            total
        );
    }
}
```

`Number` cho bộ đếm ở phần đọc giúp code chấp nhận các trường hợp JDBC/provider trả một dạng số tương thích dù registration là `Integer.class`. Với OUT DECIMAL, ví dụ kỳ vọng `BigDecimal`. Nếu provider/database trả kiểu khác, phải điều chỉnh mapping/chuyển đổi có kiểm soát, không ép kiểu theo giả định.

### 6.5. Ranh giới transaction

Trong ứng dụng Java SE dùng `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    OrderQuote quote = OrderQuoteProcedure.calculate(
        em,
        101L,
        new BigDecimal("10.00"),
        4
    );

    em.getTransaction().commit();

    System.out.println(quote);
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

`emf` là một `EntityManagerFactory` đã cấu hình, và cần import các lớp tương ứng. Dù procedure ví dụ chủ yếu đọc, việc thiết kế transaction rõ ràng giúp tránh nhầm với procedure thật có DML hoặc logic yêu cầu isolation. Với Spring/Jakarta EE, transaction thường do framework/container quản lý; không mở transaction `RESOURCE_LOCAL` thủ công trong một context JTA.

## 7. Đăng ký theo tên thay vì vị trí

### 7.1. Ví dụ có tên

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("quote_order");

sp.registerStoredProcedureParameter(
    "p_order_id",
    Long.class,
    ParameterMode.IN
);

sp.registerStoredProcedureParameter(
    "p_discount_percent",
    BigDecimal.class,
    ParameterMode.IN
);

sp.registerStoredProcedureParameter(
    "p_call_count",
    Integer.class,
    ParameterMode.INOUT
);

sp.registerStoredProcedureParameter(
    "p_subtotal",
    BigDecimal.class,
    ParameterMode.OUT
);

sp.registerStoredProcedureParameter(
    "p_total",
    BigDecimal.class,
    ParameterMode.OUT
);

sp.setParameter("p_order_id", 101L);
sp.setParameter(
    "p_discount_percent",
    new BigDecimal("10.00")
);
sp.setParameter("p_call_count", 4);

sp.execute();

Number count = (Number)
    sp.getOutputParameterValue("p_call_count");

BigDecimal subtotal = (BigDecimal)
    sp.getOutputParameterValue("p_subtotal");

BigDecimal total = (BigDecimal)
    sp.getOutputParameterValue("p_total");
```

Tên trong code phải phù hợp những tham số mà **procedure/database/provider** nhận diện. Không coi tên parameter Java tùy ý là alias tự động của chữ ký SQL.

### 7.2. Ưu điểm của đăng ký theo tên

- Code có thể dễ đọc hơn khi procedure có nhiều tham số.
- Giảm nguy cơ quên ý nghĩa vị trí 4 hoặc 5.
- Thể hiện rõ ý định giữa Java và SQL.

### 7.3. Giới hạn portability

JPA định nghĩa API theo tên, nhưng một số database/JDBC driver không hỗ trợ named parameters của stored procedure theo cách provider cần. Khi đó lời gọi có thể lỗi ngay lúc đăng ký, bind hoặc thực thi.

Với hệ thống nhiều DB hoặc khi driver có giới hạn, **đăng ký theo vị trí** thường là điểm xuất phát an toàn hơn, sau khi đối chiếu chữ ký và hành vi driver.

### 7.4. Thay đổi thứ tự tham số trong database

Nếu dùng vị trí và DBA đổi chữ ký procedure từ:

```sql
IN p_order_id,
IN p_discount_percent,
INOUT p_call_count,
OUT p_subtotal,
OUT p_total
```

sang một thứ tự khác, code Java cần được sửa theo. Dùng tên có thể giúp giảm phụ thuộc thứ tự **trên môi trường hỗ trợ named binding đúng**, nhưng không loại trừ việc thay đổi schema, đổi tên tham số, thay đổi loại hoặc quyền thực thi.

**Chữ ký stored procedure là một contract cần quản lý phiên bản.**

## 8. `@NamedStoredProcedureQuery`: khai báo một lần, gọi nhiều nơi

### 8.1. Khi nào dùng named stored procedure metadata?

Nếu procedure được gọi ở nhiều service hoặc codebase muốn tập trung chữ ký ở metadata JPA, có thể dùng:

```java
@NamedStoredProcedureQuery(
    name = "OrderQuote.calculate",
    procedureName = "quote_order",
    parameters = {
        @StoredProcedureParameter(
            name = "p_order_id",
            mode = ParameterMode.IN,
            type = Long.class
        ),
        @StoredProcedureParameter(
            name = "p_discount_percent",
            mode = ParameterMode.IN,
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            name = "p_call_count",
            mode = ParameterMode.INOUT,
            type = Integer.class
        ),
        @StoredProcedureParameter(
            name = "p_subtotal",
            mode = ParameterMode.OUT,
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            name = "p_total",
            mode = ParameterMode.OUT,
            type = BigDecimal.class
        )
    }
)
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    protected PurchaseOrder() {}
}
```

Cần import:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;
import jakarta.persistence.Table;
import java.math.BigDecimal;
```

Đoạn entity ở đây chỉ minh họa **vị trí đặt annotation metadata**. Nếu ứng dụng đã có `PurchaseOrder` đầy đủ, thêm annotation vào entity hiện hữu, không tạo hai entity cùng tên ánh xạ cùng bảng một cách tùy tiện.

### 8.2. Phân biệt hai tên

```java
name = "OrderQuote.calculate"
procedureName = "quote_order"
```

- `name`: tên **named query trong metadata JPA**, được dùng ở Java khi gọi `createNamedStoredProcedureQuery`.
- `procedureName`: tên **procedure thực sự trong database**.

Hai tên có thể khác nhau; không nên nhầm `createNamedStoredProcedureQuery("quote_order")` là đúng nếu metadata khai báo `name="OrderQuote.calculate"`.

### 8.3. Thực thi named mapping

```java
StoredProcedureQuery sp =
    em.createNamedStoredProcedureQuery(
        "OrderQuote.calculate"
    );

sp.setParameter("p_order_id", 101L);

sp.setParameter(
    "p_discount_percent",
    new BigDecimal("10.00")
);

sp.setParameter("p_call_count", 4);

sp.execute();

Number count = (Number)
    sp.getOutputParameterValue("p_call_count");

BigDecimal subtotal = (BigDecimal)
    sp.getOutputParameterValue("p_subtotal");

BigDecimal total = (BigDecimal)
    sp.getOutputParameterValue("p_total");
```

Ở cách này, **metadata đã đăng ký tham số** qua annotation. Không cần lặp lại mọi lời gọi `registerStoredProcedureParameter` bằng tay cho từng lần thực thi.

### 8.4. Named metadata không tạo procedure trong database

Annotation `@NamedStoredProcedureQuery` **không thay thế câu `CREATE PROCEDURE`**. Nó chỉ cho JPA biết cách gọi. Procedure thực phải tồn tại trong đúng schema/database mà connection sử dụng, có chữ ký tương thích và caller có quyền `EXECUTE`.

Trong deployment, quản lý procedure như một schema artifact bằng migration (Flyway/Liquibase hoặc cơ chế tương đương) phù hợp hệ thống, không giả định JPA tự sinh thân procedure khi tạo entity table.

### 8.5. Một entity có thể khai báo nhiều named procedure

JPA hỗ trợ container `@NamedStoredProcedureQueries` để đặt nhiều định nghĩa. Chúng có thể tham chiếu các procedure khác nhau cho những use case khác nhau. Tuy nhiên, tránh đặt những metadata hoàn toàn không liên quan lên một entity chỉ vì “cần chỗ để annotation”; một lớp/entity hoặc cấu trúc persistence metadata có chủ đích dễ bảo trì hơn.

## 9. Đăng ký đúng kiểu Java và kiểu SQL

### 9.1. Bảng mapping tham khảo

| Kiểu SQL trong ví dụ | Hướng | Kiểu Java phù hợp | Lưu ý |
|---|---|---|---|
| `BIGINT` | IN | `Long.class` | ID hoặc số lớn |
| `INT` | INOUT | `Integer.class` | Có thể đọc qua `Number` nếu driver trả numeric wrapper khác |
| `DECIMAL(5,2)` | IN | `BigDecimal.class` | Tỷ lệ phần trăm, không dùng `double` tùy tiện |
| `DECIMAL(14,2)` | OUT | `BigDecimal.class` | Giá trị tiền tệ |
| `VARCHAR` | OUT | `String.class` | Trả thông báo hoặc mã kết quả |
| `DATE` | IN/OUT | `LocalDate.class` khi provider/driver hỗ trợ | Cần xem mapping phiên bản và database |
| `TIMESTAMP` | IN/OUT | `LocalDateTime.class`/`Instant.class` tùy semantics và provider | Phân biệt timezone và kiểu SQL thực |
| `BOOLEAN` hoặc tương đương | IN/OUT | `Boolean.class` khi được hỗ trợ | Một số DB biểu diễn boolean bằng số/bit khác nhau |

Bảng chỉ là **điểm khởi đầu**. JDBC driver, provider, database dialect và cách định nghĩa procedure có thể ảnh hưởng kiểu wrapper được nhận ở output.

### 9.2. Chọn kiểu wrapper thay vì primitive trong registration

API:

```java
registerStoredProcedureParameter(
    int position,
    Class type,
    ParameterMode mode
)
```

thường được dùng với class object như `Long.class`, `Integer.class`, `BigDecimal.class`. Với OUT có thể NULL, kiểu wrapper giúp biểu diễn thiếu giá trị, còn primitive Java không thể chứa null.

### 9.3. OUT có thể là NULL

Giả sử procedure trả:

```sql
OUT p_error_text VARCHAR(255)
```

Nếu xử lý thành công, procedure có thể đặt `p_error_text = NULL`. Java:

```java
String errorText = (String)
    sp.getOutputParameterValue("p_error_text");

if (errorText != null) {
    // Xử lý lỗi/diagnostic theo contract nghiệp vụ.
}
```

Không gọi `errorText.isBlank()` trước khi kiểm tra null. Với kiểu numeric, cũng không tự unbox một `Integer`/`Long` OUT có thể null.

### 9.4. DECIMAL và BigDecimal

```java
new BigDecimal("10.00")
```

thể hiện đúng số thập phân đầu vào hơn việc dùng `new BigDecimal(0.1)` cho các số nhị phân khó biểu diễn chính xác.

Ở phần output, dữ liệu `DECIMAL` của MySQL thường được JDBC đọc thành `BigDecimal`. Khi so sánh:

```java
boolean equal = total.compareTo(
    new BigDecimal("828000.00")
) == 0;
```

`BigDecimal.equals` xét cả scale, nên `828000.0` và `828000.00` có thể không bằng nhau theo `equals`. `compareTo` phù hợp khi muốn so sánh **giá trị số**.

### 9.5. Không ép sai kiểu theo mong muốn

Nếu procedure trả số tiền DECIMAL, tránh:

```java
Double total = (Double)
    sp.getOutputParameterValue(5);
```

trừ khi đã xác minh provider/driver trả `Double` theo contract. Cố ép kiểu khác với wrapper thực tế có thể gây `ClassCastException`, hoặc chuyển đổi mất độ chính xác.

**Định nghĩa kiểu ở registration phải nhất quán với signature SQL và cách provider/JDBC chuyển dữ liệu.**

## 10. Gọi `execute()` và đọc kết quả theo đúng thứ tự

### 10.1. `execute()` trả boolean, không phải giá trị OUT

```java
boolean firstIsResultSet = sp.execute();
```

Giá trị trả về của `execute()` cho biết **kết quả đầu tiên của lời gọi procedure có phải result set hay không**, theo ngữ nghĩa của `StoredProcedureQuery`.

Nó **không** phải dấu hiệu tổng quát “procedure thành công hay thất bại”.

Ví dụ procedure chỉ gán OUT và không phát result set, `execute()` có thể trả `false` nhưng procedure vẫn thực thi thành công:

```java
boolean hasResultSet = sp.execute();

System.out.println(hasResultSet); // Có thể false: không có result set.

BigDecimal total = (BigDecimal)
    sp.getOutputParameterValue(5); // Output vẫn có thể hợp lệ.
```

Không viết:

```java
if (!sp.execute()) {
    throw new IllegalStateException("Procedure thất bại");
}
```

vì `false` có thể chỉ có nghĩa **không có result set ở kết quả đầu tiên**.

### 10.2. Thứ tự xử lý khi procedure trả nhiều loại kết quả

Có procedure chứa:

- Một hoặc nhiều `SELECT` trả result sets.
- Một hoặc nhiều statement DML tạo update counts.
- `OUT` và `INOUT` scalar.

Theo hướng dẫn của JPA, **kết quả result sets và update counts nên được xử lý trước khi lấy OUT**, bởi một số database/JDBC driver không cho đọc output cho đến khi các kết quả trước đã được tiêu thụ.

Luồng khái quát:

```text
execute()
    |
    +-- Result set #1? --> getResultList()
    |
    +-- Update count? --> getUpdateCount()
    |
    +-- Result set #2? --> getResultList()
    |
    +-- Hết kết quả --> getOutputParameterValue(...)
```

### 10.3. Mẫu duyệt kết quả

```java
boolean isResultSet = sp.execute();

while (true) {
    if (isResultSet) {
        List<?> rows = sp.getResultList();

        // Xử lý result set hiện tại.
        // Chỉ là ví dụ: loại phần tử phụ thuộc result mapping.
        for (Object row : rows) {
            System.out.println(row);
        }
    } else {
        int updateCount = sp.getUpdateCount();

        if (updateCount == -1) {
            break; // Không còn update count/result set.
        }

        System.out.println(
            "Affected rows: " + updateCount);
    }

    isResultSet = sp.hasMoreResults();
}

// Sau khi xử lý result set/update count:
Object output = sp.getOutputParameterValue(4);
```

Mẫu này dành cho procedure thực sự tạo nhiều kết quả. Với procedure `quote_order` ở phần trước (chỉ dùng `SELECT ... INTO` để gán biến), thường không cần vòng lặp result set.

Cần import `java.util.List`. Với native result set nhiều cột, mỗi row có thể là `Object[]`; nếu dùng entity result mapping, row có thể là managed entity. Đừng coi mọi kết quả procedure luôn là `List<Product>`.

### 10.4. `getUpdateCount()` không phải output parameter

`getUpdateCount()` đọc số hàng bị ảnh hưởng của **kết quả DML hiện tại** trong luồng kết quả procedure. Nó khác hoàn toàn:

```java
sp.getOutputParameterValue(4);
```

Dù procedure có OUT tên `p_updated_rows`, caller phải lấy nó bằng output API, không mặc định nó bằng JDBC update count. Procedure có thể thực hiện nhiều DML hoặc tự tính số liệu khác.

## 11. Phân biệt tham số OUT với tập kết quả

### 11.1. OUT scalar

```sql
OUT p_total DECIMAL(14,2)
```

Đọc:

```java
BigDecimal total = (BigDecimal)
    sp.getOutputParameterValue(5);
```

Đây là **một giá trị OUT**.

### 11.2. Procedure trả result set

Một procedure có thể thực hiện:

```sql
SELECT id, order_id, quantity, unit_price
FROM order_lines
WHERE order_id = p_order_id;
```

Đây là một **result set nhiều hàng**, không phải OUT scalar. Ở Java có thể lấy bằng `getResultList()` và cấu hình mapping phù hợp.

### 11.3. Một procedure có thể có cả hai

Khi procedure có result set và OUT, phải tách:

- **Cấu trúc hàng:** ánh xạ result set (scalar, `Object[]`, `@SqlResultSetMapping` hoặc entity mapping).
- **Hướng tham số:** đăng ký `IN`/`OUT`/`INOUT`.
- **Thứ tự xử lý:** tiêu thụ result sets/update counts trước, sau đó lấy OUT khi cần tương thích.

Đăng ký OUT **không tự biến result set thành một giá trị OUT**, và có result-set mapping **không thay thế việc đăng ký output parameter**.

### 11.4. `REF_CURSOR` là trường hợp khác

Một số database trả cursor qua tham số đặc biệt. JPA có `ParameterMode.REF_CURSOR`, nhưng đó là cơ chế khác với `OUT BigDecimal`. Cách gọi và đọc cursor phải theo database/provider. Không dùng `ParameterMode.OUT` cho cursor một cách tùy tiện rồi nghĩ JPA sẽ trả danh sách entity đúng.

## 12. Stored procedure với query results và managed entity

### 12.1. Đầu ra có thể là scalar hoặc entity

Giả sử procedure liệt kê các Order và database trả result set. JPA có thể được cấu hình để ánh xạ hàng thành entity:

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery(
        "list_orders_for_customer",
        PurchaseOrder.class
    );
```

Nếu result set chứa các cột phù hợp với metadata của `PurchaseOrder` và provider/database hỗ trợ cách gọi, các entity được ánh xạ có thể trở thành **managed trong persistence context**.

### 12.2. OUT parameter vẫn không phải managed entity

Một OUT `BigDecimal`, `Integer` hoặc `String` chỉ là giá trị được database trả lại:

```java
Object total = sp.getOutputParameterValue("p_total");
```

Giá trị scalar này không có dirty checking, không thuộc identity map và không thể được “refresh” bằng `EntityManager.refresh` như một entity.

### 12.3. Không nhầm số hàng được xử lý và số entity managed

Procedure có thể sửa 1000 hàng qua DML nhưng ứng dụng không tự có 1000 entity managed. Trái lại, một result set ánh xạ tới entity có thể đưa các instance vào context.

**Đăng ký IN/OUT/INOUT mô tả tham số procedure; result-set mapping mô tả loại dữ liệu hàng được trả.** Hai chủ đề phối hợp nhưng không thay thế nhau.

## 13. Transaction: khi procedure đọc hoặc ghi database

### 13.1. Procedure có thể thay đổi nhiều bảng

Một procedure thực tế có thể:

- Trừ tồn kho.
- Ghi đơn hàng.
- Ghi lịch sử audit.
- Tính tổng tiền.
- Trả số lượng dòng đã cập nhật qua OUT.
- Trả trạng thái xử lý qua OUT hoặc exception.

Nếu procedure có DML, cần một **transaction boundary** rõ ràng để tránh cập nhật một phần.

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    StoredProcedureQuery sp =
        em.createStoredProcedureQuery("apply_inventory_change");

    // Đăng ký và truyền tham số ở đây.
    sp.execute();

    // Lấy output sau khi xử lý các kết quả cần thiết.
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Đây là skeleton minh họa; procedure `apply_inventory_change` và chữ ký của nó phải được định nghĩa riêng trong database trước khi code có thể chạy.

### 13.2. Flush trước khi gọi procedure phụ thuộc state mới

Giả sử ứng dụng vừa thay đổi một entity managed, rồi gọi procedure đọc bảng đó:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

// Thay đổi một thuộc tính được ánh xạ trong transaction.
order.changeStatus(OrderStatus.PAID);

// Nếu procedure cần quan sát thay đổi ORM đang chờ:
em.flush();

StoredProcedureQuery sp =
    em.createStoredProcedureQuery("summarize_paid_orders");
```

Ví dụ giả định entity có `changeStatus` và procedure tổng hợp tương ứng. Ý chính: nếu procedure cần đọc thay đổi đang chờ trong persistence context, **flush trước lời gọi** để đồng bộ pending SQL trong transaction.

Không nên mặc định provider luôn flush trước mọi stored procedure ở mọi flush mode và mọi cấu hình. `FlushModeType.AUTO` có semantics riêng, nhưng với tình huống phụ thuộc dữ liệu, việc đặt điểm đồng bộ tường minh dễ lập luận hơn.

### 13.3. Flush không phải commit

`em.flush()` đồng bộ thay đổi ORM xuống database **trong transaction**. Procedure chạy trên cùng transaction có thể đọc các thay đổi đó; tuy nhiên transaction khác thường không thấy cho đến khi commit.

Sau khi `sp.execute()` và đọc OUT, transaction vẫn có thể rollback. Vì vậy một OUT `"SUCCESS"` từ procedure **không phải bằng chứng commit cuối cùng đã thành công**.

### 13.4. Procedure tự quản lý transaction cần được thiết kế cẩn thận

Một số database cho phép procedure điều khiển transaction trong những ngữ cảnh nhất định; một số khác có hạn chế nghiêm ngặt. Nếu procedure tự `COMMIT` hoặc `ROLLBACK`, ranh giới của application/JPA có thể không còn đúng như mong đợi.

Trong ứng dụng dùng JPA, nên thống nhất rõ bên nào sở hữu transaction: application/framework hay procedure/database. Không viết thủ tục tự commit một cách tùy tiện khi application kỳ vọng tính nguyên tử của toàn bộ use case.

### 13.5. Spring `@Transactional`

Trong Spring:

```java
@Service
public class QuoteService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderQuote quote(
            long orderId,
            BigDecimal discountPercent) {

        return OrderQuoteProcedure.calculate(
            em,
            orderId,
            discountPercent,
            0
        );
    }
}
```

Ví dụ giả định `quote_order` chỉ đọc bảng và tính OUT, không ghi dữ liệu lâu dài. Nếu procedure có DML, **không đánh dấu service read-only** theo thói quen: cấu hình transaction/driver/database có thể từ chối ghi hoặc xử lý không theo kỳ vọng.

Trong Spring-managed EntityManager, không gọi `em.getTransaction().begin()` thủ công. Transaction được quản lý bởi interceptor/framework qua `@Transactional`.

## 14. INOUT và transaction là hai chuyện khác nhau

Một tham số INOUT:

```sql
INOUT p_call_count INT
```

không có nghĩa nó được cập nhật và giữ vĩnh viễn trong database. Nó là một giá trị trong **lời gọi procedure**; ứng dụng nhận lại kết quả sau khi thực thi.

Ví dụ:

```java
sp.setParameter(3, 4);
sp.execute();

int updatedCount =
    ((Number) sp.getOutputParameterValue(3)).intValue();
```

Sau đó:

```java
sp2.setParameter(3, updatedCount);
```

chỉ khi ứng dụng **chủ động truyền lại** `updatedCount` thì lời gọi tiếp mới nhận được giá trị ấy. Database không mặc nhiên lưu bộ đếm vào một hàng table.

Nếu nghiệp vụ yêu cầu bộ đếm bền vững qua nhiều request, cần lưu ở bảng, có khóa/constraint và xử lý đồng thời; INOUT tự nó không giải quyết bài toán lưu trữ hay concurrency.

## 15. Procedure cập nhật database có thể làm entity managed bị stale

### 15.1. Persistence context không tự biết mọi thay đổi SQL

Giả sử application đã tải Product:

```java
Product product = em.find(Product.class, productId);
```

Sau đó procedure khác chạy UPDATE lên `products`. JPA provider không nhất thiết cập nhật các field của `product` đang managed.

```text
Lúc đầu:
  Managed Product.price = 100000
  DB Product.price      = 100000

Stored procedure UPDATE:
  DB Product.price      = 90000

Managed Product.price   = 100000 (có thể stale)
```

Một OUT trả số tiền mới không đồng nghĩa provider tự đồng bộ field managed.

### 15.2. Refresh khi cần dùng lại managed entity

```java
sp.execute();

// Sau khi xử lý kết quả procedure:
em.refresh(product);

BigDecimal current = product.getUnitPrice();
```

`refresh` chỉ dùng với **managed entity** hợp lệ và đọc lại theo góc nhìn transaction hiện tại. Cần cân nhắc nếu entity đang có pending changes chưa flush, vì refresh có thể ghi đè thay đổi trong bộ nhớ.

### 15.3. Clear nếu muốn bỏ toàn bộ context cũ

```java
em.flush(); // Nếu còn pending changes cần lưu.
sp.execute();
// ...
em.clear();
```

`clear` detach tất cả entity đang managed trong context, không chỉ Product. Sau đó muốn sửa tiếp phải tải hoặc gắn đúng instance theo lifecycle. Không dùng `clear` bừa bãi trong service lớn.

### 15.4. Native procedure có thể bỏ qua optimistic locking

Nếu procedure trực tiếp UPDATE một bảng có `@Version`, nó không tự tuân thủ optimistic locking mà ORM áp dụng khi dirty-check managed entity. Một procedure cập nhật bảng cần có chiến lược đối với cột version, chẳng hạn so sánh version kỳ vọng và tăng version khi ghi.

Không coi `StoredProcedureQuery` là lời gọi entity update lifecycle bình thường với `@PreUpdate`, `cascade` và version check tự động.

## 16. Đăng ký tham số cho stored procedure không đồng nghĩa gọi function

Database có thể phân biệt:

- **Procedure:** được gọi theo cú pháp `CALL` hoặc tương đương.
- **Function:** trả một giá trị qua biểu thức SQL, đôi khi được gọi trong `SELECT`.

Ví dụ MySQL:

```sql
CALL quote_order(...);
```

Trong PostgreSQL và các database khác, cách gọi procedure/function, kiểu kết quả và tham số OUT/INOUT có thể khác đáng kể. Không tự đổi từ `CREATE PROCEDURE` sang `CREATE FUNCTION` rồi giữ nguyên code JPA mà giả định hoạt động giống nhau.

JPA `StoredProcedureQuery` được thiết kế cho lời gọi stored procedure; một số provider có API hỗ trợ function hoặc cú pháp riêng. Nếu phải gọi function trả scalar, có thể cần SQL expression/native query hoặc extension phù hợp.

## 17. PostgreSQL, SQL Server, Oracle: điều gì cần kiểm tra?

Ví dụ `quote_order` trong bài dùng MySQL để giữ một cú pháp nhất quán. Khi chuyển sang DB khác, cần xác minh **cả bốn lớp**:

1. **Định nghĩa routine:** có phải procedure hay function? Cú pháp IN/OUT/INOUT, quy tắc return value/cursor là gì?
2. **JDBC driver:** đăng ký output, xử lý result set/update count và support named parameters ra sao?
3. **JPA provider:** chuyển `StoredProcedureQuery` thành lời gọi JDBC như thế nào? Hỗ trợ result mapping và null binding ở mức nào?
4. **Transaction/schema:** caller có quyền EXECUTE không, routine thuộc schema nào, cách xử lý commit và error như thế nào?

### 17.1. PostgreSQL

PostgreSQL có thủ tục và hàm với đặc điểm gọi khác nhau. Tùy phiên bản và JDBC driver, tham số OUT/INOUT của procedure có thể có cách ánh xạ kết quả đặc thù. Không mặc định ví dụ MySQL `CALL` với user variables hoặc thứ tự OUT được sử dụng nguyên trạng.

Nếu code cần đa DB, viết integration test trên đúng PostgreSQL và driver mục tiêu, đặc biệt khi routine trả nhiều result sets hoặc cursor.

### 17.2. SQL Server

T-SQL hỗ trợ tham số `OUTPUT` và quy ước return status. Số hàng ảnh hưởng, nhiều result sets và thông báo update counts có thể liên quan đến `SET NOCOUNT ON` trong procedure.

Khi dùng JPA, phải xác định cái gì là **tham số OUT** và cái gì là **return status/update count**. Không gọi `getOutputParameterValue` để lấy một kết quả chưa đăng ký hay nhầm boolean của `execute()` với return status.

### 17.3. Oracle

Oracle có package procedures, OUT parameters và REF CURSOR theo những quy tắc riêng. Có thể cần tên qualified theo schema/package và result mapping phù hợp. `REF_CURSOR` khác OUT scalar; không nên dựa vào cách gọi MySQL khi làm việc với Oracle package.

### 17.4. Cách viết ứng dụng portable

Không phải mọi stored procedure đều portable về SQL. Một chiến lược thực tế là:

- Giữ service-level contract ổn định, ví dụ `OrderQuote calculate(...)`.
- Cô lập phần gọi database ở một adapter/repository.
- Quản lý DDL routine theo dialect.
- Test chữ ký và kết quả thực trên mỗi DB được hỗ trợ.
- Tránh dùng named binding nếu provider/driver mục tiêu không bảo đảm.
- Dùng đúng kiểu Java và mapping output của từng môi trường.

## 18. Lỗi thường gặp khi đăng ký và gọi tham số

### 18.1. Sai vị trí

SQL khai báo:

```sql
IN p_order_id,
IN p_discount_percent,
INOUT p_call_count,
OUT p_subtotal,
OUT p_total
```

nhưng code:

```java
sp.registerStoredProcedureParameter(
    3, BigDecimal.class, ParameterMode.OUT
);
```

sẽ sai vì vị trí 3 thực tế là `INOUT INT`. Lỗi có thể xuất hiện lúc registration, binding, execute hoặc đọc output, tùy provider/JDBC.

**Cách tránh:** đối chiếu từng số thứ tự với database signature; giữ mapping ở một nơi.

### 18.2. Sai mode

```java
sp.registerStoredProcedureParameter(
    4, BigDecimal.class, ParameterMode.IN
);
```

trong khi database khai báo `OUT`. Provider có thể không đăng ký JDBC output đúng cách, khiến không thể lấy giá trị bằng `getOutputParameterValue`.

Đăng ký `INOUT` như `IN` cũng làm mất khả năng đọc kết quả cập nhật theo contract.

### 18.3. Quên setParameter cho IN

```java
sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);

// Quên sp.setParameter(1, orderId).
sp.execute();
```

Provider có thể báo tham số chưa được bind hoặc database nhận input không hợp lệ. Không mặc định một IN chưa được set sẽ tự nhận NULL một cách hợp lệ.

### 18.4. Quên giá trị đầu vào của INOUT

```java
sp.registerStoredProcedureParameter(
    3, Integer.class, ParameterMode.INOUT
);

// Quên sp.setParameter(3, initialCount).
```

INOUT có hướng **vào và ra**, nên thường phải có giá trị đầu vào trước khi thực thi. Nếu muốn hỗ trợ null, cần kiểm tra semantics của procedure và cách provider/JDBC truyền null.

### 18.5. Cố set OUT

```java
sp.registerStoredProcedureParameter(
    4, BigDecimal.class, ParameterMode.OUT
);

sp.setParameter(4, BigDecimal.ZERO);
```

Lời gọi `setParameter` không được dùng để gửi giá trị cho OUT-only theo contract. Nếu ứng dụng cần giá trị ban đầu được procedure đọc và cập nhật, chữ ký database phải là **INOUT**, và Java đăng ký `ParameterMode.INOUT`.

### 18.6. Đọc OUT trước khi execute

```java
Object subtotal = sp.getOutputParameterValue(4);
// Chưa thực thi lời gọi procedure.
```

Không có kết quả hợp lệ để đọc trước khi procedure chạy. Đúng trình tự: register, set input, execute, tiêu thụ các kết quả cần thiết rồi lấy output.

### 18.7. Hiểu sai execute(false)

```java
boolean hasResultSet = sp.execute();

if (!hasResultSet) {
    // Sai nếu coi false = procedure thất bại.
}
```

`false` thường chỉ cho biết kết quả đầu tiên không phải result set. OUT vẫn có thể tồn tại.

### 18.8. Sai kiểu Java

```java
sp.registerStoredProcedureParameter(
    2, String.class, ParameterMode.IN
);
sp.setParameter(2, "10.00");
```

Trong khi SQL tham số là DECIMAL. Database có thể tự ép string trong một số trường hợp, nhưng không nên dựa vào chuyển đổi ngầm. Dùng `BigDecimal.class` và `new BigDecimal("10.00")`.

### 18.9. Named parameter không được driver hỗ trợ

Đăng ký và bind bằng tên có thể không hoạt động ở database/provider cụ thể. Khi có lỗi liên quan named binding, đối chiếu khả năng hỗ trợ rồi thử **positional registration** đúng signature; không tự đổi thành chuỗi SQL nối tham số thô.

### 18.10. Procedure không tồn tại hoặc thiếu quyền

`CREATE PROCEDURE` chưa chạy trong schema mà application kết nối, hoặc user kết nối thiếu quyền `EXECUTE`. Lỗi sẽ không được giải quyết bằng đổi `IN` sang `OUT`.

Cần kiểm tra migration, schema/catalog, datasource, quyền thực thi và cách định danh procedure.

### 18.11. Procedure trả NULL nhưng Java unbox

```java
Integer count = (Integer)
    sp.getOutputParameterValue(3);

int primitive = count; // NullPointerException nếu count null.
```

Nếu OUT/INOUT được phép null, cần xử lý trước khi unbox hoặc dùng chính sách default có chủ đích.

### 18.12. Có result set nhưng đọc OUT quá sớm

Với những DB/driver yêu cầu đọc tất cả result sets/update counts trước, việc gọi `getOutputParameterValue` ngay sau `execute` có thể gây lỗi hoặc kết quả không sẵn sàng. Cần dùng `getResultList`, `hasMoreResults` và `getUpdateCount` theo luồng kết quả.

## 19. Biến thể: procedure trả mã kết quả và thông báo

Không phải procedure nào cũng nên ném exception cho mọi tình huống nghiệp vụ. Một số hệ thống định nghĩa:

```sql
CREATE PROCEDURE perform_action(
    IN  p_entity_id BIGINT,
    OUT p_status_code INT,
    OUT p_message VARCHAR(255)
)
...
```

Java:

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("perform_action");

sp.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
sp.registerStoredProcedureParameter(
    2, Integer.class, ParameterMode.OUT
);
sp.registerStoredProcedureParameter(
    3, String.class, ParameterMode.OUT
);

sp.setParameter(1, entityId);
sp.execute();

Integer statusCode = (Integer)
    sp.getOutputParameterValue(2);

String message = (String)
    sp.getOutputParameterValue(3);
```

Ví dụ này là **chữ ký minh họa**, không có thân procedure. Ứng dụng thực cần thống nhất:

- `statusCode` = 0 có nghĩa gì?
- Mã nào là lỗi nghiệp vụ, mã nào yêu cầu rollback?
- `message` có thể null không?
- Nếu DB ném SQL exception, có cần đọc OUT nữa không?
- Khi status success nhưng commit thất bại, trả gì cho caller?

Không chỉ kiểm tra `statusCode == 0` rồi cho rằng transaction đã commit. **OUT code là tín hiệu nghiệp vụ từ procedure, không thay thế transaction outcome.**

## 20. SQL exception và rollback

### 20.1. Lỗi có thể phát sinh tại nhiều bước

Các lỗi thường xuất hiện khi:

- Đăng ký sai mode/type/vị trí.
- Bind thiếu parameter hoặc truyền sai kiểu.
- Provider/JDBC không hỗ trợ named binding.
- Database không tìm thấy procedure.
- Procedure `SIGNAL`/`RAISE` lỗi.
- Constraint/lock/timeout trong SQL bị vi phạm.
- Commit thất bại sau khi procedure đã chạy.

JPA có thể bọc SQL exception vào `PersistenceException` hoặc ngoại lệ khác theo loại thao tác/provider. Không nên viết code chỉ bắt một thông báo lỗi của riêng một DB nếu muốn tính portable.

### 20.2. Rollback transaction thất bại

```java
em.getTransaction().begin();

try {
    StoredProcedureQuery sp =
        em.createStoredProcedureQuery("quote_order");

    // register, set, execute, read outputs ...

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
```

Nếu SQL/procedure làm transaction không còn hợp lệ, không cố sửa một vài field rồi tiếp tục commit transaction lỗi như thể chưa xảy ra gì. Rollback và khởi tạo một transaction/context mới theo quy ước ứng dụng.

### 20.3. OUT có thể đã được trả trước khi commit

Một procedure cập nhật dữ liệu và trả OUT thành công chưa bảo đảm mọi constraint deferred, lỗi serialize hoặc commit-time checks đã qua. Code phải chỉ coi use case ghi hoàn tất khi **commit thành công**.

### 20.4. Không lộ thông tin database nhạy cảm

Thông báo lỗi SQL có thể chứa tên bảng, schema, constraint hoặc nội dung nội bộ. Khi trả lỗi ra HTTP API, chuyển thành mã lỗi nghiệp vụ an toàn, ghi log phía server có phân quyền và tránh trả nguyên stack trace cho client.

## 21. Null input và INOUT có giá trị ban đầu bằng null

### 21.1. Null là dữ liệu có semantics riêng

Trong MySQL example:

```sql
SET p_call_count = COALESCE(p_call_count, 0) + 1;
```

Procedure quy định null được hiểu là 0 trước khi tăng. Về lý thuyết, INOUT nhận null có thể cho đầu ra 1.

Tuy nhiên, **khả năng truyền NULL cho stored procedure parameters không phải lúc nào giống nhau giữa provider/driver**. Một số provider có hành vi đặc thù đối với việc bỏ qua null hoặc truyền null tường minh.

Nếu nghiệp vụ không cần null, một cách rõ ràng hơn là truyền:

```java
sp.setParameter(3, 0);
```

### 21.2. Phân biệt chưa bind và đã bind null

- **Chưa gọi `setParameter`:** parameter chưa được cung cấp giá trị từ Java.
- **Gọi `setParameter(position, null)`:** ứng dụng có chủ đích truyền null, nếu provider cho phép theo type.
- **Procedure có default SQL:** không phải mọi kiểu INOUT/driver đều áp dụng default giống nhau khi Java không bind.

Do đó, không dùng “bỏ bind” như một cách ngầm yêu cầu default. Hãy thống nhất semantics với chữ ký procedure và kiểm tra môi trường thực tế.

### 21.3. Validation ở Java và database

```java
if (discountPercent == null
        || discountPercent.compareTo(BigDecimal.ZERO) < 0
        || discountPercent.compareTo(
            new BigDecimal("100.00")) > 0) {
    throw new IllegalArgumentException(
        "Discount phải nằm trong [0, 100]");
}
```

Validation ở Java cho phản hồi sớm và dễ hiểu. Validation trong procedure vẫn cần nếu nhiều caller khác nhau có thể gọi trực tiếp. **Không coi một tầng validation thay thế hoàn toàn tầng còn lại**.

## 22. Đóng gói StoredProcedureQuery trong service/repository

### 22.1. Tách contract khỏi chi tiết provider

Một thiết kế đơn giản:

```text
REST Controller / Consumer
          |
          v
QuoteService (transaction, validation)
          |
          v
OrderQuoteRepository (StoredProcedureQuery)
          |
          v
Database procedure quote_order
```

Service làm việc với giá trị miền nghiệp vụ như `OrderQuote`; repository xử lý thứ tự tham số, mode và mapping output.

### 22.2. Repository dùng vị trí

```java
@Repository
public class OrderQuoteRepository {

    @PersistenceContext
    private EntityManager em;

    public OrderQuote quote(
            long orderId,
            BigDecimal discountPercent,
            int initialCallCount) {

        StoredProcedureQuery sp =
            em.createStoredProcedureQuery("quote_order");

        sp.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            2, BigDecimal.class, ParameterMode.IN
        );
        sp.registerStoredProcedureParameter(
            3, Integer.class, ParameterMode.INOUT
        );
        sp.registerStoredProcedureParameter(
            4, BigDecimal.class, ParameterMode.OUT
        );
        sp.registerStoredProcedureParameter(
            5, BigDecimal.class, ParameterMode.OUT
        );

        sp.setParameter(1, orderId);
        sp.setParameter(2, discountPercent);
        sp.setParameter(3, initialCallCount);

        sp.execute();

        int callCount = ((Number)
            sp.getOutputParameterValue(3)).intValue();

        BigDecimal subtotal = (BigDecimal)
            sp.getOutputParameterValue(4);

        BigDecimal total = (BigDecimal)
            sp.getOutputParameterValue(5);

        return new OrderQuote(
            orderId, callCount, subtotal, total);
    }
}
```

Ví dụ sử dụng Spring `@Repository` và `@PersistenceContext`. Cần import `org.springframework.stereotype.Repository`, `jakarta.persistence.PersistenceContext`, `EntityManager`, `StoredProcedureQuery`, `ParameterMode` và `BigDecimal`. Procedure được giả định chỉ trả OUT, không có result sets phải tiêu thụ.

### 22.3. Service kiểm tra đầu vào và transaction

```java
@Service
public class QuoteService {

    private final OrderQuoteRepository repository;

    public QuoteService(OrderQuoteRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderQuote quote(
            long orderId,
            BigDecimal discountPercent) {

        if (orderId <= 0) {
            throw new IllegalArgumentException(
                "Order ID không hợp lệ");
        }

        if (discountPercent == null
                || discountPercent.compareTo(BigDecimal.ZERO) < 0
                || discountPercent.compareTo(
                    new BigDecimal("100.00")) > 0) {
            throw new IllegalArgumentException(
                "Discount ngoài khoảng [0, 100]");
        }

        return repository.quote(
            orderId,
            discountPercent,
            0
        );
    }
}
```

Ví dụ dùng Spring `@Service` và `@Transactional`. `readOnly=true` chỉ phù hợp khi procedure không có side effect làm thay đổi database; nếu procedure thực hiện DML, cần transaction ghi và cân nhắc version/state của entity managed.

### 22.4. Vì sao không đưa StoredProcedureQuery thẳng vào controller?

Nếu controller trực tiếp đăng ký năm tham số, các lớp HTTP có thể phải biết quá nhiều về database signature. Khi procedure đổi tên/thứ tự/kiểu, nhiều endpoint phải sửa. Repository/adapter cô lập chi tiết này và giúp service kiểm thử qua contract nghiệp vụ.

### 22.5. Không tái sử dụng một StoredProcedureQuery giữa các request

`StoredProcedureQuery` được tạo gắn với một `EntityManager` và trạng thái tham số/kết quả của lời gọi. Không giữ object query trong static field hoặc singleton service để nhiều thread cùng sửa giá trị và thực thi.

Có thể tái sử dụng **metadata named query**, nhưng mỗi lần gọi nên tạo một instance query mới từ EntityManager phù hợp.

## 23. Thủ tục có nhiều result sets: thiết kế giao diện trả về

Một procedure phức tạp có thể vừa trả:

- Danh sách đơn hàng.
- Danh sách dòng hàng.
- OUT tổng số dòng được xử lý.
- INOUT bộ đếm lời gọi.

Khi đó, **chỉ đọc output parameter là chưa đủ** để đáp ứng contract. Cần xác định rõ result set nào có shape nào và thứ tự nào.

Một interface có thể trả:

```java
public record ProcedureReport(
    List<OrderRow> orders,
    List<OrderLineRow> lines,
    int processedCount,
    int callCount
) {}
```

`OrderRow` và `OrderLineRow` là DTO riêng cần định nghĩa. Dữ liệu từ các result sets được chuyển thành DTO theo result mapping/mapper thích hợp, còn `processedCount` và `callCount` đọc từ OUT/INOUT.

Với nhiều result sets, API chuẩn có các phương thức `execute`, `getResultList`, `getUpdateCount` và `hasMoreResults`. Cách ánh xạ hai tập kết quả từ một procedure có thể phụ thuộc provider và database. Nếu API của ứng dụng cần portability cao, cân nhắc tách procedure đơn giản hơn hoặc dùng JDBC ở một adapter rõ ràng.

## 24. Khi nào nên dùng JDBC `CallableStatement` trực tiếp?

JPA `StoredProcedureQuery` là lựa chọn tốt khi application chủ yếu dùng JPA và procedure có chữ ký tương thích.

Tuy nhiên, một số use case cần các tính năng cấp thấp:

- Cấu hình SQL type/scale output đặc thù.
- Nhiều result sets phức tạp.
- Tham số database-specific như structured type/array.
- Function return status hoặc cursor đặc thù.
- Driver-specific escaping, callable syntax.
- Điều khiển sâu thứ tự result counts và output registration.

Khi đó, JDBC `CallableStatement` trong tầng adapter có thể phù hợp hơn.

### 24.1. Sơ đồ JDBC để đối chiếu

```java
try (Connection connection = dataSource.getConnection();
     CallableStatement statement =
         connection.prepareCall(
             "{call quote_order(?, ?, ?, ?, ?)}")) {

    statement.setLong(1, 101L);
    statement.setBigDecimal(
        2, new BigDecimal("10.00"));
    statement.setInt(3, 4);

    statement.registerOutParameter(
        3, Types.INTEGER);
    statement.registerOutParameter(
        4, Types.DECIMAL);
    statement.registerOutParameter(
        5, Types.DECIMAL);

    statement.execute();

    int count = statement.getInt(3);
    BigDecimal subtotal =
        statement.getBigDecimal(4);
    BigDecimal total =
        statement.getBigDecimal(5);
}
```

Cần import `java.sql.Connection`, `CallableStatement`, `Types`, `java.math.BigDecimal` và `javax.sql.DataSource`.

Đây là ví dụ **JDBC độc lập**, dùng DataSource và connection riêng. Trong ứng dụng Spring/JTA, nếu trộn JDBC với JPA mà lấy connection ngoài transaction, có thể không cùng transaction với EntityManager. Khi cần cùng transaction, phải dùng cơ chế nhận connection/tham gia transaction theo framework/driver, không tự cho rằng một `dataSource.getConnection()` bất kỳ sẽ tự ghép đúng ngữ cảnh.

### 24.2. So sánh JPA và JDBC

| Khía cạnh | StoredProcedureQuery | CallableStatement |
|---|---|---|
| Đăng ký hướng | `ParameterMode.IN/OUT/INOUT` | `registerOutParameter`, setters JDBC |
| Kiểu Java | `Class<?>` trong registration | JDBC `Types` cho OUT; setter/getter theo SQL type |
| Gắn với JPA EntityManager | Có | Không tự động, cần integration |
| Kết quả entity managed | Có thể khi result mapping thành entity | Không tự quản lý entity |
| Database-specific features | Phụ thuộc provider và mức hỗ trợ JPA | Kiểm soát JDBC trực tiếp hơn |
| Cần xử lý transaction | Có | Có |
| Portability | Theo JPA + DB/driver | Theo JDBC + DB/driver |

Mục tiêu không phải “JPA luôn tốt hơn JDBC”, mà là chọn đúng mức trừu tượng cần thiết.

## 25. Kiểm thử tích hợp stored procedure

### 25.1. Vì sao mock không đủ?

Một unit test có thể xác minh repository đã gọi:

```java
registerStoredProcedureParameter(
    3, Integer.class, ParameterMode.INOUT
)
```

nhưng nó **không chứng minh** MySQL procedure thật chấp nhận chữ ký, SQL type hay thứ tự OUT.

Stored procedure phụ thuộc:

- Database engine/version.
- SQL routine đã triển khai.
- JDBC driver.
- JPA provider.
- Quyền/schema.
- Transaction và cơ chế trả result sets.

Do đó cần integration test trên **database đích hoặc database test tương thích thực sự** để xác minh contract.

### 25.2. Dữ liệu và kỳ vọng

Với Order 101 có hai dòng:

```text
2 × 400000.00 + 1 × 120000.00 = 920000.00
Chiết khấu 10% => 828000.00
INOUT count ban đầu 4 => 5
```

Đây là bộ kết quả dễ kiểm chứng.

### 25.3. Ví dụ JUnit integration test

```java
@Test
void procedureReturnsInOutAndOutValues() {
    OrderQuote quote = OrderQuoteProcedure.calculate(
        em,
        101L,
        new BigDecimal("10.00"),
        4
    );

    assertEquals(101L, quote.orderId());
    assertEquals(5, quote.callCount());

    assertEquals(
        0,
        quote.subtotal().compareTo(
            new BigDecimal("920000.00"))
    );

    assertEquals(
        0,
        quote.total().compareTo(
            new BigDecimal("828000.00"))
    );
}
```

Ví dụ giả định test đã chuẩn bị schema/procedure/data và context/transaction phù hợp. JUnit import `org.junit.jupiter.api.Test` cùng các assertion tương ứng.

### 25.4. Các case quan trọng

| Case | Input | Kỳ vọng |
|---|---|---|
| Bình thường | ID 101, 10%, count 4 | count 5, subtotal 920000, total 828000 |
| Không giảm | ID 101, 0%, count 0 | total bằng subtotal |
| Giảm toàn bộ | ID 101, 100%, count 1 | total 0 |
| Order không có Line | Order tồn tại, chưa có Line | subtotal 0, total 0 |
| Order không tồn tại | ID không tồn tại | Procedure báo lỗi theo SQLSTATE |
| Discount âm | -1% | Procedure hoặc validation từ chối |
| Discount quá 100 | 101% | Procedure hoặc validation từ chối |
| OUT nullable | Procedure có OUT không được gán có chủ đích | Caller xử lý null theo contract |
| Named registration | Môi trường hỗ trợ | Kết quả tương đương positional |
| Multiple result sets | Procedure có SELECT output | Xử lý result sets trước OUT |
| Rollback | Procedure thực hiện DML rồi transaction rollback | Không có thay đổi được commit |
| Concurrency | Nhiều lời gọi cùng lúc | Kết quả phù hợp isolation/locking |

### 25.5. Không dùng H2 để chứng minh mọi đặc điểm MySQL

Một database in-memory có thể tiện cho unit/integration test cơ bản, nhưng stored procedures và cách driver xử lý OUT/INOUT là **đặc điểm dễ khác nhau giữa DB**. Với routine MySQL, nên kiểm tra ít nhất một test môi trường MySQL thực tế (có thể dùng container test nếu hạ tầng cho phép).

Không gán nhãn “đã kiểm tra procedure MySQL” chỉ vì một mock provider hoặc database khác trả giá trị như kỳ vọng.

## 26. Bảng chẩn đoán lỗi

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `Parameter not registered` | Chưa register đúng tên/vị trí trước khi set/get | Đăng ký đủ từng tham số |
| `Parameter has not been bound` | IN/INOUT chưa được set | `setParameter` trước execute |
| `Wrong number of arguments` | Thiếu/thừa tham số so với signature | Đối chiếu số lượng và thứ tự DB |
| `Cannot register OUT parameter` | Sai mode/type hoặc driver/provider không hỗ trợ | Kiểm tra SQL type, JPA mode, driver |
| OUT luôn null | Procedure không gán, đọc sai vị trí, driver chưa sẵn sàng | Kiểm tra thân procedure, kết quả và thứ tự đọc |
| INOUT không thay đổi | Chưa đọc bằng getOutputParameterValue, procedure không cập nhật | Kiểm tra logic SQL và output API |
| `execute()` trả false | Kết quả đầu tiên không phải result set | Không coi false là thất bại |
| Named parameter không nhận diện | Provider/DB không hỗ trợ hoặc sai tên | Dùng positional registration khi cần |
| `ClassCastException` khi đọc OUT | Sai Java type với giá trị driver trả | Dùng type đúng, `Number` khi phù hợp |
| NullPointerException khi unbox | OUT có thể null | Kiểm tra null trước khi chuyển primitive |
| `Procedure does not exist` | Sai schema/catalog hoặc thiếu migration | Kiểm tra datasource và deployment |
| `Permission denied / EXECUTE` | User kết nối thiếu quyền | Cấp quyền đúng phạm vi |
| Đọc output báo chưa thể truy cập | Result sets/update counts chưa được xử lý | Tiêu thụ kết quả trước |
| Procedure đọc dữ liệu ORM cũ | Pending entity changes chưa flush | Flush khi procedure cần thấy state mới |
| Entity managed vẫn giữ giá cũ | Procedure DML ngoài dirty checking | Refresh/clear/reload có chủ đích |
| Conflict version sau procedure | Native DML làm lệch version ORM | Đồng bộ protocol optimistic locking |
| Dữ liệu mất sau lời gọi “thành công” | Transaction rollback hoặc commit thất bại | Phân biệt procedure result và commit outcome |
| Chỉ lỗi ở một database | Khác syntax/routine/JDBC semantics | Tách adapter theo DB và integration test |
| Procedure tính toán sai tổng | Sai SQL aggregate, double/decimal hoặc dữ liệu test | Kiểm tra SQL và độ chính xác DECIMAL |

## 27. Bài thực hành

### Bài 1 — Phân biệt ba mode

Cho chữ ký:

```sql
CREATE PROCEDURE example_modes(
    IN p_a BIGINT,
    OUT p_b VARCHAR(50),
    INOUT p_c INT
)
...
```

Liệt kê tham số nào cần `setParameter`, tham số nào cần `getOutputParameterValue` và mode JPA tương ứng. Giải thích vì sao `p_c` cần cả hai thao tác.

### Bài 2 — Đăng ký theo vị trí

Từ `quote_order` của bài học, viết đủ năm lời gọi `registerStoredProcedureParameter` theo vị trí 1–5, ba lời gọi `setParameter` và ba lời gọi đọc output.

Giải thích vì sao vị trí 3 dùng `INOUT` nhưng 4–5 dùng `OUT`.

### Bài 3 — Đăng ký theo tên

Chuyển lời gọi ở bài 2 sang đăng ký/tương tác bằng tên. Liệt kê những yếu tố cần xác minh khi driver báo không hỗ trợ named stored procedure parameters.

### Bài 4 — Thử giá trị chiết khấu

Với Order 101 có subtotal `920000.00`, thử discount `0.00`, `10.00`, `25.00` và `100.00`. Dự đoán total từng trường hợp và so sánh với OUT `p_total`.

Không dùng `double` để kiểm tra sự chính xác của DECIMAL.

### Bài 5 — INOUT không tự đổi biến Java

Gán `Integer count = 10`, truyền vào INOUT, gọi procedure rồi in `count` trước và sau khi gọi `getOutputParameterValue`. Giải thích vì sao biến ban đầu không tự biến thành 11.

### Bài 6 — OUT khác result set

Viết một procedure chỉ trả OUT `p_subtotal` và một procedure trả danh sách dòng hàng bằng `SELECT`. Trong Java, so sánh `getOutputParameterValue` với `getResultList`.

Khi nào một procedure có thể sử dụng cả hai cơ chế?

### Bài 7 — Xử lý nhiều result sets

Thiết kế procedure trả một result set gồm OrderLine, một update count từ DML, và OUT số lượng dòng. Dùng `execute`, `getResultList`, `getUpdateCount` và `hasMoreResults` để xử lý trước khi đọc OUT.

Quan sát hành vi driver thực tế thay vì mặc định mọi DB có cùng thứ tự thông báo kết quả.

### Bài 8 — NamedStoredProcedureQuery

Đặt `@NamedStoredProcedureQuery` và năm `@StoredProcedureParameter` trên một entity hợp lệ. Gọi `createNamedStoredProcedureQuery`, truyền IN/INOUT và đọc OUT.

Giải thích sự khác nhau giữa `name` và `procedureName`.

### Bài 9 — Lỗi do sai thứ tự

Cố ý hoán đổi registration vị trí 3 và 4 trong code test. Quan sát loại lỗi khi execute và output. Sau đó sửa theo chữ ký SQL.

Không dùng mẹo bỏ hết registration để “thấy chạy”; tìm đúng sai lệch contract.

### Bài 10 — Null input

Thử trường hợp `p_call_count` nhận NULL (nếu provider và driver hỗ trợ). Dự đoán kết quả dựa trên `COALESCE(p_call_count, 0) + 1`.

Phân biệt “đã bind null” với “chưa bind”, và trình bày chính sách Java khi null không được phép.

### Bài 11 — Trạng thái managed bị stale

Trong transaction, tải Product managed. Gọi procedure thực hiện UPDATE giá Product, sau đó đọc getter của Product cũ. So sánh với query SQL và `em.refresh(product)`.

Giải thích vì sao OUT giá mới không tự cập nhật field entity đang managed.

### Bài 12 — Rollback và commit

Tạo một procedure cập nhật bảng có DML và OUT status. Gọi procedure trong transaction rồi rollback. Dùng transaction đọc mới kiểm tra dữ liệu.

Tại sao OUT “success” không chứng minh commit?

### Bài 13 — Optimistic locking

Cho entity có `@Version`. Viết quy tắc cần thiết nếu procedure thay đổi cùng hàng: kiểm tra version kỳ vọng, tăng version và báo conflict khi không có hàng được cập nhật.

Tại sao một native UPDATE chỉ có `WHERE id=?` có thể phá vỡ kỳ vọng của ORM?

### Bài 14 — JPA và JDBC

Gọi cùng `quote_order` bằng `StoredProcedureQuery` và `CallableStatement`. So sánh cách đăng ký OUT, cách truyền INOUT và lấy output.

Nêu điều kiện để JDBC cùng tham gia transaction JPA khi framework quản lý connection.

### Bài 15 — Portability

Lập bảng so sánh môi trường MySQL và một database khác (ví dụ PostgreSQL, SQL Server hoặc Oracle) về chữ ký procedure, named parameters, result sets và kiểu OUT.

Xác định phần nào của adapter phải đổi, phần nào của service-level record `OrderQuote` có thể giữ nguyên.

## 28. Ghi nhớ cốt lõi

**Đăng ký tham số IN, OUT và INOUT trong JPA là khai báo contract giữa `StoredProcedureQuery` và chữ ký procedure trong database.** `IN` nhận giá trị do Java truyền vào; `OUT` trả giá trị do procedure tính; `INOUT` vừa nhận giá trị ban đầu vừa trả giá trị sau xử lý.

Quy trình đúng là **tạo query → đăng ký tên/vị trí, kiểu và mode → set giá trị IN/INOUT → execute → xử lý result sets/update counts nếu có → lấy OUT/INOUT**. Không set OUT-only, không đọc output trước khi thực thi, không coi boolean false của `execute()` là dấu hiệu thất bại, và không cho rằng giá trị INOUT tự thay đổi biến Java.

Có thể đăng ký động bằng `registerStoredProcedureParameter` hoặc khai báo metadata bằng `@NamedStoredProcedureQuery` và `@StoredProcedureParameter`. Đăng ký theo tên dễ đọc nhưng cần kiểm tra hỗ trợ driver/database; đăng ký theo vị trí đòi đối chiếu đúng thứ tự chữ ký.

Cuối cùng, stored procedure chạy trong database và có thể có DML, result set, OUT, lỗi SQL hoặc side effect lên dữ liệu đang được JPA quản lý. Hãy giữ ranh giới transaction rõ ràng, đồng bộ pending changes khi cần, xử lý entity stale/optimistic locking có chủ đích và kiểm thử trên đúng DB/provider mục tiêu. **Đúng mode, đúng kiểu, đúng vị trí và đúng thứ tự đọc kết quả là nền tảng để gọi stored procedure an toàn bằng JPA.**
