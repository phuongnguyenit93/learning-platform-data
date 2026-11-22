# Biểu thức số học, độ ưu tiên và phép chia / hoặc DIV

Biểu thức số học xuất hiện trong hầu hết truy vấn MySQL: tính thành tiền, chiết khấu, thuế, tỷ lệ, số lượng còn lại, thời lượng hoặc phần dư khi phân bổ. Những biểu thức như `quantity * unit_price`, `total / item_count` hay `balance - amount` nhìn đơn giản nhưng có thể cho kết quả sai nếu không hiểu kiểu dữ liệu, thứ tự ưu tiên, phép chia nguyên, `NULL`, tràn số và phép chia cho 0.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Hàm và biểu thức**, bài này tập trung vào biểu thức số học, thứ tự thực hiện toán tử và cách chọn `/`, `DIV`, `%` hoặc `MOD()` theo đúng ý nghĩa nghiệp vụ.

## 1. Biểu thức số học trong SQL

Biểu thức số học kết hợp toán hạng, toán tử và dấu ngoặc để tạo ra một giá trị số. Toán hạng có thể là literal, column, biến, hàm hoặc biểu thức con.

```sql
SELECT
    10 + 5 AS addition_result,
    10 - 5 AS subtraction_result,
    10 * 5 AS multiplication_result,
    10 / 5 AS division_result,
    10 DIV 3 AS integer_division_result,
    10 % 3 AS remainder_result;
```

Các biểu thức có thể xuất hiện trong:

- `SELECT` để tính giá trị trả về.
- `WHERE` hoặc `HAVING` để lọc hàng và nhóm.
- `ORDER BY` để sắp xếp theo giá trị tính toán.
- `UPDATE` để tính giá trị mới của column.
- `INSERT ... SELECT` để biến đổi dữ liệu khi nạp.
- Generated column hoặc functional index khi biểu thức được dùng thường xuyên và phù hợp với quy tắc của MySQL.

Ví dụ nghiệp vụ:

```sql
SELECT
    order_item_id,
    quantity,
    unit_price,
    quantity * unit_price AS line_amount
FROM order_items;
```

Ở đây `quantity` và `unit_price` là toán hạng; `*` là toán tử nhân; `line_amount` là alias của kết quả.

## 2. Các toán tử số học cơ bản

| Toán tử | Ý nghĩa | Ví dụ | Kết quả |
|---|---|---|---:|
| `+` | Cộng | `8 + 3` | `11` |
| `-` | Trừ | `8 - 3` | `5` |
| `*` | Nhân | `8 * 3` | `24` |
| `/` | Chia thông thường | `8 / 3` | Kết quả có phần thập phân |
| `DIV` | Chia lấy phần nguyên theo hướng về 0 | `8 DIV 3` | `2` |
| `%` | Phần dư | `8 % 3` | `2` |
| `MOD` | Phần dư, tương đương `%` | `MOD(8, 3)` | `2` |

MySQL cũng hỗ trợ dấu một ngôi `+` và `-`:

```sql
SELECT
    +12 AS positive_value,
    -12 AS negative_value,
    -(-12) AS double_negative;
```

`MOD(N, M)` là hàm có cùng ý nghĩa với toán tử `N % M`. Có thể dùng dạng hàm khi biểu thức dễ đọc hơn hoặc khi truyền đối số qua một API tạo SQL.

Lũy thừa không phải là toán tử `^` trong MySQL. `^` là phép XOR bitwise. Nếu cần tính lũy thừa, dùng `POW()` hoặc `POWER()`:

```sql
SELECT POW(2, 3) AS eight;
```

## 3. Thứ tự ưu tiên của toán tử số học

Khi biểu thức có nhiều toán tử, MySQL dựa vào thứ tự ưu tiên để xác định phần nào được tính trước. Trong nhóm toán tử số học thông dụng:

1. Dấu một ngôi `+` và `-`.
2. Nhân `*`, chia `/`, chia nguyên `DIV`, phần dư `%` và `MOD`.
3. Cộng `+` và trừ `-`.

Các phép ở cùng một mức ưu tiên được kết hợp theo thứ tự từ trái sang phải trong những biểu thức số học thông thường. Dấu ngoặc `()` cho phép chỉ rõ thứ tự cần thực hiện và nên được dùng khi biểu thức có thể gây hiểu nhầm.

### 3.1. Nhân và chia được thực hiện trước cộng và trừ

```sql
SELECT 10 + 6 * 2 AS result;
```

Kết quả là `22`, vì `6 * 2` được tính trước rồi mới cộng 10.

Nếu muốn cộng trước:

```sql
SELECT (10 + 6) * 2 AS result;
```

Kết quả là `32`.

### 3.2. DIV, MOD và nhân cùng mức ưu tiên

```sql
SELECT 20 / 5 * 2 AS result;
```

Phép chia và nhân cùng mức ưu tiên, nên biểu thức được kết hợp từ trái sang phải: `(20 / 5) * 2`.

Tương tự:

```sql
SELECT 20 DIV 3 * 2 AS result;
SELECT 20 % 6 + 1 AS result;
```

Để tránh phụ thuộc vào việc người đọc phải tự nhớ thứ tự ưu tiên, có thể viết rõ:

```sql
SELECT (20 DIV 3) * 2 AS result;
SELECT (20 % 6) + 1 AS result;
```

### 3.3. Dấu ngoặc giúp thể hiện ý nghĩa nghiệp vụ

Hai biểu thức sau không tương đương:

```sql
SELECT amount * tax_rate / 100 AS tax_amount
FROM invoices;

SELECT amount * (tax_rate / 100) AS tax_amount
FROM invoices;
```

Về toán học chúng biểu diễn cùng tỷ lệ, nhưng cách nhóm biểu thức có thể ảnh hưởng đến kiểu trung gian và độ chính xác số học. Với `DECIMAL`, MySQL áp dụng quy tắc precision/scale cho từng phép toán; khi cần kết quả có scale cụ thể, hãy dùng `CAST()` hoặc `ROUND()` tại đúng bước nghiệp vụ.

Không nên dựa vào việc một biểu thức “trông giống toán học” để bỏ qua kiểu dữ liệu. Hãy viết ngoặc để người review hiểu rõ công thức, đặc biệt khi có phép chia, tỷ lệ hoặc phép tính trên tiền.

## 4. Phép chia thông thường `/`

Toán tử `/` thực hiện phép chia và có thể trả về phần thập phân. Với toán hạng exact-value như số nguyên và `DECIMAL`, MySQL thực hiện phép toán số học chính xác theo quy tắc precision/scale của kiểu số. Với toán hạng approximate-value như `FLOAT` hoặc `DOUBLE`, kết quả là số dấu phẩy động gần đúng.

```sql
SELECT
    5 / 2 AS exact_division,
    1 / 3 AS one_third,
    1.0E0 / 3 AS approximate_division;
```

Với exact-value division, số chữ số thập phân của kết quả chịu ảnh hưởng bởi `div_precision_increment` (mặc định là 4) cùng precision/scale của toán hạng. Kiểm tra giá trị hiện tại:

```sql
SELECT @@SESSION.div_precision_increment;
```

Không nên phụ thuộc vào số chữ số mặc định khi kết quả là dữ liệu nghiệp vụ. Nếu cần scale cụ thể, ép kiểu rõ ràng:

```sql
SELECT CAST(1 AS DECIMAL(12, 4)) /
       CAST(3 AS DECIMAL(12, 4)) AS ratio;
```

### 4.1. Chia số nguyên bằng `/` vẫn có thể tạo phần thập phân

```sql
SELECT 7 / 2 AS ordinary_division;
```

Kết quả là giá trị có phần lẻ, theo precision/scale mà MySQL áp dụng. Không dùng `/` nếu mục đích là bỏ phần thập phân.

### 4.2. Chia số thập phân

```sql
SELECT
    CAST(125000 AS DECIMAL(14, 2)) /
    CAST(3 AS DECIMAL(14, 2)) AS average_amount;
```

Với giá trị tiền, nên dùng `DECIMAL` thay vì `FLOAT`/`DOUBLE`. Kiểu dấu phẩy động lưu giá trị nhị phân gần đúng, nên một số số thập phân không thể biểu diễn chính xác. Các phép cộng dồn tiền có thể tạo sai số khó thấy nếu dùng kiểu approximate.

### 4.3. Kiểm soát scale bằng CAST và ROUND

`CAST()` chuyển kết quả sang kiểu có precision/scale được chỉ định; `ROUND()` làm tròn theo số chữ số thập phân yêu cầu.

```sql
SELECT
    CAST(10 / 3 AS DECIMAL(12, 4)) AS cast_result,
    ROUND(10 / 3, 2) AS rounded_result;
```

Hai thao tác có mục tiêu khác nhau:

- `CAST(... AS DECIMAL(p, s))` xác định kiểu dữ liệu và scale của giá trị sau chuyển đổi.
- `ROUND(value, d)` áp dụng quy tắc làm tròn đến `d` chữ số thập phân.

Không nên dùng `ROUND()` chỉ để che một phép tính sai scale. Trước hết hãy xác định quy tắc làm tròn của nghiệp vụ: làm tròn từng dòng hay chỉ làm tròn tổng cuối cùng có thể cho kết quả khác nhau.

## 5. Chia nguyên `DIV`

`DIV` thực hiện phép chia lấy phần nguyên. Phần thập phân bị loại bỏ theo hướng về 0 (truncate toward zero), không phải luôn làm tròn xuống.

```sql
SELECT
    7 DIV 2 AS positive_result,
    -7 DIV 2 AS negative_result,
    7 DIV -2 AS negative_divisor_result;
```

Kết quả tương ứng là `3`, `-3` và `-3`.

### 5.1. DIV khác FLOOR

Đây là điểm quan trọng với số âm:

```sql
SELECT
    -7 DIV 2 AS integer_division,
    FLOOR(-7 / 2) AS floor_result,
    TRUNCATE(-7 / 2, 0) AS truncate_result;
```

Kết quả:

- `-7 DIV 2` là `-3` vì phần lẻ bị loại bỏ về phía 0.
- `FLOOR(-7 / 2)` là `-4` vì `FLOOR()` lấy số nguyên nhỏ hơn hoặc bằng giá trị.
- `TRUNCATE(-7 / 2, 0)` là `-3` vì cắt phần thập phân về phía 0.

Vì vậy, `DIV` không thể thay thế `FLOOR()` trong mọi công thức. Hãy chọn theo định nghĩa nghiệp vụ.

### 5.2. Ví dụ tách tổng số phút thành giờ và phút

Giả sử `duration_minutes` là số phút không âm:

```sql
SELECT
    duration_minutes DIV 60 AS hours_part,
    MOD(duration_minutes, 60) AS minutes_part
FROM task_durations;
```

Với 135 phút, kết quả là 2 giờ và 15 phút. `DIV` lấy số giờ nguyên, `MOD()` lấy phần phút còn lại.

### 5.3. DIV không phải cách làm tròn

Nếu muốn làm tròn 2.7 thành 3, dùng `ROUND(2.7)`. `2.7 DIV 1` cho kết quả 2 vì nó loại phần lẻ. Nếu muốn lấy số nguyên nhỏ hơn hoặc bằng, dùng `FLOOR()`; nếu muốn lấy số nguyên lớn hơn hoặc bằng, dùng `CEIL()` hoặc `CEILING()`.

## 6. Phần dư `%` và hàm MOD()

`%` và `MOD()` trả về phần dư của phép chia:

```sql
SELECT
    17 % 5 AS remainder_operator,
    MOD(17, 5) AS remainder_function;
```

Cả hai trả về `2`.

Với toán hạng âm, phần dư mang dấu của toán hạng bên trái (dividend):

```sql
SELECT
    MOD(-17, 5) AS negative_dividend,
    MOD(17, -5) AS negative_divisor,
    MOD(-17, -5) AS both_negative;
```

Kết quả tương ứng là `-2`, `2` và `-2`.

### 6.1. Ví dụ kiểm tra số chẵn/lẻ

```sql
SELECT
    product_id,
    CASE
        WHEN product_id % 2 = 0 THEN 'EVEN'
        ELSE 'ODD'
    END AS id_parity
FROM products;
```

Nếu `product_id` có thể là số âm, quy tắc kiểm tra chẵn/lẻ vẫn hoạt động vì số chẵn có phần dư bằng 0.

### 6.2. Phân bổ phần dư

Giả sử cần chia 101 đơn vị cho 4 nhóm. Chia nguyên cho biết mỗi nhóm nhận tối thiểu bao nhiêu; modulo cho biết còn dư bao nhiêu:

```sql
SELECT
    101 DIV 4 AS base_amount,
    101 MOD 4 AS remainder_amount;
```

Kết quả là 25 đơn vị mỗi nhóm và còn dư 1. Phần dư phải được phân bổ theo một quy tắc nghiệp vụ xác định, ví dụ lần lượt cộng thêm một đơn vị cho nhóm đầu tiên theo thứ tự khóa. Không bỏ phần dư nếu tổng phân bổ phải bảo toàn số lượng ban đầu.

### 6.3. MOD với số thập phân

`MOD()` có thể làm việc với giá trị số thập phân:

```sql
SELECT MOD(10.5, 3.2) AS decimal_remainder;
```

Kiểu kết quả và độ chính xác phụ thuộc kiểu toán hạng. Nếu cần kết quả exact, dùng `DECIMAL` thay vì `FLOAT`/`DOUBLE`.

## 7. So sánh `/`, DIV và MOD

| Biểu thức | Kết quả | Ý nghĩa |
|---|---:|---|
| `17 / 5` | `3.4` | Chia thông thường, giữ phần thập phân. |
| `17 DIV 5` | `3` | Chia lấy phần nguyên, cắt về 0. |
| `17 % 5` | `2` | Phần dư. |
| `MOD(17, 5)` | `2` | Phần dư bằng dạng hàm. |
| `-17 DIV 5` | `-3` | Chia nguyên âm, cắt về 0. |
| `FLOOR(-17 / 5)` | `-4` | Làm tròn xuống số nguyên nhỏ hơn. |
| `MOD(-17, 5)` | `-2` | Phần dư mang dấu của số bị chia. |

Chọn toán tử theo câu hỏi:

- Cần tỷ lệ hoặc giá trị trung bình có phần thập phân: `/`.
- Cần số nhóm đầy đủ hoặc số đơn vị nguyên: `DIV`.
- Cần phần còn lại sau khi chia: `%` hoặc `MOD()`.
- Cần làm tròn: `ROUND()`, `FLOOR()` hoặc `CEIL()` tùy quy tắc.

## 8. Kiểu dữ liệu ảnh hưởng đến phép tính

MySQL có các nhóm kiểu số chính:

| Nhóm | Kiểu tiêu biểu | Đặc điểm |
|---|---|---|
| Số nguyên exact | `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, `BIGINT` | Lưu số nguyên; có thể khai báo `UNSIGNED`. |
| Số thập phân exact | `DECIMAL(p, s)` | Lưu giá trị thập phân theo precision và scale; phù hợp tiền và số liệu cần độ chính xác thập phân. |
| Số gần đúng | `FLOAT`, `DOUBLE` | Lưu số dấu phẩy động nhị phân; có thể có sai số biểu diễn. |

### 8.1. Exact-value và approximate-value

Ví dụ dùng `DECIMAL`:

```sql
SELECT
    CAST(0.1 AS DECIMAL(10, 2)) +
    CAST(0.2 AS DECIMAL(10, 2)) AS exact_sum;
```

Với `DECIMAL`, phép tính được thực hiện theo số học thập phân chính xác trong phạm vi precision hỗ trợ.

Với số dấu phẩy động:

```sql
SELECT CAST(0.1 AS DOUBLE) + CAST(0.2 AS DOUBLE) AS approximate_sum;
```

Kết quả có thể hiển thị gần `0.3` nhưng giá trị nhị phân bên trong không nhất thiết bằng chính xác 0.3. Không dùng phép so sánh bằng tuyệt đối cho kết quả `FLOAT`/`DOUBLE` nếu nghiệp vụ cần dung sai.

### 8.2. Tiền tệ nên dùng DECIMAL

Ví dụ schema:

```sql
CREATE TABLE invoice_lines (
    invoice_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity        DECIMAL(12, 3) NOT NULL,
    unit_price      DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (invoice_line_id)
);
```

Tính thành tiền:

```sql
SELECT
    invoice_line_id,
    quantity,
    unit_price,
    CAST(quantity * unit_price AS DECIMAL(18, 2)) AS line_amount
FROM invoice_lines;
```

Việc chọn precision/scale cần dựa trên giới hạn số lượng, đơn giá và tổng tiền lớn nhất. `DECIMAL(18,2)` chỉ là ví dụ; không sao chép thông số này cho mọi nghiệp vụ.

### 8.3. Số nguyên và UNSIGNED

`UNSIGNED` mở rộng miền giá trị về phía dương nhưng không biểu diễn số âm. Nó phù hợp với số lượng, số đếm hoặc ID khi miền nghiệp vụ không âm. Tuy nhiên, phép trừ có thể tạo ra số âm dù từng toán hạng đều không âm.

Ví dụ, số lượng tồn kho là `BIGINT UNSIGNED`:

```sql
SELECT quantity - 5 AS remaining_quantity
FROM inventory;
```

Nếu `quantity` nhỏ hơn 5, phép trừ có thể tạo giá trị âm ngoài miền của phép toán unsigned và MySQL có thể báo lỗi out-of-range. Đừng mặc định rằng cột unsigned sẽ tự chuyển thành số signed khi phép tính cần số âm.

Nếu số âm là một kết quả hợp lệ, có thể ép kiểu rõ ràng:

```sql
SELECT CAST(quantity AS SIGNED) - 5 AS signed_difference
FROM inventory;
```

Nếu nghiệp vụ không cho phép tồn kho âm, nên bảo vệ điều kiện ngay trong câu lệnh cập nhật thay vì ép kiểu để che lỗi:

```sql
UPDATE inventory
SET quantity = quantity - 5
WHERE product_id = 1001
  AND quantity >= 5;
```

Ứng dụng cần kiểm tra số hàng bị tác động để biết việc trừ tồn kho có thành công hay không.

### 8.4. NO_UNSIGNED_SUBTRACTION

SQL mode `NO_UNSIGNED_SUBTRACTION` thay đổi cách MySQL xử lý kết quả của phép trừ có toán hạng unsigned: kết quả được xử lý theo kiểu signed trong các trường hợp áp dụng. Điều này có thể giúp biểu thức thể hiện số âm, nhưng cũng làm thay đổi kiểu và miền kết quả của SQL hiện có.

Kiểm tra mode:

```sql
SELECT @@SESSION.sql_mode;
```

Không bật mode chỉ để một phép trừ tồn kho âm không còn lỗi. Hãy xác định số âm có hợp lệ về nghiệp vụ không, chọn kiểu dữ liệu phù hợp và kiểm thử các truy vấn phụ thuộc vào kiểu kết quả.

## 9. Chuyển kiểu và ép kiểu tường minh

MySQL có thể chuyển đổi kiểu ngầm khi biểu thức trộn số, chuỗi hoặc các kiểu khác. Điều này tiện trong truy vấn ngắn nhưng có thể tạo kết quả ngoài dự kiến nếu dữ liệu đầu vào không đồng nhất.

```sql
SELECT
    '12' + 3 AS numeric_string,
    CAST('12.50' AS DECIMAL(10, 2)) + 1 AS decimal_value;
```

Chuỗi số có thể được chuyển thành số trong ngữ cảnh toán học. Chuỗi không phải số có thể tạo warning hoặc được chuyển đổi theo quy tắc MySQL và SQL mode. Không dựa vào chuyển đổi ngầm cho dữ liệu người dùng.

Hãy dùng `CAST()` hoặc `CONVERT()` khi muốn thể hiện rõ kiểu:

```sql
SELECT
    CAST(raw_quantity AS DECIMAL(12, 3)) *
    CAST(raw_price AS DECIMAL(14, 2)) AS calculated_amount
FROM imported_order_lines;
```

Trước khi cast dữ liệu import, nên kiểm tra chuỗi đầu vào có hợp lệ. `CAST()` không thay thế validation; giá trị sai vẫn có thể tạo warning hoặc kết quả chuyển đổi không mong muốn.

## 10. NULL trong biểu thức số học

Nếu một toán hạng là `NULL`, kết quả của phép toán số học thông thường cũng là `NULL`:

```sql
SELECT
    10 + NULL AS add_result,
    10 - NULL AS subtract_result,
    10 * NULL AS multiply_result,
    10 / NULL AS divide_result;
```

`NULL` có nghĩa là thiếu hoặc chưa biết giá trị, không phải số 0. Vì vậy, không nên tự động thay mọi `NULL` bằng 0 nếu nghiệp vụ không quy định như vậy.

Nếu quy tắc nghiệp vụ xác định `NULL` phải được xem như 0, dùng `COALESCE()` rõ ràng:

```sql
SELECT COALESCE(shipping_fee, 0) + item_total AS payable_amount
FROM orders;
```

Nếu `NULL` có nghĩa là “chưa tính phí vận chuyển”, thay bằng 0 có thể làm báo cáo sai. Hãy phân biệt “không có giá trị”, “giá trị bằng 0” và “chưa xác định”.

### 10.1. NULLIF để bảo vệ mẫu số

`NULLIF(a, b)` trả về `NULL` nếu `a = b`; nếu không thì trả về `a`. Kết hợp với phép chia để tránh mẫu số bằng 0:

```sql
SELECT
    revenue / NULLIF(order_count, 0) AS average_order_value
FROM customer_statistics;
```

Khi `order_count = 0`, `NULLIF()` trả về `NULL`, nên kết quả phép chia là `NULL`. Đây là cách ngắn gọn khi kết quả “không xác định” phù hợp với nghiệp vụ.

### 10.2. CASE khi cần quy tắc kết quả cụ thể

Nếu muốn biểu diễn rõ trường hợp mẫu số bằng 0:

```sql
SELECT
    CASE
        WHEN order_count = 0 THEN 0
        ELSE revenue / order_count
    END AS average_order_value
FROM customer_statistics;
```

Chỉ trả về 0 nếu nghiệp vụ định nghĩa trung bình khi không có đơn bằng 0. Nếu không có đơn nghĩa là không có cơ sở tính trung bình, `NULL` thường phản ánh chính xác hơn.

## 11. Chia cho 0 và xử lý lỗi

Phép chia có mẫu số bằng 0 không tạo ra một giá trị số hợp lệ. Trong một truy vấn `SELECT`, biểu thức như `1 / 0` thường trả về `NULL` kèm warning. Trong câu lệnh ghi dữ liệu như `INSERT` hoặc `UPDATE`, hành vi có thể nghiêm ngặt hơn và có thể bị từ chối tùy SQL mode, đặc biệt khi bật strict mode.

Kiểm tra hành vi trên session hiện tại:

```sql
SELECT 1 / 0 AS division_result;
SHOW WARNINGS;
```

`SHOW WARNINGS` phải được chạy ngay sau câu lệnh cần kiểm tra vì một câu lệnh tiếp theo có thể thay thế danh sách warning hiện hành.

### 11.1. Cách viết an toàn với NULLIF

```sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
```

### 11.2. Cách viết an toàn với CASE

```sql
SELECT
    CASE
        WHEN denominator IS NULL OR denominator = 0 THEN NULL
        ELSE numerator / denominator
    END AS ratio
FROM metrics;
```

### 11.3. Không dùng IFNULL tùy tiện để che mẫu số 0

Ví dụ sau tránh lỗi nhưng thay đổi ý nghĩa toán học:

```sql
-- Không nên dùng nếu chưa có quy tắc nghiệp vụ:
SELECT numerator / IFNULL(denominator, 1)
FROM metrics;
```

Khi mẫu số `NULL`, câu lệnh tự thay bằng 1. Kết quả khi đó không còn phản ánh tỷ lệ ban đầu. Hãy dùng `NULLIF(denominator, 0)` để xử lý riêng mẫu số bằng 0 và quyết định rõ cách xử lý `NULL`.

## 12. Các hàm thường kết hợp với biểu thức số học

| Hàm | Mục đích | Ví dụ |
|---|---|---|
| `ABS(x)` | Giá trị tuyệt đối | `ABS(-12)` → `12` |
| `SIGN(x)` | Dấu của số: -1, 0 hoặc 1 | `SIGN(-8)` → `-1` |
| `ROUND(x, d)` | Làm tròn đến `d` chữ số | `ROUND(12.345, 2)` |
| `TRUNCATE(x, d)` | Cắt phần thập phân sau `d` chữ số | `TRUNCATE(12.349, 2)` → `12.34` |
| `FLOOR(x)` | Số nguyên lớn nhất không vượt quá x | `FLOOR(3.8)` → `3` |
| `CEIL(x)` / `CEILING(x)` | Số nguyên nhỏ nhất không nhỏ hơn x | `CEIL(3.2)` → `4` |
| `MOD(a, b)` | Phần dư | `MOD(17, 5)` → `2` |
| `POW(a, b)` / `POWER(a, b)` | Lũy thừa | `POW(2, 3)` → `8` |
| `SQRT(x)` | Căn bậc hai | `SQRT(81)` → `9` |

Ví dụ phân biệt làm tròn, cắt và floor với số âm:

```sql
SELECT
    ROUND(-3.7) AS rounded_value,
    TRUNCATE(-3.7, 0) AS truncated_value,
    FLOOR(-3.7) AS floor_value,
    CEIL(-3.7) AS ceil_value;
```

`TRUNCATE()` cắt phần lẻ về phía 0; `FLOOR()` đi về số nguyên nhỏ hơn; `CEIL()` đi về số nguyên lớn hơn. Ba hàm không thể thay thế tùy tiện cho nhau.

## 13. Ví dụ nghiệp vụ: tiền hàng, chiết khấu và thuế

Giả sử một dòng hóa đơn có số lượng, đơn giá, tỷ lệ giảm giá và thuế suất. Công thức cần được diễn đạt rõ thứ tự:

1. Thành tiền trước giảm giá = số lượng × đơn giá.
2. Tiền giảm giá = thành tiền trước giảm giá × tỷ lệ giảm giá / 100.
3. Thành tiền sau giảm giá = thành tiền trước giảm giá − tiền giảm giá.
4. Tiền thuế = thành tiền sau giảm giá × thuế suất / 100.
5. Tổng thanh toán = thành tiền sau giảm giá + tiền thuế.

Ví dụ truy vấn:

```sql
SELECT
    order_item_id,
    quantity,
    unit_price,
    discount_rate,
    tax_rate,
    ROUND(quantity * unit_price, 2) AS gross_amount,
    ROUND(quantity * unit_price * discount_rate / 100, 2) AS discount_amount,
    ROUND(
        quantity * unit_price * (1 - discount_rate / 100),
        2
    ) AS net_amount,
    ROUND(
        quantity * unit_price * (1 - discount_rate / 100)
        * tax_rate / 100,
        2
    ) AS tax_amount
FROM order_items;
```

Đây là một công thức minh họa. Trong hệ thống tài chính thực tế, phải xác định rõ:

- Tỷ lệ lưu theo đơn vị phần trăm (ví dụ 10.00) hay tỷ lệ thập phân (0.10).
- Làm tròn ở từng dòng, từng loại thuế hay chỉ ở tổng hóa đơn.
- Thuế được tính trước hay sau chiết khấu.
- Có quy tắc riêng cho từng loại tiền tệ hay không.
- Cần lưu giá trị đã tính để audit hay tính lại từ dữ liệu gốc.

Đừng để cùng một column lúc lưu `10` (10%) và lúc lưu `0.10` (10%). Hãy đặt tên và constraint để thể hiện đơn vị, ví dụ `discount_percent` hoặc `discount_rate` theo một quy ước cố định.

## 14. Biểu thức trong WHERE và khả năng sử dụng index

Một biểu thức số học trong `WHERE` có thể khiến điều kiện khó sử dụng index trên column gốc nếu MySQL phải tính toán trên từng hàng.

Ví dụ bảng `products` có index trên `unit_price`:

```sql
-- Biểu thức trên cột có thể làm index range khó được sử dụng:
SELECT product_id, unit_price
FROM products
WHERE unit_price * 1.1 > 100000;
```

Vì hệ số 1.1 là hằng số dương, có thể biến đổi điều kiện tương đương về mặt toán học:

```sql
SELECT product_id, unit_price
FROM products
WHERE unit_price > 100000 / 1.1;
```

Hãy kiểm tra tính tương đương về kiểu số, precision và làm tròn trước khi viết lại. Với các biểu thức phức tạp hoặc phụ thuộc nhiều column, không phải lúc nào cũng có thể chuyển đổi thành điều kiện trên một column đơn.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT product_id, unit_price
FROM products
WHERE unit_price > 100000 / 1.1;
```

Đừng giả định biểu thức đã được viết lại chắc chắn dùng index; optimizer còn cân nhắc độ chọn lọc, thống kê và chi phí truy cập.

### 14.1. Generated column cho biểu thức được dùng thường xuyên

Nếu hệ thống thường lọc hoặc sắp xếp theo thành tiền của một dòng hàng, có thể cân nhắc generated column:

```sql
CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity      DECIMAL(12, 3) NOT NULL,
    unit_price    DECIMAL(14, 2) NOT NULL,
    line_amount   DECIMAL(18, 2)
        GENERATED ALWAYS AS (ROUND(quantity * unit_price, 2)) STORED,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_line_amount (line_amount)
);
```

Generated column lưu hoặc tính giá trị theo định nghĩa biểu thức. `STORED` lưu giá trị được tính khi ghi; `VIRTUAL` tính khi đọc theo cơ chế của MySQL. Có thể lập index trên generated column khi kiểu và biểu thức đáp ứng điều kiện của MySQL.

Nếu dùng MySQL 8.0.13 trở lên, functional index cũng là lựa chọn cho một số biểu thức:

```sql
CREATE INDEX idx_items_amount_expression
ON order_items ((quantity * unit_price));
```

Functional index có yêu cầu về cú pháp, kiểu và tính hợp lệ của biểu thức; hãy xác minh trên phiên bản server mục tiêu. Không tạo index chỉ vì biểu thức xuất hiện trong một truy vấn hiếm; index làm tăng dung lượng và chi phí ghi.

## 15. Cập nhật dữ liệu bằng biểu thức số học

`UPDATE` có thể dùng giá trị hiện tại của column để tính giá trị mới:

```sql
UPDATE products
SET stock_quantity = stock_quantity - 1
WHERE product_id = 1001
  AND stock_quantity >= 1;
```

Điều kiện `stock_quantity >= 1` bảo đảm không trừ dưới 0 nếu nhiều request cạnh tranh cùng cập nhật. Ứng dụng cần kiểm tra update count:

- Một hàng bị cập nhật: thao tác trừ kho thành công.
- Không hàng nào bị cập nhật: sản phẩm không tồn tại hoặc không đủ tồn kho (cần truy vấn/logic riêng nếu muốn phân biệt).

Với nghiệp vụ tiền, nên thực hiện phép tính trong một câu lệnh có điều kiện và transaction phù hợp thay vì đọc giá trị về ứng dụng, tính ở client rồi ghi đè giá trị cũ. Cách cập nhật nguyên tử giảm nguy cơ lost update.

Ví dụ trừ số dư:

```sql
UPDATE accounts
SET balance = balance - 50000.00
WHERE account_id = 101
  AND balance >= 50000.00;
```

Đây chỉ là một bước trong nghiệp vụ chuyển tiền; hệ thống thực tế cần transaction bao gồm ghi nợ, ghi có, kiểm tra affected rows và rollback nếu bất kỳ bước nào không đạt.

## 16. Tràn số, precision và cảnh báo

Mỗi kiểu số có miền giá trị và precision hữu hạn. Kết quả phép tính có thể vượt miền của kiểu đích hoặc không vừa precision/scale được khai báo.

Ví dụ column `DECIMAL(8,2)` chỉ chứa tối đa tám chữ số tổng cộng, trong đó hai chữ số ở phần thập phân. Nếu phép tính tạo giá trị vượt phạm vi, MySQL có thể báo lỗi hoặc warning tùy câu lệnh, SQL mode và ngữ cảnh chuyển đổi.

Kiểm tra giá trị và cảnh báo sau thao tác thử nghiệm:

```sql
SELECT CAST(99999999.99 AS DECIMAL(8, 2)) AS boundary_value;
SHOW WARNINGS;
```

Hãy kiểm thử biên trên dữ liệu đại diện và dữ liệu cực đại dự kiến. Không chỉ kiểm tra trường hợp trung bình.

Các bước thiết kế an toàn:

1. Xác định giá trị nhỏ nhất/lớn nhất có thể có của từng toán hạng.
2. Tính miền kết quả của phép cộng, nhân, chia hoặc tổng hợp.
3. Chọn kiểu dữ liệu đủ precision và scale.
4. Xác định quy tắc làm tròn và thời điểm làm tròn.
5. Kiểm tra SQL mode và warning trong môi trường tương ứng.
6. Dùng `CAST()` khi cần cố định kiểu kết quả ở ranh giới lưu trữ hoặc giao diện.

## 17. Bài tập thực hành

### Bài tập 1: Thứ tự ưu tiên

Chạy các biểu thức sau:

```sql
SELECT 10 + 6 * 2;
SELECT (10 + 6) * 2;
SELECT 20 / 5 * 2;
SELECT 20 DIV 3 * 2;
```

**Yêu cầu:** giải thích thứ tự thực hiện và viết lại bằng dấu ngoặc để thể hiện ý nghĩa rõ ràng.

### Bài tập 2: So sánh `/` và DIV

Chạy:

```sql
SELECT
    17 / 5,
    17 DIV 5,
    -17 / 5,
    -17 DIV 5,
    FLOOR(-17 / 5);
```

**Yêu cầu:** giải thích vì sao `DIV` khác `FLOOR()` khi kết quả âm.

### Bài tập 3: Phần dư và phân bổ

Chia 103 sản phẩm cho 6 nhóm. Tính số sản phẩm tối thiểu mỗi nhóm nhận và số sản phẩm còn dư bằng `DIV` và `MOD`.

**Yêu cầu:** đề xuất quy tắc phân bổ phần dư để tổng số sản phẩm sau phân bổ vẫn bằng 103.

### Bài tập 4: Kiểu DECIMAL và DOUBLE

So sánh kết quả cộng `0.1 + 0.2` khi dùng `DECIMAL` và `DOUBLE`.

**Yêu cầu:** giải thích kiểu nào phù hợp với tiền và vì sao không nên so sánh bằng tuyệt đối các kết quả approximate.

### Bài tập 5: Chia cho 0 và NULLIF

Tạo bảng thống kê có `revenue` và `order_count`, trong đó có hàng `order_count = 0`. Tính giá trị trung bình bằng `/`, sau đó dùng `NULLIF()`.

**Yêu cầu:** ghi nhận kết quả và warning; quyết định kết quả nghiệp vụ nên là `NULL` hay 0.

### Bài tập 6: Phép trừ với UNSIGNED

Tạo cột `quantity INT UNSIGNED`, thử trừ một số lớn hơn giá trị hiện có trong môi trường thử nghiệm.

**Yêu cầu:** quan sát lỗi hoặc kết quả theo SQL mode; viết câu `UPDATE` có điều kiện để không tạo tồn kho âm.

### Bài tập 7: Tính tiền và làm tròn

Tạo bảng dòng hóa đơn có `quantity`, `unit_price`, `discount_percent` và `tax_percent`. Viết truy vấn tính gross amount, discount, net amount và tax.

**Yêu cầu:** nêu rõ quy tắc làm tròn ở từng bước và thử so sánh với cách chỉ làm tròn tổng cuối cùng.

### Bài tập 8: Kiểm tra index với biểu thức

Tạo index trên `unit_price`. So sánh `EXPLAIN` của điều kiện `unit_price * 1.1 > ...` với điều kiện đã biến đổi tương đương.

**Yêu cầu:** ghi lại access type, key và số hàng ước lượng; giải thích khi nào nên cân nhắc generated column hoặc functional index.

## 18. Checklist review biểu thức số học

- [ ] Toán tử được chọn đúng ý nghĩa: `/`, `DIV`, `%` hay `MOD()`.
- [ ] Thứ tự ưu tiên được thể hiện rõ bằng dấu ngoặc khi cần.
- [ ] Kiểu dữ liệu của toán hạng là exact hay approximate đã được xem xét.
- [ ] Tiền tệ và số liệu cần độ chính xác thập phân dùng `DECIMAL` phù hợp.
- [ ] Precision/scale của kết quả đủ cho giá trị lớn nhất dự kiến.
- [ ] Phép chia có xử lý mẫu số 0 và `NULL` theo nghiệp vụ.
- [ ] Phép tính trên `UNSIGNED` không tạo underflow ngoài ý muốn.
- [ ] Quy tắc làm tròn/cắt được xác định rõ.
- [ ] Chuyển kiểu ngầm được thay bằng `CAST()` khi cần tính xác định.
- [ ] Điều kiện `WHERE` không bọc column có index bằng biểu thức nếu có cách viết tương đương tốt hơn.
- [ ] Cập nhật số dư/tồn kho dùng điều kiện nguyên tử và kiểm tra affected rows.
- [ ] Các trường hợp biên, warning và SQL mode được kiểm thử.

## 19. Ghi nhớ

Trong MySQL, nhân, chia, `DIV`, modulo được thực hiện trước cộng và trừ; dấu ngoặc giúp xác định rõ công thức. `/` giữ phần thập phân, `DIV` cắt phần lẻ về 0 và `%`/`MOD()` trả về phần dư. `DIV` khác `FLOOR()` với số âm. Kiểu `DECIMAL` phù hợp với tiền và phép tính thập phân cần chính xác; `FLOAT`/`DOUBLE` là số gần đúng.

Biểu thức số học còn chịu ảnh hưởng bởi `NULL`, chia cho 0, `UNSIGNED`, precision/scale và SQL mode. Hãy kiểm soát mẫu số bằng `NULLIF()` hoặc `CASE`, dùng `CAST()` khi cần kiểu rõ ràng, xác định quy tắc làm tròn theo nghiệp vụ và kiểm tra execution plan khi biểu thức tham gia điều kiện lọc. Một công thức SQL đúng không chỉ cho kết quả chạy được mà còn phải giữ đúng ý nghĩa dữ liệu ở các trường hợp biên.
