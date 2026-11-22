# Lựa chọn chỉ mục từ truy vấn quan trọng và tập điều kiện thực tế

Chỉ mục (index) là một cấu trúc dữ liệu phụ giúp hệ quản trị cơ sở dữ liệu tìm, sắp xếp hoặc kiểm tra dữ liệu mà không phải đọc toàn bộ bảng trong mọi trường hợp. Nhưng thêm chỉ mục không đồng nghĩa hệ thống luôn nhanh hơn. Mỗi chỉ mục chiếm dung lượng, cần được cập nhật khi dữ liệu thay đổi, tiêu thụ cache và có thể làm tăng chi phí INSERT, UPDATE, DELETE. Một chỉ mục tốt phải phục vụ được những truy vấn quan trọng của workload thực tế với chi phí tổng thể chấp nhận được.

Trong chương **Thiết kế chỉ mục**, bài học này hướng dẫn lựa chọn chỉ mục từ các truy vấn quan trọng và tập điều kiện thực tế. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: tối ưu hiệu năng dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta bắt đầu từ truy vấn và điều kiện lọc mà ứng dụng thực sự sử dụng, sau đó mới quyết định loại chỉ mục, thứ tự cột, cột bao phủ và cách kiểm chứng.

Nguyên tắc xuyên suốt là thiết kế chỉ mục theo workload, không thiết kế theo cảm tính hoặc theo một câu SQL riêng lẻ. Một index chỉ đáng giữ khi lợi ích đo được cho các truy vấn quan trọng lớn hơn chi phí lưu trữ, bảo trì và ảnh hưởng lên các thao tác khác.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Thu thập và xếp hạng truy vấn quan trọng trước khi đề xuất chỉ mục.
- Đọc tập điều kiện lọc, điều kiện join, thứ tự sắp xếp và số cột trả về để xác định nhu cầu truy cập.
- Lựa chọn B-tree, chỉ mục ghép, covering index, partial index, expression index và các loại chỉ mục chuyên biệt theo kiểu dữ liệu.
- Xác định thứ tự cột trong chỉ mục ghép dựa trên equality, range, ORDER BY, prefix và khả năng tái sử dụng.
- Đánh giá selectivity, cardinality, phân bố dữ liệu và skew thay vì chỉ nhìn số giá trị phân biệt.
- Nhận diện chỉ mục trùng lặp, dư thừa hoặc ít được sử dụng.
- Cân bằng lợi ích đọc với chi phí ghi, dung lượng, cache và bảo trì.
- Kiểm chứng thiết kế bằng execution plan và đo tải trước/sau trên dữ liệu đại diện.

## 1. Bắt đầu từ workload, không bắt đầu từ danh sách cột

Một chỉ mục chỉ hữu ích khi nó hỗ trợ một hoặc nhiều mẫu truy vấn thực tế. Trước khi tạo index, cần hiểu ứng dụng đang đọc và ghi dữ liệu như thế nào.

Với mỗi nhóm truy vấn, thu thập tối thiểu:

- Câu SQL đã chuẩn hóa hoặc query fingerprint.
- Tần suất chạy và tổng thời gian tiêu thụ.
- Độ trễ trung bình cùng p95/p99 nếu có.
- Điều kiện WHERE và điều kiện JOIN.
- Các cột dùng trong ORDER BY, GROUP BY và DISTINCT.
- Các cột thực sự được SELECT.
- Số dòng ước lượng và số dòng thực tế.
- Số trang đọc, buffer hit, I/O và dữ liệu tạm.
- Các giá trị tham số phổ biến, hiếm và có phân bố lệch.
- Tác động của truy vấn đến transaction, lock và các workload khác.

Không phải truy vấn chậm nhất luôn là ưu tiên số một. Một truy vấn chạy 10 giây mỗi ngày có thể ít tác động hơn truy vấn chạy 5 ms nhưng lặp hàng trăm nghìn lần mỗi phút. Ngược lại, truy vấn hiếm nhưng phục vụ tác vụ nghiệp vụ quan trọng vẫn có thể cần ưu tiên. Cần kết hợp tài nguyên tiêu thụ, độ trễ người dùng và mức độ quan trọng của nghiệp vụ.

### 1.1. Lập danh mục truy vấn

Có thể phân nhóm workload theo mẫu truy cập:

| Nhóm truy vấn | Điều kiện thường gặp | Mục tiêu truy cập |
|---|---|---|
| Tra cứu theo khóa | id = ? | Tìm một dòng nhanh |
| Tra cứu theo tenant và trạng thái | tenant_id = ? AND status = ? | Tìm một nhóm dòng nhỏ |
| Lịch sử theo thời gian | tenant_id = ? AND created_at BETWEEN ... | Quét một khoảng có giới hạn |
| Danh sách có sắp xếp | status = ? ORDER BY created_at DESC | Lọc và trả kết quả đúng thứ tự |
| Join theo khóa ngoại | child.parent_id = parent.id | Tìm các dòng liên quan |
| Kiểm tra tồn tại | EXISTS (... WHERE key = ?) | Xác nhận có ít nhất một dòng |
| Báo cáo tổng hợp | WHERE date range GROUP BY category | Đọc nhiều dòng và tổng hợp |
| Tìm kiếm văn bản | text search trên nội dung | Tìm theo từ hoặc cụm từ |

Danh mục này là đầu vào để chọn chỉ mục. Không phải mọi nhóm đều cần index riêng. Có thể một chỉ mục ghép hỗ trợ nhiều truy vấn, hoặc optimizer đã chọn scan hiệu quả hơn index access cho một báo cáo đọc phần lớn bảng.

### 1.2. Chọn truy vấn mục tiêu

Giả sử hệ thống thương mại điện tử có ba truy vấn:

~~~sql
-- Q1: tra cứu một đơn hàng của một tenant.
SELECT order_id, status, total
FROM orders
WHERE tenant_id = 42
  AND order_id = 830154;

-- Q2: lấy các đơn đã thanh toán gần đây của một tenant.
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;

-- Q3: thống kê doanh thu theo trạng thái trong một khoảng thời gian.
SELECT status, SUM(total)
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00'
GROUP BY status;
~~~

Q1 là point lookup; Q2 kết hợp điều kiện bằng, thứ tự và giới hạn dòng; Q3 là range scan cộng aggregation. Chúng có thể cần những access path khác nhau. Trước khi tạo index, cần xem bảng đã có primary key hoặc index nào hỗ trợ Q1, Q2, Q3 chưa và kế hoạch hiện tại đọc bao nhiêu dữ liệu.

## 2. Đọc tập điều kiện của truy vấn

Mỗi truy vấn có thể sử dụng nhiều loại điều kiện. Phân loại chúng giúp xác định cột nào cần đứng đầu chỉ mục, cột nào dùng để xác định phạm vi, và cột nào chỉ cần để trả kết quả.

### 2.1. Điều kiện bằng (equality)

Ví dụ:

~~~sql
WHERE tenant_id = 42
  AND status = 'PAID'
~~~

Điều kiện bằng thường xác định một giá trị hoặc một nhóm khóa trong B-tree. Khi nhiều cột được so sánh bằng, chỉ mục ghép có thể đặt các cột này ở phần đầu, sau đó đến cột phạm vi hoặc sắp xếp.

Không có quy tắc phổ quát rằng cột có cardinality cao nhất luôn phải đứng đầu. Thứ tự còn phụ thuộc:

- Những truy vấn khác có dùng prefix của chỉ mục không.
- Cột nào luôn có mặt trong điều kiện.
- Phân bố giá trị và skew.
- Các cột có được lọc độc lập hay theo tổ hợp.
- Có cần hỗ trợ ORDER BY hoặc GROUP BY không.
- Optimizer của DBMS có skip scan hoặc kỹ thuật tương tự không.

### 2.2. Điều kiện phạm vi (range)

Ví dụ:

~~~sql
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00'
~~~

Trong B-tree ghép, sau khi xác định prefix bằng, cột range thường xác định vùng liên tiếp cần quét. Các cột đứng sau cột range thường ít có khả năng thu hẹp thêm vùng tìm kiếm theo cách đơn giản, dù vẫn có thể giúp lọc tại index hoặc phục vụ thứ tự trong một số tình huống.

Vì vậy, mẫu thường gặp là các cột equality trước, cột range sau. Nhưng vẫn cần xem ORDER BY, truy vấn khác và khả năng của DBMS trước khi quyết định.

### 2.3. Điều kiện JOIN

Ví dụ:

~~~sql
SELECT o.order_id, i.product_id, i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42;
~~~

Chỉ mục trên order_items(order_id) có thể giúp tìm các dòng chi tiết theo từng đơn hàng. Nếu truy vấn còn lọc theo product_id hoặc sắp xếp theo một cột khác, có thể cân nhắc chỉ mục ghép phù hợp với mẫu truy cập.

Primary key ở bảng được tham chiếu thường đã có index. Nhưng nhiều DBMS không tự động tạo index ở phía cột khóa ngoại của bảng con. Nếu workload thường xuyên join hoặc xóa/cập nhật bản ghi cha, cần kiểm tra index phía bảng con và yêu cầu của DBMS.

### 2.4. Điều kiện sắp xếp

Ví dụ:

~~~sql
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50
~~~

Chỉ mục có prefix tenant_id và tiếp theo là created_at có thể vừa tìm đúng tenant vừa trả dòng theo thứ tự thời gian, giảm hoặc loại bỏ bước sort. Chiều ASC/DESC, NULL ordering và khả năng scan ngược phụ thuộc DBMS và kiểu index. B-tree thường có thể được quét theo hai chiều, nhưng các tổ hợp nhiều cột với chiều sắp xếp khác nhau có thể cần khai báo direction cụ thể.

### 2.5. Điều kiện nhóm và tổng hợp

GROUP BY hoặc DISTINCT có thể hưởng lợi từ dữ liệu đã được sắp xếp theo khóa nhóm, nhưng một index không tự động loại bỏ toàn bộ chi phí aggregation. Nếu truy vấn cần đọc phần lớn bảng, scan tuần tự cộng hash aggregate có thể rẻ hơn đi qua index.

Hãy xem số dòng đầu vào, số nhóm, sort/hash operation và dữ liệu tạm trong execution plan trước khi tạo index chỉ nhằm hỗ trợ GROUP BY.

## 3. Hiểu B-tree và nguyên tắc prefix

### 3.1. B-tree là lựa chọn phổ biến cho truy vấn quan hệ

B-tree là loại index mặc định hoặc phổ biến trong nhiều DBMS quan hệ. Nó duy trì khóa theo thứ tự, hỗ trợ:

- So sánh bằng trên khóa.
- Quét phạm vi từ một giá trị đến giá trị khác.
- Trả dữ liệu theo thứ tự khóa.
- Tìm tiền tố chuỗi trong những điều kiện phù hợp.
- Kết hợp nhiều cột trong một index ghép.

Với B-tree, DBMS đi qua các trang nhánh đến trang lá chứa khóa cần tìm. Khi cần đọc một phạm vi, nó tìm điểm bắt đầu rồi quét các entry tiếp theo.

### 3.2. Chỉ mục ghép và leftmost prefix

Chỉ mục ghép lưu nhiều cột theo thứ tự đã định nghĩa. Ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Với thứ tự trên, các truy vấn sau thường có thể sử dụng prefix của index:

~~~sql
-- Dùng tenant_id.
WHERE tenant_id = 42

-- Dùng tenant_id và status.
WHERE tenant_id = 42 AND status = 'PAID'

-- Dùng prefix equality và range/order trên created_at.
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at DESC
~~~

Truy vấn chỉ lọc status mà không có tenant_id thường không thể tìm một vùng khóa liên tiếp hiệu quả bằng prefix của index này. Một số DBMS hỗ trợ skip scan hoặc kỹ thuật tương tự trong điều kiện phù hợp, nhưng không nên dựa vào khả năng đó nếu chưa xác minh.

Leftmost prefix không có nghĩa index chỉ hữu ích khi truy vấn dùng mọi cột. Prefix đầu vẫn có thể phục vụ truy vấn ít cột hơn. Nhưng một truy vấn chỉ dùng cột ở giữa hoặc cuối thường không khai thác được cấu trúc B-tree hiệu quả như index bắt đầu bằng cột đó.

### 3.3. Chọn thứ tự các cột equality

Giả sử truy vấn phổ biến có:

~~~sql
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
ORDER BY created_at DESC
~~~

Có thể thiết kế:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Hai cột equality đứng trước cột range/sort. Thứ tự giữa tenant_id và status cần xét thêm các truy vấn khác. Nếu nhiều truy vấn chỉ lọc tenant_id, đặt tenant_id trước có thể giúp tái sử dụng prefix. Nếu hầu hết truy vấn lọc status độc lập mà không có tenant_id, một index bắt đầu bằng status có thể cần được đánh giá riêng. Tuy nhiên, index mới cũng làm tăng chi phí ghi và không nên tạo chỉ vì một truy vấn hiếm.

Cardinality cao có thể giúp một cột chọn lọc tốt, nhưng cột có cardinality thấp vẫn hữu ích khi kết hợp với cột khác. Ví dụ status chỉ có vài giá trị, nhưng (tenant_id, status, created_at) vẫn có thể hỗ trợ truy vấn hiệu quả.

### 3.4. Cột range và cột ORDER BY

Với B-tree, khi equality prefix đã được cố định, cột tiếp theo có thể dùng để quét phạm vi và trả dữ liệu theo thứ tự. Nếu có nhiều cột range hoặc thứ tự sắp xếp phức tạp, cần kiểm tra plan cụ thể.

Ví dụ truy vấn:

~~~sql
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50
~~~

Một index có thể là:

~~~sql
CREATE INDEX idx_orders_recent
ON orders (tenant_id, status, created_at DESC, order_id DESC);
~~~

Cột order_id là tie-breaker để tạo thứ tự ổn định khi nhiều đơn có cùng created_at. Có thể cần cột này trong index để hỗ trợ thứ tự đầy đủ và keyset pagination.

### 3.5. Index có nhiều cột không phải lúc nào cũng tốt

Index càng rộng thì:

- Càng chiếm nhiều storage.
- Càng ít entry có thể nằm trên một trang.
- Càng tốn cache.
- Càng tăng chi phí cập nhật khi các cột index thay đổi.
- Càng làm tăng thời gian build, vacuum/reorganization và backup.

Hãy giữ index ở độ rộng cần thiết cho workload. Một index lớn có thể bao phủ nhiều truy vấn nhưng tạo chi phí ghi lớn và làm giảm hiệu quả cache.

## 4. Dùng selectivity và phân bố dữ liệu đúng cách

### 4.1. Selectivity

Selectivity mô tả tỷ lệ dòng thỏa một điều kiện. Khi một điều kiện chỉ chọn một phần rất nhỏ bảng, index access thường có lợi. Khi điều kiện chọn phần lớn bảng, scan tuần tự có thể rẻ hơn.

Ví dụ bảng có 10 triệu dòng:

| Điều kiện | Số dòng thỏa | Tỷ lệ chọn |
|---|---:|---:|
| order_id = một khóa duy nhất | 1 | 0,00001% |
| tenant_id = tenant nhỏ | 2.000 | 0,02% |
| status = 'PAID' | 7.000.000 | 70% |
| created_at trong một ngày cao điểm | 900.000 | 9% |

Bảng này chỉ minh họa. Tỷ lệ chọn không tạo ra một ngưỡng cố định để quyết định index hay scan. Chi phí còn phụ thuộc số cột cần đọc, cache, clustering, storage và cách optimizer ước lượng.

### 4.2. Cardinality và số giá trị phân biệt

Cardinality của một cột thường được dùng để mô tả số giá trị phân biệt hoặc số dòng của tập dữ liệu tùy ngữ cảnh. Cột có nhiều giá trị phân biệt có thể có khả năng chọn lọc tốt, nhưng không phải lúc nào cũng vậy. Nếu một cột có 1 triệu giá trị nhưng phần lớn truy vấn chỉ lọc một nhóm chiếm 80%, index có thể không giúp nhiều.

Ngược lại, cột status chỉ có ba giá trị vẫn có thể có ích khi kết hợp với tenant_id hoặc created_at. Đừng chọn index chỉ dựa trên số distinct value.

### 4.3. Skew và tham số đại diện

Dữ liệu thường không phân bố đều. Một tenant có thể chiếm 50% số đơn hàng; nhiều tenant khác chỉ có vài trăm dòng. Một trạng thái có thể chiếm gần toàn bảng. Cùng một query fingerprint có thể chạy nhanh với tenant nhỏ nhưng chậm với tenant lớn.

Khi thiết kế index, hãy đo với nhiều nhóm tham số:

- Tenant hoặc khách hàng nhỏ, trung bình và rất lớn.
- Trạng thái phổ biến và hiếm.
- Khoảng thời gian hẹp và rộng.
- Khóa có dữ liệu nóng và khóa ít được truy cập.

Thống kê cần đủ mới và đủ mô tả phân bố. Nếu optimizer ước lượng sai cardinality, nó có thể chọn scan hoặc index access không phù hợp. Hãy so sánh estimated rows với actual rows.

### 4.4. Clustering và locality

Nếu thứ tự khóa index gần với thứ tự vật lý của dữ liệu, một range scan có thể đọc ít trang hơn. Nếu các dòng phù hợp nằm rải rác trên nhiều trang, index lookup có thể dẫn đến nhiều random I/O. Một truy vấn đọc phần lớn bảng có thể chạy nhanh hơn bằng sequential scan.

Một số DBMS có thống kê correlation hoặc clustering factor để ước lượng mối liên hệ giữa thứ tự index và vị trí vật lý. Hãy dùng các số liệu tương ứng với DBMS đang triển khai thay vì chỉ nhìn selectivity.

## 5. Covering index và cột INCLUDE

### 5.1. Khi nào cần bao phủ?

Nếu truy vấn lọc theo một số cột và trả về một số cột khác, DBMS có thể phải đọc index rồi truy cập bảng để lấy các cột còn thiếu. Covering index lưu thêm cột cần trả về để giảm truy cập bảng trong các điều kiện DBMS hỗ trợ.

Ví dụ:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Một thiết kế trong PostgreSQL có thể là:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC)
INCLUDE (order_id, total);
~~~

Các cột trong INCLUDE được lưu ở leaf level để hỗ trợ trả kết quả nhưng không tham gia thứ tự khóa như các cột key. Điều này có thể giúp index-only scan khi các điều kiện visibility và trạng thái dữ liệu cho phép. Nó không đảm bảo DBMS luôn tránh truy cập bảng.

### 5.2. Không đưa mọi cột vào index

Một covering index quá rộng có thể lớn gần bằng bảng, chiếm cache và tăng chi phí ghi. Chỉ thêm cột được truy vấn quan trọng sử dụng và có lợi ích đo được.

Nếu truy vấn trả về payload JSON hoặc văn bản lớn, đưa toàn bộ payload vào index thường không hợp lý. Cân nhắc chỉ lấy metadata cần thiết hoặc tách luồng đọc chi tiết.

### 5.3. Khác biệt cú pháp giữa DBMS

PostgreSQL hỗ trợ INCLUDE trong B-tree index. SQL Server cũng có cú pháp INCLUDE cho nonclustered index. MySQL/InnoDB thường thiết kế covering index bằng cách đưa cột cần đọc vào phần key của index; cách lưu trữ và chi phí khác nhau. Không sao chép cú pháp giữa các DBMS mà chưa kiểm tra tài liệu.

## 6. Partial index và filtered index

Partial index chỉ lập chỉ mục cho những dòng thỏa một predicate. Một số DBMS cung cấp partial hoặc filtered index, nhưng cú pháp và điều kiện sử dụng khác nhau.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_orders_unpaid_created
ON orders (tenant_id, created_at DESC)
WHERE status IN ('PENDING', 'PROCESSING');
~~~

Nếu ứng dụng thường tìm đơn chưa hoàn tất:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND status IN ('PENDING', 'PROCESSING')
ORDER BY created_at DESC;
~~~

Index chỉ chứa một phần dữ liệu nên có thể nhỏ hơn index toàn bảng và giảm chi phí bảo trì cho các dòng không thỏa predicate. Tuy nhiên:

- Query phải có predicate mà optimizer chứng minh tương thích với predicate của index.
- Parameterized query hoặc biểu thức phức tạp có thể làm optimizer khó chứng minh điều kiện.
- Các dòng thay đổi trạng thái có thể được thêm vào hoặc loại khỏi index, tạo chi phí ghi.
- Không dùng partial index nếu workload thường xuyên cần truy vấn tất cả trạng thái.

Filtered index của SQL Server có khái niệm tương tự nhưng cú pháp và giới hạn riêng. MySQL không hỗ trợ partial index tổng quát giống PostgreSQL; có thể cần generated column, partitioning hoặc cách thiết kế khác tùy bài toán.

## 7. Expression index và generated column

Khi workload thường lọc theo một biểu thức, có thể cân nhắc index trên biểu thức hoặc cột được tính sẵn.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_users_lower_email
ON users (lower(email));
~~~

Truy vấn cần biểu thức tương ứng:

~~~sql
SELECT user_id
FROM users
WHERE lower(email) = lower('User@example.test');
~~~

Expression index có thể hỗ trợ tìm kiếm không phân biệt chữ hoa/thường theo biểu thức đã định nghĩa. Cần kiểm tra collation và semantics của hàm. Nếu truy vấn dùng biểu thức khác, index có thể không được sử dụng.

Generated column là cột được DBMS tính từ biểu thức theo quy tắc của hệ thống. Một index trên generated column có thể làm rõ cách dùng biểu thức và có thể hữu ích khi nhiều truy vấn dùng cùng phép biến đổi. Nhưng nó tạo thêm chi phí lưu trữ hoặc tính toán khi ghi, tùy loại generated column và DBMS.

Không tạo expression index chỉ để né một phép rewrite nếu truy vấn ít chạy hoặc biểu thức có thể chuyển sang điều kiện range đơn giản hơn.

## 8. Chọn loại index theo kiểu truy vấn và dữ liệu

B-tree là lựa chọn phổ biến, nhưng không phù hợp với mọi phép tìm kiếm.

| Loại index | Phù hợp với | Lưu ý |
|---|---|---|
| B-tree | Equality, range, ORDER BY, prefix phù hợp | Loại phổ biến nhất cho cột quan hệ |
| Hash | Equality lookup trong DBMS hỗ trợ | Không phục vụ range hoặc thứ tự |
| GIN | Thành viên trong array, JSONB, full-text trong PostgreSQL | Index có thể lớn; cập nhật có chi phí |
| GiST | Dữ liệu không gian, range và các toán tử hỗ trợ | Hiệu quả phụ thuộc operator class |
| BRIN | Bảng rất lớn có tương quan vật lý theo khóa | Nhỏ, nhưng có thể trả nhiều false positive cần recheck |
| Full-text | Tìm kiếm từ/ngữ nghĩa văn bản theo engine | Khác với LIKE prefix thông thường |
| Spatial/R-tree family | Truy vấn hình học, vùng và khoảng cách | Dùng kiểu index/operator chuyên biệt |

Tên loại index và tính năng hỗ trợ phụ thuộc DBMS. Ví dụ GIN, GiST và BRIN là các loại trong PostgreSQL; các hệ thống khác có cơ chế tương đương nhưng không nhất thiết cùng tên hoặc semantics.

### 8.1. B-tree cho equality và range

Dùng B-tree khi workload tìm theo khóa, quét phạm vi, hoặc cần dữ liệu theo thứ tự. Đây thường là lựa chọn đầu tiên để đánh giá cho khóa chính, khóa ngoại, thời gian và các cột lọc phổ biến.

### 8.2. Hash cho equality

Hash index chỉ hỗ trợ so sánh bằng theo khả năng của DBMS, không hỗ trợ range hoặc ORDER BY. Trong nhiều hệ thống, B-tree đã phục vụ tốt equality lookup nên hash index không mặc nhiên tốt hơn. Chỉ chọn khi có bằng chứng và hiểu rõ đặc tính triển khai.

### 8.3. GIN cho cấu trúc nhiều giá trị

Trong PostgreSQL, GIN có thể hỗ trợ tìm phần tử trong array, toán tử JSONB hoặc full-text. Ví dụ:

~~~sql
CREATE INDEX idx_documents_tags
ON documents USING GIN (tags);
~~~

Phù hợp với truy vấn kiểm tra thành viên trong array nếu operator class hỗ trợ. GIN có thể tạo index lớn và tăng chi phí insert/update; cần đo tốc độ ingest và vacuum/bảo trì.

### 8.4. GiST cho dữ liệu không gian và range

GiST hỗ trợ nhiều loại operator class, thường được dùng cho dữ liệu không gian, tìm kiếm giao nhau hoặc các kiểu range. Không nên chọn GiST chỉ vì dữ liệu có nhiều cột; phải xác định toán tử truy vấn được hỗ trợ.

### 8.5. BRIN cho dữ liệu lớn có thứ tự vật lý tương quan

BRIN lưu tóm tắt theo block range, thường rất nhỏ so với B-tree. Nó phù hợp khi giá trị cột tương quan với thứ tự vật lý, ví dụ bảng sự kiện được ghi gần theo thời gian. Truy vấn khoảng thời gian có thể loại bỏ nhiều block range, nhưng các block còn lại vẫn cần recheck và có thể chứa dòng không phù hợp.

## 9. Index cho JOIN, foreign key và tính duy nhất

### 9.1. Cột join

Nếu truy vấn thường nối bảng con với bảng cha theo foreign key, index ở cột foreign key của bảng con có thể giúp tìm các dòng liên quan.

~~~sql
SELECT o.order_id, i.product_id
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.order_id = 830154;
~~~

Index trên order_items(order_id) có thể hỗ trợ tìm chi tiết của một đơn hàng. Tuy nhiên, nếu bảng rất nhỏ hoặc truy vấn đọc phần lớn bảng con, scan vẫn có thể rẻ hơn.

### 9.2. Unique index

Unique index vừa hỗ trợ truy cập vừa bảo đảm tính duy nhất. Ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_users_email
ON users (email);
~~~

Unique constraint hoặc primary key thường được DBMS thực thi bằng một unique index hoặc cấu trúc tương đương. Không tạo thêm index trùng hoàn toàn với primary key/unique index nếu không có khác biệt thực sự về thứ tự hoặc cột bao phủ.

Tính duy nhất còn giúp optimizer suy luận cardinality và join. Nhưng với cột nullable, quy tắc unique và cách xử lý nhiều NULL khác nhau giữa DBMS; cần hiểu semantics của sản phẩm đang dùng.

### 9.3. Index ở phía foreign key

Index trên bảng con có thể giúp tìm dòng tham chiếu khi join, xóa hoặc cập nhật bản ghi cha. Một số DBMS tự tạo index cho primary key nhưng không tự tạo index cho foreign key. Vì vậy, hãy kiểm tra schema và workload thay vì giả định ràng buộc foreign key đồng nghĩa đã có index.

## 10. Tránh index dư thừa và trùng lặp

Hai index có thể trùng hoàn toàn hoặc một index có prefix bao phủ truy vấn mà index kia phục vụ. Ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);

CREATE INDEX idx_orders_tenant_status
ON orders (tenant_id, status);
~~~

Index thứ hai có leftmost prefix tenant_id, nên có thể phục vụ một số truy vấn chỉ lọc tenant_id. Tuy nhiên, không thể kết luận index đầu tiên luôn dư thừa: index nhỏ hơn có thể rẻ hơn để scan, có thể khác về uniqueness, predicate, collation, direction hoặc INCLUDE. Cần xem các truy vấn và plan thực tế.

Các dấu hiệu index cần xem xét:

- Không được truy cập trong thời gian đủ dài và workload đại diện.
- Có cùng key columns, direction, predicate và storage options với index khác.
- Là prefix của index rộng hơn nhưng không có lý do vận hành để giữ riêng.
- Có chi phí ghi đáng kể nhưng lợi ích đọc thấp.
- Được tạo cho truy vấn đã biến mất hoặc schema cũ.
- Quá rộng và gây áp lực cache.

Trước khi xóa index, kiểm tra khoảng thời gian thống kê, reset counter, các job định kỳ, truy vấn hiếm nhưng quan trọng, constraint phụ thuộc và khả năng sử dụng trong tương lai. Không xóa chỉ dựa vào một dashboard trong vài giờ.

## 11. Chi phí của chỉ mục đối với thao tác ghi

Mỗi index là một cấu trúc cần duy trì đồng bộ với dữ liệu. Khi INSERT, DBMS phải thêm entry vào những index liên quan. Khi DELETE, entry cần được loại bỏ hoặc đánh dấu theo cơ chế lưu trữ. Khi UPDATE thay đổi cột index, DBMS phải cập nhật entry cũ và mới.

Chi phí có thể gồm:

- Tăng số trang phải ghi và lượng transaction log/WAL.
- Tăng I/O và CPU cho việc cập nhật cấu trúc index.
- Tăng dung lượng database, backup và replication traffic.
- Tăng áp lực buffer cache vì index cạnh tranh bộ nhớ với dữ liệu.
- Page split hoặc phân mảnh khi chèn khóa vào vị trí giữa cấu trúc.
- Tranh chấp trên trang index nóng khi nhiều phiên cùng ghi vào vùng khóa tương tự.
- Thời gian và tài nguyên cần cho build, rebuild hoặc vacuum/reorganization.

Với workload đọc nhiều, thêm index có thể đáng giá. Với workload ingest nặng, index dư thừa có thể làm giảm throughput đáng kể. Với workload hỗn hợp, cần đo cả truy vấn đọc được hưởng lợi và thao tác ghi bị ảnh hưởng.

### 11.1. Hot page và khóa tuần tự

Index có khóa tăng dần có thể khiến nhiều phiên cùng chèn ở vùng cuối B-tree. Tùy DBMS, cấu hình và mức đồng thời, điều này có thể tạo page contention. Ngược lại, khóa ngẫu nhiên có thể phân tán vị trí chèn nhưng tăng page split và random I/O. Không có chiến lược khóa tối ưu cho mọi trường hợp; hãy quan sát wait events, tốc độ ghi và cấu trúc index.

### 11.2. Fill factor và bảo trì

Một số DBMS cho phép điều chỉnh fill factor hoặc tham số tương tự để dành chỗ trống trong trang index, giảm page split trong một số mẫu ghi. Đổi lại, index lớn hơn và có thể cần nhiều I/O hơn khi đọc. Đây là tham số phụ thuộc engine và workload, nên chỉ điều chỉnh khi có bằng chứng về page split hoặc contention.

Bảo trì index cũng cần kế hoạch: rebuild có thể tốn I/O, CPU, storage tạm và khóa hoặc hạn chế concurrency tùy DBMS. Hãy kiểm tra cách thực hiện online/concurrent của phiên bản cụ thể trước khi chạy trên hệ thống thật.

## 12. Index và partitioning giải quyết hai bài toán khác nhau

Partitioning chia dữ liệu thành các phần vật lý hoặc logic theo khóa phân vùng. Index giúp tìm entry trong một tập dữ liệu. Hai kỹ thuật có thể bổ trợ nhưng không thay thế hoàn toàn nhau.

Ví dụ, bảng events partition theo tháng có thể dùng partition pruning để chỉ truy cập partition cần thiết. Trong mỗi partition, B-tree index trên tenant_id hoặc event_type có thể giúp tìm tập dòng nhỏ hơn.

Không phải mọi partition đều cần cùng một index. Nếu truy vấn luôn lọc theo thời gian và đọc phần lớn partition, scan có thể hợp lý. Nếu truy vấn tìm một tenant trong partition, index cục bộ có thể hữu ích. Hãy đánh giá kích thước mỗi partition, số partition bị truy cập và chi phí quản lý index.

## 13. Quy trình thiết kế index theo workload

### Bước 1: Thu thập truy vấn quan trọng

Dùng query fingerprint, slow query log, thống kê DBMS và trace ứng dụng để lập danh sách mẫu truy vấn. Ghi tần suất, tổng thời gian, p95/p99, rows read, I/O và tác động nghiệp vụ.

### Bước 2: Phân tích điều kiện và kết quả

Với từng query, ghi rõ:

- Cột trong equality predicate.
- Cột trong range predicate.
- Cột dùng để join.
- Cột trong ORDER BY/GROUP BY.
- Cột cần trả về.
- Giới hạn dòng và yêu cầu thứ tự.
- Giá trị tham số phổ biến, hiếm và skew.

### Bước 3: Kiểm tra index hiện có

Xem primary key, unique index, foreign key index và các index khác. So sánh key order, direction, predicate, INCLUDE, collation và loại index. Kiểm tra có index nào đã phục vụ cùng query fingerprint chưa.

### Bước 4: Đưa ra thiết kế tối thiểu

Chọn loại index và thứ tự cột để hỗ trợ nhiều truy vấn quan trọng nhất với chi phí hợp lý. Thường xem xét equality prefix, sau đó range/order, rồi cột bao phủ nếu lợi ích đủ lớn. Đừng tạo index riêng cho mọi điều kiện.

### Bước 5: Dự đoán chi phí đọc và ghi

Ước lượng kích thước index, số cột, độ rộng dữ liệu, số dòng được bao phủ và tần suất cập nhật. Xác định bảng có workload ghi cao hay không. Cân nhắc index có predicate để chỉ lưu tập dòng cần thiết khi DBMS hỗ trợ.

### Bước 6: Tạo thử và kiểm tra execution plan

Trong môi trường thử nghiệm hoặc quy trình thay đổi phù hợp, tạo index và thu thập plan trước/sau. Xem access path, estimated/actual rows, buffers, sort, loops và thời gian. Xác nhận truy vấn mục tiêu thực sự sử dụng index và không làm plan khác xấu đi.

### Bước 7: Benchmark toàn workload

Chạy tải đại diện với nhiều tham số và concurrency. Đo latency, throughput, CPU, I/O, log bytes, lock waits và tốc độ ghi. Index có thể làm SELECT nhanh hơn nhưng giảm throughput INSERT/UPDATE.

### Bước 8: Theo dõi sau triển khai

Quan sát mức sử dụng index, dung lượng, cache, latency của các query digest và chi phí ghi. Giữ lại bằng chứng trước/sau và kế hoạch hoàn nguyên nếu kết quả xấu đi.

## 14. Ví dụ thiết kế index cho một workload bán hàng

Giả sử bảng orders có hàng chục triệu dòng. Các truy vấn quan trọng:

~~~sql
-- Q1: tra cứu theo tenant và order_id.
SELECT order_id, status, total
FROM orders
WHERE tenant_id = 42
  AND order_id = 830154;

-- Q2: danh sách đơn PAID mới nhất của tenant.
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;

-- Q3: báo cáo theo thời gian.
SELECT status, COUNT(*), SUM(total)
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at < TIMESTAMP '2026-12-01 00:00:00'
GROUP BY status;
~~~

Giả sử Q1 đã được hỗ trợ bởi primary key hoặc unique index trên (tenant_id, order_id). Không cần tạo thêm index trùng lặp cho Q1.

Với Q2, có thể thử index:

~~~sql
-- Ví dụ PostgreSQL.
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC)
INCLUDE (order_id, total);
~~~

Index này đặt các điều kiện bằng ở đầu, tiếp theo là cột sắp xếp. INCLUDE có thể giúp giảm truy cập bảng nếu DBMS xác nhận index-only scan khả thi. Nếu workload ghi nhiều hoặc index quá rộng, hãy thử bỏ INCLUDE và đo chênh lệch.

Q3 lọc tenant bằng equality và created_at bằng range, nhưng không lọc status. Index của Q2 có status nằm giữa tenant_id và created_at nên không nhất thiết phục vụ Q3 tốt bằng index có thứ tự:

~~~sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at);
~~~

Có nên tạo index thứ hai không? Cần xem Q3 có tần suất và tổng thời gian đủ lớn không, phạm vi thời gian chọn bao nhiêu dòng, và index hiện có có thể phục vụ nhờ scan hoặc skip scan của DBMS không. Nếu Q3 đọc phần lớn đơn hàng trong tháng, sequential scan trên partition hoặc bảng có thể rẻ hơn. Thêm index sẽ tăng chi phí mọi thao tác ghi trên orders.

Thiết kế cuối cùng phải được quyết định bằng workload profile và benchmark, không chỉ từ hình thức ba câu SQL.

## 15. Đọc execution plan để xác nhận index

Sau khi có giả thuyết về index, hãy kiểm tra plan. Một số câu hỏi quan trọng:

- DBMS có dùng index được đề xuất không?
- Điều kiện nào được dùng làm index condition, điều kiện nào vẫn là filter?
- Estimated rows có gần actual rows không?
- Có bao nhiêu loop và bao nhiêu lần truy cập bảng?
- Có sort bổ sung dù index có thứ tự không?
- Số buffer hit/read thay đổi thế nào?
- Có spill hoặc temporary I/O không?
- Thời gian parse/plan và execution có thay đổi không?

Ví dụ PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

EXPLAIN ANALYZE thực sự chạy truy vấn. Dùng trên môi trường và dữ liệu phù hợp; với câu lệnh ghi, nó có thể tạo thay đổi thật. Một plan có Index Scan không tự động tốt hơn Seq Scan. So sánh actual rows, buffers, thời gian và chi phí tổng thể.

Với MySQL, dùng EXPLAIN hoặc EXPLAIN ANALYZE nếu phiên bản hỗ trợ để xem chosen key, access type, estimated rows, actual timing và iterator. SQL Server có actual execution plan và thống kê IO/time. Tên và cách diễn giải khác nhau giữa DBMS; hãy dùng công cụ phù hợp với phiên bản đang vận hành.

## 16. Những sai lầm thường gặp khi thiết kế index

**Tạo index cho mọi cột trong WHERE.** Nhiều index đơn lẻ có thể làm tăng chi phí ghi mà không phục vụ đúng tổ hợp điều kiện. Hãy xem query pattern và index ghép.

**Đặt cột có cardinality cao nhất lên đầu theo một quy tắc cứng.** Thứ tự phụ thuộc prefix workload, equality/range, ORDER BY và phân bố tham số.

**Cho rằng index càng rộng càng tốt.** Cột bao phủ làm index lớn và tăng chi phí bảo trì. Chỉ thêm khi lợi ích đo được đủ lớn.

**Tạo index chỉ vì thấy full scan.** Full scan có thể là lựa chọn rẻ nhất khi truy vấn đọc phần lớn bảng hoặc bảng nhỏ.

**Không tính chi phí ghi.** Mỗi index bổ sung công việc INSERT, UPDATE, DELETE và có thể tạo contention.

**Dùng cùng một index cho mọi tenant hoặc tham số.** Skew có thể khiến một kế hoạch tốt cho tenant nhỏ nhưng kém cho tenant lớn.

**Không xem index hiện có.** Có thể đã có primary key, unique index hoặc index ghép với prefix phù hợp.

**Xóa index vì ít được dùng trong một khoảng ngắn.** Thống kê có thể reset, và truy vấn hiếm hoặc job định kỳ chưa chạy trong khoảng quan sát.

**Không đo lại toàn workload.** Cải thiện một query có thể làm giảm throughput ghi hoặc ảnh hưởng query khác.

## 17. Checklist trước khi tạo hoặc loại bỏ index

- [ ] Đã xác định query fingerprint và mức độ quan trọng của truy vấn chưa?
- [ ] Đã thu tần suất, tổng thời gian, p95/p99 và tài nguyên tiêu thụ chưa?
- [ ] Đã liệt kê equality, range, join, order, group và projection columns chưa?
- [ ] Đã xem phân bố dữ liệu, selectivity, cardinality và skew chưa?
- [ ] Đã kiểm tra index hiện có, primary key, unique và foreign key chưa?
- [ ] Đã xác định thứ tự cột và prefix phục vụ các query quan trọng chưa?
- [ ] Đã cân nhắc covering, partial hoặc expression index khi có lý do chưa?
- [ ] Đã ước lượng kích thước và chi phí duy trì index khi ghi chưa?
- [ ] Đã kiểm tra khả năng page contention, page split và cache pressure chưa?
- [ ] Đã so sánh execution plan trước/sau trên tham số đại diện chưa?
- [ ] Đã benchmark đọc, ghi và concurrency cùng nhau chưa?
- [ ] Đã có số liệu theo dõi và phương án hoàn nguyên chưa?

## Kết luận

Lựa chọn chỉ mục phải bắt đầu từ các truy vấn quan trọng và tập điều kiện thực tế. Hãy hiểu truy vấn lọc theo equality hay range, join trên cột nào, cần thứ tự gì và trả về những cột nào. B-tree ghép thường phục vụ tốt equality prefix kết hợp range/order; covering index có thể giảm truy cập bảng; partial và expression index có thể hữu ích cho những mẫu điều kiện đặc thù; các loại GIN, GiST, BRIN hoặc full-text phù hợp với cấu trúc dữ liệu chuyên biệt.

Một index tốt cần cân bằng lợi ích đọc với chi phí ghi, dung lượng, cache và bảo trì. Selectivity, cardinality, skew và locality phải được đo trên dữ liệu đại diện. Cuối cùng, execution plan và benchmark toàn workload mới xác nhận thiết kế có hiệu quả. Hãy tạo ít chỉ mục nhưng có lý do rõ ràng, đo trước/sau và tiếp tục theo dõi sau triển khai.

