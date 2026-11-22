# Ảnh hưởng của NULL tới WHERE, JOIN và CHECK

Một trong những khác biệt quan trọng giữa SQL và các phép so sánh thông thường trong lập trình là cách SQL xử lý **`NULL`**. Ví dụ, trong bảng đơn hàng có một đơn chưa biết trạng thái thanh toán, câu truy vấn “lấy các đơn không phải `PAID`” có thể **không trả về đơn đó**, dù trạng thái của nó không phải chuỗi `'PAID'`. Khi nối bảng, những khóa chứa `NULL` cũng không khớp với nhau bằng dấu `=`. Và một ràng buộc `CHECK (amount > 0)` vẫn có thể chấp nhận `amount = NULL`.

Ba hiện tượng trên đều bắt nguồn từ cùng một nguyên tắc: **SQL dùng logic ba giá trị (three-valued logic)** với `TRUE`, `FALSE` và **`UNKNOWN`**. Muốn viết truy vấn và ràng buộc đúng, cần hiểu vai trò của `UNKNOWN` trong từng ngữ cảnh.

Bài học này tập trung vào **ảnh hưởng của `NULL` đối với `WHERE`, `JOIN ... ON` và `CHECK`**, kèm các ví dụ SQL tự chứa. Cú pháp phần lớn là SQL thông dụng; một số khả năng so sánh đặc biệt có thể khác theo hệ quản trị.

## 1. NULL là gì và vì sao không so sánh như giá trị thông thường?

Trong SQL, `NULL` đánh dấu một giá trị **chưa biết, bị thiếu hoặc không áp dụng**. Ý nghĩa cụ thể phụ thuộc mô hình dữ liệu:

- `orders.status = NULL`: chưa biết hoặc chưa ghi nhận trạng thái đơn.
- `orders.amount = NULL`: chưa biết số tiền của đơn.
- `employees.termination_date = NULL`: ngày nghỉ việc chưa có hoặc chưa áp dụng, tùy định nghĩa nghiệp vụ.

`NULL` **khác** số `0`, chuỗi rỗng `''`, khoảng trắng `' '`, giá trị `FALSE` và chuỗi văn bản `'NULL'`. Không nên thay `NULL` bằng `0` một cách máy móc: “chưa biết số tiền” khác với “đã xác định số tiền bằng 0”.

Vì `NULL` không phải một giá trị đã biết, các phép so sánh thông thường với nó **không trả về `TRUE` hoặc `FALSE`**, mà trả về `UNKNOWN`:

| Biểu thức | Kết quả logic | Giải thích |
|---|---|---|
| `5 = 5` | `TRUE` | Hai giá trị đã biết bằng nhau |
| `5 = 7` | `FALSE` | Hai giá trị đã biết khác nhau |
| `5 = NULL` | `UNKNOWN` | Không biết giá trị bên phải |
| `NULL = NULL` | `UNKNOWN` | Không biết hai giá trị chưa biết có bằng nhau không |
| `NULL <> NULL` | `UNKNOWN` | Cũng không thể kết luận chúng khác nhau |
| `NULL > 0` | `UNKNOWN` | Không thể so sánh một số chưa biết với 0 |
| `NULL IS NULL` | `TRUE` | Phép kiểm tra dấu hiệu `NULL` riêng của SQL |
| `5 IS NULL` | `FALSE` | Giá trị 5 không phải `NULL` |

Các phép `=`, `<>`, `<`, `>`, `<=`, `>=` đều có thể tạo `UNKNOWN` nếu toán hạng cần so sánh là `NULL`. Để kiểm tra cột có thiếu giá trị hay không, dùng **`IS NULL`** hoặc **`IS NOT NULL`**:

```sql
-- Đúng: tìm các hàng chưa có trạng thái
WHERE status IS NULL

-- Đúng: tìm các hàng đã có trạng thái
WHERE status IS NOT NULL

-- Sai ý định: không tìm được hàng NULL
WHERE status = NULL
```

**Không nhầm `UNKNOWN` với `FALSE`.** Hai kết quả khác nhau, dù ở một số vị trí chúng đều khiến hàng không được giữ lại.

## 2. Logic ba giá trị: TRUE, FALSE, UNKNOWN

Gọi tắt `T = TRUE`, `F = FALSE`, `U = UNKNOWN`. Toán tử `AND`, `OR`, `NOT` tuân theo logic ba giá trị:

| A | B | A `AND` B | A `OR` B |
|---|---|---|---|
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | T | F | T |
| F | F | F | F |
| F | U | F | U |
| U | T | U | T |
| U | F | F | U |
| U | U | U | U |

Với `NOT`:

| A | `NOT` A |
|---|---|
| T | F |
| F | T |
| U | U |

Hai quy tắc dễ nhớ:

1. `FALSE AND UNKNOWN = FALSE`: khi một điều kiện chắc chắn sai, cả biểu thức `AND` chắc chắn sai.
2. `TRUE OR UNKNOWN = TRUE`: khi một điều kiện chắc chắn đúng, cả biểu thức `OR` chắc chắn đúng.

Nhưng `NOT UNKNOWN` vẫn là `UNKNOWN`; phủ định một điều chưa biết **không biến nó thành điều đã biết là đúng**.

Ví dụ với `status = NULL`:

```sql
-- Biểu thức so sánh bên trong là UNKNOWN, NOT vẫn là UNKNOWN
NOT (status = 'PAID')
```

Khi `status` có giá trị `NULL`, biểu thức trên **không phải `TRUE`**, nên trong `WHERE` hàng đó sẽ không được chọn.

## 3. Bộ dữ liệu mẫu xuyên suốt

Ta dùng hai bảng nhỏ để xem rõ các kết quả. Trong phần thực hành, tạo và chạy các lệnh dưới đây trong **cơ sở dữ liệu thử nghiệm**:

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(50) NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    status VARCHAR(20),
    amount DECIMAL(10, 2) CHECK (amount >= 0)
);

INSERT INTO customers (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO orders (order_id, customer_id, status, amount)
VALUES
    (101, 1,    'PAID',    120.00),
    (102, 1,    NULL,       80.00),
    (103, 2,    'PAID',     NULL),
    (104, NULL, 'PAID',     50.00),
    (105, 3,    'PENDING',   0.00);
```

Đọc dữ liệu mẫu:

**Bảng `customers`**

| customer_id | full_name |
|---:|---|
| 1 | An |
| 2 | Binh |
| 3 | Chi |
| 4 | Dung |

**Bảng `orders`**

| order_id | customer_id | status | amount |
|---:|---:|---|---:|
| 101 | 1 | PAID | 120.00 |
| 102 | 1 | `NULL` | 80.00 |
| 103 | 2 | PAID | `NULL` |
| 104 | `NULL` | PAID | 50.00 |
| 105 | 3 | PENDING | 0.00 |

Các ô hiển thị `NULL` trong bảng trên là **giá trị SQL NULL**, không phải chuỗi `'NULL'`. Ta cố tình có:

- Đơn 102 chưa biết trạng thái.
- Đơn 103 chưa biết số tiền.
- Đơn 104 chưa gắn với khách hàng nào (`customer_id = NULL`).
- Khách Dung chưa có đơn nào.
- Đơn 105 có số tiền **bằng 0**, khác hoàn toàn với `NULL`.

Các ví dụ dưới đây giả sử bảng giữ nguyên trạng thái này, trừ khi có chú thích khác.

## 4. WHERE chỉ giữ các hàng có điều kiện TRUE

Quy tắc cốt lõi:

> Trong mệnh đề **`WHERE`**, chỉ hàng có biểu thức điều kiện đánh giá thành **`TRUE`** được giữ lại. Hàng có `FALSE` **hoặc** `UNKNOWN` đều bị loại.

Xét:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'PAID'
ORDER BY order_id;
```

Kết quả: **101, 103, 104**. Đơn 105 bị loại vì `'PENDING' = 'PAID'` là `FALSE`; đơn 102 bị loại vì `NULL = 'PAID'` là `UNKNOWN`.

### 4.1. Vì sao `<>` và `NOT` không tự tìm được NULL?

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'PAID'
ORDER BY order_id;
```

Kết quả chỉ có **105**; đơn 102 **không xuất hiện**. Điều kiện “trạng thái khác PAID” không tự bao gồm trạng thái chưa biết.

Tương tự:

```sql
SELECT order_id
FROM orders
WHERE NOT (status = 'PAID');
```

Kết quả cũng chỉ có **105**. Với đơn 102, `NOT (UNKNOWN) = UNKNOWN`.

Nếu nghiệp vụ muốn **mọi đơn không có trạng thái PAID, bao gồm trạng thái chưa biết**, phải nói rõ:

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'PAID'
   OR status IS NULL
ORDER BY order_id;
```

Kết quả: **102 và 105**.

Điều này thể hiện hai câu hỏi khác nhau:

- **“Đã biết trạng thái không phải PAID”**: `status <> 'PAID'`.
- **“Không được ghi nhận là PAID”**: `status <> 'PAID' OR status IS NULL`.

Chọn biểu thức theo ý nghĩa nghiệp vụ, không tự mặc định `NULL` là một trạng thái cụ thể.

### 4.2. NULL trong điều kiện khoảng giá trị

```sql
SELECT order_id, amount
FROM orders
WHERE amount >= 0
ORDER BY order_id;
```

Trả về **101, 102, 104, 105**. Đơn 103 có `amount = NULL` nên `NULL >= 0` là `UNKNOWN` và bị loại. Trong khi đó, đơn 105 có `amount = 0` **vẫn được giữ** vì `0 >= 0` là `TRUE`.

Muốn tìm đơn chưa có số tiền:

```sql
SELECT order_id
FROM orders
WHERE amount IS NULL;
-- 103
```

Một cách viết điều kiện cho phép cả hàng chưa có số tiền là:

```sql
WHERE amount >= 0 OR amount IS NULL
```

Nhưng đừng thêm `OR amount IS NULL` vào mọi truy vấn: nếu yêu cầu thực tế là “chỉ các đơn **có giá trị tiền xác định** từ 0 trở lên”, điều kiện `amount >= 0` ban đầu mới chính xác.

### 4.3. AND, OR có thể tác động khác dự đoán

Lấy các đơn có trạng thái PAID **và** số tiền lớn hơn 100:

```sql
SELECT order_id
FROM orders
WHERE status = 'PAID'
  AND amount > 100
ORDER BY order_id;
```

Chỉ có **101**:

- Đơn 101: `TRUE AND TRUE = TRUE`.
- Đơn 103: `TRUE AND UNKNOWN = UNKNOWN` vì `amount` thiếu.
- Đơn 104: `TRUE AND FALSE = FALSE` vì `50 > 100` sai.

Ngược lại, với `status = 'PAID' OR amount > 100`, đơn 103 vẫn được giữ do `TRUE OR UNKNOWN = TRUE`. Điều kiện gồm nhiều vế cần được xem như một biểu thức ba giá trị hoàn chỉnh.

### 4.4. CASE, COALESCE và giá trị mặc định

`CASE WHEN` cũng xét điều kiện theo logic SQL: nhánh `WHEN` được chọn nếu điều kiện là `TRUE`; nếu là `FALSE` hoặc `UNKNOWN`, việc đánh giá tiếp tục sang nhánh khác hoặc `ELSE`.

```sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN 'Da thanh toan'
        WHEN status IS NULL THEN 'Chua biet'
        ELSE 'Chua thanh toan'
    END AS mo_ta
FROM orders
ORDER BY order_id;
```

`COALESCE(expression, fallback)` trả về biểu thức đầu tiên không `NULL`:

```sql
SELECT order_id, COALESCE(amount, 0) AS amount_for_display
FROM orders;
```

Câu này hữu ích khi giao diện muốn hiển thị 0 cho số tiền bị thiếu, nhưng nó **không chứng minh** đơn 103 thực sự có giá trị tiền bằng 0. Nên giữ phân biệt giữa *dữ liệu gốc* và *giá trị thay thế khi hiển thị hoặc tính toán*.

## 5. NULL ảnh hưởng đến JOIN như thế nào?

`JOIN` ghép các hàng theo điều kiện `ON`. Với `INNER JOIN`, chỉ những cặp hàng có `ON` đánh giá thành **`TRUE`** được ghép. Nếu so sánh khóa trả `FALSE` hoặc `UNKNOWN`, cặp đó không khớp.

### 5.1. INNER JOIN không ghép khóa NULL bằng dấu =

```sql
SELECT c.customer_id, c.full_name, o.order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| customer_id | full_name | order_id |
|---:|---|---:|
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Binh | 103 |
| 3 | Chi | 105 |

Đơn **104** không xuất hiện vì `o.customer_id = NULL`; các phép so sánh với mã khách đều thành `UNKNOWN`. Khách **Dung** không xuất hiện vì không có đơn nào khớp.

Ngay cả khi **cả hai phía của điều kiện nối đều là `NULL`**, biểu thức `left_key = right_key` vẫn trả về `UNKNOWN`. Vì vậy, đừng nghĩ hai giá trị thiếu sẽ “tự khớp” với nhau.

### 5.2. LEFT JOIN giữ hàng bên trái và bổ sung NULL ở bên phải

```sql
SELECT c.customer_id, c.full_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| customer_id | full_name | order_id |
|---:|---|---:|
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Binh | 103 |
| 3 | Chi | 105 |
| 4 | Dung | `NULL` |

`LEFT JOIN` giữ mọi khách bên trái. Nếu khách không có đơn khớp, SQL tạo một **hàng mở rộng với các cột của bảng phải là `NULL`** để đại diện cho việc không tìm thấy cặp nối. Đây gọi là **NULL do outer join bổ sung** (*null extension*).

Không nên nhầm hai nguồn `NULL`:

- `orders.status` của đơn 102 là `NULL` **có sẵn trong dữ liệu**: đơn thật có tồn tại.
- `orders.order_id` khi hiển thị khách Dung là `NULL` **do LEFT JOIN sinh ra**: không có đơn khớp.

Phân biệt này rất quan trọng khi kiểm tra “có đơn hay không”.

### 5.3. Đặt bộ lọc ở ON hay WHERE có thể đổi kết quả

Giả sử cần **hiển thị mọi khách, kèm đơn đã thanh toán nếu có**:

```sql
SELECT c.full_name, o.order_id, o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| full_name | order_id | status |
|---|---:|---|
| An | 101 | PAID |
| Binh | 103 | PAID |
| Chi | `NULL` | `NULL` |
| Dung | `NULL` | `NULL` |

Điều kiện trạng thái nằm trong **`ON`**, nên nó quyết định **đơn nào đủ điều kiện ghép**; mọi khách bên trái vẫn được giữ. Đơn 102 có trạng thái `NULL` và đơn 105 có `PENDING` không thỏa điều kiện ghép; Chi và Dung vẫn xuất hiện với các cột đơn `NULL`.

So sánh với câu lệnh chuyển bộ lọc sang **`WHERE`**:

```sql
SELECT c.full_name, o.order_id, o.status
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Kết quả chỉ còn:

| full_name | order_id | status |
|---|---:|---|
| An | 101 | PAID |
| Binh | 103 | PAID |

`WHERE` chạy **sau khi kết quả nối được tạo về mặt logic**. Những hàng có `o.status = NULL` (bao gồm cả hàng không khớp do outer join) khiến phép so sánh thành `UNKNOWN` và bị loại. Câu lệnh này thực tế chỉ giữ các hàng có đơn đã thanh toán, nên không còn danh sách đầy đủ khách.

**Quy tắc thực hành:** nếu muốn giữ tất cả hàng bên trái của `LEFT JOIN` nhưng chỉ nối những bản ghi bên phải thỏa tiêu chí, thường đặt tiêu chí liên quan bảng phải trong `ON`. Nếu mục tiêu là lọc kết quả cuối cùng, dùng `WHERE` theo đúng ý định.

### 5.4. Tìm khách không có đơn bằng LEFT JOIN

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

Kết quả chỉ có **Dung**. `orders.order_id` là **khóa chính `NOT NULL`**, nên không thể là `NULL` trong một bản ghi đơn thật; khi nó là `NULL` trong kết quả `LEFT JOIN`, nghĩa là không có hàng đơn khớp.

Tránh dùng cột phải **vốn có thể `NULL`** để kết luận “không có cặp ghép”:

```sql
-- Không dùng để tìm khách không có đơn:
SELECT c.full_name
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.status IS NULL;
```

Câu trên trả về **An** (vì đơn 102 có `status = NULL`) **và Dung** (vì không có đơn). Nó không có nghĩa “hai khách chưa từng có đơn”.

Nếu mục tiêu là **khách chưa có đơn đã thanh toán**, hãy dùng điều kiện tương ứng:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
-- Chi, Dung
```

`NOT EXISTS` kiểm tra **không tồn tại hàng con thỏa điều kiện**, không phụ thuộc một cột ngoài join có vô tình chứa `NULL` hay không.

### 5.5. RIGHT JOIN, FULL OUTER JOIN và so sánh NULL an toàn

`RIGHT JOIN` giữ toàn bộ hàng bên phải; `FULL OUTER JOIN` giữ cả các hàng không khớp từ hai phía (khi DBMS hỗ trợ). Cột của phía không có đối tác sẽ được điền `NULL`. Trong dữ liệu mẫu, `FULL OUTER JOIN` có thể hiển thị cả **khách Dung không có đơn** và **đơn 104 không gắn khách**, mỗi hàng có cột của phía còn lại là `NULL`.

Trong một số trường hợp thật sự muốn so sánh **hai giá trị `NULL` như bằng nhau**, có thể sử dụng phép so sánh **null-safe**, nếu DBMS hỗ trợ:

```sql
-- PostgreSQL và một số DBMS hỗ trợ cú pháp này:
SELECT *
FROM table_a AS a
JOIN table_b AS b
  ON a.optional_code IS NOT DISTINCT FROM b.optional_code;
```

`IS NOT DISTINCT FROM` trả về `TRUE` khi cả hai là `NULL`, `FALSE` khi chỉ một phía `NULL`, và so sánh bình thường khi cả hai có giá trị. Cú pháp và tính năng tương đương khác nhau giữa các DBMS (ví dụ MySQL có toán tử `<=>`).

Tuy nhiên, **đừng nối các khóa định danh chưa biết với nhau chỉ vì cả hai là `NULL`**: hai đơn không rõ khách không vì thế mà cùng thuộc một khách. Chỉ dùng so sánh null-safe khi quy tắc nghiệp vụ thực sự coi “đều thiếu” là một trường hợp khớp.

## 6. NULL trong CHECK: UNKNOWN được chấp nhận

`CHECK (điều_kiện)` là ràng buộc dữ liệu. Nó kiểm tra mỗi hàng khi dữ liệu được ghi hoặc cập nhật theo quy tắc DBMS. Điểm khác biệt quan trọng với `WHERE` là:

| Kết quả điều kiện | `WHERE` | `JOIN ... ON` trong INNER JOIN | `CHECK` |
|---|---|---|---|
| `TRUE` | Giữ hàng | Ghép cặp hàng | **Chấp nhận** |
| `FALSE` | Loại hàng | Không ghép cặp | **Từ chối** |
| `UNKNOWN` | Loại hàng | Không ghép cặp | **Chấp nhận** |

Đối với ràng buộc `CHECK` thông thường trong SQL, **chỉ kết quả `FALSE` mới vi phạm ràng buộc**. Nếu điều kiện là `UNKNOWN` do có `NULL`, hàng vẫn được phép tồn tại. Cách hành xử này cho phép dùng `CHECK` cho những cột **tùy chọn** mà không buộc chúng phải có giá trị.

### 6.1. CHECK (amount >= 0) không có nghĩa amount NOT NULL

Schema ví dụ đã khai báo:

```sql
amount DECIMAL(10, 2) CHECK (amount >= 0)
```

Xét các giá trị thử:

| `amount` | `amount >= 0` | Kết quả CHECK |
|---:|---|---|
| 100.00 | `TRUE` | Chấp nhận |
| 0.00 | `TRUE` | Chấp nhận |
| -10.00 | `FALSE` | **Từ chối** |
| `NULL` | `UNKNOWN` | **Chấp nhận** |

Vì vậy, đơn 103 có `amount = NULL` vẫn hợp lệ dù bảng có `CHECK (amount >= 0)`. Ràng buộc đó có ý nghĩa: **nếu đã có số tiền thì số tiền không được âm**.

Nếu nghiệp vụ bắt buộc mọi đơn đều có số tiền, hãy kết hợp **`NOT NULL`**:

```sql
CREATE TABLE required_amounts (
    id INTEGER PRIMARY KEY,
    amount DECIMAL(10, 2) NOT NULL
        CHECK (amount >= 0)
);

-- Hợp lệ
INSERT INTO required_amounts (id, amount) VALUES (1, 0.00);

-- Không hợp lệ: NOT NULL
-- INSERT INTO required_amounts (id, amount) VALUES (2, NULL);

-- Không hợp lệ: CHECK
-- INSERT INTO required_amounts (id, amount) VALUES (3, -5.00);
```

`NOT NULL` và `CHECK` bổ sung nhau: **`NOT NULL` kiểm soát việc có giá trị**, còn **`CHECK` kiểm soát điều kiện trên giá trị đó**.

### 6.2. CHECK với nhiều cột có thể bỏ lọt dữ liệu thiếu

Ví dụ một lịch sự kiện có ngày bắt đầu và kết thúc:

```sql
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY,
    starts_on DATE,
    ends_on DATE,
    CHECK (ends_on >= starts_on)
);
```

Các trường hợp:

| starts_on | ends_on | Điều kiện CHECK | Kết quả |
|---|---|---|---|
| 2025-05-01 | 2025-05-02 | `TRUE` | Chấp nhận |
| 2025-05-03 | 2025-05-02 | `FALSE` | Từ chối |
| `NULL` | 2025-05-02 | `UNKNOWN` | Chấp nhận |
| 2025-05-01 | `NULL` | `UNKNOWN` | Chấp nhận |

Nếu quy tắc nghiệp vụ là **sự kiện luôn có cả hai ngày**, cần định nghĩa:

```sql
CREATE TABLE scheduled_events (
    event_id INTEGER PRIMARY KEY,
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    CHECK (ends_on >= starts_on)
);
```

Nếu ngày kết thúc **được phép chưa xác định**, không thêm `NOT NULL` vào `ends_on`; ràng buộc ban đầu có thể là lựa chọn phù hợp. Điều quan trọng là xác định rõ cột nào là bắt buộc.

### 6.3. OR và UNKNOWN có thể khiến CHECK qua dù một vế sai

Xét một ví dụ độc lập:

```sql
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    status VARCHAR(20),
    amount DECIMAL(10, 2),
    CHECK (status = 'PAID' OR amount > 0)
);
```

Nếu nhập `status = NULL` và `amount = 0`:

- `status = 'PAID'` là `UNKNOWN`.
- `amount > 0` là `FALSE`.
- `UNKNOWN OR FALSE = UNKNOWN`.
- `CHECK` **chấp nhận** hàng đó.

Nếu yêu cầu thực sự là “trạng thái bắt buộc được biết; nếu không phải PAID thì amount phải lớn hơn 0”, cần thể hiện rõ phần bắt buộc:

```sql
CREATE TABLE stricter_payments (
    payment_id INTEGER PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(10, 2),
    CHECK (status = 'PAID' OR amount > 0)
);
```

Trong ví dụ này, `NOT NULL` loại trường hợp trạng thái không rõ. Nhưng nếu `status = 'PENDING'` và `amount = NULL` thì biểu thức `FALSE OR UNKNOWN = UNKNOWN` vẫn được chấp nhận; khi **amount cũng bắt buộc**, phải khai báo thêm `amount NOT NULL` hoặc viết logic kiểm tra bắt buộc một cách rõ ràng. Thiết kế ràng buộc luôn phải xuất phát từ ý nghĩa nghiệp vụ.

### 6.4. CHECK có thể kiểm soát NULL nếu viết rõ

Có thể biểu diễn điều kiện “giá trị bắt buộc và không âm” bằng một `CHECK`:

```sql
CHECK (amount IS NOT NULL AND amount >= 0)
```

Với `amount = NULL`, vế đầu là `FALSE`, vế sau là `UNKNOWN`, nên `FALSE AND UNKNOWN = FALSE` và `CHECK` từ chối. Tuy nhiên, khi chỉ cần bắt buộc giá trị, khai báo **`NOT NULL` trực tiếp** thường dễ đọc và rõ ý hơn.

## 7. Hai bẫy liên quan: NOT IN và COUNT

### 7.1. NOT IN có thể trả về ít hàng bất ngờ khi tập con chứa NULL

Giả sử cần tìm khách **chưa từng có đơn**. Cách viết trông hợp lý:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id FROM orders
);
```

Trong dữ liệu mẫu, truy vấn con trả các giá trị `1, 1, 2, NULL, 3`. Với khách **Dung** (`customer_id = 4`), biểu thức tương đương về mặt logic với:

```sql
4 <> 1 AND 4 <> 1 AND 4 <> 2 AND 4 <> NULL AND 4 <> 3
```

Tất cả phép so sánh với giá trị đã biết đều là `TRUE`, nhưng `4 <> NULL` là `UNKNOWN`. Kết quả tổng hợp là `UNKNOWN`, nên `WHERE` loại khách Dung. Các khách 1, 2 và 3 cũng bị loại vì đã có đơn. Vì vậy truy vấn **không trả hàng nào**, dù Dung thật sự chưa có đơn.

Cách diễn đạt chắc chắn hơn:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
-- 4, Dung
```

`NOT EXISTS` kiểm tra có hay không một hàng khớp điều kiện; các hàng có `o.customer_id = NULL` không làm thay đổi kết quả đối với khách 4. Trong ví dụ đơn giản này cũng có thể thêm `WHERE customer_id IS NOT NULL` vào truy vấn con của `NOT IN`, nhưng `NOT EXISTS` thường làm rõ ý định “không tồn tại hàng liên quan” hơn.

### 7.2. COUNT(*) khác COUNT(column)

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(amount) AS known_amounts,
    SUM(amount) AS sum_known_amounts
FROM orders;
```

Kết quả với dữ liệu mẫu:

| all_orders | known_amounts | sum_known_amounts |
|---:|---:|---:|
| 5 | 4 | 250.00 |

`COUNT(*)` đếm mọi hàng, kể cả hàng có cột `NULL`; `COUNT(amount)` chỉ đếm hàng mà `amount` **không `NULL`**. `SUM(amount)` bỏ qua `NULL` và cộng bốn giá trị đã biết: `120 + 80 + 50 + 0 = 250`. Tổng ở đây **không có nghĩa số tiền thiếu của đơn 103 bằng 0**; nó là tổng các giá trị được biết.

Nếu tất cả hàng đều có `amount = NULL`, `SUM(amount)` trả về `NULL`, trong khi `COUNT(amount)` trả về 0. Những kết quả này quan trọng khi làm báo cáo hoặc xây dựng điều kiện từ dữ liệu tổng hợp.

## 8. Mẫu truy vấn đúng theo từng ý định

| Mục tiêu | Mẫu SQL | Chú ý |
|---|---|---|
| Giá trị chắc chắn là NULL | `col IS NULL` | Không dùng `col = NULL` |
| Giá trị đã được cung cấp | `col IS NOT NULL` | Không khẳng định giá trị ấy hợp lệ về nghiệp vụ |
| Trạng thái đã biết, không phải PAID | `status <> 'PAID'` | Không gồm `NULL` |
| Trạng thái khác PAID hoặc chưa biết | `status <> 'PAID' OR status IS NULL` | Gồm `NULL` theo yêu cầu |
| Đơn có số tiền đã biết và không âm | `amount >= 0` trong `WHERE` | Hàng `NULL` bị loại |
| Ghép khách với các đơn đã thanh toán, giữ mọi khách | Điều kiện `o.status = 'PAID'` trong `ON` của `LEFT JOIN` | Khách không có đơn phù hợp vẫn xuất hiện |
| Tìm khách không có đơn | `NOT EXISTS` hoặc `LEFT JOIN` + kiểm tra khóa chính phải `IS NULL` | Tránh kiểm tra cột phải vốn có thể NULL |
| Ràng buộc giá trị nếu có thì không âm | `CHECK (amount >= 0)` | Vẫn cho phép `NULL` |
| Bắt buộc có số tiền và không âm | `amount NOT NULL CHECK (amount >= 0)` | Kiểm soát cả sự hiện diện lẫn miền giá trị |
| So sánh hai giá trị mà coi NULL–NULL là bằng | `IS NOT DISTINCT FROM` khi DBMS hỗ trợ | Chỉ dùng nếu đúng nghĩa nghiệp vụ |

## 9. Những lỗi tư duy thường gặp

**“NULL = NULL chắc chắn là TRUE.”** Sai trong phép so sánh bằng thông thường của SQL: kết quả là `UNKNOWN`. Dùng `IS NULL` để nhận diện dữ liệu thiếu, hoặc phép so sánh null-safe khi thực sự cần.

**“WHERE NOT (điều kiện) sẽ chọn mọi hàng không đạt điều kiện.”** Không luôn đúng. Hàng có điều kiện `UNKNOWN` thường vẫn là `UNKNOWN` sau `NOT` và không được `WHERE` chọn.

**“LEFT JOIN bảo đảm mọi hàng trái luôn còn sau truy vấn.”** `LEFT JOIN` giữ hàng trái **ở bước nối**, nhưng `WHERE` đặt sau đó vẫn có thể loại hàng, đặc biệt khi điều kiện chỉ kiểm tra cột phải.

**“Cột phải NULL nghĩa là không có bản ghi bên phải.”** Chỉ chắc chắn khi xét **cột không thể NULL ở một bản ghi thật** (thường là khóa chính). Một cột như `status` có thể `NULL` dù đơn hàng có thật.

**“CHECK (x > 0) đã cấm x bằng NULL.”** Sai; biểu thức là `UNKNOWN` và `CHECK` vẫn chấp nhận. Dùng `NOT NULL` nếu giá trị bắt buộc.

**“COALESCE(x, 0) làm rõ rằng x thực sự bằng 0.”** Không. Nó trả giá trị thay thế khi x thiếu. Đừng dùng để che giấu dữ liệu chưa được xác định nếu điều đó ảnh hưởng nghiệp vụ.

**“Không có kết quả với NOT IN nghĩa là tất cả hàng đều có quan hệ.”** Không nhất thiết; một `NULL` trong truy vấn con có thể khiến phép so sánh cho những hàng còn lại thành `UNKNOWN`.

## 10. Bài tập tự kiểm tra

### Bài 1 — Đọc logic WHERE

Với năm đơn mẫu, hãy dự đoán mã đơn mà từng câu truy vấn trả về **trước khi chạy**:

```sql
-- A
SELECT order_id FROM orders WHERE status <> 'PAID' ORDER BY order_id;

-- B
SELECT order_id FROM orders
WHERE status <> 'PAID' OR status IS NULL ORDER BY order_id;

-- C
SELECT order_id FROM orders
WHERE amount > 0 AND status = 'PAID' ORDER BY order_id;
```

Đáp án: **A → 105; B → 102, 105; C → 101, 104**. Đơn 103 không xuất hiện trong C vì số tiền `NULL` làm `amount > 0` thành `UNKNOWN`.

### Bài 2 — So sánh ON và WHERE

Chạy hai câu `LEFT JOIN` ở mục 5.3, giải thích vì sao **Chi** và **Dung** chỉ xuất hiện trong câu đặt `o.status = 'PAID'` ở `ON`. Hãy thử chuyển điều kiện sang `WHERE` rồi đối chiếu số hàng.

Gợi ý: kiểm tra xem `WHERE` đánh giá biểu thức `NULL = 'PAID'` thành gì.

### Bài 3 — Viết CHECK đúng yêu cầu

Thiết kế bảng `scores` có `score` trong khoảng từ 0 đến 100:

1. Phiên bản A cho phép **chưa chấm điểm** (`NULL`).
2. Phiên bản B bắt buộc **mọi hàng đều có điểm**.

Gợi ý đáp án:

```sql
-- A: điểm tùy chọn
CREATE TABLE scores_optional (
    id INTEGER PRIMARY KEY,
    score INTEGER CHECK (score BETWEEN 0 AND 100)
);

-- B: điểm bắt buộc
CREATE TABLE scores_required (
    id INTEGER PRIMARY KEY,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100)
);
```

Hãy thử `NULL`, `0`, `100`, `101` và `-1` để quan sát khác biệt.

### Bài 4 — Tìm khách không có đơn

Dựa trên bảng mẫu, viết hai cách tìm khách chưa có đơn:

1. `LEFT JOIN` rồi lọc `o.order_id IS NULL`.
2. `NOT EXISTS` với truy vấn con liên hệ `o.customer_id = c.customer_id`.

Cả hai cách đều phải trả về **Dung**. Sau đó thử `NOT IN` với truy vấn con `SELECT customer_id FROM orders`, giải thích vì sao kết quả khác do đơn 104 có `customer_id = NULL`.

### Bài 5 — Quy tắc giao dịch thực tế

Một bảng hóa đơn cho phép `paid_at` là `NULL` khi chưa thanh toán. Người dùng yêu cầu “hóa đơn đã thanh toán trong tháng này”. Có nên dùng `paid_at IS NULL` như một phần điều kiện hay không? Hãy mô tả sự khác biệt giữa **hóa đơn chưa có ngày thanh toán** và **hóa đơn có ngày thanh toán nằm ngoài tháng cần tìm** trước khi viết SQL.

## Kết luận

`NULL` khiến SQL dùng **ba giá trị logic: `TRUE`, `FALSE`, `UNKNOWN`**. Một biểu thức so sánh với `NULL` thường tạo `UNKNOWN`, nhưng các cấu trúc SQL xử lý kết quả này khác nhau:

- **`WHERE`:** chỉ giữ hàng có điều kiện `TRUE`; `FALSE` và `UNKNOWN` đều bị loại.
- **`JOIN ... ON`:** chỉ ghép cặp khi điều kiện `TRUE`; `LEFT/RIGHT/FULL OUTER JOIN` có thể bổ sung `NULL` cho phía không có hàng khớp. Đặt điều kiện trong `ON` hay `WHERE` ảnh hưởng kết quả.
- **`CHECK`:** từ chối khi điều kiện `FALSE`; chấp nhận `TRUE` **và `UNKNOWN`**. Cột bắt buộc thường cần thêm `NOT NULL`.

Khi gặp dữ liệu thiếu, hãy tự hỏi: **“NULL trong cột này có ý nghĩa nghiệp vụ gì, và điều kiện hiện tại sẽ tạo TRUE, FALSE hay UNKNOWN?”** Trả lời được hai câu hỏi đó sẽ giúp bạn tránh nhiều lỗi khó thấy khi lọc dữ liệu, nối bảng và thiết kế ràng buộc cơ sở dữ liệu.
