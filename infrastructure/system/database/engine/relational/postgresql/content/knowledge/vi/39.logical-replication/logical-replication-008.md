# Xung đột dữ liệu, lỗi áp dụng và xử lý lệch dữ liệu trong PostgreSQL Logical Replication

## 1. Vì sao logical replication có thể bị dừng?

PostgreSQL logical replication truyền các thay đổi ở mức logical row operation từ publisher tới subscriber. Publisher ghi WAL; logical decoding đọc WAL và tạo change stream; replication connection gửi changes; apply worker trên subscriber áp dụng các transaction vào bảng đích.

Luồng này hoạt động tốt khi schema, replica identity, constraints và dữ liệu ở subscriber phù hợp với thay đổi từ publisher. Nhưng subscriber có thể đã chứa dữ liệu khác, được ghi cục bộ, hoặc có cấu trúc không tương thích. Khi apply worker cố áp dụng một transaction mà subscriber không chấp nhận, transaction đó có thể thất bại và replication không tiến qua được vị trí lỗi.

Các tình huống thường gặp:

- INSERT nhận được bị trùng primary key/unique key ở subscriber.
- UPDATE hoặc DELETE không tìm thấy row tương ứng.
- Row ở subscriber có giá trị khác do ghi cục bộ hoặc chỉnh sửa thủ công.
- Constraint ở subscriber từ chối dữ liệu được publisher gửi.
- Schema hai bên không tương thích.
- Replica identity không đủ để xác định row cần UPDATE/DELETE.
- Initial table synchronization gặp dữ liệu hoặc constraint conflict.
- Một transaction lỗi được retry nhưng vẫn thất bại vì nguyên nhân chưa được sửa.

```text
PUBLISHER
   |
   | WAL / logical decoding
   v
Logical replication stream
   |
   v
SUBSCRIBER apply worker
   |
   +-- Transaction hợp lệ
   |       |
   |       v
   |    COMMIT / advance origin
   |
   +-- Conflict / SQL error
           |
           v
       Transaction abort
           |
           v
       Apply progress stops
           |
           v
       Diagnose -> repair / resync / controlled skip
```

**Logical replication không tự biến hai bộ dữ liệu khác nhau thành một bộ dữ liệu thống nhất.** Khi có conflict, cần tìm nguyên nhân, xác định dữ liệu đúng theo nghiệp vụ và chọn cách sửa có kiểm soát.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả publisher, logical decoding, replication stream và subscriber apply worker.
2. Phân biệt logical replication với physical streaming replication.
3. Nhận diện duplicate key, missing row và constraint conflicts.
4. Hiểu vai trò của replica identity trong UPDATE/DELETE.
5. Phân tích schema drift, publication filters và subscriber-side writes.
6. Phân biệt apply errors với initial table synchronization errors.
7. Đọc pg_stat_subscription, pg_stat_subscription_stats và replication origin status.
8. Tìm transaction/LSN gây lỗi trong PostgreSQL logs.
9. Chẩn đoán lỗi theo thứ tự từ schema, identity, constraints tới row contents.
10. Sửa subscriber data mà không làm mất transaction hợp lệ.
11. Hiểu rủi ro của việc skip transaction.
12. Thiết kế quy trình resync một bảng hoặc toàn subscription.
13. Ngăn xung đột bằng ownership, schema migration và write routing.
14. Xác minh dữ liệu sau khi apply worker chạy lại.
15. Xây runbook và monitoring để phát hiện data drift sớm.

---

## 2. Logical replication hoạt động thế nào?

Logical replication dùng publication trên publisher và subscription trên subscriber.

- **Publisher:** database phát các thay đổi.
- **Publication:** xác định bảng và loại thay đổi được phát.
- **Logical decoding:** chuyển WAL thành logical changes.
- **Replication slot:** giữ WAL cần thiết cho logical consumer.
- **Subscription:** cấu hình kết nối, publication và apply behavior ở subscriber.
- **Apply worker:** nhận và áp dụng changes.
- **Table synchronization worker:** thực hiện initial copy cho bảng mới được đồng bộ khi cần.

```text
Publisher table
      |
      v
WAL records
      |
      v
Logical decoding
      |
      v
Publication stream
      |
      v
Subscription connection
      |
      v
Apply worker
      |
      v
Subscriber table
```

### 2.1. Transaction boundary

Logical replication truyền thay đổi theo transaction. Apply worker áp dụng các changes thuộc transaction và commit trên subscriber theo cơ chế replication.

Nếu một transaction gặp constraint violation, transaction đó không thể được commit bình thường trên subscriber. Những transaction sau không thể được áp dụng vượt qua transaction lỗi theo thứ tự của stream.

### 2.2. Một subscription có nhiều worker

Ngoài apply worker chính, PostgreSQL có thể chạy table synchronization workers cho initial table copy. Vì vậy khi điều tra cần phân biệt lỗi ở apply worker với lỗi trong quá trình copy/synchronize từng relation.

### 2.3. Logical replication không phải multi-master tự động

Built-in logical replication chủ yếu truyền thay đổi một chiều từ publisher tới subscriber. Nếu ứng dụng ghi đồng thời trên cả hai bên hoặc có nhiều publisher ghi cùng dữ liệu, phải tự thiết kế conflict resolution/ownership. Không coi subscription là hệ thống multi-master tự động.

## 3. Logical replication khác physical replication

| Đặc điểm | Physical replication | Logical replication |
|---|---|---|
| Đơn vị truyền | WAL records ở mức vật lý | Logical row changes/transactions |
| Phạm vi | Toàn cluster theo cơ chế physical | Bảng/objects được publication chọn |
| Schema | Data files và catalogs đi cùng | Schema phải được quản lý riêng |
| Subscriber | Standby trong recovery | Database có thể hoạt động độc lập |
| Ghi trên replica | Standby thường read-only | Subscriber có thể nhận writes cục bộ, nhưng dễ gây conflict |
| Cross-version | Cần tương thích physical | Hữu ích cho một số migration/version upgrade |
| Conflict | Recovery/replication consistency issues | Unique, missing row, constraints, schema/data drift |
| PITR | Base backup + WAL | Cần backup riêng cho publisher/subscriber; logical stream không thay PITR |

### 3.1. Schema không tự được replicate

Logical replication không tự truyền CREATE TABLE, ALTER TABLE, CREATE INDEX hay mọi DDL khác. Phải triển khai schema change trên subscriber theo thứ tự tương thích.

### 3.2. Sequence không được đồng bộ như table rows

Các giá trị sequence/identity state không được logical replication tự đồng bộ theo cách đảm bảo subscriber luôn có next value phù hợp. Sau migration/failover hoặc khi subscriber được phép ghi, phải kiểm tra sequence state.

### 3.3. Objects ngoài phạm vi publication

Roles, grants, extensions, large objects và các object không thuộc logical table publication cần được quản lý bằng quy trình khác.

## 4. Conflict là gì?

Conflict xảy ra khi subscriber không thể áp dụng một logical change theo trạng thái dữ liệu/cấu trúc hiện tại.

Có thể chia thành các nhóm:

| Nhóm | Ví dụ | Dấu hiệu |
|---|---|---|
| Key conflict | INSERT trùng primary key | duplicate key value violates unique constraint |
| Missing row | UPDATE/DELETE không tìm thấy row | could not find row / affected row mismatch |
| Constraint conflict | CHECK/FK/NOT NULL/unique | violates constraint |
| Schema conflict | Thiếu cột/bảng hoặc kiểu không tương thích | column/relation/type error |
| Identity conflict | Không xác định được row để UPDATE/DELETE | replica identity/key error |
| Initial sync conflict | Copy dữ liệu vào table đích gặp trùng/constraint | table sync worker error |
| Operational conflict | Permission, trigger, DDL hoặc object state | permission denied / relation missing |

### 4.1. Conflict không nhất thiết chỉ do publisher

Subscriber có thể bị ghi cục bộ, operator có thể chỉnh row thủ công, migration có thể thay schema, hoặc một job khác có thể tạo key trước khi replication áp dụng.

### 4.2. Apply error có thể làm dừng toàn subscription

Một transaction lỗi thường khiến apply worker không thể tiến qua transaction đó. Worker launcher có thể thử khởi động lại, nhưng cùng một lỗi deterministic sẽ lặp lại nếu nguyên nhân không thay đổi.

### 4.3. Không được bỏ qua lỗi chỉ để lag giảm

Nếu apply worker chạy lại sau khi bỏ qua transaction mà dữ liệu thiếu vẫn còn, subscriber có thể lệch vĩnh viễn. Phải xác định dữ liệu bị ảnh hưởng và cách sửa trước khi tiếp tục.

## 5. Duplicate key khi INSERT

Ví dụ publisher phát:

```sql
INSERT INTO public.customers (customer_id, email)
VALUES (1001, 'a@example.com');
```

Nhưng subscriber đã có customer_id = 1001. Apply worker có thể gặp lỗi:

```text
ERROR: duplicate key value violates unique constraint
DETAIL: Key (customer_id)=(1001) already exists.
```

Nguyên nhân có thể:
- Subscriber từng được ghi cục bộ.
- Row được nhập thủ công hoặc từ một batch khác.
- Initial copy được chạy lại trên dữ liệu đích không sạch.
- Một subscription khác đã phát cùng row.
- Dữ liệu được restore từ một snapshot không cùng thời điểm.
- Publisher và subscriber dùng key generation không đồng bộ.

### 5.1. Xác định row ở hai phía

Publisher:

```sql
SELECT *
FROM public.customers
WHERE customer_id = 1001;
```

Subscriber:

```sql
SELECT *
FROM public.customers
WHERE customer_id = 1001;
```

So sánh mọi cột nghiệp vụ liên quan, không chỉ primary key.

### 5.2. Không tự động xóa row ở subscriber

Row có thể chứa dữ liệu mới hợp lệ do ứng dụng ghi cục bộ. Xác định owner và source of truth trước khi xóa hoặc ghi đè.

### 5.3. Nếu row subscriber là bản trùng có thể loại bỏ

Có thể lưu evidence, xác nhận không có foreign key/business dependency và thực hiện sửa có transaction/backup theo policy. Sau đó để apply worker retry transaction publisher.

### 5.4. Nếu row subscriber có dữ liệu cần giữ

Cần reconciliation: merge các trường, chuyển dữ liệu cục bộ sang bảng khác, hoặc thay đổi key/ownership theo thiết kế. Không giải quyết bằng skip một cách mặc định.

## 6. UPDATE không tìm thấy row

Publisher cập nhật:

```sql
UPDATE public.orders
SET status = 'SHIPPED'
WHERE order_id = 5001;
```

Nếu subscriber không có row order_id = 5001, apply có thể không tìm được tuple cần cập nhật.

Nguyên nhân:
- Row bị xóa cục bộ trên subscriber.
- Initial sync chưa hoàn tất hoặc bị bỏ qua.
- Row bị lọc bởi publication row filter.
- Publisher/subscriber không bắt đầu từ snapshot tương thích.
- Replica identity không khớp.
- Schema/partition routing khiến row nằm ở relation khác.
- Một lần skip trước đó đã bỏ qua INSERT tạo row.

### 6.1. Kiểm tra cả hai phía

Tìm row trên publisher và subscriber. Kiểm tra publication có bao gồm table/row đó không và subscriber relation có trạng thái ready không.

### 6.2. Kiểm tra replica identity

Nếu UPDATE/DELETE không thể xác định tuple trên subscriber bằng identity được gửi, apply có thể thất bại. Xem phần replica identity và table definition.

### 6.3. Phục hồi row bị thiếu

Nếu publisher là source of truth, có thể lấy row hiện tại từ publisher và đưa vào subscriber theo quy trình repair. Nhưng cần cân nhắc các transaction kế tiếp trong stream và tránh tạo duplicate.

## 7. DELETE không tìm thấy row

Publisher phát DELETE nhưng subscriber không có row tương ứng. Điều này có thể do:
- Row đã bị xóa cục bộ.
- Row chưa từng được initial sync.
- Transaction INSERT trước đó đã bị skip.
- Row filter/publication scope thay đổi.
- Subscriber data drift.

### 7.1. Xác nhận row có thực sự cần tồn tại

Nếu subscriber được thiết kế chỉ chứa một subset dữ liệu, row có thể không thuộc publication/filter hiện tại. Đừng coi mọi missing row là corruption trước khi xem publication semantics.

### 7.2. Kiểm tra lịch sử thao tác

Tìm audit log, application logs, migration scripts và manual SQL để biết row bị xóa khi nào.

### 7.3. Sửa theo source of truth

Nếu row đã bị xóa hợp lệ trên publisher, subscriber cần phản ánh trạng thái đó. Nếu row bị xóa nhầm trên subscriber, có thể cần restore/merge row trước khi tiếp tục.

## 8. Constraint conflicts

Subscriber có thể từ chối một row vì constraint không tương thích.

Các loại phổ biến:

- PRIMARY KEY / UNIQUE: key trùng.
- FOREIGN KEY: row tham chiếu chưa có hoặc bị xóa sai thứ tự.
- CHECK: giá trị không thỏa điều kiện.
- NOT NULL: publisher gửi NULL vào cột bắt buộc.
- Exclusion constraint: giá trị vi phạm exclusion rule.
- Trigger: logic trên subscriber thay đổi/khước từ row.

### 8.1. Subscriber có constraint chặt hơn publisher

Ví dụ publisher cho phép status = 'PENDING_REVIEW', nhưng subscriber CHECK chỉ cho phép 'NEW', 'PAID', 'SHIPPED'. Dữ liệu hợp lệ ở publisher vẫn thất bại khi apply.

### 8.2. Foreign key dependency

Nếu publication không bao gồm bảng cha nhưng subscriber có FK tới bảng cha, insert child có thể fail vì referenced row chưa tồn tại. Cần đồng bộ đầy đủ dependency hoặc thiết kế constraints phù hợp.

### 8.3. Trigger trên subscriber

Trigger có thể thực hiện side effects, sửa dữ liệu hoặc raise exception. Xác định trigger nào chạy trong apply context và có thực sự cần tồn tại trên subscriber.

### 8.4. Không bỏ constraint để “cho chạy”

Tạm bỏ constraint có thể làm dữ liệu sai lọt vào subscriber. Nếu cần thay đổi constraint, đánh giá invariant nghiệp vụ và đồng bộ schema trên cả hai phía.

## 9. Replica identity và UPDATE/DELETE

Logical replication cần xác định row nào bị thay đổi. Replica identity quyết định thông tin cũ được dùng để tìm tuple ở subscriber.

Mặc định, PostgreSQL thường dùng primary key làm replica identity nếu có.

Kiểm tra:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity,
    c.relhasindex
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
```

### 9.1. Các chế độ

- DEFAULT: dùng primary key nếu có.
- USING INDEX: dùng unique index phù hợp làm identity.
- FULL: dùng toàn bộ old row values làm identity.
- NOTHING: không lưu identity cho UPDATE/DELETE; thường chỉ phù hợp bảng chỉ INSERT trong publication.

Tên ký tự trong catalog có thể là d/f/i/n tương ứng các chế độ; xác minh theo version.

### 9.2. Bảng không có primary key

Nếu bảng có UPDATE/DELETE được publish mà không có replica identity phù hợp, logical replication có thể không xác định được row. Có thể tạo unique index hợp lệ hoặc cân nhắc REPLICA IDENTITY FULL.

### 9.3. REPLICA IDENTITY FULL

Ví dụ:

```sql
ALTER TABLE public.events
REPLICA IDENTITY FULL;
```

FULL có thể làm WAL/logical change payload lớn hơn và việc tìm row trên subscriber tốn kém hơn, đặc biệt với bảng rộng/lớn. Ưu tiên một unique index phù hợp khi thiết kế cho phép.

### 9.4. USING INDEX

Ví dụ:

```sql
ALTER TABLE public.devices
REPLICA IDENTITY USING INDEX devices_replica_key;
```

Index phải đáp ứng điều kiện PostgreSQL yêu cầu cho replica identity. Xác minh unique, non-partial, non-expression và tính phù hợp của columns trước khi dùng.

## 10. Schema drift là nguồn lỗi thường gặp

Logical replication không tự đồng bộ DDL. Nếu publisher và subscriber lệch schema, apply worker có thể gặp:
- Relation không tồn tại.
- Column không tồn tại.
- Data type không tương thích.
- Cột NOT NULL thiếu default ở subscriber.
- Constraint/index khác nhau.
- Partition/table mapping không đúng.
- Trigger/function khác nhau.

### 10.1. So sánh schema trước khi bật publication

Dùng migration tool hoặc schema diff có kiểm soát. So sánh table names, column names/types, nullability, defaults, identity, constraints và indexes liên quan.

### 10.2. Thứ tự triển khai schema change

Một quy trình phổ biến:
1. Thêm cấu trúc tương thích trên subscriber trước.
2. Triển khai publisher thay đổi theo kế hoạch.
3. Kiểm tra apply.
4. Backfill nếu cần.
5. Chuyển application usage.
6. Chỉ xóa cấu trúc cũ sau khi mọi consumer đã chuyển.

Chi tiết thứ tự phụ thuộc kiểu migration; không áp dụng một trình tự cứng cho mọi DDL.

### 10.3. Thêm cột

Nếu publisher bắt đầu gửi cột mới nhưng subscriber chưa có cột tương ứng, apply có thể lỗi. Chuẩn bị subscriber schema trước khi publisher phát thay đổi.

### 10.4. Xóa/đổi tên cột

Không giả định logical replication tự map column rename. Phải triển khai tương thích và kiểm tra column mapping theo behavior của version.

### 10.5. Kiểu dữ liệu

Các kiểu có thể cần cast/compatibility. Đừng chỉ so tên type; kiểm tra domain, enum labels, collation, typmod và semantics.

## 11. Publication scope, row filters và column lists

Một subscriber không nhất thiết nhận mọi row của publisher. Publication có thể giới hạn:
- Bảng.
- Loại thao tác: INSERT/UPDATE/DELETE/TRUNCATE.
- Row filter.
- Column list.

Kiểm tra bảng publication:

```sql
SELECT
    pubname,
    schemaname,
    tablename
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
```

### 11.1. Row filter

Nếu publication chỉ phát row thỏa điều kiện, subscriber không phải bản sao đầy đủ của table publisher. Khi điều kiện filter thay đổi, cần hiểu dữ liệu cũ/newly qualifying rows được đồng bộ ra sao theo version.

### 11.2. Column list

Nếu publication chỉ phát một số cột, subscriber schema và defaults phải phù hợp. Cột subscriber không được gửi có thể giữ default/giá trị cục bộ theo thiết kế, nhưng cần xác định rõ ownership.

### 11.3. Publish options

Các options như publish INSERT/UPDATE/DELETE/TRUNCATE quyết định loại changes được phát. Nếu một thao tác không được publish, subscriber có thể khác publisher theo chủ đích.

### 11.4. Không gọi mọi khác biệt là lỗi

Data drift có thể là expected subset do publication/filter. So sánh subscriber với đúng publication contract, không so toàn bộ publisher table một cách máy móc.

## 12. Ghi cục bộ trên subscriber

Đây là nguyên nhân nguy hiểm vì có thể tạo divergence mà không có một apply error ngay lập tức.

Ví dụ:
1. Publisher có customer_id = 1001.
2. Subscriber được ghi cục bộ customer_id = 1001.
3. Publisher phát INSERT cùng key hoặc UPDATE row.
4. Apply worker gặp conflict hoặc dữ liệu subscriber bị ghi đè/lệch theo thao tác tiếp theo.

### 12.1. Một chiều phải có ownership rõ

Nếu publisher là source of truth, application nên ghi vào publisher. Subscriber chủ yếu phục vụ read, analytics hoặc migration consumer.

### 12.2. Nếu subscriber cần ghi

Tách dữ liệu subscriber-local vào schema/table riêng không thuộc publication, hoặc thiết kế một cơ chế hợp nhất/ownership rõ ràng.

### 12.3. Không coi subscriber là read-only mặc định

Logical subscriber có thể nhận local writes. Hãy kiểm soát bằng role/permissions, application routing và operational policy.

### 12.4. Nhiều publisher

Nếu nhiều publisher phát thay đổi tới cùng subscriber table, phải xử lý key collisions, ordering, ownership và conflict resolution ở tầng kiến trúc. Built-in logical replication không tự giải quyết multi-master conflict.

## 13. Initial table synchronization

Khi tạo subscription với copy dữ liệu ban đầu, PostgreSQL có thể chạy table synchronization workers. Quá trình này copy snapshot rồi phối hợp WAL changes để đưa table tới trạng thái nhất quán.

Conflict có thể xuất hiện nếu:
- Subscriber table đã có dữ liệu cũ.
- Có local writes trong lúc copy.
- Constraint/schema không khớp.
- Một table sync worker thiếu quyền.
- Table bị thay đổi cấu trúc giữa quá trình sync.
- Publication membership thay đổi trong lúc copy.

### 13.1. Kiểm tra trạng thái relation synchronization

Catalog pg_subscription_rel chứa trạng thái đồng bộ từng relation:

```sql
SELECT
    s.subname,
    r.srrelid::regclass AS relation_name,
    r.srsubstate,
    r.srsublsn
FROM pg_subscription_rel AS r
JOIN pg_subscription AS s
  ON s.oid = r.srsubid
ORDER BY s.subname, relation_name;
```

Các mã trạng thái nội bộ có thể thay đổi theo version; tra tài liệu/catalog tương ứng trước khi tự động hóa.

### 13.2. Table sync worker và apply worker khác nhau

Một table có thể chưa ready dù main apply worker vẫn đang hoạt động. Theo dõi worker type và relation state.

### 13.3. copy_data

Khi tạo/refresh subscription, option copy_data quyết định có copy dữ liệu hiện có của các relation mới được thêm vào subscription theo workflow đó hay không. Không bật/tắt tùy tiện khi chưa hiểu relation state.

### 13.4. Không chạy initial copy trên table đích đã chứa dữ liệu tùy tiện

Nếu subscriber table đã có dữ liệu, initial copy có thể tạo duplicate/constraint conflicts. Chuẩn bị table rỗng hoặc có quy trình seed/snapshot được thiết kế trước.

## 14. Apply worker và trạng thái subscription

Trên subscriber, xem:

```sql
SELECT
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relation_name;
```

View và các columns có thể khác theo PostgreSQL major version; dùng query phù hợp với server.

### 14.1. pid

PID cho biết worker đang hoạt động tại thời điểm quan sát. Nếu NULL hoặc không có row như kỳ vọng, kiểm tra subscription enabled state và logs.

### 14.2. received_lsn

Vị trí WAL/logical stream gần nhất worker nhận được theo semantics của view. Nó không tự chứng minh transaction đã được apply/commit.

### 14.3. latest_end_lsn và latest_end_time

Các field này giúp quan sát tiến độ stream và thời điểm cuối được xử lý/thông báo. Đối chiếu với publisher và replication origin status để hiểu apply progress.

### 14.4. Worker type

Một số version có field phân biệt apply worker và table synchronization worker. Dùng để biết worker nào đang chạy; xác minh schema view trên server.

## 15. Thống kê lỗi subscription

Trên các PostgreSQL versions có pg_stat_subscription_stats:

```sql
SELECT
    subname,
    apply_error_count,
    sync_error_count,
    stats_reset
FROM pg_stat_subscription_stats
ORDER BY subname;
```

Các counters này giúp biết lỗi apply hoặc table synchronization đã xảy ra. Availability/columns phụ thuộc version.

### 15.1. Counter không thay log

Counter cho biết số lần lỗi, không mô tả đầy đủ transaction, constraint, row key hay root cause. Đọc PostgreSQL server logs.

### 15.2. Stats reset

Counters có thể reset. Ghi thời điểm reset và dùng delta thay vì so một số tuyệt đối không rõ thời gian tích lũy.

### 15.3. Counter tăng liên tục

Có thể worker đang retry một lỗi deterministic. Xác định transaction/LSN và sửa nguyên nhân thay vì chỉ restart subscription.

## 16. Replication origin status

Logical apply dùng replication origin để theo dõi tiến độ remote changes.

Có thể xem:

```sql
SELECT
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status
ORDER BY external_id;
```

### 16.1. remote_lsn

Vị trí remote WAL/logical stream đã được áp dụng/ghi nhận cho origin theo semantics của replication origin.

### 16.2. local_lsn

Vị trí local WAL tương ứng với tiến độ được ghi nhận trên subscriber.

### 16.3. Origin không phải data diff

Origin status cho biết progress, không chứng minh rows trên publisher và subscriber giống nhau. Một transaction bị skip hoặc subscriber-local write có thể tạo drift dù progress đã tiến.

### 16.4. Không advance origin tùy tiện

Các hàm quản trị replication origin có thể làm subscriber bỏ qua changes. Không gọi advance thủ công để “sửa lag” nếu chưa có kế hoạch reconciliation và xác minh đầy đủ.

## 17. Đọc PostgreSQL logs để tìm transaction lỗi

Khi apply thất bại, logs thường là nguồn quan trọng nhất để xác định:
- Subscription name.
- Apply worker PID.
- SQLSTATE/error message.
- Constraint/table/column.
- Key value nếu server ghi ra.
- Transaction/remote LSN context.
- Thời điểm lỗi và số lần retry.

### 17.1. Bắt đầu từ lỗi đầu tiên

Các lỗi lặp lại sau đó có thể chỉ là worker retry. Tìm log đầu tiên sau khi subscription mất tiến độ.

### 17.2. Ghi lại transaction finish LSN nếu có

Một số lỗi/log context cung cấp LSN của transaction remote. Lưu giá trị này trước khi restart/skip để có thể đối chiếu chính xác.

### 17.3. Không bật log quá rộng lâu dài

Logging mọi statement/parameter có thể tạo volume lớn và lộ dữ liệu nhạy cảm. Chỉ tăng logging có mục tiêu, trong khoảng thời gian kiểm soát.

### 17.4. SQLSTATE và constraint name

SQLSTATE giúp phân loại lỗi; constraint name/table/key giúp tìm row cần điều tra. Giữ nguyên thông tin gốc trong incident record.

## 18. Quy trình chẩn đoán tổng quát

Khi subscriber ngừng apply:

1. Xác định subscription và publisher/subscriber pair.
2. Kiểm tra subscription có enabled không.
3. Kiểm tra apply worker/table sync workers.
4. Đọc log lỗi đầu tiên và xác định SQLSTATE.
5. Ghi transaction/remote LSN nếu có.
6. Xác định relation và operation INSERT/UPDATE/DELETE.
7. So sánh schema, replica identity, publication scope và constraints.
8. So sánh row trên publisher và subscriber.
9. Kiểm tra subscriber-local writes/triggers/jobs.
10. Chọn sửa row/schema, resync table hoặc controlled skip.
11. Restart/enable apply theo runbook.
12. Theo dõi LSN/origin progress và xác minh dữ liệu sau khi apply tiếp tục.

### 18.1. Giữ evidence trước khi sửa

Lưu logs, row snapshots, schema definitions, LSN, subscription state và thời điểm. Không sửa dữ liệu trước khi chụp evidence cần cho điều tra.

### 18.2. Không chỉ nhìn lag

Lag tăng là triệu chứng. Tìm transaction đầu tiên không được apply và lý do transaction thất bại.

### 18.3. Phân biệt lỗi tạm thời và lỗi deterministic

Network disconnect/temporary storage issue có thể tự hồi phục. Duplicate key, missing row hoặc schema mismatch thường cần sửa dữ liệu/cấu trúc trước khi retry có ích.

## 19. Sửa duplicate key có kiểm soát

Giả sử log cho biết INSERT key 1001 bị duplicate.

Quy trình:

1. Đọc row 1001 trên publisher và subscriber.
2. Xác định subscriber row được tạo bởi application, import hay replication.
3. Kiểm tra foreign keys và references.
4. Xác định source of truth.
5. Sao lưu/export row và audit evidence.
6. Chọn hành động: giữ row, merge, chuyển key hoặc xóa bản trùng.
7. Thực hiện trong transaction phù hợp.
8. Xác minh unique constraints.
9. Cho apply worker tiếp tục.
10. Xác minh transaction sau lỗi và dữ liệu liên quan.

Ví dụ xóa row subscriber chỉ khi đã xác nhận nó là bản seed/trùng có thể loại bỏ:

```sql
BEGIN;

SELECT *
FROM public.customers
WHERE customer_id = 1001
FOR UPDATE;

-- Chỉ thực hiện DELETE sau khi đã xác nhận ownership
-- và đã lưu evidence/backup cần thiết.

COMMIT;
```

Không chạy ví dụ DELETE tự động trong production. Phần sửa phụ thuộc dữ liệu thực và business ownership.

## 20. Sửa missing row có kiểm soát

Nếu publisher có row nhưng subscriber thiếu:

1. Xác định row bị thiếu do filter hay data corruption.
2. Xác định transaction tạo row gốc có bị skip không.
3. Kiểm tra publication có publish INSERT cho table không.
4. Kiểm tra subscriber relation state.
5. Kiểm tra identity và schema.
6. Lấy snapshot/row đúng từ publisher.
7. Đảm bảo các dependent rows/constraints có thứ tự phù hợp.
8. Chèn/merge row theo repair procedure.
9. Cho apply worker retry transaction lỗi.
10. Xác minh dữ liệu không bị duplicate hoặc overwrite sai.

Nếu publisher đã thay đổi row nhiều lần sau thời điểm row subscriber bị thiếu, cần quyết định áp dụng trạng thái hiện tại hay tái dựng lịch sử. Một INSERT snapshot đơn lẻ không phải lúc nào cũng đủ để khôi phục đúng transaction semantics.

## 21. Sửa constraint/schema conflict

Nếu lỗi do constraint:
- So sánh definition trên hai phía.
- Xác định dữ liệu có hợp lệ theo business rule không.
- Đồng bộ CHECK/FK/UNIQUE/NOT NULL semantics.
- Kiểm tra default/generated expression.
- Kiểm tra trigger và permissions.
- Triển khai migration theo thứ tự tương thích.
- Revalidate constraints nếu dùng NOT VALID workflow.
- Cho apply tiếp tục và kiểm tra row.

### 21.1. Không nới constraint vĩnh viễn chỉ để replication chạy

Nếu constraint bảo vệ invariant quan trọng, phải giữ invariant ở cả hai phía. Tìm nguyên nhân dữ liệu publisher không phù hợp hoặc migration thiếu.

### 21.2. Không thêm constraint chặt hơn subscriber mà publisher không thể đáp ứng

Subscriber phải chấp nhận mọi row mà publication contract gửi tới, trừ khi có lý do kiến trúc rõ ràng.

### 21.3. Type/domain/enum changes

Đồng bộ enum labels, domain constraints, type casts và extension definitions trước khi publisher phát giá trị mới.

## 22. Transaction skip: cơ chế cuối cùng có kiểm soát

Một số PostgreSQL versions hỗ trợ:

```sql
ALTER SUBSCRIPTION sub_orders
SKIP (lsn = '0/16B6C50');
```

Lệnh này yêu cầu subscription bỏ qua một remote transaction tại LSN được chỉ định theo semantics của version. Cú pháp, điều kiện và thời điểm worker xử lý skip phải được kiểm tra trên đúng PostgreSQL major version.

### 22.1. Skip toàn transaction

Skip không chỉ bỏ qua một row/statement trong transaction. Nó có thể bỏ toàn bộ transaction remote, bao gồm nhiều thay đổi bảng khác.

### 22.2. Hậu quả dữ liệu

Publisher đã commit transaction nhưng subscriber bỏ qua, vì vậy subscriber có thể thiếu rows hoặc giữ trạng thái cũ. Apply progress tiến lên nhưng data divergence vẫn còn.

### 22.3. Khi nào mới cân nhắc?

Chỉ khi:
- Transaction lỗi đã được xác định chính xác.
- Biết toàn bộ tác động của transaction.
- Có kế hoạch bù/repair data.
- Business owner chấp nhận hậu quả.
- Evidence và LSN được lưu.
- Có cách xác minh sau skip.

### 22.4. Không dùng skip để chữa mọi duplicate key

Duplicate có thể chỉ là một row conflict nhưng transaction chứa nhiều thay đổi hợp lệ khác. Ưu tiên sửa subscriber state nếu có thể.

### 22.5. Không advance origin thủ công thay cho skip

Thay đổi replication origin tùy tiện có thể làm subscriber bỏ qua một dải changes lớn hơn transaction lỗi. Chỉ dùng cơ chế được tài liệu hóa và có kế hoạch recovery.

## 23. Tạm dừng và khởi động lại subscription

Có thể điều khiển subscription:

```sql
ALTER SUBSCRIPTION sub_orders DISABLE;
ALTER SUBSCRIPTION sub_orders ENABLE;
```

### 23.1. DISABLE

Dừng apply worker của subscription. Dùng khi cần sửa schema/data hoặc điều tra mà không muốn worker retry liên tục.

### 23.2. ENABLE

Khởi động lại apply theo cấu hình. Nếu lỗi chưa được sửa, worker có thể gặp lại cùng transaction.

### 23.3. Không restart lặp đi lặp lại

Restart không sửa duplicate key, missing row hay schema drift. Chỉ enable sau khi đã xử lý root cause hoặc có quyết định skip/resync.

### 23.4. Theo dõi sau enable

Kiểm tra apply worker PID, latest_end_lsn, origin progress, logs và dữ liệu table liên quan.

## 24. Resync một bảng

Nếu table đã drift nghiêm trọng, sửa từng row có thể không còn đáng tin cậy. Có thể cần resync table từ publisher theo quy trình.

Các hướng triển khai có thể gồm:
- Dùng publication membership/refresh workflow để table được initial sync lại theo đúng version và trạng thái catalog.
- Dừng apply và thực hiện controlled snapshot copy.
- Dùng dump/restore cho table trong một cửa sổ có consistency plan.
- Tạo subscription/table mới rồi cutover khi xác minh xong.

### 24.1. Không TRUNCATE subscriber tùy tiện

TRUNCATE có thể phá dữ liệu cục bộ hoặc làm mất rows chưa được publisher quản lý. Phải xác nhận subscriber table chỉ là replica của source và có backup.

### 24.2. Publication remove/add workflow

Một số workflow có thể remove relation khỏi publication, refresh subscription rồi add lại để kích hoạt initial copy. Hành vi cụ thể phụ thuộc version, subscription state và copy_data. Thử trên staging trước khi áp dụng.

### 24.3. Snapshot consistency

Snapshot dùng để copy table phải có một điểm nhất quán tương thích với WAL stream sẽ được apply sau đó. Nếu snapshot và replication origin không khớp, có thể mất hoặc lặp changes.

### 24.4. Kiểm tra trước cutover

So sánh row counts, key ranges, checksums/aggregates, constraints và application queries. Chỉ đưa table trở lại ready state khi xác minh xong.

## 25. Resync toàn subscription

Khi nhiều bảng lệch hoặc không còn tin cậy replication origin, có thể cần xây lại subscription/consumer.

Một kế hoạch có thể:
1. Xác định source of truth và maintenance window.
2. Backup subscriber hiện tại.
3. Ghi subscription/publication definitions và slot identity.
4. Dừng apply.
5. Chuẩn bị subscriber schema.
6. Lấy consistent snapshot/base data.
7. Tạo subscription/slot mới theo plan.
8. Copy dữ liệu và bắt đầu apply WAL từ điểm tương thích.
9. So sánh critical data.
10. Cutover application reads.
11. Theo dõi lag/errors.
12. Chỉ cleanup subscription/slot cũ sau khi chứng minh không còn consumer phụ thuộc.

### 25.1. Slot lifecycle

Replication slot trên publisher giữ WAL cho subscriber. Drop/recreate slot có thể làm mất khả năng tiếp tục từ vị trí cũ và yêu cầu full resync.

### 25.2. Tránh hai apply workers cùng ghi một table

Trong quá trình chuyển đổi, không để subscription cũ và mới cùng apply vào một target table trừ khi workflow đã được thiết kế để tránh duplicate/conflict.

### 25.3. Có rollback point

Giữ snapshot/backup subscriber và ghi lại LSN/slot/origin state trước khi thay đổi. Nếu resync thất bại, phải có cách quay lại trạng thái kiểm soát.

## 26. Kiểm tra publication và subscription definitions

Trên publisher:

```sql
SELECT
    pubname,
    puballtables,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_publication
ORDER BY pubname;
```

Danh sách table:

```sql
SELECT
    pubname,
    schemaname,
    tablename
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
```

Trên subscriber:

```sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications,
    subbinary
FROM pg_subscription
ORDER BY subname;
```

Một số catalog columns thay đổi theo version. Query catalog chỉ dành cho role có quyền phù hợp và cần đối chiếu version.

### 26.1. Không chia sẻ connection string

Catalog có thể chứa connection information nhạy cảm. Không đưa password/conninfo vào logs, ticket hoặc tài liệu công khai.

### 26.2. Kiểm tra publication table scope

Nếu table không thuộc publication, subscriber không nhận changes. Đó có thể là cấu hình thiếu hoặc expected behavior.

### 26.3. Kiểm tra subscription enabled

Subscription disabled thì apply worker không chạy. Đừng điều tra data conflict trước khi xác nhận trạng thái subscription.

## 27. Kiểm tra row differences

Đối với table nhỏ, có thể so sánh trực tiếp các key ranges. Ví dụ:

```sql
SELECT customer_id, email, status
FROM public.customers
WHERE customer_id BETWEEN 1000 AND 1100
ORDER BY customer_id;
```

Chạy trên cả publisher và subscriber, lưu kết quả có kiểm soát rồi đối chiếu.

### 27.1. Row count không đủ

Hai bảng có cùng số rows nhưng key/value khác nhau vẫn là drift. So sánh primary keys và cột nghiệp vụ quan trọng.

### 27.2. Aggregate checksum

Có thể tính aggregate/hash theo key range để phát hiện range khác nhau, nhưng thiết kế checksum phải ổn định về encoding, NULL handling, column order và collation.

### 27.3. Chia range

Với bảng lớn, chia theo primary key/time partition để khoanh vùng. Tránh full table scan đồng thời trên production nếu chi phí cao.

### 27.4. Snapshot consistency

Nếu publisher vẫn ghi trong khi so sánh, hai query có thể đọc hai snapshot khác thời điểm. Dùng snapshot/replication-consistent point hoặc dừng writes trong maintenance window.

## 28. Data drift không có apply error

Subscriber có thể lệch mà apply worker vẫn hoạt động:
- Subscriber được ghi cục bộ.
- Table không nằm trong publication.
- Row filter loại một số rows.
- Column list không phát mọi cột.
- Sequence state không đồng bộ.
- DDL khác nhau.
- Một transaction trước đó đã được skip.
- Application đọc nhầm node/timeline.
- Một table sync chưa hoàn tất.

### 28.1. Apply healthy không đồng nghĩa data identical

Apply worker có thể đã xử lý hết stream nhưng không bao phủ dữ liệu ngoài publication contract.

### 28.2. Sequence drift

Logical replication không tự đồng bộ sequence state. Nếu subscriber được dùng để ghi sau cutover, sequence có thể phát key đã tồn tại. Cần đồng bộ sequence theo migration/cutover runbook.

### 28.3. DDL drift

Nếu subscriber có thêm cột local hoặc constraint khác, có thể vẫn apply được một thời gian rồi lỗi khi publisher gửi một giá trị không tương thích.

### 28.4. Audit theo ownership

Ghi rõ table nào publisher-owned, subscriber read-only, subscriber-local hay shared-by-design. Nếu không có ownership, mọi khác biệt đều khó giải thích.

## 29. Dữ liệu do trigger thay đổi

Trigger trên subscriber có thể:
- Sửa giá trị trước khi ghi.
- Tạo audit row.
- Gọi function phụ.
- Gửi notification.
- Raise exception.
- Thay đổi bảng khác.

### 29.1. Side effects có thể lặp

Apply worker retry transaction có thể khiến trigger side effects được thực hiện lại trong những lần transaction rollback/attempt, tùy cách side effect được triển khai. Không dùng trigger để gửi email/thanh toán trực tiếp khi apply logical changes.

### 29.2. Trigger phải idempotent hoặc được kiểm soát

Nếu cần trigger trên subscriber, thiết kế side effects an toàn và hiểu replication apply behavior. Các external side effects nên đi qua outbox/consumer có idempotency.

### 29.3. Trigger disable không phải cách sửa mặc định

Tắt trigger có thể bỏ qua business invariants. Chỉ thực hiện theo migration/repair plan có validation và rollback.

## 30. Foreign keys và thứ tự dữ liệu

Logical apply giữ transaction semantics của stream, nhưng publication có thể không bao gồm tất cả bảng phụ thuộc. Subscriber có FK có thể từ chối row nếu parent không tồn tại.

Ví dụ:
- Publisher phát INSERT vào order_items.
- Publication không phát bảng orders.
- Subscriber có FK order_items.order_id → orders.id.
- Parent row chưa tồn tại ở subscriber.
- Apply transaction thất bại.

### 30.1. Kiểm tra publication dependencies

Liệt kê các FK và xác định mọi parent/child table cần đồng bộ. Không giả định publication tự động thêm bảng liên quan.

### 30.2. Không bỏ FK để chữa lỗi mà không có invariant plan

Nếu subscriber cần FK để bảo vệ dữ liệu, phải đồng bộ parent data/ordering phù hợp.

### 30.3. Initial copy order

Table synchronization có thể chạy song song. FK giữa các bảng trong initial sync cần được thiết kế/test theo PostgreSQL version và workflow; đừng giả định mọi bảng copy theo thứ tự FK.

## 31. TRUNCATE và publication

Logical replication có thể publish TRUNCATE nếu publication được cấu hình cho loại operation này theo version. TRUNCATE khác DELETE: nó tác động toàn table hoặc partition set theo semantics, không có row-by-row predicate.

### 31.1. Subscriber data cục bộ

Nếu subscriber chứa rows local, một replicated TRUNCATE có thể xóa chúng. Đây là lý do phải tách subscriber-local data ra khỏi replicated table.

### 31.2. Foreign key restrictions

TRUNCATE có giới hạn với FK và cách publish/apply cần xét toàn bộ relation set. Kiểm tra PostgreSQL docs/version trước khi bật.

### 31.3. Không dùng TRUNCATE để reset table drift khi chưa có snapshot

Có thể mất dữ liệu hợp lệ và làm application đọc thấy table rỗng trong thời gian resync.

## 32. DDL migration không đồng bộ

Một workflow migration an toàn cần xác định thứ tự cho publisher/subscriber.

Ví dụ thêm cột:
1. Thêm cột tương thích trên subscriber trước.
2. Thêm cột trên publisher.
3. Xác minh apply worker tiếp tục.
4. Deploy application code theo rollout plan.
5. Backfill nếu cần.
6. Thêm constraint sau khi dữ liệu đã đạt điều kiện.
7. Xóa cột cũ ở cả hai phía trong release sau.

### 32.1. Expand-contract

Chiến lược expand-contract giúp schema changes tương thích trong giai đoạn hai phiên bản cùng hoạt động:
- Expand: thêm cấu trúc mới.
- Migrate: ghi/đọc tương thích và backfill.
- Validate: kiểm tra dữ liệu.
- Contract: xóa cấu trúc cũ khi mọi consumer đã chuyển.

### 32.2. Enum additions

Nếu publisher gửi enum label mà subscriber chưa có, apply có thể lỗi. Đồng bộ enum label trước khi ứng dụng/publisher phát giá trị mới.

### 32.3. Type changes

Thay đổi type cần kiểm tra binary/text compatibility và column mapping. Test trên staging bằng dữ liệu đại diện.

## 33. Publication row filter thay đổi

Row filter xác định rows được phát từ publisher. Khi filter thay đổi, subscriber có thể không chứa đầy đủ rows theo điều kiện mới nếu không có backfill/sync procedure phù hợp.

Ví dụ publication chỉ phát:

```sql
CREATE PUBLICATION pub_active_customers
FOR TABLE public.customers
WHERE (active = true);
```

Nếu một row đổi từ active=false sang true, subscriber có thể bắt đầu nhận row update/insert theo semantics publication/version. Nếu row đổi ngược lại, behavior và việc xóa row khỏi subscriber cần được xác minh theo PostgreSQL version/operation.

### 33.1. Filter không phải row security

Publication row filter là phạm vi logical replication. Không thay thế authorization/security policy.

### 33.2. Thay filter cần kế hoạch backfill

Ghi rõ rows nào được thêm/bớt, cách xóa rows không còn đủ điều kiện và cách đảm bảo subscriber data đúng.

### 33.3. Không so sánh full table

So sánh theo publication contract và filter hiện hành.

## 34. Binary mode và type compatibility

Subscription có thể có option binary transfer trong những version hỗ trợ. Binary representation có thể yêu cầu tương thích type/encoding cụ thể hơn so với text conversion.

### 34.1. Không bật binary để chữa apply error

Nếu lỗi là duplicate key hoặc missing row, binary transfer không giải quyết nguyên nhân.

### 34.2. Version/type compatibility

Kiểm tra source/target major version, type send/receive functions, extension types và collation. Test với mọi type custom quan trọng.

### 34.3. Error context

Nếu lỗi cast/type, lưu SQLSTATE, column/type name và sample value đã được bảo vệ trước khi thay đổi schema.

## 35. Permissions và apply role

Apply worker kết nối theo subscription configuration và cần quyền phù hợp trên subscriber. Lỗi có thể do:
- Table owner/privileges.
- Schema USAGE.
- INSERT/UPDATE/DELETE grants.
- Sequence privileges trong application workflows.
- Trigger/function permissions.
- RLS/policy hoặc security configuration.
- Extension/function không tồn tại.

### 35.1. Phân biệt permission error với data conflict

permission denied không phải duplicate key. Đọc SQLSTATE và object name trước khi sửa.

### 35.2. Least privilege

Cấp quyền cần thiết cho replication apply theo version/documentation. Không biến subscription user thành superuser chỉ để vượt qua lỗi quyền.

### 35.3. Kiểm tra sau migration

Một migration có thể đổi owner hoặc grants trên subscriber mà không thay publisher. Đưa grants vào schema deployment process.

## 36. Lỗi do nhiều subscriptions hoặc publishers

Nếu cùng subscriber table nhận changes từ nhiều subscriptions:
- Có thể trùng primary keys.
- Transaction order giữa publishers không được bảo đảm như một stream duy nhất.
- Cùng row có thể được cập nhật theo thứ tự khác nhau.
- Deletes/updates có thể không tìm thấy row.
- Constraint conflict có thể xuất hiện không ổn định.

### 36.1. Thiết kế key space

Nếu thực sự cần hợp nhất nhiều nguồn, dùng key namespace/tenant/source identifier rõ ràng.

### 36.2. Ownership partition

Chia bảng/rows theo owner để mỗi source chỉ ghi phần dữ liệu của mình, hoặc dùng application-level merge pipeline.

### 36.3. Conflict resolution layer

Multi-source replication cần quy tắc conflict resolution xác định: last-write-wins, version vector, owner priority hay domain-specific merge. Built-in subscription apply không tự cung cấp business semantics này.

## 37. Tạm dừng apply để điều tra

Khi lỗi lặp và cần thời gian sửa:

```sql
ALTER SUBSCRIPTION sub_orders DISABLE;
```

Sau khi sửa:

```sql
ALTER SUBSCRIPTION sub_orders ENABLE;
```

### 37.1. Dừng có mục tiêu

Một subscription có thể chứa nhiều bảng. Disable dừng apply của subscription đó, ảnh hưởng toàn bộ các relation thuộc subscription. Ghi rõ blast radius.

### 37.2. Không dừng publisher writes mặc định

Có thể cần tiếp tục publisher writes nếu slot giữ WAL và storage đủ. Tuy nhiên lag/WAL retention phải được theo dõi để tránh đầy disk.

### 37.3. Xác nhận capacity khi pause lâu

Replication slot có thể giữ WAL trên publisher. Một subscription bị disable lâu có thể làm pg_wal tăng.

## 38. Transaction skip: quy trình quyết định

Trước khi skip:
1. Xác định chính xác remote transaction LSN.
2. Lưu log và transaction context.
3. Liệt kê tất cả tables/rows bị thay đổi trong transaction nếu có thể.
4. Xác định hậu quả nếu subscriber không nhận các changes.
5. Kiểm tra có thể sửa subscriber row để transaction apply bình thường không.
6. Nếu không thể, xây data repair plan cho mọi changes bị bỏ.
7. Xin quyết định từ owner phù hợp theo policy.
8. Thực hiện lệnh theo đúng PostgreSQL version.
9. Theo dõi apply progress.
10. Reconcile dữ liệu và ghi evidence.

### 38.1. Skip không phải conflict resolution

Nó chỉ cho stream tiến qua transaction được chọn; không giải quyết sự khác nhau về dữ liệu.

### 38.2. Skip transaction lớn

Một transaction có thể thay đổi hàng nghìn rows/nhiều tables. Không chỉ sửa row xuất hiện trong error message rồi bỏ qua toàn transaction.

### 38.3. Không skip transaction chưa xác định

Nếu log không cho biết LSN/transaction hoặc chưa hiểu side effects, dừng và thu thập thêm evidence.

## 39. Xác minh sau khi apply chạy lại

Sau repair/enable/skip, kiểm tra:
- Apply worker đang hoạt động.
- latest_end_lsn tiến triển.
- Replication origin remote_lsn tiến triển.
- Error counters không tăng thêm.
- Logs không lặp lỗi cũ.
- Table sync state ready.
- Rows liên quan khớp source-of-truth.
- FK/unique/check constraints hợp lệ.
- Sequence state phù hợp với kế hoạch.
- Application read paths không trả dữ liệu stale/sai.

Ví dụ:

```sql
SELECT
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relation_name;
```

### 39.1. Tiến độ LSN không chứng minh dữ liệu giống nhau

Sau skip, origin progress có thể tiến nhưng transaction changes bị bỏ. Phải chạy data reconciliation.

### 39.2. Kiểm tra các transaction sau lỗi

Đảm bảo stream không chỉ chạy một lần rồi dừng ở transaction tiếp theo.

### 39.3. Theo dõi ít nhất một khoảng workload đại diện

Một apply worker chạy vài giây không chứng minh hệ thống ổn định qua batch/peak workload.

## 40. Monitoring và alerting

Một dashboard logical replication nên có:

| Metric | Nguồn | Mục đích |
|---|---|---|
| Subscription enabled | pg_subscription | Phát hiện subscription bị disable |
| Apply worker PID | pg_stat_subscription | Phát hiện worker không chạy |
| Latest end LSN/time | pg_stat_subscription | Theo dõi tiến độ |
| Apply/sync error counters | pg_stat_subscription_stats khi hỗ trợ | Phát hiện lỗi |
| Replication origin LSN | pg_replication_origin_status | Theo dõi apply progress |
| Table sync state | pg_subscription_rel | Phát hiện table chưa ready |
| Slot retained WAL | pg_replication_slots | Phát hiện WAL retention |
| Publisher WAL rate | LSN samples | Đo source pressure |
| PostgreSQL logs | Server logs | Root cause/SQLSTATE |
| Data drift checks | Reconciliation jobs | Phát hiện silent divergence |

### 40.1. Alert khi apply worker biến mất

Một subscription enabled nhưng không có apply worker có thể đang lỗi, bị disable hoặc không có work tùy trạng thái. Kết hợp logs và latest progress.

### 40.2. Alert khi progress đứng yên

Nếu publisher có changes mà latest_end_lsn/origin progress không tiến trong thời gian vượt ngưỡng, điều tra apply worker/connection.

### 40.3. Alert theo slot retention

Một subscriber lỗi có thể làm publisher giữ WAL lâu. Theo dõi disk headroom và retained distance.

### 40.4. Data drift checks định kỳ

Chọn bảng critical, key ranges và aggregates để so sánh theo snapshot nhất quán. Không đợi apply error mới phát hiện divergence.

## 41. Thiết kế ownership và write routing

Để tránh conflict, mỗi table nên có hợp đồng ownership:

| Table class | Owner | Subscriber policy |
|---|---|---|
| Publisher-owned | Primary publisher | Subscriber read-only |
| Subscriber-local | Subscriber application | Không nằm trong publication |
| Shared/reference | Owner được chỉ định | Cập nhật theo quy trình kiểm soát |
| Aggregated | Pipeline/consumer | Có logic rebuild/reconciliation |
| Migration staging | Migration process | Tách khỏi production tables |

### 41.1. Permissions hỗ trợ ownership

Dùng database roles để subscriber application không thể UPDATE/DELETE bảng publisher-owned ngoài quy trình.

### 41.2. Tách schema

Ví dụ:
- public_replica: dữ liệu do publisher sở hữu.
- local_app: dữ liệu chỉ thuộc subscriber.
- integration_stage: dữ liệu staging/reconciliation.

Tên schema chỉ là ví dụ; chọn theo architecture.

### 41.3. Ghi rõ source of truth

Mỗi bảng phải có owner, publication, expected filters, local-write policy và recovery process.

## 42. Data reconciliation strategy

Một chiến lược reconciliation có thể gồm:

1. Xác định source of truth.
2. Chọn snapshot/consistent point.
3. Xác định table/key range cần so sánh.
4. Tính row counts và key coverage.
5. So sánh values của critical columns.
6. Tính checksums/aggregates theo partition/key range.
7. Phân loại missing/extra/changed rows.
8. Xác định nguyên nhân.
9. Lập repair set có audit.
10. Apply repair trong maintenance window hoặc workflow an toàn.
11. Chạy lại comparison.
12. Lưu evidence và close incident.

### 42.1. Không merge tự động mọi khác biệt

Một giá trị mới hơn trên subscriber có thể là local write hợp lệ. Cần business ownership/version semantics.

### 42.2. Idempotent repair

Repair script nên có điều kiện rõ, kiểm tra pre-state và post-state. Chạy lại không tạo thêm duplicate hoặc overwrite ngoài ý muốn.

### 42.3. Audit repair

Ghi key, old/new values theo chính sách dữ liệu, source, reason, timestamp, operator và ticket/change reference.

## 43. Ví dụ runbook cho duplicate key

**Tình huống:** apply worker báo duplicate key trên public.orders, order_id = 9001.

1. Disable subscription nếu worker đang retry liên tục và cần cửa sổ điều tra.
2. Lưu log, LSN, worker PID và stats.
3. Query order 9001 trên publisher/subscriber.
4. Kiểm tra application logs và audit để xác định nguồn row subscriber.
5. Kiểm tra foreign keys/child rows.
6. Quyết định giữ publisher row, merge subscriber row hay sửa key.
7. Thực hiện repair có transaction và evidence.
8. Enable subscription.
9. Xác nhận apply worker đi qua transaction lỗi.
10. So sánh order và child rows.
11. Kiểm tra error counters/logs.
12. Ghi corrective action: chặn local writes hoặc sửa seed process.

### 43.1. Nếu publisher row là đúng

Subscriber row có thể cần được chuyển/merge hoặc loại bỏ sau khi xác nhận dependencies.

### 43.2. Nếu subscriber row là dữ liệu cần giữ

Không xóa; reconcile thành một row/record có ownership rõ rồi quyết định cách publisher tiếp tục phát changes.

### 43.3. Nếu duplicate do sequence

Logical replication không đồng bộ sequence state tự động. Kiểm tra sequence/identity và key generation trên subscriber trước khi cutover writes.

## 44. Ví dụ runbook cho missing row UPDATE

**Tình huống:** publisher UPDATE order_id = 9001 nhưng subscriber không có row.

1. Lưu apply error và remote transaction context.
2. Query order 9001 trên publisher.
3. Kiểm tra subscriber có row không.
4. Kiểm tra publication/filter và initial sync state.
5. Kiểm tra transaction INSERT trước đó có bị skip không.
6. Kiểm tra subscriber local DELETE/audit.
7. Lấy snapshot row phù hợp từ publisher.
8. Repair subscriber row và dependent data.
9. Enable apply.
10. Xác nhận UPDATE được áp dụng và stream tiếp tục.
11. Reconcile table/range để phát hiện missing rows khác.
12. Sửa nguyên nhân gốc.

Nếu transaction publisher đã cập nhật row nhiều lần, xác định trạng thái snapshot phù hợp và tránh replay history không tương thích với repair.

## 45. Bài tập thực hành có đáp án

### Bài 1. Logical replication conflict là gì?

**Đáp án:** Tình huống subscriber không thể áp dụng một logical change vì dữ liệu, schema, identity, constraints hoặc trạng thái hiện tại không tương thích.

### Bài 2. Logical replication có tự giải quyết duplicate key không?

**Đáp án:** Không. Apply transaction thường lỗi; cần điều tra và sửa dữ liệu hoặc dùng quy trình skip có kiểm soát theo version.

### Bài 3. Duplicate key khi INSERT thường có nghĩa gì?

**Đáp án:** Subscriber đã có key vi phạm unique/primary key khi apply INSERT.

### Bài 4. UPDATE không tìm thấy row có thể do đâu?

**Đáp án:** Row bị xóa local, initial sync thiếu, filter, replica identity hoặc transaction trước đó bị skip.

### Bài 5. DELETE không tìm thấy row có thể do đâu?

**Đáp án:** Subscriber đã thiếu row, dữ liệu lệch, filter hoặc một thay đổi trước đó không được áp dụng.

### Bài 6. Apply error có thể làm gì với subscription?

**Đáp án:** Apply worker không tiến qua transaction lỗi; worker có thể retry nhưng lỗi deterministic sẽ lặp cho tới khi nguyên nhân được xử lý.

### Bài 7. Logical replication có replicate DDL tự động?

**Đáp án:** Không. Schema changes phải được quản lý riêng trên subscriber.

### Bài 8. Sequence state có được logical replication đồng bộ tự động?

**Đáp án:** Không theo cách đảm bảo next value; phải kiểm tra/synchronize theo cutover plan.

### Bài 9. Replica identity dùng để làm gì?

**Đáp án:** Xác định row cũ cần UPDATE/DELETE trên subscriber.

### Bài 10. Replica identity DEFAULT thường dùng gì?

**Đáp án:** Primary key nếu table có primary key.

### Bài 11. Bảng không có primary key có thể replicate UPDATE/DELETE không?

**Đáp án:** Có thể nếu cấu hình replica identity phù hợp, ví dụ unique index hợp lệ hoặc FULL; NOTHING không đủ cho UPDATE/DELETE.

### Bài 12. REPLICA IDENTITY FULL có trade-off gì?

**Đáp án:** Ghi nhiều old row values hơn và có thể tăng WAL/lookup cost.

### Bài 13. Subscriber có CHECK constraint chặt hơn publisher có thể gây gì?

**Đáp án:** Apply row hợp lệ trên publisher nhưng bị subscriber từ chối.

### Bài 14. Foreign key parent không nằm trong publication có thể gây lỗi gì?

**Đáp án:** Child row apply có thể fail vì referenced parent chưa tồn tại trên subscriber.

### Bài 15. Subscriber-local writes có nguy cơ gì?

**Đáp án:** Tạo duplicate/missing rows hoặc silent data divergence với publisher.

### Bài 16. Built-in logical replication có phải multi-master?

**Đáp án:** Không. Không tự giải quyết conflict giữa nhiều nguồn ghi cùng dữ liệu.

### Bài 17. Publication row filter có thể làm subscriber thiếu rows so với publisher?

**Đáp án:** Có, đó có thể là expected subset theo publication contract.

### Bài 18. pg_stat_subscription xem ở đâu?

**Đáp án:** Trên subscriber, để quan sát apply/table sync workers và tiến độ theo version.

### Bài 19. pg_stat_subscription_stats cung cấp gì?

**Đáp án:** Trên versions hỗ trợ, cung cấp counters apply_error_count và sync_error_count cùng stats reset.

### Bài 20. pg_replication_origin_status cho biết gì?

**Đáp án:** Remote/local LSN progress của replication origins; không chứng minh row data giống nhau.

### Bài 21. Vì sao cần đọc PostgreSQL logs?

**Đáp án:** Logs có SQLSTATE, constraint/table, key và transaction context/LSN để xác định lỗi gốc.

### Bài 22. Restart subscription có sửa duplicate key?

**Đáp án:** Không. Nó thường làm cùng transaction lỗi được thử lại.

### Bài 23. DISABLE subscription dùng khi nào?

**Đáp án:** Khi cần dừng apply có mục tiêu để điều tra hoặc repair, đồng thời theo dõi WAL retention.

### Bài 24. SKIP transaction bỏ qua điều gì?

**Đáp án:** Bỏ toàn bộ remote transaction tại LSN được chỉ định theo semantics/version, không chỉ một row.

### Bài 25. Vì sao skip có thể gây drift?

**Đáp án:** Publisher đã commit changes nhưng subscriber bỏ qua các changes đó trong transaction.

### Bài 26. Có nên skip mọi duplicate key?

**Đáp án:** Không. Transaction có thể chứa nhiều changes hợp lệ; ưu tiên repair subscriber nếu có thể.

### Bài 27. Khi nào cần resync table?

**Đáp án:** Khi drift lớn/không còn tin cậy và sửa từng row không phù hợp; cần snapshot-consistent procedure.

### Bài 28. Có nên TRUNCATE subscriber table tùy tiện để resync?

**Đáp án:** Không. Có thể mất local data và phá consistency; cần xác nhận ownership, backup và copy workflow.

### Bài 29. pg_subscription_rel giúp gì?

**Đáp án:** Cho biết trạng thái synchronization của từng relation theo catalog/version.

### Bài 30. Apply worker và table sync worker giống nhau?

**Đáp án:** Không. Một worker áp dụng stream; table sync worker thực hiện initial copy/sync cho relation.

### Bài 31. Subscriber có thể lệch dù apply worker khỏe?

**Đáp án:** Có, do local writes, publication filters, skipped transaction, sequence/schema drift hoặc objects ngoài publication.

### Bài 32. pg_publication_tables giúp gì?

**Đáp án:** Liệt kê các bảng thuộc publication để kiểm tra scope.

### Bài 33. Vì sao schema migration cần thứ tự?

**Đáp án:** Publisher có thể gửi cột/type mới mà subscriber chưa sẵn sàng, làm apply fail.

### Bài 34. Expand-contract có lợi ích gì?

**Đáp án:** Giữ schema tương thích trong rollout nhiều phiên bản và giúp migration an toàn hơn.

### Bài 35. Trigger trên subscriber có thể gây lỗi apply?

**Đáp án:** Có. Trigger có thể raise exception hoặc thay đổi dữ liệu/side effects.

### Bài 36. Có nên gửi email/payment trực tiếp từ trigger subscriber?

**Đáp án:** Không nên. Retry/rollback có thể gây side effects lặp; dùng outbox/idempotent consumer.

### Bài 37. pg_replication_origin_advance có nên dùng để sửa lag?

**Đáp án:** Không tùy tiện. Nó có thể làm bỏ qua một dải changes và gây data loss.

### Bài 38. Sequence drift thường lộ ra khi nào?

**Đáp án:** Khi subscriber bắt đầu nhận writes/cutover và next sequence value có thể trùng key hiện có.

### Bài 39. Row count bằng nhau có chứng minh dữ liệu giống nhau?

**Đáp án:** Không. Key/value có thể khác; cần key-range comparison và checksum/semantic checks.

### Bài 40. Snapshot consistency quan trọng khi reconcile vì sao?

**Đáp án:** Hai bên vẫn có writes; so sánh hai snapshot khác thời điểm có thể tạo false differences.

### Bài 41. Nhiều subscriptions cùng ghi một table có rủi ro gì?

**Đáp án:** Key collision, ordering ambiguity và update/delete conflict; cần ownership/merge design.

### Bài 42. Vì sao cần giữ WAL khi subscription disable?

**Đáp án:** Replication slot có thể giữ WAL cần cho subscriber; pause lâu có thể làm pg_wal tăng.

### Bài 43. pg_stat_subscription latest_end_lsn tiến nhưng dữ liệu vẫn drift có thể không?

**Đáp án:** Có, ví dụ transaction đã bị skip hoặc dữ liệu local khác publication contract.

### Bài 44. Lỗi permission denied có phải data conflict?

**Đáp án:** Không. Đây là lỗi quyền/object access; đọc SQLSTATE và sửa grants phù hợp.

### Bài 45. TRUNCATE có thể được publish?

**Đáp án:** Có theo publication operation options/version; phải xét tác động toàn table và FK.

### Bài 46. Cách phát hiện lỗi table synchronization?

**Đáp án:** Kết hợp logs, worker state và pg_subscription_rel relation synchronization state.

### Bài 47. Cách xử lý transaction skip an toàn?

**Đáp án:** Xác định LSN/transaction, toàn bộ tác động, business approval, repair plan và verification trước/sau.

### Bài 48. Cách ngăn subscriber-local write gây conflict?

**Đáp án:** Tách schema/table local, phân quyền read-only cho publisher-owned tables và ghi rõ source of truth.

### Bài 49. Khi nào cần resync toàn subscription?

**Đáp án:** Khi nhiều tables/origin state đã drift nghiêm trọng hoặc không thể tin cậy incremental repair; cần snapshot/slot/cutover plan.

### Bài 50. Điều kiện kết thúc incident apply error?

**Đáp án:** Root cause đã sửa, worker tiến qua lỗi, không còn retry, data reconciliation/constraints đạt, progress và evidence được lưu.

## 46. Checklist xử lý logical replication conflict

| Giai đoạn | Câu hỏi |
|---|---|
| Nhận diện | Publisher, subscriber và subscription nào? |
| Trạng thái | Subscription enabled không? |
| Worker | Apply worker hay table sync worker lỗi? |
| Logs | SQLSTATE và lỗi đầu tiên là gì? |
| Transaction | Có remote transaction LSN không? |
| Relation | Table/operation INSERT, UPDATE, DELETE hay TRUNCATE? |
| Identity | Replica identity có phù hợp không? |
| Schema | Columns/types/defaults/constraints có tương thích? |
| Publication | Table, operation, filter và column list có đúng? |
| Data | Row trên publisher/subscriber khác nhau thế nào? |
| Ownership | Có subscriber-local writes hoặc trigger side effects? |
| Repair | Có thể sửa row/schema để apply bình thường? |
| Skip | Nếu skip, toàn transaction ảnh hưởng những gì? |
| Resync | Snapshot và WAL/origin point có tương thích? |
| Retention | Slot đang giữ bao nhiêu WAL khi apply dừng? |
| Verification | Worker, LSN/origin progress và logs có tiến? |
| Data QA | Keys, values, constraints và business invariants đạt? |
| Prevention | Ownership, permissions và migration process đã sửa? |
| Evidence | Logs, LSN, before/after và operator được ghi lại? |

## 47. Tài liệu PostgreSQL chính thức

- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — kiến trúc publisher/subscriber và giới hạn.
- [Logical Replication Conflicts](https://www.postgresql.org/docs/current/logical-replication-conflicts.html) — các conflict khi apply changes.
- [Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html) — DDL, sequences và các giới hạn.
- [CREATE PUBLICATION](https://www.postgresql.org/docs/current/sql-createpublication.html) — publication tables và operation options.
- [CREATE SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-createsubscription.html) — subscription và initial copy.
- [ALTER SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-altersubscription.html) — enable/disable, refresh và skip options theo version.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — subscription/replication monitoring views.
- [pg_replication_origin_status](https://www.postgresql.org/docs/current/view-pg-replication-origin-status.html) — replication origin progress.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — logical slot retention.
- [Replica Identity](https://www.postgresql.org/docs/current/logical-replication-publication.html) — identity requirements for published updates/deletes.

Logical replication behavior, skip syntax, catalog columns, worker views và conflict observability thay đổi theo PostgreSQL major version. Trước khi dùng lệnh repair/resync, kiểm tra server_version, catalog definitions và tài liệu đúng phiên bản đang vận hành.

## 48. Tổng kết: sửa nguyên nhân, bảo toàn dữ liệu, xác minh tiến độ

```text
Apply error
    |
    v
Identify transaction / LSN / relation
    |
    v
Classify root cause
    |
    +-- Duplicate key / missing row
    |
    +-- Constraint / replica identity
    |
    +-- Schema / publication mismatch
    |
    +-- Initial sync / permission / trigger
    |
    v
Choose controlled repair
    |
    +-- Repair subscriber data
    |
    +-- Align schema/configuration
    |
    +-- Resync table/subscription
    |
    +-- Skip whole transaction only with explicit repair plan
    |
    v
Resume apply
    |
    v
Verify LSN progress + row data + business invariants
```

Những nguyên tắc cần nhớ:

1. **Logical replication là luồng một chiều theo publication contract.** Nó không tự giải quyết multi-master conflicts.
2. **Duplicate key và missing row thường phản ánh data drift.** So sánh cả hai phía trước khi sửa.
3. **Replica identity quyết định cách tìm row cho UPDATE/DELETE.** Bảng cần identity phù hợp.
4. **DDL không tự replicate.** Schema migration phải được phối hợp giữa publisher và subscriber.
5. **Subscriber-local writes là nguồn conflict lớn.** Phân quyền và ownership rõ ràng.
6. **Apply worker lỗi thường dừng ở transaction gây lỗi.** Restart không sửa root cause.
7. **Initial table sync có worker và trạng thái riêng.** Kiểm tra relation sync state khi copy dữ liệu ban đầu.
8. **Transaction skip bỏ cả transaction.** Chỉ dùng khi đã hiểu toàn bộ changes và có kế hoạch bù dữ liệu.
9. **Resync cần snapshot/WAL consistency.** Không TRUNCATE hay copy table tùy tiện.
10. **Replication origin progress không chứng minh data equality.** Cần row/key/checksum/business validation.
11. **Archive/slot retention vẫn quan trọng khi subscription dừng.** Theo dõi WAL capacity trên publisher.
12. **Incident chỉ đóng khi apply tiến và dữ liệu đã được reconcile.** Giữ logs, LSN, before/after evidence và corrective actions.

**Một câu để nhớ:** *Khi logical replication gặp conflict, hãy tìm transaction và nguyên nhân làm subscriber không thể áp dụng nó; sửa dữ liệu/schema theo source of truth, chỉ skip khi hiểu rõ tổn thất, rồi xác minh cả tiến độ stream lẫn tính đúng đắn của dữ liệu.*

