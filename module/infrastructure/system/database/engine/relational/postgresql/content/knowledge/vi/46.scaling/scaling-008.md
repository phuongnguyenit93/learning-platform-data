# amcheck, pageinspect, pg_buffercache và công cụ khảo sát nội bộ trong PostgreSQL

PostgreSQL cung cấp nhiều công cụ để khảo sát trạng thái bên trong database khi cần điều tra index, heap pages, buffer cache, dead tuples, visibility map, WAL và hoạt động truy vấn. Các công cụ này hữu ích khi vận hành chuyên sâu, nhưng không thay thế lẫn nhau.

- **amcheck** kiểm tra một số dạng nhất quán cấu trúc của index và heap.
- **pageinspect** đọc cấu trúc vật lý của page và tuple để phục vụ điều tra chi tiết.
- **pg_buffercache** quan sát các page đang nằm trong shared buffer cache tại thời điểm truy vấn.
- Các extension và tiện ích như **pgstattuple**, **pg_freespacemap**, **pg_visibility**, **pg_walinspect**, **pg_stat_statements**, **pg_stat_io**, **pg_amcheck**, **pg_checksums** và **pg_verifybackup** bổ sung góc nhìn về storage, visibility, WAL, workload và backup.

Những công cụ này thường được gọi là công cụ khảo sát nội bộ vì chúng giúp người quản trị nhìn sâu hơn vào cách PostgreSQL lưu trữ và xử lý dữ liệu. Một số thao tác chỉ đọc, nhưng vẫn có thể tạo tải I/O/CPU đáng kể; một số công cụ cần quyền cao và có thể làm lộ thông tin nhạy cảm. Vì vậy, phải xác định mục tiêu, phạm vi, quyền, thời điểm và cách lưu evidence trước khi chạy.

~~~mermaid
flowchart TD
    A["Câu hỏi điều tra"] --> B{"Cần xác minh điều gì?"}
    B -->|"Index/heap consistency"| C["amcheck / pg_amcheck"]
    B -->|"Page và tuple layout"| D["pageinspect"]
    B -->|"Page đang ở shared buffers"| E["pg_buffercache"]
    B -->|"Dead tuples / free space"| F["pgstattuple / pg_freespacemap"]
    B -->|"Visibility map"| G["pg_visibility"]
    B -->|"WAL records"| H["pg_walinspect / pg_waldump"]
    B -->|"Query workload"| I["pg_stat_statements / pg_stat_io"]
    C --> J["Đối chiếu logs, catalog, backup"]
    D --> J
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
~~~

Bài học thuộc chương **Mở rộng**, module **Database Engine Relational PostgreSQL**. Nội dung tập trung vào cách cài đặt, sử dụng, diễn giải và vận hành an toàn các công cụ khảo sát nội bộ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt vai trò và giới hạn của amcheck, pageinspect và pg_buffercache.
2. Kiểm tra extension có sẵn và cài extension trong đúng database.
3. Xác định quyền cần thiết và áp dụng least privilege.
4. Dùng amcheck để kiểm tra B-tree index và một số dạng heap consistency.
5. Dùng pg_amcheck để tự động hóa kiểm tra trên nhiều object/database.
6. Dùng pageinspect để đọc page header, heap tuple và B-tree page.
7. Hiểu vì sao pageinspect là công cụ forensic, không phải công cụ sửa chữa.
8. Dùng pg_buffercache để khảo sát page residency, dirty buffers và usage count.
9. Đọc pgstattuple, pg_freespacemap và pg_visibility.
10. Dùng pg_walinspect và pg_waldump để khảo sát WAL.
11. Kết hợp pg_stat_statements, pg_stat_io và các statistics views.
12. Phân biệt corruption evidence với query plan hoặc cache behavior bất thường.
13. Xây dựng quy trình khảo sát có phạm vi, evidence và stop conditions.
14. Tránh chạy kiểm tra nặng hoặc cấp quyền superuser không cần thiết.
15. Biết khi nào cần dừng ghi dữ liệu, tạo backup/clone và escalation.

## 2. Extension và tiện ích nội bộ là gì?

PostgreSQL có một số extension nằm trong bộ source/contrib hoặc package đi kèm, nhưng việc chúng có sẵn phụ thuộc cách cài đặt, distribution và version.

Extension có thể cung cấp SQL functions, views, operators, types, shared libraries, background workers hoặc catalog objects. Cài extension trong một database không tự động cài nó trong mọi database của cluster. Shared library có thể được cài ở cấp máy chủ, nhưng SQL objects của extension thường được tạo riêng từng database.

### Kiểm tra extension có sẵn

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
WHERE name IN (
    'amcheck',
    'pageinspect',
    'pg_buffercache',
    'pgstattuple',
    'pg_freespacemap',
    'pg_visibility',
    'pg_walinspect',
    'pg_stat_statements'
)
ORDER BY name;
~~~

Diễn giải:

- Có dòng trong pg_available_extensions: server tìm thấy extension control files và biết version có thể cài.
- installed_version khác NULL: extension đã được tạo trong database hiện tại.
- Không có dòng: package có thể chưa cài, extension không được build cho platform/version, hoặc server không tìm thấy extension files.

### Cài extension

Ví dụ:

~~~sql
CREATE EXTENSION amcheck;
CREATE EXTENSION pageinspect;
CREATE EXTENSION pg_buffercache;
~~~

Có thể dùng IF NOT EXISTS nếu mục đích là tạo khi chưa tồn tại:

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;
~~~

IF NOT EXISTS không xác minh extension hiện có đúng version hoặc đúng schema. Kiểm tra lại metadata sau khi cài:

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema,
    pg_get_userbyid(extowner) AS extension_owner
FROM pg_extension
WHERE extname IN ('amcheck', 'pageinspect', 'pg_buffercache')
ORDER BY extname;
~~~

Một số extension cần package OS trước khi CREATE EXTENSION. Ví dụ trên Debian/Ubuntu, package contrib có thể được phân phối riêng theo major version; tên package phụ thuộc repository/distribution. Trên managed database, provider có thể giới hạn danh sách extension được hỗ trợ.

Không chạy lệnh cài package hoặc restart database khi chưa xác định platform và change plan.

## 3. Chọn công cụ theo câu hỏi

| Câu hỏi | Công cụ phù hợp | Kết quả chính |
| --- | --- | --- |
| B-tree index có dấu hiệu sai cấu trúc không? | amcheck, pg_amcheck | Báo lỗi kiểm tra index |
| Heap page có lỗi cấu trúc được công cụ nhận diện không? | amcheck verify_heapam trên version hỗ trợ | Các lỗi heap được phát hiện |
| Một page chứa header/tuple nào? | pageinspect | Raw page và decoded fields |
| Page của relation có đang ở shared buffers không? | pg_buffercache | Buffer residency snapshot |
| Table có bao nhiêu dead tuples/free space? | pgstattuple | Tuple/dead/free-space statistics |
| Free space map ghi nhận gì? | pg_freespacemap | Free space theo heap block |
| Page có all-visible/all-frozen không? | pg_visibility | Visibility map state |
| WAL range chứa record nào? | pg_walinspect, pg_waldump | WAL record metadata/details |
| Query nào tiêu tốn buffer/time/temp I/O? | pg_stat_statements | Query-level accumulated statistics |
| Backend nào tạo I/O? | pg_stat_io | I/O counters theo backend/object/context |
| Backup file có phù hợp manifest? | pg_verifybackup | Backup validation result |
| Cluster checksum có lỗi không? | pg_checksums | Checksum verification |
| Backup/cluster metadata là gì? | pg_controldata | Control file information |

Một công cụ chỉ trả lời một phần câu hỏi. Ví dụ, amcheck không xác minh toàn bộ business data, pg_buffercache không đo trực tiếp disk latency và pageinspect không tự sửa page bị hỏng.

## 4. Quyền truy cập và an toàn

Các extension khảo sát nội bộ có thể đọc raw database pages, WAL metadata, query text hoặc thông tin của nhiều database. Quyền mặc định thay đổi theo extension và major version.

Nguyên tắc:

- Dùng role DBA/diagnostic chuyên biệt.
- Cấp đúng quyền cần thiết cho từng công cụ.
- Không cấp SUPERUSER cho application roles.
- Không mở EXECUTE trên các hàm nhạy cảm cho PUBLIC nếu không có lý do.
- Không lưu query text/tuple data chứa PII vào evidence repository không được bảo vệ.
- Thử trên staging/clone trước khi chạy kiểm tra nặng.
- Ghi lại database, relation, index, block range và thời điểm.
- Theo dõi I/O, CPU, lock waits và application latency trong lúc khảo sát.

### Kiểm tra quyền extension

Xem extension functions:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_userbyid(p.proowner) AS function_owner,
    p.proacl
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname IN (
    'public',
    'amcheck',
    'pageinspect',
    'pg_buffercache'
)
ORDER BY n.nspname, p.proname;
~~~

Schema extension có thể được đặt khác public. Dùng pg_extension để xác định schema thực tế.

Một số hàm của pageinspect và các công cụ đọc raw storage bị giới hạn cho superuser hoặc role được cấp quyền phù hợp. Không giả định mọi extension có cùng policy. Đọc phần Privileges trong tài liệu đúng version và kiểm tra ACL đang có.

### Tách quyền đọc và quyền sửa

Các công cụ được đề cập chủ yếu phục vụ khảo sát. Nếu phát hiện corruption, thao tác sửa có thể bao gồm restore, REINDEX, rebuild object, failover hoặc phục hồi từ backup. Đó là một change/incident riêng với approval và recovery plan, không phải bước tiếp theo tự động của câu lệnh kiểm tra.

## 5. amcheck là gì?

amcheck là extension cung cấp các hàm kiểm tra một số dạng nhất quán cấu trúc trong PostgreSQL. Trọng tâm chính là B-tree indexes, ngoài ra các phiên bản hỗ trợ còn cung cấp kiểm tra heap.

amcheck hữu ích khi:

- Có nghi ngờ index corruption.
- Storage/controller có lỗi hoặc reset bất thường.
- Server logs ghi lỗi liên quan page/checksum/index.
- Query trả kết quả không nhất quán và đã loại trừ lỗi ứng dụng.
- Muốn chạy kiểm tra định kỳ theo policy.
- Cần kiểm tra sau sự cố storage hoặc restore.

amcheck không phải công cụ tổng quát chứng minh mọi dữ liệu nghiệp vụ đúng. Nó kiểm tra những invariant mà hàm hỗ trợ nhận biết.

### Cài amcheck

Trong database cần kiểm tra:

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;
~~~

Xác minh:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'amcheck';
~~~

## 6. Kiểm tra B-tree bằng bt_index_check

Hàm bt_index_check kiểm tra tính nhất quán cấu trúc của B-tree index theo phạm vi của hàm và phiên bản.

Ví dụ:

~~~sql
SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

Nếu hàm hoàn tất mà không báo lỗi, các kiểm tra được thực hiện đã thành công. Điều đó không chứng minh mọi dạng corruption có thể tồn tại đều đã bị phát hiện.

### Ưu điểm và giới hạn

- Là lựa chọn nhẹ hơn so với parent check trong nhiều trường hợp.
- Có thể chạy trong workload online theo semantics/locking của version.
- Không thay thế kiểm tra dữ liệu nghiệp vụ.
- Mức kiểm tra phụ thuộc parameters và loại index.
- Không phải mọi access method đều được hỗ trợ giống B-tree.

Không diễn giải kết quả thành “toàn bộ database chắc chắn không corruption”.

## 7. Kiểm tra sâu hơn bằng bt_index_parent_check

Ví dụ:

~~~sql
SELECT bt_index_parent_check('public.orders_pkey'::regclass);
~~~

Parent check kiểm tra thêm các quan hệ giữa parent/child pages và cấu trúc B-tree. Một số phiên bản cung cấp các tùy chọn như heapallindexed hoặc rootdescend; signature và semantics cần được xác nhận theo version.

Kiểm tra sâu hơn có thể cần lock mạnh hơn hoặc làm giảm khả năng ghi đồng thời trên relation được kiểm tra. Vì vậy:

- Đánh giá table size và workload.
- Chạy ngoài peak window nếu phù hợp.
- Theo dõi lock waits và latency.
- Không chạy đồng loạt trên toàn bộ indexes lớn khi chưa đo tác động.
- Dùng pg_amcheck jobs có giới hạn concurrency.

### heapallindexed

Ở các version hỗ trợ, tùy chọn heapallindexed cho phép kiểm tra sâu hơn quan hệ giữa heap tuples và index entries. Việc này có thể tốn tài nguyên đáng kể vì phải kiểm tra nhiều dữ liệu hơn.

Không bật mọi tùy chọn kiểm tra sâu trong mọi lần chạy định kỳ mà không đánh giá chi phí.

## 8. Kiểm tra heap bằng verify_heapam

Một số version của amcheck cung cấp verify_heapam để kiểm tra một số dạng lỗi cấu trúc heap page và tuple.

Ví dụ trên version hỗ trợ:

~~~sql
SELECT *
FROM verify_heapam('public.orders'::regclass);
~~~

Kết quả có thể chứa block number, tuple offset, attribute number và thông báo lỗi tùy version.

Cần lưu ý:

- Xác minh function tồn tại và signature trên server cụ thể.
- Chạy với phạm vi phù hợp; kiểm tra heap lớn có thể tạo I/O đáng kể.
- Một số lỗi có thể liên quan TOAST data hoặc visibility state.
- Không tự sửa tuple dựa trên output.
- Lưu raw result và server logs để DBA/storage specialist phân tích.

Nếu function không tồn tại, kiểm tra amcheck version và PostgreSQL major version; không tự tạo function thay thế từ ví dụ của version khác.

## 9. pg_amcheck: tiện ích dòng lệnh

pg_amcheck là command-line utility dùng để chạy các kiểm tra amcheck trên một hoặc nhiều database/object. Utility này có từ PostgreSQL 14; option và phạm vi hỗ trợ có thể thay đổi theo version.

Ví dụ kiểm tra một database:

~~~bash
pg_amcheck --database=appdb --verbose
~~~

Ví dụ bật parent checks:

~~~bash
pg_amcheck --database=appdb --parent-check --verbose
~~~

Ví dụ chạy có giới hạn jobs:

~~~bash
pg_amcheck --database=appdb --jobs=2 --verbose
~~~

Cú pháp chính xác phụ thuộc phiên bản pg_amcheck. Kiểm tra help của binary đang dùng:

~~~bash
pg_amcheck --help
~~~

### Các lựa chọn thường gặp

- Chọn database, table hoặc index cụ thể.
- Quét nhiều database theo policy.
- Chọn parent checks.
- Chọn heapallindexed ở version hỗ trợ.
- Giới hạn parallel jobs.
- Hiển thị progress/verbose output.
- Bỏ qua object hoặc schema theo danh sách có chủ đích.

Không dùng tùy chọn toàn cluster khi chưa hiểu số lượng relation và chi phí. Trước khi chạy, lưu danh sách objects dự kiến được kiểm tra và xác định cách xử lý nếu command trả lỗi.

### Exit status và output

- Exit code thành công chỉ chứng minh các kiểm tra được thực hiện đã hoàn tất không báo lỗi.
- Exit code khác 0 cần đọc stderr/stdout để xác định object và loại lỗi.
- Một số object có thể được skip do quyền hoặc loại index không hỗ trợ.
- Kết quả không thay thế checksum verification, backup validation hoặc application checks.

## 10. Quy trình xử lý khi amcheck báo lỗi

Nếu amcheck báo lỗi:

1. Dừng lịch chạy kiểm tra tiếp theo trên cùng phạm vi nếu cần tránh tạo tải.
2. Lưu nguyên output, SQLSTATE/message, timestamp và version.
3. Xác định index/table/database chính xác.
4. Kiểm tra server logs, OS logs, storage telemetry và checksum state.
5. Xác định lỗi có lặp lại trên cùng block/object hay không.
6. Xác minh backup gần nhất và khả năng PITR.
7. Đánh giá có cần dừng writes hoặc chuyển sang incident mode.
8. Chọn phương án phục hồi có phê duyệt.
9. Sau recovery, chạy lại kiểm tra và application/data validation.

Không chạy REINDEX hoặc DROP INDEX ngay khi có bất kỳ lỗi amcheck nào. Cần xác định loại lỗi và bảo toàn evidence trước khi thay đổi object.

### Corruption không phải lúc nào cũng chỉ ở index

Nếu index bị corruption, có thể rebuild index trong một số tình huống. Nhưng nếu heap page hoặc underlying storage bị lỗi, rebuild index không khôi phục dữ liệu heap bị hỏng. Có thể cần restore/PITR hoặc chuyên gia PostgreSQL/storage đánh giá.

## 11. pageinspect là gì?

pageinspect cung cấp các hàm để xem nội dung và cấu trúc vật lý của database pages. Nó phục vụ điều tra sâu, nghiên cứu PostgreSQL internals và xác minh một giả thuyết cụ thể.

Có thể khảo sát:

- Page header.
- Heap line pointers và tuple metadata.
- B-tree metapage.
- B-tree page statistics và items.
- BRIN/GiST page structures trên các version hỗ trợ.
- Một số thông tin raw page khác tùy version.

pageinspect không phải công cụ consistency checker tổng quát. Nó giải mã các trường của page; người dùng phải hiểu cấu trúc và diễn giải output đúng version.

### Cài pageinspect

~~~sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
~~~

Xác minh:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pageinspect';
~~~

## 12. Đọc raw page bằng get_raw_page

Ví dụ lấy block đầu tiên của heap relation:

~~~sql
SELECT get_raw_page('public.orders', 0);
~~~

Hàm trả về page dưới dạng bytea. Thường kết hợp với các hàm decoder thay vì hiển thị toàn bộ binary.

Có thể chỉ định fork:

~~~sql
SELECT get_raw_page('public.orders', 'main', 0);
~~~

Các fork phổ biến:

- main: heap/index data pages.
- fsm: free space map.
- vm: visibility map.
- init: initialization fork, chủ yếu liên quan unlogged relations.

Không phải mọi relation đều có mọi fork. Block number phải nằm trong phạm vi relation/fork hiện có. Nếu page thay đổi đồng thời, kết quả là snapshot tại thời điểm đọc, không phải ảnh chụp nhất quán xuyên suốt nhiều lệnh.

## 13. Đọc page header

Ví dụ:

~~~sql
SELECT *
FROM page_header(get_raw_page('public.orders', 0));
~~~

Page header cung cấp các trường vật lý như:

- LSN: vị trí WAL liên quan page.
- Checksum field theo page format.
- Flags: trạng thái/thuộc tính page.
- Lower, upper, special: ranh giới vùng page.
- Page size và layout version.
- Prune XID: thông tin liên quan pruning.

Ý nghĩa chi tiết và cách giải mã phụ thuộc PostgreSQL version và page type. Không kết luận page corruption chỉ vì một trường có giá trị khác mong đợi nếu chưa kiểm tra loại page, version và trạng thái.

### Page layout tổng quát

~~~text
+--------------------------------------+
| Page Header                          |
+--------------------------------------+
| Line Pointer Array                   |
|  ItemId 1 | ItemId 2 | ...            |
+--------------------------------------+
|                                      |
| Free Space                           |
|                                      |
+--------------------------------------+
| Tuple / Index Tuple Data             |
| grows from the end toward the front  |
+--------------------------------------+
| Special Space (for some page types)  |
+--------------------------------------+
~~~

Heap page thường chứa header, line pointer array, free space và tuple data. Index pages có layout riêng và có thể dùng special space cho access method metadata.

## 14. Đọc heap tuples bằng heap_page_items

Ví dụ:

~~~sql
SELECT *
FROM heap_page_items(
    get_raw_page('public.orders', 'main', 0)
);
~~~

Output có thể gồm:

- lp: line pointer number.
- lp_off, lp_flags, lp_len: vị trí/trạng thái/kích thước line pointer.
- t_xmin, t_xmax: transaction IDs liên quan tạo/xóa tuple.
- t_ctid: tuple identifier.
- t_infomask, t_infomask2: flags nội bộ.
- t_hoff: offset bắt đầu tuple header.
- t_bits: null bitmap khi có.
- t_data: raw tuple data.

Các trường này là thông tin vật lý thấp cấp. Không dùng t_xmax riêng lẻ để kết luận row đã bị xóa; MVCC visibility còn phụ thuộc transaction status, hint bits, snapshot và tuple state.

### Line pointers

Line pointer có thể biểu thị:

- Tuple đang được lưu tại offset.
- Redirect pointer.
- Dead item.
- Unused item.

Không phải mọi line pointer đều chứa một tuple hiện hành. Heap page có thể chứa dead tuples chưa được vacuum hoặc tuple versions chưa thể reclaim vì transaction horizon.

### Đọc dữ liệu tuple

pageinspect không luôn giải mã t_data thành các cột SQL dễ đọc. Việc decode phụ thuộc tuple descriptor, attribute layout, alignment, null bitmap, TOAST và version. Dùng query SQL bình thường để đọc business values; dùng pageinspect khi cần điều tra cấu trúc vật lý.

## 15. Đọc B-tree metapage và page stats

B-tree index có metapage chứa metadata của index.

Ví dụ:

~~~sql
SELECT *
FROM bt_metap('public.orders_created_at_idx');
~~~

Thông tin có thể gồm:

- Root block.
- Tree level.
- Fast root/fast level.
- Version/meta flags.
- Các trường đặc thù B-tree theo version.

Xem page statistics:

~~~sql
SELECT *
FROM bt_page_stats('public.orders_created_at_idx', 1);
~~~

Block 1 chỉ là ví dụ; cần xác định block hợp lệ và ý nghĩa page type. Metapage thường ở block 0, các block tiếp theo có thể là internal/leaf pages hoặc page khác.

### Đọc B-tree items

~~~sql
SELECT *
FROM bt_page_items(
    'public.orders_created_at_idx',
    1
);
~~~

Các cột trả về phụ thuộc version, nhưng có thể bao gồm item offset, ctid, item length, data bytes, dead/metadata flags và thông tin tuple/index-specific.

Không diễn giải cột dead hoặc htid một cách độc lập khỏi version và semantics của function. Dùng pg_amcheck để kiểm tra invariants; pageinspect để quan sát page cụ thể.

## 16. pageinspect và forensic workflow

Khi nghi ngờ một block có vấn đề:

1. Xác định relation và fork.
2. Kiểm tra relation size và block range.
3. Lưu page header.
4. Lưu line pointer/tuple metadata.
5. Đọc B-tree metapage/page stats nếu là index.
6. Đối chiếu amcheck result.
7. Đối chiếu server logs và checksum.
8. Xác định block có thay đổi trong lúc khảo sát không.
9. Giữ evidence trước khi REINDEX/restore.
10. Chuyển cho DBA/storage specialist nếu có corruption evidence.

Raw page data có thể chứa dữ liệu nhạy cảm. Hạn chế quyền đọc và không đưa output tuple/raw bytes vào ticket công khai.

## 17. pg_buffercache là gì?

pg_buffercache cho phép quan sát các buffers trong PostgreSQL shared buffer cache tại thời điểm truy vấn. Nó trả lời câu hỏi: page nào đang được giữ trong shared buffers, thuộc database/relation/fork nào và có trạng thái dirty/usage nào.

Nó không phải công cụ đo physical disk I/O. Một page không nằm trong shared buffers có thể vẫn nằm trong OS page cache. Một page nằm trong shared buffers cũng có thể đã được đọc từ storage từ lâu.

### Cài đặt

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
~~~

Kiểm tra:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_buffercache';
~~~

### Xem số buffer entries

~~~sql
SELECT count(*) AS buffer_entries
FROM pg_buffercache;
~~~

### Phân bố buffer theo database

~~~sql
SELECT
    CASE
        WHEN reldatabase IS NULL THEN 'shared/system'
        ELSE COALESCE(d.datname, 'unknown database')
    END AS database_scope,
    count(*) AS buffers,
    count(*) FILTER (WHERE isdirty) AS dirty_buffers
FROM pg_buffercache AS b
LEFT JOIN pg_database AS d
    ON d.oid = b.reldatabase
GROUP BY 1
ORDER BY buffers DESC;
~~~

View có thể chứa entries không ánh xạ được vào database/relation thông thường. Đừng giả định mọi row đều thuộc một table người dùng.

## 18. Đọc các cột trong pg_buffercache

Một số cột quan trọng:

- bufferid: ID buffer trong shared buffer pool.
- relfilenode: filenode của relation.
- reltablespace: tablespace OID.
- reldatabase: database OID; có thể NULL với một số shared relations.
- relforknumber: main/FSM/VM/init fork.
- relblocknumber: block number.
- isdirty: page đang dirty.
- usagecount: usage count trong clock-sweep buffer replacement strategy.
- pinning_backends: số backend đang pin buffer theo semantics của version.

usagecount không phải hit count và không đo tần suất query truy cập page một cách trực tiếp. isdirty không đồng nghĩa page sắp được ghi ngay. pinning_backends khác 0 có thể phản ánh buffer đang được backend sử dụng.

### Buffer theo fork

~~~sql
SELECT
    relforknumber,
    count(*) AS buffers,
    count(*) FILTER (WHERE isdirty) AS dirty_buffers
FROM pg_buffercache
GROUP BY relforknumber
ORDER BY relforknumber;
~~~

Fork number mapping phổ biến: main=0, FSM=1, VM=2, init=3. Xác nhận với version/page type đang dùng.

## 19. Ánh xạ buffer về relation

Ánh xạ filenode sang relation cần xét database và tablespace. Filenode có thể thay đổi khi rewrite table, VACUUM FULL, CLUSTER, REINDEX hoặc các thao tác khác. Không join chỉ theo relfilenode trên toàn cluster.

Ví dụ cho relation thông thường trong current database:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    count(*) AS cached_buffers,
    count(*) FILTER (WHERE b.isdirty) AS dirty_buffers,
    round(avg(b.usagecount), 2) AS average_usage_count
FROM pg_buffercache AS b
JOIN pg_class AS c
    ON c.relfilenode = b.relfilenode
WHERE b.reldatabase = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
  AND c.relkind IN ('r', 'i', 'm', 't')
GROUP BY c.oid
ORDER BY cached_buffers DESC
LIMIT 30;
~~~

Đây là query khảo sát minh họa, không phải ánh xạ tổng quát hoàn hảo:

- Một số relation dùng mapped filenode và cần pg_relation_filenode().
- Tablespace cần được đối chiếu.
- TOAST relations và indexes là object riêng.
- Partitioned table parent không có storage riêng.
- Filenode có thể thay đổi trong lúc query.
- Temporary relations có scope/session riêng.

Đối với kiểm tra chính xác, dùng relation OID, tablespace mapping và pg_relation_filenode()/pg_relation_filepath() theo version. Chỉ join với catalog của database hiện tại khi reldatabase đúng database đó.

## 20. Dùng pg_buffercache để trả lời câu hỏi gì?

Các use case:

- Relation nào đang chiếm nhiều shared buffers?
- Bao nhiêu buffers của relation đang dirty?
- Main fork hay FSM/VM chiếm buffer?
- Một table có nhiều page trong cache sau workload không?
- Sau warm-up, buffer residency thay đổi ra sao?
- Có nhiều page pinned trong thời điểm khảo sát không?

Không dùng pg_buffercache để:

- Kết luận physical disk read/write count.
- Kết luận query cache hit ratio theo thời gian dài.
- Chứng minh table hot chỉ từ một snapshot.
- Đánh giá hiệu năng toàn cluster mà không xét OS cache và workload.
- Ép eviction/flush pages trong production tùy tiện.

Lấy nhiều snapshot theo khoảng thời gian và so sánh với pg_stat_io, pg_stat_database, EXPLAIN BUFFERS và OS storage metrics.

## 21. pgstattuple: đo dead tuples và free space

pgstattuple cung cấp thống kê vật lý về tuple và free space của table/index.

Cài:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
~~~

Kiểm tra table:

~~~sql
SELECT *
FROM pgstattuple('public.orders');
~~~

Output thường gồm:

- table_len: kích thước relation.
- tuple_count: số live tuples được nhận diện.
- tuple_len: tổng bytes của live tuples.
- tuple_percent: tỷ lệ page bytes dùng cho live tuples.
- dead_tuple_count và dead_tuple_len.
- dead_tuple_percent.
- free_space và free_percent.

### pgstattuple_approx

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders');
~~~

Hàm approximate có thể tận dụng visibility/free-space metadata để giảm lượng scan trong một số trường hợp, nhưng kết quả là ước lượng và có semantics riêng.

### Chi phí

pgstattuple có thể phải đọc nhiều hoặc toàn bộ relation. Với bảng lớn, việc này tạo I/O và CPU. Chạy trong observation window, giới hạn phạm vi và không quét đồng thời nhiều relation lớn mà chưa đánh giá tải.

Dead tuple percentage cao không tự động có nghĩa cần VACUUM FULL. Trước hết kiểm tra autovacuum, transaction horizon, table churn, index bloat và free space có thể tái sử dụng hay không.

## 22. pgstatindex: khảo sát B-tree index

pgstattuple cũng cung cấp pgstatindex cho B-tree indexes:

~~~sql
SELECT *
FROM pgstatindex('public.orders_created_at_idx');
~~~

Các trường có thể bao gồm:

- Index size.
- Tree level.
- Index pages.
- Leaf pages.
- Empty/deleted pages.
- Average leaf density.
- Leaf fragmentation.

Diễn giải cần dựa trên workload, fillfactor, insert pattern và version. Fragmentation hoặc density không phải tự thân là lỗi. Index lớn có thể hợp lý với workload và dữ liệu hiện tại.

Không REINDEX chỉ vì một con số density thấp mà không đo query performance, write amplification và maintenance window.

## 23. pg_freespacemap: khảo sát free space map

FSM ghi nhận ước lượng free space trong heap pages để PostgreSQL tìm nơi đặt tuple mới.

Cài:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
~~~

Xem free space:

~~~sql
SELECT *
FROM pg_freespace('public.orders')
ORDER BY blkno
LIMIT 50;
~~~

Kết quả thường có block number và free bytes được FSM ghi nhận. Đây là metadata phục vụ allocation, không phải phép đo chính xác tuyệt đối mọi byte còn có thể dùng.

Dùng để:

- Khảo sát phân bố free space.
- Điều tra table có nhiều page rỗng hoặc ít free space.
- Đối chiếu với pgstattuple.
- Hiểu hiệu quả tái sử dụng space sau vacuum.

Không chỉnh sửa FSM bằng tay. PostgreSQL tự quản lý free space map; nếu nghi metadata inconsistency, sử dụng công cụ kiểm tra và quy trình recovery phù hợp.

## 24. pg_visibility: visibility map

Visibility map lưu trạng thái page all-visible và all-frozen. Nó hỗ trợ VACUUM và index-only scans.

Cài:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_visibility;
~~~

Kiểm tra tổng quan:

~~~sql
SELECT *
FROM pg_visibility_map_summary('public.orders');
~~~

Kiểm tra từng block:

~~~sql
SELECT *
FROM pg_visibility_map('public.orders')
ORDER BY blkno
LIMIT 100;
~~~

Các cột thường thể hiện block number, all-visible và all-frozen.

### Vì sao visibility map quan trọng?

- All-visible cho phép index-only scan bỏ qua heap fetch khi điều kiện phù hợp.
- All-frozen hỗ trợ giảm nhu cầu vacuum/freeze lại page.
- Vacuum cập nhật visibility map theo trạng thái tuples.
- Transaction cũ hoặc updates có thể làm page mất all-visible state.

Một tỷ lệ all-visible thấp có thể làm index-only scan phải truy cập heap nhiều hơn, nhưng không nhất thiết là lỗi. Kiểm tra write churn, vacuum progress, long-running transactions và query plan.

### Kiểm tra page visibility

~~~sql
SELECT *
FROM pg_check_visible('public.orders'::regclass);
~~~

~~~sql
SELECT *
FROM pg_check_frozen('public.orders'::regclass);
~~~

Các hàm kiểm tra này có thể phát hiện page flags không phù hợp với tuple visibility/freeze state theo semantics của version. Chạy trên phạm vi lớn có thể tốn I/O; không tự sửa visibility map hoặc page data bằng thao tác thủ công.

## 25. pg_walinspect: khảo sát WAL bằng SQL

pg_walinspect cho phép đọc metadata của WAL records trong một LSN range. Extension này có từ PostgreSQL 15; xác nhận version và function signatures trước khi sử dụng.

Cài:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_walinspect;
~~~

Ví dụ xem WAL records trong một khoảng LSN:

~~~sql
SELECT *
FROM pg_get_wal_records_info(
    '0/1000000'::pg_lsn,
    '0/2000000'::pg_lsn
)
LIMIT 50;
~~~

Ví dụ thống kê WAL:

~~~sql
SELECT *
FROM pg_get_wal_stats(
    '0/1000000'::pg_lsn,
    '0/2000000'::pg_lsn
);
~~~

LSN trong ví dụ chỉ là placeholder. Chọn range có thật trong WAL hiện có; segment đã bị recycle hoặc archive-only có thể không đọc được từ pg_wal hiện tại.

### WAL record fields

Output có thể cung cấp:

- Start/end LSN.
- Transaction ID.
- Resource manager.
- Record type.
- Record length.
- Main data length.
- Full-page image length.
- Description.
- Block reference metadata.

Dùng để điều tra WAL generation, record types và activity trong một khoảng. Không suy luận trực tiếp business transaction chỉ từ record count.

### Bảo mật WAL inspection

WAL có thể chứa thông tin nhạy cảm hoặc dữ liệu thay đổi. Hạn chế quyền, giới hạn LSN range và redaction output. Không gửi raw WAL/record payload ra ngoài hệ thống được phép.

## 26. pg_waldump: công cụ ngoài server

pg_waldump là command-line tool đọc WAL segment và hiển thị record information. Nó hữu ích khi phân tích WAL ngoài SQL session hoặc trong incident investigation.

Ví dụ:

~~~bash
pg_waldump --path=/var/lib/postgresql/16/main/pg_wal
~~~

Option và đường dẫn phụ thuộc version, OS, package layout và WAL availability. Dùng pg_waldump --help của đúng major version.

Cần lưu ý:

- pg_waldump đọc WAL files; không sửa database.
- WAL files cần còn tồn tại hoặc được cung cấp từ archive.
- Tool version phải tương thích với WAL format.
- WAL records có thể tiết lộ thông tin nhạy cảm.
- Đọc WAL lớn có thể tạo I/O; giới hạn LSN/segment range.

Không copy hoặc xóa WAL files trong data directory đang chạy bằng thao tác thủ công. Sử dụng archive/backup tooling.

## 27. pg_stat_statements: khảo sát query workload

pg_stat_statements thống kê hoạt động của các normalized query. Nó không phải raw page inspection nhưng thường là bước đầu để xác định workload cần điều tra sâu.

Cài đặt thường cần:

1. Thêm pg_stat_statements vào shared_preload_libraries.
2. Restart PostgreSQL.
3. Tạo extension trong database cần truy vấn.
4. Xác minh counters và reset time.

Ví dụ:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Xem query tốn tổng thời gian:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Schema view và columns thay đổi theo extension version. Xác minh bằng psql describe hoặc catalog trước khi tự động hóa.

### Diễn giải

- total_exec_time: tổng thời gian thực thi tích lũy.
- mean_exec_time: trung bình mỗi lần gọi.
- calls: số lần gọi.
- shared_blks_hit/read: hoạt động buffer trong PostgreSQL.
- temp_blks_read/written: temporary block activity.
- rows: số rows trả về/thao tác theo semantics của view.

Query có total time cao có thể chỉ vì được gọi rất nhiều; query mean time cao có thể là latency issue. So sánh cả calls, mean, total và workload volume.

## 28. pg_stat_io: I/O theo backend/context

Từ PostgreSQL 16, pg_stat_io cung cấp counters I/O theo backend type, object và context.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Các trường tùy version có thể bao gồm reads/read_time, writes/write_time, writebacks/writeback_time, extends/extend_time, hits, evictions, reuses, fsyncs và fsync_time.

Kết hợp với pg_stat_statements để tìm query workload và OS/storage metrics để xác định thiết bị. Không xem mọi counter là physical device operations một-một.

### Snapshot và delta

Counters thường tích lũy từ stats reset/server start. Lưu snapshot ở t1 và t2, ghi nhận stats_reset, rồi tính delta. Nếu server restart hoặc counters reset giữa hai lần đo, phân đoạn dữ liệu trước/sau.

## 29. Các view khảo sát hệ thống bổ trợ

Không phải mọi điều tra đều cần extension. PostgreSQL built-in views thường đủ để khoanh vùng trước.

### Session và wait events

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 180) AS query_sample
FROM pg_stat_activity
ORDER BY query_start NULLS LAST;
~~~

### Blocking sessions

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

### Table statistics

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC;
~~~

### Index statistics

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
~~~

Các counters có thể reset và chỉ phản ánh workload kể từ reset. Một index có idx_scan thấp trong cửa sổ ngắn không đủ căn cứ để drop.

## 30. pg_stat_progress views

PostgreSQL cung cấp các progress views cho một số operations dài. Tên và columns tùy version.

Ví dụ vacuum:

~~~sql
SELECT *
FROM pg_stat_progress_vacuum;
~~~

Ví dụ CREATE INDEX:

~~~sql
SELECT *
FROM pg_stat_progress_create_index;
~~~

Ví dụ ANALYZE:

~~~sql
SELECT *
FROM pg_stat_progress_analyze;
~~~

Dùng để xác định operation đang ở phase nào, đã scan bao nhiêu blocks hoặc còn bao nhiêu work. Các views này không lưu lịch sử lâu dài; cần scrape/snapshot nếu muốn phân tích sau sự kiện.

## 31. pg_checksums: xác minh page checksums

Page checksums giúp phát hiện một số dạng page corruption khi PostgreSQL đọc page. Khả năng và quy trình phụ thuộc version và cách cluster được khởi tạo.

Tiện ích pg_checksums có thể kiểm tra checksum của cluster offline theo yêu cầu version. Ví dụ tổng quát:

~~~bash
pg_checksums --check --pgdata=/path/to/cluster
~~~

Cần dừng server trước khi chạy chế độ check/enable/disable theo yêu cầu của tool/version. Không chạy trên data directory đang hoạt động nếu tài liệu version yêu cầu cluster shutdown.

Lưu ý:

- Cluster phải được tạo với checksums enabled để có checksum thực tế cần kiểm tra.
- Không có checksum error không chứng minh toàn bộ logic database đúng.
- Checksum phát hiện một số dạng page corruption, không thay thế backup.
- Nếu checksum mismatch, bảo toàn evidence và xử lý theo incident/recovery plan.
- Không tự ghi lại checksum hoặc sửa raw page.

Kiểm tra trạng thái qua pg_controldata hoặc công cụ phù hợp với version.

## 32. pg_verifybackup: xác minh backup

pg_verifybackup kiểm tra backup directory dựa trên backup manifest do pg_basebackup tạo và thực hiện các validation mà tool hỗ trợ.

Ví dụ:

~~~bash
pg_verifybackup /path/to/basebackup
~~~

Tool version phải phù hợp backup format và PostgreSQL version. Kết quả thành công là bằng chứng hữu ích về manifest/file validation, nhưng restore test vẫn cần thiết để chứng minh quy trình phục hồi end-to-end.

Nếu backup tool khác pg_basebackup, dùng công cụ verify riêng của nó. Không giả định pg_verifybackup hỗ trợ mọi định dạng backup.

## 33. pg_controldata và cluster metadata

pg_controldata hiển thị thông tin control file của cluster:

~~~bash
pg_controldata /path/to/cluster
~~~

Có thể cung cấp:

- Database system identifier.
- Catalog version number.
- Database cluster state.
- Latest checkpoint location.
- REDO/WAL information.
- Checksum version.
- Timeline/checkpoint metadata.

Dùng khi xác minh cluster identity, backup/restore state hoặc điều tra startup/recovery. Chạy đúng binary version và đọc đúng data directory. Không chỉnh sửa control file bằng công cụ ngoài PostgreSQL.

## 34. Công cụ khảo sát khác

Một số công cụ bổ trợ:

| Công cụ | Mục đích | Lưu ý |
| --- | --- | --- |
| pg_test_fsync | So sánh fsync methods trên filesystem | Benchmark, không chứng minh production durability |
| pg_test_timing | Đánh giá timing overhead/precision | Chạy trên host tương ứng |
| pgbench | Benchmark workload PostgreSQL | Có thể tạo dữ liệu và tải lớn |
| psql | Truy vấn catalog và statistics | Client version và quyền cần phù hợp |
| EXPLAIN | Phân tích query plan | ANALYZE thực thi statement |
| iostat/vmstat/sar | OS I/O, CPU, memory | Cần đối chiếu device/container/cloud metrics |
| strace/perf | Điều tra syscall/CPU | Có overhead, dùng có kiểm soát |
| lsof | Kiểm tra file descriptors | Không thay thế database catalog |
| dmesg/journalctl | Kernel/storage/service errors | Có thể cần OS privileges |

Không chạy benchmark, tracing hoặc system probes trên production chỉ vì tiện. Xác định impact, duration, sample rate và stop condition.

## 35. Kết hợp nhiều công cụ trong một investigation

Ví dụ nghi ngờ table/index có vấn đề và query chậm:

1. Dùng pg_stat_statements tìm query có regression.
2. Dùng EXPLAIN (ANALYZE, BUFFERS) trên query đại diện.
3. Kiểm tra index validity bằng pg_index.
4. Chạy amcheck trên index liên quan.
5. Dùng pg_buffercache để quan sát page residency snapshot.
6. Dùng pgstattuple/pgstatindex để khảo sát tuple/bloat/index structure.
7. Dùng pg_visibility để xem all-visible/all-frozen state.
8. Đối chiếu pg_stat_io và OS I/O metrics.
9. Xem server logs, checksum và storage events.
10. Chọn repair/recovery sau khi có đủ bằng chứng.

Không cần chạy tất cả công cụ trong mọi incident. Bắt đầu từ câu hỏi cụ thể và tăng mức độ khảo sát khi evidence yêu cầu.

## 36. Runbook: kiểm tra B-tree định kỳ

### Trước khi chạy

- Xác nhận database/cluster.
- Kiểm tra amcheck version và privileges.
- Lập danh sách indexes.
- Chọn concurrency và maintenance window.
- Kiểm tra disk/I/O/latency baseline.
- Xác định log destination và alert recipient.
- Xác định cách xử lý nếu phát hiện lỗi.

### Thực hiện

Một index cụ thể:

~~~sql
SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

Hoặc dùng pg_amcheck theo danh sách database/object đã phê duyệt.

### Sau khi chạy

- Lưu exit status và output.
- Ghi object đã kiểm tra/skipped.
- Ghi thời gian và resource impact.
- Nếu có lỗi, mở incident và bảo toàn evidence.
- Chỉ đóng runbook khi phạm vi kiểm tra hoàn tất và exceptions được ghi nhận.

## 37. Runbook: khảo sát page cụ thể

### Trước khi đọc

- Xác định relation OID/name.
- Xác định fork.
- Xác nhận block number hợp lệ.
- Ghi relation size.
- Xác định có concurrent writes không.
- Kiểm tra quyền pageinspect.
- Xác định nơi lưu raw output và redaction.

### Thực hiện

~~~sql
SELECT *
FROM page_header(get_raw_page('public.orders', 'main', 0));

SELECT *
FROM heap_page_items(get_raw_page('public.orders', 'main', 0));
~~~

Với B-tree:

~~~sql
SELECT *
FROM bt_metap('public.orders_created_at_idx');

SELECT *
FROM bt_page_stats('public.orders_created_at_idx', 1);
~~~

### Sau khi đọc

- Lưu query, version, relation và block.
- Không chỉnh raw page.
- Đối chiếu amcheck nếu cần consistency validation.
- Nếu phát hiện dấu hiệu corruption, dừng thao tác sửa và chuyển sang recovery plan.

## 38. Runbook: khảo sát buffer cache

### Trước khi chạy

- Xác nhận extension và quyền.
- Chọn database scope.
- Xác định mục tiêu: residency, dirty buffers hay usage distribution.
- Lấy snapshot workload metrics cùng thời điểm.
- Tránh truy vấn lặp quá dày trên hệ thống lớn.

### Thực hiện

~~~sql
SELECT
    count(*) AS buffers,
    count(*) FILTER (WHERE isdirty) AS dirty_buffers,
    round(avg(usagecount), 2) AS average_usage_count
FROM pg_buffercache;
~~~

### Diễn giải

- Snapshot phản ánh trạng thái tại thời điểm truy vấn.
- Buffer residency thay đổi theo workload.
- Không tương đương OS cache.
- Không phải physical read/write count.
- Dirty buffer count không cho biết chính xác write latency.

Kết hợp với pg_stat_io, EXPLAIN BUFFERS, OS metrics và query workload.

## 39. Runbook: điều tra bloat và free space

### Trước khi chạy

- Chọn table/index cần khảo sát.
- Kiểm tra relation size.
- Ước lượng chi phí scan.
- Kiểm tra active workload.
- Xác định query nào sẽ sử dụng kết quả.

### Thực hiện

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders');

SELECT *
FROM pgstatindex('public.orders_created_at_idx');

SELECT *
FROM pg_freespace('public.orders')
ORDER BY blkno
LIMIT 100;
~~~

### Sau khi chạy

- So sánh live/dead/free bytes.
- Kiểm tra autovacuum và transaction horizon.
- Xác định free space có thể tái sử dụng hay cần trả lại OS.
- Đo query impact.
- Chỉ quyết định VACUUM, REINDEX hoặc table rewrite khi có kế hoạch lock/disk/recovery.

Không dùng bloat estimate đơn lẻ làm trigger tự động cho VACUUM FULL.

## 40. Runbook: điều tra WAL

### Trước khi đọc WAL

- Xác định LSN range.
- Kiểm tra WAL segment còn tồn tại hoặc có trong archive.
- Xác nhận pg_walinspect/pg_waldump version.
- Đánh giá sensitivity của WAL.
- Giới hạn output và quyền truy cập.

### Thực hiện

~~~sql
SELECT *
FROM pg_get_wal_stats(
    '0/1000000'::pg_lsn,
    '0/2000000'::pg_lsn
);
~~~

### Sau khi đọc

- Đối chiếu LSN range và timeline.
- So sánh với WAL generation metrics.
- Không suy luận business-level transaction chỉ từ record count.
- Lưu evidence đã redact.
- Không xóa/recycle WAL thủ công.

## 41. Hiểu giới hạn của từng công cụ

| Công cụ | Có thể giúp phát hiện | Không chứng minh |
| --- | --- | --- |
| amcheck | Một số lỗi cấu trúc index/heap | Toàn bộ business data đúng |
| pg_amcheck | Tự động hóa phạm vi amcheck | Mọi object/page đều được kiểm tra mọi invariant |
| pageinspect | Nội dung/metadata page cụ thể | Page consistency tổng thể |
| pg_buffercache | Buffer residency snapshot | Physical disk cache/hit rate theo thời gian |
| pgstattuple | Tuple/dead/free-space statistics | Nguyên nhân bloat hoặc hiệu năng query |
| pg_freespacemap | FSM recorded free space | Chính xác mọi byte có thể dùng |
| pg_visibility | Visibility map state | Toàn bộ MVCC correctness |
| pg_walinspect | WAL record metadata trong range | Business transaction semantics hoàn chỉnh |
| pg_stat_statements | Query-level aggregate stats | Per-request trace hoặc percentile đầy đủ |
| pg_stat_io | I/O counters theo backend/object/context | Physical device operations một-một |
| pg_checksums | Checksum mismatch ở page có checksum | Không có mọi dạng corruption |
| pg_verifybackup | Backup manifest/file validation | Restore/application recovery end-to-end |

## 42. Các rủi ro khi khảo sát production

1. **I/O amplification:** scan table/index lớn làm storage latency tăng.
2. **CPU overhead:** decode pages, compute checksums hoặc thống kê chi tiết.
3. **Lock impact:** một số amcheck modes hoặc DDL/maintenance checks cần lock ảnh hưởng concurrent workload.
4. **Sensitive data exposure:** pageinspect/WAL output có thể chứa data.
5. **Privilege escalation:** cấp superuser để tiện chạy công cụ làm tăng blast radius.
6. **Misinterpretation:** hiểu sai tuple flags, usage count hoặc visibility map.
7. **Snapshot inconsistency:** page thay đổi trong lúc đọc hoặc counters reset.
8. **False confidence:** công cụ không báo lỗi nhưng corruption nằm ngoài phạm vi kiểm tra.
9. **Repair too early:** REINDEX/VACUUM/restore trước khi lưu evidence.
10. **Tool mismatch:** binary/extension version không tương thích server.

### Nguyên tắc dừng

Dừng khảo sát và chuyển sang incident response khi:

- Có checksum mismatch hoặc amcheck corruption error.
- Server log ghi PANIC/FATAL liên quan page/storage.
- OS báo I/O error hoặc filesystem problem.
- Nhiều relation không đọc được.
- Query bắt đầu trả kết quả không nhất quán.
- Storage latency/error rate tăng mạnh do scan.
- Không thể xác định đúng target/version.
- Quyền cần thiết vượt quá quyền được phê duyệt.

## 43. Bảo mật và lưu evidence

Evidence nên ghi:

- Change/incident ID.
- Cluster/database identity.
- PostgreSQL version.
- Extension version.
- Tool version.
- Relation/index và fork/block range.
- Command/query.
- Start/end timestamp và timezone.
- Operator/role.
- Exit status.
- Output/log reference.
- Resource impact.
- Exceptions và next action.

Không lưu password/token/private key, full connection string chứa secret, raw tuple values hoặc WAL payload không cần thiết, customer PII ngoài phạm vi, raw page dumps trong ticket có quyền truy cập rộng.

Nếu cần lưu raw page hoặc WAL artifact cho forensic, dùng evidence store có access control, encryption, retention và chain-of-custody phù hợp.

## 44. Tự động hóa khảo sát có kiểm soát

Một scheduled survey có thể:

1. Lấy extension inventory.
2. Chọn index/table theo risk policy.
3. Chạy amcheck theo concurrency giới hạn.
4. Thu thập query/IO statistics.
5. Lưu output và timestamp.
6. Gửi alert khi command báo lỗi.
7. Tạo incident reference và giữ raw evidence.
8. Không tự REINDEX/restore/drop object.

### Tách detection khỏi remediation

Detection có thể tự động hóa vì phần lớn là read-only. Remediation như REINDEX, VACUUM FULL, restore, failover hoặc thay đổi data cần decision gate riêng.

Không tạo cron job chạy pageinspect trên toàn cluster thường xuyên nếu không có mục tiêu rõ. Với kiểm tra định kỳ, pg_amcheck theo scope và cadence đã benchmark thường phù hợp hơn.

## 45. Những sai lầm thường gặp

1. **Coi amcheck là chứng nhận toàn database không corruption**, trong khi nó chỉ kiểm tra các invariant được hỗ trợ.
2. **Dùng bt_index_parent_check trên toàn bộ indexes trong peak hours**, gây lock/resource impact ngoài dự kiến.
3. **Bỏ qua PostgreSQL version khi dùng function signature**, khiến query lỗi hoặc option có semantics khác.
4. **Không phân biệt amcheck và pageinspect**, dùng decoder page để kết luận consistency.
5. **Tự sửa raw page sau khi đọc pageinspect**, có thể làm hỏng database nghiêm trọng.
6. **Đọc t_xmax như trạng thái xóa đơn giản**, bỏ qua MVCC visibility và transaction status.
7. **Dùng pageinspect với role ứng dụng**, mở rộng khả năng đọc dữ liệu nội bộ.
8. **Join pg_buffercache chỉ theo relfilenode**, ánh xạ nhầm relation giữa database/tablespace.
9. **Coi usagecount là số lần query hit**, diễn giải sai buffer replacement metadata.
10. **Coi buffer miss là physical disk read**, bỏ qua OS page cache.
11. **Coi dirty buffers là write backlog chính xác**, không đối chiếu I/O/checkpoint stats.
12. **Chạy pgstattuple trên nhiều bảng lớn cùng lúc**, tạo I/O scan nặng.
13. **Dùng dead tuple percentage làm lý do duy nhất cho VACUUM FULL**, bỏ qua lock và rewrite cost.
14. **Coi FSM free bytes là dung lượng có thể dùng chính xác**, bỏ qua semantics của free space map.
15. **Dùng pg_visibility để kết luận MVCC hoàn toàn đúng**, vượt quá phạm vi visibility map.
16. **Không kiểm tra WAL LSN range/timeline**, đọc sai hoặc thiếu dữ liệu do segment đã recycle.
17. **Đưa WAL/pageinspect output lên ticket công khai**, làm lộ dữ liệu nhạy cảm.
18. **Chỉ nhìn exit code pg_amcheck**, không kiểm tra object skipped và stderr.
19. **Dùng pg_checksums khi server đang chạy**, vi phạm yêu cầu offline của tool/version.
20. **Coi pg_verifybackup thành restore test**, không kiểm tra application recovery.
21. **Cài extension ở một database rồi giả định mọi database đều có**, bỏ qua per-database installation.
22. **Cấp SUPERUSER cho tiện**, tạo blast radius không cần thiết.
23. **Tự động REINDEX khi phát hiện lỗi mà chưa lưu evidence**, làm mất thông tin điều tra.
24. **Không đối chiếu OS/storage logs**, bỏ sót nguyên nhân phần cứng/filesystem.
25. **Chạy survey quá dày**, làm chính hoạt động khảo sát gây ra bottleneck.
26. **Không lưu version, timestamp và scope**, khiến kết quả không thể tái lập.

## 46. Bài tập thực hành có đáp án

### Bài 1. amcheck dùng để làm gì?

**Đáp án:** Kiểm tra một số dạng nhất quán cấu trúc của B-tree indexes và heap trên các version hỗ trợ.

### Bài 2. pageinspect khác amcheck thế nào?

**Đáp án:** pageinspect giải mã cấu trúc page/tuple để quan sát; amcheck kiểm tra các invariant cấu trúc.

### Bài 3. pg_buffercache trả lời câu hỏi gì?

**Đáp án:** Page nào đang nằm trong PostgreSQL shared buffer cache tại thời điểm truy vấn.

### Bài 4. CREATE EXTENSION có tác dụng trên toàn cluster không?

**Đáp án:** Không. SQL extension objects được tạo trong database hiện tại; package/shared libraries được cài ở cấp server.

### Bài 5. Query nào kiểm tra extension có sẵn?

**Đáp án:** pg_available_extensions.

### Bài 6. Query nào kiểm tra extension đã cài trong database?

**Đáp án:** pg_extension.

### Bài 7. bt_index_check dùng cho object nào?

**Đáp án:** B-tree index được amcheck hỗ trợ.

### Bài 8. bt_index_parent_check có mục đích gì?

**Đáp án:** Kiểm tra sâu hơn cấu trúc parent/child của B-tree và các invariant liên quan.

### Bài 9. pg_amcheck là gì?

**Đáp án:** Command-line utility tự động hóa các kiểm tra amcheck trên database/object; có từ PostgreSQL 14.

### Bài 10. Index invalid có thể được phát hiện ở đâu?

**Đáp án:** pg_index, đặc biệt indisvalid và indisready, kết hợp với amcheck/logs.

### Bài 11. verify_heapam dùng để làm gì?

**Đáp án:** Kiểm tra một số dạng lỗi cấu trúc heap trên version amcheck có hỗ trợ.

### Bài 12. get_raw_page trả về gì?

**Đáp án:** Nội dung raw của một relation page dưới dạng bytea.

### Bài 13. page_header cung cấp gì?

**Đáp án:** Metadata của page như LSN, flags và ranh giới vùng page theo page format.

### Bài 14. heap_page_items hiển thị gì?

**Đáp án:** Line pointers và tuple header/metadata của heap page.

### Bài 15. t_xmax có luôn nghĩa row đã bị xóa không?

**Đáp án:** Không. Cần xét MVCC, transaction status, snapshot và tuple flags.

### Bài 16. bt_metap dùng để xem gì?

**Đáp án:** Metadata của B-tree index như root block và tree level.

### Bài 17. pg_buffercache usagecount là gì?

**Đáp án:** Metadata của buffer replacement strategy, không phải query hit count.

### Bài 18. Vì sao pg_buffercache không đo physical disk I/O?

**Đáp án:** Vì nó chỉ quan sát shared buffers; OS page cache và storage layer nằm ngoài view này.

### Bài 19. pgstattuple đo những gì?

**Đáp án:** Live/dead tuples, tuple bytes và free space của relation.

### Bài 20. pgstatindex dùng cho gì?

**Đáp án:** Khảo sát cấu trúc và statistics của B-tree index.

### Bài 21. pg_freespacemap cho biết gì?

**Đáp án:** Free space mà FSM ghi nhận theo heap blocks.

### Bài 22. Visibility map có hai trạng thái quan trọng nào?

**Đáp án:** All-visible và all-frozen.

### Bài 23. Vì sao visibility map quan trọng với index-only scan?

**Đáp án:** Page all-visible có thể cho phép tránh heap fetch khi query/index đáp ứng điều kiện.

### Bài 24. pg_walinspect dùng để làm gì?

**Đáp án:** Khảo sát metadata của WAL records trong một LSN range; extension có từ PostgreSQL 15.

### Bài 25. pg_stat_statements cần preload không?

**Đáp án:** Thông thường cần shared_preload_libraries và restart trước khi dùng đầy đủ.

### Bài 26. pg_stat_io có từ PostgreSQL nào?

**Đáp án:** PostgreSQL 16.

### Bài 27. pg_checksums có thể chạy trên cluster đang hoạt động không?

**Đáp án:** Chế độ check/enable/disable yêu cầu điều kiện offline theo tài liệu tool/version; không chạy khi server đang hoạt động nếu tool yêu cầu shutdown.

### Bài 28. pg_verifybackup chứng minh điều gì?

**Đáp án:** Kiểm tra backup manifest/files theo phạm vi hỗ trợ; không thay restore test end-to-end.

### Bài 29. Khi amcheck báo corruption nên làm gì trước?

**Đáp án:** Lưu evidence, xác định object/version, kiểm tra logs/storage/checksums và backup/recovery trước khi sửa.

### Bài 30. Vì sao không tự động REINDEX ngay khi phát hiện lỗi?

**Đáp án:** Cần xác định lỗi nằm ở index hay heap/storage và bảo toàn evidence trước khi thay đổi trạng thái.

## 47. Checklist khảo sát PostgreSQL internals

### Trước khi chạy

- [ ] Xác định câu hỏi điều tra.
- [ ] Xác nhận cluster/database/primary/standby.
- [ ] Xác nhận PostgreSQL và extension versions.
- [ ] Kiểm tra extension availability và installed state.
- [ ] Xác định function signature/privileges theo version.
- [ ] Chọn relation/index/fork/block range cụ thể.
- [ ] Đánh giá table/index size và I/O impact.
- [ ] Chọn maintenance window/concurrency.
- [ ] Xác định evidence destination và redaction.
- [ ] Có stop condition và escalation owner.

### Trong khi chạy

- [ ] Ghi command/query và timestamp.
- [ ] Theo dõi CPU, memory, I/O, locks và application latency.
- [ ] Lưu stdout/stderr/SQL results.
- [ ] Ghi object skipped hoặc permission errors.
- [ ] Không chạy scan toàn cluster ngoài scope.
- [ ] Không chỉnh sửa raw page hoặc WAL.
- [ ] Dừng nếu hệ thống có regression vượt ngưỡng.

### Sau khi chạy

- [ ] Diễn giải kết quả trong đúng phạm vi công cụ.
- [ ] Đối chiếu server logs và OS/storage events.
- [ ] Kết hợp catalog, statistics và application evidence.
- [ ] Nếu có corruption, mở incident và bảo toàn evidence.
- [ ] Chọn repair/recovery bằng change plan riêng.
- [ ] Lưu version, scope, output và reviewer.
- [ ] Xác minh hệ thống vẫn healthy sau khảo sát.

## 48. Tài liệu PostgreSQL chính thức

Đọc tài liệu đúng major version đang triển khai:

- [amcheck](https://www.postgresql.org/docs/current/amcheck.html) — kiểm tra B-tree và heap consistency.
- [pg_amcheck](https://www.postgresql.org/docs/current/app-pgamcheck.html) — tiện ích kiểm tra index/heap.
- [pageinspect](https://www.postgresql.org/docs/current/pageinspect.html) — đọc page, heap tuples và index pages.
- [pg_buffercache](https://www.postgresql.org/docs/current/pgbuffercache.html) — quan sát shared buffer cache.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple, dead tuple, free space và index stats.
- [pg_freespacemap](https://www.postgresql.org/docs/current/pgfreespacemap.html) — free space map.
- [pg_visibility](https://www.postgresql.org/docs/current/pgvisibility.html) — visibility map và page checks.
- [pg_walinspect](https://www.postgresql.org/docs/current/pgwalinspect.html) — WAL record inspection.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query workload statistics.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_io, sessions, replication và progress views.
- [Database Page Layout](https://www.postgresql.org/docs/current/storage-page-layout.html) — page header, line pointers và tuple layout.
- [Database Physical Storage](https://www.postgresql.org/docs/current/storage.html) — relation files và forks.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html) — page checksum verification.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — xác minh backup manifest.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html) — cluster control information.
- [pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html) — đọc WAL records từ command line.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — cài extension trong database.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Extension availability, function signatures, privileges, view columns và command options có thể khác theo major version, distribution và managed provider. Kiểm tra tài liệu đúng version trước khi chạy lệnh trong production.

## 49. Tổng kết

**amcheck kiểm tra cấu trúc, pageinspect giúp quan sát page, còn pg_buffercache cho biết page nào đang nằm trong shared buffers.** Các công cụ bổ trợ như pgstattuple, pg_visibility, pg_walinspect và pg_stat_statements mở rộng điều tra sang storage, MVCC, WAL và workload.

1. **Chọn công cụ theo câu hỏi cụ thể.** Không dùng một extension để kết luận mọi loại database health.
2. **Cài extension trong đúng database và xác minh version.** Package/shared library và SQL extension objects là hai lớp khác nhau.
3. **amcheck/pg_amcheck hỗ trợ kiểm tra index và heap theo phạm vi version.** Không báo lỗi không đồng nghĩa chứng minh toàn bộ dữ liệu đúng.
4. **pageinspect đọc cấu trúc vật lý.** Nó phục vụ forensic, không phải công cụ sửa page hoặc consistency checker tổng quát.
5. **pg_buffercache là snapshot shared buffer cache.** Nó không đo physical disk I/O và không phản ánh OS page cache.
6. **pgstattuple, pg_freespacemap và pg_visibility cung cấp các góc nhìn khác nhau.** Dead tuples, FSM free space và visibility bits không thể thay thế nhau.
7. **pg_walinspect và pg_waldump giúp khảo sát WAL.** Giới hạn LSN range và bảo vệ dữ liệu nhạy cảm.
8. **pg_stat_statements và pg_stat_io kết nối workload với I/O behavior.** Dùng snapshot/delta và đối chiếu OS metrics.
9. **Một số kiểm tra có thể rất tốn I/O/CPU hoặc cần quyền cao.** Chọn scope, concurrency và thời điểm phù hợp.
10. **Khi phát hiện corruption, bảo toàn evidence trước khi remediation.** REINDEX không sửa được mọi lỗi heap/storage.
11. **Backup validation và restore test vẫn cần thiết.** Extension diagnostics không thay thế recovery readiness.
12. **Ghi rõ version, object, block range, timestamp và kết quả.** Evidence có thể tái lập giúp điều tra và review chính xác.

Khảo sát nội bộ hiệu quả là quá trình đi từ câu hỏi tới bằng chứng: chọn đúng công cụ, hiểu giới hạn của output, đối chiếu nhiều lớp thông tin và chỉ thực hiện remediation sau khi trạng thái database đã được xác định.
