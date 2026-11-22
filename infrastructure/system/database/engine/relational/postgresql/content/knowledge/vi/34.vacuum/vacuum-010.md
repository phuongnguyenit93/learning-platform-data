# REINDEX, REINDEX CONCURRENTLY và xử lý phình chỉ mục trong PostgreSQL

Index giúp PostgreSQL tìm dữ liệu nhanh hơn, nhưng index cũng là cấu trúc vật lý cần bảo trì. INSERT tạo index entries; UPDATE có thể phải cập nhật index; DELETE để lại entries cần được dọn khi tuple không còn cần thiết. B-tree pages còn có thể chịu page split, thay đổi mật độ và phân mảnh theo workload.

Khi index phình to hoặc có dấu hiệu hỏng, PostgreSQL cung cấp lệnh **REINDEX** để xây dựng lại index từ dữ liệu nguồn. Đây là thao tác bảo trì có tác động đáng kể tới lock, I/O, dung lượng đĩa và query latency.

Có hai cách vận hành quan trọng:

- **REINDEX thông thường**: đơn giản và thường nhanh hơn, nhưng lấy lock mạnh trên bảng liên quan, có thể chặn cả đọc lẫn ghi.
- **REINDEX CONCURRENTLY**: xây index mới qua nhiều giai đoạn để ứng dụng vẫn có thể tiếp tục đọc/ghi trong phần lớn thời gian, đổi lại cần thêm tài nguyên, nhiều lần scan và có thêm điều kiện vận hành.

Điều đầu tiên cần xác định là đối tượng đang phình: heap table, TOAST relation hay index. **REINDEX chỉ xây dựng lại index; nó không thu gọn heap table.** Nếu bảng phình do dead tuples, cần điều tra VACUUM/transaction horizon; nếu heap cần rewrite, đó là bài toán khác.

~~~mermaid
flowchart TD
    A["Phát hiện relation lớn hoặc query chậm"] --> B["Xác định heap, TOAST hay index"]
    B --> C["Đo kích thước và mật độ index"]
    C --> D{"Có bằng chứng index bloat/hỏng?"}
    D -->|"Không"| E["Điều tra query plan, schema, workload"]
    D -->|"Có"| F{"Có maintenance window?"}
    F -->|"Có"| G["REINDEX thông thường"]
    F -->|"Không"| H["Đánh giá REINDEX CONCURRENTLY"]
    G --> I["Theo dõi lock, disk, latency"]
    H --> I
    I --> J["Xác minh index mới và đo lại"]
~~~

Bài thuộc chương **VACUUM**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu B-tree index, dấu hiệu bloat, cách đo, sự khác nhau giữa REINDEX và VACUUM, lock behavior, quy trình concurrent reindex, xử lý lỗi và kế hoạch vận hành an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích REINDEX làm gì và khi nào cần rebuild index.
2. Phân biệt REINDEX INDEX, TABLE, SCHEMA, DATABASE và SYSTEM.
3. Hiểu lock và downtime của REINDEX thông thường.
4. Mô tả REINDEX CONCURRENTLY và các giai đoạn xây index.
5. Biết giới hạn quan trọng: không chạy concurrent reindex trong transaction block.
6. Phân biệt index bloat với heap/table bloat và TOAST growth.
7. Đo kích thước index bằng các hàm relation-size.
8. Ước lượng mật độ B-tree bằng pgstattuple/pgstatindex khi extension được phép.
9. Hiểu vì sao số dead tuples không trực tiếp bằng mức bloat của index.
10. Chọn index cần rebuild dựa trên số liệu và workload.
11. Hiểu ảnh hưởng của fillfactor, page split và write pattern.
12. Nhận diện trường hợp index corruption và giới hạn của REINDEX.
13. Xử lý index invalid sau lần reindex concurrent thất bại.
14. Lập kế hoạch dung lượng, I/O, lock, replica lag và maintenance window.
15. Xác minh kết quả sau REINDEX và thiết kế quy trình bảo trì có thể rollback.

## 2. Index trong PostgreSQL lưu những gì?

Index là cấu trúc phụ trợ giúp tìm các hàng trong table. Với B-tree, mỗi index entry chứa giá trị khóa và thông tin định vị tuple trong heap. Index có thể hỗ trợ:

- Equality/range lookup.
- ORDER BY phù hợp với thứ tự index.
- UNIQUE/PRIMARY KEY enforcement.
- Join và foreign key workloads.
- Index-only scan nếu index bao phủ dữ liệu và visibility map cho phép.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_created
ON public.orders (customer_id, created_at);
~~~

Một query có điều kiện phù hợp:

~~~sql
SELECT order_id, created_at, total_amount
FROM public.orders
WHERE customer_id = 42
  AND created_at >= timestamptz '2026-01-01 00:00:00+00'
ORDER BY created_at;
~~~

PostgreSQL có thể dùng index này nếu planner đánh giá chi phí thấp hơn phương án khác.

### Index không phải bản sao đơn giản của table

Index có page header, internal pages, leaf pages, tuple entries, free space và metadata. Kích thước phụ thuộc:

- Kiểu index access method.
- Số lượng rows và độ rộng khóa.
- Số cột INCLUDE.
- Collation/operator class.
- Fillfactor.
- Insert/update/delete pattern.
- Page splits và cleanup.
- Version PostgreSQL và tính năng của access method.

Do đó không thể lấy số rows nhân một hằng số rồi kết luận index phải có kích thước bao nhiêu.

## 3. B-tree page split và mật độ index

B-tree tổ chức key theo thứ tự. Khi insert một key vào leaf page đã đầy, PostgreSQL có thể phải split page thành hai page và cập nhật cấu trúc cây.

Với workload random inserts:

- Key mới có thể rơi vào nhiều leaf pages.
- Một số page split xảy ra ở nhiều vị trí.
- Mật độ page có thể khác nhau.
- Index có thể cần thêm pages so với một lần build tuần tự.

Với sequential inserts vào key tăng dần, page split thường tập trung ở vùng cuối cây, nhưng điều này không có nghĩa workload nào cũng tạo index nhỏ nhất.

DELETE/UPDATE cũng có thể làm index entries trở thành dead hoặc không còn cần thiết. VACUUM cleanup và B-tree page deletion giúp tái sử dụng pages theo cơ chế của access method; không phải mọi page rỗng đều được ghép lại để làm file nhỏ ngay.

**Page split, dead entries và bloat có liên quan nhưng không phải một khái niệm duy nhất.**

## 4. Index bloat là gì?

Index bloat thường chỉ phần dung lượng vật lý mà index đang sử dụng vượt mức cần thiết cho tập dữ liệu và workload hiện tại, do mật độ page thấp, dead space, page splits hoặc lịch sử churn.

Ví dụ minh họa:

~~~text
Index trước churn:
  Leaf page A: [keys keys keys keys keys keys]
  Leaf page B: [keys keys keys keys keys keys]

Sau nhiều UPDATE/DELETE/INSERT:
  Leaf page A: [keys -- -- keys -- --]
  Leaf page B: [-- keys -- -- keys --]

Index đã có thể chứa nhiều page thưa hoặc dead space.
~~~

Đây là sơ đồ khái niệm; B-tree có cơ chế cleanup, page deletion, reuse và deduplication tùy version/access method.

### Bloat không đồng nghĩa với dead tuples

- Dead tuples là tuple versions trong heap không còn cần thiết với MVCC snapshot.
- Dead index entries là index references không còn cần cho row versions.
- Free space là vùng có thể tái sử dụng trong page.
- Bloat là nhận định về dung lượng dư/hiệu quả sử dụng page trong bối cảnh workload.

Một index lớn có thể hoàn toàn hợp lý nếu bảng có nhiều rows hoặc index key rộng. Một index có leaf density thấp có thể do fillfactor được đặt thấp có chủ đích để giảm page splits.

## 5. Dấu hiệu nào nên điều tra index bloat?

Một số tín hiệu:

- Index tăng kích thước nhanh hơn đáng kể so với số rows hoặc workload.
- Query dùng index phải đọc nhiều buffers hơn theo thời gian.
- Cache hit giảm vì index chiếm nhiều shared buffers/storage cache.
- B-tree leaf density thấp kéo dài, không phù hợp fillfactor/workload.
- Churn lớn nhưng VACUUM không cleanup được vì old snapshots.
- Một index chiếm phần lớn dung lượng bảng.
- Rebuild trong môi trường thử nghiệm làm index nhỏ hơn đáng kể và query/IO tốt hơn.

### Những dấu hiệu không đủ để kết luận

- Index lớn: có thể do dữ liệu thực sự lớn.
- Index có nhiều pages: có thể cần nhiều entries.
- idx_scan thấp: workload có thể chạy theo chu kỳ, hoặc index phục vụ constraint.
- VACUUM vừa chạy: không bảo đảm file index co lại.
- Disk tăng: có thể do heap, TOAST, WAL, temp files hoặc backup.
- Query chậm: có thể do query plan, lock, CPU, network hoặc cache.

**Không chạy REINDEX chỉ vì nhìn thấy một file index có kích thước lớn.**

## 6. Xác định kích thước table và index

Các hàm cơ bản:

| Hàm | Nội dung |
| --- | --- |
| `pg_relation_size(relation)` | Kích thước fork mặc định (thường main fork) của relation |
| `pg_table_size(relation)` | Table storage, bao gồm TOAST và các phần liên quan, không tính index |
| `pg_indexes_size(relation)` | Tổng dung lượng các index của table |
| `pg_total_relation_size(relation)` | Tổng table + TOAST + indexes |

Ví dụ xem kích thước một bảng:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders'::regclass))
        AS main_fork,
    pg_size_pretty(pg_table_size('public.orders'::regclass))
        AS table_storage,
    pg_size_pretty(pg_indexes_size('public.orders'::regclass))
        AS all_indexes,
    pg_size_pretty(pg_total_relation_size('public.orders'::regclass))
        AS total_storage;
~~~

Các hàm trả byte hoặc định dạng dễ đọc. Đừng cộng pg_table_size với pg_indexes_size rồi cộng thêm TOAST lần nữa; pg_table_size đã tính phần storage liên quan của table.

### Xem từng index

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(
        pg_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(indexname)
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(indexname)
) DESC;
~~~

Để truy vấn robust với schema/name có ký tự đặc biệt, cách dùng catalog và OID thường tốt hơn chuỗi tên ghép. Ví dụ:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_relation_size(idx.oid) AS index_bytes
FROM pg_index AS i
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY index_bytes DESC;
~~~

Đây là số đo kích thước, không phải tỷ lệ bloat.

## 7. Theo dõi hoạt động sử dụng index

pg_stat_user_indexes cho biết thống kê sử dụng index:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
~~~

Ý nghĩa:

- idx_scan: số lần bắt đầu scan index theo thống kê.
- idx_tup_read: số index entries được đọc.
- idx_tup_fetch: số live table rows được fetch qua index scan.

Đây là thống kê tích lũy theo chu kỳ/reset của statistics collector; không phải số đo chính xác về bloat hoặc toàn bộ giá trị của index.

### Index scan thấp có nghĩa nên drop?

Không. Index có thể:

- Phục vụ UNIQUE/PRIMARY KEY constraint.
- Được query theo chu kỳ.
- Phục vụ workload hiếm nhưng quan trọng.
- Được planner dùng cho query không thường xuyên.
- Hỗ trợ foreign key checks.

Trước khi drop index, kiểm tra dependencies, constraints, query logs, workload theo chu kỳ và thời gian quan sát đủ dài.

## 8. Dùng pgstattuple để quan sát dead/free space

Extension pgstattuple cung cấp thông tin vật lý về tuple, dead tuple và free space. Đây là extension bổ sung; cần quyền cài đặt phù hợp và có thể tiêu tốn I/O khi quét relation.

Trong database lab:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
~~~

Xem thống kê heap table:

~~~sql
SELECT *
FROM pgstattuple('public.orders'::regclass);
~~~

Một số cột quan trọng:

- table_len: tổng bytes của relation.
- tuple_count: số live tuples đếm được.
- tuple_len / tuple_percent: dung lượng/tỷ lệ live tuple data.
- dead_tuple_count: dead tuples đếm được.
- dead_tuple_len / dead_tuple_percent: dung lượng/tỷ lệ dead tuples.
- free_space / free_percent: free space.

### pgstattuple không phải lệnh chạy miễn phí

Hàm đầy đủ có thể scan toàn relation và tạo I/O đáng kể. Trên bảng lớn, chọn thời điểm và workload phù hợp. Một số hàm approximate giảm chi phí nhưng trả kết quả ước lượng.

pgstattuple trên heap cho biết heap storage; muốn điều tra B-tree, cần dùng hàm phù hợp như pgstatindex.

## 9. Dùng pgstatindex cho B-tree

pgstatindex thuộc extension pgstattuple và áp dụng cho B-tree index.

~~~sql
SELECT *
FROM pgstatindex('public.idx_orders_customer_created'::regclass);
~~~

Các trường thường hữu ích:

- version: phiên bản cấu trúc B-tree được báo cáo.
- tree_level: chiều cao cây.
- index_size: kích thước index.
- root_block_no: block root.
- internal_pages: số internal pages.
- leaf_pages: số leaf pages.
- empty_pages: số empty pages.
- deleted_pages: số deleted pages.
- avg_leaf_density: mật độ trung bình leaf pages.
- leaf_fragmentation: mức phân mảnh leaf pages theo định nghĩa hàm.

### Diễn giải avg_leaf_density

Mật độ thấp có thể gợi ý nhiều free space hoặc page thưa, nhưng cần xem fillfactor, kiểu dữ liệu, write pattern và mục đích của index.

Ví dụ:

- Fillfactor 70 có thể được đặt có chủ đích cho workload ghi ngẫu nhiên.
- Index vừa build lại có thể có density khác do fillfactor.
- Index tăng trưởng qua page splits có thể có density không đồng đều.
- Leaf fragmentation không tự động chứng minh query chậm.

**Không dùng một ngưỡng density cố định làm quy tắc REINDEX cho mọi index.**

## 10. pgstattuple_approx và chi phí đo

Có thể xem xét:

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders'::regclass);
~~~

Hàm approximate có thể dùng visibility map để giảm phần phải scan và ước lượng phần còn lại theo semantics của extension/version.

Lựa chọn:

| Phương pháp | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| pg_relation_size | Rất đơn giản, ít tốn kém | Chỉ đo size |
| pgstattuple | Đo tuple/dead/free space chi tiết | Có thể scan toàn relation |
| pgstattuple_approx | Có thể giảm công scan | Có sai số/ước lượng |
| pgstatindex | B-tree density/leaf metrics | Tốn I/O, chỉ phù hợp B-tree |
| Workload benchmark | Đo tác động thực tế | Cần môi trường và dữ liệu đại diện |

Không cài extension chỉ để có một con số nếu chính sách production không cho phép. Có thể đo trên replica/lab, nhưng nhớ replica có cache và workload khác primary.

## 11. REINDEX làm gì?

REINDEX xây dựng lại index bằng cách đọc dữ liệu nguồn và tạo cấu trúc index mới theo định nghĩa hiện tại.

~~~text
Index hiện tại
  |
  | đọc dữ liệu cần thiết
  v
Build index mới
  |
  | tạo pages, entries và metadata
  v
Thay index cũ bằng index mới
  |
  v
PostgreSQL sử dụng cấu trúc mới
~~~

Lợi ích có thể có:

- Loại bỏ bloat của index.
- Tạo lại B-tree pages với density theo fillfactor hiện tại.
- Rebuild index sau một số vấn đề corruption nếu heap/source data còn tốt.
- Chuyển index sang tablespace khác nếu dùng option phù hợp.
- Tạo lại cấu trúc sau thay đổi workload/index maintenance.

REINDEX không thay đổi SQL definition (các cột, expression, predicate, uniqueness) của index. Nó xây lại cấu trúc vật lý theo catalog definition.

### REINDEX không sửa mọi loại corruption

Nếu dữ liệu heap, storage device, filesystem hoặc memory bị hỏng, rebuild index có thể không giải quyết được nguyên nhân. Nếu dữ liệu nguồn chứa duplicate vi phạm UNIQUE, build unique index sẽ thất bại. Điều tra log, storage và integrity trước khi kết luận.

## 12. Các dạng REINDEX

Ví dụ cú pháp:

~~~sql
-- Xây lại một index
REINDEX INDEX public.idx_orders_customer_created;

-- Xây lại mọi index của một table
REINDEX TABLE public.orders;

-- Xây lại index của một schema
REINDEX SCHEMA public;

-- Xây lại index của database hiện tại
REINDEX DATABASE training_db;

-- Xây lại system catalog indexes của database hiện tại
REINDEX SYSTEM training_db;
~~~

Các dạng phạm vi rộng có thể gây tác động lớn. Cú pháp, quyền và hỗ trợ từng option thay đổi theo PostgreSQL version; kiểm tra tài liệu của server thực tế.

### Chọn phạm vi nhỏ nhất phù hợp

- Dấu hiệu chỉ ở một index: cân nhắc REINDEX INDEX.
- Nhiều index của một table cùng có vấn đề: REINDEX TABLE.
- Bảo trì schema/database diện rộng: lập kế hoạch riêng, không chạy tùy tiện.
- System catalog corruption: làm theo quy trình recovery chuyên biệt, có thể cần single-user mode trong một số trường hợp.

Không dùng REINDEX DATABASE như một cách “dọn dẹp định kỳ” thay cho theo dõi index.

## 13. REINDEX thông thường và lock

REINDEX thông thường có thể lấy ACCESS EXCLUSIVE lock trên bảng liên quan. Lock này chặn cả đọc lẫn ghi thông thường vào bảng trong thời gian rebuild.

Ví dụ:

~~~sql
REINDEX INDEX public.idx_orders_customer_created;
~~~

Trong thời gian lệnh chạy, ứng dụng có thể gặp:

- SELECT phải chờ.
- INSERT/UPDATE/DELETE phải chờ.
- Connection pool bị đầy bởi sessions đang đợi lock.
- API latency tăng hoặc timeout.
- DDL khác chờ lock liên quan.

### Khi nào dùng REINDEX thường?

- Có maintenance window.
- Bảng nhỏ, thời gian rebuild ngắn.
- Workload có thể dừng hoặc chuyển sang chế độ bảo trì.
- Cần cách đơn giản, ít phase hơn.
- Có đủ disk/IO và đã đánh giá lock impact.

REINDEX thường có thể nhanh hơn concurrent mode vì không cần duy trì khả năng truy cập song song trong toàn bộ quá trình. Nhưng downtime có thể đắt hơn thời gian tiết kiệm được.

## 14. REINDEX CONCURRENTLY là gì?

REINDEX CONCURRENTLY được thiết kế để rebuild index trong khi các session khác vẫn có thể đọc/ghi bảng trong phần lớn quá trình.

Ví dụ:

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

Khác với REINDEX thông thường, concurrent mode:

- Tạo một index thay thế.
- Dùng nhiều giai đoạn scan/validation.
- Chờ các transaction có thể còn dùng index cũ hoặc ảnh hưởng tới tính hợp lệ.
- Chuyển sang index mới khi đủ điều kiện.
- Dọn index cũ sau khi an toàn.

Đổi lại:

- Tốn thời gian hơn.
- Tốn thêm I/O/CPU.
- Cần thêm dung lượng cho index mới trong lúc index cũ vẫn tồn tại.
- Có thể chờ transaction lâu.
- Có thêm các hạn chế về loại relation/index và transaction context.

**CONCURRENTLY không có nghĩa là hoàn toàn không lock.** Nó tránh lock mạnh kéo dài chặn DML/SELECT, nhưng vẫn cần lock ở các phase và có thể xung đột với DDL hoặc concurrent maintenance khác.

## 15. Các giai đoạn của REINDEX CONCURRENTLY

Có thể hiểu quy trình ở mức khái niệm:

~~~text
1. Đăng ký index mới ở trạng thái chưa hợp lệ
       |
2. Chờ transaction cũ phù hợp kết thúc
       |
3. Build index mới bằng scan dữ liệu
       |
4. Chờ các transaction có thể ảnh hưởng
       |
5. Thực hiện scan/validation bổ sung
       |
6. Đánh dấu index mới hợp lệ và chuyển dependency
       |
7. Chờ snapshot cũ không còn cần index cũ
       |
8. Xóa index cũ
~~~

Chi tiết phase và số lần scan phụ thuộc phiên bản PostgreSQL. Điều cần nhớ:

- Concurrent build phải đảm bảo không bỏ sót thay đổi đồng thời.
- Với UNIQUE index, tính duy nhất phải được xác minh trong bối cảnh concurrent writes.
- Việc chờ transaction/snapshot có thể khiến lệnh kéo dài.
- Index cũ vẫn chiếm disk trong một phần thời gian.
- Một lệnh concurrent có thể thất bại hoặc bị cancel giữa các phase.

## 16. Hạn chế quan trọng của REINDEX CONCURRENTLY

### Không chạy trong transaction block

Lệnh concurrent reindex không được chạy bên trong explicit transaction block.

Sai:

~~~sql
BEGIN;
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
COMMIT;
~~~

Đúng: chạy lệnh riêng trong session ở chế độ autocommit:

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

Điều này cũng ảnh hưởng migration tools/framework thường tự wrap mọi migration trong một transaction. Phải cấu hình migration riêng để chạy ngoài transaction nếu tool/version hỗ trợ.

### Các hạn chế theo loại index/relation

Concurrent reindex có hạn chế đối với system catalogs, temporary tables và một số trường hợp partitioned indexes/relation đặc biệt. Hỗ trợ từng target form và restriction đã thay đổi theo PostgreSQL major versions.

Trước khi lập script hàng loạt:

1. Đọc trang REINDEX của đúng major version.
2. Xác định index có thuộc system catalog hay temporary relation không.
3. Kiểm tra parent/child partition indexes.
4. Kiểm tra index thuộc constraint và các dependency.
5. Chạy thử trên staging có schema tương tự.

Không giả định REINDEX DATABASE CONCURRENTLY hoặc concurrent reindex mọi partition được hỗ trợ giống nhau trên tất cả phiên bản.

## 17. REINDEX TABLE CONCURRENTLY

Trên các phiên bản hỗ trợ, có thể dùng:

~~~sql
REINDEX TABLE CONCURRENTLY public.orders;
~~~

Lệnh hướng tới rebuild các index của table theo concurrent semantics. Tuy nhiên, giới hạn theo version, partitioned table và loại index vẫn cần kiểm tra.

Nếu chỉ một index có vấn đề, chọn index đó thường giảm phạm vi tác động và dễ theo dõi hơn.

### Không chạy nhiều REINDEX CONCURRENTLY cho cùng table tùy tiện

PostgreSQL có giới hạn về concurrent reindexing trên cùng relation và lock conflicts. Chạy nhiều lệnh song song có thể chờ nhau, làm tăng I/O và kéo dài thời gian bảo trì.

Lập lịch tuần tự, theo dõi worker và xác nhận từng index hoàn tất.

## 18. Disk headroom khi concurrent reindex

Trong lúc concurrent reindex, index cũ phải còn tồn tại trong khi index mới được xây dựng. Vì vậy disk usage tạm thời có thể tăng đáng kể.

Ví dụ index cũ 80 GB:

~~~text
Trước:
  old index = 80 GB

Trong lúc build:
  old index = 80 GB
  new index = ước lượng gần kích thước build mới
  + WAL/temp/other concurrent writes

Sau khi hoàn tất:
  old index được loại bỏ
  new index còn lại
~~~

Không lấy 80 GB làm giới hạn disk cần chuẩn bị. Cần tính thêm:

- Kích thước index mới có thể khác cũ.
- WAL sinh ra trong quá trình build và DML đồng thời.
- Disk cho temp files/other operations.
- Replication/WAL retention.
- Headroom cho workload ứng dụng.
- Filesystem/container volume limits.

Nếu disk đầy giữa quá trình, reindex có thể thất bại và ảnh hưởng nhiều hơn một index.

## 19. WAL và replication impact

REINDEX tạo một cấu trúc index mới, phát sinh I/O và WAL theo cấu hình/loại operation. Với primary có physical standbys:

- WAL volume có thể tăng.
- Replica phải replay các thay đổi liên quan.
- Replication lag có thể tăng.
- WAL retention/replication slots có thể làm disk primary tăng.
- Standby query workload có thể cạnh tranh I/O.

Với logical replication, index DDL không được phát lại như row changes theo cùng cách physical replication; cần quản lý schema/index trên subscriber theo quy trình riêng.

Trước khi reindex index lớn, theo dõi WAL rate, replication lag, slot state và dung lượng archive/WAL filesystem.

## 20. REINDEX và VACUUM khác nhau thế nào?

| Tiêu chí | VACUUM | REINDEX |
| --- | --- | --- |
| Đối tượng chính | Heap table và liên quan | Index được chọn |
| Xử lý dead tuples | Có, theo visibility/cleanup rules | Build lại index từ dữ liệu nguồn |
| Xử lý dead index entries | Có thể cleanup qua index vacuum | Tạo cấu trúc index mới |
| Shrink index file mạnh | Không phải mục tiêu chung | Có thể giảm nếu index bloat |
| Shrink heap file | Không mặc định | Không |
| Freeze XID | Có | Không phải mục tiêu |
| Update planner statistics | Không thay ANALYZE | Không thay ANALYZE |
| Lock | Theo VACUUM mode | REINDEX mode có lock behavior riêng |

### Một ví dụ

Nếu orders có dead tuples vì UPDATE/DELETE nhiều:

1. Tìm nguyên nhân autovacuum không theo kịp.
2. Xử lý transaction horizon nếu có.
3. VACUUM để cleanup các tuples có thể dọn.
4. Đo lại index size/density.
5. Chỉ REINDEX nếu có bằng chứng index còn bloat đáng kể hoặc có lý do khác.

REINDEX không thay thế VACUUM. Nếu dead tuples vẫn tồn tại hoặc churn tiếp tục, index mới cũng sẽ chịu workload mới.

## 21. REINDEX và VACUUM FULL khác nhau

- REINDEX: xây lại index.
- VACUUM FULL: rewrite/compact heap table và các storage structures liên quan theo semantics của lệnh.
- CLUSTER: rewrite table theo thứ tự một index.

Nếu heap table phình, REINDEX không thu gọn heap. Nếu index phình, VACUUM FULL table không phải cách thay thế REINDEX theo mục tiêu index-specific.

| Mục tiêu | Công cụ thường xem xét |
| --- | --- |
| Dead tuples cần cleanup | VACUUM |
| Planner stats cũ | ANALYZE |
| Index bloat | REINDEX hoặc công cụ phù hợp |
| Heap/table bloat cần rewrite | VACUUM FULL, CLUSTER hoặc công cụ rewrite |
| Retention theo thời gian | Partition detach/drop |
| Index corruption | Điều tra và REINDEX khi source data/storage còn tin cậy |

Không chọn lệnh dựa trên tên gọi “dọn dẹp”. Chọn theo object và nguyên nhân.

## 22. REINDEX và CLUSTER

CLUSTER sắp xếp lại heap table theo index được chọn bằng cách rewrite relation. Nó có thể thay đổi physical row locations và cần lock mạnh.

REINDEX chỉ rebuild cấu trúc index; không sắp xếp lại heap theo thứ tự index.

Nếu mục tiêu là cải thiện locality khi query đọc range theo một index, CLUSTER có thể là một lựa chọn, nhưng:

- Thứ tự vật lý không tự được duy trì sau các lần ghi mới.
- Table rewrite tốn disk/IO và lock.
- Indexes khác có thể cần được xử lý theo quy trình CLUSTER.
- Không phải mọi workload đều hưởng lợi.

## 23. Index fillfactor

B-tree index có storage parameter `fillfactor`. Giá trị mặc định thường là 90, nhưng cần kiểm tra tài liệu/version và index access method.

Ví dụ:

~~~sql
ALTER INDEX public.idx_orders_customer_created
SET (fillfactor = 80);
~~~

Điều này đặt cấu hình cho lần build/rebuild tiếp theo; nó không tự di chuyển các entries hiện có để làm page cũ thưa hơn ngay.

Rebuild:

~~~sql
REINDEX INDEX public.idx_orders_customer_created;
~~~

Hoặc concurrent nếu phù hợp:

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

### Chọn fillfactor thế nào?

- Fillfactor thấp hơn để lại nhiều chỗ trống trong page mới, có thể giảm page splits cho workload insert/update ngẫu nhiên.
- Đổi lại index ban đầu lớn hơn và cache footprint có thể tăng.
- Workload đọc nhiều/ít thay đổi có thể phù hợp density cao hơn.
- Không có một fillfactor tối ưu cho mọi index.

**Fillfactor thấp không tự động chữa bloat.** Nó là trade-off giữa page density và không gian cho các lần ghi sau.

## 24. Fillfactor của table khác fillfactor của index

Table heap cũng có storage parameter fillfactor, nhưng semantics khác với B-tree index.

Ví dụ:

~~~sql
ALTER TABLE public.orders
SET (fillfactor = 85);
~~~

Table fillfactor có thể để lại chỗ trên heap page cho HOT updates trong một số workload. Index fillfactor kiểm soát độ đầy của index pages trong quá trình build/insert.

Không nhầm hai thiết lập hoặc thay cả hai mà không đo.

## 25. REINDEX có thể khắc phục index corruption không?

Trong một số trường hợp, index structure bị hỏng nhưng heap/source rows vẫn đúng. Rebuild index có thể tạo lại cấu trúc từ dữ liệu nguồn.

Quy trình cần thận trọng:

1. Ghi nhận lỗi và relation/index cụ thể.
2. Kiểm tra log PostgreSQL và storage/OS.
3. Xác định heap có dấu hiệu corruption không.
4. Kiểm tra constraint/dependency.
5. Chọn REINDEX thường hay CONCURRENTLY theo mức độ khẩn cấp và loại index.
6. Xác minh index sau rebuild.
7. Tiếp tục điều tra hardware/filesystem nếu corruption tái diễn.

### REINDEX không bảo đảm dữ liệu đúng

Nếu heap page đã hỏng, dữ liệu sai hoặc unique values trùng nhau, rebuild index có thể thất bại hoặc xây lại index từ dữ liệu nguồn không đầy đủ/không đúng. Không xem REINDEX như công cụ sửa ổ đĩa.

## 26. Xác minh index bằng amcheck

Extension amcheck cung cấp các hàm kiểm tra cấu trúc index. Với B-tree, có thể dùng bt_index_check và bt_index_parent_check theo quyền và options của version.

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;

SELECT bt_index_check('public.idx_orders_customer_created'::regclass);
~~~

Một số hình thức kiểm tra mạnh hơn có thể kiểm tra quan hệ parent/child và yêu cầu lock/tài nguyên khác.

amcheck kiểm tra tính nhất quán cấu trúc; nó không đo bloat và không thay backup/restore testing.

Không chạy kiểm tra nặng trên mọi index production một cách vô hạn; chọn index và lịch phù hợp.

## 27. Theo dõi index invalid sau concurrent failure

Concurrent reindex có thể thất bại hoặc bị cancel giữa các phase. Một tình huống cần nhận diện là index mới còn ở trạng thái invalid/not-ready.

Xem catalog:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
   OR NOT i.indisready
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Ý nghĩa khái quát:

- indisvalid: planner có thể xem index là hợp lệ cho query planning.
- indisready: index đã sẵn sàng nhận cập nhật từ các thao tác ghi theo trạng thái catalog.
- indislive: index còn tồn tại như một object live theo lifecycle.

Các trạng thái này là metadata nội bộ; cần đọc tài liệu version khi xử lý index invalid.

### Xử lý thế nào?

- Xác định index nào là index cũ, index mới hoặc index khác bị invalid.
- Kiểm tra constraint/dependencies.
- Xem log lỗi của lệnh REINDEX.
- Chọn reindex lại hoặc drop index invalid theo quy trình phù hợp.
- Không drop index đang backing primary key/unique/exclusion constraint mà chưa hiểu dependency.
- Xác minh query plans và constraint state sau cleanup.

Không chạy DROP INDEX hàng loạt chỉ dựa vào indisvalid = false.

## 28. Theo dõi tiến trình REINDEX

PostgreSQL có progress reporting cho CREATE INDEX và các operation liên quan theo version. Kiểm tra pg_stat_progress_create_index:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    current_locker_pid,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
ORDER BY pid;
~~~

Các cột và phase cụ thể phụ thuộc PostgreSQL version và loại operation. Khi REINDEX đang chạy, view có thể giúp quan sát phase build/index scan và các transaction đang được chờ.

### Progress không phải ETA chính xác

blocks_done / blocks_total không nhất thiết phản ánh phần trăm tổng thời gian còn lại. Các phase chờ transaction, validation, catalog swap hoặc cleanup có thể kéo dài dù counters ít thay đổi.

## 29. Theo dõi lock và session chờ

Kiểm tra session đang chờ lock:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_stat_activity AS a
LEFT JOIN pg_locks AS l
    ON l.pid = a.pid
WHERE a.datname = current_database()
ORDER BY a.query_start;
~~~

Trong maintenance window, quan sát:

- Session REINDEX.
- Session DML/SELECT đang chờ.
- DDL khác có thể xung đột.
- Transaction lâu giữ snapshot.
- Connection pool queue tăng.
- Lock wait duration.

Không cancel session chỉ dựa vào query age. Xác định PID, query, application owner và tác động trước khi terminate.

## 30. Lập kế hoạch trước REINDEX

Checklist trước khi chạy:

1. Xác định đúng database, schema, table và index.
2. Ghi lại index definition, uniqueness, predicate, INCLUDE columns và tablespace.
3. Đo kích thước index hiện tại.
4. Xác định bằng chứng bloat/corruption.
5. Kiểm tra index có backing constraint hay không.
6. Xác định PostgreSQL major version và hạn chế CONCURRENTLY.
7. Tính disk headroom cho index cũ + index mới + WAL/temp.
8. Đánh giá replication lag và WAL archive capacity.
9. Xác định maintenance window nếu dùng REINDEX thường.
10. Đặt lock_timeout/statement_timeout theo runbook nếu phù hợp.
11. Kiểm tra long-running transactions.
12. Chuẩn bị cách theo dõi progress, locks và errors.
13. Chuẩn bị hành động khi lệnh fail/cancel.
14. Chọn thời gian ít tải và thông báo owner liên quan.

### Xác nhận định nghĩa index trước khi rebuild

~~~sql
SELECT indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname = 'idx_orders_customer_created';
~~~

Ghi nhận definition để so sánh sau operation. Không cần tự drop/create index thủ công chỉ để rebuild nếu REINDEX đã đáp ứng mục tiêu.

## 31. Ví dụ REINDEX thường trong maintenance window

Giả sử index cụ thể có bằng chứng bloat và ứng dụng có thể chấp nhận lock:

~~~sql
-- Chạy ngoài transaction block theo maintenance plan.
REINDEX INDEX public.idx_orders_customer_created;
~~~

Trình tự vận hành:

1. Kiểm tra session/lock hiện tại.
2. Xác nhận ứng dụng đã vào maintenance window.
3. Chạy lệnh.
4. Theo dõi progress, disk và logs.
5. Chờ lệnh hoàn tất.
6. Kiểm tra index còn valid và definition không đổi.
7. Đo lại size/density.
8. Benchmark query đại diện.
9. Kết thúc maintenance khi ứng dụng hoạt động ổn định.

Không chạy ví dụ này trên index production thật nếu chưa xác nhận lock/downtime.

## 32. Ví dụ REINDEX CONCURRENTLY

Khi cần giữ khả năng DML:

~~~sql
-- Chạy riêng, không nằm trong BEGIN/COMMIT.
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

Quy trình:

1. Xác nhận phiên bản hỗ trợ.
2. Xác nhận loại index/relation được phép concurrent reindex.
3. Đảm bảo disk headroom.
4. Kiểm tra transaction lâu có thể làm lệnh chờ.
5. Chạy trong session autocommit.
6. Theo dõi pg_stat_progress_create_index, pg_stat_activity và logs.
7. Theo dõi WAL/replication lag.
8. Kiểm tra catalog index state sau khi hoàn tất.
9. Đo lại kích thước và query performance.

### Vì sao không wrap trong migration transaction?

Concurrent reindex tự quản lý nhiều transaction/phase. Nếu migration framework tự bọc DDL trong một transaction, PostgreSQL từ chối lệnh. Cần cấu hình migration ngoài transaction theo cách framework hỗ trợ.

## 33. Lock timeout và statement timeout

Có thể đặt session-level settings trước lệnh để tránh chờ lock quá lâu hoặc chạy không giới hạn theo policy:

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '30min';

REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

Các giá trị chỉ là ví dụ. lock_timeout giới hạn thời gian chờ mỗi lần lấy lock theo semantics PostgreSQL; statement_timeout giới hạn thời gian statement. Với concurrent reindex có nhiều phase, hãy hiểu timeout và cancellation có thể để lại trạng thái cần kiểm tra.

Nếu dùng SET LOCAL, cần transaction block, nhưng concurrent reindex không chạy trong transaction block. Vì vậy ví dụ dùng SET ở session và cần reset hoặc đóng session sau khi hoàn thành.

## 34. Chọn REINDEX hay tạo index mới CONCURRENTLY?

Có hai kỹ thuật liên quan nhưng khác mục tiêu:

- REINDEX INDEX CONCURRENTLY: rebuild index hiện tại theo definition đang có.
- CREATE INDEX CONCURRENTLY: tạo một index mới với definition mới.

Nếu cần thay đổi key columns, predicate, expression hoặc INCLUDE columns, REINDEX không làm được; cần tạo index mới, kiểm tra usage/constraints rồi migration theo quy trình riêng.

Ví dụ tạo index mới:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_customer_status
ON public.orders (customer_id, status);
~~~

Đây là thao tác thay đổi schema, không phải cách thay thế REINDEX chỉ để xử lý bloat. Cần tránh tạo index trùng chức năng không cần thiết.

## 35. Index UNIQUE và PRIMARY KEY

REINDEX giữ lại định nghĩa UNIQUE/PRIMARY KEY. Khi rebuild, PostgreSQL phải đảm bảo dữ liệu thỏa uniqueness.

Nếu có dữ liệu vi phạm uniqueness do corruption hoặc trạng thái bất thường, rebuild có thể thất bại.

Không xóa constraint chỉ để REINDEX thành công. Trước tiên:

- Kiểm tra dữ liệu trùng theo business key.
- Kiểm tra catalog constraint/index dependency.
- Xác định nguyên nhân corruption.
- Lập kế hoạch khôi phục đúng constraint.
- Xác minh replica/schema consistency.

### Kiểm tra constraint liên quan

~~~sql
SELECT
    conname,
    contype,
    conrelid::regclass AS table_name,
    conindid::regclass AS supporting_index
FROM pg_constraint
WHERE conindid = 'public.idx_orders_customer_created'::regclass;
~~~

Nếu query trả về row, index đang hỗ trợ một constraint. Hãy giữ dependency này trong kế hoạch.

## 36. REINDEX trong hệ thống có partition

Một partitioned table có thể có parent partitioned index và các child indexes trên từng partition.

~~~sql
SELECT
    parent_index.oid::regclass AS parent_index,
    child_index.oid::regclass AS child_index,
    child_table.oid::regclass AS child_table
FROM pg_inherits AS inh
JOIN pg_class AS parent_index
    ON parent_index.oid = inh.inhparent
JOIN pg_class AS child_index
    ON child_index.oid = inh.inhrelid
JOIN pg_index AS child_i
    ON child_i.indexrelid = child_index.oid
JOIN pg_class AS child_table
    ON child_table.oid = child_i.indrelid
WHERE parent_index.oid = 'public.idx_partitioned_orders'::regclass;
~~~

Truy vấn trên minh họa catalog relationship; cần điều chỉnh theo schema/index thực tế.

### Vận hành

- Xác định parent và child indexes.
- Xem partition nào thực sự có bloat.
- Kiểm tra hỗ trợ concurrent reindex theo version.
- Nếu cần, xử lý từng leaf index theo trình tự.
- Không bỏ qua tính hợp lệ của partitioned index parent.
- Kiểm tra attach/detach partition operations có đang chạy không.

Partitioned index concurrency có hạn chế thay đổi theo version. Luôn xác minh tài liệu của server cụ thể trước khi viết script tự động.

## 37. Reindex trong schema/database rộng

REINDEX SCHEMA, REINDEX DATABASE và REINDEX SYSTEM có phạm vi lớn. Một database có hàng nghìn indexes có thể tạo maintenance workload dài và peak disk usage cao.

Không chạy theo kiểu:

~~~sql
REINDEX DATABASE training_db;
~~~

trong giờ cao điểm mà không biết nó sẽ rebuild bao nhiêu index và lock những relation nào.

Trước khi chạy diện rộng:

- Inventory index count/size.
- Chọn scope cụ thể.
- Kiểm tra lock impact.
- Đánh giá tablespace/disk capacity.
- Lên thứ tự theo mức quan trọng.
- Theo dõi replication và workload.
- Có phương án pause/resume theo từng relation nếu công cụ và operation cho phép.

## 38. Reindex system catalogs

System catalogs chứa metadata quan trọng của PostgreSQL. Reindex catalog indexes có thể cần trong tình huống corruption đặc biệt.

Không coi REINDEX SYSTEM là thao tác bảo trì thường xuyên. Nếu corruption khiến server không thể hoạt động bình thường, quy trình có thể yêu cầu single-user mode hoặc hướng dẫn recovery theo version.

- Sao lưu/đảm bảo backup hợp lệ.
- Xác định catalog và index bị lỗi.
- Đọc PostgreSQL documentation về catalog reindex.
- Không tự drop catalog indexes.
- Có DBA/incident procedure và quyền vận hành phù hợp.

## 39. REINDEX và tablespace

Nếu muốn đặt index mới vào tablespace khác, PostgreSQL hỗ trợ option tablespace theo syntax/version phù hợp.

Ví dụ dạng option:

~~~sql
REINDEX (TABLESPACE fast_index_space)
INDEX public.idx_orders_customer_created;
~~~

Điều này có thể hữu ích khi chuyển index sang storage tier khác, nhưng cần:

- Tablespace tồn tại và được phép truy cập.
- Đủ dung lượng trên cả nguồn/đích.
- Kiểm tra quyền.
- Tính tác động replication/backup.
- Xác minh sau khi rebuild index thực sự ở tablespace mong muốn.

Đừng nhầm tablespace index với tablespace của heap table.

## 40. Sau REINDEX có cần ANALYZE không?

REINDEX xây dựng lại index; nó không phải ANALYZE table và không thay planner statistics.

Trong nhiều trường hợp, REINDEX không yêu cầu ANALYZE chỉ vì index đã được rebuild. Nhưng nếu workload/schema/data distribution cũng vừa thay đổi, statistics có thể cần cập nhật riêng.

~~~sql
ANALYZE public.orders;
~~~

Chỉ chạy khi có lý do về planner stats. Không gộp mọi lệnh maintenance vào một đợt mà không xác định mục tiêu từng lệnh.

## 41. Sau REINDEX cần kiểm tra gì?

### 1. Index state

~~~sql
SELECT
    i.indisvalid,
    i.indisready,
    i.indislive,
    idx.oid::regclass AS index_name
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
WHERE idx.oid = 'public.idx_orders_customer_created'::regclass;
~~~

### 2. Kích thước

~~~sql
SELECT
    pg_size_pretty(pg_relation_size(
        'public.idx_orders_customer_created'::regclass
    )) AS index_size;
~~~

### 3. Index definition

~~~sql
SELECT indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname = 'idx_orders_customer_created';
~~~

### 4. Query plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at
LIMIT 100;
~~~

### 5. Workload impact

- Query p50/p95/p99.
- Buffer reads/hits.
- CPU/IO.
- Lock waits.
- WAL/replication lag.
- Index size.
- Disk headroom.

Index nhỏ hơn không tự động có nghĩa query nhanh hơn. Planner vẫn có thể chọn plan khác hoặc bottleneck nằm ở nơi khác.

## 42. Vì sao index có thể lớn lại sau REINDEX?

Sau rebuild, workload tiếp tục ghi:

- INSERT tạo entries mới.
- UPDATE thay đổi indexed columns.
- DELETE tạo entries cần cleanup.
- B-tree page split tiếp tục xảy ra.
- Fillfactor và key distribution ảnh hưởng page density.

Nếu nguyên nhân gốc là churn hoặc schema/index design, index sẽ lại phát triển. REINDEX là thao tác bảo trì theo tình trạng, không thay thế xử lý workload.

## 43. Có nên REINDEX định kỳ?

Không có lịch chung như “mỗi tuần REINDEX toàn database” phù hợp mọi hệ thống.

Một lịch định kỳ có thể gây:

- I/O spikes không cần thiết.
- WAL/replication load.
- Disk peak.
- Lock contention nếu dùng mode thường.
- Cache churn.
- Rebuild index vốn đang khỏe mạnh.

Thay vào đó:

1. Thu thập size và workload metrics.
2. Đo bloat trên các index nghi ngờ.
3. Xác định trend qua thời gian.
4. Tìm nguyên nhân dead tuple/page split.
5. Chọn index có lợi ích dự kiến rõ.
6. Reindex có kiểm soát.
7. So sánh trước/sau.

## 44. Khi nào không nên REINDEX?

Không nên bắt đầu reindex khi:

- Chỉ có một con số index size lớn mà không có baseline.
- Disk gần đầy, không đủ chỗ cho replacement index.
- Replica/WAL storage đang có vấn đề.
- Long-running transactions làm concurrent operation chờ kéo dài.
- Workload đang ở peak và không thể chấp nhận thêm I/O.
- Index definition/dependency chưa được ghi nhận.
- Corruption có thể nằm ở heap/storage chứ không phải index.
- Unique data có dấu hiệu vi phạm constraint.
- Chưa xác định PostgreSQL version và restriction.
- Có DDL/partition maintenance đang chạy.

Nếu query chậm do thiếu index hoặc sai index definition, REINDEX chỉ build lại index cũ; cần giải quyết query design riêng.

## 45. Các lỗi thường gặp

1. **Dùng REINDEX để sửa table bloat**, trong khi REINDEX chỉ rebuild index.
2. **Nhầm VACUUM thường với REINDEX**, dù chúng có mục tiêu khác nhau.
3. **Chạy REINDEX thông thường giờ cao điểm**, chặn SELECT/DML do lock mạnh.
4. **Tưởng CONCURRENTLY không lấy lock nào**, rồi bỏ qua lock waits và DDL conflicts.
5. **Chạy REINDEX CONCURRENTLY trong BEGIN/COMMIT**, khiến PostgreSQL từ chối.
6. **Không kiểm tra version**, dùng option/relation form không được hỗ trợ.
7. **Reindex toàn database không có inventory**, gây I/O và lock impact lớn.
8. **Không tính disk headroom**, làm filesystem đầy giữa operation.
9. **Không theo dõi WAL và replica lag**.
10. **Tăng workers hoặc chạy nhiều reindex song song**, làm storage contention tăng.
11. **Coi index size lớn là bloat**, không tính data/index key width.
12. **Coi avg_leaf_density thấp luôn là lỗi**, bỏ qua fillfactor có chủ đích.
13. **Dùng pgstattuple/pgstatindex trên mọi bảng production cùng lúc**, gây scan I/O lớn.
14. **Không phân biệt heap bloat, index bloat và TOAST size**.
15. **Nghĩ VACUUM sẽ luôn thu nhỏ index file về filesystem**.
16. **Drop index invalid mà không kiểm tra constraint dependency**.
17. **Bỏ qua index mới invalid sau concurrent failure**.
18. **Nghĩ REINDEX sửa được heap corruption hoặc disk corruption**.
19. **Không xác minh UNIQUE/PRIMARY KEY sau rebuild**.
20. **Không so sánh query plan và latency trước/sau**.
21. **Đặt fillfactor thấp nhưng không tính index size tăng**.
22. **Tạo index mới CONCURRENTLY để thay đổi definition rồi quên dọn index cũ**.
23. **Dùng REINDEX định kỳ dù không có bằng chứng bloat**.
24. **Không kiểm tra partition parent/child index state**.
25. **Không kiểm tra log và tiến trình sau timeout/cancel**.

## 46. Bài tập thực hành có đáp án

Các ví dụ sử dụng schema public.orders giả định có sẵn. Chỉ chạy lệnh DDL/maintenance trong database lab hoặc theo maintenance plan được duyệt.

### Bài 1. REINDEX làm gì?

**Đáp án:** Xây dựng lại cấu trúc index từ dữ liệu nguồn theo định nghĩa index hiện tại.

### Bài 2. REINDEX có thu gọn heap table không?

**Đáp án:** Không. Nó rebuild index; heap bloat cần VACUUM/rewriting strategy riêng.

### Bài 3. Viết lệnh reindex một index

~~~sql
REINDEX INDEX public.idx_orders_customer_created;
~~~

**Đáp án:** Rebuild đúng index được chỉ định.

### Bài 4. REINDEX TABLE làm gì?

**Đáp án:** Rebuild các index của table được chỉ định theo semantics PostgreSQL version.

### Bài 5. Vì sao REINDEX thường gây downtime?

**Đáp án:** Nó lấy lock mạnh trên table liên quan, có thể chặn reads và writes trong thời gian rebuild.

### Bài 6. Viết REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

**Đáp án:** Rebuild index qua các phase để DML có thể tiếp tục trong phần lớn thời gian.

### Bài 7. Có thể đặt concurrent reindex trong BEGIN/COMMIT không?

**Đáp án:** Không. Nó không chạy trong transaction block.

### Bài 8. CONCURRENTLY có nghĩa không có lock?

**Đáp án:** Không. Vẫn có lock ở một số phase và có thể chờ transaction/DDL.

### Bài 9. Vì sao concurrent reindex cần thêm disk?

**Đáp án:** Index cũ vẫn tồn tại trong khi index thay thế được xây dựng; cần chỗ cho cả hai cùng các overhead liên quan.

### Bài 10. REINDEX và VACUUM khác nhau?

**Đáp án:** VACUUM xử lý dead tuples/visibility/freeze; REINDEX rebuild index structure.

### Bài 11. VACUUM FULL khác REINDEX?

**Đáp án:** VACUUM FULL rewrite/compact heap relation; REINDEX chỉ rebuild index được chọn.

### Bài 12. pg_relation_size đo gì?

**Đáp án:** Kích thước fork mặc định, thường là main fork, của relation.

### Bài 13. pg_indexes_size đo gì?

**Đáp án:** Tổng kích thước các indexes thuộc table.

### Bài 14. pg_total_relation_size đo gì?

**Đáp án:** Tổng table storage, TOAST và indexes liên quan.

### Bài 15. pgstatindex dùng cho loại index nào?

**Đáp án:** B-tree indexes qua extension pgstattuple.

### Bài 16. avg_leaf_density thấp có luôn là bloat?

**Đáp án:** Không. Phải xét fillfactor, write pattern, page splits và mục tiêu thiết kế.

### Bài 17. pgstattuple có thể tốn kém không?

**Đáp án:** Có. Full scan relation có thể gây I/O; cần chọn thời điểm và dùng approximate nếu phù hợp.

### Bài 18. idx_scan thấp có nghĩa nên drop index?

**Đáp án:** Không. Index có thể phục vụ constraint hoặc workload hiếm nhưng quan trọng.

### Bài 19. REINDEX có thay đổi index definition không?

**Đáp án:** Không. Nó xây lại theo definition hiện tại; muốn đổi columns/predicate cần CREATE INDEX mới.

### Bài 20. Fillfactor thấp có lợi ích gì?

**Đáp án:** Để lại free space trong pages mới, có thể giảm page splits cho workload ghi; đổi lại index lớn hơn.

### Bài 21. ALTER INDEX SET fillfactor có rebuild ngay không?

**Đáp án:** Không. Cấu hình có tác dụng cho page build/insert tiếp theo; muốn áp dụng cho toàn cấu trúc hiện tại cần rebuild.

### Bài 22. Vì sao long-running transaction ảnh hưởng cleanup?

**Đáp án:** Snapshot cũ có thể giữ tuple versions cần thiết; VACUUM/index cleanup không thể loại bỏ những entries còn cần.

### Bài 23. Index invalid sau concurrent failure xem ở đâu?

**Đáp án:** Catalog pg_index với indisvalid, indisready và indislive.

### Bài 24. Có thể drop mọi index indisvalid=false không?

**Đáp án:** Không. Kiểm tra dependency/constraint và xác định index cũ/mới trước khi cleanup.

### Bài 25. pg_stat_progress_create_index dùng để làm gì?

**Đáp án:** Theo dõi phase/progress của CREATE INDEX và operation liên quan như concurrent reindex tùy version.

### Bài 26. REINDEX có thay ANALYZE không?

**Đáp án:** Không. ANALYZE cập nhật planner statistics.

### Bài 27. Khi nào chọn REINDEX thường?

**Đáp án:** Khi có maintenance window và chấp nhận lock mạnh để hoàn tất đơn giản hơn.

### Bài 28. Khi nào cân nhắc REINDEX CONCURRENTLY?

**Đáp án:** Khi cần giữ DML/reads trong phần lớn thời gian và có đủ disk/I/O, đồng thời index/relation được hỗ trợ.

### Bài 29. B-tree page split có thể làm gì?

**Đáp án:** Chia leaf page khi không còn chỗ cho entry mới, ảnh hưởng số page và density.

### Bài 30. Nếu index nhỏ lại sau REINDEX nhưng query vẫn chậm, kiểm tra gì?

**Đáp án:** Query plan, buffers, heap/TOAST, statistics, locks, I/O, CPU, network và index definition; size reduction không tự bảo đảm latency giảm.

## 47. Checklist triển khai REINDEX

- [ ] Xác định object là heap, TOAST hay index.
- [ ] Xác định index cụ thể và ghi lại definition.
- [ ] Đo kích thước trước khi thao tác.
- [ ] Dùng pgstatindex/pgstattuple khi có bằng chứng và được phép.
- [ ] Phân biệt bloat với fillfactor/workload bình thường.
- [ ] Kiểm tra constraint/dependencies.
- [ ] Kiểm tra PostgreSQL major version và concurrent restrictions.
- [ ] Chọn REINDEX thường hoặc CONCURRENTLY theo downtime budget.
- [ ] Không chạy concurrent reindex trong transaction block.
- [ ] Tính disk headroom cho index cũ + mới + WAL/temp.
- [ ] Kiểm tra long-running transactions và lock waits.
- [ ] Theo dõi pg_stat_progress_create_index.
- [ ] Theo dõi CPU, I/O, WAL và replication lag.
- [ ] Không chạy hàng loạt index reindex song song tùy tiện.
- [ ] Kiểm tra invalid index sau failure/cancel.
- [ ] Không drop index constraint-backed khi chưa xử lý dependency.
- [ ] Xác minh indisvalid/indisready/indislive.
- [ ] Đo size/density sau rebuild.
- [ ] So sánh query plan và latency trước/sau.
- [ ] Nếu heap bloat là nguyên nhân, dùng chiến lược VACUUM/rewrite phù hợp.
- [ ] Ghi lại lý do, kết quả và thời điểm rebuild.
- [ ] Không REINDEX định kỳ nếu không có bằng chứng cần thiết.

## 48. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) — cú pháp, lock, CONCURRENTLY, restriction và các target forms.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, VACUUM và maintenance.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — VACUUM, FULL và options.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index build, CONCURRENTLY và fillfactor.
- [Index Access Methods](https://www.postgresql.org/docs/current/indexes-types.html) — các loại index.
- [B-tree Indexes](https://www.postgresql.org/docs/current/btree.html) — B-tree behavior.
- [Index Storage Parameters](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-STORAGE-PARAMETERS) — fillfactor và các storage options.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_user_indexes, pg_stat_activity.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — pg_stat_progress_create_index.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple/free-space inspection extension.
- [amcheck](https://www.postgresql.org/docs/current/amcheck.html) — index consistency checks.
- [System Catalog pg_index](https://www.postgresql.org/docs/current/catalog-pg-index.html) — indisvalid, indisready và index metadata.
- [System Catalog pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html) — index/constraint dependencies.
- [Lock Monitoring](https://www.postgresql.org/docs/current/monitoring-locks.html) — lock views và diagnostics.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — index placement và storage.
- [Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — parent/child indexes và partition maintenance.

Các URL /current/ trỏ tới tài liệu hiện hành. REINDEX CONCURRENTLY, partitioned indexes, progress columns và một số options thay đổi theo major version; xác nhận trên server thực tế trước khi chạy production.

## 49. Tổng kết

**REINDEX xây dựng lại cấu trúc index. REINDEX CONCURRENTLY giảm thời gian chặn hoạt động đọc/ghi bằng quy trình nhiều phase, nhưng cần thêm tài nguyên và vẫn có các điểm chờ/lock.**

Những điểm cần nhớ:

1. **Đo trước khi rebuild.** Index lớn không tự chứng minh bloat; dùng size, B-tree density, workload và query plan.
2. **Phân biệt heap bloat với index bloat.** REINDEX không thu gọn heap table hay TOAST.
3. **VACUUM và REINDEX bổ sung cho nhau.** VACUUM cleanup dead tuples/visibility/freeze; REINDEX tạo cấu trúc index mới.
4. **REINDEX thông thường lấy lock mạnh**, có thể chặn SELECT và DML; dùng khi có maintenance window phù hợp.
5. **REINDEX CONCURRENTLY cho phép workload tiếp tục trong phần lớn thời gian**, nhưng có nhiều phase, có thể chờ transaction và cần thêm disk/WAL.
6. **Không chạy REINDEX CONCURRENTLY trong transaction block.** Migration tool phải hỗ trợ chạy DDL ngoài transaction.
7. **Tính disk headroom và replication impact** trước khi rebuild index lớn.
8. **Fillfactor là trade-off** giữa mật độ page và khoảng trống cho write workload; thay đổi setting không tự rebuild pages cũ.
9. **Kiểm tra invalid index và dependency** nếu concurrent reindex thất bại hoặc bị cancel.
10. **REINDEX không thay ANALYZE, không sửa mọi loại corruption và không thay thế thiết kế index đúng.**
11. **Không reindex định kỳ theo lịch cứng** khi chưa có bằng chứng lợi ích.
12. **Xác minh sau operation** bằng catalog state, size, query plan, latency và replica health.

Khi xác định đúng index cần bảo trì, chọn lock mode phù hợp và đo tác động trước/sau, bạn có thể xử lý index bloat mà vẫn kiểm soát rủi ro cho PostgreSQL production.
