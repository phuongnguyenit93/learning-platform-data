# Kiểm kê extension, kiểu dữ liệu và công cụ phụ thuộc khi nâng cấp PostgreSQL

Nâng cấp PostgreSQL, đặc biệt là nâng cấp major version, không chỉ là cài binary server mới rồi khởi động database. Một cluster có thể phụ thuộc vào extension, shared libraries, custom data types, collations, foreign data wrappers, procedural languages, event triggers, client drivers, backup tools, monitoring agents và các chương trình vận hành bên ngoài. Nếu một dependency không có bản tương thích trên target version, database có thể không khởi động, extension không load được, query đổi kết quả hoặc ứng dụng không kết nối được sau cutover.

Trước khi nâng cấp, cần lập một **inventory có thể kiểm chứng**. Inventory phải trả lời được:

- Cluster đang cài extension nào, phiên bản nào và extension nào chỉ có trên host nhưng chưa được cài trong database?
- Extension nào cần shared library, package hệ điều hành, preload hoặc dịch vụ ngoài?
- Database có những kiểu dữ liệu do người dùng hoặc extension định nghĩa nào?
- Có enum, domain, composite, range, multirange, collation hoặc cast/operator đặc biệt nào?
- Những object nào phụ thuộc extension và những extension nào phụ thuộc extension khác?
- Có function viết bằng C, procedural language, FDW, event trigger hoặc background worker nào cần binary bên ngoài?
- Công cụ nào đọc/ghi cluster: pg_upgrade, pg_dump, pg_restore, backup agent, pooler, driver, ORM, CDC, monitoring, HA manager và scheduler?
- Mỗi dependency có tương thích với source version, target version, OS, architecture và cách triển khai hay không?

Inventory tốt kết hợp catalog queries trong PostgreSQL với package manifests, filesystem, deployment manifests và xác nhận từ owner của từng ứng dụng. Catalog chỉ mô tả những gì database biết; nó không thể tự liệt kê mọi thư viện hoặc executable nằm ngoài server.

~~~text
                PostgreSQL source cluster
                         |
       +-----------------+------------------+
       |                 |                  |
       v                 v                  v
    Extensions       Data types          Database objects
       |                 |                  |
       +-----------------+------------------+
                         |
                         v
                Dependency graph
                         |
       +-----------------+------------------+
       |                 |                  |
       v                 v                  v
   Server/OS         Client/tools       External services
   libraries         drivers/agents     FDW/CDC/HA/ETL
       |                 |                  |
       +-----------------+------------------+
                         |
                         v
             Compatibility matrix + rehearsal
                         |
                         v
                 Upgrade / rollback plan
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Nâng cấp**, với đề tài **“Kiểm kê extension, kiểu dữ liệu và công cụ phụ thuộc”**. Trọng tâm là xây dựng inventory trước upgrade, xác định dependency và compatibility, rồi biến kết quả thành kế hoạch kiểm thử và cutover có thể thực hiện.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao phải kiểm kê dependency trước khi nâng cấp major version.
2. Phân biệt PostgreSQL core object, extension object và external dependency.
3. Liệt kê extension đã cài bằng pg_extension.
4. Phân biệt installed extension với extension package có sẵn trên server.
5. Tra cứu default_version, installed_version, requires và relocatable.
6. Xem extension update path và xác định extension có đường nâng cấp hay không.
7. Liệt kê object thuộc extension qua pg_depend.
8. Kiểm tra shared_preload_libraries và các preload requirements.
9. Kiểm kê user-defined base types, domains, enums, composites, ranges và multiranges.
10. Tra cứu casts, operators, operator classes, access methods và collations.
11. Xác định C-language functions và thư viện chúng cần.
12. Kiểm kê procedural languages, FDW, foreign servers và user mappings.
13. Kiểm tra event triggers, publications, subscriptions và logical replication dependencies.
14. Phân biệt catalog inventory với package/filesystem inventory.
15. Kiểm kê client tools, drivers, ORMs, poolers và operational agents.
16. Xây dựng compatibility matrix cho source/target versions và OS/architecture.
17. Hiểu các khác biệt giữa pg_upgrade và dump/restore đối với extension/data types.
18. Xây dựng pre-upgrade checklist và dependency owner list.
19. Diễn tập upgrade trong môi trường staging với cùng dependency set.
20. Xử lý extension update, library replacement và post-upgrade validation.
21. Ghi nhận rủi ro, rollback requirements và điều kiện cutover.
22. Tránh các lỗi phổ biến như thiếu package, sai library path, collation drift hoặc client driver cũ.

**Phạm vi:** PostgreSQL hiện đại, chủ yếu là major-version upgrade. Catalog columns, extension packaging và công cụ có thể khác theo version, OS, distribution và managed service. Các query inventory nên được chạy trên đúng từng database và được đối chiếu với tài liệu của target major version.

---

## 2. Vì sao inventory là bước bắt buộc?

### 2.1. Database không chỉ gồm table và index

Một ứng dụng PostgreSQL có thể phụ thuộc vào:
- Extension cung cấp function, type, operator hoặc index access method.
- Shared library được load bởi server.
- Custom type và casts.
- Collation của libc hoặc ICU.
- Procedural language như PL/Perl, PL/Python hoặc PL/v8.
- Foreign data wrapper kết nối hệ thống khác.
- Event triggers và background workers.
- Client driver, ORM, migration tool và connection pooler.
- Backup, monitoring, HA và CDC tools.

### 2.2. Upgrade thay đổi binary interface và catalog behavior

Major version có thể thay đổi server ABI, catalog schema, planner/executor behavior, SQL features, data format assumptions hoặc extension API. Một C extension được compile cho major version cũ thường cần binary build tương thích target version.

### 2.3. Extension có thể cài trong database nhưng package thiếu trên target

pg_extension ghi nhận extension đã được CREATE EXTENSION trong database. Nó không chứng minh file control, SQL scripts hoặc shared library đã được cài trên server target.

### 2.4. Package có thể có trên server nhưng chưa được database dùng

pg_available_extensions cho biết các extension package mà PostgreSQL instance nhìn thấy. Một extension có thể chưa được cài vào database nào, nhưng ứng dụng dự kiến bật nó sau upgrade.

### 2.5. Một dependency thiếu có thể chỉ lộ ra khi khởi động hoặc chạy query

Ví dụ:
- Server không load được library trong shared_preload_libraries.
- CREATE EXTENSION hoặc ALTER EXTENSION UPDATE thất bại do thiếu control/SQL script.
- Function C gọi library không tồn tại.
- Collation version thay đổi làm index cần rebuild.
- Driver không hiểu protocol/authentication behavior.
- Backup agent không hỗ trợ target major version.

### 2.6. Inventory cần có owner

Mỗi dependency nên có:
- Tên và version.
- Nơi được dùng.
- Owner/đội chịu trách nhiệm.
- Target compatibility evidence.
- Hành động upgrade.
- Cách kiểm thử.
- Rollback/restore plan.

Không có owner thì một dependency ít dùng nhưng quan trọng có thể bị bỏ sót.

---

## 3. Phạm vi inventory: những lớp cần kiểm tra

| Lớp | Ví dụ | Nguồn inventory |
| --- | --- | --- |
| Extensions | PostGIS, pg_stat_statements, pg_cron | pg_extension, pg_available_extensions |
| Extension binaries | .so, .dll, shared libraries | pg_config, package manager, filesystem |
| Data types | enum, domain, composite, range | pg_type, pg_enum, pg_range |
| Functions | SQL, PL/pgSQL, C | pg_proc, pg_language |
| Operators/casts | custom operators, casts | pg_operator, pg_cast |
| Collations | libc, ICU | pg_collation |
| Index dependencies | opclass, access method | pg_opclass, pg_am |
| FDW | postgres_fdw, file_fdw | pg_foreign_data_wrapper |
| External connections | servers, user mappings | pg_foreign_server, pg_user_mapping |
| Triggers | event triggers | pg_event_trigger |
| Replication | publications, subscriptions | pg_publication, pg_subscription |
| Server settings | preload libraries, custom GUCs | pg_settings, config files |
| Client stack | libpq, JDBC, Npgsql, psycopg | application manifests |
| Operational tools | pg_upgrade, dump/restore, backup agent | hosts, CI/CD, runbooks |
| Infrastructure | OS, architecture, libc, ICU | host/package inventory |

Inventory phải bao phủ **mọi database trong cluster**. Extensions được cài theo từng database, trong khi package binaries thường được cài ở mức server/host.

---

## 4. Xác định source và target environment

Trước khi kiểm tra dependency, ghi rõ môi trường đang nâng cấp.

### 4.1. Source cluster

Thu thập:
- PostgreSQL major/minor version.
- OS distribution/version.
- CPU architecture.
- Package source và build flags.
- Data directory, tablespaces và storage layout.
- Encoding, locale, collation provider.
- Installed extensions và versions.
- Server configuration và preload settings.
- Replication topology và external integrations.

### 4.2. Target cluster

Ghi tương ứng:
- Target PostgreSQL major/minor version.
- Target OS và architecture.
- Extension package repositories.
- Shared library paths.
- libc/ICU versions.
- Client/driver versions được hỗ trợ.
- Backup/restore tool versions.
- HA/monitoring/CDC compatibility.

### 4.3. Major upgrade khác minor update

Minor update trong cùng major version thường duy trì compatibility tốt hơn, nhưng vẫn cần xem release notes và extension packaging. Major upgrade thường cần kiểm tra ABI, catalog changes, extension update scripts và migration path.

### 4.4. Managed PostgreSQL

Với managed service, provider kiểm soát server packages và upgrade process. Inventory vẫn cần xác định extension allowlist, supported versions, parameter groups, drivers, backup/restore behavior và giới hạn dịch vụ.

---

## 5. Liệt kê extension đã cài trong database

Extension là tập hợp database objects được quản lý như một đơn vị qua CREATE EXTENSION, ALTER EXTENSION và DROP EXTENSION.

### 5.1. Xem extensions đã cài

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    pg_catalog.pg_get_userbyid(e.extowner) AS extension_owner,
    e.extrelocatable
FROM pg_catalog.pg_extension AS e
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Chạy query trong từng database cần nâng cấp. Một cluster có thể có extension set khác nhau giữa các databases.

### 5.2. Ý nghĩa các cột

| Cột | Ý nghĩa |
| --- | --- |
| extname | Tên extension |
| extversion | Version SQL extension đang được cài |
| extension_schema | Schema chứa các objects thuộc extension |
| extension_owner | Role sở hữu extension |
| extrelocatable | Extension có thể chuyển schema theo metadata hay không |

### 5.3. Không chỉ ghi tên extension

Version là thông tin bắt buộc. Cùng tên extension có thể có SQL objects và binary khác nhau giữa các versions.

### 5.4. Extension owner

Owner có thể cần quyền thực hiện ALTER EXTENSION UPDATE hoặc các bước migration. Ghi lại role và cách cấp quyền trên target.

### 5.5. Extension theo từng database

Có thể lặp query qua từng database bằng automation có kiểm soát. Không dùng một kết quả của database mặc định để đại diện toàn cluster.

---

## 6. Phân biệt extension đã cài và package có sẵn

### 6.1. Extension packages có sẵn

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_catalog.pg_available_extensions
ORDER BY name;
~~~

View này phản ánh extension control files mà PostgreSQL server đang nhìn thấy.

### 6.2. Các version package có sẵn

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires,
    comment
FROM pg_catalog.pg_available_extension_versions
ORDER BY name, version;
~~~

### 6.3. Diễn giải

- installed_version khác NULL: extension đang được cài trong database hiện tại.
- default_version: version mà CREATE EXTENSION không chỉ định version thường chọn.
- version: các extension versions mà server package cung cấp.
- requires: các extension dependencies khai báo trong control metadata.
- trusted/superuser: thông tin về yêu cầu quyền cài đặt theo package metadata.
- relocatable/schema: metadata về schema placement.

### 6.4. Có package không đồng nghĩa đã cài

pg_available_extensions chỉ cho biết server nhìn thấy package. Nó không có nghĩa extension đang được database sử dụng.

### 6.5. Đã cài không đồng nghĩa có package target

Source database có thể ghi nhận extversion, nhưng target host vẫn cần package version và shared library phù hợp để load/upgrade.

### 6.6. Kiểm tra extension được cài nhưng không có default package

Nếu installed_version có giá trị nhưng target package không cung cấp version đó, cần xác định upgrade path và nguồn package. Không tự giả định extension đã bị bỏ hoặc không còn dùng.

---

## 7. Kiểm tra extension update path

Một extension muốn chuyển từ version hiện tại sang version mới thường cần update script path phù hợp.

### 7.1. Xem update paths

Trên các version hỗ trợ function này:

~~~sql
SELECT *
FROM pg_catalog.pg_extension_update_paths('postgis');
~~~

Thay tên extension bằng extension cần kiểm tra. Xác nhận function và output schema trên server version cụ thể.

### 7.2. Ý nghĩa update path

Một path biểu diễn chuỗi update scripts có thể đưa extension từ source version tới target version. Có thể cần qua nhiều version trung gian nếu package không có script trực tiếp.

### 7.3. Không có path

Nếu không có update path, ALTER EXTENSION UPDATE trực tiếp có thể không thực hiện được. Cần xem hướng dẫn vendor, intermediate releases, dump/restore hoặc migration procedure riêng.

### 7.4. Extension version không phải PostgreSQL version

Ví dụ extension version 3.4.2 không có nghĩa server version 3.4.2. Ghi riêng server major version và extension extversion.

### 7.5. Update script có thể thay đổi schema/data

Extension update có thể:
- Tạo/drop/alter objects.
- Rebuild metadata.
- Chuyển đổi internal data.
- Thay function signatures.
- Yêu cầu maintenance window.
- Cần quyền owner/superuser.

Đọc release notes và test trên bản clone trước khi chạy production.

### 7.6. Extension có pre-upgrade và post-upgrade steps

Một số extensions yêu cầu chạy script trước pg_upgrade hoặc sau upgrade. Không bỏ qua tài liệu của extension vendor.

---

## 8. Kiểm kê objects thuộc extension

Extension membership được ghi trong pg_depend với dependency type tương ứng.

### 8.1. Đếm objects theo extension

~~~sql
SELECT
    e.extname,
    count(*) AS member_objects
FROM pg_catalog.pg_depend AS d
JOIN pg_catalog.pg_extension AS e
    ON d.refclassid = 'pg_catalog.pg_extension'::regclass
   AND d.refobjid = e.oid
WHERE d.deptype = 'e'
GROUP BY e.extname
ORDER BY member_objects DESC;
~~~

### 8.2. Liệt kê object descriptions

~~~sql
SELECT
    e.extname,
    pg_catalog.pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS extension_object
FROM pg_catalog.pg_depend AS d
JOIN pg_catalog.pg_extension AS e
    ON d.refclassid = 'pg_catalog.pg_extension'::regclass
   AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, extension_object;
~~~

### 8.3. Vì sao cần inventory object members?

Biết extension có bao nhiêu objects giúp hiểu phạm vi thay đổi và phát hiện objects thuộc extension mà ứng dụng đang dùng. Tuy nhiên, số lượng object không cho biết mức độ quan trọng.

### 8.4. Object dependency ngoài extension membership

Một object do extension tạo có thể được ứng dụng tham chiếu bởi view, function, column type hoặc index. Cần xem dependencies theo cả hai hướng và xác nhận với application schema.

### 8.5. Không sửa trực tiếp extension-owned objects

Nếu object thuộc extension, thay đổi thủ công có thể làm lệch metadata hoặc khiến ALTER EXTENSION UPDATE thất bại. Dùng extension-supported configuration/API và migration scripts.

---

## 9. Extension phụ thuộc extension khác

Một extension có thể khai báo requires trong control file. Khi cài, PostgreSQL có thể cài dependency theo metadata.

### 9.1. Xem requires

~~~sql
SELECT
    name,
    version,
    requires
FROM pg_catalog.pg_available_extension_versions
WHERE requires IS NOT NULL
ORDER BY name, version;
~~~

### 9.2. Dependency chain

Ví dụ extension A cần extension B; extension B có thể cần extension C. Inventory phải giữ dependency chain thay vì chỉ liệt kê A.

### 9.3. Thứ tự upgrade

Vendor có thể quy định extension dependency cần được nâng cấp trước. Không suy luận thứ tự chỉ từ tên extension; xem control metadata, update scripts và release notes.

### 9.4. Optional dependencies

Một số extension integration chỉ cần khi feature cụ thể được bật. Ghi trạng thái thực tế: required, optional, installed-but-unused hoặc unknown.

### 9.5. Extension được dùng qua SQL object

Extension có thể đã được cài nhưng không còn query gọi trực tiếp. Có thể vẫn được tham chiếu bởi views, triggers, indexes hoặc functions; kiểm tra dependency trước khi đánh dấu unused.

---

## 10. Kiểm kê user-defined data types

PostgreSQL cho phép tạo kiểu dữ liệu tùy chỉnh. Extension cũng có thể tạo type. Một type có thể xuất hiện trong table columns, function signatures, arrays, casts, indexes và serialized data.

### 10.1. Xem user-defined types

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype,
    t.typcategory,
    t.typisdefined,
    t.typbyval,
    t.typlen,
    t.typalign,
    t.typstorage,
    t.typnamespace::regnamespace AS type_schema
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND t.typisdefined
ORDER BY n.nspname, t.typname;
~~~

### 10.2. typtype thường gặp

| Code | Loại |
| --- | --- |
| b | Base type |
| c | Composite type |
| d | Domain |
| e | Enum |
| m | Multirange |
| p | Pseudo-type |
| r | Range |

Một số loại đặc biệt có thể phụ thuộc version. Type system còn có array types được PostgreSQL tạo tự động.

### 10.3. typcategory

typcategory là nhóm phân loại type ở mức parser/type system, hữu ích khi phân tích behavior. Không thay thế typtype.

### 10.4. typbyval và typlen

Các trường mô tả cách value được lưu/truyền ở mức nội bộ. Đây là chi tiết quan trọng với C extensions/custom base types và binary compatibility.

### 10.5. typstorage

Đối với varlena types, typstorage mô tả storage strategy. Các thay đổi implementation cần được xử lý theo binary format và extension upgrade rules.

### 10.6. Type names có thể trùng schema

Không chỉ lưu typname. Cần lưu schema, owner, extension membership và các columns/functions phụ thuộc.

---

## 11. Kiểm kê columns đang dùng custom types

### 11.1. Tìm columns dùng user-defined types

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    udt_schema,
    udt_name,
    data_type
FROM information_schema.columns
WHERE udt_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

### 11.2. Kết hợp table metadata

Có thể join pg_attribute, pg_class, pg_namespace và pg_type để lấy relation kind, nullability, typmod và column details mà information_schema không thể hiện hết.

### 11.3. Partitioned tables

Kiểm tra cả parent và partitions. Type ở parent có thể được kế thừa xuống partition columns, nhưng inventory physical relations vẫn cần ghi rõ.

### 11.4. Function arguments và returns

Custom types có thể chỉ xuất hiện trong function signatures, không xuất hiện trong table columns. Kiểm kê pg_proc cũng cần thiết.

### 11.5. Views và materialized views

Views có output columns mang type cụ thể. Materialized views lưu dữ liệu vật lý; cần kiểm tra dependency và refresh behavior sau upgrade.

---

## 12. Enum types

Enum là type với tập labels được định nghĩa và có thứ tự.

### 12.1. Liệt kê enum labels

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS enum_type,
    e.enumsortorder,
    e.enumlabel
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_catalog.pg_enum AS e
    ON e.enumtypid = t.oid
ORDER BY n.nspname, t.typname, e.enumsortorder;
~~~

### 12.2. Vì sao enum quan trọng khi upgrade?

Enum labels có thể được lưu trong table data, function logic và application code. Một migration cần bảo toàn labels và ordering semantics.

### 12.3. Enum ordering

Enum comparison theo enum sort order, không phải lexical order của label. Ứng dụng có thể dựa vào thứ tự đó trong ORDER BY hoặc range comparisons.

### 12.4. Thêm label

ALTER TYPE ... ADD VALUE có semantics và transactional restrictions phụ thuộc PostgreSQL version. Kiểm tra migration scripts nếu upgrade đi kèm thay đổi enum.

### 12.5. Xóa hoặc đổi label

PostgreSQL không cung cấp thao tác đơn giản để xóa enum label hiện có. Thường cần tạo type mới, cast/migrate columns và thay dependencies. Đừng coi enum labels là chuỗi tự do.

---

## 13. Domain types

Domain là type dựa trên một base type, có thể thêm NOT NULL và CHECK constraints.

### 13.1. Liệt kê domains

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS domain_name,
    bt.typname AS base_type,
    t.typnotnull,
    t.typdefault
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_catalog.pg_type AS bt
    ON bt.oid = t.typbasetype
WHERE t.typtype = 'd'
ORDER BY n.nspname, t.typname;
~~~

### 13.2. Domain constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS domain_name,
    c.conname,
    pg_catalog.pg_get_constraintdef(c.oid) AS constraint_definition,
    c.convalidated
FROM pg_catalog.pg_constraint AS c
JOIN pg_catalog.pg_type AS t
    ON t.oid = c.contypid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE c.contypid <> 0
ORDER BY n.nspname, t.typname, c.conname;
~~~

### 13.3. Upgrade considerations

- Domain base type có được hỗ trợ trên target không?
- Constraint expressions có gọi extension functions không?
- Constraint có được validate không?
- Default expression có phụ thuộc function/operator custom không?
- Applications có serialize domain values theo format riêng không?

### 13.4. Domain không chỉ là alias

Domain có constraint semantics. Nếu dump/restore hoặc migration làm mất constraint/default, behavior ứng dụng có thể thay đổi.

---

## 14. Composite types

Composite type mô tả một cấu trúc gồm nhiều fields, có thể được tạo bởi CREATE TYPE AS hoặc tự sinh cho table row type.

### 14.1. Liệt kê composite types

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS composite_type,
    a.attnum,
    a.attname AS attribute_name,
    format_type(a.atttypid, a.atttypmod) AS attribute_type,
    a.attnotnull
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_catalog.pg_class AS c
    ON c.oid = t.typrelid
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE t.typtype = 'c'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY n.nspname, t.typname, a.attnum;
~~~

### 14.2. Table row types

Mỗi table có row type tương ứng. Query trên có thể trả về nhiều table row types; khi cần custom composites độc lập, phân biệt relation kind và type ownership.

### 14.3. Dependencies

Composite types có thể được dùng trong function return types, parameters, table columns và arrays. Kiểm tra các dependency và clients consume result shapes.

### 14.4. Binary/API compatibility

Thay đổi field order/type có thể ảnh hưởng clients đọc composite records, function signatures và serialized representations.

---

## 15. Range và multirange types

Range types biểu diễn một khoảng trên subtype có ordering phù hợp. Multirange biểu diễn tập các ranges không chồng lấn theo semantics của PostgreSQL.

### 15.1. Liệt kê range types

~~~sql
SELECT
    r.rngtypid::regtype AS range_type,
    r.rngsubtype::regtype AS subtype,
    r.rngcollation::regcollation AS collation,
    r.rngcanonical::regproc AS canonical_function,
    r.rngsubdiff::regproc AS subtype_diff_function
FROM pg_catalog.pg_range AS r
ORDER BY r.rngtypid::regtype::text;
~~~

### 15.2. Multirange

Các PostgreSQL versions hỗ trợ multirange có metadata liên kết trong pg_range. Kiểm tra schema và catalog của target version.

### 15.3. Custom range types

CREATE TYPE ... AS RANGE có thể phụ thuộc subtype, collation, canonical function và subtype difference function. Tất cả các functions/types đó cần có mặt và tương thích.

### 15.4. Use cases

- Date/time intervals.
- Numeric intervals.
- Scheduling windows.
- Exclusion constraints.
- Giải quyết overlap trong dữ liệu thời gian.

### 15.5. Upgrade test

Test operators, indexes, GiST/SP-GiST opclasses, exclusion constraints và application serialization của ranges.

---

## 16. Array, pseudo-type và base types

### 16.1. Array types

PostgreSQL tự tạo array type cho nhiều base/composite types. typcategory và type naming conventions có thể giúp nhận diện, nhưng không nên dựa riêng vào tên bắt đầu bằng underscore.

### 16.2. Pseudo-types

Các type như record, anyelement, anyarray, void và trigger được dùng trong function signatures hoặc polymorphic functions. Chúng không phải data columns thông thường.

### 16.3. Custom base types

Một extension có thể định nghĩa base type với input/output, receive/send, typmod, comparison và storage functions. Những functions này có thể được viết bằng C.

### 16.4. Binary representation

Nếu custom type có binary representation riêng, extension phải hỗ trợ target server và mọi migration requirements. Không giả định dump/restore text format luôn đủ cho mọi integration hoặc binary protocol.

### 16.5. Inventory functions gắn với type

Kiểm tra pg_type input/output/receive/send/typmod functions và các operators/opclasses dùng type đó. Đây là những điểm thường bị bỏ sót khi chỉ liệt kê tên type.

---

## 17. Functions và C-language dependencies

Functions có thể được viết bằng SQL, PL/pgSQL, C hoặc procedural languages khác. C functions thường phụ thuộc shared library ngoài database.

### 17.1. Liệt kê function theo language

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    l.lanname AS language,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    pg_catalog.pg_get_function_result(p.oid) AS result_type,
    p.probin AS library_name,
    p.prosrc AS source_or_symbol
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_catalog.pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
~~~

### 17.2. Tìm C functions

~~~sql
SELECT
    n.nspname,
    p.proname,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    p.probin AS library_name,
    p.prosrc AS symbol_name
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_catalog.pg_language AS l
    ON l.oid = p.prolang
WHERE l.lanname = 'c'
ORDER BY n.nspname, p.proname;
~~~

### 17.3. probin và prosrc

Với C-language functions, probin thường chỉ library path/name và prosrc thường chỉ symbol name. Cách đóng gói có thể dùng $libdir hoặc path cụ thể.

### 17.4. Binary compatibility

C extension/library thường được build cho PostgreSQL major version cụ thể và OS/architecture cụ thể. Cần binary package tương ứng target server, không chỉ copy file .so cũ.

### 17.5. External shared library dependencies

Một .so có thể phụ thuộc libxml2, GEOS, PROJ, GDAL, OpenSSL hoặc thư viện hệ thống khác. Kiểm tra package dependencies và dynamic linker resolution trên target.

### 17.6. SQL functions cũng có dependency

SQL/PLpgSQL functions có thể gọi custom types, operators, collations, extension functions và tables. Inventory function body/dependencies khi upgrade có schema changes.

---

## 18. Procedural languages

### 18.1. Liệt kê languages

~~~sql
SELECT
    lanname,
    lanpltrusted,
    lanispl,
    lanvalidator::regproc AS validator,
    laninline::regproc AS inline_handler,
    lancompiler
FROM pg_catalog.pg_language
ORDER BY lanname;
~~~

Một số fields có thể không phù hợp hoặc khác theo version; kiểm tra schema thực tế.

### 18.2. PL/pgSQL

PL/pgSQL thường được phân phối cùng PostgreSQL. Dù vậy, test function behavior và syntax sau major upgrade.

### 18.3. PL/Python, PL/Perl, PL/Tcl và languages khác

Các languages này có thể cần package, interpreter, ABI và runtime libraries tương thích với target OS/server.

### 18.4. Trusted/untrusted

Trust status ảnh hưởng ai có thể tạo functions trong language. Không thay đổi trust model trong lúc upgrade nếu chưa đánh giá security.

### 18.5. Function dependencies

Kiểm tra functions được viết bằng language đó, modules được import và các external packages mà code gọi.

---

## 19. Collations: dependency dễ bị bỏ sót

Collation quyết định cách so sánh/sắp xếp text. Kết quả phụ thuộc provider như libc hoặc ICU và phiên bản locale data.

### 19.1. Liệt kê collations

~~~sql
SELECT
    n.nspname AS schema_name,
    c.collname,
    c.collprovider,
    c.collisdeterministic,
    c.collcollate,
    c.collctype,
    c.collversion
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.collnamespace
ORDER BY n.nspname, c.collname;
~~~

Một số cột có thể không tồn tại trên PostgreSQL cũ; khám phá schema trước khi dùng.

### 19.2. libc và ICU

- libc collation phụ thuộc locale implementation/data của OS.
- ICU collation phụ thuộc ICU library và collation rules/version.
- Provider và version có thể khác giữa source và target host.

### 19.3. Vì sao collation drift quan trọng?

Nếu sort/equality behavior thay đổi, B-tree indexes được tạo theo collation cũ có thể không còn phản ánh thứ tự hiện tại. Điều này có thể làm query trả kết quả sai hoặc index cần rebuild theo quy trình được PostgreSQL khuyến nghị.

### 19.4. Kiểm tra collation version mismatch

Trên version hỗ trợ:

~~~sql
SELECT
    n.nspname,
    c.collname,
    c.collversion,
    pg_catalog.pg_collation_actual_version(c.oid) AS actual_version
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE c.collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(c.oid)
ORDER BY n.nspname, c.collname;
~~~

### 19.5. Refresh version không rebuild index

ALTER COLLATION ... REFRESH VERSION cập nhật metadata về version provider. Nó không tự rebuild indexes phụ thuộc collation. Cần xác định dependent indexes và REINDEX theo kế hoạch.

### 19.6. Collation dependencies

Text columns, indexes, constraints, unique indexes, expression indexes và application ordering có thể phụ thuộc collation. Inventory cần bao gồm locale/provider và dependent objects.

---

## 20. Casts, operators và operator classes

Custom types thường đi kèm casts/operators và index support methods.

### 20.1. User-defined casts

~~~sql
SELECT
    s.typname AS source_type,
    t.typname AS target_type,
    c.castcontext,
    c.castmethod,
    c.castfunc::regprocedure AS cast_function
FROM pg_catalog.pg_cast AS c
JOIN pg_catalog.pg_type AS s
    ON s.oid = c.castsource
JOIN pg_catalog.pg_type AS t
    ON t.oid = c.casttarget
ORDER BY s.typname, t.typname;
~~~

Catalog có thể chứa casts built-in lẫn user-defined. Kết hợp namespace/type ownership và extension membership để phân loại.

### 20.2. User-defined operators

~~~sql
SELECT
    n.nspname AS schema_name,
    o.oprname,
    o.oprleft::regtype AS left_type,
    o.oprright::regtype AS right_type,
    o.oprcode::regprocedure AS implementation,
    o.oprrest::regprocedure AS restriction_estimator,
    o.oprjoin::regprocedure AS join_estimator
FROM pg_catalog.pg_operator AS o
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = o.oprnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, o.oprname;
~~~

### 20.3. Operator classes

~~~sql
SELECT
    n.nspname AS schema_name,
    am.amname AS access_method,
    opc.opcname,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault,
    opc.opcfamily::regclass AS operator_family
FROM pg_catalog.pg_opclass AS opc
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = opc.opcnamespace
JOIN pg_catalog.pg_am AS am
    ON am.oid = opc.opcmethod
ORDER BY n.nspname, am.amname, opc.opcname;
~~~

### 20.4. Vì sao cần kiểm kê?

Extension có thể cung cấp operators và opclasses cho GiST, GIN, SP-GiST, BRIN hoặc custom access methods. Nếu binary hoặc opclass không tương thích, index creation/query behavior có thể thất bại.

### 20.5. Indexes phụ thuộc opclass

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    am.amname AS access_method,
    opc.opcname AS operator_class
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
JOIN pg_catalog.pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_catalog.pg_am AS am
    ON am.oid = (SELECT relam FROM pg_catalog.pg_class WHERE oid = idx.oid)
JOIN LATERAL unnest(i.indclass) WITH ORDINALITY AS opco(opclass_oid, ord)
    ON true
JOIN pg_catalog.pg_opclass AS opc
    ON opc.oid = opco.opclass_oid
ORDER BY ns.nspname, tbl.relname, idx.relname, opco.ord;
~~~

Query này minh họa inventory opclasses theo index columns; với PostgreSQL versions khác nhau, cách đọc access method từ index relation có thể cần điều chỉnh. Kiểm tra query trên target/source version và phân biệt indexes dùng default opclass với custom opclass.

---

## 21. Foreign data wrappers và external connections

FDW kết nối PostgreSQL với hệ thống dữ liệu khác. Upgrade có thể cần extension package, client library, remote server compatibility và credentials.

### 21.1. Liệt kê FDWs

~~~sql
SELECT
    fdwname,
    fdwowner::regrole AS owner,
    fdwhandler::regproc AS handler,
    fdwvalidator::regproc AS validator
FROM pg_catalog.pg_foreign_data_wrapper
ORDER BY fdwname;
~~~

### 21.2. Foreign servers

~~~sql
SELECT
    s.srvname,
    f.fdwname,
    s.srvtype,
    s.srvversion,
    s.srvoptions
FROM pg_catalog.pg_foreign_server AS s
JOIN pg_catalog.pg_foreign_data_wrapper AS f
    ON f.oid = s.srvfdw
ORDER BY s.srvname;
~~~

### 21.3. User mappings

~~~sql
SELECT
    s.srvname,
    u.umuser::regrole AS local_user,
    u.umoptions
FROM pg_catalog.pg_user_mapping AS u
JOIN pg_catalog.pg_foreign_server AS s
    ON s.oid = u.umserver
ORDER BY s.srvname, local_user;
~~~

User mapping options có thể chứa credentials hoặc secret references. Không đưa raw output vào tài liệu inventory chia sẻ rộng; mask hoặc chỉ ghi presence/secret reference.

### 21.4. Foreign tables

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS foreign_table,
    s.srvname AS server_name,
    f.fdwname
FROM pg_catalog.pg_foreign_table AS ft
JOIN pg_catalog.pg_class AS c
    ON c.oid = ft.ftrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_foreign_server AS s
    ON s.oid = ft.ftserver
JOIN pg_catalog.pg_foreign_data_wrapper AS f
    ON f.oid = s.srvfdw
ORDER BY n.nspname, c.relname;
~~~

### 21.5. FDW upgrade questions

- FDW extension có package target không?
- Handler/validator functions có tồn tại?
- Client libraries và TLS dependencies tương thích?
- Remote database/service có version hoặc protocol thay đổi?
- User mappings/credentials có được migrate an toàn?
- Query pushdown và transaction semantics có thay đổi?
- Foreign table options có còn hợp lệ?

---

## 22. Event triggers và database hooks

Event triggers có thể chạy code khi xảy ra DDL events.

### 22.1. Liệt kê event triggers

~~~sql
SELECT
    evtname,
    evtevent,
    evtenabled,
    evttags,
    evtfoid::regprocedure AS trigger_function
FROM pg_catalog.pg_event_trigger
ORDER BY evtname;
~~~

### 22.2. Vì sao quan trọng?

Một event trigger có thể chạy trong CREATE/ALTER/DROP operations. Upgrade tools hoặc extension scripts thực hiện DDL có thể kích hoạt trigger và tạo side effects.

### 22.3. Kiểm tra trigger functions

Tra cứu function language, owner, source/library và dependencies. C-language event trigger functions cần shared library tương thích.

### 22.4. Extension-owned event triggers

Xác định event trigger có thuộc extension hay do application tự tạo. Thay đổi extension phải theo extension upgrade path.

### 22.5. Rehearsal

Chạy upgrade rehearsal với cùng event triggers. Quan sát DDL side effects, locks, duration và logs.

---

## 23. Publications, subscriptions và logical replication

Logical replication có catalog objects và workers riêng.

### 23.1. Publications

~~~sql
SELECT *
FROM pg_catalog.pg_publication;
~~~

### 23.2. Publication tables

~~~sql
SELECT *
FROM pg_catalog.pg_publication_tables;
~~~

### 23.3. Subscriptions

~~~sql
SELECT
    subname,
    subowner::regrole AS owner,
    subenabled,
    subslotname,
    subpublications,
    subconninfo
FROM pg_catalog.pg_subscription;
~~~

subconninfo có thể chứa thông tin nhạy cảm; chỉ kiểm tra an toàn và mask secrets trong inventory.

### 23.4. Upgrade considerations

- Source/target logical replication compatibility.
- Subscription apply worker behavior.
- Replication slots và WAL retention.
- Publication table/column filters.
- DDL/schema synchronization.
- Sequence state.
- Large objects và objects ngoài publication.
- CDC consumers và downstream schemas.

### 23.5. Không mặc định pg_upgrade chuyển mọi replication topology

Một số replication objects/slots hoặc external CDC state cần migration riêng. Đọc hướng dẫn đúng PostgreSQL version và diễn tập.

---

## 24. Server settings và preload libraries

Một số extension cần được load trước khi server nhận connections.

### 24.1. Xem shared_preload_libraries

~~~sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
SHOW local_preload_libraries;
~~~

### 24.2. Xem các settings liên quan

~~~sql
SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name LIKE '%preload%'
ORDER BY name;
~~~

### 24.3. Extension có thể yêu cầu preload

Ví dụ pg_stat_statements và một số extensions cần shared_preload_libraries. Extension có thể vẫn tồn tại trong pg_extension nhưng server startup thất bại nếu library không có hoặc không tương thích.

### 24.4. Custom GUCs

Extension có thể định nghĩa custom configuration parameters. Ghi lại setting, scope, value và file/source. Không copy parameter cũ sang target nếu extension version mới đã đổi hoặc bỏ setting.

### 24.5. Parameter files

Inventory cần gồm:
- postgresql.conf.
- included configuration files.
- postgresql.auto.conf.
- service/environment settings.
- cloud parameter groups.
- systemd/container arguments.

### 24.6. Restart requirements

shared_preload_libraries và một số settings yêu cầu restart. Lập lịch downtime/rolling procedure theo HA topology và xác minh pending_restart.

---

## 25. External binary và package inventory

Catalog không thể xác định đầy đủ package hệ điều hành hoặc dynamic libraries. Cần kiểm tra host/container image.

### 25.1. pg_config

~~~bash
pg_config --version
pg_config --sharedir
pg_config --pkglibdir
pg_config --configure
~~~

Các đường dẫn giúp tìm extension control/SQL files và shared libraries tương ứng installation.

### 25.2. Package manager

Trên Debian/Ubuntu, có thể dùng dpkg-query hoặc apt để inventory packages. Trên RHEL/Fedora, dùng rpm/dnf. Ghi package name, version, architecture và repository.

### 25.3. Dynamic library dependencies

Trên Linux, ldd có thể giúp kiểm tra shared library dependencies của extension .so. Không chạy binary không tin cậy; dùng đúng file từ package đã xác minh.

### 25.4. Container image

Ghi image digest/tag, OS base, installed packages, build arguments và extension build artifacts. Rebuild target image từ Dockerfile/lockfiles giúp tái lập environment.

### 25.5. Không copy library từ source sang target

C extension phải tương thích PostgreSQL server ABI, architecture, libc và dependent libraries. Cài package/build artifact đúng target.

### 25.6. Build toolchain

Nếu extension tự build, kiểm kê compiler, make, PostgreSQL server headers, pg_config, C/C++ libraries và source version. Build trên target environment hoặc môi trường tương thích được vendor hỗ trợ.

---

## 26. Client drivers, applications và ORM

Database server có thể nâng cấp thành công nhưng clients vẫn lỗi do driver hoặc protocol assumptions.

### 26.1. libpq

Nhiều drivers/tools dùng libpq. Kiểm tra client library version, SSL/authentication support và connection behavior.

### 26.2. JDBC

Ứng dụng Java có thể dùng PostgreSQL JDBC driver. Inventory artifact version, JDK version, connection properties, prepared statements và type mappings.

### 26.3. psycopg và Python ecosystem

Ghi driver version, Python runtime, binary/wheel dependencies, async APIs và type adapters.

### 26.4. Npgsql/.NET

Ghi Npgsql version, .NET runtime, type mappings, enum/composite registrations và connection pool behavior.

### 26.5. Node.js, Go và các drivers khác

Ghi package/module versions, runtime versions, TLS/authentication support và custom codecs.

### 26.6. ORM

ORM có thể tạo SQL hoặc migration DDL phụ thuộc PostgreSQL version. Kiểm tra:
- Dialect/version support.
- Enum/domain/custom type mapping.
- JSON/JSONB, arrays, ranges và composite mapping.
- Generated SQL.
- Identity/sequence behavior.
- Migration framework version.

### 26.7. Không chỉ hỏi driver có kết nối được

Một driver có thể kết nối thành công nhưng serialize/deserialize custom types hoặc handle protocol features sai. Test application workflows và type round trips.

---

## 27. Operational tools và automation

Lập inventory cho tất cả công cụ chạm vào cluster hoặc data directory.

### 27.1. Upgrade utilities

- pg_upgrade binary từ target installation.
- pg_dump/pg_restore versions.
- pg_dumpall cho global objects.
- pg_checksums/pg_controldata nếu dùng trong quy trình.
- pg_config và build toolchain.

### 27.2. Backup/recovery tools

- pg_basebackup.
- pgBackRest, Barman hoặc giải pháp tương đương.
- Cloud snapshot/backup agents.
- WAL archive/restore scripts.
- Encryption/KMS clients.
- Restore orchestration.

### 27.3. HA/failover tools

- Patroni.
- repmgr.
- pg_auto_failover.
- Cloud failover manager.
- DCS/consensus services.
- Proxy/service discovery.

### 27.4. Monitoring/logging

- Prometheus exporters.
- Grafana agents.
- Log collectors.
- APM/tracing agents.
- Custom SQL monitoring jobs.

### 27.5. Poolers/proxies

- PgBouncer.
- Pgpool-II.
- Cloud proxies.
- Service mesh/network gateways.

### 27.6. CDC và integration

- Debezium.
- Kafka Connect.
- Logical decoding consumers.
- ETL/ELT tools.
- Data warehouse connectors.
- Foreign data integrations.

### 27.7. Scheduled jobs

- pg_cron.
- OS cron/systemd timers.
- Kubernetes CronJobs.
- Airflow/other orchestrators.
- Application background workers.

### 27.8. Upgrade compatibility

Mỗi tool cần xác nhận source/target major version support, protocol, catalog assumptions, extension dependencies, backup format, replication slot behavior và failover/reconnect behavior.

---

## 28. Kiểm kê global objects và cluster-level dependencies

Một số objects không thuộc riêng một database.

### 28.1. Roles

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolbypassrls,
    rolcanlogin
FROM pg_catalog.pg_roles
ORDER BY rolname;
~~~

Không xuất password hashes vào inventory chia sẻ rộng.

### 28.2. Tablespaces

~~~sql
SELECT
    spcname,
    pg_catalog.pg_get_userbyid(spcowner) AS owner,
    pg_catalog.pg_tablespace_location(oid) AS location
FROM pg_catalog.pg_tablespace
ORDER BY spcname;
~~~

Target host cần có storage paths và permissions tương ứng.

### 28.3. Database properties

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

Các cột locale provider/version phụ thuộc PostgreSQL version. Khám phá schema trước khi chạy trên source cũ.

### 28.4. Replication configuration

Ghi primary_conninfo, primary_slot_name, archive_command/restore_command, synchronous_standby_names và replication slots. Secrets trong connection strings phải được mask.

### 28.5. Config dependencies

Ghi config include paths, TLS cert/key files, authentication config, service environment variables và secrets references. Không lưu private keys/passwords trong inventory.

---

## 29. Xác định object dependency và application usage

Một object có thể tồn tại nhưng không có application usage; ngược lại, object được gọi gián tiếp qua view/function/trigger.

### 29.1. Tìm dependencies của một object

pg_depend lưu dependency edges giữa catalog objects. Dùng pg_describe_object để đọc object identity.

~~~sql
SELECT
    pg_catalog.pg_describe_object(
        d.classid, d.objid, d.objsubid
    ) AS dependent_object,
    pg_catalog.pg_describe_object(
        d.refclassid, d.refobjid, d.refobjsubid
    ) AS referenced_object,
    d.deptype
FROM pg_catalog.pg_depend AS d
WHERE d.refobjid = 'public.some_type'::regtype
ORDER BY dependent_object;
~~~

Đổi object reference phù hợp với type/table/function đang kiểm tra. Không phải mọi dependency đều có thể tra bằng một cast regtype.

### 29.2. Dependency types

pg_depend có các dependency types như normal, automatic, internal, extension membership và các loại khác. Cách drop/upgrade object phụ thuộc dependency type.

### 29.3. Dependencies không đồng nghĩa runtime usage

Catalog dependency cho biết quan hệ được PostgreSQL ghi nhận, không chứng minh object có được ứng dụng gọi trong production hay không.

### 29.4. Runtime usage evidence

Kết hợp:
- pg_stat_statements.
- Application logs/traces.
- Query logs.
- Database audit logs.
- Deployment/config repositories.
- Owner interviews.
- Scheduled jobs và ETL definitions.

### 29.5. Không đánh dấu unused chỉ vì không thấy trong một cửa sổ ngắn

Một function có thể chỉ chạy cuối tháng hoặc trong DR. Kiểm tra chu kỳ nghiệp vụ và retention của telemetry.

---

## 30. Xây dựng compatibility matrix

Compatibility matrix là tài liệu quyết định dependency nào được phép đi vào target.

### 30.1. Các chiều cần so sánh

- PostgreSQL source major/minor.
- PostgreSQL target major/minor.
- Extension name/version.
- Extension package/binary build.
- OS distribution/version.
- CPU architecture.
- libc/ICU/OpenSSL/GEOS/PROJ/GDAL hoặc libraries liên quan.
- Client driver/runtime.
- Backup/HA/monitoring tool version.
- External service/remote database version.

### 30.2. Trạng thái compatibility

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| Supported | Vendor/project xác nhận target support | Lên kế hoạch test |
| Tested internally | Đã rehearsal thành công với workload phù hợp | Ghi bằng chứng và giới hạn |
| Conditional | Cần pre/post steps hoặc config riêng | Hoàn tất điều kiện |
| Unknown | Chưa có evidence | Không coi là ready |
| Unsupported | Vendor không hỗ trợ hoặc incompatibility đã biết | Upgrade dependency/đổi thiết kế |
| Retired | Không còn maintained | Tìm replacement hoặc migration path |

### 30.3. Evidence cần lưu

- Link/version của release notes.
- Package build identifier.
- Test date/environment.
- SQL smoke test results.
- Binary load test.
- Performance comparison.
- Known limitations.
- Owner approval.

### 30.4. Không dùng latest version một cách tự động

Extension mới nhất có thể bỏ hỗ trợ source version hoặc cần intermediate upgrade. Chọn version theo compatibility matrix và vendor guidance.

### 30.5. Compatibility có nhiều tầng

Một extension có thể có SQL scripts tương thích nhưng C binary không tương thích, remote library thiếu, index opclass thay đổi hoặc performance behavior thay đổi. Chỉ ghi "compatible" khi các tầng liên quan đã được xác nhận.

---

## 31. pg_upgrade và dump/restore tác động tới dependency thế nào?

### 31.1. pg_upgrade

pg_upgrade chuyển cluster data files giữa major versions theo điều kiện hỗ trợ, giảm thời gian so với dump/restore cho cluster lớn.

Dependency requirements:
- Target server binaries.
- Target extension shared libraries.
- Extension package/SQL scripts phù hợp.
- OS/architecture requirements.
- Tablespace paths.
- Upgrade checks và pre/post steps.

### 31.2. pg_upgrade --check

Chạy check mode để phát hiện một số incompatibilities trước khi thực hiện. Đây là kiểm tra quan trọng nhưng không thay thế compatibility matrix, vendor docs và application tests.

### 31.3. pg_upgrade không tự giải quyết mọi extension update

Extension SQL version có thể vẫn ở version cũ sau chuyển đổi. Cần chạy ALTER EXTENSION UPDATE theo tài liệu extension và kế hoạch đã rehearsal.

### 31.4. Dump/restore

pg_dump/pg_restore tái tạo schema và dữ liệu qua logical representation. Có thể hữu ích khi thay đổi OS/architecture hoặc cần migration lớn, nhưng có thể tốn thời gian hơn và cần kiểm tra custom types, extension objects, ownership và restore ordering.

### 31.5. Extension binary vẫn cần target package

Dù dùng pg_upgrade hay dump/restore, target server vẫn cần extension packages/libraries nếu database objects gọi chúng.

### 31.6. Global objects

Roles, tablespaces và một số cluster-wide settings cần quy trình riêng. pg_dumpall --globals-only có thể giúp xuất global objects, nhưng phải review trước khi áp dụng.

### 31.7. Không coi một phương thức upgrade là giải pháp cho mọi dependency

Chọn phương thức theo database size, downtime, platform change, extension support, data transformations và rollback strategy.

---

## 32. Kiểm tra pg_upgrade trước khi rehearsal

### 32.1. Xác định binary target

Dùng pg_upgrade thuộc target installation và kiểm tra version/help phù hợp.

### 32.2. Chạy --check

~~~bash
pg_upgrade --check \
  --old-datadir=/path/to/old/data \
  --new-datadir=/path/to/new/data \
  --old-bindir=/path/to/old/bin \
  --new-bindir=/path/to/new/bin
~~~

Các option/path cụ thể phụ thuộc platform và cách cài đặt. Đọc pg_upgrade documentation của target major version.

### 32.3. Kiểm tra extension warnings

Nếu tool cảnh báo extension/library thiếu hoặc incompatible, xử lý trước khi thực hiện upgrade thật. Không bỏ qua chỉ vì cluster vẫn chạy trên source.

### 32.4. Kiểm tra locale/collation

Đánh giá locale changes và dependent indexes. Lên kế hoạch REINDEX/refresh theo PostgreSQL guidance.

### 32.5. Kiểm tra data type usage

Đối chiếu custom types, functions, operators và extension versions với target package. Chạy application-specific tests.

### 32.6. Check không thay thế rehearsal

--check không chứng minh backup restore, application driver, FDW, HA, monitoring và scheduled jobs hoạt động đúng.

---

## 33. Kế hoạch extension upgrade

### 33.1. Xác định version source/target

Lấy extversion từ pg_extension và target package versions từ pg_available_extension_versions trên target.

### 33.2. Đọc vendor release notes

Xác định PostgreSQL majors được hỗ trợ, minimum/maximum extension version, intermediate update path, pre/post scripts, binary ABI/build requirements, breaking SQL/API changes và index rebuild requirements.

### 33.3. Kiểm tra update path

Dùng pg_extension_update_paths nếu có. Ghi path được chọn và các script sẽ chạy.

### 33.4. Test ALTER EXTENSION UPDATE

Trên clone/staging, chạy lệnh cụ thể:

~~~sql
ALTER EXTENSION extension_name UPDATE TO 'target_extension_version';
~~~

Không chạy placeholder này nguyên văn; thay bằng extension/version đã được xác nhận và dùng đúng owner/privileges.

### 33.5. Thứ tự update

Nếu extension A requires B, làm theo dependency order được vendor/documentation quy định. Không tự suy luận tất cả extensions có thể update song song.

### 33.6. Extension không có update path

Có thể cần dump/restore, intermediate release, migration script hoặc vendor support. Không DROP/CREATE extension tùy tiện nếu extension quản lý data/configuration.

### 33.7. Xác nhận sau update

- extversion.
- Objects/functions/operators/types.
- Extension-owned indexes.
- Query behavior.
- Application type mapping.
- Logs và extension background workers.

---

## 34. Kiểm thử data types và application compatibility

### 34.1. Type round-trip

Với mỗi custom type quan trọng, test:
- Insert.
- Select.
- Cast.
- Comparison.
- Sort.
- Index lookup.
- Binary/text serialization.
- Null/edge values.
- Array/composite nesting nếu có.

### 34.2. Enum

Test mọi labels, ordering, casts, constraints và application deserialization.

### 34.3. Domain

Test CHECK/NOT NULL/default constraints và lỗi validation.

### 34.4. Composite

Test field order, null handling, function return values và client driver mapping.

### 34.5. Range/multirange

Test bounds inclusive/exclusive, empty ranges, overlaps, operators, indexes và timezone/date semantics.

### 34.6. Collation

Test ORDER BY, equality, unique constraints, case/accent behavior và indexes sau collation provider upgrade.

### 34.7. Custom C types

Test input/output, binary send/receive, comparison/hash, indexes và extension shared library loading.

### 34.8. Không chỉ test schema creation

Một schema có thể restore thành công nhưng application driver không serialize được type hoặc query plan thay đổi. Cần end-to-end application tests.

---

## 35. Các rủi ro đặc biệt cần kiểm tra

### 35.1. Extension bị bỏ maintain

Tìm release history, supported PostgreSQL versions, security fixes và migration path. Nếu không có target support, cần replacement hoặc giữ source version tới khi có kế hoạch.

### 35.2. C extension build mismatch

Kiểm tra server major version, architecture, compiler ABI và dependent libraries. Không copy binary cũ.

### 35.3. Extension dùng preload

Server có thể fail startup nếu shared_preload_libraries chứa library không có trên target.

### 35.4. Collation drift

OS/ICU update có thể làm sort behavior thay đổi. Lập inventory indexes phụ thuộc collation và REINDEX plan.

### 35.5. Custom types có binary storage

Nếu type lưu data theo custom binary representation, cần vendor-confirmed upgrade path hoặc migration procedure.

### 35.6. User mappings và secrets

FDW connection strings có thể chứa credentials. Inventory cần ghi secret reference và owner, không lưu secret plaintext.

### 35.7. Driver chưa hỗ trợ type mới/cũ

Một số driver cần explicit registration cho enum/composite/range hoặc có thay đổi type OIDs/mapping. Test client round trips.

### 35.8. Backup tools không tương thích

Tool có thể không hỗ trợ target major version hoặc backup format. Test restore trên target version.

### 35.9. Monitoring query bị lỗi sau upgrade

Statistics view columns có thể thay đổi. Kiểm tra exporter SQL collectors, dashboards và alerts.

### 35.10. Replication/CDC slot state

Logical decoding plugins và CDC connectors cần target compatibility. Kiểm tra slot restart_lsn, plugin, consumer offset và rebootstrap plan.

---

## 36. Tạo inventory có thể tái lập

### 36.1. Lưu raw query outputs

Lưu timestamp, cluster identity, database name, PostgreSQL version và command/query used. Không chỉ copy một vài dòng kết quả vào ticket.

### 36.2. Ghi OS packages

Lưu package name/version/architecture và repository. Với containers, lưu image digest và lockfiles.

### 36.3. Ghi binary locations

Lưu pg_config sharedir/pkglibdir và danh sách extension .control, SQL scripts, shared libraries. Trên target, so sánh với package manifest.

### 36.4. Ghi configuration

Lưu settings hiệu lực, source file và pending_restart. Mask secrets.

### 36.5. Ghi application inventory

Lưu service, runtime, driver, ORM, pooler, scheduled jobs và owner.

### 36.6. Ghi evidence

Mỗi row trong inventory nên có:
- Compatibility status.
- Evidence URL/document.
- Tested version.
- Test result.
- Owner.
- Required action.
- Cutover/rollback notes.

### 36.7. Version-control inventory

Đặt inventory vào repository/secure documentation có revision history. Secrets và credentials phải được tham chiếu qua secret manager, không commit plaintext.

---

## 37. Mẫu inventory và compatibility matrix

### 37.1. Extension inventory

| Database | Extension | Installed version | Target package version | Preload | Dependencies | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| appdb | extension_a | 1.4 | 1.6 | yes/no | extension_b | team | Unknown |
| analytics | extension_c | 2.1 | 2.3 | no | OS library | team | Tested |

Dòng trên chỉ là ví dụ định dạng, không phải dữ liệu của cluster thật.

### 37.2. Data type inventory

| Schema | Type | Kind | Extension-owned | Used by | Compatibility evidence |
| --- | --- | --- | --- | --- | --- |
| app | order_status | enum | no | orders.status | Type round-trip |
| app | currency_amount | domain | no | invoices | Constraint test |
| geo | geometry | base/extension | yes | spatial tables | Vendor support |

### 37.3. External tools inventory

| Tool | Version | Runs where | Connects to | Target support | Owner |
| --- | --- | --- | --- | --- | --- |
| JDBC driver | version | application | PostgreSQL | confirmed/pending | app team |
| Backup agent | version | backup host | cluster/storage | confirmed/pending | DBA |
| Exporter | version | monitoring | pg_catalog | confirmed/pending | SRE |
| Pooler | version | proxy host | PostgreSQL | confirmed/pending | platform |

### 37.4. Risk register

| Dependency | Failure mode | Impact | Mitigation | Test | Owner |
| --- | --- | --- | --- | --- | --- |
| C extension | library fails to load | Server/function unavailable | Target build | Startup + SQL test | DBA/vendor |
| ICU collation | index order mismatch | Query/unique behavior | REINDEX plan | Collation tests | DBA |
| Driver | custom type decode fails | App errors | Driver upgrade | Round-trip test | App team |
| FDW | remote library/protocol fails | Integration unavailable | Upgrade package/endpoint | Remote query test | Integration team |

---

## 38. Quy trình kiểm kê trước upgrade

### Bước 1: Xác định scope

Ghi source/target major versions, databases, hosts, OS/architecture, topology và downtime objective.

### Bước 2: Thu thập catalog inventory

Chạy queries cho extensions, available versions, extension objects, types, functions, languages, collations, operators, opclasses, FDW, event triggers và replication objects.

### Bước 3: Thu thập server configuration

Lấy shared_preload_libraries, settings có custom values, config include files, authentication, TLS, archive và replication settings. Mask secrets.

### Bước 4: Thu thập host/package inventory

Liệt kê PostgreSQL packages, extension packages, shared libraries, dependent OS packages, build toolchain và container image.

### Bước 5: Thu thập application/tool inventory

Liệt kê drivers, ORMs, migration tools, poolers, backup, monitoring, HA, CDC, ETL và scheduled jobs.

### Bước 6: Xây dependency graph

Nối database objects tới extension, extension tới shared library, application tới type/function, FDW tới remote service và tool tới PostgreSQL version.

### Bước 7: Đánh giá compatibility

Mỗi dependency phải có status và evidence. Đánh dấu Unknown nếu chưa xác nhận.

### Bước 8: Xác định migration actions

Upgrade package, rebuild C extension, ALTER EXTENSION UPDATE, REINDEX, refresh collation version, update driver, thay tool hoặc chuẩn bị data conversion.

### Bước 9: Rehearsal

Dùng clone/restore của production với cùng package/config/extension set. Chạy upgrade và application tests.

### Bước 10: Freeze và cutover readiness

Chốt inventory, package versions, artifact hashes, backup, runbooks, owners và rollback criteria. Không để package drift sau rehearsal.

---

## 39. Runbook: xử lý extension thiếu trên target

### Bước 1: Xác định extension

Ghi database, extname, extversion, owner, schema và object dependencies.

### Bước 2: Kiểm tra package target

Dùng pg_available_extensions và host package manager. Xác định thiếu control file, SQL scripts hay shared library.

### Bước 3: Kiểm tra target support

Đọc vendor release notes, supported PostgreSQL majors, OS/architecture và dependency libraries.

### Bước 4: Cài package đúng target

Dùng package/build được xác nhận cho target installation. Không copy binary từ source host.

### Bước 5: Kiểm tra preload

Nếu extension cần preload, cập nhật config target và restart theo plan trước khi nhận workload.

### Bước 6: Kiểm tra extension update path

Xác định version path và pre/post steps.

### Bước 7: Rehearse

Restore/clone database vào target, load extension, chạy update và application tests.

### Bước 8: Ghi evidence

Lưu package version, library path, extension version, test output và owner approval.

---

## 40. Runbook: collation version mismatch

### Bước 1: Liệt kê collations

Lấy provider, locale và recorded collation version.

### Bước 2: So sánh actual version

Dùng pg_collation_actual_version trên version hỗ trợ và xác định mismatch.

### Bước 3: Tìm dependent indexes

Kiểm tra indexes/constraints/expressions sử dụng collation đó. Xác định phạm vi tables và business-critical uniqueness.

### Bước 4: Đọc release guidance

Xem PostgreSQL và OS/ICU vendor instructions. Xác định thứ tự REINDEX và REFRESH VERSION.

### Bước 5: Lên kế hoạch rebuild

Ước tính disk, I/O, locks và downtime/concurrency. Chọn REINDEX hoặc phương pháp phù hợp với yêu cầu.

### Bước 6: Test comparison semantics

Test ORDER BY, equality, unique indexes và application sorting.

### Bước 7: Refresh metadata sau rebuild

Chỉ cập nhật recorded collation version sau khi các dependent objects đã được xử lý theo quy trình.

---

## 41. Lab 1: inventory extensions trong một database

Dùng database lab hoặc staging.

### 41.1. Liệt kê extensions

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema,
    extowner::regrole AS owner,
    extrelocatable
FROM pg_catalog.pg_extension
ORDER BY extname;
~~~

### 41.2. Liệt kê available versions

~~~sql
SELECT
    name,
    version,
    installed,
    requires,
    trusted,
    relocatable
FROM pg_catalog.pg_available_extension_versions
ORDER BY name, version;
~~~

### 41.3. Đếm objects

Dùng pg_depend để đếm extension members.

### 41.4. So sánh target

Chạy các queries trên target clone và so installed/available versions.

### 41.5. Ghi kết quả

Tạo inventory với extension name, source version, target package version, dependencies, preload, owner và compatibility status.

---

## 42. Lab 2: inventory custom types và dependencies

### 42.1. Liệt kê user-defined types

Dùng pg_type/pg_namespace và phân loại typtype.

### 42.2. Liệt kê enum labels

Dùng pg_enum và lưu sort order.

### 42.3. Liệt kê domains

Dùng pg_type/pg_constraint và lưu base type/default/constraints.

### 42.4. Liệt kê composite attributes

Dùng pg_class/pg_attribute/pg_type và lưu thứ tự fields.

### 42.5. Tìm columns dùng custom types

Dùng information_schema.columns hoặc catalog joins.

### 42.6. Kết luận

Đối chiếu types với extension ownership, application mappings và migration test cases.

---

## 43. Lab 3: tìm C functions và preload requirements

### 43.1. Liệt kê C functions

Dùng pg_proc join pg_language để lấy probin/prosrc.

### 43.2. Xem preload settings

~~~sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
~~~

### 43.3. Xem library paths

Trên host:

~~~bash
pg_config --pkglibdir
pg_config --sharedir
~~~

### 43.4. Kiểm tra packages

Đối chiếu library files với OS package manifest và target installation. Trên Linux, kiểm tra dynamic dependencies bằng công cụ phù hợp.

### 43.5. Rehearsal

Khởi động target server với đúng preload list và chạy smoke tests gọi các C functions.

### 43.6. Kết luận

Một catalog function có thể tồn tại trong database nhưng library implementation không load được trên target.

---

## 44. Lab 4: inventory collations và indexes

### 44.1. Liệt kê collations

Lấy provider, locale, recorded version và actual version nếu có.

### 44.2. Tìm mismatch

So sánh collversion với pg_collation_actual_version.

### 44.3. Xác định dependent objects

Tìm indexes/constraints sử dụng collation. Dùng catalog dependencies và index definitions.

### 44.4. Test semantics

Tạo dataset chứa uppercase/lowercase, accents và locale-specific characters trong lab. So sánh sort/equality trên source và target.

### 44.5. Rebuild rehearsal

Trên clone, thực hiện REINDEX theo plan rồi refresh collation version theo documentation.

### 44.6. Kết luận

Locale/provider change là một dependency của data semantics và indexes, không chỉ là cấu hình OS.

---

## 45. Lab 5: compatibility rehearsal

### 45.1. Chuẩn bị clone

Restore một backup gần production vào staging. Giữ package/config/extension set tương đương.

### 45.2. Cài target binaries và packages

Cài PostgreSQL target, extension packages, dependent libraries và operational tools.

### 45.3. Chạy upgrade check

Dùng pg_upgrade --check hoặc quy trình tương ứng với phương thức upgrade.

### 45.4. Thực hiện rehearsal

Chạy extension updates, collation plan và các migration steps đã xác định.

### 45.5. Test clients

Kết nối bằng từng driver/ORM/pooler version; test custom types, functions, transactions, authentication và TLS.

### 45.6. Test operations

Chạy backup, restore, monitoring collectors, HA/failover, CDC và scheduled jobs.

### 45.7. Ghi thời gian và issue

Ghi downtime, duration từng step, warnings, manual actions và rollback point. Không chốt production plan nếu còn dependency Unknown quan trọng.

---

## 46. Bài tập thực hành

### Bài 1 — Dependency scope

Liệt kê các lớp dependency ngoài table/index cần inventory trước major upgrade.

### Bài 2 — Installed vs available

Phân biệt pg_extension, pg_available_extensions và pg_available_extension_versions.

### Bài 3 — Extension inventory

Viết query lấy extension name, extversion, schema, owner và relocatable.

### Bài 4 — Multi-database

Vì sao phải chạy extension inventory trong mọi database của cluster?

### Bài 5 — Update path

Giải thích vì sao có package target không chứng minh có đường ALTER EXTENSION UPDATE.

### Bài 6 — Extension dependencies

Tìm extensions có requires và mô tả cách biểu diễn dependency chain.

### Bài 7 — Extension-owned objects

Dùng pg_depend và pg_describe_object để liệt kê object members của một extension.

### Bài 8 — Preload

Tìm shared_preload_libraries và nêu rủi ro khi library target thiếu.

### Bài 9 — Type taxonomy

Phân biệt base, composite, domain, enum, range, multirange và pseudo-types.

### Bài 10 — Custom columns

Viết query tìm table columns sử dụng user-defined types.

### Bài 11 — Enum ordering

Vì sao enum sort order cần được bảo toàn? Nêu test sau upgrade.

### Bài 12 — Domain constraints

Kiểm kê base type, default và CHECK constraints của domains.

### Bài 13 — Composite type

Tìm fields của composite types và giải thích vì sao field order quan trọng với clients.

### Bài 14 — Range types

Liệt kê subtype, collation, canonical function và subtype diff function của ranges.

### Bài 15 — C functions

Tìm C-language functions, library name và symbol. Nêu vì sao binary phải được build cho target.

### Bài 16 — Procedural languages

Kiểm kê language và runtime dependencies của PL/Python hoặc PL/Perl.

### Bài 17 — Collations

Liệt kê collations theo provider và locale. Giải thích recorded vs actual version.

### Bài 18 — Collation mismatch

Một ICU upgrade làm collation version đổi. Lập kế hoạch dependent index rebuild và validation.

### Bài 19 — Casts

Kiểm kê user-defined casts và functions thực hiện conversion.

### Bài 20 — Operators

Kiểm kê operators ngoài pg_catalog và implementation functions.

### Bài 21 — Operator classes

Giải thích vì sao extension opclass/access method cần target binary và index tests.

### Bài 22 — FDW

Kiểm kê FDWs, foreign servers, foreign tables và user mappings. Nêu cách bảo vệ secrets.

### Bài 23 — Event triggers

Tìm event triggers và giải thích rủi ro khi upgrade scripts chạy DDL.

### Bài 24 — Logical replication

Kiểm kê publications/subscriptions, slots, plugins và CDC consumers.

### Bài 25 — OS packages

Thiết kế package inventory cho PostgreSQL extensions trên Linux/container.

### Bài 26 — Client drivers

Lập inventory JDBC, psycopg, Npgsql hoặc driver đang dùng và các custom type mappings.

### Bài 27 — Operational tools

Liệt kê backup, monitoring, HA, pooler, CDC, ETL và scheduler tools cần xác nhận target support.

### Bài 28 — pg_upgrade

Giải thích pg_upgrade --check phát hiện được gì và không thay thế được những kiểm thử nào.

### Bài 29 — Dump/restore

So sánh dump/restore với pg_upgrade về dependency, downtime và khả năng thay đổi platform.

### Bài 30 — Extension update

Viết runbook từ source extversion tới target package, update path, rehearsal và post-upgrade validation.

### Bài 31 — Unknown dependency

Một extension không có release notes cho target version. Quyết định compatibility status và bước tiếp theo.

### Bài 32 — Library missing

Server target không load được C library khi startup. Lập trình tự kiểm tra package, path, ABI và dependent libraries.

### Bài 33 — Driver mismatch

Database đã nâng cấp nhưng ORM không đọc được custom enum/composite. Đề xuất kiểm tra và test.

### Bài 34 — Collation and uniqueness

Một collation change có thể ảnh hưởng unique index như thế nào? Xây dựng validation plan.

### Bài 35 — Dependency graph

Vẽ graph application → function/type → extension → shared library → OS package.

### Bài 36 — Ownership

Thiết kế bảng owner/escalation cho các dependencies không thuộc DBA team.

### Bài 37 — Inventory drift

Sau rehearsal, package version trên target thay đổi. Vì sao phải freeze artifacts và chạy lại compatibility checks?

### Bài 38 — Security

Một FDW user mapping có password trong options. Cách inventory mà không đưa secret plaintext vào tài liệu?

### Bài 39 — Rollback

Nêu điều kiện cần giữ source cluster, backup, extension packages và application deployment để rollback sau failed cutover.

### Bài 40 — End-to-end upgrade

Một cluster dùng PostGIS, pg_cron, pg_stat_statements, custom C extension, enum/domain types, ICU collation, postgres_fdw, JDBC/Npgsql clients, PgBouncer, backup agent và CDC. Xây dựng inventory, dependency graph, compatibility matrix, rehearsal plan, upgrade steps, validation và rollback criteria cho một major-version upgrade.

---

## 47. Checklist trước khi chốt upgrade readiness

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Source/target | PostgreSQL versions, OS và architecture |
| Databases | Đã inventory tất cả databases |
| Extensions | extname/extversion/owner/schema |
| Available packages | Target package và version có sẵn |
| Update paths | Source-to-target extension paths |
| Extension dependencies | requires chain và order |
| Extension objects | pg_depend membership |
| Preload | shared/session/local preload libraries |
| Custom types | Base/composite/domain/enum/range/multirange |
| Type usage | Columns, function arguments/returns, indexes |
| Enum labels | Values và sort order |
| Domain constraints | Base type, default, validation |
| Composite fields | Field names/order/types |
| C functions | probin, prosrc và library ABI |
| Procedural languages | Runtime/interpreter packages |
| Casts/operators | Implementation functions |
| Operator classes | Access methods và dependent indexes |
| Collations | Provider, locale, recorded/actual versions |
| Collation indexes | REINDEX plan và validation |
| FDW | Wrapper/handler/validator packages |
| Foreign servers | Remote endpoint compatibility |
| User mappings | Secret references và owners |
| Event triggers | DDL side effects |
| Publications/subscriptions | Logical replication/CDC plan |
| Global objects | Roles, tablespaces và privileges |
| Configuration | Preload, custom GUCs, config includes |
| OS packages | Versions, architecture, repositories |
| Shared libraries | Paths và dependent libraries |
| Client drivers | Version/runtime/type mapping support |
| ORMs/migrations | Dialect and generated SQL support |
| Poolers/proxies | Protocol, reconnect and auth support |
| Backup tools | Target version support and restore test |
| HA tools | Failover and rejoin support |
| Monitoring | Exporter queries and dashboard compatibility |
| CDC/ETL | Plugins, slots, offsets and schema evolution |
| Scheduled jobs | pg_cron/external scheduler owners |
| Compatibility evidence | Vendor docs and internal tests |
| Rehearsal | Same packages/config/data shape |
| Rollback | Backup, source retention and trigger conditions |
| Owners | Named team/contact for each dependency |
| Freeze | Package/image/config artifacts pinned |

## Kết luận

Kiểm kê extension, kiểu dữ liệu và công cụ phụ thuộc là bước nền tảng để nâng cấp PostgreSQL an toàn. pg_extension cho biết extension đã cài trong từng database; pg_available_extensions và pg_available_extension_versions cho biết package mà server nhìn thấy; pg_depend giúp lần theo objects thuộc extension. pg_type và các catalog liên quan mô tả custom types, còn pg_proc/pg_language, pg_collation, FDW, event triggers và replication catalogs giúp phát hiện những dependency sâu hơn.

Những nguyên tắc cần nhớ:

1. **Kiểm kê từng database.** Extensions được cài theo database, không thể suy ra toàn cluster từ một kết quả.
2. **Tách installed extension khỏi server package.** Database metadata không chứng minh target host có control files, SQL scripts và shared libraries.
3. **Ghi version và update path.** Extension cần target package và đường nâng cấp được vendor hỗ trợ.
4. **Lần theo extension-owned objects.** Dùng pg_depend để hiểu phạm vi objects và dependencies.
5. **Kiểm kê mọi custom types.** Enum, domain, composite, range và base types có thể được dùng trong columns, functions, indexes và application protocols.
6. **Kiểm tra C libraries và preload.** Binary phải tương thích target PostgreSQL major, OS, architecture và dependent libraries.
7. **Không bỏ qua collations.** libc/ICU version drift có thể yêu cầu rebuild indexes trước khi refresh metadata.
8. **FDW và user mappings phụ thuộc hệ thống ngoài.** Kiểm tra remote endpoints, libraries, protocols và secret references.
9. **Client stack cũng cần upgrade.** Driver, ORM, pooler, backup, HA, monitoring, CDC và ETL có thể trở thành điểm lỗi sau cutover.
10. **pg_upgrade --check không thay rehearsal.** Nó không chứng minh toàn bộ applications và external tools hoạt động đúng.
11. **Mọi dependency cần owner và evidence.** Unknown không được xem là compatible.
12. **Freeze artifacts sau rehearsal.** Package/image/config drift có thể làm kết quả rehearsal không còn giá trị.
13. **Test type behavior end-to-end.** Schema restore thành công chưa đủ; cần test serialization, operators, indexes, constraints và application workflows.
14. **Giữ rollback path khả dụng.** Backup, source cluster, packages và application deployment phải phù hợp với điều kiện rollback.

Một upgrade sẵn sàng khi từng dependency quan trọng đã có phiên bản target, đường migration, owner, bằng chứng tương thích và test thành công. Inventory đầy đủ giúp biến việc nâng cấp từ một lần thay server binary thành một thay đổi có kiểm soát trên toàn bộ hệ sinh thái PostgreSQL.
