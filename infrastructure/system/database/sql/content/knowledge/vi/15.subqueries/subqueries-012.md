# Kiểm chứng truy vấn con với đầu vào rỗng, nhiều hàng và bản sao

Một truy vấn con (*subquery*) có thể hoạt động hoàn toàn đúng với vài dòng dữ liệu thử nghiệm nhưng trả sai kết quả khi dữ liệu thực thay đổi. Những tình huống dễ bị bỏ sót nhất là:

- **Đầu vào rỗng:** truy vấn con không trả hàng nào.
- **Một hàng:** trường hợp đơn giản, thường được người học thử trước.
- **Nhiều hàng:** một truy vấn con dùng làm giá trị đơn có thể phát sinh lỗi; một truy vấn dùng `IN` hoặc `EXISTS` lại xử lý bình thường.
- **Bản sao/giá trị trùng lặp (*duplicates*):** `IN` và `EXISTS` thường không quan tâm số lần xuất hiện, trong khi `JOIN`, `COUNT` và `SUM` có thể thay đổi số hàng hoặc kết quả tổng hợp.
- **Giá trị `NULL`:** một hàng chứa `NULL` khác với không có hàng nào, đặc biệt đối với `NOT IN`.

Đây không chỉ là các “trường hợp biên”. Chúng quyết định trực tiếp việc truy vấn tìm khách hàng chưa có đơn, xác định giao dịch thỏa điều kiện, tính tổng tiền và lựa chọn một bản ghi liên quan có đúng hay không.

Bài học hướng dẫn xây **bộ dữ liệu kiểm chứng có chủ đích**, dự đoán kết quả theo ngữ nghĩa SQL, rồi viết truy vấn phù hợp với số hàng mà truy vấn con có thể trả. Ví dụ thực hành chủ yếu dùng **PostgreSQL**; khác biệt đáng chú ý ở MySQL, SQL Server, Oracle và SQLite được nêu rõ.

## 1. Ba khía cạnh phải kiểm tra với mọi truy vấn con

Trước khi viết câu SQL có truy vấn con, hãy phân biệt ba khía cạnh:

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Số hàng (*cardinality*)** | Truy vấn con có thể trả 0, 1 hay nhiều hàng? | Một khách hàng có thể có 0 hoặc 5 đơn. |
| **Số cột/hình dạng kết quả** | Vị trí đang dùng chấp nhận một giá trị, một cột nhiều hàng hay một bảng nhiều cột? | `SELECT (SELECT amount ...)` yêu cầu giá trị đơn; `FROM (SELECT ...)` là nguồn bảng. |
| **Tính trùng lặp và giá trị thiếu** | Có nhiều hàng giống nhau về giá trị so sánh không? Có `NULL` không? | Một khách hàng có hai đơn cùng `amount`; mã khách ở bảng đơn có thể là `NULL`. |

Bỏ sót một trong ba khía cạnh có thể dẫn đến lỗi rất khác nhau:

- **Lỗi thực thi:** truy vấn con dùng trong ngữ cảnh vô hướng trả nhiều hàng.
- **Kết quả rỗng không mong muốn:** `NOT IN` gặp `NULL` trong tập bên phải.
- **Nhân số hàng:** dùng `JOIN` khi thực ra chỉ cần kiểm tra tồn tại.
- **Tổng bị cộng trùng:** nối bảng chi tiết trước khi tính một chỉ số ở cấp bảng cha.
- **Chọn hàng không ổn định:** dùng `LIMIT 1` mà không có thứ tự xác định.

### 1.1. “Bản sao” trong kết quả truy vấn nghĩa là gì?

Ở đây **bản sao** là các **hàng hoặc giá trị trùng lặp trong kết quả SQL**, không phải sao chép một file hay sao lưu database.

Ví dụ:

```text
Truy vấn con trả:
customer_id
-----------
1
1
2
2
2
```

Tập **giá trị phân biệt** là `{1, 2}` nhưng kết quả thực tế có **5 hàng**.

Trong SQL, một kết quả truy vấn thông thường có ngữ nghĩa gần với **đa tập (*bag/multiset*)**: cùng giá trị có thể xuất hiện nhiều lần. `DISTINCT` hoặc `UNION` mới áp dụng loại trùng trong những ngữ cảnh tương ứng.

Vì vậy cần kiểm tra **số hàng**, **số giá trị phân biệt**, và **số hàng có `NULL`** một cách riêng biệt.

## 2. Các loại truy vấn con và kỳ vọng về số hàng

Không phải truy vấn con nào cũng có cùng yêu cầu.

| Vị trí/kiểu sử dụng | Số hàng hợp lệ | Điều cần kiểm chứng |
| --- | --- | --- |
| Scalar subquery: `(SELECT one_column ...)` trong `SELECT` hoặc phép so sánh với `=` | 0 hoặc 1; nhiều hàng thường gây lỗi | 0 hàng → `NULL`; 1 hàng → giá trị; nhiều hàng → lỗi ở nhiều DBMS |
| `x IN (SELECT one_column ...)` | 0, 1 hoặc nhiều | Có giá trị khớp không, có `NULL` không, trùng lặp có làm đổi tính đúng/sai không |
| `x NOT IN (SELECT one_column ...)` | 0, 1 hoặc nhiều | Đặc biệt chú ý `NULL` trong truy vấn con |
| `EXISTS (SELECT ...)` | 0, 1 hoặc nhiều | Chỉ hỏi có **ít nhất một hàng** không |
| `NOT EXISTS (SELECT ...)` | 0, 1 hoặc nhiều | Chỉ hỏi **không có hàng** |
| `x op ANY (SELECT ...)` | 0, 1 hoặc nhiều | Toán tử so sánh và logic ba giá trị |
| `x op ALL (SELECT ...)` | 0, 1 hoặc nhiều | Tất cả phép so sánh phải đúng; tập rỗng là trường hợp đặc biệt |
| Derived table trong `FROM (SELECT ...) AS t` | 0, 1 hoặc nhiều hàng; có thể nhiều cột | Kết quả tham gia `JOIN` hoặc phép tính tiếp theo như một quan hệ |
| Correlated subquery | Số hàng **thay đổi theo từng hàng ngoài** | Phải kiểm chứng khách có 0/1/n bản ghi khớp, không chỉ một trường hợp mẫu |

Điểm mấu chốt: **số hàng mà SQL cho phép phụ thuộc vị trí truy vấn con được sử dụng**. Không được đánh giá một truy vấn con chỉ bằng việc “chạy riêng thấy có kết quả”.

## 3. Tạo bộ dữ liệu mẫu có đủ các trường hợp

Các ví dụ sử dụng hai bảng:

- `demo_customers`: bốn khách hàng.
- `demo_orders`: các đơn hàng, có khách nhiều đơn, giá trị trùng và một hàng chưa xác định mã khách.

Chạy trên **PostgreSQL trong database thử nghiệm**:

```sql
CREATE TABLE demo_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NULL
        REFERENCES demo_customers(customer_id),
    order_status VARCHAR(20) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO demo_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO demo_orders (order_id, customer_id, order_status, amount)
VALUES
    (101, 1, 'PAID',    500),
    (102, 1, 'NEW',     200),
    (103, 1, 'NEW',     200),
    (104, 2, 'PAID',    800),
    (105, 2, 'PAID',    800),
    (106, 3, 'NEW',     300),
    (107, NULL, 'REVIEW', 100);
```

**Bảng khách hàng:**

| customer_id | customer_name |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 3 | Chi |
| 4 | Dung |

**Bảng đơn hàng:**

| order_id | customer_id | order_status | amount |
| ---: | ---: | --- | ---: |
| 101 | 1 | PAID | 500 |
| 102 | 1 | NEW | 200 |
| 103 | 1 | NEW | 200 |
| 104 | 2 | PAID | 800 |
| 105 | 2 | PAID | 800 |
| 106 | 3 | NEW | 300 |
| 107 | `NULL` | REVIEW | 100 |

Bảng `demo_orders` có `order_id` là khóa chính nên **không có hai đơn trùng `order_id`**. Nhưng kết quả:

```sql
SELECT customer_id
FROM demo_orders
ORDER BY order_id;
```

trả:

```text
1, 1, 1, 2, 2, 3, NULL
```

Tức là có **nhiều hàng trùng về `customer_id`**. Đồng thời có những đơn trùng `amount`:

- Hai đơn `102` và `103` đều có tiền `200`.
- Hai đơn `104` và `105` đều có tiền `800`.

### 3.1. Ma trận trường hợp

| Khách | Số đơn khớp | Đặc điểm |
| --- | ---: | --- |
| An (`1`) | 3 | Nhiều hàng; hai đơn cùng tiền `200` |
| Bình (`2`) | 2 | Nhiều hàng; cả hai đơn cùng tiền `800` |
| Chi (`3`) | 1 | Chính xác một hàng |
| Dung (`4`) | 0 | Đầu vào rỗng |
| Hàng đơn `107` | Mã khách `NULL` | Trường hợp `NULL` ở kết quả subquery |

Bộ dữ liệu này được chọn để một truy vấn con tương quan có thể gặp **0, 1, 2 và 3 hàng** ngay trong một câu SQL.

## 4. Kiểm tra truy vấn con trước khi lồng vào câu chính

Một cách đọc truy vấn con dễ hiểu là chạy riêng phần con với một giá trị mẫu.

Ví dụ, số đơn của An:

```sql
SELECT order_id, amount
FROM demo_orders
WHERE customer_id = 1
ORDER BY order_id;
```

Kết quả:

| order_id | amount |
| ---: | ---: |
| 101 | 500 |
| 102 | 200 |
| 103 | 200 |

Đổi `customer_id = 1` thành `3`, truy vấn chỉ trả một hàng; đổi thành `4`, nó trả không có hàng nào.

### 4.1. Kiểm chứng số hàng, số giá trị phân biệt và NULL

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT customer_id) AS distinct_customer_count,
    COUNT(customer_id) AS non_null_customer_count,
    SUM(
        CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END
    ) AS null_customer_count
FROM demo_orders;
```

Kết quả:

| row_count | distinct_customer_count | non_null_customer_count | null_customer_count |
| ---: | ---: | ---: | ---: |
| 7 | 3 | 6 | 1 |

Giải thích:

- `COUNT(*) = 7` vì có bảy hàng đơn.
- `COUNT(DISTINCT customer_id) = 3` vì có ba mã xác định là `1`, `2` và `3`.
- `COUNT(customer_id) = 6` vì hàm này bỏ các giá trị `NULL`.
- Một đơn có `customer_id IS NULL`.

Các con số này mô tả **các khía cạnh khác nhau** của kết quả. `COUNT(DISTINCT ...)` không phải cách thay thế `COUNT(*)` khi quan tâm đến số hàng mà scalar subquery sẽ trả.

### 4.2. Giữ thí nghiệm độc lập

Khi thử một trường hợp biên, nên có truy vấn minh họa riêng và kết quả dự đoán. Ví dụ:

```sql
-- Không có hàng
SELECT order_id
FROM demo_orders
WHERE customer_id = 4;

-- Một hàng
SELECT order_id
FROM demo_orders
WHERE customer_id = 3;

-- Nhiều hàng
SELECT order_id
FROM demo_orders
WHERE customer_id = 1;

-- Nhiều giá trị bằng nhau
SELECT amount
FROM demo_orders
WHERE customer_id = 2;
```

Đây là cách tạo thí nghiệm về **cardinality** mà không cần giả định dữ liệu production có sẵn các trường hợp tương ứng.

## 5. Scalar subquery: không có hàng thì trả NULL

**Scalar subquery** dùng một truy vấn như **một giá trị đơn** trong một biểu thức.

Ví dụ:

```sql
SELECT (
    SELECT amount
    FROM demo_orders
    WHERE order_id = 101
) AS selected_amount;
```

Vì khóa chính `order_id = 101` xác định đúng một đơn, kết quả là:

| selected_amount |
| ---: |
| 500 |

### 5.1. Khi không tìm thấy hàng

```sql
SELECT (
    SELECT amount
    FROM demo_orders
    WHERE order_id = 999
) AS selected_amount;
```

Kết quả là **một hàng với `selected_amount = NULL`**, chứ không phải một tập kết quả không có hàng.

| selected_amount |
| --- |
| `NULL` |

Cần phân biệt:

- **Truy vấn con** trả **0 hàng**.
- **Truy vấn ngoài** vẫn trả một hàng có biểu thức scalar được đánh giá là **`NULL`**.

Cũng cần phân biệt với một truy vấn con **có một hàng mà giá trị được chọn là `NULL`**: trong ngữ cảnh scalar, cả hai trường hợp đều cho biểu thức `NULL` và cần điều kiện khác nếu phải biết sự tồn tại của hàng.

### 5.2. Kiểm tra với từng khách hàng

Nếu dùng khóa chính của một đơn cụ thể, không có vấn đề nhiều hàng. Nhưng khi dùng `customer_id`:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.amount
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS one_order_amount
FROM demo_customers AS c
ORDER BY c.customer_id;
```

truy vấn **không an toàn** trên PostgreSQL vì An có ba đơn, Bình có hai đơn. Scalar subquery của họ trả **nhiều hơn một hàng**.

Chưa được phép kết luận rằng vì Dung không có đơn thì scalar subquery “luôn hợp lệ”. Phải kiểm tra cardinality với **mọi loại hàng của bảng ngoài**.

## 6. Scalar subquery trả nhiều hàng: lỗi hay kết quả đầu tiên?

Câu lệnh sau trên PostgreSQL thường báo lỗi:

```sql
-- PostgreSQL: lỗi vì subquery dùng làm scalar trả 3 hàng.
SELECT (
    SELECT amount
    FROM demo_orders
    WHERE customer_id = 1
) AS ambiguous_amount;
```

Thông điệp PostgreSQL thường là:

```text
more than one row returned by a subquery used as an expression
```

Một số DBMS khác như MySQL, SQL Server và Oracle cũng báo lỗi tương ứng trong tình huống scalar subquery trả nhiều hàng.

**Ngoại lệ cần biết:** SQLite thường dùng **hàng đầu tiên** của scalar subquery khi có nhiều hàng. Vì vậy cùng kiểu câu SQL có thể không phát sinh lỗi trên SQLite nhưng **vẫn không mô tả một lựa chọn dữ liệu xác định** nếu thiếu quy tắc sắp xếp. Không nên dựa vào hành vi này để viết mã có tính tương thích giữa DBMS.

### 6.1. Một hàng khác một giá trị phân biệt

Xét hai đơn của Bình:

```sql
SELECT amount
FROM demo_orders
WHERE customer_id = 2;
```

Kết quả:

```text
800
800
```

Có **hai hàng** nhưng chỉ **một giá trị phân biệt**. Scalar subquery trong các DBMS yêu cầu không quá một hàng vẫn coi đây là **nhiều hàng** và báo lỗi.

Không thể nói “hai hàng bằng nhau nên dùng làm scalar vẫn được”.

### 6.2. DISTINCT có thể giảm số hàng, nhưng đổi bài toán

```sql
SELECT (
    SELECT DISTINCT amount
    FROM demo_orders
    WHERE customer_id = 2
) AS one_distinct_amount;
-- 800 trên PostgreSQL: subquery sau DISTINCT chỉ còn 1 hàng.
```

Đối với Bình, `DISTINCT` đã gộp hai giá trị `800` thành một giá trị. Nhưng với An:

```sql
SELECT DISTINCT amount
FROM demo_orders
WHERE customer_id = 1;
-- 500 và 200: vẫn 2 hàng.
```

Vì vậy `DISTINCT` **không bảo đảm mọi truy vấn con thành scalar**. Quan trọng hơn, nó đổi yêu cầu từ “lấy một hàng” thành “lấy một giá trị phân biệt”. Chỉ dùng nếu ý nghĩa nghiệp vụ thực sự là vậy.

## 7. Chọn một hàng có chủ đích: ORDER BY và LIMIT

Nếu nghiệp vụ muốn lấy **đơn có mã lớn nhất** của từng khách, phải nêu tiêu chí và giới hạn một hàng:

```sql
-- PostgreSQL/MySQL/SQLite
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.amount
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.order_id DESC
        LIMIT 1
    ) AS amount_of_highest_order_id
FROM demo_customers AS c
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | amount_of_highest_order_id |
| ---: | --- | ---: |
| 1 | An | 200 |
| 2 | Bình | 800 |
| 3 | Chi | 300 |
| 4 | Dung | `NULL` |

Vì `order_id` là khóa chính, `ORDER BY order_id DESC` xác định rõ đơn có mã cao nhất trong mỗi nhóm.

### 7.1. LIMIT 1 không có ORDER BY là không đủ

```sql
SELECT (
    SELECT amount
    FROM demo_orders
    WHERE customer_id = 1
    LIMIT 1
);
```

Câu lệnh chọn tối đa một hàng, tránh lỗi nhiều hàng, nhưng **không chỉ rõ hàng nào**. Nếu An có tiền `500`, `200` và `200`, kết quả có thể là `500` hoặc `200` tùy kế hoạch thực thi và thứ tự hàng được đọc.

`LIMIT 1` giải quyết yêu cầu **số hàng**, còn `ORDER BY` giải quyết yêu cầu **hàng nào**.

### 7.2. Dùng hàm tổng hợp nếu muốn một đại lượng tổng hợp

Nếu mục tiêu là **tiền đơn lớn nhất**, không nhất thiết phải chọn một đơn cụ thể:

```sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.amount)
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS max_order_amount
FROM demo_customers AS c
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | max_order_amount |
| ---: | ---: |
| 1 | 500 |
| 2 | 800 |
| 3 | 300 |
| 4 | `NULL` |

`MAX` không có `GROUP BY` trả **một hàng kết quả tổng hợp** cho mỗi khách, kể cả khi không có đơn; giá trị trong hàng đó là `NULL` nếu không có đầu vào thích hợp.

Tuy nhiên, `MAX(amount)` chỉ trả **giá trị tiền lớn nhất**, không xác định mã đơn khi có nhiều đơn cùng số tiền lớn nhất. Nếu cần mã đơn, dùng sắp xếp có khóa phụ và chọn hàng, hoặc hàm cửa sổ.

### 7.3. Phương ngữ chọn top 1

| Hệ quản trị | Mẫu thường dùng |
| --- | --- |
| PostgreSQL, MySQL, SQLite | `ORDER BY ... LIMIT 1` |
| SQL Server | `SELECT TOP (1) ... ORDER BY ...` |
| Oracle 12c+ | `ORDER BY ... FETCH FIRST 1 ROW ONLY` |

Cú pháp không giống nhau nhưng yêu cầu kiểm chứng vẫn là: **đúng một hàng được chọn khi có nhiều hàng khớp, và không có hàng nếu không tìm được bản ghi**.

## 8. EXISTS: chỉ quan tâm có hàng hay không

`EXISTS (subquery)` trả:

- `TRUE` khi truy vấn con có **ít nhất một hàng**.
- `FALSE` khi truy vấn con **không có hàng nào**.

Bản thân kết quả `EXISTS` không có trạng thái `UNKNOWN`.

Ví dụ tìm khách hàng đã có đơn:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 3 | Chi |

Dung không xuất hiện vì truy vấn con tương quan với `customer_id = 4` không trả hàng nào.

### 8.1. Bản sao không khiến EXISTS nhân hàng

Với An, truy vấn con có **ba đơn**, nhưng `EXISTS` chỉ trả một kết quả Boolean `TRUE`. Khách hàng An xuất hiện **một lần** vì `EXISTS` hoạt động như một điều kiện lọc, không nối cả ba hàng con vào kết quả ngoài.

Tương tự, Bình có hai đơn nhưng chỉ được giữ một lần.

### 8.2. SELECT 1 và SELECT NULL có khác nhau trong EXISTS không?

`EXISTS` chỉ kiểm tra **sự tồn tại của hàng**, không kiểm tra nội dung cột được chọn.

```sql
SELECT EXISTS (
    SELECT NULL
) AS has_row;
-- PostgreSQL: TRUE, vì SELECT NULL tạo một hàng.
```

Ngược lại:

```sql
SELECT EXISTS (
    SELECT NULL
    WHERE 1 = 0
) AS has_row;
-- FALSE, vì không có hàng nào.
```

Vì vậy:

```sql
EXISTS (SELECT 1 FROM demo_orders WHERE ...)
```

và:

```sql
EXISTS (SELECT NULL FROM demo_orders WHERE ...)
```

có cùng ý nghĩa về **có hàng hay không** với cùng `FROM` và `WHERE`.

### 8.3. DISTINCT thường không cần thiết trong EXISTS

```sql
WHERE EXISTS (
    SELECT DISTINCT o.customer_id
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
```

Nếu mục tiêu chỉ là tồn tại ít nhất một hàng, việc dùng `DISTINCT` bên trong không thay đổi kết quả `TRUE`/`FALSE`. Dạng dễ đọc hơn là:

```sql
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
```

Tương tự, `ORDER BY` thường không cần thiết để xác định sự tồn tại, trừ khi có cấu trúc đi kèm thật sự thay đổi số hàng trả về.

## 9. NOT EXISTS: kiểm chứng trường hợp không có hàng

`NOT EXISTS` trả `TRUE` khi **truy vấn con không có hàng khớp**.

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM demo_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name |
| ---: | --- |
| 4 | Dung |

Bản sao ở bảng đơn **không ảnh hưởng** đến kết quả này: An có một, ba hay một trăm đơn thì `NOT EXISTS` vẫn là `FALSE` với An.

### 9.1. NULL trong bảng con có làm “nhiễm độc” NOT EXISTS không?

Bảng `demo_orders` có hàng `order_id = 107` với `customer_id = NULL`. Nhưng điều kiện tương quan:

```sql
o.customer_id = c.customer_id
```

không `TRUE` đối với hàng `NULL` đó ở bất kỳ khách hàng có mã xác định nào. Hàng ấy không tạo ra kết quả khớp; Dung vẫn được phát hiện là khách chưa có đơn.

Đó là khác biệt cốt lõi với một số cách dùng `NOT IN` khi tập bên phải có `NULL`.

### 9.2. EXISTS không nhất thiết nhanh hơn JOIN trong mọi trường hợp

Một DBMS có thể tối ưu `EXISTS` dưới dạng *semi join* và `NOT EXISTS` dưới dạng *anti join*. Nhưng kế hoạch thực tế phụ thuộc chỉ mục, thống kê và các điều kiện khác.

Chọn `EXISTS`/`NOT EXISTS` khi bài toán là **có hay không có bản ghi liên quan** vì ngữ nghĩa rõ ràng; sau đó mới đo hiệu năng nếu cần.

## 10. IN với đầu vào rỗng, nhiều hàng và giá trị trùng

`x IN (subquery)` kiểm tra liệu `x` có bằng **ít nhất một giá trị** được truy vấn con trả về hay không, theo logic ba giá trị của SQL.

Ví dụ:

```sql
SELECT c.customer_id, c.customer_name
FROM demo_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM demo_orders AS o
)
ORDER BY c.customer_id;
```

Kết quả: **An, Bình, Chi**.

Truy vấn con có:

```text
1, 1, 1, 2, 2, 3, NULL
```

Nhưng `IN` không biến An thành ba hàng hoặc Bình thành hai hàng. Một hàng khách hàng ngoài chỉ được giữ nếu điều kiện `IN` của hàng đó cho `TRUE`.

### 10.1. Bản sao không thay đổi kết quả IN

So sánh:

```sql
WHERE c.customer_id IN (
    SELECT customer_id FROM demo_orders
)
```

và:

```sql
WHERE c.customer_id IN (
    SELECT DISTINCT customer_id FROM demo_orders
)
```

Trong ví dụ này, hai câu chọn cùng ba khách. `DISTINCT` chỉ làm tập giá trị truy vấn con ngắn hơn về hình thức; các giá trị trùng không đổi tính đúng/sai của `IN`.

Không nên mặc định thêm `DISTINCT` khiến truy vấn nhanh hơn. Bộ tối ưu có thể tự xử lý cách thực thi phép kiểm tra thuộc tập.

### 10.2. Đầu vào rỗng khiến IN trả FALSE

```sql
SELECT
    1 IN (
        SELECT customer_id
        FROM demo_orders
        WHERE 1 = 0
    ) AS in_empty;
-- FALSE.
```

Không có giá trị nào trong tập bên phải để so khớp, nên kết quả là `FALSE`.

Ngay cả khi giá trị bên trái là `NULL`, nếu tập bên phải **thực sự rỗng**:

```sql
-- PostgreSQL
SELECT
    NULL::integer IN (
        SELECT customer_id
        FROM demo_orders
        WHERE 1 = 0
    ) AS null_in_empty;
-- FALSE.
```

**Không nhầm truy vấn con rỗng với truy vấn con chứa một hàng `NULL`.** Chúng có kết quả khác nhau trong nhiều phép kiểm tra.

### 10.3. IN với tập chứa NULL

```sql
SELECT
    2 IN (1, NULL) AS a,
    1 IN (1, NULL) AS b;
```

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `2 IN (1, NULL)` | `UNKNOWN` (hiển thị `NULL`) |
| `1 IN (1, NULL)` | `TRUE` |

Lý do:

```text
2 IN (1, NULL)
⇔ (2 = 1) OR (2 = NULL)
⇔ FALSE OR UNKNOWN
⇔ UNKNOWN
```

Khi có phần tử chắc chắn bằng `x`, `IN` vẫn trả `TRUE`. Nếu không có phần tử bằng `x` nhưng có so sánh với `NULL`, kết quả có thể là `UNKNOWN`.

Trong `WHERE`, chỉ các hàng có điều kiện `TRUE` được giữ; cả `FALSE` lẫn `UNKNOWN` đều bị loại.

## 11. NOT IN: trường hợp NULL nguy hiểm hơn bản sao

`NOT IN` có thể được hiểu như phủ định của phép kiểm tra thuộc tập:

```sql
x NOT IN (a, b, c)
```

tương đương về ngữ nghĩa với:

```sql
x <> a AND x <> b AND x <> c
```

Một `NULL` trong danh sách vô hướng có thể khiến toàn biểu thức thành `UNKNOWN` khi không có giá trị xác định nào khớp.

### 11.1. Truy vấn tưởng đúng nhưng trả rỗng

Giả sử muốn tìm khách hàng chưa có đơn:

```sql
SELECT c.customer_id, c.customer_name
FROM demo_customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM demo_orders AS o
)
ORDER BY c.customer_id;
```

**Kết quả: không có hàng nào.**

Trong khi Dung rõ ràng không có đơn. Nguyên nhân là truy vấn con trả `1,1,1,2,2,3,NULL`.

Với Dung:

```text
4 NOT IN (1, 1, 1, 2, 2, 3, NULL)
⇔ (4<>1) AND ... AND (4<>3) AND (4<>NULL)
⇔ TRUE AND ... AND TRUE AND UNKNOWN
⇔ UNKNOWN
```

`WHERE` không giữ hàng có điều kiện `UNKNOWN`. Những khách có mã đã xuất hiện trong tập lại cho `NOT IN = FALSE`. Kết quả chung là rỗng.

### 11.2. Thêm DISTINCT không giải quyết bẫy NULL

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE c.customer_id NOT IN (
    SELECT DISTINCT o.customer_id
    FROM demo_orders AS o
);
```

Truy vấn con trở thành `1,2,3,NULL`. `NULL` **vẫn tồn tại**, nên Dung vẫn bị loại.

**Loại bản sao và xử lý NULL là hai bài toán khác nhau.**

### 11.3. Cách 1: lọc NULL khi phù hợp nghiệp vụ

```sql
SELECT c.customer_id, c.customer_name
FROM demo_customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM demo_orders AS o
    WHERE o.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
```

Kết quả: Dung (`4`).

Cách này phù hợp ở đây vì cột bên trái `demo_customers.customer_id` là khóa chính, **không thể `NULL`**, và bản ghi đơn không xác định khách được quyết định là không tham gia tập kiểm tra mã khách.

### 11.4. Cách 2: dùng NOT EXISTS

```sql
SELECT c.customer_id, c.customer_name
FROM demo_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả cũng là Dung (`4`), không bị ảnh hưởng bởi hàng đơn có mã khách `NULL`.

Khi mục đích là **không có bản ghi liên quan**, `NOT EXISTS` thường biểu diễn rõ ý nghĩa hơn. Tuy nhiên, nếu cột trái cũng có thể `NULL`, cần quyết định xem hàng thiếu khóa có nên được xem là “không có bản ghi khớp” hay không.

### 11.5. Tập rỗng: NOT IN là TRUE

```sql
SELECT
    4 NOT IN (
        SELECT customer_id
        FROM demo_orders
        WHERE 1 = 0
    ) AS not_in_empty;
-- TRUE.
```

Điều này cũng đúng khi bên trái là `NULL` và tập bên phải rỗng:

```sql
-- PostgreSQL
SELECT
    NULL::integer NOT IN (
        SELECT customer_id
        FROM demo_orders
        WHERE 1 = 0
    ) AS null_not_in_empty;
-- TRUE.
```

**Bảng cần nhớ:**

| Tập bên phải | `4 IN (...)` | `4 NOT IN (...)` |
| --- | --- | --- |
| Không có hàng | `FALSE` | `TRUE` |
| Một hàng `NULL` | `UNKNOWN` | `UNKNOWN` |
| `1,2,3` | `FALSE` | `TRUE` |
| `1,2,3,NULL` | `UNKNOWN` | `UNKNOWN` |
| `4,4,NULL` | `TRUE` | `FALSE` |

Số lần lặp của `4` không đổi kết quả; **sự xuất hiện của `NULL`** là điểm cần phân biệt.

## 12. ANY, SOME và ALL khi truy vấn con rỗng

Ngoài `IN`, SQL còn có những biểu thức so sánh với tập:

```sql
x > ANY (SELECT ...)
x >= ALL (SELECT ...)
x = SOME (SELECT ...)
```

Ở các DBMS hỗ trợ dạng này:

- `ANY` hoặc `SOME` nghĩa là **tồn tại ít nhất một phép so sánh đúng**.
- `ALL` nghĩa là **mọi phép so sánh đều đúng**.

Với **tập rỗng**:

- `x op ANY (empty)` → `FALSE`.
- `x op ALL (empty)` → `TRUE`.

Ví dụ PostgreSQL:

```sql
SELECT
    500 > ANY (
        SELECT amount FROM demo_orders WHERE 1 = 0
    ) AS any_empty,
    500 > ALL (
        SELECT amount FROM demo_orders WHERE 1 = 0
    ) AS all_empty;
-- any_empty = FALSE
-- all_empty = TRUE
```

### 12.1. Vì sao ALL trên tập rỗng là TRUE?

Không có phần tử nào làm điều kiện `x > value` sai. Về mặt lượng từ logic, mệnh đề “đúng với mọi phần tử của tập rỗng” được xem là đúng (*vacuous truth*).

Điều đó rất dễ gây lỗi nếu ứng dụng muốn hỏi:

> “Giá trị 500 có lớn hơn mọi đơn của khách hàng này, **và khách đó phải có ít nhất một đơn** hay không?”

`500 > ALL (subquery)` một mình sẽ trả `TRUE` khi khách **chưa có đơn**. Nếu nghiệp vụ yêu cầu có ít nhất một đơn, thêm điều kiện tồn tại:

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
AND 500 > ALL (
    SELECT o.amount
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả của dữ liệu mẫu là Chi (`3`), vì chỉ Chi có đơn và mọi số tiền đơn đều thấp hơn 500. An có một đơn bằng 500, Bình có hai đơn bằng 800, Dung không có đơn.

### 12.2. ANY và ALL với giá trị trùng

Ví dụ:

```sql
SELECT
    800 = ANY (
        SELECT amount
        FROM demo_orders
        WHERE customer_id = 2
    ) AS has_amount_800,
    800 = ALL (
        SELECT amount
        FROM demo_orders
        WHERE customer_id = 2
    ) AS every_amount_800;
```

Bình có hai đơn cùng `amount = 800`, nên cả hai biểu thức trả `TRUE`.

Nhân bản một giá trị đã có **không đổi kết quả logic** của `ANY`/`ALL` nếu các giá trị và trạng thái `NULL` của tập không đổi. Nhưng nó vẫn ảnh hưởng các phép đếm, tổng và phép nối thông thường.

### 12.3. NULL trong ANY/ALL

Với tập không rỗng, phép so sánh với `NULL` có thể trả `UNKNOWN`:

- `ANY`: nếu có phép so sánh `TRUE`, kết quả `TRUE`; nếu không có `TRUE` nhưng có `UNKNOWN`, kết quả có thể `UNKNOWN`.
- `ALL`: nếu có phép so sánh `FALSE`, kết quả `FALSE`; nếu không có `FALSE` nhưng có `UNKNOWN`, kết quả có thể `UNKNOWN`.

Ví dụ:

```sql
SELECT
    5 > ANY (
        SELECT v
        FROM (VALUES (NULL::integer)) AS t(v)
    ) AS any_one_null,
    5 > ALL (
        SELECT v
        FROM (VALUES (NULL::integer)) AS t(v)
    ) AS all_one_null;
-- Cả hai biểu thức đều UNKNOWN/NULL.
```

Do đó trong bài kiểm chứng, cần tách **tập rỗng** khỏi **tập có một hàng `NULL`**.

## 13. Bản sao làm thay đổi JOIN, nhưng không nhân kết quả EXISTS

Khi muốn tìm những khách đã có đơn, cả hai câu sau có thể trông tương tự.

**Cách A — EXISTS:**

```sql
SELECT c.customer_id, c.customer_name
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả: **3 hàng**, An/Bình/Chi mỗi người một lần.

**Cách B — INNER JOIN:**

```sql
SELECT c.customer_id, c.customer_name
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả:

| customer_id | customer_name |
| ---: | --- |
| 1 | An |
| 1 | An |
| 1 | An |
| 2 | Bình |
| 2 | Bình |
| 3 | Chi |

**6 hàng**: An ba lần, Bình hai lần, Chi một lần.

Đây không phải lỗi của `JOIN`. Nó thực hiện đúng phép nối: **mỗi cặp hàng khớp tạo một hàng kết quả**. Lỗi chỉ xảy ra khi người viết dùng `JOIN` để biểu diễn yêu cầu “chỉ cần tồn tại một hàng” mà không xét tính nhân bản.

### 13.1. Thêm DISTINCT vào JOIN có thể cho cùng danh sách khách

```sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Trong ví dụ, kết quả trở về ba khách như `EXISTS`.

Nhưng việc thêm `DISTINCT` không làm hai cách **luôn tương đương** trong mọi truy vấn phức tạp. Nếu `SELECT` có thêm `o.order_id`, mỗi đơn lại khác nhau, nên `DISTINCT` không gộp thành một hàng mỗi khách.

Cũng không nên dùng `DISTINCT` để che vấn đề nhân hàng trong một phép tổng hợp trước khi kiểm tra cấp độ dữ liệu.

### 13.2. LEFT JOIN giữ khách không có đơn nhưng vẫn nhân khách có nhiều đơn

```sql
SELECT c.customer_id, o.order_id
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Kết quả gồm:

- An: ba hàng.
- Bình: hai hàng.
- Chi: một hàng.
- Dung: một hàng với `order_id = NULL`.

Tổng cộng **7 hàng**. Hàng đơn `107` có `customer_id = NULL` không khớp với khóa khách hàng nào, nên không góp một hàng `JOIN` trong kết quả này.

### 13.3. COUNT(*) và COUNT(o.order_id) sau LEFT JOIN

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | joined_rows | order_count |
| ---: | ---: | ---: |
| 1 | 3 | 3 |
| 2 | 2 | 2 |
| 3 | 1 | 1 |
| 4 | 1 | 0 |

Với Dung, `LEFT JOIN` tạo **một hàng giữ chỗ** có phía đơn hàng `NULL`. `COUNT(*)` đếm hàng giữ chỗ đó nên bằng 1; `COUNT(o.order_id)` chỉ đếm khóa đơn không `NULL` nên bằng 0.

Đó là ví dụ cho thấy **số hàng kết quả nối** khác với **số bản ghi con thực sự tồn tại**.

## 14. Tổng hợp và bản sao: khi nào SUM bị sai?

Bảng `demo_orders` có hai đơn của Bình, mỗi đơn `800`. Tính tổng tiền đơn của Bình:

```sql
SELECT
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM demo_orders
WHERE customer_id = 2;
```

Kết quả:

| order_count | total_amount |
| ---: | ---: |
| 2 | 1600 |

Hai đơn khác `order_id` có cùng số tiền `800` nhưng đều là **giao dịch thực**; tổng chính xác phải tính cả hai.

### 14.1. SUM(DISTINCT amount) có thể là sai nghiệp vụ

```sql
SELECT
    SUM(DISTINCT amount) AS distinct_amount_sum
FROM demo_orders
WHERE customer_id = 2;
-- 800, không phải 1600.
```

`DISTINCT` loại giá trị `800` lặp lại, mặc dù đó là **hai đơn khác nhau**. `SUM(DISTINCT amount)` trả 800, nhưng tổng doanh thu thực là 1600.

Đây là lỗi điển hình khi dùng `DISTINCT` như một “miếng vá” cho phép nối nhân hàng. Trước tiên phải xác định **khóa định danh bản ghi**, rồi quyết định số liệu cần tổng hợp ở cấp nào.

### 14.2. JOIN nhiều bảng con có thể nhân chéo

Giả sử một khách có:

- Ba đơn hàng.
- Hai địa chỉ giao hàng.

Nối `customers` với cả `orders` và `addresses` theo khóa khách có thể tạo **3 × 2 = 6 hàng** cho khách đó. Nếu cộng `orders.amount` trên tập kết quả nối, mỗi đơn có thể bị tính hai lần.

Cách an toàn thường là **tổng hợp từng bảng con về đúng một hàng mỗi khóa cha trước**, rồi nối các kết quả tổng hợp:

```sql
WITH order_totals AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount
    FROM demo_orders
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(t.order_count, 0) AS order_count,
    COALESCE(t.total_amount, 0) AS total_amount
FROM demo_customers AS c
LEFT JOIN order_totals AS t
    ON t.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | order_count | total_amount |
| ---: | ---: | ---: |
| 1 | 3 | 900 |
| 2 | 2 | 1600 |
| 3 | 1 | 300 |
| 4 | 0 | 0 |

CTE `order_totals` tạo tối đa một hàng cho mỗi `customer_id` có dữ liệu, giúp phép nối với khách không nhân hàng theo số đơn.

### 14.3. Đếm đơn khác đếm giá trị tiền

```sql
SELECT
    customer_id,
    COUNT(*) AS number_of_orders,
    COUNT(DISTINCT amount) AS number_of_distinct_amounts
FROM demo_orders
WHERE customer_id IS NOT NULL
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả:

| customer_id | number_of_orders | number_of_distinct_amounts |
| ---: | ---: | ---: |
| 1 | 3 | 2 |
| 2 | 2 | 1 |
| 3 | 1 | 1 |

Hai chỉ số trả lời **hai câu hỏi khác nhau**. Khi kiểm chứng truy vấn con có bản sao, cần nêu rõ “trùng ở cột nào” thay vì chỉ nói chung chung rằng dữ liệu bị lặp.

## 15. Aggregate subquery với đầu vào rỗng

Truy vấn tổng hợp không `GROUP BY` là một trường hợp quan trọng: nó thường **trả một hàng** ngay cả khi bộ lọc không tìm thấy dòng nguồn.

Ví dụ:

```sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT SUM(o.amount)
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS total_amount
FROM demo_customers AS c
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | order_count | total_amount |
| ---: | ---: | ---: |
| 1 | 3 | 900 |
| 2 | 2 | 1600 |
| 3 | 1 | 300 |
| 4 | 0 | `NULL` |

Với Dung:

- `COUNT(*)` trả giá trị **0**, bên trong một hàng kết quả aggregate.
- `SUM(amount)` trả **`NULL`**, cũng bên trong một hàng kết quả aggregate.

Câu `SUM` không tự biến thành số 0. Nếu yêu cầu hiển thị “khách chưa có đơn → tổng bằng 0”, phải diễn đạt rõ:

```sql
COALESCE((
    SELECT SUM(o.amount)
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
), 0) AS total_amount
```

### 15.1. Khi có GROUP BY, đầu vào rỗng có thể không tạo hàng

So sánh hai truy vấn con:

**A — Aggregate không GROUP BY:**

```sql
SELECT COUNT(*) AS count_value
FROM demo_orders
WHERE customer_id = 4;
-- Một hàng, count_value = 0.
```

**B — Aggregate có GROUP BY:**

```sql
SELECT customer_id, COUNT(*) AS count_value
FROM demo_orders
WHERE customer_id = 4
GROUP BY customer_id;
-- Không có hàng.
```

Với một scalar subquery lấy `count_value` từ B, kết quả biểu thức sẽ là `NULL` do không có hàng, **không phải `0`**.

Chỉ khác một `GROUP BY` nhưng **cardinality** và kết quả khi rỗng đã thay đổi.

### 15.2. EXISTS trên aggregate không GROUP BY có thể luôn TRUE

Xem:

```sql
SELECT EXISTS (
    SELECT COUNT(*)
    FROM demo_orders
    WHERE customer_id = 4
) AS has_aggregate_row;
-- TRUE.
```

Điều này dễ gây bất ngờ: khách 4 không có đơn, nhưng truy vấn con `SELECT COUNT(*)` **vẫn trả một hàng** có giá trị 0. `EXISTS` hỏi có hàng không nên trả `TRUE`.

**Sai về ý định:**

```sql
WHERE EXISTS (
    SELECT COUNT(*)
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
```

Dạng này có thể cho `TRUE` với **mọi khách hàng** vì aggregate không `GROUP BY` luôn cung cấp một hàng.

**Đúng khi muốn kiểm tra có đơn:**

```sql
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
```

Hoặc nếu mục tiêu thật sự dựa trên một giá trị đếm, so sánh trực tiếp với 0:

```sql
WHERE (
    SELECT COUNT(*)
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
) > 0
```

Dạng `EXISTS (SELECT 1 ... )` thường thể hiện ý định tồn tại đơn giản hơn.

## 16. Truy vấn con tương quan: thử từng loại hàng bên ngoài

**Correlated subquery** là truy vấn con tham chiếu cột từ truy vấn ngoài:

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Điều kiện `o.customer_id = c.customer_id` khiến tập hàng bên trong phụ thuộc vào khách hiện tại.

Một truy vấn con có thể:

- Rỗng với Dung.
- Trả một hàng với Chi.
- Trả hai hàng với Bình.
- Trả ba hàng với An.

Vì vậy, câu hỏi “truy vấn con này trả mấy hàng?” **không có một con số cố định** cho toàn bộ câu lệnh, nếu truy vấn con có tương quan.

### 16.1. Bảng dự đoán trước khi chạy

| Khách ngoài | Số hàng con | `EXISTS` | `NOT EXISTS` | `COUNT(*)` trong scalar aggregate |
| --- | ---: | --- | --- | ---: |
| An (`1`) | 3 | `TRUE` | `FALSE` | 3 |
| Bình (`2`) | 2 | `TRUE` | `FALSE` | 2 |
| Chi (`3`) | 1 | `TRUE` | `FALSE` | 1 |
| Dung (`4`) | 0 | `FALSE` | `TRUE` | 0 |

Bảng dự đoán này giúp kiểm tra ngữ nghĩa của từng phép toán mà không phải dựa vào việc “chạy thử một khách thấy đúng”.

### 16.2. Bẫy so sánh cột không có alias

Ví dụ câu lệnh:

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE customer_id = customer_id
);
```

Trong truy vấn con, tên `customer_id` không được chỉ định rõ alias và có thể được phân giải thành cột của **bảng bên trong**, dẫn đến phép so sánh một cột với **chính nó**, không phải với mã khách hiện tại. Nếu bên trong có ít nhất một mã khách khác `NULL`, truy vấn `EXISTS` có thể thành `TRUE` với mọi khách, kể cả Dung.

Cách viết rõ ý định:

```sql
WHERE o.customer_id = c.customer_id
```

**Luôn dùng alias cho cột có khả năng xuất hiện ở cả hai cấp**, nhất là trong truy vấn tương quan.

### 16.3. Truy vấn con không nhất thiết chạy vật lý từng lần

Ta thường giải thích rằng DBMS xem từng khách rồi kiểm tra truy vấn con. Đây là **mô hình ngữ nghĩa**; bộ tối ưu có thể biến đổi `EXISTS` thành semi join, dùng chỉ mục hoặc chiến lược khác.

Khi kiểm chứng **đúng/sai của kết quả**, dựa vào logic SQL; khi phân tích **hiệu năng**, dựa vào execution plan thay vì giả định có N lượt thực thi độc lập.

## 17. Thử dữ liệu rỗng mà không xóa bảng thật

Không cần xóa dữ liệu hoặc đổi trạng thái production để tạo trường hợp subquery rỗng.

Ví dụ trên PostgreSQL:

```sql
SELECT
    1 IN (
        SELECT customer_id
        FROM demo_orders
        WHERE 1 = 0
    ) AS in_empty,
    1 NOT IN (
        SELECT customer_id
        FROM demo_orders
        WHERE 1 = 0
    ) AS not_in_empty,
    EXISTS (
        SELECT 1
        FROM demo_orders
        WHERE 1 = 0
    ) AS exists_empty;
```

Kết quả:

| in_empty | not_in_empty | exists_empty |
| --- | --- | --- |
| `FALSE` | `TRUE` | `FALSE` |

Điều kiện `WHERE 1 = 0` đảm bảo truy vấn con **không trả hàng nào**, bất kể dữ liệu thực trong bảng.

### 17.1. Dùng VALUES để tạo đầu vào trùng

Trên PostgreSQL, có thể tạo tập giá trị tạm:

```sql
WITH values_with_duplicates(value) AS (
    VALUES
        (1),
        (1),
        (2),
        (2),
        (2)
)
SELECT
    COUNT(*) AS rows_total,
    COUNT(DISTINCT value) AS distinct_values
FROM values_with_duplicates;
```

Kết quả:

| rows_total | distinct_values |
| ---: | ---: |
| 5 | 2 |

Tập này chỉ tồn tại trong ngữ cảnh câu lệnh; không ghi thêm hàng vào `demo_orders`.

### 17.2. Dùng VALUES để tạo một hàng NULL

```sql
WITH one_null(value) AS (
    VALUES (NULL::integer)
)
SELECT
    2 IN (
        SELECT value FROM one_null
    ) AS in_one_null,
    2 NOT IN (
        SELECT value FROM one_null
    ) AS not_in_one_null;
```

Kết quả: **`UNKNOWN`/`NULL` cho cả hai biểu thức**.

Truy vấn này giúp tách riêng trường hợp **có một hàng chứa NULL** khỏi **không có hàng**.

### 17.3. Đừng dùng IN () như một tập rỗng di động

`IN ()` không được nhiều DBMS chấp nhận; SQLite có những quy tắc mở rộng riêng nhưng không nên dựa vào đó để viết SQL đa hệ.

Khi ứng dụng tạo danh sách tham số rỗng, nó phải xác định ý nghĩa nghiệp vụ rồi xử lý trong trình tạo câu truy vấn, thay vì mặc định mọi DBMS nhận `IN ()`.

Ví dụ, nếu ý nghĩa là “không một giá trị nào được chọn”, điều kiện lọc bằng `IN` trên danh sách rỗng về logic là `FALSE`. Nhưng nếu “không chọn bộ lọc” nghĩa là “không áp dụng điều kiện”, lại phải bỏ điều kiện lọc thay vì trả không hàng. **Quyết định này ở tầng nghiệp vụ**, không do cú pháp SQL tự quyết định.

## 18. Ma trận kiểm chứng nhỏ cho từng toán tử

Cho một giá trị cố định `x = 2` và các tập bên phải:

- A: rỗng `{}`.
- B: `{2}`.
- C: `{2, 2}`.
- D: `{1, 3}`.
- E: `{1, NULL}`.
- F: `{2, NULL}`.
- G: `{NULL}`.

### 18.1. Kết quả dự đoán

| Tập bên phải | `2 IN (...)` | `2 NOT IN (...)` | `EXISTS(subquery)` | `NOT EXISTS(subquery)` |
| --- | --- | --- | --- | --- |
| A: không hàng | `FALSE` | `TRUE` | `FALSE` | `TRUE` |
| B: `2` | `TRUE` | `FALSE` | `TRUE` | `FALSE` |
| C: `2,2` | `TRUE` | `FALSE` | `TRUE` | `FALSE` |
| D: `1,3` | `FALSE` | `TRUE` | `TRUE` | `FALSE` |
| E: `1,NULL` | `UNKNOWN` | `UNKNOWN` | `TRUE` | `FALSE` |
| F: `2,NULL` | `TRUE` | `FALSE` | `TRUE` | `FALSE` |
| G: `NULL` | `UNKNOWN` | `UNKNOWN` | `TRUE` | `FALSE` |

Bảng giúp thấy ba nguyên tắc:

1. **Bản sao**: thay `{2}` bằng `{2,2}` không đổi `IN`, `NOT IN`, `EXISTS` hoặc `NOT EXISTS`.
2. **Tập rỗng**: `EXISTS` sai; `NOT EXISTS` đúng; `IN` sai; `NOT IN` đúng.
3. **Một hàng `NULL`**: `EXISTS` đúng vì có hàng, nhưng `IN`/`NOT IN` có thể cho `UNKNOWN`.

Đối với `EXISTS`, bảng giả định subquery trả đúng các hàng đã liệt kê. `EXISTS` không so sánh từng giá trị với số 2; nó chỉ kiểm tra có hàng.

### 18.2. Thử B và C bằng SQL

```sql
WITH one_value(value) AS (
    VALUES (2)
), duplicate_values(value) AS (
    VALUES (2), (2)
)
SELECT
    2 IN (
        SELECT value FROM one_value
    ) AS in_one,
    2 IN (
        SELECT value FROM duplicate_values
    ) AS in_duplicates,
    EXISTS (
        SELECT 1 FROM duplicate_values
    ) AS exists_duplicates;
```

Kết quả: cả ba biểu thức là `TRUE`.

### 18.3. Thử E bằng SQL

```sql
WITH values_with_null(value) AS (
    VALUES
        (1),
        (NULL::integer)
)
SELECT
    2 IN (
        SELECT value FROM values_with_null
    ) AS in_null,
    2 NOT IN (
        SELECT value FROM values_with_null
    ) AS not_in_null,
    EXISTS (
        SELECT 1 FROM values_with_null
    ) AS exists_null;
```

Kết quả:

| in_null | not_in_null | exists_null |
| --- | --- | --- |
| `NULL`/`UNKNOWN` | `NULL`/`UNKNOWN` | `TRUE` |

## 19. Khi nào nên dùng DISTINCT, GROUP BY, LIMIT hoặc EXISTS?

Những công cụ này đôi khi đều có thể “giảm số hàng”, nhưng **không có cùng ý nghĩa**.

| Công cụ | Nó làm gì | Khi nào hợp lý |
| --- | --- | --- |
| `DISTINCT` | Loại các hàng trùng theo các biểu thức được chọn | Muốn tập các **giá trị hoặc bộ giá trị phân biệt** |
| `GROUP BY` | Gom hàng theo khóa nhóm; có thể tính aggregate | Muốn một hàng thống kê cho mỗi nhóm |
| `LIMIT 1`/`TOP (1)` | Chỉ giữ tối đa một hàng theo thứ tự nếu có `ORDER BY` | Muốn chọn **một bản ghi cụ thể** |
| `MAX`/`MIN` | Tính cực trị của một biểu thức | Muốn **giá trị lớn/nhỏ nhất**, không nhất thiết định danh hàng |
| `EXISTS` | Kiểm tra có hàng | Chỉ cần trả lời câu hỏi **có bản ghi liên quan hay không** |
| `NOT EXISTS` | Kiểm tra không có hàng | Tìm những hàng không có bản ghi liên quan |
| `IN` | Kiểm tra thuộc tập giá trị | So một giá trị với danh sách/truy vấn con |
| `JOIN` | Kết hợp từng cặp hàng phù hợp | Cần dữ liệu từ các hàng liên quan, chấp nhận khả năng nhân hàng |

### 19.1. Chọn theo mục đích, không theo lỗi đang gặp

Nếu scalar subquery báo lỗi nhiều hàng, đừng vội thêm `DISTINCT` hoặc `LIMIT 1` mà chưa biết yêu cầu:

- Cần **một đơn mới nhất**? Sắp theo ngày/mã và giới hạn 1.
- Cần **số tiền lớn nhất**? `MAX(amount)`.
- Cần **tổng tiền các đơn**? `SUM(amount)`.
- Cần **có đơn hay không**? `EXISTS`.
- Cần **tất cả đơn**? Dùng `JOIN` hoặc nguồn bảng để trả nhiều hàng có chủ đích.

Lỗi nhiều hàng đôi khi là dấu hiệu rằng **kiểu truy vấn con được chọn không phù hợp với bài toán**, không phải chỉ thiếu một từ khóa giới hạn.

## 20. Dùng CTE để tách kiểm chứng thành từng bước

Với truy vấn phức tạp, có thể dùng `WITH` để đặt tên tập con và quan sát số hàng trước khi dùng nó.

Ví dụ muốn tìm những khách có ít nhất một đơn `PAID`:

```sql
WITH paid_customer_ids AS (
    SELECT customer_id
    FROM demo_orders
    WHERE order_status = 'PAID'
)
SELECT
    c.customer_id,
    c.customer_name
FROM demo_customers AS c
WHERE c.customer_id IN (
    SELECT customer_id FROM paid_customer_ids
)
ORDER BY c.customer_id;
```

Kết quả: An và Bình.

CTE `paid_customer_ids` trả:

```text
1
2
2
```

Với `IN`, việc Bình lặp hai lần **không làm Bình xuất hiện hai lần**.

### 20.1. Kiểm chứng số hàng của CTE

```sql
WITH paid_customer_ids AS (
    SELECT customer_id
    FROM demo_orders
    WHERE order_status = 'PAID'
)
SELECT
    COUNT(*) AS rows_total,
    COUNT(DISTINCT customer_id) AS customers_total
FROM paid_customer_ids;
```

Kết quả:

| rows_total | customers_total |
| ---: | ---: |
| 3 | 2 |

Đếm riêng như vậy cho thấy tập con có ba hàng nhưng chỉ hai khách hàng khác nhau.

### 20.2. CTE không tự loại bản sao

```sql
WITH paid_customer_ids AS (
    SELECT customer_id
    FROM demo_orders
    WHERE order_status = 'PAID'
)
SELECT customer_id
FROM paid_customer_ids
ORDER BY customer_id;
```

Kết quả vẫn là `1, 2, 2`. `WITH` chỉ tạo tên cho một truy vấn con trong câu lệnh; nó **không** tự biến kết quả thành tập giá trị duy nhất.

Muốn loại trùng:

```sql
SELECT DISTINCT customer_id
FROM paid_customer_ids;
```

và chỉ nên làm vậy khi nghiệp vụ yêu cầu những mã khách phân biệt.

## 21. Truy vấn con ở FROM và hiện tượng nhân hàng

Một truy vấn con trong `FROM` có thể trả nhiều hàng và nhiều cột, được xem như một **nguồn dữ liệu quan hệ**.

```sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.amount
FROM demo_customers AS c
JOIN (
    SELECT customer_id, order_id, amount
    FROM demo_orders
    WHERE order_status = 'PAID'
) AS recent
    ON recent.customer_id = c.customer_id
ORDER BY c.customer_id, recent.order_id;
```

Kết quả:

| customer_id | order_id | amount |
| ---: | ---: | ---: |
| 1 | 101 | 500 |
| 2 | 104 | 800 |
| 2 | 105 | 800 |

Bình xuất hiện hai lần vì bên phải có hai đơn `PAID`. Đặt một derived table trong `FROM` **không làm phép nối tự chọn một hàng mỗi khách**.

### 21.1. Muốn một hàng thống kê cho mỗi khách

Có thể tổng hợp trước:

```sql
SELECT
    c.customer_id,
    paid.paid_count,
    paid.paid_total
FROM demo_customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS paid_count,
        SUM(amount) AS paid_total
    FROM demo_orders
    WHERE order_status = 'PAID'
    GROUP BY customer_id
) AS paid
    ON paid.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | paid_count | paid_total |
| ---: | ---: | ---: |
| 1 | 1 | 500 |
| 2 | 2 | 1600 |
| 3 | `NULL` | `NULL` |
| 4 | `NULL` | `NULL` |

Ở đây `paid` trả tối đa một hàng cho mỗi mã khách có đơn `PAID`. Vì `LEFT JOIN` không tìm thấy nhóm `PAID` cho Chi/Dung, hai cột bên phải là `NULL`. Nếu giao diện muốn hiển thị 0, có thể dùng `COALESCE(paid.paid_count,0)` và `COALESCE(paid.paid_total,0)` tùy quy tắc nghiệp vụ.

### 21.2. Derived table khác LATERAL

Nếu derived table trong `FROM` cần tham chiếu cột bảng đứng trước, PostgreSQL sử dụng `LATERAL`:

```sql
SELECT
    c.customer_id,
    latest.order_id
FROM demo_customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
```

Truy vấn này chọn tối đa một đơn **theo từng khách hàng**. Dung được giữ với `order_id = NULL`. Nó là một ví dụ về cách biến **0/nhiều hàng** thành **0 hoặc 1 hàng** theo một quy tắc có chủ đích.

SQL Server dùng `OUTER APPLY` cho ý định tương tự; các phương ngữ khác có cú pháp và giới hạn khác nhau.

## 22. Khác biệt giữa SQL standard và các DBMS

Những ngữ nghĩa chính của `EXISTS`, `IN`, `NOT IN` và phép tổng hợp được chuẩn SQL định nghĩa, nhưng chi tiết cú pháp và một số tình huống scalar subquery cần chú ý.

| Hệ quản trị | Scalar subquery trả nhiều hàng | Cách chọn top 1 phổ biến | Lưu ý |
| --- | --- | --- | --- |
| PostgreSQL | Báo lỗi ở ngữ cảnh yêu cầu một giá trị đơn | `ORDER BY ... LIMIT 1` hoặc `FETCH FIRST 1 ROW ONLY` | Hỗ trợ `VALUES`, CTE, `LATERAL`, `ANY/ALL` |
| MySQL | Thường báo lỗi “Subquery returns more than 1 row” | `ORDER BY ... LIMIT 1` | Cẩn thận `NOT IN` có `NULL`; hỗ trợ khác biệt theo phiên bản |
| SQL Server | Báo lỗi scalar subquery trả nhiều giá trị | `SELECT TOP (1) ... ORDER BY ...` | Dùng `APPLY` cho derived source tương quan |
| Oracle Database | Báo lỗi khi single-row subquery trả nhiều hàng | `FETCH FIRST 1 ROW ONLY` trên 12c+ | Tên lỗi quen thuộc là `ORA-01427`; Oracle cũ có cơ chế `ROWNUM` |
| SQLite | Scalar subquery thường lấy hàng đầu nếu có nhiều hàng | `ORDER BY ... LIMIT 1` | Không dựa vào hành vi chọn hàng đầu để tạo SQL di động |

### 22.1. Cẩn thận với cách diễn đạt “SQL trả lỗi”

Nên phân biệt:

- **Theo ngữ nghĩa được nhiều DBMS áp dụng**, scalar subquery ở vị trí một giá trị yêu cầu không quá một hàng.
- **SQLite** là một ngoại lệ thực tế đáng biết: nó không nhất thiết báo lỗi khi scalar subquery có nhiều hàng.

Vì vậy, khi kiểm chứng tính đúng trên nhiều hệ quản trị, không chỉ chạy câu SQL một lần trên SQLite rồi kết luận query portable.

### 22.2. Kiểu và NULL của từng DBMS

Ngay cả khi một câu SQL hợp lệ, cách suy luận kiểu của `NULL`, xử lý kiểu Boolean, chuỗi và biểu thức `VALUES` có thể khác. Những đoạn SQL có `NULL::integer` trong bài là **cú pháp ép kiểu PostgreSQL**. Với hệ khác, dùng `CAST(NULL AS INTEGER)` nếu được hỗ trợ theo kiểu phù hợp.

### 22.3. Phân biệt truy vấn lỗi và truy vấn không có hàng

Nếu subquery scalar trả nhiều hàng gây lỗi, kết quả **không phải** một bảng một hàng chứa `NULL`. Đó là lỗi thực thi. Không được xử lý nó như “không tìm thấy kết quả”.

Tương tự, một phép `NOT IN` khiến `WHERE` trả rỗng do `UNKNOWN` là **truy vấn thực thi thành công nhưng cho tập kết quả khác mong muốn** — loại lỗi logic, không phải lỗi cú pháp.

## 23. Thiết kế bộ dữ liệu kiểm chứng cho bài toán thực tế

Với một truy vấn con dùng trong ứng dụng, có thể lập các tình huống thử nghiệm như sau:

| Trường hợp | Dữ liệu cần dựng | Điều muốn phát hiện |
| --- | --- | --- |
| **0 hàng** | Khách hàng không có đơn | Scalar trả `NULL`, EXISTS sai, NOT EXISTS đúng, aggregate COUNT bằng 0 |
| **1 hàng** | Khách có đúng một đơn | Trường hợp cơ bản của scalar, IN, EXISTS |
| **2+ hàng khác nhau** | Khách có nhiều đơn khác số tiền | Scalar có bị lỗi hoặc chọn tùy tiện không |
| **2+ hàng giống giá trị chọn** | Hai đơn cùng số tiền | Có nhầm “một giá trị phân biệt” với “một hàng” không |
| **Có NULL trong subquery** | Một đơn chưa có mã khách | `NOT IN` có trả rỗng bất ngờ không |
| **Chỉ có một hàng NULL** | `VALUES (NULL)` | Phân biệt rỗng và một giá trị thiếu |
| **Giá trị trái NULL** | Đối tượng ngoài có khóa tùy chọn chưa xác định | `IN/NOT IN` và `NOT EXISTS` có ngữ nghĩa đúng nghiệp vụ không |
| **Đồng hạng khi chọn top 1** | Hai hàng có thời điểm/điểm số bằng nhau | Có khóa phụ để chọn ổn định không |
| **Nối với hai bảng một-nhiều** | Một cha có nhiều đơn và nhiều địa chỉ | Có nhân chéo, làm sai COUNT/SUM không |
| **Đầu vào thay đổi theo thời gian** | Chèn/xóa đơn giữa các lần chạy | Có yêu cầu snapshot/giao dịch nhất quán không |

### 23.1. Kiểm chứng cả số hàng lẫn giá trị

Thay vì chỉ nhìn vài hàng đầu, có thể đối chiếu:

- **Những ID nào xuất hiện**.
- **Mỗi ID xuất hiện bao nhiêu lần**.
- **Các giá trị có `NULL` hay không**.
- **Tổng/COUNT có đúng cấp dữ liệu**.
- **Kết quả khi không có hàng có khác khi có một hàng `NULL` không**.

Ví dụ, để phát hiện khách hàng bị nhân trong một kết quả JOIN:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
HAVING COUNT(*) > 1
ORDER BY c.customer_id;
```

Kết quả chỉ ra An (3) và Bình (2). Điều đó không chứng minh phép nối “sai”; nó chỉ chứng minh phép nối **không có cardinality một hàng mỗi khách**.

### 23.2. Không kiểm chứng bằng dữ liệu production thiếu các trường hợp biên

Một database hiện tại có thể tình cờ chỉ có tối đa một đơn cho mỗi khách; truy vấn scalar nhiều hàng chưa phát sinh lỗi. Khi ứng dụng vận hành lâu dài, dữ liệu tăng lên sẽ khiến lỗi xuất hiện.

Bộ dữ liệu thử nghiệm có chủ đích giúp phát hiện **khả năng lỗi** ngay cả khi dữ liệu hiện tại chưa có trường hợp đó.

### 23.3. Quy tắc nghiệp vụ và ràng buộc dữ liệu

Nếu thật sự mỗi khách chỉ được có **một** bản ghi thuộc một loại nhất định, có thể dùng ràng buộc `UNIQUE` hoặc thiết kế khóa phù hợp để đảm bảo.

Nhưng nếu nghiệp vụ cho phép một khách có nhiều đơn, **không thể thêm UNIQUE(customer_id) trên bảng đơn chỉ để scalar subquery không lỗi**. Thay vào đó, chọn cách truy vấn xử lý nhiều đơn có chủ đích.

## 24. Bài tập thực hành và lời giải

Dùng bảng `demo_customers` và `demo_orders` ở mục 3.

### Bài 1. Số hàng trả về của truy vấn con

**Câu hỏi:** Truy vấn sau trả bao nhiêu hàng khi thay `:id` lần lượt bằng `1`, `2`, `3` và `4`?

```sql
-- :id là ký hiệu tham số của tầng ứng dụng.
SELECT order_id
FROM demo_orders
WHERE customer_id = :id;
```

**Đáp án:** `3`, `2`, `1` và `0` hàng. Đây là bốn tình huống cardinality cần được tính đến khi đặt subquery vào câu khác.

### Bài 2. Scalar subquery của Bình có hợp lệ không?

```sql
SELECT (
    SELECT amount
    FROM demo_orders
    WHERE customer_id = 2
) AS amount;
```

**Đáp án:** Trên PostgreSQL, không hợp lệ ở ngữ cảnh scalar vì truy vấn con trả **hai hàng** (`800`, `800`), dù chúng có cùng giá trị.

### Bài 3. DISTINCT có giải quyết mọi khách không?

```sql
SELECT (
    SELECT DISTINCT amount
    FROM demo_orders
    WHERE customer_id = 1
) AS amount;
```

**Đáp án:** Không. An có các giá trị tiền phân biệt `500` và `200` nên subquery vẫn trả hai hàng. `DISTINCT` không làm nó thành scalar.

### Bài 4. Một scalar subquery rỗng trả gì?

```sql
SELECT (
    SELECT amount
    FROM demo_orders
    WHERE customer_id = 4
) AS amount;
```

**Đáp án:** Truy vấn ngoài trả một hàng, trong đó `amount = NULL`, vì subquery scalar không trả hàng.

### Bài 5. EXISTS và JOIN có cùng số hàng không?

**Câu A:**

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Câu B:**

```sql
SELECT c.customer_id
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

**Đáp án:** A trả ba hàng `1,2,3`; B trả sáu hàng `1,1,1,2,2,3`. `EXISTS` chỉ kiểm tra tồn tại, còn `JOIN` nhân theo số cặp khớp.

### Bài 6. Vì sao NOT IN không tìm ra Dung?

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE c.customer_id NOT IN (
    SELECT customer_id
    FROM demo_orders
);
```

**Đáp án:** Truy vấn con chứa `NULL`, nên `4 NOT IN (1,1,1,2,2,3,NULL)` cho `UNKNOWN`. `WHERE` loại Dung. Thay bằng `NOT EXISTS` có điều kiện tương quan, hoặc lọc `customer_id IS NOT NULL` trong subquery nếu ý định nghiệp vụ là bỏ qua dòng chưa biết khách.

### Bài 7. COUNT với tập rỗng khác SUM thế nào?

```sql
SELECT
    COUNT(*) AS count_orders,
    SUM(amount) AS sum_amount
FROM demo_orders
WHERE customer_id = 4;
```

**Đáp án:** Một hàng có `count_orders = 0` và `sum_amount = NULL`.

### Bài 8. EXISTS trên COUNT có nhận ra khách chưa có đơn không?

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE EXISTS (
    SELECT COUNT(*)
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Đáp án:** Có thể trả **cả bốn khách**, vì `SELECT COUNT(*)` không `GROUP BY` trả một hàng dù không có đơn. Đây không phải cách kiểm tra có đơn; dùng `EXISTS (SELECT 1 FROM ... WHERE ...)`.

### Bài 9. Vì sao SUM(DISTINCT amount) sai với Bình?

```sql
SELECT
    SUM(amount) AS actual_total,
    SUM(DISTINCT amount) AS distinct_amount_total
FROM demo_orders
WHERE customer_id = 2;
```

**Đáp án:** `actual_total = 1600`, `distinct_amount_total = 800`. Hai đơn khác nhau có cùng giá `800`; tổng doanh thu cần cộng cả hai.

### Bài 10. ANY và ALL với tập rỗng

```sql
SELECT
    999 > ANY (
        SELECT amount FROM demo_orders WHERE 1 = 0
    ) AS a,
    999 > ALL (
        SELECT amount FROM demo_orders WHERE 1 = 0
    ) AS b;
```

**Đáp án:** `a = FALSE`, `b = TRUE`. `ALL` trên tập rỗng đúng theo ngữ nghĩa lượng từ logic.

### Bài 11. Lấy mã đơn cao nhất mỗi khách

```sql
SELECT
    c.customer_id,
    (
        SELECT o.order_id
        FROM demo_orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.order_id DESC
        LIMIT 1
    ) AS selected_order_id
FROM demo_customers AS c
ORDER BY c.customer_id;
```

**Đáp án:**

| customer_id | selected_order_id |
| ---: | ---: |
| 1 | 103 |
| 2 | 105 |
| 3 | 106 |
| 4 | `NULL` |

`ORDER BY order_id DESC` chỉ rõ hàng được chọn và `LIMIT 1` bảo đảm subquery scalar trả tối đa một hàng.

### Bài 12. Tìm khách không có đơn bằng hai cách

**Cách A:**

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE NOT EXISTS (
    SELECT 1 FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

**Cách B:**

```sql
SELECT c.customer_id
FROM demo_customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM demo_orders AS o
    WHERE o.customer_id IS NOT NULL
);
```

**Đáp án:** Trong dữ liệu mẫu, cả hai trả `4`. Hai cách có điều kiện tương đương ở đây vì `c.customer_id` là khóa chính **không `NULL`** và Cách B chủ động bỏ `NULL` phía phải.

### Bài 13. Kiểm tra xem truy vấn ngoài có nhân bản khách không

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Đáp án:** An `3`, Bình `2`, Chi `1`, Dung `1`. Với Dung, hàng thứ nhất chính là hàng `LEFT JOIN` giữ chỗ, không phải một đơn thật. Nếu cần số đơn, dùng `COUNT(o.order_id)` để Dung nhận `0`.

### Bài 14. Phân biệt một hàng NULL và không có hàng

Xét:

```sql
SELECT
    EXISTS (
        SELECT 1 WHERE 1 = 0
    ) AS exists_empty,
    EXISTS (
        SELECT NULL
    ) AS exists_one_null;
```

**Đáp án:** `exists_empty = FALSE` và `exists_one_null = TRUE`. `EXISTS` kiểm tra **có hàng** chứ không kiểm tra giá trị của hàng.

## 25. Những sai lầm cần tránh

| Sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Chỉ thử scalar subquery với khách có một đơn | Không phát hiện lỗi khi nhiều hàng | Thử khách có 0, 1 và nhiều đơn |
| Cho rằng hai hàng cùng giá trị có thể dùng làm scalar | Scalar quan tâm **số hàng**, không chỉ số giá trị phân biệt | Chọn đúng nghiệp vụ: tổng hợp, top 1 hoặc dùng truy vấn bảng |
| Thêm `LIMIT 1` mà không sắp xếp | Hàng được chọn không xác định | `ORDER BY` với khóa phụ rõ ràng |
| Thêm `DISTINCT` mọi nơi để sửa lỗi | Có thể xóa cả bản ghi nghiệp vụ hợp lệ | Xác định khóa của bản ghi và cấp cần tổng hợp |
| Dùng `NOT IN` với subquery chứa `NULL` | Giá trị không khớp có thể cho `UNKNOWN` | `NOT EXISTS` hoặc lọc `NULL` có chủ đích |
| Coi tập rỗng và tập một hàng `NULL` giống nhau | `EXISTS`, `IN`, `NOT IN` có kết quả khác | Dựng hai trường hợp thử riêng |
| Coi `COUNT(*) = 0` là “subquery không trả hàng” | Aggregate không GROUP BY vẫn trả một hàng | Phân biệt hàng kết quả aggregate và hàng nguồn |
| Dùng `EXISTS (SELECT COUNT(*))` để hỏi có dữ liệu | COUNT trả một hàng kể cả khi bằng 0 | `EXISTS (SELECT 1 FROM ... WHERE ...)` |
| Dùng JOIN để kiểm tra tồn tại | Nhân hàng theo số bản ghi con | `EXISTS` hoặc kiểm soát phép nối |
| Dùng `COUNT(*)` sau LEFT JOIN để đếm hàng con | Hàng giữ chỗ của nối trái vẫn được đếm | `COUNT(child.primary_key)` |
| Dùng `SUM(DISTINCT amount)` để “chống cộng trùng” | Hai giao dịch cùng giá tiền bị gộp sai | Tổng hợp ở đúng cấp bản ghi, tránh join nhân chéo |
| Không thử trường hợp khóa tương quan `NULL` | Có thể hiểu sai `=` và ý nghĩa bản ghi thiếu khóa | Xác định chính sách `NULL` rõ ràng |
| Nhầm `ANY` và `ALL` trên tập rỗng | `ANY` sai, `ALL` đúng | Thêm `EXISTS` nếu nghiệp vụ yêu cầu tập không rỗng |
| Suy kết quả chung từ một DBMS | Scalar multirow có khác biệt như SQLite | Kiểm tra phương ngữ và phiên bản mục tiêu |

## 26. Quy trình ngắn để kiểm chứng truy vấn con

Khi gặp hoặc viết một truy vấn con, hãy tiến hành theo các bước:

1. **Xác định vị trí sử dụng:** scalar, `IN`/`NOT IN`, `EXISTS`/`NOT EXISTS`, `ANY`/`ALL` hay bảng con trong `FROM`?
2. **Kiểm tra số cột:** vị trí scalar thường cần đúng một cột; một derived table có thể trả nhiều cột.
3. **Dự đoán số hàng:** truy vấn con có thể trả 0, 1, nhiều hàng hay số hàng phụ thuộc từng hàng ngoài?
4. **Tạo dữ liệu biên:** ít nhất một trường hợp không khớp, một trường hợp khớp đơn, một trường hợp khớp nhiều.
5. **Tạo bản sao có chủ đích:** nhiều bản ghi cùng khóa tham chiếu hoặc cùng giá trị được chọn nhưng khác khóa chính.
6. **Thêm `NULL` khi cột có thể thiếu:** phân biệt không có hàng, một hàng `NULL` và tập chứa cả giá trị thực lẫn `NULL`.
7. **Đọc đúng ngữ nghĩa toán tử:** `EXISTS` chỉ xét sự tồn tại; `IN` xét khớp; `JOIN` nhân cặp hàng; scalar đòi một giá trị.
8. **Quyết định cách xử lý nhiều hàng:** chọn top N có thứ tự, tổng hợp, kiểm tra tồn tại hoặc giữ tất cả — không chọn tùy tiện.
9. **Kiểm tra cấp tổng hợp:** `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT ...)` và `SUM(DISTINCT ...)` không cùng nghĩa.
10. **Kiểm tra đúng DBMS và phiên bản:** nhất là scalar multirow, cú pháp `LIMIT`/`TOP`/`FETCH` và những mở rộng phương ngữ.

**Nguyên tắc cốt lõi:** Muốn kiểm chứng một truy vấn con, đừng chỉ kiểm tra một bộ dữ liệu “đẹp” với đúng một hàng. Hãy buộc câu SQL đối mặt với **tập rỗng, nhiều hàng, các giá trị trùng nhau và `NULL`**. Sau đó chọn công cụ phù hợp với câu hỏi nghiệp vụ: **scalar** cho một giá trị, **`EXISTS`** cho sự tồn tại, **`IN`** cho thuộc tập, **`JOIN`** cho những cặp bản ghi và **aggregate** cho số liệu tổng hợp. Phân biệt các ngữ nghĩa này giúp truy vấn SQL vẫn đúng khi dữ liệu tăng lên và phát sinh những trường hợp mà lúc thử nghiệm ban đầu chưa gặp.
