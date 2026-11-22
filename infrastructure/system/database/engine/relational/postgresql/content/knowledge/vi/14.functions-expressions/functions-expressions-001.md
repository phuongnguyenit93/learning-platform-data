# Toán tử, độ ưu tiên và đánh giá biểu thức trong PostgreSQL

Một câu SQL có thể chứa nhiều phép toán cùng lúc: cộng trừ, so sánh, nối chuỗi, kiểm tra `NULL`, điều kiện `AND`/`OR`, truy xuất JSONB, ép kiểu và gọi hàm. PostgreSQL phải hiểu **phép nào gắn với toán hạng nào** trước khi có thể xử lý dữ liệu.

Hãy so sánh:

```sql
SELECT 10 + 5 * 2 AS result_a;
SELECT (10 + 5) * 2 AS result_b;
```

Kết quả lần lượt là **20** và **30**. Cùng các con số, chỉ khác dấu ngoặc nhưng biểu thức đã thay đổi ý nghĩa. Trong một câu `WHERE` phức tạp, sai thứ tự `AND`/`OR` có thể khiến đơn hàng bị lọc nhầm; trong báo cáo tài chính, ép kiểu hoặc chia số nguyên có thể làm mất phần thập phân; trong truy vấn JSONB, đặt `::integer` sai vị trí có thể gây lỗi.

Bài học thuộc chương **Hàm và biểu thức** của PostgreSQL, giúp bạn:

- Nhận diện các nhóm **toán tử và cấu trúc biểu thức**.
- Hiểu **độ ưu tiên** (*precedence*) và **tính kết hợp** (*associativity*).
- Dùng dấu ngoặc để thể hiện đúng quy tắc nghiệp vụ.
- Phân biệt **cách phân tích cú pháp** với **thứ tự đánh giá khi chạy truy vấn**.
- Hiểu logic **TRUE / FALSE / UNKNOWN** khi biểu thức chứa `NULL`.
- Tránh phụ thuộc vào **short-circuit** không được đảm bảo trong điều kiện SQL.
- Viết biểu thức an toàn với `CASE`, `COALESCE`, `NULLIF` và ép kiểu rõ ràng.
- Kết hợp toán tử PostgreSQL dành cho mảng, JSONB, chuỗi, thời gian và phép so sánh.

Tài liệu sử dụng các ví dụ độc lập và một schema thử nghiệm để có thể tự kiểm tra kết quả.

## 1. Biểu thức trong SQL là gì?

**Biểu thức (expression)** là một cấu trúc được PostgreSQL đánh giá để tạo ra một giá trị hoặc một kết quả logic. Một biểu thức có thể gồm:

- **Hằng số:** `100`, `'PAID'`, `DATE '2026-01-01'`, `TRUE`, `NULL`.
- **Tham chiếu cột:** `amount`, `o.status`, `payload`.
- **Toán tử:** `+`, `*`, `=`, `<>`, `AND`, `OR`, `||`, `->>`.
- **Hàm:** `round(...)`, `lower(...)`, `date_trunc(...)`, `nullif(...)`.
- **Ép kiểu:** `amount::numeric`, `CAST(value AS integer)`.
- **Biểu thức điều kiện:** `CASE WHEN ... THEN ... ELSE ... END`.
- **Truy vấn con:** `EXISTS (SELECT ...)` hoặc subquery trả về một giá trị.

Ví dụ:

```sql
SELECT
    120000::numeric(12, 2) AS gross_amount,
    120000::numeric(12, 2) - 10000 AS net_amount,
    (120000 - 10000) >= 100000 AS reached_target,
    CASE
        WHEN (120000 - 10000) >= 100000 THEN 'Đạt'
        ELSE 'Chưa đạt'
    END AS evaluation;
```

Mỗi mục ở danh sách `SELECT` là một biểu thức có giá trị và kiểu dữ liệu xác định. Không phải toán tử nào cũng trả về Boolean: `+` trả số, `||` có thể trả chuỗi, `->>` trả văn bản từ JSON, còn `IS NULL` trả Boolean.

### 1.1. Toán tử một ngôi và hai ngôi

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Một ngôi (*unary*) | `-amount` | Đổi dấu của giá trị số |
| Một ngôi | `NOT condition` | Phủ định biểu thức Boolean |
| Hai ngôi (*binary*) | `amount - discount` | Trừ hai giá trị |
| Hai ngôi | `a = b` | So sánh bằng |
| Hai ngôi | `text_a || text_b` | Nối chuỗi với kiểu toán hạng phù hợp |
| Hai ngôi | `payload ->> 'source'` | Lấy một trường JSON dưới dạng text |

Cùng một ký hiệu có thể mang nhiều nghĩa tùy kiểu toán hạng. Ví dụ `-` trong `-5` là một ngôi, còn `10 - 5` là hai ngôi.

### 1.2. PostgreSQL hỗ trợ nạp chồng toán tử

PostgreSQL có cơ chế **operator overloading**: cùng một tên toán tử có thể được định nghĩa cho nhiều kiểu dữ liệu.

Ví dụ `||` có thể nối `TEXT`, mảng hoặc dữ liệu JSONB theo các quy tắc tương ứng; `@>` có thể mang nghĩa “chứa” trong JSONB, mảng hoặc range. Không nên chỉ nhìn ký hiệu mà đoán kết quả; phải xét **kiểu dữ liệu của toán hạng và định nghĩa operator đã được phân giải**.

## 2. Độ ưu tiên: PostgreSQL phân tích biểu thức ra sao?

**Độ ưu tiên (operator precedence)** quy định những cấu trúc nào được **gắn kết trước về cú pháp** khi biểu thức không có dấu ngoặc. Đây là quy tắc của bộ phân tích cú pháp, khác với câu hỏi “phần nào được executor thực hiện trước theo thời gian”.

Ví dụ:

```sql
SELECT
    10 + 5 * 2     AS without_parentheses,
    10 + (5 * 2)   AS explicit_default,
    (10 + 5) * 2   AS changed_meaning;
```

Kết quả: `20`, `20` và `30`.

Vì phép nhân có độ ưu tiên cao hơn phép cộng, biểu thức đầu được hiểu như biểu thức thứ hai. Dấu ngoặc trong biểu thức thứ ba **cố ý thay đổi cách nhóm phép toán**.

### 2.1. Bảng độ ưu tiên thường gặp

Bảng dưới đây trình bày **từ mức ưu tiên cao xuống thấp** theo quy tắc của PostgreSQL hiện đại:

| Mức | Cú pháp / toán tử | Vai trò |
| ---: | --- | --- |
| 1 | `.` | Dấu phân tách tên bảng/cột hoặc truy cập trường theo cú pháp phù hợp |
| 2 | `::` | Ép kiểu theo cú pháp PostgreSQL |
| 3 | `[ ]` | Truy cập phần tử hoặc lát cắt mảng |
| 4 | `+`, `-` một ngôi | Dấu dương và dấu âm |
| 5 | `COLLATE` | Chọn collation cho biểu thức |
| 6 | `AT` | Các cấu trúc như `AT TIME ZONE` |
| 7 | `^` | Lũy thừa |
| 8 | `*`, `/`, `%` | Nhân, chia, chia lấy dư |
| 9 | `+`, `-` hai ngôi | Cộng, trừ |
| 10 | Các toán tử khác | Ví dụ `||`, `->`, `->>`, `@>` hoặc toán tử người dùng định nghĩa |
| 11 | `BETWEEN`, `IN`, `LIKE`, `ILIKE`, `SIMILAR` | Kiểm tra tập, khoảng, mẫu chuỗi |
| 12 | `<`, `>`, `=`, `<=`, `>=`, `<>` | So sánh thông thường |
| 13 | `IS`, `ISNULL`, `NOTNULL` | Các phép kiểm tra như `IS NULL` |
| 14 | `NOT` | Phủ định Boolean |
| 15 | `AND` | Hội logic |
| 16 | `OR` | Tuyển logic |

Một số cấu trúc SQL có quy tắc ngữ pháp riêng; không nên dùng bảng này như công thức máy móc để phân tích mọi cách viết `NOT BETWEEN`, `IS DISTINCT FROM` hoặc toán tử tùy biến phức tạp. **Dấu ngoặc luôn là cách rõ ràng nhất để thể hiện ý định.**

Trong PostgreSQL, hầu hết toán tử ở cùng bậc có quy tắc kết hợp xác định. Đặc biệt, toán tử lũy thừa `^` của PostgreSQL được kết hợp **từ trái sang phải**, khác với một số công cụ toán học.

### 2.2. Tính kết hợp: cùng độ ưu tiên thì nhóm thế nào?

```sql
SELECT
    20 - 5 - 3 AS left_associative,
    20 - (5 - 3) AS grouped_right;
```

Kết quả:

```text
left_associative = 12    -- (20 - 5) - 3
grouped_right    = 18    -- 20 - (5 - 3)
```

Cả hai dấu `-` hai ngôi có cùng bậc, và cách phân tích thông thường gắn từ trái sang phải.

Ví dụ riêng của PostgreSQL:

```sql
SELECT
    2 ^ 3 ^ 2       AS left_associative_power,
    2 ^ (3 ^ 2)     AS explicit_right_power;
```

Kết quả lần lượt là **64** và **512**: `(2 ^ 3) ^ 2 = 64`, trong khi `2 ^ (3 ^ 2) = 512`. Không mang giả định từ Python hay máy tính cầm tay sang PostgreSQL khi dùng lũy thừa.

### 2.3. Dấu âm một ngôi và lũy thừa

Khi dấu âm và phép lũy thừa xuất hiện cùng nhau, hãy dùng dấu ngoặc để tránh hiểu nhầm về quy tắc ưu tiên:

```sql
SELECT
    -(2 ^ 2) AS negative_power,
    (-2) ^ 2 AS power_of_negative;
```

Kết quả lần lượt là **-4** và **4**. Biểu thức có dấu ngoặc vừa dễ kiểm tra vừa dễ chuyển sang ngôn ngữ khác với quy tắc ưu tiên có thể khác.

## 3. Nhóm toán tử số học

Các toán tử số học thường gặp:

| Toán tử | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `+` | `7 + 3` | Cộng |
| `-` | `7 - 3` | Trừ |
| `*` | `7 * 3` | Nhân |
| `/` | `7 / 3` | Chia |
| `%` | `7 % 3` | Chia lấy dư với kiểu hỗ trợ |
| `^` | `2 ^ 3` | Lũy thừa với kiểu hỗ trợ |
| `-value` | `-7` | Đổi dấu |

Ví dụ:

```sql
SELECT
    7 + 3 AS sum_value,
    7 - 3 AS difference,
    7 * 3 AS product,
    7 % 3 AS remainder,
    2 ^ 3 AS power_value;
```

### 3.1. Chia số nguyên và chia thập phân

Trong PostgreSQL, kết quả phụ thuộc vào **kiểu của các toán hạng**:

```sql
SELECT
    7 / 2 AS integer_division,
    7::numeric / 2 AS numeric_division,
    7.0 / 2 AS decimal_division;
```

Với phép chia số nguyên, phần lẻ bị bỏ: `7 / 2 = 3`. Khi ít nhất một toán hạng được đưa về kiểu số thập phân phù hợp, kết quả có thể là `3.5`.

Đây là bẫy trong phép tính tỷ lệ:

```sql
-- Có thể làm mất phần thập phân nếu cả hai là integer.
SELECT 1 / 4 AS incorrect_rate;

-- Ép kiểu rõ ràng để giữ phần thập phân.
SELECT 1::numeric / 4 AS correct_rate;
```

Kết quả lần lượt là `0` và `0.25`.

### 3.2. Numeric, floating point và tiền tệ

Khi tính giá chốt, giảm giá hoặc số liệu cần thập phân chính xác:

```sql
SELECT
    (120000::numeric(12, 2) - 10000) / 3
        AS amount_per_part;
```

`NUMERIC` phù hợp cho những phép tính thập phân có yêu cầu chính xác; `REAL` và `DOUBLE PRECISION` biểu diễn floating point nhị phân và có thể có sai số làm tròn. Dù dùng `NUMERIC`, vẫn phải định nghĩa **lúc nào làm tròn, dùng bao nhiêu chữ số và xử lý đơn vị tiền nào**.

Nếu làm tròn từng dòng trước khi cộng và làm tròn tổng sau khi cộng, hai kết quả có thể khác nhau. Đó là quyết định nghiệp vụ và cần được thể hiện bằng dấu ngoặc/công thức rõ ràng.

### 3.3. Phép toán không tự bảo vệ lỗi tràn và chia cho 0

```sql
-- KHÔNG chạy nếu không muốn phát sinh lỗi division_by_zero:
-- SELECT 100 / 0;
```

Toán hạng có kiểu `INTEGER`/`BIGINT` cũng có giới hạn miền giá trị. Một phép toán vượt giới hạn kiểu có thể báo lỗi thay vì tự chuyển thành số lớn vô hạn. Khi tính số lượng rất lớn hoặc tiền, chọn kiểu dữ liệu và cách ép kiểu có chủ đích.

## 4. Nhóm toán tử so sánh

Các phép so sánh phổ biến:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `=` | Bằng | `status = 'PAID'` |
| `<>` hoặc `!=` | Không bằng | `status <> 'CANCELLED'` |
| `<` | Nhỏ hơn | `amount < 100000` |
| `<=` | Nhỏ hơn hoặc bằng | `amount <= 100000` |
| `>` | Lớn hơn | `amount > 0` |
| `>=` | Lớn hơn hoặc bằng | `amount >= 50000` |

Kết quả của các phép so sánh thông thường thường thuộc kiểu `BOOLEAN`: `TRUE` hoặc `FALSE`, hoặc `NULL/UNKNOWN` nếu toán hạng thiếu dữ liệu.

Ví dụ:

```sql
SELECT
    100 >= 100 AS inclusive_threshold,
    100 > 100 AS exclusive_threshold,
    'PAID' = 'PENDING' AS different_status;
```

Kết quả: `TRUE`, `FALSE` và `FALSE`.

### 4.1. So sánh văn bản phụ thuộc kiểu và collation

Với chuỗi, phép `=`, `<`, `>` và `ORDER BY` có thể chịu ảnh hưởng của collation. Không nên coi việc sắp xếp chuỗi trên mọi database/locale là giống thứ tự số hoặc giống phép so từng byte.

Ví dụ chọn collation có chủ đích:

```sql
SELECT
    'b' COLLATE "C" > 'a' COLLATE "C"
        AS binary_style_comparison;
```

Với ví dụ ASCII đơn giản này kết quả là `TRUE`. Trong hệ thống hỗ trợ nhiều ngôn ngữ, collation, case folding và Unicode cần chính sách cụ thể; đừng dùng `lower(...)` một cách máy móc để thay thế mọi quy tắc nhận diện tên người hoặc email.

### 4.2. Toán tử so sánh không thay thế ràng buộc dữ liệu

Biểu thức:

```sql
WHERE quantity > 0
```

chỉ lọc kết quả truy vấn. Muốn ngăn dữ liệu quantity âm **khi INSERT/UPDATE**, cần thêm `CHECK(quantity > 0)` và `NOT NULL` nếu quantity là bắt buộc. SQL query đúng không có nghĩa database đã bảo vệ bất biến lúc ghi.

## 5. Logic Boolean: NOT, AND, OR

Ba toán tử điều kiện cơ bản:

| Toán tử | Nghĩa | Ví dụ |
| --- | --- | --- |
| `NOT` | Phủ định | `NOT is_active` |
| `AND` | Cả hai điều kiện cùng đúng | `status='PAID' AND amount>0` |
| `OR` | Ít nhất một điều kiện đúng | `status='PAID' OR status='PENDING'` |

**Thứ tự ưu tiên logic**:

```text
NOT   cao nhất
AND   tiếp theo
OR    thấp nhất
```

Do đó:

```sql
WHERE status = 'PAID'
   OR status = 'PENDING' AND amount >= 100000
```

được hiểu là:

```sql
WHERE status = 'PAID'
   OR (status = 'PENDING' AND amount >= 100000)
```

Không phải:

```sql
WHERE (status = 'PAID' OR status = 'PENDING')
  AND amount >= 100000
```

Hai logic phục vụ hai câu hỏi khác nhau:

- **Câu 1:** lấy mọi đơn PAID **hoặc** đơn PENDING từ 100.000 trở lên.
- **Câu 2:** chỉ lấy các đơn PAID/PENDING **có tiền từ 100.000 trở lên**.

### 5.1. Ví dụ Boolean rõ ràng

```sql
SELECT
    (TRUE OR FALSE AND FALSE) AS default_precedence,
    ((TRUE OR FALSE) AND FALSE) AS grouped_condition,
    NOT FALSE AND TRUE AS negation_then_and;
```

Kết quả lần lượt: `TRUE`, `FALSE`, `TRUE`.

### 5.2. Khi nào nên dùng ngoặc dù không bắt buộc?

Trong điều kiện chứa cả `AND` lẫn `OR`, nên đặt ngoặc để thể hiện **nhóm quy tắc nghiệp vụ**, ví dụ:

```sql
WHERE (status IN ('PAID', 'PENDING'))
  AND (amount >= 100000 OR customer_id = 1)
```

Ngay cả khi người đọc biết bảng ưu tiên, ngoặc giúp kiểm tra yêu cầu dễ hơn và hạn chế sai khi chỉnh sửa.

Không nên thêm ngoặc vô hạn quanh mọi biểu thức đơn giản; mục tiêu là **làm rõ ý nghĩa**, không làm SQL khó đọc hơn.

## 6. NULL và logic ba giá trị

Trong SQL, `NULL` thường biểu diễn dữ liệu không được biết hoặc không có giá trị. Nó **không bằng số 0**, **không bằng chuỗi rỗng** và **không giống FALSE**.

Khi so sánh với `NULL`:

```sql
SELECT
    (NULL::integer = 1) AS null_equals_one,
    (NULL::integer = NULL::integer) AS two_nulls_equal,
    (NULL::integer <> 1) AS null_not_equal_one;
```

Cả ba biểu thức đều trả **NULL/UNKNOWN**, không phải TRUE hoặc FALSE.

### 6.1. Bảng chân trị AND với UNKNOWN

| A | B | A AND B |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | UNKNOWN | **FALSE** |
| UNKNOWN | UNKNOWN | UNKNOWN |

Tại sao `FALSE AND UNKNOWN = FALSE`? Vì chỉ cần một vế đã sai, cả phép hội chắc chắn sai bất kể vế còn lại là gì.

### 6.2. Bảng chân trị OR với UNKNOWN

| A | B | A OR B |
| --- | --- | --- |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | **TRUE** |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

`TRUE OR UNKNOWN = TRUE` vì đã có một vế chắc chắn đúng.

### 6.3. NOT và UNKNOWN

```sql
SELECT
    NOT TRUE AS not_true,
    NOT FALSE AS not_false,
    NOT NULL::boolean AS not_unknown;
```

Kết quả: `FALSE`, `TRUE`, `NULL`.

**Phủ định UNKNOWN vẫn là UNKNOWN**, không biến thành TRUE.

### 6.4. WHERE chỉ giữ biểu thức TRUE

`WHERE` không giữ những hàng có điều kiện `FALSE` hoặc `UNKNOWN`.

Ví dụ:

```sql
WHERE status <> 'PAID'
```

không trả các hàng `status IS NULL`, vì `NULL <> 'PAID'` là UNKNOWN. Nếu nghiệp vụ muốn lấy cả trạng thái chưa xác định:

```sql
WHERE status <> 'PAID'
   OR status IS NULL
```

hoặc sử dụng so sánh có chủ đích với `IS DISTINCT FROM`, như phần tiếp theo.

## 7. IS NULL, IS DISTINCT FROM và so sánh an toàn với NULL

Để kiểm tra thiếu dữ liệu:

```sql
SELECT
    NULL::integer IS NULL AS is_null,
    NULL::integer IS NOT NULL AS is_not_null;
```

Kết quả là `TRUE` và `FALSE`.

**Không dùng**:

```sql
-- SAI về ngữ nghĩa: không trả TRUE khi value là NULL.
-- WHERE value = NULL
```

### 7.1. IS DISTINCT FROM và IS NOT DISTINCT FROM

PostgreSQL hỗ trợ so sánh **có kết quả Boolean xác định ngay cả khi gặp NULL**:

```sql
SELECT
    NULL::integer IS DISTINCT FROM NULL::integer
        AS both_null_distinct,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS both_null_equal_for_comparison,
    5 IS DISTINCT FROM NULL::integer
        AS value_differs_from_null,
    5 IS NOT DISTINCT FROM 5
        AS equal_nonnull;
```

Kết quả:

| Biểu thức | Giá trị |
| --- | --- |
| Hai NULL `IS DISTINCT FROM` | FALSE |
| Hai NULL `IS NOT DISTINCT FROM` | TRUE |
| 5 `IS DISTINCT FROM` NULL | TRUE |
| 5 `IS NOT DISTINCT FROM` 5 | TRUE |

Đây là so sánh rất hữu ích khi so bản cũ/bản mới trong audit, phát hiện cột đã đổi hoặc JOIN trên giá trị nullable theo quy tắc đặc biệt.

### 7.2. IS TRUE / IS FALSE / IS UNKNOWN

Khi một cột có kiểu `BOOLEAN` nhưng nullable:

```sql
SELECT
    NULL::boolean IS TRUE AS is_true,
    NULL::boolean IS FALSE AS is_false,
    NULL::boolean IS UNKNOWN AS is_unknown,
    NULL::boolean IS NOT TRUE AS is_not_true;
```

Kết quả: `FALSE`, `FALSE`, `TRUE` và `TRUE`.

`IS NOT TRUE` khác `= FALSE`: nó bao gồm cả `NULL`.

### 7.3. NULL có thể làm CHECK khác với kỳ vọng

Trong PostgreSQL, `CHECK(expression)` chấp nhận một hàng nếu biểu thức trả **TRUE hoặc UNKNOWN**, và từ chối khi trả **FALSE**.

```sql
CREATE TABLE expression_demo_nullable (
    quantity INTEGER,
    CHECK (quantity > 0)
);
```

Hàng có `quantity = NULL` không bị CHECK bác bỏ. Muốn quantity bắt buộc dương:

```sql
CREATE TABLE expression_demo_required (
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
```

Sự kết hợp giữa `NOT NULL` và `CHECK` mới bảo vệ được cả tính **có mặt** và **miền giá trị**.

## 8. BETWEEN, IN, ANY, ALL và điều kiện tập hợp

### 8.1. BETWEEN bao gồm hai đầu mút

```sql
SELECT
    10 BETWEEN 1 AND 10 AS at_upper_boundary,
    11 BETWEEN 1 AND 10 AS beyond_upper_boundary;
```

Kết quả là `TRUE` và `FALSE`.

`BETWEEN a AND b` thường có ý nghĩa tương đương kiểm tra:

```sql
value >= a AND value <= b
```

Khi hai đầu mút bị đảo, `BETWEEN` bình thường sẽ không tự hoán đổi chúng. PostgreSQL có `BETWEEN SYMMETRIC` nếu thực sự cần khoảng không phụ thuộc thứ tự hai mốc.

Với timestamp, để lấy một ngày đầy đủ nên ưu tiên **khoảng nửa mở**:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND created_at < TIMESTAMPTZ '2026-01-02 00:00:00+07'
```

thay vì tạo mốc cuối ngày bằng `23:59:59`, có thể làm mất các giá trị có phần giây nhỏ.

### 8.2. IN để so với tập giá trị

```sql
SELECT
    'PAID' IN ('PAID', 'PENDING') AS accepted,
    'CANCELLED' IN ('PAID', 'PENDING') AS rejected;
```

Kết quả: `TRUE`, `FALSE`.

`IN` hữu ích khi có danh sách giá trị hữu hạn. Nhưng cần lưu ý `NULL`:

```sql
SELECT
    2 IN (1, NULL) AS check_with_null,
    2 NOT IN (1, NULL) AS negated_check_with_null;
```

Cả hai có thể trả **NULL/UNKNOWN**, không phải FALSE và TRUE như suy nghĩ ban đầu. Không có phần tử nào khớp chắc chắn, nhưng phần tử NULL khiến không thể kết luận chắc chắn giá trị 2 có bằng một phần tử chưa biết hay không.

### 8.3. NOT IN với NULL: bẫy khi lọc ngoại trừ

Ví dụ muốn tìm khách **không có đơn hàng**:

```sql
-- Nếu subquery trả NULL, NOT IN có thể loại cả các hàng
-- mà bạn mong muốn giữ.
-- WHERE customer_id NOT IN (SELECT customer_id FROM orders)
```

Một lựa chọn thường dễ kiểm soát hơn:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
```

Nếu dữ liệu nguồn được bảo vệ `NOT NULL` thì `NOT IN` có thể phù hợp về ngữ nghĩa, nhưng vẫn cần xem tình huống subquery rỗng, NULL ở phía trái và mục đích nghiệp vụ.

### 8.4. ANY và ALL với mảng

Trong PostgreSQL:

```sql
SELECT
    3 = ANY(ARRAY[1, 3, 5]) AS found_any,
    7 > ALL(ARRAY[1, 3, 5]) AS greater_than_all,
    3 <> ALL(ARRAY[1, 5]) AS differs_from_all;
```

Cả ba ví dụ trên trả `TRUE`.

- `= ANY(array)`: có ít nhất một phần tử bằng giá trị đang xét.
- `> ALL(array)`: lớn hơn tất cả phần tử.
- `<> ALL(array)`: khác tất cả phần tử theo logic ba giá trị.

Khi mảng rỗng, `= ANY('{}'::integer[])` trả FALSE, còn `= ALL('{}'::integer[])` trả TRUE theo ngữ nghĩa tập rỗng. Mảng chứa NULL cũng có thể làm kết quả UNKNOWN nếu không tìm được bằng chứng TRUE/FALSE quyết định.

### 8.5. Dấu ngoặc với BETWEEN và NOT

Vì `BETWEEN ... AND ...` có cấu trúc ngữ pháp riêng, cách an toàn khi phủ định một điều kiện phức tạp là viết:

```sql
WHERE NOT (amount BETWEEN 50000 AND 100000)
```

Đừng đoán bằng mắt `AND` nào thuộc `BETWEEN` và `AND` nào thuộc phần điều kiện khác.

## 9. Toán tử mẫu chuỗi và biểu thức chính quy

PostgreSQL hỗ trợ:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `text LIKE pattern` | So khớp mẫu kiểu SQL |
| `text ILIKE pattern` | So khớp mẫu không phân biệt hoa/thường theo quy tắc locale |
| `text NOT LIKE pattern` | Không khớp mẫu |
| `text SIMILAR TO pattern` | So khớp mẫu theo cú pháp SQL regular-expression-like |
| `text ~ pattern` | Khớp biểu thức chính quy POSIX, phân biệt hoa/thường |
| `text ~* pattern` | Regex không phân biệt hoa/thường |
| `text !~ pattern` | Không khớp regex phân biệt hoa/thường |
| `text !~* pattern` | Không khớp regex không phân biệt hoa/thường |

### 9.1. LIKE và ký tự đại diện

```sql
SELECT
    'PostgreSQL' LIKE 'Post%' AS starts_with_post,
    'PostgreSQL' LIKE '%SQL' AS ends_with_sql,
    'A1' LIKE 'A_' AS one_character_after_a,
    'PostgreSQL' ILIKE 'post%' AS case_insensitive_match;
```

Trong mẫu `LIKE`:

- `%` khớp chuỗi ký tự bất kỳ, kể cả rỗng.
- `_` khớp đúng một ký tự.

Một giá trị nhập từ người dùng có thể chứa ký tự `%` hoặc `_`. Nếu cần tìm **ký tự literal** thay vì wildcard, phải escape theo cú pháp `LIKE ... ESCAPE ...` và chính sách của ứng dụng.

### 9.2. Regex có quy tắc riêng

```sql
SELECT
    'AB-123' ~ '^[A-Z]{2}-[0-9]{3}$'
        AS valid_code,
    'postgres' ~* '^POST'
        AS regex_case_insensitive;
```

Các ký hiệu `^` và `$` trong **chuỗi pattern regex** khác với toán tử số học `^` của SQL. Chúng được xử lý **bên trong regex engine**, không theo bảng độ ưu tiên các toán tử SQL bên ngoài.

**Đặc biệt:** dấu `~` là toán tử regex khi được áp dụng cho chuỗi, nhưng có thể là toán tử NOT bitwise với kiểu số nguyên. Cần xét kiểu dữ liệu.

## 10. Nối chuỗi và xử lý NULL

PostgreSQL dùng `||` để nối chuỗi:

```sql
SELECT
    'Post' || 'greSQL' AS name,
    'Mã: ' || 101::text AS labeled_id;
```

Kết quả: `PostgreSQL` và `Mã: 101`.

### 10.1. NULL làm biểu thức nối chuỗi thành NULL

```sql
SELECT
    'A' || NULL::text AS nullable_concat,
    'A' || COALESCE(NULL::text, '') AS guarded_concat,
    concat('A', NULL::text, 'B') AS concat_function;
```

Kết quả:

| Cột | Giá trị |
| --- | --- |
| `nullable_concat` | NULL |
| `guarded_concat` | `A` |
| `concat_function` | `AB` |

`concat(...)` bỏ qua các đối số NULL theo ngữ nghĩa PostgreSQL. Nhưng không vì thuận tiện mà mặc định mọi NULL nên được biến thành chuỗi rỗng: trong một số báo cáo, thiếu dữ liệu cần được giữ để phát hiện lỗi nhập liệu.

### 10.2. Nối chuỗi và toán tử khác

`||` nằm trong nhóm **các toán tử khác**, khác mức với `+` và `*`. Khi kết hợp phép tính số với chuỗi, nên viết:

```sql
SELECT
    'Tổng: ' || ((100 + 20) * 2)::text
        AS readable_result;
```

Giá trị là `Tổng: 240`. Dấu ngoặc làm rõ phần phép tính cần chuyển thành text trước khi nối.

## 11. Bitwise: không nhầm toán tử ^ với XOR

PostgreSQL hỗ trợ phép toán trên bit/kiểu số nguyên thích hợp:

| Toán tử | Ý nghĩa với kiểu phù hợp |
| --- | --- |
| `&` | Bitwise AND |
| `|` | Bitwise OR |
| `#` | Bitwise XOR |
| `~` | Bitwise NOT |
| `<<` | Dịch bit sang trái |
| `>>` | Dịch bit sang phải |

Ví dụ:

```sql
SELECT
    6 & 3 AS bitwise_and,
    6 | 3 AS bitwise_or,
    6 # 3 AS bitwise_xor,
    1 << 3 AS shift_left;
```

Kết quả lần lượt: `2`, `7`, `5` và `8`.

**Trong PostgreSQL, `^` là toán tử lũy thừa**, không phải XOR bit như trong nhiều ngôn ngữ lập trình. Nếu người lập trình Java quen dùng `^` cho XOR, việc chuyển nguyên công thức sang PostgreSQL có thể tạo kết quả sai mà SQL vẫn chạy thành công.

## 12. Tạo schema thực hành kết hợp nhiều biểu thức

Để dùng các toán tử với dữ liệu thực tế, tạo một bảng đơn hàng mẫu. Các lệnh chỉ dành cho **database thử nghiệm** và giả định schema chưa có bảng cùng tên.

```sql
CREATE SCHEMA IF NOT EXISTS expression_lab;

CREATE TABLE expression_lab.orders (
    order_id       INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL,
    status         TEXT,
    amount         NUMERIC(12, 2),
    discount       NUMERIC(12, 2) NOT NULL DEFAULT 0,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    denominator    INTEGER,
    ordered_at     TIMESTAMPTZ NOT NULL,
    attributes     JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags           TEXT[],
    CONSTRAINT chk_orders_status
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    CONSTRAINT chk_orders_amount
        CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT chk_orders_discount
        CHECK (discount >= 0)
);
```

Trong ví dụ, `status` và `amount` **cố tình cho phép NULL** để thực hành logic ba giá trị. Một hệ thống giao dịch thật phải thống nhất ý nghĩa NULL trước khi chọn constraint. `discount` được giới hạn không âm nhưng chưa có ràng buộc `discount <= amount`, vì ta muốn minh họa sự khác nhau giữa quy tắc truy vấn và quy tắc toàn vẹn dữ liệu.

### 12.1. Nạp dữ liệu

```sql
INSERT INTO expression_lab.orders (
    order_id, customer_id, status, amount, discount,
    quantity, denominator, ordered_at, attributes, tags
)
VALUES
    (101, 1, 'PAID', 120000, 10000, 2,  2,
     TIMESTAMPTZ '2026-01-10 09:00:00+07',
     '{"source":"web","priority":2}'::jsonb,
     ARRAY['vip', 'express']::text[]),
    (102, 1, 'PENDING', 80000, 0, 1, 0,
     TIMESTAMPTZ '2026-01-11 10:00:00+07',
     '{"source":"app","priority":1}'::jsonb,
     ARRAY['standard']::text[]),
    (103, 2, 'PAID', 200000, 25000, 3, 4,
     TIMESTAMPTZ '2026-01-12 11:00:00+07',
     '{"source":"web","priority":3}'::jsonb,
     ARRAY['vip']::text[]),
    (104, 3, 'CANCELLED', 90000, 0, 2, 0,
     TIMESTAMPTZ '2026-01-13 12:00:00+07',
     '{"source":"partner"}'::jsonb,
     ARRAY[]::text[]),
    (105, 3, NULL, NULL, 0, 1, NULL,
     TIMESTAMPTZ '2026-01-14 13:00:00+07',
     '{"source":"app"}'::jsonb,
     NULL::text[]),
    (106, 4, 'PAID', 50000, 5000, 1, 5,
     TIMESTAMPTZ '2026-02-01 08:00:00+07',
     '{"source":"partner","priority":2}'::jsonb,
     ARRAY['first-time']::text[]);
```

Từ đây ta có sáu đơn với trạng thái:

| order_id | customer_id | status | amount | discount | denominator |
| ---: | ---: | --- | ---: | ---: | ---: |
| 101 | 1 | PAID | 120000 | 10000 | 2 |
| 102 | 1 | PENDING | 80000 | 0 | 0 |
| 103 | 2 | PAID | 200000 | 25000 | 4 |
| 104 | 3 | CANCELLED | 90000 | 0 | 0 |
| 105 | 3 | NULL | NULL | 0 | NULL |
| 106 | 4 | PAID | 50000 | 5000 | 5 |

Các bản ghi có `denominator = 0` và NULL được đưa vào **có chủ đích** để thử chia an toàn. Đừng đặt phép chia chưa bảo vệ trực tiếp lên toàn bộ bảng này.

## 13. Điều kiện AND/OR tác động tới dữ liệu như thế nào?

Yêu cầu A: **mọi đơn PAID hoặc đơn PENDING có amount từ 100.000**.

```sql
SELECT order_id, status, amount
FROM expression_lab.orders
WHERE status = 'PAID'
   OR (status = 'PENDING' AND amount >= 100000)
ORDER BY order_id;
```

Kết quả: đơn **101, 103, 106**. Đơn PENDING 102 có amount 80.000 nên không đạt; mọi đơn PAID được lấy dù amount 50.000 như đơn 106.

Yêu cầu B: **chỉ đơn PAID/PENDING và amount từ 100.000**.

```sql
SELECT order_id, status, amount
FROM expression_lab.orders
WHERE (status = 'PAID' OR status = 'PENDING')
  AND amount >= 100000
ORDER BY order_id;
```

Kết quả: đơn **101, 103**; đơn 106 bị loại vì amount chưa đạt ngưỡng.

### 13.1. Với NULL, phủ định không tự tạo nhóm bù

```sql
SELECT order_id, status
FROM expression_lab.orders
WHERE NOT (status = 'PAID')
ORDER BY order_id;
```

Kết quả: 102, 104. Đơn **105 có status NULL không xuất hiện**, vì `NOT UNKNOWN = UNKNOWN`.

Muốn lấy tất cả đơn **khác PAID, bao gồm NULL**:

```sql
SELECT order_id, status
FROM expression_lab.orders
WHERE status IS DISTINCT FROM 'PAID'
ORDER BY order_id;
```

Kết quả: 102, 104, 105.

Đây là quyết định nghiệp vụ: **“không phải PAID”** có bao gồm **“chưa biết trạng thái”** hay không? Hai cách viết SQL tương ứng với hai ý nghĩa khác nhau.

## 14. Tính tiền và kiểm tra biểu thức nhiều toán tử

Giả sử `amount` là tổng giá trị trước giảm giá, ta muốn tính:

```text
net_amount = amount - discount
```

```sql
SELECT
    order_id,
    amount,
    discount,
    amount - discount AS net_amount
FROM expression_lab.orders
ORDER BY order_id;
```

Theo dữ liệu mẫu, net_amount của các đơn lần lượt: 110.000; 80.000; 175.000; 90.000; NULL; 45.000.

### 14.1. Biểu thức có NULL trả NULL

`NULL - 0` vẫn là NULL, không phải 0. Vì thế đơn 105 có `net_amount IS NULL`.

Nếu muốn hiển thị 0 cho giá trị không rõ, có thể viết:

```sql
SELECT
    order_id,
    COALESCE(amount - discount, 0) AS displayed_net_amount
FROM expression_lab.orders;
```

Nhưng cách này **đổi ý nghĩa hiển thị** từ “chưa có số tiền” sang “0”. Chỉ làm khi yêu cầu báo cáo xác định rõ NULL nên được coi là 0; không nên tùy tiện che dữ liệu chưa được nhập.

### 14.2. Kiểm tra ràng buộc nhiều cột

Nếu nghiệp vụ cho phép discount không vượt amount và amount bắt buộc phải biết:

```sql
-- Ví dụ định nghĩa trên bảng mới, không tự sửa dữ liệu cũ:
CREATE TABLE expression_lab.order_amounts_strict (
    order_id INTEGER PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    discount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT chk_amount_bounds
        CHECK (
            amount >= 0
            AND discount >= 0
            AND discount <= amount
        )
);
```

Đây là **CHECK trên cùng một hàng**, phù hợp với quan hệ giữa amount và discount. Ngược lại, quy tắc “tổng amount của đơn bằng tổng giá trị dòng hàng ở bảng khác” không thể diễn đạt trực tiếp bằng một `CHECK` thông thường có truy vấn con.

## 15. CASE: chọn kết quả theo điều kiện

`CASE` giúp xây dựng một biểu thức trả về giá trị khác nhau theo điều kiện:

```sql
SELECT
    order_id,
    status,
    CASE
        WHEN status = 'PAID' THEN 'Đã thanh toán'
        WHEN status = 'PENDING' THEN 'Đang chờ'
        WHEN status = 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Chưa xác định'
    END AS status_label
FROM expression_lab.orders
ORDER BY order_id;
```

`CASE` dạng trên chọn nhánh **WHEN đầu tiên có điều kiện TRUE**. Nếu một điều kiện `WHEN` là FALSE hoặc UNKNOWN, PostgreSQL chuyển xét nhánh tiếp theo.

### 15.1. Thứ tự WHEN ảnh hưởng kết quả

```sql
SELECT
    amount,
    CASE
        WHEN amount >= 100000 THEN 'Cao'
        WHEN amount >= 50000 THEN 'Trung bình'
        ELSE 'Thấp hoặc không xác định'
    END AS amount_tier
FROM expression_lab.orders;
```

Nếu đặt kiểm tra `amount >= 50000` lên trước, những hàng amount 120.000 hoặc 200.000 sẽ được phân loại “Trung bình”, vì nhánh đó đã TRUE trước khi đến nhánh “Cao”.

Muốn phân loại khoảng, nên viết các điều kiện **không chồng lấn hoặc theo thứ tự rõ ràng**.

### 15.2. CASE có thể trả về NULL

Nếu không có nhánh `ELSE` và không có `WHEN` nào TRUE, kết quả là `NULL`:

```sql
SELECT
    CASE
        WHEN NULL::integer > 0 THEN 'Dương'
    END AS unknown_result;
```

Kết quả là NULL. Các giá trị `THEN`/`ELSE` còn phải có khả năng tìm được một kiểu kết quả chung phù hợp; nếu trộn kiểu dữ liệu không thể chuyển đổi, PostgreSQL có thể báo lỗi phân giải kiểu.

## 16. COALESCE, NULLIF và bảo vệ phép chia

### 16.1. COALESCE lấy giá trị đầu tiên khác NULL

```sql
SELECT
    COALESCE(NULL::text, 'fallback', 'other') AS selected_text,
    COALESCE(NULL::numeric, 0) AS zero_if_unknown;
```

Kết quả là `fallback` và `0`.

`COALESCE` hữu ích khi có giá trị dự phòng. Không cần bọc tất cả cột bằng `COALESCE`; hãy chọn giá trị mặc định dựa trên ngữ nghĩa nghiệp vụ.

### 16.2. NULLIF tạo NULL khi hai giá trị bằng nhau

```sql
SELECT
    NULLIF(0, 0) AS zero_to_null,
    NULLIF(5, 0) AS five_unchanged;
```

Kết quả là NULL và 5.

### 16.3. Chia an toàn với NULLIF

Vì dữ liệu `denominator` có thể bằng 0:

```sql
SELECT
    order_id,
    amount,
    denominator,
    amount / NULLIF(denominator, 0) AS safe_ratio
FROM expression_lab.orders
ORDER BY order_id;
```

Với denominator = 0, `NULLIF(denominator, 0)` trở thành NULL, nên phép chia trả NULL thay vì phát sinh lỗi chia cho 0. Với denominator NULL, kết quả cũng NULL.

Nếu nghiệp vụ cần giá trị dự phòng khi không thể chia:

```sql
SELECT
    order_id,
    COALESCE(
        amount / NULLIF(denominator, 0),
        0
    ) AS reported_ratio
FROM expression_lab.orders
ORDER BY order_id;
```

Nhưng 0 ở đây có nghĩa **quy ước hiển thị**; không đồng nghĩa tỷ lệ toán học thực sự bằng 0. Đối với KPI, đôi khi nên để NULL hoặc kèm trạng thái “không tính được”.

### 16.4. CASE bảo vệ phép chia có điều kiện

Một cách biểu đạt khác:

```sql
SELECT
    order_id,
    CASE
        WHEN denominator IS NULL OR denominator = 0 THEN NULL
        ELSE amount / denominator
    END AS safe_ratio
FROM expression_lab.orders;
```

Với các giá trị cột động ở runtime như trong ví dụ, `CASE` có thể dùng để kiểm soát việc chỉ đánh giá nhánh tương ứng.

**Tuy nhiên**, không nên suy luận rằng `CASE` là một cơ chế bảo đảm mọi biểu thức trong nhánh không được chọn sẽ **không bao giờ** bị xử lý ở bất kỳ giai đoạn nào. PostgreSQL có thể đánh giá sớm biểu thức hằng trong lúc lập kế hoạch; aggregate và một số cấu trúc khác cũng có quy tắc đánh giá riêng. Phần 18 sẽ làm rõ giới hạn quan trọng này.

## 17. Toán tử PostgreSQL cho JSONB và mảng

PostgreSQL có nhiều toán tử dành riêng cho kiểu dữ liệu phức hợp. Đây là nơi **độ ưu tiên ép kiểu** và **kiểu kết quả của từng toán tử** đặc biệt đáng chú ý.

### 17.1. JSONB -> và ->>

Với cột `attributes JSONB`:

```sql
SELECT
    order_id,
    attributes -> 'source' AS source_json,
    attributes ->> 'source' AS source_text
FROM expression_lab.orders
ORDER BY order_id;
```

Khác biệt:

- `->` trả giá trị dạng **JSON/JSONB** tương ứng.
- `->>` trả giá trị dạng **TEXT**.

Ví dụ `attributes ->> 'priority'` trả chuỗi text như `'2'`, không tự trở thành kiểu số nguyên chỉ vì JSON ban đầu có số 2.

### 17.2. Đặt ngoặc trước khi ép kiểu JSON text

Câu đúng:

```sql
SELECT
    order_id,
    (attributes ->> 'priority')::integer AS priority_number
FROM expression_lab.orders
WHERE attributes ? 'priority'
ORDER BY order_id;
```

Các hàng có trường `priority` trong dữ liệu ví dụ có giá trị số hợp lệ. Chúng được lấy text rồi **mới chuyển sang integer**.

Không viết theo thói quen:

```sql
-- SAI Ý ĐỊNH:
-- attributes ->> 'priority'::integer
```

Vì `::` có độ ưu tiên cao hơn toán tử JSON `->>`, biểu thức trên có thể cố ép **chuỗi key 'priority' thành integer**, gây lỗi trước khi lấy giá trị từ JSON.

**Quy tắc thực hành:** với toán tử JSON kết hợp cast, dùng:

```sql
(json_expression ->> 'key')::target_type
```

hoặc:

```sql
CAST(json_expression ->> 'key' AS target_type)
```

### 17.3. JSONB containment @>

```sql
SELECT
    order_id,
    attributes
FROM expression_lab.orders
WHERE attributes @> '{"source":"web"}'::jsonb
ORDER BY order_id;
```

Kết quả: các đơn 101 và 103.

`@>` khi áp dụng cho JSONB kiểm tra phần JSON bên trái có chứa cấu trúc/giá trị yêu cầu ở bên phải theo quy tắc containment. Đây là ngữ nghĩa **khác** với toán tử so sánh text `=` hoặc `LIKE`.

### 17.4. Truy cập mảng và toán tử mảng

```sql
SELECT
    order_id,
    tags,
    tags[1] AS first_tag,
    tags @> ARRAY['vip']::text[] AS has_vip
FROM expression_lab.orders
ORDER BY order_id;
```

Với mảng PostgreSQL bình thường trong ví dụ, `tags[1]` truy cập phần tử đầu tiên; chỉ số mảng có thể được định nghĩa có lower bound khác 1 trong những trường hợp nâng cao, nên không coi “mọi mảng PostgreSQL luôn bắt đầu từ 1” là bất biến hệ thống.

`tags @> ARRAY['vip']::text[]` kiểm tra mảng bên trái **chứa** phần tử theo quy tắc toán tử mảng. Nếu `tags IS NULL`, kết quả của toán tử thường là NULL/UNKNOWN.

### 17.5. Nhiều kiểu có cùng ký hiệu toán tử

`@>` còn có thể dùng với range hoặc kiểu khác có định nghĩa hỗ trợ. Cùng cú pháp nhưng không phải cùng một phép kiểm tra về dữ liệu.

Khi đọc câu SQL có toán tử “lạ”, xem:

1. Kiểu thực của toán hạng trái và phải.
2. Operator đã được PostgreSQL chọn.
3. Kiểu kết quả.
4. Index/operator class tương ứng nếu cần tối ưu.

Không ép tất cả về TEXT chỉ để dùng toán tử quen thuộc; làm vậy có thể đánh mất ngữ nghĩa kiểu dữ liệu và lợi thế của chỉ mục phù hợp.

## 18. Độ ưu tiên không phải thứ tự đánh giá runtime

Đây là phân biệt quan trọng nhất của bài:

**Độ ưu tiên** quyết định cách biểu thức được **phân tích thành cây cú pháp**:

```text
amount + tax * rate
      |
      +--> amount + (tax * rate)
```

Nhưng **thứ tự đánh giá lúc thực thi** có thể phụ thuộc vào planner, phương án quét, việc đẩy điều kiện xuống dưới và tối ưu các biểu thức. Không nên nhìn biểu thức `a AND b` và khẳng định PostgreSQL luôn tính `a` trước rồi, nếu cần, mới tính `b`.

### 18.1. Không dựa vào short-circuit trong WHERE

Ví dụ dễ gây nguy hiểm:

```sql
-- CÁCH VIẾT KHÔNG NÊN DỰA VÀO ĐỂ CHỐNG CHIA CHO 0:
-- WHERE denominator <> 0
--   AND amount / denominator > 1000
```

Người mới học có thể nghĩ: “PostgreSQL kiểm tra denominator khác 0 trước, nếu sai thì bỏ qua phép chia”. Nhưng **biểu thức Boolean trong WHERE/HAVING có thể được sắp xếp, biến đổi và đánh giá theo kế hoạch thực thi**, nên không nên xem `AND` là một câu lệnh điều khiển luồng có thứ tự trái–phải bắt buộc.

Giải pháp diễn đạt phép tính an toàn:

```sql
SELECT
    order_id,
    amount / NULLIF(denominator, 0) AS safe_ratio
FROM expression_lab.orders
WHERE amount / NULLIF(denominator, 0) > 1000;
```

Khi denominator bằng 0, biểu thức chia an toàn trả NULL; điều kiện so sánh với 1000 trở thành UNKNOWN và hàng không được chọn.

### 18.2. Planner có thể tính trước biểu thức hằng

Ví dụ minh họa lỗi có thể phát sinh ở thời điểm lập kế hoạch:

```sql
-- KHÔNG CHẠY: biểu thức hằng 1/0 có thể bị đánh giá
-- trước khi CASE được xét như một nhánh runtime.
-- SELECT CASE WHEN false THEN 1 / 0 ELSE 0 END;
```

Ý nghĩa: `CASE` có khả năng điều khiển các nhánh khi đánh giá bình thường, nhưng **không phải ranh giới chống mọi tối ưu hóa hoặc constant folding**. Nên tránh đặt phép tính không hợp lệ thành hằng trong SQL ngay cả ở nhánh có vẻ không được chọn.

### 18.3. Aggregate có thể được tính trước CASE bao quanh

Một ý tưởng sai khi dữ liệu có denominator bằng 0:

```sql
-- CÁCH VIẾT KHÔNG AN TOÀN:
-- SELECT CASE
--     WHEN MIN(denominator) > 0
--     THEN SUM(amount / denominator)
--     ELSE NULL
-- END
-- FROM expression_lab.orders;
```

Trong truy vấn tổng hợp, những biểu thức aggregate có thể được tính **trước** khi kết quả `CASE` bao ngoài được dùng để chọn nhánh. Vì vậy, `CASE` ngoài cùng không đảm bảo bảo vệ `SUM(amount / denominator)` khỏi dữ liệu có denominator 0.

Một cách an toàn về lỗi chia:

```sql
SELECT
    SUM(amount / NULLIF(denominator, 0))
        AS sum_of_defined_ratios
FROM expression_lab.orders;
```

Tuy nhiên, phải hiểu ý nghĩa: `SUM` bỏ qua các giá trị NULL, nên câu trên **bỏ qua các hàng không tính được tỷ lệ**. Nếu mục tiêu là `SUM(amount) / SUM(denominator)`, đó là **một công thức khác**, và cũng cần bảo vệ mẫu số tổng:

```sql
SELECT
    SUM(amount) / NULLIF(SUM(denominator), 0)
        AS ratio_of_totals
FROM expression_lab.orders;
```

Không thay hai công thức cho nhau nếu không có định nghĩa nghiệp vụ.

### 18.4. Không dùng thứ tự đánh giá để tạo side effects

Các hàm có tính biến động (*VOLATILE*) như `random()` hoặc hàm tùy biến có side effect có thể được gọi theo cách phụ thuộc kế hoạch; không nên viết điều kiện Boolean để kỳ vọng side effect luôn xảy ra đúng một lần hoặc theo thứ tự cụ thể.

Một câu SQL là **mô tả kết quả cần tính**, không phải mã thủ tục với cam kết từng biểu thức được thực thi theo thứ tự hiển thị. Nếu thao tác có tác dụng phụ đòi thứ tự, cần thiết kế transaction/procedure hoặc logic ứng dụng có trình tự rõ ràng.

## 19. Phân tích cú pháp, ép kiểu và phân giải toán tử

Ngay cả khi thứ tự ngoặc đã đúng, PostgreSQL vẫn cần xác định **kiểu của mỗi toán hạng** và **định nghĩa toán tử nào được áp dụng**.

### 19.1. Literal số và literal chuỗi không có cùng ngữ nghĩa

```sql
SELECT
    10 + 2 AS numeric_addition,
    '10'::text || '2'::text AS text_concatenation;
```

Kết quả là **12** và **'102'**. Không nên đưa số vào TEXT rồi dùng `||` để thực hiện phép cộng nghiệp vụ.

PostgreSQL có thể ép kiểu **literal chưa xác định kiểu** trong một số biểu thức theo ngữ cảnh operator, nhưng sự suy luận đó không nên được xem là hợp đồng cho mọi chuỗi đầu vào, tham số prepared statement hay cast từ một cột TEXT.

### 19.2. CAST tường minh tránh phụ thuộc suy luận

```sql
SELECT
    CAST('120' AS integer) + 5 AS parsed_numeric,
    ('120'::integer + 5)::text AS result_as_text;
```

Kết quả là `125` và `'125'`.

Nếu chuỗi không phải biểu diễn số nguyên hợp lệ, ví dụ `'abc'::integer`, PostgreSQL báo lỗi. Ép kiểu **không tự thay dữ liệu bẩn bằng 0**.

### 19.3. Ép kiểu và độ ưu tiên

Vì `::` thuộc nhóm ưu tiên cao, biểu thức:

```sql
SELECT (7 / 2)::numeric AS cast_after_division;
```

cho kết quả **3** ở dạng numeric, **không trở lại 3.5**. Phần thập phân đã bị bỏ khi chia hai integer.

Muốn kết quả 3.5:

```sql
SELECT
    7::numeric / 2 AS cast_before_division,
    CAST(7 AS numeric) / 2 AS equivalent_cast;
```

**Ép kiểu sau phép tính không sửa được thông tin đã mất trong phép tính trước đó.**

### 19.4. PostgreSQL hỗ trợ toán tử do người dùng định nghĩa

Với extension hoặc schema riêng, người phát triển có thể có toán tử mới. Cú pháp `OPERATOR(schema.operator_name)` cho phép chỉ rõ toán tử thuộc schema nào trong trường hợp phù hợp, nhưng các toán tử được viết theo cú pháp chỉ định này có quy tắc ưu tiên của **nhóm toán tử chung**, không nhất thiết giữ mức ưu tiên của ký hiệu viết trực tiếp như `+`.

Vì vậy, khi dùng toán tử tùy biến, hãy đặt ngoặc quanh từng phần để tránh phụ thuộc vào cách parser phân giải các ký hiệu không quen thuộc.

## 20. Ngày giờ và AT TIME ZONE

PostgreSQL hỗ trợ biểu thức thao tác thời gian:

```sql
SELECT
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_wall_time;
```

Kết quả về ngữ nghĩa là **2026-01-01 07:00:00** dưới dạng timestamp không kèm múi giờ cho thời điểm đã chuyển về múi giờ Asia/Ho_Chi_Minh.

Quy tắc quan trọng:

- `timestamptz AT TIME ZONE zone` thường cho **timestamp without time zone**, biểu diễn giờ địa phương của thời điểm đó trong zone.
- `timestamp without time zone AT TIME ZONE zone` thường cho **timestamptz**, diễn giải giờ địa phương đã cho là thuộc zone đó.

Hai chiều này **không giống nhau**. Một giá trị giờ địa phương thiếu múi giờ và một thời điểm tuyệt đối là hai loại thông tin khác nhau.

### 20.1. Dùng dấu ngoặc khi kết hợp thời gian và logic

```sql
SELECT
    order_id,
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS business_date
FROM expression_lab.orders
ORDER BY order_id;
```

Dấu ngoặc thể hiện rõ **chuyển sang giờ địa phương trước, sau đó mới lấy ngày**. Nếu lấy ngày trước khi đổi múi giờ hoặc phụ thuộc vào thiết lập `TimeZone` của session, báo cáo theo ngày có thể bị lệch quanh nửa đêm.

### 20.2. Khoảng nửa mở cho ngày tháng

Khi lọc trực tiếp một cột `TIMESTAMPTZ`, thường dùng khoảng nửa mở:

```sql
SELECT order_id, ordered_at
FROM expression_lab.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at < TIMESTAMPTZ '2026-02-01 00:00:00+07'
ORDER BY ordered_at;
```

Khoảng này biểu diễn một tháng lịch theo offset được viết rõ trong literal. Với múi giờ có daylight saving time, thời điểm đầu và cuối tháng nên được tính theo **múi giờ nghiệp vụ**, không giả định mọi ngày luôn 24 giờ.

## 21. JOIN, WHERE, HAVING và thời điểm đánh giá biểu thức

Thứ tự logic của các thành phần truy vấn thường được giải thích như:

```text
FROM / JOIN
    -> WHERE: lọc từng hàng
    -> GROUP BY: tạo nhóm
    -> aggregate: COUNT, SUM, AVG, ...
    -> HAVING: lọc nhóm
    -> SELECT: tạo biểu thức đầu ra
    -> ORDER BY: sắp xếp
    -> LIMIT: giới hạn số hàng kết quả
```

Đây là **ngữ nghĩa truy vấn**. PostgreSQL không nhất thiết đọc tuần tự hoặc đánh giá mọi biểu thức theo các bước vật lý y hệt sơ đồ.

### 21.1. WHERE không dùng aggregate của cùng tầng truy vấn

```sql
-- SAI:
-- SELECT customer_id, COUNT(*)
-- FROM expression_lab.orders
-- WHERE COUNT(*) >= 2
-- GROUP BY customer_id;
```

Muốn lọc nhóm:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM expression_lab.orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
```

Kết quả trong dữ liệu mẫu gồm khách 1 và 3, mỗi người hai đơn.

### 21.2. FILTER chỉ lọc đầu vào một aggregate

```sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM expression_lab.orders
GROUP BY customer_id
ORDER BY customer_id;
```

`COUNT(*)` đếm toàn bộ hàng trong nhóm; `COUNT(*) FILTER (WHERE status='PAID')` chỉ đếm đơn PAID, không loại các hàng đó khỏi `COUNT(*)`.

### 21.3. SELECT alias và WHERE

```sql
-- SAI trong cùng tầng SELECT: WHERE không dùng alias vừa định nghĩa.
-- SELECT amount - discount AS net_amount
-- FROM expression_lab.orders
-- WHERE net_amount >= 100000;
```

Viết:

```sql
SELECT
    order_id,
    amount - discount AS net_amount
FROM expression_lab.orders
WHERE amount - discount >= 100000
ORDER BY order_id;
```

hoặc dùng CTE:

```sql
WITH net_orders AS (
    SELECT
        order_id,
        amount - discount AS net_amount
    FROM expression_lab.orders
)
SELECT order_id, net_amount
FROM net_orders
WHERE net_amount >= 100000;
```

Trong query ngoài, `net_amount` là cột của CTE, nên dùng trong `WHERE` hợp lệ.

### 21.4. JOIN ON và WHERE với LEFT JOIN

Ví dụ muốn lấy **mọi khách** kể cả chưa có đơn, nhưng chỉ gắn những đơn đã thanh toán:

```sql
-- Mảnh SQL minh họa, giả định bảng customers tồn tại.
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
```

Chuyển `o.status='PAID'` từ `ON` xuống `WHERE` có thể loại mất khách chưa có đơn PAID, vì ở hàng không khớp `o.status IS NULL` và điều kiện so sánh cho UNKNOWN.

Với **INNER JOIN** đơn giản, nhiều điều kiện có thể chuyển giữa `ON` và `WHERE` mà không đổi kết quả; với **OUTER JOIN**, đó không phải quy tắc chung. Tìm đúng **ngữ nghĩa** trước khi xét việc tối ưu hóa biểu thức.

## 22. Hiệu năng: biểu thức có thể ảnh hưởng đến chỉ mục

Giả sử cột `amount` có một B-tree index thông thường:

```sql
CREATE INDEX idx_expression_lab_amount
ON expression_lab.orders (amount);
```

Điều kiện:

```sql
WHERE amount >= 100000
```

thường dễ tận dụng index trên chính cột amount hơn một biểu thức không khớp cấu trúc index, ví dụ:

```sql
WHERE amount - discount >= 100000
```

Tuy nhiên, điều kiện thứ hai là **ngữ nghĩa khác**: nó so số tiền **sau giảm giá**, không thể thay bằng so amount gốc chỉ để dùng index nhanh hơn.

### 22.1. Expression index khi workload cần

PostgreSQL hỗ trợ index trên biểu thức:

```sql
CREATE INDEX idx_expression_lab_net_amount
ON expression_lab.orders ((amount - discount));
```

Index này có thể giúp truy vấn lọc/sắp xếp theo biểu thức `amount - discount` tương ứng trong workload phù hợp. Nó cũng tiêu tốn dung lượng và chi phí ghi, nên không tạo chỉ vì có một bài tập SQL.

### 22.2. Ép kiểu trên cột và khả năng dùng index

Ví dụ:

```sql
WHERE ordered_at::date = DATE '2026-01-10'
```

không đồng nhất với điều kiện trực tiếp theo khoảng `ordered_at` trên index B-tree thông thường; còn việc cast `TIMESTAMPTZ` sang DATE có thể phụ thuộc vào múi giờ session.

Một truy vấn giới hạn theo thời điểm rõ ràng:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+07'
  AND ordered_at < TIMESTAMPTZ '2026-01-11 00:00:00+07'
```

thường thuận lợi hơn cho index trên cột ordered_at, đồng thời rõ ràng về phạm vi giờ. Dù vậy, PostgreSQL planner vẫn có thể chọn Seq Scan nếu bảng nhỏ hoặc chi phí index cao.

### 22.3. Dùng EXPLAIN để quan sát

```sql
EXPLAIN
SELECT
    order_id,
    amount - discount AS net_amount
FROM expression_lab.orders
WHERE amount - discount >= 100000;
```

Khi muốn đo thực tế trên database thử nghiệm:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    amount - discount AS net_amount
FROM expression_lab.orders
WHERE amount - discount >= 100000;
```

`EXPLAIN ANALYZE` **thực thi truy vấn**, vì vậy cần thận trọng với câu ghi dữ liệu hoặc truy vấn quá nặng trên production. Với dữ liệu mẫu rất nhỏ, `Seq Scan` hoàn toàn có thể hợp lý dù đã tạo index.

## 23. Cách kiểm tra kiểu và kết quả của biểu thức

Khi không chắc PostgreSQL đang xử lý biểu thức theo kiểu nào, có thể dùng `pg_typeof(...)`:

```sql
SELECT
    pg_typeof(7 / 2) AS integer_result_type,
    pg_typeof(7::numeric / 2) AS decimal_result_type,
    pg_typeof('x'::text || 'y'::text) AS concat_result_type;
```

Kết quả tương ứng là kiểu số nguyên, `numeric` và `text`.

### 23.1. Kiểm tra từng phần của biểu thức

Với một điều kiện phức tạp:

```sql
WHERE status = 'PAID'
  AND (amount - discount) >= 100000
  AND (attributes ->> 'source') = 'web'
```

hãy thử các cột phụ trợ:

```sql
SELECT
    order_id,
    status = 'PAID' AS is_paid,
    amount - discount AS net_amount,
    (amount - discount) >= 100000 AS reaches_target,
    attributes ->> 'source' AS source_text,
    (attributes ->> 'source') = 'web' AS is_web
FROM expression_lab.orders
ORDER BY order_id;
```

Điều này giúp phân biệt một hàng bị loại vì **FALSE** hay vì **UNKNOWN do NULL**.

### 23.2. Đừng xem EXPLAIN là bộ xác nhận logic nghiệp vụ

`EXPLAIN` cho biết cách PostgreSQL dự kiến/thực sự thực thi truy vấn, không chứng minh câu WHERE đã thể hiện đúng yêu cầu. Một điều kiện thiếu ngoặc có thể chạy cực nhanh **nhưng trả sai hàng**.

Cách kiểm tra quan trọng nhất là có **dữ liệu biên**: TRUE/FALSE, NULL, số 0, giá trị đúng bằng ngưỡng, ngày sát ranh giới, văn bản khác hoa/thường, JSON thiếu field và số lượng lớn.

## 24. Dùng PreparedStatement với biểu thức trong Java

Khi SQL được ứng dụng Java gửi vào PostgreSQL, biểu thức phải có cấu trúc cố định và **giá trị đầu vào nên được truyền bằng tham số**, không nối chuỗi để tạo SQL tùy ý.

Ví dụ:

```java
String sql = """
    SELECT order_id, amount - discount AS net_amount
    FROM expression_lab.orders
    WHERE (status = ? OR status = ?)
      AND amount - discount >= ?
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PAID");
    ps.setString(2, "PENDING");
    ps.setBigDecimal(3, new java.math.BigDecimal("100000.00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            int orderId = rs.getInt("order_id");
            java.math.BigDecimal net =
                rs.getBigDecimal("net_amount");
            // Xử lý dữ liệu theo hợp đồng ứng dụng.
        }
    }
}
```

Đoạn code giả định đã có `java.sql.Connection` và imports JDBC tương ứng; đây là ví dụ về cách truyền giá trị, không phải ứng dụng Java hoàn chỉnh.

**Dấu ngoặc trong SQL vẫn quan trọng**, dù dùng PreparedStatement. Parameter binding giúp phân tách giá trị với cấu trúc câu SQL và giảm nguy cơ SQL injection; nó không tự chỉnh sửa quy tắc ưu tiên toán tử.

Các toán tử, tên cột và cấu trúc SQL không thể được thay thế tùy ý bằng một tham số giá trị; nếu cho người dùng chọn điều kiện động, ứng dụng cần whitelist cột/toán tử và xây dựng query an toàn.

## 25. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Quên `*`/`/` ưu tiên hơn `+`/`-` | Công thức sai | Thêm ngoặc theo công thức nghiệp vụ |
| Giả định `AND` và `OR` có cùng ưu tiên | Điều kiện WHERE chọn nhầm hàng | Biết `AND` ưu tiên hơn `OR`, đặt ngoặc rõ |
| Viết `NOT status='PAID'` rồi nghĩ NULL được giữ | Loại các hàng status NULL | Dùng `IS DISTINCT FROM` khi muốn bao gồm NULL |
| Viết `column = NULL` | So sánh trả UNKNOWN | Dùng `IS NULL` |
| Coi UNKNOWN là FALSE trong mọi ngữ cảnh | Hiểu sai logic NOT/AND/OR | Dùng logic ba giá trị |
| Dùng `CHECK (value > 0)` nhưng cho phép value NULL | Hàng NULL được chấp nhận | Thêm `NOT NULL` nếu cần |
| Dùng `NOT IN` với tập có NULL | Có thể không trả hàng mong đợi | Kiểm soát NULL hoặc dùng `NOT EXISTS` |
| Tin `7 / 2` trả 3.5 | Mất phần thập phân | Ép kiểu trước phép chia |
| Dùng `(7 / 2)::numeric` để “khôi phục” phần lẻ | Vẫn được 3 | `7::numeric / 2` |
| Chuyển `^` từ Java và nghĩ là XOR | Tính lũy thừa thay vì bitwise XOR | Dùng `#` cho bitwise XOR phù hợp |
| Dùng `SUM(DISTINCT amount)` để sửa join nhân dòng | Cộng thiếu các giao dịch bằng tiền | Sửa grain/JOIN rồi tổng hợp |
| Viết `payload ->> 'quantity'::integer` | Cast nhầm JSON key | `(payload ->> 'quantity')::integer` |
| So sánh giá trị JSON text với số như thể cùng kiểu | Lỗi operator/type hoặc sai logic | Chuyển kiểu rõ, xác thực dữ liệu |
| Nối chuỗi bằng `||` và không xét NULL | Toàn biểu thức thành NULL | Dùng COALESCE/concat có chủ đích |
| Tin `AND` luôn kiểm tra trái trước | Phép chia 0 hoặc hàm lỗi vẫn có thể xảy ra | Dùng `NULLIF`/CASE phù hợp |
| Coi CASE là lá chắn tuyệt đối với mọi biểu thức | Constant folding/aggregate vẫn có thể gây lỗi | Tránh biểu thức không hợp lệ; bảo vệ phép tính tại nguồn |
| Dùng `CASE WHEN SUM(...)` để “chặn” aggregate lỗi | Aggregate được tính trước CASE ngoài | Bảo vệ phần tử ngay trong aggregate |
| Dùng WHERE với aggregate của cùng tầng | Lỗi SQL | Dùng HAVING |
| Dùng bí danh SELECT trong WHERE cùng tầng | Lỗi phân giải tên | Lặp biểu thức hoặc dùng CTE |
| Chuyển filter của LEFT JOIN từ ON sang WHERE | Mất hàng trái không khớp | Giữ đúng ngữ nghĩa outer join |
| Dùng `BETWEEN` với mốc cuối ngày 23:59:59 | Mất timestamp có phần giây | Dùng khoảng nửa mở |
| Không xác định múi giờ khi lấy DATE từ TIMESTAMPTZ | Sai ngày/tháng báo cáo | Chuyển theo múi giờ nghiệp vụ |
| Cho rằng Seq Scan luôn là vấn đề | Tối ưu hóa vô ích trên bảng nhỏ | Đọc EXPLAIN/chi phí thực tế |
| Giả định operator cùng ký hiệu luôn cùng nghĩa | Sai với JSONB/mảng/bitwise | Kiểm tra kiểu và operator được phân giải |

## 26. Bài tập thực hành

Các bài dưới đây dùng PostgreSQL và dữ liệu `expression_lab.orders` ở mục 12. Mỗi bài nên ghi rõ dự đoán trước khi chạy.

1. **Ưu tiên số học:** giải thích kết quả của `100 + 20 * 3` và `(100 + 20) * 3`. Vì sao hai biểu thức khác nhau?
2. **Tính kết hợp:** chạy `20 - 5 - 3` và `20 - (5 - 3)`. Chỉ ra toán tử nào được nhóm trước.
3. **Lũy thừa:** thử `2 ^ 3 ^ 2` và `2 ^ (3 ^ 2)`. So sánh với quy tắc lũy thừa bạn biết từ toán học hoặc ngôn ngữ lập trình khác.
4. **Dấu âm:** tính `-(3 ^ 2)` và `(-3) ^ 2`. Giải thích tại sao nên dùng ngoặc.
5. **Chia số nguyên:** tính `7 / 2`, `(7 / 2)::numeric` và `7::numeric / 2`. Vì sao cast sau phép chia không khôi phục phần lẻ?
6. **Ngưỡng:** viết biểu thức chọn đơn có `amount - discount >= 100000`. Với dữ liệu mẫu, những order_id nào đạt ngưỡng?
7. **AND/OR:** tìm những đơn PAID hoặc PENDING có amount >= 100000. Viết hai câu SQL với cách đặt ngoặc khác nhau và dự đoán kết quả.
8. **Logic NULL:** thử `NOT (NULL::boolean)`, `FALSE AND NULL::boolean` và `TRUE OR NULL::boolean`. Giải thích từng kết quả.
9. **So sánh NULL:** tìm các đơn có status khác PAID, **bao gồm** status NULL. So sánh `<>` và `IS DISTINCT FROM`.
10. **IS TRUE/FALSE:** với CTE có `TRUE`, `FALSE` và `NULL::boolean`, thử `IS FALSE`, `IS NOT TRUE` và `IS UNKNOWN`.
11. **BETWEEN:** so kết quả của `BETWEEN 50000 AND 100000` và `>=50000 AND <100000` cho đúng giá trị 100000.
12. **NOT IN và NULL:** giải thích `2 NOT IN (1, NULL)`. Viết cách kiểm tra không tồn tại bằng `NOT EXISTS` phù hợp.
13. **ANY/ALL:** thử `3 = ANY(ARRAY[1,3,5])`, `3 = ANY('{}'::integer[])` và `3 = ALL('{}'::integer[])`.
14. **Mẫu chuỗi:** viết query `LIKE` chọn những status bắt đầu bằng `'P'`. So sánh `LIKE` với `ILIKE` khi đổi chữ hoa/thường.
15. **Regex:** dùng `~` kiểm tra mã `AB-123` theo pattern hai chữ cái in hoa, dấu gạch nối và ba chữ số.
16. **Nối chuỗi:** thử `'A' || NULL::text`, `'A' || COALESCE(NULL::text,'')` và `concat('A',NULL,'B')`.
17. **Bitwise:** tính `6 & 3`, `6 | 3` và `6 # 3`. Giải thích vì sao `6 ^ 3` không phải XOR trong PostgreSQL.
18. **JSONB:** lấy `attributes ->> 'source'` và lọc các đơn source = web. Kết quả gồm những order_id nào?
19. **JSONB cast:** lấy priority thành integer bằng `(attributes ->> 'priority')::integer`. Vì sao `attributes ->> 'priority'::integer` sai?
20. **JSON containment:** thử `attributes @> '{"source":"web"}'::jsonb`. So kết quả với điều kiện text `attributes ->> 'source' = 'web'`.
21. **Mảng:** dùng `tags @> ARRAY['vip']::text[]` tìm đơn có nhãn VIP. Hàng tags NULL khác gì hàng tags rỗng?
22. **Phép chia an toàn:** tính `amount / NULLIF(denominator, 0)` cho mọi đơn. Vì sao các đơn 102/104/105 không gây lỗi?
23. **CASE:** phân loại các đơn theo net_amount: từ 100000 là Cao, từ 50000 là Trung bình, dưới 50000 là Thấp và NULL là Chưa biết. Viết CASE có thứ tự điều kiện rõ ràng.
24. **SUM và NULL:** so `SUM(amount / NULLIF(denominator,0))` với `SUM(amount) / NULLIF(SUM(denominator),0)`. Hai công thức có cùng ý nghĩa không?
25. **CASE và aggregate:** giải thích vì sao CASE bao ngoài một biểu thức `SUM(amount/denominator)` không luôn chống lỗi chia cho 0. Viết phiên bản an toàn.
26. **HAVING:** đếm số đơn mỗi customer, chỉ giữ khách có hai đơn trở lên. Vì sao không thể dùng `WHERE COUNT(*) >= 2`?
27. **FILTER:** cùng một query, trả số đơn mọi trạng thái và số đơn PAID theo customer. Sự khác nhau với lọc status ở WHERE là gì?
28. **Alias:** thử dùng `net_amount` vừa tạo trong SELECT ở WHERE cùng tầng, sau đó sửa bằng CTE.
29. **Giờ địa phương:** biến `ordered_at TIMESTAMPTZ` thành ngày ở `Asia/Ho_Chi_Minh`. Vì sao nên chuyển giờ trước khi cast thành DATE?
30. **Index biểu thức:** thử `EXPLAIN` trên điều kiện `amount - discount >= 100000` trước/sau khi tạo expression index. Vì sao PostgreSQL vẫn có thể chọn Seq Scan trên bảng nhỏ?
31. **Query Java:** viết một PreparedStatement với điều kiện nhóm `(status=? OR status=?) AND amount>=?`. Trình bày lý do bind tham số không thay thế nhu cầu viết ngoặc đúng.
32. **Kiểm tra SQL mới:** với một truy vấn có JSONB, OR/AND, cast, nullable amount và date range, lập bảng kiểm tra: cây biểu thức, kiểu kết quả, NULL, thứ tự đánh giá an toàn và dữ liệu biên.

## 27. Tổng kết

Khi viết một biểu thức PostgreSQL, hãy xem ba tầng khác nhau:

```text
1. CÚ PHÁP / ĐỘ ƯU TIÊN
   10 + 5 * 2  -> 10 + (5 * 2)
   NOT > AND > OR
   Dùng ngoặc để diễn đạt ý định rõ ràng

2. KIỂU DỮ LIỆU / NULL
   7 / 2        -> chia số nguyên
   7::numeric/2 -> chia thập phân
   NULL = NULL  -> UNKNOWN
   IS NULL / IS DISTINCT FROM khi cần xử lý NULL

3. ĐÁNH GIÁ / TỐI ƯU HÓA
   Planner có thể biến đổi biểu thức Boolean
   Không dựa vào thứ tự trái-phải của AND/OR để chống lỗi
   NULLIF, CASE và phép tính an toàn theo ngữ nghĩa
   Kiểm tra kết quả trước khi tối ưu EXPLAIN
```

**Độ ưu tiên** cho PostgreSQL biết biểu thức được **nhóm như thế nào**; **kiểu dữ liệu** quyết định toán tử nào được áp dụng và giá trị nào có thể sinh ra; **kế hoạch thực thi** quyết định các phần biểu thức được xử lý ra sao khi truy vấn chạy. Ba khía cạnh này liên quan nhưng không được đánh đồng.

Thói quen đáng giá nhất là **đặt ngoặc ở nơi nghiệp vụ cần một nhóm điều kiện, ép kiểu trước phép toán khi cần giữ độ chính xác, xử lý NULL có chủ đích và không dựa vào short-circuit để bảo vệ phép tính có thể lỗi**. Làm đúng các điều đó sẽ giúp câu SQL vừa dễ đọc vừa bền vững khi dữ liệu, schema hoặc kế hoạch tối ưu thay đổi.
