# Biểu thức số học và ảnh hưởng của kiểu dữ liệu trong SQL

Trong SQL, biểu thức số học xuất hiện ở khắp nơi: tính thành tiền của một dòng hàng, tính tỷ lệ giảm giá, chuyển đổi đơn vị, tính điểm trung bình, chia số lượng sản phẩm thành các lô hoặc lập báo cáo doanh thu. Phép tính trông đơn giản như `5 / 2` có thể cho **kết quả khác nhau tùy kiểu dữ liệu của toán hạng và hệ quản trị cơ sở dữ liệu (DBMS)**.

Bài này giải thích cách SQL xử lý **cộng, trừ, nhân, chia, lấy phần dư, độ ưu tiên toán tử, NULL, làm tròn, giới hạn số và chuyển kiểu**, đồng thời hướng dẫn chọn kiểu dữ liệu để tính tiền, số lượng và chỉ số thống kê. Các ví dụ thực hành chính dành cho **PostgreSQL**; phần đối chiếu cuối bài nêu khác biệt đáng chú ý với MySQL, SQL Server và SQLite.

> Quy tắc xuyên suốt: **xem cả kiểu dữ liệu đầu vào và kiểu dữ liệu kết quả**. Chỉ nhìn giá trị các chữ số trong câu SQL chưa đủ để suy ra cách DBMS thực hiện phép tính.

## 1. Biểu thức số học là gì?

Một **biểu thức (expression)** là tổ hợp giá trị, cột, toán tử hoặc hàm mà DBMS có thể đánh giá để tạo ra một giá trị. Ví dụ:

```sql
SELECT
    10 + 3 AS addition,
    10 - 3 AS subtraction,
    10 * 3 AS multiplication,
    10 / 3 AS division,
    10 % 3 AS remainder;
```

Trong **PostgreSQL**, kết quả ví dụ là:

| Biểu thức | Giá trị | Ý nghĩa |
|---|---:|---|
| `10 + 3` | 13 | Phép cộng |
| `10 - 3` | 7 | Phép trừ |
| `10 * 3` | 30 | Phép nhân |
| `10 / 3` | 3 | **Phép chia hai số nguyên** cho phần nguyên |
| `10 % 3` | 1 | Phần dư |

Ký hiệu `+`, `-`, `*` và `/` quen thuộc với nhiều DBMS. Với phép lấy phần dư, PostgreSQL hỗ trợ `%` và hàm `MOD`; một số DBMS khác có cách viết hoặc quy tắc riêng.

Biểu thức có thể dùng ở nhiều nơi trong một câu truy vấn:

```sql
SELECT
    product_id,
    quantity,
    unit_price,
    quantity * unit_price AS line_total
FROM order_items
WHERE quantity * unit_price >= 100000
ORDER BY line_total DESC;
```

Truy vấn trên **giả định đã có bảng** `order_items(product_id, quantity, unit_price)`. Nó tính `line_total` trong `SELECT`, dùng phép tính tương tự để lọc ở `WHERE`, rồi sắp xếp theo bí danh trong `ORDER BY`.

Khi kiểu dữ liệu là số, các toán tử số học thường tạo kết quả số. Nhưng kiểu số có nhiều nhóm với **độ lớn, độ chính xác và quy tắc chuyển đổi khác nhau**.

## 2. Những nhóm kiểu số ảnh hưởng đến phép tính

Các DBMS có tên kiểu hơi khác nhau, nhưng thường có ba nhóm chính:

| Nhóm | Ví dụ trong PostgreSQL | Đặc điểm | Phù hợp với |
|---|---|---|---|
| **Số nguyên** | `SMALLINT`, `INTEGER`/`INT`, `BIGINT` | Không có phần thập phân; giới hạn phạm vi | Số lượng, số thứ tự, số lượt |
| **Số thập phân chính xác** | `NUMERIC(p, s)`, `DECIMAL(p, s)` | Lưu số thập phân theo độ chính xác xác định; hữu ích khi cần tính toán thập phân có kiểm soát | Tiền tệ, thuế, tỷ lệ, số liệu nghiệp vụ |
| **Số dấu phẩy động xấp xỉ** | `REAL`, `DOUBLE PRECISION` | Biểu diễn nhị phân xấp xỉ, phạm vi rộng nhưng không biểu diễn chính xác mọi phân số thập phân | Đo lường, khoa học, số liệu chấp nhận sai số |

### 2.1. Số nguyên không phải số thực có “.0” ẩn

Trong PostgreSQL, `5` và `2` thường được suy luận là số nguyên. Do đó:

```sql
SELECT
    5 / 2 AS integer_division,
    5.0 / 2 AS decimal_division,
    CAST(5 AS NUMERIC) / 2 AS explicit_decimal_division;
```

Kết quả tương ứng là **2**, **2.5**, **2.5**. Việc đổi **một toán hạng** sang `NUMERIC` làm thay đổi phép chia được sử dụng.

Không thể giả định mọi hệ quản trị cho cùng kết quả với `5 / 2`; phần so sánh DBMS ở cuối bài sẽ đối chiếu.

### 2.2. Số chính xác và số xấp xỉ

Ví dụ PostgreSQL:

```sql
SELECT
    0.1::NUMERIC + 0.2::NUMERIC AS exact_decimal_sum,
    0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION
        AS approximate_binary_sum;
```

Trong biểu diễn `NUMERIC`, phép cộng thập phân `0.1 + 0.2` cho đúng giá trị thập phân `0.3` theo độ chính xác đang dùng. Trong biểu diễn `DOUBLE PRECISION` nhị phân, hai giá trị `0.1` và `0.2` **không thể được biểu diễn chính xác tuyệt đối**, vì vậy kết quả có thể mang sai số rất nhỏ tùy cách hiển thị.

Đối với phép so sánh đòi hỏi đúng tuyệt đối, không nên dùng `DOUBLE PRECISION` rồi trông chờ các giá trị được tính riêng rẽ sẽ bằng nhau từng bit. Với phép đo khoa học, người ta thường đánh giá sai số trong **ngưỡng chấp nhận được** thay vì buộc hai giá trị dấu phẩy động phải bằng nhau tuyệt đối.

### 2.3. Kiểu dữ liệu là một phần của thiết kế nghiệp vụ

Cùng là số `100`, nhưng:

- `quantity INTEGER` nghĩa là **100 đơn vị**, không có phần lẻ.
- `weight_kg NUMERIC(12, 3)` nghĩa là **100.000 kg**, cần giữ ba chữ số sau dấu thập phân theo thiết kế.
- `unit_price NUMERIC(12, 2)` nghĩa là **100.00 đơn vị tiền**.
- `sensor_temperature DOUBLE PRECISION` nghĩa là phép đo có thể mang sai số xấp xỉ.

Nếu chọn sai kiểu, việc hiển thị hoặc phép tính có thể cho kết quả trái ý nghiệp vụ dù câu SQL không báo lỗi.

## 3. Thứ tự ưu tiên toán tử và dấu ngoặc

Phần lớn phép tính SQL tuân theo quy tắc quen thuộc: **nhân/chia/lấy dư thường được thực hiện trước cộng/trừ**; các toán tử có cùng mức ưu tiên thường được đánh giá theo quy tắc của DBMS.

Trong PostgreSQL:

```sql
SELECT
    2 + 3 * 4 AS without_parentheses,
    (2 + 3) * 4 AS with_parentheses;
```

Kết quả là `14` và `20`.

Một ví dụ tính giá trị đơn hàng:

```sql
SELECT
    3 * 120000 - 20000 AS correct_amount,
    3 * (120000 - 20000) AS different_amount;
```

- `3 * 120000 - 20000` = **340000**, vì giảm 20000 cho **toàn bộ đơn**.
- `3 * (120000 - 20000)` = **300000**, vì giảm 20000 cho **mỗi sản phẩm** trước khi nhân số lượng.

Hai câu đều hợp lệ nhưng có ý nghĩa hoàn toàn khác nhau. Dấu ngoặc không chỉ phục vụ trình bày: nó xác định **cách nhóm phép tính**.

### 3.1. Dấu âm và âm số

Trong PostgreSQL, dấu `-` còn là toán tử âm một ngôi:

```sql
SELECT
    -5 AS negative_number,
    -(-5) AS positive_number,
    10 + (-3) AS add_negative,
    10 - (-3) AS subtract_negative;
```

Kết quả lần lượt là `-5`, `5`, `7`, `13`.

Đối với các biểu thức phức tạp có lũy thừa, phép chia, kiểu dữ liệu hoặc toán tử riêng của DBMS, **dùng ngoặc rõ ràng** thay vì dựa vào việc nhớ chính xác mọi mức ưu tiên.

### 3.2. Tại sao định dạng cũng giúp kiểm tra ý nghĩa?

```sql
SELECT
    order_id,
    quantity * unit_price
        - COALESCE(discount_amount, 0) AS net_amount
FROM order_items;
```

Nếu nghiệp vụ yêu cầu một **tỷ lệ giảm giá theo phần trăm** chứ không phải số tiền giảm trực tiếp, biểu thức sẽ khác:

```sql
SELECT
    order_id,
    quantity * unit_price
        * (1 - COALESCE(discount_percent, 0) / 100.0)
        AS net_amount
FROM order_items;
```

Ở đây `100.0` được chọn có chủ đích để phép chia không rơi vào chia nguyên trong PostgreSQL. Cả tên cột và cách đặt ngoặc đều giúp người đọc nhận ra quy tắc tính tiền.

## 4. Chia số nguyên là nguồn lỗi phổ biến

Trong PostgreSQL, hai toán hạng kiểu số nguyên thực hiện phép chia nguyên:

```sql
SELECT
    7 / 2 AS positive_quotient,
    -7 / 2 AS negative_quotient,
    7 / -2 AS negative_divisor;
```

Kết quả tương ứng là `3`, `-3`, `-3`: phần lẻ bị loại theo hướng **về 0**, không phải luôn làm tròn xuống âm vô cùng.

Điểm khác biệt giữa chia nguyên và làm tròn xuống thể hiện rõ với số âm:

| Phép toán | Kết quả PostgreSQL |
|---|---:|
| `7 / 2` (integer) | 3 |
| `-7 / 2` (integer) | -3 |
| `FLOOR(-7.0 / 2)` | -4 |
| `CEIL(-7.0 / 2)` | -3 |

`FLOOR` và `CEIL` hoạt động trên một giá trị số có phần lẻ; chúng không đồng nghĩa với cách chia nguyên cho mọi số âm.

### 4.1. Ép kiểu **trước** khi chia

Để giữ phần thập phân, ép kiểu ít nhất một toán hạng trước phép chia:

```sql
SELECT
    CAST(7 AS NUMERIC) / 2 AS ratio_a,
    7::NUMERIC / 2 AS ratio_b,
    7 / 2.0 AS ratio_c;
```

Trong PostgreSQL, cả ba đều có giá trị số bằng `3.5`. Ký hiệu `::NUMERIC` là phép ép kiểu riêng của PostgreSQL; `CAST(... AS NUMERIC)` là cách viết SQL chuẩn hơn.

**Đặt phép ép kiểu sau phép chia là quá muộn:**

```sql
SELECT
    CAST(7 / 2 AS NUMERIC) AS cast_after_division,
    CAST(7 AS NUMERIC) / 2 AS cast_before_division;
```

- `CAST(7 / 2 AS NUMERIC)`: phép chia nguyên đã cho `3`, rồi mới chuyển `3` sang `NUMERIC`.
- `CAST(7 AS NUMERIC) / 2`: chuyển `7` sang `NUMERIC` trước, sau đó phép chia có kết quả `3.5`.

Đây là lỗi thường gặp khi tính **tỷ lệ hoàn thành, tỷ lệ chuyển đổi, trung bình hoặc phần trăm**.

### 4.2. Ví dụ tỷ lệ phần trăm

Giả sử có `successful_requests = 83` và `total_requests = 200`:

```sql
SELECT
    83 / 200 * 100 AS wrong_percent,
    83::NUMERIC / 200 * 100 AS correct_percent,
    100.0 * 83 / 200 AS also_correct;
```

Trong PostgreSQL:

- `83 / 200 * 100` = **0**, vì `83 / 200` được chia nguyên thành `0` trước khi nhân `100`.
- Hai biểu thức còn lại có giá trị **41.5**.

Một công thức có thể tái sử dụng:

```sql
SELECT
    successful_requests,
    total_requests,
    100.0 * successful_requests
        / NULLIF(total_requests, 0) AS success_percent
FROM request_statistics;
```

Bảng `request_statistics` được giả định có các cột nêu trên. `NULLIF(total_requests, 0)` ngăn lỗi chia cho 0 bằng cách biến mẫu số bằng 0 thành `NULL`. Khi mẫu số bằng 0, kết quả tỷ lệ là `NULL`, thể hiện **chưa xác định**, không mặc nhiên bằng 0%.

## 5. Kiểu NUMERIC/DECIMAL: precision và scale

Trong PostgreSQL, `NUMERIC(p, s)` hoặc `DECIMAL(p, s)` khai báo:

- **Precision (`p`):** tổng số chữ số thập phân có ý nghĩa được phép lưu.
- **Scale (`s`):** số chữ số sau dấu thập phân được giữ theo khai báo.

Ví dụ:

```sql
CREATE TABLE lesson137_prices (
    product_id INTEGER PRIMARY KEY,
    unit_price NUMERIC(10, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    discount_percent NUMERIC(5, 2) NOT NULL DEFAULT 0
);
```

`NUMERIC(10, 2)` có tối đa **10 chữ số**, trong đó **2 chữ số sau dấu thập phân**; với các giá trị hữu hạn thông thường, phần nguyên có thể chứa tối đa 8 chữ số. `NUMERIC(5, 2)` phù hợp để biểu diễn các tỷ lệ dạng 12.50 hoặc 100.00, nhưng nếu dùng cho phần trăm giảm giá thực tế, còn nên thêm ràng buộc `CHECK (discount_percent BETWEEN 0 AND 100)` nếu nghiệp vụ yêu cầu.

### 5.1. Giá trị được làm tròn theo scale khi lưu

Trong PostgreSQL, việc ép hoặc ghi một giá trị nhiều chữ số thập phân vào `NUMERIC(10,2)` sẽ **làm tròn tới 2 chữ số** trước khi kiểm tra có vừa precision hay không.

Ví dụ có thể thực hiện:

```sql
SELECT
    CAST(12.345 AS NUMERIC(10, 2)) AS rounded_for_scale,
    CAST(12.344 AS NUMERIC(10, 2)) AS another_rounded_value;
```

Các giá trị tương ứng là **12.35** và **12.34** theo quy tắc làm tròn của `NUMERIC` PostgreSQL.

Điểm rất quan trọng: **scale của cột ảnh hưởng giá trị được lưu**, nhưng **không có nghĩa mọi biểu thức với cột đó đều chỉ giữ hai chữ số sau dấu thập phân**.

```sql
SELECT
    12.35::NUMERIC(10, 2) / 3 AS division_result,
    ROUND(12.35::NUMERIC(10, 2) / 3, 2) AS rounded_result;
```

Phép chia `NUMERIC` có thể cho nhiều chữ số thập phân; `ROUND(..., 2)` chủ động làm tròn kết quả để hiển thị hoặc dùng theo nghiệp vụ.

### 5.2. Khi giá trị vượt phạm vi khai báo

Một số nguyên có thể vượt giới hạn của `INTEGER`; giá trị thập phân có thể vượt `NUMERIC(p,s)`. PostgreSQL sẽ báo lỗi thay vì tùy ý mở rộng kiểu cột để lưu giá trị không hợp lệ.

Ví dụ cho thấy giới hạn kiểu cột:

```sql
-- Giá trị 123456789.12 có 9 chữ số phần nguyên;
-- không thể lưu trong NUMERIC(10,2) chỉ chứa tối đa 8 chữ số phần nguyên.
SELECT CAST(123456789.12 AS NUMERIC(10, 2));
```

Đoạn trên **cố ý gây lỗi số vượt phạm vi**, nên chỉ chạy riêng khi muốn quan sát thông báo. Nếu cần chứa giá trị lớn hơn, chọn precision phù hợp từ bước thiết kế, không cố dựa vào phép ép kiểu ngầm để tránh giới hạn.

### 5.3. Tiền tệ: cần nghĩ tới thời điểm làm tròn

Giả sử một đơn hàng có 3 sản phẩm, đơn giá chính xác cho phép có nhiều hơn hai chữ số thập phân hoặc cần áp dụng thuế, giảm giá:

- Làm tròn **đơn giá trước khi nhân** có thể khác làm tròn **tổng sau khi nhân**.
- Làm tròn **từng dòng rồi cộng** có thể khác làm tròn **toàn bộ tổng**.
- Phải xác định đơn vị tiền tối thiểu, chính sách làm tròn và quy tắc phân bổ chênh lệch theo nghiệp vụ.

Ví dụ PostgreSQL:

```sql
SELECT
    3 * ROUND(1.005::NUMERIC, 2) AS rounded_unit_first,
    ROUND(3 * 1.005::NUMERIC, 2) AS rounded_total_last;
```

Ở đây:

- Làm tròn mỗi đơn giá trước: `1.005` thành `1.01`; nhân 3 cho **3.03**.
- Nhân trước: `3 * 1.005 = 3.015`; làm tròn hai chữ số thành **3.02**.

Cả hai cách đều có thể phù hợp trong bối cảnh riêng, nhưng **không thể hoán đổi mà vẫn bảo toàn số tiền**. Quy tắc làm tròn phải đến từ yêu cầu kế toán/thanh toán cụ thể, không phải lựa chọn tùy tiện của lập trình viên.

## 6. ROUND, TRUNC, FLOOR, CEIL: cách thay đổi giá trị số

Các hàm thường gặp trong PostgreSQL:

| Hàm | Ý nghĩa chính | Ví dụ | Kết quả |
|---|---|---|---|
| `ROUND(x, n)` | Làm tròn đến `n` chữ số thập phân (với `NUMERIC`) | `ROUND(12.345::NUMERIC, 2)` | 12.35 |
| `TRUNC(x, n)` | Cắt bỏ sau `n` chữ số, không làm tròn | `TRUNC(12.345::NUMERIC, 2)` | 12.34 |
| `FLOOR(x)` | Số nguyên lớn nhất không vượt `x` | `FLOOR(-2.3)` | -3 |
| `CEIL(x)` / `CEILING(x)` | Số nguyên nhỏ nhất không nhỏ hơn `x` | `CEIL(-2.3)` | -2 |
| `ABS(x)` | Giá trị tuyệt đối | `ABS(-25)` | 25 |

Ví dụ có thể chạy trên PostgreSQL:

```sql
SELECT
    ROUND(123.456::NUMERIC, 2) AS round_two_digits,
    TRUNC(123.456::NUMERIC, 2) AS trunc_two_digits,
    FLOOR(-2.3::NUMERIC) AS floor_negative,
    CEIL(-2.3::NUMERIC) AS ceil_negative,
    ABS(-25) AS absolute_value;
```

Một số lưu ý:

1. Trong PostgreSQL, dạng **`ROUND(value, digits)`** dùng cho `NUMERIC`. Nếu đầu vào là `DOUBLE PRECISION` và cần truyền số chữ số, có thể phải `CAST(... AS NUMERIC)`; không mặc định mọi overload đều tồn tại.
2. `ROUND` và `TRUNC` khác nhau, nhất là khi chữ số bị bỏ ≥ 5.
3. `FLOOR(-2.3) = -3`, còn phép chia nguyên `-7 / 2 = -3` trong PostgreSQL; với dữ liệu số âm khác, cách làm tròn của hai cơ chế không nên bị coi là cùng phép toán.
4. Các quy tắc xử lý giá trị ở đúng điểm giữa như `2.5` và `-2.5` có thể khác giữa kiểu `NUMERIC` và kiểu dấu phẩy động. PostgreSQL thường làm tròn `NUMERIC` ở điểm giữa **ra xa 0**, còn kết quả làm tròn float có thể chịu quy tắc nền tảng, thường là “ties to even”. Không suy luận quy tắc chung từ một kiểu sang kiểu khác.

### 6.1. Làm tròn ở SELECT khác làm tròn lúc lưu

```sql
SELECT ROUND(unit_price * quantity, 2) AS display_total
FROM lesson137_prices;
```

Cách này làm tròn **giá trị được trả về trong truy vấn**. Nó không tự cập nhật giá trị của cột `unit_price`. Ngược lại, khi kết quả được `INSERT` vào một cột `NUMERIC(p,2)`, DBMS có thể ép scale theo kiểu của cột lưu trữ.

## 7. Phép lấy phần dư, phép chia hết và quy tắc dấu

Lấy phần dư giúp phân nhóm theo chu kỳ, xác định số chẵn/lẻ, chia dữ liệu thành các nhóm hoặc kiểm tra lượng dư khi đóng gói.

Trong PostgreSQL:

```sql
SELECT
    10 % 3 AS remainder_operator,
    MOD(10, 3) AS remainder_function,
    10 % 2 AS even_check,
    11 % 2 AS odd_check;
```

Kết quả tương ứng là `1`, `1`, `0`, `1`.

Ứng dụng kiểm tra số chẵn:

```sql
SELECT
    number_value,
    CASE
        WHEN number_value % 2 = 0 THEN 'Chẵn'
        ELSE 'Lẻ'
    END AS parity
FROM (
    VALUES (2), (5), (8), (11)
) AS numbers(number_value);
```

Với số âm, **phần dư không phải ở mọi DBMS đều là giá trị không âm**. PostgreSQL có kết quả ví dụ:

```sql
SELECT
    -10 % 3 AS negative_dividend,
    10 % -3 AS negative_divisor;
```

Kết quả là `-1` và `1`. Điều này phản ánh quy tắc phần dư dựa trên phép chia nguyên; nếu nghiệp vụ cần kết quả nằm trong `[0, n)` với `n > 0` (ví dụ xoay vòng chỉ số mảng), có thể chuẩn hóa:

```sql
SELECT MOD(MOD(-10, 3) + 3, 3) AS nonnegative_modulo;
```

Kết quả là `2` trong PostgreSQL. Kỹ thuật cộng rồi lấy dư lần nữa hữu ích với `n` dương; không áp dụng máy móc cho mẫu số `0` hoặc giá trị đầu vào có đặc tính khác.

## 8. NULL và phép toán số học

`NULL` thường có nghĩa là **chưa biết hoặc không áp dụng**. Trong các biểu thức số học thông thường, nếu một toán hạng là `NULL`, kết quả cũng là `NULL`:

```sql
SELECT
    100 + NULL AS addition_with_null,
    100 * NULL AS multiplication_with_null,
    100 / NULL AS division_with_null;
```

Đây không phải lỗi chia cho 0: `NULL` là giá trị **không xác định**, khác với số `0`.

### 8.1. COALESCE chỉ nên dùng khi NULL có ý nghĩa dự phòng rõ ràng

Giả sử `discount_amount` là số tiền giảm và quy ước nghiệp vụ là **không nhập giảm giá nghĩa là không giảm**:

```sql
SELECT
    quantity * unit_price
        - COALESCE(discount_amount, 0) AS payable_amount
FROM order_items;
```

`COALESCE(discount_amount, 0)` trả số giảm giá nếu đã có, nếu `NULL` thì dùng `0`.

Nhưng nếu `NULL` nghĩa là “chưa được duyệt mức giảm giá”, cách thay bằng 0 có thể làm báo cáo hiểu sai dữ liệu. Khi đó, giữ kết quả `NULL`, thêm cột trạng thái hoặc xử lý tại tầng nghiệp vụ sẽ hợp lý hơn.

### 8.2. Chia cho 0: dùng NULLIF khi mẫu số có thể bằng 0

Trong PostgreSQL, chia số thông thường cho `0` là lỗi:

```sql
-- Cố ý gây lỗi; chỉ chạy riêng để quan sát.
SELECT 100 / 0;
```

Nếu mẫu số có thể bằng 0, dùng `NULLIF`:

```sql
SELECT
    100::NUMERIC / NULLIF(0, 0) AS safe_ratio,
    100::NUMERIC / NULLIF(4, 0) AS valid_ratio;
```

`NULLIF(0,0)` trở thành `NULL` nên `safe_ratio` trả `NULL`; `NULLIF(4,0)` giữ `4` nên `valid_ratio` = `25`.

Không tự coi tỷ lệ có mẫu số `0` bằng `0%`; trong toán học, tỷ lệ đó **không xác định**. Nếu giao diện muốn hiển thị “N/A”, có thể giữ SQL trả `NULL` rồi định dạng ngoài ứng dụng. Nếu bắt buộc quy đổi thành 0 theo quy tắc báo cáo, hãy làm rõ điều đó:

```sql
SELECT
    COALESCE(100::NUMERIC / NULLIF(0, 0), 0) AS fallback_zero;
```

Kết quả là 0, nhưng **do quy tắc dự phòng**, không phải kết quả của phép chia hợp lệ.

## 9. Tràn số và độ rộng kiểu dữ liệu

Các kiểu `SMALLINT`, `INTEGER` và `BIGINT` có **giới hạn phạm vi**. Trong PostgreSQL, phạm vi thường gặp:

| Kiểu | Phạm vi số nguyên |
|---|---|
| `SMALLINT` | -32.768 đến 32.767 |
| `INTEGER` | -2.147.483.648 đến 2.147.483.647 |
| `BIGINT` | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| `NUMERIC` | Có thể biểu diễn giá trị chính xác với phạm vi/precision lớn hơn, nhưng vẫn chịu giới hạn triển khai và khai báo cột |

Ví dụ biểu thức sau có thể vượt phạm vi của `INTEGER` trong PostgreSQL:

```sql
-- Cố ý gây lỗi số nguyên vượt phạm vi.
SELECT 2000000000::INTEGER * 2::INTEGER;
```

Để tính giá trị này, cần đưa ít nhất một toán hạng sang kiểu đủ lớn **trước khi nhân**:

```sql
SELECT
    2000000000::BIGINT * 2 AS bigint_result,
    2000000000::NUMERIC * 2 AS numeric_result;
```

Cả hai có giá trị toán học **4000000000**.

**Không ép kiểu sau khi phép toán đã tràn:**

```sql
-- Không giải quyết được lỗi nếu phép nhân INTEGER đã được thực hiện trước.
SELECT CAST(2000000000::INTEGER * 2::INTEGER AS BIGINT);
```

Đây là cùng nguyên tắc với phép chia nguyên: **chuyển kiểu trước phép toán có nguy cơ mất dữ liệu**.

### 9.1. Kết quả của SUM có thể khác kiểu cột đầu vào

PostgreSQL có các quy tắc nâng kiểu cho hàm tổng hợp. Ví dụ thông dụng:

- `SUM` trên `INTEGER` trả kiểu `BIGINT`.
- `SUM` trên `BIGINT` trả kiểu `NUMERIC`.
- `SUM` trên `NUMERIC` trả kiểu `NUMERIC`.
- `AVG` trên `INTEGER` thường trả `NUMERIC` để giữ phần thập phân.

Kiểm tra bằng PostgreSQL:

```sql
SELECT
    PG_TYPEOF(SUM(quantity)) AS sum_quantity_type,
    PG_TYPEOF(AVG(quantity)) AS avg_quantity_type
FROM lesson137_prices;
```

Với cột `quantity INTEGER`, hai kiểu kết quả là `bigint` và `numeric`. Tuy nhiên, điều này không bảo đảm **mọi biểu thức lồng bên trong `SUM` đều tránh tràn**. Ví dụ `SUM(quantity * unit_price)` được tính theo kiểu của **từng phép nhân** trước khi tổng hợp; hãy chọn kiểu các cột và phép ép kiểu trước phép nhân nếu phạm vi có nguy cơ không đủ.

## 10. Biểu thức số học trong báo cáo: hàm tổng hợp và kiểu đầu vào

Hãy tạo dữ liệu thực hành PostgreSQL:

```sql
INSERT INTO lesson137_prices (
    product_id,
    unit_price,
    quantity,
    discount_percent
)
VALUES
    (1, 125000.50, 2, 10.00),
    (2, 49999.99, 3, 0.00),
    (3, 10000.00, 0, 5.00),
    (4, 79900.00, 1, 12.50);
```

Bảng mẫu có đơn giá thập phân, số lượng nguyên và mức giảm giá dạng phần trăm.

### 10.1. Tính thành tiền từng dòng

```sql
SELECT
    product_id,
    quantity,
    unit_price,
    quantity * unit_price AS gross_amount,
    ROUND(
        quantity * unit_price
            * (1 - discount_percent / 100.0),
        2
    ) AS net_amount
FROM lesson137_prices
ORDER BY product_id;
```

Ý nghĩa:

1. `quantity * unit_price` là tiền trước giảm.
2. `discount_percent / 100.0` chuyển phần trăm sang tỷ lệ.
3. `1 - tỷ lệ` là tỷ phần khách hàng cần thanh toán.
4. `ROUND(..., 2)` thực hiện quy tắc làm tròn hai chữ số cho kết quả biểu thức trong ví dụ.

Khi triển khai thực tế, xác định rõ **thứ tự làm tròn**, **thuế áp dụng trước/sau giảm giá**, cách xử lý chiết khấu nhiều tầng và **đơn vị tiền**. Câu SQL không tự đưa ra quy tắc kế toán đúng cho mọi doanh nghiệp.

### 10.2. Tính tổng và trung bình

```sql
SELECT
    COUNT(*) AS line_count,
    SUM(quantity) AS total_quantity,
    SUM(quantity * unit_price) AS gross_total,
    AVG(unit_price) AS average_unit_price
FROM lesson137_prices;
```

Ở đây:

- `COUNT(*)` đếm số dòng, kể cả dòng có số lượng 0.
- `SUM(quantity)` cộng số lượng.
- `SUM(quantity * unit_price)` cộng số tiền gộp của từng dòng.
- `AVG(unit_price)` là **trung bình đơn giá trên các dòng**, không phải giá bán trung bình **theo từng sản phẩm**.

Để tính **đơn giá bình quân gia quyền theo số lượng**, biểu thức sẽ là:

```sql
SELECT
    SUM(quantity * unit_price)
        / NULLIF(SUM(quantity), 0) AS weighted_average_price
FROM lesson137_prices;
```

Mẫu số là **tổng số lượng**, không phải số dòng. Vì `unit_price` có kiểu `NUMERIC`, tử số `SUM(quantity * unit_price)` mang kiểu thập phân phù hợp trong PostgreSQL; `NULLIF` ngăn chia cho 0 nếu tổng số lượng bằng 0.

### 10.3. Đếm tỷ lệ phần trăm của các dòng thỏa điều kiện

Giả sử muốn tỷ lệ dòng có số lượng lớn hơn 0:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(*) FILTER (WHERE quantity > 0) AS positive_quantity_rows,
    100.0 * COUNT(*) FILTER (WHERE quantity > 0)
        / NULLIF(COUNT(*), 0) AS positive_percentage
FROM lesson137_prices;
```

`FILTER (WHERE ...)` là cú pháp PostgreSQL và các hệ có hỗ trợ SQL aggregate filter. Với 4 dòng mẫu, có **3 dòng số lượng dương**, nên kết quả `positive_percentage` là **75**. Nếu DBMS không hỗ trợ `FILTER`, có thể dùng tổng biểu thức `CASE`:

```sql
SELECT
    100.0 * SUM(
        CASE WHEN quantity > 0 THEN 1 ELSE 0 END
    ) / NULLIF(COUNT(*), 0) AS positive_percentage
FROM lesson137_prices;
```

Điều quan trọng ở cả hai câu là **nhân 100.0 trước khi chia hoặc ép kiểu sang dạng thập phân**, tránh chia nguyên ở những hệ quản trị có quy tắc như PostgreSQL.

## 11. Suy luận kiểu dữ liệu và CAST trong biểu thức

Mỗi phép toán số học được DBMS giải quyết bằng một **toán tử ứng với kiểu toán hạng**. Khi các toán hạng không cùng kiểu, DBMS có thể tự chuyển kiểu (implicit cast) hoặc yêu cầu ép kiểu (explicit cast).

Ví dụ PostgreSQL:

```sql
SELECT
    PG_TYPEOF(5 / 2) AS type_of_integer_division,
    PG_TYPEOF(5.0 / 2) AS type_of_decimal_division,
    PG_TYPEOF(5::DOUBLE PRECISION / 2) AS type_of_float_division;
```

Kết quả các kiểu lần lượt là `integer`, `numeric` và `double precision`.

### 11.1. CAST giúp câu SQL biểu đạt ý định

Ví dụ:

```sql
SELECT
    CAST(5 AS NUMERIC) / 2 AS exact_decimal_ratio,
    CAST(5 AS DOUBLE PRECISION) / 2 AS floating_ratio,
    CAST(5 AS BIGINT) * 1000000000 AS wide_integer_product;
```

- `NUMERIC` phù hợp cho tính toán thập phân cần chính xác.
- `DOUBLE PRECISION` cho phép biểu diễn xấp xỉ với phạm vi rộng.
- `BIGINT` phù hợp cho phép nhân số nguyên lớn nhưng vẫn có giới hạn.

Không có kiểu “luôn tốt nhất”: cần cân nhắc độ chính xác, phạm vi, khả năng lưu trữ, tốc độ, tương thích driver và ý nghĩa dữ liệu.

### 11.2. Literal số cũng ảnh hưởng đến suy luận kiểu

Trong PostgreSQL, khi viết:

```sql
SELECT
    5 / 2 AS integer_case,
    5 / 2.0 AS decimal_case,
    5 / 2e0 AS approximate_case;
```

`2.0` thường được suy luận là `NUMERIC`, còn `2e0` cũng có thể được PostgreSQL xử lý như literal `NUMERIC` theo cơ chế suy luận hằng số số học; **ký hiệu khoa học không bảo đảm tự thành `DOUBLE PRECISION`**.

Khi cần chắc chắn dùng phép tính xấp xỉ, hãy chỉ rõ kiểu:

```sql
SELECT
    5 / CAST(2 AS DOUBLE PRECISION) AS explicit_float_case;
```

Khi cần bảo đảm phép tính chính xác, dùng `NUMERIC` một cách tường minh cũng là thói quen rõ ràng hơn dựa vào suy luận của literal trong SQL đa hệ quản trị.

### 11.3. Chuỗi chứa số không phải kiểu số

Giá trị `'100'` là một literal chuỗi/unknown literal theo ngữ cảnh. Một số DBMS có thể tự chuyển nó sang số; DBMS khác báo lỗi hoặc xử lý theo các quy tắc riêng.

```sql
-- Nên diễn đạt kiểu đích rõ ràng khi đầu vào thực sự là văn bản số.
SELECT CAST('100' AS NUMERIC(10, 2)) + 25 AS parsed_amount;
```

Khi dữ liệu có thể không hợp lệ (ví dụ `'100abc'`, chuỗi rỗng, dấu phân cách hàng nghìn), cần **xác thực và chuyển đổi theo định dạng đầu vào**, không mặc định `CAST` luôn thành công. Trong chương trình Java, ưu tiên truyền tham số số đúng kiểu thay vì nối chuỗi nhập từ người dùng vào SQL.

## 12. Một số hàm số học và ngữ nghĩa đa hệ quản trị

Ngoài các toán tử cơ bản, SQL cung cấp nhiều hàm số học. Ví dụ PostgreSQL:

```sql
SELECT
    ABS(-7) AS absolute_value,
    POWER(2, 3) AS eight,
    SQRT(81::NUMERIC) AS nine,
    ROUND(12.345::NUMERIC, 2) AS rounded,
    CEIL(4.2::NUMERIC) AS ceiling_value,
    FLOOR(4.8::NUMERIC) AS floor_value,
    MOD(17, 5) AS remainder_value;
```

Một số biểu thức cần lưu ý:

- `POWER(base, exponent)` tính lũy thừa. Phạm vi giá trị, kiểu kết quả và hành vi đối với số âm/mũ phân số phụ thuộc DBMS.
- `SQRT(x)` tính căn bậc hai, thường cần `x >= 0` trong miền số thực; DBMS có thể báo lỗi nếu miền không hợp lệ.
- `ABS(x)` tạo trị tuyệt đối nhưng **vẫn có thể tràn kiểu** ở giá trị âm nhỏ nhất của một số kiểu nguyên có dấu.
- `ROUND` xử lý làm tròn; quy tắc điểm giữa và kiểu kết quả khác nhau giữa hệ quản trị hoặc giữa số chính xác/xấp xỉ.
- `MOD(a, b)` tính phần dư; cần kiểm soát mẫu số `b = 0` và dấu của số âm.

### 12.1. Không coi ký hiệu mũ hoặc XOR giống nhau ở mọi DBMS

Trong PostgreSQL, toán tử `^` thường được dùng cho **lũy thừa** trong ngữ cảnh số:

```sql
SELECT 2 ^ 3 AS power_result;
```

Kết quả toán học là **8**. Nhưng trong **SQL Server** và **MySQL**, `^` được dùng cho thao tác **bitwise XOR**, không phải cùng phép toán lũy thừa của PostgreSQL. Khi cần tính lũy thừa trên nhiều DBMS, hãy ưu tiên hàm `POWER(2, 3)` (cùng với quy tắc kiểu dữ liệu của từng DBMS) thay vì dùng toán tử `^`.

### 12.2. Số đặc biệt, vô hạn và NaN

Một số kiểu dấu phẩy động và một số triển khai `NUMERIC` có thể hỗ trợ giá trị đặc biệt như `NaN` (not a number) hoặc infinity. Cách truyền, so sánh, sắp xếp và lưu các giá trị đó **không nhất quán giữa DBMS**.

Trong dữ liệu tài chính và nhiều trường nghiệp vụ, cách an toàn thường là **không cho phép** giá trị đặc biệt nếu chúng không có ý nghĩa trong miền dữ liệu. Đặt kiểm tra đầu vào và ràng buộc theo quy tắc nghiệp vụ; không mặc định mọi biểu thức chia cho 0 sẽ trả cùng một giá trị đặc biệt, vì nhiều phép chia SQL thông thường sẽ báo lỗi.

## 13. Các khác biệt đáng chú ý giữa PostgreSQL, MySQL, SQL Server, SQLite

Phép cộng hoặc nhân số nguyên nhỏ thường cho cùng giá trị ở nhiều DBMS. Khác biệt nổi bật xuất hiện khi **chia nguyên, chọn kiểu kết quả, làm tròn hoặc tràn số**.

| Chủ đề | PostgreSQL | MySQL | SQL Server | SQLite |
|---|---|---|---|---|
| `5 / 2` với literal nguyên | **2** | Thông thường **2.5** với `/` | **2** | **2** khi cả hai là integer |
| Phép chia nguyên riêng | `INTEGER / INTEGER` cho phần nguyên | Toán tử `DIV`, ví dụ `5 DIV 2` | `INTEGER / INTEGER` cho phần nguyên | `INTEGER / INTEGER` cho phần nguyên |
| Kiểu thập phân chính xác | `NUMERIC` / `DECIMAL` | `DECIMAL` | `DECIMAL` / `NUMERIC` | Không có decimal fixed-point chuẩn như ba hệ trên |
| Số xấp xỉ | `REAL` / `DOUBLE PRECISION` | `FLOAT` / `DOUBLE` | `real` / `float` | Thường `REAL` |
| Phần dư | `%`, `MOD` | `%`, `MOD` | `%` | `%` |
| Ký hiệu `^` | Lũy thừa trong PostgreSQL | XOR bit | XOR bit | Không dùng như toán tử mũ phổ quát |
| Chuyển kiểu phổ biến | `CAST`, `::` | `CAST` | `CAST`, `CONVERT` | `CAST` |

Bảng tóm tắt các quy tắc thường gặp, không thay thế tài liệu phiên bản cụ thể. Một số phép tính còn phụ thuộc cột thực tế dùng `INT`, `DECIMAL`, `FLOAT` hay những kiểu riêng khác.

### 13.1. PostgreSQL

```sql
SELECT
    5 / 2 AS integer_division,
    5.0 / 2 AS numeric_division,
    5::DOUBLE PRECISION / 2 AS floating_division;
```

Đây là DBMS minh họa của bài, nên nên **ép kiểu trước khi chia** trong các truy vấn tỷ lệ phần trăm.

PostgreSQL có `NUMERIC` chính xác thập phân và các hàm như `ROUND(numeric, scale)`, `TRUNC(numeric, scale)`. Hãy chú ý kết quả của biểu thức `INTEGER * INTEGER` vẫn có thể tràn trước khi đưa vào tổng hợp hoặc ép sang `BIGINT`.

### 13.2. MySQL

Trong MySQL, `/` thường thực hiện phép chia có phần thập phân ngay cả khi hai toán hạng là số nguyên:

```sql
SELECT
    5 / 2 AS decimal_quotient,
    5 DIV 2 AS integer_quotient,
    5 % 2 AS remainder_value;
```

Kết quả giá trị thường là `2.5`, `2`, `1` (cách hiển thị số chữ số thập phân có thể phụ thuộc kiểu/precision).

MySQL có `DECIMAL(p,s)` phù hợp cho giá trị thập phân chính xác, và các tùy chọn SQL mode có thể ảnh hưởng cách xử lý lỗi, phép chia cho 0 hoặc giá trị ngoài phạm vi. Không giả định hành vi báo lỗi giống PostgreSQL.

### 13.3. SQL Server

Trong SQL Server:

```sql
SELECT
    5 / 2 AS integer_division,
    CAST(5 AS decimal(10, 2)) / 2 AS decimal_division,
    5 % 2 AS remainder_value;
```

Kết quả về giá trị là `2`, `2.5` và `1`, dù số chữ số thập phân hiển thị và kiểu kết quả phụ thuộc quy tắc precision/scale của `decimal`.

Trong SQL Server, phép tính với `decimal(p,s)` có **quy tắc xác định precision và scale của biểu thức kết quả**, phụ thuộc phép cộng, nhân hay chia. Một biểu thức chuỗi dài có thể bị điều chỉnh scale theo giới hạn precision của engine. Khi cần lưu tiền tệ hoặc tỷ lệ vào cột, phải xác định precision và scale đầu vào/đầu ra dựa trên quy tắc SQL Server, không áp dụng nguyên cách tính của PostgreSQL.

### 13.4. SQLite

SQLite dùng hệ thống kiểu linh hoạt với các **storage classes** và **type affinity**. Với các số nguyên:

```sql
SELECT
    5 / 2 AS integer_division,
    5 / 2.0 AS real_division,
    5 % 2 AS remainder_value;
```

Thông thường kết quả là `2`, `2.5` và `1`. `/` và `%` trong SQLite áp dụng hành vi theo kiểu giá trị ở **thời điểm thực thi**, không chỉ theo tên cột được khai báo.

SQLite không cung cấp decimal fixed-point chuẩn tương đương `NUMERIC(p,s)` của PostgreSQL cho việc tính tiền chính xác. Một lựa chọn thực tế thường gặp là **lưu số tiền theo đơn vị nhỏ nhất bằng integer**, ví dụ số đồng/xu theo quy định hệ thống, hoặc sử dụng thư viện/extension decimal có cơ chế tính phù hợp. Khi lưu và tính theo integer, vẫn cần xem xét **phạm vi tràn số** và cách xử lý phân số thuế/giảm giá.

## 14. Hiệu năng của biểu thức số học trong truy vấn

Các biểu thức số học trong `SELECT` có thể được tính cho từng hàng. Khi đặt biểu thức lên cột trong `WHERE` hoặc `JOIN`, DBMS có thể gặp khó khăn hơn khi dùng **chỉ mục B-tree thông thường**.

Ví dụ:

```sql
-- Biểu thức trên cột; có thể khó tận dụng chỉ mục quantity thông thường.
SELECT product_id
FROM lesson137_prices
WHERE quantity * 2 > 10;
```

Với `quantity` không âm và kiểu số phù hợp, có thể biến đổi tương đương thành:

```sql
SELECT product_id
FROM lesson137_prices
WHERE quantity > 5;
```

Điều kiện thứ hai thường dễ tận dụng chỉ mục trên `quantity` hơn. **Tuy nhiên, không tự biến đổi mọi biểu thức mà không xét NULL, tràn số, dấu số hoặc làm tròn**. Ví dụ phép chia nguyên `quantity / 2 > 5` không đơn giản tương đương với `quantity > 10` đối với mọi giá trị. Cần kiểm tra chính xác ngữ nghĩa.

PostgreSQL hỗ trợ **expression index** cho những biểu thức được phép lập chỉ mục:

```sql
-- Ví dụ minh họa: chỉ tạo nếu workload thực sự cần lọc biểu thức này.
CREATE INDEX lesson137_prices_extended_idx
    ON lesson137_prices ((quantity * unit_price));
```

Chỉ mục theo biểu thức có chi phí bảo trì khi ghi dữ liệu; với bảng thực hành nhỏ, việc thêm chỉ mục thường không làm truy vấn nhanh hơn. Khi hiệu năng quan trọng, xem `EXPLAIN` và thống kê trên dữ liệu thực tế.

## 15. Khi tính trong ứng dụng Java: so sánh SQL với kiểu dữ liệu Java

Ứng dụng Java thường đọc số từ JDBC rồi thực hiện tính toán tiếp. Cần hiểu **một phép tính có thể đã mất phần lẻ trước khi sang Java**.

### 15.1. Ép kiểu trong SQL từ đầu

Nếu bạn viết:

```sql
SELECT 5 / 2 AS result;
```

PostgreSQL trả `INTEGER` có giá trị `2`. Nếu Java gọi `getBigDecimal("result")`, kết quả nhận được vẫn là số **2**, không thể “khôi phục” phần `0.5` đã bị loại trong SQL.

Cách đúng là diễn đạt phép chia thập phân ngay trong SQL:

```sql
SELECT CAST(5 AS NUMERIC) / 2 AS result;
```

Sau đó Java có thể đọc bằng `ResultSet.getBigDecimal("result")` theo hỗ trợ của driver.

### 15.2. Dùng BigDecimal cho số tiền

Trong Java, `BigDecimal` thường phù hợp cho phép tính tiền chính xác thập phân:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("120000.50");
BigDecimal quantity = BigDecimal.valueOf(3);

BigDecimal gross = unitPrice.multiply(quantity);
BigDecimal taxRate = new BigDecimal("0.08");

BigDecimal totalWithTax = gross
        .multiply(BigDecimal.ONE.add(taxRate))
        .setScale(2, RoundingMode.HALF_UP);

System.out.println(totalWithTax);
```

Ví dụ trên dùng **một chính sách làm tròn minh họa** (`HALF_UP`) và không thay thế quy tắc kế toán cụ thể. Khi đọc/ghi SQL `NUMERIC` từ JDBC, `BigDecimal` giúp tránh chuyển qua `double` xấp xỉ nếu ứng dụng cần tính chính xác decimal.

Không tạo `BigDecimal` từ một literal `double` mà không hiểu sai số của số nhị phân; dùng chuỗi thập phân hoặc các phương thức chuyển đổi thích hợp.

### 15.3. Khi nào tính ở SQL, khi nào tính ở Java?

- Tính ở **SQL** phù hợp với lọc, tổng hợp và biến đổi trên tập dữ liệu lớn gần nơi lưu trữ, miễn là kiểu dữ liệu và công thức được kiểm soát.
- Tính ở **Java** phù hợp khi logic nghiệp vụ cần cấu trúc phức tạp, tái sử dụng qua dịch vụ hoặc chính sách làm tròn được tập trung trong mã nguồn.
- Nếu cả SQL và Java đều tính cùng một chỉ số, cần thống nhất **kiểu dữ liệu, thứ tự phép toán và làm tròn**, tránh hai nơi cho hai kết quả khác nhau.

Không có quy tắc phải luôn tính toàn bộ ở một bên; điều quan trọng là một phép tính cần được **định nghĩa nhất quán** trong hệ thống.

## 16. Những lỗi thường gặp và cách sửa

### Lỗi 1. Chia hai số nguyên khi cần tỷ lệ thập phân

```sql
-- PostgreSQL: kết quả 0.
SELECT 3 / 10 * 100 AS percentage;
```

```sql
-- Kết quả 30.
SELECT 3::NUMERIC / 10 * 100 AS percentage;
```

### Lỗi 2. CAST sau phép chia

```sql
-- Đã chia nguyên thành 2 trước khi CAST.
SELECT CAST(5 / 2 AS NUMERIC);
```

```sql
-- CAST trước, kết quả 2.5.
SELECT CAST(5 AS NUMERIC) / 2;
```

### Lỗi 3. Cho rằng DECIMAL(10,2) khiến mọi phép tính chỉ có hai chữ số

```sql
SELECT 10.00::NUMERIC(10, 2) / 3;
```

Phép chia có thể tạo thêm nhiều chữ số thập phân; muốn làm tròn theo nghiệp vụ, dùng `ROUND(..., 2)` ở đúng bước.

### Lỗi 4. Dùng kiểu float cho số tiền cần chính xác

```sql
SELECT
    0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION;
```

Kết quả xấp xỉ nhị phân có thể có sai số. Với tiền tệ cần decimal exact, chọn `NUMERIC`/`DECIMAL` hoặc lưu đơn vị nhỏ nhất bằng integer với thiết kế rõ ràng.

### Lỗi 5. Không xử lý mẫu số bằng 0

```sql
-- Cố ý gây lỗi trong PostgreSQL.
SELECT total_amount / 0
FROM order_items;
```

```sql
-- Cho NULL khi denominator = 0.
SELECT total_amount / NULLIF(item_count, 0) AS average_amount
FROM order_summaries;
```

Các bảng ở ví dụ này là giả định; cần chọn mẫu số và ý nghĩa `NULL` phù hợp nghiệp vụ.

### Lỗi 6. Dùng phép làm tròn không đúng thứ tự

```sql
SELECT
    3 * ROUND(1.005::NUMERIC, 2) AS each_item_first,
    ROUND(3 * 1.005::NUMERIC, 2) AS total_first;
```

Hai kết quả là **3.03** và **3.02**. Cần thống nhất quy tắc trên hóa đơn/báo cáo.

### Lỗi 7. Coi NULL như 0 ở mọi bài toán

```sql
SELECT
    AVG(score) AS average_known,
    AVG(COALESCE(score, 0)) AS average_zero_filled
FROM exam_scores;
```

Hai chỉ số có thể khác nhau: một bên chỉ trung bình các điểm đã biết, bên kia coi điểm thiếu là 0. `NULL` không tự đồng nghĩa với không đạt hoặc 0 điểm.

### Lỗi 8. Không nghĩ đến tràn số của biểu thức trung gian

```sql
-- Có thể tràn INTEGER trước khi tổng được tính hoặc trước CAST.
SELECT 2000000000::INTEGER * 2::INTEGER;
```

```sql
-- Mở rộng kiểu trước phép nhân.
SELECT 2000000000::BIGINT * 2;
```

### Lỗi 9. Dùng dấu `^` theo nghĩa giống nhau trên mọi DBMS

Trong PostgreSQL, `2 ^ 3` thường là lũy thừa. Trong MySQL và SQL Server, `^` thường là XOR bit. Ưu tiên `POWER(2,3)` khi muốn biểu đạt lũy thừa theo cách dễ nhận diện.

## 17. Bài tập thực hành có lời giải

Các bài dùng PostgreSQL, trừ khi ghi rõ hệ quản trị khác. Bạn có thể chạy những biểu thức `SELECT` độc lập ngay trong công cụ SQL mà không cần bảng dữ liệu. Đối với bài dùng `lesson137_prices`, hãy tạo và thêm dữ liệu ở phần 5 và phần 10 trước.

### Bài 1. Dự đoán kết quả chia nguyên

```sql
SELECT
    11 / 4 AS a,
    11.0 / 4 AS b,
    -11 / 4 AS c;
```

**Đáp án:** `a = 2`; `b = 2.75`; `c = -2`. Phần thập phân của phép chia `INTEGER` bị loại theo hướng về 0.

### Bài 2. Sửa tỷ lệ hoàn thành

Truy vấn sau sai khi cần kết quả phần trăm:

```sql
SELECT 7 / 20 * 100 AS completion_percent;
```

**Đáp án gợi ý:**

```sql
SELECT 100.0 * 7 / 20 AS completion_percent;
```

Kết quả là **35**. Việc nhân `100.0` trước tránh phép chia nguyên.

### Bài 3. Chọn cách làm tròn

Dự đoán kết quả:

```sql
SELECT
    ROUND(9.876::NUMERIC, 2) AS a,
    TRUNC(9.876::NUMERIC, 2) AS b,
    FLOOR(-1.2::NUMERIC) AS c,
    CEIL(-1.2::NUMERIC) AS d;
```

**Đáp án:** `a = 9.88`; `b = 9.87`; `c = -2`; `d = -1`.

### Bài 4. Tổng số lượng và đơn giá trung bình

Cho bảng:

```text
product_id | quantity | unit_price
-----------+----------+-----------
1          | 2        | 125000.50
2          | 3        | 49999.99
3          | 0        | 10000.00
4          | 1        | 79900.00
```

**Yêu cầu:** Tính **tổng số lượng** và **doanh thu gộp**.

```sql
SELECT
    SUM(quantity) AS total_quantity,
    SUM(quantity * unit_price) AS gross_revenue
FROM lesson137_prices;
```

**Đáp án:** tổng số lượng là **6**; tổng tiền gộp là:

```text
2 × 125000.50 = 250001.00
3 ×  49999.99 = 149999.97
0 ×  10000.00 =      0.00
1 ×  79900.00 =  79900.00
--------------------------
Tổng           = 479900.97
```

### Bài 5. Giá bình quân theo số lượng

**Yêu cầu:** tính đơn giá bình quân gia quyền từ dữ liệu bài 4.

```sql
SELECT
    ROUND(
        SUM(quantity * unit_price)
            / NULLIF(SUM(quantity), 0),
        2
    ) AS weighted_average_unit_price
FROM lesson137_prices;
```

**Đáp án:** `479900.97 / 6 = 79983.495`, làm tròn `NUMERIC` đến 2 chữ số thành **79983.50**.

Không dùng `AVG(unit_price)` nếu yêu cầu là bình quân trên **sáu sản phẩm**, vì `AVG(unit_price)` chia theo **bốn dòng dữ liệu**.

### Bài 6. Khi nào NULLIF có ích?

Xét:

```sql
SELECT
    15::NUMERIC / NULLIF(3, 0) AS a,
    15::NUMERIC / NULLIF(0, 0) AS b;
```

**Đáp án:** `a = 5`; `b = NULL`. Biểu thức thứ hai tránh lỗi chia cho 0 bằng cách đưa mẫu số thành `NULL`. Bản thân `NULL` vẫn phải được diễn giải đúng: không có tỷ lệ xác định.

### Bài 7. Phần dư và số âm

```sql
SELECT
    14 % 5 AS a,
    -14 % 5 AS b,
    MOD(MOD(-14, 5) + 5, 5) AS c;
```

**Đáp án PostgreSQL:** `a = 4`; `b = -4`; `c = 1`. Biểu thức thứ ba chuẩn hóa phần dư vào đoạn từ 0 đến trước 5.

### Bài 8. So sánh kiểu kết quả

```sql
SELECT
    PG_TYPEOF(8 / 3) AS a_type,
    PG_TYPEOF(8.0 / 3) AS b_type,
    PG_TYPEOF(8::DOUBLE PRECISION / 3) AS c_type;
```

**Đáp án:** `integer`, `numeric`, `double precision`. Cùng các chữ số đầu vào, thay đổi kiểu toán hạng làm thay đổi cách DBMS tính toán.

### Bài 9. Chọn kiểu cho nghiệp vụ

Một hệ thống cần các cột:

1. `units_in_stock`: số lượng sản phẩm nguyên, có thể đến hàng tỷ.
2. `unit_price`: giá bán theo đơn vị tiền với hai chữ số sau dấu thập phân.
3. `sensor_measurement`: số đo vật lý xấp xỉ cần phạm vi lớn.
4. `conversion_rate`: tỷ lệ yêu cầu chính xác nhiều chữ số thập phân cho báo cáo tài chính.

**Gợi ý đáp án PostgreSQL:** `BIGINT` hoặc kiểu nguyên đủ phạm vi cho (1), `NUMERIC(p,2)` cho (2), `DOUBLE PRECISION` cho (3) và `NUMERIC(p,s)` với scale phù hợp cho (4). Giá trị của `p` và `s` phải được xác định từ phạm vi thực tế, số chữ số cần giữ và các phép toán tiếp theo.

### Bài 10. Giải thích sự khác biệt giữa hai phép làm tròn

```sql
SELECT
    3 * ROUND(1.005::NUMERIC, 2) AS round_first,
    ROUND(3 * 1.005::NUMERIC, 2) AS multiply_first;
```

**Đáp án:** `round_first = 3.03` và `multiply_first = 3.02`. Sự khác biệt đến từ **thời điểm làm tròn**, không phải lỗi của `NUMERIC`. Ứng dụng cần một quy tắc nghiệp vụ nhất quán.

## 18. Bảng ghi nhớ

| Vấn đề | Cách xử lý gợi ý |
|---|---|
| Cần phần thập phân khi chia hai số nguyên | Ép kiểu **trước phép chia**: `CAST(a AS NUMERIC) / b` |
| Cần số tiền chính xác thập phân | Dùng `NUMERIC`/`DECIMAL` với precision, scale phù hợp |
| Cần đo lường chấp nhận sai số | Cân nhắc `REAL`/`DOUBLE PRECISION` |
| Cần làm tròn đến hai chữ số | `ROUND(expression::NUMERIC, 2)` trong PostgreSQL |
| Cần cắt bớt chữ số mà không làm tròn | `TRUNC(expression::NUMERIC, 2)` trong PostgreSQL |
| Mẫu số có thể bằng 0 | `numerator / NULLIF(denominator, 0)`; xác định ý nghĩa `NULL` |
| Thiếu giá trị số | Chỉ dùng `COALESCE(value, 0)` nếu `NULL` thực sự được phép coi là 0 |
| Phép tính trung gian có thể tràn | Chuyển sang `BIGINT`/`NUMERIC` **trước** phép tính |
| Tính tỷ lệ phần trăm | `100.0 * numerator / NULLIF(denominator, 0)` theo kiểu SQL phù hợp |
| Kết quả tiền không nhất quán | Thống nhất thứ tự phép toán, thời điểm làm tròn và đơn vị tiền |
| Di chuyển truy vấn sang DBMS khác | Kiểm tra lại chia nguyên, kiểu kết quả, `ROUND` và toán tử riêng như `^` |

**Khi một biểu thức số học cho kết quả bất ngờ, hãy kiểm tra theo thứ tự:** kiểu dữ liệu của từng toán hạng; thứ tự các toán tử và dấu ngoặc; quy tắc chia nguyên và chuyển kiểu; ảnh hưởng của `NULL`/chia cho 0; precision/scale và quy tắc làm tròn; giới hạn phạm vi của kiểu kết quả. SQL có thể thực thi thành công nhưng vẫn cho kết quả không đúng ý nghiệp vụ nếu các yếu tố này chưa được xác định rõ.

## Tài liệu tham khảo

- [PostgreSQL — Mathematical Functions and Operators](https://www.postgresql.org/docs/current/functions-math.html): toán tử, hàm số học, làm tròn và phần dư.
- [PostgreSQL — Numeric Types](https://www.postgresql.org/docs/current/datatype-numeric.html): số nguyên, `NUMERIC`, `DECIMAL`, số xấp xỉ, precision và scale.
- [PostgreSQL — Type Conversion](https://www.postgresql.org/docs/current/typeconv.html): cơ chế suy luận kiểu và chọn toán tử.
- [MySQL — Arithmetic Operators](https://dev.mysql.com/doc/refman/8.4/en/arithmetic-functions.html): `/`, `DIV`, `MOD` và các khác biệt về phép toán số.
- [SQLite — Expressions](https://www.sqlite.org/lang_expr.html): phép chia, phần dư và quy tắc kiểu giá trị trong biểu thức.

