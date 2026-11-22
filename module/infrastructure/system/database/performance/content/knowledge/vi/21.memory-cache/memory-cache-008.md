# Bộ đệm kế hoạch và khác biệt với bộ đệm dữ liệu hoặc kết quả

Một câu SQL được gửi nhiều lần có thể được xử lý nhanh hơn nếu hệ quản trị tái sử dụng kế hoạch đã phân tích và tối ưu. Dữ liệu mà câu truy vấn cần cũng có thể đã nằm trong RAM, giúp tránh đọc từ storage. Trong một số hệ quản trị hoặc kiến trúc ứng dụng, kết quả cuối cùng của truy vấn còn có thể được cache để dùng lại. Ba cơ chế này giải quyết ba loại công việc khác nhau: **plan cache** giữ kế hoạch thực thi, **data/page cache** giữ trang dữ liệu và chỉ mục, còn **query result cache** giữ kết quả đã tính.

Bài học thuộc chương **Bộ nhớ và bộ đệm** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Phân biệt đúng các cache giúp xác định truy vấn chậm do biên dịch, đọc dữ liệu, tính toán hay chờ kết quả; từ đó chọn thay đổi phù hợp và đo lại bằng số liệu.

## 1. Ba loại cache phục vụ ba mục tiêu khác nhau

| Loại cache | Nội dung được giữ | Công việc có thể tránh hoặc giảm | Ví dụ tên gọi/cơ chế |
|---|---|---|---|
| Plan cache | Câu lệnh đã phân tích, metadata liên quan và/hoặc kế hoạch thực thi đã tối ưu | Parse, compile, optimize hoặc một phần công việc chuẩn bị câu lệnh | SQL Server plan cache; Oracle library cache/shared SQL area; prepared statement plan trong PostgreSQL theo session |
| Data/page cache | Các page/block dữ liệu và index | Đọc page từ tầng lưu trữ khi page đã có trong RAM | SQL Server buffer pool; PostgreSQL `shared_buffers`; InnoDB buffer pool; Oracle database buffer cache |
| Query result cache | Kết quả truy vấn hoặc một phần kết quả đã tính | Đọc, join, aggregate và tính toán lại nếu kết quả còn hợp lệ | Oracle SQL Query Result Cache; cache ở ứng dụng/proxy; kết quả vật hóa trong materialized view là một cơ chế lưu trước khác |

Không nên gọi tất cả là “database cache” rồi kết luận chung rằng cache hit sẽ làm truy vấn nhanh. Một truy vấn có thể dùng lại plan nhưng vẫn đọc nhiều page từ storage; có thể đọc toàn bộ page từ RAM nhưng phải chạy join và aggregate tốn CPU; hoặc có result-cache hit và tránh được phần lớn công việc thực thi SQL.

### 1.1. Mô hình xử lý một câu truy vấn

Một luồng xử lý đơn giản có thể hình dung như sau:

```text
Ứng dụng gửi SQL và tham số
             |
             v
       Parse / bind
             |
             v
 Kiểm tra result cache (nếu có)
          /       \
       hit         miss
        |            |
   Trả kết quả      Kiểm tra plan cache
        |             /       \
        |           hit         miss
        |            |            |
        |         dùng plan    optimize / compile
        |            |            |
        |            +-----<------+
        |                 |
        |                 v
        |        Thực thi các toán tử
        |                 |
        |                 v
        |        Đọc page qua data cache
        |            /          \
        |          hit          miss
        |           |             |
        |        RAM page     storage I/O
        |           \            /
        |            +----------+
        |                 |
        |                 v
        |           Tính kết quả
        |                 |
        |                 v
        |       Lưu result nếu đủ điều kiện
        |                 |
        +-----------------+
                 |
                 v
        Trả kết quả cho ứng dụng
```

Sơ đồ chỉ mô tả các khái niệm. Thứ tự kiểm tra result cache, parse/plan, data cache và cách một engine thực hiện có thể khác nhau. Một result-cache hit có thể cho phép bỏ qua phần lớn luồng thực thi; nhiều hệ quản trị không có result cache tự động cho mọi câu SQL.

## 2. Plan cache giữ những gì?

Khi nhận một câu SQL, hệ quản trị cần phân tích cú pháp, phân giải tên bảng/cột, kiểm tra quyền và kiểu dữ liệu, xây dựng các phương án truy cập rồi chọn kế hoạch có chi phí ước lượng phù hợp. Quá trình này thường được gọi là parse, bind, optimize và compile/plan, dù thuật ngữ khác nhau giữa sản phẩm.

Kế hoạch thực thi có thể chứa:

- Các toán tử như table scan, index seek/scan, join, sort, aggregate và filter.
- Thứ tự join và phương thức join.
- Chỉ mục hoặc access path được chọn.
- Ước lượng số hàng, chi phí và thông tin thống kê được dùng khi tối ưu.
- Cách truyền tham số, kiểu dữ liệu và một số thuộc tính môi trường cần để thực thi.
- Thông tin phụ thuộc schema, object và quyền truy cập.

Plan cache giữ một biểu diễn có thể tái sử dụng của câu lệnh hoặc kế hoạch. Khi câu lệnh tương thích được gửi lại, DBMS có thể tránh một phần công việc phân tích/tối ưu. Tuy nhiên, plan reuse không có nghĩa kết quả truy vấn cũng được giữ lại. Các toán tử vẫn phải chạy và đọc dữ liệu theo kế hoạch.

### 2.1. Vì sao plan reuse có ích?

Plan reuse đặc biệt hữu ích khi:

- Một câu SQL được gọi rất thường xuyên.
- Câu lệnh có nhiều join, biểu thức hoặc logic tối ưu phức tạp.
- Hệ thống có nhiều request ngắn, trong đó chi phí compile chiếm tỷ lệ đáng kể.
- Ứng dụng dùng prepared statement hoặc parameterized SQL ổn định.

Nếu mỗi request tạo một câu SQL khác nhau chỉ vì nhúng literal, hệ quản trị có thể phải parse/optimize nhiều lần và lưu nhiều plan gần giống nhau. Điều này tiêu tốn CPU và bộ nhớ plan cache.

### 2.2. Cache key và điều kiện tái sử dụng

DBMS không thể tái sử dụng một plan chỉ vì hai câu SQL “trông gần giống”. Việc khớp cache có thể phụ thuộc:

- Nội dung SQL sau chuẩn hóa và cấu trúc tham số.
- Kiểu dữ liệu, độ dài và cách bind tham số.
- Schema, database, owner hoặc search path.
- Các tùy chọn session, isolation level, collation và SET options.
- Phiên bản schema, metadata, object dependency và quyền.
- Các hint, optimizer settings hoặc execution context.

Các yếu tố chính xác khác nhau theo hệ quản trị. Ví dụ, hai câu lệnh khác kiểu tham số hoặc khác session setting có thể tạo nhiều plan riêng, hoặc một plan không thể dùng lại trong context mới.

### 2.3. Literal SQL và parameterized SQL

Ví dụ hai câu SQL có cùng cấu trúc nhưng khác literal:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 1001;
```

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 1002;
```

Nếu ứng dụng tạo chuỗi SQL mới cho mỗi khách hàng, một số hệ quản trị có thể coi đây là các statement khác nhau. Parameterized SQL diễn đạt cùng một mẫu truy vấn:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = :customer_id;
```

Tên placeholder tùy driver và DBMS. Parameterization giúp tăng khả năng tái sử dụng plan và giảm nguy cơ SQL injection khi bind đúng cách. Tuy nhiên, một plan dùng chung cho mọi giá trị không phải lúc nào cũng là plan tốt nhất nếu phân bố dữ liệu lệch mạnh.

## 3. Data cache giữ page, không giữ kết quả truy vấn

Data cache lưu page hoặc block của bảng và chỉ mục. Khi một truy vấn cần page đã có trong buffer pool/shared buffers, DBMS có thể đọc page trong RAM. Nhưng nó vẫn phải chạy các toán tử cần thiết: tìm hàng, kiểm tra predicate, join, sort, aggregate và tạo kết quả.

Ví dụ:

```sql
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE created_at >= :start_time
  AND created_at < :end_time
GROUP BY customer_id;
```

Nếu mọi page cần thiết đều nằm trong buffer pool, truy vấn có thể tránh physical read. Nhưng DBMS vẫn phải duyệt các hàng phù hợp, cộng tổng theo nhóm và tạo output. Nếu phạm vi có hàng chục triệu bản ghi, CPU và memory cho aggregate vẫn có thể lớn.

### 3.1. Logical reads và physical reads

Logical read thường mô tả việc DBMS truy cập page qua cache do nó quản lý. Physical read thường mô tả việc DBMS phải yêu cầu đọc page từ tầng I/O thấp hơn theo định nghĩa của sản phẩm. Các thuật ngữ và counter khác nhau giữa DBMS; một miss ở buffer pool không nhất thiết đồng nghĩa thiết bị vật lý đã đọc vì OS page cache hoặc tầng storage cache có thể đáp ứng.

Nếu logical reads cao nhưng physical reads thấp, truy vấn vẫn có thể tốn CPU do đọc nhiều page trong RAM. Nếu physical reads và storage latency cao, có thể có vấn đề working set, cache churn hoặc storage bottleneck. Không dùng một counter riêng lẻ để kết luận.

### 3.2. Data cache có thể dùng chung giữa nhiều câu SQL

Page của bảng `orders` có thể được dùng bởi nhiều truy vấn. Khi một truy vấn nạp page vào buffer pool, truy vấn khác có thể hưởng lợi nếu page còn nằm trong cache. Đây là khác biệt quan trọng với result cache: cache page lưu dữ liệu nền, không lưu một tập hàng đã lọc theo một câu SQL cụ thể.

Một truy vấn có thể làm nóng data cache cho truy vấn khác, nhưng cũng có thể gây cache pollution nếu quét một vùng dữ liệu lớn ít tái sử dụng và đẩy page nóng ra ngoài.

## 4. Query result cache giữ kết quả đã tính

Query result cache lưu kết quả của một truy vấn hoặc một đơn vị tính toán để lần gọi sau có thể trả lại mà không thực hiện lại toàn bộ truy vấn. Nếu cache hit và kết quả còn hợp lệ, hệ thống có thể tránh đọc page, join, sort và aggregate.

Result cache có yêu cầu khó hơn data cache vì kết quả phụ thuộc nhiều yếu tố:

- Dữ liệu của tất cả bảng và view tham gia.
- Tham số đầu vào và kiểu dữ liệu.
- Quyền truy cập, row-level security và ngữ cảnh người dùng.
- Session settings, timezone, locale và collation.
- Thời điểm dữ liệu được đọc và transaction snapshot.
- Hàm không xác định (non-deterministic), sequence, current time hoặc trạng thái bên ngoài.

Khi dữ liệu nền thay đổi, kết quả cũ có thể không còn đúng. Hệ thống phải có quy tắc invalidation, dependency tracking, expiration hoặc chấp nhận độ trễ nhất quán đã được định nghĩa.

### 4.1. Result cache khác materialized view

Materialized view lưu trước kết quả của một truy vấn định nghĩa, thường tồn tại như một đối tượng dữ liệu có thể refresh. Query result cache thường là cơ chế cache runtime, được hệ quản trị hoặc ứng dụng quản lý theo key và chính sách invalidation/expiration.

Materialized view có thể được refresh theo lịch hoặc theo cơ chế incremental tùy sản phẩm; giữa các lần refresh, dữ liệu có thể cũ. Result cache có thể tự invalidation theo dependency nếu DBMS hỗ trợ, nhưng cũng có thể bị giới hạn hoặc không áp dụng cho truy vấn đó. Hai cơ chế không nên được coi là một.

### 4.2. Cache kết quả ở tầng ứng dụng

Ứng dụng hoặc distributed cache như Redis có thể lưu response/query result theo key do ứng dụng thiết kế. Cách này giúp giảm tải DB, nhưng ứng dụng phải chịu trách nhiệm:

- Xác định key bao gồm mọi tham số ảnh hưởng kết quả.
- Phân tách tenant, user, quyền và locale.
- Invalidate khi dữ liệu thay đổi hoặc dùng TTL phù hợp.
- Tránh trả dữ liệu nhạy cảm của người dùng này cho người dùng khác.
- Xử lý cache stampede khi nhiều request cùng làm hết hạn một key.
- Quy định chấp nhận stale data trong bao lâu.

Cache ở ứng dụng không tự biết transaction hoặc dependency trong DB. Nếu invalidation không đầy đủ, dữ liệu cũ có thể được trả dù DB đã commit cập nhật mới.

## 5. Một truy vấn có thể hit cache này nhưng miss cache khác

Ba cache độc lập về mục tiêu, vì vậy có nhiều tình huống:

| Plan cache | Data cache | Result cache | Hành vi khái quát |
|---|---|---|---|
| Hit | Hit | Không dùng | Dùng plan có sẵn, đọc page từ RAM, vẫn chạy các toán tử |
| Hit | Miss | Không dùng | Dùng plan có sẵn nhưng cần nạp page từ tầng I/O thấp hơn |
| Miss | Hit | Không dùng | Phải parse/optimize/compile, nhưng dữ liệu có thể đã ở RAM |
| Hit | Hit | Hit | Nếu result cache được kiểm tra và hợp lệ, có thể trả kết quả mà không chạy phần lớn plan |
| Miss | Miss | Không dùng | Vừa chuẩn bị plan vừa nạp page; thường là đường chạy lạnh nhưng không nhất thiết mọi tầng cache đều lạnh |

Ví dụ một truy vấn chạy lần đầu sau khi ứng dụng khởi động có thể cần compile plan, nhưng các page đã nóng do truy vấn khác. Một truy vấn chạy lặp lại có thể dùng lại plan và data pages nhưng vẫn mất nhiều CPU để aggregate. Một result-cache hit có thể trả kết quả rất nhanh dù data page đã bị đẩy khỏi buffer pool, miễn result cache vẫn hợp lệ và DBMS có thể sử dụng nó.

## 6. Plan cache không bảo đảm plan luôn phù hợp

Plan cache giảm chi phí lập kế hoạch, nhưng plan được tạo từ thông tin và giả định tại một thời điểm. Khi tham số, phân bố dữ liệu, thống kê hoặc môi trường thay đổi, plan cũ có thể không còn là lựa chọn tốt nhất.

### 6.1. Parameter sniffing và data skew

Giả sử bảng `orders` có 100 triệu hàng. Một khách hàng lớn có 20 triệu đơn hàng, còn phần lớn khách hàng chỉ có vài chục đơn. Câu truy vấn:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = @customer_id;
```

Nếu plan được tối ưu lần đầu với một khách hàng chỉ có 10 đơn, bộ tối ưu có thể chọn index seek và lookup. Plan đó có thể không phù hợp với khách hàng có 20 triệu đơn. Ngược lại, plan được tối ưu cho khách hàng rất lớn có thể chọn scan, nhưng lại tốn kém với khách hàng nhỏ.

Hiện tượng plan phụ thuộc tham số đầu tiên hoặc tham số được sniff tại compile thường được gọi là parameter sniffing trong SQL Server; các hệ quản trị khác có cơ chế bind peeking hoặc generic/custom plan với hành vi riêng.

### 6.2. Generic plan và custom plan

Một generic plan dùng một kế hoạch chung cho nhiều giá trị tham số. Một custom plan được tối ưu dựa trên giá trị cụ thể của lần thực thi. Generic plan có thể tiết kiệm compile CPU nhưng kém phù hợp khi phân bố tham số lệch. Custom plan có thể chọn access path tốt hơn cho từng tham số nhưng làm tăng chi phí planning.

Lựa chọn cần cân bằng:

- Tần suất truy vấn và chi phí compile.
- Mức độ lệch phân bố tham số.
- Sự khác nhau giữa số hàng thực tế của các giá trị.
- Độ ổn định của execution plan.
- CPU tổng thể khi concurrency cao.

### 6.3. Kế hoạch cũ và thống kê mới

Thống kê thay đổi có thể khiến cardinality estimate khác trước. DDL, index creation/drop, schema change, object dependency hoặc cấu hình optimizer cũng có thể làm plan mất hiệu lực hoặc cần compile lại. Cách invalidation và thời điểm recompile phụ thuộc hệ quản trị.

Không nên xóa toàn bộ plan cache ngay khi thấy một query chậm. Hành động đó có thể làm hàng loạt câu lệnh phải compile lại, tạo CPU spike và latency tăng trên toàn hệ thống. Trước tiên hãy xác định plan cụ thể, lý do plan không phù hợp và phạm vi invalidation cần thiết.

## 7. Plan cache bloat và SQL ad hoc

Nếu ứng dụng sinh nhiều câu SQL khác nhau do nối literal, comment thay đổi hoặc cấu trúc không chuẩn hóa, plan cache có thể chứa nhiều plan ít được dùng. Đây là một dạng plan cache bloat.

Ví dụ ứng dụng tạo:

```sql
SELECT * FROM products WHERE category_id = 10;
SELECT * FROM products WHERE category_id = 11;
SELECT * FROM products WHERE category_id = 12;
```

Parameterized SQL:

```sql
SELECT *
FROM products
WHERE category_id = @category_id;
```

có thể tăng khả năng plan reuse. Nhưng parameterization phải giữ kiểu dữ liệu đúng. Nếu ứng dụng bind `NVARCHAR` trong khi cột là `VARCHAR`, implicit conversion có thể ảnh hưởng index usage hoặc cardinality estimate tùy hệ quản trị.

### 7.1. Dấu hiệu plan cache bloat

- Số lượng plan hoặc statement cache entry tăng nhanh.
- Nhiều plan có cùng cấu trúc nhưng khác literal.
- Tỷ lệ compile/recompile cao so với số lần thực thi.
- Bộ nhớ dành cho plan cache tăng, gây áp lực lên các vùng nhớ khác.
- Nhiều plan chỉ được dùng một lần hoặc rất ít lần.

Không kết luận chỉ từ số plan lớn. Hệ thống có thể có nhiều truy vấn hợp lệ và workload đa dạng. Cần phân nhóm theo query shape, số lần sử dụng, bộ nhớ và compile CPU.

### 7.2. Parameterization có giới hạn

Parameterization không phải lúc nào cũng tốt hơn literal. Có truy vấn cần plan khác nhau theo nhóm tham số hoặc dùng dynamic SQL có cấu trúc thực sự khác nhau. Một số hệ quản trị hỗ trợ adaptive plan, parameter-sensitive plan hoặc nhiều plan variant để xử lý skew. Cần hiểu tính năng phiên bản đang chạy và kiểm chứng plan thực tế.

## 8. Invalidation, eviction và recompile

Plan cache không phải kho lưu trữ vĩnh viễn. Một entry có thể bị loại bỏ khi:

- Bộ nhớ bị áp lực và cache cần giải phóng không gian.
- Plan ít được sử dụng hoặc hết thời gian lưu theo chính sách engine.
- Schema, index, object hoặc dependency thay đổi.
- Thống kê được cập nhật theo cơ chế có thể invalidation plan.
- Session settings, quyền hoặc execution context không còn tương thích.
- Người quản trị hoặc ứng dụng yêu cầu recompile/flush theo phạm vi cụ thể.

Eviction và invalidation là hai khái niệm liên quan nhưng khác nhau. Eviction thường là loại entry ra khỏi cache để giải phóng tài nguyên; invalidation đánh dấu plan không còn an toàn hoặc phù hợp để tái sử dụng. Recompile tạo lại plan khi cần.

### 8.1. Recompile không phải lúc nào cũng xấu

Compile lại có chi phí CPU, nhưng có thể cần thiết sau khi schema, index hoặc thống kê thay đổi. Một plan mới có thể cải thiện hiệu năng đáng kể nếu plan cũ đã lỗi thời. Mục tiêu không phải loại bỏ mọi compile mà là tránh compile không cần thiết và bảo đảm plan được tái tạo khi cần.

### 8.2. Tránh xóa cache diện rộng để xử lý một query

Lệnh flush toàn bộ plan cache có thể làm nhiều truy vấn nóng mất plan cùng lúc. Sau đó, các request đồng thời phải compile lại, gây CPU spike và tăng latency. Nếu cần kiểm tra tác động của cache lạnh, thực hiện trong môi trường thử nghiệm hoặc dùng cơ chế xóa theo phạm vi nhỏ nhất mà hệ quản trị hỗ trợ.

Không xóa data cache để “làm mới plan”: hai cache có vòng đời khác nhau. Xóa data cache cũng không giải quyết plan không phù hợp; nó chỉ làm page phải được nạp lại từ tầng thấp hơn.

## 9. Khác biệt theo hệ quản trị

Các sản phẩm dùng tên gọi và phạm vi cache khác nhau. Không nên áp dụng kết luận của một engine cho engine khác.

### 9.1. SQL Server

SQL Server có plan cache trong bộ nhớ để lưu các compiled plans và hỗ trợ plan reuse. Buffer pool giữ data/index pages. Hai cơ chế độc lập: plan reuse giảm compile work, còn buffer pool hit giảm việc đọc page từ storage.

Các công cụ thường dùng:

```sql
-- Tổng quan số lần thực thi và thời gian compile của statement trong cache
SELECT TOP (20)
    qs.execution_count,
    qs.total_worker_time,
    qs.total_elapsed_time,
    qs.total_logical_reads,
    SUBSTRING(
        st.text,
        (qs.statement_start_offset / 2) + 1,
        ((CASE qs.statement_end_offset
            WHEN -1 THEN DATALENGTH(st.text)
            ELSE qs.statement_end_offset
          END - qs.statement_start_offset) / 2) + 1
    ) AS statement_text
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
ORDER BY qs.total_worker_time DESC;
```

DMV trên chỉ phản ánh các plan/statement còn trong cache tại thời điểm đọc; entry có thể bị loại bỏ và số liệu bị reset theo vòng đời cache hoặc instance. Quyền xem DMV phụ thuộc phiên bản và quyền server.

Query Store lưu lịch sử query, plan và runtime statistics theo thời gian để phân tích thay đổi; nó không phải plan cache và cũng không phải result cache. Query Store có thể giúp phát hiện plan regression ngay cả khi plan cũ không còn nằm trong cache.

SQL Server không có một query result cache tổng quát tự động áp dụng cho mọi câu SELECT như một số người thường hình dung. Indexed view, memory-optimized objects hoặc cache ở tầng ứng dụng là các cơ chế khác với plan cache.

### 9.2. Oracle Database

Oracle dùng shared pool trong SGA; library cache lưu các SQL area/cursor và thông tin thực thi có thể tái sử dụng. Database buffer cache lưu database blocks. Oracle còn có SQL Query Result Cache riêng để cache kết quả của những truy vấn đủ điều kiện và được cấu hình/sử dụng phù hợp.

Một số view hữu ích:

```sql
SELECT sql_id, executions, parse_calls, loads, invalidations,
       buffer_gets, disk_reads
FROM v$sql
ORDER BY buffer_gets DESC;
```

`V$SQL` có thể cho thấy executions, parse calls, loads và invalidations của cursor đang được giữ. Các view `V$LIBRARYCACHE`, `V$SQL_SHARED_CURSOR`, `V$RESULT_CACHE_OBJECTS` và `V$RESULT_CACHE_STATISTICS` có thể hỗ trợ điều tra thêm tùy phiên bản/quyền.

SQL Query Result Cache có thể cache kết quả của truy vấn đủ điều kiện; thay đổi dữ liệu phụ thuộc có thể invalidation kết quả. Không phải mọi câu SQL đều được cache, và việc dùng result cache cần cân nhắc tính biến động dữ liệu, session context, quyền và chi phí duy trì.

### 9.3. PostgreSQL

PostgreSQL có `shared_buffers` để cache data pages. Với prepared statements, server có thể giữ thông tin parse/plan trong phạm vi session và chọn custom plan hoặc generic plan theo cơ chế của nó. PostgreSQL không có một plan cache chia sẻ toàn cục cho mọi câu SQL giống cách SQL Server giữ compiled plan trong plan cache.

Có thể xem prepared statements của session:

```sql
SELECT name, statement, prepare_time,
       parameter_types, from_sql, generic_plans, custom_plans
FROM pg_prepared_statements;
```

View này chỉ cho biết prepared statements trong session hiện tại và các cột thống kê phụ thuộc phiên bản. Cơ chế chọn generic/custom plan có thể được điều khiển/quan sát bằng các tùy chọn như `plan_cache_mode` ở phiên bản hỗ trợ.

PostgreSQL không cung cấp một query result cache trong lõi tự động cache mọi kết quả SELECT. Ứng dụng, proxy, extension hoặc materialized view có thể đáp ứng nhu cầu cache kết quả, nhưng mỗi cách có semantics và invalidation riêng. `EXPLAIN` và `pg_stat_statements` giúp quan sát kế hoạch và workload, nhưng không phải cache kết quả.

### 9.4. MySQL

InnoDB buffer pool cache data/index pages. Prepared statements phía server có thể giảm chi phí parse và quản lý statement; metadata change có thể khiến statement cần reprepare. Không nên mặc định MySQL có một shared execution plan cache tổng quát, dùng chung giữa mọi session, tương tự SQL Server plan cache. Chi tiết prepare/optimize và tái sử dụng phụ thuộc phiên bản, statement type và engine.

MySQL Query Cache cũ đã bị loại bỏ từ MySQL 8.0. Vì vậy, với MySQL hiện đại không nên dựa vào query cache tích hợp cũ để cache kết quả SELECT. Nếu cần result caching, cân nhắc cache ở ứng dụng/proxy hoặc cơ chế vật hóa dữ liệu phù hợp và tự quản lý tính nhất quán.

Các công cụ quan sát gồm Performance Schema, `sys` schema, statement digest, prepared statement status và InnoDB metrics. Chúng giúp phân tích parse/execute, buffer pool và query workload nhưng cần đọc theo phiên bản cụ thể.

### 9.5. Bảng so sánh nhanh

| Hệ quản trị | Plan/statement reuse | Data cache | Result cache tổng quát |
|---|---|---|---|
| SQL Server | Plan cache dùng chung trong instance; Query Store lưu lịch sử riêng | Buffer pool | Không có result cache tự động tổng quát cho mọi SELECT; indexed view là cơ chế khác |
| Oracle | Library cache/shared SQL area trong shared pool | Database buffer cache | Có SQL Query Result Cache với điều kiện và cấu hình riêng |
| PostgreSQL | Prepared statement plan theo session; custom/generic plan | `shared_buffers` và có thể cả OS page cache | Không có result cache tổng quát trong lõi; dùng application cache, extension hoặc materialized view |
| MySQL | Prepared statement reuse; không nên giả định shared plan cache tổng quát | InnoDB buffer pool | Query Cache bị loại bỏ từ 8.0; thường dùng tầng ứng dụng/proxy hoặc vật hóa |

Đây là khái quát theo các phiên bản phổ biến. Hãy kiểm tra tài liệu đúng phiên bản, engine, edition và cấu hình trước khi dựa vào một tính năng cụ thể.

## 10. Query Store, plan history và plan cache là gì?

Plan cache thường phục vụ tái sử dụng plan đang có hiệu lực trong bộ nhớ. Một công cụ lưu lịch sử kế hoạch có mục tiêu khác: ghi nhận plan đã từng được dùng, thời gian chạy, số lần thực thi và biến động theo thời gian.

Ví dụ SQL Server Query Store có thể lưu query text, plan và runtime stats trong một khoảng thời gian. Nó hỗ trợ so sánh plan regression và có thể cung cấp khả năng force plan trong điều kiện phù hợp. Nhưng Query Store không phải bộ nhớ chứa data pages, không tự trả lại kết quả truy vấn và không đồng nghĩa với plan cache.

Tương tự, lịch sử execution plan trong công cụ giám sát không có nghĩa DBMS sẽ tái sử dụng plan đó. Cần phân biệt:

- Plan đang nằm trong cache và có thể được dùng lại.
- Plan đã được lưu trong repository/history để phân tích.
- Plan đang bị force hoặc được quản lý bởi tính năng ổn định kế hoạch.
- Plan thực tế của lần chạy hiện tại.

## 11. Result cache và tính nhất quán dữ liệu

Result cache có thể đem lại tốc độ rất cao cho truy vấn lặp lại trên dữ liệu ít thay đổi, nhưng nguy cơ lớn nhất là trả kết quả cũ hoặc sai context.

### 11.1. Invalidation theo dependency

Nếu kết quả phụ thuộc bảng `products`, khi một sản phẩm thay đổi, cache cần biết entry nào bị ảnh hưởng. DBMS có thể theo dõi dependency và invalidation; cache ứng dụng có thể cần phát event hoặc xóa key thủ công.

Nếu một kết quả phụ thuộc nhiều bảng, view, function hoặc dữ liệu ngoài DB, quy tắc invalidation càng phức tạp. TTL đơn giản không bảo đảm dữ liệu mới ngay sau commit; nó chỉ giới hạn thời gian stale tối đa theo giả định cache hoạt động đúng.

### 11.2. Transaction visibility

Một truy vấn trong transaction có thể phải nhìn thấy snapshot nhất quán theo isolation level. Kết quả cache được tạo ở snapshot khác có thể không hợp lệ với transaction hiện tại. DBMS tích hợp result cache phải tự áp dụng quy tắc visibility của nó; ứng dụng tự cache phải hiểu rằng một key không chỉ phụ thuộc SQL và tham số nếu kết quả còn phụ thuộc tenant, quyền hoặc snapshot.

Không đưa dữ liệu phụ thuộc quyền truy cập vào một cache dùng chung nếu key không phân biệt security context. Một result cache đúng về SQL nhưng sai về quyền vẫn là lỗi dữ liệu nghiêm trọng.

### 11.3. Truy vấn không phù hợp để cache kết quả

Các truy vấn có thể không phù hợp hoặc không đủ điều kiện cache khi phụ thuộc:

- `CURRENT_TIMESTAMP`, random hoặc hàm không xác định.
- Sequence hoặc trạng thái thay đổi theo lần gọi.
- Temporary table hoặc dữ liệu session-specific.
- Session variables, locale, timezone hoặc security context không nằm trong cache key.
- Dữ liệu thay đổi liên tục khiến invalidation gần như xảy ra sau mỗi lần cache.
- Kết quả rất lớn hoặc ít được tái sử dụng, khiến chi phí lưu trữ vượt lợi ích.

Khả năng cache của DBMS còn phụ thuộc danh sách câu lệnh, hàm và object được hỗ trợ. Hãy kiểm tra tài liệu và actual behavior thay vì suy đoán từ một truy vấn SELECT đơn giản.

### 11.4. Cache stampede và thundering herd

Khi một result-cache entry hết hạn hoặc bị invalidation, nhiều request có thể đồng thời tính lại cùng kết quả. Điều này tạo tải đột biến lên DB. Các biện pháp ở tầng ứng dụng có thể gồm single-flight/request coalescing, stale-while-revalidate nếu nghiệp vụ cho phép, jitter cho TTL, refresh trước khi hết hạn và giới hạn concurrency của tác vụ làm mới.

Không dùng stale-while-revalidate cho dữ liệu cần nhất quán tức thời như số dư hoặc trạng thái tồn kho nếu nghiệp vụ không cho phép dữ liệu cũ.

## 12. Đo hiệu quả từng loại cache

Để xác định cache nào có tác dụng, hãy đo riêng từng loại thay vì chỉ dùng một chỉ số “cache hit ratio”.

| Loại cache | Chỉ số nên quan sát | Câu hỏi |
|---|---|---|
| Plan cache | Parse/compile count, compile CPU/time, execution count, plan reuse, recompile, số plan ít dùng, cache memory | Có đang compile lặp lại hoặc giữ quá nhiều plan không? |
| Data cache | Buffer hits/misses, logical/physical reads, page reads, storage latency, cache churn, dirty pages | Truy vấn có đọc nhiều page và miss có dẫn đến I/O chậm không? |
| Result cache | Hit/miss, entry count/size, evictions, invalidations, stale/refresh events, lookup latency | Kết quả có được tái sử dụng và còn hợp lệ không? |

Ngoài ra, đo:

- p50/p95/p99 latency của query và request.
- Throughput thành công, error rate và timeout.
- CPU, RAM, I/O, lock waits và connection queue.
- Query plan thực tế, estimated/actual rows, logical reads và số lần thực thi.
- Tác động lên các truy vấn khác khi cache chiếm thêm bộ nhớ.

### 12.1. Dùng delta thay vì counter tích lũy

Nhiều counter là số tích lũy từ lúc instance khởi động hoặc từ lần reset thống kê. Hãy lấy hai snapshot cách nhau một cửa sổ đo và tính delta. So sánh các khoảng có cùng loại workload, concurrency và thời lượng.

Không so sánh hit ratio của một máy chủ chạy nhiều tuần với máy vừa restart mà không chuẩn hóa trạng thái cache và thời gian đo. Không lấy tổng compile count tích lũy làm bằng chứng plan reuse kém nếu chưa chia cho số lần execute và cửa sổ thời gian.

## 13. Quy trình điều tra truy vấn chậm

Khi một truy vấn chậm, đi theo các bước để xác định đúng loại công việc:

1. **Xác định query shape:** câu SQL, tham số, kiểu dữ liệu bind, tần suất và nhóm người dùng/tenant.
2. **Kiểm tra plan reuse:** parse/compile/recompile có thường xuyên không? Có nhiều plan gần giống do literal hoặc session settings không?
3. **Đọc execution plan:** plan hiện tại có access path, join order và cardinality phù hợp không? Có parameter sensitivity không?
4. **Kiểm tra data cache:** logical reads, physical reads, buffer hits, storage latency và working set.
5. **Kiểm tra result cache:** có result-cache hit không? Key có đủ tham số và context? Entry có bị invalidation liên tục không?
6. **Phân tích CPU và waits:** thời gian bị tiêu tốn ở compile, CPU execution, lock, I/O, memory spill hay network?
7. **Nêu giả thuyết cụ thể:** ví dụ ad hoc plan bloat, plan không phù hợp với giá trị phổ biến, scan quá rộng hoặc result cache không thể tái sử dụng.
8. **Thay đổi một yếu tố:** parameterize, cập nhật thống kê, sửa index/SQL hoặc điều chỉnh cache policy theo bằng chứng.
9. **Đo lại:** cùng dữ liệu, tham số, mức tải, trạng thái cache và thời lượng.
10. **Kiểm tra tác động phụ:** compile CPU, plan stability, RAM, I/O, invalidation, freshness và workload khác.

## 14. Thiết kế benchmark để tách plan cache và data cache

Một phép thử hữu ích nên tách riêng tác động compile và I/O. Có thể xây dựng ma trận:

| Kịch bản | Plan cache | Data cache | Mục tiêu |
|---|---|---|---|
| A | Warm | Warm | Baseline truy vấn lặp lại thông thường |
| B | Warm | Cold/ít nóng | Quan sát chi phí đọc page khi plan đã có |
| C | Cold/recompile | Warm | Ước lượng chi phí parse/optimize khi data pages còn nóng |
| D | Cold/recompile | Cold/ít nóng | Trường hợp khởi động/lạnh, cần kiểm soát cẩn thận |

Không phải mọi DBMS cho phép điều khiển từng cache độc lập. Cold data cache khó tạo chính xác vì OS page cache và storage cache có thể vẫn nóng. Xóa plan cache diện rộng cũng có thể ảnh hưởng các session khác. Thực hiện trên môi trường kiểm thử hoặc dùng cơ chế cô lập phù hợp, ghi rõ giới hạn và không làm sạch cache production chỉ để benchmark.

### 14.1. Trình tự đo đề xuất

- Chạy truy vấn với cùng tham số và thu thập actual plan.
- Ghi compile/parse time riêng nếu công cụ hỗ trợ.
- Ghi execution time, logical reads, physical reads, CPU và waits.
- Lặp lại cùng statement để quan sát plan reuse và data cache warming.
- Thử nhiều nhóm tham số để phát hiện skew.
- So sánh với query result cache tắt/bật chỉ khi DBMS hỗ trợ và kết quả vẫn có semantics giống nhau.
- Lặp lại nhiều lần, báo cáo median và percentiles, không chỉ một lần chạy.

### 14.2. Không nhầm benchmark plan reuse với benchmark result cache

Nếu result cache được bật, lần chạy thứ hai có thể bỏ qua toàn bộ execution plan hoặc phần lớn công việc. Kết quả đó không chứng minh plan cache hiệu quả. Khi muốn đo plan reuse, cần bảo đảm result cache không che khuất phần thực thi; khi muốn đo result cache, cần đo riêng hit/miss và chi phí invalidation.

## 15. Ví dụ thực hành: phân biệt ba nguyên nhân của truy vấn nhanh/chậm

Giả sử API gọi câu lệnh:

```sql
SELECT customer_id, SUM(total_amount) AS total_spent
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at < :to_time
GROUP BY customer_id;
```

Ba tình huống có thể xảy ra:

**Tình huống A — Plan cache miss:** mỗi request sinh SQL khác nhau bằng cách nối literal. Compile CPU cao, nhưng logical/physical reads và thời gian execution của từng lần không quá lớn. Hướng xử lý là parameterize đúng kiểu và xác nhận plan reuse; đồng thời kiểm tra parameter skew.

**Tình huống B — Data cache miss hoặc đọc quá nhiều page:** plan được dùng lại, nhưng truy vấn đọc nhiều page và storage latency cao. Hướng xử lý là xem index, partition pruning, predicate, working set và storage; tăng plan cache không giải quyết vấn đề.

**Tình huống C — Result cache miss/invalidation:** DBMS hoặc ứng dụng có result cache, nhưng entry thường xuyên bị invalidation vì bảng `orders` thay đổi liên tục. Hướng xử lý là đánh giá tính phù hợp của result cache, phạm vi dữ liệu có thể cache, TTL/freshness và chi phí refresh. Nếu dữ liệu thay đổi quá thường xuyên, cache kết quả có thể không đem lại lợi ích.

Trong cả ba tình huống, phải đo p95/p99, throughput, CPU, I/O, số lần compile, logical reads và cache hit/miss theo đúng tầng trước khi chọn giải pháp.

## 16. Những sai lầm thường gặp

- **Gọi mọi thứ là query cache:** không phân biệt plan, data và result cache.
- **Plan cache hit đồng nghĩa query nhanh:** plan vẫn phải thực thi và có thể đọc nhiều page hoặc chờ khóa.
- **Data cache hit đồng nghĩa đã cache kết quả:** DBMS vẫn phải chạy predicate, join, aggregate và tạo output.
- **Result cache hit giống buffer pool hit:** result cache có thể bỏ qua phần lớn truy vấn, còn buffer pool chỉ cung cấp page.
- **Parameterization luôn tạo plan tối ưu:** một plan chung có thể không phù hợp với dữ liệu lệch.
- **Mọi DBMS có shared plan cache giống nhau:** PostgreSQL, MySQL, SQL Server và Oracle có cơ chế khác nhau.
- **Query Store là plan cache:** Query Store/history phục vụ lưu lịch sử và phân tích, không phải vùng plan reuse trực tiếp.
- **Xóa toàn bộ cache để sửa một truy vấn:** có thể gây compile storm và I/O spike cho toàn hệ thống.
- **Cache kết quả mà không tính quyền và tenant:** có thể trả dữ liệu sai ngữ cảnh hoặc rò rỉ dữ liệu.
- **Dùng TTL mà không định nghĩa freshness:** dữ liệu cũ có thể vượt giới hạn nghiệp vụ.
- **Chỉ xem hit ratio tổng thể:** che giấu truy vấn nóng, cache bloat hoặc nhóm tham số có plan xấu.
- **Benchmark result cache khi muốn đo plan reuse:** kết quả cache che khuất chi phí thực thi.

## 17. Bài tập tự kiểm tra

### Bài tập 1: Plan hit nhưng truy vấn vẫn chậm

Một câu SQL chạy hàng nghìn lần và luôn dùng cùng execution plan. Plan cache hit cao, nhưng truy vấn đọc hàng triệu logical pages và CPU cao.

**Câu hỏi:** nên điều tra cache nào và những gì?

**Gợi ý trả lời:** plan cache đã tái sử dụng, nên compile không phải nguyên nhân chính. Kiểm tra data access: index, predicate, cardinality, số page đọc, join/aggregate và CPU. Data cache hit cao vẫn có thể đi kèm lượng logical reads rất lớn.

### Bài tập 2: Literal SQL tạo nhiều plan

Ứng dụng tạo một chuỗi SQL mới cho mỗi `customer_id`. Số plan trong cache tăng nhanh và compile CPU cao.

**Câu hỏi:** thay đổi nào đáng thử và rủi ro nào cần kiểm tra?

**Gợi ý trả lời:** parameterize câu SQL và bind đúng kiểu dữ liệu để tăng plan reuse. Kiểm tra phân bố customer_id có lệch không; nếu một plan chung không phù hợp mọi giá trị, cần đánh giá custom/generic plan hoặc tính năng parameter-sensitive của DBMS.

### Bài tập 3: Result cache trả dữ liệu cũ

Ứng dụng cache kết quả số dư tài khoản trong 5 phút. Một giao dịch cập nhật số dư vừa commit nhưng người dùng vẫn nhận số dư cũ.

**Câu hỏi:** vấn đề nằm ở đâu và cần xác định điều gì?

**Gợi ý trả lời:** cache ứng dụng chưa invalidation hoặc TTL không đáp ứng freshness của nghiệp vụ. Cần định nghĩa mức nhất quán, xóa key sau commit hoặc dùng cơ chế event/version phù hợp; key phải tách tài khoản và security context. Với số dư, stale result có thể không được chấp nhận.

### Bài tập 4: PostgreSQL prepared statement

Một prepared statement có `custom_plans` tăng trong giai đoạn đầu rồi `generic_plans` bắt đầu tăng. Nhóm kết luận PostgreSQL đã có shared plan cache toàn instance.

**Câu hỏi:** kết luận này đúng không?

**Gợi ý trả lời:** không. Prepared statement và kế hoạch của nó thuộc phạm vi session; PostgreSQL không có shared plan cache toàn cục cho mọi câu SQL theo mô hình SQL Server. Cần xem `pg_prepared_statements`, `plan_cache_mode` và phiên bản đang dùng.

### Bài tập 5: Flush plan cache làm hệ thống chậm

Sau khi xóa plan cache toàn instance, CPU tăng mạnh và latency của nhiều query tăng trong vài phút.

**Câu hỏi:** vì sao?

**Gợi ý trả lời:** nhiều query mất plan đã biên dịch và phải compile lại đồng thời, gây compile storm. Xóa plan cache không làm data cache nóng hơn và không phải biện pháp mặc định cho một query chậm. Cần xử lý plan cụ thể và phạm vi nhỏ nhất phù hợp.

### Checklist phân biệt và điều tra các loại cache

- [ ] Đã xác định cache đang nói đến là plan, data/page hay result cache.
- [ ] Đã biết nội dung được giữ và công việc được tránh ở mỗi tầng.
- [ ] Đã phân biệt plan reuse với data page hit.
- [ ] Đã phân biệt result cache với materialized view và cache ứng dụng.
- [ ] Đã kiểm tra query shape, parameterization, kiểu bind và session settings.
- [ ] Đã xem compile/recompile, số lần thực thi và plan cache memory.
- [ ] Đã kiểm tra parameter sniffing, data skew và estimated/actual rows.
- [ ] Đã đo logical/physical reads, buffer hit và storage latency.
- [ ] Nếu dùng result cache, đã xác định key, dependency, invalidation, TTL và freshness.
- [ ] Đã kiểm tra tenant, quyền, timezone, locale và transaction context.
- [ ] Đã phân biệt plan cache với công cụ lưu lịch sử như Query Store.
- [ ] Đã đo từng cache độc lập trong benchmark có điều kiện kiểm soát.
- [ ] Không flush cache diện rộng khi chưa đánh giá tác động.
- [ ] Đã so sánh latency, throughput, CPU, I/O, memory và tính đúng đắn trước/sau.

Plan cache, data/page cache và query result cache không thể thay thế lẫn nhau. Plan cache giảm công việc parse/optimize; data cache giảm việc đọc page từ tầng lưu trữ; result cache có thể tránh tính lại kết quả khi entry còn hợp lệ. Muốn tối ưu đúng, hãy xác định thời gian đang tiêu tốn ở giai đoạn nào, hiểu cách DBMS cụ thể quản lý cache, kiểm tra invalidation và tham số, rồi đo lại từng tầng trên workload đại diện. Chỉ số hit đơn lẻ không đủ để kết luận hiệu năng tốt; cần kết hợp execution plan, compile time, logical/physical reads, latency, throughput, CPU, I/O và tính nhất quán dữ liệu.
