# Biểu thức số học, thứ tự ưu tiên và xử lý phép chia

Trong Oracle Database, biểu thức số học xuất hiện trong hầu hết câu SQL: tính thành tiền, chiết khấu, tỷ lệ hoàn thành, điểm trung bình, số ngày chênh lệch hoặc phân bổ chi phí. Một biểu thức như `quantity * unit_price - discount / 100` có thể cho kết quả khác ý định nếu người viết không hiểu **thứ tự ưu tiên toán tử**, **cách nhóm phép tính**, **kiểu số của toán hạng** và **cách xử lý mẫu số bằng 0 hoặc NULL**.

Bài học này trình bày cách Oracle đánh giá các phép `+`, `-`, `*` và `/`; cách dùng ngoặc để thể hiện đúng ý nghĩa; sự khác nhau giữa phép chia số và chia nguyên theo nghiệp vụ; cách làm tròn; và những mẫu SQL an toàn khi mẫu số có thể bằng 0. Các ví dụ có thể chạy bằng SQL*Plus, SQLcl hoặc công cụ SQL tương thích.

## 1. Biểu thức số học là gì?

Biểu thức số học là sự kết hợp giữa **hằng số**, **cột**, **bind variable**, **hàm số** và **toán tử** để tạo ra một giá trị số. Ví dụ:

~~~sql
SELECT quantity * unit_price AS gross_amount,
       quantity * unit_price - discount_amount AS net_amount
FROM order_items;
~~~

Trong câu trên:

- `quantity` và `unit_price` là các cột số.
- `*` là phép nhân.
- `discount_amount` được trừ khỏi thành tiền trước chiết khấu.
- `AS gross_amount` và `AS net_amount` đặt tên cho kết quả.

Một biểu thức có thể xuất hiện ở nhiều vị trí:

~~~sql
SELECT order_id,
       quantity * unit_price AS line_total
FROM order_items
WHERE quantity * unit_price > 100000
ORDER BY quantity * unit_price DESC;
~~~

Oracle đánh giá biểu thức theo quy tắc SQL và kiểu dữ liệu của các toán hạng. Việc biểu thức xuất hiện trong `SELECT`, `WHERE` hay `ORDER BY` không làm thay đổi ý nghĩa toán học của toán tử; tuy nhiên optimizer có thể chọn cách thực thi truy vấn khác nhau.

### 1.1 Bốn toán tử số học cơ bản

| Toán tử | Tên | Ví dụ | Kết quả |
|---|---|---|---:|
| `+` | Cộng | `12 + 5` | 17 |
| `-` | Trừ | `12 - 5` | 7 |
| `*` | Nhân | `12 * 5` | 60 |
| `/` | Chia | `12 / 5` | 2.4 |

Oracle SQL không dùng toán tử chia nguyên riêng như một số ngôn ngữ lập trình. Phép `/` thực hiện chia số và có thể tạo phần thập phân. Nếu nghiệp vụ cần phần nguyên, phải chọn rõ `TRUNC`, `FLOOR` hoặc hàm phù hợp.

## 2. Thứ tự ưu tiên của toán tử

Quy tắc cơ bản cho biểu thức số học:

1. Phép một ngôi như dấu dương `+x` và dấu âm `-x`.
2. Phép nhân `*` và phép chia `/`.
3. Phép cộng `+` và phép trừ `-`.
4. Các toán tử cùng mức ưu tiên được kết hợp từ trái sang phải trong biểu thức số học thông thường.
5. Ngoặc đơn `(...)` được xử lý trước phần biểu thức bên ngoài và cho phép người viết chỉ định cách nhóm phép tính.

Ví dụ:

~~~sql
SELECT 100 + 20 * 3 AS result
FROM dual;
~~~

Kết quả là `160`, vì Oracle thực hiện `20 * 3` trước rồi cộng 100:

~~~text
100 + 20 * 3
= 100 + 60
= 160
~~~

Nếu ý định là cộng trước rồi nhân:

~~~sql
SELECT (100 + 20) * 3 AS result
FROM dual;
~~~

Kết quả là `360`:

~~~text
(100 + 20) * 3
= 120 * 3
= 360
~~~

### 2.1 Nhân và chia có cùng mức ưu tiên

`*` và `/` có cùng mức ưu tiên. Nếu không có ngoặc, chúng được kết hợp từ trái sang phải:

~~~sql
SELECT 20 / 5 * 2 AS left_to_right,
       20 / (5 * 2) AS grouped_denominator
FROM dual;
~~~

| Biểu thức | Cách nhóm | Kết quả |
|---|---|---:|
| `20 / 5 * 2` | `(20 / 5) * 2` | 8 |
| `20 / (5 * 2)` | `20 / 10` | 2 |

Đây là lỗi thường gặp khi tính tỷ lệ hoặc đơn giá. Nếu muốn chia cho **tích của hai giá trị**, phải đặt cả tích trong ngoặc.

### 2.2 Cộng và trừ có cùng mức ưu tiên

`+` và `-` cũng có cùng mức ưu tiên, kết hợp từ trái sang phải:

~~~sql
SELECT 100 - 20 + 5 AS left_to_right,
       100 - (20 + 5) AS subtract_group
FROM dual;
~~~

Kết quả lần lượt là `85` và `75`. Hai biểu thức không tương đương vì ngoặc thay đổi nhóm phép tính.

### 2.3 Dấu âm một ngôi và phép trừ

~~~sql
SELECT -5 * 2 AS negative_product,
       5 * -2 AS product_negative,
       5 - -2 AS subtract_negative
FROM dual;
~~~

Kết quả là `-10`, `-10` và `7`. Dấu âm đứng trước một toán hạng là phép đổi dấu; dấu `-` giữa hai biểu thức là phép trừ. Khi biểu thức phức tạp, viết ngoặc để người đọc nhìn thấy ý định:

~~~sql
SELECT 100 - (-20) AS add_twenty,
       -(100 - 20) AS negate_difference
FROM dual;
~~~

### 2.4 Ngoặc đơn làm rõ ý nghĩa nghiệp vụ

Xét công thức tính thành tiền:

~~~text
Thành tiền = số lượng × đơn giá
Giảm giá = thành tiền × tỷ lệ giảm / 100
Phải trả = thành tiền - giảm giá
~~~

SQL thể hiện rõ từng bước:

~~~sql
SELECT quantity * unit_price AS gross_amount,
       quantity * unit_price * discount_percent / 100 AS discount_amount,
       quantity * unit_price
         - (quantity * unit_price * discount_percent / 100)
           AS payable_amount
FROM order_items;
~~~

Có thể rút gọn:

~~~sql
SELECT quantity * unit_price
       * (1 - discount_percent / 100) AS payable_amount
FROM order_items;
~~~

Hai cách tương đương về ý tưởng khi các cột là số và tỷ lệ giảm có ý nghĩa như phần trăm. Cách thứ nhất dễ đối chiếu với từng bước tính; cách thứ hai gọn hơn. Trong SQL nghiệp vụ, **ngoặc có thể làm câu lệnh dễ đọc hơn dù toán tử đã có thứ tự ưu tiên rõ ràng**.

## 3. Thực hành thứ tự ưu tiên trên Oracle

Không cần tạo bảng để thử toán tử. Có thể dùng bảng giả lập một hàng `DUAL`:

~~~sql
SELECT 2 + 3 * 4 AS case_1,
       (2 + 3) * 4 AS case_2,
       20 / 5 * 2 AS case_3,
       20 / (5 * 2) AS case_4,
       100 - 20 - 5 AS case_5,
       100 - (20 - 5) AS case_6
FROM dual;
~~~

Kết quả dự kiến:

| Cột | Biểu thức | Kết quả |
|---|---|---:|
| `CASE_1` | `2 + (3 * 4)` | 14 |
| `CASE_2` | `(2 + 3) * 4` | 20 |
| `CASE_3` | `(20 / 5) * 2` | 8 |
| `CASE_4` | `20 / (5 * 2)` | 2 |
| `CASE_5` | `(100 - 20) - 5` | 75 |
| `CASE_6` | `100 - (20 - 5)` | 85 |

Bạn có thể thay hằng số bằng cột để kiểm tra cùng quy tắc trên dữ liệu:

~~~sql
SELECT order_id,
       quantity,
       unit_price,
       quantity * unit_price AS gross_amount,
       (quantity * unit_price) - discount_amount AS net_amount
FROM order_items;
~~~

### 3.1 Tránh biểu thức viết tắt khó đọc

Ví dụ:

~~~sql
SELECT base_amount * 1 - discount / 100 AS total
FROM invoices;
~~~

Người đọc phải tự suy đoán `discount` là số tiền hay phần trăm. Nếu là tỷ lệ phần trăm, công thức có thể cần:

~~~sql
SELECT base_amount * (1 - discount_percent / 100) AS total
FROM invoices;
~~~

Nếu `discount` là số tiền:

~~~sql
SELECT base_amount - discount_amount AS total
FROM invoices;
~~~

Tên cột và ngoặc nên thể hiện rõ đơn vị/ý nghĩa. Một biểu thức đúng cú pháp vẫn có thể sai nghiệp vụ nếu trộn **phần trăm** với **số tiền**.

## 4. Phép chia trong Oracle: không tự động là chia nguyên

Trong Oracle, toán tử `/` trả kết quả số. Ví dụ:

~~~sql
SELECT 5 / 2 AS quotient,
       10 / 4 AS another_quotient,
       1 / 3 AS repeating_fraction
FROM dual;
~~~

| Biểu thức | Kết quả toán học |
|---|---:|
| `5 / 2` | 2.5 |
| `10 / 4` | 2.5 |
| `1 / 3` | Xấp xỉ 0.333333... theo độ chính xác số Oracle |

Oracle không tự cắt phần thập phân chỉ vì hai toán hạng nhìn như số nguyên. Nếu cần phần nguyên, phải nói rõ muốn **cắt về 0** hay **làm tròn xuống**.

### 4.1 TRUNC: cắt phần thập phân về phía 0

~~~sql
SELECT TRUNC(5 / 2) AS positive_trunc,
       TRUNC(-5 / 2) AS negative_trunc,
       TRUNC(10 / 3, 2) AS two_decimals
FROM dual;
~~~

Kết quả lần lượt là `2`, `-2` và `3.33`. `TRUNC(n, 2)` cắt sau hai chữ số thập phân; nó không làm tròn chữ số thứ ba. `TRUNC(-2.89)` cho `-2` vì hướng về 0.

### 4.2 FLOOR: làm tròn xuống theo trục số

~~~sql
SELECT FLOOR(5 / 2) AS positive_floor,
       FLOOR(-5 / 2) AS negative_floor
FROM dual;
~~~

Kết quả là `2` và `-3`. Với số âm, `FLOOR` đi về số nguyên nhỏ hơn hoặc bằng giá trị; vì vậy khác `TRUNC`.

| Giá trị | `TRUNC(value)` | `FLOOR(value)` | Giải thích |
|---:|---:|---:|---|
| 2.9 | 2 | 2 | Cùng kết quả với số dương |
| -2.9 | -2 | -3 | `TRUNC` về 0; `FLOOR` xuống phía âm |
| 2.0 | 2 | 2 | Đã là số nguyên |

### 4.3 ROUND: làm tròn theo chữ số yêu cầu

~~~sql
SELECT ROUND(10 / 3, 2) AS rounded_2,
       ROUND(10 / 3, 0) AS rounded_integer,
       ROUND(125.456, 1) AS rounded_1
FROM dual;
~~~

Kết quả tương ứng là `3.33`, `3` và `125.5`. `ROUND` làm tròn theo quy tắc Oracle, khác với `TRUNC` là cắt bỏ phần sau vị trí chỉ định.

| Hàm | Mục đích | Ví dụ |
|---|---|---|
| `TRUNC(n, 2)` | Cắt còn hai chữ số thập phân | `3.333... → 3.33` |
| `ROUND(n, 2)` | Làm tròn còn hai chữ số | `3.335 → 3.34` |
| `FLOOR(n)` | Số nguyên lớn nhất không vượt quá n | `-2.1 → -3` |
| `CEIL(n)` | Số nguyên nhỏ nhất không nhỏ hơn n | `2.1 → 3` |

Đừng dùng `FLOOR` thay `TRUNC` khi nghiệp vụ có số âm, hoặc dùng `ROUND` khi yêu cầu là cắt phần lẻ. Cần chọn hàm dựa trên quy tắc nghiệp vụ.

## 5. Chia cho 0: lỗi thường gặp và cách xử lý

Với kiểu `NUMBER` thông thường, mẫu số bằng 0 trong phép chia gây lỗi:

~~~sql
SELECT 10 / 0 AS result
FROM dual;
~~~

Oracle báo:

~~~text
ORA-01476: divisor is equal to zero
~~~

Trong truy vấn trên nhiều hàng, chỉ cần một hàng có mẫu số bằng 0 cũng có thể làm cả câu SQL thất bại nếu biểu thức chia được đánh giá cho hàng đó. Không nên chờ lỗi xảy ra rồi mới xử lý; hãy xác định trước ý nghĩa nghiệp vụ của trường hợp mẫu số bằng 0.

### 5.1 NULLIF: biến mẫu số 0 thành NULL

Mẫu thường dùng:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
~~~

`NULLIF(a, b)` trả `NULL` nếu `a = b`; nếu không, trả `a`. Do đó:

- Nếu `denominator = 0`, mẫu số trở thành `NULL`.
- Nếu `denominator` khác 0, phép chia thực hiện bình thường.
- Nếu `denominator` vốn đã `NULL`, kết quả vẫn là `NULL`.

Trong SQL, phép toán số học với `NULL` cho `NULL`. Vì vậy kết quả tỷ lệ ở hàng có mẫu số 0 không còn làm phát sinh lỗi chia cho 0:

~~~sql
SELECT 10 / NULLIF(0, 0) AS safe_result
FROM dual;
~~~

`SAFE_RESULT` là `NULL`. Đây là cách phù hợp khi tỷ lệ không xác định nên được biểu diễn bằng giá trị chưa có/không xác định.

### 5.2 CASE: quy định rõ kết quả khi mẫu số bằng 0

Nếu nghiệp vụ yêu cầu trả một nhãn hoặc một giá trị khác:

~~~sql
SELECT CASE
         WHEN denominator = 0 THEN NULL
         ELSE numerator / denominator
       END AS ratio
FROM metrics;
~~~

Hoặc nếu quy ước tỷ lệ bằng 0 khi mẫu số bằng 0:

~~~sql
SELECT CASE
         WHEN denominator = 0 THEN 0
         ELSE numerator / denominator
       END AS ratio
FROM metrics;
~~~

Oracle hỗ trợ short-circuit evaluation cho biểu thức `CASE`: nhánh điều kiện được chọn quyết định biểu thức kết quả tương ứng. Tuy nhiên, chọn trả `0` là **quyết định nghiệp vụ**, không phải quy tắc toán học phổ quát. Tỷ lệ không xác định và tỷ lệ thực sự bằng 0 là hai trạng thái khác nhau.

### 5.3 NVL/COALESCE không tự giải quyết chia cho 0

Đoạn sau vẫn nguy hiểm:

~~~sql
SELECT numerator / NVL(denominator, 0) AS ratio
FROM metrics;
~~~

Nếu `denominator` là `NULL`, `NVL` thay bằng 0 và phép chia có thể phát sinh `ORA-01476`. Tương tự:

~~~sql
SELECT numerator / COALESCE(denominator, 0) AS ratio
FROM metrics;
~~~

không phải cách an toàn. `NVL` và `COALESCE` xử lý `NULL`, không tự bảo đảm mẫu số khác 0. Nếu mục tiêu là tránh chia cho 0, dùng `NULLIF(denominator, 0)` hoặc `CASE` kiểm tra số 0.

### 5.4 Không dựa vào thứ tự điều kiện WHERE để bảo vệ phép chia

Một cách viết dễ gây hiểu nhầm:

~~~sql
SELECT numerator / denominator AS ratio
FROM metrics
WHERE denominator <> 0;
~~~

Người viết có thể nghĩ Oracle luôn lọc bỏ hàng có denominator bằng 0 trước rồi mới tính phép chia. Nhưng optimizer có thể biến đổi và sắp xếp cách thực thi các biểu thức; không nên dựa vào thứ tự đánh giá điều kiện `WHERE` để đảm bảo một phép toán không lỗi.

Viết biểu thức tự bảo vệ:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
~~~

Hoặc dùng `CASE`:

~~~sql
SELECT CASE
         WHEN denominator <> 0
         THEN numerator / denominator
       END AS ratio
FROM metrics;
~~~

Điểm cốt lõi: **điều kiện an toàn phải nằm trong chính biểu thức thực hiện phép chia**, không chỉ nằm ở một điều kiện lọc khác.

## 6. Chọn ý nghĩa nghiệp vụ cho mẫu số bằng 0 và NULL

Không phải trường hợp nào cũng nên biến thành 0. Hãy xác định mẫu số đại diện điều gì:

| Trường hợp | Ý nghĩa có thể có | Cách biểu diễn cần cân nhắc |
|---|---|---|
| Mẫu số bằng 0 | Không có cơ sở để tính tỷ lệ | `NULL` hoặc trạng thái “không xác định” |
| Mẫu số là `NULL` | Thiếu dữ liệu đầu vào | `NULL`, hoặc xử lý riêng theo quy tắc nghiệp vụ |
| Tử số bằng 0, mẫu số dương | Tỷ lệ thực sự bằng 0 | Trả 0 |
| Tử số và mẫu số đều dương | Tỷ lệ bình thường | Chia và làm tròn theo quy tắc |
| Mẫu số âm | Có thể là điều chỉnh/hoàn trả hoặc dữ liệu không hợp lệ | Xác định nghiệp vụ trước khi tính |

Ví dụ, nếu `completed_count = 0` và `total_count = 0`, tỷ lệ hoàn thành không thể tự kết luận là 0% hay 100%. Hệ thống cần quyết định trạng thái “chưa có đối tượng để đánh giá”, hoặc trả `NULL` kèm nhãn giải thích.

### 6.1 Trả cả tỷ lệ và trạng thái

Một truy vấn báo cáo có thể tách giá trị số và trạng thái:

~~~sql
SELECT metric_id,
       numerator / NULLIF(denominator, 0) AS ratio,
       CASE
         WHEN denominator IS NULL THEN 'MISSING_DENOMINATOR'
         WHEN denominator = 0 THEN 'ZERO_DENOMINATOR'
         ELSE 'CALCULATED'
       END AS ratio_status
FROM metrics;
~~~

Cách này giữ được khác biệt giữa dữ liệu thiếu và mẫu số bằng 0. Nếu chỉ dùng `NVL(ratio, 0)`, báo cáo có thể biến nhiều trường hợp khác nhau thành cùng một số 0 và khiến người đọc hiểu sai.

### 6.2 COALESCE ở tầng hiển thị

Nếu giao diện bắt buộc hiển thị chuỗi khi tỷ lệ không xác định:

~~~sql
SELECT CASE
         WHEN denominator IS NULL THEN 'Chưa có dữ liệu'
         WHEN denominator = 0 THEN 'Không xác định'
         ELSE TO_CHAR(
                ROUND(numerator / denominator * 100, 2),
                'FM999999990D00',
                'NLS_NUMERIC_CHARACTERS=.,'
              ) || '%'
       END AS ratio_display
FROM metrics;
~~~

Đây là ví dụ trả chuỗi để trình bày. Trong API có hợp đồng dữ liệu, thường tốt hơn khi trả **giá trị số/null và trạng thái riêng**, để frontend tự định dạng theo locale người dùng. Không nên ép mọi thứ thành chuỗi nếu phía sau còn cần so sánh, sắp xếp hoặc tính tiếp.

## 7. NUMBER, BINARY_FLOAT và BINARY_DOUBLE

Oracle hỗ trợ nhiều kiểu số. Chọn đúng kiểu ảnh hưởng độ chính xác, cách chuyển đổi và kết quả của phép chia.

| Kiểu | Đặc điểm | Trường hợp thường cân nhắc |
|---|---|---|
| `NUMBER` | Số thập phân với độ chính xác/thang đo theo kiểu Oracle; hỗ trợ tới 38 chữ số có nghĩa | Tiền, số lượng, tỷ lệ nghiệp vụ cần kiểm soát thập phân |
| `BINARY_FLOAT` | Số dấu phẩy động nhị phân đơn chính xác, theo IEEE 754 | Tính toán khoa học/đồ họa cần kiểu floating point 32-bit |
| `BINARY_DOUBLE` | Số dấu phẩy động nhị phân kép chính xác, theo IEEE 754 | Tính toán số dấu phẩy động cần phạm vi/độ chính xác binary 64-bit |

### 7.1 Phép chia NUMBER

~~~sql
SELECT 1 / 3 AS number_quotient,
       ROUND(1 / 3, 4) AS rounded_quotient
FROM dual;
~~~

Kết quả đầu là giá trị số được Oracle biểu diễn với độ chính xác hữu hạn; kết quả thứ hai là `0.3333`. Với tiền tệ, thường lưu và tính bằng `NUMBER(p,s)`, rồi làm tròn theo quy tắc nghiệp vụ tại đúng bước được quy định.

### 7.2 Kiểu floating point có thể cho kết quả khác NUMBER

~~~sql
SELECT CAST(0.1 AS BINARY_DOUBLE)
       + CAST(0.2 AS BINARY_DOUBLE) AS binary_sum,
       CAST(0.1 AS NUMBER) + CAST(0.2 AS NUMBER) AS number_sum
FROM dual;
~~~

Số dấu phẩy động nhị phân không biểu diễn chính xác mọi phân số thập phân hữu hạn. Vì vậy phép cộng `0.1 + 0.2` bằng kiểu binary floating point có thể cho kết quả hiển thị gần `0.3` nhưng không nhất thiết bằng chính xác giá trị thập phân lý tưởng. `NUMBER` phù hợp hơn cho nhiều phép tính tiền tệ.

### 7.3 Numeric precedence và implicit conversion

Khi biểu thức trộn các kiểu số, Oracle áp dụng quy tắc ưu tiên kiểu số và chuyển đổi cần thiết. Thứ tự ưu tiên số thường là:

`BINARY_DOUBLE` cao hơn `BINARY_FLOAT`, và `BINARY_FLOAT` cao hơn `NUMBER`.

Nếu biểu thức có toán hạng `BINARY_DOUBLE`, kết quả có thể được xử lý theo kiểu floating point đó. Vì vậy một literal/cột có kiểu khác có thể làm thay đổi kiểu kết quả của biểu thức.

Không trộn `NUMBER` với `BINARY_DOUBLE` chỉ để “tăng độ chính xác” trong tính tiền; đó là hai mô hình biểu diễn số khác nhau. Nên giữ kiểu dữ liệu nhất quán, ép kiểu tường minh khi cần và kiểm tra kiểu kết quả nếu đang điều tra.

### 7.4 Chia cho 0 với NUMBER và kiểu floating point

Với biểu thức `NUMBER` thông thường, chia cho 0 gây `ORA-01476`. `BINARY_FLOAT` và `BINARY_DOUBLE` tuân theo quy tắc floating-point IEEE 754, có thể biểu diễn các giá trị đặc biệt như infinity hoặc NaN trong một số phép toán. Do đó, không nên trộn kiểu rồi kỳ vọng mọi phép chia cho 0 đều cho cùng hành vi lỗi.

Trong SQL nghiệp vụ, mẫu số bằng 0 vẫn nên được xử lý tường minh bằng `NULLIF` hoặc `CASE`, bất kể kiểu số. Đừng dùng giá trị infinity/NaN như một cách mã hóa lỗi nghiệp vụ.

## 8. Độ chính xác, scale và làm tròn trong biểu thức

Kiểu `NUMBER(p,s)` có:

- `p`: precision, số chữ số có nghĩa tối đa.
- `s`: scale, số chữ số được giữ sau dấu thập phân (scale âm cho phép làm tròn ở bên trái dấu thập phân).

Ví dụ:

~~~sql
CREATE TABLE lab_numeric_values (
    amount        NUMBER(12,2),
    exchange_rate NUMBER(10,6)
);
~~~

`AMOUNT` có tối đa 12 chữ số có nghĩa với scale 2; `EXCHANGE_RATE` có scale 6. Khi gán giá trị có nhiều chữ số lẻ hơn scale, Oracle có thể làm tròn theo định nghĩa kiểu; nếu phần nguyên khiến precision bị vượt, có thể phát sinh lỗi như `ORA-01438: value larger than specified precision allowed for this column`.

### 8.1 Làm tròn từng dòng hay sau khi cộng?

Hai cách có thể cho kết quả khác:

~~~sql
SELECT SUM(ROUND(line_amount * tax_rate, 2)) AS sum_rounded_lines,
       ROUND(SUM(line_amount * tax_rate), 2) AS rounded_total
FROM invoice_lines;
~~~

- `SUM(ROUND(..., 2))` làm tròn từng dòng rồi cộng.
- `ROUND(SUM(...), 2)` cộng các giá trị chưa làm tròn rồi mới làm tròn tổng.

Ví dụ đơn giản, ba dòng thuế mỗi dòng `0.005`:

~~~sql
SELECT SUM(ROUND(0.005, 2)) AS round_each,
       ROUND(SUM(0.005), 2) AS round_after_sum
FROM (
    SELECT 1 AS n FROM dual
    UNION ALL SELECT 2 FROM dual
    UNION ALL SELECT 3 FROM dual
);
~~~

Theo quy tắc làm tròn Oracle, kết quả minh họa là `0.03` khi làm tròn từng dòng và `0.02` khi làm tròn tổng. Chính sách thuế/kế toán phải chỉ định **đơn vị làm tròn**; không tự chọn vị trí `ROUND` chỉ vì biểu thức trông gọn hơn.

### 8.2 Ép kiểu kết quả có chủ đích

~~~sql
SELECT CAST(
           ROUND(quantity * unit_price, 2)
           AS NUMBER(14,2)
       ) AS line_total
FROM order_items;
~~~

`ROUND` quyết định quy tắc làm tròn, còn `CAST` chỉ định kiểu kết quả mong muốn. Ép kiểu không thay thế kiểm tra dữ liệu vượt precision; nếu giá trị quá lớn, Oracle vẫn có thể báo lỗi khi lưu hoặc chuyển kiểu.

## 9. Phép chia trong báo cáo: tỷ lệ từng dòng và tỷ lệ tổng

Một lỗi nghiệp vụ phổ biến là dùng sai vị trí của `SUM` và phép chia.

Giả sử bảng `sales_by_team` có `team_id`, `revenue` và `target`:

~~~sql
SELECT team_id,
       revenue / NULLIF(target, 0) AS achievement_ratio
FROM sales_by_team;
~~~

Đây là tỷ lệ đạt mục tiêu của **từng đội**.

Nếu muốn tỷ lệ tổng của tất cả đội:

~~~sql
SELECT SUM(revenue) / NULLIF(SUM(target), 0) AS total_achievement_ratio
FROM sales_by_team;
~~~

Không mặc định rằng:

~~~sql
SELECT AVG(revenue / NULLIF(target, 0)) AS average_team_ratio
FROM sales_by_team;
~~~

sẽ bằng `SUM(revenue) / SUM(target)`. Hai đại lượng có ý nghĩa khác nhau:

| Công thức | Ý nghĩa |
|---|---|
| `AVG(revenue / target)` | Trung bình tỷ lệ của từng đội, mỗi đội có trọng số như nhau trong phép AVG (các hàng NULL bị bỏ qua) |
| `SUM(revenue) / SUM(target)` | Tỷ lệ tổng doanh thu trên tổng mục tiêu; đội có mục tiêu lớn đóng góp trọng số lớn hơn |
| `SUM(revenue / target)` | Tổng các tỷ lệ; thường không phải chỉ số đạt mục tiêu tổng |

Ví dụ:

| Đội | Revenue | Target | Tỷ lệ |
|---|---:|---:|---:|
| A | 90 | 100 | 90% |
| B | 180 | 300 | 60% |

`AVG(90%, 60%) = 75%`, nhưng tỷ lệ tổng là `270 / 400 = 67.5%`. Chọn công thức dựa trên câu hỏi báo cáo muốn trả lời.

### 9.1 NULL trong phép tổng hợp

Oracle bỏ qua `NULL` trong nhiều hàm tổng hợp như `SUM` và `AVG`. Nếu dùng `NULLIF` để biến mẫu số 0 thành `NULL`:

~~~sql
SELECT AVG(numerator / NULLIF(denominator, 0)) AS avg_ratio,
       COUNT(*) AS input_rows,
       COUNT(numerator / NULLIF(denominator, 0)) AS calculated_rows
FROM metrics;
~~~

`INPUT_ROWS` đếm tất cả hàng; `CALCULATED_ROWS` đếm số biểu thức tỷ lệ khác `NULL`. Hai con số giúp người đọc biết có bao nhiêu hàng thực sự tham gia vào trung bình. Nếu không báo số hàng bỏ qua, một chỉ số trung bình có thể trông hợp lệ dù nhiều hàng không tính được.

## 10. Biểu thức số học với NULL

Trong Oracle SQL, `NULL` đại diện giá trị chưa biết/không có. Phép toán số học với `NULL` thường trả `NULL`:

~~~sql
SELECT 10 + NULL AS add_null,
       10 - NULL AS subtract_null,
       10 * NULL AS multiply_null,
       10 / NULL AS divide_null
FROM dual;
~~~

Các kết quả là `NULL`. Điều này không có nghĩa Oracle coi `NULL` là 0.

### 10.1 NVL và COALESCE thay đổi ý nghĩa phép tính

~~~sql
SELECT amount + NVL(discount, 0) AS amount_with_default_discount
FROM invoices;
~~~

Ở đây `NVL(discount, 0)` có ý nghĩa nghiệp vụ: thiếu giá trị chiết khấu được coi là không giảm. Nếu quy tắc của doanh nghiệp coi `NULL` là “chưa xác định chiết khấu”, thay bằng 0 có thể sai.

`COALESCE` cho phép chọn giá trị không `NULL` đầu tiên:

~~~sql
SELECT amount
       - COALESCE(discount_amount, promotional_discount, 0)
           AS net_amount
FROM invoices;
~~~

Biểu thức trên ưu tiên `discount_amount`, nếu `NULL` thì dùng `promotional_discount`, nếu cả hai `NULL` thì dùng 0. Phải xác nhận thứ tự ưu tiên này đúng nghiệp vụ; hàm không tự biết trường nào là chính.

### 10.2 NULLIF khác NVL

| Hàm | Cách xử lý | Ví dụ |
|---|---|---|
| `NVL(x, 0)` | Thay `NULL` bằng 0 | `NVL(NULL,0) = 0` |
| `COALESCE(x, y, 0)` | Lấy biểu thức đầu tiên không `NULL` | `COALESCE(NULL,5,0) = 5` |
| `NULLIF(x, 0)` | Trả `NULL` khi x bằng 0; ngược lại trả x | `NULLIF(0,0) = NULL` |

Khi bảo vệ mẫu số, `NULLIF(denominator, 0)` là mẫu phù hợp hơn `NVL(denominator, 0)`.

## 11. Chuyển đổi kiểu dữ liệu và NLS trong phép chia

Phép chia nên dùng **toán hạng kiểu số**. Nếu một bên là chuỗi, Oracle có thể phải chuyển đổi ngầm định:

~~~sql
SELECT 10 / '2' AS result
FROM dual;
~~~

Oracle có thể chuyển chuỗi `'2'` thành số 2. Nhưng dựa vào implicit conversion khiến câu SQL phụ thuộc dữ liệu đầu vào và quy tắc chuyển đổi NLS. Ví dụ:

~~~sql
SELECT 10 / '2,5' AS result
FROM dual;
~~~

Chuỗi `'2,5'` có thể được diễn giải khác nhau tùy `NLS_NUMERIC_CHARACTERS`; có môi trường báo `ORA-01722: invalid number`. Không nên dùng một chuỗi có dấu phân cách không rõ quy ước làm toán hạng số.

### 11.1 Dùng literal số trong SQL

Literal số trong SQL viết với dấu chấm thập phân:

~~~sql
SELECT 10 / 2.5 AS result
FROM dual;
~~~

Đây là số literal, không phải chuỗi văn bản chịu cùng cách parse như `'2,5'`. Dấu phân cách hiển thị kết quả có thể chịu NLS, nhưng giá trị số của literal không phải chuỗi được parse theo locale của người dùng.

### 11.2 Nếu bắt buộc chuyển chuỗi thành số

Chỉ rõ format và quy tắc NLS phù hợp:

~~~sql
SELECT TO_NUMBER(
           '1.234,50',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS parsed_number
FROM dual;
~~~

Ví dụ này yêu cầu dấu nhóm là dấu chấm và dấu thập phân là dấu phẩy. Cần dùng đúng format model và quy tắc quoting cho chuỗi SQL; trong ứng dụng, bind giá trị số trực tiếp thường an toàn hơn chuyển một chuỗi đã định dạng.

### 11.3 Java/JDBC: bind số bằng kiểu số

Ví dụ:

~~~java
String sql = """
    SELECT amount / NULLIF(quantity, 0) AS unit_amount
    FROM order_totals
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.math.BigDecimal unitAmount = rs.getBigDecimal("UNIT_AMOUNT");
        }
    }
}
~~~

Đoạn mã giả định đã có `Connection connection` và biến `orderId`; `AMOUNT`, `QUANTITY` là cột số. Bind ID bằng `setLong`, đọc kết quả số bằng `getBigDecimal` để giữ mô hình thập phân phù hợp cho nghiệp vụ tiền. Không dùng `setString` để truyền số tiền đã định dạng theo locale rồi mong Oracle luôn parse giống nhau.

## 12. Phép chia với ngày giờ và khoảng thời gian

Ngoài số, Oracle có phép toán số học liên quan ngày giờ:

- `DATE + NUMBER`: cộng số ngày; phần thập phân đại diện phần của một ngày.
- `DATE - DATE`: trả về số ngày chênh lệch, có thể có phần lẻ.
- Với `TIMESTAMP`, phép cộng/trừ khoảng thời gian thường dùng kiểu `INTERVAL` phù hợp.

Ví dụ:

~~~sql
SELECT DATE '2026-11-14' + 1 AS next_day,
       DATE '2026-11-14' + 0.5 AS twelve_hours_later,
       DATE '2026-11-15' - DATE '2026-11-14' AS days_between
FROM dual;
~~~

Kết quả lần lượt biểu diễn ngày tiếp theo, thời điểm sau 12 giờ và số ngày chênh lệch là 1. Việc hiển thị phần giờ của kết quả `DATE` vẫn chịu định dạng session/client; nếu cần rõ ràng, dùng `TO_CHAR` với format cụ thể.

Với timestamp:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:00:00'
       + INTERVAL '90' MINUTE AS after_ninety_minutes
FROM dual;
~~~

Không nên chuyển mọi timestamp thành số ngày rồi cộng trừ nếu nghiệp vụ cần xử lý timezone, daylight saving time hoặc khoảng thời gian theo tháng. Chọn kiểu `INTERVAL` và loại timestamp đúng với ý nghĩa thời gian.

## 13. Biểu thức số học trong WHERE, UPDATE và INSERT

### 13.1 WHERE: so sánh theo biểu thức

~~~sql
SELECT order_id, quantity, unit_price
FROM order_items
WHERE quantity * unit_price > 500000;
~~~

Oracle đánh giá tích để so sánh với ngưỡng. Nếu cột có `NULL`, biểu thức tích có thể là `NULL`; điều kiện không trở thành TRUE nên hàng đó không được chọn. Nếu cần coi số lượng/đơn giá thiếu là 0, phải thể hiện rõ:

~~~sql
SELECT order_id
FROM order_items
WHERE NVL(quantity, 0) * NVL(unit_price, 0) > 500000;
~~~

Đây là thay đổi logic: thiếu quantity hoặc price được coi là 0. Nếu thiếu dữ liệu là lỗi cần phát hiện, hãy kiểm tra riêng thay vì tự thay bằng 0.

### 13.2 UPDATE: tính giá trị mới

~~~sql
UPDATE inventory
SET available_qty = available_qty - :sold_qty
WHERE product_id = :product_id
  AND available_qty >= :sold_qty;
~~~

Trong ví dụ, bind variable giúp truyền số lượng bán và mã sản phẩm. Điều kiện kiểm tra tồn kho ngay tại DML giúp tránh cập nhật khi số lượng không đủ. Ứng dụng cần kiểm tra số hàng được cập nhật và xử lý transaction. Biểu thức trừ không thay thế ràng buộc như `CHECK (available_qty >= 0)`.

### 13.3 INSERT: biểu thức ở VALUES

~~~sql
INSERT INTO order_totals (order_id, amount, tax_amount, total_amount)
VALUES (
    :order_id,
    :amount,
    :amount * :tax_rate,
    :amount + (:amount * :tax_rate)
);
~~~

Oracle tính các biểu thức dựa trên bind values và kiểu dữ liệu. Nếu `tax_rate` được gửi theo dạng phần trăm 8 thay vì tỷ lệ 0.08, kết quả khác 100 lần; tên bind và hợp đồng dữ liệu phải làm rõ đơn vị.

## 14. Phép chia trong truy vấn tổng hợp và analytic

### 14.1 Tính tỷ lệ theo nhóm

~~~sql
SELECT department_id,
       SUM(completed_count) /
         NULLIF(SUM(total_count), 0) AS completion_ratio
FROM department_metrics
GROUP BY department_id
ORDER BY department_id;
~~~

Ở đây mẫu số được tính sau khi tổng hợp theo phòng ban. `NULLIF` xử lý trường hợp tổng `total_count` bằng 0.

### 14.2 Tính phần trăm đóng góp trên tổng

~~~sql
SELECT department_id,
       revenue,
       revenue / NULLIF(SUM(revenue) OVER (), 0) * 100
           AS revenue_share_percent
FROM department_revenue;
~~~

`SUM(revenue) OVER ()` tính tổng doanh thu trên toàn bộ tập hàng mà truy vấn xử lý; biểu thức chia tạo tỷ trọng mỗi hàng. Nếu cần tổng theo từng vùng, thêm `PARTITION BY region_id`:

~~~sql
SELECT region_id,
       department_id,
       revenue,
       revenue /
         NULLIF(SUM(revenue) OVER (PARTITION BY region_id), 0)
         * 100 AS region_share_percent
FROM department_revenue;
~~~

Ngoặc trong biểu thức giúp người đọc thấy rõ tỷ lệ là `revenue / tổng` rồi nhân 100. Nếu bỏ `NULLIF`, một vùng không có doanh thu có thể gây lỗi khi tổng bằng 0.

## 15. Hiệu năng và khả năng đọc của biểu thức

### 15.1 Biểu thức lặp lại có thể làm SQL khó bảo trì

~~~sql
SELECT quantity * unit_price AS gross_amount,
       quantity * unit_price - discount_amount AS net_amount,
       (quantity * unit_price - discount_amount) / NULLIF(quantity, 0)
           AS net_per_quantity
FROM order_items;
~~~

Khi biểu thức lặp lại nhiều lần, có thể đặt trong CTE:

~~~sql
WITH item_values AS (
    SELECT order_id,
           quantity,
           quantity * unit_price AS gross_amount,
           discount_amount
    FROM order_items
)
SELECT order_id,
       gross_amount,
       gross_amount - discount_amount AS net_amount,
       (gross_amount - discount_amount) / NULLIF(quantity, 0)
           AS net_per_quantity
FROM item_values;
~~~

CTE giúp tách bước tính để người đọc dễ hiểu. Không mặc định CTE luôn được materialize thành bảng tạm; Oracle optimizer có thể inline hoặc biến đổi truy vấn theo execution plan.

### 15.2 Hàm trên cột và index

Điều kiện:

~~~sql
WHERE quantity * unit_price > 500000
~~~

có thể khiến việc dùng index thường trên riêng `QUANTITY` hoặc `UNIT_PRICE` không đơn giản như điều kiện lọc trực tiếp theo một cột. Nếu workload cần truy vấn theo một biểu thức lặp lại và có bằng chứng hiệu năng, có thể đánh giá **function-based index**:

~~~sql
-- Ví dụ thiết kế, chỉ tạo sau khi đánh giá workload:
CREATE INDEX ix_order_items_line_value
ON order_items (quantity * unit_price);
~~~

Đây không phải khuyến nghị tạo index cho mọi biểu thức. Index làm tăng chi phí lưu trữ và DML; optimizer còn xét thống kê, độ chọn lọc và điều kiện truy vấn. Kiểm tra execution plan thực tế trước khi quyết định.

### 15.3 Giữ kiểu dữ liệu rõ ràng ở ranh giới ứng dụng

Nếu dữ liệu lớn và biểu thức cần lọc/tổng hợp trong database, có thể để Oracle thực hiện phép tính gần dữ liệu. Nếu chỉ hiển thị một giá trị đã lấy về, ứng dụng có thể định dạng ở tầng giao diện. Phân chia trách nhiệm dựa vào:

- Có cần lọc/sắp xếp/tổng hợp theo biểu thức trong SQL không?
- Quy tắc tính có phải dùng chung cho nhiều ứng dụng không?
- Kiểu dữ liệu và làm tròn có nhất quán giữa các hệ thống không?
- Có cần giữ nguyên số chính xác để tính tiếp hay chỉ cần chuỗi hiển thị?

## 16. Những lỗi và hiểu nhầm thường gặp

| Hiện tượng/lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Kết quả phép tính khác dự đoán | Sai thứ tự ưu tiên hoặc thiếu ngoặc | Viết lại biểu thức theo từng bước và thêm ngoặc |
| `ORA-01476: divisor is equal to zero` | Mẫu số NUMBER bằng 0 | Dùng `NULLIF` hoặc `CASE` theo ý nghĩa nghiệp vụ |
| Phép chia ra phần thập phân dù tưởng là số nguyên | Oracle `/` là phép chia số, không phải chia nguyên | Dùng `TRUNC` hoặc `FLOOR` đúng mục tiêu |
| Số âm cho kết quả khác khi dùng FLOOR/TRUNC | Hai hàm xử lý số âm khác nhau | Xác định muốn về 0 hay xuống số nguyên nhỏ hơn |
| `ORA-01722: invalid number` | Chuỗi được chuyển sang số không hợp lệ hoặc sai NLS | Bind kiểu số hoặc `TO_NUMBER` có format/NLS rõ |
| Kết quả tiền tệ lệch vài đơn vị nhỏ | Làm tròn từng dòng hay sau tổng không thống nhất; kiểu floating point | Dùng `NUMBER`, thống nhất chính sách `ROUND` |
| Tỷ lệ bằng 0 dù không có dữ liệu | Dùng `NVL(ratio,0)` làm mất ý nghĩa NULL | Trả tỷ lệ NULL và trạng thái riêng nếu chưa xác định |
| Một hàng mẫu số 0 làm cả báo cáo lỗi | Chia trực tiếp không bảo vệ mẫu số | Dùng `numerator / NULLIF(denominator,0)` |
| Lọc denominator khác 0 nhưng vẫn lỗi chia | Dựa vào thứ tự thực thi WHERE | Đưa bảo vệ vào chính biểu thức chia |
| Tỷ lệ trung bình không khớp tỷ lệ tổng | Dùng `AVG(row_ratio)` thay cho `SUM(num)/SUM(den)` | Chọn đúng định nghĩa chỉ số |
| Kết quả binary có sai số nhỏ | Số dấu phẩy động nhị phân không biểu diễn chính xác mọi số thập phân | Dùng NUMBER cho số tiền/đại lượng cần thập phân chính xác |

## 17. Bài thực hành tự kiểm tra

Các câu lệnh dưới đây có thể chạy bằng SQL*Plus, SQLcl hoặc công cụ SQL tương thích. Dùng `DUAL` để thử biểu thức trước; không cần tạo bảng nếu chỉ học toán tử.

### Bài 1 — Dự đoán thứ tự ưu tiên

Trước khi chạy, tự tính:

~~~sql
SELECT 8 + 4 * 3 AS a,
       (8 + 4) * 3 AS b,
       60 / 5 * 2 AS c,
       60 / (5 * 2) AS d,
       50 - 8 + 3 AS e,
       50 - (8 + 3) AS f
FROM dual;
~~~

Giải thích tại sao `C` và `D` khác nhau, và tại sao `E` không bằng `F`.

### Bài 2 — Phân biệt chia, cắt và làm tròn

~~~sql
SELECT 17 / 4 AS exact_division,
       TRUNC(17 / 4) AS trunc_result,
       FLOOR(17 / 4) AS floor_result,
       ROUND(17 / 4, 2) AS round_result
FROM dual;
~~~

Tiếp tục thay tử số thành `-17`. Viết ra sự khác nhau giữa `TRUNC` và `FLOOR` khi kết quả âm.

### Bài 3 — Bảo vệ phép chia

~~~sql
SELECT 100 / NULLIF(5, 0) AS normal_ratio,
       100 / NULLIF(0, 0) AS zero_denominator_ratio,
       100 / NULLIF(NULL, 0) AS null_denominator_ratio
FROM dual;
~~~

Giải thích tại sao hai kết quả sau là `NULL` và vì sao chúng không tương đương với tỷ lệ thực sự bằng 0.

### Bài 4 — Chọn kết quả khi mẫu số bằng 0

~~~sql
SELECT CASE
         WHEN 0 = 0 THEN 'NOT_DEFINED'
         ELSE TO_CHAR(100 / 0)
       END AS ratio_status
FROM dual;
~~~

Mục đích là nhận diện cách `CASE` chọn nhánh; sau đó viết lại ví dụ bằng cột thật và `NULLIF`. Không chạy phép chia không bảo vệ trên dữ liệu có mẫu số 0.

### Bài 5 — Trung bình tỷ lệ hay tỷ lệ tổng?

~~~sql
WITH teams AS (
    SELECT 90 AS revenue, 100 AS target FROM dual
    UNION ALL
    SELECT 180, 300 FROM dual
)
SELECT AVG(revenue / target) AS average_team_ratio,
       SUM(revenue) / SUM(target) AS total_ratio
FROM teams;
~~~

Dự đoán hai kết quả và giải thích công thức nào phù hợp khi báo cáo “đội trung bình đạt bao nhiêu phần trăm” và công thức nào phù hợp khi báo cáo “tổng doanh thu đạt bao nhiêu phần trăm tổng mục tiêu”.

### Bài 6 — NULL trong biểu thức

~~~sql
SELECT 10 + NULL AS direct_result,
       10 + NVL(NULL, 0) AS with_nvl,
       10 + COALESCE(NULL, 2, 0) AS with_coalesce
FROM dual;
~~~

Giải thích tại sao `NVL` và `COALESCE` thay đổi kết quả, và trường hợp nào thay `NULL` bằng 0 là đúng nghiệp vụ.

### Bài 7 — NUMBER và kiểu floating point

~~~sql
SELECT CAST(0.1 AS NUMBER) + CAST(0.2 AS NUMBER) AS decimal_sum,
       CAST(0.1 AS BINARY_DOUBLE)
         + CAST(0.2 AS BINARY_DOUBLE) AS binary_sum
FROM dual;
~~~

So sánh kiểu số, giải thích vì sao số binary floating point có thể không khớp chính xác một phân số thập phân và nêu lý do nên dùng `NUMBER` cho tiền.

### Bài 8 — Viết công thức thành tiền

Một dòng hàng có:

~~~text
quantity = 3
unit_price = 125000
discount_percent = 10
~~~

Viết SQL tính:

1. Thành tiền trước giảm.
2. Số tiền giảm.
3. Thành tiền sau giảm.
4. Thành tiền sau giảm làm tròn hai chữ số.

Đặt ngoặc để người đọc nhìn rõ thứ tự, và giải thích đơn vị của `discount_percent`.

### Bài 9 — Thiết kế tỷ lệ có trạng thái

Một bảng có `completed_count` và `total_count`. Viết truy vấn trả:

- `completion_ratio` với `NULLIF` để tránh chia cho 0.
- `ratio_status` có ba trạng thái `MISSING_TOTAL`, `NO_TARGET`, `CALCULATED`.

Giải thích cách phân biệt `total_count IS NULL` với `total_count = 0`.

## 18. Ghi nhớ khi viết biểu thức số học

| Vấn đề | Quy tắc thực hành |
|---|---|
| Thứ tự ưu tiên | Nhân/chia trước cộng/trừ; toán tử cùng mức kết hợp trái sang phải |
| Nhóm phép tính | Dùng ngoặc khi ý nghĩa nghiệp vụ cần nhóm rõ |
| Phép chia | `/` cho kết quả số, không tự cắt thành số nguyên |
| Chia cho 0 | Với NUMBER, dùng `NULLIF` hoặc `CASE` bảo vệ mẫu số |
| NULL | Không tự coi `NULL` là 0; chỉ thay bằng NVL/COALESCE khi có quy tắc nghiệp vụ |
| Làm tròn | Chọn `ROUND`, `TRUNC`, `FLOOR` hoặc `CEIL` theo mục tiêu, nhất là với số âm |
| Kiểu số | Ưu tiên `NUMBER` cho tiền và phép tính thập phân cần kiểm soát |
| Chuyển đổi | Bind đúng kiểu; tránh parse chuỗi số phụ thuộc NLS |
| Tỷ lệ báo cáo | Phân biệt trung bình tỷ lệ từng dòng với tỷ lệ của tổng |
| Hiệu năng | Đọc execution plan và workload trước khi tạo index trên biểu thức |

Một biểu thức số học tốt vừa **đúng toán học**, vừa **đúng ý nghĩa nghiệp vụ**, vừa **an toàn với dữ liệu biên**. Hãy viết rõ nhóm phép tính, quyết định trước cách xử lý mẫu số bằng 0/NULL, chọn kiểu số phù hợp và đặt quy tắc làm tròn tại đúng bước. Những điều đó giúp SQL cho kết quả ổn định giữa các session, công cụ và ứng dụng khác nhau.
