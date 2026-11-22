# Merge/materialization của CTE và kiểm tra kế hoạch thực thi

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Common Table Expression (CTE) giúp đặt tên cho một truy vấn con để câu SQL dễ đọc, dễ chia thành bước và có thể tái sử dụng trong cùng một câu lệnh. Tuy nhiên, CTE không mặc định luôn được lưu vào bảng tạm. MySQL có thể **merge** CTE vào truy vấn sử dụng nó hoặc **materialize** kết quả thành một bảng trung gian.

Hai chiến lược có chi phí và cơ hội tối ưu khác nhau. Merge có thể giúp optimizer đẩy điều kiện xuống bảng gốc, kết hợp JOIN và chọn index trực tiếp. Materialization tạo kết quả trung gian có thể được đọc lại, đặc biệt hữu ích khi CTE được tham chiếu nhiều lần hoặc có phép tổng hợp. Muốn tối ưu đúng, cần đọc kế hoạch thực thi thay vì suy luận từ cú pháp WITH.

## 1. CTE trong MySQL

CTE là một tập kết quả có tên, được khai báo bằng mệnh đề WITH và chỉ có phạm vi trong một câu SQL:

~~~sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT order_id, customer_id, total_amount
FROM paid_orders;
~~~

paid_orders là tên CTE. Truy vấn bên trong dấu ngoặc định nghĩa dữ liệu; outer query tham chiếu tên đó như một nguồn hàng. CTE có thể giúp chia truy vấn phức tạp thành các bước có tên rõ nghĩa.

MySQL hỗ trợ CTE không đệ quy và CTE đệ quy từ dòng MySQL 8.0. CTE không đệ quy thường được optimizer xử lý theo các chiến lược tương tự derived table và view. CTE đệ quy có quy tắc thực thi riêng và luôn được materialize.

### 1.1. CTE không phải bảng lưu lâu dài

CTE chỉ tồn tại trong phạm vi câu lệnh:

~~~sql
WITH order_summary AS (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
)
SELECT *
FROM order_summary;
~~~

Sau khi câu lệnh kết thúc, tên order_summary không còn dùng được trong câu SQL tiếp theo. CTE không tự tạo bảng vật lý, không thay thế bảng tạm do người dùng quản lý và không lưu kết quả qua nhiều statement.

### 1.2. CTE và derived table

Hai cách viết có thể diễn đạt cùng một nguồn dữ liệu:

~~~sql
-- Dùng CTE
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT customer_id, SUM(total_amount) AS paid_total
FROM paid_orders
GROUP BY customer_id;

-- Dùng derived table
SELECT customer_id, SUM(total_amount) AS paid_total
FROM (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'PAID'
) AS paid_orders
GROUP BY customer_id;
~~~

CTE đặt tên bước truy vấn ở đầu câu lệnh; derived table đặt truy vấn con ngay tại FROM. Cả hai đều có thể được optimizer merge hoặc materialize tùy cấu trúc và kế hoạch.

## 2. Hai chiến lược: merge và materialization

### 2.1. Merge là gì?

Khi merge, MySQL hợp nhất query block của CTE vào query block tham chiếu nó. Có thể hình dung CTE được mở rộng vào truy vấn ngoài để optimizer tối ưu các bảng và điều kiện như một kế hoạch chung.

Ví dụ:

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

CTE chỉ chiếu các cột từ bảng và không có GROUP BY, DISTINCT, LIMIT hay phép toán cản trở merge. MySQL có thể merge CTE, đưa điều kiện customer_id = 100 và status = 'PAID' xuống truy cập bảng orders, rồi chọn index thích hợp.

Trong trường hợp merge thành công, kế hoạch có thể chỉ hiển thị bảng orders; không nhất thiết có một bước tạo bảng trung gian mang tên order_source.

### 2.2. Materialization là gì?

Khi materialize, MySQL thực thi truy vấn CTE để tạo một kết quả trung gian trong internal temporary table. Truy vấn ngoài đọc kết quả đó như một nguồn hàng.

Ví dụ:

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 1000;
~~~

CTE có GROUP BY và aggregate. Những đặc điểm này ngăn merge theo các quy tắc merge của MySQL, nên CTE được materialize. Kết quả trung gian chứa tối đa một hàng cho mỗi customer_id; outer query JOIN với tập đã tổng hợp.

Materialization có chi phí xây dựng kết quả và đọc bảng trung gian. Bảng tạm nội bộ có thể được giữ trong bộ nhớ hoặc chuyển sang lưu trữ trên đĩa tùy kích thước, kiểu dữ liệu và giới hạn cấu hình. Không nên mặc định mọi materialized CTE đều nằm hoàn toàn trong RAM.

### 2.3. CTE không tự quyết định chiến lược

Chỉ nhìn thấy WITH name AS (...) không đủ để kết luận MySQL sẽ tạo bảng tạm. Với CTE không đệ quy, optimizer có thể:

- Merge CTE vào truy vấn tham chiếu.
- Materialize CTE thành kết quả trung gian.
- Chọn cách thực thi khác phù hợp với phép biến đổi được hỗ trợ.

Kết quả phụ thuộc cấu trúc CTE, số lần tham chiếu, điều kiện outer query, thống kê, phiên bản và chi phí ước lượng. Hãy dùng EXPLAIN để kiểm tra kế hoạch thực tế.

## 3. Khi nào CTE có thể được merge?

CTE đơn giản, không có cấu trúc buộc phải giữ kết quả trung gian, thường có thể được merge.

Ví dụ:

~~~sql
WITH recent_orders AS (
    SELECT order_id, customer_id, status, created_at
    FROM orders
)
SELECT order_id, created_at
FROM recent_orders
WHERE customer_id = 20
  AND status = 'PAID';
~~~

CTE chỉ chiếu cột; điều kiện lọc có thể được kết hợp với điều kiện của truy vấn ngoài. Nếu có index phù hợp, optimizer có thể truy cập trực tiếp một vùng nhỏ của orders.

### 3.1. Lợi ích của merge

Merge có thể:

- Đẩy điều kiện lọc của outer query xuống bảng gốc.
- Cho optimizer kết hợp điều kiện JOIN và WHERE trong một query block.
- Mở rộng cơ hội chọn thứ tự JOIN và access path.
- Tránh tạo và đọc một bảng tạm không cần thiết.
- Tránh lưu các cột hoặc hàng trung gian mà outer query không cần.

Ví dụ, nếu CTE chỉ trả 10 triệu đơn nhưng outer query chỉ cần một customer, merge có thể giúp lọc trực tiếp theo customer_id thay vì phải tạo toàn bộ tập trung gian trước. Đây là cơ hội tối ưu, không phải bảo đảm rằng mọi CTE merge đều nhanh hơn trong mọi tình huống.

### 3.2. Predicate pushdown và merge

Khi merge, điều kiện ngoài có thể được áp dụng trực tiếp trên bảng nguồn:

~~~sql
WITH source_orders AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
    WHERE created_at >= '2026-01-01'
)
SELECT order_id, total_amount
FROM source_orders
WHERE customer_id = 100;
~~~

Optimizer có thể kết hợp hai điều kiện thành điều kiện truy cập bảng orders:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND customer_id = 100;
~~~

Đây là cách diễn giải logic để hiểu merge. Không nhất thiết optimizer viết lại SQL theo đúng văn bản trên; hãy đọc plan để biết điều kiện và index nào thực sự được sử dụng.

## 4. Cấu trúc thường ngăn merge

Theo quy tắc MySQL, một số cấu trúc trong query block khiến derived table, view hoặc CTE không thể merge và phải được materialize. Các trường hợp quan trọng gồm:

- Aggregate function như SUM(), COUNT(), AVG(), MIN(), MAX().
- Window function.
- DISTINCT.
- GROUP BY.
- HAVING.
- LIMIT.
- UNION hoặc UNION ALL.
- Subquery trong danh sách SELECT của query block.
- Gán giá trị cho user variable.
- Query block chỉ tham chiếu literal, không đọc bảng.

Ví dụ CTE có GROUP BY:

~~~sql
WITH department_stats AS (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT *
FROM department_stats
WHERE employee_count >= 5;
~~~

CTE cần tạo kết quả tổng hợp theo department_id. Không thể đơn giản thay nó bằng một truy vấn đọc từng hàng employees mà vẫn giữ cùng ngữ nghĩa, nên merge bị ngăn và kết quả được materialize.

### 4.1. LIMIT ngăn merge

~~~sql
WITH latest_orders AS (
    SELECT order_id, customer_id, created_at
    FROM orders
    ORDER BY created_at DESC
    LIMIT 100
)
SELECT *
FROM latest_orders
WHERE customer_id = 10;
~~~

Điều kiện customer_id ở ngoài áp dụng lên 100 đơn mới nhất đã chọn. Đẩy điều kiện xuống trước LIMIT có thể làm thay đổi tập 100 hàng, vì vậy optimizer không thể tùy tiện merge query block này.

Nếu nghiệp vụ thật sự muốn 100 đơn mới nhất của riêng customer 10, hãy đặt điều kiện trong CTE:

~~~sql
WITH latest_customer_orders AS (
    SELECT order_id, customer_id, created_at
    FROM orders
    WHERE customer_id = 10
    ORDER BY created_at DESC
    LIMIT 100
)
SELECT *
FROM latest_customer_orders;
~~~

Hai truy vấn không tương đương. Hãy đặt điều kiện ở đúng tầng phản ánh yêu cầu nghiệp vụ trước khi nghĩ đến tối ưu.

### 4.2. DISTINCT và UNION

~~~sql
WITH all_customer_ids AS (
    SELECT customer_id FROM current_orders
    UNION
    SELECT customer_id FROM archived_orders
)
SELECT customer_id
FROM all_customer_ids
WHERE customer_id > 100;
~~~

UNION loại các giá trị trùng giữa hai tập. Query block phải giữ ngữ nghĩa khử trùng nên không được merge theo cách thông thường. Nếu thay UNION bằng UNION ALL, hàng trùng được giữ và ngữ nghĩa thay đổi; không đổi chỉ để mong có plan khác.

### 4.3. Materialization không có nghĩa mọi điều kiện đều bị chặn

Khi CTE materialize, một số phép đẩy điều kiện vẫn có thể được optimizer hỗ trợ, tùy cấu trúc truy vấn. Ví dụ, điều kiện trên cột grouping có thể được đẩy vào WHERE hoặc HAVING khi phép biến đổi bảo toàn ngữ nghĩa. Vì vậy, không kết luận rằng materialized CTE luôn phải tính toàn bộ dữ liệu trước khi áp dụng mọi điều kiện ngoài.

Đọc EXPLAIN và optimizer trace để biết MySQL đã áp dụng phép biến đổi nào. Đặc biệt chú ý điều kiện trên cột aggregate: nó không thể được chuyển thành điều kiện lọc hàng nguồn trước khi tính aggregate nếu việc đó làm đổi kết quả.

## 5. Materialization và khả năng tái sử dụng CTE

Một ưu điểm quan trọng của CTE là có thể tham chiếu cùng tên nhiều lần trong một câu SQL:

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > (
    SELECT AVG(t2.total_amount)
    FROM customer_totals AS t2
);
~~~

CTE customer_totals được tham chiếu ở outer JOIN và trong scalar subquery. Nếu CTE được materialize, MySQL materialize kết quả một lần cho câu lệnh rồi tái sử dụng cho các tham chiếu, thay vì tạo một bản sao độc lập cho từng chỗ dùng.

### 5.1. Index tự động trên bảng materialized

MySQL có thể tạo index nội bộ trên kết quả materialized nếu index giúp truy cập CTE hiệu quả hơn. Ví dụ, một tham chiếu tìm theo customer_id có thể được hưởng lợi từ index trên cột này.

Khi cùng CTE được tham chiếu nhiều lần với các điều kiện truy cập khác nhau, optimizer có thể tạo các index phù hợp cho từng tham chiếu. Đây là index nội bộ của bảng tạm; không phải index được thêm vĩnh viễn vào bảng nguồn.

Không thể yêu cầu một tên index nội bộ cụ thể như khi tạo index trên bảng thật. Dùng EXPLAIN để quan sát key hoặc access method mà optimizer chọn.

### 5.2. Materialization có thể bị trì hoãn

MySQL có thể trì hoãn việc materialize cho đến khi kết quả thực sự cần dùng. Nếu một nhánh JOIN trước đó không tạo hàng nào và không cần đọc CTE, MySQL có thể bỏ qua việc xây dựng bảng trung gian.

Do đó, không nên mô tả materialization đơn giản là "luôn chạy CTE trước outer query". Optimizer có thể chọn thứ tự và thời điểm phù hợp để tránh công việc không cần thiết.

### 5.3. Chi phí của materialization

Materialization có thể tốn:

- CPU để chạy SELECT tạo CTE.
- Bộ nhớ hoặc dung lượng đĩa cho internal temporary table.
- I/O để ghi và đọc kết quả trung gian.
- Chi phí tạo index nội bộ.
- Chi phí chuyển dữ liệu giữa các bước query plan.

Đổi lại, nếu CTE được tham chiếu nhiều lần, tính toán một lần rồi tái sử dụng có thể rẻ hơn chạy lại logic nguồn ở từng nơi. Kết quả phụ thuộc số hàng, số cột, số tham chiếu, điều kiện lọc và kế hoạch thực tế.

## 6. CTE đệ quy và materialization

CTE đệ quy được dùng để duyệt cây, phân cấp hoặc chuỗi quan hệ. Trong MySQL, recursive CTE luôn được materialize; không được merge như một CTE không đệ quy đơn giản.

Ví dụ duyệt cây nhân viên:

~~~sql
WITH RECURSIVE employee_tree AS (
    SELECT employee_id, manager_id, full_name, 0 AS depth
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT e.employee_id, e.manager_id, e.full_name, t.depth + 1
    FROM employees AS e
    JOIN employee_tree AS t
      ON e.manager_id = t.employee_id
)
SELECT *
FROM employee_tree
ORDER BY depth, employee_id;
~~~

Anchor member tạo các nút gốc; recursive member tìm nhân viên có manager_id trỏ đến nút đã tìm thấy. MySQL lặp recursive member để bổ sung các tầng tiếp theo cho đến khi không còn hàng mới hoặc chạm giới hạn đệ quy.

### 6.1. Materialization trong recursive CTE

Recursive CTE cần lưu và mở rộng các kết quả trung gian qua từng vòng lặp. Vì vậy, MySQL materialize kết quả recursive CTE. Không dùng MERGE hint với kỳ vọng biến recursive CTE thành truy vấn merge.

### 6.2. Kiểm soát số vòng lặp

MySQL có biến cte_max_recursion_depth để giới hạn độ sâu đệ quy. Xem giá trị:

~~~sql
SELECT @@SESSION.cte_max_recursion_depth;
~~~

Có thể điều chỉnh cho session lab:

~~~sql
SET SESSION cte_max_recursion_depth = 1000;
~~~

Không tăng giới hạn để che một truy vấn có vòng lặp hoặc dữ liệu cây lỗi. Cần kiểm tra điều kiện dừng, khóa liên kết và khả năng dữ liệu có chu trình. Việc phát hiện chu trình và giới hạn độ sâu là hai vấn đề khác nhau.

## 7. MERGE và NO_MERGE optimizer hints

MySQL cung cấp optimizer hints MERGE() và NO_MERGE() để gợi ý có merge hay materialize query block của derived table, view hoặc CTE trong các trường hợp hỗ trợ.

### 7.1. Gợi ý merge

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100;
~~~

MERGE(order_source) yêu cầu optimizer xem xét merge CTE vào truy vấn tham chiếu. Nếu cấu trúc CTE có GROUP BY, DISTINCT, LIMIT hoặc yếu tố khác cấm merge, hint không thể làm thay đổi quy tắc ngữ nghĩa.

### 7.2. Gợi ý materialize

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100;
~~~

NO_MERGE(order_source) yêu cầu giữ query block riêng để materialize nếu optimizer và cấu trúc truy vấn cho phép. Materialization không luôn tốt hơn; nó có thể tạo bảng tạm lớn trong khi merge có thể lọc sớm trên bảng nguồn.

### 7.3. Kiểm tra hint có được áp dụng

Sau EXPLAIN, có thể xem warning:

~~~sql
EXPLAIN
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100;

SHOW WARNINGS;
~~~

Nếu hint không hợp lệ, không được nhận diện hoặc không thể áp dụng, warning có thể giải thích vấn đề. Đồng thời phải xem plan; không kết luận hint thành công chỉ vì câu SQL không báo lỗi.

### 7.4. Không dùng hint thay cho phân tích

Hint là công cụ kiểm chứng giả thuyết hoặc xử lý một trường hợp đã hiểu rõ. Không rải MERGE/NO_MERGE vào mọi CTE. Dữ liệu thay đổi, thống kê cập nhật hoặc nâng phiên bản MySQL có thể làm lựa chọn tối ưu khác đi.

## 8. Điều khiển merge bằng optimizer_switch

Biến optimizer_switch có tùy chọn derived_merge. Tùy chọn này ảnh hưởng quyết định merge của derived table, view và CTE trong phạm vi hỗ trợ.

Xem trạng thái:

~~~sql
SELECT @@SESSION.optimizer_switch;
~~~

Trong môi trường lab, có thể tắt merge cho session:

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'derived_merge=off';
~~~

Chạy lại EXPLAIN để quan sát kế hoạch, sau đó khôi phục:

~~~sql
SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

Chỉ thay đổi session để thử nghiệm. Không đặt GLOBAL chỉ nhằm kiểm tra một truy vấn vì cấu hình global ảnh hưởng các kết nối mới. Khi chỉ muốn thử một CTE, optimizer hint thường có phạm vi cụ thể hơn.

Nếu thay đổi optimizer_switch bằng một chuỗi gồm nhiều tùy chọn, hãy hiểu rõ cách gán và giữ lại các thiết lập khác. Không ghi đè toàn bộ cấu hình bằng một danh sách rút gọn nếu không có chủ đích.

## 9. Đọc kế hoạch bằng EXPLAIN

EXPLAIN cho biết optimizer dự định thực thi câu SQL như thế nào. Với CTE, mục tiêu là xác định query block được merge hay materialize, nguồn hàng nào được đọc, điều kiện nào được dùng và có index nào được chọn.

### 9.1. EXPLAIN dạng mặc định

~~~sql
EXPLAIN
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

Khi CTE được merge, plan thường cho thấy truy cập trực tiếp bảng nguồn orders; không có bước materialize riêng cho CTE. Tên và cách trình bày phụ thuộc phiên bản MySQL và định dạng EXPLAIN.

### 9.2. EXPLAIN FORMAT=TREE

MySQL 8.0.16+ hỗ trợ định dạng TREE:

~~~sql
EXPLAIN FORMAT=TREE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > 1000;
~~~

TREE biểu diễn các iterator theo cấu trúc cây, thuận tiện để đọc thứ tự JOIN và bước materialize. Với materialized CTE, plan có thể hiển thị node như Materialize CTE hoặc node tương đương; tên và mức chi tiết phụ thuộc phiên bản.

### 9.3. EXPLAIN FORMAT=JSON

JSON cung cấp plan có cấu trúc:

~~~sql
EXPLAIN FORMAT=JSON
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id;
~~~

Khi materialize, cấu trúc JSON có thể mô tả derived/materialized query block và nguồn subquery. Dùng JSON khi cần đọc thuộc tính chi tiết hoặc tự động phân tích plan bằng công cụ. Không dựa vào một tên field duy nhất giữa các phiên bản; hãy đọc toàn bộ cấu trúc.

### 9.4. EXPLAIN ANALYZE

MySQL 8.0.18+ hỗ trợ EXPLAIN ANALYZE cho câu SELECT tương thích. Lệnh thực thi truy vấn và hiển thị thời gian, số vòng lặp cùng số hàng thực tế:

~~~sql
EXPLAIN ANALYZE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > 1000;
~~~

EXPLAIN thông thường chủ yếu cung cấp ước lượng; EXPLAIN ANALYZE giúp đối chiếu ước lượng với số hàng và thời gian thực tế. Lệnh này thật sự chạy SELECT, nên truy vấn nặng vẫn tiêu thụ tài nguyên. Chạy trên lab/staging hoặc trong điều kiện đã đánh giá tải; không dùng tùy tiện trên production.

## 10. Các dấu hiệu cần đọc trong plan

Khi xem EXPLAIN, tập trung vào các dấu hiệu sau:

| Dấu hiệu | Cách hiểu |
|---|---|
| Bảng nguồn xuất hiện trực tiếp, không có node materialize CTE | Có thể CTE đã được merge vào query block ngoài |
| Node Materialize CTE hoặc node materialization tương đương trong TREE | Optimizer tạo kết quả trung gian cho CTE |
| <derivedN> hoặc thông tin materialized query block trong output dạng khác | Có thể là nguồn kết quả được materialize; cần xem toàn plan |
| key là index được chọn | Kiểm tra index có hỗ trợ điều kiện JOIN/WHERE hay không |
| type hoặc access method là ALL | Có thể quét toàn bảng; đánh giá theo kích thước và tính chọn lọc |
| rows và filtered | Ước lượng số hàng đọc và tỷ lệ hàng vượt qua điều kiện |
| Số vòng lặp và actual rows trong EXPLAIN ANALYZE | Khối lượng thực tế mỗi iterator xử lý |
| Temporary table hoặc sort | Kiểm tra GROUP BY, DISTINCT, ORDER BY và kích thước dữ liệu trung gian |

Không kết luận chỉ dựa trên việc có ALL hay Materialize. Quét toàn bảng trên bảng nhỏ có thể là lựa chọn rẻ nhất; materialization có thể tiết kiệm công việc khi kết quả được dùng nhiều lần. Hãy so sánh số hàng, thời gian và mục tiêu nghiệp vụ.

## 11. Dùng optimizer trace khi EXPLAIN chưa đủ

Optimizer trace cung cấp thông tin về các quyết định và phép biến đổi optimizer đã xem xét. Có thể bật trong session:

~~~sql
SET optimizer_trace = 'enabled=on';

WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';

SELECT TRACE
FROM information_schema.OPTIMIZER_TRACE;

SET optimizer_trace = 'enabled=off';
~~~

Trace có thể giúp tìm quyết định merge/materialize, lý do một phép biến đổi bị từ chối và các lựa chọn access path. Nội dung trace khá dài và phụ thuộc phiên bản; hãy tìm phần liên quan đến query block, derived/CTE và transformation thay vì đọc như một bản log tuyến tính.

Optimizer trace là công cụ chẩn đoán, không thay thế EXPLAIN ANALYZE. Trace giải thích quyết định optimizer; EXPLAIN ANALYZE cho số liệu thực thi của iterator.

## 12. Ví dụ so sánh merge và materialization

Giả sử có hai bảng:

- customers: mỗi hàng là một khách hàng, khóa chính customer_id.
- orders: mỗi hàng là một đơn hàng, có customer_id, status, total_amount và created_at.

### 12.1. CTE đơn giản có thể merge

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount, created_at
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

Chạy EXPLAIN:

~~~sql
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount, created_at
    FROM orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

Kiểm tra liệu plan truy cập trực tiếp orders và có dùng index phù hợp hay không. Ví dụ index cần đánh giá:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

Không tạo index trùng với index hiện có. Nếu truy vấn cần thêm total_amount và index/engine hỗ trợ covering phù hợp, có thể đánh giá index bao phủ, nhưng phải cân nhắc chi phí lưu trữ và ghi.

### 12.2. CTE aggregate thường materialize

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 1000;
~~~

GROUP BY và aggregate ngăn merge. Kết quả được materialize theo customer_id trước khi JOIN. Index trên orders(customer_id, status) hoặc orders(status, customer_id) có thể phù hợp tùy điều kiện và phân bố dữ liệu; dùng EXPLAIN để lựa chọn thay vì áp dụng máy móc một thứ tự.

### 12.3. CTE được tham chiếu nhiều lần

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.total_amount,
       t.order_count
FROM customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > (
    SELECT AVG(t2.total_amount)
    FROM customer_totals AS t2
);
~~~

CTE được dùng ở cả JOIN và scalar subquery. Nếu materialized, kết quả trung gian được tạo một lần và tái sử dụng. Optimizer có thể bổ sung index nội bộ để hỗ trợ các cách truy cập khác nhau.

### 12.4. Cùng một CTE, thử ép hai chiến lược

Để kiểm chứng trên lab, dùng một CTE đơn giản và thử hint:

~~~sql
-- Yêu cầu merge
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';

-- Yêu cầu materialization
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 100
  AND status = 'PAID';
~~~

So sánh node plan, số hàng ước lượng, index và chi phí. Nếu CTE có cấu trúc cấm merge, hint MERGE không thể buộc optimizer vi phạm ngữ nghĩa. Nếu hint không được áp dụng, kiểm tra SHOW WARNINGS.

## 13. Quy trình tối ưu CTE

Khi CTE làm truy vấn chậm, thực hiện theo thứ tự:

1. **Xác định kết quả cần có:** mỗi CTE đại diện cho cấp dữ liệu nào, có cần khử trùng hoặc tổng hợp không.
2. **Kiểm tra số lần tham chiếu:** CTE dùng một lần hay nhiều lần; việc tính lại hay tái sử dụng có thể tạo khác biệt lớn.
3. **Đọc cấu trúc CTE:** tìm GROUP BY, aggregate, DISTINCT, LIMIT, UNION, window function và các yếu tố ngăn merge.
4. **Chạy EXPLAIN:** xác định CTE merge hay materialize, bảng nào được đọc, index nào được chọn.
5. **Kiểm tra predicate:** điều kiện nào được áp dụng trước khi tạo kết quả trung gian, điều kiện nào lọc sau materialization.
6. **Kiểm tra độ rộng và kích thước:** chỉ chiếu các cột cần dùng; giảm số hàng trong CTE khi điều đó bảo toàn ngữ nghĩa.
7. **Đánh giá index nguồn:** xem index trên cột lọc, JOIN và grouping; tránh thêm index trùng hoặc làm tăng chi phí ghi không cần thiết.
8. **Đo thực tế:** dùng EXPLAIN ANALYZE trên môi trường phù hợp, so sánh estimated rows với actual rows và loops.
9. **Thử hint có kiểm soát:** so sánh MERGE và NO_MERGE để kiểm chứng giả thuyết, sau đó đánh giá trên dữ liệu đại diện.
10. **Kiểm tra lại kết quả:** bảo đảm việc đổi vị trí điều kiện, thay CTE bằng JOIN hoặc đổi chiến lược không làm thay đổi semantics của LIMIT, aggregate, duplicate và NULL.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| CTE chạy chậm dù truy vấn trong CTE đơn giản | CTE bị materialize, tạo bảng trung gian lớn | Xem EXPLAIN; kiểm tra merge, hint và điều kiện lọc |
| CTE aggregate không merge | GROUP BY hoặc aggregate ngăn merge theo quy tắc | Đánh giá materialization và index nguồn; không cố merge sai ngữ nghĩa |
| NO_MERGE không tạo khác biệt | CTE vốn đã không thể merge hoặc hint không áp dụng | Xem SHOW WARNINGS và plan |
| MERGE không có tác dụng | Cấu trúc query block cấm merge | Loại bỏ cấu trúc chỉ khi vẫn giữ đúng kết quả nghiệp vụ |
| CTE được dùng hai lần nhưng tính toán tốn kém | Kế hoạch không tái sử dụng như kỳ vọng hoặc materialized result quá lớn | Xem plan và trace; kiểm tra số tham chiếu, kích thước và access path |
| Bảng tạm gây I/O tăng | Kết quả materialize lớn hoặc vượt ngưỡng lưu trữ bộ nhớ | Giảm hàng/cột đầu vào nếu đúng nghĩa, kiểm tra cấu hình và đo trên staging |
| Điều kiện ngoài không giảm dữ liệu nguồn | Điều kiện không được đẩy vào CTE hoặc bị giới hạn bởi semantics | Kiểm tra plan; đặt điều kiện vào đúng query block nếu không đổi kết quả |
| EXPLAIN ANALYZE làm truy vấn tốn tải | Lệnh thực thi truy vấn thật | Dùng môi trường lab/staging và dữ liệu phù hợp |
| Recursive CTE không merge | Recursive CTE luôn materialized | Tối ưu anchor, recursive member, index và điều kiện dừng |
| Kết quả đổi sau khi đẩy WHERE qua LIMIT/GROUP BY | Hai vị trí lọc có semantics khác nhau | Xác định thứ tự nghiệp vụ; không di chuyển điều kiện tùy tiện |

## 15. Bài thực hành: quan sát merge và materialization

Thực hiện trong database lab MySQL 8.0. Bài thực hành tạo hai bảng riêng; không chạy trên bảng production.

### 15.1. Tạo bảng mẫu

~~~sql
CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id BIGINT NOT NULL,
    customer_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_orders_customer_status (customer_id, status),
    KEY ix_lab_orders_status_customer (status, customer_id),
    CONSTRAINT fk_lab_orders_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customers (customer_id)
) ENGINE=InnoDB;
~~~

Nạp dữ liệu mẫu:

~~~sql
INSERT INTO lab_customers (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung');

INSERT INTO lab_orders
    (order_id, customer_id, status, total_amount, created_at)
VALUES
    (101, 1, 'PAID', 700.00, '2026-01-10 09:00:00'),
    (102, 1, 'PAID', 500.00, '2026-01-11 09:00:00'),
    (103, 1, 'PENDING', 200.00, '2026-01-12 09:00:00'),
    (104, 2, 'PAID', 1500.00, '2026-01-13 09:00:00'),
    (105, 2, 'CANCELLED', 300.00, '2026-01-14 09:00:00'),
    (106, 3, 'PAID', 250.00, '2026-01-15 09:00:00');
~~~

### 15.2. Bước 1 — CTE đơn giản

~~~sql
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';
~~~

Kết quả gồm hai đơn PAID của khách hàng 1. Ghi nhận số hàng trả về và kiểm tra truy vấn không cần tổng hợp hay khử trùng.

### 15.3. Bước 2 — Quan sát plan có thể merge

~~~sql
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';
~~~

Quan sát xem plan truy cập trực tiếp lab_orders hay có node materialization. Nếu bảng quá nhỏ, optimizer có thể chọn scan thay vì index; điều đó không tự chứng minh merge thất bại. Hãy đọc cấu trúc query block cùng các node của plan.

### 15.4. Bước 3 — Thử NO_MERGE

~~~sql
EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT /*+ NO_MERGE(order_source) */
       order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';

SHOW WARNINGS;
~~~

So sánh plan với bước trước. Tìm node materialize hoặc derived result và kiểm tra warning nếu hint không được áp dụng. Sau đó thử MERGE(order_source) và ghi lại sự khác biệt.

### 15.5. Bước 4 — CTE có aggregate

~~~sql
EXPLAIN FORMAT=TREE
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM lab_customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 500;
~~~

GROUP BY và aggregate ngăn merge. Xác định node materialization, số hàng được tổng hợp và bước JOIN với customers.

### 15.6. Bước 5 — CTE được tham chiếu hai lần

~~~sql
EXPLAIN FORMAT=TREE
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.total_amount,
       t.order_count
FROM lab_customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount > (
    SELECT AVG(t2.total_amount)
    FROM customer_totals AS t2
);
~~~

Xác định hai nơi tham chiếu CTE. Nếu CTE được materialize, kết quả trung gian được tạo một lần và tái sử dụng. Quan sát các access path và index nội bộ nếu EXPLAIN hiển thị.

### 15.7. Bước 6 — Đo bằng EXPLAIN ANALYZE

Nếu server là MySQL 8.0.18 trở lên:

~~~sql
EXPLAIN ANALYZE
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       t.order_count,
       t.total_amount
FROM lab_customers AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_amount >= 500;
~~~

So sánh actual rows, loops và thời gian giữa các node. Dữ liệu lab rất nhỏ nên không dùng thời gian tuyệt đối để kết luận chiến lược nào nhanh hơn trên production; mục tiêu là hiểu cấu trúc plan.

### 15.8. Bước 7 — Thử optimizer_switch trong session

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'derived_merge=off';

EXPLAIN FORMAT=TREE
WITH order_source AS (
    SELECT order_id, customer_id, status, total_amount
    FROM lab_orders
)
SELECT order_id, total_amount
FROM order_source
WHERE customer_id = 1
  AND status = 'PAID';

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

So sánh plan khi merge bị tắt. Khôi phục session setting ngay sau thử nghiệm và không dùng SET GLOBAL trong bài lab.

### 15.9. Bước 8 — Dọn bảng lab

~~~sql
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Xóa bảng con trước bảng cha để không vi phạm foreign key. Chỉ xóa hai bảng lab vừa tạo.

**Kết quả cần đạt:** giải thích được merge và materialization; nhận biết các cấu trúc ngăn merge; quan sát CTE được dùng nhiều lần; hiểu index nội bộ và materialization trì hoãn; đọc được EXPLAIN TREE và EXPLAIN ANALYZE; biết thử optimizer hints/switch trong session.

## 16. Nguyên tắc cần ghi nhớ

- CTE là query expression có tên, chỉ tồn tại trong một câu lệnh; không phải bảng vật lý lưu lâu dài.
- CTE không đệ quy có thể được merge hoặc materialize tùy query shape và quyết định optimizer.
- Merge hợp nhất query block, tạo cơ hội đẩy điều kiện và tối ưu trực tiếp trên bảng nguồn.
- Materialization tạo kết quả trung gian; có chi phí xây dựng, lưu trữ, đọc và có thể tạo index nội bộ.
- Aggregate, window function, DISTINCT, GROUP BY, HAVING, LIMIT, UNION và một số cấu trúc khác ngăn merge.
- Nếu CTE được materialize và tham chiếu nhiều lần, kết quả được tạo một lần cho câu lệnh rồi tái sử dụng; optimizer có thể tạo index nội bộ cho các tham chiếu.
- Materialization có thể được trì hoãn cho đến khi kết quả thực sự cần; không mặc định CTE luôn chạy trước outer query.
- Recursive CTE luôn được materialize; tối ưu anchor, recursive member, index và điều kiện dừng.
- MERGE/NO_MERGE và optimizer_switch là công cụ kiểm chứng có kiểm soát, không thay thế phân tích kế hoạch.
- EXPLAIN cho biết kế hoạch ước lượng; EXPLAIN ANALYZE thực thi truy vấn và cung cấp số liệu thực tế từ MySQL 8.0.18+.
- Đọc toàn bộ plan, so sánh estimated rows với actual rows, số vòng lặp, index và chi phí tạo bảng trung gian.
- Không di chuyển điều kiện qua LIMIT, GROUP BY hoặc DISTINCT nếu chưa chứng minh kết quả giữ nguyên.

CTE giúp tổ chức truy vấn, còn merge và materialization là quyết định thực thi của MySQL. Khi hiểu cấu trúc query block, cardinality, số lần tham chiếu và kế hoạch optimizer, bạn có thể chọn cách viết dễ bảo trì đồng thời phát hiện được chi phí bảng tạm, cơ hội đẩy điều kiện và index phù hợp.
