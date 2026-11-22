# CLUSTER, thứ tự vật lý và chi phí viết lại bảng trong PostgreSQL

Trong PostgreSQL, một bảng thông thường được lưu dưới dạng **heap**: các row nằm trên những page của relation, còn index là cấu trúc riêng trỏ tới vị trí của row. Khi ứng dụng thêm dữ liệu, cập nhật nhiều cột hoặc xóa rows, thứ tự vật lý trong heap có thể ngày càng khác thứ tự logic mà ứng dụng thường truy vấn.

Ví dụ, một bảng sự kiện có index theo thời gian. Ứng dụng thường đọc dữ liệu theo khoảng:

```sql
SELECT event_id, occurred_at, payload
FROM app.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-10-02 00:00:00+00'
ORDER BY occurred_at;
```

Index giúp tìm các key phù hợp, nhưng các row tương ứng có thể nằm rải rác ở nhiều heap pages. Điều đó làm tăng số lần đọc page ngẫu nhiên khi truy vấn cần lấy nhiều cột từ heap.

PostgreSQL cung cấp lệnh **CLUSTER** để viết lại một bảng theo thứ tự của một index. Sau thao tác, các row được sắp xếp vật lý theo index đã chọn, nhờ vậy những truy vấn đọc các key gần nhau có cơ hội đọc các heap pages gần nhau hơn.

Điểm cần nhớ: **CLUSTER là thao tác viết lại bảng một lần, không phải cơ chế duy trì thứ tự vật lý cho mọi INSERT/UPDATE về sau.** Nó có chi phí I/O, WAL, dung lượng đĩa, rebuild indexes và khóa bảng trong thời gian thực hiện.

Bài học tập trung vào heap/index, MVCC, CLUSTER, physical correlation, chi phí rewrite, VACUUM FULL, REINDEX, pg_repack, giám sát tiến trình và cách quyết định khi nào nên hoặc không nên cluster.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cách PostgreSQL lưu table heap, heap pages, tuple versions và index entries.
2. Phân biệt thứ tự logic của ORDER BY với vị trí vật lý của row trong heap.
3. Giải thích CTID và vì sao không được dùng CTID như business identifier bền vững.
4. Mô tả MVCC, UPDATE tạo tuple version mới và tác động của nó tới physical locality.
5. Dùng CLUSTER table USING index để sắp xếp lại bảng theo index.
6. Dùng ALTER TABLE ... CLUSTER ON index để ghi nhớ index sẽ dùng cho lần cluster sau.
7. Hiểu vì sao CLUSTER cần khóa mạnh và có thể làm các truy vấn khác chờ.
8. Ước lượng disk space, I/O, WAL, replica lag và thời gian bảo trì khi rewrite.
9. Phân biệt CLUSTER, VACUUM, VACUUM FULL, REINDEX và pg_repack.
10. Đọc pg_stats.correlation để quan sát mối tương quan giữa thứ tự cột và thứ tự vật lý.
11. Đo truy vấn trước/sau bằng EXPLAIN (ANALYZE, BUFFERS).
12. Quan sát pg_stat_progress_cluster, pg_locks, pg_stat_activity và kích thước relation.
13. Chọn bảng và index phù hợp dựa trên query workload, không chỉ dựa vào cảm giác.
14. Hiểu tác động của fillfactor, HOT updates, partitioning, BRIN và các lần ghi mới.
15. Lập kế hoạch chạy CLUSTER trong môi trường production có kiểm soát.

## 2. Heap và index: hai cấu trúc lưu trữ riêng

Một bảng PostgreSQL thông thường được tổ chức thành các heap pages. Index không phải là “bảng đã được sắp xếp” chứa toàn bộ row; nó lưu key và thông tin định vị tuple trong heap.

```text
TABLE HEAP
  Page 0: row 81 | row 12 | row 44
  Page 1: row  7 | row 90 | row 25
  Page 2: row 31 | row  3 | row 72

BTREE INDEX trên event_time
  t1 -> (Page 2, offset 3)
  t2 -> (Page 1, offset 7)
  t3 -> (Page 0, offset 12)
  t4 -> (Page 2, offset 31)
```

Index cho phép PostgreSQL tìm nhanh key và địa chỉ tuple, nhưng thứ tự key trong index không đồng nghĩa các tuple nằm liên tiếp trong heap.

### 2.1. Heap page và tuple

Một page có kích thước theo cấu hình build PostgreSQL, phổ biến là 8 KB. Page chứa header, line pointers và tuple data. Một row có thể chiếm nhiều bytes, thậm chí phần dữ liệu lớn được lưu trong TOAST relation.

Không nên giả định:

- Mỗi row luôn nằm trọn trong một page theo một vị trí cố định.
- Thứ tự SELECT không có ORDER BY là thứ tự vật lý.
- Row được INSERT sau luôn nằm ở cuối bảng.
- Một UPDATE chỉ sửa bytes tại chỗ.

### 2.2. Index entry trỏ tới tuple trong heap

Với B-tree index thông thường, key được sắp xếp theo operator class/collation và chứa TID để xác định tuple trong heap. TID thường biểu diễn bằng cặp block number và offset number.

### 2.3. CTID

PostgreSQL cung cấp system column ctid:

```sql
SELECT ctid, event_id, occurred_at
FROM app.events
LIMIT 10;
```

ctid cho biết vị trí vật lý hiện tại của một tuple version trong relation. Nó hữu ích cho chẩn đoán và một số thao tác nội bộ có kiểm soát, nhưng:

- UPDATE có thể tạo tuple version mới với CTID khác.
- CLUSTER viết lại bảng, nên CTID có thể thay đổi hàng loạt.
- VACUUM FULL và các thao tác rewrite khác cũng có thể thay đổi vị trí.
- Không dùng CTID làm primary key, foreign key hoặc ID nghiệp vụ.

## 3. Thứ tự vật lý không phải thứ tự kết quả SQL

Một bảng được cluster theo index events_occurred_at_idx vẫn phải truy vấn:

```sql
SELECT *
FROM app.events
ORDER BY occurred_at;
```

nếu ứng dụng yêu cầu kết quả có thứ tự.

### 3.1. Vì sao?

SQL chỉ bảo đảm thứ tự kết quả khi có ORDER BY. PostgreSQL có thể:

- Dùng index scan.
- Dùng bitmap heap scan.
- Dùng sequential scan.
- Dùng parallel plan.
- Chọn một execution plan khác sau khi statistics hoặc dữ liệu thay đổi.

Không có ORDER BY, thứ tự kết quả có thể khác giữa hai lần chạy dù bảng chưa được sửa.

### 3.2. CLUSTER không thay đổi ngữ nghĩa SQL

CLUSTER thay đổi bố trí vật lý để có thể cải thiện locality. Nó không thêm một ràng buộc “mọi SELECT luôn trả theo index”.

### 3.3. Nếu cần phân trang ổn định

Dùng thứ tự xác định, ví dụ:

```sql
SELECT event_id, occurred_at
FROM app.events
ORDER BY occurred_at, event_id
LIMIT 100;
```

Nếu occurred_at không unique, thêm tie-breaker như event_id. CLUSTER theo một index có thể cải thiện locality nhưng không thay thế ORDER BY và logic pagination.

## 4. MVCC làm thứ tự vật lý thay đổi như thế nào?

PostgreSQL dùng Multi-Version Concurrency Control (MVCC). UPDATE thường tạo một tuple version mới thay vì ghi đè trực tiếp tuple cũ đang có thể được transaction khác nhìn thấy.

```text
Trước UPDATE:
  Heap page 10: tuple version A (visible)

UPDATE row:
  Heap page 10: tuple version A (old/dead khi không còn snapshot cần)
  Heap page 27: tuple version B (new)

Sau VACUUM:
  vùng của tuple cũ có thể được tái sử dụng
```

### 4.1. UPDATE có thể làm row rời khỏi vùng cũ

Nếu page cũ không còn đủ chỗ hoặc UPDATE thay đổi cột được index, PostgreSQL có thể phải đặt tuple version mới ở page khác và cập nhật indexes.

### 4.2. HOT update

Heap-Only Tuple (HOT) update có thể tránh cập nhật index khi các điều kiện phù hợp, đặc biệt khi cột được sửa không được index tham chiếu và có đủ chỗ trên cùng page. HOT giúp giảm index churn nhưng không phải bảo đảm mọi UPDATE giữ nguyên vị trí logic/physical.

### 4.3. DELETE và dead tuples

DELETE đánh dấu tuple không còn visible với các snapshots mới; không nhất thiết lập tức trả bytes cho hệ điều hành. VACUUM có thể làm không gian đó tái sử dụng trong relation.

### 4.4. Vì sao CLUSTER có thể hữu ích?

CLUSTER viết lại heap từ những rows còn sống theo thứ tự index. Nó có thể:

- Gom các rows gần nhau theo key vào các heap pages gần nhau.
- Loại bỏ dead tuple versions khỏi bản rewrite.
- Giảm phân mảnh vật lý của heap.
- Làm mới bố trí các index khi chúng được rebuild.

Những lợi ích này cần được cân bằng với chi phí rewrite.

## 5. CLUSTER làm gì?

Cú pháp cơ bản:

```sql
CLUSTER [VERBOSE] table_name [USING index_name];
```

Ví dụ:

```sql
CLUSTER VERBOSE app.events
USING events_occurred_at_idx;
```

PostgreSQL tạo một bố trí vật lý mới của table theo thứ tự của index được chỉ định. Các indexes trên table cũng được rebuild để trỏ tới vị trí tuple mới.

### 5.1. Đây là thao tác rewrite

CLUSTER không chỉ “đảo vài page”. Nó tạo lại nội dung relation theo thứ tự index và chuyển sang relation storage mới theo quy trình nội bộ.

### 5.2. CLUSTER không phải clustered index được duy trì liên tục

Trong một số hệ quản trị khác, khái niệm clustered index có thể gắn với cách bảng được tổ chức lâu dài. Trong PostgreSQL, CLUSTER là thao tác sắp xếp lại tại thời điểm chạy.

INSERT/UPDATE sau đó vẫn tuân theo cơ chế heap storage thông thường. Physical order có thể dần mất correlation.

### 5.3. Index phải hỗ trợ CLUSTER

Không phải mọi loại index đều dùng được làm cơ sở cho CLUSTER. Hãy chọn index access method được phiên bản PostgreSQL hỗ trợ cho thao tác này; B-tree là lựa chọn phổ biến nhất cho thứ tự key. Kiểm tra tài liệu của đúng phiên bản khi dùng access method khác.

### 5.4. Một index có thể có nhiều rows trùng key

Nếu index key không unique, các rows cùng key có thể có thứ tự vật lý tương đối không mang ý nghĩa nghiệp vụ ổn định. Nếu cần thứ tự phụ trong truy vấn, thiết kế index nhiều cột và ORDER BY có tie-breaker rõ ràng.

## 6. Cú pháp CLUSTER thường dùng

### 6.1. Cluster một table theo index

```sql
CLUSTER app.events USING events_occurred_at_idx;
```

### 6.2. Cluster theo index đã được đánh dấu trước

```sql
ALTER TABLE app.events
CLUSTER ON events_occurred_at_idx;

CLUSTER app.events;
```

ALTER TABLE ... CLUSTER ON ghi nhớ index dùng cho những lần cluster tiếp theo. Bản thân câu ALTER này không viết lại table.

### 6.3. Xem index được đánh dấu

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisclustered
FROM pg_index AS i
WHERE i.indrelid = 'app.events'::regclass;
```

indisclustered=true cho biết index được đánh dấu là index clustering của table.

### 6.4. Cluster tất cả table đã được đánh dấu

```sql
CLUSTER VERBOSE;
```

Không chạy câu này theo thói quen trên production. Nó có thể thực hiện rewrite nhiều tables đã được đánh dấu trong database hiện tại, gây tổng chi phí và thời gian khóa lớn.

### 6.5. Cluster table theo index được nhớ

```sql
CLUSTER VERBOSE app.events;
```

Nếu table chưa có index clustering được đánh dấu, lệnh không có index rõ ràng có thể không thực hiện như ý định. Hãy kiểm tra pg_index.indisclustered trước.

## 7. Ví dụ: tạo table và index theo thời gian

Ta tạo schema lab:

```sql
CREATE SCHEMA IF NOT EXISTS storage_lab;

CREATE TABLE storage_lab.events (
    event_id bigint PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    customer_id bigint NOT NULL,
    payload text NOT NULL
);
```

Nạp 100.000 rows theo thứ tự chèn cố ý không tương quan với occurred_at:

```sql
INSERT INTO storage_lab.events (
    event_id,
    occurred_at,
    customer_id,
    payload
)
SELECT
    g,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (g % 10000) + 1,
    repeat('x', 100)
FROM generate_series(1, 100000) AS g
ORDER BY md5(g::text);
```

ORDER BY md5(g::text) làm thứ tự insert khác với thứ tự thời gian tăng dần để minh họa physical correlation thấp.

### 7.1. Tạo index

```sql
CREATE INDEX events_occurred_at_idx
ON storage_lab.events (occurred_at);

ANALYZE storage_lab.events;
```

### 7.2. Xem correlation ban đầu

```sql
SELECT
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'storage_lab'
  AND tablename = 'events'
  AND attname IN ('event_id', 'occurred_at');
```

correlation mô tả mối tương quan giữa thứ tự giá trị cột và thứ tự vật lý của rows. Giá trị gần +1 hoặc -1 cho thấy tương quan mạnh theo chiều tăng/giảm; gần 0 cho thấy ít tương quan tuyến tính.

### 7.3. Đo truy vấn range trước CLUSTER

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00'
ORDER BY occurred_at;
```

Chọn khoảng 10 phút để lấy một tập rows đủ nhỏ so với toàn bảng. Ghi lại execution time, loại scan, heap blocks read/hit, rows actual và buffers.

### 7.4. Cluster theo index thời gian

```sql
CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;

ANALYZE storage_lab.events;
```

### 7.5. Đo lại

Chạy lại cùng query EXPLAIN (ANALYZE, BUFFERS) và truy vấn pg_stats.correlation.

Với dữ liệu lab có thứ tự insert ngẫu nhiên, correlation của occurred_at thường tăng về gần +1 sau CLUSTER. Số buffers đọc cho range scan có thể giảm, nhưng kết quả cụ thể phụ thuộc cache, planner, thiết bị lưu trữ và execution plan.

**Không kỳ vọng mọi lần đo đều nhanh hơn**: nếu dữ liệu đã nằm trong cache, hoặc planner chọn sequential scan, chênh lệch có thể nhỏ.

## 8. Vì sao physical locality có thể cải thiện range scan?

Giả sử query tìm 5.000 rows liên tiếp theo occurred_at.

Trước CLUSTER, những keys liên tiếp trong B-tree có thể trỏ tới heap pages phân tán:

```text
B-tree key order:
  t1 -> heap page 8
  t2 -> heap page 91
  t3 -> heap page 12
  t4 -> heap page 75
  t5 -> heap page 4

Heap access:
  8 -> 91 -> 12 -> 75 -> 4
```

Sau CLUSTER, các rows có key gần nhau có cơ hội được đặt gần nhau:

```text
B-tree key order:
  t1 -> heap page 40
  t2 -> heap page 40
  t3 -> heap page 41
  t4 -> heap page 41
  t5 -> heap page 42

Heap access:
  40 -> 41 -> 42
```

Số heap pages cần đọc có thể giảm, đặc biệt khi truy vấn lấy nhiều columns không có sẵn trong index.

### 8.1. Index scan và heap fetch

Nếu query chỉ lấy các cột có trong index và có visibility map phù hợp, PostgreSQL có thể dùng index-only scan, giảm nhu cầu đọc heap. Khi đó CLUSTER có thể mang lại ít lợi ích hơn cho query ấy.

### 8.2. Bitmap heap scan

Bitmap scan gom các TIDs rồi truy cập heap pages theo thứ tự page để giảm I/O ngẫu nhiên. Physical locality vẫn có thể hữu ích, nhưng lợi ích phụ thuộc số rows và pages được truy cập.

### 8.3. Sequential scan

Nếu query đọc phần lớn table, sequential scan có thể vốn đã hiệu quả. Sắp xếp lại heap không tự làm một sequential scan nhanh hơn đáng kể.

### 8.4. Cache có thể che chi phí I/O

Một lần benchmark ngay sau CLUSTER có thể đọc phần lớn dữ liệu từ shared buffers hoặc OS cache. Hãy so nhiều lần, ghi nhận cache state và không dùng một lần đo đơn lẻ làm quyết định production.

## 9. Physical correlation và pg_stats

PostgreSQL lưu statistics trong pg_statistic, cung cấp view dễ đọc pg_stats.

```sql
SELECT
    schemaname,
    tablename,
    attname,
    correlation,
    null_frac,
    n_distinct
FROM pg_stats
WHERE schemaname = 'storage_lab'
  AND tablename = 'events'
ORDER BY attname;
```

### 9.1. Ý nghĩa correlation

correlation thường nằm trong khoảng -1 đến +1:

- Gần +1: giá trị cột tăng cùng chiều với vị trí vật lý.
- Gần -1: giá trị cột giảm khi vị trí vật lý tăng.
- Gần 0: không có tương quan tuyến tính rõ.

### 9.2. Correlation là statistics, không phải ràng buộc

Nó là ước lượng dựa trên sample/statistics của planner, không phải cam kết mọi tuple đã được xếp tuyệt đối theo cột.

### 9.3. Cần ANALYZE sau rewrite

Sau CLUSTER, chạy:

```sql
ANALYZE storage_lab.events;
```

để cập nhật statistics. Đừng đọc pg_stats.correlation cũ và kết luận CLUSTER không có tác dụng nếu statistics chưa được làm mới.

### 9.4. Correlation cao không chứng minh query sẽ nhanh

Query có thể không dùng index ấy; bảng có thể nhỏ; cache có thể làm I/O khác; chi phí CPU hoặc join khác mới là bottleneck. Dùng EXPLAIN và workload thực.

## 10. CLUSTER theo index nào?

Index clustering nên được chọn theo các truy vấn thường xuyên cần locality.

Ví dụ:

```sql
CREATE INDEX events_customer_time_idx
ON storage_lab.events (customer_id, occurred_at);
```

Nếu thường truy vấn:

```sql
SELECT *
FROM storage_lab.events
WHERE customer_id = 123
ORDER BY occurred_at;
```

thì thứ tự vật lý theo (customer_id, occurred_at) có thể cải thiện locality cho nhóm rows của cùng customer và thứ tự thời gian bên trong nhóm.

### 10.1. Multi-column index có thứ tự từ trái sang phải

Index (customer_id, occurred_at) có thứ tự từ điển theo key đầu tiên rồi key thứ hai. Nó không đồng nghĩa toàn bộ table được sắp theo occurred_at toàn cục.

### 10.2. Một table chỉ có một thứ tự vật lý tại một thời điểm

Bạn không thể cluster cùng một heap đồng thời theo occurred_at, customer_id và status. Chọn một thứ tự chính; các workload khác vẫn dựa vào index, partitioning hoặc thiết kế vật lý khác.

### 10.3. Không nhất thiết cluster theo primary key

Primary key thường có index, nhưng query workload có thể chủ yếu đọc theo thời gian hoặc tenant. Chọn theo access pattern thực tế, không theo tên index mặc định.

### 10.4. Index key và NULL ordering

Thứ tự index có thể bao gồm ASC/DESC, NULLS FIRST/LAST, collation và operator class. CLUSTER theo index sẽ theo ordering của index; nếu dữ liệu có NULL hoặc collation đặc biệt, cần hiểu thứ tự mong muốn.

## 11. CLUSTER không duy trì thứ tự sau INSERT/UPDATE

Sau khi cluster:

```sql
INSERT INTO storage_lab.events (
    event_id, occurred_at, customer_id, payload
)
VALUES (
    100001,
    TIMESTAMPTZ '2026-01-01 00:00:01+00',
    42,
    'late arrival'
);
```

Row mới không được PostgreSQL tự tìm đúng vị trí vật lý ở giữa heap chỉ vì table từng cluster theo occurred_at.

### 11.1. INSERT mới

PostgreSQL dùng cơ chế heap allocation bình thường để đặt tuple. Với dữ liệu đến theo thứ tự tăng dần, physical correlation có thể giữ tương đối tốt; với dữ liệu late-arriving/random, correlation có thể giảm.

### 11.2. UPDATE

UPDATE có thể tạo tuple version mới ở page khác. Nếu key dùng để cluster thay đổi, row mới càng có thể không còn ở vị trí mong muốn.

### 11.3. DELETE

DELETE để lại dead tuple cho đến khi vacuum xử lý; page layout có thể có khoảng trống và fragmentation.

### 11.4. CLUSTER định kỳ?

Không đặt lịch cluster mỗi đêm chỉ vì “table cần gọn”. Đo physical correlation, query latency và buffers, tần suất update/delete, table size và tốc độ tăng, lock window và disk/WAL budget.

Chỉ cluster lại khi lợi ích dự kiến lớn hơn chi phí và blocking chấp nhận được.

## 12. Chi phí chính của CLUSTER

CLUSTER có thể tạo ra một đợt tài nguyên đáng kể:

1. Đọc table và index cần thiết để xác định thứ tự.
2. Ghi lại heap relation.
3. Rebuild các indexes của table.
4. Tạo WAL và phát sinh I/O.
5. Có thể dùng memory/temp files tùy cách thực thi.
6. Chiếm khóa mạnh trong thời gian thao tác.
7. Tạo replication lag nếu replica phải replay lượng WAL lớn.

### 12.1. Disk space

Trong quá trình rewrite, bản cũ và bản mới có thể cùng tồn tại cho tới khi hoàn tất chuyển đổi và cleanup. Cần chuẩn bị dung lượng trống xấp xỉ quy mô table và indexes, cộng thêm headroom cho temporary files, WAL, archive và replication.

Không dùng một hệ số cố định cho mọi table: TOAST, fillfactor, index count, tablespaces và cách thực thi có thể làm footprint khác nhau.

### 12.2. WAL

Rewrite tạo lượng ghi đáng kể. Trong môi trường có physical streaming replication, WAL cần được truyền và replay. Nếu tốc độ tạo WAL vượt tốc độ replay, replica lag tăng.

### 12.3. I/O và CPU

CLUSTER vừa đọc dữ liệu cũ vừa ghi dữ liệu mới, đồng thời rebuild indexes. Sắp xếp và rebuild indexes có thể tiêu tốn CPU, đặc biệt với table lớn hoặc key phức tạp.

### 12.4. Thời gian

Thời gian phụ thuộc kích thước table, index, TOAST, storage throughput, cache, memory, concurrent workload và replica setup. Không ước lượng từ row count đơn thuần.

## 13. Khóa bảng và ảnh hưởng tới ứng dụng

CLUSTER lấy khóa ACCESS EXCLUSIVE trên table được xử lý. Đây là mức khóa mạnh, chặn các truy cập đồng thời cần lock xung đột, bao gồm SELECT thông thường.

### 13.1. Không phải chỉ chặn writers

Khác với nhiều thao tác maintenance nhẹ, CLUSTER có thể khiến cả readers và writers của table phải chờ trong thời gian giữ lock.

### 13.2. Lock queue có thể gây domino

Một CLUSTER đang chờ lấy ACCESS EXCLUSIVE có thể khiến các truy vấn mới bị xếp sau nó trong hàng đợi lock, dù chúng thường chỉ cần ACCESS SHARE. Vì vậy cần kiểm tra long-running transactions và chọn thời điểm phù hợp.

### 13.3. lock_timeout

Có thể giới hạn thời gian chờ lấy lock:

```sql
SET lock_timeout = '5s';
CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;
```

Nếu không lấy được lock trong giới hạn, thao tác thất bại thay vì chờ vô hạn. Nhưng sau khi đã lấy lock, lock_timeout không giới hạn tổng thời gian rewrite.

### 13.4. statement_timeout

statement_timeout có thể giới hạn thời gian thực thi tổng thể của statement. Nếu CLUSTER bị cancel, cần theo dõi trạng thái rollback/cleanup và dung lượng tài nguyên.

### 13.5. Long-running snapshots

CLUSTER là thao tác rewrite và có đặc tính **không MVCC-safe** trong một số tình huống: transaction đang giữ snapshot cũ từ trước thao tác có thể quan sát table như rỗng sau khi rewrite. Tránh chạy khi còn những transaction/snapshot dài cần tiếp tục truy cập table qua thời điểm CLUSTER; lập lịch maintenance và kiểm tra long-running transactions trước.

## 14. CLUSTER và transaction boundaries

CLUSTER là lệnh DDL/maintenance, không phải UPDATE từng row. Hãy kiểm tra quy tắc của phiên bản PostgreSQL và công cụ migration đang dùng khi lên lịch và thực thi.

### 14.1. Không gói CLUSTER vào migration transaction dài tùy tiện

Một migration framework có thể tự bọc mọi bước trong transaction. Nếu command hoặc cách vận hành không tương thích transaction block, pipeline sẽ thất bại. Ngay cả khi thực thi được, giữ các DDL/locks khác trong cùng transaction có thể kéo dài lock lifetime.

### 14.2. Chạy riêng trong maintenance job

Thông thường dễ kiểm soát hơn khi chạy CLUSTER như một maintenance operation riêng: ghi lại start time; xác nhận table/index đúng; kiểm tra blockers và disk headroom; đặt timeout phù hợp; quan sát progress; ANALYZE sau khi hoàn thành.

### 14.3. Không chạy song song nhiều CLUSTER lớn tùy tiện

Các rewrite cùng tranh I/O, WAL, disk và locks. Chạy tuần tự hoặc giới hạn concurrency theo budget thực tế.

## 15. So sánh CLUSTER với VACUUM

VACUUM thông thường xử lý dead tuples và làm không gian có thể tái sử dụng trong relation; nó không sắp xếp lại toàn bộ heap theo một index.

```sql
VACUUM (VERBOSE, ANALYZE) storage_lab.events;
```

### 15.1. VACUUM thường

- Đánh dấu không gian dead tuple có thể tái sử dụng.
- Cập nhật visibility map và free space map.
- Giúp tránh table/index bloat tăng không kiểm soát.
- Thường không cần ACCESS EXCLUSIVE lock.
- Không rewrite toàn bộ table theo index order.

### 15.2. VACUUM ANALYZE

Kết hợp cleanup và cập nhật planner statistics. Nó không tương đương CLUSTER.

### 15.3. Vì sao VACUUM không tạo physical order?

VACUUM tập trung vào tuple visibility và reclaim/reuse space. Nó không đọc một index rồi xây heap mới theo thứ tự index như CLUSTER.

## 16. So sánh CLUSTER với VACUUM FULL

VACUUM FULL rewrite table để thu hồi không gian, thường lấy ACCESS EXCLUSIVE lock. Nhưng mục tiêu chính là compact/reclaim storage, không phải sắp xếp theo index.

```sql
VACUUM (FULL, VERBOSE, ANALYZE) storage_lab.events;
```

| Thuộc tính | CLUSTER | VACUUM FULL |
| --- | --- | --- |
| Rewrite heap | Có | Có |
| Mục tiêu chính | Reorder theo index | Compact/reclaim space |
| Chọn index để sắp xếp | Có | Không |
| Rebuild indexes | Có | Có liên quan tới rewrite |
| ACCESS EXCLUSIVE | Có | Có |
| Duy trì thứ tự sau đó | Không | Không |
| Phù hợp khi | Locality theo key là mục tiêu | Bloat/space reclamation là mục tiêu |

### 16.1. Không dùng CLUSTER chỉ để giảm file size

Nếu vấn đề chỉ là table bloat/space reclamation, đánh giá VACUUM FULL hoặc công cụ rewrite online phù hợp hơn. CLUSTER có thể compact trong quá trình rewrite nhưng nó thêm mục tiêu ordering và có cùng chi phí lớn.

### 16.2. Không dùng VACUUM FULL để mong range scan được sắp xếp

VACUUM FULL không nhận index làm thứ tự sắp xếp heap.

## 17. So sánh CLUSTER với REINDEX

REINDEX xây dựng lại index. Nó không viết lại heap theo thứ tự key.

```sql
REINDEX INDEX storage_lab.events_occurred_at_idx;
```

Hoặc:

```sql
REINDEX TABLE storage_lab.events;
```

### 17.1. Khi nào cần REINDEX?

- Index bị bloat hoặc corruption được xác định.
- Cần rebuild index sau thay đổi cụ thể.
- Có vấn đề với index storage/structure.
- Một maintenance policy yêu cầu rebuild theo đánh giá.

### 17.2. REINDEX không cải thiện heap correlation

Nếu heap rows nằm rải rác, xây B-tree mới chỉ tạo lại index entries trỏ tới các vị trí đó. Nó không gom rows trong heap.

### 17.3. REINDEX CONCURRENTLY

PostgreSQL hỗ trợ REINDEX ... CONCURRENTLY cho các trường hợp phù hợp, giảm mức blocking so với cách thông thường nhưng có chi phí, hạn chế và thời gian thực thi riêng. Nó vẫn không tương đương CLUSTER và không reorder heap.

## 18. So sánh với pg_repack

pg_repack là extension/tool bên ngoài PostgreSQL core, thường được dùng để reorganize/compact table với thời gian giữ lock độc quyền ngắn hơn so với rewrite trực tiếp kiểu CLUSTER/VACUUM FULL.

### 18.1. Cách tiếp cận khái quát

Tool có thể tạo bản sao/cấu trúc thay thế, theo dõi các thay đổi phát sinh trong lúc copy, đồng bộ phần thay đổi và lấy lock ngắn để swap relation/indexes. Chi tiết phụ thuộc phiên bản extension và cách chạy.

### 18.2. Không phải zero-lock

pg_repack vẫn cần quyền, cấu trúc hỗ trợ, dung lượng trống và những thời điểm lấy lock. Có thể thất bại nếu môi trường không đáp ứng prerequisites hoặc có transaction/blocker kéo dài.

### 18.3. Không phải công cụ core

Phải cài extension đúng phiên bản tương thích PostgreSQL, xem quyền cần thiết, replication/DDL policy, backup và vận hành.

### 18.4. Khi nào cân nhắc?

Khi cần giảm bloat/reorder table lớn mà downtime của ACCESS EXCLUSIVE lock dài không chấp nhận được, có thể đánh giá pg_repack trong staging và production plan.

## 19. Bảng so sánh các thao tác bảo trì

| Thao tác | Viết lại heap | Rebuild index | Sắp heap theo index | Mức blocking điển hình |
| --- | --- | --- | --- | --- |
| VACUUM | Không rewrite toàn bộ | Không | Không | Thấp hơn, không ACCESS EXCLUSIVE thông thường |
| VACUUM FULL | Có | Có | Không | ACCESS EXCLUSIVE |
| CLUSTER | Có | Có | Có, theo index | ACCESS EXCLUSIVE |
| REINDEX | Không | Có | Không | Tùy biến thể; CONCURRENTLY giảm blocking |
| pg_repack | Tạo/swap bản thay thế | Có thể | Có thể theo index | Thiết kế để giảm thời gian lock cuối, vẫn có lock |

Không dùng bảng này như cam kết lock chi tiết cho mọi phiên bản/loại relation; kiểm tra tài liệu và thử nghiệm cụ thể.

## 20. Fillfactor và không gian cho UPDATE sau CLUSTER

Sau CLUSTER, table có thể rất compact. Nhưng nếu workload tiếp tục UPDATE, không gian trống trong page có thể giúp HOT updates và giảm page splits/chuyển tuple.

Ví dụ:

```sql
ALTER TABLE storage_lab.events
SET (fillfactor = 80);
```

Sau đó chạy CLUSTER trong maintenance window nếu muốn rewrite lại theo setting và ordering.

### 20.1. Fillfactor là gì?

Fillfactor điều khiển mức độ lấp đầy page khi table được tạo/rewrite hoặc khi PostgreSQL phân bổ tuple theo quy tắc tương ứng. Giá trị thấp hơn để lại nhiều chỗ trống hơn cho updates.

### 20.2. Trade-off

- Fillfactor thấp hơn: có thể giúp UPDATE/HOT locality, nhưng table lớn hơn và cache footprint cao hơn.
- Fillfactor cao hơn: tiết kiệm page cho dữ liệu ít update, nhưng ít chỗ trống để tuple version mới ở lại cùng page.

### 20.3. Không giảm fillfactor chỉ vì nghe nói HOT

Đo tỷ lệ UPDATE, HOT updates, page utilization và query performance trước khi chọn.

### 20.4. Kiểm tra setting

```sql
SELECT
    c.relname,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'storage_lab.events'::regclass;
```

## 21. CLUSTER và TOAST

Các giá trị lớn như JSON/text có thể được lưu ngoài heap page chính qua TOAST.

### 21.1. Heap tuple có thể giữ TOAST pointer

Row trong heap vẫn có metadata/pointer cho dữ liệu ngoài dòng. CLUSTER rewrite relation cần duy trì nội dung table và dữ liệu TOAST tương ứng.

### 21.2. Payload lớn làm chi phí tăng

Một table có nhiều JSONB hoặc text lớn có thể tốn nhiều I/O/disk hơn khi rewrite. Đừng ước lượng chỉ bằng pg_relation_size heap mà bỏ qua TOAST và indexes.

### 21.3. Đo tổng kích thước

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap_size,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes_size,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total_size;
```

pg_total_relation_size bao gồm relation, indexes và TOAST liên quan theo cách PostgreSQL tính tổng kích thước.

## 22. Partitioning có thể giảm nhu cầu CLUSTER toàn bảng

Nếu dữ liệu có vòng đời theo thời gian, partitioning có thể chia table lớn thành các relation nhỏ theo range:

```sql
CREATE TABLE app.events_partitioned (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);
```

Ví dụ partition theo tháng:

```sql
CREATE TABLE app.events_2026_10
PARTITION OF app.events_partitioned
FOR VALUES FROM ('2026-10-01 00:00:00+00')
TO ('2026-11-01 00:00:00+00');
```

### 22.1. Partition pruning

Query lọc theo partition key có thể chỉ đọc các partitions phù hợp. Điều này giảm dữ liệu cần quét mà không đòi reorder toàn bộ lịch sử.

### 22.2. CLUSTER theo partition

Nếu cần locality sâu hơn trong một partition, đánh giá cluster/rewrite trên các child tables riêng theo khả năng hỗ trợ của phiên bản và cấu trúc partition.

### 22.3. Partition không tự sắp xếp rows

Mỗi partition vẫn là một relation có cách lưu heap thông thường. Partitioning và CLUSTER giải quyết hai lớp khác nhau: pruning theo phạm vi dữ liệu và locality trong relation.

### 22.4. Retention

Drop/detach partition cũ có thể rẻ hơn DELETE hàng triệu rows khi chính sách cho phép. Nhưng đó là lifecycle management, không phải thay thế mọi trường hợp CLUSTER.

## 23. BRIN và dữ liệu tự nhiên có thứ tự

Với bảng rất lớn có cột thời gian tương quan vật lý cao, BRIN index có thể là lựa chọn nhỏ gọn:

```sql
CREATE INDEX events_occurred_at_brin
ON storage_lab.events
USING brin (occurred_at);
```

### 23.1. BRIN hoạt động ở mức block ranges

BRIN lưu summaries cho các nhóm heap blocks. Khi dữ liệu có correlation tốt, nó giúp loại trừ nhiều block không liên quan.

### 23.2. CLUSTER và BRIN có thể bổ trợ

CLUSTER có thể làm physical locality tốt hơn; BRIN có thể tận dụng sự tương quan đó để giảm vùng đọc. Nhưng với dữ liệu liên tục được cập nhật/random insert, hiệu quả có thể giảm.

### 23.3. Không dùng BRIN thay B-tree cho mọi query

BRIN là lossy summary index và thường cần recheck tuples. B-tree phù hợp nhiều lookup/order-by patterns có tính chọn lọc. Chọn index theo workload.

## 24. Bảng nào đáng CLUSTER?

Những đặc điểm thuận lợi:

- Table lớn và có query range scan thường xuyên.
- Query lọc theo một key có thứ tự rõ.
- Nhiều rows trả về nên heap fetch locality quan trọng.
- Dữ liệu ít thay đổi hoặc insert gần theo thứ tự key.
- Có maintenance window và disk/WAL headroom.

Những đặc điểm không thuận lợi:

- Table nhỏ, luôn nằm trong cache.
- Workload chủ yếu point lookup trả một row.
- Table update/random insert rất thường xuyên.
- Nhiều query cần các thứ tự vật lý khác nhau.
- Không thể chịu ACCESS EXCLUSIVE blocking.
- Disk không đủ để rewrite và giữ WAL/replication headroom.

### 24.1. Tần suất query

Một truy vấn hiếm chạy vài phút có thể không đủ lý do để rewrite một table vài terabytes.

### 24.2. Selectivity

Nếu query trả 1 row, B-tree lookup có thể đã hiệu quả. Nếu query trả hàng trăm nghìn rows và cần fetch nhiều cột, heap locality có thể quan trọng hơn.

### 24.3. Access pattern thay đổi

Một table hôm nay chủ yếu đọc theo thời gian, nhưng quý sau chuyển sang truy vấn theo customer. CLUSTER theo thời gian có thể không còn là lựa chọn tối ưu.

## 25. Quan sát tiến trình CLUSTER

PostgreSQL cung cấp view tiến trình pg_stat_progress_cluster trên các phiên bản hỗ trợ.

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
```

### 25.1. Các phase

Tên phase và thông tin progress có thể khác theo phiên bản. View cho biết tiến trình đang làm việc với relation nào, giai đoạn nào và tiến độ scan/write/rebuild.

### 25.2. Không phải lúc nào mọi counter cũng tăng đều

Một số phase không có cùng loại counter; tốc độ có thể dao động theo I/O và sort. Không ngoại suy ETA tuyến tính từ vài giây đầu.

### 25.3. Quan sát active backend

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE query ILIKE 'CLUSTER%'
ORDER BY query_start;
```

Query text có thể bị giới hạn theo quyền/setting và có thể chứa thông tin nhạy cảm; hạn chế ai được xem.

## 26. Kiểm tra lock trước khi chạy

Một câu truy vấn tổng quát:

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    l.mode,
    l.granted,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'storage_lab.events'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
```

### 26.1. Tìm blocker và waiter

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid;
```

### 26.2. Kiểm tra transaction dài

```sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 26.3. Không terminate blocker một cách tự động

Một transaction lâu có thể là migration hoặc nghiệp vụ đang xử lý. Trước khi cancel/terminate, xác minh owner, request, khả năng rollback và hậu quả.

## 27. Đo kích thước trước và sau

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total;
```

### 27.1. Kích thước giảm không đồng nghĩa query nhanh hơn

Một rewrite có thể compact table và giảm bloat nhưng workload query có thể không được cải thiện. Đo cả latency, buffers và throughput.

### 27.2. Kích thước tăng không luôn là lỗi

Fillfactor thấp hơn, TOAST, index build và cách phân bổ pages có thể làm kích thước khác. Phải đối chiếu mục tiêu và setting.

### 27.3. Dung lượng filesystem

pg_total_relation_size không đại diện toàn bộ nhu cầu trong lúc rewrite. Phải tính WAL directory, archive, replication slots giữ WAL, temp files và tablespaces.

## 28. Đọc EXPLAIN để đánh giá lợi ích

Trước và sau CLUSTER, chạy cùng query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00'
ORDER BY occurred_at;
```

### 28.1. Những điều cần so sánh

- Node type: Index Scan, Bitmap Heap Scan, Seq Scan.
- Estimated rows và actual rows.
- Heap blocks read/hit.
- Shared buffers.
- Sort method và temp I/O.
- Execution time.
- Rows removed by filter.

### 28.2. Không ép enable_seqscan=off làm kết quả benchmark chuẩn

Planner chọn sequential scan có thể là quyết định đúng. Đừng chỉ tắt scan types để chứng minh CLUSTER làm index scan tốt hơn.

### 28.3. Cache state và warm-up

Chạy nhiều lượt, ghi nhận warm/cold cache nếu có thể kiểm soát. Không xóa OS cache trên production để tạo benchmark.

### 28.4. Cùng workload

Đảm bảo cùng query, parameter values, data volume, concurrency và cấu hình. Nếu không, so sánh trước/sau không có ý nghĩa.

## 29. CLUSTER và statistics sau rewrite

Sau khi CLUSTER xong:

```sql
ANALYZE storage_lab.events;
```

### 29.1. Vì sao planner cần statistics mới?

Planner ước lượng chi phí dựa trên phân bố giá trị, selectivity, correlation và các thống kê khác. Physical order đã thay đổi nên statistics cũ có thể không phản ánh tốt bố trí mới.

### 29.2. Autovacuum/analyze

Autovacuum có thể cập nhật statistics theo trigger/threshold, nhưng sau một maintenance rewrite quan trọng, chủ động ANALYZE giúp query planner có thông tin mới sớm hơn.

### 29.3. Extended statistics

Nếu query phụ thuộc tương quan giữa nhiều columns, có thể cần extended statistics:

```sql
CREATE STATISTICS events_customer_status_stats
(dependencies, ndistinct)
ON customer_id, status
FROM app.events;

ANALYZE app.events;
```

Đây là ví dụ với bảng giả định có cột status. Extended stats cải thiện ước lượng một số quan hệ giữa columns; nó không trực tiếp thay physical ordering.

## 30. CLUSTER và index-only scans

Index-only scan có thể tránh đọc heap nếu mọi điều kiện visibility phù hợp với visibility map.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT occurred_at
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00';
```

### 30.1. Nếu index chứa đủ cột

Index-only scan có thể lấy kết quả trực tiếp từ index, giảm heap access. Khi ấy CLUSTER có thể không cải thiện nhiều cho query này.

### 30.2. Visibility map

PostgreSQL cần biết page nào all-visible để bỏ qua heap visibility checks trong index-only scan. VACUUM cập nhật visibility map; CLUSTER rewrite cũng làm thay đổi trạng thái vật lý và cần xem xét maintenance/analyze phù hợp.

### 30.3. Query cần payload

Nếu query lấy payload không nằm trong index, heap fetch vẫn cần thiết; locality có thể có giá trị hơn.

## 31. CLUSTER và partitioned tables

Với table partitioned, mỗi partition là một relation vật lý riêng. Không giả định một lệnh CLUSTER trên parent sẽ xử lý toàn bộ child tables như một heap đơn.

### 31.1. Xác định loại relation

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relispartition
FROM pg_class AS c
WHERE c.oid IN ('app.events'::regclass);
```

### 31.2. Cluster từng partition khi phù hợp

Xem hỗ trợ và giới hạn của phiên bản PostgreSQL đang chạy; nếu cần, chạy maintenance trên từng partition vật lý phù hợp, với index và lock budget riêng.

### 31.3. Partition không tự sắp xếp rows

Mỗi partition vẫn là một relation có cách lưu heap thông thường. Partitioning và CLUSTER giải quyết hai lớp khác nhau: pruning theo phạm vi dữ liệu và locality trong relation.

### 31.4. Retention

Drop/detach partition cũ có thể rẻ hơn DELETE hàng triệu rows khi chính sách cho phép. Nhưng đó là lifecycle management, không phải thay thế mọi trường hợp CLUSTER.

## 32. BRIN và dữ liệu tự nhiên có thứ tự

Với bảng rất lớn có cột thời gian tương quan vật lý cao, BRIN index có thể là lựa chọn nhỏ gọn:

```sql
CREATE INDEX events_occurred_at_brin
ON storage_lab.events
USING brin (occurred_at);
```

### 32.1. BRIN hoạt động ở mức block ranges

BRIN lưu summaries cho các nhóm heap blocks. Khi dữ liệu có correlation tốt, nó giúp loại trừ nhiều block không liên quan.

### 32.2. CLUSTER và BRIN có thể bổ trợ

CLUSTER có thể làm physical locality tốt hơn; BRIN có thể tận dụng sự tương quan đó để giảm vùng đọc. Nhưng với dữ liệu liên tục được cập nhật/random insert, hiệu quả có thể giảm.

### 32.3. Không dùng BRIN thay B-tree cho mọi query

BRIN là lossy summary index và thường cần recheck tuples. B-tree phù hợp nhiều lookup/order-by patterns có tính chọn lọc. Chọn index theo workload.

## 33. Bảng nào đáng CLUSTER?

Những đặc điểm thuận lợi:

- Table lớn và có query range scan thường xuyên.
- Query lọc theo một key có thứ tự rõ.
- Nhiều rows trả về nên heap fetch locality quan trọng.
- Dữ liệu ít thay đổi hoặc insert gần theo thứ tự key.
- Có maintenance window và disk/WAL headroom.

Những đặc điểm không thuận lợi:

- Table nhỏ, luôn nằm trong cache.
- Workload chủ yếu point lookup trả một row.
- Table update/random insert rất thường xuyên.
- Nhiều query cần các thứ tự vật lý khác nhau.
- Không thể chịu ACCESS EXCLUSIVE blocking.
- Disk không đủ để rewrite và giữ WAL/replication headroom.

### 33.1. Tần suất query

Một truy vấn hiếm chạy vài phút có thể không đủ lý do để rewrite một table vài terabytes.

### 33.2. Selectivity

Nếu query trả 1 row, B-tree lookup có thể đã hiệu quả. Nếu query trả hàng trăm nghìn rows và cần fetch nhiều cột, heap locality có thể quan trọng hơn.

### 33.3. Access pattern thay đổi

Một table hôm nay chủ yếu đọc theo thời gian, nhưng quý sau chuyển sang truy vấn theo customer. CLUSTER theo thời gian có thể không còn là lựa chọn tối ưu.

## 34. Quan sát tiến trình CLUSTER

PostgreSQL cung cấp view tiến trình pg_stat_progress_cluster trên các phiên bản hỗ trợ.

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
```

### 34.1. Các phase

Tên phase và thông tin progress có thể khác theo phiên bản. View cho biết tiến trình đang làm việc với relation nào, giai đoạn nào và tiến độ scan/write/rebuild.

### 34.2. Không phải lúc nào mọi counter cũng tăng đều

Một số phase không có cùng loại counter; tốc độ có thể dao động theo I/O và sort. Không ngoại suy ETA tuyến tính từ vài giây đầu.

### 34.3. Quan sát active backend

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE query ILIKE 'CLUSTER%'
ORDER BY query_start;
```

Query text có thể bị giới hạn theo quyền/setting và có thể chứa thông tin nhạy cảm; hạn chế ai được xem.

## 35. Kiểm tra lock trước khi chạy

Một câu truy vấn tổng quát:

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    l.mode,
    l.granted,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'storage_lab.events'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
```

### 35.1. Tìm blocker và waiter

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid;
```

### 35.2. Kiểm tra transaction dài

```sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 35.3. Không terminate blocker một cách tự động

Một transaction lâu có thể là migration hoặc nghiệp vụ đang xử lý. Trước khi cancel/terminate, xác minh owner, request, khả năng rollback và hậu quả.

## 36. Đo kích thước trước và sau

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total;
```

### 36.1. Kích thước giảm không đồng nghĩa query nhanh hơn

Một rewrite có thể compact table và giảm bloat nhưng workload query có thể không được cải thiện. Đo cả latency, buffers và throughput.

### 36.2. Kích thước tăng không luôn là lỗi

Fillfactor thấp hơn, TOAST, index build và cách phân bổ pages có thể làm kích thước khác. Phải đối chiếu mục tiêu và setting.

### 36.3. Dung lượng filesystem

pg_total_relation_size không đại diện toàn bộ nhu cầu trong lúc rewrite. Phải tính WAL directory, archive, replication slots giữ WAL, temp files và tablespaces.

## 37. Đọc EXPLAIN để đánh giá lợi ích

Trước và sau CLUSTER, chạy cùng query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00'
ORDER BY occurred_at;
```

### 37.1. Những điều cần so sánh

- Node type: Index Scan, Bitmap Heap Scan, Seq Scan.
- Estimated rows và actual rows.
- Heap blocks read/hit.
- Shared buffers.
- Sort method và temp I/O.
- Execution time.
- Rows removed by filter.

### 37.2. Không ép enable_seqscan=off làm kết quả benchmark chuẩn

Planner chọn sequential scan có thể là quyết định đúng. Đừng chỉ tắt scan types để chứng minh CLUSTER làm index scan tốt hơn.

### 37.3. Cache state và warm-up

Chạy nhiều lượt, ghi nhận warm/cold cache nếu có thể kiểm soát. Không xóa OS cache trên production để tạo benchmark.

### 37.4. Cùng workload

Đảm bảo cùng query, parameter values, data volume, concurrency và cấu hình. Nếu không, so sánh trước/sau không có ý nghĩa.

## 38. CLUSTER và statistics sau rewrite

Sau khi CLUSTER xong:

```sql
ANALYZE storage_lab.events;
```

### 38.1. Vì sao planner cần statistics mới?

Planner ước lượng chi phí dựa trên phân bố giá trị, selectivity, correlation và các thống kê khác. Physical order đã thay đổi nên statistics cũ có thể không phản ánh tốt bố trí mới.

### 38.2. Autovacuum/analyze

Autovacuum có thể cập nhật statistics theo trigger/threshold, nhưng sau một maintenance rewrite quan trọng, chủ động ANALYZE giúp query planner có thông tin mới sớm hơn.

### 38.3. Extended statistics

Nếu query phụ thuộc tương quan giữa nhiều columns, có thể cần extended statistics:

```sql
CREATE STATISTICS events_customer_status_stats
(dependencies, ndistinct)
ON customer_id, status
FROM app.events;

ANALYZE app.events;
```

Đây là ví dụ với bảng giả định có cột status. Extended stats cải thiện ước lượng một số quan hệ giữa columns; nó không trực tiếp thay physical ordering.

## 39. CLUSTER và index-only scans

Index-only scan có thể tránh đọc heap nếu mọi điều kiện visibility phù hợp với visibility map.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT occurred_at
FROM storage_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 12:10:00+00';
```

### 39.1. Nếu index chứa đủ cột

Index-only scan có thể lấy kết quả trực tiếp từ index, giảm heap access. Khi ấy CLUSTER có thể không cải thiện nhiều cho query này.

### 39.2. Visibility map

PostgreSQL cần biết page nào all-visible để bỏ qua heap visibility checks trong index-only scan. VACUUM cập nhật visibility map; CLUSTER rewrite cũng làm thay đổi trạng thái vật lý và cần xem xét maintenance/analyze phù hợp.

### 39.3. Query cần payload

Nếu query lấy payload không nằm trong index, heap fetch vẫn cần thiết; locality có thể có giá trị hơn.

## 40. CLUSTER và partitioned tables

Với table partitioned, mỗi partition là một relation vật lý riêng. Không giả định một lệnh CLUSTER trên parent sẽ xử lý toàn bộ child tables như một heap đơn.

### 40.1. Xác định loại relation

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relispartition
FROM pg_class AS c
WHERE c.oid IN ('app.events'::regclass);
```

### 40.2. Cluster từng partition khi phù hợp

Xem hỗ trợ và giới hạn của phiên bản PostgreSQL đang chạy; nếu cần, chạy maintenance trên từng partition vật lý phù hợp, với index và lock budget riêng.

### 40.3. Partition không tự sắp xếp rows

Mỗi partition vẫn là một relation có cách lưu heap thông thường. Partitioning và CLUSTER giải quyết hai lớp khác nhau: pruning theo phạm vi dữ liệu và locality trong relation.

### 40.4. Retention

Drop/detach partition cũ có thể rẻ hơn DELETE hàng triệu rows khi chính sách cho phép. Nhưng đó là lifecycle management, không phải thay thế mọi trường hợp CLUSTER.

## 41. BRIN và dữ liệu tự nhiên có thứ tự

Với bảng rất lớn có cột thời gian tương quan vật lý cao, BRIN index có thể là lựa chọn nhỏ gọn:

```sql
CREATE INDEX events_occurred_at_brin
ON storage_lab.events
USING brin (occurred_at);
```

### 41.1. BRIN hoạt động ở mức block ranges

BRIN lưu summaries cho các nhóm heap blocks. Khi dữ liệu có correlation tốt, nó giúp loại trừ nhiều block không liên quan.

### 41.2. CLUSTER và BRIN có thể bổ trợ

CLUSTER có thể làm physical locality tốt hơn; BRIN có thể tận dụng sự tương quan đó để giảm vùng đọc. Nhưng với dữ liệu liên tục được cập nhật/random insert, hiệu quả có thể giảm.

### 41.3. Không dùng BRIN thay B-tree cho mọi query

BRIN là lossy summary index và thường cần recheck tuples. B-tree phù hợp nhiều lookup/order-by patterns có tính chọn lọc. Chọn index theo workload.

## 42. Bảng nào đáng CLUSTER?

Những đặc điểm thuận lợi:

- Table lớn và có query range scan thường xuyên.
- Query lọc theo một key có thứ tự rõ.
- Nhiều rows trả về nên heap fetch locality quan trọng.
- Dữ liệu ít thay đổi hoặc insert gần theo thứ tự key.
- Có maintenance window và disk/WAL headroom.

Những đặc điểm không thuận lợi:

- Table nhỏ, luôn nằm trong cache.
- Workload chủ yếu point lookup trả một row.
- Table update/random insert rất thường xuyên.
- Nhiều query cần các thứ tự vật lý khác nhau.
- Không thể chịu ACCESS EXCLUSIVE blocking.
- Disk không đủ để rewrite và giữ WAL/replication headroom.

### 42.1. Tần suất query

Một truy vấn hiếm chạy vài phút có thể không đủ lý do để rewrite một table vài terabytes.

### 42.2. Selectivity

Nếu query trả 1 row, B-tree lookup có thể đã hiệu quả. Nếu query trả hàng trăm nghìn rows và cần fetch nhiều cột, heap locality có thể quan trọng hơn.

### 42.3. Access pattern thay đổi

Một table hôm nay chủ yếu đọc theo thời gian, nhưng quý sau chuyển sang truy vấn theo customer. CLUSTER theo thời gian có thể không còn là lựa chọn tối ưu.

## 43. Quan sát tiến trình CLUSTER

PostgreSQL cung cấp view tiến trình pg_stat_progress_cluster trên các phiên bản hỗ trợ.

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
```

### 43.1. Các phase

Tên phase và thông tin progress có thể khác theo phiên bản. View cho biết tiến trình đang làm việc với relation nào, giai đoạn nào và tiến độ scan/write/rebuild.

### 43.2. Không phải lúc nào mọi counter cũng tăng đều

Một số phase không có cùng loại counter; tốc độ có thể dao động theo I/O và sort. Không ngoại suy ETA tuyến tính từ vài giây đầu.

### 43.3. Quan sát active backend

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    query
FROM pg_stat_activity
WHERE query ILIKE 'CLUSTER%'
ORDER BY query_start;
```

Query text có thể bị giới hạn theo quyền/setting và có thể chứa thông tin nhạy cảm; hạn chế ai được xem.

## 44. Kiểm tra lock trước khi chạy

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS transaction_age,
    l.mode,
    l.granted,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'storage_lab.events'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
```

### 44.1. Tìm blocker và waiter

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocking_pid.pid;
```

### 44.2. Kiểm tra transaction dài

```sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 44.3. Không terminate blocker một cách tự động

Một transaction lâu có thể là migration hoặc nghiệp vụ đang xử lý. Trước khi cancel/terminate, xác minh owner, request, khả năng rollback và hậu quả.

## 45. Đo kích thước trước và sau

```sql
SELECT
    pg_size_pretty(pg_relation_size('storage_lab.events'))
        AS heap,
    pg_size_pretty(pg_indexes_size('storage_lab.events'))
        AS indexes,
    pg_size_pretty(pg_total_relation_size('storage_lab.events'))
        AS total;
```

### 45.1. Kích thước giảm không đồng nghĩa query nhanh hơn

Một rewrite có thể compact table và giảm bloat nhưng workload query có thể không được cải thiện. Đo cả latency, buffers và throughput.

### 45.2. Kích thước tăng không luôn là lỗi

Fillfactor thấp hơn, TOAST, index build và cách phân bổ pages có thể làm kích thước khác. Phải đối chiếu mục tiêu và setting.

### 45.3. Dung lượng filesystem

pg_total_relation_size không đại diện toàn bộ nhu cầu trong lúc rewrite. Phải tính WAL directory, archive, replication slots giữ WAL, temp files và tablespaces.

## 46. Tablespace, memory và chi phí rewrite

Relation có thể nằm ở tablespace riêng. Việc di chuyển tablespace cũng có thể rewrite/move relation và cần lock/disk/I/O budget. Không gộp nó với CLUSTER trong một đợt maintenance mà chưa tính tổng chi phí.

CLUSTER có thể dùng index scan hoặc sort-based approach tùy điều kiện/cost. Nếu cần sort, maintenance memory và temp files có thể ảnh hưởng thời gian.

```sql
SET maintenance_work_mem = '1GB';

CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;
```

Giá trị 1GB chỉ là minh họa. Chọn theo RAM, concurrent maintenance và phiên bản/method thực tế.

### 46.1. Không đảm bảo tăng memory sẽ tuyến tính nhanh hơn

Nếu bottleneck là disk throughput, lock wait hoặc WAL/replication, tăng maintenance_work_mem có thể không cải thiện đáng kể.

### 46.2. Temporary files

Theo dõi temp file và disk utilization trong lúc maintenance để biết có spill lớn hay không. Đừng đặt maintenance_work_mem quá lớn khi nhiều maintenance jobs có thể chạy đồng thời.

### 46.3. Tablespace và đích rewrite

Kiểm tra tablespace, filesystem capacity và quyền truy cập trước khi chạy. Disk budget phải bao gồm relation mới, indexes, TOAST, temp files, WAL và archive.

## 47. Tác động tới replicas và backup

CLUSTER tạo WAL đáng kể. Với physical streaming replication:

- Primary tạo WAL.
- WAL được truyền tới standby.
- Standby replay các thay đổi vật lý.
- Replica lag có thể tăng trong thời gian rewrite.

### 47.1. Replication slots

Replication slot giữ WAL khi subscriber/standby chưa tiêu thụ. Nếu replay chậm, WAL disk usage có thể tăng đáng kể.

### 47.2. Read replicas

Replica có thể bị lag và query đọc có thể chậm hoặc không đáp ứng freshness SLA. Theo dõi replay lag, không chỉ primary completion.

### 47.3. Backup window

CLUSTER có thể tăng WAL archive volume và tác động thời gian backup/restore. Đảm bảo backup policy và archive storage có headroom.

### 47.4. Logical replication

Rewrite vật lý không nên được hiểu như một chuỗi UPDATE nghiệp vụ từng row. Hãy xác minh behavior logical replication và schema/DDL management theo phiên bản và kiến trúc cụ thể; không dùng physical rewrite làm cơ chế đồng bộ dữ liệu logic.

## 48. Partitioning và các loại relation khác

Với table partitioned, mỗi partition là một relation vật lý riêng. Không giả định một lệnh CLUSTER trên parent sẽ xử lý toàn bộ child tables như một heap đơn. Kiểm tra hỗ trợ và giới hạn của phiên bản; nếu cần, chạy maintenance trên từng partition vật lý phù hợp.

Foreign tables thường không có heap storage cục bộ như ordinary table; view là định nghĩa query, không có heap row storage riêng; materialized view có storage vật lý nhưng vẫn cần xác minh loại relation và lệnh được hỗ trợ.

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relispartition
FROM pg_class AS c
WHERE c.oid = 'app.events'::regclass;
```

Partition pruning có thể giảm dữ liệu cần quét mà không đòi reorder toàn bộ lịch sử. BRIN có thể tận dụng physical correlation tốt cho range scans trên dữ liệu lớn; nó là lossy summary index và thường cần recheck tuples, không thay B-tree cho mọi lookup/order-by.

## 49. Kế hoạch chạy CLUSTER trên production

Trước khi chạy:

1. Xác định query workload được kỳ vọng cải thiện.
2. Đo baseline EXPLAIN/latency/buffers.
3. Kiểm tra physical correlation.
4. Xác định đúng index và table.
5. Đo table/index/TOAST size.
6. Tính disk headroom và WAL/archive budget.
7. Kiểm tra replica health và replication slots.
8. Tìm long-running transactions/snapshots và lock blockers.
9. Chọn maintenance window và thông báo workload owners.
10. Đặt timeout phù hợp.
11. Có backup/restore và rollback strategy.
12. Chạy thử trên staging với dữ liệu tương tự.

Trong lúc chạy, theo dõi pg_stat_progress_cluster, locks, pg_stat_activity, disk, I/O, WAL, replication lag và application errors.

Sau khi chạy:

- Chạy ANALYZE.
- Đo lại EXPLAIN/BUFFERS cùng workload.
- Kiểm tra constraints/row counts.
- Theo dõi replicas catch up.
- Ghi lại thời gian, dung lượng và kết quả.
- Quyết định có cần maintenance lại hay không dựa trên dữ liệu.

### 49.1. Runbook thực hiện

```sql
SELECT
    'storage_lab.events'::regclass AS target,
    pg_size_pretty(
        pg_total_relation_size('storage_lab.events')
    ) AS total_size;

SELECT
    indexrelid::regclass AS index_name,
    indisclustered,
    indisvalid,
    indisready
FROM pg_index
WHERE indrelid = 'storage_lab.events'::regclass;
```

Sau khi xác nhận lock blockers và disk budget:

```sql
SET lock_timeout = '5s';
SET statement_timeout = '2h';

CLUSTER VERBOSE storage_lab.events
USING events_occurred_at_idx;
```

Các timeout chỉ là ví dụ. Thời gian thực tế phải dựa vào SLA và kích thước table; nếu thao tác vượt giới hạn, cần xử lý rõ ràng.

```sql
ANALYZE storage_lab.events;
```

### 49.2. CLUSTER thất bại hoặc bị cancel

Nguyên nhân có thể là không lấy được lock, statement timeout, người vận hành cancel, disk full, I/O error, index không phù hợp, permission không đủ hoặc server restart.

Không đánh giá trạng thái chỉ từ client timeout. Kiểm tra backend/process, locks, logs và relation state trước khi chạy lại. Disk full là tình huống nghiêm trọng; không dùng CLUSTER để “giải phóng disk” khi filesystem đã gần đầy.

Sau cancel, xác nhận thao tác đã kết thúc/rollback, query table được, indexes valid, locks đã giải phóng và replicas bắt kịp. Không retry liên tục nếu nguyên nhân là thiếu disk hoặc blocker dài.

## 50. Theo dõi churn và hiệu quả sau bảo trì

```sql
SELECT
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab'
  AND relname = 'events';
```

### 50.1. Đọc đúng nghĩa

- n_tup_upd: số UPDATE được thống kê.
- n_tup_hot_upd: số HOT updates.
- n_dead_tup: ước lượng dead tuples.
- last_analyze/last_autoanalyze: thời điểm analyze gần nhất.

Counters là statistics tích lũy/reset theo hệ thống; không coi là số liệu tuyệt đối bất biến.

### 50.2. Table write-heavy có thể nhanh mất correlation

Nếu workload random UPDATE/INSERT liên tục, CLUSTER hôm nay có thể chỉ cải thiện trong thời gian ngắn.

### 50.3. Cần nhìn cả query workload

Một bảng có correlation thấp nhưng không có range scans quan trọng có thể không cần CLUSTER.

## 51. CLUSTER theo tenant hoặc key nghiệp vụ

Một bảng đa tenant có index:

```sql
CREATE INDEX orders_tenant_time_idx
ON app.orders (tenant_id, created_at);
```

CLUSTER theo index này có thể đặt rows cùng tenant gần nhau, rồi theo thời gian trong tenant.

```sql
SELECT *
FROM app.orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at;
```

Physical adjacency của tenants không phải RLS, không phải encryption và không thay quyền truy cập. Dữ liệu của tenant khác vẫn nằm trong cùng relation và cần được bảo vệ bằng database authorization.

Nếu một tenant rất lớn, phân bố dữ liệu lệch có thể ảnh hưởng planner và cache. Physical order không tự giải quyết skew.

## 52. CLUSTER và workload append-only

Một event log có rows thường được append theo thời gian:

- Nếu source timestamps tăng gần với ingestion order, heap có thể đã có correlation tốt.
- Nếu có late-arriving events, dữ liệu backfill hoặc import theo thứ tự không ổn định, correlation giảm.

Không giả định append-only nghĩa là luôn tăng theo event time. So occurred_at với loaded_at, source lateness và pg_stats.correlation.

Partitioning có thể giúp loại bỏ phần lớn lịch sử khi query theo time range. Sau đó có thể cluster chỉ partition lịch sử nếu workload và maintenance budget phù hợp. BRIN có thể là giải pháp nhẹ nếu dữ liệu đã tự nhiên tương quan theo thời gian.

## 53. Giới hạn của CLUSTER

1. Chỉ một thứ tự vật lý tại một thời điểm cho mỗi heap.
2. Không duy trì ordering sau các lần ghi mới.
3. Cần khóa ACCESS EXCLUSIVE.
4. Rewrite tiêu tốn disk, I/O, WAL và thời gian.
5. Có thể gây replica lag.
6. Không tự làm mọi query nhanh hơn.
7. Không thay thế index design, partition pruning, vacuum hoặc statistics.
8. Không bảo đảm kết quả SELECT có thứ tự nếu thiếu ORDER BY.
9. Không phải mọi index access method/relation type đều hỗ trợ.
10. Có rủi ro với transactions giữ snapshot cũ qua thời điểm rewrite.

## 54. Bài tập thực hành PostgreSQL

Các bài tập sử dụng schema storage_lab và dữ liệu thử nghiệm. Không chạy rewrite/lock test trên production.

1. **Heap:** mô tả page, line pointer và tuple trong một heap relation.
2. **Index:** giải thích index entry trỏ tới heap tuple như thế nào.
3. **CTID:** truy vấn ctid của một số rows và giải thích block/offset.
4. **CTID stability:** UPDATE một row và kiểm tra ctid trước/sau.
5. **MVCC:** mô tả tuple version cũ/mới sau UPDATE.
6. **HOT:** nêu các điều kiện giúp UPDATE trở thành HOT update.
7. **Dead tuples:** giải thích vì sao DELETE không lập tức thu hồi file size.
8. **Ordering:** chạy SELECT không ORDER BY nhiều lần và giải thích vì sao thứ tự không được bảo đảm.
9. **ORDER BY:** thêm tie-breaker vào query pagination.
10. **Index locality:** vẽ ví dụ key order và heap pages rải rác.
11. **CLUSTER:** giải thích mục tiêu của lệnh CLUSTER.
12. **Syntax:** chạy CLUSTER table USING index trên table lab.
13. **Mark index:** dùng ALTER TABLE ... CLUSTER ON và kiểm tra indisclustered.
14. **Remembered index:** chạy CLUSTER table không ghi USING sau khi đã đánh dấu.
15. **All tables:** giải thích rủi ro của CLUSTER VERBOSE không có table name.
16. **Index eligibility:** xác minh access methods nào trong phiên bản đang chạy được phép CLUSTER.
17. **Multi-column:** tạo index (customer_id, occurred_at) và giải thích lexicographic ordering.
18. **Tie keys:** tạo index không unique và giải thích thứ tự giữa rows trùng key.
19. **Lab data:** tạo 100.000 rows theo thứ tự insert không tương quan.
20. **Baseline:** tạo index occurred_at và ANALYZE.
21. **Correlation:** đọc pg_stats.correlation trước CLUSTER.
22. **Benchmark:** chạy EXPLAIN (ANALYZE, BUFFERS) cho range query.
23. **Cluster:** CLUSTER theo events_occurred_at_idx.
24. **Analyze:** ANALYZE sau CLUSTER và đọc correlation lần nữa.
25. **Compare:** so heap blocks và latency trước/sau.
26. **Cache:** giải thích tại sao benchmark warm-cache có thể khác cold-cache.
27. **Index-only:** tạo query chỉ lấy cột index và xem khả năng index-only scan.
28. **Payload:** thêm payload vào SELECT và xem heap fetch thay đổi.
29. **Seq scan:** giải thích khi nào planner chọn sequential scan dù có index.
30. **Physical order:** giải thích vì sao CLUSTER không bảo đảm SELECT có thứ tự.
31. **New insert:** INSERT một timestamp cũ sau CLUSTER và phân tích locality.
32. **Update key:** UPDATE clustering key và giải thích tuple version mới.
33. **Write churn:** đo n_tup_upd và n_tup_hot_upd trong pg_stat_user_tables.
34. **Recluster:** nêu tín hiệu nào đủ để chạy CLUSTER lần nữa.
35. **VACUUM:** chạy VACUUM ANALYZE và giải thích nó khác CLUSTER.
36. **VACUUM FULL:** giải thích mục tiêu reclaim space và lock.
37. **REINDEX:** rebuild index và chứng minh heap order không được sắp lại.
38. **pg_repack:** nghiên cứu prerequisites và mô hình lock của extension.
39. **Comparison:** lập bảng so sánh VACUUM, VACUUM FULL, CLUSTER, REINDEX, pg_repack.
40. **Fillfactor:** đặt fillfactor 80 và phân tích trade-off với page density.
41. **HOT:** giải thích vì sao fillfactor có thể giúp HOT nhưng tăng storage footprint.
42. **TOAST:** đo pg_total_relation_size và phân biệt heap/index/TOAST.
43. **Disk budget:** lập kế hoạch dung lượng cần thiết cho rewrite table lớn.
44. **WAL:** giải thích vì sao CLUSTER tạo WAL và có thể tăng replica lag.
45. **Lock mode:** tìm hiểu ACCESS EXCLUSIVE và các lock xung đột.
46. **Blockers:** dùng pg_locks và pg_stat_activity để tìm session giữ lock.
47. **Waiting:** giải thích lock queue domino khi CLUSTER chờ ACCESS EXCLUSIVE.
48. **lock_timeout:** thử lock_timeout ngắn trong lab và quan sát lỗi.
49. **statement_timeout:** phân biệt giới hạn chờ lock và thời gian thực thi tổng.
50. **Old snapshots:** giải thích cảnh báo MVCC-safety khi transaction giữ snapshot cũ.
51. **Progress:** đọc pg_stat_progress_cluster trong lúc một session chạy CLUSTER.
52. **Size:** đo heap/index/total size trước và sau rewrite.
53. **Memory:** nghiên cứu maintenance_work_mem và tác động sort/temp files.
54. **Temp I/O:** theo dõi temp file trong một thao tác sort lớn.
55. **Partition:** tạo partition theo thời gian và giải thích partition pruning khác CLUSTER.
56. **Partition maintenance:** đề xuất chính sách cluster chỉ những partitions lịch sử.
57. **BRIN:** tạo BRIN index trên occurred_at và so với B-tree.
58. **Tenant index:** tạo index (tenant_id, created_at) và phân tích physical grouping.
59. **Security:** giải thích tại sao physical grouping không phải tenant isolation.
60. **Collation:** tạo index với collation và phân tích ordering khi CLUSTER.
61. **Index mark:** đổi index được đánh dấu cluster và xác minh metadata.
62. **Replica:** lập dashboard replay lag trong maintenance.
63. **Backup:** phân tích WAL archive/storage khi rewrite.
64. **Tablespace:** kiểm tra table/index tablespaces và disk headroom.
65. **Production plan:** viết checklist trước khi chạy CLUSTER cho table 500 GB.
66. **Cancel:** lập quy trình xử lý khi CLUSTER bị cancel hoặc server mất kết nối.
67. **EXPLAIN:** so sánh Index Scan và Bitmap Heap Scan sau cluster.
68. **Buffers:** phân biệt shared hit và shared read trong EXPLAIN.
69. **Query diversity:** giải thích vì sao một table không thể tối ưu physical order cho mọi index.
70. **Workload:** chọn một query có đủ selectivity để benchmark CLUSTER.
71. **No benefit:** nêu ba trường hợp CLUSTER không cải thiện hiệu năng.
72. **Append-only:** đánh giá correlation của dữ liệu ghi theo event time.
73. **Late arrivals:** phân tích tác động của dữ liệu đến trễ lên physical order.
74. **Partition + BRIN:** đề xuất kiến trúc cho bảng event rất lớn.
75. **Long transactions:** truy vấn các transaction lâu trước maintenance.
76. **Monitoring:** xây truy vấn theo dõi pg_stat_progress_cluster, pg_locks và pg_stat_activity.
77. **Capacity:** tính tổng dung lượng cho heap mới, indexes, TOAST, WAL và temp.
78. **Benchmark integrity:** lập quy trình so sánh cùng query/parameters/cache/concurrency.
79. **Maintenance cadence:** thiết kế tiêu chí chạy lại dựa trên correlation, query latency và write churn.
80. **Thiết kế tổng hợp:** chọn index clustering, fillfactor, thời điểm, lock/timeouts, disk/WAL budget, replica monitoring, ANALYZE và rollback plan cho bảng production có range queries.

## 55. Checklist trước khi quyết định

### Workload

- [ ] Có query range scan quan trọng đọc nhiều rows và heap columns.
- [ ] Query thực sự dùng index dự kiến làm clustering key.
- [ ] Physical correlation hiện tại thấp hoặc locality có vấn đề.
- [ ] Lợi ích đã được chứng minh qua EXPLAIN/BUFFERS hoặc benchmark.
- [ ] Không có một thứ tự vật lý khác quan trọng hơn.

### Chi phí

- [ ] Table/index/TOAST size đã được đo.
- [ ] Filesystem và tablespace có đủ disk headroom.
- [ ] WAL/archive/replication slots có headroom.
- [ ] I/O và CPU có thể chịu rewrite.
- [ ] Thời gian maintenance window đủ.

### Blocking và consistency

- [ ] Có thể lấy ACCESS EXCLUSIVE lock.
- [ ] Long-running transactions/snapshots đã được kiểm tra.
- [ ] Application owners biết table sẽ bị block.
- [ ] Có timeout và cancel/rollback plan.

### Sau maintenance

- [ ] ANALYZE được chạy.
- [ ] EXPLAIN/BUFFERS được đo lại.
- [ ] Replica lag được theo dõi tới khi catch up.
- [ ] Query latency/throughput đạt mục tiêu.
- [ ] Có kế hoạch quan sát correlation suy giảm theo thời gian.

## 56. Tổng kết

CLUSTER đáng cân nhắc khi **heap locality là bottleneck có bằng chứng**. Một index range scan lấy nhiều rows và nhiều columns có thể hưởng lợi khi những rows theo key được gom trên các heap pages gần nhau. Nhưng thao tác viết lại toàn bộ relation có thể gây chi phí lớn hơn lợi ích nếu workload thay đổi liên tục hoặc không cần locality.

```text
CLUSTER
  = REWRITE HEAP THEO INDEX ORDER
  + REBUILD INDEXES
  + ACCESS EXCLUSIVE LOCK
  + DISK / I/O / WAL COST
  + PHYSICAL LOCALITY CÓ THỂ TỐT HƠN

SAU CLUSTER
  INSERT / UPDATE / DELETE TIẾP TỤC
  THEO CƠ CHẾ HEAP THÔNG THƯỜNG
  -> CORRELATION CÓ THỂ GIẢM DẦN
```

Những nguyên tắc quan trọng:

- **Heap và index là hai cấu trúc riêng.** Index order không tự động là heap order.
- **ORDER BY mới bảo đảm thứ tự kết quả.** CLUSTER chỉ thay bố trí vật lý.
- **MVCC tạo nhiều tuple versions.** UPDATE, DELETE và INSERT có thể làm locality suy giảm.
- **CLUSTER viết lại table theo index**, rebuild indexes và cần ACCESS EXCLUSIVE lock.
- **CLUSTER không duy trì thứ tự cho các lần ghi tiếp theo.** Đánh giá lại theo workload và physical correlation.
- **Chi phí không chỉ là thời gian câu lệnh:** phải tính disk, TOAST, indexes, WAL, replica lag, temp I/O và blocking.
- **VACUUM, VACUUM FULL, REINDEX và pg_repack có mục tiêu khác nhau.** Chọn công cụ đúng vấn đề.
- **Đo trước/sau bằng EXPLAIN (ANALYZE, BUFFERS)** và cập nhật statistics bằng ANALYZE.
- **Không chạy rewrite lớn khi thiếu disk hoặc còn long-running snapshots/transactions.** Có lock, timeout và rollback plan.
- **Chọn index cluster theo query workload**, không theo thói quen hoặc chỉ vì index đó là primary key.

Khi hiểu rõ CLUSTER, bạn có thể chủ động cải thiện locality của heap cho các workload phù hợp mà vẫn dự trù được tác động của rewrite lên ứng dụng, storage, WAL và replicas. Một quyết định tốt luôn bắt đầu từ **đo đạc physical correlation và query cost**, kết thúc bằng việc kiểm chứng lợi ích thực tế sau maintenance.
