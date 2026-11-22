# Xác minh dữ liệu, quyền, hiệu năng và sao lưu sau nâng cấp PostgreSQL

Một đợt nâng cấp PostgreSQL chỉ hoàn tất khi hệ thống mới chạy đúng, dữ liệu còn nguyên vẹn, quyền truy cập giữ đúng ý định, ứng dụng hoạt động ổn định và backup có thể phục hồi. Việc server khởi động thành công hoặc lệnh nâng cấp trả về exit code 0 chỉ chứng minh một phần của quá trình.

Sau nâng cấp, cần kiểm tra theo nhiều lớp:

- **Nền tảng và phiên bản:** server đang chạy đúng binary, major/minor version, extension và cấu hình dự kiến.
- **Dữ liệu và database objects:** schema, rows, indexes, constraints, sequences, large objects và metadata được giữ đúng.
- **Quyền và bảo mật:** roles, memberships, ownership, grants, default privileges, row-level security và authentication vẫn đúng.
- **Hiệu năng:** planner statistics được cập nhật, query plans hợp lý, latency/throughput không regression và resource usage nằm trong ngưỡng.
- **HA và backup:** replication hoạt động, WAL archive tiếp tục, backup mới được tạo và restore test đạt.
- **Ứng dụng và vận hành:** client/driver tương thích, smoke tests đạt, monitoring/alerting nhận diện đúng server mới và evidence được lưu.

Bài học này trình bày quy trình xác minh sau nâng cấp cho cả minor update và major upgrade, với các câu lệnh SQL, kiểm tra hệ điều hành, cách so sánh baseline và tiêu chí đóng thay đổi.

~~~mermaid
flowchart TD
    A["Hoàn tất upgrade"] --> B["Xác nhận version và cluster identity"]
    B --> C["Kiểm tra extensions, catalogs và configuration"]
    C --> D["Đối chiếu schema và dữ liệu"]
    D --> E["Xác minh roles, grants và security"]
    E --> F["Analyze và đánh giá query plans"]
    F --> G["Kiểm tra HA, WAL và replication"]
    G --> H["Tạo backup mới"]
    H --> I["Restore test và application smoke tests"]
    I --> J{"Tất cả tiêu chí đạt?"}
    J -->|"Không"| K["Dừng đóng change, điều tra / recovery"]
    J -->|"Có"| L["Lưu evidence và sign-off"]
~~~

Bài học thuộc chương **Nâng cấp**, module **Database Engine Relational PostgreSQL**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kiểm tra sau minor update và major upgrade.
2. Xác nhận PostgreSQL server, client tools, cluster và endpoint đang dùng đúng phiên bản.
3. Kiểm tra extension versions và shared library compatibility.
4. Xác minh schema, tables, indexes, constraints, sequences và large objects.
5. Đối chiếu dữ liệu giữa source và target bằng counts, aggregates và checks.
6. Phát hiện index invalid, constraint chưa validate và object ownership sai.
7. Kiểm tra roles, role memberships, ACLs, default privileges và RLS.
8. Xác minh pg_hba.conf, TLS, authentication và security-sensitive settings.
9. Kiểm tra collation versions và xử lý yêu cầu REINDEX khi cần.
10. Cập nhật planner statistics sau major upgrade.
11. So sánh query plans và hiệu năng với baseline trước nâng cấp.
12. Kiểm tra replication, logical replication, slots và WAL archive.
13. Tạo backup mới sau nâng cấp và kiểm tra khả năng restore.
14. Chạy application smoke tests và kiểm tra driver compatibility.
15. Thu thập evidence có timestamp, context và nguồn rõ ràng.
16. Xây dựng tiêu chí chấp nhận, rollback/recovery và đóng change.

## 2. Minor update và major upgrade khác nhau thế nào?

Cách xác minh phụ thuộc loại nâng cấp.

### Minor update

Minor update thường thay đổi các chữ số ở phần minor/release trong cùng một major series, ví dụ từ một bản PostgreSQL 16.x sang bản 16.y mới hơn. Các bản cập nhật này thường giữ nguyên định dạng dữ liệu trên disk trong cùng major version, nhưng vẫn cần kiểm tra:

- Server binary thực tế đã được cập nhật.
- Service restart thành công.
- Extension packages/binaries tương thích.
- Configuration không có lỗi hoặc setting bị thay đổi.
- Application connections và queries hoạt động.
- Backup/WAL archiving tiếp tục.
- Logs không có lỗi mới sau restart.

Minor update không đồng nghĩa bỏ qua kiểm thử. Một bản cập nhật có thể sửa bug, security issue hoặc thay đổi hành vi ở một thành phần cụ thể.

### Major upgrade

Major upgrade chuyển từ một major version sang major version khác, ví dụ PostgreSQL 15 lên 16. Major upgrade có thể liên quan đến:

- Thay đổi catalog và internal data structures.
- Thay đổi planner/executor behavior.
- Extension phải cài lại hoặc nâng cấp.
- Thay đổi default configuration.
- Thay đổi statistics views và system catalogs.
- Collation/library version differences.
- Driver/client compatibility.
- Replication topology và logical replication behavior.
- Yêu cầu tạo lại backup chain phù hợp với cluster mới.

Các phương pháp major upgrade phổ biến:

| Phương pháp | Cách hoạt động | Điểm cần xác minh |
| --- | --- | --- |
| pg_upgrade | Chuyển cluster hiện có sang binary major version mới | Catalog compatibility, extension binaries, post-upgrade analyze |
| Dump/restore | Export logical data rồi import vào cluster mới | Object completeness, data reconciliation, ownership, duration |
| Logical replication migration | Đồng bộ dữ liệu sang cluster mới rồi cutover | Schema parity, replication lag, sequence state, final consistency |
| Managed service upgrade | Provider điều phối upgrade | Provider logs, version, extensions, endpoint, backups và HA |

Không dùng cùng một checklist chi tiết cho mọi phương pháp. Ví dụ, dump/restore cần đối chiếu dữ liệu và objects rất kỹ; pg_upgrade cần chú ý extension binaries, collation và statistics; logical replication cần xử lý writes cuối, sequences và cutover watermark.

## 3. Tiêu chí hoàn tất nâng cấp

Trước khi thực hiện, hãy xác định acceptance criteria cụ thể. Ví dụ:

| Nhóm | Tiêu chí chấp nhận mẫu |
| --- | --- |
| Version | Server báo đúng major/minor version đã phê duyệt |
| Cluster identity | Kết nối đúng environment, database và node |
| Database availability | Tất cả database cần phục vụ có thể kết nối |
| Objects | Schema, tables, views, functions, triggers và indexes cần thiết tồn tại |
| Data integrity | Row counts/aggregates/checks theo policy khớp |
| Indexes | Không có index invalid ngoài các trường hợp đã biết |
| Constraints | Constraint cần thiết tồn tại và validated |
| Sequences | Sequence state không lùi sau dữ liệu hiện có |
| Permissions | Role, ownership và effective privileges đúng |
| Security | Authentication, TLS, HBA, RLS và audit settings đúng |
| Performance | Latency/throughput không vượt regression budget |
| Replication | Standby/consumers streaming và lag trong ngưỡng |
| Backup | Backup mới hoàn tất, archive hoạt động và restore test đạt |
| Application | Smoke tests và critical workflows thành công |
| Monitoring | Metrics/alerts nhận diện đúng cluster mới |
| Evidence | Có đầy đủ output, logs, metrics và sign-off |

Các ngưỡng như latency regression, replication lag và thời gian quan sát phải được service owner định nghĩa trước. Không dùng một ngưỡng chung cho mọi hệ thống.

## 4. Xác nhận đúng server và cluster

Sau upgrade, trước tiên xác nhận kết nối đang trỏ tới đúng cluster. Với endpoint qua proxy, load balancer hoặc DNS alias, không suy luận node chỉ từ hostname mà ứng dụng sử dụng.

~~~sql
SELECT
    version() AS server_version,
    current_setting('server_version') AS server_version_setting,
    current_setting('server_version_num') AS server_version_num,
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS server_started_at,
    pg_is_in_recovery() AS is_standby;
~~~

Kiểm tra thêm:

~~~sql
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW port;
SHOW listen_addresses;
~~~

Các giá trị đường dẫn có thể chứa thông tin hạ tầng; chỉ lưu vào evidence repository có quyền truy cập phù hợp.

### Kiểm tra binary phía hệ điều hành

Trên Linux, kiểm tra binary và tool path:

~~~bash
postgres --version
psql --version
pg_ctl --version
pg_config --version
which postgres
which psql
~~~

Service có thể đang chạy binary khác với binary đầu tiên trong PATH. Kiểm tra unit/service definition, process command line và package manager để xác nhận executable thực tế.

Trên Windows, dùng service configuration và đường dẫn executable của PostgreSQL service. Với managed database, dùng console/API và provider events.

### Vì sao phải kiểm tra client tools riêng?

Có thể server đã nâng cấp nhưng psql, pg_dump, pg_restore, pg_basebackup hoặc extension build tools vẫn ở version cũ. Một số client tools hỗ trợ kết nối tới server khác major version, nhưng không có nghĩa mọi tool operation đều tương thích theo mọi hướng. Dùng tool version được khuyến nghị cho quy trình upgrade/backup.

## 5. Xác minh tất cả database

Liệt kê database:

~~~sql
SELECT
    datname,
    datallowconn,
    datistemplate,
    pg_get_userbyid(datdba) AS owner,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY datname;
~~~

Đối chiếu với inventory trước upgrade:

- Database nào cần giữ?
- Database nào được tạo bởi ứng dụng hoặc extension?
- Owner có thay đổi không?
- Database có allow connections đúng không?
- Encoding và locale có đúng không?
- Database template có bị thay đổi ngoài kế hoạch không?

Kiểm tra encoding và locale:

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion
FROM pg_database
ORDER BY datname;
~~~

Một số cột, chẳng hạn locale provider/collation version, phụ thuộc major version. Nếu query không tương thích, điều chỉnh theo catalog của server đang chạy và dùng các lệnh SHOW hoặc psql meta-commands tương ứng.

### Kết nối từng database

Một query chạy được trong database postgres không chứng minh các database nghiệp vụ đều hoạt động. Runbook cần kết nối từng database quan trọng và chạy tối thiểu:

- SELECT current_database().
- Kiểm tra schema inventory.
- Kiểm tra extension.
- Kiểm tra quyền của application role.
- Chạy smoke query đại diện.

## 6. Xác minh extensions

Extensions có cả metadata trong database và shared library/control files ở filesystem. Major upgrade cần bảo đảm cả hai phía tương thích.

Liệt kê extensions đã cài:

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    pg_get_userbyid(e.extowner) AS extension_owner
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

So sánh với danh sách extension được phê duyệt trước nâng cấp.

Xem extension versions có sẵn trên server:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Nếu extension đã cài nhưng shared library hoặc control file không có, extension có thể lỗi khi gọi function hoặc khi thực hiện upgrade script.

### Kiểm tra extension packages

Với self-managed PostgreSQL:

- Cài đúng package extension cho major version mới.
- Cài shared libraries đúng architecture/ABI.
- Kiểm tra control files và SQL upgrade scripts.
- Xác minh dependency như PostGIS, PL/Python, FDW hoặc extension nội bộ.
- Restart nếu extension cần preload.
- Chạy ALTER EXTENSION UPDATE theo tài liệu và kế hoạch.

Không chạy UPDATE tất cả extensions một cách mù quáng. Một số extension có upgrade path nhiều bước hoặc cần thao tác riêng.

### shared_preload_libraries

~~~sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
SHOW local_preload_libraries;
~~~

Nếu extension yêu cầu preload, xác minh module đã được nạp sau restart và log không có lỗi library load. Kiểm tra từng database vì CREATE EXTENSION thường được thực hiện riêng trong từng database.

## 7. Kiểm tra schema và database objects

Với dump/restore hoặc logical migration, cần đối chiếu object inventory giữa source và target. Với pg_upgrade, catalog được chuyển đổi nhưng vẫn nên xác minh các objects quan trọng.

### Table và partition

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
~~~

Kiểm tra partition:

~~~sql
SELECT
    parent.relid::regclass AS partitioned_table,
    parent.isleaf,
    parent.level
FROM pg_partition_tree('public.events') AS parent
ORDER BY parent.level, parent.relid;
~~~

Thay public.events bằng partitioned table thực tế. Nếu version không hỗ trợ hàm này, dùng pg_inherits và catalog liên quan.

### Views và materialized views

~~~sql
SELECT
    schemaname,
    viewname,
    viewowner
FROM pg_views
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, viewname;
~~~

Materialized views cần xác minh tồn tại và dữ liệu đã được refresh nếu quy trình migration/restore yêu cầu.

### Functions và procedures

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef AS security_definer
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
~~~

Kiểm tra function/procedure quan trọng bằng smoke calls trong môi trường an toàn. Một function có thể tồn tại nhưng lỗi do extension, search_path, type hoặc permission thay đổi.

### Triggers

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled
FROM pg_trigger AS t
JOIN pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
ORDER BY n.nspname, c.relname, t.tgname;
~~~

Đối chiếu trigger enable state với baseline. Không bật thủ công trigger bị disable theo chủ đích của ứng dụng hoặc migration.

## 8. Phát hiện index invalid hoặc chưa sẵn sàng

Một index có thể tồn tại trong catalog nhưng không hợp lệ để planner sử dụng. Điều này có thể xảy ra sau CREATE INDEX CONCURRENTLY thất bại hoặc thao tác bị ngắt.

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive
FROM pg_index AS i
WHERE NOT i.indisvalid
   OR NOT i.indisready
   OR NOT i.indislive
ORDER BY i.indrelid::regclass::text;
~~~

Kết quả cần được điều tra. Một số index invalid có thể đã được chấp nhận có chủ đích trong một quy trình đặc biệt; ghi rõ exception. Nếu không có lý do, xử lý theo runbook: kiểm tra build logs, xác định dependency và tạo lại/drop index một cách an toàn.

### Kiểm tra index quan trọng

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

Đối chiếu definition, uniqueness, predicate, included columns, tablespace và storage parameters. Chỉ so sánh tên index là chưa đủ.

## 9. Xác minh constraints

Liệt kê constraint chưa validate:

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE NOT convalidated
ORDER BY conrelid::regclass::text, conname;
~~~

Một constraint NOT VALID có thể là trạng thái được thiết kế có chủ đích, ví dụ constraint được thêm để kiểm tra dữ liệu mới trước khi validate dữ liệu cũ. Không tự động validate mọi constraint khi chưa đánh giá thời gian, lock và data quality.

Kiểm tra constraint quan trọng:

- Primary key.
- Unique constraints.
- Foreign keys.
- Check constraints.
- Exclusion constraints.

Với dump/restore, xác minh cả constraint definitions và dữ liệu thỏa mãn. Với migration, xác minh các constraint mới đã được validate đúng kế hoạch.

## 10. Xác minh sequence và identity columns

Sequence state rất dễ bị bỏ sót khi dùng dump/restore hoặc logical replication. Nếu sequence đứng sau giá trị lớn nhất trong bảng, lần INSERT tiếp theo có thể gặp duplicate key.

Liệt kê sequence:

~~~sql
SELECT
    schemaname,
    sequencename,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    last_value
FROM pg_sequences
ORDER BY schemaname, sequencename;
~~~

last_value có thể NULL khi sequence chưa được gọi trong session/server state hoặc user không có quyền xem theo semantics của version. Đừng diễn giải NULL như lỗi nâng cấp.

### Đối chiếu sequence với dữ liệu

Với sequence gắn vào cột serial/identity, xác định sequence qua pg_get_serial_sequence:

~~~sql
SELECT pg_get_serial_sequence('public.orders', 'order_id');
~~~

Sau đó kiểm tra giá trị sequence và giá trị lớn nhất trong bảng. Cần tính đến increment âm, sequence cycle, cache và transaction đang ghi. Không chạy setval tùy tiện trong production vì có thể tạo race với writers.

Nếu cần đồng bộ sequence sau logical migration, thực hiện trong cutover window sau khi đã dừng writers, xác định chính xác sequence và hướng setval. Ghi lại old/new value và kiểm tra bằng một transaction phù hợp.

### Identity columns

Identity columns dùng sequence nội bộ nhưng có metadata khác serial. Kiểm tra column metadata trong information_schema.columns và pg_attribute/pg_depend nếu cần phân tích sâu. Xác minh generated identity behavior bằng insert test trong staging hoặc transaction rollback ở môi trường an toàn.

## 11. Large objects và dữ liệu ngoài bảng

PostgreSQL large objects được quản lý riêng với các table rows thông thường. Dump/restore cần bao gồm large objects nếu ứng dụng sử dụng chúng.

Kiểm tra số large objects:

~~~sql
SELECT count(*) AS large_object_count
FROM pg_largeobject_metadata;
~~~

Đối chiếu với source baseline. Có thể cần kiểm tra quyền sở hữu và ACL trên large objects, không chỉ số lượng.

Các dữ liệu ngoài database như file trên filesystem, object storage, foreign data source, secrets và external services không tự được chuyển chỉ vì PostgreSQL cluster đã nâng cấp. Xác minh các dependency đó theo inventory ứng dụng.

## 12. Đối chiếu dữ liệu giữa source và target

Phương pháp so sánh phụ thuộc upgrade path.

### Với pg_upgrade

pg_upgrade chuyển đổi cluster theo cơ chế physical/catalog upgrade. Không phải dump/restore toàn bộ rows. Dù vậy, cần xác minh database/object inventory, table accessibility, constraints, indexes và application behavior.

### Với dump/restore hoặc logical migration

Dùng một cutover point nhất quán. Nếu source tiếp tục nhận writes trong khi target được kiểm tra, counts có thể khác chỉ vì dữ liệu mới phát sinh.

Các phép kiểm tra thường dùng:

- Row count theo table/partition.
- Min/max primary key.
- Min/max timestamps.
- Aggregates trên các cột nghiệp vụ.
- Duplicate key checks.
- Null/range checks.
- Referential integrity.
- Checksum theo key range hoặc partition.
- Large object counts.

Ví dụ:

~~~sql
SELECT
    count(*) AS row_count,
    min(order_id) AS min_order_id,
    max(order_id) AS max_order_id,
    min(created_at) AS first_order,
    max(created_at) AS last_order,
    sum(total_amount) AS total_amount
FROM public.orders;
~~~

Kiểm tra duplicate:

~~~sql
SELECT order_id, count(*) AS occurrences
FROM public.orders
GROUP BY order_id
HAVING count(*) > 1
LIMIT 100;
~~~

Kiểm tra NULL/range:

~~~sql
SELECT
    count(*) FILTER (WHERE order_id IS NULL) AS null_ids,
    count(*) FILTER (WHERE total_amount < 0) AS negative_amounts
FROM public.orders;
~~~

### Không chỉ dựa vào row count

Hai bảng có cùng row count nhưng vẫn có thể chứa dữ liệu khác nhau. Với dữ liệu quan trọng, so sánh aggregates/checksums theo key range hoặc partition và ghi rõ phương pháp. Hash toàn bảng có thể tốn CPU/I/O và cần snapshot nhất quán.

### Đảm bảo snapshot nhất quán

Nếu có thể, dừng writes hoặc dùng cơ chế snapshot/watermark đã được thiết kế. Với logical replication, chờ subscription catch up, ghi nhận final LSN/watermark và điều phối cutover để không bỏ sót writes.

## 13. Xác minh ownership

Sau dump/restore, role ownership có thể khác nếu role không được tạo hoặc map đúng.

Kiểm tra table owners:

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
~~~

Kiểm tra database owner:

~~~sql
SELECT
    datname,
    pg_get_userbyid(datdba) AS database_owner
FROM pg_database
ORDER BY datname;
~~~

Kiểm tra schema owners:

~~~sql
SELECT
    nspname AS schema_name,
    pg_get_userbyid(nspowner) AS schema_owner
FROM pg_namespace
WHERE nspname NOT LIKE 'pg_%'
  AND nspname <> 'information_schema'
ORDER BY nspname;
~~~

So sánh với ownership baseline và role mapping. Không dùng một lệnh REASSIGN OWNED toàn cluster nếu chưa hiểu scope; lệnh có thể ảnh hưởng nhiều object thuộc role đó trong database hiện tại.

## 14. Xác minh roles và attributes

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolbypassrls,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
ORDER BY rolname;
~~~

Đối chiếu các role quan trọng:

- Superuser/admin roles.
- Application login roles.
- Read-only/reporting roles.
- Replication roles.
- Backup/monitoring roles.
- Migration/deployment roles.
- Roles bị khóa hoặc hết hạn theo policy.

Role tồn tại không có nghĩa password/secret đã được đồng bộ đúng. Không xuất password hashes vào evidence. Kiểm tra authentication bằng secret manager và test login an toàn.

### Role memberships

~~~sql
SELECT
    member.rolname AS member_role,
    granted.rolname AS granted_role,
    grantor.rolname AS grantor_role,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS member
    ON member.oid = m.member
JOIN pg_roles AS granted
    ON granted.oid = m.roleid
JOIN pg_roles AS grantor
    ON grantor.oid = m.grantor
ORDER BY member.rolname, granted.rolname;
~~~

Role membership semantics và các cột tùy chọn có thể khác theo version. Đối chiếu các memberships cần thiết và kiểm tra quyền kế thừa/set role của ứng dụng.

## 15. Xác minh grants và effective privileges

PostgreSQL có nhiều lớp quyền:

- Database CONNECT/TEMP/CREATE.
- Schema USAGE/CREATE.
- Table SELECT/INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER.
- Sequence USAGE/SELECT/UPDATE.
- Function EXECUTE.
- Type USAGE.
- Tablespace CREATE.
- Role membership và ownership.

### Table grants

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee, privilege_type;
~~~

View information_schema có thể chỉ hiển thị grants phù hợp với quyền nhìn thấy của current user. Với audit toàn diện, dùng catalog/ACL inspection và role có quyền giám sát phù hợp.

### Effective privilege checks

~~~sql
SELECT
    has_database_privilege('orders_app', 'sales', 'CONNECT') AS can_connect,
    has_schema_privilege('orders_app', 'public', 'USAGE') AS can_use_public,
    has_table_privilege('orders_app', 'public.orders', 'SELECT') AS can_read_orders,
    has_table_privilege('orders_app', 'public.orders', 'INSERT') AS can_insert_orders;
~~~

Thay role/database/object theo môi trường. Effective privilege functions giúp xác minh quyền thực tế sau khi xét membership và ownership trong ngữ cảnh kiểm tra.

### Default privileges

Default privileges ảnh hưởng object được tạo trong tương lai. Một restore có thể giữ grants hiện tại nhưng thiếu default privileges cho objects mới.

Kiểm tra:

~~~sql
SELECT
    defaclrole::regrole AS owner_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype,
    defaclacl
FROM pg_default_acl
ORDER BY owner_role, schema_name, defaclobjtype;
~~~

Đối chiếu default privileges theo creator role và schema. Lệnh ALTER DEFAULT PRIVILEGES áp dụng theo role thực hiện/đối tượng tạo, nên cần xác minh bằng cách tạo object test trong staging hoặc transaction phù hợp.

## 16. Xác minh row-level security và security settings

### Row-level security

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS rls_forced
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
~~~

Kiểm tra policies:

~~~sql
SELECT *
FROM pg_policies
ORDER BY schemaname, tablename, policyname;
~~~

Test bằng role ứng dụng thực tế. Superuser và role có BYPASSRLS có thể bỏ qua RLS, vì vậy test bằng admin không chứng minh application role bị giới hạn đúng.

### Security definer functions

Functions dùng SECURITY DEFINER chạy với quyền của owner. Kiểm tra các routine này, owner và search_path:

~~~sql
SELECT
    n.nspname,
    p.proname,
    pg_get_userbyid(p.proowner) AS owner,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
~~~

Xác minh search_path an toàn theo policy và đảm bảo role owner không có quyền quá rộng không cần thiết.

### HBA và TLS

Kiểm tra rules:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

Kiểm tra TLS setting:

~~~sql
SHOW ssl;
SHOW ssl_min_protocol_version;
SHOW ssl_cert_file;
SHOW ssl_ca_file;
~~~

Đường dẫn certificate có thể nhạy cảm. Test kết nối TLS từ ứng dụng/monitoring client và xác nhận certificate chain/hostname validation. Không chỉ dựa vào SHOW ssl = on.

## 17. Kiểm tra collation và locale version

Major upgrade hoặc nâng OS/ICU/glibc có thể làm thay đổi collation behavior. Collation thay đổi có thể khiến thứ tự so sánh/sắp xếp khác trước và ảnh hưởng index dựa trên collation.

Kiểm tra database collation version:

~~~sql
SELECT
    datname,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion,
    pg_database_collation_actual_version(oid) AS actual_collation_version
FROM pg_database
ORDER BY datname;
~~~

Kiểm tra collations trong database hiện tại:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.collname,
    c.collprovider,
    c.collversion,
    pg_collation_actual_version(c.oid) AS actual_version
FROM pg_collation AS c
JOIN pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.collname;
~~~

Một số cột/function phụ thuộc major version và locale provider. Nếu server không hỗ trợ một cột, điều chỉnh query theo version.

### Khi collation version khác

Không bỏ qua warning collation version mismatch. Cần:

1. Xác định provider (libc/ICU) và version trước/sau.
2. Liệt kê index/collation-dependent objects liên quan.
3. Lập kế hoạch REINDEX các objects bị ảnh hưởng.
4. Chọn cách rebuild phù hợp lock/downtime.
5. Chỉ refresh recorded collation version sau khi đã rebuild các objects cần thiết theo tài liệu.
6. Chạy lại kiểm tra và lưu evidence.

Các lệnh REFRESH VERSION chỉ cập nhật metadata version đã ghi nhận; chúng không tự rebuild index. Thực hiện refresh quá sớm có thể che dấu mismatch trong khi index cũ vẫn còn.

## 18. Xác minh cấu hình sau nâng cấp

So sánh cấu hình hiệu lực với baseline và configuration management.

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

Tập trung vào:

- max_connections và reserved slots.
- shared_buffers, work_mem, maintenance_work_mem.
- WAL/checkpoint settings.
- logging settings.
- autovacuum.
- SSL/authentication.
- replication settings.
- planner cost constants.
- locale/collation.
- preload libraries.
- extension-specific settings.

### Xác định config errors

~~~sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE error IS NOT NULL
   OR applied = false
ORDER BY sourcefile, sourceline;
~~~

Một số dòng không được áp dụng có thể do override hợp lệ từ file/command line/session. Đọc source và precedence trước khi kết luận là lỗi.

### Parameter mới và default thay đổi

Major upgrade có thể thêm setting mới hoặc thay đổi default. So sánh toàn bộ pg_settings có thể tạo nhiều khác biệt hợp lệ. Review những setting ảnh hưởng durability, memory, planner, authentication và logging theo release notes.

Không copy nguyên postgresql.conf cũ vào major version mới mà không review. Một số parameter có thể đã bị đổi tên, bỏ hoặc thay semantics.

## 19. Cập nhật planner statistics sau major upgrade

Planner statistics có thể không được chuyển hoặc không còn đại diện tốt cho cluster mới. Sau pg_upgrade, chạy analyze theo hướng dẫn output của pg_upgrade.

Ví dụ:

~~~bash
vacuumdb --all --analyze-in-stages
~~~

Lệnh này phân tích các database theo stages để planner sớm có statistics cơ bản rồi tiếp tục tăng độ chi tiết. Chạy bằng role có đủ quyền và dùng client tools phù hợp với server version.

Với database lớn, việc analyze có thể tạo I/O và CPU đáng kể. Theo dõi progress, load và application latency. Không mở lại toàn bộ workload peak nếu hệ thống chưa đủ capacity.

### Xác minh statistics

~~~sql
SELECT
    schemaname,
    relname,
    last_analyze,
    last_autoanalyze,
    n_live_tup,
    n_mod_since_analyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC;
~~~

Thời điểm analyze có thể NULL nếu table chưa được analyze. Đánh giá bảng quan trọng theo query workload thay vì yêu cầu mọi table có cùng timestamp.

## 20. Xác minh query plans và performance

Major version mới có thể thay đổi planner, executor và cost behavior. Query từng nhanh ở version cũ có thể chọn plan khác.

Với query quan trọng, lưu plan trước/sau:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
SELECT
    order_id,
    created_at,
    total_amount
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

EXPLAIN ANALYZE thực thi câu lệnh. Với DML, có thể thay đổi dữ liệu; dùng staging hoặc transaction rollback phù hợp. Không chạy query benchmark nặng tùy tiện trên production trong peak hours.

So sánh:

- Plan nodes và join strategy.
- Estimated rows so với actual rows.
- Execution time.
- Shared/local/temp buffers.
- I/O timings khi bật.
- Sort method và disk spill.
- Hash batches.
- Rows removed by filter.
- WAL generated.
- Parallel workers.
- Settings ảnh hưởng plan.

Một plan khác không tự động là regression. So sánh latency và resource consumption trên workload đại diện.

## 21. Dùng pg_stat_statements để so sánh workload

Nếu extension được cài và preload đúng:

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
    left(query, 180) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Tên/cột có thể thay đổi giữa extension versions. Kiểm tra schema thực tế của pg_stat_statements sau nâng cấp.

### So sánh trước/sau

- Lưu snapshot trước upgrade nếu có.
- Ghi thời gian reset statistics.
- Dùng cùng observation window.
- Chuẩn hóa theo số calls và workload volume.
- Xem p95/p99 từ APM nếu extension không cung cấp percentile phù hợp.
- Phân biệt cache warm-up với regression lâu dài.
- Không so sánh counters nếu chúng reset giữa hai snapshot mà không biết.

pg_stat_statements có thể cần reset hoặc khởi tạo lại theo policy. Không reset statistics ngay khi vừa nâng cấp nếu còn cần evidence để so sánh.

## 22. Warm-up và cache behavior

Sau restart/upgrade, shared buffers và OS page cache có thể lạnh hơn trước. Query đầu tiên có thể chậm hơn bình thường do phải đọc pages từ storage.

Có thể dùng workload warm-up có kiểm soát:

- Chạy các query read-only đại diện.
- Dùng pg_prewarm nếu extension được cài và có nhu cầu.
- Khởi động application pools dần.
- Theo dõi storage latency và cache hit.
- Tránh tạo tải warm-up vượt capacity.

Không đánh giá performance chỉ bằng vài phút đầu sau restart. Đồng thời, không bỏ qua regression thật bằng cách gọi mọi query chậm là cache cold. Xác định observation window trước.

## 23. Kiểm tra database health và transaction behavior

### Long-running transactions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Kiểm tra transaction cũ, idle-in-transaction và session bị block.

### Locks

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 160) AS query_sample
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
~~~

Cú pháp/columns có thể khác theo version. Xác minh lock contention trong observation window và xem server logs nếu xuất hiện deadlocks.

### Database statistics

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
~~~

Dùng counters để so sánh delta trong cùng cửa sổ thời gian. Không kết luận từ tổng tích lũy của cluster mà không xét stats_reset và workload.

## 24. Xác minh replication và HA

Sau nâng cấp, xác nhận topology đúng với kế hoạch.

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

Trên standby:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
~~~

Kiểm tra WAL receiver:

~~~sql
SELECT
    status,
    sender_host,
    sender_port,
    received_tli,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    last_msg_receipt_time
FROM pg_stat_wal_receiver;
~~~

Đối chiếu:

- Số standby dự kiến.
- Replication state.
- Sync state.
- LSN progress.
- Replication lag.
- Network errors.
- Replication slots.
- HA manager/DCS health.
- Fencing/leader state nếu topology có orchestration.

### Replication slots

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
~~~

Logical/physical slot handling có thể thay đổi theo version và upgrade method. Không giả định mọi logical slots, subscriptions hoặc downstream consumers tự tiếp tục. Kiểm tra trạng thái consumer, slot validity, restart LSN và WAL retention.

## 25. Xác minh logical replication và subscriptions

Nếu dùng logical replication, kiểm tra publisher/subscriber:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

Trên subscriber, kiểm tra trạng thái worker và subscription stats theo version:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Xác minh:

- Subscription enabled.
- Apply workers chạy.
- Replication slot tồn tại và active đúng.
- Table synchronization hoàn tất.
- Không có persistent apply errors.
- Schema hai phía tương thích.
- Sequence values được đồng bộ riêng khi cutover cần.
- Conflict/data drift được điều tra.

Logical replication không tự replicate mọi object như roles, DDL, sequences hoặc large objects. Các đối tượng này cần quy trình riêng.

## 26. Xác minh WAL archiving

Kiểm tra cấu hình:

~~~sql
SHOW archive_mode;
SHOW archive_command;
SHOW wal_level;
~~~

Kiểm tra statistics:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Sau major upgrade, archive destination/path/permissions hoặc tool integration có thể thay đổi. Xác minh WAL mới được archive thành công sau thời điểm nâng cấp. Không chỉ nhìn một archive thành công từ trước upgrade.

Nếu dùng archive module hoặc backup tool riêng, kiểm tra logs/metadata của tool và thực hiện restore/PITR test trên môi trường tách biệt.

## 27. Tạo backup mới sau nâng cấp

Một cluster sau major upgrade là một trạng thái vận hành mới. Tạo backup mới theo công cụ hỗ trợ major version mới, thay vì chỉ dựa vào backup cũ.

Backup mới cần bao gồm:

- Physical base backup phù hợp với version mới.
- WAL archive sau thời điểm backup.
- Backup metadata/manifest.
- Cấu hình PostgreSQL cần thiết.
- Extension packages và version inventory.
- Role/global objects theo quy trình.
- Tablespace mapping.
- TLS/certificates/secrets được lưu trong secret manager theo policy.
- HA manager configuration và service inventory khi cần.

### Vì sao backup cũ vẫn quan trọng?

Backup trước upgrade có thể là đường phục hồi về cluster cũ. Giữ chúng theo retention và rollback policy. Không xóa backup cũ chỉ vì backup mới đã chạy; cần biết thời điểm rollback window kết thúc và cách phục hồi độc lập.

### Backup physical và logical

- Physical backup phù hợp cho restore cluster cùng major version và recovery theo WAL.
- Logical dump hữu ích cho portability, object-level recovery và kiểm tra dữ liệu.
- Backup configuration/roles có thể cần riêng tùy công cụ.
- Managed services có snapshot/automated backup semantics riêng.

Đọc tài liệu của backup tool và provider để xác nhận hỗ trợ PostgreSQL major version mới.

## 28. Restore test sau nâng cấp

Backup hoàn tất không chứng minh có thể restore. Thực hiện restore drill trên môi trường cô lập.

Quy trình:

1. Chọn backup ID sau nâng cấp.
2. Xác nhận manifest/checksum và WAL coverage.
3. Chuẩn bị target version phù hợp.
4. Restore vào host/volume test riêng.
5. Thực hiện recovery tới target mong muốn.
6. Xác nhận PostgreSQL startup và database inventory.
7. Chạy object/data integrity checks.
8. Kiểm tra extension và roles.
9. Chạy application smoke tests nếu phù hợp.
10. Đo thời gian restore và recovery point.
11. Lưu logs, output và evidence.

### RPO và RTO thực tế

- RPO thực tế được xác định bằng khoảng cách giữa recovery point và thời điểm sự cố/backup policy yêu cầu.
- RTO thực tế là thời gian từ lúc bắt đầu recovery đến khi dịch vụ được xác nhận hoạt động.

Ghi số đo từ restore test, không chỉ ghi giá trị mục tiêu trong tài liệu.

## 29. Backup và pg_upgrade

Nếu dùng pg_upgrade, giữ lại old cluster theo kế hoạch cho tới khi acceptance criteria đạt và rollback window kết thúc.

Lưu ý với hard-link mode:

- pg_upgrade có thể dùng hard links để giảm thời gian/copy space.
- Khi cluster mới bắt đầu ghi, các file được hard-link có thể cùng tham chiếu inode với old cluster.
- Sau khi new cluster đã chạy và ghi dữ liệu, old cluster có thể không còn là bản rollback độc lập an toàn.
- Không khởi động old cluster như thể nó là bản cũ nguyên vẹn sau khi hard-link upgrade đã bắt đầu hoạt động.

Nếu cần rollback độc lập, dùng phương án copy/clone hoặc backup có kế hoạch. Đọc tài liệu pg_upgrade đúng version và lưu chính xác mode đã dùng.

### Không coi pg_upgrade --check là post-upgrade validation

--check kiểm tra một số điều kiện trước khi nâng cấp. Nó không chứng minh dữ liệu sau nâng cấp, extensions, application và backup đều đúng.

## 30. Kiểm tra application và client compatibility

Sau upgrade, chạy smoke tests bằng đúng application roles và connection paths production sử dụng.

Các nhóm cần kiểm tra:

- Driver version và connection protocol.
- Authentication method và TLS.
- Prepared statements.
- Parameter types/casting.
- Date/time and timezone handling.
- Numeric/JSON/array/range types.
- Transaction isolation behavior.
- Error handling và retry.
- Stored procedures/functions.
- Extensions/FDWs.
- ORM-generated SQL.
- Connection pool reset/reconnect.
- Read/write routing.
- Batch jobs, scheduled jobs và background workers.

### Smoke tests

Ví dụ các thao tác cần test trong application:

1. Mở connection bằng service role.
2. Chạy health query.
3. Đọc một record nghiệp vụ đã biết.
4. Ghi một record test có thể rollback hoặc cleanup.
5. Chạy transaction commit/rollback.
6. Chạy query có join/index/filter quan trọng.
7. Gọi function/procedure quan trọng.
8. Kiểm tra queue/worker hoặc ETL nếu có.
9. Xác nhận application logs không có lỗi mới.
10. Xác nhận request latency và error rate trong ngưỡng.

Không chỉ test bằng superuser hoặc psql admin. Ứng dụng cần được xác minh với role, driver, network path và connection pool thực tế.

## 31. Kiểm tra timezone, encoding và data type behavior

Kiểm tra server/database/client settings:

~~~sql
SHOW server_encoding;
SHOW client_encoding;
SHOW timezone;
SHOW DateStyle;
SHOW lc_messages;
SHOW lc_monetary;
SHOW lc_numeric;
SHOW lc_time;
~~~

So sánh với baseline và yêu cầu ứng dụng.

Một số thay đổi environment có thể ảnh hưởng:

- Timestamp rendering và timezone conversion.
- Date parsing.
- Text sorting/case folding.
- Numeric formatting.
- Encoding conversion.
- Collation-sensitive uniqueness/order.
- Client driver type mapping.

Chạy test cho các giá trị biên: timestamp gần midnight/DST nếu có, Unicode, numeric precision, JSON, arrays và nulls.

## 32. Kiểm tra prepared statements và query behavior

Một số driver/ORM dùng prepared statements và có thể bị ảnh hưởng bởi planner statistics, parameter types hoặc plan caching.

Kiểm tra:

- Query có parameter binding đúng.
- Prepared statement không giữ plan kém phù hợp.
- Search_path và schema resolution đúng.
- Function/operator overload được chọn đúng.
- Transaction isolation không gây regression.
- Query timeout/statement timeout không đổi ngoài dự kiến.

Nếu dùng EXPLAIN để kiểm tra parameterized queries, tái hiện bằng cùng role, search_path và parameter types như ứng dụng. Query chạy trong psql admin có thể chọn plan khác.

## 33. Kiểm tra connection limits và pools

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
~~~

Một số version có thêm reserved slots cho roles đặc biệt. Kiểm tra parameter thực tế và quyền kết nối theo version.

Đếm session:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC;
~~~

Xác minh:

- Connection pool trỏ đúng endpoint.
- Pool size không vượt capacity.
- App reconnect sau restart.
- Không còn session stale tới old endpoint.
- Retry/backoff không tạo connection storm.
- Reserved administrative access vẫn khả dụng.

## 34. Kiểm tra monitoring và alerting

Sau upgrade, dashboard có thể không hoạt động vì system views hoặc column names đã thay đổi. Exporter phiên bản cũ có thể query catalog không còn tương thích.

Kiểm tra:

- PostgreSQL exporter version.
- SQL queries/custom collectors.
- Metrics names và labels.
- Dashboard panels.
- Alert rules.
- Log parser/schema.
- HA manager metrics.
- Backup/restore monitoring.
- Replication lag alerts.
- Disk/WAL/connection alerts.

Chạy một lần kiểm tra end-to-end: tạo hoặc quan sát một sự kiện phù hợp, xác nhận metric/log xuất hiện, dashboard hiển thị và alert routing hoạt động. Không chỉ xác nhận exporter process đang running.

## 35. Kiểm tra logs sau nâng cấp

Đọc logs từ startup và observation window:

- Configuration parameter removed/renamed/ignored.
- Extension library load failures.
- Collation version warnings.
- Invalid indexes hoặc constraints.
- Authentication/TLS failures.
- Query errors/SQLSTATE changes.
- Deadlocks và lock waits.
- WAL/archive errors.
- Replication disconnects.
- Checkpoint/I/O warnings.
- Autovacuum issues.
- Crashes, PANIC hoặc recovery loops.

So sánh với baseline trước upgrade. Một số thông điệp INFO/LOG có thể thay đổi do version; tập trung vào lỗi mới, tần suất tăng và tác động thực tế.

## 36. Kiểm tra background maintenance

Sau upgrade, xác nhận các hoạt động bảo trì tiếp tục:

- Autovacuum và autoanalyze.
- Checkpoints.
- WAL archiving.
- Backup jobs.
- Replication.
- Scheduled jobs.
- Statistics collection.
- Monitoring collectors.

Xem autovacuum progress:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
~~~

Kiểm tra table statistics:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

Statistics là ước lượng và có thể reset. Dùng cùng observation window để so sánh.

## 37. Các khác biệt đặc biệt theo upgrade method

### pg_upgrade

Tập trung vào:

- Binary paths và cluster identity.
- Extension shared libraries và SQL update scripts.
- Collation version mismatch.
- Statistics cần analyze lại.
- Invalid indexes/constraints.
- Config file differences và removed parameters.
- Logical replication slots/subscriptions theo support của version.
- Backup mới cho cluster mới.
- Old cluster rollback policy, nhất là link mode.

### Dump/restore

Tập trung vào:

- Tất cả databases và globals được dump.
- Roles, ownership, grants và default privileges.
- Large objects.
- Sequences và identity state.
- Extensions được cài đúng trước restore.
- Object creation order/dependencies.
- Data counts/checksums/aggregates.
- Invalid objects và restore warnings.
- Database encoding/locale.
- Application cutover watermark.

### Logical replication

Tập trung vào:

- Schema parity.
- Publication/subscription state.
- Table synchronization.
- Replication lag và final LSN/watermark.
- DDL không tự replicate.
- Sequence synchronization.
- Large objects và non-replicated objects.
- Final write freeze/cutover.
- Reverse replication hoặc rollback data path.

### Managed service

Tập trung vào:

- Provider upgrade event/log.
- Engine version và parameter group.
- Extension support matrix.
- Endpoint/DNS changes.
- Replicas/failover state.
- Automated backup/snapshot status.
- Provider-specific restore point.
- Monitoring/exporter compatibility.
- Maintenance window và rollback limitations.

## 38. Khi post-check thất bại

Không tiếp tục mở toàn bộ traffic hoặc đóng change nếu một tiêu chí quan trọng chưa đạt.

### Data mismatch

- Giữ source/backup theo policy.
- Dừng writers nếu cutover chưa hoàn tất.
- Xác định snapshot/watermark.
- Tìm table/partition/key range khác biệt.
- Kiểm tra sequence, trigger, generated columns và logical replication.
- Reconcile hoặc restore theo recovery plan.
- Không chạy update sửa dữ liệu hàng loạt trước khi hiểu nguyên nhân.

### Permission regression

- Xác định role/object bị ảnh hưởng.
- So sánh owner, ACL, membership và default privileges.
- Test bằng application role.
- Cấp/revoke quyền theo least privilege.
- Ghi lại effective privilege checks.
- Không giải quyết bằng cách cấp SUPERUSER cho ứng dụng.

### Performance regression

- Kiểm tra analyze/statistics.
- So sánh EXPLAIN plans.
- Kiểm tra collation/index validity.
- Kiểm tra cache warm-up và I/O.
- Xem wait events, locks, temp files, WAL và connection counts.
- Thay đổi có kiểm soát, giữ baseline và rollback nếu vượt budget.

### Backup/restore failure

- Không xóa backup trước upgrade.
- Kiểm tra backup tool version, manifest, WAL coverage và credentials.
- Tạo backup mới sau khi xử lý lỗi.
- Thử restore trên target cô lập.
- Ghi nhận RPO/RTO thực tế.
- Escalate nếu không chứng minh được recovery path.

### Replication failure

- Kiểm tra primary/standby version và topology.
- Xem receiver/sender state, slots và WAL availability.
- Kiểm tra HBA/TLS/network.
- Kiểm tra extension/replication compatibility.
- Rebuild standby nếu WAL không còn đủ, theo runbook.
- Xác minh HA manager leader state.

## 39. Rollback sau upgrade

Rollback plan phải được thiết kế trước khi nâng cấp. Khả năng rollback phụ thuộc phương pháp:

- Minor update: thường có thể quay lại package/binary cũ theo quy trình hỗ trợ, nhưng phải xem có thay đổi catalog/data không và không khởi động binary cũ với data state không tương thích.
- pg_upgrade copy mode: old cluster có thể còn nguyên để khởi động lại nếu new cluster chưa làm thay đổi external dependencies hoặc data routing; vẫn cần kiểm soát writes.
- pg_upgrade link mode: sau khi new cluster bắt đầu ghi, old cluster không còn là rollback copy độc lập.
- Dump/restore: rollback có thể chuyển app về source nếu source còn nguyên và chưa có writes mới ở target; nếu target đã nhận writes, cần reverse sync/reconciliation.
- Logical replication: rollback phụ thuộc việc giữ source, hướng đồng bộ ngược và cutover writes.

Không chỉ đổi DNS về server cũ. Nếu target đã nhận transaction mới, việc quay về có thể mất dữ liệu. Runbook phải xác định data divergence và recovery strategy.

## 40. Bằng chứng sau nâng cấp

Evidence package nên có:

- Change ID, runbook version và operator.
- Source/target PostgreSQL versions.
- Upgrade method và tool versions.
- Start/end timestamps và timezone.
- Cluster/database identity.
- Extension inventory.
- Object/schema inventory.
- Data reconciliation results.
- Index/constraint/sequence checks.
- Role/membership/grants/RLS checks.
- Collation check và REINDEX evidence nếu cần.
- Configuration diff và pending_restart.
- Analyze completion.
- Query plan/performance comparison.
- Replication/HA status.
- WAL archive status.
- New backup ID/manifest.
- Restore test output.
- Application smoke tests.
- Monitoring snapshots.
- Deviations, exceptions và approvals.
- Reviewer sign-off.

Không đưa passwords, tokens, private keys hoặc query parameters nhạy cảm vào evidence. Redact dữ liệu cần thiết nhưng giữ timestamp, environment, object name và SQLSTATE để có thể điều tra.

## 41. Runbook mẫu: post-upgrade verification

~~~text
RUNBOOK: PostgreSQL Post-Upgrade Verification

A. IDENTIFY
   - Change ID:
   - Environment:
   - Cluster / endpoint:
   - Source version:
   - Target version:
   - Upgrade method:
   - Operator / verifier:

B. PRE-UPGRADE BASELINE
   - Database inventory:
   - Extensions:
   - Object inventory:
   - Data checks:
   - Roles / grants:
   - Query latency / throughput:
   - Replication / slots:
   - Backup ID / restore point:

C. POST-UPGRADE PLATFORM
   - Server version:
   - Client tools:
   - Cluster identity:
   - Startup logs:
   - Effective configuration:
   - Extension binaries and SQL versions:

D. DATA AND OBJECTS
   - Schema/object inventory:
   - Invalid indexes:
   - Unvalidated constraints:
   - Sequence state:
   - Large objects:
   - Row counts / aggregates / checksums:

E. SECURITY
   - Roles / memberships:
   - Ownership / grants:
   - Default privileges:
   - RLS / policies:
   - HBA / TLS:
   - Security definer routines:

F. PERFORMANCE
   - Analyze completed:
   - Query plan comparison:
   - Latency / throughput:
   - CPU / memory / I/O:
   - Temp files / locks / deadlocks:

G. HA AND BACKUP
   - Replication:
   - Slots / subscriptions:
   - WAL archive:
   - New backup:
   - Restore test:
   - RPO / RTO evidence:

H. APPLICATION
   - Driver / connection:
   - Read smoke test:
   - Write smoke test:
   - Critical workflows:
   - Error rate / latency:
   - Monitoring and alerts:

I. DECISION
   - Acceptance criteria:
   - Exceptions:
   - Rollback/recovery decision:
   - Reviewer:
   - Closure timestamp:
~~~

## 42. Bảng SQL xác minh nhanh

| Mục tiêu | Query hoặc công cụ |
| --- | --- |
| Server version | version(), SHOW server_version |
| Cluster role | pg_is_in_recovery() |
| Startup time | pg_postmaster_start_time() |
| Database inventory | pg_database |
| Extensions | pg_extension, pg_available_extensions |
| Table inventory | pg_tables |
| Index definitions | pg_indexes |
| Invalid indexes | pg_index |
| Constraints | pg_constraint |
| Sequences | pg_sequences |
| Large objects | pg_largeobject_metadata |
| Roles | pg_roles |
| Memberships | pg_auth_members |
| Table grants | information_schema.role_table_grants |
| Effective privileges | has_database_privilege(), has_schema_privilege(), has_table_privilege() |
| Default privileges | pg_default_acl |
| RLS policies | pg_policies |
| HBA parsing | pg_hba_file_rules |
| Effective config | pg_settings |
| Config errors | pg_file_settings |
| Collation | pg_database, pg_collation |
| Table statistics | pg_stat_user_tables |
| Query statistics | pg_stat_statements |
| Current sessions | pg_stat_activity |
| Locks | pg_locks, pg_blocking_pids() |
| Replication | pg_stat_replication |
| WAL receiver | pg_stat_wal_receiver |
| Replication slots | pg_replication_slots |
| WAL archive | pg_stat_archiver |
| Vacuum progress | pg_stat_progress_vacuum |

Các views và columns có thể thay đổi theo major version. Kiểm tra schema thực tế trước khi dùng query trong script tự động.

## 43. Những sai lầm thường gặp

1. **Coi server khởi động thành công là nâng cấp hoàn tất**, bỏ qua data, permission, performance và backup checks.
2. **Chỉ kiểm tra version qua psql client**, không xác nhận server binary và cluster endpoint.
3. **Quên cài extension binaries cho major version mới**, dẫn tới function/library load errors.
4. **Chỉ kiểm tra extension name**, không kiểm tra extversion và package/shared library.
5. **Không chạy analyze sau pg_upgrade**, khiến planner dùng statistics thiếu hoặc không đại diện.
6. **Không kiểm tra collation version**, để index có thể không còn phù hợp với sort semantics mới.
7. **Refresh collation version trước khi rebuild index**, che warning nhưng chưa sửa index.
8. **Chỉ so sánh row count**, bỏ qua nội dung, aggregates, keys và large objects.
9. **Không đồng bộ sequence state sau logical migration**, gây duplicate key khi insert.
10. **Không kiểm tra invalid indexes**, để planner bỏ qua index hoặc thao tác DML gặp vấn đề.
11. **Bỏ qua NOT VALID constraints**, không biết constraint nào chưa kiểm tra dữ liệu cũ.
12. **Chỉ kiểm tra role tồn tại**, không kiểm tra memberships, ownership, grants và default privileges.
13. **Test quyền bằng superuser**, bỏ qua RLS và least-privilege behavior của application role.
14. **Không kiểm tra SECURITY DEFINER/search_path**, tạo rủi ro quyền sau upgrade.
15. **Copy nguyên config cũ sang major version mới**, bỏ qua setting removed/renamed/default changes.
16. **Không kiểm tra driver và ORM**, để application gặp lỗi type/protocol/prepared statements.
17. **Đánh giá performance ngay sau restart**, nhầm cache warm-up với regression hoặc bỏ qua regression thật.
18. **So sánh cumulative counters mà không xét stats_reset**, dẫn tới kết luận sai.
19. **Không xác minh replication slots/subscriptions**, làm downstream consumers ngừng nhận dữ liệu.
20. **Không xác minh WAL archive sau upgrade**, mất recovery chain mới.
21. **Dùng backup cũ làm recovery plan duy nhất**, không tạo backup phù hợp cluster mới.
22. **Coi backup command thành công là restore proof**, không chạy restore test.
23. **Không giữ old cluster theo rollback policy**, hoặc hiểu sai rủi ro của pg_upgrade link mode.
24. **Đổi endpoint về source khi target đã nhận writes**, gây mất dữ liệu hoặc split-brain nghiệp vụ.
25. **Không test ứng dụng bằng role/driver thật**, chỉ test bằng psql admin.
26. **Không kiểm tra monitoring/exporter compatibility**, để dashboard mất metrics sau upgrade.
27. **Không ghi evidence và timestamp**, khiến reviewer không thể xác nhận trạng thái.
28. **Đóng change ngay sau smoke test đơn giản**, chưa quan sát replication, backup và workload peak.

## 44. Bài tập thực hành có đáp án

### Bài 1. Vì sao server start thành công chưa đủ chứng minh upgrade hoàn tất?

**Đáp án:** Vì còn phải xác minh dữ liệu, objects, quyền, extension, hiệu năng, replication, backup và application behavior.

### Bài 2. Minor update và major upgrade khác nhau thế nào?

**Đáp án:** Minor update nằm trong cùng major series; major upgrade chuyển sang major version mới và có thể thay đổi catalog/data format, planner, extensions và defaults.

### Bài 3. Query nào xác nhận server version?

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

**Đáp án:** Các lệnh trên hiển thị version của server đang kết nối.

### Bài 4. Query nào liệt kê extension đã cài?

**Đáp án:** pg_extension kết hợp pg_namespace.

### Bài 5. Vì sao phải kiểm tra shared library của extension?

**Đáp án:** Metadata extension trong database không bảo đảm binary/control files trên filesystem tương thích với major version mới.

### Bài 6. Query nào tìm index invalid?

**Đáp án:** pg_index với indisvalid = false hoặc indisready = false.

### Bài 7. convalidated = false nghĩa là gì?

**Đáp án:** Constraint chưa được validate toàn bộ dữ liệu hiện có; có thể là trạng thái được tạo có chủ đích nhưng cần kiểm tra.

### Bài 8. Vì sao phải kiểm tra sequence sau logical migration?

**Đáp án:** Sequence có thể không được logical replication đồng bộ và có thể thấp hơn key lớn nhất trong bảng.

### Bài 9. pg_largeobject_metadata dùng để kiểm tra gì?

**Đáp án:** Metadata và số lượng PostgreSQL large objects.

### Bài 10. Vì sao row count không đủ chứng minh dữ liệu đúng?

**Đáp án:** Hai bảng có cùng số rows vẫn có thể chứa giá trị khác nhau; cần aggregates/checksums/key checks.

### Bài 11. Query nào xem role attributes?

**Đáp án:** pg_roles.

### Bài 12. Vì sao phải kiểm tra default privileges?

**Đáp án:** Chúng quyết định quyền của objects được tạo trong tương lai, không chỉ objects hiện có.

### Bài 13. Vì sao test RLS bằng superuser không có giá trị xác nhận application behavior?

**Đáp án:** Superuser hoặc role BYPASSRLS có thể bỏ qua row-level security.

### Bài 14. SECURITY DEFINER function cần kiểm tra gì?

**Đáp án:** Owner, execute grants và search_path an toàn.

### Bài 15. Collation version mismatch có thể ảnh hưởng gì?

**Đáp án:** Thứ tự so sánh/sắp xếp có thể thay đổi và index dựa trên collation có thể cần rebuild.

### Bài 16. ALTER DATABASE REFRESH COLLATION VERSION có rebuild index không?

**Đáp án:** Không. Nó cập nhật metadata version; các index bị ảnh hưởng phải được xử lý riêng.

### Bài 17. Vì sao chạy analyze sau pg_upgrade?

**Đáp án:** Planner cần statistics phù hợp với cluster mới để ước lượng rows và chọn query plan tốt.

### Bài 18. vacuumdb --all --analyze-in-stages làm gì?

**Đáp án:** Analyze các database theo stages để cung cấp planner statistics cơ bản sớm rồi tăng độ chi tiết.

### Bài 19. EXPLAIN ANALYZE có thực thi query không?

**Đáp án:** Có. Với DML cần dùng staging hoặc transaction rollback phù hợp.

### Bài 20. Shared read trong EXPLAIN có chắc là physical disk read không?

**Đáp án:** Không. OS page cache có thể phục vụ page.

### Bài 21. pg_stat_statements cần điều kiện gì?

**Đáp án:** Extension cần được cài và cấu hình preload phù hợp; schema/cột phải khớp version.

### Bài 22. Vì sao cần so sánh stats_reset?

**Đáp án:** Counters có thể reset, khiến delta hoặc tổng số trước/sau không còn cùng khoảng thời gian.

### Bài 23. Query nào xác nhận node là standby?

**Đáp án:** SELECT pg_is_in_recovery(); true nghĩa là đang recovery/standby.

### Bài 24. pg_stat_replication xem từ node nào?

**Đáp án:** Trên primary, để xem các standby đang kết nối.

### Bài 25. Logical replication có tự đồng bộ sequence và DDL không?

**Đáp án:** Không mặc định. Sequence và DDL cần quy trình riêng.

### Bài 26. pg_stat_archiver chứng minh điều gì?

**Đáp án:** Thống kê hoạt động WAL archiving, bao gồm archive successes và failures.

### Bài 27. Vì sao phải tạo backup mới sau major upgrade?

**Đáp án:** Cần recovery artifact phù hợp với cluster/version mới và WAL archive sau thời điểm nâng cấp.

### Bài 28. Backup command exit code 0 có chứng minh restore được không?

**Đáp án:** Không. Cần validate metadata và thực hiện restore test.

### Bài 29. Vì sao pg_upgrade link mode ảnh hưởng rollback?

**Đáp án:** New và old cluster có thể dùng chung inode qua hard links; sau khi cluster mới ghi, old cluster không còn là bản độc lập nguyên vẹn.

### Bài 30. Khi nào được đóng change?

**Đáp án:** Khi mọi acceptance criteria quan trọng đạt, application/monitoring ổn định, replication/backup được xác minh, evidence đủ và reviewer sign-off.

## 45. Checklist xác minh sau nâng cấp

### Platform và version

- [ ] Xác nhận đúng cluster, endpoint, database và node.
- [ ] Xác nhận server major/minor version.
- [ ] Xác nhận binary/service path và client tools.
- [ ] Kiểm tra startup time và startup logs.
- [ ] Kiểm tra configuration errors và pending_restart.
- [ ] Review parameter defaults/removed settings theo release notes.

### Extensions và objects

- [ ] Đối chiếu extension name/version/schema/owner.
- [ ] Cài đúng extension binaries và control files.
- [ ] Xác nhận preload libraries.
- [ ] Đối chiếu databases, schemas, tables, views, functions và triggers.
- [ ] Kiểm tra partition inventory.
- [ ] Tìm invalid indexes.
- [ ] Kiểm tra constraints và convalidated.
- [ ] Kiểm tra sequences/identity state.
- [ ] Kiểm tra large objects.
- [ ] Kiểm tra tablespaces và external dependencies.

### Data integrity

- [ ] Dùng snapshot/watermark nhất quán khi so sánh.
- [ ] Đối chiếu row counts theo table/partition.
- [ ] Đối chiếu min/max keys và timestamps.
- [ ] So sánh aggregates/checksums cho dữ liệu quan trọng.
- [ ] Kiểm tra duplicate/null/range constraints.
- [ ] Kiểm tra referential integrity.
- [ ] Kiểm tra sequence state sau logical migration.
- [ ] Ghi nhận mọi exception.

### Permissions và security

- [ ] Đối chiếu roles và attributes.
- [ ] Đối chiếu role memberships.
- [ ] Đối chiếu database/schema/table/sequence/function grants.
- [ ] Kiểm tra ownership.
- [ ] Kiểm tra default privileges.
- [ ] Kiểm tra RLS policies và FORCE RLS.
- [ ] Kiểm tra SECURITY DEFINER routines/search_path.
- [ ] Kiểm tra pg_hba_file_rules.
- [ ] Test TLS/authentication bằng application role.
- [ ] Không đưa secrets vào evidence.

### Performance và application

- [ ] Chạy analyze theo kế hoạch.
- [ ] Kiểm tra statistics của bảng quan trọng.
- [ ] So sánh EXPLAIN plans.
- [ ] So sánh latency/throughput/error rate với baseline.
- [ ] Đánh giá cache warm-up và observation window.
- [ ] Kiểm tra temp files, locks, deadlocks và I/O.
- [ ] Test bằng đúng driver/ORM/service role.
- [ ] Chạy read/write/transaction smoke tests.
- [ ] Kiểm tra scheduled jobs, workers và integrations.
- [ ] Xác minh monitoring/exporter/dashboard/alerts.

### HA và backup

- [ ] Xác minh primary/standby role.
- [ ] Xác minh streaming replication và lag.
- [ ] Kiểm tra replication slots và subscriptions.
- [ ] Kiểm tra WAL archiving sau upgrade.
- [ ] Tạo backup mới phù hợp cluster mới.
- [ ] Validate manifest/checksum.
- [ ] Thực hiện restore test trên môi trường cô lập.
- [ ] Ghi RPO/RTO thực tế.
- [ ] Giữ backup/old cluster theo rollback policy.
- [ ] Xác minh backup schedule và alert tiếp tục hoạt động.

### Closure

- [ ] Tất cả acceptance criteria đạt.
- [ ] Không còn unknown state quan trọng.
- [ ] Deviations và risks được ghi nhận.
- [ ] Evidence package có context/timestamp/source.
- [ ] Reviewer và application owner sign-off.
- [ ] Rollback window được quản lý rõ.
- [ ] Runbook và inventory được cập nhật.
- [ ] Change được đóng đúng trạng thái.

## 46. Tài liệu PostgreSQL chính thức

Đọc tài liệu đúng major version nguồn và đích:

- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html) — tổng quan các phương pháp nâng cấp.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — kiểm tra, nâng cấp cluster và các mode copy/link.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — chiến lược backup/restore.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — logical dump.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — restore archive.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — physical base backup.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity, pg_stat_replication, pg_stat_wal và các statistics views.
- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — database metadata.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — roles và membership.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — ownership và object privileges.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS và policy behavior.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — locale, provider và collation versions.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — ANALYZE và planner statistics.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — query plans và execution metrics.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publication/subscription và replication limitations.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — WAL archive và point-in-time recovery.
- [Extension Packaging](https://www.postgresql.org/docs/current/extend-extensions.html) — extension control files và versioning.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Hành vi pg_upgrade, system catalogs, statistics views, collation support, extension compatibility và backup tools thay đổi theo major version. Kiểm tra tài liệu của cả source và target version trước khi thực hiện.

## 47. Tổng kết

**Nâng cấp chỉ hoàn tất khi dữ liệu, quyền, hiệu năng, HA, backup và ứng dụng đều được xác minh bằng bằng chứng có thể kiểm tra lại.** Việc server khởi động hoặc lệnh upgrade thành công chỉ là điểm bắt đầu của post-upgrade verification.

1. **Phân biệt minor update và major upgrade.** Mỗi upgrade method có các rủi ro và bằng chứng riêng.
2. **Xác nhận đúng server, binary, cluster và database.** Không dựa riêng vào client version hoặc endpoint alias.
3. **Kiểm tra extension binaries và SQL versions.** Metadata extension không bảo đảm shared libraries tương thích.
4. **Đối chiếu objects, indexes, constraints, sequences và large objects.** Đặc biệt kiểm tra invalid indexes và sequence state.
5. **Đối chiếu dữ liệu theo snapshot/watermark nhất quán.** Row count đơn lẻ không chứng minh dữ liệu giống nhau.
6. **Xác minh roles, memberships, ownership, grants và default privileges.** Test bằng application roles và kiểm tra RLS.
7. **Kiểm tra collation version.** Rebuild index bị ảnh hưởng trước khi refresh recorded version.
8. **Chạy analyze và so sánh query plans.** Statistics cũ/thiếu có thể gây performance regression.
9. **Đánh giá application compatibility.** Driver, ORM, TLS, prepared statements và background jobs đều cần smoke tests.
10. **Xác minh replication, slots, subscriptions và WAL archive.** Không giả định mọi logical replication state tự chuyển.
11. **Tạo backup mới và thực hiện restore test.** Backup command thành công chưa chứng minh recovery path.
12. **Giữ rollback path đúng với upgrade method.** Đặc biệt hiểu rủi ro của pg_upgrade link mode và writes sau cutover.
13. **Lưu evidence có timestamp, context và source.** Chỉ đóng change khi acceptance criteria và reviewer sign-off hoàn tất.

Một quy trình post-upgrade tốt biến việc nâng cấp thành một thay đổi có thể chứng minh: biết chính xác cluster đang chạy gì, dữ liệu và quyền có còn đúng không, ứng dụng có giữ được hiệu năng không và đội vận hành có thể phục hồi cluster mới khi cần hay không.
