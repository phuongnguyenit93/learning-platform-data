# ORA-00054, ORA-00060 và phân biệt chờ khóa với deadlock

Trong Oracle Database, nhiều phiên làm việc có thể cùng đọc và thay đổi dữ liệu. Database dùng lock để bảo vệ tính nhất quán khi một transaction đang sửa dòng hoặc object. Vì vậy, việc một session phải chờ lock là hoạt động bình thường. Vấn đề xuất hiện khi ứng dụng yêu cầu lấy lock ngay nhưng tài nguyên đang bận, thời gian chờ vượt ngưỡng, hoặc nhiều transaction chờ lẫn nhau theo một vòng phụ thuộc.

Hai lỗi thường gặp là:

- **ORA-00054 — resource busy:** session không lấy được lock theo chế độ NOWAIT hoặc hết thời gian chờ được cấu hình. Thường gặp khi chạy DDL trên object đang được transaction khác sử dụng, hoặc khi câu lệnh yêu cầu lock không chờ.
- **ORA-00060 — deadlock detected:** Oracle phát hiện một chu trình chờ lock giữa các transaction. Không transaction nào trong chu trình có thể tiếp tục nếu không có một thao tác bị hủy, vì vậy Oracle chọn một statement để rollback và trả lỗi.

Điểm khác biệt cốt lõi là: **lock wait thông thường có một bên giữ lock và một bên chờ; deadlock có một vòng chờ khép kín giữa nhiều transaction**. ORA-00054 thường biểu thị yêu cầu lock không thể chờ thêm theo chính sách hiện tại. ORA-00060 biểu thị Oracle đã phát hiện chu trình và phá vỡ chu trình đó bằng cách rollback một statement.

## 1. Lock trong Oracle dùng để làm gì?

Lock là cơ chế điều phối truy cập đồng thời. Khi transaction thay đổi một dòng, Oracle giữ row lock để transaction khác không thể ghi đè thay đổi chưa commit theo cách phá vỡ tính nhất quán. Lock thường được giữ đến khi transaction `COMMIT` hoặc `ROLLBACK`.

Ví dụ:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
```

Sau câu lệnh này, transaction giữ lock trên dòng tài khoản đã cập nhật. Nếu session khác muốn cập nhật cùng dòng, nó phải chờ transaction đầu tiên kết thúc hoặc nhận lỗi nếu câu lệnh dùng NOWAIT/timeout.

### 1.1. Oracle không khóa toàn bộ bảng cho mọi UPDATE

Oracle thường dùng row-level locking cho DML. Khi một session cập nhật một số dòng, các dòng đó bị khóa để bảo vệ thay đổi. Một DML statement cũng lấy table lock ở mode phù hợp để phối hợp với DDL và DML khác, nhưng điều đó không có nghĩa toàn bộ bảng bị khóa độc quyền.

Các truy vấn `SELECT` thông thường sử dụng read consistency và thường không phải chờ row lock của transaction đang cập nhật. Một session có thể đọc phiên bản dữ liệu nhất quán trước khi transaction kia commit. Ngược lại, `SELECT ... FOR UPDATE` yêu cầu khóa dòng để chuẩn bị cập nhật nên có thể phải chờ.

### 1.2. Transaction giữ lock đến khi kết thúc

Thông thường, row lock được giữ cho đến `COMMIT` hoặc `ROLLBACK`. Nếu ứng dụng mở transaction, cập nhật một dòng rồi chờ người dùng nhập liệu hoặc gọi một dịch vụ HTTP trước khi commit, lock có thể bị giữ lâu hơn cần thiết.

Transaction dài làm tăng:

- Số session phải chờ cùng một dòng hoặc object.
- Thời gian giữ lock và xác suất contention.
- Khả năng deadlock khi transaction truy cập nhiều tài nguyên theo thứ tự khác nhau.
- Khối lượng undo cần giữ và thời gian rollback khi có lỗi.
- Số kết nối bị chiếm trong connection pool.

Nên giữ transaction ngắn, thực hiện các thao tác cần thiết trong database rồi commit/rollback sớm. Không giữ transaction mở trong khi chờ tương tác người dùng hoặc thực hiện tác vụ mạng lâu.

## 2. Các loại lock thường gặp

Oracle có nhiều loại lock. Khi điều tra ORA-00054 hoặc ORA-00060, cần xác định resource đang bị tranh chấp là row, table, DDL object hay loại resource khác.

### 2.1. TX enqueue — transaction/row lock

`TX` là enqueue liên quan đến transaction. Một tình huống phổ biến là session A đã sửa một row nhưng chưa commit; session B muốn sửa cùng row nên phải chờ transaction A kết thúc.

Wait event thường gặp:

```text
enq: TX - row lock contention
```

Wait event này cho biết session đang chờ một transaction giữ lock liên quan đến row. Nó không tự động có nghĩa là deadlock. Nếu blocker commit hoặc rollback, waiter có thể tiếp tục.

### 2.2. TM enqueue — table-level DML lock

`TM` là enqueue ở cấp table, dùng để phối hợp các thao tác DML và một số thao tác DDL. DML thông thường lấy table lock ở mode tương thích với các DML khác. Một số thao tác như thay đổi cấu trúc bảng hoặc xóa bảng cần lock mạnh hơn và có thể bị chặn.

Wait event có thể gặp:

```text
enq: TM - contention
```

TM contention có thể liên quan đến DDL, foreign key, thao tác trên table hoặc các lock mode không tương thích. Cần xem object và SQL cụ thể trước khi kết luận nguyên nhân.

### 2.3. DDL lock và object/library cache lock

DDL cần bảo vệ định nghĩa object trong lúc thay đổi. Nếu một session đang dùng object hoặc giữ lock tương thích không đủ cho DDL, câu lệnh như `ALTER TABLE`, `DROP TABLE` hoặc `TRUNCATE TABLE` có thể phải chờ.

Các wait liên quan đến object metadata hoặc PL/SQL có thể có tên như `library cache lock`, `library cache pin` hoặc `row cache lock`. Chúng không giống row lock thông thường; cần phân tích theo object, dependency và câu lệnh đang chạy.

### 2.4. Lock mode

Một số lock mode hiển thị trong `V$LOCK`:

| Giá trị `LMODE` / `REQUEST` | Tên mode | Ý nghĩa khái quát |
|---:|---|---|
| 0 | None | Không giữ hoặc không yêu cầu lock |
| 1 | Null | Null mode |
| 2 | Row-S / SS | Row Share / Sub Share |
| 3 | Row-X / SX | Row Exclusive / Sub Exclusive |
| 4 | Share / S | Share |
| 5 | S/Row-X / SSX | Share Row Exclusive |
| 6 | Exclusive / X | Exclusive |

Khả năng tương thích phụ thuộc loại resource và mode. Không nên nhìn riêng con số `LMODE` rồi kết luận một session đang khóa toàn bộ bảng. Cần kết hợp `TYPE`, `ID1`, `ID2`, `REQUEST`, object và câu SQL.

## 3. ORA-00054: resource busy

Thông báo thường gặp:

```text
ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired
```

Lỗi này xảy ra khi câu lệnh cần một lock nhưng không thể lấy lock theo chính sách chờ hiện tại. Một session khác có thể đang giữ lock tương thích không đủ, hoặc câu lệnh đã dùng NOWAIT/timeout và hết thời gian.

### 3.1. Ví dụ DDL bị chặn bởi transaction DML

Giả sử bảng `ORDERS` đang được ứng dụng cập nhật.

**Session A:**

```sql
UPDATE orders
SET order_status = 'PAID'
WHERE order_id = 1001;

-- Chưa COMMIT hoặc ROLLBACK.
```

**Session B:**

```sql
ALTER TABLE orders ADD payment_reference VARCHAR2(100);
```

DDL cần lock phù hợp để thay đổi metadata bảng. Transaction A đang giữ lock liên quan đến bảng, vì vậy DDL ở session B có thể không lấy được lock. Với `DDL_LOCK_TIMEOUT` bằng 0, DDL không chờ mà trả ORA-00054 ngay khi lock cần thiết đang bận.

Nếu session A commit hoặc rollback, session B có thể chạy lại DDL thành công. Đây là lock wait một chiều: B chờ A; A không chờ B. Không có chu trình deadlock.

### 3.2. NOWAIT trong SELECT FOR UPDATE

`SELECT ... FOR UPDATE` yêu cầu khóa các dòng được chọn để session có thể cập nhật an toàn.

Session A:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 10
FOR UPDATE;
```

Session B:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 10
FOR UPDATE NOWAIT;
```

Nếu session A vẫn giữ row lock, session B không chờ mà nhận lỗi resource busy. NOWAIT hữu ích khi ứng dụng muốn phản hồi ngay rằng tài nguyên đang được xử lý ở nơi khác.

### 3.3. WAIT n và SKIP LOCKED

Oracle cho phép điều khiển hành vi chờ của `SELECT FOR UPDATE`:

```sql
SELECT order_id, order_status
FROM orders
WHERE order_id = 1001
FOR UPDATE WAIT 5;
```

Câu lệnh chờ tối đa số giây được chỉ định cho row lock. Khi hết timeout, Oracle trả lỗi timeout phù hợp với câu lệnh và phiên bản; với `SELECT FOR UPDATE WAIT`, có thể gặp ORA-30006. Không nên giả định mọi timeout lock đều luôn trả ORA-00054.

Để bỏ qua các dòng đang bị khóa:

```sql
SELECT order_id, order_status
FROM orders
WHERE order_status = 'NEW'
ORDER BY order_id
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` hữu ích cho nhiều worker cùng lấy việc từ một bảng queue: worker này có thể xử lý dòng khác thay vì chờ dòng worker khác đang giữ. Nó làm thay đổi semantics của kết quả vì các dòng bị khóa sẽ không xuất hiện trong tập kết quả. Không dùng nó cho truy vấn nghiệp vụ cần nhìn thấy mọi dòng.

### 3.4. LOCK TABLE với NOWAIT hoặc WAIT

Có thể yêu cầu lock table tường minh:

```sql
LOCK TABLE orders IN EXCLUSIVE MODE NOWAIT;
```

Nếu lock mode không lấy được ngay, câu lệnh trả lỗi thay vì chờ. Có thể chỉ định WAIT theo cú pháp Oracle hỗ trợ:

```sql
LOCK TABLE orders IN EXCLUSIVE MODE WAIT 10;
```

Table lock thường không phải giải pháp mặc định cho ứng dụng OLTP. Khóa toàn bảng hoặc yêu cầu mode mạnh có thể làm giảm concurrency đáng kể.

## 4. DDL_LOCK_TIMEOUT

`DDL_LOCK_TIMEOUT` điều khiển thời gian DDL chờ trong hàng đợi DML lock trước khi trả lỗi resource busy. Giá trị mặc định là 0, nghĩa là hành vi NOWAIT đối với lock mà DDL cần chờ.

Có thể đặt cho session:

```sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 30;
```

Sau đó DDL có thể chờ tối đa khoảng 30 giây để lấy lock phù hợp. Ví dụ:

```sql
ALTER TABLE orders ADD payment_reference VARCHAR2(100);
```

Nếu transaction đang giữ lock kết thúc trong thời gian đó, DDL có thể tiếp tục. Nếu thời gian chờ hết, DDL vẫn có thể trả ORA-00054.

### 4.1. DDL_LOCK_TIMEOUT không giải quyết mọi vấn đề

Tăng timeout chỉ thay đổi thời gian chờ. Nó không:

- Làm cho transaction blocker commit nhanh hơn.
- Phá vỡ một deadlock.
- Bảo đảm DDL sẽ thành công sau timeout.
- Thay thế việc tìm session giữ lock lâu.
- Làm DDL online hoặc loại bỏ tác động lên workload.

Nếu một transaction giữ lock hàng chục phút, tăng timeout lên một giờ có thể chỉ khiến deployment đứng chờ lâu hơn. Cần tìm nguyên nhân transaction mở lâu và chọn thời điểm triển khai phù hợp.

### 4.2. Xem giá trị DDL_LOCK_TIMEOUT

```sql
SELECT name,
       value,
       isdefault,
       isses_modifiable,
       issys_modifiable
FROM v$parameter
WHERE name = 'ddl_lock_timeout';
```

Giá trị trong `V$PARAMETER` phản ánh cấu hình có hiệu lực ở session hiện tại. Nếu thay đổi cho session, chỉ session đó chịu tác động. Cấu hình hệ thống cần được DBA đánh giá theo chính sách môi trường.

## 5. ORA-00060: deadlock detected

Thông báo thường gặp:

```text
ORA-00060: deadlock detected while waiting for resource
```

Deadlock xảy ra khi các transaction tạo thành một vòng chờ. Mỗi transaction đang giữ một resource mà transaction khác cần, đồng thời lại chờ resource do transaction kia giữ. Không transaction nào có thể tự tiến triển để giải phóng lock.

Oracle phát hiện chu trình và rollback một statement tham gia deadlock để phá vỡ vòng chờ. Transaction còn lại có thể tiếp tục sau khi resource được giải phóng.

### 5.1. Ví dụ deadlock giữa hai dòng

Giả sử bảng `ACCOUNTS` có hai dòng:

| ACCOUNT_ID | BALANCE |
|---:|---:|
| 10 | 1000 |
| 20 | 1500 |

Hai session chuyển tiền theo thứ tự ngược nhau.

**Session A:**

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
```

Session A giữ lock dòng 10.

**Session B:**

```sql
UPDATE accounts
SET balance = balance - 200
WHERE account_id = 20;
```

Session B giữ lock dòng 20.

Sau đó session A muốn cập nhật dòng 20:

```sql
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;
```

A phải chờ B vì B đang giữ row 20.

Session B tiếp tục muốn cập nhật dòng 10:

```sql
UPDATE accounts
SET balance = balance + 200
WHERE account_id = 10;
```

B phải chờ A vì A đang giữ row 10. Lúc này:

```text
Session A giữ row 10 ──────> chờ row 20 do B giữ
        ^                                  |
        |                                  v
Session B chờ row 10 <────── giữ row 20
```

Chu trình đã khép kín. A không thể tiếp tục nếu B chưa nhả row 20; B không thể tiếp tục nếu A chưa nhả row 10. Oracle phát hiện deadlock và trả ORA-00060 cho một statement được chọn để rollback.

### 5.2. Lock wait thông thường khác deadlock

Trường hợp chỉ có Session A giữ row 10 và Session B chờ row 10:

```text
Session A: giữ row 10, đang xử lý
Session B: chờ row 10
```

Đây là lock wait, không phải deadlock. Khi A commit/rollback, B có thể tiếp tục. Không có cạnh chờ ngược từ A sang B.

Trong deadlock:

```text
A giữ tài nguyên 1, chờ tài nguyên 2 của B
B giữ tài nguyên 2, chờ tài nguyên 1 của A
```

Chu trình khiến các session không thể tự giải phóng resource theo thứ tự hiện tại.

### 5.3. Deadlock không nhất thiết chỉ có hai session

Một chu trình có thể gồm ba hoặc nhiều transaction:

```text
T1 giữ A, chờ B
T2 giữ B, chờ C
T3 giữ C, chờ A
```

Oracle phát hiện vòng chờ trong lock graph. Vì vậy, khi điều tra không nên chỉ tìm hai session có cùng table name; cần đọc deadlock graph và xác định toàn bộ resource/session tham gia.

### 5.4. Statement rollback không đồng nghĩa toàn transaction đã rollback

Khi ORA-00060 xảy ra, Oracle rollback statement gây deadlock để phá vỡ chu trình. Các statement trước đó trong transaction có thể vẫn còn hiệu lực chưa commit và transaction vẫn mở.

Ứng dụng nên xử lý lỗi bằng cách rollback transaction hiện tại rồi mới thử lại toàn bộ nghiệp vụ nếu phù hợp. Không nên bắt ORA-00060, bỏ qua lỗi và tiếp tục dùng transaction như thể không có gì xảy ra.

## 6. Phân biệt ORA-00054 và ORA-00060

| Tiêu chí | ORA-00054 | ORA-00060 |
|---|---|---|
| Ý nghĩa | Không lấy được lock theo NOWAIT/timeout | Oracle phát hiện vòng chờ deadlock |
| Hình dạng chờ | Thường là một session chờ resource do session khác giữ | Hai hoặc nhiều transaction chờ lẫn nhau theo chu trình |
| Nguyên nhân thường gặp | DDL gặp DML đang mở; `NOWAIT`; timeout lock | Transaction cập nhật nhiều dòng/object theo thứ tự khác nhau |
| Oracle có phát hiện cycle không? | Không nhất thiết có cycle | Có cycle trong lock dependency graph |
| Cách xử lý đầu tiên | Xác định blocker, chờ hoặc chọn thời điểm DDL; điều chỉnh timeout nếu phù hợp | Đọc deadlock trace, xác định thứ tự lock và sửa transaction logic |
| Retry | Có thể retry sau khi resource được giải phóng hoặc theo backoff | Retry toàn transaction sau rollback, nếu nghiệp vụ idempotent |
| Có phải luôn cần kill session? | Không | Không; Oracle đã rollback một statement để phá deadlock |

Không nên suy luận rằng mọi lock wait lâu sẽ tự biến thành ORA-00060. Nếu không có chu trình, session có thể chờ rất lâu hoặc hết timeout tùy câu lệnh. Deadlock là trạng thái phụ thuộc vòng, không đơn thuần là “chờ quá lâu”.

## 7. Cách tìm session đang chờ và session chặn

Khi điều tra lock contention, cần xác định ít nhất:

- Session waiter: session đang chờ.
- Session blocker: session đang giữ resource mà waiter cần.
- SQL đang chạy và SQL trước đó của blocker.
- Object hoặc row liên quan nếu có thể xác định.
- Thời gian chờ và transaction age.
- Instance chứa session nếu database chạy RAC.

### 7.1. Xem session đang bị chặn qua GV$SESSION

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       event,
       wait_class,
       state,
       seconds_in_wait,
       sql_id,
       blocking_instance,
       blocking_session,
       final_blocking_instance,
       final_blocking_session
FROM gv$session
WHERE blocking_session_status = 'VALID'
ORDER BY seconds_in_wait DESC;
```

`GV$SESSION` tổng hợp session từ các instance trong RAC. `V$SESSION` chỉ phản ánh instance hiện tại. Các cột `BLOCKING_SESSION` và `BLOCKING_INSTANCE` cho biết blocker được Oracle xác định; `FINAL_BLOCKING_SESSION` giúp tìm blocker gốc trong một chuỗi chặn nhiều tầng.

Quyền xem các dynamic performance views thường cần quyền catalog/monitoring phù hợp. Không nên cấp quyền DBA cho tài khoản ứng dụng chỉ để chạy truy vấn chẩn đoán.

### 7.2. Ghép waiter với blocker

```sql
SELECT w.inst_id           AS waiter_inst_id,
       w.sid               AS waiter_sid,
       w.serial#           AS waiter_serial,
       w.username          AS waiter_user,
       w.event             AS wait_event,
       w.seconds_in_wait,
       w.sql_id            AS waiter_sql_id,
       b.inst_id           AS blocker_inst_id,
       b.sid               AS blocker_sid,
       b.serial#           AS blocker_serial,
       b.username          AS blocker_user,
       b.status            AS blocker_status,
       b.sql_id            AS blocker_sql_id,
       b.prev_sql_id       AS blocker_prev_sql_id
FROM gv$session w
JOIN gv$session b
  ON b.inst_id = w.blocking_instance
 AND b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.seconds_in_wait DESC;
```

`SQL_ID` của blocker có thể là SQL hiện tại hoặc NULL nếu session đang idle; `PREV_SQL_ID` thường giúp xác định câu SQL trước đó đã lấy lock. Cần xem cả hai cùng transaction age và trạng thái session. Không nên chỉ nhìn `STATUS = 'INACTIVE'` rồi kết luận session không giữ lock: một session inactive vẫn có thể đang giữ transaction chưa commit.

### 7.3. Xem lock đang được giữ hoặc yêu cầu

```sql
SELECT inst_id,
       sid,
       type,
       id1,
       id2,
       lmode,
       request,
       ctime,
       block
FROM gv$lock
WHERE request > 0
   OR block <> 0
ORDER BY type, id1, id2, inst_id, sid;
```

Ý nghĩa chính:

- `TYPE`: loại enqueue/resource, thường gặp `TX` và `TM`.
- `ID1`, `ID2`: định danh resource; ý nghĩa phụ thuộc `TYPE`.
- `LMODE`: mode session đang giữ.
- `REQUEST`: mode session đang yêu cầu; lớn hơn 0 nghĩa là đang chờ lock.
- `CTIME`: thời gian session giữ mode hiện tại theo đơn vị giây.
- `BLOCK`: thông tin resource có đang chặn session khác hay không; cách diễn giải chi tiết có thể khác trong RAC.

Không join `ID1`/`ID2` như thể chúng luôn là object ID. Với TM lock, `ID1` thường liên quan object ID; với TX lock, chúng định danh transaction resource theo cách khác.

### 7.4. Xác định object bị khóa qua GV$LOCKED_OBJECT

```sql
SELECT lo.inst_id,
       lo.session_id AS sid,
       s.serial#,
       s.username,
       o.owner,
       o.object_name,
       o.object_type,
       lo.locked_mode
FROM gv$locked_object lo
JOIN gv$session s
  ON s.inst_id = lo.inst_id
 AND s.sid = lo.session_id
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.inst_id, lo.session_id, o.owner, o.object_name;
```

View này hữu ích để liên hệ DML lock với object. Nó không liệt kê mọi dạng lock trong Oracle; ví dụ không phải mọi DDL/library cache lock đều được phản ánh như một dòng trong `GV$LOCKED_OBJECT`.

### 7.5. DBA_BLOCKERS và DBA_WAITERS

Oracle cung cấp các view như `DBA_BLOCKERS` và `DBA_WAITERS` để xem quan hệ blocker/waiter trong một số phạm vi. Với RAC hoặc chuỗi chặn phức tạp, các view `GV$SESSION` và `GV$LOCK` thường linh hoạt hơn vì có `INST_ID` và thông tin session chi tiết.

### 7.6. Xem DDL lock

Có thể kiểm tra DDL lock đang giữ/yêu cầu qua `DBA_DDL_LOCKS`:

```sql
SELECT session_id,
       owner,
       name,
       type,
       mode_held,
       mode_requested
FROM dba_ddl_locks
WHERE mode_held <> 'None'
   OR mode_requested <> 'None'
ORDER BY owner, name, session_id;
```

Quyền và nội dung view phụ thuộc phiên bản. Nếu cần kiểm tra theo session cụ thể, kết hợp `SESSION_ID` với `GV$SESSION` và xác định instance phù hợp.

## 8. Xác định transaction đang giữ lock lâu

Session blocker có thể đang `INACTIVE` nhưng vẫn có transaction chưa kết thúc. Cần kiểm tra transaction start time và lượng undo.

```sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.status,
       s.last_call_et,
       s.sql_id,
       s.prev_sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM gv$session s
JOIN gv$transaction t
  ON t.inst_id = s.inst_id
 AND t.addr = s.taddr
ORDER BY t.start_time;
```

`LAST_CALL_ET` có ý nghĩa theo trạng thái session; với session inactive, nó thường cho biết thời gian kể từ khi session trở thành inactive. `USED_UBLK` và `USED_UREC` cho biết mức sử dụng undo của transaction. Đây là dữ liệu hỗ trợ điều tra, không thay thế việc xem SQL và logic ứng dụng.

### 8.1. Session inactive vẫn có thể giữ lock

Một ứng dụng có thể:

1. Lấy connection từ pool.
2. Chạy UPDATE.
3. Không commit/rollback do lỗi xử lý hoặc quên transaction boundary.
4. Trả connection về pool trong trạng thái transaction chưa kết thúc nếu cấu hình/logic quản lý sai.

Session database có thể không chạy SQL ở thời điểm quan sát nhưng transaction vẫn mở và giữ lock. Đây là nguyên nhân phổ biến của lock wait kéo dài.

### 8.2. Xem SQL hiện tại và SQL trước đó

`GV$SESSION.SQL_ID` phản ánh SQL hiện tại; `PREV_SQL_ID` có thể giúp xác định câu lệnh gần nhất. Để xem text:

```sql
SELECT inst_id,
       sql_id,
       child_number,
       sql_text
FROM gv$sql
WHERE sql_id IN (:waiter_sql_id, :blocker_sql_id);
```

Bind hai SQL ID tương ứng. Nếu cursor đã bị aging out khỏi shared pool, `GV$SQL` có thể không còn dòng. Với quyền và license phù hợp, các nguồn lịch sử có thể hỗ trợ điều tra, nhưng cần tuân thủ chính sách licensing của Oracle Diagnostics Pack/Tuning Pack nếu dùng AWR/ASH.

## 9. Điều tra ORA-00060 bằng deadlock trace

Khi Oracle phát hiện deadlock, database tạo trace chứa deadlock graph và thông tin resource/session liên quan. Trace là nguồn quan trọng nhất để biết transaction nào giữ gì và chờ gì tại thời điểm lỗi.

### 9.1. Tìm thư mục trace

```sql
SELECT name,
       value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
```

`Diag Trace` cho biết thư mục trace của instance/session kết nối. Deadlock trace được tạo bởi tiến trình database và có thể nằm trong ADR trace directory. Trong RAC, cần xác định instance đã ghi trace; có thể xem alert log/ADR của instance tương ứng.

### 9.2. Nội dung cần đọc trong deadlock graph

Trace thường cung cấp thông tin như:

- Resource type, resource ID và lock mode.
- Session/process giữ lock.
- Session/process đang yêu cầu lock.
- Quan hệ giữa các resource trong chu trình.
- Thông tin row/object liên quan trong một số trường hợp.
- SQL đang thực thi hoặc thông tin transaction.

Khi đọc trace, lập bảng:

| Session | Resource đang giữ | Resource đang chờ | SQL/operation |
|---|---|---|---|
| Session A | Row hoặc enqueue X | Row hoặc enqueue Y | Update object nào? |
| Session B | Row hoặc enqueue Y | Row hoặc enqueue X | Update object nào? |

Nếu có nhiều session, mở rộng bảng cho toàn bộ chu trình. Tập trung vào thứ tự lock, không chỉ tên bảng xuất hiện trong thông báo.

### 9.3. Row information trong trace

Deadlock trace đôi khi chứa object ID, file number, block number và row slot. Có thể ánh xạ object ID qua `DBA_OBJECTS`:

```sql
SELECT owner,
       object_name,
       object_type
FROM dba_objects
WHERE object_id = :object_id;
```

Thông tin row có thể được dùng để xác định dòng cụ thể theo công cụ và trace detail phù hợp. Không phải mọi deadlock đều cung cấp row information đầy đủ; một số deadlock liên quan đến metadata/library cache hoặc resource không ánh xạ trực tiếp thành một row.

### 9.4. Đừng chỉ sửa bằng cách tăng timeout

Tăng `DDL_LOCK_TIMEOUT` hoặc thời gian chờ không giải quyết deadlock. Một chu trình không tự biến mất chỉ vì chờ lâu hơn. Oracle phát hiện chu trình và rollback statement để giải phóng resource.

Với ORA-00060, cần tìm nguyên nhân thứ tự lock không nhất quán, phạm vi transaction quá rộng hoặc một chuỗi trigger/foreign key tạo thêm lock.

## 10. Nguyên nhân phổ biến của lock wait và ORA-00054

### 10.1. DDL chạy khi ứng dụng đang dùng bảng

Một transaction DML mở lâu có thể khiến `ALTER TABLE`, `DROP TABLE`, `TRUNCATE TABLE` hoặc thao tác metadata khác không lấy được DDL lock cần thiết.

Giải pháp:

- Chạy DDL trong maintenance window phù hợp.
- Xác định blocker trước khi triển khai.
- Đợi transaction hoàn tất nếu có thể.
- Dùng `DDL_LOCK_TIMEOUT` có giới hạn phù hợp.
- Chia migration để giảm thời gian lock.
- Đánh giá online DDL nếu thao tác và phiên bản hỗ trợ.

### 10.2. SELECT FOR UPDATE giữ row lock lâu

Ứng dụng có thể lấy row lock rồi thực hiện công việc ngoài database trước khi commit. Những session khác muốn cập nhật dòng đó phải chờ.

Giải pháp là giảm thời gian từ lúc lấy lock đến commit, tránh gọi API bên ngoài trong transaction và chỉ lock những dòng thực sự cần.

### 10.3. Transaction quên commit hoặc rollback

Một exception bị bắt nhưng không kết thúc transaction có thể giữ lock. Cần kiểm tra transaction boundary trong Java/Spring, auto-commit, connection pool và exception handling.

### 10.4. Lock table hoặc DDL tường minh

Một đoạn PL/SQL hoặc job có thể gọi `LOCK TABLE` với mode mạnh. Nếu không thật sự cần, tránh lock table rộng. Nếu cần, đặt thời gian chờ rõ và đảm bảo transaction ngắn.

### 10.5. DDL trên object phụ thuộc

Compile package, thay view hoặc thay đổi metadata có thể cạnh tranh với session đang dùng object. Nếu gặp library cache lock/pin, cần kiểm tra object đang được thực thi, dependency và DDL concurrent.

## 11. Nguyên nhân phổ biến của deadlock

### 11.1. Hai transaction cập nhật cùng nhiều dòng theo thứ tự ngược

Đây là trường hợp kinh điển. Transaction A cập nhật row 10 rồi row 20; transaction B cập nhật row 20 rồi row 10. Nếu chúng chạy đồng thời, có thể hình thành chu trình.

Giải pháp: thống nhất thứ tự lock, ví dụ luôn cập nhật theo `ACCOUNT_ID` tăng dần.

### 11.2. Nhiều bảng được cập nhật theo thứ tự khác nhau

Transaction A cập nhật `ORDERS` rồi `INVENTORY`; transaction B cập nhật `INVENTORY` rồi `ORDERS`. Nếu cùng chạm một tập dữ liệu, chúng có thể chờ nhau.

Giải pháp: quy định thứ tự truy cập bảng trong service/repository và áp dụng nhất quán ở mọi code path.

### 11.3. Trigger tạo thêm lock ẩn

Một câu UPDATE trên bảng A có thể kích hoạt trigger cập nhật bảng B. Người viết transaction có thể nghĩ chỉ khóa A, nhưng trigger tạo thêm lock trên B. Nếu transaction khác cập nhật B rồi trigger quay lại A, deadlock có thể xảy ra.

Khi điều tra, phải xem cả trigger, package được gọi và cascade logic, không chỉ câu SQL hiển thị ở tầng Java.

### 11.4. Foreign key và parent update/delete

Thao tác trên parent table có thể cần kiểm tra child table. Foreign key không được index có thể làm tăng mức độ khóa và contention trong một số thao tác parent delete/update. Cần xem execution plan, constraint và index trên cột FK.

Index FK không tự động loại bỏ mọi deadlock, nhưng có thể giảm một số table-level contention và làm thao tác parent key hiệu quả hơn. Quyết định tạo index cần dựa trên workload.

### 11.5. Transaction dài hoặc xử lý ngoài database

Transaction càng dài, lock càng tồn tại lâu và càng có nhiều cơ hội va chạm với transaction khác. Không nên:

- Mở transaction rồi gọi REST API bên ngoài.
- Giữ transaction khi gửi email hoặc chờ message broker.
- Chờ người dùng xác nhận trong khi giữ row lock.
- Chạy báo cáo dài trong cùng transaction cập nhật dữ liệu.

Nếu cần phối hợp database và hệ thống ngoài, cân nhắc outbox, saga hoặc thiết kế commit ngắn rồi xử lý bất đồng bộ.

## 12. Cách phòng ngừa deadlock

### 12.1. Thống nhất thứ tự lock

Đây là biện pháp quan trọng nhất với deadlock do nhiều row/table. Nếu nhiều transaction phải cập nhật cùng tập tài nguyên, hãy sắp xếp theo một thứ tự duy nhất.

Ví dụ Java:

```java
List<Long> accountIds = Stream.of(sourceAccountId, targetAccountId)
        .sorted()
        .toList();

// Lock các account theo account_id tăng dần trước khi thực hiện transfer.
```

Ở database, có thể select các dòng theo thứ tự xác định và lock:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id IN (:accountIds)
ORDER BY account_id
FOR UPDATE;
```

Thứ tự phải được bảo đảm trong mọi code path liên quan. Nếu một trigger hoặc procedure khóa theo thứ tự khác, vẫn có thể deadlock.

### 12.2. Giữ transaction ngắn

Chỉ thực hiện thao tác cần thiết bên trong transaction. Chuẩn bị dữ liệu trước khi bắt đầu transaction nếu có thể; commit ngay sau khi các DML cần atomicity hoàn tất.

### 12.3. Lock đúng phạm vi

Không dùng `LOCK TABLE ... EXCLUSIVE` nếu chỉ cần khóa một vài row. Dùng `SELECT FOR UPDATE` với predicate có index phù hợp để hạn chế tập dòng bị khóa.

### 12.4. Tạo index phù hợp

Index trên predicate cập nhật giúp Oracle tìm row nhanh hơn và giảm thời gian transaction giữ lock. Index trên foreign key có thể giảm một số contention trong thao tác parent. Tuy nhiên, thêm index làm tăng chi phí DML; cần cân nhắc tổng thể.

### 12.5. Tránh cập nhật không cần thiết

Không cập nhật row nếu giá trị mới giống giá trị hiện tại và không cần side effect. Giảm số row bị khóa và số lần trigger chạy có thể giảm contention.

### 12.6. Tách công việc bất đồng bộ

Nếu transaction cần phát thông báo hoặc xử lý ngoài database, ghi một outbox row trong cùng transaction rồi commit. Worker đọc outbox và gửi message sau đó. Cách này tránh giữ row lock trong khi chờ network.

## 13. Xử lý lỗi trong ứng dụng Java/Spring

Khi dùng Spring JDBC, lỗi Oracle được chuyển thành `DataAccessException` hoặc subtype tương ứng bởi exception translator. Tầng ứng dụng vẫn có thể kiểm tra root cause `SQLException` và vendor error code khi cần phân loại.

### 13.1. Không nuốt lỗi lock

Không nên viết:

```java
try {
    repository.updateOrder(order);
} catch (DataAccessException ex) {
    log.warn("Update failed", ex);
    // Tiếp tục như thể update thành công.
}
```

Nếu update thất bại do lock, ứng dụng phải quyết định trả lỗi, retry hoặc chuyển trạng thái công việc. Tiếp tục nghiệp vụ khi dữ liệu chưa được cập nhật có thể tạo trạng thái sai.

### 13.2. Rollback transaction khi deadlock

Ví dụ service:

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);
}
```

Nếu một statement ném unchecked `DataAccessException` và exception thoát khỏi method, Spring mặc định rollback transaction. Nếu code bắt exception bên trong method rồi không ném lại, Spring có thể commit phần thay đổi còn lại nếu transaction chưa bị đánh dấu rollback-only.

Với deadlock, nên để exception thoát ra hoặc đánh dấu transaction rollback-only. Sau đó nếu retry, chạy lại toàn bộ transaction trong transaction mới.

### 13.3. Retry có giới hạn và backoff

Retry có thể phù hợp với contention tạm thời, nhưng phải có:

- Số lần retry giới hạn.
- Backoff tăng dần và jitter để tránh nhiều worker retry cùng lúc.
- Transaction mới cho mỗi lần thử.
- Idempotency hoặc bảo đảm nghiệp vụ không bị thực hiện hai lần.
- Metric/log để nhận biết contention đang tăng.

Không retry vô hạn. Nếu lỗi do thứ tự lock sai trong code, retry chỉ che vấn đề và làm tải hệ thống tăng thêm.

### 13.4. Phân biệt retry ORA-00054 và ORA-00060

Với ORA-00054 từ DDL, thường cần chờ blocker kết thúc, lên lịch DDL hoặc điều chỉnh `DDL_LOCK_TIMEOUT`. Retry nhanh liên tục có thể tạo thêm contention.

Với ORA-00060, rollback transaction hiện tại rồi retry toàn bộ nghiệp vụ nếu an toàn. Không chỉ chạy lại statement bị lỗi vì các statement trước đó có thể đã thực hiện và transaction có thể còn giữ lock.

### 13.5. Kiểm tra vendor error code

Ví dụ helper đơn giản:

```java
static OptionalInt findOracleErrorCode(Throwable error) {
    Throwable current = error;
    while (current != null) {
        if (current instanceof SQLException sqlException) {
            int code = sqlException.getErrorCode();
            if (code == 54 || code == 60) {
                return OptionalInt.of(code);
            }
        }
        current = current.getCause();
    }
    return OptionalInt.empty();
}
```

Đoạn code chỉ minh họa cách tìm vendor error code trong cause chain. Cần kiểm tra translator và exception hierarchy của phiên bản Spring đang dùng. Không nên phụ thuộc vào message text vì ngôn ngữ và nội dung message có thể thay đổi.

## 14. Xử lý blocker: commit, rollback hay terminate session?

Khi phát hiện blocker, bước đầu tiên là xác định owner của session và transaction. Không nên kill session ngay khi nhìn thấy một lock.

Thứ tự xử lý nên là:

1. Xác định waiter, blocker, instance, SQL và object.
2. Xác định blocker thuộc ứng dụng/job nào và transaction có đang làm việc hợp lệ không.
3. Liên hệ owner hoặc kiểm tra runbook để biết có thể chờ transaction hoàn tất không.
4. Nếu nghiệp vụ không còn hợp lệ, yêu cầu ứng dụng rollback/đóng transaction theo quy trình.
5. Chỉ cân nhắc terminate session khi có phê duyệt và hiểu tác động rollback.

### 14.1. Vì sao không nên kill session tùy tiện?

Terminate session có thể:

- Buộc Oracle rollback transaction đang mở; rollback có thể mất thời gian.
- Làm request ứng dụng thất bại hoặc client nhận trạng thái kết quả không xác định.
- Tạo thêm tải I/O/undo trong quá trình rollback.
- Làm connection pool cần loại bỏ và tạo connection mới.
- Làm một job batch phải chạy lại từ đầu.

Nếu session là một giao dịch thanh toán hoặc batch quan trọng, kill có thể gây tác động lớn hơn thời gian chờ ban đầu.

### 14.2. Kill session trong RAC

DBA có thể dùng `ALTER SYSTEM KILL SESSION` với SID, SERIAL# và instance theo cú pháp được hỗ trợ:

```sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
```

Đây là thao tác quản trị có tác động. Cần thay các placeholder bằng session đã xác minh và tuân theo runbook. `IMMEDIATE` không có nghĩa rollback transaction lớn sẽ hoàn tất tức thì.

Không dùng câu lệnh này như giải pháp mặc định cho ORA-00054 hoặc ORA-00060. Với deadlock, Oracle đã rollback một statement để phá vòng chờ; điều cần sửa thường là transaction ordering.

## 15. Lock trong RAC

Trong Oracle RAC, nhiều instance cùng truy cập một database. Global Enqueue Service và Global Cache Service phối hợp các resource giữa các instance. Một session chờ lock có thể bị blocker ở instance khác.

### 15.1. Dùng GV$ thay vì chỉ V$

Trong RAC, nên dùng các view `GV$SESSION`, `GV$LOCK`, `GV$LOCKED_OBJECT`, `GV$TRANSACTION` để có `INST_ID` và xem toàn cluster.

Nếu chỉ truy vấn `V$SESSION` trên một instance, có thể bỏ sót blocker hoặc waiter đang ở node khác.

### 15.2. Blocking instance và final blocker

`BLOCKING_INSTANCE` cho biết instance của blocker trực tiếp. `FINAL_BLOCKING_INSTANCE` giúp tìm blocker cuối cùng trong chuỗi chặn. Đây là thông tin hữu ích khi session B chờ A, nhưng A lại chờ một session C.

### 15.3. RAC không loại bỏ deadlock

RAC cung cấp cơ chế global coordination nhưng ứng dụng vẫn có thể tạo deadlock logic khi transaction khóa nhiều row/table theo thứ tự khác nhau. Việc lock nằm trên các node khác nhau không làm mất quy tắc về thứ tự truy cập tài nguyên.

## 16. Quy trình chẩn đoán ORA-00054

Khi DDL hoặc câu lệnh NOWAIT trả ORA-00054, thực hiện theo trình tự:

1. Xác định câu SQL gây lỗi và loại lock mà câu lệnh yêu cầu.
2. Kiểm tra `DDL_LOCK_TIMEOUT` nếu lỗi xảy ra với DDL.
3. Tìm waiter/blocker qua `GV$SESSION`.
4. Xem SQL hiện tại và SQL trước đó của blocker.
5. Kiểm tra blocker có transaction mở hay không qua `GV$TRANSACTION`.
6. Xác định object bằng `GV$LOCKED_OBJECT`, `DBA_DDL_LOCKS` hoặc thông tin lock phù hợp.
7. Quyết định chờ, retry có backoff, dời DDL hoặc xử lý transaction blocker.
8. Sau khi lock được giải phóng, chạy lại statement và xác nhận object ở trạng thái mong muốn.

Không chỉ tăng timeout mà bỏ qua blocker. Nếu cùng một blocker lặp lại mỗi lần deploy, cần xử lý transaction hoặc deployment window gây ra tình trạng đó.

## 17. Quy trình chẩn đoán ORA-00060

Khi nhận ORA-00060:

1. Ghi nhận timestamp, service, module, action, SQL ID và request/job ID.
2. Xác định instance ghi deadlock trace.
3. Mở deadlock graph và liệt kê mọi session/resource trong cycle.
4. Xác định bảng, row hoặc object liên quan.
5. Xem SQL và transaction flow của từng session.
6. Kiểm tra trigger, procedure, foreign key và các lời gọi ẩn tạo thêm lock.
7. Tìm điểm khác nhau về thứ tự truy cập tài nguyên.
8. Sửa code để thống nhất lock order hoặc rút ngắn transaction.
9. Tạo test concurrency tái hiện tình huống.
10. Theo dõi tần suất deadlock sau khi deploy bản sửa.

Deadlock trace phản ánh một thời điểm cụ thể. Nếu không thể tái hiện, cần tăng khả năng quan sát bằng application module/action, SQL logging có kiểm soát và metric transaction duration.

## 18. Ví dụ thiết kế lại giao dịch chuyển tiền

Một service chuyển tiền cần cập nhật hai tài khoản. Nếu hai request chuyển tiền theo hướng ngược nhau cùng lúc, thứ tự cập nhật có thể tạo deadlock.

### 18.1. Thiết kế dễ deadlock

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    jdbc.update("UPDATE accounts SET balance = balance - ? WHERE account_id = ?",
            amount, fromId);

    jdbc.update("UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
            amount, toId);
}
```

Request A chuyển 10 sang 20; request B chuyển 20 sang 10. Hai transaction có thể lấy lock theo thứ tự ngược nhau.

### 18.2. Lock theo thứ tự account ID

Có thể khóa cả hai account theo thứ tự tăng dần trước khi thay đổi:

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    List<Account> accounts = jdbc.query("""
        SELECT account_id, balance
        FROM accounts
        WHERE account_id IN (?, ?)
        ORDER BY account_id
        FOR UPDATE
        """, accountRowMapper, fromId, toId);

    Map<Long, Account> byId = accounts.stream()
            .collect(Collectors.toMap(Account::accountId, Function.identity()));

    Account source = Objects.requireNonNull(byId.get(fromId));
    Account target = Objects.requireNonNull(byId.get(toId));

    if (source.balance().compareTo(amount) < 0) {
        throw new InsufficientFundsException();
    }

    jdbc.update("UPDATE accounts SET balance = balance - ? WHERE account_id = ?",
            amount, fromId);
    jdbc.update("UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
            amount, toId);
}
```

Mẫu này minh họa ý tưởng lock theo thứ tự ổn định. Trong code thực tế cần xử lý trường hợp `fromId == toId`, account không tồn tại, amount không hợp lệ, precision và quy tắc số dư. Cũng cần xác nhận execution plan thực sự lock theo thứ tự mong muốn; nếu yêu cầu rất nghiêm ngặt, có thể khóa từng ID theo thứ tự bằng hai câu SELECT FOR UPDATE riêng.

### 18.3. Kiểm thử concurrency

Tạo hai thread hoặc hai worker transaction chạy đồng thời:

- Worker A chuyển từ account 10 sang 20.
- Worker B chuyển từ account 20 sang 10.
- Lặp lại với barrier để tăng khả năng hai transaction giao nhau.
- Xác nhận không có deadlock sau khi áp dụng lock order.
- Xác nhận tổng balance không thay đổi ngoài phí nghiệp vụ.
- Xác nhận lỗi thiếu tiền rollback cả transaction.

Test cần chạy trên Oracle thật hoặc môi trường tương thích đầy đủ, vì locking semantics của database khác nhau.

## 19. Các wait event nên phân biệt

| Wait event | Ý nghĩa khái quát | Hướng điều tra |
|---|---|---|
| `enq: TX - row lock contention` | Chờ transaction giữ row lock | Tìm blocker, transaction age, row/object |
| `enq: TM - contention` | Chờ table enqueue | Kiểm tra DDL, FK, table lock mode và DML |
| `library cache lock` | Chờ lock trên library cache object | Kiểm tra DDL/compile và session đang dùng object |
| `library cache pin` | Chờ pin object trong library cache | Kiểm tra compile/reload object và SQL/PLSQL đang chạy |
| `row cache lock` | Chờ dictionary cache lock | Xem DDL và hoạt động metadata đồng thời |
| `cursor: pin S wait on X` | Chờ pin liên quan cursor/shared pool | Điều tra cursor invalidation, parse và concurrent execution |

Tên event và cách diễn giải chi tiết phụ thuộc phiên bản Oracle. Wait event cho biết loại chờ, không tự cung cấp nguyên nhân nghiệp vụ. Phải ghép với SQL, session, object và transaction.

## 20. Những điều không nên làm

- Không kill session chỉ vì nó xuất hiện trong danh sách blocker mà chưa xác định owner và transaction.
- Không tăng timeout vô hạn để che transaction dài.
- Không retry liên tục một câu DML đang tranh chấp mà không có backoff.
- Không bắt ORA-00060 rồi tiếp tục transaction như thể statement đã thành công.
- Không chạy DDL trong cùng luồng xử lý nghiệp vụ đang có DML chưa commit.
- Không dùng table lock mạnh nếu row lock đáp ứng được yêu cầu.
- Không giả định session `INACTIVE` là session không giữ lock.
- Không dùng `SKIP LOCKED` nếu nghiệp vụ cần xử lý mọi dòng và không chấp nhận bỏ qua dòng đang khóa.
- Không kết luận deadlock chỉ từ thời gian chờ dài; phải có chu trình chờ.
- Không chỉ nhìn `V$SESSION` trong RAC rồi kết luận không có blocker ở instance khác.

## 21. Bài thực hành: quan sát lock wait và deadlock

### 21.1. Chuẩn bị dữ liệu

```sql
CREATE TABLE lock_demo (
    id NUMBER PRIMARY KEY,
    value NUMBER NOT NULL
);

INSERT INTO lock_demo(id, value) VALUES (1, 100);
INSERT INTO lock_demo(id, value) VALUES (2, 200);
COMMIT;
```

### 21.2. Tạo lock wait một chiều

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
-- Chưa commit.
```

Session B:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
```

Session B chờ Session A. Từ session quản trị, chạy truy vấn waiter/blocker ở phần 7.1 và xác định blocker. Sau đó commit Session A; Session B tiếp tục.

### 21.3. Tạo deadlock

Reset dữ liệu nếu cần và commit trước khi thử.

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
```

Session B:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 2;
```

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 2;
-- A chờ B.
```

Session B:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
-- B tạo chu trình chờ; một statement sẽ nhận ORA-00060.
```

Sau lỗi, kiểm tra deadlock trace. Rollback transaction còn lại và xem giá trị cuối trong bảng. Không để transaction thử nghiệm mở khi kết thúc bài thực hành.

### 21.4. Thử DDL_LOCK_TIMEOUT

Session A:

```sql
UPDATE lock_demo SET value = value + 1 WHERE id = 1;
-- Chưa commit.
```

Session B:

```sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 5;
ALTER TABLE lock_demo ADD note VARCHAR2(50);
```

Nếu Session A không giải phóng lock trong khoảng chờ, Session B có thể nhận ORA-00054. Nếu Session A commit trong thời gian đó, DDL có thể tiếp tục.

## 22. Checklist vận hành

Khi nhận incident liên quan lock, ghi lại:

| Thông tin | Giá trị cần thu thập |
|---|---|
| Error | ORA-00054 hay ORA-00060; timestamp và service |
| Waiter | Instance, SID, SERIAL#, username, module/action, SQL ID |
| Blocker | Instance, SID, SERIAL#, username, status, current/previous SQL ID |
| Resource | TX/TM/DDL/library cache; object/row nếu xác định được |
| Duration | Seconds in wait, transaction start time, undo usage |
| Trace | ADR trace path và deadlock graph nếu là ORA-00060 |
| Application | Request/job ID, transaction boundary và retry count |
| Recovery | Commit/rollback, retry, DDL reschedule hay xử lý blocker theo runbook |
| Prevention | Lock order, transaction duration, index/FK, DDL window |

## 23. Nguyên tắc cần nhớ

1. Lock wait là cơ chế bình thường khi transaction khác đang giữ resource; deadlock là một chu trình chờ không thể tự tiến triển.
2. ORA-00054 thường liên quan NOWAIT hoặc timeout khi lấy lock; xác định blocker và câu lệnh yêu cầu lock.
3. `DDL_LOCK_TIMEOUT` có thể cho DDL chờ một khoảng thời gian, nhưng không sửa nguyên nhân blocker và không giải quyết deadlock.
4. ORA-00060 được Oracle phát hiện qua lock graph; trace file cho biết resource/session trong chu trình.
5. Khi gặp deadlock, statement bị rollback nhưng transaction có thể vẫn mở; ứng dụng nên rollback transaction và chỉ retry toàn bộ nghiệp vụ trong transaction mới nếu an toàn.
6. Thống nhất thứ tự lock, rút ngắn transaction, tránh giữ lock khi gọi dịch vụ ngoài và tạo index phù hợp giúp giảm contention.
7. Trong RAC, dùng `GV$` views và theo dõi `INST_ID` để không bỏ sót blocker ở node khác.
8. Chỉ terminate session theo runbook sau khi xác định tác động; không dùng kill session làm giải pháp mặc định.

ORA-00054 và ORA-00060 đều liên quan đến lock, nhưng phản ánh hai tình huống khác nhau. ORA-00054 cho biết yêu cầu lock không lấy được theo chế độ NOWAIT hoặc timeout; thường cần tìm session đang giữ resource, chọn thời điểm chạy DDL hoặc điều chỉnh thời gian chờ hợp lý. ORA-00060 cho biết Oracle đã phát hiện vòng chờ giữa các transaction; cần đọc deadlock trace và sửa thứ tự truy cập tài nguyên. Hiểu đúng sự khác biệt này giúp xử lý sự cố nhanh hơn, tránh kill session hoặc retry sai cách và cải thiện thiết kế transaction để hệ thống Oracle hoạt động ổn định khi có nhiều session đồng thời.
