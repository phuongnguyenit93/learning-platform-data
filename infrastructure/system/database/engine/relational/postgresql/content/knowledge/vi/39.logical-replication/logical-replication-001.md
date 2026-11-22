# Khác biệt giữa sao chép logic và vật lý trong PostgreSQL

PostgreSQL có hai cách chính để truyền thay đổi từ một database server sang server khác: **physical replication** và **logical replication**. Cả hai đều có thể sử dụng WAL và replication protocol, nhưng chúng truyền thông tin ở các mức khác nhau và giải quyết những nhu cầu khác nhau.

Physical replication chuyển các WAL records để standby tái tạo thay đổi ở mức storage. Kết quả là một bản sao vật lý của toàn bộ PostgreSQL cluster, thường được dùng cho high availability (HA), failover, disaster recovery và read-only hot standby.

Logical replication giải mã thay đổi từ WAL thành các thao tác dữ liệu ở mức bảng và row, rồi áp dụng chúng lên subscriber. Nó cho phép chọn publication, bảng và trong các phiên bản hỗ trợ có thể chọn row hoặc column. Cơ chế này phù hợp với selective replication, data integration, CDC và migration giữa các major versions.

Không có lựa chọn nào luôn tốt hơn lựa chọn kia. Hãy chọn theo câu hỏi: cần một standby thay thế nguyên cluster hay cần truyền một tập thay đổi dữ liệu có chọn lọc sang một database khác?

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích physical replication và logical replication trong PostgreSQL.
2. Mô tả luồng WAL sender/receiver và logical decoding/apply.
3. Phân biệt phạm vi dữ liệu được sao chép ở mỗi cơ chế.
4. Giải thích vai trò của wal_level, replication slots, publications và subscriptions.
5. Cấu hình một physical standby cơ bản.
6. Cấu hình một publication/subscription cơ bản.
7. Hiểu initial copy, streaming changes và tiến độ replication.
8. Phân biệt read-only hot standby với logical subscriber có thể nhận writes cục bộ.
9. Hiểu các giới hạn về DDL, sequences, large objects và schema compatibility của logical replication.
10. Chọn replica identity cho bảng có UPDATE/DELETE.
11. Phân tích replication lag, conflicts và WAL retention.
12. Theo dõi physical/logical replication bằng system views.
13. Chọn cơ chế phù hợp cho HA, DR, selective replication, CDC và major-version migration.
14. Thiết kế quy trình cutover, failover, resynchronization và bảo mật.

## 2. Hai cơ chế ở hai mức khác nhau

### 2.1. Physical replication

Physical replication truyền WAL để standby replay thay đổi trên một bản sao tương thích của cluster. Standby nhận cùng lịch sử thay đổi vật lý và duy trì một data directory tương ứng với primary.

~~~text
Application
    |
    v
Primary PostgreSQL
    |
    | WAL records
    v
WAL sender / replication connection
    |
    v
WAL receiver on standby
    |
    v
Write and replay WAL
    |
    v
Physical standby
~~~

Standby có thể chạy hot standby để phục vụ các truy vấn đọc trong khi replay WAL. Khi primary gặp sự cố, một standby phù hợp có thể được promote thành primary mới.

### 2.2. Logical replication

Logical replication giải mã thay đổi từ WAL thành các thay đổi dữ liệu logic. Publisher xác định bảng được công bố; subscriber nhận initial table data nếu được yêu cầu và tiếp tục apply thay đổi.

~~~text
Publisher database
    |
    v
WAL at logical level
    |
    v
Logical decoding
    |
    v
Publication / logical replication protocol
    |
    v
Subscriber apply worker
    |
    v
Subscriber tables
~~~

Subscriber có schema và storage riêng. Nó có thể chứa một tập bảng được chọn từ publisher và có thể phục vụ workload riêng, tùy cách thiết kế quyền ghi.

### 2.3. Điểm khác biệt cốt lõi

- Physical replication sao chép trạng thái cluster ở mức vật lý qua WAL.
- Logical replication sao chép các thay đổi dữ liệu logic của những bảng được publish.
- Physical standby là bản sao của cluster; logical subscriber là một database độc lập nhận changes theo publication.
- Physical replication phù hợp để thay primary; logical replication phù hợp để chia sẻ hoặc chuyển dữ liệu có chọn lọc.

## 3. WAL là nền tảng của cả hai

PostgreSQL sử dụng Write-Ahead Log (WAL) để ghi lại những thay đổi cần cho recovery. Physical replication gửi WAL records để standby replay. Logical replication cũng dựa trên WAL, nhưng publisher cần ghi đủ thông tin cho logical decoding.

### 3.1. wal_level

Các mức chính:

| Giá trị | Mục đích |
| --- | --- |
| minimal | Thông tin cần cho crash recovery cục bộ |
| replica | Thông tin cho WAL archiving và physical replication |
| logical | Bổ sung thông tin cho logical decoding |

Physical replication cần wal_level=replica hoặc logical. Logical replication cần wal_level=logical trên publisher.

Ví dụ:

~~~conf
# Physical replication
wal_level = replica

# Logical replication hoặc kết hợp physical + logical
wal_level = logical
~~~

wal_level là setting cần PostgreSQL restart để áp dụng. Kiểm tra trên server:

~~~sql
SHOW wal_level;

SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name = 'wal_level';
~~~

### 3.2. WAL sender và receiver

Primary dùng WAL sender processes để phục vụ replication connections. Standby physical có WAL receiver để nhận stream. Logical subscriber cũng kết nối tới publisher bằng replication protocol, nhưng dữ liệu được gửi theo logical changes.

### 3.3. Replication slots

Replication slot theo dõi tiến độ của consumer và giữ WAL mà consumer còn cần. Có hai loại phổ biến:

- Physical slot: giữ WAL cho physical standby.
- Logical slot: giữ WAL cho logical decoding/subscriber.

Slot giúp consumer reconnect mà không mất WAL cần thiết, nhưng slot inactive có thể giữ WAL quá lâu và làm đầy disk. Cần theo dõi restart_lsn, consumer lag và giới hạn retention.

### 3.4. Archive vẫn có vai trò riêng

WAL archive lưu segment ra nơi độc lập để phục vụ PITR và recovery. Replication slot hoặc streaming connection không thay thế base backup và WAL archive. Một kiến trúc production thường kết hợp replication với backup/PITR.

## 4. Phạm vi dữ liệu được sao chép

| Thành phần | Physical replication | Native logical replication |
| --- | --- | --- |
| Table rows | Toàn bộ cluster state được replay | Chỉ bảng thuộc publication |
| Schema/DDL | Được phản ánh qua physical WAL/system catalogs | Không tự replicate DDL; phải triển khai schema riêng |
| Indexes | Có vì là một phần physical database | Không replicate index definition; subscriber cần schema/index riêng |
| Constraints | Có trong physical state | Phải tạo schema/constraints ở subscriber |
| Roles và grants | Cluster-level catalog changes được replay | Phải quản lý riêng |
| Sequences | Physical state được replay | Sequence state không được đồng bộ như table row changes |
| Large objects | Nằm trong physical cluster state | Không được native logical replication replicate như bảng |
| Extensions | Catalog state được replay; binary/config vẫn cần trên host | Cần cài/cấu hình phù hợp riêng trên subscriber |
| Database khác trong cùng cluster | Cũng nằm trong cluster physical copy | Publication/subscription được cấu hình theo database |
| Server configuration files | Không tự copy file cấu hình ngoài data directory | Không tự copy |
| WAL history | Physical WAL stream | Logical changes được giải mã từ WAL |

### 4.1. Physical replication là toàn cluster

Một PostgreSQL instance có thể chứa nhiều databases. Physical standby tái tạo cluster ở mức vật lý, không chọn riêng một database hoặc vài bảng.

Nó cũng không tự sao chép mọi thứ nằm ngoài PostgreSQL data directory, chẳng hạn file cấu hình đặt ở đường dẫn riêng, certificates, scripts, service definitions, secrets hoặc application files. Những phần này cần configuration management và backup riêng.

### 4.2. Logical replication là theo publication

Publication thuộc một database và xác định những bảng/changes được gửi. Một subscriber có thể nhận một tập con dữ liệu thay vì toàn bộ cluster.

Logical replication không tự mang theo toàn bộ cluster metadata. Schema, roles, grants, extension binaries, functions và các dependencies phải được quản lý theo quy trình riêng.

## 5. So sánh tổng quan

| Tiêu chí | Physical replication | Logical replication |
| --- | --- | --- |
| Đơn vị sao chép | Cluster vật lý | Changes của bảng được publish |
| Dữ liệu truyền | WAL records | Logical row changes |
| Cấu hình chính | wal_level=replica, sender/receiver | wal_level=logical, publication/subscription |
| Initial setup | Base backup | Schema chuẩn bị trước, optional initial table copy |
| Read behavior | Hot standby thường read-only | Subscriber là database độc lập, có thể nhận local writes |
| Chọn bảng | Không | Có |
| Row/column filtering | Không | Có ở các phiên bản hỗ trợ |
| DDL tự động | Có qua physical WAL | Không |
| Sequence state | Có | Không tự đồng bộ |
| Cross-major migration | Không dùng physical WAL trực tiếp giữa major versions khác nhau | Có thể dùng logical replication với version direction/compatibility phù hợp |
| HA failover | Là use case chính | Không phải physical standby replacement |
| Selective data sharing | Không | Phù hợp |
| CDC/integration | Cần giải mã/consumer khác | Phù hợp với logical decoding |
| Lag monitoring | WAL sent/write/flush/replay | Slot LSN và subscription apply progress |
| Disk retention risk | Slot/archive/standby lag | Logical slot có thể giữ WAL và catalog history |
| Conflict type | Recovery conflicts trên standby | Apply conflicts với dữ liệu/schema subscriber |
| Use case tiêu biểu | HA, DR, read replicas | CDC, migration, data distribution |

## 6. Physical replication hoạt động như thế nào?

Physical replication giữ một standby đồng bộ với primary bằng cách gửi WAL. Standby được khởi tạo từ base backup tương thích rồi tiếp tục nhận WAL.

### 6.1. Initial base backup

Một standby mới không thể chỉ kết nối tới primary và tự nhận toàn bộ dữ liệu lịch sử. Nó cần một base backup hoặc một bản physical copy nhất quán tương thích.

Ví dụ tạo base backup:

~~~bash
pg_basebackup \
  --host=primary.example.internal \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/standby \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf
~~~

Tên option có thể được viết ngắn là -R. Binary phải tương thích với PostgreSQL major version của cluster.

### 6.2. WAL streaming

Sau khi base backup hoàn tất, standby kết nối tới primary, nhận WAL từ vị trí cần thiết và replay.

### 6.3. Hot standby

Nếu hot_standby được bật và recovery state phù hợp, standby có thể phục vụ read-only queries trong lúc replay WAL.

~~~sql
SELECT pg_is_in_recovery();
~~~

Trên standby đang ở recovery, kết quả thường là true. Standby không nhận các writes thông thường của ứng dụng.

### 6.4. Promote

Khi quyết định failover, standby có thể được promote. Nó rời recovery mode và bắt đầu hoạt động như primary mới, ghi WAL theo timeline mới.

Promotion cần quy trình fencing để bảo đảm primary cũ không tiếp tục nhận writes.

## 7. Cấu hình physical replication cơ bản

### 7.1. Primary configuration

Ví dụ:

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = 2GB
~~~

Các con số chỉ minh họa. Tính sender/slot theo số standbys, backup clients và các replication connections.

### 7.2. Replication role

~~~sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
~~~

Password chỉ là placeholder. Production nên dùng secret management hoặc cơ chế xác thực phù hợp, không commit secret vào Git.

### 7.3. pg_hba.conf

Ví dụ cho một subnet nội bộ:

~~~conf
host  replication  replicator  10.20.0.0/24  scram-sha-256
~~~

Giới hạn network source và dùng TLS theo yêu cầu bảo mật.

### 7.4. Tạo physical slot

Trên primary:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
~~~

### 7.5. Cấu hình standby

Ví dụ:

~~~conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a'
primary_slot_name = 'standby_a'
~~~

Base backup workflow hoặc -R có thể tạo standby.signal và recovery connection settings phù hợp. Không tạo data directory mới bằng cách copy file khi primary đang ghi mà không dùng quy trình backup nhất quán.

### 7.6. Kiểm tra primary

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
FROM pg_stat_replication;
~~~

Nếu không có row, kiểm tra standby connection, authentication, pg_hba.conf, network và logs.

## 8. Các chế độ physical replication

### 8.1. Asynchronous replication

Primary không cần đợi standby xác nhận WAL trước khi commit trả về. Latency thấp hơn, nhưng khi primary hỏng có thể mất các commits chưa tới standby được promote.

### 8.2. Synchronous replication

Primary có thể chờ standby xác nhận WAL theo cấu hình synchronous replication. Cách này giảm data loss cho commits được xác nhận theo mức sync đã chọn, nhưng có thể tăng latency hoặc ảnh hưởng availability khi synchronous standby không sẵn sàng.

Ví dụ:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Đây chỉ là cấu hình minh họa; cần hiểu rõ synchronous_commit, synchronous_standby_names và failover policy.

### 8.3. Cascading replication

Một standby có thể gửi WAL tiếp cho standby khác:

~~~text
Primary
  |
  +---- Standby A
           |
           +---- Standby B
           |
           +---- Standby C
~~~

Cascading giảm số kết nối trực tiếp tới primary và có thể phân phối replicas theo vùng. Mỗi tầng cần đủ WAL, network và capacity để downstream bắt kịp.

### 8.4. WAL archive và streaming

Standby có thể nhận WAL qua streaming, lấy segment từ archive hoặc kết hợp cả hai. Archive là đường phục hồi khi segment cần thiết không còn trong pg_wal trên upstream.

## 9. Logical replication hoạt động như thế nào?

Logical replication sử dụng logical decoding để chuyển WAL records thành thay đổi ở mức bảng/row. Publisher phát changes theo publication; subscriber apply changes vào những bảng tương ứng.

### 9.1. Publisher

Publisher là database có publication và nguồn logical changes.

### 9.2. Publication

Publication xác định bảng và loại operations được publish, ví dụ INSERT, UPDATE, DELETE và TRUNCATE.

### 9.3. Logical replication slot

Slot theo dõi vị trí logical decoding cần giữ. Nó cho phép subscriber tiếp tục từ vị trí đã xác nhận khi reconnect, miễn WAL cần thiết còn tồn tại.

### 9.4. Subscriber

Subscriber tạo subscription để kết nối publisher. Apply worker nhận changes và cập nhật các bảng tương ứng.

### 9.5. Initial table synchronization

Khi subscription được tạo với copy_data bật, PostgreSQL có thể copy dữ liệu hiện có của các bảng được publish rồi chuyển sang apply changes phát sinh trong thời gian đồng bộ. Nếu copy_data=false, dữ liệu ban đầu phải được nạp bằng cách khác và phải nhất quán với replication start position.

### 9.6. Schema phải có trước

Native logical replication không tự tạo đầy đủ schema trên subscriber. Bảng, columns và các cấu trúc cần thiết phải được tạo trước bằng migration/deployment tooling.

## 10. Cấu hình logical replication cơ bản

### 10.1. Publisher configuration

~~~conf
wal_level = logical
max_wal_senders = 10
max_replication_slots = 10
~~~

Các giá trị cần đủ cho subscriptions, table synchronization workers và những replication clients khác. wal_level cần restart.

### 10.2. Tạo publication

Trên publisher database:

~~~sql
CREATE PUBLICATION sales_publication
FOR TABLE
    sales.orders,
    sales.order_items;
~~~

Publication chỉ bao gồm hai bảng được chỉ định.

Để publish tất cả bảng hiện có và những bảng được tạo sau đó theo semantics của FOR ALL TABLES:

~~~sql
CREATE PUBLICATION all_tables_publication
FOR ALL TABLES;
~~~

FOR ALL TABLES có phạm vi rộng; cần kiểm tra quyền và dữ liệu nào được phép rời publisher.

### 10.3. Tạo subscriber schema

Tạo database, schema, tables và các indexes/constraints cần thiết trên subscriber qua migration tooling. Schema tương thích là điều kiện để apply changes thành công.

### 10.4. Tạo subscription

Trên subscriber database:

~~~sql
CREATE SUBSCRIPTION sales_subscription
CONNECTION 'host=publisher.example.internal port=5432 dbname=salesdb user=logical_reader'
PUBLICATION sales_publication
WITH (copy_data = true);
~~~

Ví dụ cần role và authentication phù hợp. Quản lý password bằng secret store/credential mechanism; không ghi secret thật vào tài liệu, shell history hoặc repository.

### 10.5. Kiểm tra subscription

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Các cột có thể thay đổi theo phiên bản. Dùng \d+ pg_stat_subscription hoặc tài liệu đúng major version để hiểu schema view.

### 10.6. Tạo slot thủ công

Subscription thường quản lý publisher-side logical slot. Nếu workflow tạo slot thủ công, phải thống nhất slot name, plugin, LSN và subscription options; không tạo slot trùng hoặc bỏ quên slot không còn consumer.

## 11. Publication có thể publish những gì?

Publication có thể chỉ định operations:

~~~sql
CREATE PUBLICATION orders_changes
FOR TABLE sales.orders
WITH (publish = 'insert, update, delete, truncate');
~~~

### 11.1. INSERT

Row mới được gửi tới subscriber.

### 11.2. UPDATE

Thay đổi row được gửi. Subscriber phải có cách xác định row cũ theo replica identity.

### 11.3. DELETE

Thông tin cần để xác định row bị xóa được gửi. Replica identity đặc biệt quan trọng.

### 11.4. TRUNCATE

TRUNCATE có thể được publish trong các phiên bản hỗ trợ. Cần kiểm tra semantics, bảng được publish và ảnh hưởng cascade; không suy ra rằng mọi object liên quan tự được đồng bộ.

### 11.5. Row filters và column lists

Các phiên bản PostgreSQL mới hỗ trợ row filters và column lists trong publication. Điều này cho phép giới hạn rows/columns được publish, nhưng phải xem xét version compatibility và tính nhất quán của filter ở publisher/subscriber.

Ví dụ ý tưởng với row filter:

~~~sql
CREATE PUBLICATION active_customers
FOR TABLE app.customers
WHERE (active = true);
~~~

Cú pháp và giới hạn cụ thể cần kiểm tra theo major version. Row filtering không thay thế security policy tổng thể; subscriber vẫn cần kiểm soát truy cập.

## 12. Replica identity trong logical replication

Khi publisher gửi UPDATE hoặc DELETE, subscriber cần nhận diện row tương ứng. PostgreSQL dùng replica identity cho mục đích này.

### 12.1. DEFAULT

Mặc định, PostgreSQL dùng primary key nếu bảng có primary key.

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY DEFAULT;
~~~

### 12.2. USING INDEX

Có thể chọn một unique index đáp ứng các điều kiện của PostgreSQL làm replica identity.

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY USING INDEX customers_external_id_key;
~~~

Index phải thỏa điều kiện của phiên bản, bao gồm uniqueness và các thuộc tính cần thiết.

### 12.3. FULL

REPLICA IDENTITY FULL yêu cầu sử dụng toàn bộ old row làm identity information cho UPDATE/DELETE.

~~~sql
ALTER TABLE app.audit_items
REPLICA IDENTITY FULL;
~~~

FULL có thể tăng lượng WAL/decoding/network data và chi phí tìm row trên subscriber. Chỉ dùng khi cần và đã đánh giá hiệu năng.

### 12.4. NOTHING

REPLICA IDENTITY NOTHING không cung cấp identity để định vị row cũ. Bảng có thể publish INSERT, nhưng UPDATE/DELETE cần identity phù hợp; các thao tác này có thể gây lỗi khi apply.

### 12.5. Kiểm tra identity

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2;
~~~

Giá trị trong relreplident là mã nội bộ; dùng catalog documentation hoặc psql để diễn giải theo phiên bản.

## 13. Những gì native logical replication không tự sao chép

Đây là khác biệt quan trọng khi thiết kế migration hoặc subscriber có thể được promote.

### 13.1. DDL

CREATE TABLE, ALTER TABLE, CREATE INDEX và các schema changes không tự được gửi như logical row changes. Phải triển khai DDL riêng trên subscriber theo thứ tự tương thích.

### 13.2. Sequence state

Sequence increments/state không được replicate như table row changes. Nếu subscriber được dùng làm database ghi độc lập hoặc trở thành nguồn ghi sau cutover, cần đồng bộ sequence values để tránh ID collision.

### 13.3. Large objects

Large objects không được native logical replication publish như bảng thông thường. Cần cơ chế copy/transfer riêng.

### 13.4. Roles và grants

Role definitions, passwords và cluster-wide permissions không được tự replicate qua publication. Quản lý bằng provisioning/identity tooling.

### 13.5. Extension binaries và server configuration

Subscriber host phải cài extension binaries tương thích, cấu hình parameter và external dependencies riêng.

### 13.6. Materialized views và các objects khác

Các objects không nằm trong tập table changes của publication không tự được đồng bộ. Xác định những objects cần tạo/rebuild riêng.

### 13.7. Schema evolution

Khi publisher thay đổi schema, subscriber phải được migrate theo trình tự an toàn. Nếu publisher gửi row shape mà subscriber chưa hỗ trợ, apply worker có thể dừng vì lỗi.

## 14. Logical subscriber có thể ghi dữ liệu không?

Subscriber là một PostgreSQL database riêng và không bị đặt vào physical recovery read-only mode chỉ vì đang nhận logical replication. Người dùng có thể ghi local data nếu quyền và kiến trúc cho phép.

Tuy nhiên, writes vào các bảng đang được replicate có thể xung đột với changes từ publisher.

### 14.1. Conflict ví dụ

Publisher insert customer_id=100. Subscriber đã có local row customer_id=100. Apply INSERT có thể gặp unique constraint violation và subscription worker dừng apply cho đến khi xử lý.

### 14.2. Conflict do local update

Publisher cập nhật row nhưng subscriber cũng đã thay đổi row đó. Native logical replication không tự giải quyết mọi business conflict bằng merge logic tổng quát.

### 14.3. Tránh dual-write không kiểm soát

Nếu hai phía cùng ghi một tập bảng, cần thiết kế ownership, keyspace, conflict resolution và loop prevention. Native publication/subscription đơn hướng không tự tạo hệ thống multi-master an toàn.

### 14.4. Tách bảng local

Một subscriber có thể giữ bảng local không thuộc publication hoặc các bảng được thiết kế riêng cho ứng dụng subscriber. Phân tách ownership rõ ràng giúp tránh conflict.

## 15. Physical replication và logical replication trong HA

### 15.1. Physical standby là lựa chọn phổ biến cho HA

Standby nhận physical WAL, giữ cluster state tương ứng và có thể được promote. Đây là mô hình quen thuộc cho primary/standby.

### 15.2. Logical subscriber không phải hot standby

Subscriber không phải physical copy của cluster. Nó không tự có tất cả databases, roles, sequence states, extension state và DDL của publisher.

### 15.3. Failover physical

Khi primary lỗi, promote physical standby sau khi fencing và đánh giá replication lag. Sau đó dựng lại replicas theo primary mới.

### 15.4. Cutover logical

Logical replication thường dùng cho migration: đồng bộ dữ liệu sang cluster đích, kiểm tra lag, dừng writes hoặc tạo một điểm cutover, chờ apply hết changes, đồng bộ phần metadata còn thiếu rồi chuyển ứng dụng.

### 15.5. Không gọi logical cutover là promote standby

Logical cutover là chuyển ứng dụng sang database độc lập đã nhận dữ liệu. Nó có các bước schema, sequence, permissions, validation và routing khác physical promotion.

## 16. Logical replication cho major-version migration

Physical WAL không phải cơ chế chuyển trực tiếp data directory giữa hai PostgreSQL major versions khác nhau. Logical replication có thể hỗ trợ migration từ publisher cũ sang subscriber mới hơn nếu versions và features tương thích.

### 16.1. Luồng migration

~~~text
Old PostgreSQL cluster
  Publisher / publication
          |
          | Initial copy + logical changes
          v
New PostgreSQL cluster
  Subscriber
          |
          v
Validate schema and data
          |
          v
Catch up to cutover point
          |
          v
Switch application writes
~~~

### 16.2. Chuẩn bị schema

Deploy schema tương thích lên subscriber trước khi replicate. Đảm bảo types, columns, constraints và indexes phù hợp với data đang truyền.

### 16.3. Initial copy

Subscription có thể copy table data ban đầu. Với database lớn, cần tính thời gian copy, network, disk I/O, locks và khả năng publisher tiếp tục phục vụ writes.

### 16.4. Theo dõi catch-up

Theo dõi slot LSN, subscription progress và apply rate. Không cutover khi subscriber còn lag hoặc có apply errors.

### 16.5. DDL trong migration

Áp dụng DDL trên cả hai phía theo một trình tự đã thử nghiệm. Tránh thay đổi column/table shape ở publisher trước khi subscriber tương thích.

### 16.6. Sequence và metadata

Trước khi chuyển writes, đồng bộ sequence values, roles, grants, extensions, functions, triggers, indexes và objects ngoài publication.

### 16.7. Cutover

Dừng writes trên publisher hoặc đưa ứng dụng vào maintenance/read-only mode, chờ subscriber apply hết changes, kiểm tra counts/aggregates, đồng bộ sequence/metadata cuối cùng và chuyển connection endpoint.

### 16.8. Rollback plan

Sau khi subscriber bắt đầu nhận writes mới, việc quay lại publisher cũ không còn đơn giản. Phải xác định data flow ngược hoặc giữ publisher cũ read-only và có cách reconcile changes phát sinh sau cutover.

## 17. Logical replication cho CDC và data integration

Logical decoding có thể cấp row changes cho subscriber hoặc các consumer khác qua output plugin/replication protocol.

Use cases:

- Đồng bộ một số bảng sang analytics database.
- Đưa changes vào Kafka hoặc event pipeline qua connector.
- Đồng bộ dữ liệu sang search/indexing system.
- Tạo read model cho một workload khác.
- Data integration giữa các dịch vụ.
- Audit/change processing ở downstream.

### 17.1. CDC không phải event sourcing

WAL-derived row changes phản ánh database mutations. Chúng không tự giải thích ý định nghiệp vụ như “khách hàng chấp thuận hợp đồng” nếu schema không lưu business event đó.

### 17.2. Ordering và transactions

Logical replication giữ semantics transaction ở mức protocol/apply phù hợp. Consumer bên ngoài phải hiểu commit boundaries, ordering, duplicate/retry và checkpoint behavior của connector.

### 17.3. Idempotency

Downstream có thể retry hoặc xử lý lại events. Dùng event identity, source LSN/transaction metadata và idempotent writes để tránh duplicate effects.

### 17.4. Schema changes

CDC consumers phải xử lý schema evolution. Nếu downstream schema registry hoặc topic format không tương thích, pipeline có thể dừng dù PostgreSQL publisher vẫn hoạt động.

## 18. So sánh hiệu năng và tài nguyên

Không có tỷ lệ overhead cố định cho mọi workload. Tác động phụ thuộc write volume, row width, index, replica identity, network, subscriber apply rate và retention.

| Tài nguyên | Physical replication | Logical replication |
| --- | --- | --- |
| Primary CPU | WAL generation, sender/network | WAL generation, decoding, filtering/encoding |
| Network | WAL stream | Logical changes; có thể ít hơn hoặc nhiều hơn tùy data/schema |
| Primary disk | WAL và slot retention | WAL/slot retention, có thể thêm catalog retention |
| Standby/subscriber CPU | WAL write/replay | Apply row changes, maintain indexes/constraints |
| Storage | Cluster physical copy | Theo schema/data được subscribe và indexes local |
| Apply behavior | Replay physical WAL | Execute logical changes |
| Lag bottleneck | Network, write, flush, replay | Decode, network, apply, locks/indexes |
| Scaling | Có thể thêm physical read replicas | Chọn nhiều subscribers/projections theo workload |

### 18.1. Physical replay

Physical replay thường hiệu quả cho việc duy trì một bản sao vật lý vì nó không phải chuyển từng row thành SQL statement ở subscriber. Tuy nhiên, replay vẫn chịu ảnh hưởng storage I/O, WAL rate, network và recovery conflicts.

### 18.2. Logical apply

Logical apply thực hiện changes trên subscriber, duy trì indexes/constraints và có thể tốn CPU/I/O đáng kể. Subscriber có workload local hoặc index nặng có thể apply chậm hơn publisher tạo changes.

### 18.3. Row width và replica identity

REPLICA IDENTITY FULL có thể làm logical changes lớn hơn. Bảng nhiều cột/toàn row và workload UPDATE thường xuyên cần được benchmark.

### 18.4. Initial sync

Initial table copy có thể tạo tải lớn trên publisher/subscriber. Lập lịch, giới hạn workers và đo disk/network trước migration.

## 19. Replication lag: hai cơ chế, hai cách nhìn

### 19.1. Physical lag

Trên primary:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Các LSN thể hiện các mốc gửi, ghi, flush và replay. Có thể tính khoảng cách bytes:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS bytes_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS bytes_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication;
~~~

### 19.2. Standby receive/replay

Trên standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

Timestamp cuối có thể cũ khi primary ít writes; hãy kết hợp LSN delta và WAL activity.

### 19.3. Logical subscription progress

Trên subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

View cung cấp trạng thái worker và tiến độ nhận/apply theo phiên bản. Đọc schema thực tế bằng psql hoặc catalog docs trước khi xây dashboard phụ thuộc cột cụ thể.

### 19.4. Logical slot progress

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
ORDER BY slot_type, slot_name;
~~~

restart_lsn cho biết WAL sớm nhất slot còn cần; confirmed_flush_lsn thể hiện vị trí logical consumer đã xác nhận. Hai giá trị không nhất thiết bằng nhau.

### 19.5. Tính lag không chỉ bằng thời gian

Dùng byte/LSN gap, WAL generation rate, consumer apply rate và thời điểm cuối cùng có tiến triển. Một con số replay_lag có thể NULL hoặc gây hiểu nhầm khi workload ít ghi.

## 20. WAL retention và replication slots

Cả physical và logical slots có thể giữ WAL trên publisher.

### 20.1. Physical slot

Giữ WAL cần cho standby. Nếu standby offline, primary có thể giữ segment cho tới khi standby reconnect hoặc slot bị giới hạn/invalidated.

### 20.2. Logical slot

Giữ WAL cần cho logical decoding. Nếu CDC consumer dừng, slot có thể giữ WAL và catalog history, gây disk growth hoặc vacuum retention.

### 20.3. max_slot_wal_keep_size

Giới hạn lượng WAL được giữ do replication slots. Nếu vượt giới hạn, slot có thể mất khả năng tiếp tục từ vị trí cũ khi WAL cần thiết bị loại bỏ. Đây là trade-off giữa bảo vệ disk và khả năng resume.

### 20.4. wal_keep_size

Giữ một lượng WAL tối thiểu trong pg_wal để hỗ trợ standby. Đây không phải giới hạn tổng WAL hoặc thời gian giữ cố định.

### 20.5. max_wal_size

Là mục tiêu mềm liên quan checkpoint, không phải hard cap của pg_wal. Slots và archive backlog vẫn có thể làm WAL directory lớn hơn.

### 20.6. Monitoring slot

Theo dõi active, restart_lsn, confirmed_flush_lsn, retained WAL estimate, safe_wal_size và owner. Không drop slot chỉ vì inactive mà chưa xác minh consumer.

## 21. Conflicts và lỗi apply

### 21.1. Physical recovery conflicts

Hot standby phục vụ read queries trong lúc replay WAL. Một query dài có thể xung đột với cleanup/replay trên standby. PostgreSQL có thể delay replay hoặc cancel query theo cấu hình recovery conflict.

Các setting như max_standby_streaming_delay và hot_standby_feedback ảnh hưởng trade-off giữa query availability và replay/vacuum behavior.

### 21.2. Logical apply conflicts

Logical apply có thể gặp unique violation, missing target row, incompatible schema, permission error hoặc constraint failure. Apply worker có thể dừng apply cho tới khi xử lý lỗi.

### 21.3. Không sửa dữ liệu subscriber tùy tiện

Nếu subscriber có local writes vào bảng replicated, conflict có thể lặp lại. Xác định ownership và source of truth trước khi sửa.

### 21.4. Skip transaction không phải giải pháp mặc định

Một số workflow có thể bỏ qua transaction lỗi, nhưng điều đó làm subscriber diverge. Chỉ làm khi hiểu chính xác transaction, chấp nhận hậu quả và có quy trình resync/validation.

### 21.5. Resync table

Nếu subscriber table bị diverge hoặc initial sync lỗi, có thể cần copy lại table theo quy trình subscription/table synchronization hoặc rebuild subscriber data. Không tự xóa slot trước khi biết trạng thái publisher/subscriber.

## 22. Logical replication và schema evolution

Vì DDL không tự replicate, schema rollout cần coordination.

### 22.1. Additive change

Một quy trình thường an toàn hơn:

1. Thêm column tương thích trên subscriber.
2. Thêm column trên publisher.
3. Cập nhật publication/column list nếu cần.
4. Deploy application tương thích với cả hai schema.
5. Backfill nếu cần.
6. Theo dõi apply.
7. Loại bỏ column cũ sau khi tất cả consumers không còn cần.

### 22.2. Rename column

Rename không tự được logical replication truyền như DDL. Phải triển khai thay đổi tương thích ở cả hai phía và kiểm tra mapping/column lists.

### 22.3. Drop column

Không drop publisher column khi subscriber/consumer còn cần nó. Thực hiện deprecation và remove theo rollout stages.

### 22.4. Type change

Kiểm tra khả năng chuyển đổi type và subscriber column. Một type change có thể khiến apply worker lỗi hoặc tạo semantics khác.

### 22.5. DDL deployment order

Đối với thay đổi cần thiết cho apply, chuẩn bị subscriber schema trước khi publisher bắt đầu gửi row shape mới. Lập migration có rollback/reconciliation plan.

## 23. Sequence và cutover logical

Sequence state không được native logical replication đồng bộ như table rows.

### 23.1. Vì sao quan trọng?

Giả sử publisher đã tạo order_id tới 500000, subscriber initial copy có dữ liệu tới 499000 nhưng sequence của subscriber vẫn ở giá trị thấp. Sau cutover, insert mới có thể đụng primary key đã tồn tại.

### 23.2. Đồng bộ sequence

Trước cutover, dừng writes hoặc chốt một điểm nhất quán, lấy sequence values từ publisher và set sequence trên subscriber lớn hơn mọi ID đã dùng.

Ví dụ kiểm tra:

~~~sql
SELECT last_value, is_called
FROM sales.orders_order_id_seq;
~~~

Ví dụ điều chỉnh phải dựa vào sequence thật, cột ID, cache và concurrency. Không áp dụng một câu setval chung mà không xác định giá trị an toàn.

### 23.3. Identity columns

Identity columns cũng dựa vào sequence semantics. Kiểm tra underlying sequence và ownership.

### 23.4. Các nguồn ID khác

Nếu ứng dụng dùng UUID hoặc external ID generator, kiểm tra generator/clock/worker coordination và unique constraints trước khi chuyển writes.

## 24. Bảo mật replication

### 24.1. Replication role

Cấp quyền tối thiểu cho replication connection. Không dùng superuser cho mọi subscriber/standby nếu không cần.

### 24.2. Network

Giới hạn pg_hba.conf theo IP/subnet và role. Chỉ expose replication port trên network cần thiết; dùng TLS và network segmentation phù hợp.

### 24.3. Physical data access

Physical standby chứa bản sao của toàn cluster, vì vậy quyền truy cập host/volume/backup của standby có thể tương đương quyền truy cập dữ liệu rất rộng.

### 24.4. Logical data scope

Publication có thể giới hạn bảng/rows/columns theo feature/version. Tuy vậy, logical replication vẫn là kênh xuất dữ liệu; bảo vệ credentials, subscription connections, slot ownership và subscriber storage.

### 24.5. Credentials

Không hard-code password trong Git, command history hoặc logs. Dùng .pgpass với permission phù hợp, secret manager hoặc cơ chế credentials của môi trường.

### 24.6. Subscriber permissions

Kiểm soát ai được đọc/ghi trên subscriber. Không giả định publication filtering là lớp authorization duy nhất.

## 25. Khi nào chọn physical replication?

Chọn physical replication khi:

- Cần standby có thể thay thế primary.
- Cần HA/failover cho toàn cluster.
- Cần read-only hot standby.
- Cần replica vật lý gần như giống primary.
- Cần cascading physical replicas.
- Cần DR với WAL shipping/streaming.
- Cần một bản clone vật lý cho mục đích vận hành phù hợp.

Physical replication thường là lựa chọn chính cho PostgreSQL HA truyền thống.

### 25.1. Không phù hợp khi cần chọn một vài bảng

Physical standby mang toàn cluster. Nếu chỉ muốn chia sẻ bảng customers và orders sang một analytics database, logical replication phù hợp hơn.

### 25.2. Major-version migration

Physical WAL không phải cơ chế trực tiếp để replicate giữa hai major versions khác nhau. Dùng logical replication hoặc công cụ upgrade/migration phù hợp.

## 26. Khi nào chọn logical replication?

Chọn logical replication khi:

- Chỉ cần một tập bảng hoặc dữ liệu được chọn.
- Cần CDC sang hệ thống khác.
- Cần migrate sang cluster độc lập hoặc major version mới hơn.
- Subscriber cần schema/storage riêng.
- Cần data distribution theo tenant/table/row filter ở phiên bản hỗ trợ.
- Cần tạo read model hoặc downstream database.

### 26.1. Không dùng thay physical HA nếu cần failover toàn cluster

Logical subscriber không tự chứa toàn bộ cluster metadata và objects. Nếu dùng làm target failover, phải xây dựng đầy đủ schema, roles, sequences, extensions, DDL, permissions và cutover/reconciliation process.

### 26.2. Không dùng khi schema drift không được quản lý

Nếu hai phía thay đổi DDL độc lập, apply errors và divergence rất dễ xảy ra. Cần schema migration discipline.

## 27. Có thể kết hợp physical và logical không?

Có. Một primary có thể phục vụ physical standbys để HA và logical slots/publications để CDC hoặc selective replication.

~~~text
                    +--> Physical standby A
                    |
Primary PostgreSQL -+--> Physical standby B
                    |
                    +--> Logical subscriber / analytics
                    |
                    +--> CDC connector / event pipeline
~~~

Khi kết hợp:

- Publisher cần wal_level=logical vì đây là mức cần cho logical decoding.
- Tính đủ max_wal_senders và max_replication_slots cho cả hai loại consumer.
- Theo dõi từng slot và consumer lag.
- Dự trù WAL disk cho standby/CDC outage.
- Archive WAL cho PITR độc lập.
- Xác định failover behavior cho logical consumers và slot synchronization theo version/tooling.
- Không để CDC outage làm đầy disk primary.

## 28. Version compatibility

### 28.1. Physical replication

Physical replication yêu cầu tương thích physical WAL/data format, thông thường cùng PostgreSQL major version. Minor versions trong cùng major series được thiết kế cho compatibility, nhưng phải theo upgrade guidance.

Không sao chép trực tiếp WAL/data directory giữa hai major versions khác nhau và kỳ vọng standby hoạt động như physical replica.

### 28.2. Logical replication

Logical replication có thể kết nối publisher/subscriber ở các major versions khác nhau theo các giới hạn được PostgreSQL hỗ trợ. Một hướng migration phổ biến là publisher ở major version cũ và subscriber ở major version mới hơn.

Kiểm tra:

- Publisher/subscriber version pair.
- Logical protocol/output plugin compatibility.
- Publication features như row filters/column lists.
- Data type compatibility.
- DDL/schema differences.
- Extension behavior.
- Slot/failover capabilities của phiên bản.

### 28.3. Không giả định mọi tính năng cùng tồn tại

Các features logical replication được bổ sung theo major versions. Dùng tài liệu của cả publisher và subscriber versions, và test trên cùng version pair dự kiến.

## 29. Monitoring physical replication

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
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

Theo dõi:

- Connection state và sender count.
- WAL sent/write/flush/replay LSN.
- Byte lag và time lag.
- Last receive/last replay.
- Replication slot activity và retained WAL.
- Filesystem free space.
- Recovery conflicts/cancelled queries.

## 30. Monitoring logical replication

Trên subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

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

Theo dõi:

- Subscription enabled/disabled.
- Apply worker state.
- Last received/applied progress theo version.
- Slot active/inactive.
- restart_lsn và confirmed_flush_lsn.
- WAL retained estimate.
- Apply errors và conflicts.
- Table synchronization progress.
- Consumer/downstream checkpoint nếu dùng CDC.

### 30.1. Retained WAL estimate

Ví dụ ước lượng khoảng cách LSN:

~~~sql
SELECT
    slot_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

Đây là ước lượng khoảng cách WAL, không phải dung lượng độc quyền của một slot; nhiều consumers có thể cần chung các segments.

### 30.2. Slot inactive

active=false không có nghĩa slot không giữ WAL. Xác định owner và consumer trước khi drop.

### 30.3. Apply lag

Logical subscriber có thể nhận WAL nhưng apply chậm. Theo dõi apply progress và error logs, không chỉ network connection.

## 31. Troubleshooting physical replication

### 31.1. Standby không kết nối

Kiểm tra primary_conninfo, network/DNS/firewall, pg_hba.conf, replication role/password, TLS certificates, max_wal_senders và PostgreSQL logs trên cả hai node.

### 31.2. Requested WAL segment đã bị recycle

Standby cần WAL không còn trong pg_wal. Kiểm tra physical slot, wal_keep_size và archive. Nếu archive có segment, cấu hình restore path. Nếu không còn WAL cần thiết, có thể phải dựng lại standby từ base backup.

### 31.3. Replay lag tăng

Kiểm tra storage I/O, network throughput, WAL generation burst, long-running queries/conflicts và standby CPU.

### 31.4. Primary disk tăng

Kiểm tra inactive slots, archive failures và standby lag. Không xóa files trong pg_wal thủ công.

### 31.5. Promote không an toàn

Xác minh primary cũ đã bị fencing và xác định RPO trước promote. Tránh split brain.

## 32. Troubleshooting logical replication

### 32.1. Subscription không kết nối

Kiểm tra connection string, pg_hba, role, password, network, publisher database và publication name.

### 32.2. Apply worker lỗi schema

So sánh table definitions, column names/types, replica identity và DDL rollout order.

### 32.3. Unique violation

Tìm local writes hoặc dữ liệu initial copy trùng với publisher. Xác định source of truth và xử lý conflict có kiểm soát.

### 32.4. UPDATE/DELETE không apply

Kiểm tra replica identity, row có tồn tại trên subscriber và subscriber có diverge hay không.

### 32.5. Slot giữ WAL quá nhiều

Kiểm tra active state, restart_lsn, confirmed_flush_lsn, consumer logs và max_slot_wal_keep_size. Khôi phục consumer hoặc lập kế hoạch resnapshot nếu slot mất WAL.

### 32.6. Subscriber không theo kịp

Kiểm tra apply CPU, indexes, constraints, locks, network, initial sync và số workers. Benchmark trước khi tăng workers vì nhiều workers có thể tăng contention.

## 33. Thiết kế migration bằng logical replication

Một migration có kiểm soát thường gồm các giai đoạn:

### Giai đoạn 1: Discovery

Inventory databases/tables, sizes, write rates, DDL, extensions, large objects, sequences, roles, grants, jobs và external dependencies.

### Giai đoạn 2: Compatibility

Kiểm tra publisher/subscriber versions, data types, collation, extensions, schema và publication features.

### Giai đoạn 3: Provision subscriber

Tạo cluster/database đích, cấu hình network/security, schema, indexes, constraints và roles.

### Giai đoạn 4: Start replication

Tạo publication/subscription, chọn copy_data, xác nhận initial table sync và theo dõi WAL slots.

### Giai đoạn 5: Validate

So sánh row counts, key sets, aggregates, constraints, application read paths và apply lag.

### Giai đoạn 6: Cutover

Dừng writes hoặc kiểm soát write window, chờ subscriber bắt kịp, đồng bộ sequences/metadata, chuyển application endpoint và xác minh.

### Giai đoạn 7: Stabilize

Theo dõi lỗi/latency, giữ publisher cũ read-only theo rollback window và ghi rõ điều kiện kết thúc rollback window.

## 34. Thiết kế HA bằng physical replication

Một kiến trúc HA điển hình:

~~~text
Application
     |
     v
Connection proxy / service endpoint
     |
     v
Primary PostgreSQL
     |
     +---- Physical standby A
     |
     +---- Physical standby B
     |
     +---- WAL archive / backup repository
~~~

Cần thiết kế sync/async policy và RPO, fencing và leader election, promotion/rejoin procedure, replication slots và WAL capacity, archive/PITR độc lập, monitoring và alert, restore/failover drills, network/storage failure domains.

## 35. Backup không thể bị thay thế bởi replication

Physical standby có thể nhận một DELETE nhầm. Logical subscriber cũng có thể nhận DELETE nếu publication cho phép. Replication duy trì changes, không tự tạo lịch sử bất biến.

Một backup strategy cần:

- Base backups định kỳ.
- WAL archive liên tục nếu cần PITR.
- Bản sao backup ở failure domain khác.
- Retention policy phù hợp.
- Encryption và access controls.
- Verification và restore drills.

## 36. Những quyết định thiết kế cần ghi lại

| Quyết định | Câu hỏi |
| --- | --- |
| Replication type | Cần bản sao cluster hay dữ liệu chọn lọc? |
| Data scope | Toàn cluster, database, table hay row? |
| Version | Có cần khác major version không? |
| Initial copy | Base backup hay logical table sync? |
| DDL | Ai triển khai schema changes và theo thứ tự nào? |
| Sequence | Đồng bộ sequence khi cutover ra sao? |
| Writes | Primary duy nhất hay subscriber cũng ghi? |
| Conflicts | Xử lý unique/missing-row conflicts thế nào? |
| Retention | Slot/WAL outage budget là bao lâu? |
| HA/DR | Failover/fencing và recovery target thế nào? |
| Security | Ai được đọc replication stream và subscriber data? |
| Monitoring | Theo dõi LSN, apply lag, slots và disk thế nào? |

## 37. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng logical subscriber như physical standby | Thiếu cluster metadata/objects và failover semantics | Dùng physical replication cho HA hoặc xây migration plan đầy đủ |
| Nghĩ physical replication chọn được vài bảng | Sao chép toàn cluster | Dùng logical publication |
| Nghĩ logical replication tự copy DDL | Subscriber schema drift/apply failure | Quản lý schema migrations riêng |
| Quên sequence state khi cutover | ID collision | Đồng bộ sequence trước khi bật writes |
| Không cấu hình replica identity | UPDATE/DELETE không apply | Primary key hoặc identity phù hợp |
| Dùng REPLICA IDENTITY FULL tùy tiện | WAL/network/apply overhead | Dùng key/index phù hợp khi có thể |
| Để subscriber và publisher cùng ghi không có ownership | Conflicts/divergence | Single-writer hoặc conflict strategy rõ |
| Không giám sát logical slot | WAL giữ lâu, disk đầy | Theo dõi restart_lsn/active/retention |
| Nghĩ wal_keep_size là hard cap | pg_wal vẫn có thể lớn | Theo dõi slots/archive/disk |
| Nghĩ replication thay backup | Xóa nhầm được replicate | Base backup + WAL archive/PITR |
| Promote standby khi primary chưa fenced | Split brain | Fencing và quorum |
| Dùng physical WAL giữa major versions | Không tương thích | Upgrade tool hoặc logical migration |
| Bỏ qua DDL ordering | Apply worker lỗi | Schema rollout có coordination |
| Bật copy_data=false khi subscriber chưa có data | Subscriber thiếu rows ban đầu | Preload nhất quán hoặc initial copy |
| Tăng apply workers không đo | Contention và I/O tăng | Benchmark theo workload |
| Drop inactive slot không xác minh owner | Consumer mất khả năng resume | Inventory và lifecycle |
| Dùng publication ALL TABLES thiếu kiểm soát | Phơi dữ liệu ngoài dự kiến | Scope publication theo policy |
| Không test failover/cutover | RTO/RPO không như mong đợi | Diễn tập định kỳ |

## 38. Bài tập thực hành PostgreSQL

Thực hiện trên hai PostgreSQL clusters trong lab. Không thay đổi replication hoặc failover trên production khi chưa có kế hoạch vận hành.

1. **Khái niệm:** giải thích physical replication ở mức WAL.
2. **Khái niệm:** giải thích logical replication ở mức row changes.
3. **Sơ đồ:** vẽ primary, WAL sender, receiver và physical standby.
4. **Sơ đồ:** vẽ publisher, publication, logical slot và subscriber.
5. **Scope:** chứng minh physical replication mang toàn cluster.
6. **Scope:** tạo publication chỉ gồm hai bảng.
7. **wal_level:** đọc giá trị wal_level hiện tại.
8. **Configuration:** giải thích vì sao logical cần wal_level=logical.
9. **Restart:** xác định setting nào cần restart.
10. **Role:** tạo replication role trên lab.
11. **pg_hba:** giới hạn replication connection theo subnet.
12. **Physical slot:** tạo physical replication slot.
13. **Base backup:** tạo standby bằng pg_basebackup.
14. **Standby signal:** kiểm tra cấu hình recovery/standby do -R tạo.
15. **Physical status:** đọc pg_stat_replication.
16. **Receiver:** đọc pg_stat_wal_receiver trên standby.
17. **Replay:** so sánh receive LSN và replay LSN.
18. **Hot standby:** chạy SELECT trên standby và kiểm tra pg_is_in_recovery().
19. **Read-only:** thử một write trên standby và quan sát behavior.
20. **Promote:** thực hành promote một standby lab.
21. **Fencing:** vẽ quy trình đảm bảo primary cũ không ghi sau failover.
22. **Async:** mô tả rủi ro data loss khi asynchronous standby lag.
23. **Sync:** cấu hình synchronous_standby_names trong lab.
24. **Commit:** so sánh synchronous_commit modes theo documentation của version.
25. **Cascading:** tạo sơ đồ primary → standby A → standby B.
26. **Archive:** cấu hình WAL archive cho physical recovery.
27. **Slot lag:** làm standby offline và quan sát retained WAL.
28. **wal_keep_size:** giải thích vì sao đây không phải time limit.
29. **max_slot_wal_keep_size:** đặt cap trong lab và giải thích invalidation risk.
30. **Logical prerequisites:** kiểm tra max_wal_senders/max_replication_slots.
31. **Publication:** tạo publication cho bảng orders.
32. **Subscription:** tạo subscriber và subscription.
33. **Initial copy:** bật copy_data và quan sát table synchronization.
34. **Preload:** thử copy_data=false sau khi nạp data nhất quán.
35. **INSERT:** insert row trên publisher và xác nhận subscriber.
36. **UPDATE:** update row và quan sát logical apply.
37. **DELETE:** delete row và xác nhận behavior.
38. **TRUNCATE:** thử publication có/không publish truncate theo version.
39. **Replica identity:** kiểm tra bảng có primary key.
40. **Identity index:** chọn unique index làm replica identity trong lab.
41. **FULL:** bật REPLICA IDENTITY FULL và quan sát thay đổi WAL/traffic.
42. **NOTHING:** giải thích giới hạn khi UPDATE/DELETE.
43. **Row filter:** tạo publication row filter nếu version hỗ trợ.
44. **Column list:** thử column list và kiểm tra version compatibility.
45. **DDL:** thêm column ở một phía và quan sát vì sao DDL không tự replicate.
46. **Schema rollout:** triển khai DDL tương thích trên cả publisher/subscriber.
47. **Sequence:** so sánh sequence values hai phía.
48. **Sequence cutover:** đồng bộ sequence trước khi bật writes trên subscriber.
49. **Large objects:** lập kế hoạch chuyển large objects riêng.
50. **Roles:** tạo role/grants trên subscriber qua provisioning.
51. **Extension:** xác minh extension binaries trên subscriber.
52. **Local writes:** tạo conflict unique key trên subscriber rồi quan sát apply error.
53. **Conflict repair:** lập kế hoạch reconcile dữ liệu bị conflict.
54. **Loop prevention:** vẽ một topology hai chiều và chỉ ra nguy cơ loop.
55. **Physical vs logical:** so sánh read-only hot standby và writable subscriber.
56. **Major version:** giải thích vì sao physical WAL không phải major-upgrade transport.
57. **Migration:** lập kế hoạch logical migration từ version cũ sang version mới.
58. **Cutover:** dừng writes, chờ apply và chuyển endpoint trong lab.
59. **Rollback:** xác định vì sao quay lại publisher cũ sau khi subscriber nhận writes cần reconciliation.
60. **CDC:** thiết kế consumer dùng logical decoding để gửi changes xuống event pipeline.
61. **Ordering:** mô tả transaction boundaries và ordering mà CDC consumer phải giữ.
62. **Idempotency:** thiết kế downstream processing chống duplicate events.
63. **Monitoring:** truy vấn pg_stat_subscription.
64. **Slot monitoring:** đọc restart_lsn và confirmed_flush_lsn.
65. **Retention estimate:** ước lượng WAL bytes từ current LSN tới restart_lsn.
66. **Inactive slot:** tìm slot inactive và xác định owner.
67. **Disk growth:** mô phỏng logical consumer dừng và quan sát WAL retention.
68. **Physical lag:** tính sent/write/flush/replay LSN deltas.
69. **Logical lag:** so sánh publisher slot progress với subscriber apply progress.
70. **Apply worker:** tìm lỗi trong subscriber logs.
71. **Schema conflict:** tạo mismatch type ở lab và xử lý.
72. **Missing row:** mô phỏng UPDATE/DELETE không tìm thấy row tương ứng.
73. **Resync:** xây quy trình table resynchronization.
74. **Performance:** benchmark physical replay và logical apply trên cùng workload.
75. **Initial sync:** đo thời gian copy table lớn và network throughput.
76. **Security:** cấu hình TLS và least-privilege replication access.
77. **Publication scope:** audit bảng được publish trước khi triển khai.
78. **HA design:** thiết kế physical primary/standby có archive và backup.
79. **Combined design:** thêm logical CDC vào kiến trúc physical HA và tính sender/slot capacity.
80. **Thiết kế tổng hợp:** chọn physical/logical replication cho một hệ thống cần HA, major-version migration, selective data sharing, CDC, cutover, backup/PITR, monitoring và conflict management.

## 39. Checklist lựa chọn và triển khai

### Chọn cơ chế

- [ ] Xác định cần whole-cluster copy hay selected table changes.
- [ ] Xác định HA/failover hay selective data distribution.
- [ ] Xác định có cần khác PostgreSQL major version không.
- [ ] Xác định subscriber có được ghi local hay không.
- [ ] Xác định DDL, sequence, roles, extensions và large objects được chuyển bằng cách nào.

### Physical replication

- [ ] wal_level=replica hoặc logical.
- [ ] Base backup tương thích.
- [ ] max_wal_senders/max_replication_slots đủ.
- [ ] pg_hba/network/TLS/replication role đúng.
- [ ] Slot/archive/wal_keep_size có retention budget.
- [ ] Monitoring receive/write/flush/replay lag.
- [ ] Fencing, promote, rejoin và restore drills.

### Logical replication

- [ ] Publisher wal_level=logical.
- [ ] Publication scope được review.
- [ ] Subscriber schema được triển khai trước.
- [ ] Replica identity đáp ứng UPDATE/DELETE.
- [ ] Initial copy hoặc preload có consistency.
- [ ] DDL/sequence/roles/extensions được đồng bộ riêng.
- [ ] Subscription/slot/worker capacity đủ.
- [ ] Conflict, resync và cutover được diễn tập.

### Bảo vệ dữ liệu

- [ ] Base backups độc lập.
- [ ] WAL archive liên tục cho PITR.
- [ ] Retention và disk alerts.
- [ ] Replication credentials được bảo vệ.
- [ ] Subscriber access được giới hạn.
- [ ] Restore/failover/migration tests định kỳ.

## 40. Tổng kết

Physical replication và logical replication đều truyền thay đổi từ PostgreSQL publisher/primary sang một server khác, nhưng chúng khác nhau về mức dữ liệu, phạm vi và mục tiêu:

~~~text
PHYSICAL
Primary
  -> WAL records
  -> Physical standby
  -> Whole-cluster copy
  -> HA / failover / read-only standby

LOGICAL
Publisher
  -> WAL logical decoding
  -> Publication / slot
  -> Logical changes
  -> Subscriber tables
  -> Selective replication / CDC / migration
~~~

Những nguyên tắc quan trọng:

- **Physical replication sao chép cluster ở mức vật lý.** Nó phù hợp cho standby, HA, failover, cascading và read scaling.
- **Logical replication sao chép changes của các bảng được publish.** Nó phù hợp cho selective replication, CDC, data integration và nhiều kịch bản major-version migration.
- **Physical standby thường read-only trong recovery; logical subscriber là database độc lập.** Local writes trên subscriber có thể gây conflict với apply.
- **Logical replication không tự replicate DDL, sequence state, roles, grants hoặc large objects.** Phải có quy trình schema và metadata riêng.
- **Replica identity quyết định cách UPDATE/DELETE tìm row trên subscriber.** Primary key là lựa chọn mặc định tốt khi phù hợp.
- **Replication slots giữ WAL cho consumer nhưng có thể làm đầy disk.** Theo dõi restart_lsn, confirmed_flush_lsn, inactive slots và retained WAL.
- **HA không thay backup.** Cả physical lẫn logical replication đều có thể truyền một thay đổi sai; cần base backup và WAL archive để PITR.
- **Migration bằng logical replication cần schema compatibility, initial sync, sequence synchronization, cutover và rollback plan.**
- **Chọn cơ chế theo mục tiêu vận hành.** Nếu cần thay thế nguyên cluster, ưu tiên physical; nếu cần chia sẻ dữ liệu có chọn lọc hoặc CDC, cân nhắc logical; nhiều hệ thống cần kết hợp cả hai.

Một thiết kế PostgreSQL vững chắc thường xác định rõ source of truth, phạm vi dữ liệu, quyền ghi, cách xử lý schema, retention và recovery path cho từng consumer. Khi những quyết định này được kiểm thử cùng HA, backup và migration drills, replication mới đáp ứng đúng mục tiêu của hệ thống.
