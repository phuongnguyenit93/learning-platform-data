# Retention policy, redundancy, recovery window và deletion policy

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Sao lưu và phục hồi  
> **Mục tiêu:** Hiểu cách RMAN quyết định backup nào còn cần cho khả năng phục hồi; phân biệt retention policy với archived log deletion policy; chọn REDUNDANCY hoặc RECOVERY WINDOW theo RPO/RTO; hiểu OBSOLETE và EXPIRED; quản lý archived redo log trong môi trường standalone và Data Guard; kiểm tra cấu hình, dự báo dung lượng và xây dựng quy trình xóa an toàn.

## 1. Hai chính sách khác nhau trong vòng đời backup

RMAN có nhiều quy tắc để quyết định dữ liệu backup nào cần được giữ và khi nào file có thể bị xóa. Hai chính sách thường bị nhầm lẫn là:

- **Backup retention policy:** xác định những backup nào còn cần thiết để đáp ứng mục tiêu phục hồi. Backup không còn cần theo chính sách này được đánh dấu OBSOLETE.
- **Archived log deletion policy:** xác định điều kiện archived redo log phải đáp ứng trước khi RMAN cho phép xóa log khỏi vị trí lưu trữ được quản lý.

Hai chính sách liên quan nhưng không thay thế nhau.

Ví dụ:

- Retention policy yêu cầu giữ khả năng phục hồi về bất kỳ thời điểm nào trong 7 ngày gần nhất.
- Deletion policy yêu cầu archived redo log phải được backup ít nhất một lần lên DISK trước khi xóa.
- Nếu database có Data Guard, deletion policy còn có thể yêu cầu log đã được ship hoặc apply tới standby.

Một archived log có thể không còn cần cho một backup cụ thể nhưng vẫn chưa đủ điều kiện xóa theo deletion policy. Ngược lại, log đã được backup đủ số bản nhưng vẫn có thể cần để phục hồi tới một thời điểm nằm trong recovery window.

**Không dùng một lệnh DELETE chỉ dựa vào tuổi file hoặc dung lượng đang dùng.** Trước khi xóa, cần biết backup nào còn cần, log nào còn cần cho recovery, standby đã nhận/apply đến đâu và bản backup còn đọc được không.

## 2. Các khái niệm nền tảng

### 2.1. Backup retention

Retention là khoảng thời gian hoặc số bản backup mà hệ thống cần duy trì để phục hồi theo yêu cầu.

RMAN hỗ trợ hai cách cấu hình chính:

- REDUNDANCY: giữ một số lượng backup tối thiểu.
- RECOVERY WINDOW: giữ khả năng phục hồi tới bất kỳ thời điểm nào trong một khoảng ngày gần đây.

Hai cách biểu đạt mục tiêu khác nhau. Chọn một chính sách phù hợp với yêu cầu vận hành, không nên chọn chỉ vì cú pháp dễ nhớ.

### 2.2. Archived redo log

Archived redo log chứa các thay đổi redo đã được archive từ online redo log. Các log này cần cho media recovery và point-in-time recovery sau thời điểm backup.

Một backup datafile cũ có thể cần một chuỗi archived redo log liên tục để recover tới thời điểm mong muốn. Có full backup mà thiếu log cần thiết vẫn có thể không đạt recovery point yêu cầu.

### 2.3. Recovery window

Recovery window là khoảng thời gian mà DBA muốn có thể phục hồi database về bất kỳ thời điểm nào trong khoảng đó, tính lùi từ thời điểm hiện tại.

Ví dụ RECOVERY WINDOW OF 7 DAYS có nghĩa mục tiêu là có thể recover tới một thời điểm bất kỳ trong 7 ngày gần nhất, với điều kiện backup, archived logs, control file, encryption keys và các dependency cần thiết còn sẵn sàng.

Recovery window không có nghĩa “chỉ giữ file backup tạo trong 7 ngày”. Có thể cần giữ một backup cũ hơn mốc 7 ngày làm cơ sở, cùng các archived log cần thiết từ backup đó tới thời điểm recover.

### 2.4. Redundancy

Redundancy là số lượng backup cần giữ theo từng datafile/control file để đáp ứng chính sách. Ví dụ REDUNDANCY 2 yêu cầu duy trì hai bản backup phù hợp theo cách RMAN đánh giá dependency và repository metadata.

Redundancy không đại diện cho số ngày. Nếu backup chạy mỗi đêm, redundancy 2 có thể chỉ bảo vệ được một khoảng ngắn; nếu backup chạy mỗi tuần, cùng giá trị 2 có thể tương ứng khoảng thời gian dài hơn.

### 2.5. Obsolete và expired

Đây là hai trạng thái khác nhau:

- **OBSOLETE:** file backup không còn cần thiết để đáp ứng retention policy hiện hành.
- **EXPIRED:** RMAN đã kiểm tra repository nhưng không tìm thấy file ở vị trí mà repository ghi nhận, hoặc file không thể được xác nhận tồn tại theo cơ chế crosscheck.

Obsolete nói về việc file còn cần cho recovery hay không. Expired nói về việc file có hiện diện/được xác nhận ở storage hay không.

Một backup có thể AVAILABLE nhưng OBSOLETE. Một backup có thể EXPIRED vì storage tạm thời không truy cập được; không nên xóa record ngay trước khi xác minh storage.

## 3. Cấu hình retention policy bằng RMAN

Xem cấu hình hiện tại:

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ALL;
~~~

RMAN thường mặc định retention policy là REDUNDANCY 1 nếu chưa được cấu hình khác. Không dựa vào mặc định: luôn kiểm tra cấu hình thực tế của database và môi trường backup.

### 3.1. Cấu hình theo redundancy

Ví dụ giữ redundancy 2:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

Cấu hình này yêu cầu RMAN giữ đủ số bản backup theo quy tắc redundancy. Backup vượt quá số lượng cần thiết có thể trở thành OBSOLETE nếu không còn cần cho dependency/recovery khác.

Dùng redundancy khi mục tiêu được định nghĩa bằng số bản backup, ví dụ cần giữ hai bản backup phù hợp độc lập theo chính sách.

Cần nhớ:

- Số bản backup không tự nói lên số ngày có thể phục hồi.
- Lịch backup không đều làm thời gian bảo vệ thay đổi.
- Incremental backup có dependency vào level 0 hoặc backup chain.
- Archived logs cần thiết để recover backup vẫn phải được giữ.
- Một bản backup không thể đọc hoặc thiếu encryption key không tạo ra khả năng phục hồi thực tế.

### 3.2. Cấu hình theo recovery window

Ví dụ giữ recovery window 7 ngày:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
~~~

RMAN đánh giá backup dựa trên việc có thể phục hồi tới mọi thời điểm trong cửa sổ yêu cầu. Những backup cũ hơn vẫn có thể cần thiết làm base backup để phục hồi tới đầu cửa sổ.

Dùng recovery window khi yêu cầu nghiệp vụ được mô tả theo thời gian, chẳng hạn:

- Có thể khôi phục database về bất kỳ thời điểm nào trong 7 ngày gần nhất.
- Có thể điều tra dữ liệu sai trong 14 ngày.
- Có thể phục hồi giao dịch bị xóa nhầm trong 30 ngày.

Recovery window cần archived redo log coverage liên tục từ backup phù hợp tới điểm phục hồi. Nếu có gap, thiếu log hoặc backup hỏng, cấu hình policy đúng vẫn không đảm bảo phục hồi.

### 3.3. So sánh hai lựa chọn

| Tiêu chí | REDUNDANCY n | RECOVERY WINDOW OF n DAYS |
|---|---|---|
| Mục tiêu | Số bản backup | Khoảng thời gian phục hồi |
| Phụ thuộc lịch backup | Có, ảnh hưởng số ngày bảo vệ thực tế | Có, cần backup/log đủ để phủ thời gian |
| Dễ diễn giải cho nghiệp vụ | Ít trực quan hơn | Trực tiếp theo ngày |
| Backup cũ làm base | RMAN xét dependency | Có thể cần giữ backup trước đầu cửa sổ |
| Phù hợp | Chính sách số bản | Chính sách RPO/PITR theo thời gian |
| Đảm bảo restore thành công | Không tự đảm bảo | Không tự đảm bảo |

Không có giá trị n nào luôn tương đương với một recovery window cố định. Ví dụ REDUNDANCY 2 không đồng nghĩa RECOVERY WINDOW OF 2 DAYS.

### 3.4. NONE và thay đổi policy

RMAN hỗ trợ cấu hình retention policy về NONE trong trường hợp cần tắt việc đánh dấu backup obsolete theo retention policy:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO NONE;
~~~

Đây không phải lựa chọn mặc định an toàn cho vận hành thông thường. Khi retention policy là NONE, RMAN không đánh dấu backup obsolete theo chính sách retention đó. Điều này có thể làm backup tăng không giới hạn nếu không có quy trình dọn dẹp khác.

Nếu thay đổi policy, ghi lại:

- Giá trị cũ và mới.
- Người phê duyệt.
- Thời điểm hiệu lực.
- Ảnh hưởng tới FRA và backup storage.
- Kế hoạch quay lại.
- Cách xác nhận backup vẫn đáp ứng RPO/RTO.

## 4. Recovery window trong thực tế

Giả sử hôm nay là ngày 14 và yêu cầu recovery window là 7 ngày. Mục tiêu là có thể phục hồi về một thời điểm trong khoảng từ ngày 7 đến hiện tại.

Nếu full backup gần nhất được tạo ngày 10, để phục hồi về ngày 8 thì backup ngày 10 không thể dùng vì nó mới hơn điểm cần phục hồi. RMAN cần một backup phù hợp trước điểm ngày 8 và archived logs từ backup đó tới ngày 8.

Vì vậy, policy có thể giữ một backup cũ hơn đầu cửa sổ. Điều này là cần thiết để thực hiện recovery window, không phải backup dư thừa.

### 4.1. Backup chain và incremental

Ví dụ lịch:

- Chủ nhật: incremental level 0.
- Thứ Hai đến thứ Bảy: incremental level 1.
- Archived redo log backup chạy liên tục.

Để recover tới một SCN, cần base backup thích hợp, incremental backup cần thiết và archived redo log liên tục đến SCN đó.

Không xóa thủ công một level 0 chỉ vì nó cũ hơn 7 ngày nếu level 1 hoặc recovery window vẫn phụ thuộc vào nó.

### 4.2. Archived redo log coverage

Recovery window yêu cầu log coverage liên tục. Kiểm tra:

- Archive log được tạo đầy đủ trên mọi thread.
- Backup job đã backup log.
- Log không bị xóa trước khi standby apply nếu cần.
- Log còn truy cập được trên storage.
- RMAN repository còn metadata đúng.
- Có bản sao log/backup ở vị trí phục hồi được.

Trong RAC, mỗi redo thread có sequence riêng. Không chỉ kiểm tra thread 1.

### 4.3. Recovery window không phải retention của mọi loại dữ liệu

Retention policy của RMAN quản lý backup theo quy tắc RMAN. Nó không thay thế:

- Retention của application audit.
- Retention của archive log theo chính sách pháp lý riêng.
- Retention của export/Data Pump.
- Retention của snapshot storage.
- Retention của Flashback Data Archive.
- Retention của guaranteed restore point/flashback logs.
- Retention của bản sao offsite hoặc immutable backup.

Các lớp lưu trữ này có thể có chính sách và owner riêng.

## 5. Archived log deletion policy

Archived log deletion policy quy định điều kiện mà archived redo log phải đáp ứng trước khi RMAN cho phép xóa.

Xem policy:

~~~text
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

Hoặc xem toàn bộ cấu hình:

~~~text
RMAN> SHOW ALL;
~~~

### 5.1. Xóa sau khi backup đủ số lần

Ví dụ yêu cầu mỗi archived log được backup ít nhất một lần lên DISK:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
~~~

Nếu dùng SBT/tape:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE SBT;
~~~

Điều kiện này kiểm soát số lần backup lên device type tương ứng. Nó không tự chứng minh bản backup đã được sao chép offsite, immutable hoặc restore test thành công.

Nếu backup job lưu một bản trên cùng storage với archive log, mất storage đó có thể làm mất cả hai. Hãy phân biệt số bản RMAN với số bản độc lập theo failure domain.

### 5.2. Chỉ xóa sau khi standby apply redo

Trong Data Guard, primary có thể yêu cầu archived log được apply tới standby trước khi đủ điều kiện xóa:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO APPLIED ON ALL STANDBY;
~~~

Điều kiện APPLIED ON STANDBY giúp tránh xóa log trước khi standby áp dụng. Tùy cấu hình và số standby, dùng ALL có nghĩa phải thỏa điều kiện với tất cả standby thuộc phạm vi policy.

Nếu một standby ngừng hoạt động hoặc apply lag kéo dài, archived logs có thể không được xóa và FRA có thể tăng. Đây là dấu hiệu cần xử lý Data Guard, không phải lý do tự động bỏ deletion policy.

### 5.3. Chỉ xóa sau khi ship tới standby

Có thể cấu hình điều kiện log đã được chuyển tới standby:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO SHIPPED TO ALL STANDBY;
~~~

SHIPPED và APPLIED là hai trạng thái khác nhau:

- Shipped: redo đã được chuyển tới standby.
- Applied: redo đã được áp dụng vào datafile tại standby.

Nếu yêu cầu bảo vệ cần standby đã apply, chỉ ship chưa đủ. Chọn điều kiện theo RPO, transport/apply mode và thiết kế HA.

### 5.4. Kết hợp điều kiện

Một policy có thể cần nhiều điều kiện, ví dụ log đã được apply trên standby và đã được backup lên device type cần thiết. Cú pháp kết hợp chính xác phụ thuộc Oracle release và RMAN configuration grammar; kiểm tra SQL/RMAN Reference của phiên bản đang chạy trước khi triển khai.

Không thay policy production bằng một câu lệnh kết hợp chưa được thử trong lab. Sau cấu hình, chạy SHOW ARCHIVELOG DELETION POLICY và kiểm tra behavior với backup/delete test.

### 5.5. Deletion policy không phải backup retention policy

Ví dụ:

- Backup retention: RECOVERY WINDOW OF 14 DAYS.
- Archive deletion: BACKED UP 1 TIMES TO DEVICE TYPE DISK.
- Data Guard: yêu cầu APPLIED ON ALL STANDBY.

Ba điều kiện giải quyết ba câu hỏi khác nhau: cần giữ backup nào, log đã có bản backup chưa, và standby đã apply chưa.

## 6. OBSOLETE: backup không còn cần theo retention policy

RMAN đánh dấu backup là OBSOLETE khi backup đó không còn cần thiết để đáp ứng retention policy hiện tại, xét các dependency và repository metadata.

Liệt kê backup obsolete:

~~~text
RMAN> REPORT OBSOLETE;
~~~

Lệnh này chỉ báo cáo. Nó không xóa file.

Có thể xem danh sách backup:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

Đối chiếu với lịch backup, recovery window, redundancy và nhu cầu restore thực tế.

### 6.1. Xóa backup obsolete

Sau khi review report và được phép dọn dẹp:

~~~text
RMAN> DELETE OBSOLETE;
~~~

RMAN sẽ hỏi xác nhận theo chế độ tương tác thông thường. Lệnh xóa backup được đánh giá obsolete theo retention policy và cập nhật repository.

Trong automation, không bỏ prompt hoặc dùng NOPROMPT trước khi đã có:

- Policy được phê duyệt.
- Báo cáo obsolete đã lưu.
- Kiểm tra backup còn lại.
- Xác nhận recovery window vẫn đáp ứng.
- Kiểm tra standby và archive log deletion policy.
- Cơ chế audit/log command output.

### 6.2. OBSOLETE không có nghĩa file hỏng

Một backup obsolete có thể vẫn đọc tốt. Nó chỉ không còn cần theo retention policy hiện hành.

Một backup AVAILABLE có thể OBSOLETE. Một backup EXPIRED có thể vẫn được coi là cần thiết theo repository nhưng file không tìm thấy. Hai trạng thái không được dùng thay cho nhau.

### 6.3. Thay đổi retention làm thay đổi danh sách obsolete

Nếu chuyển từ recovery window 30 ngày sang 7 ngày, nhiều backup có thể trở thành obsolete. Ngược lại, mở rộng từ 7 lên 30 ngày không thể khôi phục các backup/log đã xóa trước đó.

Trước khi rút ngắn retention, đánh giá nghĩa vụ pháp lý, business recovery requirement, offsite copy và các bản backup còn lại. Policy mới có thể làm thay đổi kết quả REPORT OBSOLETE ngay lập tức.

## 7. EXPIRED: repository không tìm thấy file

CROSSCHECK kiểm tra repository metadata so với storage.

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

Kết quả có thể cập nhật trạng thái backup từ AVAILABLE sang EXPIRED nếu file không được tìm thấy. Nếu file hiện diện lại, crosscheck có thể đánh dấu lại AVAILABLE.

### 7.1. Vì sao file có thể EXPIRED?

- Backup mount hoặc NFS share đang unavailable.
- Object storage/network lỗi.
- Tape library chưa mount media.
- File bị di chuyển hoặc xóa ngoài RMAN.
- Sai path, credential hoặc storage configuration.
- Backup piece thực sự đã bị xóa.
- Control file/catalog metadata không còn khớp storage.

EXPIRED không tự nói nguyên nhân. Trước khi dọn record, xác minh storage và vị trí backup.

### 7.2. DELETE EXPIRED

Sau khi xác nhận file thực sự không còn và đã đánh giá recovery impact:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

DELETE EXPIRED xóa repository records cho file RMAN đã đánh dấu expired. Nó không xóa file vật lý đang tồn tại ở một vị trí khác.

Không dùng DELETE EXPIRED như cách dọn file backup tồn tại nhưng RMAN chưa nhìn thấy do storage tạm thời offline. Nếu xóa record, cần resync/catalog lại hoặc catalog file phù hợp sau khi storage trở lại.

### 7.3. Khác biệt tóm tắt

| Trạng thái/command | Ý nghĩa | Tác động |
|---|---|---|
| AVAILABLE | RMAN tin file có sẵn theo repository | Có thể dùng trong restore nếu file thực sự đọc được |
| EXPIRED | CROSSCHECK không tìm thấy file | Repository đánh dấu file không sẵn sàng |
| OBSOLETE | Không còn cần theo retention policy | Có thể xóa bằng DELETE OBSOLETE |
| CROSSCHECK | Đối chiếu repository với storage | Cập nhật trạng thái; không phải lệnh dọn file |
| DELETE EXPIRED | Xóa record expired | Không xóa file vật lý |
| DELETE OBSOLETE | Xóa backup obsolete | Xóa file backup và cập nhật repository |

## 8. Quy trình dọn dẹp an toàn

Một quy trình vận hành nên tách quan sát, quyết định và xóa.

### Bước 1 — Xác nhận đúng database

Kiểm tra DBID, DB_NAME, DB_UNIQUE_NAME, role, instance và môi trường. Tránh chạy RMAN trên nhầm database hoặc nhầm catalog.

Trong SQL:

~~~sql
SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode
FROM v$database;
~~~

### Bước 2 — Xem cấu hình

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> SHOW ALL;
~~~

Ghi lại policy và device type. Kiểm tra cấu hình riêng của môi trường Data Guard nếu có.

### Bước 3 — Kiểm tra backup inventory

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
RMAN> REPORT NEED BACKUP;
~~~

Xác định backup gần nhất, level 0/incremental chain, archived log coverage, control file/SPFILE backup và vị trí lưu.

### Bước 4 — Crosscheck khi cần

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK tạo trạng thái repository cập nhật hơn. Nếu storage đang unavailable, dừng ở đây và xử lý kết nối trước khi DELETE EXPIRED.

### Bước 5 — Report obsolete

~~~text
RMAN> REPORT OBSOLETE;
~~~

Đọc danh sách và xác nhận backup còn lại đủ đáp ứng retention, recovery window và yêu cầu restore. Nếu kết quả bất thường sau khi đổi policy, không tiếp tục xóa cho đến khi hiểu lý do.

### Bước 6 — Kiểm tra deletion policy cho archived logs

~~~text
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> LIST ARCHIVELOG ALL;
~~~

Với Data Guard, xác nhận transport/apply lag, gap và standby status. Với policy backup count, xác nhận log đã được backup đúng device type.

### Bước 7 — Thực hiện xóa có kiểm soát

Chỉ sau review và approval:

~~~text
RMAN> DELETE OBSOLETE;
~~~

Nếu có expired records thực sự không còn file và đã đánh giá impact:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

Không trộn xóa obsolete và expired thành một bước không có report.

### Bước 8 — Xác minh sau dọn dẹp

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

Kiểm tra FRA/storage, archived log backlog, Data Guard lag và kết quả backup job kế tiếp. Lưu RMAN log và người phê duyệt.

## 9. FRA và tự động reclaimable space

Fast Recovery Area (FRA) là vùng Oracle quản lý cho các file recovery như backup pieces, archived redo logs, flashback logs và control file autobackup tùy cấu hình.

Xem FRA:

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

Xem usage theo file type:

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$recovery_area_usage
ORDER BY file_type;
~~~

SPACE_RECLAIMABLE là dung lượng Oracle đánh giá có thể reclaim theo quy tắc quản lý FRA; không đồng nghĩa mọi file đều có thể xóa ngay.

### 9.1. FRA reclaim và retention

Khi FRA cần thêm chỗ, Oracle có thể reclaim các file đủ điều kiện theo quy tắc quản lý recovery area. Retention policy và archived log deletion policy ảnh hưởng file nào đủ điều kiện.

Nếu không có file nào có thể reclaim, database có thể báo lỗi do FRA đầy. Tăng SPACE_LIMIT chỉ có ích nếu filesystem/ASM/cloud storage thực sự còn capacity.

### 9.2. Flashback logs và guaranteed restore point

Guaranteed restore point có thể giữ flashback logs cần thiết để quay lại điểm đó. Những log này có thể không được reclaim như log thông thường, khiến FRA tăng nhanh.

Kiểm tra restore points:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
~~~

Không drop guaranteed restore point chỉ để giải phóng FRA khi chưa xác nhận owner, thời hạn và mục tiêu recovery. Đây là quyết định có thể loại bỏ khả năng flashback về mốc đã cam kết.

### 9.3. Xử lý FRA gần đầy

1. Xác định file type chiếm dung lượng.
2. Kiểm tra backup retention và obsolete report.
3. Kiểm tra archive deletion policy và Data Guard apply.
4. Kiểm tra guaranteed restore point/flashback logs.
5. Xác minh storage headroom.
6. Chọn giải pháp: xử lý standby lag, backup log, dọn obsolete qua RMAN, mở rộng storage hoặc điều chỉnh policy theo phê duyệt.
7. Xác minh FRA có headroom và recovery protection còn đúng.

Không xóa trực tiếp file trong FRA bằng OS command.

## 10. Backup optimization không phải retention policy

RMAN có cấu hình BACKUP OPTIMIZATION:

~~~text
RMAN> CONFIGURE BACKUP OPTIMIZATION ON;
~~~

Backup optimization cho phép RMAN bỏ qua một số file đã có bản backup phù hợp trên device type theo quy tắc tối ưu hóa. Nó có thể giảm thời gian và dung lượng backup lặp lại.

Tuy nhiên:

- Nó không quyết định backup nào obsolete.
- Nó không thay thế retention policy.
- Nó không thay thế archived log deletion policy.
- Nó không chứng minh bản backup hiện có còn đọc được.
- Nó không tạo bản copy độc lập ở failure domain khác.

Nếu bật optimization, hiểu điều kiện RMAN dùng để xem file đã được backup phù hợp. Khi backup strategy thay đổi, kiểm tra lại device type, retention và availability.

## 11. Data Guard: phối hợp retention và deletion

Trong Data Guard, primary có thể tạo archived redo log nhanh hơn standby nhận hoặc apply. Nếu deletion policy yêu cầu APPLIED ON ALL STANDBY, log chưa apply sẽ không đủ điều kiện xóa theo policy.

### 11.1. Theo dõi transport/apply lag

Trên standby hoặc database có quyền xem:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Xem archive destination:

~~~sql
SELECT dest_id,
       status,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Và archive gap:

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

### 11.2. Điều gì xảy ra khi standby ngừng apply?

Nếu standby bị ngắt kết nối hoặc apply lag kéo dài:

- Archived logs trên primary có thể không được xóa.
- FRA có thể tăng nhanh.
- Primary có thể gặp áp lực storage.
- RPO/HA protection có thể bị suy giảm.
- Xóa log bằng FORCE có thể làm mất khả năng catch-up của standby.

Không bỏ APPLIED requirement chỉ để làm FRA giảm. Trước tiên khôi phục transport/apply hoặc đánh giá standby theo DR policy.

### 11.3. Nhiều standby

Nếu dùng ALL STANDBY, một standby chậm có thể giữ log lại dù các standby khác đã apply. Đây có thể là behavior mong muốn để đảm bảo tất cả standby cần thiết có thể phục hồi.

Nếu có standby không còn dùng, cần decommission đúng quy trình Data Guard và cập nhật policy/topology. Không xóa cấu hình hoặc bỏ standby khỏi điều kiện chỉ để vượt qua backlog mà không đánh giá DR.

## 12. Cấu hình backup strategy mẫu

Ví dụ một hệ thống muốn:

- Có thể PITR 14 ngày.
- Full/incremental backup hằng ngày theo lịch.
- Archived log được backup lên DISK ít nhất một lần trước khi xóa.
- Có standby và chỉ xóa log khi standby đã apply.
- Control file autobackup luôn bật.

Một cấu hình khởi điểm cần được review:

~~~text
RMAN> CONFIGURE RETENTION POLICY
      TO RECOVERY WINDOW OF 14 DAYS;

RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO APPLIED ON ALL STANDBY;

RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Nếu cần thêm điều kiện backup count cho archived log, cấu hình kết hợp theo cú pháp của Oracle release cụ thể và test trong lab.

Cấu hình trên không thay thế lịch backup. Cần có job thực sự chạy database backup, archived log backup, controlfile/SPFILE autobackup và offsite copy.

### 12.1. Backup database và archived logs

Một ví dụ command backup:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Lệnh này minh họa backup database cùng archived redo logs; lịch production cần cân nhắc incremental level, channel, compression, encryption, parallelism, storage và workload.

### 12.2. Backup archived logs và DELETE INPUT

Ví dụ:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

DELETE INPUT yêu cầu RMAN xóa input archived log đã được backup theo điều kiện phù hợp. Archived log deletion policy được áp dụng cho các thao tác xóa liên quan, trừ các trường hợp force override.

Không dùng DELETE INPUT nếu chưa hiểu:

- Backup destination.
- Device type và số bản backup.
- Data Guard apply/ship requirements.
- Archive log còn cần cho recovery window.
- Storage failure domain và offsite copy.

DELETE INPUT không phải lệnh “backup xong thì xóa bất kể điều kiện”.

### 12.3. Control file và SPFILE

Control file lưu metadata backup và cấu trúc database. Bật autobackup:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Kiểm tra output backup có control file/SPFILE autobackup và biết cách restore khi control file mất. Nếu dùng recovery catalog, vẫn cần bảo vệ catalog database riêng.

### 12.4. Encryption và key management

Backup mã hóa chỉ có thể restore khi có key/wallet/keystore phù hợp. Runbook cần xác định:

- TDE keystore/wallet location.
- Backup keystore theo chính sách.
- Password/secret escrow.
- Quy trình mở keystore trong disaster recovery.
- Người có quyền truy cập.
- Cách kiểm tra key availability trong môi trường restore.

Không lưu password hoặc key material trực tiếp trong runbook không bảo vệ.

## 13. Retention policy và recovery catalog

RMAN có thể lưu repository metadata trong control file hoặc recovery catalog. Recovery catalog giúp quản lý lịch sử backup lâu hơn và nhiều database hơn tùy thiết kế.

Cần lưu ý:

- Control file có giới hạn lưu metadata theo cấu hình và thời gian.
- Record cũ có thể được reuse theo cơ chế control file record keep time.
- Recovery catalog phải được backup và bảo vệ.
- Catalog resync cần được vận hành theo lịch.
- Một bản backup trên storage nhưng không còn record có thể cần catalog lại.
- Một record AVAILABLE không đảm bảo storage/file đọc được; validate là cần thiết.

Retention policy được đánh giá dựa trên repository metadata và dependency. Repository không chính xác có thể làm report và quyết định dọn dẹp sai.

### 13.1. SHOW và REPORT là bước quan sát

Trước khi thay policy hoặc xóa:

~~~text
RMAN> SHOW ALL;
RMAN> REPORT OBSOLETE;
RMAN> REPORT NEED BACKUP;
RMAN> LIST BACKUP SUMMARY;
~~~

Lưu output trước khi thực hiện thay đổi để có bằng chứng và khả năng điều tra.

## 14. Recovery window, redundancy và RPO/RTO

Retention policy phải bắt nguồn từ yêu cầu nghiệp vụ.

| Yêu cầu | Ý nghĩa với backup |
|---|---|
| RPO 15 phút | Archived redo log phải được bảo vệ đủ thường xuyên để giới hạn mất dữ liệu |
| PITR 7 ngày | Backup base và archived logs cần phủ mọi thời điểm trong cửa sổ 7 ngày |
| Giữ 2 bản backup | Có thể dùng REDUNDANCY 2, nhưng phải xác định failure domain |
| RTO 1 giờ | Restore/recover phải được thử và đo để hoàn thành trong 1 giờ |
| DR standby | Transport/apply và deletion policy phải giữ log cần cho standby |
| Immutable/offsite | Cần storage policy và copy độc lập ngoài RMAN retention đơn thuần |

Retention policy không đảm bảo RTO. Một bản backup có thể đủ tuổi nhưng restore mất 12 giờ do dung lượng lớn hoặc network chậm.

Recovery window cũng không phải RPO. Recovery window mô tả khoảng thời gian có thể chọn điểm phục hồi; RPO mô tả lượng dữ liệu tối đa được phép mất trong sự cố.

### 14.1. Số bản backup và failure domain

Hai backup copy cùng một disk array không tương đương hai bản độc lập nếu array bị hỏng. Cân nhắc:

- Primary backup storage.
- Secondary/offsite copy.
- Object lock/immutability.
- Tape hoặc cloud archive.
- Credential và account tách biệt.
- Kiểm thử restore từ bản offsite.

RMAN redundancy count không tự mô tả toàn bộ failure-domain architecture.

### 14.2. Đặt retention theo thời hạn thực tế

Ví dụ:

- PITR online: 14 ngày.
- Weekly long-term backup: 8 tuần.
- Monthly archive: 12 tháng.
- Immutable copy: theo compliance retention.
- Audit/application logs: theo policy riêng.

Không nhất thiết mọi lớp đều do cùng RMAN retention policy điều khiển. Tách backup operational, long-term archive và compliance copy để tránh xóa nhầm.

## 15. Thay đổi retention policy: change procedure

Rút ngắn retention có thể làm nhiều backup thành obsolete. Tăng retention không thể phục hồi các file đã xóa trước đó.

Trước thay đổi:

1. Xác nhận database/DBID/DB_UNIQUE_NAME và RMAN target.
2. Lưu SHOW ALL và SHOW RETENTION POLICY.
3. Lưu LIST BACKUP SUMMARY và REPORT OBSOLETE.
4. Kiểm tra RPO/RTO và compliance retention.
5. Xác nhận offsite/immutable copies.
6. Kiểm tra Data Guard topology và deletion policy.
7. Tính storage headroom và growth.
8. Phê duyệt change và rollback plan.

Thực hiện cấu hình mới:

~~~text
RMAN> CONFIGURE RETENTION POLICY
      TO RECOVERY WINDOW OF 14 DAYS;
~~~

Sau đó kiểm tra:

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> REPORT OBSOLETE;
~~~

Không xóa ngay nếu danh sách obsolete tăng bất thường. So sánh với policy cũ, backup chain và recovery scenarios.

### 15.1. Rollback policy

Nếu policy mới không phù hợp, cấu hình lại giá trị cũ:

~~~text
RMAN> CONFIGURE RETENTION POLICY
      TO REDUNDANCY 2;
~~~

Rollback cấu hình không khôi phục file đã xóa. Vì vậy, thay đổi retention và lệnh DELETE phải được tách thành hai change/checkpoint riêng.

## 16. Runbook: FRA tăng nhanh hoặc không reclaim được

**Trigger:** FRA vượt warning threshold, SPACE_RECLAIMABLE thấp, ORA-19809/ORA-19804 hoặc archive destination lỗi.

### Bước 1 — Xác nhận trạng thái

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
FROM v$recovery_area_usage;
~~~

### Bước 2 — Kiểm tra policy và backup inventory

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> REPORT OBSOLETE;
RMAN> LIST BACKUP SUMMARY;
~~~

### Bước 3 — Kiểm tra nguyên nhân tăng

- Backup job tạo nhiều bản hơn dự kiến.
- Archived logs không được backup.
- Standby chưa apply hoặc transport bị lỗi.
- Guaranteed restore point giữ flashback logs.
- Backup piece không thể reclaim do retention.
- FRA limit nhỏ hơn tốc độ phát sinh.
- Storage underlying không còn headroom.

### Bước 4 — Hành động an toàn

Chọn một trong các hướng sau theo nguyên nhân:

- Khôi phục archive transport/apply.
- Chạy backup archived logs theo policy.
- Xóa backup obsolete sau khi review.
- Điều chỉnh storage/FRA limit nếu storage còn khả năng cấp.
- Review guaranteed restore point với owner.
- Điều chỉnh lịch backup hoặc retention qua change approval.

Không xóa file bằng OS command và không dùng DELETE FORCE để vượt policy chỉ nhằm giảm dung lượng.

### Bước 5 — Xác minh

- FRA usage và growth rate giảm.
- Không còn archive destination error.
- Backup và archived log coverage vẫn đủ.
- Data Guard lag trong giới hạn.
- Restore window/RPO/RTO không bị phá vỡ.
- Alert được đóng với evidence.

## 17. Runbook: backup bị EXPIRED

**Trigger:** CROSSCHECK đánh dấu backup EXPIRED hoặc RMAN báo file không tìm thấy.

1. Xác nhận đúng database, DBID, DB_UNIQUE_NAME và catalog.
2. Kiểm tra mount point, NFS/object storage/tape và credential.
3. Xác minh file có tồn tại ở vị trí dự kiến hay không.
4. Nếu storage tạm thời unavailable, khôi phục kết nối rồi CROSSCHECK lại.
5. Nếu file thực sự mất, xác định backup chain/recovery point bị ảnh hưởng.
6. Xác định còn bản copy khác hoặc offsite copy không.
7. Chạy backup thay thế nếu cần và đánh giá RPO/RTO.
8. Chỉ DELETE EXPIRED sau khi xác nhận record thực sự không còn giá trị.
9. Lưu RMAN output và incident record.

Không dùng DELETE EXPIRED để che lỗi mount hoặc permission.

## 18. Runbook: kiểm tra recovery window trước restore

Khi có yêu cầu phục hồi:

1. Xác định target time/SCN và business owner.
2. Xác nhận database incarnation và DBID.
3. Xác định backup base phù hợp trước target.
4. Xác định incremental chain.
5. Xác nhận archived logs liên tục tới target.
6. Xác nhận control file/SPFILE và encryption keys.
7. Xác nhận destination/host đủ dung lượng.
8. Dùng RESTORE ... PREVIEW để xem file RMAN dự kiến dùng nếu phù hợp.
9. Dùng RESTORE ... VALIDATE hoặc VALIDATE BACKUPSET trong môi trường phù hợp.
10. Thực hiện restore/recover theo runbook đã phê duyệt.
11. Kiểm tra database, schema và business data sau recovery.
12. Ghi actual RTO/RPO và khoảng dữ liệu bị mất nếu có.

Ví dụ RMAN kiểm tra đường restore:

~~~text
RMAN> RESTORE DATABASE PREVIEW;
RMAN> RESTORE DATABASE VALIDATE;
~~~

PREVIEW hiển thị những backup RMAN dự kiến dùng; VALIDATE kiểm tra khả năng đọc backup cần cho restore. Chúng không thay thế một lần restore hoàn chỉnh.

## 19. Các lỗi và hiểu nhầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ RECOVERY WINDOW 7 DAYS chỉ giữ file tạo trong 7 ngày | Xóa nhầm base backup cũ còn cần | Hiểu recovery window theo khả năng PITR |
| Nghĩ REDUNDANCY 2 tương đương 2 ngày | Khoảng bảo vệ không như mong đợi | Đối chiếu lịch backup và archived logs |
| Dùng retention policy thay deletion policy | Archive log bị giữ/xóa sai điều kiện | Cấu hình hai policy riêng |
| Nghĩ OBSOLETE là file hỏng | Xóa nhầm hoặc điều tra sai | OBSOLETE là không còn cần theo retention |
| Nghĩ EXPIRED là backup obsolete | Xóa repository record khi storage tạm offline | Kiểm tra storage và crosscheck lại |
| Chạy DELETE OBSOLETE mà không review | Xóa backup cần cho mục tiêu khác | REPORT OBSOLETE và approval |
| Chạy DELETE EXPIRED khi mount offline | Mất metadata của file vẫn còn | Khôi phục storage trước |
| Chỉ backup log một lần trên cùng storage | Mất cả log và bản backup khi storage hỏng | Copy độc lập/offsite |
| Xóa log trước khi standby apply | Standby không catch up được | APPLIED deletion policy |
| Bỏ deletion policy để xử lý FRA đầy | Có thể phá RPO/DR | Khắc phục transport/apply hoặc storage |
| Nghĩ BACKUP OPTIMIZATION là retention | Bỏ sót backup cần thiết | Tách optimization khỏi retention |
| Tăng FRA mà storage không đủ | Vẫn lỗi allocation | Kiểm tra ASM/filesystem/cloud capacity |
| Xóa archive bằng OS | RMAN repository và recovery bị lệch | Dùng RMAN |
| Tăng retention sau khi đã xóa file | Không thể phục hồi backup đã mất | Có offsite/immutable copy và restore plan |
| Chỉ kiểm tra backup SUCCESS | Không biết restore có chạy được | Validate và restore test |
| Quên encryption key/control file | Backup không thể restore | Bảo vệ metadata và key material |

## 20. Bài thực hành

Thực hiện trong database lab với backup storage riêng. Không thực hành xóa backup production.

### Bài 1 — Xem retention mặc định

Chạy SHOW RETENTION POLICY và SHOW ALL. Ghi policy hiện tại, device type và archived log deletion policy.

### Bài 2 — Redundancy

Cấu hình REDUNDANCY 2 trong lab, tạo nhiều backup theo lịch, chạy REPORT OBSOLETE. Quan sát backup nào RMAN đánh dấu obsolete và vì sao.

### Bài 3 — Recovery window

Cấu hình RECOVERY WINDOW OF 7 DAYS, tạo backup và archived log qua nhiều ngày giả lập. Chạy REPORT OBSOLETE và xác định base backup cần giữ.

### Bài 4 — So sánh redundancy và recovery window

Giữ cùng lịch backup nhưng thay policy giữa hai lần thử. So sánh danh sách obsolete. Giải thích vì sao số bản backup không tương đương số ngày.

### Bài 5 — Crosscheck

Di chuyển một backup piece trong lab, chạy CROSSCHECK BACKUP và xem trạng thái EXPIRED. Đưa file về vị trí, crosscheck lại và quan sát trạng thái.

### Bài 6 — Delete expired

Chỉ sau khi file test thực sự không còn, chạy DELETE EXPIRED BACKUP. Xác nhận repository record được xóa và giải thích vì sao lệnh này không xóa file vật lý.

### Bài 7 — Delete obsolete

Chạy REPORT OBSOLETE, lưu output, review dependency, rồi DELETE OBSOLETE trong lab. Kiểm tra LIST BACKUP SUMMARY sau đó.

### Bài 8 — Archived log deletion policy

Cấu hình BACKED UP 1 TIMES TO DEVICE TYPE DISK. Backup archive logs và kiểm tra điều kiện DELETE INPUT.

### Bài 9 — Data Guard apply policy

Trong lab Data Guard, cấu hình APPLIED ON STANDBY. Tạm dừng apply theo quy trình lab, tạo archive và quan sát log không đủ điều kiện xóa. Khôi phục apply và xác minh.

### Bài 10 — FRA pressure

Tạo backup/archive log đủ để tăng FRA. Quan sát V$RECOVERY_FILE_DEST và V$RECOVERY_AREA_USAGE. Xác định file type và điều kiện reclaimable.

### Bài 11 — Restore validation

Chạy RESTORE DATABASE PREVIEW và RESTORE DATABASE VALIDATE. Sau đó restore sang môi trường test và đo thời gian thực tế.

### Bài 12 — Recovery point

Chọn một SCN trong recovery window, xác định backup base và archived log coverage. Thử recover trong clone và ghi actual RPO/RTO.

## 21. Checklist trước khi xóa backup hoặc archived log

- [ ] Xác nhận đúng DBID, DB_UNIQUE_NAME, database role và RMAN catalog.
- [ ] Ghi lại retention policy hiện tại.
- [ ] Ghi lại archived log deletion policy.
- [ ] Xác nhận yêu cầu RPO/RTO, PITR và compliance.
- [ ] Kiểm tra LIST BACKUP SUMMARY và backup chain.
- [ ] Kiểm tra archived log coverage cho mọi redo thread.
- [ ] Kiểm tra control file/SPFILE autobackup.
- [ ] Kiểm tra encryption wallet/keystore.
- [ ] Kiểm tra Data Guard transport/apply/gap nếu có.
- [ ] Chạy CROSSCHECK khi cần và xác minh storage sẵn sàng.
- [ ] Phân biệt EXPIRED với OBSOLETE.
- [ ] Chạy REPORT OBSOLETE và lưu kết quả.
- [ ] Review danh sách file sẽ xóa và backup còn lại.
- [ ] Xác nhận offsite/immutable copy nếu yêu cầu.
- [ ] Có change approval và rollback/restore plan.
- [ ] Chạy DELETE OBSOLETE hoặc DELETE EXPIRED đúng mục đích.
- [ ] Kiểm tra LIST BACKUP SUMMARY và REPORT NEED BACKUP sau thao tác.
- [ ] Kiểm tra FRA, archive destination và Data Guard sau dọn dẹp.
- [ ] Lưu RMAN log, người thực hiện và thời điểm.

## 22. Ghi nhớ cốt lõi

- Retention policy quyết định backup nào còn cần để đáp ứng chính sách phục hồi; archived log deletion policy quyết định điều kiện xóa archived redo log.
- REDUNDANCY n giữ số lượng backup theo quy tắc RMAN; RECOVERY WINDOW OF n DAYS giữ khả năng phục hồi về mọi thời điểm trong cửa sổ ngày.
- REDUNDANCY 2 không đồng nghĩa recovery window 2 ngày.
- Recovery window có thể cần giữ base backup cũ hơn đầu cửa sổ và archived logs liên tục tới điểm phục hồi.
- Backup có mặt trên storage chưa đủ; cần control file/catalog metadata, encryption keys và khả năng đọc/restore.
- OBSOLETE nghĩa backup không còn cần theo retention policy; EXPIRED nghĩa crosscheck không tìm thấy file.
- CROSSCHECK cập nhật trạng thái repository; DELETE EXPIRED xóa record expired; DELETE OBSOLETE xóa backup không còn cần.
- Không xóa record expired khi storage chỉ đang tạm offline.
- Deletion policy có thể yêu cầu archive log được backup đủ số lần hoặc được ship/apply tới standby.
- SHIPPED không đồng nghĩa APPLIED; chọn điều kiện theo RPO và Data Guard design.
- Backup optimization không thay thế retention hoặc deletion policy.
- FRA tự reclaim file đủ điều kiện nhưng không thể bảo đảm có space nếu file vẫn cần cho recovery hoặc standby.
- Guaranteed restore point có thể giữ flashback logs và làm FRA tăng.
- Không xóa archived log, backup piece hoặc file FRA bằng OS command.
- Tăng retention sau khi đã xóa file không thể khôi phục file đó; rollback policy không rollback thao tác DELETE.
- REPORT OBSOLETE, SHOW ALL, LIST BACKUP và restore validation phải là một phần của quy trình dọn dẹp.
- Backup SUCCESS không chứng minh RTO/RPO; phải kiểm tra và diễn tập restore thực tế.
- Thiết kế retention theo business recovery window, RPO/RTO, failure domain, compliance và dung lượng.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN retention policy, redundancy, recovery window, obsolete backups, archived log deletion policy and FRA.
- [Oracle Database Backup and Recovery Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — CONFIGURE, REPORT, CROSSCHECK, DELETE, LIST, RESTORE and VALIDATE commands.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$RECOVERY_FILE_DEST, V$RECOVERY_AREA_USAGE, V$ARCHIVED_LOG and Data Guard views.
- [Oracle Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — Redo transport, apply, standby availability and archive log management.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Fast Recovery Area, archived redo logs, control files and database recovery configuration.

RMAN syntax, Data Guard deletion-policy options, multitenant behavior and repository metadata can vary by Oracle release. Verify the exact release reference and test retention changes, crosschecks, deletion and restore validation in a non-production environment before changing production backup policy.

