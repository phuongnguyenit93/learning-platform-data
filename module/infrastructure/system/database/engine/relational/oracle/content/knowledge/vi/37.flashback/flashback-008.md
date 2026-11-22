# Restore point, guaranteed restore point và áp lực dung lượng

Oracle Database hỗ trợ **restore point** để đánh dấu một mốc SCN có ý nghĩa trong vòng đời database. DBA thường tạo restore point trước khi nâng cấp, triển khai thay đổi lớn, chạy migration hoặc thực hiện một thao tác có rủi ro. Nếu cần quay lại trạng thái trước thay đổi, restore point có thể được dùng làm đích cho Flashback Database hoặc một số quy trình RMAN point-in-time recovery.

Có hai loại restore point cần phân biệt:

- **Normal restore point:** lưu tên và SCN của mốc được đánh dấu. Nó giúp tham chiếu lại mốc đó, nhưng không bảo đảm các flashback log cần thiết sẽ được giữ lại.
- **Guaranteed restore point (GRP):** yêu cầu Oracle giữ lại flashback log cần thiết để có thể flashback database về mốc đó, cho đến khi restore point được drop. Cơ chế bảo đảm này tạo áp lực lưu trữ trong Fast Recovery Area (FRA).

GRP rất hữu ích trước một thay đổi có khả năng phải rollback, nhưng nếu giữ quá lâu, flashback log không thể được xóa khi còn cần cho restore point. FRA có thể đầy, làm ảnh hưởng hoạt động archive log, backup và khả năng vận hành database. Vì vậy, tạo GRP phải luôn đi cùng kế hoạch theo dõi dung lượng và thời điểm drop rõ ràng.

## 1. Restore point là gì?

Restore point là một tên gọi gắn với một mốc SCN (System Change Number) trong database. SCN xác định thứ tự thay đổi của database. Khi tạo restore point, Oracle ghi nhận tên, SCN và thông tin liên quan trong control file.

Ví dụ:

~~~sql
CREATE RESTORE POINT before_release;
~~~

Lệnh trên tạo một normal restore point tên BEFORE_RELEASE. Có thể xem mốc này bằng:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database
  FROM v$restore_point
 ORDER BY time DESC;
~~~

Restore point không phải một bản backup độc lập. Nó không sao chép datafile, control file hay redo log. Nó chỉ đánh dấu một mốc để các quy trình phục hồi có thể tham chiếu.

Một restore point có thể được dùng để:

- Xác định SCN trước một release hoặc migration.
- Chỉ định đích cho Flashback Database nếu có đủ flashback log và điều kiện cần thiết.
- Làm mốc trong quy trình RMAN point-in-time recovery.
- Giúp DBA ghi nhận trạng thái database trước một thay đổi quan trọng.

Tên restore point dễ nhớ hơn việc ghi lại một con số SCN dài. Tuy nhiên, cần ghi nhận cả tên, SCN, thời gian và database incarnation trong runbook để tránh nhầm lẫn giữa các môi trường hoặc các lần triển khai.

## 2. Normal restore point

Normal restore point lưu metadata của mốc SCN trong control file. Nó không buộc Oracle phải giữ lại toàn bộ flashback log cần thiết để quay lại mốc đó.

Tạo restore point:

~~~sql
CREATE RESTORE POINT before_patch;
~~~

Kiểm tra:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       preserved
  FROM v$restore_point
 WHERE name = 'BEFORE_PATCH';
~~~

GUARANTEE_FLASHBACK_DATABASE cho biết restore point có phải GRP hay không. PRESERVED là thông tin về trạng thái lưu giữ restore point trong các release có cột này; hãy đối chiếu dictionary của phiên bản đang dùng nếu cấu trúc view khác.

Normal restore point hữu ích khi:

- Chỉ cần lưu mốc SCN để ghi nhận hoặc dùng cho RMAN PITR.
- Không yêu cầu bảo đảm flashback log luôn sẵn có.
- Có backup và archived redo theo chiến lược recovery riêng.
- Muốn tránh ràng buộc lưu trữ lâu dài do GRP tạo ra.

Nếu sau một thời gian flashback log cần thiết đã bị Oracle tái sử dụng hoặc xóa, normal restore point vẫn có thể còn metadata nhưng không thể bảo đảm Flashback Database về mốc đó. DBA phải kiểm tra khả năng thực tế trước khi dựa vào nó.

### Drop normal restore point

Khi không còn cần mốc:

~~~sql
DROP RESTORE POINT before_patch;
~~~

Drop restore point xóa mốc metadata. Nó không xóa datafile hoặc backup. Trước khi drop, xác nhận không còn runbook, release rollback hoặc RMAN operation đang tham chiếu mốc này.

## 3. Guaranteed restore point (GRP)

Guaranteed restore point cũng đánh dấu một SCN, nhưng có thêm cam kết giữ lại flashback log cần thiết để có thể flashback database về mốc đó. Oracle không tự loại bỏ các flashback log còn cần cho GRP chỉ vì chúng đã cũ hơn DB_FLASHBACK_RETENTION_TARGET.

Tạo GRP:

~~~sql
CREATE RESTORE POINT before_upgrade
  GUARANTEE FLASHBACK DATABASE;
~~~

Kiểm tra:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
  FROM v$restore_point
 WHERE name = 'BEFORE_UPGRADE';
~~~

Nếu GUARANTEE_FLASHBACK_DATABASE là YES, restore point là guaranteed. STORAGE_SIZE cho biết lượng flashback log storage được ghi nhận cho restore point theo cách Oracle tính ở release đó. Giá trị có thể tăng theo thời gian khi database thay đổi.

### GRP có cần bật Flashback Database trước không?

Một đặc điểm quan trọng của Oracle là có thể tạo guaranteed restore point ngay cả khi Flashback Database chưa được bật, miễn là các điều kiện cần thiết như cấu hình Fast Recovery Area được đáp ứng. Khi GRP được tạo, Oracle bắt đầu duy trì flashback log cần thiết để bảo đảm khả năng quay lại mốc đó.

Điều này không có nghĩa mọi cấu hình recovery đều được đáp ứng tự động. DBA vẫn cần kiểm tra ARCHIVELOG mode, FRA, storage, control file, quyền, phiên bản và kế hoạch phục hồi tổng thể.

### GRP không tự động hết hạn

Guaranteed restore point được giữ cho đến khi được drop rõ ràng. Không nên kỳ vọng retention policy thông thường sẽ tự xóa GRP để giải phóng dung lượng.

Nếu GRP không còn cần thiết, phải drop:

~~~sql
DROP RESTORE POINT before_upgrade;
~~~

Sau khi drop, các flashback log không còn cần cho GRP có thể trở thành đối tượng có thể reclaim theo quy tắc quản lý FRA. Dung lượng không nhất thiết giảm ngay lập tức về mức ban đầu; Oracle quản lý việc tái sử dụng và xóa file theo nhu cầu.

## 4. So sánh normal restore point và guaranteed restore point

| Tiêu chí | Normal restore point | Guaranteed restore point |
|---|---|---|
| Lưu tên và SCN | Có | Có |
| Bảo đảm flashback log được giữ | Không | Có, cho đến khi drop |
| Tự động hết hạn theo flashback retention | Không nên dựa vào retention như cam kết; metadata và log là hai vấn đề riêng | Không; phải drop tường minh |
| Tác động dung lượng FRA | Không tạo cam kết giữ log lâu dài | Có thể giữ nhiều flashback log và làm FRA tăng |
| Phù hợp | Đánh dấu SCN, RMAN PITR, mốc tham chiếu | Cửa sổ rollback cần bảo đảm bằng Flashback Database |
| Rủi ro vận hành chính | Đến lúc cần có thể thiếu flashback log | Giữ lâu có thể làm FRA đầy |

Điểm cốt lõi: normal restore point giữ mốc; GRP giữ mốc và buộc Oracle bảo toàn flashback log cần thiết để quay lại mốc đó.

## 5. Flashback Database và mối liên hệ với restore point

Flashback Database là cơ chế đưa database về một thời điểm hoặc SCN trước đó bằng cách sử dụng flashback log và redo theo quy trình Oracle. Nó thường nhanh hơn việc restore toàn bộ datafile từ backup rồi apply redo, nhưng không thay thế backup.

Một số điều kiện quan trọng để dùng Flashback Database:

- Database phải ở ARCHIVELOG mode.
- Fast Recovery Area phải được cấu hình.
- Flashback Database phải được bật, hoặc có GRP được tạo để bảo đảm flashback log theo cơ chế tương ứng.
- Flashback log cần thiết phải còn sẵn có.
- Database phải được đưa về trạng thái phù hợp để thực hiện Flashback Database, thường là MOUNT.
- Phải có quyền và quy trình DBA thích hợp.

Kiểm tra ARCHIVELOG:

~~~sql
SELECT log_mode
  FROM v$database;
~~~

Kiểm tra tham số liên quan:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER db_flashback_retention_target;
SHOW PARAMETER db_flashback;
~~~

DB_FLASHBACK_RETENTION_TARGET là mục tiêu retention theo phút. Đây là mục tiêu mà Oracle cố gắng đáp ứng khi quản lý flashback log; nó không phải cam kết giữ log trong mọi tình huống. GRP tạo cam kết giữ log cần thiết cho mốc cụ thể cho đến khi drop.

### Bật Flashback Database

Quy trình bật Flashback Database thường yêu cầu database ở MOUNT và ARCHIVELOG mode:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE FLASHBACK ON;
ALTER DATABASE OPEN;
~~~

Đây là thao tác thay đổi trạng thái database, cần cửa sổ bảo trì và kế hoạch vận hành. Không chạy nguyên mẫu trên production khi chưa xác nhận Data Guard, RAC, PDB, backup và các điều kiện phiên bản.

Kiểm tra trạng thái:

~~~sql
SELECT flashback_on,
       log_mode,
       open_mode
  FROM v$database;
~~~

FLASHBACK_ON cho biết Flashback Database đang bật theo cấu hình. Nếu đang dùng GRP trong khi Flashback Database chưa bật, cần phân biệt rõ việc GRP giữ log với trạng thái bật Flashback Database toàn cục.

## 6. FRA là gì?

Fast Recovery Area (FRA) là vùng lưu trữ do Oracle quản lý cho các file phục vụ backup và recovery. FRA có thể đặt trên filesystem hoặc ASM disk group tùy cấu hình.

Các loại file thường gặp trong FRA:

- Flashback logs.
- Archived redo logs.
- RMAN backup pieces.
- Image copies.
- Control file autobackup.
- Một số file phục hồi khác theo cấu hình.

FRA có giới hạn dung lượng logic được cấu hình bằng DB_RECOVERY_FILE_DEST_SIZE. Oracle quản lý việc tái sử dụng và xóa file đủ điều kiện theo retention policy, archived log deletion policy và dependency phục hồi.

Kiểm tra cấu hình:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
~~~

Ví dụ:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest = '+FRA'
  SCOPE=BOTH;

ALTER SYSTEM SET db_recovery_file_dest_size = 500G
  SCOPE=BOTH;
~~~

Các giá trị trên chỉ minh họa. Trước khi thay đổi, phải xác nhận ASM disk group hoặc filesystem có đủ dung lượng vật lý, có kế hoạch capacity và thay đổi đã được phê duyệt. Tăng quota logic mà storage bên dưới không đủ có thể chỉ chuyển vấn đề sang tầng storage.

### FRA quota không phải dung lượng vật lý

DB_RECOVERY_FILE_DEST_SIZE là giới hạn dung lượng FRA mà Oracle được phép sử dụng theo cấu hình. Nó không tự mở rộng filesystem hoặc ASM disk group.

Ví dụ, FRA được cấu hình 500 GB nhưng disk group chỉ còn 100 GB trống. Tăng quota lên 800 GB không tạo thêm dung lượng vật lý. Cần theo dõi cả:

- Giới hạn FRA trong Oracle.
- Dung lượng vật lý của filesystem/ASM.
- Mức sử dụng và dung lượng reclaimable.
- Tốc độ tăng flashback log, archived redo và backup.
- Tác động của GRP đang tồn tại.

## 7. Vì sao GRP tạo áp lực dung lượng?

Flashback log lưu thông tin cần thiết để đưa block về trạng thái trước đó. Khi có GRP, Oracle phải giữ các flashback log cần để quay lại mốc SCN của GRP. Những log này không thể bị reclaim chỉ vì vượt quá mục tiêu retention thông thường.

Giả sử:

1. DBA tạo GRP trước khi nâng cấp vào thứ Hai.
2. Database tiếp tục hoạt động với nhiều DML trong các ngày tiếp theo.
3. Các block thay đổi tạo ra flashback log.
4. GRP vẫn cần quay lại mốc thứ Hai.
5. Oracle phải giữ các flashback log cần thiết từ mốc đó.
6. FRA tiếp tục chứa flashback log, archived redo và backup mới.
7. Dung lượng khả dụng giảm dần nếu tốc độ tạo log lớn hơn khả năng reclaim.

GRP càng tồn tại lâu và workload càng thay đổi nhiều, lượng flashback log cần giữ càng có thể lớn. Không chỉ thời gian quyết định dung lượng; tỷ lệ block thay đổi, kích thước block, workload batch, bulk load và các hoạt động ghi dữ liệu đều ảnh hưởng.

### Nhiều GRP cùng tồn tại

Nếu có nhiều guaranteed restore point, GRP cũ nhất có thể buộc Oracle giữ flashback log trong một khoảng dài hơn. Tạo thêm GRP không làm giải phóng log cũ; nó có thể tăng thêm yêu cầu bảo toàn các mốc.

Không nên tạo GRP cho mọi release rồi để tồn tại vô thời hạn. Mỗi GRP phải có owner, mục đích, thời điểm tạo, cửa sổ rollback và người chịu trách nhiệm drop.

## 8. Theo dõi dung lượng FRA

### V$RECOVERY_FILE_DEST

View này cho biết giới hạn và mức sử dụng FRA:

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
  FROM v$recovery_file_dest;
~~~

Các cột chính:

- NAME: vị trí FRA.
- SPACE_LIMIT: giới hạn dung lượng cấu hình.
- SPACE_USED: dung lượng Oracle ghi nhận đang dùng.
- SPACE_RECLAIMABLE: dung lượng có thể được reclaim theo quy tắc FRA tại thời điểm truy vấn.
- NUMBER_OF_FILES: số file trong FRA.

Tính phần trăm sử dụng:

~~~sql
SELECT name,
       ROUND(space_used / NULLIF(space_limit, 0) * 100, 2)
         AS used_pct,
       ROUND(space_reclaimable / NULLIF(space_limit, 0) * 100, 2)
         AS reclaimable_pct,
       ROUND((space_limit - space_used) / 1024 / 1024 / 1024, 2)
         AS free_gb
  FROM v$recovery_file_dest;
~~~

SPACE_RECLAIMABLE không đồng nghĩa toàn bộ dung lượng đó chắc chắn được giải phóng ngay lập tức. Các dependency và trạng thái file có thể ảnh hưởng khả năng reclaim. Hãy đối chiếu alert log và usage theo loại file.

### V$FLASH_RECOVERY_AREA_USAGE

View này phân tách mức sử dụng theo loại file:

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
  FROM v$flash_recovery_area_usage
 ORDER BY percent_space_used DESC;
~~~

Các loại file có thể gồm:

- CONTROLFILE.
- ONLINELOG.
- ARCHIVELOG.
- BACKUPPIECE.
- IMAGECOPY.
- FLASHBACKLOG.
- Một số loại file khác theo release.

Nếu FLASHBACKLOG chiếm tỷ trọng cao và có GRP lâu ngày, cần kiểm tra các restore point và tuổi của mốc trước khi quyết định cleanup.

### Kiểm tra các GRP đang tồn tại

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;
~~~

Đây là truy vấn quan trọng để tìm GRP cũ hoặc không rõ owner. Nếu có nhiều GRP, ghi nhận mốc cũ nhất, mục đích và người chịu trách nhiệm trước khi drop.

## 9. Theo dõi flashback log và nhu cầu ước tính

V$FLASHBACK_DATABASE_LOG cung cấp thông tin về flashback log:

~~~sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
  FROM v$flashback_database_log;
~~~

Các trường giúp hiểu:

- OLDEST_FLASHBACK_SCN/TIME: mốc cũ nhất hiện còn trong flashback log theo thông tin view.
- RETENTION_TARGET: mục tiêu retention theo phút.
- FLASHBACK_SIZE: dung lượng flashback log hiện được ghi nhận.
- ESTIMATED_FLASHBACK_SIZE: ước tính dung lượng cần cho mục tiêu retention dựa trên workload và số liệu hiện có.

Giá trị estimate là dự báo, không phải cam kết dung lượng chính xác cho tương lai. Workload có thể thay đổi mạnh sau khi triển khai hoặc chạy batch.

V$FLASHBACK_DATABASE_STAT có thể dùng để quan sát lượng flashback data và redo trong các khoảng thời gian:

~~~sql
SELECT begin_time,
       end_time,
       flashback_data,
       db_data,
       redo_data,
       estimated_flashback_size
  FROM v$flashback_database_stat
 ORDER BY begin_time DESC;
~~~

View này giúp DBA ước tính tốc độ phát sinh flashback data theo workload. Cột và số liệu có thể khác theo release; kiểm tra dictionary của phiên bản thực tế.

### Ước tính thời gian giữ GRP

Giả sử flashback log tăng trung bình 12 GB mỗi giờ trong một workload thử nghiệm. Nếu còn 120 GB khả dụng dành cho flashback log, khoảng thời gian lý thuyết là 10 giờ. Đây chỉ là phép ước tính đơn giản:

\[
\text{Thời gian dự kiến} \approx
\frac{\text{Dung lượng khả dụng}}{\text{Tốc độ phát sinh flashback log}}
\]

Không dùng phép tính này làm ngưỡng vận hành duy nhất. Phải dự phòng cho archived redo, backup, biến động workload, các file FRA khác và dung lượng storage vật lý. Dùng dữ liệu lịch sử trong giờ cao điểm để ước tính bảo thủ hơn.

## 10. Cảnh báo khi FRA gần đầy

Oracle có thể ghi cảnh báo khi FRA đạt các ngưỡng sử dụng. Trong alert log có thể thấy thông báo liên quan đến mức sử dụng FRA, ví dụ cảnh báo ở mức cao hoặc thông báo không thể reclaim file.

Các lỗi thường gặp:

| Mã lỗi | Ý nghĩa khái quát |
|---|---|
| ORA-19809 | Vượt giới hạn dung lượng recovery file destination |
| ORA-19804 | Không thể reclaim lượng dung lượng yêu cầu từ giới hạn FRA |
| ORA-19815 | Cảnh báo FRA đang tiến gần hoặc vượt ngưỡng sử dụng được thông báo |
| ORA-00257 | Lỗi archiver; thường cần kiểm tra FRA/archive destination và giải phóng dung lượng hợp lệ |
| ORA-38786 | Có thể liên quan điều kiện bật/hoạt động Flashback Database; xem đầy đủ error stack |

Mã lỗi chỉ là dấu hiệu ban đầu. Đọc đầy đủ alert log và RMAN output để biết file type, destination, yêu cầu dung lượng và operation đang thất bại.

### Vì sao FRA đầy có thể ảnh hưởng database?

Nếu FRA không thể reclaim file cần thiết, Oracle có thể không ghi thêm được archived redo vào FRA hoặc không tạo được flashback log mới. Tác động cụ thể phụ thuộc file type, destination, cấu hình archive và workload:

- Archiving có thể thất bại nếu archive destination đầy.
- Database có thể bị ảnh hưởng nghiêm trọng khi log switch không thể hoàn tất do không lưu được archived redo.
- Flashback logging có thể không tiếp tục theo cách cần thiết.
- Backup job có thể thất bại vì không còn chỗ ghi backup piece.
- Các thao tác recovery hoặc maintenance có thể không thực hiện được.

Không nên chờ FRA đạt 100% mới xử lý. Cần cảnh báo sớm và có runbook giải phóng dung lượng an toàn.

## 11. Tại sao không nên xóa file FRA bằng hệ điều hành?

FRA được Oracle quản lý và các file trong đó có dependency với control file, recovery catalog, backup, archived redo và restore point. Xóa file trực tiếp bằng rm, del hoặc công cụ filesystem có thể khiến repository vẫn nghĩ file tồn tại, làm mất khả năng phục hồi hoặc gây lỗi ở các thao tác RMAN sau.

Không làm:

~~~text
rm /fra/ORCL/archivelog/...
del D:\FRA\ORCL\...
~~~

Thay vào đó:

- Dùng RMAN CROSSCHECK để đối chiếu repository với file hiện có.
- Dùng DELETE EXPIRED khi đã xác nhận file không còn tồn tại.
- Dùng DELETE OBSOLETE theo retention policy đã được duyệt.
- Dùng BACKUP ARCHIVELOG và DELETE INPUT theo chính sách backup/deletion phù hợp.
- Drop guaranteed restore point đã hết nhu cầu để Oracle có thể reclaim flashback log không còn bị bảo vệ.

Không chạy DELETE OBSOLETE hoặc DELETE ARCHIVELOG ALL chỉ để giải phóng FRA mà chưa xác nhận backup, archived log deletion policy, Data Guard và nhu cầu PITR.

## 12. Quản lý vòng đời GRP

Một GRP nên có vòng đời rõ ràng:

1. Xác định thay đổi có rủi ro và nhu cầu rollback.
2. Xác nhận database có điều kiện tạo GRP.
3. Kiểm tra dung lượng FRA và tốc độ tăng log.
4. Tạo GRP ngay trước cửa sổ thay đổi.
5. Ghi lại tên, SCN, timestamp, owner và thời điểm hết hạn nội bộ.
6. Thực hiện release/migration.
7. Kiểm tra ứng dụng và dữ liệu.
8. Giữ GRP trong khoảng quan sát đã phê duyệt.
9. Khi rollback window đóng và không còn cần mốc, drop GRP.
10. Theo dõi FRA sau khi drop và lưu bằng chứng.

Ví dụ tạo restore point có tên theo release:

~~~sql
CREATE RESTORE POINT before_release_2026_11_14
  GUARANTEE FLASHBACK DATABASE;
~~~

Ghi nhận:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
  FROM v$restore_point
 WHERE name = 'BEFORE_RELEASE_2026_11_14';
~~~

Sau khi release ổn định và hết cửa sổ rollback:

~~~sql
DROP RESTORE POINT before_release_2026_11_14;
~~~

Tên restore point phải tuân thủ quy tắc đặt tên của Oracle và quy ước nội bộ. Không tái sử dụng tên một cách tùy tiện vì gây nhầm lẫn trong runbook và audit.

### Ai chịu trách nhiệm drop?

Mỗi GRP cần có owner rõ ràng:

- DBA tạo restore point.
- Release owner xác nhận thay đổi đã ổn định.
- DBA kiểm tra không còn yêu cầu rollback.
- Người được phân quyền thực hiện DROP RESTORE POINT.
- Monitoring xác nhận FRA bắt đầu reclaim theo nhu cầu.

Không để việc drop phụ thuộc vào trí nhớ cá nhân. Hãy tạo ticket hoặc lịch nhắc có ngày hết hạn nội bộ.

## 13. Flashback Database về restore point

Khi cần quay lại mốc đã đánh dấu, DBA có thể dùng Flashback Database. Quy trình điển hình:

1. Ngừng ứng dụng và kết nối ghi dữ liệu.
2. Xác nhận đúng database, restore point và SCN.
3. Đưa database về trạng thái MOUNT theo yêu cầu.
4. Thực hiện FLASHBACK DATABASE TO RESTORE POINT.
5. Mở database bằng RESETLOGS theo quy trình.
6. Kiểm tra database, PDB, service và dữ liệu.
7. Thực hiện backup mới sau khi tạo incarnation mới theo chính sách.

Ví dụ khung thao tác:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO RESTORE POINT
  before_release_2026_11_14;

ALTER DATABASE OPEN RESETLOGS;
~~~

Đây là thao tác thay đổi trạng thái và dữ liệu rất lớn. Không chạy ví dụ nguyên trạng trên production. Trước khi thực hiện, phải xác nhận:

- Có đúng restore point và database incarnation.
- Flashback log cần thiết còn sẵn có.
- Database ở ARCHIVELOG và điều kiện Flashback Database đáp ứng.
- Tất cả ứng dụng đã dừng hoặc được cô lập.
- Có phê duyệt rollback và kế hoạch kiểm tra sau phục hồi.
- Có backup phù hợp để xử lý nếu flashback thất bại.

### OPEN RESETLOGS và database incarnation

Sau khi Flashback Database về một mốc trước hiện tại, database thường phải được mở bằng RESETLOGS. Thao tác này tạo database incarnation mới. Các backup và archived redo thuộc incarnation trước cần được quản lý đúng theo RMAN.

Sau khi mở RESETLOGS:

- Kiểm tra database và PDB.
- Kiểm tra service.
- Chạy smoke test và đối soát dữ liệu.
- Ghi nhận incarnation mới.
- Thực hiện backup theo chính sách.
- Kiểm tra RMAN repository và chiến lược backup tiếp theo.

Không giả định các backup cũ tự động trở thành không dùng được; RMAN quản lý incarnation và có thể sử dụng backup theo quy tắc recovery. DBA cần hiểu incarnation hiện tại và mục tiêu phục hồi.

## 14. Guaranteed restore point không thay thế backup

GRP có thể bảo đảm khả năng Flashback Database về mốc khi flashback log còn được bảo vệ, nhưng không bảo vệ trước mọi loại thảm họa:

- Mất toàn bộ storage chứa datafile và FRA.
- Mất control file hoặc metadata cần thiết mà không có bản sao phù hợp.
- Hỏng thiết bị chứa cả database và flashback log.
- Mất encryption wallet/keystore.
- Lỗi hạ tầng khiến cả database và FRA không thể truy cập.
- Lỗi nghiệp vụ hoặc ứng dụng cần khôi phục một phần dữ liệu thay vì toàn database.

GRP không phải bản sao độc lập ở site khác. Nếu database và FRA cùng nằm trên một storage domain rồi storage bị mất, GRP cũng có thể mất.

Vẫn cần:

- RMAN backup định kỳ.
- Backup control file và SPFILE.
- Backup archived redo.
- Bản sao backup ở storage/domain/site độc lập.
- Kiểm tra restore validate.
- Restore drill.
- Bảo vệ TDE wallet/keystore.
- Runbook cho Data Guard hoặc DR nếu có.

Hãy xem GRP là công cụ rollback nhanh cho một cửa sổ thay đổi, còn backup/DR là nền tảng bảo vệ trước mất mát vật lý và thảm họa.

## 15. Restore point và RMAN point-in-time recovery

RMAN có thể dùng restore point làm tên tham chiếu cho mốc recovery. Ví dụ:

~~~text
RMAN> RUN {
  SET UNTIL RESTORE POINT before_release_2026_11_14;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Đây là khung minh họa cho quy trình RMAN PITR. RMAN cần backup và archived redo phù hợp để phục hồi đến SCN của restore point. Normal restore point có thể làm mốc tham chiếu cho RMAN ngay cả khi không có bảo đảm flashback log như GRP, nhưng vẫn cần đầy đủ backup/redo.

Khác biệt:

- Flashback Database dùng flashback log và redo theo cơ chế Flashback để quay lại mốc.
- RMAN PITR restore datafile từ backup rồi apply redo đến điểm đích.
- GRP bảo đảm giữ flashback log cần cho Flashback Database; nó không tạo thêm backup datafile.

Chọn phương pháp theo loại sự cố, RTO/RPO, dung lượng, mức độ ảnh hưởng và khả năng backup/redo.

## 16. Restore point trong CDB và PDB

Trong Oracle Multitenant, restore point có thể được tạo ở phạm vi CDB hoặc PDB tùy phiên bản và loại restore point. Cần xác định rõ:

- Đang kết nối CDB root hay PDB.
- Restore point là toàn CDB hay PDB-specific.
- Phiên bản Oracle có hỗ trợ PDB restore point và guaranteed PDB restore point theo cách cần dùng không.
- PDB có đang ở trạng thái phù hợp không.
- Lệnh Flashback/restore có phạm vi tác động nào.

Không mặc định một restore point tạo trong root chỉ bảo đảm mọi PDB có thể phục hồi độc lập theo cùng cách. Đọc tài liệu Multitenant/Flashback của release cụ thể trước khi thiết kế runbook.

Khi tạo hoặc dùng restore point ở môi trường CDB, cần ghi nhận CON_ID/PDB, SCN, thời điểm và phạm vi. Nếu yêu cầu chỉ rollback một PDB, đánh giá khả năng Flashback PDB hoặc PDB PITR được hỗ trợ trong release thay vì flashback toàn CDB không cần thiết.

## 17. Đánh giá dung lượng trước khi tạo GRP

Trước khi tạo guaranteed restore point, hãy thu thập:

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
  FROM v$recovery_file_dest;

SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
  FROM v$flash_recovery_area_usage
 ORDER BY percent_space_used DESC;

SELECT oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
  FROM v$flashback_database_log;
~~~

Kiểm tra các GRP đang tồn tại:

~~~sql
SELECT name,
       time,
       scn,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;
~~~

Đánh giá:

- FRA còn bao nhiêu dung lượng khả dụng?
- File type nào đang chiếm phần lớn?
- Có GRP cũ nào còn tồn tại?
- Workload sắp tới có bulk load hoặc batch lớn không?
- Cần giữ GRP trong bao lâu?
- Có đủ dung lượng vật lý bên dưới FRA không?
- Archived redo và backup có đang tăng bất thường không?
- Có cảnh báo capacity hoặc job backup nào đang lỗi không?

Nếu dung lượng không đủ, hãy xử lý capacity trước khi tạo GRP. Không tạo GRP rồi mới tìm cách giải phóng dung lượng trong lúc production đã gần đầy.

## 18. Thiết kế cảnh báo áp lực FRA

Một hệ thống monitoring nên cảnh báo theo nhiều ngưỡng, thay vì chỉ cảnh báo khi FRA đầy:

| Mức | Ví dụ ngưỡng | Hành động |
|---|---|---|
| Thông tin | FRA sử dụng vượt 70% | Xem xu hướng và tốc độ tăng |
| Cảnh báo | Vượt 80% hoặc tăng nhanh bất thường | Kiểm tra GRP, flashback log, archive và backup |
| Nghiêm trọng | Vượt 90% hoặc không còn reclaimable space | DBA xử lý ngay theo runbook, đánh giá ảnh hưởng archive |
| Khẩn cấp | ORA-19809/ORA-19804 hoặc archive destination đầy | Kích hoạt incident và xử lý capacity/dependency |

Các ngưỡng chỉ là ví dụ. Cần đặt theo tốc độ tăng dữ liệu, dung lượng, SLA và thời gian phản ứng của đội vận hành.

Monitoring nên ghi nhận theo thời gian:

- SPACE_USED.
- SPACE_RECLAIMABLE.
- SPACE_LIMIT.
- Phần trăm theo file type.
- Số lượng và tuổi GRP.
- STORAGE_SIZE của từng GRP.
- Flashback log generation rate.
- Archived redo generation rate.
- Backup growth và job failure.

Một FRA còn 20% dung lượng có thể vẫn nguy hiểm nếu tốc độ tăng cao và GRP dự kiến giữ thêm 24 giờ. Xu hướng quan trọng không kém tỷ lệ hiện tại.

## 19. Xử lý khi FRA gần đầy hoặc đầy

Khi FRA tăng nhanh, không xóa file bằng hệ điều hành và không drop GRP một cách tự động. Hãy xử lý theo trình tự:

### Bước 1: xác định nguyên nhân

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable
  FROM v$recovery_file_dest;

SELECT file_type,
       percent_space_used,
       percent_space_reclaimable
  FROM v$flash_recovery_area_usage
 ORDER BY percent_space_used DESC;

SELECT name,
       time,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;
~~~

### Bước 2: kiểm tra GRP và rollback window

Liên hệ release owner để xác nhận GRP nào còn cần. Nếu thay đổi vẫn đang trong cửa sổ rollback, không drop chỉ để lấy dung lượng trừ khi đã có quyết định nghiệp vụ và phương án recovery khác.

### Bước 3: kiểm tra file có thể reclaim hợp lệ

Dùng RMAN để crosscheck và đánh giá backup/archived log:

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> REPORT OBSOLETE;
~~~

Các lệnh trên không tự xóa backup. REPORT OBSOLETE cho biết backup nào không còn cần theo retention policy hiện tại. Xác nhận policy, Data Guard và yêu cầu PITR trước khi xóa.

### Bước 4: giải phóng dung lượng theo chính sách

Nếu đã xác nhận backup obsolete:

~~~text
RMAN> DELETE OBSOLETE;
~~~

Nếu một GRP đã hết nhu cầu và được phê duyệt:

~~~sql
DROP RESTORE POINT before_upgrade;
~~~

Nếu archived redo đã được backup đầy đủ và deletion policy cho phép, có thể dùng quy trình RMAN phù hợp để xóa log đủ điều kiện. Không xóa archive log đang cần cho standby hoặc PITR.

### Bước 5: tăng capacity nếu cần

Nếu storage vật lý còn đủ, DBA có thể tăng DB_RECOVERY_FILE_DEST_SIZE theo quy trình:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 700G
  SCOPE=BOTH;
~~~

Con số chỉ minh họa. Xác nhận filesystem/ASM còn dung lượng trước khi tăng quota.

### Bước 6: xác nhận hoạt động bình thường

- Kiểm tra alert log không còn lỗi FRA.
- Kiểm tra archive log có thể tiếp tục.
- Kiểm tra backup job.
- Kiểm tra flashback logging.
- Kiểm tra ứng dụng và session.
- Ghi nhận dung lượng trước/sau và hành động đã thực hiện.

## 20. DROP GRP có giải phóng dung lượng ngay không?

Drop GRP loại bỏ yêu cầu bảo toàn flashback log cho mốc đó. Các flashback log chỉ được giữ vì GRP có thể trở thành file reclaimable. Tuy nhiên, Oracle có thể không xóa toàn bộ ngay lập tức; việc reclaim phụ thuộc nhu cầu không gian, dependency của restore point khác và cơ chế quản lý FRA.

Nếu vẫn còn một GRP cũ hơn, các flashback log cần cho GRP cũ có thể tiếp tục được giữ. Vì vậy, sau khi drop một GRP, hãy kiểm tra lại danh sách GRP và FRA usage:

~~~sql
SELECT name,
       time,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;

SELECT file_type,
       percent_space_used,
       percent_space_reclaimable
  FROM v$flash_recovery_area_usage;
~~~

Đừng kỳ vọng SPACE_USED giảm ngay về 0. Mục tiêu là các file không còn cần cho recovery có thể được Oracle reclaim theo quy tắc.

## 21. Những hiểu lầm thường gặp

**Restore point là backup:** không đúng. Restore point chủ yếu lưu mốc SCN và metadata; nó không tạo bản sao datafile.

**Normal restore point bảo đảm flashback được:** không đúng. Normal restore point không bảo đảm flashback log được giữ lại.

**GRP tự hết hạn theo DB_FLASHBACK_RETENTION_TARGET:** không đúng. GRP cần được drop tường minh.

**Tạo GRP không cần FRA:** không đúng. GRP cần môi trường lưu flashback log phù hợp, bao gồm FRA được cấu hình.

**Flashback Database phải luôn bật trước khi tạo GRP:** không nhất thiết. Oracle cho phép tạo GRP khi Flashback Database chưa bật nếu đáp ứng điều kiện; GRP sẽ yêu cầu giữ flashback log cho mốc đó.

**GRP thay thế RMAN backup:** không đúng. GRP không bảo vệ trước mất storage, site hoặc các thành phần backup.

**FRA đầy thì xóa file cũ bằng OS:** rất nguy hiểm. Dùng RMAN và cơ chế quản lý Oracle.

**Tăng DB_RECOVERY_FILE_DEST_SIZE tự tạo thêm disk:** không đúng. Đây là quota logic, không phải capacity vật lý.

**Drop một GRP luôn giải phóng ngay toàn bộ flashback log:** không đúng. Các GRP khác hoặc dependency có thể tiếp tục giữ log.

**FLASHBACK RETENTION TARGET là bảo đảm retention:** không đúng. Đây là mục tiêu best-effort; GRP mới cung cấp bảo đảm giữ log cho mốc cụ thể.

## 22. Ví dụ quy trình trước và sau một release

Giả sử ứng dụng chuẩn bị nâng cấp schema vào cuối tuần và cần khả năng rollback nhanh trong vòng 6 giờ sau khi triển khai.

### Trước release

1. Xác nhận RMAN backup gần nhất và archived redo.
2. Kiểm tra restore validate theo kế hoạch.
3. Xem FRA usage và các GRP đang tồn tại.
4. Ước tính flashback log generation trong 6 giờ cao điểm.
5. Xác nhận FRA còn đủ headroom và storage vật lý.
6. Tạo GRP có tên theo release.

~~~sql
CREATE RESTORE POINT before_app_release_2026_11_14
  GUARANTEE FLASHBACK DATABASE;
~~~

7. Ghi lại SCN/time và thông báo cho release owner.

### Trong release

- Theo dõi FRA, flashback log, archive log và alert log.
- Không tạo thêm GRP nếu không có lý do.
- Theo dõi application health, error rate và dữ liệu.
- Nếu phát hiện lỗi nghiêm trọng, đánh giá rollback bằng Flashback Database theo runbook.

### Sau release

- Chạy smoke test.
- Đối soát số lượng và tổng dữ liệu quan trọng.
- Theo dõi workload trong khoảng quan sát.
- Khi release owner xác nhận rollback window đóng, drop GRP.

~~~sql
DROP RESTORE POINT before_app_release_2026_11_14;
~~~

- Kiểm tra FRA usage và backup job.
- Lưu kết quả release, SCN, thời điểm drop và bằng chứng.

Nếu release cần rollback sau khi GRP đã drop, phải dùng phương án backup/RMAN/Data Guard phù hợp. Không giả định có thể quay lại mốc chỉ vì tên restore point đã từng tồn tại.

## 23. Restore drill riêng cho GRP

Trước khi dùng GRP trong production, nên diễn tập quy trình trong môi trường thử nghiệm:

1. Chuẩn bị database thử nghiệm với cấu hình FRA và ARCHIVELOG phù hợp.
2. Tạo một tập dữ liệu đại diện.
3. Tạo GRP.
4. Thực hiện DML và thay đổi schema theo kịch bản.
5. Theo dõi flashback log và FRA usage.
6. Dừng ứng dụng và thực hiện Flashback Database về GRP.
7. Mở database bằng RESETLOGS theo quy trình.
8. Kiểm tra dữ liệu trước mốc và xác nhận thay đổi sau mốc đã bị hoàn nguyên.
9. Kiểm tra PDB/service và ứng dụng.
10. Tạo backup mới theo chính sách và drop GRP sau khi kết thúc thử nghiệm.

Trong drill, cần ghi:

- Thời gian tạo GRP.
- SCN của GRP.
- Dung lượng FRA trước/sau.
- Flashback log generation rate.
- Thời gian flashback.
- Thời gian mở database và PDB.
- RTO/RPO đạt được.
- Kết quả smoke test và đối soát dữ liệu.

Không diễn tập bằng cách flashback database production nếu chưa có phê duyệt và kế hoạch ngừng dịch vụ. Một GRP không phải công cụ rollback không gây gián đoạn.

## 24. Checklist vận hành GRP và FRA

- [ ] Xác nhận ARCHIVELOG mode.
- [ ] Xác nhận FRA đã cấu hình và có dung lượng vật lý.
- [ ] Kiểm tra DB_RECOVERY_FILE_DEST_SIZE.
- [ ] Kiểm tra DB_FLASHBACK_RETENTION_TARGET và trạng thái FLASHBACK_ON.
- [ ] Kiểm tra danh sách restore point hiện tại.
- [ ] Xác định owner và rollback window của mỗi GRP.
- [ ] Kiểm tra V$RECOVERY_FILE_DEST.
- [ ] Kiểm tra V$FLASH_RECOVERY_AREA_USAGE.
- [ ] Kiểm tra V$FLASHBACK_DATABASE_LOG và tốc độ tạo log.
- [ ] Ước tính dung lượng cần giữ cho toàn bộ cửa sổ GRP.
- [ ] Xác nhận RMAN backup và archived redo độc lập.
- [ ] Ghi nhận SCN/time của restore point.
- [ ] Tạo GRP ngay trước thay đổi cần bảo vệ.
- [ ] Theo dõi FRA trong suốt cửa sổ rollback.
- [ ] Drop GRP khi được release owner xác nhận.
- [ ] Kiểm tra reclaim và trạng thái archive/backup sau drop.
- [ ] Lưu bằng chứng và kết quả drill.

## 25. Kết luận

Restore point đánh dấu một SCN để các quy trình phục hồi có thể tham chiếu. Normal restore point lưu mốc nhưng không bảo đảm flashback log còn sẵn có. Guaranteed restore point buộc Oracle giữ flashback log cần thiết cho đến khi được drop, nên rất hữu ích trước release hoặc migration có rủi ro.

Đổi lại, GRP có thể làm flashback log tăng liên tục và chiếm FRA. Nếu FRA không thể reclaim file, archive log, backup và hoạt động database có thể bị ảnh hưởng. Hãy theo dõi V$RESTORE_POINT, V$RECOVERY_FILE_DEST, V$FLASH_RECOVERY_AREA_USAGE và V$FLASHBACK_DATABASE_LOG; dự báo dung lượng theo workload và thời gian giữ GRP; đặt owner và hạn drop rõ ràng.

GRP không thay thế RMAN backup hoặc DR. Trước khi dùng trong production, hãy diễn tập Flashback Database trong môi trường cô lập, kiểm tra PDB/service, đo RTO/RPO và xác nhận quy trình backup/recovery độc lập vẫn đáp ứng yêu cầu. Khi rollback window kết thúc, drop GRP theo phê duyệt và xác nhận FRA đã trở lại trạng thái an toàn.
