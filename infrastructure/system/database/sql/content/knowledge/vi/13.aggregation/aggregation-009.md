# Kết quả khi đầu vào rỗng hoặc toàn NULL

Một báo cáo SQL có thể không tìm thấy **bất kỳ bản ghi nào**, hoặc tìm thấy nhiều bản ghi nhưng **cột dùng để tính tổng đều là `NULL`**. Hai tình huống khác nhau này thường tạo cùng kết quả `NULL` ở `SUM` hoặc `AVG`, trong khi `COUNT(*)` và `COUNT(column)` lại giúp phân biệt chúng.

Ví dụ, một cửa hàng không có giao dịch trong ngày khác với một cửa hàng có giao dịch nhưng chưa đồng bộ được số tiền. Nếu hệ thống tự biến cả hai trường hợp thành tổng tiền bằng `0`, người đọc báo cáo có thể hiểu nhầm rằng mọi giao dịch đều đã được kiểm kê và giá trị thực bằng không.

Bài học thuộc **Database SQL → Tổng hợp dữ liệu**, tập trung vào ngữ nghĩa của các hàm tổng hợp (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX` và một số hàm khác) khi dữ liệu đầu vào rỗng, toàn `NULL` hoặc có giá trị bằng 0. Ví dụ thực hành dùng **PostgreSQL**; các điểm khác biệt của những hệ quản trị khác được nêu riêng.

## 1. Ba tình huống phải phân biệt

Khi nói một tập dữ liệu “không có gì để tính”, cần xác định cụ thể trường hợp nào xảy ra:

| Tình huống | Dòng dữ liệu | Giá trị ở cột `amount` | Ý nghĩa có thể gặp |
| --- | ---: | --- | --- |
| **Đầu vào rỗng** | 0 dòng | Không tồn tại giá trị nào | Không có giao dịch trong khoảng thời gian chọn |
| **Có dòng nhưng toàn NULL** | 2 dòng | `NULL`, `NULL` | Có giao dịch nhưng chưa có số tiền |
| **Có dòng, giá trị bằng 0** | 2 dòng | `0`, `0` | Có giao dịch với giá trị đã biết bằng 0 |

Ba tình huống không đồng nghĩa:

- **Không có dòng**: truy vấn nguồn, sau `FROM` và `WHERE`, không tạo bản ghi nào để tổng hợp.
- **Toàn `NULL` trong cột tính toán**: tập nguồn có dòng, nhưng biểu thức đưa vào hàm tổng hợp đều là `NULL`.
- **Giá trị `0`**: số 0 là giá trị số xác định, không bị xem là thiếu dữ liệu.

Có thể minh họa bằng ba tập số:

```text
A: []                  -- không có dòng
B: [NULL, NULL]        -- có hai dòng, cả hai thiếu amount
C: [0, 0]              -- có hai dòng, cả hai amount = 0
```

Với những hàm SQL thông dụng:

| Hàm tổng hợp | A: rỗng | B: toàn NULL | C: hai số 0 |
| --- | ---: | ---: | ---: |
| `COUNT(*)` | `0` | `2` | `2` |
| `COUNT(amount)` | `0` | `0` | `2` |
| `SUM(amount)` | `NULL` | `NULL` | `0` |
| `AVG(amount)` | `NULL` | `NULL` | `0` |
| `MIN(amount)` | `NULL` | `NULL` | `0` |
| `MAX(amount)` | `NULL` | `NULL` | `0` |

**Quy tắc cốt lõi:** với các hàm trên, `COUNT` trả về `0` khi không có giá trị nào để đếm; `SUM`, `AVG`, `MIN`, `MAX` trả về `NULL` khi không còn **giá trị đầu vào khác `NULL`** để tính.

Kết quả trong bảng được hiểu cho một phép **tổng hợp toàn bộ tập dữ liệu, không `GROUP BY`**, nên mỗi truy vấn vẫn tạo một hàng kết quả. Nếu có `GROUP BY`, câu chuyện về **số hàng kết quả** còn một quy tắc riêng.

## 2. Tổng hợp xử lý NULL như thế nào?

Các hàm tổng hợp SQL thông dụng thường **bỏ qua đầu vào `NULL`** trong biểu thức được tổng hợp:

```sql
SELECT
    COUNT(amount),
    SUM(amount),
    AVG(amount),
    MIN(amount),
    MAX(amount)
FROM some_table;
```

Ở đây:

- `COUNT(*)` đếm **mọi hàng**, không phụ thuộc giá trị của từng cột.
- `COUNT(amount)` đếm hàng mà biểu thức `amount` **khác `NULL`**.
- `SUM(amount)` cộng các giá trị khác `NULL`.
- `AVG(amount)` tính trung bình các giá trị khác `NULL`, không lấy số lượng tất cả hàng làm mẫu số.
- `MIN(amount)` và `MAX(amount)` tìm cực trị trong các giá trị khác `NULL`.

Vì thế, với dãy `[10, NULL, 20]`:

```text
COUNT(*)      = 3
COUNT(amount) = 2
SUM(amount)   = 30
AVG(amount)   = 15
MIN(amount)   = 10
MAX(amount)   = 20
```

**Bỏ qua `NULL` không có nghĩa thay `NULL` bằng `0`.** Nếu thay bằng 0 trước khi tính `AVG`, mẫu số sẽ thay đổi và kết quả có thể khác.

### COUNT(*) và COUNT(expression) không giống nhau

```sql
-- PostgreSQL: hai giá trị NULL trên hai hàng
WITH source_rows(amount) AS (
    VALUES (NULL::NUMERIC), (NULL::NUMERIC)
)
SELECT COUNT(*)      AS total_rows,
       COUNT(amount) AS known_amounts
FROM source_rows;
```

Kết quả:

| `total_rows` | `known_amounts` |
| ---: | ---: |
| 2 | 0 |

`COUNT(*)` không nhìn vào một cột cụ thể. `COUNT(amount)` kiểm tra giá trị của biểu thức `amount` ở từng hàng.

Một biểu thức hằng khác `NULL` cũng được tính là có giá trị trên mỗi hàng:

```sql
SELECT COUNT(1) AS row_count_equivalent
FROM source_rows;
```

`COUNT(1)` cũng đếm số hàng vì `1` khác `NULL`. Tuy nhiên, khi muốn diễn đạt **đếm hàng**, `COUNT(*)` dễ hiểu và là cách viết phổ biến hơn.

## 3. Tạo bảng PostgreSQL để thực hành

Dùng hai bảng tạm: một bảng dữ liệu bán hàng và một bảng danh mục nhóm. Hãy chạy trong một kết nối **PostgreSQL thực hành**. Bảng tạm chỉ tồn tại trong phiên kết nối; nếu đã có cùng tên, mở phiên mới hoặc chọn tên bảng khác.

```sql
CREATE TEMP TABLE aggregation_null_lab (
    sale_id     INTEGER PRIMARY KEY,
    segment     TEXT NOT NULL,
    amount      NUMERIC(12, 2),
    description TEXT
);

INSERT INTO aggregation_null_lab
    (sale_id, segment, amount, description)
VALUES
    (1, 'A', 100.00, 'Đã ghi nhận tiền'),
    (2, 'A', NULL,   'Chưa đồng bộ tiền'),
    (3, 'A',   0.00, 'Giá trị hợp lệ bằng 0'),
    (4, 'B', NULL,   'Chưa có số tiền'),
    (5, 'B', NULL,   'Vẫn chưa có số tiền'),
    (6, 'C',   0.00, 'Không phát sinh tiền'),
    (7, 'C',   0.00, 'Không phát sinh tiền');

CREATE TEMP TABLE aggregation_segments_lab (
    segment TEXT PRIMARY KEY
);

INSERT INTO aggregation_segments_lab (segment)
VALUES ('A'), ('B'), ('C'), ('D');

SELECT sale_id, segment, amount, description
FROM aggregation_null_lab
ORDER BY sale_id;
```

Bộ dữ liệu có ý nghĩa:

| Nhóm | Dòng trong bảng bán hàng | Các giá trị `amount` |
| --- | ---: | --- |
| A | 3 | `100.00`, `NULL`, `0.00` |
| B | 2 | `NULL`, `NULL` |
| C | 2 | `0.00`, `0.00` |
| D | 0 | Không có dòng bán hàng |

Nhóm **D** tồn tại trong **bảng danh mục**, nhưng chưa có bản ghi bán hàng. Điều này giúp thực hành cả “nhóm có dòng nhưng thiếu số tiền” lẫn “nhóm không có dòng”.

## 4. Tổng hợp toàn bảng: COUNT khác SUM và AVG

Thực hiện:

```sql
SELECT
    COUNT(*)       AS total_rows,
    COUNT(amount)  AS known_amounts,
    SUM(amount)    AS total_amount,
    AVG(amount)    AS average_amount,
    MIN(amount)    AS minimum_amount,
    MAX(amount)    AS maximum_amount
FROM aggregation_null_lab;
```

Kết quả trên bảng mẫu:

| `total_rows` | `known_amounts` | `total_amount` | `average_amount` | `minimum_amount` | `maximum_amount` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 4 | 100.00 | 25.00 | 0.00 | 100.00 |

Giải thích theo từng bước:

1. Bảng có **7 hàng** nên `COUNT(*) = 7`.
2. Có **4 hàng** có `amount` khác `NULL` nên `COUNT(amount) = 4`.
3. Các giá trị hợp lệ là `100`, `0`, `0`, `0` nên `SUM(amount) = 100`.
4. `AVG(amount) = 100 / 4 = 25`, không phải `100 / 7`.
5. Cực tiểu trong các giá trị hợp lệ là `0`; cực đại là `100`.

Nếu cần biết **bao nhiêu hàng thiếu giá trị amount**, có thể tính:

```sql
SELECT COUNT(*) - COUNT(amount) AS missing_amount_rows
FROM aggregation_null_lab;
```

Kết quả là **3**. Cách tính này phù hợp khi mỗi hàng có đúng một giá trị `amount` cần xác định là có hay thiếu.

## 5. Đầu vào rỗng: không có hàng vẫn có thể trả một hàng tổng hợp

Một phép lọc có thể loại hết tất cả hàng:

```sql
SELECT
    COUNT(*)      AS total_rows,
    COUNT(amount) AS known_amounts,
    SUM(amount)   AS total_amount,
    AVG(amount)   AS average_amount,
    MIN(amount)   AS minimum_amount,
    MAX(amount)   AS maximum_amount
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Trong bảng mẫu không có `segment = 'Z'`. Kết quả là **một hàng**:

| `total_rows` | `known_amounts` | `total_amount` | `average_amount` | `minimum_amount` | `maximum_amount` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

Vì sao vẫn có một hàng?

Khi câu `SELECT` dùng **hàm tổng hợp và không có `GROUP BY`**, DBMS tạo ra một nhóm tổng hợp toàn cục trên các hàng nguồn. Dù tập nguồn không có dòng nào, nhóm tổng hợp toàn cục vẫn cho một hàng kết quả, trừ khi bị điều kiện `HAVING` loại bỏ.

Điều này khác với một truy vấn chỉ đọc các hàng thông thường:

```sql
-- Không có hàm tổng hợp: trả 0 hàng
SELECT sale_id, amount
FROM aggregation_null_lab
WHERE segment = 'Z';

-- Có tổng hợp toàn cục: trả 1 hàng chứa COUNT(*) = 0
SELECT COUNT(*) AS total_rows
FROM aggregation_null_lab
WHERE segment = 'Z';
```

**Đầu vào rỗng không đồng nghĩa đầu ra truy vấn rỗng.** Phải nhìn xem câu SQL có tổng hợp toàn cục, `GROUP BY` hay `HAVING` hay không.

### Cách thử mà không cần bảng dữ liệu

PostgreSQL cho phép tạo một nguồn rỗng bằng `WHERE FALSE`:

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(x)   AS sum_value
FROM (
    SELECT 5::NUMERIC AS x
    WHERE FALSE
) AS empty_source;
```

Kết quả: một hàng có `row_count = 0` và `sum_value = NULL`.

## 6. Có hàng nhưng toàn NULL: nhìn giống tập rỗng ở nhiều hàm

Nhóm B có hai hàng, nhưng `amount` của cả hai đều `NULL`:

```sql
SELECT
    COUNT(*)       AS total_rows,
    COUNT(amount)  AS known_amounts,
    SUM(amount)    AS total_amount,
    AVG(amount)    AS average_amount,
    MIN(amount)    AS minimum_amount,
    MAX(amount)    AS maximum_amount
FROM aggregation_null_lab
WHERE segment = 'B';
```

Kết quả:

| `total_rows` | `known_amounts` | `total_amount` | `average_amount` | `minimum_amount` | `maximum_amount` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

So với đầu vào rỗng:

- `COUNT(*)` khác: **2** thay vì **0**.
- `COUNT(amount)` đều là **0**.
- `SUM`, `AVG`, `MIN`, `MAX` đều là **`NULL`**.

Vì vậy **chỉ nhìn `SUM(amount) IS NULL` không đủ để biết không có hàng hay có hàng nhưng toàn giá trị thiếu**.

### Tại sao SUM không trả 0?

Một cách hiểu hữu ích:

- `SUM(0, 0) = 0` vì có hai số đã xác định và tổng của chúng bằng 0.
- `SUM(NULL, NULL) = NULL` vì không có số đã xác định nào để tạo kết quả.
- `SUM` trên **không hàng** cũng là `NULL` theo ngữ nghĩa SQL phổ biến.

Nhiều người nghĩ “tổng của tập rỗng bằng 0” theo quy ước đại số, nhưng không nên áp quy ước đó vào hành vi mặc định của `SUM` trong SQL. Nếu báo cáo cần số 0 cho trường hợp không có giao dịch, hãy đặt **quy tắc chuyển đổi kết quả** rõ ràng, ví dụ với `COALESCE` hoặc `CASE` ở phần sau.

### Trường hợp có số 0 thật

Nhóm C có hai hàng với `amount = 0`:

```sql
SELECT
    COUNT(*)      AS total_rows,
    COUNT(amount) AS known_amounts,
    SUM(amount)   AS total_amount,
    AVG(amount)   AS average_amount
FROM aggregation_null_lab
WHERE segment = 'C';
```

Kết quả: `total_rows = 2`, `known_amounts = 2`, `total_amount = 0` và `average_amount = 0`.

Ở đây `0` là giá trị xác định. SQL không bỏ qua nó như `NULL`.

## 7. GROUP BY thay đổi số hàng kết quả khi nguồn rỗng

Đây là điểm phân biệt quan trọng nhất bên cạnh giá trị của từng hàm.

### Không GROUP BY: một kết quả cho toàn bộ tập

```sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Trả **một hàng**: `(0, NULL)`.

### Có GROUP BY trên cột: chỉ có những nhóm thực sự hình thành

```sql
SELECT segment,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM aggregation_null_lab
WHERE segment = 'Z'
GROUP BY segment;
```

Trả **0 hàng**. Không có hàng đầu vào nên không tạo được nhóm `segment` nào.

Nếu bỏ điều kiện `WHERE`:

```sql
SELECT segment,
       COUNT(*) AS row_count,
       COUNT(amount) AS known_amounts,
       SUM(amount) AS total_amount
FROM aggregation_null_lab
GROUP BY segment
ORDER BY segment;
```

Kết quả:

| `segment` | `row_count` | `known_amounts` | `total_amount` |
| --- | ---: | ---: | ---: |
| A | 3 | 2 | 100.00 |
| B | 2 | 0 | `NULL` |
| C | 2 | 2 | 0.00 |

**Không có nhóm D trong kết quả** vì bảng nguồn không có hàng nào mang `segment = 'D'`.

### Sơ đồ phân biệt

```text
Đầu vào rỗng: []

SELECT COUNT(*), SUM(x)
  không GROUP BY
    └─ 1 nhóm tổng hợp toàn cục
         └─ 1 hàng: (0, NULL)

SELECT category, COUNT(*), SUM(x)
  GROUP BY category
    └─ không có category từ hàng nguồn
         └─ 0 nhóm
              └─ 0 hàng
```

Trong PostgreSQL còn có biểu thức nhóm rỗng `GROUP BY ()` để yêu cầu nhóm tổng hợp toàn cục:

```sql
SELECT COUNT(*) AS row_count
FROM aggregation_null_lab
WHERE segment = 'Z'
GROUP BY ();
```

Trường hợp này tạo **một hàng** với `row_count = 0`. Cần phân biệt **nhóm tổng hợp toàn cục** với việc nhóm theo giá trị của một cột.

## 8. Muốn hiện cả nhóm không có giao dịch: dùng bảng danh mục và LEFT JOIN

Nếu báo cáo cần hiển thị A, B, C **và D**, `GROUP BY` trực tiếp trên bảng bán hàng không đủ. Hãy bắt đầu từ bảng **danh mục mọi nhóm cần báo cáo**, rồi dùng `LEFT JOIN` để giữ lại các nhóm chưa có giao dịch.

```sql
SELECT
    d.segment,
    COUNT(f.sale_id) AS sale_rows,
    COUNT(f.amount)  AS known_amount_rows,
    SUM(f.amount)    AS total_amount,
    AVG(f.amount)    AS average_amount
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Kết quả:

| `segment` | `sale_rows` | `known_amount_rows` | `total_amount` | `average_amount` |
| --- | ---: | ---: | ---: | ---: |
| A | 3 | 2 | 100.00 | 50.00 |
| B | 2 | 0 | `NULL` | `NULL` |
| C | 2 | 2 | 0.00 | 0.00 |
| D | 0 | 0 | `NULL` | `NULL` |

Nhóm D có mặt vì bảng `aggregation_segments_lab` có một hàng D, còn bảng `aggregation_null_lab` không có hàng khớp.

### Vì sao COUNT(*) có thể đánh lừa khi LEFT JOIN?

Xét cách viết:

```sql
SELECT d.segment,
       COUNT(*)         AS joined_rows,
       COUNT(f.sale_id) AS actual_sale_rows
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Với nhóm D:

- `COUNT(*) = 1` vì `LEFT JOIN` vẫn tạo **một hàng kết quả của phép nối** cho D, trong đó cột phía phải là `NULL`.
- `COUNT(f.sale_id) = 0` vì không có bản ghi bán hàng thật; `f.sale_id` là khóa chính không `NULL` của bảng bán hàng nên giá trị `NULL` sau join biểu thị không khớp.

Nếu nghiệp vụ muốn đếm **số giao dịch thực**, phải đếm một cột bên phải không thể `NULL` trên hàng thật, chẳng hạn khóa chính `f.sale_id`, không đếm mọi hàng của phép nối.

### Phân biệt không có giao dịch, toàn NULL và tổng bằng 0

```sql
SELECT d.segment,
       COUNT(f.sale_id) AS sale_rows,
       COUNT(f.amount) AS known_amount_rows,
       SUM(f.amount) AS total_amount,
       CASE
           WHEN COUNT(f.sale_id) = 0 THEN 'no_sales'
           WHEN COUNT(f.amount) = 0 THEN 'all_amounts_missing'
           WHEN SUM(f.amount) = 0 THEN 'known_total_zero'
           ELSE 'known_total_nonzero'
       END AS data_status
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Kết quả trạng thái:

| Nhóm | `data_status` |
| --- | --- |
| A | `known_total_nonzero` |
| B | `all_amounts_missing` |
| C | `known_total_zero` |
| D | `no_sales` |

Điều kiện được kiểm tra theo thứ tự phù hợp để không gộp nhóm D và B:

1. Không có bản ghi bán hàng thật → `no_sales`.
2. Có bản ghi nhưng không có giá trị số nào → `all_amounts_missing`.
3. Có giá trị số, tổng bằng 0 → `known_total_zero`.
4. Các trường hợp còn lại → `known_total_nonzero`.

Nhóm A có cả `NULL` nhưng vẫn có hai số đã biết; trạng thái chỉ nói tổng hiện tính được là 100. Nếu báo cáo yêu cầu **tất cả bản ghi phải có số tiền** mới được công nhận tổng đầy đủ, cần thêm kiểm tra `COUNT(f.amount) = COUNT(f.sale_id)` trước khi chấp nhận tổng.

## 9. COALESCE(SUM(...), 0) có ý nghĩa gì?

`COALESCE(expression, fallback)` trả kết quả đầu tiên khác `NULL`. Vì vậy:

```sql
SELECT COALESCE(SUM(amount), 0) AS total_display
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Trả **0** thay cho `SUM(amount) = NULL` trong trường hợp đầu vào rỗng.

Với nhóm B (toàn `NULL`), biểu thức cũng trả **0**:

```sql
SELECT COALESCE(SUM(amount), 0) AS total_display
FROM aggregation_null_lab
WHERE segment = 'B';
```

Đây là lựa chọn có thể chấp nhận **nếu nghiệp vụ quy định dùng 0 khi không có tổng**. Nhưng nếu dữ liệu chưa đồng bộ mà báo cáo hiển thị 0 như một tổng xác nhận, người đọc có thể bị đánh lừa.

### COALESCE(SUM(amount), 0) khác SUM(COALESCE(amount, 0))

Hai cách viết nhìn giống nhau nhưng tác động ở **thời điểm khác nhau**:

```sql
-- Thay NULL của kết quả tổng hợp
COALESCE(SUM(amount), 0)

-- Thay NULL từng hàng rồi mới tính tổng
SUM(COALESCE(amount, 0))
```

So sánh ba tình huống:

| Nguồn đầu vào | `COALESCE(SUM(amount),0)` | `SUM(COALESCE(amount,0))` |
| --- | ---: | ---: |
| 0 hàng | 0 | `NULL` |
| 2 hàng toàn `NULL` | 0 | 0 |
| 2 hàng: `NULL` và `10` | 10 | 10 |

Vì sao cách thứ hai vẫn trả `NULL` khi nguồn rỗng? Vì không có **bất cứ hàng nào** để chạy `COALESCE(amount,0)`, nên `SUM` vẫn nhận tập giá trị rỗng và trả `NULL`.

Có thể quan sát trực tiếp bằng PostgreSQL:

```sql
SELECT
    COALESCE(SUM(amount), 0) AS fallback_after_sum,
    SUM(COALESCE(amount, 0)) AS fallback_before_sum
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Kết quả: `0` và `NULL`.

### COALESCE bên trong AVG làm đổi mẫu số

```sql
SELECT
    AVG(amount) AS avg_known_only,
    AVG(COALESCE(amount, 0)) AS avg_treat_missing_as_zero
FROM aggregation_null_lab
WHERE segment = 'A';
```

Với nhóm A: `amount = [100, NULL, 0]`.

- `AVG(amount) = (100 + 0) / 2 = 50`.
- `AVG(COALESCE(amount, 0)) = (100 + 0 + 0) / 3 ≈ 33.33`.

Vì vậy, `COALESCE` đặt **trước** hàm tổng hợp có thể thay đổi ý nghĩa thống kê. Chỉ áp dụng khi nghiệp vụ xác nhận rằng một giá trị thiếu nên được tính như 0.

### Một chính sách hiển thị tinh tế hơn

Giả sử yêu cầu:

- Nhóm **không có giao dịch**: hiển thị tổng **0**.
- Nhóm **có giao dịch nhưng toàn bộ số tiền thiếu**: để `NULL` để báo chưa đủ dữ liệu.
- Nhóm có ít nhất một số tiền: hiển thị tổng các số đã biết.

Có thể viết:

```sql
SELECT d.segment,
       CASE
           WHEN COUNT(f.sale_id) = 0 THEN 0::NUMERIC
           ELSE SUM(f.amount)
       END AS report_amount
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Kết quả: A = 100, B = `NULL`, C = 0, D = 0. Đây là một **chính sách báo cáo được định nghĩa rõ**, không phải quy tắc ngầm của `SUM`.

## 10. COUNT(DISTINCT), SUM(DISTINCT) và giá trị NULL

Từ khóa `DISTINCT` trong các hàm tổng hợp phù hợp cho phép tính không lặp giá trị:

```sql
SELECT
    COUNT(amount) AS known_count,
    COUNT(DISTINCT amount) AS distinct_known_count,
    SUM(amount) AS sum_all,
    SUM(DISTINCT amount) AS sum_distinct_values
FROM aggregation_null_lab;
```

Trong dữ liệu mẫu, giá trị `amount` khác `NULL` là `100, 0, 0, 0`:

- `COUNT(amount) = 4`.
- `COUNT(DISTINCT amount) = 2`, vì chỉ có hai giá trị phân biệt là 100 và 0.
- `SUM(amount) = 100`.
- `SUM(DISTINCT amount) = 100`.

`COUNT(DISTINCT amount)` **không xem `NULL` là một giá trị đếm được**. Trên tập rỗng hoặc tập toàn `NULL`, kết quả `COUNT(DISTINCT amount)` vẫn là `0`.

Còn `SUM(DISTINCT amount)` trong hai trường hợp đó vẫn là `NULL`, không phải 0. `DISTINCT` không thay đổi quy tắc của `SUM` khi không có giá trị số hợp lệ để cộng.

**Lưu ý nghiệp vụ:** `SUM(DISTINCT amount)` cộng các **giá trị tiền khác nhau**, không phải cộng các giao dịch khác nhau. Nếu hai giao dịch cùng số tiền 100, chúng thường vẫn phải được tính hai lần vào doanh thu; dùng `DISTINCT` để “loại trùng giao dịch” có thể làm báo cáo sai.

## 11. FILTER: một điều kiện có thể khiến đầu vào của từng hàm rỗng

Trong PostgreSQL, `FILTER (WHERE condition)` chỉ đưa các hàng thỏa điều kiện vào **hàm tổng hợp cụ thể**.

```sql
SELECT
    COUNT(*) FILTER (WHERE amount > 1000)
        AS number_of_large_sales,
    SUM(amount) FILTER (WHERE amount > 1000)
        AS large_sales_total,
    AVG(amount) FILTER (WHERE amount > 1000)
        AS large_sales_average
FROM aggregation_null_lab;
```

Không có hàng nào có `amount > 1000`. Cả ba hàm đều nhận đầu vào rỗng:

| `number_of_large_sales` | `large_sales_total` | `large_sales_average` |
| ---: | ---: | ---: |
| 0 | `NULL` | `NULL` |

**Một bảng có nhiều hàng vẫn có thể tạo đầu vào rỗng cho từng hàm** vì `FILTER` đặt sau lời gọi hàm.

### FILTER theo từng nhóm

```sql
SELECT segment,
       COUNT(*) AS all_rows,
       COUNT(*) FILTER (WHERE amount > 0) AS positive_rows,
       SUM(amount) FILTER (WHERE amount > 0) AS positive_total
FROM aggregation_null_lab
GROUP BY segment
ORDER BY segment;
```

Kết quả:

| Nhóm | `all_rows` | `positive_rows` | `positive_total` |
| --- | ---: | ---: | ---: |
| A | 3 | 1 | 100.00 |
| B | 2 | 0 | `NULL` |
| C | 2 | 0 | `NULL` |

Nhóm C có hai số 0 thật, nhưng điều kiện `amount > 0` loại cả hai. `SUM` của tập con “giá trị dương” trở thành `NULL`, dù `SUM(amount)` của cả nhóm C bằng 0.

Khi phân tích báo cáo, phải hỏi **“đầu vào của phép tổng hợp nào đang rỗng?”**, không chỉ “bảng có rỗng không?”.

### COUNT với CASE và SUM với CASE

Một cách đếm có điều kiện trên nhiều DBMS là:

```sql
SELECT
    COUNT(CASE WHEN amount > 0 THEN 1 END) AS positive_by_count,
    SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) AS positive_by_sum
FROM aggregation_null_lab;
```

Hai biểu thức trên đều cho **1** trên bảng hiện tại. Nhưng nếu nguồn có **0 hàng**:

```sql
SELECT
    COUNT(CASE WHEN amount > 0 THEN 1 END) AS positive_by_count,
    SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) AS positive_by_sum
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Kết quả là `0` và `NULL`.

Lý do:

- `COUNT(...)` trả 0 nếu không có kết quả khác `NULL`.
- `SUM(...)` trả `NULL` nếu không có hàng đầu vào để cộng, **kể cả biểu thức `CASE` có `ELSE 0`**.

Cần đặt `COALESCE` ở ngoài `SUM` nếu chính sách yêu cầu 0 trong trường hợp đầu vào rỗng:

```sql
SELECT COALESCE(
    SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END),
    0
) AS positive_rows
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Kết quả là `0`. Tuy nhiên, `COUNT(*) FILTER (WHERE amount > 0)` thường diễn đạt phép đếm rõ hơn trong PostgreSQL.

Một lỗi khác:

```sql
-- Không đúng nếu mục đích là đếm số hàng amount > 0
COUNT(CASE WHEN amount > 0 THEN 1 ELSE 0 END)
```

Vì cả `1` và `0` đều khác `NULL`, biểu thức này đếm **mọi hàng nguồn**, không chỉ những hàng thỏa điều kiện.

## 12. HAVING có thể loại bỏ hàng tổng hợp toàn cục

`WHERE` lọc **hàng nguồn** trước khi tổng hợp; `HAVING` lọc **nhóm sau khi tổng hợp**.

Truy vấn này trả một hàng với `COUNT(*) = 0`:

```sql
SELECT COUNT(*) AS row_count
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Nhưng nếu thêm điều kiện `HAVING`:

```sql
SELECT COUNT(*) AS row_count
FROM aggregation_null_lab
WHERE segment = 'Z'
HAVING COUNT(*) > 0;
```

Truy vấn trả **0 hàng**, vì nhóm tổng hợp toàn cục có `COUNT(*) = 0`, không thỏa `HAVING`.

Tương tự:

```sql
SELECT segment, SUM(amount) AS total_amount
FROM aggregation_null_lab
GROUP BY segment
HAVING SUM(amount) > 0
ORDER BY segment;
```

Kết quả chỉ có nhóm A:

- Nhóm A có `SUM(amount) = 100`, điều kiện TRUE.
- Nhóm B có `SUM(amount) = NULL`, điều kiện `NULL > 0` là UNKNOWN nên bị loại.
- Nhóm C có `SUM(amount) = 0`, điều kiện FALSE nên bị loại.

Nếu muốn tìm nhóm **có hàng nhưng chưa có bất kỳ số tiền nào**, hãy dùng:

```sql
SELECT segment, COUNT(*) AS sale_rows
FROM aggregation_null_lab
GROUP BY segment
HAVING COUNT(amount) = 0
ORDER BY segment;
```

Kết quả là nhóm **B**. Nhóm D vẫn không xuất hiện vì `GROUP BY` bảng bán hàng không tạo nhóm D. Muốn tìm thêm nhóm không có giao dịch, cần bắt đầu từ bảng danh mục và `LEFT JOIN`.

## 13. NULL ở khóa nhóm không đồng nghĩa không có nhóm

Một điểm dễ nhầm: `NULL` ở **cột dùng trong GROUP BY** không làm hàng biến mất. Những hàng có khóa nhóm `NULL` có thể được đặt vào **một nhóm chung**.

```sql
WITH events(category, amount) AS (
    VALUES
        (NULL::TEXT, 10::NUMERIC),
        (NULL::TEXT, NULL::NUMERIC),
        ('known'::TEXT, 5::NUMERIC)
)
SELECT category,
       COUNT(*) AS row_count,
       COUNT(amount) AS known_count,
       SUM(amount) AS total
FROM events
GROUP BY category
ORDER BY category NULLS LAST;
```

Kết quả có hai nhóm:

| `category` | `row_count` | `known_count` | `total` |
| --- | ---: | ---: | ---: |
| `known` | 1 | 1 | 5 |
| `NULL` | 2 | 1 | 10 |

Các giá trị khóa `NULL` được gom với nhau trong `GROUP BY`, dù phép so sánh thông thường `NULL = NULL` không trả TRUE. Đây là quy tắc gom nhóm, không phải thay đổi quy tắc so sánh bằng trong `WHERE`.

**Hai việc khác nhau:**

- `GROUP BY category` khi `category IS NULL` vẫn có thể tạo một nhóm.
- `SUM(amount)` của nhóm đó vẫn bỏ qua `amount IS NULL` khi tính.

Vì thế “nhóm có khóa `NULL`” không có nghĩa “đầu vào nhóm rỗng” hoặc “các giá trị đo đều `NULL`”.

## 14. Một số hàm tổng hợp khác có đặc điểm riêng

Không phải mọi hàm tổng hợp trả `NULL` cho **tập toàn `NULL`** theo cùng một cách. Cần phân biệt hàm **bỏ qua `NULL`** với hàm có thể **giữ `NULL` như một phần tử được thu thập**.

### STRING_AGG: ghép các chuỗi khác NULL

Trong PostgreSQL:

```sql
SELECT STRING_AGG(description, ' | ' ORDER BY sale_id) AS notes
FROM aggregation_null_lab
WHERE segment = 'A';
```

`STRING_AGG` nối các giá trị văn bản khác `NULL`. Nếu không có giá trị văn bản hợp lệ (tập rỗng hoặc mọi biểu thức là `NULL`), kết quả thường là `NULL`.

Thử nguồn rỗng:

```sql
SELECT STRING_AGG(description, ', ') AS combined
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Kết quả là `NULL`, không phải chuỗi rỗng `''`.

### ARRAY_AGG: có thể giữ phần tử NULL

PostgreSQL `ARRAY_AGG` thu thập giá trị vào một mảng. Nếu có hai hàng đều `NULL`, mảng có thể chứa **hai phần tử `NULL`**:

```sql
SELECT ARRAY_AGG(amount ORDER BY sale_id) AS amounts
FROM aggregation_null_lab
WHERE segment = 'B';
```

Kết quả là một mảng có hai phần tử `NULL`, được client PostgreSQL có thể hiển thị tương tự `{NULL,NULL}`.

Nhưng với nguồn hoàn toàn không có hàng:

```sql
SELECT ARRAY_AGG(amount) AS amounts
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Kết quả là **`NULL`**, không phải mảng rỗng theo mặc định của PostgreSQL.

Để yêu cầu mảng rỗng cho nguồn rỗng, có thể dùng:

```sql
SELECT COALESCE(
           ARRAY_AGG(amount),
           ARRAY[]::NUMERIC[]
       ) AS amounts
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Kết quả là mảng rỗng. Với nhóm B, vì `ARRAY_AGG` đã có một mảng chứa hai giá trị `NULL`, `COALESCE` **không** biến nó thành mảng rỗng.

Muốn loại phần tử `NULL` khỏi mảng:

```sql
SELECT COALESCE(
           ARRAY_AGG(amount ORDER BY sale_id)
               FILTER (WHERE amount IS NOT NULL),
           ARRAY[]::NUMERIC[]
       ) AS known_amounts
FROM aggregation_null_lab
WHERE segment = 'B';
```

Kết quả là mảng rỗng vì cả hai giá trị `amount` đều thiếu và bộ lọc đã loại chúng.

### JSON_AGG: NULL có thể trở thành phần tử JSON

PostgreSQL cũng có `JSON_AGG`, có thể thu thập các giá trị SQL `NULL` thành phần tử `null` trong mảng JSON:

```sql
SELECT JSON_AGG(amount ORDER BY sale_id) AS amounts_json
FROM aggregation_null_lab
WHERE segment = 'B';
```

Kết quả mang nội dung tương tự `[null, null]`. Nếu không có hàng nguồn, `JSON_AGG` trả SQL `NULL`. Hai kết quả **mảng chứa các phần tử null** và **SQL NULL** không giống nhau.

Các hàm JSON mới hoặc biến thể với quy tắc bỏ qua `NULL` có thể có cú pháp khác tùy DBMS và phiên bản. Không nên suy từ quy tắc của `SUM` rằng mọi hàm tổng hợp sẽ bỏ qua `NULL` giống nhau.

### BOOL_AND và BOOL_OR trong PostgreSQL

Với một tập boolean, PostgreSQL hỗ trợ `BOOL_AND` và `BOOL_OR`. Chúng bỏ qua các giá trị `NULL` khi có giá trị boolean xác định:

```sql
WITH checks(ok) AS (
    VALUES (TRUE), (NULL::BOOLEAN), (FALSE)
)
SELECT BOOL_AND(ok) AS all_ok,
       BOOL_OR(ok)  AS any_ok
FROM checks;
```

Kết quả: `all_ok = FALSE` và `any_ok = TRUE`.

Nếu đầu vào **không có giá trị boolean khác `NULL`**, ví dụ toàn `NULL` hoặc không có hàng, kết quả của hai hàm trong PostgreSQL là `NULL`. Đừng mặc định rằng `BOOL_AND` trên tập rỗng trả TRUE hoặc `BOOL_OR` trả FALSE theo một quy ước toán học khác.

## 15. Hàm tổng hợp dạng cửa sổ và đầu vào rỗng

Hàm tổng hợp có thể xuất hiện dưới dạng **window function**, ví dụ `SUM(amount) OVER ()`:

```sql
SELECT sale_id,
       amount,
       COUNT(*) OVER () AS all_rows,
       SUM(amount) OVER () AS grand_total
FROM aggregation_null_lab
ORDER BY sale_id;
```

Kết quả vẫn có **7 hàng**; mỗi hàng có thêm tổng số dòng bằng 7 và tổng tiền đã biết bằng 100.

Nếu điều kiện `WHERE` loại hết hàng:

```sql
SELECT sale_id,
       COUNT(*) OVER () AS all_rows,
       SUM(amount) OVER () AS grand_total
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Truy vấn trả **0 hàng**, không có “một hàng tổng hợp 0/NULL” như với hàm tổng hợp toàn cục. Vì **window function tính trên các hàng kết quả còn tồn tại**; không có hàng nào để gắn giá trị cửa sổ, thì không có hàng đầu ra.

Tương tự, với một phân hoạch có hàng nhưng `amount` toàn `NULL`:

```sql
SELECT sale_id,
       segment,
       amount,
       COUNT(amount) OVER (PARTITION BY segment)
           AS known_values_in_segment,
       SUM(amount) OVER (PARTITION BY segment)
           AS segment_total
FROM aggregation_null_lab
WHERE segment = 'B'
ORDER BY sale_id;
```

Trả **2 hàng**: mỗi hàng có `known_values_in_segment = 0` và `segment_total = NULL`.

Cần phân biệt **hàm tổng hợp thông thường làm thay đổi số hàng kết quả** với **hàm cửa sổ gắn kết quả vào các hàng hiện có**.

## 16. Trung bình và tỷ lệ: tránh chia cho 0 khi không có giá trị

Với một tập có các số khác `NULL`, `AVG(amount)` về mặt ý nghĩa tương ứng với:

\[
\operatorname{AVG}(amount)
=
\frac{\operatorname{SUM}(amount)}
{\operatorname{COUNT}(amount)}
\]

Nhưng khi `COUNT(amount) = 0`, phép chia không được xác định. Trong SQL, **`AVG(amount)` trả `NULL`** cho tập toàn `NULL` hoặc rỗng. Nếu tự viết công thức, phải bảo vệ mẫu số:

```sql
SELECT
    AVG(amount) AS built_in_average,
    SUM(amount) / NULLIF(COUNT(amount), 0)
        AS average_with_safe_division
FROM aggregation_null_lab
WHERE segment = 'B';
```

Cả hai trả `NULL`. `NULLIF(COUNT(amount), 0)` tạo mẫu số `NULL` khi số giá trị đã biết bằng 0, tránh lỗi chia cho 0.

Đối với dữ liệu tiền tệ cần phần thập phân, hãy chú ý kiểu số của phép chia. Trong PostgreSQL, `AVG` của `NUMERIC` trả `NUMERIC`; nếu tự chia hai số nguyên, phép chia nguyên có thể làm mất phần lẻ.

### Không nên dùng COUNT(*) thay COUNT(amount) mà không có lý do

```sql
SELECT
    SUM(amount) / NULLIF(COUNT(*), 0)
        AS average_per_record,
    AVG(amount)
        AS average_of_known_amounts
FROM aggregation_null_lab
WHERE segment = 'A';
```

Với nhóm A:

- `average_per_record = 100 / 3 ≈ 33.33`.
- `average_of_known_amounts = 100 / 2 = 50`.

Hai phép tính trả lời hai câu hỏi khác nhau:

- **Bình quân trên mọi bản ghi**: muốn coi các bản ghi thiếu `amount` như không đóng góp vào tổng nhưng vẫn tính vào mẫu số, cần quy định nghiệp vụ như vậy một cách rõ ràng.
- **Trung bình các số tiền đã biết**: dùng `AVG(amount)`; hàng có `amount = NULL` không tính vào mẫu số.

Nếu tình trạng thiếu dữ liệu nghĩa là “chưa đồng bộ”, cả hai con số có thể chưa đủ để khẳng định một chỉ tiêu tài chính chính thức. Nên kèm tỷ lệ hoàn thiện dữ liệu, chẳng hạn `COUNT(amount)` so với `COUNT(*)`.

## 17. Thiết kế báo cáo: giữ ý nghĩa của NULL nhưng vẫn hỗ trợ hiển thị

Một báo cáo đáng tin cậy nên tách **giá trị tính toán** khỏi **trạng thái dữ liệu**. Có thể cung cấp:

- `sale_rows`: số giao dịch thực.
- `known_amount_rows`: số giao dịch có tiền đã biết.
- `total_amount`: tổng các số tiền đã biết, có thể `NULL`.
- `data_status`: lý do không có tổng hoặc mức độ đầy đủ.
- `display_amount`: giá trị thay thế dùng riêng cho một giao diện, nếu nghiệp vụ yêu cầu.

Ví dụ:

```sql
SELECT
    d.segment,
    COUNT(f.sale_id) AS sale_rows,
    COUNT(f.amount) AS known_amount_rows,
    SUM(f.amount) AS total_amount,
    CASE
        WHEN COUNT(f.sale_id) = 0 THEN 'no_sales'
        WHEN COUNT(f.amount) = 0 THEN 'all_amounts_missing'
        WHEN COUNT(f.amount) < COUNT(f.sale_id)
            THEN 'partially_missing'
        ELSE 'complete'
    END AS data_status,
    COALESCE(SUM(f.amount), 0) AS display_amount
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Kết quả về mặt ý nghĩa:

| Nhóm | `sale_rows` | `known_amount_rows` | `total_amount` | `data_status` | `display_amount` |
| --- | ---: | ---: | ---: | --- | ---: |
| A | 3 | 2 | 100 | partially_missing | 100 |
| B | 2 | 0 | `NULL` | all_amounts_missing | 0 |
| C | 2 | 2 | 0 | complete | 0 |
| D | 0 | 0 | `NULL` | no_sales | 0 |

**Cột `display_amount` không thay thế cột `total_amount` và `data_status`.** Nhờ giữ cả ba, ứng dụng biết 0 của nhóm C là giá trị xác định, 0 của nhóm D là số hiển thị cho tình trạng không có giao dịch, còn 0 của nhóm B chỉ là giá trị thay thế trong khi dữ liệu tiền hoàn toàn thiếu.

### Cách giải thích trong nghiệp vụ

- **Nhóm A:** đã có 100 tiền được ghi nhận, nhưng còn một giao dịch chưa có số tiền; tổng này **chưa chắc đầy đủ**.
- **Nhóm B:** có hai giao dịch mà không biết số tiền; không nên kết luận doanh thu thực bằng 0.
- **Nhóm C:** có hai giao dịch với số tiền đã ghi là 0; giá trị tổng bằng 0.
- **Nhóm D:** không có giao dịch trong dữ liệu nguồn; nếu báo cáo chọn quy ước, tổng của nhóm không có hoạt động có thể hiển thị 0.

Một API nên cân nhắc trả `null` cho số liệu không xác định và một trường trạng thái thay vì ép mọi trường hợp thành 0.

## 18. Những khác biệt cần nhớ giữa các DBMS

Các quy tắc `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` khi không có giá trị số hợp lệ là ngữ nghĩa SQL rất phổ biến. Tuy nhiên, một số hàm riêng và cách biểu diễn kết quả khác nhau theo hệ quản trị.

| Chủ đề | PostgreSQL | Lưu ý khi chuyển hệ |
| --- | --- | --- |
| `COUNT(*)` với nguồn rỗng, không `GROUP BY` | `0` | Hành vi nền tảng phổ biến của SQL |
| `COUNT(column)` khi toàn `NULL` | `0` | Các giá trị `NULL` bị bỏ qua |
| `SUM/AVG/MIN/MAX` khi không có giá trị khác `NULL` | `NULL` | Hành vi phổ biến; cần phân biệt với hàm đặc thù |
| `GROUP BY category` với nguồn rỗng | 0 hàng | Không tạo nhóm từ dữ liệu không tồn tại |
| `FILTER (WHERE ...)` | Có hỗ trợ | Không phải DBMS/phiên bản nào cũng hỗ trợ cùng cú pháp; có thể dùng `CASE` |
| `ARRAY_AGG`, `JSON_AGG` | Có thể thu thập phần tử `NULL` | Quy tắc JSON/array khác nhau theo DBMS và biến thể hàm |
| Hàm cộng có kết quả 0 ngay cả khi rỗng | `SUM` không mặc định làm vậy | **SQLite có hàm `total(x)` riêng**, trả `0.0` khi không có giá trị khác `NULL`; `sum(x)` của SQLite vẫn trả `NULL` |
| Giá trị NULL ở khóa GROUP BY | Những khóa `NULL` được gom cùng nhóm | Cách xử lý định danh nhóm có thể khác với phép so sánh thông thường trong `WHERE` |

Đặc biệt ở SQLite:

```sql
-- SQLite
SELECT SUM(x), TOTAL(x)
FROM (SELECT 1 AS x WHERE 1 = 0);
```

`SUM(x)` cho `NULL`, còn `TOTAL(x)` cho `0.0`. `TOTAL` là hàm mở rộng của SQLite, **không phải** lý do để suy ra `SUM` trên SQL nói chung trả 0.

Ngoài ra, kiểu kết quả có thể khác nhau: `COUNT` ở SQL Server thường trả `int` trong nhiều ngữ cảnh và có giới hạn riêng; PostgreSQL `COUNT` trả `bigint`. Hàm `AVG` với kiểu integer cũng có kiểu kết quả khác nhau giữa các hệ. Khi xuất dữ liệu qua driver, cần kiểm tra metadata kiểu số và chính sách tràn số của DBMS đang dùng.

## 19. Các lỗi thường gặp

| Cách viết hoặc hiện tượng | Vấn đề thực tế | Hướng xử lý |
| --- | --- | --- |
| `SUM(amount)` trả `NULL` dù bảng có dòng | Có thể mọi `amount` trong phạm vi truy vấn đều là `NULL` | Xem `COUNT(*)` và `COUNT(amount)` |
| `SUM(amount)` trả `NULL` khi không có giao dịch | SQL không mặc định dùng tổng tập rỗng bằng 0 | Dùng `COALESCE(SUM(amount),0)` nếu nghiệp vụ cho phép |
| `AVG(amount)` khác `SUM(amount)/COUNT(*)` | `AVG` chỉ tính các giá trị khác `NULL` | Chọn đúng mẫu số nghiệp vụ |
| `SUM(COALESCE(amount,0))` vẫn trả `NULL` | Không có hàng nào để chạy `COALESCE` | Nếu cần, bọc cả `SUM` bằng `COALESCE` |
| `COALESCE(SUM(amount),0)` làm thiếu tiền thành 0 | Gộp tập rỗng và tập toàn `NULL` | Giữ thêm `COUNT(*)`, `COUNT(amount)` hoặc trạng thái dữ liệu |
| `GROUP BY segment` không thấy nhóm D | D không có giao dịch nên không tạo nhóm | Dùng bảng danh mục và `LEFT JOIN` |
| `COUNT(*)` sau `LEFT JOIN` đếm nhóm D là 1 | Hàng bên trái vẫn được giữ sau nối | Dùng `COUNT(f.primary_key)` để đếm hàng phải thực |
| `SUM(...) FILTER (...)` trả `NULL` dù nhóm có hàng | Bộ lọc của hàm đã loại hết các hàng có ích | Kiểm tra điều kiện `FILTER` |
| `COUNT(CASE WHEN p THEN 1 ELSE 0 END)` đếm quá nhiều | Cả 0 và 1 đều khác `NULL` | Dùng `COUNT(CASE WHEN p THEN 1 END)` hoặc `COUNT(*) FILTER (WHERE p)` |
| `HAVING SUM(amount) > 0` loại nhóm toàn `NULL` | `NULL > 0` là UNKNOWN | Viết điều kiện theo mục tiêu, có thể kiểm tra `COUNT(amount)` |
| `ARRAY_AGG` cho mảng chứa `NULL` | Hàm thu thập cả phần tử `NULL` | Dùng `FILTER (WHERE x IS NOT NULL)` nếu muốn loại phần tử |
| Window aggregate không trả hàng tổng khi nguồn rỗng | Không có hàng kết quả để gắn giá trị cửa sổ | Dùng tổng hợp toàn cục nếu cần một hàng kết quả |
| Đếm thiếu dữ liệu bằng `COUNT(column)` | `COUNT(column)` đếm giá trị **có**, không phải **thiếu** | Dùng `COUNT(*) - COUNT(column)` hoặc `COUNT(*) FILTER (WHERE column IS NULL)` |

## 20. Bài tập tự luyện

Các bài sau sử dụng PostgreSQL và hai bảng tạm `aggregation_null_lab`, `aggregation_segments_lab` của mục 3. Hãy dự đoán số hàng kết quả **trước khi** dự đoán giá trị của từng cột.

### Bài 1: Tổng hợp trên nguồn rỗng

Với điều kiện `segment = 'Z'`, tính:

- `COUNT(*)`;
- `COUNT(amount)`;
- `SUM(amount)`;
- `AVG(amount)`.

Câu truy vấn có `GROUP BY` hay không? Có bao nhiêu hàng kết quả?

### Bài 2: Tổng hợp nhóm toàn NULL

Lọc `segment = 'B'`. Tại sao `COUNT(*) = 2` nhưng `COUNT(amount) = 0`? `SUM(amount)` và `AVG(amount)` trả gì?

### Bài 3: Tổng hợp nhóm chứa số 0

Lọc `segment = 'C'`. So sánh kết quả `SUM(amount)` với nhóm B. Chỉ ra lý do một nhóm trả số 0 và nhóm kia trả `NULL`.

### Bài 4: GROUP BY khi không có hàng

So sánh số hàng của hai câu:

```sql
SELECT COUNT(*) FROM aggregation_null_lab WHERE segment = 'Z';

SELECT segment, COUNT(*)
FROM aggregation_null_lab
WHERE segment = 'Z'
GROUP BY segment;
```

Vì sao hai câu khác nhau dù có cùng điều kiện lọc?

### Bài 5: Hiển thị cả nhóm D

Viết câu `LEFT JOIN` để trả cả A, B, C, D, với hai cột `sale_rows` và `known_amount_rows`. Tại sao cần `COUNT(f.sale_id)` thay vì `COUNT(*)`?

### Bài 6: Gắn trạng thái dữ liệu

Trả `segment` và `data_status` theo quy tắc:

- Không có giao dịch: `no_sales`.
- Có giao dịch nhưng mọi `amount` đều `NULL`: `all_missing`.
- Có giao dịch, có tiền đã biết và tổng bằng 0: `total_zero`.
- Còn lại: `total_nonzero`.

Sử dụng `CASE` cùng `COUNT`, `SUM`.

### Bài 7: COALESCE ở trong hay ngoài?

Với nguồn rỗng (lọc `segment = 'Z'`), dự đoán hai biểu thức:

```sql
COALESCE(SUM(amount), 0)
SUM(COALESCE(amount, 0))
```

Giải thích tại sao kết quả không giống nhau.

### Bài 8: Trung bình của nhóm A

Tính `AVG(amount)` và `AVG(COALESCE(amount,0))` cho nhóm A. Kết quả nào phù hợp nếu `NULL` mang nghĩa “số tiền chưa đồng bộ”?

### Bài 9: COUNT và SUM có điều kiện

Với tập nguồn rỗng, so sánh:

```sql
COUNT(CASE WHEN amount > 0 THEN 1 END)

SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END)
```

Biểu thức nào trả `0`, biểu thức nào trả `NULL`? Hãy viết cách khiến phép `SUM` trả 0 nếu yêu cầu báo cáo quy định như vậy.

### Bài 10: ARRAY_AGG toàn NULL

Với nhóm B, `ARRAY_AGG(amount)` trả gì về cấu trúc? Với nguồn `segment = 'Z'`, hàm trả gì? Viết biểu thức trả mảng rỗng khi không có giá trị khác `NULL`.

### Bài 11: Tỷ lệ hoàn thiện dữ liệu

Với mỗi nhóm A, B, C, D, tính tỷ lệ số tiền đã biết trên số giao dịch thực. Yêu cầu:

- Nếu không có giao dịch, tỷ lệ là `NULL` vì không có mẫu số.
- Nếu có giao dịch nhưng số tiền đều thiếu, tỷ lệ là 0.
- Nếu tất cả giao dịch có số tiền, tỷ lệ là 1.

Chọn mẫu số đúng khi có `LEFT JOIN` và dùng `NULLIF` để tránh chia cho 0.

### Bài 12: HAVING và nhóm toàn NULL

Viết câu truy vấn lấy các nhóm có giao dịch nhưng `COUNT(amount) = 0`. Vì sao nhóm D không xuất hiện khi chỉ dùng `GROUP BY` trên bảng bán hàng?

## 21. Gợi ý đáp án

**Bài 1:**

```sql
SELECT COUNT(*) AS rows_count,
       COUNT(amount) AS known_count,
       SUM(amount) AS amount_sum,
       AVG(amount) AS amount_average
FROM aggregation_null_lab
WHERE segment = 'Z';
```

Một hàng kết quả: `0`, `0`, `NULL`, `NULL`.

**Bài 2:** Nhóm B có hai hàng thật nhưng cả hai `amount` đều `NULL`. Kết quả `COUNT(*) = 2`, `COUNT(amount) = 0`, `SUM(amount) = NULL`, `AVG(amount) = NULL`.

**Bài 3:** Nhóm C có hai giá trị đã biết bằng 0, nên `SUM(amount) = 0` và `COUNT(amount) = 2`. Nhóm B không có giá trị nào khác `NULL` nên `SUM(amount) = NULL`.

**Bài 4:** Câu không `GROUP BY` trả một hàng `COUNT(*) = 0`; câu `GROUP BY segment` trả không hàng nào vì không có nhóm `segment` được tạo.

**Bài 5:**

```sql
SELECT d.segment,
       COUNT(f.sale_id) AS sale_rows,
       COUNT(f.amount) AS known_amount_rows
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Nhóm D có một hàng của kết quả `LEFT JOIN` nhưng không có hàng bán hàng thực, vì vậy `COUNT(*)` sẽ là 1 còn `COUNT(f.sale_id)` là 0.

**Bài 6:**

```sql
SELECT d.segment,
       CASE
           WHEN COUNT(f.sale_id) = 0 THEN 'no_sales'
           WHEN COUNT(f.amount) = 0 THEN 'all_missing'
           WHEN SUM(f.amount) = 0 THEN 'total_zero'
           ELSE 'total_nonzero'
       END AS data_status
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Kết quả: A = `total_nonzero`, B = `all_missing`, C = `total_zero`, D = `no_sales`.

**Bài 7:** `COALESCE(SUM(amount),0) = 0` còn `SUM(COALESCE(amount,0)) = NULL` khi nguồn rỗng, vì không có dòng nào để tạo giá trị 0 ở bên trong `SUM`.

**Bài 8:**

```sql
SELECT AVG(amount) AS known_average,
       AVG(COALESCE(amount,0)) AS missing_as_zero_average
FROM aggregation_null_lab
WHERE segment = 'A';
```

`known_average = 50`, còn `missing_as_zero_average ≈ 33.33`. Nếu `NULL` nghĩa là số tiền chưa đồng bộ, trung bình các giá trị đã biết là 50, nhưng cần ghi rõ còn dữ liệu chưa hoàn thiện; không nên tự xem nó là 0.

**Bài 9:** `COUNT(CASE WHEN ... THEN 1 END) = 0`; `SUM(CASE ... ELSE 0 END) = NULL` khi nguồn rỗng. Nếu có quy tắc thay kết quả rỗng bằng 0:

```sql
SELECT COALESCE(
    SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END),
    0
) AS positive_count
FROM aggregation_null_lab
WHERE segment = 'Z';
```

**Bài 10:** Với B, `ARRAY_AGG(amount)` trả mảng chứa hai phần tử `NULL`. Với Z, hàm trả SQL `NULL`. Muốn thu mảng **chỉ gồm giá trị đã biết**, mặc định mảng rỗng nếu không có:

```sql
SELECT COALESCE(
    ARRAY_AGG(amount ORDER BY sale_id)
        FILTER (WHERE amount IS NOT NULL),
    ARRAY[]::NUMERIC[]
) AS known_amounts
FROM aggregation_null_lab
WHERE segment = 'B';
```

**Bài 11:**

```sql
SELECT d.segment,
       COUNT(f.sale_id) AS sale_rows,
       COUNT(f.amount) AS known_amount_rows,
       COUNT(f.amount)::NUMERIC
           / NULLIF(COUNT(f.sale_id), 0) AS completeness_ratio
FROM aggregation_segments_lab AS d
LEFT JOIN aggregation_null_lab AS f
  ON f.segment = d.segment
GROUP BY d.segment
ORDER BY d.segment;
```

Kết quả: A = `2/3`, B = `0`, C = `1`, D = `NULL`. Mẫu số là `COUNT(f.sale_id)` vì cần đếm giao dịch thực, không phải số hàng sau `LEFT JOIN`.

**Bài 12:**

```sql
SELECT segment
FROM aggregation_null_lab
GROUP BY segment
HAVING COUNT(amount) = 0
ORDER BY segment;
```

Kết quả là B. D không có hàng nào trong bảng giao dịch để tạo nhóm; nếu muốn xét D phải nối với bảng danh mục.

## 22. Cách lựa chọn kết quả phù hợp với yêu cầu nghiệp vụ

Khi thiết kế một chỉ tiêu tổng hợp, hãy quyết định theo thứ tự:

1. **Nguồn có thể có 0 dòng không?** Ví dụ không có giao dịch trong ngày, tháng hoặc cho một khách hàng.
2. **Có thể có dòng nhưng cột đo toàn `NULL` không?** Ví dụ dữ liệu chưa đồng bộ hoặc số tiền chưa được xác nhận.
3. **Giá trị `0` có hợp lệ không?** Nếu có, nó cần được phân biệt với tình trạng thiếu.
4. **Báo cáo cần một hàng tổng hay một hàng cho từng nhóm?** Nếu mọi nhóm phải xuất hiện, cần nguồn danh mục để tạo nhóm thiếu dữ liệu.
5. **Phép tính nào cần giữ `NULL` và phép nào được phép thay bằng 0?** Hãy đặt quy tắc theo đúng ý nghĩa, thường ở lớp trình bày.
6. **Có cần báo mức độ hoàn thiện dữ liệu không?** `COUNT(*)`, `COUNT(expression)` và cột trạng thái là những tín hiệu quan trọng.
7. **Có điều kiện `FILTER`, `HAVING`, `LEFT JOIN` hoặc window function không?** Chúng có thể thay đổi tập đầu vào hay số hàng kết quả.

Điểm cần ghi nhớ là: **một kết quả `NULL` của `SUM` hoặc `AVG` không tự chứng minh bảng không có dòng; một kết quả bằng 0 cũng không tự chứng minh nguồn dữ liệu đã đầy đủ.** Khi cần phân biệt rõ, hãy xét đồng thời số hàng thực, số giá trị khác `NULL` và phép tính tổng hợp, rồi diễn đạt chính sách hiển thị phù hợp với yêu cầu nghiệp vụ.
