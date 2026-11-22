# IFNULL, COALESCE, NULLIF và kiểu dữ liệu kết quả

Bài học thuộc chương **Hàm và biểu thức** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Ba hàm `IFNULL()`, `COALESCE()` và `NULLIF()` giúp chuẩn hóa giá trị thiếu, chọn dữ liệu thay thế và xử lý các trường hợp đặc biệt trong phép tính.

Sau bài này, bạn có thể chọn đúng hàm theo nghiệp vụ, phân biệt `NULL` với 0 và chuỗi rỗng, dự đoán kiểu dữ liệu của biểu thức, kiểm tra metadata kết quả và tránh lỗi chuyển kiểu khi dùng các hàm này trong truy vấn, view, bảng tạm hoặc ứng dụng.

## 1. NULL có ý nghĩa gì?

Trong MySQL, `NULL` biểu thị giá trị không xác định hoặc chưa có. Nó không đồng nghĩa với số 0, chuỗi rỗng hay giá trị FALSE.

| Giá trị | Ý nghĩa ví dụ |
|---|---|
| `NULL` | Chưa biết số điện thoại |
| `0` | Số lượng thực tế bằng không |
| `''` | Đã biết trường văn bản có giá trị rỗng |
| `' '` | Chuỗi có một dấu cách |
| `FALSE` hoặc `0` trong ngữ cảnh logic | Điều kiện sai |

Các phép toán thông thường với `NULL` thường trả về `NULL`:

~~~sql
SELECT
    NULL + 10 AS numeric_result,
    CONCAT('Phone: ', NULL) AS text_result,
    NULL = NULL AS equality_result;
~~~

Cả ba biểu thức đều cho kết quả NULL. So sánh `NULL = NULL` không trả TRUE vì SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN.

Để kiểm tra NULL, dùng `IS NULL` hoặc `IS NOT NULL`:

~~~sql
SELECT
    NULL IS NULL AS is_null,
    NULL IS NOT NULL AS is_not_null;
~~~

Ba hàm trong bài xử lý NULL theo ba mục đích khác nhau:

- `IFNULL(a, b)`: nếu `a` khác NULL thì lấy `a`, nếu không thì lấy `b`.
- `COALESCE(a, b, ...)`: lấy đối số đầu tiên khác NULL.
- `NULLIF(a, b)`: nếu `a` bằng `b` thì trả NULL, nếu không thì trả `a`.

## 2. IFNULL(): thay một giá trị NULL bằng giá trị dự phòng

Cú pháp:

~~~sql
IFNULL(expr1, expr2)
~~~

Hàm trả về:

- `expr1` nếu `expr1` không phải NULL.
- `expr2` nếu `expr1` là NULL.

Ví dụ cơ bản:

~~~sql
SELECT
    IFNULL(NULL, 'Chưa cung cấp') AS display_value,
    IFNULL('An', 'Chưa cung cấp') AS existing_value,
    IFNULL(0, 100) AS zero_value,
    IFNULL('', 'default') AS empty_string_value;
~~~

Kết quả:

| Biểu thức | Kết quả |
|---|---|
| `IFNULL(NULL, 'Chưa cung cấp')` | `Chưa cung cấp` |
| `IFNULL('An', 'Chưa cung cấp')` | `An` |
| `IFNULL(0, 100)` | `0` |
| `IFNULL('', 'default')` | Chuỗi rỗng |

Điểm quan trọng: `IFNULL()` chỉ kiểm tra NULL. Nó không tự xem 0 hoặc chuỗi rỗng là dữ liệu thiếu.

### Ví dụ trong bảng khách hàng

Giả sử bảng `customers` có cột `display_name` có thể NULL:

~~~sql
SELECT
    customer_id,
    IFNULL(display_name, 'Khách hàng chưa đặt tên') AS customer_name
FROM customers;
~~~

Truy vấn trả nhãn thay thế cho các hàng chưa có tên. Giá trị gốc trong bảng không bị thay đổi.

### IFNULL() không cập nhật dữ liệu

Câu lệnh:

~~~sql
SELECT IFNULL(phone_number, 'Chưa có số điện thoại')
FROM customers;
~~~

chỉ thay giá trị trong kết quả truy vấn. Nó không ghi chuỗi thay thế vào cột `phone_number`.

Nếu cần sửa dữ liệu thật, phải dùng câu lệnh UPDATE và xác định rõ điều kiện:

~~~sql
UPDATE customers
SET phone_number = 'Chưa cung cấp'
WHERE phone_number IS NULL;
~~~

Tuy nhiên, chỉ làm việc này nếu chuỗi đó thực sự là một giá trị nghiệp vụ hợp lệ cho cột. Với dữ liệu số điện thoại, thường nên giữ NULL và chỉ tạo nhãn hiển thị ở truy vấn hoặc tầng ứng dụng.

## 3. COALESCE(): chọn giá trị đầu tiên khác NULL

Cú pháp:

~~~sql
COALESCE(value1, value2, ..., valueN)
~~~

Hàm kiểm tra các đối số từ trái sang phải và trả về giá trị đầu tiên khác NULL. Nếu tất cả đều NULL, kết quả là NULL.

Ví dụ:

~~~sql
SELECT
    COALESCE(NULL, NULL, 'Primary', 'Fallback') AS first_available,
    COALESCE(NULL, NULL, NULL) AS no_available_value,
    COALESCE('Main', 'Backup') AS first_value;
~~~

Kết quả:

| Biểu thức | Kết quả |
|---|---|
| `COALESCE(NULL, NULL, 'Primary', 'Fallback')` | `Primary` |
| `COALESCE(NULL, NULL, NULL)` | NULL |
| `COALESCE('Main', 'Backup')` | `Main` |

Khác với IFNULL, COALESCE nhận từ hai đối số trở lên. Đây là hàm theo chuẩn SQL và phù hợp khi có nhiều nguồn dữ liệu dự phòng.

### Chọn email theo thứ tự ưu tiên

Một khách hàng có thể có email công việc, email cá nhân và email liên hệ phụ:

~~~sql
SELECT
    customer_id,
    COALESCE(
        work_email,
        personal_email,
        backup_email,
        'Chưa có email'
    ) AS contact_email
FROM customers;
~~~

Thứ tự đối số thể hiện chính sách ưu tiên. Nếu email công việc có giá trị, các địa chỉ phía sau không được chọn. Nếu email công việc NULL, MySQL xét tiếp email cá nhân.

Đừng sắp xếp các đối số tùy tiện: thay đổi thứ tự có thể thay đổi dữ liệu hiển thị dù các cột nguồn không thay đổi.

### COALESCE() với nhiều giá trị mặc định

Có thể dùng các cấp dự phòng:

~~~sql
SELECT
    order_id,
    COALESCE(
        shipping_note,
        customer_note,
        internal_note,
        'Không có ghi chú'
    ) AS note_to_display
FROM orders;
~~~

Đây là cách ngắn gọn hơn nhiều lớp IFNULL lồng nhau:

~~~sql
IFNULL(
    shipping_note,
    IFNULL(
        customer_note,
        IFNULL(internal_note, 'Không có ghi chú')
    )
)
~~~

Hai cách trên có thể tương đương về giá trị trong ví dụ này, nhưng COALESCE dễ đọc và dễ mở rộng hơn.

## 4. NULLIF(): biến một giá trị cụ thể thành NULL

Cú pháp:

~~~sql
NULLIF(expr1, expr2)
~~~

Hàm thực hiện phép so sánh:

- Nếu `expr1 = expr2` là TRUE, trả NULL.
- Nếu phép so sánh không đúng, trả `expr1`.

Ví dụ:

~~~sql
SELECT
    NULLIF(10, 10) AS equal_values,
    NULLIF(10, 5) AS different_values,
    NULLIF(0, 0) AS zero_to_null,
    NULLIF('', '') AS empty_to_null;
~~~

Kết quả:

| Biểu thức | Kết quả |
|---|---|
| `NULLIF(10, 10)` | NULL |
| `NULLIF(10, 5)` | `10` |
| `NULLIF(0, 0)` | NULL |
| `NULLIF('', '')` | NULL |

NULLIF không sửa dữ liệu trong bảng. Nó chỉ biến kết quả của biểu thức thành NULL.

### Chuẩn hóa chuỗi rỗng

Một số nguồn nhập liệu gửi chuỗi rỗng thay cho giá trị chưa biết. Có thể chuẩn hóa chuỗi rỗng thành NULL trước khi chọn nhãn:

~~~sql
SELECT
    customer_id,
    COALESCE(
        NULLIF(TRIM(phone_number), ''),
        'Chưa cung cấp'
    ) AS phone_display
FROM customers;
~~~

Quy trình của biểu thức:

1. `TRIM(phone_number)` loại dấu cách ở đầu và cuối.
2. `NULLIF(..., '')` đổi chuỗi rỗng thành NULL.
3. `COALESCE(..., 'Chưa cung cấp')` chọn nhãn thay thế.

Cần quyết định rõ việc loại bỏ dấu cách có phù hợp nghiệp vụ hay không. Với mã định danh hoặc dữ liệu mà dấu cách có ý nghĩa, không tự động TRIM.

### Chuẩn hóa giá trị sentinel

Một hệ thống cũ có thể dùng `'N/A'`, `'UNKNOWN'` hoặc `'NONE'` làm ký hiệu cho dữ liệu thiếu:

~~~sql
SELECT
    COALESCE(
        NULLIF(status_text, 'N/A'),
        'Chưa xác định'
    ) AS normalized_status
FROM imported_records;
~~~

Chỉ chuyển sentinel thành NULL khi quy ước dữ liệu nguồn xác nhận chuỗi đó không phải giá trị hợp lệ. Nếu người dùng có thể nhập thật chữ `N/A`, phép chuyển đổi sẽ làm mất ý nghĩa của dữ liệu.

## 5. Kết hợp ba hàm

Ba hàm có thể kết hợp để làm sạch và chọn dữ liệu:

~~~sql
SELECT
    customer_id,
    COALESCE(
        NULLIF(TRIM(preferred_name), ''),
        NULLIF(TRIM(legal_name), ''),
        'Khách hàng'
    ) AS display_name
FROM customers;
~~~

Cách đọc:

- Ưu tiên `preferred_name` sau khi bỏ khoảng trắng.
- Nếu giá trị đó rỗng hoặc NULL, xét `legal_name`.
- Nếu cả hai không có giá trị, dùng `Khách hàng`.

Ví dụ với số tiền:

~~~sql
SELECT
    order_id,
    IFNULL(discount_amount, 0.00) AS discount_amount,
    COALESCE(
        promotion_name,
        coupon_name,
        'Không áp dụng khuyến mãi'
    ) AS promotion_label
FROM orders;
~~~

Ở đây IFNULL phù hợp cho một giá trị tiền có thể thiếu; COALESCE phù hợp cho nhiều nguồn tên khuyến mãi.

Một ví dụ khác dùng NULLIF để tránh mẫu số bằng 0:

~~~sql
SELECT
    product_id,
    revenue / NULLIF(units_sold, 0) AS revenue_per_unit
FROM product_sales;
~~~

Nếu `units_sold = 0`, NULLIF trả NULL và phép chia không thực hiện với mẫu số 0. Kết quả `revenue_per_unit` là NULL. Nếu nghiệp vụ muốn hiển thị 0 thay cho NULL, có thể bọc thêm COALESCE:

~~~sql
SELECT
    product_id,
    COALESCE(
        revenue / NULLIF(units_sold, 0),
        0
    ) AS revenue_per_unit
FROM product_sales;
~~~

Chỉ thay NULL bằng 0 khi 0 là cách biểu diễn đúng của nghiệp vụ. Trong báo cáo, NULL có thể có nghĩa “không tính được”, còn 0 có nghĩa “đã tính và kết quả bằng không”.

## 6. Kiểu dữ liệu kết quả: phần dễ gây lỗi nhất

Các hàm có thể trả về một giá trị nhìn có vẻ đúng nhưng metadata kiểu dữ liệu lại khác điều bạn mong đợi. Điều này ảnh hưởng tới:

- Kiểu cột khi dùng `CREATE TABLE ... SELECT`.
- Kiểu dữ liệu của view hoặc bảng tạm.
- Kiểu mà MySQL gửi qua giao thức cho connector.
- Cách ứng dụng ánh xạ giá trị sang kiểu Java, .NET, Python hoặc ngôn ngữ khác.
- So sánh, sắp xếp, tính toán tiếp theo và độ chính xác số học.

Không chỉ nhìn giá trị hiển thị để kết luận kiểu kết quả. Cần hiểu quy tắc riêng của từng hàm.

### Quy tắc kiểu trả về của IFNULL()

`IFNULL(expr1, expr2)` trả giá trị của expr1 nếu không NULL, ngược lại trả expr2. Nhưng kiểu kết quả mặc định được xác định từ hai đối số theo thứ tự mức tổng quát:

1. STRING
2. REAL
3. INTEGER

Vì vậy, một đối số chuỗi có thể khiến kiểu kết quả là kiểu chuỗi ngay cả khi giá trị thực tế được chọn là số.

Ví dụ được MySQL minh họa:

~~~sql
SELECT IFNULL(1, 'test') AS result_value;
~~~

Giá trị trả về là `1`. Tuy nhiên, khi tạo bảng từ biểu thức:

~~~sql
CREATE TEMPORARY TABLE ifnull_type_demo AS
SELECT IFNULL(1, 'test') AS result_value;

DESCRIBE ifnull_type_demo;

DROP TEMPORARY TABLE ifnull_type_demo;
~~~

MySQL tạo cột `result_value` kiểu `VARBINARY(4)` trong ví dụ tài liệu. Đây là khác biệt quan trọng giữa **giá trị của hàng** và **kiểu metadata của biểu thức**.

Không nên trộn số và chuỗi trong IFNULL nếu mục tiêu là một cột số:

~~~sql
-- Tránh trộn DECIMAL với chuỗi '0'
SELECT IFNULL(amount, '0') AS amount_value
FROM invoices;
~~~

Nên dùng giá trị thay thế cùng miền kiểu:

~~~sql
SELECT
    IFNULL(amount, CAST(0 AS DECIMAL(12,2))) AS amount_value
FROM invoices;
~~~

Nếu cột `amount` đã là DECIMAL và 0 là giá trị thay thế hợp lệ, có thể dùng:

~~~sql
SELECT IFNULL(amount, 0) AS amount_value
FROM invoices;
~~~

Dùng CAST tường minh khi cần kiểm soát chính xác kiểu và độ chính xác của kết quả.

### Quy tắc kiểu trả về của COALESCE()

Kiểu kết quả của `COALESCE()` là kiểu tổng hợp từ kiểu của tất cả đối số, không chỉ đối số đầu tiên khác NULL ở một hàng cụ thể.

Ví dụ:

~~~sql
SELECT COALESCE(NULL, 100, 200) AS numeric_value;
~~~

Các đối số có kiểu số nên kết quả có kiểu số.

Nếu trộn số và chuỗi:

~~~sql
SELECT COALESCE(100, '200') AS mixed_value;
~~~

Giá trị được chọn là 100, nhưng kiểu kết quả được suy ra từ cả hai đối số. Do có sự kết hợp kiểu số và chuỗi, kết quả có thể được tổng hợp thành kiểu chuỗi.

Với dữ liệu tiền, nên giữ tất cả nhánh cùng kiểu DECIMAL:

~~~sql
SELECT
    COALESCE(
        paid_amount,
        refunded_amount,
        CAST(0 AS DECIMAL(14,2))
    ) AS effective_amount
FROM payment_summary;
~~~

Nếu các đối số là các kiểu ngày giờ khác nhau, hoặc có sự pha trộn kiểu chuỗi và nhị phân, quy tắc tổng hợp cũng có thể ảnh hưởng metadata. Khi kiểu kết quả là hợp đồng của API hoặc schema, hãy CAST các nhánh về cùng kiểu trước khi gọi COALESCE.

### Quy tắc kiểu trả về của NULLIF()

`NULLIF(expr1, expr2)` trả về NULL nếu hai biểu thức bằng nhau, nếu không thì trả `expr1`. Kiểu trả về là kiểu của đối số thứ nhất.

Ví dụ:

~~~sql
SELECT
    NULLIF(CAST(10 AS DECIMAL(12,2)), 10) AS decimal_result,
    NULLIF(CAST(10 AS SIGNED), 5) AS integer_result;
~~~

Biểu thức đầu có kiểu theo đối số đầu là DECIMAL; biểu thức thứ hai theo đối số đầu là SIGNED/INTEGER.

Nếu đối số đầu là chuỗi, kết quả vẫn theo kiểu chuỗi của đối số đầu, kể cả khi một số hàng trở thành NULL.

### Bảng so sánh kiểu kết quả

| Hàm | Quy tắc kiểu kết quả | Điều cần chú ý |
|---|---|---|
| `IFNULL(a, b)` | Kiểu tổng quát hơn của hai đối số theo quy tắc IFNULL | Một nhánh chuỗi có thể làm kết quả thành chuỗi |
| `COALESCE(a, b, ...)` | Kiểu tổng hợp từ tất cả đối số | Các đối số không được chọn ở một hàng vẫn tham gia xác định kiểu |
| `NULLIF(a, b)` | Cùng kiểu với đối số đầu tiên | So sánh có thể dùng chuyển đổi kiểu và collation |

Không nên đoán kiểu kết quả chỉ bằng cách nhìn giá trị mẫu. Nếu biểu thức được lưu vào bảng hoặc trả qua API, hãy kiểm tra metadata.

## 7. CAST để kiểm soát kiểu kết quả

`CAST()` cho phép chuyển biểu thức sang kiểu đích rõ ràng. Đây là cách hữu ích để ổn định kiểu trả về của IFNULL và COALESCE.

### Giá trị tiền

~~~sql
SELECT
    COALESCE(
        subtotal,
        tax_amount,
        CAST(0 AS DECIMAL(14,2))
    ) AS amount_value
FROM invoices;
~~~

Nếu cả `subtotal` và `tax_amount` đều là DECIMAL tương thích, kết quả giữ ngữ nghĩa số thập phân. Không dùng FLOAT cho tiền chỉ để tránh lỗi kiểu.

### Giá trị nguyên

~~~sql
SELECT
    IFNULL(
        retry_count,
        CAST(0 AS UNSIGNED)
    ) AS retry_count
FROM job_queue;
~~~

Dùng kiểu UNSIGNED khi miền dữ liệu chỉ có giá trị không âm và cột nguồn cũng phù hợp. Nếu cần cho phép số âm, chọn SIGNED.

### Chuỗi và collation

~~~sql
SELECT
    COALESCE(
        CAST(preferred_label AS CHAR CHARACTER SET utf8mb4),
        CAST(legal_label AS CHAR CHARACTER SET utf8mb4),
        'Chưa có tên'
    ) AS display_label
FROM customers;
~~~

Khi biểu thức kết hợp các chuỗi khác character set hoặc collation, MySQL phải xác định quy tắc so sánh và collation của kết quả. Nếu gặp lỗi `Illegal mix of collations`, hãy kiểm tra charset/collation của các đối số và chuyển chúng về một quy ước rõ ràng bằng CAST, CONVERT hoặc COLLATE.

### Kiểm tra kiểu và collation

Có thể dùng các hàm sau để kiểm tra biểu thức chuỗi:

~~~sql
SELECT
    CHARSET(COALESCE(name_vi, name_en, 'Unknown')) AS result_charset,
    COLLATION(COALESCE(name_vi, name_en, 'Unknown')) AS result_collation;
~~~

Để kiểm tra kiểu cột được suy ra khi tạo bảng:

~~~sql
CREATE TEMPORARY TABLE result_type_probe AS
SELECT
    IFNULL(1, 'test') AS ifnull_value,
    COALESCE(1, 'test') AS coalesce_value,
    NULLIF(1, 2) AS nullif_value;

DESCRIBE result_type_probe;

DROP TEMPORARY TABLE result_type_probe;
~~~

Cách kiểm tra này hữu ích khi xây dựng view, bảng tạm hoặc bảng từ SELECT. Kiểu cụ thể của biểu thức hỗn hợp có thể phụ thuộc kiểu đối số, literal, charset, collation và phiên bản MySQL.

## 8. So sánh chuỗi trong NULLIF phụ thuộc collation

`NULLIF(a, b)` dùng quy tắc so sánh của biểu thức `a = b`. Với chuỗi, collation có thể quyết định hai chuỗi có được xem là bằng nhau hay không.

Ví dụ với collation không phân biệt hoa thường:

~~~sql
SELECT NULLIF(
    _utf8mb4'A' COLLATE utf8mb4_0900_ai_ci,
    _utf8mb4'a' COLLATE utf8mb4_0900_ai_ci
) AS case_insensitive_result;
~~~

Hai chuỗi được xem là bằng nhau theo collation này, vì vậy kết quả là NULL.

Với collation phân biệt hoa thường:

~~~sql
SELECT NULLIF(
    _utf8mb4'A' COLLATE utf8mb4_0900_as_cs,
    _utf8mb4'a' COLLATE utf8mb4_0900_as_cs
) AS case_sensitive_result;
~~~

Hai chuỗi khác nhau theo quy tắc so sánh này, nên kết quả là `A`.

Điều này rất quan trọng khi dùng NULLIF để chuẩn hóa mã, trạng thái hoặc dữ liệu nhập. Nếu nghiệp vụ yêu cầu phân biệt hoa/thường, hãy chọn collation phù hợp hoặc so sánh theo byte. Nếu không, hai giá trị khác chữ hoa/thường có thể bị xem là bằng nhau và đổi thành NULL.

Với đối số có kiểu khác nhau, MySQL có thể chuyển đổi kiểu trước khi so sánh. Ví dụ chuỗi số và số nguyên có thể được so sánh theo quy tắc chuyển kiểu. Nếu dữ liệu đầu vào không đồng nhất, hãy CAST tường minh để tránh việc một giá trị bị coi là bằng một giá trị khác ngoài dự kiến.

## 9. NULLIF và giá trị NULL trong phép so sánh

Nếu một đối số của NULLIF là NULL, phép so sánh `expr1 = expr2` thường cho UNKNOWN:

~~~sql
SELECT
    NULLIF(10, NULL) AS non_null_first,
    NULLIF(NULL, 10) AS null_first,
    NULLIF(NULL, NULL) AS both_null;
~~~

- `NULLIF(10, NULL)` trả 10 vì phép so sánh không phải TRUE, nên trả đối số đầu.
- `NULLIF(NULL, 10)` trả NULL vì đối số đầu vốn đã NULL.
- `NULLIF(NULL, NULL)` cũng trả NULL.

Đừng dùng NULLIF để kiểm tra hai giá trị có cùng NULL hay không. Nếu cần so sánh null-safe, dùng toán tử `<=>`:

~~~sql
SELECT
    NULL <=> NULL AS both_are_null,
    NULLIF(NULL, NULL) IS NULL AS nullif_result_is_null;
~~~

Hai biểu thức có mục đích khác nhau: `<=>` trả TRUE/FALSE, còn NULLIF trả một giá trị hoặc NULL.

### NULLIF có thể đánh giá đối số đầu hai lần

MySQL ghi rõ rằng `expr1` có thể được đánh giá hai lần khi hai đối số không bằng nhau. Vì vậy, tránh đưa biểu thức tốn kém hoặc không ổn định vào vị trí đầu nếu việc đánh giá lặp lại có thể ảnh hưởng kết quả hoặc hiệu năng.

Ví dụ nên tránh dùng một lời gọi không xác định hoặc biểu thức phức tạp trực tiếp:

~~~sql
SELECT NULLIF(expensive_expression(), 0);
~~~

Nếu cần tái sử dụng một kết quả đã tính, hãy tính và lưu nó vào biến, cột trung gian hoặc một bước xử lý phù hợp rồi truyền giá trị ổn định vào NULLIF.

## 10. Ứng dụng với phép tính và hàm tổng hợp

### Tránh chia cho 0

Một mẫu rất phổ biến:

~~~sql
SELECT
    revenue / NULLIF(units_sold, 0) AS revenue_per_unit
FROM product_sales;
~~~

Khi `units_sold` bằng 0, NULLIF trả NULL. Phép chia cho NULL trả NULL thay vì thực hiện chia cho 0.

Nếu muốn báo cáo hiển thị 0:

~~~sql
SELECT
    COALESCE(
        revenue / NULLIF(units_sold, 0),
        0
    ) AS revenue_per_unit
FROM product_sales;
~~~

Cần phân biệt “không tính được vì không có đơn vị bán” với “doanh thu trên mỗi đơn vị bằng 0”. Đừng thay NULL bằng 0 nếu điều đó làm sai ý nghĩa phân tích.

### Bỏ qua giá trị sentinel trong AVG

Giả sử dữ liệu cũ dùng 0 để biểu thị thời gian chưa ghi nhận. Có thể chuyển 0 thành NULL trước khi tính trung bình:

~~~sql
SELECT
    AVG(NULLIF(processing_seconds, 0)) AS avg_processing_seconds
FROM job_runs;
~~~

Các hàm tổng hợp như AVG bỏ qua NULL. Tuy nhiên, chỉ áp dụng khi 0 thực sự là mã biểu thị thiếu dữ liệu. Nếu tác vụ có thể hoàn tất trong 0 giây theo nghiệp vụ, chuyển 0 thành NULL sẽ làm sai thống kê.

### Phân biệt SUM(COALESCE(...)) và COALESCE(SUM(...))

Hai biểu thức dưới đây không hoàn toàn giống nhau:

~~~sql
SELECT
    SUM(COALESCE(amount, 0)) AS sum_each_row_defaulted,
    COALESCE(SUM(amount), 0) AS defaulted_total
FROM payments;
~~~

- `SUM(COALESCE(amount, 0))`: thay từng giá trị NULL thành 0 trước khi cộng. Nếu có hàng nhưng tất cả amount đều NULL, tổng là 0; nếu tập đầu vào hoàn toàn không có hàng, SUM vẫn trả NULL.
- `COALESCE(SUM(amount), 0)`: cộng các giá trị không NULL trước; sau đó thay kết quả tổng NULL bằng 0. Cách này trả 0 cả khi không có hàng đầu vào hoặc mọi amount đều NULL.

Vì vậy, hai biểu thức có thể khác nhau khi tập đầu vào rỗng. Hãy chọn theo yêu cầu nghiệp vụ thay vì thay thế NULL một cách máy móc.

### Đếm các giá trị không phải trạng thái cụ thể

~~~sql
SELECT
    COUNT(NULLIF(status, 'cancelled')) AS non_cancelled_count
FROM orders;
~~~

Nếu status bằng `cancelled`, NULLIF trả NULL và COUNT(expr) bỏ qua giá trị đó. Các trạng thái khác được đếm. Hãy lưu ý rằng status NULL cũng không được COUNT vì COUNT(expr) bỏ qua mọi NULL.

## 11. Sử dụng trong WHERE và tác động đến index

Có thể dùng IFNULL, COALESCE hoặc NULLIF trong điều kiện:

~~~sql
SELECT customer_id
FROM customers
WHERE COALESCE(region_code, 'UNKNOWN') = 'UNKNOWN';
~~~

Tuy nhiên, bọc cột trong hàm có thể khiến điều kiện khó sử dụng index B-tree thông thường trên cột đó. Nếu bảng lớn, hãy xem kế hoạch thực thi bằng EXPLAIN.

Trong ví dụ trên, nếu mục tiêu là tìm cả NULL và giá trị literal UNKNOWN, có thể viết:

~~~sql
SELECT customer_id
FROM customers
WHERE region_code IS NULL
   OR region_code = 'UNKNOWN';
~~~

Cách viết này biểu đạt điều kiện trực tiếp trên cột và có thể giúp optimizer tận dụng index tốt hơn, tùy thống kê và dữ liệu.

Không phải mọi biểu thức chứa hàm đều làm mất index trong mọi trường hợp. MySQL có thể hỗ trợ functional index hoặc generated column trong một số thiết kế. Hãy đo và kiểm tra kế hoạch thực thi thay vì suy đoán.

## 12. Bài thực hành: thay thế, chọn ưu tiên và loại giá trị sentinel

Thực hiện trong database lab riêng.

### Bước 1: tạo bảng

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_null_functions_lab;
USE mysql_null_functions_lab;

CREATE TABLE customer_contacts (
    customer_id INT NOT NULL PRIMARY KEY,
    preferred_name VARCHAR(100) NULL,
    legal_name VARCHAR(100) NULL,
    work_email VARCHAR(200) NULL,
    personal_email VARCHAR(200) NULL,
    phone_number VARCHAR(30) NULL
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO customer_contacts
    (customer_id, preferred_name, legal_name, work_email,
     personal_email, phone_number)
VALUES
    (1, 'An', 'Nguyen Van An', 'an@work.example', 'an@home.example', '0901000001'),
    (2, '', 'Tran Thi Binh', NULL, 'binh@home.example', '   '),
    (3, NULL, NULL, NULL, NULL, NULL),
    (4, 'Cuong', 'Le Van Cuong', NULL, NULL, '0904000004');
~~~

### Bước 2: thay một NULL bằng IFNULL

~~~sql
SELECT
    customer_id,
    IFNULL(preferred_name, 'Chưa đặt tên') AS preferred_name_display
FROM customer_contacts
ORDER BY customer_id;
~~~

Quan sát hàng số 2: preferred_name là chuỗi rỗng nên IFNULL không thay thế nó. Đây là hành vi đúng vì chuỗi rỗng không phải NULL.

### Bước 3: chọn tên đầu tiên có dữ liệu bằng COALESCE

~~~sql
SELECT
    customer_id,
    COALESCE(
        preferred_name,
        legal_name,
        'Khách hàng'
    ) AS selected_name
FROM customer_contacts
ORDER BY customer_id;
~~~

Hàng số 2 chọn chuỗi rỗng vì đây là giá trị khác NULL đầu tiên. Hàng số 3 chọn nhãn `Khách hàng`.

### Bước 4: kết hợp NULLIF và COALESCE

~~~sql
SELECT
    customer_id,
    COALESCE(
        NULLIF(TRIM(preferred_name), ''),
        NULLIF(TRIM(legal_name), ''),
        'Khách hàng'
    ) AS display_name,
    COALESCE(
        NULLIF(TRIM(work_email), ''),
        NULLIF(TRIM(personal_email), ''),
        'Chưa có email'
    ) AS contact_email,
    COALESCE(
        NULLIF(TRIM(phone_number), ''),
        'Chưa có số điện thoại'
    ) AS phone_display
FROM customer_contacts
ORDER BY customer_id;
~~~

Quan sát cách chuỗi rỗng và chuỗi chỉ chứa dấu cách được chuẩn hóa thành NULL trước khi chọn giá trị thay thế.

### Bước 5: kiểm tra NULLIF trong phép chia

~~~sql
SELECT
    100 / NULLIF(5, 0) AS valid_ratio,
    100 / NULLIF(0, 0) AS zero_denominator_ratio,
    COALESCE(100 / NULLIF(0, 0), 0) AS displayed_ratio;
~~~

Giải thích sự khác biệt giữa kết quả NULL và kết quả 0 được tạo bởi COALESCE.

### Bước 6: kiểm tra kiểu dữ liệu kết quả

~~~sql
CREATE TEMPORARY TABLE function_type_probe AS
SELECT
    IFNULL(1, 'test') AS ifnull_value,
    COALESCE(1, 'test') AS coalesce_value,
    NULLIF(CAST(1 AS DECIMAL(10,2)), 2) AS nullif_value;

DESCRIBE function_type_probe;

SELECT * FROM function_type_probe;

DROP TEMPORARY TABLE function_type_probe;
~~~

Đọc metadata của từng cột. Đối chiếu với quy tắc:

- IFNULL tổng hợp kiểu của hai đối số.
- COALESCE tổng hợp kiểu của tất cả đối số.
- NULLIF giữ kiểu của đối số thứ nhất.

Thử thay các literal bằng DECIMAL, SIGNED và CHAR để quan sát kiểu cột thay đổi.

### Bước 7: dọn dẹp

~~~sql
DROP DATABASE mysql_null_functions_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh sẽ xóa toàn bộ bảng và dữ liệu thực hành.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| IFNULL không thay giá trị 0 | 0 không phải NULL | Dùng NULLIF(value, 0) trước nếu 0 là sentinel theo nghiệp vụ |
| IFNULL không thay chuỗi rỗng | `''` khác NULL | Dùng NULLIF(TRIM(value), '') nếu phù hợp |
| COALESCE chọn giá trị không mong muốn | Thứ tự đối số không đúng chính sách ưu tiên | Sắp xếp lại thứ tự ưu tiên |
| COALESCE vẫn trả NULL | Tất cả đối số đều NULL | Thêm giá trị dự phòng cuối nếu nghiệp vụ yêu cầu |
| Kết quả IFNULL có kiểu chuỗi dù giá trị là số | Kiểu kết quả được tổng hợp từ cả hai đối số | Dùng CAST và giá trị dự phòng cùng kiểu |
| COALESCE tạo metadata không mong muốn | Các đối số có kiểu không đồng nhất | Chuẩn hóa kiểu tất cả nhánh bằng CAST |
| NULLIF trả NULL ngoài dự kiến | Hai chuỗi được xem là bằng nhau theo collation hoặc bị chuyển kiểu | Kiểm tra collation và kiểu; CAST/COLLATE rõ ràng |
| Phép chia vẫn cho NULL | NULLIF đổi mẫu số 0 thành NULL | Xác định nghiệp vụ muốn giữ NULL hay bọc COALESCE |
| Truy vấn chậm sau khi bọc cột trong COALESCE | Điều kiện có thể không tận dụng index thông thường | Viết điều kiện tương đương trên cột gốc và kiểm tra EXPLAIN |
| Ứng dụng nhận kiểu dữ liệu khác dự kiến | Metadata biểu thức khác giá trị mẫu | Kiểm tra kiểu qua CREATE TABLE ... SELECT hoặc connector metadata |

## 14. Checklist khi dùng các hàm xử lý NULL

- [ ] Đã xác định NULL có ý nghĩa gì trong cột: chưa biết, chưa nhập hay không áp dụng.
- [ ] Đã phân biệt NULL với 0, chuỗi rỗng và chuỗi chỉ có dấu cách.
- [ ] Dùng IFNULL khi chỉ có một giá trị dự phòng.
- [ ] Dùng COALESCE khi có nhiều nguồn giá trị theo thứ tự ưu tiên.
- [ ] Dùng NULLIF khi cần đổi một giá trị sentinel thành NULL hoặc bảo vệ mẫu số.
- [ ] Đã xác định thứ tự đối số COALESCE theo nghiệp vụ.
- [ ] Các nhánh có kiểu dữ liệu tương thích.
- [ ] Đã CAST rõ ràng khi cần hợp đồng kiểu ổn định cho view, bảng tạm hoặc API.
- [ ] Đã kiểm tra collation khi NULLIF so sánh chuỗi.
- [ ] Không chuyển 0 hoặc chuỗi rỗng thành NULL nếu chúng là dữ liệu hợp lệ.
- [ ] Đã xem xét tác động của hàm trong điều kiện WHERE tới khả năng dùng index.
- [ ] Đã kiểm tra kết quả và metadata bằng dữ liệu đại diện.

## 15. Nguyên tắc cần ghi nhớ

1. IFNULL nhận đúng hai đối số và chọn đối số thứ nhất nếu nó khác NULL.
2. COALESCE nhận từ hai đối số trở lên và trả giá trị khác NULL đầu tiên.
3. NULLIF trả NULL khi hai đối số bằng nhau; nếu không, trả đối số đầu tiên.
4. Cả ba hàm chỉ tạo giá trị trong biểu thức truy vấn; chúng không tự cập nhật dữ liệu trong bảng.
5. IFNULL có quy tắc kiểu kết quả riêng; không suy ra metadata chỉ từ giá trị thực tế được chọn.
6. COALESCE tổng hợp kiểu từ tất cả đối số, kể cả các nhánh không được chọn ở một hàng.
7. NULLIF giữ kiểu của đối số đầu tiên, nhưng phép so sánh vẫn chịu ảnh hưởng bởi chuyển đổi kiểu và collation.
8. Dùng CAST khi kiểu kết quả là một phần của hợp đồng dữ liệu.
9. NULLIF(value, 0) là mẫu hữu ích để tránh chia cho 0; quyết định có thay NULL thành 0 hay không phải dựa vào nghiệp vụ.
10. Kiểm tra metadata của biểu thức khi tạo bảng, view, bảng tạm hoặc tích hợp với connector.

## Tài liệu tham khảo chính thức

Các quy tắc trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [Flow Control Functions](https://dev.mysql.com/doc/refman/9.7/en/flow-control-functions.html): cú pháp, giá trị trả về và kiểu kết quả của IFNULL và NULLIF; quy tắc đánh giá expr1 của NULLIF.
2. [Comparison Functions and Operators](https://dev.mysql.com/doc/refman/9.7/en/comparison-operators.html): COALESCE, kiểu kết quả tổng hợp và quy tắc so sánh.
3. [Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/9.7/en/type-conversion.html): chuyển đổi kiểu trong biểu thức và so sánh.
4. [Character Set and Collation of Function Results](https://dev.mysql.com/doc/refman/9.7/en/string-functions-charset.html): character set, collation và cách tổng hợp kết quả hàm.
5. [Problems with NULL Values](https://dev.mysql.com/doc/refman/9.7/en/problems-with-null.html): khác biệt giữa NULL và chuỗi rỗng, quy tắc so sánh NULL.
6. [CREATE TABLE ... SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table-select.html): tạo cột từ biểu thức SELECT và kiểm tra kiểu dữ liệu suy ra.
7. [MySQL 9.7.2 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/9.7/en/news-9-7-2.html): điều chỉnh xử lý kiểu temporal trong IF và NULLIF.

