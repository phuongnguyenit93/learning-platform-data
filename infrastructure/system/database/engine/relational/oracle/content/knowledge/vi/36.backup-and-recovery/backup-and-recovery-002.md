# Consistent backup, inconsistent backup và crash recovery

Một bản backup database chỉ hữu ích khi có thể khôi phục về trạng thái dữ liệu nhất quán. Trong Oracle, backup có thể được tạo khi database đã shutdown sạch hoặc khi database vẫn đang mở để phục vụ ứng dụng. Hai trường hợp này có đặc tính khác nhau: **consistent backup** chụp các datafile ở trạng thái nhất quán tại một điểm SCN; **inconsistent backup** có thể chứa các block/datafile ở những thời điểm khác nhau và cần redo để đưa chúng về cùng trạng thái khi restore.

**Crash recovery** là quá trình Oracle tự động đưa database về trạng thái nhất quán sau khi instance dừng bất thường, trong khi các datafile vẫn còn sẵn sàng. Oracle dùng redo để roll forward những thay đổi cần thiết và dùng undo để rollback transaction chưa commit. Nếu datafile bị mất/hỏng và phải lấy lại từ backup, đó là **media recovery**; nó có thể cần archived redo logs và online redo logs.

Bài học này trình bày:
- SCN, checkpoint và trạng thái nhất quán giữa datafile.
- Consistent backup và inconsistent/fuzzy backup.
- Backup khi database đóng, backup online và ARCHIVELOG/NOARCHIVELOG.
- RMAN online backup và user-managed hot backup mode.
- Vai trò của control file, SPFILE, online redo và archived redo.
- Crash/instance recovery so với media recovery.
- Roll forward bằng redo và rollback bằng undo.
- Quan sát recovery qua dynamic performance views và alert log.
- Restore/recover các loại backup và điều kiện OPEN/RESETLOGS.
- Lab và quy trình vận hành backup/recovery.

Các ví dụ dùng Oracle Database 19c. Cú pháp RMAN/SQL và một số view có thể khác theo release, cấu hình RAC, CDB/PDB và loại storage. Luôn kiểm tra tài liệu Backup and Recovery đúng phiên bản và thực hành restore trên môi trường lab trước khi áp dụng production.

## 1. SCN, checkpoint và tính nhất quán

### 1.1. SCN là gì?

System Change Number (SCN) là số thứ tự logic Oracle dùng để biểu diễn thứ tự các thay đổi trong database. SCN được dùng trong read consistency, redo, checkpoint, recovery và xác định điểm dữ liệu.

SCN không phải đồng hồ thời gian thực. Nó tăng theo hoạt động database và là mốc logic để Oracle xác định một trạng thái dữ liệu.

Khi nói một datafile được checkpoint tới SCN X, điều đó có nghĩa các thay đổi cần thiết tới mốc đó đã được ghi theo cơ chế checkpoint vào datafile và header metadata tương ứng. Nếu datafile có block mới hơn hoặc chưa đồng bộ hoàn toàn với các file khác, recovery có thể cần redo để đưa các file về trạng thái tương thích.

### 1.2. Checkpoint

Checkpoint là cơ chế Oracle thúc đẩy ghi dirty buffers từ buffer cache ra datafiles và cập nhật checkpoint information. Checkpoint giúp giới hạn lượng redo cần áp dụng khi instance recovery.

Checkpoint không có nghĩa mọi transaction đã commit tại thời điểm đó, cũng không có nghĩa mọi block trong database đều chứa dữ liệu của cùng một transaction snapshot. Dirty blocks của transaction chưa commit vẫn có thể được ghi xuống datafile; undo cho phép Oracle rollback hoặc cung cấp read-consistent view.

Các checkpoint liên quan:
- Thread checkpoint/instance checkpoint.
- Datafile checkpoint.
- Incremental checkpoint.
- Checkpoint trong quá trình shutdown hoặc log switch.

### 1.3. Datafile header và checkpoint SCN

Datafile header lưu thông tin nhận dạng file, checkpoint, resetlogs và trạng thái recovery. Control file cũng lưu metadata về datafiles, checkpoint và redo log history.

Khi database hoạt động bình thường, các datafile có thể ở các checkpoint SCN khác nhau. Điều này không có nghĩa database đang hỏng: Oracle quản lý sự khác biệt bằng redo và checkpoint coordination. Để database mở nhất quán, Oracle cần đảm bảo các file được recover tới một trạng thái tương thích.

### 1.4. Consistent database state

Một database consistent là trạng thái mà các datafiles được đồng bộ về một điểm nhất quán theo yêu cầu recovery, không còn cần redo để giải quyết sự khác biệt do backup/crash trước khi mở theo cách tương ứng.

Một **consistent whole database backup** thường được tạo sau khi database shutdown sạch, khi mọi datafile đã được checkpoint về trạng thái nhất quán. Nếu khôi phục đầy đủ bộ file từ backup đó và không có vấn đề khác, không cần media recovery để roll forward tới một SCN chung.

Một **inconsistent backup** có thể chứa datafile được copy ở các thời điểm khác nhau khi database đang mở. Nó có thể chứa block ở trạng thái fuzzy và cần redo để recover trước khi mở.

## 2. Consistent backup

Consistent backup là backup của database đã được đưa về trạng thái nhất quán trước khi lấy bản sao.

### 2.1. Tạo consistent backup bằng clean shutdown

Ví dụ user-managed backup ở cấp OS:

~~~sql
SHUTDOWN IMMEDIATE;
~~~

Sau khi instance dừng sạch, database đã hoàn tất transaction theo semantics của shutdown immediate, rollback transaction chưa commit và checkpoint datafiles. Khi database đã đóng, có thể copy toàn bộ datafiles, control files và SPFILE theo quy trình backup được hỗ trợ.

Có thể tạo consistent backup bằng RMAN khi database ở trạng thái MOUNT sau clean shutdown:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

Trong RMAN:

~~~text
BACKUP DATABASE;
BACKUP CURRENT CONTROLFILE;
BACKUP SPFILE;
~~~

Sau backup:

~~~sql
ALTER DATABASE OPEN;
~~~

Cần có kế hoạch bảo vệ control file và SPFILE. Nếu cấu hình control file autobackup, RMAN có thể tự tạo autobackup theo policy; vẫn phải xác minh backup piece thực tế và khả năng restore.

### 2.2. Điều kiện clean shutdown

Các kiểu shutdown cần phân biệt:
- SHUTDOWN NORMAL: chờ user disconnect.
- SHUTDOWN TRANSACTIONAL: chờ transaction đang hoạt động kết thúc.
- SHUTDOWN IMMEDIATE: kết thúc session và rollback transaction chưa commit trước khi dừng.
- SHUTDOWN ABORT: dừng instance ngay, không hoàn tất clean checkpoint/shutdown recovery.

Backup được lấy sau SHUTDOWN NORMAL, TRANSACTIONAL hoặc IMMEDIATE thành công có thể là consistent backup. Backup sau SHUTDOWN ABORT không được coi là consistent chỉ vì instance đã dừng; khi startup Oracle phải thực hiện crash/instance recovery.

### 2.3. Ưu điểm và hạn chế

Ưu điểm:
- Bộ datafile được copy ở trạng thái nhất quán.
- Có thể không cần archived redo để recover chính bộ consistent backup đó.
- Khái niệm và quy trình dễ hiểu.
- Phù hợp database nhỏ, lab hoặc hệ thống có downtime được chấp nhận.

Hạn chế:
- Cần downtime hoặc cửa sổ ngừng database.
- Không phù hợp hệ thống yêu cầu availability cao.
- Chỉ khôi phục được tới trạng thái tại thời điểm backup; giao dịch sau đó không có trong bản backup nếu không có cơ chế bổ sung.
- Cần sao lưu đầy đủ các file cần thiết và bảo vệ chúng cùng một bộ.

Một consistent backup không thay thế chiến lược backup định kỳ, offsite copy, archived log backup và kiểm thử restore nếu RPO/RTO yêu cầu phục hồi tới thời điểm mới hơn.

## 3. Inconsistent backup và fuzzy datafiles

Inconsistent backup là backup được tạo khi database đang mở hoặc khi các file không được đảm bảo checkpoint đồng thời về một trạng thái nhất quán.

### 3.1. Vì sao online backup có thể inconsistent?

Khi database mở, các session tiếp tục thay đổi block trong lúc backup đang đọc datafile. Một file có thể được copy trước khi transaction cập nhật block; file khác có thể được copy sau khi transaction đã thay đổi block. Bản sao có thể chứa các block thuộc nhiều SCN khác nhau.

Oracle gọi trạng thái cần recovery này là fuzzy. Fuzzy không đồng nghĩa backup hỏng. Nó có nghĩa cần áp dụng redo phù hợp để đưa các datafile về trạng thái nhất quán.

### 3.2. Ví dụ timeline

~~~text
Thời gian ---------------------------------------------------->

T1: Backup bắt đầu copy datafile A
T2: Transaction thay đổi block A và B, tạo redo
T3: Backup copy datafile B
T4: Transaction COMMIT
T5: Backup hoàn tất

Datafile A và B có thể phản ánh những thời điểm khác nhau.
Archived/online redo giúp roll forward về một SCN nhất quán.
~~~

Trong ví dụ, bản backup có thể đã copy block A trước thay đổi nhưng copy block B sau thay đổi. Recovery dùng redo để áp dụng thay đổi cần thiết, sau đó undo đảm bảo transaction chưa commit không xuất hiện như dữ liệu đã commit.

### 3.3. Inconsistent không có nghĩa là không an toàn

Oracle hỗ trợ online backup có kiểm soát trong ARCHIVELOG mode. RMAN theo dõi metadata backup và redo cần thiết. Khi restore, RMAN/Oracle áp dụng recovery để đưa các datafile về một điểm nhất quán.

Điều kiện quan trọng là phải bảo vệ đầy đủ archived redo logs cần thiết, control file, backup pieces và metadata. Một online backup thiếu redo cần thiết có thể không recover được tới mục tiêu mong muốn.

### 3.4. Backup một datafile không đồng nghĩa database-wide consistency

Một datafile backup có thể cần redo từ checkpoint của chính file đó. Nếu database có nhiều datafiles, recovery phải đảm bảo tất cả file cần thiết tương thích ở SCN đích. Không chỉ nhìn một datafile header để kết luận cả database consistent.

## 4. ARCHIVELOG và NOARCHIVELOG

Chế độ log ảnh hưởng trực tiếp tới khả năng backup online và phục hồi sau sự cố.

### 4.1. ARCHIVELOG mode

Trong ARCHIVELOG mode, Oracle lưu các redo log group đã đầy thành archived redo logs trước khi tái sử dụng group. Archived redo cho phép:
- Backup database trong khi database vẫn mở theo quy trình được hỗ trợ.
- Recover datafiles từ backup tới SCN/time mong muốn trong phạm vi redo còn có.
- Bảo vệ dữ liệu sau thời điểm backup.
- Thực hiện point-in-time recovery và nhiều kịch bản media recovery.

Kiểm tra:

~~~sql
ARCHIVE LOG LIST;
~~~

Hoặc:

~~~sql
SELECT
    log_mode,
    open_mode,
    current_scn
FROM v$database;
~~~

### 4.2. NOARCHIVELOG mode

Trong NOARCHIVELOG mode, online redo logs được tái sử dụng mà không lưu archived copies theo cơ chế archive log. Khi log cũ bị ghi đè, redo đó không còn sẵn để media recovery thông thường.

Hệ quả:
- Không thể dựa vào online backup đang mở theo quy trình online backup thông thường.
- Thường phải clean shutdown rồi backup database ở trạng thái MOUNT.
- Khả năng recover bị giới hạn bởi consistent backup gần nhất và các redo còn khả dụng.
- Mất datafile có thể đồng nghĩa mất các thay đổi sau backup.

NOARCHIVELOG chỉ phù hợp một số database có thể tái tạo dữ liệu hoặc chấp nhận RPO lớn. Không chọn chế độ này chỉ để tiết kiệm dung lượng archive.

### 4.3. Bật ARCHIVELOG mode

Ví dụ quy trình cơ bản:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST;
~~~

Trước khi bật:
- Xác định archive destination và dung lượng.
- Kiểm tra quyền/space của filesystem hoặc FRA.
- Cấu hình backup archived logs.
- Giám sát archive destination bị đầy.
- Kiểm tra backup và restore.
- Lập kế hoạch downtime vì cần restart/mount.

Chuyển sang ARCHIVELOG mode không tự tạo một chiến lược backup đầy đủ. Cần sao lưu database, control file, SPFILE và archived redo logs.

## 5. RMAN online backup

RMAN là công cụ Oracle khuyến nghị để backup/recovery. Với database ở ARCHIVELOG mode, RMAN có thể backup database trong khi database vẫn mở.

### 5.1. Điều kiện trước khi backup online

- Database đang ở ARCHIVELOG mode.
- Database và datafiles ở trạng thái phù hợp.
- Có nơi lưu backup pieces và archived logs.
- Control file/SPFILE được bảo vệ.
- Archive destination có đủ dung lượng.
- RMAN configuration/retention policy đã được xem xét.
- Backup job có log và monitoring.

### 5.2. Backup database cùng archived logs

Ví dụ trong RMAN:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Lệnh này yêu cầu RMAN backup database và archived redo logs theo trình tự cần thiết cho backup. Hành vi chính xác về archive log switching và phạm vi backup phụ thuộc cấu hình RMAN/version; kiểm tra output job và danh sách backup sau khi chạy.

Có thể bật control file autobackup:

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Và backup SPFILE/control file theo chính sách. Không chỉ dựa vào việc job trả SUCCESS; xác nhận backup piece, archived log coverage và restore validation.

### 5.3. RMAN không yêu cầu BEGIN BACKUP mode

RMAN online backup quản lý việc đọc datafile và metadata/redo cần thiết theo cơ chế của RMAN. Không chạy ALTER TABLESPACE BEGIN BACKUP trước RMAN backup. BEGIN/END BACKUP là cơ chế user-managed hot backup; áp dụng không đúng cách có thể làm tăng redo và gây nhầm lẫn trạng thái backup.

### 5.4. Kiểm tra backup

Trong RMAN:

~~~text
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
REPORT NEED BACKUP;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Ý nghĩa:
- LIST hiển thị backup mà repository biết.
- REPORT NEED BACKUP đánh giá nhu cầu backup theo policy.
- RESTORE PREVIEW liệt kê các backup cần dùng cho restore.
- RESTORE DATABASE VALIDATE kiểm tra khả năng đọc backup piece cần thiết mà không thực hiện restore thực tế.

Validation giúp phát hiện một số vấn đề readability nhưng không thay thế diễn tập restore hoàn chỉnh trên môi trường độc lập.

## 6. User-managed hot backup và BEGIN/END BACKUP

Ngoài RMAN, Oracle hỗ trợ user-managed backup bằng cách copy datafile ở cấp OS trong khi database mở. Khi đó cần dùng BEGIN BACKUP/END BACKUP đúng quy trình.

### 6.1. Điều kiện

- Database phải ở ARCHIVELOG mode cho online hot backup thông thường.
- Có quy trình copy file và bảo vệ control file.
- Phải sao lưu archived redo cần thiết.
- Phải kết thúc backup mode đúng cách.
- Phải kiểm tra file copy và recovery trước khi tin cậy.

### 6.2. BEGIN BACKUP

Ví dụ cho một tablespace:

~~~sql
ALTER TABLESPACE users BEGIN BACKUP;
~~~

Trong backup mode, Oracle giữ checkpoint SCN của datafile ở trạng thái phù hợp cho user-managed backup và thay đổi cách ghi redo đối với block được sửa lần đầu trong khoảng backup, bao gồm ghi full block image trong các trường hợp cần thiết để xử lý fractured block.

Điều này làm redo generation có thể tăng đáng kể, nhất là khi nhiều block được cập nhật trong backup window. BEGIN BACKUP không đóng băng dữ liệu và không ngăn ứng dụng ghi vào tablespace.

### 6.3. Copy datafile

Xác định đúng datafile của tablespace:

~~~sql
SELECT
    file_id,
    file_name,
    tablespace_name
FROM dba_data_files
WHERE tablespace_name = 'USERS';
~~~

Trong OS, copy đúng các file được xác định trong thời gian BEGIN BACKUP:

~~~bash
cp /u02/oradata/ORCL/users01.dbf /backup/orcl/users01.dbf
~~~

Ví dụ chỉ minh họa một file. Với nhiều datafile, cần copy toàn bộ file thuộc phạm vi backup và ghi nhận chính xác file name/path.

### 6.4. END BACKUP

Sau khi copy xong:

~~~sql
ALTER TABLESPACE users END BACKUP;
~~~

Kiểm tra trạng thái:

~~~sql
SELECT
    file#,
    status,
    change#,
    time
FROM v$backup;
~~~

File không còn ở backup mode sau khi END BACKUP hoàn tất. Không để tablespace ở backup mode lâu hơn cần thiết vì có thể làm tăng redo và gây vấn đề vận hành.

### 6.5. Backup toàn database

Có thể dùng ALTER DATABASE BEGIN BACKUP/END BACKUP trong một số quy trình user-managed cũ, nhưng cần cân nhắc phạm vi, redo overhead và hướng dẫn release. Thực hành hiện đại thường ưu tiên RMAN; nếu buộc dùng user-managed backup, hãy có runbook chính xác cho từng datafile/tablespace, control file và archived logs.

### 6.6. Nếu quên END BACKUP

Kiểm tra V$BACKUP để phát hiện file còn ACTIVE. Nếu database crash khi file ở backup mode, Oracle có thể cần xử lý trạng thái backup khi startup/recovery. DBA phải xác định file nào đang ở backup mode, database đang MOUNT/OPEN ra sao và thực hiện END BACKUP/recovery theo đúng tài liệu Oracle cho tình huống cụ thể. Không chạy lệnh hàng loạt hoặc copy file thêm khi chưa hiểu trạng thái.

## 7. Redo, undo và recovery

### 7.1. Redo là gì?

Redo record mô tả các thay đổi cần áp dụng để tái tạo database block. Redo được ghi vào redo log buffer rồi LGWR ghi xuống online redo logs. Khi log group được archive trong ARCHIVELOG mode, Oracle tạo archived redo log.

Redo được tạo cho thay đổi dữ liệu và các thay đổi cần thiết khác, bao gồm thông tin phục vụ undo. Redo không chỉ chứa transaction đã commit; redo của transaction chưa commit cũng có thể được ghi.

### 7.2. Undo là gì?

Undo lưu thông tin cần để rollback transaction và cung cấp read consistency. Khi transaction thay đổi row, Oracle tạo undo record mô tả cách khôi phục giá trị trước đó.

Trong recovery:
- Redo roll forward thay đổi đã ghi redo vào datafiles, bao gồm thay đổi của transaction chưa commit.
- Undo rollback transaction chưa commit để database trở về trạng thái transactionally consistent.

### 7.3. Vì sao phải roll forward cả transaction chưa commit?

Khi crash, datafile có thể chứa một số block của transaction chưa commit vì DBWR đã ghi chúng xuống trước crash. Oracle phải áp dụng redo để đảm bảo mọi block có thay đổi được phục hồi đúng. Sau đó transaction recovery dùng undo để loại bỏ thay đổi chưa commit.

Nếu chỉ roll forward các transaction đã commit, database có thể còn block ở trạng thái dở dang hoặc thiếu thay đổi cần thiết để đồng bộ các cấu trúc liên quan.

### 7.4. Minh họa

~~~text
Trước crash:
  Transaction A: UPDATE row 1, COMMIT
  Transaction B: UPDATE row 2, chưa COMMIT

Datafile có thể đã nhận một phần block của A và B.
Redo log chứa redo cho cả thay đổi A và B.

Crash recovery:
  1. Cache recovery: roll forward redo để tái tạo block nhất quán.
  2. Transaction recovery: dùng undo rollback B.
  3. Database mở với thay đổi A đã commit, B không xuất hiện như committed data.
~~~

## 8. Crash recovery và instance recovery

Crash recovery thường được gọi là instance recovery: Oracle phục hồi database sau khi instance dừng bất thường nhưng các datafiles/redo cần thiết vẫn còn sẵn sàng.

Các nguyên nhân:
- Server mất điện hoặc OS crash.
- Oracle instance process bị lỗi.
- Shutdown abort.
- Instance bị terminate.
- Một instance RAC thất bại.

### 8.1. Điều gì xảy ra khi startup?

Khi instance khởi động và mount/open database, Oracle kiểm tra checkpoint và trạng thái redo. Nếu cần, Oracle thực hiện instance recovery trước khi cho database hoạt động bình thường.

Luồng khái quát:

~~~text
Instance failure / abnormal shutdown
               |
               v
        STARTUP / mount
               |
               v
   Read control file and datafile headers
               |
               v
   Determine checkpoint and redo position
               |
               v
       Cache recovery (redo)
               |
               v
 Transaction recovery (undo rollback)
               |
               v
        Open database normally
~~~

Trong nhiều trường hợp, DBA chỉ cần khởi động instance; Oracle tự động thực hiện crash recovery. Không cần restore datafile nếu file vẫn nguyên vẹn và redo còn đủ.

### 8.2. Cache recovery / roll forward

Oracle áp dụng redo từ vị trí checkpoint cần thiết để đưa data blocks về trạng thái nhất quán. Redo có thể nằm trong online redo logs của thread cần recovery.

### 8.3. Transaction recovery / rollback

Sau roll forward, Oracle xác định transaction chưa commit và rollback bằng undo. Việc rollback có thể tiếp tục sau khi database đã mở; session có thể gặp transaction recovery/rollback activity trong thời gian đó.

### 8.4. Crash recovery không phải media recovery

| Tình huống | Loại recovery | Cần restore backup? |
| --- | --- | --- |
| Instance crash, datafiles và online redo còn tốt | Instance/crash recovery | Thường không |
| Shutdown abort rồi startup | Instance/crash recovery | Thường không |
| Datafile bị xóa/hỏng | Media recovery | Thường cần restore file |
| Diskgroup chứa datafile bị mất | Media recovery/storage recovery | Tùy redundancy và backup |
| Restore online backup | Media recovery | Có, áp dụng redo sau restore |
| Restore tới SCN/time trong quá khứ | Incomplete media recovery | Có, sau đó OPEN RESETLOGS |

Nếu datafile mất, Oracle không thể chỉ dựa vào instance recovery để tạo lại file. Cần restore từ backup và recover bằng redo.

## 9. Checkpoint và thời gian crash recovery

Checkpoint giúp giảm lượng redo phải áp dụng khi instance recovery. Checkpoint quá cũ có thể làm recovery cần xử lý nhiều redo hơn; checkpoint thường xuyên hơn có thể tăng I/O và ảnh hưởng workload nếu cấu hình không phù hợp.

### 9.1. FAST_START_MTTR_TARGET

Oracle có thể dùng FAST_START_MTTR_TARGET để đặt mục tiêu thời gian instance recovery (ước lượng). Ví dụ:

~~~sql
SHOW PARAMETER fast_start_mttr_target;
~~~

Xem thông tin recovery:

~~~sql
SELECT
    target_mttr,
    estimated_mttr,
    actual_redo_blks,
    target_redo_blks,
    optimal_logfile_size
FROM v$instance_recovery;
~~~

Tên/cột và cách tính phụ thuộc release. MTTR target là mục tiêu cho instance recovery, không phải cam kết mọi crash sẽ mở database trong đúng số giây đó; storage, redo volume, workload và lỗi phần cứng có thể làm thời gian thực tế khác.

### 9.2. Không ép checkpoint liên tục

Chạy ALTER SYSTEM CHECKPOINT liên tục không phải cách tối ưu chung để tăng tốc recovery. Nó có thể tạo I/O spike và làm tăng chi phí ghi dirty buffers. Hãy điều chỉnh MTTR và checkpoint policy theo workload, đo tác động và tuân thủ khuyến nghị Oracle.

## 10. Media recovery sau khi restore inconsistent backup

Media recovery cần thiết khi datafile được restore từ backup và phải áp dụng redo để đồng bộ tới SCN mục tiêu.

### 10.1. Quy trình tổng quát

~~~text
Backup pieces + control file + archived redo
                   |
                   v
              RESTORE
                   |
                   v
       Datafiles trở về trạng thái backup
                   |
                   v
               RECOVER
                   |
                   v
   Apply archived/online redo tới target SCN
                   |
                   v
      Datafiles nhất quán tại target SCN
                   |
                   v
                 OPEN
~~~

### 10.2. Restore và recover bằng RMAN

Ví dụ khái niệm cho complete recovery với control file hiện tại:

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

Trong RMAN, các lệnh restore/recover được chạy tại RMAN prompt; STARTUP/ALTER DATABASE có thể được thực hiện qua RMAN hoặc SQL*Plus tùy quy trình.

Complete recovery áp dụng redo tới trạng thái mới nhất có thể theo redo sẵn có và control file/repository. Nếu tất cả datafiles được recover đầy đủ bằng current control file, thường mở database bình thường.

### 10.3. Backup control file

Nếu control file cũng bị mất và phải restore từ backup, Oracle có thể yêu cầu recovery với backup control file và mở RESETLOGS sau khi hoàn tất quy trình phù hợp.

Luồng ví dụ:

~~~text
STARTUP NOMOUNT;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN RESETLOGS;
~~~

Đây là ví dụ khái quát. Nếu cần incomplete recovery hoặc control file backup, phải xác định target SCN/time, redo availability, incarnation và hướng dẫn RMAN chính xác. Không chạy OPEN RESETLOGS chỉ vì thấy một lệnh ví dụ; RESETLOGS tạo database incarnation mới và ảnh hưởng backup/recovery strategy.

### 10.4. Incomplete recovery / point-in-time recovery

Nếu cần đưa database về thời điểm trước một lỗi logic, dùng RMAN SET UNTIL SCN/TIME/SEQUENCE phù hợp rồi restore/recover. Sau incomplete recovery, database thường phải OPEN RESETLOGS.

Ví dụ dạng lệnh RMAN:

~~~text
RUN {
  SET UNTIL TIME "TO_DATE('2026-11-14 10:30:00',
                         'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Sau đó mở database bằng RESETLOGS theo yêu cầu của recovery path. Thời gian trong ví dụ chỉ minh họa; cần chọn đúng timezone, target và kiểm tra redo coverage.

## 11. Control file, SPFILE và redo logs trong backup

### 11.1. Control file

Control file lưu cấu trúc database, datafile/redo log names, checkpoint metadata, log history và RMAN repository records nếu dùng control file repository.

Nếu control file bị mất:
- Có thể restore từ autobackup.
- Có thể cần catalog backup nếu repository không có metadata.
- Có thể phải recover bằng backup control file.
- Thường phải OPEN RESETLOGS sau quy trình restore control file phù hợp.

Giữ nhiều bản control file multiplexed không thay thế backup control file; multiplexing bảo vệ khỏi mất một bản do lỗi storage/file.

### 11.2. SPFILE/PFILE

SPFILE chứa tham số khởi động database. Backup SPFILE giúp khôi phục cấu hình instance sau sự cố. RMAN có thể backup SPFILE riêng hoặc cùng control file autobackup theo cấu hình.

~~~text
BACKUP SPFILE;
~~~

Nếu dùng PFILE, lưu file cấu hình ở nơi được bảo vệ và quản lý version.

### 11.3. Online redo logs

Online redo logs cần cho crash/instance recovery và có thể cần trong media recovery tới current state. Không coi việc backup datafiles là đủ nếu online redo và archived redo cần thiết không được bảo vệ.

Không nên copy online redo log file đang hoạt động như một file thông thường để tạo backup. Dùng cơ chế Oracle hỗ trợ và backup control file/archived logs theo kế hoạch.

### 11.4. Archived redo logs

Archived logs là chuỗi redo cần thiết để recover từ backup tới SCN mục tiêu. Nếu thiếu một log trong chuỗi cần thiết, recovery có thể dừng ở SCN trước đó.

Bảo vệ archive logs:
- Backup thường xuyên.
- Giữ theo retention/recovery window.
- Theo dõi archive destination/FRA.
- Có bản sao ngoài host/zone nếu yêu cầu DR.
- Kiểm tra restore/validate.
- Tránh xóa archived logs thủ công khi RMAN repository chưa được cập nhật.

## 12. Kiểm tra trạng thái backup và recovery

### 12.1. Database mode và SCN

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn,
    checkpoint_change#
FROM v$database;
~~~

Các cột cho biết database identity, open mode, archive mode và một số mốc SCN. Chúng không tự chứng minh mọi backup piece đều hợp lệ.

### 12.2. Datafile header

~~~sql
SELECT
    file#,
    status,
    error,
    recover,
    fuzzy,
    checkpoint_change#,
    checkpoint_time
FROM v$datafile_header
ORDER BY file#;
~~~

Các cột RECOVER và FUZZY giúp nhận biết trạng thái cần recovery/fuzzy của từng datafile. Diễn giải phải kết hợp control file, open state, backup mode và recovery context.

### 12.3. Datafile metadata

~~~sql
SELECT
    file#,
    name,
    status,
    checkpoint_change#,
    checkpoint_time
FROM v$datafile
ORDER BY file#;
~~~

So sánh metadata datafile với header và recovery status. Không dùng một chênh lệch SCN đơn lẻ để kết luận database hỏng; checkpoint có thể khác nhau trong hoạt động bình thường.

### 12.4. Files cần media recovery

~~~sql
SELECT
    file#,
    online,
    error,
    change#,
    time
FROM v$recover_file
ORDER BY file#;
~~~

V$RECOVER_FILE giúp xác định datafiles Oracle đánh dấu cần media recovery. Nếu view không trả dòng, điều đó không thay thế restore validation hoặc backup testing.

### 12.5. User-managed backup mode

~~~sql
SELECT
    file#,
    status,
    change#,
    time
FROM v$backup
ORDER BY file#;
~~~

STATUS có thể cho biết file đang ở trạng thái backup mode. Sau user-managed backup, xác nhận status không còn ACTIVE. View này không dùng để theo dõi RMAN backup mode.

### 12.6. Alert log

Alert log ghi nhận:
- Instance startup/shutdown.
- Crash recovery start/completion.
- Media recovery messages.
- Datafile errors.
- Archive log issues.
- Control file/redo problems.

Khi điều tra startup chậm sau crash, hãy đọc alert log từ thời điểm failure tới khi database open. Kết hợp timestamp với V$INSTANCE_RECOVERY, V$SESSION và OS/storage metrics.

## 13. Crash recovery trong thực tế

### 13.1. Khi instance crash nhưng file còn nguyên

Nếu instance dừng bất thường nhưng datafiles, control files và online redo logs còn nguyên:
1. Xác nhận host/storage ổn định.
2. Kiểm tra alert log và lỗi OS.
3. Khởi động instance.
4. Oracle tự phát hiện cần instance recovery.
5. Oracle roll forward redo và rollback transaction chưa commit.
6. Xác nhận database OPEN và service hoạt động.
7. Kiểm tra datafile status, alert log và backup health.

Không restore backup chỉ vì database từng crash. Restore không cần thiết có thể đưa dữ liệu về thời điểm cũ và làm mất transaction hợp lệ sau backup.

### 13.2. Khi online redo bị mất/hỏng

Nếu online redo cần cho crash recovery bị mất hoặc hỏng, tình huống phức tạp hơn. Khả năng recovery phụ thuộc:
- Redo group/member nào bị ảnh hưởng.
- Current/active/inactive status.
- Multiplexed members còn lại.
- Archived logs có sẵn.
- Control file state.
- Database mode và failure timing.

Không xóa/recreate redo log group để né lỗi khi chưa xác định trạng thái. Có thể cần media recovery, incomplete recovery hoặc quy trình disaster recovery chuyên biệt.

### 13.3. RAC instance recovery

Trong RAC, nếu một instance thất bại, các instance còn lại có thể thực hiện instance recovery cho thread của instance bị lỗi theo cơ chế RAC. Global Cache Service và redo thread riêng của từng instance làm quá trình phức tạp hơn single-instance.

Khi điều tra RAC:
- Xác định instance/thread bị lỗi.
- Xem alert log của từng instance.
- Kiểm tra redo thread và archive sequence.
- Kiểm tra cluster/interconnect.
- Dùng công cụ/guide RAC đúng phiên bản.

Không áp dụng nguyên trạng mọi lệnh single-instance cho RAC production.

## 14. Các lỗi recovery thường gặp

| Lỗi/hiện tượng | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| ORA-01113 | Datafile cần media recovery | Xác định file, restore nếu cần rồi recover |
| ORA-01110 | Thông tin file datafile liên quan lỗi | Đọc kèm ORA trước đó để xác định file |
| ORA-01194 | File chưa đủ recovery để nhất quán | Áp dụng thêm redo tới SCN cần thiết |
| ORA-01152 | File không được restore từ backup đủ cũ cho recovery | Chọn backup phù hợp với target và redo |
| ORA-00279 | Recovery yêu cầu một change/redo sequence cụ thể | Cung cấp archived log đúng sequence/thread |
| ORA-00308 | Không mở được archived log | Kiểm tra file/path/permission và backup copy |
| ORA-00313 | Không mở được redo log member | Kiểm tra redo group/member và storage |
| ORA-01157 | Không nhận diện/lock được datafile | Kiểm tra file path, storage và permissions |
| ORA-00205 | Không xác định được control file | Kiểm tra CONTROL_FILES và bản control file |
| ORA-00257 | Archiver error, thường do archive destination đầy | Giải phóng/mở rộng destination và xử lý archive |
| Startup mất lâu sau abort | Instance recovery cần apply nhiều redo/rollback | Theo dõi alert log, MTTR và I/O |
| Datafile fuzzy sau online backup | Backup cần redo recovery | Bảo đảm archived logs cần thiết và recover |
| V$BACKUP còn ACTIVE | File có thể còn trong user-managed backup mode | Xác định trạng thái và kết thúc backup mode đúng cách |

Mã lỗi có thể xuất hiện theo chuỗi. Luôn đọc thông báo đầu tiên và alert log; không xử lý chỉ dựa vào dòng cuối.

## 15. Runbook: phân biệt instance recovery và media recovery

Khi database không mở được sau sự cố:

### Bước 1: Xác định loại sự cố
- Instance crash nhưng file còn nguyên?
- Datafile bị mất hoặc corrupt?
- Control file bị mất?
- Online redo/archive log bị mất?
- Chỉ một tablespace/file offline hay toàn database?

### Bước 2: Bảo toàn bằng chứng
- Không xóa/ghi đè file lỗi.
- Lưu alert log và OS/storage logs.
- Ghi thời điểm, SCN, thread/sequence nếu có.
- Xác nhận backup pieces và archive logs còn nguyên.

### Bước 3: Kiểm tra database state
- Instance status/open mode.
- Control file availability.
- Datafile header RECOVER/FUZZY.
- V$RECOVER_FILE.
- Online redo log status.
- Archived log coverage.

### Bước 4: Chọn recovery path
- Chỉ crash, files intact: startup và instance recovery tự động.
- Datafile missing/corrupt: restore file và media recover.
- Control file lost: restore control file, mount, restore/recover theo backup control file procedure.
- Point-in-time recovery: chọn target SCN/time và chuẩn bị OPEN RESETLOGS.

### Bước 5: Xác nhận sau recovery
- Database OPEN đúng mode.
- Datafiles ONLINE và không còn yêu cầu recovery.
- Alert log không còn recovery error.
- Service và application smoke tests thành công.
- Backup mới được tạo theo incarnation/state sau RESETLOGS nếu có.
- Archive destinations và backup jobs hoạt động.

Không mở RESETLOGS hoặc xóa redo/archive logs trước khi xác định recovery target và kiểm tra backup strategy.

## 16. Lab: so sánh consistent và inconsistent backup

Lab này cần một database Oracle riêng, có quyền SYSDBA/RMAN và nơi lưu backup. Không thực hiện trên production.

### 16.1. Quan sát trạng thái ban đầu

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn
FROM v$database;

SELECT
    file#,
    status,
    recover,
    fuzzy,
    checkpoint_change#
FROM v$datafile_header
ORDER BY file#;
~~~

Ghi nhận log mode, current SCN và datafile header state.

### 16.2. Tạo consistent backup

Clean shutdown:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

Trong RMAN:

~~~text
BACKUP DATABASE;
BACKUP CURRENT CONTROLFILE;
BACKUP SPFILE;
LIST BACKUP SUMMARY;
~~~

Mở lại database:

~~~sql
ALTER DATABASE OPEN;
~~~

Ghi thời điểm backup, backup pieces và control file/SPFILE được bảo vệ. Nếu database ở NOARCHIVELOG, kiểu backup clean shutdown/mount là quy trình cần dùng; xác nhận với RMAN guide của release.

### 16.3. Tạo online backup trong ARCHIVELOG mode

Xác nhận:

~~~sql
ARCHIVE LOG LIST;
~~~

Trong RMAN:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
LIST BACKUP SUMMARY;
LIST BACKUP OF ARCHIVELOG ALL;
~~~

Ghi nhận backup database và archive logs. Đây là inconsistent/online backup có thể cần redo để recover; RMAN quản lý backup metadata.

### 16.4. So sánh

Ghi bảng:

| Thuộc tính | Consistent backup | Inconsistent/online backup |
| --- | --- | --- |
| Database mở khi backup | Không, sau clean shutdown | Có thể có |
| Datafile checkpoint | Đã được đưa về trạng thái nhất quán trước backup | Có thể khác nhau/fuzzy |
| Redo để recover | Thường không cần cho chính backup nhất quán | Cần redo phù hợp |
| Downtime | Cần | Có thể không cần |
| ARCHIVELOG | Không bắt buộc cho consistent cold backup | Cần cho online backup thông thường |
| RPO | Trạng thái tại backup | Có thể recover tới điểm mới hơn nếu có redo |

### 16.5. Restore validation

Trong RMAN:

~~~text
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Quan sát backup piece nào được yêu cầu. Lưu ý validation không thực hiện restore vào database đang chạy; nó kiểm tra khả năng đọc backup theo lệnh validate.

## 17. Lab: quan sát crash recovery

Chỉ thực hiện trên database lab riêng, có backup và được phép dừng instance.

### 17.1. Ghi nhận baseline

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn
FROM v$database;

SELECT
    target_mttr,
    estimated_mttr,
    actual_redo_blks,
    target_redo_blks
FROM v$instance_recovery;
~~~

Ghi alert log location và trạng thái backup gần nhất.

### 17.2. Tạo workload lab

Tạo bảng thử nghiệm và chạy một số DML trong session. Commit một phần transaction; giữ một transaction khác chưa commit trong session lab.

~~~sql
CREATE TABLE lab_crash_recovery (
    id NUMBER PRIMARY KEY,
    value NUMBER
);

INSERT INTO lab_crash_recovery VALUES (1, 100);
COMMIT;

UPDATE lab_crash_recovery
SET value = 200
WHERE id = 1;
-- Session này chưa COMMIT.
~~~

### 17.3. Thực hiện shutdown abort trong lab

Từ một session SYSDBA được phép:

~~~sql
SHUTDOWN ABORT;
~~~

Lệnh này mô phỏng dừng bất thường. Chỉ chạy trong database lab vì tất cả session bị ngắt và startup tiếp theo phải thực hiện instance recovery.

### 17.4. Startup và quan sát

~~~sql
STARTUP;
~~~

Theo dõi alert log để quan sát crash recovery. Sau khi database mở:

~~~sql
SELECT * FROM lab_crash_recovery;
~~~

Thay đổi đã commit phải còn. Transaction chưa commit phải được rollback; giá trị 100 được giữ lại thay vì 200.

Kết quả cụ thể phụ thuộc checkpoint/redo timing, nhưng semantics transaction phải được bảo đảm.

### 17.5. Dọn lab

~~~sql
DROP TABLE lab_crash_recovery PURGE;
~~~

Nếu instance không startup được hoặc lab có file/redo lỗi, dừng thao tác và dùng backup lab để phục hồi. Không thử các lệnh media recovery trên production dựa vào bài tập này.

## 18. Bài tập thực hành

### Bài 1 — SCN và checkpoint

Đọc V$DATABASE, V$DATAFILE và V$DATAFILE_HEADER. Giải thích checkpoint SCN, current SCN và vì sao header SCN giữa các datafile không phải lúc nào cũng giống nhau trong database đang mở.

### Bài 2 — Clean shutdown

Tạo consistent backup sau SHUTDOWN IMMEDIATE. Ghi lại trạng thái database và giải thích vì sao backup có thể không cần redo recovery.

### Bài 3 — Shutdown abort

So sánh SHUTDOWN IMMEDIATE với SHUTDOWN ABORT trong lab. Quan sát alert log và giải thích instance recovery.

### Bài 4 — ARCHIVELOG

Kiểm tra LOG_MODE. Nếu lab ở NOARCHIVELOG, lập kế hoạch chuyển sang ARCHIVELOG, cấu hình destination và backup archived logs.

### Bài 5 — RMAN online backup

Chạy BACKUP DATABASE PLUS ARCHIVELOG trong lab. Dùng LIST BACKUP, RESTORE PREVIEW và RESTORE VALIDATE để kiểm tra.

### Bài 6 — User-managed backup mode

Trong môi trường lab, thực hiện BEGIN BACKUP, copy datafile, END BACKUP và xem V$BACKUP. Ghi nhận redo volume nếu có công cụ theo dõi.

### Bài 7 — Redo và undo

Tạo một transaction chưa commit, thực hiện crash recovery trong lab. Giải thích vì sao Oracle cần roll forward redo rồi rollback bằng undo.

### Bài 8 — Media recovery

Dùng bản sao lab riêng để mô phỏng restore một datafile từ online backup và áp dụng archived logs. Không thao tác trên datafile production.

### Bài 9 — Control file backup

Bật CONTROLFILE AUTOBACKUP trong RMAN lab, kiểm tra LIST BACKUP và mô tả quy trình restore control file khi mất control file hiện tại.

### Bài 10 — Runbook

Viết runbook phân loại sự cố instance crash, datafile loss, control file loss và point-in-time recovery. Với mỗi tình huống ghi rõ backup, redo, target SCN và điều kiện OPEN/RESETLOGS.

## 19. Dọn dẹp và khôi phục môi trường lab

- Đảm bảo mọi transaction lab đã commit/rollback có chủ đích.
- Xóa đúng bảng và object lab.
- Khôi phục tham số hoặc archive destination đã thay đổi.
- Xác nhận database OPEN và service đăng ký.
- Kiểm tra V$BACKUP không còn user-managed file ACTIVE.
- Xác nhận backup pieces/archived logs lab được lưu hoặc xóa theo policy.
- Không xóa archived logs cần cho recovery của database dùng chung.
- Không xóa control file, online redo log hoặc datafile để tạo thêm tình huống nếu chưa có bản backup độc lập và kế hoạch restore.

## Tổng kết

Consistent backup thường được tạo sau clean shutdown khi các datafiles đã checkpoint về trạng thái nhất quán. Inconsistent/online backup được tạo khi database đang mở hoặc file được copy ở những thời điểm khác nhau; datafiles có thể fuzzy và cần redo để recover về một SCN nhất quán. ARCHIVELOG mode cho phép online backup và media recovery tới thời điểm mới hơn; NOARCHIVELOG giới hạn khả năng phục hồi và thường yêu cầu consistent backup sau clean shutdown.

Crash recovery (instance recovery) xảy ra khi instance dừng bất thường nhưng datafiles và redo còn sẵn sàng. Oracle tự động roll forward bằng redo rồi rollback transaction chưa commit bằng undo. Media recovery khác: khi datafile/control file bị mất hoặc restore từ backup, DBA phải restore file và apply redo phù hợp. Control file, SPFILE, online redo và archived redo đều là thành phần quan trọng của chiến lược bảo vệ database.

Khi vận hành, xác định rõ loại backup, SCN/checkpoint, ARCHIVELOG mode, backup piece và redo coverage. Dùng RMAN để quản lý backup/restore, validate khả năng đọc và diễn tập phục hồi. Không nhầm crash recovery với restore backup, không chạy BEGIN/END BACKUP trước RMAN, và không OPEN RESETLOGS khi chưa xác định recovery path. Một backup chỉ đáng tin khi đã chứng minh có thể restore và recover theo RPO/RTO cần thiết.

## Tài liệu Oracle tham khảo

- [Oracle Database Backup and Recovery User's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup/recovery, consistent/inconsistent backups, instance recovery và media recovery.
- [Oracle Database Backup and Recovery Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — RMAN commands, BACKUP, RESTORE, RECOVER và validation.
- [Oracle Database Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — startup/shutdown, checkpoint, redo và archive mode.
- [Oracle Database Reference — V$DATAFILE_HEADER (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE_HEADER.html) — datafile header checkpoint và recovery flags.
- [Oracle Database Reference — V$RECOVER_FILE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RECOVER_FILE.html) — datafiles cần media recovery.
- [Oracle Database Reference — V$BACKUP (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-BACKUP.html) — trạng thái user-managed backup mode.
- [Oracle Database Reference — V$INSTANCE_RECOVERY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INSTANCE_RECOVERY.html) — thông tin checkpoint và MTTR recovery.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu Backup and Recovery User's Guide, RMAN Reference và Data Dictionary Reference đúng phiên bản, đặc biệt backup mode, archived redo requirements, control file recovery, RESETLOGS và RAC instance recovery.
