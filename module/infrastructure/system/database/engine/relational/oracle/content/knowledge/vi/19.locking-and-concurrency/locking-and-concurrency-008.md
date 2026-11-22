# Blocking session, chuỗi chờ và truy tìm giao dịch gây nghẽn

Trong Oracle Database, một transaction có thể giữ khóa trên hàng dữ liệu chưa commit. Khi session khác cần sửa hoặc khóa chính hàng đó, session thứ hai phải chờ transaction đang giữ khóa kết thúc. Session giữ khóa được gọi là **blocking session**; session phải chờ là **waiting session** hoặc **waiter**.

Một waiter có thể khiến nhiều session khác phải chờ. Nếu chính blocker cũng đang chờ một session khác, ta có một **blocking chain** (chuỗi chờ). Khi xử lý sự cố, tìm session đang chờ lâu chỉ là bước đầu; cần truy ngược đến transaction gốc đang giữ khóa, xác định câu SQL và ứng dụng sở hữu nó, rồi mới chọn cách giải phóng.

Bài học này hướng dẫn:

- Phân biệt blocker, waiter, blocking chain và deadlock.
- Dùng các dynamic performance views V$SESSION/GV$SESSION để tìm session đang chờ và session chặn nó.
- Dùng GV$LOCK, GV$LOCKED_OBJECT và GV$TRANSACTION để hiểu khóa, đối tượng và transaction.
- Truy tìm SQL, module, client và hàng đang bị chờ.
- Xử lý an toàn, bao gồm trường hợp session không còn chạy SQL nhưng vẫn giữ transaction chưa commit.

Các ví dụ tập trung vào Oracle 19c. Tài khoản giám sát cần quyền đọc dynamic performance views và các dictionary view liên quan; trong môi trường production, DBA nên cấp quyền tối thiểu phù hợp thay vì cấp quyền quản trị rộng.

## 1. Blocker và waiter là gì?

Oracle dùng cơ chế khóa để bảo đảm nhiều transaction có thể làm việc đồng thời mà không ghi đè thay đổi chưa hoàn tất của nhau.

Ví dụ:

1. Session A cập nhật tài khoản 101 nhưng chưa COMMIT hoặc ROLLBACK.
2. Session B cũng muốn cập nhật tài khoản 101.
3. B phải đợi A kết thúc transaction.
4. Trong thời gian đó, A là blocker và B là waiter.

~~~text
Session A                                  Session B
---------                                  ---------
UPDATE account 101
  (giữ row lock)
                                           UPDATE account 101
                                             |
                                             v
                                           WAITING
                                             |
                                             | enq: TX - row lock contention
                                             |
                  A blocks B ---------------+

COMMIT hoặc ROLLBACK
  |
  v
B được tiếp tục
~~~

Khóa hàng của Oracle được giữ đến khi transaction kết thúc. Vì vậy session A có thể đang INACTIVE (không chạy câu SQL nào ở thời điểm giám sát) nhưng vẫn là blocker nếu transaction của nó chưa commit/rollback. Đây là nguyên nhân thường gặp khi ứng dụng mở transaction, cập nhật dữ liệu rồi chờ người dùng thao tác quá lâu.

### 1.1. Blocker không nhất thiết là session đang chạy lâu

Các trường hợp phổ biến:

- Một session cập nhật hàng rồi quên commit.
- Một session thực hiện SELECT ... FOR UPDATE, sau đó giữ transaction mở.
- Ứng dụng giữ transaction trong khi gọi dịch vụ bên ngoài hoặc chờ thao tác người dùng.
- Một batch xử lý nhiều hàng trong một transaction quá dài.
- DDL hoặc LOCK TABLE chờ/giữ khóa không tương thích với DML khác.

Do đó, chỉ xem session ACTIVE hoặc SQL đang chạy lâu sẽ bỏ sót nhiều blocker quan trọng. Hãy xem trạng thái transaction và quan hệ blocking.

### 1.2. Blocking chain

Một chuỗi chờ có thể có dạng:

~~~text
Session A (root blocker)
      |
      +---- blocks B
                 |
                 +---- B blocks C
                              |
                              +---- blocks D
~~~

Nếu chỉ giải phóng D, D có thể tiếp tục nhưng C, B vẫn chờ. Cần xác định root blocker (session ở đầu chuỗi) và những waiter phụ thuộc vào nó.

### 1.3. Blocking không đồng nghĩa với deadlock

**Blocking** là một session chờ tài nguyên do session khác giữ; nếu blocker hoàn tất transaction, waiter có thể tiếp tục.

**Deadlock** là một vòng chờ: transaction A chờ tài nguyên do B giữ, trong khi B lại chờ tài nguyên do A giữ (hoặc một chu trình nhiều session). Oracle phát hiện deadlock và thường báo ORA-00060: deadlock detected while waiting for resource, đồng thời ghi thông tin chẩn đoán vào trace. Đây không chỉ là một session chờ lâu.

## 2. Tạo tình huống blocking trong lab

Ta dùng hai session kết nối cùng schema để quan sát khóa hàng. Chỉ thực hành trong schema lab do bạn sở hữu.

### 2.1. Tạo bảng

~~~sql
CREATE TABLE lab_lock_accounts (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12, 2) NOT NULL,
    note       VARCHAR2(100)
);

INSERT INTO lab_lock_accounts VALUES (101, 1000, 'Account A');
INSERT INTO lab_lock_accounts VALUES (102, 2000, 'Account B');
COMMIT;
~~~

### 2.2. Session A: cập nhật nhưng chưa commit

Mở kết nối thứ nhất:

~~~sql
UPDATE lab_lock_accounts
SET balance = balance - 100
WHERE account_id = 101;
~~~

Không chạy COMMIT hoặc ROLLBACK ngay. Session A đã thay đổi hàng 101 và đang giữ khóa của transaction.

### 2.3. Session B: cập nhật cùng hàng

Mở kết nối thứ hai:

~~~sql
UPDATE lab_lock_accounts
SET balance = balance + 50
WHERE account_id = 101;
~~~

Câu lệnh ở Session B sẽ chờ Session A kết thúc transaction. Tùy công cụ client, trạng thái của cửa sổ SQL có thể hiển thị đang thực thi hoặc chờ.

### 2.4. Giải phóng waiter

Quay lại Session A và chạy một trong hai lệnh:

~~~sql
COMMIT;
~~~

hoặc:

~~~sql
ROLLBACK;
~~~

Sau khi A kết thúc transaction, B có thể tiếp tục. Nếu A COMMIT, thay đổi của A được lưu trước khi B cập nhật. Nếu A ROLLBACK, thay đổi của A bị hủy và B tiếp tục trên dữ liệu đã rollback.

Không chạy cả hai lệnh trong cùng một lần thử. Hãy ghi nhận lựa chọn và quan sát kết quả ở Session B.

## 3. Tìm waiter và blocker bằng V$SESSION

V$SESSION chứa thông tin về các session trong instance hiện tại. Với hệ thống một instance, có thể dùng V$SESSION; với Oracle RAC, dùng GV$SESSION để quan sát tất cả instance.

### 3.1. Truy vấn các session đang bị chặn

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    event,
    wait_class,
    state,
    seconds_in_wait,
    sql_id,
    blocking_session_status,
    blocking_instance,
    blocking_session,
    final_blocking_instance,
    final_blocking_session
FROM v$session
WHERE blocking_session_status = 'VALID'
ORDER BY seconds_in_wait DESC;
~~~

Các cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| SID, SERIAL# | Định danh session trong instance; cần cả hai khi thao tác với session |
| USERNAME | Database user của session |
| STATUS | ACTIVE hoặc INACTIVE tại thời điểm quan sát |
| EVENT, WAIT_CLASS | Sự kiện và nhóm wait mà session đang gặp |
| STATE | Trạng thái chờ, ví dụ WAITING |
| SECONDS_IN_WAIT | Thời gian của wait hiện tại khi session đang ở trạng thái chờ |
| SQL_ID | SQL hiện tại của session nếu có |
| BLOCKING_SESSION_STATUS | Trạng thái thông tin blocker |
| BLOCKING_SESSION | SID của blocker trực tiếp khi trạng thái là VALID |
| FINAL_BLOCKING_SESSION | SID của blocker cuối chuỗi nếu Oracle xác định được |

Chỉ coi BLOCKING_SESSION là có giá trị khi BLOCKING_SESSION_STATUS = 'VALID'. Các trạng thái khác có thể cho biết không có holder, session không còn ở trạng thái chờ hoặc Oracle chưa xác định được blocker.

SECONDS_IN_WAIT giúp xếp thứ tự các waiter đang chờ, nhưng không tự chứng minh nguyên nhân hay mức độ ảnh hưởng nghiệp vụ. Hãy kết hợp event, SQL, transaction và số lượng session phụ thuộc.

### 3.2. Xem waiter cùng session blocker

Truy vấn sau ghép waiter với session đang chặn trực tiếp:

~~~sql
SELECT
    w.sid                 AS waiter_sid,
    w.serial#             AS waiter_serial,
    w.username            AS waiter_user,
    w.status              AS waiter_status,
    w.event,
    w.wait_class,
    w.seconds_in_wait,
    w.sql_id              AS waiter_sql_id,
    w.blocking_session    AS blocker_sid,
    b.serial#             AS blocker_serial,
    b.username            AS blocker_user,
    b.status              AS blocker_status,
    b.sql_id              AS blocker_sql_id,
    b.prev_sql_id         AS blocker_prev_sql_id,
    b.module,
    b.action,
    b.machine,
    b.program,
    b.logon_time
FROM v$session w
LEFT JOIN v$session b
  ON b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.seconds_in_wait DESC;
~~~

Kết quả cho biết session nào đang chờ, session nào giữ khóa trực tiếp, wait event và thời gian chờ, SQL ID hiện tại/trước đó của blocker, cùng module/action/máy/chương trình client để truy tìm ứng dụng sở hữu nó.

Nếu BLOCKER_STATUS = 'INACTIVE', vẫn phải kiểm tra transaction. Session không chạy SQL ở thời điểm này nhưng có thể giữ khóa do DML trước đó chưa commit.

### 3.3. Dùng GV$SESSION trong Oracle RAC

Trong RAC, SID chỉ có ý nghĩa trong phạm vi instance. Không được ghép waiter và blocker chỉ bằng SID vì hai instance có thể có session trùng SID.

~~~sql
SELECT
    w.inst_id              AS waiter_inst_id,
    w.sid                  AS waiter_sid,
    w.serial#              AS waiter_serial,
    w.username             AS waiter_user,
    w.status               AS waiter_status,
    w.event,
    w.wait_class,
    w.seconds_in_wait,
    w.sql_id               AS waiter_sql_id,
    w.blocking_instance    AS blocker_inst_id,
    w.blocking_session     AS blocker_sid,
    b.serial#              AS blocker_serial,
    b.username             AS blocker_user,
    b.status               AS blocker_status,
    b.sql_id               AS blocker_sql_id,
    b.prev_sql_id          AS blocker_prev_sql_id,
    b.module,
    b.action,
    b.machine,
    b.program
FROM gv$session w
LEFT JOIN gv$session b
  ON b.inst_id = w.blocking_instance
 AND b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.seconds_in_wait DESC;
~~~

BLOCKING_INSTANCE là instance chứa blocker. Điều kiện join cần cả INST_ID và SID. Với RAC, các view GV$ có cột INST_ID; dùng chúng để không nhầm session giữa các instance.

## 4. Truy tìm root blocker và chuỗi chờ

BLOCKING_SESSION cho biết blocker trực tiếp. Nếu blocker cũng đang chờ, cần lần tiếp theo BLOCKING_SESSION của chính nó. Oracle cung cấp FINAL_BLOCKING_SESSION và FINAL_BLOCKING_INSTANCE để chỉ ra blocker cuối chuỗi khi xác định được.

### 4.1. Gom waiter theo final blocker

~~~sql
SELECT
    final_blocking_instance,
    final_blocking_session,
    COUNT(*) AS waiting_sessions,
    MAX(seconds_in_wait) AS longest_wait_seconds
FROM gv$session
WHERE blocking_session_status = 'VALID'
  AND final_blocking_session_status = 'VALID'
GROUP BY
    final_blocking_instance,
    final_blocking_session
ORDER BY waiting_sessions DESC, longest_wait_seconds DESC;
~~~

Một final blocker có nhiều waiter thường là điểm cần điều tra trước. Số waiter là số session đang chờ trực tiếp hoặc gián tiếp được gán cho blocker cuối, tùy thông tin Oracle cung cấp tại thời điểm truy vấn.

### 4.2. Theo dõi một blocker cụ thể

Sau khi có INST_ID, SID, SERIAL# của blocker, tìm tất cả waiter đang trỏ đến session đó:

~~~sql
SELECT
    inst_id,
    sid,
    serial#,
    username,
    status,
    event,
    seconds_in_wait,
    sql_id,
    blocking_session_status
FROM gv$session
WHERE blocking_session_status = 'VALID'
  AND blocking_instance = :blocker_inst_id
  AND blocking_session = :blocker_sid
ORDER BY seconds_in_wait DESC;
~~~

Bind blocker_inst_id và blocker_sid lấy từ kết quả giám sát. Cách này hữu ích khi một session đang chặn nhiều giao dịch cùng lúc.

## 5. Hiểu TX và TM enqueue

Oracle hiển thị nhiều wait event liên quan đến enqueue. Hai loại thường gặp khi điều tra blocking DML là TX và TM.

### 5.1. TX — transaction enqueue

TX là enqueue gắn với transaction. Một transaction thường giữ TX enqueue ở mode độc quyền trong thời gian có thay đổi chưa commit.

Wait event thường gặp:

| Event | Diễn giải ban đầu |
| --- | --- |
| enq: TX - row lock contention | Session chờ transaction khác kết thúc vì cần truy cập hàng đang bị khóa |
| enq: TX - allocate ITL entry | Có thể thiếu transaction slot (ITL) trong block |
| enq: TX - index contention | Có thể liên quan cạnh tranh cấu trúc/index; cần đọc thêm wait và segment |

Không suy ra mọi wait bắt đầu bằng enq: TX đều là cùng một lỗi row lock. Hãy đọc chính xác EVENT, xem object/SQL và xác định loại tài nguyên đang tranh chấp.

### 5.2. TM — table enqueue

TM là enqueue trên đối tượng bảng, dùng để phối hợp các thao tác DML và các thao tác cần khóa bảng. DML thông thường thường lấy table lock ở mode Row Exclusive (mode 3), tương thích với nhiều DML khác trên cùng bảng.

enq: TM - contention có thể liên quan đến:

- LOCK TABLE hoặc một thao tác yêu cầu table lock mạnh hơn.
- DDL chờ khóa đối tượng.
- Thiết kế foreign key không có index trong tình huống cập nhật/xóa khóa cha.
- Các thao tác DML/DDL khác tranh chấp mode khóa trên cùng bảng.

Đừng kết luận chỉ từ TM rằng toàn bộ bảng bị khóa độc quyền. Cần xem LMODE, REQUEST, object và câu SQL liên quan.

### 5.3. Xem các enqueue TX/TM

~~~sql
SELECT
    inst_id,
    sid,
    type,
    id1,
    id2,
    lmode,
    request,
    ctime,
    block
FROM gv$lock
WHERE type IN ('TX', 'TM')
  AND (request > 0 OR block > 0)
ORDER BY type, id1, id2, request DESC;
~~~

Các cột:

- TYPE: loại enqueue, ví dụ TX hoặc TM.
- ID1, ID2: định danh tài nguyên của enqueue; ý nghĩa phụ thuộc loại lock.
- LMODE: mode session đang giữ.
- REQUEST: mode session đang yêu cầu; giá trị lớn hơn 0 cho biết đang chờ.
- CTIME: thời gian ở mode hiện tại.
- BLOCK: thông tin lock có chặn session khác hay không; trong RAC có thể có giá trị chỉ ra khả năng chặn ở instance khác.

### 5.4. Bảng quy đổi lock mode

| Giá trị | Tên mode |
| ---: | --- |
| 0 | None |
| 1 | Null |
| 2 | Row-S (SS) |
| 3 | Row-X (SX) |
| 4 | Share |
| 5 | S/Row-X (SSX) |
| 6 | Exclusive |

Các mode này là cách Oracle biểu diễn mức khóa; việc hai lock có xung đột hay không phụ thuộc ma trận tương thích của loại enqueue. Không chỉ nhìn thấy LMODE lớn hơn 0 là kết luận có blocker.

## 6. Xác định đối tượng đang bị khóa

GV$LOCKED_OBJECT cho biết các đối tượng đang được transaction khóa ở cấp đối tượng. Kết hợp với session và DBA_OBJECTS để tìm owner, table, partition/subobject.

~~~sql
SELECT
    lo.inst_id,
    lo.session_id AS sid,
    s.serial#,
    s.username,
    o.owner,
    o.object_name,
    o.subobject_name,
    lo.object_id,
    lo.locked_mode,
    s.status,
    s.module,
    s.action
FROM gv$locked_object lo
JOIN gv$session s
  ON s.inst_id = lo.inst_id
 AND s.sid = lo.session_id
LEFT JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.inst_id, lo.session_id, o.owner, o.object_name;
~~~

LOCKED_MODE dùng các giá trị mode ở mục 5.4. GV$LOCKED_OBJECT cho biết object bị transaction khóa, nhưng **không cung cấp trực tiếp ROWID của từng hàng**. Muốn tìm hàng cụ thể, cần kết hợp thông tin ROW_WAIT_* của waiter khi các cột này hợp lệ.

### 6.1. Không nhầm TX ID1 với OBJECT_ID

Trong GV$LOCK, ID1/ID2 mang ý nghĩa theo loại enqueue. Với TX, chúng định danh transaction resource; không được coi TX.ID1 là OBJECT_ID để join thẳng DBA_OBJECTS.

Với TM, ID1 thường tương ứng object ID của bảng bị khóa. Tuy nhiên, khi cần tên đối tượng và mode DML lock, GV$LOCKED_OBJECT thường dễ đọc hơn. Luôn xét TYPE trước khi diễn giải ID1/ID2.

## 7. Truy tìm hàng đang bị waiter chờ

V$SESSION có các cột ROW_WAIT_OBJ#, ROW_WAIT_FILE#, ROW_WAIT_BLOCK# và ROW_WAIT_ROW#. Các giá trị này hữu ích khi session đang chờ một transaction khác commit và Oracle đã xác định hàng liên quan. Chúng không hợp lệ cho mọi loại wait; ROW_WAIT_OBJ# = -1 thường biểu thị không có thông tin hàng đang chờ dùng được.

### 7.1. Xem đối tượng và ROWID đang chờ

~~~sql
SELECT
    w.inst_id,
    w.sid AS waiter_sid,
    w.serial# AS waiter_serial,
    w.event,
    w.seconds_in_wait,
    w.row_wait_obj#,
    o.owner,
    o.object_name,
    o.subobject_name,
    CASE
        WHEN w.row_wait_obj# <> -1 THEN
            DBMS_ROWID.ROWID_CREATE(
                1,
                w.row_wait_obj#,
                w.row_wait_file#,
                w.row_wait_block#,
                w.row_wait_row#
            )
    END AS waiting_rowid
FROM gv$session w
LEFT JOIN dba_objects o
  ON o.data_object_id = w.row_wait_obj#
WHERE w.blocking_session_status = 'VALID'
  AND w.row_wait_obj# <> -1
ORDER BY w.seconds_in_wait DESC;
~~~

ROWID_CREATE dựng ROWID từ object/file/block/row của vị trí đang chờ. Đối chiếu OWNER, OBJECT_NAME, SUBOBJECT_NAME và ROWID với bảng thực tế trước khi kết luận. Với partitioned table, DATA_OBJECT_ID giúp xác định segment/subobject tương ứng.

Chỉ dùng các cột ROW_WAIT_* khi waiter thực sự đang ở loại wait mà Oracle cung cấp thông tin hàng. Nếu các giá trị không hợp lệ, hãy điều tra theo object lock, SQL và transaction; không tự dựng ROWID từ các giá trị mặc định.

### 7.2. Xem hàng sau khi đã xác định bảng

Ví dụ nếu truy vấn cho thấy hàng thuộc APP.ORDERS, có thể dùng ROWID thu được để đọc đúng hàng:

~~~sql
SELECT *
FROM app.orders
WHERE ROWID = CHARTOROWID(:waiting_rowid);
~~~

Đây là thao tác đọc phục vụ chẩn đoán. Không tự động cập nhật hoặc xóa hàng đang bị chờ chỉ vì đã tìm được ROWID.

## 8. Truy tìm transaction giữ khóa

Session có thể không chạy SQL ở thời điểm quan sát nhưng vẫn có transaction mở. V$TRANSACTION/GV$TRANSACTION chứa thông tin transaction đang tồn tại.

### 8.1. Join session với transaction

~~~sql
SELECT
    b.inst_id,
    b.sid,
    b.serial#,
    b.username,
    b.status,
    b.module,
    b.action,
    b.machine,
    b.program,
    t.start_time,
    t.xidusn,
    t.xidslot,
    t.xidsqn,
    t.used_ublk,
    t.used_urec
FROM gv$session b
JOIN gv$transaction t
  ON t.inst_id = b.inst_id
 AND t.addr = b.taddr
WHERE EXISTS (
    SELECT 1
    FROM gv$session w
    WHERE w.blocking_session_status = 'VALID'
      AND w.blocking_instance = b.inst_id
      AND w.blocking_session = b.sid
)
ORDER BY t.start_time;
~~~

Giải thích:

- TADDR trong session trỏ tới transaction state object.
- ADDR trong transaction được dùng để ghép với TADDR trong cùng instance.
- START_TIME cho biết thời điểm transaction bắt đầu theo định dạng Oracle hiển thị.
- USED_UBLK và USED_UREC phản ánh lượng undo block/record đã dùng, giúp ước lượng quy mô thay đổi cần rollback nếu transaction bị hủy.

USED_UBLK/USED_UREC không phải bộ đếm chính xác thời gian rollback còn lại. Transaction lớn có thể mất thời gian cleanup đáng kể; đừng dùng một con số này để hứa thời điểm giải phóng khóa.

### 8.2. Tìm transaction của một session cụ thể

~~~sql
SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    s.username,
    s.status,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM gv$session s
JOIN gv$transaction t
  ON t.inst_id = s.inst_id
 AND t.addr = s.taddr
WHERE s.inst_id = :inst_id
  AND s.sid = :sid;
~~~

Thay bind bằng instance và SID lấy từ kết quả giám sát. Nếu không có hàng, session có thể đã kết thúc transaction trong lúc bạn điều tra hoặc không còn transaction hiện tại.

## 9. Tìm SQL và ứng dụng tạo ra blocker

### 9.1. SQL_ID hiện tại và trước đó

Trong V$SESSION:

- SQL_ID là SQL hiện tại của session nếu đang có.
- PREV_SQL_ID là SQL trước đó.

Một blocker INACTIVE thường không có SQL đang chạy; PREV_SQL_ID là manh mối để tìm câu lệnh gần nhất. Tuy nhiên, đó không phải bằng chứng tuyệt đối về câu SQL đã lấy khóa: session có thể đã chạy thêm SELECT hoặc câu SQL khác sau DML gây khóa.

### 9.2. Lấy SQL text

~~~sql
SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    s.status,
    s.sql_id,
    s.prev_sql_id,
    q.sql_text
FROM gv$session s
LEFT JOIN gv$sqlarea q
  ON q.inst_id = s.inst_id
 AND q.sql_id = COALESCE(s.sql_id, s.prev_sql_id)
WHERE s.inst_id = :blocker_inst_id
  AND s.sid = :blocker_sid;
~~~

GV$SQLAREA lưu thông tin SQL đã được parse trong shared pool. Nếu SQL đã bị aged out, câu truy vấn có thể không còn trả text. Nếu session hiện tại đang chạy SQL khác, text lấy được cũng có thể không phải câu lệnh đã mở transaction.

### 9.3. Xác định module, action và client

Các trường MODULE, ACTION, CLIENT_IDENTIFIER, MACHINE, PROGRAM trong GV$SESSION giúp nối session với ứng dụng, request hoặc job. Ứng dụng nên chủ động gắn ngữ cảnh:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OrderService',
        action_name => 'UpdateOrder'
    );
    DBMS_SESSION.SET_IDENTIFIER('request-2026-000123');
END;
/
~~~

Khi trả connection về pool, ứng dụng nên reset module/action/client identifier để request sau không kế thừa thông tin cũ. DBA có thể truy vấn:

~~~sql
SELECT
    inst_id,
    sid,
    serial#,
    username,
    module,
    action,
    client_identifier,
    machine,
    program,
    status
FROM gv$session
WHERE inst_id = :inst_id
  AND sid = :sid;
~~~

Nếu module/action/client identifier trống, có thể cần phối hợp với đội ứng dụng để bổ sung instrumentation. Không nên suy luận chính xác endpoint hoặc người dùng cuối chỉ từ MACHINE/PROGRAM.

### 9.4. Lịch sử SQL và ASH

GV$SQL/GV$SQLAREA chỉ giữ SQL còn trong shared pool. Nếu cần lịch sử hoạt động, DBA có thể xem AWR/ASH hoặc trace, nhưng V$ACTIVE_SESSION_HISTORY và DBA_HIST_ACTIVE_SESS_HISTORY cùng các báo cáo AWR thường thuộc phạm vi Diagnostics Pack licensing. SQL Monitor/một số báo cáo tuning có thể thuộc Tuning Pack. Hãy xác nhận quyền sử dụng và giấy phép của môi trường trước khi dùng các tính năng này.

Không mặc định rằng mọi hệ thống Oracle đều được phép truy vấn AWR/ASH. Nếu không có license phù hợp, dùng thông tin session hiện tại, SQL cache còn sẵn, application logs và trace được bật theo quy trình DBA.

## 10. Phân biệt các nguyên nhân nghẽn thường gặp

### 10.1. Transaction cập nhật chưa commit

Triệu chứng:

- Waiter có event enq: TX - row lock contention.
- BLOCKING_SESSION_STATUS = 'VALID'.
- Blocker có transaction trong GV$TRANSACTION.
- Blocker có thể INACTIVE.

Hướng điều tra: xác định ứng dụng và chủ sở hữu blocker; xem transaction bắt đầu khi nào và quy mô undo; xem SQL hiện tại/trước đó, module và request ID; hỏi đội sở hữu session xem có thể commit/rollback an toàn không.

### 10.2. SELECT FOR UPDATE

SELECT ... FOR UPDATE lấy khóa hàng để ứng dụng đọc rồi cập nhật nhất quán. Nếu ứng dụng giữ transaction mở sau khi đọc, session khác cần sửa cùng hàng sẽ chờ.

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id = 101
FOR UPDATE;
~~~

Khóa được giữ cho đến khi transaction commit hoặc rollback. Không dùng FOR UPDATE cho màn hình đọc thông thường nếu ứng dụng không cần khóa hàng.

### 10.3. TM contention và foreign key không có index

Một tình huống cần kiểm tra là bảng con có foreign key nhưng cột foreign key không được index. Khi session xóa hoặc thay đổi khóa ở bảng cha, Oracle có thể cần khóa bảng con mạnh hơn để bảo vệ toàn vẹn tham chiếu; DML đồng thời trên bảng con có thể bị ảnh hưởng.

Khi thấy enq: TM - contention, hãy kiểm tra object/table đang bị chờ, LMODE và REQUEST trong GV$LOCK, foreign key liên quan và index trên các cột FK, cùng DDL hoặc LOCK TABLE đang chạy.

Không phải mọi foreign key đều bắt buộc phải có index trong mọi hệ thống. Quyết định index phụ thuộc mẫu DML, yêu cầu toàn vẹn, cardinality và chi phí ghi.

### 10.4. ITL contention

enq: TX - allocate ITL entry có thể xảy ra khi block không còn transaction slot có thể dùng ngay. Đây là dạng tranh chấp khác với hai session cập nhật cùng một row. Cần xem segment, block, INITRANS, mức đồng thời và thiết kế lưu trữ; không xử lý bằng cách chỉ tìm một row lock rồi yêu cầu commit.

### 10.5. DDL chờ DML

DDL cần khóa phù hợp trên đối tượng. Nếu transaction DML chưa kết thúc, thao tác DDL có thể chờ. Tương tự, DDL đang giữ khóa có thể làm DML hoặc DDL khác chờ. Hãy kiểm tra EVENT, object và SQL của cả hai session trước khi kết luận.

## 11. Deadlock và ORA-00060

Deadlock là chu trình trong đồ thị chờ, không phải một hàng đợi dài thông thường.

~~~text
Session A                         Session B
---------                         ---------
UPDATE row 1                      UPDATE row 2
giữ khóa row 1                    giữ khóa row 2

UPDATE row 2  ----------------->  đang chờ row 2
đang chờ row 2

                                  UPDATE row 1
                                  đang chờ row 1

          A chờ B; B chờ A
                 |
                 v
          DEADLOCK CYCLE
~~~

Oracle phát hiện chu trình và báo ORA-00060 cho một statement trong chu trình, đồng thời ghi thông tin deadlock vào trace. Thông thường, statement gây deadlock bị rollback; transaction của session không nhất thiết bị rollback toàn bộ. Ứng dụng phải xử lý lỗi và quyết định rollback/retry transaction theo thiết kế.

### 11.1. Cách giảm deadlock

- Các transaction nên khóa nhiều hàng theo cùng một thứ tự, ví dụ tăng dần theo primary key.
- Giữ transaction ngắn.
- Tránh giữ khóa trong lúc gọi dịch vụ ngoài hoặc chờ người dùng.
- Cập nhật đúng phạm vi hàng; index phù hợp giúp giảm lượng dữ liệu cần truy cập.
- Xử lý ORA-00060 có retry giới hạn và backoff khi nghiệp vụ cho phép.

Không nên coi mọi ORA-00060 là lỗi để retry vô hạn. Nếu thứ tự khóa luôn tạo chu trình, retry chỉ làm lặp lại sự cố.

## 12. Xử lý blocker an toàn

Khi đã xác định root blocker, cần phối hợp với chủ sở hữu ứng dụng/transaction. Thứ tự ưu tiên:

1. **Xác nhận tác động:** bao nhiêu waiter, bảng nào, giao dịch nghiệp vụ nào bị ảnh hưởng.
2. **Xác định chủ sở hữu:** module, action, client identifier, machine, program và người trực ứng dụng.
3. **Kiểm tra trạng thái transaction:** thời gian bắt đầu, undo đã dùng, SQL gần nhất và trạng thái session.
4. **Yêu cầu session kết thúc transaction đúng nghiệp vụ:** commit nếu thay đổi cần lưu; rollback nếu thay đổi cần hủy.
5. **Chỉ terminate khi có thẩm quyền và đã đánh giá hậu quả:** ví dụ session bị bỏ quên hoặc ứng dụng không thể tự giải phóng.

Không chạy COMMIT hoặc ROLLBACK trong session giám sát với kỳ vọng nó sẽ kết thúc transaction của blocker. Mỗi transaction thuộc session của nó.

### 12.1. Kết thúc session trên một instance

Sau khi xác nhận đúng session và có phê duyệt vận hành:

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
~~~

Thay sid và serial# bằng giá trị vừa xác nhận. Cần quyền ALTER SYSTEM.

### 12.2. Kết thúc session trong RAC

Trong RAC, chỉ rõ instance:

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
~~~

Không dùng SID đơn lẻ để quyết định session cần kill; phải đối chiếu INST_ID, SID, SERIAL#, username và thông tin ứng dụng.

### 12.3. KILL SESSION không đồng nghĩa rollback hoàn tất ngay

Sau lệnh kill:

- Oracle đánh dấu session cần kết thúc.
- Transaction chưa commit cần được rollback.
- Nếu transaction lớn, cleanup có thể mất thời gian.
- Session có thể tạm hiển thị trạng thái KILLED trong lúc cleanup.
- Khóa được giải phóng theo tiến trình rollback/cleanup, không nhất thiết ngay khi câu lệnh ALTER SYSTEM trả về.

Theo dõi lại waiter, blocker, transaction và alert/trace theo quy trình DBA. Không lặp lệnh kill liên tục chỉ vì session chưa biến mất khỏi view ngay lập tức.

## 13. Phòng ngừa blocking trong ứng dụng

### 13.1. Giữ transaction ngắn

~~~text
BEGIN TRANSACTION
  Read required data
  Validate
  Perform DML
COMMIT

Only after commit:
  Call external service
  Wait for user
  Render response
~~~

Thiết kế cụ thể phụ thuộc nghiệp vụ, nhưng tránh giữ row lock trong thời gian gọi HTTP, gửi email, chờ nhập liệu hoặc xử lý tác vụ không liên quan đến transaction.

### 13.2. Dùng WAIT/NOWAIT/SKIP LOCKED đúng mục tiêu

Oracle hỗ trợ các lựa chọn cho SELECT ... FOR UPDATE:

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id = 101
FOR UPDATE NOWAIT;
~~~

NOWAIT trả lỗi ngay nếu hàng đang bị khóa, phù hợp khi ứng dụng muốn báo “đang được xử lý” thay vì chờ.

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id = 101
FOR UPDATE WAIT 5;
~~~

WAIT 5 chờ tối đa khoảng thời gian được chỉ định trước khi trả lỗi timeout nếu vẫn không lấy được khóa.

~~~sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id IN (101, 102)
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED bỏ qua hàng đang bị session khác khóa. Nó hữu ích cho mô hình worker lấy việc từ queue, nơi một worker có thể xử lý các hàng chưa bị chiếm. Không dùng tùy tiện trong nghiệp vụ cần bảo đảm mọi hàng đều được xử lý; bỏ qua hàng có thể làm thay đổi kết quả nghiệp vụ.

### 13.3. Thiết kế hàng đợi bằng SKIP LOCKED

Một worker có thể lấy một nhóm công việc chưa bị worker khác khóa:

~~~sql
SELECT job_id, payload
FROM lab_job_queue
WHERE status = 'READY'
ORDER BY created_at, job_id
FOR UPDATE SKIP LOCKED;
~~~

Sau khi lấy việc, worker cập nhật trạng thái và commit theo transaction ngắn. Cần thiết kế thêm cơ chế lease/retry/visibility timeout nếu worker chết sau khi khóa hoặc sau khi nhận việc. SKIP LOCKED không tự cung cấp toàn bộ semantics của một message queue.

Nếu mỗi worker chỉ được nhận một số lượng job giới hạn, hãy dùng cursor và chỉ fetch số hàng cần xử lý; đừng fetch toàn bộ kết quả READY. Với SELECT FOR UPDATE, các hàng được khóa khi được fetch, nên kích thước batch fetch là một phần của thiết kế queue. Đóng cursor và commit/rollback theo quy trình xử lý job.

### 13.4. Khóa nhiều hàng theo thứ tự thống nhất

Nếu hai transaction cần cập nhật cùng một tập tài khoản, hãy khóa theo cùng thứ tự:

~~~sql
SELECT account_id
FROM lab_lock_accounts
WHERE account_id IN (101, 102)
ORDER BY account_id
FOR UPDATE;
~~~

Việc khóa theo thứ tự thống nhất giảm khả năng transaction A khóa 101 rồi chờ 102 trong khi transaction B khóa 102 rồi chờ 101. Cần kiểm tra execution plan và mẫu truy vấn thực tế; thứ tự logic mong muốn phải được thể hiện rõ trong thiết kế.

### 13.5. Instrument session

Ứng dụng nên gắn MODULE, ACTION và CLIENT_IDENTIFIER. Những thông tin này giúp DBA nối session database với log ứng dụng. Không đưa thông tin bí mật hoặc dữ liệu cá nhân không cần thiết vào các trường này.

## 14. Checklist điều tra một sự cố blocking

| Bước | Câu hỏi cần trả lời | Nguồn thông tin |
| --- | --- | --- |
| 1 | Ai đang chờ? | GV$SESSION waiter, event, wait time |
| 2 | Ai chặn trực tiếp? | BLOCKING_INSTANCE, BLOCKING_SESSION |
| 3 | Root blocker là ai? | FINAL_BLOCKING_INSTANCE, FINAL_BLOCKING_SESSION |
| 4 | Bao nhiêu session bị ảnh hưởng? | Nhóm waiter theo final blocker |
| 5 | Loại tài nguyên nào? | EVENT, GV$LOCK TX/TM |
| 6 | Bảng/partition nào liên quan? | GV$LOCKED_OBJECT, DBA_OBJECTS |
| 7 | Hàng nào đang bị chờ? | ROW_WAIT_* khi hợp lệ |
| 8 | Transaction bắt đầu khi nào? | GV$TRANSACTION |
| 9 | SQL nào và ứng dụng nào? | SQL_ID, PREV_SQL_ID, GV$SQLAREA, module/action |
| 10 | Có thể giải phóng an toàn không? | Xác nhận với chủ sở hữu transaction và quy trình vận hành |

Ghi lại timestamp, instance, SID, serial, event, blocker, SQL ID, module và batch/request ID. Một sự cố blocking có thể biến mất trước khi truy vấn thứ hai chạy; snapshot có thời điểm rõ ràng giúp đối chiếu log và tái dựng diễn biến.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ tìm session ACTIVE nên bỏ sót blocker | Blocker có thể INACTIVE nhưng transaction chưa commit | Tìm waiter qua BLOCKING_SESSION_STATUS, rồi kiểm tra transaction |
| Ghép SID trong RAC nhưng không ghép INST_ID | SID có thể trùng giữa các instance | Dùng GV$SESSION và ghép cả instance + SID |
| Nhầm waiter với blocker | Chỉ nhìn session có event chờ | Dùng cột blocking session để xác định quan hệ |
| Thấy TX là kết luận row lock | TX còn có ITL/index/unique-related waits | Đọc chính xác wait event và object |
| Thấy TM là kết luận cả bảng bị khóa độc quyền | TM mode khác nhau và có tính tương thích | Xem LMODE, REQUEST, object và SQL |
| Join TX ID1 với DBA_OBJECTS.OBJECT_ID | TX ID1 không phải object ID | Dùng TYPE để diễn giải ID1/ID2; xem GV$LOCKED_OBJECT |
| Không thấy SQL của blocker | Session idle hoặc SQL đã aged out | Xem PREV_SQL_ID, SQLAREA còn cache, module/action và application log |
| Cho rằng PREV_SQL_ID chắc chắn là DML gây khóa | Session có thể chạy SQL khác sau DML | Dùng nó làm manh mối và đối chiếu transaction/application trace |
| ROW_WAIT_* không có giá trị | Không phải mọi wait đều cung cấp row location | Chỉ dùng khi row_wait_obj# hợp lệ và đúng loại wait |
| Kill blocker nhưng waiter vẫn chờ | Transaction rollback/cleanup chưa xong | Theo dõi tiến trình cleanup, không kill lặp |
| Xem blocking là deadlock | Một chiều chờ chưa tạo chu trình | Deadlock là vòng chờ; xem ORA-00060 và trace |
| Dùng SKIP LOCKED cho báo cáo cần đủ hàng | Hàng bị khóa bị bỏ qua | Chỉ dùng khi nghiệp vụ cho phép worker bỏ qua hàng đang được xử lý |
| Retry vô hạn sau ORA-00060 | Thứ tự khóa vẫn tạo chu trình | Chuẩn hóa thứ tự khóa và giới hạn retry/backoff |

## 16. Bài tập thực hành

Sử dụng LAB_LOCK_ACCOUNTS ở mục 2 và hai kết nối riêng.

### Bài 1 — Tạo row lock

Trong Session A, cập nhật account 101 nhưng chưa commit. Trong Session B, cập nhật cùng account. Ghi lại session nào là blocker, session nào là waiter và event của waiter.

### Bài 2 — So sánh INACTIVE và transaction mở

Sau khi Session A chạy UPDATE, để session A không chạy SQL nhưng không commit. Từ session thứ ba, truy vấn V$SESSION và V$TRANSACTION. Giải thích vì sao session INACTIVE vẫn có thể giữ khóa.

### Bài 3 — Xem waiter và blocker

Chạy truy vấn mục 3.2. Ghi lại SID, SERIAL#, SQL_ID, PREV_SQL_ID, MODULE và MACHINE của hai session.

### Bài 4 — Quan sát transaction

Dùng GV$TRANSACTION để xem START_TIME, USED_UBLK và USED_UREC của blocker. Commit hoặc rollback ở Session A, sau đó chạy lại truy vấn để quan sát transaction biến mất và waiter tiếp tục.

### Bài 5 — Xem lock mode

Truy vấn GV$LOCK cho TX/TM. Xác định session đang request lock và session đang giữ lock. Đối chiếu mode với bảng quy đổi trong bài.

### Bài 6 — Xem object và row wait

Dùng GV$LOCKED_OBJECT để xác định bảng bị khóa. Khi waiter đang ở enq: TX - row lock contention, kiểm tra ROW_WAIT_* và dựng ROWID nếu các cột hợp lệ. Đọc hàng bằng ROWID.

### Bài 7 — Thử SELECT FOR UPDATE

Session A chạy SELECT ... FOR UPDATE trên account 102. Session B thử FOR UPDATE NOWAIT, rồi thử WAIT 5. Ghi lại sự khác nhau về thời gian và kết quả.

### Bài 8 — Thiết kế worker queue

Giả sử có bảng job queue với trạng thái READY. Viết truy vấn lấy một số job bằng FOR UPDATE SKIP LOCKED. Giải thích vì sao hai worker có thể nhận các hàng khác nhau và cần xử lý thế nào nếu một worker dừng giữa chừng.

## 17. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi cả hai session đã commit/rollback và không còn giữ khóa:

~~~sql
DROP TABLE lab_lock_accounts PURGE;
~~~

Nếu bảng đang bị session khác sử dụng hoặc có transaction chưa kết thúc, hãy giải phóng transaction trước khi xóa. PURGE bỏ qua recycle bin; không dùng với bảng nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

Blocking xảy ra khi một session phải đợi tài nguyên mà transaction khác đang giữ. V$SESSION/GV$SESSION cho biết waiter, blocker trực tiếp và final blocker; GV$LOCK mô tả enqueue/mode; GV$LOCKED_OBJECT chỉ ra đối tượng; GV$TRANSACTION cho biết transaction đang mở; ROW_WAIT_* có thể giúp tìm hàng cụ thể khi Oracle cung cấp vị trí chờ.

Một blocker có thể INACTIVE nhưng vẫn giữ khóa vì transaction chưa commit/rollback. Truy tìm nguyên nhân cần kết hợp wait event, session identity, transaction, SQL ID, module/action và application log. Trong RAC, luôn ghép bằng cả INST_ID và SID. Phân biệt blocking một chiều với deadlock ORA-00060, và chỉ kết thúc session sau khi xác nhận chủ sở hữu cùng tác động rollback. Cách phòng ngừa hiệu quả nhất là transaction ngắn, thứ tự khóa thống nhất, index phù hợp, dùng NOWAIT/WAIT/SKIP LOCKED đúng nghiệp vụ và instrument ứng dụng để nhận diện request gây nghẽn.

## Tài liệu Oracle tham khảo

- [Oracle Database Reference — V$SESSION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html) — session state, wait event, blocking session và row-wait columns.
- [Oracle Database Reference — V$LOCK (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html) — enqueue, lock modes, request và blocking flags.
- [Oracle Database Reference — V$LOCKED_OBJECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html) — object locks của transaction.
- [Oracle Database Reference — V$TRANSACTION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html) — transaction state và undo usage.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — FOR UPDATE, NOWAIT, WAIT và SKIP LOCKED.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html) — gắn module và action vào session.

Khi triển khai trên Oracle release khác 19c hoặc RAC, hãy đối chiếu Reference đúng phiên bản, đặc biệt các cột blocking/final-blocking, wait event và cú pháp quản trị session.
