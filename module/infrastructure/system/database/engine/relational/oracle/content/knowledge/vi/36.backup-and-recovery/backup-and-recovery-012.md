# Point-in-time recovery, RESETLOGS và database incarnation

Point-in-time recovery (PITR) là quá trình đưa Oracle Database trở về một thời điểm hoặc System Change Number (SCN) đã chọn. Kỹ thuật này thường được dùng khi dữ liệu bị xóa nhầm, một batch job ghi sai hàng loạt, một thay đổi ứng dụng gây hỏng dữ liệu logic hoặc cần khôi phục database về trạng thái trước một sự cố.

Trong Oracle, PITR toàn database thường được thực hiện bằng RMAN: chọn mốc đích, restore các datafile từ backup phù hợp, apply archived redo và incremental backup đến mốc đó, rồi mở database bằng RESETLOGS. Thao tác mở RESETLOGS tạo một nhánh redo mới, được Oracle gọi là một **database incarnation** mới.

Ba khái niệm cần hiểu cùng nhau:

- **PITR:** xác định database cần quay về mốc nào và phục hồi dữ liệu đến mốc đó.
- **RESETLOGS:** mở database sau incomplete recovery hoặc một số trường hợp recovery đặc biệt, đồng thời khởi tạo redo stream mới.
- **Database incarnation:** một nhánh lịch sử redo được xác định bởi các lần mở database bằng RESETLOGS.

PITR có thể làm mất các transaction đã commit sau mốc phục hồi trên toàn database. Vì vậy, chọn đúng SCN/time và xác định phạm vi phục hồi là quyết định quan trọng nhất trước khi chạy lệnh.

## 1. PITR là gì?

PITR đưa database về trạng thái nhất quán tại một mốc nằm trong quá khứ. Mốc đó có thể được xác định bằng:

- SCN.
- Thời gian (timestamp).
- Log sequence, trong một số kịch bản RMAN.
- Guaranteed restore point hoặc normal restore point làm mốc tham chiếu.

Ví dụ, một thao tác xóa nhầm được commit lúc 10:15. Nếu có backup và redo cần thiết, DBA có thể phục hồi database về một SCN ngay trước transaction đó. Những thay đổi hợp lệ được commit sau SCN này cũng sẽ không còn trong database sau khi PITR hoàn tất.

PITR không phải là một thao tác undo riêng một câu SQL. Khi thực hiện whole database point-in-time recovery, tất cả datafile thuộc database được đưa về cùng một mốc nhất quán. Điều đó có thể ảnh hưởng nhiều schema và ứng dụng đang dùng chung database.

### 1.1 Các loại point-in-time recovery

Oracle có nhiều cách phục hồi theo thời điểm, tùy phạm vi:

| Loại | Phạm vi | Tác động chính |
|---|---|---|
| Database PITR (DBPITR) | Toàn database | Đưa toàn bộ database về một mốc; sau đó mở RESETLOGS |
| Tablespace PITR (TSPITR) | Một hoặc nhiều tablespace | Phục hồi tablespace qua auxiliary instance, database chính vẫn tiếp tục ở hiện tại |
| PDB PITR | Một pluggable database trong CDB | Phục hồi PDB theo quy trình multitenant; không áp dụng nguyên xi quy trình whole CDB |
| Flashback Database | Toàn database hoặc phạm vi được hỗ trợ | Dùng flashback logs để đưa database về mốc trước đó |
| Flashback Table | Một hoặc nhiều bảng | Đưa bảng về trạng thái trước đó nếu điều kiện và undo cho phép |

DBPITR phù hợp khi cần khôi phục trạng thái nhất quán của toàn database. Nếu chỉ một bảng hoặc một tablespace bị ảnh hưởng, TSPITR, Flashback Table, RMAN RECOVER TABLE hoặc phương án khôi phục đối tượng riêng lẻ có thể giảm tác động đến các giao dịch không liên quan.

PDB PITR có cú pháp và điều kiện riêng cho môi trường multitenant. Cần phân biệt rõ đang phục hồi CDB hay một PDB; không dùng lệnh ALTER DATABASE OPEN RESETLOGS của whole database như thể đó là toàn bộ quy trình cho mọi trường hợp PDB.

### 1.2 PITR khác complete recovery như thế nào?

**Complete recovery** áp dụng tất cả redo cần thiết để đưa datafile đến trạng thái hiện tại hoặc đến mức mới nhất có thể phục hồi, không chủ động dừng ở một mốc quá khứ.

**Incomplete recovery** dừng trước khi áp dụng toàn bộ redo có sẵn. PITR là một dạng incomplete recovery khi dùng RMAN restore/recover đến một target time hoặc SCN.

| Tiêu chí | Complete recovery | Incomplete recovery / PITR |
|---|---|---|
| Mục tiêu | Phục hồi đến hiện tại hoặc điểm mới nhất | Phục hồi đến mốc quá khứ đã chọn |
| Redo | Áp dụng toàn bộ redo cần thiết | Dừng tại target |
| Transaction sau target | Được giữ nếu redo hợp lệ | Bị loại khỏi trạng thái database sau target |
| Mở database | Thường không cần RESETLOGS nếu không có điều kiện đặc biệt | Thường phải OPEN RESETLOGS |
| Incarnation | Tiếp tục nhánh hiện tại | Tạo nhánh mới khi mở RESETLOGS |

Nếu recovery dùng backup control file hoặc thực hiện incomplete recovery, database thường cần mở RESETLOGS. Hãy xác định rõ loại recovery và control file đang sử dụng trước khi quyết định lệnh mở database.

## 2. SCN và thời gian phục hồi

SCN (System Change Number) là số thứ tự logic Oracle dùng để định vị các thay đổi trong database. SCN là mốc chính xác hơn timestamp khi cần xác định ranh giới recovery.

### 2.1 Chọn target SCN

Khi biết SCN trước transaction gây lỗi, có thể dùng target SCN để phục hồi:

~~~sql
SELECT current_scn
FROM v$database;
~~~

Lệnh trên chỉ cho biết SCN hiện tại tại thời điểm truy vấn. Trong điều tra sự cố, cần lấy SCN từ nguồn đáng tin cậy: log ứng dụng, audit record, LogMiner, transaction investigation, restore point hoặc thông tin vận hành đã ghi lại.

Ví dụ, nếu cần dừng recovery tại SCN 987654321:

~~~rman
RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Target SCN là ranh giới recovery. Hãy đọc cú pháp UNTIL SCN trong tài liệu RMAN của release đang dùng và kiểm tra kết quả thực tế quanh ranh giới, đặc biệt khi xác định một transaction cụ thể. Không nên lấy SCN bất kỳ chỉ vì nó gần thời điểm sự cố.

### 2.2 Chọn target time

RMAN cũng cho phép chỉ định thời gian:

~~~rman
RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 09:30:00','YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Dùng TO_DATE với format rõ ràng giúp tránh phụ thuộc NLS_DATE_FORMAT. Cần xác định timezone của thời điểm sự cố và cách timestamp được ghi bởi ứng dụng/database. DATE không chứa timezone, do đó cần thống nhất giờ máy chủ, giờ ứng dụng và giờ người điều tra.

Khi sự cố xảy ra sát một thời điểm, timestamp có thể không đủ chính xác để phân biệt các transaction liên tiếp. Nếu có thể, hãy tìm SCN tương ứng và dùng SCN làm mốc.

### 2.3 Chuyển đổi SCN và timestamp

Oracle cung cấp các hàm:

~~~sql
SELECT SCN_TO_TIMESTAMP(987654321)
FROM dual;

SELECT TIMESTAMP_TO_SCN(
         TO_TIMESTAMP('2026-11-14 09:30:00',
                      'YYYY-MM-DD HH24:MI:SS')
       )
FROM dual;
~~~

Các hàm này dựa trên mapping SCN/time mà Oracle lưu giữ trong một khoảng thời gian giới hạn. Không nên giả định mapping tồn tại vô thời hạn hoặc luôn có độ chính xác tuyệt đối cho mọi thời điểm cũ. TIMESTAMP_TO_SCN có thể không tìm được mapping cho timestamp ngoài phạm vi được lưu giữ.

Khi cần phục hồi từ một sự kiện lịch sử, ưu tiên nguồn SCN đã được ghi nhận tại thời điểm xảy ra sự kiện. Nếu chỉ có timestamp, dùng RMAN SET UNTIL TIME và kiểm tra mốc kết quả bằng dữ liệu thực tế.

### 2.4 Target phải có thể phục hồi

Để phục hồi đến target, cần có:

- Backup datafile đủ cũ để bắt đầu recovery.
- Archived redo log liên tục từ backup đến target.
- Incremental backup nếu quy trình dựa vào incremental.
- Control file hoặc recovery catalog chứa metadata phù hợp.
- SPFILE/parameter file và password file khi cần khởi động instance.
- Tất cả redo thread liên quan nếu database chạy RAC.

Nếu thiếu archived redo cần thiết, database không thể áp dụng các thay đổi vượt qua khoảng trống đó. DBA có thể phải chọn target sớm hơn, tìm bản archived log trong backup hoặc nguồn lưu trữ khác, hoặc dùng một phương án phục hồi khác.

## 3. Khi nào nên dùng PITR?

Một số tình huống điển hình:

- Người dùng xóa hoặc cập nhật nhầm dữ liệu rồi commit.
- Batch job chạy sai logic và ghi hàng loạt dữ liệu không đúng.
- Deployment làm thay đổi dữ liệu theo cách không thể đảo ngược bằng thao tác ứng dụng.
- Một schema hoặc nhóm dữ liệu bị hỏng logic và cần dựng lại trạng thái trước sự cố.
- Cần phục hồi một môi trường kiểm thử về mốc đã biết.
- Cần tạo bản sao database tại thời điểm trước khi một sự kiện xảy ra.

Không phải mọi lỗi dữ liệu đều cần DBPITR. Nếu chỉ một bảng bị ảnh hưởng, đưa toàn bộ database về quá khứ có thể làm mất các transaction hợp lệ của mọi ứng dụng khác.

Trước khi chọn DBPITR, hãy cân nhắc:

- Flashback Table nếu undo và điều kiện hỗ trợ còn đủ.
- Flashback Database nếu flashback logs còn trong phạm vi cần thiết.
- RMAN RECOVER TABLE để phục hồi một bảng sang schema hoặc database phụ.
- Tablespace PITR nếu lỗi nằm trong một tablespace và cấu trúc phụ thuộc cho phép.
- Data Pump hoặc bản sao phục hồi để trích xuất dữ liệu rồi hợp nhất vào database hiện tại.
- Khôi phục logic từ application log hoặc nguồn dữ liệu có kiểm soát.

## 4. Điều kiện và chuẩn bị trước DBPITR

PITR là thao tác có ảnh hưởng rộng. Trước khi thực hiện, cần chuẩn bị cả kỹ thuật và nghiệp vụ.

### 4.1 Database ở ARCHIVELOG mode

Whole database PITR dựa vào archived redo để áp dụng thay đổi từ backup đến target. Database production thường cần được cấu hình ARCHIVELOG và có quy trình backup archive log.

Kiểm tra:

~~~sql
SELECT name, log_mode, open_mode, current_scn
FROM v$database;
~~~

Nếu database đang ở NOARCHIVELOG, khả năng phục hồi phụ thuộc nhiều hơn vào backup offline hoặc các bản backup nhất quán. Không thể giả định rằng có thể PITR đến bất kỳ thời điểm nào nếu không có redo cần thiết.

### 4.2 Xác nhận backup có thể dùng

Trong RMAN:

~~~rman
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
~~~

Có thể dùng RESTORE DATABASE PREVIEW để xem RMAN dự kiến dùng backup nào cho một kịch bản restore. RESTORE ... VALIDATE giúp kiểm tra khả năng đọc backup piece mà không ghi đè datafile đích.

Ví dụ:

~~~rman
RESTORE DATABASE VALIDATE;
~~~

Lệnh này không thay thế một buổi diễn tập recovery hoàn chỉnh. Backup có thể đọc được nhưng vẫn thiếu archived log, control file hoặc các thành phần cần thiết khác cho target cụ thể.

### 4.3 Kiểm tra archived redo log

Có thể xem metadata archived log:

~~~sql
SELECT thread#,
       sequence#,
       first_change#,
       next_change#,
       resetlogs_change#,
       name,
       deleted,
       status
FROM v$archived_log
ORDER BY thread#, sequence#;
~~~

Cần kiểm tra tính liên tục của redo trong từng thread và đúng incarnation. Trong RAC, mỗi redo thread có sequence riêng. Một khoảng trống ở thread đang hoạt động có thể ngăn recovery đến target.

Một số bản ghi V$ARCHIVED_LOG có thể trùng do nhiều bản copy của cùng một sequence. Cần xem NAME, STATUS, DELETED, backup metadata và nguồn lưu trữ thực tế, không chỉ đếm số dòng trong view.

### 4.4 Bảo toàn trạng thái hiện tại

Trước khi đưa database về quá khứ, nên giữ một bản sao trạng thái hiện tại nếu có thể:

- Backup database và archived redo hiện tại.
- Ghi lại SQL_ID/SCN, thời điểm và mô tả sự cố.
- Lưu bản sao control file và SPFILE theo quy trình.
- Ghi nhận cấu hình, incarnation và danh sách datafile/tablespace.
- Nếu đủ tài nguyên, dựng một auxiliary database để kiểm tra target hoặc trích xuất dữ liệu.

Bản sao trạng thái hiện tại giúp phục hồi các transaction hợp lệ sau target nếu nghiệp vụ cần hợp nhất chúng lại. Không nên bắt đầu DBPITR trước khi xác định cách xử lý các giao dịch phát sinh sau mốc recovery.

### 4.5 Kiểm tra không gian lưu trữ và đường dẫn

RMAN cần đủ dung lượng cho restored datafile, archived redo, backup piece và khu vực auxiliary nếu dùng. Kiểm tra FRA, diskgroup ASM, filesystem, quyền ghi, tên file và mapping datafile.

Nếu dùng SET NEWNAME, DB_FILE_NAME_CONVERT hoặc SWITCH DATAFILE ALL, hãy xác nhận đường dẫn mới không đè lên file thuộc database khác.

## 5. Quy trình whole database PITR bằng RMAN

Quy trình phổ biến gồm các bước:

1. Chọn target SCN hoặc time.
2. Xác nhận backup và redo cần thiết.
3. Dừng ứng dụng và database.
4. Khởi động database ở MOUNT.
5. Đặt target bằng SET UNTIL.
6. Restore database.
7. Recover database đến target.
8. Mở database bằng RESETLOGS.
9. Kiểm tra database và ứng dụng.
10. Backup lại sau RESETLOGS.

Ví dụ dưới đây giả định control file hiện tại còn sử dụng được, database có backup phù hợp và archived redo liên tục.

### 5.1 Dừng database và mount

Trong SQL*Plus với quyền SYSDBA:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

Nếu database đã mount, không cần khởi động lại. Không để ứng dụng tiếp tục ghi dữ liệu trong khi đang thực hiện whole database PITR.

### 5.2 Restore và recover đến SCN

Kết nối RMAN:

~~~text
rman target /
~~~

Chạy:

~~~rman
RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

SET UNTIL phải được đặt trước RESTORE để RMAN chọn backup phù hợp với target, sau đó cũng áp dụng giới hạn đó cho recovery trong RUN block.

RMAN restore các datafile từ backup và apply incremental/archived redo theo khả năng của repository và nguồn backup. Thông báo RMAN cho biết backup piece và archived log nào được dùng.

Nếu dùng target time, thay SET UNTIL SCN bằng SET UNTIL TIME với biểu thức thời gian rõ ràng.

### 5.3 Mở RESETLOGS

Sau khi recovery hoàn tất đến target, thoát RMAN và mở database:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Sau incomplete recovery, OPEN RESETLOGS tạo redo branch mới. Database không tiếp tục ghi redo trên cùng nhánh cũ như trước.

Nếu recovery được thực hiện với backup control file, yêu cầu RESETLOGS cũng thường áp dụng. Luôn xác định đúng trạng thái control file và kiểu recovery trước khi mở.

### 5.4 Kiểm tra sau khi mở

~~~sql
SELECT name,
       open_mode,
       log_mode,
       resetlogs_change#,
       resetlogs_time,
       current_scn
FROM v$database;
~~~

Kiểm tra datafile:

~~~sql
SELECT file#,
       name,
       status,
       checkpoint_change#
FROM v$datafile
ORDER BY file#;
~~~

Kiểm tra tablespace:

~~~sql
SELECT tablespace_name,
       status,
       contents
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

Ngoài trạng thái database, cần kiểm tra invalid objects, job, sequence, application service, quyền, database link và dữ liệu nghiệp vụ tại mốc đã chọn. Một database OPEN không tự chứng minh mọi ứng dụng đã sẵn sàng.

## 6. Ví dụ PITR theo thời gian

Giả sử một batch chạy sai lúc 09:30 và commit nhiều thay đổi. Điều tra xác định dữ liệu cần giữ đến trước 09:30:00.

Sau khi xác nhận backup và archived log, DBA có thể thực hiện:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

RMAN:

~~~rman
RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 09:29:59','YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Mở database:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Thời gian trong ví dụ chỉ minh họa. Trong thực tế cần xác nhận timezone và ranh giới transaction. Nếu batch có nhiều commit, target 09:29:59 có thể không đủ để xác định chính xác transaction nào cần loại bỏ. SCN từ LogMiner, audit hoặc ứng dụng thường giúp chọn target chính xác hơn.

### 6.1 Kiểm tra dữ liệu sau recovery

Không chỉ kiểm tra rằng các dòng bị xóa đã xuất hiện lại. Hãy kiểm tra cả các transaction hợp lệ ngay trước target và xác nhận các transaction sau target đã bị loại bỏ như dự kiến.

Nên có truy vấn đối soát theo nghiệp vụ:

- Tổng số đơn hàng theo trạng thái.
- Tổng số tiền theo ngày hoặc đơn vị.
- Số lượng giao dịch trong khoảng thời gian.
- Các khóa ngoại và quan hệ giữa bảng.
- Các bản ghi do batch/job đã tác động.
- Dữ liệu đồng bộ sang hệ thống bên ngoài.

Đặc biệt, database PITR không tự khôi phục các hệ thống ngoài Oracle như message queue, cache, file export, báo cáo đã gửi hoặc giao dịch ở database khác. Cần kế hoạch đồng bộ hoặc bù trừ cho các hệ thống liên quan.

## 7. PITR khi control file bị mất

Nếu control file hiện tại bị mất, cần khôi phục control file từ backup hoặc autobackup trước khi mount và recovery. Đây là tình huống disaster recovery, có thêm bước so với ví dụ sử dụng control file hiện tại.

Quy trình khái quát:

1. Xác định DBID của database.
2. Khởi động instance NOMOUNT với SPFILE/PFILE phù hợp.
3. Cấu hình vị trí autobackup nếu cần.
4. Restore control file từ autobackup.
5. Mount database.
6. Đặt target và restore/recover datafile.
7. Mở RESETLOGS.

Ví dụ khung lệnh RMAN:

~~~rman
rman target /

SET DBID 1234567890;

STARTUP NOMOUNT;

RESTORE CONTROLFILE FROM AUTOBACKUP;

ALTER DATABASE MOUNT;

RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Sau đó trong SQL*Plus:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Đây là khung minh họa, không phải runbook dùng nguyên trạng cho mọi hệ thống. Khi control file bị mất, cần xác định autobackup format, DBID, vị trí backup, cấu hình channel, SPFILE, ASM và quyền truy cập. Nếu RMAN không tự tìm được autobackup, có thể phải chỉ định format hoặc handle cụ thể.

Khi dùng backup control file, metadata về backup/archived log mới nhất có thể không nằm trong control file được restore. Recovery catalog hoặc catalog backup piece và archived log có thể cần thiết để RMAN tìm đầy đủ chuỗi redo.

## 8. Vì sao phải OPEN RESETLOGS?

Sau incomplete recovery, database không có toàn bộ redo cần thiết để tiếp tục nhánh cũ đến hiện tại. OPEN RESETLOGS xác lập một điểm bắt đầu mới cho redo.

Khi mở RESETLOGS, Oracle:

- Tạo redo stream mới.
- Reset log sequence theo nhánh mới.
- Ghi nhận resetlogs SCN và resetlogs time.
- Tạo database incarnation mới.
- Giữ quan hệ với incarnation cha trong metadata để RMAN quản lý lịch sử phục hồi.

RESETLOGS không đổi DBID trong thao tác thông thường. DBID nhận diện database; incarnation nhận diện một nhánh lịch sử redo của database đó. Không nhầm incarnation mới với việc tạo một database hoàn toàn mới.

### 8.1 RESETLOGS không phải lệnh xóa toàn bộ dữ liệu

Tên lệnh có thể khiến người mới nghĩ Oracle xóa redo hoặc dữ liệu. Thực tế, RESETLOGS là thao tác mở database sau recovery theo quy tắc redo mới. Datafile chứa trạng thái đã phục hồi tại target; Oracle khởi tạo redo logs để database tiếp tục hoạt động trên nhánh mới.

Không dùng RESETLOGS để thử xem database có mở được không. Đây là ranh giới quan trọng trong lịch sử recovery. Hãy chỉ mở sau khi đã xác nhận restore/recovery hoàn tất và trạng thái database phù hợp.

### 8.2 Khi nào cần RESETLOGS?

Các trường hợp thường yêu cầu OPEN RESETLOGS:

- Incomplete recovery, bao gồm DBPITR.
- Recovery sử dụng backup control file.
- Một số quy trình Flashback Database về quá khứ.
- Các tình huống recovery đặc biệt được Oracle yêu cầu resetlogs.

Complete recovery với current control file thường mở database bình thường, không cần RESETLOGS. Không nên áp dụng RESETLOGS cho mọi lần recover.

## 9. Database incarnation là gì?

Một database incarnation là một nhánh lịch sử redo bắt đầu tại một lần OPEN RESETLOGS. Mỗi incarnation có:

- Incarnation number.
- Resetlogs SCN.
- Resetlogs timestamp.
- Quan hệ với incarnation trước đó (parent/ancestor).
- Redo branch riêng sau điểm resetlogs.

Hãy hình dung lịch sử database như một cây:

~~~text
Incarnation 1
    |
    | OPEN RESETLOGS tại SCN 5000
    v
Incarnation 2
    |
    | OPEN RESETLOGS tại SCN 8200
    v
Incarnation 3
~~~

Ví dụ, database chạy trong incarnation 1 đến SCN 5000. DBA thực hiện PITR về SCN 4500 và mở RESETLOGS. Từ đó incarnation 2 bắt đầu. Các thay đổi được tạo sau SCN 4500 trên incarnation 1 không thuộc nhánh redo mới của incarnation 2.

Nếu sau đó lại phục hồi incarnation 2 về SCN 7000 và mở RESETLOGS, incarnation 3 được tạo. Incarnation 1 và 2 vẫn là các ancestor trong lịch sử, nhưng database hiện tại đang hoạt động trên nhánh 3.

### 9.1 Xem incarnation hiện tại

Trong SQL:

~~~sql
SELECT incarnation#,
       resetlogs_change#,
       resetlogs_time,
       prior_incarnation#,
       status
FROM v$database_incarnation
ORDER BY incarnation#;
~~~

Trong RMAN:

~~~rman
LIST INCARNATION OF DATABASE;
~~~

RMAN thường đánh dấu incarnation hiện tại là CURRENT. Các incarnation khác có thể có trạng thái PARENT hoặc ORPHAN tùy quan hệ và trạng thái repository.

Các cột và trạng thái hiển thị cần được kiểm tra theo release. Khi cần xác định nhánh, hãy đối chiếu incarnation number với resetlogs SCN/time, không chỉ nhìn số thứ tự.

### 9.2 DBID và incarnation khác nhau

| Thuộc tính | DBID | Incarnation |
|---|---|---|
| Mục đích | Nhận diện database | Nhận diện nhánh redo |
| Thay đổi khi OPEN RESETLOGS? | Thông thường không | Có, tạo incarnation mới |
| Dùng trong RMAN | Nhận diện repository/database | Chọn nhánh lịch sử khi restore/recover |
| Phạm vi | Database identity | Một nhánh trong lịch sử database |

DBID có thể thay đổi trong các thao tác như NID để đổi database identity, nhưng đó là thao tác riêng và không phải hệ quả thông thường của RESETLOGS.

## 10. RMAN quản lý incarnation như thế nào?

RMAN lưu quan hệ giữa các incarnation trong control file hoặc recovery catalog. Nhờ đó, RMAN có thể nhận diện backup và archived redo thuộc nhánh nào.

Một số lệnh thường dùng:

~~~rman
LIST INCARNATION OF DATABASE;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST ARCHIVELOG ALL;
~~~

Khi database mở RESETLOGS, RMAN ghi nhận incarnation mới. Các backup cũ không tự động vô dụng. RMAN có thể sử dụng backup thuộc incarnation cha nếu chúng là tổ tiên hợp lệ của nhánh recovery và chuỗi redo phù hợp.

Tuy nhiên, không nên giả định mọi archived log hoặc backup từ nhánh cũ đều có thể áp dụng lên nhánh mới. Sau điểm RESETLOGS, redo của các nhánh song song không thể trộn lẫn tùy ý. Cần dùng incarnation metadata và RMAN để chọn đúng chuỗi.

### 10.1 Chuyển RMAN về incarnation cha

Nếu cần phục hồi đến một mốc nằm trên incarnation cũ, RMAN có thể cần chuyển recovery context về incarnation đó:

~~~rman
LIST INCARNATION OF DATABASE;

RESET DATABASE TO INCARNATION 2;
~~~

Trong ví dụ, 2 là incarnation number lấy từ kết quả LIST, không phải số cố định cho mọi database.

Lệnh này thay đổi incarnation mà RMAN dùng làm ngữ cảnh cho các thao tác restore/recover. Nó không phải lệnh tùy tiện để chuyển database đang mở sang một nhánh khác; hãy thực hiện trong quy trình recovery phù hợp, thường với database đã mount và có control file/recovery catalog chứa incarnation tree.

Sau khi chọn đúng incarnation, đặt target SCN/time nằm trong nhánh đó, restore/recover bằng backup và redo tương ứng, rồi mở RESETLOGS nếu quy trình yêu cầu. Khi mở, một incarnation mới có thể được tạo từ nhánh đã chọn.

### 10.2 Khi nào cần RESET DATABASE TO INCARNATION?

Một số tình huống:

- Đã mở RESETLOGS sau PITR và sau đó phát hiện cần quay lại một mốc trước lần RESETLOGS đó.
- Cần phục hồi một nhánh ancestor để lấy lại trạng thái hoặc dữ liệu cũ.
- Cần RMAN nhận diện backup và archived log thuộc nhánh cũ khi target nằm trước resetlogs SCN của incarnation hiện tại.

Không dùng lệnh này chỉ để khắc phục một lỗi backup chung chung. Trước tiên phải xác định target nằm trên nhánh nào và backup/redo của nhánh đó còn đủ hay không.

### 10.3 Incarnation ORPHAN

Một incarnation có thể được hiển thị là ORPHAN khi nó không còn nằm trên nhánh hiện tại được RMAN chọn làm đường đi active, ví dụ sau các lần resetlogs tạo nhánh khác. ORPHAN không đồng nghĩa backup thuộc incarnation đó đã bị xóa hoặc chắc chắn không dùng được.

RMAN có thể phục hồi từ một ancestor/nhánh cũ nếu chọn đúng incarnation và có đủ backup/redo. Hãy xem quan hệ resetlogs SCN/time và kiểm tra khả năng restore/recover cụ thể.

## 11. Backup sau RESETLOGS

Sau khi mở RESETLOGS thành công, nên thực hiện một backup mới của database và archived redo theo chính sách vận hành.

Lý do:

- Database đang chạy trên incarnation mới.
- Backup mới tạo điểm khôi phục rõ ràng cho nhánh mới.
- Giảm phụ thuộc vào việc ghép backup/redo từ các nhánh cũ.
- Đơn giản hóa quy trình disaster recovery tiếp theo.
- Tạo bằng chứng rằng backup sau recovery đọc được và có thể dùng.

Ví dụ:

~~~rman
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Tùy chính sách, có thể cần backup control file và SPFILE riêng hoặc cấu hình autobackup:

~~~rman
CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Kiểm tra cấu hình hiện tại:

~~~rman
SHOW ALL;
~~~

Một số hệ thống dùng backup optimization, compression, encryption, SBT hoặc media manager. Cần bảo đảm backup sau RESETLOGS được ghi vào đúng repository và retention policy không xóa mất các backup cần thiết.

Sau backup, nên kiểm tra:

~~~rman
LIST BACKUP SUMMARY;
RESTORE DATABASE VALIDATE;
~~~

RESTORE ... VALIDATE kiểm tra khả năng đọc backup, nhưng vẫn cần diễn tập recovery định kỳ để chứng minh toàn bộ quy trình hoạt động.

## 12. PITR và Flashback Database

Flashback Database là cơ chế đưa database về một thời điểm trước đó bằng flashback logs. Nó có thể nhanh hơn việc restore toàn bộ datafile và apply archived redo từ backup, nếu flashback logs còn đủ cho target.

Ví dụ khung lệnh:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO SCN 987654321;

ALTER DATABASE OPEN RESETLOGS;
~~~

Hoặc:

~~~sql
FLASHBACK DATABASE TO TIMESTAMP
  TO_TIMESTAMP('2026-11-14 09:30:00',
               'YYYY-MM-DD HH24:MI:SS');
~~~

Cú pháp cụ thể và trạng thái database cần tuân theo tài liệu phiên bản Oracle. Flashback Database thường thực hiện khi database ở MOUNT. Sau khi flashback về quá khứ, database được mở RESETLOGS để tạo redo branch mới.

### 12.1 Flashback logs và Fast Recovery Area

Flashback Database cần được bật và có flashback logs phù hợp. Kiểm tra:

~~~sql
SELECT flashback_on
FROM v$database;

SELECT name,
       space_limit,
       space_used,
       space_reclaimable
FROM v$recovery_file_dest;
~~~

DB_FLASHBACK_RETENTION_TARGET đặt mục tiêu retention, nhưng không nên xem nó là bảo đảm rằng mọi target time đều có flashback logs. Dung lượng FRA, workload, archived logs và guaranteed restore point có thể ảnh hưởng khả năng giữ flashback logs.

### 12.2 Guaranteed restore point

Guaranteed restore point có thể bảo đảm Oracle giữ đủ flashback logs để flashback database về mốc đó, với điều kiện FRA có đủ dung lượng và cấu hình phù hợp.

Tạo restore point:

~~~sql
CREATE RESTORE POINT BEFORE_RELEASE GUARANTEE FLASHBACK DATABASE;
~~~

Xem restore point:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database
FROM v$restore_point;
~~~

Sau khi không còn cần, có thể xóa restore point:

~~~sql
DROP RESTORE POINT BEFORE_RELEASE;
~~~

Guaranteed restore point có thể giữ flashback logs và làm FRA tăng nhanh. Cần giám sát dung lượng, đặt thời hạn và xóa khi đã hoàn tất mục đích. Nó không thay thế backup RMAN.

### 12.3 So sánh Flashback Database và RMAN DBPITR

| Tiêu chí | Flashback Database | RMAN DBPITR |
|---|---|---|
| Cơ chế | Áp dụng flashback logs để đảo ngược thay đổi | Restore backup rồi apply redo đến target |
| Phụ thuộc | Flashback Database bật và logs còn đủ | Backup và archived redo liên tục |
| Thời gian | Có thể nhanh nếu target gần và flashback logs sẵn có | Có thể lâu nếu restore nhiều datafile |
| Phạm vi | Toàn database | Toàn database |
| RESETLOGS | Thường cần sau khi flashback về quá khứ | Cần sau incomplete recovery |
| Vai trò backup | Không thay thế backup | Dựa trực tiếp vào backup và redo |

Nếu flashback logs không đủ hoặc database bị mất datafile nghiêm trọng, RMAN restore/recover vẫn là phương án chính. Nên có cả backup và flashback theo yêu cầu RPO/RTO.

## 13. PITR và TSPITR: tránh phục hồi quá rộng

Tablespace Point-in-Time Recovery cho phép đưa một hoặc nhiều tablespace về thời điểm quá khứ trong khi phần còn lại của database tiếp tục ở trạng thái hiện tại.

RMAN thường dùng auxiliary instance để phục hồi tablespace đến target rồi đưa các datafile đã phục hồi về database chính. Quy trình có thêm yêu cầu về auxiliary destination, dung lượng và quan hệ phụ thuộc giữa tablespace.

Ví dụ khung lệnh:

~~~rman
RECOVER TABLESPACE users
  UNTIL SCN 987654321
  AUXILIARY DESTINATION '/u02/aux';
~~~

Cú pháp và giới hạn phụ thuộc phiên bản Oracle. TSPITR không phải lúc nào cũng phù hợp nếu object có dependency qua nhiều tablespace, foreign key, partitioning hoặc cấu trúc dữ liệu liên quan. Cần kiểm tra self-containment và yêu cầu recovery của tablespace trước khi thực hiện.

Nếu chỉ cần một bảng, có thể cân nhắc RMAN RECOVER TABLE hoặc phục hồi vào auxiliary database rồi trích xuất dữ liệu. Việc chọn phương án phải cân bằng phạm vi ảnh hưởng và khả năng hợp nhất các thay đổi hợp lệ sau target.

## 14. PITR trong môi trường CDB/PDB

Trong multitenant architecture, cần xác định phạm vi là:

- Toàn CDB.
- Một PDB.
- Một tablespace trong PDB.
- Một bảng trong PDB.

CDB PITR ảnh hưởng toàn container database và các PDB trong phạm vi phục hồi. PDB PITR có thể phục hồi một PDB riêng theo khả năng và quy trình của release, giúp tránh đưa các PDB khác về quá khứ.

Trước khi chạy recovery, kiểm tra:

~~~sql
SHOW CON_NAME;

SELECT con_id,
       name,
       open_mode
FROM v$pdbs
ORDER BY con_id;
~~~

Với PDB, cần xác minh backup/archived redo, auxiliary requirements, trạng thái PDB, common/local user, service và các dependency bên ngoài. Lệnh recovery và mở RESETLOGS ở cấp PDB khác với quy trình DBPITR toàn CDB. Không áp dụng nguyên ví dụ whole database cho PDB mà không kiểm tra tài liệu đúng release.

## 15. Xử lý thiếu archived redo log

Một trong những lỗi thường gặp là RMAN yêu cầu archived log nhưng không tìm thấy file tương ứng.

Thông báo có thể cho biết sequence hoặc SCN cần thiết. Hãy kiểm tra:

- Log có tồn tại trong FRA hoặc archive destination khác không?
- Có bản backup của archived log không?
- Media manager/SBT có thể restore log không?
- Có log ở instance khác hoặc nơi lưu trữ ngoài database không?
- Log có thuộc đúng thread và incarnation không?
- Tên file hoặc archive destination có thay đổi không?
- Recovery catalog và control file có metadata phù hợp không?

Không nên tạo file giả hoặc đổi tên một archive log khác để lấp khoảng trống. Archived redo có header và sequence/SCN riêng; một file không đúng không thể thay thế log bị thiếu.

Nếu không thể lấy được log cần thiết, phải chọn target sớm hơn điểm thiếu redo hoặc dùng một nguồn backup/recovery khác. Database chỉ có thể mở nhất quán tại một điểm mà tất cả datafile liên quan có thể được phục hồi tương thích.

## 16. Lỗi vận hành thường gặp và cách suy luận

| Triệu chứng | Hướng kiểm tra |
|---|---|
| RMAN báo thiếu archived log | Xác định thread, sequence, SCN, incarnation và tìm backup/archive copy |
| Không thể restore backup piece | Kiểm tra quyền, media manager, path, encryption wallet và tính toàn vẹn backup |
| Database yêu cầu media recovery khi mở | Kiểm tra datafile checkpoint và redo còn thiếu |
| OPEN RESETLOGS bị từ chối | Xác nhận recovery đã hoàn tất, database ở trạng thái phù hợp và đúng control file |
| Database mở được nhưng ứng dụng lỗi | Kiểm tra object, job, sequence, service, external systems và dữ liệu tại target |
| RMAN chọn backup không mong muốn | Kiểm tra SET UNTIL đặt trước RESTORE, incarnation, tag và repository |
| Không tìm thấy incarnation cũ | Kiểm tra control file/recovery catalog và metadata incarnation |
| Flashback Database không tới được target | Kiểm tra flashback logs, retention, FRA và restore point |
| Archive sequence trùng hoặc nhiều bản copy | Xem thread, resetlogs ID, SCN range, status và file thực tế |

Không xử lý lỗi bằng cách chạy lại cùng một lệnh nhiều lần mà không đọc thông báo RMAN/Oracle. Lưu log đầy đủ của RMAN và alert log để xác định bước recovery đã hoàn tất đến đâu.

## 17. Bảo toàn giao dịch sau target

Whole database PITR loại bỏ các thay đổi sau target khỏi database được phục hồi. Một số thay đổi đó có thể là giao dịch hợp lệ, không liên quan đến lỗi.

Ví dụ:

- 09:00: người dùng tạo đơn hàng hợp lệ.
- 09:30: batch lỗi cập nhật nhầm dữ liệu.
- 09:45: người dùng thanh toán một đơn hàng khác.
- 10:00: DBA phục hồi database về 09:29:59.

Sau PITR, các giao dịch từ 09:30 trở đi có thể không còn trong database, bao gồm cả thanh toán hợp lệ lúc 09:45. Nếu không có kế hoạch, ứng dụng có thể mất dữ liệu nghiệp vụ ngoài phạm vi sự cố.

Một chiến lược thường dùng:

1. Giữ nguyên bản database hiện tại hoặc backup trạng thái hiện tại.
2. Phục hồi bản chính về target trong môi trường kiểm soát.
3. Xác định các giao dịch hợp lệ phát sinh sau target.
4. Trích xuất dữ liệu cần thiết từ bản hiện tại hoặc application log.
5. Kiểm tra xung đột khóa, sequence, foreign key và thứ tự nghiệp vụ.
6. Hợp nhất dữ liệu có chọn lọc vào database đã phục hồi.
7. Đối soát với hệ thống bên ngoài trước khi mở lại traffic.

Không copy toàn bộ dữ liệu sau target một cách máy móc. Cần phân biệt transaction lỗi, transaction phụ thuộc transaction lỗi và transaction hợp lệ độc lập.

## 18. Kiểm thử recovery và diễn tập

Backup chỉ có giá trị khi chứng minh được khả năng restore/recover. Tổ chức nên diễn tập PITR trong môi trường không ảnh hưởng production.

Một bài diễn tập có thể gồm:

- Tạo dữ liệu kiểm thử và ghi nhận SCN.
- Backup database và archived redo.
- Thực hiện một thay đổi có thể đảo ngược trong môi trường thử.
- Chọn target trước thay đổi.
- Restore/recover đến target.
- Mở RESETLOGS.
- Kiểm tra dữ liệu, object và ứng dụng.
- Kiểm tra incarnation mới trong V$DATABASE_INCARNATION.
- Backup lại database sau RESETLOGS.
- Ghi thời gian từng bước để đánh giá RTO.

Đo cả RPO và RTO:

- **RPO (Recovery Point Objective):** mức dữ liệu tối đa tổ chức chấp nhận mất, thường biểu diễn bằng thời gian hoặc điểm giao dịch.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

Một quy trình PITR chính xác nhưng mất quá nhiều giờ có thể không đáp ứng RTO. Ngược lại, phục hồi nhanh đến target sai có thể vi phạm RPO và làm mất transaction hợp lệ.

## 19. Checklist trước, trong và sau PITR

### Trước recovery

- [ ] Xác định chính xác DBID, database, CDB/PDB và incarnation hiện tại.
- [ ] Xác định target SCN/time và timezone.
- [ ] Xác định transaction hoặc sự kiện cần loại bỏ.
- [ ] Xác nhận database ARCHIVELOG và backup phù hợp.
- [ ] Xác nhận archived redo liên tục trên tất cả thread cần thiết.
- [ ] Kiểm tra control file, SPFILE, password file và recovery catalog.
- [ ] Bảo toàn trạng thái hiện tại và giao dịch sau target nếu cần.
- [ ] Kiểm tra dung lượng datafile, FRA, auxiliary destination và backup storage.
- [ ] Xác định downtime, RPO/RTO và kế hoạch thông báo ứng dụng.

### Trong recovery

- [ ] Dừng ứng dụng ghi dữ liệu.
- [ ] Khởi động database ở MOUNT đúng quy trình.
- [ ] Đặt SET UNTIL trước RESTORE trong RUN block.
- [ ] Theo dõi từng datafile và archived log được restore/apply.
- [ ] Xác nhận recovery dừng tại target dự kiến.
- [ ] Lưu RMAN output và alert log.
- [ ] Chỉ mở RESETLOGS khi recovery hoàn tất và trạng thái phù hợp.

### Sau recovery

- [ ] Xác nhận OPEN_MODE và RESETLOGS_CHANGE#/TIME.
- [ ] Kiểm tra incarnation mới.
- [ ] Kiểm tra datafile, tablespace và object invalid.
- [ ] Đối soát dữ liệu nghiệp vụ và transaction boundary.
- [ ] Kiểm tra sequence, scheduler job, service và hệ thống ngoài.
- [ ] Backup database và archived redo trên incarnation mới.
- [ ] Validate backup và diễn tập restore theo lịch.
- [ ] Lưu hồ sơ sự cố, target, backup, incarnation và kết quả.

## 20. Kết luận

Point-in-time recovery đưa database về một SCN hoặc thời điểm đã chọn bằng cách restore backup và áp dụng redo đến target. Với whole database incomplete recovery, Oracle thường yêu cầu mở bằng RESETLOGS. Thao tác này tạo redo branch mới và một database incarnation mới, trong khi DBID thông thường vẫn giữ nguyên.

RMAN quản lý quan hệ giữa các incarnation để có thể phục hồi trên nhánh hiện tại hoặc ancestor khi có đủ backup và redo. Sau RESETLOGS, cần backup lại trên nhánh mới và kiểm tra khả năng phục hồi. Trước khi thực hiện PITR, hãy xác định target chính xác, bảo toàn trạng thái hiện tại, đánh giá các transaction sau target và chọn phạm vi nhỏ nhất đáp ứng mục tiêu khôi phục.
