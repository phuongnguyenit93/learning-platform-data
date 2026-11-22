# Đọc execution plan và thiết kế chỉ mục theo điều kiện truy vấn

Trong **Spring Data Relational JDBC**, repository method và câu SQL trong **@Query** cuối cùng vẫn được database thực thi. Tốc độ không phụ thuộc riêng vào Java hay Spring Data; database phải tìm các hàng phù hợp, join bảng, sắp xếp và trả kết quả. Khi dữ liệu tăng, một truy vấn từng chạy nhanh có thể trở thành nút thắt nếu database phải quét quá nhiều hàng hoặc sắp xếp một tập dữ liệu lớn.

Hai công cụ quan trọng để cải thiện truy vấn là:

- **Execution plan:** cho biết database dự định hoặc thực tế thực hiện truy vấn bằng những bước nào.
- **Index:** cấu trúc dữ liệu phụ giúp database tìm hàng theo điều kiện lọc, join hoặc thứ tự sắp xếp mà không phải quét toàn bộ bảng.

Thiết kế index phải bắt đầu từ truy vấn thực tế: cột nào xuất hiện trong WHERE, điều kiện nào là equality/range, bảng nào tham gia join, có ORDER BY/LIMIT hay không và truy vấn trả về những cột nào. Sau đó đọc execution plan và đo lại trên dữ liệu đại diện.

## 1. Execution plan là gì?

Execution plan (kế hoạch thực thi) là cách database dự định dùng để thực hiện một câu SQL. Tùy database, plan có thể mô tả:

- Cách đọc dữ liệu: sequential/table scan, index scan, index seek hoặc bitmap scan.
- Cách kết hợp bảng: nested loop, hash join hoặc merge join.
- Cách lọc và sắp xếp: filter, sort, aggregate, limit.
- Ước lượng số hàng, chi phí, bộ nhớ và I/O.
- Với chế độ phân tích thực thi, số hàng và thời gian thực tế của từng node.

Ví dụ, truy vấn:

```sql
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

có thể được thực hiện theo hai cách:

1. Quét toàn bộ bảng, lọc các đơn hàng của khách hàng 42 đang mở, sắp xếp theo thời gian rồi lấy 20 hàng đầu.
2. Dùng index bắt đầu bằng customer_id và status, đọc theo thứ tự created_at giảm dần rồi dừng khi đã lấy đủ 20 hàng.

Với bảng nhỏ, cách 1 đôi khi rẻ hơn. Với bảng lớn và điều kiện chọn được ít hàng, cách 2 thường có lợi hơn. Optimizer chọn plan dựa trên thống kê, chi phí ước lượng và cấu hình database.

## 2. Dùng EXPLAIN để xem kế hoạch thực thi

Mỗi database có cú pháp và cách trình bày plan riêng. Hai hệ quản trị thường gặp là PostgreSQL và MySQL.

### 2.1. PostgreSQL: EXPLAIN

EXPLAIN hiển thị kế hoạch mà PostgreSQL dự định dùng:

```sql
EXPLAIN
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

Plan cơ bản thường có các thông tin:

- cost=startup..total: chi phí ước lượng nội bộ của planner, không phải milliseconds.
- rows: số hàng planner ước tính node sẽ trả về.
- width: kích thước trung bình ước lượng của mỗi hàng, tính bằng byte.
- Tên node: ví dụ Seq Scan, Index Scan, Index Only Scan, Sort và Limit.

Chi phí của PostgreSQL là đơn vị tương đối để so sánh các phương án trong cùng môi trường/cấu hình. Không so sánh trực tiếp con số cost giữa hai database hoặc coi cost là thời gian chạy thực tế.

### 2.2. PostgreSQL: EXPLAIN ANALYZE

EXPLAIN ANALYZE thực thi câu SQL rồi bổ sung số liệu thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

Các thông tin đáng chú ý:

| Thành phần | Ý nghĩa |
| --- | --- |
| actual time | Thời gian thực tế của node, thường hiển thị khoảng bắt đầu và kết thúc trung bình mỗi loop |
| actual rows | Số hàng thực tế node trả về mỗi loop |
| loops | Số lần node được thực thi |
| Buffers: shared hit | Số block được tìm thấy trong shared buffers |
| Buffers: shared read | Số block phải đọc vào shared buffers |
| Rows Removed by Filter | Số hàng bị loại bởi filter tại node |
| Planning Time | Thời gian lập kế hoạch |
| Execution Time | Thời gian thực thi được đo bởi PostgreSQL |

EXPLAIN ANALYZE thực sự chạy câu lệnh. Với SELECT, nó đọc dữ liệu như truy vấn bình thường; với UPDATE/DELETE/INSERT, nó có thể thay đổi dữ liệu. Chỉ chạy phân tích trên câu lệnh ghi trong môi trường an toàn, với transaction rollback có chủ đích hoặc dữ liệu thử nghiệm. Rollback không hoàn tác mọi side effect bên ngoài database như sequence hoặc lời gọi từ trigger.

### 2.3. MySQL: EXPLAIN và EXPLAIN ANALYZE

MySQL có EXPLAIN để xem cách optimizer dự định đọc bảng:

```sql
EXPLAIN
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

Một số cột quan trọng trong dạng tabular:

| Cột | Ý nghĩa |
| --- | --- |
| type | Kiểu truy cập bảng, ví dụ ALL, range, ref, eq_ref, const, system |
| possible_keys | Các index optimizer có thể xem xét |
| key | Index được chọn |
| key_len | Độ dài phần index được sử dụng |
| rows | Số hàng ước lượng cần đọc |
| filtered | Tỷ lệ phần trăm hàng còn lại sau filter theo ước lượng |
| Extra | Thông tin bổ sung như Using filesort hoặc Using temporary |

MySQL 8.0.18 trở lên hỗ trợ EXPLAIN ANALYZE để thực thi truy vấn và hiển thị thông tin thực tế theo iterator plan:

```sql
EXPLAIN ANALYZE
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

EXPLAIN ANALYZE cũng chạy câu SQL. Hãy áp dụng cùng nguyên tắc an toàn như PostgreSQL khi phân tích câu lệnh có side effect.

## 3. Cách đọc plan theo thứ tự

Plan thường được hiển thị dạng cây. Các node con cung cấp dữ liệu cho node cha. Khi đọc, bắt đầu từ node gốc để hiểu kết quả cuối cùng, rồi lần theo các node con để tìm nơi phát sinh nhiều công việc nhất.

Một số node phổ biến:

| Node | Ý nghĩa | Điều cần quan sát |
| --- | --- | --- |
| Sequential/Table Scan | Đọc tuần tự các hàng của bảng | Bảng lớn hay nhỏ, filter loại bỏ bao nhiêu hàng |
| Index Scan/Seek | Dùng index để tìm vị trí hàng | Số hàng index đọc và số lần phải truy cập bảng |
| Index Only Scan | Có thể lấy dữ liệu từ index mà không cần đọc heap/table cho từng hàng | PostgreSQL còn phụ thuộc visibility map; không phải cứ có index là luôn index-only |
| Bitmap Index Scan + Bitmap Heap Scan | Tìm vị trí bằng index rồi đọc các page tương ứng theo bitmap | Hữu ích khi nhiều hàng cần đọc nhưng không phải toàn bảng |
| Filter | Lọc hàng sau khi node con trả dữ liệu | Số hàng bị loại và filter có thể đưa vào index không |
| Sort | Sắp xếp kết quả | Số hàng cần sort, bộ nhớ và khả năng dùng index theo thứ tự |
| Nested Loop | Với mỗi hàng phía ngoài, tìm hàng tương ứng phía trong | Số vòng lặp và index ở phía trong |
| Hash Join | Tạo hash table từ một phía rồi dò phía còn lại | Kích thước dữ liệu, memory và spill ra disk |
| Merge Join | Ghép hai đầu vào đã được sắp xếp theo khóa join | Chi phí sort hoặc lợi ích từ index đã có thứ tự |
| Aggregate/GroupAggregate | Gom nhóm hoặc tính aggregate | Số hàng đầu vào và phương pháp aggregate |
| Limit | Dừng khi đủ số hàng cần trả | Index phù hợp có thể giúp dừng sớm |

Không đánh giá một node chỉ qua tên. Seq Scan không tự động là xấu; quét tuần tự bảng nhỏ có thể nhanh hơn đọc index rồi truy cập nhiều hàng rời rạc. Index Scan cũng không tự động tốt nếu phải đọc quá nhiều hàng và nhiều page ngẫu nhiên.

### 3.1. Tìm node tốn thời gian

Với PostgreSQL EXPLAIN ANALYZE:

- So sánh actual time giữa các node.
- Xem loops; một node nhanh nhưng chạy hàng trăm nghìn lần vẫn có thể rất tốn.
- Nhân số hàng với số loops để hiểu tổng lượng công việc gần đúng.
- Quan sát Buffers để biết truy vấn chạm nhiều page hay đọc từ cache.
- Xem node sort/hash có spill ra disk hay không.

Với MySQL, xem thời gian thực tế và số vòng lặp trong iterator plan của EXPLAIN ANALYZE. Plan dạng tabular EXPLAIN chủ yếu là ước lượng; không coi cột rows là số hàng thực tế đã đọc.

### 3.2. Kiểm tra sai lệch giữa estimate và actual

Một dấu hiệu quan trọng là số hàng ước lượng khác xa số hàng thực tế.

```text
Planner estimate: 100 rows
Actual result:    120,000 rows
```

Optimizer có thể chọn nested loop hoặc index path dựa trên giả định chỉ có 100 hàng, nhưng thực tế phải xử lý 120.000 hàng. Nguyên nhân có thể là:

- Statistics cũ hoặc chưa đủ mẫu.
- Dữ liệu lệch phân bố (skew), ví dụ một status phổ biến hơn nhiều status khác.
- Các cột có tương quan nhưng thống kê mặc định giả định gần độc lập.
- Điều kiện dùng expression/cast mà planner không ước lượng tốt.
- Tham số truy vấn có phân bố khác nhau giữa các lần chạy.

PostgreSQL có thể cần cập nhật statistics bằng ANALYZE và cân nhắc extended statistics cho các cột tương quan. MySQL có cơ chế cập nhật statistics tương ứng. Không tạo index mới trước khi kiểm tra liệu planner đang có số liệu thống kê đủ tốt hay không.

## 4. Bắt đầu từ điều kiện truy vấn, không bắt đầu từ tên entity

Index phục vụ một workload cụ thể. Hãy thu thập các query thường chạy, query chậm và query có độ ưu tiên nghiệp vụ cao. Với mỗi query, ghi lại:

1. Các cột trong WHERE và kiểu điều kiện: equality, range, IN, IS NULL, pattern.
2. Các cột dùng trong JOIN.
3. Các cột và thứ tự trong ORDER BY.
4. Có LIMIT/pagination không?
5. Các cột cần trả về trong SELECT.
6. Tần suất chạy và số hàng thường trả về.
7. Tỷ lệ đọc/ghi của bảng.

Ví dụ truy vấn danh sách đơn hàng đang mở của một khách hàng:

```sql
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
```

Điều kiện:

| Cột | Vai trò | Loại điều kiện |
| --- | --- | --- |
| customer_id | Phân vùng theo khách hàng | Equality |
| status | Lọc trạng thái | Equality |
| created_at | Giới hạn thời gian và sắp xếp | Range + Order |
| id, order_number | Kết quả cần trả | Projection |

Từ đây mới đề xuất index, rồi xác nhận bằng execution plan.

## 5. B-tree index cho equality, range và sort

B-tree là loại index mặc định và thường dùng cho equality, range, một số điều kiện thứ tự/prefix, ORDER BY khi thứ tự index phù hợp và join theo khóa.

Ví dụ:

```sql
CREATE INDEX idx_purchase_order_customer
    ON purchase_order (customer_id);

CREATE INDEX idx_purchase_order_created
    ON purchase_order (created_at);
```

Index một cột phù hợp nếu workload thường lọc theo cột đó độc lập. Nhưng nếu query thường kết hợp nhiều điều kiện, index ghép có thể hiệu quả hơn.

## 6. Composite index và quy tắc leftmost prefix

Composite index (index nhiều cột) lưu các khóa theo thứ tự cột được khai báo. Với B-tree:

```sql
CREATE INDEX idx_order_customer_status_created
    ON purchase_order (customer_id, status, created_at);
```

Index trên phù hợp nhất với query có điều kiện trên các cột dẫn đầu:

- customer_id.
- customer_id và status.
- customer_id, status và điều kiện range trên created_at.

Query chỉ lọc status mà không có customer_id thường không thể tận dụng phần đầu index hiệu quả như query có customer_id. Đây là ý nghĩa của leftmost prefix.

### 6.1. Thứ tự cột quan trọng

Giả sử hai query:

```sql
-- Query A: luôn lọc theo customer và status.
SELECT id, status
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN';

-- Query B: tìm các đơn hàng theo status trên toàn hệ thống.
SELECT id, customer_id
FROM purchase_order
WHERE status = 'OPEN';
```

Index (customer_id, status) hỗ trợ Query A. Nó không phải lựa chọn tốt cho Query B vì Query B không ràng buộc cột đầu tiên. Query B có thể cần index riêng bắt đầu bằng status nếu đủ chọn lọc và đủ thường xuyên.

### 6.2. Equality trước range là quy tắc khởi đầu hữu ích

Với query có nhiều điều kiện equality và một điều kiện range, một điểm bắt đầu thường tốt là đặt các cột equality trước, cột range sau:

```sql
WHERE customer_id = ?
  AND status = ?
  AND created_at >= ?
```

Index gợi ý:

```sql
CREATE INDEX idx_order_customer_status_created
    ON purchase_order (customer_id, status, created_at);
```

Các cột equality giới hạn một vùng liên tiếp trong index; range trên cột tiếp theo giới hạn phần cần đọc. Đây là quy tắc thiết kế khởi đầu, không thay thế việc xem plan và workload.

### 6.3. Không áp dụng máy móc “cột có cardinality cao nhất luôn đứng đầu”

Lời khuyên “đặt cột có nhiều giá trị khác nhau nhất trước” không phải quy tắc tổng quát cho mọi composite index. Với nhiều cột equality được ràng buộc cùng lúc, thứ tự giữa chúng có thể không ảnh hưởng nhiều tới một query cụ thể; khả năng phục vụ các query khác, leftmost prefix, sort order và phân bố dữ liệu mới là yếu tố quyết định.

Hãy chọn thứ tự dựa trên những prefix mà workload thực sự sử dụng, cột thường xuất hiện độc lập, equality/range và thứ tự sort, selectivity thực tế, kích thước index và chi phí ghi.

### 6.4. Direction của index và ORDER BY

Với truy vấn:

```sql
SELECT id, created_at
FROM purchase_order
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Index:

```sql
CREATE INDEX idx_order_customer_created_desc
    ON purchase_order (customer_id, created_at DESC);
```

có thể giúp database tìm các hàng của khách hàng rồi đọc theo thứ tự thời gian giảm dần, dừng sớm khi đủ 20 hàng. B-tree có thể được quét ngược, nhưng thứ tự direction trở nên quan trọng khi index có nhiều cột sort với hướng trộn khác nhau. Hãy kiểm tra plan thực tế.

## 7. Covering index và index-only scan

Một query có thể cần nhiều cột hơn những cột dùng để lọc. Nếu index chứa cả cột lọc và cột trả về, database có thể tránh một số lần truy cập bảng.

PostgreSQL hỗ trợ INCLUDE để thêm cột payload vào index mà không dùng chúng làm khóa tìm kiếm:

```sql
CREATE INDEX idx_order_customer_status_created_cover
    ON purchase_order (customer_id, status, created_at DESC)
    INCLUDE (id, order_number);
```

Index này chứa key columns customer_id, status, created_at và included columns id, order_number. Với query chỉ chọn các cột có trong index, PostgreSQL có thể cân nhắc Index Only Scan. Tuy nhiên, index-only scan còn phụ thuộc visibility map và trạng thái vacuum; plan vẫn có thể phải truy cập heap để xác nhận visibility.

Trong MySQL/InnoDB, một secondary index có thể là covering index nếu chứa các cột cần thiết; InnoDB secondary index cũng mang primary key ở leaf record. Cú pháp INCLUDE kiểu PostgreSQL không dùng được cho MySQL.

Covering index có thể làm index lớn hơn đáng kể. Chỉ thêm các cột trả về khi lợi ích giảm table lookup được đo thấy rõ; đừng biến mọi index thành bản sao gần đầy đủ của bảng.

## 8. Partial index và filtered workload

PostgreSQL hỗ trợ partial index: chỉ index các hàng thỏa điều kiện:

```sql
CREATE INDEX idx_open_orders_customer_created
    ON purchase_order (customer_id, created_at DESC)
    WHERE status = 'OPEN';
```

Index này nhỏ hơn index toàn bảng nếu chỉ một phần hàng có status OPEN. Nó phù hợp khi query thường xuyên có predicate tương ứng:

```sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = 'OPEN'
  AND customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Planner chỉ dùng partial index khi có thể chứng minh điều kiện query bao hàm predicate của index. Với prepared statement có parameter thay cho literal, khả năng chứng minh có thể phụ thuộc loại plan và giá trị tham số; hãy kiểm tra query đúng như ứng dụng thực sự chạy.

MySQL không có partial index B-tree tổng quát theo cú pháp PostgreSQL. Có thể dùng generated column/expression index hoặc thiết kế khác tùy trường hợp, nhưng cần xác nhận khả năng của phiên bản MySQL.

## 9. Expression index và điều kiện có hàm

Nếu query áp dụng hàm lên cột:

```sql
SELECT id, email
FROM customer
WHERE LOWER(email) = LOWER('ALICE@example.com');
```

Index B-tree thông thường trên email có thể không phục vụ trực tiếp biểu thức LOWER(email). PostgreSQL hỗ trợ expression index:

```sql
CREATE INDEX idx_customer_lower_email
    ON customer (LOWER(email));
```

Query phải dùng biểu thức tương thích với index. Khi có thể, chuẩn hóa dữ liệu ở write path hoặc dùng kiểu/collation phù hợp cũng có thể là lựa chọn tốt.

Tương tự, cast hoặc phép toán trên cột có thể làm index thường không được dùng theo cách mong muốn. Hãy xem plan và kiểu dữ liệu của bind parameter; tránh cast cột một cách không cần thiết nếu có thể cast giá trị đầu vào.

## 10. Index cho LIKE, tìm kiếm văn bản và JSON

Không phải mọi điều kiện chuỗi đều được B-tree xử lý giống nhau.

### 10.1. Prefix search và leading wildcard

Query LIKE 'alice%' có thể tận dụng B-tree trong một số database/collation/operator class phù hợp.

Query LIKE '%alice%' thường không thể dùng B-tree thông thường để tìm substring vì giá trị cần tìm không bắt đầu từ đầu chuỗi. Với PostgreSQL, extension pg_trgm và GIN/GiST index có thể phù hợp cho tìm kiếm substring:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_customer_email_trgm
    ON customer
    USING GIN (email gin_trgm_ops);
```

Đánh giá kích thước index và hiệu năng insert/update trước khi dùng.

### 10.2. Full-text search

Nếu yêu cầu là tìm từ/ngữ theo ngôn ngữ, stemming hoặc ranking, full-text search phù hợp hơn việc dùng LIKE '%word%' trên bảng lớn. PostgreSQL có tsvector/tsquery và GIN index; database khác có cơ chế full-text riêng.

### 10.3. JSONB

PostgreSQL có GIN index cho JSONB:

```sql
CREATE INDEX idx_event_payload_gin
    ON event_record
    USING GIN (payload);
```

GIN có thể hỗ trợ các toán tử JSONB phù hợp, ví dụ containment @>:

```sql
SELECT id
FROM event_record
WHERE payload @> '{"eventType":"ORDER_CONFIRMED"}';
```

Nếu query thường lọc một giá trị scalar cụ thể bằng expression:

```sql
SELECT id
FROM event_record
WHERE payload ->> 'eventType' = 'ORDER_CONFIRMED';
```

có thể cân nhắc expression index:

```sql
CREATE INDEX idx_event_type
    ON event_record ((payload ->> 'eventType'));
```

Chọn GIN hay expression B-tree dựa trên toán tử query thực tế. Một index JSONB tổng quát không tự động tối ưu mọi biểu thức truy vấn JSON.

## 11. Index cho JOIN và khóa ngoại

Truy vấn join thường cần tìm các hàng ở bảng liên quan theo khóa:

```sql
SELECT o.id, o.order_number, c.name
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
WHERE c.region = 'NORTH';
```

Primary key trên customer.id thường đã có index. Bảng đơn hàng có thể cần index trên purchase_order.customer_id nếu query join/filter theo cột đó đủ thường xuyên:

```sql
CREATE INDEX idx_order_customer
    ON purchase_order (customer_id);
```

Không giả định database nào cũng tự tạo index cho cột foreign key phía tham chiếu. Ví dụ PostgreSQL tự tạo index cho primary key/unique constraint được khai báo, nhưng không tự động tạo index trên cột referencing foreign key. InnoDB yêu cầu index phù hợp cho foreign key và có thể tự tạo nếu chưa có.

Index trên foreign key giúp join và cũng có thể giúp database tìm hàng con khi cập nhật/xóa hàng cha cần kiểm tra constraint. Tuy nhiên, chỉ tạo index theo workload và hành vi database cụ thể.

## 12. Chọn loại index theo workload

Không phải mọi database có cùng loại index hoặc semantics. Một số ví dụ phổ biến:

| Loại index | Workload thường phù hợp | Ghi chú |
| --- | --- | --- |
| B-tree | Equality, range, sort, join | Lựa chọn mặc định cho nhiều truy vấn quan hệ |
| Hash | Equality | PostgreSQL có hash index; phạm vi sử dụng hẹp hơn B-tree |
| GIN | JSONB, array, full-text và dữ liệu có nhiều thành phần | Tốt cho membership/containment; chi phí ghi và kích thước có thể cao |
| GiST | Spatial, range và các kiểu tìm kiếm có operator class phù hợp | Cần chọn operator class đúng |
| BRIN | Bảng rất lớn có dữ liệu tương quan với thứ tự vật lý, ví dụ log theo thời gian | Index nhỏ nhưng có thể trả về nhiều block cần recheck |
| Full-text index | Tìm kiếm từ/ngữ | Cú pháp và khả năng phụ thuộc database |

MySQL/InnoDB thường sử dụng B-tree cho index thông thường; các loại như FULLTEXT hoặc SPATIAL có cơ chế riêng. Đừng áp dụng cú pháp PostgreSQL GIN/GiST/BRIN cho MySQL hoặc ngược lại.

## 13. Selectivity và cardinality

**Selectivity** mô tả tỷ lệ hàng còn lại sau điều kiện lọc. Một predicate chọn 1% bảng thường chọn lọc cao hơn predicate giữ lại 90% bảng.

Ví dụ bảng có một triệu đơn hàng:

| Predicate | Số hàng khớp | Tỷ lệ |
| --- | ---: | ---: |
| id = 123 | 1 | 0,0001% |
| customer_id = 42 | 500 | 0,05% |
| status = 'OPEN' | 700.000 | 70% |

Index trên id thường rất hữu ích cho lookup một hàng. Index chỉ trên status có thể ít hữu ích nếu hầu hết bảng có cùng trạng thái OPEN, vì database có thể phải đọc quá nhiều hàng rải rác. Tuy vậy, index status vẫn có thể hữu ích trong một partial index chỉ chứa một trạng thái hiếm hoặc trong composite index theo customer/status.

Cardinality là số giá trị khác nhau của một cột. Cardinality cao thường tạo khả năng phân biệt tốt, nhưng không đủ để quyết định index. Cần xét phân bố giá trị, tần suất query, số hàng trả về và thứ tự cột trong composite index.

## 14. Vì sao optimizer không dùng index dù đã tạo?

Có index không đồng nghĩa database luôn chọn index. Các nguyên nhân thường gặp:

- Bảng nhỏ, sequential scan rẻ hơn.
- Điều kiện lọc trả về phần lớn bảng.
- Statistics chưa cập nhật hoặc phân bố dữ liệu bị lệch.
- Index không bắt đầu bằng các cột query ràng buộc.
- Query dùng hàm/cast khác với expression index.
- Kiểu dữ liệu bind parameter không phù hợp.
- Leading wildcard hoặc toán tử không được loại index hỗ trợ.
- Cột sort không khớp thứ tự index.
- Index có nhiều random heap fetch, chi phí cao hơn scan.
- Query trả về quá nhiều cột/hàng nên covering path không có lợi.

Không ép optimizer dùng index ngay khi thấy nó chọn sequential scan. Hãy xem ước lượng, actual rows, buffers và workload. Hints hoặc tắt scan method chỉ nên dùng trong điều tra có kiểm soát, không thay thế việc sửa query, statistics hoặc thiết kế index.

## 15. Spring Data JDBC: từ repository method tới execution plan

Spring Data JDBC có thể tạo SQL từ derived query method hoặc thực thi SQL khai báo bằng @Query. Database chỉ nhìn thấy SQL và parameter đã bind; tên method Java không quyết định index.

Ví dụ derived query:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder>
    findByCustomerIdAndStatusOrderByCreatedAtDesc(
            Long customerId,
            String status
    );
}
```

Ví dụ SQL tùy biến:

```java
@Query("""
    SELECT id, customer_id, order_number, status, created_at
    FROM purchase_order
    WHERE customer_id = :customerId
      AND status = :status
    ORDER BY created_at DESC
    """)
List<PurchaseOrder> findRecentOrders(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
```

Tên method và SQL minh họa cần khớp với property/table thực tế của ứng dụng. Spring Data JDBC không tự tạo index dựa trên tên query method. Index phải được tạo trong database schema bằng migration và xác nhận bằng plan.

### 15.1. Xem SQL thực tế

Khi plan không như mong đợi, cần xem SQL thực tế mà Spring Data JDBC gửi:

- Bật logging phù hợp cho package Spring JDBC/repository trong môi trường phát triển.
- Dùng datasource proxy hoặc công cụ quan sát SQL nếu cần cả bind parameter.
- Kiểm tra SQL được tạo từ derived method, đặc biệt khi có sort, pagination hoặc projection.
- Chạy EXPLAIN với cùng predicate và kiểu giá trị đại diện.

Không ghi log giá trị nhạy cảm như access token, email riêng tư hoặc dữ liệu cá nhân ở production nếu chưa có chính sách bảo vệ phù hợp.

### 15.2. Pageable và ORDER BY

Nếu query có pagination, index cần phù hợp cả điều kiện lọc lẫn thứ tự sắp xếp. Ví dụ:

```sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50 OFFSET 50000;
```

Index (customer_id, created_at DESC) có thể giúp lọc và sắp xếp, nhưng database vẫn phải đi qua/loại bỏ các hàng trước offset lớn. Với trang rất sâu, cân nhắc keyset/seek pagination dựa trên giá trị sort cuối cùng của trang trước, nếu API và nghiệp vụ cho phép.

Đếm tổng số hàng để tạo Page cũng có thể là một query riêng và tốn chi phí. Nếu giao diện không cần tổng số trang, cân nhắc API trả Slice hoặc giới hạn kết quả theo cách phù hợp với phiên bản/framework đang dùng.

## 16. Ví dụ thiết kế index từ một truy vấn

Giả sử bảng:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Truy vấn workload:

```sql
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
```

### 16.1. Bước đầu: index theo điều kiện và thứ tự

PostgreSQL:

```sql
CREATE INDEX idx_po_customer_status_created
    ON purchase_order (
        customer_id,
        status,
        created_at DESC
    );
```

Index bắt đầu bằng hai cột equality, sau đó là cột range/sort. Nó có thể tìm vùng index cho khách hàng và trạng thái, rồi đọc theo thứ tự thời gian.

### 16.2. Đọc plan trước và sau

Trước khi tạo index:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
```

Tạo index trong môi trường thử nghiệm, cập nhật statistics khi cần, rồi chạy lại cùng query. So sánh execution time, planning time, estimated/actual rows, buffers hit/read, sort node, số hàng index/table phải đọc để trả 20 hàng và chi phí insert/update tăng thêm do index mới.

Không chỉ nhìn thấy Index Scan rồi kết luận thành công. Nếu index scan phải đọc hàng trăm nghìn tuple và loại gần hết, query vẫn có thể chậm.

### 16.3. Cân nhắc covering index

Nếu query chạy rất thường xuyên và table lookup là phần tốn kém, PostgreSQL có thể thử:

```sql
CREATE INDEX idx_po_customer_status_created_cover
    ON purchase_order (
        customer_id,
        status,
        created_at DESC
    )
    INCLUDE (id, order_number);
```

Chỉ giữ một trong hai index nếu index cover thay thế được index trước và workload xác nhận lợi ích. Không giữ hai index gần như trùng nhau nếu không có query khác cần chúng.

## 17. Index có chi phí: đừng tạo quá nhiều

Mỗi index bổ sung tạo ra chi phí:

- Insert phải thêm entry vào mỗi index liên quan.
- Update cột nằm trong index có thể phải sửa index entry.
- Delete phải đánh dấu/xóa entry theo cơ chế database.
- Tốn disk, buffer cache và thời gian backup/restore.
- Tăng công việc vacuum/maintenance ở database có MVCC.
- Nhiều index tương tự làm schema khó quản lý và làm tăng chi phí ghi.

Index dư thừa có thể làm write throughput giảm đáng kể. Trước khi thêm index, kiểm tra đã có index nào có prefix và thứ tự phù hợp chưa. Sau khi thêm, theo dõi mức sử dụng index và workload ghi.

Không xóa index chỉ vì một khoảng thời gian ngắn không thấy được dùng. Index có thể phục vụ query hiếm nhưng quan trọng, constraint hoặc workload theo mùa. Xác nhận với owner và quan sát đủ chu kỳ tải trước khi loại bỏ.

## 18. Tạo index trong migration

Index là một phần của database schema. Quản lý bằng Flyway, Liquibase hoặc công cụ migration của dự án thay vì tạo thủ công trên production rồi quên ghi lại.

Ví dụ migration SQL:

```sql
CREATE INDEX idx_po_customer_status_created
    ON purchase_order (
        customer_id,
        status,
        created_at DESC
    );
```

Với PostgreSQL bảng lớn, CREATE INDEX CONCURRENTLY có thể giảm mức block đối với thao tác ghi trong lúc build index, nhưng có giới hạn riêng và không được chạy bên trong transaction block. Kiểm tra cách migration tool quản lý transaction trước khi dùng.

Trước khi tạo index production, ước lượng kích thước bảng và thời gian build, kiểm tra disk space/tải I/O, xác định mức lock/block, lập kế hoạch deploy/rollback và chạy migration trên dữ liệu gần production để ước lượng.

## 19. Quy trình tối ưu truy vấn lặp lại được

Một quy trình có thể áp dụng cho từng query chậm:

1. **Xác định query:** lấy SQL thực tế, parameter shape, tần suất và latency từ log/metrics.
2. **Tạo baseline:** chạy EXPLAIN và, trong môi trường an toàn, EXPLAIN ANALYZE.
3. **Đọc plan:** tìm scan, join, sort, estimate/actual mismatch, loops và buffer I/O.
4. **Kiểm tra statistics:** xác nhận statistics được cập nhật và phản ánh phân bố dữ liệu.
5. **Đề xuất index/query change:** dựa trên predicate, join, sort, projection và selectivity.
6. **Đo lại:** chạy cùng query với cùng dataset/parameter đại diện sau thay đổi.
7. **Kiểm tra write cost:** đo insert/update/delete và kích thước index.
8. **Thử trên staging:** dùng database engine, version và dữ liệu gần production.
9. **Triển khai migration:** theo quy trình release của dự án.
10. **Theo dõi production:** query latency, database load, pool wait và mức sử dụng index.

Khi so sánh, chạy đủ số lần để giảm ảnh hưởng cache/warm-up và tải nền. Ghi rõ việc đo dùng cache nóng hay lạnh; không so sánh hai lần chạy trong điều kiện khác nhau rồi kết luận index tốt hơn.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có index nhưng planner vẫn Seq Scan | Bảng nhỏ, predicate ít chọn lọc hoặc statistics/chi phí cho thấy scan rẻ hơn | Xem actual rows, buffers và kích thước bảng |
| Composite index không được dùng | Query bỏ qua cột dẫn đầu hoặc thứ tự cột không phù hợp | Thiết kế theo leftmost prefix và workload |
| Query có filter nhanh nhưng ORDER BY vẫn sort lớn | Index không hỗ trợ thứ tự sort hoặc điều kiện trước sort không khớp | Xem composite index có thể bao gồm sort key không |
| Index scan vẫn chậm | Đọc quá nhiều index entry/table row hoặc random I/O | Kiểm tra selectivity, heap fetches và buffers |
| Estimate rows sai xa actual | Statistics cũ, skew hoặc tương quan cột | Cập nhật statistics, cân nhắc extended statistics |
| LIKE không dùng B-tree | Pattern bắt đầu bằng wildcard hoặc collation/operator không phù hợp | Prefix search, trigram hoặc full-text theo nhu cầu |
| Hàm LOWER làm mất khả năng dùng index thường | Query dùng expression khác key index | Expression index hoặc chuẩn hóa dữ liệu |
| JSONB query chậm dù đã có GIN | Toán tử/expression không khớp loại index | Thiết kế operator class hoặc expression index phù hợp |
| Insert/update chậm sau khi thêm index | Index write amplification và storage overhead | Đo workload ghi, loại index dư thừa |
| EXPLAIN ANALYZE làm thay đổi dữ liệu | Dùng nó trên câu lệnh ghi | Chỉ chạy trên môi trường an toàn, rollback có kiểm soát |
| Query từ Spring Data có plan khác SQL thử tay | Parameter, bind type, sort hoặc SQL thực tế khác | Lấy SQL và bind parameter thực tế từ ứng dụng |
| Offset pagination ngày càng chậm | Database phải đi qua nhiều hàng trước offset | Cân nhắc keyset pagination |

## 21. Bài tập thực hành

**Bài 1 — Đọc plan cơ bản.** Tạo bảng purchase_order với ít nhất vài trăm nghìn hàng. Chạy một query có điều kiện theo customer_id, dùng EXPLAIN và xác định node scan, số hàng ước lượng và sort.

**Bài 2 — So sánh estimate/actual.** Chạy EXPLAIN ANALYZE trên PostgreSQL. Ghi lại estimated rows, actual rows, loops và buffers. Giải thích node nào xử lý nhiều hàng nhất.

**Bài 3 — Composite index.** Tạo index (customer_id, status, created_at). So sánh query dùng cả ba cột với query chỉ dùng status; giải thích leftmost-prefix.

**Bài 4 — Equality và range.** Viết query có hai điều kiện equality và một điều kiện range. Thử hai thứ tự composite index trong database test và so sánh plan trên cùng dữ liệu.

**Bài 5 — ORDER BY/LIMIT.** Tạo index phù hợp với customer filter và created time descending. Kiểm tra plan có giảm sort và dừng sớm khi lấy một trang nhỏ không.

**Bài 6 — Covering index.** Trên PostgreSQL, thử INCLUDE các cột projection. Quan sát Index Only Scan, heap fetches và kích thước index.

**Bài 7 — Partial và expression index.** Tạo partial index cho đơn hàng OPEN và expression index cho LOWER(email). Xác nhận query tương ứng có thể sử dụng chúng.

**Bài 8 — JSONB và LIKE.** So sánh B-tree với GIN/trigram cho hai query khác nhau: JSONB containment và substring search. Ghi rõ loại toán tử mà mỗi index hỗ trợ.

**Bài 9 — Spring Data JDBC.** Tạo derived query và @Query cho cùng một use case. Lấy SQL thực tế, chạy EXPLAIN và so sánh plan.

**Bài 10 — Đo write overhead.** Đo thời gian insert/update trước và sau khi thêm nhiều index. So sánh read benefit với write cost và dung lượng.

**Bài 11 — Pagination sâu.** So sánh LIMIT/OFFSET ở offset nhỏ và lớn. Thử cách seek/keyset dựa trên cặp sort key ổn định và giải thích khác biệt.

**Bài 12 — Migration index.** Viết migration tạo index cho query đã chọn. Chạy trên database test, xác nhận plan sau migration và kiểm tra quy trình rollback.

### Tài liệu tham khảo

- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): cách đọc plan, estimated/actual rows, cost và buffer.
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html): tổng quan index, loại index và cách planner sử dụng.
- [PostgreSQL — Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html): quy tắc index nhiều cột.
- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, Hash, GiST, SP-GiST, GIN và BRIN.
- [PostgreSQL — Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): expression index.
- [PostgreSQL — Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): index theo predicate.
- [MySQL — EXPLAIN Output](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html): các trường trong plan MySQL.
- [MySQL — EXPLAIN ANALYZE](https://dev.mysql.com/doc/refman/8.4/en/explain.html): phân tích iterator plan với số liệu thực thi.
- [Spring Data Relational Reference](https://docs.spring.io/spring-data/relational/reference/): repository query và mapping trong Spring Data JDBC.
