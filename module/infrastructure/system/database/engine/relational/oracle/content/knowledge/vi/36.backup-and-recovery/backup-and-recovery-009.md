# LIST, REPORT, CROSSCHECK, EXPIRED và OBSOLETE trong RMAN

Oracle Recovery Manager (RMAN) lưu thông tin về các backup và bản sao database trong **RMAN repository**. Repository cho biết backup nào đã được tạo, backup piece nằm ở đâu, backup thuộc database nào, thời điểm hoàn thành, thiết bị lưu trữ, trạng thái và những thông tin cần thiết để RMAN tìm file khi RESTORE hoặc RECOVER.

Thông tin trong repository có thể khác với tình trạng thực tế của file trên disk hoặc tape. Ví dụ, một người quản trị dùng lệnh của hệ điều hành xóa backup file nhưng không thông báo cho RMAN. Repository vẫn ghi file là AVAILABLE, mặc dù file đã mất. Trường hợp ngược lại cũng có thể xảy ra: backup file vẫn còn nhưng thiết bị lưu trữ hoặc media manager tạm thời không truy cập được.

RMAN cung cấp các lệnh **LIST**, **REPORT** và **CROSSCHECK** để kiểm tra inventory, đánh giá khả năng đáp ứng retention policy và đồng bộ trạng thái backup với thiết bị lưu trữ. Sau CROSSCHECK, một backup không tìm thấy có thể mang trạng thái **EXPIRED**. Một backup có thể vẫn tồn tại nhưng không còn cần thiết theo retention policy thì được xem là **OBSOLETE**. Đây là hai khái niệm khác nhau và dẫn đến hai thao tác dọn dẹp khác nhau: DELETE EXPIRED và DELETE OBSOLETE.

Bài học thuộc nhóm **Sao lưu và phục hồi** của Database Engine Relational Oracle. Nội dung tập trung vào cách đọc RMAN repository, cú pháp LIST và REPORT, kiểm tra backup bằng CROSSCHECK, ý nghĩa AVAILABLE/EXPIRED/UNAVAILABLE, retention policy, cách xác định OBSOLETE và quy trình dọn dẹp an toàn.

Sau bài này, bạn có thể:

- Giải thích RMAN repository lưu metadata ở đâu và vai trò của recovery catalog.
- Dùng LIST BACKUP, LIST BACKUP SUMMARY, LIST BACKUP BY FILE và LIST COPY.
- Liệt kê archived redo logs, control file, SPFILE, incarnation và backup theo tag.
- Dùng LIST EXPIRED để xem những record đã được đánh dấu EXPIRED.
- Phân biệt LIST với REPORT và CROSSCHECK.
- Dùng REPORT SCHEMA, REPORT NEED BACKUP, REPORT UNRECOVERABLE và REPORT OBSOLETE.
- Hiểu retention policy theo RECOVERY WINDOW và REDUNDANCY.
- Chọn đúng CROSSCHECK BACKUP, CROSSCHECK COPY và DEVICE TYPE.
- Hiểu trạng thái AVAILABLE, EXPIRED và UNAVAILABLE.
- Biết CROSSCHECK chỉ cập nhật repository, không xóa file hoặc record.
- Phân biệt EXPIRED với OBSOLETE.
- Dùng DELETE EXPIRED để dọn record không còn tìm thấy.
- Dùng DELETE OBSOLETE để xóa backup không còn cần thiết theo retention policy.
- Kiểm tra kênh SBT, media manager, FRA, Data Guard và CDB/PDB trước maintenance.
- Preview restore và xác minh backup trước khi dựa vào nó cho kế hoạch phục hồi.

> **Phạm vi ví dụ:** Các lệnh và ví dụ chủ yếu theo Oracle Database 19c RMAN. Hãy chạy ở RMAN prompt, kết nối đúng TARGET và recovery catalog nếu có. Các lệnh DELETE có thể xóa file vật lý; chỉ thực hiện sau khi kiểm tra retention policy, khả năng restore và yêu cầu lưu trữ của tổ chức.

## 1. RMAN repository là gì?

RMAN repository là tập hợp metadata mà RMAN sử dụng để theo dõi backup, image copy, archived redo log và các đối tượng liên quan đến phục hồi.

### 1.1. Repository trong control file

RMAN luôn lưu repository trong control file của target database. Khi RMAN tạo backup, control file ghi metadata về backup đó. Metadata này giúp RMAN xác định:

- Backup set và backup piece nào đã được tạo.
- Data file, control file, SPFILE hoặc archived log nào được bảo vệ.
- Backup hoàn thành lúc nào.
- Backup nằm trên DISK hay thiết bị SBT/tape.
- Backup piece handle hoặc vị trí file.
- Trạng thái của backup.
- Backup có đáp ứng yêu cầu phục hồi hay không.

Nếu control file bị mất, metadata backup có thể bị mất một phần hoặc toàn bộ tùy vào thời điểm autobackup và cấu hình lưu trữ. Vì vậy, control file autobackup là thành phần quan trọng của chiến lược RMAN.

### 1.2. Recovery catalog

Ngoài control file, có thể cấu hình recovery catalog trong một database riêng. Catalog lưu metadata RMAN trong các bảng thuộc schema catalog.

| Nơi lưu | Đặc điểm |
| --- | --- |
| Target control file | Luôn có; lưu repository của chính target database |
| Recovery catalog | Tùy chọn; lưu metadata tập trung cho một hoặc nhiều target database |

Recovery catalog hữu ích khi:

- Quản lý backup của nhiều database.
- Lưu lịch sử lâu hơn giới hạn record trong control file.
- Theo dõi database incarnation và backup history tập trung.
- Hỗ trợ một số thao tác quản trị và báo cáo qua nhiều database.

LIST, REPORT và CROSSCHECK có thể được dùng với hoặc không có recovery catalog, tùy điều kiện kết nối của từng lệnh. Không có catalog không có nghĩa là RMAN không có repository.

### 1.3. Repository là metadata, không phải bản thân backup

Record trong repository không chứng minh backup file hiện vẫn tồn tại hoặc có thể đọc được. Ví dụ:

1. RMAN tạo backup piece tại /backup/db/full_01.bkp.
2. Control file ghi record backup là AVAILABLE.
3. Quản trị viên xóa file bằng lệnh hệ điều hành.
4. Repository vẫn có record AVAILABLE vì RMAN chưa được thông báo.
5. CROSSCHECK kiểm tra thiết bị, không tìm thấy file và cập nhật record thành EXPIRED.

Đây là lý do phải dùng CROSSCHECK định kỳ, nhất là khi backup được di chuyển, xóa hoặc quản lý bởi công cụ bên ngoài RMAN.

## 2. Bốn khái niệm cần tách biệt

| Lệnh/khái niệm | Câu hỏi được trả lời | Có xóa file không? |
| --- | --- | --- |
| LIST | RMAN đang ghi nhận những backup/object nào? | Không |
| REPORT | Backup hiện tại có đáp ứng chính sách phục hồi không? | Không |
| CROSSCHECK | File mà repository ghi nhận có còn tìm thấy trên thiết bị không? | Không |
| DELETE EXPIRED / DELETE OBSOLETE | Dọn record hoặc backup nào theo điều kiện đã xác định? | DELETE OBSOLETE xóa file vật lý; DELETE EXPIRED chủ yếu dọn record EXPIRED |

Có thể hình dung quy trình:

~~~text
LIST
  |
  v
Xem RMAN repository đang ghi nhận gì
  |
  v
CROSSCHECK
  |
  v
Đối chiếu repository với DISK / SBT
  |
  +------ Không tìm thấy ------> EXPIRED
  |
  +------ Tìm thấy -----------> AVAILABLE
  |
  v
REPORT OBSOLETE
  |
  v
Đánh giá theo retention policy
  |
  +------ Không cần nữa ------> OBSOLETE
  |
  v
Review kết quả và khả năng phục hồi
  |
  v
DELETE EXPIRED hoặc DELETE OBSOLETE
~~~

LIST, REPORT và CROSSCHECK là các thao tác kiểm tra/đánh giá. DELETE là bước maintenance làm thay đổi file hoặc metadata.

## 3. LIST: xem backup trong repository

LIST hiển thị backup và các đối tượng liên quan mà RMAN đã ghi nhận.

### 3.1. Liệt kê tất cả backup

Tại RMAN prompt:

~~~text
RMAN> LIST BACKUP;
~~~

LIST BACKUP hiển thị thông tin backup sets, backup pieces và proxy copies theo phạm vi mặc định. Thông tin thường gồm:

- Backup set key.
- Loại backup.
- Level backup.
- Trạng thái.
- Device type.
- Thời gian hoàn thành.
- Kích thước và thời gian chạy.
- Backup piece handle.
- Tag.
- Các data file hoặc archived log nằm trong backup set.

Đây là lệnh phù hợp khi cần xem chi tiết một inventory backup.

### 3.2. Tóm tắt backup

~~~text
RMAN> LIST BACKUP SUMMARY;
~~~

SUMMARY hiển thị một dòng cho mỗi backup, phù hợp để kiểm tra nhanh:

| Cột thường gặp | Ý nghĩa |
| --- | --- |
| Key | Khóa nhận diện backup set trong repository |
| TY | Loại backup, ví dụ backup set hoặc proxy copy |
| LV | Level backup |
| S | Trạng thái |
| Device Type | DISK hoặc SBT_TAPE |
| Completion Time | Thời điểm hoàn tất |
| #Pieces | Số backup pieces |
| #Copies | Số bản sao |
| Compressed | Backup có được RMAN nén hay không |
| Tag | Tag gắn với backup |

Trong output LIST BACKUP SUMMARY, cột trạng thái thường dùng:

- A: AVAILABLE.
- U: UNAVAILABLE.
- X: các backup pieces trong backup set đã EXPIRED.

SUMMARY giúp phát hiện nhanh backup có trạng thái bất thường, nhưng không thay thế việc xem chi tiết handle hoặc kiểm tra khả năng restore.

### 3.3. Liệt kê theo từng data file

~~~text
RMAN> LIST BACKUP BY FILE;
~~~

BY FILE nhóm backup theo từng data file, archived redo log, control file và SPFILE. Cách xem này hữu ích khi cần xác nhận:

- Data file nào đã được backup.
- File nào chưa có backup gần đây.
- Backup set nào chứa một data file cụ thể.
- Archived log sequence nào có bản backup.
- Trạng thái backup theo từng file.

### 3.4. Liệt kê backup của database

~~~text
RMAN> LIST BACKUP OF DATABASE;
~~~

Lệnh này giới hạn kết quả vào backup của database data files.

### 3.5. Liệt kê backup control file

~~~text
RMAN> LIST BACKUP OF CONTROLFILE;
~~~

Control file backup rất quan trọng khi phải phục hồi repository hoặc mount database sau khi control file hiện tại bị mất.

### 3.6. Liệt kê backup SPFILE

~~~text
RMAN> LIST BACKUP OF SPFILE;
~~~

SPFILE chứa tham số khởi động instance. Nếu mất SPFILE, backup SPFILE giúp khôi phục cấu hình database.

### 3.7. Liệt kê backup archived redo log

~~~text
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

Lệnh hiển thị backup sets chứa archived redo logs. Khi kiểm tra khả năng point-in-time recovery, cần xác định backup data files và chuỗi archived logs có thể sử dụng để phục hồi tới thời điểm mong muốn.

### 3.8. Liệt kê archived redo log đã được archive

~~~text
RMAN> LIST ARCHIVELOG ALL;
~~~

LIST ARCHIVELOG ALL hiển thị archived logs mà repository ghi nhận, không chỉ backup sets chứa archived logs. Có thể kiểm tra sequence, thread, thời gian, trạng thái và vị trí.

### 3.9. Liệt kê image copies

~~~text
RMAN> LIST COPY;
~~~

LIST COPY hiển thị các bản sao file, bao gồm data file copies và archived log copies. Image copy là bản sao file ở dạng file copy, khác với backup set chứa backup pieces theo định dạng RMAN.

Có thể giới hạn:

~~~text
RMAN> LIST COPY OF DATABASE;
RMAN> LIST COPY OF DATAFILE 1;
RMAN> LIST COPY OF ARCHIVELOG ALL;
~~~

### 3.10. Liệt kê theo tag

~~~text
RMAN> LIST BACKUP TAG 'WEEKLY_FULL';
~~~

Tag giúp nhận diện nhóm backup theo lịch hoặc mục đích. Tag không phải retention policy và không tự quyết định backup có obsolete hay không.

### 3.11. Liệt kê backup theo thời gian

~~~text
RMAN> LIST BACKUP COMPLETED AFTER 'SYSDATE-7';
~~~

Ví dụ này lọc backup hoàn thành trong khoảng bảy ngày gần đây. Có thể kết hợp các điều kiện thời gian được hỗ trợ để tìm backup trong một khoảng cụ thể.

### 3.12. Liệt kê record EXPIRED

~~~text
RMAN> LIST EXPIRED BACKUP;
~~~

Hoặc:

~~~text
RMAN> LIST EXPIRED COPY;
~~~

LIST EXPIRED chỉ hiển thị những record repository hiện mang trạng thái EXPIRED. Nếu chưa CROSSCHECK gần đây, kết quả có thể chưa phản ánh tình trạng mới nhất của file trên thiết bị.

### 3.13. Liệt kê database incarnation

~~~text
RMAN> LIST INCARNATION;
~~~

Incarnation thay đổi khi database thực hiện OPEN RESETLOGS. Khi phục hồi về incarnation cũ hoặc xử lý backup từ một nhánh database trước đó, thông tin incarnation giúp xác định đúng lịch sử phục hồi.

### 3.14. LIST FAILURE trong Oracle 19c

Trong các phiên bản trước, RMAN có lệnh LIST FAILURE thuộc Data Recovery Advisor. Tuy nhiên, Oracle Database 19c đã deprecated Data Recovery Advisor và các lệnh LIST FAILURE, ADVISE FAILURE, REPAIR FAILURE, CHANGE FAILURE không còn là workflow được cung cấp như trước. Không nhầm LIST FAILURE với LIST BACKUP hoặc LIST EXPIRED.

## 4. REPORT: đánh giá tình trạng backup và khả năng phục hồi

REPORT trả lời các câu hỏi về mức độ bảo vệ database và backup nào cần được tạo hoặc có thể được dọn theo retention policy.

Các REPORT thường dùng:

- REPORT SCHEMA.
- REPORT NEED BACKUP.
- REPORT UNRECOVERABLE.
- REPORT OBSOLETE.

### 4.1. REPORT SCHEMA

~~~text
RMAN> REPORT SCHEMA;
~~~

REPORT SCHEMA liệt kê tablespaces và data files thuộc database tại thời điểm được yêu cầu. Kết quả thường có:

- File number.
- Tablespace name.
- Data file name.
- Kích thước.
- Trạng thái online/offline theo metadata.

Lệnh này hữu ích khi:

- Kiểm tra database có những data files nào.
- Đối chiếu file number và tablespace.
- Chuẩn bị restore/recover.
- Xác định file mới được thêm vào database nhưng chưa có backup.

Trong Data Guard, có thể dùng FOR DB_UNIQUE_NAME để báo cáo schema của database cụ thể trong môi trường.

### 4.2. REPORT NEED BACKUP

~~~text
RMAN> REPORT NEED BACKUP;
~~~

Lệnh báo cáo các data files cần được backup thêm để đáp ứng retention policy hiện tại.

Ví dụ chỉ kiểm tra một data file:

~~~text
RMAN> REPORT NEED BACKUP DATAFILE 1;
~~~

Hoặc kiểm tra tablespace:

~~~text
RMAN> REPORT NEED BACKUP TABLESPACE USERS;
~~~

Có thể chỉ định tiêu chí:

~~~text
RMAN> REPORT NEED BACKUP RECOVERY WINDOW OF 7 DAYS;
RMAN> REPORT NEED BACKUP REDUNDANCY 2;
RMAN> REPORT NEED BACKUP DAYS 3;
RMAN> REPORT NEED BACKUP INCREMENTAL 2;
~~~

Ý nghĩa:

| Điều kiện | Mục đích |
| --- | --- |
| RECOVERY WINDOW OF n DAYS | Xác định file cần backup để đáp ứng recovery window |
| REDUNDANCY n | Xác định file chưa có đủ số bản backup theo redundancy |
| DAYS n | Xác định file cần nhiều hơn n ngày archived redo logs để phục hồi |
| INCREMENTAL n | Xác định file cần áp dụng nhiều hơn n incremental backups |

Nếu retention policy được cấu hình NONE, REPORT NEED BACKUP không thể xác định file nào cần backup theo policy và sẽ báo lỗi.

### 4.3. REPORT UNRECOVERABLE

~~~text
RMAN> REPORT UNRECOVERABLE;
~~~

Lệnh tìm các data files có hoạt động NOLOGGING hoặc unrecoverable operation kể từ lần backup thích hợp gần nhất.

Ví dụ:

- Direct-path INSERT với NOLOGGING.
- Một số thao tác load dữ liệu không tạo đầy đủ redo.

Vì thao tác NOLOGGING không tạo redo cần thiết để tái tạo block thay đổi, archived redo logs không đủ để phục hồi các block đó. Cần tạo full hoặc incremental backup phù hợp sau operation để bảo vệ dữ liệu.

REPORT UNRECOVERABLE giúp DBA nhận diện file cần backup lại.

### 4.4. REPORT OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
~~~

Lệnh báo cáo các backup và copies không còn cần thiết để đáp ứng retention policy hiện tại.

Ví dụ:

~~~text
RMAN> REPORT OBSOLETE;
RMAN retention policy will be applied to the command
RMAN retention policy is set to redundancy 1
Report of obsolete backups and copies
...
~~~

REPORT OBSOLETE không xóa file. Nó chỉ cho biết RMAN sẽ xem những backup nào là obsolete theo policy.

Có thể xem theo policy khác mà không thay cấu hình mặc định:

~~~text
RMAN> REPORT OBSOLETE RECOVERY WINDOW OF 7 DAYS;
RMAN> REPORT OBSOLETE REDUNDANCY 2;
~~~

Đây là cách thử đánh giá kết quả theo retention policy khác trước khi quyết định thay đổi cấu hình hoặc chạy DELETE OBSOLETE.

### 4.5. REPORT và LIST khác nhau

| LIST | REPORT |
| --- | --- |
| Liệt kê object và metadata trong repository | Đánh giá tình trạng backup theo policy hoặc schema |
| Xem backup set, piece, copy, archived log | Xem file cần backup, file unrecoverable, backup obsolete |
| Hữu ích để tìm key/handle/tag | Hữu ích để quyết định backup/retention |
| Không kết luận một file có đáp ứng recovery window hay không | Có thể đánh giá điều kiện recoverability theo policy |

## 5. CROSSCHECK: đối chiếu repository với thiết bị lưu trữ

CROSSCHECK kiểm tra các backup/copies đã được RMAN ghi nhận có còn tìm thấy trên thiết bị tương ứng hay không.

### 5.1. Mục tiêu

Repository có thể không phản ánh tình trạng vật lý:

- Backup file bị xóa bằng lệnh hệ điều hành.
- Disk mount bị tháo hoặc không truy cập được.
- Tape được chuyển sang kho offsite.
- Media manager catalog không tìm thấy backup piece.
- Backup storage được di chuyển.
- Media manager hoặc channel configuration gặp lỗi tạm thời.

CROSSCHECK cập nhật trạng thái record để RMAN biết backup nào đang có thể truy cập.

### 5.2. CROSSCHECK BACKUP

~~~text
RMAN> CROSSCHECK BACKUP;
~~~

Kiểm tra backup sets, proxy copies và image copies đã ghi trong repository, tùy phạm vi object và device channels được cấu hình.

### 5.3. CROSSCHECK BACKUP DEVICE TYPE DISK

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
~~~

Chỉ kiểm tra backup thuộc thiết bị DISK.

### 5.4. CROSSCHECK BACKUP DEVICE TYPE SBT

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE SBT;
~~~

SBT thường đại diện media manager/tape hoặc thiết bị backup tích hợp qua SBT interface. RMAN cần channel và media manager configuration đúng để truy vấn catalog thiết bị.

Nếu chưa cấu hình automatic SBT channel, có thể phải cấp maintenance channel:

~~~text
RMAN> ALLOCATE CHANNEL FOR MAINTENANCE DEVICE TYPE SBT;
RMAN> CROSSCHECK BACKUP;
RMAN> RELEASE CHANNEL;
~~~

Thực tế, cú pháp và channel allocation cần khớp với media manager đang triển khai. Không crosscheck tape bằng cấu hình SBT sai rồi xóa các record bị đánh dấu EXPIRED.

### 5.5. CROSSCHECK COPY

~~~text
RMAN> CROSSCHECK COPY;
~~~

Kiểm tra image copies và các bản sao file được ghi nhận trong repository.

### 5.6. CROSSCHECK từng loại object

~~~text
RMAN> CROSSCHECK COPY OF DATABASE;
RMAN> CROSSCHECK BACKUP OF DATABASE;
RMAN> CROSSCHECK BACKUP OF ARCHIVELOG ALL;
RMAN> CROSSCHECK BACKUP OF DATAFILE 1;
~~~

Có thể thu hẹp phạm vi để kiểm tra một nhóm backup trước khi maintenance.

### 5.7. CROSSCHECK theo backup set hoặc tag

~~~text
RMAN> CROSSCHECK BACKUPSET 1338, 1339, 1340;
RMAN> CROSSCHECK BACKUPPIECE TAG 'NIGHTLY_BACKUP';
~~~

Dùng LIST để lấy key, tag hoặc handle chính xác trước khi crosscheck phạm vi hẹp.

## 6. CROSSCHECK làm gì và không làm gì?

### 6.1. Nếu tìm thấy file

Nếu CROSSCHECK tìm thấy backup file hoặc media manager xác nhận backup có trong catalog, repository có thể được cập nhật thành AVAILABLE.

Ví dụ, backup trước đó EXPIRED do storage tạm thời không truy cập được. Sau khi storage hoạt động trở lại và CROSSCHECK tìm thấy file, trạng thái có thể trở lại AVAILABLE.

### 6.2. Nếu không tìm thấy file

Nếu CROSSCHECK không tìm thấy file hoặc media manager báo backup không tồn tại, repository record được cập nhật thành EXPIRED.

### 6.3. CROSSCHECK không xóa file vật lý

CROSSCHECK không xóa file trên disk/tape và cũng không xóa record trong repository. Nó chỉ đồng bộ trạng thái.

Muốn xóa record EXPIRED, dùng DELETE EXPIRED. Muốn xóa backup còn tồn tại nhưng không cần theo retention policy, dùng DELETE OBSOLETE.

### 6.4. CROSSCHECK chỉ kiểm tra object đã được ghi nhận

CROSSCHECK không tự tìm mọi file backup bất kỳ trong thư mục hoặc tape library. Nó kiểm tra những object mà RMAN đã biết trong repository.

Nếu có backup được copy thủ công vào storage nhưng chưa catalog, dùng CATALOG để đăng ký record trước khi RMAN có thể quản lý nó theo repository.

### 6.5. CROSSCHECK không phải VALIDATE

CROSSCHECK kiểm tra khả năng tìm thấy file/backup metadata theo thiết bị. Nó không đọc toàn bộ backup để xác minh mọi block đều không corrupt.

Để kiểm tra tính toàn vẹn vật lý, có thể dùng:

~~~text
RMAN> VALIDATE BACKUPSET 123;
~~~

Hoặc:

~~~text
RMAN> BACKUP VALIDATE DATABASE;
~~~

Để kiểm tra backup có thể được dùng cho restore, cần xem xét RESTORE ... VALIDATE hoặc RESTORE ... PREVIEW theo mục tiêu.

## 7. Trạng thái AVAILABLE, EXPIRED và UNAVAILABLE

Đây là các trạng thái availability trong RMAN repository.

### 7.1. AVAILABLE

AVAILABLE nghĩa là RMAN repository coi backup có thể truy cập để restore/recover theo trạng thái hiện tại.

Nó không phải bằng chứng rằng:

- Tất cả block trong backup đều đọc được.
- Media không bị corruption.
- Backup có đầy đủ archived logs để phục hồi đến mọi thời điểm.
- Backup đáp ứng mọi yêu cầu nghiệp vụ.

Muốn xác minh sâu hơn, dùng VALIDATE và kiểm thử restore.

### 7.2. EXPIRED

EXPIRED nghĩa là CROSSCHECK không tìm thấy file hoặc media manager không xác nhận được backup.

EXPIRED là trạng thái repository. Nó không tự xóa file và cũng không chứng minh file bị hỏng. Một backup có thể bị đánh dấu EXPIRED vì:

- Storage tạm thời offline.
- NFS mount chưa được gắn.
- Tape chưa được mount hoặc media manager không truy cập được.
- SBT channel PARMS sai.
- Sai credential hoặc cấu hình media manager.
- File thực sự đã bị xóa.

Trước khi xóa record EXPIRED, phải xác minh lý do file không được tìm thấy.

### 7.3. UNAVAILABLE

UNAVAILABLE là trạng thái được DBA đặt để cho RMAN biết backup tạm thời không thể sử dụng hoặc đã chuyển ra ngoài phạm vi truy cập hiện tại.

Ví dụ:

- Backup đã được chuyển sang kho offsite.
- Disk volume đang bảo trì.
- Tape nằm ở kho lưu trữ chưa thể mount.

Đặt UNAVAILABLE:

~~~text
RMAN> CHANGE BACKUPSET 12 UNAVAILABLE;
~~~

Khi backup quay trở lại:

~~~text
RMAN> CHANGE BACKUPSET 12 AVAILABLE;
~~~

RMAN không dùng file UNAVAILABLE cho RESTORE hoặc RECOVER. Các file trong Fast Recovery Area không thể được đánh dấu UNAVAILABLE theo cơ chế này.

### 7.4. So sánh trạng thái

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| AVAILABLE | Repository coi backup có thể sử dụng | Có thể xem xét cho restore; validate khi cần |
| EXPIRED | CROSSCHECK không tìm thấy backup | Kiểm tra storage/channel; crosscheck lại hoặc DELETE EXPIRED record |
| UNAVAILABLE | DBA chủ động đánh dấu tạm thời không dùng được | Khi backup quay lại, CHANGE ... AVAILABLE |

### 7.5. Trạng thái khác với OBSOLETE

AVAILABLE/EXPIRED/UNAVAILABLE nói về khả năng truy cập hoặc trạng thái file trong repository.

OBSOLETE nói về nhu cầu lưu giữ theo retention policy. Một backup có thể:

- AVAILABLE và OBSOLETE.
- AVAILABLE và không OBSOLETE.
- EXPIRED và record vẫn đang tồn tại.
- UNAVAILABLE dù file thực tế vẫn còn ở kho offsite.

Do đó không thể suy luận OBSOLETE chỉ từ trạng thái AVAILABLE hoặc EXPIRED.

## 8. EXPIRED: quy trình xử lý và dọn record

### 8.1. Tìm record EXPIRED

~~~text
RMAN> LIST EXPIRED BACKUP;
RMAN> LIST EXPIRED COPY;
~~~

Có thể kiểm tra bằng các view RMAN repository:

~~~sql
SELECT
    recid,
    stamp,
    status,
    device_type,
    handle
FROM v$backup_piece
WHERE status = 'X'
ORDER BY completion_time DESC;
~~~

V$BACKUP_PIECE là view có metadata backup piece; status code trong view có thể dùng ký tự nội bộ như A, X, D. Đối chiếu tài liệu reference của release trước khi viết automation dựa vào status code.

Một view khác trong Oracle 19c:

~~~sql
SELECT
    file#,
    status,
    device_type,
    filename
FROM v$backup_files
WHERE status = 'EXPIRED';
~~~

Tên cột và phạm vi dòng trả về tùy loại record; hãy kiểm tra V$BACKUP_FILES reference nếu dùng trong script quản trị.

### 8.2. Vì sao không xóa EXPIRED ngay?

Một record có thể bị đánh dấu EXPIRED do lỗi tạm thời. Ví dụ:

1. NFS backup mount bị mất kết nối.
2. DBA chạy CROSSCHECK.
3. RMAN không truy cập được file và đánh dấu EXPIRED.
4. NFS mount được khôi phục.
5. File backup thực tế vẫn tồn tại.

Nếu xóa record ngay, RMAN sẽ không còn metadata tương ứng để sử dụng file theo record cũ. Hãy khôi phục kết nối storage và CROSSCHECK lại trước.

### 8.3. CROSSCHECK lại sau khi sửa storage

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> LIST EXPIRED BACKUP;
~~~

Nếu file tìm thấy lại, trạng thái có thể trở về AVAILABLE. Nếu vẫn không tìm thấy, kiểm tra handle, mount, permission và cấu hình backup destination.

### 8.4. DELETE EXPIRED

Sau khi xác minh backup thực sự không còn và record cần được dọn:

~~~text
RMAN> DELETE EXPIRED BACKUP;
~~~

Hoặc chỉ dọn expired copies:

~~~text
RMAN> DELETE EXPIRED COPY;
~~~

DELETE EXPIRED xóa record EXPIRED khỏi repository. Nếu một file được đánh dấu EXPIRED nhưng thực tế vẫn tồn tại, RMAN cảnh báo và không xóa file vật lý đó.

### 8.5. DELETE EXPIRED không phải công cụ xóa file hiện hữu

Không dùng DELETE EXPIRED với mục tiêu giải phóng dung lượng của các file backup còn tồn tại. Nếu file hiện hữu và cần được xóa theo retention policy, hãy đánh giá bằng REPORT OBSOLETE rồi dùng DELETE OBSOLETE khi phù hợp.

## 9. OBSOLETE: backup không còn cần thiết theo retention policy

OBSOLETE là kết quả đánh giá backup theo chính sách lưu giữ được cấu hình hoặc chỉ định trong lệnh REPORT/DELETE.

### 9.1. Ví dụ backup vẫn còn nhưng đã obsolete

Giả sử:

- Retention policy là REDUNDANCY 1.
- Có ba full backups thành công.
- Backup cũ hơn không còn cần thiết để giữ một bản backup đáp ứng policy.
- File cũ vẫn tồn tại trên disk.

Backup cũ có thể được đánh giá OBSOLETE dù file vật lý còn nguyên vẹn và repository vẫn ghi AVAILABLE.

### 9.2. OBSOLETE không có nghĩa backup bị lỗi

Backup OBSOLETE vẫn có thể đọc được và có thể restore. Nó chỉ không còn cần thiết để đáp ứng retention policy hiện tại.

### 9.3. REPORT OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
~~~

Lệnh này cho biết những backup sets, backup pieces, data file copies và archived logs được xem là obsolete theo policy.

### 9.4. DELETE OBSOLETE

~~~text
RMAN> DELETE OBSOLETE;
~~~

DELETE OBSOLETE xóa backup vật lý khỏi disk hoặc yêu cầu media manager xóa backup trên SBT, đồng thời cập nhật repository:

- File backup bị xóa khỏi media.
- Record tương ứng được đánh dấu DELETED trong control file.
- Record trong recovery catalog được cập nhật/xóa tương ứng.

DELETE OBSOLETE là thao tác destructive. Hãy chạy REPORT OBSOLETE trước, kiểm tra output và xác nhận policy đúng.

## 10. Retention policy: cơ sở xác định OBSOLETE

RMAN retention policy xác định những backup nào phải được giữ để đáp ứng yêu cầu phục hồi.

Có hai dạng chính:

- REDUNDANCY.
- RECOVERY WINDOW.

Ngoài ra có thể đặt NONE để tắt retention policy.

### 10.1. REDUNDANCY

REDUNDANCY xác định số bản backup của mỗi data file cần giữ.

Ví dụ:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

RMAN giữ đủ hai bản backup phù hợp cho mỗi data file theo quy tắc retention. Các backup cũ hơn có thể trở thành obsolete khi không còn cần để duy trì redundancy.

Default retention policy được Oracle tài liệu hóa là REDUNDANCY 1, nhưng cấu hình thực tế có thể đã được DBA thay đổi.

### 10.2. RECOVERY WINDOW

RECOVERY WINDOW xác định khoảng thời gian mà database cần có khả năng phục hồi về một thời điểm trong quá khứ.

Ví dụ:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
~~~

Ý nghĩa là phải duy trì đủ backup và archived redo logs để có thể phục hồi tới bất kỳ thời điểm nào trong recovery window bảy ngày, theo điều kiện phục hồi của RMAN.

Không hiểu RECOVERY WINDOW OF 7 DAYS đơn giản là chỉ giữ các backup được tạo trong bảy ngày gần nhất. Để phục hồi tới thời điểm ở đầu cửa sổ, RMAN có thể phải giữ một full backup được tạo trước thời điểm đó cùng chuỗi archived redo logs cần thiết.

### 10.3. So sánh REDUNDANCY và RECOVERY WINDOW

| Policy | Đặt theo | Câu hỏi chính |
| --- | --- | --- |
| REDUNDANCY 2 | Số bản backup | Cần giữ bao nhiêu bản backup? |
| RECOVERY WINDOW OF 7 DAYS | Thời gian phục hồi | Cần phục hồi được về thời điểm nào trong quá khứ? |

REDUNDANCY phù hợp khi yêu cầu chính là số bản backup. RECOVERY WINDOW phù hợp khi yêu cầu nghiệp vụ là thời gian có thể quay lại.

### 10.4. NONE

~~~text
RMAN> CONFIGURE RETENTION POLICY TO NONE;
~~~

NONE tắt retention policy. Khi không có retention policy, RMAN không thể xác định backup nào obsolete theo policy mặc định. REPORT OBSOLETE không có policy để đánh giá sẽ báo lỗi.

Không đặt NONE chỉ để tránh báo obsolete. Cần có quy trình lưu giữ thay thế được DBA và business owner phê duyệt.

### 10.5. Kiểm tra policy hiện tại

~~~text
RMAN> SHOW RETENTION POLICY;
~~~

Hoặc:

~~~text
RMAN> SHOW ALL;
~~~

SHOW ALL hiển thị các cấu hình RMAN quan trọng khác như device type, control file autobackup, channel, backup optimization và archived log deletion policy.

### 10.6. Thử policy khác trong REPORT

~~~text
RMAN> REPORT OBSOLETE REDUNDANCY 2;
RMAN> REPORT OBSOLETE RECOVERY WINDOW OF 14 DAYS;
~~~

Các tùy chọn này chỉ điều khiển cách REPORT đánh giá kết quả của câu lệnh đó. Chúng không tự thay đổi cấu hình retention policy.

### 10.7. Cẩn thận với policy override trong DELETE

Ví dụ policy đang cấu hình:

~~~text
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
~~~

Nếu chạy:

~~~text
RMAN> DELETE OBSOLETE RECOVERY WINDOW OF 7 DAYS;
~~~

RMAN có thể xóa backup theo recovery window bảy ngày, làm giảm khả năng phục hồi từ bảy đến mười bốn ngày trước. Đây là override có tác động thật đến recoverability, không phải chỉ là lệnh báo cáo.

## 11. Vì sao phải CROSSCHECK trước REPORT OBSOLETE?

Oracle khuyến nghị crosscheck để repository phản ánh tình trạng thực tế của backup trước khi đánh giá và dọn obsolete.

Nếu repository còn ghi một file AVAILABLE nhưng file đã bị xóa ngoài RMAN:

- LIST có thể hiển thị file như thể nó vẫn tồn tại.
- REPORT OBSOLETE có thể đánh giá trên metadata chưa cập nhật.
- DELETE có thể gặp mismatch giữa repository và media.

Quy trình chuẩn:

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK COPY;
RMAN> LIST EXPIRED BACKUP;
RMAN> REPORT OBSOLETE;
~~~

Sau khi xem xét, mới quyết định:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED COPY;
RMAN> DELETE OBSOLETE;
~~~

Không nhất thiết phải chạy tất cả lệnh trong mọi lần maintenance. Chọn phạm vi phù hợp với thiết bị và chính sách lưu trữ.

## 12. DELETE EXPIRED và DELETE OBSOLETE khác nhau thế nào?

| Tiêu chí | DELETE EXPIRED | DELETE OBSOLETE |
| --- | --- | --- |
| Điều kiện | Record có trạng thái EXPIRED | Backup không còn cần theo retention policy |
| Nguồn trạng thái | CROSSCHECK | Retention policy |
| File vật lý | Nếu file thực tế còn tồn tại, RMAN cảnh báo và không xóa file đó | Xóa file backup trên media khi lệnh thành công |
| Repository | Xóa record EXPIRED | Cập nhật record thành DELETED và đồng bộ catalog |
| Mục tiêu | Dọn metadata của backup không tìm thấy | Giải phóng dung lượng từ backup không còn cần |
| Có thể backup còn tồn tại? | Có, nếu crosscheck sai hoặc storage tạm lỗi | Có, thường là file còn nguyên nhưng không cần theo policy |

### 12.1. DELETE EXPIRED BACKUP

~~~text
RMAN> DELETE EXPIRED BACKUP;
~~~

Lệnh này dọn record EXPIRED. Nếu file tồn tại trên media, RMAN cảnh báo mismatch và không xóa file vật lý.

### 12.2. DELETE OBSOLETE

~~~text
RMAN> DELETE OBSOLETE;
~~~

Lệnh này xóa backup không còn cần thiết theo retention policy. Với backup trên tape/SBT, RMAN yêu cầu media manager xử lý xóa.

### 12.3. NOPROMPT

~~~text
RMAN> DELETE NOPROMPT OBSOLETE;
~~~

NOPROMPT bỏ qua bước liệt kê và yêu cầu xác nhận tương tác. Nó không làm lệnh an toàn hơn; chỉ bỏ prompt. Trong command file hoặc scheduler, RMAN không prompt như phiên tương tác nên cần review script và policy trước khi chạy.

### 12.4. FORCE

~~~text
RMAN> DELETE FORCE EXPIRED BACKUP;
~~~

FORCE có thể bỏ qua một số kiểm tra và xóa metadata bất kể tình trạng media; với DELETE nói chung, FORCE có thể bỏ qua I/O errors và archived log deletion policy. Không dùng FORCE như cách sửa lỗi mặc định. Chỉ dùng khi đã hiểu chính xác record/file cần xử lý và có phê duyệt.

## 13. CROSSCHECK với DISK và SBT

Thiết bị lưu trữ khác nhau có cách kiểm tra khác nhau.

### 13.1. DISK

Với backup trên disk, RMAN kiểm tra file tại vị trí được ghi trong repository và có thể kiểm tra header của backup file.

Ví dụ:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
~~~

Nếu backup nằm trên NFS hoặc ASM-related storage, đảm bảo mount và quyền truy cập đúng ở thời điểm crosscheck.

### 13.2. SBT/TAPE

Với SBT, RMAN làm việc với media management software để xác nhận backup tồn tại trong media catalog.

Ví dụ:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE SBT;
~~~

Nếu media manager không truy cập được hoặc channel PARMS sai, backup có thể bị đánh dấu EXPIRED dù tape thực tế vẫn chứa backup.

### 13.3. Channel phải đúng với thiết bị tạo backup

RMAN dùng channel có cùng device type với backup để kiểm tra. Nếu backup được tạo bằng SBT nhưng chỉ có disk channel, cần cấu hình/allocate SBT maintenance channel.

### 13.4. Không xóa EXPIRED từ tape khi media manager đang lỗi

Nếu nhiều backup tape đồng loạt chuyển sang EXPIRED:

1. Dừng quy trình DELETE EXPIRED tự động.
2. Kiểm tra media manager service.
3. Kiểm tra SBT library và credentials.
4. Kiểm tra channel PARMS.
5. Xác nhận tape catalog truy cập được.
6. CROSSCHECK lại.
7. Chỉ dọn record sau khi xác minh backup thực sự không còn.

Đây là một tình huống phổ biến gây mất metadata cần thiết để tìm lại backup trên tape.

## 14. Data Guard và DB_UNIQUE_NAME

Trong Data Guard, mỗi backup gắn với database đã tạo ra backup đó. Primary và standby có thể dùng cùng DBID nhưng DB_UNIQUE_NAME khác nhau.

### 14.1. LIST theo database unique name

~~~text
RMAN> LIST BACKUP FOR DB_UNIQUE_NAME 'STANDBY1';
~~~

Hoặc:

~~~text
RMAN> LIST ARCHIVELOG ALL FOR DB_UNIQUE_NAME 'STANDBY1';
~~~

### 14.2. Crosscheck trong Data Guard

Trong Data Guard, RMAN chỉ có thể cập nhật trạng thái một file từ AVAILABLE sang EXPIRED khi kết nối TARGET tới database liên kết với file đó. Nếu file thuộc database khác trong Data Guard environment, RMAN có thể yêu cầu thực hiện crosscheck khi kết nối đúng target.

### 14.3. Disk và tape accessibility

RMAN có quy tắc accessibility riêng:

- Tape backups có thể được xem là accessible giữa các database trong cùng Data Guard environment tùy media manager.
- Disk backups thường chỉ accessible với database đã tạo chúng.

Không giả định mọi backup trên primary đều có thể được standby crosscheck hoặc restore trực tiếp.

### 14.4. Xác minh trước khi DELETE

Nếu backup được tạo ở standby hoặc primary khác, hãy xác định DB_UNIQUE_NAME và nơi lưu trữ trước khi chạy DELETE. Xóa nhầm backup có thể ảnh hưởng kế hoạch phục hồi của database khác.

## 15. CDB/PDB và backup metadata

Trong Oracle Multitenant, RMAN có thể quản lý backup ở phạm vi CDB và PDB.

### 15.1. Kết nối CDB root

Để xem reporting thông tin backup toàn CDB, kết nối root bằng common user có SYSDBA hoặc SYSBACKUP phù hợp.

~~~text
RMAN> CONNECT TARGET /;
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
~~~

LIST BACKUP từ root có thể hiển thị backup của toàn CDB.

### 15.2. Báo cáo obsolete backup của PDB

Trong Oracle 19c, việc báo cáo/xóa obsolete backups khi kết nối trực tiếp PDB có các giới hạn. Với các thao tác quản lý obsolete backup của PDB, cần kiểm tra tài liệu release cụ thể và thực hiện từ root theo cú pháp được hỗ trợ.

### 15.3. Không nhầm PDB name với DB_UNIQUE_NAME

PDB là pluggable database trong CDB. DB_UNIQUE_NAME nhận diện database trong Data Guard/recovery catalog. Đây là hai phạm vi khác nhau.

## 16. Fast Recovery Area và maintenance

Fast Recovery Area (FRA) là vùng lưu trữ do Oracle quản lý cho các file liên quan đến backup/recovery, ví dụ:

- Archived redo logs.
- RMAN backups.
- Control file autobackups.
- Flashback logs.
- Một số file recovery khác.

### 16.1. Kiểm tra FRA

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;
~~~

### 16.2. Kiểm tra usage theo file type

~~~sql
SELECT
    file_type,
    percent_space_used,
    percent_space_reclaimable,
    number_of_files
FROM v$recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

### 16.3. FRA tự quản lý một số file đủ điều kiện xóa

Nếu FRA được cấu hình, Oracle có thể tự xóa các file đủ điều kiện khi cần dung lượng. Tuy nhiên, database không vi phạm retention policy chỉ để giải phóng quota. Nếu FRA đầy, hãy kiểm tra:

- Backup nào obsolete.
- Archived logs nào đủ điều kiện xóa theo archived log deletion policy.
- Flashback logs và guaranteed restore points.
- FRA space limit và storage capacity.
- Các file bị xóa ngoài RMAN khiến repository stale.

### 16.4. Xóa file bằng hệ điều hành làm repository stale

Nếu dùng lệnh hệ điều hành xóa file trong FRA hoặc backup directory, Oracle không tự động cập nhật mọi RMAN repository record ngay lập tức. CROSSCHECK giúp nhận diện file đã mất và DELETE EXPIRED dọn record.

### 16.5. Không xóa archived log chỉ vì đã backup một lần

Archived log deletion policy có thể yêu cầu backup trên thiết bị cụ thể, hoặc yêu cầu log đã được apply trên standby trong Data Guard. Kiểm tra:

~~~text
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

Các lệnh DELETE ARCHIVELOG và BACKUP ... DELETE INPUT tuân theo policy này khi policy được cấu hình khác NONE, trừ khi dùng FORCE. Không dùng DELETE ARCHIVELOG ALL để xử lý FRA đầy mà chưa xem xét standby và yêu cầu phục hồi.

## 17. Preview restore trước khi dọn backup

LIST và REPORT cho biết metadata và retention status. Nhưng khi chuẩn bị xóa backup quan trọng, nên kiểm tra xem RMAN có thể chọn được backup để restore.

### 17.1. RESTORE DATABASE PREVIEW

~~~text
RMAN> RESTORE DATABASE PREVIEW;
~~~

PREVIEW truy vấn repository và liệt kê backup RMAN sẽ sử dụng cho restore/recovery tại thời điểm hiện tại. Nó không đọc toàn bộ backup file.

### 17.2. PREVIEW SUMMARY

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

SUMMARY cho output gọn hơn về backup được chọn.

### 17.3. RESTORE VALIDATE

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

VALIDATE thực hiện kiểm tra backup mà RMAN sẽ dùng, đọc các backup blocks theo thao tác validate và giúp phát hiện file/block không đọc được.

### 17.4. VALIDATE BACKUPSET

~~~text
RMAN> VALIDATE BACKUPSET 123;
~~~

Dùng khi cần kiểm tra một backup set cụ thể.

### 17.5. PREVIEW không giống VALIDATE

| Lệnh | Có đọc backup file? | Mục tiêu |
| --- | --- | --- |
| RESTORE ... PREVIEW | Không đọc backup contents | Xem RMAN dự định chọn backup nào |
| RESTORE ... VALIDATE | Có đọc/kiểm tra dữ liệu backup theo validate | Xác minh backup có thể đọc được |
| VALIDATE BACKUPSET | Có | Kiểm tra backup set cụ thể |

PREVIEW hữu ích trước DELETE OBSOLETE để kiểm tra backup còn lại có phù hợp cho restore. Tuy nhiên, PREVIEW chỉ phản ánh metadata hiện có; để có bằng chứng mạnh hơn, cần VALIDATE và kiểm thử restore định kỳ.

## 18. Quy trình maintenance an toàn

Một quy trình thực tế có thể gồm các bước:

### Bước 1 — Xác định đúng database

Kết nối đúng TARGET, DBID, DB_UNIQUE_NAME và recovery catalog nếu có. Trong RAC/Data Guard, xác định instance/database sở hữu backup.

### Bước 2 — Xem cấu hình RMAN

~~~text
RMAN> SHOW ALL;
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

### Bước 3 — Kiểm tra backup inventory

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP;
RMAN> LIST COPY;
RMAN> LIST ARCHIVELOG ALL;
~~~

### Bước 4 — CROSSCHECK đúng thiết bị

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> CROSSCHECK COPY;
~~~

Nếu có SBT:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE SBT;
~~~

### Bước 5 — Xem EXPIRED

~~~text
RMAN> LIST EXPIRED BACKUP;
RMAN> LIST EXPIRED COPY;
~~~

Điều tra các file không tìm thấy trước khi xóa record.

### Bước 6 — Báo cáo backup cần thiết

~~~text
RMAN> REPORT NEED BACKUP;
RMAN> REPORT UNRECOVERABLE;
RMAN> REPORT OBSOLETE;
~~~

### Bước 7 — Kiểm tra khả năng restore

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

Với database quan trọng, thực hiện RESTORE ... VALIDATE hoặc kiểm thử restore trên môi trường phục hồi.

### Bước 8 — Dọn record EXPIRED

Chỉ khi đã xác nhận file thực sự không còn:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED COPY;
~~~

### Bước 9 — Dọn OBSOLETE

Chỉ khi retention policy đúng và backup còn lại đáp ứng recovery requirement:

~~~text
RMAN> DELETE OBSOLETE;
~~~

### Bước 10 — Kiểm tra sau maintenance

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST EXPIRED BACKUP;
RMAN> REPORT OBSOLETE;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

Ghi nhận số backup bị xóa, dung lượng giải phóng, record còn EXPIRED và kết quả preview.

## 19. Lập lịch maintenance

Có thể lập lịch maintenance định kỳ nhưng phải tách kiểm tra khỏi xóa.

### 19.1. Công việc kiểm tra hàng ngày

- LIST BACKUP SUMMARY.
- CROSSCHECK BACKUP DEVICE TYPE DISK.
- CROSSCHECK BACKUP DEVICE TYPE SBT nếu có.
- Kiểm tra LIST EXPIRED BACKUP.
- Kiểm tra FRA usage.
- Kiểm tra trạng thái backup job.

### 19.2. Công việc hàng tuần

- REPORT OBSOLETE.
- REPORT NEED BACKUP.
- REPORT UNRECOVERABLE.
- Kiểm tra restore preview.
- Review expired records và storage errors.
- Chỉ xóa obsolete sau khi kiểm tra policy và approval phù hợp.

### 19.3. Tự động hóa

Một RMAN script maintenance có thể dùng:

~~~text
RUN {
    CROSSCHECK BACKUP DEVICE TYPE DISK;
    CROSSCHECK COPY;
    LIST EXPIRED BACKUP;
    REPORT OBSOLETE;
}
~~~

Đây là script kiểm tra, không xóa backup. Khi chuyển sang automation có DELETE, cần log output, kiểm soát policy, review phạm vi và có cơ chế alert khi số file obsolete/expired bất thường.

### 19.4. Không dùng NOPROMPT để che rủi ro

NOPROMPT hữu ích cho scheduler nhưng bỏ bước xác nhận. Trước khi tự động hóa DELETE OBSOLETE, phải:

- Kiểm tra retention policy đã được phê duyệt.
- Kiểm tra archived log deletion policy.
- Kiểm tra backup ngoài site/tape.
- Kiểm tra guaranteed restore points và yêu cầu flashback.
- Kiểm tra recovery window business.
- Có log và cảnh báo sau mỗi lần chạy.

## 20. Một số truy vấn repository hỗ trợ kiểm tra

Ngoài RMAN LIST/REPORT, có thể xem repository qua dynamic performance views và recovery catalog views.

### 20.1. V$BACKUP_SET

~~~sql
SELECT
    recid,
    stamp,
    set_stamp,
    set_count,
    backup_type,
    incremental_level,
    pieces,
    start_time,
    completion_time
FROM v$backup_set
ORDER BY completion_time DESC;
~~~

### 20.2. V$BACKUP_PIECE

~~~sql
SELECT
    recid,
    stamp,
    set_stamp,
    set_count,
    piece#,
    status,
    device_type,
    handle,
    bytes,
    completion_time
FROM v$backup_piece
ORDER BY completion_time DESC;
~~~

### 20.3. V$BACKUP_FILES

~~~sql
SELECT
    file#,
    file_type,
    status,
    device_type,
    completion_time,
    filename
FROM v$backup_files
ORDER BY completion_time DESC;
~~~

V$BACKUP_FILES hợp nhất metadata của nhiều loại backup/copy. Không giả định mọi cột có giá trị cho mọi file type.

### 20.4. Recovery catalog views

Nếu dùng recovery catalog, có thể truy vấn các view RC_ như:

- RC_BACKUP_SET.
- RC_BACKUP_PIECE.
- RC_DATAFILE_COPY.
- RC_ARCHIVED_LOG.
- RC_DATABASE.

Các view này cung cấp metadata của nhiều target database đã đăng ký catalog. Chú ý DB_KEY, DBID và DB_UNIQUE_NAME khi lọc để không trộn backup của nhiều database.

## 21. Các tình huống thực tế

### 21.1. Backup file bị xóa bằng OS

Triệu chứng:

- LIST BACKUP SUMMARY vẫn hiển thị AVAILABLE.
- File không tồn tại trên disk.

Xử lý:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> LIST EXPIRED BACKUP;
~~~

Sau khi xác nhận file thực sự bị xóa:

~~~text
RMAN> DELETE EXPIRED BACKUP;
~~~

### 21.2. Tape media manager tạm thời lỗi

Triệu chứng:

- Nhiều backup SBT chuyển sang EXPIRED.
- Backup catalog của media manager vẫn có record.
- Channel báo lỗi kết nối.

Xử lý:

1. Dừng DELETE EXPIRED job.
2. Sửa media manager/channel.
3. Kiểm tra PARMS và credentials.
4. CROSSCHECK lại SBT.
5. Xác nhận backup trở về AVAILABLE.

### 21.3. Disk backup đã chuyển ra offsite

Nếu file không còn ở vị trí RMAN truy cập được nhưng vẫn được lưu ở kho offsite:

~~~text
RMAN> CHANGE BACKUPSET 12 UNAVAILABLE;
~~~

Khi backup được đưa trở lại:

~~~text
RMAN> CHANGE BACKUPSET 12 AVAILABLE;
RMAN> CROSSCHECK BACKUPSET 12;
~~~

UNAVAILABLE thể hiện tình trạng tạm thời theo quyết định DBA; EXPIRED là kết quả kiểm tra không tìm thấy.

### 21.4. FRA đầy

Không xóa file thủ công ngay. Thực hiện:

1. Kiểm tra V$RECOVERY_FILE_DEST và V$RECOVERY_AREA_USAGE.
2. Kiểm tra retention policy.
3. CROSSCHECK để cập nhật record.
4. REPORT OBSOLETE.
5. Kiểm tra archived log deletion policy và standby apply.
6. Xác minh restore preview.
7. Xóa obsolete hoặc tăng FRA quota/storage theo kế hoạch.

### 21.5. Muốn giữ backup cuối tháng lâu dài

Có thể dùng archival backup với KEEP clause khi tạo backup, hoặc CHANGE ... KEEP để thay đổi trạng thái lưu giữ theo tài liệu. Backup được đánh dấu KEEP có thể được miễn khỏi retention policy thông thường trong thời hạn đã chỉ định.

Ví dụ minh họa:

~~~text
RMAN> CHANGE BACKUPSET 231 KEEP UNTIL TIME 'SYSDATE+180';
~~~

KEEP FOREVER yêu cầu recovery catalog vì control file không thể lưu repository records vô hạn. Không dùng KEEP tùy tiện vì nó có thể làm tăng dung lượng lưu trữ đáng kể.

## 22. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| LIST vẫn hiển thị backup đã xóa | Repository chưa được CROSSCHECK | CROSSCHECK đúng device type |
| CROSSCHECK đánh dấu nhiều backup SBT EXPIRED | Media manager/channel không truy cập được | Dừng delete, kiểm tra media manager và crosscheck lại |
| DELETE EXPIRED không giải phóng dung lượng | File vật lý vẫn tồn tại nhưng record EXPIRED | Dùng REPORT OBSOLETE và DELETE OBSOLETE nếu file không cần |
| REPORT OBSOLETE báo không có retention policy | CONFIGURE RETENTION POLICY TO NONE | Thiết lập policy phù hợp sau khi được phê duyệt |
| Backup AVAILABLE nhưng restore lỗi | File corruption, missing logs hoặc backup không hợp lệ | RESTORE VALIDATE, VALIDATE BACKUPSET và kiểm tra archived logs |
| Backup OBSOLETE vẫn còn trên disk | RMAN chưa được yêu cầu DELETE OBSOLETE hoặc FRA chưa cần reclaim | REPORT rồi DELETE OBSOLETE nếu đủ điều kiện |
| Backup bị đánh dấu UNAVAILABLE | DBA dùng CHANGE UNAVAILABLE hoặc storage offsite | Kiểm tra nơi lưu và CHANGE AVAILABLE khi quay lại |
| CROSSCHECK không tìm thấy file ở RAC | Mount/storage không đồng nhất giữa node | Kiểm tra đường dẫn và storage visibility |
| Không crosscheck được SBT | Thiếu maintenance channel hoặc sai SBT parameters | Cấu hình channel đúng media manager |
| LIST EXPIRED không phản ánh tình trạng mới | Chưa chạy CROSSCHECK sau thay đổi storage | CROSSCHECK rồi LIST lại |
| DELETE OBSOLETE xóa backup cần cho recovery window | Policy hoặc override ngắn hơn yêu cầu | Kiểm tra SHOW RETENTION POLICY và REPORT OBSOLETE |
| Archived logs bị xóa quá sớm | Không xét archive log deletion policy/Data Guard | Kiểm tra policy và trạng thái apply trên standby |
| LIST BACKUP không thấy file copy ngoài RMAN | Backup chưa có repository record | Dùng CATALOG khi phù hợp |

## 23. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| LIST xác nhận file vật lý còn tồn tại | LIST đọc repository; cần CROSSCHECK để đối chiếu media |
| REPORT OBSOLETE xóa backup | REPORT chỉ báo cáo |
| CROSSCHECK xóa file không tìm thấy | CROSSCHECK chỉ cập nhật trạng thái repository |
| EXPIRED nghĩa là backup obsolete | EXPIRED nghĩa không tìm thấy; OBSOLETE nghĩa không cần theo retention |
| OBSOLETE nghĩa là backup hỏng | Backup có thể còn nguyên và restore được |
| DELETE EXPIRED giải phóng dung lượng file hiện hữu | Nó chủ yếu dọn record EXPIRED; file còn tồn tại sẽ được cảnh báo và không bị xóa |
| DELETE OBSOLETE chỉ xóa metadata | Nó xóa backup trên media và cập nhật repository |
| AVAILABLE chứng minh backup có thể restore hoàn chỉnh | Cần validate và kiểm thử restore |
| UNAVAILABLE giống EXPIRED | UNAVAILABLE là trạng thái DBA chủ động đặt; EXPIRED là kết quả crosscheck |
| RECOVERY WINDOW 7 ngày chỉ giữ backup tạo trong 7 ngày | Cần đủ backup và archived redo logs để phục hồi tới thời điểm trong cửa sổ |
| REPORT OBSOLETE RECOVERY WINDOW thay policy mặc định | Chỉ override cách REPORT đánh giá cho câu lệnh đó |
| DELETE OBSOLETE RECOVERY WINDOW ngắn hơn không có rủi ro | Có thể giảm recovery window thực tế |
| CROSSCHECK tự tìm mọi file backup trong thư mục | Nó chỉ kiểm tra các record RMAN đã biết |
| CROSSCHECK và VALIDATE giống nhau | CROSSCHECK kiểm tra availability; VALIDATE đọc/kiểm tra backup |
| FRA tự xóa mọi file khi đầy | Chỉ xóa file đủ điều kiện theo quy tắc retention/deletion policy |

## 24. Checklist trước khi chạy maintenance

**Kết nối và phạm vi**

- Đã kết nối đúng target database chưa?
- DBID và DB_UNIQUE_NAME có đúng không?
- Có dùng recovery catalog không?
- Có phải Data Guard hoặc RAC không?
- Đang kết nối CDB root hay PDB?

**Repository và thiết bị**

- Đã xem SHOW ALL và retention policy chưa?
- Đã LIST BACKUP SUMMARY chưa?
- DISK mount và permission có đúng không?
- SBT/media manager có hoạt động không?
- Maintenance channel có được cấu hình đúng không?
- Có backup đang nằm offsite không?

**Đánh giá recoverability**

- REPORT NEED BACKUP có kết quả gì?
- REPORT UNRECOVERABLE có file nào không?
- REPORT OBSOLETE có đúng với recovery window nghiệp vụ không?
- Archived log deletion policy có bảo vệ standby không?
- RESTORE DATABASE PREVIEW có chọn được backup cần thiết không?
- Có kiểm thử RESTORE VALIDATE gần đây không?

**Trước khi xóa**

- Đã xác minh EXPIRED là thực sự không còn?
- Đã review từng backup OBSOLETE?
- Có backup KEEP hoặc archival cần giữ không?
- Có yêu cầu audit/legal retention không?
- Có phê duyệt cho DELETE không?
- Có log output và kế hoạch rollback/restore không?

## 25. Bài thực hành tổng hợp

Lab này dùng RMAN để quan sát backup, crosscheck, báo cáo expired/obsolete và thực hành maintenance. Chỉ chạy trên database lab có backup test.

### Bước 1 — Kết nối RMAN

~~~text
$ rman target /
RMAN> SHOW ALL;
RMAN> SHOW RETENTION POLICY;
~~~

Nếu dùng recovery catalog, kết nối đúng catalog schema theo quy trình DBA.

### Bước 2 — Liệt kê backup

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP;
RMAN> LIST COPY;
RMAN> LIST ARCHIVELOG ALL;
~~~

Ghi lại backup key, completion time, device type, tag và status.

### Bước 3 — Xem schema và backup cần thiết

~~~text
RMAN> REPORT SCHEMA;
RMAN> REPORT NEED BACKUP;
RMAN> REPORT UNRECOVERABLE;
~~~

### Bước 4 — CROSSCHECK disk

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> CROSSCHECK COPY;
~~~

Nếu lab có SBT, thực hiện crosscheck bằng channel media manager tương ứng.

### Bước 5 — Xem EXPIRED

~~~text
RMAN> LIST EXPIRED BACKUP;
RMAN> LIST EXPIRED COPY;
~~~

Không xóa record nếu chưa xác minh lý do file không tìm thấy.

### Bước 6 — Báo cáo OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
~~~

So sánh với policy khác:

~~~text
RMAN> REPORT OBSOLETE REDUNDANCY 2;
RMAN> REPORT OBSOLETE RECOVERY WINDOW OF 14 DAYS;
~~~

### Bước 7 — Preview restore

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

Xác nhận RMAN còn tìm thấy các backup cần thiết để phục hồi.

### Bước 8 — Dọn EXPIRED trong lab

Chỉ thực hiện nếu các file đã được xác minh là không còn:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED COPY;
~~~

### Bước 9 — Dọn OBSOLETE trong lab

Chỉ thực hiện nếu retention policy của lab đã được xác nhận:

~~~text
RMAN> DELETE OBSOLETE;
~~~

### Bước 10 — Kiểm tra sau maintenance

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST EXPIRED BACKUP;
RMAN> REPORT OBSOLETE;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

Ghi lại kết quả và xác nhận backup còn lại vẫn đáp ứng yêu cầu phục hồi của lab.

## 26. Câu hỏi tự kiểm tra

1. RMAN repository lưu thông tin ở đâu?
2. Recovery catalog khác control file repository thế nào?
3. LIST BACKUP SUMMARY dùng để làm gì?
4. LIST BACKUP BY FILE khác LIST BACKUP SUMMARY thế nào?
5. LIST COPY hiển thị những loại object nào?
6. LIST EXPIRED hiển thị điều gì?
7. REPORT NEED BACKUP kiểm tra gì?
8. REPORT UNRECOVERABLE phát hiện loại operation nào?
9. REPORT OBSOLETE có xóa file không?
10. CROSSCHECK kiểm tra điều gì?
11. CROSSCHECK BACKUP và CROSSCHECK COPY khác nhau thế nào?
12. Khi nào cần SBT maintenance channel?
13. CROSSCHECK có xóa file vật lý không?
14. EXPIRED có nghĩa backup bị corruption không?
15. AVAILABLE có bảo đảm restore thành công không?
16. UNAVAILABLE do ai đặt và dùng khi nào?
17. OBSOLETE được xác định theo yếu tố nào?
18. DELETE EXPIRED có xóa file vật lý còn tồn tại không?
19. DELETE OBSOLETE làm gì?
20. REDUNDANCY 2 có nghĩa gì?
21. RECOVERY WINDOW OF 7 DAYS có nghĩa gì?
22. Vì sao recovery window không đơn giản là giữ backup tạo trong bảy ngày?
23. REPORT OBSOLETE RECOVERY WINDOW có thay đổi cấu hình retention không?
24. DELETE OBSOLETE RECOVERY WINDOW ngắn hơn có rủi ro gì?
25. Vì sao phải CROSSCHECK trước REPORT OBSOLETE?
26. CROSSCHECK khác VALIDATE thế nào?
27. Khi nào dùng RESTORE DATABASE PREVIEW?
28. Khi nào dùng RESTORE DATABASE VALIDATE?
29. Vì sao cần kiểm tra archived log deletion policy trong Data Guard?
30. Vì sao không nên chạy DELETE NOPROMPT OBSOLETE mà không review?

**Gợi ý trả lời:**

1. Luôn trong control file target; có thể có thêm recovery catalog.
2. Recovery catalog là repository bổ sung tập trung, còn control file repository luôn tồn tại.
3. Xem tóm tắt một dòng cho từng backup.
4. BY FILE nhóm backup theo từng data file/log; SUMMARY cho overview từng backup set.
5. Data file copies, archived log copies và image copies.
6. Các record repository đã được đánh dấu EXPIRED.
7. Data files cần backup thêm để đáp ứng retention policy.
8. Các operation NOLOGGING/unrecoverable như direct-path load.
9. Không, chỉ báo cáo.
10. Đối chiếu record repository với file trên disk hoặc media manager.
11. BACKUP kiểm tra backup sets/copies; COPY kiểm tra image copies và các bản sao file.
12. Khi cần kiểm tra/xóa backup trên SBT mà chưa có automatic SBT channel phù hợp.
13. Không.
14. Không; chỉ có nghĩa CROSSCHECK không tìm thấy hoặc không truy cập được.
15. Không; cần validate và kiểm thử restore.
16. DBA chủ động đặt khi file tạm thời không thể truy cập hoặc chuyển offsite.
17. Retention policy.
18. Không; nếu file vẫn tồn tại, RMAN cảnh báo và không xóa file vật lý.
19. Xóa backup vật lý không còn cần theo policy và cập nhật repository.
20. Giữ hai bản backup phù hợp cho mỗi data file.
21. Phải có khả năng phục hồi về thời điểm trong bảy ngày gần nhất theo điều kiện policy.
22. Có thể cần full backup trước đầu cửa sổ và archived logs để phục hồi tới đầu cửa sổ.
23. Không; chỉ override đánh giá trong câu REPORT đó.
24. Có thể giảm khả năng phục hồi so với policy đã cấu hình.
25. Để repository phản ánh tình trạng file thực tế.
26. CROSSCHECK kiểm tra availability; VALIDATE đọc và kiểm tra backup data.
27. Để xem RMAN dự định dùng backup nào mà không đọc backup contents.
28. Để kiểm tra backup RMAN chọn có đọc/validate được không.
29. Để tránh xóa log mà standby chưa apply hoặc policy chưa cho phép.
30. Vì NOPROMPT bỏ bước xác nhận, có thể xóa backup ngoài ý muốn.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Backup and Recovery User's Guide — Reporting on RMAN Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/reporting-rman-operations.html): LIST, REPORT, REPORT NEED BACKUP, REPORT UNRECOVERABLE và REPORT OBSOLETE.
- [Oracle Database 19c Backup and Recovery User's Guide — Maintaining RMAN Backups and Repository Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/maintaining-rman-backups.html): CROSSCHECK, AVAILABLE/EXPIRED, DELETE EXPIRED và DELETE OBSOLETE.
- [Oracle Database 19c Backup and Recovery User's Guide — RMAN Backup Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/rman-backup-concepts.html): retention policy, redundancy và recovery window.
- [Oracle Database 19c Backup and Recovery Reference — LIST](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/LIST.html): cú pháp và output LIST.
- [Oracle Database 19c Backup and Recovery Reference — DELETE](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/DELETE.html): semantics DELETE, EXPIRED, OBSOLETE, FORCE và NOPROMPT.
- [Oracle Database 19c Backup and Recovery Reference — CROSSCHECK](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/CROSSCHECK.html): cú pháp crosscheck và trạng thái repository.
- [Oracle Database 19c Backup and Recovery Reference — REPORT](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/REPORT.html): cú pháp REPORT và các tiêu chí báo cáo.
- [Oracle Database 19c Database Reference — V$BACKUP_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-BACKUP_FILES.html): truy vấn metadata backup.

**Nguyên tắc cần nhớ:** LIST cho biết RMAN repository đang ghi nhận gì; REPORT đánh giá backup có đáp ứng yêu cầu phục hồi và retention policy không; CROSSCHECK đối chiếu record với DISK/SBT. EXPIRED là backup không tìm thấy khi crosscheck, còn OBSOLETE là backup không còn cần theo retention policy. DELETE EXPIRED dọn record EXPIRED; DELETE OBSOLETE xóa backup vật lý không còn cần thiết. Luôn kiểm tra retention policy, thiết bị lưu trữ, archived log deletion policy và khả năng RESTORE trước khi chạy lệnh xóa.
