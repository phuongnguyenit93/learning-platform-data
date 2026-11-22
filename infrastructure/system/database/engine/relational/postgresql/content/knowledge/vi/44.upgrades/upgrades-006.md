# Di chuyển bằng sao chép logic để giảm gián đoạn trong PostgreSQL

Nâng cấp PostgreSQL hoặc chuyển database sang máy chủ mới thường đòi hỏi sao chép một lượng dữ liệu lớn. Nếu chỉ dùng logical dump rồi restore, thời gian dừng ứng dụng có thể kéo dài bằng toàn bộ thời gian dump, truyền file và nạp dữ liệu. Với database lớn, cửa sổ downtime này có thể vượt quá mục tiêu vận hành.

Logical replication cho phép tạo một bản sao liên tục ở server đích trong khi server nguồn vẫn phục vụ ứng dụng. PostgreSQL gửi các thay đổi dữ liệu đã commit từ publisher sang subscriber sau khi subscriber hoàn tất initial table synchronization. Khi dữ liệu đã bắt kịp, đội vận hành tạm dừng writes, chờ một điểm đồng bộ cuối cùng, xử lý sequence state và chuyển ứng dụng sang đích. Cách làm này có thể giảm downtime xuống khoảng thời gian cutover thay vì thời gian copy toàn bộ database.

Logical replication không sao chép mọi thành phần của database. DDL, sequence state, large objects và một số loại object cần được chuẩn bị hoặc di chuyển riêng. Vì vậy, migration thành công cần phối hợp schema, publication/subscription, WAL retention, quyền truy cập, validation và rollback plan.

~~~text
                  PostgreSQL source
                   (publisher)
                        |
                WAL level = logical
                        |
                 Publication
                        |
                Logical decoding
                        |
                 Replication slot
                        |
                 WAL changes stream
                        |
                        v
                 PostgreSQL target
                  (subscriber)
                        |
              Initial table synchronization
                        |
                 Apply changes
                        |
                  Catch up / validate
                        |
             Freeze writes at source
                        |
                Final sync barrier
                        |
              Sequence state sync
                        |
                 Application cutover
                        |
                        v
                  New primary
~~~

Bài này thuộc chương **Nâng cấp** của module *Database Engine Relational PostgreSQL*, tập trung vào di chuyển bằng logical replication để giảm gián đoạn dịch vụ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích logical replication và vì sao phù hợp cho migration downtime thấp.
2. Phân biệt publisher, publication, subscriber và subscription.
3. So sánh logical replication với pg_dump/restore và physical replication.
4. Chuẩn bị source và target cho replication.
5. Cấu hình wal_level, replication slots, WAL senders và apply workers.
6. Tạo replication role với quyền tối thiểu cần thiết.
7. Chuẩn bị schema, roles, extensions và database settings ở target.
8. Tạo publication cho các bảng cần di chuyển.
9. Tạo subscription và hiểu initial table synchronization.
10. Theo dõi trạng thái đồng bộ từng bảng.
11. Hiểu vì sao DDL không tự được replicate.
12. Xử lý sequence, identity, large objects và các object ngoài phạm vi.
13. Phân biệt copy_data=true và copy_data=false.
14. Theo dõi replication slots và WAL retention.
15. Xử lý apply errors, data conflicts và schema mismatch.
16. Xác minh dữ liệu bằng counts, aggregates, checksums và business invariants.
17. Thiết kế cutover barrier để xác nhận mọi thay đổi trước đó đã được apply.
18. Đồng bộ sequence state sau khi source ngừng ghi.
19. Chuyển ứng dụng sang target mà không tạo dual-write.
20. Xây dựng rollback plan trước và sau khi target nhận writes.
21. Xử lý khác biệt major version, extensions, collation và data types.
22. Thiết kế migration theo từng nhóm bảng hoặc workload.
23. Giám sát lag, slot retention, disk, workers và apply throughput.
24. Xây dựng runbook migration, validation và cutover.

## 2. Vì sao dùng logical replication để migration?

Một logical dump thông thường tạo snapshot dữ liệu tại thời điểm dump. Những writes commit sau snapshot không tự xuất hiện trong artifact. Nếu restore mất nhiều giờ, ứng dụng phải dừng ghi trong toàn bộ khoảng thời gian đó hoặc cần một cơ chế đồng bộ delta riêng.

Logical replication giúp tách initial copy và continuous changes.

### 2.1. Initial copy

Subscriber tạo bản sao ban đầu của các bảng được publish. Quá trình này có thể kéo dài, nhưng publisher vẫn tiếp tục phục vụ workload.

### 2.2. Continuous replication

Sau snapshot của từng bảng, logical replication chuyển các thay đổi tiếp theo qua logical decoding và apply worker. Subscriber dần bắt kịp publisher.

### 2.3. Cutover ngắn

Khi subscriber đã gần đồng bộ, tạm dừng writes ở source, chờ các transaction còn lại được apply, đồng bộ các trạng thái không replicate và chuyển ứng dụng.

### 2.4. Downtime vẫn tồn tại

Logical replication không loại bỏ hoàn toàn downtime. Cần một cửa sổ ngắn để ngăn writes, xác nhận barrier, sync sequence, kiểm tra target và đổi endpoint.

### 2.5. Lợi ích chính

- Copy dữ liệu lớn trong lúc source vẫn hoạt động.
- Có thể chuyển giữa các PostgreSQL major versions theo hướng được hỗ trợ.
- Cho phép kiểm tra target trước cutover.
- Có thể di chuyển theo nhóm bảng.
- Giảm thời gian ứng dụng không ghi được so với dump/restore thuần túy.

### 2.6. Chi phí và rủi ro

- Tăng WAL generation/decoding và network traffic.
- Tạo replication slots có thể giữ WAL trên source.
- Initial copy có thể tăng I/O và load.
- DDL và sequence state cần xử lý riêng.
- Conflict hoặc schema mismatch có thể làm apply worker dừng.
- Cutover và rollback cần quy trình rõ ràng.

## 3. Các thành phần logical replication

| Thành phần | Nơi tồn tại | Vai trò |
| --- | --- | --- |
| Publisher | Source | Database phát thay đổi |
| Publication | Source | Xác định bảng và loại thay đổi được gửi |
| Logical replication slot | Source | Giữ vị trí WAL cần cho subscriber |
| Subscriber | Target | Database nhận thay đổi |
| Subscription | Target | Kết nối publication và quản lý apply |
| Table synchronization worker | Target | Copy dữ liệu ban đầu cho từng bảng |
| Apply worker | Target | Áp dụng các thay đổi liên tục |
| Replication origin | Target | Theo dõi tiến độ từ publisher |

### 3.1. Publisher

Publisher là database nguồn có wal_level=logical và publication. Nó vẫn nhận INSERT/UPDATE/DELETE từ ứng dụng trong giai đoạn migration.

### 3.2. Publication

Publication là tập hợp bảng và thao tác được phép gửi. Có thể publish một số bảng cụ thể, mọi bảng hoặc các bảng trong một publication được định nghĩa bằng danh sách.

### 3.3. Logical replication slot

Slot ghi nhận WAL position mà subscriber đã xác nhận. Publisher không được recycle WAL cần thiết cho slot, vì vậy slot giúp subscriber tiếp tục sau gián đoạn nhưng cũng có thể giữ nhiều WAL.

### 3.4. Subscriber

Subscriber là database đích. Nó có schema và bảng tương thích để nhận thay đổi. Trong migration một chiều, ứng dụng không nên ghi vào các bảng đang được replicate ở target.

### 3.5. Subscription

Subscription lưu kết nối tới publisher, publication names, trạng thái enable và các tùy chọn copy/apply.

### 3.6. Initial table synchronization

Khi subscription được tạo với copy_data=true, PostgreSQL copy dữ liệu hiện có của từng bảng bằng snapshot phù hợp, sau đó chuyển sang apply changes.

### 3.7. Apply worker

Apply worker nhận transaction changes và áp dụng chúng vào subscriber. Nếu gặp lỗi như duplicate key, thiếu bảng/cột hoặc constraint violation, worker có thể dừng và cần xử lý.

### 3.8. Replication origin

Subscriber lưu tiến độ apply từ remote publisher. Đây là một nguồn để kiểm tra đến đâu dữ liệu đã được áp dụng.

## 4. Logical replication khác physical replication

| Tiêu chí | Logical replication | Physical streaming replication |
| --- | --- | --- |
| Đơn vị truyền | Logical row changes | WAL records ở mức physical |
| Phạm vi | Bảng được publish | Toàn bộ cluster data |
| Schema/DDL | Không tự replicate | Theo WAL |
| Sequence state | Không tự replicate | Theo WAL |
| Large objects | Không replicate như table rows | Có trong physical data |
| Cross-major migration | Có thể theo hướng tương thích | Thường cần physical compatibility cùng major |
| Selective tables | Có | Không ở mức table publication |
| Subscriber writable | Có thể ghi, nhưng conflict risk | Standby thường read-only |
| Use case | Migration, selective replication, integration | HA, failover, physical standby |

### 4.1. Chọn logical replication

Phù hợp khi cần di chuyển một database hoặc tập bảng, nâng cấp major version hoặc duy trì source hoạt động trong lúc initial copy.

### 4.2. Chọn physical replication

Phù hợp cho HA/DR khi cần bản sao vật lý toàn cluster cùng major version và muốn replay toàn bộ WAL.

### 4.3. Không nhầm logical replication với logical backup

pg_dump tạo artifact để restore. Logical replication duy trì stream changes giữa hai database. Có thể dùng pg_dump để chuẩn bị schema hoặc seed data, nhưng subscription vẫn cần được đồng bộ đúng snapshot/slot.

## 5. Phạm vi và giới hạn của logical replication

Logical replication built-in tập trung vào table data. Trước khi migration, lập inventory tất cả object mà ứng dụng phụ thuộc.

### 5.1. Được replicate

Publication có thể gửi các thay đổi INSERT, UPDATE, DELETE và TRUNCATE theo publish options đã cấu hình. Mặc định thường bao gồm các thao tác này, nhưng hãy kiểm tra publication thực tế.

### 5.2. DDL không được replicate

CREATE TABLE, ALTER TABLE, CREATE INDEX, GRANT, CREATE FUNCTION, CREATE EXTENSION và các thay đổi schema khác phải được áp dụng riêng trên subscriber.

### 5.3. Sequence state không được replicate

Sequence definitions có thể được tạo trên target qua schema migration, nhưng current values/last_value không được đồng bộ liên tục bằng logical replication. Cần sync tại cutover.

### 5.4. Large objects không được replicate

Large objects được quản lý qua LO catalogs/API, không phải table row changes thông thường. Nếu ứng dụng dùng large objects, cần copy riêng và giữ OID/reference nhất quán theo kế hoạch.

### 5.5. Views và materialized views

View definitions không phải table data stream. Tạo lại definitions trên target; materialized views có thể cần refresh sau khi data đã ổn định.

### 5.6. Foreign tables và remote data

Foreign table definitions và dữ liệu remote không tự được sao chép như bảng local đã publish. Di chuyển external source và FDW configuration riêng.

### 5.7. Roles và privileges

Roles, memberships, database privileges, ownership và tablespaces cần chuẩn bị riêng. Publication/subscription không phải công cụ cluster-global migration.

### 5.8. Unlogged và temporary tables

Các bảng không thuộc phạm vi publication hoặc không đáp ứng điều kiện logical replication phải được xử lý riêng. Temporary tables không phải dữ liệu migration lâu dài.

### 5.9. Generated columns

Generated column values không được truyền như các cột thường trong logical replication; target cần có generated expression tương thích để tính giá trị của nó.

### 5.10. Extension và server configuration

Cài extension binaries/packages, cấu hình shared_preload_libraries, locale/collation, SSL, authentication, postgresql.conf và external secrets trên target theo quy trình riêng.

## 6. Lập kế hoạch migration

Một migration tốt bắt đầu bằng inventory và mục tiêu cutover.

### 6.1. Xác định nguồn và đích

Ghi host, port, database, PostgreSQL versions, network path, storage, extension versions và owner cho mỗi hệ thống.

### 6.2. Xác định downtime objective

Định nghĩa thời gian dừng ghi tối đa, RPO/RTO, thời gian validation và rollback window.

### 6.3. Xác định workload

Phân tích database size, write rate, WAL generation, busiest tables, long transactions, large objects, sequence usage và DDL frequency.

### 6.4. Chọn bảng

Publication phải chứa đầy đủ bảng cần di chuyển. Xác định bảng nào không cần replicate, bảng partitioned và bảng không có primary key.

### 6.5. Dependency inventory

Ghi lại foreign keys, views, functions, triggers, types, extensions, sequences, large objects, FDW và application dependencies.

### 6.6. Schema change freeze

Trong migration, tránh DDL tự phát. Mọi schema changes phải được áp dụng đồng bộ trên publisher và subscriber theo thứ tự tương thích.

### 6.7. Cutover owner

Chỉ định người có quyền quyết định dừng writes, xác nhận barrier và chuyển traffic. Tránh nhiều nhóm cùng thay endpoint.

### 6.8. Rollback boundary

Xác định thời điểm target bắt đầu nhận writes. Sau mốc này, quay lại source cần đồng bộ ngược hoặc reconciliation; đổi connection string đơn thuần sẽ làm mất writes mới trên target.

## 7. Kiểm tra version compatibility

Logical replication hỗ trợ một số kịch bản cross-major, nhưng cần tuân thủ hướng tương thích.

### 7.1. Publisher cũ, subscriber mới

Một mô hình nâng cấp thông dụng là publisher chạy major version cũ và subscriber chạy major version mới hơn hoặc tương thích theo tài liệu PostgreSQL.

### 7.2. Subscriber không nên cũ hơn publisher

Không giả định logical replication hỗ trợ mọi hướng version. Kiểm tra compatibility matrix của hai major versions trước khi thiết kế.

### 7.3. Data types

Kiểu dữ liệu và cách biểu diễn phải tương thích. Các type/extension mới trên source có thể không tồn tại hoặc có semantics khác trên target cũ.

### 7.4. Collation và locale

Collation provider/version khác nhau có thể ảnh hưởng sort order và index validity. Chuẩn bị database encoding/locale và kiểm tra indexes trên target.

### 7.5. Extension

Cài extension package tương thích với target major version. Kiểm tra upgrade scripts và extension schema objects trước khi tạo subscription.

### 7.6. Feature differences

Generated columns, partitioning, identity behavior, publication options và statistics views có thể khác theo version. Thử migration trên môi trường staging có cùng version pair.

### 7.7. Không dùng logical replication để downgrade tùy tiện

Nếu target cũ hơn publisher hoặc không hiểu schema/data semantics, chọn phương án export/transform khác hoặc nâng cấp target version.

## 8. Chuẩn bị publisher

Publisher cần phát logical WAL và có đủ resources cho slot, sender và decoding.

### 8.1. wal_level

~~~conf
wal_level = logical
~~~

Đây là startup parameter, cần restart PostgreSQL khi thay đổi.

### 8.2. max_replication_slots

~~~conf
max_replication_slots = 10
~~~

Cần đủ slots cho subscriptions, table synchronization và các consumers khác. Ước lượng dựa trên topology và migration concurrency.

### 8.3. max_wal_senders

~~~conf
max_wal_senders = 10
~~~

Cần đủ WAL sender processes cho logical replication connections và các physical/backup consumers khác.

### 8.4. max_worker_processes

Logical decoding và các process nền dùng worker resources. Kiểm tra giới hạn worker của server.

### 8.5. Restart

Sau khi thay đổi startup parameters, restart source theo maintenance plan. Kiểm tra setting thực bằng SHOW và pg_settings.

### 8.6. Kiểm tra cấu hình

~~~sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_replication_slots',
    'max_wal_senders',
    'max_worker_processes'
)
ORDER BY name;
~~~

### 8.7. WAL capacity

Logical slot có thể giữ WAL trong lúc subscriber chậm hoặc offline. Đảm bảo pg_wal filesystem có headroom và alert theo retained WAL.

## 9. Chuẩn bị subscriber

Subscriber cần đủ workers, connections và storage để nhận/apply changes.

### 9.1. Worker settings

Các tham số thường cần xem:
- max_replication_slots.
- max_logical_replication_workers.
- max_sync_workers_per_subscription.
- max_worker_processes.

### 9.2. Apply workers

Một apply worker xử lý subscription; table synchronization có thể dùng các workers riêng. Số workers giới hạn mức copy song song.

### 9.3. Connection capacity

Subscriber cần connections cho apply/sync workers và ứng dụng/monitoring. Chừa headroom phù hợp.

### 9.4. Disk capacity

Initial copy có thể làm target tăng dung lượng nhanh. Cần đủ chỗ cho table data, indexes, WAL, temporary operations và concurrent workload.

### 9.5. Subscriber không nhận application writes sớm

Trong migration một chiều, giữ target ở trạng thái không cho ứng dụng ghi vào replicated tables trước cutover. Writes riêng có thể gây conflict hoặc làm target khác source.

### 9.6. Kiểm tra settings

~~~sql
SHOW max_logical_replication_workers;
SHOW max_sync_workers_per_subscription;
SHOW max_worker_processes;
SHOW max_replication_slots;
~~~

## 10. Tạo replication role và quyền truy cập

Publisher cần role có thể kết nối replication và đọc bảng để initial synchronization.

### 10.1. Tạo role

~~~sql
CREATE ROLE migration_repl
    WITH LOGIN REPLICATION PASSWORD 'replace-with-secret';
~~~

Dùng secret thật qua secret manager hoặc passfile; placeholder không phải mật khẩu production.

### 10.2. Quyền SELECT

Cấp SELECT cho các bảng được copy ban đầu:

~~~sql
GRANT SELECT ON TABLE app.customers, app.orders, app.order_items
TO migration_repl;
~~~

Có thể dùng grant theo schema/table phù hợp, nhưng tránh mở rộng quyền ngoài scope migration.

### 10.3. pg_hba.conf

Ví dụ cho kết nối replication:

~~~conf
hostssl replication migration_repl 10.40.0.0/24 scram-sha-256
~~~

Initial table copy cũng cần kết nối database thông thường và quyền SELECT tương ứng; cấu hình pg_hba phải cho phép connection tới database đó.

### 10.4. TLS

Dùng SSL mode phù hợp, xác minh hostname và CA. Không tắt certificate validation để bỏ qua lỗi cấu hình.

### 10.5. Subscription owner

Role tạo subscription trên target cần quyền phù hợp trên target database/tables và quyền quản lý subscription theo major version. Apply worker cần có khả năng ghi vào subscriber tables.

### 10.6. Secrets

Connection string được lưu trong catalog subscription. Giới hạn quyền đọc catalog và dùng passfile/secret mechanism khi phù hợp để giảm việc lưu password trực tiếp.

### 10.7. Kiểm tra kết nối

Từ target, thử kết nối tới publisher bằng cùng network path, TLS và authentication mà subscription sẽ dùng.

## 11. Chuẩn bị schema trên target

Logical replication yêu cầu các bảng đích tương thích với bảng nguồn.

### 11.1. Dump schema-only

Một cách tạo schema ban đầu:

~~~bash
pg_dump --schema-only --no-owner --no-privileges \
  -d sourcedb -f sourcedb_schema.sql
~~~

### 11.2. Restore schema

~~~bash
psql -X -v ON_ERROR_STOP=1 -d targetdb \
  -f sourcedb_schema.sql
~~~

Chuẩn bị roles, extensions và tablespaces cần thiết trước khi restore schema.

### 11.3. DDL compatibility

Đảm bảo tables, column names/types, constraints và required objects tương thích. Logical replication không tự tạo hoặc ALTER schema khi source thay đổi.

### 11.4. Indexes và constraints

Primary keys/unique constraints có thể cần cho replica identity và integrity. Indexes secondary có thể được chuẩn bị theo chiến lược migration; trì hoãn tạo index có thể tăng apply performance nhưng phải bảo đảm query/cutover readiness.

### 11.5. Triggers

Kiểm tra triggers trên subscriber. Logical apply không tương đương application INSERT thông thường ở mọi trigger mode; trigger được cấu hình ENABLE REPLICA/ALWAYS có thể có behavior riêng. Tránh side effects hoặc double-processing.

### 11.6. Foreign keys

Các foreign keys phải tương thích với dữ liệu và thứ tự apply. Initial copy của nhiều bảng có thể tạo thời điểm một bảng đã copy trong khi bảng liên quan chưa hoàn tất; test schema/constraints trên đúng version.

### 11.7. Default values

Subscriber có thể có defaults khác nếu cột không được gửi hoặc có extra columns. Dùng schema tương thích và kiểm tra mọi row sau apply.

### 11.8. DDL freeze

Sau khi tạo subscription, không tự ý đổi column/table trên source hoặc target. Nếu cần thay đổi, áp dụng theo migration plan cho cả hai phía và bảo đảm apply worker không nhận row shape không tương thích.

## 12. Replica identity và bảng không có primary key

UPDATE/DELETE cần cách xác định row tương ứng trên subscriber.

### 12.1. Primary key

Mặc định PostgreSQL dùng primary key làm replica identity khi có.

### 12.2. REPLICA IDENTITY FULL

Nếu không có primary key hoặc unique index phù hợp, có thể dùng:

~~~sql
ALTER TABLE app.audit_events REPLICA IDENTITY FULL;
~~~

Khi đó PostgreSQL dùng toàn bộ row để xác định tuple cũ. Cách này có thể tăng WAL/network/apply cost và phụ thuộc khả năng so sánh dữ liệu.

### 12.3. Không có replica identity

Nếu publication gửi UPDATE/DELETE cho bảng không có replica identity phù hợp, thao tác có thể thất bại hoặc bị từ chối theo cấu hình/version.

### 12.4. Unique index

Có thể chọn một unique index phù hợp bằng REPLICA IDENTITY USING INDEX nếu đáp ứng yêu cầu không nullable và các điều kiện của PostgreSQL.

### 12.5. Insert-only tables

Bảng chỉ publish INSERT không cần xác định row cũ cho UPDATE/DELETE, nhưng phải xác nhận publication thực sự không gửi các thao tác đó.

### 12.6. Kiểm tra inventory

Liệt kê bảng được publish và kiểm tra primary key, replica identity, partitioning và thao tác ứng dụng thực hiện.

## 13. Tạo publication

Publication xác định dữ liệu được gửi từ publisher.

### 13.1. Publish bảng cụ thể

~~~sql
CREATE PUBLICATION app_migration_pub
FOR TABLE app.customers, app.orders, app.order_items;
~~~

### 13.2. Publish mọi bảng

~~~sql
CREATE PUBLICATION app_migration_pub
FOR ALL TABLES;
~~~

FOR ALL TABLES có yêu cầu quyền cao hơn và có thể bao gồm những bảng không cần di chuyển. Dùng danh sách explicit nếu muốn kiểm soát scope.

### 13.3. Publish options

Có thể chọn các thao tác insert/update/delete/truncate:

~~~sql
CREATE PUBLICATION app_insert_update_pub
FOR TABLE app.events
WITH (publish = 'insert, update');
~~~

Chỉ bỏ DELETE/TRUNCATE nếu ứng dụng và migration plan hiểu rõ dữ liệu target sẽ khác source ra sao.

### 13.4. Row filters và column lists

Các phiên bản hỗ trợ có thể dùng row filters và column lists để giới hạn dữ liệu. Chúng làm thay đổi semantics của bản sao; cần xác minh target là một subset được chủ đích, không phải replica đầy đủ.

### 13.5. Partitioned tables

Kiểm tra cách publication xử lý partitioned tables và publish_via_partition_root. Source/target partition layout có thể khác nhưng cần tương thích với version và publication semantics.

### 13.6. Kiểm tra publication

~~~sql
SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete, pubtruncate
FROM pg_publication;
~~~

### 13.7. Kiểm tra bảng trong publication

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_migration_pub'
ORDER BY schemaname, tablename;
~~~

## 14. Tạo subscription

Subscription được tạo trên subscriber và trỏ tới publisher publication.

### 14.1. Lệnh cơ bản

~~~sql
CREATE SUBSCRIPTION app_migration_sub
CONNECTION 'host=source-db.internal port=5432 dbname=sourcedb user=migration_repl sslmode=verify-full'
PUBLICATION app_migration_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
~~~

Tên publication phải tồn tại trên publisher. Connection string phải truy cập đúng database chứa publication.

### 14.2. copy_data=true

Mặc định, PostgreSQL copy dữ liệu hiện có của các bảng được publish trước khi apply stream changes. Đây là cách đơn giản cho initial migration nếu target tables được chuẩn bị rỗng.

### 14.3. create_slot=true

Tạo logical replication slot trên publisher để giữ vị trí WAL cho subscription. Slot name thường gắn với subscription name, trừ khi được cấu hình khác.

### 14.4. enabled=true

Subscription được bật để workers kết nối và bắt đầu đồng bộ. Có thể tạo subscription disabled rồi bật sau trong một số workflow.

### 14.5. Tạo subscription ngoài transaction block

CREATE SUBSCRIPTION tạo replication slot/connection và không nên được chạy trong transaction block thông thường. Thực hiện bằng một lệnh psql độc lập.

### 14.6. Connection string

Không hardcode password trong repository hoặc log. Nếu dùng passfile, bảo đảm PostgreSQL OS user có thể đọc file và permissions phù hợp.

### 14.7. Kiểm tra subscription

~~~sql
SELECT subname, subenabled, subslotname, subpublications
FROM pg_subscription;
~~~

### 14.8. Xác nhận worker

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Các cột trong view thay đổi theo major version; kiểm tra schema view trước khi viết dashboard phụ thuộc.

## 15. Initial table synchronization

Khi copy_data=true, PostgreSQL đồng bộ từng bảng trước khi chuyển bảng đó sang streaming apply bình thường.

### 15.1. Snapshot

Table synchronization worker lấy snapshot nhất quán cho bảng và copy rows sang subscriber.

### 15.2. Changes trong lúc copy

Các thay đổi phát sinh sau snapshot được giữ trong logical stream/slot và apply sau khi copy hoàn tất để subscriber không bỏ sót commits.

### 15.3. Nhiều bảng

Các bảng có thể được đồng bộ song song theo max_sync_workers_per_subscription và worker capacity. Không phải mọi bảng đều hoàn tất cùng lúc.

### 15.4. Table states

pg_subscription_rel theo dõi trạng thái đồng bộ từng relation. Những trạng thái thường gặp biểu diễn khởi tạo, copy data, hoàn tất copy, synchronized và ready.

~~~sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY relation::text;
~~~

### 15.5. Worker capacity

Nếu sync workers quá ít, initial copy có thể kéo dài. Nếu quá nhiều, source/target có thể bị I/O contention và tăng load.

### 15.6. Target data

Khi copy_data=true, target tables nên được chuẩn bị theo đúng trạng thái mong muốn, thường là rỗng. Nếu đã có dữ liệu, initial copy có thể tạo duplicate key hoặc constraint errors.

### 15.7. Initial copy và application writes

Không cho ứng dụng ghi vào target trong lúc initial sync. Logical replication là one-way stream; nó không merge dữ liệu tự ghi với dữ liệu được apply.

### 15.8. Bảng lớn

Một bảng rất lớn có thể chiếm phần lớn thời gian initial copy. Theo dõi từng relation và đánh giá parallelism, network throughput, disk I/O và indexes.

## 16. copy_data=false và pre-seeding

copy_data=false bỏ qua initial table copy và chỉ bắt đầu apply các thay đổi sau điểm bắt đầu subscription.

### 16.1. Khi nào dùng?

Có thể dùng khi subscriber đã được nạp một bản sao dữ liệu nhất quán từ trước bằng một quy trình có phối hợp snapshot/slot.

### 16.2. Không dùng sau một pg_dump tùy tiện

Nếu chỉ chạy pg_dump, restore target rồi tạo subscription copy_data=false, có thể có khoảng trống hoặc trùng lặp giữa snapshot dump và logical slot. Hai bước không tự động chia sẻ cùng một consistency point.

### 16.3. Consistent snapshot

Pre-seeding cần phối hợp thời điểm snapshot của data copy với điểm consistent của logical replication slot. Dùng một quy trình/tool đã được kiểm chứng cho mục đích này.

### 16.4. Lợi ích

Với database rất lớn, pre-seeding có thể giảm thời gian initial copy qua replication workers và cho phép dùng công cụ truyền dữ liệu phù hợp hơn.

### 16.5. Rủi ro

Nếu snapshot/slot không khớp, subscriber có thể thiếu transaction hoặc apply changes lên baseline sai. Đây là lỗi consistency nghiêm trọng.

### 16.6. Validation

Trước khi bật subscription với copy_data=false, phải chứng minh snapshot và stream không có gap, table schemas khớp và mọi bảng trong publication có baseline chính xác.

## 17. Theo dõi replication progress

Migration chỉ có thể cutover khi subscriber đã nhận và apply mọi thay đổi cần thiết.

### 17.1. Subscriber: pg_stat_subscription

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription;
~~~

Các cột có thể khác theo PostgreSQL version. Kiểm tra \d+ pg_stat_subscription trước khi dùng query trong automation.

### 17.2. Subscriber: table states

~~~sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel;
~~~

Đảm bảo tất cả bảng cần migration đã đạt trạng thái ready theo semantics của version.

### 17.3. Subscriber: replication origin

~~~sql
SELECT
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status;
~~~

remote_lsn thể hiện tiến độ remote đã apply theo replication origin. Dùng cùng với barrier/cutover protocol để xác nhận.

### 17.4. Publisher: replication slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

### 17.5. Publisher: WAL sender

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

### 17.6. Không chỉ nhìn connection state

State streaming cho biết connection đang hoạt động, không đảm bảo initial copy đã xong hoặc subscriber đã bắt kịp.

### 17.7. Table sync và apply lag

Tách thời gian initial copy khỏi apply lag. Một bảng chưa ready có thể chưa nhận đầy đủ stream changes dù subscription worker đang kết nối.

## 18. WAL retention và replication slots

Logical replication slot giữ WAL cần thiết cho subscriber.

### 18.1. Vì sao slot giữ WAL?

Nếu subscriber mất kết nối, publisher phải giữ WAL từ vị trí slot cần để subscriber có thể tiếp tục. WAL chỉ được giải phóng khi không còn cần cho slot/consumer khác.

### 18.2. Disk growth

Nếu subscriber chậm hoặc dừng lâu, pg_wal có thể tăng nhanh và làm đầy filesystem source.

### 18.3. restart_lsn

restart_lsn là điểm WAL sớm nhất slot còn cần. Khoảng cách từ current WAL LSN tới restart_lsn giúp ước lượng retained WAL, nhưng cần tính cả các slots khác.

### 18.4. confirmed_flush_lsn

Với logical slot, confirmed_flush_lsn phản ánh vị trí subscriber đã xác nhận theo protocol. Đây là tín hiệu tiến độ quan trọng.

### 18.5. max_slot_wal_keep_size

Có thể dùng giới hạn WAL giữ bởi slots theo cấu hình phù hợp. Nếu vượt giới hạn, slot có thể bị invalidated và subscriber phải resync. Không đặt giới hạn quá thấp so với migration duration và WAL rate.

### 18.6. Slot inactive

Slot inactive trong thời gian dài vẫn có thể giữ WAL. Alert theo active state, retained bytes và thời gian inactive.

### 18.7. Không xóa slot đang dùng

Không drop replication slot chỉ để giải phóng disk khi migration còn cần nó. Làm vậy có thể khiến subscriber không thể tiếp tục và phải copy lại.

### 18.8. Capacity planning

Ước tính retained WAL theo peak WAL generation rate × thời gian subscriber có thể offline/chậm, cộng headroom. Theo dõi free space trên source trong toàn bộ migration.

## 19. DDL và schema changes trong migration

Logical replication không tự replicate DDL. Schema trên hai phía phải được duy trì tương thích thủ công.

### 19.1. Freeze DDL

Cách đơn giản nhất là đóng băng schema changes trong migration window từ lúc tạo schema target tới khi cutover hoàn tất.

### 19.2. Thay đổi có kế hoạch

Nếu cần deploy DDL, áp dụng theo thứ tự tương thích:
1. Tạo column/object cần thiết trên subscriber.
2. Xác nhận subscriber schema sẵn sàng.
3. Áp dụng thay đổi trên publisher.
4. Xác minh apply worker vẫn hoạt động.
5. Cập nhật ứng dụng theo expand/contract strategy.

### 19.3. Add column

Nếu source bắt đầu gửi một column mà subscriber chưa có, apply có thể lỗi. Chuẩn bị column trên subscriber trước khi source ghi dữ liệu vào column đó.

### 19.4. Drop/rename column

Không rename/drop cột trên publisher trong khi subscriber chưa được cập nhật tương ứng. Logical replication map dữ liệu theo schema/table contract; thay đổi không đồng bộ có thể làm apply dừng.

### 19.5. Type change

Kiểu dữ liệu và cast semantics cần tương thích. Thay đổi type lớn có thể cần migration data riêng hoặc tạo table mới.

### 19.6. Index changes

Index DDL không được replicate. Tạo/drop indexes riêng trên target và cân nhắc ảnh hưởng tới initial copy/apply throughput.

### 19.7. Constraints

Unique/check/foreign key constraints cần phù hợp với dữ liệu đang apply. Constraint target chặt hơn source có thể khiến apply worker lỗi.

### 19.8. Functions/triggers

Tạo functions và triggers trên target trước khi ứng dụng chuyển. Kiểm tra trigger behavior để tránh gửi dữ liệu rồi chạy side effects hai lần.

## 20. Sequence và identity columns

Sequence state không được đồng bộ liên tục bởi built-in logical replication.

### 20.1. Sequence definition

Schema-only dump có thể tạo sequence và ownership/default, nhưng không đảm bảo current sequence value của source được phản ánh trên target.

### 20.2. Values in rows

Giá trị ID đã lưu trong table rows được replicate như column data. Tuy nhiên, sequence cấp ID tiếp theo trên target có thể vẫn ở giá trị ban đầu.

### 20.3. Rủi ro duplicate key

Nếu target bắt đầu ghi trước khi sequence được đồng bộ, nextval có thể tạo giá trị đã tồn tại và gây unique violation.

### 20.4. Sync tại cutover

Sau khi source ngừng ghi và mọi transaction đã apply, đọc last_value/is_called của từng sequence trên source và đặt target tương ứng.

### 20.5. Tìm sequence sở hữu bởi column

~~~sql
SELECT pg_get_serial_sequence('app.orders', 'id');
~~~

### 20.6. Đọc trạng thái sequence

~~~sql
SELECT last_value, is_called
FROM app.orders_id_seq;
~~~

Chạy sau khi đã dừng các writers có thể gọi sequence. Nếu có sequence cache, drain/đóng các application sessions để không còn giá trị đã cấp nhưng chưa được xử lý.

### 20.7. Đặt trạng thái trên target

~~~sql
SELECT setval('app.orders_id_seq', 900500, true);
~~~

Ví dụ dùng giá trị minh họa. Thay bằng last_value/is_called thực tế đã ghi nhận từ source. Nếu is_called=false, truyền false để lần nextval tiếp theo trả về start value hiện tại của sequence.

### 20.8. Identity

Dùng pg_get_serial_sequence để tìm sequence gắn với serial/identity column. Kiểm tra GENERATED ALWAYS/BY DEFAULT và bảo đảm generation mode giống migration design.

### 20.9. Sequence không gắn column

Các sequence độc lập, sequence được gọi trong function hoặc dùng cho nhiều bảng phải được inventory riêng. Không chỉ sync sequence tìm được từ primary key columns.

### 20.10. Writes ngoài bảng

Nếu ứng dụng gọi nextval nhưng transaction không insert row, sequence state vẫn có thể tiến. Vì vậy, không chỉ dùng MAX(id) để suy ra trạng thái sequence.

## 21. Large objects và dữ liệu ngoài bảng

Large objects không thuộc logical table replication thông thường.

### 21.1. OID references

Một table có thể chứa OID trỏ tới large object. Logical replication sẽ truyền giá trị OID trong row nếu column được publish, nhưng nội dung LO không tự được copy.

### 21.2. Copy large objects riêng

Dùng công cụ/ứng dụng phù hợp để đọc nội dung large objects từ source và tạo chúng trên target. Cần giữ OID mapping hoặc cập nhật reference columns theo kế hoạch.

### 21.3. Tránh OID collision

Nếu tạo large objects mới trên target, OID có thể khác source. Không giả định copy nội dung tự giữ cùng OID. Thiết kế mapping và cập nhật references an toàn.

### 21.4. bytea

Nếu binary data được lưu trong bytea column của bảng được publish, giá trị column được replicate như row data. Đây là khác biệt quan trọng so với large object OID reference.

### 21.5. External files

File trong filesystem, object storage, remote service hoặc application host cần di chuyển riêng. Logical replication không theo dõi chúng.

### 21.6. FDW và secrets

Foreign servers, user mappings, credentials và remote data source cần chuẩn bị lại trên target. Không đưa secret vào SQL dump hoặc logs không được bảo vệ.

## 22. Publication filters và migration scope

Publication có thể giới hạn bảng, rows hoặc columns theo khả năng version.

### 22.1. Table list

Explicit table list giúp migration chỉ bao gồm các bảng cần thiết và dễ review scope.

### 22.2. FOR ALL TABLES

Dùng khi thật sự cần mọi bảng phù hợp và có quyền yêu cầu. Kiểm tra các bảng được thêm mới trong thời gian migration; publication FOR ALL TABLES có thể bao phủ các bảng mới theo semantics của nó, nhưng schema trên subscriber vẫn cần được tạo thủ công.

### 22.3. Row filters

Row filters có thể chỉ replicate rows thỏa predicate. Nếu dùng, target là một subset có chủ đích; không coi row counts bằng source là validation criteria.

### 22.4. Column lists

Column lists có thể giới hạn columns được gửi. Kiểm tra subscriber có đủ columns/defaults/generated columns để nhận data và ứng dụng target hoạt động.

### 22.5. Multiple publications

Một subscription có thể subscribe nhiều publications. Tránh publish cùng một bảng qua nhiều publication có thể tạo duplicate/confusing semantics; kiểm tra effective publication scope.

### 22.6. Schema evolution

Bảng mới được thêm vào publication cần được tạo trên subscriber và xử lý subscription/table synchronization phù hợp. Không giả định DDL auto-follow.

## 23. Data conflicts và apply errors

Logical replication apply worker phải áp dụng thay đổi theo constraints và schema của subscriber.

### 23.1. Duplicate key

Target đã có row cùng primary key nhưng source gửi INSERT. Kiểm tra target có dữ liệu pre-seeded hoặc application writes hay không.

### 23.2. Missing row

Source gửi UPDATE/DELETE nhưng subscriber không tìm thấy row phù hợp. Kiểm tra initial copy consistency, manual changes và replica identity.

### 23.3. Schema mismatch

Thiếu column/table, type không tương thích hoặc constraint khác có thể làm apply thất bại.

### 23.4. Permission error

Subscription owner/apply worker không có quyền cần thiết trên target table hoặc schema.

### 23.5. Trigger side effects

Trigger trên subscriber có thể thay đổi dữ liệu hoặc gọi external side effects. Kiểm tra trigger firing modes và logic ứng dụng.

### 23.6. TRUNCATE

Nếu publication gửi TRUNCATE, đảm bảo target có cùng kỳ vọng về bảng liên quan và foreign key dependencies. Kiểm thử truncate behavior trên staging.

### 23.7. Apply worker dừng

Kiểm tra PostgreSQL logs, subscription worker state và error details. Sau khi sửa nguyên nhân, xác minh worker tự tiếp tục hoặc enable lại subscription theo đúng trạng thái.

### 23.8. Không bỏ qua lỗi tùy tiện

Không skip transaction chỉ để dashboard báo healthy. Xác định row/object bị thiếu, sửa dữ liệu hoặc rebuild table/subscription theo quy trình có kiểm soát.

## 24. Validation trong lúc migration

Validation nên được tiến hành nhiều lần, không chỉ ở cutover.

### 24.1. Schema validation

So sánh table/column definitions, types, constraints, indexes, triggers, defaults, ownership và grants.

### 24.2. Row counts

Đếm rows theo bảng ở source và target. Khi replication còn chạy, hai số có thể khác do writes đang diễn ra; chỉ so sánh chính xác sau barrier.

### 24.3. Aggregate checks

So sánh totals, min/max IDs, counts theo ngày/partition, sums và business invariants. Chọn các phép kiểm tra phản ánh semantics dữ liệu.

### 24.4. Hash/chunk validation

Với bảng lớn, có thể chia theo primary key ranges hoặc partitions và tính checksums trên cùng snapshot/cutover point. Tránh quét toàn bộ source/target quá thường xuyên trong giờ cao điểm.

### 24.5. Referential integrity

Kiểm tra foreign key relationships, orphan rows và business constraints sau khi initial sync hoàn tất.

### 24.6. Sequence validation

So sánh last_value/is_called và xác nhận target nextval sẽ không tạo duplicate IDs sau cutover.

### 24.7. Large objects

Kiểm tra OID references và đọc thử nội dung LO sau khi copy riêng.

### 24.8. Application validation

Chạy read-only smoke tests, query plans quan trọng, permissions và connection behavior trên target trước khi mở traffic ghi.

### 24.9. Extension behavior

Xác nhận extensions được load, functions/operators/types tồn tại và query kết quả tương thích.

## 25. Cutover barrier và đồng bộ cuối

Cutover cần một bằng chứng rằng mọi writes đã commit trước thời điểm đóng source đều được apply trên target.

### 25.1. Freeze application writes

Đưa ứng dụng vào maintenance/read-only mode hoặc chặn write endpoints. Dừng background jobs, workers, schedulers và integration consumers có thể ghi vào source.

### 25.2. Drain transactions

Chờ các transaction đang mở hoàn tất hoặc rollback. Kiểm tra prepared transactions và sessions còn có thể ghi. Không chỉ dừng load balancer trong khi connection pools vẫn giữ sessions.

### 25.3. Ghi marker transaction

Một cách rõ ràng là dùng bảng migration marker đã nằm trong publication. Sau khi writers được dừng và transaction đã drain, insert một marker duy nhất trên source:

~~~sql
INSERT INTO admin.migration_barrier (migration_id, created_at)
VALUES ('cutover-2026-01', clock_timestamp());
~~~

Giá trị migration_id ở trên chỉ là ví dụ. Marker phải được commit và bảng phải được publish/subscribed, table sync đã ready.

### 25.4. Chờ marker trên target

Poll target cho tới khi marker row xuất hiện. Vì marker được commit sau khi source writers đã drain và được gửi trong cùng logical stream, sự hiện diện của marker chứng minh các transaction publish trước nó đã được apply theo thứ tự stream.

### 25.5. Dùng LSN như tín hiệu bổ sung

Có thể đối chiếu pg_replication_origin_status.remote_lsn và pg_stat_subscription latest_end_lsn với publisher LSN. Tuy nhiên, barrier row dễ diễn giải hơn khi có WAL activity khác và cần một điều kiện ứng dụng rõ ràng.

### 25.6. Không dùng replication lag time đơn lẻ

Một metric lag bằng zero hoặc connection state streaming không chứng minh mọi transaction đã apply. Dùng marker và table readiness để xác nhận cutover point.

### 25.7. Disable subscription

Sau khi marker xuất hiện và mọi validation cuối đạt, có thể disable subscription để ngừng apply trong lúc chuyển traffic:

~~~sql
ALTER SUBSCRIPTION app_migration_sub DISABLE;
~~~

Giữ subscription/slot theo rollback plan. Đừng drop slot trước khi chắc chắn không còn cần tiếp tục replication hoặc rollback.

## 26. Đồng bộ sequence tại cutover

Sau khi source ngừng ghi, đồng bộ toàn bộ sequences có liên quan.

### 26.1. Inventory sequences

Liệt kê sequence trong các schema được migration. Ghi sequence name, owner, increment, start/min/max, cache, cycle và current state.

### 26.2. Đọc source state

Với mỗi sequence, đọc last_value và is_called. Cần thực hiện sau khi mọi application sessions có thể gọi nextval đã dừng.

### 26.3. Ghi lại state

Lưu sequence states vào artifact migration có quyền truy cập hạn chế và ghi rõ mapping source-to-target. Không lưu secrets cùng file này.

### 26.4. Set target

Dùng setval trên target với giá trị và is_called tương ứng. Không hardcode MAX(id)+1 cho mọi sequence vì sequence có thể có increment/start khác 1 hoặc được dùng độc lập.

### 26.5. Identity columns

Dùng pg_get_serial_sequence để tìm identity/serial sequence. Kiểm tra target identity definition và sequence ownership.

### 26.6. Kiểm tra nextval

Trước khi mở writes, xác nhận giá trị tiếp theo không xung đột với keys đã replicate. Với sequence tăng 1 và is_called=true, nextval trả giá trị sau last_value.

### 26.7. Không để writers chạy đồng thời

Nếu source hoặc target còn session gọi sequence trong lúc sync, state có thể thay đổi sau khi capture. Giữ write freeze cho tới khi hoàn tất.

## 27. Cutover ứng dụng

Khi barrier và sequence sync hoàn tất, chuyển ứng dụng sang target.

### 27.1. Xác nhận target readiness

Kiểm tra subscription status, schema, indexes, constraints, privileges, extensions, sequence states, large objects và application smoke tests.

### 27.2. Chuyển connection endpoint

Cập nhật service discovery, DNS, proxy, connection strings hoặc secret configuration để ứng dụng kết nối target.

### 27.3. Recycle connection pools

Đóng connections cũ và tạo connections mới. Đảm bảo không còn application sessions ghi vào source.

### 27.4. Chỉ mở một writer

Trong cutover, source phải tiếp tục được fence/read-only hoặc không thể nhận application writes. Tránh dual-write giữa hai database.

### 27.5. Enable writes trên target

Sau khi routing xác nhận, bật application writes và theo dõi lỗi database, latency, constraints và sequence generation.

### 27.6. Background jobs

Chuyển scheduled jobs, workers, ETL, cron tasks và consumers sang target. Kiểm tra các job không phụ thuộc hostname cũ.

### 27.7. Observability

Cập nhật dashboards/alerts để nhận diện target là primary mới. Không hardcode role theo hostname cũ.

### 27.8. Theo dõi ổn định

Theo dõi application errors, connection counts, transaction rate, query latency, replication/slot status và database logs trong cutover window.

## 28. Rollback strategy

Rollback phải được thiết kế trước khi bắt đầu migration.

### 28.1. Trước khi target nhận writes

Nếu chưa mở writes trên target, có thể giữ source làm primary và chuyển endpoint trở lại sau khi xác nhận source vẫn ở trạng thái nhất quán. Subscription/slot có thể được giữ để điều tra hoặc retry.

### 28.2. Sau khi target nhận writes

Source đã trở thành stale. Chỉ chuyển ứng dụng về source sẽ làm mất các writes mới trên target.

### 28.3. Reverse replication

Có thể thiết kế một logical replication stream ngược hoặc một cơ chế reconciliation, nhưng cần schema compatibility, publication/subscription riêng và xử lý conflict. Không tự động xuất hiện chỉ vì đã có subscription ban đầu.

### 28.4. Write freeze trong rollback

Nếu cần quay lại source sau khi target đã nhận writes, dừng writes ở target, đồng bộ delta ngược hoặc export/reconcile dữ liệu mới rồi mới chuyển traffic.

### 28.5. Sequence reconciliation

Rollback sau target writes cần sync sequence theo hướng ngược và kiểm tra duplicate IDs.

### 28.6. External side effects

Email, payment, queue messages, object storage và external APIs không được logical replication rollback. Reconciliation cần xem cả những hệ thống đó.

### 28.7. Rollback deadline

Định nghĩa thời điểm kết thúc rollback window. Sau đó, source có thể được retire theo quy trình riêng và rollback trở thành restore/recovery project.

## 29. Logical replication và pg_dump: phối hợp đúng cách

Hai công cụ có thể bổ sung nhau.

### 29.1. Schema bootstrap

pg_dump --schema-only tạo schema definitions để chuẩn bị target. Roles/globals và extensions cần xử lý riêng.

### 29.2. Initial copy bằng subscription

Dùng copy_data=true để PostgreSQL tự copy các bảng và apply changes từ consistent stream.

### 29.3. Pre-seeded data

Nếu dùng pg_dump để nạp data trước, phải phối hợp snapshot và logical slot. Chỉ đặt copy_data=false sau khi chứng minh baseline và stream có cùng consistency point.

### 29.4. Large objects

Nếu dùng pg_dump để copy large objects, logical replication vẫn không cập nhật LO content sau snapshot. Nếu ứng dụng thay đổi LO trong migration, cần đồng bộ delta riêng hoặc freeze các thay đổi LO.

### 29.5. Sequences

Dump có thể chứa sequence state ở thời điểm dump, nhưng logical stream không cập nhật nó. Đồng bộ lại tại cutover sau khi writes dừng.

### 29.6. Validation

Dùng dump/restore hoặc SQL queries cho các objects ngoài publication và logical replication cho continuous table changes. Giữ inventory rõ phần nào được xử lý bởi công cụ nào.

## 30. Migration theo nhóm bảng

Với database lớn, có thể chia migration thành các nhóm theo dependency và workload.

### 30.1. Core tables

Bắt đầu với bảng ít phụ thuộc hoặc có thể validate độc lập. Theo dõi initial copy duration và apply throughput.

### 30.2. High-write tables

Các bảng có write rate cao cần slot capacity, network và apply workers phù hợp. Nếu apply không theo kịp, lag sẽ tăng.

### 30.3. Large tables

Chọn thời điểm ít tải hoặc dùng pre-seeding có consistent snapshot nếu quy trình đã được kiểm chứng.

### 30.4. Reference tables

Các bảng ít thay đổi có thể được copy sớm để giảm khối lượng công việc ở cutover.

### 30.5. Foreign key groups

Nhóm các bảng có quan hệ chặt chẽ và validation cùng nhau. Không cutover một nhóm khi application vẫn cần cross-table consistency với nhóm còn ở source.

### 30.6. Publication boundaries

Một subscription có thể dùng nhiều publications; đặt tên và ownership rõ ràng. Đảm bảo mỗi table có một replication path dự kiến và không bị publish trùng ngoài ý muốn.

### 30.7. Cutover all-or-nothing

Nếu ứng dụng cần transaction consistency xuyên các nhóm bảng, không chuyển từng nhóm độc lập trừ khi application architecture hỗ trợ dual-database operation một cách rõ ràng.

## 31. Partitioned tables và special table behavior

### 31.1. Partitioned table

Kiểm tra publication có publish partitioned root hay individual partitions theo setting publish_via_partition_root và PostgreSQL version.

### 31.2. Subscriber partition layout

Target có thể có partition layout tương ứng hoặc khác theo supported behavior. Test inserts/updates/delete và partition routing trên đúng version pair.

### 31.3. Table filters

Row filters trên publication có thể tạo subset data. Không dùng cho migration full fidelity trừ khi subset là mục tiêu rõ ràng.

### 31.4. TRUNCATE

Xác minh publish option cho TRUNCATE và foreign key dependencies. Nếu ứng dụng sử dụng TRUNCATE, test trên staging.

### 31.5. Replica identity FULL

Với bảng không có key, FULL có thể tăng lượng dữ liệu cần gửi/so sánh và ảnh hưởng performance. Cân nhắc thêm primary/unique key phù hợp trước migration nếu có thể.

### 31.6. Identity/Generated columns

Kiểm tra explicit identity values và generated column definitions. Subscriber cần tạo ra row state tương đương dù generated values được tính tại target.

## 32. Performance và capacity trong migration

Logical replication tạo workload thêm trên source và target.

### 32.1. Source CPU

Logical decoding và WAL sender tiêu thụ CPU. Theo dõi CPU, active sessions và query latency của ứng dụng.

### 32.2. Source I/O

Initial copy đọc table data; WAL decode đọc WAL; ứng dụng vẫn đọc/ghi. Cân nhắc I/O contention.

### 32.3. Network

Initial copy và change stream cùng dùng network. Theo dõi throughput, retransmissions, latency và bandwidth limit.

### 32.4. Target I/O

Subscriber ghi initial data, indexes và WAL của chính nó. Disk write throughput có thể trở thành bottleneck.

### 32.5. Apply throughput

So sánh tốc độ WAL changes phát sinh với tốc độ subscriber apply. Nếu source sinh thay đổi nhanh hơn target xử lý, lag tăng.

### 32.6. Worker parallelism

Tăng sync workers có thể tăng initial copy throughput nhưng cũng tăng source/target load. Điều chỉnh dựa trên benchmark.

### 32.7. Indexes

Indexes trên subscriber tăng chi phí insert/update. Giữ constraints cần thiết, cân nhắc secondary indexes theo chiến lược được test và hoàn tất trước cutover.

### 32.8. Large transactions

Transaction lớn có thể cần được apply như một đơn vị commit và làm lag tăng đột biến. Theo dõi long transactions và batch size.

### 32.9. Vacuum và bloat

Initial load và apply changes làm tăng table churn. Theo dõi autovacuum, dead tuples, table growth và vacuum progress trên target.

## 33. Monitoring và alerting cho migration

### 33.1. Subscription state

Theo dõi enabled, worker PID, last message times và table synchronization state.

### 33.2. Table readiness

Đếm số bảng chưa ready. Không cutover nếu bảng trong scope vẫn đang initial copy.

### 33.3. Slot state

Theo dõi logical slot active, restart_lsn, confirmed_flush_lsn và wal_status.

### 33.4. Retained WAL

Ước tính WAL bytes đang bị slot giữ và filesystem free space trên publisher.

### 33.5. Replication lag

Theo dõi received/applied progress và barrier. Lag time có thể không chính xác khi publisher idle hoặc không có transactions.

### 33.6. Apply errors

Alert khi apply worker dừng, subscription không có worker hoặc logs có repeated apply errors.

### 33.7. Resource metrics

Theo dõi source/target CPU, disk, network, connections, WAL generation, checkpoints và autovacuum.

### 33.8. Migration dashboard

Một dashboard hữu ích có:
- Initial sync progress theo bảng.
- Subscription worker state.
- Source logical slot state.
- Retained WAL và disk free.
- Apply lag/progress.
- Apply errors.
- Source/target transaction rate.
- CPU, I/O, network.
- Cutover marker state.
- Validation status.

## 34. Troubleshooting

### Lỗi 1. CREATE SUBSCRIPTION báo publisher không cho replication

Kiểm tra wal_level=logical, pg_hba.conf, role REPLICATION, network và source database connection.

### Lỗi 2. Initial copy permission denied

Cấp SELECT đúng các bảng được copy cho replication role và kiểm tra quyền schema/database.

### Lỗi 3. Apply worker dừng do duplicate key

Kiểm tra target có dữ liệu cũ hoặc application writes, xác định row xung đột và khôi phục baseline đúng. Không xóa row tùy tiện.

### Lỗi 4. UPDATE/DELETE không tìm thấy row

Kiểm tra initial copy, manual changes, replica identity và target drift.

### Lỗi 5. Relation does not exist

Schema chưa được tạo hoặc DDL chưa được áp dụng trên target. Tạo object tương thích rồi xử lý worker theo trạng thái.

### Lỗi 6. Column does not exist

Schema mismatch. Đưa target schema về đúng contract trước khi apply tiếp.

### Lỗi 7. Unsupported replica identity

Thêm primary/unique key phù hợp hoặc cấu hình REPLICA IDENTITY FULL khi chấp nhận chi phí.

### Lỗi 8. Subscription worker không chạy

Kiểm tra subenabled, connection, PostgreSQL logs, worker limits và permissions.

### Lỗi 9. WAL disk tăng trên source

Kiểm tra slot active, subscriber lag, retained WAL, apply errors và max_slot_wal_keep_size. Không drop slot nếu migration vẫn cần.

### Lỗi 10. Initial copy quá chậm

Kiểm tra table size, worker count, network, disk I/O, indexes và source workload. Tăng workers chỉ sau khi đo tài nguyên.

### Lỗi 11. Subscriber apply lag tăng

So sánh WAL generation với apply throughput, tìm large transactions, target indexes, triggers, constraints và CPU/I/O bottleneck.

### Lỗi 12. Sequence tạo duplicate key sau cutover

Sequence state chưa được đồng bộ hoặc target đã nhận writes trước khi sync. Freeze writes, xác định sequence và setval có kiểm soát.

### Lỗi 13. Large object thiếu nội dung

OID row được replicate nhưng LO content không. Copy large objects riêng và kiểm tra OID mapping.

### Lỗi 14. DDL deploy làm subscription lỗi

Schema thay đổi không đồng bộ. Áp dụng expand/contract và tạo target schema trước khi publisher phát row shape mới.

### Lỗi 15. Slot bị invalidated

WAL cần thiết đã bị recycle do giới hạn retention hoặc slot mất tính hợp lệ. Cần resync/recreate subscription theo quy trình, không thể bỏ qua gap.

### Lỗi 16. Cutover marker không xuất hiện

Kiểm tra marker table có trong publication, subscription enabled, table ready, apply worker và source transaction commit.

### Lỗi 17. Marker có nhưng validation khác

Có thể có bảng ngoài publication, filter, large objects, sequences, DDL hoặc writes ngoài application path. Đối chiếu inventory và transaction boundary.

### Lỗi 18. Target vẫn nhận writes từ ứng dụng cũ

Kiểm tra DNS, connection pools, background jobs và service discovery. Fence source hoặc target theo cutover plan để chỉ một writer.

### Lỗi 19. Rollback mất writes

Nếu target đã nhận writes, source không có delta mới. Đồng bộ ngược hoặc reconciliation trước khi chuyển về source.

### Lỗi 20. Extension/function khác behavior

Cài đúng extension version, chạy migration scripts và kiểm tra collation/type/function behavior trên target.

## 35. Runbook migration giảm downtime

1. Xác nhận mục tiêu version, RPO/RTO và downtime window.
2. Inventory database objects, tables, sequences, large objects và external dependencies.
3. Xác nhận target version bằng hoặc mới hơn publisher theo compatibility requirements.
4. Cài extensions và chuẩn bị roles, privileges, tablespaces, locale/collation.
5. Chuẩn bị target database và schema.
6. Xác định publication table scope và replica identity.
7. Freeze DDL hoặc lập expand/contract migration plan.
8. Cấu hình publisher wal_level=logical, slots và senders.
9. Restart publisher nếu cần và xác nhận settings.
10. Tạo replication role, grants và pg_hba/TLS.
11. Cấu hình subscriber worker capacity và disk/network.
12. Tạo publication.
13. Tạo subscription với copy_data=true cho baseline thông thường.
14. Theo dõi initial table synchronization.
15. Theo dõi apply lag, logical slot và WAL retention.
16. Validate schema, counts, aggregates và business invariants.
17. Copy large objects/external data riêng.
18. Chuẩn bị sequence inventory và sync script.
19. Test application reads trên target và kiểm tra permissions/extensions.
20. Lập cutover communication và rollback plan.
21. Tạm dừng source writes, schedulers và consumers.
22. Drain active/long transactions.
23. Insert và commit migration marker trên bảng được publish.
24. Chờ marker xuất hiện trên target.
25. Xác nhận mọi bảng ready và apply errors bằng zero.
26. Đồng bộ sequence states từ source sang target.
27. Chạy final validation và smoke tests.
28. Disable subscription nếu quy trình cutover yêu cầu.
29. Fence source để không còn application writes.
30. Chuyển application endpoint/credentials sang target.
31. Recycle connection pools và chuyển background jobs.
32. Mở writes trên target.
33. Theo dõi lỗi, latency, connections, storage và business invariants.
34. Giữ source/slot theo rollback window đã định.
35. Chỉ cleanup source subscription/slot sau khi quyết định retire và xác nhận không còn rollback dependency.

## 36. Bài tập thực hành

Các bài tập nên chạy trên hai PostgreSQL instances riêng trong lab. Không tạo/drop replication slots hoặc chuyển endpoint production khi chưa có change plan.

### Bài 1. Logical replication

Vì sao logical replication giúp giảm downtime so với dump/restore thuần túy?

### Bài 2. Components

Phân biệt publisher, publication, subscriber và subscription.

### Bài 3. Slot

Logical replication slot có vai trò gì?

### Bài 4. Version

Trong migration cross-major, hướng version nào thường được hỗ trợ?

### Bài 5. wal_level

Cần đặt wal_level thành giá trị nào trên publisher?

### Bài 6. Restart

Vì sao thay wal_level cần restart?

### Bài 7. Replication role

Tạo role có quyền LOGIN và REPLICATION bằng SQL nào?

### Bài 8. SELECT privilege

Vì sao replication role cần SELECT trên các bảng initial copy?

### Bài 9. Publication

Viết lệnh tạo publication cho ba bảng app.customers, app.orders và app.order_items.

### Bài 10. FOR ALL TABLES

Khi nào nên tránh FOR ALL TABLES?

### Bài 11. Subscription

Viết lệnh tạo subscription với copy_data=true.

### Bài 12. Initial copy

Initial table synchronization hoạt động như thế nào?

### Bài 13. copy_data=false

Vì sao không nên tạo pg_dump/restore bình thường rồi bật copy_data=false mà không phối hợp snapshot?

### Bài 14. DDL

Logical replication có replicate CREATE/ALTER TABLE không?

### Bài 15. Sequence

Vì sao cần sync sequence tại cutover?

### Bài 16. Large object

Vì sao table OID reference được replicate nhưng LO content không?

### Bài 17. Replica identity

Vì sao UPDATE/DELETE cần replica identity?

### Bài 18. FULL

REPLICA IDENTITY FULL có trade-off nào?

### Bài 19. Table state

View nào theo dõi trạng thái đồng bộ từng bảng?

### Bài 20. Subscription stats

View nào cung cấp trạng thái subscription workers?

### Bài 21. Replication origin

pg_replication_origin_status giúp kiểm tra điều gì?

### Bài 22. WAL retention

Vì sao slot có thể làm pg_wal tăng?

### Bài 23. max_slot_wal_keep_size

Tham số này bảo vệ filesystem theo cách nào và có rủi ro gì?

### Bài 24. Apply error

Kể ba nguyên nhân khiến apply worker dừng.

### Bài 25. Target writes

Vì sao không nên để ứng dụng ghi vào target trong lúc subscription đang apply?

### Bài 26. DDL freeze

Vì sao cần freeze hoặc phối hợp DDL hai phía?

### Bài 27. Validation

Nêu bốn cách kiểm tra dữ liệu source và target.

### Bài 28. Barrier

Vì sao marker row cần nằm trong publication?

### Bài 29. Cutover

Nêu thứ tự chính giữa freeze writes, marker, sequence sync và endpoint switch.

### Bài 30. Sequence state

Những thông tin nào cần ghi lại khi sync một sequence?

### Bài 31. Rollback

Vì sao không thể chỉ đổi endpoint về source sau khi target đã nhận writes?

### Bài 32. Reverse replication

Khi nào cần thiết kế replication ngược?

### Bài 33. Partitioning

Cần kiểm tra setting nào liên quan publish partition root?

### Bài 34. Generated columns

Generated column cần được xử lý thế nào trên subscriber?

### Bài 35. TRUNCATE

Vì sao cần test TRUNCATE behavior và foreign key dependencies?

### Bài 36. Monitoring

Kể năm metrics/state cần theo dõi trong migration.

### Bài 37. Performance

Nêu các tài nguyên có thể trở thành bottleneck trong initial copy.

### Bài 38. Slot invalidation

Nếu slot bị invalidated vì thiếu WAL, có thể tiếp tục apply như bình thường không?

### Bài 39. Large objects

Đề xuất cách migration large objects cùng table references.

### Bài 40. Thiết kế

Đề xuất kế hoạch logical replication migration cho database lớn có một primary, nhiều bảng và yêu cầu downtime ngắn.

## 37. Lời giải tham khảo

### Bài 1–4. Khái niệm

Logical replication copy baseline rồi chuyển tiếp các changes liên tục, nên source vẫn phục vụ ứng dụng trong initial copy. Publisher phát thay đổi; publication định nghĩa scope; subscriber nhận; subscription kết nối publication. Slot giữ WAL cần thiết. Cross-major migration thường dùng publisher cũ và subscriber mới hơn theo compatibility requirements.

### Bài 5–8. Chuẩn bị

Publisher cần wal_level=logical và restart nếu thay đổi. Tạo role:

~~~sql
CREATE ROLE migration_repl LOGIN REPLICATION PASSWORD 'replace-with-secret';
~~~

Role cần SELECT trên bảng để initial table copy đọc dữ liệu. Bảo vệ credential và dùng TLS.

### Bài 9–13. Publication và subscription

~~~sql
CREATE PUBLICATION app_migration_pub
FOR TABLE app.customers, app.orders, app.order_items;
~~~

Tránh FOR ALL TABLES nếu chỉ cần một tập bảng hoặc không muốn tự động mở rộng scope. Subscription:

~~~sql
CREATE SUBSCRIPTION app_migration_sub
CONNECTION 'host=source-db.internal dbname=sourcedb user=migration_repl sslmode=verify-full'
PUBLICATION app_migration_pub
WITH (copy_data = true, create_slot = true, enabled = true);
~~~

Initial copy lấy snapshot từng bảng rồi apply changes phát sinh sau snapshot. copy_data=false chỉ an toàn khi baseline data và slot consistent point được phối hợp; một pg_dump bình thường không tự tạo quan hệ này.

### Bài 14–18. Schema và replica identity

DDL không tự replicate. Sequence state cũng không replicate. Large object content không replicate dù OID column có thể được gửi. UPDATE/DELETE cần xác định row cũ bằng primary key/unique index hoặc REPLICA IDENTITY FULL. FULL có thể tăng WAL, network và apply cost.

### Bài 19–24. Monitoring và lỗi

pg_subscription_rel theo dõi table sync state; pg_stat_subscription theo dõi worker; pg_replication_origin_status theo dõi remote/local apply progress. Slot giữ WAL khi subscriber chậm/offline. max_slot_wal_keep_size giới hạn lượng WAL giữ nhưng nếu quá ngưỡng slot có thể invalidated và cần resync. Apply worker có thể dừng do duplicate key, missing row, schema mismatch, permissions hoặc constraint violation.

### Bài 25–30. Cutover

Target không nên nhận application writes vì stream một chiều và có thể tạo conflicts. Freeze DDL để schema tương thích. Validation gồm schema comparison, row counts, aggregates/checksums và business invariants. Marker table phải được publish để marker commit đi qua cùng stream. Thứ tự cutover: freeze/drain source writes, commit marker, chờ marker trên target, sync sequences, validate cuối, fence source và switch endpoint. Ghi sequence last_value, is_called, increment/start và ownership mapping.

### Bài 31–35. Rollback và special tables

Sau khi target nhận writes, source không có các thay đổi đó; rollback cần reverse replication hoặc reconciliation. Partitioned table cần kiểm tra publish_via_partition_root. Generated columns được tính tại subscriber theo definition phù hợp. TRUNCATE cần test vì publication option và foreign key relationships ảnh hưởng kết quả apply.

### Bài 36–40. Vận hành

Theo dõi table readiness, worker state, slot retained WAL, apply lag, errors, CPU, I/O, network và disk. Initial copy bottleneck có thể là source read I/O, target write I/O, network, indexes hoặc worker limits. Slot invalidated không thể tiếp tục như bình thường; cần resync/rebuild theo plan. Large objects cần copy riêng, giữ OID mapping và cập nhật references khi cần.

Migration database lớn cần inventory, chuẩn bị schema/roles/extensions, logical publication/subscription, initial copy, continuous catch-up, validation, freeze writes, marker barrier, sequence/LO sync, endpoint cutover, monitoring và rollback window. Giữ source fenced sau cutover để không tạo dual-writer.

## 38. Bảng tra cứu nhanh

| Nhu cầu | Công cụ / view |
| --- | --- |
| Bật logical WAL | wal_level = logical |
| Tạo replication role | CREATE ROLE ... REPLICATION |
| Cấp quyền đọc initial copy | GRANT SELECT |
| Cho phép kết nối replication | pg_hba.conf |
| Tạo publication | CREATE PUBLICATION |
| Kiểm tra publication | pg_publication |
| Kiểm tra publication tables | pg_publication_tables |
| Tạo subscription | CREATE SUBSCRIPTION |
| Tạm dừng subscription | ALTER SUBSCRIPTION ... DISABLE |
| Bật subscription | ALTER SUBSCRIPTION ... ENABLE |
| Kiểm tra subscription | pg_subscription |
| Worker state | pg_stat_subscription |
| Table sync state | pg_subscription_rel |
| Logical slot state | pg_replication_slots |
| WAL sender state | pg_stat_replication |
| Apply origin progress | pg_replication_origin_status |
| Tìm sequence của column | pg_get_serial_sequence() |
| Đọc sequence state | SELECT last_value, is_called |
| Đặt sequence state | setval() |
| Xác minh target | SQL counts/aggregates/checksums |
| Cutover barrier | Published marker table |
| Schema bootstrap | pg_dump --schema-only |
| Logical initial copy | copy_data = true |
| Pre-seeded subscription | copy_data = false (consistent snapshot required) |
| Slot WAL cap | max_slot_wal_keep_size |
| Worker capacity | max_logical_replication_workers / max_sync_workers_per_subscription |
| Target version | Same or newer supported subscriber |
| Large objects | Separate copy/mapping workflow |

## 39. Checklist migration bằng logical replication

1. Xác định source, target, PostgreSQL versions và downtime objective.
2. Inventory tables, partitions, types, functions, views, triggers và constraints.
3. Inventory sequences, identity columns, large objects và external files.
4. Inventory roles, memberships, grants, tablespaces và extensions.
5. Xác nhận subscriber version tương thích với publisher.
6. Chuẩn bị target database, encoding, locale và collation.
7. Cài extension packages và tạo schema.
8. Kiểm tra primary keys/replica identity cho UPDATE/DELETE.
9. Freeze DDL hoặc có expand/contract plan.
10. Cấu hình publisher wal_level=logical.
11. Cấu hình max_replication_slots và max_wal_senders.
12. Cấu hình subscriber logical/sync workers.
13. Restart publisher khi cần và kiểm tra settings.
14. Tạo replication role và SELECT grants.
15. Cấu hình pg_hba, TLS, secrets và network.
16. Tạo publication với table scope rõ ràng.
17. Kiểm tra publication tables và publish operations.
18. Chuẩn bị subscriber tables tương thích.
19. Tạo subscription với copy_data=true hoặc pre-seeding đã được chứng minh consistent.
20. Theo dõi initial table synchronization tới trạng thái ready.
21. Theo dõi apply workers và errors.
22. Theo dõi logical slot retained WAL và source disk headroom.
23. Theo dõi apply lag và throughput.
24. Validate schema, counts, aggregates và business invariants.
25. Copy large objects và external data riêng.
26. Chuẩn bị sequence inventory và cutover sync script.
27. Kiểm thử application reads, permissions, extensions và query plans trên target.
28. Tạm dừng writes/background jobs ở source khi cutover.
29. Drain transactions và ngăn writers mới.
30. Commit marker trên bảng đã publish.
31. Chờ marker được apply trên target.
32. Xác nhận tất cả bảng ready và không còn apply errors.
33. Đồng bộ last_value/is_called của sequences.
34. Chạy final validation và smoke tests.
35. Disable subscription nếu cần cho cutover.
36. Fence source và xác nhận chỉ target nhận writes.
37. Chuyển endpoints, connection pools, jobs và consumers.
38. Mở writes trên target.
39. Theo dõi latency, errors, capacity và business invariants.
40. Giữ rollback window; chỉ drop slot/retire source sau quyết định cuối.

## 40. Tổng kết

Logical replication giảm downtime bằng cách copy dữ liệu ban đầu trong khi source vẫn hoạt động, sau đó tiếp tục chuyển các changes đã commit tới subscriber. Khi target đã gần bắt kịp, đội vận hành có thể dừng writes trong một cửa sổ ngắn, dùng marker để xác nhận stream đã apply tới điểm cutover, đồng bộ sequences và chuyển ứng dụng.

Migration cần chuẩn bị publication/subscription, wal_level=logical, replication roles, slots, WAL senders, apply workers, schema và quyền trên target. Theo dõi initial table sync, apply lag và slot retention xuyên suốt quá trình. Slot giữ WAL cho subscriber nhưng có thể làm đầy disk nếu target chậm hoặc mất kết nối; không drop slot khi còn cần migration stream.

Logical replication chỉ xử lý table changes trong publication. DDL, sequence state, large objects, roles, extensions, FDW và external files cần được xử lý riêng. Schema mismatch, replica identity không phù hợp, duplicate keys, missing rows và subscriber-only writes có thể làm apply worker dừng hoặc khiến dữ liệu hai phía khác nhau. Hãy validate schema, row counts, aggregates, business invariants và các object ngoài phạm vi trước cutover.

Cutover an toàn cần freeze writers, drain transactions, commit marker trên bảng được publish, chờ marker xuất hiện trên target, đồng bộ sequence states, chạy final checks rồi mới chuyển endpoints. Giữ source không nhận writes để tránh split-brain. Sau khi target nhận writes, rollback cần reverse synchronization hoặc reconciliation; đổi connection string về source không tự mang các writes mới quay lại.

Hãy kiểm thử toàn bộ quy trình trên staging với cùng version pair và dữ liệu đại diện. Đo initial copy, apply throughput, WAL retention, validation time và cutover duration. Một runbook có owner, barrier, sequence sync, large-object plan, rollback boundary và monitoring rõ ràng sẽ biến logical replication thành một phương án migration có downtime ngắn và có thể kiểm soát.
