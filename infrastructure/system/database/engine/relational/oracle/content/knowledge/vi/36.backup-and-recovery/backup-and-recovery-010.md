# RESTORE VALIDATE, kiểm tra lỗi block và diễn tập phục hồi

Một bản backup chỉ có giá trị khi có thể đọc được, chứa đủ dữ liệu cần thiết và có thể phục hồi thành một database hoạt động đúng trong thời gian mục tiêu. Việc một job backup kết thúc thành công chưa chứng minh rằng mọi backup piece đều đọc được hoặc có đủ archived redo để phục hồi đến thời điểm mong muốn.

Oracle Recovery Manager (RMAN) cung cấp các lệnh để kiểm tra backup và dữ liệu mà không phải phục hồi đè lên database đang chạy. Hai thao tác quan trọng là **RESTORE ... VALIDATE**, dùng để kiểm tra các backup mà RMAN sẽ chọn cho một thao tác restore, và **VALIDATE**, dùng để đọc, kiểm tra datafile hoặc backup nhằm phát hiện block corruption. Sau đó, DBA cần diễn tập restore/recover trong môi trường cô lập để chứng minh toàn bộ quy trình có thể đáp ứng RTO và RPO.

## 1. Phân biệt backup thành công, validate và restore drill

Ba hoạt động này kiểm tra các mức độ khác nhau:

| Hoạt động | Điều được kiểm tra | Điều chưa được chứng minh |
|---|---|---|
| Backup job hoàn tất | RMAN đã ghi backup theo cấu hình và báo thành công | Backup có thể phục hồi đầy đủ đến thời điểm nghiệp vụ cần hay không |
| RMAN VALIDATE / RESTORE VALIDATE | Datafile hoặc backup piece có thể đọc và vượt qua các kiểm tra được yêu cầu | Toàn bộ database đã được phục hồi, mở và ứng dụng chạy đúng |
| Restore drill | Backup, control file, SPFILE, archived redo, mật khẩu/keystore và quy trình phục hồi có thể phối hợp để tạo database hoạt động | Không tự động chứng minh mọi kịch bản thảm họa hoặc mọi điểm thời gian đều đã được thử |

Có thể hiểu:

- Backup tạo ra bản sao có thể dùng cho recovery.
- Validate kiểm tra khả năng đọc và một số dạng hỏng dữ liệu.
- Restore drill thực hiện phục hồi thật trong môi trường thử nghiệm, sau đó kiểm tra database và ứng dụng.

Không thay thế bước nào bằng bước khác. Một backup có thể được validate nhưng restore drill vẫn thất bại do thiếu archived redo, thiếu TDE wallet, thiếu cấu hình storage hoặc sai quy trình mở database.

## 2. RESTORE VALIDATE là gì?

Trong RMAN, RESTORE ... VALIDATE yêu cầu RMAN xác định backup cần thiết cho thao tác restore rồi đọc các backup piece tương ứng để kiểm tra chúng có thể được sử dụng hay không. RMAN không ghi đè datafile đích và không thực hiện một lần restore thực sự.

Ví dụ:

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

Lệnh này kiểm tra các backup mà RMAN chọn để phục hồi database theo repository và trạng thái hiện tại. Nó hữu ích để xác nhận các backup piece cần thiết có thể được đọc, nhưng không tạo ra datafile đã phục hồi.

Có thể kiểm tra một datafile cụ thể:

~~~text
RMAN> RESTORE DATAFILE 7 VALIDATE;
~~~

Hoặc kiểm tra tablespace:

~~~text
RMAN> RESTORE TABLESPACE USERS VALIDATE;
~~~

Phạm vi chính xác của lệnh phụ thuộc database, recovery catalog/control file repository, cấu hình channel, thời điểm restore và các backup sẵn có. Nếu muốn kiểm tra khả năng phục hồi tới một SCN hoặc thời điểm cụ thể, cần chỉ định cùng điều kiện UNTIL phù hợp với lệnh restore dự kiến.

### RESTORE VALIDATE không phục hồi file

Sau RESTORE DATABASE VALIDATE:

- Datafile đích không được tạo hoặc ghi đè như một thao tác restore bình thường.
- Database không được đưa về một SCN khác.
- Không có thao tác RECOVER DATABASE.
- Không mở database bằng RESETLOGS.
- Không chứng minh ứng dụng có thể khởi động sau phục hồi.

Đây là một bài kiểm tra đọc backup, không phải diễn tập phục hồi hoàn chỉnh.

## 3. RESTORE PREVIEW và RESTORE VALIDATE khác nhau

RMAN có lệnh PREVIEW để liệt kê các backup mà nó dự định dùng cho thao tác restore:

~~~text
RMAN> RESTORE DATABASE PREVIEW;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

PREVIEW giúp xem RMAN chọn backup set, datafile copy hoặc các thành phần liên quan nào dựa trên repository, thời điểm và cấu hình. Nó không tương đương việc đọc toàn bộ nội dung backup piece để xác minh khả năng đọc.

RESTORE VALIDATE thực hiện thêm bước đọc và kiểm tra các backup piece được chọn:

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

Một quy trình kiểm tra có thể dùng cả hai:

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
RMAN> RESTORE DATABASE VALIDATE;
~~~

Đọc PREVIEW trước giúp DBA hiểu RMAN định dùng backup nào. VALIDATE sau đó kiểm tra các backup piece cần thiết có thể đọc được hay không.

PREVIEW thành công không chứng minh backup piece không bị hỏng. Ngược lại, VALIDATE thành công cũng không chứng minh mọi điều kiện ngoài RMAN như dung lượng đích, quyền filesystem, password, wallet hoặc kết nối ứng dụng đã sẵn sàng.

## 4. Chỉ định thời điểm hoặc SCN khi kiểm tra restore

Phục hồi database thường phải xác định một thời điểm đích:

- Thời điểm trước khi xảy ra lỗi logic.
- SCN đã được ghi nhận trong kế hoạch recovery.
- Sequence archived redo cuối cùng có thể áp dụng.
- Một mốc thời gian phục vụ diễn tập PITR.

Ví dụ kiểm tra backup có thể dùng cho restore đến một thời điểm:

~~~text
RMAN> RUN {
  SET UNTIL TIME "TO_DATE('2026-11-14 02:00:00',
                          'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE PREVIEW SUMMARY;
  RESTORE DATABASE VALIDATE;
}
~~~

Thời điểm ở ví dụ chỉ minh họa. Cần thống nhất timezone, database host time, session time zone và cách RMAN diễn giải thời điểm. Với hệ thống cần độ chính xác cao, SCN thường là mốc rõ ràng hơn thời gian đồng hồ nếu SCN đã được ghi nhận đúng.

Ví dụ dùng SCN:

~~~text
RMAN> RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE PREVIEW;
  RESTORE DATABASE VALIDATE;
}
~~~

SCN phải là giá trị hợp lệ cho mục tiêu phục hồi và backup/redo hiện có. Chỉ định UNTIL trong restore validate giúp kiểm tra bộ backup được chọn theo cùng mục tiêu với kế hoạch phục hồi.

## 5. VALIDATE database và datafile

Lệnh VALIDATE đọc các block của database hoặc phạm vi được chỉ định để tìm lỗi. Ví dụ:

~~~text
RMAN> VALIDATE DATABASE;
~~~

Kiểm tra một tablespace:

~~~text
RMAN> VALIDATE TABLESPACE USERS;
~~~

Kiểm tra một datafile:

~~~text
RMAN> VALIDATE DATAFILE 7;
~~~

Kiểm tra một block cụ thể:

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

VALIDATE mặc định tập trung vào physical corruption như block không đọc được, checksum mismatch hoặc block header/body không nhất quán theo kiểm tra vật lý. Nó có thể phát hiện một số lỗi được ghi nhận trong quá trình đọc block.

### Kiểm tra logic bằng CHECK LOGICAL

Có thể yêu cầu RMAN kiểm tra thêm cấu trúc logic bên trong block:

~~~text
RMAN> VALIDATE DATABASE CHECK LOGICAL;
~~~

Hoặc giới hạn phạm vi:

~~~text
RMAN> VALIDATE DATAFILE 7 CHECK LOGICAL;
~~~

CHECK LOGICAL bổ sung kiểm tra cấu trúc block, chẳng hạn tính nhất quán của một số cấu trúc dữ liệu bên trong block. Kiểm tra này tốn thêm CPU và có thể làm thời gian validate dài hơn.

Không nên đồng nhất logical block check với kiểm tra đúng/sai nghiệp vụ. Một block có thể có cấu trúc Oracle hợp lệ nhưng chứa giá trị nghiệp vụ sai, ví dụ số dư bị cập nhật nhầm hoặc một bản ghi bị xóa hợp lệ về mặt cấu trúc nhưng sai với yêu cầu kinh doanh. RMAN CHECK LOGICAL không thay thế đối soát dữ liệu, constraint, kiểm tra ứng dụng hoặc kiểm toán nghiệp vụ.

## 6. BACKUP VALIDATE và VALIDATE BACKUPSET

Ngoài RESTORE VALIDATE, RMAN có các lệnh validate khác phục vụ những mục đích riêng.

### BACKUP VALIDATE

~~~text
RMAN> BACKUP VALIDATE DATABASE;
~~~

BACKUP VALIDATE đọc các datafile như một thao tác backup nhưng không tạo backup piece mới. Nó giúp kiểm tra dữ liệu nguồn mà một lần backup sẽ đọc. Có thể bổ sung CHECK LOGICAL:

~~~text
RMAN> BACKUP VALIDATE CHECK LOGICAL DATABASE;
~~~

BACKUP VALIDATE không thay thế việc kiểm tra backup đã tồn tại. Nó kiểm tra nguồn dữ liệu hiện tại, trong khi RESTORE VALIDATE kiểm tra backup mà RMAN dự định dùng để restore.

### VALIDATE BACKUPSET

Nếu cần kiểm tra một backup set cụ thể, có thể dùng:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> VALIDATE BACKUPSET 123;
~~~

Thay 123 bằng key của backup set lấy từ repository. VALIDATE BACKUPSET đọc backup set được chỉ định và kiểm tra tính toàn vẹn theo khả năng của RMAN.

Một backup set có thể chứa nhiều backup piece. Nếu backup set trải trên nhiều piece hoặc nhiều thiết bị, cần bảo đảm RMAN có thể truy cập toàn bộ piece cần thiết.

## 7. Phân biệt VALIDATE, CROSSCHECK và RESTORE VALIDATE

Ba lệnh thường bị nhầm:

| Lệnh | Mục tiêu | Có đọc nội dung block backup? |
|---|---|---|
| CROSSCHECK BACKUP | Đối chiếu repository với sự tồn tại/khả năng truy cập của backup trên thiết bị | Không phải kiểm tra đầy đủ nội dung block |
| VALIDATE BACKUPSET | Đọc và kiểm tra backup set cụ thể | Có |
| RESTORE DATABASE VALIDATE | Kiểm tra backup được chọn cho thao tác restore | Có, với các backup piece cần thiết |

Ví dụ CROSSCHECK:

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> LIST EXPIRED BACKUP;
~~~

CROSSCHECK cập nhật trạng thái repository khi backup không còn hiện diện hoặc không thể truy cập theo cách RMAN kiểm tra. Nó không chứng minh backup piece còn lại không có block hỏng.

Không chạy DELETE EXPIRED hoặc DELETE OBSOLETE chỉ vì muốn làm sạch danh sách mà chưa hiểu retention policy, backup dependency và quy trình bảo quản bản sao. Các lệnh xóa backup có thể làm giảm khả năng phục hồi.

## 8. Physical block corruption và logical block corruption

Một block Oracle có thể bị hỏng theo nhiều cách. Cần phân biệt:

### Physical corruption

Physical corruption xảy ra khi block không thể được đọc đúng hoặc cấu trúc vật lý không đáp ứng kiểm tra của Oracle. Ví dụ:

- Checksum không khớp.
- Block bị ghi dở hoặc fractured.
- Block header/body không nhất quán.
- I/O trả về dữ liệu lỗi hoặc block không đọc được.

Physical corruption có thể liên quan storage, controller, memory, filesystem, lỗi ghi, firmware hoặc phần mềm.

### Logical corruption

Logical corruption là block có thể đọc về mặt vật lý nhưng cấu trúc logic bên trong không hợp lệ theo quy tắc kiểm tra. Ví dụ có thể liên quan row directory, row piece hoặc cấu trúc index.

Logical corruption có thể được phát hiện khi bật CHECK LOGICAL hoặc khi database thực hiện một số thao tác đọc/kiểm tra. Không phải mọi lỗi logic đều có cùng nguyên nhân hoặc cách sửa.

### Lỗi nghiệp vụ không phải block corruption

Ví dụ:

- Giá sản phẩm bị cập nhật sai.
- Bản ghi khách hàng bị xóa nhầm.
- Một transaction nghiệp vụ commit sai.
- Dữ liệu giữa hai hệ thống không đồng bộ.

Các trường hợp này có thể cần Flashback, PITR, audit, application recovery hoặc đối soát nghiệp vụ. RMAN block validation không thể xác định dữ liệu có đúng nghiệp vụ hay không.

## 9. Các view theo dõi block corruption

Sau khi RMAN hoặc một số thao tác database phát hiện corruption, thông tin có thể được ghi vào các dynamic performance view.

### V$DATABASE_BLOCK_CORRUPTION

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$database_block_corruption
 ORDER BY file#, block#;
~~~

Các cột quan trọng:

- FILE#: số datafile chứa block.
- BLOCK#: block đầu tiên trong vùng bị báo lỗi.
- BLOCKS: số block liên tiếp trong vùng.
- CORRUPTION_CHANGE#: SCN liên quan đến corruption theo metadata.
- CORRUPTION_TYPE: loại lỗi được ghi nhận.

CORRUPTION_TYPE có thể biểu diễn các loại như CHECKSUM, FRACTURED, CORRUPT, LOGICAL hoặc các trạng thái khác tùy phiên bản và cách phát hiện.

Một dòng có BLOCKS lớn hơn 1 biểu thị một vùng nhiều block, không chỉ một block đơn lẻ. Khi lập kế hoạch sửa, cần tính toàn bộ phạm vi.

### V$BACKUP_CORRUPTION và V$COPY_CORRUPTION

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$backup_corruption
 ORDER BY file#, block#;

SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$copy_corruption
 ORDER BY file#, block#;
~~~

Các view này phản ánh corruption được phát hiện trong backup set hoặc image copy tương ứng. Một datafile nguồn không có corruption vẫn có thể có một backup copy bị lỗi do thiết bị, quá trình ghi hoặc truyền tải. Ngược lại, backup cũ có thể chứa block đã hỏng từ trước.

### Xác định tên datafile

~~~sql
SELECT file#,
       name
  FROM v$datafile
 ORDER BY file#;
~~~

Kết hợp FILE# với tên datafile giúp xác định tablespace và object liên quan:

~~~sql
SELECT d.file#,
       d.name,
       t.name AS tablespace_name
  FROM v$datafile d
  JOIN v$tablespace t
    ON t.ts# = d.ts#
 ORDER BY d.file#;
~~~

Nếu cần xác định segment chứa block, có thể dùng DBA_EXTENTS:

~~~sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       file_id,
       block_id,
       blocks
  FROM dba_extents
 WHERE file_id = 7
   AND 12345 BETWEEN block_id AND block_id + blocks - 1;
~~~

Thay FILE_ID và block number bằng giá trị thực tế. DBA_EXTENTS mô tả extent đã cấp cho segment; block có thể thuộc segment metadata, bitmap, undo hoặc loại block đặc biệt không ánh xạ thành một hàng DBA_EXTENTS theo cách đơn giản. Không có kết quả không chứng minh block không quan trọng.

## 10. Phát hiện corruption qua RMAN và database

Một số cách phát hiện phổ biến:

1. RMAN VALIDATE đọc datafile hoặc backup.
2. RMAN RESTORE VALIDATE đọc backup piece cần cho restore.
3. Database gặp lỗi khi đọc block trong truy vấn hoặc hoạt động nền.
4. DBVERIFY kiểm tra file/block ở mức công cụ ngoài database trong các trường hợp phù hợp.
5. Oracle báo lỗi trong alert log hoặc trace.

Một số lỗi thường gặp:

| Mã lỗi | Ý nghĩa khái quát |
|---|---|
| ORA-01578 | Oracle phát hiện block bị hỏng |
| ORA-01110 | Cho biết datafile liên quan đến lỗi khác |
| ORA-19566 | RMAN không thể đọc số block hỏng vượt ngưỡng trong backup operation |
| ORA-19624 | Lỗi khi xử lý backup/restore operation; cần xem lỗi đi kèm |
| ORA-270xx | Lỗi tầng I/O hoặc hệ điều hành, thường cần xem chi tiết OS error |

Không chẩn đoán nguyên nhân chỉ từ một mã lỗi. Đọc đầy đủ error stack, alert log, trace, OS/storage log và kết quả RMAN.

## 11. Kiểm tra block theo phạm vi nhỏ trước

Khi có nghi ngờ ở một datafile hoặc một vùng block, có thể validate có mục tiêu:

~~~text
RMAN> VALIDATE DATAFILE 7;
~~~

Hoặc:

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

Nếu cần kiểm tra logic:

~~~text
RMAN> VALIDATE DATAFILE 7 CHECK LOGICAL;
~~~

Phạm vi nhỏ giúp điều tra nhanh hơn và giảm I/O so với validate toàn bộ database. Tuy nhiên, nếu corruption có thể nằm ở nơi khác, kiểm tra một block không thay thế một lịch validate toàn diện.

Sau khi validate, truy vấn V$DATABASE_BLOCK_CORRUPTION và đối chiếu alert log/RMAN output. Ghi nhận file number, block range, corruption type, thời điểm phát hiện và thao tác đã chạy.

## 12. Sửa block bằng Block Media Recovery

Khi corruption là loại có thể phục hồi ở cấp block và có backup/redo phù hợp, RMAN có thể thực hiện block media recovery. Thay vì restore cả datafile, RMAN phục hồi block bị hỏng từ backup rồi áp dụng redo cần thiết.

Ví dụ:

~~~text
RMAN> RECOVER DATAFILE 7 BLOCK 12345;
~~~

Hoặc phục hồi các block được liệt kê trong corruption list:

~~~text
RMAN> RECOVER CORRUPTION LIST;
~~~

Block media recovery thường hữu ích khi:

- Chỉ một số block bị hỏng.
- Database có backup hợp lệ chứa block cần thiết.
- Có archived redo cần thiết để đưa block về trạng thái nhất quán.
- Database ở chế độ và cấu hình hỗ trợ thao tác.

Không phải mọi corruption đều có thể sửa bằng block media recovery. Logical corruption, block thuộc các cấu trúc đặc biệt, thiếu backup/redo hoặc corruption ở phạm vi rộng có thể cần phương án khác. Cần đối chiếu tài liệu RMAN đúng phiên bản và đánh giá loại lỗi trước khi thực hiện.

### Vì sao block media recovery giảm thời gian gián đoạn?

Nếu chỉ một block của một datafile lớn bị hỏng, restore toàn bộ datafile có thể yêu cầu nhiều I/O và thời gian hơn. Block media recovery chỉ xử lý block được chỉ định, trong khi các block khác của datafile vẫn có thể tiếp tục được truy cập theo điều kiện hỗ trợ.

Tuy nhiên, thao tác vẫn tiêu thụ tài nguyên, cần backup và redo, và phải được theo dõi. Không coi đây là thao tác không có rủi ro.

### Sau khi phục hồi block

Kiểm tra:

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_type
  FROM v$database_block_corruption
 ORDER BY file#, block#;
~~~

Chạy validate lại phạm vi đã sửa:

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

Kiểm tra alert log, RMAN output, ứng dụng và đối soát dữ liệu liên quan. Nếu corruption list không còn dòng tương ứng, đó là tín hiệu tốt nhưng vẫn cần xác nhận truy vấn thực tế và tính đúng đắn nghiệp vụ.

## 13. Khi nào cần restore datafile hoặc tablespace?

Block media recovery không phải lúc nào cũng phù hợp. Có thể cần restore/recover datafile hoặc tablespace khi:

- Nhiều block bị hỏng hoặc corruption trải rộng.
- Backup/redo không đáp ứng điều kiện block recovery.
- Datafile bị mất hoặc không thể đọc ở cấp file.
- Corruption liên quan cấu trúc cần phục hồi ở phạm vi lớn hơn.
- Kế hoạch recovery yêu cầu khôi phục về một SCN/thời điểm cụ thể.

Ví dụ khung lệnh phục hồi datafile:

~~~text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
~~~

Đây chỉ là khung thao tác, không phải lệnh có thể chạy an toàn trên mọi trạng thái database. Nếu datafile thuộc SYSTEM, UNDO, đang online, database ở NOARCHIVELOG, hoặc file đang được sử dụng, quy trình có thể khác đáng kể. Phải kiểm tra trạng thái, backup, redo, control file, datafile path và tài liệu release trước.

Sau khi phục hồi datafile, có thể cần đưa file online hoặc thực hiện thao tác mở database phù hợp. Không dùng ALTER DATABASE OPEN RESETLOGS như một bước mặc định cho mọi datafile recovery.

## 14. Backup có thể đọc nhưng vẫn không đủ để phục hồi

RESTORE VALIDATE thành công không chứng minh có đủ mọi thành phần để mở database ở điểm đích. Những dependency thường bị bỏ sót:

- Control file hoặc recovery catalog.
- SPFILE và các tham số cần thiết.
- Tất cả datafile cần thiết.
- Archived redo log liên tục đến thời điểm đích.
- Online redo cần thiết trong kịch bản cụ thể.
- TDE keystore/wallet và password.
- Backup encryption password hoặc Oracle key material.
- Password file và cấu hình listener/service.
- Filesystem/ASM disk group và quyền truy cập đích.
- External table, DIRECTORY, BFILE, external procedure hoặc dữ liệu ngoài database.
- Cấu hình Data Guard/RAC nếu thuộc phạm vi phục hồi.

Một backup datafile tốt nhưng thiếu archived redo cần thiết có thể không recover được đến SCN mong muốn. Một database được mã hóa TDE có thể restore được file nhưng không mở được nếu keystore không sẵn sàng.

Vì vậy, backup plan cần lưu giữ và thử phục hồi cả các thành phần hỗ trợ, không chỉ datafile.

## 15. Kiểm tra archived redo và khả năng recovery

RMAN cần archived redo phù hợp để recover datafile hoặc database đến điểm đích. Có thể liệt kê archived log:

~~~text
RMAN> LIST ARCHIVELOG ALL;
~~~

Kiểm tra backup của archived log:

~~~text
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

Và validate các backup cần thiết thông qua restore validate:

~~~text
RMAN> RESTORE ARCHIVELOG ALL VALIDATE;
~~~

Phạm vi lệnh và lựa chọn log phụ thuộc thời điểm, repository và cấu hình. Trong thực tế, nên validate log cần cho một khoảng SCN/time cụ thể thay vì mặc định đọc toàn bộ lịch sử.

Một cách kiểm tra archive log trong database:

~~~sql
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
~~~

Trong RAC, mỗi thread có sequence riêng. Khi kiểm tra tính liên tục, phải xét tất cả thread liên quan, không chỉ một thread. Một số bản ghi có thể đại diện cho nhiều bản sao archived log; status/name cần được hiểu đúng theo repository và control file.

## 16. Kiểm tra backup pieces và thiết bị lưu trữ

Backup có thể nằm trên disk, tape hoặc media manager. RESTORE VALIDATE cần đọc được backup piece qua channel và thiết bị tương ứng.

Trước khi validate:

- Kiểm tra channel configuration.
- Kiểm tra quyền đọc file backup.
- Kiểm tra mount point hoặc ASM disk group.
- Kiểm tra media manager/SBT library nếu dùng tape.
- Kiểm tra credential và network đến backup appliance.
- Xác nhận encryption password hoặc keystore có sẵn khi cần.

Ví dụ cấu hình channel SBT phụ thuộc media manager:

~~~text
RMAN> RUN {
  ALLOCATE CHANNEL c1 DEVICE TYPE SBT_TAPE;
  RESTORE DATABASE VALIDATE;
  RELEASE CHANNEL c1;
}
~~~

Đây chỉ là khung minh họa. Hệ thống tape thường cần PARMS, ENV hoặc cấu hình channel được vendor cung cấp. Không copy cấu hình SBT từ môi trường khác nếu chưa xác nhận thư viện và credential.

Với disk backup, RMAN có thể dùng DISK channel mặc định hoặc channel đã cấu hình. Khi validate thất bại, phân biệt:

- Backup piece không tồn tại.
- Quyền đọc hoặc đường dẫn sai.
- Thiết bị không mount.
- Media manager lỗi.
- Backup piece bị hỏng.
- Thiếu encryption key/password.

Không kết luận backup hỏng nếu nguyên nhân thực tế là media manager không truy cập được.

## 17. Quy trình kiểm tra định kỳ bằng RMAN

Một lịch vận hành có thể kết hợp:

### Sau mỗi backup quan trọng

- Xác nhận job hoàn tất và backup piece được ghi.
- Kiểm tra RMAN output và lỗi cảnh báo.
- Crosscheck theo chính sách thiết bị.
- Ghi nhận DBID, thời điểm, backup tag và vị trí lưu.

### Theo lịch validate

- Chạy RESTORE DATABASE VALIDATE theo lịch và phạm vi được chọn.
- Chạy VALIDATE DATABASE hoặc VALIDATE DATAFILE theo lịch để kiểm tra nguồn dữ liệu.
- Bổ sung CHECK LOGICAL theo tần suất và ngân sách tài nguyên phù hợp.
- Kiểm tra corruption list và RMAN output.

### Theo lịch restore drill

- Chọn một backup set hoặc mốc thời điểm đại diện.
- Restore vào môi trường cô lập.
- Recover đến SCN/time mục tiêu.
- Mở database theo quy trình phù hợp.
- Kiểm tra ứng dụng và dữ liệu.
- Đo RTO/RPO thực tế.

Tần suất cụ thể phải theo SLA, độ quan trọng dữ liệu, dung lượng, chi phí backup storage và chính sách tổ chức. Không nên chạy validate toàn database với tần suất cao nếu nó tạo I/O cạnh tranh với workload production.

## 18. Thiết kế restore drill an toàn

Restore drill là diễn tập phục hồi thật nhưng phải được cách ly khỏi production. Mục tiêu là chứng minh có thể phục hồi một database từ backup và redo, không phải kiểm tra bằng cách ghi đè file production.

### Chuẩn bị môi trường

Trước khi restore:

1. Chuẩn bị máy hoặc môi trường thử nghiệm tách biệt.
2. Bảo đảm không dùng chung đường dẫn datafile với production.
3. Chuẩn bị đủ dung lượng cho datafile, FRA/TEMP và archived redo.
4. Chuẩn bị Oracle Home, patch level và cấu hình tương thích.
5. Chuẩn bị password file, SPFILE, control file và DBID.
6. Chuẩn bị TDE wallet/keystore và mật khẩu nếu database được mã hóa.
7. Chuẩn bị quyền truy cập backup storage/media manager.
8. Xác định SCN hoặc thời điểm cần phục hồi.
9. Xác định tên database, DB_UNIQUE_NAME, listener/service và cách cô lập network.

Môi trường drill không được vô tình cung cấp service trùng production hoặc gửi email, message, payment hay job thật. Vô hiệu hóa outbound integration và scheduler job không phù hợp trước khi mở ứng dụng thử nghiệm.

### Chuẩn bị bộ backup

Kiểm tra:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
RMAN> RESTORE DATABASE VALIDATE;
~~~

Nếu drill cần PITR, chạy PREVIEW và VALIDATE với cùng UNTIL SCN hoặc UNTIL TIME dự kiến. Xác nhận archived redo, control file và các thành phần mã hóa.

### Thực hiện restore và recover

Trong môi trường thử nghiệm, quy trình có thể gồm:

1. Khởi động instance NOMOUNT với SPFILE/PFILE phù hợp.
2. Restore control file nếu cần.
3. Mount database.
4. Catalog backup nếu backup không có trong repository hiện tại.
5. Restore datafile vào đường dẫn đích đã được map.
6. Recover database đến SCN/time mục tiêu.
7. Mở database theo chế độ phù hợp, thường là RESETLOGS sau incomplete recovery.
8. Kiểm tra PDB và service.
9. Chạy smoke test và đối soát dữ liệu.

Các bước và lệnh chính xác phụ thuộc loại backup, control file có sẵn hay không, ASM/filesystem, DBID, CDB/PDB, RAC và kiểu recovery. Không dùng một script restore chung cho mọi database.

## 19. Khung diễn tập restore trên môi trường cô lập

Ví dụ dưới đây minh họa thứ tự ở mức khái niệm cho một database có backup RMAN trên disk. Các đường dẫn, DBID, tên database, SPFILE, control file và SCN phải được thay theo runbook thật.

~~~text
RMAN> STARTUP NOMOUNT;
RMAN> SET DBID 1234567890;
RMAN> RESTORE SPFILE FROM AUTOBACKUP;
~~~

Nếu dùng SPFILE được restore, cần restart instance theo quy trình phù hợp để nạp SPFILE. Nếu control file cần restore:

~~~text
RMAN> STARTUP NOMOUNT;
RMAN> RESTORE CONTROLFILE FROM AUTOBACKUP;
RMAN> ALTER DATABASE MOUNT;
~~~

Sau khi mount, nếu backup piece không có trong repository hiện tại, catalog đường dẫn phù hợp:

~~~text
RMAN> CATALOG START WITH '/backup/stage/';
RMAN> LIST BACKUP SUMMARY;
~~~

Restore và recover:

~~~text
RMAN> RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Với incomplete recovery đến SCN/time, mở database bằng RESETLOGS theo quy trình recovery tương ứng:

~~~text
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

Không chạy ví dụ trên trên production. Các lệnh STARTUP, RESTORE CONTROLFILE, SET DBID, CATALOG, SET UNTIL và OPEN RESETLOGS phải được đặt đúng trình tự theo tình huống. Nếu database là CDB, cần kiểm tra PDB sau khi mở CDB và thực hiện các thao tác PDB recovery nếu phạm vi drill yêu cầu.

### Kiểm tra sau khi mở

~~~sql
SELECT name,
       open_mode,
       database_role
  FROM v$database;

SELECT name,
       open_mode,
       restricted
  FROM v$pdbs
 ORDER BY name;
~~~

Sau đó kiểm tra:

- Datafile và tablespace ở trạng thái mong đợi.
- PDB ứng dụng đã mở đúng chế độ.
- Invalid object và component status.
- Job không phù hợp đã bị vô hiệu hóa trong drill.
- Service thử nghiệm trỏ đến database phục hồi, không phải production.
- Ứng dụng có thể đăng nhập và thực hiện truy vấn nghiệp vụ cơ bản.
- Dữ liệu tại thời điểm đích đúng với yêu cầu drill.

## 20. Đo RTO và RPO

Restore drill cần đo kết quả thay vì chỉ đánh dấu pass/fail.

**RTO (Recovery Time Objective)** là thời gian mục tiêu để đưa dịch vụ trở lại hoạt động sau sự cố. Trong drill, ghi lại thời gian từ lúc bắt đầu quy trình phục hồi đến khi ứng dụng vượt qua các kiểm tra sẵn sàng đã định nghĩa.

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa được chấp nhận, thường biểu diễn bằng khoảng thời gian dữ liệu. Trong drill, ghi lại thời điểm/SCN dữ liệu cuối cùng có thể phục hồi và so sánh với thời điểm sự cố giả định.

Ví dụ:

| Chỉ số | Mục tiêu | Kết quả drill |
|---|---|---|
| RTO | 2 giờ | 1 giờ 35 phút |
| RPO | 15 phút | 8 phút |
| Restore validate | Thành công | Thành công |
| Recovery đến SCN đích | Thành công | Thành công |
| PDB mở đúng chế độ | READ WRITE | READ WRITE |
| Smoke test ứng dụng | Thành công | Thành công |

Các con số trên chỉ minh họa. RTO/RPO phải được xác định theo yêu cầu nghiệp vụ, không lấy ví dụ làm SLA mặc định.

Nếu restore validate mất 30 phút nhưng restore drill mất 4 giờ, cần tìm bottleneck trong datafile restore, archived redo apply, storage throughput, cấu hình channel, network hoặc kiểm tra ứng dụng.

## 21. Diễn tập các kịch bản khác nhau

Không nên chỉ thử restore toàn database một lần rồi coi mọi kịch bản đã được chứng minh. Các tình huống cần xem xét:

| Kịch bản | Nội dung cần thử |
|---|---|
| Mất một datafile | Restore/recover datafile và xác nhận tablespace hoạt động |
| Hỏng một số block | Validate, phát hiện corruption và block media recovery nếu phù hợp |
| Mất control file | Restore control file, mount và tiếp tục recovery |
| Mất SPFILE | Restore SPFILE hoặc dựng PFILE tối thiểu để phục hồi |
| Lỗi logic do thao tác nhầm | PITR đến trước thời điểm lỗi, kiểm tra dữ liệu |
| Mất toàn bộ host | Phục hồi trên host/môi trường khác với đường dẫn mới |
| Mất primary trong Data Guard | Thử quy trình switchover/failover riêng theo kiến trúc |
| Mất PDB hoặc dữ liệu trong PDB | Diễn tập PDB restore/recovery phù hợp với phiên bản |
| Thiếu TDE wallet | Xác minh khả năng lấy lại keystore và mở dữ liệu mã hóa |
| Mất backup storage/site | Phục hồi từ bản sao ở vị trí khác hoặc media offsite |

Mỗi kịch bản có điều kiện và thủ tục riêng. Đặc biệt, Data Guard switchover/failover không giống RMAN restore drill; cần runbook và diễn tập riêng.

## 22. Theo dõi hiệu năng và tác động của VALIDATE

VALIDATE và RESTORE VALIDATE đọc lượng dữ liệu lớn, do đó có thể tạo I/O đáng kể. Trước khi chạy trên production:

- Xác định dung lượng database và backup.
- Ước tính thời gian đọc và tốc độ storage.
- Kiểm tra workload giờ cao điểm.
- Giới hạn channel parallelism phù hợp.
- Chọn cửa sổ chạy và theo dõi latency.
- Xác định tác động đến FRA, tape library hoặc backup appliance.
- Không chạy đồng thời quá nhiều job validate/backup/restore nếu gây cạnh tranh.

RMAN có thể dùng nhiều channel để đọc song song. Tăng channel có thể giảm thời gian nếu storage đủ khả năng, nhưng cũng có thể làm production chậm hơn do I/O contention.

Một ví dụ giới hạn channel:

~~~text
RMAN> RUN {
  ALLOCATE CHANNEL c1 DEVICE TYPE DISK;
  ALLOCATE CHANNEL c2 DEVICE TYPE DISK;
  RESTORE DATABASE VALIDATE;
  RELEASE CHANNEL c1;
  RELEASE CHANNEL c2;
}
~~~

Số channel cần được điều chỉnh theo throughput, CPU, backup device và mức tải. Không mặc định càng nhiều channel càng tốt.

## 23. Kiểm tra cấu hình block protection

Một số tham số ảnh hưởng việc phát hiện lỗi block:

~~~sql
SHOW PARAMETER db_block_checksum;
SHOW PARAMETER db_block_checking;
~~~

DB_BLOCK_CHECKSUM điều khiển việc Oracle tính và kiểm tra checksum block theo cấu hình. DB_BLOCK_CHECKING điều khiển một số kiểm tra logic block khi database xử lý block. Các mức và overhead phụ thuộc phiên bản, workload và cấu hình.

Không thay đổi các tham số này trong production chỉ vì vừa phát hiện corruption. Trước hết cần xem giá trị hiện tại, khuyến nghị Oracle cho release, chi phí CPU/I/O và quy trình thay đổi. Checksum giúp phát hiện một số dạng hỏng; nó không bảo đảm phát hiện mọi lỗi phần cứng hoặc mọi lỗi logic nghiệp vụ.

## 24. Diễn giải kết quả validate

Khi RMAN validate hoàn tất, cần đọc cả summary và lỗi chi tiết:

- Số datafile/backup piece đã được kiểm tra.
- Số block đã được đọc.
- Thời gian thực hiện.
- Block corruption được phát hiện.
- Backup piece không thể truy cập hoặc không đọc được.
- Lỗi I/O, media manager hoặc encryption.
- Datafile/backup piece và block range liên quan.

Một thông báo RMAN hoàn tất không có lỗi là bằng chứng rằng phạm vi đã chọn được kiểm tra thành công theo loại kiểm tra được yêu cầu. Nó không chứng minh mọi backup trong repository đều tốt hoặc mọi thời điểm PITR đều có đủ redo.

Nếu có corruption:

1. Dừng việc xóa backup hoặc cleanup liên quan.
2. Lưu output RMAN và alert log.
3. Truy vấn corruption views.
4. Xác định file, block range, corruption type.
5. Xác định corruption nằm ở datafile nguồn hay backup piece.
6. Kiểm tra các bản backup khác và archived redo.
7. Chọn block recovery, datafile restore/recover hoặc phương án phù hợp.
8. Validate lại và kiểm tra ứng dụng.
9. Điều tra nguyên nhân hạ tầng để tránh tái diễn.

Không bỏ qua corruption chỉ vì ứng dụng chưa báo lỗi. Một block có thể chưa được truy cập trong workload hiện tại nhưng sẽ gây lỗi khi một truy vấn hoặc batch đọc đến nó.

## 25. Những sai lầm thường gặp

**Coi RESTORE VALIDATE là restore thật:** lệnh không tạo datafile phục hồi và không mở database. Cần restore drill riêng.

**Coi PREVIEW là kiểm tra nội dung backup:** PREVIEW liệt kê backup RMAN định chọn; cần VALIDATE để đọc backup piece.

**Coi CROSSCHECK là kiểm tra block:** CROSSCHECK chủ yếu đối chiếu repository với sự tồn tại/khả năng truy cập của backup, không đọc toàn bộ nội dung như VALIDATE.

**Chỉ chạy VALIDATE DATABASE mà không kiểm tra backup:** database nguồn có thể tốt trong khi backup piece đã hỏng. Cần RESTORE VALIDATE hoặc VALIDATE BACKUPSET.

**Chỉ chạy RESTORE VALIDATE mà không kiểm tra datafile nguồn:** backup có thể đọc được nhưng dữ liệu nguồn hiện tại đã có corruption mới. Chọn thêm VALIDATE DATABASE theo lịch.

**Bỏ qua CHECK LOGICAL:** một số lỗi cấu trúc logic có thể không được phát hiện nếu chỉ kiểm tra vật lý. Chọn tần suất logical check phù hợp.

**Cho rằng CHECK LOGICAL kiểm tra dữ liệu nghiệp vụ:** nó kiểm tra cấu trúc block, không xác minh mọi quy tắc nghiệp vụ.

**Không lưu TDE wallet hoặc backup encryption password:** datafile/backup có thể đọc được nhưng không giải mã được khi phục hồi.

**Không kiểm tra archived redo:** restore datafile thành công nhưng recovery không thể đi đến SCN/time đích.

**Diễn tập trên production path:** có nguy cơ ghi đè file thật. Dùng môi trường cô lập và đường dẫn đích riêng.

**Chỉ đo thời gian RMAN restore:** RTO còn bao gồm khởi động, recover, mở PDB/service, xác nhận dữ liệu và đưa ứng dụng hoạt động.

**Không kiểm tra sau recovery:** database OPEN không có nghĩa ứng dụng đã sẵn sàng hoặc dữ liệu đúng.

## 26. Mẫu lịch và bằng chứng vận hành

Một lịch bảo đảm khả năng phục hồi có thể có:

| Hoạt động | Mục đích | Bằng chứng cần lưu |
|---|---|---|
| Sau mỗi backup | Xác nhận backup job hoàn tất | RMAN log, tag, thời điểm, vị trí backup |
| Theo lịch crosscheck | Phát hiện backup hết hạn/không còn truy cập | CROSSCHECK output và danh sách expired |
| Theo lịch restore validate | Kiểm tra backup có thể đọc cho restore | RMAN log, backup piece được chọn, kết quả |
| Theo lịch database validate | Phát hiện corruption ở datafile nguồn | RMAN output, corruption view trước/sau |
| Theo lịch logical validate | Kiểm tra thêm cấu trúc logic block | Output CHECK LOGICAL và tài nguyên sử dụng |
| Theo lịch restore drill | Chứng minh quy trình recovery thực tế | SCN/time, log restore/recover, smoke test, RTO/RPO |
| Sau thay đổi hạ tầng | Xác nhận đường backup/restore vẫn hoạt động | Kết quả validate và drill có mục tiêu |

Mỗi lần kiểm tra nên lưu:

- DBID, DB_UNIQUE_NAME, database role và release.
- Thời điểm bắt đầu/kết thúc cùng timezone.
- Backup tag, backup set key và device type.
- SCN/time đích nếu có.
- Channel và cấu hình media manager.
- Kết quả RMAN, warning và error stack.
- Corruption list.
- RTO/RPO và kết quả smoke test.
- Người thực hiện, người review và ticket thay đổi.

Log RMAN có thể chứa đường dẫn, tên host, object và metadata nhạy cảm. Bảo vệ quyền truy cập và retention theo chính sách tổ chức.

## 27. Runbook mẫu: từ phát hiện block hỏng đến xác nhận phục hồi

Giả sử RMAN validate phát hiện block hỏng ở datafile 7:

**Bước 1: ghi nhận kết quả và không xóa backup**

Lưu RMAN output, timestamp, lỗi đầy đủ và trạng thái database.

**Bước 2: kiểm tra corruption list**

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$database_block_corruption
 WHERE file# = 7
 ORDER BY block#;
~~~

**Bước 3: xác định datafile và segment**

~~~sql
SELECT file#,
       name
  FROM v$datafile
 WHERE file# = 7;
~~~

Nếu block thuộc một segment, đối chiếu DBA_EXTENTS và metadata liên quan.

**Bước 4: kiểm tra backup thay thế**

~~~text
RMAN> LIST BACKUP OF DATAFILE 7;
RMAN> RESTORE DATAFILE 7 PREVIEW;
RMAN> RESTORE DATAFILE 7 VALIDATE;
~~~

Xác nhận RMAN có backup phù hợp và có thể đọc. Kiểm tra archived redo cần thiết.

**Bước 5: chọn cách phục hồi**

Nếu corruption thuộc loại có thể block media recovery và có backup/redo:

~~~text
RMAN> RECOVER DATAFILE 7 BLOCK 12345;
~~~

Nếu file bị mất hoặc corruption rộng, lập kế hoạch restore/recover datafile hoặc tablespace theo trạng thái database.

**Bước 6: validate lại**

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

Kiểm tra lại V$DATABASE_BLOCK_CORRUPTION, alert log và kết quả RMAN.

**Bước 7: kiểm tra ứng dụng và nguyên nhân gốc**

Chạy truy vấn liên quan, smoke test, đối soát dữ liệu và kiểm tra storage/OS log. Nếu lỗi đến từ thiết bị hoặc đường I/O, cần xử lý hạ tầng trước khi coi sự cố đã kết thúc.

Các lệnh trên là mẫu quy trình, không phải một chuỗi có thể chạy nguyên trạng trong mọi database. Xác định đúng block, backup, redo, loại corruption và trạng thái file trước khi thực hiện recovery.

## 28. Kết luận

RESTORE DATABASE VALIDATE kiểm tra các backup mà RMAN chọn để phục hồi database và đọc các backup piece cần thiết mà không ghi đè datafile đích. RESTORE PREVIEW cho biết RMAN định dùng backup nào; VALIDATE DATABASE và CHECK LOGICAL kiểm tra block của database nguồn; VALIDATE BACKUPSET kiểm tra một backup set cụ thể; CROSSCHECK chỉ đối chiếu repository với khả năng hiện diện/truy cập của backup.

Khi phát hiện block corruption, hãy xem RMAN output, V$DATABASE_BLOCK_CORRUPTION, V$BACKUP_CORRUPTION và V$COPY_CORRUPTION để xác định file, block range và loại lỗi. Block media recovery có thể sửa một số corruption phù hợp khi có backup và redo, còn corruption rộng hoặc loại không hỗ trợ có thể cần restore/recover ở phạm vi lớn hơn.

Cuối cùng, validate không thay thế restore drill. Hãy diễn tập trong môi trường cô lập, kiểm tra control file, SPFILE, datafile, archived redo, TDE keystore, service và PDB, rồi mở database và chạy smoke test. Đo RTO/RPO và lưu bằng chứng để biết quy trình phục hồi thực sự đáp ứng yêu cầu nghiệp vụ.
