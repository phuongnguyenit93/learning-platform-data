# Di chuyển dữ liệu trực tuyến và xác minh trước chuyển đổi trong PostgreSQL

Di chuyển một PostgreSQL database trực tuyến có nghĩa là chuyển dữ liệu và workload sang một hệ thống đích trong khi hệ thống nguồn vẫn tiếp tục phục vụ ứng dụng trong phần lớn thời gian chuẩn bị. Mục tiêu là giảm downtime, giữ dữ liệu nhất quán và có bằng chứng đủ tin cậy trước khi đổi ứng dụng sang đích.

Một phương pháp phổ biến là **logical replication**: tạo schema tương thích trên subscriber, nạp dữ liệu ban đầu, tiếp tục nhận các thay đổi phát sinh trên publisher, xác minh độ đầy đủ và tính đúng đắn của dữ liệu, rồi tạo một điểm chốt để cutover. Cách làm này hữu ích khi nâng cấp major version, chuyển sang hạ tầng mới, đổi storage, tách workload hoặc di chuyển sang một cluster độc lập.

Migration online không chỉ là tạo publication và subscription. Cần chuẩn bị schema, indexes, constraints, sequences, roles, extensions, large objects, jobs, application configuration và các phụ thuộc ngoài database. Phải đo replication lag, kiểm soát writes ở thời điểm cutover và có kế hoạch rollback thực tế.

Bài học này trình bày quy trình end-to-end cho PostgreSQL native logical replication, cách xác minh trước chuyển đổi, các giới hạn cần xử lý riêng và những tình huống khiến migration không thể hoàn tất an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định phạm vi và yêu cầu của một migration PostgreSQL online.
2. Phân biệt migration online với physical failover, backup restore và offline dump/restore.
3. Đánh giá version compatibility và các tính năng logical replication.
4. Inventory schema, tables, data types, extensions, sequences và external dependencies.
5. Chuẩn bị publisher, subscriber, publication và subscription.
6. Lập kế hoạch initial data copy trong khi source tiếp tục nhận writes.
7. Theo dõi logical changes và replication lag.
8. Xác minh schema, row counts, keys, aggregates và dữ liệu theo từng chunk.
9. Xác minh sequences, roles, grants, extensions, indexes và constraints.
10. Tạo một barrier/marker để xác nhận subscriber đã apply toàn bộ changes trước cutover.
11. Thực hiện cutover với write freeze và endpoint switch có kiểm soát.
12. Ngăn dual writes và split brain sau khi chuyển đổi.
13. Xây dựng rollback plan cho cả trước và sau khi target bắt đầu nhận writes.
14. Xử lý apply errors, schema drift, slot retention và resynchronization.
15. Lập checklist, monitoring, runbooks và 80 bài tập thực hành.

## 2. Migration online là gì?

Migration online chuyển dữ liệu và workload từ source sang target với downtime được giới hạn vào một cửa sổ ngắn, thường dành cho việc dừng writes, chốt replication, xác minh cuối và chuyển endpoint.

~~~text
Ứng dụng đang ghi
       |
       v
Source PostgreSQL (publisher)
       |
       +---- Initial data copy ----------------------+
       |                                             |
       +---- Logical changes / CDC ------------------+
                                                     |
                                                     v
Target PostgreSQL (subscriber)
       |
       v
Validate schema + data + metadata
       |
       v
Freeze writes -> catch up -> barrier -> cutover
       |
       v
Ứng dụng ghi vào target
~~~

### 2.1. Source và target

- **Source/publisher**: cluster đang phục vụ workload và phát các thay đổi được publish.
- **Target/subscriber**: cluster mới nhận initial data và logical changes.
- **Cutover**: thời điểm ứng dụng ngừng ghi source và bắt đầu ghi target.
- **Catch-up**: quá trình subscriber apply các changes còn tồn đọng.
- **Rollback window**: khoảng thời gian có thể quay lại source theo một quy trình đã định nghĩa.

### 2.2. Migration online không đồng nghĩa zero downtime

Một migration có thể giảm downtime đáng kể, nhưng vẫn cần một giai đoạn write freeze hoặc maintenance window để chốt dữ liệu. Nếu ứng dụng không thể dừng writes hoặc không có cơ chế fencing, việc bảo đảm một điểm chuyển đổi nhất quán sẽ khó hơn nhiều.

### 2.3. Migration không chỉ chuyển rows

Một hệ thống PostgreSQL còn có schema, indexes, constraints, sequences, roles, grants, extensions, configuration, jobs, secrets, certificates, connection pools và integrations. Phải kiểm kê toàn bộ phần ứng dụng cần để hoạt động.

## 3. Chọn chiến lược migration

Không phải mọi migration đều cần logical replication.

| Chiến lược | Phù hợp khi | Downtime và giới hạn |
| --- | --- | --- |
| Logical replication | Cần đồng bộ liên tục sang cluster độc lập, chọn bảng, có thể khác major version | DDL/sequence/large objects và cutover phải xử lý riêng |
| Physical replication | Cần standby tương thích cùng major version hoặc thay hạ tầng mà giữ cluster vật lý | Sao chép toàn cluster; không phải đường upgrade trực tiếp giữa major versions |
| pg_dump/pg_restore | Database vừa/nhỏ, downtime chấp nhận được, muốn quy trình đơn giản | Downtime thường dài hơn vì dump và restore |
| Backup + PITR | Cần dựng lại trạng thái tại thời điểm hoặc DR | Không tự đồng bộ liên tục sang target đang chạy |
| Tool migration chuyên dụng | Cần orchestration, parallel copy, CDC và validation nâng cao | Phụ thuộc capabilities/semantics của tool |

### 3.1. Dùng logical replication khi nào?

- Chuyển sang PostgreSQL major version mới hơn với version pair được hỗ trợ.
- Chuyển từ máy vật lý sang cloud/managed PostgreSQL.
- Chỉ di chuyển một tập database tables.
- Tách một workload thành cluster riêng.
- Duy trì source hoạt động trong khi target được nạp dữ liệu.
- Cần một luồng CDC trong thời gian migration.

### 3.2. Dùng physical replication khi nào?

- Chuyển primary sang standby cùng major version.
- Cần HA/failover cho toàn cluster.
- Muốn giữ nguyên trạng thái vật lý của cluster.
- Không cần đổi major version hoặc schema.

### 3.3. Dùng dump/restore khi nào?

- Dữ liệu đủ nhỏ để nằm trong maintenance window.
- Muốn chuyển toàn bộ schema và data qua một quy trình logical dump.
- Có thể dừng writes trong thời gian export/import.
- Không cần duy trì source online lâu.

### 3.4. Quyết định dựa trên RPO/RTO và downtime budget

Ghi rõ downtime tối đa, RPO trong thời gian migration, RTO nếu cutover thất bại, dung lượng dữ liệu và tốc độ thay đổi, network bandwidth, khả năng provision target, rollback window và thời điểm không thể quay lại đơn giản.

## 4. Khảo sát hệ thống nguồn

Bắt đầu bằng discovery. Không tạo publication trước khi biết dữ liệu nào cần chuyển và những object nào không nằm trong logical replication.

### 4.1. Phiên bản PostgreSQL

~~~sql
SELECT version();

SHOW server_version;
SHOW server_version_num;
SHOW wal_level;
~~~

Ghi nhận version của source, target, pg_dump, pg_restore, pg_basebackup và các extension. Kiểm tra tài liệu compatibility cho đúng cặp major versions.

### 4.2. Database inventory

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
~~~

Logical publication/subscription hoạt động trong phạm vi một database. Nếu source có nhiều databases, lập kế hoạch riêng cho từng database hoặc chọn chiến lược khác.

### 4.3. Table inventory

~~~sql
SELECT
    schemaname,
    tablename,
    n_live_tup,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', schemaname, tablename)::regclass
        )
    ) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, tablename)::regclass
) DESC;
~~~

n_live_tup là ước lượng thống kê, không phải exact row count. Dùng nó để sắp xếp inventory; validation cuối cần phép đo chính xác hoặc phương pháp checksum có kiểm soát.

### 4.4. Tables cần xử lý riêng

Inventory:
- Tables không có primary key.
- Tables có UPDATE/DELETE nhưng thiếu replica identity phù hợp.
- Partitioned tables.
- Unlogged tables.
- Temporary tables.
- Tables chứa generated columns hoặc data types đặc biệt.
- Large objects.
- Tables được ghi bởi extension hoặc background process.
- Tables có triggers và foreign keys phức tạp.
- Tables quá lớn cần chia chunk hoặc bulk-load riêng.

### 4.5. Schema objects

Liệt kê và lưu:
- Schemas và tables.
- Views và materialized views.
- Functions, procedures và triggers.
- Sequences và identity columns.
- Types, domains và collations.
- Indexes, constraints và partition definitions.
- Publications/subscriptions hiện có.
- Extensions và versions.
- Roles, memberships, grants và default privileges.

### 4.6. External dependencies

Logical replication không chuyển PostgreSQL configuration files, TLS certificates và secrets, application binaries/configuration, scheduled jobs bên ngoài database, object storage contents, message queues, foreign servers/credentials và external service state. Đưa các dependencies này vào migration checklist.

## 5. Kiểm tra version compatibility

Logical replication có thể hỗ trợ migration giữa một số major versions khác nhau, nhưng không nên giả định mọi hướng và mọi feature đều tương thích.

Kiểm tra:
1. Source và target major versions.
2. Publisher/subscriber version direction.
3. Logical replication protocol compatibility.
4. Publication features có được hỗ trợ ở cả hai phía.
5. Data types, collations và extension compatibility.
6. Generated columns, partitioning và identity behavior.
7. DDL khác biệt giữa versions.
8. Slot failover/synchronization capabilities nếu topology cần.
9. Bug fixes và known limitations của minor versions.

### 5.1. Source cũ sang target mới

Đây là hướng thường gặp khi major-version migration. Subscriber mới có thể nhận logical changes từ publisher cũ nếu cặp phiên bản được hỗ trợ. Kiểm tra PostgreSQL documentation cho đúng version pair trước khi triển khai.

### 5.2. Dùng binary phù hợp

Dùng psql, pg_dump, pg_restore và replication tools từ bộ client tương thích với target/source. Không dùng một binary cũ rồi giả định nó hiểu mọi option mới.

### 5.3. Extension compatibility

Extension có thể cần:
- Phiên bản tương thích với target.
- Cài shared libraries trước khi restore schema.
- Upgrade script phù hợp.
- Kiểm tra operator classes, data types và functions.
- Kiểm tra extension có tạo background workers hoặc dữ liệu ngoài bảng hay không.

## 6. Lập migration inventory và mapping

Tạo bảng mapping để biết mỗi object được xử lý thế nào.

| Object | Source | Target | Phương thức | Validation |
| --- | --- | --- | --- | --- |
| Table rows | app.orders | app.orders | Initial copy + logical changes | Count, keys, totals |
| Table schema | app.orders | app.orders | Migration DDL | Schema diff |
| Sequence | orders_id_seq | orders_id_seq | Đồng bộ riêng | last_value/max(id) |
| Roles | app_writer | app_writer | Provisioning | Membership/grants |
| Extension | pgcrypto | pgcrypto | Install/upgrade | Version and function test |
| Large objects | LO catalog | LO catalog | Copy riêng | OID/content checks |
| Scheduled jobs | Scheduler | Scheduler | Recreate | Job inventory |
| Configuration | Source config | Target config | Config management | Parameter diff |

### 6.1. Object owner

Chỉ định owner cho từng nhóm: database team, application team, security, platform, operations.

### 6.2. Dependencies

Ví dụ table orders phụ thuộc customers và order_items. Chuyển schema và data theo dependency graph; tránh cutover khi bảng cha/child chưa nhất quán.

### 6.3. Scope freeze

Chốt danh sách publication tables trước initial sync. Nếu thêm bảng giữa chừng, phải có quy trình add table, schema, initial copy và validation riêng.

## 7. Chuẩn bị target cluster

Target nên được provision trước khi bắt đầu initial copy.

### 7.1. Hạ tầng

Kiểm tra CPU, RAM và storage capacity, IOPS và throughput, network route từ target tới source, disk space cho data/WAL/temporary files, backup destination, monitoring/alerting, TLS certificates và secrets, maintenance/upgrade policy.

### 7.2. PostgreSQL settings

Đặt parameter phù hợp với workload đích: max_connections, shared_buffers, work_mem, maintenance_work_mem, effective_cache_size, max_worker_processes, max_wal_size, checkpoint settings, autovacuum settings, logging và monitoring.

Không copy nguyên config source nếu hardware/storage/managed service khác.

### 7.3. Schema

Tạo schema và table definitions tương thích trước khi subscription apply. Dùng migration scripts có version và review. Kiểm tra types, columns, defaults, generated expressions và collations.

### 7.4. Indexes

Indexes trên target có thể làm initial load chậm hơn và tốn I/O khi apply. Cần quyết định:
- Tạo indexes trước để giữ read path và constraint behavior.
- Hoặc tạo một số indexes sau bulk load để tăng tốc, nếu quy trình initial copy cho phép và target chưa phục vụ traffic.
- Giữ unique indexes cần thiết để tránh duplicates.
- Không bỏ constraints mà không có validation/re-enable plan.

### 7.5. Roles và privileges

Tạo roles, memberships, grants, default privileges và ownership. Không dựa vào logical replication để mang roles từ source sang target.

### 7.6. Extensions

Cài extension binaries trước khi tạo objects phụ thuộc. Tạo extension ở target với version tương thích và chạy smoke tests.

## 8. Chuẩn bị publisher

Logical replication cần wal_level=logical trên publisher.

~~~conf
wal_level = logical
max_wal_senders = 20
max_replication_slots = 20
~~~

Giá trị là ví dụ; tính theo số subscriptions, synchronization workers và CDC consumers. wal_level cần restart PostgreSQL để áp dụng.

Kiểm tra:

~~~sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
~~~

### 8.1. Replication role

Tạo role có quyền phù hợp cho logical replication và initial table copy theo version:

~~~sql
CREATE ROLE migration_reader
WITH LOGIN REPLICATION PASSWORD 'managed-outside-source-control';
~~~

Quyền SELECT trên các bảng cần copy cũng cần được cấp theo workflow. Tránh dùng superuser chỉ để tiện triển khai nếu không cần.

### 8.2. pg_hba.conf

Ví dụ:

~~~conf
host  appdb  migration_reader  10.30.0.0/24  scram-sha-256
~~~

Cấu hình thực tế cần khớp database, source IP, TLS policy và authentication method.

### 8.3. Firewall và TLS

Chỉ mở replication port cho target/worker cần thiết. Dùng TLS certificate validation và bảo vệ credentials. Không gửi replication password qua ticket/log.

### 8.4. Capacity

Tính max_wal_senders cho subscriptions và các clients, max_replication_slots cho logical slots, max_sync_workers_per_subscription, max_parallel_apply_workers_per_subscription nếu version hỗ trợ và disk cho retained WAL trong outage budget.

## 9. Tạo publication

Trên source database:

~~~sql
CREATE PUBLICATION app_migration_pub
FOR TABLE
    app.customers,
    app.orders,
    app.order_items;
~~~

Publication xác định những tables được publish. Nó không tự tạo schema trên target.

### 9.1. Publication cho tất cả bảng

~~~sql
CREATE PUBLICATION app_all_pub
FOR ALL TABLES;
~~~

Chỉ dùng khi thực sự muốn publish mọi bảng phù hợp trong database. Scope rộng có thể làm lộ dữ liệu không cần thiết và tăng tải/retention.

### 9.2. Publication operations

~~~sql
CREATE PUBLICATION app_changes_pub
FOR TABLE app.orders
WITH (publish = 'insert, update, delete, truncate');
~~~

Chọn operations theo nhu cầu. Nếu target phải phản ánh chính xác table state, bỏ một loại operation có thể khiến hai phía diverge.

### 9.3. Row filters và column lists

Các phiên bản hỗ trợ có thể publish một tập rows hoặc columns. Điều này hữu ích cho selective distribution nhưng tạo thêm yêu cầu validation: target chỉ được kỳ vọng chứa phần dữ liệu nằm trong filter.

### 9.4. Kiểm tra publication scope

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_migration_pub'
ORDER BY schemaname, tablename;
~~~

Lưu kết quả làm baseline migration scope.

## 10. Replica identity cho UPDATE và DELETE

Subscriber cần định vị row tương ứng khi apply UPDATE/DELETE.

### 10.1. Primary key

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY DEFAULT;
~~~

Bảng có primary key thường dùng primary key làm replica identity.

### 10.2. Unique index

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY USING INDEX customers_external_id_key;
~~~

Index phải đáp ứng các điều kiện của PostgreSQL về uniqueness, nullability và trạng thái hợp lệ.

### 10.3. FULL

~~~sql
ALTER TABLE app.audit_items
REPLICA IDENTITY FULL;
~~~

FULL dùng toàn bộ old row làm identity information, có thể tăng WAL, network và chi phí tìm row trên target. Đánh giá kỹ với bảng lớn hoặc UPDATE nhiều.

### 10.4. Kiểm tra bảng thiếu identity

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relreplident
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2;
~~~

Lập danh sách các bảng có UPDATE/DELETE nhưng không có identity phù hợp trước khi tạo publication.

## 11. Tạo subscription và initial copy

Trên target database, sau khi schema đã sẵn sàng:

~~~sql
CREATE SUBSCRIPTION app_migration_sub
CONNECTION 'host=source.example.internal port=5432 dbname=appdb user=migration_reader'
PUBLICATION app_migration_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
~~~

Đây là ví dụ; quản lý password qua credential mechanism an toàn. Subscription có thể tạo logical replication slot trên publisher và khởi tạo table synchronization.

### 11.1. Initial table synchronization

Với copy_data=true, PostgreSQL copy dữ liệu hiện có cho các bảng được publish, đồng thời theo dõi changes để tiếp tục apply sau initial sync. Cơ chế synchronization đảm bảo chuyển tiếp từ snapshot sang stream theo semantics của PostgreSQL.

### 11.2. copy_data=false

Chỉ dùng khi dữ liệu đã được nạp theo một quy trình khác có consistency với logical replication start position. Nếu preload tùy tiện rồi bật subscription mà không căn chỉnh snapshot/LSN, có thể bỏ sót hoặc lặp changes.

### 11.3. Initial copy ảnh hưởng source

Initial sync đọc source tables, tạo network traffic và tải I/O. Với database lớn, chạy thử và đo throughput trước khi migration chính thức.

### 11.4. Đồng bộ nhiều bảng

PostgreSQL có thể dùng table synchronization workers. Số worker cần cân bằng giữa tốc độ copy và contention trên source/target. Tăng workers không luôn tăng throughput.

### 11.5. Kiểm tra table sync state

~~~sql
SELECT
    srsubid,
    srrelid::regclass AS table_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
~~~

Các mã trạng thái và catalog columns cần diễn giải theo version. Dùng view/catalog docs để xác định bảng nào đang copy, đã sync hoặc đang apply changes.

## 12. Theo dõi quá trình initial load

### 12.1. Subscription status

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

View thể hiện worker PID và tiến độ nhận/apply theo phiên bản. Kiểm tra worker có hoạt động và last message times có tiến triển.

### 12.2. Copy progress

~~~sql
SELECT *
FROM pg_stat_progress_copy;
~~~

View này hiển thị tiến độ các COPY operations đang chạy. Không phải mọi phiên bản/worker đều hiển thị cùng một mức chi tiết.

### 12.3. Source load

Theo dõi CPU và storage I/O, query latency, connection count, WAL generation rate, replication slot retained WAL, disk free space và long-running transactions.

### 12.4. Target load

Theo dõi COPY throughput, apply worker CPU, index maintenance, constraint checks, disk write latency, temporary files, autovacuum và replication apply lag.

### 12.5. Initial sync timeout

Nếu một table quá lớn hoặc worker lỗi, xác định table cụ thể, error log và slot state. Không drop/recreate subscription liên tục mà chưa hiểu side effects và dữ liệu đã copy tới đâu.

## 13. Logical changes sau initial copy

Sau khi initial sync hoàn tất, subscriber tiếp tục apply các logical changes phát sinh trên publisher.

### 13.1. Change stream

Publisher ghi WAL, logical decoding tạo row changes và apply worker áp dụng chúng lên subscriber.

### 13.2. Transaction boundaries

Các thay đổi được gửi theo transaction semantics. Một transaction ở source có thể thay đổi nhiều bảng; cần hiểu apply ordering và subscriber consistency khi quan sát trong lúc migration.

### 13.3. Apply rate

Nếu source tạo changes nhanh hơn subscriber apply, lag sẽ tăng. Xác định bottleneck là decode, network, target indexes, constraints, locks hay CPU.

### 13.4. Long transactions

Transaction lớn có thể tạo lượng changes lớn và làm chậm việc apply/feedback. Tránh chạy migration lớn, bulk update hoặc DDL nguy hiểm trong cutover window nếu chưa benchmark.

### 13.5. Subscription errors

Một apply error có thể khiến worker dừng hoặc subscription không tiến triển. Kiểm tra subscriber logs, pg_stat_subscription và slot state trước khi tiếp tục.

## 14. Những phần logical replication không tự chuyển

| Thành phần | Logical replication tự chuyển? | Hành động cần thiết |
| --- | --- | --- |
| Rows của bảng publish | Có | Initial copy + stream |
| DDL/schema | Không | Migration scripts |
| Index definitions | Không | Tạo trên target |
| Constraints | Không | Tạo và validate |
| Sequence state | Không | Đồng bộ trước cutover |
| Roles/passwords | Không | Provision riêng |
| Grants/default privileges | Không | Apply permissions |
| Extensions/binaries | Không | Install/upgrade |
| Large objects | Không | Copy riêng |
| Materialized view contents | Không tự cập nhật theo table changes | Refresh/rebuild |
| Server config | Không | Configuration management |
| Scheduled jobs | Không | Recreate và kiểm tra |
| External files/secrets | Không | Transfer/provision riêng |

### 14.1. DDL

Thêm/drop/rename column, table, index hoặc constraint phải được triển khai riêng. Subscriber phải có schema tương thích với changes đang apply.

### 14.2. Sequences

Sequence state không được replicate như row changes. Trước cutover, đồng bộ các sequence/identity generators để giá trị tiếp theo không đụng IDs đã có.

### 14.3. Large objects

Large objects không được native logical replication chuyển như bảng. Dùng một bước export/import riêng và xác minh OID/content theo thiết kế.

### 14.4. Roles và grants

Dùng provisioning scripts hoặc identity management. Kiểm tra object ownership, schema usage, table privileges, sequence privileges và default privileges.

### 14.5. Materialized views

Materialized view contents không tự theo logical changes của bảng nguồn. Xác định thời điểm refresh và kiểm tra kết quả trước cutover.

## 15. Schema migration trong lúc source vẫn hoạt động

DDL và logical apply phải được phối hợp.

### 15.1. Expand-and-contract

Một mẫu an toàn hơn:
1. Add column mới nullable/default phù hợp ở target.
2. Add column tương thích trên source.
3. Xác nhận subscriber schema đã sẵn sàng.
4. Deploy application version có thể đọc cả schema cũ và mới.
5. Backfill theo batch nếu cần.
6. Validate dữ liệu.
7. Chuyển application sang column mới.
8. Chỉ drop column cũ sau khi mọi consumer đã chuyển.

### 15.2. Rename column

Rename ở source không tự được logical replication gửi sang subscriber. Dùng giai đoạn tương thích: thêm column mới, dual-read/dual-write có kiểm soát nếu cần, backfill và loại bỏ column cũ sau.

### 15.3. Type change

Đánh giá cast semantics và subscriber type. Type change có thể làm apply fail hoặc biến đổi dữ liệu. Test với dữ liệu thực tế đại diện.

### 15.4. DDL freeze

Trong giai đoạn migration, hạn chế DDL ngoài kế hoạch. Mọi schema change phải được ghi vào migration log và áp dụng đúng thứ tự ở source/target.

### 15.5. Publication changes

Nếu thêm table vào publication, phải tạo schema ở target và xử lý initial data copy/replication state cho table đó. Không chỉ ALTER PUBLICATION rồi giả định subscriber đã có rows.

## 16. Partitioned tables

Partitioned tables cần kiểm tra behavior theo PostgreSQL version và publication settings.

### 16.1. Publish partition root

Một số phiên bản hỗ trợ lựa chọn publish changes theo root partitioned table hoặc từng partition thông qua tùy chọn publish_via_partition_root. Behavior ảnh hưởng table mapping trên subscriber.

### 16.2. Subscriber partitioning

Target có thể dùng cùng hoặc khác partition layout tùy khả năng tương thích. Nhưng schema/partition routing phải được kiểm tra kỹ; không giả định mọi layout khác nhau đều apply trực tiếp.

### 16.3. Partition attach/detach

Các thao tác DDL như attach/detach partition không tự được replicate như logical row changes. Triển khai DDL đồng bộ và kiểm tra table membership.

### 16.4. Validation theo partition

So sánh row counts và aggregates từng partition để xác định vùng dữ liệu bị thiếu. Với partition lớn, chia validation theo key/time range.

## 17. Xác minh schema trước chuyển đổi

Schema validation chứng minh target có cấu trúc phù hợp với ứng dụng và publication.

### 17.1. So sánh columns

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    is_identity,
    identity_generation,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

Chạy ở source và target, lưu kết quả và so sánh. Các cột information_schema phụ thuộc version; dùng truy vấn tương thích với cả hai bên.

### 17.2. So sánh constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname,
    con.contype,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
JOIN pg_class AS c ON c.oid = con.conrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3;
~~~

### 17.3. So sánh indexes

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

### 17.4. So sánh functions và views

Dùng pg_dump --schema-only hoặc catalog queries để so sánh DDL. Lưu ý normalized DDL có thể khác do version-generated clauses, owner, tablespace hoặc formatting.

### 17.5. So sánh extensions

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Không chỉ so extension name; kiểm tra version và shared library compatibility.

## 18. Xác minh row counts

Row count là lớp kiểm tra dễ hiểu, nhưng một mình nó không chứng minh dữ liệu giống nhau.

### 18.1. Exact count

~~~sql
SELECT count(*) FROM app.orders;
~~~

Chạy ở source và target sau khi target đã catch up tại cùng một logical point. Nếu source vẫn đang ghi, hai lần count riêng biệt có thể khác chỉ vì writes mới.

### 18.2. Count theo partition/key range

~~~sql
SELECT
    date_trunc('day', created_at) AS day,
    count(*) AS row_count
FROM app.orders
GROUP BY 1
ORDER BY 1;
~~~

Đối với bảng lớn, chia theo ngày, tenant hoặc key range để phát hiện vùng dữ liệu thiếu.

### 18.3. Approximate count

pg_class.reltuples và n_live_tup hữu ích cho sizing/monitoring nhưng không dùng làm bằng chứng exact equality.

### 18.4. Snapshot consistency

Khi so sánh source và target, cần xác định cùng một replication barrier hoặc một snapshot logic tương đương. Nếu source tiếp tục thay đổi giữa hai lần đọc, kết quả có thể false positive.

## 19. Xác minh keys và dữ liệu chi tiết

Count bằng nhau vẫn có thể che giấu việc một row bị thiếu và một row khác bị duplicate.

### 19.1. Primary key coverage

Với bảng nhỏ hoặc vừa, có thể so sánh key sets bằng EXCEPT:

~~~sql
SELECT order_id
FROM source_copy.orders
EXCEPT
SELECT order_id
FROM target_copy.orders;
~~~

Kết quả cần rỗng nếu hai key sets giống nhau. Mẫu này giả định hai tập dữ liệu đã được đưa vào cùng database validation hoặc có cơ chế truy cập tương đương.

### 19.2. Reverse comparison

~~~sql
SELECT order_id
FROM target_copy.orders
EXCEPT
SELECT order_id
FROM source_copy.orders;
~~~

### 19.3. Nulls và composite keys

Khi bảng dùng composite primary key, so sánh đầy đủ tất cả thành phần. Kiểm tra nullability và uniqueness theo constraint thực tế.

### 19.4. Data types và collation

Text comparisons có thể khác theo collation/locale. Timestamp, numeric precision, timezone, enum và custom types cần được so sánh theo semantics tương đương.

## 20. Xác minh aggregates và business invariants

Các aggregates phát hiện một số dạng lệch dữ liệu với chi phí thấp hơn so sánh từng row.

~~~sql
SELECT
    count(*) AS order_count,
    sum(total_amount) AS total_amount,
    min(created_at) AS first_order,
    max(created_at) AS last_order
FROM app.orders;
~~~

### 20.1. Nhóm theo trạng thái

~~~sql
SELECT status, count(*), sum(total_amount)
FROM app.orders
GROUP BY status
ORDER BY status;
~~~

### 20.2. Nhóm theo tenant

~~~sql
SELECT tenant_id, count(*) AS rows_per_tenant
FROM app.customers
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

### 20.3. Business invariants

Ví dụ: tổng số giao dịch theo ngày, tổng tiền theo currency, số lượng orders theo status, inventory không âm nếu domain yêu cầu, không có orphan references theo business rules, số lượng active tenants và các sequence IDs lớn hơn IDs đã sử dụng.

### 20.4. Aggregate không thay thế row comparison

Hai dataset có thể có cùng count và sum nhưng chứa các rows khác nhau. Kết hợp nhiều kiểm tra và chọn bảng critical để đối chiếu key-level/content-level.

## 21. Hash/checksum dữ liệu theo chunk

Với bảng lớn, có thể tính digest theo từng key range hoặc partition. Không nên gom toàn bộ bảng vào một string/array lớn vì tốn memory và có thể ảnh hưởng production.

### 21.1. Canonical representation

Một checksum chỉ hữu ích khi hai phía serialize dữ liệu theo cùng quy tắc:
- Chọn columns theo thứ tự cố định.
- Chuẩn hóa timestamp/timezone.
- Quy định cách biểu diễn NULL.
- Giữ numeric precision.
- Chuẩn hóa text/encoding.
- Sắp xếp theo unique key.
- Bao gồm key để phân biệt rows.

### 21.2. Hash theo chunk

Ví dụ minh họa với một key range nhỏ:

~~~sql
SELECT md5(
    string_agg(
        row_to_json(t)::text,
        E'\\n'
        ORDER BY t.order_id
    )
) AS chunk_digest
FROM app.orders AS t
WHERE t.order_id >= 100000
  AND t.order_id < 110000;
~~~

Chạy cùng query trên source và target ở cùng barrier. Đây là mẫu minh họa; row_to_json text formatting, data types và schema phải tương thích. Với bảng rất lớn, chia nhiều ranges để tránh aggregate quá lớn.

### 21.3. Hash không phải bằng chứng chống giả mạo

Digest giúp so sánh bytes/representation. Nó không xác thực nguồn gốc nếu actor có thể thay cả dữ liệu và digest. Bảo vệ report và metadata bằng quyền truy cập/immutable storage.

### 21.4. Chọn chunk key

Dùng primary key hoặc partition key ổn định. Tránh offset pagination trên bảng đang thay đổi vì inserts/deletes có thể làm dịch chuyển vị trí.

### 21.5. Tạo validation manifest

Ghi table name, chunk boundaries, row count, digest algorithm, digest value, barrier ID/LSN, source/target version, timestamp và validation status.

## 22. Xác minh foreign keys và constraints

Native logical apply không đồng nghĩa mọi constraint trên subscriber đã được xác minh đầy đủ như một lần kiểm tra dữ liệu độc lập.

### 22.1. Foreign keys

~~~sql
SELECT o.customer_id
FROM app.orders AS o
LEFT JOIN app.customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
LIMIT 100;
~~~

### 22.2. Unique constraints

Kiểm tra duplicates theo key/index definitions, đặc biệt nếu target schema được tạo riêng hoặc constraints được tạo sau initial copy.

### 22.3. Check constraints

Đối chiếu definitions và chạy truy vấn tìm rows vi phạm điều kiện. Constraint NOT VALID có thể chưa kiểm tra toàn bộ rows cũ cho tới khi validate.

### 22.4. Validate constraints

Nếu constraint được tạo NOT VALID để giảm ảnh hưởng trong rollout, lên kế hoạch VALIDATE CONSTRAINT trước cutover khi phù hợp.

### 22.5. Index validity

Kiểm tra index trạng thái hợp lệ và query plans cho workload quan trọng. Index có thể tồn tại nhưng invalid nếu concurrent build thất bại.

## 23. Xác minh sequences và identity

Logical replication không đồng bộ sequence state như table rows. Đây là bước dễ bị quên trước khi target nhận writes.

### 23.1. Inventory sequences

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
    cache_size
FROM pg_sequences
ORDER BY schemaname, sequencename;
~~~

### 23.2. So sánh sequence definitions

Đối chiếu start, increment, min/max, cache, cycle và ownership. Sequence name giống nhau không chứng minh cấu hình giống nhau.

### 23.3. Lấy giá trị hiện tại

Đọc last_value/is_called từ từng sequence bằng cách phù hợp với quyền và version. Không gọi nextval chỉ để kiểm tra vì nó làm thay đổi sequence state.

### 23.4. Đồng bộ trước cutover

Trong write freeze:
1. Dừng writers.
2. Chờ transaction đang chạy kết thúc.
3. Đọc giá trị sequence ở source.
4. Đọc maximum key trên target.
5. Chọn next value an toàn theo increment/cycle semantics.
6. Set target sequence phù hợp.
7. Kiểm tra sequence ownership và identity dependency.

### 23.5. Không set sequence lùi

Target có thể đã có local writes hoặc IDs cao hơn source. Không đặt sequence thấp hơn giá trị đã dùng. Nếu source và target đều đã nhận writes, phải reconcile keyspace.

## 24. Xác minh roles, grants và security

### 24.1. Roles

Tạo roles và memberships qua provisioning script. Không copy password hashes một cách tùy tiện; áp dụng chính sách identity/security của môi trường mới.

### 24.2. Grants

Kiểm tra CONNECT trên database, USAGE trên schema, SELECT/INSERT/UPDATE/DELETE trên tables, USAGE/SELECT/UPDATE trên sequences, EXECUTE trên functions và default privileges cho objects tương lai.

### 24.3. Ownership

Object owner ảnh hưởng khả năng ALTER/DROP và một số operations. Chuẩn hóa ownership theo target policy, không mặc định giữ username source nếu không còn phù hợp.

### 24.4. Row-level security

Kiểm tra RLS policies, role membership, FORCE ROW LEVEL SECURITY và application session settings. Một bảng có đủ rows nhưng application vẫn có thể nhìn thấy ít hơn vì RLS.

### 24.5. Security smoke tests

Dùng từng application role để chạy các queries chính. Xác nhận user chỉ thấy/ghi được dữ liệu thuộc phạm vi được phép.

## 25. Xác minh functions, triggers và jobs

### 25.1. Functions/procedures

So sánh definitions, language, volatility, security definer, search_path và dependencies. Một function có thể compile nhưng hành vi khác do extension/version.

### 25.2. Triggers

Logical apply có semantics riêng về trigger firing. Kiểm tra triggers trên subscriber để tránh phát sinh side effects lặp lại hoặc bỏ sót nghiệp vụ.

### 25.3. Event triggers

Event triggers không tự được logical replication chuyển. Provision riêng và kiểm tra quyền thực thi.

### 25.4. Scheduled jobs

Recreate cron/pgAgent/application scheduler jobs. Trong giai đoạn migration, tránh bật cùng một job trên cả source và target nếu job tạo side effects.

### 25.5. Outbox và event consumers

Nếu source có outbox table được publish, bảo đảm consumer không xử lý cùng event hai lần khi migration/cutover. Dùng idempotency keys và checkpoint.

## 26. Xác minh large objects và dữ liệu ngoài bảng

Large objects không được native logical replication sao chép như table rows.

### 26.1. Inventory

Kiểm tra hệ thống có dùng large objects hay không, ví dụ dữ liệu được tham chiếu qua OID trong bảng ứng dụng.

### 26.2. Export/import

Dùng công cụ phù hợp như pg_dump/pg_restore hoặc API large-object để chuyển nội dung. Chọn workflow bảo toàn OIDs nếu ứng dụng phụ thuộc OID, hoặc cập nhật references khi OID thay đổi.

### 26.3. Validation

So sánh số lượng large objects, OIDs nếu phải giữ nguyên, kích thước nội dung, digest của bytes và các references từ bảng ứng dụng.

### 26.4. External blobs

Nếu application lưu file trong object storage và chỉ lưu URL/key trong PostgreSQL, migration database không chuyển object bytes. Kiểm tra bucket replication, ACL, encryption và URL semantics.

## 27. Theo dõi replication lag

Trên publisher:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Trên subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

### 27.1. LSN progress

Logical slot giữ WAL từ restart_lsn và consumer xác nhận tiến độ qua confirmed_flush_lsn. Subscriber views cung cấp trạng thái worker/progress tùy version.

### 27.2. Lag theo bytes

~~~sql
SELECT
    slot_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS wal_distance
FROM pg_replication_slots
WHERE slot_type = 'logical'
  AND restart_lsn IS NOT NULL;
~~~

Đây là khoảng cách LSN ước lượng, không phải dung lượng độc quyền của slot.

### 27.3. Lag theo thời gian

Theo dõi last message send/receipt/apply timestamps theo view có sẵn ở version. Workload ít writes có thể làm timestamp cũ dù không có backlog đáng kể; kết hợp với LSN.

### 27.4. Slot retention

Logical slot có thể giữ WAL khi subscriber dừng. Theo dõi inactive slots, restart_lsn, retained WAL, safe_wal_size nếu có và disk free space.

### 27.5. WAL capacity planning

Ước lượng WAL generation rate nhân với outage duration budget, cộng headroom cho burst và thời gian xử lý sự cố. Đừng chỉ dựa vào wal_keep_size; slot retention có thể khiến pg_wal tăng đáng kể.

## 28. Tạo barrier trước cutover

Cutover cần một điểm xác nhận rằng mọi thay đổi hợp lệ trước khi dừng source đã tới target.

Một phương pháp thực tế là **write freeze + drain + marker transaction**.

### 28.1. Freeze writers

Dừng hoặc chặn mọi đường ghi:
- Web/API writers.
- Background workers.
- Scheduled jobs.
- ETL/import jobs.
- Admin scripts.
- External integrations.
- Service accounts khác.

Đảm bảo không còn transaction đang chạy có thể commit sau barrier.

### 28.2. Drain in-flight transactions

Theo dõi pg_stat_activity, application queues và transaction state. Chờ các writers kết thúc hoặc xử lý chúng theo runbook. Không chỉ tắt load balancer rồi giả định mọi DB sessions đã dừng.

### 28.3. Marker table

Có thể tạo một bảng marker thuộc publication:

~~~sql
CREATE TABLE migration_control.cutover_markers (
    marker_id text PRIMARY KEY,
    created_at timestamptz NOT NULL,
    source_lsn pg_lsn
);
~~~

Tạo schema/table tương ứng trên target trước khi subscription cần nó.

### 28.4. Ghi marker sau khi freeze

Khi mọi writers đã dừng và transaction đang chạy đã drain, ghi một marker trên source:

~~~sql
INSERT INTO migration_control.cutover_markers
    (marker_id, created_at, source_lsn)
VALUES
    ('cutover_2026_11_14_01', clock_timestamp(), pg_current_wal_lsn());
~~~

Marker phải nằm trong publication/subscription đang được theo dõi. Câu lệnh này là ví dụ; LSN được lấy trong transaction có thể không phải commit LSN cuối cùng. Mục đích chính là tạo một row marker có thứ tự trong logical stream.

### 28.5. Chờ marker xuất hiện trên target

~~~sql
SELECT *
FROM migration_control.cutover_markers
WHERE marker_id = 'cutover_2026_11_14_01';
~~~

Khi marker đã được apply trên target, các changes trước marker trong cùng logical stream đã được apply theo thứ tự transaction. Nếu có nhiều subscriptions hoặc publications, cần marker/confirmation cho từng stream và xác minh tất cả.

### 28.6. Barrier không thay validation

Marker chứng minh stream đã đi qua điểm chốt; nó không chứng minh schema, sequences, large objects hoặc business data đã được kiểm tra. Hoàn tất toàn bộ validation trước khi chuyển writes.

## 29. Cutover runbook

Một cutover có kiểm soát có thể thực hiện theo trình tự:

1. Xác nhận target schema/data validation đạt yêu cầu.
2. Xác nhận không còn apply errors và lag trong ngưỡng.
3. Đưa ứng dụng vào maintenance/read-only mode.
4. Dừng writers và background jobs trên source.
5. Drain in-flight transactions.
6. Ghi cutover marker trên source.
7. Chờ marker được apply trên target.
8. Xác minh counts/aggregates/critical keys lần cuối.
9. Đồng bộ sequences và metadata còn thiếu.
10. Kiểm tra roles, grants, extensions và connection settings.
11. Cô lập source khỏi writes.
12. Chuyển application endpoint sang target.
13. Chạy smoke tests với target.
14. Mở writes trên target.
15. Theo dõi error rate, latency, locks và data consistency.
16. Giữ source read-only/isolated trong rollback window theo policy.

### 29.1. Thứ tự endpoint switch

Có thể chuyển qua DNS, proxy, service discovery hoặc connection configuration. Cần tính DNS TTL, connection pool lifetime, prepared statements và các session còn kết nối source.

### 29.2. Fencing source

Sau khi target nhận writes, source phải không còn nhận application writes. Dùng firewall, revoke credentials, read-only mode hoặc cơ chế hạ tầng phù hợp. Chỉ đổi DNS không bảo đảm mọi client đã chuyển.

### 29.3. Không dual-write tùy tiện

Nếu cả source và target cùng nhận writes, hai lịch sử có thể diverge. Native logical replication đơn hướng không tự merge hai phía.

### 29.4. Smoke tests

Chạy login và authorization, read queries chính, một write transaction thử nghiệm được kiểm soát, sequence-generated insert, foreign key transaction, application health endpoints, background worker status, outbox/event processing, query latency và error rate.

## 30. Rollback plan trước và sau cutover

Rollback phải được thiết kế trước khi migration bắt đầu.

### 30.1. Trước khi target nhận writes

Nếu validation hoặc cutover thất bại trước khi target nhận writes:
- Giữ source là system of record.
- Tắt subscription hoặc giữ target cô lập theo runbook.
- Khắc phục schema/data/lag.
- Chạy lại validation.
- Chọn cutover window mới.

Đây là rollback đơn giản nhất.

### 30.2. Sau khi target nhận writes

Khi target đã nhận writes mới, source cũ trở nên stale. Không thể chỉ đổi endpoint về source mà không mất các writes phát sinh trên target.

### 30.3. Reverse replication

Có thể thiết kế một luồng reverse logical replication trước hoặc sau cutover, nhưng phải giải quyết publication/subscription direction, schema compatibility, replica identity, conflicts, sequence state, tables/rows được ghi trên mỗi phía và loop prevention.

Không mặc định subscription cũ tự trở thành replication ngược.

### 30.4. Rollback window

Đặt thời lượng rõ ràng. Trong window, giữ source read-only và lưu trữ đủ để đối chiếu. Xác định điều kiện kết thúc rollback window và thời điểm source có thể bị retire.

### 30.5. Khi không có reverse path

Nếu target đã nhận writes và không có reverse replication, rollback có thể cần export changes từ target, restore source theo một quy trình mới hoặc chấp nhận một maintenance window dài hơn. Đây phải là quyết định có owner dữ liệu và RPO rõ ràng.

## 31. Xử lý apply errors trong migration

### 31.1. Unique violation

Nguyên nhân thường là target có local data trùng key hoặc initial load không nhất quán. Xác định row và source of truth trước khi sửa.

### 31.2. Missing row khi UPDATE/DELETE

Có thể do row không được initial copy, bị local delete hoặc subscriber diverge. Kiểm tra replica identity và table sync state.

### 31.3. Schema mismatch

So sánh columns, types, defaults và generated expressions. Triển khai DDL phù hợp rồi tiếp tục theo quy trình đã thử nghiệm.

### 31.4. Permission errors

Kiểm tra publisher connection role, SELECT privileges cho initial copy và subscriber apply role/ownership. Đọc error log cụ thể theo version.

### 31.5. Worker dừng

Xem pg_stat_subscription, PostgreSQL logs và slot activity. Không drop slot hoặc recreate subscription trước khi xác định changes nào đã apply và data nào cần resync.

### 31.6. Resync một table

Nếu table diverge:
1. Đưa table vào trạng thái không nhận local writes.
2. Xác định snapshot/LSN consistency.
3. Dùng table synchronization workflow được PostgreSQL hỗ trợ hoặc copy lại table theo kế hoạch.
4. Đảm bảo không bỏ sót changes phát sinh trong lúc resync.
5. So sánh counts/keys/aggregates.
6. Xác nhận subscription apply tiếp tục.

## 32. Partitioned tables và table additions

### 32.1. Thêm bảng vào publication

Tạo schema trên target trước, sau đó cập nhật publication và khởi tạo initial data synchronization cho bảng mới theo version/workflow.

### 32.2. Partition routing

Kiểm tra publish_via_partition_root và target partition layout. Thử INSERT/UPDATE/DELETE tại boundary partitions.

### 32.3. Attach/detach

DDL partition changes không tự replicate. Triển khai ở target và source theo thứ tự tương thích, tránh source bắt đầu publish rows vào một layout mà target chưa sẵn sàng.

### 32.4. Validation partition

Đối chiếu counts, min/max keys và aggregates từng partition. Kiểm tra partitions mới nhất thường có nhiều changes nhất.

## 33. Những bảng có write volume cao

Một số bảng có thể làm subscriber không bắt kịp.

### 33.1. Xác định write hot spots

Dùng pg_stat_user_tables, workload metrics và WAL generation để tìm bảng có insert/update/delete rate cao.

### 33.2. Bulk operations

Bulk UPDATE/DELETE có thể tạo lượng WAL lớn và backlog. Tránh chạy cleanup lớn trong initial sync/cutover window nếu có thể.

### 33.3. Index cost

Subscriber phải maintain indexes. Index quá nhiều hoặc không cần thiết có thể làm apply chậm. Chỉ điều chỉnh sau benchmark và phải bảo đảm constraints/validation.

### 33.4. Parallel apply

Các phiên bản mới có thể hỗ trợ parallel apply/streaming cho một số trường hợp. Tính năng và settings phụ thuộc major version. Tăng workers chỉ sau khi xác định bottleneck và test contention.

### 33.5. Network throughput

Đo bandwidth thực tế và latency giữa source/target. Nén/transport layer có thể giúp network nhưng tăng CPU.

## 34. Initial copy cho database lớn

### 34.1. Dự báo thời gian

Ước lượng tổng bytes cần copy, throughput đọc source, network throughput hữu dụng, throughput ghi target, index/constraint overhead và thời gian retry/validation.

### 34.2. Table lớn nhất

Chia kế hoạch theo table/partition. Table rất lớn có thể chi phối toàn bộ migration duration.

### 34.3. Preload bên ngoài

Có thể dùng dump/restore hoặc bulk load trước rồi bắt đầu logical changes, nhưng cần căn chỉnh snapshot và replication start position. Không dùng copy_data=false với preload tùy tiện mà không có consistency protocol.

### 34.4. Thử nghiệm trước

Chạy thử trên dataset đại diện hoặc clone. Đo throughput, WAL retention, source impact, apply lag và thời gian cutover.

### 34.5. Temporary storage

Dự trù disk cho dump files, staging, sort/hash validation, indexes, WAL và temporary files. Giữ đủ headroom để autovacuum/checkpoint hoạt động.

## 35. Bảo mật trong migration

### 35.1. Data in transit

Dùng TLS, xác minh server certificates và giới hạn network. Không coi private subnet là thay thế encryption.

### 35.2. Data at rest

Bảo vệ target volumes, snapshots, export files và temporary directories bằng encryption phù hợp.

### 35.3. Least privilege

Tách replication role, schema migration role, application runtime role, validation/read-only role, cutover operator và backup/restore role.

### 35.4. PII và data minimization

Nếu target chỉ cần subset, giới hạn publication theo bảng/row/column khi feature hỗ trợ và policy cho phép. Xác minh không có bảng nhạy cảm bị publish ngoài ý muốn.

### 35.5. Audit

Ghi lại ai tạo publication/subscription, ai thay schema, ai thay credentials, ai phê duyệt cutover, ai bật writes trên target, validation reports và thời điểm.

### 35.6. Secret cleanup

Sau migration, rotate/revoke credentials không còn cần, xóa temporary exports theo retention policy và kiểm tra target logs không lưu secrets.

## 36. Monitoring trong toàn bộ migration

Thiết lập dashboard trước khi chạy initial copy.

### Source

- CPU, memory, storage I/O.
- Active connections.
- Query latency.
- WAL generation rate.
- Replication slot activity.
- Retained WAL estimate.
- Disk free space.
- Long-running transactions.
- Publication scope.

### Target

- CPU, memory, disk I/O.
- Initial table sync state.
- Apply worker state.
- Subscription errors.
- Lag/LSN progress.
- Index/constraint state.
- Disk free space.
- Autovacuum and bloat.
- Application smoke tests.

### Migration process

- Tables copied/remaining.
- Bytes copied.
- Rows validated.
- Chunk checksums passed/failed.
- Schema diff status.
- Sequence sync status.
- Barrier marker status.
- Cutover readiness.
- Rollback window expiry.

## 37. Các system views hữu ích

### 37.1. Publication tables

~~~sql
SELECT *
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
~~~

### 37.2. Replication slots

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

### 37.3. Subscription workers

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

### 37.4. Table synchronization state

~~~sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
~~~

### 37.5. Active sessions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Các views/catalogs có thể khác nhau theo version và quyền. Chỉ dùng các cột có trong major version đang vận hành.

## 38. Checklist xác minh trước cutover

### Schema

- [ ] Tables, columns và types tương thích.
- [ ] Indexes tồn tại và hợp lệ.
- [ ] Constraints và foreign keys đã kiểm tra.
- [ ] Functions, triggers và views đã được triển khai.
- [ ] Extensions tương thích.
- [ ] Partition definitions và mappings đúng.

### Data

- [ ] Initial table sync hoàn tất.
- [ ] Replication apply không còn lỗi.
- [ ] Row counts so sánh tại cùng barrier.
- [ ] Key sets được đối chiếu cho bảng critical.
- [ ] Aggregates/business invariants đạt.
- [ ] Chunk checksums đạt theo policy.
- [ ] Large objects/external files đã chuyển.
- [ ] Không có bảng ngoài scope bị thiếu.

### Metadata/security

- [ ] Roles và memberships có đủ.
- [ ] Grants/default privileges đúng.
- [ ] RLS policies đúng.
- [ ] Ownership và sequence privileges đúng.
- [ ] Secrets/certificates/configuration sẵn sàng.
- [ ] Jobs không chạy đồng thời trên hai phía.

### Cutover

- [ ] Write freeze đã được thử nghiệm.
- [ ] In-flight transactions đã drain.
- [ ] Marker table nằm trong publication.
- [ ] Barrier marker đã xuất hiện trên target.
- [ ] Sequences được đồng bộ.
- [ ] Source được fencing khỏi writes.
- [ ] Endpoint switch và connection pool refresh đã thử.
- [ ] Smoke tests và rollback decision owner sẵn sàng.

## 39. Runbook: migration rehearsal

Một rehearsal nên chạy toàn bộ quy trình trong staging:

1. Provision source clone và target.
2. Inventory schema/data/dependencies.
3. Tạo target schema và roles.
4. Tạo publication/subscription.
5. Chạy initial copy.
6. Tạo workload writes đại diện trên source.
7. Theo dõi lag và WAL retention.
8. Thực hiện DDL change mẫu theo expand-and-contract.
9. Validate counts, keys, aggregates và hashes.
10. Đồng bộ sequence.
11. Freeze writers.
12. Drain transactions.
13. Ghi marker và chờ target apply.
14. Thực hiện endpoint switch.
15. Chạy smoke tests.
16. Test rollback trước và sau khi target nhận writes.
17. Đo downtime/RTO và data validation duration.
18. Ghi issues, owners và thời gian sửa.

## 40. Runbook: migration production

### Trước ngày cutover

- Hoàn tất discovery và compatibility review.
- Rehearse ít nhất một lần trên dữ liệu đại diện.
- Provision target và backup target.
- Tạo publication/subscription.
- Initial sync và catch up.
- Hoàn tất schema/metadata.
- Chạy validation baseline.
- Chuẩn bị dashboard, alerts và incident contacts.
- Chốt maintenance window và decision owner.

### Trong cutover

- Thông báo freeze.
- Dừng writes/jobs/integrations.
- Drain active transactions.
- Ghi marker.
- Chờ marker apply.
- Chạy final validation.
- Đồng bộ sequences.
- Fence source.
- Switch endpoint.
- Smoke test.
- Mở writes trên target.

### Sau cutover

- Theo dõi errors, latency, locks và application behavior.
- Kiểm tra target backup/PITR.
- Tạo lại HA/replicas nếu cần.
- Giữ source read-only trong rollback window.
- Revoke/rotate credentials cũ.
- Kết thúc rollback window theo approval.
- Retire source theo retention policy.
- Cập nhật tài liệu và lessons learned.

## 41. Rollback decision matrix

| Thời điểm | Tình trạng | Hướng xử lý |
| --- | --- | --- |
| Trước initial sync | Target chưa có data | Sửa provisioning rồi chạy lại |
| Trong initial sync | Một số bảng chưa copy | Dừng/khắc phục theo table sync state; không cutover |
| Sau sync, trước freeze | Source còn writes, target apply | Giữ source là primary, xử lý lag/errors |
| Trong freeze, trước marker | Writers chưa drain | Chưa cutover; giữ freeze hoặc hủy freeze có kiểm soát |
| Marker chưa xuất hiện | Subscriber chưa catch up | Chờ/điều tra apply; không switch |
| Validation cuối thất bại | Data/schema chưa đạt | Hủy cutover, source tiếp tục làm system of record |
| Target đã nhận writes | Hai histories bắt đầu khác nhau | Cần reverse sync/reconciliation; không chỉ đổi endpoint |
| Sau rollback window | Source đã retire | Khôi phục theo DR/backup plan mới |

## 42. Troubleshooting: subscriber không bắt kịp

Nguyên nhân:
- Initial copy còn chạy.
- Source write rate cao.
- Target apply chậm do indexes/constraints.
- Network throughput thấp.
- Long transactions.
- Apply errors.
- Target disk/CPU không đủ.
- Slot/WAL retention hoặc connection issues.

Hướng xử lý:
1. Xác định table sync hay streaming apply đang chậm.
2. Đọc subscriber logs và pg_stat_subscription.
3. Kiểm tra slot LSN và retained WAL.
4. Đo CPU, disk, network và lock waits.
5. Xác định bảng/transaction tạo backlog lớn.
6. Giảm workload migration không cần thiết.
7. Tăng resources/workers sau benchmark.
8. Không drop slot hoặc recreate subscription như phản xạ.

## 43. Troubleshooting: counts khác nhau

Nguyên nhân:
- Source vẫn nhận writes trong lúc count.
- Target chưa apply hết changes.
- Một table không nằm trong publication.
- Initial copy không hoàn tất.
- Row filter/column list làm dữ liệu target có scope khác.
- Subscriber local writes.
- DDL/schema mismatch.
- Truy vấn count chạy ở các snapshot khác nhau.

Hướng xử lý:
1. Chốt barrier và freeze writers.
2. Xác nhận marker đã apply.
3. Kiểm tra publication scope.
4. Kiểm tra table sync states.
5. So sánh key ranges và partition counts.
6. Kiểm tra apply errors và local writes.
7. Re-sync bảng diverged nếu cần.
8. Chạy lại validation.

## 44. Troubleshooting: sequence collision sau cutover

Nguyên nhân:
- Sequence state không được logical replication đồng bộ.
- Target sequence thấp hơn maximum key.
- Target có local writes trước cutover.
- Sequence cache còn giá trị cũ trong sessions.

Hướng xử lý:
1. Dừng writes liên quan nếu collision đang xảy ra.
2. Xác định sequence ownership và increment.
3. Đọc current sequence state và maximum key.
4. Chọn giá trị next an toàn.
5. Đồng bộ sequence.
6. Kiểm tra concurrent sessions/cache.
7. Chạy insert test và kiểm tra uniqueness.

## 45. Troubleshooting: apply worker lỗi sau DDL

Nguyên nhân:
- Column mới chưa có trên target.
- Column type khác.
- Column rename/drop không đồng bộ.
- Replica identity/index thay đổi.
- Publication column list không còn tương thích.

Hướng xử lý:
1. Giữ source là system of record.
2. Đọc chính xác apply error.
3. Xác định DDL change và transaction gây lỗi.
4. Triển khai schema tương thích trên target.
5. Kiểm tra table state/divergence.
6. Tiếp tục apply theo supported procedure hoặc resync table.
7. Chạy lại schema/data validation.

## 46. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tạo subscription trước khi target schema sẵn sàng | Apply lỗi | Provision schema trước |
| Dùng copy_data=false mà không có consistent preload | Thiếu/lặp rows | Đồng bộ snapshot và replication start position |
| Chỉ so sánh row count | Bỏ sót row mismatch | Keys, aggregates, hashes theo chunk |
| So sánh source/target khi source vẫn ghi | False mismatch | Cùng barrier/snapshot |
| Quên DDL | Apply worker dừng | Schema migration coordination |
| Quên sequence | Primary key collision | Đồng bộ trước cutover |
| Quên large objects | Dữ liệu file/object thiếu | Copy và verify riêng |
| Không kiểm tra roles/grants | Ứng dụng không truy cập được | Provision và smoke test từng role |
| Không theo dõi logical slot | WAL giữ đầy disk | Monitor retention và consumer lag |
| Tăng workers không đo | Contention/I/O tăng | Benchmark bottleneck |
| Switch DNS nhưng không fence source | Hai cluster nhận writes | Fencing và session drain |
| Dùng marker không nằm trong publication | Không có barrier proof | Publish marker table và verify |
| Chuyển writes khi còn in-flight transactions | Mất thứ tự commit | Freeze và drain trước marker |
| Coi target đã sync là rollback-ready | Target writes không có ở source | Reverse sync/reconciliation plan |
| Chạy jobs trên cả hai clusters | Side effects duplicate | Single active scheduler |
| Không test target backups | Target mới không có DR | Backup/PITR verification |
| Không rehearsal | Downtime vượt budget | Diễn tập toàn quy trình |
| Retire source ngay sau cutover | Mất đường đối chiếu/rollback | Giữ read-only theo rollback window |

## 47. Bài tập thực hành PostgreSQL

Thực hiện trên hai clusters lab/staging. Không chạy migration/cutover trên production chỉ để thử nghiệm.

1. **Discovery:** đọc source/target PostgreSQL versions.
2. **Inventory:** liệt kê databases và sizes.
3. **Tables:** tạo inventory tables theo size và write rate.
4. **Schema:** export schema-only bằng pg_dump.
5. **Dependencies:** lập danh sách extensions, roles, sequences và large objects.
6. **Compatibility:** kiểm tra một version pair publisher/subscriber.
7. **Target:** provision target database và schema.
8. **Roles:** tạo migration role với quyền tối thiểu.
9. **Network:** cấu hình pg_hba và firewall trong lab.
10. **TLS:** thiết lập TLS cho replication connection.
11. **wal_level:** đặt logical và xác minh sau restart.
12. **Capacity:** tính max_wal_senders và max_replication_slots.
13. **Publication:** tạo publication cho hai bảng.
14. **Scope:** kiểm tra pg_publication_tables.
15. **Replica identity:** tìm bảng thiếu primary key.
16. **FULL:** thử REPLICA IDENTITY FULL và quan sát behavior.
17. **Subscription:** tạo subscription với copy_data=true.
18. **Initial copy:** theo dõi pg_subscription_rel.
19. **Copy progress:** đọc pg_stat_progress_copy trong lúc initial sync.
20. **Streaming:** insert/update/delete trên source và xác nhận target.
21. **Apply status:** theo dõi pg_stat_subscription.
22. **Slot:** kiểm tra pg_replication_slots trên publisher.
23. **Lag:** tính LSN distance và retained WAL estimate.
24. **Disk:** mô phỏng subscriber offline và theo dõi WAL growth.
25. **Recovery:** khởi động lại subscriber và xác nhận apply tiếp tục.
26. **Schema:** tạo column mới và triển khai DDL đúng thứ tự.
27. **Rename:** thiết kế expand-and-contract cho rename column.
28. **Type:** thử type change trong lab và kiểm tra apply.
29. **Partition:** publish partitioned table và kiểm tra partition behavior.
30. **Table addition:** thêm bảng mới vào publication và đồng bộ initial data.
31. **Row filter:** tạo row-filter publication nếu version hỗ trợ.
32. **Column list:** giới hạn columns và kiểm tra target representation.
33. **Count:** so sánh exact counts sau barrier.
34. **Partition counts:** so sánh counts theo ngày/partition.
35. **Keys:** so sánh key sets bằng EXCEPT.
36. **Aggregates:** so sánh sums/counts theo status.
37. **Business invariant:** viết query kiểm tra dữ liệu nghiệp vụ.
38. **Chunk digest:** tính hash cho các key ranges nhỏ.
39. **Schema diff:** so sánh information_schema.columns.
40. **Constraints:** so sánh pg_constraint definitions.
41. **Indexes:** so sánh pg_indexes.
42. **Extensions:** so sánh extname/extversion.
43. **Foreign keys:** tìm orphan rows ở target.
44. **Unique:** tìm duplicate business keys.
45. **RLS:** kiểm tra policies và query visibility theo role.
46. **Roles:** so sánh memberships và grants.
47. **Sequences:** inventory pg_sequences hai phía.
48. **Sequence sync:** đồng bộ target sequence sau freeze.
49. **Large objects:** copy một tập large objects và so digest.
50. **External blobs:** xác minh object storage keys/contents.
51. **Triggers:** kiểm tra side effects trên subscriber.
52. **Jobs:** bảo đảm scheduler chỉ active ở source trước cutover.
53. **Outbox:** kiểm tra event idempotency trong migration.
54. **Barrier table:** tạo marker table nằm trong publication.
55. **Write freeze:** dừng application writers trên lab.
56. **Drain:** kiểm tra pg_stat_activity và chờ transaction kết thúc.
57. **Marker:** ghi marker sau khi freeze.
58. **Wait:** xác nhận marker xuất hiện trên subscriber.
59. **Final validation:** chạy counts/keys/aggregates sau marker.
60. **Endpoint:** chuyển application connection string sang target.
61. **Fencing:** chặn writes trên source sau cutover.
62. **Smoke test:** chạy read/write tests trên target.
63. **Sequence insert:** kiểm tra insert-generated ID sau cutover.
64. **Rollback before writes:** hủy cutover trước khi target nhận writes.
65. **Rollback after writes:** mô tả dữ liệu cần reconcile nếu target đã ghi.
66. **Reverse replication:** xây dựng design reverse stream và loop prevention.
67. **Lag incident:** cố tình làm target apply chậm trong lab.
68. **Apply error:** tạo schema mismatch và tìm log.
69. **Resync:** xây quy trình resync một table diverged.
70. **Capacity:** benchmark initial copy trên bảng lớn.
71. **Workers:** thay đổi sync/apply workers và đo contention.
72. **Network:** đo throughput và latency giữa hai clusters.
73. **Security:** kiểm tra secrets không xuất hiện trong command history/logs.
74. **Audit:** ghi lại publication/subscription/DDL/cutover actors.
75. **Rehearsal:** chạy toàn bộ migration rehearsal.
76. **RTO:** đo downtime và thời gian từng bước.
77. **RPO:** xác định điểm dữ liệu được bảo đảm ở barrier.
78. **Backup:** tạo backup/PITR policy cho target sau cutover.
79. **DR:** diễn tập restore target sang failure domain khác.
80. **Thiết kế tổng hợp:** lập kế hoạch migration online cho database lớn, có initial copy, logical CDC, schema evolution, validation nhiều lớp, barrier marker, sequence sync, write freeze, cutover, rollback/reverse path, security, monitoring và DR.

## 48. Checklist quyết định go/no-go

### Readiness

- [ ] Source/target versions tương thích.
- [ ] Target capacity và network đã đo.
- [ ] Schema/dependencies đã inventory.
- [ ] Roles, grants, extensions và configuration đã chuẩn bị.
- [ ] Publication scope được review.
- [ ] Replica identity phù hợp.
- [ ] Initial sync hoàn tất.
- [ ] Apply workers không có lỗi.
- [ ] WAL retention còn headroom.
- [ ] Backup/PITR của source và target đã có.

### Validation

- [ ] Schema diff đạt.
- [ ] Row counts đạt tại cùng barrier.
- [ ] Key comparisons đạt cho bảng critical.
- [ ] Aggregates/business invariants đạt.
- [ ] Chunk digests đạt theo policy.
- [ ] Constraints/indexes hợp lệ.
- [ ] Sequences được đồng bộ.
- [ ] Large objects/external files được xác minh.
- [ ] Roles/RLS/application permissions được test.
- [ ] Jobs và integrations có single-owner plan.

### Cutover

- [ ] Write freeze đã diễn tập.
- [ ] In-flight transactions đã drain.
- [ ] Marker được publish và đã apply.
- [ ] Final validation đạt.
- [ ] Source fencing sẵn sàng.
- [ ] Endpoint switch và connection refresh đã thử.
- [ ] Smoke tests và decision owner có mặt.
- [ ] Rollback/reverse plan được chấp thuận.

## 49. Tổng kết

Một migration PostgreSQL online thành công cần ba giai đoạn rõ ràng:

~~~text
1. INITIAL COPY
   Source online
       |
       v
   Target schema + table data
       |
       v
2. CONTINUOUS CATCH-UP
   Logical changes
       |
       v
   Target apply + validation
       |
       v
3. CONTROLLED CUTOVER
   Freeze writers + drain
       |
       v
   Marker/barrier + final checks
       |
       v
   Sequence sync + fence source
       |
       v
   Switch endpoint + smoke tests
~~~

Những nguyên tắc quan trọng:

- **Discovery đi trước replication.** Biết rõ schema, data scope, extensions, sequences, large objects và external dependencies.
- **Initial copy phải có consistency protocol.** Không preload tùy tiện rồi bật subscription với copy_data=false.
- **Logical replication chuyển row changes, không chuyển toàn bộ database metadata.** DDL, roles, grants, sequences và nhiều objects cần bước riêng.
- **Validation cần nhiều lớp.** Row counts, key sets, aggregates, chunk hashes, constraints và application tests phát hiện những loại sai lệch khác nhau.
- **So sánh tại cùng một barrier.** Khi source còn ghi, hai lần query độc lập không chứng minh dữ liệu bằng nhau.
- **Freeze và drain trước marker.** Marker trong publication giúp chứng minh stream đã đi qua điểm chốt; nhiều streams cần xác minh riêng.
- **Sequence phải được đồng bộ trước khi target nhận writes.** Nếu không, primary key collisions có thể xuất hiện ngay sau cutover.
- **Fencing source là bắt buộc khi chuyển write ownership.** Chỉ đổi DNS không ngăn các clients cũ ghi vào source.
- **Rollback sau khi target nhận writes cần reverse sync hoặc reconciliation.** Không thể chỉ trỏ ứng dụng trở lại source cũ.
- **Rehearsal quyết định downtime thực tế.** Đo initial copy, lag, validation, freeze, cutover và rollback trên dữ liệu đại diện.

Di chuyển trực tuyến là một quy trình thay đổi ownership của dữ liệu. Khi source/target scope, schema, stream position, validation evidence và write ownership đều được xác định rõ, việc chuyển đổi có thể diễn ra trong một cửa sổ ngắn mà vẫn giữ được khả năng kiểm soát và phục hồi.
