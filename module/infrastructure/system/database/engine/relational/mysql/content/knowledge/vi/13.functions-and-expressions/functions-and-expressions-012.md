# LEAST, GREATEST và xử lý NULL hoặc kiểu dữ liệu hỗn hợp

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Hai hàm **LEAST()** và **GREATEST()** giúp chọn giá trị nhỏ nhất hoặc lớn nhất trong một danh sách biểu thức của cùng một hàng. Chúng hữu ích khi giới hạn giá trị trong một khoảng, so sánh nhiều mốc thời gian hoặc chọn một ngưỡng theo dữ liệu.

Kết quả có thể gây bất ngờ nếu danh sách chứa **NULL**, trộn số với chuỗi hoặc dùng các chuỗi có collation khác nhau. Cần hiểu cách MySQL so sánh các đối số trước khi dùng hai hàm trong truy vấn nghiệp vụ.

## 1. LEAST() và GREATEST() làm gì?

**LEAST(value1, value2, ...)** trả về đối số có giá trị nhỏ nhất; **GREATEST(value1, value2, ...)** trả về đối số có giá trị lớn nhất. Mỗi hàm cần ít nhất hai đối số.

~~~sql
SELECT
    LEAST(12, 5, 20, 8) AS smallest_value,
    GREATEST(12, 5, 20, 8) AS largest_value;
~~~

Kết quả:

| smallest_value | largest_value |
|---:|---:|
| 5 | 20 |

Hai hàm là scalar function: chúng so sánh các đối số trong một lần đánh giá biểu thức, thường là trên từng hàng. Chúng không quét nhiều hàng của một bảng để tìm min/max như aggregate MIN() và MAX().

Ví dụ với dữ liệu mỗi sản phẩm có hai mức giá:

~~~sql
SELECT product_id,
       LEAST(list_price, sale_price) AS lower_price,
       GREATEST(list_price, sale_price) AS higher_price
FROM products;
~~~

Với mỗi hàng, MySQL so sánh list_price và sale_price rồi trả về một trong hai giá trị. Cần xác định rõ ý nghĩa nghiệp vụ của hai cột; hàm không tự hiểu giá nào là giá niêm yết hoặc giá khuyến mãi.

## 2. Cú pháp và vị trí sử dụng

~~~sql
LEAST(value1, value2, ...)
GREATEST(value1, value2, ...)
~~~

Có thể sử dụng các hàm trong SELECT, WHERE, ORDER BY, UPDATE và biểu thức SQL khác:

~~~sql
SELECT order_id,
       LEAST(requested_quantity, available_quantity) AS fulfillable_quantity
FROM order_requests;
~~~

Ví dụ giới hạn số lượng giao theo lượng khách yêu cầu và lượng hàng có sẵn. Nếu một trong hai đối số là NULL, kết quả của LEAST() cũng là NULL; phần xử lý dữ liệu thiếu cần được quyết định riêng.

Ví dụ giới hạn điểm số trong khoảng 0 đến 100:

~~~sql
SELECT student_id,
       LEAST(GREATEST(raw_score, 0), 100) AS normalized_score
FROM exam_results;
~~~

Biểu thức thực hiện theo thứ tự:

1. GREATEST(raw_score, 0) bảo đảm kết quả không nhỏ hơn 0.
2. LEAST(..., 100) giới hạn kết quả tối đa là 100.

Nếu raw_score là NULL, toàn bộ biểu thức vẫn là NULL. Không nên thay giá trị thiếu bằng 0 nếu nghiệp vụ phân biệt "chưa có điểm" với "điểm bằng 0".

## 3. Phân biệt với MIN() và MAX()

LEAST()/GREATEST() và MIN()/MAX() có tên gọi gần nhau nhưng phạm vi tính toán khác nhau:

| Hàm | Loại | Phạm vi |
|---|---|---|
| LEAST(a, b, c) | Scalar | So sánh nhiều biểu thức trong cùng một lần tính |
| GREATEST(a, b, c) | Scalar | So sánh nhiều biểu thức trong cùng một lần tính |
| MIN(column) | Aggregate | Tìm giá trị nhỏ nhất của một cột trên tập hàng hoặc nhóm |
| MAX(column) | Aggregate | Tìm giá trị lớn nhất của một cột trên tập hàng hoặc nhóm |

Ví dụ chọn mức thấp hơn giữa hai cột trong mỗi sản phẩm:

~~~sql
SELECT product_id, LEAST(price_a, price_b) AS lower_price
FROM product_prices;
~~~

Ví dụ tìm giá thấp nhất trong toàn bộ sản phẩm:

~~~sql
SELECT MIN(price_a) AS minimum_price_a
FROM product_prices;
~~~

MIN() và MAX() là aggregate nên bỏ qua các giá trị NULL; nếu không có giá trị không NULL trong tập đầu vào, kết quả là NULL. Ngược lại, LEAST() và GREATEST() trả NULL nếu bất kỳ đối số nào là NULL. Đây là khác biệt quan trọng khi xử lý dữ liệu thiếu.

## 4. NULL làm kết quả của LEAST và GREATEST thành NULL

Trong MySQL, nếu bất kỳ đối số nào của LEAST() hoặc GREATEST() là NULL, kết quả của hàm là NULL:

~~~sql
SELECT
    LEAST(10, NULL, 20) AS least_result,
    GREATEST(10, NULL, 20) AS greatest_result;
~~~

Cả hai cột kết quả đều là NULL, dù các đối số còn lại có giá trị xác định.

### 4.1. NULL lan truyền qua biểu thức

Giả sử start_price có giá trị 100 và discount_price chưa được cung cấp:

~~~sql
SELECT LEAST(start_price, discount_price) AS effective_price
FROM product_prices;
~~~

Kết quả là NULL, không phải 100. Hàm không tự hiểu rằng đối số thiếu cần bị bỏ qua.

Tương tự, GREATEST() cũng không tự chọn đối số khác NULL. Điều này phù hợp với quy tắc lan truyền NULL: khi một đầu vào cần thiết không xác định, kết quả phép so sánh có thể không xác định.

### 4.2. Phân biệt NULL với 0 và chuỗi rỗng

~~~sql
SELECT
    LEAST(0, 5) AS zero_and_five,
    LEAST('', 'A') AS empty_and_text,
    LEAST(NULL, 5) AS null_and_five;
~~~

Số 0 là một giá trị số; chuỗi rỗng là một giá trị chuỗi; NULL là trạng thái không có giá trị. Không thay NULL bằng 0 hoặc chuỗi rỗng chỉ để hàm trả kết quả nếu điều đó làm sai nghĩa dữ liệu.

### 4.3. NULL đến từ LEFT JOIN

Một cột được lấy từ phía phải của LEFT JOIN có thể là NULL do không có hàng khớp:

~~~sql
SELECT c.customer_id,
       LEAST(c.credit_limit, p.requested_limit) AS allowed_limit
FROM customers AS c
LEFT JOIN pending_limits AS p
  ON p.customer_id = c.customer_id;
~~~

Nếu khách hàng chưa có hàng trong pending_limits, p.requested_limit là NULL trong kết quả join và allowed_limit cũng là NULL. Cần xác định "không có yêu cầu" có nghĩa là dùng credit_limit, không áp dụng giới hạn hay chưa thể tính. Không để LEAST() quyết định thay quy tắc nghiệp vụ.

## 5. Khi muốn bỏ qua đối số NULL

Đôi khi nghiệp vụ muốn chọn giá trị nhỏ nhất/lớn nhất trong các đối số có giá trị, bỏ qua những đối số NULL. LEAST() và GREATEST() không thực hiện quy tắc đó tự động.

### 5.1. Hai đối số: dùng CASE

Với hai giá trị a và b, có thể viết rõ:

~~~sql
SELECT
    CASE
        WHEN a IS NULL THEN b
        WHEN b IS NULL THEN a
        ELSE LEAST(a, b)
    END AS least_non_null,
    CASE
        WHEN a IS NULL THEN b
        WHEN b IS NULL THEN a
        ELSE GREATEST(a, b)
    END AS greatest_non_null
FROM measurements;
~~~

Nếu cả hai đều NULL, nhánh đầu trả b (cũng NULL). Nếu chỉ một giá trị có mặt, giá trị đó được trả về. Nếu cả hai có mặt, hàm so sánh bình thường.

### 5.2. Nhiều đối số trong cùng một hàng

Với ba cột, có thể viết CASE để xử lý từng khả năng NULL:

~~~sql
SELECT measurement_id,
       CASE
           WHEN value_a IS NULL AND value_b IS NULL THEN value_c
           WHEN value_a IS NULL AND value_c IS NULL THEN value_b
           WHEN value_b IS NULL AND value_c IS NULL THEN value_a
           WHEN value_a IS NULL THEN LEAST(value_b, value_c)
           WHEN value_b IS NULL THEN LEAST(value_a, value_c)
           WHEN value_c IS NULL THEN LEAST(value_a, value_b)
           ELSE LEAST(value_a, value_b, value_c)
       END AS smallest_non_null
FROM measurements;
~~~

Nếu cả ba cột NULL, điều kiện đầu đúng và value_c cũng NULL nên kết quả vẫn NULL. Có thể viết CASE tương tự với GREATEST() để tìm giá trị lớn nhất. Khi số cột tăng, cách viết này dài; hãy cân nhắc chuẩn hóa dữ liệu thành các hàng hoặc dùng quy trình unpivot phù hợp.

### 5.3. Nhiều cột trên toàn bộ bảng: dùng MIN/MAX

Nếu cần tìm min/max trên toàn bộ các cột và hàng, có thể chuyển dữ liệu thành một tập giá trị bằng UNION ALL:

~~~sql
SELECT MIN(value) AS overall_minimum,
       MAX(value) AS overall_maximum
FROM (
    SELECT value_a AS value FROM measurements
    UNION ALL
    SELECT value_b FROM measurements
    UNION ALL
    SELECT value_c FROM measurements
) AS all_values;
~~~

MIN() và MAX() bỏ qua NULL; nếu toàn bộ giá trị là NULL, kết quả vẫn NULL. Ví dụ này tính trên toàn bộ bảng, không phải min/max riêng cho từng hàng. Dùng UNION ALL để giữ mọi giá trị và tránh chi phí loại trùng không cần thiết.

### 5.4. Dùng COALESCE với sentinel có thể nguy hiểm

Một cách thường thấy là thay NULL bằng một số cực lớn hoặc cực nhỏ rồi gọi LEAST()/GREATEST(). Cách này chỉ đúng nếu sentinel chắc chắn nằm ngoài miền giá trị hợp lệ và không thể xuất hiện trong dữ liệu thật.

~~~sql
-- Chỉ minh họa; sentinel phải được xác định theo miền dữ liệu
SELECT LEAST(
    COALESCE(value_a, 999999999),
    COALESCE(value_b, 999999999)
) AS smallest_value
FROM measurements;
~~~

Nếu 999999999 là một giá trị hợp lệ, kết quả có thể sai. Với ngày giờ, việc chọn ngày giả còn dễ gây nhầm lẫn. Ưu tiên CASE hoặc aggregate trên tập hàng khi cần bỏ qua NULL.

## 6. Quy tắc so sánh kiểu số

MySQL chọn cách so sánh dựa trên kiểu của các đối số. Các quy tắc quan trọng đối với LEAST() và GREATEST():

- Nếu tất cả đối số là số nguyên, so sánh như số nguyên.
- Nếu có ít nhất một đối số kiểu DOUBLE, so sánh như DOUBLE.
- Nếu không có DOUBLE nhưng có ít nhất một đối số DECIMAL, so sánh như DECIMAL.
- Nếu danh sách có kết hợp số và chuỗi, các đối số được so sánh như chuỗi.

Vì vậy, không nên trộn số và chuỗi chỉ vì chuỗi có vẻ chứa chữ số. Giá trị '100' là chuỗi, không mặc nhiên mang cùng ngữ nghĩa với số 100 trong mọi biểu thức.

### 6.1. Các đối số số nguyên

~~~sql
SELECT
    LEAST(8, 12, 3) AS min_integer,
    GREATEST(8, 12, 3) AS max_integer;
~~~

Các đối số là số nguyên nên được so sánh theo giá trị số.

### 6.2. DECIMAL và dữ liệu tài chính

Với số tiền, nên dùng DECIMAL có precision/scale phù hợp:

~~~sql
SELECT LEAST(
           CAST('125.50' AS DECIMAL(12,2)),
           CAST('99.90' AS DECIMAL(12,2))
       ) AS lower_amount;
~~~

DECIMAL biểu diễn số thập phân chính xác theo precision/scale khai báo. Nếu có đối số DOUBLE, MySQL so sánh theo DOUBLE, vốn là kiểu dấu phẩy động gần đúng. Tránh để một literal hoặc cột DOUBLE vô tình làm thay đổi cách so sánh các giá trị tiền.

### 6.3. DOUBLE và số gần đúng

~~~sql
SELECT GREATEST(1.25E0, 1.20, 1.30) AS greatest_value;
~~~

Ký hiệu khoa học như 1.25E0 là literal gần đúng kiểu dấu phẩy động. Khi một đối số là DOUBLE, quy tắc so sánh chuyển sang DOUBLE. Nếu yêu cầu nghiệp vụ cần so sánh thập phân chính xác, hãy chuyển các giá trị về DECIMAL phù hợp trước khi gọi hàm.

### 6.4. Tránh trộn số với chuỗi số

Một ví dụ dễ gây bất ngờ:

~~~sql
SELECT GREATEST(2, '10') AS result;
~~~

Vì danh sách có cả số và chuỗi, MySQL so sánh chúng như chuỗi. Theo thứ tự từ điển, chuỗi '2' lớn hơn chuỗi '10', nên kết quả được chọn có thể là đối số 2, dù về số học 10 lớn hơn 2.

Nếu muốn so sánh số học, chuyển kiểu tường minh:

~~~sql
SELECT GREATEST(
           CAST(2 AS DECIMAL(10,0)),
           CAST('10' AS DECIMAL(10,0))
       ) AS numeric_result;
~~~

Kết quả số học là 10. Trước khi CAST chuỗi thành số, cần xác thực dữ liệu đầu vào. Chuỗi không phải số có thể tạo giá trị chuyển đổi không mong đợi, warning hoặc lỗi tùy ngữ cảnh và SQL mode.

## 7. Quy tắc so sánh chuỗi và collation

Khi các đối số được so sánh như chuỗi, collation quyết định thứ tự. Collation có thể phân biệt hoặc không phân biệt chữ hoa/thường, dấu và một số khác biệt Unicode.

~~~sql
SELECT
    LEAST('apple', 'Banana') AS first_value,
    GREATEST('apple', 'Banana') AS last_value;
~~~

Kết quả phụ thuộc collation được áp dụng cho biểu thức. Với collation không phân biệt hoa/thường, hai chuỗi khác nhau về chữ hoa/thường có thể được xem là tương đương trong so sánh; với collation phân biệt, thứ tự có thể khác.

### 7.1. Chỉ định collation rõ ràng

Nếu cần một quy tắc so sánh cụ thể, chỉ định collation:

~~~sql
SELECT LEAST(
           _utf8mb4'An' COLLATE utf8mb4_0900_as_cs,
           _utf8mb4'an' COLLATE utf8mb4_0900_as_cs
       ) AS case_sensitive_min;
~~~

utf8mb4_0900_as_cs là collation của MySQL 8.0, phân biệt dấu và hoa/thường. Trên phiên bản khác, hãy kiểm tra collation có sẵn bằng SHOW COLLATION và chọn quy tắc phù hợp.

### 7.2. Collation không tương thích

Nếu các biểu thức chuỗi đến từ cột hoặc literal có collation không tương thích, MySQL có thể báo lỗi trộn collation. Kiểm tra:

~~~sql
SELECT
    CHARSET(column_a) AS charset_a,
    COLLATION(column_a) AS collation_a,
    CHARSET(column_b) AS charset_b,
    COLLATION(column_b) AS collation_b
FROM sample_table
LIMIT 10;
~~~

Có thể chuyển các biểu thức về cùng charset/collation trước khi so sánh:

~~~sql
SELECT LEAST(
           CONVERT(column_a USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
           CONVERT(column_b USING utf8mb4) COLLATE utf8mb4_0900_ai_ci
       ) AS least_text
FROM sample_table;
~~~

Chỉ dùng collation đích nếu server hỗ trợ và quy tắc đó đúng với yêu cầu nghiệp vụ. Không chọn collation chỉ để làm biến mất lỗi kỹ thuật; collation mới có thể thay đổi thứ tự và kết quả so sánh.

### 7.3. Chuỗi nhị phân

Nếu các đối số là chuỗi nhị phân, việc so sánh dựa trên byte thay vì quy tắc ngôn ngữ của collation văn bản. Không dùng chuỗi nhị phân để thay thế cho quy tắc so sánh tên, địa chỉ hoặc văn bản người dùng trừ khi mục tiêu thật sự là so sánh byte.

## 8. So sánh ngày và thời gian

Khi so sánh mốc thời gian, hãy bảo đảm các đối số cùng kiểu DATE, DATETIME hoặc TIMESTAMP theo ý định:

~~~sql
SELECT order_id,
       LEAST(
           CAST(created_at AS DATETIME),
           CAST(deadline_at AS DATETIME)
       ) AS earlier_time,
       GREATEST(
           CAST(created_at AS DATETIME),
           CAST(deadline_at AS DATETIME)
       ) AS later_time
FROM orders;
~~~

Nếu hai cột đã có cùng kiểu và cùng ý nghĩa múi giờ, không cần CAST thừa. Nếu một cột là chuỗi ngày giờ, hãy chuyển đổi rõ ràng và kiểm tra dữ liệu sai định dạng trước khi so sánh.

Ví dụ giới hạn ngày hẹn trong một khoảng:

~~~sql
SELECT task_id,
       LEAST(
           GREATEST(due_date, DATE '2026-01-01'),
           DATE '2026-12-31'
       ) AS due_date_in_year
FROM tasks;
~~~

Biểu thức đưa ngày trước năm 2026 về 2026-01-01, ngày sau năm 2026 về 2026-12-31 và giữ nguyên ngày nằm trong khoảng. Nếu due_date là NULL, kết quả vẫn NULL.

Đừng trộn ngày giờ với chuỗi định dạng tùy ý hoặc số nguyên biểu diễn timestamp mà không chuyển đổi tường minh. Khi dữ liệu đi qua nhiều múi giờ, chuẩn hóa quy ước thời gian trước khi so sánh.

## 9. Ép kiểu tường minh để kiểm soát kết quả

Khi các đối số không cùng kiểu, dùng CAST() hoặc CONVERT() để thể hiện ý định:

~~~sql
SELECT LEAST(
           CAST(raw_value_a AS DECIMAL(14,3)),
           CAST(raw_value_b AS DECIMAL(14,3))
       ) AS minimum_measurement
FROM sensor_readings;
~~~

Một số kiểu CAST thường dùng:

~~~sql
CAST(value AS SIGNED)
CAST(value AS UNSIGNED)
CAST(value AS DECIMAL(12,2))
CAST(value AS CHAR)
CAST(value AS DATE)
CAST(value AS DATETIME)
~~~

Chọn kiểu đích đủ sức chứa dữ liệu. Ví dụ, CAST một số lớn sang SIGNED có thể làm thay đổi hoặc gây lỗi nếu vượt miền biểu diễn; CAST số tiền sang DECIMAL(12,2) có thể làm tròn hoặc mất phần lẻ vượt scale. Cần kiểm tra dữ liệu đầu vào và quy tắc làm tròn.

Nếu mục tiêu là so sánh số, đừng CAST sang CHAR. Nếu mục tiêu là so sánh văn bản theo collation, đừng để MySQL tự suy luận kiểu số từ một số đối số.

## 10. Dùng LEAST và GREATEST để giới hạn giá trị

### 10.1. Giới hạn số lượng

~~~sql
SELECT request_id,
       GREATEST(requested_quantity, 0) AS nonnegative_quantity
FROM order_requests;
~~~

Biểu thức giới hạn số lượng âm về 0. Nếu cột có thể NULL, kết quả vẫn NULL. Nếu NULL phải được hiểu là 0, có thể dùng:

~~~sql
SELECT request_id,
       GREATEST(COALESCE(requested_quantity, 0), 0)
           AS nonnegative_quantity
FROM order_requests;
~~~

Chỉ dùng COALESCE(..., 0) nếu nghiệp vụ xác định giá trị chưa có tương đương số lượng bằng 0.

### 10.2. Giới hạn khoảng thời gian

~~~sql
SELECT task_id,
       LEAST(
           GREATEST(actual_duration_minutes, 0),
           480
       ) AS capped_duration
FROM task_metrics;
~~~

Kết quả được giới hạn từ 0 đến 480 phút. Đây là quy tắc hiển thị hoặc tính toán; nếu dữ liệu gốc âm hoặc vượt 480 là bất thường cần điều tra, hãy giữ cột nguồn để kiểm toán thay vì chỉ lưu kết quả đã giới hạn.

### 10.3. Cập nhật giá trị có giới hạn

Có thể dùng biểu thức trong UPDATE:

~~~sql
UPDATE inventory
SET reserved_quantity =
    LEAST(
        GREATEST(reserved_quantity, 0),
        on_hand_quantity
    )
WHERE product_id = 100;
~~~

Ví dụ này giới hạn số lượng đặt trước từ 0 đến lượng hàng hiện có. Trước khi dùng trong hệ thống đồng thời, cần thiết kế transaction và khóa phù hợp để on_hand_quantity không thay đổi ngoài dự kiến giữa lúc kiểm tra và cập nhật. Hàm không tự bảo đảm quy tắc đồng thời hoặc tính toàn vẹn giữa nhiều hàng.

## 11. Phân biệt giá trị nhỏ nhất trong hàng và trong bảng

Giả sử bảng lưu ba lần đo trên mỗi thiết bị:

~~~sql
CREATE TABLE sensor_readings (
    reading_id BIGINT NOT NULL,
    sensor_id BIGINT NOT NULL,
    value_a DECIMAL(10,2) NULL,
    value_b DECIMAL(10,2) NULL,
    value_c DECIMAL(10,2) NULL,
    PRIMARY KEY (reading_id)
);
~~~

Chọn giá trị nhỏ nhất trong ba cột của từng lần đo:

~~~sql
SELECT reading_id,
       LEAST(value_a, value_b, value_c) AS row_minimum
FROM sensor_readings;
~~~

Nếu một trong ba cột NULL, row_minimum là NULL.

Tìm giá trị nhỏ nhất của value_a trên toàn bộ hàng:

~~~sql
SELECT MIN(value_a) AS column_minimum
FROM sensor_readings;
~~~

MIN(value_a) bỏ qua các hàng có value_a NULL. Đây là phép tổng hợp theo hàng của bảng, không phải so sánh các cột trong từng hàng.

Nếu cần tìm min của cả ba cột trên toàn bộ bảng và bỏ qua NULL:

~~~sql
SELECT MIN(value) AS overall_minimum,
       MAX(value) AS overall_maximum
FROM (
    SELECT value_a AS value FROM sensor_readings
    UNION ALL
    SELECT value_b FROM sensor_readings
    UNION ALL
    SELECT value_c FROM sensor_readings
) AS all_values;
~~~

Truy vấn chuyển các cột thành một tập giá trị rồi dùng MIN()/MAX(); các NULL được aggregate bỏ qua. Dùng UNION ALL để giữ mọi giá trị và tránh chi phí loại trùng không cần thiết.

## 12. Tương tác với điều kiện WHERE và index

Có thể dùng LEAST()/GREATEST() trong điều kiện:

~~~sql
SELECT product_id, price_a, price_b
FROM products
WHERE LEAST(price_a, price_b) < 100;
~~~

Điều kiện này dễ diễn đạt ý định nhưng việc đặt hàm lên cột có thể khiến MySQL khó tận dụng index thông thường trên từng cột như điều kiện so sánh trực tiếp. Nếu bảng lớn, hãy dùng EXPLAIN để kiểm tra kế hoạch.

Với hai cột không NULL và cùng kiểu số, biểu thức:

~~~sql
WHERE LEAST(price_a, price_b) < 100
~~~

có thể được viết tương đương về logic thành:

~~~sql
WHERE price_a < 100 OR price_b < 100
~~~

Tuy nhiên, khi có NULL, cần kiểm tra lại logic ba giá trị trước khi viết lại. LEAST() trả NULL nếu một trong hai cột NULL; còn điều kiện OR có thể TRUE nếu một cột nhỏ hơn 100 và cột kia NULL. Hai biểu thức không tương đương trong trường hợp có NULL.

Không tối ưu bằng cách biến đổi biểu thức mà chưa chứng minh tương đương trên toàn bộ miền dữ liệu, bao gồm NULL và kiểu dữ liệu. Dùng EXPLAIN và dữ liệu đại diện để đánh giá hiệu quả thực tế.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| LEAST(a, b) trả NULL dù một cột có giá trị | Đối số còn lại là NULL | Xác định NULL có phải được bỏ qua hay cần làm kết quả chưa xác định |
| GREATEST(2, '10') chọn 2 | Danh sách trộn số và chuỗi nên so sánh theo chuỗi | CAST các đối số về kiểu số phù hợp |
| Giá tiền so sánh không như mong đợi | Có đối số DOUBLE hoặc kiểu số bị ép không phù hợp | Dùng DECIMAL nhất quán và kiểm tra precision/scale |
| Thứ tự chuỗi khác giữa hai môi trường | Collation khác nhau hoặc collation không tương thích | Kiểm tra CHARSET/COLLATION và chỉ định collation phù hợp |
| Hàm không bỏ qua NULL như MIN | LEAST/GREATEST là scalar function và NULL lan truyền | Dùng CASE hoặc chuyển giá trị thành tập hàng rồi aggregate MIN/MAX |
| Kết quả ngày giờ không đúng kỳ vọng | Trộn DATE/DATETIME với chuỗi hoặc số | Chuẩn hóa kiểu bằng CAST/CONVERT và quy ước múi giờ |
| Truy vấn chậm sau khi thêm LEAST/GREATEST vào WHERE | Hàm được áp dụng lên cột khiến index khó được sử dụng | Đọc EXPLAIN; chỉ viết lại điều kiện sau khi kiểm tra tương đương với NULL |
| Thay NULL bằng sentinel tạo kết quả sai | Sentinel nằm trong miền giá trị hợp lệ | Dùng CASE hoặc aggregate bỏ qua NULL |

## 14. Bài thực hành: so sánh kiểu dữ liệu và NULL

Thực hiện trong database lab hoặc môi trường phát triển mà bạn được phép tạo bảng.

**Bước 1 — Tạo bảng mẫu.**

~~~sql
CREATE TABLE lab_measurements (
    measurement_id INT NOT NULL,
    value_a DECIMAL(10,2) NULL,
    value_b DECIMAL(10,2) NULL,
    value_c DECIMAL(10,2) NULL,
    label_a VARCHAR(20) NULL,
    label_b VARCHAR(20) NULL,
    PRIMARY KEY (measurement_id)
) ENGINE=InnoDB;
~~~

**Bước 2 — Nạp dữ liệu.**

~~~sql
INSERT INTO lab_measurements
    (measurement_id, value_a, value_b, value_c, label_a, label_b)
VALUES
    (1, 10.00, 20.00, 5.00, 'apple', 'Banana'),
    (2, 0.00, 8.00, 12.00, 'A', 'a'),
    (3, NULL, 7.00, 9.00, 'pear', 'orange'),
    (4, NULL, NULL, NULL, NULL, 'kiwi');
~~~

**Bước 3 — Tính min/max theo hàng.**

~~~sql
SELECT measurement_id,
       LEAST(value_a, value_b, value_c) AS row_min,
       GREATEST(value_a, value_b, value_c) AS row_max
FROM lab_measurements
ORDER BY measurement_id;
~~~

Quan sát hàng 3 và 4. Giải thích vì sao chỉ một đối số NULL cũng khiến kết quả LEAST/GREATEST là NULL.

**Bước 4 — So sánh với aggregate.**

~~~sql
SELECT MIN(value_a) AS min_value_a,
       MAX(value_a) AS max_value_a,
       COUNT(value_a) AS known_value_count
FROM lab_measurements;
~~~

Đối chiếu kết quả với LEAST(value_a, value_b, value_c) ở bước trước. Giải thích vì sao aggregate MIN/MAX bỏ qua NULL trong khi scalar LEAST/GREATEST không bỏ qua.

**Bước 5 — Thử kiểu dữ liệu hỗn hợp.**

~~~sql
SELECT GREATEST(2, '10') AS mixed_result,
       GREATEST(
           CAST(2 AS DECIMAL(10,0)),
           CAST('10' AS DECIMAL(10,0))
       ) AS numeric_result;
~~~

Giải thích khác biệt giữa so sánh chuỗi và so sánh số. Thử thêm các chuỗi '100', '20' để quan sát thứ tự từ điển.

**Bước 6 — Thử so sánh chuỗi theo collation.**

~~~sql
SELECT
    LEAST(
        _utf8mb4'An' COLLATE utf8mb4_0900_as_cs,
        _utf8mb4'an' COLLATE utf8mb4_0900_as_cs
    ) AS case_sensitive_result;
~~~

Nếu phiên bản không hỗ trợ collation ví dụ, dùng SHOW COLLATION để chọn collation tương ứng và ghi lại quy tắc hoa/thường, dấu.

**Bước 7 — Thử bỏ qua NULL.**

~~~sql
SELECT measurement_id,
       CASE
           WHEN value_a IS NULL THEN value_b
           WHEN value_b IS NULL THEN value_a
           ELSE LEAST(value_a, value_b)
       END AS least_non_null
FROM lab_measurements
ORDER BY measurement_id;
~~~

Kiểm tra hàng mà cả value_a và value_b đều NULL. Kết quả phải vẫn NULL.

**Bước 8 — Dọn bảng lab.**

~~~sql
DROP TABLE lab_measurements;
~~~

Chỉ xóa bảng lab do bạn vừa tạo sau khi hoàn thành quan sát.

**Kết quả cần đạt:** dùng được LEAST/GREATEST để so sánh nhiều giá trị trong cùng hàng; giải thích NULL propagation; phân biệt scalar với aggregate; nhận diện rủi ro khi trộn số và chuỗi; biết ép kiểu và collation tường minh.

## 15. Nguyên tắc cần ghi nhớ

- LEAST() trả đối số nhỏ nhất và GREATEST() trả đối số lớn nhất trong cùng một lần đánh giá; mỗi hàm cần ít nhất hai đối số.
- Đây là scalar function, khác với aggregate MIN()/MAX() quét giá trị trên nhiều hàng.
- Chỉ một đối số NULL cũng làm kết quả LEAST/GREATEST thành NULL.
- MIN()/MAX() bỏ qua NULL; không giả định LEAST/GREATEST có cùng hành vi.
- Các đối số số nguyên được so sánh như số nguyên; DOUBLE làm phép so sánh theo DOUBLE; DECIMAL được dùng khi không có DOUBLE nhưng có DECIMAL.
- Khi trộn số và chuỗi, MySQL so sánh như chuỗi; CAST tường minh nếu muốn so sánh số học.
- Collation quyết định thứ tự so sánh chuỗi; chuẩn hóa charset/collation nếu các đối số không tương thích.
- Dùng CASE hoặc aggregate MIN/MAX trên tập hàng nếu cần bỏ qua đối số NULL.
- Không thay NULL bằng sentinel hoặc 0 nếu giá trị đó có thể mang ý nghĩa nghiệp vụ.
- Kiểm tra logic NULL trước khi viết lại điều kiện có LEAST/GREATEST để tối ưu index.
- Dùng DECIMAL cho giá trị tài chính cần so sánh thập phân chính xác; tránh để DOUBLE thay đổi quy tắc tính toán.

Khi hiểu quy tắc NULL, kiểu dữ liệu và collation, bạn có thể dùng LEAST/GREATEST để giới hạn và so sánh giá trị mà không tạo ra kết quả sai do ép kiểu ngầm. Hãy làm rõ ý nghĩa dữ liệu thiếu và chuẩn hóa kiểu của các đối số ngay tại biểu thức SQL.
