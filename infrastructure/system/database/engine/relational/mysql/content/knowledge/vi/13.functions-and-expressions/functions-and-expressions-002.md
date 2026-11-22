# ROUND, TRUNCATE, MOD, CEIL, FLOOR và quy tắc số âm

MySQL cung cấp các hàm toán học để làm tròn, cắt phần thập phân, tính phần dư và lấy số nguyên ở phía trên hoặc phía dưới một giá trị. Các hàm `ROUND()`, `TRUNCATE()`, `MOD()`, `CEIL()` và `FLOOR()` thường xuất hiện trong truy vấn báo cáo, tính tiền, chia nhóm dữ liệu, phân trang theo bucket và xử lý số đo.

Điểm dễ gây lỗi là cách các hàm xử lý số âm không giống nhau. `TRUNCATE()` cắt về phía 0; `CEIL()` đi về phía dương vô cùng; `FLOOR()` đi về phía âm vô cùng; `MOD()` giữ dấu của số bị chia; còn `ROUND()` có quy tắc riêng cho giá trị chính xác và giá trị dấu phẩy động gần đúng. Hiểu đúng các quy tắc này giúp tránh sai lệch trong tính toán nghiệp vụ.

## 1. Tổng quan các hàm

| Hàm | Tác dụng | Ví dụ với số dương | Ví dụ với số âm |
| --- | --- | --- | --- |
| `ROUND(x, d)` | Làm tròn đến `d` chữ số thập phân; `d` âm làm tròn bên trái dấu thập phân | `ROUND(2.56, 1) = 2.6` | `ROUND(-2.56, 1) = -2.6` |
| `TRUNCATE(x, d)` | Cắt bỏ phần vượt quá `d` chữ số mà không làm tròn | `TRUNCATE(2.59, 1) = 2.5` | `TRUNCATE(-2.59, 1) = -2.5` |
| `MOD(n, m)` | Lấy phần dư của phép chia `n` cho `m` | `MOD(11, 4) = 3` | `MOD(-11, 4) = -3` |
| `CEIL(x)` | Lấy số nguyên nhỏ nhất lớn hơn hoặc bằng `x` | `CEIL(2.1) = 3` | `CEIL(-2.1) = -2` |
| `FLOOR(x)` | Lấy số nguyên lớn nhất nhỏ hơn hoặc bằng `x` | `FLOOR(2.9) = 2` | `FLOOR(-2.1) = -3` |

`CEIL()` là tên ngắn của `CEILING()`. Hai tên này có cùng ý nghĩa. Các hàm trên trả về giá trị tính toán trong biểu thức; chúng không tự thay đổi dữ liệu đang lưu trong bảng. Muốn lưu kết quả, cần dùng `UPDATE`, `INSERT` hoặc một phép ghi dữ liệu khác.

## 2. ROUND(): làm tròn số

Cú pháp:

```sql
ROUND(number [, decimals])
```

- `number` là giá trị cần làm tròn.
- `decimals` là số chữ số cần giữ sau dấu thập phân.
- Nếu bỏ `decimals`, MySQL mặc định làm tròn đến số nguyên gần nhất.
- Nếu `decimals` dương, làm tròn đến số chữ số thập phân tương ứng.
- Nếu `decimals` bằng 0, làm tròn đến số nguyên.
- Nếu `decimals` âm, làm tròn các chữ số ở bên trái dấu thập phân.

Ví dụ:

```sql
SELECT
    ROUND(12.3456) AS integer_value,
    ROUND(12.3456, 2) AS two_decimals,
    ROUND(12.3456, 1) AS one_decimal,
    ROUND(12.3456, 0) AS zero_decimals,
    ROUND(12345.67, -1) AS nearest_ten,
    ROUND(12345.67, -2) AS nearest_hundred;
```

Kết quả tương ứng là `12`, `12.35`, `12.3`, `12`, `12350` và `12300`.

### 2.1. ROUND với số âm

Với đối số chính xác (exact-value) như số nguyên hoặc `DECIMAL`, MySQL làm tròn trường hợp đúng nửa đơn vị theo hướng ra xa số 0. Vì vậy, `2.5` thành `3`, còn `-2.5` thành `-3`.

```sql
SELECT
    ROUND(2.5) AS positive_half,
    ROUND(-2.5) AS negative_half,
    ROUND(2.45, 1) AS positive_tie,
    ROUND(-2.45, 1) AS negative_tie,
    ROUND(149, -1) AS positive_tens,
    ROUND(-149, -1) AS negative_tens;
```

Với các giá trị chính xác trong ví dụ, kết quả lần lượt là `3`, `-3`, `2.5`, `-2.5`, `150` và `-150`.

Hãy chú ý trường hợp `-2.45` làm tròn đến một chữ số: kết quả là `-2.5`, tức độ lớn tăng lên khi làm tròn ở điểm giữa. Không nên mô tả quy tắc này đơn giản là “luôn tăng số lên”, vì với số âm hướng ra xa 0 có nghĩa là giá trị số học nhỏ hơn.

### 2.2. ROUND với số chính xác và số gần đúng

MySQL phân biệt hai nhóm giá trị:

- **Exact-value:** số nguyên và `DECIMAL`/`NUMERIC`. Quy tắc điểm giữa được làm tròn ra xa 0.
- **Approximate-value:** `FLOAT`, `DOUBLE` và biểu thức dấu phẩy động. Kết quả `ROUND()` phụ thuộc thư viện toán học của hệ thống; trên nhiều nền tảng, điểm giữa được làm tròn theo quy tắc gần nhất với số chẵn (round to nearest even).

Có thể quan sát khác biệt bằng cách so sánh literal chính xác với literal có ký hiệu số mũ:

```sql
SELECT
    ROUND(2.5) AS exact_value_round,
    ROUND(2.5E0) AS approximate_value_round;
```

`2.5` là literal exact-value; `2.5E0` là literal approximate-value. Kết quả của biểu thức approximate có thể khác tùy thư viện C và nền tảng, vì vậy không dùng ví dụ đó làm quy tắc tài chính có tính di động.

Với tiền tệ hoặc số thập phân cần kết quả lặp lại được, ưu tiên `DECIMAL` và literal chính xác. Tránh chuyển giá trị sang `DOUBLE` trước khi làm tròn nếu nghiệp vụ yêu cầu quy tắc decimal rõ ràng.

## 3. TRUNCATE(): cắt phần thập phân, không làm tròn

Cú pháp:

```sql
TRUNCATE(number, decimals)
```

`TRUNCATE()` giữ lại số chữ số được chỉ định và bỏ phần còn lại. Khác với `ROUND()`, hàm không xét chữ số kế tiếp để quyết định tăng hay giảm. Với số âm, thao tác cắt diễn ra về phía 0.

```sql
SELECT
    TRUNCATE(12.349, 2) AS positive_value,
    TRUNCATE(-12.349, 2) AS negative_value,
    TRUNCATE(149, -1) AS positive_tens,
    TRUNCATE(-149, -1) AS negative_tens;
```

Kết quả lần lượt là `12.34`, `-12.34`, `140` và `-140`.

### 3.1. Dương và âm: TRUNCATE luôn hướng về 0

So sánh `TRUNCATE()` với `FLOOR()` trên số âm:

```sql
SELECT
    TRUNCATE(-2.9, 0) AS truncated_value,
    FLOOR(-2.9) AS floored_value,
    CEIL(-2.9) AS ceiled_value;
```

Kết quả là `-2`, `-3` và `-2`. `TRUNCATE(-2.9, 0)` bỏ phần thập phân để tiến về 0; `FLOOR(-2.9)` phải đi xuống số nguyên nhỏ hơn, tức `-3`.

### 3.2. D âm trong TRUNCATE

Tham số `decimals` âm làm hàm bỏ các chữ số bên phải hàng tương ứng:

```sql
SELECT
    TRUNCATE(9876.543, -1) AS tens,
    TRUNCATE(9876.543, -2) AS hundreds,
    TRUNCATE(9876.543, -3) AS thousands,
    TRUNCATE(-9876.543, -2) AS negative_hundreds;
```

Kết quả là `9870`, `9800`, `9000` và `-9800`. Các chữ số bị bỏ không làm phát sinh bước làm tròn.

Không nên dùng `TRUNCATE()` thay cho `ROUND()` trong tính tiền chỉ vì muốn kết quả có hai chữ số thập phân. Cắt phần dư có thể tạo thiên lệch có hệ thống, đặc biệt khi áp dụng cho hàng triệu giao dịch. Chỉ dùng khi quy tắc nghiệp vụ hoặc quy định kế toán thực sự yêu cầu cắt.

## 4. ROUND và TRUNCATE khác nhau ở điểm nào?

Hai hàm có thể trả cùng kết quả với một số đầu vào, nhưng ngữ nghĩa khác nhau:

| Biểu thức | ROUND | TRUNCATE | Giải thích |
| --- | ---: | ---: | --- |
| `12.346`, 2 chữ số | `12.35` | `12.34` | ROUND xét chữ số tiếp theo; TRUNCATE bỏ phần dư |
| `12.341`, 2 chữ số | `12.34` | `12.34` | Chữ số tiếp theo không làm ROUND tăng |
| `-12.346`, 2 chữ số | `-12.35` | `-12.34` | TRUNCATE vẫn đi về 0 |
| `149`, `decimals = -1` | `150` | `140` | ROUND đến hàng chục; TRUNCATE bỏ hàng đơn vị |
| `-149`, `decimals = -1` | `-150` | `-140` | Cùng quy tắc nhưng cần chú ý hướng số âm |

Chọn hàm theo yêu cầu nghiệp vụ:

- Cần làm tròn theo quy tắc số học: dùng `ROUND()`.
- Cần loại bỏ phần chữ số vượt quá mà không làm tròn: dùng `TRUNCATE()`.
- Cần lấy biên nguyên phía trên hoặc phía dưới: dùng `CEIL()` hoặc `FLOOR()`.

## 5. CEIL() và CEILING(): lấy số nguyên phía trên

Cú pháp:

```sql
CEIL(number)
CEILING(number)
```

Hai hàm trả về số nguyên nhỏ nhất lớn hơn hoặc bằng đối số. Có thể hiểu đây là phép làm tròn về phía dương vô cùng.

```sql
SELECT
    CEIL(2.1) AS positive_fraction,
    CEIL(2.0) AS positive_integer,
    CEIL(-2.1) AS negative_fraction,
    CEIL(-2.0) AS negative_integer;
```

Kết quả lần lượt là `3`, `2`, `-2` và `-2`.

Ví dụ ứng dụng: tính số trang hoặc số kiện cần dùng khi mỗi trang/kiện chứa tối đa một số lượng cố định. Nếu có 21 sản phẩm và mỗi thùng chứa 10 sản phẩm, cần `CEIL(21 / 10) = 3` thùng.

Để tránh phép chia số nguyên ngoài ý muốn, có thể dùng số decimal hoặc ép kiểu rõ ràng:

```sql
SELECT CEIL(21 / 10.0) AS box_count;
```

## 6. FLOOR(): lấy số nguyên phía dưới

Cú pháp:

```sql
FLOOR(number)
```

`FLOOR()` trả về số nguyên lớn nhất nhỏ hơn hoặc bằng đối số. Đây là phép làm tròn về phía âm vô cùng.

```sql
SELECT
    FLOOR(2.9) AS positive_fraction,
    FLOOR(2.0) AS positive_integer,
    FLOOR(-2.1) AS negative_fraction,
    FLOOR(-2.0) AS negative_integer;
```

Kết quả lần lượt là `2`, `2`, `-3` và `-2`.

Với số dương, `FLOOR(x)` thường trông giống việc bỏ phần thập phân. Với số âm, kết quả khác `TRUNCATE(x, 0)`:

```sql
SELECT
    FLOOR(-8.7) AS floor_result,
    TRUNCATE(-8.7, 0) AS truncate_result;
```

Kết quả là `-9` và `-8`. Đây là khác biệt quan trọng khi tính khoảng, bucket hoặc phân loại giá trị âm.

## 7. Phân biệt ROUND, TRUNCATE, CEIL và FLOOR trên số âm

Hãy dùng cùng một giá trị để nhìn rõ hướng xử lý:

```sql
SELECT
    -2.7 AS original_value,
    ROUND(-2.7) AS rounded,
    TRUNCATE(-2.7, 0) AS truncated,
    CEIL(-2.7) AS ceiling_value,
    FLOOR(-2.7) AS floor_value;
```

| Hàm | Kết quả | Hướng xử lý |
| --- | ---: | --- |
| `ROUND(-2.7)` | `-3` | Số nguyên gần nhất |
| `TRUNCATE(-2.7, 0)` | `-2` | Về phía 0 |
| `CEIL(-2.7)` | `-2` | Về phía dương vô cùng |
| `FLOOR(-2.7)` | `-3` | Về phía âm vô cùng |

Một cách ghi nhớ:

- `TRUNCATE`: bỏ phần dư, tiến về 0.
- `CEIL`: đi lên trên trục số.
- `FLOOR`: đi xuống dưới trục số.
- `ROUND`: chọn số gần nhất theo quy tắc làm tròn của kiểu số.

Không nên diễn giải “lên” và “xuống” theo độ lớn tuyệt đối. Trên trục số, `-2` lớn hơn `-3`, vì vậy `CEIL(-2.7)` là `-2` và `FLOOR(-2.7)` là `-3`.

## 8. MOD(): lấy phần dư của phép chia

Cú pháp:

```sql
MOD(dividend, divisor)
```

`MOD(n, m)` trả về phần dư khi chia `n` cho `m`. Toán tử `%` là cách viết ngắn tương đương:

```sql
SELECT
    MOD(11, 4) AS function_result,
    11 % 4 AS operator_result;
```

Cả hai biểu thức đều trả về `3`.

`MOD()` thường dùng để:

- Kiểm tra số chẵn/lẻ: `MOD(id, 2) = 0`.
- Chia dữ liệu vào các nhóm tuần hoàn.
- Xác định vị trí trong chu kỳ.
- Tính phần dư khi chia đơn vị hoặc số lượng.

Ví dụ lấy các bản ghi có ID chẵn:

```sql
SELECT id, name
FROM products
WHERE MOD(id, 2) = 0;
```

Nếu cả hai đối số là số nguyên, kết quả là phần dư nguyên. `MOD()` cũng hỗ trợ số thập phân:

```sql
SELECT MOD(34.5, 3) AS remainder;
```

Kết quả là `1.5`.

## 9. Dấu của MOD khi có số âm

Trong MySQL, phần dư của `MOD(n, m)` mang dấu của số bị chia `n` (đối số thứ nhất), nếu phần dư khác 0. Vì vậy, kết quả có thể âm:

```sql
SELECT
    MOD(11, 4) AS positive_positive,
    MOD(-11, 4) AS negative_positive,
    MOD(11, -4) AS positive_negative,
    MOD(-11, -4) AS negative_negative;
```

Kết quả lần lượt là `3`, `-3`, `3` và `-3`.

Điều này khác với một số định nghĩa modulo trong toán học hoặc ngôn ngữ lập trình vốn luôn chuẩn hóa kết quả về miền không âm khi modulo dương. Nếu nghiệp vụ cần bucket từ `0` đến `m - 1` và `m` luôn dương, có thể chuẩn hóa:

```sql
SELECT MOD(MOD(-11, 4) + 4, 4) AS normalized_remainder;
```

Kết quả là `1`. Công thức chuẩn hóa này giả định số chia dương và khác 0. Nếu số chia có thể âm hoặc bằng 0, hãy xác định quy tắc nghiệp vụ riêng và kiểm tra đầu vào trước khi tính.

### 9.1. MOD với số chia bằng 0

Nếu đối số thứ hai bằng 0, `MOD()` trả về `NULL`:

```sql
SELECT MOD(10, 0) AS result;
```

Kết quả là `NULL`. Khi dữ liệu có thể chứa số chia bằng 0, hãy kiểm tra trước hoặc xử lý kết quả `NULL` bằng logic rõ ràng. Không giả định phép chia modulo luôn trả về số.

## 10. ROUND và TRUNCATE với số chữ số âm

Tham số `decimals` âm cho phép thao tác với các hàng chục, trăm, nghìn... thay vì chỉ phần thập phân.

```sql
SELECT
    ROUND(1234.56, -1) AS round_tens,
    ROUND(1234.56, -2) AS round_hundreds,
    ROUND(1234.56, -3) AS round_thousands,
    TRUNCATE(1234.56, -1) AS truncate_tens,
    TRUNCATE(1234.56, -2) AS truncate_hundreds,
    TRUNCATE(1234.56, -3) AS truncate_thousands;
```

Kết quả:

| Biểu thức | Kết quả |
| --- | ---: |
| `ROUND(1234.56, -1)` | `1230` |
| `ROUND(1234.56, -2)` | `1200` |
| `ROUND(1234.56, -3)` | `1000` |
| `TRUNCATE(1234.56, -1)` | `1230` |
| `TRUNCATE(1234.56, -2)` | `1200` |
| `TRUNCATE(1234.56, -3)` | `1000` |

Trong ví dụ này kết quả tình cờ giống nhau vì chữ số bị bỏ không làm `ROUND()` tăng lên. Với `149`, hai hàm khác nhau: `ROUND(149, -1) = 150`, còn `TRUNCATE(149, -1) = 140`.

Với số âm, quy tắc hướng về 0 của `TRUNCATE()` vẫn giữ nguyên:

```sql
SELECT
    ROUND(-149, -1) AS rounded_negative,
    TRUNCATE(-149, -1) AS truncated_negative;
```

Kết quả lần lượt là `-150` và `-140`.

## 11. Ứng dụng trong tính tiền và báo cáo

Với dữ liệu tiền tệ, nên lưu bằng `DECIMAL(p,s)` thay vì `FLOAT`/`DOUBLE` nếu cần số thập phân chính xác. Ví dụ:

```sql
CREATE TABLE invoice_lines (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity DECIMAL(10, 3) NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    tax_rate DECIMAL(5, 4) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Tính tổng dòng và làm tròn đến hai chữ số:

```sql
SELECT
    id,
    quantity * unit_price AS raw_subtotal,
    ROUND(quantity * unit_price, 2) AS rounded_subtotal,
    ROUND(quantity * unit_price * tax_rate, 2) AS rounded_tax
FROM invoice_lines;
```

### 11.1. Làm tròn từng dòng hay làm tròn tổng?

Hai cách tính có thể cho kết quả khác nhau:

```sql
-- Làm tròn từng dòng trước khi cộng
SELECT SUM(ROUND(quantity * unit_price * tax_rate, 2)) AS sum_of_rounded_tax
FROM invoice_lines;

-- Cộng giá trị chính xác trước, rồi làm tròn tổng
SELECT ROUND(SUM(quantity * unit_price * tax_rate), 2) AS rounded_total_tax
FROM invoice_lines;
```

Đây không chỉ là khác biệt kỹ thuật. Quy định kế toán, thuế hoặc hợp đồng có thể yêu cầu làm tròn ở cấp dòng, cấp hóa đơn hoặc cấp kỳ báo cáo. Hãy thống nhất quy tắc với nghiệp vụ trước khi viết SQL; không chọn cách cho ra số “đẹp” hơn.

`TRUNCATE()` có thể hữu ích khi một quy tắc yêu cầu cắt phần nhỏ hơn đơn vị thanh toán, nhưng việc cắt luôn về 0 có thể gây thiên lệch. Không dùng `TRUNCATE()` thay `ROUND()` nếu yêu cầu là làm tròn chuẩn.

### 11.2. Lưu giá trị đã làm tròn

Một biểu thức `SELECT ROUND(...)` chỉ thay đổi kết quả trả về. Nếu muốn lưu giá trị làm tròn vào cột, cần thực hiện DML:

```sql
UPDATE invoice_lines
SET unit_price = ROUND(unit_price, 2)
WHERE id = 100;
```

Trước khi chạy `UPDATE` hàng loạt, hãy kiểm tra phạm vi bằng `SELECT`, backup khi cần và xác nhận việc thay đổi giá trị gốc có đúng nghiệp vụ không. Nếu chỉ cần hiển thị, nên làm tròn trong truy vấn đọc hoặc tầng trình bày thay vì ghi đè dữ liệu nguồn.

## 12. Ứng dụng trong chia nhóm và phân bổ

`MOD()` có thể chia ID thành các nhóm tuần hoàn:

```sql
SELECT
    id,
    MOD(id, 4) AS bucket_no
FROM events
ORDER BY id;
```

Với ID không âm, `bucket_no` nhận các giá trị `0`, `1`, `2`, `3` theo chu kỳ. Cách này có thể dùng trong bài tập chia shard hoặc phân phối công việc đơn giản, nhưng không phải chiến lược sharding hoàn chỉnh: cần xem phân bố ID, khả năng mở rộng, thay đổi số shard và yêu cầu định tuyến.

`CEIL()` và `FLOOR()` cũng hữu ích khi tính nhóm theo kích thước cố định. Ví dụ tính số trang cần thiết khi mỗi trang chứa 25 hàng:

```sql
SELECT CEIL(COUNT(*) / 25.0) AS page_count
FROM products;
```

Nếu cần xác định nhóm bắt đầu từ 0 cho một số dương `x` theo kích thước bucket `k`, có thể dùng `FLOOR(x / k)`. Với số âm, cần xác định rõ muốn bucket theo hướng `FLOOR` hay cắt về 0 vì kết quả có thể khác nhau ở ranh giới.

## 13. Kiểu dữ liệu và ép kiểu ảnh hưởng kết quả

Các hàm toán học nhận nhiều loại đối số, nhưng kiểu dữ liệu đầu vào ảnh hưởng độ chính xác và kết quả. Một cột `DECIMAL` phù hợp với phép tính thập phân chính xác; `FLOAT` và `DOUBLE` là số gần đúng nên có thể biểu diễn một số thập phân bằng giá trị nhị phân xấp xỉ.

Nếu dữ liệu đến từ chuỗi, hãy chuyển kiểu rõ ràng và xác thực trước:

```sql
SELECT ROUND(CAST('123.456' AS DECIMAL(10, 3)), 2) AS rounded_value;
```

Không dựa vào ép kiểu ngầm từ chuỗi tùy ý. Chuỗi rỗng, ký tự không phải số hoặc định dạng dấu thập phân khác nhau có thể tạo warning, lỗi hoặc kết quả không như mong muốn tùy SQL mode.

Với các phép tính có nhiều hàm lồng nhau, hãy kiểm tra kiểu và độ chính xác tại từng bước. Ví dụ `ROUND(SUM(...), 2)` khác `SUM(ROUND(..., 2))` cả về kết quả lẫn nơi áp dụng làm tròn.

## 14. NULL và hàm toán học

Nếu đối số cần thiết là `NULL`, kết quả của các hàm toán học này thường là `NULL`:

```sql
SELECT
    ROUND(NULL, 2) AS rounded_null,
    TRUNCATE(NULL, 2) AS truncated_null,
    MOD(NULL, 3) AS modulo_null,
    CEIL(NULL) AS ceiling_null,
    FLOOR(NULL) AS floor_null;
```

Với `MOD()`, số chia bằng 0 cũng trả về `NULL`. Khi dùng trong biểu thức báo cáo, cần quyết định có muốn giữ `NULL` để thể hiện thiếu dữ liệu hay thay bằng giá trị khác:

```sql
SELECT COALESCE(ROUND(amount, 2), 0.00) AS display_amount
FROM payments;
```

Chỉ dùng `COALESCE(..., 0)` nếu nghiệp vụ xem giá trị thiếu tương đương 0. Nếu `NULL` có nghĩa là chưa tính, chưa nhập hoặc không áp dụng, thay bằng 0 có thể làm sai báo cáo.

## 15. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| `ROUND()` luôn làm tròn điểm giữa theo cùng một cách | Exact-value và approximate-value có thể khác nhau | Dùng `DECIMAL` cho số thập phân cần chính xác |
| `TRUNCATE()` là làm tròn xuống | Nó cắt về phía 0, không phải `FLOOR()` | Kiểm tra đặc biệt với số âm |
| `FLOOR(-2.7)` trả `-2` | `FLOOR()` đi xuống trục số và trả `-3` | Phân biệt hướng trục số với hướng về 0 |
| `CEIL(-2.7)` trả `-3` | `CEIL()` đi lên trục số và trả `-2` | Dùng định nghĩa số nguyên nhỏ nhất lớn hơn hoặc bằng giá trị |
| `MOD(-11, 4)` trả `1` | MySQL trả `-3`, cùng dấu với số bị chia | Chuẩn hóa nếu cần remainder không âm và divisor dương |
| `MOD(n, 0)` trả 0 | Kết quả là `NULL` | Kiểm tra số chia và xử lý NULL |
| `ROUND()` trong SELECT làm thay đổi cột | Hàm chỉ tạo giá trị kết quả | Dùng DML nếu thật sự cần lưu giá trị đã xử lý |
| Cắt tiền bằng `TRUNCATE()` tương đương làm tròn | Cắt có thể tạo thiên lệch | Theo đúng quy tắc kế toán/nghiệp vụ |

## 16. Quy trình chọn hàm phù hợp

Trước khi dùng hàm toán học, hãy trả lời:

1. **Dữ liệu là exact hay approximate?** Với tiền và số thập phân quan trọng, ưu tiên `DECIMAL`.
2. **Cần làm tròn hay cắt?** Dùng `ROUND()` cho làm tròn, `TRUNCATE()` cho cắt về 0.
3. **Cần biên trên hay biên dưới?** Dùng `CEIL()` cho phía trên, `FLOOR()` cho phía dưới.
4. **Có số âm không?** Kiểm tra kết quả trên số âm thay vì suy luận từ ví dụ số dương.
5. **MOD cần dấu nào?** MySQL giữ dấu số bị chia; chuẩn hóa nếu thuật toán cần miền không âm.
6. **Có thể gặp NULL hoặc chia cho 0 không?** Xác định cách xử lý và ý nghĩa của giá trị thiếu.
7. **Làm tròn ở cấp nào?** Theo từng dòng, tổng hóa đơn hay báo cáo; cần thống nhất quy tắc trước.
8. **Chỉ hiển thị hay lưu kết quả?** Tránh ghi đè dữ liệu gốc nếu chỉ cần định dạng khi đọc.

## 17. Bài tập thực hành

1. Chạy `ROUND(2.5)`, `ROUND(-2.5)`, `ROUND(2.45, 1)` và `ROUND(-2.45, 1)`; giải thích quy tắc điểm giữa với exact-value.
2. So sánh `ROUND(2.5)` và `ROUND(2.5E0)` trên server của bạn; ghi nhận ảnh hưởng của approximate-value.
3. Chạy `TRUNCATE(149, -1)`, `TRUNCATE(-149, -1)`, `ROUND(149, -1)` và `ROUND(-149, -1)`.
4. So sánh `TRUNCATE(-2.9, 0)`, `CEIL(-2.9)` và `FLOOR(-2.9)`.
5. Chạy `MOD(11, 4)`, `MOD(-11, 4)`, `MOD(11, -4)`, `MOD(-11, -4)` và giải thích dấu kết quả.
6. Viết biểu thức chuẩn hóa phần dư về miền không âm khi số chia dương; thử với số bị chia âm.
7. Tạo bảng invoice line dùng `DECIMAL`, so sánh `SUM(ROUND(...))` với `ROUND(SUM(...))`.
8. Viết truy vấn tính số thùng cần thiết nếu mỗi thùng chứa 12 sản phẩm bằng `CEIL()`.
9. Kiểm tra kết quả của các hàm với `NULL` và `MOD()` với số chia bằng 0.
10. Chọn một bài toán có số âm (số dư tài khoản, nhiệt độ, chênh lệch tồn kho) và giải thích nên dùng ROUND, TRUNCATE, CEIL hay FLOOR.

## 18. Ghi nhớ

`ROUND(x, d)` làm tròn đến số chữ số được chỉ định; `d` âm làm tròn về hàng chục, trăm hoặc nghìn. Với exact-value như `DECIMAL`, điểm giữa được làm tròn ra xa 0; với approximate-value như `DOUBLE`, kết quả có thể phụ thuộc thư viện toán học của hệ thống. `TRUNCATE(x, d)` cắt phần vượt quá và luôn hướng về 0, kể cả khi số âm.

`CEIL()`/`CEILING()` trả số nguyên nhỏ nhất lớn hơn hoặc bằng giá trị, còn `FLOOR()` trả số nguyên lớn nhất nhỏ hơn hoặc bằng giá trị. `MOD(n, m)` trả phần dư mang dấu của `n`; nếu `m = 0`, kết quả là `NULL`. Khi xử lý tiền tệ, dùng `DECIMAL` và thống nhất làm tròn ở cấp dòng hay cấp tổng. Luôn thử với số âm, `NULL`, số chia bằng 0 và kiểu dữ liệu thực tế trước khi đưa biểu thức vào ứng dụng.
