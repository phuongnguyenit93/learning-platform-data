# WHERE và HAVING: thời điểm lọc và tính đúng đắn của phép tổng hợp

WHERE và HAVING đều dùng để lọc dữ liệu, nhưng chúng tác động ở những giai đoạn logic khác nhau của một truy vấn. WHERE chọn các hàng đầu vào trước khi GROUP BY tạo nhóm và tính aggregate. HAVING lọc các nhóm sau khi phép tổng hợp đã được tính. Đặt một điều kiện sai vị trí có thể làm thay đổi số hàng, COUNT, SUM, AVG hoặc thậm chí biến một outer join thành inner join ngoài ý muốn.

Trong tối ưu hiệu năng cơ sở dữ liệu, phân biệt đúng hai mệnh đề giúp giảm dữ liệu phải xử lý mà vẫn giữ nguyên kết quả nghiệp vụ. Một điều kiện có thể đẩy xuống WHERE nếu nó chỉ giới hạn các hàng đầu vào theo cách tương đương; điều kiện phụ thuộc kết quả aggregate phải được đánh giá sau GROUP BY. Cần xem execution plan để xác nhận engine đã áp dụng predicate sớm đến đâu, đồng thời kiểm thử kết quả với dữ liệu biên, NULL và nhóm không có hàng.

## 1. Thứ tự xử lý logic của truy vấn

Một truy vấn SELECT có thể được viết theo thứ tự cú pháp, nhưng thứ tự xử lý logic thường được hiểu khái quát như sau:

1. FROM và JOIN: xác định nguồn dữ liệu và kết hợp các quan hệ.
2. ON: áp dụng điều kiện ghép trong từng phép JOIN.
3. WHERE: lọc các hàng đầu vào.
4. GROUP BY: gom các hàng còn lại thành nhóm.
5. Các phép aggregate: tính COUNT, SUM, AVG, MIN, MAX và các biểu thức tổng hợp.
6. HAVING: lọc các nhóm dựa trên khóa nhóm hoặc kết quả aggregate.
7. SELECT: tạo các biểu thức và cột đầu ra.
8. DISTINCT: loại các hàng kết quả trùng nếu được yêu cầu.
9. ORDER BY: sắp xếp kết quả.
10. LIMIT/OFFSET hoặc cơ chế giới hạn hàng tương ứng: giới hạn kết quả cuối.

Đây là mô hình logic để hiểu ngữ nghĩa, không phải cam kết engine thực thi vật lý theo đúng thứ tự trên. Bộ tối ưu có thể đổi thứ tự join, đẩy predicate xuống scan hoặc dùng một kế hoạch khác miễn là kết quả vẫn tương đương theo quy tắc SQL.

Điểm quan trọng là WHERE nhìn thấy các hàng sau FROM/JOIN nhưng trước GROUP BY; HAVING nhìn thấy các nhóm sau tổng hợp. Vì vậy, WHERE không thể trực tiếp kiểm tra SUM hoặc COUNT của một nhóm trong cùng cấp SELECT, còn HAVING có thể.

## 2. WHERE lọc hàng trước khi tổng hợp

WHERE xác định những hàng nào được phép tham gia phép GROUP BY và aggregate. Nếu một hàng bị loại bởi WHERE, hàng đó không đóng góp vào COUNT, SUM, AVG hoặc các phép tính khác của nhóm.

Ví dụ, bảng orders lưu đơn hàng ở nhiều trạng thái:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Truy vấn trên chỉ đếm và cộng các đơn PAID. Đơn CANCELLED hoặc PENDING không tham gia phép tổng hợp.

Nếu bảng có 10 triệu hàng nhưng chỉ 15% là PAID, WHERE có thể giảm đáng kể số hàng cần đưa vào aggregate. Khi có chỉ mục hoặc partition phù hợp, engine còn có thể đọc một phần dữ liệu thay vì quét toàn bộ bảng.

### 2.1. Điều kiện phù hợp với WHERE

Thông thường, đặt trong WHERE những điều kiện:

- Lọc theo cột thời gian, trạng thái, tenant hoặc khóa nghiệp vụ trước khi nhóm.
- Giới hạn phạm vi dữ liệu mà báo cáo thực sự cần.
- Lọc theo cột tham gia join hoặc điều kiện của một bảng nguồn, nếu việc đặt điều kiện không làm thay đổi ngữ nghĩa outer join.
- Lọc các hàng không cần tham gia phép tổng hợp.

Ví dụ:

~~~sql
SELECT
    product_id,
    SUM(quantity) AS units_sold
FROM order_items
WHERE created_at >= :from_time
  AND created_at < :to_time
  AND is_test_order = FALSE
GROUP BY product_id;
~~~

Khoảng thời gian và điều kiện loại đơn thử nghiệm giới hạn dữ liệu đầu vào trước khi tính tổng số lượng bán.

### 2.2. WHERE không thể lọc theo kết quả aggregate cùng cấp

Ví dụ sau không hợp lệ trong SQL thông thường:

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE SUM(total_amount) > 100000
GROUP BY customer_id;
~~~

Lý do là WHERE được áp dụng trước khi nhóm và tính SUM. Để lọc khách hàng theo tổng doanh thu, dùng HAVING:

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id
HAVING SUM(total_amount) > 100000;
~~~

## 3. HAVING lọc nhóm sau khi tổng hợp

HAVING được áp dụng sau GROUP BY. Nó thường dùng điều kiện phụ thuộc vào aggregate, chẳng hạn tổng doanh thu, số đơn, giá trị trung bình hoặc số lượng bản ghi thỏa một tiêu chí.

Ví dụ:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= :from_time
  AND created_at < :to_time
GROUP BY customer_id
HAVING COUNT(*) >= 5
   AND SUM(total_amount) >= 100000;
~~~

WHERE giới hạn các đơn hàng trong khoảng thời gian. GROUP BY tạo một nhóm cho mỗi khách hàng. HAVING chỉ giữ nhóm có ít nhất 5 đơn và tổng doanh thu đạt ngưỡng.

### 3.1. Điều kiện trên khóa nhóm trong HAVING

SQL cho phép dùng HAVING với điều kiện trên cột nhóm, dù không có aggregate:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING customer_id = 125;
~~~

Với GROUP BY đơn giản trên customer_id, điều kiện này thường có thể chuyển thành WHERE:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id = 125
GROUP BY customer_id;
~~~

Hai cách cho cùng kết quả trong trường hợp này vì mọi hàng trong một nhóm có cùng customer_id. Dạng WHERE thường cho optimizer cơ hội loại dữ liệu sớm hơn và tận dụng chỉ mục trên customer_id.

Tuy nhiên, không phải mọi biểu thức HAVING đều có thể chuyển thẳng xuống WHERE. Cần xét biểu thức nhóm, NULL, grouping sets và ngữ nghĩa của truy vấn. Với ROLLUP hoặc GROUPING SETS, một cột có thể mang NULL đại diện cho subtotal; lọc cột nhóm một cách đơn giản có thể loại cả hàng tổng phụ ngoài dự kiến.

### 3.2. HAVING không thay thế WHERE

Truy vấn:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING customer_id = 125;
~~~

có thể chỉ trả một nhóm nhưng engine có thể vẫn phải đọc và nhóm nhiều hàng trước khi loại các nhóm khác nếu không đẩy được điều kiện xuống. Viết điều kiện khóa nhóm ở WHERE làm ý định lọc đầu vào rõ ràng hơn:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id = 125
GROUP BY customer_id;
~~~

Không cần viết lại khi optimizer đã tự biến đổi hiệu quả, nhưng nên ưu tiên đặt predicate hàng ở WHERE để truy vấn dễ hiểu và tạo cơ hội tối ưu rõ ràng.

## 4. So sánh trực tiếp WHERE và HAVING

| Tiêu chí | WHERE | HAVING |
|---|---|---|
| Thời điểm logic | Trước GROUP BY | Sau GROUP BY và aggregate |
| Đơn vị được lọc | Hàng đầu vào | Nhóm kết quả |
| Dùng aggregate như SUM/COUNT | Không dùng trực tiếp aggregate cùng cấp | Có thể dùng aggregate |
| Mục đích thường gặp | Giảm dữ liệu cần xử lý | Chọn nhóm theo kết quả tổng hợp |
| Ảnh hưởng đến aggregate | Hàng bị loại không đóng góp vào aggregate | Aggregate được tính trước khi nhóm bị loại |
| Cơ hội tối ưu | Có thể giảm scan, join và aggregate đầu vào | Có thể giảm số nhóm đầu ra; optimizer có thể đẩy điều kiện tương đương nếu an toàn |

Ví dụ phân biệt:

~~~sql
-- Chỉ tính đơn đã thanh toán, rồi giữ khách có ít nhất 3 đơn PAID.
SELECT customer_id, COUNT(*) AS paid_orders
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 3;
~~~

Nếu chuyển status = 'PAID' sang HAVING, phải nhóm theo status hoặc dùng một biểu thức aggregate có điều kiện; kết quả sẽ có ngữ nghĩa khác nếu mục tiêu là chỉ tính đơn PAID.

## 5. Vì sao vị trí lọc ảnh hưởng đến tính đúng đắn?

Điều kiện đặt trước hay sau tổng hợp quyết định tập hàng đóng góp vào phép tính. Chuyển điều kiện giữa WHERE và HAVING mà không xét ý nghĩa có thể làm thay đổi kết quả.

### 5.1. Lọc hàng trước khi tính SUM

Giả sử một khách hàng có ba đơn:

| Đơn | Trạng thái | Giá trị |
|---|---|---:|
| O1 | PAID | 100 |
| O2 | PAID | 200 |
| O3 | CANCELLED | 500 |

Truy vấn:

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

trả doanh thu 300. Nếu nhóm toàn bộ đơn rồi dùng điều kiện HAVING để giữ nhóm có một đơn PAID, nhưng aggregate vẫn là SUM của tất cả trạng thái, kết quả doanh thu sẽ là 800. Hai truy vấn không tương đương.

Nếu nghiệp vụ cần tổng doanh thu của tất cả đơn nhưng chỉ giữ khách hàng có ít nhất một đơn PAID, có thể dùng conditional aggregate:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS all_order_amount,
    SUM(CASE WHEN status = 'PAID' THEN total_amount ELSE 0 END) AS paid_amount,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_count
FROM orders
GROUP BY customer_id
HAVING SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) > 0;
~~~

Ở đây tất cả đơn vẫn tham gia all_order_amount; chỉ các biểu thức CASE mới giới hạn đóng góp theo trạng thái PAID.

### 5.2. COUNT(*) và COUNT(column)

COUNT(*) đếm tất cả hàng trong nhóm. COUNT(column) chỉ đếm các hàng mà biểu thức column không NULL.

Ví dụ:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS row_count,
    COUNT(shipped_at) AS shipped_count
FROM orders
GROUP BY customer_id;
~~~

Nếu nhóm có 10 đơn nhưng chỉ 6 đơn có shipped_at khác NULL, row_count là 10 còn shipped_count là 6. Dùng WHERE shipped_at IS NOT NULL sẽ loại bốn hàng trước khi tính cả hai COUNT, làm thay đổi row_count.

### 5.3. AVG không tương đương với trung bình của các trung bình

Khi chia dữ liệu thành các nhóm rồi tổng hợp tiếp, không được luôn lấy AVG của AVG. Trung bình phải được tính có trọng số theo số hàng:

~~~sql
-- Trung bình trên toàn bộ hàng
SELECT AVG(amount)
FROM payments;
~~~

Nếu mỗi nhóm có số hàng khác nhau, AVG(avg_per_group) thường khác AVG(amount) trên toàn bộ dữ liệu. Việc chuyển filter hoặc thay đổi cấp độ tổng hợp có thể làm thay đổi trọng số và kết quả.

## 6. Lọc theo aggregate và conditional aggregation

Không phải mọi báo cáo đều chỉ cần loại bỏ toàn bộ hàng không thỏa một điều kiện. Đôi khi cùng một nhóm cần nhiều chỉ số, mỗi chỉ số tính trên một tập con khác nhau.

### 6.1. Dùng CASE trong aggregate

Ví dụ cần tổng số đơn và số đơn PAID theo khách hàng:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN status = 'CANCELLED' THEN total_amount ELSE 0 END) AS cancelled_amount
FROM orders
GROUP BY customer_id;
~~~

WHERE status = 'PAID' ở đây sẽ làm mất các đơn khác trạng thái và khiến all_orders không còn là tổng số đơn. CASE giữ toàn bộ hàng đầu vào nhưng chỉ cho các hàng phù hợp đóng góp vào từng aggregate.

### 6.2. FILTER trên aggregate khi hệ quản trị hỗ trợ

Một số hệ quản trị hỗ trợ mệnh đề FILTER để giới hạn hàng cho từng aggregate:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    SUM(total_amount) FILTER (WHERE status = 'CANCELLED') AS cancelled_amount
FROM orders
GROUP BY customer_id;
~~~

FILTER được hỗ trợ trong PostgreSQL và một số hệ quản trị khác; không phải cú pháp portable cho mọi engine. Với SQL Server hoặc MySQL, có thể dùng SUM(CASE...) hoặc COUNT(CASE...) theo ngữ nghĩa phù hợp.

### 6.3. HAVING với nhiều aggregate

Có thể lọc nhóm dựa trên nhiều phép tổng hợp:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 10
   AND COUNT(CASE WHEN status = 'PAID' THEN 1 END) >= 5
   AND SUM(total_amount) > 500000;
~~~

Đây là điều kiện trên kết quả nhóm, nên thuộc HAVING. Nếu một predicate có thể giới hạn hàng đầu vào mà không thay đổi aggregate cần tính, hãy tách predicate đó sang WHERE; các ngưỡng aggregate vẫn ở HAVING.

## 7. Outer join, NULL và vị trí đặt predicate

Một lỗi phổ biến là chuyển điều kiện giữa ON và WHERE khi có LEFT JOIN. Hai vị trí này có ngữ nghĩa khác nhau.

Giả sử cần liệt kê tất cả khách hàng và số đơn PAID của mỗi người, kể cả khách hàng chưa có đơn PAID.

**Cách giữ tất cả khách hàng:**

~~~sql
SELECT
    c.id,
    COUNT(o.id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
   AND o.status = 'PAID'
GROUP BY c.id;
~~~

Điều kiện status được đặt trong ON nên chỉ các đơn PAID được ghép. Khách hàng không có đơn PAID vẫn xuất hiện với COUNT(o.id) bằng 0.

**Cách có thể vô tình loại khách hàng không có đơn PAID:**

~~~sql
SELECT
    c.id,
    COUNT(o.id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
WHERE o.status = 'PAID'
GROUP BY c.id;
~~~

LEFT JOIN tạo hàng mở rộng với các cột orders là NULL cho khách hàng không có đơn. WHERE o.status = 'PAID' loại các hàng NULL đó, khiến kết quả gần với INNER JOIN. Hai truy vấn không tương đương.

### 7.1. COUNT(*) hay COUNT khóa của bảng phải?

Với LEFT JOIN, khách hàng không có đơn vẫn tạo một hàng kết quả với các cột phía orders là NULL. Vì vậy:

- COUNT(*) đếm hàng mở rộng đó và trả 1.
- COUNT(o.id) bỏ qua NULL và trả 0 nếu không có đơn khớp.

Khi đếm số hàng ở phía bảng phải sau outer join, thường dùng COUNT trên khóa không NULL của bảng phải.

### 7.2. HAVING sau LEFT JOIN

Nếu muốn giữ khách hàng có ít nhất hai đơn PAID:

~~~sql
SELECT c.id, COUNT(o.id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id
   AND o.status = 'PAID'
GROUP BY c.id
HAVING COUNT(o.id) >= 2;
~~~

HAVING lọc các nhóm khách hàng theo số đơn đã ghép. Khách hàng có 0 hoặc 1 đơn bị loại sau tổng hợp. Nếu muốn giữ cả khách hàng không có đơn, không đặt ngưỡng loại họ trong HAVING.

## 8. HAVING, DISTINCT và các dạng nhóm nâng cao

### 8.1. DISTINCT không thay thế mọi phép tổng hợp

SELECT DISTINCT loại bỏ hàng kết quả trùng sau khi biểu thức SELECT được tính. GROUP BY tạo nhóm để tính aggregate. Hai dạng có thể tương đương trong trường hợp chỉ chọn các cột nhóm, nhưng không thể thay thế tùy ý khi có COUNT, SUM hoặc biểu thức phụ thuộc nhóm.

### 8.2. ROLLUP, CUBE và GROUPING SETS

Các hệ quản trị hỗ trợ GROUPING SETS, ROLLUP hoặc CUBE có thể tạo cả nhóm chi tiết và nhóm tổng phụ. Các cột nhóm ở hàng subtotal có thể được hiển thị thành NULL, kể cả khi dữ liệu gốc cũng có NULL.

Ví dụ:

~~~sql
SELECT
    region,
    status,
    SUM(total_amount) AS revenue,
    GROUPING(region) AS is_region_total,
    GROUPING(status) AS is_status_total
FROM orders
GROUP BY ROLLUP (region, status);
~~~

Nếu đặt HAVING status IS NOT NULL, có thể loại cả hàng subtotal mà status được đặt NULL để biểu diễn tổng theo region. Nếu cần phân biệt NULL dữ liệu với NULL do rollup tạo ra, dùng hàm GROUPING hoặc cơ chế tương đương của engine.

### 8.3. Window function có thứ tự lọc riêng

Window function được tính trên tập hàng sau WHERE và GROUP BY/HAVING ở cùng cấp truy vấn theo ngữ nghĩa của câu lệnh. Nếu muốn lọc theo ROW_NUMBER hoặc RANK, thường cần một lớp truy vấn bên ngoài:

~~~sql
SELECT customer_id, order_id, row_num
FROM (
    SELECT
        customer_id,
        id AS order_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, id DESC
        ) AS row_num
    FROM orders
    WHERE status = 'PAID'
) AS ranked_orders
WHERE row_num <= 3;
~~~

WHERE bên trong giới hạn đơn PAID trước khi đánh số. WHERE bên ngoài chọn ba hàng đầu của mỗi khách hàng sau khi window function đã được tính. HAVING không phải công cụ để lọc trực tiếp kết quả window function trong cùng cấp SELECT.

## 9. Tối ưu hiệu năng: đưa điều kiện đến đúng giai đoạn

### 9.1. Giảm số hàng trước aggregate

Nếu báo cáo chỉ cần dữ liệu trong một khoảng thời gian, đặt điều kiện thời gian trong WHERE:

~~~sql
SELECT product_id, SUM(quantity) AS units
FROM order_items
WHERE created_at >= :from_time
  AND created_at < :to_time
GROUP BY product_id
HAVING SUM(quantity) > 100;
~~~

Engine có thể dùng chỉ mục trên created_at, partition pruning hoặc predicate pushdown để giảm dữ liệu phải đọc và tổng hợp. HAVING vẫn giữ vai trò lọc nhóm theo tổng số lượng.

### 9.2. Giữ predicate có thể tận dụng chỉ mục

Tránh biến đổi cột trong WHERE nếu điều đó làm điều kiện khó dùng chỉ mục. Ví dụ:

~~~sql
-- Có thể khó tận dụng chỉ mục thường trên created_at
WHERE CAST(created_at AS DATE) = DATE '2026-01-15'
~~~

Có thể viết khoảng nửa mở:

~~~sql
WHERE created_at >= TIMESTAMP '2026-01-15 00:00:00'
  AND created_at < TIMESTAMP '2026-01-16 00:00:00'
~~~

Khoảng nửa mở tránh phụ thuộc độ chính xác timestamp và thường tạo điều kiện range dễ tận dụng index hơn. Kiểu literal và timezone cần phù hợp hệ quản trị và kiểu cột.

### 9.3. Đẩy predicate từ HAVING xuống WHERE khi tương đương

Nếu HAVING chỉ lọc khóa nhóm:

~~~sql
SELECT department_id, COUNT(*) AS employee_count
FROM employees
GROUP BY department_id
HAVING department_id = 20;
~~~

có thể viết:

~~~sql
SELECT department_id, COUNT(*) AS employee_count
FROM employees
WHERE department_id = 20
GROUP BY department_id;
~~~

Việc lọc trước có thể giúp đọc ít hàng và chỉ tạo một nhóm. Một số optimizer tự thực hiện phép biến đổi tương đương, nhưng SQL rõ ràng vẫn giúp người đọc nhận ra ý định.

Không đẩy HAVING chứa aggregate xuống WHERE. Ví dụ HAVING COUNT(*) > 10 phải được kiểm tra sau khi đếm nhóm. Cũng không chuyển predicate nếu nó thay đổi tập hàng tham gia SUM/AVG hoặc làm đổi ngữ nghĩa outer join/grouping sets.

### 9.4. Predicate pushdown qua view và subquery

Optimizer có thể đẩy điều kiện từ truy vấn ngoài vào view hoặc subquery để giảm dữ liệu trung gian. Khả năng này phụ thuộc vào cấu trúc truy vấn, aggregate, DISTINCT, LIMIT, window function, outer join và đặc tính của hệ quản trị.

Ví dụ, lọc theo một khóa nhóm có thể được đẩy vào trước aggregate nếu chứng minh được tương đương. Nhưng lọc theo một cột không thuộc khóa nhóm có thể thay đổi dữ liệu đóng góp vào aggregate. Không tự viết lại chỉ vì muốn đẩy filter xuống; hãy xác nhận kết quả và actual plan.

## 10. Ví dụ phân tích một báo cáo bán hàng

Yêu cầu: tính số đơn và doanh thu PAID theo khách hàng trong quý, chỉ hiển thị khách có ít nhất 5 đơn và doanh thu từ 1.000.000 trở lên.

Truy vấn:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS paid_revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= :quarter_start
  AND created_at < :next_quarter_start
GROUP BY customer_id
HAVING COUNT(*) >= 5
   AND SUM(total_amount) >= 1000000
ORDER BY paid_revenue DESC;
~~~

Cách đọc:

1. WHERE giới hạn hàng PAID và khoảng thời gian của quý.
2. Engine có thể tận dụng chỉ mục hoặc partition theo status/created_at để giảm dữ liệu đầu vào, tùy thiết kế và độ chọn lọc.
3. GROUP BY tạo nhóm theo customer_id.
4. COUNT và SUM tính trên các đơn còn lại sau WHERE.
5. HAVING loại nhóm không đạt số đơn hoặc doanh thu tối thiểu.
6. ORDER BY sắp xếp các nhóm còn lại theo doanh thu.

Giả sử bảng có 80 triệu đơn, nhưng chỉ 4 triệu đơn PAID trong quý. Nếu đặt điều kiện thời gian và trạng thái đúng trong WHERE, engine có cơ hội chỉ xử lý tập con này. Nếu đưa điều kiện trạng thái vào HAVING bằng cách nhóm theo status hoặc viết một cấu trúc khác, có thể phải tổng hợp nhiều dữ liệu hơn và dễ làm thay đổi ý nghĩa doanh thu.

Một chỉ mục có thể được thử nghiệm là (status, created_at, customer_id), hoặc phương án phù hợp hơn với phân bố và workload thực tế. Không thể chọn thứ tự chỉ mục chỉ từ câu SQL: cần xem equality/range, độ chọn lọc, cột trả về, partitioning, các truy vấn khác và chi phí ghi.

Sau khi chạy, hãy đọc actual execution plan:

- Số hàng thực tế sau predicate status và created_at.
- Index Seek/Range Scan hay Table/Seq Scan.
- Số hàng đầu vào và số nhóm đầu ra của Aggregate.
- Sort có xử lý nhiều nhóm hay spill ra vùng tạm không.
- Estimated rows có lệch nhiều so với actual rows không.
- Logical reads, physical reads, CPU và elapsed time.

Nếu WHERE đã giảm dữ liệu tốt nhưng aggregate vẫn chậm, kiểm tra số nhóm, độ rộng dữ liệu, Hash/Sort spill và bộ nhớ. Nếu số hàng sau WHERE lớn hơn nhiều dự kiến, kiểm tra thống kê và phân bố trước khi thêm chỉ mục.

## 11. Kiểm thử tính đúng đắn khi thay đổi WHERE/HAVING

Trước khi giữ một phép viết lại, so sánh kết quả trên cùng snapshot dữ liệu. Các trường hợp nên có:

- Không có hàng nào thỏa WHERE.
- Một nhóm chỉ có một hàng.
- Nhóm có đúng ngưỡng HAVING và thấp hơn/ngay trên ngưỡng.
- Cột lọc có NULL.
- Aggregate đầu vào có NULL.
- Nhóm có cả hàng được chọn và hàng bị loại bởi predicate.
- LEFT JOIN không tìm thấy hàng ở bảng phải.
- Nhiều hàng trùng khóa hoặc quan hệ một-nhiều.
- Giá trị âm, 0 và giá trị biên nếu nghiệp vụ cho phép.
- ROLLUP/GROUPING SETS hoặc window function nếu truy vấn sử dụng.

Có thể đối chiếu hai truy vấn bằng cách chạy trên snapshot giống nhau, so sánh số hàng, khóa nhóm và giá trị aggregate. EXCEPT/MINUS hoặc phép so sánh tương đương có thể giúp tìm khác biệt, nhưng phải xét duplicate: phép tập hợp như EXCEPT thường loại trùng, vì vậy có thể cần so sánh thêm số lần xuất hiện hoặc tổng hợp theo khóa.

Không chỉ xác nhận số dòng kết quả bằng nhau. Hai kết quả có cùng số dòng nhưng giá trị SUM, AVG hoặc COUNT khác nhau vẫn là sai.

## 12. Quy trình tối ưu WHERE và HAVING

1. **Làm rõ yêu cầu nghiệp vụ:** xác định hàng nào được tham gia tính toán và nhóm nào được giữ lại.
2. **Ghi truy vấn baseline:** lưu SQL, tham số, execution plan, số hàng, reads, CPU và elapsed time.
3. **Phân loại từng predicate:** điều kiện trên hàng đưa vào WHERE; điều kiện trên aggregate đưa vào HAVING; điều kiện join đặt đúng ON/WHERE theo loại join.
4. **Kiểm tra NULL và outer join:** xác định COUNT(*), COUNT(column), NULL extension và logic ba giá trị.
5. **Kiểm tra khả năng lọc sớm:** xem predicate có dùng index, partition pruning hoặc pushdown không.
6. **Đề xuất một thay đổi:** chuyển predicate khóa nhóm tương đương xuống WHERE, sửa điều kiện range hoặc dùng conditional aggregate nếu yêu cầu cần nhiều tập con.
7. **Đo lại trên cùng dữ liệu:** giữ tham số, cache state, concurrency và cách đo tương đương.
8. **Đọc kế hoạch mới:** kiểm tra scan, join, số hàng trước/sau aggregate, Sort/Hash, temp I/O và estimated/actual rows.
9. **So sánh kết quả:** xác minh khóa nhóm, số hàng, COUNT, SUM, AVG, NULL và trường hợp biên.
10. **Đánh giá workload tổng thể:** xác nhận cải thiện truy vấn không làm tăng chi phí ghi hoặc làm chậm các truy vấn khác.

## 13. Những nhầm lẫn thường gặp

- **Đưa điều kiện aggregate vào WHERE:** WHERE chạy trước khi aggregate, nên không thể lọc SUM/COUNT của nhóm ở cùng cấp truy vấn.
- **Đưa mọi điều kiện vào HAVING:** làm ý định lọc hàng mờ đi và có thể khiến nhiều hàng được xử lý trước khi loại nhóm.
- **Chuyển status từ WHERE sang HAVING:** có thể thay đổi những hàng đóng góp vào COUNT/SUM.
- **Đẩy predicate qua LEFT JOIN:** có thể loại hàng không khớp và biến outer join thành inner join.
- **Dùng COUNT(*) để đếm hàng bảng phải sau LEFT JOIN:** hàng mở rộng NULL vẫn được đếm; thường cần COUNT khóa của bảng phải.
- **Nhầm COUNT(*) với COUNT(column):** COUNT(column) bỏ qua NULL.
- **Tính trung bình của các trung bình:** bỏ qua trọng số theo số hàng của mỗi nhóm.
- **Dùng HAVING trên ROLLUP mà không xét NULL tổng phụ:** có thể loại các dòng subtotal.
- **Giả định optimizer luôn đẩy HAVING xuống WHERE:** chỉ những phép biến đổi chứng minh được tương đương mới an toàn.
- **Chỉ so sánh thời gian:** cần kiểm tra kết quả aggregate và số liệu tài nguyên để xác định cải thiện có thật.

## 14. Checklist kiểm tra vị trí lọc

- [ ] Đã xác định rõ tập hàng cần tham gia aggregate.
- [ ] Predicate trên hàng được đặt ở WHERE khi phù hợp.
- [ ] Predicate phụ thuộc SUM, COUNT, AVG hoặc aggregate khác được đặt ở HAVING.
- [ ] Đã kiểm tra predicate khóa nhóm có thể chuyển xuống WHERE một cách tương đương.
- [ ] Đã xác nhận điều kiện JOIN nằm đúng ON hoặc WHERE theo yêu cầu giữ hàng.
- [ ] Đã kiểm tra NULL, COUNT(*) và COUNT(column).
- [ ] Đã xem xét conditional aggregation khi nhiều chỉ số cần các tập con khác nhau.
- [ ] Đã kiểm tra ROLLUP/GROUPING SETS và window function nếu có.
- [ ] Đã đọc actual plan và số hàng trước/sau filter, join, aggregate.
- [ ] Đã xác nhận index access, partition pruning hoặc predicate pushdown có thực sự diễn ra.
- [ ] Đã so sánh số hàng, khóa nhóm và giá trị aggregate trước/sau.
- [ ] Đã đo lại reads, CPU, thời gian và temp I/O dưới tải đại diện.

WHERE và HAVING phục vụ hai thời điểm lọc khác nhau. WHERE quyết định dữ liệu đầu vào của phép tổng hợp; HAVING quyết định nhóm nào được giữ sau khi aggregate hoàn tất. Đặt predicate đúng giai đoạn vừa bảo toàn ý nghĩa COUNT/SUM/AVG, vừa tạo cơ hội giảm dữ liệu sớm. Mọi thay đổi cần được kiểm chứng bằng actual execution plan và đối chiếu kết quả trên dữ liệu đại diện.
