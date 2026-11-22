# Đọc ghi chú phát hành và lập danh sách thay đổi tương thích khi nâng cấp PostgreSQL

Nâng cấp PostgreSQL là thay đổi có phạm vi rộng hơn việc thay binary hoặc chuyển data directory sang một phiên bản mới. Một major release có thể thay đổi cú pháp SQL, hành vi hàm, system catalog, cấu hình, mặc định bảo mật, planner, extension interfaces và cách các công cụ vận hành làm việc. Một thay đổi nhỏ trong release notes đôi khi tác động trực tiếp tới ứng dụng, migration scripts, backup jobs hoặc quy trình failover.

Ghi chú phát hành (release notes) là nguồn đầu tiên để nhận diện các thay đổi giữa phiên bản hiện tại và phiên bản đích. Nhưng đọc lướt danh sách tính năng mới là chưa đủ. Người chuẩn bị nâng cấp phải tìm cả thay đổi tương thích ngược, tính năng bị loại bỏ, hành vi được sửa, default mới, giới hạn mới, thay đổi bảo mật và các ghi chú migration. Sau đó cần liên kết từng mục với thành phần thực tế trong hệ thống, đánh giá rủi ro, xác định người xử lý và tạo test chứng minh hệ thống vẫn hoạt động.

Bài học thuộc chương **Nâng cấp** của module *Database Engine Relational PostgreSQL*. Nội dung hướng dẫn cách thu thập release notes theo đúng dải phiên bản, phân tích thay đổi, kiểm kê ứng dụng và hạ tầng, xây dựng compatibility register, xác định blocker, thiết kế kiểm thử và hoàn thiện danh sách công việc trước khi nâng cấp.

> **Nguyên tắc:** Mỗi thay đổi trong release notes cần được gắn với một thành phần cụ thể hoặc được ghi rõ là chưa xác định được phạm vi ảnh hưởng. Một danh sách chỉ chép lại release notes chưa phải là compatibility assessment.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt major release, minor release và các loại thay đổi trong PostgreSQL.
2. Xác định đầy đủ dải release notes cần đọc từ source version tới target version.
3. Tìm các phần Migration, Server, SQL, Utilities, Client Interfaces, Extensions và Security.
4. Phân biệt tính năng mới với thay đổi có thể làm hỏng tương thích.
5. Nhận diện thay đổi cú pháp, semantics, defaults, configuration, catalog và planner.
6. Đánh giá tác động của thay đổi bảo mật, authentication và TLS.
7. Kiểm tra khả năng tương thích của extensions, drivers, poolers và công cụ backup.
8. Kiểm kê cấu hình server, SQL, stored procedures, jobs và migration scripts.
9. Đánh giá collation, locale, encoding, time zone và operating system dependencies.
10. Xác định các thay đổi có thể ảnh hưởng replication, backup, recovery và HA.
11. Xây dựng compatibility register với severity, owner, evidence và validation.
12. Phân biệt blocker, high risk, conditional change và informational item.
13. Sử dụng truy vấn PostgreSQL để thu thập baseline trước nâng cấp.
14. Tìm usage của setting/API cũ trong repository và deployment automation.
15. Thiết kế regression tests và staging upgrade rehearsal.
16. Phân biệt nâng cấp minor với major và chọn cách migration phù hợp.
17. Lập cutover, rollback và acceptance criteria.
18. Tạo checklist để review và phê duyệt danh sách thay đổi tương thích.

## 2. Release notes là gì?

Release notes là tài liệu mô tả các thay đổi được đưa vào một phiên bản phần mềm. Với PostgreSQL, release notes thường chia nội dung theo phiên bản và nhóm thay đổi, chẳng hạn server, SQL, utilities, client interfaces, extensions/contrib, build/platform và migration.

Release notes có thể đề cập:
- Tính năng mới.
- Lỗi đã sửa.
- Thay đổi hành vi.
- Tính năng hoặc API bị deprecated.
- Tính năng bị loại bỏ.
- Thay đổi mặc định.
- Thay đổi cấu hình.
- Thay đổi catalog hoặc system views.
- Thay đổi planner/executor.
- Sửa lỗi bảo mật.
- Yêu cầu về extension, compiler, operating system hoặc công cụ.

### 2.1. Release notes không phải upgrade runbook

Release notes giải thích sản phẩm đã thay đổi. Chúng không nhất thiết mô tả đầy đủ cách chuẩn bị backup, chạy pg_upgrade, chuyển traffic, migrate extension, xử lý application cutover hoặc rollback sau khi target đã nhận writes.

Cần đọc thêm tài liệu upgrade chính thức và hướng dẫn của extension/vendor.

### 2.2. Release notes không phải danh sách mọi khác biệt

Không phải mọi khác biệt hành vi đều được liệt kê như một mục riêng. Planner có thể chọn execution plan khác, bug fix có thể làm kết quả trước đây sai được sửa lại, và extension có thể thay đổi độc lập với PostgreSQL core.

Vì vậy, release notes là đầu vào của assessment, còn kiểm kê hệ thống và testing mới xác định tác động thực tế.

### 2.3. Đọc release notes theo phạm vi phiên bản

Một hệ thống nâng từ PostgreSQL 15 lên 18 cần đọc các thay đổi của 16, 17 và 18, không chỉ trang của 18. Các phiên bản major trung gian có thể chứa thay đổi cấu hình hoặc behavior mà hệ thống đang dùng.

Cũng cần xem các minor releases liên quan tới source và target để nắm bug fixes, security fixes, known issues và những thay đổi đã được đưa vào binary đang triển khai.

## 3. Phân biệt major và minor release

Từ PostgreSQL 10 trở đi, cách đánh số phổ biến là major version và minor version, ví dụ 16.1, 16.2 hoặc 17.0, 17.1.

- **Major release:** số đầu thay đổi, ví dụ 16 lên 17. Major upgrade có thể thay đổi internal catalog/storage compatibility và thường cần một phương thức migration được hỗ trợ.
- **Minor release:** số thứ hai thay đổi, ví dụ 17.1 lên 17.2. Minor releases chủ yếu chứa bug fixes và security fixes, thường giữ tương thích dữ liệu trong cùng major version.

### 3.1. Minor upgrade vẫn cần đọc release notes

Minor releases thường không yêu cầu dump/restore hoặc pg_upgrade, nhưng có thể sửa behavior mà ứng dụng đang vô tình phụ thuộc, sửa lỗi khiến query trả kết quả khác với bug trước đó, thay đổi security behavior, sửa lỗi crash/corruption, yêu cầu restart để thay binary hoặc ảnh hưởng extension/client packages.

### 3.2. Major upgrade cần assessment rộng hơn

Major upgrade có thể liên quan catalog changes, removed parameters/SQL features, data type hoặc function behavior, extension binary compatibility, planner changes, collation version, authentication defaults, backup/replication tooling, upgrade method và downtime.

### 3.3. Không suy ra tương thích chỉ từ số version

Hai phiên bản cùng major thường có compatibility expectations cao hơn, nhưng vẫn cần kiểm tra bug/security notes và extension compatibility. Hai phiên bản khác major không thể coi là binary/data-directory interchangeable.

## 4. Xác định source và target versions

Trước khi đọc release notes, ghi rõ phiên bản thực tế và phiên bản đích.

Trên server:

```sql
SELECT
    version() AS full_version,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num;
```

Ghi lại:
- PostgreSQL major/minor hiện tại.
- PostgreSQL target major/minor chính xác.
- Operating system và version.
- CPU architecture.
- Package source/repository.
- Extension versions.
- Driver/client versions.
- HA manager và DCS versions.
- Backup tooling versions.
- Deployment topology.

### 4.1. Target phải là version cụ thể

Không ghi “upgrade lên PostgreSQL mới nhất” trong compatibility register. Ghi major/minor chính xác, ví dụ 17.4 hoặc version đã được tổ chức phê duyệt. Nếu target thay đổi trong quá trình chuẩn bị, phải rà soát lại release notes và test scope.

### 4.2. Xác định mọi cluster trong môi trường

Production, staging, DR, reporting, development và local test clusters có thể không cùng version. Đừng chỉ lấy version của một primary rồi áp dụng cho tất cả.

### 4.3. Phân biệt server và client versions

PostgreSQL server, libpq, psql, pg_dump, pg_restore, pg_basebackup, JDBC driver, psycopg, Npgsql, PgBouncer và monitoring exporters có vòng đời version riêng. Ghi chúng thành các dòng inventory riêng.

## 5. Xác định dải release notes phải đọc

Giả sử source là PostgreSQL 14.9 và target là 17.4. Phạm vi major notes gồm các thay đổi của PostgreSQL 15, 16 và 17.

Cách lập dải đọc:

1. Xác nhận source major/minor từ production.
2. Xác nhận target major/minor đã được chọn.
3. Liệt kê từng major version nằm giữa source và target, bao gồm target.
4. Đọc migration notes của từng major.
5. Đọc toàn bộ các mục major-release notes của từng phiên bản liên quan.
6. Đọc minor-release notes có liên quan tới source/target deployment và các bản vá mà hệ thống sẽ đi qua.
7. Ghi lại ngày, URL, version và người thực hiện review.

### 5.1. Không bỏ qua major version trung gian

Một thay đổi được giới thiệu trong major trung gian vẫn có thể ảnh hưởng khi nâng cấp trực tiếp lên target. Không cần cài lần lượt từng major để đọc notes của chúng.

### 5.2. Đọc migration notes trước

Phần Migration thường chứa các thay đổi cần xử lý trước hoặc trong upgrade. Đánh dấu các mục có câu chữ như:
- no longer supported;
- removed;
- must be changed;
- incompatible;
- requires;
- cannot be used;
- default has changed;
- behavior has changed.

Đây là từ khóa sàng lọc, không phải bằng chứng duy nhất về mức độ ảnh hưởng.

### 5.3. Đọc toàn bộ mục có liên quan sau khi sàng lọc

Không chỉ search từ “removed”. Một bug fix có thể thay đổi kết quả query, một planner improvement có thể làm performance regress, và một default mới có thể ảnh hưởng authentication hoặc memory usage dù không được gọi là breaking change.

## 6. Cách đọc một mục release note

Với mỗi mục, tách nội dung thành các câu hỏi:

1. **What changed?** Thành phần hoặc behavior nào thay đổi?
2. **When?** Thay đổi xuất hiện từ version nào?
3. **Why?** Đây là feature, bug fix, security fix hay compatibility change?
4. **Who is affected?** Server, DBA, application, extension, client, OS hay automation?
5. **Is it conditional?** Chỉ ảnh hưởng khi bật một setting hoặc dùng một API cụ thể?
6. **What is the old behavior?** Hệ thống hiện tại đang hoạt động thế nào?
7. **What is the new behavior?** Target sẽ xử lý khác ra sao?
8. **What must change?** Cần sửa code, config, data, extension hay process?
9. **How to prove it?** Test nào chứng minh đã xử lý?
10. **What if it fails?** Có workaround, fallback hoặc rollback path nào?

### 6.1. Không copy nguyên văn dài vào register

Ghi lại một câu mô tả ngắn bằng ngôn ngữ của đội vận hành, trỏ tới URL và section gốc. Lưu version và heading để reviewer có thể mở lại đúng nội dung.

### 6.2. Phân biệt fact với hypothesis

Ví dụ:
- Fact: target release thay đổi default của một setting.
- Hypothesis: ứng dụng có thể bị ảnh hưởng vì đang dựa vào default cũ.
- Evidence: config production không set setting đó và integration test dùng behavior cũ.
- Action: đặt explicit config hoặc cập nhật code, sau đó chạy test.

Không ghi hypothesis như một kết luận đã được xác nhận.

## 7. Phân loại thay đổi tương thích

| Loại | Mô tả | Ví dụ tác động |
|---|---|---|
| Removed | Tính năng/API/setting bị loại bỏ | Config cũ không còn được nhận |
| Deprecated | Tính năng còn dùng nhưng không nên tiếp tục dựa vào | Cần lập kế hoạch thay thế |
| Behavior | Semantics hoặc kết quả xử lý thay đổi | Query/application logic cần test |
| Default | Giá trị mặc định thay đổi | Hệ thống không khai báo explicit setting bị ảnh hưởng |
| SQL/API | Syntax, function, operator hoặc type thay đổi | Stored procedure/client query lỗi |
| Catalog | System catalog/view/function thay đổi | Monitoring hoặc admin script lỗi |
| Security | Authentication, privilege, TLS hoặc policy thay đổi | Client không kết nối được |
| Performance | Planner, executor, memory hoặc I/O behavior đổi | Query latency/throughput thay đổi |
| Extension | Extension API, version hoặc build requirement đổi | Extension không load/upgrade được |
| Utility | Tool option, output hoặc behavior đổi | Backup/deployment automation lỗi |
| Platform | OS, compiler, architecture, library dependency đổi | Package/build không tương thích |
| Replication/Recovery | WAL, slot, backup, standby behavior đổi | DR/failover process bị ảnh hưởng |
| Bug fix | Lỗi cũ được sửa | Kết quả hoặc timing thay đổi so với behavior trước |

### 7.1. Breaking change

Một breaking change là thay đổi làm cho một thành phần trước đây hoạt động được không còn hoạt động hoặc cần thay đổi để tiếp tục hoạt động.

Không phải mọi removed feature đều là blocker cho mọi hệ thống. Nếu hệ thống không dùng feature đó, impact có thể là none, nhưng cần có evidence để kết luận.

### 7.2. Behavioral change

Một API vẫn tồn tại nhưng semantics thay đổi có thể nguy hiểm hơn compile error. Ví dụ query vẫn chạy nhưng kết quả, ordering, rounding, timezone interpretation hoặc privilege check khác.

### 7.3. Default change

Nếu cấu hình không explicit, hệ thống kế thừa default của phiên bản. Do đó, thay đổi default cần được so sánh với effective production value, không chỉ file config được quản lý trong Git.

### 7.4. Bug fix cũng cần kiểm tra

Nếu ứng dụng dựa vào một bug cũ, bug fix có thể làm behavior thay đổi. Không nên giữ bug làm contract; hãy xác định ứng dụng cần điều chỉnh thế nào để tuân thủ semantics đúng.

## 8. Xây dựng compatibility inventory

Release note chỉ hữu ích khi biết hệ thống đang sử dụng những gì. Tạo inventory theo các lớp.

**Database**
- Database names, owners, encodings, locales.
- Schemas, tables, views, materialized views.
- Functions, procedures, triggers, operators, types.
- Extensions và versions.
- Collations và ICU/libc providers.
- Roles, grants, row-level security policies.
- Foreign data wrappers và foreign servers.

**Application**
- Services, batch jobs, ETL/CDC consumers.
- SQL embedded trong code.
- ORM và migration framework.
- Connection pools.
- Driver/client library versions.
- Query builders và generated SQL.

**Operations**
- postgresql.conf, include files, pg_hba.conf, pg_ident.conf.
- Backup/PITR scripts.
- Replication/HA configuration.
- Monitoring exporters, dashboards và alerts.
- Deployment scripts, service units, container images.
- Cron jobs, maintenance jobs và failover runbooks.

**Platform**
- OS, architecture, kernel.
- Locale packages, ICU, OpenSSL, LDAP/Kerberos.
- Filesystem, storage, mount options.
- Package repository và compiler/runtime dependencies.

## 9. Thu thập baseline từ PostgreSQL

Các truy vấn sau giúp ghi lại trạng thái source cluster. Chạy với role có quyền phù hợp và lưu kết quả theo ngày/cluster.

### 9.1. Version và cluster identity

```sql
SELECT
    version() AS full_version,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num,
    pg_postmaster_start_time() AS postmaster_started_at;
```

### 9.2. Database encodings và collations

```sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
ORDER BY datname;
```

Một số phiên bản cung cấp thêm metadata về locale provider. Điều chỉnh query theo schema của source cluster.

### 9.3. Extensions đang cài

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
ORDER BY extname;
```

### 9.4. Extension versions có sẵn

```sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
```

Danh sách này phản ánh các extension control files được cài trên server hiện tại, không phải những extension chắc chắn có trên target package. Cần kiểm tra target environment riêng.

### 9.5. Effective configuration

```sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
ORDER BY name;
```

Ghi lại effective value và source. File config có thể chứa giá trị bị override bởi command line, ALTER SYSTEM hoặc include file.

### 9.6. Config parse errors

```sql
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
```

View này phản ánh các cấu hình file mà PostgreSQL đọc; cần xem cả startup logs và cách service truyền command-line options.

### 9.7. pg_hba rules

```sql
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
```

Không xuất password hoặc secret vào inventory. Ghi lại authentication method và phạm vi rule.

### 9.8. Shared preload libraries

```sql
SHOW shared_preload_libraries;
```

Mỗi library cần xác nhận binary tương thích target và load thành công sau restart.

## 10. Kiểm kê application SQL và database objects

Tìm tất cả SQL có thể chạy trên target:
- Query trong source code.
- Stored procedures/functions.
- Trigger bodies.
- Views/materialized views.
- Migration scripts.
- Scheduled SQL jobs.
- Reporting queries.
- Administrative scripts.
- Ad hoc scripts có được dùng trong production runbook.

### 10.1. Tìm trong repository

Dùng công cụ search của repository để tìm removed/deprecated SQL syntax, removed configuration names, function/operator names được release notes đề cập, system catalog/view names, authentication options, extension-specific APIs và SQL patterns chịu ảnh hưởng của planner hoặc type semantics.

Ví dụ:

```bash
rg -n -i "recovery\.conf|wal_keep_segments|old_setting_name" .
```

Thay các tên mẫu bằng keyword thật từ release notes. Loại trừ generated files hoặc vendor code khi phù hợp, nhưng ghi rõ phạm vi đã bỏ qua.

### 10.2. Search result không chứng minh runtime usage

Một tên setting có thể xuất hiện trong tài liệu cũ hoặc test fixture. Ngược lại, SQL có thể được tạo động và không xuất hiện dưới dạng literal. Kết hợp source search, query logs, application tracing và owner interviews.

### 10.3. Tìm dynamic SQL

Kiểm tra:
- EXECUTE trong PL/pgSQL.
- SQL được tạo từ string concatenation.
- ORM-generated SQL.
- Query templates.
- Stored procedure được gọi từ application.
- ETL/BI tools tự phát sinh SQL.

### 10.4. Kiểm kê system catalog dependencies

Ứng dụng thường xuyên đọc trực tiếp pg_catalog hoặc information_schema có thể phụ thuộc vào cột/semantics nội bộ. Xác định query nào dùng catalog để monitoring, migration hoặc application logic.

Ưu tiên supported views/functions và kiểm tra release notes của catalog changes. Không coi catalog layout là API ổn định nếu tài liệu không cam kết.

## 11. Thay đổi SQL syntax và semantics

Đọc các mục release notes liên quan:
- Parser và grammar.
- Reserved keywords.
- Data types.
- Operators.
- Built-in functions.
- Casts và implicit conversions.
- Aggregate/window functions.
- JSON/JSONB.
- Date/time.
- Numeric and floating-point behavior.
- Collation and string operations.
- DDL/DML behavior.
- Privileges và RLS.

### 11.1. Reserved words

Một identifier trước đây hợp lệ có thể trở thành keyword hoặc bị xử lý khác. Kiểm tra schema/table/column/function names và dynamic SQL.

### 11.2. Function signatures

Một function có thể thay đổi overload, argument types, return type hoặc volatility/strictness behavior. Compile stored procedures và test client deserialization.

### 11.3. Implicit casts

Thay đổi cast resolution có thể khiến query không còn resolve được function overload, chọn overload khác, thất bại do ambiguous operator hoặc thay đổi execution plan/kết quả.

### 11.4. Date/time và timezone

Kiểm tra timestamp conversions, timezone database, daylight saving rules, interval arithmetic và parsing của date strings. Tránh dựa vào implicit session timezone trong business logic.

### 11.5. Ordering và collation

String sort order có thể thay đổi theo libc/ICU version. Query ORDER BY, unique indexes và application pagination có thể bị ảnh hưởng.

### 11.6. Numeric và floating-point

Kiểm tra rounding, overflow, division by zero, NaN/infinity comparisons, aggregate precision và client serialization. Test boundary values thay vì chỉ test dữ liệu thông thường.

### 11.7. JSON và JSONB

Kiểm tra function/operator semantics, path expressions, indexing, ordering assumptions và client decoding. Không giả định mọi JSON text giữ nguyên formatting sau parse/serialization.

## 12. Thay đổi configuration parameters

Đối chiếu source effective settings với target release notes và target postgresql.conf.sample.

Các loại thay đổi:
- Setting removed.
- Setting renamed.
- Setting deprecated.
- Setting mới.
- Default changed.
- Unit/range changed.
- Context changed (reload/restart).
- Semantics changed.
- Setting moved to another component/tool.

### 12.1. Removed settings

Nếu setting bị loại bỏ, xóa khỏi config template và automation sau khi thay thế behavior. Một dòng cũ có thể khiến server startup warning/error hoặc tạo cấu hình tưởng rằng có tác dụng nhưng thực tế bị bỏ qua.

### 12.2. Renamed settings

Không chỉ đổi tên. So sánh unit và semantics cũ/mới. Nếu đơn vị chuyển từ segment count sang bytes, cần chuyển đổi theo WAL segment size thực tế.

### 12.3. Default changed

Ghi cả source effective value, target default, target explicit value dự kiến, lý do chọn và test chứng minh.

Nếu tổ chức muốn giữ behavior cũ, có thể cần đặt explicit target setting. Không áp dụng máy móc giá trị cũ nếu default mới sửa lỗi hoặc cải thiện security.

### 12.4. Context changed

Setting có thể chuyển từ reloadable sang restart-required hoặc ngược lại. Deployment automation phải biết lúc nào cần restart.

### 12.5. Sample config không phải config production

File postgresql.conf.sample của target cho biết tên và default tham khảo. Nó không thay thế inventory effective configuration, include files, ALTER SYSTEM hoặc service arguments.

## 13. Ví dụ lịch sử về compatibility changes

Các ví dụ sau minh họa cách chuyển một mục release note thành hành động. Chúng chỉ áp dụng nếu dải nâng cấp thực tế đi qua các phiên bản liên quan.

### 13.1. PostgreSQL 12: recovery.conf bị loại bỏ

PostgreSQL 12 loại bỏ cách cấu hình standby/recovery bằng file recovery.conf. Các recovery parameters được chuyển vào cấu hình server và việc chọn standby/recovery mode dùng signal files như standby.signal hoặc recovery.signal.

Assessment:
- Tìm recovery.conf trong automation, image, Ansible/Chef/Puppet, scripts và runbooks.
- Kiểm tra cách tạo standby và restore workflow.
- Chuyển recovery settings vào config phù hợp.
- Tạo đúng signal file theo mục đích.
- Test standby startup, archive restore và PITR.

### 13.2. PostgreSQL 13: wal_keep_segments được thay bằng wal_keep_size

PostgreSQL 13 thay đổi cơ chế cấu hình giữ WAL tối thiểu từ wal_keep_segments sang wal_keep_size, biểu diễn theo dung lượng.

Assessment:
- Tìm wal_keep_segments trong config templates, Terraform/Ansible, scripts và monitoring.
- Xác định segment size của cluster cũ.
- Chuyển giá trị sang bytes/MB/GB theo semantics mới.
- Kiểm tra standby outage window và WAL disk budget.
- Test catch-up và disk headroom.

### 13.3. Cách dùng ví dụ

Không áp dụng hai ví dụ này nếu source/target không đi qua các major releases liên quan. Luôn mở release notes chính thức của version cụ thể để xác nhận exact behavior, migration instruction và mọi ngoại lệ.

## 14. System catalogs, monitoring views và admin scripts

Một số hệ thống có monitoring queries phụ thuộc trực tiếp vào:
- pg_stat_activity.
- pg_stat_replication.
- pg_stat_wal_receiver.
- pg_stat_archiver.
- pg_stat_database.
- pg_stat_user_tables.
- pg_stat_io.
- pg_replication_slots.
- pg_class, pg_attribute, pg_proc, pg_namespace.
- information_schema.

### 14.1. Column additions/removals

Query SELECT * vào view có thể làm exporter parse sai khi columns thay đổi. Ưu tiên liệt kê columns cần dùng.

### 14.2. Type changes

Driver/monitoring parser có thể giả định một column là integer/text trong khi target trả kiểu khác. Kiểm tra schema và output type.

### 14.3. Privilege changes

Một view/function có thể yêu cầu quyền khác hoặc trả dữ liệu đã được giới hạn. Kiểm tra monitoring role sau upgrade; không cấp superuser chỉ để làm dashboard chạy.

### 14.4. Query catalog nội bộ

Nếu application logic dựa trên catalog internals, ghi nhận như dependency có rủi ro cao và đánh giá thay bằng supported interfaces khi khả thi.

### 14.5. Exporter compatibility

Exporter có thể có logic version-specific. Kiểm tra compatibility matrix của exporter và test với target server trước khi upgrade production.

## 15. Extensions và modules

Extension thường có binary/library phụ thuộc PostgreSQL major version. Một extension được cài trên source chưa chắc có package/build cho target.

Kiểm kê:
- Extension name.
- Installed version.
- Schema.
- Owner.
- Shared preload requirements.
- Target package availability.
- Supported PostgreSQL major versions.
- Upgrade path.
- Dependencies.
- License/support status.
- Vendor release notes.

### 15.1. Inventory extension

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
ORDER BY extname;
```

### 15.2. Kiểm tra update paths

Với extension có hỗ trợ update paths, có thể kiểm tra:

```sql
SELECT *
FROM pg_extension_update_paths('extension_name');
```

Hàm và output cần được kiểm tra trên phiên bản hiện tại. Danh sách paths không chứng minh target package đã được cài hoặc upgrade thành công.

### 15.3. Extension binaries

Xác nhận target OS package có shared libraries/control files/SQL scripts tương thích target major. Cài binary trước khi thực hiện bước upgrade cần extension theo hướng dẫn của extension và PostgreSQL.

### 15.4. shared_preload_libraries

Extension cần preload phải được cấu hình trên target trước khi start nếu migration/upgrade procedure yêu cầu. Kiểm tra exact library name, load order, dependencies và restart.

### 15.5. Extension update SQL

Một số extension cần ALTER EXTENSION ... UPDATE sau server upgrade. Xác nhận version đích, update path và thứ tự update giữa các extensions phụ thuộc nhau.

### 15.6. Không chỉ kiểm tra extension có tên trong pg_extension

Một module có thể được preload nhưng không được tạo extension trong database; một shared library có thể được gọi bởi function thủ công. Inventory cần cả shared_preload_libraries, session_preload_libraries, local_preload_libraries và function dependencies khi phù hợp.

## 16. Drivers, client libraries và connection poolers

Kiểm tra các clients kết nối PostgreSQL:
- libpq.
- JDBC driver.
- psycopg/psycopg2.
- Npgsql.
- pgx.
- Node PostgreSQL clients.
- Go/Rust clients.
- ODBC drivers.
- BI/reporting connectors.
- PgBouncer và các poolers/proxies.

### 16.1. Wire protocol

PostgreSQL protocol có tính tương thích rộng, nhưng server features, authentication methods, data types, error fields và protocol extensions có thể phụ thuộc client version.

### 16.2. SCRAM và authentication

Nếu target hoặc policy dùng authentication method mới, kiểm tra driver có hỗ trợ method đó không, stored passwords có format tương thích không, pg_hba.conf rules có phù hợp không, pooler có hỗ trợ auth flow không và connection string/secret rotation có được test không.

### 16.3. TLS và certificate

Kiểm tra TLS versions, cipher policies, CA chain, hostname verification, client certificates và OpenSSL/runtime libraries. Test cả kết nối từ application containers và admin workstations.

### 16.4. Type mapping

Kiểm tra driver mapping cho numeric, UUID, JSON/JSONB, arrays, enums, ranges, timestamps, intervals và custom types. Một thay đổi type/format có thể làm serializer hoặc ORM fail.

### 16.5. Connection pooler

PgBouncer và các poolers khác có thể cần version phù hợp để hiểu authentication, protocol behavior hoặc server parameters. Test transaction pooling/session pooling, prepared statements, cancellation và failover reconnect.

### 16.6. Tool client version

psql, pg_dump, pg_restore, pg_basebackup và pg_rewind cần version compatibility riêng. Không dùng binary cũ mà chưa kiểm tra target server support.

## 17. Authentication, roles và security defaults

Release notes và security documentation có thể chứa thay đổi:
- Password encryption default.
- Authentication methods.
- TLS behavior.
- SCRAM support.
- Certificate validation.
- Role attributes.
- Privilege defaults.
- Row-level security.
- Security definer behavior.
- Extension security restrictions.
- Password/credential tooling.

### 17.1. Inventory pg_hba.conf

Ghi từng rule: connection type, database, user, address, auth method và thứ tự. Rule đầu tiên match quyết định authentication method; một rule mới đặt sai thứ tự có thể làm client fail.

### 17.2. Không export password hashes

Compatibility assessment chỉ cần biết auth method, role attributes và client capability. Không đưa password hashes/secrets vào spreadsheet, Markdown hoặc ticket.

### 17.3. SCRAM readiness

Nếu target hoặc policy dùng SCRAM, xác nhận tất cả drivers, poolers, monitoring tools, backup clients và administrative tools có thể authenticate.

### 17.4. TLS validation

Test certificate expiry, SAN/hostname, CA rotation, client cert mapping và TLS minimum version. Kết nối từ laptop không chứng minh mọi application pods đều có trust store đúng.

### 17.5. Least privilege

Nếu target thay đổi privilege defaults hoặc security checks, test application roles và maintenance roles. Tránh xử lý lỗi bằng cách cấp SUPERUSER.

## 18. Collation, locale và encoding

Locale/collation là vùng dễ bị bỏ sót vì có thể phụ thuộc OS và thư viện bên ngoài PostgreSQL.

### 18.1. Database encoding

Ghi lại encoding của từng database. Không giả định mọi database cùng encoding hoặc target có thể tự chuyển encoding mà không có data migration.

### 18.2. libc và ICU

Collation behavior có thể phụ thuộc version libc/ICU. Sau OS upgrade hoặc PostgreSQL upgrade, sort order có thể thay đổi.

### 18.3. Collation version mismatch

Một collation version khác có thể khiến indexes dựa trên collation cũ không còn phản ánh ordering mới. Kiểm tra collation metadata và actual version trên target.

### 18.4. Rebuild affected indexes

Nếu collation behavior thay đổi, đánh giá các indexes và constraints dùng collation đó. Có thể cần REINDEX theo đúng quy trình. Chỉ refresh recorded collation version sau khi xử lý indexes phụ thuộc theo hướng dẫn PostgreSQL.

### 18.5. Pagination và uniqueness

Thay đổi sort order có thể ảnh hưởng keyset pagination, ORDER BY, unique indexes, deduplication và application code giả định thứ tự chuỗi.

### 18.6. Time zone database

OS/tzdata updates có thể thay đổi lịch sử hoặc quy tắc DST cho một số timezone. Test timestamp conversions và scheduled jobs chạy qua DST boundaries.

## 19. Planner và performance compatibility

Planner changes thường không làm query fail, nhưng có thể làm latency tăng đáng kể.

Kiểm tra:
- Join order/algorithm.
- Index selection.
- Cardinality estimates.
- Parallel query.
- Partition pruning.
- CTE inlining/materialization.
- JIT.
- Statistics behavior.
- Memory settings.
- Sort/hash spill.
- Prepared statements/generic plans.

### 19.1. Capture baseline

Trước upgrade, thu thập query latency p50/p95/p99, calls/rows/blocks, EXPLAIN ANALYZE BUFFERS cho critical queries trong staging, pg_stat_statements snapshots, CPU, memory, I/O và temp file usage.

### 19.2. Không so sánh plan text một cách máy móc

Plan có thể khác nhưng performance tốt hơn. So sánh runtime, rows, buffers, I/O, temp spills và workload distribution.

### 19.3. ANALYZE sau major upgrade

Sau khi upgrade, statistics có thể cần được thu thập lại. Lập kế hoạch ANALYZE theo hướng dẫn của phương thức upgrade và size của cluster. Đánh giá autovacuum/analyze activity trước khi mở traffic đầy đủ.

### 19.4. Query regression

Chọn workload đại diện, gồm query thường xuyên, query chậm, batch jobs, reporting, DDL-heavy và peak concurrency. Một query đơn lẻ chạy nhanh trong staging không chứng minh toàn bộ workload tốt.

### 19.5. Planner settings không phải workaround mặc định

Không tắt planner feature hoặc thay đổi global cost parameters chỉ vì một query regression. Tìm nguyên nhân, cập nhật statistics/indexes/query shape và dùng setting override có phạm vi khi cần.

## 20. Data type, index và storage compatibility

Đọc notes liên quan:
- Type representation/validation.
- Index access methods.
- Operator classes/families.
- Constraints.
- Partitioning.
- TOAST.
- Large objects.
- Generated columns.
- Identity columns.
- Sequence behavior.
- Vacuum/freeze.
- WAL/recovery.

### 20.1. Indexes và operator classes

Extension hoặc custom operator class cần được build/test trên target. Kiểm tra index validity sau migration và các indexes phụ thuộc collation.

### 20.2. Partitioning

Kiểm tra attach/detach, pruning, constraint exclusion, unique constraints và partitioned index behavior. Các planner improvements có thể làm query plan thay đổi.

### 20.3. Sequences và identity

Test sequence ownership, cache behavior, nextval/currval, identity insert rules và migration scripts. Không giả định sequence state được khôi phục như table data trong mọi phương thức migration.

### 20.4. Large objects và custom types

Kiểm tra serialization, backup/restore, extension dependencies và application mapping. Đảm bảo dump/restore hoặc logical migration bao gồm các objects cần thiết.

## 21. Replication, backup và recovery compatibility

Một upgrade plan cần đánh giá:
- Physical replication.
- Logical replication.
- Replication slots.
- WAL level và WAL parameters.
- Archive command/library.
- Restore command.
- Backup software.
- pg_basebackup.
- pg_upgrade.
- pg_dump/pg_restore.
- pg_rewind.
- HA manager/DCS.
- Monitoring và alerting.

### 21.1. Physical replication giữa major versions

Không giả định physical streaming replication có thể kết nối tự do giữa hai major versions. Kiểm tra giới hạn source/target của version và phương thức migration.

### 21.2. Logical replication cho migration

Logical replication có thể được dùng cho một số major upgrade/cutover designs, nhưng cần kiểm tra publication/subscription support, DDL handling, sequence synchronization, large objects, extension objects và conflict handling.

### 21.3. Replication slots

Kiểm tra physical/logical slot compatibility, failover slot support, slot synchronization và WAL retention parameters. Một slot có thể cần recreate hoặc consumer reinitialize sau migration.

### 21.4. Backup software

Xác nhận backup tool hỗ trợ target major, backup format, catalog migration và restore version. Có một backup success không đủ; phải có restore test.

### 21.5. pg_upgrade

Dùng pg_upgrade --check theo đúng source/target binary và data directory để phát hiện một số điều kiện không tương thích. Đây không phải full application compatibility test và không thay kiểm tra extension/operational readiness.

### 21.6. Rollback backup

Giữ base backup/snapshot và WAL/archive của source theo retention plan. Khi target đã nhận writes, quay lại source cần kế hoạch đồng bộ/reconciliation; không thể coi downgrade binary là rollback đầy đủ.

## 22. Utilities và automation

Đọc release notes của:
- pg_dump/pg_restore.
- pg_upgrade.
- pg_basebackup.
- pg_rewind.
- psql.
- vacuumdb.
- reindexdb.
- clusterdb.
- createdb/dropdb.
- initdb.
- pg_ctl.
- pg_config.
- Backup vendor tools.

### 22.1. Binary path

Automation có thể gọi binary bằng PATH và vô tình dùng version cũ sau khi package mới cài. Ghi absolute path hoặc xác minh --version.

### 22.2. Option changes

Tìm options removed/renamed, default output format, exit codes, warnings, environment variables và config file locations.

### 22.3. Output parsing

Scripts parse text output có thể fail khi format/columns thay đổi. Ưu tiên machine-readable output hoặc kiểm tra version-specific output.

### 22.4. Shell và OS dependencies

Một script archive/backup có thể phụ thuộc bash, tar, gzip, openssl, rsync, filesystem semantics hoặc cloud CLI. Kiểm tra cả tool versions và permission model trên target host.

## 23. Operating system và package compatibility

Major PostgreSQL version có thể thay đổi requirements cho supported operating systems, CPU architectures, compiler/toolchain, OpenSSL/LDAP/Kerberos libraries, ICU/libxml/libxslt, Python/Perl/Ruby extensions, filesystem/kernel features, package repositories và container base images.

### 23.1. Package source

Ghi lại PostgreSQL packages đến từ distro repository, PostgreSQL community repository, vendor image hay custom build.

### 23.2. Extension packages

Extension package name có thể khác theo major version hoặc distro. Cài đúng package cho target trước khi chạy extension upgrade.

### 23.3. Container images

Pin image tag/digest, OS base, extension packages, CA certificates và runtime dependencies. Không dùng floating latest cho production upgrade.

### 23.4. System libraries

Một extension có thể load trên source host nhưng fail trên target do thiếu shared library hoặc ABI mismatch. Kiểm tra package dependencies và startup logs.

## 24. Từ release note thành compatibility register

Compatibility register là danh sách có cấu trúc để biến từng thay đổi thành việc cần xử lý và bằng chứng kiểm tra.

| Trường | Nội dung |
|---|---|
| ID | Mã mục duy nhất |
| Source/target | Dải phiên bản liên quan |
| Release note | URL và section/heading |
| Change summary | Mô tả ngắn thay đổi |
| Change class | Removed, behavior, default, security, performance... |
| Component | Server, SQL, app, extension, driver, OS, tooling |
| Current usage | Bằng chứng hệ thống đang dùng |
| Target behavior | Behavior/version requirement mới |
| Impact | Thành phần và luồng nghiệp vụ bị ảnh hưởng |
| Severity | Blocker, High, Medium, Low, Info |
| Action | Sửa code/config/package/process |
| Owner | Người/team chịu trách nhiệm |
| Validation | Test và expected result |
| Status | Open, Investigating, Planned, Fixed, Tested, Accepted |
| Evidence | PR, test run, config diff, approval |

### 24.1. Một mục phải có action hoặc lý do no-impact

Nếu thay đổi có thể áp dụng nhưng hệ thống không sử dụng, ghi usage search đã thực hiện, inventory nào đã kiểm tra, kết quả không tìm thấy dependency, người xác nhận và evidence link.

Không ghi N/A mà không có căn cứ.

### 24.2. Tách một mục release note thành nhiều impacts

Một thay đổi có thể ảnh hưởng application config, monitoring, backup automation và staging. Tạo các child actions hoặc nhiều register rows để mỗi owner có thể xử lý độc lập.

### 24.3. Không gộp nhiều thay đổi khác nhau

Một dòng “PostgreSQL 17 changes” không đủ để review. Mỗi item cần trỏ tới một release note/behavior cụ thể.

## 25. Severity và priority

| Mức | Định nghĩa | Ví dụ |
|---|---|---|
| Blocker | Upgrade không thể hoàn thành hoặc hệ thống không thể chạy an toàn | Extension bắt buộc không có target build |
| High | Có khả năng làm hỏng core workload/security/DR | Authentication client không tương thích |
| Medium | Cần thay đổi hoặc test có mục tiêu; có workaround | Config default làm thay đổi performance |
| Low | Tác động nhỏ, phạm vi hạn chế | Admin script cần sửa output parser |
| Info | Không có usage hiện tại, lưu để tham khảo | Feature mới chưa dùng |

### 25.1. Severity không phải priority

Severity đo hậu quả nếu vấn đề xảy ra. Priority đo thứ tự xử lý dựa trên thời gian, dependency và nguồn lực.

### 25.2. Risk score

Có thể đánh giá likelihood, impact, detectability và mitigation. Không cần một công thức số học phức tạp nếu nó làm team mất thời gian tranh luận về điểm. Quan trọng là định nghĩa nhất quán và có owner.

### 25.3. Blocker phải có exit criteria

Ví dụ: “Extension X chưa có package cho target” chỉ được đóng khi package được cài, extension update thành công và test workload hoàn tất.

## 26. Ví dụ compatibility register

Giả sử một hệ thống có source 12.x và target 13.x. Đây là ví dụ minh họa các mục lịch sử:

| ID | Thay đổi | Usage evidence | Impact | Action | Validation |
|---|---|---|---|---|---|
| PG-COMP-01 | recovery.conf bị loại bỏ từ PG12 | Có file trong standby provisioning | Standby bootstrap không đúng | Chuyển recovery settings và signal-file logic | Tạo standby mới, restart, replay WAL |
| PG-COMP-02 | wal_keep_segments thay bằng wal_keep_size từ PG13 | Có trong config template | Setting cũ không còn phù hợp | Chuyển đơn vị và cập nhật template | Kiểm tra effective setting, standby catch-up |
| PG-COMP-03 | Extension package target chưa xác nhận | pg_extension cho thấy extension đang cài | Cluster có thể không start hoặc extension không load | Xác nhận vendor build và upgrade path | Restore staging, update extension, smoke test |
| PG-COMP-04 | Planner behavior thay đổi | Query report thuộc top workload | Latency có thể thay đổi | Capture baseline và regression test | Compare runtime, buffers, p95/p99 |
| PG-COMP-05 | Driver SCRAM support chưa xác nhận | App đang dùng driver cũ | Client có thể không authenticate | Nâng driver/pooler nếu cần | Connection test từ từng app runtime |

### 26.1. Tách fact và impact

Mục PG-COMP-01 ghi fact về release notes. “Standby bootstrap không đúng” là impact chỉ được đánh dấu confirmed khi inventory tìm thấy provisioning dùng recovery.conf.

### 26.2. Một row có thể có nhiều owners

DBA có thể xử lý config, Platform xử lý image, Application team xử lý driver. Dùng child tasks để mỗi owner có deadline và evidence riêng.

## 27. Quy trình assessment từng bước

1. **Freeze scope:** ghi source version, target version, environments, topology và thời gian dự kiến nâng cấp.
2. **Thu thập release notes:** tạo danh sách official URLs cho tất cả major versions trong dải, minor releases liên quan và extension/vendor release notes.
3. **Đọc migration notes:** đánh dấu các mục yêu cầu thao tác trước upgrade, thay đổi config, removed settings và upgrade constraints.
4. **Đọc các nhóm còn lại:** review server, SQL, utilities, client interfaces, security, performance, platform và extension-related notes.
5. **Trích xuất change candidates:** mỗi candidate có version, heading, summary và source link. Giữ cả bug/security fixes có thể ảnh hưởng workload.
6. **Thu thập baseline:** export versions, settings, extensions, collations, roles/auth methods, replication, backup và monitoring inventory.
7. **Map change tới usage:** search code/config, inspect database metadata, query logs, owner interviews và vendor matrices.
8. **Phân loại impact:** đánh dấu confirmed, possible, no usage found hoặc unknown. Gán severity và owner.
9. **Xác định remediation:** viết action cụ thể: config migration, code change, driver upgrade, extension package, reindex, backup procedure hoặc test.
10. **Thiết kế validation:** mỗi action phải có test input, expected result, environment và evidence location.
11. **Rehearse:** restore staging từ backup hoặc clone gần production, thực hiện upgrade rehearsal, chạy regression tests và đo performance.
12. **Review và sign-off:** DBA, application, platform, security, backup/DR và product owners xác nhận các items liên quan.

## 28. Tạo release notes reading log

Ngoài compatibility register, giữ reading log để chứng minh phạm vi đã review.

| Field | Example |
|---|---|
| Product | PostgreSQL |
| Source version | 14.9 |
| Target version | 17.4 |
| Release family reviewed | 15, 16, 17 |
| Minor notes | Source/target minor notes trong scope |
| Sections | Migration, Server, SQL, Utilities, Client, Security |
| Reviewer | DBA/engineer |
| Review date | YYYY-MM-DD |
| URL | Official release notes |
| Result | Reviewed / Follow-up required |

Nếu target minor thay đổi từ 17.4 thành 17.5, cập nhật reading log và đọc phần notes mới phát sinh. Ghi rõ exclusions và lý do. Với compliance, lưu URL/version/heading và ngày review; có thể lưu snapshot nội bộ theo policy.

## 29. Test strategy cho compatibility

Chia test theo lớp:

**Static review**
- Search removed settings/API.
- Parse config templates.
- Check extension package matrix.
- Review driver versions.
- Review SQL/catalog dependencies.

**Database tests**
- Restore source backup lên staging.
- Upgrade staging bằng phương thức dự kiến.
- Validate database startup and catalogs.
- Reindex/ANALYZE nếu cần.
- Run schema and data checks.

**Application tests**
- Connection/authentication.
- CRUD and transaction semantics.
- Stored procedures/triggers.
- ORM migrations.
- Batch/ETL/reporting.
- Error handling and retries.

**Operational tests**
- Backup and restore.
- WAL archive and PITR.
- Replication and failover.
- Monitoring/exporters.
- Connection pooler behavior.
- Restart/reboot and service automation.

**Performance tests**
- Critical query plans.
- Throughput and latency percentiles.
- CPU, memory, I/O, temp files.
- Concurrent workload and peak load.

## 30. Regression test design

Một test tốt liên kết trực tiếp với compatibility item.

Mỗi test cần requirement/behavior, source version expected result, target version expected result, input data and boundary cases, SQL/application operation, expected output/state, runtime threshold nếu cần, test owner và evidence/timestamp.

### 30.1. Test business behavior

Không chỉ test SQL có execute được. Kiểm tra kết quả business: amount, ordering, permissions, timezone, uniqueness, retry semantics và transaction boundaries.

### 30.2. Test boundary values

Ưu tiên NULL, empty string/array/JSON, large numeric values, timestamp gần DST transitions, Unicode/collation edge cases, duplicate keys, long-running transactions, concurrent DDL/DML, large objects/large rows và high-volume WAL.

### 30.3. Test error behavior

Application có thể dựa vào SQLSTATE, constraint names, error message parsing hoặc retry policy. Kiểm tra các lỗi authentication, serialization, deadlock, cancellation và connection reset.

### 30.4. Test extensions

Chạy extension-specific tests và representative functions/indexes. Kiểm tra extension version, schema objects, shared libraries và startup logs.

## 31. Performance comparison

Performance test cần workload tương đương.

### 31.1. Baseline source

Ghi query fingerprints, calls/rows, mean/p95/p99 latency, shared/local/temp blocks, CPU utilization, storage IOPS/latency, WAL bytes/sec, lock waits và connection counts.

### 31.2. Target environment

Dùng hardware/storage/network tương đương hoặc ghi rõ khác biệt. Nếu staging nhỏ hơn production, không so sánh absolute latency một cách trực tiếp.

### 31.3. EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...
FROM ...
WHERE ...;
```

Chỉ chạy EXPLAIN ANALYZE trên query an toàn trong staging hoặc production theo quy trình đã phê duyệt vì nó thực thi statement.

### 31.4. Query plan diff

Ghi plan source và target, nhưng đánh giá theo actual runtime, rows, buffers, I/O và workload. Một plan khác không tự động là regression.

### 31.5. Cold/warm cache

Test cả cold-start và steady-state khi chúng quan trọng. Không để một lần run duy nhất quyết định kết quả.

## 32. Staging upgrade rehearsal

Staging rehearsal nên gần production nhất có thể.

1. Tạo backup/clone có tính đại diện.
2. Mask dữ liệu nhạy cảm theo policy nếu cần.
3. Cài target binaries và extension packages.
4. Chạy pre-upgrade checks.
5. Thực hiện upgrade bằng phương thức dự kiến.
6. Xử lý extension upgrades và collation/index requirements.
7. Chạy ANALYZE theo plan.
8. Chạy database/application regression tests.
9. Chạy backup, archive, replication và failover tests.
10. Đo performance.
11. Ghi thời gian từng bước và issue.
12. Lặp lại sau khi sửa blocker.

### 32.1. Rehearsal phải có timing

Ghi thời gian backup, pg_upgrade/dump restore, reindex, analyze, application smoke tests và cutover. Dùng số liệu để xác định maintenance window.

### 32.2. Rehearsal phải có recovery path

Test restore source backup và recovery nếu target không khởi động. Đừng chỉ luyện đường upgrade thành công.

### 32.3. Production-like configuration

Dùng cùng config management, extension versions, service accounts, TLS, authentication, monitoring và backup tools. Một staging chỉ có PostgreSQL core có thể bỏ lỡ dependency quan trọng.

## 33. Phân biệt compatibility assessment và upgrade method

Compatibility assessment trả lời “những gì cần thay đổi và kiểm thử?”. Upgrade method trả lời “làm sao chuyển database từ source sang target?”.

Các phương thức phổ biến:
- pg_upgrade.
- Dump/restore với pg_dump/pg_restore.
- Logical replication hoặc migration tooling.
- Vendor/cloud-managed upgrade workflow.

### 33.1. pg_upgrade

Thường giảm thời gian chuyển dữ liệu lớn bằng cách chuyển/reuse data files theo cơ chế được hỗ trợ. Cần source/target binaries, extension compatibility, filesystem constraints và pre-checks.

### 33.2. Dump/restore

Tạo logical dump và restore vào target. Có thể phù hợp khi cần thay đổi storage/encoding/schema hoặc không thể dùng pg_upgrade, nhưng thời gian phụ thuộc dữ liệu và index rebuild.

### 33.3. Logical migration

Có thể giảm downtime nhưng đòi hỏi xử lý replication, DDL, sequences, large objects, extension objects, write freeze/cutover và consistency. Không phải mọi workload đều phù hợp.

### 33.4. Chọn method sau compatibility inventory

Nếu extension hoặc data feature không được hỗ trợ bởi method, đưa nó thành blocker và chọn phương án khác. Đừng chọn upgrade method trước khi biết dependencies.

## 34. Rollback và downgrade planning

Rollback phải được thiết kế trước khi production cutover.

### 34.1. Giữ source recoverable

Giữ source data directory/backup/snapshot, binaries, configuration, extension packages và WAL/archive theo policy.

### 34.2. Xác định rollback boundary

Trước khi target nhận writes, quay về source có thể tương đối đơn giản nếu source được giữ nguyên và cutover chưa hoàn tất. Sau khi target nhận writes, source không tự có các thay đổi mới.

### 34.3. Không coi downgrade binary là rollback

Không start data directory của target bằng source binaries. PostgreSQL major upgrade không cung cấp downgrade tổng quát bằng cách thay binary.

### 34.4. Reconciliation sau writes

Nếu phải quay lại source sau khi target đã nhận writes, cần một chiến lược đồng bộ/reconciliation đã thiết kế và test. Có thể cần logical export, reverse replication nếu topology/tooling hỗ trợ hoặc restore theo recovery plan. Không improvisation trong incident.

### 34.5. Rollback criteria

Định nghĩa trước target startup failure, critical application test failure, data validation mismatch, authentication outage, performance vượt SLA, backup/replication không hoạt động và cutover không hoàn thành trong maintenance window.

## 35. Change list cho production cutover

Mỗi item cần trạng thái và evidence.

**Pre-upgrade**
- Release notes review complete.
- Extension packages available.
- Drivers/poolers supported.
- Removed config settings replaced.
- Backup and restore verified.
- Source baseline captured.
- Target config reviewed.
- Maintenance window and owners confirmed.

**Upgrade execution**
- Source writes frozen/drained theo method.
- Backup/snapshot verified.
- Target binaries/packages installed.
- Upgrade command/workflow completed.
- Extension SQL updates completed.
- Collation/index actions completed.
- ANALYZE/statistics plan executed.

**Post-upgrade**
- Server version confirmed.
- Database consistency checks complete.
- Roles/grants/authentication verified.
- Applications connected.
- Critical transactions pass.
- Query latency/throughput within SLA.
- Replication and archive healthy.
- Backup and PITR tested.
- Monitoring/alerts healthy.
- Old cluster retained per rollback policy.

## 36. Compatibility review meeting

Một review hiệu quả cần đại diện DBA/database engineering, application owners, platform/infrastructure, security/IAM, backup/DR, SRE/Operations, data/BI/ETL owners và extension/vendor owner.

### 36.1. Câu hỏi cần trả lời

1. Tất cả major versions trung gian đã được review chưa?
2. Minor/security notes trong scope đã được review chưa?
3. Mọi removed/deprecated settings có owner chưa?
4. Extension packages và update paths đã xác nhận chưa?
5. Drivers/poolers có hỗ trợ target không?
6. Locale/collation changes đã được đánh giá chưa?
7. Query regressions đã được test chưa?
8. Backup/PITR/replication/failover đã được rehearsal chưa?
9. Mọi blocker đã đóng chưa?
10. Ai có quyền quyết định go/no-go?

### 36.2. Không đóng mục chỉ bằng lời nói

Một item nên được đóng bằng evidence: test report, PR/config commit, vendor compatibility matrix, package build, restore log hoặc signed acceptance.

### 36.3. Chấp nhận rủi ro có chủ đích

Nếu một item không thể xử lý trước upgrade, ghi rõ impact, workaround, owner, expiration date và người chấp nhận. Không giấu item trong ghi chú tự do.

## 37. Go/no-go criteria

Một upgrade có thể được xem xét go khi:
- Release notes range đã review đầy đủ.
- Không còn blocker mở.
- High-risk items có remediation/test/acceptance.
- Extension và client compatibility đã xác nhận.
- Backup restore/PITR có evidence.
- Staging rehearsal đạt.
- Performance nằm trong SLA hoặc có approved mitigation.
- Cutover/rollback runbooks đã được review.
- Owners và on-call coverage đã xác nhận.
- Monitoring và alerting sẵn sàng.

No-go khi:
- Không biết target version chính xác.
- Chưa có backup restore proof.
- Extension bắt buộc không tương thích.
- Fencing/replication/DR behavior chưa rõ.
- Authentication path chưa được test.
- Có blocker chưa có owner hoặc mitigation.
- Staging rehearsal chưa hoàn tất.

## 38. Những lỗi thường gặp khi đọc release notes

| Lỗi | Hậu quả |
|---|---|
| Chỉ đọc release notes target major | Bỏ sót thay đổi từ major trung gian |
| Chỉ đọc mục feature mới | Bỏ qua removed/default/behavior/security changes |
| Bỏ qua minor release notes | Không thấy bug/security fixes liên quan |
| Không kiểm kê usage hiện tại | Không biết thay đổi có ảnh hưởng hệ thống không |
| Coi setting trong file config là effective value | Bỏ qua override từ include/ALTER SYSTEM/CLI |
| Chỉ search source code | Bỏ sót dynamic SQL và runtime-generated queries |
| Bỏ qua extension vendors | Server upgrade xong extension không load |
| Bỏ qua client drivers/poolers | Applications không authenticate hoặc type mapping lỗi |
| Không kiểm tra collation/ICU | Ordering/index behavior thay đổi |
| Coi bug fix không ảnh hưởng compatibility | Ứng dụng phụ thuộc behavior lỗi cũ |
| Chỉ test server startup | Không phát hiện application/operational regression |
| Không test backup restore | Không thể chứng minh recovery path |
| Không ghi evidence | Không thể review hoặc audit quyết định |
| Ghi N/A không có lý do | Unknown dependency bị coi nhầm là no impact |
| Không có rollback boundary | Incident sau cutover không có phương án rõ |

## 39. Template compatibility register

Có thể dùng cấu trúc Markdown sau làm khởi điểm; trong dự án thực tế, lưu ở tracker hoặc spreadsheet để quản lý owner/status.

| ID | Version | Release note / section | Change class | Component | Current usage/evidence | Impact | Severity | Action | Owner | Validation | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| PG-COMP-001 |  |  |  |  |  |  |  |  |  |  | Open |
| PG-COMP-002 |  |  |  |  |  |  |  |  |  |  | Open |
| PG-COMP-003 |  |  |  |  |  |  |  |  |  |  | Open |

### 39.1. Quy ước status

- `Open`: chưa điều tra.
- `Investigating`: đang xác minh usage/impact.
- `Planned`: đã có action/owner.
- `Fixed`: đã thay đổi code/config/package.
- `Tested`: validation thành công, có evidence.
- `Accepted`: rủi ro được owner có thẩm quyền chấp nhận.
- `Blocked`: không thể tiếp tục do dependency hoặc thiếu hỗ trợ.

### 39.2. Quy ước impact confidence

- `Confirmed`: có evidence usage và test.
- `Likely`: có dấu hiệu nhưng chưa chứng minh runtime.
- `No usage found`: đã tìm trong các inventory đã liệt kê.
- `Unknown`: chưa đủ dữ liệu.

Không dùng `No usage found` khi chỉ search một repository.

## 40. Checklist đọc release notes

- [ ] Ghi source major/minor chính xác.
- [ ] Ghi target major/minor chính xác.
- [ ] Liệt kê mọi major version trung gian.
- [ ] Đọc Migration notes của từng major.
- [ ] Đọc Server changes.
- [ ] Đọc SQL/function/type/operator changes.
- [ ] Đọc configuration changes/default changes.
- [ ] Đọc system catalog và monitoring view changes.
- [ ] Đọc utilities/client interfaces changes.
- [ ] Đọc security/authentication/TLS changes.
- [ ] Đọc planner/performance/bug fixes có liên quan.
- [ ] Đọc platform/build requirements.
- [ ] Đọc extension/vendor release notes.
- [ ] Ghi URL, section, version và review date.
- [ ] Ghi exclusions và lý do.

## 41. Checklist inventory và compatibility

- [ ] Server versions trên tất cả environments.
- [ ] Database encodings/locales/collations.
- [ ] Effective server configuration.
- [ ] pg_hba authentication methods.
- [ ] Extensions và target packages.
- [ ] shared_preload_libraries và related modules.
- [ ] Drivers, poolers, ORM và application runtimes.
- [ ] SQL, PL/pgSQL, dynamic SQL và migration scripts.
- [ ] Direct catalog dependencies.
- [ ] Backup/restore tools và PITR archive.
- [ ] Replication slots/WAL/standby/HA manager.
- [ ] Monitoring exporters and dashboards.
- [ ] OS, architecture, libraries và package source.
- [ ] Collation/ICU/tzdata dependencies.
- [ ] Jobs, cron, ETL và BI clients.
- [ ] Owners và evidence cho từng dependency.

## 42. Checklist validation và go/no-go

- [ ] Mỗi change candidate có impact classification.
- [ ] Mỗi affected component có owner.
- [ ] Mỗi blocker có remediation.
- [ ] Config target đã review effective values.
- [ ] Extensions đã install/update trên staging.
- [ ] Client authentication đã test.
- [ ] SQL/application regression suite đã pass.
- [ ] Critical query performance đã so sánh.
- [ ] Collation/index actions đã hoàn tất.
- [ ] Backup restore/PITR đã rehearsal.
- [ ] Replication/failover đã test.
- [ ] Monitoring/alerts đã kiểm tra.
- [ ] Upgrade duration nằm trong maintenance window.
- [ ] Rollback criteria và recovery path đã review.
- [ ] Go/no-go owners đã sign off.

## 43. Tài liệu chính thức tham khảo

- [PostgreSQL Release Notes](https://www.postgresql.org/docs/release/): release notes theo các phiên bản PostgreSQL.
- [PostgreSQL Documentation — Release Notes](https://www.postgresql.org/docs/current/release.html): release notes của phiên bản tài liệu hiện hành.
- [PostgreSQL Documentation — Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html): các phương thức nâng cấp cluster.
- [PostgreSQL Documentation — pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): kiểm tra và nâng cấp bằng pg_upgrade.
- [PostgreSQL Documentation — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical backup và compatibility của dump utility.
- [PostgreSQL Documentation — ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html): cập nhật extension.
- [PostgreSQL Documentation — Collation Support](https://www.postgresql.org/docs/current/collation.html): locale/collation và version behavior.
- [PostgreSQL Documentation — Authentication](https://www.postgresql.org/docs/current/client-authentication.html): client authentication và pg_hba.
- [PostgreSQL Documentation — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): baseline monitoring views.
- [PostgreSQL Documentation — Release Policy](https://www.postgresql.org/support/versioning/): vòng đời hỗ trợ và version policy.

Với extension, driver, pooler, backup tool và cloud service, đọc thêm compatibility matrix/release notes của chính nhà cung cấp. Các đường dẫn /current/ thay đổi theo phiên bản tài liệu hiện hành; khi assessment cần lưu URL/version cụ thể đã review.

## 44. Tổng kết

Đọc release notes là bước khởi đầu của compatibility assessment. Để biến thông tin đó thành kế hoạch nâng cấp có thể thực thi, cần nối từng thay đổi với inventory thực tế, đánh giá impact, chỉ định owner và yêu cầu evidence.

1. **Phạm vi phiên bản:** đọc notes của mọi major version trung gian và target, cùng minor/security notes có liên quan.
2. **Phân loại:** tìm removed, deprecated, behavior, default, SQL/API, catalog, security, performance, extension, utility và platform changes.
3. **Inventory:** thu thập config effective, database objects, extensions, drivers, application SQL, collations, backup, replication và OS dependencies.
4. **Compatibility register:** ghi source link, usage evidence, target behavior, severity, action, owner, validation và status.
5. **Testing:** rehearsal upgrade trên staging, chạy application regression, query performance, backup/PITR, replication và operational tests.
6. **Decision:** đóng blockers, ghi nhận accepted risks, xác định rollback boundary và yêu cầu go/no-go evidence.

Một compatibility list tốt cho biết thay đổi nào thực sự chạm tới hệ thống, ai chịu trách nhiệm xử lý, cách chứng minh đã xử lý và điều kiện nào phải đạt trước khi production được nâng cấp.
