# Đánh giá tác động trước khi kill session, khởi động lại hoặc đổi tham số trong Oracle Database

Trong sự cố Oracle Database, các hành động như kết thúc một session, restart instance hoặc thay đổi system parameter có thể giải quyết triệu chứng nhanh, nhưng cũng có thể làm gián đoạn transaction hợp lệ, tạo rollback kéo dài, ngắt hàng loạt kết nối hoặc thay đổi hành vi toàn database. Trước khi thực hiện, DBA cần xác định chính xác đối tượng bị tác động, nguyên nhân, phạm vi ảnh hưởng và cách khôi phục nếu kết quả không như dự kiến.

Ba nhóm hành động có phạm vi khác nhau:

- **Kill/disconnect session:** tác động tới một session cụ thể và transaction của session đó. Transaction chưa commit có thể phải rollback; lock có thể chưa được giải phóng ngay.
- **Restart:** có thể chỉ restart service, một instance RAC, một PDB hoặc toàn database. Phạm vi quyết định số session bị ngắt, workload phải reconnect và khả năng failover.
- **Đổi parameter:** có thể chỉ ảnh hưởng session hiện tại, các session mới, một instance, mọi instance hoặc một PDB; hiệu lực có thể tức thời hoặc cần restart.

Không nên dùng một hành động có phạm vi rộng để xử lý một triệu chứng chưa được xác định. Hãy thu thập bằng chứng trước, chọn thay đổi nhỏ nhất đáp ứng mục tiêu, theo dõi trong khi thực hiện và xác minh sau đó.

Bài học lấy Oracle Database 19c làm mốc, bao gồm single-instance, RAC và multitenant. Các ví dụ giả định người thực hiện có quyền DBA phù hợp và đã được phê duyệt theo quy trình vận hành của hệ thống.

## 1. Khung đánh giá tác động trước khi can thiệp

### 1.1. Xác định triệu chứng và mục tiêu

Trước khi chạy lệnh, mô tả sự cố bằng dữ kiện quan sát được:

- Session nào đang chờ hoặc chặn session khác?
- SQL nào tiêu thụ CPU, I/O, TEMP hoặc undo bất thường?
- Database, instance, service hay chỉ một PDB không đáp ứng?
- Lỗi bắt đầu lúc nào và ảnh hưởng tới ứng dụng nào?
- Có transaction đang mở hoặc giao dịch phân tán không?
- Triệu chứng xuất hiện trên một instance hay tất cả instance?
- Có thay đổi gần đây về deployment, workload, network hoặc parameter không?

Sau đó xác định kết quả mong muốn, ví dụ giải phóng một lock, dừng một truy vấn runaway, chuyển service sang instance khỏe, áp dụng một parameter mới hoặc khôi phục khả năng phục vụ.

Không dùng các mô tả chung như “database bị treo” làm căn cứ restart. Hãy xác định session, wait event, service, instance và phạm vi lỗi trước.

### 1.2. Xác định blast radius

Blast radius là phạm vi người dùng, transaction và thành phần kỹ thuật có thể bị ảnh hưởng:

| Hành động | Phạm vi thường gặp | Tác động cần dự kiến |
| --- | --- | --- |
| Cancel một SQL statement | Một statement/session | Statement dừng; transaction có thể vẫn mở |
| Kill một session | Một session | Connection mất; transaction chưa commit rollback |
| Disconnect một session | Một session | Session bị ngắt theo chế độ chỉ định |
| Stop/start service | Các session dùng service đó | Connection bị ngắt hoặc chuyển hướng tùy cấu hình |
| Restart một RAC instance | Mọi session trên instance | Session mất; service có thể failover |
| Restart một PDB | Session và workload thuộc PDB | PDB đóng/mở; CDB khác vẫn có thể hoạt động |
| Restart database | Toàn database và các service phụ thuộc | Mọi session bị ngắt; recovery/startup cần thời gian |
| Đổi session parameter | Session hiện tại | Chỉ session đó chịu tác động |
| Đổi system parameter dynamic | Instance/PDB/session scope theo tham số | Hành vi workload có thể đổi ngay hoặc với session mới |
| Đổi static parameter trong SPFILE | Sau lần restart phù hợp | Cần downtime/restart theo phạm vi áp dụng |

Phạm vi thực tế phụ thuộc cấu hình RAC, service, PDB, connection pool, Data Guard và loại parameter. Không mặc định rằng restart một instance sẽ tự động chuyển mọi client sang instance khác.

### 1.3. Thu thập trạng thái trước khi thay đổi

Lưu lại tối thiểu:
- Thời điểm và incident/change ID.
- Database name, DB unique name, role, open mode.
- Instance, service và PDB liên quan.
- Session ID, serial number, instance ID nếu xử lý session.
- SQL ID, module, action, machine, client identifier.
- Transaction start time, undo đã dùng và lock đang giữ.
- Wait event, blocker chain và session bị chặn.
- Parameter hiện tại, giá trị trong SPFILE và scope.
- CPU, memory, I/O, TEMP, UNDO, REDO, FRA và application latency.
- Alert log và error stack liên quan.

Lưu kết quả trước khi kill, restart hoặc đổi parameter. Sau thao tác, so sánh lại cùng các chỉ số để xác định thay đổi có giải quyết đúng nguyên nhân không.

### 1.4. Phân biệt khắc phục nguyên nhân và giảm triệu chứng

Ví dụ:
- Kill session đang chặn DDL có thể giải phóng lock, nhưng không sửa transaction hoặc logic ứng dụng tạo blocker.
- Restart instance có thể làm hết tình trạng session treo, nhưng không sửa SQL gây quá tải hoặc lỗi cấu hình.
- Tăng SGA/PGA có thể giảm một số lỗi thiếu bộ nhớ, nhưng có thể làm hệ điều hành thiếu RAM hoặc gây áp lực lên các instance khác.
- Tăng process/session limit có thể cho phép thêm kết nối, nhưng không sửa connection leak hoặc pool mở quá nhiều session.

Trước khi hành động, ghi rõ giả thuyết nguyên nhân và bằng chứng nào sẽ xác nhận giả thuyết đó.

## 2. Xác định database, instance, service và role

### 2.1. Kiểm tra database context

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       log_mode,
       flashback_on
FROM   v$database;
~~~

Các trường này giúp xác định database đang là primary hay standby, đang mở ở chế độ nào và có ARCHIVELOG/Flashback Database ra sao. Không restart hoặc thay đổi cấu hình trước khi biết đang thao tác trên primary, physical standby hay môi trường khác.

### 2.2. Kiểm tra instance

~~~sql
SELECT instance_name,
       host_name,
       instance_number,
       status,
       database_status,
       startup_time
FROM   v$instance;
~~~

Trong RAC, dùng GV$INSTANCE để xem tất cả instance:

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM   gv$instance
ORDER  BY inst_id;
~~~

Đừng nhầm tên instance với DB_UNIQUE_NAME hoặc service name. Một database RAC có nhiều instance nhưng có thể cung cấp cùng service qua nhiều instance.

### 2.3. Kiểm tra service

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
FROM   gv$active_services
ORDER  BY inst_id, name;
~~~

Đối chiếu service đang hoạt động với cấu hình Clusterware và endpoint ứng dụng sử dụng. Một service không hoạt động trên instance dự kiến có thể khiến kết nối thất bại hoặc bị định tuyến sang instance khác.

### 2.4. Kiểm tra PDB

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM   v$pdbs
ORDER  BY con_id;
~~~

Nếu lỗi chỉ xảy ra trong một PDB, không mặc định cần restart CDB. Kiểm tra service, PDB open mode, session và parameter có thể thay đổi ở PDB scope.

### 2.5. Kiểm tra vai trò Data Guard

~~~sql
SELECT database_role,
       open_mode,
       protection_mode,
       switchover_status
FROM   v$database;
~~~

Trước khi restart primary/standby hoặc thay đổi parameter liên quan redo, xác định Data Guard broker, transport/apply lag và trạng thái peer. Một thao tác trên standby không nên vô tình làm gián đoạn primary; thao tác trên primary cần đánh giá failover/standby impact.

## 3. Đánh giá session trước khi kill

### 3.1. Xác định đúng session

Trong single-instance, SID có thể đủ để bắt đầu điều tra nhưng không đủ an toàn để nhận diện session lâu dài. SID có thể được tái sử dụng sau khi session kết thúc. Kết hợp SID với SERIAL#.

Trong RAC, cần thêm INST_ID. Một session được xác định bởi ít nhất:
- INST_ID.
- SID.
- SERIAL#.

Không lấy SID từ màn hình giám sát rồi kill sau một khoảng thời gian dài mà không xác minh lại; session có thể đã kết thúc và SID được dùng lại.

### 3.2. Xem session người dùng và SQL đang chạy

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       type,
       service_name,
       module,
       action,
       client_identifier,
       machine,
       program,
       sql_id,
       prev_sql_id,
       sql_exec_start,
       event,
       wait_class,
       seconds_in_wait,
       blocking_instance,
       blocking_session,
       logon_time,
       last_call_et
FROM   gv$session
WHERE  type = 'USER'
ORDER  BY inst_id, sid;
~~~

Các thông tin cần diễn giải:
- USERNAME và SERVICE_NAME: tài khoản và service.
- MODULE/ACTION/CLIENT_IDENTIFIER: ứng dụng hoặc nghiệp vụ nếu được thiết lập.
- MACHINE/PROGRAM: client hoặc process nguồn.
- SQL_ID/PREV_SQL_ID: SQL hiện tại/gần nhất.
- EVENT/WAIT_CLASS: session đang làm gì hoặc chờ gì.
- BLOCKING_INSTANCE/BLOCKING_SESSION: blocker trực tiếp nếu Oracle xác định được.
- LOGON_TIME: thời điểm mở session.
- LAST_CALL_ET: thời gian từ lần call gần nhất tùy trạng thái session; không phải lúc nào cũng là thời gian transaction.

Không kết luận session “idle vô hại” chỉ từ STATUS='INACTIVE'. Session inactive vẫn có thể giữ transaction chưa commit và lock.

### 3.3. Tìm blocker và waiter

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       blocking_instance,
       blocking_session,
       final_blocking_instance,
       final_blocking_session,
       sql_id,
       module,
       machine
FROM   gv$session
WHERE  blocking_session IS NOT NULL
   OR  final_blocking_session IS NOT NULL
ORDER  BY inst_id, sid;
~~~

Final blocker giúp nhìn sâu hơn trong chuỗi blocking. Nếu một session chặn nhiều session khác, kill nhầm waiter thay vì blocker có thể không giải quyết được hàng đợi.

Đánh giá toàn bộ chuỗi:
1. Session nào đang chờ?
2. Session nào đang chặn trực tiếp?
3. Session nào là blocker cuối cùng?
4. Blocker có transaction nghiệp vụ hợp lệ không?
5. Có nhiều tầng blocker hoặc lock cycle không?

### 3.4. Xem object bị khóa

~~~sql
SELECT lo.inst_id,
       lo.session_id AS sid,
       s.serial#,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM   gv$locked_object lo
JOIN   dba_objects o
       ON o.object_id = lo.object_id
LEFT JOIN gv$session s
       ON s.inst_id = lo.inst_id
      AND s.sid = lo.session_id
ORDER  BY lo.inst_id, o.owner, o.object_name;
~~~

LOCKED_MODE là mã chế độ khóa. Tra Oracle Database Reference để diễn giải mode. Một session có thể giữ nhiều lock trên nhiều object; xác định object liên quan tới sự cố trước khi kết luận.

### 3.5. Xem lock enqueue

~~~sql
SELECT l.inst_id,
       s.sid,
       s.serial#,
       s.username,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block,
       s.event,
       s.sql_id,
       s.module
FROM   gv$lock l
JOIN   gv$session s
       ON s.inst_id = l.inst_id
      AND s.sid = l.sid
WHERE  l.request > 0
   OR  l.block = 1
ORDER  BY l.inst_id, l.block DESC, l.request DESC;
~~~

ID1/ID2 phụ thuộc loại enqueue. Không coi chúng luôn là OBJECT_ID. Với TX, TM và các loại lock khác, cần giải mã theo tài liệu Oracle và ngữ cảnh.

### 3.6. Kiểm tra transaction đang mở

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.status,
       s.module,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec,
       t.xidusn,
       t.xidslot,
       t.xidsqn
FROM   gv$session s
JOIN   gv$transaction t
       ON t.inst_id = s.inst_id
      AND t.addr = s.taddr
ORDER  BY t.start_time;
~~~

USED_UBLK và USED_UREC cho biết lượng undo transaction đã dùng theo view tại thời điểm truy vấn. Chúng giúp ước lượng quy mô rollback nhưng không dự đoán chính xác thời gian rollback. Rollback phụ thuộc lượng thay đổi, I/O, contention, redo và trạng thái recovery.

### 3.7. Transaction rollback đang chạy

Sau khi session bị kết thúc, rollback có thể tiếp tục trong nền. Có thể xem tiến độ fast-start transaction recovery khi view có dữ liệu:

~~~sql
SELECT xid,
       state,
       undoblocksdone,
       undoblockstotal,
       ROUND(
           100 * undoblocksdone / NULLIF(undoblockstotal, 0),
           2
       ) AS percent_done
FROM   v$fast_start_transactions;
~~~

Các cột và trạng thái cần được diễn giải theo Oracle Database Reference. Không phải mọi rollback session đều xuất hiện theo cùng một cách trong view này. Lock có thể còn tồn tại trong khi rollback chưa hoàn tất.

### 3.8. Kiểm tra distributed transaction

Nếu session liên quan database link hoặc transaction phân tán, kiểm tra trạng thái in-doubt trước khi kill/restart:

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       advice,
       fail_time
FROM   dba_2pc_pending;
~~~

Không tự force commit hoặc force rollback distributed transaction chỉ vì một session đang chờ. Cần xác định coordinator, peer database và quy trình xử lý in-doubt transaction.

## 4. Chọn cách xử lý session

### 4.1. Ưu tiên dừng đúng statement nếu phù hợp

Nếu chỉ một SQL statement runaway nhưng session còn cần được giữ để ứng dụng tiếp tục hoạt động, hãy cân nhắc cơ chế cancel SQL được hỗ trợ bởi release/driver và runbook. Dừng statement không nhất thiết kết thúc session.

Sau khi cancel, xác minh:
- Statement đã dừng.
- Transaction còn mở hay đã rollback.
- Session có còn giữ lock không.
- Ứng dụng có thể tiếp tục hoặc cần rollback transaction.
- Connection pool có đánh dấu connection lỗi không.

Đừng giả định cancel statement tự động rollback toàn transaction.

### 4.2. Kill session bằng ALTER SYSTEM

Single-instance:

~~~sql
ALTER SYSTEM KILL SESSION '123,4567' IMMEDIATE;
~~~

RAC:

~~~sql
ALTER SYSTEM KILL SESSION '123,4567,@2' IMMEDIATE;
~~~

Trong ví dụ RAC, 123 là SID, 4567 là SERIAL# và 2 là INST_ID. Thay các giá trị bằng kết quả vừa xác minh từ GV$SESSION. Không dùng ví dụ nguyên trạng trên hệ thống thật.

IMMEDIATE yêu cầu Oracle kết thúc session ngay theo cơ chế quản lý session. Nếu session không thể kết thúc ngay, Oracle có thể đánh dấu session để kill và trả ORA-00031. Việc cleanup/rollback có thể tiếp tục sau đó.

### 4.3. DISCONNECT SESSION

Oracle cũng hỗ trợ:

~~~sql
ALTER SYSTEM DISCONNECT SESSION '123,4567' POST_TRANSACTION;
~~~

Hoặc:

~~~sql
ALTER SYSTEM DISCONNECT SESSION '123,4567' IMMEDIATE;
~~~

- POST_TRANSACTION chờ transaction hiện tại hoàn tất rồi mới disconnect.
- IMMEDIATE ngắt session ngay theo cơ chế disconnect.

DISCONNECT SESSION thường được dùng để chủ động ngắt một session; chọn mode theo mục tiêu và khả năng chờ transaction. Trong RAC, thêm INST_ID theo cú pháp được hỗ trợ.

### 4.4. KILL SESSION không đồng nghĩa process OS biến mất ngay

Oracle quản lý session, server process và rollback. Sau lệnh kill:
- Session có thể hiện trạng thái KILLED trong một khoảng thời gian.
- Server process có thể cần cleanup.
- Transaction chưa commit cần rollback.
- Lock có thể còn được giữ tới khi rollback/cleanup giải phóng.
- Client nhận lỗi connection/session terminated.

Không thấy session biến mất ngay không có nghĩa lệnh không có tác dụng. Kiểm tra lại GV$SESSION, transaction và lock sau một khoảng theo dõi hợp lý.

### 4.5. ORA-00031: session marked for kill

ORA-00031 cho biết session đã được đánh dấu để kill nhưng chưa kết thúc tức thời. Nguyên nhân có thể là session đang ở một trạng thái cần cleanup hoặc rollback.

Không lặp lệnh kill liên tục. Theo dõi:
- Session còn tồn tại không.
- Transaction rollback có tiến triển không.
- Wait event và process state.
- Lock còn giữ trên object nào.
- Có distributed transaction hay external call không.

Nếu cleanup bị kẹt kéo dài, thu thập incident evidence và xử lý theo Oracle Support/DBA runbook thay vì kill OS process ngay.

### 4.6. Tránh kill background process

Không kill background process như PMON, SMON, DBWn, LGWR, CKPT, ARCn, MMON hoặc process nội bộ chỉ vì thấy chúng xuất hiện trong danh sách session/process. Các process này có vai trò duy trì database.

Điều tra session người dùng bằng TYPE='USER', module, program, process và tài liệu Oracle. Nếu nghi ngờ background process lỗi, dùng alert log, trace file và Oracle Support process thay vì kill trực tiếp.

### 4.7. Kill OS process là phương án cuối

Không dùng taskkill, kill -9 hoặc terminate process từ hệ điều hành để thay cho ALTER SYSTEM KILL SESSION. Việc kết thúc process bên ngoài có thể buộc Oracle phát hiện process chết và thực hiện recovery/rollback; nếu chọn nhầm process, tác động có thể lớn hơn một session.

Chỉ dùng biện pháp OS-level khi DBA/Oracle Support runbook yêu cầu, đã xác minh PID/SPID và instance, có quyền phù hợp và đã đánh giá recovery impact.

## 5. Đánh giá transaction và hậu quả khi kill

### 5.1. Transaction chưa commit sẽ không được giữ nguyên

Kill session không phải thao tác “chỉ giải phóng lock”. Nếu session có transaction chưa commit, Oracle phải rollback thay đổi chưa commit để bảo đảm atomicity.

Tác động có thể gồm:
- Hàng đã insert bị loại bỏ.
- Update được hoàn tác.
- Delete được phục hồi.
- Lock giữ trong thời gian rollback.
- Undo/redo và I/O tiếp tục được sử dụng.
- Ứng dụng nhận lỗi và có thể cần gửi lại request theo chính sách.

Nếu transaction có hàng triệu thay đổi, rollback có thể lâu hơn thời gian câu SQL ban đầu chạy.

### 5.2. Đánh giá quy mô rollback

Dùng:
- Transaction start time.
- USED_UBLK/USED_UREC.
- Số hàng và object có liên quan.
- Wait event của session.
- Redo/undo generation.
- Fast-start transaction recovery nếu có.

Không dùng USED_UBLK để dự đoán thời gian tuyệt đối. Hai transaction có cùng undo blocks vẫn có thể rollback khác nhau do storage và contention.

### 5.3. Session inactive nhưng có transaction

Một session STATUS='INACTIVE' có thể đã thực hiện DML rồi để quên COMMIT/ROLLBACK. Session không chạy SQL tại thời điểm quan sát nhưng vẫn giữ transaction và lock.

Đây là trường hợp cần liên hệ owner/ứng dụng trước khi kill. Có thể transaction là một bước nghiệp vụ nhiều phút hoặc một thao tác cần commit có kiểm soát.

### 5.4. Connection pool có thể tạo lại session

Khi kill một session thuộc pool:
- Pool có thể loại connection hỏng.
- Ứng dụng có thể mở connection mới.
- Request đang xử lý có thể lỗi.
- Retry logic có thể chạy lại thao tác.
- Nếu commit outcome không rõ, thao tác có nguy cơ bị gửi lặp.

Đánh giá retry/idempotency trước khi kill session ứng dụng. Giải phóng blocker nhưng không xử lý pool leak hoặc retry storm có thể khiến session mới nhanh chóng tạo ra cùng vấn đề.

### 5.5. Các câu hỏi trước khi kill blocker

- Session có phải final blocker không?
- Có thể yêu cầu ứng dụng commit/rollback đúng nghiệp vụ không?
- Transaction đã chạy bao lâu và dùng bao nhiêu undo?
- Có batch hoặc ETL quan trọng không?
- Session có liên quan distributed transaction không?
- Các session bị chặn có bao nhiêu và thuộc service nào?
- Kill có làm retry storm hoặc duplicate request không?
- Có phương án cancel statement hoặc giảm workload ít tác động hơn không?

Nếu chưa xác định được owner hoặc transaction, ưu tiên thu thập thông tin và phối hợp thay vì kill.

## 6. Restart: xác định đúng phạm vi

### 6.1. Restart service

Service là điểm kết nối logic cho workload. Trong RAC, service có thể chạy trên một hoặc nhiều instance theo cấu hình preferred/available instances.

Restart hoặc relocate service có thể ảnh hưởng các session dùng service đó mà không cần restart toàn database. Tuy nhiên, session đang kết nối không tự động chuyển sang service khác trừ khi client/driver/connection pool và cấu hình HA hỗ trợ.

Trước khi stop service:
- Xác định service có bao nhiêu client/session.
- Kiểm tra preferred/available instance.
- Xem service có được dùng bởi batch, scheduler hoặc ứng dụng khác không.
- Xác định cách client reconnect.
- Kiểm tra FAN/ONS/Application Continuity nếu kiến trúc dùng.
- Drain workload theo quy trình.

### 6.2. Restart một RAC instance

Restart một instance có thể phù hợp khi lỗi chỉ nằm trên một node hoặc cần bảo trì từng instance. Tác động:
- Tất cả session trên instance bị ngắt.
- Transaction chưa commit cần rollback.
- Service có thể được chuyển sang instance khác nếu cấu hình cho phép.
- Instance còn lại có thể phải nhận thêm tải.
- Cache, buffer và workload cần warm up lại.
- RAC interconnect/service relocation có thể ảnh hưởng latency.

Kiểm tra capacity của instance còn lại trước khi dừng một node. Nếu hai node đều gần hết CPU/memory, chuyển tải có thể làm cả cluster mất khả năng phục vụ.

### 6.3. Restart PDB

Nếu lỗi chỉ thuộc một PDB, có thể cân nhắc đóng/mở PDB theo runbook:

~~~sql
ALTER PLUGGABLE DATABASE apppdb CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE apppdb OPEN;
~~~

Câu lệnh cần chạy ở container phù hợp và với quyền thích hợp. CLOSE IMMEDIATE ngắt các session của PDB; transaction chưa commit bị xử lý theo quá trình đóng. Các PDB khác trong CDB có thể tiếp tục hoạt động, nhưng vẫn chia sẻ instance resources.

Trước khi đóng PDB, xác minh service, application pool, scheduler job, local user và Data Guard/PDB state. Không dùng restart PDB nếu lỗi nằm ở CDB root hoặc instance.

### 6.4. Restart toàn database

Restart database ảnh hưởng rộng hơn:
- Mọi session bị ngắt.
- Transaction chưa commit bị rollback hoặc recovery khi startup.
- Service/listener registration cần hoạt động lại.
- Scheduler job có thể bị gián đoạn.
- Connection pool phải reconnect.
- Data Guard/replication/CDC có thể bị ảnh hưởng.
- Startup có thể cần instance recovery.
- Ứng dụng cần smoke test trước khi nhận traffic.

Chỉ restart toàn database khi đã xác định nguyên nhân hoặc có bằng chứng instance/database state cần khởi động lại.

### 6.5. Restart host

Restart máy chủ tác động cả database instance, listener, agent, storage path, monitoring, backup và các service khác cùng host. Đây là phạm vi lớn nhất trong các lựa chọn nêu trên.

Trước khi restart host, kiểm tra:
- Có nhiều Oracle instance cùng host không.
- Có ASM hoặc Grid Infrastructure service dùng chung không.
- Có listener/SCAN/local listener không.
- Có application agent, backup agent hoặc monitoring process không.
- RAC node còn lại có đủ capacity không.
- Data Guard/standby có sẵn sàng không.
- Storage/network path có phụ thuộc host không.

Không dùng reboot host như cách xử lý một session hoặc một SQL statement.

## 7. Các kiểu SHUTDOWN và mức tác động

### 7.1. SHUTDOWN NORMAL

~~~sql
SHUTDOWN NORMAL;
~~~

Oracle chờ người dùng tự disconnect trước khi đóng database. Nếu còn session đăng nhập, lệnh có thể chờ lâu. Phù hợp với môi trường có thể chủ động đóng ứng dụng và chờ mọi người dùng rời đi.

### 7.2. SHUTDOWN TRANSACTIONAL

~~~sql
SHUTDOWN TRANSACTIONAL;
~~~

Oracle ngăn transaction mới bắt đầu, chờ transaction hiện tại hoàn tất rồi mới disconnect session và đóng database. Cách này bảo vệ transaction đang chạy tốt hơn nhưng có thể chờ lâu nếu transaction không kết thúc.

### 7.3. SHUTDOWN IMMEDIATE

~~~sql
SHUTDOWN IMMEDIATE;
~~~

Oracle không chờ người dùng tự disconnect. Các session bị ngắt và transaction chưa commit được rollback; database đóng theo quy trình nhất quán. Đây thường là lựa chọn vận hành khi cần shutdown có kiểm soát nhưng không thể chờ tất cả client tự rời đi.

Thời gian shutdown có thể kéo dài do rollback hoặc I/O. Không kết luận database treo chỉ vì lệnh chưa trả về ngay.

### 7.4. SHUTDOWN ABORT

~~~sql
SHUTDOWN ABORT;
~~~

ABORT dừng instance ngay mà không thực hiện shutdown clean như IMMEDIATE. Khi startup lại, Oracle thực hiện instance/crash recovery dựa trên redo và trạng thái cần phục hồi.

Chỉ dùng khi:
- Các phương án shutdown có kiểm soát không thể hoàn tất.
- Có sự cố nghiêm trọng cần dừng instance.
- DBA hiểu thời gian và tác động instance recovery.
- Runbook/Oracle Support hướng dẫn hoặc có quyết định incident commander.

Không dùng ABORT như cách shutdown nhanh thường ngày. Nó không sửa nguyên nhân lỗi và có thể kéo dài thời gian database sẵn sàng trở lại.

### 7.5. So sánh shutdown mode

| Mode | Chờ user disconnect | Chờ transaction | Ngắt session | Recovery khi startup |
| --- | --- | --- | --- | --- |
| NORMAL | Có | Gián tiếp vì chờ user | Không chủ động ngắt | Shutdown clean |
| TRANSACTIONAL | Không chờ user tự disconnect | Có | Sau khi transaction hoàn tất | Shutdown clean |
| IMMEDIATE | Không | Không chờ transaction commit; rollback thay đổi chưa commit | Có | Shutdown clean |
| ABORT | Không | Không chờ rollback hoàn tất trước khi dừng | Có | Instance recovery cần chạy khi startup |

Các mode có semantics riêng theo Oracle SQL*Plus/Admin Guide. Luôn xem trạng thái alert log và tiến trình shutdown thay vì chỉ dựa vào client đã mất kết nối.

## 8. Restart có kiểm soát trong RAC và Grid Infrastructure

### 8.1. Ưu tiên SRVCTL cho tài nguyên Clusterware quản lý

Với database/service được Grid Infrastructure quản lý, dùng SRVCTL theo runbook để stop/start đúng resource. Ví dụ minh họa:

~~~bash
srvctl status database -db <db_unique_name>
srvctl status instance -db <db_unique_name> -instance <instance_name>
srvctl status service -db <db_unique_name>
~~~

Dừng một instance:

~~~bash
srvctl stop instance -db <db_unique_name> -instance <instance_name> -stopoption immediate
~~~

Khởi động lại instance:

~~~bash
srvctl start instance -db <db_unique_name> -instance <instance_name>
~~~

Cú pháp và tùy chọn có thể thay đổi theo Grid Infrastructure release/RU. Kiểm tra trợ giúp SRVCTL và Oracle Clusterware Administration Guide của môi trường đang chạy.

### 8.2. Kiểm tra service trước và sau

Trước khi stop instance:
- Xem service đang chạy ở đâu.
- Xác nhận service có available instance.
- Kiểm tra client failover/connection pool behavior.
- Đảm bảo node còn lại đủ capacity.

Sau khi start:
- Xác nhận instance OPEN.
- Xác nhận service chạy trên instance mong muốn.
- Kiểm tra listener registration.
- Kiểm tra session distribution.
- Kiểm tra application health và error rate.

### 8.3. Không restart nhiều instance đồng thời tùy tiện

Trong RAC, restart đồng thời nhiều instance có thể làm database mất toàn bộ khả năng phục vụ. Nếu mục tiêu là bảo trì rolling, thực hiện tuần tự:
1. Chọn instance.
2. Drain/relocate service.
3. Xác nhận workload đã chuyển.
4. Stop instance.
5. Bảo trì/start instance.
6. Xác nhận instance/service khỏe.
7. Chuyển sang instance tiếp theo.

Chỉ dùng rolling procedure được hỗ trợ cho patch/operation cụ thể; không tự suy ra rằng mọi thay đổi đều có thể rolling.

### 8.4. Listener và service không giống database

Listener có thể restart mà database instance vẫn chạy; database service có thể cần đăng ký lại. Nếu ứng dụng không kết nối được, kiểm tra listener, service registration và database state riêng biệt trước khi restart toàn database.

## 9. Restart trong Data Guard và hệ thống nhiều tầng

### 9.1. Primary và standby

Trước khi restart:
- Xác định role.
- Kiểm tra transport lag/apply lag.
- Kiểm tra redo destination và broker state.
- Xác định có cần switchover/failover hay chỉ restart.
- Xác nhận standby có đủ khả năng tiếp nhận workload nếu kế hoạch yêu cầu.

Không restart cả primary và standby cùng lúc nếu không có kế hoạch recovery/DR được phê duyệt.

### 9.2. Data Guard Broker

Nếu dùng broker, kiểm tra trạng thái configuration/database bằng DGMGRL theo runbook. Không tắt broker hoặc thay đổi role thủ công chỉ để làm hết cảnh báo mà chưa xác định trạng thái redo transport/apply.

Sau restart, xác minh broker configuration, transport, apply và role transition status.

### 9.3. Downstream systems

Restart database có thể tác động:
- GoldenGate/CDC.
- ETL và data warehouse.
- Database link.
- Message consumer/outbox poller.
- Scheduler/external job.
- Backup/monitoring.
- Application connection pools.

Ghi nhận vị trí checkpoint và khả năng replay của downstream. Database mở lại không đồng nghĩa toàn bộ pipeline đã đồng bộ.

## 10. Đổi parameter: xác định scope và hiệu lực

### 10.1. Session parameter

`ALTER SESSION SET` chỉ thay đổi session hiện tại:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
~~~

Thích hợp cho cấu hình mang tính session như NLS hoặc một số optimizer/session settings được hỗ trợ. Không ảnh hưởng session khác.

Trong connection pool, session có thể được tái sử dụng. Nếu thay session parameter, phải reset trước khi trả connection hoặc cấu hình initialization/reset hook.

### 10.2. System parameter

`ALTER SYSTEM SET` thay đổi tham số ở phạm vi system/instance theo semantics của tham số và cấu hình RAC/PDB. Không dùng câu lệnh này khi mục tiêu chỉ là thử nghiệm trên một session.

Ví dụ dạng tổng quát:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

Giá trị 500 chỉ là ví dụ cú pháp, không phải khuyến nghị. Xác định mức phù hợp bằng số liệu workload và giới hạn ứng dụng.

### 10.3. SCOPE=MEMORY

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = MEMORY;
~~~

Thay đổi giá trị trong memory của instance theo phạm vi áp dụng, không ghi vào SPFILE. Sau restart, giá trị sẽ quay về cấu hình persistent trước đó.

Dùng khi cần thử một giá trị dynamic có kiểm soát và đã có kế hoạch rollback/đánh giá. Không dùng MEMORY cho static parameter không thể đổi trong runtime.

### 10.4. SCOPE=SPFILE

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = SPFILE;
~~~

Ghi giá trị vào SPFILE để áp dụng khi instance khởi động lại; không thay đổi memory hiện tại. Phù hợp với parameter tĩnh cần restart hoặc khi muốn lên lịch thay đổi ở lần khởi động tiếp theo.

Nếu database khởi động từ PFILE, không thể ghi SPFILE theo cách này; cần quản lý PFILE theo quy trình.

### 10.5. SCOPE=BOTH

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = BOTH;
~~~

Ghi vào SPFILE và áp dụng vào memory nếu parameter cho phép thay đổi tức thời. Đây là cách phổ biến cho dynamic parameter khi muốn thay đổi có hiệu lực và tồn tại qua restart.

Không mặc định mọi parameter đều hỗ trợ BOTH. Kiểm tra ISSYS_MODIFIABLE và thông báo lỗi của Oracle.

### 10.6. Dynamic, deferred và static

V$PARAMETER có thông tin ISSYS_MODIFIABLE:
- IMMEDIATE: có thể thay đổi tức thời ở system scope theo hỗ trợ của parameter.
- DEFERRED: thay đổi có hiệu lực với session mới theo semantics của parameter.
- FALSE: không thể thay đổi động ở system scope; thường cần restart để áp dụng.

Ngoài ra, ISSES_MODIFIABLE cho biết có thể thay đổi ở session scope; ISPDB_MODIFIABLE cho biết khả năng thay đổi ở PDB scope. Kiểm tra đúng cột và tài liệu cho parameter cụ thể.

### 10.7. Tham số static không đổi được ngay

Nếu ISSYS_MODIFIABLE='FALSE', câu ALTER SYSTEM SET ... SCOPE=BOTH có thể lỗi ORA-02095 hoặc lỗi liên quan. Thường cần ghi SPFILE rồi lên lịch restart:

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = SPFILE;
~~~

Không lặp câu lệnh với SCOPE=MEMORY khi Oracle đã báo parameter không thể sửa động.

## 11. Kiểm tra giá trị parameter trước khi đổi

### 11.1. Giá trị runtime

~~~sql
SELECT inst_id,
       name,
       value,
       isdefault,
       ismodified,
       isses_modifiable,
       issys_modifiable,
       ispdb_modifiable
FROM   gv$parameter
WHERE  name IN (
           'open_cursors',
           'processes',
           'sessions',
           'sga_target',
           'pga_aggregate_target',
           'optimizer_mode'
       )
ORDER  BY name, inst_id;
~~~

GV$PARAMETER cho biết giá trị hiện tại theo instance. Một số tham số có thể khác nhau giữa các instance trong RAC.

### 11.2. Giá trị trong SPFILE

~~~sql
SELECT sid,
       name,
       value,
       isspecified,
       update_comment
FROM   v$spparameter
WHERE  name IN (
           'open_cursors',
           'processes',
           'sessions',
           'sga_target',
           'pga_aggregate_target',
           'optimizer_mode'
       )
ORDER  BY name, sid;
~~~

V$SPPARAMETER cho biết cấu hình persistent. Giá trị runtime và SPFILE có thể khác nhau nếu có thay đổi MEMORY hoặc SPFILE chưa được áp dụng bằng restart.

### 11.3. Chụp trạng thái trước change

Trước khi đổi parameter, lưu:
- Name.
- Value hiện tại theo từng instance.
- Value trong SPFILE.
- Scope/SID/PDB.
- ISSYS_MODIFIABLE và ISPDB_MODIFIABLE.
- Thời điểm thay đổi gần nhất nếu có.
- Workload và metric baseline.
- Giá trị rollback.

Không chỉ ghi lại một dòng SHOW PARAMETER nếu môi trường RAC có instance-specific setting.

### 11.4. Xác định parameter có được sửa trong PDB không

Một số parameter có thể được sửa ở PDB scope, một số chỉ ở CDB/system scope. Kiểm tra ISPDB_MODIFIABLE và tài liệu của tham số.

Khi kết nối vào PDB, xác định CON_NAME trước khi đổi. Không chạy ALTER SYSTEM từ CDB root với ý định tác động một PDB mà không chỉ định đúng container/scope.

### 11.5. Parameter trong RAC

Trong RAC, parameter có thể:
- Áp dụng chung cho mọi instance.
- Có giá trị riêng theo instance.
- Chỉ áp dụng ở memory một instance.
- Được lưu trong SPFILE theo SID cụ thể hoặc SID='*'.

Kiểm tra GV$PARAMETER và V$SPPARAMETER trước khi sửa. Không giả định thay đổi ở một instance tự động thay đổi toàn cluster.

## 12. Đổi parameter trong RAC và PDB

### 12.1. SID='*' và SID cụ thể

Đổi parameter chung cho các instance trong SPFILE:

~~~sql
ALTER SYSTEM SET parameter_name = value
SCOPE = SPFILE SID = '*';
~~~

Đổi parameter cho một instance:

~~~sql
ALTER SYSTEM SET parameter_name = value
SCOPE = SPFILE SID = 'orcl2';
~~~

Tên SID phải là instance name đúng. Việc áp dụng memory/runtime phụ thuộc parameter và câu lệnh; kiểm tra GV$PARAMETER sau khi đổi hoặc restart.

### 12.2. Tránh cấu hình lệch giữa instance

Nếu cùng service có thể chạy trên nhiều instance nhưng parameter khác nhau, session chuyển instance có thể nhận behavior khác. Điều này có thể làm lỗi chỉ xuất hiện khi load balance hoặc failover.

Ghi lại lý do mọi instance-specific parameter. Sau rolling restart, xác minh từng instance đã có cấu hình đúng.

### 12.3. PDB scope

Một parameter cho phép PDB modification có thể được đặt trong PDB theo cú pháp và quyền phù hợp. Ví dụ minh họa khi đang ở PDB:

~~~sql
ALTER SESSION SET CONTAINER = APPPDB;
ALTER SYSTEM SET parameter_name = value SCOPE = BOTH;
~~~

Không áp dụng ví dụ này cho mọi parameter. Kiểm tra ISPDB_MODIFIABLE, PDB open state và Oracle Multitenant Administrator's Guide. Nếu tham số chỉ được sửa ở CDB level, lệnh từ PDB sẽ không hợp lệ.

### 12.4. Kiểm tra sau đổi

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
~~~

Sau đó đọc lại GV$PARAMETER/V$PARAMETER và V$SPPARAMETER ở đúng container/instance. Xác minh session mới và session hiện tại nếu tham số có semantics DEFERRED.

## 13. Đánh giá tác động theo nhóm parameter

### 13.1. Memory parameter

Ví dụ:
- SGA_TARGET.
- SGA_MAX_SIZE.
- PGA_AGGREGATE_TARGET.
- MEMORY_TARGET.
- MEMORY_MAX_TARGET.
- DB_CACHE_SIZE.
- SHARED_POOL_SIZE.

Tác động:
- Cạnh tranh RAM với hệ điều hành và process khác.
- Thay đổi cache hit/miss và workload latency.
- Ảnh hưởng nhiều instance nếu host có RAC.
- Có thể cần restart đối với một số parameter hoặc cấu hình memory.
- Có thể khiến process bị OOM hoặc host swap nếu cấp phát quá mức.

Trước khi tăng, xem memory thực tế, OS headroom, huge pages, AMM/ASMM mode, PGA usage và giới hạn container/VM. Không tăng SGA chỉ vì một query chậm mà chưa xác định wait class.

### 13.2. Process/session parameter

Ví dụ:
- PROCESSES.
- SESSIONS.
- OPEN_CURSORS.

Tác động:
- Có thể cần restart với một số parameter như PROCESSES.
- Tăng session/process limit làm tăng khả năng tiêu thụ memory và OS process.
- OPEN_CURSORS lớn hơn không sửa cursor leak; nó chỉ tăng giới hạn cursor mở mỗi session.
- Connection pool quá lớn có thể tiếp tục làm đầy session.

Đo peak concurrent sessions, process count, cursor usage và pool configuration trước khi thay.

### 13.3. Optimizer parameter

Ví dụ:
- OPTIMIZER_MODE.
- OPTIMIZER_FEATURES_ENABLE.
- Một số optimizer-related parameter khác.

Tác động:
- Execution plan có thể thay đổi.
- SQL latency có thể tăng/giảm theo từng query.
- Bind peeking/adaptive behavior và cursor sharing có thể bị ảnh hưởng.
- Thay đổi toàn hệ thống có thể tạo regression trên workload không liên quan.

Không đổi optimizer parameter toàn database để sửa một query mà chưa kiểm tra SQL plan, statistics, bind values và phạm vi ảnh hưởng. Cân nhắc SQL plan management hoặc giải pháp theo SQL cụ thể nếu phù hợp.

### 13.4. Undo/redo parameter

Các thay đổi liên quan undo, redo, archive và recovery có thể ảnh hưởng transaction consistency, recovery window, archive destination và khả năng khôi phục.

Không tăng/giảm retention, undo tablespace hoặc archive behavior khi chưa đánh giá:
- Transaction dài.
- Flashback Query/Flashback Database requirement.
- Backup/archived redo.
- FRA capacity.
- Data Guard transport/apply.
- Recovery objective.

### 13.5. Network và security parameter

Thay đổi listener/network encryption, timeout, wallet, authentication hoặc security parameter có thể làm client không kết nối được. Cần kiểm tra:
- JDBC/OCI driver compatibility.
- TLS/certificate/wallet.
- Connection pool.
- Listener endpoint.
- Client config ở tất cả application nodes.
- Rollback path nếu client cũ không tương thích.

### 13.6. Underscore/hidden parameter

Các parameter bắt đầu bằng dấu gạch dưới thường là hidden/undocumented parameter. Không thay đổi chúng chỉ vì tìm thấy trên forum hoặc một blog.

Chỉ dùng khi Oracle Support hoặc tài liệu chính thức của tình huống yêu cầu, có SR/change record, giá trị được chỉ định và kế hoạch hoàn nguyên. Hidden parameter có thể thay đổi semantics giữa RU và gây tác động không dự đoán được.

## 14. Quy trình đổi parameter an toàn

### Bước 1 — Ghi nhận hiện trạng

Lưu GV$PARAMETER, V$SPPARAMETER, SHOW PARAMETER, database role, instance/PDB và baseline metric.

### Bước 2 — Xác nhận mục tiêu

Viết rõ:
- Triệu chứng cần giải quyết.
- Parameter liên quan vì sao.
- Dự kiến thay đổi behavior nào.
- Phạm vi session/instance/database/PDB.
- Dynamic hay cần restart.
- Tác động lên workload khác.

### Bước 3 — Kiểm tra tài liệu và khả năng sửa

Xem:
- ISSYS_MODIFIABLE.
- ISSES_MODIFIABLE.
- ISPDB_MODIFIABLE.
- Instance-specific behavior.
- COMPATIBLE/version restrictions.
- Licensing nếu parameter gắn với option.

### Bước 4 — Chọn scope

- SESSION: thử trong một session nếu phù hợp.
- MEMORY: thử runtime, không persistent.
- SPFILE: lưu cho lần restart sau.
- BOTH: runtime và persistent nếu dynamic.
- SID: chọn instance hoặc toàn RAC.
- CONTAINER: chọn CDB/PDB đúng phạm vi.

### Bước 5 — Thay một biến mỗi lần

Không đổi nhiều parameter cùng lúc nếu muốn biết thay đổi nào gây cải thiện/regression. Dùng change window, ghi timestamp và người thực hiện.

### Bước 6 — Quan sát ngay sau thay đổi

Theo dõi:
- Alert log.
- ORA error.
- Session/process count.
- CPU/memory.
- Wait events.
- SQL plan/latency.
- Connection pool.
- Service/PDB availability.
- Data Guard/replication nếu liên quan.

### Bước 7 — Quyết định giữ hay rollback

So sánh metric với baseline và tiêu chí đã định. Nếu không đạt, phục hồi giá trị trước đó ở đúng scope. Nếu static parameter đã ghi SPFILE, cần lên kế hoạch restart để áp dụng rollback value.

### Bước 8 — Ghi nhận cấu hình cuối

Lưu runtime value, SPFILE value, instance/PDB, scope, timestamp và change result. Cập nhật configuration management để lần triển khai sau không ghi đè ngoài ý muốn.

## 15. Rollback parameter và cấu hình

### 15.1. Khôi phục giá trị runtime và persistent

Nếu trước đó parameter là dynamic và dùng BOTH:

~~~sql
ALTER SYSTEM SET parameter_name = old_value SCOPE = BOTH;
~~~

Dùng giá trị cũ đã ghi nhận, không suy đoán từ default.

### 15.2. Khôi phục SPFILE cho static parameter

~~~sql
ALTER SYSTEM SET parameter_name = old_value
SCOPE = SPFILE SID = '*';
~~~

Sau đó restart đúng phạm vi để giá trị có hiệu lực. Nếu chỉ đổi SPFILE nhưng chưa restart, runtime value vẫn là giá trị cũ.

### 15.3. RESET parameter

Có thể xóa một entry khỏi SPFILE để trở về default/giá trị kế thừa theo quy tắc:

~~~sql
ALTER SYSTEM RESET parameter_name
SCOPE = SPFILE SID = '*';
~~~

RESET không có nghĩa “khôi phục giá trị trước change” nếu trước đó đã có explicit value. Chỉ dùng sau khi kiểm tra cấu hình kế thừa và giá trị default mong muốn.

### 15.4. Rollback session state

Với session parameter, chạy ALTER SESSION để đặt lại giá trị ban đầu hoặc đóng session. Với pool, bảo đảm connection được reset trước khi trả về pool.

Không chỉ reset trong code path thành công; phải xử lý exception/finally để tránh session state rò sang request tiếp theo.

## 16. Ma trận lựa chọn hành động

| Triệu chứng | Hành động xem xét trước | Điều kiện để nâng mức can thiệp |
| --- | --- | --- |
| Một SQL runaway | Cancel statement nếu được hỗ trợ | SQL không dừng, session gây tác động nghiêm trọng và đã xác định transaction |
| Một session chặn nhiều waiter | Xác định final blocker và transaction | Owner không thể kết thúc an toàn, impact được chấp thuận |
| Session inactive giữ lock | Xác minh transaction và owner | Đã đánh giá rollback/business effect |
| Service không nhận kết nối | Kiểm tra listener, service, PDB | Service/resource thực sự lỗi và có kế hoạch chuyển/khởi động |
| Một RAC instance lỗi | Drain/relocate service, restart instance | Node không thể phục hồi hoặc cần maintenance |
| Một PDB lỗi | Kiểm tra PDB/service/session | Chỉ PDB bị ảnh hưởng và đã đánh giá session/transaction |
| Toàn database không ổn định | Thu thập alert/instance evidence | Có căn cứ restart database và kế hoạch recovery |
| Một parameter gây behavior sai | Thử scope nhỏ nhất nếu hỗ trợ | Đã xác định phạm vi, dynamic/static và rollback |
| Parameter static cần đổi | Ghi SPFILE và lên lịch restart | Đã chuẩn bị downtime/rolling strategy nếu được hỗ trợ |
| Host/storage/network lỗi | Điều phối infrastructure/DBA | Restart host theo DR/maintenance runbook |

## 17. Các kịch bản thực tế

### 17.1. DDL bị chặn bởi một transaction lâu

Tình huống:
- ALTER TABLE chờ lock.
- Một session ứng dụng inactive nhưng giữ transaction.
- Nhiều request chờ DDL hoặc chờ object liên quan.

Cách xử lý:
1. Tìm session đang chặn và final blocker.
2. Xác định owner/module/client identifier.
3. Xem transaction start time, undo blocks và SQL trước đó.
4. Hỏi application owner có thể commit/rollback theo nghiệp vụ không.
5. Nếu cần kill, ghi rõ transaction sẽ rollback và lock có thể chưa nhả ngay.
6. Theo dõi rollback và blocker chain.
7. Chạy lại DDL với timeout có giới hạn trong cửa sổ phù hợp.

Không kill waiter; xác định blocker thực sự trước.

### 17.2. Một query tiêu thụ CPU cao

Tình huống:
- CPU tăng.
- Một SQL_ID chiếm nhiều DB time.
- Các session khác bị chậm.

Cách xử lý:
1. Xác định SQL_ID, plan, module và số session cùng chạy.
2. Xác định query là batch hợp lệ hay runaway.
3. Kiểm tra execution plan, bind values và wait class.
4. Nếu chỉ cần dừng statement, dùng cơ chế cancel phù hợp.
5. Chỉ kill session nếu cần chấm dứt session và đã đánh giá transaction.
6. Theo dõi pool retry và số session mới.
7. Khắc phục SQL/plan/root cause sau khi ổn định.

Không restart database chỉ vì CPU cao do một SQL.

### 17.3. Session count chạm giới hạn

Tình huống:
- Ứng dụng nhận lỗi không tạo thêm session.
- Nhiều session INACTIVE.
- Connection pool có thể quá lớn hoặc leak.

Cách xử lý:
1. Phân nhóm session theo username, service, module, machine.
2. Đối chiếu pool max size và số replica.
3. Xác định session inactive có transaction không.
4. Xử lý leak/pool config.
5. Kill session chỉ khi đã xác định connection stale và transaction impact.
6. Thay PROCESSES/SESSIONS chỉ sau khi tính memory/process capacity và restart requirement.

Tăng giới hạn đơn thuần có thể chỉ trì hoãn lỗi và làm tăng tải.

### 17.4. Một RAC instance cần restart

Tình huống:
- Một instance có wait/error bất thường.
- Service còn có instance khác có thể nhận workload.

Cách xử lý:
1. Kiểm tra GV$INSTANCE, GV$ACTIVE_SERVICES và session distribution.
2. Kiểm tra capacity instance còn lại.
3. Xác nhận client failover/connection pool behavior.
4. Drain hoặc relocate service theo runbook.
5. Stop instance bằng Clusterware tool.
6. Start instance và xác minh open mode.
7. Kiểm tra service placement, listener và application health.
8. Theo dõi load redistribution.

Không dừng instance thứ hai trước khi instance đầu tiên và service đã ổn định.

### 17.5. Parameter static cần thay đổi

Tình huống:
- Oracle báo parameter không thể sửa động.
- Cần thay giá trị để hỗ trợ workload mới.

Cách xử lý:
1. Đọc ISSYS_MODIFIABLE và V$SPPARAMETER.
2. Xác định parameter áp dụng toàn RAC hay instance cụ thể.
3. Ghi giá trị runtime/SPFILE hiện tại.
4. Kiểm tra memory/resource và compatibility.
5. Đặt giá trị mới trong SPFILE.
6. Lập lịch restart đúng phạm vi.
7. Sau restart, kiểm tra runtime và SPFILE.
8. Chạy smoke test và so sánh workload.
9. Nếu regression, khôi phục giá trị cũ và restart theo kế hoạch.

## 18. Checklist trước khi kill, restart hoặc đổi parameter

### Bằng chứng

- [ ] Có incident/change ID và thời điểm bắt đầu.
- [ ] Đã xác định database, role, instance, service và PDB.
- [ ] Đã xác định session/SQL/parameter liên quan.
- [ ] Đã lưu alert log, wait event và metric baseline.
- [ ] Đã xác định blocker chain nếu có.

### Transaction và dữ liệu

- [ ] Đã kiểm tra transaction đang mở.
- [ ] Đã ước lượng undo/rollback impact.
- [ ] Đã kiểm tra distributed transaction nếu có.
- [ ] Đã đánh giá commit outcome và retry/idempotency.
- [ ] Đã xác định lock có thể còn giữ trong lúc rollback.

### Phạm vi can thiệp

- [ ] Đã chọn session/service/PDB/instance/database/host scope đúng.
- [ ] Đã xác định session bằng SID + SERIAL# + INST_ID.
- [ ] Đã xác nhận session không phải background process.
- [ ] Đã kiểm tra service failover và capacity RAC.
- [ ] Đã xác định restart có ảnh hưởng Data Guard/CDC/batch không.

### Parameter

- [ ] Đã lưu GV$PARAMETER và V$SPPARAMETER.
- [ ] Đã kiểm tra dynamic/static, session/system/PDB scope.
- [ ] Đã xác định SCOPE và SID.
- [ ] Đã ghi giá trị rollback.
- [ ] Đã đánh giá CPU/memory/optimizer/network/security impact.
- [ ] Không dùng hidden parameter khi chưa có hướng dẫn chính thức.

### Thực hiện và xác minh

- [ ] Có owner/incident commander phê duyệt theo quy trình.
- [ ] Có maintenance window hoặc điều kiện dừng rõ ràng.
- [ ] Theo dõi blocker, rollback, startup và alert log.
- [ ] Kiểm tra session/service/instance/database state sau thao tác.
- [ ] Kiểm tra application reconnect và error rate.
- [ ] Kiểm tra parameter runtime/SPFILE đúng scope.
- [ ] Ghi lại kết quả, thời gian và bước tiếp theo.

## 19. Bài thực hành

Thực hiện trên database test, hai session riêng và dữ liệu có thể khôi phục. Không kill session, restart hoặc thay parameter trên production chỉ để thử nghiệm.

### Bài 1 — Tạo blocking transaction

Session A update một hàng và chưa commit. Session B update cùng hàng. Quan sát blocker/waiter qua GV$SESSION.

### Bài 2 — Xác định transaction

Join GV$SESSION với GV$TRANSACTION. Ghi USED_UBLK, USED_UREC và START_TIME trước khi kết thúc transaction.

### Bài 3 — Kill session trong lab

Dùng SID/SERIAL# vừa xác minh để kill session test. Quan sát trạng thái KILLED, rollback và thời điểm lock được giải phóng.

### Bài 4 — Disconnect POST_TRANSACTION

Tạo transaction test và chạy DISCONNECT SESSION POST_TRANSACTION. Commit từ session gốc theo quy trình test rồi quan sát disconnect.

### Bài 5 — ORA-00031

Trong một kịch bản có kiểm soát, quan sát session marked for kill nếu phát sinh. Theo dõi cleanup thay vì lặp lệnh kill.

### Bài 6 — DDL_LOCK_TIMEOUT

Giữ DML lock, đặt DDL_LOCK_TIMEOUT=5 trong session khác và thử ALTER TABLE. Ghi thời gian chờ và kết quả.

### Bài 7 — Shutdown mode

Trong database test có thể restart, so sánh NORMAL, TRANSACTIONAL và IMMEDIATE. Không dùng ABORT nếu không có mục tiêu học crash recovery rõ ràng.

### Bài 8 — PDB restart

Đóng/mở một PDB test. Xác nhận session PDB bị ngắt và CDB/root cùng PDB khác vẫn hoạt động theo thiết kế.

### Bài 9 — Parameter MEMORY

Đổi một parameter dynamic phù hợp bằng SCOPE=MEMORY. Xác nhận GV$PARAMETER đổi nhưng V$SPPARAMETER không đổi; restart lab để quan sát giá trị trở về.

### Bài 10 — Parameter SPFILE

Đổi một parameter lab bằng SCOPE=SPFILE. Xác nhận runtime chưa đổi và SPFILE đã ghi; restart lab rồi xác nhận runtime.

### Bài 11 — Parameter BOTH

Chọn parameter dynamic được phép, đổi SCOPE=BOTH. Xác nhận cả runtime và SPFILE.

### Bài 12 — Session parameter và pool

Đổi NLS hoặc timezone trong một session. Trả connection vào pool test và mượn lại để quan sát session state; triển khai reset hook.

### Bài 13 — RAC scope

Trong môi trường RAC test, so sánh GV$PARAMETER và V$SPPARAMETER với SID='*' và SID cụ thể. Không thay đổi parameter production.

### Bài 14 — Viết incident runbook

Chọn một tình huống blocker, runaway SQL hoặc static parameter. Viết bằng chứng cần thu, blast radius, lệnh dự kiến, điều kiện dừng, rollback và validation.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — ALTER SYSTEM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SYSTEM.html): thay đổi parameter và kết thúc session.
- [Oracle Database 19c SQL Language Reference — ALTER SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SESSION.html): thay đổi session settings.
- [Oracle Database 19c Administrator's Guide — Starting Up and Shutting Down](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/starting-up-and-shutting-down.html): shutdown mode và startup.
- [Oracle Database 19c Administrator's Guide — Managing Processes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-processes.html): session/process management.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session state, SQL, blocker và client information.
- [Oracle Database 19c Database Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html): transaction và undo usage.
- [Oracle Database 19c Database Reference — V$PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PARAMETER.html): runtime parameter values và modifiability.
- [Oracle Database 19c Database Reference — V$SPPARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SPPARAMETER.html): parameter values trong SPFILE.
- [Oracle Database 19c Database Reference — DDL_LOCK_TIMEOUT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DDL_LOCK_TIMEOUT.html): DDL lock wait.
- [Oracle Real Application Clusters Administration and Deployment Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/): service, instance và SRVCTL.
- [Oracle Database 19c Data Guard Broker Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/): kiểm tra và vận hành Data Guard configuration.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): điều kiện sử dụng các tính năng được cấp phép.

Kill session, restart và đổi parameter đều có thể cần thiết khi xử lý sự cố, nhưng mỗi hành động có phạm vi và hậu quả khác nhau. Kill session có thể tạo rollback dài và giữ lock tới khi cleanup hoàn tất; restart làm mất các connection trong phạm vi bị dừng và có thể cần instance recovery; parameter change có thể tác động một session, một instance, PDB hoặc toàn database, tức thời hoặc sau restart. **Hãy lưu bằng chứng và giá trị cấu hình trước khi can thiệp, xác định transaction và blast radius, chọn scope nhỏ nhất đáp ứng mục tiêu, rồi xác minh trạng thái và workload sau thay đổi.**
