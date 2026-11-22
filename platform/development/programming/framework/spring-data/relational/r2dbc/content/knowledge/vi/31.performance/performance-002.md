# Đọc kế hoạch thực thi SQL và lựa chọn chỉ mục

Trong Spring Data Relational R2DBC, một repository method hoặc câu SQL của `DatabaseClient` cuối cùng vẫn được database optimizer chuyển thành một kế hoạch thực thi vật lý. Kế hoạch đó quyết định database đọc bảng bằng cách quét tuần tự hay dùng index, nối bảng theo thuật toán nào, sắp xếp ở đâu và cần bao nhiêu lần đọc dữ liệu.

Muốn cải thiện hiệu năng, cần đọc execution plan của chính câu SQL đang chạy với dữ liệu và tham số gần thực tế. Sau đó mới quyết định có cần tạo index, thay đổi thứ tự cột trong composite index, viết lại predicate, giảm số row được đọc hay thay đổi cách phân trang.

Một số nguyên tắc quan trọng:

- Index không phải lúc nào cũng nhanh hơn table scan. Với truy vấn lấy phần lớn bảng, sequential scan có thể rẻ hơn.
- Execution plan là quyết định của optimizer dựa trên thống kê, cấu hình, phiên bản, tham số và dữ liệu hiện tại.
- Estimated rows khác actual rows là dấu hiệu cần xem lại statistics, skew hoặc giả định của optimizer.
- Composite index phải được thiết kế theo predicate, join và order by thực tế; chỉ thêm mọi cột vào index không phải chiến lược tốt.
- `EXPLAIN ANALYZE` hoặc actual execution plan thường thực thi câu SQL thật. Cần đặc biệt cẩn thận với INSERT, UPDATE, DELETE và truy vấn có side effect.
- R2DBC không tự tạo index. Ứng dụng cần quản lý index bằng migration/schema và đo lại bằng database/driver thực tế.

## 1. Execution plan là gì?

Execution plan là mô tả cách database dự định hoặc đã thực hiện một câu SQL. SQL mô tả kết quả mong muốn; optimizer chọn cách thực hiện để lấy kết quả đó.

Ví dụ:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Optimizer có thể lựa chọn:

- Quét toàn bộ bảng `orders`, lọc theo tenant và status, sort rồi lấy 20 dòng.
- Dùng index bắt đầu bằng `tenant_id` và `status`, đọc theo `created_at` rồi dừng sau 20 dòng.
- Dùng một index để tìm row ID, sau đó truy cập table/heap để lấy các cột còn lại.
- Dùng index scan hoặc bitmap scan tùy hệ quản trị và số row dự kiến.

Các lựa chọn có chi phí khác nhau. Index phù hợp có thể giảm số row cần đọc và loại bỏ sort. Index không phù hợp có thể làm tăng I/O, random access và chi phí cập nhật.

## 2. Optimizer lựa chọn kế hoạch như thế nào?

Optimizer thường thực hiện các bước khái quát:

1. Parse SQL và kiểm tra cú pháp.
2. Resolve bảng, cột, kiểu dữ liệu và quyền truy cập.
3. Viết lại biểu thức hoặc chuẩn hóa query khi có thể.
4. Xây dựng các phương án scan, join, filter, sort và aggregate.
5. Ước lượng số row, I/O, CPU, memory và chi phí liên quan.
6. Chọn phương án có cost ước lượng thấp theo cost model.
7. Thực thi kế hoạch.

Cost là đơn vị nội bộ của optimizer, không phải số mili giây. Cost 100 không có nghĩa truy vấn mất 100 ms, và cost 200 không nhất thiết chạy chậm gấp đôi cost 100.

Optimizer dựa vào statistics như:

- Số row của bảng.
- Số giá trị phân biệt của một cột.
- Tần suất các giá trị phổ biến.
- Histogram hoặc phân bố dữ liệu.
- Số trang dữ liệu và index.
- Tương quan giữa các giá trị theo khả năng thống kê của database.

Nếu statistics cũ hoặc không đại diện, optimizer có thể ước lượng sai và chọn kế hoạch không phù hợp.

## 3. Phân biệt estimated plan và actual plan

Có hai loại thông tin thường gặp:

| Loại | Ý nghĩa |
|---|---|
| Estimated execution plan | Kế hoạch optimizer dự định dùng, kèm ước lượng |
| Actual execution plan | Kế hoạch thực sự đã chạy và số liệu runtime thực tế |

Estimated plan hữu ích khi muốn xem lựa chọn của optimizer mà không chạy query. Actual plan cho biết số row thực tế, số vòng lặp, thời gian hoặc I/O tùy database.

Không phải hệ quản trị nào cũng dùng cùng thuật ngữ. PostgreSQL thường dùng `EXPLAIN` và `EXPLAIN ANALYZE`; SQL Server có estimated/actual execution plan; Oracle có `EXPLAIN PLAN` và plan của cursor đã chạy; MySQL có `EXPLAIN ANALYZE`; SQLite có `EXPLAIN QUERY PLAN`.

### Cẩn thận với EXPLAIN ANALYZE

`EXPLAIN ANALYZE` thực thi câu SQL để thu số liệu. Với SELECT, nó thực sự chạy truy vấn. Với DML, nó có thể thực hiện thay đổi dữ liệu.

Trước khi chạy actual plan cho câu ghi:

- Dùng dữ liệu thử hoặc môi trường staging khi phù hợp.
- Có thể bao trong transaction rồi rollback nếu database hỗ trợ và thao tác không gây side effect bên ngoài.
- Nhớ rằng trigger, sequence, external function hoặc side effect không transactional có thể không được hoàn tác như mong đợi.
- Không chạy DML nguy hiểm trên production chỉ để xem plan.

## 4. Đọc các thành phần phổ biến trong execution plan

Tên node khác nhau theo database, nhưng nhiều khái niệm tương tự:

| Thành phần | Ý nghĩa |
|---|---|
| Table/Sequential Scan | Đọc lần lượt các row hoặc page của bảng |
| Index Seek/Index Scan | Dùng cấu trúc index để tìm hoặc duyệt key |
| Bitmap Index/Heap Scan | Kết hợp row location từ index rồi đọc heap theo nhóm |
| Nested Loop | Với mỗi row bên ngoài, tìm row tương ứng bên trong |
| Hash Join | Tạo hash table từ một phía rồi dò phía còn lại |
| Merge Join | Ghép hai đầu vào đã được sắp xếp theo join key |
| Sort | Sắp xếp row theo thứ tự cần thiết |
| Aggregate | Tính COUNT, SUM, GROUP BY hoặc aggregate khác |
| Filter | Loại bỏ row không thỏa điều kiện |
| Limit/Top | Dừng hoặc giới hạn số row trả về |

Một kế hoạch thường là cây node. Node ở dưới tạo dữ liệu cho node cha; node trên cùng thường biểu diễn kết quả cuối.

~~~text
Limit
  |
  v
Index Scan
  |
  v
Index trên (tenant_id, status, created_at)
~~~

Đây là ví dụ khái niệm. Kế hoạch thực tế có thể thêm filter, heap fetch, sort hoặc node khác.

## 5. Những con số cần đọc

### Estimated rows và actual rows

Estimated rows là số row optimizer dự đoán. Actual rows là số row thực tế node phát ra khi chạy.

Nếu estimated rows là 10 nhưng actual rows là 100.000, optimizer đã đánh giá thấp quy mô dữ liệu. Điều này có thể khiến nó chọn nested loop hoặc memory allocation không phù hợp.

Nếu sai lệch lớn:

- Kiểm tra statistics có mới không.
- Kiểm tra giá trị tham số có bị skew không.
- Kiểm tra predicate có dùng function/cast khiến thống kê khó áp dụng không.
- Kiểm tra correlation giữa các cột.
- Xem database có extended/multicolumn statistics và có cần tạo không.

### Loops

Một node có thể được gọi nhiều lần. Actual rows hiển thị theo từng lần gọi hoặc tổng tùy công cụ, nên cần đọc cùng `loops`.

Ví dụ nested loop có inner index scan chạy 10.000 lần. Mỗi lần chỉ đọc 1 row nhưng tổng số lần truy cập có thể lớn.

### Cost

Nhiều optimizer hiển thị startup cost và total cost. Đây là cost ước lượng, không phải thời gian thực. Dùng nó để so sánh node trong cùng kế hoạch và cùng hệ quản trị, không quy đổi trực tiếp thành milliseconds.

### Actual time

Một số công cụ hiển thị thời gian thực tế theo node. Thời gian có thể cộng dồn theo loops hoặc được đo theo cách riêng của database. Không cộng máy móc mọi node vì node cha và con có thể chạy lồng nhau.

### Buffers và I/O

Buffer hit cho biết dữ liệu được tìm thấy trong cache/buffer; read cho biết database phải đọc page vào buffer từ tầng lưu trữ theo cách database báo cáo.

Số buffer lớn có thể chỉ ra truy vấn đọc quá nhiều page. Tuy nhiên, buffer hit cao vẫn tiêu tốn CPU và memory bandwidth; cache hit không làm một truy vấn quét hàng triệu row trở thành miễn phí.

### Rows removed by filter

Nếu một node đọc nhiều row nhưng loại bỏ phần lớn bằng filter phía sau, có thể index chưa hỗ trợ đủ predicate hoặc optimizer chọn scan do ước lượng cost. Đây là tín hiệu để xem xét index và query shape.

## 6. Khi nào table scan là lựa chọn tốt?

Sequential scan không phải lỗi. Nếu truy vấn cần phần lớn row của bảng, đọc tuần tự có thể hiệu quả hơn việc:

1. Dò index.
2. Lấy danh sách row location.
3. Nhảy đến nhiều page của bảng để lấy dữ liệu.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE created_at >= :startTime;
~~~

Nếu phần lớn đơn hàng được tạo sau thời điểm đó, optimizer có thể chọn table scan. Thêm index `created_at` chưa chắc cải thiện truy vấn và sẽ làm tăng chi phí ghi.

Không nên ép index chỉ vì thấy chữ Seq Scan hoặc Table Scan. Trước hết cần biết số row được trả về, tỷ lệ dữ liệu cần đọc và actual I/O.

## 7. Index là gì?

Index là cấu trúc dữ liệu phụ giúp database tìm row theo một hoặc nhiều thuộc tính mà không phải quét toàn bộ bảng trong mọi trường hợp.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);
~~~

Truy vấn:

~~~sql
SELECT id, status
FROM orders
WHERE tenant_id = :tenantId;
~~~

Index trên tenant_id có thể giúp tìm các row của một tenant nhanh hơn nếu tenant đó chiếm tỷ lệ nhỏ của bảng.

Index thường được tổ chức theo B-tree trong các trường hợp thông thường. Database cũng hỗ trợ loại index khác như hash, GIN, GiST, full-text, spatial hoặc bitmap tùy hệ quản trị và loại dữ liệu.

Index có chi phí:

- Tốn dung lượng lưu trữ.
- Mỗi INSERT có thể phải cập nhật index.
- UPDATE cột thuộc index có thể phải sửa cấu trúc index.
- DELETE cần loại bỏ entry.
- Nhiều index làm tăng write amplification, cache pressure và thời gian bảo trì.

Vì vậy, tạo index theo query workload thực tế, không tạo index cho mọi cột.

## 8. B-tree index và các phép so sánh

B-tree thường phù hợp với:

- Equality: `column = value`.
- Range: `column >= value`, `column BETWEEN a AND b`.
- Sắp xếp theo cột index.
- Prefix matching của chuỗi trong một số collation/kiểu dữ liệu.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);
~~~

Có thể hỗ trợ:

~~~sql
SELECT id, status
FROM orders
WHERE created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at;
~~~

Index có thể giúp lọc range và trả kết quả theo thứ tự. Nếu truy vấn chọn phần lớn bảng, optimizer vẫn có thể chọn scan.

## 9. Thiết kế composite index

Composite index chứa nhiều cột theo một thứ tự cụ thể:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Thứ tự cột rất quan trọng. Với B-tree, nhiều hệ quản trị có thể sử dụng prefix bên trái của index hiệu quả.

Index (tenant_id, status, created_at) thường phù hợp với:

~~~sql
WHERE tenant_id = :tenantId
~~~

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
~~~

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :fromTime
~~~

Nhưng không nhất thiết hiệu quả với:

~~~sql
WHERE status = :status
~~~

vì không có điều kiện trên cột đầu tiên tenant_id. Một số optimizer có kỹ thuật skip scan hoặc lựa chọn khác, nhưng không nên dựa vào nó như quy tắc portable.

### Equality trước range là một điểm bắt đầu hữu ích

Với truy vấn:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at DESC
~~~

Một index hợp lý để thử:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Các cột equality thường đứng trước cột range/order. Tuy nhiên, không có quy tắc “cột có selectivity cao nhất luôn phải đứng đầu” áp dụng cho mọi query. Hãy xem toàn bộ workload, điều kiện prefix, join, sort và các query khác cùng dùng index.

### Thứ tự cột phải theo query workload

Nếu có hai query:

~~~sql
WHERE tenant_id = :tenantId AND status = :status
~~~

và:

~~~sql
WHERE tenant_id = :tenantId AND created_at >= :fromTime
~~~

index (tenant_id, status, created_at) có thể phục vụ query đầu rất tốt, nhưng query thứ hai không thể luôn dùng phần created_at như một range liên tục sau khi bỏ qua status. Có thể cần index khác (tenant_id, created_at) nếu workload đủ quan trọng.

Mỗi index bổ sung đều có chi phí ghi và lưu trữ. Hãy ưu tiên các query có tần suất cao, latency lớn hoặc ảnh hưởng trực tiếp tới SLA.

## 10. Index cho ORDER BY và LIMIT

Truy vấn danh sách gần đây:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC
LIMIT 50;
~~~

Index:

~~~sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at DESC);
~~~

Index có thể cho phép database tìm phạm vi tenant và đọc theo thứ tự mới nhất, dừng sau 50 row mà không sort toàn bộ tập kết quả.

Nếu query còn lọc status:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC
LIMIT 50
~~~

có thể thử (tenant_id, status, created_at DESC).

Không phải mọi database đều cần ghi rõ DESC để quét ngược B-tree; khả năng hỗ trợ thứ tự đảo phụ thuộc cấu trúc index và hệ quản trị. Khi có nhiều cột sort với hướng ASC/DESC khác nhau, khai báo direction có thể quan trọng hơn.

## 11. Covering index và index-only scan

Nếu query chỉ đọc các cột có trong index, database có thể tránh truy cập bảng hoặc heap cho một số trường hợp.

Ví dụ:

~~~sql
SELECT tenant_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

Một index chứa các cột cần đọc:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

đôi khi có thể trở thành covering index cho query này.

Một số hệ quản trị hỗ trợ cột INCLUDE riêng:

~~~sql
-- PostgreSQL
CREATE INDEX idx_orders_tenant_status
ON orders (tenant_id, status)
INCLUDE (created_at);
~~~

~~~sql
-- SQL Server
CREATE INDEX IX_orders_tenant_status
ON dbo.orders (tenant_id, status)
INCLUDE (created_at);
~~~

INCLUDE không phải cú pháp portable. MySQL thường đạt covering index bằng cách thêm cột vào key definition; PostgreSQL và SQL Server có semantics INCLUDE riêng.

Index-only scan không phải lúc nào cũng tránh hoàn toàn việc đọc heap. Ví dụ PostgreSQL cần visibility map phù hợp để xác nhận row visibility mà không truy cập heap. Actual plan sẽ cho biết có heap fetch hay không.

Đừng đưa các cột rất lớn như JSON hoặc text vào index chỉ để tạo covering index nếu lợi ích đọc không bù được kích thước và chi phí ghi.

## 12. Partial index và filtered index

Nếu truy vấn thường xuyên chỉ lấy một tập con ổn định của bảng, index có điều kiện có thể giảm kích thước.

Ví dụ PostgreSQL partial index:

~~~sql
CREATE INDEX idx_orders_open_tenant_created
ON orders (tenant_id, created_at DESC)
WHERE status = 'OPEN';
~~~

Query có predicate phù hợp:

~~~sql
SELECT id, created_at
FROM orders
WHERE status = 'OPEN'
  AND tenant_id = :tenantId
ORDER BY created_at DESC;
~~~

Index chỉ chứa row thỏa điều kiện status = 'OPEN'.

SQL Server có filtered index:

~~~sql
CREATE INDEX IX_orders_open_tenant_created
ON dbo.orders (tenant_id, created_at DESC)
WHERE status = 'OPEN';
~~~

Partial/filtered index không được hỗ trợ cùng cú pháp trên mọi hệ quản trị. MySQL không có partial index tổng quát giống PostgreSQL; có thể phải dùng generated column, functional index hoặc thiết kế schema/query khác.

Optimizer chỉ dùng partial index khi có thể chứng minh predicate query phù hợp với predicate index. Query parameter hóa status có thể làm việc chứng minh này phức tạp hơn tùy database và plan mode. Hãy kiểm tra actual plan với cách bind thực tế.

## 13. Expression index và functional index

Nếu query lọc theo một biểu thức:

~~~sql
SELECT id, email
FROM customer
WHERE LOWER(email) = LOWER(:email);
~~~

Index thường trên email có thể không được dùng như mong đợi vì predicate áp dụng function lên cột.

PostgreSQL hỗ trợ expression index:

~~~sql
CREATE INDEX idx_customer_lower_email
ON customer (LOWER(email));
~~~

Một số hệ quản trị khác hỗ trợ functional index hoặc index trên computed/generated column với cú pháp riêng.

Điều kiện query phải khớp biểu thức hoặc semantics mà optimizer nhận diện. Không phải cứ tạo index trên LOWER(email) là mọi biểu thức tương đương đều dùng được.

Nếu có thể chuẩn hóa email khi ghi và lưu một cột normalized riêng, query có thể trở nên đơn giản hơn. Cần quyết định rõ quy tắc Unicode, collation và case folding; LOWER() không tự giải quyết mọi quy tắc chuẩn hóa email quốc tế.

## 14. Sargable predicate

Predicate sargable là điều kiện cho phép optimizer tận dụng index để xác định phạm vi tìm kiếm hiệu quả. Một số dạng query làm index khó được sử dụng:

### Function trên cột được index

Không thuận lợi:

~~~sql
WHERE DATE(created_at) = :day
~~~

Thường tốt hơn:

~~~sql
WHERE created_at >= :dayStart
  AND created_at < :nextDayStart
~~~

### Cast hoặc chuyển kiểu trên cột

Không thuận lợi:

~~~sql
WHERE CAST(customer_id AS VARCHAR(30)) = :customerId
~~~

Tốt hơn là bind đúng kiểu của cột:

~~~sql
WHERE customer_id = :customerId
~~~

Tránh để database phải chuyển đổi từng giá trị của cột trong lúc lọc.

### Wildcard ở đầu LIKE

~~~sql
WHERE name LIKE '%nguyen'
~~~

B-tree thông thường thường không hỗ trợ tìm prefix khi wildcard nằm đầu chuỗi. Có thể cần full-text, trigram, specialized text index hoặc search service tùy yêu cầu.

Ngược lại:

~~~sql
WHERE name LIKE 'nguyen%'
~~~

có thể dùng B-tree trong một số collation/kiểu dữ liệu và database.

### OR giữa nhiều cột

~~~sql
WHERE email = :value OR phone = :value
~~~

Optimizer có thể kết hợp nhiều index, nhưng kết quả tùy database và selectivity. Có thể so sánh với UNION/UNION ALL hoặc thiết kế query khác, nhưng phải giữ đúng semantics loại bỏ trùng và NULL.

## 15. Index cho JOIN và foreign key

Ví dụ:

~~~sql
SELECT o.id, o.created_at, c.name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.tenant_id = :tenantId;
~~~

Các index có thể cần:

~~~sql
CREATE INDEX idx_orders_tenant_customer
ON orders (tenant_id, customer_id);
~~~

Primary key của customer thường đã có index trên customer.id. Nhưng index trên orders.customer_id không phải lúc nào cũng tự được tạo khi khai báo foreign key; điều này tùy hệ quản trị.

Index trên cột foreign key thường giúp:

- Tìm các child row theo parent.
- Thực hiện join.
- Kiểm tra hoặc xử lý delete/update parent trong một số database.

Không nên tạo index trên mọi foreign key mà không xem query workload. Với bảng nhỏ hoặc cột có ít truy vấn, lợi ích có thể không đáng kể; với bảng child lớn, index thường rất hữu ích.

## 16. Chọn loại JOIN qua execution plan

### Nested Loop

Nested Loop thường phù hợp khi tập bên ngoài nhỏ và tập bên trong có index lookup hiệu quả.

~~~text
Nested Loop
  -> Scan nhỏ trên customer
  -> Index lookup trên orders(customer_id)
~~~

Nếu outer side có 10 row và inner index lookup rất rẻ, nested loop có thể nhanh. Nếu outer side thực tế có 100.000 row nhưng optimizer ước lượng 10, inner lookup lặp nhiều lần có thể rất tốn kém.

### Hash Join

Hash Join thường phù hợp với tập dữ liệu lớn hơn khi database có thể xây hash table trong memory và dò tập còn lại. Nó có thể spill ra disk nếu memory không đủ.

### Merge Join

Merge Join có thể hiệu quả khi hai đầu vào đã được sắp xếp theo join key hoặc có thể lấy từ index theo thứ tự phù hợp. Nếu phải sort cả hai phía, chi phí sort cần được tính đến.

Không nên ép join algorithm trước khi xác định nguyên nhân. Hãy so estimated/actual rows, số lần lặp, I/O và spill. Thường sửa statistics, index hoặc query shape sẽ bền vững hơn hint cố định.

## 17. Index cho GROUP BY và aggregate

Query:

~~~sql
SELECT status, COUNT(*)
FROM orders
WHERE tenant_id = :tenantId
GROUP BY status;
~~~

Index (tenant_id, status) có thể giúp lọc theo tenant và có dữ liệu theo thứ tự status. Nhưng aggregate vẫn phải đọc số row phù hợp để đếm; index không làm COUNT(*) miễn phí nếu cần xét toàn bộ row trong nhóm.

Với aggregate rất thường xuyên và dữ liệu lớn, có thể cần materialized view, summary table, counter được cập nhật có kiểm soát hoặc hệ thống analytics riêng. Đừng tạo index để thay thế một mô hình tổng hợp dữ liệu không phù hợp.

## 18. Đọc EXPLAIN trên PostgreSQL

Kế hoạch ước lượng:

~~~sql
EXPLAIN
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Kế hoạch kèm runtime:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Các thông tin cần xem:

- Seq Scan, Index Scan, Index Only Scan, Bitmap Index Scan, Bitmap Heap Scan.
- rows ước lượng và actual rows.
- loops.
- Planning Time và Execution Time.
- Buffers: shared hit/read, local hoặc temp buffers nếu có.
- Rows Removed by Filter.
- Sort method và disk spill.
- Heap Fetches của Index Only Scan.

EXPLAIN ANALYZE chạy statement thật. Với DML, cần dùng môi trường an toàn hoặc transaction rollback có kiểm soát.

### ANALYZE và statistics

Trong PostgreSQL, lệnh ANALYZE cập nhật statistics cho optimizer:

~~~sql
ANALYZE orders;
~~~

ANALYZE ở đây khác với tùy chọn EXPLAIN ANALYZE. Một lệnh cập nhật statistics; lệnh kia thực thi query để đo runtime.

Khi một cột có phân bố lệch, có thể cần tăng statistics target hoặc dùng extended statistics cho nhóm cột có tương quan. Chỉ làm sau khi plan và số liệu cho thấy optimizer ước lượng sai.

## 19. Đọc EXPLAIN trên MySQL

MySQL hỗ trợ:

~~~sql
EXPLAIN
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Có thể dùng format TREE trên các phiên bản hỗ trợ:

~~~sql
EXPLAIN FORMAT=TREE
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE trong các phiên bản MySQL hỗ trợ sẽ thực thi query và cung cấp actual timing/row information:

~~~sql
EXPLAIN ANALYZE
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Trong output truyền thống, chú ý:

- type: access type như const, eq_ref, ref, range, index, ALL.
- possible_keys: các index optimizer có thể cân nhắc.
- key: index thực sự được chọn.
- key_len: độ dài phần index được sử dụng.
- rows: số row ước lượng.
- filtered: tỷ lệ row còn lại sau filter theo ước lượng.
- Extra: thông tin như Using index, Using where, Using filesort, Using temporary.

type = ALL thường biểu thị table scan, nhưng không tự động chứng minh query chậm. Xem số row, tỷ lệ trả về và actual time.

Using filesort không nhất thiết có nghĩa là ghi file xuống disk; đó là tên thuật ngữ của MySQL cho bước sort bổ sung. Kiểm tra actual plan và memory/temp behavior trước khi kết luận.

## 20. Đọc execution plan trên SQL Server

SQL Server có estimated execution plan và actual execution plan trong SQL Server Management Studio hoặc công cụ tương ứng. Có thể bật thống kê:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT id, status, created_at
FROM dbo.orders
WHERE tenant_id = @tenantId
  AND status = @status
ORDER BY created_at DESC;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
~~~

Các node thường gặp:

- Clustered Index Seek/Scan.
- Nonclustered Index Seek/Scan.
- Key Lookup hoặc RID Lookup.
- Nested Loops, Hash Match, Merge Join.
- Sort, Stream Aggregate, Hash Aggregate.

Chú ý:

- Estimated Number of Rows so với Actual Number of Rows.
- Actual Number of Executions.
- Logical reads và physical reads.
- Key Lookup lặp quá nhiều lần.
- Sort/hash spill ra tempdb.
- Memory grant lớn hoặc không đủ.
- Warning về implicit conversion hoặc cardinality estimate.

SQL Server có parameter sniffing: plan được tối ưu dựa trên giá trị parameter ở một lần compile có thể không phù hợp với giá trị có phân bố khác nhiều. Đừng kết luận index sai chỉ từ một lần chạy; hãy kiểm tra workload, Query Store và plan variation.

## 21. Đọc execution plan trên Oracle

Oracle có thể tạo estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

Xem plan:

~~~sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Để xem cursor đã thực thi và runtime statistics khi được thu thập:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Các thông tin cần chú ý:

- TABLE ACCESS FULL.
- INDEX RANGE SCAN, INDEX UNIQUE SCAN.
- NESTED LOOPS, HASH JOIN, MERGE JOIN.
- E-Rows và A-Rows.
- Buffers, Reads, Starts.
- Predicate Information.

EXPLAIN PLAN là ước lượng, không thay thế actual cursor statistics. Để xem runtime chính xác, cần query đã được chạy và statistics được thu thập theo cách phù hợp.

## 22. Đọc EXPLAIN QUERY PLAN trên SQLite

SQLite hỗ trợ:

~~~sql
EXPLAIN QUERY PLAN
SELECT id, status, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC;
~~~

Output thường có các chỉ dẫn:

- SCAN: quét bảng hoặc index.
- SEARCH: tìm một phần dữ liệu theo điều kiện.
- USING INDEX: dùng index.
- USING COVERING INDEX: index cung cấp đủ cột cần thiết.
- USE TEMP B-TREE FOR ORDER BY: cần cấu trúc tạm để sort.

SQLite có optimizer và locking model riêng. Không áp dụng nguyên suy luận từ PostgreSQL/MySQL sang SQLite chỉ vì câu SQL giống nhau.

## 23. Ví dụ đọc một plan và đề xuất index

Query:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC
LIMIT 20;
~~~

Giả sử actual plan cho thấy:

- Table scan đọc 1.000.000 row.
- Filter giữ lại 1.500 row.
- Sort 1.500 row trước khi lấy 20.
- Thời gian và logical reads tập trung ở scan và sort.

Một index để thử:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Index này có thể:

1. Tìm đúng tenant.
2. Giới hạn theo status.
3. Đọc theo created_at giảm dần.
4. Dừng sau 20 row nếu plan phù hợp.

Sau khi tạo index:

1. Cập nhật statistics theo cơ chế database.
2. Chạy lại cùng query với cùng loại parameter.
3. So sánh estimated/actual rows.
4. So sánh buffers/reads/logical reads.
5. Kiểm tra sort có được loại bỏ không.
6. Đo latency nhiều lần trong điều kiện cache tương đương.
7. Đo chi phí INSERT/UPDATE vì index mới cũng phải được duy trì.

Không chỉ nhìn thấy Index Scan là kết luận thành công. Kế hoạch mới phải giảm công việc thực tế và không làm write workload tệ hơn mức chấp nhận được.

## 24. Statistics và cardinality estimation

Optimizer cần ước lượng số row sau mỗi predicate. Ví dụ:

~~~sql
WHERE status = 'OPEN'
~~~

Nếu ước lượng OPEN chiếm 1% nhưng thực tế chiếm 90%, lựa chọn index lookup có thể không hiệu quả. Ngược lại, nếu optimizer nghĩ status OPEN rất phổ biến nhưng thực tế hiếm, nó có thể chọn table scan.

Khi ước lượng sai:

- Kiểm tra statistics có được cập nhật sau bulk load không.
- Kiểm tra histogram và số distinct value.
- Xem phân bố dữ liệu có skew không.
- Xem các cột có tương quan không.
- Kiểm tra kiểu bind và implicit conversion.
- Kiểm tra parameter sniffing hoặc generic plan behavior.

Không chạy lệnh cập nhật statistics liên tục như một cách chữa mọi vấn đề. Statistics update có chi phí và có thể thay đổi plan. Chỉ điều chỉnh khi có bằng chứng.

## 25. Chọn index theo selectivity và workload

Selectivity mô tả mức độ một điều kiện thu hẹp dữ liệu:

- Điều kiện trả 1 trong 1.000.000 row có selectivity cao.
- Điều kiện trả 800.000 trong 1.000.000 row có selectivity thấp.

Index thường có ích khi điều kiện giảm đáng kể số row cần truy cập. Nhưng selectivity không phải tiêu chí duy nhất:

- Query có thể lấy nhiều cột ngoài index.
- Random heap access có thể tốn hơn scan tuần tự.
- Query có LIMIT nhỏ có thể hưởng lợi từ index order.
- Composite index có thể dùng prefix equality.
- Buffer cache và clustering của dữ liệu ảnh hưởng I/O.
- Một index có thể phục vụ nhiều query trong workload.

Đừng xếp cột trong composite index chỉ theo selectivity đơn lẻ. Hãy xem thứ tự điều kiện, prefix, range và ORDER BY.

## 26. Index cho truy vấn phân trang

OFFSET pagination:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC
LIMIT 50 OFFSET 50000;
~~~

Database vẫn có thể phải đi qua nhiều row trước khi bỏ 50.000 row đầu. Index hỗ trợ tenant và created_at giúp thứ tự, nhưng chi phí bỏ qua một offset lớn vẫn còn.

Keyset pagination:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND created_at < :lastSeenCreatedAt
ORDER BY created_at DESC
LIMIT 50;
~~~

Index:

~~~sql
CREATE INDEX idx_orders_tenant_created_id
ON orders (tenant_id, created_at DESC, id DESC);
~~~

Nếu created_at có thể trùng, cần tie-breaker ổn định như id:

~~~sql
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Index và predicate phải khớp với thứ tự sort. Keyset pagination tránh chi phí offset lớn và giảm nguy cơ bản ghi dịch chuyển giữa các trang khi có insert mới, nhưng cần xử lý rõ điều kiện sort và tính ổn định của cursor.

## 27. Index cho truy vấn theo thời gian

Không nên dùng:

~~~sql
WHERE DATE(created_at) = :date
~~~

thay vào đó tạo khoảng nửa mở:

~~~sql
WHERE created_at >= :startOfDay
  AND created_at < :startOfNextDay
~~~

Khoảng nửa mở tránh vấn đề precision ở cuối ngày và thường sargable với B-tree trên created_at.

Nếu dữ liệu rất lớn và chủ yếu truy vấn theo thời gian, cân nhắc:

- B-tree index theo thời điểm.
- Partitioning theo range thời gian.
- BRIN index trong PostgreSQL khi dữ liệu vật lý có tương quan với thời gian.
- Retention/archive để giảm kích thước bảng nóng.

Partitioning không thay thế index cho mọi query. Cần xem partition pruning và index local/global theo database.

## 28. Một số loại index đặc thù

| Loại index | Dùng cho | Ghi chú |
|---|---|---|
| B-tree | Equality, range, order | Loại phổ biến |
| Hash | Equality ở hệ quản trị hỗ trợ | Không hỗ trợ range/order như B-tree |
| GIN | Array, JSONB, full-text trong PostgreSQL | Phù hợp membership/containment |
| GiST | Spatial, range và một số kiểu tìm kiếm | Cần operator class phù hợp |
| BRIN | Bảng rất lớn có tương quan vật lý với giá trị | Index nhỏ, có thể trả nhiều false positives |
| Full-text | Tìm kiếm văn bản | Khác LIKE substring thông thường |
| Spatial | Truy vấn hình học/vị trí | Phụ thuộc database và extension |

Không phải tất cả loại index đều có mặt trên mọi database hoặc được hỗ trợ bởi cùng R2DBC driver. Spring Data R2DBC gửi SQL; việc tạo và sử dụng index thuộc database.

## 29. JSON và index

Nếu query thường xuyên lọc trong JSON, index B-tree trên toàn cột JSON chưa chắc giúp được:

~~~sql
SELECT id
FROM event_log
WHERE payload ->> 'eventType' = :eventType;
~~~

Với PostgreSQL, có thể cân nhắc expression index:

~~~sql
CREATE INDEX idx_event_log_event_type
ON event_log ((payload ->> 'eventType'));
~~~

Nếu query dùng containment hoặc toán tử JSONB khác, GIN index có thể phù hợp hơn:

~~~sql
CREATE INDEX idx_event_log_payload
ON event_log USING GIN (payload);
~~~

Chọn operator class và kiểu index theo toán tử query thực tế. Một index GIN tổng quát không nhất thiết tối ưu cho mọi JSON predicate.

Với MySQL, SQL Server và Oracle, chiến lược JSON index khác nhau, có thể dùng generated/computed column hoặc functional index. Nếu query JSON quan trọng và cần portable, cân nhắc trích trường được truy vấn thường xuyên thành cột quan hệ có kiểu rõ ràng.

## 30. R2DBC và cách xem plan của câu SQL ứng dụng

Repository method có thể sinh SQL dựa trên tên method hoặc query annotation:

~~~java
Flux<Order> findByTenantIdAndStatusOrderByCreatedAtDesc(
    Long tenantId,
    String status
);
~~~

Để tối ưu đúng, cần biết SQL thực tế mà Spring Data tạo ra. Có thể:

- Dùng logging phù hợp của Spring Data/R2DBC trong môi trường development.
- Dùng tracing hoặc datasource/driver instrumentation được hỗ trợ.
- Viết query tường minh bằng @Query hoặc DatabaseClient khi cần kiểm soát.
- Lấy câu SQL và chạy EXPLAIN bằng công cụ của database.

Không bật log bind value nhạy cảm ở production chỉ để đọc query. Dùng query fingerprint hoặc log đã che dữ liệu.

### DatabaseClient với bind parameter

~~~java
Flux<OrderSummary> findRecentOrders(
        Long tenantId,
        String status) {

    return databaseClient.sql(
            "SELECT id, status, created_at " +
            "FROM orders " +
            "WHERE tenant_id = :tenantId " +
            "AND status = :status " +
            "ORDER BY created_at DESC " +
            "LIMIT 50"
        )
        .bind("tenantId", tenantId)
        .bind("status", status)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("status", String.class),
            row.get("created_at", LocalDateTime.class)
        ))
        .all();
}
~~~

Bind parameter giúp tách dữ liệu khỏi SQL và tránh SQL injection. Khi kiểm tra plan, hãy dùng giá trị đại diện và hiểu cách database tối ưu parameterized statement.

Không nối chuỗi giá trị đầu vào vào SQL để tạo plan “giống thật”. Nếu cần thử literal, chỉ dùng dữ liệu kiểm thử không nhạy cảm và giữ query an toàn trong ứng dụng.

## 31. Parameter sniffing và skew trong query parameter

Một query có thể chạy nhanh với tenant nhỏ nhưng chậm với tenant rất lớn:

~~~sql
WHERE tenant_id = :tenantId
~~~

Ví dụ:

- Tenant A có 50 row.
- Tenant B có 5 triệu row.

Một plan phù hợp với tenant A có thể không phù hợp với tenant B. Một số database có parameter sniffing hoặc plan cache; một số có thể tạo generic plan cho prepared statement hoặc thay đổi plan theo cơ chế riêng.

Khi latency không ổn định theo parameter:

1. Đo riêng các nhóm giá trị nhỏ, trung bình và lớn.
2. So sánh estimated/actual rows.
3. Kiểm tra plan cache hoặc Query Store theo database.
4. Xem thống kê có mô tả được skew không.
5. Chỉ dùng hint/recompile hoặc tách query khi đã chứng minh cần thiết.

Không giả định mỗi lần R2DBC bind parameter sẽ tạo một plan hoàn toàn mới. Plan caching phụ thuộc database, driver và cách prepared statement được dùng.

## 32. Index và chi phí ghi

Mỗi index là một cấu trúc cần duy trì:

- INSERT phải thêm entry vào các index liên quan.
- UPDATE cột index có thể thay đổi entry.
- DELETE phải xóa entry.
- Index lớn làm tăng disk usage và cache pressure.
- Index có thể làm tăng thời gian migration, vacuum/rebuild và replication traffic.

Ví dụ bảng orders có 12 index có thể đọc nhanh nhiều query, nhưng insert hàng chục nghìn row/giây có thể bị chậm do duy trì các index đó.

Khi thêm index:

1. Xác định query cần cải thiện.
2. Đo latency và I/O trước.
3. Tạo index trong migration có thể rollback hoặc có quy trình vận hành an toàn.
4. Đo lại read workload.
5. Đo write throughput và kích thước index.
6. Kiểm tra index trùng lặp hoặc không còn dùng.

Không xóa index chỉ vì một báo cáo nói ít được sử dụng nếu nó bảo vệ unique constraint hoặc phục vụ workload hiếm nhưng quan trọng.

## 33. Index và unique constraint

PRIMARY KEY và UNIQUE constraint thường được database bảo đảm bằng index hoặc cấu trúc tương đương. Chúng vừa bảo vệ tính toàn vẹn vừa có thể phục vụ truy vấn.

Ví dụ:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
~~~

Không cần tạo thêm một index giống hệt trên email nếu unique constraint đã tạo index tương ứng. Tạo index trùng có thể tăng write cost mà không đem lại lợi ích.

Một index không unique không thay thế unique constraint. Nếu dữ liệu phải duy nhất, hãy thể hiện quy tắc ở database để chống race condition giữa các transaction.

## 34. Đọc dấu hiệu sort và temporary work

Nếu plan có Sort hoặc Using filesort, hãy xem:

- Số row đi vào sort.
- Sort key có thể được cung cấp bởi index không.
- Sort có spill ra disk hoặc tempdb không.
- Query có LIMIT nhỏ nhưng vẫn sort rất nhiều row không.
- Composite index có thể hỗ trợ cả filter và order không.

Index (tenant_id, status, created_at DESC) có thể loại bỏ sort cho một query cụ thể. Nhưng nếu index cần thêm quá nhiều cột hoặc làm tăng chi phí ghi, có thể chấp nhận sort trên tập kết quả nhỏ hơn.

Sort không luôn xấu. Với vài chục row, sort trong memory có thể rẻ hơn duy trì một index lớn chỉ để loại bỏ bước sort đó.

## 35. Khi nào cần partition thay vì thêm index?

Nếu bảng rất lớn và query thường giới hạn theo một chiều tự nhiên như thời gian hoặc tenant, partitioning có thể giảm tập dữ liệu cần xét thông qua partition pruning.

Ví dụ phân vùng theo tháng:

~~~text
orders_2026_01
orders_2026_02
orders_2026_03
...
~~~

Query có predicate thời gian phù hợp có thể chỉ đọc một số partition. Tuy nhiên:

- Partition key phải xuất hiện trong predicate để pruning hiệu quả.
- Mỗi partition vẫn có thể cần index riêng.
- Unique constraint trên partitioned table có giới hạn riêng theo database.
- Quản lý migration, retention và query across partitions phức tạp hơn.

Không partition chỉ vì bảng có nhiều row. Hãy xác định bottleneck, phân bố dữ liệu, retention và khả năng pruning trước.

## 36. Quy trình tối ưu một query R2DBC

Một quy trình thực tế:

1. Xác định repository method hoặc SQL đang chậm.
2. Lấy SQL thực tế và bind parameter đại diện.
3. Đo latency, throughput và tần suất query.
4. Chạy estimated plan.
5. Chạy actual plan ở môi trường an toàn.
6. Tìm node đọc nhiều row/page, sort lớn, loop nhiều hoặc spill.
7. So estimated rows với actual rows.
8. Kiểm tra statistics và kiểu bind.
9. Đề xuất query rewrite hoặc index có mục tiêu.
10. Tạo index qua migration.
11. Cập nhật statistics theo cơ chế database.
12. Chạy lại plan với cùng workload.
13. Đo cả read performance và write overhead.
14. Giữ thay đổi khi cải thiện được xác nhận và không làm workload quan trọng khác suy giảm quá mức.

Tối ưu query là quá trình đo và so sánh, không phải cuộc thi tạo nhiều index nhất.

## 37. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Thấy Seq Scan là kết luận cần index | Có thể làm query chậm hơn | Xem tỷ lệ row trả về và actual I/O |
| Đọc cost như milliseconds | Đánh giá sai mức chênh lệch | Dùng actual time và I/O |
| Chỉ xem estimated plan | Bỏ lỡ sai lệch cardinality | Lấy actual plan ở môi trường an toàn |
| Chạy EXPLAIN ANALYZE trên DML production | Thay đổi dữ liệu thật | Dùng staging hoặc transaction rollback có kiểm soát |
| Không cập nhật statistics sau bulk load | Optimizer chọn plan dựa trên dữ liệu cũ | Chạy statistics maintenance phù hợp |
| Tạo index một cột trong khi query lọc nhiều cột | Vẫn phải lọc nhiều row hoặc sort | Thiết kế composite index theo query |
| Đặt cột composite index tùy tiện | Không dùng được prefix mong muốn | Xem equality, range, join và order |
| Dùng function trên indexed column | Index có thể không được dùng | Viết predicate sargable hoặc expression index |
| Index quá nhiều | Ghi chậm và tốn storage | Theo dõi workload và loại index dư thừa |
| Chỉ đo tenant nhỏ | Query tenant lớn có plan khác | Kiểm thử nhiều nhóm parameter |
| Nghĩ index-only scan luôn không đọc bảng | Có thể vẫn heap fetch | Xem actual plan và visibility/statistics |
| Dùng OFFSET rất lớn | Database phải bỏ qua nhiều row | Cân nhắc keyset pagination |
| Tạo index giống unique constraint | Tốn thêm chi phí ghi | Kiểm tra index đã được constraint tạo |
| Dùng plan từ DB khác để suy luận | Optimizer và dialect khác nhau | Đo trên đúng database/driver |
| Log bind values nhạy cảm ở production | Lộ dữ liệu | Che tham số hoặc dùng query fingerprint |

## 38. Checklist lựa chọn index

Trước khi tạo index, hãy trả lời:

1. Query nào cần được tối ưu và tần suất chạy là bao nhiêu?
2. Predicate equality, range và join key là gì?
3. Query có ORDER BY, LIMIT hoặc GROUP BY không?
4. Số row thực tế sau filter là bao nhiêu?
5. Optimizer đang scan, seek, lookup hay sort?
6. Estimated rows có gần actual rows không?
7. Có function, cast, wildcard đầu chuỗi hoặc biểu thức làm predicate kém sargable không?
8. Composite index cần prefix nào?
9. Có thể dùng covering/INCLUDE, partial hoặc expression index không?
10. Index mới có trùng với primary key, unique constraint hoặc index khác không?
11. Chi phí INSERT/UPDATE/DELETE tăng bao nhiêu?
12. Database có giới hạn index key, chiều dài cột hoặc kiểu dữ liệu không?
13. Đã thử trên dữ liệu có phân bố giống production chưa?
14. Đã đo lại query và write workload sau khi tạo index chưa?

## 39. Ghi nhớ

- Execution plan cho biết database thực hiện SQL bằng scan, index, join, sort và aggregate như thế nào.
- Estimated plan cho biết dự đoán; actual plan cho biết runtime statistics. EXPLAIN ANALYZE thực thi câu SQL.
- Cost là đơn vị nội bộ của optimizer, không phải milliseconds.
- So estimated rows với actual rows để phát hiện cardinality estimation sai.
- Sequential scan có thể là lựa chọn tốt nếu query cần phần lớn bảng.
- B-tree hỗ trợ equality, range và order trong các điều kiện phù hợp.
- Composite index phải theo predicate, join và ORDER BY; thứ tự cột quyết định prefix có thể sử dụng.
- Covering/index-only scan có thể giảm table lookup nhưng còn phụ thuộc database và trạng thái dữ liệu.
- Partial/filtered, expression, GIN, GiST, BRIN và full-text index là các khả năng đặc thù cần kiểm tra theo hệ quản trị.
- Predicate sargable giúp optimizer tận dụng index; tránh function/cast không cần thiết trên cột được lọc.
- Statistics và data skew ảnh hưởng trực tiếp đến lựa chọn plan.
- Parameterized query có thể có plan khác theo giá trị bind, plan cache và parameter sniffing.
- Index tăng tốc một số truy vấn đọc nhưng làm tăng storage và chi phí ghi.
- Repository và DatabaseClient không tự tạo index; quản lý index qua schema migration.
- Đọc plan trên đúng database, đúng driver và dữ liệu đại diện; đo cả read và write sau thay đổi.
