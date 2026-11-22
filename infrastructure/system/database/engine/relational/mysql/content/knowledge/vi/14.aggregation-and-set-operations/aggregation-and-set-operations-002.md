# NULL, tập rỗng và kết quả của phép tổng hợp

Các hàm tổng hợp trong MySQL như `COUNT()`, `SUM()`, `AVG()`, `MIN()` và `MAX()` không xử lý `NULL` giống nhau. Hầu hết hàm tổng hợp bỏ qua giá trị `NULL`; `COUNT(*)` đếm hàng bất kể các cột có `NULL`, còn `COUNT(expression)` chỉ đếm biểu thức khác `NULL`. Khi đầu vào không có hàng hoặc không có giá trị khác `NULL`, `COUNT()` trả về 0 nhưng `SUM()`, `AVG()`, `MIN()` và `MAX()` trả về `NULL`.

Sự khác biệt giữa tập rỗng, một nhóm không có giá trị hợp lệ và giá trị tổng hợp bằng 0 rất quan trọng trong báo cáo, thống kê doanh thu, phân tích dữ liệu và xử lý dữ liệu thiếu. Trong module `DATABASE_MYSQL`, cần hiểu những quy tắc này để viết `GROUP BY`, `HAVING`, conditional aggregation và truy vấn tổng hợp an toàn.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt tập kết quả rỗng với một tập có hàng nhưng tất cả giá trị tổng hợp đều `NULL`.
- Giải thích khác biệt giữa `COUNT(*)`, `COUNT(expression)` và `COUNT(DISTINCT expression)`.
- Dự đoán kết quả của `SUM()`, `AVG()`, `MIN()`, `MAX()` khi đầu vào rỗng hoặc chứa `NULL`.
- Hiểu vì sao aggregate không có `GROUP BY` vẫn trả một hàng trên tập rỗng, còn `GROUP BY` có thể không trả nhóm nào.
- Sử dụng `COALESCE()`/`IFNULL()` đúng ngữ nghĩa thay vì biến mọi trường hợp thiếu dữ liệu thành 0.
- Viết conditional aggregation, `HAVING` và aggregate qua `LEFT JOIN` mà không đếm nhầm hàng.
- Phân biệt `DISTINCT` với `COUNT(DISTINCT ...)` khi có `NULL`.

## 1. Dữ liệu mẫu

Các ví dụ sử dụng bảng `payment_sample`. Cột `amount` có thể `NULL` để biểu diễn khoản tiền chưa được xác định hoặc không có dữ liệu ghi nhận.

```sql
CREATE TABLE payment_sample (
    payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category VARCHAR(20) NULL,
    amount DECIMAL(12, 2) NULL,
    note VARCHAR(100) NULL,
    PRIMARY KEY (payment_id),
    KEY idx_payment_category (category)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO payment_sample (category, amount, note)
VALUES
    ('A', 10.00, 'cash'),
    ('A', NULL, 'amount pending'),
    ('A', 30.00, 'card'),
    ('B', NULL, 'not recorded'),
    ('B', NULL, NULL),
    (NULL, 5.00, 'unclassified'),
    (NULL, NULL, 'unknown amount');
```

Ta có ba nhóm dữ liệu đang xuất hiện: `A`, `B` và `NULL`. Nhóm `A` có hai giá trị tiền xác định; nhóm `B` có hai hàng nhưng không có giá trị tiền khác `NULL`; nhóm `NULL` có một giá trị tiền và một giá trị thiếu.

## 2. NULL trong hàm tổng hợp

Phần lớn hàm tổng hợp bỏ qua các đối số `NULL`. Điều đó có nghĩa chúng tính trên các giá trị có mặt, không tự coi `NULL` là 0.

| Hàm | Cách xử lý `NULL` | Kết quả khi không có giá trị khác `NULL` |
|---|---|---|
| `COUNT(*)` | Đếm mọi hàng, kể cả hàng có cột `NULL` | `0` nếu đầu vào không có hàng |
| `COUNT(expr)` | Chỉ đếm hàng mà `expr` khác `NULL` | `0` |
| `COUNT(DISTINCT expr)` | Đếm giá trị khác `NULL` duy nhất | `0` |
| `SUM(expr)` | Bỏ qua `NULL`, cộng các giá trị còn lại | `NULL` |
| `AVG(expr)` | Bỏ qua `NULL`, lấy trung bình các giá trị còn lại | `NULL` |
| `MIN(expr)` | Bỏ qua `NULL`, lấy giá trị nhỏ nhất | `NULL` |
| `MAX(expr)` | Bỏ qua `NULL`, lấy giá trị lớn nhất | `NULL` |
| `GROUP_CONCAT(expr)` | Bỏ qua đối số `NULL` | `NULL` nếu không có giá trị khác `NULL` |

### 2.1. COUNT(*) và COUNT(expression)

Chạy truy vấn trên nhóm `A`:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(note) AS note_count
FROM payment_sample
WHERE category = 'A';
```

Kết quả:

| row_count | amount_count | note_count |
|---:|---:|---:|
| 3 | 2 | 3 |

`COUNT(*)` đếm ba hàng. `COUNT(amount)` chỉ đếm hai hàng có `amount` khác `NULL`. `COUNT(note)` đếm ba hàng vì cả ba giá trị `note` của nhóm A đều có dữ liệu.

Chạy trên nhóm `B`:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(note) AS note_count
FROM payment_sample
WHERE category = 'B';
```

Kết quả:

| row_count | amount_count | note_count |
|---:|---:|---:|
| 2 | 0 | 1 |

Nhóm B có hai hàng, nhưng không có giá trị `amount` khác `NULL`. Đây không phải tập rỗng: hàng vẫn tồn tại, chỉ có dữ liệu tiền bị thiếu.

### 2.2. COUNT(DISTINCT expression)

`COUNT(DISTINCT expression)` đếm các giá trị khác `NULL` sau khi loại trùng:

```sql
SELECT
    COUNT(category) AS non_null_categories,
    COUNT(DISTINCT category) AS distinct_non_null_categories
FROM payment_sample;
```

Kết quả là `5` cho `COUNT(category)` và `2` cho `COUNT(DISTINCT category)`: có năm hàng có category khác `NULL`, nhưng chỉ có hai giá trị phân biệt là `A` và `B`.

`COUNT(DISTINCT category)` không đếm `NULL`. Ngược lại, `SELECT DISTINCT category` có thể trả về một hàng `NULL` duy nhất:

```sql
SELECT DISTINCT category
FROM payment_sample;
```

Vì vậy, “đếm giá trị khác nhau” bằng `COUNT(DISTINCT ...)` không tương đương với đếm số hàng của `SELECT DISTINCT` khi cột có `NULL`.

## 3. SUM, AVG, MIN và MAX khi có NULL

Với nhóm `A`:

```sql
SELECT
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'A';
```

Kết quả:

| total_amount | average_amount | minimum_amount | maximum_amount |
|---:|---:|---:|---:|
| 40.00 | 20.00 | 10.00 | 30.00 |

Hàm tổng hợp bỏ qua hàng có `amount IS NULL`. `AVG(amount)` tính trung bình `(10 + 30) / 2 = 20`, không chia cho tổng ba hàng.

Với nhóm `B`:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'B';
```

Kết quả:

| row_count | known_amount_count | total_amount | average_amount | minimum_amount | maximum_amount |
|---:|---:|---:|---:|---:|---:|
| 2 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

Có hàng, nhưng không có số tiền để tính. Trả `0` cho tổng hoặc trung bình ở trường hợp này có thể làm báo cáo hiểu sai rằng tổng tiền thực sự bằng 0.

## 4. Tập rỗng và aggregate không có GROUP BY

Một truy vấn tổng hợp không có `GROUP BY` trả về một hàng kết quả ngay cả khi không có hàng đầu vào. `COUNT()` trả `0`; các hàm như `SUM()`, `AVG()`, `MIN()` và `MAX()` trả `NULL`.

Ví dụ lọc category không tồn tại:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'C';
```

Kết quả:

| row_count | amount_count | total_amount | average_amount | minimum_amount | maximum_amount |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

Lưu ý: truy vấn vẫn trả một hàng. Hàng đó là kết quả của phép tổng hợp trên tập đầu vào rỗng, không phải một hàng dữ liệu `payment_sample`.

### 4.1. Tập rỗng khác với tập có toàn NULL

So sánh hai truy vấn:

```sql
-- Tập đầu vào có hai hàng, nhưng amount đều NULL.
SELECT COUNT(*) AS row_count, COUNT(amount) AS value_count, SUM(amount) AS total
FROM payment_sample
WHERE category = 'B';

-- Không có hàng đầu vào.
SELECT COUNT(*) AS row_count, COUNT(amount) AS value_count, SUM(amount) AS total
FROM payment_sample
WHERE category = 'C';
```

| Trường hợp | `COUNT(*)` | `COUNT(amount)` | `SUM(amount)` |
|---|---:|---:|---:|
| Category B: có hai hàng, amount đều NULL | 2 | 0 | `NULL` |
| Category C: không có hàng | 0 | 0 | `NULL` |

Chỉ nhìn `SUM(amount)` thì không phân biệt được hai trường hợp. Kết hợp `COUNT(*)` và `COUNT(amount)` để biết không có hàng hay có hàng nhưng không có giá trị hợp lệ.

### 4.2. Xóa hết dữ liệu cũng không làm aggregate mất hàng kết quả

Trong một bảng rỗng, truy vấn:

```sql
SELECT COUNT(*) AS row_count, SUM(amount) AS total_amount
FROM payment_sample;
```

vẫn trả một hàng: `row_count = 0`, `total_amount = NULL`. Có thể quan sát trong một bảng tạm hoặc derived table rỗng mà không cần xóa dữ liệu:

```sql
SELECT COUNT(*) AS row_count, SUM(amount) AS total_amount
FROM (
    SELECT CAST(NULL AS DECIMAL(12, 2)) AS amount
    WHERE 1 = 0
) AS empty_input;
```

Đầu vào của aggregate không có hàng nào. Vì vậy `COUNT(*)` bằng 0 và `SUM(amount)` bằng `NULL`.

## 5. GROUP BY trên tập rỗng và nhóm chỉ chứa NULL

Khi có `GROUP BY`, MySQL tạo kết quả cho các nhóm thực sự xuất hiện trong tập sau `WHERE`. Nếu tập đầu vào rỗng, không có nhóm nào và truy vấn không trả hàng.

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM payment_sample
WHERE category = 'C'
GROUP BY category;
```

Kết quả là không có hàng. Điều này khác với aggregate không `GROUP BY`, vốn trả một hàng có `COUNT(*) = 0`.

### 5.1. Nhóm có giá trị NULL

`GROUP BY` gom các giá trị `NULL` của cùng biểu thức vào một nhóm:

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM payment_sample
GROUP BY category;
```

Kết quả có ba nhóm: `A`, `B` và `NULL`. Nhóm `NULL` có hai hàng, một giá trị amount là 5.00 và một giá trị amount là `NULL`, nên `COUNT(*) = 2`, `COUNT(amount) = 1`, `SUM(amount) = 5.00`.

Nhóm `NULL` không có nghĩa các hàng được coi là bằng nhau trong mọi phép so sánh. Quy tắc gom nhóm của `GROUP BY` xử lý các giá trị `NULL` cùng nhóm; còn phép so sánh `category = NULL` vẫn cho `UNKNOWN`. Để lọc nhóm null, dùng `WHERE category IS NULL`.

## 6. COALESCE và IFNULL: khi nào nên đổi NULL thành 0?

`COALESCE()` trả về đối số đầu tiên khác `NULL`; `IFNULL()` nhận hai đối số và trả đối số thứ hai khi đối số đầu tiên là `NULL`.

```sql
SELECT
    SUM(amount) AS raw_total,
    COALESCE(SUM(amount), 0) AS displayed_total,
    IFNULL(AVG(amount), 0) AS displayed_average
FROM payment_sample
WHERE category = 'C';
```

Kết quả `raw_total` và `AVG` là `NULL`; hai biểu thức bọc trả `0` để hiển thị. Đây là quyết định trình bày hoặc quy tắc nghiệp vụ, không phải thuộc tính tự nhiên của phép tổng hợp.

### 6.1. Không làm mất thông tin về trạng thái dữ liệu

Nếu chỉ trả `COALESCE(SUM(amount), 0)`, người đọc không biết tổng bằng 0 vì:

- Không có hàng phù hợp.
- Có hàng nhưng tất cả amount đều `NULL`.
- Có các giá trị amount hợp lệ và tổng thực sự bằng 0.

Có thể trả thêm các bộ đếm để giữ ngữ cảnh:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count,
    SUM(amount) AS raw_total,
    COALESCE(SUM(amount), 0) AS total_for_display,
    CASE
        WHEN COUNT(*) = 0 THEN 'NO_ROWS'
        WHEN COUNT(amount) = 0 THEN 'ALL_VALUES_NULL'
        ELSE 'HAS_VALUES'
    END AS data_state
FROM payment_sample
WHERE category = 'B';
```

`COALESCE()` phù hợp khi báo cáo định nghĩa “không có số liệu” là hiển thị 0. Nếu người dùng cần phân biệt “không có dữ liệu” với “không phát sinh”, hãy giữ `NULL` hoặc trả thêm trạng thái.

### 6.2. AVG(amount) khác AVG(COALESCE(amount, 0))

Hai biểu thức sau có mẫu số khác nhau:

```sql
SELECT
    AVG(amount) AS average_known_values,
    AVG(COALESCE(amount, 0)) AS average_null_as_zero
FROM payment_sample
WHERE category = 'A';
```

Với nhóm A, `AVG(amount)` tính trung bình các giá trị đã biết (10 và 30), bằng 20. `AVG(COALESCE(amount, 0))` thay giá trị thiếu bằng 0 trước khi tính và chia cho cả ba hàng, bằng khoảng 13.3333.

Chỉ dùng cách thứ hai nếu nghiệp vụ xác nhận `NULL` thực sự có nghĩa là 0. Nếu `NULL` nghĩa là chưa ghi nhận, chưa biết hoặc không áp dụng, thay bằng 0 sẽ làm sai thống kê.

## 7. Conditional aggregation

Conditional aggregation dùng `CASE` bên trong hàm tổng hợp để tính nhiều chỉ số trong cùng một lần nhóm dữ liệu.

Ví dụ đếm số giao dịch theo trạng thái:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(CASE WHEN category = 'A' THEN 1 END) AS category_a_rows,
    COUNT(CASE WHEN category = 'B' THEN 1 END) AS category_b_rows,
    COUNT(CASE WHEN category IS NULL THEN 1 END) AS unclassified_rows
FROM payment_sample;
```

`CASE` không có nhánh `ELSE` sẽ trả `NULL` khi điều kiện không khớp. `COUNT()` bỏ qua các giá trị `NULL`, nên mỗi biểu thức đếm đúng số hàng thỏa điều kiện.

### 7.1. Đếm và cộng theo điều kiện

```sql
SELECT
    COUNT(CASE WHEN category = 'A' THEN 1 END) AS a_row_count,
    COUNT(CASE WHEN category = 'B' THEN 1 END) AS b_row_count,
    SUM(CASE WHEN category = 'A' THEN amount ELSE 0 END) AS a_total_with_zero_else,
    COALESCE(SUM(CASE WHEN category = 'B' THEN amount END), 0) AS b_total_for_display
FROM payment_sample;
```

`COUNT(CASE ...)` trả 0 nếu không có hàng phù hợp. Với `SUM(CASE WHEN ... THEN amount ELSE 0 END)`, các hàng không khớp đóng góp 0; nếu không có hàng đầu vào, `SUM()` vẫn trả `NULL` vì không có biểu thức nào được cộng. Với nhóm B, các hàng khớp có amount đều `NULL`; `COALESCE()` biến tổng `NULL` thành 0 để hiển thị.

Nếu cần phân biệt “không có giao dịch B” với “có giao dịch B nhưng amount chưa được ghi”, hãy tính thêm `COUNT(CASE WHEN category = 'B' THEN 1 END)` và `COUNT(CASE WHEN category = 'B' THEN amount END)`.

### 7.2. Conditional aggregation theo từng nhóm

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(CASE WHEN amount >= 20 THEN 1 END) AS amount_at_least_20,
    SUM(CASE WHEN amount >= 20 THEN amount ELSE 0 END) AS sum_at_least_20
FROM payment_sample
GROUP BY category;
```

Điều kiện `amount >= 20` với amount `NULL` trả `UNKNOWN`, vì vậy nhánh `WHEN` không được chọn và nhánh `ELSE 0` được dùng. Nếu không có `ELSE`, `CASE` sẽ trả `NULL` ở những hàng không thỏa điều kiện; cách chọn phụ thuộc việc bạn muốn bỏ qua hay đóng góp 0.

## 8. HAVING và nhóm không có giá trị

`WHERE` lọc hàng trước khi nhóm và tổng hợp; `HAVING` lọc kết quả nhóm sau khi tính aggregate.

Ví dụ chỉ giữ nhóm có ít nhất một amount đã ghi nhận:

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM payment_sample
GROUP BY category
HAVING COUNT(amount) > 0;
```

Nhóm B bị loại vì `COUNT(amount) = 0`, dù nhóm có hai hàng. Nhóm A và nhóm `NULL` được giữ.

Nếu muốn tìm nhóm có hàng nhưng toàn bộ giá trị amount là `NULL`:

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count
FROM payment_sample
GROUP BY category
HAVING COUNT(*) > 0
   AND COUNT(amount) = 0;
```

Không thể dùng `WHERE SUM(amount) ...` để lọc nhóm vì aggregate được tính sau bước lọc hàng. Dùng `HAVING` cho điều kiện phụ thuộc kết quả tổng hợp.

## 9. Aggregate qua LEFT JOIN và bẫy COUNT(*)

Khi dùng `LEFT JOIN`, một hàng ở bảng bên trái không có bản ghi khớp vẫn xuất hiện với các cột phía phải là `NULL`. Vì vậy, `COUNT(*)` đếm cả hàng mở rộng có giá trị null, còn `COUNT(child.primary_key)` chỉ đếm các hàng con thực sự khớp.

```sql
CREATE TABLE customer_sample (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_sample (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_sample_customer (customer_id)
) ENGINE=InnoDB;

INSERT INTO customer_sample VALUES
    (1, 'An'), (2, 'Binh'), (3, 'Chi');

INSERT INTO order_sample VALUES
    (101, 1, 100.00),
    (102, 1, NULL),
    (103, 2, 0.00);
```

Đếm đơn hàng theo khách:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count,
    COUNT(o.amount) AS known_amount_count,
    SUM(o.amount) AS total_amount
FROM customer_sample AS c
LEFT JOIN order_sample AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả đáng chú ý:

- Khách An có hai đơn: `COUNT(*) = 2`, `COUNT(o.order_id) = 2`, `COUNT(o.amount) = 1`, `SUM(o.amount) = 100.00`.
- Khách Binh có một đơn với amount bằng 0: cả hai bộ đếm hàng/đơn đều bằng 1, `COUNT(o.amount) = 1`, `SUM = 0.00`.
- Khách Chi không có đơn: `LEFT JOIN` tạo một hàng mở rộng với cột `o.*` là `NULL`; do đó `COUNT(*) = 1`, nhưng `COUNT(o.order_id) = 0`, `COUNT(o.amount) = 0`, `SUM(o.amount) = NULL`.

Nếu báo cáo cần số đơn hàng, hãy dùng `COUNT(o.order_id)` hoặc một cột con chắc chắn `NOT NULL`, không dùng `COUNT(*)` trong truy vấn `LEFT JOIN` theo cách này.

### 9.1. Khi nào COALESCE tổng LEFT JOIN thành 0?

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.amount), 0) AS total_for_display
FROM customer_sample AS c
LEFT JOIN order_sample AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Khách Chi sẽ có `order_count = 0` và `total_for_display = 0`. Nhưng nếu khách có đơn mà mọi `amount` đều `NULL`, tổng cũng sẽ được hiển thị là 0. Nếu cần phân biệt hai trạng thái, giữ thêm `COUNT(o.order_id)` và `COUNT(o.amount)`.

## 10. GROUP_CONCAT và giá trị NULL

`GROUP_CONCAT()` nối các giá trị không `NULL` trong một nhóm. Nó bỏ qua đối số `NULL`; nếu nhóm không có giá trị khác `NULL`, kết quả là `NULL`.

```sql
SELECT
    category,
    GROUP_CONCAT(note ORDER BY note SEPARATOR ', ') AS notes
FROM payment_sample
GROUP BY category;
```

Nhóm B có một note là `'not recorded'` và một note `NULL`, nên chuỗi chỉ chứa `'not recorded'`. Nếu tất cả note của nhóm đều `NULL`, kết quả `notes` là `NULL`.

Giới hạn độ dài kết quả được điều khiển bởi `group_concat_max_len` (mặc định thường là 1024 byte). Kiểm tra giá trị hiện tại:

```sql
SELECT @@SESSION.group_concat_max_len;
```

Nếu kết quả bị cắt, hãy kiểm tra warning và cân nhắc điều chỉnh giới hạn theo nhu cầu, đồng thời tính đến `max_allowed_packet` và bộ nhớ. Không giả định `GROUP_CONCAT()` luôn trả toàn bộ nội dung không giới hạn.

## 11. NULL trong biểu thức tổng hợp và phép tính

### 11.1. Chia cho 0 và mẫu số không có giá trị

Để tính tỷ lệ, hãy chọn mẫu số có ý nghĩa và xử lý trường hợp mẫu số bằng 0:

```sql
SELECT
    SUM(amount) / NULLIF(COUNT(amount), 0) AS average_amount
FROM payment_sample
WHERE category = 'B';
```

`NULLIF(COUNT(amount), 0)` trả `NULL` khi không có giá trị amount. Phép chia khi đó trả `NULL` thay vì thực hiện chia cho 0. Với phép tính trung bình đơn giản, `AVG(amount)` thường rõ ràng hơn; ví dụ này minh họa cách bảo vệ mẫu số trong biểu thức tỷ lệ.

### 11.2. NULL trong phép cộng trước khi tổng hợp

```sql
SELECT SUM(amount + shipping_fee) AS total_with_shipping
FROM order_with_shipping;
```

Nếu một trong hai toán hạng là `NULL`, phép cộng cho `NULL`; `SUM()` bỏ qua hàng đó. Nếu nghiệp vụ coi phí chưa có là 0, hãy viết rõ:

```sql
SELECT SUM(amount + COALESCE(shipping_fee, 0)) AS total_with_shipping
FROM order_with_shipping;
```

Chỉ dùng `COALESCE(shipping_fee, 0)` nếu `NULL` thực sự mang nghĩa không phát sinh phí. Nếu `NULL` có nghĩa chưa tính phí, phép thay thế có thể làm báo cáo thiếu chính xác.

## 12. Tập rỗng trong subquery và phép kiểm tra tồn tại

Một subquery trả không hàng có ngữ nghĩa khác với một aggregate subquery:

- Scalar subquery không trả hàng sẽ cho giá trị `NULL`.
- Scalar subquery có aggregate không `GROUP BY` vẫn trả một hàng kết quả; `COUNT(*)` có thể là 0 và `SUM()` có thể là `NULL`.
- `EXISTS (subquery)` trả FALSE nếu subquery không có hàng; `NOT EXISTS` trả TRUE.

Ví dụ:

```sql
SELECT
    (SELECT amount
     FROM payment_sample
     WHERE category = 'C'
     LIMIT 1) AS scalar_no_row,
    (SELECT COUNT(*)
     FROM payment_sample
     WHERE category = 'C') AS aggregate_count,
    EXISTS (
        SELECT 1
        FROM payment_sample
        WHERE category = 'C'
    ) AS has_category_c;
```

Kết quả tương ứng là `NULL`, `0` và `0`. Dùng `EXISTS`/`NOT EXISTS` khi câu hỏi nghiệp vụ là “có hàng nào hay không”, thay vì đếm toàn bộ nếu không cần con số.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `SUM()` trả `NULL` dù truy vấn có hàng | Mọi giá trị của biểu thức tổng hợp đều `NULL` | Kiểm tra `COUNT(*)` và `COUNT(expr)` để phân biệt |
| `COUNT(*)` và `COUNT(column)` khác nhau | `COUNT(*)` đếm hàng, `COUNT(column)` bỏ qua `NULL` | Chọn bộ đếm theo câu hỏi nghiệp vụ |
| Báo cáo hiện 0 khi không có dữ liệu | `COALESCE(SUM(...), 0)` đã gộp tập rỗng và all-NULL | Trả thêm row count/value count hoặc trạng thái |
| Trung bình thấp bất ngờ | `AVG(COALESCE(value, 0))` tính cả hàng thiếu như 0 | Chỉ thay NULL bằng 0 khi nghiệp vụ quy định |
| GROUP BY không trả hàng khi lọc tập rỗng | Không có nhóm nào để tạo | Nếu cần một hàng tổng hợp, bỏ GROUP BY hoặc dùng scalar aggregate |
| LEFT JOIN đếm khách không có đơn thành 1 | Dùng `COUNT(*)` trên hàng mở rộng của LEFT JOIN | Dùng `COUNT(child.primary_key)` |
| COUNT(DISTINCT col) thấp hơn số giá trị DISTINCT nhìn thấy | `COUNT(DISTINCT)` bỏ qua NULL, còn `SELECT DISTINCT` có thể trả một NULL | Xác định có cần tính NULL như một giá trị riêng hay không |
| GROUP_CONCAT bị cắt | Vượt `group_concat_max_len` | Kiểm tra session setting và warning, tăng có kiểm soát nếu cần |

## 14. Quy trình đọc kết quả aggregate

Khi một phép tổng hợp trả `NULL` hoặc 0, kiểm tra theo thứ tự:

1. Xem truy vấn sau `WHERE` có bao nhiêu hàng bằng `COUNT(*)`.
2. Xem biểu thức aggregate có bao nhiêu giá trị khác `NULL` bằng `COUNT(expr)`.
3. Xem các giá trị có thực sự bằng 0 hay chỉ đang thiếu.
4. Nếu có `GROUP BY`, xác định nhóm có xuất hiện trong tập đầu vào hay không.
5. Nếu có `LEFT JOIN`, đếm khóa chính phía con thay vì đếm hàng join chung.
6. Kiểm tra `CASE`, `COALESCE`, `IFNULL` và phép tính bên trong aggregate có làm thay đổi ngữ nghĩa `NULL` hay không.
7. Chỉ thay `NULL` thành 0 ở tầng báo cáo khi định nghĩa nghiệp vụ cho phép.

Một truy vấn chẩn đoán hữu ích:

```sql
SELECT
    COUNT(*) AS input_rows,
    COUNT(amount) AS non_null_amounts,
    SUM(amount) AS raw_sum,
    AVG(amount) AS raw_average,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'B';
```

Kết quả cho biết có hai hàng đầu vào nhưng không có amount hợp lệ để tổng hợp. Đây là cách chẩn đoán tốt hơn việc chỉ bọc `SUM()` trong `COALESCE()` rồi bỏ qua nguyên nhân.

## 15. Bài thực hành

Thực hiện trong database lab riêng với `payment_sample`, `customer_sample` và `order_sample`:

1. Tính `COUNT(*)`, `COUNT(amount)`, `SUM(amount)` và `AVG(amount)` cho category A và B; giải thích khác biệt.
2. Lọc category C không tồn tại và quan sát aggregate không `GROUP BY` vẫn trả một hàng.
3. Thêm `GROUP BY category` vào truy vấn trên và xác nhận kết quả không có hàng.
4. Chạy `SELECT DISTINCT category` và `COUNT(DISTINCT category)` để quan sát cách mỗi câu xử lý `NULL`.
5. Tạo một nhóm có hàng nhưng toàn bộ amount là `NULL`; dùng `HAVING COUNT(*) > 0 AND COUNT(amount) = 0` để tìm nhóm đó.
6. So sánh `AVG(amount)` với `AVG(COALESCE(amount, 0))`; giải thích ảnh hưởng của mẫu số.
7. Viết conditional aggregation để đếm số hàng từng category và tính tổng amount theo điều kiện.
8. Dùng `LEFT JOIN` để đếm đơn theo khách; so sánh `COUNT(*)` với `COUNT(order_id)` cho khách không có đơn.
9. Thử `GROUP_CONCAT(note)` trên nhóm có note `NULL` và nhóm chỉ có note `NULL`; kiểm tra `group_concat_max_len`.
10. So sánh scalar subquery rỗng, aggregate scalar subquery và `EXISTS` trên cùng điều kiện không có hàng.
11. Thiết kế một báo cáo có ba trạng thái: `NO_ROWS`, `ALL_VALUES_NULL`, `HAS_VALUES`; trả cả số hàng và số giá trị hợp lệ.
12. Viết giải thích ngắn cho nghiệp vụ về lúc nào tổng tiền thiếu phải hiển thị `NULL`, lúc nào có thể hiển thị 0.

Bạn hoàn thành bài khi có thể phân biệt tập rỗng, nhóm toàn `NULL` và tổng thực sự bằng 0; đồng thời chọn đúng hàm đếm và cách xử lý giá trị thiếu trong báo cáo.

## 16. Nguyên tắc cần ghi nhớ

- `COUNT(*)` đếm hàng; `COUNT(expr)` đếm giá trị khác `NULL`; `COUNT(DISTINCT expr)` đếm giá trị khác `NULL` duy nhất.
- `SUM()`, `AVG()`, `MIN()` và `MAX()` bỏ qua `NULL`, trả `NULL` nếu không có giá trị hợp lệ.
- Aggregate không `GROUP BY` trả một hàng trên tập rỗng; `COUNT()` là 0 còn các aggregate giá trị thường là `NULL`.
- `GROUP BY` trên tập rỗng không tạo nhóm và không trả hàng.
- `GROUP BY` gom các giá trị `NULL` vào cùng một nhóm; `WHERE col = NULL` vẫn không đúng, hãy dùng `IS NULL`.
- Có hàng nhưng toàn bộ giá trị aggregate là `NULL` khác với không có hàng; dùng cả `COUNT(*)` và `COUNT(expr)` để phân biệt.
- `COALESCE(SUM(expr), 0)` là quy tắc hiển thị/nghiệp vụ, không chứng minh tổng thực sự bằng 0.
- `AVG(COALESCE(expr, 0))` thay đổi mẫu số; chỉ dùng nếu NULL được định nghĩa là 0.
- `LEFT JOIN` tạo hàng mở rộng; dùng `COUNT(child.primary_key)` để đếm bản ghi con thực sự tồn tại.
- `HAVING` lọc nhóm sau tổng hợp; `WHERE` lọc hàng trước tổng hợp.
- `GROUP_CONCAT()` bỏ qua NULL và có thể bị cắt theo `group_concat_max_len`.
