# Điều kiện dùng snapshot và tính nhất quán toàn bộ dữ liệu trong PostgreSQL

Một bản backup chỉ hữu ích khi dữ liệu trong đó tạo thành một trạng thái có thể phục hồi và có ý nghĩa. Nếu một bản sao chứa bảng đơn hàng tại thời điểm A, bảng thanh toán tại thời điểm B và file đính kèm tại thời điểm C, ứng dụng có thể khôi phục được từng thành phần nhưng lại nhận một hệ thống không nhất quán về nghiệp vụ.

PostgreSQL cung cấp **MVCC snapshots** để một transaction đọc một trạng thái dữ liệu nhất quán trong database. Các công cụ như `pg_dump` dùng snapshot để xuất dữ liệu logic mà không cần dừng mọi hoạt động ghi. Với backup vật lý hoặc storage snapshots, yêu cầu lại khác: cần một bản sao data files có thể được đưa về trạng thái nhất quán bằng WAL recovery, đồng thời phối hợp đúng các volume, tablespaces và WAL.

Vì vậy, khi thiết kế backup phải trả lời hai câu hỏi:

1. **Snapshot nhìn thấy dữ liệu nào?** Những transaction nào được xem là đã commit tại thời điểm snapshot?
2. **Snapshot bao phủ những thành phần nào?** Tất cả bảng, database, tablespaces, WAL, Large Objects, sequence state, file bên ngoài và hệ thống liên quan có cùng một mốc nhất quán không?

Hai câu hỏi này quyết định snapshot có phù hợp để tạo logical dump, physical backup, storage snapshot, PITR hay bản sao phục vụ kiểm thử.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích MVCC snapshot và visibility rules trong PostgreSQL.
2. Phân biệt snapshot của từng statement với snapshot cố định của transaction.
3. Mô tả cách `pg_dump` dùng snapshot để tạo logical backup nhất quán.
4. Giải thích parallel dump và exported snapshot giữa nhiều connections.
5. Nêu điều kiện và giới hạn của `pg_export_snapshot`/`SET TRANSACTION SNAPSHOT`.
6. Phân biệt logical consistency với physical/crash consistency.
7. Dùng `pg_backup_start`/`pg_backup_stop` hoặc `pg_basebackup` đúng mục đích.
8. Xác định cách phối hợp snapshot trên nhiều volumes, tablespaces và WAL.
9. Hiểu giới hạn của snapshot khi có nhiều databases hoặc hệ thống bên ngoài PostgreSQL.
10. Nhận diện sequence state, Large Objects, roles/tablespaces và cấu hình không tự động được bảo đảm bởi một snapshot bảng đơn lẻ.
11. Định nghĩa consistency point, RPO/RTO, backup retention và restore validation.
12. Thiết kế các bài lab kiểm chứng snapshot và phục hồi.

## 2. MVCC snapshot là gì?

PostgreSQL sử dụng **Multi-Version Concurrency Control (MVCC)**. Khi một transaction UPDATE hoặc DELETE row, PostgreSQL thường tạo phiên bản row mới hoặc đánh dấu phiên bản cũ; readers có thể tiếp tục nhìn thấy phiên bản phù hợp với snapshot của mình mà không cần chặn writers trong phần lớn tình huống.

Snapshot là tập thông tin giúp PostgreSQL quyết định transaction nào đã commit, đang hoạt động hoặc chưa thể được xem là đã hoàn tất tại một thời điểm logic.

### 2.1. Snapshot quyết định row visibility

Một row version có các thông tin transaction nội bộ (ví dụ xmin/xmax) để PostgreSQL xác định nó có visible với snapshot hay không. Ứng dụng không nên tự viết logic nghiệp vụ dựa trên việc đọc trực tiếp các system columns này; hãy hiểu chúng như nền tảng của MVCC.

Ví dụ:

```text
Ban đầu:
  account 1 balance = 100

Transaction A:
  UPDATE balance = 150
  COMMIT

Transaction B bắt đầu snapshot:
  thấy balance = 150

Transaction C bắt đầu trước khi A commit:
  snapshot của C có thể không thấy phiên bản 150
  và tiếp tục thấy phiên bản cũ = 100
```

Snapshot không “đóng băng database” hay copy mọi pages vào RAM. Nó xác định phiên bản row nào được xem là visible khi query đọc dữ liệu.

### 2.2. READ COMMITTED: snapshot mới cho từng statement

Ở isolation level mặc định `READ COMMITTED`, mỗi statement thường nhìn thấy snapshot mới được lấy khi statement bắt đầu. Hai SELECT liên tiếp trong cùng transaction có thể thấy các commits xảy ra giữa hai câu lệnh.

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM bank.accounts
WHERE account_id = 1;

-- Transaction khác có thể UPDATE và COMMIT ở đây.

SELECT balance
FROM bank.accounts
WHERE account_id = 1;

COMMIT;
```

SELECT thứ hai có thể thấy giá trị mới. Do đó, nhiều câu SELECT dưới READ COMMITTED không tự tạo thành một snapshot cố định xuyên suốt transaction.

### 2.3. REPEATABLE READ: snapshot cố định cho transaction

Ở `REPEATABLE READ`, transaction sử dụng snapshot nhất quán được thiết lập cho lần đọc đầu tiên (hoặc khi snapshot được import). Các SELECT sau đó tiếp tục nhìn thấy cùng một trạng thái MVCC, ngay cả khi transaction khác commit thay đổi.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM sales.orders;
SELECT sum(total_amount) FROM sales.orders;

COMMIT;
```

Hai câu SELECT dùng cùng snapshot nên không thấy một nửa trạng thái trước và một nửa trạng thái sau các commits đồng thời.

### 2.4. SERIALIZABLE

`SERIALIZABLE` bổ sung kiểm soát để các transactions commit có thể được giải thích như một thứ tự tuần tự tương đương. Nó có thể abort transaction bằng serialization failure nếu phát hiện xung đột không thể tuần tự hóa.

Đối với read-only reporting/backup, có thể dùng `SERIALIZABLE READ ONLY DEFERRABLE` trong tình huống cần safe snapshot và chấp nhận chờ trước khi bắt đầu. Đây không phải yêu cầu mặc định của mọi backup.

### 2.5. Snapshot không bao gồm dữ liệu chưa commit

Nếu một transaction đã INSERT row nhưng chưa COMMIT khi snapshot được tạo, snapshot thông thường không coi row đó là dữ liệu committed để backup. Nếu transaction COMMIT sau thời điểm snapshot, dump dựa trên snapshot cũ cũng không thấy row mới.

Điều này là mong muốn: backup không nên lấy một nửa transaction hoặc coi dữ liệu chưa được xác nhận là đã tồn tại.

### 2.6. Snapshot không ngăn writes tiếp tục

MVCC cho phép backup đọc trạng thái nhất quán trong khi ứng dụng vẫn INSERT/UPDATE/DELETE. Writers không phải chờ toàn bộ dump hoàn tất chỉ vì reader giữ snapshot.

Tuy nhiên, snapshot dài hạn có chi phí: PostgreSQL có thể phải giữ các row versions cũ để transaction backup còn nhìn thấy. Điều này có thể làm VACUUM không thu hồi được dead tuples và tăng table/index bloat.

## 3. Snapshot tại statement và snapshot tại transaction

Phân biệt đúng hai phạm vi này là điều kiện quan trọng để tạo bản backup nhiều câu lệnh.

### 3.1. Hai SELECT dưới READ COMMITTED có thể thấy hai trạng thái

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT count(*) FROM app.orders;

-- Một session khác INSERT và COMMIT một order mới.

SELECT count(*) FROM app.orders;
COMMIT;
```

Nếu transaction thứ hai commit giữa hai SELECT, kết quả có thể khác nhau. Một backup tự viết bằng nhiều SELECT độc lập theo mặc định này có thể trộn các thời điểm.

### 3.2. Một transaction REPEATABLE READ dùng cùng snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM app.orders;

-- Session khác INSERT và COMMIT một order mới.

SELECT count(*) FROM app.orders;
COMMIT;
```

Hai SELECT nhìn thấy cùng snapshot. Row được commit sau snapshot không xuất hiện trong cả hai kết quả.

### 3.3. Snapshot bắt đầu khi nào?

Với REPEATABLE READ, snapshot thường được xác lập khi transaction thực hiện statement đầu tiên cần snapshot, không nhất thiết ngay ở câu `BEGIN`. Nếu cần snapshot chung với một exporter khác, hãy import snapshot trước statement đầu tiên của transaction consumer.

### 3.4. Transaction read-only

Khai báo `READ ONLY` giúp thể hiện rằng transaction chỉ đọc và có thể cho PostgreSQL áp dụng một số tối ưu/kiểm soát. Nó không tự làm snapshot bền vững qua restart, không export file backup và không ngăn các sessions khác ghi dữ liệu.

### 3.5. Snapshot không phải lock toàn database

Một transaction read-only REPEATABLE READ không khóa toàn bộ tables để giữ dữ liệu đứng yên. Nó dùng MVCC visibility. DDL vẫn có thể cần locks và xung đột với các hoạt động khác; các lock mà pg_dump giữ trên objects giúp tránh một số thay đổi cấu trúc gây bất nhất trong quá trình dump.

## 4. pg_dump và logical backup nhất quán

`pg_dump` tạo logical backup bằng cách đọc schema và dữ liệu rồi xuất thành SQL hoặc archive format. Nó được thiết kế để tạo một dump nhất quán trong khi database vẫn có thể được sử dụng đồng thời.

### 4.1. Snapshot của pg_dump

pg_dump mở transaction với snapshot phù hợp để các bảng được dump phản ánh một trạng thái MVCC nhất quán của database. Dữ liệu committed sau snapshot sẽ không xuất hiện trong dump đó.

Ví dụ:

```bash
pg_dump -Fc -f app.dump appdb
```

`-Fc` tạo custom archive; không có nghĩa snapshot là một filesystem image. Khi restore, `pg_restore` tái tạo các đối tượng logical.

### 4.2. Concurrent DML

Trong khi pg_dump chạy:

- Session ứng dụng có thể INSERT/UPDATE/DELETE.
- pg_dump vẫn đọc các row versions visible với snapshot của nó.
- Các transaction commit sau snapshot không được đưa vào dump.
- Những row versions cũ có thể phải được giữ lại cho tới khi dump kết thúc.

Do đó, một dump dài có thể làm tăng bloat nếu workload ghi liên tục và snapshot giữ lâu.

### 4.3. Concurrent DDL

pg_dump lấy locks phù hợp trên các objects để tránh schema thay đổi giữa lúc đọc metadata và dữ liệu. Một số DDL có thể phải đợi hoặc khiến dump thất bại nếu xung đột lock. Vì vậy cần phối hợp migration/DDL với backup windows và đọc lỗi pg_dump thay vì giả định mọi DDL luôn chạy song song không ảnh hưởng.

### 4.4. Snapshot của một database

pg_dump hoạt động trên **một database** mỗi lần. Nó không tạo một snapshot MVCC toàn cluster bao phủ mọi databases trong cùng một mốc thời gian.

Nếu ứng dụng dùng database A cho orders và database B cho billing, chạy hai lệnh pg_dump tuần tự không đảm bảo cả hai dump đại diện cùng một consistency point. Cần thiết kế phối hợp riêng hoặc thay đổi ranh giới dữ liệu.

### 4.5. Global objects

pg_dump của một database không dump toàn bộ cluster-wide objects như roles và tablespaces. Dùng `pg_dumpall --globals-only` hoặc quy trình quản lý globals riêng:

```bash
pg_dumpall --globals-only > globals.sql
```

Dump globals là một tác vụ riêng, không có cùng một snapshot MVCC xuyên tất cả databases. Cần quản lý thay đổi roles/tablespaces trong backup window nếu cần bộ backup cluster nhất quán về cấu hình/quyền.

### 4.6. Sequences là ngoại lệ quan trọng

Sequence values không tuân theo MVCC transactional semantics như table rows. `nextval` có hiệu lực ngay và không rollback theo transaction. Trong lúc dump, ứng dụng có thể tiếp tục gọi nextval; giá trị sequence được dump không nhất thiết tạo thành một snapshot MVCC hoàn hảo cùng với rows.

Nếu cần đảm bảo trạng thái sequence sau restore không va chạm với keys đã xuất, hãy phối hợp writers/sequence usage hoặc kiểm tra/reconcile sequence values sau restore. Không giả định một transaction REPEATABLE READ đóng băng sequence.

### 4.7. Large Objects

pg_dump có thể dump Large Objects khi được cấu hình/định dạng phù hợp; không chỉ dump OID trong bảng metadata rồi mặc định nội dung LO sẽ có trong archive. Với selective dumps, cần xem tùy chọn `--large-objects` và kiểm tra archive.

### 4.8. Extensions và external dependencies

pg_dump lưu định nghĩa extension theo cơ chế extension, nhưng không tự đóng gói mọi binary/package/OS dependency cần thiết để cài extension trên server đích. Tương tự, file ngoài database, secret, certificates, config và object storage không tự được đưa vào dump.

### 4.10. Serializable deferrable

pg_dump có tùy chọn `--serializable-deferrable` để dùng một transaction SERIALIZABLE, READ ONLY, DEFERRABLE. Transaction có thể chờ tới khi nhận được một safe snapshot thay vì bắt đầu ngay; điều này hữu ích trong một số yêu cầu consistency đặc biệt nhưng có thể làm thời gian bắt đầu dump lâu hơn.

Không cần bật tùy chọn này cho mọi backup. Nó không tạo snapshot xuyên databases, không đóng băng sequence và không thay thế application-level consistency protocol.

### 4.9. Restore không giống chạy dump SQL trong production

Logical dump là tập lệnh/đối tượng để tái tạo database. Khi restore, có thể cần role, tablespace, extension, encoding/collation, owner và quyền phù hợp. Kiểm tra restore trên database đích độc lập.

## 5. Parallel pg_dump và exported snapshot

Dump song song giúp tăng throughput với database lớn. Để nhiều worker connections đọc cùng một trạng thái, chúng cần sử dụng chung snapshot.

### 5.1. Vì sao parallel dump cần snapshot chung?

Nếu mỗi worker lấy snapshot riêng:

- Worker A có thể dump orders trước một transaction mới.
- Worker B có thể dump order_items sau khi transaction đó commit.
- Dump có thể chứa một order_item mà order parent không xuất hiện trong cùng logical state.

Một snapshot chung giúp các worker thấy cùng visibility point, từ đó giữ tính nhất quán giữa các tables.

### 5.2. pg_dump -j

```bash
pg_dump -Fd -j 4 -f app_directory_dump appdb
```

Parallel dump yêu cầu directory format `-Fd` và nhiều connections. pg_dump điều phối snapshot giữa các worker theo cơ chế nội bộ; không cần tự tạo một snapshot cho từng worker.

### 5.3. Export snapshot bằng PostgreSQL

Một session có thể export snapshot bằng `pg_export_snapshot()` trong transaction thích hợp:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

PostgreSQL trả về một snapshot identifier dạng text. Session exporter phải tiếp tục giữ transaction mở trong khi các sessions khác import snapshot đó.

### 5.4. Import snapshot

Trong session consumer:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

-- Thực hiện các SELECT cần cùng snapshot.
SELECT count(*) FROM app.orders;
SELECT count(*) FROM app.order_items;

COMMIT;
```

Thay snapshot identifier bằng giá trị thực do exporter trả về. `SET TRANSACTION SNAPSHOT` phải được gọi trước query đầu tiên của transaction consumer (ngoại trừ các lệnh thiết lập transaction được phép), và isolation level phải là REPEATABLE READ hoặc SERIALIZABLE.

### 5.5. Exporter phải còn mở

Snapshot identifier không phải file hay token tồn tại mãi. Exporter transaction phải còn mở khi consumer import. Khi exporter kết thúc, snapshot đó không còn có thể được import mới.

Consumer đã import snapshot có thể tiếp tục dùng snapshot trong transaction của chính nó sau khi exporter kết thúc, theo semantics PostgreSQL; nhưng không thể dùng identifier cũ để mở thêm consumer mới sau khi exporter đóng.

### 5.6. Snapshot chỉ trong cùng database

Snapshot export/import áp dụng cho connections tới cùng database. Không dùng một snapshot ID để đồng bộ visibility xuyên nhiều databases trong cùng cluster.

### 5.7. pg_dump --snapshot

`pg_dump` có option `--snapshot=snapshot_id` để sử dụng snapshot đã export bởi một session khác. Đây là cơ chế hữu ích khi phối hợp pg_dump với công cụ khác, nhưng session exporter phải duy trì transaction đúng thời gian pg_dump import snapshot.

### 5.8. Snapshot và connection pool

Không để exporter transaction bị trả về pool hoặc commit/rollback trước khi các consumers import xong. Một connection pool có thể tái sử dụng session cho request khác; giữ snapshot exporter cần ownership rõ ràng và timeout để tránh transaction idle kéo dài.

### 5.9. Snapshot exported không phải durable backup

Snapshot ID chỉ mô tả visibility trong các transactions đang sống. Nó không chứa bytes, không thể dùng sau restart để dựng lại database và không thay thế dump/base backup/WAL archive.

## 6. Logical snapshot không phải physical snapshot

Hai cách backup dùng từ “snapshot” nhưng bảo đảm khác nhau.

### 6.1. Logical snapshot

Logical backup đọc rows và schema theo MVCC visibility. Ví dụ `pg_dump` xuất CREATE TABLE, INSERT/COPY data, indexes, constraints, functions và các objects được hỗ trợ.

Đặc điểm:

- Có thể restore vào database mới hoặc PostgreSQL version khác trong phạm vi tương thích.
- Có thể chọn schema/table/database objects.
- Dùng snapshot để các bảng trong một database phản ánh cùng một trạng thái logic.
- Restore cần tái tạo objects và nạp dữ liệu, thường tốn thời gian với database lớn.
- Không tự bao gồm mọi global objects, config và dependencies bên ngoài.

### 6.2. Physical snapshot/backup

Physical backup sao chép data files, WAL cần thiết và các thành phần cluster. Nó không đọc từng row theo một MVCC snapshot như pg_dump. Thay vào đó, backup phải đủ dữ liệu để PostgreSQL **crash-recover** các data files về trạng thái nhất quán bằng WAL.

Đặc điểm:

- Bao phủ cluster vật lý, gồm nhiều databases trong cluster.
- Thường restore nhanh hơn logical dump với database lớn vì sao chép data files.
- Phụ thuộc kiến trúc/major version, platform, tablespaces và cấu hình cluster.
- Cần WAL liên tục từ backup start/redo point để hoàn tất recovery.
- Không dùng như logical export để chọn riêng vài tables.

### 6.3. Crash-consistent storage snapshot

Storage snapshot có thể chụp block devices tại một điểm thời gian. Nếu server đang chạy, snapshot tương tự một ảnh đĩa sau crash: các data pages có thể được ghi ở những thời điểm khác nhau, nhưng WAL recovery có thể đưa chúng về trạng thái nhất quán nếu toàn bộ files/WAL cần thiết được chụp và bảo toàn đúng cách.

Một snapshot storage không tự động là application-consistent. Nhà cung cấp cloud có thể tạo snapshot từng volume ở những thời điểm khác nhau; nếu PGDATA, tablespaces và pg_wal nằm trên nhiều volumes, cần cơ chế snapshot group nhất quán hoặc phối hợp backup API.

### 6.4. Application-consistent snapshot

Application-consistent nghĩa ứng dụng/database được phối hợp để snapshot phản ánh một trạng thái phù hợp với nghiệp vụ. Với PostgreSQL, có thể:

- Dùng pg_dump/pg_basebackup và cơ chế WAL tương ứng.
- Tạm dừng writes hoặc đặt một application barrier trong thời gian cần thiết.
- Dùng backup API khi chụp filesystem/storage snapshots online.
- Đồng bộ thêm các hệ thống bên ngoài theo transaction/barrier.

“Quiesce” application không tự thay thế PostgreSQL backup protocol; vẫn phải bảo đảm data files và WAL hợp lệ.

### 6.5. Tính nhất quán có nhiều tầng

| Tầng | Câu hỏi |
| --- | --- |
| Page/physical | Pages và WAL có thể crash-recover không? |
| Database/MVCC | Các rows được đọc từ cùng snapshot logic không? |
| Cluster | Mọi databases, roles, tablespaces và shared catalogs có trong backup không? |
| Application | Các bảng liên quan có phản ánh một business operation hoàn chỉnh không? |
| Distributed | Các databases/services/files ngoài PostgreSQL có cùng consistency point không? |
| Restore | Bản backup có thực sự khôi phục được và ứng dụng có dùng được không? |

Không nên dùng một chữ “consistent” để khẳng định tất cả các tầng đều đã được giải quyết.

## 7. Online physical backup và backup API

PostgreSQL cho phép tạo physical backup khi server vẫn chạy. Để data files được sao chép an toàn, cần dùng backup protocol và giữ WAL cần thiết.

### 7.1. pg_backup_start và pg_backup_stop

Trên PostgreSQL hiện đại, SQL functions `pg_backup_start` và `pg_backup_stop` tạo một backup window:

```sql
SELECT pg_backup_start(
    'nightly-backup-2026-11-14',
    false
);

-- Copy/snapshot các data files theo backup procedure.

SELECT *
FROM pg_backup_stop(true);
```

Các hàm này là building blocks cho **physical backup**. Chúng không tự copy data directory hay tạo một archive hoàn chỉnh; công cụ backup phải lưu các files và metadata/WAL cần thiết.

### 7.2. Tham số fast

Tham số `fast` của `pg_backup_start(label, fast)` quyết định checkpoint được yêu cầu có thực hiện càng nhanh càng tốt hay trải đều theo checkpoint I/O policy:

- `false`: thường dùng mặc định, checkpoint có thể trải đều writes để giảm I/O burst.
- `true`: yêu cầu checkpoint nhanh hơn, có thể tạo I/O cao hơn.

Chọn theo yêu cầu backup window và storage; không bật fast cho mọi backup mà không đo.

### 7.3. Backup start point và WAL

Backup start ghi nhận điểm WAL cần thiết và đưa cluster vào chế độ backup. Trong thời gian backup, PostgreSQL bảo đảm WAL có thông tin đủ để khôi phục bản copy data files về consistency point phù hợp.

### 7.4. Snapshot/copy data files trong backup window

Một quy trình filesystem snapshot khái niệm:

1. Gọi `pg_backup_start`.
2. Chụp **tất cả** data files/tablespaces liên quan tại một consistency point.
3. Gọi `pg_backup_stop`.
4. Lưu backup label/tablespace map metadata do API trả về theo yêu cầu phiên bản.
5. Bảo đảm WAL từ backup start tới backup stop được đưa vào backup hoặc archive và có thể truy xuất khi restore.

Không chỉ copy thư mục `base` rồi coi là backup đầy đủ; còn có global catalogs, WAL, tablespaces và metadata cần thiết.

### 7.5. Backup label và tablespace map

Backup procedure có thể cần file `backup_label` ở root của backup và `tablespace_map` khi có tablespaces. Với API non-exclusive hiện đại, `pg_backup_stop` trả nội dung metadata để công cụ backup ghi đúng vị trí. `pg_basebackup` xử lý các metadata này tự động.

Không tự tạo backup_label bằng cách đoán LSN/timestamp; dùng nội dung chính xác do PostgreSQL trả về.

### 7.6. Đảm bảo WAL liên tục

Data files của backup có thể phản ánh các page ở thời điểm khác nhau. WAL từ backup start tới backup stop giúp redo/hoàn tất consistency. Nếu thiếu segment cần thiết, physical backup có thể không khởi động được.

WAL có thể được lấy qua archive hoặc streaming theo cách công cụ backup hỗ trợ. Chỉ giữ file data snapshot mà không có WAL cần thiết là chưa đủ.

### 7.7. Phiên bản cũ

Tên backup functions và semantics đã thay đổi qua các PostgreSQL majors. Các phiên bản cũ dùng `pg_start_backup`/`pg_stop_backup` (có biến thể exclusive/non-exclusive theo version); PostgreSQL hiện đại dùng `pg_backup_start`/`pg_backup_stop`. Luôn theo đúng tài liệu major đang chạy, không trộn procedure từ hai phiên bản.

### 7.8. Không để backup mode mở vô thời hạn

Nếu gọi backup start nhưng không gọi stop đúng cách, backup state có thể kéo dài, giữ WAL và làm tăng disk usage. Dùng công cụ quản lý backup có cleanup/error handling và alert khi backup window bất thường.

## 8. pg_basebackup tạo physical backup nhất quán

`pg_basebackup` là công cụ chuẩn để tạo base backup từ một PostgreSQL server. Nó dùng replication protocol và backup mechanisms thay cho việc người dùng tự copy files tùy tiện.

### 8.1. Ví dụ tạo backup dạng directory

```bash
pg_basebackup \
  -h db-primary.example.net \
  -p 5432 \
  -U replication_backup \
  -D /backup/pg/base-2026-11-14 \
  -F plain \
  -X stream \
  -P
```

Ví dụ cần role có quyền replication và cấu hình kết nối phù hợp. Bảo vệ password bằng passfile/secret manager, không đặt mật khẩu trực tiếp trong command line hoặc shell history.

### 8.2. WAL methods

`pg_basebackup` có các lựa chọn WAL:

- `-X stream`: stream WAL cần thiết đồng thời với quá trình backup qua replication connection bổ sung.
- `-X fetch`: lấy WAL cần thiết sau khi copy data; các segments phải còn sẵn cho tới khi fetch hoàn tất.
- `-X none`: không lấy WAL vào backup; cần bảo đảm WAL cần thiết có thể lấy từ archive/nguồn khác.

Với backup độc lập dễ phục hồi, `-X stream` thường là lựa chọn đơn giản; nhưng chọn theo capacity/network và kiến trúc archive thực tế.

### 8.3. Format

- `-F plain`: tạo cây data directory.
- `-F tar`: tạo tar archives.

Tùy format, tablespaces có thể được đặt ở vị trí khác; kiểm tra các options liên quan và metadata backup.

### 8.4. Backup manifest và checksum

Các PostgreSQL majors hiện đại hỗ trợ backup manifest để liệt kê files và checksum. Có thể dùng `pg_verifybackup` để kiểm tra backup manifest/checksums và một số điều kiện backup:

```bash
pg_verifybackup /backup/pg/base-2026-11-14
```

Verification không thay thế restore test. Một backup có manifest hợp lệ vẫn có thể không khởi động được vì thiếu WAL archive, cấu hình, extension binaries hoặc dependency bên ngoài.

### 8.5. Backup từ standby

`pg_basebackup` có thể lấy backup từ standby trong các cấu hình được hỗ trợ. Cần xem giới hạn theo major, trạng thái standby, WAL receiver và các yêu cầu WAL. Một số thống kê/backup labels có thể khác so với lấy từ primary; test restore.

### 8.6. Không chạy pg_basebackup vào PGDATA đang hoạt động

`-D` phải là thư mục backup đích thích hợp. Không trỏ vào data directory đang phục vụ của server hoặc ghi đè một backup đang dùng. Tách rõ nguồn và đích.

### 8.7. Kiểm tra kết quả

Sau backup:

- Kiểm tra exit code và log.
- Kiểm tra backup manifest nếu có.
- Kiểm tra đủ tablespaces.
- Kiểm tra WAL included/available.
- Chạy `pg_verifybackup` khi phù hợp.
- Thử restore vào một cluster độc lập.

### 8.8. Backup không phải restore

`pg_basebackup` hoàn tất thành công chứng minh quy trình copy đã hoàn thành theo giao thức; nó không chứng minh server đích có thể start, app có quyền, archive WAL đầy đủ hoặc RTO đạt mục tiêu. Restore drill mới xác nhận điều đó.

## 9. Storage snapshots trên nhiều volumes và tablespaces

Một cluster PostgreSQL có thể lưu data files ở nhiều vị trí:

- PGDATA chứa control files, system catalogs và phần lớn database files.
- Tablespaces có thể nằm trên các filesystem/volume khác.
- `pg_wal` có thể được đặt riêng bằng symlink.
- Configuration/log files có thể ở vị trí ngoài PGDATA.

Một storage snapshot chỉ chụp một volume không tự động bao phủ toàn bộ cluster.

### 9.1. Tablespace là gì?

Tablespace cho phép đặt database objects trên storage location khác với default data directory. Catalog `pg_tablespace` giữ metadata tablespace; thư mục `pg_tblspc` trong PGDATA có symlinks tới các vị trí vật lý.

```sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
```

Để physical backup đầy đủ, phải bảo đảm các tablespace directories được copy/snapshot cùng backup set và được restore đúng vị trí hoặc map lại theo công cụ.

### 9.2. Nhiều volume phải có consistency point chung

Giả sử:

```text
Volume A: PGDATA/base
Volume B: tablespace chứa index
Volume C: pg_wal

Snapshot A lúc 10:00:00.000
Snapshot B lúc 10:00:00.300
Snapshot C lúc 10:00:00.700

Các snapshots không cùng một thời điểm logic.
```

Nếu storage provider không hỗ trợ atomic consistency group, những volume này có thể phản ánh các trạng thái khác nhau. PostgreSQL backup protocol và WAL có thể hỗ trợ recovery, nhưng quy trình phải được thiết kế và kiểm thử theo cách các volume được chụp; không tự giả định snapshot từng volume độc lập là tương đương một snapshot toàn cluster.

### 9.3. Phối hợp filesystem snapshot online

Quy trình khái niệm:

1. Xác định PGDATA, tất cả tablespace paths và WAL location.
2. Gọi `pg_backup_start` trên primary.
3. Yêu cầu storage provider tạo **consistent group snapshot** cho tất cả volumes chứa data/tablespaces/WAL liên quan.
4. Xác nhận snapshot đã hoàn tất và có thể mount/clone.
5. Gọi `pg_backup_stop` và lưu backup label/tablespace map theo version.
6. Bảo đảm WAL cần thiết từ backup start tới backup stop được archive/giữ lại.
7. Ghi metadata backup: LSN, timeline, snapshot IDs, tablespace mappings, PostgreSQL version và thời gian.

Trình tự chi tiết phải khớp tài liệu của PostgreSQL major và storage provider. Nếu snapshot tool chỉ tạo crash-consistent snapshot chứ không hỗ trợ group consistency, cần thêm cơ chế phối hợp/đóng băng hoặc dùng công cụ backup chuẩn.

### 9.4. Snapshot pg_wal riêng

Nếu `pg_wal` nằm trên volume riêng, phải hiểu nó tương tác thế nào với data volumes và archive. Một snapshot data-only không đủ nếu backup procedure yêu cầu WAL local; có thể lấy WAL qua archive/streaming thay vì copy volume, nhưng phải bảo đảm segment start/end cần thiết tồn tại và liên tục.

Không copy một vài file WAL tùy ý vào backup rồi coi đó là chuỗi hoàn chỉnh. Ghi nhận start LSN, stop LSN, timeline và kiểm tra archive.

### 9.5. Tablespace mapping khi restore

Nếu đường dẫn tablespace trên server đích khác server nguồn, dùng mapping options của công cụ restore/backup phù hợp. Không tạo symlink thủ công trỏ vào volume không có dữ liệu. Kiểm tra quyền OS user PostgreSQL và mount order trước khi start server.

### 9.6. External configuration

Các file cấu hình có thể nằm ngoài PGDATA (ví dụ `postgresql.conf`, `pg_hba.conf`, SSL certificates, include files). Backup vật lý của data directory không nhất thiết chứa tất cả các file này. Quản lý cấu hình bằng configuration management và backup riêng, ghi lại phiên bản/các secrets theo chính sách bảo mật.

### 9.7. Restore phải giữ nguyên ranh giới volume

Trước khi start restored cluster:

- Mount đủ volumes đúng paths.
- Tablespace directories tồn tại và có owner/permissions đúng.
- Symlinks không trỏ tới data directory cũ.
- WAL/archive path truy cập được.
- Config và extension libraries tương thích.
- Không có process PostgreSQL khác đang dùng cùng data directory.

## 10. Tính nhất quán toàn bộ dữ liệu trong một database

Một MVCC snapshot đảm bảo các table reads trong một database nhìn thấy cùng visibility point. Nhưng tính nhất quán nghiệp vụ còn phụ thuộc cách ứng dụng ghi dữ liệu.

### 10.1. Transaction atomic tạo consistency giữa nhiều bảng

Giả sử một đơn hàng tạo row trong orders và order_items:

```sql
BEGIN;

INSERT INTO app.orders(order_id, customer_id, total_amount)
VALUES (1001, 7, 250.00);

INSERT INTO app.order_items(order_id, product_id, quantity)
VALUES
    (1001, 21, 1),
    (1001, 22, 2);

COMMIT;
```

Snapshot trước COMMIT không thấy các thay đổi này; snapshot sau COMMIT thấy toàn bộ transaction. Nó không thấy chỉ row orders mà thiếu order_items của cùng transaction.

### 10.2. Snapshot không sửa được business workflow nhiều transactions

Nếu ứng dụng tạo order ở transaction A, sau đó vài giây mới tạo payment ở transaction B, một snapshot được lấy giữa hai transactions có thể thấy order ở trạng thái chưa thanh toán. Đó có thể là một trạng thái nghiệp vụ hợp lệ nếu workflow định nghĩa pending payment; hoặc có thể là trạng thái cần phối hợp nếu backup yêu cầu chỉ lấy các đơn đã hoàn tất.

MVCC bảo đảm atomicity của từng transaction, không gộp nhiều transactions độc lập thành một business transaction.

### 10.3. Snapshot boundary và business barrier

Nếu cần backup chỉ sau khi mọi workflow đã hoàn tất một giai đoạn:

1. Ứng dụng phát tín hiệu bắt đầu backup window.
2. Ngừng nhận các loại operations mới hoặc chuyển chúng sang queue.
3. Chờ in-flight transactions/workflows đạt trạng thái an toàn.
4. Ghi một barrier/epoch ID trong database.
5. Tạo snapshot/backup và lưu barrier ID cùng backup metadata.
6. Tiếp tục nhận operations.

Barrier phải được thiết kế để các writers không thể lọt qua mà không được đánh dấu; chỉ sleep vài giây không tạo được consistency guarantee.

### 10.4. Snapshot và foreign keys

Một snapshot MVCC sẽ đọc các versions theo visibility. Nếu transaction đã COMMIT một thay đổi có FK, snapshot thấy transaction như một đơn vị. Nhưng nếu FK bị disable, dữ liệu được ghi ngoài transaction hoặc application logic không dùng constraints, snapshot không tự sửa những vi phạm nghiệp vụ đã tồn tại.

### 10.5. Deferred constraints

Constraint DEFERRABLE có thể được kiểm tra tại COMMIT. Snapshot không thấy một transaction chưa COMMIT; do đó không thể nhìn thấy trạng thái trung gian mà transaction đang tạm thời vi phạm deferred constraint. Đây là một lý do transaction boundary quan trọng với logical backup.

### 10.6. Materialized views

Materialized view lưu dữ liệu đã materialize. Logical dump có thể lưu định nghĩa và nội dung theo lựa chọn dump; physical backup lưu data files của nó. Nếu materialized view đã stale trước backup, snapshot nhất quán vẫn có thể chứa dữ liệu stale. Backup consistency không đồng nghĩa freshness của cache/reporting data.

### 10.7. Unlogged tables

Unlogged tables không ghi WAL theo cách như logged tables và nội dung có thể bị truncate sau crash/recovery; chúng cũng không được replicate tới standby như bảng logged thông thường. Nếu dữ liệu trong unlogged table là dữ liệu cần khôi phục bền vững, hãy đổi sang logged table hoặc thiết kế tái tạo dữ liệu từ nguồn khác.

## 11. Nhiều databases và nhiều hệ thống bên ngoài

Snapshot export/import của PostgreSQL có phạm vi một database. Một cluster physical backup có thể bao phủ tất cả databases trong cluster tại một physical consistency point, nhưng logical dumps riêng lẻ không có một MVCC snapshot chung xuyên databases.

### 11.1. Nhiều databases trong một cluster

PostgreSQL connection kết nối tới một database cụ thể. Không thể dùng một exported MVCC snapshot của database A để import vào connection database B.

Nếu chạy:

```bash
pg_dump -Fc -f orders.dump orders_db
pg_dump -Fc -f billing.dump billing_db
```

hai dump có thể được tạo ở hai thời điểm khác nhau. Nếu có dữ liệu tham chiếu chéo qua application logic, chúng có thể không tương ứng cùng một business state.

### 11.2. Physical backup bao phủ cluster

Physical base backup của một cluster bao phủ các database files trong cluster, shared catalogs và WAL cần thiết để khôi phục physical state. Đây là cách phù hợp khi cần một consistency point vật lý toàn cluster, với điều kiện tất cả tablespaces/WAL liên quan được bao gồm.

### 11.3. Cross-database business transaction

Một ứng dụng kết nối tới database A và B rồi thực hiện hai commits độc lập không có atomic transaction chung chỉ vì hai database nằm trong cùng PostgreSQL cluster. Nếu cần atomicity, cần dùng kiến trúc phù hợp (ví dụ distributed transaction/2PC với vận hành và recovery tương ứng) hoặc mô hình saga/outbox với trạng thái bền vững.

### 11.4. Microservices và nhiều clusters

Một snapshot PostgreSQL không thể tự đồng bộ:

- Database của service khác.
- Kafka/Pulsar offsets.
- Redis/cache.
- Object storage.
- File system hoặc document store.
- Payment/email provider.

Cần xác định một **global consistency point** bằng barrier, event offsets, CDC positions, coordinated checkpoint hoặc quiesce workflow. Chỉ lưu timestamp của từng backup không chứng minh chúng có cùng trạng thái.

### 11.5. Event stream và database snapshot

Nếu database được cập nhật từ event stream, backup metadata có thể ghi:

- Database snapshot/backup LSN.
- Consumer group offsets.
- Source partition offsets.
- CDC replication slot/consistent point.
- Application epoch/barrier ID.

Khi restore, cần biết replay event từ offset nào để tránh bỏ sót hoặc áp dụng trùng events so với trạng thái đã được materialize trong database.

### 11.6. Object storage/file bên ngoài

Nếu database row chứa object key, một snapshot DB chỉ giữ key và metadata; nó không snapshot bytes trong bucket. Nếu object bị thay/xóa sau snapshot, restored database có thể trỏ tới object không còn hoặc có version khác.

Giải pháp có thể gồm:

- Object versioning và lưu version ID trong DB.
- Backup bucket theo cùng retention window.
- Upload staging rồi publish immutable object key.
- Snapshot/manifest object list và checksum tại consistency point.
- Cleanup chỉ sau khi mọi DB backups tham chiếu object cũ hết retention.

### 11.7. Hai-phase commit không tự backup external resource

2PC có thể phối hợp commit giữa resource managers hỗ trợ protocol, nhưng không biến một object store hay HTTP API thông thường thành transactional participant. Với hệ thống không hỗ trợ 2PC, dùng outbox/saga và backup barrier.

## 12. Sequence state và các ngoại lệ của snapshot

Sequence là một nguồn bất ngờ khi cần snapshot “toàn bộ dữ liệu”.

### 12.1. nextval không rollback

`nextval` cấp giá trị sequence ngay; transaction rollback không trả lại giá trị đã cấp. Điều này tránh khóa và đảm bảo cấp phát hiệu quả, nhưng sequence không có MVCC visibility như rows.

### 12.2. Sequence có thể tiến trong lúc pg_dump

Ứng dụng có thể gọi `nextval` trong khi pg_dump đang chạy. Dump table rows và dump sequence state không nhất thiết là một snapshot MVCC đồng bộ. Sau restore, sequence có thể cần được reconcile để giá trị tiếp theo lớn hơn các keys đã tồn tại.

### 12.3. Kiểm tra sequence sau restore

Ví dụ với một table có serial/identity:

```sql
SELECT max(id) AS max_id
FROM app.orders;

SELECT last_value, is_called
FROM app.orders_id_seq;
```

Tên sequence thực tế có thể khác. Chỉ chạy `setval` trong maintenance window sau khi xác định đúng sequence, quyền sở hữu và concurrency; không reset sequence trong khi writers vẫn cấp số mới.

### 12.4. Reconcile sequence

Một pattern sau restore (đã dừng writers và xác định sequence đúng):

```sql
SELECT setval(
    'app.orders_id_seq',
    COALESCE((SELECT max(id) FROM app.orders), 1),
    EXISTS (SELECT 1 FROM app.orders)
);
```

Khi bảng rỗng, `is_called=false` khiến lần nextval kế tiếp trả start value theo sequence semantics. Với sequence có increment/start/minvalue tùy chỉnh, kiểm tra kỹ trước khi dùng pattern này.

### 12.5. Identity columns

Identity columns cũng dựa trên sequence. Đừng nghĩ `GENERATED ALWAYS AS IDENTITY` làm sequence state transactional hoặc tự đồng bộ hoàn hảo với concurrent dump.

### 12.6. Large Objects và external references

Large Objects có nội dung riêng và cần được đưa vào backup/dump phù hợp; OID trong row không tự chứa file. Nếu application lưu OID ở JSON/text/custom format, tool dump/cleanup không nhất thiết nhận diện references như cột oid.

## 13. Những thành phần không tự động được bao phủ bởi một snapshot

| Thành phần | Logical pg_dump database | Physical base backup |
| --- | --- | --- |
| Table rows/schema trong database | Có, theo dump options/snapshot. | Có trong data files. |
| Indexes/constraints/functions | Theo objects được dump. | Có trong data files/catalogs. |
| Large Objects | Có khi được include theo options/format. | Có trong physical data files. |
| Roles/global privileges | Không; dump globals riêng. | Shared catalogs trong cluster, nhưng config/identity môi trường vẫn cần quản lý. |
| Tablespace definitions/data | Tablespace definitions/global objects cần quản lý riêng; dump không tự copy data directory vật lý. | Data của tablespaces phải được backup đầy đủ. |
| Sequence state | Có dump sequence state nhưng không phải MVCC snapshot thuần. | Có trong data files/WAL recovery. |
| PostgreSQL config files | Không. | Không nhất thiết nếu nằm ngoài PGDATA. |
| Extension binaries/OS packages | Không. | Không nhất thiết; cần cài tương thích trên host. |
| Object storage/file share | Không. | Không. |
| Kafka/CDC offsets | Không tự động. | Không tự động. |
| Other databases in cluster | Không trong một pg_dump database. | Có trong physical cluster backup. |
| Other PostgreSQL clusters | Không. | Không. |
| Secrets/certificates | Không. | Không nhất thiết; quản lý riêng. |
| Temporary tables/sessions | Không phải dữ liệu persistent cần restore. | Không khôi phục như objects persistent thông thường. |

Đây là bảng khái quát; options, PostgreSQL major, extension và công cụ backup có thể làm thay đổi phạm vi cụ thể. Luôn kiểm tra backup manifest và restore thực tế.

## 14. Snapshot dài hạn, VACUUM và tác động tới hệ thống

Một backup giữ snapshot trong thời gian dài có thể làm thay đổi khả năng thu hồi dead tuples.

### 14.1. Vì sao VACUUM cần biết snapshot cũ nhất?

MVCC phải giữ row versions cũ nếu còn transaction có thể nhìn thấy chúng. Một transaction backup REPEATABLE READ kéo dài có thể giữ xmin horizon cũ, khiến VACUUM không thể loại bỏ nhiều dead tuples.

Hệ quả:

- Heap/index bloat tăng.
- Disk usage tăng.
- Autovacuum phải làm việc nhiều hơn sau khi snapshot kết thúc.
- Một số bảng có thể gần transaction ID wraparound nếu vacuum bị giữ lại quá lâu.

### 14.2. Quan sát transaction giữ snapshot

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    backend_xmin,
    age(backend_xid) AS xid_age,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

`backend_xmin` có thể cho biết backend giữ snapshot horizon. Quyền hiển thị query/metadata tùy role và cấu hình. Không kill transaction chỉ vì nó lâu; xác định đó là backup, report, logical replication hoặc transaction nghiệp vụ.

### 14.3. idle in transaction

Một session bắt đầu REPEATABLE READ, export snapshot rồi chờ file copy/network lâu có thể ở trạng thái idle in transaction. Đây là rủi ro vì giữ snapshot/transaction resources.

Giải pháp:

- Giữ exporter transaction chỉ lâu đủ để consumers import snapshot.
- Không dùng transaction DB làm nơi chờ người dùng upload/download.
- Có timeout/monitor cho backup orchestration.
- Đảm bảo cleanup/rollback exporter nếu consumer thất bại.

### 14.4. Snapshot exported và vòng đời exporter

Nếu exporter đóng quá sớm, consumer chưa import sẽ không thể dùng snapshot. Nếu exporter mở quá lâu, VACUUM có thể bị giữ lại. Cần cân bằng hai yêu cầu bằng orchestration có deadline và xác nhận worker import thành công.

### 14.5. Backup trên hot standby

Logical dump từ standby có thể bị ảnh hưởng bởi recovery conflicts khi WAL replay cần loại bỏ row versions mà query backup vẫn đang đọc. Query có thể bị cancel theo hot standby conflict settings.

`hot_standby_feedback` có thể giảm một số cancellations bằng cách gửi feedback tới primary để giữ dead tuples cần thiết, nhưng đổi lại có thể gây bloat trên primary. Không bật mà không đo tác động.

### 14.6. Snapshot không thể kéo dài vô hạn

Backup phải có SLA, timeout và cảnh báo. Một snapshot sống nhiều giờ/ngày có thể gây retention pressure và làm hệ thống vận hành xấu đi dù dump cuối cùng thành công.

## 15. Thiết kế consistency point cho toàn ứng dụng

Khi dữ liệu nằm trong một database và mọi nghiệp vụ quan trọng commit trong transaction, MVCC snapshot thường là đủ. Khi dữ liệu trải qua nhiều transactions, databases hoặc external systems, cần một coordination protocol.

### 15.1. Ghi backup epoch/barrier

Ứng dụng có thể lưu một epoch ID:

```sql
CREATE TABLE ops.backup_epochs (
    epoch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status text NOT NULL,
    barrier_created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    snapshot_lsn pg_lsn,
    notes text
);
```

Barrier chỉ có ý nghĩa nếu mọi writers tuân thủ protocol. Một row barrier không tự ngăn transactions khác ghi dữ liệu không phối hợp.

### 15.2. Application quiesce

Một quy trình quiesce có thể:

1. Chuyển API sang maintenance/read-only hoặc queue writes.
2. Đợi in-flight transactions kết thúc.
3. Đợi các multi-step workflows đạt checkpoint nghiệp vụ.
4. Ghi barrier/epoch vào DB.
5. Tạo snapshot/backup.
6. Ghi LSN/snapshot metadata và mở writes trở lại.

Thời gian quiesce cần nằm trong RTO/RPO/availability budget.

### 15.3. Queue và event offsets

Nếu workers consume message rồi cập nhật DB, snapshot DB phải liên hệ với offsets:

```text
Message partition P:
  offset 1000 -> DB transaction commit
  offset 1001 -> đang xử lý
  offset 1002 -> chưa nhận

Backup consistency point:
  DB state bao gồm offset 1000
  consumer offset được lưu/đồng bộ tương ứng
  sau restore, resume từ offset 1001
```

Nếu offset đã commit trước DB state hoặc ngược lại, có thể bỏ sót hoặc áp dụng trùng events. Cần lưu offset cùng DB transaction hoặc dùng inbox/outbox protocol.

### 15.4. CDC và replication slots

Khi dùng logical decoding/CDC, snapshot consistent point cần phối hợp với replication slot/consistent LSN. Pipeline thường cần một initial snapshot và WAL stream bắt đầu tại LSN liên quan để không bỏ sót thay đổi giữa lúc snapshot và streaming.

Không chỉ ghi lại “dump bắt đầu lúc 10:00” rồi giả định CDC từ 10:00 không có gap. LSN là mốc chính xác hơn timestamp; vẫn cần protocol của connector để ghép snapshot và WAL.

### 15.5. Cross-database snapshot

PostgreSQL không cung cấp một exported MVCC snapshot có thể import đồng thời qua các databases độc lập. Các lựa chọn:

- Dùng physical cluster backup nếu mục tiêu là một cluster vật lý.
- Đưa dữ liệu cần atomicity vào cùng database/transaction boundary.
- Dừng writers ở một barrier chung rồi dump từng database.
- Dùng application-level epoch và reconciliation khi restore.

### 15.6. External object store

Một protocol an toàn cho file:

1. Upload object dưới key immutable/staging.
2. Tính checksum và size, xác minh object tồn tại.
3. Commit DB metadata trỏ tới object version cụ thể.
4. Backup DB cùng manifest/version inventory của bucket.
5. Không xóa object cũ cho tới khi mọi backup tham chiếu nó hết retention.

Object version ID quan trọng hơn một key mutable có thể bị overwrite sau backup.

### 15.7. Saga và business consistency

Nếu nghiệp vụ nhiều services dùng saga, snapshot có thể phản ánh saga đang ở trạng thái giữa các bước. Điều này không nhất thiết sai nếu state machine được lưu đầy đủ và có thể tiếp tục/compensate sau restore. Nếu backup yêu cầu chỉ lấy sagas terminal, phải đặt barrier và kiểm tra pending workflows.

## 16. Backup metadata và consistency manifest

Một backup tốt nên có manifest mô tả trạng thái và phạm vi của nó.

### 16.1. Trường metadata đề xuất

| Trường | Ý nghĩa |
| --- | --- |
| backup_id | ID duy nhất của backup set. |
| backup_type | logical dump, physical base backup, storage snapshot, PITR anchor. |
| started_at/finished_at | Thời điểm theo timezone chuẩn. |
| server_version | PostgreSQL major/minor và tool versions. |
| system_identifier | Định danh cluster cho physical backup. |
| timeline | Timeline của WAL stream. |
| start_lsn/stop_lsn | WAL range liên quan nếu backup type cung cấp. |
| database_list | Databases được bao phủ. |
| tablespace_map | Paths/IDs của tablespaces. |
| snapshot_ids | Storage provider snapshot IDs/consistency group. |
| wal_archive_range | Segments/LSNs cần để phục hồi. |
| globals_backup | Roles/tablespaces/config globals có được backup không. |
| app_epoch | Business barrier ID nếu có. |
| external_manifest | Object versions/event offsets/other system checkpoints. |
| checksum/manifest | Integrity data cho backup artifacts. |
| retention_until | Thời điểm sớm nhất được phép purge. |
| restore_test_id | Kết quả lần restore drill gần nhất. |

### 16.2. Không chỉ lưu timestamp

Timestamp không đủ để chứng minh hai backups cùng consistency point. Clock skew, timezone, transaction latency và asynchronous replication khiến thời gian wall-clock không thể thay thế LSN/snapshot ID/epoch.

### 16.3. LSN không phải global transaction ID

LSN là vị trí WAL trong một timeline/cluster. Nó không tự so sánh trực tiếp với LSN của một cluster khác sau clone/reseed/timeline fork. Manifest cần system identifier và timeline để diễn giải LSN đúng ngữ cảnh.

### 16.4. Kiểm tra completeness

Một manifest nên trả lời:

- Những database nào được backup?
- Tablespace nào được copy?
- WAL range nào cần có?
- Snapshot storage nào được tạo cùng nhau?
- Roles/extensions/config nào cần phục hồi?
- External objects/offsets nào được liên kết?
- Restore test gần nhất có thành công không?

## 17. Quy trình backup và restore mẫu

### 17.1. Logical backup một database

```bash
pg_dump -Fc -f appdb-2026-11-14.dump appdb
pg_dumpall --globals-only > globals-2026-11-14.sql
```

Hai lệnh có phạm vi khác nhau. Lệnh đầu dump một database; lệnh thứ hai dump global objects. Nếu cần consistency xuyên nhiều databases, không giả định hai bước này có chung snapshot.

### 17.2. Parallel logical backup

```bash
pg_dump -Fd -j 4 -f appdb-directory appdb
```

Parallel dump dùng directory format. pg_dump điều phối snapshot giữa workers.

### 17.3. Dùng exported snapshot với pg_dump

Session A:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot();
```

Giữ transaction mở và copy snapshot ID trả về. Trong shell, chạy:

```bash
pg_dump --snapshot='00000003-0000001B-1' -Fc \
  -f appdb-consistent.dump appdb
```

Sau khi pg_dump đã import snapshot và hoàn tất công việc, kết thúc Session A:

```sql
COMMIT;
```

Snapshot ID chỉ là ví dụ; thay bằng ID thật. Không commit exporter trước khi pg_dump import snapshot. Kiểm tra version/tool options nếu dùng parallel dump hoặc nhiều workers.

### 17.4. Physical backup bằng pg_basebackup

```bash
pg_basebackup \
  -h db-primary.example.net \
  -U replication_backup \
  -D /backup/pg/base-current \
  -F plain \
  -X stream \
  -P
```

Lưu output/log và backup manifest. Nếu cần PITR, cấu hình WAL archive liên tục ngoài base backup.

### 17.5. Kiểm tra backup

```bash
pg_verifybackup /backup/pg/base-current
```

Chỉ chạy nếu backup format/version có manifest và tool hỗ trợ. Với logical dump, kiểm tra archive list:

```bash
pg_restore --list appdb-2026-11-14.dump
```

Đây là bước kiểm tra artifact, chưa thay restore drill.

### 17.6. Restore logical dump

```bash
createdb restored_appdb
pg_restore -d restored_appdb appdb-2026-11-14.dump
```

Tạo roles/globals và extension dependencies theo thứ tự phù hợp. Kiểm tra owner/privileges và data consistency.

### 17.7. Restore physical backup

Quy trình physical restore phụ thuộc format và PostgreSQL major:

1. Chuẩn bị host/data directory và tablespace paths.
2. Khôi phục base backup.
3. Cấu hình archive/restore command và recovery target nếu cần.
4. Cung cấp WAL cần thiết và timeline history.
5. Start PostgreSQL vào crash/archive recovery.
6. Chờ recovery hoàn tất hoặc pause tại target.
7. Kiểm tra database và application trước khi mở traffic.

Không start đồng thời hai server dùng cùng physical data directory.

### 17.8. Restore không có WAL

Một physical backup online có thể cần WAL từ backup start tới stop. Nếu không có WAL đó, backup có thể không hoàn tất recovery. Không được xóa WAL archive vì nghĩ “đã có base backup”; retention policy phải bảo đảm chuỗi WAL liên tục.

## 18. Snapshot, PITR và consistency point

Point-in-Time Recovery (PITR) không phải khôi phục một snapshot MVCC đã export. PITR dùng base backup và WAL để dựng lại trạng thái database tại một target.

### 18.1. Base backup là điểm neo

Base backup cung cấp data files nhất quán sau recovery. WAL liên tục sau backup cho phép tiến tới target time/LSN. Nếu base backup cũ, lượng WAL phải replay và thời gian restore có thể tăng.

### 18.2. Backup label và start/stop LSN

Backup metadata cho biết WAL range cần thiết để recovery. Lưu chính xác start/stop LSN, timeline và label. Không dùng timestamp thay thế hoàn toàn các LSN này.

### 18.3. WAL archive continuity

Để PITR thành công, phải có mọi WAL segment cần thiết từ base backup tới recovery target (cùng timeline/history). Một segment thiếu ở giữa có thể làm recovery dừng, dù archive có nhiều segment mới hơn.

### 18.4. Recovery target

PostgreSQL có thể dừng recovery theo thời gian, LSN, transaction ID hoặc named restore point tùy version:

```conf
restore_command = 'cp /archive/%f %p'
recovery_target_time = '2026-11-14 10:15:00+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

Đây là cấu hình minh họa. Đường dẫn archive, timezone, timeline và target phải được kiểm tra trên bản restore thử nghiệm. Không copy thẳng vào production.

### 18.5. Snapshot không thay thế WAL archive

Storage snapshot của một thời điểm chỉ cho một trạng thái data volume. Nếu cần phục hồi tới thời điểm sau snapshot hoặc trước một lỗi logic, phải có WAL/backup chain phù hợp. Snapshot không cung cấp mọi trạng thái ở giữa hai lần snapshot.

### 18.6. Restore tới một điểm trước lỗi logic

Ví dụ người dùng xóa nhầm một bảng lúc 10:20. Để PITR tới 10:19:59:

1. Chọn base backup có trước 10:20.
2. Xác minh WAL archive liên tục tới target.
3. Restore vào cluster tách biệt.
4. Cấu hình recovery target trước thao tác DROP.
5. Start recovery và pause/promote theo runbook.
6. Xác minh dữ liệu rồi trích xuất/đưa dữ liệu cần thiết về hệ thống.

Không ghi đè primary hiện tại trước khi xác minh restore.

### 18.7. Timeline và failover

Sau promote/failover, timeline mới có thể phân nhánh từ timeline cũ. Archive phải lưu history files và WAL đúng nhánh. Một target time không đủ nếu chọn sai timeline; lưu timeline trong backup manifest.

## 19. RPO, RTO và consistency requirements

### 19.1. RPO

**Recovery Point Objective** là lượng dữ liệu tối đa tổ chức chấp nhận mất sau sự cố, thường biểu diễn thành thời gian. RPO 5 phút có nghĩa chiến lược backup/replication phải bảo đảm có thể khôi phục tới một điểm không cũ hơn khoảng 5 phút so với thời điểm sự cố (theo định nghĩa cụ thể của tổ chức).

RPO phụ thuộc:

- WAL flush/durability settings.
- WAL archive frequency và archive success.
- Base backup age.
- Synchronous/asynchronous replication và failover policy.
- External object/event/offset consistency.

MVCC snapshot tự nó không quyết định RPO.

### 19.2. RTO

**Recovery Time Objective** là thời gian tối đa để khôi phục dịch vụ sau sự cố. RTO bao gồm:

```text
Phát hiện sự cố
  + quyết định restore/failover
  + chuẩn bị host/storage
  + restore base backup hoặc promote standby
  + replay WAL
  + kiểm tra database/application
  + mở traffic
```

Một backup nhanh tạo ra chưa chắc restore nhanh. Phải đo toàn bộ quy trình.

### 19.3. Consistency point khác backup timestamp

Backup bắt đầu lúc 01:00 và kết thúc lúc 01:20 không có nghĩa snapshot logic đại diện 01:10. Với pg_dump, snapshot visibility được xác lập khi transaction lấy snapshot. Với physical backup, backup start/stop LSN và WAL xác định recovery semantics. Với storage group snapshot, snapshot IDs và thời điểm tạo cần được phối hợp với backup API.

### 19.4. RPO cho multi-system

Nếu DB commit order 1000 và Kafka offset 1000 nhưng backup DB và offset snapshot không đồng bộ, restore có thể replay event đã được áp dụng hoặc bỏ qua event chưa được áp dụng. RPO của một hệ thống phân tán phải xét cả các systems và offsets, không chỉ PostgreSQL.

### 19.5. RTO cho restore logical và physical

Logical dump thường cần tạo schema, indexes và load rows; có thể chậm với database lớn nhưng linh hoạt. Physical backup thường copy/restore data files nhanh hơn, nhưng vẫn cần WAL replay, version/platform compatibility và startup. Chọn theo mục tiêu RTO thực nghiệm.

### 19.6. Backup frequency không phải snapshot consistency

Backup mỗi 5 phút không tự bảo đảm RPO 5 phút nếu archive bị lỗi hoặc backup không restore được. Ngược lại, WAL archiving liên tục có thể cho PITR granularity nhỏ giữa các base backups nếu archive chain đầy đủ.

## 20. Kiểm chứng consistency sau backup/restore

Backup job exit code 0 là một tín hiệu cần thiết nhưng chưa đủ. Phải xác minh nội dung và khả năng dùng.

### 20.1. Integrity checks

- Verify backup manifest/checksum nếu công cụ hỗ trợ.
- Kiểm tra file count/size và WAL segments.
- So sánh checksum các external objects.
- Xác nhận tablespace map, system identifier và timeline.
- Lưu log/exit code của từng bước.

### 20.2. Database consistency checks

Sau restore, chạy các truy vấn nghiệp vụ:

```sql
-- Ví dụ: không có order item mồ côi.
SELECT count(*) AS orphan_items
FROM app.order_items i
LEFT JOIN app.orders o USING (order_id)
WHERE o.order_id IS NULL;

-- Ví dụ: tổng số tiền theo order khớp với items.
SELECT o.order_id
FROM app.orders o
JOIN (
    SELECT order_id, sum(quantity * unit_price) AS item_total
    FROM app.order_items
    GROUP BY order_id
) i USING (order_id)
WHERE o.total_amount <> i.item_total;
```

Các truy vấn chỉ là ví dụ; business invariants thực tế phải được định nghĩa và xử lý null/rounding/discount/tax đúng.

### 20.3. Sequence validation

Kiểm tra nextval tiếp theo không xung đột với keys hiện có sau restore. Nếu cần setval, dừng writers và dùng sequence name/value chính xác.

### 20.4. Large Objects and external files

Kiểm tra OID có mở được, size/checksum đúng; object storage keys/version IDs còn tồn tại và có thể đọc. Một row metadata tồn tại không chứng minh binary đã được backup.

### 20.5. Roles và privileges

Test bằng role ứng dụng thật, không chỉ superuser. Kiểm tra:

- Login/authentication.
- Schema/table/sequence permissions.
- RLS policies và tenant context.
- Extension permissions.
- Tablespace access.
- Certificates/secrets/config.

### 20.6. Application smoke tests

Sau restore, thực hiện một luồng end-to-end có kiểm soát: đọc user, query order, tải attachment, ghi một record thử nếu môi trường test cho phép, publish/consume event và xác minh. Chỉ mở traffic khi những chức năng trọng yếu đạt.

### 20.7. Restore drill

Một backup được xem là đáng tin khi đội vận hành có thể restore thành công trong điều kiện gần production và đạt RTO/RPO. Lịch test cần bao phủ:

- Logical restore.
- Physical restore.
- PITR tới target.
- Failover từ standby.
- Restore roles/config/tablespaces.
- External object/event offset recovery.

## 21. Những lỗi thiết kế snapshot/backup thường gặp

### 21.1. Dùng READ COMMITTED cho nhiều câu dump tự viết

Mỗi statement có thể thấy snapshot khác nhau, khiến tables được export từ nhiều trạng thái. Dùng một transaction REPEATABLE READ hoặc công cụ backup quản lý snapshot.

### 21.2. Tạo snapshot riêng cho từng worker

Workers có thể thấy các committed changes khác nhau. Dùng pg_dump parallel hoặc exported snapshot chung.

### 21.3. Export snapshot rồi đóng exporter ngay

Consumer chưa import sẽ không thể dùng snapshot ID. Giữ exporter transaction tới khi mọi consumer đã import.

### 21.4. Giữ exporter transaction hàng giờ

Snapshot cũ giữ dead tuples và gây bloat. Giữ exporter chỉ trong thời gian orchestration cần thiết, theo dõi backend_xmin và timeout.

### 21.5. Cho rằng snapshot MVCC đóng băng sequence

Sequence nextval không transactional. Reconcile sequence values sau restore khi cần.

### 21.6. Dump hai databases và coi như một consistency point

pg_dump snapshots theo từng database. Dùng physical cluster backup hoặc application barrier để phối hợp.

### 21.7. Chỉ copy PGDATA

Tablespaces/WAL có thể ở ngoài PGDATA. Phải inventory và backup tất cả locations.

### 21.8. Snapshot từng volume ở thời điểm khác nhau

Có thể tạo một backup set không đồng bộ. Dùng consistency group hoặc backup protocol phù hợp, và test restore.

### 21.9. Storage snapshot không có WAL cần thiết

Data files có thể cần WAL để crash-recover. Bảo đảm backup start/stop WAL range hoặc archive/stream tương ứng.

### 21.10. Gọi pg_backup_start nhưng quên pg_backup_stop

Backup mode kéo dài có thể giữ WAL và gây storage growth. Dùng orchestration có cleanup/error handling.

### 21.11. Chỉ dump OID mà bỏ Large Object

Metadata row còn nhưng binary mất. Dùng tùy chọn backup LO phù hợp và test đọc object sau restore.

### 21.12. Quên roles/tablespaces

pg_dump một database không tự mang toàn bộ globals. Dump/backup globals riêng và restore theo thứ tự.

### 21.13. Cho rằng pg_dump bao gồm extension binaries/config

Dump có thể chứa CREATE EXTENSION nhưng không cài package/library trên host đích. Chuẩn bị dependencies và config riêng.

### 21.14. Dùng snapshot DB làm snapshot object storage

Database key còn nhưng object version đã bị xóa/overwrite. Dùng versioning/manifest và retention đồng bộ.

### 21.15. Bỏ qua event offsets

Restore DB mà không đồng bộ consumer offsets có thể replay duplicate hoặc bỏ sót events. Lưu offsets/barrier cùng consistency protocol.

### 21.16. Nghĩ physical backup là một ảnh MVCC

Physical backup dựa vào WAL recovery, không phải một lần SELECT theo snapshot. Dùng đúng backup protocol.

### 21.17. Nghĩ checkpoint là backup

Checkpoint chỉ tạo recovery point nội bộ, không tạo bản sao độc lập hay PITR archive.

### 21.18. Nghĩ pg_verifybackup chứng minh ứng dụng hoạt động

Manifest verification không test application permissions, external files, restore environment hoặc RTO. Cần restore drill.

### 21.19. Không giữ WAL đủ lâu

Base backup có nhưng archive bị purge trước retention window thì PITR có thể không đạt target. Retention phải tính backup age và WAL chain.

### 21.20. Không thử restore định kỳ

Backup có thể hỏng, thiếu tablespace, sai version hoặc thiếu WAL. Restore test là điều kiện xác nhận khả năng phục hồi.

### 21.21. Dùng timestamp làm global barrier

Clock skew và commit latency khiến timestamp không đồng bộ transaction state. Dùng LSN, snapshot ID, event offset và application epoch.

### 21.22. Tạm dừng writes nhưng bỏ qua in-flight workflows

Một workflow nhiều transactions có thể ở giữa bước. Chờ transaction DB chưa đủ; phải chờ business workflow đạt barrier terminal/safe.

### 21.23. Chỉ kiểm tra row counts

Số row bằng nhau không đảm bảo quan hệ, checksum, sequence, Large Objects hoặc external references đúng. Kiểm tra business invariants và end-to-end reads.

### 21.24. Restore vào cùng data directory đang chạy

Có thể làm hỏng hoặc ghi đè cluster. Restore vào data directory/host tách biệt; kiểm tra process và mount trước khi thao tác.

### 21.25. Không ghi lại timeline/system identifier

Có thể trộn WAL hoặc backup từ cluster/timeline sai. Lưu identity, timeline và LSN trong manifest.

## 22. Lab 1: quan sát READ COMMITTED và REPEATABLE READ

Mục tiêu: thấy một transaction có thể nhìn hai snapshots khác nhau dưới READ COMMITTED nhưng giữ cùng snapshot dưới REPEATABLE READ.

### 22.1. Chuẩn bị dữ liệu

Session setup:

```sql
CREATE SCHEMA IF NOT EXISTS snapshot_lab;

DROP TABLE IF EXISTS snapshot_lab.accounts;
CREATE TABLE snapshot_lab.accounts (
    account_id integer PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO snapshot_lab.accounts
VALUES (1, 100.00), (2, 200.00);
```

### 22.2. Thử READ COMMITTED

Session A:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT sum(balance)
FROM snapshot_lab.accounts;
```

Kết quả ban đầu là 300.

Session B:

```sql
BEGIN;
UPDATE snapshot_lab.accounts
SET balance = balance + 50
WHERE account_id = 1;
COMMIT;
```

Quay lại Session A:

```sql
SELECT sum(balance)
FROM snapshot_lab.accounts;

COMMIT;
```

Kết quả thứ hai là 350 vì statement mới lấy snapshot mới sau khi Session B commit.

### 22.3. Thử REPEATABLE READ

Session A:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT sum(balance)
FROM snapshot_lab.accounts;
```

Session B thực hiện UPDATE và COMMIT như trên. Session A chạy lại:

```sql
SELECT sum(balance)
FROM snapshot_lab.accounts;

COMMIT;
```

Session A tiếp tục thấy tổng ở snapshot ban đầu. Sau COMMIT, một transaction mới sẽ thấy giá trị đã cập nhật.

### 22.4. Quan sát ý nghĩa với backup

Nếu một backup script tự chạy nhiều SELECT dưới READ COMMITTED, nó có thể trộn hai trạng thái. pg_dump dùng snapshot transaction để các bảng thuộc một database được dump nhất quán.

## 23. Lab 2: export và import snapshot

Mục tiêu: nhiều sessions đọc cùng một snapshot.

### 23.1. Session exporter

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

Copy snapshot ID thực tế trả về. Giữ transaction này mở.

### 23.2. Session consumer A

Thay snapshot ID bằng giá trị exporter:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT count(*) FROM snapshot_lab.accounts;
```

### 23.3. Session consumer B

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT sum(balance) FROM snapshot_lab.accounts;
```

Hai consumer dùng cùng visibility point dù chạy trên hai connections khác nhau trong cùng database.

### 23.4. Thử thay đổi đồng thời

Trong một session thứ ba, UPDATE/INSERT rồi COMMIT. Hai consumer vẫn nhìn thấy snapshot đã import, không thấy thay đổi commit sau đó.

### 23.5. Kết thúc

COMMIT consumer transactions. Sau khi mọi consumers đã import snapshot và hoàn thành công việc, COMMIT exporter. Thử mở consumer mới sau khi exporter đóng: snapshot ID cũ không còn có thể import.

### 23.6. Giới hạn

Snapshot identifier chỉ tồn tại trong lifetime exporter; không dùng qua database khác, không dùng sau restart và không thay thế file backup.

## 24. Lab 3: pg_dump trong khi ứng dụng ghi dữ liệu

Mục tiêu: tạo logical dump trong khi concurrent DML và xác minh dump là một trạng thái nhất quán.

### 24.1. Tạo bảng lab

```sql
DROP TABLE IF EXISTS snapshot_lab.events;
CREATE TABLE snapshot_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO snapshot_lab.events(event_name)
SELECT 'initial-' || g
FROM generate_series(1, 1000) AS g;
```

### 24.2. Chạy pg_dump

```bash
pg_dump -Fc -f snapshot-lab.dump snapshot_lab_db
```

Thay database name đúng với lab. Nếu muốn thử parallel dump, dùng directory format và `-j`.

### 24.3. Concurrent writer

Trong lúc pg_dump đang chạy, một session khác có thể INSERT thêm rows:

```sql
INSERT INTO snapshot_lab.events(event_name)
SELECT 'during-dump-' || g
FROM generate_series(1, 10000) AS g;
```

Dump phản ánh snapshot của pg_dump; các rows commit sau snapshot không được đưa vào dump đó.

### 24.4. Restore sang database mới

```bash
createdb snapshot_lab_restore
pg_restore -d snapshot_lab_restore snapshot-lab.dump
```

So sánh dữ liệu dump với trạng thái tại snapshot bằng một marker/transaction đã ghi nhận. Không so sánh đơn giản với bảng live sau khi writer đã commit hàng nghìn rows.

### 24.5. Kiểm tra dump artifact

```bash
pg_restore --list snapshot-lab.dump
```

Kiểm tra archive contents, sau đó chạy query trên restored database. Lệnh list không chứng minh data correctness; query/restore test mới xác minh.

## 25. Lab 4: physical base backup và verification

Mục tiêu: hiểu một physical backup chứa data files và WAL cần thiết.

### 25.1. Điều kiện trước

- Một PostgreSQL lab server riêng.
- Role replication/backup được cấp quyền tối thiểu phù hợp.
- pg_hba.conf cho phép kết nối replication từ backup host.
- Destination storage đủ dung lượng và không phải PGDATA hiện tại.
- PostgreSQL client tools cùng major hoặc version tương thích.

### 25.2. Chạy pg_basebackup

```bash
pg_basebackup \
  -h 127.0.0.1 \
  -p 5432 \
  -U replication_backup \
  -D /backup/lab-base \
  -F plain \
  -X stream \
  -P
```

Thay host, port và path theo môi trường lab. Không ghi password trực tiếp trong command; dùng passfile/secret management.

### 25.3. Verify manifest

```bash
pg_verifybackup /backup/lab-base
```

Nếu backup manifest có mặt và phiên bản hỗ trợ, tool xác minh file checksums/manifest consistency. Ghi output và exit code.

### 25.4. Restore vào cluster riêng

Dùng data directory mới, tablespace mapping và port riêng. Cấu hình WAL archive nếu recovery cần. Start server restored theo tài liệu đúng major, không dùng chung data directory với source.

### 25.5. Kiểm tra dữ liệu

Chạy các queries nghiệp vụ và so sánh với mốc backup. Ghi thời gian server ready và app ready để xây baseline RTO.

## 26. Lab 5: mô phỏng consistency barrier

Mục tiêu: nhận ra snapshot MVCC không tự gom nhiều transactions thành một workflow.

### 26.1. Tạo bảng order/payment

```sql
CREATE TABLE snapshot_lab.orders (
    order_id bigint PRIMARY KEY,
    status text NOT NULL
);

CREATE TABLE snapshot_lab.payments (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES snapshot_lab.orders(order_id),
    status text NOT NULL
);
```

### 26.2. Tạo trạng thái workflow hai bước

Transaction A:

```sql
BEGIN;
INSERT INTO snapshot_lab.orders VALUES (9001, 'pending_payment');
COMMIT;
```

Tạm dừng trước khi tạo payment.

### 26.3. Snapshot ở giữa workflow

Một transaction REPEATABLE READ có thể thấy order 9001 pending nhưng chưa có payment. Snapshot này vẫn **nhất quán theo MVCC** vì transaction A đã commit và transaction payment chưa chạy.

### 26.4. Hoàn tất workflow

```sql
BEGIN;
INSERT INTO snapshot_lab.payments(order_id, status)
VALUES (9001, 'captured');
UPDATE snapshot_lab.orders
SET status = 'paid'
WHERE order_id = 9001;
COMMIT;
```

Snapshot trước transaction này không thấy payment và trạng thái paid; snapshot sau thấy cả hai thay đổi cùng nhau.

### 26.5. Rút ra barrier

Nếu backup chỉ chấp nhận orders đã paid, cần barrier/workflow query kiểm tra pending orders và chờ chúng hoàn tất hoặc ghi nhận chúng trong trạng thái phục hồi được. MVCC không tự đợi saga nhiều transactions.

## 27. Case study

### 27.1. Case A: pg_dump chạy lâu trong giờ cao điểm

**Bối cảnh:** database lớn, dump kéo dài 90 phút trong khi ứng dụng ghi liên tục.

**Triệu chứng:** dump nhất quán nhưng table bloat tăng, autovacuum không thu hồi được một số dead tuples và disk usage tăng.

**Phân tích:** snapshot dài hạn giữ row versions cũ cần thiết cho pg_dump. MVCC cho phép writers tiếp tục, nhưng không miễn phí.

**Hướng xử lý:** theo dõi backend_xmin, dump duration, dead tuples và autovacuum; dùng parallel dump khi phù hợp, tăng năng lực I/O/backup host hoặc chọn backup strategy khác. Không kết thúc exporter giữa chừng rồi kỳ vọng workers vẫn có thể import snapshot mới.

### 27.2. Case B: hai pg_dump riêng cho orders_db và billing_db

**Bối cảnh:** ứng dụng lưu orders trong database A và billing trong database B. Hai lệnh dump chạy cách nhau 15 phút.

**Rủi ro:** một order được commit giữa hai lần dump, khiến restored databases không cùng consistency point.

**Hướng xử lý:** nếu cần physical state toàn cluster, dùng physical backup. Nếu cần logical dumps riêng, tạo application barrier/maintenance window để dừng writes liên quan và ghi epoch chung trước khi dump; test cross-database reconciliation.

### 27.3. Case C: snapshot storage của ba volumes không đồng thời

**Bối cảnh:** PGDATA, tablespace và WAL ở ba cloud disks; provider tạo snapshot từng disk riêng.

**Rủi ro:** mỗi volume phản ánh thời điểm khác nhau. Backup set có thể không phục hồi được nếu WAL/data state không tương thích.

**Hướng xử lý:** dùng consistency group/atomic multi-volume snapshots hoặc backup tool có PostgreSQL backup protocol. Ghi snapshot IDs, start/stop LSN, tablespace map và test restore.

### 27.4. Case D: sequence bị lùi sau logical restore

**Bối cảnh:** trong lúc pg_dump, ứng dụng tiếp tục cấp ID từ sequence. Sau restore, nextval trả giá trị thấp hơn một số keys đã có.

**Rủi ro:** INSERT mới vi phạm PK/UNIQUE.

**Hướng xử lý:** dừng writers trong lúc reconcile; so sánh sequence state với max key và setval đúng sequence. Nếu có nhiều sequences/custom increments, xử lý từng cái theo metadata thực tế.

### 27.5. Case E: snapshot DB nhưng object storage bị lifecycle xóa

**Bối cảnh:** database backup giữ row có object_key, nhưng bucket lifecycle xóa object cũ sau 30 ngày trong khi DB backup giữ 90 ngày.

**Rủi ro:** restore DB trỏ tới object đã mất.

**Hướng xử lý:** dùng object versioning/backup bucket và retention ít nhất bằng DB backup retention; manifest liên kết DB backup ID với object versions/checksums.

### 27.6. Case F: logical replication snapshot ban đầu và CDC

**Bối cảnh:** pipeline lấy initial snapshot rồi bắt đầu stream WAL changes. Nếu snapshot point và CDC start LSN không được ghép đúng, có thể mất hoặc duplicate changes.

**Hướng xử lý:** dùng cơ chế consistent snapshot/LSN của logical decoding connector; lưu slot, snapshot metadata và offsets; test crash giữa snapshot và streaming.

### 27.7. Case G: backup từ hot standby bị cancel

**Bối cảnh:** pg_dump chạy trên standby nhưng recovery replay cần cleanup row versions mà query backup vẫn đang đọc.

**Triệu chứng:** query bị cancel do recovery conflict.

**Hướng xử lý:** xem hot standby conflict logs và backup duration; cân nhắc chạy dump trên primary, điều chỉnh thời gian/khối lượng hoặc dùng hot_standby_feedback khi hiểu rõ bloat impact. Không tăng timeout một cách mù quáng.

### 27.8. Case H: pg_basebackup thành công nhưng restore không start

**Bối cảnh:** backup command trả exit code 0, nhưng server đích thiếu tablespace mount hoặc WAL cần thiết.

**Rủi ro:** backup artifact không usable.

**Hướng xử lý:** kiểm tra manifest, tablespace paths, WAL method, system identifier, version và logs; restore drill định kỳ trên host riêng.

### 27.9. Case I: backup đúng MVCC nhưng nghiệp vụ còn pending

**Bối cảnh:** order transaction commit trước, payment transaction chưa chạy khi snapshot được lấy.

**Rủi ro:** backup có order pending_payment. Đây là trạng thái nhất quán về database nhưng không đáp ứng yêu cầu “chỉ backup đơn đã hoàn tất”.

**Hướng xử lý:** định nghĩa business barrier và xử lý pending workflows trước snapshot, hoặc đảm bảo saga state đủ để tiếp tục sau restore.

### 27.10. Case J: backup có database nhưng thiếu roles

**Bối cảnh:** pg_dump một database được restore sang server mới, nhưng roles/owners không tồn tại.

**Triệu chứng:** restore báo lỗi owner/privileges hoặc app không truy cập được.

**Hướng xử lý:** dump/restore globals riêng, chuẩn bị role mappings và test dưới application role. Không dùng superuser để che lỗi quyền.

## 28. Bài tập thực hành

Các bài dùng database lab và schema `snapshot_lab` đã tạo ở phần trước. Các bài về storage snapshots/cloud cần mô tả thiết kế; không tạo snapshot hoặc dừng cluster production.

### Bài 1. MVCC

Snapshot trong PostgreSQL là gì? Nó giúp quyết định điều gì khi đọc row versions?

### Bài 2. READ COMMITTED

Vì sao hai SELECT trong một transaction READ COMMITTED có thể nhìn thấy hai trạng thái khác nhau?

### Bài 3. REPEATABLE READ

Vì sao REPEATABLE READ phù hợp hơn cho một backup script chạy nhiều SELECT?

### Bài 4. Chưa commit

Một transaction INSERT row nhưng chưa COMMIT khi snapshot bắt đầu. Row đó có xuất hiện trong snapshot không?

### Bài 5. Snapshot và writers

MVCC snapshot có bắt buộc chặn mọi writers trong suốt backup không? Nêu một chi phí vận hành của snapshot dài hạn.

### Bài 6. pg_dump

pg_dump tạo snapshot nhất quán cho phạm vi nào? Nó có tự tạo một snapshot xuyên tất cả databases không?

### Bài 7. Parallel dump

Vì sao workers của parallel pg_dump phải dùng chung snapshot? Option nào bật parallel dump và format nào cần thiết?

### Bài 8. Export snapshot

Viết SQL bắt đầu transaction read-only REPEATABLE READ và export snapshot.

### Bài 9. Import snapshot

Nêu điều kiện isolation level và thời điểm gọi `SET TRANSACTION SNAPSHOT` trong consumer transaction.

### Bài 10. Exporter lifetime

Vì sao exporter transaction phải còn mở khi consumer import snapshot? Snapshot ID có thể dùng sau restart không?

### Bài 11. pg_dump --snapshot

Option này làm gì? Khi nào session exporter có thể COMMIT?

### Bài 12. Sequences

Vì sao sequence state không được đóng băng bởi MVCC snapshot? Nêu cách kiểm tra sau restore.

### Bài 13. Globals

pg_dump một database có bao gồm roles và tablespaces cluster-wide không? Dùng công cụ nào để dump globals?

### Bài 14. Logical vs physical

Phân biệt logical snapshot và physical backup theo dữ liệu được copy và cách recovery.

### Bài 15. Crash consistency

Storage snapshot đang chạy PostgreSQL có thể giống ảnh đĩa sau crash. WAL có vai trò gì khi restore?

### Bài 16. pg_backup_start/stop

Viết thứ tự các bước cho filesystem snapshot online dùng backup API.

### Bài 17. Backup label

`backup_label` và `tablespace_map` có vai trò gì? Vì sao không được tự tạo bằng cách đoán LSN?

### Bài 18. Multi-volume

PGDATA, tablespace và pg_wal ở ba volumes. Vì sao cần consistency group hoặc phối hợp backup protocol?

### Bài 19. pg_basebackup

Giải thích khác nhau giữa `-X stream`, `-X fetch` và `-X none`.

### Bài 20. Verify

`pg_verifybackup` kiểm tra điều gì? Vì sao nó không thay restore drill?

### Bài 21. Cross-database

Hai pg_dump chạy ở hai thời điểm khác nhau có thể tạo trạng thái inconsistent như thế nào? Đề xuất hai giải pháp.

### Bài 22. Business workflow

Một order và payment được ghi trong hai transactions. Snapshot giữa hai transactions có thể thấy gì? Đó có phải lỗi MVCC không?

### Bài 23. External object

Database backup lưu object key nhưng object bị overwrite sau đó. Đề xuất cách giữ object version nhất quán với DB backup.

### Bài 24. Event offsets

Vì sao restore database mà không đồng bộ Kafka consumer offsets có thể mất hoặc xử lý trùng events?

### Bài 25. Snapshot retention

Một pg_dump giữ snapshot 4 giờ trong workload write-heavy. Nêu tác động lên VACUUM và cách theo dõi.

### Bài 26. Standby backup

Vì sao pg_dump trên standby có thể bị cancel do recovery conflict? `hot_standby_feedback` có đánh đổi gì?

### Bài 27. Unlogged table

Dữ liệu unlogged table có được bảo đảm như logged table sau crash/standby recovery không?

### Bài 28. RPO/RTO

Checkpoint có quyết định RPO không? Những yếu tố nào ảnh hưởng RPO và RTO?

### Bài 29. Consistency manifest

Đề xuất ít nhất tám metadata fields cần lưu cùng backup để chứng minh phạm vi và khả năng phục hồi.

### Bài 30. Thiết kế tổng hợp

Một hệ thống có orders_db, billing_db, Kafka và object storage. Hãy thiết kế quy trình backup nhất quán toàn hệ thống và mô tả restore/offset reconciliation.

## 29. Gợi ý lời giải bài tập

### Đáp án 1. MVCC

Snapshot là tập thông tin transaction visibility tại một thời điểm logic, dùng để quyết định phiên bản row nào được xem là visible. Nó không phải bản copy vật lý toàn database.

### Đáp án 2. READ COMMITTED

READ COMMITTED lấy snapshot mới cho mỗi statement. Một transaction khác commit giữa hai SELECT có thể làm SELECT thứ hai nhìn thấy rows/versions mới.

### Đáp án 3. REPEATABLE READ

Nó giữ cùng snapshot cho các statements trong transaction, vì vậy nhiều SELECT dùng để xuất dữ liệu nhìn thấy cùng một visibility point. Đây là cơ sở cho logical dump nhất quán.

### Đáp án 4. Chưa commit

Không. Snapshot không coi transaction chưa commit là committed; nếu transaction commit sau snapshot, snapshot cũ vẫn không thấy row đó.

### Đáp án 5. Writers

Không. MVCC cho phép readers và writers chạy đồng thời trong phần lớn trường hợp. Snapshot dài hạn có thể giữ dead tuples, trì hoãn VACUUM và làm tăng bloat/disk usage.

### Đáp án 6. pg_dump

pg_dump tạo logical snapshot trong **một database**. Nó không tạo một exported MVCC snapshot chung xuyên tất cả databases trong cluster.

### Đáp án 7. Parallel dump

Nếu workers dùng snapshots khác nhau, bảng cha/bảng con có thể phản ánh các thời điểm khác nhau. Dùng `pg_dump -j N`; parallel dump yêu cầu directory format `-Fd`.

### Đáp án 8. Export snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot();
```

Giữ transaction exporter mở để consumer import.

### Đáp án 9. Import snapshot

Consumer phải dùng REPEATABLE READ hoặc SERIALIZABLE. Gọi `SET TRANSACTION SNAPSHOT 'snapshot_id'` trước query đầu tiên của transaction (ngoại trừ transaction-setting commands được phép).

### Đáp án 10. Exporter lifetime

Snapshot ID chỉ có thể import mới khi exporter transaction còn sống. Sau khi exporter kết thúc, identifier không còn dùng được cho consumer mới; nó không phải durable object và không tồn tại qua restart.

### Đáp án 11. pg_dump --snapshot

Option cho pg_dump dùng snapshot đã được một session khác export. Exporter có thể COMMIT sau khi pg_dump đã import snapshot thành công và không còn consumer nào cần import; thực tế nên đợi công cụ xác nhận đã thiết lập snapshot.

### Đáp án 12. Sequences

`nextval` không transactional và không rollback, nên sequence có thể tiến trong lúc dump. Sau restore, so sánh `last_value/is_called` với max key của table; nếu cần dừng writers và dùng `setval` để reconcile.

### Đáp án 13. Globals

Không. pg_dump một database không dump roles/tablespaces cluster-wide. Dùng `pg_dumpall --globals-only` hoặc quy trình quản lý globals riêng.

### Đáp án 14. Logical vs physical

Logical backup đọc schema/rows theo MVCC snapshot rồi tái tạo objects khi restore. Physical backup copy data files và WAL cần thiết; crash recovery replay WAL để đưa pages về consistency.

### Đáp án 15. Crash consistency

Snapshot block device có thể chứa pages được ghi ở những thời điểm khác nhau. WAL cung cấp các records cần redo để khôi phục consistency, miễn backup bao gồm đúng data files/tablespaces và WAL range cần thiết.

### Đáp án 16. Backup API

1. Inventory PGDATA/tablespaces/WAL volumes.
2. Gọi `pg_backup_start`.
3. Snapshot/copy tất cả volumes liên quan tại consistency point chung.
4. Gọi `pg_backup_stop`.
5. Lưu backup_label/tablespace_map do API trả về theo version.
6. Bảo đảm WAL từ start tới stop được archive/giữ.
7. Ghi manifest và test restore.

### Đáp án 17. Backup label

`backup_label` lưu thông tin backup start/checkpoint/redo cần cho recovery; `tablespace_map` mô tả mapping tablespaces trong backup. Chúng phải khớp đúng backup operation; tự đoán LSN/timestamp có thể làm recovery đọc sai WAL hoặc không nhận diện backup đúng.

### Đáp án 18. Multi-volume

Snapshot volume ở các thời điểm khác nhau có thể tạo data/tablespace/WAL không tương thích. Consistency group chụp đồng bộ hoặc backup API phối hợp WAL bảo đảm một physical backup có thể recovery.

### Đáp án 19. WAL methods

- `-X stream`: lấy WAL song song với data copy.
- `-X fetch`: lấy WAL sau khi copy, segments phải còn sẵn.
- `-X none`: không lấy WAL vào backup; cần nguồn archive/retention khác để cung cấp WAL cần thiết.

### Đáp án 20. Verify

`pg_verifybackup` kiểm tra backup manifest, file presence/checksums và một số điều kiện backup. Nó không start server, không xác minh application behavior, external objects, permissions hoặc RTO; cần restore drill.

### Đáp án 21. Cross-database

Orders dump lúc A và billing dump lúc B có thể chứa các trạng thái nghiệp vụ không cùng thời điểm. Giải pháp: physical cluster backup; hoặc application barrier/maintenance window để dừng writes liên quan rồi dump từng database và ghi chung epoch.

### Đáp án 22. Business workflow

Snapshot giữa hai transactions có thể thấy order pending_payment mà chưa có payment. Đây là trạng thái nhất quán MVCC vì transaction order đã commit và payment chưa commit; không phải lỗi MVCC. Nếu nghiệp vụ yêu cầu chỉ backup trạng thái terminal, cần barrier.

### Đáp án 23. External object

Dùng immutable object key/version ID, lưu version ID và checksum trong DB, backup bucket/version inventory theo retention ít nhất bằng DB backup, và không xóa object còn được backup tham chiếu.

### Đáp án 24. Event offsets

Nếu DB snapshot đã áp dụng offset N nhưng consumer offset restore là N-1, event N có thể được xử lý trùng. Nếu consumer offset là N+1 nhưng DB snapshot chưa áp dụng N, event bị bỏ sót. Cần commit offsets cùng DB state/inbox hoặc lưu coordinated barrier/CDC LSN.

### Đáp án 25. Snapshot retention

Snapshot 4 giờ có thể giữ xmin cũ, làm VACUUM không loại bỏ dead tuples, tăng bloat và nguy cơ wraparound pressure. Theo dõi `pg_stat_activity.backend_xmin`, xact_start, dead tuples, table size và autovacuum; giảm thời gian dump/parallelize/đổi backup strategy.

### Đáp án 26. Standby backup

WAL replay trên standby có thể cần cleanup row versions mà query dump vẫn đọc, dẫn đến recovery conflict và query cancel. `hot_standby_feedback` có thể yêu cầu primary giữ dead tuples lâu hơn, giảm cancellation nhưng tăng bloat trên primary.

### Đáp án 27. Unlogged table

Không. Unlogged tables không WAL-log data như logged tables; contents có thể bị truncate sau crash recovery và không replicate sang standby. Không dùng để lưu dữ liệu cần durable backup/replication nếu không có nguồn tái tạo.

### Đáp án 28. RPO/RTO

Checkpoint không quyết định RPO. RPO phụ thuộc WAL flush, synchronous_commit, replication mode, archive continuity và external systems. RTO phụ thuộc detection, restore/standby promotion, WAL replay, storage, app validation và mở traffic.

### Đáp án 29. Consistency manifest

Ví dụ: backup_id, backup_type, PostgreSQL version, system_identifier, timeline, start_lsn, stop_lsn, database list, tablespace map, storage snapshot IDs, WAL archive range, app epoch, object version manifest, checksum, retention_until, restore_test_id.

### Đáp án 30. Thiết kế tổng hợp

Một phương án:

1. Đặt application barrier/epoch; ngừng nhận writes mới liên quan hoặc queue chúng.
2. Đợi in-flight order/payment workflows tới trạng thái an toàn và ghi barrier.
3. Chốt Kafka partition offsets tương ứng với DB commits; ghi offsets/barrier trong DB hoặc manifest theo protocol.
4. Đảm bảo object storage dùng immutable version IDs và tạo inventory/checksum tại barrier.
5. Tạo physical cluster backup nếu orders_db/billing_db cùng cluster cần một physical consistency point; nếu logical dump riêng, giữ barrier trong suốt hai dumps.
6. Archive WAL liên tục và lưu start/stop LSN, timeline.
7. Ghi manifest liên kết DB backup ID, app epoch, Kafka offsets, object versions và checksums.
8. Restore DB vào môi trường tách biệt, PITR tới target, restore object versions, khôi phục consumer offsets tương ứng.
9. Reconcile inbox/outbox/transactions pending để tránh duplicate/lost events.
10. Chạy business invariants và end-to-end smoke tests trước khi mở traffic.

Nếu không thể dừng writes, cần protocol coordinated snapshot/CDC và saga state; chỉ chụp DB và bucket riêng lẻ không bảo đảm consistency toàn hệ thống.

## 30. Checklist thiết kế backup snapshot

### 30.1. Phạm vi snapshot

1. Snapshot là MVCC logical, physical base backup hay storage snapshot?
2. Snapshot bao phủ một database, toàn cluster hay nhiều hệ thống?
3. Có cần cùng snapshot cho nhiều tables/workers không?
4. Có cần consistency xuyên nhiều databases hoặc services không?
5. Có application workflows nhiều transactions cần barrier không?
6. Có sequence state, Large Objects, unlogged tables hoặc foreign data cần lưu ý không?

### 30.2. MVCC và pg_dump

7. Script nhiều SELECT có dùng REPEATABLE READ hoặc snapshot chung không?
8. Parallel dump có dùng snapshot synchronization đúng không?
9. Exporter transaction có giữ đủ lâu để consumer import và kết thúc sớm sau đó không?
10. Snapshot duration có được đo và giới hạn không?
11. Có theo dõi backend_xmin/VACUUM impact không?
12. DDL/migrations có được phối hợp với dump không?
13. Có dump globals (roles/tablespaces) riêng không?
14. Sequence values có được reconcile sau restore không?
15. Large Objects có được include và kiểm tra không?

### 30.3. Physical/storage backup

16. Có dùng pg_basebackup hoặc backup API đúng major không?
17. Backup có WAL cần thiết từ start tới stop không?
18. Tất cả tablespaces và external volumes có được inventory không?
19. Storage snapshots nhiều volume có atomic consistency group không?
20. Backup label/tablespace map được lưu đúng không?
21. pg_wal nằm riêng có được phối hợp đúng không?
22. Config files/certificates/extensions có backup riêng không?
23. Backup manifest/checksum có được verify không?

### 30.4. Hệ thống phân tán

24. External object storage có versioning/immutable keys không?
25. Kafka/CDC offsets có consistency point gắn với DB backup không?
26. Có app epoch/barrier chung không?
27. Có chờ pending sagas/in-flight workflows không?
28. Có xử lý 2PC hoặc outbox/saga đúng khả năng external systems không?

### 30.5. Restore và vận hành

29. Có restore drill cho logical, physical và PITR không?
30. Có test bằng application role/RLS không?
31. Có kiểm tra business invariants, sequence, LO và external objects không?
32. RPO/RTO có được đo từ sự cố tới app-ready không?
33. WAL archive retention có đủ cho base backup window không?
34. Có kiểm tra timeline/system identifier/LSN trong manifest không?
35. Có alert backup stale/failed, archive lag và restore-test overdue không?

## 31. Runbook khi snapshot/backup không nhất quán

### Bước 1. Xác định loại backup

Đầu tiên xác định artifact là pg_dump, pg_basebackup, filesystem snapshot, storage snapshot hay bộ backup đa hệ thống. Mỗi loại có consistency model và cách phục hồi khác nhau.

### Bước 2. Xác định consistency point

Với logical dump: tìm snapshot/transaction boundary và database name.

Với physical backup: tìm backup start/stop LSN, backup_label, timeline, system identifier và WAL range.

Với storage snapshot: tìm snapshot IDs, consistency group, volume list và backup API window.

Với distributed backup: tìm application epoch, Kafka offsets, CDC LSN và object versions.

### Bước 3. Kiểm tra completeness

Kiểm tra database list, tablespaces, WAL, roles/globals, LO, config/extensions, external objects và event offsets. Không suy ra đầy đủ từ file dump tồn tại.

### Bước 4. Kiểm tra lỗi snapshot lâu

Nếu pg_dump kéo dài hoặc vacuum bị giữ, kiểm tra `pg_stat_activity.backend_xmin`, transaction age, autovacuum và table bloat. Dừng backup transaction chỉ theo runbook, sau khi xác định consumer/exporter đang ở giai đoạn nào.

### Bước 5. Verify artifact

Chạy `pg_verifybackup` khi phù hợp, `pg_restore --list` với custom archive, kiểm tra checksums/manifest và file list. Ghi rõ đây là artifact verification, chưa phải restore validation.

### Bước 6. Restore vào môi trường độc lập

Không ghi đè production để thử. Restore đúng PostgreSQL major, tablespace map, WAL chain và dependencies. Xác minh server start và recovery hoàn tất.

### Bước 7. Kiểm tra business consistency

Chạy các invariants: orphan rows, totals, sequence values, attachment checksums, object versions, consumer offsets và saga states. Kiểm tra bằng role ứng dụng.

### Bước 8. Quyết định mở traffic

Chỉ mở traffic sau khi xác nhận consistency point, RPO, data integrity, authorization, external dependencies và smoke tests. Nếu có dữ liệu thiếu, giữ restored cluster cô lập và lập kế hoạch reconciliation.

### Bước 9. Sửa nguyên nhân

Ví dụ:

- READ COMMITTED nhiều statements → dùng transaction snapshot.
- Cross-database dumps → thêm barrier hoặc physical cluster backup.
- Missing WAL → sửa archive retention/backup procedure.
- Missing tablespaces → cập nhật volume inventory/consistency group.
- Missing external objects → object versioning/manifest/retention.
- Sequence collision → post-restore reconciliation.
- Long snapshot → tối ưu duration và backup concurrency.

### Bước 10. Cập nhật manifest và diễn tập lại

Ghi root cause, consistency point, artifact IDs, restore time và corrective actions. Chạy lại drill để chứng minh lỗi đã được xử lý.

## 32. Tổng kết

**Snapshot là một định nghĩa về trạng thái dữ liệu được nhìn thấy tại một consistency point; backup là artifact phải chứa đủ thành phần để khôi phục trạng thái đó.** PostgreSQL MVCC giúp logical readers nhìn thấy một tập row versions nhất quán, còn physical backup cần WAL recovery để làm các data files trở nên nhất quán.

Những điểm cốt lõi:

- READ COMMITTED lấy snapshot mới cho từng statement; REPEATABLE READ giữ snapshot nhất quán trong transaction.
- pg_dump dùng snapshot cho một database; parallel workers phải chia sẻ snapshot để tránh trộn trạng thái giữa các bảng.
- `pg_export_snapshot`/`SET TRANSACTION SNAPSHOT` phối hợp connections trong cùng database; exporter phải còn mở khi consumers import.
- Snapshot lâu giữ dead tuples và có thể gây bloat/VACUUM pressure.
- Sequence values không tuân theo MVCC snapshot như table rows; cần kiểm tra/reconcile sau restore.
- pg_dump một database không tự dump roles/global objects và không tạo consistency point xuyên nhiều databases.
- Physical backup cần data files, tablespaces, backup metadata và WAL liên tục; pg_basebackup/back-up API xử lý protocol.
- Storage snapshots nhiều volumes cần consistency group hoặc phối hợp backup API.
- Crash consistency, database MVCC consistency và business/distributed consistency là các tầng khác nhau.
- Snapshot DB không bao gồm object storage, Kafka offsets, file systems hoặc các services bên ngoài.
- Checkpoint không phải backup; PITR cần base backup và WAL archive liên tục.
- Backup manifest nên ghi system identifier, timeline, LSN, databases, tablespaces, snapshot IDs, app epoch và external versions.
- Backup chỉ đáng tin khi đã restore/test bằng ứng dụng và đo RTO/RPO.

Nguyên tắc thực hành:

> **Chọn đúng consistency point cho loại backup, phối hợp mọi thành phần thuộc phạm vi dữ liệu và chứng minh khả năng phục hồi bằng restore drill.**

## 33. Tài liệu tham khảo

Tài liệu PostgreSQL chính thức; chọn đúng major đang vận hành:

- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): READ COMMITTED, REPEATABLE READ, SERIALIZABLE và MVCC snapshots.
- [Snapshot Synchronization Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION): `pg_export_snapshot` và snapshot import.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical dump, snapshot, parallel jobs, globals và large objects.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html): dump nhiều databases và global objects.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, WAL archive và PITR.
- [Backup Control Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-BACKUP): `pg_backup_start` và `pg_backup_stop`.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): tạo physical base backup, WAL methods và tablespaces.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): kiểm tra backup manifest/checksums.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html): data locations và tablespace management.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity, backend_xmin và các statistics views.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): MVCC dead tuples, VACUUM và transaction horizons.
- [Sequence Manipulation Functions](https://www.postgresql.org/docs/current/functions-sequence.html): nextval/setval và sequence semantics.
- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): standby recovery, hot standby conflicts và feedback.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publication/subscription, initial copy và replication behavior.






