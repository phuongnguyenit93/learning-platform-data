# Complete recovery khi mất datafile hoặc hỏng vùng lưu trữ

Khi một datafile bị mất, ổ đĩa chứa datafile hỏng hoặc một vùng lưu trữ không còn truy cập được, Oracle Database có thể không đọc được một phần dữ liệu cần thiết để vận hành. Để đưa database trở lại trạng thái nhất quán, DBA phải xác định phạm vi hư hỏng, khôi phục các file từ bản sao lưu và áp dụng redo cần thiết.

**Complete recovery** là quá trình khôi phục file rồi áp dụng các thay đổi redo để đưa file hoặc database tiến đến thời điểm hiện tại mà redo cần thiết còn đầy đủ. Mục tiêu là giữ lại các transaction đã commit đến thời điểm recovery hoàn tất, thay vì chủ động quay database về một thời điểm cũ. Nếu thiếu một đoạn redo cần thiết và không có bản sao lưu/nguồn redo thay thế, không thể tiếp tục complete recovery qua khoảng trống đó; khi ấy DBA phải cân nhắc incomplete recovery hoặc một phương án khôi phục khác.

Trong Oracle, RMAN là công cụ chính để restore backup và recover datafile/database. Tuy nhiên, RMAN không thay thế việc hiểu kiến trúc file, redo, control file, ASM và trạng thái instance. Cùng một thông báo lỗi “file không truy cập được” có thể bắt nguồn từ datafile bị xóa, disk group ASM mất, filesystem đầy, quyền truy cập thay đổi, lỗi I/O hoặc hỏng block. Trình tự xử lý đúng phụ thuộc vào file nào bị ảnh hưởng và database đang ở trạng thái nào.

## 1. Phân biệt restore, recovery và complete recovery

Ba thuật ngữ thường xuất hiện cùng nhau nhưng có ý nghĩa khác nhau:

- **Restore:** lấy một bản sao của file từ backup và đưa file đó trở lại vị trí lưu trữ. File vừa restore thường chứa dữ liệu ở một SCN cũ hơn database hiện tại.
- **Recover:** áp dụng redo (archived redo log và có thể cả online redo log) lên file đã restore hoặc file cần đồng bộ, để đưa file tiến đến SCN cần thiết.
- **Open:** mở database hoặc đưa datafile/tablespace trở lại trạng thái online sau khi recovery hoàn tất và các điều kiện nhất quán đã được đáp ứng.

Luồng khái quát:

```text
Phát hiện file hỏng/mất
        |
        v
Xác định file, tablespace, trạng thái database
        |
        v
Đảm bảo storage/đường dẫn đích sẵn sàng
        |
        v
RESTORE từ backup
        |
        v
RECOVER: áp dụng archived/online redo cần thiết
        |
        v
Kiểm tra trạng thái và tính nhất quán
        |
        v
ONLINE file/tablespace hoặc OPEN database
```

Restore không tự làm database nhất quán với các file còn lại. Một datafile được restore từ backup có thể có checkpoint SCN cũ. Recovery đưa file đó bắt kịp các thay đổi cần thiết.

### 1.1. Complete recovery và incomplete recovery

| Đặc điểm | Complete recovery | Incomplete recovery |
|---|---|---|
| Mục tiêu | Khôi phục đến thời điểm hiện tại hoặc điểm mới nhất có thể áp dụng đầy đủ redo | Dừng tại một thời điểm/SCN/log sequence đã chọn trong quá khứ |
| Redo | Cần chuỗi redo liên tục từ backup đến điểm recovery | Cần redo đến điểm dừng được chọn |
| Dữ liệu đã commit sau điểm dừng | Được giữ nếu redo đầy đủ và recovery tới hiện tại | Không còn trong database sau khi mở lại ở điểm cũ |
| Mở database | Thông thường mở bình thường nếu dùng current control file và hoàn tất complete recovery | Thường cần `OPEN RESETLOGS` sau incomplete recovery |
| Tình huống | Mất datafile nhưng vẫn còn backup và redo đầy đủ | Hỏng logic, xóa nhầm dữ liệu hoặc thiếu redo cần quay về trước sự cố |

Complete recovery không có nghĩa “restore bản backup mới nhất rồi mở database”. Một bản backup mới nhất vẫn có thể cũ hơn thời điểm database bị sự cố. Phải áp dụng redo từ checkpoint của bản backup đến thời điểm recovery mục tiêu.

### 1.2. SCN và vai trò của redo

SCN (System Change Number) là số thứ tự thay đổi logic do Oracle quản lý. Datafile header lưu checkpoint SCN và các thông tin cần thiết để xác định file đang ở trạng thái nào. Control file lưu metadata về database, datafile, redo log và checkpoint. Redo log ghi lại các thay đổi cần thiết để khôi phục database.

Khi restore datafile từ backup, header của file có thể ghi nhận SCN cũ. Oracle yêu cầu redo để đưa file tới SCN phù hợp với database và các file liên quan. Nếu cần một archived redo log mà không còn bản sao nào, recovery có thể dừng tại log đó.

Một backup được tạo khi database đang mở có thể là fuzzy backup: các datafile không nhất thiết được copy tại cùng một thời điểm logic. Điều đó không làm backup vô dụng. RMAN ghi nhận thông tin backup và recovery sử dụng redo để đưa các file về trạng thái nhất quán.

## 2. Những thành phần cần cho complete recovery

Để khôi phục một datafile hoặc toàn bộ database, cần hiểu vai trò của các thành phần sau:

| Thành phần | Vai trò trong recovery |
|---|---|
| Datafile backup | Cung cấp bản dữ liệu nền để restore |
| Incremental backup | Có thể rút ngắn lượng redo phải áp dụng hoặc cập nhật bản datafile copy tùy chiến lược backup |
| Archived redo log | Lưu redo đã archive, cần để roll forward qua các log sequence tương ứng |
| Online redo log | Chứa redo gần nhất chưa archive; có thể cần trong một số tình huống để recovery đến thời điểm hiện tại |
| Control file | Lưu cấu trúc database, tên file, checkpoint, log history và thông tin backup nếu dùng control-file repository |
| SPFILE/PFILE | Cung cấp tham số để khởi động instance, gồm vị trí control file và các thiết lập cần thiết |
| RMAN repository | Theo dõi backup, archived log, datafile và metadata recovery |
| Storage/ASM/filesystem | Phải sẵn sàng để nhận file restore và cho Oracle truy cập |

RMAN có thể lấy metadata từ control file hoặc recovery catalog. Recovery catalog là một schema lưu repository tập trung, hữu ích khi quản lý nhiều database hoặc giữ lịch sử backup lâu hơn control file. Nếu control file bị mất, recovery catalog có thể giúp khôi phục metadata, nhưng vẫn cần bản sao control file hoặc autobackup và thông tin định danh database.

### 2.1. Điều kiện quan trọng: ARCHIVELOG và redo đầy đủ

Complete media recovery cho datafile thường cần database ở chế độ `ARCHIVELOG`, cùng bản backup phù hợp và toàn bộ redo cần thiết. Trong chế độ `NOARCHIVELOG`, online redo được tái sử dụng sau khi log switch và không có chuỗi archived log đầy đủ để roll forward tùy ý. Khi đó, phương án thông thường là khôi phục toàn bộ database từ một backup nhất quán được tạo khi database đóng sạch; không thể dựa vào archived redo để hoàn tất media recovery đến thời điểm hiện tại.

Kiểm tra chế độ archive:

```sql
SELECT log_mode,
       open_mode,
       database_role
FROM v$database;
```

Kiểm tra archive destination và trạng thái archive theo cấu hình môi trường. Không nên chỉ nhìn một thư mục archive rồi kết luận redo đã đầy đủ; log sequence có thể được lưu ở FRA, ASM, backup piece hoặc một thiết bị backup khác.

### 2.2. Backup không nằm cùng vùng storage cần bảo vệ

Nếu mọi datafile, control file, archived log và backup đều nằm trên cùng một disk group hoặc cùng một thiết bị lưu trữ, mất storage có thể làm mất cả dữ liệu lẫn khả năng recovery. Một chiến lược backup cần có bản sao ở failure domain khác, ví dụ storage độc lập, thiết bị backup hoặc vị trí off-site theo chính sách tổ chức.

ASM mirroring, RAID, replication và snapshot có thể tăng khả năng chịu lỗi, nhưng không thay thế backup độc lập. Một lệnh xóa nhầm, lỗi logic hoặc sự cố lan truyền có thể ảnh hưởng cả bản sao đồng bộ.

## 3. Xác định phạm vi sự cố trước khi restore

Trước khi chạy lệnh restore/recover, cần trả lời:

1. File nào không truy cập được: một datafile, nhiều datafile, control file, online redo log, tempfile hay toàn bộ disk group?
2. File thuộc tablespace nào? Có phải `SYSTEM`, `SYSAUX`, undo tablespace hoặc tablespace ứng dụng?
3. Database đang `OPEN`, `MOUNT` hay `NOMOUNT`?
4. Datafile có thể offline riêng lẻ hay phải dừng database?
5. File gốc còn tồn tại nhưng lỗi I/O, hay file đã bị xóa/thiết bị mất hoàn toàn?
6. Backup nào có thể dùng và redo sequence nào còn sẵn?
7. Storage đích đã được sửa, tạo lại hoặc mount đúng chưa?
8. Có standby database hoặc bản sao storage nào có thể hỗ trợ không?

### 3.1. Xác định datafile và tablespace

Các view thường dùng:

```sql
SELECT d.file#,
       d.name,
       d.status,
       d.enabled,
       t.name AS tablespace_name
FROM v$datafile d
JOIN v$tablespace t
  ON t.ts# = d.ts#
ORDER BY d.file#;
```

Kiểm tra header và trạng thái recovery:

```sql
SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#,
       name
FROM v$datafile_header
ORDER BY file#;
```

```sql
SELECT file#,
       online_status,
       error,
       change#,
       time
FROM v$recover_file
ORDER BY file#;
```

Các view có thể cho biết file cần recovery hoặc header không đọc được. Nếu instance không thể mount, một số view không truy vấn được; khi đó cần dựa vào alert log, RMAN output, control file backup, storage diagnostics và metadata backup.

### 3.2. Phân biệt datafile với tempfile

Tempfile chứa dữ liệu tạm cho sort, hash join và các operation khác. Tempfile không được recover bằng archived redo như permanent datafile. Nếu tempfile mất, DBA thường có thể tạo lại tempfile hoặc thêm tempfile mới vào temporary tablespace theo quy trình thích hợp.

Ví dụ tạo lại tempfile:

```sql
ALTER TABLESPACE temp
  ADD TEMPFILE '/u02/oradata/DB1/temp02.dbf'
  SIZE 2G AUTOEXTEND ON NEXT 256M MAXSIZE 20G;
```

Đường dẫn, kích thước và cấu hình autoextend chỉ là ví dụ. Hãy dùng vị trí storage và chính sách dung lượng thực tế. Không chạy `RESTORE DATAFILE` cho tempfile như thể đó là permanent datafile.

### 3.3. Kiểm tra backup và archived redo bằng RMAN

Kết nối RMAN:

```text
rman target /
```

Kiểm tra schema và backup:

```rman
REPORT SCHEMA;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST ARCHIVELOG ALL;
```

Kiểm tra file cụ thể:

```rman
LIST BACKUP OF DATAFILE 7;
LIST BACKUP OF ARCHIVELOG FROM SEQUENCE 1200;
```

Số file, sequence và đường dẫn trong ví dụ cần thay bằng giá trị của database thực tế. Backup có thể nằm trên SBT/tape hoặc thiết bị khác nên `LIST` và trạng thái repository cần được đối chiếu với khả năng truy cập thiết bị.

## 4. Mất một datafile không thuộc SYSTEM khi database vẫn mở

Đây là tình huống phổ biến: một datafile thuộc tablespace ứng dụng bị xóa hoặc storage chứa file bị lỗi, trong khi các datafile quan trọng khác vẫn hoạt động.

Nếu database ở `ARCHIVELOG`, control file hiện tại còn sử dụng được và các backup/redo cần thiết còn đầy đủ, có thể offline datafile bị ảnh hưởng, restore và recover riêng file đó. Những tablespace khác vẫn có thể tiếp tục hoạt động tùy loại file, trạng thái database và tác động của sự cố.

### 4.1. Ví dụ: mất datafile số 7

Giả sử datafile số 7 thuộc tablespace `USERS` bị mất. Kiểm tra trước:

```sql
SELECT file#,
       name,
       status
FROM v$datafile
WHERE file# = 7;
```

Nếu database vẫn mở và datafile có thể được offline riêng:

```sql
ALTER DATABASE DATAFILE 7 OFFLINE;
```

Sau đó trong RMAN:

```rman
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

Khi recovery thành công, đưa file online:

```sql
ALTER DATABASE DATAFILE 7 ONLINE;
```

Nếu datafile đã được Oracle đánh dấu offline do lỗi hoặc lệnh offline không thực hiện được vì tình trạng file, cần xác định chính xác trạng thái trong control file và xử lý theo trạng thái thực tế. Không dùng `OFFLINE FOR DROP` cho tình huống muốn phục hồi file; tùy chọn đó thể hiện ý định loại bỏ file khỏi database và có thể dẫn đến mất khả năng recovery file.

### 4.2. Vì sao cần cả RESTORE và RECOVER?

Giả sử backup datafile 7 được tạo ở SCN 5.000.000. Database tiếp tục chạy và datafile bị mất ở SCN 5.300.000. Restore đưa bản datafile tại SCN 5.000.000 trở lại. Nếu đưa file online ngay, header của file không khớp trạng thái hiện tại của database.

`RECOVER DATAFILE 7` áp dụng redo cần thiết để đưa file tiến đến SCN phù hợp. Nếu redo liên tục đến thời điểm hiện tại còn đầy đủ, đây là complete recovery của datafile.

### 4.3. Đưa cả tablespace offline khi cần

Trong một số tình huống, DBA có thể offline cả tablespace thay vì một datafile riêng:

```sql
ALTER TABLESPACE users OFFLINE IMMEDIATE;
```

Sau đó:

```rman
RESTORE TABLESPACE users;
RECOVER TABLESPACE users;
```

Đưa tablespace online sau khi hoàn tất:

```sql
ALTER TABLESPACE users ONLINE;
```

Phương án tablespace-level phù hợp khi cần khôi phục nhiều datafile trong cùng tablespace hoặc muốn kiểm soát trạng thái cả tablespace. Nó không áp dụng cho `SYSTEM` tablespace; `SYSTEM` không thể offline khi database đang mở.

### 4.4. Restore datafile sang vị trí mới

Nếu đường dẫn cũ không còn dùng được, cần chỉ định vị trí mới trước khi restore. Ví dụ RMAN:

```rman
RUN {
  SET NEWNAME FOR DATAFILE 7 TO '/u03/oradata/DB1/users07.dbf';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

`SET NEWNAME` chỉ định đường dẫn restore; `SWITCH DATAFILE` cập nhật repository/control file để database sử dụng file mới. Thư mục đích phải tồn tại, Oracle có quyền ghi và dung lượng phải đủ.

Nếu dùng Oracle Managed Files (OMF) hoặc ASM, có thể dùng cách đặt tên phù hợp với cấu hình và phiên bản, ví dụ tên do Oracle sinh. Không trộn đường dẫn filesystem với ASM alias một cách tùy tiện. Sau switch, kiểm tra `V$DATAFILE.NAME` để xác nhận database tham chiếu đúng vị trí.

## 5. Mất datafile thuộc SYSTEM hoặc sự cố buộc phải dừng database

Datafile thuộc `SYSTEM` chứa data dictionary cần thiết để database vận hành. Không thể offline riêng datafile `SYSTEM` trong khi database đang mở. Khi datafile này mất hoặc hỏng nghiêm trọng, database thường phải được shutdown và khởi động ở trạng thái `MOUNT` để restore/recover.

### 5.1. Trình tự khôi phục datafile SYSTEM

Giả sử datafile số 1 thuộc `SYSTEM` bị mất, current control file vẫn còn và backup/redo đầy đủ:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
```

Trong RMAN:

```rman
RESTORE DATAFILE 1;
RECOVER DATAFILE 1;
```

Sau khi recovery hoàn tất:

```sql
ALTER DATABASE OPEN;
```

Với current control file và complete recovery, thông thường không cần `RESETLOGS`. Nếu RMAN hoặc Oracle báo còn file khác cần recovery, không cố mở database bằng cách bỏ qua lỗi; phải khôi phục đầy đủ các file cần thiết trước.

### 5.2. Khi nhiều datafile hoặc toàn bộ database bị mất

Nếu nhiều datafile bị mất do một storage failure, database có thể không mở được hoặc không thể tiếp tục vận hành an toàn. Khi đó, có thể restore và recover toàn bộ database:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
```

```rman
RESTORE DATABASE;
RECOVER DATABASE;
```

Sau khi complete recovery thành công với current control file:

```sql
ALTER DATABASE OPEN;
```

`RESTORE DATABASE` lấy các datafile cần thiết từ backup; `RECOVER DATABASE` áp dụng redo để đồng bộ. Nếu chỉ một phần file bị mất, có thể chỉ restore/recover file cần thiết thay vì restore mọi datafile. Phạm vi chọn lệnh cần dựa trên danh sách file và mục tiêu recovery.

### 5.3. Datafile thuộc undo tablespace

Undo datafile chứa undo segment cần thiết cho read consistency, rollback transaction và nhiều hoạt động nội bộ. Mất undo datafile có thể ảnh hưởng rộng hơn một bảng ứng dụng, đặc biệt nếu file chứa undo segment đang được sử dụng.

Không nên xử lý undo datafile như một tablespace ứng dụng thông thường mà không kiểm tra trạng thái transaction và undo tablespace đang hoạt động. Nếu database còn mở, đánh giá file/tablespace và trạng thái undo; nếu sự cố ảnh hưởng khả năng mount/open, thực hiện restore/recovery ở mức phù hợp. Tránh xóa hoặc tạo lại undo tablespace trong lúc chưa xác định transaction và dependency, vì có thể làm mất khả năng rollback hoặc gây lỗi khi instance khởi động.

## 6. Mất toàn bộ vùng lưu trữ hoặc disk group ASM

Khi storage hỏng, lỗi có thể không chỉ nằm ở một datafile. Ví dụ, một disk group ASM chứa nhiều datafile, control file và online redo log có thể bị dismount hoặc mất khả năng truy cập. Cần phân biệt lỗi thiết bị vật lý, lỗi ASM disk, lỗi disk group, lỗi filesystem và lỗi đường dẫn.

### 6.1. ASM redundancy và failure group

ASM có thể dùng redundancy `EXTERNAL`, `NORMAL` hoặc `HIGH` tùy disk group và cấu hình. Với `NORMAL`/`HIGH`, ASM có thể duy trì các bản mirror ở các failure group khác nhau để chịu một số dạng lỗi disk. Khi một disk bị hỏng nhưng disk group còn đủ redundancy và các failure group còn lại hoạt động, ASM có thể tiếp tục truy cập dữ liệu hoặc tái cân bằng sau khi thay disk.

Nếu disk group còn hoạt động và file vẫn được ASM bảo vệ, DBA có thể cần xử lý disk failure/rebalance theo hướng dẫn ASM thay vì restore toàn bộ database. Nếu toàn bộ disk group hoặc mọi bản mirror đều mất, ASM không thể tự tái tạo dữ liệu; cần khôi phục storage và restore từ backup.

ASM mirroring không thay thế backup. Nó bảo vệ trước một số lỗi phần cứng theo redundancy đã cấu hình, nhưng không bảo vệ đầy đủ trước xóa nhầm, corruption logic, lỗi phần mềm hoặc sự cố lan rộng.

### 6.2. Kiểm tra disk group

Khi ASM instance và quyền truy cập phù hợp còn hoạt động, DBA có thể xem disk group và disk:

```sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       usable_file_mb
FROM v$asm_diskgroup;
```

```sql
SELECT group_number,
       disk_number,
       name,
       path,
       mount_status,
       header_status,
       mode_status,
       state
FROM v$asm_disk
ORDER BY group_number, disk_number;
```

Trong môi trường RAC, có thể cần xem view global tương ứng hoặc kiểm tra ASM instance trên node thích hợp. Nếu ASM instance không khởi động hoặc disk group không mount được, cần xem alert log ASM, OS/storage logs và trạng thái thiết bị trước khi thực hiện thao tác mount/recreate.

### 6.3. Nếu chỉ một ASM disk bị lỗi

Nếu disk group vẫn đủ redundancy, DBA có thể thay thế disk lỗi và để ASM rebalance. Cú pháp cụ thể phụ thuộc cấu hình và cách quản trị storage. Ví dụ khái niệm:

```sql
ALTER DISKGROUP DATA DROP DISK data_0003;
```

Sau khi thiết bị mới được cấp và nhìn thấy trong ASM:

```sql
ALTER DISKGROUP DATA ADD DISK '/dev/asm/data_new01';
```

Đây là ví dụ minh họa, không phải lệnh để chạy trực tiếp trên hệ thống thật. Phải xác nhận đúng disk path, failure group, redundancy, dung lượng và trạng thái rebalance. Không drop disk còn dữ liệu duy nhất hoặc chưa được mirror an toàn. Nếu redundancy không đủ, thao tác drop có thể làm mất dữ liệu.

### 6.4. Nếu disk group bị mất hoàn toàn

Nếu disk group chứa datafile bị mất hoàn toàn, quy trình tổng quát là:

1. Khôi phục thiết bị hoặc cấp storage mới.
2. Tạo/mount disk group hoặc filesystem đích theo thiết kế.
3. Bảo đảm các thư mục/ASM destination và quyền truy cập sẵn sàng.
4. Khôi phục control file nếu control file cũng bị mất.
5. Mount database.
6. Catalog backup nếu repository không còn nhận diện backup piece.
7. Restore các datafile cần thiết sang storage mới.
8. Recover bằng archived/online redo còn đầy đủ.
9. Kiểm tra file name, trạng thái, alert log và mở database.

Nếu disk group cũ chứa cả Fast Recovery Area, archived log hoặc backup piece, các bản sao đó cũng có thể đã mất. Cần dùng backup nằm ở failure domain khác. Không thể complete recovery chỉ bằng cách tạo lại disk group trống; việc tạo storage mới chỉ khôi phục nơi chứa file, không khôi phục nội dung dữ liệu.

## 7. Khi cần khôi phục control file hoặc SPFILE

Mất control file là sự cố khác với mất datafile. Control file chứa cấu trúc database và thông tin checkpoint/log. Nếu mọi bản multiplexed control file bị mất, database không thể mount bằng control file hiện tại. Cần restore control file từ autobackup hoặc backup phù hợp trước khi restore/recover datafile.

### 7.1. Restore control file từ autobackup

Nếu control file autobackup được cấu hình và biết DBID, một trình tự điển hình khi mất control file có thể là:

```sql
STARTUP NOMOUNT;
```

Trong RMAN:

```rman
SET DBID 1234567890;
RESTORE CONTROLFILE FROM AUTOBACKUP;
```

Sau đó mount database:

```sql
ALTER DATABASE MOUNT;
```

Nếu backup piece không được nhận diện tự động, cần catalog vị trí backup phù hợp hoặc chỉ định handle theo môi trường. Khi restore control file từ backup, repository và thông tin file có thể phản ánh thời điểm cũ; có thể cần catalog lại backup/archived log sau đó.

### 7.2. Recovery khi dùng backup control file

Khi recovery sử dụng backup control file, Oracle thường yêu cầu mở database với `RESETLOGS` sau khi recovery hoàn tất, kể cả khi đã áp dụng redo đến điểm mới nhất có thể. Đây là khác biệt quan trọng với complete recovery dùng current control file.

Ví dụ khái quát:

```rman
RESTORE DATABASE;
RECOVER DATABASE;
```

Sau khi recovery bằng backup control file hoàn tất theo yêu cầu Oracle:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

`RESETLOGS` tạo một incarnation mới và reset log sequence theo cơ chế Oracle. Sau khi mở, cần kiểm tra database/incarnation và thực hiện backup đầy đủ theo chính sách. Không chạy `OPEN RESETLOGS` chỉ vì thấy lệnh trong một hướng dẫn recovery khác; hãy xác định loại control file và recovery mode thực tế.

### 7.3. SPFILE bị mất

Nếu SPFILE bị mất nhưng control file và datafile còn, có thể khởi động bằng PFILE phù hợp hoặc restore SPFILE từ autobackup nếu có. SPFILE không chứa dữ liệu nghiệp vụ, nhưng chứa tham số quan trọng như `CONTROL_FILES`, `DB_NAME`, `DB_UNIQUE_NAME`, `DB_RECOVERY_FILE_DEST` và cấu hình ASM.

Nếu restore SPFILE từ autobackup, cần bảo đảm tham số sau restore phù hợp với đường dẫn storage mới. Không khởi động database với tham số trỏ đến control file hoặc disk group không còn tồn tại.

## 8. Các lệnh RMAN thường dùng trong complete recovery

### 8.1. Kiểm tra và xem trước thao tác restore

```rman
REPORT SCHEMA;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF DATAFILE 7;
LIST ARCHIVELOG ALL;
```

Xem trước file/backup mà RMAN dự kiến sử dụng:

```rman
RESTORE DATABASE PREVIEW;
```

Kiểm tra backup có thể đọc:

```rman
RESTORE DATABASE VALIDATE;
```

`PREVIEW` hỗ trợ xem lựa chọn backup theo repository và trạng thái hiện tại. `VALIDATE` kiểm tra khả năng đọc backup mà không thực hiện restore datafile. Kết quả validate không bảo đảm storage đích có đủ dung lượng hoặc mọi lỗi runtime khác đã được loại trừ.

### 8.2. Restore/recover một datafile

```rman
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

### 8.3. Restore/recover một tablespace

```rman
RESTORE TABLESPACE USERS;
RECOVER TABLESPACE USERS;
```

### 8.4. Restore/recover toàn database

```rman
RESTORE DATABASE;
RECOVER DATABASE;
```

### 8.5. Khôi phục khi backup piece không có trong repository

Nếu backup piece được copy từ nơi khác hoặc repository không ghi nhận, có thể catalog file vào RMAN repository. Ví dụ với filesystem:

```rman
CATALOG START WITH '/backup/DB1/' NOPROMPT;
```

Chỉ catalog vị trí đáng tin cậy, đúng database và đúng backup piece. Với SBT/tape, cần media manager và cấu hình channel phù hợp. Không nên catalog nhầm backup của database khác.

## 9. Redo log bị hỏng không giống datafile bị hỏng

Online redo log chứa redo của các transaction gần nhất. Mất một member trong nhóm multiplexed redo log khác với mất cả group. Nếu chỉ một member bị lỗi và còn member khác hợp lệ, có thể xử lý member lỗi theo hướng dẫn Oracle mà không restore datafile.

Nếu toàn bộ group chứa redo cần thiết bị mất, khả năng recovery phụ thuộc trạng thái group, archived log và thời điểm checkpoint. Mất current online redo có thể khiến complete recovery đến thời điểm hiện tại không còn khả thi nếu redo đó là bản duy nhất của các thay đổi cần thiết.

Không xử lý lỗi redo log bằng cách restore datafile rồi bỏ qua redo. Datafile có thể chứa transaction chưa hoàn tất hoặc chưa đồng bộ với các file khác. Cần xem alert log và trạng thái `V$LOG`, `V$LOGFILE`, `V$ARCHIVED_LOG` để xác định chính xác.

Ví dụ xem redo log group/member:

```sql
SELECT l.group#,
       l.thread#,
       l.sequence#,
       l.status,
       l.archived,
       f.member
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
ORDER BY l.thread#, l.group#, f.member;
```

Không dùng `CLEAR UNARCHIVED LOGFILE` như một cách sửa lỗi chung. Lệnh này có thể làm mất redo cần cho recovery và buộc phải thực hiện recovery strategy khác. Chỉ sử dụng trong tình huống được Oracle hướng dẫn, sau khi đã hiểu tác động và chấp nhận hậu quả dữ liệu.

## 10. Kiểm tra tính sẵn sàng của archived redo

Complete recovery cần chuỗi redo liên tục từ checkpoint của backup đến mục tiêu. Một archive log bị thiếu có thể chặn recovery ngay cả khi datafile backup còn tốt.

Xem archived log:

```sql
SELECT thread#,
       sequence#,
       first_change#,
       next_change#,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
ORDER BY thread#, sequence#;
```

Trong RAC, cần xem từng redo thread. Không được chỉ kiểm tra sequence của thread 1 nếu database có nhiều thread. Một số archived log có thể có nhiều bản copy; cần kiểm tra ít nhất một bản có thể đọc và được RMAN nhận diện.

RMAN có thể restore archived log từ backup khi cần:

```rman
RESTORE ARCHIVELOG FROM SEQUENCE 1200 UNTIL SEQUENCE 1250 THREAD 1;
```

Ví dụ trên chỉ minh họa cú pháp theo một thread; cần thay sequence/thread theo recovery window và database thực tế. Khi recover, RMAN có thể tự restore archived log từ backup nếu cấu hình channel và repository cho phép.

Nếu log sequence cần thiết không còn ở archive, hãy kiểm tra backup archived log, bản copy ở standby, FRA, thiết bị tape và các bản sao khác. Không tự ý nhảy qua log bị thiếu để gọi là complete recovery.

## 11. Recover datafile sang đường dẫn khác khi storage cũ hỏng

Khi filesystem hoặc disk group cũ không thể dùng lại, restore sang vị trí mới là một phần của recovery plan. Phải cập nhật metadata để database tham chiếu đúng file sau restore.

### 11.1. Filesystem

Ví dụ:

```rman
RUN {
  SET NEWNAME FOR DATAFILE 7 TO '/u03/oradata/DB1/users07.dbf';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

Sau đó kiểm tra:

```sql
SELECT file#,
       name,
       status
FROM v$datafile
WHERE file# = 7;
```

### 11.2. ASM/OMF

Với ASM, tên file thường có dạng `+DATA/DB1/DATAFILE/...` hoặc được Oracle Managed Files quản lý. Khi restore sang disk group khác, phải xác định disk group đích đã mount, có đủ `usable_file_mb` và có redundancy phù hợp.

Ví dụ khái niệm dùng OMF destination:

```rman
RUN {
  SET NEWNAME FOR DATAFILE 7 TO '+DATA2';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

Khả năng dùng tên disk group làm OMF destination và cú pháp cụ thể phụ thuộc cấu hình ASM/OMF, phiên bản Oracle và trạng thái file. Hãy xác nhận cú pháp trên phiên bản đang chạy trước khi dùng trong production.

## 12. Block media recovery khi chỉ một số block bị hỏng

Không phải mọi corruption đều yêu cầu restore cả datafile. Nếu chỉ một số block bị hỏng và có backup/redo phù hợp, RMAN hỗ trợ block media recovery để khôi phục các block bị ảnh hưởng.

Ví dụ:

```rman
RECOVER DATAFILE 7 BLOCK 12345;
```

Có thể chỉ định nhiều block theo cú pháp RMAN tương ứng. Block media recovery không thay thế việc xử lý storage đang tiếp tục gây lỗi. Nếu thiết bị vật lý không ổn định, cần khắc phục storage trước hoặc song song với việc phục hồi block.

Kiểm tra corruption có thể dùng `V$DATABASE_BLOCK_CORRUPTION`:

```sql
SELECT file#,
       block#,
       blocks,
       corruption_type
FROM v$database_block_corruption
ORDER BY file#, block#;
```

RMAN cũng có thể validate datafile hoặc database để phát hiện block corruption. `VALIDATE CHECK LOGICAL` kiểm tra thêm một số lỗi logic ở mức block, nhưng tiêu thụ tài nguyên và cần được lên lịch phù hợp.

## 13. Xử lý khi database không thể MOUNT hoặc OPEN

Nếu database không mount được, cần xác định control file, SPFILE, ASM và các file nền tảng có sẵn hay không. Không thể chạy mọi lệnh SQL trong một trạng thái instance chưa mount.

Trình tự điều tra khái quát:

1. Đọc alert log của database và ASM để tìm lỗi đầu tiên, không chỉ lỗi cuối cùng.
2. Kiểm tra instance có khởi động được bằng PFILE/SPFILE hay không.
3. Xác nhận control file còn tồn tại và các bản multiplexed có truy cập được không.
4. Xác nhận ASM disk group/filesystem chứa control file và datafile đã mount.
5. Nếu control file mất, restore control file từ autobackup/recovery catalog.
6. Mount database và xác định danh sách file cần restore.
7. Restore datafile sang vị trí có thể truy cập.
8. Recover bằng redo liên tục.
9. Mở database theo đúng chế độ recovery đã thực hiện.

Nếu chỉ datafile mất nhưng control file và instance vẫn hoạt động, có thể không cần shutdown toàn bộ database. Nếu file thuộc SYSTEM hoặc control file bị mất, thường phải làm việc ở trạng thái MOUNT hoặc NOMOUNT theo đúng trình tự.

## 14. Kiểm chứng sau recovery

Lệnh RMAN kết thúc thành công là tín hiệu quan trọng nhưng chưa phải toàn bộ bước xác nhận. Sau recovery, cần kiểm tra database, datafile, tablespace, alert log và các ứng dụng liên quan.

### 14.1. Kiểm tra trạng thái database

```sql
SELECT name,
       open_mode,
       database_role,
       log_mode,
       resetlogs_change#,
       resetlogs_time
FROM v$database;
```

### 14.2. Kiểm tra datafile và header

```sql
SELECT file#,
       name,
       status,
       enabled
FROM v$datafile
ORDER BY file#;
```

```sql
SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#,
       name
FROM v$datafile_header
ORDER BY file#;
```

### 14.3. Kiểm tra file còn cần recovery

```sql
SELECT file#,
       online_status,
       error,
       change#,
       time
FROM v$recover_file;
```

Sau khi complete recovery đúng phạm vi, không nên còn file cần media recovery cho database đang chuẩn bị mở bình thường. Nếu view vẫn báo file cần recovery, hãy xác định file đó và lý do; không cố ép online.

### 14.4. Kiểm tra tablespace

```sql
SELECT tablespace_name,
       status,
       contents
FROM dba_tablespaces
ORDER BY tablespace_name;
```

```sql
SELECT file_id,
       file_name,
       tablespace_name,
       status,
       online_status
FROM dba_data_files
ORDER BY file_id;
```

Kiểm tra tablespace cần online đã ở trạng thái phù hợp. `SYSTEM` và các tablespace quan trọng phải ở trạng thái cần thiết để database hoạt động bình thường. Một tablespace ứng dụng có thể vẫn được để offline có chủ đích nếu chưa hoàn tất xử lý storage.

### 14.5. Validate sau recovery

Có thể dùng RMAN để validate:

```rman
VALIDATE DATABASE;
```

Hoặc kiểm tra logic:

```rman
VALIDATE CHECK LOGICAL DATABASE;
```

Đây là thao tác có thể tiêu thụ I/O và CPU đáng kể trên database lớn. Hãy chọn phạm vi validate và thời điểm chạy phù hợp. Kiểm tra alert log, OS/storage log, backup status và các truy vấn nghiệp vụ đại diện sau khi database mở.

## 15. Những tình huống không thể complete recovery

Complete recovery chỉ khả thi khi có đủ bản dữ liệu nền và redo cần thiết. Một số trường hợp làm mục tiêu này không thể thực hiện:

- Không còn backup datafile phù hợp hoặc mọi bản backup đều hỏng.
- Một hoặc nhiều archived redo log cần thiết bị mất và không có bản sao khác.
- Online redo log duy nhất chứa thay đổi cần thiết bị mất.
- Storage chứa cả datafile lẫn backup/archive log bị mất và không có bản sao ngoài failure domain.
- Database ở `NOARCHIVELOG` và không có consistent backup phù hợp để khôi phục.
- Control file/repository không thể xác định file và backup, đồng thời không có bản sao metadata cần thiết.

Trong các tình huống đó, DBA phải xác định điểm recovery mới nhất có thể đạt được và mức mất dữ liệu có thể chấp nhận. Có thể cần incomplete recovery, restore từ standby, khôi phục bản sao storage hoặc phương án disaster recovery khác. Không nên tuyên bố “complete recovery thành công” nếu đã bỏ qua một đoạn redo cần thiết.

## 16. Những sai lầm cần tránh

| Sai lầm | Hậu quả có thể xảy ra | Cách xử lý đúng |
|---|---|---|
| Restore datafile rồi đưa online ngay | File có checkpoint cũ, không nhất quán với database | Recover bằng redo trước khi online |
| Dùng `OPEN RESETLOGS` cho mọi recovery | Thay đổi incarnation không cần thiết hoặc sai trình tự | Chỉ dùng khi recovery path yêu cầu, ví dụ incomplete recovery hoặc backup control file |
| Offline `SYSTEM` khi database đang mở | Không được Oracle hỗ trợ | Shutdown và startup MOUNT để recover |
| Dùng `OFFLINE FOR DROP` khi muốn phục hồi file | Thể hiện ý định bỏ file, làm phức tạp hoặc mất khả năng recovery | Dùng offline/recovery phù hợp, không đánh dấu drop |
| Chỉ kiểm tra archived log của một thread trong RAC | Có thể thiếu redo của thread khác | Kiểm tra sequence theo từng thread |
| Recreate disk group mà không xác minh backup | Có thể phá hủy dữ liệu còn cứu được | Chụp trạng thái, xác minh thiết bị và backup trước khi thay đổi storage |
| Coi ASM mirroring là backup | Không bảo vệ trước mọi lỗi logic hoặc thao tác xóa | Duy trì backup độc lập |
| Restore tempfile như permanent datafile | Dùng sai cơ chế recovery | Tạo lại tempfile theo temporary tablespace |
| Bỏ qua control file hoặc redo log damage | Database có thể không mount/open hoặc thiếu redo | Xác định loại file trước khi chọn recovery path |
| Chạy lệnh RMAN theo ví dụ mà không thay số file/path | Có thể restore nhầm file hoặc ghi đè vị trí không mong muốn | Xác nhận DBID, DB name, file#, path và repository |

## 17. Quy trình chuẩn khi xảy ra mất datafile hoặc storage failure

Một quy trình vận hành có thể được tổ chức như sau:

1. **Bảo toàn hiện trạng:** ghi nhận thời điểm sự cố, alert log, lỗi OS/storage, ASM disk group và trạng thái instance.
2. **Xác định phạm vi:** liệt kê datafile, tablespace, control file, redo log và tempfile bị ảnh hưởng.
3. **Đánh giá khả năng tiếp tục hoạt động:** quyết định offline một file, offline tablespace hay shutdown database.
4. **Khôi phục storage:** sửa filesystem, thay disk, mount disk group hoặc chuẩn bị vị trí đích mới.
5. **Kiểm tra backup:** xác định datafile backup, incremental backup, control file, SPFILE và archived redo có thể đọc.
6. **Kiểm tra chuỗi redo:** bảo đảm log sequence liên tục đến mục tiêu complete recovery, xét từng thread trong RAC.
7. **Chọn phạm vi restore:** datafile, tablespace hay database theo mức độ hư hỏng.
8. **Restore:** đưa bản backup vào đúng vị trí hoặc dùng `SET NEWNAME` và `SWITCH` khi chuyển storage.
9. **Recover:** áp dụng redo bằng RMAN đến mục tiêu cần thiết.
10. **Đưa file/database hoạt động:** online datafile/tablespace hoặc open database theo đúng control file/recovery mode.
11. **Kiểm chứng:** xem trạng thái datafile, header, `V$RECOVER_FILE`, alert log và validate khi phù hợp.
12. **Backup sau recovery:** tạo backup mới và xác nhận archived log/backup policy tiếp tục hoạt động.
13. **Rút kinh nghiệm:** ghi nhận RTO/RPO thực tế, thời gian restore, thời gian apply redo, điểm nghẽn storage và khoảng trống trong backup strategy.

## 18. Bài thực hành: mất một datafile của tablespace USERS

Giả sử database `DB1` đang ở `ARCHIVELOG`, mở bình thường, current control file còn sử dụng được. Datafile số 7 thuộc tablespace `USERS` bị xóa khỏi filesystem. RMAN có backup datafile 7 và archived redo đầy đủ đến thời điểm hiện tại.

### Bước 1: Xác định file

```sql
SELECT d.file#,
       d.name,
       t.name AS tablespace_name
FROM v$datafile d
JOIN v$tablespace t
  ON t.ts# = d.ts#
WHERE d.file# = 7;
```

Xác nhận đây là datafile của `USERS`, không phải `SYSTEM` hoặc datafile của undo tablespace đang hoạt động.

### Bước 2: Offline file

```sql
ALTER DATABASE DATAFILE 7 OFFLINE;
```

Nếu file đã offline do lỗi, kiểm tra trạng thái thay vì lặp lại lệnh một cách máy móc.

### Bước 3: Kiểm tra backup

```rman
LIST BACKUP OF DATAFILE 7;
LIST ARCHIVELOG ALL;
RESTORE DATAFILE 7 PREVIEW;
```

Đảm bảo backup có thể truy cập và redo cần thiết còn đầy đủ.

### Bước 4: Restore và recover

```rman
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

RMAN khôi phục bản datafile từ backup và áp dụng redo cần thiết.

### Bước 5: Online file

```sql
ALTER DATABASE DATAFILE 7 ONLINE;
```

### Bước 6: Kiểm tra

```sql
SELECT file#,
       name,
       status
FROM v$datafile
WHERE file# = 7;
```

```sql
SELECT *
FROM v$recover_file
WHERE file# = 7;
```

Kiểm tra alert log và chạy truy vấn nghiệp vụ đại diện trên tablespace. Sau đó, xác nhận backup job kế tiếp và archived log backup vẫn hoạt động.

## 19. Bài thực hành: mất toàn bộ disk group chứa datafile

Giả sử disk group `DATA` bị mất hoàn toàn, database không thể mount vì các datafile và control file đều nằm trong disk group này. Backup database và control file autobackup nằm trên storage độc lập `/backup/DB1`; archived redo từ backup đến thời điểm sự cố cũng được backup đầy đủ.

Trình tự ở mức khái niệm:

1. Khôi phục hoặc cấp storage mới, tạo disk group đích theo thiết kế ASM.
2. Khôi phục SPFILE hoặc dùng PFILE có các tham số ASM/control file phù hợp.
3. Khởi động instance ở `NOMOUNT`.
4. Restore control file từ autobackup, dùng DBID nếu cần.
5. Mount database.
6. Catalog backup piece nếu repository không nhận diện các file backup.
7. Đặt newname cho datafile sang disk group mới, restore và switch file.
8. Recover database bằng archived/online redo đầy đủ.
9. Mở database theo loại control file và recovery path; nếu dùng backup control file thì xử lý `RESETLOGS` theo yêu cầu Oracle.
10. Validate, kiểm tra file, backup lại database và xác nhận chiến lược bảo vệ storage.

Đây là một kịch bản disaster recovery, không nên thực hiện bằng cách copy lệnh mẫu rồi chạy liên tiếp. Cần có kế hoạch cụ thể cho DBID, autobackup format, channel, ASM disk group, newname, archived log và quyền truy cập thiết bị backup.

## 20. Recovery, RTO và RPO

Complete recovery là mục tiêu kỹ thuật về khả năng đưa database đến điểm hiện tại bằng redo. Trong vận hành, cần gắn nó với hai chỉ tiêu:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa tổ chức chấp nhận mất, đo theo thời gian hoặc điểm dữ liệu.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau sự cố.

Một chiến lược có backup hằng ngày nhưng archived log không được bảo vệ có thể không đạt RPO gần bằng 0. Một database có đầy đủ backup và redo nhưng restore mất nhiều giờ do storage/network chậm có thể không đạt RTO.

Muốn đánh giá thực tế, cần diễn tập restore/recover định kỳ, đo thời gian đọc backup, apply redo, mở database và xác nhận ứng dụng. Chỉ có log “backup completed successfully” không chứng minh rằng toàn bộ hệ thống có thể phục hồi trong thời gian cam kết.

Complete recovery khi mất datafile hoặc hỏng storage là quá trình phối hợp giữa backup, control file, redo, trạng thái instance và hệ thống lưu trữ. DBA phải xác định đúng loại file bị mất, chọn phạm vi restore phù hợp, áp dụng đầy đủ redo và kiểm tra trạng thái sau recovery. Khi giữ được chuỗi redo liên tục và bản backup hợp lệ, Oracle có thể đưa datafile hoặc database trở lại trạng thái nhất quán mà không phải chủ động bỏ các transaction đã commit sau thời điểm backup.
