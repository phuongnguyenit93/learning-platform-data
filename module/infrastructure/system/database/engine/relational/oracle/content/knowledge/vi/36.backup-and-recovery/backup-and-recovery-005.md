# Full backup, incremental level 0/1 và block change tracking

Oracle Recovery Manager (RMAN) hỗ trợ nhiều cách sao lưu database. Với database lớn, backup toàn bộ mỗi ngày có thể tốn thời gian và dung lượng. Incremental backup giúp giảm lượng dữ liệu phải đọc/ghi bằng cách chỉ sao lưu các block thay đổi kể từ một mốc backup trước đó. Block Change Tracking (BCT) tiếp tục tối ưu quá trình này bằng cách giúp RMAN tìm các block đã thay đổi mà không phải quét toàn bộ datafile để xác định chúng.

Ba khái niệm cần phân biệt:

- **Full backup:** backup đầy đủ theo yêu cầu RMAN, nhưng không làm cha (parent) cho incremental level 1.
- **Incremental level 0:** baseline chứa các block đã sử dụng của datafile, có thể làm nền cho các incremental level 1 tiếp theo.
- **Incremental level 1:** chỉ sao lưu các block thay đổi kể từ level 0 hoặc level 1 trước đó, theo kiểu differential hoặc cumulative.
- **Block Change Tracking:** file bitmap do Oracle duy trì để ghi nhận vị trí block thay đổi, giúp RMAN xác định nhanh block cần đọc cho incremental backup.

Lựa chọn chiến lược phải dựa trên RPO, RTO, tốc độ phát sinh redo, kích thước database, cửa sổ backup, băng thông và thời gian restore. Backup nhỏ hơn chưa chắc phục hồi nhanh hơn; cần kiểm thử cả backup lẫn restore/recover.

## 1. RMAN và các thành phần backup

RMAN là công cụ Oracle dùng để backup, restore và recover database. RMAN hiểu cấu trúc database, datafile, control file, archived redo log và metadata backup.

Một kế hoạch backup thường bảo vệ:

- Datafile của database.
- Control file.
- SPFILE.
- Archived redo log khi database ở ARCHIVELOG mode.
- Keystore nếu database dùng TDE.
- Recovery catalog nếu tổ chức sử dụng catalog.
- Cấu hình, password file, wallet và các artifact cần cho quy trình phục hồi.

RMAN có thể ghi backup ra disk hoặc media manager/tape thông qua channel và device type phù hợp.

### 1.1 Backup set và image copy

RMAN hỗ trợ hai dạng backup chính:

**Backup set**

- Là định dạng backup riêng của RMAN.
- Chứa backup pieces.
- Có thể chỉ lưu các block đã sử dụng của datafile.
- Có thể dùng compression và encryption theo cấu hình hỗ trợ.
- Thường là định dạng mặc định cho RMAN backup.

**Image copy**

- Là bản sao file ở dạng tương ứng với datafile/control file gốc.
- Có thể dùng trực tiếp trong một số quy trình restore/switch.
- Phù hợp với incremental merge khi cập nhật image copy bằng level 1.
- Thường chiếm dung lượng gần với file nguồn.

Không nhầm image copy với bản copy OS tùy tiện. Image copy do RMAN quản lý và được ghi nhận trong repository.

### 1.2 RMAN repository

RMAN lưu metadata về backup trong:

- Control file của target database.
- Recovery catalog nếu được cấu hình.

Metadata có thể gồm backup piece, datafile, archived log, checkpoint SCN, tag, completion time và trạng thái. Metadata không thay thế bản backup vật lý. Nếu file backup bị mất, repository có thể vẫn còn record cũ cho tới khi crosscheck.

### 1.3 Channel

Channel là kết nối RMAN dùng để đọc/ghi backup. Channel có thể được cấu hình cho DISK hoặc SBT_TAPE và có thể chạy song song.

Ví dụ:

~~~text
RMAN> CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
~~~

Parallelism cao hơn có thể tăng throughput nhưng cũng tiêu thụ CPU, I/O, memory và network nhiều hơn. Hãy benchmark trên storage thật.

## 2. Full backup là gì?

Full backup là bản backup đầy đủ các block cần thiết của đối tượng được sao lưu. Với datafile, RMAN thường chỉ sao lưu các block đã được sử dụng, không nhất thiết ghi toàn bộ các block trống như một bản copy vật lý từng byte.

Ví dụ:

~~~text
RMAN> BACKUP DATABASE;
~~~

Lệnh này tạo full backup database theo cấu hình RMAN. Nếu không chỉ định incremental level, đây là full backup chứ không phải level 0.

### 2.1 Full backup không phải incremental level 0

Đây là điểm rất quan trọng:

- Full backup có thể dùng để restore database.
- Full backup không được dùng làm parent cho incremental level 1.
- Level 0 backup là baseline được RMAN sử dụng trong incremental backup strategy.

Ví dụ:

~~~text
RMAN> BACKUP DATABASE;
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

Full backup đầu tiên không trở thành level 0 chỉ vì nó chứa toàn bộ dữ liệu. Nếu chưa có level 0 phù hợp, RMAN có thể phải tạo level 0 khi thực hiện incremental strategy. Không xây dựng kế hoạch dựa trên giả định full backup thông thường sẽ là parent của level 1.

### 2.2 Khi nào full backup phù hợp?

- Database nhỏ, thời gian backup cho phép.
- Cần một bản full độc lập để restore đơn giản.
- Làm baseline định kỳ theo chính sách.
- Trước/sau một thay đổi lớn nếu quy trình yêu cầu.
- Môi trường không cần incremental chain phức tạp.

### 2.3 Full backup và restore time

Full backup có thể làm quy trình restore đơn giản vì ít phụ thuộc vào incremental chain. Tuy nhiên, restore vẫn cần archived redo log để recover tới thời điểm mong muốn trong ARCHIVELOG mode.

Full backup không đồng nghĩa không cần archive log và không tự tạo point-in-time recovery nếu thiếu redo.

## 3. Incremental backup là gì?

Incremental backup chỉ lưu các block thay đổi theo một mốc backup trước đó. Thay vì đọc và ghi toàn bộ dữ liệu mỗi lần, RMAN có thể sao lưu phần block được xác định là đã thay đổi.

Lợi ích:

- Giảm lượng dữ liệu backup.
- Giảm thời gian backup khi tỷ lệ block thay đổi thấp.
- Giảm băng thông truyền backup.
- Có thể rút ngắn cửa sổ backup.

Chi phí:

- Cần quản lý chuỗi baseline và incremental.
- Restore/recover có thể cần áp dụng nhiều incremental backup.
- Backup strategy và retention phức tạp hơn.
- Nếu tỷ lệ block thay đổi cao, incremental có thể gần bằng full về lượng dữ liệu.

## 4. Incremental level 0

Incremental level 0 là baseline của incremental backup strategy. Nó sao lưu các block đã sử dụng của datafile và có thể làm parent cho level 1.

Ví dụ:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0 DATABASE;
~~~

Level 0 có thể được tạo thành backup set hoặc image copy tùy cú pháp và cấu hình.

### 4.1 Level 0 chứa gì?

Về khái niệm, level 0 chứa dữ liệu cần thiết của datafile tại mốc backup. RMAN ghi nhận checkpoint/SCN của backup để xác định phạm vi thay đổi cho incremental tiếp theo.

Level 0 không phải bản sao logic của từng hàng SQL. Đây là backup vật lý theo block.

### 4.2 Level 0 làm parent cho level 1

Ví dụ:

~~~text
Ngày 1: Incremental level 0
Ngày 2: Incremental level 1
Ngày 3: Incremental level 1
Ngày 4: Incremental level 1
~~~

Các level 1 sẽ dựa vào mốc level 0 và/hoặc level 1 trước đó tùy differential/cumulative.

### 4.3 Tạo level 0 mới

Khi database thay đổi lớn, incremental chain quá dài hoặc lịch backup yêu cầu, có thể tạo level 0 mới. Level 0 mới làm baseline cho các level 1 sau đó.

Không tạo level 0 quá thường xuyên nếu mục tiêu incremental là giảm thời gian/dung lượng. Cần cân bằng baseline refresh và restore chain.

## 5. Incremental level 1: differential và cumulative

RMAN hỗ trợ hai kiểu level 1:

- Differential level 1: sao lưu block thay đổi kể từ incremental backup gần nhất ở level 0 hoặc level 1.
- Cumulative level 1: sao lưu block thay đổi kể từ incremental level 0 gần nhất.

### 5.1 Differential level 1

Lệnh:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

Giả sử lịch:

| Ngày | Backup |
|---|---|
| Thứ Hai | Level 0 |
| Thứ Ba | Level 1 differential |
| Thứ Tư | Level 1 differential |
| Thứ Năm | Level 1 differential |

Level 1 thứ Tư chỉ cần chứa các block thay đổi kể từ backup incremental gần nhất trước đó, tức level 1 thứ Ba trong ví dụ.

Ưu điểm:

- Mỗi incremental thường nhỏ hơn cumulative nếu lượng thay đổi mỗi ngày không quá lớn.
- Backup nhanh hơn khi tỷ lệ thay đổi hằng ngày thấp.

Nhược điểm:

- Restore có thể phải áp dụng nhiều level 1 liên tiếp sau level 0.
- Nếu thiếu một incremental cần thiết trong chain, có thể phải chọn đường restore khác hoặc baseline khác.

### 5.2 Cumulative level 1

Lệnh:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

Cumulative level 1 sao lưu mọi block thay đổi kể từ level 0 gần nhất.

Ví dụ:

| Ngày | Backup |
|---|---|
| Thứ Hai | Level 0 |
| Thứ Ba | Level 1 cumulative |
| Thứ Tư | Level 1 cumulative |
| Thứ Năm | Level 1 cumulative |

Level 1 cumulative thứ Năm chứa các block thay đổi kể từ level 0 thứ Hai, kể cả các block đã được sao lưu trong cumulative thứ Ba và thứ Tư.

Ưu điểm:

- Restore thường chỉ cần level 0 và cumulative level 1 mới nhất để đưa datafile tới mốc cumulative đó.
- Ít phụ thuộc vào nhiều incremental trung gian.

Nhược điểm:

- Backup hằng ngày có thể lớn dần cho tới lần level 0 kế tiếp.
- Có thể đọc/ghi lặp lại các block đã thay đổi từ đầu chu kỳ.
- Cửa sổ backup và dung lượng archive/backup có thể tăng.

### 5.3 So sánh differential và cumulative

| Tiêu chí | Differential level 1 | Cumulative level 1 |
|---|---|---|
| Mốc so sánh | Level 0 hoặc level 1 gần nhất | Level 0 gần nhất |
| Kích thước mỗi backup | Thường nhỏ hơn | Thường tăng theo thời gian từ level 0 |
| Số incremental cần apply | Có thể cần nhiều level 1 | Có thể chỉ cần level 1 cumulative gần nhất |
| Backup window | Thường ngắn hơn | Có thể dài hơn |
| Restore complexity | Chain dài hơn | Chain đơn giản hơn |
| Phù hợp | Muốn giảm dung lượng/backup time | Muốn đơn giản hóa restore |

Không có lựa chọn đúng cho mọi database. Hãy đo tỷ lệ thay đổi, thời gian backup, thời gian restore và yêu cầu RTO.

## 6. Ví dụ chuỗi incremental

Giả sử database có 1 TB block đã sử dụng và mỗi ngày thay đổi khoảng 2%:

~~~text
Thứ Hai: Level 0
   |
   +-- Thứ Ba: Level 1
   |
   +-- Thứ Tư: Level 1
   |
   +-- Thứ Năm: Level 1
   |
   +-- Thứ Sáu: Level 1
~~~

Nếu differential, mỗi level 1 thường chỉ chứa thay đổi kể từ incremental trước đó. Nếu cumulative, level 1 cuối tuần có thể chứa tổng hợp thay đổi từ level 0.

Các tỷ lệ 2% và 1 TB chỉ là ví dụ minh họa. Dung lượng backup thực tế còn phụ thuộc block size, unused blocks, compression, block changes và overhead.

### 6.1 Differential restore chain

~~~text
Restore Level 0
      |
      v
Apply Level 1 (Tue)
      |
      v
Apply Level 1 (Wed)
      |
      v
Apply Level 1 (Thu)
      |
      v
Apply archived redo logs
      |
      v
Recover to target SCN/time
~~~

### 6.2 Cumulative restore chain

~~~text
Restore Level 0
      |
      v
Apply latest Level 1 CUMULATIVE
      |
      v
Apply archived redo logs
      |
      v
Recover to target SCN/time
~~~

Sơ đồ mô tả khái niệm. RMAN tự lựa chọn backup cần thiết theo repository và lệnh RESTORE/RECOVER; người vận hành phải kiểm tra preview và output thực tế.

## 7. Block Change Tracking (BCT) là gì?

Block Change Tracking là cơ chế Oracle ghi nhận các block đã thay đổi vào một file bitmap riêng. Khi RMAN thực hiện incremental backup, BCT giúp RMAN xác định những vùng có block thay đổi mà không cần quét toàn bộ datafile để tìm chúng.

Không có BCT:

- RMAN có thể phải đọc nhiều block của datafile để xác định block nào thay đổi kể từ mốc backup.
- Sau khi xác định, RMAN chỉ backup các block thay đổi cần thiết.

Có BCT:

- Oracle duy trì bitmap về các block thay đổi.
- RMAN dùng bitmap để xác định vùng cần đọc.
- RMAN vẫn đọc block dữ liệu cần backup và ghi backup như bình thường.

### 7.1 BCT không phải incremental backup

BCT không tạo backup, không lưu bản sao dữ liệu và không thay thế RMAN. Nó chỉ tăng tốc bước xác định block thay đổi.

### 7.2 BCT không thay đổi nội dung backup

BCT không làm incremental backup thiếu block và không làm giảm yêu cầu recovery. RMAN vẫn phải backup đầy đủ các block cần thiết theo level và mốc SCN.

### 7.3 BCT có lợi nhất khi nào?

- Database lớn.
- Incremental level 1 chạy thường xuyên.
- Tỷ lệ block thay đổi thấp so với kích thước datafile.
- Quá trình đọc datafile để tìm changed blocks là bottleneck.
- Có đủ dung lượng và I/O để duy trì BCT file.

BCT có thể không đem lại lợi ích đáng kể khi:

- Chỉ chạy full hoặc level 0 backup.
- Hầu hết block thay đổi mỗi chu kỳ.
- Database nhỏ.
- Storage đọc toàn bộ datafile đã đủ nhanh.
- Backup bottleneck nằm ở network, compression, output device hoặc media manager.

## 8. Bật Block Change Tracking

Trước khi bật, DBA cần xác định vị trí file BCT, quyền filesystem, storage redundancy và chính sách backup.

Ví dụ:

~~~sql
ALTER DATABASE ENABLE BLOCK CHANGE TRACKING
USING FILE '/u02/oradata/ORCL/bct01.ctf';
~~~

Đường dẫn chỉ là ví dụ. File cần nằm trên storage ổn định, có đủ dung lượng và được Oracle software owner truy cập.

Kiểm tra:

~~~sql
SELECT status,
       filename,
       bytes
FROM v$block_change_tracking;
~~~

Các cột thường gặp:

- STATUS: trạng thái tracking.
- FILENAME: vị trí BCT file.
- BYTES: kích thước file.

Metadata view có thể khác theo phiên bản.

### 8.1 Tắt BCT

~~~sql
ALTER DATABASE DISABLE BLOCK CHANGE TRACKING;
~~~

Chỉ tắt khi có lý do vận hành hoặc cần thay đổi file theo quy trình. Khi BCT tắt, incremental backup vẫn chạy nhưng có thể phải quét nhiều block để tìm thay đổi.

### 8.2 Đổi vị trí BCT file

Cách di chuyển phụ thuộc phiên bản. Một phương án tương thích rộng là:

1. Xác nhận backup window và workload.
2. Tắt BCT.
3. Chuẩn bị vị trí mới.
4. Bật BCT với file mới.
5. Kiểm tra STATUS và FILENAME.
6. Chạy incremental backup thử và theo dõi elapsed time.

Một số release có cú pháp MOVE BLOCK CHANGE TRACKING FILE. Kiểm tra tài liệu đúng phiên bản trước khi dùng. Không xóa file đang được database sử dụng.

## 9. BCT file và vòng đời

BCT file là file phụ trợ để tăng tốc incremental backup, không phải datafile chứa dữ liệu nghiệp vụ.

Các điểm cần nhớ:

- BCT file có thể được tái tạo nếu bị mất; incremental backup tiếp theo có thể phải quét datafile đầy đủ để khởi tạo tracking lại.
- BCT file không thay thế backup datafile hoặc archived redo log.
- BCT file không cần được coi như một thành phần bắt buộc để phục hồi database từ RMAN backup; sau restore/recovery cần kiểm tra trạng thái và cấu hình lại theo release.
- Không copy BCT file đang mở bằng OS rồi coi bản copy là bản backup hợp lệ.
- Nếu database dùng RAC, BCT file phải nằm trên vị trí mà cấu hình cluster hỗ trợ và được quản lý đúng theo release.

### 9.1 BCT và restore/resetlogs

Sau restore, duplicate, resetlogs hoặc thay đổi kiến trúc, cần kiểm tra BCT status. Một số thao tác có thể làm BCT file không còn phù hợp hoặc cần tạo lại. Đừng giả định BCT file từ database nguồn luôn dùng được cho database clone/đích.

### 9.2 BCT không phải một phần của recovery chain

RMAN restore/recover cần backup và redo phù hợp. BCT chỉ hỗ trợ tạo incremental backup nhanh hơn. Mất BCT file không đồng nghĩa mất khả năng restore từ backup đã tạo.

## 10. BCT có thể cải thiện incremental backup ra sao?

Giả sử:

- Datafile có 500 GB block đã sử dụng.
- Mỗi ngày chỉ 1% block thay đổi.
- Backup level 1 cần khoảng 5 GB block thay đổi trước compression.

Không có BCT, RMAN có thể phải đọc nhiều block của 500 GB datafile để tìm các block thay đổi. Có BCT, RMAN có thể dựa trên bitmap để chỉ đọc các vùng có thay đổi, rồi backup khoảng 5 GB block cần thiết.

Các con số chỉ minh họa. BCT không đảm bảo lượng I/O giảm chính xác theo tỷ lệ 100:1 vì còn phụ thuộc block distribution, bitmap granularity, file layout, backup type và các yếu tố khác.

### 10.1 BCT chủ yếu giúp giảm đọc khi xác định block

BCT không nhất thiết làm backup piece nhỏ hơn so với cùng một incremental backup không có BCT. Nội dung block được backup vẫn do thay đổi dữ liệu quyết định. Lợi ích chủ yếu là giảm công việc đọc/scan để tìm changed blocks.

### 10.2 BCT không tăng tốc full/level 0 theo cùng cách

Full backup hoặc incremental level 0 phải đọc các block cần backup theo baseline. BCT không giúp bỏ qua các block chưa thay đổi so với baseline vì baseline cần chứa dữ liệu hiện tại.

Lợi ích chính của BCT nằm ở incremental level 1.

## 11. Cấu hình và theo dõi BCT

### 11.1 Kiểm tra trạng thái

~~~sql
SELECT status,
       filename,
       bytes
FROM v$block_change_tracking;
~~~

### 11.2 Kiểm tra file ở hệ điều hành

DBA có thể kiểm tra file có tồn tại, ownership và dung lượng ở OS. Không thay đổi nội dung hoặc di chuyển file khi database chưa được thông báo bằng lệnh phù hợp.

### 11.3 Theo dõi incremental backup

RMAN output và backup metadata cho biết thời gian, bytes, datafile và backup set. Có thể xem:

~~~sql
SELECT session_key,
       input_type,
       status,
       start_time,
       end_time,
       elapsed_seconds,
       input_bytes,
       output_bytes,
       input_bytes_per_sec,
       output_bytes_per_sec
FROM v$rman_backup_job_details
ORDER BY start_time DESC;
~~~

Các cột có thể khác theo phiên bản và quyền. So sánh job level 1 trước/sau khi bật BCT trong cùng workload, không so sánh hai job khác tải.

## 12. Tạo full backup và incremental backup bằng RMAN

### 12.1 Full backup

~~~text
RMAN> BACKUP DATABASE;
~~~

Tạo full backup database. Đây không phải baseline level 0 cho incremental chain.

### 12.2 Incremental level 0

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0 DATABASE;
~~~

Tạo baseline cho level 1.

### 12.3 Incremental level 1 differential

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

Nếu không có từ khóa CUMULATIVE, level 1 là differential.

### 12.4 Incremental level 1 cumulative

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

Sao lưu các block thay đổi kể từ level 0 gần nhất.

### 12.5 Kèm archived redo log

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Hoặc:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE PLUS ARCHIVELOG;
~~~

PLUS ARCHIVELOG yêu cầu RMAN xử lý archived redo log theo quy trình của lệnh. Kiểm tra output để xác nhận các sequence cần thiết đã được backup.

## 13. Ví dụ lịch backup differential

Giả sử database chạy ARCHIVELOG, level 0 vào Chủ nhật và level 1 differential mỗi ngày:

| Ngày | Lệnh/loại backup | Mục tiêu |
|---|---|---|
| Chủ nhật | Level 0 | Baseline tuần |
| Thứ Hai | Level 1 differential | Block thay đổi từ level 0 |
| Thứ Ba | Level 1 differential | Block thay đổi từ level 1 thứ Hai |
| Thứ Tư | Level 1 differential | Block thay đổi từ level 1 thứ Ba |
| Thứ Năm | Level 1 differential | Block thay đổi từ level 1 thứ Tư |
| Thứ Sáu | Level 1 differential | Block thay đổi từ level 1 thứ Năm |
| Thứ Bảy | Level 1 differential | Block thay đổi từ level 1 thứ Sáu |

Archived redo log được backup thường xuyên giữa các lần datafile backup để đáp ứng RPO.

## 14. Ví dụ lịch backup cumulative

| Ngày | Lệnh/loại backup | Mục tiêu |
|---|---|---|
| Chủ nhật | Level 0 | Baseline tuần |
| Thứ Hai | Level 1 cumulative | Thay đổi từ Chủ nhật |
| Thứ Ba | Level 1 cumulative | Tất cả thay đổi từ Chủ nhật |
| Thứ Tư | Level 1 cumulative | Tất cả thay đổi từ Chủ nhật |
| Thứ Năm | Level 1 cumulative | Tất cả thay đổi từ Chủ nhật |
| Thứ Sáu | Level 1 cumulative | Tất cả thay đổi từ Chủ nhật |
| Thứ Bảy | Level 1 cumulative | Tất cả thay đổi từ Chủ nhật |

Restore về mốc thứ Bảy có thể dùng level 0 Chủ nhật và level 1 cumulative thứ Bảy, sau đó apply archived redo cần thiết.

## 15. Chọn differential hay cumulative

Hãy cân nhắc:

**Differential**

- Tỷ lệ thay đổi mỗi ngày nhỏ.
- Backup window hẹp.
- Muốn giảm dung lượng incremental hằng ngày.
- Chấp nhận restore apply nhiều incremental.
- Có công cụ và quy trình tự động chọn chain đáng tin cậy.

**Cumulative**

- Muốn giảm số incremental cần apply khi restore.
- Restore time quan trọng hơn dung lượng backup tăng dần.
- Storage đủ lớn.
- Chu kỳ level 0 không quá dài.
- Dữ liệu thay đổi không khiến cumulative quá lớn.

Có thể kết hợp differential hằng ngày và cumulative theo chu kỳ để cân bằng backup window và restore time. Cần kiểm thử chain thực tế trước khi chọn.

## 16. Incremental merge với image copy

Incremental merge là chiến lược cập nhật image copy bằng các incremental backup để duy trì một bản copy gần trạng thái hiện tại.

Khái niệm:

1. Tạo image copy baseline.
2. Tạo level 1 incremental cho các block thay đổi.
3. Dùng RECOVER COPY để merge incremental vào image copy.
4. Image copy được cập nhật dần.

Ví dụ khung:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0
      FOR RECOVER OF COPY WITH TAG 'DAILY_MERGE'
      DATABASE;

RMAN> RECOVER COPY OF DATABASE
      WITH TAG 'DAILY_MERGE';

RMAN> BACKUP INCREMENTAL LEVEL 1
      FOR RECOVER OF COPY WITH TAG 'DAILY_MERGE'
      DATABASE;
~~~

Đây là ví dụ khung cho incremental merge. Thứ tự và cách lập lịch đầy đủ cần theo runbook RMAN của phiên bản, vì lần chạy đầu có thể tạo image copy baseline và các lần sau mới có incremental để merge.

### 16.1 Lợi ích

- Duy trì image copy gần hiện tại.
- Có thể giảm thời gian cần để restore datafile vì bản copy đã được cập nhật.
- Phù hợp khi RTO quan trọng và có đủ disk.

### 16.2 Chi phí

- Cần dung lượng cho image copy và incremental.
- Cần lập lịch merge.
- Cần quản lý tag và checkpoint.
- Cần kiểm tra image copy có recoverable và đúng mốc.

Incremental merge không thay thế archived redo log nếu muốn recover tới thời điểm sau image copy.

## 17. RMAN CONFIGURE và script backup

RMAN cho phép lưu cấu hình mặc định:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
RMAN> CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
RMAN> CONFIGURE BACKUP OPTIMIZATION ON;
~~~

BACKUP OPTIMIZATION có thể tránh backup lại một số file đã được backup theo quy tắc RMAN. Cần hiểu ảnh hưởng của nó tới archive log và retention.

### 17.1 Ví dụ script level 0

~~~text
RUN {
  BACKUP INCREMENTAL LEVEL 0
    DATABASE
    TAG 'WEEKLY_L0';

  BACKUP ARCHIVELOG ALL
    TAG 'ARCHIVE_WEEKLY';

  BACKUP CURRENT CONTROLFILE;
}
~~~

### 17.2 Ví dụ script level 1 differential

~~~text
RUN {
  BACKUP INCREMENTAL LEVEL 1
    DATABASE
    TAG 'DAILY_L1_DIFF';

  BACKUP ARCHIVELOG ALL
    TAG 'DAILY_ARCH';
}
~~~

### 17.3 Ví dụ script level 1 cumulative

~~~text
RUN {
  BACKUP INCREMENTAL LEVEL 1 CUMULATIVE
    DATABASE
    TAG 'DAILY_L1_CUM';

  BACKUP ARCHIVELOG ALL
    TAG 'DAILY_ARCH';
}
~~~

Các ví dụ cần bổ sung channel, format, encryption, logging, deletion policy và error handling theo chuẩn tổ chức. Không chạy script production trước khi thử trong môi trường tương đương.

## 18. Compression và encryption của backup

RMAN backup set có thể dùng compression:

~~~text
RMAN> BACKUP AS COMPRESSED BACKUPSET DATABASE;
~~~

Compression có thể giảm dung lượng nhưng tiêu thụ CPU và có thể làm chậm backup/restore. Chọn algorithm/level theo license và phiên bản.

Backup encryption là cơ chế riêng:

- Transparent encryption có thể dựa vào keystore.
- Password encryption yêu cầu mật khẩu khi restore.
- Dual mode kết hợp cơ chế theo hỗ trợ phiên bản.

Nếu database dùng TDE, không mặc định mọi file backup hoặc export đều được mã hóa theo cùng cách. Hãy kiểm tra backup type và RMAN encryption configuration.

## 19. Restore và recover từ level 0/1

Restore lấy datafile từ backup. Recover áp dụng incremental backup và redo để đưa datafile tới trạng thái nhất quán.

### 19.1 Complete recovery

~~~text
RMAN> STARTUP MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
RMAN> ALTER DATABASE OPEN;
~~~

RMAN tự chọn các backup/incremental/archive log phù hợp theo repository và mục tiêu recovery. Trong thực tế có thể cần restore control file, catalog, SPFILE và keystore trước.

### 19.2 Xem trước restore

~~~text
RMAN> RESTORE DATABASE PREVIEW;
~~~

PREVIEW liệt kê backup RMAN dự kiến dùng, giúp kiểm tra chain và file cần thiết.

### 19.3 Kiểm tra khả năng đọc backup

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

VALIDATE đọc và kiểm tra backup theo phạm vi, nhưng không tạo datafile đã restore và không chứng minh toàn bộ recovery/open thành công.

### 19.4 Recover tới thời điểm

~~~text
RMAN> RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 10:30:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

Đây là ví dụ incomplete recovery. Thời điểm phải xác định theo timezone và clock của database. Sau OPEN RESETLOGS, database tạo incarnation mới và cần kế hoạch backup mới.

## 20. Level 1 và archived redo log có vai trò khác nhau

Incremental level 1 chứa block đã thay đổi kể từ backup incremental trước đó. Archived redo log chứa redo records để phục hồi các thay đổi theo SCN.

Hai loại file không thay thế nhau:

- Incremental backup giúp đưa datafile tiến nhanh tới một mốc backup.
- Archived redo log giúp apply các thay đổi sau mốc backup tới thời điểm recovery.

Ví dụ:

~~~text
Level 0 (Sunday)
      |
      v
Level 1 (Wednesday)
      |
      v
Archived redo logs (Wed -> Fri 14:30)
      |
      v
Target recovery point: Friday 14:30
~~~

Nếu thiếu archived redo log cần thiết sau incremental, database có thể không recover tới target SCN.

## 21. Block Change Tracking và restore/recovery

BCT không được dùng để tái tạo dữ liệu trong restore. Khi restore database, RMAN dùng backup datafile và redo. BCT file là metadata tăng tốc cho incremental backup trong tương lai.

Sau khi restore:

- Kiểm tra V$BLOCK_CHANGE_TRACKING.
- Nếu status không ENABLED hoặc file không còn hợp lệ, cấu hình lại.
- Không để việc thiếu BCT cản trở restore nếu backup và redo đầy đủ.
- Incremental backup đầu tiên sau khi tạo lại BCT có thể phải đọc nhiều datafile hơn.

## 22. Kiểm tra backup metadata

### 22.1 LIST BACKUP

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

### 22.2 REPORT NEED BACKUP

~~~text
RMAN> REPORT NEED BACKUP;
~~~

Lệnh báo cáo datafile cần backup theo retention policy/cấu hình. Kết quả cần đọc trong bối cảnh policy và RPO.

### 22.3 CROSSCHECK

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK đối chiếu repository với file thực tế. Nó không tự backup file bị thiếu.

### 22.4 DELETE EXPIRED

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

DELETE EXPIRED xóa record expired khỏi repository sau khi crosscheck phát hiện file không còn tồn tại. Nó không phải lệnh xóa mọi backup cũ theo retention.

### 22.5 DELETE OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
RMAN> DELETE OBSOLETE;
~~~

DELETE OBSOLETE xóa backup không còn cần thiết theo retention policy. Trước khi chạy, kiểm tra policy, off-site copy, standby requirements và restore chain.

## 23. Thiết kế retention cho incremental chain

Retention phải đủ để giữ:

- Level 0 baseline.
- Level 1 differential/cumulative cần thiết.
- Archived redo log để recover tới target.
- Control file/SPFILE backup.
- Backup ngoài site.

Nếu retention xóa level 0 quá sớm, level 1 có thể không còn đường restore phù hợp. Nếu giữ archive quá ngắn, PITR tới mốc cũ có thể thất bại.

### 23.1 Recovery window

Ví dụ:

~~~text
RMAN> CONFIGURE RETENTION POLICY
     TO RECOVERY WINDOW OF 14 DAYS;
~~~

Recovery window 14 ngày không đơn giản có nghĩa xóa mọi file cũ hơn 14 ngày. RMAN phải giữ các backup cần thiết để đáp ứng khả năng phục hồi trong window, bao gồm các backup cũ hơn có thể là nền tảng.

### 23.2 Redundancy

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

Redundancy 2 giữ đủ các backup theo quy tắc RMAN để có hai bản cần thiết. Nó không tương đương recovery window theo số ngày.

## 24. Performance: đo hiệu quả incremental và BCT

Để đánh giá BCT, so sánh incremental backup trước và sau khi bật trong điều kiện workload tương đương:

- Thời gian backup.
- Input bytes.
- Output bytes.
- Read throughput.
- CPU.
- Storage IOPS/latency.
- Tỷ lệ block thay đổi.
- Backup piece size.

Không so sánh level 0 với level 1 rồi kết luận BCT cải thiện bao nhiêu; đây là hai loại backup có lượng dữ liệu khác nhau.

### 24.1 Đọc RMAN job details

~~~sql
SELECT session_key,
       input_type,
       status,
       start_time,
       end_time,
       elapsed_seconds,
       input_bytes,
       output_bytes,
       input_bytes_per_sec,
       output_bytes_per_sec
FROM v$rman_backup_job_details
ORDER BY start_time DESC;
~~~

### 24.2 Đọc RMAN backup set

~~~sql
SELECT set_stamp,
       set_count,
       backup_type,
       incremental_level,
       pieces,
       start_time,
       completion_time
FROM v$backup_set
ORDER BY completion_time DESC;
~~~

Tên/cột view có thể khác theo phiên bản. RMAN LIST BACKUP là cách kiểm tra trực tiếp và thường dễ đọc hơn cho operator.

## 25. BCT trong môi trường RAC và Data Guard

### 25.1 RAC

BCT file phải đặt trên storage phù hợp với kiến trúc RAC và được database quản lý. DBA cần kiểm tra trạng thái khi các instance hoạt động, đường dẫn dùng chung và khả năng truy cập từ các node theo yêu cầu phiên bản.

Không đặt BCT file trên filesystem local của một node nếu database/backup architecture yêu cầu các instance khác cùng truy cập.

### 25.2 Data Guard

Primary và standby có thể có BCT file riêng để tăng tốc incremental backup được thực hiện tại từng database. BCT file không phải redo được transport như archived log.

Sau switchover/failover, kiểm tra BCT status trên database mới đóng vai primary và nơi thực hiện backup. Không giả định BCT file trên primary tự trở thành BCT file hợp lệ trên standby.

## 26. Các lỗi thường gặp với incremental backup

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Level 1 không nhỏ hơn level 0 nhiều | Nhiều block thay đổi hoặc compression khác | Đo changed-block ratio và backup type |
| RMAN tạo level 0 khi yêu cầu level 1 | Chưa có level 0 phù hợp | Kiểm tra LIST BACKUP và baseline |
| Restore cần nhiều incremental | Differential chain | Cân nhắc cumulative hoặc level 0 thường xuyên hơn |
| Incremental backup vẫn đọc nhiều datafile | BCT tắt, không khả dụng hoặc thay đổi nhiều | Kiểm tra V$BLOCK_CHANGE_TRACKING |
| BCT status DISABLED | Chưa bật hoặc đã tắt | Bật lại sau khi xác nhận vị trí file |
| BCT file mất | File system/storage issue | Tạo lại BCT; incremental tiếp theo có thể scan nhiều |
| Restore validate thành công nhưng recovery lỗi | Thiếu archive hoặc backup chain | RESTORE PREVIEW, kiểm tra thread/sequence/SCN |
| Backup piece bị EXPIRED | File mất hoặc không truy cập được | CROSSCHECK, kiểm tra storage và repository |
| FRA đầy | Archive/backup/flashback giữ dung lượng | RMAN policy, tăng capacity, không xóa OS |
| Backup job chậm sau tăng parallelism | I/O/CPU/network contention | Điều chỉnh channel/parallelism |

## 27. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Coi full backup là level 0 | Incremental chain không có baseline đúng | Tạo BACKUP INCREMENTAL LEVEL 0 |
| Nghĩ level 1 luôn cumulative | Restore dependency bị hiểu sai | Xác định differential hay cumulative |
| Nghĩ BCT tạo backup | Bỏ qua RMAN backup thật | Dùng BCT cùng incremental RMAN |
| Nghĩ BCT làm backup nhỏ hơn | Hiểu sai tác dụng | BCT chủ yếu giảm scan để tìm changed blocks |
| Nghĩ BCT cần để restore | Tưởng mất BCT là mất dữ liệu | BCT không phải recovery chain |
| Chỉ giữ level 1 mà xóa level 0 | Không còn baseline để restore | Giữ chain theo retention |
| Xóa differential trung gian | Có thể làm mất chain cần thiết | Dùng RMAN retention và kiểm tra restore preview |
| Chỉ backup datafile, không backup archive | Không recover tới target time | Backup archived redo log |
| Không backup control file/SPFILE | Khó dựng lại database | Bật control file autobackup |
| Không backup keystore TDE | Không giải mã được dữ liệu | Bảo vệ keystore cùng backup |
| Tăng parallelism tối đa | Gây I/O/CPU contention | Benchmark và giới hạn channel |
| Chỉ chạy RESTORE VALIDATE | Chưa chứng minh recovery hoàn chỉnh | Diễn tập restore/recover/open |
| Dùng BCT nhưng không kiểm tra status | Tưởng BCT hoạt động trong khi disabled | Giám sát V$BLOCK_CHANGE_TRACKING |
| Coi incremental nhỏ là restore nhanh | Có thể phải apply chain dài | Đo cả backup và restore time |

## 28. Bài thực hành tự kiểm tra

Các bài tập nên thực hiện trong database lab hoặc môi trường đã được DBA cho phép.

### Bài 1 — Full backup

Chạy BACKUP DATABASE. Dùng LIST BACKUP để xác định loại backup và giải thích vì sao nó không phải level 0.

### Bài 2 — Level 0 baseline

Chạy BACKUP INCREMENTAL LEVEL 0 DATABASE. Xem metadata incremental_level và tag trong RMAN repository.

### Bài 3 — Differential level 1

Thay đổi dữ liệu giữa hai lần backup. Chạy level 1 differential nhiều ngày và vẽ chain parent/child.

### Bài 4 — Cumulative level 1

Tạo level 0 rồi chạy cumulative level 1 ở nhiều ngày. So sánh lượng block được backup và restore chain.

### Bài 5 — Bật BCT

Bật BCT trong lab, kiểm tra V$BLOCK_CHANGE_TRACKING và vị trí file.

### Bài 6 — Đo incremental trước/sau BCT

Chạy workload thay đổi một tỷ lệ nhỏ block. So sánh elapsed time và input bytes của incremental level 1 trước/sau BCT.

### Bài 7 — Tắt và bật lại BCT

Tắt BCT, xác nhận status. Bật lại với file mới và kiểm tra incremental backup tiếp theo.

### Bài 8 — Restore preview

Chạy RESTORE DATABASE PREVIEW. Ghi các backup piece và incremental cần thiết cho restore.

### Bài 9 — Restore validate

Chạy RESTORE DATABASE VALIDATE và phân biệt kết quả với restore/recover thực tế.

### Bài 10 — Incremental merge

Trong lab, tạo image copy baseline và chạy RECOVER COPY cùng level 1 FOR RECOVER OF COPY. Kiểm tra image copy được cập nhật.

### Bài 11 — Retention

Thử REPORT OBSOLETE và REPORT NEED BACKUP. Giải thích vì sao một level 0 cũ có thể vẫn cần giữ.

### Bài 12 — Recovery drill

Restore level 0, apply incremental chain và archived redo tới một thời điểm mục tiêu. Ghi lại thời gian restore, recover và open.

## 29. Checklist thiết kế backup

**Yêu cầu nghiệp vụ**

- RPO và RTO đã được phê duyệt?
- Cần PITR bao nhiêu ngày?
- Database có Data Guard/RAC/TDE?
- Có yêu cầu off-site/immutable backup?

**Chiến lược level**

- Full backup hay level 0 baseline?
- Level 1 differential hay cumulative?
- Chu kỳ level 0?
- Cần incremental merge không?
- Restore chain dài tối đa bao nhiêu?

**BCT**

- Incremental level 1 có thường xuyên?
- Tỷ lệ changed blocks đủ thấp để BCT có lợi?
- BCT file đặt trên storage phù hợp?
- Có giám sát STATUS/FILENAME?
- Có kế hoạch sau restore/clone/resetlogs?

**RMAN**

- Backup database và archive log?
- Control file autobackup?
- SPFILE?
- Retention/deletion policy?
- Channel/parallelism?
- Backup encryption/compression?
- Recovery catalog?

**Khả năng phục hồi**

- RESTORE PREVIEW?
- RESTORE VALIDATE?
- Có đủ archive sequence/thread?
- Có keystore TDE?
- Đã diễn tập restore/recover/open?
- RTO thực tế đạt mục tiêu?

## 30. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Full backup | Backup đầy đủ, không phải parent của level 1 |
| Incremental level 0 | Baseline cho incremental strategy |
| Incremental level 1 | Backup block thay đổi kể từ mốc trước |
| Differential level 1 | Thay đổi kể từ level 0 hoặc level 1 gần nhất |
| Cumulative level 1 | Thay đổi kể từ level 0 gần nhất |
| BCT | Bitmap ghi nhận block thay đổi, giúp RMAN tìm block nhanh hơn |
| BCT file | File phụ trợ, không phải backup dữ liệu |
| BACKUP DATABASE | Tạo full backup |
| BACKUP INCREMENTAL LEVEL 0 | Tạo baseline incremental |
| BACKUP INCREMENTAL LEVEL 1 | Tạo differential level 1 |
| BACKUP INCREMENTAL LEVEL 1 CUMULATIVE | Tạo cumulative level 1 |
| FOR RECOVER OF COPY | Hỗ trợ incremental merge với image copy |
| RESTORE | Khôi phục file từ backup |
| RECOVER | Áp dụng incremental và redo |
| RESTORE PREVIEW | Xem trước backup cần cho restore |
| RESTORE VALIDATE | Kiểm tra khả năng đọc backup, không thay restore drill |
| Retention policy | Xác định backup cần giữ |
| Archived redo log | Cho phép recover sau mốc backup |
| RPO/RTO | Mục tiêu mất dữ liệu và thời gian phục hồi |

Full backup là bản backup độc lập; incremental level 0 mới là baseline cho level 1. Differential level 1 thường tiết kiệm dung lượng hơn nhưng có thể cần áp dụng nhiều incremental khi restore; cumulative level 1 thường đơn giản hóa restore nhưng backup lớn dần trong chu kỳ. BCT ghi nhận block thay đổi để giảm công việc quét tìm block của incremental backup, không tạo backup và không thay thế archived redo log. Hãy thiết kế lịch theo RPO/RTO, đo cả thời gian backup lẫn restore, giữ đầy đủ level 0/1 và archive log cần thiết, bảo vệ control file/SPFILE/keystore, rồi xác nhận bằng restore drill.
