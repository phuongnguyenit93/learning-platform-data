# Bloat trong bảng và chỉ mục PostgreSQL

Một bảng PostgreSQL có 2 triệu hàng đang hoạt động nhưng file trên đĩa lớn gấp nhiều lần dự kiến. Một chỉ mục từng nhỏ nay chiếm hàng chục gigabyte. Query vẫn đúng, nhưng cache hit giảm, backup lâu hơn, I/O tăng và mỗi lần scan phải đọc nhiều page hơn. Những hiện tượng này có thể liên quan đến **bloat** trong bảng hoặc chỉ mục.

Trong PostgreSQL, bloat không đơn giản là “file có nhiều byte trống”. Nó thường hình thành từ cách **MVCC** giữ nhiều phiên bản row, cách VACUUM dọn những phiên bản không còn cần thiết, và cách các page/index pages giữ lại khoảng trống để tái sử dụng. Muốn xử lý đúng, trước hết phải phân biệt:

- Dead tuples còn tồn tại nhưng chưa thể dọn vì transaction/snapshot cũ;
- Dead tuples đã đủ điều kiện dọn và chờ VACUUM;
- Khoảng trống bên trong relation có thể tái sử dụng;
- Page/index page không còn hữu ích và cần được rewrite/rebuild để thu nhỏ file;
- Dung lượng tăng hợp lý vì dữ liệu thật, TOAST, indexes hoặc fillfactor.

**VACUUM thường giúp tái sử dụng không gian bên trong relation; nó không mặc định thu nhỏ file về hệ điều hành.** `VACUUM FULL`, `CLUSTER`, `pg_repack` hoặc `REINDEX` có thể rewrite/rebuild relation/index để thu hồi dung lượng, nhưng có chi phí, yêu cầu disk tạm và mức độ khóa khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích bloat trong bảng và chỉ mục là gì, vì sao không thể suy ra chỉ từ kích thước file.
2. Mô tả cách MVCC tạo row versions khi UPDATE/DELETE.
3. Phân biệt live tuples, dead tuples, free space, page fragmentation và bloat.
4. Giải thích vai trò của VACUUM thường, VACUUM FULL, ANALYZE, CLUSTER, REINDEX và pg_repack.
5. Hiểu vì sao VACUUM thường không nhất thiết làm file relation nhỏ đi.
6. Nhận diện những transaction/snapshot cũ giữ lại dead tuples.
7. Phân biệt bloat bảng, bloat index và dung lượng TOAST.
8. Giải thích HOT update, fillfactor và tác động tới index churn.
9. Đọc các thống kê `pg_stat_user_tables`, `pg_stat_user_indexes`, `pg_class` và `pg_stat_progress_vacuum`.
10. Dùng `pgstattuple`, `pgstattuple_approx` và `pgstatindex` khi extension có sẵn.
11. Hiểu giới hạn của các công thức ước lượng bloat và số liệu thống kê.
12. Điều chỉnh autovacuum theo quy mô bảng và tốc độ thay đổi dữ liệu.
13. Theo dõi vacuum freeze và rủi ro transaction ID wraparound.
14. Chọn cách xử lý phù hợp với mức độ bloat, lock budget, disk headroom và SLA.
15. Xây quy trình đo trước/sau khi vacuum hoặc rebuild.

## 2. Bloat là gì?

**Bloat** mô tả dung lượng relation (bảng, index hoặc TOAST relation) lớn hơn mức cần thiết để lưu dữ liệu hữu ích theo trạng thái hiện tại và thiết kế lưu trữ. Phần dư có thể đến từ:

- Các phiên bản row cũ (dead tuples) chưa được dọn;
- Khoảng trống bên trong page được giữ lại sau khi tuples bị xóa;
- Page/index page thưa do cập nhật, xóa, phân mảnh hoặc page splits;
- Fillfactor cố ý chừa khoảng trống;
- Dữ liệu TOAST lớn hoặc các index cần thiết mà người quan sát chưa tính vào;
- Những page không còn hiệu quả để truy vấn nhưng vẫn nằm trong file relation.

### 2.1. Ví dụ trực quan

Giả sử một bảng lưu 100.000 đơn hàng. Sau nhiều năm, một lượng lớn đơn đã bị xóa hoặc thay đổi. Kích thước file vẫn có thể gần bằng kích thước trước khi xóa:

~~~text
Trước khi thay đổi:
+--------------------------------------------------+
| live row | live row | live row | live row | ...  |
+--------------------------------------------------+

Sau nhiều UPDATE/DELETE:
+--------------------------------------------------+
| live row | dead row | free space | live row | ...|
+--------------------------------------------------+

Sau VACUUM thường:
+--------------------------------------------------+
| live row | reusable space | live row | free ... |
+--------------------------------------------------+

Sau rewrite/rebuild:
+---------------------------------------+
| live row | live row | live row | ...  |
+---------------------------------------+
~~~

Sơ đồ chỉ mô tả ý tưởng. Một heap page thực tế chứa page header, line pointers, tuple data, alignment và có thể có free space; index pages có cấu trúc riêng.

### 2.2. Bloat không đồng nghĩa mọi free space đều xấu

Một page còn chỗ trống có thể rất hữu ích:

- UPDATE có thể tạo phiên bản row mới ngay trên cùng page;
- HOT update có thể tránh tạo index entries mới;
- INSERT tiếp theo có thể sử dụng free space;
- Một index page chừa chỗ giúp hạn chế page splits.

Vì vậy, **không phải mọi byte trống đều cần thu hồi**. Cố ép mọi page đầy 100% có thể khiến các lần UPDATE/INSERT sau tốn I/O và tạo bloat mới nhanh hơn.

### 2.3. Kích thước relation không nói hết hiệu quả

Một bảng 10 GB có thể hợp lý nếu có nhiều live data. Một bảng 2 GB có thể có bloat lớn nếu chỉ còn một phần nhỏ dữ liệu cần thiết. Cần xem:

- Số live/dead tuples;
- Tỷ lệ free space và phân bố page;
- Kích thước heap, indexes và TOAST;
- Query workload và scan patterns;
- Xu hướng tăng theo thời gian, không chỉ một lần đo.

### 2.4. Phân biệt bloat với dung lượng tăng hợp lý

Nếu bảng có thêm cột JSONB chứa tài liệu lớn, index GIN mới hoặc số hàng tăng thật, relation lớn lên có thể là điều bình thường. **Không gọi mọi tăng trưởng disk là bloat.**

## 3. MVCC tạo row versions như thế nào?

PostgreSQL dùng **Multi-Version Concurrency Control (MVCC)**. UPDATE thường không ghi đè trực tiếp bytes của row cũ theo kiểu một file text; hệ thống tạo phiên bản mới để các transaction nhìn thấy snapshot phù hợp.

### 3.1. INSERT

Một INSERT tạo tuple mới với transaction metadata cho biết transaction nào đã tạo nó. Khi transaction commit, tuple có thể được nhìn thấy bởi các snapshot phù hợp.

### 3.2. UPDATE

Ví dụ:

~~~sql
UPDATE orders
SET status = 'paid'
WHERE order_id = 1001;
~~~

Về mặt MVCC, PostgreSQL thường:

1. Đánh dấu phiên bản cũ không còn là phiên bản hiện hành cho các snapshot mới;
2. Tạo phiên bản tuple mới chứa `status='paid'`;
3. Giữ phiên bản cũ cho tới khi không còn snapshot nào có thể cần nó;
4. Sau đó VACUUM có thể dọn phiên bản cũ.

Một UPDATE có thể tạo dead tuple dù số lượng hàng logic không đổi.

### 3.3. DELETE

~~~sql
DELETE FROM orders
WHERE order_id = 1001;
~~~

DELETE đánh dấu tuple là đã bị xóa theo transaction visibility. Tuple không nhất thiết biến mất ngay khỏi file. Nó cần được VACUUM dọn sau khi không còn transaction/snapshot nào cần nhìn thấy phiên bản đó.

### 3.4. Dead tuple không phải row đang hoạt động

**Dead tuple** là phiên bản row không còn hiển thị với snapshot hiện tại và có thể được thu hồi khi horizon transaction cho phép. Trong một khoảng thời gian, phiên bản cũ vẫn cần được giữ cho transaction đang đọc dữ liệu cũ.

### 3.5. Vì sao PostgreSQL không xóa ngay?

Một transaction có thể đã bắt đầu trước UPDATE và vẫn cần nhìn thấy giá trị cũ. Nếu PostgreSQL xóa phiên bản cũ ngay, transaction đó sẽ đọc dữ liệu sai hoặc mất tính nhất quán snapshot.

~~~text
Transaction A: BEGIN -------------------- SELECT ...
                    |
Transaction B:       UPDATE row; COMMIT
                    |
VACUUM:              chưa thể xóa old tuple nếu A còn cần snapshot cũ
                    |
Transaction A: COMMIT
                    |
VACUUM sau đó:       có thể dọn old tuple
~~~

### 3.6. HOT update

Trong điều kiện phù hợp, PostgreSQL có thể thực hiện **Heap-Only Tuple (HOT) update**: phiên bản mới nằm trên cùng heap page và không cần tạo index entries mới cho những indexes không bị ảnh hưởng. HOT giúp giảm index churn và chi phí dọn dẹp.

HOT thường yêu cầu:

- UPDATE không thay đổi những cột được index dùng (bao gồm các phụ thuộc index liên quan);
- Có đủ chỗ trên cùng heap page cho tuple mới;
- Các điều kiện HOT khác theo kiểu index/thiết kế cụ thể được đáp ứng.

### 3.7. Không phải UPDATE nào cũng tạo index entry mới

Nếu HOT update thành công, các index entries cũ có thể dẫn tới HOT chain; PostgreSQL có thể truy cập phiên bản thích hợp trong heap. Nếu HOT không thể thực hiện, index có thể cần entries mới cho row version mới, làm tăng index churn.

## 4. Ba lớp không gian cần phân biệt

### 4.1. Heap/table bloat

Heap bloat liên quan tới page của bảng chứa:

- Live tuples;
- Dead tuples;
- Line pointers;
- Free space;
- Page metadata.

Dead tuples và các page thưa có thể làm heap scan đọc nhiều page hơn cần thiết.

### 4.2. Index bloat

Index bloat là dung lượng index tăng vượt nhu cầu hữu ích do churn, page splits, deleted entries/pages và phân bố page không hiệu quả. B-tree index có các leaf/internal pages; các loại index khác (GIN, GiST, BRIN, hash) có cấu trúc và hành vi riêng.

**Không dùng một công thức B-tree để kết luận mọi loại index đều bloat như nhau.**

### 4.3. TOAST bloat

PostgreSQL có thể lưu giá trị lớn (text, bytea, JSONB...) ngoài heap chính trong TOAST relation. UPDATE/DELETE những giá trị lớn có thể làm TOAST table/index phát sinh dead tuples và free space.

Khi chỉ đo heap table, bạn có thể bỏ sót phần lớn dung lượng của một bảng chứa JSON/document lớn. Dùng `pg_total_relation_size()` và kiểm tra TOAST relation liên quan.

### 4.4. Page fragmentation

Page fragmentation mô tả dữ liệu phân bố thưa hoặc không liên tục theo cách làm tăng page reads/sequential scan hoặc giảm mật độ index. Một relation có free space nhưng workload có thể tái sử dụng nó hiệu quả; vì vậy fragmentation và bloat có liên quan nhưng không đồng nghĩa tuyệt đối.

### 4.5. Free space map (FSM)

FSM lưu thông tin ước lượng về free space trong relation để PostgreSQL tìm page phù hợp cho các lần ghi. FSM giúp tái sử dụng không gian; nó không phải bảng lưu dữ liệu nghiệp vụ và không có nghĩa mọi free bytes được trả lại hệ điều hành.

### 4.6. Visibility map (VM)

Visibility map theo dõi những heap pages mà mọi tuples đã được xác nhận visible cho tất cả transactions hiện tại, và trạng thái all-frozen. Nó giúp:

- VACUUM tránh scan lại một số page không cần thiết;
- Index-only scans bỏ qua heap fetch khi visibility conditions cho phép.

Dead tuples, updates hoặc transaction horizon có thể làm page mất trạng thái all-visible. VACUUM cập nhật VM theo quá trình dọn dẹp.

### 4.7. Bảng so sánh

| Khái niệm | Có thể tái sử dụng? | Có tự làm file nhỏ đi? |
| --- | --- | --- |
| Dead tuple đã dọn | Space được tái sử dụng trong relation | Thường không |
| Free space trong heap page | Có thể dùng cho tuple mới | Không |
| Empty/trailing pages | Có thể được truncate trong một số trường hợp vacuum | Có thể giảm file nếu ở cuối và đủ điều kiện |
| Index deleted/free pages | Có thể được index tái sử dụng tùy cấu trúc | Thường không |
| Bloat cần rewrite | Sau rewrite, relation/index được xây lại gọn hơn | Có, tùy phương pháp |

## 5. Những nguyên nhân phổ biến tạo bloat

### 5.1. UPDATE/DELETE với tần suất cao

Bảng trạng thái, event queue, session table hoặc bảng thống kê bị UPDATE liên tục có thể tạo nhiều dead tuple versions. Nếu vacuum không theo kịp, số dead tuples và dung lượng relation tăng.

### 5.2. UPDATE những cột có index

Nếu UPDATE thay đổi cột được index, HOT update thường không áp dụng cho index đó; PostgreSQL cần duy trì index entries phù hợp với phiên bản mới. Một workload cập nhật nhiều cột index có thể làm index churn tăng đáng kể.

### 5.3. Page splits của B-tree

Khi một B-tree leaf page không đủ chỗ cho insert mới, PostgreSQL có thể split page. Page splits là hành vi bình thường của B-tree, nhưng workload insert/update theo thứ tự ngẫu nhiên, key rộng hoặc page density cao có thể làm index tăng page count và phân mảnh.

### 5.4. Autovacuum không theo kịp

Nguyên nhân có thể:

- Scale factor quá cao với bảng rất lớn;
- Threshold chưa phù hợp;
- Autovacuum worker không đủ hoặc bị bận;
- Cost delay/budget khiến vacuum chạy chậm;
- Long-running transaction/replication horizon giữ dead tuples;
- Bảng bị ghi nhanh hơn tốc độ vacuum;
- Autovacuum bị disable ở table hoặc database;
- I/O/CPU/lock contention.

### 5.5. Long-running transaction và idle in transaction

Một session mở transaction lâu, kể cả đang `idle in transaction`, có thể giữ snapshot cũ và ngăn VACUUM thu hồi một số tuples. Một câu SELECT nhỏ trong transaction mở lâu cũng có thể kéo dài xmin horizon.

### 5.6. Replication slots và standby feedback

Replication slot giữ WAL và có thể giữ xmin/catalog_xmin để subscriber/consumer còn đọc được dữ liệu cần thiết. `hot_standby_feedback` từ standby cũng có thể giữ horizon, khiến primary không dọn một số dead tuples.

### 5.7. Fillfactor và workload không tương thích

Fillfactor quá cao có thể khiến page thiếu chỗ cho HOT updates. Fillfactor thấp có thể tạo nhiều free space hơn dự định và làm relation lớn hơn ngay từ đầu. Cần chọn theo tỷ lệ UPDATE/INSERT và kích thước row.

### 5.8. DELETE hàng loạt nhưng không rewrite

DELETE 90% rows không có nghĩa file table sẽ giảm 90% ngay sau commit. VACUUM thường giúp tái sử dụng page space; muốn file nhỏ lại rõ rệt cần rewrite relation theo phương án phù hợp.

### 5.9. Bulk import, batch churn và job chạy lại

Job import/ETL tạo nhiều UPDATE/DELETE lặp, upsert hàng loạt hoặc xóa rồi nạp lại có thể làm table/index churn lớn. Idempotency và batch design tốt giúp giảm thao tác ghi dư thừa.

### 5.10. Index không cần thiết

Mỗi index thêm dung lượng, WAL, chi phí INSERT/UPDATE/DELETE và công việc vacuum. Index dư thừa hoặc không được query dùng có thể làm storage tăng mà không đem lại lợi ích tương xứng.

### 5.11. Những gì không phải bloat

- Số hàng live tăng thật;
- Cột JSONB/text/bytea chứa dữ liệu lớn;
- Index mới được thêm vì query workload cần;
- Fillfactor thấp được chọn có chủ đích;
- Một bảng audit/event tăng theo retention policy;
- Một index có page density thấp vì workload và cấu trúc của loại index đó.

Đánh giá bloat phải đi cùng workload và business data, không chỉ nhìn một tỷ lệ.

## 6. VACUUM thường làm gì?

`VACUUM` là cơ chế bảo trì định kỳ để thu hồi các dead tuples không còn cần thiết và giữ relation khỏe mạnh cho MVCC. Nó không phải lệnh “nén mọi bảng thành file nhỏ nhất”.

### 6.1. Dọn dead tuples

Khi transaction horizon cho phép, VACUUM:

1. Tìm những tuple versions không còn cần thiết;
2. Làm sạch các references tương ứng trong indexes theo quy trình index cleanup;
3. Đánh dấu heap space có thể được tái sử dụng;
4. Cập nhật free space/visibility metadata phù hợp;
5. Thực hiện freeze công việc cần thiết để ngăn transaction ID wraparound theo chính sách vacuum.

### 6.2. VACUUM thường không rewrite toàn bảng

~~~sql
VACUUM copy411.contacts;
~~~

Lệnh thường dọn và đánh dấu space để PostgreSQL tái sử dụng trong relation. Nó không cần copy toàn bộ live rows sang một relation mới, nên thường ít disruptive hơn VACUUM FULL.

### 6.3. VACUUM có thể truncate page trống ở cuối

Trong một số trường hợp, VACUUM thường có thể truncate những empty pages nằm ở **cuối relation** và làm file nhỏ đi một phần. Tuy nhiên:

- Chỉ các trailing pages phù hợp mới được truncate;
- Free space ở giữa file thường vẫn được giữ lại để tái sử dụng;
- Việc truncate tail có thể cần lock mạnh trong một khoảng thời gian;
- Option `TRUNCATE` của VACUUM có thể điều khiển hành vi này theo version.

Do đó, không nên hứa rằng chạy VACUUM thường sẽ trả lại toàn bộ bloat cho filesystem.

### 6.4. VACUUM ANALYZE

~~~sql
VACUUM (ANALYZE) public.orders;
~~~

VACUUM dọn tuples; ANALYZE thu thập statistics cho planner (phân bố giá trị, selectivity, histogram/most-common values...). Hai việc bổ sung nhau:

- VACUUM hỗ trợ storage cleanup/MVCC;
- ANALYZE hỗ trợ planner chọn execution plan.

ANALYZE **không** tự dọn dead tuples hay thu nhỏ file.

### 6.5. VACUUM VERBOSE

~~~sql
VACUUM (VERBOSE, ANALYZE) public.orders;
~~~

`VERBOSE` cung cấp thông tin về số pages/tuples và công việc vacuum. Output phụ thuộc version và tình trạng bảng. Đây là nguồn chẩn đoán hữu ích, nhưng không thay phép đo bloat đầy đủ.

### 6.6. VACUUM không chạy trong transaction block

~~~sql
-- Không đặt VACUUM bên trong:
BEGIN;
VACUUM public.orders;
COMMIT;
~~~

Lệnh VACUUM thông thường không được chạy trong explicit transaction block. Một số công cụ migration tự bao câu lệnh trong transaction; khi chạy vacuum phải cấu hình tool phù hợp.

### 6.7. VACUUM và lock

VACUUM thường dùng lock cho phép nhiều hoạt động đọc/ghi bình thường tiếp tục, nhưng vẫn tương tác với workload và có thể bị chặn bởi một số DDL/lock khác. VACUUM không phải “không khóa gì”. Theo dõi progress, lock waits, I/O và workload khi chạy trên bảng lớn.

### 6.8. VACUUM không giải quyết mọi index bloat ngay lập tức

VACUUM làm index cleanup theo loại index và tùy tình huống. Với B-tree, các index pages có thể được tái sử dụng nhưng index file không nhất thiết co lại. Khi cần rebuild index để thu hồi page không hiệu quả, xem REINDEX.

### 6.9. INDEX_CLEANUP

VACUUM có option `INDEX_CLEANUP` (theo version) để kiểm soát việc làm sạch index entries. Chế độ AUTO có thể quyết định dựa trên mức độ dead tuples; OFF có thể giảm thời gian trong một số tình huống nhưng để lại index cleanup debt. **Không tắt index cleanup thường xuyên chỉ để vacuum nhanh hơn** mà không đánh giá hậu quả.

## 7. VACUUM FULL: rewrite relation để thu nhỏ file

`VACUUM FULL` xây dựng lại nội dung bảng, loại bỏ phần lớn free space/bloat và làm relation nhỏ hơn khi có thể.

~~~sql
VACUUM (FULL, ANALYZE) public.orders;
~~~

### 7.1. Cách hoạt động ở mức khái niệm

Thay vì chỉ đánh dấu page space có thể tái sử dụng, VACUUM FULL **rewrite relation** sang một bản vật lý gọn hơn, sau đó thay relation cũ bằng bản mới theo quy trình PostgreSQL.

### 7.2. Ưu điểm

- Có thể thu hồi đáng kể disk space của heap table;
- Xây lại layout relation gọn hơn;
- Có thể cải thiện locality/scan khi bảng trước đó bị phân mảnh nghiêm trọng;
- Giảm số pages cần đọc khi bloat thực sự lớn.

### 7.3. Nhược điểm quan trọng

- Cần **ACCESS EXCLUSIVE lock** trên bảng trong quá trình thực hiện;
- Các truy vấn và thao tác khác trên bảng có thể phải chờ;
- Cần disk tạm đủ cho bản rewrite và các cấu trúc liên quan;
- Tốn I/O/CPU, có thể tạo WAL và ảnh hưởng replication/backup;
- Không phù hợp chạy tùy tiện trên bảng lớn đang phục vụ workload quan trọng.

### 7.4. VACUUM FULL không phải lựa chọn autovacuum

Autovacuum thực hiện vacuum thường; nó **không tự chạy VACUUM FULL** để thu nhỏ mọi bảng. Đây là chủ đích vì FULL cần lock mạnh và rewrite relation.

### 7.5. Không chạy FULL chỉ vì n_dead_tup cao

`n_dead_tup` là estimate; nhiều dead tuples có thể được VACUUM thường dọn và tái sử dụng. Trước khi chọn FULL, cần xác định:

1. Dead tuples có thực sự còn nhiều sau vacuum không?
2. Relation size có lớn hơn nhu cầu live data rõ rệt không?
3. Space có được tái sử dụng cho workload kế tiếp không?
4. Có long transaction giữ horizon không?
5. Có đủ disk tạm và lock window không?

### 7.6. Khi nào cân nhắc?

- Bảng đã xóa lượng lớn dữ liệu và cần trả disk về filesystem;
- Bloat lớn đã được xác nhận bằng đo đạc;
- Có maintenance window/khả năng chặn truy cập;
- Đã xác minh đủ dung lượng để rewrite và backup/recovery plan.

## 8. CLUSTER: rewrite và sắp xếp theo index

`CLUSTER` viết lại một bảng theo thứ tự của index được chỉ định:

~~~sql
CLUSTER public.orders USING orders_created_at_idx;
~~~

### 8.1. CLUSTER làm gì?

- Rewrite table theo thứ tự index;
- Xây lại indexes của table theo quy trình;
- Có thể cải thiện locality khi query thường đọc các rows gần nhau theo key đã cluster;
- Thu hồi free space/bloat trong heap bằng cách tạo layout mới.

### 8.2. CLUSTER không duy trì thứ tự vĩnh viễn

Sau CLUSTER, các INSERT/UPDATE mới có thể làm thứ tự vật lý lệch dần. PostgreSQL không tự giữ bảng luôn theo index order cho mọi lần ghi tiếp theo.

### 8.3. Lock và disk

CLUSTER cần lock mạnh (ACCESS EXCLUSIVE) và disk tạm cho rewrite. Lập kế hoạch như một thao tác bảo trì lớn, không coi nó là lệnh tối ưu index nhẹ.

### 8.4. CLUSTER vs VACUUM FULL

| Tiêu chí | VACUUM FULL | CLUSTER |
| --- | --- | --- |
| Rewrite heap | Có | Có |
| Sắp xếp theo index | Không phải mục tiêu | Có |
| Thu hồi heap bloat | Có | Có |
| Rebuild indexes | Có theo quy trình rewrite | Có |
| Lock mạnh | Có | Có |
| Giữ thứ tự lâu dài | Không bảo đảm | Không bảo đảm sau DML tiếp theo |

Chọn CLUSTER khi **thứ tự vật lý theo một index** có giá trị cho workload, không chỉ vì muốn làm nhỏ file.

## 9. pg_repack: rewrite online hơn, nhưng không miễn phí

`pg_repack` là extension/tool bên ngoài core PostgreSQL, được dùng để rebuild table/index với mục tiêu giảm thời gian khóa đọc/ghi so với VACUUM FULL hoặc CLUSTER trong những tình huống phù hợp.

### 9.1. Mô hình hoạt động khái quát

pg_repack thường:

1. Tạo cấu trúc bảng mới có layout mong muốn;
2. Copy dữ liệu;
3. Theo dõi/áp dụng các thay đổi phát sinh trong lúc copy;
4. Hoán đổi cấu trúc ở giai đoạn cuối với lock ngắn hơn nếu điều kiện thuận lợi.

Chi tiết phụ thuộc phiên bản extension và cách chạy.

### 9.2. Không có nghĩa zero-lock

pg_repack vẫn cần lock ở một số giai đoạn, cần quyền và prerequisites, có thể bị chặn bởi long-running transactions/DDL, và cần đủ disk tạm cho cả cấu trúc cũ/mới. Không tuyên bố “online hoàn toàn, không bao giờ block”.

### 9.3. Điều kiện cần kiểm tra

- Version pg_repack tương thích với server;
- Extension đã được cài đặt/được DBA cho phép;
- Bảng có primary key hoặc unique index phù hợp theo yêu cầu của tool/version;
- Quyền sở hữu và quyền tạo objects phù hợp;
- Có disk headroom, WAL/replication budget;
- Lock window và workload được theo dõi;
- Có backup/rollback/recovery plan.

### 9.4. Khi nào cân nhắc?

Khi đã xác nhận bloat đáng kể, cần rewrite table/index nhưng không thể chấp nhận thời gian ACCESS EXCLUSIVE lock dài như VACUUM FULL. Đánh giá bằng tài liệu chính thức của extension và staging test trước.

### 9.5. pg_repack không thay autovacuum

Rewrite là biện pháp xử lý hậu quả. Nếu workload, autovacuum, long snapshots và index design không thay đổi, bloat có thể quay trở lại.

## 10. REINDEX: xử lý bloat trong chỉ mục

`REINDEX` xây lại index từ dữ liệu của bảng/partition tương ứng. Nó thường là cách trực tiếp để thu hồi bloat trong một index đã được xác nhận.

### 10.1. Reindex một index

~~~sql
REINDEX INDEX public.orders_customer_id_idx;
~~~

Lệnh không concurrent có thể chặn hoạt động ghi/đọc liên quan theo lock semantics của REINDEX; phải kiểm tra version và lock behavior.

### 10.2. REINDEX TABLE

~~~sql
REINDEX TABLE public.orders;
~~~

Lệnh này rebuild các indexes của bảng; nó **không phải** thao tác rewrite heap table giống VACUUM FULL. Nếu bloat chủ yếu nằm trong heap, chỉ REINDEX không giải quyết heap bloat.

### 10.3. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_customer_id_idx;
~~~

Trong các phiên bản hỗ trợ, `CONCURRENTLY` giảm mức độ chặn INSERT/UPDATE/DELETE trong phần lớn quá trình rebuild bằng cách tạo index mới, đồng bộ thay đổi và swap khi phù hợp. Tuy nhiên:

- Vẫn có các giai đoạn cần lock;
- Có thể chờ transaction/snapshot cũ;
- Cần disk tạm cho index cũ và mới cùng tồn tại;
- Tốn CPU/I/O và WAL;
- Có thể thất bại để lại index invalid cần xử lý;
- Không được chạy trong transaction block.

### 10.4. Reindex không phải VACUUM

| Lệnh | Mục tiêu chính |
| --- | --- |
| VACUUM | Dọn dead tuples và làm không gian có thể tái sử dụng |
| VACUUM FULL | Rewrite heap để thu nhỏ relation |
| REINDEX | Rebuild index |
| REINDEX CONCURRENTLY | Rebuild index với ít chặn DML hơn theo quy trình concurrent |
| CLUSTER | Rewrite heap theo thứ tự index |

### 10.5. Reindex khi nào?

- B-tree index được đo thấy page density/size bất thường sau churn lớn;
- Index bị invalid/corrupt theo quy trình xử lý được hướng dẫn;
- Cần thu hồi index space mà vacuum cleanup không làm file nhỏ lại;
- Có bằng chứng index là nguồn storage/latency đáng kể.

Không reindex tất cả indexes theo lịch tùy tiện: rebuild tốn I/O/WAL, disk tạm và có thể ảnh hưởng production.

## 11. HOT update và fillfactor

**HOT (Heap-Only Tuple)** giảm chi phí khi UPDATE một row bằng cách tránh tạo index entries mới trong những điều kiện phù hợp. Đây là một cơ chế quan trọng để hạn chế index bloat ở các bảng có workload UPDATE.

### 11.1. Điều kiện HOT

Một UPDATE có thể là HOT khi:

- Những cột có liên quan tới các indexes của bảng không bị thay đổi (bao gồm cột dùng trong expression/predicate của index);
- Phiên bản tuple mới có thể được đặt trên cùng heap page với phiên bản cũ;
- Những điều kiện HOT khác theo loại index và implementation được đáp ứng.

Nếu UPDATE thay đổi một cột được index, PostgreSQL thường phải tạo index entries mới cho tuple version mới.

### 11.2. Vì sao fillfactor liên quan HOT?

Nếu heap page được lấp đầy gần như tối đa, khi UPDATE cần tạo tuple version mới có thể không còn chỗ trên page cũ. HOT không thực hiện được dù không thay cột index. Đặt table fillfactor thấp hơn 100 có thể chừa chỗ cho các updates tại chỗ.

### 11.3. Table fillfactor

~~~sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    status text NOT NULL,
    updated_at timestamptz NOT NULL
)
WITH (fillfactor = 80);
~~~

Fillfactor 80 là ví dụ: PostgreSQL cố gắng để heap pages khoảng 80% đầy khi tạo/ghi theo quy tắc fillfactor, để dành chỗ cho updates. Đây không phải cam kết mọi page luôn chính xác 20% free.

### 11.4. Thay fillfactor của bảng đã tồn tại

~~~sql
ALTER TABLE public.orders
SET (fillfactor = 80);
~~~

Lệnh này thay storage parameter cho **những page/tuple được tạo hoặc ghi sau đó**; nó không tự rewrite toàn bộ table hiện có để áp dụng layout mới. Nếu cần áp dụng tới các page hiện hữu, cần một thao tác rewrite phù hợp và phải lập kế hoạch lock/disk.

### 11.5. Fillfactor thấp không luôn tốt

- Bảng append-only ít UPDATE có thể không cần chừa nhiều chỗ;
- Fillfactor thấp làm relation ban đầu lớn hơn và giảm mật độ scan;
- Row lớn có thể chiếm nhiều page hơn;
- Nếu UPDATE thường thay cột indexed, giảm fillfactor không tự làm HOT update được;
- Chọn quá thấp có thể làm tăng storage/IO không cần thiết.

### 11.6. Index fillfactor

B-tree index cũng có fillfactor, thường mặc định 90. Có thể cấu hình:

~~~sql
CREATE INDEX orders_customer_idx
ON public.orders(customer_id)
WITH (fillfactor = 80);

ALTER INDEX public.orders_customer_idx
SET (fillfactor = 80);
~~~

Index fillfactor điều khiển mức lấp đầy của leaf pages theo quy tắc xây dựng/split. Giá trị thấp hơn có thể giúp index workload có nhiều insert ngẫu nhiên hạn chế split ở một số tình huống, nhưng tăng số pages và storage.

### 11.7. ALTER INDEX không tự rebuild toàn bộ index

Thay fillfactor không tự sắp xếp lại những page hiện có theo một mật độ mới. Nếu mục tiêu là áp dụng fillfactor lên toàn bộ index, cần đánh giá REINDEX (có thể concurrent nếu phiên bản hỗ trợ).

### 11.8. Theo dõi HOT ratio

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    round(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_stat_user_tables
WHERE n_tup_upd > 0
ORDER BY n_tup_upd DESC;
~~~

HOT ratio cao có thể cho thấy workload UPDATE tận dụng được HOT; ratio thấp cần phân tích cột update, index definitions, row size và free space. **Không có một ngưỡng HOT ratio chung cho mọi bảng**.

### 11.9. HOT không loại bỏ heap bloat

HOT giảm index churn nhưng vẫn tạo tuple version mới trong heap. VACUUM vẫn cần prune/clean những tuple versions không còn cần thiết. HOT là một cách giảm chi phí, không phải thay thế VACUUM.

## 12. Autovacuum: cơ chế duy trì tự động

PostgreSQL có **autovacuum launcher** và các worker tự động chạy VACUUM/ANALYZE khi bảng đạt ngưỡng cấu hình. Với phần lớn hệ thống, giữ autovacuum bật và điều chỉnh theo workload là nền tảng để kiểm soát bloat.

### 12.1. Hai việc autovacuum làm

- **Auto-vacuum:** dọn dead tuples, cập nhật visibility/freeze metadata;
- **Auto-analyze:** thu thập statistics cho planner khi dữ liệu thay đổi đủ nhiều.

Một bảng có thể cần VACUUM và ANALYZE ở các thời điểm khác nhau.

### 12.2. Ngưỡng vacuum dựa trên threshold và scale factor

Với UPDATE/DELETE, ngưỡng kích hoạt thường được mô tả khái quát:

~~~text
vacuum threshold
  = autovacuum_vacuum_threshold
  + autovacuum_vacuum_scale_factor * estimated_table_tuples
~~~

Các giá trị mặc định phổ biến trong PostgreSQL là threshold 50 và scale factor 0.2, nhưng **hãy kiểm tra version/config thực tế**. Một bảng 100 triệu rows với scale factor 0.2 có thể cần khoảng 20 triệu tuple changes (cộng threshold) trước khi đạt ngưỡng dựa trên công thức này.

### 12.3. Vì sao scale factor mặc định có thể quá cao?

Với bảng rất lớn, một tỷ lệ 20% tương ứng số rows khổng lồ. Autovacuum có thể chỉ chạy khi dead tuples đã tích tụ nhiều, dẫn đến table/index bloat và vacuum workload lớn.

### 12.4. Ngưỡng analyze

~~~text
analyze threshold
  = autovacuum_analyze_threshold
  + autovacuum_analyze_scale_factor * estimated_table_tuples
~~~

Statistics cũ có thể làm planner chọn plan kém dù vacuum đã dọn dead tuples. `ANALYZE` là công việc riêng cần theo dõi.

### 12.5. Ngưỡng vacuum do INSERT

PostgreSQL hiện đại còn có `autovacuum_vacuum_insert_threshold` và `autovacuum_vacuum_insert_scale_factor` để vacuum các bảng append-heavy, hỗ trợ cập nhật visibility map và freeze tuples. Cơ chế insert-triggered vacuum không giống hoàn toàn ngưỡng UPDATE/DELETE.

### 12.6. Xem cấu hình hiện tại

~~~sql
SHOW autovacuum;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_max_workers;
SHOW autovacuum_naptime;
SHOW autovacuum_vacuum_cost_limit;
SHOW autovacuum_vacuum_cost_delay;
~~~

Một số GUC hoặc default có thể khác theo major version và cấu hình managed service. Dùng `SHOW`/`pg_settings` thay vì ghi nhớ một con số cố định.

### 12.7. Điều chỉnh per-table

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

Đây là ví dụ cho bảng lớn, thay đổi thường xuyên; không phải cấu hình tối ưu chung. Với bảng nhỏ, threshold tuyệt đối và scale factor khác có thể hợp lý.

### 12.8. Per-table settings có thể xem lại

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND c.reloptions IS NOT NULL
ORDER BY n.nspname, c.relname;
~~~

`reloptions` chứa storage parameters của relation, bao gồm fillfactor và các autovacuum options nếu được đặt.

### 12.9. Autovacuum workers

`autovacuum_max_workers` giới hạn số worker autovacuum chạy đồng thời. Tăng workers có thể giúp nhiều bảng được vacuum song song, nhưng cũng tăng cạnh tranh CPU/I/O. Nếu bottleneck là disk throughput, thêm worker không nhất thiết làm tổng vacuum nhanh hơn.

### 12.10. Cost-based delay

Autovacuum có cơ chế cost-based vacuum delay/limit để cân bằng bảo trì với workload. Nếu vacuum chạy quá chậm, xem:

- Cost limit/delay global và per-table;
- I/O saturation;
- Số worker và bảng đủ điều kiện;
- Long transactions/replication horizon;
- Kích thước và tốc độ thay đổi của từng bảng.

Không đơn giản tăng cost limit lên mức rất cao mà không đo tác động tới latency ứng dụng.

### 12.11. Autovacuum không thay thế VACUUM FULL

Autovacuum giữ relation sạch và space có thể tái sử dụng. Nó không rewrite mọi bảng để thu nhỏ file về mức tối thiểu. Nếu cần trả lại disk cho filesystem, phải chọn phương pháp rewrite có kiểm soát.

### 12.12. Không disable autovacuum như cách trị bloat

~~~sql
-- Không dùng như giải pháp thường trực:
ALTER TABLE public.orders
SET (autovacuum_enabled = false);
~~~

Disable autovacuum có thể làm dead tuples tích tụ, tăng bloat và rủi ro transaction ID wraparound. Chỉ dùng trong tình huống chuyên biệt, có người vận hành theo dõi và kế hoạch VACUUM thủ công được xác định rõ.

## 13. Vacuum freeze và transaction ID wraparound

VACUUM không chỉ dọn bloat. Nó còn đóng vai trò **freeze tuples** để transaction ID cũ không bị diễn giải sai sau khi counter wraparound.

### 13.1. Vì sao freeze quan trọng?

PostgreSQL dùng transaction IDs hữu hạn. Khi tuổi transaction quá lớn, database phải bảo đảm các tuples cũ được đánh dấu frozen hoặc xử lý theo cơ chế chống wraparound trước khi những IDs có thể bị tái sử dụng.

### 13.2. Anti-wraparound autovacuum

Kể cả khi một bảng không có nhiều dead tuples, PostgreSQL vẫn có thể cần vacuum để freeze. Anti-wraparound vacuum là bảo vệ tính đúng đắn của database, không chỉ là tối ưu storage.

### 13.3. Kiểm tra age(relfrozenxid)

~~~sql
SELECT
    n.nspname,
    c.relname,
    age(c.relfrozenxid) AS xid_age,
    c.relfrozenxid
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY xid_age DESC
LIMIT 30;
~~~

Đây là một chỉ báo để xác định bảng có XID age lớn. Cần kết hợp với database-level age, cấu hình freeze và thông tin autovacuum; không tự kết luận database sắp wraparound chỉ từ một hàng.

### 13.4. Kiểm tra giới hạn freeze

~~~sql
SHOW autovacuum_freeze_max_age;
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
~~~

Đây là các tham số ảnh hưởng khi VACUUM freeze. Thay đổi chúng tùy tiện có thể làm tăng công việc freeze hoặc đẩy rủi ro gần wraparound hơn.

### 13.5. VACUUM FREEZE không đồng nghĩa compact

~~~sql
VACUUM (FREEZE, VERBOSE) public.orders;
~~~

FREEZE giúp xử lý transaction metadata; nó không phải lệnh rewrite relation để loại bỏ bloat. Nếu mục tiêu là shrink file, cần đánh giá FULL/CLUSTER/pg_repack riêng.

### 13.6. Không trì hoãn anti-wraparound vacuum

Khi database tiến gần giới hạn an toàn, PostgreSQL có thể ưu tiên vacuum khẩn cấp và từ chối một số writes để bảo vệ dữ liệu. Đây là sự cố nghiêm trọng; xử lý theo tài liệu/version và runbook DBA, không chỉ tăng ngưỡng freeze để tránh log cảnh báo.

## 14. Đo kích thước bảng, index và TOAST

Trước khi sửa bloat, cần xác định dung lượng đang nằm ở đâu. PostgreSQL cung cấp các hàm size:

| Hàm | Ý nghĩa |
| --- | --- |
| `pg_relation_size(relation)` | Kích thước fork mặc định (main fork) của relation |
| `pg_table_size(relation)` | Dung lượng table gồm heap, TOAST và các thành phần liên quan, không gồm indexes |
| `pg_indexes_size(relation)` | Tổng kích thước indexes của table |
| `pg_total_relation_size(relation)` | Tổng table + indexes + TOAST |
| `pg_size_pretty(bytes)` | Hiển thị bytes ở dạng dễ đọc |

### 14.1. Bảng lớn nhất theo tổng dung lượng

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_table_size(relid)) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

Query này cho biết dung lượng vật lý, **không tự kết luận bloat**. Bảng có index nhiều hoặc TOAST lớn có thể total size cao vì dữ liệu thật.

### 14.2. Kích thước từng index

~~~sql
SELECT
    ns.nspname AS schemaname,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_get_indexdef(idx.oid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(idx.oid) DESC
LIMIT 50;
~~~

Đây là cách tìm những index tiêu tốn nhiều disk. Kích thước lớn không đồng nghĩa index thừa hoặc bloat; đối chiếu query workload và số rows/distinct values.

### 14.3. Kiểm tra tỷ trọng heap/index/TOAST

~~~sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS main_heap,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
    pg_size_pretty(pg_table_size(c.oid)
                   - pg_relation_size(c.oid)) AS toast_and_aux,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.relpersistence = 'p'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 30;
~~~

`pg_table_size` đã gồm TOAST và auxiliary forks, nên phép trừ trên không phải một phép đo TOAST chính xác. Để đo riêng TOAST, cần truy vấn relation được tham chiếu qua `pg_class.reltoastrelid`.

### 14.4. Đo TOAST riêng

~~~sql
SELECT
    c.oid::regclass AS table_name,
    NULLIF(c.reltoastrelid, 0)::regclass AS toast_relation,
    CASE
        WHEN c.reltoastrelid <> 0
        THEN pg_size_pretty(pg_total_relation_size(c.reltoastrelid))
    END AS toast_total_size
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.reltoastrelid <> 0
ORDER BY pg_total_relation_size(c.reltoastrelid) DESC;
~~~

TOAST table có thể lớn khi row chứa nhiều giá trị lớn. Cần xác định đó là dữ liệu cần giữ hay các phiên bản cũ của giá trị đã thay đổi.

## 15. Thống kê dead tuples và vacuum

View `pg_stat_user_tables` cung cấp các estimates/counters để theo dõi table activity.

### 15.1. Bảng nào có nhiều dead tuples?

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_percent,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

`n_live_tup` và `n_dead_tup` là **ước lượng**, không phải số đếm chính xác tại mọi thời điểm. Tỷ lệ dead cao là tín hiệu điều tra, không phải bằng chứng đủ để chạy VACUUM FULL.

### 15.2. Theo dõi tốc độ thay đổi

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY (n_tup_upd + n_tup_del) DESC
LIMIT 30;
~~~

Counters có thể reset và phản ánh activity từ lần reset gần nhất; hãy ghi snapshot theo thời gian nếu muốn biết tốc độ thay đổi mỗi giờ/ngày.

### 15.3. Index usage statistics

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

`idx_scan` thấp có thể gợi ý index ít được sử dụng, nhưng cần xem thời gian thống kê, workload theo mùa, constraints và query plans. **Không DROP index chỉ vì idx_scan=0 trong một cửa sổ ngắn**: index có thể bảo vệ UNIQUE/FK hoặc được dùng theo lịch.

### 15.4. Theo dõi vacuum đang chạy

~~~sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY p.pid;
~~~

Các progress columns phản ánh giai đoạn/công việc vacuum; một số giá trị có thể không áp dụng ở mọi phase. Nếu không có row, có thể không có vacuum đang chạy tại thời điểm truy vấn.

### 15.5. Vacuum progress không đồng nghĩa phần trăm bloat còn lại

`heap_blks_scanned / heap_blks_total` mô tả tiến độ scan trong công việc hiện tại, không phải tỷ lệ bloat đã được loại bỏ. Không dùng nó để dự đoán chắc chắn thời gian hoàn tất hoặc disk space sẽ thu hồi.

### 15.6. Kiểm tra ANALYZE cũ

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 30;
~~~

Statistics stale có thể làm query plan kém, dẫn tới đọc nhiều pages hơn hoặc chọn index không phù hợp. Đây là vấn đề planner statistics, khác bloat vật lý dù có thể cùng xuất hiện.

## 16. Long transactions và replication horizon

VACUUM chỉ dọn những tuple versions mà không còn snapshot/transaction nào cần nhìn thấy. Vì vậy phải tìm **ai đang giữ xmin horizon** khi dead tuples không giảm sau vacuum.

### 16.1. Tìm transaction chạy lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Chú ý các session `idle in transaction`. Chúng có thể giữ transaction snapshot dù không còn query đang chạy.

### 16.2. Snapshot lâu không nhất thiết query lâu

~~~sql
BEGIN;
SELECT COUNT(*) FROM public.orders;
-- ứng dụng giữ connection mở hàng giờ
~~~

có thể giữ snapshot trong thời gian dài. VACUUM có thể không dọn các versions mà snapshot ấy còn cần. Cần xem transaction lifecycle và connection pool behavior.

### 16.3. Replication slots

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE WHEN catalog_xmin IS NOT NULL
         THEN age(catalog_xmin) END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Slot inactive lâu có thể giữ WAL và transaction horizon. **Không DROP replication slot để giải quyết bloat một cách tùy tiện**: consumer có thể mất khả năng tiếp tục replication và phải resync/reinitialize.

### 16.4. Standby feedback

~~~sql
SHOW hot_standby_feedback;
~~~

Khi standby gửi feedback về primary, xmin horizon có thể được giữ lại để tránh conflict trên standby. Điều này giảm một số query conflicts nhưng có thể làm primary tích tụ dead tuples/bloat.

### 16.5. Prepared transactions

~~~sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Prepared transactions bị bỏ quên có thể giữ resources/transaction state. Không tự `ROLLBACK PREPARED` nếu chưa xác định coordinator và nghiệp vụ giao dịch hai pha; cần phối hợp với chủ hệ thống.

### 16.6. Giải quyết nguyên nhân trước khi chạy thêm VACUUM

Nếu snapshot cũ vẫn giữ tuples, chạy VACUUM lặp lại thường không thể thu hồi phần đang bị giữ. Xác định session/slot/prepared transaction, hiểu tác động rồi xử lý theo quy trình ứng dụng/replication. Sau khi horizon tiến lên, vacuum mới có thể dọn.

## 14. Đo kích thước bảng, index và TOAST

Trước khi sửa bloat, cần xác định dung lượng đang nằm ở đâu. PostgreSQL cung cấp các hàm size:

| Hàm | Ý nghĩa |
| --- | --- |
| `pg_relation_size(relation)` | Kích thước fork mặc định (main fork) của relation |
| `pg_table_size(relation)` | Dung lượng table gồm heap, TOAST và các thành phần liên quan, không gồm indexes |
| `pg_indexes_size(relation)` | Tổng kích thước indexes của table |
| `pg_total_relation_size(relation)` | Tổng table + indexes + TOAST |
| `pg_size_pretty(bytes)` | Hiển thị bytes ở dạng dễ đọc |

### 14.1. Bảng lớn nhất theo tổng dung lượng

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_table_size(relid)) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

Query này cho biết dung lượng vật lý, **không tự kết luận bloat**. Bảng có index nhiều hoặc TOAST lớn có thể total size cao vì dữ liệu thật.

### 14.2. Kích thước từng index

~~~sql
SELECT
    ns.nspname AS schemaname,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_get_indexdef(idx.oid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(idx.oid) DESC
LIMIT 50;
~~~

Đây là cách tìm những index tiêu tốn nhiều disk. Kích thước lớn không đồng nghĩa index thừa hoặc bloat; đối chiếu query workload và số rows/distinct values.

### 14.3. Kiểm tra tỷ trọng heap/index/TOAST

~~~sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS main_heap,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
    pg_size_pretty(pg_total_relation_size(c.oid)
                   - pg_table_size(c.oid)) AS toast_and_aux,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.relpersistence = 'p'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 30;
~~~

`pg_table_size` đã gồm TOAST và auxiliary forks, nên phép trừ trên không phải một phép đo TOAST chính xác. Để đo riêng TOAST, cần truy vấn relation được tham chiếu qua `pg_class.reltoastrelid`.

### 14.4. Đo TOAST riêng

~~~sql
SELECT
    c.oid::regclass AS table_name,
    NULLIF(c.reltoastrelid, 0)::regclass AS toast_relation,
    CASE
        WHEN c.reltoastrelid <> 0
        THEN pg_size_pretty(pg_total_relation_size(c.reltoastrelid))
    END AS toast_total_size
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.reltoastrelid <> 0
ORDER BY pg_total_relation_size(c.reltoastrelid) DESC;
~~~

TOAST table có thể lớn khi row chứa nhiều giá trị lớn. Cần xác định đó là dữ liệu cần giữ hay các phiên bản cũ của giá trị đã thay đổi.

## 15. Thống kê dead tuples và vacuum

View `pg_stat_user_tables` cung cấp các estimates/counters để theo dõi table activity.

### 15.1. Bảng nào có nhiều dead tuples?

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_percent,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

`n_live_tup` và `n_dead_tup` là **ước lượng**, không phải số đếm chính xác tại mọi thời điểm. Tỷ lệ dead cao là tín hiệu điều tra, không phải bằng chứng đủ để chạy VACUUM FULL.

### 15.2. Theo dõi tốc độ thay đổi

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY (n_tup_upd + n_tup_del) DESC
LIMIT 30;
~~~

Counters có thể reset và phản ánh activity từ lần reset gần nhất; hãy ghi snapshot theo thời gian nếu muốn biết tốc độ thay đổi mỗi giờ/ngày.

### 15.3. Index usage statistics

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

`idx_scan` thấp có thể gợi ý index ít được sử dụng, nhưng cần xem thời gian thống kê, workload theo mùa, constraints và query plans. **Không DROP index chỉ vì idx_scan=0 trong một cửa sổ ngắn**: index có thể bảo vệ UNIQUE/FK hoặc được dùng theo lịch.

### 15.4. Theo dõi vacuum đang chạy

~~~sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY p.pid;
~~~

Các progress columns phản ánh giai đoạn/công việc vacuum; một số giá trị có thể không áp dụng ở mọi phase. Nếu không có row, có thể không có vacuum đang chạy tại thời điểm truy vấn.

### 15.5. Vacuum progress không đồng nghĩa phần trăm bloat còn lại

`heap_blks_scanned / heap_blks_total` mô tả tiến độ scan trong công việc hiện tại, không phải tỷ lệ bloat đã được loại bỏ. Không dùng nó để dự đoán chắc chắn thời gian hoàn tất hoặc disk space sẽ thu hồi.

### 15.6. Kiểm tra ANALYZE cũ

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 30;
~~~

Statistics stale có thể làm query plan kém, dẫn tới đọc nhiều pages hơn hoặc chọn index không phù hợp. Đây là vấn đề planner statistics, khác bloat vật lý dù có thể cùng xuất hiện.

## 16. Long transactions và replication horizon

VACUUM chỉ dọn những tuple versions mà không còn snapshot/transaction nào cần nhìn thấy. Vì vậy phải tìm **ai đang giữ xmin horizon** khi dead tuples không giảm sau vacuum.

### 16.1. Tìm transaction chạy lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Chú ý các session `idle in transaction`. Chúng có thể giữ transaction snapshot dù không còn query đang chạy.

### 16.2. Snapshot lâu không nhất thiết query lâu

~~~sql
BEGIN;
SELECT COUNT(*) FROM public.orders;
-- ứng dụng giữ connection mở hàng giờ
~~~

có thể giữ snapshot trong thời gian dài. VACUUM có thể không dọn các versions mà snapshot ấy còn cần. Cần xem transaction lifecycle và connection pool behavior.

### 16.3. Replication slots

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE WHEN catalog_xmin IS NOT NULL
         THEN age(catalog_xmin) END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Slot inactive lâu có thể giữ WAL và transaction horizon. **Không DROP replication slot để giải quyết bloat một cách tùy tiện**: consumer có thể mất khả năng tiếp tục replication và phải resync/reinitialize.

### 16.4. Standby feedback

~~~sql
SHOW hot_standby_feedback;
~~~

Khi standby gửi feedback về primary, xmin horizon có thể được giữ lại để tránh conflict trên standby. Điều này giảm một số query conflicts nhưng có thể làm primary tích tụ dead tuples/bloat.

### 16.5. Prepared transactions

~~~sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Prepared transactions bị bỏ quên có thể giữ resources/transaction state. Không tự `ROLLBACK PREPARED` nếu chưa xác định coordinator và nghiệp vụ giao dịch hai pha; cần phối hợp với chủ hệ thống.

### 16.6. Giải quyết nguyên nhân trước khi chạy thêm VACUUM

Nếu snapshot cũ vẫn giữ tuples, chạy VACUUM lặp lại thường không thể thu hồi phần đang bị giữ. Xác định session/slot/prepared transaction, hiểu tác động rồi xử lý theo quy trình ứng dụng/replication. Sau khi horizon tiến lên, vacuum mới có thể dọn.

## 17. Đo live/dead/free space bằng pgstattuple

Các statistics trong `pg_stat_user_tables` là estimates. Khi cần đo sâu hơn, PostgreSQL có extension **`pgstattuple`** (thường thuộc bộ contrib).

### 17.1. Cài extension trong database lab

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
~~~

Việc cài extension phụ thuộc package/server image và quyền của role. Một managed service có thể yêu cầu thao tác qua DBA hoặc allowlist extension. Không giả định extension đã có sẵn trên mọi PostgreSQL instance.

### 17.2. Đo một table

~~~sql
SELECT *
FROM pgstattuple('public.orders'::regclass);
~~~

Kết quả thường có:

| Field | Ý nghĩa |
| --- | --- |
| `table_len` | Kích thước relation được quét |
| `tuple_count` | Số live tuples được đếm |
| `tuple_len` | Tổng bytes của live tuple data |
| `tuple_percent` | Tỷ lệ bytes live tuples |
| `dead_tuple_count` | Số dead tuples |
| `dead_tuple_len` | Tổng bytes dead tuples |
| `dead_tuple_percent` | Tỷ lệ bytes dead tuples |
| `free_space` | Tổng free space trong relation |
| `free_percent` | Tỷ lệ free space |

### 17.3. Ví dụ đọc kết quả

Giả sử output minh họa:

| Metric | Giá trị giả định |
| --- | ---: |
| table_len | 1.000 MB |
| tuple_len | 550 MB |
| dead_tuple_len | 150 MB |
| free_space | 220 MB |
| overhead/other | 80 MB |

Không thể nói “bloat chính xác bằng 450 MB” mà không xét page layout, alignment, line pointers, index/TOAST, fillfactor và khả năng tái sử dụng. Nhưng số liệu gợi ý relation có nhiều bytes không chứa live tuple data và đáng được điều tra.

### 17.4. pgstattuple_approx

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders'::regclass);
~~~

Hàm approximate có thể tận dụng visibility map để bỏ qua một số pages all-visible, giảm chi phí so với full scan. Nó trả các trường như:

- `table_len`, `scanned_percent`;
- `approx_tuple_count`, `approx_tuple_len`, `approx_tuple_percent`;
- `dead_tuple_count`, `dead_tuple_len`, `dead_tuple_percent`;
- `approx_free_space`, `approx_free_percent`.

Kết quả là **ước lượng**; không so trực tiếp một cách máy móc với số liệu exact khi snapshot/workload đã thay đổi.

### 17.5. Đo một B-tree index

~~~sql
SELECT *
FROM pgstatindex('public.orders_customer_id_idx'::regclass);
~~~

Các chỉ số thường gồm:

| Field | Ý nghĩa |
| --- | --- |
| `tree_level` | Chiều cao B-tree |
| `index_size` | Kích thước index |
| `internal_pages` | Số internal pages |
| `leaf_pages` | Số leaf pages |
| `empty_pages` | Số empty pages |
| `deleted_pages` | Số deleted pages |
| `avg_leaf_density` | Mật độ trung bình leaf pages |
| `leaf_fragmentation` | Chỉ số phân mảnh leaf page theo định nghĩa extension |

`pgstatindex` áp dụng cho **B-tree**. Không dùng output này để kết luận bloat của GIN/GiST/BRIN/hash indexes.

### 17.6. Density thấp không tự động chứng minh bloat

Leaf density thấp có thể do:

- Index fillfactor được đặt thấp có chủ đích;
- Index vừa được xây lại với fillfactor;
- Workload random inserts và page splits;
- Nhiều delete/update;
- Đặc tính key và kích thước tuple.

So sánh với thiết kế fillfactor, workload và lịch sử. Một index có density 70% có thể hoàn toàn hợp lý cho workload insert/update ngẫu nhiên.

### 17.7. Chi phí của pgstattuple

`pgstattuple` có thể scan toàn relation; `pgstatindex` cũng cần đọc cấu trúc index. Trên bảng/index hàng trăm GB, đây là công việc I/O đáng kể. Dùng `pgstattuple_approx` khi phù hợp, chọn thời điểm và theo dõi impact.

### 17.8. Không chạy liên tục để theo dõi realtime

Extension đo sâu thích hợp cho **điều tra/đối chiếu theo đợt**, không nhất thiết chạy mỗi phút trên mọi bảng. Dùng stats views nhẹ hơn để theo dõi xu hướng, rồi chọn một số relations đáng nghi để đo sâu.

## 18. Ước lượng bloat: các giới hạn cần hiểu

Có nhiều công thức SQL trên internet dùng `pg_class.reltuples`, `relpages`, data types, page size và fillfactor để ước lượng expected pages. Những công thức này có ích để sàng lọc, nhưng có giả định.

### 18.1. reltuples và relpages là estimates

~~~sql
SELECT
    c.oid::regclass AS relation,
    c.reltuples,
    c.relpages,
    pg_relation_size(c.oid) AS relation_bytes,
    current_setting('block_size')::integer AS block_size
FROM pg_class AS c
WHERE c.relkind = 'r'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_relation_size(c.oid) DESC;
~~~

`reltuples`/`relpages` được cập nhật từ những hoạt động như VACUUM/ANALYZE và không phải lúc nào cũng phản ánh chính xác hiện trạng tức thời.

### 18.2. Công thức expected size phải giả định row width

Một estimate đơn giản có thể cần:

- Average tuple width;
- Heap page overhead;
- Line pointer overhead;
- Fillfactor;
- Alignment/padding;
- Null bitmap;
- TOAST storage behavior;
- Tuple visibility/dead versions.

Nếu giả định row width sai, expected page count cũng sai. Không có một truy vấn bloat universal chính xác cho mọi schema/workload.

### 18.3. Bloat estimate không phải disk bytes có thể thu hồi ngay

Một báo cáo 40 GB “waste” không đảm bảo VACUUM FULL có thể trả đúng 40 GB. Một phần là free space hữu ích, một phần do fillfactor, một phần nằm trong index/TOAST, và một phần có thể không reclaim được do snapshots.

### 18.4. Dùng pgstattuple để kiểm chứng estimate

Một quy trình hợp lý:

1. Dùng size/stats views tìm ứng viên;
2. Chạy pgstattuple/pgstatindex cho một vài relation;
3. Xem long transactions/slots;
4. Chạy VACUUM thường nếu có dead tuples dọn được;
5. Đo lại;
6. Chỉ cân nhắc rewrite nếu bloat vật lý vẫn đáng kể và cần trả disk.

### 18.5. Đo trước/sau với cùng điều kiện

So sánh trước/sau nên dùng:

- Cùng relation và cùng loại size function;
- Cùng workload window hoặc ghi nhận lượng DML giữa hai lần đo;
- Cùng extension/version và cùng cách đo;
- Snapshot/time stamp;
- Dead tuple counts, free space và index density;
- Query latency/I/O nếu mục tiêu là hiệu năng.

Không so sánh `pg_table_size` trước với `pg_total_relation_size` sau rồi kết luận bloat tăng.

## 19. Đọc tình trạng autovacuum theo bảng

### 19.1. Tổng hợp activity và tuổi vacuum

~~~sql
SELECT
    s.schemaname,
    s.relname,
    pg_size_pretty(pg_total_relation_size(s.relid)) AS total_size,
    s.n_live_tup,
    s.n_dead_tup,
    s.n_tup_upd,
    s.n_tup_del,
    s.last_autovacuum,
    s.autovacuum_count,
    s.last_autoanalyze,
    s.n_mod_since_analyze
FROM pg_stat_user_tables AS s
ORDER BY pg_total_relation_size(s.relid) DESC
LIMIT 50;
~~~

Tìm các bảng lớn có n_dead_tup cao, UPDATE/DELETE nhiều và autovacuum gần nhất quá lâu. Nhưng đừng chỉ dựa vào `last_autovacuum`: một bảng có thể chưa cần vacuum, hoặc vacuum có thể bị chạy bởi thao tác manual.

### 19.2. Kiểm tra autovacuum bị tắt

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.reloptions @> ARRAY['autovacuum_enabled=false'];
~~~

Query này tìm một dạng storage option cụ thể; cấu hình autovacuum global và per-table cần được kiểm tra thêm. Temporary tables không được autovacuum xử lý như permanent tables.

### 19.3. Kiểm tra database-level vacuum settings

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_%'
ORDER BY name;
~~~

`source` giúp thấy cấu hình đến từ default/config file/database/role/session theo trạng thái server. Một managed database có thể áp giới hạn hoặc override riêng.

### 19.4. Nhiều workers không chạy có thể là triệu chứng

Nếu autovacuum không chạy, kiểm tra:

- Có bảng đủ threshold không?
- Autovacuum có bật ở server/database/table không?
- Có worker slots không?
- Worker có bị cost delay/IO chậm không?
- Có lock conflict hoặc long-running transactions không?
- Logs có lỗi permission/disk space không?

### 19.5. Autovacuum liên tục trên cùng bảng

Một bảng có thể liên tục đạt ngưỡng vì write rate rất cao. Điều này không nhất thiết là autovacuum “chạy sai”; có thể workload tạo churn vượt khả năng cleanup hiện tại. Cần xem threshold, scale factor, cost budget, worker capacity, index count và schema design.

## 20. Quy trình xử lý bloat theo nguyên nhân

Không có một lệnh “fix bloat” áp dụng cho mọi trường hợp. Hãy xác định **bloat nằm ở heap, index hay TOAST**, có thể vacuum dọn hay không, và mục tiêu là tái sử dụng space hay trả disk về filesystem.

### 20.1. Cây quyết định

~~~text
Relation tăng size / query scan chậm
            |
            v
Đo heap, indexes, TOAST và live/dead/free
            |
            v
Dead tuples còn nhiều?
     | Có                         | Không / ít
     v                            v
Tìm xmin horizon,            Index density/page layout
autovacuum và vacuum          hoặc heap free space lớn?
     |                            |
     v                            v
Sửa nguyên nhân; VACUUM       Index bloat? ---- Có ---> REINDEX (CONCURRENTLY nếu phù hợp)
thường + ANALYZE              Heap bloat?  ---- Có ---> Cân nhắc rewrite
     |                            |
     v                            v
Đo lại, theo dõi tái sử dụng  Cần thu hồi disk ngay?
                                  |
                      +-----------+-----------+
                      |                       |
                      v                       v
             Có lock window             Cần hạn chế block
                      |                       |
                      v                       v
              VACUUM FULL/CLUSTER       pg_repack (nếu phù hợp)
~~~

Sơ đồ là quy trình lựa chọn, không phải thuật toán tự động. Mỗi bước cần xem phiên bản, lock, disk, replication và SLA.

### 20.2. Trường hợp A: nhiều dead tuples, nhưng chưa cần shrink file

~~~sql
VACUUM (ANALYZE, VERBOSE) public.orders;
~~~

Sau đó:

1. Kiểm tra `n_dead_tup` và vacuum timestamps;
2. Đo lại bằng pgstattuple nếu cần;
3. Quan sát INSERT/UPDATE mới có dùng free space không;
4. Theo dõi size và query latency qua thời gian.

Không cần chạy FULL chỉ vì file chưa nhỏ lại; free space có thể đã sẵn sàng để tái sử dụng.

### 20.3. Trường hợp B: dead tuples không giảm

Kiểm tra:

- Long-running transactions và idle-in-transaction;
- Replication slots, `xmin`, `catalog_xmin`;
- `hot_standby_feedback`;
- Prepared transactions;
- Worker/autovacuum settings;
- Lock waits, I/O saturation và vacuum logs.

Giải quyết horizon blocker trước; vacuum thêm lần nữa khi tuples đã có thể được thu hồi.

### 20.4. Trường hợp C: index bloat đã xác nhận

Chọn đúng index và cân nhắc:

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_customer_id_idx;
~~~

Hoặc trong maintenance window phù hợp:

~~~sql
REINDEX INDEX public.orders_customer_id_idx;
~~~

Đo index size trước/sau, kiểm tra trạng thái index, query plans, lock waits và WAL. Không reindex toàn database chỉ dựa vào một báo cáo estimate.

### 20.5. Trường hợp D: heap bloat cần trả disk

Nếu có maintenance window:

~~~sql
VACUUM (FULL, ANALYZE) public.orders;
~~~

Nếu cần sắp xếp vật lý theo một index và chấp nhận lock:

~~~sql
CLUSTER public.orders USING orders_created_at_idx;
~~~

Nếu cần hạn chế thời gian chặn DML và đã đáp ứng prerequisites, đánh giá pg_repack. Cả ba đều cần disk headroom và test trên staging.

### 20.6. Trường hợp E: bloat quay lại nhanh

Không tiếp tục rewrite theo lịch ngắn mà không xử lý:

- UPDATE columns có index nhưng không cần index;
- HOT ratio thấp do page không có free space;
- Fillfactor không phù hợp;
- Autovacuum threshold quá cao;
- Transaction/snapshot cũ;
- ETL/job tạo churn;
- Index dư thừa hoặc key quá rộng.

### 20.7. Không dùng DROP/CREATE index để thay REINDEX một cách tùy tiện

Drop index có thể làm query chậm, constraint mất bảo vệ hoặc DML tạo duplicate data. Nếu cần xây index lại, hiểu dependencies/constraints và dùng REINDEX/CREATE INDEX CONCURRENTLY theo kế hoạch.

## 21. Lab: tạo churn, đo và quan sát VACUUM

Lab này minh họa khác biệt giữa **dead tuples**, **free space có thể tái sử dụng** và **file size**. Chỉ chạy trong database lab có quyền tạo schema/table và đủ disk; không dùng trên production.

### 21.1. Tạo schema và bảng thử

~~~sql
CREATE SCHEMA copy426;

CREATE TABLE copy426.bloat_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status text NOT NULL,
    note text NOT NULL,
    payload text NOT NULL
)
WITH (fillfactor = 80);
~~~

Table fillfactor 80 chừa chỗ cho một số updates; nó không đảm bảo mọi UPDATE đều HOT.

### 21.2. Tạo dữ liệu

~~~sql
INSERT INTO copy426.bloat_demo(status, note, payload)
SELECT
    CASE WHEN g % 2 = 0 THEN 'open' ELSE 'closed' END,
    'note-' || g,
    repeat('x', 200)
FROM generate_series(1, 50000) AS g;

CREATE INDEX bloat_demo_status_idx
ON copy426.bloat_demo(status);

CREATE INDEX bloat_demo_note_idx
ON copy426.bloat_demo(note);
~~~

### 21.3. Ghi lại kích thước ban đầu

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('copy426.bloat_demo'::regclass))
        AS heap_size,
    pg_size_pretty(pg_indexes_size('copy426.bloat_demo'::regclass))
        AS indexes_size,
    pg_size_pretty(pg_total_relation_size('copy426.bloat_demo'::regclass))
        AS total_size;
~~~

### 21.4. UPDATE cột không được index

~~~sql
UPDATE copy426.bloat_demo
SET payload = repeat('y', 200)
WHERE id % 2 = 0;
~~~

Nếu tuple mới vừa page và điều kiện HOT được đáp ứng, một phần updates có thể là HOT vì `payload` không nằm trong indexes. Xem `n_tup_hot_upd` để quan sát; kết quả phụ thuộc row layout và page free space.

### 21.5. UPDATE cột được index

~~~sql
UPDATE copy426.bloat_demo
SET status = CASE
    WHEN status = 'open' THEN 'closed'
    ELSE 'open'
END
WHERE id % 3 = 0;
~~~

`status` được index, nên những updates thay giá trị này thường không phải HOT đối với index đó; index entries mới có thể phát sinh.

### 21.6. DELETE một phần rows

~~~sql
DELETE FROM copy426.bloat_demo
WHERE id % 10 = 0;
~~~

Commit các statements trước khi đo để các tuples đã xóa có trạng thái phù hợp với snapshot hiện tại. VACUUM vẫn có thể phải chờ những transaction khác giữ snapshot cũ.

### 21.7. Đo dead/free space trước VACUUM

~~~sql
SELECT *
FROM pgstattuple('copy426.bloat_demo'::regclass);

SELECT
    pg_relation_size('copy426.bloat_demo'::regclass) AS heap_bytes,
    pg_indexes_size('copy426.bloat_demo'::regclass) AS index_bytes;
~~~

Nếu extension chưa được cài/được phép, dùng `pg_stat_user_tables` làm estimate và bỏ qua phép đo sâu.

### 21.8. Chạy VACUUM thường

~~~sql
VACUUM (VERBOSE, ANALYZE) copy426.bloat_demo;
~~~

Chạy lệnh này **ngoài explicit transaction block**. Sau đó đo lại bằng cùng query ở 21.7.

### 21.9. Điều cần quan sát

- Dead tuple bytes/count có thể giảm;
- Free space có thể tăng vì tuples đã được dọn;
- Heap/index file size có thể không giảm đáng kể;
- Space đó có thể được INSERT/UPDATE sau này tái sử dụng;
- Index cleanup có thể thay đổi trạng thái page nhưng không đảm bảo index file shrink.

### 21.10. Kiểm tra index B-tree

~~~sql
SELECT *
FROM pgstatindex('copy426.bloat_demo_status_idx'::regclass);

SELECT *
FROM pgstatindex('copy426.bloat_demo_note_idx'::regclass);
~~~

So sánh leaf density/page counts trước và sau khi có churn/vacuum nếu đã ghi baseline. Không suy ra một ngưỡng “đúng” cho mọi workload từ kết quả lab nhỏ.

### 21.11. Thử REINDEX trên index lab

~~~sql
REINDEX INDEX CONCURRENTLY copy426.bloat_demo_status_idx;
~~~

Nếu version hỗ trợ và lab không nằm trong explicit transaction block, lệnh concurrent cho phép DML tiếp tục phần lớn quá trình. Trong lab không có tải đồng thời, so sánh size trước/sau để thấy index được xây lại. Với server cũ, dùng cú pháp hỗ trợ của version hoặc REINDEX thường trong môi trường test.

### 21.12. Thử VACUUM FULL chỉ trong lab

~~~sql
VACUUM (FULL, ANALYZE) copy426.bloat_demo;
~~~

Lệnh này rewrite bảng và cần ACCESS EXCLUSIVE lock. Sau khi chạy, đo lại heap/table size. Kết quả cho thấy shrink file khác với vacuum thường.

### 21.13. Không lặp lại lab vô hạn

50.000 rows đủ để quan sát ý tưởng trong môi trường nhỏ. Không tăng lên hàng tỷ rows chỉ để làm biểu đồ bloat; disk/CPU/WAL và replication có thể bị ảnh hưởng.

### 21.14. Dọn lab nếu đã xác nhận có thể xóa

~~~sql
DROP SCHEMA copy426 CASCADE;
~~~

Lệnh này xóa mọi objects trong schema lab. Chỉ chạy nếu schema đúng là **schema thử nghiệm của bài**, không chứa dữ liệu cần giữ.

## 22. Bloat theo loại index

Không phải index nào cũng có cấu trúc B-tree. Cách cleanup và cách đo phải phù hợp với access method.

### 22.1. B-tree

B-tree thường dùng cho equality/range/order queries. INSERT/UPDATE/DELETE có thể làm page splits, dead entries và leaf pages thưa. VACUUM làm cleanup; REINDEX rebuild cấu trúc.

### 22.2. GIN

GIN thường dùng cho arrays, full-text search và JSONB operators. Nó có cơ chế pending list để gom inserts trước khi merge vào cấu trúc chính (tùy `fastupdate` và settings). Pending list quá lớn hoặc cleanup không theo kịp có thể làm query latency tăng.

Những yếu tố cần theo dõi:

- GIN pending list và `gin_pending_list_limit`;
- Autovacuum/VACUUM cleanup;
- Tần suất UPDATE/DELETE trên dữ liệu được index;
- Kích thước index và query latency.

Không dùng `pgstatindex` (B-tree tool) để đo GIN.

### 22.3. GiST và SP-GiST

Các index spatial/search khác có cấu trúc tree riêng. Page utilization và split behavior không thể đánh giá bằng cùng một ngưỡng leaf density của B-tree. Dùng công cụ/metrics phù hợp access method và workload.

### 22.4. BRIN

BRIN lưu summary theo block ranges, thường nhỏ hơn nhiều so với B-tree cho bảng lớn có dữ liệu tương quan với thứ tự vật lý. Bloat/size ở BRIN có semantics khác; cần xem số ranges, summarization và tính tương quan của dữ liệu.

### 22.5. Hash index

Hash index có bucket/split/overflow behavior riêng. Không áp dụng công thức bloat B-tree cho hash index.

### 22.6. Index không dùng và index dư thừa

Một index không được query sử dụng có thể là ứng viên review để loại bỏ, nhưng trước khi DROP:

- Kiểm tra primary key/unique/exclusion constraints;
- Kiểm tra foreign keys và query plans;
- Xem workload theo ngày/tháng/quý;
- Kiểm tra index phục vụ maintenance, reporting hoặc incident queries;
- So sánh index trùng lặp/left-prefix với query predicates;
- Xem thời gian từ lần reset statistics.

Index dư thừa làm tăng storage và write amplification, nhưng DROP nhầm index có thể phá correctness hoặc performance.

### 22.7. Index có predicate hoặc expression

Partial/expression indexes có thể giảm kích thước nếu chỉ index rows/expressions cần thiết. Tuy nhiên, predicate/expression cũng ảnh hưởng HOT eligibility và chi phí DML. Đánh giá theo workload thay vì thêm index cho mọi cột.

## 23. Thiết kế schema để giảm bloat

### 23.1. Chỉ index những gì workload cần

Mỗi index cần storage và phải được cập nhật khi dữ liệu liên quan thay đổi. Giảm index không cần thiết có thể giảm:

- Index bloat;
- WAL volume;
- CPU/I/O cho INSERT/UPDATE/DELETE;
- Thời gian vacuum/index cleanup;
- Backup/restore time.

### 23.2. Không index cột cập nhật liên tục nếu không cần

Nếu một cột `updated_at` được cập nhật mỗi lần row thay đổi và được index, mọi UPDATE có thể làm tăng index churn. Hãy hỏi query nào thật sự cần index này và liệu có thể dùng một thiết kế khác.

### 23.3. HOT-friendly schema

Để tăng cơ hội HOT:

- Không index những cột thường xuyên đổi nếu query không cần;
- Chừa free space hợp lý trên heap pages;
- Giữ row width ổn định khi có thể;
- Theo dõi HOT ratio;
- Kiểm tra expression/partial index dependencies.

### 23.4. Row width và TOAST

Các row có nhiều cột text/JSONB lớn có thể dùng TOAST. UPDATE một cột lớn có thể tạo version mới và TOAST chunks mới. Nếu workload thường xuyên thay một phần JSON document lớn, cân nhắc tách dữ liệu thành các bảng/records nhỏ hơn theo access pattern và retention.

### 23.5. Tách dữ liệu nóng/lạnh

Một bảng lưu cả dữ liệu giao dịch mới và lịch sử nhiều năm có thể chịu churn trên cùng relation. Tùy nghiệp vụ, partitioning theo thời gian hoặc tách archive table giúp:

- Retention rõ ràng;
- Xóa dữ liệu cũ bằng partition detach/drop thay vì DELETE từng row;
- Vacuum tập trung trên partitions nóng;
- Giới hạn index maintenance cho dữ liệu active.

Partitioning không tự loại bloat; mỗi partition vẫn cần vacuum và index maintenance.

### 23.6. Retention và DELETE hàng loạt

Nếu business policy là xóa toàn bộ dữ liệu của một tháng, partition drop/detach có thể hiệu quả hơn DELETE hàng triệu rows. Tuy nhiên, cần kiểm tra foreign keys, dependencies, backup/replication, audit, retention/legal holds và quyền DDL.

### 23.7. TRUNCATE khi xóa toàn bộ bảng

`TRUNCATE` có thể thu hồi table storage nhanh hơn DELETE vì không xử lý từng row. Nhưng nó cần lock mạnh, có semantics FK/trigger riêng và không phát row-level DELETE triggers. Chỉ dùng khi thực sự muốn bỏ **toàn bộ rows** và các hệ thống phụ thuộc chấp nhận semantics đó.

### 23.8. Không UPDATE dữ liệu không đổi

~~~sql
UPDATE public.orders
SET status = status
WHERE batch_id = 42;
~~~

có thể tạo row versions và index churn dù giá trị không đổi. Nếu nghiệp vụ cho phép, lọc rows thực sự khác:

~~~sql
UPDATE public.orders
SET status = 'paid'
WHERE batch_id = 42
  AND status IS DISTINCT FROM 'paid';
~~~

Giảm UPDATE thừa thường là cách trực tiếp để giảm dead tuples và vacuum pressure.

### 23.9. Upsert chỉ khi cần

`INSERT ... ON CONFLICT DO UPDATE` có thể UPDATE row đã tồn tại dù giá trị mới giống giá trị cũ, tùy câu lệnh. Thêm predicate `WHERE old.col IS DISTINCT FROM EXCLUDED.col` khi phù hợp để tránh update không cần thiết.

### 23.10. Retention của audit/event tables

Audit/event tables thường append-heavy, nhưng vẫn có thể bị UPDATE/DELETE do sửa trạng thái hoặc retention. Thiết kế partition theo thời gian và drop partition cũ có thể giảm churn, nhưng phải xem compliance và khả năng truy vấn lịch sử.

## 24. Tuning autovacuum theo loại bảng

Không có bộ tham số chung cho mọi bảng. Tối ưu dựa trên row count, update/delete rate, page count, thời gian vacuum, dead tuple trend và I/O budget.

### 24.1. Bảng lớn, UPDATE/DELETE nhiều

Một ví dụ per-table để vacuum sớm hơn:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.005
);
~~~

Scale factor thấp hơn làm ngưỡng dựa trên tỷ lệ nhỏ hơn; threshold tuyệt đối tránh vacuum quá thường xuyên với bảng rất nhỏ. Các con số chỉ là điểm bắt đầu cần đo.

### 24.2. Bảng nhỏ, thay đổi ít

Bảng nhỏ thường cần threshold tuyệt đối tương đối thấp để không đợi tới một tỷ lệ lớn. Nhưng nếu table rất nhỏ và ít ghi, defaults có thể đã phù hợp; đừng tune vì thấy bảng “không vacuum hôm nay”.

### 24.3. Bảng append-only

Bảng chủ yếu INSERT vẫn cần vacuum để:

- Freeze tuples;
- Cập nhật visibility map;
- Hỗ trợ index-only scans;
- Duy trì vacuum age.

Xem các insert-triggered vacuum settings trên version đang chạy.

### 24.4. Bảng update nóng nhưng không index cột cập nhật

Kiểm tra HOT ratio, fillfactor và vacuum cadence. Nếu HOT ratio thấp do page thiếu chỗ, cân nhắc giảm fillfactor; nếu cột update bị index, đánh giá index necessity trước.

### 24.5. Bảng có nhiều indexes

Vacuum phải làm cleanup liên quan tới indexes. Số index lớn làm chi phí bảo trì cao; cân nhắc loại bỏ indexes dư thừa và chọn `INDEX_CLEANUP` theo tình huống có hiểu biết.

### 24.6. Bảng partitioned

Autovacuum xử lý các partitions có storage như các relations riêng. Partitioned parent không chứa heap tuples như partition leaf; việc ANALYZE statistics cho parent/partition hierarchy có thể cần thao tác thủ công theo version/workload. Kiểm tra từng partition lớn, không chỉ parent.

### 24.7. Global worker/cost tuning

Nếu nhiều bảng cùng cần vacuum, xem:

- `autovacuum_max_workers`;
- `autovacuum_naptime`;
- `autovacuum_vacuum_cost_limit`;
- `autovacuum_vacuum_cost_delay`;
- Disk throughput, CPU và IOPS;
- Worker duration và số bảng pending.

Tăng workers/cost limit có thể giảm backlog nhưng làm ứng dụng cạnh tranh I/O. Cần đo latency và replication lag.

### 24.8. Log autovacuum

~~~sql
SHOW log_autovacuum_min_duration;
~~~

Trong môi trường được phép, cấu hình log các lần autovacuum đủ dài để xác định bảng nào vacuum chậm, bao nhiêu tuples/pages được xử lý và có skip do blockers không. Logs cần được bảo vệ, có retention và tránh ghi quá nhiều khi workload lớn.

### 24.9. Theo dõi sau tuning

Sau khi thay storage parameters:

1. Ghi cấu hình trước/sau;
2. Theo dõi autovacuum frequency/duration;
3. Theo dõi `n_dead_tup` và relation size;
4. Theo dõi HOT ratio;
5. Theo dõi query latency, I/O và WAL;
6. Đánh giá lại sau một chu kỳ workload đầy đủ.

Không kết luận tuning thành công chỉ vì dead tuples giảm trong vài phút nếu bloat/latency dài hạn chưa được quan sát.

## 25. Bloat, backup, replication và disk capacity

### 25.1. Bloat làm backup lớn hơn

Backup vật lý lưu các relation files nên bloat có thể làm tăng dung lượng backup, thời gian truyền và restore. Backup logic có thể chỉ serialize rows/index definitions và không giữ nguyên mọi free pages như physical backup; tác động tùy công cụ.

### 25.2. Rewrite tạo thêm I/O/WAL

VACUUM FULL, CLUSTER, REINDEX và pg_repack có thể đọc/ghi nhiều dữ liệu, tạo WAL và làm replication lag tăng. Trên hệ thống có standby, theo dõi:

- WAL generation rate;
- Replication lag;
- Slot retention;
- Disk headroom ở primary và standby;
- Backup/archiving backlog.

### 25.3. Disk tạm cần được tính trước

Trong rewrite, relation cũ và bản mới có thể cùng tồn tại trong một khoảng thời gian. Với index rebuild concurrent, index cũ và mới cũng có thể cùng chiếm disk. Đừng bắt đầu khi filesystem chỉ còn ít dung lượng hơn kích thước relation mục tiêu.

### 25.4. Không nhầm disk free với relation free space

`df`/disk monitoring cho biết filesystem capacity. `pgstattuple` cho biết tuple/free space bên trong relation. VACUUM thường có thể tăng reusable space mà df không đổi; rewrite có thể giảm relation size nhưng filesystem free space chỉ tăng khi file blocks thực sự được trả lại.

### 25.5. Storage snapshots và copy-on-write

Một số storage/volume snapshots có thể giữ lại blocks cũ sau rewrite cho tới khi snapshot hết hạn. Dung lượng relation giảm chưa chắc storage backend/billing giảm ngay. Kiểm tra semantics của storage layer.

### 25.6. Replication slots có thể làm cả WAL và dead tuples tăng

Slot bị bỏ quên có thể giữ WAL; `xmin`/`catalog_xmin` của slot còn có thể ảnh hưởng vacuum horizon. Đánh giá cả hai vấn đề, không chỉ xóa slot để giải phóng dung lượng.

## 26. Runbook chẩn đoán bloat trong production

Khi một bảng/index tăng dung lượng hoặc query chậm, hãy đi theo thứ tự đo và xác định nguyên nhân trước khi rewrite.

### Giai đoạn A — Xác định relation và phạm vi

Ghi nhận:

1. Schema/table/index cụ thể;
2. Tổng dung lượng và tốc độ tăng theo ngày/tuần;
3. Heap, indexes hay TOAST chiếm phần lớn;
4. Rows live/dead ước lượng;
5. Workload INSERT/UPDATE/DELETE;
6. Query nào chậm, scan loại gì và latency thay đổi ra sao;
7. Version PostgreSQL, storage type, replication topology và SLA.

### Giai đoạn B — Đo sâu có chọn lọc

Với những relation đáng nghi:

- Dùng `pgstattuple` hoặc `pgstattuple_approx` cho heap;
- Dùng `pgstatindex` cho B-tree index;
- Xem relation size và indexes/TOAST;
- Ghi lại timestamp, query, kết quả và workload đang chạy.

Không chạy full scans trên mọi relation lớn cùng lúc nếu chưa có I/O budget.

### Giai đoạn C — Xem VACUUM và autovacuum

Kiểm tra:

- `n_dead_tup`, `last_autovacuum`, `autovacuum_count`;
- Table storage parameters và autovacuum settings;
- `pg_stat_progress_vacuum`;
- Logs autovacuum;
- Long-running transactions, idle-in-transaction, prepared transactions;
- Replication slot xmin/catalog_xmin và standby feedback.

### Giai đoạn D — Phân loại nguyên nhân

| Kết quả quan sát | Hướng xử lý |
| --- | --- |
| Dead tuples nhiều, chưa vacuum gần đây | Xem autovacuum thresholds/workers |
| Vacuum chạy nhưng dead tuples không dọn | Tìm xmin horizon/long snapshot |
| Dead tuples giảm, free space tăng, size giữ nguyên | Có thể đang ở trạng thái tái sử dụng bình thường |
| Heap free space lớn và cần trả disk | Đánh giá VACUUM FULL/CLUSTER/pg_repack |
| B-tree density thấp và index size bất thường | Xem workload/fillfactor; cân nhắc REINDEX |
| GIN pending list/cleanup backlog | Xem GIN settings, vacuum và workload |
| TOAST chiếm dung lượng lớn | Xem churn của large values/retention |
| Bloat quay lại nhanh | Sửa schema, HOT eligibility, index churn, autovacuum |

### Giai đoạn E — Chọn remediation và tính rủi ro

Trước khi chạy:

- Lock type và thời gian chặn DML;
- Disk tạm cần cho relation/index mới;
- WAL generation, replication lag và backup impact;
- Query latency trong maintenance;
- Transaction đang giữ locks/snapshots;
- Có thể rollback/khôi phục như thế nào;
- Có đủ người vận hành và monitoring trong thời gian chạy không.

### Giai đoạn F — Thực hiện và đo lại

1. Chụp số liệu baseline;
2. Chạy VACUUM thường/REINDEX/rewrite đã chọn;
3. Theo dõi progress, locks, I/O, WAL và replication;
4. Đo lại relation/index size bằng cùng hàm;
5. Đo lại live/dead/free và density;
6. Kiểm tra query plans/latency;
7. Ghi nhận thay đổi và theo dõi bloat có quay lại không.

### Giai đoạn G — Không dừng ở con số disk

Một rewrite có thể giảm file size nhưng query latency không cải thiện nếu bottleneck là missing index, bad plan, network, CPU hoặc lock contention. Ngược lại, VACUUM thường có thể cải thiện khả năng tái sử dụng dù file size không đổi. Đo cả storage và behavior.

## 27. Các tình huống dễ chẩn đoán nhầm

### 27.1. File lớn nhưng không có nhiều dead tuples

Có thể do live data lớn, indexes/TOAST lớn, fillfactor thấp hoặc index thiết kế dư. Không tự chạy VACUUM FULL.

### 27.2. Dead tuples cao nhưng VACUUM không shrink

VACUUM thường chủ yếu tái sử dụng free space. Nếu dead tuple count giảm mà file size không đổi, điều đó không nhất thiết là thất bại.

### 27.3. VACUUM chạy liên tục

Có thể write rate cao, scale factor không phù hợp, bảng partitioned, worker capacity thấp hoặc vacuum phải làm freeze/index cleanup nhiều. Xem trend và duration trước khi tăng workers.

### 27.4. Query chậm sau khi UPDATE hàng loạt

Có thể do statistics cũ, dead tuples, cache churn hoặc index churn. Chạy ANALYZE phù hợp, kiểm tra plan, vacuum và index state. Không giả định VACUUM FULL là đáp án duy nhất.

### 27.5. Index size tăng dù heap size ổn định

Xem update columns có index, page splits, fillfactor, duplicate indexes và index type. Reindex có thể giúp nếu bloat được xác nhận, nhưng hãy xử lý write pattern để tránh lặp lại.

### 27.6. pg_stat_user_tables báo n_dead_tup thấp nhưng bloat vẫn lớn

Stats là estimate và chỉ phản ánh dead tuple estimates; relation có thể có free pages/page density thấp hoặc index bloat. Dùng pgstattuple/pgstatindex để đo sâu.

### 27.7. pgstattuple báo free_percent cao

Free space có thể được tái sử dụng. Nếu workload tiếp theo là INSERT/UPDATE cùng relation, đó có thể là lợi ích. Chỉ rewrite khi có mục tiêu trả disk hoặc cải thiện locality đã được đo.

### 27.8. REINDEX xong nhưng database size không giảm nhiều

Index được rebuild có thể nhỏ hơn, nhưng heap, các indexes khác, TOAST, WAL, temporary files hoặc snapshots/storage layer vẫn chiếm disk. Đo đúng relation và filesystem.

### 27.9. VACUUM FULL không chạy được

Nguyên nhân có thể là lock không lấy được, transaction block, disk không đủ, permission, relation type hoặc DDL conflict. Đọc lỗi cụ thể và chọn phương án phù hợp; không retry liên tục gây lock queue.

### 27.10. Autovacuum freeze không phải bloat event

Một bảng có thể được vacuum để freeze dù dead tuples ít. Đừng tắt vacuum chỉ vì không thấy tỷ lệ dead cao.

## 28. Checklist lựa chọn remediation

| Tình trạng | Ưu tiên xem xét | Cần tránh |
| --- | --- | --- |
| Dead tuples sau UPDATE/DELETE | VACUUM thường, autovacuum tuning | VACUUM FULL ngay |
| Dead tuples bị giữ bởi old snapshot | Giải quyết transaction/slot horizon | Chạy vacuum lặp lại |
| Free space tái sử dụng được | Theo dõi workload | Ép compact mọi page |
| Heap bloat lớn cần shrink | VACUUM FULL/CLUSTER/pg_repack | Chạy trong giờ cao điểm không chuẩn bị |
| B-tree index bloat xác nhận | REINDEX (CONCURRENTLY nếu phù hợp) | Reindex tất cả indexes theo lịch |
| Index churn do UPDATE | HOT, fillfactor, review index | Chỉ rebuild rồi bỏ nguyên nhân |
| GIN pending list | GIN maintenance/settings | Dùng pgstatindex B-tree metrics |
| TOAST bloat | Vacuum/rewriting TOAST relation phù hợp, review large-value churn | Chỉ đo heap main fork |
| Partition cũ hết retention | Detach/drop partition nếu business cho phép | DELETE hàng triệu rows không cần thiết |
| Wraparound risk | Anti-wraparound vacuum/runbook DBA | Tăng freeze threshold để che cảnh báo |

## 29. Các truy vấn giám sát hữu ích

### 29.1. Top relation theo size

~~~sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    c.reltuples::bigint AS estimated_rows,
    c.relpages AS estimated_pages,
    c.reloptions
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.relpersistence = 'p'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 50;
~~~

### 29.2. Top dead tuple estimates

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
~~~

### 29.3. Top long transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

### 29.4. Vacuum đang chạy

~~~sql
SELECT
    pid,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
~~~

### 29.5. Tuổi XID theo database

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    datfrozenxid
FROM pg_database
ORDER BY xid_age DESC;
~~~

Đây là các truy vấn giám sát đọc metadata; quyền xem chi tiết có thể phụ thuộc role. Dùng dashboard/monitoring lưu số liệu theo thời gian để nhận ra trend thay vì chỉ chạy thủ công khi đã hết disk.

## 30. Bài tập thực hành — MVCC và khái niệm bloat

Các bài tập sử dụng PostgreSQL database lab, schema `copy426` và các query trong bài. Một số câu yêu cầu suy luận, không nhất thiết phải thực thi DDL. **Không chạy các lệnh rewrite, DROP hoặc TRUNCATE trên production chỉ để làm bài tập.**

### Bài 1 — Định nghĩa bloat

Một table file lớn hơn nhu cầu live data. Nêu ít nhất bốn nguyên nhân có thể làm relation lớn và giải thích vì sao file lớn chưa đủ chứng minh bloat.

### Bài 2 — UPDATE theo MVCC

Một row được UPDATE từ `status='open'` thành `status='paid'`.

**Câu hỏi:** vì sao PostgreSQL có thể tạo tuple version mới? Phiên bản cũ được dọn ngay không?

### Bài 3 — DELETE không xóa bytes ngay

DELETE 100.000 rows và commit. **Câu hỏi:** vì sao table file có thể chưa giảm kích thước? VACUUM cần làm gì tiếp theo?

### Bài 4 — Dead tuple

Phân biệt live tuple, dead tuple, tuple version còn cần cho snapshot cũ và free space sau vacuum.

### Bài 5 — VACUUM thường

~~~sql
VACUUM public.orders;
~~~

**Câu hỏi:** lệnh có rewrite toàn heap không? Mục tiêu chính là gì?

**Đáp án:** không rewrite toàn bảng; dọn dead tuples và làm không gian có thể tái sử dụng.

### Bài 6 — VACUUM không shrink file

Sau VACUUM, `n_dead_tup` giảm mạnh nhưng `pg_relation_size()` gần như không đổi.

**Câu hỏi:** đây có phải thất bại không? Giải thích free space có thể tái sử dụng.

### Bài 7 — Trailing pages

VACUUM thường có thể truncate empty pages ở cuối relation trong trường hợp nào? Vì sao free space nằm giữa file thường không được trả lại filesystem?

### Bài 8 — VACUUM ANALYZE

Phân biệt tác dụng của VACUUM và ANALYZE. Vì sao statistics mới không tự dọn dead tuples?

### Bài 9 — VACUUM trong transaction

~~~sql
BEGIN;
VACUUM public.orders;
COMMIT;
~~~

**Câu hỏi:** vì sao cách chạy này không hợp lệ? Một migration tool tự wrap transaction cần xử lý ra sao?

### Bài 10 — Long-running snapshot

Transaction A mở snapshot; transaction B UPDATE/DELETE row và commit; VACUUM chạy khi A còn mở.

**Bài tập:** giải thích vì sao old tuple có thể chưa được dọn và điều gì thay đổi sau khi A kết thúc.

### Bài 11 — HOT update

Một table có index trên `customer_id`, còn UPDATE chỉ đổi `note`.

**Câu hỏi:** khi nào HOT có thể xảy ra? Tại sao nó giảm index churn?

### Bài 12 — HOT không thành công

UPDATE thay đổi cột có B-tree index.

**Câu hỏi:** vì sao HOT thường không áp dụng cho index đó? Index entries mới có thể phát sinh thế nào?

### Bài 13 — Fillfactor 100

Một heap page đầy gần hết, UPDATE cần tạo tuple version mới.

**Bài tập:** giải thích vì sao thiếu free space có thể làm HOT thất bại dù không thay cột index.

### Bài 14 — Table fillfactor 80

~~~sql
CREATE TABLE t (
    id bigint,
    status text
) WITH (fillfactor = 80);
~~~

**Câu hỏi:** 20% free có phải cam kết tuyệt đối cho mọi page? Vì sao table có thể lớn hơn lúc đầu?

### Bài 15 — ALTER TABLE SET fillfactor

~~~sql
ALTER TABLE t SET (fillfactor = 70);
~~~

**Câu hỏi:** lệnh này có tự rewrite toàn bộ pages hiện có không? Cách nào áp dụng layout mới tới dữ liệu cũ?

### Bài 16 — Index fillfactor

So sánh table fillfactor và B-tree index fillfactor. Chúng giúp những workload nào và đánh đổi storage ra sao?

### Bài 17 — HOT ratio

~~~sql
SELECT n_tup_upd, n_tup_hot_upd
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

**Câu hỏi:** HOT ratio thấp có thể do những nguyên nhân nào? Có ngưỡng chung cho mọi bảng không?

### Bài 18 — Heap bloat và index bloat

Một bảng heap 2 GB có indexes 15 GB.

**Bài tập:** xác định cần đo những gì trước khi chọn VACUUM FULL hay REINDEX.

### Bài 19 — TOAST

Một bảng có JSONB lớn, `pg_total_relation_size` cao hơn nhiều `pg_relation_size`.

**Câu hỏi:** tại sao phải kiểm tra TOAST relation? Heap size có thể bỏ sót phần nào?

### Bài 20 — Free space map

FSM có vai trò gì trong việc tìm page có chỗ trống? Nó có phải một file chứa dữ liệu row hay cơ chế trả disk cho filesystem không?

### Bài 21 — Visibility map

Giải thích all-visible và all-frozen flags hỗ trợ VACUUM và index-only scans thế nào.

### Bài 22 — Page fragmentation

Một table có free space 30% nhưng workload sắp tới là INSERT cùng loại rows.

**Câu hỏi:** tại sao không nên mặc định rewrite để loại hết free space?

### Bài 23 — Index page split

Mô tả vì sao B-tree leaf page có thể split khi insert. Workload random keys và fillfactor ảnh hưởng thế nào?

### Bài 24 — Index dư thừa

Một bảng có 12 indexes, trong đó 5 index chưa thấy được dùng.

**Bài tập:** liệt kê kiểm tra cần thiết trước khi DROP một index.

### Bài 25 — No-op UPDATE

~~~sql
UPDATE orders SET status = status;
~~~

**Câu hỏi:** câu này có thể tạo row churn không? Viết predicate tránh update giá trị không đổi.

**Đáp án:** dùng `status IS DISTINCT FROM target_value` trong WHERE khi phù hợp.

### Bài 26 — Fillfactor thấp quá mức

Một bảng append-only có fillfactor 50.

**Bài tập:** phân tích chi phí storage/scan và vì sao fillfactor thấp không tự động tốt.

### Bài 27 — Churn từ ETL

Một ETL xóa toàn bộ rows của ngày hôm qua rồi insert lại cùng dữ liệu.

**Câu hỏi:** cách làm này tạo những chi phí nào? Có thể dùng partitioning, upsert có điều kiện hoặc staging ra sao?

### Bài 28 — Dữ liệu lớn

UPDATE một JSONB document 2 MB trên hàng triệu rows.

**Bài tập:** giải thích vì sao TOAST churn và WAL có thể lớn; đề xuất tách dữ liệu hoặc cập nhật theo access pattern.

### Bài 29 — Bloat hay tăng trưởng thật?

Một bảng tăng từ 5 GB lên 12 GB sau khi thêm 20 triệu rows mới.

**Câu hỏi:** cần bằng chứng nào trước khi gọi phần tăng 7 GB là bloat?

### Bài 30 — VACUUM và transaction ID

Một bảng ít DELETE nhưng có XID age cao.

**Câu hỏi:** tại sao vẫn cần VACUUM freeze? Có thể disable autovacuum chỉ vì dead tuples ít không?

### Bài 31 — pgstattuple

Chạy `pgstattuple('public.orders'::regclass)`.

**Bài tập:** giải thích `tuple_percent`, `dead_tuple_percent` và `free_percent`. Vì sao không cộng hai phần trăm rồi gọi kết quả là “bloat chính xác”?

### Bài 32 — pgstattuple_approx

**Câu hỏi:** vì sao `pgstattuple_approx` có thể nhanh hơn full scan? Nó tận dụng metadata nào? Đổi lại số liệu có đặc điểm gì?

### Bài 33 — pgstatindex

Một B-tree index có `avg_leaf_density` thấp.

**Bài tập:** liệt kê ít nhất bốn lý do có thể khiến density thấp và giải thích vì sao cần biết index fillfactor.

### Bài 34 — Các hàm kích thước

Phân biệt `pg_relation_size`, `pg_table_size`, `pg_indexes_size` và `pg_total_relation_size`. Viết query cho một table để in đủ bốn số.

### Bài 35 — Index lớn nhất

Dùng `pg_stat_user_indexes` và `pg_relation_size(indexrelid)` để liệt kê 10 indexes lớn nhất.

**Câu hỏi:** có thể DROP index đầu tiên trong danh sách không? Những kiểm tra nào còn thiếu?

### Bài 36 — TOAST size

Viết query dùng `pg_class.reltoastrelid` để tìm TOAST relation lớn nhất. Giải thích tại sao chỉ xem main heap fork không đủ.

### Bài 37 — Autovacuum threshold

Giả sử một table có 50 triệu estimated tuples, vacuum threshold 1.000 và scale factor 0.01.

**Câu hỏi:** ngưỡng UPDATE/DELETE gần đúng là bao nhiêu theo công thức? Vì sao đây vẫn chỉ là mô hình ước lượng?

**Đáp án:** khoảng 501.000 tuple changes, tùy các quy tắc/estimates và version.

### Bài 38 — Scale factor mặc định

Một bảng 100 triệu rows dùng scale factor 0.2.

**Bài tập:** giải thích vì sao đợi tới khoảng 20 triệu changes có thể quá muộn với workload lớn.

### Bài 39 — Insert-triggered vacuum

Một bảng event append-only hầu như không UPDATE/DELETE.

**Câu hỏi:** tại sao vẫn cần vacuum insert/freeze? Nêu các settings insert-triggered liên quan theo version.

### Bài 40 — Autovacuum workers

Server có 10 bảng lớn cùng cần vacuum, nhưng chỉ có 3 workers.

**Bài tập:** nêu những metric cần xem trước khi tăng workers và vì sao bottleneck I/O có thể khiến tăng worker không cải thiện.

### Bài 41 — Long transaction

Một session ở trạng thái idle in transaction 4 giờ.

**Câu hỏi:** nó có thể giữ snapshot và làm vacuum không dọn được dead tuples thế nào? Nêu cách điều tra.

### Bài 42 — Replication slot

Một logical replication slot inactive nhiều ngày, có xmin/catalog_xmin cũ.

**Bài tập:** phân tích ảnh hưởng tới WAL và vacuum horizon; vì sao không được DROP slot nếu chưa xác nhận subscriber?

### Bài 43 — hot_standby_feedback

**Câu hỏi:** feedback từ standby có thể giúp tránh điều gì? Đổi lại primary có thể chịu ảnh hưởng gì về dead tuples?

### Bài 44 — pg_stat_progress_vacuum

**Bài tập:** viết query lấy relation, phase, heap_blks_total/scanned/vacuumed. Giải thích vì sao tỷ lệ blocks scanned không phải tỷ lệ bloat đã xử lý.

### Bài 45 — REINDEX CONCURRENTLY

**Câu hỏi:** lợi ích chính so với REINDEX thường là gì? Những giai đoạn nào vẫn có lock, disk tạm và transaction waits?

### Bài 46 — VACUUM FULL

Một bảng 200 GB cần shrink nhưng chỉ còn 40 GB disk free.

**Bài tập:** phân tích vì sao chạy VACUUM FULL có thể thất bại/ảnh hưởng dịch vụ; cần chuẩn bị disk/lock/backup thế nào?

### Bài 47 — CLUSTER

Một bảng query theo thời gian và thường lấy một khoảng date liên tục.

**Câu hỏi:** khi nào CLUSTER theo index thời gian có thể cải thiện locality? Vì sao thứ tự vật lý sẽ lệch dần sau các writes mới?

### Bài 48 — pg_repack

**Bài tập:** nêu prerequisites, lock phases, disk headroom và khác biệt giữa “ít block hơn” với “zero-lock”.

### Bài 49 — Partition retention

Một bảng log partition theo tháng, cần xóa dữ liệu đã quá 24 tháng.

**Bài tập:** so sánh DELETE hàng triệu rows với detach/drop partition. Liệt kê FK, audit, replication, backup và legal retention cần kiểm tra.

### Bài 50 — Capstone: bảng orders có bloat

Một hệ thống có bảng `orders` 300 GB, 6 indexes, UPDATE status nhiều lần/ngày, autovacuum chạy liên tục, dead tuple estimate dao động cao. Bảng có long-running reporting transaction và logical replication slot.

**Yêu cầu nộp:**

1. Vẽ sơ đồ heap, indexes, TOAST và transaction horizons liên quan.
2. Viết truy vấn đo total size, heap/index sizes, dead tuple estimates, vacuum activity và HOT ratio.
3. Chọn một phương án đo sâu bằng pgstattuple/pgstatindex và giải thích chi phí.
4. Điều tra reporting transaction và replication slot trước khi chạy thêm VACUUM.
5. Tính autovacuum threshold hiện tại, đề xuất per-table settings có cơ sở.
6. Review indexes trên những cột UPDATE thường xuyên; xác định cơ hội HOT.
7. Đề xuất fillfactor table/index và giải thích trade-off.
8. Chỉ ra khi nào VACUUM thường đủ và khi nào cần REINDEX.
9. Đánh giá VACUUM FULL, CLUSTER hoặc pg_repack theo lock/disk/WAL/SLA.
10. Lập kế hoạch đo trước/sau, replication lag, query latency và disk recovery.
11. Đưa ra giải pháp ngăn bloat tái diễn: update predicates, retention, partitioning, index cleanup.
12. Viết runbook rollback/incident nếu rewrite không hoàn tất hoặc disk pressure tăng.

**Tiêu chí đạt:** không chọn một lệnh chỉ vì nó “làm nhỏ file”. Người học phải chứng minh được **bloat nằm ở đâu, vì sao hình thành, có thể vacuum dọn không, và chi phí/khóa của phương án sửa là gì**.

## 31. Checklist bảo trì định kỳ

### 31.1. Theo dõi dung lượng

- [ ] Ghi nhận total size của các tables lớn theo thời gian.
- [ ] Phân biệt heap, indexes và TOAST.
- [ ] Ghi nhận tỷ lệ tăng size so với số live rows và business data.
- [ ] Theo dõi các index lớn nhất và lý do nghiệp vụ tồn tại.
- [ ] Không xem relation size đơn lẻ là bằng chứng bloat.

### 31.2. Theo dõi MVCC và VACUUM

- [ ] Theo dõi n_live_tup/n_dead_tup và hiểu chúng là estimates.
- [ ] Theo dõi last_autovacuum, autovacuum_count và vacuum duration.
- [ ] Theo dõi pg_stat_progress_vacuum khi có vacuum lớn.
- [ ] Kiểm tra long-running transactions và idle-in-transaction.
- [ ] Kiểm tra replication slots, xmin/catalog_xmin và standby feedback.
- [ ] Kiểm tra prepared transactions bị bỏ quên.
- [ ] Không disable autovacuum như giải pháp thường trực.
- [ ] Theo dõi XID age và anti-wraparound vacuum.

### 31.3. Theo dõi HOT và indexes

- [ ] Theo dõi HOT update ratio.
- [ ] Review index trên các cột bị UPDATE thường xuyên.
- [ ] Đánh giá table/index fillfactor theo workload.
- [ ] Kiểm tra index usage theo chu kỳ đủ dài.
- [ ] Không DROP index chỉ vì idx_scan thấp trong cửa sổ ngắn.
- [ ] Dùng metric phù hợp access method; pgstatindex chỉ cho B-tree.
- [ ] Xem GIN pending list/maintenance nếu dùng GIN.

### 31.4. Chọn remediation

- [ ] VACUUM thường trước khi nghĩ tới rewrite nếu có dead tuples dọn được.
- [ ] Chỉ chạy VACUUM FULL khi cần shrink và có lock/disk window.
- [ ] Chỉ CLUSTER khi physical ordering đem lại lợi ích query đo được.
- [ ] REINDEX đúng index đã xác nhận có vấn đề.
- [ ] Dùng REINDEX CONCURRENTLY khi version và workload phù hợp.
- [ ] Đánh giá pg_repack theo prerequisites/lock/disk/WAL.
- [ ] Không chạy rewrite toàn bộ relations theo lịch không có bằng chứng.

### 31.5. An toàn vận hành

- [ ] Ghi baseline size, dead/free space và query latency.
- [ ] Xác minh đủ disk tạm và filesystem headroom.
- [ ] Xác minh WAL/archive/replication capacity.
- [ ] Kiểm tra locks và transaction đang chạy.
- [ ] Có maintenance/rollback plan và người giám sát.
- [ ] Đo lại bằng cùng công cụ/cùng cách sau remediation.
- [ ] Theo dõi bloat quay lại và sửa nguyên nhân gốc.

## 32. Câu hỏi thường gặp

### 32.1. VACUUM có xóa dead tuples không?

Có, khi các tuple versions không còn cần thiết đối với transaction snapshots. VACUUM làm space có thể tái sử dụng; nó không nhất thiết rewrite relation hoặc thu nhỏ file.

### 32.2. Tại sao VACUUM xong file không nhỏ?

Free space có thể nằm ở giữa relation và được giữ để tái sử dụng. Chỉ những trailing pages phù hợp mới có thể được truncate trong một số trường hợp. Muốn rewrite toàn heap, xem VACUUM FULL/CLUSTER/pg_repack.

### 32.3. VACUUM FULL có an toàn không?

Nó là thao tác hợp lệ nhưng cần ACCESS EXCLUSIVE lock, disk tạm và I/O lớn. Phải lập kế hoạch trên bảng production, không chạy tùy tiện trong giờ cao điểm.

### 32.4. Có nên chạy VACUUM FULL hằng đêm?

Thông thường không. Autovacuum và VACUUM thường là bảo trì định kỳ; rewrite lớn cần bằng chứng bloat và mục tiêu thu hồi disk cụ thể.

### 32.5. Dead tuple percent cao có nghĩa cần VACUUM FULL?

Không. VACUUM thường có thể dọn dead tuples và space được tái sử dụng. Chỉ chọn rewrite nếu bloat vật lý còn đáng kể và cần thu nhỏ relation.

### 32.6. REINDEX có làm nhỏ table heap không?

Không. REINDEX rebuild index. Heap bloat cần vacuum/rewrite table phù hợp.

### 32.7. REINDEX CONCURRENTLY có không khóa?

Không. Nó giảm mức chặn DML trong phần lớn quá trình nhưng vẫn có các giai đoạn lock, transaction waits, disk tạm và WAL.

### 32.8. Fillfactor thấp có làm bloat tăng?

Nó làm relation/index có thể lớn hơn ban đầu vì cố ý chừa chỗ. Nhưng với workload UPDATE hoặc insert ngẫu nhiên, khoảng trống đó có thể giảm HOT failures/page splits. Đánh giá trade-off theo workload.

### 32.9. HOT update có tránh dead tuples không?

Không. HOT vẫn tạo tuple version mới trong heap, nhưng có thể tránh tạo index entries mới. VACUUM vẫn cần cleanup.

### 32.10. Vì sao long transaction làm bloat?

Nó có thể giữ snapshot cũ khiến VACUUM không dọn một số tuple versions. Tìm transaction lâu và xử lý đúng lifecycle trước khi chạy thêm vacuum.

### 32.11. Replication slot có ảnh hưởng bloat không?

Có thể. Slot giữ xmin/catalog_xmin có thể làm vacuum horizon cũ; slot còn có thể giữ WAL. Không xóa slot nếu chưa xác định consumer và recovery plan.

### 32.12. pgstattuple có chính xác không?

`pgstattuple` quét relation để đo tuple/dead/free space tại thời điểm chạy, nhưng kết quả vẫn phải diễn giải theo page layout, concurrency và mục tiêu reclaim. `pgstattuple_approx` nhanh hơn trong một số trường hợp nhưng là ước lượng.

### 32.13. pgstatindex có đo được GIN không?

Không. `pgstatindex` dành cho B-tree. Dùng metrics/tool phù hợp cho GIN, GiST, BRIN hoặc hash.

### 32.14. n_dead_tup bằng 0 có chứng minh không có bloat?

Không. Nó là estimate về dead tuples, không đo đầy đủ free page density, index bloat hoặc TOAST. Relation vẫn có thể thưa hoặc có nhiều free space hữu ích.

### 32.15. Vì sao autovacuum không chạy ngay khi có DELETE?

Nó hoạt động theo threshold/scale factor, worker availability, cost limits và điều kiện transaction horizon. DELETE commit không có nghĩa autovacuum lập tức chạy.

### 32.16. Có nên tăng autovacuum_max_workers thật cao?

Không mặc định. Thêm workers có thể tăng I/O contention. Đo vacuum backlog, worker duration, storage throughput và application latency trước.

### 32.17. TRUNCATE có phải cách trị bloat?

Chỉ khi nghiệp vụ thực sự muốn xóa toàn bộ rows và chấp nhận lock/FK/trigger semantics. Không dùng TRUNCATE để giữ lại rows live.

### 32.18. Bloat có làm query chậm luôn không?

Không phải lúc nào. Tác động phụ thuộc query access pattern, cache, scan type và vị trí bloat. Đo query latency/plan và I/O thay vì chỉ suy từ size.

### 32.19. pg_repack có thay autovacuum không?

Không. pg_repack là công cụ rewrite/rebuild; autovacuum vẫn cần để duy trì MVCC cleanup và freeze.

### 32.20. Làm sao biết bloat đã quay lại?

Theo dõi trend size, live/dead/free space, index density, HOT ratio, vacuum cadence và write workload theo cùng cửa sổ thời gian. Một lần đo đơn lẻ không đủ.

## 33. Tài liệu PostgreSQL chính thức

Các liên kết sau trỏ tới tài liệu PostgreSQL hiện hành. Khi vận hành, hãy chọn **đúng major version** của server vì autovacuum settings, REINDEX CONCURRENTLY, progress views và một số options thay đổi theo version:

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): MVCC cleanup, VACUUM, ANALYZE, autovacuum và wraparound.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): option FULL, FREEZE, VERBOSE, INDEX_CLEANUP và TRUNCATE.
- [Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html): thresholds, scale factors, workers và cost settings.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): rebuild index, CONCURRENTLY và lock/transaction restrictions.
- [CLUSTER](https://www.postgresql.org/docs/current/sql-cluster.html): rewrite table theo index và storage parameters.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html): pgstattuple, pgstattuple_approx và pgstatindex.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_user_tables, pg_stat_user_indexes, pg_stat_activity và replication stats.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): pg_stat_progress_vacuum và các progress views.
- [Storage Page Layout](https://www.postgresql.org/docs/current/storage-page-layout.html): heap page, tuple headers, line pointers và free space.
- [Heap-Only Tuples (HOT)](https://www.postgresql.org/docs/current/storage-hot.html): HOT update và điều kiện liên quan.
- [CREATE TABLE Storage Parameters](https://www.postgresql.org/docs/current/sql-createtable.html#SQL-CREATETABLE-STORAGE-PARAMETERS): table fillfactor và storage options.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index fillfactor và các index options.
- [System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html): relpages, reltuples, reloptions và TOAST relation.
- [System Catalog pg_stat_all_tables](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ALL-TABLES-VIEW): table activity counters.
- [System Catalog pg_stat_progress_vacuum](https://www.postgresql.org/docs/current/progress-reporting.html#VACUUM-PROGRESS-REPORTING): vacuum progress.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): replication slots và hot_standby_feedback.
- [Routine Reindexing](https://www.postgresql.org/docs/current/routine-reindex.html): khi nào và cách reindex.
- [pg_repack project](https://github.com/reorg/pg_repack): extension/tool bên ngoài core để rewrite relation với thời gian block thấp hơn trong những điều kiện phù hợp.

## 34. Tổng kết

**Bloat trong bảng và chỉ mục** phát sinh từ tương tác giữa MVCC row versions, dead tuples, free space, page layout, index churn, TOAST và cơ chế vacuum. PostgreSQL giữ các phiên bản cũ khi snapshot còn cần chúng; VACUUM dọn những versions đủ điều kiện và làm space có thể tái sử dụng.

| Công cụ | Mục tiêu chính | Có rewrite? | Điểm cần lưu ý |
| --- | --- | --- | --- |
| VACUUM | Dọn dead tuples, freeze và tái sử dụng space | Không rewrite toàn heap | File thường không shrink đáng kể |
| VACUUM ANALYZE | Cleanup + cập nhật planner statistics | Không rewrite toàn heap | ANALYZE không thay VACUUM |
| VACUUM FULL | Thu hồi heap bloat bằng rewrite | Có | ACCESS EXCLUSIVE lock, disk tạm |
| CLUSTER | Rewrite heap theo index order | Có | Lock mạnh; thứ tự vật lý lệch dần sau DML |
| REINDEX | Rebuild indexes | Có, với index | Không sửa heap bloat |
| REINDEX CONCURRENTLY | Rebuild index với ít block DML hơn | Có, với index | Vẫn có lock phases, disk/WAL và transaction waits |
| pg_repack | Rewrite table/index với block window ngắn hơn | Có | Tool ngoài core, prerequisites và disk headroom |

Để kiểm soát bloat bền vững:

1. Theo dõi table/index/TOAST sizes cùng live/dead/free estimates;
2. Giữ autovacuum hoạt động và tune theo quy mô/write rate;
3. Tìm long transactions, replication slots và snapshot horizons;
4. Thiết kế index/fillfactor để giảm churn và tăng HOT khi phù hợp;
5. Tránh UPDATE không đổi và retention DELETE không cần thiết;
6. Đo sâu bằng pgstattuple/pgstatindex có chọn lọc;
7. Chọn VACUUM, REINDEX hoặc rewrite theo đúng loại bloat;
8. Đo trước/sau cả disk, query latency, WAL và replication.

**Không phải mọi free space đều là lãng phí, và không phải mọi relation lớn đều bị bloat.** Một hệ thống khỏe là hệ thống dọn dead tuples kịp thời, tái sử dụng free space hiệu quả, giữ indexes phù hợp với workload và chỉ rewrite khi lợi ích thu hồi/hiệu năng lớn hơn chi phí lock, I/O và disk tạm.
