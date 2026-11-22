# Thời gian giao dịch và ảnh hưởng đến số phiên chờ

Một giao dịch cơ sở dữ liệu càng kéo dài thì tài nguyên mà nó đang sử dụng hoặc giữ lại càng lâu. Nếu giao dịch giữ khóa trên một hàng, trang hoặc phạm vi dữ liệu mà giao dịch khác cũng cần truy cập, các yêu cầu đến sau có thể phải chờ. Khi nhiều yêu cầu cùng tranh chấp một tài nguyên nóng, thời gian chờ có thể tăng nhanh hơn nhiều so với phần thời gian giao dịch được kéo dài.

Vì vậy, khi điều tra transaction contention, không chỉ đo thời gian chạy của từng câu SQL. Cần biết giao dịch bắt đầu lúc nào, khóa được lấy ở thời điểm nào, khóa được giữ đến khi nào, phiên nào đang chặn phiên nào và có bao nhiêu yêu cầu đang xếp hàng. Một câu truy vấn chạy nhanh vẫn có thể nằm trong một transaction mở lâu; ngược lại, một truy vấn chạy lâu nhưng không giữ tài nguyên độc quyền có thể không tạo ra nhiều phiên chờ khóa.

Trong phạm vi DATABASE_PERFORMANCE, bài học này giải thích mối quan hệ giữa thời gian giao dịch, mức đồng thời và số phiên chờ; cách đọc wait và blocking trên các hệ quản trị phổ biến; cùng các biện pháp rút ngắn thời gian giữ tài nguyên mà vẫn bảo toàn tính đúng đắn của nghiệp vụ.

## 1. Phân biệt thời gian câu lệnh, thời gian giao dịch và thời gian chờ

Ba khoảng thời gian thường bị gộp nhầm:

- **Statement duration:** thời gian một câu SQL được thực thi, từ lúc DB bắt đầu xử lý câu lệnh đến khi câu lệnh hoàn tất theo cách đo của công cụ.
- **Transaction duration:** thời gian từ lúc transaction bắt đầu đến khi COMMIT hoặc ROLLBACK hoàn tất.
- **Wait duration:** tổng hoặc khoảng thời gian một phiên phải chờ một tài nguyên, chẳng hạn khóa, I/O, bộ nhớ, worker hoặc kết nối.

Một transaction có thể chứa nhiều câu lệnh, thời gian ứng dụng suy nghĩ giữa các câu lệnh và cả những khoảng không gửi SQL nào. Ví dụ:

```text
BEGIN
  SELECT ... FOR UPDATE;     -- lấy khóa hàng
  đọc và kiểm tra dữ liệu
  gọi dịch vụ thanh toán     -- chờ mạng 900 ms
  UPDATE ...
COMMIT
```

Nếu câu SELECT và UPDATE chỉ mất tổng cộng 15 ms nhưng ứng dụng giữ transaction mở 900 ms để chờ dịch vụ thanh toán, khóa được lấy từ câu SELECT có thể bị giữ gần như suốt khoảng thời gian đó. Các phiên cần cùng hàng có thể phải chờ dù DB không thực thi SQL liên tục.

### Phiên hoạt động không đồng nghĩa phiên đang chạy SQL

Một connection có thể ở nhiều trạng thái:

| Trạng thái | Ý nghĩa | Có thể giữ tài nguyên giao dịch? |
|---|---|---|
| Đang chạy câu SQL | DB đang thực thi lệnh | Có |
| Đang chờ khóa | Câu lệnh chưa thể tiếp tục vì tài nguyên bị giữ | Có thể đang giữ khóa khác và đồng thời chờ khóa mới |
| Idle in transaction | Không chạy SQL nhưng transaction chưa kết thúc | Có, tùy các thao tác trước đó và DBMS |
| Idle/autocommit đã hoàn tất | Không có transaction mở | Thông thường không giữ khóa giao dịch |
| Chờ lấy connection trong pool | Ứng dụng chưa có session DB để gửi SQL | Không phải phiên đang chờ khóa trong DB |

Số connection đang mở, số session đang active, số transaction đang mở và số session đang chờ là các đại lượng khác nhau. Không nên nhìn tổng connection rồi kết luận tất cả đều đang tranh chấp.

## 2. Vì sao transaction dài làm tăng số phiên chờ?

Transaction có thể giữ khóa hoặc trạng thái snapshot trong thời gian dài. Khi một transaction giữ tài nguyên mà transaction khác cần, các yêu cầu đến sau không thể hoàn tất ngay. Nếu tốc độ yêu cầu tiếp tục đến trong khi tài nguyên chưa được giải phóng, hàng đợi tăng lên.

Một chuỗi đơn giản:

1. Phiên A bắt đầu transaction và khóa một hàng tài khoản.
2. Phiên B cần cập nhật cùng hàng nên phải chờ A commit hoặc rollback.
3. Phiên C cũng cần hàng đó và tiếp tục xếp hàng.
4. A chờ một dịch vụ bên ngoài trước khi commit.
5. B và C không thể hoàn tất dù câu SQL của chúng rất ngắn.

Thời gian của A tác động đến B và C. Nếu có nhiều hàng hoặc tài nguyên nóng cùng bị giữ, một transaction dài có thể làm tăng số waiter trên nhiều điểm khác nhau.

### Thời gian giữ khóa quan trọng hơn thời gian mở transaction đơn thuần

Không phải mọi transaction dài đều giữ cùng một loại khóa từ đầu đến cuối. Một transaction có thể mở trước khi truy cập dữ liệu, chỉ lấy khóa khi chạy câu lệnh đầu tiên, hoặc chỉ giữ một số khóa sau khi cập nhật. Quy tắc giữ và giải phóng phụ thuộc DBMS, isolation level, loại khóa và câu lệnh.

Với nhiều hệ quản trị, khóa ghi trên hàng thường được giữ đến khi transaction kết thúc. Khóa đọc có thể được giải phóng sớm ở một số isolation level, hoặc được thay bằng cơ chế versioning. Khóa phạm vi, predicate lock, schema lock và khóa metadata có quy tắc riêng.

Do đó, cần đo riêng:

- Thời gian transaction mở.
- Thời điểm lấy khóa đầu tiên và thời điểm giải phóng khóa cuối cùng.
- Tổng thời gian chờ khóa của các phiên bị ảnh hưởng.
- Thời gian ứng dụng nằm ngoài DB nhưng vẫn giữ transaction.

Một transaction mở lâu nhưng chưa lấy khóa có thể gây ảnh hưởng qua snapshot, undo hoặc vacuum mà không nhất thiết tạo lock waiter. Một transaction ngắn nhưng khóa đúng hàng nóng có thể tạo hàng đợi rõ rệt trong giờ cao điểm.

## 3. Định luật Little: liên hệ giữa tốc độ đến, thời gian và số giao dịch đồng thời

Định luật Little mô tả một hệ thống ổn định:

```text
L = λ × W
```

Trong đó:

- **L** là số yêu cầu hoặc giao dịch trung bình đang ở trong phạm vi hệ thống được đo.
- **λ** là tốc độ yêu cầu hoàn tất/đến trung bình, tính theo yêu cầu mỗi giây.
- **W** là thời gian trung bình một yêu cầu ở trong phạm vi đó.

Giả sử ứng dụng nhận và hoàn tất trung bình 40 transaction mỗi giây:

| Thời gian transaction trung bình | Số transaction đang mở trung bình ước tính |
|---:|---:|
| 0,25 giây | 40 × 0,25 = 10 |
| 0,50 giây | 40 × 0,50 = 20 |
| 0,75 giây | 40 × 0,75 = 30 |
| 1,00 giây | 40 × 1,00 = 40 |

Nếu tốc độ đến không đổi, tăng thời gian transaction từ 250 ms lên 750 ms có thể làm số transaction đồng thời trung bình tăng từ khoảng 10 lên khoảng 30. Nhiều transaction đồng thời hơn làm tăng số connection bị chiếm, bộ nhớ trạng thái giao dịch và cơ hội các giao dịch đụng vào cùng tài nguyên.

Định luật Little áp dụng cho trung bình trong một hệ thống ổn định, với λ và W được đo trên cùng một phạm vi. Nó không tự dự báo p95/p99, burst ngắn hoặc số waiter khóa cụ thể. Số transaction đồng thời cũng không bằng số phiên chờ: nhiều transaction có thể chạy song song mà không chặn nhau.

### Phân biệt concurrency và queue length

- **Concurrency:** số công việc đang tồn tại hoặc đang được xử lý cùng lúc.
- **Queue length:** số công việc đang phải chờ một tài nguyên hoặc một bước xử lý.
- **Blocked sessions:** các phiên DB bị chặn bởi phiên khác.
- **Pool pending requests:** yêu cầu ứng dụng đang chờ connection từ pool.

Khi transaction duration tăng, concurrency thường tăng nếu throughput giữ nguyên. Queue length chỉ tăng mạnh khi tài nguyên có giới hạn hoặc có tranh chấp; mức tăng phụ thuộc phân bố tải, thời gian giữ tài nguyên và cách hệ thống lập lịch.

## 4. Hàng đợi khóa có thể tăng phi tuyến

Với một tài nguyên độc quyền, có thể hình dung một hàng đợi đơn giản: mỗi transaction giữ khóa trong một khoảng thời gian S; yêu cầu đến với tốc độ λ. Mức sử dụng tài nguyên xấp xỉ:

```text
ρ = λ × S
```

Khi ρ tiến gần 1, tài nguyên gần như luôn bận và thời gian chờ có thể tăng rất nhanh. Nếu ρ vượt 1 trong thời gian dài, hàng đợi không thể ổn định vì yêu cầu đến nhanh hơn khả năng giải phóng tài nguyên.

Ví dụ minh họa với một khóa nóng chỉ cho phép một transaction ghi tại một thời điểm:

| Tốc độ yêu cầu đến | Thời gian giữ khóa | Mức sử dụng ρ |
|---:|---:|---:|
| 5 lần/giây | 100 ms | 0,50 |
| 5 lần/giây | 160 ms | 0,80 |
| 5 lần/giây | 180 ms | 0,90 |
| 5 lần/giây | 195 ms | 0,975 |

Chỉ tăng thời gian giữ khóa từ 100 ms lên 195 ms đã đưa tài nguyên từ mức sử dụng 50% lên gần bão hòa. Mô hình này giả định một tài nguyên độc quyền và tốc độ đến tương đối ổn định; hệ thống thật có nhiều khóa, thời gian phục vụ biến thiên và chính sách lập lịch khác nhau. Dù vậy, nó giải thích vì sao một thay đổi nhỏ trong thời gian giữ khóa có thể làm hàng đợi tăng mạnh khi tải đã cao.

### Một waiter có thể kéo theo waiter khác

Blocking có thể tạo thành chuỗi. Ví dụ:

```text
Session A: giữ khóa trên hàng X
    |
    v
Session B: giữ khóa trên hàng Y, chờ hàng X
    |
    v
Session C: chờ hàng Y
```

A là blocker gốc trong chuỗi. B vừa là waiter của A, vừa có thể là blocker của C do đang giữ khóa Y. Nếu chỉ nhìn C, việc kết thúc hoặc tối ưu câu lệnh của C không giải quyết nguyên nhân. Cần tìm blocker gốc và hiểu vì sao A chưa kết thúc transaction.

## 5. Những nguyên nhân làm transaction kéo dài

Transaction dài thường bắt nguồn từ cách ứng dụng xác định ranh giới giao dịch, truy vấn chậm hoặc chờ tài nguyên bên ngoài:

### Công việc ngoài DB nằm trong transaction

- Gọi HTTP/RPC, thanh toán, gửi email hoặc gọi dịch vụ khác.
- Chờ người dùng xác nhận hoặc nhập thêm dữ liệu.
- Đọc/ghi file, upload/download hoặc xử lý ảnh.
- Chờ message broker hoặc một tác vụ bất đồng bộ.
- Thực hiện tính toán CPU nặng sau khi đã khóa hàng.

Nếu transaction đã lấy khóa trước khi thực hiện các việc này, khóa có thể bị giữ trong toàn bộ thời gian chờ.

### Truy vấn bên trong transaction chậm

- Thiếu index hoặc chọn sai access path.
- Sai cardinality estimate dẫn đến join hoặc scan tốn kém.
- Sort/hash spill ra đĩa.
- Truy vấn trả quá nhiều hàng hoặc fetch từng hàng chậm.
- Chờ I/O, worker, memory grant hoặc tài nguyên khác.
- Cập nhật nhiều index, trigger hoặc cascade.

Một câu SQL chậm kéo dài transaction nếu nó nằm trong transaction đang giữ khóa hoặc snapshot. Tối ưu truy vấn có thể rút ngắn thời gian giữ tài nguyên, nhưng cần xác nhận đúng câu lệnh đang kéo dài transaction.

### Ứng dụng không đóng transaction

- Nhánh lỗi bỏ qua rollback.
- Connection được trả về pool khi transaction vẫn mở.
- Framework mở transaction ở lớp cao hơn dự kiến.
- Autocommit bị tắt nhưng không có commit/rollback ở mọi đường đi.
- Cursor hoặc streaming result được giữ mở quá lâu.
- Session ở trạng thái idle in transaction do luồng ứng dụng chờ.

### Transaction quá rộng

Một thao tác nghiệp vụ có thể gom nhiều bước không cần cùng một transaction. Càng nhiều bước, thời gian và số tài nguyên có thể bị giữ càng lớn. Tuy nhiên, tách transaction phải giữ được các invariant nghiệp vụ; không được chia commit nếu điều đó làm lộ trạng thái trung gian không hợp lệ.

## 6. Isolation level và ảnh hưởng đến blocking

Isolation level quyết định cách transaction nhìn thấy thay đổi đồng thời và loại khóa hoặc versioning mà DB sử dụng. Isolation cao hơn có thể tăng tính nhất quán nhưng cũng có thể tăng thời gian chờ hoặc chi phí quản lý phiên bản.

| Isolation/cơ chế | Đặc điểm khái quát | Tác động cần quan sát |
|---|---|---|
| Read Uncommitted | Có thể đọc dữ liệu chưa commit ở hệ quản trị hỗ trợ | Giảm một số chờ đọc nhưng có thể thấy dữ liệu bẩn; không phải giải pháp chung |
| Read Committed | Mỗi câu lệnh đọc dữ liệu đã commit theo semantics DBMS | Có thể dùng shared lock hoặc MVCC tùy engine |
| Repeatable Read | Giữ tính nhất quán đọc trong phạm vi transaction theo DBMS | Có thể giữ khóa lâu hơn hoặc giữ snapshot cũ |
| Serializable | Bảo đảm mức cô lập cao nhất theo semantics DBMS | Có thể phát sinh blocking hoặc serialization failure cần retry |
| Snapshot/RCSI | Đọc phiên bản dữ liệu thay vì chặn người ghi trong nhiều trường hợp | Giảm reader-writer blocking nhưng tăng chi phí version store/undo và vẫn có xung đột ghi |

Không thể so sánh tên isolation level giữa các DBMS như thể chúng có hành vi hoàn toàn giống nhau. Ví dụ, Repeatable Read của PostgreSQL dựa trên snapshot transaction và có thể phát hiện serialization anomaly theo quy tắc riêng; InnoDB Repeatable Read dùng consistent read và next-key locking cho một số thao tác khóa; SQL Server có thể bật READ_COMMITTED_SNAPSHOT để dùng row versioning cho Read Committed.

### MVCC giảm một số loại blocking nhưng không xóa mọi tranh chấp

MVCC cho phép reader đọc phiên bản phù hợp của hàng mà không nhất thiết chờ writer đang sửa hàng đó. Tuy nhiên:

- Hai writer cùng sửa một hàng vẫn có thể phải chờ nhau.
- SELECT FOR UPDATE hoặc thao tác khóa tường minh vẫn có thể chặn phiên khác.
- DDL và metadata lock có quy tắc riêng.
- Serializable có thể hủy transaction để bảo đảm tính đúng đắn.
- Snapshot dài có thể giữ phiên bản cũ lâu, làm vacuum/purge không thể dọn dẹp.
- Lock trên unique key, foreign key hoặc phạm vi dữ liệu vẫn có thể xuất hiện.

Không nên hạ isolation level chỉ để làm số waiter giảm. Trước tiên phải xác định hiện tượng đọc sai nào nghiệp vụ chấp nhận được, rồi mới thay đổi isolation.

## 7. Transaction dài trong các hệ quản trị phổ biến

### PostgreSQL

PostgreSQL dùng MVCC. Các thao tác ghi và khóa hàng thường giữ row lock đến khi transaction kết thúc. Reader thông thường có thể đọc phiên bản đã commit trước đó mà không chờ row lock của writer, nhưng SELECT FOR UPDATE, DDL, advisory lock và một số xung đột khác vẫn có thể chờ.

Transaction lâu hoặc session ở trạng thái idle in transaction có thể giữ snapshot cũ. Điều này có thể ngăn VACUUM thu hồi tuple chết, làm bảng và index phình to, tăng I/O và ảnh hưởng kế hoạch. Cần phân biệt lock contention với tác động của xmin/snapshot cũ.

Xem các transaction đang mở và wait event:

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Các trường xact_start, state và wait_event giúp nhận diện transaction lâu, idle in transaction và phiên đang chờ. pg_blocking_pids trả về PID đang chặn phiên được hỏi. Cần xem cả blocker và waiter, không chỉ phiên có thời gian chờ dài nhất.

Có thể kiểm tra thời gian transaction và trạng thái idle:

```sql
SELECT
    pid,
    state,
    now() - xact_start AS transaction_age,
    now() - state_change AS state_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
```

Quyền xem đầy đủ query và session của người dùng khác phụ thuộc quyền giám sát. Cần cẩn thận với query text vì có thể chứa dữ liệu nhạy cảm.

### MySQL InnoDB

InnoDB dùng row-level locking và MVCC. Khóa ghi thường được giữ đến commit hoặc rollback. Với Repeatable Read, next-key lock/gap lock có thể khóa cả khoảng khóa để bảo vệ điều kiện truy vấn trong một số thao tác locking read, UPDATE hoặc DELETE.

Transaction mở lâu có thể giữ undo cần thiết và làm purge chậm. Điều này làm history list length tăng, dung lượng undo và công việc purge tăng. Một transaction không chạy SQL nhưng chưa commit vẫn có thể giữ khóa và snapshot.

Xem transaction đang mở:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_wait_started,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Trong MySQL 8.0, Performance Schema có các bảng data_locks và data_lock_waits để xem quan hệ khóa/chờ. Có thể dùng view sys.innodb_lock_waits nếu được cài và cấp quyền. SHOW ENGINE INNODB STATUS cung cấp thêm thông tin về deadlock gần nhất và trạng thái InnoDB.

Không phải mọi gap lock đều là vấn đề; chúng có thể cần thiết để giữ semantics isolation. Nếu thấy nhiều waiter, hãy kiểm tra access path, index, isolation level và predicate đang khóa phạm vi nào trước khi thay đổi cấu hình.

### SQL Server

SQL Server có lock manager và nhiều loại khóa như S, U, X, IS, IX, key, page, object và schema. Khóa ghi thường được giữ đến cuối transaction. Lock escalation có thể chuyển nhiều khóa nhỏ thành khóa phạm vi lớn hơn khi điều kiện phù hợp.

READ_COMMITTED_SNAPSHOT hoặc SNAPSHOT isolation dùng row versioning cho đọc trong các trường hợp hỗ trợ, giúp giảm reader-writer blocking. Nhưng writer-writer conflict, schema lock, lock hint và một số thao tác vẫn có thể chờ. Snapshot transaction dài có thể làm version store tăng; vị trí lưu version phụ thuộc cấu hình và phiên bản.

Xem các request đang chờ và blocker:

```sql
SELECT
    r.session_id,
    r.status,
    r.command,
    r.wait_type,
    r.wait_time,
    r.blocking_session_id,
    r.open_transaction_count,
    r.total_elapsed_time,
    DB_NAME(r.database_id) AS database_name
FROM sys.dm_exec_requests AS r
WHERE r.blocking_session_id <> 0
   OR r.open_transaction_count > 0
ORDER BY r.total_elapsed_time DESC;
```

Để xem transaction mở theo session, có thể kết hợp sys.dm_tran_session_transactions, sys.dm_tran_active_transactions và sys.dm_exec_sessions. Các DMV có yêu cầu quyền phù hợp. Wait type bắt đầu bằng LCK_M thường liên quan đến lock wait, nhưng cần xác định resource và blocker cụ thể.

### Oracle

Oracle dùng consistent read và undo để reader thường không chặn writer và writer thường không chặn reader trong các truy vấn đọc thông thường. Tuy nhiên, hai transaction cập nhật cùng hàng vẫn có thể chờ TX enqueue; SELECT FOR UPDATE và DDL/metadata lock cũng có thể tạo chờ.

Transaction dài giữ undo cần thiết để phục hồi và cung cấp consistent read. Query chạy lâu có thể gặp lỗi snapshot too old nếu undo cần thiết bị ghi đè trước khi truy vấn hoàn tất. Cần phân biệt thời gian query đọc lâu với transaction mở lâu và xem undo retention, workload ghi cùng thời điểm.

Xem session đang chờ và blocker:

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    event,
    wait_class,
    seconds_in_wait,
    blocking_session,
    sql_id,
    prev_sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
   OR event LIKE 'enq: TX%'
ORDER BY seconds_in_wait DESC;
```

Quyền truy cập V$SESSION và các view hiệu năng phụ thuộc quyền DBA/catalog. Cần xem transaction gốc, SQL hiện tại và SQL trước đó của blocker để hiểu vì sao khóa chưa được giải phóng.

## 8. Đọc blocking chain và tìm blocker gốc

Một phiên chờ không phải lúc nào cũng là nguyên nhân gốc. Nó có thể đang chờ một phiên khác; phiên đó lại đang chờ một phiên thứ ba. Cần dựng chuỗi blocking để tìm transaction giữ tài nguyên đầu tiên.

Quy trình:

1. Tìm các waiter có wait type/event liên quan đến lock.
2. Lấy session ID/PID của blocker trực tiếp.
3. Xem transaction start time, trạng thái session, SQL hiện tại và SQL gần nhất của blocker.
4. Xác định blocker có đang chờ một tài nguyên khác hay không.
5. Lần theo chuỗi đến phiên không bị chặn nhưng đang giữ khóa.
6. Xác định tài nguyên bị giữ, câu lệnh lấy khóa và thời điểm transaction có thể commit.
7. Đánh giá các waiter khác cùng phụ thuộc vào blocker đó.

### Các chỉ số cần xem cùng nhau

| Chỉ số | Câu hỏi |
|---|---|
| Transaction age | Transaction đã mở bao lâu? |
| Query age | Câu SQL hiện tại chạy bao lâu? |
| Lock wait duration | Phiên đã chờ khóa bao lâu? |
| Blocking session count | Một blocker đang chặn bao nhiêu phiên? |
| Wait type/event | Đang chờ lock, I/O, memory, worker hay tài nguyên khác? |
| Rows locked/modified | Transaction đã khóa hoặc thay đổi bao nhiêu hàng? |
| Open transaction count | Session có transaction chưa kết thúc không? |
| Application name / client | Yêu cầu đến từ service, job hay người dùng nào? |
| SQL fingerprint | Câu lệnh nào thường xuất hiện trong chuỗi chặn? |

Một blocker có thể đang ở trạng thái idle và query hiện tại là NULL hoặc không còn phản ánh câu SQL đã lấy khóa. Vì vậy, cần dùng transaction start, last query, application trace và log để tìm thao tác trước đó.

### Phân biệt lock wait với các loại wait khác

- Lock wait: phiên chờ khóa do transaction khác giữ.
- I/O wait: phiên chờ đọc/ghi storage; không nhất thiết có blocker session.
- CPU/run queue: phiên đã sẵn sàng chạy nhưng chưa được cấp CPU.
- Memory grant wait: phiên chờ vùng nhớ thực thi.
- Latch/buffer wait: chờ cấu trúc đồng bộ nội bộ của DB.
- Network/client wait: DB có thể đang chờ client tiêu thụ hoặc gửi dữ liệu.
- Connection pool wait: ứng dụng chưa lấy được connection; DB có thể không thấy request đó.

Nếu nhầm I/O wait thành lock wait, việc kết thúc transaction blocker sẽ không giải quyết được nút thắt. Hãy phân loại wait event trước khi chọn hành động.

## 9. Transaction duration và connection pool

Connection pool giới hạn số kết nối đồng thời từ ứng dụng đến DB. Một connection được mượn trong suốt thời gian transaction thường không thể phục vụ request khác cho đến khi được trả về.

Nếu mỗi request giữ connection 500 ms và hệ thống nhận 100 request/giây, số connection đang được mượn trung bình có thể vào khoảng 50 theo định luật Little. Nếu transaction hoặc thời gian giữ connection tăng lên 1,5 giây, nhu cầu trung bình có thể tăng lên khoảng 150 connection.

Điều này có thể tạo hai loại hàng đợi khác nhau:

1. Request chờ connection trong pool của ứng dụng.
2. Session đã vào DB nhưng chờ khóa hoặc tài nguyên khác.

Hai hàng đợi có thể cùng xuất hiện. Ví dụ, một số connection bị giữ bởi transaction chờ khóa; pool hết connection; request mới xếp hàng ở ứng dụng. Người vận hành nhìn thấy API timeout nhưng DB chỉ hiển thị một số lượng session chờ nhất định.

### Vì sao tăng pool size có thể làm tình hình tệ hơn?

Nếu DB đang bão hòa CPU, I/O hoặc một khóa nóng, tăng số connection cho phép nhiều transaction cùng tham gia tranh chấp. Điều đó có thể làm số waiter và context switching tăng mà throughput không cải thiện.

Hãy xác định:

- Tổng số connection tối đa trên tất cả instance ứng dụng.
- Active, idle và pending acquire trong từng pool.
- Thời gian giữ connection và thời gian transaction.
- Số session DB active, idle in transaction và blocked.
- Năng lực xử lý thực tế của DB.

Pool size phải dựa trên năng lực DB và mức concurrency cần thiết. Không đặt pool tối đa bằng một con số lớn chỉ để loại bỏ pool wait.

## 10. Đo transaction duration và số phiên chờ

Một dashboard hữu ích nên hiển thị các chỉ số theo thời gian và theo ứng dụng:

### Chỉ số transaction

- Số transaction bắt đầu và hoàn tất mỗi giây.
- Transaction duration p50/p95/p99.
- Số transaction đang mở và tuổi transaction lâu nhất.
- Số session idle in transaction.
- Số transaction vượt ngưỡng thời gian.
- Rows locked/modified và thời gian giữ khóa nếu DBMS cung cấp.

### Chỉ số blocking

- Số waiter hiện tại và số waiter duy nhất trong một khoảng thời gian.
- Tổng lock wait time mỗi phút.
- Lock wait p95/p99.
- Số blocker gốc và số phiên bị chặn bởi từng blocker.
- Deadlock count và lock timeout count.
- Loại resource, object hoặc key thường bị tranh chấp.

### Chỉ số ứng dụng và pool

- Connection acquire wait và timeout.
- Connection hold time.
- Transaction begin-to-commit duration theo endpoint/job.
- Thời gian chờ dịch vụ ngoài trong transaction.
- Số request đang chờ worker.
- Tỷ lệ lỗi, retry và request timeout.

Không chỉ dùng số waiter tại một thời điểm. Một đợt blocking ngắn có thể biến mất trước lúc dashboard refresh. Ghi nhận wait duration, số lần xuất hiện, tổng thời gian chờ và trace của request giúp tái dựng sự cố.

## 11. Ví dụ thực tế: một hàng tài khoản nóng

Một dịch vụ xử lý ghi nợ cần cập nhật số dư và lịch sử giao dịch. Luồng hiện tại:

1. Bắt đầu transaction.
2. SELECT tài khoản FOR UPDATE.
3. Gọi dịch vụ kiểm tra hạn mức qua HTTP.
4. Ghi giao dịch và cập nhật số dư.
5. Commit.

Dịch vụ kiểm tra hạn mức mất trung bình 700 ms. Khóa hàng tài khoản được giữ trong phần lớn thời gian này. Nhiều yêu cầu đồng thời cho cùng một tài khoản phải chờ.

### Dấu hiệu quan sát

- Một số session chờ row lock trên cùng account_id.
- Blocker có transaction age cao nhưng không chạy SQL trong một khoảng thời gian.
- Trace ứng dụng cho thấy span HTTP nằm giữa SELECT FOR UPDATE và COMMIT.
- Pool active tăng, acquire wait tăng và p95 API xấu đi.

### Hướng thiết kế lại

Nếu quy tắc nghiệp vụ cho phép, có thể thực hiện bước kiểm tra dịch vụ ngoài trước khi lấy khóa, sau đó bắt đầu transaction ngắn để khóa hàng, xác minh lại điều kiện quan trọng và ghi thay đổi. Nếu kết quả kiểm tra có thể hết hiệu lực, dùng version, reservation hoặc cơ chế xác nhận để tránh race condition.

Một phương án khác là dùng trạng thái trung gian và outbox/saga cho quy trình nhiều dịch vụ. Khi đó cần thiết kế rõ trạng thái PENDING, xác nhận, bù trừ và xử lý retry. Không được đơn giản chuyển lời gọi HTTP ra ngoài transaction nếu điều đó làm mất tính nguyên tử hoặc cho phép ghi nợ sai.

Sau thay đổi, đo lại:

- Thời gian giữ row lock.
- Số waiter trên account_id.
- Transaction duration p95/p99.
- Connection hold time và pool wait.
- Tỷ lệ xung đột version hoặc retry.
- Tính đúng đắn của số dư khi hai yêu cầu đến đồng thời.

Mục tiêu không chỉ là giảm số phiên chờ; hệ thống phải giữ nguyên invariant tài chính.

## 12. Ví dụ blocking chain giữa nhiều bảng

Giả sử một luồng chuyển đơn hàng và tồn kho:

- Session A cập nhật hàng trong bảng Inventory rồi tiếp tục xử lý.
- Session B cập nhật Order, sau đó cần cập nhật Inventory.
- Session C cần cập nhật Order và phải chờ B.

Nếu B giữ khóa Order trong khi chờ Inventory do A đang giữ, C có thể bị chặn bởi B. Đây là blocking chain:

```text
Session A --holds Inventory--> resource
Session B --waits Inventory; holds Order--> Session A
Session C --waits Order--> Session B
```

Để giảm rủi ro, các luồng nên lấy khóa theo thứ tự nhất quán, ví dụ luôn khóa Inventory trước Order nếu semantics nghiệp vụ cho phép. Transaction cần ngắn và cập nhật tập hàng theo thứ tự ổn định. Nếu hai thao tác cần khóa theo thứ tự khác nhau, deadlock có thể xảy ra ngay cả khi từng câu lệnh riêng lẻ chạy nhanh.

Thứ tự khóa nhất quán làm giảm chu trình chờ nhưng không loại bỏ mọi deadlock. Cần xử lý lỗi deadlock bằng retry có giới hạn và kiểm tra lại điều kiện nghiệp vụ.

## 13. Cách rút ngắn transaction mà vẫn giữ tính đúng đắn

### Thu hẹp ranh giới transaction

- Chỉ bắt đầu transaction khi đã sẵn sàng đọc/ghi dữ liệu cần bảo vệ.
- Commit ngay sau khi hoàn thành phần thay đổi nguyên tử.
- Không giữ transaction mở trong khi chờ người dùng, mạng hoặc file.
- Đóng cursor và trả connection sớm khi không còn cần.
- Đảm bảo mọi nhánh thành công/lỗi đều commit hoặc rollback đúng cách.

### Giảm thời gian câu lệnh bên trong transaction

- Dùng index hỗ trợ predicate, join và foreign key.
- Sửa cardinality estimate và execution plan sai.
- Giảm số hàng cần đọc/cập nhật.
- Tránh cập nhật cột không thay đổi.
- Chia bulk update/delete thành batch nếu nghiệp vụ cho phép.
- Giảm trigger hoặc cascade không cần thiết sau khi đánh giá semantics.

### Giảm phạm vi khóa

- Chỉ khóa các hàng thật sự cần thay đổi.
- Dùng điều kiện WHERE đủ chọn lọc và index phù hợp.
- Tránh SELECT FOR UPDATE trên tập rộng nếu chỉ sửa một hàng.
- Cập nhật nhiều hàng theo thứ tự khóa ổn định.
- Tránh range scan khóa quá rộng do thiếu index hoặc predicate không phù hợp.
- Cân nhắc optimistic concurrency bằng version column nếu xung đột hiếm và retry an toàn.

### Chuyển công việc ngoài DB ra khỏi vùng giữ khóa

Nếu cần gọi dịch vụ ngoài, có thể thực hiện trước transaction rồi xác minh lại điều kiện trong transaction. Nếu cần đảm bảo DB và message broker đồng bộ, dùng transactional outbox hoặc workflow có trạng thái thay vì giữ transaction DB trong lúc đợi mạng.

Không phải nghiệp vụ nào cũng cho phép tách. Hãy liệt kê invariant cần giữ, trạng thái trung gian được phép và hành vi khi một bước thành công còn bước kia thất bại.

## 14. Chọn isolation level và cơ chế đồng thời

Nếu waiter chủ yếu là reader chờ writer, row versioning hoặc MVCC có thể giảm blocking trong một số hệ quản trị. Nếu waiter là writer chờ writer trên cùng hàng, đổi isolation level thường không giải quyết được xung đột dữ liệu.

Trước khi thay đổi isolation:

1. Xác định loại anomaly cần ngăn: dirty read, non-repeatable read, phantom hoặc write skew.
2. Xác định wait xuất phát từ read lock, write lock, range lock hay serialization conflict.
3. Đánh giá khả năng bật row versioning và chi phí version store/undo.
4. Kiểm tra các truy vấn dùng locking read hoặc hint có ghi đè hành vi mặc định không.
5. Thử với workload đồng thời và kiểm tra tính đúng đắn dữ liệu.

### Optimistic concurrency

Với dữ liệu ít xung đột, có thể đọc version rồi cập nhật có điều kiện:

```sql
UPDATE inventory
SET quantity = :new_quantity,
    version = version + 1
WHERE item_id = :item_id
  AND version = :expected_version;
```

Nếu số hàng bị ảnh hưởng bằng 0, dữ liệu đã thay đổi kể từ lần đọc; ứng dụng cần đọc lại và quyết định retry hoặc báo xung đột. Cách này tránh giữ khóa trong suốt thời gian tính toán bên ngoài transaction, nhưng vẫn cần transaction ngắn cho thao tác ghi và phải xác định cách xử lý cạnh tranh.

Optimistic concurrency không phù hợp nếu mọi request đều xung đột trên cùng một hàng và tỷ lệ retry cao. Khi đó cần tuần tự hóa theo khóa nghiệp vụ, hàng đợi hoặc thiết kế lại mô hình dữ liệu.

### Pessimistic locking

SELECT FOR UPDATE hoặc lock hint phù hợp khi cần giữ quyền cập nhật trong một đoạn ngắn và xung đột thường xuyên. Chỉ lấy khóa khi đã sẵn sàng cập nhật, giữ transaction ngắn và khóa theo thứ tự nhất quán.

Khóa tường minh không làm tăng throughput của một tài nguyên độc quyền; nó chỉ làm rõ thứ tự truy cập và bảo vệ semantics. Nếu giữ khóa lâu, nó có thể làm hàng đợi lớn hơn.

## 15. Batch transaction và giới hạn của việc chia nhỏ

Với công việc cập nhật hàng loạt, transaction lớn có thể giữ khóa và log lâu. Chia thành batch với commit giữa các đợt giúp giảm thời gian giữ tài nguyên và tạo điểm tiếp tục. Nhưng không phải mọi nghiệp vụ đều cho phép commit từng phần.

Batch phù hợp khi:

- Mỗi nhóm hàng có thể được xử lý độc lập.
- Trạng thái trung gian được chấp nhận hoặc được ẩn khỏi người dùng.
- Có checkpoint bền vững và retry an toàn.
- Có thể xác minh số hàng đã xử lý.

Không nên chia commit nếu yêu cầu toàn bộ tập thay đổi phải nguyên tử. Khi cần, hãy dùng staging table, trạng thái publish, versioned dataset hoặc quy trình chuyển đổi hai pha phù hợp.

Kích thước batch nên được điều chỉnh theo transaction duration, lock wait, log throughput, I/O và p95/p99 của workload trực tuyến. Batch quá nhỏ làm tăng commit overhead; batch quá lớn vẫn tạo transaction dài.

## 16. Deadlock, lock timeout và retry

Blocking là trạng thái chờ; deadlock là chu trình chờ mà không transaction nào có thể tiếp tục nếu không hủy ít nhất một transaction. DBMS thường phát hiện deadlock và chọn một transaction làm nạn nhân.

Lock timeout xảy ra khi phiên chờ vượt giới hạn cấu hình hoặc ứng dụng. Nó không nhất thiết là deadlock và không tự xác định blocker có lỗi.

Khi gặp lỗi:

- Ghi lại mã lỗi, transaction, SQL fingerprint, resource và blocker.
- Rollback transaction theo đúng trạng thái của driver/DBMS.
- Chỉ retry các lỗi tạm thời được xác định.
- Dùng retry giới hạn với exponential backoff và jitter.
- Bảo đảm thao tác idempotent hoặc có idempotency key.
- Không retry ngay lập tức trong vòng lặp không giới hạn.

Nếu một transaction bị hủy do deadlock, mọi thay đổi trong transaction thường bị rollback theo semantics DBMS. Ứng dụng phải bắt đầu transaction mới và thực hiện lại toàn bộ đơn vị công việc, không chỉ tiếp tục từ câu lệnh cuối.

## 17. Quy trình điều tra sự cố transaction contention

1. **Xác nhận triệu chứng.** Ghi thời điểm, endpoint/job, p95/p99, timeout, số request và số session chờ.
2. **Phân loại wait.** Xác định lock wait hay I/O, CPU, memory, latch, network hoặc pool wait.
3. **Tìm blocker gốc.** Dựng blocking chain và xác định session giữ tài nguyên đầu tiên.
4. **Đo transaction age.** Xem thời điểm bắt đầu, trạng thái, câu lệnh hiện tại và thao tác gần nhất.
5. **Xác định khóa/tài nguyên.** Bảng, hàng, index key, range, metadata hoặc advisory lock.
6. **Nối với trace ứng dụng.** Tìm khoảng thời gian chờ mạng, xử lý CPU hoặc thao tác ngoài DB nằm trong transaction.
7. **Kiểm tra kế hoạch SQL.** Xem scan, row estimate, số hàng bị khóa, index và thời gian thực thi.
8. **Kiểm tra isolation và phiên bản.** Xem row versioning, snapshot, gap/range lock, lock escalation hoặc vacuum/undo.
9. **Đề xuất thay đổi có mục tiêu.** Rút ngắn transaction, thu hẹp predicate, sửa index, thống nhất thứ tự khóa hoặc thay đổi concurrency control.
10. **Đo lại cùng workload.** So sánh transaction duration, waiter count, lock wait time, deadlock, throughput và p95/p99.

Trong sự cố đang diễn ra, kết thúc một blocker có thể giải phóng hàng đợi nhưng cũng có thể rollback công việc lớn hoặc làm ứng dụng lỗi. Trước khi can thiệp, cần biết transaction nào đang chạy, tác động rollback và quy trình vận hành được phép. Sau khi xử lý tình huống cấp bách, vẫn phải tìm nguyên nhân khiến transaction kéo dài.

## 18. Ví dụ số liệu trước và sau

Giả sử một API xử lý 30 transaction mỗi giây. Mỗi transaction cập nhật cùng một nhóm tài khoản và giữ khóa trung bình 200 ms. Khi transaction được rút ngắn còn 60 ms bằng cách đưa lời gọi HTTP ra ngoài vùng giữ khóa và giảm thời gian SQL, concurrency trung bình và khả năng chồng lấn khóa có thể giảm đáng kể.

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Transaction throughput | 30/s | 30/s |
| Transaction duration trung bình | 900 ms | 300 ms |
| Transaction đồng thời ước tính theo Little | 27 | 9 |
| Thời gian giữ khóa nóng | 200 ms | 60 ms |
| Waiter p95 | 480 ms | 70 ms |
| Deadlock mỗi giờ | 12 | 2 |

Các số liệu là giả định minh họa, không phải dự báo. Việc giảm transaction duration từ 900 ms xuống 300 ms làm số transaction đồng thời trung bình ước tính giảm theo tỷ lệ nếu throughput giữ nguyên. Số waiter và thời gian chờ thực tế còn phụ thuộc phân bố khóa, burst, thời gian giữ khóa và cách DB lập lịch.

Sau thay đổi cần xác minh logic nghiệp vụ. Nếu dịch vụ ngoài được gọi trước transaction, dữ liệu có thể thay đổi giữa lúc kiểm tra và lúc ghi; cần version check, reservation hoặc xác nhận lại điều kiện trước commit.

## 19. Checklist thiết kế và vận hành

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Đã phân biệt statement duration và transaction duration chưa? | Có mốc begin/commit và trace tương ứng |
| Transaction có chờ mạng hoặc người dùng sau khi lấy khóa không? | Đã đo thời gian ngoài DB trong transaction |
| Có session idle in transaction không? | Có dashboard/alert và nguồn ứng dụng |
| Blocker gốc là phiên nào? | Có blocking chain và resource cụ thể |
| Wait là lock hay loại tài nguyên khác? | Đã phân loại wait event/type |
| Có bao nhiêu waiter và tổng lock wait time? | Theo dõi cả số lượng và thời gian |
| Predicate và index có thu hẹp phạm vi khóa không? | Đã xem execution plan và số hàng thực tế |
| Isolation level có cần thiết cho invariant không? | Có phân tích anomaly và semantics |
| Pool wait có bị nhầm với DB lock wait không? | Đã đo hai hàng đợi riêng |
| Có thể rút ngắn transaction hoặc dùng optimistic concurrency không? | Có kiểm tra xung đột và retry |
| Retry có giới hạn và idempotent không? | Có backoff, khóa idempotency và xử lý lỗi |
| Sau điều chỉnh có giảm tác động end-to-end không? | Đã so sánh p95/p99, throughput và tính đúng đắn |

## 20. Những sai lầm thường gặp

- **Chỉ đo thời gian câu SQL:** bỏ qua thời gian transaction vẫn mở giữa các câu lệnh.
- **Coi mọi session mở là session đang chờ:** connection idle, active và blocked có ý nghĩa khác nhau.
- **Tăng connection pool để chữa lock wait:** có thể làm tăng concurrency và tranh chấp trên DB.
- **Kết thúc blocker mà không đánh giá rollback:** có thể làm mất công việc lớn hoặc tạo lỗi dây chuyền.
- **Hạ isolation level theo cảm tính:** có thể tạo dirty read, write skew hoặc kết quả không nhất quán.
- **Đưa lời gọi mạng ra ngoài transaction mà không xác minh lại:** có thể tạo race condition và vi phạm invariant.
- **Chỉ nhìn waiter count tức thời:** bỏ lỡ các đợt blocking ngắn hoặc waiter đã timeout.
- **Nhầm I/O wait với lock wait:** xử lý sai nguyên nhân gốc.
- **Không theo dõi idle in transaction:** session không chạy SQL vẫn có thể giữ khóa hoặc snapshot.
- **Retry không giới hạn:** làm tăng tải đúng lúc hệ thống đang tranh chấp.
- **Chỉ tối ưu blocker mà bỏ qua workload tạo ra nó:** sự cố có thể tái diễn ở đợt tải tiếp theo.

## 21. Nguyên tắc ra quyết định

Thời gian transaction quyết định khoảng thời gian trạng thái giao dịch và nhiều loại khóa có thể tồn tại. Khi tải tăng, transaction dài làm số giao dịch đồng thời tăng theo quan hệ trung bình của định luật Little; nếu nhiều giao dịch cần cùng tài nguyên độc quyền, hàng đợi khóa có thể tăng rất nhanh khi mức sử dụng tiến gần bão hòa.

Hãy đo transaction duration, lock hold time, waiter count, wait duration và blocking chain riêng biệt. Nối số liệu DB với trace ứng dụng để phát hiện thời gian chờ mạng hoặc xử lý ngoài DB nằm trong transaction. Sau đó rút ngắn ranh giới giao dịch, thu hẹp phạm vi khóa, cải thiện truy vấn và chỉ điều chỉnh isolation khi semantics cho phép.

Một cải thiện tốt phải làm giảm thời gian chờ và độ trễ end-to-end mà vẫn bảo toàn tính đúng đắn khi nhiều giao dịch xảy ra đồng thời. Số phiên chờ giảm chỉ là một tín hiệu; throughput, p95/p99, deadlock, tính nhất quán và độ ổn định của workload đều cần được kiểm chứng.
