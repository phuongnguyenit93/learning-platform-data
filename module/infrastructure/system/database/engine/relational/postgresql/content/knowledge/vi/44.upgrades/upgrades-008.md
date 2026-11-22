# Thay đổi collation, reindex và rủi ro sau nâng cấp hệ điều hành

PostgreSQL dùng collation để xác định cách so sánh và sắp xếp text theo locale. Quy tắc này có thể đến từ thư viện locale của hệ điều hành như glibc hoặc từ ICU. Khi nâng cấp hệ điều hành, glibc hay ICU có thể thay đổi quy tắc so sánh ký tự. Một index được xây dựng theo quy tắc cũ có thể không còn đúng thứ tự theo quy tắc mới.

Đây là rủi ro dữ liệu thực tế: query dùng index có thể trả kết quả sai hoặc không đầy đủ; unique index có thể phát hiện xung đột mới khi được xây dựng lại; và replica có thể có hành vi khác nếu các node dùng các phiên bản locale khác nhau. PostgreSQL lưu lại version collation để cảnh báo mismatch, nhưng việc cập nhật metadata không tự sửa index.

Bài học này giải thích collation providers, version tracking, cách phát hiện mismatch, xác định index phụ thuộc collation, lựa chọn REINDEX, xử lý unique conflicts, và lập kế hoạch nâng cấp OS/ICU/glibc cho primary, standbys và logical subscribers. Các ví dụ hướng tới PostgreSQL trên Linux; catalog columns, provider support và lệnh quản trị cần được xác minh theo major version đang vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích collation và tác động lên so sánh/sắp xếp text.
2. Phân biệt libc, ICU và các provider khác nếu phiên bản hỗ trợ.
3. Hiểu vì sao OS/ICU upgrade có thể làm thay đổi collation behavior.
4. Đọc collation version được lưu và actual version của runtime.
5. Phát hiện mismatch ở database default collation và named collations.
6. Xác định indexes sử dụng collation bị thay đổi.
7. Lập thứ tự reindex và refresh collation metadata an toàn.
8. Hiểu tác động tới unique indexes, constraints, partitioning và query results.
9. So sánh REINDEX thường với REINDEX CONCURRENTLY.
10. Phối hợp reindex trên primary, physical standbys và logical subscribers.
11. Xây dựng runbook trước/sau nâng cấp hệ điều hành.
12. Kiểm thử locale behavior, index correctness, replication và rollback readiness.

## 2. Collation là gì?

Collation là bộ quy tắc dùng để so sánh và sắp xếp chuỗi ký tự theo một locale hoặc bộ quy tắc cụ thể. Ví dụ, quy tắc có thể quyết định:

- Chữ hoa và chữ thường được sắp xếp như thế nào.
- Các ký tự có dấu được đặt ở vị trí nào.
- Hai chuỗi có thứ tự trước/sau ra sao.
- Một số ký tự hoặc chuỗi được xem là tương đương trong phép so sánh theo collation.

Không có một thứ tự alphabet duy nhất phù hợp với mọi ngôn ngữ. Kết quả có thể khác giữa locale tiếng Anh, tiếng Việt, tiếng Đức, tiếng Thổ Nhĩ Kỳ hoặc giữa các phiên bản dữ liệu locale.

### Collation không phải encoding

Encoding quy định cách biểu diễn ký tự thành bytes, ví dụ UTF8. Collation quy định cách so sánh/sắp xếp các giá trị text. Một database UTF8 vẫn có thể thay đổi kết quả ORDER BY khi provider hoặc version collation thay đổi.

### Collation và phép so sánh

Collation ảnh hưởng các phép toán text có sử dụng quy tắc locale. Những biểu thức cụ thể chịu ảnh hưởng phụ thuộc collation được gắn cho expression, operator class và database. Không giả định mọi phép so sánh bytes đều chịu collation.

## 3. Collation được dùng ở đâu?

Collation có thể ảnh hưởng:

- ORDER BY trên text.
- So sánh text trong predicates và joins.
- B-tree indexes trên text/varchar/char và expression indexes.
- Unique indexes/unique constraints có key sử dụng collation.
- DISTINCT, GROUP BY và một số phép toán text khác.
- Partition bounds hoặc logic ứng dụng dựa vào thứ tự text.
- Kết quả của các truy vấn phụ thuộc locale.

Một số thao tác có thể dùng binary comparison hoặc collation cụ thể được chỉ định rõ. Cần xác định collation thực tế của từng expression thay vì cho rằng mọi cột text dùng cùng một quy tắc.

## 4. Collation của database và collation của expression

Khi tạo database, có thể chọn locale/provider cho default collation. Các cột và expressions thường kế thừa default collation theo quy tắc PostgreSQL, nhưng có thể chỉ định collation khác.

Ví dụ:

```sql
CREATE TABLE customer (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name text COLLATE "en_US"
);
```

Một expression cũng có thể chọn collation:

```sql
SELECT display_name
FROM customer
ORDER BY display_name COLLATE "C";
```

Collation "C" thường dùng thứ tự dựa trên byte/code point theo encoding và không giống locale-aware collation. Ý nghĩa chính xác tùy encoding/platform.

## 5. Collation provider: libc và ICU

PostgreSQL có thể lấy collation rules từ các provider khác nhau:

| Provider | Nguồn quy tắc | Điểm cần quan tâm |
|---|---|---|
| libc | Locale library của hệ điều hành, thường là glibc trên Linux | Có thể đổi khi nâng cấp OS/glibc |
| ICU | International Components for Unicode | Có thể đổi khi nâng cấp ICU hoặc dữ liệu locale |
| builtin/khác | Provider được hỗ trợ ở một số phiên bản mới | Kiểm tra feature support theo PostgreSQL version |

Provider có sẵn phụ thuộc cách PostgreSQL được build và phiên bản. Không phải mọi cluster đều hỗ trợ ICU.

### libc

Collation libc dựa trên locale của hệ điều hành. Nâng cấp distribution có thể cập nhật glibc hoặc locale data, làm thay đổi version và thứ tự so sánh. Hai servers chạy hai OS releases khác nhau có thể không có cùng behavior dù database catalog giống nhau.

### ICU

ICU cung cấp locale-aware sorting và tailoring. ICU version hoặc locale data có thể thay đổi giữa các bản phát hành. Named ICU collations thường lưu provider, locale và version metadata trong PostgreSQL catalog.

### Chọn provider

ICU có thể cung cấp behavior nhất quán hơn giữa các hệ điều hành nếu triển khai và version được kiểm soát, nhưng ICU cũng có version changes. Không có provider nào loại bỏ nhu cầu kiểm tra collation version và reindex khi quy tắc thay đổi.

## 6. Deterministic và nondeterministic collations

PostgreSQL hỗ trợ deterministic và nondeterministic collations trong các phiên bản có ICU support.

- Deterministic collation phân biệt hai strings khác nhau ở mức bytes ngay cả khi provider xem chúng có cùng sort weight.
- Nondeterministic collation có thể xem một số strings khác bytes là tương đương theo quy tắc ICU, ví dụ một số khác biệt về case hoặc accents tùy locale/rules.

Ví dụ tạo ICU collation trong phiên bản hỗ trợ:

```sql
CREATE COLLATION app_case_insensitive (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
```

Đây là ví dụ minh họa; ICU locale keywords và tính năng được hỗ trợ phụ thuộc PostgreSQL/ICU version. Nondeterministic collations có giới hạn về một số index/operator operations; đọc tài liệu phiên bản trước khi dùng.

## 7. Vì sao nâng cấp hệ điều hành ảnh hưởng collation?

PostgreSQL không tự đóng gói toàn bộ locale database của libc vào data directory. Với libc provider, server dùng locale implementation từ runtime host. Khi package OS được cập nhật, quy tắc locale có thể thay đổi.

Các thay đổi có thể đến từ:

- glibc update.
- ICU library update.
- Locale definitions/data update.
- Thay đổi OS distribution/release.
- Thay đổi container base image.
- Thay đổi provider hoặc locale configuration khi tạo cluster/database.

Một container image mới cũng có thể chứa ICU/glibc version khác dù PostgreSQL major version không đổi.

## 8. Rủi ro khi index được xây dựng theo collation cũ

B-tree index lưu entries theo thứ tự mà comparator/collation cung cấp tại thời điểm build. Nếu comparator thay đổi, thứ tự vật lý của index có thể không còn khớp với thứ tự mà server hiện tại dùng khi tìm kiếm.

Hậu quả có thể gồm:

- Index scan bỏ sót hoặc trả kết quả không đúng.
- ORDER BY dùng index cho ra thứ tự không khớp comparator hiện tại.
- Range predicates trên text hoạt động sai.
- Unique index phát hiện duplicate mới khi rebuild.
- Kết quả ứng dụng thay đổi sau khi query chuyển từ index scan sang sequential scan hoặc ngược lại.

Đây là vấn đề tính đúng đắn, không chỉ là hiệu năng. Khi PostgreSQL cảnh báo collation version mismatch, cần xử lý trước khi tin cậy các index phụ thuộc collation.

## 9. Unique index và duplicate conflicts

Giả sử trước nâng cấp, hai strings được collation cũ xem là khác nhau; sau nâng cấp, collation mới xem chúng tương đương trong unique index. Khi REINDEX unique index, PostgreSQL có thể phát hiện duplicate và từ chối hoàn thành.

### Vì sao cần chuẩn bị?

- Dữ liệu có thể chứa hai giá trị trước đây được chấp nhận nhưng nay xung đột.
- Unique constraint được thực thi bởi unique index nên rebuild có thể thất bại.
- Không thể tự động quyết định bản ghi nào phải giữ.
- Ứng dụng có thể cần merge/rename dữ liệu trước khi index được tạo lại.

Trước cutover, kiểm tra các cặp giá trị có khả năng tương đương theo collation mới bằng cách thử trên môi trường clone có cùng provider/version. Không chỉ dùng equality theo collation cũ để dự đoán kết quả mới.

## 10. Version tracking trong PostgreSQL

PostgreSQL lưu version collation đã biết tại thời điểm tạo database/collation. Khi server chạy, có thể so sánh recorded version với actual version do provider hiện tại trả về.

Hai vùng metadata quan trọng:

- Database default collation version trong catalog pg_database.
- Version của từng named collation trong pg_collation.

Các fields/functions có thể khác theo major version. Trên các phiên bản hỗ trợ, dùng các functions actual-version để kiểm tra mismatch.

## 11. Kiểm tra database default collation version

Query trên PostgreSQL versions hỗ trợ:

```sql
SELECT
    datname,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion,
    pg_catalog.pg_database_collation_actual_version(oid)
        AS actual_collation_version
FROM pg_catalog.pg_database
WHERE datallowconn
  AND datcollversion IS DISTINCT FROM
      pg_catalog.pg_database_collation_actual_version(oid)
ORDER BY datname;
```

Các cột datlocprovider/datcollversion và function actual version cần được xác minh theo PostgreSQL major version. Nếu query báo column/function không tồn tại, tra tài liệu/catalog của version đó thay vì suy luận rằng không có mismatch.

### Ý nghĩa

- datcollversion: version được lưu trong database catalog.
- actual version: version provider hiện tại báo cho locale.
- IS DISTINCT FROM: so sánh an toàn cả khi một bên NULL.

Query này phát hiện database default collation mismatch. Nó không thay thế việc kiểm tra từng named collation.

## 12. Kiểm tra named collations

Trong từng database:

```sql
SELECT
    oid,
    collname,
    collprovider,
    collcollate,
    collctype,
    colliculocale,
    collversion,
    pg_catalog.pg_collation_actual_version(oid)
        AS actual_collation_version
FROM pg_catalog.pg_collation
WHERE collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(oid)
ORDER BY collname;
```

Một số columns như colliculocale chỉ có ở PostgreSQL versions có hỗ trợ ICU metadata. Điều chỉnh SELECT theo catalog schema của major version.

### Vì sao chạy trong từng database?

Collations là database objects. Một database có thể có named collations riêng, kể cả khi database default locale giống database khác. Kiểm kê toàn cluster cần kết nối lần lượt tới từng database có thể truy cập.

## 13. Xem tất cả collations và provider

Để kiểm kê trước khi nâng cấp:

```sql
SELECT
    collname,
    collprovider,
    collisdeterministic,
    collcollate,
    collctype,
    collversion
FROM pg_catalog.pg_collation
ORDER BY collprovider, collname;
```

Các columns có thể khác theo version/provider. Mục tiêu inventory là biết:

- Collation nào là default.
- Collation nào do application tạo.
- Provider nào được sử dụng.
- Locale/rules nào được cấu hình.
- Version nào đang được lưu.
- Schema/table/index nào phụ thuộc chúng.

## 14. Phát hiện mismatch không đồng nghĩa đã tìm hết indexes

Database-level mismatch cho biết locale version khác với version được lưu. Named collation mismatch cho biết một collation object cần được xử lý. Tuy nhiên, để lên kế hoạch reindex, cần xác định indexes phụ thuộc các collations đó.

Indexes có thể chứa text key columns, expression keys hoặc collation được chỉ định tường minh. Kiểm tra index catalog thay vì chỉ tìm tên cột kiểu text.

## 15. Tìm indexes dùng named collations bị mismatch

Trên các phiên bản có pg_collation_actual_version:

```sql
WITH mismatched_collations AS (
    SELECT oid, collname
    FROM pg_catalog.pg_collation
    WHERE collversion IS DISTINCT FROM
          pg_catalog.pg_collation_actual_version(oid)
)
SELECT DISTINCT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    mc.collname AS collation_name
FROM pg_catalog.pg_index AS ix
JOIN pg_catalog.pg_class AS idx
  ON idx.oid = ix.indexrelid
JOIN pg_catalog.pg_class AS tbl
  ON tbl.oid = ix.indrelid
JOIN pg_catalog.pg_namespace AS ns
  ON ns.oid = tbl.relnamespace
CROSS JOIN LATERAL unnest(ix.indcollation) AS ic(collation_oid)
JOIN mismatched_collations AS mc
  ON mc.oid = ic.collation_oid
ORDER BY schema_name, table_name, index_name;
```

Query này tìm collations được khai báo trong index key metadata. Kiểm tra khả năng tương thích của unnest với catalog type trên major version cụ thể. Với database default collation mismatch, đối chiếu thêm datcollversion và các indexes dùng default collation; không kết luận chỉ từ named-collation query.

## 16. Kiểm tra index definitions

Để xem definition của indexes trong schema:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
```

Index definition giúp phát hiện expression, COLLATE clauses, operator classes và unique constraints. Kết hợp với pg_index.indcollation để biết collation OIDs được index dùng.

Không chỉ tìm từ khóa text trong indexdef; collation có thể được kế thừa từ column/expression.

## 17. Database default mismatch và named collation mismatch

Hai loại mismatch cần được quản lý riêng:

| Loại | Metadata | Refresh command |
|---|---|---|
| Database default collation | pg_database.datcollversion | ALTER DATABASE ... REFRESH COLLATION VERSION |
| Named collation | pg_collation.collversion | ALTER COLLATION ... REFRESH VERSION |

Refresh chỉ cập nhật version metadata. Nó không tự rebuild indexes hoặc sửa dữ liệu đã được sắp xếp theo quy tắc cũ.

### Thứ tự bắt buộc

1. Phát hiện mismatch.
2. Xác định indexes/objects phụ thuộc.
3. Rebuild các indexes cần thiết theo provider version mới.
4. Kiểm tra unique conflicts và correctness.
5. Chỉ sau khi reindex hoàn tất mới refresh recorded collation version.

Nếu refresh metadata trước khi reindex, PostgreSQL có thể không còn cảnh báo mismatch dù indexes vẫn được xây dựng theo thứ tự cũ.

## 18. ALTER COLLATION REFRESH VERSION

Với named collation:

```sql
ALTER COLLATION app_schema.app_locale REFRESH VERSION;
```

Tên schema/collation phải xác định đúng object. Lệnh cập nhật recorded version theo actual provider version hiện tại.

### Điều lệnh không làm

- Không chạy REINDEX.
- Không thay đổi locale/rules của collation.
- Không kiểm tra và giải quyết duplicate values.
- Không sửa mọi database khác.

Chỉ chạy sau khi các dependent indexes đã được rebuild và xác minh.

## 19. ALTER DATABASE REFRESH COLLATION VERSION

Với database default collation:

```sql
ALTER DATABASE appdb REFRESH COLLATION VERSION;
```

Lệnh này cập nhật metadata version của database default collation. Nó không rebuild indexes và không refresh các named collations riêng.

### Phạm vi

Chạy cho từng database bị mismatch. Một database refresh thành công không tự cập nhật database khác hoặc template database.

## 20. REINDEX là gì?

REINDEX xây dựng lại index từ table data hiện tại. Khi collation ordering thay đổi, rebuild tạo lại index entries theo comparator mới.

Một số hình thức:

```sql
REINDEX INDEX app_schema.customer_name_idx;
REINDEX TABLE app_schema.customer;
REINDEX SCHEMA app_schema;
REINDEX DATABASE appdb;
```

REINDEX DATABASE chỉ tác động database hiện tại; kết nối tới database cần xử lý và chạy lệnh trong đúng context. REINDEX DATABASE không chạy trong transaction block. Cú pháp/permission/behavior có thể khác theo PostgreSQL version.

## 21. REINDEX INDEX và REINDEX TABLE

REINDEX INDEX nhắm tới một index cụ thể. Đây là lựa chọn phù hợp khi đã xác định chính xác index bị ảnh hưởng.

REINDEX TABLE rebuild các indexes của table. Nó rộng hơn cần thiết nếu chỉ một index dùng collation thay đổi, nhưng có thể đơn giản hóa runbook cho một table.

### Chọn phạm vi

- Index cụ thể: giảm thời gian và WAL nếu dependency inventory đáng tin cậy.
- Table: hữu ích khi nhiều indexes trên table bị ảnh hưởng.
- Schema/database: phù hợp với maintenance window hoặc khi muốn xử lý toàn bộ indexes trong phạm vi đã xác định.

Không chọn REINDEX DATABASE chỉ vì dễ viết nếu cluster có workload lớn và cần kiểm soát downtime.

## 22. REINDEX DATABASE và mọi database trong cluster

Một cluster PostgreSQL có thể chứa nhiều databases. REINDEX DATABASE appdb chỉ rebuild indexes trong appdb. Phải lặp lại cho từng database có mismatch/indexes liên quan.

Inventory nên gồm:

- Application databases.
- Databases chứa extensions hoặc shared application objects.
- template1 nếu nó có collations/indexes được dùng làm template cho database mới.
- Database maintenance/monitoring nếu có user-defined collations.

template0 thường được giữ làm pristine template và không cho phép kết nối thông thường. Không thay đổi template0 như một bước mặc định; tuân thủ hướng dẫn PostgreSQL cho version đang dùng.

## 23. REINDEX SYSTEM

REINDEX SYSTEM rebuild indexes trên system catalogs của database hiện tại. Phần lớn indexes catalog dùng các semantics nội bộ không phụ thuộc locale application, nên không mặc định chạy REINDEX SYSTEM chỉ vì OS collation version đổi.

Chỉ dùng khi có lý do cụ thể hoặc PostgreSQL/vendor runbook yêu cầu. REINDEX SYSTEM có tác động rộng và có thể yêu cầu quyền cao, maintenance planning.

## 24. REINDEX CONCURRENTLY

Trên PostgreSQL versions hỗ trợ, REINDEX CONCURRENTLY giảm thời gian khóa ghi đối với table/index bằng cách tạo index mới trong khi cho phép concurrent operations theo cơ chế nhiều phase.

Ví dụ:

```sql
REINDEX INDEX CONCURRENTLY app_schema.customer_name_idx;
```

Ưu điểm:

- Hạn chế blocking writes trong phần lớn quá trình.
- Hữu ích cho production tables cần availability cao.

Chi phí/ràng buộc:

- Tốn thêm disk space trong thời gian build.
- Tạo thêm I/O, CPU và WAL.
- Có nhiều phases và có thể mất lâu hơn.
- Có thể thất bại và để lại invalid index cần xử lý.
- Không chạy bên trong transaction block.
- Có giới hạn với một số index types/constraints và catalog indexes.

Đọc tài liệu đúng PostgreSQL version trước khi dùng. Không coi CONCURRENTLY là không có lock hoặc không có operational impact.

## 25. Chọn REINDEX thường hay CONCURRENTLY

| Tiêu chí | REINDEX thường | REINDEX CONCURRENTLY |
|---|---|---|
| Blocking writes | Có thể khóa ghi table trong quá trình | Giảm blocking ghi, vẫn có lock ở các phase |
| Thời gian | Thường ngắn hơn | Thường lâu hơn do nhiều phase |
| Disk tạm | Cần space cho build | Thường cần space bổ sung lớn hơn |
| WAL/I/O | Có thể lớn | Cũng lớn, có thể kéo dài hơn |
| Transaction block | Không cho một số forms | Không chạy trong transaction block |
| Operational complexity | Đơn giản hơn | Cần theo dõi phases/invalid indexes |

Nếu có maintenance window rõ và có thể chấp nhận khóa, REINDEX thường có thể đơn giản hơn. Nếu cần duy trì writes, CONCURRENTLY có thể phù hợp khi index type/version hỗ trợ và đủ capacity.

## 26. Disk space và WAL khi reindex

Reindex có thể cần tạo bản index mới trước khi bản cũ được loại bỏ. Dung lượng cần thiết phụ thuộc kích thước index, concurrency, temporary build files và storage layout.

Tính cả:

- Index size hiện tại.
- Bản index mới trong quá trình build.
- WAL generation.
- WAL archive backlog.
- Replication slot retention.
- Standby catch-up capacity.
- Temp files và free space trên từng mount.

Không bắt đầu reindex hàng loạt khi pg_wal hoặc archive destination gần đầy. Reindex trên primary có thể tạo lượng WAL đáng kể và làm standbys lag.

## 27. Reindex và replication

Với physical streaming replication, thay đổi index trên primary được ghi vào WAL và replay trên standbys. Standby ở recovery mode không chạy REINDEX độc lập cho cùng physical cluster.

Trước/sau reindex:

- Kiểm tra standby streaming state.
- Theo dõi replay lag.
- Kiểm tra WAL archive và replication slots.
- Đảm bảo standbys dùng cùng OS/ICU/libc collation version với primary.
- Không đưa standby có locale mismatch vào read traffic phụ thuộc index.

Nếu primary và standby dùng provider versions khác nhau, cùng một index structure có thể được diễn giải theo comparator khác nhau trên mỗi node. Giữ runtime locale versions đồng nhất là yêu cầu quan trọng.

## 28. Logical replication

Logical replication không tự replicate mọi DDL/index maintenance operation. Subscriber có thể có indexes được tạo riêng và cần reindex tại subscriber nếu collation version của nó thay đổi.

Kế hoạch cho logical replication:

1. Inventory publisher và subscribers.
2. Xác định OS/ICU/libc versions trên từng node.
3. Reindex indexes phụ thuộc collation trên mỗi database subscriber.
4. Kiểm tra constraints/unique conflicts riêng.
5. Đồng bộ DDL/schema changes theo quy trình logical replication.
6. Theo dõi apply workers và lag.

Không giả định reindex trên publisher tự sửa indexes trên subscribers.

## 29. Partitioned tables và collation

Nếu partition key hoặc expression dùng text collation, thay đổi thứ tự so sánh có thể ảnh hưởng cách so sánh partition bounds và việc định tuyến rows mới.

Sau nâng cấp:

- Xem partition key definitions.
- Xác định collations gắn với partition key expressions.
- Kiểm tra partition bounds theo comparator mới.
- Xác nhận rows hiện có vẫn thuộc partition đúng theo policy.
- Test insert/update routing trên clone.
- Kiểm tra unique constraints/indexes trên partitioned tables theo giới hạn version.

Reindex không tự di chuyển rows giữa partitions nếu semantics của partition bounds thay đổi. Cần đánh giá riêng dữ liệu và routing logic.

## 30. Constraints và dữ liệu hiện có

Unique constraints thường dựa trên unique indexes. Khi collation mới coi hai giá trị là tương đương, reindex có thể thất bại vì duplicate keys.

Check constraints có thể chứa biểu thức text comparison. Việc đổi collation không tự động chạy lại mọi check constraint trên dữ liệu hiện có.

### Trước khi reindex

- Tìm unique indexes phụ thuộc collation.
- Tìm constraints dùng text comparisons.
- Test duplicate detection bằng collation mới trên clone.
- Xác định business rule để merge/rename dữ liệu nếu có conflict.
- Chuẩn bị downtime/transaction plan cho data cleanup.

Không tự động xóa hoặc sửa một trong các duplicate records. Quyết định thuộc business data owner.

## 31. Tác động tới query plans và kết quả

Sau reindex, planner có thể chọn plan khác do index statistics/size thay đổi hoặc index mới phù hợp hơn. Tuy nhiên, reindex không thay thế ANALYZE khi statistics cần cập nhật.

Kiểm tra:

- ORDER BY text trước/sau.
- Range predicates trên text.
- Equality/uniqueness behavior.
- Index scans và bitmap scans.
- Query plans cho workload quan trọng.
- Latency/throughput sau rebuild.

Chạy ANALYZE cho tables liên quan nếu cần cập nhật statistics; không nhầm ANALYZE với REINDEX.

## 32. Collation mismatch warning

PostgreSQL có thể cảnh báo database/collation version mismatch khi khởi động hoặc khi dùng collation. Warning báo rằng version được lưu khác actual provider version.

Warning không có nghĩa mọi index chắc chắn đã trả kết quả sai, nhưng cần coi là rủi ro correctness cho dependent objects. Không suppress warning bằng refresh metadata trước khi rebuild.

### Quy trình xử lý warning

1. Ghi nhận database/collation/provider.
2. Xác định OS/ICU/glibc version thay đổi.
3. Xác định indexes/objects phụ thuộc.
4. Đánh giá duplicate conflicts và capacity.
5. Reindex.
6. Verify.
7. Refresh version metadata.
8. Restart/recheck logs nếu runbook yêu cầu.

## 33. Kiểm tra locale runtime trên Linux

Một số lệnh hỗ trợ inventory:

```sh
ldd --version
locale
locale -a
```

Nếu dùng ICU, công cụ như icuinfo hoặc package manager có thể cho biết ICU library version, tùy distribution.

### Container image

Kiểm tra bên trong đúng container image/pod đang chạy PostgreSQL, không chỉ trên host. Container có thể đóng gói ICU/glibc khác host; dynamic linking và mounted libraries cũng có thể ảnh hưởng runtime.

Ghi lại:

- OS release.
- glibc version.
- ICU version/package.
- PostgreSQL build/version.
- Locale definitions.
- Container image digest.

## 34. Kiểm tra PostgreSQL build và collation providers

```sql
SELECT version();

SELECT
    collprovider,
    count(*) AS collation_count
FROM pg_catalog.pg_collation
GROUP BY collprovider
ORDER BY collprovider;
```

Kiểm tra PostgreSQL version, build platform và provider inventory. Không dựa vào package version đơn lẻ để suy luận runtime locale data.

## 35. Test collation behavior trước/sau nâng cấp

Tạo test dataset đại diện cho ngôn ngữ/dữ liệu thực tế:

```sql
CREATE TEMP TABLE collation_probe (
    value text COLLATE "default"
);

INSERT INTO collation_probe(value)
VALUES
    ('a'),
    ('A'),
    ('á'),
    ('ä'),
    ('z'),
    ('đ'),
    ('Đ'),
    ('I'),
    ('i'),
    ('ı');

SELECT value
FROM collation_probe
ORDER BY value;
```

Kết quả cụ thể phụ thuộc database locale/provider. Lưu output trên môi trường cũ, chạy cùng test trên clone đã nâng cấp và so sánh. Thêm dữ liệu domain-specific, đặc biệt tên người, địa chỉ, SKU/text keys và ngôn ngữ ứng dụng hỗ trợ.

## 36. Test uniqueness theo collation mới

Trên clone dùng provider mới, tạo unique index thử trên tập dữ liệu đại diện:

```sql
CREATE TEMP TABLE unique_probe (
    value text COLLATE "default"
);

INSERT INTO unique_probe(value)
VALUES ('A'), ('a'), ('á'), ('Á');

CREATE UNIQUE INDEX unique_probe_value_idx
ON unique_probe(value);
```

Nếu index build thất bại, dữ liệu chứa values được xem là trùng theo comparator mới. Đây là test minh họa; dùng đúng target collation và unique index definitions của ứng dụng.

## 37. Backup và rollback planning

Trước OS/ICU upgrade:

- Backup base backup/physical snapshot theo policy.
- Xác nhận WAL archive liên tục.
- Test restore gần đây.
- Ghi lại PostgreSQL config và OS package versions.
- Lưu output collation inventory/version.
- Lưu index inventory và sizes.
- Xác định rollback boundary.

### Rollback không chỉ là downgrade package

Nếu data directory đã được sử dụng dưới runtime collation mới, quay lại OS/library cũ có thể tạo mismatch ngược. Nếu đã reindex theo collation mới, old runtime có thể lại diễn giải index theo quy tắc cũ.

Một rollback an toàn có thể cần restore snapshot/backup hoặc hoàn nguyên cả OS/library và index state theo kế hoạch đã thử. Không giả định downgrade package là đủ.

## 38. Nâng cấp OS riêng với PostgreSQL major upgrade

Không gộp OS upgrade, PostgreSQL major upgrade và collation change thành một bước không thể phân biệt nguyên nhân.

Khuyến nghị:

- Lập compatibility matrix OS/PostgreSQL/extensions.
- Test OS upgrade với cùng PostgreSQL major version trước nếu có thể.
- Sau đó lập kế hoạch major upgrade riêng.
- Ghi nhận collation versions trước/sau mỗi bước.
- Reindex theo đúng hướng dẫn cho từng transition.

pg_upgrade có thể phát hiện collation version mismatch và đưa ra cảnh báo; tuân thủ output và tài liệu đúng version. Không bỏ qua cảnh báo vì server vẫn khởi động được.

## 39. Nâng cấp primary và standby

Với physical replication, các node cần cùng collation semantics để query trên standby sử dụng indexes an toàn.

Một trình tự tham khảo:

1. Xác nhận OS/ICU/glibc target version.
2. Kiểm tra compatibility trên clone.
3. Đưa standby ra khỏi read traffic.
4. Nâng cấp standby theo orchestration và kiểm tra provider versions.
5. Giữ standby không phục vụ collated reads khi version chưa đồng nhất với index state.
6. Nâng cấp primary theo failover/maintenance plan đã kiểm thử.
7. Reindex trên writable primary theo kế hoạch.
8. Theo dõi WAL replay để standbys nhận index rebuild.
9. Đồng bộ runtime locale versions trên mọi nodes.
10. Refresh metadata và xác minh mismatch biến mất.
11. Chỉ đưa nodes trở lại read traffic sau khi validation hoàn tất.

Thứ tự chính xác phụ thuộc HA manager, synchronous replication, downtime budget và cách nâng cấp storage/OS. Không để primary và standby có locale versions khác nhau trong khi cùng phục vụ queries phụ thuộc collated indexes.

## 40. Rolling upgrade và read traffic

Nếu OS upgrade được thực hiện rolling:

- Node đã nâng cấp có thể dùng comparator mới.
- Node chưa nâng cấp vẫn dùng comparator cũ.
- Physical standby replay index pages do primary tạo, nhưng query comparator tại standby đến từ runtime local.
- Một read query trên standby có thể dùng index với semantics không khớp.

Vì vậy, trong giai đoạn mixed versions, giữ node không đồng nhất khỏi read routing cho workload chịu ảnh hưởng. Đặt maintenance/health labels theo collation readiness, không chỉ TCP/replication health.

## 41. Reindex trên primary: quy trình tổng thể

1. Xác định mọi databases có default/named collation mismatch.
2. Lập danh sách indexes bị ảnh hưởng và unique constraints.
3. Kiểm tra duplicate conflicts trên clone dùng locale mới.
4. Đánh giá disk, WAL, archive, slots và standby capacity.
5. Chọn targeted REINDEX hay database-wide REINDEX.
6. Chọn thường hay CONCURRENTLY theo availability/version constraints.
7. Reindex indexes/tables trong từng database.
8. Xác minh indexes hợp lệ và queries đúng.
9. Cập nhật statistics khi cần.
10. Refresh named collations.
11. Refresh database default collation.
12. Kiểm tra warning/version mismatch lần cuối.

Refresh metadata phải ở cuối sau khi dependent indexes được xử lý.

## 42. Refresh version cho nhiều named collations

Sau khi reindex các dependent indexes, chạy ALTER COLLATION REFRESH VERSION cho từng collation bị mismatch.

Có thể generate danh sách lệnh từ catalog, nhưng phải review tên/schema và thứ tự trước khi thực thi. Không chạy generated SQL một cách mù quáng trong production.

Ví dụ tạo command text:

```sql
SELECT format(
    'ALTER COLLATION %I.%I REFRESH VERSION;',
    n.nspname,
    c.collname
)
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.collnamespace
WHERE c.collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(c.oid)
ORDER BY n.nspname, c.collname;
```

Query này chỉ tạo command text cho review. Không tự động chạy lệnh nếu reindex chưa hoàn tất.

## 43. Refresh database default collation

Sau khi xử lý indexes phụ thuộc default collation:

```sql
ALTER DATABASE appdb REFRESH COLLATION VERSION;
```

Thực hiện trong session được kết nối tới database khác hoặc theo restriction của PostgreSQL version. Lệnh không rebuild indexes và không refresh named collations.

## 44. Kiểm tra sau refresh

Chạy lại database mismatch query và named collation mismatch query. Kết quả mong muốn là không còn mismatches chưa xử lý trong scope.

Đồng thời kiểm tra:

- PostgreSQL logs không còn warning collation version mismatch cho objects đã xử lý.
- Indexes liên quan valid/ready.
- Unique constraints vẫn hợp lệ.
- Query results/order phù hợp expected behavior.
- Physical standbys replay hoàn tất.
- Logical subscribers đã được reindex riêng.

Không dùng “không còn warning” làm bằng chứng duy nhất rằng data semantics đã đúng; cần validation theo workload.

## 45. REINDEX thất bại do duplicate keys

Nếu unique index rebuild thất bại:

1. Ghi lại index/constraint và lỗi duplicate key.
2. Xác định collation mới thực tế đang được dùng.
3. Tìm các values bị coi là tương đương.
4. Đối chiếu business ownership và semantics.
5. Quyết định merge/rename/normalize records với data owner.
6. Kiểm tra foreign keys/references và application dependencies.
7. Thực hiện cleanup có backup và audit.
8. Rebuild unique index.
9. Kiểm tra constraint và application behavior.
10. Chỉ sau đó refresh collation metadata.

Không drop unique constraint để làm reindex qua được rồi quên khôi phục integrity. Nếu cần khoảng thời gian không có constraint, phải có guard/maintenance plan thay thế.

## 46. REINDEX CONCURRENTLY thất bại

Concurrent reindex có thể thất bại vì duplicate keys, cancellation, deadlock, disk exhaustion hoặc lỗi runtime. Có thể để lại invalid index cần điều tra.

Kiểm tra:

```sql
SELECT
    ns.nspname,
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready,
    ix.indislive
FROM pg_catalog.pg_index AS ix
JOIN pg_catalog.pg_class AS idx
  ON idx.oid = ix.indexrelid
JOIN pg_catalog.pg_namespace AS ns
  ON ns.oid = idx.relnamespace
WHERE NOT ix.indisvalid
   OR NOT ix.indisready
ORDER BY ns.nspname, idx.relname;
```

Các flags catalog có ý nghĩa riêng và có thể thay đổi theo version. Xác định index nào invalid do concurrent build, đọc logs, rồi drop/rebuild theo documented procedure. Không refresh collation metadata khi index cần thiết vẫn chưa hợp lệ.

## 47. Reindex progress monitoring

Các PostgreSQL versions mới cung cấp progress views cho một số maintenance commands, bao gồm REINDEX. Kiểm tra catalog view theo version, ví dụ pg_stat_progress_create_index cho progress của index builds.

```sql
SELECT *
FROM pg_catalog.pg_stat_progress_create_index;
```

Theo dõi:

- Index/table đang build.
- Phase hiện tại.
- Tuổi command.
- Wait events/locks.
- Disk free và WAL generation.
- Standby replay lag.

Không kill backend chỉ vì progress đứng yên trong một phase ngắn; xem wait events, locks và storage I/O.

## 48. Reindex và locks

REINDEX thường có thể block writes trên table/index tùy command/version. REINDEX CONCURRENTLY giảm blocking nhưng vẫn lấy locks ở các phase và có thể chờ transactions lâu.

Trước khi chạy:

- Xem long-running transactions.
- Xem idle-in-transaction sessions.
- Xem DDL/deploy windows.
- Đặt lock_timeout/statement_timeout theo runbook.
- Chạy từng batch nhỏ.
- Theo dõi lock waits và application latency.

Không đặt timeout quá ngắn khiến concurrent build liên tục restart, cũng không để DDL chờ vô hạn.

## 49. Reindex và bloat

Reindex có thể loại bỏ index bloat bằng cách xây lại index từ heap data. Nhưng mục tiêu chính trong collation upgrade là correctness của index ordering. Không coi mọi bloat problem là collation mismatch.

### So sánh

- REINDEX do collation change: bắt buộc khi index semantics bị ảnh hưởng.
- REINDEX do bloat: quyết định theo index size, page density và workload.
- VACUUM: xử lý dead tuples/reclaim reusable space; không thay REINDEX để cập nhật collation ordering.
- ANALYZE: cập nhật planner statistics; không rebuild index.

## 50. Collation changes và application behavior

Ứng dụng có thể dựa vào thứ tự text ổn định trong:

- Pagination dựa trên ORDER BY text.
- Keyset pagination.
- Cursor tokens.
- Deduplication theo case/accent behavior.
- Search/sort UI.
- Export files có thứ tự deterministic.
- Partition routing theo text.

Sau OS/ICU upgrade, thứ tự có thể thay đổi dù dữ liệu không đổi. Test API pagination và cursor continuation; một cursor được tạo trước upgrade có thể không còn phản ánh cùng thứ tự.

## 51. Collation "C" và "POSIX"

Collation "C" và "POSIX" thường dùng semantics gần binary/code-point order và không phụ thuộc locale language rules như libc locale-aware collations. Chúng có thể phù hợp với keys kỹ thuật cần ordering ổn định, nhưng không tự động là lựa chọn đúng cho mọi text field.

### Lưu ý khi chuyển collation

Đổi column/expression sang "C" có thể thay đổi equality/order semantics của ứng dụng. Cần tạo index phù hợp và kiểm thử query behavior. Không thể chỉ đổi collation metadata để tránh reindex mà không đánh giá business semantics.

## 52. ICU custom rules và locale identifiers

ICU collations có thể dùng locale identifier và custom tailoring/rules trong các phiên bản hỗ trợ. Khi nâng ICU, kết quả sort có thể đổi ngay cả khi locale identifier không đổi.

Inventory cần lưu:

- Collation name.
- Provider.
- ICU locale identifier.
- Deterministic setting.
- Custom rules nếu có.
- Recorded version.
- Actual version.

Không đổi ICU locale/rules trong cùng change window với OS upgrade nếu có thể tách riêng; tách giúp xác định nguyên nhân và rollback.

## 53. Nhiều databases và template1

Collations và indexes là database-local objects. Một cluster có thể có mismatch ở nhiều databases với các custom collations khác nhau.

Quy trình inventory:

1. Liệt kê databases và default locale/provider/version.
2. Kết nối từng database.
3. Liệt kê named collation mismatches.
4. Lập index dependency list.
5. Reindex và refresh trong từng database.
6. Kiểm tra template1 nếu được dùng để tạo databases mới.

Nếu template1 giữ recorded version cũ, database mới được tạo từ template có thể cần xử lý tương tự. Không thao tác template0 theo thói quen.

## 54. Monitoring trong và sau OS upgrade

Theo dõi:

- PostgreSQL startup warnings/errors.
- Collation mismatch inventory.
- REINDEX progress/failures.
- Invalid index count.
- Unique constraint errors.
- Disk free bytes/inodes.
- WAL generation/archive backlog.
- Physical standby replay lag.
- Logical replication lag/apply errors.
- Query latency, error rate và pagination correctness.

Đặt alerts cho filesystem gần đầy và replication lag trước khi bắt đầu reindex. Reindex có thể làm tăng WAL và disk pressure.

## 55. Change plan cho production

Một change request nên ghi:

- Cluster/database scope.
- OS, glibc, ICU và PostgreSQL versions trước/sau.
- Collation providers/locales liên quan.
- Indexes và constraints bị ảnh hưởng.
- Disk/WAL estimate.
- Chọn REINDEX mode và lock impact.
- Primary/standby/logical subscriber sequence.
- Application traffic/read-routing plan.
- Backup/restore checkpoint.
- Validation criteria.
- Rollback decision point và owner.

Không bắt đầu chỉ dựa vào một câu “OS upgrade completed”; cần có version inventory và collation comparison.

## 56. Runbook: trước khi nâng cấp OS

1. Xác định PostgreSQL major/minor version và package source.
2. Ghi lại OS release, glibc, ICU và locale data versions.
3. Kiểm kê databases, providers và collations.
4. Lưu output database/named collation version queries.
5. Tạo index dependency inventory.
6. Kiểm tra unique indexes và constraints.
7. Clone production sang staging.
8. Nâng cấp OS/ICU trên clone.
9. Reproduce collation mismatches.
10. Test reindex, duplicates, query ordering và application behavior.
11. Ước lượng disk/WAL/replication impact.
12. Chốt maintenance/failover/rollback plan.

## 57. Runbook: sau khi nâng cấp OS

1. Ghi nhận actual glibc/ICU/locale versions trên từng node.
2. Xác nhận PostgreSQL khởi động và đọc logs.
3. Chạy database default collation mismatch query.
4. Chạy named collation mismatch query trong từng database.
5. Lập index list theo collation OIDs.
6. Đưa nodes có runtime mismatch khỏi affected read traffic.
7. Xác định duplicate conflicts và index build capacity.
8. Reindex dependent indexes trên writable primary.
9. Theo dõi WAL/archive/standby replay.
10. Reindex logical subscribers riêng.
11. Verify indexes và query behavior.
12. Refresh named collation versions.
13. Refresh database default versions.
14. Chạy lại mismatch queries và kiểm tra logs.
15. Mở lại traffic sau khi mọi nodes đồng nhất và validation pass.

## 58. Runbook: duplicate conflict khi reindex unique index

1. Dừng bước refresh metadata.
2. Lưu error details và index definition.
3. Xác định collation mới/provider version.
4. Tái hiện trên clone hoặc query có collation tường minh.
5. Tìm rows xung đột theo comparator mới.
6. Tham vấn data owner về canonical value.
7. Xử lý references, foreign keys và downstream consumers.
8. Backup/record affected rows.
9. Merge/rename/normalize data theo approved change.
10. Rebuild unique index/constraint.
11. Verify uniqueness và application behavior.
12. Tiếp tục refresh version metadata.

## 59. Runbook: standby có collation version khác primary

1. Xác định provider/runtime versions trên primary và standby.
2. Kiểm tra recorded/actual version tại standby.
3. Ngừng route collated reads tới node không đồng nhất.
4. Xác nhận OS/ICU upgrade plan cho toàn topology.
5. Reindex trên primary sau khi provider version mục tiêu đã được thống nhất.
6. Theo dõi WAL replay hoàn tất trên standby.
7. Xác minh standby runtime version khớp primary.
8. Chạy query probes trên standby.
9. Chỉ đưa node trở lại read pool sau validation.

Không chạy REINDEX độc lập trên physical standby đang recovery.

## 60. Runbook: REINDEX CONCURRENTLY bị lỗi

1. Ghi lại command, index, PostgreSQL version và error.
2. Kiểm tra logs và lock waits.
3. Kiểm tra disk/inodes/WAL capacity.
4. Kiểm tra pg_index flags của index.
5. Xác định concurrent build có để invalid index không.
6. Kiểm tra duplicate conflict nếu là unique index.
7. Drop/rebuild invalid index theo documented procedure.
8. Điều chỉnh workload/window/timeout nếu cần.
9. Chạy lại và theo dõi progress.
10. Chỉ refresh collation metadata sau khi mọi dependent indexes hợp lệ.

## 61. Checklist collation upgrade

### Inventory

- OS/glibc/ICU/PostgreSQL versions được ghi lại.
- Database default locale/provider/version được kiểm kê.
- Named collations và custom ICU rules được kiểm kê.
- Dependent indexes/constraints được liệt kê.
- Primary, physical standbys và logical subscribers được tính đến.

### Capacity và availability

- Backup/restore checkpoint sẵn sàng.
- Disk space/inodes đủ cho rebuild.
- WAL/archive/replication slots có headroom.
- Standby replay capacity được kiểm tra.
- REINDEX mode và lock impact được phê duyệt.
- Read routing có thể loại node chưa đồng nhất.

### Execution

- Reindex trước refresh metadata.
- Duplicate conflicts được xử lý có approval.
- Physical standbys nhận WAL replay.
- Logical subscribers reindex riêng.
- Database và named collation versions được refresh riêng.

### Validation

- Không còn mismatch chưa xử lý.
- Indexes hợp lệ/ready.
- Unique constraints được xác minh.
- ORDER BY/range/pagination probes đúng.
- Replication và application SLO ổn định.
- Logs không còn warning ngoài scope đã giải thích.

## 62. Bài tập thực hành

### Bài 1 — Collation

Giải thích collation là gì và khác encoding UTF8 như thế nào.

### Bài 2 — Provider

So sánh libc và ICU providers. Những thay đổi nào trong OS upgrade có thể làm collation version đổi?

### Bài 3 — Collation usage

Liệt kê các query/index/constraint operations có thể phụ thuộc collation.

### Bài 4 — Default và named collations

Phân biệt database default collation với named collation được gắn trên column/expression.

### Bài 5 — Deterministic

So sánh deterministic và nondeterministic ICU collations. Những giới hạn nào cần kiểm tra?

### Bài 6 — Version mismatch

Giải thích recorded collation version và actual provider version. Vì sao mismatch cần được xử lý?

### Bài 7 — Database inventory

Viết query liệt kê database default collation versions và actual versions trên PostgreSQL version hỗ trợ.

### Bài 8 — Named collation inventory

Viết query tìm pg_collation rows có collversion khác actual version.

### Bài 9 — Index dependencies

Giải thích pg_index.indcollation có thể giúp tìm indexes dùng collations nào.

### Bài 10 — Unique conflict

Hai strings trước đây unique nhưng trở thành tương đương theo collation mới. Điều gì có thể xảy ra khi REINDEX unique index?

### Bài 11 — Refresh version

Phân biệt ALTER COLLATION REFRESH VERSION và ALTER DATABASE REFRESH COLLATION VERSION.

### Bài 12 — Thứ tự operations

Vì sao phải REINDEX trước khi refresh recorded collation version?

### Bài 13 — REINDEX INDEX

Viết lệnh rebuild một index cụ thể và nêu trường hợp nên chọn targeted reindex.

### Bài 14 — REINDEX DATABASE

Một cluster có năm databases. Vì sao một lệnh REINDEX DATABASE chỉ xử lý một database?

### Bài 15 — REINDEX SYSTEM

Giải thích phạm vi REINDEX SYSTEM và vì sao không nên chạy mặc định cho mọi collation mismatch.

### Bài 16 — CONCURRENTLY

So sánh REINDEX INDEX và REINDEX INDEX CONCURRENTLY về locks, disk, WAL và operational complexity.

### Bài 17 — Disk budget

Một database có 400 GB indexes cần rebuild. Liệt kê các disk/WAL/archive headroom cần tính trước khi chạy.

### Bài 18 — Physical replication

Vì sao physical standby không tự chạy REINDEX độc lập? Dữ liệu index rebuild đến standby bằng cách nào?

### Bài 19 — Mixed OS versions

Primary dùng ICU version mới, standby dùng version cũ. Vì sao không nên tiếp tục route collated reads tới standby?

### Bài 20 — Logical replication

Vì sao reindex trên publisher không tự rebuild indexes trên logical subscriber?

### Bài 21 — Partitioning

Collation change có thể ảnh hưởng partition bounds/routing của text partition key như thế nào?

### Bài 22 — Check constraints

Một CHECK constraint dùng text comparison. Vì sao reindex không tự validate lại toàn bộ existing rows?

### Bài 23 — Query correctness

Thiết kế test ORDER BY, range predicates và keyset pagination trước/sau ICU upgrade.

### Bài 24 — Locale probes

Tạo tập dữ liệu có chữ hoa/thường, accents và ký tự tiếng Việt để so sánh sort behavior.

### Bài 25 — Unique probe

Thiết kế thử nghiệm unique index trên clone dùng collation mới để phát hiện duplicate conflicts.

### Bài 26 — OS inventory

Viết lệnh thu thập OS release, glibc, locale list và ICU version trên Linux.

### Bài 27 — Container image

Vì sao OS version trên host chưa đủ để xác định collation runtime của PostgreSQL container?

### Bài 28 — pg_upgrade

Nêu cách xử lý collation mismatch warnings sau pg_upgrade và vì sao không được bỏ qua.

### Bài 29 — Rollback

Vì sao downgrade glibc/ICU sau khi đã reindex có thể tạo mismatch theo chiều ngược lại?

### Bài 30 — Template databases

Vì sao cần kiểm tra template1 trong inventory và không nên sửa template0 theo thói quen?

### Bài 31 — Invalid index

Viết query kiểm tra indisvalid/indisready và mô tả cách xử lý index invalid sau concurrent reindex.

### Bài 32 — Progress

Dùng pg_stat_progress_create_index để theo dõi REINDEX. Những metrics hệ thống nào cần theo dõi cùng?

### Bài 33 — Lock planning

Thiết kế maintenance window cho REINDEX thường trên một table lớn có traffic ghi cao.

### Bài 34 — Bloat

Phân biệt REINDEX vì collation correctness với REINDEX vì bloat, VACUUM và ANALYZE.

### Bài 35 — Application behavior

Một API dùng keyset pagination theo text name. Vì sao cursor cũ có thể không còn ổn định sau collation change?

### Bài 36 — Multi-database runbook

Thiết kế cách chạy inventory, reindex và refresh version cho nhiều databases trong cùng cluster.

### Bài 37 — Standby readiness

Thiết kế health/readiness gate để không route queries tới standby có collation version chưa đồng nhất.

### Bài 38 — Concurrent failure

REINDEX CONCURRENTLY thất bại do disk full và để lại invalid index. Viết runbook xử lý trước khi refresh metadata.

### Bài 39 — Duplicate cleanup

Một unique index rebuild phát hiện duplicate theo collation mới. Thiết kế quy trình phối hợp data owner, merge records và khôi phục constraint.

### Bài 40 — Production OS upgrade end-to-end

Một hệ thống có:

- PostgreSQL primary và ba physical standbys.
- Hai logical subscribers cho reporting/analytics.
- PostgreSQL major version hiện tại không đổi.
- OS upgrade làm glibc và ICU versions thay đổi.
- Database default collation dùng libc.
- Một số application schemas dùng named ICU collations.
- Nhiều unique indexes trên customer names và product labels.
- Một standby phục vụ read traffic.
- WAL archive và replication slots có retention giới hạn.
- Downtime budget 30 phút.

Hãy thiết kế:

1. Inventory OS, provider, locale và recorded/actual versions.
2. Clone-based test cho sorting, uniqueness và query plans.
3. Index dependency/unique conflict discovery.
4. Disk/WAL/archive/standby capacity plan.
5. Primary/standby OS upgrade sequence và read traffic gating.
6. Targeted REINDEX hay database-wide strategy.
7. REINDEX thường hay CONCURRENTLY theo downtime budget.
8. Physical standby WAL replay và logical subscriber reindex.
9. ALTER COLLATION/ALTER DATABASE refresh sequence.
10. Validation, rollback decision point và post-upgrade monitoring.

## Kết luận

**Nâng cấp OS hoặc ICU có thể thay đổi collation semantics mà indexes hiện tại đã dựa vào.** PostgreSQL lưu recorded versions và có thể cảnh báo mismatch, nhưng cảnh báo chỉ giúp phát hiện rủi ro; nó không tự rebuild index. Database default collation và named collations có metadata riêng, vì vậy cần kiểm tra cả hai trong từng database.

Khi version thay đổi, xác định indexes và constraints phụ thuộc collation, đánh giá unique conflicts, capacity và replication impact, rồi REINDEX trước khi refresh version metadata. REINDEX thường có thể khóa writes; REINDEX CONCURRENTLY giảm blocking nhưng cần thêm disk/WAL và có các giới hạn theo version/index type. Physical standbys nhận index changes qua WAL, còn logical subscribers cần xử lý riêng.

OS/ICU versions phải nhất quán trên các nodes phục vụ cùng data. Trong rolling upgrade, không route collated reads tới node có runtime comparator khác index state. Kiểm thử trên clone với dữ liệu đại diện, giữ backup/rollback plan và xác minh query ordering, uniqueness, indexes, replication cùng application behavior.

**Refresh metadata là bước cuối sau reindex.** Làm đúng thứ tự giúp PostgreSQL catalog phản ánh runtime provider mới trong khi các indexes đã được xây dựng lại theo cùng quy tắc.
