# Hàm số học, làm tròn và xử lý sai số trong PostgreSQL

Trong hệ quản trị cơ sở dữ liệu, phép tính không chỉ là cộng, trừ, nhân, chia. Một cột có kiểu `INTEGER`, `NUMERIC` hay `DOUBLE PRECISION` có thể làm cùng một biểu thức cho kết quả khác nhau về **kiểu dữ liệu, phần thập phân, độ chính xác và cách làm tròn**.

Ví dụ, phép chia `7 / 2` giữa hai số nguyên trong PostgreSQL cho kết quả `3`, trong khi `7::NUMERIC / 2` cho `3.5`. Giá trị `12.345` khi chuyển vào `NUMERIC(8,2)` thường được làm tròn thành `12.35`. Một phép tính với `DOUBLE PRECISION` có thể sinh sai số biểu diễn nhị phân dù người dùng nhìn thấy hai con số thập phân có vẻ rất đơn giản. Chia cho 0 có thể làm cả câu SQL lỗi; cast sau khi đã nhân hai `INTEGER` không thể cứu một phép nhân đã bị tràn số.

Vì vậy, khi viết truy vấn phân tích, xử lý đơn hàng, tính thuế, tổng hợp chỉ số hoặc tính phần trăm, người học PostgreSQL cần hiểu đồng thời:

1. **Toán tử và hàm số học làm gì?**
2. **Kiểu dữ liệu quyết định kết quả như thế nào?**
3. **Rounding/truncation xảy ra ở bước nào?**
4. **Khi nào cần xử lý lỗi và giá trị không xác định?**
5. **Làm sao bảo đảm kết quả phù hợp với ngữ nghĩa nghiệp vụ?**

Bài học trình bày các toán tử `+`, `-`, `*`, `/`, `%`, các hàm `ABS`, `SIGN`, `ROUND`, `TRUNC`, `FLOOR`, `CEIL`, `MOD`, `POWER`, `SQRT`, phân biệt tính toán thập phân chính xác với dấu phẩy động nhị phân, cùng kỹ thuật xử lý chia cho 0, tràn số, `NULL` và sai số cộng dồn.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Sử dụng toán tử số học và xác định **thứ tự ưu tiên** bằng dấu ngoặc.
- Phân biệt phép chia nguyên và phép chia có phần thập phân; biết **cast trước khi tính** khi cần.
- Chọn `NUMERIC/DECIMAL`, `INTEGER/BIGINT` hay `REAL/DOUBLE PRECISION` theo yêu cầu độ chính xác.
- Dùng các hàm trị tuyệt đối, dấu, làm tròn, cắt phần lẻ, chia lấy dư, lũy thừa và căn bậc hai.
- Phân biệt **round**, **trunc**, **floor** và **ceil**, đặc biệt với số âm.
- Giải thích hành vi khi giá trị nằm chính giữa hai mức làm tròn và khác biệt giữa `NUMERIC` với floating point.
- Hiểu `NUMERIC(p,s)` giới hạn số chữ số và có thể làm tròn khi gán vào cột.
- Nhận diện sai số nhị phân, so sánh số thực gần bằng nhau và giới hạn của epsilon.
- Xử lý `division_by_zero`, overflow, giá trị đầu vào sai, `NULL` và giá trị đặc biệt theo cách tường minh.
- Tính phần trăm, đơn giá, số lượng, thuế và tổng tiền mà không làm tròn quá sớm.
- Sử dụng `SUM`, `AVG` và các phép tổng hợp phù hợp với kiểu đầu vào.
- Viết và kiểm chứng các truy vấn thực hành trên PostgreSQL.

Các ví dụ dùng cú pháp PostgreSQL hiện đại. Phần tạo/xóa bảng chỉ dành cho **database thực hành**, không chạy trực tiếp trên môi trường chứa dữ liệu cần giữ.

## 2. Bức tranh tổng thể: kiểu số là một phần của phép toán

PostgreSQL có nhiều kiểu số với đặc tính khác nhau:

| Kiểu | Đặc tính | Tình huống phù hợp | Cần lưu ý |
| --- | --- | --- | --- |
| `SMALLINT` | Số nguyên 2 byte | Bộ đếm nhỏ, trạng thái số | Miền hẹp |
| `INTEGER` / `INT` | Số nguyên 4 byte | Số lượng, mã số, bộ đếm vừa | Chia nguyên; overflow |
| `BIGINT` | Số nguyên 8 byte | Số lượng lớn, đơn vị tiền nhỏ nhất | Vẫn có giới hạn |
| `NUMERIC(p,s)` / `DECIMAL(p,s)` | Số thập phân có độ chính xác được kiểm soát | Tiền, đo lường cần decimal, tỷ lệ | Chi phí tính toán, scale, rounding |
| `NUMERIC` | Số decimal không bị ràng buộc bởi `p,s` cụ thể trong định nghĩa cột | Phép tính trung gian cần nhiều chữ số | Không thay validation miền giá trị |
| `REAL` | Floating point nhị phân 4 byte | Dữ liệu đo/ước lượng có chấp nhận sai số | Khoảng 6 chữ số thập phân có nghĩa |
| `DOUBLE PRECISION` | Floating point nhị phân 8 byte | Thống kê, khoa học, số học gần đúng | Khoảng 15 chữ số thập phân có nghĩa |
| `MONEY` | Kiểu tiền chuyên biệt, định dạng phụ thuộc locale | Một số hệ thống cũ/đặc thù | Không tự lưu currency; không linh hoạt bằng numeric cho nhiều trường hợp |

Độ chính xác có **hai nghĩa cần phân biệt**:

- **Precision của kiểu dữ liệu:** một giá trị có thể được biểu diễn với bao nhiêu chữ số và quy tắc nào.
- **Độ đúng của kết quả nghiệp vụ:** công thức, đơn vị, làm tròn và dữ liệu đầu vào có phù hợp yêu cầu hay không.

Một phép tính bằng `NUMERIC` có thể chính xác theo số học thập phân nhưng **vẫn sai nghiệp vụ** nếu dùng sai tỷ giá, cộng hai đồng tiền khác nhau hoặc làm tròn đơn giá trước khi nhân số lượng.

### 2.1. Exact và approximate

`NUMERIC` biểu diễn chính xác nhiều giá trị thập phân hữu hạn như `0.1`, `0.01` và `12.345` trong phạm vi kiểu, còn floating point nhị phân không thể biểu diễn chính xác mọi phân số thập phân đó.

Ví dụ:

```sql
SELECT
    0.1::NUMERIC + 0.2::NUMERIC AS decimal_sum,
    0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION
        AS floating_sum;
```

Cả hai đều gần với `0.3` khi hiển thị, nhưng trong số thực nhị phân, sai số biểu diễn có thể khiến phép kiểm tra bằng nhau tuyệt đối thất bại.

Điều này không có nghĩa `NUMERIC` có độ chính xác vô hạn trong mọi phép tính. Phép chia `1/3` có biểu diễn thập phân vô hạn; PostgreSQL vẫn phải đưa ra một kết quả hữu hạn theo cơ chế tính decimal của nó.

---

## 3. Chuẩn bị database thực hành

Để chạy các ví dụ mà không ảnh hưởng dữ liệu thật, tạo schema riêng:

> **Cảnh báo:** Các lệnh `DROP TABLE IF EXISTS` ở phần thực hành sẽ xóa dữ liệu cũ trong những bảng có tên tương ứng của schema `arithmetic_lab`. Chỉ chạy trong một database test được phép reset.

```sql
CREATE SCHEMA IF NOT EXISTS arithmetic_lab;

DROP TABLE IF EXISTS arithmetic_lab.order_lines;
DROP TABLE IF EXISTS arithmetic_lab.sensor_readings;

CREATE TABLE arithmetic_lab.order_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL,
    quantity NUMERIC(12,3) NOT NULL
        CHECK (quantity > 0),
    unit_price NUMERIC(16,4) NOT NULL
        CHECK (unit_price >= 0),
    discount_rate NUMERIC(7,5) NOT NULL DEFAULT 0
        CHECK (discount_rate BETWEEN 0 AND 1),
    line_gross NUMERIC(20,4)
        GENERATED ALWAYS AS (
            quantity * unit_price
        ) STORED
);

CREATE TABLE arithmetic_lab.sensor_readings (
    reading_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_code TEXT NOT NULL,
    reading_value DOUBLE PRECISION,
    expected_value DOUBLE PRECISION,
    measured_at TIMESTAMPTZ NOT NULL
);
```

Dùng `NUMERIC` cho các trường tính tiền và `DOUBLE PRECISION` cho dữ liệu đo lường minh họa.

Thêm dữ liệu:

```sql
INSERT INTO arithmetic_lab.order_lines (
    sku, quantity, unit_price, discount_rate
)
VALUES
    ('ITEM-A',   2.000,  19.9900, 0.00000),
    ('ITEM-B',   1.500,   4.2000, 0.10000),
    ('ITEM-C', 100.000,   0.0150, 0.00000),
    ('ITEM-D',   3.000,  12.3450, 0.07500),
    ('ITEM-E',   1.000, 100.0000, 0.15000);

INSERT INTO arithmetic_lab.sensor_readings (
    sensor_code, reading_value, expected_value, measured_at
)
VALUES
    ('TEMP-A', 23.5,     23.5, '2026-11-01 09:00:00+00'),
    ('TEMP-A', 23.50001, 23.5, '2026-11-01 09:01:00+00'),
    ('TEMP-B',  0.1,      0.1, '2026-11-01 09:02:00+00'),
    ('TEMP-B', NULL,     10.0, '2026-11-01 09:03:00+00');
```

Kiểm tra dữ liệu:

```sql
SELECT
    line_id, sku, quantity, unit_price,
    discount_rate, line_gross
FROM arithmetic_lab.order_lines
ORDER BY line_id;

SELECT *
FROM arithmetic_lab.sensor_readings
ORDER BY reading_id;
```

Giá trị `line_gross` được hệ thống tính từ `quantity * unit_price`. Nó là số tiền **trước chiết khấu**, giữ bốn chữ số phần lẻ theo định nghĩa cột. Đây là dữ liệu minh họa, không phải một hệ thống hóa đơn đầy đủ.

---

## 4. Toán tử số học cơ bản

Các toán tử thường dùng:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `+` | Cộng | `5 + 3` |
| `-` | Trừ | `5 - 3` |
| `*` | Nhân | `5 * 3` |
| `/` | Chia | `10 / 4` |
| `%` | Chia lấy dư | `10 % 4` |
| `^` | Lũy thừa trong PostgreSQL | `2 ^ 3` |
| `+x` | Dấu dương một ngôi | `+5` |
| `-x` | Đổi dấu | `-5` |

Thử một câu SQL:

```sql
SELECT
    12 + 5 AS added,
    12 - 5 AS subtracted,
    12 * 5 AS multiplied,
    12 / 5 AS integer_quotient,
    12 % 5 AS remainder,
    2 ^ 3 AS power_result;
```

Với hai số nguyên `12` và `5`, phần thương `12 / 5` là **2**, không phải 2.4. Phép chia dư `12 % 5` là **2**.

### 4.1. Dấu ngoặc và thứ tự ưu tiên

Cách viết không rõ ràng:

```sql
SELECT 10 + 2 * 3 AS result;
```

Kết quả là **16**, vì phép nhân có ưu tiên cao hơn phép cộng.

Dấu ngoặc thay đổi phép tính:

```sql
SELECT (10 + 2) * 3 AS result;
```

Kết quả **36**.

Khi công thức có phần trăm, phí, thuế hoặc nhiều nhánh, luôn dùng dấu ngoặc để diễn đạt ý định:

```sql
SELECT
    (100::NUMERIC - 15::NUMERIC)
      * (1::NUMERIC + 0.08::NUMERIC)
        AS net_plus_tax;
```

Trong ví dụ: giá sau giảm là 85 và sau tính thuế giả định 8% là 91.8.

Không dùng suy đoán về độ ưu tiên của toán tử để quyết định kết quả trong công thức có giá trị nghiệp vụ quan trọng.

### 4.2. Phép trừ và số âm

```sql
SELECT
    -7 + 2 AS a,
    -7 - 2 AS b,
    -7 * 2 AS c;
```

Kết quả lần lượt: -5, -9, -14.

Việc một công thức cho kết quả âm không có nghĩa PostgreSQL sai. Có cho phép số âm hay không là **ràng buộc của từng trường dữ liệu**: lợi nhuận có thể âm, giá niêm yết thường không âm, bút toán điều chỉnh có thể mang dấu âm.

---

## 5. Phép chia nguyên: bẫy kinh điển

Trong PostgreSQL, phép chia hai toán hạng kiểu số nguyên trả thương số nguyên và **bỏ phần lẻ theo hướng về 0**.

```sql
SELECT
    7 / 2 AS int_division,
    -7 / 2 AS negative_int_division,
    7::NUMERIC / 2 AS decimal_division,
    7 / 2::NUMERIC AS cast_right_operand;
```

Kết quả theo ý nghĩa:

| Biểu thức | Kết quả |
| --- | ---: |
| `7 / 2` | 3 |
| `-7 / 2` | -3 |
| `7::NUMERIC / 2` | 3.5 |
| `7 / 2::NUMERIC` | 3.5 |

**-7 / 2 = -3** chứ không phải -4, vì chia nguyên cắt phần thập phân theo hướng về 0. Điều đó khác với hàm `FLOOR(-3.5)`, vốn cho -4.

### 5.1. Cast trước, không phải sau

Hai biểu thức rất khác nhau:

```sql
SELECT
    (7 / 2)::NUMERIC AS cast_after_division,
    7::NUMERIC / 2 AS cast_before_division;
```

Kết quả:

- `(7 / 2)::NUMERIC` → **3**; phần lẻ đã mất trước khi cast.
- `7::NUMERIC / 2` → **3.5**; một toán hạng đã chuyển sang kiểu decimal trước phép chia.

Tương tự:

```sql
SELECT
    100 * (3 / 4) AS wrong_fraction,
    100::NUMERIC * 3 / 4 AS correct_fraction;
```

Kết quả là 0 so với 75, vì `3 / 4` là 0 trong phép chia nguyên.

### 5.2. Phần trăm có thể thành 0 vì chia nguyên

Ví dụ tỷ lệ 3 đơn thành công trên 10 đơn:

```sql
SELECT
    3 / 10 * 100 AS wrong_percent,
    3::NUMERIC / 10 * 100 AS correct_percent;
```

Kết quả:

- Cách đầu: **0**.
- Cách sau: **30**.

Một lỗi phân tích phổ biến là tính:

```sql
COUNT(*) / total_count
```

khi cả hai toán hạng là số nguyên. Khi cần tỷ lệ có phần thập phân, chuyển sang `NUMERIC` hoặc kiểu thích hợp trước phép chia.

### 5.3. Decimal literal cũng ảnh hưởng kiểu

```sql
SELECT
    7 / 2 AS integer_case,
    7.0 / 2 AS decimal_literal_case,
    7::DOUBLE PRECISION / 2 AS float_case;
```

Trong PostgreSQL, literal có dấu thập phân như `7.0` thường được hiểu theo kiểu `numeric` khi không có ngữ cảnh ép kiểu khác; nó không nhất thiết là `double precision`. Để chủ động chọn kiểu, hãy cast rõ `::NUMERIC` hoặc `::DOUBLE PRECISION`.

Không dùng kiểu do parser ngầm suy ra như một phần không được kiểm soát của công thức quan trọng.

---

## 6. Chia lấy dư: %, MOD và DIV

**Phần dư** hữu ích khi kiểm tra tính chẵn lẻ, phân nhóm chu kỳ hoặc xác định vị trí trong một vòng lặp.

```sql
SELECT
    10 % 3 AS remainder_operator,
    MOD(10, 3) AS remainder_function,
    10 / 3 AS integer_quotient;
```

Kết quả: phần dư 1, thương nguyên 3.

### 6.1. Phần dư với số âm

```sql
SELECT
    MOD(7, 3) AS positive_case,
    MOD(-7, 3) AS negative_dividend,
    MOD(7, -3) AS negative_divisor;
```

Theo quy tắc phần dư gắn với phép chia làm tròn về 0 của số nguyên PostgreSQL:

- `MOD(7,3)` → 1.
- `MOD(-7,3)` → -1.
- `MOD(7,-3)` → 1.

Không tự coi `MOD` luôn trả số trong khoảng `0..m-1` khi có giá trị âm. Nếu thuật toán cần phần dư không âm cho số chia dương `m`, có thể định nghĩa chuẩn hóa có chủ đích như:

```sql
SELECT
    MOD(MOD(-7, 3) + 3, 3) AS nonnegative_modulo;
```

Kết quả là 2. Công thức đó chỉ minh họa cho **m = 3 dương**; cần xác thực `m > 0` trong bài toán tổng quát.

### 6.2. Hàm DIV

PostgreSQL còn hỗ trợ `DIV(y, x)` cho phép lấy thương số nguyên trong những ngữ cảnh numeric:

```sql
SELECT
    DIV(7::NUMERIC, 2::NUMERIC) AS quotient_positive,
    DIV((-7)::NUMERIC, 2::NUMERIC) AS quotient_negative;
```

Kết quả có ý nghĩa thương bị cắt phần lẻ: 3 và -3.

`DIV` không phải công cụ thay thế phép chia decimal; nếu cần 3.5, dùng `7::NUMERIC / 2`.

### 6.3. Không gọi MOD khi số chia bằng 0

```sql
-- Câu này được dùng để quan sát lỗi, không chạy trong transaction cần giữ.
SELECT MOD(10, 0);
```

PostgreSQL báo lỗi chia cho 0. Cách xử lý chia cho 0 được trình bày riêng ở phần sau.

---

## 7. ABS, SIGN: trị tuyệt đối và dấu

### 7.1. ABS

`ABS(x)` trả trị tuyệt đối, tức độ lớn không âm của một số:

```sql
SELECT
    ABS(-12) AS abs_negative,
    ABS(12) AS abs_positive,
    ABS(0) AS abs_zero,
    ABS(-12.345::NUMERIC) AS abs_decimal;
```

Kết quả lần lượt: 12, 12, 0, 12.345.

Ứng dụng:

- Đo độ lệch tuyệt đối giữa giá trị thực tế và giá trị kỳ vọng.
- Đếm/tổng hợp mức sai khác không phụ thuộc dấu.
- Kiểm tra một giá trị có nằm trong khoảng dung sai hay không.

Ví dụ:

```sql
SELECT
    ABS(100.12::NUMERIC - 100.00::NUMERIC)
        AS absolute_difference;
```

Kết quả 0.12.

**Lưu ý:** nếu dùng kiểu số nguyên ở biên cực tiểu của miền biểu diễn, trị tuyệt đối có thể không vừa trong cùng kiểu nguyên. Chẳng hạn trị tuyệt đối của giá trị nhỏ nhất của `BIGINT` vượt quá giá trị dương lớn nhất của `BIGINT`.

Vì vậy, với trường hợp có thể chạm biên, chuyển sang `NUMERIC` trước khi tính:

```sql
SELECT ABS((-9223372036854775808)::NUMERIC)
    AS safe_big_abs;
```

### 7.2. SIGN

`SIGN(x)` trả dấu của số:

- -1 nếu `x < 0`.
- 0 nếu `x = 0`.
- 1 nếu `x > 0`.

```sql
SELECT
    SIGN(-15::NUMERIC) AS negative_sign,
    SIGN(0::NUMERIC) AS zero_sign,
    SIGN(15::NUMERIC) AS positive_sign;
```

Trong nghiệp vụ, có thể dùng SIGN để phân loại chênh lệch tăng/giảm:

```sql
SELECT
    SIGN(95::NUMERIC - 100::NUMERIC) AS movement_direction;
```

Kết quả -1. Nhưng đừng dùng SIGN thay việc lưu nguyên chênh lệch nếu cần biết **độ lớn** của thay đổi.

### 7.3. ABS không phải kiểm tra gần bằng nhau tuyệt đối cho mọi trường hợp

Với floating point, một phép kiểm tra như:

```sql
ABS(a - b) < 0.000001
```

chỉ có ý nghĩa nếu bạn đã chọn tolerance hợp lý theo **đơn vị và thang đo**. Sai số 0.000001 có thể rất nhỏ đối với dữ liệu đo bằng hàng triệu đơn vị nhưng quá lớn cho phép đo cực nhỏ.

Phần sau sẽ trình bày cách so sánh số thực theo cả dung sai tuyệt đối và tương đối.

---

## 8. ROUND, TRUNC, FLOOR, CEIL: bốn thao tác khác nhau

Đây là nhóm hàm cần nắm vững vì chúng thường được dùng trong tiền, báo cáo, điểm số, tỷ lệ và đo lường.

| Hàm | Cách xử lý | Ví dụ số dương | Ví dụ số âm |
| --- | --- | --- | --- |
| `ROUND(x)` | Làm tròn về số nguyên gần nhất theo quy tắc kiểu dữ liệu | `ROUND(2.7::NUMERIC) = 3` | `ROUND(-2.7::NUMERIC) = -3` |
| `TRUNC(x)` | Cắt phần thập phân, về phía 0 | `TRUNC(2.7::NUMERIC) = 2` | `TRUNC(-2.7::NUMERIC) = -2` |
| `FLOOR(x)` | Số nguyên lớn nhất không vượt x | `FLOOR(2.7) = 2` | `FLOOR(-2.7) = -3` |
| `CEIL(x)` / `CEILING(x)` | Số nguyên nhỏ nhất không nhỏ hơn x | `CEIL(2.7) = 3` | `CEIL(-2.7) = -2` |

### 8.1. Thực hành số dương và số âm

```sql
SELECT
    ROUND( 3.7::NUMERIC) AS round_positive,
    TRUNC( 3.7::NUMERIC) AS trunc_positive,
    FLOOR( 3.7::NUMERIC) AS floor_positive,
    CEIL(  3.7::NUMERIC) AS ceil_positive,

    ROUND(-3.7::NUMERIC) AS round_negative,
    TRUNC(-3.7::NUMERIC) AS trunc_negative,
    FLOOR(-3.7::NUMERIC) AS floor_negative,
    CEIL( -3.7::NUMERIC) AS ceil_negative;
```

Kết quả:

| Giá trị | ROUND | TRUNC | FLOOR | CEIL |
| ---: | ---: | ---: | ---: | ---: |
| 3.7 | 4 | 3 | 3 | 4 |
| -3.7 | -4 | -3 | -4 | -3 |

**Điểm phân biệt quyết định:** `TRUNC(-3.7)` là -3, còn `FLOOR(-3.7)` là -4.

### 8.2. Khi nào dùng FLOOR/CEIL?

Ví dụ một kho vận có tổng trọng lượng 25.1 kg và chỉ vận chuyển theo **thùng 10 kg**. Nếu nghiệp vụ yêu cầu làm tròn lên số thùng:

```sql
SELECT
    CEIL(25.1::NUMERIC / 10::NUMERIC)
        AS required_box_count;
```

Kết quả 3.

Nếu chỉ tính số thùng đầy:

```sql
SELECT
    FLOOR(25.1::NUMERIC / 10::NUMERIC)
        AS full_box_count;
```

Kết quả 2.

Hai hàm đúng cho **hai câu hỏi khác nhau**. Không thể chỉ hỏi “phải làm tròn bằng hàm nào?” nếu chưa xác định quy tắc nghiệp vụ.

### 8.3. TRUNC không có nghĩa dữ liệu đã được xác thực

```sql
SELECT
    TRUNC(19.999::NUMERIC, 2) AS truncated_money,
    ROUND(19.999::NUMERIC, 2) AS rounded_money;
```

Kết quả lần lượt 19.99 và 20.00.

Nếu API bắt buộc khách hàng chỉ gửi tối đa hai chữ số lẻ, cả hai phép biến đổi này đều có thể **che giấu lỗi đầu vào**. Khi đó, quy trình đúng là kiểm tra input trước, rồi từ chối `19.999` thay vì lặng lẽ chuyển nó thành một giá trị khác.

---

## 9. ROUND với tham số thứ hai: độ rộng làm tròn

PostgreSQL hỗ trợ:

```sql
ROUND(value::NUMERIC, decimal_places)
```

Trong đó `decimal_places` xác định số chữ số phần thập phân được giữ.

```sql
SELECT
    ROUND(12.34567::NUMERIC, 0) AS zero_places,
    ROUND(12.34567::NUMERIC, 1) AS one_place,
    ROUND(12.34567::NUMERIC, 2) AS two_places,
    ROUND(12.34567::NUMERIC, 4) AS four_places;
```

Kết quả theo số học:

| Scale yêu cầu | Kết quả |
| ---: | ---: |
| 0 | 12 |
| 1 | 12.3 |
| 2 | 12.35 |
| 4 | 12.3457 |

### 9.1. Scale âm: làm tròn phần nguyên

Tham số thứ hai có thể âm, nghĩa là làm tròn về hàng chục, trăm hoặc nghìn.

```sql
SELECT
    ROUND(12345.678::NUMERIC, -1) AS nearest_ten,
    ROUND(12345.678::NUMERIC, -2) AS nearest_hundred,
    ROUND(12345.678::NUMERIC, -3) AS nearest_thousand;
```

Kết quả:

- Hàng chục: 12350.
- Hàng trăm: 12300.
- Hàng nghìn: 12000.

Tham số scale âm của **hàm ROUND** khác với cách khai báo scale ở cột `NUMERIC(p,s)`, mặc dù PostgreSQL hiện đại cũng có những khả năng mở rộng scale trong định nghĩa type.

### 9.2. TRUNC cũng có thể nhận số chữ số

```sql
SELECT
    TRUNC(123.4567::NUMERIC, 2) AS trunc_two,
    TRUNC(123.4567::NUMERIC, 0) AS trunc_zero,
    TRUNC(123.4567::NUMERIC, -1) AS trunc_tens;
```

Kết quả tương ứng: 123.45, 123, 120.

Với số âm:

```sql
SELECT
    TRUNC(-123.4567::NUMERIC, 2) AS neg_trunc,
    ROUND(-123.4567::NUMERIC, 2) AS neg_round;
```

Kết quả: -123.45 và -123.46.

### 9.3. Khi giá trị nằm chính giữa hai mức làm tròn

Với kiểu `NUMERIC`, PostgreSQL làm tròn trường hợp đúng giữa hai lựa chọn **ra xa số 0** (*ties away from zero*) theo quy tắc làm tròn mặc định.

```sql
SELECT
    ROUND( 2.5::NUMERIC) AS plus_two_point_five,
    ROUND(-2.5::NUMERIC) AS minus_two_point_five,
    ROUND( 1.235::NUMERIC, 2) AS plus_three_digits,
    ROUND(-1.235::NUMERIC, 2) AS minus_three_digits;
```

Kết quả:

| Đầu vào numeric | Sau ROUND |
| --- | ---: |
| 2.5 | 3 |
| -2.5 | -3 |
| 1.235 tới 2 chữ số | 1.24 |
| -1.235 tới 2 chữ số | -1.24 |

**Không nên mặc định cùng một quy tắc cho `DOUBLE PRECISION`**. Việc xử lý giá trị đúng ở giữa của hàm `round(double precision)` phụ thuộc cơ chế floating-point/hệ thống, thường theo quy tắc gần nhất với kết quả chẵn trong những môi trường phổ biến.

Ví dụ:

```sql
SELECT
    ROUND(2.5::NUMERIC) AS decimal_round,
    ROUND(2.5::DOUBLE PRECISION) AS float_round;
```

Trong môi trường IEEE thông dụng, phần numeric là 3, còn phần double có thể là 2 theo round-to-nearest-even. Đừng xây logic tiền dựa trên một giả định về cách làm tròn dấu phẩy động giữa các nền tảng.

### 9.4. Hai tham số của ROUND cần kiểu NUMERIC phù hợp

Một khác biệt API quan trọng:

```sql
-- Hợp lệ:
SELECT ROUND(12.345::NUMERIC, 2);
```

Nhưng trong PostgreSQL, dạng:

```sql
-- DỰ KIẾN LỖI: không có round(double precision, integer)
-- với chữ ký hàm thông thường.
SELECT ROUND(12.345::DOUBLE PRECISION, 2);
```

thường báo không tìm thấy hàm khớp đối số.

Cách sửa là chuyển giá trị sang NUMERIC **nếu việc chuyển kiểu phù hợp yêu cầu**, rồi gọi hàm:

```sql
SELECT ROUND((12.345::DOUBLE PRECISION)::NUMERIC, 2);
```

Tuy nhiên, việc cast một giá trị đã qua floating-point sang NUMERIC **không làm sống lại độ chính xác đầu vào đã mất**. Nếu cần decimal chính xác, hãy parse/lưu bằng NUMERIC từ đầu.

---

## 10. NUMERIC(p,s): precision, scale và làm tròn khi lưu

Khai báo:

```sql
amount NUMERIC(12,2)
```

có ý nghĩa thông thường:

- Tổng **12 chữ số thập phân có nghĩa** trong miền được khai báo.
- Giữ **2 chữ số phía sau dấu thập phân**.
- Cho tối đa **10 chữ số phần nguyên** trong dạng `0 <= scale <= precision`.

Ví dụ:

```sql
SELECT
    123.456::NUMERIC(8,2) AS rounded_on_cast;
```

Kết quả là **123.46**.

Đây là điều rất quan trọng: khi một giá trị được ép vào `NUMERIC(p,s)`, PostgreSQL có thể **làm tròn tới scale của cột**, không phải lúc nào cũng báo lỗi khi đầu vào có quá nhiều chữ số lẻ.

### 10.1. Scale không phải bộ kiểm tra format đầu vào

Nếu người dùng nhập `19.999` nhưng nghiệp vụ chỉ chấp nhận hai chữ số sau dấu thập phân:

```sql
SELECT 19.999::NUMERIC(8,2) AS stored_value;
```

kết quả có thể là **20.00**.

Bởi vậy:

- Nếu **được phép làm tròn**, hãy ghi rõ quy tắc và thực hiện có chủ đích.
- Nếu **bắt buộc từ chối** đầu vào hơn hai chữ số, kiểm tra **dữ liệu gốc trước khi cast**.
- Không dùng CHECK kiểu `CHECK(amount = ROUND(amount,2))` trên một cột đã là `NUMERIC(...,2)` để chứng minh input có tối đa 2 chữ số lẻ; giá trị đã có thể bị làm tròn trước CHECK.

### 10.2. Precision có thể gây overflow sau làm tròn

```sql
SELECT 999.99::NUMERIC(5,2) AS valid_amount;
```

Hợp lệ vì phần nguyên có ba chữ số.

Nhưng:

```sql
-- DỰ KIẾN LỖI: phần nguyên vượt khả năng của NUMERIC(5,2).
SELECT 1000.00::NUMERIC(5,2);
```

bị từ chối.

Ngay cả giá trị gần giới hạn như `999.995` cũng có thể bị làm tròn lên `1000.00` và **sau đó vượt giới hạn của cột**.

### 10.3. Không dùng scale 2 cho mọi giá trị

| Đại lượng | Ví dụ kiểu | Tại sao |
| --- | --- | --- |
| Số tiền cuối cùng bằng USD | `NUMERIC(18,2)` | Lưu tới cent theo hợp đồng nghiệp vụ |
| Giá cho một đơn vị hàng nhỏ | `NUMERIC(18,4)` | Có thể nhỏ hơn một cent |
| Tỷ giá | `NUMERIC(24,10)` | Cần nhiều chữ số để giảm sai lệch khi nhân |
| Số lượng/khối lượng | `NUMERIC(12,3)` | Số lượng có phần lẻ theo đơn vị đo |
| Thuế suất dạng tỷ lệ 0..1 | `NUMERIC(9,6)` | Cần precision của tỷ lệ |
| Giá trị trung gian | `NUMERIC` | Không vội giới hạn scale ngay |

Đây là các ví dụ, không phải quy định bắt buộc. Chọn precision và scale theo **miền giá trị và phép toán có thể xảy ra**.

---

## 11. Sai số floating point: tại sao 0.1 + 0.2 khó bằng 0.3?

`REAL` và `DOUBLE PRECISION` dùng biểu diễn **nhị phân dấu phẩy động**. Phân số thập phân `0.1` không có biểu diễn nhị phân hữu hạn, nên giá trị lưu là một xấp xỉ.

Thử:

```sql
SELECT
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        AS calculated,
    0.3::DOUBLE PRECISION
        AS expected,
    (
        0.1::DOUBLE PRECISION
        + 0.2::DOUBLE PRECISION
        = 0.3::DOUBLE PRECISION
    ) AS equal_as_floats;
```

Ở phần lớn môi trường floating-point nhị phân thông dụng, phép so sánh bằng nhau tuyệt đối trong ví dụ có thể trả **FALSE**, vì hai phía dùng những giá trị nhị phân gần 0.3 nhưng không đồng nhất.

So sánh với:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC)
      = 0.3::NUMERIC AS equal_as_decimal;
```

Kết quả TRUE.

### 11.1. Độ chính xác hiển thị khác độ chính xác bên trong

PostgreSQL có thể hiển thị một số thực dưới dạng chuỗi ngắn dễ đọc, tùy quy tắc output và cấu hình `extra_float_digits`:

```sql
SHOW extra_float_digits;
```

Việc nhìn thấy `0.3` trên màn hình **không chứng minh** rằng số floating point được lưu chính xác bằng phân số thập phân 3/10.

Đừng dùng cách ép kiểu sang text hoặc số chữ số hiển thị để quyết định hai phép tính thực sự bằng nhau.

### 11.2. Thứ tự cộng có thể ảnh hưởng tổng floating point

Phép cộng dấu phẩy động phải làm tròn từng bước vào một số chữ số có nghĩa hữu hạn. Vì vậy về mặt tính toán máy tính, tổng có thể phụ thuộc thứ tự cộng khi các số có độ lớn rất khác nhau.

Ví dụ ý tưởng:

```text
1e16 + 1 - 1e16

Nếu phép cộng giữa 1e16 và 1 làm mất giá trị 1
do precision hữu hạn:
    kết quả cuối có thể là 0

Nhưng nếu nhóm 1 + (-1e16) rồi cộng với 1e16,
kết quả cũng chịu các bước làm tròn khác nhau.
```

Một ví dụ thể hiện rõ thứ tự trong nhiều hệ thống IEEE:

```sql
SELECT
    (
        (1e16::DOUBLE PRECISION + 1::DOUBLE PRECISION)
        - 1e16::DOUBLE PRECISION
    ) AS first_order,

    (
        1e16::DOUBLE PRECISION
        + (1::DOUBLE PRECISION - 1e16::DOUBLE PRECISION)
    ) AS second_order;
```

Cả hai thứ tự trong ví dụ cụ thể này **có thể cùng làm mất 1**; điều quan trọng là tính không kết hợp tuyệt đối của floating-point. Để thấy khác biệt rõ hơn, có thể đối chiếu:

```sql
SELECT
    (
        (1e16::DOUBLE PRECISION
          + (-1e16)::DOUBLE PRECISION)
        + 1::DOUBLE PRECISION
    ) AS cancel_first,

    (
        1e16::DOUBLE PRECISION
        + ((-1e16)::DOUBLE PRECISION
          + 1::DOUBLE PRECISION)
    ) AS add_small_to_large_first;
```

Ở môi trường IEEE phổ biến, `cancel_first` là 1, còn `add_small_to_large_first` có thể là 0.

Với `SUM(double precision)` trên lượng dữ liệu lớn, kế hoạch song song và thứ tự xử lý khác nhau cũng có thể tạo sai lệch rất nhỏ ở các chữ số cuối. Không mặc định tổng floating point phải có bit pattern giống nhau giữa mọi kế hoạch.

### 11.3. NUMERIC có giải quyết mọi sai số không?

`NUMERIC` phù hợp khi cần **số thập phân hữu hạn chính xác** hoặc phép toán decimal với precision được kiểm soát. Nhưng không tự biến mọi phép tính thành kết quả toán học vô hạn độ chính xác:

- `1 / 3` không có kết quả thập phân hữu hạn.
- Các phép lũy thừa, căn và log có thể cần gần đúng.
- Cast sang `NUMERIC(p,s)` có thể làm tròn.
- Thao tác sai thứ tự vẫn cho kết quả nghiệp vụ sai.
- Dữ liệu đã mất chính xác ở `double` không thể được khôi phục từ ý định ban đầu chỉ bằng cast.

Chọn NUMERIC là **quyết định representation**, không thay thế thiết kế rounding và validation.

---

## 12. So sánh hai số thực gần bằng nhau

Nếu tính toán bằng floating point để đo lường hoặc mô phỏng, phép so sánh:

```sql
actual_value = expected_value
```

có thể quá nghiêm ngặt khi hai giá trị chỉ khác nhau bởi sai số tính toán.

Một cách thường dùng là kiểm tra **độ lệch tuyệt đối**:

```sql
SELECT
    ABS(
        (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        - 0.3::DOUBLE PRECISION
    ) < 1e-12::DOUBLE PRECISION AS nearly_equal;
```

Trong môi trường IEEE phổ biến, kết quả TRUE.

### 12.1. Chọn epsilon theo đơn vị

`epsilon = 0.000001` có ý nghĩa rất khác giữa:

- Sai số nhiệt độ tính theo độ C.
- Sai số khoảng cách tính theo mét.
- Sai số đo bằng microsecond.
- Sai số của số tiền quy đổi.

Không có một epsilon đúng cho mọi lĩnh vực. Nếu cần chính xác tới 0.01 USD, tốt hơn nên dùng representation tiền tệ exact, không chỉ so sánh double với một epsilon tùy tiện.

### 12.2. Dung sai tuyệt đối kết hợp tương đối

Khi giá trị có thể rất lớn hoặc rất nhỏ, có thể dùng:

```sql
SELECT
    ABS(actual_value - expected_value)
        <= GREATEST(
            0.000001::DOUBLE PRECISION,
            0.000001::DOUBLE PRECISION
                * GREATEST(
                    ABS(actual_value),
                    ABS(expected_value)
                )
        ) AS approximately_equal
FROM arithmetic_lab.sensor_readings
WHERE actual_value IS NOT NULL
  AND expected_value IS NOT NULL;
```

Ở đây:

- Vế trái là độ lệch tuyệt đối.
- `0.000001` đầu là dung sai tuyệt đối minh họa.
- Phần nhân giá trị lớn hơn là dung sai tương đối.
- `GREATEST` lấy ngưỡng lớn hơn của hai tiêu chí.

**Đây là công thức minh họa**, không phải chuẩn sai số chung. Ngưỡng cần được thiết kế theo yêu cầu đo lường, thiết bị, khoảng giá trị và độ nhạy nghiệp vụ.

### 12.3. Tránh epsilon khi cần so sánh giá trị tiền đã chốt

Nếu một giao dịch phải thanh toán đúng **19.99 USD**, việc dùng:

```sql
ABS(amount_float - 19.99) < 0.01
```

có thể coi nhiều giá trị khác nhau tới gần một cent là “bằng nhau”. Trong hệ thống thanh toán, điều đó có thể không chấp nhận được.

Với số tiền đã chốt, nên lưu `NUMERIC` có scale thích hợp hoặc số nguyên theo đơn vị nhỏ nhất, rồi kiểm tra bằng nhau theo hợp đồng tiền tệ.

### 12.4. NULL và NaN trong phép gần bằng nhau

Một phép so sánh có `NULL` thường cho UNKNOWN và bị loại trong `WHERE`. Giá trị đặc biệt `NaN` hoặc infinity có thể cần xử lý tách biệt theo chính sách dữ liệu; không mặc định các công thức epsilon tự kiểm tra tính hữu hạn.

---

## 13. Giá trị đặc biệt: NaN và Infinity

Các kiểu floating-point của PostgreSQL có thể biểu diễn những giá trị đặc biệt như:

- `NaN` — Not a Number.
- `Infinity` — dương vô cực.
- `-Infinity` — âm vô cực.

Có thể minh họa bằng literal được cast tường minh:

```sql
SELECT
    'NaN'::DOUBLE PRECISION AS float_nan,
    'Infinity'::DOUBLE PRECISION AS float_positive_inf,
    '-Infinity'::DOUBLE PRECISION AS float_negative_inf;
```

Kiểu `NUMERIC` của PostgreSQL hiện đại cũng hỗ trợ các giá trị đặc biệt trong những điều kiện/khai báo phù hợp, mặc dù các giới hạn precision/scale có thể làm một số giá trị không lưu được.

### 13.1. PostgreSQL có quy tắc so sánh NaN riêng

Không nên giả định mọi hệ quản trị SQL dùng hoàn toàn cùng ngữ nghĩa IEEE cho so sánh NaN. PostgreSQL có những quy tắc phục vụ việc sắp xếp và index, trong đó các giá trị NaN có thể được coi bằng nhau và lớn hơn những giá trị số không phải NaN khi so sánh/sắp xếp.

Thử trong lab:

```sql
SELECT
    'NaN'::DOUBLE PRECISION = 'NaN'::DOUBLE PRECISION
        AS pg_nan_equals_nan,
    'NaN'::DOUBLE PRECISION > 1000::DOUBLE PRECISION
        AS pg_nan_greater_than_number;
```

Vì vậy, một `CHECK (value >= 0)` **không tự chứng minh giá trị là số hữu hạn hợp lệ** nếu kiểu dữ liệu cho phép NaN hoặc infinity.

Nếu ứng dụng chỉ nhận phép đo hữu hạn, cần có validation tại ứng dụng hoặc ràng buộc được thiết kế đúng theo kiểu và phiên bản sử dụng. Không xem NaN là giá trị cảm biến hợp lệ chỉ vì nó có kiểu `DOUBLE PRECISION`.

### 13.2. Infinity không phải cách xử lý lỗi chia cho 0 mặc định

Trong nhiều ngôn ngữ tính toán, một phép chia floating-point có thể cho Infinity. Nhưng trong SQL PostgreSQL:

```sql
-- DỰ KIẾN LỖI division_by_zero.
SELECT 1.0::DOUBLE PRECISION / 0.0::DOUBLE PRECISION;
```

Không nên trông đợi biểu thức này trả infinity rồi mới xử lý sau; PostgreSQL có thể báo lỗi chia cho 0. Hãy kiểm tra mẫu số rõ ràng trước phép chia.

---

## 14. Chia cho 0: lỗi và cách xử lý

Mẫu:

```sql
SELECT 100 / 0;
```

phát sinh lỗi:

```text
ERROR: division by zero
SQLSTATE: 22012
```

Với một câu SQL nằm trong transaction tường minh, lỗi có thể khiến transaction rơi vào trạng thái aborted; ứng dụng cần `ROLLBACK` hoặc xử lý savepoint phù hợp thay vì tiếp tục như chưa có lỗi.

### 14.1. Dùng NULLIF để tránh phép chia cho 0

`NULLIF(a,b)` trả `NULL` nếu hai giá trị bằng nhau; nếu không, nó trả `a`.

Ví dụ:

```sql
SELECT
    100::NUMERIC / NULLIF(0::NUMERIC, 0::NUMERIC)
        AS safe_ratio;
```

`NULLIF(0,0)` trả NULL, nên phép chia thành `100 / NULL` và trả NULL thay vì lỗi chia cho 0.

Với mẫu số khác 0:

```sql
SELECT
    100::NUMERIC / NULLIF(4::NUMERIC, 0::NUMERIC)
        AS ratio;
```

Kết quả 25.

### 14.2. Ví dụ tính giá trị trung bình cho các nhóm có thể rỗng

Giả sử có cột `success_count` và `total_count`:

```sql
SELECT
    success_count::NUMERIC
       / NULLIF(total_count, 0) AS success_ratio
FROM some_daily_metrics;
```

Đây là mẫu SQL cho bảng giả định `some_daily_metrics`, chưa được tạo trong lab.

Nếu `total_count = 0`, tỷ lệ trả NULL. Đây thường là cách diễn đạt đúng: **không đủ mẫu số để định nghĩa tỷ lệ**.

### 14.3. Có nên COALESCE kết quả NULL về 0?

```sql
SELECT COALESCE(
    100::NUMERIC / NULLIF(0::NUMERIC, 0::NUMERIC),
    0::NUMERIC
) AS ratio_or_zero;
```

Câu này trả 0.

Nhưng hãy suy nghĩ: **không xác định tỷ lệ** có thật sự đồng nghĩa **tỷ lệ bằng 0** không?

| Tình huống | Ý nghĩa |
| --- | --- |
| 0 thành công trên 10 lượt | Tỷ lệ thành công 0% |
| 0 thành công trên 0 lượt | Không có quan sát, tỷ lệ không xác định |
| 5 thành công trên 0 lượt | Dữ liệu không nhất quán hoặc định nghĩa khác |
| total_count NULL | Chưa có thông tin mẫu số |

Nếu báo cáo muốn hiển thị dấu gạch ngang hoặc “N/A” khi không có mẫu số, giữ NULL có thể là lựa chọn đúng hơn. `COALESCE` chỉ nên dùng khi nghiệp vụ quy định rõ.

### 14.4. Dùng CASE để xử lý riêng

```sql
SELECT CASE
    WHEN 0 = 0 THEN NULL::NUMERIC
    ELSE 100::NUMERIC / 0::NUMERIC
END AS guarded_result;
```

Đây là ví dụ cách phân nhánh ý tưởng, nhưng trong PostgreSQL có **một lưu ý về planner**: biểu thức hằng như `1/0` đôi khi có thể bị tính sớm khi lập kế hoạch ngay cả trong nhánh CASE mà bạn cho là không chạy.

Vì thế, không nên dùng một mẫu CASE chứa phép chia hằng cho 0 để cam kết mọi lỗi đều bị tránh. Trong truy vấn thực tế có mẫu số từ cột, giải pháp như `numerator / NULLIF(denominator, 0)` thường ngắn và dễ kiểm chứng hơn.

### 14.5. NULLIF không sửa dữ liệu sai

Dùng `NULLIF` ngăn lỗi tại phép chia, nhưng nếu `total_count = 0` trong một tình huống mà về nghiệp vụ nó **không bao giờ được bằng 0**, bạn vẫn nên phát hiện và xử lý dữ liệu đầu vào, thay vì giấu sự cố bằng một NULL im lặng.

---

## 15. NULL trong phép toán số học

Nhiều toán tử và hàm số học thông dụng của PostgreSQL có hành vi: khi đầu vào là NULL, kết quả trả NULL.

```sql
SELECT
    10 + NULL::INTEGER AS add_null,
    10 * NULL::INTEGER AS multiply_null,
    ABS(NULL::NUMERIC) AS abs_null,
    ROUND(NULL::NUMERIC, 2) AS round_null;
```

Các biểu thức đều trả NULL.

### 15.1. NULL không phải 0

Ví dụ một bảng có cột `discount_rate` nullable:

- `discount_rate = 0`: biết rõ không giảm giá.
- `discount_rate IS NULL`: chưa xác định mức giảm hoặc không áp dụng theo mô hình.
- Hai trạng thái có thể khác ý nghĩa.

Nếu dùng:

```sql
COALESCE(discount_rate, 0)
```

bạn đang **quyết định** coi giá trị thiếu là 0. Điều đó có thể đúng cho một default nghiệp vụ, nhưng không được tự áp dụng cho mọi dữ liệu.

### 15.2. NULLIF và COALESCE

```sql
SELECT
    NULLIF(5, 5) AS equal_to_null,
    NULLIF(5, 3) AS different_remains,
    COALESCE(NULL::INTEGER, 8) AS first_nonnull,
    COALESCE(NULL::NUMERIC, NULL::NUMERIC, 2.5::NUMERIC)
        AS third_value;
```

Ý nghĩa:

- `NULLIF(5,5)` → NULL.
- `NULLIF(5,3)` → 5.
- `COALESCE(NULL,8)` → 8.
- `COALESCE(NULL,NULL,2.5)` → 2.5.

Không dùng `COALESCE` vô điều kiện để biến dữ liệu lỗi, dữ liệu chưa nhận được hoặc chia cho 0 thành một giá trị hợp lệ giả tạo.

### 15.3. SUM và AVG bỏ qua NULL ở đầu vào

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(reading_value) AS known_readings,
    SUM(reading_value) AS sum_readings,
    AVG(reading_value) AS average_reading
FROM arithmetic_lab.sensor_readings;
```

Bảng lab có bốn hàng, trong đó một reading_value NULL.

- `COUNT(*)` đếm 4 hàng.
- `COUNT(reading_value)` đếm 3 giá trị không NULL.
- `SUM` và `AVG` bỏ qua reading_value NULL theo quy tắc aggregate.

Nếu mọi reading đều NULL, `AVG` và `SUM` trả NULL, không phải số 0.

---

## 16. Overflow, underflow và giới hạn miền số

Một phép toán có thể **đúng về công thức** nhưng kết quả không thể biểu diễn bằng kiểu dữ liệu đã chọn.

### 16.1. Tràn số nguyên

`INTEGER` có miền số nguyên có dấu:

```text
-2147483648 ... 2147483647
```

Ví dụ:

```sql
-- DỰ KIẾN LỖI tràn INTEGER.
SELECT 2147483647::INTEGER + 1::INTEGER;
```

Nếu muốn phép cộng có thể vượt miền INTEGER, hãy chuyển kiểu **trước phép cộng**:

```sql
SELECT
    2147483647::BIGINT + 1::BIGINT
        AS safe_bigint_sum;
```

Kết quả 2147483648, hợp lệ trong BIGINT.

### 16.2. BIGINT cũng có giới hạn

`BIGINT` có miền:

```text
-9223372036854775808 ... 9223372036854775807
```

Với số có thể vượt miền này, dùng `NUMERIC` cho bước tính hoặc thiết kế lại mô hình dữ liệu.

```sql
SELECT
    9000000000000000000::NUMERIC
      + 9000000000000000000::NUMERIC
        AS decimal_large_sum;
```

Kết quả 18000000000000000000, vượt BIGINT nhưng vẫn phù hợp với NUMERIC trong ví dụ.

### 16.3. Cast sau khi nhân có thể quá muộn

Ví dụ sai:

```sql
-- DỰ KIẾN LỖI: INTEGER * INTEGER có thể overflow trước cast.
SELECT (2000000000::INTEGER * 2::INTEGER)::BIGINT;
```

Phép nhân kiểu INTEGER phải hoàn tất trước khi kết quả được cast thành BIGINT. Nếu nó tràn, cast cuối không cứu được.

Cách đúng:

```sql
SELECT 2000000000::BIGINT * 2::BIGINT AS safe_product;
```

Tương tự, nếu chia số nguyên rồi cast sang NUMERIC, phần lẻ đã mất. **Thời điểm chuyển kiểu quan trọng không kém việc chọn kiểu đích.**

### 16.4. Kiểm tra miền ngay khi thiết kế schema

Nếu số lượng không bao giờ âm:

```sql
quantity BIGINT NOT NULL CHECK (quantity >= 0)
```

Nếu tỷ lệ là giá trị từ 0 đến 1:

```sql
rate NUMERIC(9,6) NOT NULL
    CHECK (rate BETWEEN 0 AND 1)
```

Nếu cần số nguyên lớn hơn 0:

```sql
units INTEGER NOT NULL CHECK (units > 0)
```

Constraint giúp ngăn những giá trị không phù hợp với miền nghiệp vụ, nhưng **không bảo đảm công thức ở các bước sau không overflow**. Vẫn phải ước lượng khả năng tăng trưởng và kết quả trung gian.

### 16.5. Numeric field overflow

Một câu:

```sql
-- DỰ KIẾN LỖI: precision quá nhỏ.
SELECT 100000::NUMERIC(5,2);
```

vượt miền NUMERIC(5,2). PostgreSQL thường dùng SQLSTATE **22003** cho các lỗi numeric value out of range hoặc những tình huống tương ứng.

Ứng dụng phải phân biệt lỗi out of range với lỗi input không parse được, chia cho 0 và vi phạm CHECK/NOT NULL.

### 16.6. Underflow với floating point

Với floating point, một số khác 0 nhưng **quá nhỏ** có thể không biểu diễn được ở độ lớn yêu cầu, hoặc bị làm tròn đến 0 trong những tình huống nhất định.

Ví dụ khái niệm:

```text
Một phép nhân ra 10^-400
nhưng kiểu floating-point có miền mũ hữu hạn.
Kết quả có thể bị dưới ngưỡng biểu diễn.
```

Không có nghĩa mọi tình huống underflow đều trả 0 một cách im lặng. Hành vi cụ thể có thể phụ thuộc phép toán/kiểu/phiên bản và các quy tắc lỗi của PostgreSQL. Nếu cần các đại lượng cực nhỏ, hãy kiểm tra miền số và representation ngay từ thiết kế.

---

## 17. POWER, SQRT, CBRT và hàm toán học khác

Ngoài phép tính cộng trừ nhân chia, PostgreSQL có các hàm toán học dùng cho thống kê, kỹ thuật và phân tích.

### 17.1. POWER và toán tử ^

```sql
SELECT
    POWER(2::NUMERIC, 3::NUMERIC) AS two_cubed,
    2 ^ 3 AS two_cubed_operator,
    POWER(10::NUMERIC, 2::NUMERIC) AS ten_squared;
```

Các kết quả: 8, 8, 100.

Khi viết biểu thức nhiều lũy thừa hoặc kết hợp số âm, hãy **dùng ngoặc để xác định rõ nhóm tính**, không tự suy ra từ thói quen ký hiệu toán học ngoài SQL.

### 17.2. SQRT và CBRT

```sql
SELECT
    SQRT(81::NUMERIC) AS square_root_81,
    CBRT(27::DOUBLE PRECISION) AS cube_root_27;
```

Kết quả theo ý nghĩa: 9 và xấp xỉ 3.

Số học căn, lũy thừa và log có **miền xác định**. Ví dụ căn bậc hai thực của số âm không xác định trong tập số thực; PostgreSQL không tự biến nó thành một số thực hợp lệ chỉ vì có hàm SQRT.

```sql
-- DỰ KIẾN LỖI miền giá trị với số thực âm.
SELECT SQRT((-1)::NUMERIC);
```

Cách xử lý phải đến từ nghiệp vụ:

- Nếu số âm là dữ liệu sai: từ chối/đánh dấu lỗi.
- Nếu cần toán học số phức: biểu diễn/công cụ riêng, không giả định SQRT của số thực trả số phức.
- Nếu giá trị âm cực nhỏ do sai số floating-point: xác định chính sách tolerance/clip có kiểm soát, không tự che giấu mọi giá trị âm.

### 17.3. LOG, LN và miền đầu vào

Các hàm logarithm yêu cầu đầu vào phù hợp với miền toán học; ví dụ log của số không dương không có giá trị thực hữu hạn thông thường.

```sql
SELECT
    LN(1::NUMERIC) AS ln_one,
    LN(10::NUMERIC) AS ln_ten,
    LOG(100::NUMERIC) AS log_base_ten_of_100;
```

Kết quả theo ý nghĩa: 0, giá trị gần 2.302585..., và 2.

Không chạy `LN(0)` hoặc `LOG(-1)` như một cách mặc định lấy NULL; những tình huống ngoài miền có thể báo lỗi.

### 17.4. PI và các hàm lượng giác

PostgreSQL có hàm `PI()` và nhiều hàm lượng giác phục vụ kỹ thuật:

```sql
SELECT
    PI() AS pi_approx,
    RADIANS(180::DOUBLE PRECISION) AS radians_of_180,
    DEGREES(PI() / 2) AS degrees_of_half_pi,
    SIN(PI() / 2) AS sine_of_half_pi;
```

Những phép tính này thường dùng floating point xấp xỉ; không nên so sánh trực tiếp kết quả với 0 hoặc 1 bằng dấu `=` cho mọi trường hợp. Nếu bài toán cần ngưỡng kiểm tra, sử dụng dung sai được thiết kế theo đơn vị.

---

## 18. RANDOM và số giả ngẫu nhiên

PostgreSQL có `RANDOM()`, trả một số giả ngẫu nhiên kiểu `DOUBLE PRECISION` thường nằm trong khoảng **[0,1)**.

```sql
SELECT RANDOM() AS random_fraction;
```

Ví dụ để mô phỏng một số nguyên 1..6 trong bài lab:

```sql
SELECT
    FLOOR(RANDOM() * 6)::INTEGER + 1
        AS simulated_die_roll;
```

Kết quả có thể là một số nguyên từ 1 đến 6.

### 18.1. RANDOM không phù hợp tạo token bảo mật

`RANDOM()` phục vụ mục đích thống kê/mô phỏng/thử nghiệm thông thường. Không dùng nó để sinh password reset token, API secret hoặc giá trị cần tính bí mật mật mã.

Các ứng dụng cần ngẫu nhiên bảo mật phải dùng API nguồn entropy/cryptographic random phù hợp và cơ chế bảo mật riêng.

### 18.2. Khả năng tái lập

PostgreSQL hỗ trợ `SETSEED` để đặt seed cho generator giả ngẫu nhiên ở session trong một số ngữ cảnh:

```sql
SELECT SETSEED(0.25);
SELECT RANDOM();
```

Cách này có thể hữu ích cho thí nghiệm, nhưng **không phải bảo đảm** rằng mọi phiên bản, môi trường, kế hoạch chạy và số lần gọi sẽ luôn tạo kết quả giống hệt nhau. Không xây tính đúng của nghiệp vụ dựa trên chuỗi RANDOM mặc định.

---

## 19. SUM, AVG, MIN, MAX và kiểu kết quả

Hàm tổng hợp cũng là một phần quan trọng của xử lý số học trong truy vấn.

```sql
SELECT
    COUNT(*) AS line_count,
    SUM(line_gross) AS total_gross,
    AVG(line_gross) AS average_gross,
    MIN(line_gross) AS minimum_gross,
    MAX(line_gross) AS maximum_gross
FROM arithmetic_lab.order_lines;
```

Với dữ liệu lab:

- `ITEM-A`: 2 × 19.99 = 39.98.
- `ITEM-B`: 1.5 × 4.20 = 6.30.
- `ITEM-C`: 100 × 0.0150 = 1.50.
- `ITEM-D`: 3 × 12.3450 = 37.0350.
- `ITEM-E`: 1 × 100 = 100.00.

Tổng gross ban đầu là **184.8150** trước mọi quy tắc làm tròn thành tiền theo currency.

### 19.1. Kiểu dữ liệu đầu vào ảnh hưởng kiểu của aggregate

Một số quy tắc PostgreSQL phổ biến:

| Đầu vào | `SUM(...)` thường trả | `AVG(...)` thường trả |
| --- | --- | --- |
| `SMALLINT` | `BIGINT` | `NUMERIC` |
| `INTEGER` | `BIGINT` | `NUMERIC` |
| `BIGINT` | `NUMERIC` | `NUMERIC` |
| `NUMERIC` | `NUMERIC` | `NUMERIC` |
| `REAL` | `REAL` | `DOUBLE PRECISION` |
| `DOUBLE PRECISION` | `DOUBLE PRECISION` | `DOUBLE PRECISION` |

Đây là những hành vi của các aggregate PostgreSQL thông dụng, không phải lời hứa rằng mọi phép toán số học khác đều tự nâng kiểu theo cùng quy tắc.

Ví dụ `SUM(integer)` có thể tránh overflow của một tổng vừa phải nhờ trả BIGINT, nhưng một biểu thức **integer × integer** nằm bên trong SUM có thể overflow **trước khi aggregate nhận giá trị**.

### 19.2. Cast trước aggregate khi cần miền lớn

Ví dụ một bảng giả định có `quantity INTEGER` và `unit_price_cents INTEGER`.

Viết rủi ro:

```sql
-- Mẫu minh họa; bảng sale_items chưa tạo trong lab.
SELECT SUM(quantity * unit_price_cents)
FROM sale_items;
```

Phép nhân `INTEGER * INTEGER` có thể overflow trước khi SUM.

Một cách chuyển kiểu trước:

```sql
SELECT SUM(
    quantity::NUMERIC * unit_price_cents::NUMERIC
)
FROM sale_items;
```

Hoặc cast sang BIGINT nếu chắc chắn các tích và tổng phù hợp miền số.

### 19.3. SUM trên tập rỗng không tự là 0

```sql
SELECT
    COUNT(*) AS rows_count,
    SUM(line_gross) AS total
FROM arithmetic_lab.order_lines
WHERE sku = 'SKU-NOT-FOUND';
```

Kết quả: `rows_count = 0` và `total = NULL`.

Nếu báo cáo muốn hiển thị 0:

```sql
SELECT
    COALESCE(SUM(line_gross), 0::NUMERIC) AS total
FROM arithmetic_lab.order_lines
WHERE sku = 'SKU-NOT-FOUND';
```

Không nên thay `AVG(...) NULL` bằng 0 một cách máy móc khi tập không có quan sát.

---

## 20. Làm tròn từng dòng hay làm tròn ở tổng?

Đây là lỗi tính toán tiền thường gặp, dù mọi toán hạng đều `NUMERIC`.

Giả sử có hai dòng, mỗi dòng có giá trị 0.05 USD, và một thuế suất **giả định** 10%.

### 20.1. Làm tròn thuế từng dòng

```sql
SELECT
    ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
    + ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
        AS tax_per_line_then_sum;
```

Mỗi dòng có thuế chưa làm tròn 0.005, làm tròn kiểu NUMERIC đến 2 chữ số là 0.01, cộng lại thành **0.02 USD**.

### 20.2. Cộng cơ sở trước, làm tròn thuế tổng

```sql
SELECT
    ROUND(
        (0.05::NUMERIC + 0.05::NUMERIC)
        * 0.10::NUMERIC,
        2
    ) AS tax_on_total;
```

Tổng cơ sở 0.10 × 10% = 0.01, nên kết quả **0.01 USD**.

| Phương pháp | Kết quả thuế |
| --- | ---: |
| Làm tròn mỗi dòng rồi SUM | 0.02 USD |
| SUM cơ sở rồi làm tròn thuế | 0.01 USD |

**Hai cách tính cùng dùng decimal exact nhưng vẫn cho kết quả khác.** Đó là do **điểm làm tròn**, không phải do lỗi lưu trữ PostgreSQL.

Chính sách thuế thực tế phải theo quy định và hợp đồng nghiệp vụ được áp dụng; bài này không mặc định một cách luôn đúng trong mọi hệ thống.

### 20.3. Tránh làm tròn đơn giá quá sớm

Đơn giá 0.0150 USD/đơn vị, số lượng 100:

```sql
SELECT
    ROUND(0.0150::NUMERIC, 2) * 100
        AS wrong_early_round,
    ROUND(0.0150::NUMERIC * 100, 2)
        AS line_total_rounded_at_end;
```

Kết quả:

- Làm tròn đơn giá trước: 0.02 × 100 = **2.00**.
- Nhân trước, làm tròn thành tiền sau: 1.50 = **1.50**.

Số tiền chênh 0.50 USD chỉ vì đặt ROUND sai vị trí.

**Quy tắc thiết kế:** giữ đủ chữ số của giá và phép tính trung gian; làm tròn theo **mốc nghiệp vụ đã được xác định**, không phải “càng sớm càng an toàn”.

---

## 21. Lab: tính số tiền sau chiết khấu

Bảng `arithmetic_lab.order_lines` đã có:

- `quantity NUMERIC(12,3)`.
- `unit_price NUMERIC(16,4)`.
- `discount_rate NUMERIC(7,5)`, là tỷ lệ từ 0 tới 1.
- `line_gross NUMERIC(20,4)`, tự tính `quantity * unit_price`.

Tính giảm giá và thành tiền sau giảm ở hai chữ số thập phân:

```sql
SELECT
    sku,
    quantity,
    unit_price,
    line_gross,
    discount_rate,
    ROUND(
        line_gross * discount_rate,
        2
    ) AS discount_amount,
    ROUND(
        line_gross * (1::NUMERIC - discount_rate),
        2
    ) AS line_net
FROM arithmetic_lab.order_lines
ORDER BY line_id;
```

Ở đây có **hai công thức cạnh tranh** cần lưu ý:

1. `ROUND(gross × (1 - rate), 2)`.
2. `ROUND(gross,2) - ROUND(gross × rate,2)`.

Chúng không mặc định bằng nhau với mọi dữ liệu. Nếu nghiệp vụ yêu cầu line amount được làm tròn trước rồi trừ discount đã làm tròn, hãy thiết kế đúng thứ tự đó thay vì tự chọn công thức tương đương về toán học thuần.

### 21.1. Tính tổng từ kết quả làm tròn từng dòng

Nếu quy tắc đã xác nhận là **làm tròn net của từng dòng** trước khi cộng hóa đơn:

```sql
WITH line_amounts AS (
    SELECT
        sku,
        ROUND(
            line_gross * (1::NUMERIC - discount_rate),
            2
        ) AS net_amount
    FROM arithmetic_lab.order_lines
)
SELECT
    COUNT(*) AS line_count,
    SUM(net_amount) AS invoice_net_total
FROM line_amounts;
```

Cách này làm rõ rằng số tiền của mỗi dòng đã được lượng tử hóa tới hai chữ số trước khi tổng hợp. Nếu nghiệp vụ yêu cầu tính chính xác tổng net chưa làm tròn rồi mới ROUND một lần, truy vấn cần khác:

```sql
SELECT
    ROUND(
        SUM(line_gross * (1::NUMERIC - discount_rate)),
        2
    ) AS invoice_net_round_once
FROM arithmetic_lab.order_lines;
```

Không nên mặc định hai câu luôn cho cùng kết quả.

### 21.2. Phân biệt decimal tiền và tỷ lệ

Nếu `discount_rate = 0.10` thì tương đương 10%, không phải 0.10%.

Một lỗi khi tích hợp API:

```text
Frontend: gửi "10" với ý nghĩa 10%
Backend: nhân trực tiếp amount * 10
Kết quả: giá trị gấp 10 lần, không phải giảm 10%
```

Cần xác định API nhận **percent 10** hay **fraction 0.10**, và nếu dùng fraction, constraint `BETWEEN 0 AND 1` giúp chặn nhiều giá trị ngoài miền.

### 21.3. Tỷ giá khác với tiền

Tỷ giá có thể cần nhiều chữ số thập phân hơn số tiền thanh toán cuối:

```sql
SELECT
    123.45::NUMERIC AS source_amount,
    25000.123456::NUMERIC AS example_rate,
    ROUND(
        123.45::NUMERIC * 25000.123456::NUMERIC,
        0
    ) AS rounded_target_amount;
```

Tỷ giá trên chỉ là **giả định để học**, không phải giá thị trường. Nếu dùng `NUMERIC(12,2)` cho rate này, bạn đã làm tròn tỷ giá trước và có thể tạo chênh lệch trong khoản quy đổi.

---

## 22. Tách giá trị, đơn vị và chính sách rounding

Một con số như `100` chưa xác định là:

- 100 USD.
- 100 cents.
- 100 đồng.
- 100 chiếc.
- 100%.
- Tỷ giá 100 đơn vị đích / 1 đơn vị nguồn.

Các phép toán phải thực hiện trên **đại lượng cùng đơn vị**.

### 22.1. Số tiền theo đơn vị nhỏ nhất

Nhiều hệ thống thanh toán chọn lưu số tiền đã chốt dưới dạng `BIGINT` minor units:

```text
USD 19.99 -> 1999 cents
VND 125000 -> 125000 đồng (nếu hợp đồng dùng scale 0)
KWD 1.234 -> 1234 đơn vị nhỏ nhất (nếu scale 3)
```

Trong trường hợp này, mọi ứng dụng phải thống nhất:

- Mã tiền tệ.
- Scale hay số chữ số minor units.
- Miền giá trị.
- Thời điểm chuyển đổi/round từ đơn giá/tỷ giá.
- Kiểu và giới hạn khi trao đổi qua JSON/JavaScript.

**Không cộng trực tiếp hai minor-unit amount của hai currency khác nhau**, dù cả hai đều là BIGINT.

### 22.2. Chuyển decimal sang minor units

Ví dụ USD có scale 2:

```sql
SELECT
    19.99::NUMERIC * 100 AS cents_decimal,
    ROUND(19.99::NUMERIC * 100, 0)::BIGINT
        AS cents_integer;
```

Kết quả 1999.

Nếu đầu vào `19.999`, phần cent không nguyên. Tùy hợp đồng, phải:

- Từ chối input vì quá nhiều chữ số lẻ.
- Hoặc làm tròn theo chính sách rõ ràng trước khi cast.

Không tự cast và hy vọng giá trị sẽ được hiểu đúng.

### 22.3. Giá trị nhỏ nhất khác nhau theo currency

Không nên nhân mọi loại tiền với 100:

- USD thường có 2 chữ số minor unit.
- JPY, VND trong nhiều hợp đồng dữ liệu có scale 0.
- Một số đồng tiền như KWD có thể dùng scale 3.

Hệ thống đa tiền tệ cần bảng/reference rule được quản trị, không lấy một số `100` cố định làm hệ số cho mọi giao dịch.

---

## 23. Các chức năng hiển thị không phải các chức năng tính toán

Khi xuất báo cáo, bạn có thể muốn hiển thị `12345.6` thành `12,345.60` hoặc dạng có ký hiệu tiền. PostgreSQL hỗ trợ `TO_CHAR` cho định dạng đầu ra.

Ví dụ:

```sql
SELECT
    TO_CHAR(12345.6::NUMERIC, 'FM999,999,990.00')
        AS formatted_amount;
```

Kết quả là **chuỗi text đã định dạng**, không còn là một giá trị numeric để tính toán trực tiếp theo cách thông thường.

### 23.1. Không lưu chuỗi format làm tiền

Không nên lưu:

```text
'12,345.60'
'12.345,60'
'$12,345.60'
```

làm dữ liệu tiền chính khi cột có thể lưu `NUMERIC` hoặc minor units.

Vì:

- Dấu phẩy/chấm có nghĩa khác nhau theo locale.
- Có thể chứa ký hiệu tiền không thống nhất.
- Sắp xếp chuỗi khác sắp xếp số.
- SUM/AVG và CHECK numeric trở nên khó khăn.
- Tái nhập có thể parse sai.

Tính toán bằng kiểu số; định dạng ở **tầng hiển thị** hoặc giai đoạn xuất báo cáo.

### 23.2. Lưu ý hàm ROUND và định dạng

`TO_CHAR` có thể có quy tắc định dạng/làm tròn theo mẫu. Nếu ứng dụng cần một con số nghiệp vụ **đã chốt**, nên tính và lưu/ghi nhận kết quả numeric theo policy trước, rồi chỉ định dạng để hiển thị.

Đừng lấy text đã format làm bằng chứng chính rằng giá trị nguồn ban đầu đã được lưu chính xác.

---

## 24. Nhập số từ text, CSV và API

Một lỗi độ chính xác thường xuất hiện **trước khi giá trị vào PostgreSQL**.

Ví dụ luồng xấu:

```text
Client nhập "19.99"
    -> Parser chuyển thành double
    -> Ứng dụng tính thêm nhiều phép double
    -> Cast sang NUMERIC(18,2)
    -> Lưu giá trị đã qua sai số/round trung gian
```

Cột NUMERIC cuối **không thể biết lại ý định gốc** nếu ứng dụng đã biến đổi giá trị sai.

### 24.1. Kiểm tra text trước khi cast

Nếu API chỉ chấp nhận USD không âm và tối đa hai chữ số lẻ, có thể xác định định dạng input:

```text
"0"
"0.01"
"19.99"
"1000.00"
```

Và từ chối:

```text
"-1.00"
"12.345"
"abc"
"1,000.00"    (nếu API chỉ cho số không có dấu phân cách hàng nghìn)
```

Một regex minh họa cho **chuỗi decimal không âm, dấu chấm, tối đa hai chữ số lẻ**:

```sql
SELECT
    input_text,
    input_text ~ '^[0-9]+(\.[0-9]{1,2})?$'
        AS format_ok
FROM (
    VALUES
        ('19.99'),
        ('12.345'),
        ('-1.00'),
        ('0'),
        ('abc')
) AS x(input_text);
```

**Regex chỉ kiểm tra format**, chưa kiểm tra số có vượt precision, đúng currency, đúng scale của payment provider hay quá lớn cho kiểu lưu trữ.

Việc chuyển giá trị dạng text sang NUMERIC cần xử lý những lỗi parse, giá trị ngoài miền và kiểm tra nghiệp vụ.

### 24.2. Lỗi input không hợp lệ

Ví dụ:

```sql
-- DỰ KIẾN LỖI ép kiểu.
SELECT 'abc'::NUMERIC;
```

PostgreSQL có thể báo lỗi SQLSTATE **22P02** (*invalid_text_representation*).

Một giá trị có dạng số hợp lệ nhưng ngoài miền có thể báo lỗi khác, như **22003** (*numeric_value_out_of_range*). Ứng dụng nên phân loại lỗi bằng SQLSTATE và trả thông điệp phù hợp, không chỉ so khớp chuỗi error message.

### 24.3. Dùng staging khi import dữ liệu chưa tin cậy

Một quy trình an toàn:

```text
File CSV / API external
          |
          v
Staging lưu raw string
          |
          v
Validate format + range + unit
          |
          v
Cast sang NUMERIC/BIGINT
          |
          v
Tính toán theo policy rõ ràng
          |
          v
Ràng buộc bảng chính + đối soát
```

Không biến mọi lỗi parse thành 0 hoặc NULL rồi bỏ qua. Điều đó có thể tạo báo cáo đẹp về hình thức nhưng sai tổng tiền hoặc mất dấu vết dữ liệu nguồn.

---

## 25. Java BigDecimal và JDBC khi làm việc với NUMERIC

Với ứng dụng Java kết nối PostgreSQL, `java.math.BigDecimal` là lựa chọn phổ biến để thao tác với `NUMERIC/DECIMAL`.

### 25.1. Không tạo BigDecimal từ double một cách vô ý

Mẫu không nên dùng cho số tiền decimal literal:

```java
import java.math.BigDecimal;

// Có thể mang vào BigDecimal biểu diễn nhị phân của double.
BigDecimal bad = new BigDecimal(0.1);
```

Nên dùng:

```java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal alsoUseful = BigDecimal.valueOf(0.1);
```

Dạng từ chuỗi giữ đúng ý nghĩa decimal mà người viết mô tả. `BigDecimal.valueOf(double)` thường dùng biểu diễn decimal của double an toàn hơn constructor trực tiếp, nhưng **không thể khôi phục những chữ số đã mất sau nhiều phép tính double**.

### 25.2. Quy định rounding mode

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("0.0150");
BigDecimal quantity = new BigDecimal("100");

BigDecimal gross = unitPrice.multiply(quantity);
BigDecimal payable = gross.setScale(2, RoundingMode.HALF_UP);

System.out.println(payable);  // 1.50
```

Trong Java, bạn có thể dùng `HALF_UP`, `HALF_EVEN`, `DOWN` hoặc các mode khác. **Không mặc định PostgreSQL `ROUND(numeric,scale)` và mọi mode của Java là tương đương**.

Nếu nghiệp vụ yêu cầu half-even, cần thiết kế logic tương ứng và kiểm thử đồng nhất giữa database, backend và các hệ thống đối soát.

### 25.3. Chia BigDecimal cần xác định độ chính xác

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal result = one.divide(
    three,
    8,
    RoundingMode.HALF_UP
);
```

Ở đây kết quả được làm tròn tới 8 chữ số lẻ. Không nên gọi phép chia tùy tiện rồi kỳ vọng mọi kết quả đều có biểu diễn hữu hạn; trong Java, một phép chia không kết thúc và không khai báo rounding phù hợp có thể báo `ArithmeticException`.

### 25.4. Truyền và đọc NUMERIC bằng JDBC

Ví dụ mẫu (bảng `payments` chưa được tạo trong lab):

```java
BigDecimal amount = new BigDecimal("19.99");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO payments (amount) VALUES (?)")) {
    ps.setBigDecimal(1, amount);
    ps.executeUpdate();
}
```

Khi đọc:

```java
BigDecimal stored = resultSet.getBigDecimal("amount");
```

Với số tiền minor units lưu BIGINT, có thể dùng `setLong/getLong`, nhưng vẫn cần currency và scale. Nếu kết nối JavaScript/JSON tham gia, lưu ý miền số nguyên chính xác của JavaScript Number nhỏ hơn miền BIGINT PostgreSQL.

---

## 26. Cách dùng EXPLAIN và quan sát hiệu năng

Tính toán bằng `NUMERIC` thường mang lại độ chính xác decimal cần thiết, nhưng có thể tốn CPU hơn phép tính `INTEGER/BIGINT` trong nhiều workload. Hàm số học trong `WHERE` cũng có thể ảnh hưởng khả năng dùng index.

### 26.1. Truy vấn có phép tính trên cột

Ví dụ:

```sql
SELECT sku, line_gross
FROM arithmetic_lab.order_lines
WHERE ROUND(line_gross, 2) >= 20::NUMERIC;
```

Nếu có một B-tree index chỉ trên `line_gross`, việc áp dụng hàm `ROUND(line_gross,2)` lên cột có thể làm truy vấn không tận dụng index theo cách đơn giản như `WHERE line_gross >= 20`.

Không được tự thay hai predicate trên thành tương đương nếu chúng **có thể khác nghĩa tại ranh giới rounding**. Trước tiên phải xác định logic nghiệp vụ, sau đó mới xem index hoặc thiết kế cột tính sẵn.

### 26.2. Expression index khi cần

Nếu một truy vấn quan trọng thường lọc bằng cùng một biểu thức:

```sql
CREATE INDEX idx_order_lines_rounded_gross
ON arithmetic_lab.order_lines (
    (ROUND(line_gross, 2))
);
```

PostgreSQL có thể cân nhắc expression index cho điều kiện tương ứng khi định nghĩa hàm, kiểu dữ liệu, thống kê và query phù hợp.

Nhưng:

- Index tăng dung lượng và chi phí ghi.
- Phải phù hợp chính xác với biểu thức được truy vấn.
- Một bảng lab chỉ có 5 hàng thường sẽ được quét tuần tự.
- Không tạo index trước khi biết workload thực tế.

### 26.3. Quan sát plan

```sql
EXPLAIN
SELECT sku
FROM arithmetic_lab.order_lines
WHERE ROUND(line_gross, 2) >= 20::NUMERIC;
```

Để đo thực thi trên SELECT:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku
FROM arithmetic_lab.order_lines
WHERE ROUND(line_gross, 2) >= 20::NUMERIC;
```

`EXPLAIN ANALYZE` **chạy câu lệnh thực**, nên không dùng tùy tiện cho `UPDATE/DELETE/INSERT` trên production. Với câu SELECT minh họa, bạn có thể quan sát kế hoạch scan, thời gian thực tế và buffer.

### 26.4. Tránh công thức lặp lại nhiều lần khi có thể chuẩn hóa

Một câu SQL phức tạp có thể tính:

```sql
ROUND(quantity * unit_price * (1 - discount_rate), 2)
```

ở nhiều vị trí SELECT, WHERE, ORDER BY. Có thể cân nhắc một derived table hoặc CTE để đặt tên biểu thức:

```sql
WITH calculated AS (
    SELECT
        line_id,
        sku,
        ROUND(
            quantity * unit_price
            * (1::NUMERIC - discount_rate),
            2
        ) AS net_amount
    FROM arithmetic_lab.order_lines
)
SELECT sku, net_amount
FROM calculated
WHERE net_amount >= 20::NUMERIC
ORDER BY net_amount DESC, sku;
```

CTE giúp dễ đọc và nhất quán công thức, nhưng **không mặc định** PostgreSQL sẽ materialize nó hay chỉ thực thi biểu thức đúng một lần. Với truy vấn chậm, cần xem plan và dữ liệu thực tế.

---

## 27. Các lỗi SQLSTATE và cách xử lý

Khi làm toán trong SQL, một số lỗi quan trọng:

| Tình huống | SQLSTATE thường gặp | Ý nghĩa |
| --- | --- | --- |
| Chia cho 0 | `22012` | `division_by_zero` |
| Giá trị số vượt miền kiểu | `22003` | `numeric_value_out_of_range` |
| Text không ép thành numeric được | `22P02` | `invalid_text_representation` |
| Vi phạm CHECK của bảng | `23514` | `check_violation` |
| Cột NOT NULL nhận NULL | `23502` | `not_null_violation` |

Ví dụ xử lý ở backend:

- Dữ liệu đầu vào sai format → thông báo validation rõ, không lộ SQL nội bộ.
- Tỷ lệ mẫu số 0 → trả “không xác định” nếu nghiệp vụ cho phép; không tự coi bằng 0.
- Overflow → xem lại kiểu dữ liệu/giới hạn và công thức trung gian.
- CHECK violation → sửa dữ liệu hoặc luồng nhập, không tắt constraint để né lỗi.
- Lỗi transaction → rollback hoặc dùng savepoint theo quy trình.

### 27.1. Lỗi trong transaction

```sql
BEGIN;

-- DỰ KIẾN LỖI:
SELECT 1 / 0;

-- Trong transaction PostgreSQL, các statement tiếp theo
-- thường không tiếp tục bình thường cho tới ROLLBACK.
ROLLBACK;
```

Khi học, nên chạy từng ví dụ **dự kiến lỗi** tách biệt, ở chế độ autocommit, hoặc dùng transaction/savepoint có kế hoạch. Không đưa câu lỗi vào script nạp dữ liệu chính rồi giả định mọi câu sau vẫn được thực thi.

### 27.2. Không phụ thuộc thông báo lỗi dạng text

Các driver thường cung cấp SQLSTATE riêng. Mã lỗi có cấu trúc bền vững hơn việc parse chuỗi “division by zero” hoặc “numeric field overflow”, vốn có thể khác theo phiên bản, ngôn ngữ hoặc wrapper.

Dù vậy, không nên trả toàn bộ thông báo PostgreSQL nguyên văn cho người dùng cuối nếu nó tiết lộ cấu trúc bảng hoặc dữ liệu nhạy cảm.

---

## 28. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`7 / 2` phải là 3.5.” | Hai số nguyên chia nhau trong PostgreSQL cho thương nguyên 3. |
| “Cast kết quả sang NUMERIC sẽ lấy lại phần lẻ.” | Nếu phần lẻ đã mất ở phép chia nguyên, cast sau không khôi phục. |
| “`NUMERIC` là chính xác vô hạn với mọi phép tính.” | Decimal hữu hạn chính xác, nhưng chia vô hạn/căn và ép scale vẫn có giới hạn. |
| “`DOUBLE PRECISION` đủ cho mọi số tiền vì có nhiều chữ số.” | Nó là floating point nhị phân, có thể sai số decimal. |
| “ROUND và TRUNC giống nhau.” | ROUND làm tròn; TRUNC cắt phần lẻ về 0. |
| “FLOOR(-3.7) là -3.” | FLOOR làm tròn xuống, nên là -4. |
| “CEIL(-3.7) là -4.” | CEIL làm tròn lên, nên là -3. |
| “ROUND luôn làm tròn .5 về số chẵn.” | ROUND với NUMERIC dùng quy tắc ties away from zero. |
| “ROUND(double,2) luôn sẵn có.” | PostgreSQL thường chỉ có chữ ký hai đối số cho NUMERIC. |
| “NUMERIC(10,2) tự từ chối giá có 3 số lẻ.” | PostgreSQL có thể làm tròn đầu vào tới scale 2. |
| “CAST sau phép nhân có thể sửa overflow.” | Phép nhân đã lỗi trước khi cast; cast toán hạng trước. |
| “MOD(-7,3) luôn là 2.” | Phần dư có thể âm theo quy tắc số chia/kiểu; cần chuẩn hóa nếu muốn dải không âm. |
| “SUM trên tập rỗng bằng 0.” | SUM trả NULL; COUNT(*) trả 0. |
| “Mẫu số 0 nên tự biến tỷ lệ thành 0.” | Không có mẫu số có thể nghĩa là tỷ lệ không xác định. |
| “COALESCE luôn sửa dữ liệu tốt hơn.” | Nó có thể che giấu dữ liệu thiếu hoặc lỗi nghiệp vụ. |
| “Nếu FLOAT hiển thị 0.3 thì lưu chính xác 0.3.” | Biểu diễn nhị phân vẫn có thể là xấp xỉ. |
| “So sánh FLOAT bằng = luôn an toàn.” | Sai số biểu diễn/tính toán có thể gây khác biệt. |
| “Chọn epsilon cực nhỏ sẽ luôn chính xác.” | Epsilon cần theo đơn vị và thang đo; gần 0 và giá trị lớn khác nhau. |
| “NaN không bao giờ thỏa so sánh trong PostgreSQL.” | PostgreSQL có quy tắc so sánh NaN đặc thù để phục vụ sort/index. |
| “ROUND từng dòng và ROUND tổng là tương đương.” | Hai điểm làm tròn có thể cho hai kết quả khác nhau. |
| “Giá đơn vị luôn có 2 số lẻ.” | Đơn giá, tỷ giá và số lượng có thể cần scale khác. |
| “Random() phù hợp tạo token bảo mật.” | Cần cryptographic RNG riêng. |
| “Một cột NUMERIC đúng type nghĩa là mọi phép tính tài chính đúng.” | Cần đúng đơn vị, chính sách rounding, transaction và validation. |

---

## 29. Bài tập thực hành

### Bài 1 — Toán tử và thứ tự ưu tiên

Dự đoán kết quả:

```sql
SELECT
    8 + 3 * 4 AS a,
    (8 + 3) * 4 AS b,
    17 / 5 AS c,
    17 % 5 AS d;
```

Giải thích khác nhau giữa `a` và `b`, cũng như thương nguyên và phần dư.

### Bài 2 — Chia nguyên và cast

Chạy:

```sql
SELECT
    7 / 2 AS a,
    (7 / 2)::NUMERIC AS b,
    7::NUMERIC / 2 AS c,
    (-7)::INTEGER / 2 AS d;
```

Giải thích vì sao `a` và `b` bằng 3, `c` bằng 3.5 và `d` bằng -3.

### Bài 3 — Tính tỷ lệ thành công

Có 7 đơn thành công trên 12 đơn. Viết truy vấn PostgreSQL tính tỷ lệ phần trăm tới hai chữ số sau dấu thập phân.

Gợi ý:

```sql
ROUND(7::NUMERIC / 12::NUMERIC * 100, 2)
```

Vì sao `7 / 12 * 100` có thể sai?

### Bài 4 — Phân biệt ROUND, TRUNC, FLOOR và CEIL

Với các giá trị 3.7, -3.7, 2.5, -2.5, hãy lập bảng kết quả bốn hàm.

Đặc biệt, giải thích vì sao `TRUNC(-3.7)` khác `FLOOR(-3.7)`.

### Bài 5 — ROUND với scale âm

Tính:

```sql
SELECT
    ROUND(12345.678::NUMERIC, -1),
    ROUND(12345.678::NUMERIC, -2),
    TRUNC(12345.678::NUMERIC, -2);
```

Giải thích tại sao ROUND về hàng trăm khác TRUNC về hàng trăm.

### Bài 6 — NUMERIC và floating-point

So sánh:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC) = 0.3::NUMERIC
        AS decimal_equal,
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
         = 0.3::DOUBLE PRECISION AS float_equal;
```

Sau đó dùng `ABS(a-b) < epsilon` để kiểm tra gần bằng nhau trong bài toán đo lường.

Tại sao không nên dùng epsilon tùy tiện để đối soát tiền thanh toán cuối cùng?

### Bài 7 — Quy tắc làm tròn dấu âm

Chạy:

```sql
SELECT
    ROUND( 1.235::NUMERIC, 2),
    ROUND(-1.235::NUMERIC, 2),
    TRUNC(-1.235::NUMERIC, 2);
```

Giải thích làm tròn số âm đúng giữa hai mức ở NUMERIC và sự khác biệt với cắt phần lẻ.

### Bài 8 — Numeric precision và overflow

Thử:

```sql
SELECT
    999.99::NUMERIC(5,2) AS valid;
```

Sau đó chạy riêng:

```sql
-- DỰ KIẾN LỖI.
SELECT 1000.00::NUMERIC(5,2);
```

Vì sao không đủ chữ số phần nguyên? Điều gì xảy ra nếu nhập `999.995`?

### Bài 9 — Tràn số trước khi cast

So sánh:

```sql
-- DỰ KIẾN LỖI.
SELECT (2000000000::INTEGER * 2::INTEGER)::BIGINT;
```

và:

```sql
SELECT 2000000000::BIGINT * 2::BIGINT;
```

Giải thích vì sao phải cast **trước phép tính**.

### Bài 10 — Chia cho 0 và NULLIF

Viết truy vấn tính `sales / visits` với:

- sales = 100, visits = 20;
- sales = 100, visits = 0;
- sales = 0, visits = 0.

Dùng `NULLIF(visits,0)` để tránh lỗi và giải thích tại sao hai trường hợp mẫu số bằng 0 nên được xem xét riêng về nghiệp vụ.

### Bài 11 — SUM và AVG với NULL

Bảng `arithmetic_lab.sensor_readings` có một `reading_value NULL`. So sánh:

```sql
SELECT
    COUNT(*),
    COUNT(reading_value),
    SUM(reading_value),
    AVG(reading_value)
FROM arithmetic_lab.sensor_readings;
```

Vì sao COUNT(*) khác COUNT(column)? Nếu lọc ra tập không có hàng thì SUM trả gì?

### Bài 12 — Làm tròn thuế theo dòng và theo tổng

Hai dòng hàng đều có giá 0.05 USD, thuế suất giả định 10%. Tính:

1. Round thuế từng dòng về 2 chữ số rồi cộng.
2. Cộng cơ sở rồi nhân thuế và round cuối.

Đối chiếu 0.02 và 0.01, giải thích vì sao đây là quyết định **quy tắc nghiệp vụ**, không phải lỗi của NUMERIC.

### Bài 13 — Đơn giá dưới 0.01

Sản phẩm có đơn giá 0.0150 USD và số lượng 100. Viết SQL theo hai cách:

1. Làm tròn đơn giá tới 2 chữ số trước khi nhân.
2. Nhân số lượng trước rồi làm tròn kết quả.

So sánh 2.00 và 1.50, sau đó nêu cách chọn scale lưu unit_price.

### Bài 14 — Xử lý NaN và Infinity

Dùng literal:

```sql
SELECT
    'NaN'::DOUBLE PRECISION,
    'Infinity'::DOUBLE PRECISION,
    '-Infinity'::DOUBLE PRECISION;
```

Giải thích vì sao hệ thống đo lường/tài chính cần chính sách chấp nhận hoặc từ chối riêng những giá trị đặc biệt.

### Bài 15 — MOD số âm

Chạy:

```sql
SELECT
    MOD(-7,3),
    MOD(7,-3),
    MOD(MOD(-7,3)+3,3);
```

Phân biệt phần dư thông thường với phần dư đã chuẩn hóa về khoảng không âm cho số chia dương.

### Bài 16 — Tính tổng hóa đơn qua CTE

Từ bảng `arithmetic_lab.order_lines`, tạo CTE `line_amounts` chứa:

- SKU.
- Gross = quantity × unit_price.
- Discount = gross × discount_rate.
- Net = ROUND(gross × (1 - discount_rate), 2).

Sau đó SUM(net) để tính tổng. Viết thêm phiên bản SUM(gross × (1 - discount_rate)) rồi ROUND một lần. Hai kết quả có bắt buộc bằng nhau với mọi dataset không?

### Bài 17 — Lựa chọn phép toán cho dữ liệu đo

Một cảm biến đo giá trị thực 23.50001 và kỳ vọng 23.5. Thiết kế kiểm tra bằng:

- Dung sai tuyệt đối 0.001.
- Dung sai tương đối 0.01%.
- Cách phối hợp hai ngưỡng.

Giải thích vì sao không thể chọn một epsilon chung cho mọi đơn vị đo.

### Bài 18 — Thiết kế kiểu dữ liệu

Hãy chọn kiểu và scale phù hợp cho:

1. Số lượng sản phẩm nguyên.
2. Cân nặng có ba chữ số thập phân.
3. Đơn giá có bốn chữ số thập phân.
4. Số tiền thanh toán USD đã chốt tới cent.
5. Tỷ giá có nhiều chữ số lẻ.
6. Số tiền tính theo minor units.
7. Nhiệt độ cảm biến cho thống kê xấp xỉ.

Nêu ảnh hưởng của overflow, rounding và đơn vị dữ liệu cho từng lựa chọn.

### Bài 19 — Parse text trước khi lưu numeric

Đầu vào từ API:

```text
19.99
19.999
-1.00
abc
0
```

Chính sách chỉ cho phép số không âm, tối đa hai chữ số lẻ. Phân loại đầu vào hợp lệ/không hợp lệ và giải thích tại sao chỉ định nghĩa `NUMERIC(18,2)` không đủ từ chối `19.999`.

### Bài 20 — Tối ưu biểu thức

Dựng index trên:

```sql
CREATE INDEX idx_order_lines_rounded_gross
ON arithmetic_lab.order_lines ((ROUND(line_gross,2)));
```

Dùng `EXPLAIN` xem kế hoạch truy vấn với điều kiện `ROUND(line_gross,2) >= 20`. Tại sao PostgreSQL có thể vẫn chọn sequential scan trên bảng chỉ có năm hàng?

---

## 30. Checklist thiết kế phép tính an toàn

| Câu hỏi | Hành động cần xác định |
| --- | --- |
| Hai toán hạng là INTEGER hay NUMERIC? | Kiểm tra chia nguyên và thời điểm cast |
| Phép tính có thể overflow? | Ước lượng miền trung gian, nâng kiểu trước khi cộng/nhân |
| Có thể có mẫu số bằng 0? | Kiểm tra/NULLIF và chính sách giá trị không xác định |
| Đầu vào có thể NULL? | Phân biệt thiếu dữ liệu và số 0 |
| Có tiền tệ hoặc tỷ lệ? | Xác định đơn vị, currency và cách biểu diễn tỷ lệ |
| Có cần decimal exact? | Dùng NUMERIC hoặc integer minor units |
| Có tính toán floating-point? | Xác định sai số chấp nhận và tính hữu hạn |
| Có so sánh gần bằng? | Thiết kế tolerance tuyệt đối/tương đối theo miền |
| Có ROUND? | Ghi rõ scale, tie rule và thời điểm làm tròn |
| Có giá trị âm? | Phân biệt ROUND/TRUNC/FLOOR/CEIL |
| Có tính thuế/chiết khấu? | Quyết định rounding từng dòng hay toàn tổng |
| Có đơn giá nhỏ hơn cent? | Giữ precision trung gian, tránh round quá sớm |
| Có tỷ giá? | Giữ đủ chữ số và lưu rate theo thời điểm |
| Có giới hạn NUMERIC(p,s)? | Kiểm tra overflow cả sau rounding |
| Có NaN/Infinity? | Xác thực theo chính sách dữ liệu |
| Có nhập từ CSV/JSON? | Validate format/range trước cast |
| Có ứng dụng Java? | BigDecimal từ string và RoundingMode phù hợp |
| Có hệ thống JavaScript? | Xem miền safe integer và JSON contract |
| Có aggregate SUM/AVG? | Xem kiểu đầu ra, NULL và sai số cộng dồn |
| Query chậm do tính toán? | Xem EXPLAIN, index, biểu thức và thống kê |
| Có yêu cầu kiểm toán? | Lưu snapshot công thức, rounding policy, unit và giá trị đã chốt |
| Có thao tác cập nhật số dư? | Dùng transaction, constraint, concurrency và idempotency |

## Kết luận

Hàm số học trong PostgreSQL chỉ thực sự đáng tin cậy khi đi cùng **kiểu dữ liệu đúng, công thức đúng và quy tắc làm tròn rõ ràng**.

Những nguyên tắc quan trọng nhất:

- `+`, `-`, `*`, `/`, `%` và các hàm toán học phải được sử dụng với hiểu biết về kiểu toán hạng. **Chia hai số nguyên có thể làm mất phần lẻ**, và **cast sau phép tính không cứu được kết quả đã cắt hoặc đã tràn**.
- `ROUND`, `TRUNC`, `FLOOR`, `CEIL` là những phép biến đổi khác nhau; số âm và trường hợp đúng giữa hai mức làm tròn cần được kiểm tra cẩn thận.
- `NUMERIC` phù hợp khi cần số thập phân chính xác trong phạm vi cho phép, nhưng `NUMERIC(p,s)` có thể làm tròn lúc lưu và những phép tính như chia vô hạn vẫn cần precision hữu hạn.
- `REAL/DOUBLE PRECISION` là số nhị phân gần đúng; dùng cho đo lường, khoa học hoặc thống kê khi sai số được chấp nhận, không mặc định dùng làm tiền cuối cùng cần đối soát.
- `NULLIF` có thể giúp tránh lỗi chia cho 0, nhưng giá trị “không xác định” không tự đồng nghĩa 0. `COALESCE` cần thể hiện chính sách nghiệp vụ có chủ đích.
- Overflow, giá trị đầu vào không parse được, NaN và Infinity phải được nhận diện và xử lý phù hợp, không che giấu bằng việc cast hoặc làm tròn tùy tiện.
- **Làm tròn ở đâu** quan trọng không kém **làm tròn thế nào**; tiền, thuế, đơn giá và tỷ giá thường yêu cầu những scale khác nhau và quy trình được đối soát.

Khi tách rõ **representation**, **tính toán trung gian**, **validation**, **rounding policy** và **giá trị cuối**, bạn có thể xây dựng truy vấn PostgreSQL chính xác, giải thích được kết quả và tránh những sai lệch nhỏ tích lũy thành lỗi nghiệp vụ lớn.
