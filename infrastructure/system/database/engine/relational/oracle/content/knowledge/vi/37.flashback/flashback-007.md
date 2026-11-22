# Flashback Database, flashback log và cấu hình vùng phục hồi

Flashback Database là khả năng đưa toàn bộ cơ sở dữ liệu Oracle trở về một thời điểm hoặc SCN trước đó bằng cách sử dụng flashback log kết hợp với redo. Tính năng này hữu ích khi một thao tác triển khai, cập nhật dữ liệu hoặc thay đổi cấu hình gây ra kết quả không mong muốn. Thay vì phải khôi phục toàn bộ datafile từ bản sao lưu rồi thực hiện media recovery, DBA có thể đưa các block dữ liệu về trạng thái cũ nếu các flashback log cần thiết vẫn còn.

Flashback Database cần được chuẩn bị trước sự cố. Cơ sở dữ liệu phải chạy ở chế độ ARCHIVELOG, vùng phục hồi phải được cấu hình đủ dung lượng và tính năng phải được bật trước thời điểm cần quay lui. Flashback log không phải là bản sao lưu và không thay thế chiến lược backup bằng RMAN.

## 1. Các khái niệm chính

### Flashback Database

Flashback Database đưa trạng thái của toàn bộ database về một thời điểm, SCN hoặc restore point. Phạm vi tác động là toàn database: các thay đổi sau mốc được chọn sẽ bị loại khỏi trạng thái database sau khi mở lại.

Ví dụ, trước khi triển khai một phiên bản ứng dụng mới, DBA tạo một restore point. Nếu triển khai thất bại và làm dữ liệu bị thay đổi ngoài dự kiến, DBA có thể flashback database về restore point đó.

Flashback Database khác với các tính năng Flashback có phạm vi hẹp hơn:

| Tính năng | Phạm vi và mục đích |
|---|---|
| Flashback Database | Đưa toàn bộ database về một mốc thời gian hoặc SCN |
| Flashback Table | Đưa một hoặc nhiều bảng về trạng thái trước đó, khi đáp ứng các điều kiện của tính năng |
| Flashback Query | Truy vấn dữ liệu tại một thời điểm trong quá khứ bằng cú pháp như `AS OF TIMESTAMP` |
| Flashback Transaction | Phân tích hoặc tạo câu lệnh bù cho một transaction đã thực hiện |
| RMAN point-in-time recovery | Khôi phục database hoặc tablespace bằng backup và redo đến một mốc xác định |

Hãy chọn Flashback Table hoặc Flashback Query nếu chỉ cần xem hay khôi phục một phần dữ liệu. Flashback Database phù hợp khi cần quay lui trạng thái của cả database.

### Flashback log

Flashback log lưu các hình ảnh block trước khi block thay đổi, giúp Oracle tái tạo trạng thái cũ của block. Tiến trình nền RVWR (Recovery Writer) ghi flashback data vào các flashback log trong quá trình database hoạt động khi Flashback Database được bật.

Khi thực hiện Flashback Database, Oracle sử dụng flashback log để đưa các block về trạng thái trước đó và sử dụng thông tin redo cần thiết để bảo đảm database nhất quán tại mốc đích. Flashback log có mục đích và định dạng khác với online redo log hoặc archived redo log:

- Online redo log ghi lại các thay đổi để phục vụ instance recovery và quá trình recovery.
- Archived redo log là bản lưu trữ của các redo log đã đầy, được dùng trong media recovery, backup và các hoạt động khôi phục.
- Flashback log lưu thông tin block trước thay đổi để hỗ trợ đưa database lùi về quá khứ.

Flashback log được Oracle quản lý trong Fast Recovery Area (FRA). DBA không nên tự di chuyển, đổi tên hoặc xóa các file này bằng hệ điều hành.

### SCN, timestamp và restore point

SCN (System Change Number) là số thứ tự thay đổi mà Oracle sử dụng để xác định một mốc nhất quán. Có thể yêu cầu flashback theo SCN hoặc timestamp. SCN thường phù hợp khi cần một mốc chính xác được ghi nhận trong log hoặc trong quá trình điều tra sự cố.

Restore point là tên gắn với một SCN để DBA dễ tham chiếu. Có hai loại thường dùng:

- Normal restore point ghi nhận một mốc SCN. Nó không buộc Oracle giữ lại toàn bộ flashback log vô thời hạn; khả năng sử dụng phụ thuộc vào flashback log còn sẵn có.
- Guaranteed restore point yêu cầu Oracle giữ các flashback log cần thiết để có thể quay lại mốc đó, miễn là restore point còn tồn tại và database có thể tiếp tục tạo, lưu trữ các log cần thiết. Nó có thể làm FRA tăng nhanh nếu giữ quá lâu.

## 2. Fast Recovery Area (FRA)

Fast Recovery Area là vùng lưu trữ do Oracle quản lý cho các file phục vụ backup và recovery. Tùy cấu hình, FRA có thể chứa:

- Flashback log.
- Archived redo log.
- RMAN backup piece và image copy.
- Control file autobackup và SPFILE autobackup.
- Một số bản sao control file hoặc online redo log nếu chúng được cấu hình đặt trong FRA.

FRA giúp Oracle và RMAN quản lý việc sử dụng dung lượng, nhận diện file có thể tái sử dụng và thu hồi file khi cần theo chính sách recovery. Việc một file có thể được reclaim hay không phụ thuộc vào trạng thái recovery, chính sách RMAN, nhu cầu Data Guard và các restore point đang được giữ.

Hai tham số quan trọng nhất để cấu hình FRA là:

| Tham số | Ý nghĩa |
|---|---|
| `DB_RECOVERY_FILE_DEST` | Đường dẫn thư mục hoặc disk group dùng làm FRA |
| `DB_RECOVERY_FILE_DEST_SIZE` | Giới hạn dung lượng FRA mà Oracle được phép sử dụng |

Phải đặt `DB_RECOVERY_FILE_DEST_SIZE` trước khi đặt `DB_RECOVERY_FILE_DEST`. Giá trị SIZE là giới hạn Oracle quản lý, không phải cam kết rằng thiết bị lưu trữ có đúng lượng dung lượng trống đó. DBA cần kiểm tra dung lượng thực tế, overhead của filesystem hoặc ASM, và chừa khoảng dự phòng cho tăng trưởng.

Ví dụ, FRA dùng ASM disk group `+RECO` với giới hạn 120 GB:

```sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 120G SCOPE=BOTH;
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO' SCOPE=BOTH;
```

Nếu dùng filesystem, thay `+RECO` bằng đường dẫn hợp lệ, chẳng hạn `/u01/app/oracle/fast_recovery_area`. Thư mục phải tồn tại và Oracle Database software owner phải có quyền truy cập phù hợp.

`SCOPE=BOTH` giả định database sử dụng SPFILE và áp dụng thay đổi cho cả bộ nhớ lẫn cấu hình lưu trữ. Nếu database khởi động bằng PFILE, hãy cập nhật file tham số phù hợp và thực hiện theo quy trình khởi động lại của môi trường đó. Trong Oracle RAC, FRA phải nằm trên vùng lưu trữ dùng chung mà các instance có thể truy cập; cấu hình tham số phải nhất quán giữa các instance.

## 3. Cấu hình retention và bật Flashback Database

### Điều kiện trước khi bật

Trước khi cấu hình, DBA cần xác nhận:

1. Database ở chế độ ARCHIVELOG.
2. FRA đã được cấu hình và còn đủ dung lượng.
3. Storage có hiệu năng và độ tin cậy phù hợp với tải ghi của database.
4. Chính sách RMAN, archived log và Data Guard (nếu có) không xung đột với nhu cầu lưu flashback log.
5. Có backup hợp lệ. Flashback Database không thay thế backup khi datafile hoặc storage bị mất.

Kiểm tra trạng thái hiện tại:

```sql
SELECT name, log_mode, flashback_on, open_mode
FROM v$database;
```

Nếu `LOG_MODE` là `NOARCHIVELOG`, cần chuyển database sang ARCHIVELOG. Thao tác này cần database ở trạng thái MOUNT:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
```

Có thể bật Flashback Database ngay khi database vẫn ở trạng thái MOUNT:

```sql
ALTER DATABASE FLASHBACK ON;
ALTER DATABASE OPEN;
```

Nếu database đã ở ARCHIVELOG, chỉ cần đưa database về MOUNT trước khi bật Flashback Database:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE FLASHBACK ON;
ALTER DATABASE OPEN;
```

Trong một môi trường đang hoạt động, hãy lên lịch thao tác cần shutdown và tuân thủ quy trình vận hành của hệ thống. Câu lệnh trên là ví dụ cho database đơn instance; môi trường RAC hoặc Data Guard cần thực hiện theo quy trình tương ứng.

### Đặt mục tiêu lưu giữ flashback log

Tham số `DB_FLASHBACK_RETENTION_TARGET` đặt mục tiêu lưu giữ flashback log, tính bằng phút. Giá trị mặc định thường là 1440 phút (24 giờ).

```sql
ALTER SYSTEM SET DB_FLASHBACK_RETENTION_TARGET = 1440 SCOPE=BOTH;
```

Đặt mục tiêu 1440 phút có nghĩa là Oracle cố gắng giữ đủ flashback log để hỗ trợ quay lui khoảng 24 giờ. Đây không phải cam kết tuyệt đối rằng database luôn có thể flashback đủ 24 giờ. Thời gian thực tế phụ thuộc vào tốc độ thay đổi block, dung lượng FRA, file cần giữ cho recovery và các restore point.

Để ước lượng dung lượng, hãy theo dõi lượng flashback data được tạo trong các khoảng thời gian có tải cao, sau đó tính theo retention mục tiêu và cộng thêm dung lượng cho archived log, backup, restore point cùng khoảng dự phòng. Không nên chọn FRA chỉ dựa trên kích thước database; lượng block thay đổi và tốc độ phát sinh log mới là yếu tố quan trọng.

### Xác nhận tính năng đã bật

```sql
SELECT log_mode, flashback_on
FROM v$database;

SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER db_flashback_retention_target;
```

Giá trị `FLASHBACK_ON` thường là `YES` khi Flashback Database đã bật. Hãy kiểm tra thêm phạm vi flashback có sẵn trong `V$FLASHBACK_DATABASE_LOG` và tình trạng FRA; chỉ nhìn tham số cấu hình không đủ để kết luận rằng database có thể quay lui đến mọi mốc mong muốn.

## 4. Tạo và quản lý restore point

Tạo normal restore point trước một thao tác quan trọng:

```sql
CREATE RESTORE POINT before_release;
```

Tạo guaranteed restore point khi cần bảo đảm khả năng quay lại mốc trước thay đổi:

```sql
CREATE RESTORE POINT before_upgrade
GUARANTEE FLASHBACK DATABASE;
```

Tên restore point nên mô tả rõ mục đích và thời điểm tạo. Sau khi công việc hoàn tất và không còn cần khả năng quay lui, xóa restore point:

```sql
DROP RESTORE POINT before_upgrade;
```

Có thể kiểm tra các restore point đang tồn tại:

```sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
```

Guaranteed restore point có thể giữ flashback log lâu hơn retention mục tiêu. Nếu quên xóa restore point sau khi triển khai, FRA có thể đầy dù DBA đã đặt retention tương đối ngắn. Khi FRA không còn chỗ để ghi file cần thiết, database có thể gặp lỗi ghi archived log hoặc các hoạt động recovery khác bị ảnh hưởng. Vì vậy, mỗi restore point cần có người sở hữu, mục đích và thời điểm dự kiến xóa rõ ràng.

## 5. Theo dõi flashback log và dung lượng FRA

DBA nên theo dõi cả phạm vi flashback thực tế lẫn dung lượng FRA. Các view động hữu ích gồm:

| View | Thông tin chính |
|---|---|
| `V$DATABASE` | Chế độ ARCHIVELOG, trạng thái Flashback Database và trạng thái mở |
| `V$FLASHBACK_DATABASE_LOG` | Mốc flashback cũ nhất, retention mục tiêu, dung lượng flashback log và dung lượng ước tính |
| `V$FLASHBACK_DATABASE_STAT` | Lượng flashback data, database data và redo theo từng khoảng thống kê |
| `V$RECOVERY_FILE_DEST` | Giới hạn FRA, dung lượng đã dùng và dung lượng có thể reclaim |
| `V$FLASH_RECOVERY_AREA_USAGE` | Tỷ lệ dung lượng FRA theo từng loại file |
| `V$RESTORE_POINT` | Các restore point và dung lượng liên quan |

Kiểm tra mốc thời gian cũ nhất mà flashback log hiện có thể hỗ trợ:

```sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
FROM v$flashback_database_log;
```

Kiểm tra tổng dung lượng FRA:

```sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
```

Kiểm tra loại file đang chiếm FRA:

```sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
```

Theo dõi tốc độ phát sinh flashback data theo thời gian:

```sql
SELECT begin_time,
       end_time,
       flashback_data,
       db_data,
       redo_data,
       estimated_flashback_size
FROM v$flashback_database_stat
ORDER BY begin_time;
```

Các cột dung lượng trong những view này thường được biểu diễn bằng byte. Có thể chuyển sang MB hoặc GB khi xây dựng báo cáo giám sát. Hãy quan sát nhiều chu kỳ tải, bao gồm giờ cao điểm và các đợt batch lớn, để ước lượng FRA phù hợp.

Một FRA có tỷ lệ sử dụng cao chưa chắc lập tức gặp sự cố nếu còn nhiều file có thể reclaim. Ngược lại, `SPACE_RECLAIMABLE` thấp cùng với tỷ lệ sử dụng gần giới hạn là dấu hiệu cần xử lý sớm. Guaranteed restore point có thể khiến các flashback log cần thiết không được reclaim, do đó cần theo dõi riêng các restore point đang tồn tại.

## 6. Flashback toàn database về một mốc

Flashback Database là thao tác ảnh hưởng đến toàn bộ database. Cần xác định đúng mốc đích và đánh giá tác động dữ liệu trước khi chạy.

Quy trình tổng quát:

1. Xác định SCN, timestamp hoặc restore point cần quay lại. Đối chiếu với thời điểm xảy ra sự cố và phạm vi thay đổi cần loại bỏ.
2. Kiểm tra `V$FLASHBACK_DATABASE_LOG` để xác nhận mốc đích nằm trong phạm vi log còn sẵn có. Nếu dùng restore point, xác nhận restore point tồn tại.
3. Dừng ứng dụng hoặc các tác vụ ghi dữ liệu theo runbook của hệ thống.
4. Shutdown database và khởi động ở trạng thái MOUNT.
5. Chạy lệnh Flashback Database đến mốc đã chọn.
6. Mở database bằng `RESETLOGS`.
7. Xác minh dữ liệu, trạng thái ứng dụng và tạo backup mới theo chính sách RMAN.

Ví dụ flashback theo SCN:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO SCN 123456789;

ALTER DATABASE OPEN RESETLOGS;
```

Ví dụ flashback theo timestamp:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO TIMESTAMP
  (SYSTIMESTAMP - INTERVAL '30' MINUTE);

ALTER DATABASE OPEN RESETLOGS;
```

Ví dụ flashback về guaranteed restore point:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO RESTORE POINT before_upgrade;

ALTER DATABASE OPEN RESETLOGS;
```

Sau Flashback Database, database phải được mở bằng `RESETLOGS`. Việc này tạo một database incarnation mới. DBA cần kiểm tra incarnation trong RMAN và thực hiện backup mới để thiết lập điểm khôi phục cho trạng thái database sau khi flashback.

Không thực hiện lệnh flashback chỉ vì một mốc thời gian có vẻ phù hợp. Nếu chọn mốc quá sớm, mọi thay đổi hợp lệ sau mốc đó cũng bị loại khỏi trạng thái database. Hãy xác định rõ dữ liệu nào sẽ bị mất, thông báo cho chủ ứng dụng và có phương án kiểm chứng sau khi mở database.

## 7. Vận hành, xử lý sự cố và giới hạn

### FRA gần đầy hoặc đầy

Khi FRA tiến gần giới hạn, hãy xác định loại file đang chiếm dung lượng bằng `V$FLASH_RECOVERY_AREA_USAGE`, sau đó kiểm tra chính sách RMAN và các restore point. Các bước xử lý thường gồm:

- Xác nhận `DB_RECOVERY_FILE_DEST_SIZE` và dung lượng thực tế của filesystem hoặc ASM.
- Xem các restore point còn cần thiết hay không; xóa restore point đã hết mục đích sau khi được chủ sở hữu xác nhận.
- Kiểm tra backup retention policy, archived log deletion policy và trạng thái backup.
- Dùng RMAN để quản lý file obsolete hoặc expired theo chính sách đã thiết lập, ví dụ `DELETE OBSOLETE` sau khi xác nhận retention policy phù hợp.
- Tăng giới hạn FRA hoặc mở rộng storage khi nhu cầu lưu trữ thực tế tăng.

Không xóa trực tiếp flashback log, archived redo log hoặc backup file bằng lệnh hệ điều hành. Việc xóa ngoài cơ chế quản lý của Oracle có thể làm metadata và trạng thái recovery không còn nhất quán. Cũng không nên xóa archived log chỉ để giải phóng dung lượng khi chưa kiểm tra nhu cầu recovery và Data Guard.

### Không thể flashback đến mốc yêu cầu

Nếu mốc đích cũ hơn `OLDEST_FLASHBACK_TIME`, flashback log cần thiết có thể đã bị reclaim hoặc không còn tồn tại. Kiểm tra lại SCN, timestamp, retention thực tế và restore point. Nếu không còn đủ flashback log, cần đánh giá phương án RMAN point-in-time recovery từ backup và archived redo log.

Nếu Flashback Database chưa bật tại thời điểm xảy ra sự cố, không thể tạo ngược flashback log cho khoảng thời gian trước đó. Việc tăng `DB_FLASHBACK_RETENTION_TARGET` sau sự cố cũng không khôi phục được log đã mất.

### Giới hạn cần nhớ

- Flashback Database chỉ hữu ích khi các flashback log cần thiết còn sẵn có và database đáp ứng điều kiện của tính năng.
- Đây không phải giải pháp phục hồi khi datafile hoặc thiết bị lưu trữ bị mất. Trường hợp đó vẫn cần backup và media recovery.
- Thao tác `NOLOGGING` và một số hoạt động hoặc thay đổi cấu trúc có thể tạo giới hạn cho khả năng flashback hoặc yêu cầu xử lý bổ sung. Cần kiểm tra tài liệu đúng phiên bản Oracle và thử nghiệm trên môi trường tương tự.
- Flashback Database quay lui toàn database. Nếu chỉ một bảng bị ảnh hưởng, hãy cân nhắc tính năng Flashback có phạm vi hẹp hơn.
- Sau `OPEN RESETLOGS`, database chuyển sang incarnation mới. Cần cập nhật kế hoạch backup và xác minh trạng thái RMAN.
- Retention target là mục tiêu. Tải ghi cao, FRA thiếu dung lượng hoặc guaranteed restore point tồn tại lâu có thể làm thay đổi đáng kể mức sử dụng storage.

## 8. Checklist cấu hình và vận hành

Trước khi đưa Flashback Database vào sử dụng, DBA có thể kiểm tra lần lượt:

- [ ] Database đang ở chế độ ARCHIVELOG.
- [ ] `DB_RECOVERY_FILE_DEST_SIZE` được đặt trước `DB_RECOVERY_FILE_DEST`.
- [ ] FRA trỏ đến storage hợp lệ, có đủ dung lượng thực tế và khoảng dự phòng.
- [ ] `DB_FLASHBACK_RETENTION_TARGET` phản ánh mục tiêu vận hành.
- [ ] `V$DATABASE.FLASHBACK_ON` xác nhận tính năng đã bật.
- [ ] `V$FLASHBACK_DATABASE_LOG` cho thấy phạm vi flashback thực tế phù hợp.
- [ ] Có cảnh báo giám sát cho FRA, archived log và guaranteed restore point.
- [ ] Restore point có mục đích, chủ sở hữu và kế hoạch xóa rõ ràng.
- [ ] RMAN backup và quy trình media recovery vẫn được duy trì.
- [ ] Quy trình flashback đã được diễn tập, gồm xác minh dữ liệu sau `OPEN RESETLOGS`.

Flashback Database đem lại một cách quay lui nhanh khi thay đổi logic hoặc thao tác dữ liệu gây ra sự cố. Hiệu quả của nó phụ thuộc vào việc cấu hình FRA, duy trì ARCHIVELOG, theo dõi flashback log và quản lý restore point có kỷ luật. DBA cần xem Flashback Database là một lớp trong chiến lược bảo vệ dữ liệu tổng thể, phối hợp với backup RMAN, archived redo log và quy trình kiểm thử khôi phục.

