# ABS, ROUND, CEILING, FLOOR và hàm số thông dụng

Trong SQL, biểu thức toán học không chỉ dùng để cộng, trừ, nhân, chia. Chúng còn giúp tính **độ lệch tuyệt đối**, **làm tròn số tiền**, **quy đổi số lượng thành số kiện hàng**, **đặt ngưỡng giá trị**, **xác định chiều âm/dương** và xử lý những phép tính có căn bậc hai hoặc lũy thừa.

Ví dụ, một đơn hàng có 23 sản phẩm, mỗi hộp đựng được 6 sản phẩm. Phép chia cho kết quả khoảng 3,83 hộp, nhưng doanh nghiệp cần **4 hộp nguyên** để đóng gói. Hàm `CEILING` phù hợp với quy tắc đó. Ở một báo cáo khác, khi tính trung bình thành tiền, bạn cần xác định làm tròn **từng dòng trước khi cộng** hay **chỉ làm tròn tổng cuối cùng**; hai cách có thể cho kết quả khác nhau. Còn khi đo sai lệch so với mục tiêu, dấu âm hoặc dương có thể không quan trọng: `ABS` trả về độ lớn của sai lệch.

Bài học thuộc nhóm **Database SQL → Biểu thức và hàm**. Các câu SQL thực hành dùng **PostgreSQL**, đồng thời phân biệt những điểm về hàm, kiểu số và quy tắc làm tròn giữa các hệ quản trị.

## 1. Bản đồ các hàm số thường dùng

| Hàm | Ý nghĩa | Ví dụ theo PostgreSQL | Kết quả |
| --- | --- | --- | --- |
| `ABS(x)` | Trị tuyệt đối của `x` | `ABS(-12.5)` | `12.5` |
| `ROUND(x)` | Làm tròn đến số nguyên gần nhất | `ROUND(12.6::NUMERIC)` | `13` |
| `ROUND(x, d)` | Làm tròn đến `d` chữ số thập phân của `NUMERIC` | `ROUND(12.345::NUMERIC, 2)` | `12.35` |
| `CEILING(x)` hoặc `CEIL(x)` | Số nguyên nhỏ nhất **lớn hơn hoặc bằng** `x` | `CEIL(12.1)` | `13` |
| `FLOOR(x)` | Số nguyên lớn nhất **nhỏ hơn hoặc bằng** `x` | `FLOOR(12.9)` | `12` |
| `TRUNC(x, d)` | Cắt bỏ chữ số thập phân dư của `NUMERIC`, đi về phía 0 | `TRUNC(12.349::NUMERIC, 2)` | `12.34` |
| `MOD(a,b)` | Phần dư của phép chia | `MOD(17, 5)` | `2` |
| `SIGN(x)` | Dấu của số: âm, 0, dương | `SIGN(-8::NUMERIC)` | `-1` |
| `POWER(a,b)` | Lũy thừa `a` mũ `b` | `POWER(2::NUMERIC, 3)` | `8` |
| `SQRT(x)` | Căn bậc hai không âm | `SQRT(81::NUMERIC)` | `9` |
| `EXP(x)` | Hàm mũ cơ số `e` | `EXP(0::NUMERIC)` | `1` |
| `LN(x)` | Logarit tự nhiên, với `x > 0` | `LN(1::NUMERIC)` | `0` |
| `LOG(x)` | Trong PostgreSQL, logarit cơ số 10 khi dùng một đối số | `LOG(100::NUMERIC)` | `2` |

Tên hàm có thể gần giống nhau giữa các DBMS, nhưng **kiểu đối số, số lượng đối số, quy tắc làm tròn, kiểu kết quả và miền giá trị hợp lệ** không phải lúc nào cũng trùng nhau.

### Hàm số trong biểu thức SELECT

Một hàm có thể nhận hằng số, cột hoặc biểu thức làm đối số:

```sql
SELECT
    ABS(-7)                AS magnitude,
    ROUND(15.678::NUMERIC, 2) AS rounded_value,
    CEILING(15.1)          AS rounded_up,
    FLOOR(15.9)            AS rounded_down;
```

Trong PostgreSQL, câu `SELECT` không cần `FROM` có thể trả một hàng gồm các kết quả trên. Khi đưa tên cột từ bảng vào đối số, hàm sẽ được áp dụng cho giá trị của từng hàng phù hợp với truy vấn.

## 2. Chuẩn bị dữ liệu để quan sát kết quả

Hãy dùng một database **PostgreSQL thực hành** và chạy các câu lệnh sau trong cùng phiên kết nối. Bảng `numeric_functions_lab` là **bảng tạm** và chỉ tồn tại trong phiên. Nếu cùng tên đã tồn tại, dùng phiên mới hoặc đổi tên bảng trước khi chạy lại.

```sql
CREATE TEMP TABLE numeric_functions_lab (
    sample_id     INTEGER PRIMARY KEY,
    measured      NUMERIC(12, 4),
    target_value  NUMERIC(12, 4),
    label         TEXT NOT NULL
);

INSERT INTO numeric_functions_lab (
    sample_id, measured, target_value, label
)
VALUES
    (1, -12.3450, -10.0000, 'Giá trị âm'),
    (2,   8.1550,  10.0000, 'Gần mục tiêu'),
    (3,  -0.2500,   0.0000, 'Âm nhỏ'),
    (4,   0.0000,   0.0000, 'Bằng không'),
    (5,  23.5000,  20.0000, 'Nửa đơn vị'),
    (6,   0.0050,   0.0000, 'Số rất nhỏ'),
    (7,      NULL,  15.0000, 'Thiếu số đo'),
    (8, 1234.5670, 1200.0000, 'Giá trị lớn');

SELECT sample_id, label, measured, target_value
FROM numeric_functions_lab
ORDER BY sample_id;
```

Bộ dữ liệu gồm số âm, số dương, số 0, một giá trị đúng nửa đơn vị, giá trị nhỏ ở phần thập phân và giá trị `NULL`. Nhờ đó bạn có thể thấy các hàm hoạt động thế nào trong tình huống thường gặp và ở ranh giới.

## 3. ABS: lấy trị tuyệt đối

**`ABS(x)`** trả về độ lớn của `x` mà không giữ dấu âm. Với số thực thông thường:

\[
|x| =
\begin{cases}
-x & \text{khi } x < 0\\
x & \text{khi } x \ge 0
\end{cases}
\]

Ví dụ:

```sql
SELECT ABS(-9::NUMERIC) AS negative_input,
       ABS(9::NUMERIC)  AS positive_input,
       ABS(0::NUMERIC)  AS zero_input;
```

Kết quả lần lượt là `9`, `9` và `0`.

### Tính độ lệch tuyệt đối so với mục tiêu

Trong bảng thực hành, biểu thức `measured - target_value` giữ lại hướng sai lệch. Biểu thức `ABS(measured - target_value)` chỉ giữ **khoảng cách số học** giữa hai giá trị:

```sql
SELECT sample_id,
       measured,
       target_value,
       measured - target_value AS signed_difference,
       ABS(measured - target_value) AS absolute_difference
FROM numeric_functions_lab
ORDER BY sample_id;
```

Vài ví dụ:

| `sample_id` | `measured` | `target_value` | Sai lệch có dấu | Sai lệch tuyệt đối |
| ---: | ---: | ---: | ---: | ---: |
| 1 | -12.3450 | -10.0000 | -2.3450 | 2.3450 |
| 2 | 8.1550 | 10.0000 | -1.8450 | 1.8450 |
| 3 | -0.2500 | 0.0000 | -0.2500 | 0.2500 |
| 4 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 5 | 23.5000 | 20.0000 | 3.5000 | 3.5000 |
| 7 | `NULL` | 15.0000 | `NULL` | `NULL` |

Nếu hệ thống yêu cầu số đo chênh lệch tối đa 2 đơn vị so với mục tiêu:

```sql
SELECT sample_id, measured, target_value
FROM numeric_functions_lab
WHERE ABS(measured - target_value) <= 2
ORDER BY sample_id;
```

Theo dữ liệu mẫu, các hàng thỏa điều kiện là **2, 3, 4 và 6**. Hàng 7 không được chọn vì `ABS(NULL)` trả `NULL`; điều kiện so sánh với `NULL` là UNKNOWN, nên `WHERE` không giữ hàng.

Việc dùng `ABS` đúng khi doanh nghiệp quan tâm **mức chênh lệch bất kể chiều**. Nếu cần phân biệt “cao hơn mục tiêu” và “thấp hơn mục tiêu”, hãy giữ thêm biểu thức sai lệch có dấu.

### Trị tuyệt đối không làm kiểu nguyên có phạm vi vô hạn

Với kiểu nguyên có dấu, số âm nhỏ nhất có độ lớn lớn hơn số dương lớn nhất cùng kiểu. Trong PostgreSQL, `INTEGER` 32 bit có miền `-2147483648` đến `2147483647`.

Ví dụ sau **cố ý gây lỗi overflow**:

```sql
-- Không chạy cùng các câu lệnh bài thực hành khác trong một transaction:
SELECT ABS('-2147483648'::INTEGER);
```

Độ lớn `2147483648` không vừa kiểu `INTEGER`. Nếu cần kết quả đó, hãy nâng kiểu toán hạng trước khi gọi hàm:

```sql
SELECT ABS('-2147483648'::INTEGER::BIGINT) AS magnitude;
```

Kết quả là `2147483648`. Việc ép kiểu **sau** khi `ABS` đã tràn không giải quyết được lỗi. Nguyên tắc này cũng áp dụng cho các phép nhân/cộng có kiểu trung gian quá nhỏ.

## 4. ROUND: làm tròn đến độ chính xác mong muốn

**`ROUND`** chọn một giá trị gần với số gốc theo mức làm tròn. Ở PostgreSQL, với kiểu `NUMERIC` có thể dùng:

```sql
ROUND(number)
ROUND(number, decimal_places)
```

Trong đó `decimal_places` chỉ vị trí làm tròn:

- `2`: giữ hai chữ số sau dấu thập phân.
- `1`: giữ một chữ số sau dấu thập phân.
- `0`: làm tròn đến hàng đơn vị.
- `-1`: làm tròn đến hàng chục.
- `-2`: làm tròn đến hàng trăm.

Ví dụ:

```sql
SELECT
    ROUND(1234.567::NUMERIC,  2) AS two_decimals,
    ROUND(1234.567::NUMERIC,  1) AS one_decimal,
    ROUND(1234.567::NUMERIC,  0) AS whole_number,
    ROUND(1234.567::NUMERIC, -1) AS nearest_ten,
    ROUND(1234.567::NUMERIC, -2) AS nearest_hundred;
```

Kết quả lần lượt là `1234.57`, `1234.6`, `1235`, `1230` và `1200`.

### ROUND theo từng hàng

```sql
SELECT sample_id,
       measured,
       ROUND(measured, 2) AS rounded_to_2,
       ROUND(measured, 0) AS rounded_to_0
FROM numeric_functions_lab
ORDER BY sample_id;
```

Kết quả quan trọng:

| `measured` | `ROUND(measured,2)` | `ROUND(measured,0)` |
| ---: | ---: | ---: |
| -12.3450 | -12.35 | -12 |
| 8.1550 | 8.16 | 8 |
| -0.2500 | -0.25 | 0 |
| 0.0000 | 0.00 | 0 |
| 23.5000 | 23.50 | 24 |
| 0.0050 | 0.01 | 0 |
| `NULL` | `NULL` | `NULL` |
| 1234.5670 | 1234.57 | 1235 |

### Quy tắc làm tròn ở đúng điểm giữa

Nếu một giá trị nằm **chính xác giữa hai kết quả có thể chọn**, DBMS cần quy tắc xử lý trường hợp hòa (tie).

Đối với **`NUMERIC` trong PostgreSQL**, quy tắc là **round half away from zero**: làm tròn ra xa số 0.

```sql
SELECT
    ROUND(2.5::NUMERIC)        AS positive_half, -- 3
    ROUND(-2.5::NUMERIC)       AS negative_half, -- -3
    ROUND(1.245::NUMERIC, 2)   AS positive_tie,  -- 1.25
    ROUND(-1.245::NUMERIC, 2)  AS negative_tie;  -- -1.25
```

Có những quy tắc khác, chẳng hạn *round half to even* (ưu tiên kết quả có chữ số cuối chẵn) và *round half toward zero*. Vì vậy không được suy ra mọi hệ quản trị, mọi kiểu số và mọi môi trường đều làm tròn giống `NUMERIC` của PostgreSQL.

### ROUND không giống định dạng hiển thị

Hàm `ROUND` tạo **một giá trị biểu thức** theo quy tắc toán học. Trong khi đó, một giao diện chỉ hiển thị hai chữ số có thể thay đổi cách **trình bày** mà không thay đổi giá trị được lưu.

Ví dụ:

```sql
SELECT ROUND(12.345::NUMERIC, 2) AS rounded_result;
```

Khi lưu vào cột `NUMERIC(p,2)`, hệ quản trị còn áp dụng kiểm tra precision/scale của kiểu đích. `ROUND(number,2)` chỉ chọn giá trị gần đúng đến hai chữ số; nó không tự xác nhận giá trị đó vừa phạm vi cột lưu trữ.

## 5. CEILING và FLOOR: luôn lấy mức trên hoặc mức dưới

Hai hàm dùng **thứ tự trên trục số**, không dựa vào cách cắt phần thập phân:

- **`CEILING(x)`** (hoặc `CEIL(x)`): số nguyên nhỏ nhất **≥ x**.
- **`FLOOR(x)`**: số nguyên lớn nhất **≤ x**.

Biểu diễn trực giác:

```text
             -3         -2         -1          0          1          2          3
──────────────┼──────────┼──────────┼───────────┼──────────┼──────────┼──────────
                 ↑ -2.3
             FLOOR = -3, CEIL = -2

                                                          ↑ 1.2
                                                   FLOOR = 1, CEIL = 2
```

Ví dụ:

```sql
SELECT
    CEILING(12.1::NUMERIC) AS positive_ceiling,
    FLOOR(12.9::NUMERIC)   AS positive_floor,
    CEILING(-12.9::NUMERIC) AS negative_ceiling,
    FLOOR(-12.1::NUMERIC)   AS negative_floor;
```

Kết quả: `13`, `12`, `-12`, `-13`.

### So sánh trên cùng một tập số

| Giá trị `x` | `FLOOR(x)` | `CEILING(x)` | `ROUND(x::NUMERIC)` |
| ---: | ---: | ---: | ---: |
| 2.1 | 2 | 3 | 2 |
| 2.5 | 2 | 3 | 3 |
| 2.9 | 2 | 3 | 3 |
| -2.1 | -3 | -2 | -2 |
| -2.5 | -3 | -2 | -3 |
| -2.9 | -3 | -2 | -3 |
| 0 | 0 | 0 | 0 |

Điểm thường bị nhầm: với số âm, **`CEILING(-2.9) = -2`**, vì `-2` là số nguyên nhỏ nhất vẫn lớn hơn hoặc bằng `-2.9`. Còn **`FLOOR(-2.1) = -3`**, vì `-3` là số nguyên lớn nhất vẫn nhỏ hơn hoặc bằng `-2.1`.

### Ứng dụng 1: tính số hộp phải sử dụng

Một hộp chứa tối đa 6 sản phẩm, đơn hàng có 23 sản phẩm. Số hộp tối thiểu:

\[
\text{boxes} = \left\lceil \frac{23}{6} \right\rceil = 4
\]

Trong PostgreSQL:

```sql
SELECT CEILING(23::NUMERIC / 6) AS required_boxes;
```

Kết quả là **4**.

Nếu viết `CEILING(23 / 6)`, PostgreSQL thực hiện phép chia hai số nguyên thành `3` trước; khi đó `CEILING(3)` vẫn là `3`. **Phải chuyển ít nhất một toán hạng sang kiểu giữ phần thập phân trước khi chia**.

Nếu đơn không có sản phẩm, `CEILING(0::NUMERIC / 6) = 0`. Công thức phù hợp khi số lượng không âm và sức chứa mỗi hộp dương. Cần kiểm tra điều kiện này trong ứng dụng hoặc dữ liệu đầu vào.

### Ứng dụng 2: làm tròn lên một bước giá

Giả sử giá trị cần làm tròn **lên bội số gần nhất của 50**:

\[
\text{rounded\_up} = \left\lceil \frac{x}{50} \right\rceil \times 50
\]

```sql
SELECT CEILING(123::NUMERIC / 50) * 50 AS rounded_up; -- 150
```

Muốn làm tròn **xuống bội số gần nhất của 50**:

```sql
SELECT FLOOR(123::NUMERIC / 50) * 50 AS rounded_down; -- 100
```

Hai công thức hoạt động theo **nghĩa toán học của trục số**. Với giá trị âm, `CEILING` tiến về phía dương vô cực và `FLOOR` tiến về phía âm vô cực; nếu nghiệp vụ yêu cầu “bỏ phần lẻ, tiến về 0” thì phải dùng quy tắc khác.

## 6. TRUNC: cắt phần thập phân thay vì làm tròn gần nhất

**`TRUNC`** bỏ các chữ số vượt vị trí được yêu cầu; với số âm, nó tiến **về 0**, không tiến về âm vô cực.

Trong PostgreSQL:

```sql
SELECT
    TRUNC(12.987::NUMERIC, 2)    AS positive_trunc, -- 12.98
    TRUNC(-12.987::NUMERIC, 2)   AS negative_trunc, -- -12.98
    TRUNC(12.987::NUMERIC)       AS positive_int,   -- 12
    TRUNC(-12.987::NUMERIC)      AS negative_int;   -- -12
```

So sánh trên cùng một giá trị:

```sql
SELECT
    ROUND(-2.79::NUMERIC, 0) AS rounded,  -- -3
    TRUNC(-2.79::NUMERIC, 0) AS truncated, -- -2
    CEIL(-2.79::NUMERIC)     AS ceiling,   -- -2
    FLOOR(-2.79::NUMERIC)    AS floored;   -- -3
```

| Hàm | `2.79` | `-2.79` |
| --- | ---: | ---: |
| `ROUND(x)` | 3 | -3 |
| `TRUNC(x)` | 2 | -2 |
| `CEILING(x)` | 3 | -2 |
| `FLOOR(x)` | 2 | -3 |

Có thể hiểu:

- `ROUND`: chọn mức gần nhất theo quy tắc rounding.
- `TRUNC`: bỏ phần không muốn giữ, hướng về 0.
- `CEILING`: hướng tới mức trên trên trục số.
- `FLOOR`: hướng tới mức dưới trên trục số.

Cắt phần thập phân có thể là yêu cầu nghiệp vụ hợp lệ, nhưng **không nên dùng `TRUNC` để thay thế `ROUND`** nếu quy định cần làm tròn gần nhất.

### TRUNC với số chữ số âm

PostgreSQL hỗ trợ cắt đến hàng chục hoặc trăm cho `NUMERIC`:

```sql
SELECT
    TRUNC(1234.567::NUMERIC, -1) AS truncated_tens,     -- 1230
    TRUNC(1234.567::NUMERIC, -2) AS truncated_hundreds, -- 1200
    TRUNC(-1234.567::NUMERIC, -2) AS negative_hundreds; -- -1200
```

Cú pháp và tên hàm cắt số khác nhau theo DBMS: MySQL có `TRUNCATE(x,d)`, Oracle có `TRUNC`, còn SQL Server thường dùng `ROUND(x,d,1)` cho tình huống cắt chữ số.

## 7. SIGN: xác định âm, dương hay bằng 0

**`SIGN(x)`** trả:

- `-1` khi `x < 0`;
- `0` khi `x = 0`;
- `1` khi `x > 0`.

```sql
SELECT
    SIGN(-10::NUMERIC) AS negative_sign,
    SIGN(0::NUMERIC)   AS zero_sign,
    SIGN(10::NUMERIC)  AS positive_sign;
```

Kết quả `-1`, `0`, `1`.

Ứng dụng trong bảng số đo:

```sql
SELECT sample_id,
       measured - target_value AS difference,
       SIGN(measured - target_value) AS direction
FROM numeric_functions_lab
ORDER BY sample_id;
```

Quy ước có thể là: `-1` nghĩa là thấp hơn mục tiêu, `0` nghĩa là đúng mục tiêu, `1` nghĩa là cao hơn mục tiêu. Nếu một trong hai giá trị thiếu, `SIGN(NULL)` trả `NULL`; hệ thống không nên tự gán “đúng mục tiêu” cho một sai lệch chưa xác định.

Khi muốn nhãn văn bản thay vì số `-1/0/1`:

```sql
SELECT sample_id,
       CASE
           WHEN measured IS NULL OR target_value IS NULL
               THEN 'Chưa đủ dữ liệu'
           WHEN measured < target_value THEN 'Thấp hơn'
           WHEN measured > target_value THEN 'Cao hơn'
           ELSE 'Bằng mục tiêu'
       END AS comparison_label
FROM numeric_functions_lab
ORDER BY sample_id;
```

`CASE` phù hợp khi cần nhánh nghiệp vụ rõ ràng, còn `SIGN` hữu ích khi cần kết quả số gọn để xử lý tiếp.

## 8. MOD: chia lấy phần dư

**`MOD(a,b)`** trả phần dư sau khi chia `a` cho `b` trong những kiểu số mà DBMS hỗ trợ. Trong PostgreSQL:

```sql
SELECT
    MOD(17, 5) AS remainder_17_5, -- 2
    MOD(12, 4) AS remainder_12_4, -- 0
    MOD(-7, 3) AS remainder_neg_7; -- -1
```

Với số nguyên trong PostgreSQL, toán tử `%` cũng thực hiện chia lấy phần dư:

```sql
SELECT 17 % 5 AS remainder;
```

### Ứng dụng: kiểm tra số chẵn và số lẻ

```sql
SELECT sample_id,
       CASE
           WHEN MOD(sample_id, 2) = 0 THEN 'Chẵn'
           ELSE 'Lẻ'
       END AS parity
FROM numeric_functions_lab
ORDER BY sample_id;
```

Nếu `sample_id` luôn là số nguyên không `NULL`, điều kiện kiểm tra phần dư bằng 0 giúp phân nhóm theo chẵn/lẻ.

### Ứng dụng: chia đều công việc

Giả sử có 17 hồ sơ chia thành các gói 5 hồ sơ:

```sql
SELECT
    17 / 5 AS full_groups,
    MOD(17, 5) AS remaining_records;
```

Trong PostgreSQL, phép chia hai số nguyên `17 / 5` cho `3`, phần dư là `2`. Nếu phải cấp một gói nữa cho hai hồ sơ còn lại, tổng số gói cần là `CEIL(17::NUMERIC / 5) = 4`.

**Lưu ý:** dấu của phần dư khi có toán hạng âm có thể gây nhầm lẫn và quy tắc của các ngôn ngữ/hệ thống có thể khác nhau. Nếu ứng dụng cần chỉ số vòng tròn luôn nằm trong `0..n-1`, cần thiết kế biểu thức xử lý phần dư âm thay vì giả định `MOD(negative,n)` luôn không âm.

Mẫu số của `MOD` phải khác 0. `MOD(17,0)` cũng là phép toán không hợp lệ; khi mẫu số có thể bằng 0, cần kiểm tra hoặc dùng `NULLIF` theo ý định nghiệp vụ.

## 9. POWER, SQRT, EXP và LOG: hàm toán học nâng cao

Các hàm này xuất hiện trong tài chính, thống kê, tính tăng trưởng, mô hình đo lường và phân tích khoa học.

### POWER: lũy thừa

```sql
SELECT
    POWER(2::NUMERIC, 3) AS two_cubed,
    POWER(10::NUMERIC, 2) AS ten_squared,
    POWER(1.05::NUMERIC, 3) AS growth_factor;
```

Kết quả lần lượt là `8`, `100`, `1.157625`.

Ví dụ một đại lượng tăng 5% mỗi kỳ trong 3 kỳ:

\[
\text{future\_value} = \text{initial\_value}\times(1+0.05)^3
\]

```sql
SELECT ROUND(
           1000::NUMERIC * POWER(1.05::NUMERIC, 3),
           2
       ) AS value_after_three_periods;
```

Kết quả là `1157.63`.

Đây là **mô hình tăng trưởng minh họa**, không phải một công thức luôn đúng cho mọi loại lãi suất hay lịch tính lãi. Cần xác định chu kỳ và quy tắc làm tròn của bài toán cụ thể.

### SQRT: căn bậc hai

```sql
SELECT SQRT(81::NUMERIC) AS exact_square_root,
       ROUND(SQRT(2::NUMERIC), 4) AS approximate_square_root;
```

Kết quả là `9` và xấp xỉ `1.4142` sau làm tròn.

Trong miền số thực, căn bậc hai của số âm không xác định. Với PostgreSQL, `SQRT` trên một số âm thông thường gây lỗi miền giá trị. Nếu dữ liệu có thể âm, cần xác định chính sách: từ chối, bỏ qua hay trả `NULL` theo yêu cầu.

Ví dụ bảo vệ miền giá trị:

```sql
SELECT sample_id,
       measured,
       CASE
           WHEN measured >= 0 THEN SQRT(measured)
           ELSE NULL
       END AS square_root_if_valid
FROM numeric_functions_lab
ORDER BY sample_id;
```

Nếu `measured IS NULL`, điều kiện `measured >= 0` là UNKNOWN; `CASE` trả `NULL` do nhánh `ELSE`. Với số âm, kết quả cũng `NULL` nhưng lý do khác nhau. Nếu cần phân biệt “thiếu giá trị” với “giá trị ngoài miền”, hãy trả thêm cột trạng thái.

### LN, LOG và EXP

Trong PostgreSQL:

```sql
SELECT
    LN(1::NUMERIC) AS natural_log_of_one,
    LOG(100::NUMERIC) AS base10_log_of_hundred,
    EXP(0::NUMERIC) AS exponential_of_zero;
```

Kết quả lần lượt là `0`, `2`, `1`.

- `LN(x)`: logarit cơ số tự nhiên `e`.
- `LOG(x)` với một đối số trong PostgreSQL: logarit cơ số 10.
- `EXP(x)`: giá trị `e^x`.

PostgreSQL còn hỗ trợ dạng `LOG(base, value)` cho kiểu số phù hợp:

```sql
SELECT LOG(2::NUMERIC, 8::NUMERIC) AS logarithm_base_two;
```

Kết quả là `3`.

**Miền giá trị:** logarit thực cần đối số dương; `LN(0)`, `LN(-1)` và `LOG(0)` không phải những phép tính hợp lệ trong miền số thực thông thường. Hàm mũ và lũy thừa cũng có thể tạo số quá lớn, gây tràn hoặc vượt khả năng tính của kiểu số. Không nên coi mọi đầu vào số đều hợp lệ cho mọi hàm.

**Khác biệt DBMS:** tên `LOG` đặc biệt dễ gây nhầm. Trong SQL Server, `LOG(x)` thường là logarit tự nhiên; cơ số 10 có hàm `LOG10`, còn PostgreSQL dùng `LN` cho logarit tự nhiên và `LOG` một đối số cho cơ số 10. Hãy đọc tài liệu của DBMS đang dùng trước khi chuyển công thức.

## 10. Tạo cột tính toán cho từng hàng và tổng hợp nhiều hàng

Hàm số trong `SELECT` có thể áp dụng cho **mỗi hàng**, hoặc kết hợp với hàm tổng hợp như `SUM`, `AVG`, `MIN`, `MAX`.

### Làm tròn từng hàng

```sql
SELECT sample_id,
       measured,
       ROUND(measured, 2) AS rounded_measurement
FROM numeric_functions_lab
ORDER BY sample_id;
```

Câu này tính một kết quả `ROUND` cho từng hàng, giữ nguyên số lượng hàng (trừ khi có `WHERE`).

### Làm tròn sau phép tổng hợp

```sql
SELECT ROUND(AVG(measured), 2) AS rounded_average
FROM numeric_functions_lab;
```

`AVG(measured)` tính trung bình các giá trị `measured` khác `NULL`, sau đó `ROUND` làm tròn kết quả chung. Đây là một **hàng kết quả tổng hợp**, không phải danh sách một kết quả cho mỗi hàng.

### Làm tròn trước khi tổng hợp

```sql
SELECT AVG(ROUND(measured, 2)) AS average_of_rounded_values
FROM numeric_functions_lab;
```

Ở đây mỗi giá trị được làm tròn trước khi `AVG` tính trung bình. Biểu thức khác với `ROUND(AVG(measured),2)` vì thứ tự thực hiện và số chữ số ở bước trung gian khác nhau.

Một ví dụ thể hiện rõ sự khác biệt:

```sql
WITH amounts(amount) AS (
    VALUES
        (1.005::NUMERIC),
        (1.005::NUMERIC)
)
SELECT
    ROUND(SUM(amount), 2) AS round_after_sum,
    SUM(ROUND(amount, 2)) AS sum_after_round
FROM amounts;
```

Kết quả PostgreSQL:

| `round_after_sum` | `sum_after_round` |
| ---: | ---: |
| 2.01 | 2.02 |

Giá trị `1.005` được làm tròn thành `1.01` nếu làm tròn từng dòng. Nhưng cộng hai giá trị gốc cho `2.010` rồi mới làm tròn cho `2.01`. Với hóa đơn, thuế và số tiền, cần quy định **làm tròn ở cấp dòng hay cấp tổng**, thay vì thay đổi thứ tự theo cảm giác.

## 11. Ứng dụng thực tế: số lượng, tiền tệ và sai số

### 11.1. Tính số kiện hàng bằng CEILING

Giả sử một bảng dòng giao hàng có `quantity` và `units_per_box`:

```sql
WITH shipments(quantity, units_per_box) AS (
    VALUES (23, 6), (12, 6), (0, 6), (7, 4)
)
SELECT quantity,
       units_per_box,
       CEIL(
           quantity::NUMERIC / NULLIF(units_per_box, 0)
       ) AS required_boxes
FROM shipments;
```

Kết quả `required_boxes` lần lượt là `4`, `2`, `0`, `2`.

`NULLIF(units_per_box, 0)` chuyển mẫu số bằng 0 thành `NULL` để tránh chia cho 0. Tuy nhiên, một sức chứa bằng 0 vốn là dữ liệu không hợp lệ; `NULL` chỉ phản ánh “không tính được”, không tự sửa lỗi đầu vào. Trong ứng dụng thật nên có ràng buộc `units_per_box > 0`.

### 11.2. Làm tròn đơn giá và thành tiền

```sql
WITH line_items(unit_price, quantity) AS (
    VALUES
        (19.995::NUMERIC, 2),
        (12.345::NUMERIC, 3)
)
SELECT unit_price,
       quantity,
       ROUND(unit_price, 2) AS unit_price_rounded,
       ROUND(unit_price * quantity, 2) AS total_rounded
FROM line_items;
```

Ở dòng đầu, làm tròn đơn giá trước cho `20.00` rồi nhân với `2` sẽ cho `40.00`; nhưng lấy `19.995 × 2 = 39.990` rồi làm tròn tổng sẽ cho `39.99`. Cùng dữ liệu nguồn nhưng hai chiến lược cho kết quả khác.

Đừng mặc định phải làm tròn ở từng mức tính toán. Quy tắc nghiệp vụ có thể yêu cầu giữ chính xác ở đơn giá, tính thuế và tổng sau cùng; hãy tuân thủ thời điểm làm tròn đã được định nghĩa.

### 11.3. Kiểm soát sai lệch trong phạm vi cho phép

Ví dụ phát hiện phép đo lệch quá 5% so với mục tiêu **khi mục tiêu khác 0**:

```sql
SELECT sample_id,
       measured,
       target_value,
       ABS(measured - target_value)
           / NULLIF(ABS(target_value), 0) AS relative_error
FROM numeric_functions_lab
WHERE measured IS NOT NULL
  AND target_value IS NOT NULL
  AND target_value <> 0
ORDER BY sample_id;
```

Công thức:

\[
\text{relative\_error}
= \frac{|\text{measured} - \text{target}|}{|\text{target}|}
\]

Dùng `ABS(target_value)` để mẫu số dương kể cả khi mục tiêu âm. Khi mục tiêu bằng 0, **sai số tương đối theo công thức trên không xác định**; không nên thay bằng 0. Có thể dùng một quy tắc sai số tuyệt đối riêng cho trường hợp mục tiêu bằng 0 nếu nghiệp vụ cho phép.

Để lấy những phép đo có sai số tương đối lớn hơn 5%:

```sql
SELECT sample_id, measured, target_value
FROM numeric_functions_lab
WHERE measured IS NOT NULL
  AND target_value IS NOT NULL
  AND ABS(target_value) > 0
  AND ABS(measured - target_value)
          / NULLIF(ABS(target_value), 0) > 0.05
ORDER BY sample_id;
```

Việc thêm `NULLIF` giữ cho biểu thức không chia cho 0 kể cả khi điều kiện hoặc cách thực thi được tổ chức lại. Ngưỡng `0.05` trong ví dụ chỉ mang ý nghĩa minh họa; phải chọn theo đơn vị đo và yêu cầu thực tế.

### 11.4. Làm tròn số ngày hoặc thời lượng theo block

Một hệ thống có thể tính phí theo block 15 phút, trong đó **bất kỳ phần lẻ dương nào cũng tính trọn một block**. Giả sử thời gian là số phút không âm:

```sql
WITH usages(minutes_used) AS (
    VALUES (0), (1), (15), (16), (30), (31)
)
SELECT minutes_used,
       CEIL(minutes_used::NUMERIC / 15) AS billable_blocks
FROM usages
ORDER BY minutes_used;
```

Kết quả `billable_blocks` lần lượt là `0`, `1`, `1`, `2`, `2`, `3`. Nếu chính sách có tối thiểu một block kể cả không sử dụng, công thức sẽ khác; `CEILING` chỉ triển khai phép làm tròn lên theo công thức đã được chọn.

## 12. NULL, kiểu dữ liệu và giá trị ngoài miền

### Hàm số và NULL

Phần lớn hàm toán học thông thường trả `NULL` nếu đối số cần thiết là `NULL`:

```sql
SELECT
    ABS(NULL::NUMERIC) AS absolute_null,
    ROUND(NULL::NUMERIC, 2) AS round_null,
    CEIL(NULL::NUMERIC) AS ceil_null,
    FLOOR(NULL::NUMERIC) AS floor_null;
```

Tất cả trả `NULL`.

Một cột `NULL` không tự động trở thành 0 khi đi vào `ABS` hoặc `ROUND`. Nếu giá trị thiếu phải được thay bằng số mặc định theo nghiệp vụ, có thể viết:

```sql
SELECT sample_id,
       COALESCE(ROUND(measured, 2), 0) AS display_value
FROM numeric_functions_lab
ORDER BY sample_id;
```

Nhưng với hàng 7, cách này khiến giá trị hiển thị bằng `0` dù dữ liệu thực tế **chưa có số đo**. Khi sự phân biệt quan trọng, giữ kết quả `NULL` và trả thêm cột trạng thái là lựa chọn rõ ràng hơn.

### NUMERIC và DOUBLE PRECISION có quy tắc khác nhau

Các ví dụ `ROUND(x,2)` của bài dùng `NUMERIC` vì số thập phân chính xác làm việc dễ dự đoán hơn khi cần số chữ số sau dấu thập phân.

Trong PostgreSQL, hàm `ROUND(double precision)` có biến thể riêng nhưng `ROUND(double precision, integer)` không được cung cấp giống `ROUND(numeric, integer)`. Ví dụ khi cần hai chữ số:

```sql
SELECT ROUND(12.345::NUMERIC, 2) AS exact_numeric_round;

-- Chuyển một giá trị FLOAT sang NUMERIC trước khi dùng tham số thứ hai:
SELECT ROUND(12.345::DOUBLE PRECISION::NUMERIC, 2)
       AS converted_float_round;
```

Phép chuyển từ floating point sang numeric không phục hồi chính xác giá trị thập phân gốc nếu sai số nhị phân đã xuất hiện trước đó. Nếu cần tính toán số tiền chính xác, nên thống nhất kiểu `NUMERIC`/`DECIMAL` cho dữ liệu đầu vào và phép tính liên quan.

Ở đúng điểm giữa giữa hai mức làm tròn, `ROUND(numeric)` của PostgreSQL làm tròn ra xa 0; `ROUND(double precision)` thường theo cách làm tròn của thư viện hệ thống và có thể chọn điểm hòa khác. Khi mã SQL phải chạy trên nhiều môi trường, hãy xác định kiểu đối số và chính sách làm tròn, nhất là ở các giá trị biên.

### Tràn số và miền giá trị

Một số trường hợp cần kiểm tra trước khi gọi hàm hoặc ép kiểu:

- `ABS` trên giá trị nguyên âm nhỏ nhất có thể tràn nếu kết quả vẫn dùng cùng kiểu nguyên.
- `POWER` và `EXP` có thể trả giá trị quá lớn so với kiểu kết quả.
- `SQRT` trên số âm, `LN`/`LOG` trên số không dương không hợp lệ trong miền số thực thường dùng.
- `MOD(a, 0)` và phép chia cho 0 không hợp lệ.
- Giá trị đã làm tròn vẫn có thể vượt phạm vi cột `NUMERIC(p,s)` khi được lưu.

Ví dụ với cột `NUMERIC(5,2)`, số dương lớn nhất thường lưu được là `999.99`. Giá trị `999.995` được làm tròn thành `1000.00` khi ép về scale 2 và vượt phạm vi cột trong PostgreSQL. Để khắc phục, cần xác định giá trị đó có hợp lệ theo nghiệp vụ hay không rồi mới quyết định tăng precision hoặc từ chối đầu vào.

## 13. So sánh hàm số giữa các hệ quản trị SQL

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle Database | SQLite |
| --- | --- | --- | --- | --- | --- |
| Trị tuyệt đối | `ABS(x)` | `ABS(x)` | `ABS(x)` | `ABS(x)` | `ABS(x)` |
| Làm tròn | `ROUND(x,d)` với `NUMERIC` | `ROUND(x,d)` | `ROUND(x,d)` | `ROUND(x,d)` | `ROUND(x,d)` |
| Làm tròn lên | `CEIL(x)` / `CEILING(x)` | `CEIL(x)` / `CEILING(x)` | `CEILING(x)` | `CEIL(x)` | `ceil(x)` / `ceiling(x)` khi có math functions |
| Làm tròn xuống | `FLOOR(x)` | `FLOOR(x)` | `FLOOR(x)` | `FLOOR(x)` | `floor(x)` khi có math functions |
| Cắt chữ số thập phân | `TRUNC(x,d)` với `NUMERIC` | `TRUNCATE(x,d)` | `ROUND(x,d,1)` | `TRUNC(x,d)` | `trunc(x)` có thể có khi bật math functions; cần kiểm tra khả năng theo bản build |
| Phần dư | `MOD(a,b)` hoặc `a % b` | `MOD(a,b)` hoặc `a % b` | `a % b` | `MOD(a,b)` | `a % b` |
| Logarit tự nhiên | `LN(x)` | `LN(x)` | `LOG(x)` | `LN(x)` | `ln(x)` khi có math functions |
| Logarit cơ số 10 | `LOG(x)` | `LOG10(x)` | `LOG10(x)` | `LOG(10,x)` hoặc `LOG(10, x)` theo phiên bản/cú pháp | `log10(x)` hoặc `log(x)` khi có math functions |

Bảng nhằm giúp nhận biết **không thể chuyển nguyên tên hàm và tham số giữa mọi hệ quản trị**. Chi tiết còn phụ thuộc phiên bản, kiểu dữ liệu, cấu hình SQL và cách cài đặt các hàm mở rộng.

Một vài điểm đặc biệt cần nhớ:

- **PostgreSQL** có cả `CEIL` và `CEILING`; `ROUND(numeric,d)` dùng thập phân chính xác và làm tròn các trường hợp đúng giữa hai mức ra xa 0.
- **MySQL** hỗ trợ `ROUND`, `TRUNCATE` và `CEIL`; hành vi làm tròn có thể phụ thuộc kiểu số chính xác hay gần đúng.
- **SQL Server** dùng tên `CEILING` và có cú pháp `ROUND(value, decimals, 1)` cho thao tác cắt thay vì làm tròn theo mặc định. `LOG` một đối số biểu thị logarit tự nhiên.
- **Oracle** sử dụng `CEIL` và `TRUNC` cho số; cần phân biệt `TRUNC(number)` với biến thể `TRUNC(date)` khi đối số là ngày.
- **SQLite** có typing động. Các hàm toán học bổ sung như `ceil`, `floor`, `ln` và `log` phụ thuộc việc thư viện SQLite được biên dịch với khả năng math functions; không phải mọi bản build đều có chúng. `ROUND` của SQLite xử lý số theo cơ chế khác kiểu `NUMERIC` chính xác của PostgreSQL.

Một điểm khác biệt không nằm ở tên hàm: **chia số nguyên**. Ví dụ PostgreSQL `23 / 6` cho `3`, vì thế kết hợp với `CEIL` sau đó không thể tự tạo `4`. Cần ép kiểu trước phép chia hoặc thiết kế công thức chia nguyên thích hợp theo DBMS.

## 14. Chẩn đoán những lỗi tính toán thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `CEILING(23 / 6)` trả 3, mong 4 | Phép chia nguyên đã bỏ phần thập phân | Ép một toán hạng sang `NUMERIC` trước phép chia |
| `FLOOR(-2.1)` trả -3, mong -2 | `FLOOR` đi về âm vô cực, không phải cắt phần lẻ | Dùng `TRUNC` nếu yêu cầu là đi về 0 |
| `ROUND(-2.5::NUMERIC)` trả -3 | PostgreSQL `NUMERIC` làm tròn giá trị hòa ra xa 0 | Chọn đúng kiểu và xác nhận quy tắc rounding nghiệp vụ |
| `ROUND(double precision, 2)` không chạy PostgreSQL | Không có overload hai đối số tương ứng cho `double precision` | Chuyển sang `NUMERIC` khi phù hợp; hiểu giới hạn sai số đã có |
| `ABS` báo overflow với số nguyên rất âm | Trị tuyệt đối vượt giới hạn kiểu nguyên | Nâng kiểu toán hạng trước khi gọi `ABS` |
| `SQRT(x)` hoặc `LN(x)` báo lỗi | Giá trị ngoài miền định nghĩa | Kiểm tra đầu vào và định nghĩa cách xử lý |
| Tỷ lệ `NULL` sau `NULLIF` | Mẫu số bằng 0 hoặc đầu vào khác bị thiếu | Xác định lý do, không mặc định `NULL = 0` |
| Tổng tiền lệch một cent | Làm tròn từng dòng khác làm tròn tổng cuối | Quy định chính sách làm tròn và áp dụng nhất quán |
| `MOD(a,0)` báo lỗi | Mẫu số của phép dư bằng 0 | Kiểm tra điều kiện hoặc dùng `NULLIF` nếu `NULL` phù hợp |
| Kết quả logarit khác hệ cũ | `LOG` có thể là cơ số khác giữa DBMS | Chọn đúng `LN`, `LOG`, `LOG10` theo hệ |
| Câu SQL chạy khác nhau trên PostgreSQL và SQLite | SQLite có typing động và khả năng math functions tùy bản build | Kiểm tra kiểu và hàm có sẵn tại môi trường thực thi |

## 15. Bài tập thực hành

Dùng bảng tạm `numeric_functions_lab` của mục 2 để luyện tập trong PostgreSQL. Hãy dự đoán kết quả trước khi chạy.

### Bài 1. Trị tuyệt đối

Viết truy vấn trả `sample_id`, `measured`, `target_value` và `absolute_difference = ABS(measured - target_value)`. Lọc những hàng có sai lệch tuyệt đối **không vượt quá 2**, sắp xếp theo `sample_id`.

Câu hỏi: hàng có `measured IS NULL` có được trả về không? Vì sao?

### Bài 2. Làm tròn đến các mức khác nhau

Với mỗi hàng, tạo ba cột:

- `rounded_2`: `ROUND(measured,2)`.
- `rounded_0`: `ROUND(measured,0)`.
- `rounded_tens`: `ROUND(measured,-1)`.

Dự đoán kết quả cho `measured = -12.3450` và `1234.5670`.

### Bài 3. Phân biệt CEILING, FLOOR và TRUNC

Dùng các số `2.9`, `-2.9`, `0.1`, `-0.1` và so sánh:

```sql
SELECT
    value,
    CEIL(value) AS ceiling_value,
    FLOOR(value) AS floor_value,
    TRUNC(value) AS truncated_value
FROM (
    VALUES
        (2.9::NUMERIC),
        (-2.9::NUMERIC),
        (0.1::NUMERIC),
        (-0.1::NUMERIC)
) AS v(value);
```

Giải thích tại sao ba hàm không thể thay thế lẫn nhau cho số âm.

### Bài 4. Tính số hộp cần đóng

Mỗi hộp chứa 8 sản phẩm. Tính số hộp cho số lượng `0`, `1`, `8`, `9`, `17`. Chọn hàm phù hợp và bảo đảm phép chia không bị cắt phần lẻ trước.

### Bài 5. Kiểm tra chẵn/lẻ

Viết truy vấn lấy `sample_id` và cột `number_group` có giá trị `'even'` nếu `sample_id` chẵn, `'odd'` nếu lẻ. Dùng `MOD`.

### Bài 6. Làm tròn ở cấp dòng và cấp tổng

Với hai giá trị `1.005` và `1.005`:

1. Tính `ROUND(SUM(amount), 2)`.
2. Tính `SUM(ROUND(amount,2))`.
3. Giải thích vì sao kết quả khác nhau dù đầu vào giống hệt.

### Bài 7. Dấu của sai lệch

Dùng `SIGN(measured - target_value)` để tạo cột `direction`. Sau đó tạo cột nhãn bằng `CASE`: `'below'`, `'equal'`, `'above'` hoặc `'unknown'` nếu thiếu dữ liệu.

### Bài 8. Căn bậc hai và logarit

Tính:

```sql
SELECT SQRT(49::NUMERIC),
       POWER(3::NUMERIC, 4),
       LOG(1000::NUMERIC),
       LN(1::NUMERIC);
```

Chỉ ra hàm nào cần đối số dương (hoặc không âm) trong miền số thực.

### Bài 9. Tạo mức giá theo bội số

Một mức giá `123` cần được quy đổi về:

- Bội số **50 gần nhất ở phía trên**.
- Bội số **50 gần nhất ở phía dưới**.

Viết hai biểu thức dùng `CEIL` và `FLOOR`. Sau đó thử với `100` để kiểm tra giá trị vốn đã là bội số không bị tăng/giảm sai.

### Bài 10. Kiểu số và sai số

Giải thích hai khác biệt:

1. `CEIL(23 / 6)` và `CEIL(23::NUMERIC / 6)` trong PostgreSQL.
2. `ROUND(1.245::NUMERIC, 2)` và việc làm tròn một giá trị lưu bằng số dấu phẩy động nhị phân.

Với dữ liệu tiền tệ, bạn sẽ chọn kiểu nào và quy định gì về thời điểm làm tròn?

## 16. Gợi ý lời giải

### Bài 1

```sql
SELECT sample_id,
       measured,
       target_value,
       ABS(measured - target_value) AS absolute_difference
FROM numeric_functions_lab
WHERE ABS(measured - target_value) <= 2
ORDER BY sample_id;
```

Kết quả gồm các `sample_id` **2, 3, 4, 6**. `NULL` không thỏa điều kiện `<= 2` vì kết quả so sánh là UNKNOWN.

### Bài 2

```sql
SELECT sample_id,
       measured,
       ROUND(measured, 2) AS rounded_2,
       ROUND(measured, 0) AS rounded_0,
       ROUND(measured, -1) AS rounded_tens
FROM numeric_functions_lab
ORDER BY sample_id;
```

Với `-12.3450`: kết quả `-12.35`, `-12`, `-10`. Với `1234.5670`: kết quả `1234.57`, `1235`, `1230`.

### Bài 3

`CEILING(2.9) = 3`, `FLOOR(2.9) = 2`, `TRUNC(2.9) = 2`. Với `-2.9`: `CEILING = -2`, `FLOOR = -3`, `TRUNC = -2`. Với `0.1`: `CEILING = 1`, `FLOOR = 0`, `TRUNC = 0`. Với `-0.1`: `CEILING = 0`, `FLOOR = -1`, `TRUNC = 0`.

### Bài 4

```sql
WITH quantities(quantity) AS (
    VALUES (0), (1), (8), (9), (17)
)
SELECT quantity,
       CEILING(quantity::NUMERIC / 8) AS boxes
FROM quantities
ORDER BY quantity;
```

Kết quả số hộp: `0, 1, 1, 2, 3`.

### Bài 5

```sql
SELECT sample_id,
       CASE
           WHEN MOD(sample_id, 2) = 0 THEN 'even'
           ELSE 'odd'
       END AS number_group
FROM numeric_functions_lab
ORDER BY sample_id;
```

### Bài 6

```sql
WITH amounts(amount) AS (
    VALUES (1.005::NUMERIC), (1.005::NUMERIC)
)
SELECT ROUND(SUM(amount), 2) AS round_after_sum,
       SUM(ROUND(amount, 2)) AS sum_after_round
FROM amounts;
```

Kết quả `2.01` và `2.02`. Lựa chọn nào phù hợp phụ thuộc chính sách làm tròn của nghiệp vụ.

### Bài 7

```sql
SELECT sample_id,
       SIGN(measured - target_value) AS direction,
       CASE
           WHEN measured IS NULL OR target_value IS NULL
               THEN 'unknown'
           WHEN measured < target_value THEN 'below'
           WHEN measured > target_value THEN 'above'
           ELSE 'equal'
       END AS direction_label
FROM numeric_functions_lab
ORDER BY sample_id;
```

### Bài 8

Kết quả là `7`, `81`, `3`, `0`. `SQRT` cần đầu vào **không âm** cho căn bậc hai thực; `LN` và `LOG` cần đầu vào **dương**. `POWER` có điều kiện miền riêng với cơ số âm và số mũ không nguyên, cùng nguy cơ tràn cho giá trị rất lớn.

### Bài 9

```sql
SELECT CEIL(123::NUMERIC / 50) * 50 AS upper_multiple,
       FLOOR(123::NUMERIC / 50) * 50 AS lower_multiple;
```

Kết quả `150` và `100`. Nếu thay `123` bằng `100`, cả hai đều trả `100`.

### Bài 10

`23 / 6` trong PostgreSQL dùng phép chia nguyên cho `3`; `CEIL(3)` vẫn là `3`. `23::NUMERIC / 6` giữ phần thập phân nên `CEIL` trả `4`. `NUMERIC` là lựa chọn phù hợp khi cần biểu diễn decimal chính xác và quy định số chữ số/kiểu làm tròn; số floating point nhị phân có thể mang sai số xấp xỉ. Với tiền tệ cần thêm quy tắc **làm tròn lúc nào, đến bao nhiêu chữ số và xử lý điểm hòa như thế nào**.

Khi chọn một hàm số trong SQL, hãy xác định **ý nghĩa của kết quả trước**: cần khoảng cách tuyệt đối, số gần nhất, mức tối thiểu phía trên, mức tối đa phía dưới, hay chỉ cắt chữ số? Tiếp theo kiểm tra **kiểu dữ liệu, giá trị NULL, dấu âm, miền hợp lệ và thứ tự các phép toán**. Chính những chi tiết này quyết định việc biểu thức cho kết quả đúng trong dữ liệu thật, không chỉ trong ví dụ có số dương đơn giản.
