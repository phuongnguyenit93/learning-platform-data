# Phân biệt backup, restore, recovery và yêu cầu RPO/RTO trong Oracle

## 1. Bốn khái niệm phải phân biệt

Trong vận hành Oracle Database, backup, restore và recovery là các bước liên quan nhưng không đồng nghĩa. RPO và RTO là hai mục tiêu nghiệp vụ dùng để thiết kế và đánh giá khả năng phục hồi.

- **Backup:** tạo bản sao dữ liệu và metadata cần thiết để có thể khôi phục khi xảy ra sự cố.
- **Restore:** chép dữ liệu từ backup về vị trí phục hồi, chẳng hạn khôi phục datafile hoặc control file.
- **Recovery:** áp dụng redo, archived redo log và incremental backup cần thiết để đưa database hoặc một phần database đến trạng thái nhất quán mong muốn.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa mà tổ chức chấp nhận mất, thường biểu diễn bằng khoảng thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ về mức hoạt động đã định.

Ví dụ: một hệ thống có RPO 15 phút và RTO 2 giờ. Nếu sự cố xảy ra lúc 10:00, tổ chức đặt mục tiêu dữ liệu được phục hồi không cũ hơn khoảng 9:45 và dịch vụ hoạt động trở lại trong vòng 2 giờ. Đây là mục tiêu thiết kế; chỉ thử nghiệm phục hồi mới chứng minh được hệ thống có đáp ứng hay không.

Bài học thuộc chương **Sao lưu và phục hồi** trong module **Database Engine Relational Oracle**. Nội dung giải thích cách RMAN tạo backup, restore datafile/control file, recover bằng redo, chọn điểm phục hồi, thiết kế RPO/RTO, chuẩn bị disaster recovery và kiểm thử định kỳ.

## 2. Backup: tạo bản sao có thể dùng để phục hồi

Backup là dữ liệu được lưu ở nơi khác với bản dữ liệu đang hoạt động, nhằm bảo vệ trước lỗi phần cứng, lỗi thao tác, hỏng block, lỗi phần mềm, mất site hoặc tấn công phá hoại.

Một bản backup chỉ có giá trị khi:
- Có đủ thành phần để phục hồi.
- Được lưu trên storage phù hợp và còn truy cập được.
- Có metadata để xác định vị trí và nội dung.
- Có khóa giải mã nếu backup được mã hóa.
- Có archived redo cần thiết cho mục tiêu phục hồi.
- Đã được kiểm tra và thử restore/recovery.

Một lệnh backup thành công không chứng minh rằng database có thể phục hồi đến mọi thời điểm. Phải xét cả datafile, control file, SPFILE, archived redo logs, TDE keystore/wallet, cấu hình Oracle Net và các phụ thuộc bên ngoài.

### 2.1. Những gì cần backup?

| Thành phần | Vai trò khi phục hồi |
|---|---|
| Datafiles | Chứa dữ liệu và cấu trúc database |
| Control file | Ghi cấu trúc database, datafile, checkpoint và metadata backup |
| SPFILE hoặc PFILE | Giữ cấu hình khởi động instance |
| Archived redo logs | Cho phép roll forward sau thời điểm backup |
| Online redo logs | Chứa redo gần nhất; tình trạng có thể quyết định khả năng cứu dữ liệu |
| TDE keystore/wallet | Cung cấp khóa để mở dữ liệu được mã hóa |
| RMAN recovery catalog | Lưu metadata backup dài hạn và thông tin repository nếu sử dụng |
| Password file | Có thể cần cho xác thực quản trị từ xa |
| Oracle Net/configuration | Giúp ứng dụng và công cụ kết nối lại |
| External dependencies | Wallet, credential, file ngoài database, cấu hình ứng dụng và storage |

RMAN tập trung vào backup database files và archived redo. Các cấu phần như application configuration, secret manager, external files và quy trình khởi động dịch vụ cần được bảo vệ trong kế hoạch tổng thể.

### 2.2. Backup vật lý và backup logic

**Backup vật lý** lưu các thành phần vật lý của database, ví dụ datafile, control file và archived redo. Oracle Recovery Manager (RMAN) là công cụ chính để thực hiện backup và recovery vật lý.

**Backup logic** xuất object và dữ liệu ở mức logic, ví dụ Oracle Data Pump `expdp`. Logical export hữu ích cho di chuyển schema, khôi phục object hoặc trao đổi dữ liệu, nhưng không thay thế RMAN trong phục hồi toàn bộ database sau khi mất datafile hoặc control file.

Có thể cần cả hai loại:
- RMAN cho disaster recovery và media recovery.
- Data Pump cho phục hồi object, di chuyển dữ liệu hoặc khôi phục chọn lọc theo nghiệp vụ.

### 2.3. Backup không phải bản sao đang đồng bộ

Backup thường phản ánh dữ liệu tại một thời điểm hoặc trong một khoảng thời gian có cơ chế đảm bảo nhất quán. Nó không nhất thiết chứa thay đổi mới nhất.

Nếu backup cuối cùng được tạo lúc 01:00 và database mất lúc 10:00, muốn phục hồi gần 10:00 phải có redo/archived redo đầy đủ từ backup đến điểm đích. Thiếu log có thể khiến RPO thực tế lớn hơn mục tiêu.

## 3. Restore: đưa bản backup trở lại vị trí phục hồi

Restore là thao tác lấy file từ backup hoặc image copy và đặt lại vào vị trí mà Oracle sẽ sử dụng.

Ví dụ:
- Restore một datafile bị mất.
- Restore toàn bộ database sau khi storage hỏng.
- Restore control file khi control file bị mất.
- Restore SPFILE để khởi động instance.
- Restore một tablespace trong quy trình phục hồi phù hợp.

Restore chỉ đưa file về trạng thái đã được backup. Nếu database có thay đổi sau thời điểm backup, các thay đổi đó chưa tự xuất hiện trong file vừa restore.

### 3.1. Ví dụ lệnh RMAN RESTORE

Trong RMAN, cú pháp khái quát:

```sql
RESTORE DATABASE;
```

Lệnh này yêu cầu RMAN chọn backup phù hợp và restore các datafile của database theo repository, cấu hình và trạng thái hiện tại.

Restore control file:

```sql
RESTORE CONTROLFILE FROM AUTOBACKUP;
```

Restore SPFILE:

```sql
RESTORE SPFILE FROM AUTOBACKUP;
```

Các lệnh này là ví dụ cho môi trường đã cấu hình autobackup và có thể truy cập backup piece. Nếu control file và SPFILE đều mất, có thể phải khởi động instance ở trạng thái phù hợp, chỉ định DBID và cấu hình channel/đường dẫn theo tài liệu Oracle.

### 3.2. Restore không đồng nghĩa database đã mở được

Sau restore, datafile thường ở thời điểm checkpoint của backup. Các file có thể chưa đồng bộ cùng một SCN. Oracle cần recovery để áp dụng redo và đưa các file về trạng thái nhất quán.

Vì vậy, quy trình media recovery thường có dạng:

```sql
RESTORE DATABASE;
RECOVER DATABASE;
```

Chỉ sau khi recovery đạt điều kiện mở database phù hợp mới thực hiện lệnh mở database theo đúng tình huống.

### 3.3. Restore có thể mất nhiều thời gian

Thời gian restore phụ thuộc:
- Dung lượng backup cần đọc.
- Tốc độ backup storage và network.
- Số channel RMAN.
- Loại backup set hay image copy.
- Compression/encryption overhead.
- Khả năng đọc song song.
- Vị trí datafile đích và tốc độ ghi storage.

RTO phải tính thời gian restore thực tế, không chỉ thời gian chạy lệnh recovery.

## 4. Recovery: áp dụng thay đổi để đưa database đến trạng thái nhất quán

Recovery là quá trình dùng redo và các backup cần thiết để đưa database hoặc datafile đến một điểm nhất quán. Oracle có thể áp dụng:
- Archived redo logs.
- Online redo logs còn dùng được.
- Incremental backup.
- Redo được tạo sau incremental backup.

Trong media recovery, RMAN hoặc Oracle phục hồi datafile bằng cách roll forward các thay đổi cần thiết. Khi cần, Oracle cũng thực hiện undo để bảo đảm transaction chưa commit không xuất hiện như dữ liệu đã commit.

### 4.1. Ví dụ RMAN RECOVER

```sql
RESTORE DATABASE;
RECOVER DATABASE;
```

`RESTORE DATABASE` lấy các datafile từ backup. `RECOVER DATABASE` áp dụng incremental backup và redo cần thiết để đồng bộ datafile theo điểm phục hồi được chọn.

### 4.2. Complete recovery

Complete recovery đưa database/datafile đến thời điểm mới nhất có thể theo redo sẵn có, thường là đến thời điểm hiện tại hoặc điểm cuối cùng mà redo đầy đủ.

Ví dụ database mất một datafile nhưng control file và archived redo còn đủ. DBA restore datafile từ backup cũ rồi apply archived redo và online redo để đưa datafile về cùng trạng thái với phần còn lại của database.

### 4.3. Incomplete recovery và point-in-time recovery

Incomplete recovery dừng tại một điểm trước hiện tại, ví dụ:
- Trước khi người dùng xóa nhầm dữ liệu.
- Trước một transaction gây lỗi logic.
- Trước khi triển khai ứng dụng làm hỏng dữ liệu.
- Một SCN, timestamp hoặc log sequence được chọn.

Sau incomplete recovery, database thường cần mở bằng `RESETLOGS` theo quy trình Oracle. Việc này tạo một database incarnation mới. Phải quản lý backup tiếp theo và incarnation history cẩn thận.

### 4.4. Recovery không phải lúc nào cũng cần restore toàn database

Nếu chỉ một datafile hỏng và các file khác còn tốt, có thể restore/recover riêng datafile. Nếu lỗi nằm trong một tablespace, có thể xem xét tablespace point-in-time recovery hoặc quy trình phục hồi phù hợp. Nếu chỉ mất một bảng, có thể dùng RMAN table recovery trên phiên bản hỗ trợ hoặc Data Pump/Flashback theo tình huống.

Chọn phạm vi phục hồi nhỏ nhất đáp ứng yêu cầu, nhưng không được làm mất tính nhất quán của database.

## 5. ARCHIVELOG và NOARCHIVELOG

Chế độ logging ảnh hưởng trực tiếp đến khả năng backup online và phục hồi đến thời điểm gần nhất.

### 5.1. ARCHIVELOG mode

Ở chế độ `ARCHIVELOG`, Oracle lưu các online redo log đã đầy thành archived redo log trước khi tái sử dụng nhóm redo đó. Archived logs cho phép recovery qua nhiều thời điểm sau backup.

Lợi ích:
- Hỗ trợ online backup bằng RMAN theo quy trình Oracle.
- Hỗ trợ media recovery đến điểm có đủ redo.
- Hỗ trợ Data Guard và các kiến trúc bảo vệ dữ liệu khác.
- Có thể đáp ứng RPO nhỏ hơn khoảng cách giữa hai lần backup database.

Đổi lại, phải có dung lượng và quy trình quản lý archived logs. Nếu archive destination đầy, database có thể bị ảnh hưởng nghiêm trọng khi không thể archive redo.

Kiểm tra mode:

```sql
SELECT log_mode
FROM v$database;
```

### 5.2. NOARCHIVELOG mode

Ở `NOARCHIVELOG`, Oracle không giữ archived redo logs cho các online redo log đã đầy. Khả năng phục hồi thường giới hạn ở backup nhất quán offline và những redo còn tồn tại.

Với database quan trọng cần hoạt động liên tục và RPO thấp, NOARCHIVELOG thường không phù hợp. Một backup offline nhất quán có thể phục hồi database đến thời điểm backup, nhưng không thể roll forward qua khoảng thời gian không có archived redo.

### 5.3. Chuyển sang ARCHIVELOG

Thao tác thay đổi archive mode cần dừng và mount database theo quy trình DBA. Ví dụ tổng quát:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
```

Sau khi chuyển mode, xác nhận cấu hình archive destination, dung lượng, monitoring và tạo một backup baseline mới. Không chạy thao tác này trên production nếu chưa có change plan, cửa sổ bảo trì và backup phù hợp.

### 5.4. Backup online và consistency

Trong ARCHIVELOG mode, RMAN có thể backup database khi database đang mở theo cơ chế hot backup. RMAN quản lý tính nhất quán bằng checkpoint và redo cần thiết.

Trong NOARCHIVELOG mode, để có backup database nhất quán thông thường cần shutdown cleanly và backup khi database ở trạng thái mount phù hợp. Chi tiết phụ thuộc kiến trúc và phiên bản; không coi việc copy datafile đang mở bằng hệ điều hành là backup hợp lệ.

## 6. RMAN: công cụ backup và recovery chính của Oracle

Recovery Manager (RMAN) là công cụ Oracle cung cấp để:
- Backup database, tablespace, datafile và archived redo.
- Restore từ backup set hoặc image copy.
- Recover bằng incremental backup và redo.
- Kiểm tra backup và block corruption.
- Quản lý retention và obsolete backup.
- Theo dõi repository metadata.

RMAN có thể dùng control file làm repository hoặc dùng recovery catalog riêng.

### 6.1. Kết nối RMAN

Ví dụ kết nối cục bộ:

```text
rman target /
```

Kết nối target database bằng OS authentication khi môi trường cho phép. Có thể kết nối recovery catalog nếu tổ chức triển khai catalog. Không đưa password thật vào command line hoặc shell history.

### 6.2. Backup database và archived logs

Ví dụ:

```sql
BACKUP DATABASE PLUS ARCHIVELOG;
```

Lệnh này yêu cầu RMAN backup database cùng archived redo logs cần thiết theo quy trình của nó. Cần bảo đảm archive destination còn đủ dung lượng và backup destination hoạt động.

Có thể chỉ định nhãn/tag:

```sql
BACKUP DATABASE TAG 'WEEKLY_DB_BACKUP';
```

Tag giúp nhận diện nhóm backup trong repository; tag không thay thế retention policy hoặc backup catalog.

### 6.3. Backup control file và SPFILE

```sql
BACKUP CURRENT CONTROLFILE;
BACKUP SPFILE;
```

Có thể cấu hình autobackup:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

Control file autobackup rất quan trọng vì control file chứa metadata cấu trúc database và backup. SPFILE cần để khởi động instance với cấu hình đúng. Với database dùng SPFILE, RMAN autobackup có thể bao gồm SPFILE theo cấu hình và quy tắc Oracle.

### 6.4. Backup archived redo logs

```sql
BACKUP ARCHIVELOG ALL;
```

Không xóa archived redo log chỉ vì đã copy file sang nơi khác. Dùng RMAN để quản lý backup, retention và xóa log theo chính sách đã xác nhận. Nếu log chưa được backup hoặc đang cần cho standby/recovery, xóa có thể làm mất khả năng phục hồi.

## 7. Các loại backup RMAN

### 7.1. Backup set

Backup set là định dạng RMAN đóng gói block dữ liệu vào một hoặc nhiều backup piece. Đây là dạng phổ biến khi dùng `BACKUP`.

Ưu điểm:
- Có thể bỏ qua một số block chưa dùng theo cơ chế RMAN.
- Hỗ trợ compression và encryption theo cấu hình/edition.
- Có thể chia thành nhiều backup piece.
- Quản lý thông qua RMAN repository.

### 7.2. Image copy

Image copy là bản sao file tương ứng với datafile/control file theo định dạng có thể dùng trực tiếp làm file database sau khi chuyển/đặt đúng vị trí.

Ưu điểm:
- Có thể switch database sang image copy trong một số quy trình.
- Hữu ích cho chiến lược incremental merge.
- Không cần giải nén backup set như một số trường hợp restore.

Image copy thường chiếm dung lượng gần với file được copy. Hãy cân nhắc storage và thời gian tạo.

### 7.3. Full backup và level 0

Trong RMAN, cần phân biệt:
- **Full backup:** backup toàn bộ block cần thiết theo semantics RMAN, nhưng không làm base cho incremental backup theo chiến lược level 1.
- **Incremental level 0:** backup nền chứa các block được dùng, có thể làm base cho các incremental level 1 tiếp theo.

Ví dụ level 0:

```sql
BACKUP INCREMENTAL LEVEL 0 DATABASE;
```

Nếu muốn xây dựng chiến lược incremental, level 0 là baseline phù hợp.

### 7.4. Incremental level 1 differential

Level 1 differential chứa các block thay đổi kể từ level 0 hoặc level 1 gần nhất tùy chiến lược incremental. Đây là lựa chọn mặc định khi không chỉ rõ `CUMULATIVE`.

```sql
BACKUP INCREMENTAL LEVEL 1 DATABASE;
```

Khi restore, RMAN cần level 0 và các level 1 liên quan cùng redo để roll forward.

### 7.5. Incremental level 1 cumulative

Level 1 cumulative chứa các block thay đổi kể từ level 0 gần nhất.

```sql
BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
```

Cumulative thường tạo backup lớn hơn differential theo thời gian nhưng có thể giảm số incremental backup cần apply khi recovery.

### 7.6. So sánh differential và cumulative

| Tiêu chí | Level 1 differential | Level 1 cumulative |
|---|---|---|
| Cơ sở so sánh | Level 0 hoặc level 1 gần nhất | Level 0 gần nhất |
| Dung lượng mỗi backup | Thường nhỏ hơn | Thường lớn hơn |
| Số backup cần apply | Có thể nhiều hơn | Thường ít hơn |
| Thời gian backup | Thường ngắn hơn | Có thể dài hơn |
| Recovery time | Có thể cần apply nhiều level | Có thể ít level hơn |
| Phù hợp | Tiết kiệm dung lượng và backup window | Ưu tiên giảm bước apply khi restore |

Kết quả thực tế phụ thuộc tỷ lệ thay đổi block, lịch backup và workload.

### 7.7. Block Change Tracking

Block Change Tracking (BCT) giúp RMAN xác định block thay đổi để tăng tốc incremental backup trong các cấu hình hỗ trợ. BCT giảm công việc quét để tìm block thay đổi, không loại bỏ việc đọc dữ liệu cần backup.

BCT cần file tracking và quản lý dung lượng/vị trí. Bật hoặc di chuyển file tracking theo tài liệu phiên bản và quy trình DBA.

## 8. Thiết kế lịch backup

Lịch backup nên phản ánh RPO, RTO, tốc độ thay đổi dữ liệu và thời gian restore.

Ví dụ lịch minh họa:
- Chủ nhật: level 0.
- Thứ Hai đến Thứ Bảy: level 1 differential.
- Mỗi 15 phút: backup archived redo logs.
- Hàng ngày: backup control file/SPFILE thông qua autobackup hoặc job được kiểm soát.
- Hàng tuần: kiểm tra restore validate.
- Hàng quý: diễn tập phục hồi ở môi trường riêng.

Đây không phải lịch dùng chung cho mọi hệ thống. Nếu RPO là 5 phút, backup archived redo mỗi 15 phút không đáp ứng mục tiêu đó. Có thể cần backup log thường xuyên hơn, Data Guard hoặc giải pháp bảo vệ khác.

### 8.1. Ví dụ RMAN cấu hình retention

```sql
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
```

Recovery window là thời gian mà chiến lược backup phải cho phép phục hồi về bất kỳ thời điểm nào trong cửa sổ đó, với điều kiện backup và redo cần thiết còn tồn tại.

Một cách khác là redundancy:

```sql
CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
```

Redundancy giữ số bản backup cần thiết theo policy. Không cấu hình retention chỉ dựa trên dung lượng; cần xét RPO/RTO, quy định lưu trữ và bản backup offsite.

### 8.2. Backup destination và FRA

Fast Recovery Area (FRA) có thể lưu backup, archived redo, flashback logs và file phục hồi khác. Theo dõi:
- Tổng dung lượng và dung lượng đã dùng.
- Tốc độ tăng archived redo.
- Backup piece cũ/obsolete.
- Flashback log.
- Tình trạng archive destination.
- Cảnh báo không đủ chỗ.

Không xem FRA là nơi backup duy nhất. Nếu storage/FRA bị mất cùng database, bản backup ở đó cũng có thể mất. Cần bản sao ở storage hoặc site độc lập theo yêu cầu disaster recovery.

## 9. RPO và RTO: hai mục tiêu khác nhau

### 9.1. RPO — Recovery Point Objective

RPO là lượng dữ liệu tối đa mà tổ chức chấp nhận mất sau sự cố, biểu diễn như khoảng cách thời gian từ điểm dữ liệu phục hồi đến thời điểm sự cố.

Ví dụ:
- RPO 24 giờ: có thể chấp nhận phục hồi về backup ngày trước trong tình huống đã xác định.
- RPO 1 giờ: cần backup/redo hoặc cơ chế bảo vệ dữ liệu bảo đảm điểm phục hồi không lùi quá một giờ.
- RPO gần 0: cần giải pháp sao chép/standby và vận hành phù hợp; backup định kỳ đơn thuần thường không đủ để bảo đảm.

RPO không đồng nghĩa tần suất backup database. Với ARCHIVELOG và archived redo đầy đủ, có thể phục hồi đến một thời điểm sau backup database. Ngược lại, nếu thiếu một đoạn archived redo, điểm phục hồi có thể phải lùi về trước đoạn thiếu đó.

### 9.2. RTO — Recovery Time Objective

RTO là thời gian tối đa để khôi phục dịch vụ về mức hoạt động đã định sau sự cố.

RTO không chỉ là thời gian chạy `RESTORE DATABASE`. Cần tính:
- Phát hiện và phân loại sự cố.
- Quyết định failover hay restore.
- Cấp phát hạ tầng/storage.
- Restore datafile và control file.
- Apply incremental backup và redo.
- Open database và kiểm tra consistency.
- Khởi động listener, service và ứng dụng.
- Xác minh dữ liệu và nghiệp vụ.
- Mở lại traffic theo từng bước.

Nếu database mở được sau 45 phút nhưng ứng dụng mất thêm 90 phút để xác minh và kết nối, RTO dịch vụ phải tính toàn bộ thời gian đó.

### 9.3. Ví dụ RPO/RTO

| Hệ thống | RPO mục tiêu | RTO mục tiêu | Gợi ý thiết kế |
|---|---:|---:|---|
| Báo cáo nội bộ | 24 giờ | 8 giờ | Backup định kỳ, restore test |
| Ứng dụng nghiệp vụ | 15 phút | 2 giờ | ARCHIVELOG, backup log thường xuyên, restore rehearsal |
| Giao dịch quan trọng | 1 phút | 15 phút | Xem xét standby, redo transport/apply, failover runbook |
| Dịch vụ gần như liên tục | Gần 0 | Vài phút | Kiến trúc HA/DR chuyên biệt, kiểm thử failover |

Các con số là ví dụ minh họa. RPO/RTO phải do chủ hệ thống và nghiệp vụ phê duyệt, dựa trên chi phí downtime và mất dữ liệu.

### 9.4. RPO và RTO có thể xung đột chi phí

RPO thấp hơn thường cần bảo vệ redo thường xuyên hoặc đồng bộ hơn. RTO thấp hơn thường cần hạ tầng sẵn sàng, bản sao ở site khác, quy trình tự động hóa và kiểm thử. Cả hai mục tiêu thấp đều làm tăng chi phí vận hành.

Không chọn RPO/RTO chỉ theo mong muốn kỹ thuật. Tổ chức cần xác định tổn thất chấp nhận được, yêu cầu pháp lý, SLA và ngân sách.

## 10. Ánh xạ RPO/RTO sang chiến lược Oracle

### 10.1. RPO chủ yếu được quyết định bởi khả năng giữ redo

Một backup database hàng đêm có thể đáp ứng RPO 24 giờ nếu tổ chức chấp nhận mất dữ liệu trong ngày. Nếu RPO 15 phút, cần bảo đảm archived redo được backup/đưa ra site an toàn với tần suất và độ trễ phù hợp.

Nếu cần RPO gần 0, cần đánh giá Data Guard synchronous transport hoặc giải pháp bảo vệ khác theo kiến trúc. Không tuyên bố RPO bằng 0 chỉ vì có standby; cần xem transport mode, protection mode, network và tình trạng apply.

### 10.2. RTO chủ yếu được quyết định bởi tốc độ khôi phục và mức sẵn sàng

RTO có thể giảm bằng:
- Backup storage có throughput đủ cao.
- RMAN channel/parallelism được benchmark.
- Image copy hoặc incremental merge nếu phù hợp.
- Standby database sẵn sàng.
- Runbook tự động hóa.
- Hạ tầng DR đã cấp phát.
- Kiểm thử failover/restore định kỳ.
- Quy trình ứng dụng và DNS/network rõ ràng.

Tăng RMAN parallelism không tự động làm restore nhanh hơn nếu storage, CPU, network hoặc encryption đã là bottleneck.

### 10.3. Ma trận lựa chọn

| Mục tiêu | Thành phần cần đánh giá |
|---|---|
| RPO vài giờ | Backup database và archived redo theo lịch |
| RPO vài phút | Archived redo backup/transport thường xuyên, giám sát archive gap |
| RPO gần 0 | Data Guard protection mode và synchronous transport theo yêu cầu |
| RTO vài giờ | RMAN restore/recovery đã diễn tập, storage sẵn sàng |
| RTO dưới một giờ | Restore acceleration, image copy hoặc standby/failover |
| RTO vài phút | HA/DR có failover tự động hoặc bán tự động và runbook được thử |

Các giải pháp HA/DR không thay thế backup. Logical corruption hoặc thao tác xóa nhầm có thể được replicate sang standby, vì vậy vẫn cần backup độc lập và khả năng point-in-time recovery.

## 11. Restore và recover database bằng RMAN

### 11.1. Kịch bản database mất datafile

Giả sử một datafile bị mất nhưng control file, SPFILE và archived redo còn dùng được.

Quy trình tổng quát:
1. Xác định datafile hỏng/mất.
2. Xác định backup hợp lệ và archived redo cần thiết.
3. Restore datafile.
4. Recover datafile.
5. Xác nhận trạng thái online và database consistency.
6. Kiểm tra ứng dụng và alert log.

Ví dụ:

```sql
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

Số 7 là ví dụ. Xác định đúng file number, tên file và trạng thái trước khi thực hiện.

### 11.2. Kịch bản mất toàn bộ database files

Khi mất datafile trên diện rộng:
1. Khôi phục control file nếu cần.
2. Mount database.
3. Catalog backup piece nếu repository không biết vị trí backup.
4. Restore database.
5. Recover database.
6. Mở database theo đúng complete/incomplete recovery path.
7. Kiểm tra database và ứng dụng.

Ví dụ khung lệnh:

```sql
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

Nếu control file mất, quy trình cần restore control file trước và mount lại theo hướng dẫn Oracle. Không chạy nguyên ví dụ trên production khi chưa xác định trạng thái hiện tại và điểm phục hồi.

### 11.3. Catalog backup piece

Nếu backup được copy sang vị trí mới và RMAN repository không có metadata, có thể cần catalog file:

```sql
CATALOG START WITH '/backup/restore_area/';
```

Đường dẫn là ví dụ. Xác nhận đúng thư mục và chỉ catalog các backup piece hợp lệ. Không dùng lệnh này thay cho kiểm tra backup identity hoặc tính toàn vẹn.

### 11.4. Kiểm tra backup có thể restore

```sql
RESTORE DATABASE PREVIEW;
```

PREVIEW cho biết RMAN dự định dùng backup nào và các yêu cầu liên quan; nó không restore file.

```sql
RESTORE DATABASE VALIDATE;
```

VALIDATE kiểm tra khả năng đọc/đáp ứng của backup cần thiết theo phạm vi lệnh; nó không thay thế một lần restore/recovery thật. Một số loại lỗi chỉ lộ ra khi diễn tập đầy đủ trên môi trường phục hồi.

## 12. Point-in-time recovery (PITR)

PITR phục hồi database hoặc phạm vi được hỗ trợ về một điểm trước hiện tại, thường để tránh một thay đổi logic sai hoặc lỗi thao tác.

### 12.1. Chọn điểm bằng thời gian hoặc SCN

RMAN hỗ trợ chỉ định điểm đích bằng `UNTIL TIME`, `UNTIL SCN` hoặc các lựa chọn phù hợp như sequence. Ví dụ minh họa:

```sql
RUN {
    SET UNTIL TIME
        "TO_DATE('2026-11-14 09:30:00',
                 'YYYY-MM-DD HH24:MI:SS')";
    RESTORE DATABASE;
    RECOVER DATABASE;
}
```

Thời điểm và timezone phải được xác định chính xác. Với sự cố dữ liệu logic, nên tìm SCN hoặc thời điểm transaction gây lỗi để tránh phục hồi quá xa.

### 12.2. Mở database sau incomplete recovery

Sau database point-in-time recovery, quy trình thường yêu cầu:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

`RESETLOGS` bắt đầu một incarnation mới. Ngay sau đó cần tạo backup mới và xác nhận RMAN repository/incarnation state. Không dùng `OPEN RESETLOGS` như một lệnh sửa lỗi chung khi database không mở được.

### 12.3. TSPITR và table recovery

- **Tablespace point-in-time recovery (TSPITR):** phục hồi một tablespace về điểm thời gian trước đó trong khi các phần còn lại của database tiếp tục ở trạng thái hiện tại, với điều kiện và quy trình Oracle quy định.
- **RMAN table recovery:** một số phiên bản hỗ trợ phục hồi table hoặc table partition đến một thời điểm bằng cách tạo auxiliary instance và import lại object. Cú pháp và giới hạn phụ thuộc release.
- **Data Pump:** có thể import lại object từ logical export.
- **Flashback:** có thể phục hồi một số lỗi thao tác mà không cần restore toàn database, nếu dữ liệu và flashback logs còn đủ.

Chọn đúng công cụ theo phạm vi sự cố. Phục hồi một bảng về thời điểm cũ không giống phục hồi toàn database; phải đánh giá foreign key, dependency, transaction và dữ liệu phát sinh sau thời điểm đó.

## 13. Control file, SPFILE và recovery catalog

### 13.1. Control file

Control file ghi thông tin cấu trúc database, checkpoint, datafile, redo log và metadata backup. Mất control file có thể làm database không mount được.

Bảo vệ bằng:
- Multiplex control file trên các vị trí/storage phù hợp.
- RMAN autobackup.
- Backup control file thường xuyên.
- Bản sao ngoài site.
- Runbook restore control file và mount database.

Multiplexing giúp chống lỗi mất một bản control file nhưng không bảo vệ khỏi mất toàn bộ storage/site nếu các bản nằm cùng miền lỗi.

### 13.2. SPFILE

SPFILE lưu tham số khởi động. Mất SPFILE có thể phục hồi từ autobackup hoặc PFILE được quản lý. Giữ bản sao cấu hình và ghi nhận các thay đổi tham số quan trọng.

### 13.3. Recovery catalog

RMAN repository có thể nằm trong control file hoặc recovery catalog riêng. Catalog lưu metadata backup và lịch sử dài hơn tùy cấu hình.

Recovery catalog hữu ích khi:
- Quản lý nhiều database.
- Lưu metadata backup dài hạn.
- Theo dõi incarnation và backup history.
- Hỗ trợ một số tính năng quản lý tập trung.

Catalog không chứa bản sao datafile và không thay thế backup storage. Bảo vệ chính catalog database như một hệ thống quan trọng khác.

## 14. Archived redo log: mắt xích quan trọng của recovery

### 14.1. Backup archived redo thường xuyên

Ví dụ:

```sql
BACKUP ARCHIVELOG ALL;
```

Có thể dùng `BACKUP DATABASE PLUS ARCHIVELOG` trong job để kết hợp backup database và log. Tần suất backup log phải đáp ứng RPO và tốc độ sinh redo.

### 14.2. Archive gap

Nếu thiếu một archived redo log trong chuỗi cần thiết, recovery có thể không tiến qua được đoạn thiếu đó. DBA cần theo dõi:
- Archive destination status.
- Sequence được tạo và đã backup.
- Log deletion policy.
- Standby archive gap nếu có Data Guard.
- Network transfer và apply lag.
- Dung lượng FRA và filesystem.

### 14.3. Không xóa log bằng hệ điều hành

Không tự xóa archived redo file bằng `rm` hoặc `del` trong khi RMAN/database còn quản lý. Dùng RMAN và deletion policy để xóa log chỉ khi điều kiện backup/standby đã đáp ứng.

Ví dụ kiểm tra repository:

```sql
LIST ARCHIVELOG ALL;
```

Kiểm tra backup:

```sql
LIST BACKUP OF ARCHIVELOG ALL;
```

## 15. Kiểm tra backup và khả năng phục hồi

### 15.1. CROSSCHECK

```sql
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
```

CROSSCHECK đối chiếu metadata RMAN với sự tồn tại của file ở storage hoặc media manager. Nó không đọc toàn bộ nội dung backup để chứng minh có thể phục hồi.

### 15.2. REPORT OBSOLETE và DELETE OBSOLETE

```sql
REPORT OBSOLETE;
```

Lệnh này liệt kê backup không còn cần thiết theo retention policy hiện tại.

Sau khi DBA xem xét:

```sql
DELETE OBSOLETE;
```

Không xóa backup chỉ dựa trên tuổi file hoặc thao tác filesystem. Phải hiểu retention, redundancy, recovery window và yêu cầu lưu trữ pháp lý.

### 15.3. VALIDATE

```sql
VALIDATE DATABASE;
```

VALIDATE kiểm tra các file/block theo phạm vi và khả năng của lệnh. Có thể dùng:

```sql
BACKUP VALIDATE CHECK LOGICAL DATABASE;
```

`CHECK LOGICAL` yêu cầu thêm kiểm tra logical block corruption và có chi phí CPU. Chọn lịch chạy phù hợp, theo dõi output và xử lý corruption theo hướng dẫn Oracle.

### 15.4. Restore rehearsal

Một lần kiểm tra có giá trị nhất là restore/recovery thật vào môi trường cô lập:
1. Chuẩn bị server/storage phục hồi.
2. Lấy backup từ nơi lưu trữ độc lập.
3. Khôi phục control file/SPFILE nếu cần.
4. Restore datafile.
5. Apply archived redo.
6. Open database theo quy trình.
7. Kiểm tra object và dữ liệu nghiệp vụ.
8. Đo thời gian từng giai đoạn.
9. Ghi lại lỗi, thiếu quyền, thiếu key và dependency.
10. Dọn môi trường theo quy trình.

VALIDATE tốt nhưng không thay thế restore rehearsal. Chỉ một lần diễn tập đầy đủ mới kiểm tra cả backup media, network, key, cấu hình, runbook và kỹ năng vận hành.

## 16. Bảo vệ backup và khóa mã hóa

Backup có thể chứa toàn bộ dữ liệu production, do đó phải được bảo vệ như database đang chạy.

### 16.1. Encryption

RMAN hỗ trợ backup encryption theo cấu hình và điều kiện phiên bản/edition. Nếu backup mã hóa, phải bảo vệ password hoặc keystore cần thiết để giải mã.

Không lưu encryption password cạnh backup piece trong cùng thư mục hoặc cùng quyền truy cập. Quản lý key theo secret management policy và có quy trình khôi phục đã thử.

### 16.2. TDE keystore

Nếu datafile dùng TDE, khôi phục file mà thiếu keystore/master key phù hợp có thể khiến dữ liệu không giải mã được. Backup kế hoạch cần bao gồm:
- Keystore/wallet.
- Password/secret mở keystore.
- Key history cần cho backup cũ.
- Quy trình restore key trên host/site DR.
- Kiểm thử restore database mã hóa.

Không xóa key cũ chỉ vì đã rotate master key. Backup cũ có thể vẫn phụ thuộc key đó.

### 16.3. Offsite và immutable backup

Có ít nhất một bản backup ở miền lỗi khác:
- Storage hoặc object store ở site khác.
- Tài khoản/quyền quản trị tách biệt.
- Immutable/WORM hoặc object lock khi kiến trúc hỗ trợ.
- Credential backup tách khỏi credential database.
- Giám sát việc xóa/sửa backup.
- Kiểm thử khả năng truy cập từ DR site.

Nếu ransomware có thể xóa cả database và backup cùng tài khoản quản trị, backup không còn là lớp bảo vệ độc lập.

## 17. Data Guard, Flashback và các lớp bảo vệ khác

### 17.1. Data Guard không thay thế backup

Data Guard duy trì standby bằng cách chuyển và apply redo. Nó có thể giảm RPO/RTO trong sự cố site hoặc instance tùy protection mode và cấu hình.

Tuy nhiên, lỗi logic, thao tác xóa nhầm hoặc dữ liệu sai có thể được chuyển sang standby. Backup độc lập và PITR vẫn cần thiết.

### 17.2. Flashback Database

Flashback Database có thể đưa database về một thời điểm trước đó bằng flashback logs khi đã bật và có đủ dữ liệu flashback. Nó có thể nhanh hơn restore/recovery truyền thống cho một số tình huống.

Flashback không thay thế backup vì flashback logs có retention và dung lượng giới hạn, không bảo vệ đầy đủ trước mất toàn bộ storage/site.

### 17.3. Flashback Table và Data Pump

Flashback Table có thể khôi phục một bảng về trạng thái trước đó trong phạm vi hỗ trợ. Data Pump có thể phục hồi object từ export. Hai cách này hữu ích cho lỗi ở phạm vi hẹp, nhưng cần kiểm tra dependency, constraint, transaction và tính nhất quán ứng dụng.

## 18. Tính RTO từ các bước thực tế

Ví dụ một lần diễn tập restore có các giai đoạn:

| Giai đoạn | Thời gian đo |
|---|---:|
| Phát hiện và quyết định | 10 phút |
| Cấp phát storage/host | 15 phút |
| Restore control file và SPFILE | 5 phút |
| Restore datafile | 45 phút |
| Apply incremental và archived redo | 25 phút |
| Open database và kiểm tra | 10 phút |
| Khởi động ứng dụng/đổi traffic | 15 phút |
| Tổng | 125 phút |

Nếu RTO là 2 giờ (120 phút), runbook này chưa đạt mục tiêu. Phải giảm một hoặc nhiều giai đoạn, chuẩn bị hạ tầng trước hoặc chọn kiến trúc DR có thời gian failover ngắn hơn.

Đây là ví dụ minh họa. Thời gian phải đo trên dữ liệu và storage thực tế, gồm thời gian chờ phê duyệt, cấp quyền và kiểm tra nghiệp vụ.

### 18.1. Phân bổ ngân sách RTO

Không dùng toàn bộ RTO cho restore. Hãy phân bổ:
- Detection.
- Decision/authorization.
- Infrastructure.
- Database restore/recovery.
- Application startup.
- Validation.
- Traffic restoration.

Đặt buffer thời gian cho tình huống thực tế có thể chậm hơn diễn tập.

### 18.2. RTO dịch vụ khác RTO database

Database có thể mở nhưng ứng dụng chưa hoạt động vì:
- Listener/service chưa đăng ký.
- DNS hoặc load balancer chưa cập nhật.
- Secret/wallet chưa có trên host DR.
- Job hoặc scheduler chưa được bật.
- Queue/message broker còn lỗi.
- Cache hoặc session state cần khởi tạo.
- Người dùng chưa được chuyển traffic.

SLA nên xác định rõ “dịch vụ phục hồi” nghĩa là gì: database OPEN, health check thành công hay giao dịch nghiệp vụ đầu tiên hoàn tất.

## 19. Tính RPO từ backup và redo

Giả sử:
- Database backup gần nhất lúc 01:00.
- Archived redo được backup mỗi 10 phút.
- Sự cố xảy ra lúc 10:00.
- Chuỗi archived redo đầy đủ và có thể truy cập.

Nếu backup redo cuối cùng hoàn tất lúc 09:50, điểm phục hồi có thể tiến xa hơn 09:50 khi còn các archived log mới hơn trên storage hoặc standby. RPO thực tế phải dựa vào redo cuối cùng có thể phục hồi, không chỉ timestamp của job backup.

### 19.1. Archive backup frequency không phải archive generation frequency

Oracle có thể archive redo thường xuyên tùy tốc độ log switch. Job backup archived redo chạy mỗi 10 phút không có nghĩa mọi log được backup đúng mỗi 10 phút nếu job bị trễ hoặc thất bại.

Cần theo dõi:
- Thời điểm log được archive.
- Thời điểm backup log hoàn tất.
- Sequence gap.
- Log còn trên disk.
- Log đã chuyển offsite.
- Standby apply lag nếu dùng Data Guard.

### 19.2. RPO gần 0 cần đo lag

Với Data Guard, theo dõi transport lag và apply lag, trạng thái destination và protection mode. Synchronous transport có thể giảm mất dữ liệu trong một số điều kiện, nhưng còn phụ thuộc commit acknowledgment, network, standby availability và cấu hình. Không suy ra RPO từ tên chế độ mà không kiểm tra vận hành.

## 20. Các kịch bản phục hồi thường gặp

| Sự cố | Hướng xử lý ban đầu |
|---|---|
| Mất một datafile | Restore/recover datafile |
| Mất control file | Restore control file, mount và recovery |
| Mất SPFILE | Restore SPFILE hoặc dùng PFILE có kiểm soát |
| Mất toàn bộ storage database | Restore database từ backup độc lập và recover |
| Xóa nhầm dữ liệu | Flashback/PITR/table recovery/Data Pump theo phạm vi |
| Sai dữ liệu do deploy | Xác định điểm trước lỗi; cân nhắc PITR hoặc phục hồi object |
| Mất site | Failover Data Guard hoặc restore tại DR site |
| Hỏng block | RMAN block media recovery nếu điều kiện hỗ trợ |
| Backup piece bị mất/hỏng | Chọn backup khác; kiểm tra chuỗi redo và retention |
| Mất TDE keystore | Khôi phục keystore/key phù hợp trước khi đọc dữ liệu mã hóa |

Không có một lệnh duy nhất dùng cho mọi sự cố. Trước khi chạy restore/recover, xác định phạm vi hỏng, trạng thái control file, datafile, redo, incarnation và điểm phục hồi mong muốn.

## 21. Runbook phục hồi cần có gì?

Một runbook tốt phải được viết để người trực ca có thể làm theo trong tình huống áp lực.

Nội dung tối thiểu:
1. Sơ đồ database, storage, RAC/standby và dependency.
2. Owner, escalation path và người có quyền phê duyệt.
3. Vị trí backup, control file autobackup, SPFILE và recovery catalog.
4. Cách lấy DBID và xác định incarnation.
5. Quy trình truy cập backup offsite.
6. Quy trình khôi phục TDE keystore.
7. Lệnh RMAN đã kiểm thử cho từng kịch bản.
8. Cách xác định SCN/time/sequence mục tiêu.
9. Cách xử lý archive gap.
10. Quy trình open/resetlogs khi phù hợp.
11. Kiểm tra database và application.
12. Kế hoạch chuyển traffic và thông báo.
13. Bằng chứng phục hồi và thời gian từng bước.
14. Quy trình quay lui hoặc xử lý nếu recovery thất bại.

Không để password, private key hoặc wallet password dạng plaintext trong runbook. Dùng secret manager và hướng dẫn truy cập có kiểm soát.

## 22. Bài thực hành RMAN trong môi trường lab

Các lệnh dưới đây minh họa quy trình. Cần database lab, quyền SYSBACKUP/SYSDBA phù hợp, storage backup đủ chỗ và cấu hình RMAN hợp lệ. Không chạy restore/recovery hoặc xóa backup trên production chỉ để học.

### Bước 1. Kiểm tra database mode

```sql
SELECT name, open_mode, log_mode
FROM v$database;
```

### Bước 2. Kết nối RMAN

```text
rman target /
```

### Bước 3. Cấu hình control file autobackup

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

### Bước 4. Tạo backup database và archived logs

```sql
BACKUP DATABASE PLUS ARCHIVELOG;
```

### Bước 5. Xem backup

```sql
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
```

### Bước 6. Kiểm tra repository và obsolete

```sql
CROSSCHECK BACKUP;
REPORT OBSOLETE;
```

Chỉ chạy `DELETE OBSOLETE` sau khi xác nhận retention và bản backup cần giữ.

### Bước 7. Xem trước restore

```sql
RESTORE DATABASE PREVIEW;
```

### Bước 8. Validate backup

```sql
RESTORE DATABASE VALIDATE;
```

### Bước 9. Diễn tập trên auxiliary host/database

Thực hiện restore/recovery theo runbook vào môi trường riêng. Đo thời gian, kiểm tra key, archived logs, object và ứng dụng. Không thử làm mất datafile của database lab dùng chung.

### Bước 10. Lập báo cáo RPO/RTO

Ghi:
- Thời điểm backup cuối.
- Redo cuối cùng phục hồi được.
- Điểm phục hồi đạt được.
- Thời gian phát hiện.
- Thời gian restore.
- Thời gian recovery.
- Thời gian kiểm tra.
- Thời điểm dịch vụ sẵn sàng.
- Sai lệch so với mục tiêu.

## 23. Những sai lầm thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| Backup và restore là một việc | Backup tạo bản sao; restore đưa file từ bản sao về vị trí phục hồi |
| Restore là database đã sẵn sàng | Datafile có thể còn cần media recovery |
| Recovery chỉ là copy file | Recovery áp dụng redo/incremental để đưa dữ liệu đến điểm nhất quán |
| Full backup và level 0 giống nhau trong mọi ngữ cảnh | Level 0 là base cho incremental level 1; full backup không làm base incremental |
| Backup hàng ngày đáp ứng mọi RPO | RPO còn phụ thuộc archived redo và chuỗi log có thể phục hồi |
| Backup job thành công chứng minh restore được | Cần validate và restore rehearsal |
| FRA là bản backup offsite | FRA có thể mất cùng storage/site |
| Data Guard thay thế RMAN | Standby không bảo vệ đầy đủ trước logical corruption hoặc thao tác sai được replicate |
| TDE backup không cần key | Cần keystore/master key tương ứng để giải mã |
| RTO chỉ là thời gian restore datafile | Còn phát hiện, hạ tầng, recovery, application và validation |
| RPO bằng tần suất chạy backup | Phải tính redo cuối cùng có thể phục hồi |
| `CROSSCHECK` đọc toàn bộ backup để xác minh | Nó đối chiếu repository với sự tồn tại/khả dụng media, không thay thế restore test |
| `REPORT OBSOLETE` có nghĩa có thể xóa mọi file cũ | Phải theo retention policy và dependency |
| `OPEN RESETLOGS` là cách sửa database không mở được | Chỉ dùng theo đúng quy trình incomplete recovery/incarnation |
| Data Pump thay thế RMAN | Export logic không thay thế phục hồi vật lý toàn database |

## 24. Checklist thiết kế backup và DR

### Mục tiêu nghiệp vụ
- RPO được owner phê duyệt.
- RTO được định nghĩa ở cấp dịch vụ.
- Xác định các hệ thống phụ thuộc.
- Xác định thời gian phục hồi tối đa cho từng giai đoạn.

### Backup
- Database ở ARCHIVELOG nếu cần online backup/PITR.
- Có level 0/full và lịch incremental phù hợp.
- Archived redo được backup/transport đủ thường xuyên.
- Control file và SPFILE được bảo vệ.
- Recovery catalog được backup nếu sử dụng.
- TDE keystore và key history được bảo vệ.
- Backup có bản sao offsite/immutable theo policy.

### Kiểm tra
- RMAN CROSSCHECK và VALIDATE chạy theo lịch.
- Có restore rehearsal định kỳ.
- Đã thử phục hồi database mã hóa.
- Đã đo thời gian restore/recovery thực tế.
- Đã kiểm tra archive gap và backup retention.

### DR
- Có runbook và owner.
- Hạ tầng DR sẵn sàng.
- Có quyền truy cập backup và key.
- Có kế hoạch Data Guard/failover nếu dùng.
- Có kiểm tra ứng dụng sau database recovery.
- Có ngưỡng quyết định failover/restore.
- Có diễn tập và cập nhật runbook sau mỗi lần thử.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Backup là gì?

**Trả lời:** Là bản sao dữ liệu và metadata được tạo để có thể phục hồi database hoặc object khi xảy ra sự cố.

**Câu 2.** Restore khác recovery thế nào?

**Trả lời:** Restore đưa file từ backup về vị trí phục hồi; recovery áp dụng incremental backup và redo để đưa file/database đến trạng thái nhất quán tại điểm đích.

**Câu 3.** RPO là gì?

**Trả lời:** Mức mất dữ liệu tối đa tổ chức chấp nhận, thường biểu diễn bằng khoảng thời gian từ điểm phục hồi đến thời điểm sự cố.

**Câu 4.** RTO là gì?

**Trả lời:** Thời gian tối đa để khôi phục dịch vụ về mức hoạt động được định nghĩa.

**Câu 5.** Vì sao ARCHIVELOG quan trọng?

**Trả lời:** Archived redo cho phép roll forward sau backup và phục hồi đến các điểm thời gian mới hơn backup nếu chuỗi log đầy đủ.

**Câu 6.** Full backup khác incremental level 0 thế nào?

**Trả lời:** Level 0 là baseline cho incremental level 1; full backup không đóng vai trò base incremental theo chiến lược RMAN.

**Câu 7.** Differential và cumulative level 1 khác nhau thế nào?

**Trả lời:** Differential lấy thay đổi từ level 0 hoặc level 1 gần nhất; cumulative lấy thay đổi kể từ level 0 gần nhất.

**Câu 8.** Vì sao cần backup control file và SPFILE?

**Trả lời:** Control file mô tả cấu trúc database và metadata backup; SPFILE giữ tham số cần để khởi động instance.

**Câu 9.** Vì sao cần archived redo backup?

**Trả lời:** Để có thể recover qua thời điểm backup database và đáp ứng RPO đã đặt.

**Câu 10.** CROSSCHECK có chứng minh restore thành công không?

**Trả lời:** Không. Nó đối chiếu repository và media; cần VALIDATE và restore rehearsal để kiểm chứng sâu hơn.

**Câu 11.** Data Guard có thay thế backup không?

**Trả lời:** Không. Lỗi logic có thể được replicate sang standby; vẫn cần backup độc lập và PITR.

**Câu 12.** Vì sao backup TDE cần keystore?

**Trả lời:** Dữ liệu mã hóa cần master key phù hợp để giải mã sau restore.

**Câu 13.** RTO có gồm kiểm tra ứng dụng không?

**Trả lời:** Có, nếu mục tiêu được định nghĩa ở cấp dịch vụ. Database mở được chưa chắc nghiệp vụ đã hoạt động.

**Câu 14.** RPO có bằng tần suất backup database không?

**Trả lời:** Không. Cần xét archived redo cuối cùng có thể phục hồi và mọi đoạn log bị thiếu.

**Câu 15.** Khi nào dùng PITR?

**Trả lời:** Khi cần đưa database về một điểm trước hiện tại, ví dụ trước thao tác xóa nhầm hoặc lỗi logic.

**Câu 16.** Vì sao phải mở RESETLOGS sau một số incomplete recovery?

**Trả lời:** Vì Oracle bắt đầu incarnation mới sau khi database được phục hồi về điểm không còn theo redo hiện tại; cần quản lý backup/incarnation tiếp theo đúng cách.

## 26. Kết luận

Backup, restore và recovery là ba phần của một quy trình bảo vệ dữ liệu. Backup tạo bản sao có thể sử dụng; restore đưa file từ backup trở lại; recovery áp dụng incremental backup và redo để đưa database về điểm nhất quán mong muốn. RMAN là công cụ trung tâm cho backup và media recovery vật lý, còn Data Pump, Flashback và Data Guard giải quyết các phạm vi bảo vệ khác nhau.

RPO xác định tổ chức chấp nhận mất tối đa bao nhiêu dữ liệu; RTO xác định mất bao lâu để dịch vụ hoạt động trở lại. RPO phụ thuộc backup, archived redo, độ đầy đủ của log và cơ chế standby/replication. RTO phụ thuộc tốc độ restore/recovery, hạ tầng DR, key, ứng dụng và khả năng thực hiện runbook. Không thể suy ra hai mục tiêu này chỉ từ lịch backup hoặc một lệnh RMAN thành công.

Thiết kế tốt phải bảo vệ datafile, control file, SPFILE, archived redo, recovery catalog nếu có, TDE keystore và các dependency bên ngoài; đồng thời giữ ít nhất một bản backup độc lập với miền lỗi của database. Hãy kiểm tra bằng CROSSCHECK/VALIDATE và quan trọng nhất là diễn tập restore/recovery thật, đo thời gian từng bước, xác nhận dữ liệu và ứng dụng. Chỉ khi thử nghiệm chứng minh đạt RPO/RTO thì kế hoạch backup và disaster recovery mới có bằng chứng vận hành.

