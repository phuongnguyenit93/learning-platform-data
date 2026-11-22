# COUNT(*), COUNT(cột), SUM, AVG, MIN và MAX

Các hàm tổng hợp (aggregate functions) biến nhiều hàng thành một giá trị hoặc một giá trị cho mỗi nhóm. Chúng thường được dùng trong báo cáo doanh thu, thống kê đơn hàng, kiểm tra tồn kho, phân tích dữ liệu và các truy vấn nghiệp vụ. Dùng đúng hàm tổng hợp đòi hỏi hiểu rõ hàng nào được tính, `NULL` được xử lý ra sao và kết quả thay đổi thế nào khi tập đầu vào rỗng.

MySQL cung cấp các hàm cơ bản `COUNT()`, `SUM()`, `AVG()`, `MIN()` và `MAX()`. `COUNT(*)` đếm hàng, `COUNT(cột)` đếm giá trị không `NULL`, `SUM()` tính tổng, `AVG()` tính trung bình, còn `MIN()` và `MAX()` tìm giá trị nhỏ nhất/lớn nhất. Những hàm này thường đi cùng `GROUP BY` để tạo kết quả theo khách hàng, sản phẩm, trạng thái hoặc khoảng thời gian.

Bài học này thuộc module `DATABASE_MYSQL`, nơi bạn thực hành thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và tối ưu truy vấn. Mục tiêu là viết phép tổng hợp có ngữ nghĩa chính xác, xử lý được dữ liệu thiếu và tránh đếm/tính tổng sai do join hoặc dữ liệu trùng.

Sau bài học, bạn có thể:

- Phân biệt `COUNT(*)`, `COUNT(cột)` và `COUNT(DISTINCT cột)`.
- Dùng `SUM`, `AVG`, `MIN`, `MAX` trên dữ liệu số và hiểu kết quả với `NULL`.
- Dự đoán kết quả khi không có hàng hoặc tất cả giá trị đầu vào đều `NULL`.
- Nhóm dữ liệu bằng `GROUP BY` và lọc nhóm bằng `HAVING`.
- Viết conditional aggregation để tính nhiều chỉ số trong một lần quét.
- Tránh lỗi nhân bản hàng khi tổng hợp qua nhiều quan hệ một-nhiều.
- Hiểu kiểu kết quả, ảnh hưởng của collation và giới hạn khi tổng hợp temporal values.
- Kiểm tra truy vấn tổng hợp bằng dữ liệu mẫu và `EXPLAIN`.

## 1. Aggregate function hoạt động như thế nào?

Một aggregate function nhận một tập giá trị và tính ra một kết quả. Nếu không có `GROUP BY`, MySQL tổng hợp toàn bộ tập hàng thỏa `FROM`/`WHERE` thành một kết quả. Nếu có `GROUP BY`, MySQL chia hàng thành các nhóm rồi tính riêng từng nhóm.

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM sales
WHERE status = 'PAID';
```

Truy vấn này trả một hàng tổng hợp cho toàn bộ các giao dịch `PAID`. Khi thêm `GROUP BY customer_id`, nó trả một hàng cho mỗi khách hàng có ít nhất một hàng đầu vào sau điều kiện `WHERE`.

Thứ tự xử lý logic có thể hình dung như sau:

```text
FROM / JOIN
     |
     v
WHERE (lọc hàng đầu vào)
     |
     v
GROUP BY (tạo nhóm, nếu có)
     |
     v
Aggregate functions
     |
     v
HAVING (lọc nhóm)
     |
     v
SELECT (chiếu kết quả)
     |
     v
ORDER BY / LIMIT
```

Đây là mô hình tư duy cho ngữ nghĩa truy vấn. Optimizer có thể thực thi theo kế hoạch khác, nhưng kết quả phải tuân theo quy tắc SQL.

## 2. Tạo dữ liệu mẫu để quan sát

Ví dụ dùng hai bảng tạm: khách hàng và giao dịch bán hàng. Fixture có giá trị bình thường, `NULL`, số tiền bằng 0, hai giao dịch có cùng số tiền và một khách hàng chưa có giao dịch.

Chạy toàn bộ ví dụ trong cùng một session MySQL:

```sql
DROP TEMPORARY TABLE IF EXISTS sales;
DROP TEMPORARY TABLE IF EXISTS customers;

CREATE TEMPORARY TABLE customers (
    customer_id INT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TEMPORARY TABLE sales (
    sale_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(10, 2) NULL,
    quantity INT UNSIGNED NULL,
    PRIMARY KEY (sale_id),
    KEY idx_sales_customer_status (customer_id, status)
) ENGINE = InnoDB;

INSERT INTO customers (customer_id, customer_name) VALUES
(1, 'An'),
(2, 'Bình'),
(3, 'Chi'),
(4, 'Dũng');

INSERT INTO sales (sale_id, customer_id, status, amount, quantity) VALUES
(101, 1, 'PAID',    100.00, 2),
(102, 1, 'PAID',      NULL, 1),
(103, 1, 'PENDING',  50.00, 1),
(104, 2, 'PAID',    200.00, 3),
(105, 2, 'PAID',    200.00, 2),
(106, 3, 'PAID',      0.00, 0);
```

Ý nghĩa dữ liệu:

| Dữ liệu | Mục đích kiểm tra |
| --- | --- |
| Sale 101 | Giá trị số bình thường |
| Sale 102 | `amount` là `NULL`, nhưng hàng vẫn tồn tại |
| Sale 103 | Trạng thái không phải `PAID` |
| Sale 104 và 105 | Hai hàng khác nhau có cùng `amount = 200.00` |
| Sale 106 | Giá trị bằng 0, khác với `NULL` |
| Customer 4 | Không có hàng ở bảng `sales` |

Fixture này giúp thấy rõ aggregate bỏ qua `NULL`, đếm hàng khác đếm giá trị và `DISTINCT` có thể làm thay đổi ý nghĩa phép tính.

## 3. COUNT(*) — đếm số hàng

`COUNT(*)` đếm số hàng trong tập đầu vào, bất kể các cột của hàng đó có giá trị `NULL` hay không.

```sql
SELECT COUNT(*) AS total_sales
FROM sales;
```

Expected result là `6`, vì bảng có sáu hàng.

Đếm các giao dịch đã thanh toán:

```sql
SELECT COUNT(*) AS paid_sales
FROM sales
WHERE status = 'PAID';
```

Expected result là `5`. Hàng có `amount = NULL` vẫn được tính vì `COUNT(*)` chỉ quan tâm số hàng, không quan tâm giá trị từng cột.

`COUNT(*)` cũng đếm hàng sau phép join. Đây là điểm quan trọng: nếu một hàng cha được ghép với ba hàng con, hàng cha xuất hiện ba lần trong tập kết quả join và `COUNT(*)` có thể đếm ba lần. Muốn đếm thực thể cha, cần chọn đúng khóa hoặc cấu trúc truy vấn phù hợp.

## 4. COUNT(cột) — đếm giá trị không NULL

`COUNT(expr)` đếm số hàng mà biểu thức `expr` trả về giá trị khác `NULL`. Nó không đếm giá trị `NULL`.

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(quantity) AS quantity_count
FROM sales
WHERE status = 'PAID';
```

Expected result:

| row_count | amount_count | quantity_count |
| ---: | ---: | ---: |
| 5 | 4 | 5 |

Có năm giao dịch `PAID`, nhưng chỉ bốn giao dịch có `amount` khác `NULL`. `quantity` của cả năm giao dịch đều có giá trị, kể cả số 0.

Điểm cần nhớ:

- `COUNT(amount)` vẫn đếm giá trị 0, chuỗi rỗng hoặc `FALSE` nếu biểu thức đó không phải `NULL`.
- `COUNT(*)` đếm hàng bất kể mọi cột đều `NULL` hay không.
- `COUNT(1)` cũng thường đếm tất cả hàng như `COUNT(*)` vì biểu thức literal `1` không `NULL`; để thể hiện ý nghĩa rõ ràng, ưu tiên `COUNT(*)` khi mục tiêu là đếm hàng.
- `COUNT(nullable_column)` phù hợp khi muốn biết có bao nhiêu hàng thực sự có giá trị ở cột đó.

## 5. COUNT(DISTINCT ...) — đếm giá trị khác nhau

`COUNT(DISTINCT expr)` đếm số giá trị khác nhau và bỏ qua `NULL`.

```sql
SELECT
    COUNT(*) AS paid_rows,
    COUNT(amount) AS non_null_amounts,
    COUNT(DISTINCT amount) AS distinct_amounts
FROM sales
WHERE status = 'PAID';
```

Expected result là `5`, `4`, `3`:

- Có năm hàng `PAID`.
- Có bốn giá trị amount khác `NULL`.
- Các amount khác nhau là `100.00`, `200.00` và `0.00`.

MySQL cũng hỗ trợ đếm tổ hợp nhiều biểu thức:

```sql
SELECT COUNT(DISTINCT customer_id, status) AS distinct_customer_status_pairs
FROM sales;
```

Với dạng nhiều biểu thức, MySQL đếm các tổ hợp giá trị khác nhau mà tất cả biểu thức trong tổ hợp đều không `NULL`.

Với biểu thức kiểu chuỗi, khái niệm “khác nhau” còn chịu ảnh hưởng của collation. Nếu collation không phân biệt hoa/thường hoặc dấu, một số chuỗi có thể được xem là tương đương khi `COUNT(DISTINCT text_column)` chạy. Nếu nghiệp vụ cần phân biệt byte hoặc chữ hoa/thường, hãy chọn collation phù hợp và kiểm thử dữ liệu đại diện.

### 5.1. DISTINCT không đồng nghĩa loại hàng trùng

Hai giao dịch 104 và 105 là hai giao dịch riêng biệt dù có cùng amount. Nếu tính tổng:

```sql
SELECT
    SUM(amount) AS total_amount,
    SUM(DISTINCT amount) AS distinct_amount_total
FROM sales
WHERE customer_id = 2
  AND status = 'PAID';
```

Kết quả là:

| total_amount | distinct_amount_total |
| ---: | ---: |
| 400.00 | 200.00 |

`SUM(DISTINCT amount)` chỉ cộng mỗi giá trị amount một lần. Nó không phải cách sửa lỗi join nhân bản hàng nếu mỗi hàng có ý nghĩa nghiệp vụ riêng. Hãy xác định bạn muốn tổng các giao dịch hay tổng các mức giá duy nhất.

## 6. SUM() — tính tổng

`SUM(expr)` cộng các giá trị khác `NULL` trong tập đầu vào. Nếu không có giá trị nào để cộng (tập đầu vào rỗng hoặc tất cả giá trị đều `NULL`), kết quả là `NULL`.

```sql
SELECT
    SUM(amount) AS paid_revenue,
    SUM(quantity) AS paid_quantity
FROM sales
WHERE status = 'PAID';
```

Expected result:

| paid_revenue | paid_quantity |
| ---: | ---: |
| 500.00 | 8 |

Tổng amount là `100 + 200 + 200 + 0 = 500`. Giá trị `NULL` của sale 102 bị bỏ qua. Quantity là `2 + 1 + 3 + 2 + 0 = 8`.

### 6.1. SUM và NULL

Ba trường hợp sau cho kết quả khác nhau:

```sql
-- Không có hàng nào khớp
SELECT SUM(amount) AS result
FROM sales
WHERE customer_id = 999;

-- Có hàng, nhưng mọi amount đều NULL
SELECT SUM(amount) AS result
FROM sales
WHERE customer_id = 1
  AND sale_id = 102;

-- Có hàng với amount bằng 0
SELECT SUM(amount) AS result
FROM sales
WHERE customer_id = 3;
```

Kết quả lần lượt là `NULL`, `NULL` và `0.00`. Hai trường hợp đầu có tổng không xác định vì không có giá trị số để cộng; trường hợp cuối có một giá trị số thực sự bằng 0.

Nếu báo cáo muốn hiển thị 0 thay cho `NULL`, dùng `COALESCE()`:

```sql
SELECT COALESCE(SUM(amount), 0.00) AS paid_revenue
FROM sales
WHERE customer_id = 999;
```

Đây là quy tắc hiển thị/nghiệp vụ. Không nên thay mọi `NULL` thành 0 một cách máy móc nếu hệ thống cần phân biệt “không có dữ liệu” với “tổng thực bằng 0”.

## 7. AVG() — tính trung bình

`AVG(expr)` tính tổng các giá trị khác `NULL` chia cho số giá trị khác `NULL`. Nó không chia cho tổng số hàng nếu có giá trị `NULL`.

```sql
SELECT AVG(amount) AS average_paid_amount
FROM sales
WHERE status = 'PAID';
```

Có bốn amount khác `NULL`: 100, 200, 200 và 0. Kết quả là `500 / 4 = 125.00`.

So sánh:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS amount_sum,
    AVG(amount) AS amount_avg,
    SUM(amount) / COUNT(*) AS wrong_average_if_null_means_missing
FROM sales
WHERE status = 'PAID';
```

`AVG(amount)` chia cho 4, còn `SUM(amount) / COUNT(*)` chia cho 5 và cho kết quả 100.00. Nếu `NULL` có nghĩa là chưa có dữ liệu, cách chia cho `COUNT(*)` làm sai trung bình. Hãy xác định mẫu số theo định nghĩa nghiệp vụ.

`AVG(DISTINCT amount)` tính trung bình trên các giá trị khác nhau. Với khách hàng 2, `AVG(amount)` là 200.00 và `AVG(DISTINCT amount)` cũng là 200.00; với dữ liệu có nhiều mức giá, hai kết quả có thể khác nhau đáng kể.

## 8. MIN() và MAX() — tìm giá trị nhỏ nhất/lớn nhất

`MIN(expr)` trả giá trị nhỏ nhất và `MAX(expr)` trả giá trị lớn nhất trong tập giá trị khác `NULL`. Nếu không có giá trị khác `NULL`, cả hai trả `NULL`.

```sql
SELECT
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM sales
WHERE status = 'PAID';
```

Expected result là `0.00` và `200.00`. `NULL` không tham gia so sánh; số 0 vẫn là một giá trị hợp lệ.

MIN/MAX không chỉ dùng cho số:

```sql
SELECT
    MIN(customer_name) AS first_name_by_collation,
    MAX(customer_name) AS last_name_by_collation
FROM customers;
```

Với chuỗi, thứ tự so sánh phụ thuộc kiểu dữ liệu và collation. Collation không phân biệt hoa/thường hoặc dấu có thể coi một số chuỗi là tương đương theo quy tắc so sánh. Không hiểu `MIN(text_column)` là “chuỗi xuất hiện đầu tiên theo thời gian” hoặc “tên đầu tiên theo từ điển tiếng Việt” nếu chưa xác định collation.

Đối với `ENUM` và `SET`, `MIN()`/`MAX()` so sánh giá trị chuỗi thay vì vị trí khai báo nội bộ. Nếu cần thứ tự nghiệp vụ, hãy viết `CASE` hoặc dùng cột thứ tự rõ ràng.

## 9. Kết quả khi tập đầu vào rỗng hoặc NULL

Bảng sau tóm tắt hành vi quan trọng:

| Hàm | Tập đầu vào không có hàng | Có hàng nhưng tất cả expr là NULL |
| --- | --- | --- |
| `COUNT(*)` | `0` | Đếm số hàng |
| `COUNT(expr)` | `0` | `0` |
| `COUNT(DISTINCT expr)` | `0` | `0` |
| `SUM(expr)` | `NULL` | `NULL` |
| `AVG(expr)` | `NULL` | `NULL` |
| `MIN(expr)` | `NULL` | `NULL` |
| `MAX(expr)` | `NULL` | `NULL` |

Ví dụ tập rỗng:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS amount_sum,
    AVG(amount) AS amount_avg,
    MIN(amount) AS min_amount,
    MAX(amount) AS max_amount
FROM sales
WHERE customer_id = 999;
```

Truy vấn aggregate không có `GROUP BY` vẫn trả đúng một hàng kết quả. Các hàm COUNT trả 0, các hàm tổng hợp còn lại trả `NULL`.

Nếu thêm `GROUP BY customer_id` vào cùng truy vấn, tập đầu vào rỗng tạo ra 0 nhóm nên kết quả không có hàng. Đây là khác biệt quan trọng khi API cần trả một summary rỗng hay một danh sách nhóm rỗng.

## 10. GROUP BY — tổng hợp theo nhóm

`GROUP BY` chia các hàng thành nhóm có cùng giá trị ở các biểu thức nhóm. Các hàm aggregate được tính riêng cho từng nhóm.

```sql
SELECT
    customer_id,
    COUNT(*) AS paid_sale_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS paid_total,
    AVG(amount) AS average_amount,
    MIN(amount) AS min_amount,
    MAX(amount) AS max_amount
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id;
```

Expected result:

| customer_id | paid_sale_count | amount_count | paid_total | average_amount | min_amount | max_amount |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 1 | 100.00 | 100.00 | 100.00 | 100.00 |
| 2 | 2 | 2 | 400.00 | 200.00 | 200.00 | 200.00 |
| 3 | 1 | 1 | 0.00 | 0.00 | 0.00 | 0.00 |

Khách hàng 4 không xuất hiện vì không có hàng `sales` để tạo nhóm. Muốn hiển thị cả khách hàng không có giao dịch, cần bắt đầu từ bảng `customers` và dùng `LEFT JOIN`.

### 10.1. GROUP BY với LEFT JOIN

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(s.sale_id) AS paid_sale_count,
    COUNT(s.amount) AS amount_count,
    SUM(s.amount) AS paid_total,
    AVG(s.amount) AS average_amount
FROM customers AS c
LEFT JOIN sales AS s
    ON s.customer_id = c.customer_id
   AND s.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Kết quả có cả khách hàng 4. Với khách hàng này, `COUNT(s.sale_id) = 0`, `COUNT(s.amount) = 0`, còn `SUM` và `AVG` là `NULL`.

Với fixture hiện tại, kết quả mong đợi:

| customer_id | customer_name | paid_sale_count | amount_count | paid_total | average_amount |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | An | 2 | 1 | 100.00 | 100.00 |
| 2 | Bình | 2 | 2 | 400.00 | 200.00 |
| 3 | Chi | 1 | 1 | 0.00 | 0.00 |
| 4 | Dũng | 0 | 0 | `NULL` | `NULL` |

Điều kiện `s.status = 'PAID'` được đặt trong `ON` để không loại khách hàng không có đơn đã thanh toán. Nếu đưa điều kiện đó xuống `WHERE`, hàng được tạo bởi phần `LEFT JOIN` có `s.status = NULL` sẽ bị loại, làm mất khách hàng 4.

### 10.2. COUNT(*) và COUNT khóa bảng con sau LEFT JOIN

Với khách hàng không có giao dịch, `LEFT JOIN` vẫn tạo một hàng kết quả chứa cột bên trái và các cột bên phải là `NULL`:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(s.sale_id) AS sale_rows
FROM customers AS c
LEFT JOIN sales AS s
    ON s.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Khách hàng 4 có `joined_rows = 1`, nhưng `sale_rows = 0`. Khi đếm bản ghi bên phải của outer join, dùng cột khóa không nullable như `sale_id`.

### 10.3. NULL trong GROUP BY

Các hàng có giá trị `NULL` ở biểu thức nhóm được xếp vào cùng một nhóm `NULL`. Điều này khác với phép so sánh `NULL = NULL`, vốn không trả `TRUE`; quy tắc nhóm coi các giá trị NULL là cùng nhóm để tổng hợp.

```sql
SELECT
    region,
    COUNT(*) AS row_count
FROM some_table
GROUP BY region;
```

Nếu `region` có nhiều hàng NULL, kết quả có một nhóm với `region = NULL`. Khi hiển thị, có thể dùng `COALESCE(region, 'Chưa phân loại')`, nhưng hãy đảm bảo nhãn thay thế không gây nhầm với một giá trị region thực tế.

## 11. WHERE và HAVING

`WHERE` lọc hàng trước khi nhóm và tính aggregate. `HAVING` lọc kết quả nhóm sau khi aggregate được tính.

Ví dụ: tính tổng giao dịch `PAID` của từng khách hàng, chỉ hiển thị khách hàng có tổng lớn hơn 100:

```sql
SELECT
    customer_id,
    SUM(amount) AS paid_total
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) > 100
ORDER BY paid_total DESC;
```

`WHERE status = 'PAID'` lọc giao dịch đầu vào; `HAVING SUM(amount) > 100` lọc nhóm sau khi tổng được tính. MySQL cho phép tham chiếu alias select list trong `HAVING`:

```sql
HAVING paid_total > 100
```

Tuy nhiên, để truy vấn rõ ràng và dễ chuyển giữa hệ quản trị, có thể lặp lại biểu thức aggregate trong `HAVING`. Không dùng aggregate trực tiếp trong `WHERE`:

```sql
-- Sai: WHERE được xử lý trước khi nhóm
SELECT customer_id, SUM(amount)
FROM sales
WHERE SUM(amount) > 100
GROUP BY customer_id;
```

Hãy chuyển điều kiện nhóm sang `HAVING`.

## 12. Conditional aggregation — nhiều chỉ số trong một truy vấn

Conditional aggregation dùng `CASE` bên trong aggregate để tính nhiều nhóm chỉ số trên cùng tập hàng.

Ví dụ thống kê tổng số giao dịch theo trạng thái:

```sql
SELECT
    customer_id,
    COUNT(*) AS all_sales,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_sales,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_sales,
    SUM(CASE WHEN status = 'PAID' THEN amount END) AS paid_amount,
    SUM(CASE WHEN status = 'PENDING' THEN amount END) AS pending_amount
FROM sales
GROUP BY customer_id
ORDER BY customer_id;
```

`CASE` không có `ELSE` trong biểu thức tổng tiền sẽ trả `NULL` cho hàng không thuộc trạng thái đó. `SUM()` bỏ qua các giá trị NULL, nhờ vậy nhóm không có giao dịch thuộc trạng thái tương ứng sẽ có tổng `NULL`. Nếu muốn tổng hiển thị 0 khi không có giao dịch, dùng `COALESCE()` ở lớp ngoài:

```sql
COALESCE(SUM(CASE WHEN status = 'REFUNDED' THEN amount END), 0.00)
    AS refunded_amount
```

Đếm giao dịch có điều kiện cũng có thể viết bằng `COUNT(CASE ...)`:

```sql
SELECT
    customer_id,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_count
FROM sales
GROUP BY customer_id;
```

`COUNT()` chỉ đếm biểu thức khác NULL; các nhánh không khớp không có `ELSE`, do đó trả NULL và không được đếm.

## 13. Kiểu dữ liệu của kết quả aggregate

Kiểu kết quả có ảnh hưởng tới JDBC, DTO và phép tính tiếp theo trong SQL.

| Hàm | Đặc điểm kiểu kết quả trong MySQL |
| --- | --- |
| `COUNT()` | Trả số nguyên kiểu `BIGINT` |
| `SUM()` với đối số exact-value (integer/DECIMAL) | Trả `DECIMAL` |
| `SUM()` với đối số approximate-value (`FLOAT`/`DOUBLE`) | Trả `DOUBLE` |
| `AVG()` với đối số exact-value | Trả `DECIMAL` |
| `AVG()` với đối số approximate-value | Trả `DOUBLE` |
| `MIN()` / `MAX()` | Trả giá trị cùng kiểu với biểu thức đầu vào |

Ví dụ, nếu `amount` là `DECIMAL(10,2)`, nên đọc kết quả `SUM(amount)` và `AVG(amount)` bằng Java `BigDecimal`, không chuyển sang `double` nếu cần độ chính xác thập phân. `COUNT()` thường được đọc bằng `long`/`Long` trong JDBC.

```java
long saleCount = resultSet.getLong("sale_count");
BigDecimal total = resultSet.getBigDecimal("total_amount");
BigDecimal average = resultSet.getBigDecimal("average_amount");
```

Nếu kết quả aggregate có thể là NULL, ví dụ `SUM()` trên tập rỗng, kiểm tra null hoặc dùng wrapper/kiểu tham chiếu. Không đọc một giá trị có thể NULL bằng primitive rồi coi 0 là giá trị thật.

## 14. Tổng hợp dữ liệu temporal

`MIN()` và `MAX()` có thể hữu ích với `DATE`, `DATETIME` và `TIMESTAMP`, ví dụ tìm giao dịch đầu tiên hoặc gần nhất:

```sql
SELECT
    MIN(placed_at) AS first_sale_at,
    MAX(placed_at) AS latest_sale_at
FROM sales_history;
```

Không dùng `SUM()` hoặc `AVG()` trực tiếp trên kiểu `TIME`, `DATE` hoặc `DATETIME` với kỳ vọng tính toán theo đơn vị thời gian. MySQL có thể chuyển temporal value sang dạng số, làm mất phần sau ký tự không phải số đầu tiên và cho kết quả không như ý.

Nếu cần tổng thời lượng `TIME`, chuyển sang giây trước:

```sql
SELECT SEC_TO_TIME(SUM(TIME_TO_SEC(duration))) AS total_duration
FROM task_runs;
```

Nếu cần trung bình thời lượng:

```sql
SELECT SEC_TO_TIME(AVG(TIME_TO_SEC(duration))) AS average_duration
FROM task_runs;
```

`TIME_TO_SEC()` trả số giây (có thể có phần thập phân nếu TIME có fractional seconds). `SEC_TO_TIME()` chuyển số giây về TIME. Cần kiểm tra giới hạn của kiểu TIME nếu tổng thời lượng lớn hoặc có thể vượt phạm vi biểu diễn.

## 15. Tránh nhân bản dữ liệu khi JOIN trước khi aggregate

Một lỗi phổ biến là join hai bảng con một-nhiều rồi tính tổng. Nếu một đơn có 2 dòng hàng và 3 lần thanh toán, phép join trực tiếp có thể tạo 6 hàng. `SUM(item_amount)` và `SUM(payment_amount)` khi đó bị nhân lên.

Mô hình minh họa:

```text
orders (1)
   |             |
   | 1-to-many   | 1-to-many
   v             v
order_items    payments
   2 rows        3 rows
        \        /
         JOIN result
            6 rows
```

Hãy tổng hợp mỗi bảng con về một hàng cho mỗi đơn trước khi join:

```sql
SELECT
    o.order_id,
    item_totals.items_total,
    payment_totals.payments_total
FROM orders AS o
LEFT JOIN (
    SELECT order_id, SUM(quantity * unit_price) AS items_total
    FROM order_items
    GROUP BY order_id
) AS item_totals
    ON item_totals.order_id = o.order_id
LEFT JOIN (
    SELECT order_id, SUM(amount) AS payments_total
    FROM payments
    GROUP BY order_id
) AS payment_totals
    ON payment_totals.order_id = o.order_id;
```

Mỗi derived table chỉ có tối đa một hàng cho mỗi `order_id`, nên join không nhân chéo các hàng con. Đây là ví dụ cấu trúc; các bảng `orders`, `order_items` và `payments` cần được tạo theo schema của bài lab riêng.

Không dùng `SUM(DISTINCT amount)` như một cách chữa chung cho join fan-out. Hai khoản tiền hợp lệ có thể bằng nhau nhưng vẫn phải được cộng hai lần. Hãy sửa cardinality của join hoặc aggregate trước khi ghép.

## 16. Index và hiệu năng của truy vấn aggregate

Aggregate phải xử lý các hàng đầu vào. Index phù hợp có thể giảm số hàng phải đọc hoặc giúp truy cập theo thứ tự nhóm, nhưng không có một index tối ưu cho mọi truy vấn tổng hợp.

Ví dụ truy vấn:

```sql
SELECT customer_id, SUM(amount)
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id;
```

Với truy vấn này, index bắt đầu bằng `status` và tiếp theo là `customer_id` có thể hữu ích khi lọc trạng thái trước rồi nhóm theo khách hàng. Một covering index có thêm `amount` có thể giảm việc đọc hàng từ clustered index, nhưng sẽ lớn hơn và làm tăng chi phí ghi.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT customer_id, SUM(amount)
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id;
```

Quan sát `type`, `key`, `rows`, `filtered` và `Extra`. Tùy truy vấn, MySQL có thể dùng index hoặc tạo temporary table/filesort để nhóm và sắp xếp. Không suy ra truy vấn chậm chỉ vì thấy `Using temporary`; cần đo với dữ liệu đại diện.

Các nguyên tắc:

- Đẩy điều kiện lọc hàng không liên quan vào `WHERE` trước khi nhóm.
- Chỉ chọn các cột thực sự cần thiết.
- Chọn index dựa trên kết hợp điều kiện lọc, join và nhóm.
- Cân nhắc kích thước covering index so với lợi ích giảm table lookup.
- Kiểm tra cardinality và thống kê; dữ liệu fixture nhỏ không đại diện cho phân bố production.
- Dùng `EXPLAIN ANALYZE` khi chấp nhận truy vấn được thực thi thật.

## 17. Bài tập thực hành

1. Chạy fixture ở phần 2. Tính `COUNT(*)`, `COUNT(amount)`, `SUM(amount)`, `AVG(amount)`, `MIN(amount)` và `MAX(amount)` cho trạng thái `PAID`.
2. So sánh `COUNT(*)` với `COUNT(amount)` và giải thích ảnh hưởng của sale 102.
3. So sánh `SUM(amount)` với `SUM(DISTINCT amount)` cho khách hàng 2.
4. Chạy aggregate trên tập rỗng và trên tập chỉ có amount NULL. Ghi kết quả từng hàm.
5. Thêm `GROUP BY customer_id`, sau đó đổi thành `LEFT JOIN` từ customers để giữ khách hàng chưa có giao dịch.
6. Thử `COUNT(*)` và `COUNT(s.sale_id)` sau `LEFT JOIN`; giải thích vì sao kết quả khác ở khách hàng 4.
7. Viết conditional aggregation để tính số giao dịch `PAID`, `PENDING` và tổng tiền của từng trạng thái.
8. Tạo dữ liệu có hai bảng con một-nhiều rồi chứng minh join trực tiếp làm nhân bản hàng và sai tổng. Sửa bằng cách aggregate từng bảng con trước.
9. Tìm giao dịch sớm nhất/muộn nhất bằng `MIN()` và `MAX()`. Thử tổng hợp duration qua `TIME_TO_SEC()` và `SEC_TO_TIME()`.
10. Chạy `EXPLAIN` cho truy vấn aggregate theo status và customer; thử một index tổng hợp rồi so sánh kế hoạch với dữ liệu đủ lớn.

## 18. Checklist trước khi đưa aggregate vào production

- [ ] Đã xác định rõ đơn vị đếm: hàng, giá trị không NULL, thực thể hay giá trị duy nhất.
- [ ] Đã chọn `COUNT(*)`, `COUNT(cột)` hoặc `COUNT(DISTINCT ...)` theo đúng yêu cầu.
- [ ] Đã xác định cách xử lý `NULL`, 0 và tập đầu vào rỗng.
- [ ] Đã xác định `SUM(DISTINCT)`/`AVG(DISTINCT)` có đúng ý nghĩa nghiệp vụ hay không.
- [ ] `WHERE` lọc hàng trước aggregate và `HAVING` lọc nhóm sau aggregate.
- [ ] `GROUP BY` không phụ thuộc vào giá trị không xác định; tương thích `ONLY_FULL_GROUP_BY`.
- [ ] Outer join đếm khóa không nullable của bảng con thay vì `COUNT(*)` khi cần đếm hàng con.
- [ ] Không có join fan-out làm nhân bản giá trị trước khi tính tổng.
- [ ] Kiểu kết quả aggregate tương thích với JDBC và domain model.
- [ ] Temporal values được chuyển sang đơn vị số trước khi `SUM`/`AVG` thời lượng.
- [ ] Index và kế hoạch thực thi được kiểm tra bằng dữ liệu đại diện.

## 19. Tiêu chí hoàn thành

Bạn hoàn thành bài khi giải thích được sự khác nhau giữa `COUNT(*)`, `COUNT(cột)` và `COUNT(DISTINCT ...)`, dự đoán chính xác hành vi của `SUM`, `AVG`, `MIN`, `MAX` với `NULL` và tập rỗng, viết được truy vấn `GROUP BY`/`HAVING` và conditional aggregation, tránh lỗi đếm sai sau `LEFT JOIN` hoặc join fan-out, đồng thời chọn được cách kiểm tra index và kiểu kết quả phù hợp cho ứng dụng.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Aggregate Functions](https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html)
- [MySQL 8.4 Reference Manual — GROUP BY Modifiers](https://dev.mysql.com/doc/refman/8.4/en/group-by-modifiers.html)
- [MySQL 8.4 Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
