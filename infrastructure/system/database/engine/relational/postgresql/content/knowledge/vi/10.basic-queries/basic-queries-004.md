# Logic ba giá trị với NULL và IS DISTINCT FROM

Trong PostgreSQL, một điều kiện SQL không chỉ có hai kết quả `TRUE` và `FALSE`. Khi xuất hiện giá trị `NULL`, nhiều phép so sánh trả về trạng thái thứ ba: **`UNKNOWN` (chưa xác định)**. Đây là nền tảng của **logic ba giá trị (three-valued logic, 3VL)** trong SQL.

Nếu quen Java, bạn có thể kỳ vọng biểu thức so sánh luôn là một `boolean`. Nhưng trong SQL:

```sql
SELECT
    (1 = 1) AS true_case,
    (1 = 2) AS false_case,
    (1 = NULL::integer) AS unknown_case;
```

Kết quả cột cuối là **NULL của kiểu boolean**, biểu diễn `UNKNOWN`, chứ không phải `FALSE`.

Điều này ảnh hưởng trực tiếp tới `WHERE`, `JOIN`, `NOT IN`, `CASE`, `CHECK`, phép tổng hợp và cách ứng dụng tìm hàng có giá trị thiếu. PostgreSQL cung cấp toán tử **`IS DISTINCT FROM`** và **`IS NOT DISTINCT FROM`** để so sánh hai giá trị theo cách luôn trả `TRUE` hoặc `FALSE`, kể cả khi một trong hai hoặc cả hai là `NULL`.

Bài học thuộc chương *Truy vấn cơ bản*, tập trung vào cách viết điều kiện SQL đúng đắn, hiểu bảng chân trị, tránh những bẫy với `NULL` và chọn toán tử tương ứng với ý nghĩa nghiệp vụ. Các ví dụ có thể thực hành trên một PostgreSQL database thử nghiệm.

## 1. Hiểu đúng NULL trước khi viết điều kiện

`NULL` không phải một giá trị thông thường như số 0 hoặc chuỗi rỗng. Nó biểu diễn **sự thiếu vắng thông tin** theo mô hình dữ liệu SQL: chưa biết, chưa được cung cấp hoặc không áp dụng, tùy ý nghĩa của cột.

Phân biệt rõ:

| Biểu diễn | Ý nghĩa |
|---|---|
| `NULL` | Không có giá trị SQL được biết tại cột/biểu thức |
| `0` | Số không, là một giá trị cụ thể |
| `''` | Chuỗi rỗng, vẫn là một giá trị text |
| `'NULL'` | Chuỗi gồm bốn chữ cái N-U-L-L |
| `FALSE` | Giá trị boolean sai |
| `'1970-01-01'` | Một ngày cụ thể, không phải “ngày chưa biết” theo SQL |
| `DEFAULT` | Từ khóa yêu cầu dùng biểu thức mặc định trong các ngữ cảnh ghi dữ liệu cho phép |

Ví dụ:

```sql
SELECT
    NULL::text IS NULL AS missing_text,
    ''::text IS NULL AS empty_text_is_missing,
    0::integer IS NULL AS zero_is_missing,
    FALSE IS NULL AS false_is_missing;
```

Chỉ biểu thức đầu có kết quả `TRUE`.

**Ý nghĩa nghiệp vụ rất quan trọng.** Với `paid_at TIMESTAMPTZ`, `NULL` có thể mang nghĩa “chưa thanh toán”. Với `middle_name TEXT`, `NULL` có thể mang nghĩa “không khai báo tên đệm”. Không nên thay tất cả `NULL` bằng `0`, chuỗi `'N/A'` hoặc một ngày giả, vì các giá trị giả có thể gây sai số liệu hoặc che giấu thông tin chưa biết.

### 1.1. NULL không có nghĩa hàng không tồn tại

Một hàng có thể tồn tại hoàn toàn hợp lệ nhưng cột `email` hoặc `paid_at` là NULL:

```text
customer_id | full_name | email
------------+-----------+-----------------------
1           | Lan       | lan@example.test
2           | Minh      | NULL
3           | Hoa       | hoa@example.test
```

Điều kiện `email IS NULL` chọn **hàng đang tồn tại nhưng thiếu email**. Nó không phải cách xác định một hàng không được lưu trong bảng.

Với `LEFT JOIN`, PostgreSQL cũng có thể tạo các trường kết quả NULL khi **không có hàng khớp bên phải**; trường hợp này cần phân biệt với cột bên phải vốn đã NULL trong một hàng có thật.

## 2. Ba kết quả của biểu thức boolean

Trong SQL, các điều kiện có thể đánh giá thành:

- **`TRUE`:** điều kiện được xác định là đúng.
- **`FALSE`:** điều kiện được xác định là sai.
- **`UNKNOWN`:** chưa thể khẳng định đúng hay sai do thông tin thiếu, được biểu diễn bằng **`NULL` kiểu boolean**.

Ví dụ:

```sql
SELECT
    8 > 5                AS comparison_true,
    8 < 5                AS comparison_false,
    8 > NULL::integer    AS comparison_unknown;
```

Nếu hiển thị trong `psql` theo mặc định, cột boolean NULL có thể trông như một ô trống. Để nhận diện dễ hơn:

```text
\pset null '[NULL]'
```

Đây là **meta-command của `psql`**, chỉ thay đổi cách trình bày. Nó không biến NULL thành chuỗi `'[NULL]'` trong database. Trong các ứng dụng JDBC hoặc công cụ SQL khác, hãy dùng cơ chế hiển thị NULL của công cụ tương ứng.

### 2.1. Bảng chân trị nền tảng

| Biểu thức | Kết quả SQL |
|---|---|
| `TRUE` | `TRUE` |
| `FALSE` | `FALSE` |
| `NULL::boolean` | `UNKNOWN` |
| `NOT TRUE` | `FALSE` |
| `NOT FALSE` | `TRUE` |
| `NOT NULL::boolean` | `UNKNOWN` |

**`UNKNOWN` không phải một chuỗi giá trị thứ ba lưu trong kiểu `BOOLEAN`.** Cột boolean có thể lưu `TRUE`, `FALSE` hoặc `NULL`; từ `UNKNOWN` mô tả **cách logic diễn giải NULL** khi làm việc với điều kiện.

## 3. So sánh thông thường với NULL

Toán tử quan hệ thông dụng như `=`, `<>`, `<`, `>`, `<=`, `>=` nhìn chung trả **`UNKNOWN` khi một toán hạng là `NULL`**, với những toán tử chuẩn tương ứng.

```sql
SELECT
    (5 = NULL::integer)       AS eq_null,
    (5 <> NULL::integer)      AS ne_null,
    (5 < NULL::integer)       AS lt_null,
    (NULL::integer = 5)       AS null_eq_number,
    (NULL::integer = NULL::integer) AS null_eq_null;
```

Cả năm biểu thức trên trả NULL kiểu boolean, tức UNKNOWN.

Tại sao `NULL = NULL` không ra `TRUE`? Vì hai chỗ “không biết” không bảo đảm biểu diễn cùng một giá trị thực. Hai khách cùng chưa khai báo mã số thuế không có nghĩa mã số thuế của họ giống nhau.

Đây là **quy tắc của toán tử `=`**, không phải kết luận rằng PostgreSQL không bao giờ có cách coi hai NULL là tương đương. `IS NOT DISTINCT FROM`, `GROUP BY` và một số quy tắc uniqueness có cách xử lý NULL theo mục đích riêng.

### 3.1. Sai lầm phổ biến: WHERE column = NULL

```sql
-- Không tìm được những hàng NULL như mong đợi:
SELECT *
FROM demo_3vl.customer
WHERE email = NULL;
```

Vì `email = NULL` trả UNKNOWN cho mọi hàng trong điều kiện so sánh thông thường, `WHERE` không giữ hàng nào nhờ biểu thức này.

Cách đúng:

```sql
SELECT *
FROM demo_3vl.customer
WHERE email IS NULL;
```

Muốn tìm hàng có email:

```sql
SELECT *
FROM demo_3vl.customer
WHERE email IS NOT NULL;
```

**`IS NULL` và `IS NOT NULL` luôn cho `TRUE` hoặc `FALSE`**, không trả UNKNOWN như phép so sánh `= NULL`.

### 3.2. Câu phủ định cũng không tự biến UNKNOWN thành TRUE

```sql
SELECT
    NOT (5 = NULL::integer) AS negated_unknown,
    5 <> NULL::integer     AS not_equal_unknown;
```

Cả hai đều UNKNOWN. Lý do: **`NOT UNKNOWN = UNKNOWN`**.

Vì vậy cách viết:

```sql
WHERE NOT (status = 'PAID')
```

không tự bao gồm những hàng `status IS NULL`. Điều kiện `status = 'PAID'` là UNKNOWN ở các hàng đó; sau `NOT` nó vẫn UNKNOWN nên `WHERE` loại bỏ.

## 4. Bảng chân trị của NOT, AND, OR

### 4.1. NOT

| A | `NOT A` |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Đây là lý do không thể áp máy móc quy tắc Java “không phải đúng thì là sai” cho mọi biểu thức SQL có NULL.

### 4.2. AND

`A AND B` là FALSE nếu đã có một toán hạng xác định là FALSE; là TRUE nếu cả hai TRUE; những trường hợp còn lại có thể UNKNOWN.

| A | B = TRUE | B = FALSE | B = UNKNOWN |
|---|---|---|---|
| TRUE | TRUE | FALSE | UNKNOWN |
| FALSE | FALSE | FALSE | FALSE |
| UNKNOWN | UNKNOWN | FALSE | UNKNOWN |

Ví dụ:

```sql
SELECT
    (TRUE AND NULL::boolean)  AS true_and_unknown,
    (FALSE AND NULL::boolean) AS false_and_unknown,
    (NULL::boolean AND NULL::boolean) AS unknown_and_unknown;
```

Kết quả tương ứng: UNKNOWN, FALSE, UNKNOWN.

Một tình huống thực tế:

```sql
WHERE is_active = TRUE
  AND email IS NOT NULL
```

Nếu `is_active` là NULL thì biểu thức `is_active = TRUE` là UNKNOWN. Nếu email cũng NULL, `email IS NOT NULL` là FALSE; kết quả `UNKNOWN AND FALSE` là FALSE. Trong mọi trường hợp, `WHERE` chỉ giữ những hàng có điều kiện tổng TRUE.

### 4.3. OR

`A OR B` là TRUE nếu ít nhất một toán hạng TRUE; là FALSE nếu cả hai FALSE; những trường hợp còn lại có thể UNKNOWN.

| A | B = TRUE | B = FALSE | B = UNKNOWN |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| FALSE | TRUE | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | UNKNOWN |

```sql
SELECT
    (TRUE OR NULL::boolean)   AS true_or_unknown,
    (FALSE OR NULL::boolean)  AS false_or_unknown,
    (NULL::boolean OR NULL::boolean) AS unknown_or_unknown;
```

Kết quả tương ứng: TRUE, UNKNOWN, UNKNOWN.

### 4.4. Tự sinh đầy đủ bảng chân trị trong PostgreSQL

```sql
WITH truth_values(v, label) AS (
    VALUES
        (TRUE, 'TRUE'),
        (FALSE, 'FALSE'),
        (NULL::boolean, 'UNKNOWN')
)
SELECT
    a.label AS a,
    b.label AS b,
    a.v AND b.v AS a_and_b,
    a.v OR b.v  AS a_or_b,
    NOT a.v AS not_a
FROM truth_values AS a
CROSS JOIN truth_values AS b
ORDER BY a.label, b.label;
```

Khi thử, dùng `\pset null '[UNKNOWN]'` trong `psql` nếu muốn thấy kết quả boolean NULL dễ nhận biết. Lưu ý tên `[UNKNOWN]` chỉ là **nhãn hiển thị**; giá trị thực vẫn là NULL.

## 5. Vì sao các công thức logic hai giá trị có thể gây bất ngờ?

Trong logic hai giá trị cổ điển, mệnh đề “P hoặc không P” luôn đúng. Nhưng trong 3VL:

```sql
SELECT
    (NULL::boolean OR NOT NULL::boolean) AS excluded_middle,
    (NULL::boolean AND NOT NULL::boolean) AS contradiction;
```

Cả hai trả UNKNOWN.

Điều này giải thích bẫy sau:

```sql
SELECT *
FROM demo_3vl.customer
WHERE active = TRUE
   OR active <> TRUE;
```

Một người viết có thể nghĩ điều kiện bao phủ mọi hàng: “hoặc bằng TRUE, hoặc không bằng TRUE”. Thực tế, **hàng có `active IS NULL` bị loại** vì cả hai vế đều UNKNOWN.

Nếu mục tiêu là bao gồm tất cả các trạng thái, hãy viết rõ nghĩa mong muốn: `active IS TRUE`, `active IS FALSE` và `active IS UNKNOWN` là ba phép kiểm tra không trả UNKNOWN. Một điều kiện đúng với mọi hàng cũng không cần thiết phải viết dưới dạng OR như trên.

**Không có nghĩa toàn bộ đại số boolean đều mất hiệu lực trong SQL.** Nhiều quy tắc như De Morgan vẫn đúng theo bảng chân trị 3VL. Vấn đề là những quy tắc phụ thuộc giả định “mệnh đề chỉ đúng hoặc sai” không còn luôn phù hợp.

## 6. Chuẩn bị bảng và dữ liệu thực hành

Các phần dưới dùng cùng một schema nhỏ. Hãy chạy trên database lab, không chạy trên dữ liệu sản xuất.

```sql
CREATE SCHEMA IF NOT EXISTS demo_3vl;

CREATE TABLE demo_3vl.customer (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT,
    country_code TEXT,
    active BOOLEAN
);

CREATE TABLE demo_3vl.sales_order (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_3vl.customer(customer_id),
    status TEXT,
    note TEXT,
    paid_at TIMESTAMPTZ,
    amount NUMERIC(12, 2)
);

INSERT INTO demo_3vl.customer
    (customer_id, full_name, email, country_code, active)
VALUES
    (1, 'Lan',  'lan@example.test', 'VN', TRUE),
    (2, 'Minh', NULL,               'VN', NULL),
    (3, 'Hoa',  'hoa@example.test', NULL, FALSE),
    (4, 'An',   NULL,               NULL, TRUE),
    (5, 'Binh', 'binh@example.test','US', FALSE);

INSERT INTO demo_3vl.sales_order
    (order_id, customer_id, status, note, paid_at, amount)
VALUES
    (101, 1, 'NEW',       '',       NULL,  100000),
    (102, 1, 'PAID',      NULL,     '2026-11-10 10:00:00+07', 200000),
    (103, 2, NULL,        'manual',NULL,  150000),
    (104, 3, 'CANCELLED', NULL,     NULL,   50000),
    (105, 5, 'PAID',      NULL,     '2026-11-11 15:00:00+07', NULL);
```

Giải thích thiết kế:

- `customer.email` và `customer.country_code` nullable để tạo trường hợp UNKNOWN.
- `customer.active` nullable nhằm minh họa boolean có thể chưa biết; trong ứng dụng thật thường cần đánh giá xem `NOT NULL DEFAULT FALSE` có thích hợp hơn không.
- `sales_order.status` nullable để thấy khác biệt giữa `<>` và `IS DISTINCT FROM`.
- `sales_order.note` cố tình có cả chuỗi rỗng và NULL.
- `sales_order.amount` có một hàng NULL để thử các hàm tổng hợp.
- `paid_at` có NULL ở các đơn chưa ghi nhận thời điểm thanh toán.

Dữ liệu được chèn với khóa chính cố định để các kết quả trong bài dễ suy luận. Nếu chạy lại cùng lệnh `INSERT`, PostgreSQL sẽ từ chối vì khóa chính trùng. Trong lab, tạo bảng một lần trên schema sạch.

## 7. WHERE chỉ giữ TRUE, không giữ UNKNOWN

Đây là quy tắc quan trọng nhất khi đọc truy vấn:

> **`WHERE` giữ hàng nếu điều kiện là `TRUE`. Cả `FALSE` và `UNKNOWN` đều không được giữ.**

Ví dụ:

```sql
SELECT customer_id, full_name, active
FROM demo_3vl.customer
WHERE active = TRUE
ORDER BY customer_id;
```

Kết quả: khách 1 và 4 vì `active = TRUE`. Khách 2 có `active = NULL` không xuất hiện, mặc dù không ai chứng minh khách đó đang inactive.

```sql
SELECT customer_id, full_name, active
FROM demo_3vl.customer
WHERE active <> TRUE
ORDER BY customer_id;
```

Kết quả: khách 3 và 5 với `active = FALSE`. Khách 2 **vẫn không xuất hiện**.

Nếu muốn phân loại cả ba trạng thái:

```sql
SELECT
    customer_id,
    full_name,
    CASE
        WHEN active IS TRUE THEN 'ACTIVE'
        WHEN active IS FALSE THEN 'INACTIVE'
        ELSE 'UNKNOWN'
    END AS active_state
FROM demo_3vl.customer
ORDER BY customer_id;
```

Bây giờ khách 2 được phân loại `UNKNOWN` thay vì bị lặng lẽ loại khỏi kết quả.

### 7.1. Không phải NULL nào cũng cần lọc đi

`WHERE email IS NULL` là một truy vấn có chủ đích để tìm hồ sơ thiếu email:

```sql
SELECT customer_id, full_name
FROM demo_3vl.customer
WHERE email IS NULL
ORDER BY customer_id;
```

Kết quả: khách 2 và 4.

Nếu nghiệp vụ cần liên hệ khách hàng, đây là danh sách dữ liệu cần bổ sung. Nếu người viết thay NULL bằng `'unknown@example.test'` ngay từ đầu, việc xác định hồ sơ thực sự thiếu email có thể khó hơn.

## 8. IS NULL và IS NOT NULL luôn cho kết quả xác định

`IS NULL` và `IS NOT NULL` được thiết kế để hỏi về sự thiếu giá trị:

| Giá trị `x` | `x IS NULL` | `x IS NOT NULL` |
|---|---|---|
| `10` | FALSE | TRUE |
| `0` | FALSE | TRUE |
| `''` | FALSE | TRUE |
| `FALSE` | FALSE | TRUE |
| `NULL` | TRUE | FALSE |

```sql
SELECT
    order_id,
    note,
    note IS NULL AS note_missing,
    note IS NOT NULL AS note_present
FROM demo_3vl.sales_order
ORDER BY order_id;
```

Với đơn 101 có `note = ''`, `note IS NOT NULL` là TRUE. Một chuỗi rỗng và NULL không được đồng nhất.

### 8.1. Khi cần cả “NULL hoặc rỗng”

```sql
SELECT order_id, note
FROM demo_3vl.sales_order
WHERE note IS NULL
   OR note = ''
ORDER BY order_id;
```

Ở điều kiện này:

- `note IS NULL` là TRUE khi note NULL.
- `note = ''` là TRUE khi note rỗng.
- Hợp bằng OR đúng theo mong muốn, bất chấp vế so sánh có thể UNKNOWN khi note NULL.

Cũng có thể dùng `NULLIF` để gộp chuỗi rỗng thành NULL **trong một biểu thức**:

```sql
SELECT order_id, note
FROM demo_3vl.sales_order
WHERE NULLIF(note, '') IS NULL
ORDER BY order_id;
```

Nhưng hai cách đó biểu diễn cùng một nhu cầu chỉ nếu **chuỗi rỗng** là giá trị đặc biệt cần coi như thiếu. Nếu chuỗi chỉ toàn khoảng trắng cũng phải coi là thiếu, cần luật khác, ví dụ `NULLIF(btrim(note), '') IS NULL`, và phải hiểu đặc tính khoảng trắng/Unicode của dữ liệu.

## 9. IS DISTINCT FROM: so sánh an toàn với NULL

Toán tử `IS DISTINCT FROM` hỏi **hai giá trị có khác nhau không**, với quy tắc rõ ràng đối với NULL:

- Hai giá trị **đều NULL** → **không khác nhau**.
- Một giá trị NULL, giá trị kia không NULL → **khác nhau**.
- Hai giá trị đều không NULL → so sánh theo phép bằng của kiểu dữ liệu.

Nó **luôn trả `TRUE` hoặc `FALSE`**, không trả UNKNOWN cho những trường hợp NULL thông thường.

### 9.1. Bảng chân trị

| A | B | `A = B` | `A <> B` | `A IS DISTINCT FROM B` |
|---|---|---|---|---|
| `7` | `7` | TRUE | FALSE | FALSE |
| `7` | `9` | FALSE | TRUE | TRUE |
| `7` | `NULL` | UNKNOWN | UNKNOWN | TRUE |
| `NULL` | `7` | UNKNOWN | UNKNOWN | TRUE |
| `NULL` | `NULL` | UNKNOWN | UNKNOWN | FALSE |

Thử trực tiếp:

```sql
SELECT
    7 IS DISTINCT FROM 7 AS same_values,
    7 IS DISTINCT FROM 9 AS different_values,
    7 IS DISTINCT FROM NULL::integer AS value_vs_null,
    NULL::integer IS DISTINCT FROM 7 AS null_vs_value,
    NULL::integer IS DISTINCT FROM NULL::integer AS both_null;
```

Các kết quả lần lượt: FALSE, TRUE, TRUE, TRUE, FALSE.

**Đừng hiểu “distinct” ở đây là hai hàng có khóa chính khác nhau.** Nó đang so sánh **giá trị của biểu thức** theo toán tử bằng của kiểu dữ liệu, có thêm cách xử lý NULL.

### 9.2. IS NOT DISTINCT FROM: bằng nhau bao gồm NULL

Toán tử `IS NOT DISTINCT FROM` đảo nghĩa của `IS DISTINCT FROM` và thường được gọi là **null-safe equality**:

| A | B | `A IS NOT DISTINCT FROM B` |
|---|---|---|
| `7` | `7` | TRUE |
| `7` | `9` | FALSE |
| `7` | `NULL` | FALSE |
| `NULL` | `7` | FALSE |
| `NULL` | `NULL` | TRUE |

```sql
SELECT
    NULL::text IS NOT DISTINCT FROM NULL::text AS both_missing,
    'VN'::text IS NOT DISTINCT FROM 'VN'::text AS same_country,
    'VN'::text IS NOT DISTINCT FROM NULL::text AS missing_country;
```

Kết quả: TRUE, TRUE, FALSE.

Ta có thể nhớ:

- **`=`:** bằng nhau nếu thông tin đủ để kết luận, còn NULL thường trả UNKNOWN.
- **`IS NOT DISTINCT FROM`:** coi NULL với NULL là tương đương để so sánh.
- **`<>`:** khác nhau nếu thông tin đủ để kết luận.
- **`IS DISTINCT FROM`:** coi NULL với giá trị thật là khác nhau, NULL với NULL là không khác nhau.

### 9.3. Ví dụ trên dữ liệu khách hàng

Tìm những khách có mã quốc gia **khác 'VN'**, bao gồm cả người chưa có mã quốc gia:

```sql
SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
WHERE country_code IS DISTINCT FROM 'VN'
ORDER BY customer_id;
```

Kết quả: khách 3, 4, 5. Khách 3 và 4 có country_code NULL, và toán tử xác nhận rằng NULL được xem là **khác** một giá trị cụ thể `'VN'`.

So sánh với:

```sql
SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
WHERE country_code <> 'VN'
ORDER BY customer_id;
```

Chỉ khách 5 có `'US'`. Khách 3, 4 bị loại vì điều kiện với NULL là UNKNOWN.

**Cẩn thận ngữ nghĩa:** “không biết quốc gia” **không đồng nghĩa thật sự thuộc quốc gia ngoài VN**. `IS DISTINCT FROM 'VN'` phù hợp nếu yêu cầu là “giá trị hiện lưu khác với 'VN', kể cả thiếu dữ liệu”. Nếu yêu cầu nghiệp vụ là “đã xác nhận không thuộc VN”, cần:

```sql
WHERE country_code IS NOT NULL
  AND country_code <> 'VN'
```

Chọn toán tử phải theo ý nghĩa dữ liệu, không chỉ vì nó bao gồm nhiều hàng hơn.

## 10. IS DISTINCT FROM và IS NOT DISTINCT FROM dùng trong UPDATE

Một ứng dụng thường muốn tránh cập nhật hàng khi giá trị mới **thật sự không khác** giá trị cũ. Điều này hữu ích với audit, trigger, WAL, optimistic update và đồng bộ dữ liệu, đặc biệt khi cả hai bên có thể NULL.

Ví dụ thay `country_code` của khách 3 thành `'VN'` nếu giá trị hiện có khác:

```sql
UPDATE demo_3vl.customer
SET country_code = 'VN'
WHERE customer_id = 3
  AND country_code IS DISTINCT FROM 'VN'
RETURNING customer_id, country_code;
```

Ở lần chạy đầu, `country_code` cũ là NULL nên được coi là khác `'VN'`; hàng được cập nhật. Chạy lại cùng lệnh, điều kiện trở thành FALSE, PostgreSQL không phải thực hiện UPDATE cho hàng đó.

Nếu viết:

```sql
-- Không phát hiện NULL khác 'VN' theo cách mong muốn:
UPDATE demo_3vl.customer
SET country_code = 'VN'
WHERE customer_id = 4
  AND country_code <> 'VN';
```

khách 4 có country_code NULL, nên điều kiện UNKNOWN và **không được cập nhật**. Nếu mục tiêu là sửa mọi giá trị khác (kể cả NULL), dùng `IS DISTINCT FROM`.

### 10.1. Đồng bộ một giá trị nullable từ nguồn khác

Giả sử ứng dụng có cặp giá trị `old_email` và `new_email`, cả hai đều có thể NULL.

```sql
WITH input(old_email, new_email) AS (
    VALUES
        (NULL::text, NULL::text),
        (NULL::text, 'new@example.test'),
        ('a@example.test', NULL::text),
        ('a@example.test', 'a@example.test')
)
SELECT
    old_email,
    new_email,
    old_email IS DISTINCT FROM new_email AS value_changed
FROM input;
```

Kết quả `value_changed` lần lượt FALSE, TRUE, TRUE, FALSE. Đây là câu hỏi rất hay dùng trong CDC/ETL: “giá trị dữ liệu có thay đổi thật không?”, không phải “có bằng nhau theo logic ba giá trị không?”.

### 10.2. UPSERT không cập nhật lại giá trị giống hệt

```sql
CREATE TABLE demo_3vl.app_setting (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO demo_3vl.app_setting AS target
    (setting_key, setting_value)
VALUES
    ('theme', NULL)
ON CONFLICT (setting_key)
DO UPDATE SET
    setting_value = EXCLUDED.setting_value,
    updated_at = now()
WHERE target.setting_value IS DISTINCT FROM EXCLUDED.setting_value;
```

Ở lần chèn đầu, hàng được tạo. Những lần chạy tiếp theo với `setting_value = NULL`, điều kiện `NULL IS DISTINCT FROM NULL` là FALSE, nên nhánh `DO UPDATE` không ghi lại hàng chỉ vì một sự kiện đồng bộ trùng lặp.

Nếu dùng `target.setting_value <> EXCLUDED.setting_value`, biểu thức cũng UNKNOWN khi có NULL và sẽ **bỏ qua cả những thay đổi hợp lệ từ NULL sang giá trị thật hoặc ngược lại**.

Lưu ý: điều kiện ở nhánh UPSERT chỉ áp dụng sau khi phát hiện xung đột; các constraint và những tác động khác của quá trình ghi vẫn tuân theo quy tắc PostgreSQL. Không coi ví dụ này là mẫu xử lý cạnh tranh hoàn chỉnh cho mọi bảng.

## 11. IS NOT DISTINCT FROM trong JOIN

Trong `INNER JOIN` thông thường, điều kiện:

```sql
ON a.code = b.code
```

không nối hai hàng khi cả hai có `code IS NULL`, vì `NULL = NULL` là UNKNOWN; điều kiện `ON` chỉ chấp nhận TRUE để xác lập cặp khớp.

Nếu nghiệp vụ thực sự muốn **coi NULL ở hai phía là cùng một nhóm**, có thể viết:

```sql
ON a.code IS NOT DISTINCT FROM b.code
```

### 11.1. Thí nghiệm với danh sách mã

```sql
WITH source(code, source_name) AS (
    VALUES
        ('VN'::text, 'A'),
        (NULL::text, 'B'),
        ('US'::text, 'C')
),
lookup(code, label) AS (
    VALUES
        ('VN'::text, 'Viet Nam'),
        (NULL::text, 'Unspecified')
)
SELECT
    s.source_name,
    s.code AS source_code,
    l.label
FROM source AS s
LEFT JOIN lookup AS l
    ON s.code IS NOT DISTINCT FROM l.code
ORDER BY s.source_name;
```

Kết quả:

| source_name | source_code | label |
|---|---|---|
| A | VN | Viet Nam |
| B | NULL | Unspecified |
| C | US | NULL |

Nếu thay `IS NOT DISTINCT FROM` bằng `=`, hàng B sẽ **không nối** với dòng `lookup.code IS NULL`; `label` nhận NULL do `LEFT JOIN` không tìm được hàng khớp.

### 11.2. Không phải lúc nào cũng nên nối NULL với NULL

Hai mã khách hàng đều NULL không có nghĩa chúng trỏ đến **cùng khách hàng**. Nếu nối hai bảng lớn trên một trường định danh nullable:

```sql
ON left_table.customer_id IS NOT DISTINCT FROM right_table.customer_id
```

và cả hai bảng có nhiều dòng `customer_id IS NULL`, mọi tổ hợp NULL/NULL có thể tạo rất nhiều cặp khớp, làm tăng số hàng và gây **sai dữ liệu báo cáo**.

Hãy chỉ dùng null-safe equality khi NULL có ý nghĩa **một nhóm/khoá thiếu chung có thể nối được** theo hợp đồng dữ liệu. Với foreign key nghiệp vụ, thường nên dùng khóa thật, `NOT NULL` khi phù hợp và phép `=`.

## 12. Bẫy LEFT JOIN: ON và WHERE không tương đương

Với outer join, điều kiện `ON` và `WHERE` có thời điểm áp dụng khác nhau.

Muốn lấy mọi khách hàng và đơn đã `PAID` nếu có:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.status
FROM demo_3vl.customer AS c
LEFT JOIN demo_3vl.sales_order AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Tất cả khách hàng được giữ bởi `LEFT JOIN`. Khách không có đơn PAID có cột phía `o` là NULL trong kết quả.

Nhưng chuyển điều kiện xuống `WHERE`:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.status
FROM demo_3vl.customer AS c
LEFT JOIN demo_3vl.sales_order AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

`WHERE o.status = 'PAID'` loại những hàng mà `o.status` là NULL (do không khớp hoặc dữ liệu gốc NULL), khiến kết quả không còn giữ khách không có đơn PAID như mục tiêu ban đầu.

**Quy tắc:** `ON` quyết định cặp hàng khớp; `WHERE` lọc kết quả sau bước join. Trong outer join, chuyển điều kiện từ `ON` sang `WHERE` có thể thay đổi số hàng và ý nghĩa truy vấn.

### 12.1. Phân biệt hàng bên phải không tồn tại với cột nullable

Khi cần tìm khách **không có đơn nào**, dựa vào một cột khóa không nullable ở bảng bên phải:

```sql
SELECT c.customer_id, c.full_name
FROM demo_3vl.customer AS c
LEFT JOIN demo_3vl.sales_order AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Vì `o.order_id` là PRIMARY KEY, NULL trong kết quả bên phải cho biết không có hàng order khớp. Nếu thay bằng `WHERE o.note IS NULL`, ta còn lấy cả những đơn có thật nhưng `note` NULL, tạo kết quả sai.

Một cách khác thường dễ diễn đạt hơn là `NOT EXISTS`, sẽ xét ở phần sau.

## 13. IN: một biểu thức có thể cho UNKNOWN

`x IN (a,b,c)` trong các trường hợp thông thường tương đương ý tưởng `x = a OR x = b OR x = c` theo logic SQL.

```sql
SELECT
    2 IN (1, 2, NULL) AS found_value,
    3 IN (1, 2, NULL) AS absent_with_null,
    3 IN (1, 2)       AS absent_without_null,
    NULL::integer IN (1, 2) AS null_left;
```

Kết quả:

- `2 IN (1,2,NULL)` → TRUE, vì đã có một phép so sánh TRUE.
- `3 IN (1,2,NULL)` → UNKNOWN, vì không có so sánh TRUE và có so sánh với NULL.
- `3 IN (1,2)` → FALSE.
- `NULL IN (1,2)` → UNKNOWN.

`IN` không mặc nhiên tìm được giá trị NULL trong danh sách. Nếu muốn so khớp NULL như một thành viên riêng, phải mô hình hóa rõ bằng `IS NULL` hoặc null-safe equality trong thiết kế thích hợp.

## 14. NOT IN và NULL: lỗi lọc dữ liệu rất thường gặp

`NOT IN` đặc biệt dễ gây sai vì phủ định của UNKNOWN vẫn UNKNOWN.

```sql
SELECT
    3 NOT IN (1, 2, NULL) AS surprising_result;
```

Kết quả là UNKNOWN, **không phải TRUE**.

Giải thích:

```text
3 NOT IN (1, 2, NULL)

≈ NOT (3 = 1 OR 3 = 2 OR 3 = NULL)
≈ NOT (FALSE OR FALSE OR UNKNOWN)
≈ NOT UNKNOWN
≈ UNKNOWN
```

Nếu đặt biểu thức này vào `WHERE`, hàng bị loại.

### 14.1. Tình huống với subquery

Giả sử có danh sách quốc gia loại trừ, nhưng một hàng bị nhập thiếu mã:

```sql
CREATE TABLE demo_3vl.excluded_country (
    country_code TEXT
);

INSERT INTO demo_3vl.excluded_country (country_code)
VALUES ('US'), (NULL);
```

Truy vấn:

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE c.country_code NOT IN (
    SELECT e.country_code
    FROM demo_3vl.excluded_country AS e
);
```

Không nên kỳ vọng truy vấn sẽ trả đầy đủ các khách có quốc gia khác US. Vì subquery có NULL, phép `NOT IN` có thể trả UNKNOWN cho các mã không khớp, khiến chúng bị loại.

### 14.2. Cách 1: loại NULL khỏi tập bên phải khi đúng nghiệp vụ

Nếu luật là “bỏ qua dòng excluded_country chưa có mã”:

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE c.country_code IS NOT NULL
  AND c.country_code NOT IN (
      SELECT e.country_code
      FROM demo_3vl.excluded_country AS e
      WHERE e.country_code IS NOT NULL
  )
ORDER BY c.customer_id;
```

Ở đây, điều kiện phía trái `c.country_code IS NOT NULL` được đặt tường minh vì truy vấn chỉ xét quốc gia **đã biết**. Các khách quốc gia NULL không được phân loại là nằm ngoài danh sách.

### 14.3. Cách 2: NOT EXISTS với so sánh đã chọn

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_3vl.excluded_country AS e
    WHERE e.country_code = c.country_code
)
ORDER BY c.customer_id;
```

`NOT EXISTS` kiểm tra có hàng subquery nào thỏa điều kiện hay không. Khi hai mã đều NULL, `e.country_code = c.country_code` là UNKNOWN nên không được coi là một hàng khớp. Theo cách này, những khách có country_code NULL **có thể vẫn được giữ**.

Nếu muốn NULL ở hai phía được xem là cùng một mã thiếu (và do bảng loại trừ có một NULL, khách thiếu country_code cũng bị loại):

```sql
SELECT c.customer_id, c.country_code
FROM demo_3vl.customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_3vl.excluded_country AS e
    WHERE e.country_code IS NOT DISTINCT FROM c.country_code
)
ORDER BY c.customer_id;
```

**Không có một phép thay thế `NOT IN` bằng `NOT EXISTS` đúng cho mọi ý nghĩa NULL.** Sự khác nhau nằm ở cách xác định “một hàng khớp” và cách xử lý giá trị thiếu. Hãy viết điều kiện khớp theo ngữ nghĩa thực sự mong muốn.

### 14.4. EXISTS và NOT EXISTS bản thân trả TRUE hoặc FALSE

Một biểu thức `EXISTS (subquery)` là TRUE nếu subquery trả ít nhất một hàng, FALSE nếu không có hàng; nó **không trả UNKNOWN chỉ vì cột của hàng trong subquery là NULL**.

```sql
SELECT
    EXISTS (SELECT NULL::integer) AS has_one_row,
    EXISTS (SELECT 1 WHERE FALSE) AS has_no_row;
```

Kết quả: TRUE và FALSE. Điều quan trọng là **có hàng được trả** hay không, không phải ô chứa giá trị gì.

## 15. ANY và ALL cũng chịu logic ba giá trị

Ngoài `IN`, PostgreSQL hỗ trợ so sánh theo tập giá trị với `ANY` và `ALL`. Chúng rất hữu ích nhưng cần hiểu NULL.

Ví dụ:

```sql
SELECT
    2 = ANY (ARRAY[1, 2, NULL]::integer[]) AS any_match,
    3 = ANY (ARRAY[1, 2, NULL]::integer[]) AS any_unknown,
    3 <> ALL (ARRAY[1, 2, NULL]::integer[]) AS all_unknown;
```

Với toán tử bình thường có tính strict đối với NULL:

- `ANY` có thể TRUE nếu ít nhất một so sánh TRUE.
- Nếu không có TRUE nhưng có so sánh UNKNOWN, kết quả có thể UNKNOWN.
- `ALL` có thể FALSE nếu ít nhất một so sánh FALSE.
- Nếu không có FALSE nhưng có so sánh UNKNOWN, kết quả có thể UNKNOWN.

Cần phân biệt **mảng rỗng**, **mảng NULL** và **mảng chứa phần tử NULL**:

```sql
SELECT
    3 = ANY (ARRAY[]::integer[]) AS any_empty,
    3 = ALL (ARRAY[]::integer[]) AS all_empty,
    3 = ANY (NULL::integer[]) AS any_null_array;
```

Kết quả theo quy tắc thông thường: FALSE, TRUE, UNKNOWN.

Các trường hợp biên này đặc biệt quan trọng khi JDBC truyền một mảng tham số: danh sách rỗng và danh sách chứa một phần tử NULL không có ý nghĩa giống nhau.

## 16. CASE WHEN: UNKNOWN không được coi là nhánh TRUE

`CASE WHEN điều_kiện THEN ...` chỉ chọn nhánh có điều kiện TRUE. Nếu điều kiện FALSE hoặc UNKNOWN, PostgreSQL thử nhánh tiếp theo.

```sql
SELECT
    customer_id,
    country_code,
    CASE
        WHEN country_code = 'VN' THEN 'Viet Nam'
        WHEN country_code <> 'VN' THEN 'Foreign'
        ELSE 'Unknown'
    END AS country_group
FROM demo_3vl.customer
ORDER BY customer_id;
```

Với khách quốc gia NULL, hai phép so sánh đều UNKNOWN, nên đi vào `ELSE 'Unknown'`.

Cách viết khác rõ ý hơn:

```sql
SELECT
    customer_id,
    CASE
        WHEN country_code IS NULL THEN 'Unknown'
        WHEN country_code = 'VN' THEN 'Viet Nam'
        ELSE 'Foreign'
    END AS country_group
FROM demo_3vl.customer
ORDER BY customer_id;
```

Ở đây người đọc thấy rõ cách phân loại giá trị thiếu. Đừng cố coi country_code NULL như một quốc gia khác VN nếu nghiệp vụ cần phân biệt “chưa biết”.

### 16.1. Simple CASE với WHEN NULL cũng không làm điều thường mong đợi

```sql
SELECT
    customer_id,
    CASE country_code
        WHEN 'VN' THEN 'Viet Nam'
        WHEN NULL THEN 'Unknown'
        ELSE 'Other'
    END AS country_label
FROM demo_3vl.customer
ORDER BY customer_id;
```

Nhánh `WHEN NULL` của simple CASE **không khớp với country_code NULL** theo so sánh bằng thông thường. Cách đúng là searched CASE với `WHEN country_code IS NULL THEN ...`.

### 16.2. CASE trả một giá trị, không phải luôn là một phép kiểm tra constraint

Ví dụ:

```sql
SELECT
    order_id,
    CASE WHEN amount > 0 THEN 'POSITIVE' ELSE 'NOT_POSITIVE' END
        AS amount_group
FROM demo_3vl.sales_order
ORDER BY order_id;
```

Đơn 105 có `amount NULL` sẽ nhận `NOT_POSITIVE`, dù ta **chưa biết** số tiền có dương hay không. Nếu cần ba nhãn:

```sql
CASE
    WHEN amount IS NULL THEN 'UNKNOWN'
    WHEN amount > 0 THEN 'POSITIVE'
    ELSE 'NON_POSITIVE'
END
```

Không phải lúc nào `ELSE` cũng có nghĩa “điều kiện ngược lại là TRUE”; nó còn bao gồm UNKNOWN của các nhánh trước.

## 17. Boolean nullable: IS TRUE, IS FALSE, IS UNKNOWN

Trong PostgreSQL, cột boolean nullable có thể mang TRUE, FALSE hoặc NULL.

```sql
SELECT
    customer_id,
    active,
    active IS TRUE AS definitely_active,
    active IS FALSE AS definitely_inactive,
    active IS UNKNOWN AS status_unknown,
    active IS NOT TRUE AS not_known_active,
    active IS NOT FALSE AS not_known_inactive
FROM demo_3vl.customer
ORDER BY customer_id;
```

Các phép kiểm tra `IS TRUE`, `IS FALSE`, `IS UNKNOWN` và dạng `IS NOT ...` **trả boolean xác định**.

| active | `IS TRUE` | `IS FALSE` | `IS UNKNOWN` | `IS NOT TRUE` | `IS NOT FALSE` |
|---|---|---|---|---|---|
| TRUE | TRUE | FALSE | FALSE | FALSE | TRUE |
| FALSE | FALSE | TRUE | FALSE | TRUE | FALSE |
| NULL | FALSE | FALSE | TRUE | TRUE | TRUE |

**Hai điều kiện khác nhau:**

```sql
WHERE active IS FALSE
```

chỉ chọn hàng đã biết là FALSE.

```sql
WHERE active IS NOT TRUE
```

chọn cả FALSE **và NULL**. Nếu nghiệp vụ phân biệt “tài khoản đã bị vô hiệu hóa” với “chưa xác minh trạng thái”, đây là khác biệt rất lớn.

### 17.1. WHERE active và WHERE NOT active

```sql
SELECT customer_id
FROM demo_3vl.customer
WHERE active;

SELECT customer_id
FROM demo_3vl.customer
WHERE NOT active;
```

Câu đầu chọn TRUE; câu sau chọn FALSE; **cả hai đều bỏ qua NULL**. Muốn chọn FALSE hoặc NULL, dùng `active IS NOT TRUE`.

## 18. CHECK constraint: UNKNOWN thường được chấp nhận

Đây là nơi người mới rất dễ viết constraint mà tưởng dữ liệu đã được bảo vệ hoàn toàn.

```sql
CREATE TABLE demo_3vl.delivery (
    delivery_id INTEGER PRIMARY KEY,
    distance_km NUMERIC(10,2),
    CONSTRAINT ck_delivery_distance_positive
        CHECK (distance_km > 0)
);
```

Thử:

```sql
INSERT INTO demo_3vl.delivery (delivery_id, distance_km)
VALUES (1, NULL);
```

Lệnh này **có thể thành công**, vì `distance_km > 0` trả UNKNOWN, và PostgreSQL coi CHECK hợp lệ khi kết quả **không phải FALSE**.

Nhưng:

```sql
-- Cố tình vi phạm CHECK:
INSERT INTO demo_3vl.delivery (delivery_id, distance_km)
VALUES (2, -1);
```

Bị từ chối vì điều kiện trả FALSE.

Để yêu cầu khoảng cách phải được cung cấp và dương:

```sql
CREATE TABLE demo_3vl.delivery_strict (
    delivery_id INTEGER PRIMARY KEY,
    distance_km NUMERIC(10,2) NOT NULL,
    CONSTRAINT ck_delivery_strict_distance_positive
        CHECK (distance_km > 0)
);
```

`NOT NULL` và `CHECK` bảo vệ hai điều khác nhau:

- `NOT NULL`: không được thiếu giá trị.
- `CHECK`: những giá trị được cung cấp phải thỏa miền hợp lệ.

### 18.1. DEFAULT cũng không thay thế NOT NULL hoặc CHECK

```sql
status TEXT DEFAULT 'NEW'
```

không tự cấm `NULL` và cũng không cấm `'WRONG'`. Muốn bảo vệ cả hai:

```sql
status TEXT NOT NULL DEFAULT 'NEW',
CONSTRAINT ck_status_allowed
    CHECK (status IN ('NEW','PAID','CANCELLED'))
```

Giá trị default được dùng khi `INSERT` bỏ cột hoặc yêu cầu `DEFAULT` hợp lệ; khi client gửi `NULL` tường minh, default không tự áp dụng và `NOT NULL` sẽ từ chối.

Sự khác biệt giữa **khởi tạo giá trị** và **kiểm tra hợp lệ** là nền tảng của thiết kế schema đúng.

## 19. UNIQUE và NULL: không giống so sánh bằng trong WHERE

Một unique constraint thông thường của PostgreSQL cho phép nhiều giá trị NULL ở cột nullable, vì theo quy tắc unique mặc định các NULL không được coi là trùng nhau.

```sql
CREATE TABLE demo_3vl.external_ref (
    id INTEGER PRIMARY KEY,
    reference_code TEXT UNIQUE
);

INSERT INTO demo_3vl.external_ref (id, reference_code)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'EXT-001');
```

Những hàng (1,NULL) và (2,NULL) hợp lệ theo unique thông thường. Nhưng:

```sql
-- Cố tình vi phạm UNIQUE:
INSERT INTO demo_3vl.external_ref (id, reference_code)
VALUES (4, 'EXT-001');
```

Bị từ chối vì mã `EXT-001` trùng.

### 19.1. UNIQUE NULLS NOT DISTINCT (PostgreSQL 15+)

Từ PostgreSQL 15, có cú pháp `UNIQUE NULLS NOT DISTINCT` để yêu cầu coi các NULL là **không phân biệt nhau khi kiểm tra duy nhất**:

```sql
CREATE TABLE demo_3vl.external_ref_strict (
    id INTEGER PRIMARY KEY,
    reference_code TEXT,
    CONSTRAINT uq_external_ref_strict_code
        UNIQUE NULLS NOT DISTINCT (reference_code)
);
```

Lúc này:

```sql
INSERT INTO demo_3vl.external_ref_strict (id, reference_code)
VALUES (1, NULL);

-- Cố tình vi phạm UNIQUE NULLS NOT DISTINCT:
INSERT INTO demo_3vl.external_ref_strict (id, reference_code)
VALUES (2, NULL);
```

Hàng thứ hai bị từ chối vì NULL và NULL được xem là **không phân biệt** trong chính sách duy nhất.

Điều này cho thấy PostgreSQL có **nhiều ngữ cảnh xử lý NULL khác nhau**:

- `NULL = NULL` → UNKNOWN.
- `NULL IS NOT DISTINCT FROM NULL` → TRUE.
- `UNIQUE` thông thường → có thể cho nhiều NULL.
- `UNIQUE NULLS NOT DISTINCT` → không cho các giá trị NULL trùng theo luật unique liên quan.

Không trộn các quy tắc thành một định luật “NULL luôn bằng nhau” hoặc “NULL không bao giờ giống nhau”.

### 19.2. ON CONFLICT cũng phụ thuộc định nghĩa unique

Với unique thông thường, hai hàng có `reference_code NULL` có thể không xung đột nhau; chúng không tự kích hoạt cùng một nhánh `ON CONFLICT (reference_code)` chỉ vì cả hai NULL.

Nếu nghiệp vụ cần chỉ một hàng “reference chưa được cấp”, chọn ràng buộc/thiết kế đúng thay vì cố dùng `ON CONFLICT` để thay thế luật unique thiếu.

## 20. DISTINCT, GROUP BY và NULL

Khi truy vấn `SELECT DISTINCT`, PostgreSQL loại các dòng trùng lặp. Những giá trị NULL trong cùng một vị trí được xử lý **theo quy tắc loại trùng của tập kết quả**, không đơn thuần bằng biểu thức `NULL = NULL` trong `WHERE`.

```sql
SELECT DISTINCT country_code
FROM demo_3vl.customer
ORDER BY country_code NULLS LAST;
```

Các country_code mẫu là VN, VN, NULL, NULL, US. Kết quả DISTINCT có ba nhóm: `VN`, `US` và một hàng `NULL`.

Tương tự:

```sql
SELECT
    country_code,
    COUNT(*) AS customers
FROM demo_3vl.customer
GROUP BY country_code
ORDER BY country_code NULLS LAST;
```

Khách có country_code NULL được gom vào **một nhóm NULL** khi `GROUP BY`, với `COUNT(*) = 2` theo dữ liệu mẫu trước khi các bài thực hành UPDATE thay đổi nó.

### 20.1. GROUP BY NULL khác với kết luận chúng có cùng mã thật

Việc gom hai giá trị thiếu thành một nhóm **không chứng minh** chúng biểu diễn cùng quốc gia thực. Nó chỉ giúp báo cáo có một nhóm “chưa biết”.

Nếu phân tích tỷ lệ khách theo quốc gia, cần hiện nhóm UNKNOWN rõ ràng:

```sql
SELECT
    COALESCE(country_code, '[UNKNOWN]') AS country_group,
    COUNT(*) AS customer_count
FROM demo_3vl.customer
GROUP BY COALESCE(country_code, '[UNKNOWN]')
ORDER BY country_group;
```

Ở câu trên, giá trị `'[UNKNOWN]'` là nhãn hiển thị, nhưng nếu dữ liệu thật cũng có country_code đúng chuỗi đó, chúng sẽ bị gộp vào cùng nhóm. Với hệ thống thực, nên tách **trường flag NULL** và **label hiển thị** hoặc có quy tắc domain để tránh va chạm sentinel.

### 20.2. COUNT(DISTINCT ...) bỏ qua NULL

```sql
SELECT
    COUNT(*) AS total_customers,
    COUNT(country_code) AS known_country_count,
    COUNT(DISTINCT country_code) AS distinct_known_countries
FROM demo_3vl.customer;
```

Theo dữ liệu mẫu ban đầu:

- `COUNT(*)` = 5 vì đếm tất cả hàng.
- `COUNT(country_code)` = 3 vì bỏ qua hai hàng NULL.
- `COUNT(DISTINCT country_code)` = 2 vì hai giá trị không NULL khác nhau là `VN` và `US`.

**`SELECT DISTINCT` có thể hiển thị một hàng NULL, nhưng `COUNT(DISTINCT column)` không đếm NULL.** Đây là hai thao tác có ngữ nghĩa khác nhau, không phải mâu thuẫn.

## 21. Các hàm tổng hợp và cách chúng xử lý NULL

Phần lớn hàm aggregate thông dụng như `SUM`, `AVG`, `MIN`, `MAX` bỏ qua các giá trị NULL trong input của chúng; `COUNT(*)` đếm hàng và `COUNT(column)` đếm những giá trị column không NULL.

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(amount) AS orders_with_amount,
    COUNT(*) - COUNT(amount) AS orders_missing_amount,
    SUM(amount) AS sum_known_amount,
    AVG(amount) AS avg_known_amount
FROM demo_3vl.sales_order;
```

Theo dữ liệu mẫu ban đầu:

- Tổng số đơn: 5.
- Số đơn có amount khác NULL: 4.
- Số đơn thiếu amount: 1.
- `SUM(amount)` cộng bốn khoản có giá trị, **không xem NULL là một khoản 0 đã biết**.
- `AVG(amount)` chia tổng các giá trị đã biết cho số giá trị không NULL, không chia cho 5.

Nếu tất cả amount đều NULL hoặc tập đầu vào rỗng, `SUM(amount)` thường trả NULL; `COUNT(*)` và `COUNT(amount)` trả số đếm thích hợp, có thể là 0.

### 21.1. COUNT(*) FILTER để đếm NULL rõ ràng

```sql
SELECT
    COUNT(*) FILTER (WHERE amount IS NULL) AS missing_amount,
    COUNT(*) FILTER (WHERE amount IS NOT NULL) AS known_amount,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM demo_3vl.sales_order;
```

`FILTER (WHERE ...)` tuân theo logic điều kiện: chỉ những hàng có điều kiện TRUE được đưa vào aggregate tương ứng.

### 21.2. COALESCE(SUM(...),0) không giống SUM(COALESCE(...,0)) trong mọi mục đích

```sql
SELECT
    COALESCE(SUM(amount), 0) AS total_or_zero,
    SUM(COALESCE(amount, 0)) AS total_with_missing_as_zero
FROM demo_3vl.sales_order;
```

Với bảng có hàng, hai công thức có thể cùng cho một tổng số học; nhưng chúng mang **ý nghĩa khác**:

- `COALESCE(SUM(amount), 0)` thay NULL ở **kết quả tổng** nếu không có giá trị để tổng hợp.
- `SUM(COALESCE(amount,0))` coi **mỗi amount thiếu** như 0 ở đầu vào.

Nếu tính trung bình, khác biệt lộ rõ:

```sql
SELECT
    AVG(amount) AS avg_known_amount,
    AVG(COALESCE(amount, 0)) AS avg_missing_as_zero
FROM demo_3vl.sales_order;
```

Công thức thứ hai xem đơn có amount thiếu là 0 và đưa nó vào mẫu số, có thể làm sai báo cáo. Không thay NULL bằng 0 trước khi tổng hợp trừ khi nghiệp vụ xác nhận giá trị thiếu thực sự phải được tính là 0.

## 22. HAVING cũng chỉ giữ những nhóm có điều kiện TRUE

`HAVING` lọc các nhóm sau `GROUP BY`, với quy tắc logic giống `WHERE`: nhóm được giữ khi điều kiện đánh giá TRUE.

```sql
SELECT
    customer_id,
    AVG(amount) AS avg_amount
FROM demo_3vl.sales_order
GROUP BY customer_id
HAVING AVG(amount) > 100000
ORDER BY customer_id;
```

Nếu một nhóm chỉ có những amount NULL, `AVG(amount)` trả NULL; phép `> 100000` là UNKNOWN; nhóm đó không được giữ.

Nếu muốn tách các nhóm không có amount được biết:

```sql
SELECT
    customer_id,
    COUNT(amount) AS known_amount_rows,
    AVG(amount) AS avg_amount
FROM demo_3vl.sales_order
GROUP BY customer_id
HAVING COUNT(amount) = 0
ORDER BY customer_id;
```

Ở tập ví dụ ban đầu, khách 5 có một đơn amount NULL nên thỏa nhóm không có amount được biết.

## 23. ORDER BY và vị trí của NULL

`ORDER BY` có thể sắp xếp các hàng có NULL, nhưng không có nghĩa PostgreSQL dùng `NULL = NULL` để quyết định thứ tự.

PostgreSQL mặc định coi NULL lớn hơn giá trị không NULL khi sắp xếp theo thứ tự thông thường:

- `ORDER BY x ASC` thường đặt NULL **cuối**.
- `ORDER BY x DESC` thường đặt NULL **đầu**.

Nên viết tường minh khi đầu ra quan trọng:

```sql
SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
ORDER BY country_code ASC NULLS LAST, customer_id;

SELECT customer_id, full_name, country_code
FROM demo_3vl.customer
ORDER BY country_code DESC NULLS LAST, customer_id;
```

`NULLS FIRST` / `NULLS LAST` là quy tắc sắp xếp, **không thay đổi dữ liệu lưu và không biến NULL thành giá trị thực**.

Nếu dùng pagination, thêm một khóa tiebreaker ổn định như `customer_id` để tránh thứ tự tương đối không xác định giữa các hàng có cùng country_code.

## 24. IS DISTINCT FROM với nhiều cột và row expression

Khi so sánh một bộ giá trị gồm nhiều cột, có thể dùng các row constructors trong PostgreSQL.

```sql
SELECT
    ROW(1, NULL::text) IS NOT DISTINCT FROM
        ROW(1, NULL::text) AS same_pair,
    ROW(1, NULL::text) IS DISTINCT FROM
        ROW(1, 'x'::text) AS changed_pair;
```

Kết quả: TRUE và TRUE.

Điều này hữu ích khi kiểm tra một nhóm thuộc tính có thay đổi hay không:

```sql
WITH changes(
    old_status, old_note,
    new_status, new_note
) AS (
    VALUES
        ('NEW'::text, NULL::text, 'NEW'::text, NULL::text),
        ('NEW'::text, NULL::text, 'PAID'::text, NULL::text),
        ('NEW'::text, NULL::text, 'NEW'::text, 'done'::text)
)
SELECT
    old_status,
    old_note,
    new_status,
    new_note,
    ROW(old_status, old_note)
        IS DISTINCT FROM ROW(new_status, new_note) AS any_change
FROM changes;
```

Kết quả lần lượt FALSE, TRUE, TRUE.

Không nên lạm dụng so sánh `ROW(...)` chứa hàng trăm cột để quyết định cập nhật toàn bộ bản ghi: chi phí so sánh, ý nghĩa từng cột, kiểu dữ liệu có toán tử equality hay không và các trường được bỏ qua (ví dụ `updated_at`) cần được xác định.

### 24.1. Row-valued IS NULL có sắc thái riêng

Với row/composite values, PostgreSQL có quy tắc `IS NULL` đặc biệt: một row có thể được xem là NULL nếu bản thân row NULL hoặc **mọi trường của nó đều NULL**; `IS NOT NULL` có thể yêu cầu row không NULL và **mọi trường không NULL**. Vì thế với row chứa một số trường NULL và một số trường có giá trị, **cả `row IS NULL` lẫn `row IS NOT NULL` có thể là FALSE**.

Đây là khác biệt so với một scalar `x IS NULL` / `x IS NOT NULL` luôn là hai kết quả phủ định nhau. Trong bài toán thông thường, nên kiểm tra từng trường hoặc dùng `IS [NOT] DISTINCT FROM` với row nếu mục tiêu là so sánh null-safe cả bộ giá trị.

Ví dụ:

```sql
SELECT
    ROW(NULL::integer, 1) IS NULL AS row_is_null,
    ROW(NULL::integer, 1) IS NOT NULL AS row_is_not_null,
    ROW(NULL::integer, 1) IS DISTINCT FROM
        ROW(NULL::integer, 2) AS row_has_change;
```

Kết quả tương ứng: FALSE, FALSE, TRUE. Không dùng trực giác từ scalar để suy ra tính chất của composite values.

## 25. NULLIF và COALESCE: hai công cụ bổ sung

### 25.1. NULLIF(a,b)

`NULLIF(a,b)` trả NULL nếu `a` và `b` bằng nhau theo quy tắc biểu thức; nếu không, trả `a`.

```sql
SELECT
    NULLIF('', '') AS empty_to_null,
    NULLIF('A', '') AS nonempty_kept,
    NULLIF(0, 0) AS zero_to_null;
```

Một ứng dụng có thể dùng:

```sql
SELECT
    order_id,
    NULLIF(btrim(note), '') AS normalized_note
FROM demo_3vl.sales_order
ORDER BY order_id;
```

Cách này **biểu diễn** chuỗi rỗng hoặc chỉ toàn khoảng trắng mặc định của `btrim` thành NULL trong kết quả. Nó không tự cập nhật bảng.

### 25.2. COALESCE(a,b,...)

`COALESCE` chọn biểu thức đầu tiên **không NULL**:

```sql
SELECT
    order_id,
    COALESCE(note, '[NO NOTE]') AS note_display
FROM demo_3vl.sales_order
ORDER BY order_id;
```

Với note NULL, đầu ra là `'[NO NOTE]'`. Với note = `''`, kết quả vẫn là chuỗi rỗng vì `''` **không phải NULL**.

Nếu muốn xử lý cả hai:

```sql
SELECT
    order_id,
    COALESCE(NULLIF(btrim(note), ''), '[NO NOTE]') AS note_display
FROM demo_3vl.sales_order
ORDER BY order_id;
```

Đừng coi chuỗi `'[NO NOTE]'` là dữ liệu thực có trong bảng. Nó chỉ là giá trị biểu diễn mà query chọn khi cần.

### 25.3. COALESCE không thay thế IS DISTINCT FROM ở mọi nơi

Một cách so sánh thường thấy:

```sql
COALESCE(a, '<missing>') = COALESCE(b, '<missing>')
```

Nếu dữ liệu thực có thể nhận chuỗi `'<missing>'`, phép so sánh sẽ **coi NULL và chuỗi đó là bằng nhau**, tạo lỗi. Hơn nữa, ép kiểu, collation và kiểu cột có thể khiến cách này khó kiểm soát.

Khi yêu cầu đơn giản là **so sánh hai giá trị bao gồm NULL**, dùng trực tiếp:

```sql
a IS NOT DISTINCT FROM b
```

thường rõ nghĩa và tránh sentinel giả.

## 26. So sánh null-safe có phải chỉ là “NULL = NULL” không?

Không. `IS DISTINCT FROM` còn là lựa chọn để tránh mất hàng khi **một phía NULL và phía kia không NULL**, đặc biệt trong UPDATE và kiểm tra dữ liệu chênh lệch.

Ta có thể biểu diễn ý tưởng của `a IS DISTINCT FROM b` như sau:

```sql
CASE
    WHEN a IS NULL AND b IS NULL THEN FALSE
    WHEN a IS NULL OR b IS NULL THEN TRUE
    ELSE a <> b
END
```

Đây là mô tả logic cho các kiểu dữ liệu có so sánh equality/inequality phù hợp, **không phải lời khuyên thay toán tử PostgreSQL bằng CASE dài trong mọi query**.

Trong truy vấn thực tế, viết `IS DISTINCT FROM` giúp mục đích rõ hơn và thường tránh các lỗi khi tự lắp nhiều điều kiện OR/AND với UNKNOWN.

### 26.1. Không phải mọi kiểu dữ liệu có phép bằng giống nhau

`IS DISTINCT FROM` dựa trên ngữ nghĩa phép so sánh của kiểu dữ liệu. Với các kiểu như text, numeric, timestamp hoặc tuple của các kiểu có equality, nó có ý nghĩa rõ ràng.

Nhưng “khác nhau” không phải lúc nào cũng là so sánh **byte-for-byte**. Collation, kiểu dữ liệu, quy tắc so sánh và normalization có thể ảnh hưởng kết quả. Ví dụ, nếu nghiệp vụ coi hai email chỉ khác chữ hoa là tương đương, cần nêu quy tắc đó một cách tường minh (như xử lý chuẩn hóa/kiểu/collation thích hợp), không chờ `IS NOT DISTINCT FROM` tự làm việc đó.

## 27. IS DISTINCT FROM và chỉ mục: đúng trước, tối ưu sau

Vì `IS [NOT] DISTINCT FROM` dùng ngữ nghĩa so sánh riêng, không nên giả định planner sẽ luôn tối ưu nó giống hệt `=` hoặc `<>` với một index B-tree thông thường.

Ví dụ:

```sql
CREATE INDEX idx_customer_country_code
ON demo_3vl.customer(country_code);

EXPLAIN
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code IS NOT DISTINCT FROM 'VN';
```

Bảng lab có năm hàng nên `Seq Scan` có thể là kế hoạch tốt nhất. Ngay cả ở bảng lớn, việc PostgreSQL sử dụng index còn phụ thuộc **phiên bản, selectivity, biểu thức, kiểu dữ liệu, thống kê và khả năng chuyển điều kiện thành index condition**. Đừng suy ra toán tử có vẻ “giống bằng nhau” thì chắc chắn sinh cùng kế hoạch.

### 27.1. IS NULL có thể tận dụng index

B-tree trong PostgreSQL có thể lưu thông tin về NULL để phục vụ những truy vấn thích hợp. Ví dụ:

```sql
EXPLAIN
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code IS NULL;
```

Một index B-tree thường hoặc một partial index thiết kế cho truy vấn thiếu dữ liệu có thể hữu ích:

```sql
CREATE INDEX idx_customer_missing_country
ON demo_3vl.customer(customer_id)
WHERE country_code IS NULL;
```

Đây chỉ là ví dụ cho workload thường xuyên tìm khách thiếu country_code. Không tạo index bổ sung trên production nếu chưa đánh giá số hàng thiếu, kích thước bảng và chi phí ghi. Với năm hàng mẫu, planner có thể vẫn chọn Seq Scan.

### 27.2. Cẩn trọng khi thay toán tử để “ép index”

Nếu thay:

```sql
WHERE country_code IS NOT DISTINCT FROM $1
```

bằng:

```sql
WHERE country_code = $1
```

thì khi `$1` là NULL, **kết quả khác nhau**: toán tử thứ nhất tìm các hàng country_code NULL, còn phép bằng thứ hai trả UNKNOWN. Tối ưu hóa làm thay đổi ngữ nghĩa là lỗi logic, dù kế hoạch mới nhanh hơn.

Nếu bộ tham số có thể NULL và cần tối ưu, hãy thử tách hai nhánh query (`IS NULL` hoặc `=` khi tham số không NULL) tại tầng ứng dụng với **cùng ngữ nghĩa null-safe** và benchmark trên workload thực, thay vì bỏ mất trường hợp NULL.

## 28. JDBC: binding NULL và đọc boolean SQL

Trong ứng dụng Java, một cột nullable không nên được xử lý như primitive `boolean` luôn có hai trạng thái.

### 28.1. Đặt tham số NULL một cách rõ ràng

Ví dụ tìm khách theo email, bao gồm trường hợp tham số email là NULL:

```java
String sql = """
    SELECT customer_id, full_name, email
    FROM demo_3vl.customer
    WHERE email IS NOT DISTINCT FROM ?
    ORDER BY customer_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    String email = suppliedEmail; // Có thể null.
    if (email == null) {
        ps.setNull(1, java.sql.Types.VARCHAR);
    } else {
        ps.setString(1, email);
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("customer_id"));
        }
    }
}
```

`IS NOT DISTINCT FROM ?` giữ đúng ý nghĩa khi email được bind thành NULL. Nếu viết `WHERE email = ?`, một tham số NULL sẽ khiến phép so sánh UNKNOWN, không tìm được các hàng email NULL.

Cú pháp parameter `?` thuộc JDBC PreparedStatement; trong `psql`, bạn không thể copy nguyên query có `?` rồi mong nó là bind placeholder của JDBC.

### 28.2. Đọc boolean nullable với wasNull()

`ResultSet.getBoolean(...)` trả primitive `boolean`. Khi giá trị SQL là NULL, JDBC trả `false` và cần gọi `wasNull()` để biết giá trị đọc thực sự là NULL.

```java
boolean activeValue = rs.getBoolean("active");
boolean activeWasNull = rs.wasNull();

Boolean active = activeWasNull ? null : activeValue;
```

Nếu bỏ `wasNull()`, ứng dụng có thể đánh đồng một khách `active = FALSE` với một khách `active = NULL`. Nhiều framework hỗ trợ kiểu boxed `Boolean` để giữ ba trạng thái, nhưng cần kiểm tra mapping và cách dùng trong API/business logic.

### 28.3. Java null và SQL NULL không tự có cùng toán tử

Trong Java:

```java
Objects.equals(a, b)
```

cho `true` nếu cả hai tham chiếu đều null. Nhưng câu SQL:

```sql
a = b
```

không làm vậy đối với SQL NULL. Nếu muốn logic gần với `Objects.equals`, dùng `IS NOT DISTINCT FROM` cho kiểu dữ liệu có so sánh phù hợp.

Đừng dùng nối chuỗi để tạo điều kiện `... = NULL`; luôn dùng SQL có tham số và chọn toán tử đúng.

## 29. PostgreSQL statistics và khả năng tối ưu NULL

Bộ lập kế hoạch không xử lý NULL như một giá trị hoàn toàn không tồn tại. PostgreSQL có thống kê về tỷ lệ NULL của cột và những phân phối giá trị khác, thường xem qua `pg_stats`:

```sql
ANALYZE demo_3vl.customer;

SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals
FROM pg_stats
WHERE schemaname = 'demo_3vl'
  AND tablename = 'customer'
  AND attname IN ('email', 'country_code', 'active')
ORDER BY attname;
```

`null_frac` là **ước lượng tỷ lệ NULL** từ thống kê. Dữ liệu mẫu quá nhỏ nên số liệu không phản ánh workload lớn.

Khi so sánh kế hoạch:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code IS NULL;
```

và:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id
FROM demo_3vl.customer
WHERE country_code = 'VN';
```

cần hiểu planner có thể ước lượng số hàng khác nhau vì tỷ lệ NULL khác tần suất `'VN'`. Các lựa chọn Index Scan/Seq Scan vẫn dựa trên chi phí, thống kê và kích thước dữ liệu.

`EXPLAIN ANALYZE` thực thi câu SQL. Với các câu `UPDATE`/`DELETE`, không dùng nó trên production chỉ để xem kế hoạch nếu chưa chuẩn bị transaction và đánh giá side effect.

## 30. Trường hợp đặc biệt: JSON null và SQL NULL

PostgreSQL có kiểu `JSONB` với một giá trị JSON `null`. **JSON null** không hoàn toàn là **SQL NULL**.

```sql
SELECT
    'null'::jsonb IS NULL AS json_null_is_sql_null,
    NULL::jsonb IS NULL AS sql_null_is_sql_null,
    'null'::jsonb IS NOT DISTINCT FROM NULL::jsonb
        AS json_null_equals_sql_null;
```

Kết quả: FALSE, TRUE, FALSE. Một giá trị JSONB chứa literal JSON `null` vẫn là một **giá trị JSONB không phải SQL NULL**.

Ví dụ trích xuất key có thể tạo NULL theo cách khác:

```sql
SELECT
    ('{"name": null}'::jsonb -> 'name') AS json_null_value,
    ('{"name": null}'::jsonb ->> 'name') AS text_extraction,
    ('{}'::jsonb -> 'name') AS missing_key;
```

Thông thường:

- Toán tử `->` trả JSONB null khi key tồn tại với giá trị JSON null.
- Toán tử `->>` trả SQL NULL khi trích xuất JSON null thành text.
- Key không tồn tại có thể cho SQL NULL khi dùng các toán tử truy xuất này.

Khi so sánh, phải biết biểu thức đang mang kiểu `jsonb` hay `text` và đang trả SQL NULL hay JSON null. Đây là nguyên nhân thường gặp khi lọc dữ liệu API trong bảng JSONB.

## 31. Cách viết điều kiện an toàn theo ý nghĩa nghiệp vụ

| Ý định | Điều kiện nên cân nhắc | Vì sao |
|---|---|---|
| Email chưa có | `email IS NULL` | Kiểm tra thiếu giá trị |
| Email đã có | `email IS NOT NULL` | Không nhầm chuỗi rỗng với NULL |
| Đã xác nhận active | `active IS TRUE` | Chỉ TRUE |
| Đã xác nhận inactive | `active IS FALSE` | Chỉ FALSE |
| Không được xác nhận active | `active IS NOT TRUE` | FALSE hoặc NULL |
| Quốc gia chắc chắn khác VN | `country_code IS NOT NULL AND country_code <> 'VN'` | Không biến “chưa biết” thành “khác VN” |
| Giá trị lưu khác VN kể cả NULL | `country_code IS DISTINCT FROM 'VN'` | Phân biệt NULL với một giá trị cụ thể |
| Khớp hai giá trị kể cả cả hai NULL | `a IS NOT DISTINCT FROM b` | Null-safe equality |
| Phát hiện thay đổi bao gồm chuyển sang/từ NULL | `old_value IS DISTINCT FROM new_value` | Luôn trả boolean rõ |
| Tìm khách không có đơn | `NOT EXISTS (SELECT 1 ... WHERE o.customer_id = c.customer_id)` | Dựa vào sự tồn tại hàng, không so cột nullable |
| Loại danh sách có thể chứa NULL | `NOT EXISTS` hoặc lọc NULL đúng nghiệp vụ | Tránh bẫy NOT IN |
| Chỉ lấy ghi chú có nội dung | `note IS NOT NULL AND btrim(note) <> ''` | NULL và chuỗi rỗng là hai trường hợp |
| Chưa có thời điểm thanh toán | `paid_at IS NULL` | Kiểm tra trạng thái thiếu timestamp |
| Chỉ những đơn số tiền dương đã biết | `amount > 0` | NULL sẽ bị loại bởi WHERE; có thể thêm IS NOT NULL để rõ ý |

Không có công thức “luôn dùng IS DISTINCT FROM thay cho =”. Khi cần semantics SQL chuẩn của `=`, hoặc khi cột đã `NOT NULL` và tham số chắc chắn không NULL, `=` thường ngắn gọn và phù hợp. `IS DISTINCT FROM` là công cụ để **chủ động quyết định cách xử lý NULL**, không phải quy tắc viết mọi phép so sánh.

## 32. Các hiểu lầm thường gặp

**“NULL là một giá trị đặc biệt nên NULL = NULL phải TRUE.”** Không đúng trong phép `=` SQL thông thường: kết quả là UNKNOWN. Nếu muốn null-safe equality, dùng `IS NOT DISTINCT FROM`.

**“WHERE giữ mọi hàng không có điều kiện FALSE.”** Không đúng. `WHERE` chỉ giữ TRUE; UNKNOWN cũng bị loại.

**“NOT biến UNKNOWN thành TRUE.”** Không đúng. `NOT UNKNOWN` vẫn UNKNOWN.

**“column <> 'X' bao gồm NULL.”** Không đúng. Với NULL, phép `<>` cho UNKNOWN; muốn bao gồm giá trị thiếu theo ý nghĩa khác biệt, dùng `IS DISTINCT FROM`.

**“NOT IN luôn là cách viết ngắn của NOT EXISTS.”** Không đúng khi có NULL và khi điều kiện so khớp khác nhau. Phải xác định null semantics trước khi thay.

**“LEFT JOIN giữ tất cả hàng bên trái dù đặt mọi điều kiện trong WHERE.”** Không đúng. `WHERE` sau outer join có thể loại những hàng không có match do NULL ở các cột phải.

**“CHECK (quantity > 0) tự cấm NULL.”** Không đúng. CHECK chấp nhận UNKNOWN, cần `NOT NULL` nếu cột bắt buộc.

**“UNIQUE nghĩa là cột không được NULL.”** Không đúng. Unique thông thường cho phép nhiều NULL; NOT NULL là constraint riêng.

**“Đổi mọi NULL thành 0 trước SUM/AVG luôn giúp báo cáo tốt hơn.”** Không đúng. Có thể làm sai mẫu số, phân phối hoặc làm mất thông tin thiếu.

**“IS NOT DISTINCT FROM luôn dùng index y hệt =.”** Không được bảo đảm. Cần xem kế hoạch trên phiên bản và dữ liệu thực.

**“NULL trong JSONB và SQL NULL là một.”** Không đúng. JSON literal `null` được chứa trong một giá trị JSONB không NULL, còn SQL NULL là thiếu giá trị SQL.

## 33. Bài tập thực hành

### Bài 1 — Ba kết quả của một phép so sánh

Dự đoán kết quả:

```sql
SELECT
    (10 = 10) AS a,
    (10 = 20) AS b,
    (10 = NULL::integer) AS c,
    (NULL::integer = NULL::integer) AS d;
```

**Đáp án:** TRUE, FALSE, UNKNOWN, UNKNOWN.

### Bài 2 — Hai truy vấn không tương đương

```sql
SELECT customer_id FROM demo_3vl.customer
WHERE country_code <> 'VN';

SELECT customer_id FROM demo_3vl.customer
WHERE country_code IS DISTINCT FROM 'VN';
```

**Câu hỏi:** trên dữ liệu mẫu ban đầu, khác nhau ở hàng nào?

**Đáp án:** truy vấn đầu chỉ lấy khách có mã đã biết khác VN, tức khách 5 (`US`). Truy vấn sau còn có khách 3 và 4 có mã NULL vì NULL được coi là khác `'VN'` trong phép `IS DISTINCT FROM`.

Nếu đã chạy UPDATE trong bài trước, dữ liệu thực tế có thể khác. Khi luyện các bài độc lập, hãy bắt đầu từ tập dữ liệu mẫu ban đầu.

### Bài 3 — NOT IN với NULL

Dự đoán:

```sql
SELECT
    9 NOT IN (1, 2, NULL) AS a,
    9 NOT IN (1, 2) AS b,
    2 NOT IN (1, 2, NULL) AS c;
```

**Đáp án:** UNKNOWN, TRUE, FALSE. Lý do: ở `a` không có match nhưng có phép so với NULL; ở `b` mọi phép so sánh đều cho FALSE rồi được phủ định; ở `c` có một match rõ ràng.

### Bài 4 — Lọc boolean chưa xác định

**Yêu cầu:** lấy khách đã biết inactive **hoặc** chưa xác định trạng thái active.

```sql
SELECT customer_id, full_name, active
FROM demo_3vl.customer
WHERE active IS NOT TRUE
ORDER BY customer_id;
```

**Đáp án:** khách 2, 3, 5 trên dữ liệu ban đầu. Không dùng `WHERE NOT active` nếu muốn bao gồm NULL.

### Bài 5 — Tìm khách không có đơn

**Yêu cầu:** liệt kê khách không xuất hiện trong bảng `sales_order`.

```sql
SELECT c.customer_id, c.full_name
FROM demo_3vl.customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_3vl.sales_order AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

**Đáp án:** khách 4 theo dữ liệu ban đầu. `EXISTS` xét có hàng thỏa điều kiện, không cần chọn một cột nullable ở bảng đơn.

### Bài 6 — CHECK có cho NULL không?

```sql
CREATE TABLE demo_3vl.exercise_check (
    id INTEGER PRIMARY KEY,
    score INTEGER CHECK (score BETWEEN 0 AND 100)
);

INSERT INTO demo_3vl.exercise_check (id, score)
VALUES (1, NULL);
```

**Câu hỏi:** lệnh INSERT có hợp lệ không?

**Đáp án:** có, vì CHECK cho UNKNOWN. Nếu bắt buộc phải có score, dùng `NOT NULL` cùng CHECK.

### Bài 7 — Đếm dữ liệu thiếu không làm sai trung bình

**Yêu cầu:** tính số đơn, số đơn biết amount, số đơn thiếu amount và trung bình amount đã biết.

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(amount) AS known_amount,
    COUNT(*) FILTER (WHERE amount IS NULL) AS missing_amount,
    AVG(amount) AS avg_known_amount
FROM demo_3vl.sales_order;
```

**Đáp án:** trên tập mẫu ban đầu có 5 đơn, 4 đơn biết amount, 1 đơn thiếu; trung bình được tính trên bốn amount đã biết. Không dùng `AVG(COALESCE(amount, 0))` nếu “chưa biết” không có nghĩa là 0.

### Bài 8 — Phát hiện cập nhật thật sự

```sql
SELECT
    NULL::text IS DISTINCT FROM NULL::text AS a,
    NULL::text IS DISTINCT FROM 'A'::text AS b,
    'A'::text IS DISTINCT FROM 'A'::text AS c,
    'A'::text IS DISTINCT FROM 'B'::text AS d;
```

**Đáp án:** FALSE, TRUE, FALSE, TRUE. Toán tử trả boolean xác định và phù hợp với việc so sánh before/after có thể NULL.

### Bài 9 — JOIN khi hai khóa NULL

**Câu hỏi:** nếu A và B cùng có `code NULL`, điều kiện `A.code = B.code` có nối chúng không?

**Đáp án:** không, vì điều kiện UNKNOWN. `A.code IS NOT DISTINCT FROM B.code` sẽ coi chúng là match. Nhưng việc đó có đúng nghiệp vụ không phải phụ thuộc loại “code” và ý nghĩa NULL.

### Bài 10 — Sửa CASE bị hiểu nhầm

Một báo cáo dùng:

```sql
CASE WHEN amount > 0 THEN 'POSITIVE' ELSE 'NON_POSITIVE' END
```

**Yêu cầu:** bổ sung trạng thái khi amount NULL.

```sql
CASE
    WHEN amount IS NULL THEN 'UNKNOWN'
    WHEN amount > 0 THEN 'POSITIVE'
    ELSE 'NON_POSITIVE'
END
```

**Đáp án:** searched CASE với kiểm tra NULL tường minh giúp báo cáo không vô tình gọi dữ liệu thiếu là không dương.

## 34. Checklist trước khi triển khai điều kiện có NULL

Khi một query có cột nullable hoặc parameter có thể NULL, hãy hỏi:

1. Cột có thể NULL theo DDL **và theo dữ liệu thực tế** không?
2. NULL mang nghĩa “chưa biết”, “không áp dụng”, hay trạng thái cần xử lý riêng?
3. Biểu thức `=` / `<>` có thể trở thành UNKNOWN không?
4. `WHERE`, `HAVING`, `ON` và `CASE WHEN` xử lý UNKNOWN như thế nào?
5. Nếu dùng `NOT IN`, subquery hoặc danh sách bên phải có thể chứa NULL không?
6. Nếu dùng outer join, điều kiện phía phải có được đặt đúng ở `ON` hoặc `WHERE` không?
7. Nếu cần so sánh thay đổi, có nên dùng `IS DISTINCT FROM` không?
8. Nếu cần khớp kể cả NULL ở hai phía, việc đó có đúng nghĩa hay làm tăng số cặp join giả?
9. Với `CHECK` và `UNIQUE`, NULL được chấp nhận theo chính sách nào?
10. `SUM`, `AVG`, `COUNT`, `DISTINCT`, `GROUP BY` có bỏ qua hay gom NULL như mong muốn không?
11. Ứng dụng JDBC/ORM có phân biệt NULL và FALSE/0/chuỗi rỗng không?
12. Sau khi điều kiện đúng, có cần đo `EXPLAIN` để xem hiệu năng trên dữ liệu thật không?

Một câu SQL ngắn chưa chắc có nghĩa đơn giản. Với NULL, phần quan trọng nhất là **ghi rõ ý định của phép so sánh**.

## 35. Sơ đồ tổng kết

```text
                     GIÁ TRỊ SQL
                         │
               ┌─────────┴──────────┐
               │                    │
               ▼                    ▼
         Giá trị đã biết           NULL
               │                    │
               ▼                    ▼
           =, <>, <, >        =, <>, <, >
               │                    │
               ▼                    ▼
        TRUE hoặc FALSE           UNKNOWN
               │                    │
               └──────────┬─────────┘
                          ▼
                 AND / OR / NOT
                          │
                          ▼
                TRUE / FALSE / UNKNOWN
                          │
            ┌─────────────┴────────────┐
            │                          │
            ▼                          ▼
       WHERE/HAVING/ON             CASE WHEN
       chỉ nhận TRUE              chỉ chọn TRUE
            │                          │
            ▼                          ▼
      Chọn hàng/khớp join        Chọn nhánh kết quả

ĐỂ KIỂM TRA NULL:
  x IS NULL / x IS NOT NULL        → TRUE hoặc FALSE

ĐỂ SO SÁNH NULL-SAFE:
  a IS DISTINCT FROM b            → khác nhau, kể cả khác NULL
  a IS NOT DISTINCT FROM b        → tương đương, kể cả cả hai NULL

TRONG MÔ HÌNH DỮ LIỆU:
  NOT NULL                         → cấm NULL
  CHECK                            → FALSE bị từ chối, UNKNOWN thường hợp lệ
  UNIQUE mặc định                  → có thể cho nhiều NULL
  UNIQUE NULLS NOT DISTINCT (15+)  → coi NULL trùng khi kiểm tra unique

TRONG BÁO CÁO:
  COUNT(*)                         → đếm mọi hàng
  COUNT(x)                         → chỉ đếm x khác NULL
  SUM(x), AVG(x)                   → bỏ qua NULL trong input
  DISTINCT / GROUP BY              → gom NULL theo quy tắc tập kết quả
```

Năm nguyên tắc cần nhớ:

1. **NULL đưa phép so sánh thông thường vào logic ba giá trị.** `NULL = NULL` và `value <> NULL` không trả TRUE hoặc FALSE mà thường trả UNKNOWN.
2. **WHERE chỉ giữ TRUE.** FALSE và UNKNOWN đều không vào kết quả; vì thế `NOT` không tự “cứu” những hàng có NULL.
3. **IS DISTINCT FROM và IS NOT DISTINCT FROM giải quyết so sánh nullable.** Chúng luôn trả boolean xác định và hữu ích cho phát hiện thay đổi, đồng bộ dữ liệu hoặc khớp NULL có chủ đích.
4. **NULL có ngữ nghĩa theo từng ngữ cảnh.** `NOT IN`, outer join, CHECK, UNIQUE, GROUP BY, COUNT và AVG đều có quy tắc khác nhau cần hiểu rõ, không chỉ áp một câu “NULL là không biết”.
5. **Tính đúng nghĩa nghiệp vụ quan trọng hơn cú pháp ngắn.** “Chưa biết quốc gia” không tự là “ngoài Việt Nam”; “chưa có amount” không tự là 0; “hai mã tham chiếu đều thiếu” không có nghĩa chúng cùng trỏ một thực thể.

Khi một truy vấn PostgreSQL trả ít hàng hơn mong đợi hoặc bộ lọc “khác giá trị” không hoạt động với NULL, hãy kiểm tra ba điều theo thứ tự: **biểu thức có thể là UNKNOWN không, WHERE/JOIN xử lý UNKNOWN ra sao, và nghiệp vụ thật sự muốn NULL được đối xử thế nào?** Trả lời ba câu hỏi đó thường giúp tìm đúng lỗi mà không cần thêm nhiều điều kiện chắp vá.
