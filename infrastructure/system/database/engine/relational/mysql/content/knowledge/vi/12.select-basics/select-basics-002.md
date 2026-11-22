# Chọn cột, biểu thức, bí danh và truy vấn không cần bảng

Bài học thuộc chương **SELECT cơ bản** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Lệnh `SELECT` là nền tảng để đọc dữ liệu, tính toán giá trị, trình bày kết quả và kiểm tra nhanh biểu thức ngay trong MySQL.

Sau bài này, bạn có thể chọn cột cụ thể hoặc toàn bộ cột, viết biểu thức trong danh sách SELECT, đặt bí danh cho cột kết quả, hiểu các giá trị NULL và kiểu dữ liệu của biểu thức, đồng thời dùng SELECT không cần bảng để tính toán hoặc kiểm tra hàm.

## 1. Cấu trúc cơ bản của SELECT

Cấu trúc thường gặp:

~~~sql
SELECT
    [ALL | DISTINCT]
    select_expr [, select_expr ...]
[FROM table_name]
[WHERE condition]
[GROUP BY group_expression]
[HAVING group_condition]
[ORDER BY sort_expression [ASC | DESC]]
[LIMIT row_count];
~~~

Trong đó:

- `SELECT` xác định các giá trị hoặc cột cần trả về.
- Danh sách `select_expr` có thể chứa tên cột, biểu thức, hàm hoặc literal.
- `FROM` xác định bảng hoặc nguồn dữ liệu.
- `WHERE` lọc hàng đầu vào.
- `GROUP BY` gom các hàng thành nhóm.
- `HAVING` lọc nhóm.
- `ORDER BY` sắp xếp kết quả.
- `LIMIT` giới hạn số hàng trả về.

Bài học này tập trung vào danh sách biểu thức sau `SELECT`, bí danh cột và trường hợp không có `FROM`. Các mệnh đề lọc, nhóm và kết hợp bảng sẽ được học sâu hơn ở các bài tiếp theo.

Một truy vấn đơn giản:

~~~sql
SELECT product_id, product_name, price
FROM products;
~~~

MySQL trả về ba cột được yêu cầu từ các hàng của bảng `products`. Cột không được liệt kê sẽ không xuất hiện trong kết quả.

### Một SELECT có thể trả về nhiều biểu thức

~~~sql
SELECT
    10 AS quantity,
    25.50 AS unit_price,
    10 * 25.50 AS line_total;
~~~

Truy vấn này không đọc bảng nào. Nó tính ba biểu thức và trả về một hàng với ba cột.

## 2. Chọn cột cụ thể thay vì lấy tất cả

### Liệt kê tên cột

Cách rõ ràng nhất là ghi tên các cột cần đọc:

~~~sql
SELECT product_id, product_name
FROM products;
~~~

Chỉ hai cột này được đưa vào tập kết quả. Cách viết này có một số lợi ích:

- Người đọc biết ngay truy vấn cần dữ liệu nào.
- Ứng dụng không nhận thêm cột không sử dụng.
- Giảm lượng dữ liệu truyền qua mạng khi bảng có nhiều cột hoặc cột nội dung lớn.
- Ít bị ảnh hưởng khi schema thêm cột mới.
- Dễ rà soát dữ liệu nhạy cảm có thể bị trả về ngoài ý muốn.

Ví dụ, trang danh sách sản phẩm chỉ cần mã, tên và giá:

~~~sql
SELECT
    product_id,
    product_name,
    price
FROM products;
~~~

Không cần lấy mô tả dài, ảnh nhị phân hoặc dữ liệu JSON nếu màn hình không sử dụng chúng.

### Dùng dấu sao *

Dấu `*` yêu cầu MySQL trả về tất cả cột của nguồn dữ liệu:

~~~sql
SELECT *
FROM products;
~~~

Có thể dùng trong giai đoạn khám phá schema hoặc kiểm tra nhanh một bảng nhỏ. Tuy nhiên, không nên mặc định dùng `SELECT *` trong API hoặc truy vấn production vì:

- Thêm cột mới có thể làm thay đổi cấu trúc kết quả mà ứng dụng nhận.
- Có thể đọc cột lớn gây tốn I/O, bộ nhớ và băng thông.
- Có thể trả về cột nội bộ hoặc thông tin nhạy cảm không cần thiết.
- Khó nhận biết chính xác các cột mà truy vấn phụ thuộc.

### Chọn tất cả cột của một bảng trong truy vấn nhiều bảng

Khi truy vấn có nhiều bảng, có thể dùng bí danh bảng kèm dấu sao:

~~~sql
SELECT
    p.*,
    c.category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id;
~~~

`p.*` chỉ chọn các cột của bảng được đặt bí danh `p`. Cách này hữu ích khi muốn lấy toàn bộ cột của một bảng và chỉ một số cột của bảng khác.

### Tham chiếu cột có định danh rõ ràng

Một cột có thể được tham chiếu bằng:

- `column_name`: tên cột nếu không mơ hồ.
- `table_name.column_name`: tên bảng và tên cột.
- `database_name.table_name.column_name`: tên database, bảng và cột.

Ví dụ:

~~~sql
SELECT
    products.product_id,
    products.product_name
FROM shop.products;
~~~

Khi hai bảng cùng có cột `id`, hãy chỉ rõ bảng:

~~~sql
SELECT
    customers.id AS customer_id,
    orders.id AS order_id
FROM customers
JOIN orders
    ON orders.customer_id = customers.id;
~~~

Nếu tham chiếu cột không định danh trong khi có nhiều bảng cùng chứa tên đó, MySQL có thể báo lỗi `Column ... is ambiguous`. Việc ghi rõ tiền tố giúp truy vấn dễ đọc và tránh nhầm cột.

## 3. Biểu thức trong danh sách SELECT

Mỗi phần tử sau `SELECT` được gọi là một biểu thức chọn (`select_expr`). Biểu thức có thể là:

- Tên cột.
- Hằng số số, chuỗi, ngày giờ hoặc boolean.
- Phép toán số học.
- Phép so sánh hoặc logic.
- Lời gọi hàm.
- Biểu thức điều kiện như `CASE`.
- Kết hợp nhiều biểu thức.

MySQL tính các biểu thức cho từng hàng đầu vào rồi trả giá trị thành cột kết quả.

Giả sử bảng `products` có các cột:

| Cột | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `product_id` | INT | Mã sản phẩm |
| `product_name` | VARCHAR(200) | Tên sản phẩm |
| `price` | DECIMAL(12,2) | Giá bán |
| `stock_quantity` | INT | Số lượng tồn |
| `discount_rate` | DECIMAL(5,2) | Tỷ lệ giảm giá theo phần trăm |
| `description` | VARCHAR(500) | Mô tả ngắn, có thể NULL |
| `category_id` | INT | Mã danh mục |
| `status` | VARCHAR(20) | Trạng thái sản phẩm |

Có thể tính thành tiền sau giảm giá ngay trong SELECT:

~~~sql
SELECT
    product_id,
    product_name,
    price,
    discount_rate,
    price * (1 - discount_rate / 100) AS discounted_price
FROM products;
~~~

Cột `discounted_price` là giá trị được tính khi truy vấn chạy. Nó không tự tạo thêm cột trong bảng `products`.

### Phép toán số học

Các toán tử thường dùng:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `+` | Cộng | `price + 10` |
| `-` | Trừ | `price - 5` |
| `*` | Nhân | `price * stock_quantity` |
| `/` | Chia | `price / 2` |
| `DIV` | Chia lấy phần nguyên | `17 DIV 5` |
| `%` hoặc `MOD` | Phần dư | `17 % 5` |
| `-` | Đổi dấu | `-price` |

Ví dụ:

~~~sql
SELECT
    17 + 5 AS addition_result,
    17 - 5 AS subtraction_result,
    17 * 5 AS multiplication_result,
    17 / 5 AS division_result,
    17 DIV 5 AS integer_division_result,
    17 MOD 5 AS remainder_result;
~~~

Kết quả phép chia `/` có thể là số thập phân; `DIV` trả phần nguyên theo quy tắc chia số nguyên của MySQL. Hãy chọn kiểu dữ liệu phù hợp nếu kết quả được dùng để tính tiền hoặc lưu vào cột khác.

### Thứ tự ưu tiên toán tử và dấu ngoặc

MySQL thực hiện phép nhân và chia trước phép cộng và trừ. Khi biểu thức có nhiều bước nghiệp vụ, dùng dấu ngoặc để thể hiện rõ ý định:

~~~sql
SELECT
    price * (1 - discount_rate / 100) AS discounted_price
FROM products;
~~~

Nếu bỏ ngoặc không đúng chỗ, thứ tự tính có thể làm kết quả khác mong đợi. Đặc biệt với biểu thức tài chính, hãy kiểm tra kiểu DECIMAL, quy tắc làm tròn và độ chính xác thay vì chuyển sang FLOAT một cách tùy tiện.

## 4. Biểu thức chuỗi và hàm thường dùng

### Nối chuỗi bằng CONCAT

Trong MySQL, dùng `CONCAT()` để nối các chuỗi:

~~~sql
SELECT
    CONCAT('MySQL', ' ', 'Database') AS course_name;
~~~

Có thể nối cột:

~~~sql
SELECT
    CONCAT(product_name, ' - ', product_id) AS product_label
FROM products;
~~~

Nếu một đối số của `CONCAT()` là NULL, kết quả thường là NULL. Khi cần thay NULL bằng chuỗi rỗng hoặc giá trị mặc định, dùng `COALESCE()` hoặc `IFNULL()`:

~~~sql
SELECT
    CONCAT(
        product_name,
        ' - ',
        COALESCE(description, 'Chưa có mô tả')
    ) AS product_summary
FROM products;
~~~

### CONCAT_WS

`CONCAT_WS(separator, ...)` nối các đối số bằng dấu phân cách:

~~~sql
SELECT
    CONCAT_WS(' ', first_name, middle_name, last_name) AS full_name
FROM customers;
~~~

`CONCAT_WS` bỏ qua các đối số NULL sau đối số separator. Nếu separator là NULL, kết quả là NULL. Điều này khác với `CONCAT()`, nơi một đối số NULL có thể làm toàn bộ kết quả thành NULL.

### Chuyển chữ hoa và chữ thường

~~~sql
SELECT
    UPPER(product_name) AS uppercase_name,
    LOWER(product_name) AS lowercase_name
FROM products;
~~~

Kết quả chịu ảnh hưởng bởi character set và cách xử lý ký tự của MySQL. Với văn bản Unicode, hãy dùng charset phù hợp như `utf8mb4`.

### Độ dài ký tự và độ dài byte

`CHAR_LENGTH()` trả số ký tự; `LENGTH()` trả số byte:

~~~sql
SELECT
    'Cơ sở dữ liệu' AS sample_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    LENGTH('Cơ sở dữ liệu') AS byte_count;
~~~

Với UTF-8, một ký tự có thể chiếm nhiều byte. Không dùng `LENGTH()` để đếm ký tự người dùng nhìn thấy.

## 5. Biểu thức điều kiện: CASE, IF và NULL

### CASE

`CASE` tạo giá trị theo nhiều nhánh điều kiện:

~~~sql
SELECT
    product_id,
    product_name,
    stock_quantity,
    CASE
        WHEN stock_quantity = 0 THEN 'Hết hàng'
        WHEN stock_quantity < 10 THEN 'Sắp hết'
        ELSE 'Còn hàng'
    END AS stock_status
FROM products;
~~~

Có thể dùng dạng so sánh một biểu thức:

~~~sql
SELECT
    CASE 'A'
        WHEN 'A' THEN 'Đang hoạt động'
        WHEN 'I' THEN 'Ngừng hoạt động'
        ELSE 'Không xác định'
    END AS status_label;
~~~

Các nhánh THEN/ELSE trả về giá trị có kiểu mà MySQL tổng hợp từ các nhánh. Nếu các nhánh có kiểu không tương thích, MySQL có thể chuyển đổi kiểu kết quả. Nên trả các giá trị cùng kiểu và định dạng rõ ràng.

### IF

Hàm `IF(condition, value_if_true, value_if_false)` trả một trong hai giá trị:

~~~sql
SELECT
    product_name,
    IF(stock_quantity > 0, 'Có hàng', 'Hết hàng') AS availability
FROM products;
~~~

Nếu điều kiện là NULL, MySQL xử lý nó như không đúng và chọn nhánh thứ ba. Với logic nhiều nhánh hoặc cần rõ ràng, `CASE` thường dễ đọc hơn.

### NULL không phải là 0 hay chuỗi rỗng

NULL biểu thị giá trị không xác định hoặc không có. Nó khác với:

- Số 0.
- Chuỗi rỗng `''`.
- Chuỗi chứa dấu cách.
- Giá trị `FALSE`.

Các biểu thức số học với NULL thường trả NULL:

~~~sql
SELECT
    NULL + 10 AS arithmetic_result,
    CONCAT('Product: ', NULL) AS concat_result;
~~~

Kết quả của cả hai biểu thức là NULL.

Không kiểm tra NULL bằng toán tử `=`:

~~~sql
-- Không đúng để kiểm tra NULL
SELECT NULL = NULL AS comparison_result;
~~~

Kết quả so sánh là NULL (UNKNOWN), không phải TRUE. Dùng:

~~~sql
SELECT
    NULL IS NULL AS is_null,
    NULL IS NOT NULL AS is_not_null;
~~~

### COALESCE và IFNULL

`COALESCE(v1, v2, ...)` trả đối số đầu tiên không phải NULL:

~~~sql
SELECT
    product_name,
    COALESCE(description, 'Chưa có mô tả') AS display_description
FROM products;
~~~

`IFNULL(value, replacement)` nhận hai đối số và thay NULL bằng giá trị thay thế:

~~~sql
SELECT
    product_name,
    IFNULL(description, 'Chưa có mô tả') AS display_description
FROM products;
~~~

Dùng COALESCE khi có nhiều phương án dự phòng; dùng IFNULL khi chỉ có một giá trị thay thế.

### NULL-safe equality

MySQL cung cấp toán tử `<=>` để so sánh null-safe:

~~~sql
SELECT
    NULL <=> NULL AS both_null,
    10 <=> NULL AS one_null,
    10 <=> 10 AS same_value;
~~~

Kết quả lần lượt là 1, 0 và 1. Toán tử này hữu ích khi cần so sánh hai giá trị mà vẫn muốn xử lý trường hợp cả hai cùng NULL.

## 6. Ép kiểu và chuyển đổi kiểu trong biểu thức

MySQL có thể tự chuyển đổi kiểu khi biểu thức kết hợp số, chuỗi và ngày giờ. Đây là implicit conversion (chuyển đổi ngầm). Nó tiện lợi nhưng cũng có thể tạo kết quả khó đoán nếu dữ liệu không đồng nhất.

Ví dụ:

~~~sql
SELECT
    '10' + 5 AS numeric_result,
    CONCAT('10', 5) AS string_result;
~~~

Trong biểu thức cộng, chuỗi có thể được chuyển sang số. Trong CONCAT, các đối số được xử lý như chuỗi để nối.

Nếu chuỗi không phải số:

~~~sql
SELECT
    'abc' + 5 AS converted_result;
~~~

MySQL có thể chuyển phần chuỗi không có dạng số thành 0 và phát Warning tùy ngữ cảnh. Không nên dựa vào chuyển đổi ngầm để xử lý dữ liệu đầu vào không hợp lệ.

### CAST

Dùng `CAST(expr AS type)` để yêu cầu chuyển đổi rõ ràng:

~~~sql
SELECT
    CAST('125.75' AS DECIMAL(10,2)) AS amount,
    CAST('2026-11-19' AS DATE) AS report_date,
    CAST(123 AS CHAR) AS text_value;
~~~

Một số kiểu đích thường dùng gồm:

- `SIGNED`, `UNSIGNED`
- `DECIMAL(p,s)`
- `CHAR`
- `DATE`
- `DATETIME`
- `TIME`
- `JSON`

Có thể dùng `CONVERT(expr, type)` hoặc `CONVERT(expr USING charset)` cho một số mục tiêu chuyển kiểu/chuyển charset.

Ép kiểu không bảo đảm mọi dữ liệu đều chuyển đổi hợp lệ. Hãy kiểm tra Warning, SQL mode và kết quả sau chuyển đổi khi xử lý dữ liệu không sạch.

## 7. Bí danh cột bằng AS

Bí danh (alias) đặt tên cho cột kết quả của SELECT. Bí danh không đổi tên cột thật trong bảng và không tạo cột mới trong schema.

~~~sql
SELECT
    product_name AS name,
    price AS unit_price,
    price * stock_quantity AS inventory_value
FROM products;
~~~

Kết quả có các tiêu đề:

- `name`
- `unit_price`
- `inventory_value`

Alias đặc biệt hữu ích cho biểu thức dài, báo cáo và dữ liệu trả về cho ứng dụng.

Alias cũng không phải biến trung gian để dùng lại ngay trong một biểu thức khác ở cùng danh sách SELECT. Ví dụ, không thể đặt `price * stock_quantity AS inventory_value` rồi tham chiếu `inventory_value + 10` ở biểu thức kế tiếp trong cùng SELECT. Hãy lặp biểu thức hoặc bọc truy vấn trong derived table/CTE nếu cần tái sử dụng tên đó.

### Nên viết AS tường minh

MySQL cho phép bỏ từ khóa `AS`:

~~~sql
SELECT
    product_name name,
    price unit_price
FROM products;
~~~

Tuy nhiên, nên dùng `AS` để dễ đọc và tránh lỗi quên dấu phẩy:

~~~sql
-- Có thể bị hiểu price là bí danh của product_name
SELECT product_name price
FROM products;
~~~

Nếu ý định là chọn hai cột, câu đúng phải là:

~~~sql
SELECT
    product_name,
    price
FROM products;
~~~

### Alias có thể chứa dấu cách

Nếu cần tiêu đề có khoảng trắng, dùng identifier quote bằng backtick:

~~~sql
SELECT
    product_name AS `Product name`,
    price * stock_quantity AS `Inventory value`
FROM products;
~~~

Đối với tên alias có ký tự đặc biệt hoặc trùng từ khóa, backtick giúp MySQL hiểu đó là identifier. Tránh dùng dấu nháy đơn để tham chiếu alias ở các mệnh đề khác vì ở đó nó được hiểu là string literal.

### Alias dùng được ở đâu?

MySQL cho phép tham chiếu alias của biểu thức trong:

- `ORDER BY`
- `GROUP BY`
- `HAVING`

Ví dụ:

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
ORDER BY inventory_value DESC;
~~~

Không được dùng alias của danh sách SELECT trong `WHERE`:

~~~sql
-- Không hợp lệ: alias chưa được xác định ở thời điểm WHERE được xử lý
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
WHERE inventory_value > 1000;
~~~

Hãy lặp lại biểu thức hoặc dùng truy vấn con/CTE khi muốn đặt tên cho giá trị rồi lọc ở lớp ngoài:

~~~sql
SELECT *
FROM (
    SELECT
        product_name,
        price * stock_quantity AS inventory_value
    FROM products
) AS product_values
WHERE inventory_value > 1000;
~~~

### Tránh alias trùng tên cột

Không nên đặt alias giống một cột khác trong cùng nguồn dữ liệu. Khi MySQL phân giải tên trong ORDER BY, GROUP BY hoặc HAVING, xung đột giữa tên cột và alias có thể làm truy vấn khó hiểu hoặc phát Warning.

Hãy đặt tên rõ nghĩa, duy nhất trong danh sách SELECT, ví dụ `calculated_total`, `customer_label`, `stock_status`.

## 8. SELECT không cần FROM

MySQL có thể tính toán biểu thức mà không cần đọc bảng:

~~~sql
SELECT 1 + 1;
~~~

Kết quả:

~~~text
+-------+
| 1 + 1 |
+-------+
|     2 |
+-------+
~~~

Một số ví dụ hữu ích:

~~~sql
SELECT
    VERSION() AS mysql_version,
    CURRENT_USER() AS authenticated_account,
    DATABASE() AS current_database,
    NOW() AS current_time;
~~~

Các hàm này cho biết phiên bản server, tài khoản MySQL thực tế, database hiện chọn và thời gian session.

Một SELECT chỉ tính biểu thức và không đọc bảng không cần quyền `SELECT` trên một database/table. Quyền `SELECT` được kiểm tra khi câu lệnh thực sự truy cập bảng hoặc view.

### Tính toán nhanh

~~~sql
SELECT
    1250 * 1.08 AS price_with_tax,
    100 DIV 7 AS whole_groups,
    100 MOD 7 AS remainder;
~~~

### Kiểm tra hàm và biểu thức

~~~sql
SELECT
    UPPER('mysql') AS upper_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    ROUND(123.4567, 2) AS rounded_value,
    COALESCE(NULL, NULL, 'fallback') AS fallback_value;
~~~

### Kiểm tra session

~~~sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.autocommit AS session_autocommit;
~~~

Các biến hệ thống có thể đọc bằng cú pháp `@@variable_name`. Dùng `@@SESSION` hoặc `@@GLOBAL` khi muốn chỉ rõ phạm vi.

### DUAL là gì?

Có thể viết:

~~~sql
SELECT 1 + 1 FROM DUAL;
~~~

`DUAL` là tên bảng giả tương thích với một số hệ quản trị khác. MySQL không yêu cầu FROM DUAL khi truy vấn không tham chiếu bảng nào:

~~~sql
SELECT 1 + 1;
~~~

Hai cách trên cho kết quả giống nhau trong ví dụ này. Với MySQL, nên dùng SELECT không FROM để câu lệnh gọn và thể hiện đúng rằng không có bảng nguồn. DUAL chỉ cần khi muốn giữ cú pháp tương thích hoặc chuyển câu truy vấn giữa các hệ quản trị.

### SELECT không FROM trả về bao nhiêu hàng?

Một SELECT gồm các biểu thức hằng hoặc hàm, không có FROM và không có điều kiện loại bỏ hàng, trả về một hàng:

~~~sql
SELECT 'MySQL' AS database_name, 9 + 7 AS version_major_minor;
~~~

Kết quả gồm một hàng và hai cột.

Nếu dùng điều kiện WHERE không đúng, kết quả có thể không có hàng:

~~~sql
SELECT 1 AS value
WHERE 1 = 0;
~~~

SELECT không FROM vẫn là một truy vấn; nó chỉ không cần bảng làm nguồn dữ liệu.

## 9. ALL, DISTINCT và kết quả trùng lặp

Mặc định, SELECT dùng `ALL`, nghĩa là giữ các hàng trùng nhau:

~~~sql
SELECT ALL category_id
FROM products;
~~~

Từ khóa ALL có thể bỏ qua vì đây là mặc định.

Dùng `DISTINCT` để loại các hàng trùng nhau trong tập cột được chọn:

~~~sql
SELECT DISTINCT category_id
FROM products;
~~~

Nếu chọn nhiều cột, MySQL loại hàng khi toàn bộ tổ hợp giá trị được chọn trùng nhau:

~~~sql
SELECT DISTINCT
    category_id,
    status
FROM products;
~~~

Điều này khác với việc chỉ loại trùng theo `category_id`. Nếu cùng category nhưng status khác nhau, hai hàng vẫn được giữ.

Có thể dùng DISTINCT trên biểu thức:

~~~sql
SELECT DISTINCT
    LOWER(product_name) AS normalized_name
FROM products;
~~~

`DISTINCT` không tự sắp xếp kết quả theo thứ tự nghiệp vụ. Nếu cần thứ tự ổn định, hãy dùng `ORDER BY` rõ ràng.

## 10. Kết quả SELECT không có thứ tự mặc định

Nếu không có `ORDER BY`, MySQL không bảo đảm thứ tự các hàng. Thứ tự quan sát được có thể thay đổi theo index, kế hoạch thực thi, dữ liệu, phiên bản hoặc hoạt động của server.

Không nên viết code ứng dụng giả định:

~~~sql
SELECT product_id, product_name
FROM products;
~~~

luôn trả theo `product_id` tăng dần chỉ vì hiện tại dữ liệu có vẻ như vậy.

Nếu cần thứ tự, hãy chỉ định:

~~~sql
SELECT product_id, product_name
FROM products
ORDER BY product_id ASC;
~~~

Nếu cần phân trang ổn định, nên dùng một khóa sắp xếp có tính duy nhất hoặc thêm khóa phụ:

~~~sql
SELECT product_id, product_name
FROM products
ORDER BY product_name ASC, product_id DESC
LIMIT 20;
~~~

Không dựa vào thứ tự vật lý của hàng hoặc thứ tự index nếu truy vấn không yêu cầu sắp xếp.

## 11. Ví dụ kết hợp: tạo kết quả phục vụ màn hình danh sách

Giả sử một trang quản lý sản phẩm cần hiển thị:

- Mã sản phẩm.
- Tên sản phẩm.
- Giá hiện tại.
- Giá sau giảm.
- Trạng thái tồn kho.
- Nhãn hiển thị cho người dùng.

Có thể viết:

~~~sql
SELECT
    p.product_id AS id,
    p.product_name AS name,
    p.price AS original_price,
    p.price * (1 - p.discount_rate / 100) AS discounted_price,
    CASE
        WHEN p.stock_quantity <= 0 THEN 'Hết hàng'
        WHEN p.stock_quantity < 10 THEN 'Sắp hết'
        ELSE 'Còn hàng'
    END AS stock_status,
    CONCAT(
        p.product_name,
        ' (#',
        p.product_id,
        ')'
    ) AS display_label
FROM products AS p
ORDER BY p.product_name ASC, p.product_id ASC
LIMIT 50;
~~~

Điểm đáng chú ý:

- Chỉ chọn các cột cần dùng.
- Biểu thức tính giá được đặt alias rõ ràng.
- CASE tạo trạng thái theo tồn kho.
- CONCAT tạo nhãn trình bày.
- ORDER BY xác định thứ tự.
- LIMIT giới hạn số hàng trả về.

Nếu `discount_rate` có thể NULL, phép tính `price * (1 - discount_rate / 100)` cũng có thể trả NULL. Khi nghiệp vụ xem NULL là không giảm giá, hãy dùng `COALESCE(discount_rate, 0)` một cách có chủ đích.

## 12. Bài thực hành: biểu thức, alias và SELECT không FROM

Các câu lệnh sau dùng database lab riêng.

### Bước 1: tính toán không cần bảng

~~~sql
SELECT
    250 * 1.08 AS price_after_tax,
    250 DIV 7 AS full_groups,
    250 MOD 7 AS remaining_units;
~~~

Giải thích kết quả của từng biểu thức và phân biệt phép chia `/` với `DIV`.

### Bước 2: kiểm tra hàm chuỗi và NULL

~~~sql
SELECT
    CONCAT('MySQL', ' ', 'Lab') AS course_name,
    CONCAT('Name: ', NULL) AS concat_with_null,
    CONCAT_WS(' ', 'Nguyen', NULL, 'An') AS concat_ws_result,
    COALESCE(NULL, NULL, 'default') AS fallback_value,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    LENGTH('Cơ sở dữ liệu') AS byte_count;
~~~

Quan sát cách CONCAT và CONCAT_WS xử lý NULL, đồng thời so sánh số ký tự và số byte.

### Bước 3: tạo bảng thử nghiệm

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_select_basics_lab;
USE mysql_select_basics_lab;

CREATE TABLE products (
    product_id INT NOT NULL PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    discount_rate DECIMAL(5,2) NULL,
    stock_quantity INT NOT NULL,
    description VARCHAR(500) NULL,
    category_id INT NOT NULL,
    status VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

INSERT INTO products
    (product_id, product_name, price, discount_rate, stock_quantity,
     description, category_id, status)
VALUES
    (1, 'Keyboard', 850000.00, 10.00, 25, 'Bàn phím cơ', 1, 'A'),
    (2, 'Mouse', 250000.00, 5.00, 6, NULL, 1, 'A'),
    (3, 'Monitor', 4200000.00, NULL, 0, 'Màn hình 27 inch', 2, 'I'),
    (4, 'USB Hub', 320000.00, 0.00, 80, 'Hub USB-C', 1, 'A');
~~~

### Bước 4: chọn cột cụ thể

~~~sql
SELECT product_id, product_name
FROM products;
~~~

So sánh với:

~~~sql
SELECT *
FROM products;
~~~

Liệt kê những cột bổ sung mà dấu sao trả về.

### Bước 5: tính biểu thức và đặt alias

~~~sql
SELECT
    product_name AS name,
    price AS original_price,
    price * (1 - COALESCE(discount_rate, 0) / 100) AS final_price,
    stock_quantity * price AS inventory_value
FROM products;
~~~

Giải thích vì sao `COALESCE(discount_rate, 0)` giúp hàng Monitor có giá sau giảm bằng giá gốc.

### Bước 6: dùng alias trong ORDER BY

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
ORDER BY inventory_value DESC;
~~~

Thử thay alias bằng tên biểu thức đầy đủ. Quan sát kết quả có thay đổi không.

### Bước 7: thử lỗi tham chiếu alias trong WHERE

Câu sau không hợp lệ:

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
WHERE inventory_value > 1000000;
~~~

Viết lại bằng biểu thức:

~~~sql
SELECT
    product_name,
    price * stock_quantity AS inventory_value
FROM products
WHERE price * stock_quantity > 1000000;
~~~

Hoặc dùng derived table:

~~~sql
SELECT *
FROM (
    SELECT
        product_name,
        price * stock_quantity AS inventory_value
    FROM products
) AS product_values
WHERE inventory_value > 1000000;
~~~

### Bước 8: kiểm tra DISTINCT

~~~sql
SELECT DISTINCT discount_rate
FROM products;
~~~

Thử:

~~~sql
SELECT DISTINCT discount_rate, stock_quantity
FROM products;
~~~

Giải thích vì sao số hàng của hai truy vấn có thể khác nhau.

### Bước 9: dọn dẹp

~~~sql
DROP DATABASE mysql_select_basics_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh sẽ xóa toàn bộ bảng và dữ liệu thực hành.

## 13. Những lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Unknown column` trong SELECT | Tên cột sai hoặc cột không thuộc nguồn dữ liệu | Kiểm tra tên cột và định danh bảng |
| `Column ... is ambiguous` | Nhiều bảng có cùng tên cột | Dùng `table_name.column_name` hoặc alias bảng |
| Alias không dùng được trong WHERE | WHERE được xử lý trước giá trị alias trong SELECT | Lặp biểu thức hoặc dùng derived table/CTE |
| Alias không được nhận như mong đợi | Thiếu dấu phẩy khiến biểu thức sau bị hiểu là alias | Dùng dấu phẩy và viết AS tường minh |
| Kết quả số khác mong đợi | Chuyển đổi kiểu ngầm hoặc ưu tiên toán tử | Dùng CAST và dấu ngoặc rõ ràng |
| Kết quả biểu thức thành NULL | Một toán hạng là NULL hoặc hàm xử lý NULL | Dùng IS NULL, COALESCE hoặc IFNULL theo nghiệp vụ |
| CONCAT trả NULL | Có đối số NULL | Dùng CONCAT_WS hoặc thay NULL có chủ đích |
| Kết quả DISTINCT vẫn có nhiều hàng | Toàn bộ tổ hợp cột được chọn chưa trùng | Xác định đúng tập cột cần loại trùng |
| Thứ tự hàng thay đổi | Không có ORDER BY | Chỉ định ORDER BY với khóa sắp xếp rõ |
| SELECT * trả dữ liệu quá lớn | Lấy cả cột không cần thiết | Liệt kê cột cụ thể |

## 14. Nguyên tắc cần ghi nhớ

1. Danh sách sau SELECT có thể chứa tên cột, literal, phép toán, hàm và biểu thức điều kiện.
2. Chọn đúng cột cần dùng; chỉ sử dụng `*` khi thật sự muốn lấy toàn bộ.
3. Khi nhiều bảng có cột trùng tên, định danh bằng tên bảng hoặc alias bảng.
4. Dùng `AS` tường minh để đặt alias cho cột kết quả và biểu thức.
5. Alias là tên trong tập kết quả, không thay đổi schema.
6. Alias có thể dùng trong ORDER BY, GROUP BY và HAVING theo quy tắc MySQL; không dùng trực tiếp trong WHERE.
7. NULL khác 0 và chuỗi rỗng; dùng IS NULL, COALESCE, IFNULL hoặc toán tử <=> theo mục đích.
8. Dùng CAST khi cần chuyển kiểu rõ ràng và kiểm tra Warning khi chuyển đổi dữ liệu.
9. SELECT không cần FROM có thể dùng để tính toán, kiểm tra hàm và biến hệ thống; DUAL là tùy chọn.
10. Không có ORDER BY thì không có bảo đảm về thứ tự hàng.
11. DISTINCT loại các hàng trùng theo toàn bộ danh sách biểu thức được chọn.
12. Trong ứng dụng, chỉ trả các cột cần thiết để giảm dữ liệu truyền và tránh lộ thông tin không cần thiết.

## Tài liệu tham khảo chính thức

Các cú pháp và hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/select.html): danh sách biểu thức, chọn cột, SELECT không cần bảng, DUAL, DISTINCT, ORDER BY và LIMIT.
2. [Problems with Column Aliases](https://dev.mysql.com/doc/refman/9.7/en/problems-with-alias.html): phạm vi sử dụng alias và lý do không thể dùng alias trong WHERE.
3. [Expressions](https://dev.mysql.com/doc/refman/9.7/en/expressions.html): biểu thức, toán tử và cách MySQL đánh giá giá trị.
4. [Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/9.7/en/type-conversion.html): chuyển đổi kiểu ngầm trong biểu thức.
5. [Flow Control Functions](https://dev.mysql.com/doc/refman/9.7/en/flow-control-functions.html): CASE, IF, IFNULL và COALESCE.
6. [String Functions](https://dev.mysql.com/doc/refman/9.7/en/string-functions.html): CONCAT, CONCAT_WS, LENGTH, CHAR_LENGTH, UPPER và LOWER.
7. [NULL Values](https://dev.mysql.com/doc/refman/9.7/en/working-with-null.html): ngữ nghĩa NULL và các phép kiểm tra NULL.
8. [Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): quyền SELECT khi đọc bảng và các SELECT không truy cập bảng.

