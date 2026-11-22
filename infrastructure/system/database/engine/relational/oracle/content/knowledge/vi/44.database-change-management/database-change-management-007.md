# Online DDL, DBMS_REDEFINITION và giới hạn khóa/tính năng trong Oracle Database

Thay đổi cấu trúc bảng trong database đang phục vụ ứng dụng thường khó vì DDL có thể phải chờ transaction, giữ khóa metadata hoặc làm gián đoạn DML trong một khoảng thời gian. Với bảng lớn, một thao tác tưởng đơn giản như thêm cột, đổi datatype, di chuyển segment hoặc tạo index có thể kéo dài và ảnh hưởng trực tiếp tới workload.

Oracle cung cấp nhiều cách giảm thời gian gián đoạn:

- **Online DDL:** dùng từ khóa `ONLINE` cho những thao tác DDL được Oracle hỗ trợ, chẳng hạn tạo/rebuild một số loại index hoặc di chuyển một số bảng.
- **DBMS_REDEFINITION:** xây dựng một bảng trung gian có cấu trúc đích, đồng bộ thay đổi từ bảng gốc và chuyển đổi metadata ở bước kết thúc.
- **DDL_LOCK_TIMEOUT:** điều khiển thời gian một DDL chờ khóa cần thiết trước khi báo lỗi.
- **Thiết kế triển khai theo giai đoạn:** thêm cấu trúc tương thích, deploy ứng dụng, backfill dữ liệu, chuyển đọc/ghi và dọn cấu trúc cũ.

Từ “online” không có nghĩa là “không khóa” hoặc “không có thời điểm chặn DML”. Nhiều thao tác vẫn cần khóa metadata ngắn ở đầu/cuối, có giới hạn theo loại object, datatype, edition, release update và trạng thái transaction. DBA phải kiểm tra chính xác thao tác được hỗ trợ, đo thời gian và chuẩn bị đường lui.

Bài học lấy Oracle Database 19c làm mốc. Nội dung giải thích cơ chế khóa, các dạng Online DDL, quy trình DBMS_REDEFINITION, giới hạn tính năng, cách theo dõi blocking session và cách lập kế hoạch thay đổi schema với downtime tối thiểu.

## 1. Vì sao DDL trên bảng lớn có thể gây gián đoạn?

### 1.1. DDL và DML có mục tiêu khác nhau

DML thay đổi dữ liệu hàng: `INSERT`, `UPDATE`, `DELETE`, `MERGE`. Oracle dùng row lock và table-level DML lock để bảo đảm tính nhất quán.

DDL thay đổi metadata hoặc cấu trúc object: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME`. Để thay đổi metadata an toàn, Oracle cần các loại lock khác, bao gồm DDL lock và library cache lock/pin tùy hoạt động.

Một DDL có thể:
- Chờ transaction đang dùng object hoàn tất.
- Chờ khóa metadata.
- Quét hoặc rewrite segment.
- Cập nhật index, constraint hoặc dependent object.
- Giữ khóa đủ lâu để chặn các session khác.
- Thành công nhanh nhưng gây invalidation/reparse ở workload kế tiếp.

### 1.2. DDL có implicit commit

Nhiều câu lệnh DDL thực hiện commit ngầm trước và sau thao tác. Vì vậy:

~~~sql
UPDATE app.orders
SET    status = 'READY'
WHERE  order_id = 1001;

ALTER TABLE app.orders ADD source_code VARCHAR2(20);

ROLLBACK;
~~~

`ROLLBACK` không hoàn tác DDL và có thể không hủy DML đã được commit ngầm trước DDL. Không gom DDL và DML vào một transaction rồi kỳ vọng có thể rollback toàn bộ migration.

Mỗi bước migration cần được thiết kế có thể tiếp tục, xác minh hoặc sửa bù độc lập.

### 1.3. “Online” không đồng nghĩa “zero downtime”

Một thao tác Online DDL có thể cho phép DML tiếp tục trong phần lớn thời gian thực hiện. Tuy vậy, nó vẫn có thể cần:
- Khóa ngắn để bắt đầu hoặc hoàn tất.
- Chờ transaction cũ kết thúc.
- Đồng bộ index/metadata.
- Dung lượng phụ để tạo segment mới.
- CPU và I/O đáng kể.
- Điều kiện riêng đối với partition, LOB, index type hoặc constraint.

Ứng dụng có thể thấy latency tăng, session chờ lock hoặc một số thao tác thất bại khi cửa sổ chuyển metadata xảy ra.

### 1.4. Xác định mức gián đoạn chấp nhận được

Trước khi chọn kỹ thuật, trả lời:

1. DML có phải tiếp tục trong lúc thay đổi không?
2. Có thể chặn ghi trong vài giây ở bước cuối không?
3. Bảng có bao nhiêu hàng, kích thước segment và tốc độ DML?
4. Có primary key ổn định không?
5. Có trigger, foreign key, materialized view log, LOB hoặc partition không?
6. Ứng dụng có tương thích đồng thời với schema cũ và mới không?
7. Có đủ tablespace/FRA cho segment trung gian và redo/undo không?
8. Có thể rollback hoặc forward-fix nếu bước cuối thất bại không?

Một thay đổi có downtime vài giây có thể chấp nhận được; thay đổi khác cần DML tiếp tục gần như toàn bộ thời gian. Đó là hai yêu cầu thiết kế khác nhau.

## 2. Các loại lock liên quan tới DDL

### 2.1. Row lock và TX enqueue

DML thường khóa các hàng mà transaction sửa. TX enqueue đại diện transaction lock. Một transaction chưa commit có thể giữ row lock lâu và khiến transaction khác chờ.

Ví dụ Session A:

~~~sql
UPDATE app.orders
SET    status = 'PROCESSING'
WHERE  order_id = 1001;

-- Chưa COMMIT hoặc ROLLBACK.
~~~

Session B cập nhật cùng hàng sẽ chờ row lock. Đây là blocking DML, không phải lỗi Online DDL.

### 2.2. TM table lock

DML còn lấy table-level lock (TM enqueue) để phối hợp thao tác trên object và bảo vệ tính toàn vẹn. Mức lock phụ thuộc loại statement và constraint.

TM lock không có nghĩa toàn bộ bảng luôn bị khóa độc quyền. Nhiều DML có thể cùng giữ row-exclusive table lock và cập nhật các hàng khác nhau.

### 2.3. DDL lock

DDL lock bảo vệ định nghĩa object trong khi thực hiện thay đổi. Một DDL cần mức lock tương thích với operation; nếu session khác giữ lock không tương thích, DDL có thể chờ.

Các thao tác có từ khóa ONLINE vẫn cần khóa metadata ở một số điểm. Vì vậy, transaction dài trên bảng có thể làm bước bắt đầu hoặc hoàn tất DDL bị chặn.

### 2.4. Library cache lock/pin

Oracle lưu metadata và cursor trong shared pool/library cache. DDL thay đổi object có thể cần invalidation hoặc lock/pin trên object metadata. Một số session đang parse hoặc sử dụng object có thể làm thay đổi metadata chờ lâu hơn.

Khi điều tra, không chỉ nhìn TX/TM. Cần xem wait event, blocking session, object và loại lock thực tế.

### 2.5. Kiểm tra DDL lock timeout

`DDL_LOCK_TIMEOUT` quy định số giây DDL chờ DML lock cần thiết trước khi báo lỗi. Giá trị mặc định thường là 0, tức không chờ nếu không lấy được lock ngay.

~~~sql
SHOW PARAMETER ddl_lock_timeout;
~~~

Đặt timeout trong session migration:

~~~sql
ALTER SESSION SET DDL_LOCK_TIMEOUT = 60;
~~~

Nếu lock chưa được giải phóng trong khoảng thời gian chờ, DDL có thể kết thúc với lỗi như ORA-00054. Timeout chỉ điều khiển thời gian chờ; nó không làm transaction đang giữ lock commit và cũng không làm DDL an toàn hơn.

### 2.6. WAIT khác DDL_LOCK_TIMEOUT

`DDL_LOCK_TIMEOUT` là tham số session áp dụng cho các DDL thuộc phạm vi hỗ trợ. Nó không giống mệnh đề WAIT/NOWAIT của một số câu lệnh khóa tường minh:

~~~sql
LOCK TABLE app.orders IN EXCLUSIVE MODE WAIT 10;
~~~

Không dùng `LOCK TABLE` để thay thế online DDL. Lệnh trên có thể chặn workload và chỉ phù hợp khi runbook chủ động yêu cầu khóa bảng.

## 3. Kiểm tra session đang giữ hoặc chờ lock

### 3.1. Xem object bị khóa

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.os_user_name,
       lo.locked_mode,
       obj.owner,
       obj.object_name,
       obj.object_type
FROM   v$locked_object lo
JOIN   dba_objects obj
       ON obj.object_id = lo.object_id
ORDER  BY obj.owner, obj.object_name, lo.session_id;
~~~

`LOCKED_MODE` là mã mức khóa. Có thể tra ý nghĩa trong Oracle Database Reference. View cần quyền phù hợp; trong môi trường hạn chế, DBA có thể chạy truy vấn thay cho application user.

### 3.2. Tìm blocking session

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       sql_id,
       module,
       program
FROM   v$session
WHERE  blocking_session IS NOT NULL
   OR  event LIKE '%enq:%'
ORDER  BY seconds_in_wait DESC;
~~~

`BLOCKING_SESSION` giúp tìm session đang chặn session khác khi Oracle xác định được blocker. Với RAC, dùng GV$SESSION và giữ INST_ID để phân biệt instance.

### 3.3. Xem lock theo session

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM   v$lock l
JOIN   v$session s
       ON s.sid = l.sid
WHERE  l.request > 0
   OR  l.block = 1
ORDER  BY l.block DESC, l.request DESC;
~~~

Các cột LMODE và REQUEST biểu diễn mode đang giữ và mode đang yêu cầu. ID1/ID2 có ý nghĩa phụ thuộc loại enqueue; không diễn giải chúng như object ID cho mọi loại lock.

### 3.4. Xem DDL lock

~~~sql
SELECT session_id,
       owner,
       name,
       type,
       mode_held,
       mode_requested
FROM   dba_ddl_locks
ORDER  BY owner, name, session_id;
~~~

View DBA_DDL_LOCKS giúp xem DDL lock theo object và session. Kết hợp với V$SESSION để tìm SQL, module và thời gian chờ.

### 3.5. Xác định transaction lâu

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       s.event,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM   v$transaction t
JOIN   v$session s
       ON s.taddr = t.addr
ORDER  BY t.start_time;
~~~

Transaction tồn tại lâu có thể giữ lock và tạo lượng undo lớn. Không kill session ngay khi thấy transaction lâu; xác định owner, business impact, rollback cost và phương án xử lý.

### 3.6. Không xử lý blocker theo cảm tính

Trước khi yêu cầu commit/rollback hoặc kill session:
- Xác định ứng dụng/job sở hữu session.
- Xác định transaction đang làm gì.
- Đánh giá rollback time và undo.
- Kiểm tra session có đang chạy batch quan trọng không.
- Thông báo owner theo quy trình.
- Chỉ kill session khi có phê duyệt và hiểu tác động.

Một DDL chờ lock có thể là dấu hiệu đúng của transaction nghiệp vụ đang hoạt động; ép giải phóng lock có thể gây hậu quả lớn hơn việc hoãn DDL.

## 4. Online DDL: nguyên tắc và nhóm thao tác

### 4.1. Cách hoạt động ở mức khái quát

Với một thao tác hỗ trợ ONLINE, Oracle có thể thực hiện phần lớn công việc trong khi DML tiếp tục. Tùy operation, Oracle có thể tạo hoặc duy trì cấu trúc trung gian, ghi nhận thay đổi đồng thời và đồng bộ trước khi hoàn tất.

Không phải mọi câu `ALTER TABLE ... ONLINE` đều hợp lệ. Từ khóa ONLINE chỉ được hỗ trợ trong những vị trí cú pháp được tài liệu hóa.

### 4.2. Tạo index online

~~~sql
CREATE INDEX app.ix_orders_status
ON app.orders(status)
ONLINE;
~~~

Trong thời gian build, ứng dụng có thể tiếp tục DML theo phạm vi hỗ trợ. Việc tạo index vẫn tiêu thụ CPU, I/O, TEMP và có thể cần khóa ngắn ở các giai đoạn chuyển trạng thái.

Kiểm tra:
- Index type có hỗ trợ ONLINE không.
- Table có LOB/partition/đặc tính đặc biệt không.
- Tablespace index có đủ chỗ không.
- DML rate có quá cao khiến build khó hoàn tất không.
- Edition và điều kiện license của tính năng.

### 4.3. Rebuild index online

~~~sql
ALTER INDEX app.ix_orders_status
REBUILD ONLINE;
~~~

Rebuild online thường được dùng để tái tạo một số loại index mà vẫn cho phép DML tiếp tục. Không phải mọi index type đều hỗ trợ; domain index, bitmap hoặc các cấu trúc đặc biệt có giới hạn riêng.

Nếu rebuild vào tablespace khác:

~~~sql
ALTER INDEX app.ix_orders_status
REBUILD TABLESPACE index_new ONLINE;
~~~

Kiểm tra cú pháp và thứ tự clause theo SQL Language Reference đúng release. Đo thời gian, dung lượng segment mới và tác động I/O trước khi chạy trên bảng lớn.

### 4.4. Di chuyển table online

Một số heap table có thể được di chuyển online:

~~~sql
ALTER TABLE app.orders
MOVE TABLESPACE data_new
ONLINE;
~~~

Mục đích có thể là chuyển tablespace, tái tổ chức segment hoặc thay đổi thuộc tính lưu trữ. `ONLINE` cho phép DML trong phần lớn operation được hỗ trợ, nhưng không có nghĩa không cần metadata lock.

Kiểm tra:
- Table type và thuộc tính có được hỗ trợ.
- LOB segment có cần di chuyển riêng không.
- Index có được duy trì hay cần rebuild.
- Partition/subpartition có cú pháp riêng.
- Segment mới và temporary space có đủ chỗ.
- Các dependent object và statistics sau thao tác.

### 4.5. Thêm cột

~~~sql
ALTER TABLE app.orders
ADD source_system VARCHAR2(30);
~~~

Thêm cột nullable không có default thường là thay đổi metadata nhanh, nhưng vẫn cần DDL lock. Thêm cột có default có thể được tối ưu theo cơ chế metadata-only/fast add trong các trường hợp Oracle hỗ trợ.

Không giả định mọi default expression đều có cùng chi phí. Default constant, default biểu thức, NOT NULL, datatype và release có thể làm thay đổi cách Oracle thực hiện. Test với dữ liệu và phiên bản tương đương production.

### 4.6. Thêm constraint theo giai đoạn

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT ck_orders_amount
CHECK (amount >= 0)
ENABLE NOVALIDATE;
~~~

ENABLE NOVALIDATE không quét và xác nhận toàn bộ dữ liệu cũ theo cách ENABLE VALIDATE thực hiện. Constraint được bật để kiểm soát DML mới theo semantics của loại constraint; dữ liệu lịch sử có thể vẫn chứa vi phạm.

Sau khi sửa dữ liệu cũ, có thể validate:

~~~sql
ALTER TABLE app.orders
ENABLE VALIDATE CONSTRAINT ck_orders_amount;
~~~

Validation có thể đọc nhiều dữ liệu và có yêu cầu khóa/tài nguyên riêng. Kiểm tra behavior của loại constraint, edition/release và workload trước khi chọn thời điểm.

### 4.7. Đổi datatype hoặc cấu trúc phức tạp

Các thay đổi như đổi datatype cột lớn, thay đổi nullability, đổi partitioning, thêm cột tính toán hoặc chuyển đổi kiểu dữ liệu có thể cần scan/rewrite và có giới hạn online.

Nếu không có cú pháp ONLINE phù hợp, hoặc thao tác không đáp ứng yêu cầu concurrency, xem DBMS_REDEFINITION. Không thêm từ khóa ONLINE vào câu lệnh không hỗ trợ rồi giả định Oracle tự chuyển thành online operation.

### 4.8. SET UNUSED và DROP UNUSED COLUMNS

Có thể đánh dấu cột không còn sử dụng:

~~~sql
ALTER TABLE app.orders
SET UNUSED (legacy_code);
~~~

Đây thường là thao tác metadata nhanh hơn việc xóa vật lý cột ngay lập tức. Cột không còn xuất hiện trong truy vấn thông thường nhưng không gian chưa được thu hồi ngay.

Thu hồi vật lý sau đó:

~~~sql
ALTER TABLE app.orders
DROP UNUSED COLUMNS;
~~~

DROP UNUSED COLUMNS có thể cần rewrite và tiêu thụ tài nguyên đáng kể. Có thể thực hiện theo batch/checkpoint trong trường hợp được hỗ trợ; đọc cú pháp đúng release và đánh giá thời gian.

## 5. Các giới hạn cần hiểu trước khi dùng ONLINE

### 5.1. Giới hạn theo operation

Từ khóa ONLINE không áp dụng đồng nhất cho mọi DDL. Mỗi operation có danh sách object/type/option hỗ trợ riêng.

Ví dụ:
- CREATE INDEX ONLINE hỗ trợ một số loại index và điều kiện nhất định.
- ALTER INDEX REBUILD ONLINE có giới hạn theo index type.
- ALTER TABLE MOVE ONLINE có giới hạn theo loại bảng và thuộc tính.
- Thay đổi constraint có semantics ENABLE/DISABLE/VALIDATE riêng.
- Một số thay đổi cột có thể cần rewrite.
- Partition maintenance có cú pháp và giới hạn theo operation.

Tra SQL Language Reference 19c của chính câu lệnh đang dùng, không suy ra từ câu lệnh tương tự.

### 5.2. Giới hạn theo object

Cần kiểm tra kỹ nếu bảng có:
- LONG hoặc kiểu dữ liệu legacy.
- LOB/SecureFiles.
- IOT hoặc clustered table.
- Nested table/object type.
- Virtual column hoặc hidden column.
- Partition/subpartition.
- Materialized view log.
- Trigger và foreign key phức tạp.
- Domain index hoặc bitmap index.
- Replication/CDC dependency.
- VPD/RLS policy hoặc audit policy.

Danh sách này là các dấu hiệu cần xem xét, không có nghĩa tất cả đều không hỗ trợ. Hỗ trợ cụ thể phụ thuộc thao tác và release.

### 5.3. Giới hạn theo edition và licensing

Một số khả năng online và online table redefinition phụ thuộc edition hoặc option của Oracle Database. Không suy ra quyền sử dụng chỉ vì cú pháp chạy được hoặc package tồn tại.

Trước khi triển khai:
- Kiểm tra Oracle Database edition.
- Kiểm tra Licensing Information User Manual của 19c và offering đang dùng.
- Xác nhận quyền dùng Online Index/Online Table Redefinition tương ứng.
- Kiểm tra hợp đồng BYOL/license-included nếu dùng cloud.
- Ghi nhận phạm vi tính năng được phép dùng.

Không thay thế kiểm tra licensing bằng V$OPTION hoặc một lần chạy thử.

### 5.4. Giới hạn tài nguyên

Online operation thường cần dung lượng bổ sung vì cấu trúc cũ và mới có thể cùng tồn tại trong một khoảng thời gian.

Ước lượng:
- Segment table/index mới.
- Temporary segment.
- TEMP cho sort/build.
- UNDO cho DML đồng thời.
- REDO và archived log.
- FRA/backup capacity.
- CPU và I/O headroom.

Nếu storage đầy giữa operation, DDL có thể thất bại hoặc ảnh hưởng workload khác.

### 5.5. Tác động tới optimizer và ứng dụng

Sau DDL:
- Cursor có thể bị invalidated và parse lại.
- Statistics có thể cần thu thập hoặc kiểm tra.
- Index mới có thể thay đổi execution plan.
- Cột mới có thể chưa được application version cũ xử lý.
- Constraint mới có thể làm DML trước đây thành lỗi.
- Trigger/dependent object có thể cần compile hoặc kiểm tra.

Online chỉ nói về khả năng duy trì hoạt động trong lúc thay đổi, không bảo đảm ứng dụng tương thích schema mới.

## 6. DBMS_REDEFINITION là gì?

### 6.1. Mục đích

`DBMS_REDEFINITION` cho phép thay đổi cấu trúc một bảng lớn trong khi bảng gốc vẫn tiếp tục phục vụ DML trong phần lớn quá trình.

Ý tưởng:
1. Tạo một **interim table** có cấu trúc đích.
2. Kiểm tra bảng gốc có đủ điều kiện redefine.
3. Bắt đầu redefinition để Oracle copy dữ liệu và theo dõi thay đổi đồng thời.
4. Sao chép các dependent object cần thiết.
5. Đồng bộ thay đổi phát sinh sau lần copy ban đầu.
6. Hoàn tất bằng một bước chuyển đổi metadata cần khóa ngắn.
7. Xác minh object và dọn bảng trung gian cũ theo quy trình.

~~~text
Bảng gốc ORDERS
      |
      | START_REDEF_TABLE
      v
Copy dữ liệu + ghi nhận thay đổi DML
      |
      +-----------------------------+
      | DML vẫn tiếp tục trên gốc   |
      +-----------------------------+
      |
      v
Bảng trung gian ORDERS_INT
      |
      | COPY_TABLE_DEPENDENTS
      | SYNC_INTERIM_TABLE
      v
FINISH_REDEF_TABLE
      |
      | khóa metadata trong bước chuyển
      v
Cấu trúc mới hoạt động dưới tên bảng gốc
~~~

### 6.2. Khi nào phù hợp?

DBMS_REDEFINITION phù hợp khi cần:
- Thay đổi thứ tự hoặc cấu trúc cột.
- Đổi datatype theo mapping được hỗ trợ.
- Di chuyển table sang tablespace mới.
- Thay đổi cách tổ chức/partitioning.
- Tạo cấu trúc mới và chuyển dữ liệu từ bảng cũ.
- Giảm thời gian DML bị chặn so với một thao tác offline dài.

Không phải công cụ sửa mọi schema change. Cần kiểm tra eligibility, datatype, dependency và tài nguyên trước.

### 6.3. Chi phí của redefinition

Trong thời gian chạy, có thể tồn tại đồng thời:
- Segment của bảng gốc.
- Segment interim table.
- Index/LOB/partition mới.
- Redo/undo do copy và DML đồng thời.
- Metadata/dependent object đang được copy.

Vì vậy, redefinition thường cần thêm dung lượng và I/O đáng kể. Một bảng lớn không đủ free space để chứa cấu trúc trung gian có thể không phù hợp dù yêu cầu downtime rất thấp.

## 7. Chuẩn bị trước khi redefine

### 7.1. Chọn phương thức CONS_USE_PK hoặc CONS_USE_ROWID

DBMS_REDEFINITION hỗ trợ hai phương thức phổ biến:

- `DBMS_REDEFINITION.CONS_USE_PK`: dùng primary key hoặc unique key đáp ứng điều kiện của package để nhận diện hàng.
- `DBMS_REDEFINITION.CONS_USE_ROWID`: dùng ROWID khi bảng không có khóa phù hợp; Oracle sử dụng cơ chế rowid-based redefinition và có thể thêm cột nội bộ phục vụ quá trình.

Ưu tiên primary key ổn định khi bảng có khóa phù hợp. Rowid method có giới hạn và yêu cầu riêng; kiểm tra package reference và `CAN_REDEF_TABLE` trước khi dùng.

### 7.2. Kiểm tra table có thể redefine

Ví dụ:

~~~sql
BEGIN
    DBMS_REDEFINITION.CAN_REDEF_TABLE(
        uname        => 'APP',
        tname        => 'ORDERS',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

Procedure kiểm tra bảng có thể dùng phương thức đã chọn. Nếu bảng không đủ điều kiện, procedure trả lỗi mô tả nguyên nhân. Không bỏ qua lỗi eligibility rồi tiếp tục tạo interim table theo suy đoán.

Có thể kiểm tra bằng CONS_USE_ROWID nếu thiết kế phù hợp và package hỗ trợ cho object đó.

### 7.3. Kiểm tra cấu trúc hiện tại

~~~sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
~~~

Kiểm tra khóa:

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   all_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY constraint_type, constraint_name;
~~~

Kiểm tra dependent object: indexes, triggers, grants, constraints, materialized view logs, policies, synonyms và ứng dụng phụ thuộc.

### 7.4. Tạo interim table

Giả sử muốn thêm cột SOURCE_SYSTEM và chuyển CREATED_AT thành ORDER_CREATED_AT:

~~~sql
CREATE TABLE app.orders_int (
    order_id          NUMBER        NOT NULL,
    customer_id       NUMBER        NOT NULL,
    order_created_at  TIMESTAMP(6),
    status            VARCHAR2(30),
    source_system     VARCHAR2(30),
    CONSTRAINT pk_orders_int PRIMARY KEY (order_id)
)
TABLESPACE data_new;
~~~

Interim table phải có cấu trúc đích phù hợp với column mapping. Không tạo index/constraint trùng lặp trước khi hiểu bước COPY_TABLE_DEPENDENTS sẽ tạo những object nào.

DDL tạo bảng có implicit commit. Dùng schema test và kiểm tra tablespace/privilege trước khi chạy production.

### 7.5. Quyền thực thi

Tài khoản chạy redefinition cần quyền thực hiện các thao tác trên bảng gốc và interim table, cùng quyền execute package DBMS_REDEFINITION. Khi redefine object của schema khác, cần quyền quản trị phù hợp theo tài liệu Oracle.

Không cấp quyền ANY hoặc DBA rộng chỉ để làm ví dụ chạy được. DBA nên cấp đúng quyền cần thiết cho owner/operator và thu hồi quyền tạm thời sau change nếu chính sách yêu cầu.

## 8. Quy trình DBMS_REDEFINITION từng bước

Ví dụ dưới đây dùng schema APP, bảng ORDERS và interim table ORDERS_INT. Đây là khung minh họa; phải thay cấu trúc, quyền, tablespace và tên cột theo database thật.

### 8.1. Bước 1 — CAN_REDEF_TABLE

~~~sql
BEGIN
    DBMS_REDEFINITION.CAN_REDEF_TABLE(
        uname        => 'APP',
        tname        => 'ORDERS',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

Procedure kiểm tra bảng có thể dùng phương thức đã chọn. Chỉ tiếp tục khi không có lỗi và các điều kiện nghiệp vụ/tài nguyên đã được xác nhận.

### 8.2. Bước 2 — START_REDEF_TABLE

~~~sql
BEGIN
    DBMS_REDEFINITION.START_REDEF_TABLE(
        uname        => 'APP',
        orig_table   => 'ORDERS',
        int_table    => 'ORDERS_INT',
        col_mapping  =>
            'ORDER_ID ORDER_ID, ' ||
            'CUSTOMER_ID CUSTOMER_ID, ' ||
            'CREATED_AT ORDER_CREATED_AT, ' ||
            'STATUS STATUS, ' ||
            'CAST(NULL AS VARCHAR2(30)) SOURCE_SYSTEM',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

`col_mapping` mô tả cách lấy cột từ bảng gốc sang interim table. Biểu thức có thể dùng để đổi tên hoặc chuyển đổi giá trị nếu kiểu dữ liệu và quy tắc redefinition hỗ trợ.

Kiểm tra kỹ:
- Mỗi cột đích có biểu thức mapping hợp lệ.
- Datatype/precision/scale tương thích.
- NOT NULL/default/identity semantics.
- Giá trị biểu thức không vi phạm constraint.
- Primary key mapping nhất quán.

Không đưa hàm không deterministic hoặc biểu thức có side effect vào mapping nếu chưa hiểu tác động khi copy/sync.

### 8.3. Bước 3 — COPY_TABLE_DEPENDENTS

~~~sql
DECLARE
    l_num_errors PLS_INTEGER;
BEGIN
    DBMS_REDEFINITION.COPY_TABLE_DEPENDENTS(
        uname            => 'APP',
        orig_table       => 'ORDERS',
        int_table        => 'ORDERS_INT',
        copy_indexes     => DBMS_REDEFINITION.CONS_ORIG_PARAMS,
        copy_triggers    => TRUE,
        copy_constraints => TRUE,
        copy_privileges  => TRUE,
        ignore_errors    => FALSE,
        num_errors       => l_num_errors,
        copy_statistics  => TRUE,
        copy_mvlog       => FALSE
    );

    DBMS_OUTPUT.PUT_LINE('Dependent object errors: ' || l_num_errors);
END;
/
~~~

Procedure sao chép các dependent object được chỉ định. Tùy chọn `copy_indexes` điều khiển cách copy index; `CONS_ORIG_PARAMS` yêu cầu dùng các tham số index gốc theo cơ chế package.

Nếu có lỗi, xem `DBA_REDEFINITION_ERRORS` và xử lý từng object. Không đặt `ignore_errors => TRUE` chỉ để quy trình chạy tiếp mà chưa xác định object nào bị bỏ qua.

Ví dụ tra lỗi:

~~~sql
SELECT object_owner,
       object_name,
       base_table_owner,
       base_table_name,
       ddl_txt
FROM   dba_redefinition_errors
WHERE  base_table_owner = 'APP'
AND    base_table_name = 'ORDERS';
~~~

### 8.4. Bước 4 — SYNC_INTERIM_TABLE

Trong khi DML vẫn tiếp tục trên bảng gốc, đồng bộ các thay đổi phát sinh:

~~~sql
BEGIN
    DBMS_REDEFINITION.SYNC_INTERIM_TABLE(
        uname      => 'APP',
        orig_table => 'ORDERS',
        int_table  => 'ORDERS_INT'
    );
END;
/
~~~

Có thể chạy SYNC_INTERIM_TABLE nhiều lần trước bước kết thúc để giảm lượng thay đổi còn tồn tại. Với bảng có DML cao, theo dõi thời gian sync và tốc độ phát sinh thay đổi.

Không để redefinition chạy quá lâu mà không giám sát; interim table, redo/undo và segment mới đều tiêu thụ tài nguyên.

### 8.5. Bước 5 — FINISH_REDEF_TABLE

~~~sql
BEGIN
    DBMS_REDEFINITION.FINISH_REDEF_TABLE(
        uname            => 'APP',
        orig_table       => 'ORDERS',
        int_table        => 'ORDERS_INT',
        dml_lock_timeout => 30
    );
END;
/
~~~

FINISH_REDEF_TABLE đồng bộ thay đổi cuối và hoàn tất chuyển đổi. Bước này cần khóa DML/metadata ngắn để bảo đảm nhất quán. `dml_lock_timeout` giới hạn thời gian chờ lấy lock theo package semantics.

Nếu không lấy được lock trong thời gian cho phép, finish có thể thất bại. Khi đó đánh giá blocker, sync lại nếu cần và thử lại trong cửa sổ phù hợp. Không tăng timeout quá cao khi ứng dụng không thể chịu việc DML chờ lâu.

### 8.6. Bước 6 — Kiểm tra sau khi finish

Kiểm tra cấu trúc:

~~~sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
~~~

Kiểm tra index:

~~~sql
SELECT index_name,
       index_type,
       status,
       visibility
FROM   all_indexes
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY index_name;
~~~

Kiểm tra constraint:

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   all_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY constraint_name;
~~~

Kiểm tra trigger, grants, statistics, invalid objects, row count và dữ liệu mẫu. Chỉ dọn object cũ/interim theo trạng thái thực tế sau khi xác nhận metadata đã chuyển thành công.

### 8.7. Bước 7 — Dọn interim/old object

Sau khi finish, tên interim có thể được dùng cho bảng cũ theo quy trình hoán đổi của redefinition. Kiểm tra DBA_TABLES, DBA_OBJECTS và package documentation trước khi DROP.

Không chạy `DROP TABLE APP.ORDERS_INT` một cách mù quáng ngay sau finish nếu chưa xác nhận object nào đang mang tên đó. Lưu backup/đối chiếu cần thiết và chỉ xóa đúng object cũ sau khi ứng dụng đã được xác minh.

## 9. Hủy hoặc xử lý redefinition thất bại

### 9.1. ABORT_REDEF_TABLE

Nếu cần hủy khi redefinition chưa finish:

~~~sql
BEGIN
    DBMS_REDEFINITION.ABORT_REDEF_TABLE(
        uname      => 'APP',
        orig_table => 'ORDERS',
        int_table  => 'ORDERS_INT'
    );
END;
/
~~~

Abort chấm dứt quá trình redefinition đang chạy. Bảng gốc vẫn là object ứng dụng đang dùng; kiểm tra trạng thái và dọn interim/dependent object còn lại theo tài liệu.

### 9.2. Khi COPY_TABLE_DEPENDENTS có lỗi

- Xem DBA_REDEFINITION_ERRORS.
- Xác định object nào không copy được.
- Kiểm tra object có thể tạo thủ công sau finish hay không.
- Kiểm tra trigger/constraint/index có phụ thuộc tên cột cũ không.
- Chọn sửa và chạy lại bước phù hợp hoặc abort.
- Không finish khi thiếu dependency quan trọng.

### 9.3. Khi SYNC_INTERIM_TABLE kéo dài

Nguyên nhân có thể:
- DML rate cao.
- Redo/undo hoặc I/O bị giới hạn.
- Interim table/index không đủ tài nguyên.
- Transaction lớn trên bảng gốc.
- Storage bị cạnh tranh bởi backup hoặc batch.

Theo dõi thời gian, lượng redo, session wait và blocker. Có thể điều chỉnh workload, chạy sync nhiều lần hoặc lên lịch finish khi DML thấp.

### 9.4. Khi FINISH_REDEF_TABLE không lấy được lock

Tìm blocker và transaction dài. Không kill session theo phản xạ. Có thể:
- Chờ transaction tự hoàn tất.
- Yêu cầu application owner đóng transaction.
- Giảm DML trong thời gian ngắn.
- Chọn thời điểm ít tải.
- Tăng `dml_lock_timeout` có kiểm soát nếu business cho phép.
- Đồng bộ interim lại trước lần finish tiếp theo.

### 9.5. Kiểm tra trạng thái redefinition

Các view như DBA_REDEFINITION_OBJECTS và DBA_REDEFINITION_ERRORS có thể hỗ trợ theo dõi object và lỗi tùy release. Kiểm tra dictionary view có sẵn bằng DESC và tra Oracle Database Reference. Không dựa vào một view duy nhất để suy ra mọi bước đã hoàn tất.

## 10. Thay đổi constraint online theo giai đoạn

### 10.1. ENABLE NOVALIDATE

Có thể thêm constraint và bật enforcement cho DML mới mà chưa xác thực toàn bộ dữ liệu cũ:

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT ck_orders_total
CHECK (total_amount >= 0)
ENABLE NOVALIDATE;
~~~

Điều này giúp chia việc triển khai thành hai phần:
1. Đưa constraint vào để kiểm soát thay đổi mới.
2. Làm sạch dữ liệu cũ và validate sau.

Các semantics khác nhau theo loại constraint; đặc biệt unique/primary key cần index/điều kiện riêng. Kiểm tra loại constraint và tài liệu trước khi dùng.

### 10.2. Tìm dữ liệu vi phạm trước khi VALIDATE

~~~sql
SELECT order_id,
       total_amount
FROM   app.orders
WHERE  total_amount < 0;
~~~

Sửa dữ liệu theo nghiệp vụ, không chỉ đổi số âm thành 0 để lệnh validate thành công. Sau đó:

~~~sql
ALTER TABLE app.orders
ENABLE VALIDATE CONSTRAINT ck_orders_total;
~~~

Validation có thể đọc toàn bộ bảng và cần tài nguyên. Theo dõi lock/wait và thực hiện khi workload phù hợp.

### 10.3. NOVALIDATE không có nghĩa constraint đã đúng với dữ liệu lịch sử

Một constraint ENABLE NOVALIDATE vẫn có thể để lại hàng cũ vi phạm. Truy vấn dữ liệu cũ có thể vẫn trả các hàng vi phạm. Ghi rõ trạng thái ENABLED/VALIDATED trong metadata và change record.

~~~sql
SELECT constraint_name,
       status,
       validated
FROM   all_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS';
~~~

## 11. Online index và index maintenance

### 11.1. Tạo index online

~~~sql
CREATE INDEX app.ix_orders_created
ON app.orders(created_at)
ONLINE;
~~~

Index build cần đọc dữ liệu và ghi segment index. DML đồng thời có thể được theo dõi/đồng bộ theo cơ chế Oracle. Tác động CPU/I/O vẫn đáng kể.

### 11.2. Rebuild online và unusable index

~~~sql
ALTER INDEX app.ix_orders_created
REBUILD ONLINE;
~~~

Trước rebuild:
- Kiểm tra index status.
- Kiểm tra index type và partition.
- Xem tablespace/free space.
- Xác định index có được dùng bởi constraint không.
- Đánh giá plan và thời gian build.
- Kiểm tra license/edition.

Không rebuild index chỉ vì index lớn; xem segment growth, blevel, clustering factor, workload và lý do cụ thể.

### 11.3. Index partition

Với local/global partitioned index, cú pháp và tác động khác nhau. Một thao tác partition maintenance có thể làm global index unusable nếu không chỉ định cách duy trì phù hợp.

Kiểm tra `DBA_IND_PARTITIONS`, `DBA_IND_SUBPARTITIONS`, `DBA_INDEXES` và cú pháp `UPDATE INDEXES`/`UPDATE GLOBAL INDEXES` phù hợp operation. Không dùng một câu rebuild index toàn cục cho mọi trường hợp.

### 11.4. Theo dõi tiến độ

~~~sql
SELECT sid,
       serial#,
       opname,
       target,
       sofar,
       totalwork,
       units,
       elapsed_seconds,
       time_remaining
FROM   v$session_longops
WHERE  totalwork > 0
AND    sofar < totalwork
ORDER  BY elapsed_seconds DESC;
~~~

Không phải mọi DDL đều xuất hiện trong V$SESSION_LONGOPS. Kết hợp alert log, session wait, SQL monitor nếu được cấp phép và thời gian thực tế.

## 12. Thiết kế migration không gián đoạn bằng expand-and-contract

### 12.1. Vì sao cần nhiều bước?

Ngay cả khi DDL online, ứng dụng cũ và mới có thể cùng hoạt động trong lúc rolling deployment. Nếu đổi tên cột ngay lập tức, phiên bản cũ có thể lỗi trước khi toàn bộ instance được nâng cấp.

Mô hình expand-and-contract:
1. **Expand:** thêm cột/bảng/constraint mới tương thích với code cũ.
2. **Deploy:** triển khai code có thể đọc/ghi cả cấu trúc cũ và mới.
3. **Backfill:** copy dữ liệu sang cột/cấu trúc mới theo batch.
4. **Verify:** đối chiếu dữ liệu và chuyển traffic/read path.
5. **Contract:** ngừng dùng cấu trúc cũ rồi mới drop/rename sau thời gian an toàn.

### 12.2. Ví dụ đổi tên cột

Giả sử cần đổi tên CUSTOMER_NAME thành DISPLAY_NAME.

Không nên chỉ:
~~~sql
ALTER TABLE app.customer RENAME COLUMN customer_name TO display_name;
~~~

nếu ứng dụng cũ vẫn truy vấn CUSTOMER_NAME.

Quy trình tương thích:
1. Add DISPLAY_NAME nullable/default phù hợp.
2. Deploy application ghi đồng thời hoặc dual-write theo chính sách.
3. Backfill DISPLAY_NAME theo batch.
4. Đối chiếu dữ liệu.
5. Chuyển ứng dụng đọc DISPLAY_NAME.
6. Ngừng ghi CUSTOMER_NAME.
7. Sau thời gian ổn định mới drop/rename cột cũ trong change riêng.

Dual-write cần xử lý lỗi một phía, transaction và concurrency. Có thể dùng trigger tạm thời nhưng phải đánh giá recursion, performance và logic nghiệp vụ.

### 12.3. Backfill theo batch

~~~sql
UPDATE app.customer
SET    display_name = customer_name
WHERE  display_name IS NULL
AND    customer_id BETWEEN :low_id AND :high_id;
~~~

Chia range giúp giới hạn transaction/undo và theo dõi tiến độ. Chọn batch size dựa trên redo, undo, lock, replication lag và workload. Commit từng batch theo quy trình, ghi checkpoint để có thể tiếp tục.

### 12.4. Kiểm tra consistency

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM   app.customer
WHERE  NVL(display_name, CHR(0))
   <>  NVL(customer_name, CHR(0));
~~~

Điều kiện thực tế cần xử lý NULL, collation và quy tắc chuẩn hóa dữ liệu chính xác. Không dùng sentinel value có thể xuất hiện trong dữ liệu thật; đây chỉ là ví dụ minh họa.

## 13. Thời gian khóa và chiến lược cutover

### 13.1. Đo lock window riêng

Với DBMS_REDEFINITION, phần copy/sync có thể kéo dài nhưng DML vẫn tiếp tục. FINISH_REDEF_TABLE là điểm cutover cần lock để đồng bộ cuối và đổi metadata.

Hãy đo:
- Thời gian lấy lock.
- Thời gian sync cuối.
- Thời gian finish.
- Số transaction bị chờ.
- p95/p99 latency của ứng dụng.
- Số session bị block.
- Thời gian validate sau cutover.

Đừng dùng tổng thời gian redefinition làm downtime estimate; cần đo riêng giai đoạn chặn DML.

### 13.2. Hạ DML rate trước cutover

Có thể giảm lượng thay đổi còn phải sync bằng:
- Chọn giờ ít tải.
- Tạm dừng batch ghi lớn.
- Điều phối deploy và maintenance.
- Chia batch trước đó.
- Thông báo application owner để giảm concurrency trong vài phút.

Không cần dừng toàn bộ ứng dụng nếu operation hỗ trợ DML; mục tiêu là làm bước cuối ngắn và dự đoán được.

### 13.3. DDL_LOCK_TIMEOUT có giới hạn

Tăng timeout có thể khiến DDL chờ lâu hơn, nhưng đồng thời:
- DDL session giữ tài nguyên và có thể tạo hàng chờ.
- Session khác có thể bị ảnh hưởng tùy lock/order.
- Maintenance vượt quá cửa sổ đã dự kiến.
- Người vận hành khó biết khi nào nên hủy.

Chọn timeout có giới hạn và quy tắc retry. Không đặt giá trị rất lớn như một cách che blocker.

### 13.4. Lock timeout và ứng dụng

Khi DDL đang chờ lock, ứng dụng có thể tiếp tục hoạt động hoặc phát sinh queue tùy loại lock và operation. Theo dõi cả:
- Blocking session.
- Waiting session.
- Connection pool pending threads.
- Request latency.
- Error rate.
- Database wait class.

Nếu latency vượt ngưỡng, dừng hoặc hoãn DDL theo runbook.

## 14. Giám sát và xác minh sau DDL

### 14.1. Kiểm tra object status

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM   dba_objects
WHERE  owner = 'APP'
AND    object_name IN ('ORDERS', 'IX_ORDERS_STATUS')
ORDER  BY object_type, object_name;
~~~

### 14.2. Kiểm tra invalid object

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM   dba_objects
WHERE  owner = 'APP'
AND    status <> 'VALID'
ORDER  BY object_type, object_name;
~~~

Một số object có thể invalid sau thay đổi phụ thuộc. Xác định nguyên nhân và compile theo quy trình; không compile hàng loạt mà chưa biết dependency.

### 14.3. Kiểm tra index

~~~sql
SELECT index_name,
       index_type,
       status,
       visibility,
       uniqueness
FROM   dba_indexes
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY index_name;
~~~

Với partitioned index, kiểm tra thêm trạng thái từng partition/subpartition.

### 14.4. Kiểm tra constraint

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       rely
FROM   dba_constraints
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY constraint_name;
~~~

VALIDATED và STATUS cần được xem cùng nhau. ENABLE NOVALIDATE khác ENABLE VALIDATE.

### 14.5. Kiểm tra dữ liệu

So sánh:
- Row count.
- Min/max primary key.
- Tổng hợp theo partition hoặc business group.
- Null count.
- Duplicate key.
- Checksum trên các cột nghiệp vụ.
- Foreign key orphan.
- Giá trị sau conversion.

Với bảng có DML liên tục, đối chiếu phải dùng một mốc nhất quán hoặc quy trình sync/validation thích hợp.

### 14.6. Statistics và execution plan

Sau move/redefinition, xem statistics và plan của SQL quan trọng. Có thể cần gather statistics theo chính sách:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

Không gather statistics tùy tiện ngay sau mọi DDL nếu auto stats hoặc quy trình release đã quản lý. Kiểm tra execution plan, buffer gets, elapsed time và bind distribution.

## 15. Runbook triển khai Online DDL/DBMS_REDEFINITION

### Trước khi chạy

1. Xác định schema/table và thay đổi đích.
2. Đọc datatype, constraint, index, trigger, partition, LOB và dependency.
3. Xác nhận edition, license và operation support trong Oracle 19c.
4. Kiểm tra transaction/lock dài và DML rate.
5. Kiểm tra tablespace, TEMP, UNDO, REDO, FRA và backup.
6. Tạo interim table hoặc script DDL đã review.
7. Chạy CAN_REDEF_TABLE nếu dùng DBMS_REDEFINITION.
8. Thử trên dữ liệu và workload tương đương.
9. Đo thời gian copy, sync và cutover.
10. Chuẩn bị abort/rollback/forward-fix và người phê duyệt.

### Trong khi chạy

1. Ghi change ID, session, module và thời điểm bắt đầu.
2. Theo dõi V$SESSION, V$LOCKED_OBJECT, DBA_DDL_LOCKS và wait event.
3. Theo dõi CPU, I/O, TEMP, UNDO, REDO và storage.
4. Theo dõi job/procedure progress và error view.
5. Chạy SYNC_INTERIM_TABLE khi phù hợp.
6. Chỉ FINISH khi dependent object và cutover readiness đã đạt.
7. Giới hạn lock timeout và theo dõi blocker.
8. Dừng/abort khi vượt ngưỡng đã định.

### Sau khi chạy

1. Xác nhận table metadata và object name.
2. Xác nhận index/constraint/trigger/grant.
3. Xác nhận row count và dữ liệu nghiệp vụ.
4. Kiểm tra invalid object và sequence.
5. Kiểm tra SQL plan và latency.
6. Dọn old/interim object sau khi xác nhận chính xác.
7. Thu thập statistics theo chính sách.
8. Lưu log, elapsed time, lock window và kết quả vào change record.

## 16. Lựa chọn phương án theo tình huống

| Nhu cầu | Phương án xem xét | Điểm cần kiểm tra |
| --- | --- | --- |
| Tạo B-tree index trên bảng đang ghi | CREATE INDEX ONLINE | Index type, edition, space, CPU/I/O |
| Rebuild index trong lúc DML | ALTER INDEX REBUILD ONLINE | Index/partition support, lock window |
| Di chuyển heap table | ALTER TABLE MOVE ONLINE | Table/LOB/partition restrictions, indexes |
| Thêm cột tương thích | ADD COLUMN, kiểm tra fast metadata operation | Default, NOT NULL, datatype, DDL lock |
| Thêm constraint khi dữ liệu cũ chưa sạch | ENABLE NOVALIDATE rồi VALIDATE | Constraint type, old data, validation cost |
| Đổi datatype/partition/column mapping phức tạp | DBMS_REDEFINITION | Eligibility, interim table, dependencies, space |
| Đổi tên cột trong rolling deployment | Expand-and-contract | App compatibility và dual-write |
| Thao tác không hỗ trợ ONLINE | Offline DDL trong maintenance window hoặc thiết kế lại | Downtime, backup, lock và rollback |

Không có một kỹ thuật online áp dụng cho mọi DDL. Chọn theo operation, object, edition, dependency và mức gián đoạn có thể chấp nhận.

## 17. Lỗi thường gặp và hướng xử lý

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-00054 | Không lấy được lock trong thời gian cho phép | Xác định blocker, DDL_LOCK_TIMEOUT, retry có kiểm soát |
| ORA-01450 | Key/index entry vượt giới hạn block | Xem key length, block size, index design |
| ORA-01408 | Cột đã có index tương đương | Kiểm tra index hiện hữu |
| ORA-01452 | Tạo unique index nhưng dữ liệu trùng | Tìm duplicate và xử lý dữ liệu |
| ORA-01502 | Index/partition unusable | Xác định nguyên nhân và rebuild/recover phù hợp |
| Lỗi redefine liên quan dependency | Điều kiện/dependency của redefinition không đáp ứng | Đọc lỗi gốc và DBA_REDEFINITION_ERRORS |
| FINISH_REDEF_TABLE chờ lâu | Transaction/blocker hoặc DML rate cao | Tìm blocker, sync lại, chọn cutover ít tải |
| Interim table thiếu object | COPY_TABLE_DEPENDENTS lỗi/bỏ qua | Xem DBA_REDEFINITION_ERRORS và tạo dependency đúng |
| Không đủ tablespace | Segment cũ và mới cùng tồn tại | Bổ sung space, dọn đúng đối tượng, lập lại kế hoạch |
| DML latency tăng | CPU/I/O/redo/undo tranh chấp | Giảm concurrency, điều chỉnh lịch/parallelism |
| SQL plan thay đổi | Statistics/index/access path đổi | So sánh plan, stats và SQL workload |

### 17.1. ORA-00054

Kiểm tra blocker trước khi tăng timeout. Có thể dùng:

~~~sql
SELECT sid,
       serial#,
       username,
       event,
       blocking_session,
       sql_id,
       module
FROM   v$session
WHERE  blocking_session IS NOT NULL;
~~~

Nếu transaction thuộc batch dài, phối hợp owner để kết thúc an toàn. Không kill session trước khi đánh giá rollback.

### 17.2. ORA-01452 khi tạo unique index

Tìm duplicate:

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count
FROM   app.orders
GROUP  BY customer_id
HAVING COUNT(*) > 1;
~~~

Giải quyết duplicate theo business rule rồi mới tạo unique index. Không xóa hàng trùng tùy tiện.

### 17.3. Redefinition errors

~~~sql
SELECT *
FROM   dba_redefinition_errors
WHERE  base_table_owner = 'APP'
AND    base_table_name = 'ORDERS';
~~~

Đọc DDL_TXT để xác định dependent object lỗi. Chỉ finish khi các object bắt buộc đã được xử lý.

## 18. Những hiểu nhầm thường gặp

**“ONLINE nghĩa là không có lock.”** Không. Operation vẫn có thể cần khóa metadata ngắn ở đầu/cuối hoặc chờ transaction.

**“Tất cả ALTER TABLE đều hỗ trợ ONLINE.”** Không. Chỉ một số operation/cú pháp/object được hỗ trợ.

**“DBMS_REDEFINITION không cần thêm dung lượng.”** Không. Bảng gốc và interim structure có thể cùng tồn tại, kèm index/LOB và redo/undo.

**“CAN_REDEF_TABLE thành công nghĩa toàn bộ migration chắc chắn thành công.”** Không. Nó kiểm tra eligibility, không thay thế kiểm tra space, mapping, dependency và workload.

**“Có thể bỏ qua lỗi COPY_TABLE_DEPENDENTS.”** Không. Thiếu index, trigger, constraint hoặc privilege có thể làm ứng dụng sai sau cutover.

**“FINISH_REDEF_TABLE không cần lock.”** Không. Bước cuối cần đồng bộ và chuyển đổi metadata, có thể chờ DML lock.

**“DDL_LOCK_TIMEOUT làm DDL chạy online.”** Không. Nó chỉ điều khiển thời gian chờ lock.

**“ENABLE NOVALIDATE có nghĩa dữ liệu cũ đã hợp lệ.”** Không. Dữ liệu cũ chưa được validate.

**“Move table online luôn giữ mọi index và dependency.”** Không nên giả định; kiểm tra trạng thái index, LOB và object liên quan sau operation.

**“DDL có thể rollback bằng ROLLBACK.”** Không. Nhiều DDL có implicit commit.

**“Nếu DDL thất bại thì không có thay đổi nào xảy ra.”** Không. Một số bước hoặc object phụ thuộc có thể đã được tạo/thay đổi trước khi lỗi.

**“Online DDL không ảnh hưởng execution plan.”** Không. Index, statistics, metadata và cursor invalidation có thể làm plan thay đổi.

## 19. Bài thực hành

Thực hiện trong schema test và dữ liệu có thể tái tạo. Các bài tạo/drop/alter object không chạy trên production nếu chưa có change approval.

### Bài 1 — Quan sát DML lock

Mở hai session. Session A update một hàng nhưng chưa commit; session B update cùng hàng. Quan sát wait event và blocking_session.

### Bài 2 — DDL chờ transaction

Giữ transaction trên bảng test rồi thử ALTER TABLE từ session khác. Quan sát ORA-00054 khi DDL_LOCK_TIMEOUT=0 và thử timeout có giới hạn.

### Bài 3 — Tạo index online

Tạo index trên bảng test bằng ONLINE trong khi session khác chạy DML. Ghi elapsed, latency và index status.

### Bài 4 — Rebuild index online

Rebuild index test bằng ONLINE. Theo dõi V$SESSION_LONGOPS, CPU/I/O và trạng thái sau hoàn tất.

### Bài 5 — MOVE TABLE ONLINE

Di chuyển bảng heap test sang tablespace khác. Kiểm tra segment, index, LOB và row count.

### Bài 6 — Thêm constraint NOVALIDATE

Tạo dữ liệu cũ có vi phạm, thêm constraint ENABLE NOVALIDATE. Thử DML mới vi phạm, sau đó sửa dữ liệu cũ và VALIDATE.

### Bài 7 — SET UNUSED

Đánh dấu một cột test SET UNUSED. Xác nhận cột không còn xuất hiện trong metadata thông thường; đo riêng bước DROP UNUSED COLUMNS.

### Bài 8 — CAN_REDEF_TABLE

Tạo bảng có primary key và chạy CAN_REDEF_TABLE với CONS_USE_PK. Ghi lại điều kiện thành công.

### Bài 9 — Redefinition đổi tên cột

Tạo interim table và dùng col_mapping để chuyển CREATED_AT thành ORDER_CREATED_AT. Xác minh dữ liệu sau finish.

### Bài 10 — COPY_TABLE_DEPENDENTS

Tạo index, trigger, constraint và grant trên bảng test. Chạy COPY_TABLE_DEPENDENTS và kiểm tra DBA_REDEFINITION_ERRORS.

### Bài 11 — Đồng bộ nhiều lần

Trong lúc redefinition, chạy DML ở session khác. Gọi SYNC_INTERIM_TABLE nhiều lần và quan sát thời gian sync.

### Bài 12 — Finish bị blocker

Giữ transaction trên bảng gốc trước finish. Quan sát finish chờ hoặc timeout; giải phóng lock an toàn rồi thử lại.

### Bài 13 — Abort redefinition

Bắt đầu redefinition test rồi ABORT_REDEF_TABLE. Xác nhận bảng gốc vẫn sử dụng được và kiểm tra object trung gian cần dọn.

### Bài 14 — Thiết kế expand-and-contract

Mô phỏng đổi tên cột cho ứng dụng có hai version cùng chạy. Thiết kế add, dual-write/backfill, verify, switch read và drop cột cũ.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_REDEFINITION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html): CAN_REDEF_TABLE, START_REDEF_TABLE, COPY_TABLE_DEPENDENTS, SYNC_INTERIM_TABLE, FINISH_REDEF_TABLE và ABORT_REDEF_TABLE.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): các dạng thay đổi bảng và giới hạn cú pháp.
- [Oracle Database 19c SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): tạo index và ONLINE clause.
- [Oracle Database 19c SQL Language Reference — ALTER INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-INDEX.html): rebuild và maintenance index.
- [Oracle Database 19c Database Reference — DDL_LOCK_TIMEOUT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DDL_LOCK_TIMEOUT.html): thời gian chờ DDL lock.
- [Oracle Database 19c Database Reference — V$LOCKED_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html): object lock đang giữ.
- [Oracle Database 19c Database Reference — DBA_DDL_LOCKS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DDL_LOCKS.html): DDL lock metadata.
- [Oracle Database 19c Database Reference — DBA_REDEFINITION_ERRORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_REDEFINITION_ERRORS.html): lỗi khi copy dependent object trong redefinition.
- [Oracle Database VLDB and Partitioning Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): online table/index maintenance và partition operations.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): edition và điều kiện sử dụng các tính năng.

Online DDL giúp một số thay đổi cấu trúc tiếp tục phục vụ DML trong phần lớn thời gian, nhưng vẫn có giới hạn theo operation, object, edition và tài nguyên; các bước metadata có thể cần lock ngắn. DBMS_REDEFINITION phù hợp với thay đổi bảng phức tạp hơn khi cần copy dữ liệu sang interim table, đồng bộ DML và cutover có kiểm soát. **Hãy kiểm tra eligibility, dependency, license, dung lượng và blocker trước khi bắt đầu; đo riêng lock window cuối, xác minh mọi object sau cutover và luôn có kế hoạch abort hoặc forward-fix.**
