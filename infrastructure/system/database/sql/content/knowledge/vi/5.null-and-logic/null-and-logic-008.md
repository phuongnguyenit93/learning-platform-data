# NULLIF để chuẩn hóa giá trị và xử lý mẫu số bằng 0

Trong dữ liệu thực tế, cùng một ý nghĩa “không có giá trị sử dụng được” có thể được ghi bằng nhiều cách: `NULL`, chuỗi rỗng `''`, chuỗi chỉ có khoảng trắng, ký hiệu `'N/A'` hoặc số `0` được dùng làm mã “chưa đo”. Ở một tình huống khác, khi tính `doanh_thu / so_don_hang`, mẫu số bằng `0` có thể làm câu SQL báo lỗi chia cho 0.

Hàm **`NULLIF`** giúp xử lý hai tình huống này bằng cùng một quy tắc: **nếu hai biểu thức bằng nhau thì trả về `NULL`; nếu không thì trả về biểu thức thứ nhất**. Tuy nhiên, việc chuyển một giá trị thành `NULL` chỉ đúng khi có ý nghĩa nghiệp vụ rõ ràng. Số `0` đôi khi là dữ liệu hợp lệ, còn `NULL` biểu thị không có giá trị xác định.

Bài học thuộc nhóm **Database SQL → NULL và logic**, giải thích cách `NULLIF` tương tác với logic ba giá trị, cách chuẩn hóa dữ liệu thiếu và cách tính tỷ lệ không gặp lỗi chia cho 0. Các bài thực hành dùng **PostgreSQL**; những điểm khác nhau giữa các hệ quản trị được nhắc rõ.

## 1. Cú pháp và ý nghĩa của `NULLIF`

Cú pháp cơ bản:

```sql
NULLIF(expression_1, expression_2)
```

Quy tắc diễn giải:

- Khi `expression_1 = expression_2` cho kết quả **TRUE**, `NULLIF` trả `NULL`.
- Khi phép so sánh **FALSE** hoặc **UNKNOWN**, `NULLIF` trả giá trị của `expression_1`.
- Hai biểu thức phải có kiểu dữ liệu tương thích với phép so sánh bằng của DBMS đang dùng.

Có thể hiểu ngữ nghĩa thông thường qua `CASE`:

```sql
CASE
    WHEN expression_1 = expression_2 THEN NULL
    ELSE expression_1
END
```

Đây là cách giải thích **kết quả logic**, không phải lời khẳng định rằng mọi DBMS thực hiện hai biểu thức đúng một lần hoặc sinh cùng kế hoạch thực thi. Với biểu thức chứa hàm có tác dụng phụ hay giá trị thay đổi, cần đặc biệt thận trọng.

### Bảng kết quả cơ bản

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `NULLIF(5, 5)` | `NULL` | Hai giá trị bằng nhau |
| `NULLIF(5, 7)` | `5` | Hai giá trị khác nhau |
| `NULLIF(0, 0)` | `NULL` | Giá trị `0` khớp giá trị cần thay |
| `NULLIF(0, 1)` | `0` | `0` vẫn được giữ khi không khớp |
| `NULLIF('N/A', 'N/A')` | `NULL` | Chuỗi khớp nhau |
| `NULLIF('active', 'N/A')` | `'active'` | Chuỗi khác nhau |

Với giá trị `NULL`, hãy dùng kiểu được khai báo rõ khi cần:

```sql
-- PostgreSQL
SELECT NULLIF(NULL::INTEGER, 0) AS missing_left,
       NULLIF(5, NULL::INTEGER) AS missing_right,
       NULLIF(NULL::INTEGER, NULL::INTEGER) AS both_missing;
```

Kết quả tương ứng là `NULL`, `5` và `NULL`. Trường hợp cả hai đầu vào đều `NULL` cần hiểu đúng: `NULL = NULL` **không phải TRUE**; kết quả `NULLIF` vẫn là `NULL` vì biểu thức đầu tiên vốn đã là `NULL`.

## 2. Mối liên hệ với logic ba giá trị của SQL

Trong SQL, các phép so sánh thông thường như `=`, `<>`, `<`, `>` có thể trả **TRUE**, **FALSE** hoặc **UNKNOWN** nếu có `NULL` tham gia.

```sql
-- PostgreSQL
SELECT (5 = 5)                AS comparison_true,
       (5 = 7)                AS comparison_false,
       (5 = NULL::INTEGER)    AS comparison_unknown,
       (NULL::INTEGER = NULL::INTEGER) AS nulls_equal_unknown;
```

Hai cột cuối cho giá trị `NULL`, biểu thị trạng thái logic **UNKNOWN**, không phải `FALSE`. Trong điều kiện `WHERE`, chỉ những hàng có điều kiện là `TRUE` mới được giữ.

Với `NULLIF(a,b)`, nhánh trả `NULL` chỉ xảy ra khi `a = b` thực sự là `TRUE`. Nếu phép so sánh là `UNKNOWN`, nhánh “giữ `a`” được áp dụng; `a` có thể chính là `NULL`.

Không dùng cú pháp sau để kiểm tra kết quả:

```sql
-- Sai ý nghĩa: phép so sánh với NULL không xác định
SELECT NULLIF(0, 0) = NULL;
```

Thay bằng toán tử kiểm tra `NULL`:

```sql
SELECT NULLIF(0, 0) IS NULL     AS is_missing,
       NULLIF(5, 0) IS NOT NULL AS has_value;
```

Quy tắc quan trọng: **`NULLIF` tạo ra `NULL`; `IS NULL` và `IS NOT NULL` dùng để kiểm tra `NULL`**.

## 3. Chuẩn hóa dữ liệu: khi một giá trị giả biểu thị “không có”

Giả sử hệ thống nhập dữ liệu có cột `phone_extension`, nơi chuỗi rỗng được dùng để nói “không có số máy lẻ”. Khi xuất báo cáo, ta có thể chuẩn hóa thành `NULL`:

```sql
-- PostgreSQL
SELECT NULLIF(''::TEXT, '')      AS empty_value,
       NULLIF('123'::TEXT, '')   AS valid_extension;
```

Kết quả: cột đầu là `NULL`, cột sau là `'123'`.

Việc này hữu ích vì nhiều toán tử và hàm SQL có quy tắc xử lý `NULL` rõ ràng: `COUNT(column)` bỏ qua `NULL`, `AVG(column)` bỏ qua `NULL`, còn `COALESCE` cung cấp giá trị thay thế khi biểu thức là `NULL`.

### 3.1. Chuỗi rỗng và chuỗi chỉ chứa khoảng trắng

`NULLIF(column, '')` chỉ nhận diện **chuỗi rỗng chính xác**. Các chuỗi `'   '` hoặc `'  A01  '` có khoảng trắng không khớp với `''`.

Có thể chuẩn hóa khoảng trắng bằng `TRIM` trước:

```sql
-- PostgreSQL
SELECT NULLIF(TRIM(''::TEXT), '')       AS empty_to_null,
       NULLIF(TRIM('   '::TEXT), '')    AS spaces_to_null,
       NULLIF(TRIM('  A01  '::TEXT), '') AS trimmed_code;
```

Kết quả lần lượt là `NULL`, `NULL` và `'A01'`.

Thứ tự ở đây có ý nghĩa:

```text
Giá trị nhập: "   "
       │
       ▼
TRIM(...)       → ""
       │
       ▼
NULLIF(..., '') → NULL
```

Đây là **chuẩn hóa giá trị trong biểu thức truy vấn**; nó không tự động sửa dữ liệu đang lưu trong bảng.

Chú ý: `TRIM` mặc định loại bỏ ký tự khoảng trắng được xác định theo cú pháp/hệ quản trị. Nó không nhất thiết loại bỏ mọi loại khoảng trắng Unicode, ký tự điều khiển hoặc dấu phân cách ẩn. Nếu dữ liệu nhập đến từ nhiều nguồn, quy tắc làm sạch ký tự cần được định nghĩa rõ.

### 3.2. Chuẩn hóa ký hiệu như `'N/A'`, `'UNKNOWN'`

Giả sử `'N/A'` có nghĩa “không áp dụng”. Ta có thể dùng `NULLIF` sau khi chuẩn hóa chữ hoa/chữ thường:

```sql
-- PostgreSQL
SELECT NULLIF(UPPER(TRIM(' n/a '::TEXT)), 'N/A') AS normalized_value;
```

Kết quả là `NULL`.

Muốn xem cả trường hợp ký hiệu `'UNKNOWN'`, có thể dùng các lần `NULLIF` lồng nhau:

```sql
WITH source_values(raw_code) AS (
    VALUES
        (' A12 '::TEXT),
        (' n/a '::TEXT),
        ('Unknown'::TEXT),
        ('   '::TEXT),
        (NULL::TEXT)
),
prepared AS (
    SELECT raw_code,
           UPPER(TRIM(raw_code)) AS cleaned_code
    FROM source_values
)
SELECT raw_code,
       NULLIF(
           NULLIF(
               NULLIF(cleaned_code, ''),
               'N/A'
           ),
           'UNKNOWN'
       ) AS normalized_code
FROM prepared;
```

| Giá trị gốc | Giá trị chuẩn hóa |
| --- | --- |
| `' A12 '` | `'A12'` |
| `' n/a '` | `NULL` |
| `'Unknown'` | `NULL` |
| `'   '` | `NULL` |
| `NULL` | `NULL` |

Đoạn này giả định mã không phân biệt chữ hoa/chữ thường. Nếu mã `'Ab1'` và `'AB1'` là hai mã khác nhau, không được tự ý áp dụng `UPPER`.

Khi có nhiều mã đặc biệt, `CASE`, bảng quy tắc ánh xạ hoặc bước làm sạch dữ liệu có thể rõ ràng hơn việc lồng hàng loạt `NULLIF`.

### 3.3. Giá trị số `0` hoặc `-1` có phải dữ liệu thiếu?

Trong một hệ thống cảm biến cũ, `-1` có thể là mã báo lỗi. Khi đó:

```sql
SELECT NULLIF(sensor_value, -1) AS valid_reading
FROM sensor_data;
```

Câu lệnh chỉ là **mẫu minh họa**, giả sử bảng `sensor_data` và cột `sensor_value` đã tồn tại.

Ngược lại, không nên chuyển `0` thành `NULL` chỉ vì cột có nhiều số 0. Ví dụ:

- `temperature = 0` có thể là nhiệt độ hợp lệ.
- `discount_percent = 0` có nghĩa không giảm giá, một giá trị xác định.
- `number_of_orders = 0` có thể là số lượng đơn hàng thực tế.
- `blood_pressure = 0` có thể là giá trị đo lỗi trong một hệ thống cụ thể, nhưng việc hiểu nó là thiếu dữ liệu phải dựa vào quy tắc nguồn.

**`NULLIF` không biết quy tắc nghiệp vụ**. Bạn phải xác định rõ giá trị nào là “mã thiếu” trước khi áp dụng.

## 4. Vì sao `NULLIF` giải quyết được mẫu số bằng 0?

Phép chia có dạng:

\[
\text{ratio} = \frac{\text{numerator}}{\text{denominator}}
\]

Khi mẫu số bằng `0`, thương số không được xác định theo phép chia thông thường. Trong PostgreSQL và nhiều DBMS, phép chia trực tiếp cho `0` sinh lỗi:

```sql
-- PostgreSQL: gây lỗi division by zero
SELECT 10::NUMERIC / 0::NUMERIC;
```

Để biểu diễn rằng tỷ lệ không xác định khi mẫu số bằng 0:

```sql
-- PostgreSQL: không phát sinh phép chia cho 0
SELECT 10::NUMERIC / NULLIF(0::NUMERIC, 0::NUMERIC) AS safe_ratio;
```

`NULLIF(0,0)` tạo `NULL`. Khi mẫu số là `NULL`, kết quả phép chia số học thông thường cũng là `NULL`; phép chia cho 0 không được thực hiện.

Công thức cơ bản:

```sql
numerator / NULLIF(denominator, 0)
```

Công thức này xử lý ba trạng thái:

| Tử số | Mẫu số | Kết quả nguyên tắc |
| ---: | ---: | --- |
| `10` | `2` | `5` |
| `10` | `0` | `NULL` (không xác định) |
| `10` | `NULL` | `NULL` (thiếu mẫu số) |
| `NULL` | `2` | `NULL` (thiếu tử số) |
| `0` | `2` | `0` (tỷ lệ hợp lệ bằng 0) |
| `0` | `0` | `NULL` (không phải 0) |

Ví dụ chạy được trong PostgreSQL:

```sql
SELECT 10::NUMERIC / NULLIF(2::NUMERIC, 0) AS ratio_ok,
       10::NUMERIC / NULLIF(0::NUMERIC, 0) AS ratio_zero_denominator,
       0::NUMERIC  / NULLIF(2::NUMERIC, 0) AS zero_numerator;
```

Kết quả là `5`, `NULL` và `0`. Trường hợp `0 / 0` **không được coi là 0**.

### 4.1. Phải quan tâm đến kiểu dữ liệu của phép chia

`NULLIF` bảo vệ mẫu số, nhưng **không tự đổi phép chia số nguyên thành phép chia thập phân**.

Trong PostgreSQL:

```sql
SELECT 5 / NULLIF(2, 0) AS integer_result;

SELECT 5::NUMERIC / NULLIF(2, 0) AS decimal_result;
```

Kết quả thứ nhất là `2` vì hai toán hạng được xử lý như số nguyên. Kết quả thứ hai là `2.5` vì tử số được ép sang `NUMERIC` trước phép chia.

Khi tính tỷ lệ hay phần trăm, nên chọn kiểu có khả năng biểu diễn phần lẻ rõ ràng:

```sql
SELECT ROUND(
           5::NUMERIC / NULLIF(2, 0),
           2
       ) AS decimal_ratio;
```

`ROUND` chỉ kiểm soát số chữ số của kết quả trong trường hợp dùng kiểu thích hợp; nó không thay thế việc bảo vệ mẫu số.

### 4.2. Dùng `COALESCE` khi thật sự muốn giá trị mặc định

Một số giao diện yêu cầu luôn hiển thị số, ví dụ bảng điều khiển muốn hiển thị `0` nếu chưa có đơn hàng:

```sql
SELECT COALESCE(
           10::NUMERIC / NULLIF(0::NUMERIC, 0),
           0
       ) AS display_ratio;
```

Kết quả là `0`, nhưng đây là **quy ước hiển thị được lựa chọn**, không phải tỷ lệ toán học thật của `10 / 0`. Nếu `NULL` có nghĩa “chưa đủ dữ liệu”, thay bằng `0` sẽ làm mất khả năng phân biệt “không có tỷ lệ” với “tỷ lệ bằng 0”.

So sánh hai cách đặt `COALESCE`:

```sql
-- Bảo vệ chia cho 0, rồi mới thay kết quả NULL nếu muốn
COALESCE(numerator / NULLIF(denominator, 0), 0)

-- Không phải cách bảo vệ tương đương: khi denominator = 0,
-- COALESCE trả lại 0 và phép chia vẫn có thể lỗi
numerator / COALESCE(denominator, 0)
```

Trong PostgreSQL, cách thứ hai **không bảo vệ** phép chia cho 0 và còn biến mẫu số `NULL` thành `0`.

## 5. Thực hành trên một bảng dữ liệu nhỏ

Phần này dùng **PostgreSQL** và bảng tạm để không tạo bảng lâu dài. Hãy chạy trong một kết nối database thực hành. Lệnh tạo bảng tạm chỉ chạy một lần cho mỗi tên bảng trong phiên.

### Bước 1: Tạo bảng dữ liệu thô

```sql
CREATE TEMP TABLE nullif_lab (
    row_id        INTEGER PRIMARY KEY,
    external_code TEXT,
    revenue       NUMERIC(12, 2),
    order_count   INTEGER
);

INSERT INTO nullif_lab (row_id, external_code, revenue, order_count)
VALUES
    (1, ' A01 ', 100.00, 5),
    (2, '   ',    50.00, 0),
    (3, 'N/A',    20.00, NULL),
    (4, ' b02 ',   0.00, 4),
    (5, NULL,     NULL, 2);
```

Dữ liệu được cố ý thiết kế để có khoảng trắng, ký hiệu không có mã, mẫu số bằng `0` và trường `NULL`.

### Bước 2: Chuẩn hóa mã mà chưa sửa dữ liệu nguồn

```sql
SELECT row_id,
       external_code,
       NULLIF(TRIM(external_code), '') AS normalized_code
FROM nullif_lab
ORDER BY row_id;
```

| `row_id` | `external_code` | `normalized_code` |
| ---: | --- | --- |
| 1 | `' A01 '` | `'A01'` |
| 2 | `'   '` | `NULL` |
| 3 | `'N/A'` | `'N/A'` |
| 4 | `' b02 '` | `'b02'` |
| 5 | `NULL` | `NULL` |

`NULLIF(TRIM(external_code), '')` chỉ biến mã trống thành `NULL`. Nó **chưa xử lý** `'N/A'`, vì đây là giá trị khác `''`.

Muốn xử lý đồng thời chuỗi trống và `'N/A'`:

```sql
SELECT row_id,
       NULLIF(
           NULLIF(TRIM(external_code), ''),
           'N/A'
       ) AS normalized_code
FROM nullif_lab
ORDER BY row_id;
```

Cột mã đã chuẩn hóa lúc này là `'A01'`, `NULL`, `NULL`, `'b02'`, `NULL`. Nếu dữ liệu thực tế có các dạng `'n/a'`, `' N/A '`, quy tắc chuẩn hóa chữ hoa/chữ thường phải được đưa vào biểu thức theo yêu cầu nghiệp vụ.

### Bước 3: Tính doanh thu bình quân trên một đơn hàng

```sql
SELECT row_id,
       revenue,
       order_count,
       revenue / NULLIF(order_count, 0) AS revenue_per_order
FROM nullif_lab
ORDER BY row_id;
```

Vì `revenue` là `NUMERIC` nên phép chia ở PostgreSQL cho phép biểu diễn số thập phân. Kết quả có ý nghĩa:

| `row_id` | `revenue` | `order_count` | `revenue_per_order` |
| ---: | ---: | ---: | ---: |
| 1 | 100.00 | 5 | 20 |
| 2 | 50.00 | 0 | `NULL` |
| 3 | 20.00 | `NULL` | `NULL` |
| 4 | 0.00 | 4 | 0 |
| 5 | `NULL` | 2 | `NULL` |

Ba lý do ra `NULL` khác nhau: mẫu số bằng 0 (hàng 2), mẫu số thiếu (hàng 3) và tử số thiếu (hàng 5). Một cột kết quả `NULL` không tự cho biết lý do, vì vậy dữ liệu hoặc câu truy vấn bổ sung cần giữ thông tin nguồn nếu phải phân loại trạng thái.

### Bước 4: Trả cả tỷ lệ lẫn trạng thái để giải thích kết quả

```sql
SELECT row_id,
       CASE
           WHEN order_count IS NULL THEN 'missing_denominator'
           WHEN order_count = 0 THEN 'zero_denominator'
           WHEN revenue IS NULL THEN 'missing_numerator'
           ELSE 'valid'
       END AS ratio_status,
       revenue / NULLIF(order_count, 0) AS revenue_per_order
FROM nullif_lab
ORDER BY row_id;
```

Cách này vẫn dùng `NULLIF` để bảo vệ phép chia, đồng thời dùng `CASE` khi cần **giải thích lý do**:

- Hàng 1 và 4: `valid`.
- Hàng 2: `zero_denominator`.
- Hàng 3: `missing_denominator`.
- Hàng 5: `missing_numerator`.

Với báo cáo và API, một trường `ratio_status` có thể hữu ích hơn việc âm thầm thay mọi kết quả `NULL` bằng `0`.

## 6. `NULLIF`, `COALESCE` và `CASE` phối hợp thế nào?

Ba biểu thức phục vụ những câu hỏi khác nhau:

| Biểu thức | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| `NULLIF(a,b)` | Giá trị `a` có bằng mã/giá trị phải coi là thiếu không? | `NULLIF(order_count, 0)` |
| `COALESCE(a,b)` | Nếu `a` là `NULL`, dùng giá trị thay thế nào? | `COALESCE(note, 'Chưa có')` |
| `CASE WHEN ...` | Có cần nhiều nhánh điều kiện với những kết quả khác nhau không? | Phân biệt mẫu số thiếu, mẫu số bằng 0 và tỷ lệ hợp lệ |

Ví dụ kết hợp cả ba:

```sql
SELECT row_id,
       COALESCE(
           NULLIF(TRIM(external_code), ''),
           '(không có mã)'
       ) AS code_display,
       CASE
           WHEN order_count = 0 THEN 'Không thể tính: 0 đơn hàng'
           WHEN order_count IS NULL THEN 'Chưa biết số đơn hàng'
           WHEN revenue IS NULL THEN 'Chưa biết doanh thu'
           ELSE 'Tính được'
       END AS explanation,
       ROUND(revenue / NULLIF(order_count, 0), 2) AS average_revenue
FROM nullif_lab
ORDER BY row_id;
```

Ở đây `COALESCE` chỉ phục vụ nhãn hiển thị; `CASE` giải thích trạng thái; `NULLIF` xử lý riêng trường hợp mẫu số bằng 0. Mỗi thành phần có mục đích riêng nên dễ bảo trì hơn một biểu thức lồng nhiều tầng không có giải thích.

## 7. `NULLIF` làm thay đổi kết quả hàm tổng hợp

Nhiều hàm tổng hợp SQL bỏ qua `NULL` trong cột đầu vào:

- `COUNT(*)` đếm tất cả hàng.
- `COUNT(expression)` đếm hàng mà biểu thức khác `NULL`.
- `SUM(expression)` và `AVG(expression)` bỏ qua các giá trị `NULL`.
- Nếu một nhóm không có giá trị khác `NULL` để tính `SUM` hoặc `AVG`, kết quả thường là `NULL` (trong khi `COUNT` bằng `0`).

Vì vậy, `NULLIF` có thể thay đổi ý nghĩa thống kê:

```sql
WITH readings(value) AS (
    VALUES (0::NUMERIC), (50::NUMERIC), (100::NUMERIC)
)
SELECT COUNT(*)                   AS row_count,
       COUNT(value)               AS all_non_null_values,
       COUNT(NULLIF(value, 0))    AS non_zero_values,
       AVG(value)                 AS avg_including_zero,
       AVG(NULLIF(value, 0))      AS avg_excluding_zero
FROM readings;
```

Kết quả:

| `row_count` | `all_non_null_values` | `non_zero_values` | `avg_including_zero` | `avg_excluding_zero` |
| ---: | ---: | ---: | ---: | ---: |
| 3 | 3 | 2 | 50 | 75 |

Hai cách tính trung bình đều đúng **theo giả định riêng**:

- `AVG(value)` đúng nếu `0` là phép đo hợp lệ.
- `AVG(NULLIF(value,0))` đúng nếu `0` là mã “không có phép đo” và phải bị loại khỏi mẫu thống kê.

Nếu biến mọi giá trị `0` thành `NULL` một cách vô điều kiện, bạn có thể vô tình làm tăng trung bình hoặc giảm số lượng mẫu. Ngược lại, nếu để mã `0` đại diện giá trị thiếu, báo cáo có thể bị kéo về 0 không đúng thực tế.

## 8. Dùng `NULLIF` cho tỷ lệ sau `SUM`

Một tình huống phổ biến là tính tỷ lệ tổng:

```sql
SELECT SUM(revenue) / NULLIF(SUM(order_count), 0)
       AS overall_revenue_per_order
FROM nullif_lab;
```

Biểu thức `NULLIF(SUM(order_count), 0)` bảo vệ **mẫu số sau khi tổng hợp**. Đây là thứ tự đúng khi nghiệp vụ yêu cầu `tổng doanh thu / tổng số đơn`.

Không đồng nhất hai công thức sau:

```sql
-- Tỷ lệ trên tổng các giá trị
SUM(revenue) / NULLIF(SUM(order_count), 0)

-- Trung bình các tỷ lệ trên từng dòng
AVG(revenue / NULLIF(order_count, 0))
```

Chúng đo lường hai đại lượng khác nhau. Để thấy rõ, xét dữ liệu ví dụ:

```sql
WITH groups(revenue, orders) AS (
    VALUES
        (10::NUMERIC, 2),
        (30::NUMERIC, 0),
        (20::NUMERIC, 4)
)
SELECT SUM(revenue) / NULLIF(SUM(orders), 0)
           AS ratio_of_totals,
       AVG(revenue / NULLIF(orders, 0))
           AS average_row_ratio
FROM groups;
```

`ratio_of_totals` = `60 / 6 = 10`; `average_row_ratio` = `AVG(5, NULL, 5) = 5`.

Tại sao khác nhau? Hàng `revenue = 30` và `orders = 0` không tạo tỷ lệ trên từng dòng (vì bị chuyển thành `NULL`), nhưng **doanh thu 30 vẫn đi vào tổng doanh thu**. Nếu một hàng có `orders = 0` và `revenue > 0` là dữ liệu không hợp lệ theo nghiệp vụ, cần giải quyết tính hợp lệ của hàng đó thay vì giả định `NULLIF` sẽ tự loại nó khỏi mọi phép tổng hợp.

Trong PostgreSQL, có thể chỉ cộng những hàng thỏa điều kiện nghiệp vụ:

```sql
WITH groups(revenue, orders) AS (
    VALUES
        (10::NUMERIC, 2),
        (30::NUMERIC, 0),
        (20::NUMERIC, 4)
)
SELECT SUM(revenue) FILTER (WHERE orders > 0)
       / NULLIF(SUM(orders) FILTER (WHERE orders > 0), 0)
       AS valid_rows_ratio
FROM groups;
```

Kết quả `30 / 6 = 5`. Cú pháp `FILTER` được PostgreSQL hỗ trợ, nhưng mức độ hỗ trợ theo DBMS có thể khác. Dù cách viết là `FILTER` hay `CASE`, điều quan trọng là **tử số và mẫu số phải cùng tuân theo chính sách chọn dữ liệu**.

### Mẫu số là kết quả đếm

Một ví dụ khác là bình quân doanh thu trên số khách hàng hợp lệ:

```sql
WITH customers(customer_id, spend) AS (
    VALUES
        (1, 120::NUMERIC),
        (2, 80::NUMERIC),
        (3, NULL::NUMERIC)
)
SELECT SUM(spend)
       / NULLIF(COUNT(spend), 0) AS average_known_spend
FROM customers;
```

`COUNT(spend)` chỉ đếm khách có giá trị chi tiêu đã biết. Khi tất cả `spend` là `NULL`, `COUNT(spend)` bằng 0 và `NULLIF` chuyển mẫu số về `NULL`; phép tính không gây chia cho 0.

Nếu muốn tính trung bình các giá trị khác `NULL`, `AVG(spend)` vốn đã thực hiện quy tắc đó và thường rõ ràng hơn. Công thức minh họa ở trên hữu ích khi làm quen với bảo vệ mẫu số là một biểu thức tổng hợp.

## 9. `NULLIF` trong điều kiện `WHERE`

Giả sử muốn tìm những hàng có mã thực sự sử dụng được:

```sql
SELECT row_id, external_code
FROM nullif_lab
WHERE NULLIF(TRIM(external_code), '') IS NOT NULL
ORDER BY row_id;
```

Câu trên loại giá trị `NULL`, chuỗi rỗng và chuỗi chỉ có khoảng trắng. Nó **chưa loại `'N/A'`**, trừ khi thêm quy tắc tương ứng.

Để tìm hàng có mã bị thiếu theo quy tắc chuỗi rỗng:

```sql
SELECT row_id
FROM nullif_lab
WHERE NULLIF(TRIM(external_code), '') IS NULL
ORDER BY row_id;
```

Với bảng tạm đã tạo, kết quả là hàng 2 và 5. Giá trị `NULL` đi qua `TRIM` và `NULLIF` vẫn là `NULL`.

`WHERE NULLIF(column, sentinel) IS NULL` là một cách diễn đạt thuận tiện để tìm cả `NULL` gốc lẫn mã sentinel. Tuy nhiên, các hàm bọc quanh cột có thể ảnh hưởng khả năng dùng một số loại index thông thường. Với bảng lớn, hãy xem kế hoạch thực thi và cân nhắc chuẩn hóa khi ghi, cột tính toán hoặc index biểu thức được DBMS hỗ trợ.

## 10. Chuẩn hóa trong `SELECT` khác với sửa dữ liệu đã lưu

Có hai tình huống cần phân biệt:

**Chuẩn hóa khi đọc:**

```sql
SELECT NULLIF(TRIM(external_code), '') AS code
FROM nullif_lab;
```

Kết quả truy vấn được chuẩn hóa, còn giá trị gốc trong bảng **không đổi**.

**Chuẩn hóa và lưu vào cột đích:**

```sql
-- Ví dụ cấu trúc thao tác, giả sử target_table đã được chuẩn bị:
INSERT INTO target_table (external_code)
SELECT NULLIF(TRIM(external_code), '')
FROM source_table;
```

Ở cách thứ hai, biểu thức chuẩn hóa trở thành dữ liệu được lưu vào bảng đích, nếu ràng buộc cột cho phép `NULL`. `target_table` và `source_table` ở đây chỉ là tên minh họa, không phải các bảng được tạo trong bài thực hành.

Một kế hoạch nhập dữ liệu đáng tin cậy thường giữ được **giá trị thô** để truy vết, định nghĩa **giá trị chuẩn hóa** cho xử lý và ghi lại **quy tắc chuyển đổi**. Không cập nhật hàng loạt `0`, `'N/A'` hay `''` thành `NULL` trên dữ liệu nghiệp vụ trước khi xác nhận ý nghĩa từng trường.

### Ràng buộc bảng có thể hỗ trợ chính sách dữ liệu

Nếu một cột bắt buộc có mã không rỗng, có thể chặn dữ liệu sai khi lưu, ví dụ PostgreSQL:

```sql
CREATE TEMP TABLE valid_codes (
    id   INTEGER PRIMARY KEY,
    code TEXT NOT NULL
         CHECK (TRIM(code) <> '')
);
```

Ở đây `NOT NULL` ngăn giá trị `NULL` và `CHECK` ngăn chuỗi rỗng hoặc chỉ khoảng trắng. Quy tắc kiểm tra cần bao quát cả tình huống `NULL` vì trong SQL, một `CHECK` có biểu thức kết quả `UNKNOWN` thường không tự từ chối hàng. Ví dụ trên dùng kết hợp `NOT NULL` và `CHECK` để thể hiện chính sách rõ ràng.

## 11. Những giới hạn và trường hợp cần chú ý

### 11.1. Kiểu dữ liệu và quy tắc so sánh

`NULLIF(a,b)` phải so sánh được hai biểu thức. Không nên ngầm cho rằng mọi chuỗi, số và ngày giờ có thể so sánh trực tiếp hoặc được ép về cùng một kiểu giống nhau trên mọi DBMS.

Ví dụ PostgreSQL:

```sql
SELECT NULLIF(0::INTEGER, 0::INTEGER) AS integer_result,
       NULLIF(0.00::NUMERIC, 0::NUMERIC) AS numeric_result;
```

Kiểu kết quả của `NULLIF` phụ thuộc cơ chế phân giải toán tử và ép kiểu của hệ quản trị. PostgreSQL có thể nâng kiểu của biểu thức thứ nhất để tìm toán tử `=` phù hợp; SQL Server mô tả `NULLIF` trả kiểu của biểu thức thứ nhất. Để dễ kiểm soát, hãy ghi kiểu rõ ràng khi có sự kết hợp giữa integer, decimal, floating point và chuỗi.

### 11.2. So sánh chuỗi phụ thuộc chuẩn hóa và collation

Hai chuỗi trông giống nhau chưa chắc so sánh bằng nhau: chúng có thể khác khoảng trắng, chữ hoa/chữ thường, chuẩn Unicode hoặc collation.

```sql
-- PostgreSQL: không trùng chuỗi nếu chưa TRIM
SELECT NULLIF(' N/A '::TEXT, 'N/A') AS still_has_spaces;

-- Chuẩn hóa khoảng trắng trước khi so sánh
SELECT NULLIF(TRIM(' N/A '::TEXT), 'N/A') AS missing_marker;
```

Ví dụ đầu giữ `' N/A '`; ví dụ sau trả `NULL`. Khi chuẩn hóa mã, hãy viết rõ các bước biến đổi cần thiết thay vì phụ thuộc một cách ngầm vào collation.

### 11.3. Số rất gần 0 chưa chắc bằng 0

`NULLIF(denominator,0)` so sánh **bằng 0**. Với dữ liệu dấu phẩy động, một mẫu số như `0.00000000001` không bằng 0 nhưng có thể tạo tỷ lệ rất lớn.

Nếu nghiệp vụ xem mọi giá trị có độ lớn dưới một ngưỡng là không đáng tin cậy, cần quy tắc khác:

```sql
-- PostgreSQL: ngưỡng chỉ mang tính minh họa
WITH measurements(numerator, denominator) AS (
    VALUES (10.0::NUMERIC, 0.000001::NUMERIC)
)
SELECT CASE
           WHEN denominator IS NULL THEN NULL
           WHEN ABS(denominator) < 0.001 THEN NULL
           ELSE numerator / denominator
       END AS ratio_with_threshold
FROM measurements;
```

Ngưỡng `0.001` chỉ nên được dùng khi có cơ sở từ đơn vị, sai số đo và yêu cầu nghiệp vụ. Đây là vấn đề riêng so với kiểm tra mẫu số **chính xác bằng 0** của `NULLIF`.

### 11.4. Hệ quản trị có thể xử lý chia cho 0 khác nhau

- **PostgreSQL**: phép chia trực tiếp cho 0 thường phát sinh lỗi; `NULLIF` là cách phổ biến để chuyển mẫu số 0 thành `NULL` trước phép chia.
- **SQL Server**: phép chia cho 0 thường phát sinh lỗi; có thể dùng `NULLIF` để tránh lỗi và dùng `CAST` nếu cần kết quả decimal.
- **MySQL**: lỗi, cảnh báo hoặc kết quả `NULL` khi chia cho 0 phụ thuộc ngữ cảnh và chế độ SQL; `NULLIF` thể hiện rõ ý định và không nên dựa vào hành vi ngầm của môi trường.
- **SQLite**: phép chia cho 0 thường cho `NULL` thay vì lỗi; dùng `NULLIF` vẫn giúp thể hiện quy tắc nghiệp vụ rõ ràng.
- **Oracle Database**: phép chia cho 0 có thể báo lỗi; lưu ý thêm rằng Oracle hiện coi chuỗi ký tự độ dài bằng 0 là `NULL` trong nhiều ngữ cảnh, nên `NULLIF(text_col, '')` có thể mang hành vi khác với PostgreSQL.

Sự khác biệt này làm cho việc thử SQL trên đúng DBMS mục tiêu trở nên cần thiết, đặc biệt khi di chuyển truy vấn giữa các hệ.

### 11.5. `NULLIF` không kiểm tra tất cả loại dữ liệu lỗi

`NULLIF` không thay thế cơ chế kiểm tra kiểu số, quyền truy cập, ràng buộc khóa, lỗi chuyển đổi hay kiểm tra dữ liệu nhập. Ví dụ mẫu số là chuỗi `'abc'` không thể coi là số hợp lệ chỉ bằng cách viết `NULLIF(denominator, 0)`.

Phải xác thực và chuyển đổi dữ liệu đúng kiểu trước khi tính. Trong hệ có nhiều giá trị không hợp lệ, đôi khi cần một bước phân loại `CASE` hoặc cơ chế nhập liệu an toàn phù hợp DBMS để tránh lỗi ép kiểu.

## 12. Những lỗi thường gặp khi dùng `NULLIF`

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Truy vấn vẫn báo chia cho 0 | Đặt `NULLIF` sai vị trí hoặc dùng `COALESCE(denominator,0)` | Bảo vệ **chính mẫu số** bằng `numerator / NULLIF(denominator,0)` |
| Kết quả bằng `2` thay vì `2.5` | Phép chia integer | Ép một toán hạng sang decimal trước khi chia |
| `AVG` tăng bất thường sau chuẩn hóa | Chuyển các giá trị `0` hợp lệ thành `NULL` rồi bị bỏ qua khi tính trung bình | Xác định `0` là số đo hợp lệ hay sentinel trước khi chuẩn hóa |
| `NULLIF(code,'')` không đổi chuỗi `'  '` | Chuỗi chứa khoảng trắng khác chuỗi rỗng | Dùng `NULLIF(TRIM(code),'')` nếu chính sách cho phép |
| `'n/a'` không được nhận diện là `'N/A'` | Khác cách viết chữ hoa/thường | Dùng chuẩn hóa chữ nếu mã không phân biệt hoa/thường |
| Tỷ lệ `NULL` bị hiển thị như `0` | `COALESCE` hoặc tầng giao diện tự đặt giá trị mặc định | Giữ trạng thái riêng để không lẫn “chưa xác định” với 0 |
| `NULLIF(NULL,NULL)` là `NULL` nên tưởng `NULL = NULL` là TRUE | Nhầm logic ba giá trị | Nhớ `NULL = NULL` là UNKNOWN; kết quả vẫn `NULL` do biểu thức thứ nhất đã `NULL` |
| Tỷ lệ sau `SUM` khác trung bình tỷ lệ từng hàng | Hai phép tổng hợp có ý nghĩa khác nhau; các hàng mẫu số 0 có thể vẫn góp vào tử số tổng | Chọn công thức và quy tắc lọc dữ liệu đúng nghiệp vụ |

## 13. Bài tập thực hành

Các bài sau dùng PostgreSQL. Có thể dùng bảng tạm `nullif_lab` ở mục 5.

### Bài 1: Dự đoán kết quả `NULLIF`

Dự đoán kết quả từng biểu thức rồi chạy:

```sql
SELECT NULLIF(0, 0)                              AS a,
       NULLIF(10, 0)                             AS b,
       NULLIF(NULL::INTEGER, 0)                  AS c,
       NULLIF(10, NULL::INTEGER)                 AS d,
       NULLIF(NULL::INTEGER, NULL::INTEGER)      AS e;
```

Hãy giải thích tại sao `c` và `e` đều trả `NULL` mà không cần kết luận phép `NULL = NULL` là đúng.

### Bài 2: Chuẩn hóa mã chuỗi

Trong bảng `nullif_lab`, hãy tạo cột kết quả `clean_code` có quy tắc:

1. Bỏ khoảng trắng hai đầu.
2. Xem chuỗi rỗng và `'N/A'` là `NULL`.
3. Giữ nguyên chữ hoa/chữ thường của các mã còn lại.

Dùng `TRIM` và `NULLIF`. Không cập nhật bảng gốc.

### Bài 3: Tính tỷ lệ an toàn

Tính `revenue_per_order` theo quy tắc:

- Nếu `order_count` bằng `0` hoặc `NULL`, kết quả là `NULL`.
- Nếu `revenue` là `NULL`, kết quả là `NULL`.
- Nếu cả hai hợp lệ và `order_count > 0`, lấy `revenue / order_count`.

Dùng `NULLIF` trong mẫu số. Xác định hàng nào có tỷ lệ đúng bằng `0`.

### Bài 4: Chuẩn hóa số đo giả

Một bảng đo có ba giá trị `0`, `25` và `75`. Tính hai trung bình: (a) coi `0` là đo hợp lệ; (b) coi `0` là mã thiếu dữ liệu. Giải thích vì sao kết quả khác nhau.

### Bài 5: Nhận diện việc làm mất ý nghĩa của `NULL`

Một báo cáo đang dùng:

```sql
COALESCE(revenue / NULLIF(order_count, 0), 0)
```

Trong trường hợp nào số `0` hiển thị có thể bị hiểu sai? Hãy đề xuất cách trả thêm `ratio_status` để phân biệt “không có doanh thu”, “không có đơn hàng” và “thiếu dữ liệu”.

### Bài 6: Chọn công thức tổng hợp

Với dữ liệu `(revenue, orders)` gồm `(10,2)`, `(30,0)` và `(20,4)`, hãy tính:

- `SUM(revenue) / NULLIF(SUM(orders),0)`
- `AVG(revenue / NULLIF(orders,0))`

Sau đó thử chỉ tính các hàng có `orders > 0`. Giải thích ý nghĩa từng con số.

### Gợi ý đáp án

**Bài 1:** `a = NULL`, `b = 10`, `c = NULL`, `d = 10`, `e = NULL`. Giá trị đầu tiên là `NULL` thì kết quả cuối cũng `NULL`; không có quy tắc so sánh “hai `NULL` bằng nhau” ở đây.

**Bài 2:**

```sql
SELECT row_id,
       NULLIF(
           NULLIF(TRIM(external_code), ''),
           'N/A'
       ) AS clean_code
FROM nullif_lab
ORDER BY row_id;
```

**Bài 3:**

```sql
SELECT row_id,
       revenue / NULLIF(order_count, 0) AS revenue_per_order
FROM nullif_lab
ORDER BY row_id;
```

Hàng 4 có `revenue_per_order = 0` vì tử số thật sự bằng 0 và mẫu số bằng 4. Hàng 2, 3 và 5 có `NULL` do mẫu số hoặc tử số không đủ để tính.

**Bài 4:**

```sql
WITH readings(value) AS (
    VALUES (0::NUMERIC), (25::NUMERIC), (75::NUMERIC)
)
SELECT AVG(value) AS treating_zero_as_valid,
       AVG(NULLIF(value, 0)) AS treating_zero_as_missing
FROM readings;
```

Kết quả lần lượt là `100/3` (xấp xỉ `33.33`) và `50`. Chọn kết quả nào phụ thuộc ý nghĩa thật của số 0.

**Bài 5:** `0` có thể là tỷ lệ hợp lệ hoặc là giá trị thay thế `NULL` do mẫu số bằng 0, mẫu số thiếu hay tử số thiếu. Có thể dùng `CASE` trả nhãn `valid`, `zero_denominator`, `missing_denominator`, `missing_numerator` đồng thời giữ kết quả `NULL` khi không xác định.

**Bài 6:** Tỷ lệ tổng là `60/6 = 10`; trung bình tỷ lệ theo hàng là `AVG(5, NULL, 5) = 5`; nếu loại hàng `orders = 0` khỏi **cả tử số và mẫu số**, tỷ lệ tổng là `(10+20)/(2+4) = 5`. Các giá trị khác nhau vì chính sách tổng hợp và chọn hàng khác nhau.

`NULLIF` ngắn gọn nhưng có sức ảnh hưởng lớn đến ý nghĩa dữ liệu: nó có thể biến mã “thiếu” thành `NULL` để các biểu thức SQL xử lý nhất quán, hoặc thay mẫu số bằng `NULL` để biểu thị phép chia không xác định. Khi dùng trong báo cáo, hãy luôn kiểm tra xem `0` là giá trị thật hay mã thiếu, và liệu bạn cần giữ lại thông tin lý do khiến kết quả trở thành `NULL`.
