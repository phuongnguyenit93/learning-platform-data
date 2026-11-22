# Chỉ mục một phần hoặc có điều kiện và phạm vi áp dụng

Chỉ mục một phần (partial index) hoặc chỉ mục có điều kiện (filtered index) chỉ lưu các hàng thỏa một predicate xác định. Thay vì lập chỉ mục cho toàn bộ bảng, hệ quản trị duy trì cấu trúc chỉ mục trên tập con dữ liệu mà một nhóm truy vấn thường xuyên cần truy cập. Khi predicate của truy vấn phù hợp với điều kiện của chỉ mục, bộ tối ưu có thể dùng chỉ mục nhỏ hơn, giảm số trang phải đọc, giảm dung lượng cache và giảm chi phí bảo trì so với một chỉ mục toàn bảng tương đương.

Trong thiết kế chỉ mục chuyên biệt cho DATABASE_PERFORMANCE, cần xác định rõ tập con nào có giá trị nghiệp vụ ổn định, truy vấn nào có thể chứng minh rằng nó chỉ cần tập con đó và hệ quản trị đang dùng hỗ trợ cơ chế nào. PostgreSQL và SQLite có partial index; SQL Server có filtered index; Oracle có thể tạo chỉ mục B-tree có điều kiện bằng biểu thức CASE trong function-based index; MySQL không có partial index native theo predicate và cần cân nhắc các cách mô phỏng bằng generated column hoặc composite index. Những cách này không hoàn toàn tương đương về lưu trữ và hành vi của optimizer.

## 1. Ý tưởng của chỉ mục một phần

Giả sử bảng orders có 50 triệu hàng, trong đó chỉ 2% đơn hàng còn ở trạng thái OPEN. Ứng dụng có một màn hình thường xuyên tìm các đơn OPEN theo khách hàng và thời điểm tạo:

~~~sql
SELECT id, customer_id, created_at, total_amount
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 125
ORDER BY created_at DESC;
~~~

Một chỉ mục toàn bảng có thể là:

~~~sql
CREATE INDEX ix_orders_status_customer_created
ON orders (status, customer_id, created_at);
~~~

Chỉ mục này chứa mục cho mọi hàng. Nếu truy vấn gần như chỉ quan tâm đến các hàng OPEN và tập OPEN rất nhỏ, có thể cân nhắc một chỉ mục chỉ chứa những hàng đó:

~~~sql
CREATE INDEX ix_orders_open_customer_created
ON orders (customer_id, created_at)
WHERE status = 'OPEN';
~~~

Đây là cú pháp PostgreSQL/SQLite. Predicate status = 'OPEN' xác định hàng nào được đưa vào chỉ mục. Cột status không cần nằm trong key chỉ mục để xác định phạm vi; engine duy trì chỉ mục theo predicate.

Nếu chỉ mục một phần chứa 2% số hàng, cấu trúc có thể nhỏ hơn đáng kể so với chỉ mục toàn bảng. Tuy nhiên, mức tiết kiệm thực tế còn tùy kích thước khóa, độ rộng hàng, page fill, overhead và số lượng chỉ mục khác.

### 1.1. Chỉ mục một phần khác gì chỉ mục toàn bảng?

| Thuộc tính | Chỉ mục toàn bảng | Chỉ mục một phần/có điều kiện |
|---|---|---|
| Phạm vi hàng | Tất cả hàng đủ điều kiện lập chỉ mục | Chỉ hàng thỏa predicate |
| Kích thước | Thường lớn hơn nếu bảng có nhiều hàng ngoài tập quan tâm | Có thể nhỏ hơn nhiều khi predicate chọn tập con nhỏ |
| Khả năng dùng | Có thể phục vụ nhiều dạng truy vấn trên các cột khóa | Chỉ hữu ích khi truy vấn phù hợp predicate và key |
| Chi phí ghi | Duy trì mục cho các hàng liên quan | Chỉ duy trì hàng thuộc tập predicate; cập nhật ra/vào tập vẫn có chi phí |
| Thống kê | Mô tả tập dữ liệu rộng hơn | Một số engine có thống kê gắn với tập đã lọc |
| Rủi ro | Dễ tạo chỉ mục dư thừa, tốn cache | Dễ không được optimizer chọn nếu predicate không chứng minh được |

Chỉ mục một phần không phải cách để bỏ qua thiết kế key columns. Sau khi xác định tập con, vẫn cần chọn thứ tự cột khóa phù hợp với equality, range, join và ORDER BY của workload.

## 2. Khi nào nên dùng?

Chỉ mục một phần thường phù hợp khi một tập con nhỏ và có ý nghĩa ổn định được truy cập thường xuyên.

### 2.1. Trạng thái hiếm hoặc hàng chưa xử lý

Ví dụ hệ thống có bảng jobs chứa hàng triệu tác vụ, nhưng chỉ một phần nhỏ đang chờ xử lý:

~~~sql
SELECT id, priority, scheduled_at
FROM jobs
WHERE state = 'READY'
  AND scheduled_at <= CURRENT_TIMESTAMP
ORDER BY priority DESC, scheduled_at;
~~~

Nếu READY chỉ chiếm tỷ lệ nhỏ, chỉ mục có điều kiện trên READY có thể giúp worker tìm tác vụ cần chạy mà không phải đi qua phần lớn hàng đã hoàn tất.

### 2.2. Bản ghi đang hoạt động và soft delete

Một bảng users hoặc subscriptions có thể giữ cả lịch sử đã xóa logic. Các truy vấn ứng dụng thường chỉ đọc bản ghi chưa bị xóa:

~~~sql
SELECT id, email
FROM users
WHERE deleted_at IS NULL
  AND email = 'user@example.test';
~~~

Chỉ mục có điều kiện trên hàng deleted_at IS NULL có thể nhỏ hơn chỉ mục bao phủ toàn bộ lịch sử, nếu phần lớn dữ liệu đã bị xóa logic và engine hỗ trợ predicate này.

### 2.3. Giá trị khác NULL hoặc dữ liệu có điều kiện

Nếu truy vấn thường tìm các hàng có một cột quan trọng khác NULL, predicate có thể là column IS NOT NULL. Đây là trường hợp phù hợp với một số hệ quản trị hỗ trợ filtered/partial index.

### 2.4. Tập dữ liệu theo loại sự kiện

Một bảng events có nhiều loại sự kiện nhưng một nhóm truy vấn chỉ phân tích loại hiếm, chẳng hạn event_type = 'PAYMENT_FAILED'. Chỉ mục có điều kiện trên loại này có thể hỗ trợ truy vấn điều tra sự cố.

### 2.5. Unique constraint trên một tập con

Một số engine cho phép tạo unique partial/filtered index. Ví dụ, chỉ yêu cầu email duy nhất đối với tài khoản chưa bị xóa:

~~~sql
CREATE UNIQUE INDEX ux_users_active_email
ON users (email)
WHERE deleted_at IS NULL;
~~~

Ví dụ trên là cú pháp PostgreSQL. Nó áp dụng tính duy nhất cho các hàng thỏa predicate, thay vì bắt buộc email duy nhất trên toàn bộ lịch sử. Cần kiểm tra ngữ nghĩa NULL và yêu cầu nghiệp vụ của hệ quản trị; không được xem partial unique index là thay thế cho mọi ràng buộc UNIQUE.

## 3. Điều kiện quan trọng: truy vấn phải hàm ý predicate của chỉ mục

Để dùng partial/filtered index, optimizer cần xác định rằng mọi hàng mà truy vấn có thể trả về đều thuộc tập hàng của chỉ mục. Nói cách khác, predicate của truy vấn phải hàm ý predicate của chỉ mục.

Giả sử chỉ mục có predicate:

~~~sql
WHERE status = 'OPEN'
~~~

Truy vấn sau rõ ràng thỏa điều kiện:

~~~sql
SELECT id, customer_id
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 125;
~~~

Truy vấn sau không thể dùng riêng chỉ mục OPEN để trả lời đầy đủ vì nó có thể cần cả hàng CLOSED:

~~~sql
SELECT id, customer_id
FROM orders
WHERE status IN ('OPEN', 'CLOSED')
  AND customer_id = 125;
~~~

Truy vấn có predicate rộng hơn hoặc khác biểu thức cũng có thể khiến optimizer không chứng minh được quan hệ hàm ý, dù người phát triển biết hai điều kiện tương đương trong một ngữ cảnh cụ thể.

### 3.1. Viết predicate tương thích

Hãy giữ điều kiện trong SQL rõ ràng và gần với predicate của index:

- Dùng cùng giá trị trạng thái hoặc điều kiện phạm vi đã định nghĩa.
- Tránh bọc cột bằng hàm hoặc ép kiểu không cần thiết nếu làm thay đổi cách optimizer nhận diện predicate.
- Kiểm tra logic NULL rõ ràng; phép so sánh bằng với NULL không tương đương IS NULL.
- Đảm bảo kiểu dữ liệu, collation, timezone và ngữ nghĩa so sánh thống nhất.
- Xem xét biểu thức có deterministic/immutable theo yêu cầu của engine không.

Ví dụ, nếu partial index dựa trên deleted_at IS NULL, truy vấn dùng chính điều kiện này dễ được nhận diện hơn một biểu thức phức tạp khác có ý định biểu diễn cùng trạng thái.

### 3.2. Tham số hóa và prepared statement

Một trường hợp dễ bỏ sót là truy vấn dùng tham số:

~~~sql
SELECT id, customer_id
FROM orders
WHERE status = :status
  AND customer_id = :customer_id;
~~~

Nếu partial index chỉ chứa status = 'OPEN', một generic plan không biết giá trị status tại thời điểm lập kế hoạch có thể không chứng minh được rằng mọi hàng kết quả đều thuộc index. Một số engine hoặc chế độ lập kế hoạch có thể tạo kế hoạch riêng khi biết giá trị tham số; hành vi phụ thuộc engine, driver, plan cache và phiên bản.

Khi kiểm tra, hãy thử cả truy vấn literal và prepared statement với các giá trị tham số đại diện. Đọc actual execution plan để xác nhận chỉ mục có được chọn hay không. Không giả định việc bind tham số luôn cho phép hoặc luôn ngăn dùng partial index.

### 3.3. Predicate không ổn định theo thời gian

Predicate kiểu created_at lớn hơn thời điểm hiện tại trừ đi một khoảng thời gian thay đổi theo thời gian. Một số hệ quản trị không cho phép hàm volatile hoặc không bất biến trong điều kiện của partial index vì tập hàng của chỉ mục sẽ không tự cập nhật chỉ vì thời gian trôi qua.

Thay vì lập chỉ mục “các hàng trong 7 ngày gần nhất” bằng một predicate phụ thuộc đồng hồ, hãy xem xét một cột trạng thái được cập nhật theo quy trình nghiệp vụ, partitioning theo thời gian hoặc chỉ mục thông thường trên created_at. Chỉ dùng biểu thức được engine cho phép và có cơ chế duy trì tính đúng đắn.

## 4. PostgreSQL: partial index

PostgreSQL hỗ trợ partial index trực tiếp với mệnh đề WHERE trong CREATE INDEX.

Ví dụ chỉ mục cho đơn OPEN:

~~~sql
CREATE INDEX ix_orders_open_customer_created
ON orders (customer_id, created_at DESC)
INCLUDE (total_amount)
WHERE status = 'OPEN';
~~~

Truy vấn tương ứng:

~~~sql
SELECT customer_id, created_at, total_amount
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 125
ORDER BY created_at DESC;
~~~

Predicate giới hạn tập hàng được lưu; key columns vẫn quyết định thứ tự tìm kiếm và sắp xếp; INCLUDE giữ thêm payload nếu phiên bản và access method hỗ trợ.

### 4.1. Giới hạn predicate

- Predicate chỉ tham chiếu các cột của chính bảng được lập chỉ mục.
- Không dùng subquery hoặc aggregate trong predicate.
- Các hàm và operator trong predicate phải đáp ứng yêu cầu immutability của PostgreSQL.
- Planner phải chứng minh predicate truy vấn hàm ý predicate của index.
- Partial index có thể dùng cho UNIQUE để áp dụng tính duy nhất trên tập hàng được chọn.

PostgreSQL không có bộ chứng minh định lý tổng quát cho mọi biểu thức tương đương. Giữ predicate đơn giản, rõ ràng và tương thích với truy vấn giúp planner nhận diện tốt hơn.

### 4.2. Kiểm tra kế hoạch

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, created_at, total_amount
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 125
ORDER BY created_at DESC;
~~~

Kiểm tra Index Scan hoặc Index Only Scan trên partial index, số hàng thực tế, buffers và thời gian. Nếu index không được dùng, xem predicate có khớp không, số hàng OPEN có đủ chọn lọc không, thống kê đã cập nhật chưa và có index khác rẻ hơn không.

## 5. SQL Server: filtered index

SQL Server hỗ trợ filtered index trên một tập hàng thỏa điều kiện WHERE. Đây là một dạng nonclustered index có predicate lọc.

Ví dụ:

~~~sql
CREATE NONCLUSTERED INDEX IX_Orders_Open_Customer_Created
ON dbo.Orders (customer_id, created_at)
INCLUDE (total_amount)
WHERE status = 'OPEN';
~~~

Truy vấn:

~~~sql
SELECT customer_id, created_at, total_amount
FROM dbo.Orders
WHERE status = 'OPEN'
  AND customer_id = @customer_id
ORDER BY created_at;
~~~

Filtered index có thể nhỏ hơn chỉ mục không lọc, giảm storage và chi phí bảo trì khi chỉ một phần nhỏ bảng thỏa điều kiện. SQL Server cũng duy trì filtered statistics, giúp optimizer ước lượng trên tập con được lọc chính xác hơn trong một số workload.

### 5.1. Giới hạn và lưu ý

- Filter predicate có các giới hạn cú pháp; không phải mọi biểu thức SQL đều được chấp nhận.
- Truy vấn phải có điều kiện tương thích để optimizer có thể dùng filtered index.
- Tham số hóa và kế hoạch được cache có thể ảnh hưởng đến khả năng chứng minh predicate.
- Nếu truy vấn trả về cột không có trong index, engine vẫn có thể cần lookup.
- Cần kiểm tra điều kiện NULL và kiểu dữ liệu trong filter.

Filtered index phù hợp với các tập dữ liệu có trạng thái rõ ràng như hàng chưa xử lý, bản ghi chưa xóa hoặc cột có giá trị NULL/NOT NULL theo nghiệp vụ. Hãy kiểm tra tài liệu phiên bản SQL Server đang triển khai khi predicate có biểu thức hoặc kiểu dữ liệu đặc biệt.

### 5.2. Xác nhận bằng Actual Execution Plan

Mở Actual Execution Plan và xác nhận operator dùng đúng filtered index. Đối chiếu số hàng thực tế, logical reads, Key Lookup và thời gian. Nếu truy vấn có tham số status, thử các giá trị khác nhau và kiểm tra kế hoạch cache có phù hợp cho từng trường hợp hay không.

## 6. SQLite: partial index

SQLite hỗ trợ partial index với WHERE trong CREATE INDEX:

~~~sql
CREATE INDEX ix_orders_open_customer_created
ON orders (customer_id, created_at)
WHERE status = 'OPEN';
~~~

Truy vấn:

~~~sql
SELECT id, customer_id, created_at
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 125;
~~~

SQLite chỉ đưa hàng thỏa predicate vào index. Query planner dùng các quy tắc giới hạn để nhận diện khi điều kiện truy vấn hàm ý predicate của index; không phải mọi biểu thức logic tương đương đều được chứng minh. Viết predicate truy vấn nhất quán với predicate index và dùng EXPLAIN QUERY PLAN để kiểm tra.

Ví dụ:

~~~sql
EXPLAIN QUERY PLAN
SELECT id, customer_id, created_at
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 125;
~~~

Partial index của SQLite cũng có thể là UNIQUE để giới hạn tính duy nhất cho các hàng thuộc predicate. Cần lưu ý predicate không được dùng subquery, tham chiếu bảng khác hoặc hàm không deterministic theo các quy tắc của SQLite.

## 7. MySQL: không có partial index native

MySQL/InnoDB không hỗ trợ cú pháp tạo B-tree index chỉ chứa các hàng thỏa một WHERE predicate như PostgreSQL, SQL Server hoặc SQLite. Một composite index vẫn có entry cho các hàng của bảng theo các giá trị khóa, kể cả khi cột khóa là NULL.

Có thể dùng generated column hoặc functional index để biểu diễn điều kiện nghiệp vụ thành một giá trị có thể lập chỉ mục. Ví dụ:

~~~sql
ALTER TABLE orders
ADD COLUMN open_customer_id BIGINT
    GENERATED ALWAYS AS (
        CASE WHEN status = 'OPEN' THEN customer_id ELSE NULL END
    ) STORED;

CREATE INDEX ix_orders_open_customer
ON orders (open_customer_id, created_at);
~~~

Truy vấn có thể tham chiếu generated column:

~~~sql
SELECT id, customer_id, created_at
FROM orders
WHERE open_customer_id = 125
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

Cách này tạo một đường truy cập có điều kiện, nhưng không phải partial index thực sự: các hàng không OPEN vẫn có entry trong secondary index với giá trị open_customer_id là NULL, cùng các thành phần khóa khác. Vì vậy, chỉ mục có thể không tiết kiệm dung lượng như partial index native.

Nếu dùng functional key parts, cú pháp và giới hạn phụ thuộc phiên bản MySQL. Generated column tường minh thường giúp SQL dễ đọc và thuận tiện kiểm tra hơn. Cần đo kích thước index, cardinality, access plan và chi phí cập nhật generated value.

## 8. Oracle Database: function-based index có điều kiện

Oracle Database không dùng cú pháp partial index WHERE giống PostgreSQL. Có thể tạo function-based B-tree index với biểu thức CASE để các hàng ngoài tập quan tâm tạo ra NULL cho toàn bộ key expression. B-tree index của Oracle không lưu entry khi tất cả key columns đều NULL; nhờ đó có thể tạo một index chỉ chứa hàng thỏa điều kiện.

Ví dụ tạo virtual columns:

~~~sql
ALTER TABLE orders ADD (
    open_customer_id GENERATED ALWAYS AS (
        CASE WHEN status = 'OPEN' THEN customer_id END
    ) VIRTUAL,
    open_created_at GENERATED ALWAYS AS (
        CASE WHEN status = 'OPEN' THEN created_at END
    ) VIRTUAL
);

CREATE INDEX ix_orders_open_customer_created
ON orders (open_customer_id, open_created_at);
~~~

Truy vấn tham chiếu các cột ảo:

~~~sql
SELECT id, customer_id, created_at
FROM orders
WHERE open_customer_id = :customer_id
  AND open_created_at >= :from_time
  AND open_created_at < :to_time;
~~~

Với hàng không OPEN, cả hai biểu thức trả NULL nên không tạo entry B-tree cho hàng đó. Hàng OPEN có giá trị được lưu trong index và có thể được tìm kiếm theo các virtual columns.

Đây là kỹ thuật function-based/conditional indexing, cần xác nhận optimizer nhận diện biểu thức và kế hoạch dùng index. Nếu truy vấn tiếp tục lọc trực tiếp bằng status/customer_id/created_at mà không tham chiếu biểu thức hoặc virtual columns tương ứng, optimizer có thể không chuyển đổi sang đường truy cập này.

Không thêm một key expression luôn khác NULL cho mọi hàng nếu mục tiêu là bỏ các hàng ngoài predicate; điều đó sẽ làm index có entry cho toàn bảng. Kiểm tra thêm kích thước khóa, giới hạn kiểu dữ liệu và chi phí cập nhật virtual expression.

## 9. Chọn predicate và key columns

Một partial/filtered index cần hai quyết định riêng:

1. Predicate chọn tập hàng nào được lưu.
2. Key columns xác định cách tìm kiếm, nối hoặc sắp xếp bên trong tập hàng đó.

Ví dụ, chỉ mục cho jobs đang READY có thể dùng:

~~~sql
-- PostgreSQL
CREATE INDEX ix_jobs_ready_schedule
ON jobs (priority DESC, scheduled_at)
WHERE state = 'READY';
~~~

Predicate state = 'READY' chọn tập con. priority và scheduled_at phục vụ thứ tự lấy việc. Nếu truy vấn lọc theo queue_id trước, key columns có thể cần bắt đầu bằng queue_id. Hãy thiết kế theo predicate thực tế và tần suất truy vấn.

### 9.1. Predicate càng hẹp không phải lúc nào cũng càng tốt

Một predicate rất hẹp có thể tạo index nhỏ, nhưng nếu truy vấn thực tế cần nhiều trạng thái hoặc nhiều nhóm hàng, index có thể không được dùng. Predicate quá rộng lại làm index gần bằng kích thước toàn bảng và mất phần lớn lợi ích.

Hãy đo:

- Tỷ lệ hàng thỏa predicate.
- Tỷ lệ truy vấn thực sự dùng tập con đó.
- Số hàng được đọc và trả về.
- Tần suất hàng chuyển vào hoặc ra khỏi predicate.
- Chi phí tạo, cập nhật, xóa và bảo trì index.

### 9.2. Predicate trên cột trạng thái thay đổi thường xuyên

Một hàng có thể chuyển từ READY sang RUNNING rồi DONE. Khi trạng thái thay đổi, hệ quản trị phải thêm hoặc loại bỏ entry khỏi index có điều kiện. Nếu phần lớn workload là cập nhật trạng thái liên tục, chi phí duy trì index có thể đáng kể.

Với hàng đợi công việc, cân nhắc tốc độ chuyển trạng thái, mức độ tranh chấp khi nhiều worker lấy việc và khả năng index hỗ trợ thứ tự lấy việc. Partial index có thể giảm vùng tìm kiếm, nhưng không tự giải quyết khóa, SKIP LOCKED, transaction dài hoặc contention trên các hàng nóng.

### 9.3. Predicate trên tenant hoặc người dùng

Không nên tạo một partial index riêng cho mỗi tenant nếu số tenant lớn hoặc tenant liên tục thay đổi. Cách này làm số lượng index tăng nhanh, gây áp lực catalog, cache, storage và bảo trì. Thường nên dùng composite index bắt đầu bằng tenant_id, partitioning hoặc chiến lược phù hợp với phân bố tenant.

## 10. Tác động đến ghi dữ liệu và vận hành

Partial/filtered index có thể giảm chi phí ghi so với index toàn bảng nếu phần lớn hàng nằm ngoài predicate và các cột index không thay đổi. Tuy nhiên, mọi thay đổi có thể làm hàng đi vào hoặc ra khỏi tập predicate đều cần cập nhật index.

Ví dụ:

- INSERT một hàng có status = 'OPEN' phải tạo index entry.
- UPDATE status từ CLOSED sang OPEN phải thêm entry.
- UPDATE status từ OPEN sang CLOSED phải xóa entry.
- UPDATE customer_id hoặc created_at của hàng OPEN phải cập nhật key.
- DELETE hàng OPEN phải loại bỏ entry.

Các chỉ mục có điều kiện cũng cần thống kê phù hợp. Sau đợt nạp dữ liệu hoặc thay đổi lớn về tỷ lệ trạng thái, hãy kiểm tra statistics và actual plan. PostgreSQL và SQL Server có thống kê liên quan đến tập được lọc; cách cập nhật và sử dụng khác nhau.

Trước khi tạo index trên production, đánh giá thời gian build, lock behavior, dung lượng, replication lag và ảnh hưởng I/O. Dùng tùy chọn tạo index online/concurrently khi hệ quản trị và quy trình vận hành hỗ trợ; không mặc định mọi engine hoặc mọi loại index đều có cùng mức độ online.

## 11. Quy trình thử nghiệm chỉ mục một phần

1. **Chọn truy vấn từ workload:** xác định truy vấn chậm hoặc thường xuyên dùng một tập con dữ liệu.
2. **Đo tỷ lệ predicate:** thống kê số hàng thỏa và không thỏa điều kiện, cùng xu hướng thay đổi theo thời gian.
3. **Lưu baseline:** SQL, tham số, execution plan, số hàng, logical/physical reads, CPU, elapsed time và trạng thái cache.
4. **Xác minh predicate:** bảo đảm predicate của truy vấn hàm ý predicate index và được optimizer của engine nhận diện.
5. **Thiết kế key:** chọn cột equality, range, join và order phù hợp bên trong tập con.
6. **Kiểm tra khả năng engine:** dùng partial, filtered, function-based hoặc giải pháp mô phỏng đúng với hệ quản trị.
7. **Tạo index trong môi trường thử nghiệm:** ghi thời gian tạo và kích thước index.
8. **Đo lại nhiều tham số:** thử giá trị phổ biến/hiếm, trạng thái khác nhau và prepared statement nếu ứng dụng sử dụng.
9. **Đánh giá ghi:** đo INSERT/UPDATE/DELETE, đặc biệt các thao tác làm hàng đi vào hoặc ra khỏi predicate.
10. **Kiểm tra workload tổng thể:** xem cache, storage, số index, thời gian bảo trì và các truy vấn khác bị ảnh hưởng.
11. **Xác minh tính đúng đắn:** đối chiếu kết quả với truy vấn không dùng index hoặc phương án baseline.
12. **Theo dõi sau triển khai:** xác nhận optimizer tiếp tục chọn index khi dữ liệu và phân bố thay đổi.

## 12. Các sai lầm thường gặp

- **Tạo index cho tập con nhưng truy vấn không có predicate tương thích:** optimizer không thể dùng index để trả lời đầy đủ.
- **Cho rằng mọi biểu thức tương đương đều được nhận diện:** bộ chứng minh predicate của engine có giới hạn.
- **Dùng điều kiện phụ thuộc đồng hồ:** tập hàng không tự thay đổi theo thời gian nếu engine không thể duy trì predicate đó.
- **Nhầm generated-column index của MySQL là partial index:** các hàng ngoài tập vẫn có thể có entry chứa NULL.
- **Bỏ qua thứ tự key columns:** predicate giới hạn tập hàng không thay thế việc thiết kế key cho equality, range và ORDER BY.
- **Predicate quá rộng:** index gần bằng toàn bảng nhưng vẫn có chi phí duy trì riêng.
- **Predicate quá hẹp:** nhiều truy vấn thực tế không thể dùng index.
- **Tạo một index cho mỗi tenant:** số index tăng nhanh và khó vận hành.
- **Bỏ qua chuyển trạng thái:** UPDATE có thể thêm/xóa entry và làm tăng write amplification.
- **Chỉ đo SELECT:** bỏ qua INSERT, UPDATE, DELETE, build index và bảo trì.
- **Không thử prepared statement:** plan cache hoặc tham số có thể làm optimizer không chứng minh được predicate.

## 13. Checklist đánh giá phạm vi áp dụng

- [ ] Đã chọn truy vấn có số liệu và tần suất thực tế.
- [ ] Đã đo tỷ lệ hàng thỏa predicate và mức độ ổn định của tập con.
- [ ] Đã xác định predicate của truy vấn hàm ý predicate của index.
- [ ] Đã kiểm tra giới hạn predicate và cú pháp của hệ quản trị.
- [ ] Đã phân biệt predicate chọn hàng với key columns phục vụ tìm kiếm/sắp xếp.
- [ ] Đã kiểm tra tham số hóa, prepared statement và plan cache.
- [ ] Đã xác nhận actual execution plan dùng index dự kiến.
- [ ] Đã đo logical reads, physical reads, thời gian và kích thước index.
- [ ] Đã đánh giá INSERT/UPDATE/DELETE và thay đổi trạng thái.
- [ ] Đã cân nhắc unique constraint, NULL semantics và tính đúng đắn nghiệp vụ.
- [ ] Đã so sánh lợi ích với composite index hoặc partitioning khi phù hợp.
- [ ] Đã kiểm tra ảnh hưởng đến toàn workload và quy trình bảo trì.

Chỉ mục một phần hoặc có điều kiện phát huy hiệu quả khi một tập con nhỏ, ổn định và được truy vấn thường xuyên. Predicate quyết định hàng nào được lưu; key columns quyết định cách tìm kiếm và thứ tự dữ liệu. Hãy xác nhận optimizer có thể chứng minh điều kiện truy vấn phù hợp, hiểu đúng cơ chế của từng hệ quản trị và đo cả lợi ích đọc lẫn chi phí ghi trước khi đưa chỉ mục vào vận hành.
