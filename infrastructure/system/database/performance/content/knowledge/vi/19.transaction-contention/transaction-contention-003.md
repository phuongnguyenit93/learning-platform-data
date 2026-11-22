# Mức cô lập, MVCC và chi phí duy trì các phiên bản dữ liệu

Trong chương **Giao dịch và tranh chấp** của module **DATABASE_PERFORMANCE**, mức cô lập giao dịch và cơ chế MVCC quyết định cách các transaction nhìn thấy dữ liệu đang được thay đổi đồng thời. Chúng ảnh hưởng tới tính đúng đắn của kết quả, khả năng đọc/ghi song song, thời gian chờ khóa và chi phí lưu trữ. Một cấu hình cô lập quá yếu có thể cho phép ứng dụng đọc hoặc ghi dựa trên trạng thái không phù hợp; cấu hình quá chặt có thể tăng khóa, xung đột và retry. MVCC giúp nhiều truy vấn đọc tiếp tục nhìn thấy một phiên bản nhất quán trong khi transaction khác ghi dữ liệu, nhưng đổi lại database phải tạo, giữ và dọn các phiên bản cũ.

Tối ưu hiệu năng cơ sở dữ liệu vì vậy cần nhìn đồng thời vào tải đọc/ghi, execution plan, thời gian chờ, thống kê transaction và vòng đời phiên bản dữ liệu. Không thể kết luận MVCC luôn nhanh hơn khóa, hoặc mức `REPEATABLE READ` có cùng semantics trên mọi hệ quản trị. Cần hiểu snapshot được tạo khi nào, loại đọc nào dùng snapshot, xung đột ghi được phát hiện ra sao và tiến trình dọn phiên bản bị ảnh hưởng bởi transaction dài như thế nào.

## 1. Mức cô lập giao dịch giải quyết vấn đề gì?

Transaction gom một nhóm thao tác thành một đơn vị công việc. Khi nhiều transaction chạy đồng thời, database cần xác định mỗi transaction được nhìn thấy thay đổi nào và xử lý xung đột ra sao. Mức cô lập (*isolation level*) đặt ra những giới hạn đối với việc các transaction quan sát lẫn nhau.

Các hiện tượng kinh điển thường dùng để mô tả mức cô lập:

| Hiện tượng | Mô tả |
|---|---|
| Dirty read | Transaction đọc dữ liệu do transaction khác ghi nhưng chưa commit; dữ liệu đó có thể bị rollback |
| Non-repeatable read | Cùng một dòng được đọc hai lần trong một transaction nhưng giá trị thay đổi do transaction khác commit ở giữa |
| Phantom read | Cùng một điều kiện truy vấn được thực hiện lại nhưng tập dòng phù hợp thay đổi do transaction khác thêm/xóa dòng |
| Lost update | Hai transaction cùng đọc một giá trị rồi ghi lại dựa trên giá trị cũ, khiến một cập nhật bị ghi đè |
| Read skew | Một transaction đọc các phần dữ liệu ở những thời điểm khác nhau và nhìn thấy tổ hợp trạng thái không nhất quán |
| Write skew | Hai transaction đọc cùng một trạng thái hợp lệ rồi cập nhật các dòng khác nhau; khi cả hai commit, ràng buộc nghiệp vụ tổng thể bị vi phạm |

Các tên hiện tượng trên mô tả hành vi, không phải tên một cơ chế triển khai. Mức cô lập cùng tên có thể khác nhau giữa PostgreSQL, MySQL/InnoDB, SQL Server và Oracle. Hãy kiểm tra semantics của sản phẩm và phiên bản thực tế.

### 1.1. Ví dụ lost update

Giả sử tài khoản có số dư 100. Hai transaction cùng muốn trừ 10:

1. A đọc số dư 100.
2. B đọc số dư 100.
3. A tính 90 và ghi 90.
4. B cũng tính 90 và ghi 90.

Kết quả cuối là 90, trong khi đúng ra phải là 80. Nếu cập nhật bằng một biểu thức nguyên tử:

```sql
UPDATE accounts
SET balance = balance - 10
WHERE account_id = 42;
```

database thực hiện phép cập nhật trên giá trị hiện hành theo cơ chế khóa/đồng thời của engine, tránh mẫu đọc-sửa-ghi tách rời nói trên. Tuy nhiên, nếu nghiệp vụ cần kiểm tra hạn mức, số dư không âm hoặc nhiều dòng liên quan, vẫn phải thiết kế transaction và constraint phù hợp.

### 1.2. Ví dụ write skew

Giả sử quy định một ca trực phải có ít nhất một bác sĩ đang trực. Hai bác sĩ A và B đều đang trực. Hai transaction đồng thời kiểm tra thấy có hai người, sau đó mỗi transaction tắt trạng thái trực của một người khác nhau. Nếu cả hai cùng commit mà không có khóa hoặc kiểm tra serializable phù hợp, kết quả có thể là không còn ai trực.

Mỗi transaction chỉ cập nhật một dòng riêng nên không nhất thiết có xung đột ghi trực tiếp. Vấn đề nằm ở ràng buộc tổng thể được xác định từ nhiều dòng đã đọc. Đây là lý do snapshot isolation đơn thuần không bảo đảm mọi invariant nghiệp vụ.

## 2. Các mức cô lập thường gặp

SQL chuẩn định nghĩa bốn mức phổ biến: `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Trong triển khai thực tế, tên mức cô lập không đủ để suy ra mọi chi tiết về snapshot, khóa phạm vi hay write conflict.

| Mức | Mục tiêu khái quát | Đánh đổi thường gặp |
|---|---|---|
| READ UNCOMMITTED | Cho phép đọc dữ liệu chưa commit ở các engine hỗ trợ | Có thể thấy dirty read; ít phù hợp với dữ liệu nghiệp vụ cần tin cậy |
| READ COMMITTED | Chỉ đọc dữ liệu đã commit tại thời điểm đọc theo semantics engine | Hai lần đọc có thể thấy trạng thái khác nhau |
| REPEATABLE READ | Giữ kết quả đọc ổn định hơn trong transaction | Có thể giữ snapshot lâu, tăng xung đột hoặc chi phí phiên bản; xử lý phantom tùy engine |
| SERIALIZABLE | Bảo đảm kết quả tương đương một thứ tự tuần tự hợp lệ | Có thể dùng khóa phạm vi hoặc phát hiện xung đột; transaction có thể phải retry |

### 2.1. READ UNCOMMITTED

Mức này cho phép transaction đọc thay đổi chưa commit trong các hệ quản trị thực sự hỗ trợ dirty read. Nếu transaction ghi sau đó rollback, dữ liệu mà transaction đọc đã không bao giờ trở thành trạng thái đã commit.

Một số engine không cung cấp dirty read thực sự dù cú pháp có thể được chấp nhận. PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED`; Oracle không cung cấp dirty read qua mức cô lập này; SQL Server có thể cho dirty read khi dùng `READ UNCOMMITTED` hoặc `NOLOCK`; MySQL/InnoDB hỗ trợ mức `READ UNCOMMITTED` với semantics riêng. Không nên dùng mức này chỉ để giảm blocking mà chưa đánh giá tính đúng đắn.

### 2.2. READ COMMITTED

Ở mức khái quát, transaction chỉ đọc dữ liệu đã commit. Tuy nhiên, snapshot có thể được tạo theo từng statement hoặc theo cách triển khai riêng. Nếu transaction chạy hai câu `SELECT` cách nhau, transaction khác có thể commit thay đổi ở giữa và kết quả lần đọc sau khác lần đầu.

Ví dụ, A đọc số đơn hoàn tất là 20. B hoàn tất thêm một đơn và commit. A đọc lại và thấy 21. Đây có thể là hành vi hợp lệ ở `READ COMMITTED`.

### 2.3. REPEATABLE READ

Mục tiêu là giữ một góc nhìn ổn định hơn trong transaction. Nhưng cách xử lý dòng mới thỏa predicate (*phantom*) khác nhau. Một số engine dùng snapshot transaction; một số kết hợp snapshot với next-key/gap locks; các thao tác locking read có thể dùng semantics khác consistent read.

Vì vậy, không nên dựa vào tên `REPEATABLE READ` để kết luận một truy vấn `SELECT` thông thường và `SELECT ... FOR UPDATE` nhìn thấy cùng một tập dữ liệu. Hãy đọc tài liệu engine và thử nghiệm với transaction đồng thời.

### 2.4. SERIALIZABLE

`SERIALIZABLE` yêu cầu kết quả tương đương một thứ tự tuần tự hợp lệ. Engine có thể khóa phạm vi dữ liệu, dùng predicate lock hoặc phát hiện các phụ thuộc xung đột rồi hủy một transaction. Tính đúng đắn cao hơn có thể đi kèm thời gian chờ, deadlock hoặc lỗi serialization cần retry.

Ứng dụng phải có chiến lược retry cho những lỗi có thể thử lại, đồng thời bảo đảm thao tác có tính idempotent hoặc được thực hiện lại trong transaction mới. Không retry vô hạn và không retry một phần transaction đã commit.

## 3. MVCC hoạt động như thế nào?

MVCC (*Multi-Version Concurrency Control*) là cơ chế quản lý nhiều phiên bản của cùng một dòng dữ liệu. Thay vì ghi đè ngay phiên bản mà mọi reader đang nhìn thấy, database lưu thông tin phiên bản mới và metadata cần thiết để transaction đọc đúng phiên bản phù hợp với snapshot của nó.

Một mô hình khái quát:

1. Transaction A bắt đầu và tạo snapshot theo quy tắc của engine.
2. Transaction B cập nhật một dòng và commit phiên bản mới.
3. A tiếp tục đọc theo snapshot của mình, nên có thể vẫn thấy phiên bản cũ.
4. Transaction mới bắt đầu sau khi B commit có thể thấy phiên bản mới.
5. Khi không còn snapshot nào cần phiên bản cũ, engine có thể thu hồi hoặc tái sử dụng không gian lưu trữ theo cơ chế riêng.

MVCC giúp reader thông thường không phải chờ writer chỉ vì writer đang tạo phiên bản mới. Tuy nhiên, writer vẫn cần phối hợp với writer khác trên cùng dữ liệu; khóa, kiểm tra xung đột và constraint vẫn tồn tại. Các thao tác như `SELECT FOR UPDATE`, DDL hoặc truy vấn dùng locking hint có thể tham gia cơ chế khóa khác với consistent read thông thường.

### 3.1. Snapshot và visibility

Snapshot xác định phiên bản nào được transaction nhìn thấy. Nó có thể dựa trên transaction id, commit sequence, SCN, LSN hoặc metadata nội bộ khác. Một dòng có thể có nhiều phiên bản; database xác định phiên bản phù hợp với thời điểm đọc và trạng thái commit của transaction tạo phiên bản.

Không phải cứ có MVCC là mọi transaction giữ snapshot từ lúc `BEGIN`. Ví dụ, PostgreSQL `READ COMMITTED` tạo snapshot cho từng statement; PostgreSQL `REPEATABLE READ` giữ snapshot transaction. SQL Server RCSI dùng row versioning theo statement, trong khi `SNAPSHOT` dùng transaction-level snapshot. Oracle `READ COMMITTED` dùng statement-level read consistency; transaction `SERIALIZABLE` có góc nhìn nhất quán ở mức transaction.

### 3.2. Version chain và chi phí đọc

Khi một dòng được cập nhật nhiều lần, engine có thể phải lần theo thông tin phiên bản hoặc undo để tìm phiên bản mà snapshot cần. Nếu có nhiều phiên bản cũ chưa được dọn, việc đọc có thể cần thêm công việc và không gian lưu trữ.

Mức chi phí cụ thể khác nhau:

- Có engine lưu phiên bản cũ ngay trong heap hoặc trang dữ liệu.
- Có engine giữ undo record riêng để tái tạo phiên bản cũ.
- Có engine lưu row version trong version store riêng hoặc vùng lưu trữ gắn với cơ chế phục hồi.

Do đó, MVCC có thể giảm blocking giữa reader và writer nhưng không miễn phí. Khi tỷ lệ cập nhật cao hoặc snapshot kéo dài, chi phí tạo, giữ, đọc và dọn phiên bản có thể trở thành nút thắt.

## 4. MVCC và khóa không loại trừ nhau

Một hiểu lầm thường gặp là database dùng MVCC thì không cần khóa. Trên thực tế:

- Hai transaction cập nhật cùng một dòng vẫn phải được tuần tự hóa hoặc phát hiện xung đột.
- Unique constraint và foreign key cần bảo vệ tính toàn vẹn khi nhiều transaction ghi đồng thời.
- `SELECT ... FOR UPDATE` hoặc locking read chủ động yêu cầu khóa để phối hợp với writer khác.
- DDL và một số thao tác bảo trì có thể cần khóa metadata hoặc khóa bảng.
- Serializable có thể dùng predicate/key-range locks hoặc phát hiện phụ thuộc để ngăn anomaly.

MVCC chủ yếu giúp reader có thể đọc phiên bản phù hợp mà không cần chờ mọi writer hoàn tất. Nó không làm cho các transaction ghi cùng dữ liệu có thể commit độc lập nếu điều đó vi phạm tính tuần tự hoặc constraint.

### 4.1. Consistent read và locking read

Consistent read đọc dữ liệu theo snapshot. Locking read yêu cầu khóa dòng hoặc phạm vi để bảo đảm thao tác tiếp theo không bị thay đổi ngoài ý muốn. Ví dụ trong MySQL/InnoDB, `SELECT ... FOR UPDATE` là locking read; nó không giống consistent nonlocking `SELECT` thông thường.

Trước khi thêm `FOR UPDATE`, hãy xác định transaction cần bảo vệ invariant nào và khóa bao nhiêu dòng. Khóa quá rộng hoặc giữ quá lâu có thể làm tăng lock wait, deadlock và giảm throughput. Nếu chỉ cần cập nhật một giá trị dựa trên giá trị hiện tại, một câu `UPDATE` nguyên tử có thể đơn giản và ít cửa sổ race hơn.

### 4.2. Deadlock và retry

Deadlock xảy ra khi các transaction giữ tài nguyên mà transaction kia cần, tạo thành vòng chờ. MVCC không loại bỏ deadlock giữa các writer hoặc locking reader. Hãy:

- Cập nhật nhiều dòng theo thứ tự khóa ổn định.
- Giữ transaction ngắn và chỉ khóa những dòng cần thiết.
- Tạo chỉ mục cho predicate để tránh scan rộng trong locking operation.
- Không gọi mạng hoặc chờ người dùng trong transaction đang giữ khóa.
- Xử lý deadlock/serialization error bằng retry có giới hạn và backoff.
- Ghi nhận transaction/query gây deadlock để sửa nguyên nhân, không chỉ tăng retry.

## 5. Khác biệt MVCC giữa các hệ quản trị

Các hệ quản trị lớn đều có cơ chế read consistency hoặc row versioning, nhưng nơi lưu phiên bản và cách dọn rất khác nhau. Phần này giúp nhận diện đúng chỉ số vận hành và tránh áp dụng một mẹo của hệ này sang hệ khác.

### 5.1. PostgreSQL

PostgreSQL lưu phiên bản dòng trong heap. Khi `UPDATE` hoặc `DELETE`, phiên bản cũ có thể vẫn tồn tại để transaction có snapshot phù hợp đọc được; phiên bản mới được tạo hoặc cập nhật theo cơ chế heap tuple. Các transaction id và visibility metadata giúp xác định dòng nào nhìn thấy được.

`VACUUM` thu hồi các phiên bản không còn cần thiết để không gian có thể được tái sử dụng. `VACUUM` thông thường không nhất thiết trả ngay dung lượng file hệ điều hành; `VACUUM FULL` có thể compact quan hệ nhưng cần khóa mạnh và ghi lại dữ liệu. Autovacuum tự động duy trì bảng dựa trên ngưỡng và cấu hình.

Transaction dài, session `idle in transaction`, replication slot giữ xmin hoặc snapshot lâu có thể ngăn VACUUM loại bỏ phiên bản cũ. Hậu quả có thể gồm:

- Dead tuple tích tụ và table/index bloat.
- Tăng số trang phải đọc và giảm hiệu quả cache.
- Autovacuum phải làm nhiều việc hơn hoặc không theo kịp tốc độ cập nhật.
- Tăng rủi ro transaction ID wraparound nếu vacuum freeze không theo kịp.

Kiểm tra transaction đang mở:

```sql
SELECT pid,
       usename,
       state,
       xact_start,
       now() - xact_start AS transaction_age,
       wait_event_type,
       wait_event,
       query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Quan sát dead tuple và hoạt động vacuum:

```sql
SELECT relname,
       n_live_tup,
       n_dead_tup,
       last_vacuum,
       last_autovacuum,
       vacuum_count,
       autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Các bộ đếm dòng trong view thống kê là ước lượng. Đọc cùng tuổi transaction, tốc độ update/delete, log autovacuum và dung lượng relation. Không chạy `VACUUM FULL` như phản xạ đầu tiên khi thấy dead tuple; trước hết tìm nguyên nhân phiên bản không được dọn và đánh giá tác động khóa/dung lượng.

PostgreSQL có các mức cô lập `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`. `READ UNCOMMITTED` được xử lý như `READ COMMITTED`. `REPEATABLE READ` dùng snapshot transaction và ngăn phantom theo cách triển khai của PostgreSQL, nhưng vẫn có thể xảy ra serialization anomaly như write skew. `SERIALIZABLE` dùng Serializable Snapshot Isolation (SSI) để phát hiện các phụ thuộc nguy hiểm; transaction có thể bị hủy với serialization failure và ứng dụng phải retry toàn bộ transaction.

### 5.2. MySQL/InnoDB

InnoDB dùng undo log để giữ thông tin cần thiết cho consistent read. Khi một dòng được cập nhật, undo record hỗ trợ transaction cũ tái tạo phiên bản phù hợp với read view. Các phiên bản không còn cần thiết được purge khi không còn read view nào phải giữ chúng.

Transaction dài có thể giữ read view cũ, làm purge không loại bỏ được undo record. History list length tăng là tín hiệu cần điều tra, đặc biệt khi đi kèm transaction lâu, undo tablespace tăng hoặc truy vấn chậm.

Kiểm tra transaction InnoDB:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
       trx_rows_locked,
       trx_rows_modified,
       trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Có thể xem trạng thái InnoDB bằng `SHOW ENGINE INNODB STATUS` và các bảng thống kê phù hợp phiên bản. Chú ý history list length, purge state, lock wait và transaction lâu. Không chỉ dựa vào một con số history list; cần quan sát xu hướng và khả năng purge theo thời gian.

InnoDB mặc định thường dùng `REPEATABLE READ`. Consistent read thông thường trong transaction dùng read view được tạo ở lần đọc nhất quán đầu tiên; locking read và thao tác ghi có semantics khác, thường xét trạng thái hiện hành và dùng khóa. Ở `REPEATABLE READ`, InnoDB có thể dùng next-key/gap locks cho locking read và một số thao tác tìm kiếm để ngăn insert phantom trong phạm vi khóa. `READ COMMITTED` thường giảm gap locking cho tìm kiếm thông thường, nhưng vẫn giữ các khóa cần thiết cho constraint và foreign key.

### 5.3. SQL Server

SQL Server hỗ trợ row versioning cho hai chế độ quan trọng:

- **READ_COMMITTED_SNAPSHOT (RCSI):** khi bật ở cấp database, `READ COMMITTED` dùng row versioning để mỗi statement đọc một snapshot nhất quán tại thời điểm statement bắt đầu, thay vì dùng shared lock theo cách truyền thống cho các lần đọc dữ liệu thông thường.
- **SNAPSHOT isolation:** transaction đọc theo snapshot ở mức transaction; cần bật `ALLOW_SNAPSHOT_ISOLATION` ở cấp database và ứng dụng chọn mức `SNAPSHOT`.

Row version thường được lưu trong version store của `tempdb`; với Accelerated Database Recovery (ADR), persistent version store (PVS) trong database có thể tham gia lưu giữ phiên bản theo cấu hình và phiên bản. Cần xác định cơ chế thực tế đang dùng trước khi chẩn đoán áp lực dung lượng.

Kiểm tra cấu hình:

```sql
SELECT name,
       is_read_committed_snapshot_on,
       snapshot_isolation_state_desc,
       is_accelerated_database_recovery_on
FROM sys.databases
WHERE database_id = DB_ID();
```

Ví dụ bật RCSI hoặc snapshot isolation cần thực hiện theo kế hoạch thay đổi vì có thể yêu cầu không còn connection hoặc transaction hoạt động tùy thao tác:

```sql
ALTER DATABASE YourDatabase
SET READ_COMMITTED_SNAPSHOT ON;

ALTER DATABASE YourDatabase
SET ALLOW_SNAPSHOT_ISOLATION ON;
```

Theo dõi version store trong `tempdb` và transaction giữ phiên bản:

```sql
SELECT *
FROM sys.dm_tran_version_store_space_usage
WHERE database_id = DB_ID();

SELECT *
FROM sys.dm_tran_active_snapshot_database_transactions;
```

Quyền truy cập DMV tùy phiên bản và quyền server. RCSI không đồng nghĩa snapshot transaction: mỗi statement có snapshot riêng, nên hai statement trong cùng transaction có thể thấy hai trạng thái đã commit khác nhau. `SNAPSHOT` giữ góc nhìn transaction và có thể phát sinh update conflict khi transaction cố ghi một dòng đã bị transaction khác sửa sau snapshot.

### 5.4. Oracle Database

Oracle dùng undo data để cung cấp read consistency. Một câu truy vấn nhìn thấy dữ liệu tại một SCN phù hợp với thời điểm bắt đầu statement; các block hiện tại có thể được tái tạo về trạng thái trước đó bằng undo khi cần. Ở mức `READ COMMITTED`, mỗi statement có read consistency riêng. Transaction `SERIALIZABLE` hoặc `READ ONLY` sử dụng góc nhìn nhất quán theo transaction theo semantics Oracle.

Nếu một truy vấn cần phiên bản cũ nhưng undo đã bị ghi đè trước khi truy vấn hoàn tất, có thể gặp `ORA-01555: snapshot too old`. Đây là dấu hiệu thời gian truy vấn/snapshot vượt khả năng cung cấp undo cần thiết trong điều kiện workload và cấu hình hiện tại; không đơn giản chỉ là lỗi tăng timeout.

Theo dõi transaction và undo:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       t.start_time,
       t.used_ublk,
       t.used_urec,
       s.status,
       s.sql_id
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.start_time;
```

Kiểm tra cấu hình undo:

```sql
SELECT tablespace_name,
       retention,
       status
FROM dba_tablespaces
WHERE contents = 'UNDO';

SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       ssolderrcnt
FROM v$undostat
ORDER BY begin_time DESC;
```

Tên view, cột và quyền xem phụ thuộc phiên bản/edition. Cần theo dõi dung lượng undo, retention, tốc độ phát sinh undo, thời gian truy vấn dài nhất và lỗi snapshot too old. Tăng undo tablespace hoặc retention có thể giúp, nhưng phải xem cả dung lượng, workload và khả năng ghi đè undo; không thể chỉ tăng một tham số mà bỏ qua nguyên nhân truy vấn kéo dài.

## 6. So sánh cách tạo snapshot và lưu phiên bản

| Hệ quản trị | Cơ chế/điểm quan sát | Ảnh hưởng của transaction dài |
|---|---|---|
| PostgreSQL | Heap tuple versions, xmin/xmax, VACUUM/autovacuum | Giữ dead tuple cần thiết, gây bloat và cản trở vacuum cleanup/freeze |
| MySQL/InnoDB | Undo log, read view, purge, history list length | Giữ undo history, làm purge bị chặn và undo tăng |
| SQL Server | Row versioning, tempdb version store hoặc PVS khi ADR | Giữ row versions lâu hơn, tăng dung lượng version store và áp lực cleanup |
| Oracle | Undo segments, read consistency theo SCN | Cần giữ undo lâu hơn; thiếu undo phù hợp có thể gây snapshot too old |

Các cơ chế trên không thể quy đổi một-một. Ví dụ, PostgreSQL giữ phiên bản cũ trong heap; InnoDB dùng undo để tái tạo phiên bản; SQL Server lưu row version trong vùng riêng; Oracle dùng undo để tái tạo block nhất quán. Chỉ số cần theo dõi và biện pháp dọn vì thế khác nhau.

## 7. Transaction dài làm tăng chi phí MVCC ra sao?

Một transaction dài có thể giữ snapshot hoặc read view cũ dù nó không thực hiện nhiều câu SQL. Database phải giữ những phiên bản mà snapshot đó còn có thể cần. Trong khi đó, transaction khác tiếp tục cập nhật và tạo thêm phiên bản.

Chuỗi tác động thường gặp:

1. Một transaction mở snapshot và giữ transaction lâu.
2. Workload khác cập nhật/xóa nhiều dòng, tạo phiên bản mới và metadata undo/version.
3. Tiến trình cleanup không thể loại các phiên bản còn cần cho snapshot cũ.
4. Dung lượng phiên bản tăng, số trang và chi phí quản lý tăng.
5. Truy vấn đọc có thể phải xử lý thêm version/undo; cache bị chiếm bởi dữ liệu không còn hữu ích cho workload mới.
6. Cleanup phải xử lý backlog lớn hơn khi snapshot được giải phóng.

Transaction dài không chỉ là transaction có nhiều câu lệnh. Một session `idle in transaction` chờ ứng dụng hoặc người dùng vẫn có thể giữ snapshot/lock. Các nguyên nhân thường gặp gồm ứng dụng mở transaction trước khi gọi API bên ngoài, quên commit/rollback, streaming result chưa đóng, job batch chạy quá lâu hoặc transaction đọc báo cáo giữ snapshot trong nhiều phút.

### 7.1. Phân biệt transaction dài và query dài

Query dài có thể đang tiêu thụ CPU/I/O và giữ snapshot trong lúc chạy. Transaction dài có thể gồm nhiều query ngắn nhưng giữ snapshot giữa các lần gọi. Cả hai đều cần theo dõi:

- `query_start` hoặc thời gian bắt đầu câu lệnh.
- `xact_start`/transaction start.
- Trạng thái session, đặc biệt idle in transaction.
- Thời gian chờ lock và wait event.
- Snapshot/read view lâu nhất và tác động tới cleanup.

Không kết thúc transaction chỉ dựa vào tuổi nếu chưa xác định chủ sở hữu và tác động nghiệp vụ. Trước hết tìm nguyên nhân giữ transaction, sau đó phối hợp xử lý session hoặc sửa ứng dụng theo quy trình vận hành.

### 7.2. Tác động tới dung lượng và cache

Phiên bản cũ có thể chiếm heap, undo tablespace, tempdb version store hoặc undo segment. Dung lượng tăng có thể gây thêm I/O, tăng backup/log, làm cache chứa nhiều trang hơn và kéo dài bảo trì. Với hệ thống có giới hạn đĩa, version store tăng đột biến còn có thể gây lỗi ghi hoặc làm database mất khả năng tiếp tục phục vụ.

Theo dõi xu hướng tăng/giảm, không chỉ số hiện tại. Nếu phiên bản tăng trong khi cleanup không theo kịp, cần tìm transaction giữ snapshot, tốc độ DML, cấu hình cleanup và tài nguyên lưu trữ.

## 8. Chi phí tạo phiên bản và ghi transaction log

MVCC yêu cầu database lưu đủ thông tin để rollback, phục hồi và cung cấp snapshot. Một thao tác `UPDATE` có thể phát sinh nhiều công việc hơn số byte ứng dụng thay đổi:

- Ghi phiên bản mới hoặc thông tin undo của phiên bản cũ.
- Ghi transaction log/WAL/redo để bảo đảm durability và recovery.
- Cập nhật index nếu cột được đánh chỉ mục thay đổi hoặc cấu trúc lưu trữ yêu cầu.
- Cập nhật metadata visibility, version chain hoặc delete marker.
- Cleanup phiên bản cũ khi không còn cần thiết.
- Tạo thêm I/O, CPU và áp lực cache.

Nếu ứng dụng cập nhật cùng một dòng nhiều lần trong một transaction hoặc phát nhiều update nhỏ, chi phí version/log có thể tăng. Có thể giảm bằng cách gộp thay đổi trong một câu lệnh, chỉ cập nhật khi giá trị thực sự thay đổi và tránh ghi lại cùng dữ liệu không cần thiết.

Ví dụ, thay vì gửi nhiều câu lệnh:

```sql
UPDATE customer_profile SET city = :city WHERE customer_id = :id;
UPDATE customer_profile SET phone = :phone WHERE customer_id = :id;
UPDATE customer_profile SET note = :note WHERE customer_id = :id;
```

có thể gộp thành một câu lệnh nếu các giá trị đã sẵn sàng:

```sql
UPDATE customer_profile
SET city = :city,
    phone = :phone,
    note = :note
WHERE customer_id = :id;
```

Gộp update có thể giảm số lần tạo phiên bản/log và số lần tìm dòng, nhưng không phải lúc nào cũng đúng nếu mỗi cập nhật có quy tắc audit hoặc thời điểm commit riêng. Hãy giữ semantics nghiệp vụ.

### 8.1. Chỉ cập nhật khi giá trị thay đổi

Một số ứng dụng gửi `UPDATE` dù giá trị mới giống giá trị cũ. Tùy engine và biểu thức, thao tác có thể vẫn tạo công việc ghi/version/index. Có thể thêm predicate để bỏ qua thay đổi không cần thiết:

```sql
UPDATE customer_profile
SET phone = :phone
WHERE customer_id = :id
  AND phone IS DISTINCT FROM :phone;
```

`IS DISTINCT FROM` là cú pháp PostgreSQL và một số hệ quản trị hỗ trợ; cú pháp null-safe comparison khác nhau theo sản phẩm. Cần lưu ý trigger, audit, `updated_at` và yêu cầu phát sự kiện có thể vẫn cần chạy ngay cả khi giá trị nghiệp vụ không đổi.

### 8.2. Chỉ mục làm tăng chi phí ghi

Mỗi chỉ mục có thể phải cập nhật khi các cột khóa hoặc cột bao phủ thay đổi. Với workload ghi cao, quá nhiều index làm tăng log, page split, I/O và thời gian giữ khóa. Khi phân tích chi phí MVCC, hãy xem cả bảng lẫn index; bloat hoặc version cleanup ở bảng không phải yếu tố duy nhất.

## 9. Chọn mức cô lập theo invariant nghiệp vụ

Không nên chọn mức cô lập chỉ dựa trên mong muốn “tránh lock”. Hãy liệt kê invariant cần bảo vệ rồi chọn cơ chế phù hợp.

| Nhu cầu | Cơ chế có thể phù hợp | Điều cần xác minh |
|---|---|---|
| Đọc danh sách và chấp nhận dữ liệu thay đổi giữa các statement | READ COMMITTED hoặc snapshot theo statement | Kết quả có thể khác giữa các lần đọc |
| Tạo báo cáo nhất quán trong một transaction | Snapshot transaction/REPEATABLE READ hoặc SERIALIZABLE theo engine | Thời gian giữ snapshot và cleanup cost |
| Trừ tồn kho nếu đủ hàng | Atomic conditional update hoặc khóa dòng | Không để hai đơn cùng vượt tồn |
| Bảo đảm ít nhất một nhân sự trực | SERIALIZABLE, khóa nhóm/invariant hoặc mô hình dữ liệu khác | Snapshot isolation có thể cho write skew |
| Chuyển tiền giữa hai tài khoản | Transaction nguyên tử, khóa theo thứ tự ổn định và constraint | Không để cập nhật một phía hoặc lost update |
| Duyệt dữ liệu ổn định trong batch dài | Snapshot/consistent read phù hợp hoặc chia batch theo khóa | Dung lượng phiên bản, undo retention và khả năng restart |

### 9.1. Dùng atomic update khi có thể

Ví dụ trừ tồn kho chỉ khi còn đủ số lượng:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :requested
WHERE product_id = :product_id
  AND available_quantity >= :requested;
```

Ứng dụng kiểm tra số dòng bị ảnh hưởng. Nếu bằng 1, cập nhật thành công; nếu bằng 0, không đủ hàng hoặc sản phẩm không tồn tại. Phép kiểm tra và cập nhật nằm trong cùng statement, giúp tránh mẫu đọc trước rồi ghi sau. Nếu cần cập nhật nhiều sản phẩm, phải xử lý thứ tự khóa, rollback toàn bộ khi thiếu một mặt hàng và retry khi gặp deadlock phù hợp.

### 9.2. Dùng optimistic concurrency khi phù hợp

Một bảng có cột `version` có thể phát hiện dữ liệu đã bị thay đổi kể từ lần đọc:

```sql
UPDATE documents
SET body = :new_body,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = :id
  AND version = :expected_version;
```

Nếu số dòng cập nhật bằng 0, phiên bản đã thay đổi hoặc dòng không còn tồn tại. Ứng dụng có thể tải lại, hợp nhất thay đổi hoặc báo conflict. Cơ chế này hữu ích khi xung đột ít và không muốn giữ khóa trong lúc người dùng chỉnh sửa lâu.

### 9.3. Dùng SERIALIZABLE hoặc khóa phạm vi cho invariant nhiều dòng

Nếu invariant phụ thuộc nhiều dòng, có thể cần transaction serializable, khóa một dòng đại diện cho nhóm, constraint phù hợp hoặc thiết kế lại để biến invariant thành cập nhật nguyên tử trên một bản ghi. Với serializable, phải chuẩn bị retry toàn bộ transaction khi engine phát hiện xung đột.

Khóa một dòng đại diện có thể đơn giản hóa việc phối hợp nhưng tạo hot row. Cần đo mức tranh chấp và xác định thứ tự khóa. Không dùng `SELECT ... FOR UPDATE` trên tập dữ liệu rộng nếu chỉ cần bảo vệ một invariant nhỏ.

## 10. Giảm thời gian giữ snapshot và transaction

Các biện pháp vận hành có hiệu quả cao thường bắt đầu từ việc giảm tuổi transaction:

- Mở transaction ngay trước nhóm thao tác cần nguyên tử và commit ngay sau đó.
- Không chờ người dùng, API bên ngoài, message broker hoặc tác vụ chậm trong transaction.
- Đóng cursor/stream và connection đúng cách; rollback khi xử lý lỗi.
- Chia batch lớn thành các đơn vị có thể restart, có checkpoint và semantics nhất quán.
- Với báo cáo rất dài, cân nhắc replica đọc, snapshot export hoặc kho phân tích thay vì giữ snapshot lâu trên primary.
- Theo dõi và xử lý session `idle in transaction` theo chính sách.
- Tránh transaction đọc kéo dài không cần thiết chỉ để giữ một kết quả UI; có thể materialize kết quả hoặc dùng keyset pagination.

Chia batch làm giảm thời gian giữ snapshot và lock, nhưng mỗi batch có thể nhìn thấy snapshot khác nhau. Nếu cần toàn bộ báo cáo phản ánh một thời điểm duy nhất, chia batch độc lập có thể làm dữ liệu không nhất quán giữa các phần. Cần chọn giữa snapshot thống nhất, export snapshot, bảng staging hoặc chấp nhận dữ liệu thay đổi theo từng batch.

## 11. Đo và chẩn đoán chi phí MVCC

Khi thấy dung lượng tăng, truy vấn chậm hoặc cleanup không theo kịp, hãy thu thập dữ liệu ở bốn lớp:

1. **Transaction:** tuổi transaction, trạng thái session, isolation level, snapshot lâu nhất, transaction idle.
2. **DML:** số dòng insert/update/delete, tốc độ phát sinh phiên bản, các bảng/index bị cập nhật nhiều.
3. **Cleanup:** vacuum/purge/version cleanup/undo retention có theo kịp không, có bị chặn bởi snapshot cũ không.
4. **Tài nguyên:** dung lượng version/undo/tempdb, WAL/redo, I/O latency, CPU, cache hit và wait events.

### 11.1. PostgreSQL

Các điểm quan sát quan trọng:

- `pg_stat_activity.xact_start`, `state` và `wait_event` để tìm transaction lâu hoặc idle in transaction.
- `pg_stat_user_tables.n_dead_tup`, `last_autovacuum` và các bộ đếm vacuum để theo dõi dead tuple và hoạt động dọn.
- `pg_stat_database` và `pg_stat_wal` (tùy phiên bản) để theo dõi hoạt động đọc/ghi và WAL.
- `pg_stat_progress_vacuum` để xem vacuum đang làm việc tới đâu.
- Replication slot và `xmin`/`catalog_xmin` nếu có slot giữ phiên bản cũ.

Không nên chỉ tăng `autovacuum_vacuum_scale_factor` hoặc giảm ngưỡng một cách máy móc. Với bảng cập nhật lớn, cấu hình theo từng bảng có thể cần thiết. Trước tiên xác định tốc độ dead tuple, thời gian snapshot lâu nhất, khả năng I/O và lịch vacuum.

### 11.2. MySQL/InnoDB

Theo dõi:

- Transaction lâu trong `information_schema.innodb_trx`.
- `SHOW ENGINE INNODB STATUS` để xem transaction, lock wait, deadlock và history list length.
- Các metric InnoDB undo/purge, undo tablespace và transaction history theo phiên bản.
- Performance Schema để xác định statement và wait event có thời gian chờ cao.

Nếu history list length tăng liên tục, kiểm tra transaction giữ read view lâu, tốc độ DML và khả năng purge. Không chỉ tăng undo tablespace nếu nguyên nhân là transaction không kết thúc; dung lượng lớn hơn có thể trì hoãn sự cố nhưng không xử lý gốc rễ.

### 11.3. SQL Server

Theo dõi:

- `sys.dm_tran_active_snapshot_database_transactions` để xem transaction đang giữ snapshot.
- `sys.dm_db_version_store_space_usage` cho dung lượng version store theo database.
- `tempdb` file usage và các wait liên quan tới tempdb.
- ADR/PVS metrics khi database bật Accelerated Database Recovery.
- Query Store, wait statistics và transaction log usage để nối chi phí versioning với workload.

Nếu tempdb tăng nhanh, xác định database và transaction đang giữ phiên bản, kiểm tra RCSI/SNAPSHOT, transaction dài và ADR. Tăng file tempdb có thể cần thiết để cấp dung lượng, nhưng không thay thế việc giải phóng transaction giữ version lâu.

### 11.4. Oracle Database

Theo dõi:

- `v$transaction` và `v$session` để tìm transaction lâu, undo block/record đã dùng.
- `v$undostat` để xem undo generation, query length và snapshot too old.
- Undo tablespace, retention và cảnh báo dung lượng.
- SQL Monitor/AWR/ASH nếu môi trường được cấp phép và cấu hình để xác định truy vấn giữ snapshot lâu.

Khi gặp `ORA-01555`, xem thời gian query, undo generation, retention và khả năng ghi đè undo. Tăng undo retention hoặc dung lượng có thể hỗ trợ, nhưng cần đánh giá không gian thực tế và các transaction khác.

## 12. Benchmark mức cô lập và MVCC

Một benchmark hữu ích phải mô phỏng cả đọc lẫn ghi. Chạy riêng một truy vấn đọc trên dữ liệu tĩnh không thể cho biết chi phí versioning khi workload cập nhật liên tục.

### 12.1. Xây dựng workload thử

Chọn các nhóm hoạt động đại diện:

- Reader chạy truy vấn theo snapshot, gồm đọc một dòng và scan/report dài.
- Writer cập nhật cùng một tập dòng và các tập dòng độc lập.
- Transaction thực hiện locking read hoặc cập nhật nhiều dòng.
- Transaction ngắn và transaction kéo dài để quan sát tác động snapshot.
- Batch insert/update/delete với tốc độ gần production.

Chạy nhiều mức đồng thời, ví dụ thấp, trung bình và cao; giữ dữ liệu và phân bố tương đương. Không dùng một giá trị concurrency duy nhất để quyết định cấu hình production.

### 12.2. Chỉ số cần ghi

| Nhóm | Chỉ số |
|---|---|
| Hiệu năng giao dịch | Throughput, p50/p95/p99, commit latency, timeout |
| Tranh chấp | Lock wait, deadlock, serialization/update conflict, retry rate |
| MVCC | Tuổi transaction/snapshot, số version hoặc undo history, cleanup lag |
| Lưu trữ | Table/index bloat, version store, undo tablespace, tempdb usage |
| Ghi log | WAL/redo/transaction log bytes, log flush latency |
| Tài nguyên | CPU, memory, IOPS, read/write latency, cache hit |
| Độ đúng | Lost update, write skew, kết quả đọc không nhất quán, invariant violation |

### 12.3. So sánh cấu hình

Thử các mức cô lập và row versioning trong môi trường riêng. So sánh không chỉ latency mà cả lỗi, retry và độ đúng. Một cấu hình có p95 thấp hơn nhưng cho phép vi phạm invariant không phải cải thiện.

Giữ cùng dataset, query mix, số worker, warm/cold cache và thời gian chạy. Đo đủ lâu để thấy cleanup hoạt động; benchmark vài giây có thể kết thúc trước khi version store hoặc purge backlog thể hiện vấn đề.

## 13. Ví dụ điều tra transaction dài làm tăng chi phí phiên bản

Một dịch vụ báo cáo mở transaction ở `REPEATABLE READ`, đọc một tập lớn, sau đó gọi một dịch vụ bên ngoài để lấy metadata và chờ vài phút trước khi commit. Trong thời gian đó, hệ thống giao dịch tiếp tục cập nhật nhiều dòng.

Triệu chứng có thể gồm:

- PostgreSQL có dead tuple tăng và autovacuum khó thu hồi phiên bản.
- MySQL/InnoDB có history list length tăng và purge không theo kịp.
- SQL Server có version store/tempdb tăng do snapshot transaction còn hoạt động.
- Oracle có nhu cầu undo lớn hơn và truy vấn dài có nguy cơ `ORA-01555` nếu undo bị tái sử dụng.

Quy trình xử lý:

1. Xác định transaction bắt đầu lúc nào, session nào giữ snapshot và công việc nào đang chờ.
2. Xác nhận nó có thật sự cần một snapshot duy nhất trong suốt thời gian gọi dịch vụ ngoài không.
3. Chuyển lời gọi mạng ra ngoài transaction nếu không cần tính nguyên tử với dữ liệu database.
4. Nếu báo cáo cần snapshot ổn định, đọc và materialize dữ liệu cần thiết trong transaction ngắn hoặc dùng cơ chế snapshot/export phù hợp.
5. Nếu có thể chia batch, xác định semantics nhất quán giữa các batch và checkpoint để restart.
6. Đo lại tuổi transaction, cleanup lag, version/undo/tempdb, I/O và latency của workload ghi.

Kết quả mong đợi là transaction ngắn hơn, cleanup có thể tiến triển và dung lượng phiên bản ổn định. Không chỉ xác nhận query báo cáo chạy nhanh hơn; cần quan sát sau khi workload ghi tiếp tục trong một khoảng thời gian đủ dài.

## 14. Những sai lầm thường gặp

- **Cho rằng MVCC loại bỏ mọi khóa:** writer, locking read, constraint và DDL vẫn có thể chờ khóa.
- **Cho rằng cùng tên isolation có cùng semantics:** snapshot và phantom handling khác nhau giữa các engine.
- **Dùng READ UNCOMMITTED để chữa blocking:** có thể đọc dữ liệu chưa commit hoặc không đem lại khác biệt trên engine không hỗ trợ dirty read.
- **Cho rằng REPEATABLE READ ngăn mọi write skew:** snapshot isolation không tự bảo vệ mọi invariant nhiều dòng.
- **Giữ transaction mở trong lúc gọi API:** kéo dài snapshot, lock và vòng đời phiên bản.
- **Chỉ theo dõi query duration:** transaction có thể idle nhưng vẫn giữ snapshot lâu.
- **Chỉ tăng dung lượng undo/tempdb:** không xử lý transaction hoặc cleanup đang bị chặn.
- **Chạy VACUUM FULL/rebuild như bước đầu:** thao tác có thể khóa hoặc tạo tải lớn mà không xử lý nguyên nhân giữ phiên bản.
- **Retry mọi lỗi không giới hạn:** có thể khuếch đại tải và lặp tác dụng phụ.
- **Benchmark chỉ có reader:** bỏ qua version generation, purge, log và write conflict.
- **Chia batch mà không xác định snapshot:** các batch có thể đọc những trạng thái dữ liệu khác nhau.
- **Bỏ qua version store/undo trong dự báo dung lượng:** workload cập nhật cao có thể làm vùng lưu trữ tăng đột biến.

## 15. Checklist chọn isolation và vận hành MVCC

- [ ] Đã mô tả invariant nghiệp vụ và anomaly cần ngăn chặn.
- [ ] Đã xác minh semantics thực tế của isolation level trên đúng engine/phiên bản.
- [ ] Đã phân biệt consistent read với locking read.
- [ ] Đã dùng atomic update hoặc optimistic concurrency khi phù hợp.
- [ ] Đã xác định trường hợp cần khóa dòng/phạm vi hoặc SERIALIZABLE.
- [ ] Đã có retry có giới hạn cho deadlock, serialization failure và update conflict.
- [ ] Đã giữ transaction ngắn và tránh chờ mạng/người dùng khi đang mở transaction.
- [ ] Đã theo dõi transaction age, idle-in-transaction và snapshot lâu nhất.
- [ ] Đã theo dõi vacuum/purge/version store/undo và dung lượng log tương ứng engine.
- [ ] Đã đo tốc độ DML, version generation, cleanup lag và I/O.
- [ ] Đã benchmark workload đọc/ghi đồng thời với dữ liệu đại diện.
- [ ] Đã kiểm thử lost update, phantom, write skew và các invariant quan trọng.
- [ ] Đã xác định cách chia batch mà vẫn giữ semantics dữ liệu cần thiết.
- [ ] Đã có dashboard/cảnh báo cho lock wait, deadlock, version growth và transaction dài.

Mức cô lập quyết định những trạng thái đồng thời mà transaction được phép quan sát; MVCC giúp cung cấp phiên bản phù hợp để đọc mà không buộc mọi reader chờ writer. Cơ chế này vẫn tạo chi phí lưu phiên bản, log, undo và cleanup, đặc biệt khi transaction giữ snapshot lâu. Khi chọn isolation theo invariant, giữ transaction ngắn, theo dõi vòng đời phiên bản và benchmark tải đọc/ghi cùng nhau, hệ thống có thể duy trì tính đúng đắn mà vẫn kiểm soát được tranh chấp và chi phí vận hành.
