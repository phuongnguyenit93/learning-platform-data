# SHUTDOWN NORMAL, TRANSACTIONAL, IMMEDIATE và ABORT

Oracle Database có nhiều chế độ shutdown để DBA chọn cách kết thúc hoạt động của instance. Bốn chế độ thường gặp là NORMAL, TRANSACTIONAL, IMMEDIATE và ABORT. Chúng khác nhau ở cách xử lý session đang kết nối, transaction đang chạy, SQL statement chưa hoàn tất và công việc recovery khi khởi động lại.

Chọn sai shutdown mode có thể làm maintenance bị chờ lâu, ngắt giao dịch của ứng dụng hoặc buộc instance recovery khi startup tiếp theo. Vì vậy, DBA cần hiểu chính xác mức độ chờ, rollback và trạng thái database sau từng chế độ. Shutdown cũng là một thao tác vận hành: cần phối hợp với application, connection pool, scheduler, RAC/Clusterware và Data Guard nếu hệ thống có sử dụng.

Sau bài học, bạn có thể:

- Phân biệt hành vi của SHUTDOWN NORMAL, TRANSACTIONAL, IMMEDIATE và ABORT.
- Chọn mode theo yêu cầu bảo toàn transaction và thời gian dừng dịch vụ.
- Hiểu điều gì xảy ra với session, SQL statement và transaction chưa commit.
- Giải thích vì sao NORMAL/TRANSACTIONAL có thể chờ lâu.
- Phân biệt rollback khi shutdown immediate với instance recovery sau abort.
- Kết nối bằng quyền quản trị và thực hiện shutdown đúng cú pháp.
- Kiểm tra session, transaction và trạng thái instance trước khi shutdown.
- Theo dõi một shutdown đang chờ và xử lý blocker.
- Lập kế hoạch shutdown/startup cho single instance, RAC và CDB/PDB.
- Hiểu ảnh hưởng tới application services, scheduled jobs, listener và Data Guard.
- Chẩn đoán lỗi phổ biến và xây dựng runbook có kiểm soát.

> Ví dụ dùng SQL*Plus/SQLcl và Oracle instance thông thường. Quyền, cú pháp chi tiết và hành vi một số tùy chọn có thể phụ thuộc release/platform. Trong RAC và môi trường Oracle Restart/Clusterware, dùng công cụ quản lý tài nguyên như SRVCTL theo runbook của hệ thống.

## 1. Shutdown là gì?

### 1.1. Instance và database

Oracle instance gồm SGA và background processes. Database là các file vật lý như datafiles, control files và online redo logs. Khi shutdown sạch, Oracle kết thúc hoạt động instance, đóng database, dismount database khỏi instance và dừng các background process.

Shutdown ABORT kết thúc instance ngay, không thực hiện toàn bộ trình tự đóng sạch. Database sẽ cần instance recovery ở lần startup tiếp theo.

### 1.2. Các trạng thái chính

Một instance/database thường đi qua các trạng thái:

```text
STARTUP NOMOUNT
    |
    v
MOUNT
    |
    v
OPEN
    |
    v
SHUTDOWN
```

- NOMOUNT: instance đã khởi động và đọc parameter file, SGA/process được tạo.
- MOUNT: control file được mở, database được mount.
- OPEN: datafiles và online redo logs được mở; database phục vụ truy cập theo mode.
- SHUTDOWN: instance đã dừng.

### 1.3. Clean shutdown và abort

NORMAL, TRANSACTIONAL và IMMEDIATE là các clean shutdown modes: Oracle thực hiện trình tự kết thúc giao dịch/session theo mode rồi đóng database và dừng instance.

ABORT là shutdown không sạch: Oracle dừng instance mà không chờ session, không rollback các transaction đang mở như IMMEDIATE và không đóng database theo trình tự thông thường. Recovery sẽ được thực hiện khi startup sau đó.

### 1.4. Shutdown không đồng nghĩa với tắt máy chủ

SHUTDOWN dừng một Oracle instance. Nó không tắt OS, không tự dừng mọi listener, không dừng các instance khác trên host và không thay thế quy trình dừng application/Clusterware/ASM.

Nếu host chạy nhiều database hoặc ASM, phải xác định đúng target instance và thứ tự phụ thuộc trước khi thao tác.

## 2. Cú pháp SHUTDOWN

### 2.1. Cú pháp cơ bản

Trong SQL*Plus hoặc SQLcl:

```sql
SHUTDOWN NORMAL
SHUTDOWN TRANSACTIONAL
SHUTDOWN IMMEDIATE
SHUTDOWN ABORT
```

Nếu gõ SHUTDOWN không kèm mode, mặc định là NORMAL.

### 2.2. SHUTDOWN là lệnh của client

SHUTDOWN là command của SQL*Plus/SQLcl, không phải câu SQL DML/DDL để chạy trong PL/SQL block. Không đặt nó bên trong BEGIN ... END.

Ví dụ kết nối quản trị trên host bằng OS authentication:

```sql
sqlplus / as sysdba
SHUTDOWN IMMEDIATE
```

Hoặc kết nối qua phương thức xác thực quản trị được DBA cấp. Không đưa mật khẩu SYS vào script, shell history hoặc log.

### 2.3. Quyền cần thiết

Shutdown cần một administrative connection với quyền phù hợp, thường là SYSDBA hoặc SYSOPER; các administrative privilege khác có thể được hỗ trợ theo release. Dùng tài khoản/quyền được tổ chức cấp và tuân theo chính sách kiểm soát truy cập.

Tài khoản ứng dụng thông thường không được phép shutdown instance. Không cấp SYSDBA cho application chỉ để thực hiện thao tác vận hành.

### 2.4. Không nhầm SHUTDOWN với ALTER DATABASE CLOSE

ALTER DATABASE CLOSE đóng database nhưng không nhất thiết dừng instance. SHUTDOWN kết thúc cả database lifecycle và instance. Trong runbook, chọn đúng thao tác theo mục tiêu: đóng database, chuyển trạng thái, hay dừng hẳn instance.

### 2.5. Xác định instance trước khi shutdown

Sau khi kết nối, kiểm tra:

```sql
SELECT
    instance_name,
    host_name,
    status,
    database_status,
    startup_time
FROM v$instance;

SELECT
    name,
    open_mode,
    database_role
FROM v$database;
```

Trên RAC, kiểm tra toàn cluster qua GV$INSTANCE và dùng SRVCTL để xác định đúng instance/resource cần dừng.

## 3. So sánh bốn shutdown modes

### 3.1. Bảng tổng quan

| Hành vi | NORMAL | TRANSACTIONAL | IMMEDIATE | ABORT |
| --- | --- | --- | --- | --- |
| Ngăn kết nối mới | Có | Có | Có | Instance dừng ngay |
| Ngăn transaction mới | Không theo cơ chế drain riêng; session đang kết nối vẫn hoạt động | Có | Có | Không chờ |
| Chờ user tự disconnect | Có | Không; sau khi transaction kết thúc Oracle ngắt client | Không | Không |
| Chờ transaction hiện tại kết thúc | Chờ user/session tự kết thúc | Có | Không; rollback transaction chưa commit | Không |
| Hủy SQL đang chạy | Không theo kiểu immediate | Đợi transaction hoàn tất | Có | Dừng process/instance |
| Rollback transaction chưa commit | Phụ thuộc user kết thúc session và hành vi disconnect | Transaction được hoàn tất bởi client trước khi disconnect | Oracle rollback | Không rollback sạch trong shutdown |
| Clean shutdown | Có | Có | Có | Không |
| Instance recovery ở startup sau | Không cần do shutdown mode | Không cần do shutdown mode | Không cần do shutdown mode | Có |

### 3.2. Cách nhớ

- NORMAL: đợi tất cả user tự rời khỏi database.
- TRANSACTIONAL: ngăn transaction mới, đợi transaction đang có kết thúc rồi ngắt client.
- IMMEDIATE: ngắt client và rollback transaction chưa commit.
- ABORT: dừng ngay, recovery ở startup kế tiếp.

### 3.3. Chọn theo mục tiêu vận hành

| Mục tiêu | Mode thường phù hợp |
| --- | --- |
| Chờ ứng dụng tự kết thúc mọi session | NORMAL |
| Cho giao dịch đang chạy hoàn tất, không nhận giao dịch mới | TRANSACTIONAL |
| Cần dừng dịch vụ trong thời gian hợp lý, chấp nhận rollback transaction chưa commit | IMMEDIATE |
| Instance không thể shutdown sạch hoặc cần dừng khẩn cấp | ABORT |

Đây là định hướng lựa chọn, không phải thay thế runbook. Với ứng dụng có giao dịch tài chính hoặc distributed transaction, phải hiểu transaction boundary và phối hợp với application owner trước khi chọn mode.

## 4. SHUTDOWN NORMAL

### 4.1. Hành vi

NORMAL là mode mặc định nếu không chỉ rõ mode. Oracle ngăn các kết nối mới và chờ tất cả user đang kết nối disconnect một cách bình thường. Shutdown command chỉ hoàn tất sau khi các session hiện có rời khỏi database.

Oracle không tự động ngắt các user đang kết nối để hoàn tất shutdown như IMMEDIATE. Một session idle, connection pool giữ connection hoặc application quên close connection có thể làm shutdown chờ vô thời hạn.

### 4.2. Transaction đang mở

Với NORMAL, session có thể tiếp tục hoạt động và tự commit/rollback transaction theo logic ứng dụng, sau đó disconnect. Oracle chờ session kết thúc thay vì tự động rollback mọi transaction ngay khi nhận lệnh shutdown.

Nếu user không disconnect, shutdown tiếp tục chờ. Vì vậy, NORMAL phù hợp khi DBA muốn ứng dụng đóng phiên một cách tự nhiên và có thể kiểm soát thời điểm các client rời đi.

### 4.3. Ví dụ

```sql
SHUTDOWN NORMAL
```

Nếu có user session vẫn kết nối, command sẽ chưa trả prompt hoàn tất. DBA cần xác định session còn lại và phối hợp để chúng disconnect.

### 4.4. Khi nào dùng?

- Môi trường lab hoặc maintenance có ít session.
- Hệ thống có quy trình drain connection rõ ràng.
- Muốn cho ứng dụng hoàn thành công việc và tự đóng session.
- Có thời gian dừng không bị giới hạn chặt.

### 4.5. Rủi ro

- Có thể chờ rất lâu vì idle session.
- Connection pool có thể giữ connection mở dù không chạy SQL.
- Job/session nền của ứng dụng có thể không tự disconnect.
- DBA có thể nhầm shutdown bị treo trong khi Oracle chỉ đang chờ client.

Nếu thời gian maintenance có giới hạn, NORMAL thường không phải lựa chọn thực tế cho hệ thống có nhiều session khó kiểm soát.

## 5. SHUTDOWN TRANSACTIONAL

### 5.1. Hành vi

TRANSACTIONAL ngăn user bắt đầu transaction mới và chờ các transaction hiện đang hoạt động hoàn tất. Khi transaction kết thúc, Oracle disconnect client/session và tiếp tục shutdown.

Mục tiêu là cho giao dịch đang chạy có cơ hội commit hoặc rollback theo logic của ứng dụng, đồng thời không cho giao dịch mới bắt đầu trong giai đoạn drain.

### 5.2. Khác NORMAL

NORMAL chờ mọi session disconnect, kể cả session không có transaction nhưng vẫn giữ connection.

TRANSACTIONAL tập trung vào transaction: nó chờ transaction hiện tại hoàn tất, rồi Oracle ngắt client. Session idle không có transaction không cần đợi user tự đóng connection như NORMAL.

### 5.3. Khác IMMEDIATE

TRANSACTIONAL không chủ động rollback transaction đang hoạt động chỉ để shutdown nhanh. Nó đợi transaction kết thúc. IMMEDIATE hủy SQL đang chạy và rollback transaction chưa commit.

Nếu một transaction chạy lâu hoặc application không kết thúc transaction, TRANSACTIONAL cũng có thể chờ lâu.

### 5.4. Ví dụ

```sql
SHUTDOWN TRANSACTIONAL
```

Trong thời gian chờ, application không thể bắt đầu transaction mới. Các transaction đã bắt đầu cần hoàn tất trước khi session bị disconnect.

### 5.5. TRANSACTIONAL LOCAL trong RAC

Một số release hỗ trợ tùy chọn SHUTDOWN TRANSACTIONAL LOCAL trong môi trường RAC. Tùy chọn LOCAL giới hạn việc chờ theo transaction local của instance đang shutdown, thay vì chờ mọi transaction có liên quan từ các instance khác theo semantics TRANSACTIONAL thông thường.

Đây là cú pháp chuyên biệt cho RAC; kiểm tra Oracle RAC Administrator's Guide của release và dùng SRVCTL/Clusterware runbook nếu instance được quản lý bởi cluster. Không dùng LOCAL trên single-instance như một mode riêng.

### 5.6. Khi nào dùng?

- Muốn ngừng nhận transaction mới.
- Muốn cho transaction hiện tại kết thúc bình thường.
- Muốn tránh rollback hàng loạt transaction đang chạy.
- Có thể chấp nhận thời gian drain phụ thuộc transaction dài nhất.

### 5.7. Rủi ro

- Transaction batch/ETL dài có thể kéo dài shutdown.
- Application có thể retry và tạo request mới nếu không được thông báo drain.
- Distributed transaction/in-doubt transaction cần quy trình riêng.
- Không phải mọi client đều có thể hoàn thành trước maintenance deadline.

## 6. SHUTDOWN IMMEDIATE

### 6.1. Hành vi

IMMEDIATE ngăn kết nối mới và transaction mới, kết thúc các SQL statement đang chạy, disconnect user session và rollback transaction chưa commit. Sau khi xử lý rollback và đóng database, Oracle dismount database và dừng instance.

IMMEDIATE không chờ user tự disconnect và không chờ transaction hiện tại commit như TRANSACTIONAL. Đây là mode thường dùng cho maintenance có thời gian dừng được kiểm soát.

### 6.2. Rollback transaction chưa commit

Giả sử session đang thực hiện:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Chưa COMMIT
```

Nếu DBA chạy SHUTDOWN IMMEDIATE, transaction chưa commit sẽ bị rollback. Giá trị đã commit trước đó vẫn được bảo toàn; thay đổi chưa commit không trở thành dữ liệu bền vững.

Rollback có thể mất thời gian nếu transaction đã sửa nhiều block hoặc tạo lượng undo lớn. Vì vậy, IMMEDIATE không có nghĩa command luôn hoàn tất ngay lập tức.

### 6.3. SQL statement đang chạy

Oracle chấm dứt SQL statement đang thực thi và xử lý transaction tương ứng theo quy tắc rollback. Application có thể nhận lỗi kết nối hoặc lỗi statement; ứng dụng cần xử lý request thất bại và không giả định thao tác đã commit.

### 6.4. Ví dụ

```sql
SHUTDOWN IMMEDIATE
```

Khi command hoàn tất, database đã đóng sạch theo trình tự shutdown immediate. Startup tiếp theo không cần instance recovery chỉ vì shutdown mode này.

### 6.5. Khi nào dùng?

- Maintenance có cửa sổ thời gian rõ.
- Muốn dừng session mà không phải chờ client tự disconnect.
- Chấp nhận rollback các transaction chưa commit.
- Cần shutdown sạch để patch, restart hoặc thay đổi cấu hình.

### 6.6. Rủi ro

- Transaction chưa commit bị rollback.
- Client đang xử lý có thể nhận lỗi và cần retry theo idempotency.
- Rollback lớn có thể làm shutdown kéo dài.
- Application có thể đang thực hiện side effect bên ngoài database; rollback Oracle không tự hoàn tác email, HTTP call hoặc file system operation.

### 6.7. IMMEDIATE là lựa chọn phổ biến, nhưng không phải mặc định cho mọi hệ thống

Trước khi dùng, drain traffic và thông báo ứng dụng. Nếu nghiệp vụ yêu cầu giao dịch hiện tại phải hoàn thành, TRANSACTIONAL có thể phù hợp hơn. Nếu session cần tự đóng theo quy trình ứng dụng, NORMAL có thể phù hợp hơn.

## 7. SHUTDOWN ABORT

### 7.1. Hành vi

ABORT dừng instance ngay lập tức, không chờ user disconnect, không chờ transaction kết thúc, không rollback các transaction chưa commit trong trình tự shutdown và không đóng/dismount database theo quy trình clean shutdown.

Đây là tình huống gần với instance bị crash hoặc mất nguồn ở góc nhìn recovery. Oracle cần thực hiện instance recovery khi database được startup lại.

### 7.2. Ví dụ

```sql
SHUTDOWN ABORT
```

Dùng ABORT khi các mode shutdown khác không thể hoàn tất trong thời gian cần thiết hoặc instance đang ở trạng thái không thể shutdown bình thường. Không dùng làm cách dừng dịch vụ hằng ngày chỉ vì nó nhanh.

### 7.3. Điều gì xảy ra với transaction chưa commit?

ABORT không làm cho transaction chưa commit trở thành committed. Ở lần startup kế tiếp, Oracle sử dụng redo để khôi phục các thay đổi cần thiết cho database consistency, sau đó undo các transaction chưa commit theo recovery process.

Các transaction chưa commit sẽ không được xem là giao dịch thành công. Client có thể không biết chắc statement cuối cùng đã commit hay chưa nếu kết nối bị mất đúng thời điểm COMMIT; application phải kiểm tra kết quả bằng transaction ID/idempotency key trước khi retry thao tác nghiệp vụ.

### 7.4. Instance recovery sau ABORT

Khi startup, Oracle kiểm tra trạng thái database và thực hiện instance recovery nếu cần. Ở mức khái quát:

1. Redo được áp dụng để đưa datafiles về trạng thái nhất quán với redo cần thiết.
2. Các thay đổi thuộc transaction chưa commit được undo theo cơ chế recovery.
3. Database được đưa về trạng thái có thể mở.

Thời gian recovery phụ thuộc lượng redo chưa checkpoint, tốc độ storage, cấu hình recovery và trạng thái instance khi abort. Startup sau ABORT có thể lâu hơn clean shutdown.

### 7.5. ABORT có làm hỏng database không?

ABORT tự nó không đồng nghĩa database bị corrupt. Oracle được thiết kế để phục hồi sau instance failure bằng redo/undo. Tuy nhiên, abort làm phát sinh recovery work, làm gián đoạn client và có thể kéo dài thời gian đưa dịch vụ trở lại.

Không nhầm instance recovery với media recovery. Nếu datafile/storage bị hỏng vật lý, instance recovery không thay thế restore/recover từ backup.

### 7.6. Khác với kill process ở OS

Nếu cần abort, dùng lệnh SHUTDOWN ABORT qua Oracle administrative interface khi instance còn phản hồi. Không kill -9 hoặc terminate Oracle process tùy tiện; thao tác OS có thể làm tình huống khó kiểm soát hơn và bỏ qua cơ chế quản trị của Oracle.

Nếu instance không còn phản hồi, thực hiện quy trình incident recovery/Clusterware phù hợp và làm việc với DBA chịu trách nhiệm.

### 7.7. Khi nào dùng?

- SHUTDOWN IMMEDIATE/NORMAL/TRANSACTIONAL không thể hoàn tất và cần dừng instance.
- Instance bị treo hoặc không đáp ứng lệnh shutdown bình thường.
- Có sự cố vận hành yêu cầu dừng ngay theo incident runbook.
- DBA đã chấp nhận startup sau đó phải thực hiện instance recovery.

### 7.8. Rủi ro

- Startup tiếp theo cần instance recovery.
- Thời gian recovery khó dự đoán nếu chưa biết lượng redo cần xử lý.
- Client mất kết nối đột ngột; kết quả transaction cuối cùng có thể cần xác minh.
- Có thể làm tăng thời gian outage tổng thể dù lệnh abort trả về nhanh.

## 8. Rollback, checkpoint và recovery

### 8.1. Rollback không giống instance recovery

Rollback là hoàn tác thay đổi của transaction chưa commit. Instance recovery là quy trình khôi phục database sau khi instance kết thúc bất thường hoặc shutdown không sạch.

IMMEDIATE thực hiện rollback transaction chưa commit trước khi kết thúc clean shutdown. ABORT dừng trước khi rollback theo trình tự shutdown; việc recovery xử lý transaction chưa commit khi startup.

### 8.2. Checkpoint và clean shutdown

Trong clean shutdown, Oracle đóng database theo trình tự và thực hiện các hoạt động cần thiết để đảm bảo trạng thái database có thể mở lại mà không cần instance recovery do shutdown. Các dirty buffer và metadata được xử lý theo cơ chế Oracle.

ABORT không chờ checkpoint/close theo quy trình clean shutdown. Vì vậy, redo và undo được dùng để phục hồi sau startup.

### 8.3. Transaction đã COMMIT

Commit được Oracle xác nhận theo redo durability semantics. Sau ABORT, redo recovery giúp bảo toàn các transaction đã commit theo cấu hình durability của database. Không coi các thay đổi chưa commit là đã lưu chỉ vì client đã gửi DML.

### 8.4. Distributed transaction

Transaction phân tán có thể ở trạng thái in-doubt nếu kết nối tới participant/coordinator bị gián đoạn. Shutdown mode không thay thế quy trình xử lý distributed transaction. DBA cần xem DBA_2PC_PENDING/DBA_2PC_NEIGHBORS và dùng quy trình commit/rollback force chỉ khi có quyết định nghiệp vụ và thông tin coordinator phù hợp.

### 8.5. Startup sau từng mode

| Mode trước đó | Instance recovery do shutdown mode? | Ghi chú |
| --- | --- | --- |
| NORMAL | Không | Clean close |
| TRANSACTIONAL | Không | Clean close sau khi transaction hoàn tất |
| IMMEDIATE | Không | Clean close sau rollback transaction chưa commit |
| ABORT | Có | Oracle recovery ở startup tiếp theo |

Không nhầm recovery do ABORT với media recovery do file bị mất/hỏng.

## 9. Theo dõi session trước khi shutdown

### 9.1. Liệt kê user sessions

DBA có thể xem các session user đang kết nối:

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    machine,
    program,
    module,
    logon_time,
    event,
    sql_id,
    taddr
FROM v$session
WHERE type = 'USER'
ORDER BY username, logon_time;
```

Session IDLE vẫn có thể giữ connection và làm SHUTDOWN NORMAL chờ. Xem MACHINE, PROGRAM và MODULE để xác định owner; không kill session chỉ vì status là INACTIVE.

### 9.2. Tìm session có transaction

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.machine,
    s.program,
    s.sql_id,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM v$session s
JOIN v$transaction t
  ON t.addr = s.taddr
ORDER BY t.start_time;
```

USED_UBLK và USED_UREC là thông tin về undo sử dụng, giúp nhận biết transaction có quy mô lớn. Chúng không phải phép đo thời gian rollback chính xác.

### 9.3. Session blocker và lock

```sql
SELECT
    sid,
    serial#,
    username,
    blocking_session,
    event,
    seconds_in_wait,
    sql_id,
    machine,
    program
FROM v$session
WHERE blocking_session IS NOT NULL;
```

Đây là truy vấn tìm session đang chờ một blocker. Shutdown chờ session disconnect/transaction hoàn tất không nhất thiết luôn hiển thị một blocking_session; cần xem session list và transaction list song song.

### 9.4. Kiểm tra job đang chạy

```sql
SELECT
    owner,
    job_name,
    session_id,
    running_instance,
    elapsed_time,
    cpu_used
FROM dba_scheduler_running_jobs
ORDER BY owner, job_name;
```

View yêu cầu quyền phù hợp. Job đang chạy có thể sở hữu transaction dài hoặc tạo session không tự đóng. Phối hợp với owner để dừng/hoàn tất job đúng cách.

### 9.5. Kiểm tra session theo service/module

```sql
SELECT
    service_name,
    module,
    action,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY service_name, module, action
ORDER BY session_count DESC;
```

Thông tin module/action/service chỉ hữu ích nếu ứng dụng thiết lập chúng nhất quán. Dùng để xác định connection pool hoặc workload còn kết nối.

## 10. Theo dõi shutdown đang chờ

### 10.1. Shutdown NORMAL chờ user disconnect

Nếu command vẫn chờ, kiểm tra:

- User sessions còn kết nối.
- Connection pool giữ idle connection.
- Scheduler/job session.
- Monitoring/backup/agent tự kết nối lại.
- Application chưa drain traffic hoặc còn health check.

Shutdown NORMAL không bị giới hạn bởi một timeout mặc định kiểu WAIT n giây cho mỗi session. DBA phải xác định session còn lại và phối hợp đóng.

### 10.2. Shutdown TRANSACTIONAL chờ transaction

Xem V$TRANSACTION và V$SESSION để tìm transaction còn hoạt động. Tìm SQL_ID, module, machine, thời gian bắt đầu và lượng undo. Transaction batch lớn có thể cần thời gian hoàn tất.

Không kết luận transaction bị treo chỉ vì nó chạy lâu. Hỏi application owner xem transaction còn tiến triển và có thể commit/rollback theo logic hay không.

### 10.3. Shutdown IMMEDIATE chờ rollback

IMMEDIATE có thể mất thời gian khi rollback transaction lớn. Theo dõi alert log, session/process và undo activity theo công cụ DBA được phép. Không chuyển sang ABORT chỉ vì rollback chưa hoàn tất sau vài giây; cân nhắc rủi ro recovery và tổng outage.

### 10.4. Alert log

Alert log ghi nhận các sự kiện startup/shutdown, lỗi nghiêm trọng và nhiều thông báo tiến trình. Có thể xem bằng ADRCI hoặc view phù hợp:

```sql
SELECT
    originating_timestamp,
    message_text
FROM v$diag_alert_ext
WHERE originating_timestamp > SYSTIMESTAMP - INTERVAL '2' HOUR
ORDER BY originating_timestamp;
```

Quyền và availability của view phụ thuộc cấu hình. Alert log là nguồn chính để xác nhận Oracle ghi nhận shutdown/recovery tới đâu.

### 10.5. Không mở thêm connection ứng dụng trong lúc drain

Nếu application, monitor hoặc pool tiếp tục reconnect, NORMAL có thể không bao giờ hoàn tất. Trước khi shutdown, chuyển service sang maintenance/drain và chặn traffic mới theo quy trình hạ tầng.

## 11. Ngắt session thủ công: dùng thận trọng

### 11.1. ALTER SYSTEM KILL SESSION

DBA có thể kết thúc một session cụ thể:

```sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
```

Thay sid và serial# bằng giá trị thực lấy từ V$SESSION. Đây là thao tác mạnh: transaction chưa commit của session bị rollback và ứng dụng có thể nhận lỗi.

### 11.2. Không kill session chỉ vì shutdown NORMAL chờ

Nếu mục tiêu là để application đóng phiên bình thường, hãy thông báo owner/pool trước. Kill session có thể làm request đang xử lý thất bại, tạo retry và side effect trùng lặp ở hệ thống bên ngoài.

### 11.3. KILL SESSION không phải ABORT instance

KILL SESSION tác động một session. SHUTDOWN ABORT dừng toàn instance. Hai lệnh có phạm vi và recovery consequence hoàn toàn khác nhau.

### 11.4. Session marked for kill

ALTER SYSTEM KILL SESSION có thể đánh dấu session để kết thúc và cleanup; session có thể chưa biến mất ngay nếu đang rollback hoặc chờ tài nguyên. Kiểm tra trạng thái session và alert/trace thay vì lặp lệnh kill liên tục.

### 11.5. OS process termination

Không dùng kill -9 hoặc taskkill để xử lý session Oracle thông thường. Dùng Oracle session management và shutdown command. Chỉ xử lý process ở OS theo incident runbook và hướng dẫn DBA/Oracle Support khi instance không còn phản hồi.

## 12. Shutdown trong CDB và PDB

### 12.1. CDB instance và pluggable database

Trong multitenant architecture, CDB instance quản lý container database và các PDB. SHUTDOWN tác động tới instance/CDB, không phải lệnh chỉ đóng riêng một PDB.

Nếu mục tiêu là đóng một PDB nhưng giữ CDB instance chạy, dùng ALTER PLUGGABLE DATABASE:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
```

PDB close mode và cú pháp chi tiết phụ thuộc release. Đóng PDB không dừng listener hay instance; các PDB khác vẫn có thể hoạt động.

### 12.2. Shutdown toàn CDB

Khi kết nối với quyền quản trị vào CDB, SHUTDOWN NORMAL/TRANSACTIONAL/IMMEDIATE/ABORT tác động tới instance và các PDB đang được quản lý bởi instance đó. Chọn mode theo transaction/session toàn CDB, không chỉ theo một PDB.

### 12.3. PDB có session riêng

Trước khi close PDB, kiểm tra session trong container tương ứng và phối hợp application service kết nối tới PDB đó. Có thể dùng CDB views như CDB_PDBS/CDB_SERVICES hoặc GV$SESSION với CON_ID để xác định container. Cần quyền common user phù hợp.

### 12.4. PDB close không tương đương instance shutdown

| Thao tác | Phạm vi |
| --- | --- |
| ALTER PLUGGABLE DATABASE ... CLOSE | Đóng một hoặc nhiều PDB |
| SHUTDOWN ... | Đóng CDB/database và dừng instance |

Không shutdown cả CDB chỉ để deploy một ứng dụng trong một PDB nếu quy trình chỉ yêu cầu đóng PDB đó.

## 13. Shutdown trong RAC và Oracle Clusterware

### 13.1. Instance là đơn vị trên mỗi node

Trong RAC, nhiều instance cùng truy cập một database. Mỗi instance có SGA/process riêng, nhưng database files được chia sẻ. Shutdown một instance không đồng nghĩa shutdown toàn database; các instance còn lại có thể tiếp tục phục vụ.

### 13.2. Dùng SRVCTL cho tài nguyên do Clusterware quản lý

Với RAC/Oracle Restart, nên dùng SRVCTL để dừng instance/database/service theo resource management. Ví dụ minh họa dừng một instance:

```text
srvctl stop instance -db <db_unique_name> -instance <instance_name> -stopoption immediate
```

Hoặc dừng database resource:

```text
srvctl stop database -db <db_unique_name> -stopoption immediate
```

Các option và cú pháp chính xác thay đổi theo release. Kiểm tra srvctl help và Clusterware Administrator's Guide của phiên bản đang chạy trước khi thực hiện.

### 13.3. Vì sao không nên bỏ qua Clusterware?

Clusterware theo dõi trạng thái resource, dependency, service và restart policy. Nếu DBA dùng SQL*Plus shutdown trực tiếp trong khi Clusterware vẫn quản lý resource, Clusterware có thể đánh giá resource đã dừng ngoài dự kiến và thực hiện hành động theo policy.

Dùng SRVCTL giúp Clusterware biết ý định dừng và phối hợp service/instance đúng quy trình.

### 13.4. Shutdown một instance và service relocation

Trước khi dừng một RAC instance:

- Xác định service đang chạy trên instance đó.
- Drain hoặc relocate service theo policy.
- Kiểm tra số session còn lại và transaction đang hoạt động.
- Xác nhận instance còn lại đủ capacity.
- Kiểm tra FAN/ONS, connection pool và load balancing.

Nếu không có instance còn lại đủ tài nguyên, service relocation có thể làm node khác quá tải.

### 13.5. Shutdown toàn RAC database

Nếu cần dừng toàn bộ database, phối hợp stop service và dừng database resource theo thứ tự được Clusterware quản lý. Không chạy shutdown thủ công song song trên nhiều instance nếu runbook không yêu cầu; tránh các race condition giữa Clusterware và DBA.

### 13.6. TRANSACTIONAL LOCAL

Trong RAC, TRANSACTIONAL LOCAL có thể dùng khi cần shutdown instance và chỉ chờ transaction local của instance đó. Đánh giá tác động của transaction phân tán và service failover trước khi dùng; không giả định transaction trên instance khác không có liên hệ nghiệp vụ với công việc đang chạy.

## 14. Listener, services và connection pool

### 14.1. Listener không phải instance

Listener là process mạng tiếp nhận kết nối và chuyển request tới database service. SHUTDOWN instance không nhất thiết dừng listener. Listener có thể tiếp tục chạy và báo service không khả dụng khi instance đã dừng.

Không cần dừng listener trong mọi lần shutdown database. Nếu maintenance liên quan listener/network, đó là một bước riêng trong runbook.

### 14.2. Database services

Service là tên kết nối logic cho workload/PDB/role. Trong RAC, service có thể chạy trên một hoặc nhiều instance và được Clusterware quản lý.

Trước khi shutdown:

- Ngừng nhận request mới ở load balancer/API gateway.
- Drain service hoặc relocate service theo thiết kế.
- Cho connection pool ngừng mượn connection mới.
- Chờ request/transaction đang chạy theo SLA.
- Đóng connection idle theo policy.

### 14.3. Connection pool

Connection pool có thể giữ nhiều physical session ngay cả khi không có request. Đây là nguyên nhân thường làm NORMAL chờ lâu. Cấu hình pool cần có chế độ drain/stop và timeout hợp lý cho maintenance.

Không chỉ tắt web server nếu batch worker, scheduler hoặc integration service vẫn giữ connection tới database.

### 14.4. FAN/ONS và application failover

Trong RAC, Fast Application Notification (FAN) và Oracle Notification Service (ONS) có thể thông báo service/instance events để connection pool xử lý connection lỗi và failover. Hành vi thực tế phụ thuộc driver/pool và cấu hình. Kiểm thử failover/drain trước khi dùng cho maintenance quan trọng.

### 14.5. Stop service trước hay shutdown trước?

Thứ tự thông dụng là ngừng traffic mới, drain/stop service, chờ transaction/request theo policy, sau đó shutdown instance. Với RAC, service relocation có thể diễn ra thay vì stop hoàn toàn. Thứ tự cụ thể phụ thuộc kiến trúc ứng dụng và Clusterware.

## 15. Shutdown trong Data Guard

### 15.1. Xác định role

Trước khi shutdown, kiểm tra database role và open mode:

```sql
SELECT
    name,
    database_role,
    open_mode,
    protection_mode,
    switchover_status
FROM v$database;
```

Phân biệt PRIMARY, PHYSICAL STANDBY, LOGICAL STANDBY hoặc role khác được hỗ trợ. Không áp dụng runbook của primary cho standby mà không kiểm tra vai trò.

### 15.2. Shutdown primary

Shutdown primary làm dịch vụ database primary ngừng phục vụ. Standby có thể tiếp tục apply redo đã nhận, nhưng redo transport từ primary dừng khi primary không hoạt động. Sau khi primary trở lại, kiểm tra transport/apply lag và archive gap theo Data Guard runbook.

Shutdown không tự động thực hiện switchover hoặc failover.

### 15.3. Shutdown standby

Shutdown standby làm apply/redo processing trên standby tạm dừng. Primary có thể tiếp tục hoạt động, nhưng cần theo dõi transport destination, archive retention và khả năng bắt kịp khi standby trở lại.

### 15.4. Broker-managed configuration

Nếu dùng Data Guard Broker, thực hiện maintenance theo quy trình DGMGRL/Broker của tổ chức. Kiểm tra trạng thái configuration, transport/apply lag và role transition. Không thay đổi role hoặc disable broker chỉ để chạy một lệnh shutdown đơn giản nếu không có yêu cầu.

### 15.5. Switchover/failover là quy trình khác

Switchover/failover là chuyển role có kiểm soát hoặc khẩn cấp giữa primary và standby. SHUTDOWN chỉ dừng instance/database. Không dùng ABORT hay IMMEDIATE thay cho quy trình role transition.

## 16. Jobs, backup và công việc nền

### 16.1. Scheduler jobs

Job Scheduler có thể đang chạy khi shutdown được yêu cầu. Xem DBA_SCHEDULER_RUNNING_JOBS và phối hợp với job owner. Xác định job có thể dừng/retry an toàn hay phải hoàn tất.

### 16.2. DBMS_JOB và job queue

Các job legacy qua DBMS_JOB và job queue processes cũng có thể tạo session hoạt động. Tham số JOB_QUEUE_PROCESSES điều khiển worker job queue theo phạm vi/release. Không đặt về 0 trên production nếu chưa hiểu ảnh hưởng tới tất cả job và chưa có kế hoạch khôi phục giá trị.

### 16.3. RMAN và backup

Trước shutdown, xác định RMAN backup/restore, duplicate, block media recovery hoặc backup agent đang chạy. Shutdown có thể làm job bị gián đoạn; backup không hoàn tất cần được đánh dấu và xử lý theo backup policy.

### 16.4. Data Pump và external jobs

Data Pump job, external table process, external job hoặc integration task có thể có session/process bên ngoài. Dừng database không tự bảo đảm các tiến trình ngoài database đã cleanup đúng cách. Theo dõi job state và file/log của chúng.

### 16.5. Background processes

Oracle tự quản lý background processes như DBWn, LGWR, CKPT, SMON, PMON và ARCn. Không kill riêng các process này như một cách shutdown. Dùng SHUTDOWN/SRVCTL để Oracle kết thúc instance theo trình tự.

## 17. Runbook trước khi shutdown

### 17.1. Xác nhận đúng môi trường

Trước khi chạy lệnh:

- Xác định database name, DB_UNIQUE_NAME, instance name và host.
- Xác định single instance, RAC, Oracle Restart hay container.
- Xác định CDB/PDB và container hiện tại.
- Xác định database role nếu có Data Guard.
- Kiểm tra maintenance window, owner và người phê duyệt.
- Xác nhận đúng môi trường DEV/TEST/UAT/PROD.

Một lệnh shutdown chạy đúng cú pháp nhưng trên nhầm instance vẫn là sự cố nghiêm trọng.

### 17.2. Xác nhận trạng thái hiện tại

```sql
SELECT instance_name, host_name, status, database_status, startup_time
FROM v$instance;

SELECT name, db_unique_name, open_mode, database_role
FROM v$database;
```

Với RAC:

```sql
SELECT inst_id, instance_name, host_name, status
FROM gv$instance
ORDER BY inst_id;
```

### 17.3. Thông báo và drain traffic

Thông báo application owner, DBA on-call, monitoring và người dùng. Chặn request mới ở load balancer/API gateway, chuyển service sang maintenance hoặc drain, ngừng batch/job mới và chờ request đang chạy theo SLA.

Đảm bảo health check/monitoring không tự tạo lại connection trong lúc shutdown NORMAL.

### 17.4. Kiểm tra session và transaction

Chạy các truy vấn V$SESSION, V$TRANSACTION và DBA_SCHEDULER_RUNNING_JOBS ở phần trước. Xác định:

- Session của application pool.
- Transaction có lượng undo lớn.
- Batch/reporting/ETL đang chạy.
- Session quản trị/monitoring cần duy trì.
- Distributed transaction đang in-doubt.

Lưu output phục vụ audit/incident nếu policy cho phép; mask thông tin nhạy cảm.

### 17.5. Kiểm tra backup và Data Guard

Xác nhận backup/restore/Data Pump đang chạy, archive destination và standby lag. Nếu là Data Guard, kiểm tra role, transport/apply và quy trình Broker. Nếu là RAC, xác nhận service relocation/capacity và instance còn lại.

### 17.6. Chọn mode và thông báo hậu quả

Ghi rõ lý do chọn NORMAL, TRANSACTIONAL, IMMEDIATE hay ABORT. Nếu IMMEDIATE, thông báo có thể rollback transaction chưa commit. Nếu ABORT, thông báo startup sau đó cần instance recovery và outage có thể dài hơn.

### 17.7. Chuẩn bị startup và rollback kế hoạch

Trước maintenance, xác nhận:

- SPFILE/PFILE và password file hiện có.
- Storage, ASM, listener và Clusterware dependencies.
- Quy trình startup/verification.
- Người chịu trách nhiệm xác nhận application health.
- Kế hoạch nếu startup hoặc recovery không hoàn tất.

## 18. Thực hiện shutdown theo từng kịch bản

### 18.1. Kịch bản NORMAL

1. Drain application traffic.
2. Yêu cầu connection pool đóng physical connection.
3. Xác nhận session count giảm về 0 hoặc chỉ còn admin session cần thiết.
4. Kết nối administrative session riêng.
5. Chạy SHUTDOWN NORMAL.
6. Chờ command hoàn tất.
7. Xác nhận instance dừng và ghi nhận thời gian.

Nếu còn session, tìm owner và xử lý qua application/pool. Không tự động kill tất cả session chỉ để làm lệnh hoàn tất.

### 18.2. Kịch bản TRANSACTIONAL

1. Chặn request/transaction mới tại application/service layer.
2. Chạy SHUTDOWN TRANSACTIONAL.
3. Theo dõi V$TRANSACTION/V$SESSION từ một monitoring session hoặc công cụ giám sát phù hợp.
4. Cho transaction đang chạy hoàn tất.
5. Khi transaction kết thúc, Oracle disconnect clients và hoàn tất shutdown.

Không bắt đầu transaction mới trong lúc drain. Nếu transaction không tiến triển, phối hợp owner để quyết định tiếp tục chờ hay chuyển phương án.

### 18.3. Kịch bản IMMEDIATE

1. Thông báo application và chặn traffic mới.
2. Xác nhận có thể rollback transaction chưa commit.
3. Chạy SHUTDOWN IMMEDIATE.
4. Theo dõi alert log và thời gian rollback nếu command chưa hoàn tất.
5. Chờ Oracle đóng database và dừng instance.
6. Xác nhận shutdown sạch trước khi tiếp tục maintenance.

Không chạy ABORT ngay khi IMMEDIATE còn đang rollback nếu chưa đánh giá tác động và chưa có quyết định incident.

### 18.4. Kịch bản ABORT

1. Xác nhận instance cần dừng và lý do khẩn cấp.
2. Đánh giá client transaction cuối cùng có thể ở trạng thái không xác định đối với caller.
3. Chạy SHUTDOWN ABORT qua administrative connection nếu instance còn phản hồi.
4. Ghi nhận thời điểm abort và alert/trace.
5. Startup lại theo recovery runbook khi đã sẵn sàng.
6. Theo dõi instance recovery và xác nhận database open.
7. Đối chiếu các giao dịch nghiệp vụ cuối cùng bằng idempotency key/request ID.

ABORT không phải cách bỏ qua bước kiểm tra; nó chuyển công việc sang recovery ở startup tiếp theo.

## 19. Xác nhận instance đã shutdown

### 19.1. Output của SQL*Plus

Với clean shutdown, SQL*Plus thường hiển thị thông báo database closed, database dismounted và instance shut down. Output cụ thể có thể khác theo client/version.

ABORT thường kết thúc nhanh và không hiển thị cùng trình tự clean close. Không dựa riêng vào một dòng output; kiểm tra alert log và process/resource state.

### 19.2. Kết nối lại để kiểm tra

Sau khi instance đã dừng, query V$INSTANCE không thể chạy trên chính instance đó vì không còn instance để trả kết quả. Dùng OS process/Clusterware/SRVCTL và alert log để xác nhận.

Ví dụ trên RAC:

```text
srvctl status database -db <db_unique_name>
srvctl status instance -db <db_unique_name> -instance <instance_name>
```

Cú pháp cụ thể tùy release. Trên single instance, kiểm tra trạng thái Oracle process và alert log theo OS/runbook.

### 19.3. Kiểm tra listener và service

Listener có thể vẫn chạy sau shutdown. Kiểm tra service không còn được quảng bá từ instance đã dừng; trên RAC, service có thể đang chạy ở instance khác. Không kết luận instance còn mở chỉ vì listener process vẫn tồn tại.

### 19.4. Ghi nhận thời gian

Ghi lại:

- Thời điểm bắt đầu drain.
- Thời điểm chạy shutdown.
- Thời gian chờ session/transaction.
- Thời gian rollback nếu IMMEDIATE.
- Thời gian command hoàn tất.
- Mode được sử dụng.
- Số session/transaction còn lại ở thời điểm bắt đầu.

Số liệu này giúp cải thiện maintenance window và phát hiện connection leak.

## 20. Startup sau shutdown

### 20.1. Startup sau clean shutdown

Sau NORMAL, TRANSACTIONAL hoặc IMMEDIATE, kết nối administrative session và chạy:

```sql
STARTUP
```

Oracle khởi tạo instance, mount và open database theo startup command. Nếu cấu hình yêu cầu startup mount hoặc restricted, làm theo runbook tương ứng.

### 20.2. Startup sau ABORT

Sau ABORT:

```sql
STARTUP
```

Oracle tự thực hiện instance recovery nếu cần trong quá trình startup. Theo dõi alert log để biết recovery progress và lỗi phát sinh. Không chạy media recovery chỉ vì shutdown trước đó là ABORT; chỉ dùng khi có vấn đề file/media riêng.

### 20.3. STARTUP FORCE

STARTUP FORCE là lệnh kết hợp: nếu instance đang chạy, Oracle thực hiện shutdown abort rồi startup. Đây không phải một cách startup an toàn hơn và có thể tạo instance recovery. Chỉ dùng khi cần và hiểu rằng instance đang chạy sẽ bị abort.

### 20.4. Kiểm tra trạng thái sau startup

```sql
SELECT
    instance_name,
    status,
    database_status,
    startup_time
FROM v$instance;

SELECT
    name,
    open_mode,
    database_role
FROM v$database;
```

Xác nhận database open mode, role, PDB state, service registration, background process và alert log. Với RAC, xác nhận mọi instance/service đúng trạng thái mong muốn.

### 20.5. Xác minh application

Sau khi database open:

- Kiểm tra service đăng ký với listener/Clusterware.
- Kiểm tra connection pool có thể kết nối lại.
- Kiểm tra transaction test/read-only health check.
- Kiểm tra scheduler/job state.
- Kiểm tra Data Guard transport/apply nếu có.
- Theo dõi error rate, latency và wait events.

Chỉ mở traffic khi application owner xác nhận hệ thống hoạt động bình thường.

## 21. Lỗi thường gặp khi shutdown/startup

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-01031: insufficient privileges | Session không có quyền administrative phù hợp | Kết nối bằng quyền được cấp; không nâng quyền ứng dụng tùy tiện |
| ORA-01034: ORACLE not available | Instance chưa chạy hoặc đã shutdown | Kiểm tra ORACLE_SID, service và trạng thái instance |
| ORA-01089: immediate shutdown in progress | Instance đang trong quá trình shutdown | Chờ/kiểm tra tiến trình shutdown và alert log |
| ORA-01012: not logged on | Session bị disconnect hoặc instance đã dừng | Kết nối lại khi instance sẵn sàng |
| ORA-01033: initialization or shutdown in progress | Database đang startup/shutdown | Theo dõi alert log; không tạo thêm kết nối ứng dụng |
| SHUTDOWN NORMAL chờ mãi | Session idle/pool/monitor chưa disconnect | Drain traffic, tìm owner session và đóng connection đúng cách |
| SHUTDOWN TRANSACTIONAL chờ lâu | Transaction dài chưa commit/rollback | Tìm V$TRANSACTION, hỏi application owner và theo dõi tiến triển |
| SHUTDOWN IMMEDIATE chờ lâu | Rollback transaction lớn hoặc cleanup | Theo dõi undo/alert log, tránh abort vội |
| Startup sau ABORT mất lâu | Instance recovery đang chạy | Theo dõi alert log, I/O và recovery progress |
| ORA-04031/ORA-04030 sau startup | Memory pressure hoặc allocation issue | Kiểm tra SGA/PGA/OS; không quy kết chỉ do ABORT |
| ORA-01157/ORA-01110 khi startup | Datafile không truy cập được | Kiểm tra storage/path/ASM và media recovery runbook |
| Service không đăng ký sau startup | Listener/service/Clusterware chưa sẵn sàng | Kiểm tra LOCAL_LISTENER, service resource và alert log |
| RAC instance tự restart | Clusterware restart policy/resource management | Dùng SRVCTL và kiểm tra Clusterware logs |

### 21.1. ORA-01034 sau shutdown

Sau khi instance dừng, kết nối tới database có thể trả ORA-01034. Đây có thể là trạng thái dự kiến; xác nhận có phải maintenance đang diễn ra hay instance dừng ngoài kế hoạch trước khi startup.

### 21.2. ORA-01089 trong lúc shutdown

ORA-01089 thường cho biết immediate shutdown đang diễn ra. Application không nên retry liên tục vào instance trong lúc shutdown. DBA kiểm tra tiến trình và alert log để biết shutdown có tiến triển hay gặp lỗi.

### 21.3. Startup sau ABORT gặp lỗi file

Nếu startup báo datafile không truy cập được, đó là vấn đề storage/file availability cần xử lý riêng. Instance recovery không thể sửa một file bị mất hoặc thiết bị storage hỏng. Kiểm tra ASM/disk group, mount point và backup trước khi quyết định media recovery.

## 22. Bài lab: quan sát NORMAL và TRANSACTIONAL

Chỉ thực hiện trên database lab/dedicated instance có thể dừng. Không chạy bài lab shutdown trên shared development, UAT hoặc production. Cần hai terminal/session riêng và quyền quản trị phù hợp.

### 22.1. Chuẩn bị bảng

```sql
CREATE TABLE shutdown_lab (
    id NUMBER PRIMARY KEY,
    value_text VARCHAR2(100)
);

INSERT INTO shutdown_lab VALUES (1, 'before');
COMMIT;
```

### 22.2. Session A — giữ connection idle

Kết nối bằng user lab và để session A mở, không disconnect.

### 22.3. Session B — SHUTDOWN NORMAL

Kết nối quản trị ở terminal B và chạy:

```sql
SHUTDOWN NORMAL
```

Lệnh sẽ chờ session A disconnect. Quay lại session A và chạy EXIT/LOGOFF. Sau đó quan sát terminal B hoàn tất shutdown.

### 22.4. Startup lại

```sql
STARTUP
```

Xác nhận instance mở lại trước bài tiếp theo.

### 22.5. Session A — mở transaction

Trong session A:

```sql
UPDATE shutdown_lab
SET value_text = 'transactional-test'
WHERE id = 1;

-- Chưa COMMIT
```

### 22.6. Session B — SHUTDOWN TRANSACTIONAL

Trong terminal B, chạy:

```sql
SHUTDOWN TRANSACTIONAL
```

Command sẽ chờ transaction đang mở. Quay lại session A, chạy COMMIT. Oracle disconnect client sau khi transaction kết thúc và hoàn tất shutdown.

### 22.7. Startup và xác minh

```sql
STARTUP

SELECT * FROM shutdown_lab WHERE id = 1;
```

Giá trị đã commit phải còn sau startup. Lab minh họa transaction được phép hoàn tất trước khi instance dừng.

## 23. Bài lab: IMMEDIATE và ABORT

Chỉ chạy trên dedicated lab instance. ABORT mô phỏng instance failure và bắt buộc startup recovery. Không dùng để thử trên database dùng chung hoặc production.

### 23.1. Chuẩn bị transaction chưa commit

Sau khi instance đã startup và bảng SHUTDOWN_LAB còn tồn tại, trong session A:

```sql
UPDATE shutdown_lab
SET value_text = 'not-committed'
WHERE id = 1;

-- Không COMMIT
```

### 23.2. Session B — SHUTDOWN IMMEDIATE

Trong terminal quản trị B:

```sql
SHUTDOWN IMMEDIATE
```

Oracle disconnect session A và rollback transaction chưa commit. Khi command hoàn tất, reconnect bằng administrative account rồi STARTUP.

### 23.3. Kiểm tra sau IMMEDIATE

```sql
SELECT id, value_text
FROM shutdown_lab
WHERE id = 1;
```

Giá trị phải là giá trị đã commit trước transaction thử nghiệm, không phải not-committed. Clean shutdown IMMEDIATE không yêu cầu instance recovery do mode shutdown.

### 23.4. Session A — tạo transaction mới cho ABORT

Trong session A:

```sql
UPDATE shutdown_lab
SET value_text = 'abort-uncommitted'
WHERE id = 1;

-- Không COMMIT
```

### 23.5. Session B — SHUTDOWN ABORT

Trong terminal quản trị B:

```sql
SHUTDOWN ABORT
```

Instance dừng ngay; session A mất kết nối. Reconnect bằng administrative connection và chạy STARTUP. Theo dõi alert log để quan sát instance recovery.

### 23.6. Kiểm tra sau ABORT

```sql
SELECT id, value_text
FROM shutdown_lab
WHERE id = 1;
```

Giá trị chưa commit không được giữ như một transaction thành công. Oracle recovery xử lý các thay đổi chưa commit. Nếu cần kiểm tra sâu, xem alert log và recovery messages.

### 23.7. Bài học

- IMMEDIATE rollback transaction chưa commit trong clean shutdown.
- ABORT dừng trước khi clean rollback; startup sau đó thực hiện instance recovery.
- Cả hai mode đều không biến DML chưa commit thành committed.
- Client mất kết nối đúng thời điểm COMMIT có thể không biết chắc kết quả; application phải xác minh bằng request ID/idempotency key.

## 24. Quy tắc về client và transaction outcome

### 24.1. Client nhận lỗi không đồng nghĩa transaction đã rollback

Nếu network bị ngắt trong lúc COMMIT, client có thể không nhận được response dù database đã commit thành công. Đây là kết quả không xác định từ góc nhìn client, không thể kết luận bằng exception phía ứng dụng.

### 24.2. Dùng idempotency key

Với thao tác nghiệp vụ có thể retry, tạo request ID duy nhất và lưu cùng transaction nghiệp vụ. Khi client reconnect, tra cứu request ID để xác định thao tác đã commit hay chưa trước khi gửi lại.

### 24.3. Không retry mù quáng

Một request bị lỗi do shutdown có thể đã tạo side effect ở service ngoài database. Retry không có idempotency có thể tạo thanh toán, email hoặc order trùng. Thiết kế transaction/outbox và idempotent consumer nếu ứng dụng có side effect liên hệ thống.

### 24.4. Giao dịch phân tán

Nếu request dùng database link hoặc XA/JTA, transaction có thể cần transaction manager điều phối. DBA không nên force commit/rollback in-doubt transaction chỉ dựa trên việc instance vừa shutdown; phối hợp application transaction coordinator và DBA theo quy trình distributed transaction.

## 25. Checklist vận hành shutdown/startup

### 25.1. Trước shutdown

- [ ] Xác nhận DB_NAME, DB_UNIQUE_NAME, instance, host và môi trường.
- [ ] Xác nhận single instance/RAC/Oracle Restart và CDB/PDB.
- [ ] Kiểm tra database role nếu có Data Guard.
- [ ] Có maintenance window và thông báo stakeholder.
- [ ] Drain request mới, connection pool và service.
- [ ] Kiểm tra session, transaction, job, backup và Data Pump.
- [ ] Xác định transaction dài và distributed transaction.
- [ ] Chọn shutdown mode theo SLA và yêu cầu rollback.
- [ ] Chuẩn bị startup command, dependencies và rollback plan.

### 25.2. Trong shutdown

- [ ] Dùng đúng administrative connection và đúng instance.
- [ ] Theo dõi session/transaction nếu NORMAL/TRANSACTIONAL đang chờ.
- [ ] Theo dõi rollback nếu IMMEDIATE kéo dài.
- [ ] Nếu ABORT, ghi nhận incident và chuẩn bị instance recovery.
- [ ] Không kill OS process tùy tiện.
- [ ] Không để application/monitor tạo connection mới trong lúc drain.

### 25.3. Sau shutdown

- [ ] Xác nhận instance/resource đã dừng.
- [ ] Kiểm tra alert log và thời điểm shutdown hoàn tất.
- [ ] Với ABORT, ghi nhận recovery cần thiết ở startup sau.
- [ ] Xác nhận các service/listener/instance khác ở trạng thái mong muốn.
- [ ] Ghi lại thời gian và session/transaction còn tồn tại.

### 25.4. Sau startup

- [ ] Xác nhận V$INSTANCE và V$DATABASE.
- [ ] Kiểm tra alert log, recovery và file availability.
- [ ] Xác nhận PDB open state.
- [ ] Xác nhận RAC instance/service và Clusterware status.
- [ ] Xác nhận Data Guard transport/apply.
- [ ] Kiểm tra scheduler, backup và job state.
- [ ] Kiểm thử application connection và health checks.
- [ ] Chỉ mở traffic khi owner xác nhận dịch vụ ổn định.

## 26. Câu hỏi tự kiểm tra

1. SHUTDOWN không kèm mode mặc định là mode nào?
2. Vì sao NORMAL có thể chờ vô thời hạn?
3. NORMAL xử lý session idle như thế nào?
4. TRANSACTIONAL ngăn điều gì và chờ điều gì?
5. TRANSACTIONAL khác NORMAL ở cách disconnect client ra sao?
6. TRANSACTIONAL khác IMMEDIATE ở xử lý transaction chưa commit thế nào?
7. IMMEDIATE có chờ user tự disconnect không?
8. Vì sao IMMEDIATE có thể vẫn mất nhiều thời gian?
9. ABORT khác IMMEDIATE ở rollback và close database thế nào?
10. Vì sao startup sau ABORT cần instance recovery?
11. Instance recovery khác media recovery ra sao?
12. ABORT có tự động làm mất các transaction đã commit không?
13. Vì sao client có thể không biết COMMIT đã thành công khi connection bị mất?
14. Idempotency key giúp xử lý retry thế nào?
15. V$SESSION và V$TRANSACTION giúp xác định blocker ra sao?
16. Vì sao session INACTIVE vẫn có thể làm NORMAL chờ?
17. Khi nào nên dùng ALTER SYSTEM KILL SESSION?
18. Vì sao không nên kill -9 Oracle process?
19. SHUTDOWN CDB khác CLOSE PDB thế nào?
20. Vì sao RAC nên dùng SRVCTL cho resource do Clusterware quản lý?
21. TRANSACTIONAL LOCAL có mục đích gì trong RAC?
22. Listener có tự dừng khi database shutdown không?
23. Service drain và connection pool ảnh hưởng shutdown thế nào?
24. Shutdown primary ảnh hưởng redo transport Data Guard ra sao?
25. Vì sao switchover/failover là quy trình khác shutdown?
26. Cần kiểm tra gì trước khi dừng Scheduler/RMAN/Data Pump?
27. Sau ABORT cần xem alert log để biết điều gì?
28. Những gì phải xác minh trước khi mở lại application traffic?

## 27. Mô hình ghi nhớ

```text
SHUTDOWN REQUEST
       |
       +-- NORMAL
       |     Ngăn kết nối mới
       |     Chờ mọi user disconnect
       |
       +-- TRANSACTIONAL
       |     Ngăn transaction mới
       |     Chờ transaction hiện tại kết thúc
       |     Disconnect client sau đó
       |
       +-- IMMEDIATE
       |     Ngăn kết nối/transaction mới
       |     Kết thúc SQL đang chạy
       |     Rollback transaction chưa commit
       |     Clean close
       |
       +-- ABORT
             Dừng instance ngay
             Không clean rollback/close
             Instance recovery ở STARTUP
       |
       v
OPERATIONS
       |
       +-- Drain application/services
       +-- Check sessions and transactions
       +-- Monitor alert log and rollback
       +-- RAC -> SRVCTL / Clusterware
       +-- PDB -> ALTER PLUGGABLE DATABASE
       +-- Data Guard -> role/transport/apply checks
       |
       v
STARTUP AND VERIFY
       |
       +-- V$INSTANCE / V$DATABASE
       +-- Alert log / recovery
       +-- PDB / service / listener
       +-- Application health and idempotent retry
```

**Điểm cần nhớ:** NORMAL chờ user tự disconnect; TRANSACTIONAL chờ transaction đang chạy hoàn tất rồi disconnect client; IMMEDIATE hủy statement và rollback transaction chưa commit trước clean close; ABORT dừng ngay và để instance recovery xử lý ở startup kế tiếp. Chọn mode theo transaction semantics, maintenance deadline và kiến trúc RAC/CDB/Data Guard; luôn drain application và xác minh trạng thái sau shutdown/startup.
