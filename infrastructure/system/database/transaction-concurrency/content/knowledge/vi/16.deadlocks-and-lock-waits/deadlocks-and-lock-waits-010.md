# Đọc bằng chứng bế tắc để xác định câu lệnh và tài nguyên liên quan

Khi nhiều giao dịch cùng truy cập dữ liệu, một giao dịch có thể phải chờ khóa do giao dịch khác đang giữ. Nếu các giao dịch tạo thành một vòng chờ mà không giao dịch nào có thể tiếp tục, hệ quản trị cơ sở dữ liệu (DBMS) phát hiện **bế tắc (deadlock)** và thường hủy một giao dịch làm nạn nhân để phá vỡ vòng chờ.

Muốn xử lý đúng nguyên nhân, cần đọc bằng chứng do DBMS ghi nhận: giao dịch nào tham gia, câu lệnh nào đang chạy, mỗi giao dịch đang giữ tài nguyên gì, đang chờ tài nguyên gì và DBMS đã chọn giao dịch nào làm nạn nhân. Chỉ nhìn thông báo “deadlock detected” hoặc tên wait type thường chưa đủ để xác định lỗi nằm ở câu lệnh, thứ tự truy cập hay thiết kế dữ liệu.

Bài này trình bày cách đọc deadlock graph và thông tin lock wait, sau đó đối chiếu với công cụ của SQL Server, PostgreSQL và MySQL/InnoDB. Tên cột, loại tài nguyên và cách lưu bằng chứng khác nhau theo DBMS và phiên bản; cần dùng đúng nguồn chẩn đoán của hệ thống đang vận hành.

## 1. Phân biệt lock wait và deadlock

**Lock wait** là tình huống một giao dịch yêu cầu khóa nhưng khóa đó đang được giữ ở chế độ không tương thích. Giao dịch chờ có thể tiếp tục khi giao dịch giữ khóa commit, rollback hoặc giải phóng khóa theo cơ chế của DBMS.

**Deadlock** xảy ra khi tồn tại một chu trình chờ. Mỗi giao dịch trong chu trình đang chờ tài nguyên do một giao dịch khác trong cùng chu trình giữ. Không giao dịch nào có thể tự tiến lên để giải phóng tài nguyên cho giao dịch kế tiếp.

Ví dụ hai giao dịch cập nhật hai tài khoản theo thứ tự ngược nhau:

```text
Transaction A                    Transaction B
     |                                 |
     | khóa hàng Account 101           |
     |                                 | khóa hàng Account 202
     | yêu cầu khóa 202                |
     | phải chờ B                      |
     |                                 | yêu cầu khóa 101
     |                                 | phải chờ A
     +------------- DEADLOCK ----------+
```

Sơ đồ chờ:

```text
      A  ──chờ khóa do──>  B
      ^                    |
      |                    |
      └──chờ khóa do───────┘
```

Một lock wait đơn lẻ không nhất thiết là deadlock. Nếu A chờ B, nhưng B không chờ tài nguyên nào của A và có thể commit, đó chỉ là chờ khóa. Nếu A chờ B, B chờ C và C chờ A, vòng chờ đã hình thành.

| Dấu hiệu | Lock wait | Deadlock |
|---|---|---|
| Quan hệ chờ | Một hoặc nhiều giao dịch đang chờ | Có chu trình chờ khép kín |
| Có thể tự hết khi blocker commit? | Thường có | Không thể nếu chu trình còn nguyên |
| DBMS cần chọn nạn nhân? | Không nhất thiết | Thường có để phá chu trình |
| Bằng chứng hữu ích | Waiter, blocker, tài nguyên và thời gian chờ | Toàn bộ chu trình, tài nguyên, chế độ khóa và victim |
| Kết quả thường thấy | Câu lệnh tiếp tục sau khi được cấp khóa | Một transaction bị rollback hoặc nhận lỗi deadlock |

DBMS thường phát hiện deadlock bằng cách theo dõi đồ thị chờ hoặc cơ chế tương đương. Khi phát hiện chu trình, hệ thống chọn một transaction làm victim. Việc chọn victim dựa trên chính sách nội bộ như chi phí rollback, mức ưu tiên hoặc lượng công việc; không nên giả định transaction bắt đầu sau luôn là victim.

## 2. Đọc bằng chứng theo một trình tự cố định

Một deadlock report có thể chứa nhiều trường kỹ thuật. Đọc theo trình tự sau giúp chuyển từ thông tin thô sang nguyên nhân có thể sửa:

1. **Xác định sự kiện:** thời điểm, DBMS, database, phiên bản, mã lỗi và loại deadlock.
2. **Xác định các transaction:** session/process ID, transaction ID, ứng dụng, người dùng và thời điểm bắt đầu transaction.
3. **Xác định victim:** giao dịch nào bị chọn hủy và lỗi được trả về cho ứng dụng nào.
4. **Đọc chu trình chờ:** A chờ tài nguyên nào do B giữ; B chờ tài nguyên nào do A hoặc giao dịch khác giữ.
5. **Tìm câu lệnh:** xác định câu lệnh đang chờ và câu lệnh đang giữ khóa tại thời điểm deadlock.
6. **Giải mã tài nguyên:** bảng, index, partition, key, page, row, metadata hay tài nguyên đồng bộ khác.
7. **Đối chiếu đường đi dữ liệu:** kiểm tra thứ tự truy cập bảng/index, predicate, kế hoạch thực thi và ranh giới transaction.
8. **Đề xuất thay đổi và đo lại:** kiểm thử cùng workload để xác nhận chu trình đã biến mất và không tạo điểm nghẽn mới.

Không nên bắt đầu bằng việc sửa ngay câu lệnh của victim. Victim là transaction DBMS chọn để phá deadlock; transaction gây ra chu trình có thể là một transaction khác, và nguyên nhân thường nằm ở cách nhiều luồng truy cập tài nguyên theo thứ tự không thống nhất.

## 3. Hiểu cấu trúc deadlock graph

Nhiều DBMS cung cấp deadlock graph hoặc báo cáo có cấu trúc tương đương. Dù định dạng khác nhau, một đồ thị thường cần trả lời bốn câu hỏi:

- Những transaction/process nào tham gia?
- Transaction nào đang sở hữu khóa hoặc tài nguyên?
- Transaction nào đang yêu cầu khóa hoặc tài nguyên đó?
- Tài nguyên nào tạo ra cạnh chờ giữa các transaction?

Một đồ thị khái niệm:

```text
              Resource R1
       owner: Transaction A
       waiter: Transaction B
                    |
                    v
              Transaction B
                    |
                    | đang chờ R2
                    v
              Resource R2
       owner: Transaction B
       waiter: Transaction A
                    |
                    v
              Transaction A
```

Trong báo cáo thực tế, cần phân biệt:

- **Owner/holder:** transaction đang giữ tài nguyên ở một chế độ khóa nhất định.
- **Waiter/requester:** transaction đang yêu cầu tài nguyên và chưa được cấp.
- **Lock mode:** chế độ khóa đang giữ hoặc đang yêu cầu, ví dụ shared, update, exclusive hoặc chế độ đặc thù của DBMS.
- **Resource:** đối tượng bị khóa hoặc tài nguyên đồng bộ mà transaction đang chờ.
- **Victim:** transaction DBMS chọn hủy để phá vòng chờ.

Một tài nguyên có thể có nhiều owner nếu các chế độ khóa tương thích. Vì vậy, đừng diễn giải owner-list thành “chỉ một giao dịch đang giữ tài nguyên”. Hãy đọc cả chế độ khóa và danh sách waiter.

### Victim không đồng nghĩa với thủ phạm duy nhất

Victim là giao dịch bị rollback. Nó có thể là transaction nhỏ nhất hoặc ít tốn chi phí rollback theo chính sách của DBMS, nhưng không nhất thiết là transaction được thiết kế sai. Nếu chỉ sửa code của victim, chu trình có thể xuất hiện lại khi cùng hai luồng chạy đồng thời.

Hãy giữ lại cả câu lệnh của victim lẫn câu lệnh của các transaction còn lại. Cần phân tích toàn bộ thứ tự lấy tài nguyên để tìm ra cạnh nào có thể bị loại bỏ bằng cách chuẩn hóa thứ tự truy cập hoặc rút ngắn thời gian giữ khóa.

## 4. Từ process/session ID đến câu lệnh SQL

Thông tin session ID chỉ giúp định danh phiên kết nối tại thời điểm sự kiện. Để biết giao dịch làm gì, cần nối ID đó với câu lệnh, ứng dụng và transaction.

Các trường đáng chú ý gồm:

| Trường | Ý nghĩa khi điều tra |
|---|---|
| Session/process ID | Định danh phiên DB tại thời điểm sự kiện; có thể được tái sử dụng sau đó |
| Transaction ID | Định danh transaction, hữu ích khi một session chạy nhiều transaction theo thời gian |
| Application name/client app | Tìm service, worker, batch hoặc phiên bản ứng dụng gửi câu lệnh |
| Hostname/client address | Xác định nguồn kết nối hoặc máy chạy worker |
| Login/user/schema | Xác định danh tính thực thi và ngữ cảnh quyền |
| Transaction start time | Phát hiện transaction mở lâu hoặc giữ khóa qua nhiều bước |
| Current statement/input buffer | Câu lệnh đang chạy hoặc batch gần nhất được ghi nhận |
| Execution stack/statement offset | Xác định đoạn lệnh cụ thể trong batch hoặc procedure |
| Isolation level | Hiểu quy tắc đọc/ghi và thời gian giữ khóa |
| Wait type/resource | Cho biết loại chờ và tài nguyên mà session đang yêu cầu |

### Câu lệnh hiện tại và câu lệnh trước đó

Một transaction có thể chạy nhiều câu lệnh trước khi deadlock xảy ra. Câu lệnh được ghi trong deadlock report thường là câu lệnh đang thực thi tại thời điểm phát hiện, nhưng transaction có thể vẫn giữ khóa do một câu lệnh trước đó đã lấy.

Ví dụ:

```sql
BEGIN TRANSACTION;

UPDATE Account
SET balance = balance - 100
WHERE account_id = 101;

-- Một số xử lý ứng dụng diễn ra ở đây.

UPDATE Account
SET balance = balance + 100
WHERE account_id = 202;

COMMIT;
```

Nếu transaction đang chờ ở câu UPDATE thứ hai, nó vẫn giữ khóa đã lấy ở câu UPDATE thứ nhất. Chỉ nhìn câu lệnh đang chờ sẽ không cho biết toàn bộ tài nguyên transaction đang giữ. Cần xem cả stack, batch, transaction và các resource owner trong graph.

Ngoài ra, câu lệnh được ghi nhận có thể là một stored procedure hoặc batch lớn. Cần dùng statement offset, execution plan hoặc log ứng dụng để xác định câu lệnh con và tham số thực tế. Tránh kết luận chỉ từ một đoạn SQL đã bị rút gọn hoặc không có giá trị bind.

## 5. Giải mã tài nguyên bị khóa

Tên tài nguyên thường không trực tiếp là tên bảng hoặc giá trị khóa nghiệp vụ. Một DBMS có thể hiển thị ID nội bộ, hash của key, số trang, partition ID hoặc transaction ID.

| Loại tài nguyên thường gặp | Có thể biểu thị | Cần tra cứu thêm |
|---|---|---|
| KEY / index key | Một khóa trong cấu trúc chỉ mục | Tên index, bảng, key value hoặc hash key |
| RID / row identifier | Vị trí hàng vật lý | Bảng/heap, file, page và slot |
| PAGE | Trang dữ liệu hoặc trang chỉ mục | Database, file, page ID và đối tượng sở hữu trang |
| OBJECT / TABLE | Đối tượng bảng hoặc cấu trúc liên quan | Schema, object ID, loại khóa và partition |
| HOBT / partition | Heap hoặc B-tree/partition nội bộ trong SQL Server | Mapping sang partition, index và object |
| transaction ID | Transaction đang giữ hoặc được tham chiếu bởi khóa | Session sở hữu transaction và trạng thái của nó |
| relation / tuple / transactionid | Đối tượng hoặc phiên bản/transaction trong PostgreSQL | `pg_locks`, `pg_class`, `pg_stat_activity` |
| record / gap / next-key | Bản ghi hoặc khoảng khóa trong InnoDB | Schema, table, index, key và predicate truy vấn |
| metadata/schema lock | Định nghĩa hoặc metadata đối tượng | DDL, transaction sử dụng object và loại metadata lock |

### Khóa hàng không phải lúc nào cũng hiện thành tên hàng

Một số DBMS khóa bản ghi chỉ mục thay vì hiển thị trực tiếp giá trị hàng. Trong PostgreSQL, transaction chờ khóa hàng thường được thể hiện qua chờ khóa `transactionid` của transaction đang giữ phiên bản hàng, chứ không nhất thiết xuất hiện như một hàng tuple lock chưa được cấp trong `pg_locks`. Trong InnoDB, `LOCK_DATA` có thể hiển thị giá trị index key nếu có thể giải mã; nếu không, trường này có thể là `NULL`.

Vì vậy, nếu báo cáo hiển thị `transactionid`, `KEY` hash hoặc page ID, không nên kết luận rằng transaction đang khóa “toàn bộ bảng”. Hãy nối tài nguyên nội bộ với metadata bảng/index và câu lệnh đã truy cập nó.

### Chế độ khóa cũng quan trọng như loại tài nguyên

Hai transaction cùng tham chiếu một tài nguyên chưa chắc xung đột nếu chế độ khóa tương thích. Ngược lại, một transaction yêu cầu khóa độc quyền có thể phải chờ nhiều khóa chia sẻ đang được giữ. Đọc cả `granted/requested mode`, `lock mode`, `owner mode` và `waiter mode` theo định dạng DBMS.

## 6. SQL Server: đọc XML deadlock graph

SQL Server ghi deadlock graph dưới dạng sự kiện Extended Events `xml_deadlock_report`. Trên các phiên bản hiện đại, session hệ thống `system_health` thường thu thập sự kiện này theo cấu hình mặc định. Có thể kiểm tra target ring buffer của session:

```sql
SELECT
    XEvent.query('(data/value/deadlock)[1]') AS DeadlockGraph
FROM (
    SELECT CAST(t.target_data AS xml) AS TargetData
    FROM sys.dm_xe_session_targets AS t
    INNER JOIN sys.dm_xe_sessions AS s
        ON s.address = t.event_session_address
    WHERE s.name = N'system_health'
      AND t.target_name = N'ring_buffer'
) AS Data
CROSS APPLY Data.TargetData.nodes(
    'RingBufferTarget/event[@name="xml_deadlock_report"]'
) AS XEventData(XEvent);
```

Ring buffer có giới hạn dung lượng và dữ liệu cũ có thể bị ghi đè. Với hệ thống cần lưu bằng chứng lâu dài, nên cấu hình Extended Events ghi ra event file theo chính sách vận hành, đồng thời giới hạn dung lượng và thời gian lưu phù hợp.

### 6.1. Các phần trong XML graph

Một XML deadlock graph thường có các phần chính:

- `victim-list`: process được SQL Server chọn làm nạn nhân.
- `process-list`: thông tin từng process tham gia, như `spid`, `waitresource`, `waittime`, `lockMode`, `transactionname`, `lasttranstarted`, `clientapp`, `hostname`, `loginname`, `inputbuf` và `executionStack`.
- `resource-list`: tài nguyên bị tranh chấp và danh sách owner/waiter cùng chế độ khóa.

Khi đọc graph:

1. Lấy `victimProcess/@id` trong `victim-list`.
2. Tìm process có `@id` tương ứng trong `process-list` để biết session và câu lệnh của victim.
3. Đọc các process còn lại để xác định transaction đang giữ tài nguyên và transaction đang chờ.
4. Trong `resource-list`, đối chiếu `owner-list` và `waiter-list` để dựng cạnh chờ.
5. Tra `objectname`, `indexname`, `hobtid`, `associatedObjectId`, `fileid` và `pageid` nếu có để xác định bảng/index/partition.
6. Đọc `executionStack` và `inputbuf` để xác định câu lệnh cụ thể; nếu batch dài, xem offset và SQL text tương ứng.

Ví dụ, nếu graph cho thấy process A giữ khóa `KEY` trên index `IX_Account_CustomerId` và chờ `KEY` trên `PK_Account`, trong khi process B giữ khóa trên `PK_Account` và chờ `IX_Account_CustomerId`, cần kiểm tra hai câu lệnh có truy cập index theo thứ tự khác nhau hay không. Chỉ biết cả hai cùng truy cập bảng `Account` chưa đủ để xác định chu trình.

### 6.2. Xem lock wait đang diễn ra

DMV `sys.dm_exec_requests` giúp xem request hiện đang chờ session khác:

```sql
SELECT
    r.session_id,
    r.blocking_session_id,
    r.status,
    r.wait_type,
    r.wait_time,
    r.wait_resource,
    DB_NAME(r.database_id) AS database_name,
    s.host_name,
    s.program_name,
    s.login_name,
    txt.text AS batch_text
FROM sys.dm_exec_requests AS r
INNER JOIN sys.dm_exec_sessions AS s
    ON s.session_id = r.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS txt
WHERE r.blocking_session_id <> 0;
```

Truy vấn này cho thấy trạng thái hiện tại, không thay thế deadlock graph đã xảy ra. Sau khi SQL Server chọn victim và rollback, request có thể biến mất trước khi người vận hành kịp truy vấn DMV.

Có thể xem các khóa đang tồn tại bằng `sys.dm_tran_locks`, kết hợp `sys.partitions`, `sys.objects`, `sys.indexes` và thông tin session để giải mã tài nguyên. Cần quyền DMV phù hợp trên phiên bản SQL Server đang dùng.

### 6.3. Wait type và wait resource

`LCK_M_*` thường biểu thị một request đang chờ khóa. Hậu tố giúp nhận biết chế độ khóa được yêu cầu, nhưng chỉ wait type không cho biết ai đang giữ khóa hoặc có deadlock hay không. Cần xem `blocking_session_id`, `wait_resource` và deadlock graph.

Một deadlock graph cũng có thể chứa resource không phải khóa dữ liệu, ví dụ `exchangeEvent` liên quan đến các luồng song song. Khi đó, không nên cố giải thích toàn bộ graph bằng thứ tự khóa bảng; cần phân tích đúng loại resource và execution plan.

## 7. PostgreSQL: log deadlock và các view khóa

PostgreSQL ghi deadlock thành lỗi SQLSTATE `40P01` (`deadlock_detected`). Log thường có phần `DETAIL` mô tả process nào chờ loại lock nào, process nào đang giữ, cùng câu lệnh liên quan nếu cấu hình log cho phép.

Một thông báo điển hình có dạng khái niệm:

```text
ERROR: deadlock detected
DETAIL: Process 123 waits for ShareLock on transaction 456;
        blocked by process 789.
        Process 789 waits for ShareLock on transaction 123;
        blocked by process 123.
CONTEXT: while updating tuple (...) in relation "account"
STATEMENT: UPDATE account SET ... WHERE ...;
```

Thông báo cụ thể thay đổi theo phiên bản và loại tài nguyên. Trong ví dụ, `ShareLock on transaction` không có nghĩa câu lệnh đang đọc bảng theo khóa chia sẻ thông thường; đó có thể là cơ chế chờ transaction khác kết thúc để xác định phiên bản hàng có thể cập nhật.

### 7.1. Cấu hình log để giữ bằng chứng

Các tham số thường hữu ích:

- `log_lock_waits = on`: ghi log những lần chờ khóa vượt ngưỡng `deadlock_timeout`.
- `deadlock_timeout`: khoảng thời gian PostgreSQL chờ trước khi kiểm tra deadlock; đây không phải thời gian timeout tổng thể của transaction.
- `log_line_prefix`: nên chứa PID, user, database, application name và transaction ID khi phù hợp để nối các dòng log.
- `log_min_error_statement`: quyết định mức lỗi mà câu lệnh được ghi kèm; deadlock là lỗi nên cần bảo đảm cấu hình log giữ đủ statement.

Không nên tùy tiện giảm `deadlock_timeout` quá thấp trong production chỉ để lấy thêm log, vì việc kiểm tra deadlock thường xuyên hơn có chi phí. Chọn giá trị theo đặc tính workload và yêu cầu chẩn đoán.

### 7.2. Xem waiter và blocker hiện tại

`pg_stat_activity` cung cấp thông tin phiên và câu lệnh; `pg_blocking_pids()` giúp tìm các PID đang chặn một PID khác:

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    now() - a.query_start AS query_age,
    pg_blocking_pids(a.pid) AS blocked_by,
    a.query
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
```

Truy vấn này cho biết các lock wait đang tồn tại. Một deadlock đã được PostgreSQL phát hiện thường đã khiến victim bị hủy, nên cần đọc log để dựng lại sự kiện đã qua.

Để xem tài nguyên khóa, có thể truy vấn `pg_locks`:

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    l.transactionid,
    l.virtualxid,
    a.application_name,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.granted = false
   OR l.pid IS NOT NULL
ORDER BY l.pid, l.locktype;
```

`granted = false` thường là request đang chờ. Các khóa đã cấp cũng hữu ích khi đối chiếu với waiter. Không phải mọi row-level lock đang được giữ đều hiện thành một bản ghi `tuple` dễ đọc trong `pg_locks`; PostgreSQL có thể thể hiện việc chờ cập nhật hàng qua khóa transaction ID. Hãy kết hợp log `DETAIL`, `pg_blocking_pids()`, `pg_stat_activity` và `pg_locks` thay vì dựa vào một view riêng lẻ.

### 7.3. Từ relation OID đến bảng và index

Trường `relation` trong `pg_locks` là OID của relation khi loại khóa có liên quan đến relation. Ép sang `regclass` giúp hiển thị tên đối tượng theo search path. Với các lock type không có relation, trường này có thể null; khi đó cần đọc `locktype`, `transactionid`, `classid`, `objid` và `objsubid` theo đúng ý nghĩa của loại khóa.

Nếu log chỉ ghi `tuple` hoặc `transactionid`, hãy đối chiếu `CONTEXT` và câu lệnh để xác định bảng/hàng. Không suy ra giá trị khóa nghiệp vụ chỉ từ PID hoặc transaction ID.

## 8. MySQL/InnoDB: SHOW ENGINE INNODB STATUS và Performance Schema

InnoDB phát hiện deadlock và chọn một transaction làm victim để rollback. Có thể xem deadlock được phát hiện gần nhất bằng:

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong phần `LATEST DETECTED DEADLOCK`, thường có:

- Hai hoặc nhiều transaction tham gia và trạng thái của chúng.
- Câu lệnh SQL gần nhất được thực thi trong mỗi transaction.
- Khóa transaction đang giữ (`HOLDS THE LOCK(S)`).
- Khóa transaction đang chờ (`WAITING FOR THIS LOCK TO BE GRANTED`).
- Bảng, index, record hoặc gap liên quan.
- Transaction được chọn làm victim.

Đây là bằng chứng hữu ích nhưng chỉ mô tả deadlock gần nhất trong trạng thái được giữ. Nếu nhiều deadlock xảy ra liên tiếp, sự kiện cũ có thể bị thay thế. Có thể bật `innodb_print_all_deadlocks` để ghi tất cả deadlock vào error log theo chính sách vận hành.

### 8.1. Đọc record lock, gap lock và next-key lock

InnoDB có thể dùng record lock trên bản ghi index, gap lock trên khoảng giữa các giá trị index và next-key lock kết hợp record với gap. Deadlock có thể xuất hiện dù hai transaction không cập nhật cùng một giá trị khóa chính, vì một transaction có thể giữ hoặc chờ khoảng khóa liên quan đến predicate và index đang được dùng.

Trong báo cáo, các thông tin như `index PRIMARY`, tên secondary index, `lock_mode X`, `locks rec but not gap`, `gap before rec` hoặc `insert intention` giúp hiểu loại tài nguyên đang xung đột. Cần đối chiếu với thứ tự index scan và điều kiện WHERE; tên bảng đơn thuần chưa đủ.

### 8.2. Xem lock wait hiện tại trong Performance Schema

Trên MySQL 8.0, các bảng `performance_schema.data_locks` và `performance_schema.data_lock_waits` cung cấp thông tin lock đang tồn tại và quan hệ waiter/blocker:

```sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    rt.PROCESSLIST_ID AS waiting_connection,
    bt.PROCESSLIST_ID AS blocking_connection,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_TYPE,
    r.LOCK_MODE AS waiting_lock_mode,
    b.LOCK_MODE AS blocking_lock_mode,
    r.LOCK_DATA AS waiting_lock_data,
    b.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
 AND r.ENGINE = w.ENGINE
JOIN performance_schema.data_locks AS b
  ON b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
 AND b.ENGINE = w.ENGINE
LEFT JOIN performance_schema.threads AS rt
  ON rt.THREAD_ID = w.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = w.BLOCKING_THREAD_ID;
```

Đây là ảnh chụp lock wait hiện tại. Sau khi InnoDB rollback victim, quan hệ chờ của deadlock đã được giải quyết nên truy vấn có thể không còn trả về sự kiện vừa xảy ra. Muốn điều tra deadlock lịch sử, hãy dùng error log hoặc hệ thống thu thập log tập trung.

Để tìm câu lệnh, có thể nối `THREAD_ID` với `performance_schema.events_statements_current` hoặc bảng history tương ứng nếu instrumentation và consumer đã bật. Cần kiểm tra quyền, cấu hình Performance Schema và phiên bản MySQL; không phải mọi statement history đều được lưu mặc định.

## 9. Đọc wait type mà không kết luận vội

Wait type là một tín hiệu để phân loại nguyên nhân chờ, không phải kết luận đầy đủ.

| Bằng chứng | Gợi ý ban đầu | Cần xác nhận |
|---|---|---|
| SQL Server `LCK_M_*` | Request đang chờ khóa | Blocker, resource, lock mode và deadlock graph |
| PostgreSQL `wait_event_type = 'Lock'` | Backend đang chờ một loại lock | `pg_blocking_pids`, `pg_locks`, log và transaction owner |
| MySQL/InnoDB `data_lock_waits` | Transaction đang chờ engine lock | Record/index/gap, statement và transaction đang giữ |
| Metadata lock wait | DDL hoặc truy vấn đang chờ metadata | Transaction giữ metadata lock và object liên quan |
| Latch/buffer/contention wait | Chờ đồng bộ nội bộ hoặc tài nguyên bộ nhớ | Xác định đây có phải deadlock graph hay một loại wait khác |

Một hệ thống có nhiều lock wait kéo dài nhưng không có deadlock. Ngược lại, deadlock có thể được phát hiện và giải quyết nhanh đến mức khi người vận hành chạy truy vấn DMV, không còn waiter nào. Vì vậy, cần giữ log/event graph liên tục thay vì chỉ truy vấn sau khi người dùng báo lỗi.

## 10. Dựng lại timeline từ nhiều nguồn bằng chứng

Deadlock graph thường là ảnh chụp tại thời điểm phát hiện. Để hiểu vì sao transaction giữ khóa lâu, cần ghép nó với log ứng dụng và lịch sử câu lệnh.

Ví dụ timeline:

| Thời điểm | Transaction A | Transaction B |
|---|---|---|
| T1 | Bắt đầu transaction | |
| T2 | Cập nhật hàng 101, giữ khóa | Bắt đầu transaction |
| T3 | | Cập nhật hàng 202, giữ khóa |
| T4 | Yêu cầu hàng 202, chờ B | |
| T5 | | Yêu cầu hàng 101, chờ A |
| T6 | DBMS phát hiện chu trình và chọn victim | DBMS phá chu trình |

Log ứng dụng nên có request ID, job ID, transaction boundary và thời gian bắt đầu/kết thúc. Không ghi thông tin nhạy cảm hoặc payload đầy đủ nếu không cần thiết; có thể log template SQL, mã thực thể đã che bớt và các tham số không nhạy cảm.

Khi ghép các nguồn, hãy lưu ý đồng hồ giữa application server và database server có thể lệch. Ưu tiên timestamp từ nguồn sự kiện gốc và dùng ID tương quan thay vì chỉ so sánh thời gian hiển thị.

## 11. Từ bằng chứng đến nguyên nhân gốc

Sau khi xác định được câu lệnh và tài nguyên, hãy kiểm tra các nhóm nguyên nhân sau:

### Thứ tự truy cập tài nguyên không nhất quán

Transaction A cập nhật bảng `Account` rồi `Ledger`, trong khi transaction B cập nhật `Ledger` rồi `Account`. Cả hai có thể giữ khóa trên đối tượng thứ nhất và chờ đối tượng thứ hai. Chuẩn hóa thứ tự truy cập trong tất cả luồng có thể loại bỏ chu trình.

### Transaction giữ khóa quá lâu

Ứng dụng có thể mở transaction, cập nhật một hàng rồi gọi API bên ngoài hoặc chờ người dùng trước khi commit. Các transaction khác phải chờ lâu hơn, tăng cơ hội hình thành chu trình. Giữ phần transaction ngắn và đưa công việc ngoài DB ra khỏi khoảng đang giữ khóa khi có thể.

### Index và predicate làm phạm vi khóa rộng

Một câu UPDATE có điều kiện thiếu index phù hợp có thể quét nhiều hàng hoặc index entry. Với isolation và DBMS cụ thể, thao tác có thể giữ nhiều khóa hơn dự kiến. Kiểm tra execution plan, index được chọn, số hàng ước lượng/thực tế và predicate.

### Nhiều index hoặc nhiều đường ghi

Một UPDATE có thể sửa cả hàng dữ liệu và nhiều index. Hai câu lệnh cùng bảng nhưng truy cập theo index khác nhau có thể tạo thứ tự lấy khóa khác nhau. Cần xem resource trong graph thay vì chỉ nhìn tên bảng.

### Khóa phạm vi và phantom

Predicate hoặc range scan có thể tạo gap/key-range/predicate lock. Hai transaction tác động vào các khoảng chồng lấn có thể xung đột dù chưa cùng sửa một hàng đang tồn tại. Cần xác định isolation level và index thực tế.

### Deadlock ngoài khóa dữ liệu

Một số graph chứa exchange, worker, metadata hoặc tài nguyên đồng bộ khác. Khi đó, chỉ đổi thứ tự UPDATE có thể không giải quyết đúng nguyên nhân. Đọc loại resource và execution plan trước khi đề xuất sửa.

## 12. Biện pháp khắc phục dựa trên bằng chứng

Không có một cách sửa deadlock dùng chung cho mọi trường hợp. Chọn thay đổi dựa trên chu trình và tài nguyên đã xác định:

| Nguyên nhân được xác nhận | Hướng xử lý có thể thử |
|---|---|
| Hai luồng lấy cùng tập khóa theo thứ tự ngược nhau | Chuẩn hóa thứ tự truy cập bảng, hàng hoặc khóa nghiệp vụ |
| Transaction giữ khóa qua API hoặc thao tác chậm | Rút ngắn transaction; chuyển tác động ngoài DB sang outbox hoặc bước sau commit |
| Quét nhiều hàng do thiếu index | Đánh giá index/predicate và execution plan; giảm số hàng cần đọc/ghi |
| Nhiều hàng cùng bị cập nhật trong một transaction dài | Chia batch hợp lý, commit theo đơn vị nghiệp vụ an toàn |
| Nhiều transaction tranh chấp cùng một hàng nóng | Gộp cập nhật, serialize theo khóa nghiệp vụ hoặc xem lại mô hình dữ liệu |
| Deadlock do gap/key-range hoặc predicate | Xem isolation, index và quy tắc nghiệp vụ; không hạ isolation tùy tiện |
| Metadata/DDL xung đột với truy vấn dài | Lên lịch DDL, rút ngắn transaction đọc và kiểm soát thời điểm deploy |
| Lỗi do retry sai cách | Retry toàn bộ transaction theo loại lỗi có thể retry, có giới hạn và backoff |

### Retry victim đúng cách

Deadlock victim thường nhận lỗi và transaction bị rollback theo quy tắc DBMS. Ứng dụng có thể retry nếu thao tác phù hợp, nhưng phải:

1. Nhận diện đúng mã lỗi deadlock của driver/DBMS.
2. Kết thúc hoặc rollback transaction lỗi trước khi thử lại.
3. Chạy lại toàn bộ đơn vị nghiệp vụ cần thiết, đọc lại dữ liệu và tính toán lại.
4. Giới hạn số lần retry, dùng backoff/jitter khi phù hợp.
5. Bảo đảm tác động ngoài cơ sở dữ liệu không bị lặp ngoài ý muốn; dùng idempotency hoặc transactional outbox khi cần.

Không retry vô hạn và không retry mọi lỗi SQL. Một constraint violation hoặc lỗi dữ liệu thường không biến mất chỉ vì chạy lại.

## 13. Những hiểu lầm thường gặp khi đọc deadlock evidence

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Victim là transaction gây lỗi duy nhất. | Victim chỉ là transaction DBMS chọn hủy; cần phân tích tất cả cạnh trong chu trình. |
| Một lock wait đồng nghĩa deadlock. | Lock wait có thể kết thúc khi blocker commit; deadlock cần chu trình chờ. |
| Tên bảng trong log cho biết chính xác hàng bị khóa. | Resource có thể là index key, page, range, transaction ID hoặc metadata. |
| Câu lệnh trong graph là toàn bộ transaction. | Transaction có thể đã chạy nhiều câu lệnh và vẫn giữ khóa từ thao tác trước. |
| DMV hiện tại luôn cho thấy deadlock vừa xảy ra. | Sau khi victim bị rollback, quan hệ chờ đã biến mất; cần log hoặc event graph lịch sử. |
| Chỉ cần thêm index là hết deadlock. | Index có thể giảm scan nhưng cũng tạo thêm index maintenance và thứ tự khóa khác; cần đo lại. |
| Hạ isolation luôn là cách nhanh nhất. | Có thể làm mất bảo đảm nghiệp vụ hoặc tạo lỗi dữ liệu; cần hiểu resource và invariant trước. |
| Retry câu lệnh cuối là đủ. | Cần retry toàn bộ transaction và tính lại từ dữ liệu mới. |

## 14. Mẫu ghi nhận một sự cố deadlock

Khi xử lý sự cố, có thể lưu một bản ghi kỹ thuật với các trường sau để lần sau so sánh được:

```text
Incident ID:
Timestamp / timezone:
DBMS and version:
Database / schema:
Deadlock event ID:
Victim session / transaction:
Other sessions / transactions:
Application / worker / request IDs:

Cycle:
  Transaction A holds:
  Transaction A waits for:
  Transaction B holds:
  Transaction B waits for:

Statements:
  A current statement:
  A preceding statements in transaction:
  B current statement:
  B preceding statements in transaction:

Resources:
  Table / index / partition / key / page / metadata:
  Lock modes held and requested:
  Isolation level:

Root cause hypothesis:
Evidence supporting the hypothesis:
Change applied:
Validation workload and result:
Remaining risk:
```

Nên lưu deadlock graph/XML hoặc đoạn log gốc cùng với bản phân tích. Không chỉ lưu phần kết luận đã diễn giải, vì khi có thêm sự kiện mới, nhóm vận hành có thể cần đối chiếu lại resource ID, lock mode hoặc câu lệnh ban đầu.

## 15. Quy trình điều tra trong thực tế

Khi nhận được báo cáo deadlock, hãy thực hiện theo thứ tự:

1. Thu thập log hoặc graph gốc, thời điểm, mã lỗi và phiên bản DBMS.
2. Xác định victim và toàn bộ transaction tham gia.
3. Dựng chu trình owner/waiter từ resource list hoặc log detail.
4. Nối session/process ID với application, request/job ID và câu lệnh.
5. Giải mã resource thành bảng, index, partition, key/range hoặc tài nguyên nội bộ.
6. Xem các câu lệnh trước đó trong transaction để tìm khóa được giữ từ đâu.
7. Đối chiếu execution plan, index và isolation level.
8. Chọn một thay đổi nhỏ có thể loại bỏ cạnh chờ hoặc giảm thời gian giữ tài nguyên.
9. Kiểm thử đồng thời với dữ liệu và thứ tự thao tác tương tự production.
10. Theo dõi deadlock rate, lock wait duration, retry count và latency sau khi triển khai.

Đọc bằng chứng bế tắc đúng cách là nối được ba lớp thông tin: **transaction nào tham gia, câu lệnh nào tạo ra yêu cầu khóa, và tài nguyên nào tạo thành chu trình chờ**. Khi đã có đủ ba lớp này, việc sửa thứ tự truy cập, index, transaction boundary hoặc retry policy sẽ dựa trên nguyên nhân cụ thể. Điều đó giúp giảm deadlock mà vẫn giữ các bảo đảm đồng thời mà nghiệp vụ cần.
