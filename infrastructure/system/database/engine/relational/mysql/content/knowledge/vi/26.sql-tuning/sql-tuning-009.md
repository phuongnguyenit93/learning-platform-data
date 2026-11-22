# Tối ưu GROUP BY, DISTINCT và truy vấn báo cáo

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Các truy vấn báo cáo thường phải lọc một tập dữ liệu lớn, nhóm hàng, tính aggregate và loại bỏ bản ghi trùng. Nếu đặt điều kiện sai vị trí, JOIN làm nhân bản hàng hoặc index không phù hợp, truy vấn có thể đọc và sắp xếp nhiều dữ liệu hơn cần thiết.

Muốn tối ưu nhóm truy vấn này, cần hiểu rõ thứ tự logic của WHERE, GROUP BY, HAVING, SELECT, DISTINCT và ORDER BY; phân biệt COUNT(*), COUNT(column) và COUNT(DISTINCT ...); kiểm soát cardinality sau JOIN; chọn composite index theo workload; rồi dùng EXPLAIN và số liệu thực tế để xác minh. Một truy vấn báo cáo tốt phải giữ đúng kết quả nghiệp vụ trước khi tối ưu thời gian chạy.

## 1. Vòng đời logic của truy vấn báo cáo

Một truy vấn SELECT có thể gồm các phần:

~~~sql
SELECT ...
FROM ...
JOIN ...
WHERE ...
GROUP BY ...
HAVING ...
ORDER BY ...
LIMIT ...;
~~~

Để hiểu kết quả, có thể hình dung thứ tự logic khái quát:

1. FROM và JOIN tạo tập hàng đầu vào.
2. WHERE lọc từng hàng trước khi nhóm.
3. GROUP BY chia các hàng còn lại thành nhóm.
4. Aggregate tính giá trị cho mỗi nhóm.
5. HAVING lọc các nhóm sau khi aggregate.
6. SELECT tạo các biểu thức đầu ra.
7. DISTINCT loại các hàng kết quả trùng nhau.
8. ORDER BY sắp xếp kết quả.
9. LIMIT giới hạn số hàng trả về.

Đây là thứ tự logic để suy luận semantics, không phải thứ tự vật lý mà optimizer bắt buộc phải thực hiện. MySQL có thể đẩy điều kiện, đổi thứ tự join, dùng index hoặc materialize để giảm chi phí, miễn giữ kết quả đúng.

### 1.1. WHERE lọc hàng, HAVING lọc nhóm

WHERE lọc hàng trước khi GROUP BY:

~~~sql
SELECT customer_id, SUM(amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Chỉ các đơn PAID tham gia tính tổng.

HAVING lọc nhóm sau khi aggregate:

~~~sql
SELECT customer_id, SUM(amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) >= 10000000;
~~~

Truy vấn chỉ giữ khách hàng có tổng doanh thu PAID đạt ngưỡng.

Không đưa điều kiện aggregate như SUM(amount) >= ... vào WHERE. Ngược lại, điều kiện chỉ phụ thuộc từng hàng như status = 'PAID' nên đặt ở WHERE để loại hàng sớm và giúp optimizer tận dụng index.

### 1.2. Điều kiện nhóm không cần aggregate

Nếu một điều kiện chỉ phụ thuộc cột nhóm và không cần aggregate, thường nên đặt trong WHERE:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id >= 100
GROUP BY customer_id;
~~~

Viết HAVING customer_id >= 100 có thể vẫn được MySQL xử lý, nhưng WHERE diễn đạt đúng việc lọc hàng đầu vào và có thể giảm số hàng phải nhóm.

## 2. GROUP BY và các hàm aggregate

GROUP BY gom các hàng có cùng giá trị của biểu thức nhóm thành một nhóm. Mỗi nhóm tạo ra một hàng kết quả; các hàm aggregate tính giá trị trên các hàng thuộc nhóm đó.

Ví dụ:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue,
    AVG(total_amount) AS average_order,
    MIN(created_at) AS first_order_at,
    MAX(created_at) AS last_order_at
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Mỗi customer_id có một hàng kết quả với số đơn, tổng tiền, giá trị trung bình và khoảng thời gian đặt đơn.

### 2.1. COUNT(*), COUNT(column) và COUNT(DISTINCT column)

| Biểu thức | Ý nghĩa |
|---|---|
| COUNT(*) | Đếm tất cả hàng trong nhóm |
| COUNT(column) | Đếm hàng có column khác NULL |
| COUNT(DISTINCT column) | Đếm các giá trị column khác NULL, không trùng |

Ví dụ:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(referrer_id) AS rows_with_referrer,
    COUNT(DISTINCT referrer_id) AS unique_referrers
FROM visits;
~~~

Nếu có 100 hàng, trong đó 20 hàng referrer_id là NULL và 10 giá trị referrer_id bị lặp, ba kết quả sẽ khác nhau. Chọn hàm theo câu hỏi nghiệp vụ, không thay COUNT(*) bằng COUNT(column) nếu cột có thể NULL.

### 2.2. SUM và AVG bỏ qua NULL

SUM(expr) và AVG(expr) bỏ qua giá trị NULL. Nếu không có giá trị khác NULL, kết quả có thể là NULL. COUNT(*) vẫn đếm hàng ngay cả khi các cột trong hàng chứa NULL.

~~~sql
SELECT
    COUNT(*) AS row_count,
    COUNT(discount_amount) AS discount_count,
    SUM(discount_amount) AS total_discount,
    AVG(discount_amount) AS average_discount
FROM order_items;
~~~

Không tự thay NULL bằng 0 nếu NULL có ý nghĩa "chưa biết" hoặc "không áp dụng". Nếu nghiệp vụ xác định NULL tương đương 0, có thể dùng COALESCE một cách rõ ràng.

### 2.3. DISTINCT bên trong aggregate

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT product_id) AS unique_products
FROM order_items
GROUP BY customer_id;
~~~

COUNT(DISTINCT product_id) đếm số sản phẩm khác nhau trong nhóm, không phải số dòng order_items. Nó có thể cần bộ nhớ hoặc temporary structure để nhận diện duplicate; hãy đánh giá trên dữ liệu thực tế.

### 2.4. Aggregate không có GROUP BY

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID';
~~~

Không có GROUP BY, aggregate áp dụng trên toàn bộ tập hàng còn lại và trả một hàng kết quả, kể cả khi tập đầu vào rỗng, với các giá trị aggregate theo semantics tương ứng.

## 3. ONLY_FULL_GROUP_BY và cột không được nhóm

Một lỗi phổ biến là SELECT cột không nằm trong GROUP BY và cũng không được aggregate:

~~~sql
SELECT customer_id, order_status, SUM(total_amount)
FROM orders
GROUP BY customer_id;
~~~

Nếu một customer có nhiều order_status, MySQL không thể tự hiểu cần chọn trạng thái nào. Khi ONLY_FULL_GROUP_BY được bật, truy vấn này bị từ chối trừ khi MySQL xác định được functional dependency phù hợp.

Kiểm tra SQL mode:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### 3.1. Functional dependency

MySQL có thể cho phép cột không nằm trong GROUP BY nếu cột đó phụ thuộc hàm vào các cột nhóm. Ví dụ, customer_id là primary key của customers nên full_name được xác định duy nhất bởi customer_id:

~~~sql
SELECT c.customer_id, c.full_name, COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

MySQL có thể nhận diện full_name phụ thuộc vào primary key customer_id. Quy tắc phụ thuộc hàm được MySQL nhận diện có giới hạn và phụ thuộc cấu trúc khóa, join và biểu thức; không giả định mọi quan hệ nghiệp vụ đều được optimizer chứng minh.

### 3.2. ANY_VALUE không sửa được logic mơ hồ

Có thể dùng ANY_VALUE(order_status) để nói rõ rằng một giá trị bất kỳ trong nhóm là chấp nhận được:

~~~sql
SELECT
    customer_id,
    ANY_VALUE(order_status) AS sample_status,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
~~~

ANY_VALUE không chọn trạng thái mới nhất, phổ biến nhất hay có ưu tiên cao nhất. Nếu cần một hàng cụ thể, hãy định nghĩa quy tắc bằng aggregate phù hợp, subquery hoặc window function.

### 3.3. Không tắt ONLY_FULL_GROUP_BY để che truy vấn sai

Tắt SQL mode có thể khiến MySQL chọn một giá trị không xác định từ nhóm. Kết quả có thể thay đổi khi execution plan, index hoặc dữ liệu thay đổi. Hãy sửa câu truy vấn để xác định rõ giá trị cần trả về.

## 4. DISTINCT loại trùng ở mức kết quả

SELECT DISTINCT loại bỏ các hàng có cùng giá trị trên toàn bộ danh sách biểu thức SELECT:

~~~sql
SELECT DISTINCT customer_id
FROM orders;
~~~

Mỗi customer_id xuất hiện một lần trong kết quả. DISTINCT không có nghĩa là "chỉ lấy hàng đầu tiên" và cũng không xác định hàng đại diện nếu SELECT thêm những cột khác nhau.

Ví dụ:

~~~sql
SELECT DISTINCT customer_id, status
FROM orders;
~~~

Khách hàng có hai status khác nhau vẫn xuất hiện hai hàng vì cặp (customer_id, status) khác nhau.

### 4.1. DISTINCT và GROUP BY

Hai truy vấn sau có thể tạo cùng tập customer_id:

~~~sql
SELECT DISTINCT customer_id
FROM orders;

SELECT customer_id
FROM orders
GROUP BY customer_id;
~~~

Khi chỉ cần loại trùng, DISTINCT thường thể hiện ý định rõ hơn. GROUP BY phù hợp khi cần aggregate hoặc logic nhóm.

Không có bảo đảm thứ tự kết quả nếu không có ORDER BY, kể cả khi GROUP BY hoặc DISTINCT được thực hiện bằng index.

### 4.2. DISTINCT sau JOIN có thể che vấn đề

~~~sql
SELECT DISTINCT c.customer_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Nếu mục tiêu chỉ là khách hàng có đơn hàng, viết EXISTS thường trực tiếp hơn:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

DISTINCT có thể che việc JOIN tạo quá nhiều hàng do quan hệ một-nhiều. Nếu cần cột hoặc aggregate từ bảng orders, hãy xác định rõ cardinality và nhóm trước khi kết hợp.

### 4.3. DISTINCT và NULL

Trong kết quả DISTINCT, các giá trị NULL được xem là duplicate với nhau cho mục đích loại trùng. Ví dụ, nếu cột region_id có nhiều NULL, SELECT DISTINCT region_id chỉ trả một hàng NULL.

Điều này khác với phép so sánh bằng thông thường giữa NULL và NULL, vốn cho kết quả UNKNOWN.

## 5. DISTINCT và ORDER BY

Nếu cần kết quả duy nhất theo một tập cột và sắp xếp, hãy xác định rõ thứ tự dựa trên các biểu thức có ý nghĩa với kết quả.

Ví dụ:

~~~sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY customer_id;
~~~

Nếu muốn sắp xếp theo cột không có trong danh sách SELECT:

~~~sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY created_at DESC;
~~~

Truy vấn này không xác định rõ created_at nào đại diện cho một customer_id có nhiều đơn. MySQL có thể từ chối một số dạng DISTINCT/ORDER BY mơ hồ để tránh kết quả không xác định.

Nếu yêu cầu là mỗi khách hàng kèm thời điểm đặt đơn mới nhất, hãy tính MAX(created_at) hoặc chọn hàng mới nhất bằng window function:

~~~sql
SELECT customer_id, MAX(created_at) AS last_order_at
FROM orders
GROUP BY customer_id
ORDER BY last_order_at DESC;
~~~

Không dùng DISTINCT để chọn ngẫu nhiên một hàng rồi hy vọng ORDER BY tìm ra hàng mới nhất.

## 6. Conditional aggregation cho báo cáo nhiều chỉ tiêu

Conditional aggregation tính nhiều chỉ tiêu trong một lần GROUP BY bằng SUM(CASE...), COUNT(CASE...) hoặc biểu thức tương đương.

Ví dụ báo cáo đơn theo trạng thái:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_orders,
    SUM(CASE WHEN status = 'PAID' THEN total_amount ELSE 0 END) AS paid_revenue
FROM orders
GROUP BY customer_id;
~~~

Một lần đọc tập orders có thể tạo nhiều chỉ tiêu thay vì chạy nhiều truy vấn riêng rồi ghép kết quả.

### 6.1. SUM(CASE...) và COUNT(CASE...)

Có thể viết:

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
~~~

COUNT bỏ qua NULL, nên chỉ đếm hàng mà CASE trả về 1. Tương đương về mục tiêu với:

~~~sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
~~~

Với COUNT, không cần ELSE 0 vì COUNT(0) vẫn đếm giá trị 0. Với SUM, cần cân nhắc ELSE 0 và hành vi khi không có hàng đầu vào.

### 6.2. Báo cáo theo tháng

~~~sql
SELECT
    DATE_FORMAT(created_at, '%Y-%m') AS order_month,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01'
  AND status = 'PAID'
GROUP BY DATE_FORMAT(created_at, '%Y-%m')
ORDER BY order_month;
~~~

Điều kiện WHERE dùng khoảng ngày trực tiếp trên created_at để có cơ hội tận dụng index. Biểu thức DATE_FORMAT chỉ dùng để tạo khóa nhóm và nhãn báo cáo.

### 6.3. Chuyển điều kiện báo cáo vào aggregate khi cần giữ mọi nhóm

Nếu muốn báo cáo tất cả khách hàng, kể cả khách hàng không có đơn PAID, không đặt status = 'PAID' trong WHERE sau LEFT JOIN vì điều đó có thể loại hàng NULL phía orders:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS all_orders,
    SUM(CASE WHEN o.status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN o.status = 'PAID' THEN o.total_amount ELSE 0 END) AS paid_revenue
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

Điều kiện trạng thái nằm trong CASE để giữ nhóm khách hàng không có đơn. COUNT(o.order_id) đếm đơn thực tế vì order_id là khóa chính NOT NULL; COUNT(*) sẽ đếm cả hàng NULL mở rộng từ LEFT JOIN.

## 7. JOIN và cardinality trước khi aggregate

Một truy vấn báo cáo có thể sai số liệu nếu JOIN tạo nhiều bản sao của một hàng trước khi SUM hoặc COUNT.

Giả sử:

- Một customer có nhiều orders.
- Một order có nhiều order_items.
- Mỗi order có một khoản shipping_fee được lưu ở bảng orders.

Truy vấn:

~~~sql
SELECT
    o.customer_id,
    SUM(o.shipping_fee) AS shipping_total,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
GROUP BY o.customer_id;
~~~

shipping_fee bị lặp theo số order_items của mỗi đơn. Tổng shipping có thể bị nhân lên. DISTINCT trên kết quả cuối không sửa được aggregate đã tính sai.

### 7.1. Aggregate trước khi JOIN

Nếu cần tổng shipping theo customer và tổng item theo customer, có thể tổng hợp riêng:

~~~sql
SELECT
    o.customer_id,
    SUM(o.shipping_fee) AS shipping_total
FROM orders AS o
GROUP BY o.customer_id;
~~~

Và:

~~~sql
SELECT
    o.customer_id,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
GROUP BY o.customer_id;
~~~

Nếu cần ghép cả hai chỉ tiêu trong một kết quả:

~~~sql
SELECT
    s.customer_id,
    s.shipping_total,
    i.item_total
FROM (
    SELECT customer_id, SUM(shipping_fee) AS shipping_total
    FROM orders
    GROUP BY customer_id
) AS s
JOIN (
    SELECT o.customer_id,
           SUM(oi.quantity * oi.unit_price) AS item_total
    FROM orders AS o
    JOIN order_items AS oi
      ON oi.order_id = o.order_id
    GROUP BY o.customer_id
) AS i
  ON i.customer_id = s.customer_id;
~~~

Nếu cần giữ khách hàng không có item hoặc không có đơn, chọn LEFT JOIN và COALESCE theo quy tắc nghiệp vụ. Derived table có aggregate thường cần materialization; chi phí đọc orders nhiều lần cũng cần được cân nhắc. Có thể tối ưu bằng cách thiết kế báo cáo hoặc summary table khi workload phù hợp.

### 7.2. COUNT sau LEFT JOIN

Với LEFT JOIN, nếu khách hàng không có đơn:

- COUNT(*) đếm hàng mở rộng NULL, thường là 1.
- COUNT(o.order_id) trả 0 vì order_id NULL ở hàng mở rộng.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

Đối với báo cáo số đơn, COUNT(o.order_id) thường là biểu thức đúng nếu order_id NOT NULL.

## 8. GROUP BY và composite index

Index có thể giúp lọc hàng, cung cấp thứ tự phù hợp cho nhóm hoặc bao phủ các cột cần đọc. Nhưng index chỉ có ích nếu thứ tự cột và điều kiện truy vấn tương thích.

Giả sử báo cáo:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

Một index cần đánh giá:

~~~sql
CREATE INDEX ix_orders_status_date_customer
ON orders (status, created_at, customer_id);
~~~

Index bắt đầu bằng equality status, sau đó range created_at. customer_id nằm sau range nên không nhất thiết cung cấp thứ tự nhóm tối ưu; tuy nhiên index có thể hỗ trợ lọc và chứa customer_id để giảm đọc clustered record tùy plan.

### 8.1. Equality, range và GROUP BY

Thứ tự cột index thường được thiết kế theo:

1. Các điều kiện equality có tính chọn lọc và xuất hiện ổn định.
2. Cột range dùng để giới hạn khoảng đọc.
3. Cột nhóm hoặc sắp xếp nếu thứ tự và access path cho phép.
4. Cột chỉ cần đọc để có covering index nếu lợi ích lớn hơn chi phí.

Đây là nguyên tắc để bắt đầu thử nghiệm, không phải quy tắc cứng. Một index (status, customer_id, created_at) có thể giúp nhóm theo customer_id sau equality status, nhưng điều kiện range ngày nằm sau customer_id nên có thể phải đọc nhiều hơn. Index (status, created_at, customer_id) lọc ngày tốt hơn nhưng có thể cần bước nhóm/sort. Hãy so sánh bằng EXPLAIN và dữ liệu thật.

### 8.2. Index hỗ trợ GROUP BY

Nếu các cột nhóm tạo thành leftmost prefix của index và access path có thể đọc theo thứ tự đó, MySQL có thể tận dụng index để giảm công việc sắp xếp hoặc nhóm. Một số trường hợp đủ điều kiện có thể dùng Loose Index Scan, thể hiện bằng Using index for group-by trong EXPLAIN truyền thống.

Không phải mọi GROUP BY trên index đều tránh được temporary table hoặc filesort. Điều kiện lọc, aggregate, thứ tự cột và loại truy vấn quyết định khả năng tận dụng index.

### 8.3. Loose Index Scan

Loose Index Scan có thể nhảy qua các nhóm giá trị trong một index thay vì đọc mọi key trong nhóm, nhưng chỉ áp dụng cho một số query shape, thường liên quan GROUP BY trên prefix index và aggregate MIN/MAX hoặc một số dạng DISTINCT. Nó có nhiều điều kiện về index và biểu thức.

Đừng thiết kế query dựa trên giả định MySQL luôn dùng Loose Index Scan. Kiểm tra Using index for group-by và plan thực tế.

### 8.4. Covering index

Một index là covering cho truy vấn khi tất cả cột cần đọc có sẵn trong index. Với báo cáo chỉ lấy customer_id và COUNT(*), một index phù hợp có thể giảm việc đọc clustered record. Nếu cần SUM(total_amount), total_amount phải có trong index để bao phủ, nhưng thêm cột này làm index rộng và tăng chi phí ghi.

Đừng thêm quá nhiều cột chỉ để ép covering. So sánh số lần truy cập bảng, kích thước index, buffer pool và workload ghi.

## 9. DISTINCT và index

SELECT DISTINCT column có thể tận dụng index nếu index cung cấp thứ tự phù hợp và giá trị có thể được đọc hiệu quả. Tuy nhiên, nếu chọn nhiều cột hoặc có biểu thức, MySQL có thể cần temporary table hoặc bước duplicate elimination.

~~~sql
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
~~~

Index (status, customer_id) có thể hỗ trợ equality filter theo status và các customer_id liên tiếp theo index order. Tùy thống kê và số hàng, optimizer có thể chọn index scan hoặc cách khác.

### 9.1. DISTINCT nhiều cột

~~~sql
SELECT DISTINCT customer_id, status
FROM orders;
~~~

Index (customer_id, status) có thể cung cấp các cặp theo thứ tự, nhưng việc dùng index có lợi hay không còn phụ thuộc số hàng, độ rộng index và tỷ lệ duplicate.

### 9.2. COUNT(DISTINCT)

~~~sql
SELECT COUNT(DISTINCT customer_id)
FROM orders
WHERE status = 'PAID';
~~~

Đây là phép đếm giá trị khác nhau, không tương đương COUNT(*). Với nhiều giá trị trùng, engine cần xác định duplicate; index phù hợp có thể giúp nhưng không bảo đảm bỏ qua toàn bộ chi phí.

### 9.3. DISTINCT không phải công cụ sửa JOIN sai

Nếu truy vấn có nhiều JOIN một-nhiều và cần tổng tiền, thêm DISTINCT ở ngoài không sửa aggregate đã nhân bản. Hãy xác định grain của từng bảng và aggregate đúng cấp trước khi kết hợp.

## 10. Báo cáo nhiều cấp với WITH ROLLUP

MySQL hỗ trợ WITH ROLLUP để thêm các hàng tổng phụ và tổng cuối cho GROUP BY:

~~~sql
SELECT
    region_id,
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY region_id, customer_id WITH ROLLUP;
~~~

Kết quả gồm:

- Tổng theo từng cặp region_id/customer_id.
- Hàng subtotal theo region_id khi customer_id được cuộn lên.
- Hàng grand total khi cả hai cấp được cuộn.

Các hàng tổng hợp được biểu diễn bằng NULL ở các cột nhóm đã được cuộn. Nếu dữ liệu gốc cũng cho phép NULL, cần phân biệt hàng subtotal với NULL thật bằng GROUPING():

~~~sql
SELECT
    region_id,
    customer_id,
    GROUPING(region_id) AS region_is_total,
    GROUPING(customer_id) AS customer_is_total,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY region_id, customer_id WITH ROLLUP;
~~~

GROUPING(expr) giúp nhận biết NULL được tạo bởi rollup. ROLLUP tạo thêm hàng aggregate, vì vậy cần tính đến số nhóm và chi phí tổng hợp; không dùng nếu báo cáo chỉ cần một cấp nhóm.

## 11. Top-N theo nhóm: GROUP BY hay window function?

GROUP BY trả một hàng cho mỗi nhóm, nhưng không giữ lại toàn bộ hàng chi tiết. Nếu cần top 3 đơn mới nhất cho mỗi khách hàng, aggregate MAX(created_at) không đủ để lấy các cột của đúng ba đơn.

Dùng window function:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        created_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
SELECT order_id, customer_id, created_at, total_amount
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, created_at DESC, order_id DESC;
~~~

Window function giữ từng hàng và gán thứ hạng trong nhóm. GROUP BY phù hợp khi cần một kết quả tổng hợp mỗi nhóm; window function phù hợp khi cần giữ hàng chi tiết và tính thứ hạng hoặc aggregate theo cửa sổ.

### 11.1. MAX và hàng tương ứng

~~~sql
SELECT customer_id, MAX(created_at)
FROM orders
GROUP BY customer_id;
~~~

Truy vấn chỉ trả thời điểm lớn nhất, không tự trả order_id của hàng có thời điểm đó. Nếu cần hàng tương ứng, dùng window function hoặc join lại với aggregate và xử lý trường hợp nhiều hàng cùng timestamp.

## 12. LIMIT và phân trang báo cáo

LIMIT sau GROUP BY/ORDER BY chỉ giới hạn số nhóm kết quả được trả về; nó không nhất thiết làm MySQL chỉ đọc số hàng đầu vào tương ứng.

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

MySQL vẫn phải xử lý đủ dữ liệu cần thiết để tính doanh thu của các nhóm trước khi xác định top 20, trừ khi optimizer có thể áp dụng một tối ưu cụ thể theo cấu trúc truy vấn.

### 12.1. ORDER BY aggregate

Sắp xếp theo SUM/COUNT thường cần tính aggregate của các nhóm rồi sắp xếp. Index trên cột gốc không thể trực tiếp chứa tổng doanh thu động của mỗi customer nếu không có summary table hoặc giá trị được duy trì riêng.

### 12.2. Offset lớn

LIMIT 20 OFFSET 100000 có thể phải tạo và bỏ qua rất nhiều hàng sau khi sắp xếp. Với báo cáo lớn, cân nhắc keyset pagination theo khóa sắp xếp ổn định hoặc bảng tổng hợp đã lưu.

Nếu sắp xếp theo revenue aggregate, keyset pagination cần định nghĩa tie-breaker ổn định và có thể phải tính aggregate trước. Không thay offset bằng điều kiện đơn giản nếu thứ tự không duy nhất.

## 13. Tối ưu điều kiện lọc cho báo cáo

Giảm số hàng đầu vào trước khi nhóm thường có tác động lớn hơn việc thay đổi cách viết aggregate.

### 13.1. Dùng khoảng thời gian thay vì hàm trên cột lọc

Không nên:

~~~sql
WHERE DATE(created_at) = '2026-02-12'
~~~

Nếu muốn lọc theo ngày, hãy viết:

~~~sql
WHERE created_at >= '2026-02-12 00:00:00'
  AND created_at < '2026-02-13 00:00:00'
~~~

Điều kiện nửa mở cho phép index range scan trên created_at khi có index phù hợp và tránh phụ thuộc độ chính xác phần giây.

### 13.2. Lọc trước rồi mới aggregate

~~~sql
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

Đặt điều kiện status và khoảng ngày trong WHERE để giảm tập hàng cần nhóm. Nếu cần giữ cả khách hàng không có đơn, hãy bắt đầu từ customers và đặt điều kiện phía orders trong ON hoặc CASE tùy yêu cầu.

### 13.3. Tránh chuyển đổi kiểu dữ liệu trên cột index

Nếu customer_id là BIGINT, tránh so sánh bằng một chuỗi có định dạng khác nếu có thể gây implicit conversion trên cột. Dùng parameter đúng kiểu từ ứng dụng để optimizer có thể tận dụng index tốt hơn.

### 13.4. Kiểm tra selectivity

Điều kiện status = 'PAID' có thể không chọn lọc nếu phần lớn đơn đều PAID. Một index chỉ trên status có thể không hiệu quả. Kết hợp với khoảng thời gian hoặc customer_id có thể phù hợp hơn. Dùng thống kê và EXPLAIN để đánh giá, không suy ra selectivity chỉ từ số lượng giá trị khác nhau.

## 14. Đọc EXPLAIN cho GROUP BY và DISTINCT

Dùng EXPLAIN để biết MySQL đọc bao nhiêu hàng ước lượng, dùng index nào và có bước sắp xếp hoặc temporary table không.

### 14.1. EXPLAIN dạng tabular

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

Quan sát:

- type: cách truy cập bảng.
- possible_keys và key: index có thể dùng và index được chọn.
- rows: số hàng ước lượng đọc.
- filtered: tỷ lệ ước lượng còn lại sau điều kiện lọc.
- Extra: có thể hiển thị Using temporary, Using filesort hoặc Using index for group-by.

### 14.2. Using temporary

Using temporary cho biết kế hoạch cần một temporary table cho một phần xử lý. Nó không tự động có nghĩa dữ liệu đã ghi ra đĩa hoặc truy vấn chắc chắn chậm. Temporary table có thể ở memory hoặc chuyển sang disk tùy kích thước và giới hạn.

Xác định temporary table phục vụ GROUP BY, DISTINCT, derived table hay một thao tác khác. Đánh giá kích thước dữ liệu và thời gian thực tế trước khi thay đổi.

### 14.3. Using filesort

Using filesort chỉ ra MySQL dùng thuật toán sort bổ sung thay vì lấy kết quả theo thứ tự index trực tiếp. Tên gọi không khẳng định dữ liệu chắc chắn được sort trên đĩa; thuật toán có thể dùng bộ nhớ hoặc tệp tạm tùy kích thước và cấu hình.

ORDER BY aggregate thường cần sort sau khi nhóm. Đừng tạo index trên cột gốc với kỳ vọng nó tự sắp xếp được giá trị SUM động.

### 14.4. Using index for group-by

Trong một số query shape, EXPLAIN có thể hiển thị Using index for group-by, thường liên quan Loose Index Scan. Đây là dấu hiệu MySQL có thể tận dụng index để đọc nhóm hiệu quả hơn. Không phải mọi GROUP BY dùng index đều có Extra này.

### 14.5. EXPLAIN FORMAT=JSON

~~~sql
EXPLAIN FORMAT=JSON
SELECT customer_id, COUNT(DISTINCT product_id)
FROM order_items
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

JSON có thể cung cấp thông tin về temporary table, grouping operation, cost estimate, access path và số hàng dự kiến. Cấu trúc output phụ thuộc phiên bản và query plan.

### 14.6. EXPLAIN ANALYZE

Trên MySQL 8.0.18 trở lên:

~~~sql
EXPLAIN ANALYZE
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE thực thi SELECT và hiển thị actual rows, loops cùng thời gian iterator. So sánh ước lượng với thực tế để tìm nơi cardinality lệch hoặc bước aggregate/sort tốn thời gian. Chạy trên dữ liệu đại diện và đánh giá tải trước khi dùng với báo cáo nặng.

## 15. Statistics và histogram ảnh hưởng đến báo cáo

Optimizer dùng thống kê index và phân bố dữ liệu để ước lượng số hàng. Nếu thống kê cũ hoặc dữ liệu lệch, optimizer có thể chọn index không phù hợp, thứ tự join kém hoặc access path tốn kém.

### 15.1. Cập nhật thống kê

~~~sql
ANALYZE TABLE orders;
~~~

ANALYZE TABLE cập nhật thống kê cho optimizer. Thực hiện sau các thay đổi dữ liệu lớn khi có bằng chứng estimates lệch, đồng thời đánh giá chi phí và tác động trên môi trường thực tế.

### 15.2. Histogram cho cột có phân bố lệch

Nếu một cột lọc không có index phù hợp nhưng phân bố dữ liệu lệch, histogram có thể giúp optimizer ước lượng selectivity:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 8 BUCKETS;
~~~

Histogram không thay thế index và không phải lúc nào cũng cải thiện plan. Kiểm tra estimate trước/sau và quan sát workload.

### 15.3. So sánh estimated với actual

Nếu EXPLAIN ước lượng 100 hàng nhưng EXPLAIN ANALYZE cho thấy 100.000 hàng, optimizer có thể chọn chiến lược grouping/join không phù hợp. Tìm nguyên nhân như skew, correlation giữa cột, histogram thiếu hoặc statistics stale.

## 16. Summary table cho báo cáo lặp lại

Nếu báo cáo tổng hợp toàn lịch sử chạy liên tục, việc tính lại GROUP BY trên hàng tỷ dòng mỗi lần có thể không phù hợp. Có thể duy trì bảng tổng hợp theo ngày/tenant/customer:

~~~sql
CREATE TABLE daily_customer_revenue (
    report_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    paid_order_count BIGINT NOT NULL,
    paid_revenue DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (report_date, customer_id),
    KEY ix_daily_customer (customer_id, report_date)
) ENGINE=InnoDB;
~~~

Báo cáo tháng có thể tổng hợp từ bảng daily:

~~~sql
SELECT
    customer_id,
    SUM(paid_order_count) AS paid_order_count,
    SUM(paid_revenue) AS paid_revenue
FROM daily_customer_revenue
WHERE report_date >= '2026-01-01'
  AND report_date < '2026-02-01'
GROUP BY customer_id;
~~~

Summary table giảm khối lượng đọc ở thời điểm truy vấn nhưng thêm chi phí cập nhật, đồng bộ, xử lý late-arriving data và sửa sai dữ liệu. Cần xác định nguồn dữ liệu chuẩn, cách cập nhật idempotent và quy trình rebuild.

### 16.1. Incremental aggregation

Có thể cập nhật summary table trong cùng transaction với dữ liệu nguồn nếu workload và tính nhất quán cho phép. Nếu cập nhật bất đồng bộ, cần cơ chế event/outbox, retry và reconciliation để tránh bỏ sót hoặc cộng trùng.

### 16.2. Khi nào không cần summary table?

Nếu báo cáo chạy ít, dữ liệu vừa phải hoặc cần dữ liệu mới nhất tuyệt đối, truy vấn trực tiếp có thể đơn giản và đáng tin cậy hơn. Đừng thêm một tầng dữ liệu dẫn xuất nếu chi phí vận hành lớn hơn lợi ích.

## 17. Quy trình tối ưu GROUP BY, DISTINCT và báo cáo

Một quy trình có thể lặp lại:

1. Viết rõ grain của kết quả: một hàng cho mỗi customer, ngày, sản phẩm hay nhóm nào.
2. Xác định aggregate cần tính và quy tắc NULL.
3. Kiểm tra JOIN có làm nhân bản hàng trước aggregate không.
4. Đặt điều kiện lọc hàng trong WHERE và điều kiện aggregate trong HAVING.
5. Dùng EXISTS nếu chỉ cần kiểm tra sự tồn tại; tránh JOIN rồi DISTINCT không cần thiết.
6. Kiểm tra ONLY_FULL_GROUP_BY và functional dependency.
7. Thiết kế index theo equality, range, grouping, ordering và covering needs.
8. Chạy EXPLAIN và đọc partitions, key, rows, filtered, Extra.
9. Chạy EXPLAIN ANALYZE trên dữ liệu đại diện để đo actual rows, loops và thời gian.
10. Kiểm tra statistics, histogram và độ lệch dữ liệu nếu estimate sai.
11. Cân nhắc summary table nếu cùng báo cáo nặng được tính lặp lại thường xuyên.
12. Đo lại cả latency đọc lẫn chi phí ghi/dung lượng sau thay đổi.

## 18. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đặt điều kiện cột thường trong HAVING | Nhóm nhiều hàng không cần thiết | Chuyển điều kiện hàng sang WHERE |
| Đưa aggregate vào WHERE | SQL không hợp lệ hoặc sai cấu trúc | Dùng HAVING hoặc derived query |
| SELECT cột không nhóm và không aggregate | Kết quả mơ hồ hoặc lỗi ONLY_FULL_GROUP_BY | Nhóm, aggregate hoặc xác định functional dependency |
| Dùng ANY_VALUE để chọn hàng mới nhất | Chọn giá trị bất kỳ | Dùng MAX + join hoặc window function |
| JOIN một-nhiều rồi SUM cột ở phía một | Tổng bị nhân bản | Aggregate đúng grain trước khi JOIN |
| COUNT(*) sau LEFT JOIN để đếm con | Hàng cha không có con có thể bị đếm là 1 | COUNT khóa NOT NULL của bảng con |
| Dùng DISTINCT để che duplicate do JOIN | Tốn tài nguyên và che sai cardinality | Sửa JOIN hoặc dùng EXISTS |
| Dùng NOT IN khi subquery có NULL | Kết quả UNKNOWN bị loại | Dùng NOT EXISTS hoặc xử lý NULL có chủ đích |
| Dùng hàm trên cột ngày trong WHERE | Có thể mất range access | Dùng khoảng thời gian nửa mở |
| Thêm index theo cảm tính | Tăng chi phí ghi và dung lượng | Kiểm tra query workload và EXPLAIN |
| Nghĩ Using filesort chắc chắn sort trên disk | Chẩn đoán sai | Đo thời gian và kích thước sort thực tế |
| Nghĩ LIMIT 20 chỉ đọc 20 hàng đầu vào | Báo cáo vẫn phải aggregate/sort nhiều dữ liệu | Giảm tập đầu vào hoặc dùng summary table phù hợp |
| Dùng GROUP BY thay window function cho top-N | Mất thông tin hàng chi tiết | Dùng ROW_NUMBER/RANK theo nhóm |
| Tắt ONLY_FULL_GROUP_BY để truy vấn chạy | Kết quả không xác định | Viết truy vấn có semantics rõ |

## 19. Bài thực hành: tối ưu báo cáo doanh thu khách hàng

Thực hiện trong database lab MySQL 8.0. Tạo bảng riêng, nạp dữ liệu mẫu và so sánh truy vấn. Không chạy trên bảng production.

### 19.1. Tạo bảng

~~~sql
CREATE TABLE lab_customers (
    customer_id BIGINT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    region_id INT NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_status_date_customer (status, created_at, customer_id),
    KEY ix_lab_customer_status_date (customer_id, status, created_at)
) ENGINE=InnoDB;

CREATE TABLE lab_order_items (
    item_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (item_id),
    KEY ix_lab_items_order (order_id),
    KEY ix_lab_items_product (product_id)
) ENGINE=InnoDB;
~~~

### 19.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO lab_customers (customer_id, full_name, region_id)
VALUES
    (1, 'An', 10),
    (2, 'Binh', 10),
    (3, 'Chi', 20),
    (4, 'Dung', 20);

INSERT INTO lab_orders
    (order_id, customer_id, status, created_at, total_amount)
VALUES
    (101, 1, 'PAID', '2026-01-05 10:00:00', 100.00),
    (102, 1, 'PAID', '2026-01-10 11:00:00', 150.00),
    (103, 1, 'PENDING', '2026-01-12 12:00:00', 200.00),
    (104, 2, 'PAID', '2026-01-15 09:00:00', 300.00),
    (105, 3, 'CANCELLED', '2026-01-20 13:00:00', 80.00),
    (106, 3, 'PAID', '2026-02-02 14:00:00', 120.00);

INSERT INTO lab_order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES
    (1, 101, 501, 1, 60.00),
    (2, 101, 502, 2, 20.00),
    (3, 102, 501, 1, 150.00),
    (4, 103, 503, 1, 200.00),
    (5, 104, 501, 2, 150.00),
    (6, 106, 504, 1, 120.00);
~~~

### 19.3. Bước 1 — Báo cáo doanh thu theo khách hàng

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS paid_revenue,
    AVG(total_amount) AS average_order_value
FROM lab_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY paid_revenue DESC;
~~~

Kết quả mong đợi: customer 2 có doanh thu 300; customer 1 có hai đơn và doanh thu 250. Customer 3 không có đơn PAID trong tháng 1.

### 19.4. Bước 2 — Báo cáo tất cả khách hàng kể cả không có đơn

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total_amount), 0) AS paid_revenue
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
 AND o.created_at >= '2026-01-01'
 AND o.created_at < '2026-02-01'
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Điều kiện lọc orders nằm trong ON để giữ khách hàng không có đơn. COUNT(o.order_id) trả 0 cho hàng không có match.

### 19.5. Bước 3 — Phát hiện tổng bị nhân bản khi JOIN chi tiết

~~~sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS order_total,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM lab_orders AS o
JOIN lab_order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
~~~

Quan sát order_total: đơn 101 có hai item nên total_amount của đơn đó bị cộng hai lần. Đây là lỗi cardinality, không phải lỗi SUM.

### 19.6. Bước 4 — Tổng hợp đúng cấp

~~~sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS order_total
FROM lab_orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
~~~

Và tổng item:

~~~sql
SELECT
    o.customer_id,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM lab_orders AS o
JOIN lab_order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
~~~

So sánh hai kết quả. Nếu cần ghép, tổng hợp mỗi nguồn trước rồi JOIN theo customer_id.

### 19.7. Bước 5 — So sánh DISTINCT và EXISTS

~~~sql
SELECT DISTINCT c.customer_id
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

~~~sql
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Hai truy vấn diễn đạt danh sách khách hàng có đơn PAID. Đọc EXPLAIN để so sánh cách optimizer xử lý.

### 19.8. Bước 6 — Đọc EXPLAIN

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS paid_revenue
FROM lab_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY paid_revenue DESC;
~~~

Quan sát key, rows, filtered, Using temporary và Using filesort. Dữ liệu ít có thể khiến optimizer chọn scan; không đánh giá index chỉ từ bảng lab nhỏ.

### 19.9. Bước 7 — So sánh index access

~~~sql
SHOW INDEX FROM lab_orders;

EXPLAIN FORMAT=JSON
SELECT
    customer_id,
    SUM(total_amount)
FROM lab_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

Đối chiếu với index (status, created_at, customer_id) và (customer_id, status, created_at). Giải thích vì sao equality status rồi range created_at có thể lọc tốt nhưng không nhất thiết cung cấp thứ tự nhóm customer_id.

### 19.10. Bước 8 — Dọn bảng lab

~~~sql
DROP TABLE lab_order_items;
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Chỉ xóa ba bảng lab vừa tạo.

**Kết quả cần đạt:** viết báo cáo có WHERE/GROUP BY/HAVING đúng vị trí; phân biệt COUNT(*) và COUNT(column); tránh tổng bị nhân bản do JOIN; dùng DISTINCT hoặc EXISTS đúng mục tiêu; giải thích index và đọc EXPLAIN cho truy vấn báo cáo.

## 20. Nguyên tắc cần ghi nhớ

- WHERE lọc hàng trước GROUP BY; HAVING lọc nhóm sau aggregate.
- COUNT(*) đếm hàng; COUNT(column) bỏ qua NULL; COUNT(DISTINCT column) đếm giá trị khác NULL không trùng.
- SUM và AVG bỏ qua NULL; chỉ dùng COALESCE khi nghiệp vụ xác định NULL tương đương một giá trị thay thế.
- ONLY_FULL_GROUP_BY giúp ngăn chọn cột không xác định trong nhóm; functional dependency chỉ được MySQL nhận diện trong các trường hợp phù hợp.
- ANY_VALUE trả một giá trị bất kỳ, không phải giá trị mới nhất hay đại diện theo ưu tiên.
- DISTINCT loại duplicate trên toàn bộ tuple SELECT; nó không sửa aggregate đã sai do JOIN nhân bản.
- Khi chỉ cần biết có hàng khớp, EXISTS thường rõ hơn JOIN rồi DISTINCT.
- Trước khi aggregate nhiều bảng, xác định grain và cardinality; aggregate từng nguồn trước nếu JOIN làm nhân bản chỉ tiêu.
- Với LEFT JOIN, COUNT(*) có thể đếm hàng mở rộng NULL; COUNT khóa NOT NULL của bảng con thường phù hợp để đếm hàng match.
- Conditional aggregation tính nhiều chỉ tiêu trong một lần GROUP BY.
- Thiết kế composite index theo equality, range, grouping, ordering và covering needs; xác minh bằng EXPLAIN.
- Using temporary và Using filesort là dấu hiệu của bước xử lý bổ sung, không tự động chứng minh dữ liệu đã ghi ra đĩa hoặc truy vấn chậm.
- ORDER BY aggregate thường phải tính nhóm trước rồi sắp xếp; LIMIT không bảo đảm chỉ đọc một phần nhỏ dữ liệu đầu vào.
- Dùng window function khi cần top-N hàng chi tiết trong mỗi nhóm; dùng GROUP BY khi cần một hàng tổng hợp mỗi nhóm.
- ROLLUP tạo subtotal và grand total; GROUPING() giúp phân biệt NULL do rollup với NULL dữ liệu.
- Báo cáo lặp lại trên dữ liệu rất lớn có thể cần summary table, nhưng phải quản lý đồng bộ và tính idempotent.
- Dùng EXPLAIN ANALYZE để so sánh estimated và actual rows trên dữ liệu đại diện; cập nhật statistics khi có bằng chứng cần thiết.

Tối ưu báo cáo bắt đầu từ kết quả cần trả về và grain của dữ liệu. Khi WHERE giảm đúng tập đầu vào, JOIN giữ đúng cardinality, GROUP BY và DISTINCT được dùng đúng mục tiêu, index phù hợp với điều kiện lọc và nhóm, MySQL có thể xử lý ít dữ liệu hơn. Hãy luôn xác minh bằng execution plan và số liệu thực tế thay vì chỉ đổi cú pháp rồi giả định truy vấn đã nhanh hơn.
