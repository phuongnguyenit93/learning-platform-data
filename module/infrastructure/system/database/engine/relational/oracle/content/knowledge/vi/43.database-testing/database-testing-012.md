# Kiểm thử phục hồi dữ liệu và kiểm tra khả năng quay lui triển khai

Một kế hoạch backup chỉ có giá trị khi tổ chức chứng minh được rằng dữ liệu có thể phục hồi trong thời gian và mức mất dữ liệu đã cam kết. Tương tự, một kế hoạch rollback triển khai chỉ đáng tin khi đội vận hành đã thử quay về phiên bản ứng dụng hoặc schema trước đó mà không làm mất dữ liệu phát sinh hợp lệ.

Trong Oracle Database, cần kiểm thử hai năng lực liên quan nhưng khác nhau:

- **Data recovery test**: chứng minh backup, archived redo, control file, cấu hình và quy trình có thể khôi phục database hoặc phạm vi dữ liệu tới điểm mục tiêu.
- **Deployment rollback test**: chứng minh có thể đưa ứng dụng và database schema về trạng thái tương thích sau khi release mới gặp lỗi, đồng thời bảo toàn các giao dịch hợp lệ theo chính sách nghiệp vụ.

Không thể thay thế hai bài kiểm thử này bằng một lần chạy RMAN VALIDATE hoặc một lần redeploy binary cũ. Kiểm tra backup có đọc được không khác với restore thật; rollback ứng dụng không tự đảo ngược DDL hoặc data migration đã commit.

Bài học trình bày cách xác định mục tiêu RPO/RTO, kiểm tra backup, dựng môi trường phục hồi cô lập, chạy restore/recover, kiểm tra dữ liệu sau phục hồi, thiết kế rollback ứng dụng/schema, xử lý implicit commit của Oracle DDL và lập bằng chứng kiểm thử có thể lặp lại.

## 1. Phân biệt backup validation, restore test và rollback test

Ba hoạt động này thường bị gộp thành một, nhưng chúng chứng minh các điều khác nhau.

| Hoạt động | Câu hỏi được trả lời | Bằng chứng chính |
| --- | --- | --- |
| Backup validation | Backup piece và file nguồn có đọc/kiểm tra được không? | RMAN validate output, lỗi đọc/corruption |
| Restore test | Có thể dựng lại database từ backup và redo không? | Database clone mở được tại target, log restore/recover |
| Deployment rollback test | Có thể quay lại phiên bản ứng dụng/schema trước mà dữ liệu vẫn hợp lệ không? | Test migration rollback, app compatibility, reconciliation và service smoke test |

### 1.1. Backup validation không phải restore hoàn chỉnh

RMAN có thể đọc backup piece và xác minh khả năng sử dụng ở mức file. Tuy nhiên, một lần validate không chứng minh toàn bộ quy trình restore/recover sẽ hoàn tất trên host mới.

Restore thật còn phụ thuộc:
- Có đủ backup level và backup piece.
- Có control file hoặc recovery catalog cần thiết.
- Có SPFILE/PFILE và password file.
- Có archived redo liên tục tới target.
- Có TDE wallet/keystore nếu database mã hóa.
- Có storage, quyền truy cập, Oracle Home và cấu hình tương thích.
- Có đủ thời gian, network và dung lượng để restore/recover.
- Người vận hành biết thứ tự lệnh và điều kiện mở database.

### 1.2. Rollback ứng dụng không phải rollback database

Nếu release mới chỉ thay Java code và không thay schema/data, có thể deploy lại artifact cũ. Nhưng nếu migration đã:
- Thêm, đổi tên hoặc xóa column.
- Thay đổi datatype.
- Chuyển đổi dữ liệu.
- Xóa partition hoặc bảng.
- Thay đổi constraint, index hoặc trigger.
- Cập nhật trạng thái nghiệp vụ hàng loạt.

thì rollback binary cũ có thể khiến ứng dụng không tương thích schema mới. Oracle DDL còn có implicit commit, nên @Transactional không thể tự hoàn tác toàn bộ migration.

### 1.3. Restore về thời điểm trước release có thể mất giao dịch mới

Flashback Database hoặc point-in-time recovery có thể đưa database về trước thời điểm triển khai. Những transaction hợp lệ phát sinh sau điểm đó có thể bị loại khỏi trạng thái được phục hồi.

Vì vậy, rollback toàn database cần quyết định nghiệp vụ rõ ràng:
- Chấp nhận mất những giao dịch nào?
- Có thể trích xuất/replay giao dịch sau điểm phục hồi không?
- Có thể chỉ sửa schema hoặc dùng forward-fix không?
- Ai phê duyệt việc quay lui?
- Ứng dụng có được dừng ghi trong quá trình chuyển trạng thái không?

## 2. Xác định RPO, RTO và phạm vi kiểm thử

Trước khi viết runbook, hãy định nghĩa mục tiêu có thể đo.

### 2.1. RPO — Recovery Point Objective

RPO là lượng dữ liệu tối đa có thể mất tính theo thời gian hoặc điểm giao dịch.

Ví dụ:
- RPO 0: yêu cầu không mất transaction đã commit trong failure model được xác định.
- RPO 5 phút: chấp nhận khôi phục tới điểm không cũ hơn 5 phút so với sự cố.
- RPO 1 giờ: có thể chấp nhận mất dữ liệu trong cửa sổ tối đa 1 giờ.

RPO phải gắn với cách backup và redo được bảo vệ. Full backup mỗi đêm không tự đáp ứng RPO 5 phút nếu không có archived redo phù hợp và được bảo vệ.

### 2.2. RTO — Recovery Time Objective

RTO là thời gian tối đa để khôi phục dịch vụ tới mức sử dụng được.

RTO nên tính cả:
1. Phát hiện và phân loại sự cố.
2. Quyết định recovery target.
3. Chuẩn bị host/storage/Oracle Home.
4. Restore datafile/control file.
5. Apply archived redo.
6. Mở database và PDB.
7. Kiểm tra dữ liệu, object và service.
8. Chuyển traffic và xác nhận ứng dụng.

Không chỉ đo thời gian RMAN RESTORE DATABASE. Ứng dụng chỉ được xem là phục hồi khi service, credential, job và các dependency cần thiết hoạt động.

### 2.3. Chia phạm vi recovery

Một kế hoạch có thể cần nhiều loại test:

- **Whole database recovery**: mất host, storage hoặc toàn bộ database.
- **Datafile recovery**: mất hoặc hỏng một datafile.
- **Tablespace recovery**: chỉ phục hồi một tablespace theo phương pháp phù hợp.
- **Point-in-time recovery (PITR)**: quay database hoặc phạm vi hỗ trợ về SCN/time trước lỗi logic.
- **Block media recovery**: phục hồi một số block bị hỏng khi có điều kiện phù hợp.
- **PDB recovery**: phục hồi một pluggable database trong CDB.
- **Logical recovery**: phục hồi bảng/row hoặc dữ liệu nghiệp vụ bị thay đổi nhầm.
- **Deployment rollback**: đưa app/schema về trạng thái tương thích trước release.

Không phải mọi loại sự cố đều nên dùng restore toàn database. Chọn phạm vi nhỏ nhất có thể đáp ứng mục tiêu và giữ được dữ liệu hợp lệ.

## 3. Thiết kế kế hoạch kiểm thử phục hồi

Một test plan tốt có trigger, môi trường, dữ liệu đầu vào, bước thực hiện, tiêu chí pass/fail, người phụ trách và bằng chứng.

### 3.1. Xác định kịch bản

Ví dụ:

| Kịch bản | Mục tiêu | Kỹ thuật thường xem xét |
| --- | --- | --- |
| Mất một datafile | Khôi phục file và apply redo | RMAN RESTORE/RECOVER DATAFILE |
| Mất toàn database host | Dựng database ở host khác | Restore database + media recovery |
| Xóa nhầm dữ liệu | Khôi phục trước thao tác sai | Flashback, PITR, export/restore hoặc logical repair |
| Hỏng block | Khôi phục block bị ảnh hưởng | RMAN block media recovery nếu đủ điều kiện |
| Migration làm sai dữ liệu | Khôi phục dữ liệu hoặc sửa ngược | Compensating migration, PITR hoặc restore clone |
| Release mới lỗi | Quay app về binary cũ | Redeploy artifact cũ và kiểm tra schema compatibility |
| Schema migration không tương thích | Quay schema/app về trạng thái tương thích | Rollback script đã thử, forward-fix hoặc restore strategy |
| Primary site mất | Khôi phục dịch vụ tại standby | Data Guard failover theo DR runbook |

### 3.2. Xác định test data và điểm kiểm chứng

Trước khi tạo backup hoặc restore point, chuẩn bị dữ liệu kiểm thử có thể đối chiếu:
- Một số primary key đã biết.
- Số dòng theo partition hoặc business date.
- Tổng tiền/tổng số lượng theo nhóm.
- Một vài LOB/document mẫu có hash.
- Trạng thái order/payment quan trọng.
- Sequence/identity behavior.
- Constraint và quan hệ foreign key.
- Các bản ghi được tạo trước và sau recovery target.

Không chỉ dùng COUNT(*) trên một bảng lớn. Tổng số dòng có thể giống nhau dù nội dung hoặc trạng thái nghiệp vụ đã sai.

### 3.3. Chọn môi trường phục hồi cô lập

Ưu tiên restore/duplicate vào host, VM, storage hoặc namespace riêng:
- Không ghi đè datafile production.
- Không trùng đường dẫn ASM/filesystem với database đang chạy.
- Không đăng ký service trùng với production.
- Không cho ứng dụng production tự động kết nối clone.
- Không gửi email, thanh toán, message hoặc webhook thật từ dữ liệu clone.
- Dùng credential riêng và giới hạn network egress.
- Bảo vệ dữ liệu nhạy cảm theo chính sách masking/access.
- Đặt giới hạn storage và thời gian lưu clone.

Một restore test có thể gây sự cố production nếu dùng sai control file, file name hoặc connect service. Cô lập môi trường là một điều kiện của bài kiểm thử, không phải bước phụ.

## 4. Chuẩn bị trước khi chạy restore test

Trước khi phục hồi, thu thập đầy đủ metadata và dependency.

### 4.1. Database identity

Ghi nhận:
- DB_NAME, DB_UNIQUE_NAME và DBID.
- Oracle Database release, RU và COMPATIBLE.
- CDB/PDB, database role và open mode.
- Character set và national character set.
- Time zone file version nếu ứng dụng phụ thuộc.
- RAC/ASM hay filesystem.
- TDE encryption và wallet/keystore.
- ARCHIVELOG mode và FRA.
- Backup policy, retention và recovery catalog.

Ví dụ truy vấn:

~~~sql
SELECT name,
       dbid,
       db_unique_name,
       open_mode,
       database_role,
       log_mode,
       force_logging
FROM v$database;
~~~

Phiên bản:

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

### 4.2. Kiểm tra backup inventory

RMAN:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
RMAN> REPORT SCHEMA;
RMAN> SHOW ALL;
~~~

Kiểm tra:
- Full/incremental backup gần nhất.
- Backup control file và SPFILE.
- Archived redo log từ backup tới recovery target.
- Backup piece location và accessibility.
- Retention policy và deletion policy.
- Recovery catalog có sẵn không.
- Backup có được mã hóa không và khóa còn truy cập được không.

### 4.3. TDE wallet/keystore

Nếu database có Transparent Data Encryption, backup datafile có thể không đủ để mở database nếu không có keystore phù hợp.

Cần xác nhận:
- Wallet/keystore backup.
- Password hoặc auto-login wallet theo chính sách.
- Key version và key rotation history.
- Quyền truy cập an toàn trong môi trường test.
- Khả năng mở keystore sau restore.
- Không đưa secret vào log hoặc tài liệu kiểm thử.

Test restore phải bao gồm bước mở keystore trong môi trường cô lập nếu database cần giải mã dữ liệu.

### 4.4. Các file và thông tin khác

Tùy kiến trúc, cần chuẩn bị:
- SPFILE/PFILE.
- Password file.
- Control file autobackup.
- Archived redo log.
- TNS/listener/service configuration.
- ASM disk group hoặc mount point.
- Directory object và external file cần thiết.
- Database link, credential và external dependency.
- Script tạo service, job và quyền truy cập sau recovery.

Không phải tất cả các thành phần này đều được chứa trong RMAN backup theo cùng cách.

## 5. RMAN validation: kiểm tra trước khi restore

RMAN cung cấp các lệnh giúp kiểm tra backup và file nguồn. Chúng rất hữu ích nhưng không thay thế restore thật.

### 5.1. CROSSCHECK

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK so sánh metadata trong RMAN repository với file thực tế hoặc media manager. Nó có thể đánh dấu backup là EXPIRED nếu không tìm thấy.

CROSSCHECK không đọc toàn bộ nội dung backup để chứng minh có thể restore. Không nhầm EXPIRED với OBSOLETE:
- EXPIRED: RMAN không tìm thấy file khi crosscheck.
- OBSOLETE: backup không còn cần theo retention policy hiện tại.

### 5.2. Validate backup set

~~~text
RMAN> VALIDATE BACKUPSET 123;
~~~

Thay 123 bằng backup set key thực tế từ LIST BACKUP. Lệnh đọc và kiểm tra backup set theo phạm vi hỗ trợ; nó không dựng database lên host test.

### 5.3. Restore preview

~~~text
RMAN> RESTORE DATABASE PREVIEW;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

PREVIEW hiển thị backup mà RMAN dự kiến sử dụng cho restore. Nó giúp phát hiện thiếu backup metadata hoặc chuỗi backup không phù hợp trước khi thực hiện restore.

PREVIEW không đọc toàn bộ backup piece và không chứng minh restore sẽ thành công.

### 5.4. Restore validate

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

Lệnh này đọc các backup cần thiết theo kế hoạch restore mà không ghi datafile được phục hồi ra vị trí đích. Nó giúp xác minh backup piece có thể đọc trong quá trình restore giả lập.

Có thể validate archived redo theo phạm vi cần thiết:

~~~text
RMAN> RESTORE ARCHIVELOG ALL VALIDATE;
~~~

Cần xác định đúng phạm vi để tránh kiểm tra quá nhiều dữ liệu không liên quan.

### 5.5. Kiểm tra logical corruption

~~~text
RMAN> BACKUP VALIDATE CHECK LOGICAL DATABASE;
~~~

CHECK LOGICAL yêu cầu RMAN kiểm tra thêm cấu trúc logic của block bên cạnh kiểm tra vật lý theo phạm vi lệnh. Lệnh này đọc database file hiện tại; nó không thay thế restore test từ backup.

Các loại validation khác nhau có phạm vi khác nhau. Lưu output, timestamp, DBID và backup identifiers để có thể đối chiếu trong audit.

## 6. Restore test thực tế vào môi trường cô lập

Đây là bước chứng minh khả năng phục hồi thực sự. Chạy trên host/target được chuẩn bị riêng và kiểm tra mọi file path trước khi thực thi.

### 6.1. Chuẩn bị auxiliary host

- Cài Oracle software tương thích.
- Cấp đủ storage cho datafile, redo, temp, FRA và recovery.
- Cấu hình Oracle Home và environment.
- Chuẩn bị password file và PFILE/SPFILE.
- Xác nhận quyền đọc backup và archived redo.
- Chuẩn bị TDE keystore nếu cần.
- Cấu hình DB_UNIQUE_NAME/service riêng cho clone.
- Chặn traffic production tới clone.
- Kiểm tra không có file path nào trỏ nhầm production.

### 6.2. Dùng RMAN DUPLICATE hoặc restore/recover

Có hai hướng phổ biến:

**RMAN DUPLICATE** tạo một database độc lập từ target database hoặc backup. Đây thường là lựa chọn thuận tiện để dựng bản clone kiểm thử khi có đủ điều kiện và cấu hình auxiliary.

**RESTORE/RECOVER** phục hồi database từ backup theo runbook. Hướng này hữu ích khi muốn kiểm tra quy trình disaster recovery thực tế, bao gồm control file, SPFILE, archived redo và file relocation.

Cú pháp DUPLICATE phụ thuộc active/backup-based duplicate, DBID, file naming, OMF, ASM và Oracle release. Dùng script đã được kiểm thử cho đúng môi trường. Không sao chép nguyên lệnh từ production khác.

### 6.3. Trình tự recovery tổng quát

Một runbook restore database có thể gồm các giai đoạn:

~~~text
1. Xác nhận DBID, backup và target recovery
2. Khởi động auxiliary instance ở NOMOUNT
3. Restore SPFILE/PFILE nếu cần
4. Restore control file phù hợp
5. Mount database
6. Catalog backup piece nếu repository chưa biết
7. Restore datafile
8. Recover database bằng archived/online redo có sẵn
9. Kiểm tra recovery state và file status
10. Open database theo đúng recovery mode
11. Mở PDB/service cần thiết
12. Kiểm tra dữ liệu và ứng dụng
~~~

Các bước chính xác có thể khác nếu dùng backup control file, duplicate, RAC, ASM hoặc TDE.

### 6.4. Lệnh minh họa RESTORE và RECOVER

~~~text
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
~~~

Đây là các lệnh lõi trong một quy trình đã mount database và xác định đúng backup/recovery target. Trước khi chạy, phải bảo đảm control file, repository và file name mapping phù hợp.

Sau complete recovery với current control file, database có thể mở theo quy trình OPEN thông thường. Nếu thực hiện incomplete recovery hoặc recovery dùng backup control file trong trường hợp yêu cầu, cần OPEN RESETLOGS. Không dùng RESETLOGS chỉ vì lệnh OPEN đầu tiên thất bại.

### 6.5. Restore test cần đo gì?

Ghi nhận:
- Thời điểm bắt đầu restore.
- Thời gian đọc backup.
- Thời gian recover redo.
- Lượng dữ liệu/backup được phục hồi.
- Recovery target SCN/time.
- Lỗi RMAN/ORA.
- Thời gian database OPEN.
- Thời gian service/app sẵn sàng.
- Dung lượng storage thực tế.
- Mức RPO/RTO đạt được.

Không dừng đồng hồ ở thời điểm RMAN báo RESTORE complete nếu ứng dụng vẫn chưa truy cập được dữ liệu.

## 7. Point-in-Time Recovery (PITR)

PITR phục hồi database tới một thời điểm hoặc SCN trước khi sự cố xảy ra. Nó hữu ích khi cần loại bỏ thay đổi logic không mong muốn nhưng phạm vi ảnh hưởng có thể lớn.

### 7.1. Xác định target

Target có thể được xác định bằng:
- Timestamp.
- SCN.
- Log sequence theo quy trình phù hợp.

Dùng timestamp từ nguồn thời gian đáng tin cậy và lưu timezone. Khi sự cố phát hiện muộn, target nên là điểm ngay trước thao tác gây lỗi, không phải thời điểm người dùng báo sự cố.

### 7.2. PITR minh họa theo thời gian

~~~text
RMAN> RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 09:30:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Sau incomplete recovery theo quy trình yêu cầu:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Timestamp ở ví dụ chỉ minh họa. Cần kiểm tra timezone, SCN và semantics target theo release. RESETLOGS tạo database incarnation mới; phải cập nhật backup/recovery strategy sau khi mở.

### 7.3. PITR theo SCN

~~~text
RMAN> RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

SCN là điểm nhất quán của database. Xác định target SCN từ audit, application log, Flashback Query, alert log hoặc dữ liệu giám sát phù hợp. RMAN sử dụng giới hạn SCN theo semantics của lệnh; kiểm tra target chính xác trong kế hoạch recovery.

### 7.4. Rủi ro PITR toàn database

PITR toàn database có thể loại bỏ mọi thay đổi sau target, kể cả transaction hợp lệ không liên quan tới lỗi. Trước khi thực hiện trên production:
- Dừng hoặc kiểm soát ghi.
- Xác định dữ liệu phát sinh sau target cần bảo toàn.
- Trích xuất/replay dữ liệu hợp lệ nếu có phương án.
- Đánh giá tác động tới sequence, external system và downstream consumer.
- Có phê duyệt và runbook rõ ràng.

Trong nhiều tình huống, restore clone rồi trích xuất dữ liệu cần thiết an toàn hơn việc đưa production lùi toàn bộ.

## 8. Các phương án phục hồi phạm vi nhỏ hơn

Không phải mọi lỗi dữ liệu đều cần restore cả database.

### 8.1. Flashback Table

Flashback Table có thể đưa một hoặc nhiều table về trạng thái trước một timestamp/SCN trong phạm vi Oracle hỗ trợ, thường cần row movement được bật và undo còn đủ.

~~~sql
ALTER TABLE app.orders ENABLE ROW MOVEMENT;

FLASHBACK TABLE app.orders
TO TIMESTAMP
  (SYSTIMESTAMP - INTERVAL '20' MINUTE);
~~~

Đây là ví dụ cú pháp; phải xác nhận điều kiện, dependency, constraint, trigger và khả năng flashback của bảng. Flashback Table có thể ảnh hưởng tới rowid và quan hệ với bảng liên quan. Kiểm thử trước trên clone.

### 8.2. Flashback Drop

Recycle Bin có thể hỗ trợ khôi phục một table bị DROP nếu object còn trong recycle bin và các điều kiện phù hợp:

~~~sql
FLASHBACK TABLE app.orders
TO BEFORE DROP;
~~~

Không phải mọi DROP đều có thể flashback. PURGE, một số object type và thao tác DDL khác có thể loại bỏ khả năng phục hồi bằng recycle bin.

### 8.3. Tablespace Point-in-Time Recovery

TSPITR phục hồi một tablespace về thời điểm trước mà không nhất thiết đưa toàn database về thời điểm đó. Nó cần auxiliary destination và xử lý các quan hệ phụ thuộc giữa tablespace được phục hồi với phần còn lại.

Kiểm thử:
- Tablespace được chọn có đủ điều kiện TSPITR không.
- Object phụ thuộc nằm ở tablespace khác ra sao.
- Referential integrity và application consistency sau phục hồi.
- Dung lượng auxiliary.
- Thời gian import/transport metadata và hoàn tất recovery.

### 8.4. PDB point-in-time recovery

Trong CDB, có thể có nhu cầu phục hồi một PDB thay vì toàn CDB theo khả năng phiên bản và cấu hình. Test cần xác định:
- CDB root và PDB state.
- Backup/archived redo cần thiết.
- PDB identity và service.
- Tác động tới dữ liệu dùng chung hoặc external dependency.
- Cách mở PDB và xác nhận application connection.

Không áp dụng lệnh PITR toàn CDB cho một lỗi chỉ nằm trong một PDB nếu có phương án phục hồi phạm vi nhỏ hơn phù hợp.

### 8.5. Block media recovery

Nếu chỉ một số block bị hỏng và có backup/redo phù hợp, RMAN có thể phục hồi block mà không cần restore toàn bộ datafile/database.

Test cần ghi nhận:
- Block corruption location.
- Backup chứa block hợp lệ.
- Archived redo để recover block.
- Các điều kiện loại trừ.
- Kết quả kiểm tra V$DATABASE_BLOCK_CORRUPTION sau recovery.

## 9. Kiểm tra dữ liệu sau khi phục hồi

Database mở được chưa chứng minh dữ liệu nghiệp vụ đúng. Cần validation theo nhiều lớp.

### 9.1. Kiểm tra trạng thái database

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       resetlogs_change#,
       resetlogs_time
FROM v$database;
~~~

Kiểm tra instance:

~~~sql
SELECT instance_name,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

Kiểm tra file cần recovery:

~~~sql
SELECT file#,
       error,
       change#,
       time
FROM v$recover_file;
~~~

Nếu dùng CDB, kiểm tra trạng thái PDB:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

### 9.2. Kiểm tra block corruption

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_type,
       corruption_change#
FROM v$database_block_corruption
ORDER BY file#, block#;
~~~

Không chỉ kiểm tra view này ngay sau restore; so sánh với kết quả RMAN validate và các thông tin corruption trước đó nếu có.

### 9.3. Đối soát số dòng

Ví dụ:

~~~sql
SELECT status,
       COUNT(*) AS row_count
FROM app.orders
GROUP BY status
ORDER BY status;
~~~

Đối chiếu với:
- Baseline trước sự cố.
- Expected state tại recovery target.
- Tổng theo ngày/partition.
- Tổng theo tenant/customer.
- Số bản ghi theo trạng thái nghiệp vụ.

Số dòng chỉ là một tín hiệu. Nếu một cột bị cập nhật sai nhưng không thay đổi số lượng, COUNT(*) sẽ không phát hiện.

### 9.4. Đối soát tổng nghiệp vụ

Ví dụ:

~~~sql
SELECT TRUNC(created_at) AS business_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM app.orders
GROUP BY TRUNC(created_at)
ORDER BY business_day;
~~~

Các tổng nên được so sánh tại cùng recovery target và cùng timezone/business cutoff. Chú ý NULL, currency, rounding, soft delete và dữ liệu late-arriving.

### 9.5. Hash theo khóa

Để kiểm tra nội dung, có thể tạo digest theo primary key hoặc theo chunk khóa. Ví dụ khái niệm:

~~~sql
SELECT order_id,
       STANDARD_HASH(
           TO_CHAR(order_id) || '|' ||
           TO_CHAR(customer_id) || '|' ||
           TO_CHAR(status) || '|' ||
           TO_CHAR(total_amount, 'FM9999999990D00'),
           'SHA256'
       ) AS row_hash
FROM app.orders
WHERE order_id BETWEEN :low_id AND :high_id
ORDER BY order_id;
~~~

Đây là mẫu minh họa; cần chuẩn hóa format ngày, số, NLS, NULL và LOB để hash ổn định. Với bảng lớn, hash theo chunk/partition để tránh tải quá lớn và giúp tìm vùng sai khác.

### 9.6. LOB và file ngoài database

Đối với BLOB/CLOB:
- So sánh DBMS_LOB.GETLENGTH.
- Hash nội dung theo streaming ở ứng dụng hoặc công cụ kiểm tra phù hợp.
- Kiểm tra locator và quyền đọc.
- Kiểm tra external file nếu bảng chỉ lưu path/URI.

RMAN backup database không tự backup mọi file nằm ngoài database, chẳng hạn file trên object storage hoặc filesystem do ứng dụng quản lý.

## 10. Kiểm tra object và dependency sau recovery

Một database có thể OPEN nhưng ứng dụng vẫn lỗi vì object, grant hoặc service chưa sẵn sàng.

### 10.1. INVALID objects

~~~sql
SELECT owner,
       object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
~~~

Liệt kê chi tiết:

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Compile schema khi phù hợp:

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema      => 'APP',
        compile_all => FALSE
    );
END;
/
~~~

Không chạy compile toàn bộ schema một cách mù quáng trên production. Trước hết xác định nguyên nhân invalid, dependency thiếu, quyền, synonym và lỗi compile. Recompile không sửa được object phụ thuộc package/table không tồn tại.

### 10.2. Constraint và index

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE owner = 'APP'
ORDER BY table_name, constraint_name;
~~~

~~~sql
SELECT owner,
       index_name,
       table_name,
       status,
       visibility
FROM dba_indexes
WHERE owner = 'APP'
ORDER BY index_name;
~~~

Kiểm tra constraint ENABLED/VALIDATED theo yêu cầu. Index UNUSABLE có thể khiến query hoặc DML gặp lỗi/plan thay đổi.

### 10.3. Sequence và identity

Nếu ứng dụng dùng sequence tạo ID:
- Kiểm tra sequence tồn tại và quyền.
- Xác nhận giá trị sequence không tạo collision với dữ liệu đã phục hồi hoặc replay.
- Kiểm tra cache/order nếu có yêu cầu.
- Xác minh identity column và generator strategy.

Không suy ra sequence value phải bằng MAX(primary_key)+1 trong mọi hệ thống; sequence có thể có gap do cache, rollback hoặc concurrency. Mục tiêu là không tạo trùng khóa và giữ semantics nghiệp vụ.

### 10.4. Các thành phần khác

Kiểm tra:
- Synonym và database link.
- Grants/roles.
- Directory object.
- Scheduler jobs và trạng thái enable.
- Materialized view và refresh status.
- Trigger và package.
- Service và listener registration.
- PDB saved state.
- TDE wallet.
- External table/file location.
- Credentials và network ACL.

Các thành phần external có thể cần cấu hình lại sau khi restore sang host khác.

## 11. Kiểm thử Flashback Database và restore point

Flashback Database có thể đưa database về một thời điểm trước thay đổi không mong muốn mà không cần restore toàn bộ datafile từ backup, nếu điều kiện và flashback logs đáp ứng.

### 11.1. Guaranteed restore point

Một guaranteed restore point giữ lại flashback logs cần thiết để có thể flashback về điểm đó theo điều kiện Oracle. Nó hữu ích trước một lần upgrade hoặc deployment có rủi ro cao.

Ví dụ tạo restore point:

~~~sql
CREATE RESTORE POINT before_release
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
ORDER BY time DESC;
~~~

Điều kiện cấu hình, ARCHIVELOG, Flashback Database và FRA cần được xác minh theo release và kiến trúc trước khi sử dụng. Guaranteed restore point có thể giữ flashback logs và làm FRA tăng nhanh.

### 11.2. Flashback Database

Một runbook điển hình cần:
1. Dừng traffic ghi và kiểm soát session.
2. Shutdown database theo quy trình.
3. Startup MOUNT.
4. Xác nhận target restore point và flashback logs còn đủ.
5. Thực hiện FLASHBACK DATABASE.
6. Mở database RESETLOGS theo yêu cầu.
7. Kiểm tra incarnation, dữ liệu và service.
8. Backup phù hợp sau khi mở.
9. Drop restore point khi đã hết nhu cầu giữ.

Ví dụ phần lệnh chính:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
FLASHBACK DATABASE TO RESTORE POINT before_release;
ALTER DATABASE OPEN RESETLOGS;
~~~

Đây là minh họa, không phải script production dùng không cần điều chỉnh. Hãy kiểm tra database role, RAC, PDB, Data Guard, FRA và trạng thái recovery trước khi chạy.

### 11.3. Giới hạn của restore point

- Restore point không thay thế backup độc lập.
- Flashback Database đưa toàn database về trạng thái trước target; transaction sau target có thể bị loại bỏ.
- Restore point không tự khôi phục external file hoặc hệ thống bên ngoài.
- Guaranteed restore point giữ flashback log và có thể làm FRA đầy nếu giữ quá lâu.
- Sau flashback/open resetlogs, backup và Data Guard cần được đánh giá theo incarnation mới.

### 11.4. Drop restore point sau test

Sau khi đã xác nhận không cần quay lại điểm đó:

~~~sql
DROP RESTORE POINT before_release;
~~~

Không xóa restore point ngay sau deployment nếu rollback window vẫn còn hiệu lực. Mặt khác, không giữ guaranteed restore point vô thời hạn vì có thể tiêu thụ FRA.

## 12. Kiểm thử rollback ứng dụng và schema

Một release thường gồm nhiều lớp: application binary, database schema, dữ liệu migration, configuration và external integration. Rollback phải xét tất cả lớp.

### 12.1. Phân loại thay đổi

| Thay đổi | Cách quay lui thường xem xét |
| --- | --- |
| Java code/config không đổi schema | Redeploy artifact cũ, restore config |
| Thêm nullable column | Có thể giữ column và chạy app cũ nếu tương thích |
| Thêm index | Có thể drop index nếu không còn dependency và an toàn |
| Thêm constraint | Có thể disable/drop theo migration đã thử, nhưng phải xét dữ liệu |
| Rename/drop column | App cũ có thể lỗi; cần migration tương thích hoặc restore/forward-fix |
| Đổi datatype | Có thể mất thông tin hoặc không tương thích; cần dữ liệu backup/transform ngược |
| Data backfill | Cần inverse/compensating script hoặc restore dữ liệu |
| Xóa bảng/partition | Có thể cần PITR/restore từ backup; không thể giả định binary rollback phục hồi dữ liệu |
| DDL phức tạp | Cần migration strategy và test riêng; không dựa vào transaction rollback |

### 12.2. Expand-contract

Chiến lược expand-contract giảm rủi ro khi ứng dụng và schema phải được triển khai qua nhiều bước.

**Expand**
- Thêm column/table/index mới theo cách tương thích ngược.
- Không xóa field cũ ngay.
- Cho phép app cũ tiếp tục hoạt động.
- Có thể dual-write hoặc giữ mapping tạm thời.

**Migrate**
- Backfill dữ liệu theo batch có checkpoint.
- Kiểm tra số dòng, checksum và business aggregate.
- Chuyển ứng dụng đọc/ghi sang cấu trúc mới.
- Theo dõi lỗi và latency.

**Contract**
- Chỉ xóa column/table cũ khi không còn app version nào sử dụng.
- Kiểm tra job, report, database link và consumer.
- Thực hiện cleanup trong release riêng có kế hoạch rollback phù hợp.

Không gộp thêm field mới, backfill, đổi code và drop field cũ trong một bước duy nhất nếu cần rollback nhanh.

### 12.3. Backward và forward compatibility

Kiểm thử tối thiểu:
- App cũ chạy với schema sau bước expand.
- App mới chạy với schema sau migration.
- App cũ có thể chạy trong rollback window nếu cần.
- Job/consumer cũ và mới cùng đọc message/data đúng.
- Migration có thể chạy lại an toàn hoặc phát hiện đã chạy.
- Rollback script không xóa dữ liệu được tạo hợp lệ bởi app mới.

## 13. Oracle DDL và giới hạn của @Transactional

Oracle thực hiện implicit commit xung quanh phần lớn DDL. Vì vậy, migration DDL không thể được coi như DML bình thường có thể rollback bằng transaction.

### 13.1. Ví dụ

~~~sql
UPDATE app.orders
SET status = 'READY'
WHERE order_id = 1001;

ALTER TABLE app.orders ADD source_code VARCHAR2(30);

ROLLBACK;
~~~

UPDATE có thể đã bị commit ngầm trước khi ALTER TABLE thực hiện; ROLLBACK sau đó không khôi phục trạng thái ban đầu của UPDATE. DDL cũng có commit semantics riêng.

Không dùng @Transactional quanh script ALTER TABLE/CREATE INDEX rồi kỳ vọng rollback toàn bộ migration khi một lệnh sau thất bại.

### 13.2. Migration có thể thất bại giữa chừng

Một file migration có nhiều câu lệnh DDL có thể thực hiện được một phần trước khi gặp lỗi. Database có thể ở trạng thái trung gian:
- Column đã thêm nhưng index chưa tạo.
- Một số partition đã chuyển đổi.
- Constraint tạo xong nhưng validate thất bại.
- Backfill đã chạy một phần.
- Một số object compile INVALID.

Migration tool lưu trạng thái version, nhưng trạng thái migration record không tự hoàn tác mọi DDL đã thực hiện.

### 13.3. Thiết kế migration có thể phục hồi

- Chia migration thành bước nhỏ.
- Kiểm tra precondition trước khi thay đổi.
- Dùng tên object rõ và kiểm tra object tồn tại.
- Ghi checkpoint cho backfill dài.
- Có script kiểm tra trạng thái sau mỗi bước.
- Có inverse/compensating script nếu thao tác đảo ngược được.
- Dùng restore point/PITR khi cần quay cả database.
- Có forward-fix khi rollback destructive không an toàn.
- Không xóa dữ liệu cũ trước khi app mới được xác nhận ổn định.

## 14. Rollback strategy: binary rollback, schema rollback và database restore

Ba chiến lược có phạm vi và rủi ro khác nhau.

### 14.1. Binary rollback

Đưa application artifact về version trước:
- Lấy đúng artifact immutable đã phát hành.
- Khôi phục config/secret tương thích.
- Deploy lại vào cùng môi trường hoặc route traffic về phiên bản cũ.
- Kiểm tra schema vẫn tương thích với code cũ.
- Kiểm tra queue/message không chứa format mà app cũ không đọc được.

Binary rollback nhanh nhưng chỉ an toàn khi database schema và data format vẫn tương thích.

### 14.2. Schema rollback

Chạy migration ngược hoặc compensating migration:
- Kiểm tra dependency của app version hiện tại.
- Xác định dữ liệu mới có thể chuyển ngược hay không.
- Backup/export phần dữ liệu cần giữ.
- Chạy script rollback đã thử trên clone.
- Đối soát dữ liệu sau rollback.
- Kiểm tra object INVALID, constraint và index.

Một migration không phải lúc nào cũng có inverse chính xác. Ví dụ chuyển dữ liệu nhiều giá trị vào một column đã chuẩn hóa có thể làm mất thông tin gốc. Khi không thể đảo ngược, forward-fix hoặc restore/replay có thể an toàn hơn.

### 14.3. Database restore/flashback

Dùng khi cần đưa toàn database hoặc phạm vi hỗ trợ về trạng thái trước deployment:
- Xác định target và giao dịch bị ảnh hưởng.
- Dừng ghi.
- Thực hiện flashback/PITR trên phạm vi đã chọn.
- Mở database đúng mode.
- Reconcile dữ liệu sau target.
- Xác nhận PDB/service.
- Backup và điều chỉnh Data Guard sau incarnation change.

Đây là phương án tác động lớn. Không dùng restore toàn database chỉ vì một API mới lỗi nếu có thể quay binary hoặc forward-fix schema.

### 14.4. Blue-green hoặc clone-based cutover

Có thể triển khai release mới trên môi trường/database clone riêng rồi chuyển service/traffic sau khi xác nhận. Khi có lỗi, route traffic về môi trường cũ nếu dữ liệu ghi đã được đồng bộ theo thiết kế.

Blue-green chỉ an toàn khi đã giải quyết:
- Đồng bộ dữ liệu giữa hai môi trường.
- Dual-write hoặc change data capture.
- Cutover consistency point.
- External side effects.
- Service/DNS/connection pool.
- Dữ liệu phát sinh sau cutover khi quay về môi trường cũ.

Không chỉ đổi DNS để rollback nếu database mới đã nhận transaction mà database cũ chưa có.

## 15. Runbook kiểm thử rollback một release

Một lần diễn tập nên có checklist thực thi cụ thể.

### 15.1. Trước triển khai

1. Ghi release ID và artifact checksum.
2. Ghi schema version hiện tại.
3. Ghi database identity và service.
4. Xác nhận backup gần nhất và archived redo.
5. Tạo restore point nếu chiến lược dùng Flashback Database.
6. Kiểm tra FRA headroom và retention.
7. Export/capture cấu hình ứng dụng.
8. Lưu migration scripts và inverse/compensating scripts.
9. Ghi business baseline: row counts, aggregates, key samples.
10. Xác nhận RPO/RTO và rollback approver.

### 15.2. Trong triển khai

- Chạy migration theo thứ tự.
- Ghi timestamp và output từng bước.
- Xác nhận schema version.
- Deploy application artifact.
- Chạy smoke test và business transaction test.
- Kiểm tra alert, invalid objects và connection pool.
- Theo dõi lỗi, latency, lock và job.
- Không drop schema cũ trước khi hết rollback window.

### 15.3. Kích hoạt rollback

Trigger nên được định nghĩa trước:
- Tỷ lệ lỗi vượt ngưỡng.
- Business invariant sai.
- Mất dữ liệu hoặc dữ liệu trùng.
- Latency vượt SLA.
- Migration tạo lock/blocking nghiêm trọng.
- App version mới không tương thích với database/service.

Người có thẩm quyền quyết định rollback phải rõ. Không để nhiều nhóm đồng thời chạy rollback script khác nhau.

### 15.4. Sau rollback

- Xác nhận application version đang phục vụ.
- Xác nhận schema version và migration state.
- Kiểm tra transaction đang chạy và connection pool.
- Đối soát dữ liệu theo business baseline.
- Kiểm tra constraint/index/INVALID objects.
- Kiểm tra job, queue, database link và external integration.
- Kiểm tra alert log.
- Ghi nhận dữ liệu phát sinh trong cửa sổ triển khai.
- Chốt quyết định giữ/loại restore point.
- Tạo backup mới nếu database incarnation hoặc recovery state đã thay đổi.

## 16. Kiểm thử data migration và inverse migration

Một data migration cần được kiểm thử với dữ liệu đại diện và khối lượng gần production.

### 16.1. Kiểm tra precondition

Ví dụ:
- Column nguồn tồn tại.
- Column đích chưa tồn tại hoặc đã ở trạng thái mong muốn.
- Không có duplicate key.
- Dữ liệu nằm trong miền giá trị dự kiến.
- Constraint không bị vi phạm.
- Đủ dung lượng undo/temp/tablespace.
- Batch window phù hợp.

Nếu precondition không đạt, migration nên dừng trước khi thay đổi dữ liệu.

### 16.2. Idempotency

Một migration có thể được chạy lại sau lỗi nếu được thiết kế idempotent:
- Kiểm tra object trước khi tạo.
- Upsert theo key ổn định.
- Backfill theo checkpoint.
- Lưu progress và số dòng xử lý.
- Không lặp side effect không idempotent.
- Có thể tiếp tục từ chunk cuối đã commit.

Idempotent không có nghĩa script có thể chạy tùy ý nhiều lần mà không kiểm tra dữ liệu. Cần xác định rõ điều kiện trước/sau.

### 16.3. Kiểm tra inverse migration

Nếu có script đảo ngược:
- Chạy migration xuôi trên bản clone.
- Ghi baseline.
- Chạy inverse migration.
- Đối soát dữ liệu, schema và object.
- Chạy ứng dụng version cũ.
- Chạy truy vấn nghiệp vụ.
- Kiểm tra sequence/identity, LOB, grants và index.
- Kiểm tra dữ liệu được tạo trong thời gian migration.

Nếu inverse không thể phục hồi thông tin đã mất, ghi rõ giới hạn và dùng forward-fix hoặc restore strategy.

## 17. Kiểm thử Data Guard và site recovery

Nếu kiến trúc có Data Guard, recovery test cần bao gồm cả role transition và ứng dụng.

### 17.1. Switchover có kế hoạch

Kiểm tra:
- Primary/standby role.
- Transport/apply lag.
- Archive gap.
- SRL trên cả hai member.
- Broker configuration.
- Service role-based.
- Client reconnect.
- Backup sau chuyển role.

### 17.2. Failover giả lập

Không thử failover bằng cách làm hỏng production. Dùng DR exercise có phạm vi được phê duyệt:
- Cô lập site/instance theo kịch bản test.
- Xác nhận standby có redo mới nhất.
- Đo RPO.
- Thực hiện failover.
- Mở service và test ứng dụng.
- Đo RTO.
- Reintegrate/reinstate hoặc rebuild primary cũ.

### 17.3. Standby không thay backup

Data Guard replicate cả thay đổi logic. Test cần xác nhận backup độc lập vẫn có thể restore tới điểm trước lỗi logic, kể cả khi standby đã apply thao tác sai.

## 18. Bằng chứng kiểm thử và tiêu chí pass/fail

Một test chỉ được xem là hoàn tất khi có bằng chứng đủ để người khác lặp lại và đánh giá.

### 18.1. Bằng chứng nên lưu

- Test ID, ngày giờ và người thực hiện.
- DBID, DB_UNIQUE_NAME, Oracle release/RU.
- Backup tag, backup set key và archive range.
- Recovery target SCN/time.
- RMAN log và alert log.
- Restore/recover start/end time.
- Database/PDB open mode.
- Data reconciliation report.
- Object/constraint/index status.
- Application smoke test output.
- RPO/RTO measured.
- Deviations, blockers và corrective actions.

Không lưu password, wallet secret, token hoặc dữ liệu nhạy cảm trong report.

### 18.2. Tiêu chí pass

Ví dụ:
- Restore hoàn tất trên host cô lập.
- Database mở đúng target và role.
- Không còn file recovery ngoài dự kiến.
- PDB/service cần thiết mở được.
- Row counts và business aggregates khớp expected state.
- Hash/key sample khớp.
- Không có corruption mới chưa xử lý.
- Critical object không INVALID.
- Application smoke test thành công.
- RPO/RTO đạt mục tiêu.
- Evidence và log được lưu.

### 18.3. Tiêu chí fail

- Thiếu backup hoặc archived redo.
- TDE keystore không thể mở.
- Restore/recover vượt RTO.
- Database không mở được tại target.
- Data reconciliation sai.
- Service/app không hoạt động.
- Không thể quay schema/app về version tương thích.
- Rollback làm mất giao dịch cần giữ.
- Không có bằng chứng hoặc không xác định được trạng thái cuối.

Nếu fail, ghi nguyên nhân và hành động khắc phục. Không đánh dấu test pass chỉ vì database instance đang OPEN.

## 19. Lịch kiểm thử định kỳ

Tần suất tùy RPO/RTO và mức độ quan trọng.

| Hoạt động | Tần suất gợi ý | Mục đích |
| --- | --- | --- |
| Backup job monitoring | Hằng ngày | Phát hiện job fail và thiếu archive |
| RMAN backup validation | Theo lịch định kỳ | Kiểm tra backup/file có thể đọc |
| Restore validation | Hằng tuần/tháng tùy mức rủi ro | Kiểm tra restore path |
| Isolated restore test | Hằng quý hoặc theo policy | Chứng minh restore/recover thực tế |
| PITR/Flashback exercise | Trước release rủi ro và định kỳ | Kiểm tra recovery target |
| Deployment rollback rehearsal | Mỗi release lớn hoặc thay đổi schema | Chứng minh app/schema rollback |
| Data Guard DR exercise | Theo DR policy | Đo RPO/RTO site recovery |
| TDE key recovery test | Theo key management policy | Bảo đảm có thể giải mã backup |

Đây là lịch tham khảo. Hệ thống có RPO/RTO nghiêm ngặt có thể cần test thường xuyên hơn; môi trường ít quan trọng có thể dùng tần suất khác nhưng vẫn phải có bằng chứng.

## 20. Các lỗi thường gặp trong recovery và rollback test

| Lỗi/tình huống | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| RMAN-06025 | Không tìm thấy archived log/backup phù hợp | Kiểm tra backup inventory, thread/sequence và archive range |
| RMAN-06054 | RMAN cần archived log chưa được biết trong repository | Catalog/register đúng log hoặc khôi phục từ backup |
| ORA-01113 | Datafile cần media recovery | Xác định file và apply redo phù hợp |
| ORA-01157 / ORA-01110 | Không mở được datafile | Kiểm tra path, storage, permission và file state |
| ORA-19809 | FRA vượt giới hạn | Kiểm tra archive/backup retention và storage |
| ORA-19870 | Lỗi khi restore backup piece | Đọc lỗi bên dưới, kiểm tra media/readability |
| ORA-01555 | Snapshot too old | Kiểm tra undo, query duration và workload |
| ORA-01578 | Data block corruption | Xác định block và phương án RMAN recovery |
| ORA-01031 | Thiếu quyền | Kiểm tra SYSDBA/RMAN/catalog privilege |
| TDE keystore error | Thiếu wallet/key hoặc password | Khôi phục key material đúng quy trình |
| Migration rollback fail | DDL đã commit hoặc dữ liệu không đảo ngược được | Forward-fix, compensating migration hoặc PITR |
| App cũ lỗi sau binary rollback | Schema đã thay đổi không tương thích | Expand-contract hoặc restore schema/data |
| Restore test ghi nhầm production | File mapping/service isolation sai | Dừng thao tác, cô lập và xử lý incident theo runbook |

Luôn đọc toàn bộ RMAN/ORA stack và alert log. Một mã lỗi thường chỉ chỉ ra bước thất bại, không cung cấp toàn bộ nguyên nhân.

## 21. Ví dụ: diễn tập phục hồi trước release

Giả sử release R42 có:
- Thêm column source_channel.
- Backfill giá trị từ bảng staging.
- Ứng dụng mới đọc column này.
- Dự kiến giữ binary R41 để rollback trong 48 giờ.

Một diễn tập phù hợp:

1. Restore clone từ backup gần nhất.
2. Ghi baseline counts và aggregates.
3. Tạo guaranteed restore point nếu chiến lược database rollback cần dùng.
4. Chạy migration expand: thêm column nullable và index tương ứng.
5. Chạy backfill theo chunk.
6. Đối soát số dòng và giá trị source_channel.
7. Deploy app R42 và chạy smoke/business test.
8. Ghi dữ liệu thử mới bằng app R42.
9. Redeploy app R41 trên cùng schema đã expand.
10. Kiểm tra app R41 vẫn đọc/ghi được.
11. Kiểm tra dữ liệu tạo bởi R42 không bị mất.
12. Thử inverse migration trên một clone khác nếu migration có script đảo ngược.
13. Nếu cần database flashback, quay clone về restore point và xác nhận transaction sau restore point bị loại bỏ đúng như dự kiến.
14. Đo thời gian từng bước và ghi RPO/RTO.

Kết quả cần phân biệt:
- Binary rollback R42 về R41 có thể an toàn vì schema mới vẫn tương thích.
- Drop column source_channel ngay khi rollback có thể làm mất dữ liệu đã tạo bởi R42.
- Flashback toàn database sẽ loại bỏ transaction sau restore point, nên không thể dùng thay thế binary rollback nếu cần giữ dữ liệu mới.

## 22. Ví dụ: đối soát sau PITR

Giả sử thao tác xóa nhầm order xảy ra lúc 10:15. Recovery target được chọn lúc 10:14:30.

Sau khi phục hồi clone:
- Kiểm tra order ID bị xóa đã tồn tại tại target.
- Kiểm tra các order khác được tạo trước target vẫn tồn tại.
- Kiểm tra giao dịch sau target không xuất hiện trong clone nếu PITR toàn database.
- Tính lại tổng order theo business date.
- Kiểm tra payment reference và external payment provider.
- Kiểm tra sequence không tạo collision nếu clone được dùng để trích xuất dữ liệu.
- Xuất danh sách row cần phục hồi vào database production bằng phương pháp đã phê duyệt.

Không đưa nguyên clone PITR trở lại production nếu có nhiều giao dịch hợp lệ sau target cần giữ. Có thể cần trích xuất và merge có kiểm soát.

## 23. Checklist runbook phục hồi dữ liệu

- [ ] Xác định DBID, DB_UNIQUE_NAME, role và Oracle release.
- [ ] Xác định recovery scope: database, datafile, tablespace, PDB, block hay logical data.
- [ ] Xác định RPO/RTO và recovery target.
- [ ] Xác nhận backup, control file, SPFILE và archived redo.
- [ ] Xác nhận TDE wallet/keystore nếu có.
- [ ] Xác nhận storage, Oracle Home và file mapping.
- [ ] Cô lập host/service/network của restore target.
- [ ] Chạy RMAN PREVIEW/VALIDATE phù hợp.
- [ ] Thực hiện restore/recover trên target.
- [ ] Mở database đúng mode và xử lý RESETLOGS nếu cần.
- [ ] Kiểm tra PDB, service và database role.
- [ ] Kiểm tra corruption, recovery file và alert log.
- [ ] Đối soát row count, business aggregate và hash.
- [ ] Kiểm tra constraint, index, sequence và INVALID objects.
- [ ] Chạy application smoke test.
- [ ] Đo RPO/RTO và lưu evidence.
- [ ] Tạo backup mới khi cần.
- [ ] Ghi corrective action cho mọi sai lệch.

## 24. Checklist kiểm thử rollback triển khai

- [ ] Lưu artifact và config version trước release.
- [ ] Ghi schema version và database identity.
- [ ] Có migration script và precondition.
- [ ] Đánh giá backward/forward compatibility.
- [ ] Xác định DDL có implicit commit.
- [ ] Có inverse/compensating script nếu khả thi.
- [ ] Có backup/restore point nếu cần database rewind.
- [ ] Đánh giá giao dịch phát sinh sau rollback target.
- [ ] Kiểm tra queue/message/external side effects.
- [ ] Kiểm tra app cũ trên schema mới.
- [ ] Kiểm tra app mới sau migration.
- [ ] Đối soát dữ liệu sau migration và rollback.
- [ ] Kiểm tra INVALID objects, constraint và index.
- [ ] Đo thời gian rollback và phục hồi service.
- [ ] Có approver, owner và rollback trigger.
- [ ] Lưu log, evidence và kết quả test.

## 25. Bài tập tự luyện

1. Phân biệt backup validation và restore test.
2. Vì sao RMAN RESTORE DATABASE VALIDATE không thay thế restore thật?
3. CROSSCHECK khác VALIDATE như thế nào?
4. RESTORE DATABASE PREVIEW chứng minh điều gì?
5. Định nghĩa RPO và RTO bằng ví dụ.
6. Nêu các thành phần cần chuẩn bị cho restore trên host mới.
7. Vì sao TDE wallet/keystore là dependency của recovery?
8. Phân biệt complete recovery và point-in-time recovery.
9. Khi nào PITR có thể yêu cầu OPEN RESETLOGS?
10. Vì sao không dùng RESETLOGS như cách thử lại OPEN?
11. Phân biệt Flashback Table và Flashback Database.
12. Khi nào Flashback Drop có thể phục hồi table?
13. Nêu điều kiện cần xem xét trước TSPITR.
14. PDB recovery khác whole CDB recovery ở điểm nào?
15. Block media recovery giải quyết loại sự cố nào?
16. Viết query kiểm tra database role và open mode.
17. Viết query kiểm tra file cần recovery.
18. Viết query kiểm tra database block corruption.
19. Vì sao row count không đủ chứng minh dữ liệu đúng?
20. Thiết kế business aggregate để đối soát order sau PITR.
21. Nêu cách hash dữ liệu theo key range.
22. Nêu các object cần kiểm tra sau restore ngoài datafile.
23. INVALID object có luôn được sửa bằng COMPILE_SCHEMA không?
24. Vì sao sequence value không nhất thiết bằng MAX(primary key)+1?
25. Phân biệt binary rollback và schema rollback.
26. Vì sao Oracle DDL không rollback như DML trong @Transactional?
27. Giải thích chiến lược expand-contract.
28. Khi nào forward-fix an toàn hơn inverse migration?
29. Vì sao flashback toàn database có thể làm mất transaction hợp lệ sau restore point?
30. Thiết kế một DR/deployment rollback rehearsal có target, dữ liệu đối soát, RPO/RTO, evidence và người phê duyệt.

**Một recovery plan chỉ được chứng minh khi có thể phục hồi database trên môi trường cô lập, mở đúng recovery target và đối soát được dữ liệu nghiệp vụ. Một rollback plan chỉ đáng tin khi đã thử cả binary, schema và side effect liên quan.** Hãy phân biệt RMAN validation với restore thật, xác định RPO/RTO, kiểm tra backup cùng archived redo/TDE key, kiểm chứng dữ liệu và object sau recovery, đồng thời thiết kế migration tương thích ngược. Với Oracle, DDL có implicit commit nên @Transactional không thể thay thế migration rollback hoặc database recovery strategy.

