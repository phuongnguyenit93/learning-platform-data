# Sự cố sau nâng cấp, thay đổi collation hoặc extension trong PostgreSQL

Một lần nâng cấp PostgreSQL hoặc cập nhật thư viện hệ điều hành có thể làm thay đổi hành vi của database dù dữ liệu vẫn mở được và server đã khởi động thành công. Ứng dụng có thể gặp lỗi thiếu function, không nạp được shared library, query trả thứ tự khác, unique index không còn phù hợp với quy tắc so sánh chuỗi hoặc extension không tương thích với major version mới.

Ba nhóm thay đổi cần được phân biệt:

- **Nâng cấp PostgreSQL:** thay đổi binary/server version, catalog hoặc data directory theo quy trình major/minor upgrade.
- **Thay đổi collation:** cập nhật provider hoặc phiên bản thư viện libc/ICU làm thay đổi quy tắc so sánh và sắp xếp text.
- **Thay đổi extension:** cập nhật package/binary trên máy chủ, SQL objects trong từng database hoặc cấu hình preload.

Các nhóm này có thể xảy ra cùng một maintenance window. Vì vậy, khi có sự cố sau upgrade, cần xác định thành phần nào thay đổi, database nào bị ảnh hưởng, object nào phụ thuộc và trạng thái hiện tại của cluster trước khi chạy lệnh sửa.

Bài học tập trung vào điều tra và phục hồi sau nâng cấp, collation drift và extension incompatibility. Trọng tâm là giữ evidence, xác minh tương thích, rebuild những object bị ảnh hưởng và đưa database/application trở lại trạng thái có thể kiểm chứng.

~~~mermaid
flowchart TD
    A["Sự cố sau upgrade / collation / extension"] --> B["Contain: dừng rollout và thay đổi tiếp"]
    B --> C["Xác minh cluster, version, package, logs"]
    C --> D{"Nhóm nguyên nhân"}
    D -->|"PostgreSQL upgrade"| E["Binary, catalog, config, app compatibility"]
    D -->|"Collation drift"| F["Provider version, dependent indexes"]
    D -->|"Extension"| G["Package, shared library, SQL version, preload"]
    E --> H["Chọn recovery plan"]
    F --> H
    G --> H
    H --> I["Repair / reindex / update / restore"]
    I --> J["Schema, data, app, replication checks"]
    J --> K{"Acceptance criteria đạt?"}
    K -->|"Không"| L["Giữ incident mở và escalate"]
    K -->|"Có"| M["Sign-off và đóng change"]
~~~

Bài học thuộc chương **Xử lý sự cố**, module **Database Engine Relational PostgreSQL**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt sự cố do PostgreSQL upgrade, collation version drift và extension incompatibility.
2. Thu thập cluster identity, server version, package version và upgrade evidence.
3. Nhận diện các triệu chứng thường gặp sau major/minor upgrade.
4. Hiểu collation provider libc và ICU ảnh hưởng tới so sánh text thế nào.
5. Kiểm tra recorded collation version so với actual provider version.
6. Xác định index và object phụ thuộc vào collation đã thay đổi.
7. Lập kế hoạch REINDEX và refresh collation version theo thứ tự an toàn.
8. Phân biệt extension package, shared library và SQL extension version.
9. Kiểm tra extension availability, update paths và dependency.
10. Xử lý lỗi thiếu shared library, undefined symbol và update script failure.
11. Quản lý shared_preload_libraries và yêu cầu restart.
12. Xây dựng quy trình sau pg_upgrade hoặc dump/restore.
13. Xác minh configuration, roles, grants, sequences, replication và CDC.
14. Chọn rollback, forward-fix hoặc restore dựa trên data state.
15. Thiết kế monitoring và acceptance checks sau maintenance.
16. Thu thập evidence và xây dựng runbook có stop conditions.

## 2. Phân loại sự cố sau nâng cấp

Một lỗi xuất hiện ngay sau maintenance không nhất thiết do PostgreSQL core. Có thể là hệ điều hành, extension, application driver, collation provider hoặc cấu hình.

| Nhóm | Thay đổi thường gặp | Triệu chứng |
| --- | --- | --- |
| PostgreSQL major upgrade | Binary và catalog/data format | Startup, catalog, SQL behavior hoặc extension errors |
| PostgreSQL minor update | Bug fixes, binary/package | Crash, behavior change hoặc package mismatch |
| OS/library upgrade | libc, ICU, OpenSSL, timezone data | Collation mismatch, TLS/auth errors |
| Collation update | Sort/equality semantics | Warning, index inconsistency, unique conflicts |
| Extension package update | Shared library/control/SQL scripts | Missing library, symbol error, update path missing |
| Extension SQL update | Extension catalog objects | Missing function/type/operator hoặc dependency error |
| Configuration migration | Parameter renamed/removed | Startup warning/error, setting ignored |
| Application upgrade | Driver/ORM/query behavior | Prepared statement, type mapping, query regression |
| Replication/CDC | Protocol, schema, slot state | Subscriber/connector lag hoặc apply failure |

Không kết luận nguyên nhân chỉ từ thời điểm lỗi. So sánh maintenance timeline, server logs, package changes, migration records và application rollout.

## 3. Quy tắc đầu tiên: contain và bảo toàn evidence

Khi phát hiện sự cố:

1. Dừng rollout tiếp theo và các thay đổi không liên quan.
2. Xác định có cần giữ traffic ở phiên bản tương thích hay chuyển sang maintenance mode.
3. Không chạy REINDEX, ALTER EXTENSION, REFRESH COLLATION VERSION hoặc DROP EXTENSION theo phản xạ.
4. Lưu PostgreSQL logs, OS/package logs, upgrade logs và application errors.
5. Ghi cluster/database identity, server version và extension versions.
6. Xác định backup, WAL archive và PITR readiness.
7. Xác định primary/standby, replication slots và CDC consumers.
8. Ghi rõ thời điểm lỗi đầu tiên và thay đổi ngay trước đó.

Nếu database đang hoạt động nhưng trả kết quả sai hoặc có dấu hiệu corruption, ưu tiên bảo toàn trạng thái và escalation. Không chạy hàng loạt lệnh sửa khi chưa hiểu blast radius.

## 4. Xác minh đúng cluster và PostgreSQL version

Trước khi điều tra, xác nhận session đang kết nối đúng target:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    version() AS server_version,
    current_setting('server_version_num') AS server_version_num,
    pg_is_in_recovery() AS is_standby,
    pg_postmaster_start_time() AS server_started_at;
~~~

Kiểm tra cluster control information ở host bằng binary phù hợp:

~~~bash
pg_controldata /path/to/data-directory
~~~

pg_controldata có thể cung cấp system identifier, catalog version, cluster state, checkpoint và checksum metadata. Đọc đúng data directory và đúng tool version.

Ghi lại:

- Cluster/system identifier.
- PostgreSQL major/minor version trước và sau.
- Database name và role.
- Primary/standby state.
- Server start time.
- Data directory và package source.
- Upgrade method.
- Release/change ID.

Không dựa vào hostname hoặc database name đơn lẻ để nhận diện cluster.

## 5. Phân biệt major upgrade và minor update

**Minor update** thường giữ nguyên data directory format trong cùng major release và tập trung vào bug/security fixes. Tuy nhiên, package extension và thư viện hệ điều hành có thể thay đổi cùng đợt maintenance.

**Major upgrade** thay đổi major version và cần quy trình nâng cấp data/catalog, thường bằng pg_upgrade hoặc dump/restore/logical migration.

Không dùng binary major version mới để mở trực tiếp data directory của major version cũ. Phải sử dụng quy trình upgrade được PostgreSQL hỗ trợ.

### pg_upgrade

pg_upgrade chuyển cluster giữa các major versions bằng cách tạo cluster mới tương thích với binary/catalog mới và chuyển dữ liệu theo cơ chế được hỗ trợ.

Trước khi chạy:

- Đọc release notes cho cả source và target major versions.
- Kiểm tra operating system, architecture và binary paths.
- Cài extension packages tương thích target version.
- Chạy pg_upgrade --check.
- Kiểm tra tablespaces, locale, encoding và shared libraries.
- Xác nhận backup/restore path.
- Kiểm tra disk space và downtime plan.
- Lưu output/log của upgrade.

Ví dụ kiểm tra trước:

~~~bash
pg_upgrade --check \
  --old-datadir=/path/to/old/data \
  --new-datadir=/path/to/new/data \
  --old-bindir=/path/to/old/bin \
  --new-bindir=/path/to/new/bin
~~~

Đây là cú pháp minh họa; tùy chọn và cách gọi phụ thuộc platform/version. Dùng pg_upgrade --help của binary target.

### Copy mode và link mode

- **Copy mode:** dữ liệu được copy; tốn disk/time hơn nhưng source cluster có thể được giữ nguyên để phục hồi theo plan.
- **Link mode:** dùng hard links để giảm thời gian/disk. Sau khi cluster mới được khởi động và thay đổi shared files, không thể coi cluster cũ là một bản rollback độc lập an toàn.

Không dựa vào link-mode source directory như backup sau khi upgrade đã bắt đầu ghi vào cluster mới. Phải có backup/snapshot độc lập.

## 6. Công việc sau pg_upgrade

Sau khi pg_upgrade hoàn tất, chưa nên mở toàn bộ traffic ngay. Các bước thường cần xem xét:

1. Xem toàn bộ upgrade logs và generated scripts.
2. Xác minh target cluster identity và version.
3. Kiểm tra configuration files đã được merge đúng.
4. Cài/kiểm tra extension binaries cho target major version.
5. Cập nhật SQL extension versions theo update paths.
6. Xử lý collation version mismatch và rebuild dependent objects.
7. Chạy ANALYZE để tạo optimizer statistics mới.
8. Kiểm tra roles, ownership, grants và authentication.
9. Kiểm tra sequences/identity values.
10. Kiểm tra replication, logical slots, subscriptions và CDC.
11. Chạy application smoke tests.
12. Chạy post-upgrade data/schema checks.
13. Mở traffic theo staged rollout.

pg_upgrade không thay thế toàn bộ operational checklist. Đặc biệt, optimizer statistics có thể cần được thu thập lại; dùng analyze scripts được tạo bởi upgrade workflow nếu có và review trước khi chạy.

## 7. Kiểm tra configuration sau upgrade

Một số parameters có thể bị đổi tên, deprecated hoặc bị loại bỏ giữa major versions. Configuration cũ có thể tạo warnings, bị bỏ qua hoặc ngăn server start.

Kiểm tra:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
ORDER BY name;
~~~

Kiểm tra các settings quan trọng theo workload:

- shared_buffers.
- work_mem.
- maintenance_work_mem.
- max_connections.
- wal_level.
- max_wal_senders.
- max_replication_slots.
- shared_preload_libraries.
- archive_mode và archive_command.
- ssl, authentication và logging settings.
- autovacuum parameters.
- locale/collation-related settings.

Đối chiếu file cấu hình với giá trị server thực sự đang sử dụng. Giá trị trong file không chứng minh server đã load thành công.

Kiểm tra warnings khi startup và cấu hình được include từ các file khác. Không copy nguyên postgresql.conf cũ vào target mà không đối chiếu release notes.

## 8. Collation là gì?

Collation định nghĩa quy tắc so sánh và sắp xếp chuỗi theo locale/provider. Nó ảnh hưởng tới các thao tác như ORDER BY, comparison, equality semantics của một số collation, unique indexes và các biểu thức dựa trên text.

PostgreSQL có thể sử dụng provider như:

- **libc:** dựa trên locale support của operating system.
- **ICU:** dựa trên International Components for Unicode nếu build/server hỗ trợ.
- **builtin:** các collation built-in có behavior riêng theo version.

Collation không chỉ là cách hiển thị chữ. Nếu provider thay đổi cách so sánh hai chuỗi hoặc thứ tự sort, các index được tạo theo quy tắc cũ có thể không còn phản ánh quy tắc hiện tại.

Ví dụ, một locale có thể xử lý khác nhau về:

- Chữ hoa/chữ thường.
- Dấu phụ/diacritics.
- Thứ tự ký tự có dấu.
- Unicode normalization hoặc equivalence.
- Ngôn ngữ có quy tắc sort đặc thù.

Không tự suy ra kết quả cụ thể từ tên locale; test với dữ liệu và provider thực tế.

## 9. Collation version mismatch xảy ra khi nào?

PostgreSQL lưu recorded version của collation provider tại thời điểm database/collation được tạo hoặc refresh. Nếu libc/ICU được nâng cấp, actual provider version có thể khác recorded version.

Khi đó PostgreSQL có thể phát warning về collation version mismatch. Đây là dấu hiệu rằng quy tắc sort/equality có thể đã thay đổi trong khi indexes hoặc objects phụ thuộc vẫn được tạo theo quy tắc cũ.

Ví dụ nguyên nhân:

- OS package cập nhật glibc.
- ICU package được nâng.
- Container image mới dùng thư viện khác.
- Cluster được restore sang host có locale provider version khác.
- Database được migrate sang distribution khác.
- Collation definition thay đổi giữa môi trường.

Một mismatch không có nghĩa mọi table đã hỏng. Cần xác định collation nào thay đổi và object nào phụ thuộc.

## 10. Kiểm tra collation version của database

Đối với default collation của database:

~~~sql
SELECT
    d.datname,
    d.datcollate,
    d.datctype,
    d.datcollversion AS recorded_version,
    pg_database_collation_actual_version(d.oid) AS actual_version
FROM pg_database AS d
WHERE d.datname = current_database();
~~~

Nếu recorded_version khác actual_version, database default collation có thể đã thay đổi.

Đối chiếu tất cả databases mà maintenance ảnh hưởng, không chỉ database đang kết nối. Cần kết nối hoặc dùng catalog visibility phù hợp để xác minh từng database.

### Kiểm tra collation objects

~~~sql
SELECT
    n.nspname AS schema_name,
    c.collname,
    c.collprovider,
    c.collisdeterministic,
    c.collversion AS recorded_version,
    pg_collation_actual_version(c.oid) AS actual_version
FROM pg_collation AS c
JOIN pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid)
ORDER BY n.nspname, c.collname;
~~~

Các cột và provider codes có thể khác theo PostgreSQL version. Xem catalog của server hiện tại trước khi tự động hóa.

Nếu actual version là NULL, provider có thể không cung cấp version string theo semantics của version/build đó. Không coi NULL là bằng chứng mismatch hoặc healthy nếu chưa hiểu provider.

## 11. Tìm index phụ thuộc collation

Indexes trên text/varchar/char hoặc expression có collation có thể cần rebuild sau provider update. Những index có key expression như lower(name), sort key hoặc collation-specific operator class cũng cần được xem xét.

Có thể bắt đầu bằng inventory:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Review definitions để xác định collatable keys, expressions và predicates. Catalog dependencies có thể hỗ trợ khoanh vùng, nhưng không nên dựa vào một query đơn giản nếu index dùng expression hoặc collation được kế thừa từ type/operator.

### Lưu ý về unique indexes

Sau khi collation thay đổi, hai giá trị text trước đây được coi là khác nhau có thể được coi là bằng nhau theo provider mới. Khi rebuild unique index, PostgreSQL có thể báo duplicate key.

Đây là vấn đề dữ liệu và semantics, không phải chỉ là lỗi index. Cần:

1. Lấy các duplicate candidates theo collation mới.
2. Xác định business rule chọn/merge giá trị.
3. Sửa dữ liệu theo quy trình nghiệp vụ.
4. Xác minh uniqueness.
5. Rebuild index.
6. Chỉ tiếp tục khi constraint semantics được bảo đảm.

Không drop unique constraint để làm REINDEX chạy qua nếu chưa có quyết định bảo vệ uniqueness.

## 12. Vì sao phải REINDEX sau collation update?

B-tree index lưu cấu trúc sắp xếp theo comparison semantics lúc index được tạo. Khi collation provider đổi, thứ tự hoặc equality semantics có thể thay đổi. Index cũ có thể không còn phù hợp với cách PostgreSQL so sánh hiện tại.

Rebuild index giúp tạo lại thứ tự index theo provider mới.

Các object thường cần đánh giá:

- B-tree indexes có text keys.
- Indexes trên expressions có collation.
- Unique indexes dùng collation.
- Indexes trên columns/domain có collatable types.
- Partitioned indexes và indexes trên từng partition.
- Các object khác có persisted semantics phụ thuộc collation.

Không mặc định mọi index trong cluster đều bị ảnh hưởng. Xác định scope theo database, collation và index definition.

## 13. Thứ tự an toàn: rebuild rồi mới refresh version

Một điểm quan trọng: lệnh REFRESH COLLATION VERSION chỉ cập nhật metadata version được ghi nhận. Nó không rebuild index và không sửa thứ tự key đã lưu.

Quy trình tổng quát:

1. Xác định provider/version mismatch.
2. Xác định database/collation bị ảnh hưởng.
3. Inventory indexes và dependent objects.
4. Đánh giá duplicate keys, lock, disk và runtime.
5. Rebuild các indexes/object bị ảnh hưởng.
6. Xác minh index valid và application behavior.
7. Chạy REFRESH COLLATION VERSION cho đúng database/collation.
8. Kiểm tra lại recorded/actual version.
9. Lưu evidence và đóng change.

Không refresh version trước khi rebuild dependent objects; làm vậy có thể xóa warning trong khi index vẫn dùng thứ tự cũ.

### Refresh database default collation

Sau khi các dependent objects đã được rebuild:

~~~sql
ALTER DATABASE sales REFRESH COLLATION VERSION;
~~~

Lệnh phải được thực hiện theo quyền và connection policy phù hợp. Cú pháp này cập nhật recorded version của database default collation.

### Refresh một named collation

~~~sql
ALTER COLLATION public.customer_sort REFRESH VERSION;
~~~

Lệnh này cập nhật recorded version cho collation object cụ thể. Nó không rebuild indexes phụ thuộc vào collation đó.

Nếu nhiều database dùng cùng named collation definition được tạo riêng trong từng database, phải xử lý từng database.

## 14. REINDEX theo phạm vi

### Một index

~~~sql
REINDEX INDEX public.orders_customer_name_idx;
~~~

Lệnh này rebuild một index và có thể cần lock ảnh hưởng concurrent access.

### Một table

~~~sql
REINDEX TABLE public.orders;
~~~

Rebuild các indexes trên table theo phạm vi command và version.

### Một schema/database

~~~sql
REINDEX SCHEMA public;
~~~

~~~sql
REINDEX DATABASE sales;
~~~

Các lệnh phạm vi rộng có thể tốn I/O, disk và lock. Dùng khi scope thực sự yêu cầu; không chạy trên toàn database chỉ vì một collation object mismatch.

### Concurrent reindex

Với index phù hợp, có thể cân nhắc:

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_customer_name_idx;
~~~

CONCURRENTLY có hạn chế riêng, không chạy trong transaction block thông thường và có thể tạo index invalid nếu thất bại. Nó giảm thời gian chặn writes nhưng thường tốn thời gian/I/O hơn và cần thêm disk.

Kiểm tra tài liệu đúng version và plan cho invalid index recovery. Không chạy concurrent rebuild hàng loạt mà không giới hạn concurrency.

## 15. Kiểm tra index sau REINDEX

Kiểm tra index validity:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
WHERE i.indrelid = 'public.orders'::regclass
ORDER BY i.indexrelid::regclass::text;
~~~

Nếu dùng REINDEX CONCURRENTLY và operation thất bại, kiểm tra index invalid trước khi retry. Không drop index chỉ dựa trên tên; xác minh definition, dependency và owner.

Chạy amcheck nếu phù hợp với loại index và operational window. Sau đó chạy query tests dùng các collation-sensitive predicates/orderings.

## 16. Test collation behavior bằng dữ liệu đại diện

Trước/sau provider change, tạo test cases đại diện cho locale và business data:

~~~sql
SELECT
    value,
    value COLLATE "en-x-icu" AS test_value
FROM (
    VALUES
        ('a'),
        ('A'),
        ('á'),
        ('ä'),
        ('ae'),
        ('Å'),
        ('ß'),
        ('ss')
) AS samples(value)
ORDER BY test_value;
~~~

Tên collation chỉ là ví dụ; phải dùng collation có thật trong database. Kết quả phụ thuộc provider, locale và options.

Có thể so sánh equality/order behavior:

~~~sql
SELECT
    'a' COLLATE "some_collation"
        = 'A' COLLATE "some_collation" AS equal_under_collation;
~~~

Không dùng test strings đơn lẻ để đại diện toàn bộ language rules. Xác định các cases quan trọng với business: tên khách hàng, địa chỉ, mã tìm kiếm, sort keys, uniqueness và case/accent sensitivity.

## 17. Collation và database creation

Default collation/ctype của database được xác định khi tạo database, dựa trên template và provider/options được chọn.

Kiểm tra:

~~~sql
SELECT
    datname,
    datlocprovider,
    datcollate,
    datctype,
    daticulocale,
    datcollversion
FROM pg_database
ORDER BY datname;
~~~

Các cột như datlocprovider/daticulocale có thể không tồn tại ở PostgreSQL versions cũ hơn. Dùng query phù hợp catalog version.

Không thể coi thay đổi default locale như một thao tác config đơn giản. Thay đổi collation provider/options có thể cần tạo database mới và migrate dữ liệu/indexes theo quy trình được hỗ trợ.

## 18. Extension có những lớp version nào?

Một PostgreSQL extension thường có ba lớp cần quản lý:

1. **OS package/shared library:** file binary, control file và SQL scripts được cài trên server.
2. **SQL extension version:** version được ghi trong pg_extension của từng database.
3. **Server compatibility:** binary extension được build cho PostgreSQL major version và ABI tương ứng.

Cập nhật một lớp không tự động cập nhật các lớp còn lại.

Ví dụ, package extension cho PostgreSQL 17 có thể không dùng được với PostgreSQL 16. Cài package mới ở host cũng không nhất thiết cập nhật SQL objects trong database. Ngược lại, ALTER EXTENSION UPDATE không thể tạo shared library bị thiếu.

## 19. Kiểm tra extension inventory

Trong từng database:

~~~sql
SELECT
    e.extname,
    e.extversion AS installed_version,
    n.nspname AS extension_schema,
    pg_get_userbyid(e.extowner) AS extension_owner
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Kiểm tra extension server có sẵn:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

Kiểm tra các version được package cung cấp:

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

Thực hiện inventory trên tất cả databases cần thiết. Extension SQL objects được cài theo database, dù shared library nằm ở cấp server.

## 20. Kiểm tra extension update paths

PostgreSQL có thể cung cấp các đường nâng cấp SQL giữa extension versions.

~~~sql
SELECT *
FROM pg_extension_update_paths('postgis');
~~~

Thay postgis bằng extension thực tế. Function trả các source/target versions và update path mà server package hiện có hỗ trợ.

Nếu không có đường trực tiếp từ installed version tới target version, có thể cần nâng qua các version trung gian hoặc cài package cung cấp script còn thiếu.

Không tự sửa pg_extension.extversion. Metadata version phải được cập nhật bằng ALTER EXTENSION và scripts chính thức.

## 21. Cập nhật SQL extension version

Ví dụ:

~~~sql
ALTER EXTENSION hstore UPDATE;
~~~

Hoặc chỉ định target version:

~~~sql
ALTER EXTENSION hstore UPDATE TO '1.8';
~~~

Version ví dụ chỉ minh họa. Chọn target từ pg_available_extension_versions và update path thực tế.

Lưu ý:

- ALTER EXTENSION UPDATE chạy trong database hiện tại.
- Cần thực hiện cho từng database có extension.
- Update script có thể tạo/đổi function, type, operator, view hoặc catalog metadata.
- Dependency với extension khác có thể yêu cầu thứ tự update.
- Extension-specific upgrade guide có thể yêu cầu thao tác bổ sung.
- Một số extension cần restart hoặc background worker configuration.

CREATE EXTENSION IF NOT EXISTS không nâng cấp extension đã cài. Nó chỉ tránh lỗi nếu extension đã tồn tại.

## 22. Lỗi thiếu extension control file hoặc SQL script

Triệu chứng có thể gồm:

- extension control file không tồn tại.
- Không tìm thấy extension version.
- Không tìm thấy update script.
- CREATE EXTENSION báo extension unavailable.
- ALTER EXTENSION báo không có update path.

Nguyên nhân thường là:

- OS package chưa được cài.
- Package chỉ được cài cho PostgreSQL major version cũ.
- Package repository không có target extension version.
- File control/script không nằm trong extension directory mà server dùng.
- Container image khác với image trước upgrade.

Cách xử lý:

1. Xác nhận PostgreSQL binary/package version.
2. Xác định extension package tương ứng target major.
3. Kiểm tra package manager inventory.
4. Kiểm tra extension control/SQL files theo package policy.
5. Cài đúng package qua change process.
6. Xác minh pg_available_extensions.
7. Kiểm tra update path.
8. Chạy SQL extension update theo plan.

Không copy thủ công một vài file extension từ host khác vào thư mục lib/share của PostgreSQL. Package phải phù hợp ABI, dependencies và server version.

## 23. Lỗi không nạp được shared library

Các lỗi thường gặp:

- could not access file "$libdir/extension_name".
- undefined symbol.
- symbol lookup error.
- incompatible library version.
- cannot load library.
- shared object dependency not found.

Nguyên nhân:

- Shared library chưa được cài.
- Binary được build cho PostgreSQL major version khác.
- Package bị thiếu dependency.
- Library path không đúng.
- Server chưa được restart sau package/config update.
- Architecture hoặc OS mismatch.

Quy trình:

1. Lưu nguyên server log/error.
2. Xác nhận extension name và library path.
3. Kiểm tra server major version.
4. Kiểm tra package build version/architecture.
5. Kiểm tra shared library dependencies ở OS layer.
6. Cài package tương thích.
7. Restart nếu cần theo extension docs.
8. Xác minh extension functions/load behavior.

Không dùng ALTER EXTENSION UPDATE để sửa lỗi binary load nếu package library còn thiếu.

## 24. shared_preload_libraries và restart

Một số extension yêu cầu được load lúc server startup thông qua shared_preload_libraries. Ví dụ thường gặp là pg_stat_statements hoặc một số extension có background workers.

Kiểm tra:

~~~sql
SHOW shared_preload_libraries;
~~~

Và:

~~~sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name = 'shared_preload_libraries';
~~~

Thêm extension vào shared_preload_libraries yêu cầu restart server. CREATE EXTENSION trong database là bước khác; thường vẫn cần tạo SQL objects sau khi library được load.

Không ghi đè danh sách preload hiện có khi thêm extension mới. Giữ các libraries đang dùng và xác minh thứ tự/compatibility theo tài liệu extension.

Nếu server không start sau khi thêm library, xem startup logs và khôi phục cấu hình trước đó theo change plan.

## 25. Extension dependency và update order

Một extension có thể phụ thuộc extension khác, types/functions hoặc shared libraries. Update sai thứ tự có thể làm script thất bại.

Kiểm tra requires metadata:

~~~sql
SELECT
    name,
    version,
    requires
FROM pg_available_extension_versions
WHERE name IN ('extension_a', 'extension_b')
ORDER BY name, version;
~~~

Tên extension chỉ là placeholder.

Trước update:

- Xem extension dependency graph.
- Đọc release notes.
- Xác định target versions.
- Kiểm tra update path.
- Xem objects bên ngoài extension phụ thuộc vào function/type/operator.
- Xác định update script transactional behavior.
- Backup và test trên clone.

Không DROP EXTENSION ... CASCADE để giải quyết dependency errors nếu chưa xác định toàn bộ objects bị xóa.

## 26. Extension update thất bại giữa chừng

Nhiều extension update scripts được chạy trong transaction, nhưng không nên giả định mọi extension hoặc mọi thao tác đều atomic trong mọi version/tool.

Nếu update fail:

1. Lưu full error và extension version hiện tại.
2. Kiểm tra transaction/session state.
3. Xác minh pg_extension.extversion.
4. Kiểm tra functions/types/operators đã thay đổi tới đâu.
5. Đọc update SQL script và extension release notes.
6. Kiểm tra dependencies và package version.
7. Xác định retry có an toàn không.
8. Chọn update lại, repair theo vendor guide hoặc restore.

Không chỉnh trực tiếp catalog pg_extension để làm version hiển thị như target. Nếu SQL objects chưa được nâng đúng, metadata có thể che giấu trạng thái không nhất quán.

## 27. Extension có thể thay đổi behavior mà không đổi SQL API

Một extension update có thể giữ nguyên function signatures nhưng thay đổi:

- Algorithm.
- Planner integration.
- Operator semantics.
- Background worker behavior.
- Storage format hoặc internal metadata.
- Performance profile.
- Memory/resource use.
- Compatibility với server version.

Do đó, kiểm tra chỉ bằng cách gọi function thành công là chưa đủ. Chạy extension-specific regression tests và application queries quan trọng.

Với extension quản lý index/data types hoặc background jobs, xác minh index/operator compatibility và worker health.

## 28. Extension upgrade trong major PostgreSQL upgrade

Trước major upgrade:

1. Xác định mọi extension trong từng database.
2. Xác minh target PostgreSQL version hỗ trợ extension.
3. Cài package/shared libraries cho target major.
4. Kiểm tra extension update paths.
5. Đọc upgrade notes của extension.
6. Xác định extension nào cần preload.
7. Test pg_upgrade --check hoặc dump/restore trên clone.
8. Lập thứ tự SQL extension updates sau khi target cluster sẵn sàng.

Sau major upgrade:

- Xác minh extension package có sẵn.
- Kiểm tra pg_extension version.
- Chạy update scripts theo thứ tự.
- Restart nếu preload/config yêu cầu.
- Chạy extension-specific checks.
- Kiểm tra application queries và background workers.

Không cho rằng pg_upgrade tự động cập nhật mọi extension SQL version hoặc cài đúng shared library mới.

## 29. Sự cố sau OS/container image upgrade

Một image mới có thể đổi:

- glibc/libc.
- ICU.
- OpenSSL.
- locale data.
- timezone database.
- shared library dependencies.
- PostgreSQL/extension packages.

Nếu server chạy trong container, image digest là evidence quan trọng. Ghi image trước/sau, package versions và runtime architecture.

Với libc/ICU, kiểm tra collation mismatch. Với OpenSSL/auth, kiểm tra TLS handshakes, certificate chain và authentication methods. Với extension binaries, kiểm tra dynamic library dependencies.

Không sửa image production bằng cách cài package thủ công không có trong build pipeline. Tạo image mới reproducible, test và promote theo release process.

## 30. Application errors sau upgrade

Application có thể gặp:

- undefined function/operator.
- type conversion errors.
- prepared statement errors.
- ORM migration mismatch.
- changed query plans.
- collation-sensitive ordering differences.
- authentication/TLS failures.
- driver incompatibility.
- extension function behavior changes.

Thu thập:

- Application build/driver version.
- SQLSTATE và full server error.
- Query ID/normalized query.
- Database version.
- Extension version.
- Search_path và role.
- Prepared statement/session behavior.
- Query plan trước/sau nếu có.

Không kết luận lỗi application chỉ vì server upgrade đã hoàn tất. Cần tái hiện với cùng role, settings và parameter values.

## 31. Kiểm tra collation trong nhiều databases

Collation metadata và extension SQL objects cần được kiểm tra theo database scope.

Tạo inventory database:

~~~sql
SELECT
    datname,
    datlocprovider,
    datcollate,
    datctype,
    datcollversion,
    pg_database_collation_actual_version(oid) AS actual_version
FROM pg_database
WHERE datallowconn
ORDER BY datname;
~~~

Các columns về locale provider phụ thuộc major version. Nếu query không chạy trên server cũ, điều chỉnh theo catalog version.

Với từng database:

- Xác định default collation.
- Liệt kê named collations bị mismatch.
- Liệt kê dependent indexes.
- Ghi nhận schema/table/index owner.
- Xác định app/consumer dùng collation đó.
- Lập rebuild plan riêng.

Không refresh database A rồi giả định database B đã được xử lý.

## 32. Tìm collation dependencies trong catalogs

Có thể sử dụng pg_depend để hỗ trợ xác định objects phụ thuộc collation. Ví dụ query khảo sát:

~~~sql
SELECT DISTINCT
    idx.oid::regclass AS index_name,
    tbl.oid::regclass AS table_name,
    coll.oid::regcollation AS collation_name
FROM pg_depend AS d
JOIN pg_class AS idx
    ON d.classid = 'pg_class'::regclass
   AND d.objid = idx.oid
JOIN pg_index AS i
    ON i.indexrelid = idx.oid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_collation AS coll
    ON d.refclassid = 'pg_collation'::regclass
   AND d.refobjid = coll.oid
WHERE idx.relkind = 'i'
ORDER BY index_name::text, collation_name::text;
~~~

Dùng query này như một nguồn inventory và xác nhận kết quả bằng pg_get_indexdef, expression/predicate và PostgreSQL catalog của version đang chạy. Không coi nó là danh sách hoàn chỉnh duy nhất cho mọi loại dependency hoặc mọi version.

## 33. Unique index conflict sau collation change

Nếu REINDEX unique index báo duplicate key, collation mới có thể làm hai giá trị trước đây phân biệt trở thành equal theo comparison semantics.

Ví dụ các strings có khác biệt case/diacritics/locale-specific equivalence. Không giả định một cặp cụ thể luôn equal; behavior phụ thuộc collation.

Recovery:

1. Giữ nguyên dữ liệu và error output.
2. Xác định unique index và collation.
3. Tái hiện comparison bằng collation mới.
4. Liệt kê duplicate groups theo đúng expression/key.
5. Làm việc với data owner để quyết định merge/rename/retain.
6. Kiểm tra downstream references.
7. Sửa data trong change được duyệt.
8. Rebuild unique index.
9. Xác minh uniqueness và application behavior.

Không drop unique index trong thời gian dài nếu application dựa vào nó để bảo vệ business invariant.

## 34. Collation warning không tự biến mất bằng refresh

Lệnh REFRESH VERSION cập nhật recorded version trong catalog. Nó không scan data, không rebuild index và không chứng minh object đã được sửa.

Một quy trình sai là:

1. Nhận warning.
2. Chạy ALTER DATABASE ... REFRESH COLLATION VERSION.
3. Warning biến mất.
4. Bỏ qua indexes cũ.

Kết quả là metadata không còn cảnh báo nhưng index có thể vẫn chứa ordering theo provider cũ.

Quy trình đúng là xác định/rebuild dependent objects trước, xác minh sau đó mới refresh metadata.

## 35. Kiểm tra index sau collation rebuild

Ngoài pg_index validity, kiểm tra:

- Index definition khớp expected.
- Unique constraints vẫn được enforce.
- Partitioned index và child indexes valid.
- Query plan dùng index đúng.
- ORDER BY và comparison trả behavior đúng.
- Application search/sort tests đạt.
- Amcheck không phát hiện lỗi với B-tree indexes được chọn.
- Không có invalid index còn sót lại.

Nếu reindex chạy trên table partitioned, kiểm tra cả parent index và từng partition index theo semantics của version.

## 36. Sau upgrade: ANALYZE và query plan

Optimizer statistics có thể cần được thu thập lại sau major upgrade. Sau khi database ổn định và theo workload plan, chạy ANALYZE hoặc scripts do pg_upgrade tạo.

~~~sql
ANALYZE;
~~~

Hoặc với table cụ thể:

~~~sql
ANALYZE public.orders;
~~~

Với database lớn, dùng vacuumdb --all --analyze-in-stages theo tài liệu/version và giới hạn tài nguyên phù hợp.

Kiểm tra query quan trọng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

EXPLAIN ANALYZE thực thi statement. Dùng query đại diện, tránh side effects và kiểm soát tải.

So sánh actual rows, estimated rows, buffers, sort/hash spills, execution time và plan shape. Không ép planner settings chỉ để khôi phục một plan cũ khi chưa hiểu nguyên nhân.

## 37. Sau upgrade: sequences và identity

Với dump/restore, bulk load hoặc custom migration, sequence state có thể cần xác minh. Native logical replication cũng không mặc định đồng bộ sequence state như row changes.

Tìm sequence gắn với cột:

~~~sql
SELECT
    pg_get_serial_sequence('public.orders', 'order_id') AS sequence_name;
~~~

Sau khi xác định sequence cụ thể, so sánh sequence state với dữ liệu và increment policy. Không chạy setval trên toàn bộ sequences bằng một script chung mà chưa kiểm tra concurrent writes, cache, cycling và ownership.

Khi cutover primary/sink, đồng bộ sequence là một bước riêng có verification.

## 38. Sau upgrade: roles, grants và authentication

Xác minh:

- Roles và memberships.
- LOGIN/NOLOGIN và role attributes.
- Ownership của databases/schemas/tables.
- Grants và default privileges.
- RLS policies.
- SECURITY DEFINER functions.
- pg_hba.conf.
- TLS/certificate settings.
- Password/SCRAM authentication.
- Service account credentials.

Ví dụ kiểm tra role attributes:

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolbypassrls
FROM pg_roles
ORDER BY rolname;
~~~

Không chỉ test kết nối bằng superuser. Chạy smoke tests bằng đúng application/connector roles để phát hiện permission regressions.

## 39. Sau upgrade: replication, subscriptions và CDC

Major upgrade hoặc OS change có thể ảnh hưởng replication topology và connectors.

Kiểm tra physical replication:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Kiểm tra logical slots:

~~~sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Kiểm tra logical subscriptions:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Các columns thay đổi theo version. Kiểm tra slot ownership, connector version, schema history, publication scope và subscriber schema.

Không drop/recreate slots chỉ để dọn inventory. Slot có thể giữ WAL cần cho CDC; nếu mất slot, cần bootstrap/reconcile.

## 40. Kiểm tra extension và collation trên standby

Physical standby nhận data files/catalog changes qua WAL, nhưng binary packages và OS libraries phải được cài tương thích trên từng node. Khi failover, standby cần có extension shared libraries và configuration phù hợp để tiếp tục phục vụ workload.

Với logical subscribers, DDL và extension packages thường phải triển khai riêng. Đảm bảo subscriber schema/extension state tương thích trước khi publisher phát các row changes phụ thuộc schema mới.

Kiểm tra cả failover candidate, không chỉ primary hiện tại.

## 41. Monitoring sau upgrade

Dashboard nên theo dõi:

| Nhóm | Tín hiệu |
| --- | --- |
| Server | Startup/restart errors, uptime, crash recovery |
| Query | Error rate, p95/p99 latency, top query deltas |
| Planner | Plan changes, rows estimate, buffer/temp activity |
| Storage | Disk free, WAL growth, I/O latency |
| Locks | Blocked sessions, deadlocks, lock wait duration |
| Maintenance | Autovacuum, analyze progress, dead tuples |
| Collation | Recorded/actual version mismatch |
| Extensions | Installed/available version, worker health, library errors |
| Replication | Replay lag, inactive slots, retained WAL |
| Application | Smoke tests, connection failures, business errors |

Theo dõi baseline trước và sau upgrade. Một số counter reset khi restart, nên lưu snapshot trước maintenance và đánh dấu thời điểm reset.

## 42. Release gates sau upgrade

Định nghĩa acceptance criteria trước khi maintenance:

- Target server version đúng.
- Cluster identity đúng.
- Server startup sạch, không có fatal extension/config errors.
- Extension packages và SQL versions tương thích.
- Collation mismatches đã được xử lý hoặc có exception rõ.
- Dependent indexes đã được rebuild.
- Indexes/constraints ở trạng thái expected.
- ANALYZE hoàn tất theo kế hoạch.
- Application smoke tests đạt.
- Roles/grants/authentication đạt.
- Replication/CDC healthy.
- Backup/PITR path được xác nhận.
- Query latency/error rate trong ngưỡng.
- Data reconciliation đạt.

Nếu một gate fail, giữ change mở và chọn recovery path. Không đánh dấu maintenance thành công chỉ vì server process đang running.

## 43. Rollback hay forward-fix?

Sau major upgrade, rollback không giống đổi application binary về version trước.

| Tình huống | Hướng xử lý |
| --- | --- |
| Upgrade chưa start cluster mới và source còn nguyên | Có thể hủy theo pg_upgrade/maintenance procedure |
| Copy-mode upgrade, cluster mới chưa nhận writes | Có thể quay về source theo plan đã test |
| Link-mode cluster mới đã start | Không coi source directory là rollback độc lập |
| Extension package thiếu nhưng data state ổn | Cài đúng package/restore config theo change |
| Extension SQL update lỗi | Kiểm tra transaction/version/dependencies; repair hoặc restore |
| Collation mismatch, indexes chưa rebuild | Rebuild dependent objects rồi refresh metadata |
| Unique index rebuild conflict | Resolve data semantics trước khi rebuild |
| New cluster đã nhận writes | Rollback cần reverse-sync/reconcile writes |
| Data corruption hoặc mất dữ liệu | Backup/PITR/incident recovery theo RPO/RTO |

Không chạy binary cũ trên data directory đã được nâng cấp. Không chuyển traffic về cluster cũ nếu cluster đó không nhận được các writes mới.

## 44. Backup, PITR và recovery readiness

Trước upgrade hoặc thay đổi collation/extension có rủi ro:

- Có base backup/managed snapshot.
- WAL archive liên tục và được kiểm tra.
- Restore procedure được ghi rõ.
- Encryption keys/credentials có sẵn.
- Restore test gần đây.
- RPO/RTO được xác nhận.
- Snapshot của config/package inventory.
- Snapshot của extension versions và collation versions.
- Plan cho writes phát sinh sau cutover.

Backup trước upgrade là baseline recovery, nhưng nếu target đã nhận writes, quay lại backup cũ sẽ mất các writes đó trừ khi có reverse sync/replay strategy.

## 45. Runbook: collation version mismatch

### Contain

- Dừng các schema changes liên quan.
- Ghi database và collation bị mismatch.
- Lưu warning/log và provider package versions.
- Kiểm tra backup và capacity.

### Determine scope

- Kiểm tra database default collation version.
- Liệt kê named collations mismatch.
- Inventory dependent indexes/expressions.
- Xác định unique indexes và duplicate risk.
- Xác định app/consumer sử dụng các indexes đó.

### Recover

- Chọn maintenance window/concurrency.
- Rebuild dependent indexes.
- Xử lý unique conflicts theo business rules.
- Kiểm tra index validity và application sort/equality behavior.
- Chỉ sau đó REFRESH COLLATION VERSION.
- Recheck recorded/actual versions.

### Close

- Lưu index list và REINDEX logs.
- Lưu collation version trước/sau.
- Chạy query/business tests.
- Kiểm tra monitoring và replication.
- Reviewer sign-off.

## 46. Runbook: extension không tương thích sau upgrade

### Contain

- Dừng extension update/deployment tiếp theo.
- Lưu full error và server startup logs.
- Xác định database và extension.
- Xác định package/binary/SQL versions.

### Determine cause

- Kiểm tra pg_extension.
- Kiểm tra pg_available_extensions.
- Kiểm tra pg_available_extension_versions.
- Kiểm tra pg_extension_update_paths.
- Kiểm tra shared_preload_libraries.
- Xác định package build cho PostgreSQL major.
- Xem extension release notes và dependency.

### Recover

- Cài package tương thích.
- Sửa config/preload nếu cần.
- Restart theo maintenance plan.
- Chạy ALTER EXTENSION UPDATE theo path hỗ trợ.
- Xác minh functions/types/operators.
- Chạy extension-specific tests.
- Kiểm tra application và worker health.

### Close

- Lưu package/build versions.
- Lưu SQL extension version trước/sau.
- Xác minh không có missing library/symbol errors.
- Kiểm tra replication/failover nodes.
- Reviewer sign-off.

## 47. Runbook: ứng dụng lỗi sau major upgrade

1. Xác nhận target database và server version.
2. Lấy SQLSTATE, query ID và full error context.
3. Xác định app/driver/ORM version.
4. Kiểm tra extension functions/types/operators liên quan.
5. Kiểm tra collation-sensitive queries.
6. Kiểm tra prepared statements và connection pools.
7. Kiểm tra grants/search_path/RLS.
8. Kiểm tra query plan và statistics.
9. Reproduce bằng application role.
10. Sửa app/config/schema theo forward-compatible plan.
11. Chạy smoke tests và canary.
12. Lưu evidence và theo dõi sau rollout.

Không dùng superuser trong smoke test vì nó có thể che permission errors mà application role gặp phải.

## 48. Evidence và change record

Một evidence package nên có:

- Change/incident ID.
- Cluster/system identifier.
- Source/target PostgreSQL versions.
- OS/container image và package versions.
- Upgrade method và logs.
- Database/extension inventory.
- Collation recorded/actual versions.
- Dependent index list.
- REINDEX/update commands và output.
- Migration/extension ledger state.
- Backup/PITR/WAL archive status.
- Application/driver versions.
- Replication/CDC state.
- Smoke test và reconciliation results.
- Recovery decision, owner và reviewer.

Redact credentials, connection strings, PII và raw data. Evidence cần timestamp/timezone và target identity để có thể tái lập.

## 49. Những sai lầm thường gặp

1. **Chỉ kiểm tra server start thành công**, bỏ qua extension, collation và application compatibility.
2. **Dùng binary major version mới mở data directory cũ**, bỏ qua quy trình upgrade.
3. **Coi source cluster link-mode là backup sau khi target đã chạy**, có thể gây hỏng dữ liệu.
4. **Không lưu upgrade logs/package inventory**, mất bằng chứng để tìm nguyên nhân.
5. **Refresh collation version trước khi rebuild indexes**, làm warning biến mất nhưng index vẫn dùng ordering cũ.
6. **Cho rằng mọi index trong database đều cần rebuild**, không xác định collation dependencies và scope.
7. **Bỏ qua unique conflicts sau collation update**, làm mất business invariant khi cố drop constraint.
8. **Coi REINDEX là cách sửa mọi corruption**, trong khi lỗi có thể nằm ở heap/storage.
9. **Chạy REINDEX DATABASE trong peak hours**, gây I/O/lock impact lớn.
10. **Giả định REINDEX CONCURRENTLY không có rủi ro**, bỏ qua runtime, disk và invalid index recovery.
11. **Cài extension package nhưng không update SQL version**, khiến binary và catalog state lệch.
12. **ALTER EXTENSION UPDATE khi shared library còn thiếu**, không giải quyết lỗi OS package.
13. **Dùng extension binary của major version khác**, gây undefined symbol/ABI errors.
14. **Dùng CREATE EXTENSION IF NOT EXISTS để nâng version**, vì lệnh không update extension đã cài.
15. **Chỉnh pg_extension.extversion trực tiếp**, làm metadata sai với SQL objects.
16. **DROP EXTENSION CASCADE để xử lý update error**, có thể xóa nhiều dependent objects.
17. **Thêm shared_preload_libraries nhưng không restart**, extension không được load.
18. **Ghi đè preload list cũ**, vô tình bỏ extension đang được hệ thống khác dùng.
19. **Chỉ update extension ở một database**, bỏ sót các database khác.
20. **Không kiểm tra extension update paths**, chạy target version không có upgrade script phù hợp.
21. **Không kiểm tra standby/failover node packages**, failover xong extension không load.
22. **Bỏ qua ANALYZE sau major upgrade**, optimizer dùng statistics thiếu hoặc cũ.
23. **Không kiểm tra sequence state**, insert sau cutover có thể gặp duplicate key.
24. **Chỉ test bằng superuser**, bỏ sót lỗi grants/application role.
25. **Không test locale-specific strings**, không phát hiện sort/equality regressions.
26. **Không kiểm tra logical subscriber/CDC schema**, downstream apply bị lỗi sau DDL.
27. **Rollback về cluster cũ sau khi target đã nhận writes**, làm mất dữ liệu mới.
28. **Coi backup file tồn tại là restore readiness**, không có restore test.
29. **Không theo dõi WAL/disk trong REINDEX hoặc backfill**, có thể làm đầy storage.
30. **Đóng incident khi warning biến mất**, chưa xác minh index, application và data correctness.

## 50. Bài tập thực hành có đáp án

### Bài 1. Ba nhóm sự cố chính trong bài là gì?

**Đáp án:** PostgreSQL upgrade, collation version drift và extension incompatibility.

### Bài 2. Major upgrade khác minor update thế nào?

**Đáp án:** Major upgrade thay đổi major version và cần quy trình chuyển đổi data/catalog; minor update thường giữ data format trong cùng major release.

### Bài 3. pg_upgrade --check dùng để làm gì?

**Đáp án:** Kiểm tra các điều kiện upgrade trước khi thực hiện upgrade thật.

### Bài 4. Vì sao không mở data directory cũ bằng binary major mới?

**Đáp án:** Data/catalog format không được đảm bảo tương thích; cần pg_upgrade hoặc dump/restore theo tài liệu.

### Bài 5. Copy mode và link mode khác nhau thế nào?

**Đáp án:** Copy mode tạo bản copy dữ liệu; link mode dùng hard links và source không còn là rollback độc lập an toàn sau khi target được khởi động/ghi.

### Bài 6. Collation là gì?

**Đáp án:** Quy tắc so sánh và sắp xếp chuỗi theo provider/locale.

### Bài 7. Collation provider thường gặp là gì?

**Đáp án:** libc và ICU; một số version còn có builtin provider.

### Bài 8. Collation version mismatch xuất hiện khi nào?

**Đáp án:** Recorded provider version khác actual version, thường sau OS/libc/ICU upgrade hoặc migration sang host khác.

### Bài 9. Vì sao mismatch có thể ảnh hưởng index?

**Đáp án:** Index được xây theo comparison/sort semantics cũ; provider mới có thể tạo thứ tự/equality khác.

### Bài 10. ALTER DATABASE REFRESH COLLATION VERSION làm gì?

**Đáp án:** Cập nhật recorded version của database default collation; không rebuild indexes.

### Bài 11. Khi nào dùng ALTER COLLATION REFRESH VERSION?

**Đáp án:** Sau khi xử lý dependent objects của named collation, để cập nhật recorded version cho collation object đó.

### Bài 12. Thứ tự đúng giữa REINDEX và REFRESH COLLATION VERSION là gì?

**Đáp án:** Xác định/rebuild dependent objects trước, verify, rồi mới refresh recorded version.

### Bài 13. Unique index có thể lỗi gì sau collation update?

**Đáp án:** Hai strings trước đây khác nhau có thể trở thành equal theo collation mới, tạo duplicate-key conflict khi rebuild.

### Bài 14. pg_extension lưu thông tin gì?

**Đáp án:** Extension SQL version, schema và owner trong database hiện tại.

### Bài 15. pg_available_extensions dùng để làm gì?

**Đáp án:** Xem extension packages/control files và default/installed versions mà server nhận diện.

### Bài 16. pg_extension_update_paths giúp gì?

**Đáp án:** Xem các đường SQL upgrade giữa extension versions có sẵn.

### Bài 17. CREATE EXTENSION IF NOT EXISTS có nâng version không?

**Đáp án:** Không. Nó chỉ tránh lỗi nếu extension đã tồn tại.

### Bài 18. ALTER EXTENSION UPDATE chạy ở phạm vi nào?

**Đáp án:** Database hiện tại; cần update từng database có extension.

### Bài 19. Lỗi undefined symbol thường gợi ý điều gì?

**Đáp án:** Shared library/ABI hoặc dependency không tương thích với server/package đang chạy.

### Bài 20. shared_preload_libraries thay đổi thường cần gì?

**Đáp án:** Restart server để load library lúc startup.

### Bài 21. Vì sao cài package không tự cập nhật SQL extension version?

**Đáp án:** Package cung cấp binary/control/scripts; SQL objects trong database cần ALTER EXTENSION UPDATE.

### Bài 22. Vì sao không sửa pg_extension.extversion trực tiếp?

**Đáp án:** Metadata có thể không khớp SQL objects thực tế và làm che trạng thái không nhất quán.

### Bài 23. Sau major upgrade cần làm gì với optimizer statistics?

**Đáp án:** Chạy ANALYZE theo kế hoạch để thu thập statistics cho planner.

### Bài 24. Vì sao phải kiểm tra sequence sau dump/restore/cutover?

**Đáp án:** Sequence state có thể thấp hơn dữ liệu hiện có và gây duplicate key ở lần insert tiếp theo.

### Bài 25. Vì sao smoke test cần dùng application role?

**Đáp án:** Superuser có thể che permission errors mà ứng dụng thực tế gặp phải.

### Bài 26. Native logical replication có tự chuyển DDL không?

**Đáp án:** Không mặc định; schema changes phải được triển khai riêng ở subscriber.

### Bài 27. Vì sao phải kiểm tra extension trên standby?

**Đáp án:** Standby/failover node cần package, library và config tương thích để phục vụ workload sau promotion.

### Bài 28. Khi nào rollback về source cluster không an toàn?

**Đáp án:** Khi target đã nhận writes mới hoặc source link-mode không còn độc lập; cần reverse-sync/reconcile hoặc recovery plan.

### Bài 29. Backup readiness cần gì ngoài file backup?

**Đáp án:** WAL/PITR chain, keys, restore procedure, restore test và RPO/RTO.

### Bài 30. Khi nào đóng incident sau collation/extension upgrade?

**Đáp án:** Khi recorded/actual versions đúng, dependent indexes/objects đã được xử lý, extension binary/SQL versions tương thích, app/data/replication checks đạt và evidence/sign-off đầy đủ.

## 51. Checklist xử lý sự cố sau upgrade

### Containment và inventory

- [ ] Dừng rollout và thay đổi tiếp theo.
- [ ] Xác nhận cluster/database identity.
- [ ] Ghi PostgreSQL source/target versions.
- [ ] Ghi OS/container image và package versions.
- [ ] Lưu upgrade/server/application logs.
- [ ] Xác định primary/standby và replication topology.
- [ ] Xác nhận backup/PITR/WAL archive readiness.
- [ ] Xác định application/driver versions.

### Collation

- [ ] Kiểm tra database recorded/actual collation version.
- [ ] Kiểm tra named collation recorded/actual versions.
- [ ] Xác định provider libc/ICU/builtin.
- [ ] Inventory dependent indexes và expressions.
- [ ] Đánh giá unique conflict risk.
- [ ] Rebuild objects theo scope.
- [ ] Kiểm tra index validity và query behavior.
- [ ] Chỉ sau đó refresh recorded version.
- [ ] Recheck mismatch và lưu evidence.

### Extension

- [ ] Inventory pg_extension từng database.
- [ ] Kiểm tra pg_available_extensions.
- [ ] Kiểm tra extension package cho target major.
- [ ] Kiểm tra pg_extension_update_paths.
- [ ] Xác minh shared library và dependencies.
- [ ] Kiểm tra shared_preload_libraries.
- [ ] Chạy ALTER EXTENSION UPDATE theo path hỗ trợ.
- [ ] Xác minh function/type/operator/worker behavior.
- [ ] Kiểm tra standby/failover packages.

### Post-upgrade acceptance

- [ ] Configuration và startup logs sạch.
- [ ] ANALYZE hoàn tất theo kế hoạch.
- [ ] Sequences/identity đúng.
- [ ] Roles/grants/RLS/authentication đúng.
- [ ] Indexes/constraints valid.
- [ ] Application smoke tests đạt.
- [ ] Query latency/error rate trong ngưỡng.
- [ ] Replication/CDC healthy.
- [ ] Data reconciliation đạt.
- [ ] Backup/restore readiness xác nhận.
- [ ] Evidence và reviewer sign-off đầy đủ.

## 52. Tài liệu PostgreSQL chính thức

Đọc tài liệu đúng major version đang vận hành:

- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html) — các phương thức nâng cấp cluster.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — nâng cấp major version.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — providers, locales và collations.
- [ALTER COLLATION](https://www.postgresql.org/docs/current/sql-altercollation.html) — refresh collation version.
- [ALTER DATABASE](https://www.postgresql.org/docs/current/sql-alterdatabase.html) — database properties và refresh default collation version.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) — rebuild indexes và concurrent mode.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — cài extension.
- [ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html) — update extension version.
- [pg_available_extensions](https://www.postgresql.org/docs/current/view-pg-available-extensions.html) — extension inventory.
- [pg_extension](https://www.postgresql.org/docs/current/catalog-pg-extension.html) — installed extension metadata.
- [Extension Building Infrastructure](https://www.postgresql.org/docs/current/extend-pgxs.html) — extension packaging/build infrastructure.
- [Runtime Configuration](https://www.postgresql.org/docs/current/runtime-config.html) — server configuration.
- [Shared Library Preloading](https://www.postgresql.org/docs/current/runtime-config-client.html) — preload settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — server and replication monitoring.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — backup and recovery.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html) — cluster control metadata.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html) — collect planner statistics.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher/subscriber behavior and schema coordination.

Các URL /current/ trỏ tới tài liệu hiện hành. Catalog columns, extension update paths, provider support, command options và locking behavior có thể khác theo PostgreSQL major version, operating system và managed provider. Luôn đối chiếu tài liệu của đúng server/tool version trước khi chạy lệnh trên production.

## 53. Tổng kết

**Sự cố sau upgrade cần được phân loại trước khi sửa.** PostgreSQL binary/data upgrade, collation provider change và extension package/SQL update là các lớp khác nhau, dù có thể xuất hiện cùng lúc.

1. **Xác minh cluster, version và maintenance timeline.** Không suy luận nguyên nhân chỉ từ thời điểm lỗi.
2. **Major upgrade cần quy trình chuyển đổi được hỗ trợ.** Không mở data directory cũ bằng binary major mới.
3. **Collation mismatch có thể làm index ordering/equality cũ không còn phù hợp.** Xác định dependent objects và rebuild trước.
4. **REFRESH COLLATION VERSION chỉ cập nhật metadata.** Nó không sửa hoặc rebuild index.
5. **Unique indexes có thể phát hiện duplicate theo collation mới.** Giải quyết business data conflict trước khi rebuild.
6. **Extension có package/binary version và SQL version riêng.** Cần kiểm tra cả hai cùng server compatibility.
7. **ALTER EXTENSION UPDATE cần update path hợp lệ.** Không sửa pg_extension catalog trực tiếp.
8. **shared_preload_libraries thường cần restart.** Giữ nguyên các libraries đang được sử dụng.
9. **Sau upgrade cần ANALYZE, kiểm tra sequences, roles, grants, replication và application.**
10. **Rollback cần xét writes đã phát sinh và upgrade method.** Link mode không phải backup độc lập.
11. **Monitoring và acceptance gates phải bao phủ database lẫn application.** Server running chưa đủ để đóng maintenance.
12. **Bảo toàn evidence trước remediation.** Ghi versions, logs, object scope, commands và verification results.

Một lần nâng cấp chỉ hoàn tất khi database, extension, collation, application và downstream consumers cùng đạt trạng thái tương thích có thể kiểm chứng.
