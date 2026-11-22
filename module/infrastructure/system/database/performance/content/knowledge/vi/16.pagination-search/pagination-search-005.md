# Tổng số bản ghi, đếm chính xác và lựa chọn giảm chi phí đếm

Trong chương **Phân trang và tìm kiếm** của module **DATABASE_PERFORMANCE**, tổng số bản ghi thường được dùng để hiển thị số kết quả, số trang, tiến độ xử lý hoặc số lượng đối tượng thỏa điều kiện. Tuy nhiên, phép đếm chính xác trên bảng lớn có thể tốn I/O và CPU gần bằng một truy vấn quét dữ liệu, ngay cả khi giao diện chỉ hiển thị một trang nhỏ. Vì vậy, cần phân biệt lúc nào nghiệp vụ thực sự cần con số chính xác, lúc nào chỉ cần biết còn dữ liệu hay không, và lúc nào có thể dùng số liệu ước lượng hoặc bộ đếm được duy trì trước.

Tối ưu đếm không chỉ là thêm chỉ mục cho `COUNT(*)`. Cần xác định đúng ngữ nghĩa của số lượng, phạm vi dữ liệu, mức nhất quán giữa trang kết quả và tổng số, tần suất cập nhật, yêu cầu độ mới và chi phí duy trì bộ đếm. Một giải pháp phù hợp phải cân bằng độ chính xác, độ trễ, tải đọc, tải ghi và độ phức tạp vận hành.

## 1. Xác định chính xác cần đếm điều gì

Trước khi tối ưu, hãy mô tả một đơn vị được tính là gì. “Số bản ghi” có thể là số dòng trong bảng, số đơn hàng, số khách hàng duy nhất, số kết quả sau join hoặc số đối tượng đang hoạt động theo một bộ lọc. Các định nghĩa này không tương đương.

### 1.1. COUNT(*), COUNT(cột) và COUNT(DISTINCT)

| Biểu thức | Ngữ nghĩa |
|---|---|
| `COUNT(*)` | Đếm mọi dòng trong tập kết quả, kể cả dòng có cột `NULL` |
| `COUNT(column_name)` | Đếm dòng mà biểu thức/cột không phải `NULL` |
| `COUNT(DISTINCT column_name)` | Đếm số giá trị khác nhau và không phải `NULL` của biểu thức |
| `COUNT(DISTINCT col1, col2)` | Đếm tổ hợp giá trị khác nhau theo cú pháp được hệ quản trị hỗ trợ; cần kiểm tra cách xử lý `NULL` và cú pháp từng sản phẩm |

Ví dụ, bảng `orders` có một dòng cho mỗi đơn hàng:

```sql
SELECT COUNT(*) AS order_rows,
       COUNT(customer_id) AS orders_with_customer,
       COUNT(DISTINCT customer_id) AS unique_customers
FROM orders;
```

Ba kết quả có thể khác nhau. Nếu `customer_id` cho phép `NULL`, `COUNT(customer_id)` bỏ qua các dòng đó. `COUNT(DISTINCT customer_id)` đếm khách hàng duy nhất, không phải số đơn hàng.

### 1.2. Đếm sau JOIN có thể làm tăng số dòng

Nếu một đơn hàng có nhiều dòng sản phẩm, join `orders` với `order_items` tạo nhiều dòng cho một đơn hàng. Khi cần đếm đơn hàng, `COUNT(*)` trên kết quả join sẽ đếm số dòng chi tiết, không phải số đơn.

```sql
-- Đếm dòng chi tiết sau join
SELECT COUNT(*)
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id;

-- Đếm số đơn hàng có ít nhất một dòng chi tiết
SELECT COUNT(*)
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_items AS i
    WHERE i.order_id = o.order_id
);
```

Nếu chỉ cần xác định đơn hàng có dòng chi tiết, `EXISTS` thể hiện đúng ý nghĩa và tránh tạo tập join có nhiều dòng trùng đơn. Optimizer có thể biến đổi `EXISTS` thành semi-join phù hợp. Nếu nghiệp vụ thực sự cần đếm số tổ hợp đơn hàng và sản phẩm, khi đó mới đếm các dòng join.

### 1.3. Đếm kết quả có phân trang

Giả sử trang danh sách hiển thị đơn hàng đã hoàn tất của một tenant trong khoảng thời gian:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'COMPLETED'
  AND created_at >= :from_time
  AND created_at <  :to_time
ORDER BY created_at DESC, order_id DESC
OFFSET :offset ROWS
FETCH NEXT :page_size ROWS ONLY;
```

Nếu giao diện yêu cầu tổng số kết quả, truy vấn đếm phải áp dụng cùng điều kiện nghiệp vụ:

```sql
SELECT COUNT(*) AS total_count
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'COMPLETED'
  AND created_at >= :from_time
  AND created_at <  :to_time;
```

Điều kiện lọc không khớp giữa truy vấn trang và truy vấn đếm sẽ làm số trang sai. Cần thống nhất cách xử lý quyền truy cập, soft delete, tenant, trạng thái, khoảng ngày, múi giờ và các điều kiện tìm kiếm khác.

## 2. Vì sao đếm chính xác có thể tốn kém?

Một phép đếm chính xác phải xác định mọi dòng thuộc tập kết quả theo snapshot dữ liệu mà câu lệnh nhìn thấy. Nếu không có bộ đếm chính xác được duy trì riêng, hệ quản trị thường phải đọc các entry của chỉ mục hoặc các trang dữ liệu đủ để xác định số dòng thỏa điều kiện.

### 2.1. Chi phí đọc

Với `SELECT COUNT(*) FROM large_table`, số kết quả trả về chỉ là một dòng, nhưng số dòng cần kiểm tra có thể lên tới hàng triệu. Kích thước kết quả nhỏ không đồng nghĩa lượng công việc nhỏ.

Nếu truy vấn có điều kiện lọc, chi phí phụ thuộc vào số dòng và số trang liên quan. Một chỉ mục hẹp chứa các cột lọc có thể giảm lượng dữ liệu phải đọc. Nếu điều kiện khớp phần lớn bảng, scan một chỉ mục nhỏ hoặc bảng có thể vẫn phải đọc nhiều trang.

### 2.2. MVCC và khả năng nhìn thấy dòng

Ở các hệ quản trị dùng MVCC như PostgreSQL và InnoDB, một transaction đọc dữ liệu theo snapshot và phải xác định phiên bản dòng nào nhìn thấy được. Vì nhiều transaction có thể chèn, cập nhật hoặc xóa đồng thời, không thể luôn lấy một bộ đếm toàn cục duy nhất rồi dùng nó làm số dòng chính xác cho mọi snapshot.

Điều này giải thích vì sao một số hệ quản trị không duy trì sẵn một con số chính xác cho `COUNT(*)` toàn bảng ở mọi thời điểm. Đếm có thể phải đọc chỉ mục hoặc dữ liệu để áp dụng visibility rules. Chỉ mục-only scan cũng có thể cần kiểm tra thêm trang dữ liệu nếu metadata về khả năng nhìn thấy chưa đủ.

### 2.3. COUNT(DISTINCT) và tổng hợp phức tạp

`COUNT(DISTINCT)` thường cần loại bỏ trùng. Tùy plan và hệ quản trị, engine có thể dùng hash aggregate, sort hoặc cấu trúc trung gian. Nếu tập dữ liệu lớn, thao tác có thể tiêu thụ nhiều bộ nhớ và spill ra vùng tạm.

Đếm sau join, lọc nhiều chiều hoặc biểu thức trên cột có thể làm tập đầu vào lớn hơn và khó tận dụng chỉ mục. Hãy xem execution plan để xác định chi phí nằm ở scan, join, sort, hash aggregate hay I/O.

## 3. Đọc execution plan của truy vấn đếm

Không nên chỉ nhìn elapsed time. Hãy xem các chỉ số sau:

- **Estimated rows và actual rows:** optimizer dự đoán bao nhiêu dòng và thực tế bao nhiêu dòng đi qua từng operator.
- **Access path:** table scan, sequential scan, index scan, index-only scan, range scan hoặc seek.
- **Logical reads/buffers:** số trang đọc từ cache/buffer và số trang phải lấy từ tầng lưu trữ.
- **CPU và elapsed:** phân biệt chi phí xử lý với thời gian chờ I/O hoặc tài nguyên khác.
- **Aggregate:** xem có `HashAggregate`, `Sort`, `Stream Aggregate` hoặc operator loại bỏ trùng hay không.
- **Memory và spill:** xác định sort/hash có vượt bộ nhớ và dùng temp space hay không.
- **Parallelism:** scan song song có giảm thời gian nhưng tăng tổng CPU hoặc ảnh hưởng workload khác không.

Một index scan không mặc nhiên nhanh hơn table scan. Nếu phải đếm phần lớn bảng, đọc một chỉ mục hẹp có thể tiết kiệm I/O vì index entry nhỏ hơn row đầy đủ. Nhưng nếu chỉ mục không bao phủ điều kiện hoặc visibility check khiến phải truy cập bảng nhiều lần, lợi ích có thể giảm. Optimizer cần được đánh giá bằng số liệu thực tế.

### 3.1. Ví dụ PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM orders
WHERE tenant_id = 42
  AND status = 'COMPLETED';
```

Đọc loại scan, actual rows, thời gian, `shared hit`, `shared read` và operator aggregate. Nếu có `Index Only Scan`, xem `Heap Fetches`: giá trị cao cho thấy PostgreSQL vẫn phải kiểm tra heap cho nhiều entry do visibility map chưa đánh dấu các trang tương ứng là all-visible.

`EXPLAIN ANALYZE` thực thi câu lệnh. Với truy vấn đếm đọc dữ liệu, cần chạy trong môi trường hoặc khoảng tải được kiểm soát để tránh tạo thêm tải đáng kể trên production.

### 3.2. Ví dụ MySQL

```sql
EXPLAIN ANALYZE
SELECT COUNT(*)
FROM orders
WHERE tenant_id = 42
  AND status = 'COMPLETED';
```

Trong MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` hiển thị iterator và số dòng thực tế. Kiểm tra access type, key được chọn, số dòng đọc và thời gian của iterator. Với phiên bản không hỗ trợ `EXPLAIN ANALYZE`, dùng `EXPLAIN`, Performance Schema và đo runtime riêng.

### 3.3. Ví dụ SQL Server

```sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT COUNT_BIG(*)
FROM dbo.Orders
WHERE tenant_id = @tenant_id
  AND status = 'COMPLETED';

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
```

Đọc Actual Execution Plan, logical reads, CPU time, elapsed time, estimated/actual rows và aggregate operator. Dùng `COUNT_BIG` nếu số lượng có thể vượt giới hạn kiểu `int` của `COUNT`.

## 4. Giảm chi phí bằng chỉ mục phù hợp

Nếu truy vấn đếm có điều kiện lọc ổn định và chọn lọc tốt, chỉ mục trên các cột lọc có thể giảm số entry phải kiểm tra. Thứ tự cột cần dựa trên điều kiện equality, range, phân bố dữ liệu và các truy vấn liên quan.

Ví dụ truy vấn thường lọc theo tenant, trạng thái và khoảng thời gian:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
```

Chỉ mục này có thể hỗ trợ điều kiện equality trên `tenant_id` và `status`, sau đó giới hạn range theo `created_at`. Nếu workload chủ yếu đếm một trạng thái cố định, một filtered/partial index có thể nhỏ hơn:

```sql
-- PostgreSQL: partial index cho trạng thái hoàn tất
CREATE INDEX ix_orders_completed_tenant_created
ON orders (tenant_id, created_at)
WHERE status = 'COMPLETED';
```

Với SQL Server, filtered index có thể áp dụng ý tưởng tương tự:

```sql
CREATE INDEX ix_orders_completed_tenant_created
ON dbo.Orders (tenant_id, created_at)
WHERE status = 'COMPLETED';
```

Optimizer chỉ có thể dùng partial/filtered index khi điều kiện truy vấn chứng minh được rằng các dòng cần tìm nằm trong tập index. Cần kiểm tra tham số hóa, predicate và plan thực tế.

### 4.1. Index-only hoặc covering access

Truy vấn đếm thường không cần trả về cột ngoài điều kiện lọc. Nếu chỉ mục chứa đủ các cột cần kiểm tra, hệ quản trị có thể đếm trực tiếp trên chỉ mục mà không phải đọc toàn bộ row. Ví dụ chỉ mục `(tenant_id, status, created_at)` có thể hỗ trợ truy vấn lọc theo cả ba cột mà không cần lấy thêm dữ liệu đơn hàng.

Từng engine có cách gọi và điều kiện khác nhau:

- PostgreSQL có thể dùng `Index Only Scan`, nhưng vẫn phụ thuộc visibility map và có thể phát sinh heap fetches.
- MySQL/InnoDB có thể dùng secondary index phù hợp để xử lý điều kiện và đếm mà không cần lấy các cột không có trong index; secondary index của InnoDB còn mang khóa chính ở leaf entry.
- SQL Server có thể dùng nonclustered index hẹp hoặc covering index; với truy vấn chỉ đếm, không cần `INCLUDE` các cột không tham gia predicate.
- Oracle có thể dùng index range/fast full scan tùy tính chọn lọc, cấu trúc index và chi phí ước lượng.

Không nên tạo một chỉ mục rất rộng chỉ để phục vụ một phép đếm. Chỉ mục tăng dung lượng, chi phí ghi và bảo trì. Hãy so sánh tổng workload và xác định index có phục vụ thêm truy vấn khác hay không.

### 4.2. Giữ predicate có thể sử dụng chỉ mục

Tránh áp dụng hàm trực tiếp lên cột lọc nếu làm mất khả năng range access. Ví dụ, thay vì:

```sql
WHERE DATE(created_at) = :day
```

có thể dùng khoảng nửa mở:

```sql
WHERE created_at >= :day_start
  AND created_at <  :next_day_start
```

Cách viết khoảng nửa mở tránh vấn đề phần thời gian cuối ngày và thường giúp chỉ mục trên `created_at` xác định range rõ ràng. Giá trị biên cần được tạo theo đúng múi giờ nghiệp vụ.

## 5. Khi nào không cần đếm chính xác?

Nhiều giao diện hiển thị tổng số chỉ vì thói quen, dù thao tác tiếp theo của người dùng không phụ thuộc vào con số đó. Hãy xem lại yêu cầu sản phẩm.

### 5.1. Chỉ cần biết còn trang tiếp theo

Nếu giao diện chỉ cần nút **Tiếp theo**, không cần chạy `COUNT(*)`. Có thể lấy `page_size + 1` dòng:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'COMPLETED'
  AND (created_at, order_id) < (:last_created_at, :last_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size_plus_one;
```

Nếu truy vấn trả về nhiều hơn `page_size` dòng, ứng dụng biết còn dữ liệu tiếp theo; bỏ dòng dư trước khi trả kết quả. Cú pháp so sánh tuple ở trên phù hợp với PostgreSQL và một số hệ quản trị khác; có thể cần viết lại thành điều kiện kết hợp nếu hệ quản trị không hỗ trợ.

### 5.2. Dùng keyset pagination

Với `OFFSET` lớn, database thường phải đi qua hoặc bỏ qua nhiều dòng trước khi trả trang cần thiết. Keyset pagination dùng giá trị cuối trang trước làm cursor, giúp truy vấn tiếp tục từ vị trí trong thứ tự chỉ mục.

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'COMPLETED'
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size_plus_one;
```

Chỉ mục phù hợp có thể là `(tenant_id, status, created_at DESC, order_id DESC)`, tùy engine và cách truy vấn. Khóa sắp xếp cần ổn định và có tie-breaker duy nhất như `order_id`, nếu không các dòng có cùng timestamp có thể bị bỏ qua hoặc lặp lại giữa các trang.

Keyset pagination giảm chi phí đi tới trang sâu nhưng không cung cấp tổng số kết quả. Nếu nghiệp vụ chỉ cần duyệt tiếp, đây thường là đánh đổi tốt. Nếu cần nhảy trực tiếp tới trang bất kỳ hoặc hiển thị tổng số trang chính xác, phải cân nhắc thêm chi phí đếm và cách phân trang.

### 5.3. Hiển thị tổng số theo dạng xấp xỉ hoặc giới hạn

Thay vì hiển thị `1.284.391 kết quả`, giao diện có thể hiển thị:

- `Hơn 10.000 kết quả` nếu chỉ cần giúp người dùng hiểu quy mô.
- `10.000+` nếu hệ thống chỉ đếm đến ngưỡng.
- `Khoảng 1,3 triệu kết quả` nếu số liệu ước lượng được chấp nhận.
- Không hiển thị tổng số; chỉ cung cấp trạng thái còn/không còn dữ liệu.

Đếm đến ngưỡng có thể dừng sớm:

```sql
SELECT COUNT(*)
FROM (
    SELECT 1
    FROM orders
    WHERE tenant_id = :tenant_id
      AND status = 'COMPLETED'
    LIMIT 10001
) AS capped;
```

Nếu kết quả là 10.001, ứng dụng hiển thị `10.000+`; nếu nhỏ hơn, đó là tổng chính xác. Cách này có thể dừng sớm khi đủ số dòng và có access path phù hợp, nhưng không đảm bảo luôn nhanh nếu predicate khó tìm hoặc không có chỉ mục. Cú pháp giới hạn dòng cần điều chỉnh theo hệ quản trị.

## 6. Ước lượng số lượng thay cho đếm chính xác

Khi giao diện hoặc vận hành chỉ cần quy mô gần đúng, có thể dùng thống kê optimizer hoặc hàm ước lượng. Cần công bố rõ đây là ước lượng và kiểm tra độ mới.

### 6.1. Ước lượng số dòng toàn bảng

PostgreSQL lưu ước lượng số dòng trong `pg_class.reltuples`, được cập nhật bởi `ANALYZE` và một số hoạt động bảo trì:

```sql
SELECT c.reltuples::bigint AS estimated_rows,
       c.relpages
FROM pg_class AS c
WHERE c.oid = 'public.orders'::regclass;
```

`reltuples` là ước lượng, không phải số đếm chính xác tại snapshot hiện tại. Ước lượng có thể được scale theo kích thước relation và trở nên kém chính xác khi bảng thay đổi mạnh sau lần thu thập thống kê.

Trong MySQL, `SHOW TABLE STATUS` hoặc metadata của InnoDB có thể cung cấp số dòng ước lượng. Với InnoDB, `TABLE_ROWS` trong metadata không phải số đếm chính xác; không dùng nó cho nghiệp vụ yêu cầu con số tuyệt đối.

SQL Server có thể cung cấp số dòng ước lượng qua thống kê phân vùng:

```sql
SELECT SUM(row_count) AS estimated_rows
FROM sys.dm_db_partition_stats
WHERE object_id = OBJECT_ID(N'dbo.Orders')
  AND index_id IN (0, 1);
```

`row_count` trong DMV này được mô tả là số dòng ước lượng. Phạm vi `index_id IN (0, 1)` chọn heap hoặc clustered index, tránh cộng các nonclustered index và đếm trùng cùng dữ liệu.

Oracle có thể dùng `NUM_ROWS` trong `USER_TABLES` hoặc `ALL_TABLES`, nhưng giá trị phụ thuộc lần thu thập optimizer statistics gần nhất:

```sql
SELECT table_name, num_rows, last_analyzed
FROM user_tables
WHERE table_name = 'ORDERS';
```

Không dùng metadata ước lượng để kiểm tra số lượng hóa đơn, hạn mức hoặc điều kiện nghiệp vụ cần chính xác tuyệt đối.

### 6.2. Ước lượng theo điều kiện lọc

Optimizer có thể ước lượng số dòng thỏa predicate từ histogram, density và thống kê nhiều cột. Một số hệ quản trị cung cấp estimated rows trong execution plan hoặc giao diện thống kê. Ước lượng có thể sai nếu dữ liệu lệch, cột có tương quan, tham số khác giá trị phổ biến hoặc thống kê đã cũ.

Vì vậy, số dòng ước lượng phù hợp cho hiển thị quy mô hoặc chọn chiến lược vận hành có dung sai. Không dùng nó để quyết định nghiệp vụ yêu cầu chính xác, chẳng hạn số dư, số đơn cần đối soát hoặc số quyền truy cập được cấp.

### 6.3. Đếm distinct xấp xỉ

Đếm giá trị phân biệt thường tốn kém hơn đếm dòng vì phải loại bỏ trùng. Với dashboard phân tích, có thể dùng thuật toán sketch như HyperLogLog để ước lượng cardinality với bộ nhớ nhỏ và sai số có kiểm soát.

Một số hệ quản trị có hàm dựng sẵn, ví dụ `APPROX_COUNT_DISTINCT` trên các phiên bản SQL Server và Oracle hỗ trợ. PostgreSQL core không cung cấp cùng hàm tổng quát này; có thể dùng extension hoặc hệ thống phân tích có hỗ trợ sketch. Cú pháp, sai số và khả năng gộp sketch khác nhau theo sản phẩm.

Chỉ dùng kết quả xấp xỉ khi nghiệp vụ chấp nhận sai số. Ghi rõ thuật toán, phạm vi, sai số dự kiến và cách kiểm tra định kỳ bằng phép đếm chính xác trên mẫu hoặc kỳ đối soát.

## 7. Duy trì bộ đếm chính xác trước

Nếu cùng một bộ lọc được đếm liên tục và cần kết quả chính xác với độ trễ thấp, có thể duy trì bảng counter. Thay vì đếm lại hàng triệu dòng mỗi lần đọc, hệ thống cập nhật bộ đếm khi dữ liệu nguồn thay đổi.

Ví dụ bảng số đơn hoàn tất theo tenant:

```sql
CREATE TABLE tenant_order_counts (
    tenant_id       bigint PRIMARY KEY,
    completed_count bigint NOT NULL DEFAULT 0,
    updated_at      timestamptz NOT NULL
);
```

Khi tạo đơn hoàn tất, cập nhật dữ liệu nguồn và counter trong cùng transaction:

```sql
BEGIN;

INSERT INTO orders (order_id, tenant_id, status, created_at)
VALUES (:order_id, :tenant_id, 'COMPLETED', :created_at);

INSERT INTO tenant_order_counts (tenant_id, completed_count, updated_at)
VALUES (:tenant_id, 1, clock_timestamp())
ON CONFLICT (tenant_id)
DO UPDATE SET
    completed_count = tenant_order_counts.completed_count + 1,
    updated_at = EXCLUDED.updated_at;

COMMIT;
```

Ví dụ trên dùng cú pháp PostgreSQL và giả định mỗi đơn được tạo trực tiếp ở trạng thái hoàn tất. Nếu đơn có thể chuyển trạng thái, hủy hoặc xóa, cần cập nhật delta tương ứng. Transaction bảo đảm không có trường hợp đơn đã commit nhưng counter chưa commit hoặc ngược lại trong cùng database.

### 7.1. Xử lý chuyển trạng thái

Với bộ đếm `completed_count`, quy tắc delta có thể là:

| Thay đổi trạng thái | Delta |
|---|---:|
| `PENDING` → `COMPLETED` | +1 |
| `COMPLETED` → `CANCELLED` | -1 |
| `COMPLETED` → `COMPLETED` (chỉ sửa mô tả) | 0 |
| `CANCELLED` → `COMPLETED` | +1 |

Phải kiểm tra trạng thái cũ và mới trong cùng transaction, tránh cập nhật counter nhiều lần khi cùng một event được gửi lại. Có thể dùng optimistic version, event id duy nhất hoặc bảng inbox để chống xử lý trùng.

Nếu counter giảm xuống âm, thường có lỗi trong quy tắc delta, sự kiện bị xử lý lặp hoặc dữ liệu nguồn đã không đồng bộ. Không nên âm thầm ép về 0 vì sẽ che lỗi. Cần ghi nhận bất thường và đối soát.

### 7.2. Bộ đếm theo nhiều chiều

Nếu báo cáo cần số đơn theo tenant, trạng thái, ngày và kênh bán, có thể duy trì counter theo tổ hợp chiều. Tuy nhiên, số tổ hợp có thể tăng nhanh. Hãy chỉ giữ những chiều phục vụ truy vấn thường xuyên và xác định grain rõ ràng.

Một bảng counter có khóa `(tenant_id, sales_day, status)` có thể hỗ trợ báo cáo theo tenant/ngày/trạng thái, nhưng không trả lời được số khách hàng duy nhất nếu không lưu thông tin hoặc cấu trúc khác phù hợp.

### 7.3. Điểm nóng và tranh chấp cập nhật

Bộ đếm một dòng cho tenant có lưu lượng ghi rất cao có thể trở thành điểm nóng. Mọi transaction đều cập nhật cùng một row, gây lock contention và giảm throughput ghi. Một số cách giảm tranh chấp:

- Chia counter thành nhiều bucket theo shard hoặc hash, sau đó cộng các bucket khi đọc.
- Duy trì counter theo partition thời gian rồi cộng các kỳ cần thiết.
- Gom sự kiện theo batch và cập nhật counter theo lô.
- Dùng luồng cập nhật bất đồng bộ nếu có thể chấp nhận độ trễ và có cơ chế đối soát.

Chia shard làm truy vấn đọc phải cộng nhiều dòng và tăng độ phức tạp khi thay đổi số shard. Cần đo tải ghi, thời gian khóa và chi phí đọc tổng hợp trước khi chọn.

### 7.4. Đối soát và sửa sai

Counter phải có quy trình đối soát với bảng nguồn. Ví dụ định kỳ tính lại số đơn hoàn tất theo tenant rồi so với counter. Khi phát hiện lệch, cần xác định nguyên nhân và cập nhật theo transaction hoặc quy trình rebuild có kiểm soát.

Không nên xem counter là nguồn dữ liệu gốc. Bảng giao dịch vẫn là nguồn sự thật; counter là cấu trúc dẫn xuất để tối ưu đọc. Cần có khả năng tái tạo counter từ dữ liệu nguồn sau lỗi, triển khai sai hoặc thay đổi quy tắc nghiệp vụ.

## 8. Cache số lượng và độ mới dữ liệu

Nếu cùng một bộ lọc được gọi thường xuyên, cache kết quả đếm có thể giảm tải database. Tuy nhiên, cache chỉ có ích khi xác định được khóa cache, thời hạn, chính sách invalidation và mức sai lệch chấp nhận được.

Khóa cache cần bao gồm mọi thành phần ảnh hưởng kết quả, chẳng hạn tenant, quyền truy cập, trạng thái, khoảng thời gian, bộ lọc tìm kiếm và phiên bản quy tắc. Bỏ sót tenant hoặc quyền truy cập có thể trả số lượng sai và làm lộ thông tin giữa người dùng.

Các chiến lược thường dùng:

- **TTL ngắn:** đơn giản, chấp nhận số đếm cũ trong một khoảng thời gian.
- **Invalidation theo sự kiện:** xóa hoặc cập nhật cache khi dữ liệu nguồn thay đổi; cần tránh mất sự kiện.
- **Cache theo phiên bản:** tăng version khi dữ liệu thay đổi, key mới tự tách khỏi giá trị cũ.
- **Stale-while-revalidate:** trả số liệu gần nhất trong khi cập nhật nền, phù hợp dashboard chấp nhận độ trễ.

Cache không tự làm cho số liệu chính xác. Hãy hiển thị thời điểm cập nhật hoặc mô tả rõ số liệu có thể trễ nếu nghiệp vụ cần nhận biết.

## 9. Nhất quán giữa trang kết quả và tổng số

Nếu ứng dụng chạy truy vấn lấy trang và truy vấn đếm trong hai statement riêng, dữ liệu có thể thay đổi giữa hai lần đọc. Ví dụ, trang trả về 20 dòng, sau đó một transaction khác thêm 3 dòng trước khi truy vấn count chạy. Giao diện có thể hiển thị trang và tổng số không thuộc cùng một snapshot.

Nếu cần nhất quán chặt chẽ, có thể chạy hai truy vấn trong cùng transaction với isolation level cung cấp snapshot phù hợp. Cách cấu hình cụ thể tùy hệ quản trị; `READ COMMITTED` ở một số hệ thống tạo snapshot theo statement, còn `REPEATABLE READ` hoặc snapshot isolation có thể giữ góc nhìn nhất quán lâu hơn. Cần cân nhắc thời gian transaction và tác động tới version store/MVCC.

Một lựa chọn là trả tổng số cùng trang bằng window function:

```sql
SELECT order_id,
       created_at,
       total_amount,
       COUNT(*) OVER () AS total_count
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'COMPLETED'
ORDER BY created_at DESC, order_id DESC
OFFSET :offset ROWS
FETCH NEXT :page_size ROWS ONLY;
```

Window count có thể giúp trả kết quả trang và tổng trong cùng statement snapshot. Nhưng nó không làm phép đếm miễn phí: engine vẫn phải xác định tổng số dòng của tập lọc trước hoặc trong quá trình thực hiện. Nếu trang không có dòng nào, không có row để mang `total_count`; trường hợp đó cần xử lý riêng. Với truy vấn lớn, window count có thể làm mất lợi thế dừng sớm của truy vấn chỉ lấy một trang.

Nếu chỉ cần biết còn trang tiếp theo, lấy `page_size + 1` dòng thường rẻ hơn nhiều so với window count chính xác.

## 10. Tối ưu truy vấn đếm theo hệ quản trị

### 10.1. PostgreSQL

PostgreSQL không duy trì một số đếm chính xác toàn bảng trong catalog cho mọi snapshot. `COUNT(*)` phải đọc dữ liệu hoặc chỉ mục đủ để xác định các dòng nhìn thấy. Planner có thể dùng index-only scan nếu phù hợp, nhưng visibility map quyết định có cần heap fetch hay không.

Để xem ước lượng toàn bảng:

```sql
SELECT reltuples::bigint AS estimated_rows
FROM pg_class
WHERE oid = 'public.orders'::regclass;
```

`reltuples` được cập nhật bởi `ANALYZE` và các hoạt động bảo trì; nó không thay thế `COUNT(*)` chính xác. Với truy vấn lọc, có thể tạo partial index cho predicate ổn định và đo lại `EXPLAIN (ANALYZE, BUFFERS)`.

### 10.2. MySQL/InnoDB

Với InnoDB, `COUNT(*)` không lấy một bộ đếm chính xác toàn cục dùng chung cho mọi transaction vì các transaction có thể nhìn thấy tập row khác nhau theo MVCC. Engine thường đếm qua một chỉ mục phù hợp, thường là chỉ mục nhỏ nhất có thể dùng, hoặc cấu trúc bảng khi cần. Metadata như `TABLE_ROWS` chỉ là ước lượng.

Nếu truy vấn đếm có điều kiện, tạo secondary index phù hợp với predicate có thể giảm số entry phải kiểm tra. Xác nhận bằng `EXPLAIN ANALYZE` trên phiên bản hỗ trợ và theo dõi Performance Schema. Đừng coi `SHOW TABLE STATUS` là nguồn số lượng chính xác cho InnoDB.

### 10.3. SQL Server

`COUNT(*)` trả về kiểu `int`; nếu số dòng có thể vượt giới hạn `int`, dùng `COUNT_BIG(*)` để nhận `bigint`. SQL Server có thể dùng heap/clustered scan hoặc nonclustered index scan tùy chi phí. Với predicate ổn định, filtered index có thể giảm kích thước cấu trúc phải đọc.

`sys.dm_db_partition_stats.row_count` cung cấp số dòng ước lượng hữu ích cho dashboard quản trị nhanh, nhưng không thay thế truy vấn đếm chính xác trong nghiệp vụ. Khi cần chính xác theo điều kiện lọc, hãy dùng câu SQL tương ứng và đo plan.

### 10.4. Oracle Database

Oracle có thể thực hiện table scan, index fast full scan hoặc access path khác tùy điều kiện và thống kê. `NUM_ROWS` trong `USER_TABLES`/`ALL_TABLES` phản ánh optimizer statistics gần nhất, không phải số dòng chính xác tại thời điểm đọc.

Để xem số liệu runtime, có thể kết hợp execution plan và `DBMS_XPLAN.DISPLAY_CURSOR` với thống kê phù hợp. Với truy vấn đếm thường xuyên, đánh giá function/filtered logic, index phù hợp và khả năng duy trì summary/counter ở tầng ứng dụng.

## 11. Lựa chọn chiến lược theo yêu cầu nghiệp vụ

| Nhu cầu | Chiến lược phù hợp | Đánh đổi |
|---|---|---|
| Cần số lượng chính xác cho đối soát hoặc quyết định nghiệp vụ | `COUNT` chính xác trên dữ liệu nguồn hoặc counter được duy trì nguyên tử và đối soát | Có thể tốn I/O/CPU hoặc chi phí ghi counter |
| Chỉ cần biết có kết quả hay không | `EXISTS` hoặc truy vấn lấy một dòng | Không cung cấp tổng số |
| Chỉ cần biết còn trang tiếp theo | Lấy `page_size + 1` dòng | Không biết tổng số trang |
| Cần tổng số nhưng có thể trễ vài giây/phút | Cache hoặc summary có timestamp | Có thể cũ so với nguồn |
| Dashboard cần quy mô gần đúng | Metadata thống kê hoặc approximate count | Có sai số và phụ thuộc độ mới thống kê |
| Cần số distinct trên tập rất lớn, chấp nhận sai số | Approximate distinct/sketch | Kết quả không chính xác tuyệt đối |
| Cùng bộ lọc được đếm rất thường xuyên | Counter theo grain phù hợp | Cần idempotency, xử lý update/delete và đối soát |
| Chỉ cần hiển thị tối đa một ngưỡng | Đếm giới hạn đến `threshold + 1` | Chỉ chính xác dưới ngưỡng; phụ thuộc khả năng dừng sớm |

Đừng chọn kỹ thuật trước khi xác định độ chính xác cần thiết. Một phép đếm chính xác có thể là yêu cầu pháp lý hoặc nghiệp vụ; một con số trên dashboard có thể chỉ cần ước lượng. Hai trường hợp cần thiết kế khác nhau.

## 12. Quy trình đo và giảm chi phí đếm

1. **Xác định ngữ nghĩa:** đếm dòng, thực thể duy nhất, dòng sau join hay số kết quả sau quyền truy cập và bộ lọc.
2. **Xác định yêu cầu chính xác:** cần tuyệt đối chính xác tại snapshot nào, hay chấp nhận sai số/độ trễ bao nhiêu?
3. **Đo đường cơ sở:** ghi elapsed, CPU, logical/physical reads, actual rows, plan, sort/hash, spill và tần suất gọi.
4. **Kiểm tra predicate:** xác nhận điều kiện đếm khớp với truy vấn danh sách, không có hàm hoặc chuyển đổi không cần thiết trên cột lọc.
5. **Đánh giá chỉ mục:** xem index scan/index-only/covering access, thứ tự cột và khả năng dùng partial/filtered index.
6. **Loại bỏ công việc thừa:** dùng `EXISTS` khi chỉ cần kiểm tra tồn tại, tránh join gây nhân dòng, bỏ `COUNT(DISTINCT)` nếu định nghĩa nghiệp vụ không yêu cầu distinct.
7. **Xem lại giao diện:** nếu chỉ cần nút tiếp theo, dùng `page_size + 1`; nếu cần quy mô, cân nhắc ngưỡng hoặc ước lượng.
8. **Chọn cache/counter/summary nếu có tần suất cao:** xác định grain, invalidation, idempotency, transaction và cơ chế đối soát.
9. **Đo tải hỗn hợp:** kiểm tra ảnh hưởng của count và cập nhật counter lên truy vấn giao dịch khác.
10. **Xác minh kết quả:** so sánh số liệu với nguồn, kiểm thử dữ liệu đồng thời thay đổi và ghi lại độ trễ/độ mới sau triển khai.

### Ví dụ quyết định cho API danh sách

Một API trả 25 đơn hàng mỗi trang. Dashboard có hàng trăm request mỗi giây và hiện chạy thêm `COUNT(*)` chính xác cho mỗi request. Truy vấn đếm chiếm phần lớn logical reads, trong khi người dùng chủ yếu bấm Tiếp theo và hiếm khi cần biết tổng số.

Phương án có thể là:

1. Chuyển phân trang sang keyset dựa trên `(created_at, order_id)` và chỉ lấy 26 dòng.
2. Dùng dòng thứ 26 để xác định `has_next`; chỉ trả 25 dòng cho client.
3. Bỏ truy vấn count khỏi luồng mặc định.
4. Nếu màn hình quản trị cần tổng số, cung cấp thao tác đếm riêng hoặc hiển thị số liệu cache/ước lượng có thời điểm cập nhật.
5. Nếu nghiệp vụ cần số chính xác liên tục theo tenant và trạng thái, đánh giá counter nguyên tử và đối soát nền.

Đo lại request rate, p95/p99, logical reads, CPU và tải ghi. Nếu count bị loại bỏ nhưng API vẫn cần truy vấn đắt do `OFFSET` lớn, keyset pagination và chỉ mục sắp xếp phù hợp có thể giải quyết phần chi phí còn lại.

## 13. Những sai lầm thường gặp

- **Cho rằng `COUNT(*)` luôn miễn phí vì chỉ trả một dòng:** engine có thể phải đọc hàng triệu entry hoặc row.
- **Dùng `COUNT(column)` thay `COUNT(*)` mà không hiểu `NULL`:** hai biểu thức có ngữ nghĩa khác nhau.
- **Đếm sau join mà không xét nhân dòng:** số đơn hàng có thể bị đếm thành số dòng chi tiết.
- **Dùng `COUNT(DISTINCT)` để sửa mọi vấn đề join:** có thể che lỗi thiết kế và tạo chi phí sort/hash lớn.
- **Cho rằng index seek luôn nhanh:** đếm phần lớn bảng có thể cần đọc nhiều entry; scan chỉ mục hẹp có thể hợp lý hơn.
- **Tin metadata ước lượng là số chính xác:** thống kê có thể cũ hoặc không phản ánh snapshot hiện tại.
- **Dùng window count để tối ưu mọi trang:** phép đếm vẫn phải xử lý toàn bộ tập lọc và có thể ngăn dừng sớm.
- **Cộng counter mà không chống sự kiện trùng:** retry hoặc giao nhận ít nhất một lần có thể làm số lượng tăng sai.
- **Chỉ tăng counter mà quên update/delete:** bộ đếm sẽ lệch khi trạng thái hoặc bản ghi nguồn thay đổi.
- **Duy trì một row counter cho tenant có tải ghi rất lớn:** row nóng có thể gây lock contention.
- **Cache count nhưng thiếu tenant/quyền trong cache key:** có thể trả số lượng sai hoặc lộ thông tin.
- **Đo riêng count mà bỏ qua workload tổng:** tối ưu đọc có thể làm tăng chi phí ghi hoặc ảnh hưởng transaction khác.

## 14. Checklist thiết kế số lượng và phân trang

- [ ] Đã định nghĩa một đơn vị được đếm và phân biệt `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT)`.
- [ ] Đã kiểm tra join có làm nhân số dòng và xác định có cần `EXISTS` hay không.
- [ ] Đã bảo đảm truy vấn đếm dùng cùng điều kiện nghiệp vụ với truy vấn danh sách.
- [ ] Đã xác định tổng số cần chính xác tuyệt đối, ước lượng hay chỉ cần `has_next`.
- [ ] Đã đo execution plan, actual rows, logical reads, CPU, elapsed và spill.
- [ ] Đã kiểm tra index/covering access và khả năng dùng partial hoặc filtered index.
- [ ] Đã cân nhắc keyset pagination hoặc giới hạn đếm thay cho full count.
- [ ] Đã đánh giá độ mới và sai số nếu dùng metadata, cache hoặc approximate count.
- [ ] Đã thiết kế idempotency, xử lý update/delete và đối soát nếu duy trì counter.
- [ ] Đã kiểm tra điểm nóng và lock contention khi cập nhật counter đồng thời.
- [ ] Đã bảo đảm cache key chứa tenant, quyền và toàn bộ bộ lọc ảnh hưởng kết quả.
- [ ] Đã xác định mức nhất quán giữa trang và tổng số trong điều kiện dữ liệu thay đổi đồng thời.
- [ ] Đã benchmark p95/p99, throughput, CPU, I/O và chi phí ghi trước/sau.

Đếm chính xác là cần thiết khi con số ảnh hưởng trực tiếp tới nghiệp vụ, đối soát hoặc quyết định có yêu cầu tuyệt đối. Với giao diện phân trang và dashboard, có nhiều trường hợp chỉ cần biết còn dữ liệu, một con số giới hạn, số liệu gần đúng hoặc bộ đếm được duy trì trước. Xác định đúng ngữ nghĩa và mức chính xác trước khi chọn kỹ thuật giúp giảm I/O, CPU và độ trễ mà vẫn giữ được tính đúng đắn của kết quả.
