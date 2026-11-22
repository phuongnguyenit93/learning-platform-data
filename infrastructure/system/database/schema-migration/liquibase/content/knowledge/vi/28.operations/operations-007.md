# Chuẩn bị bản sao lưu và diễn tập khôi phục

## 1. Mục tiêu và bối cảnh

Liquibase quản lý thay đổi schema và dữ liệu qua changelog, changeset và lịch sử triển khai. Dù migration được kiểm thử kỹ, sự cố vẫn có thể xảy ra: triển khai nhầm changeset, lỗi ứng dụng ghi dữ liệu sai, thao tác DBA xóa nhầm bảng, hỏng storage, lỗi phần cứng, mã độc hoặc sự cố ở vùng cloud. Khi đó, khả năng phục hồi phụ thuộc vào việc tổ chức đã chuẩn bị bản sao lưu phù hợp và thực sự thử khôi phục hay chưa.

Một bản backup chỉ được xem là có giá trị vận hành khi có thể **restore thành công trong thời gian đáp ứng mục tiêu**, dữ liệu đạt điểm phục hồi chấp nhận được và ứng dụng có thể tiếp tục hoạt động. Việc lệnh backup trả exit code 0 hoặc file dump tồn tại chưa đủ chứng minh điều đó.

Bài thuộc chương **Vận hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **chuẩn bị bản sao lưu và diễn tập khôi phục**, bao gồm dữ liệu, schema, lịch sử Liquibase, artifact changelog và cấu hình cần thiết để dựng lại dịch vụ.

Sau bài học, bạn cần có thể:

1. Xác định RPO, RTO và phạm vi dữ liệu cần bảo vệ.
2. Chọn backup logic, physical, snapshot, full, incremental hoặc differential phù hợp.
3. Hiểu vai trò của transaction consistency, WAL, binlog và log backup trong phục hồi theo thời điểm.
4. Bảo vệ backup bằng mã hóa, phân quyền, retention và bản sao bất biến.
5. Giữ changelog, artifact, cấu hình và thông tin phiên bản đồng bộ với backup database.
6. Khôi phục database vào môi trường cô lập và kiểm tra schema, dữ liệu, DATABASECHANGELOG.
7. Diễn tập nhiều tình huống, đo thời gian và ghi nhận bằng chứng.
8. Xây dựng runbook phục hồi có người chịu trách nhiệm, điều kiện cutover và tiêu chí kết thúc.

## 2. Phân biệt backup, restore và disaster recovery

Ba khái niệm liên quan nhưng không giống nhau:

- **Backup** là bản sao dữ liệu hoặc trạng thái database được tạo tại một thời điểm hay theo một chuỗi backup.
- **Restore** là thao tác nạp bản backup vào một database/instance đích.
- **Recovery** là quá trình đưa database từ trạng thái đã restore tới một điểm nhất quán có thể sử dụng, có thể bao gồm áp dụng transaction log/WAL/binlog.
- **Disaster recovery (DR)** là năng lực khôi phục toàn dịch vụ sau sự cố lớn, bao gồm database, ứng dụng, mạng, secret, DNS, storage, nhân sự và quy trình vận hành.

Backup là một thành phần của DR, không phải toàn bộ DR. Nếu chỉ sao lưu database nhưng không giữ artifact ứng dụng, changelog, cấu hình, certificate hoặc cách cấp secret, nhóm có thể phục hồi dữ liệu mà vẫn không khởi động được hệ thống.

Một quy trình cần mô tả cả **điểm phục hồi** và **đường đi để dịch vụ hoạt động trở lại**.

## 3. Xác định RPO và RTO trước khi chọn công nghệ

Hai mục tiêu thường dùng để thiết kế backup:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường được biểu diễn bằng khoảng thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ tới trạng thái hoạt động.

Ví dụ một hệ thống đơn hàng đặt mục tiêu RPO 5 phút và RTO 60 phút:

| Mục tiêu | Ý nghĩa vận hành | Hệ quả thiết kế |
|---|---|---|
| RPO 5 phút | Chấp nhận mất tối đa khoảng 5 phút giao dịch trong kịch bản đã xác định | Cần backup nền kết hợp transaction log/WAL/binlog được lưu và chuyển đi thường xuyên |
| RTO 60 phút | Dịch vụ phải hoạt động lại trong vòng 60 phút | Cần automation, hạ tầng dự phòng, runbook, người trực và diễn tập đủ nhanh |

RPO/RTO phải được thống nhất với chủ sản phẩm, vận hành và chủ sở hữu dữ liệu. Không chọn con số chỉ dựa trên khả năng của công cụ.

Cần làm rõ RTO bắt đầu tính từ lúc nào: phát hiện sự cố, xác nhận incident hay bắt đầu lệnh restore. Nên tính cả thời gian quyết định, cấp quyền, dựng instance, restore, replay log, kiểm tra và cutover; nếu chỉ đo thời gian lệnh restore, con số sẽ quá lạc quan.

### 3.1. RPO/RTO khác nhau theo dữ liệu và dịch vụ

Không phải mọi bảng có cùng mức độ quan trọng:

- Đơn hàng, thanh toán và sổ cái có yêu cầu mất dữ liệu rất thấp.
- Dữ liệu cache hoặc báo cáo có thể dựng lại từ nguồn khác.
- Dữ liệu audit có thể cần retention dài và tính toàn vẹn cao.
- Dữ liệu test có thể được tạo lại.
- DATABASECHANGELOG là lịch sử quản lý schema, cần được phục hồi nhất quán với schema tương ứng.

Có thể phân loại theo business impact và đặt RPO/RTO cho từng database hoặc nhóm dữ liệu. Tránh dùng một lịch backup chung cho mọi hệ thống mà không xét mức độ quan trọng.

## 4. Chọn chiến lược backup

### 4.1. Logical backup

Logical backup xuất dữ liệu và cấu trúc thành các câu lệnh hoặc định dạng logic có thể import vào database tương thích.

Ví dụ công cụ:

- PostgreSQL: pg_dump/pg_restore.
- MySQL/MariaDB: mysqldump hoặc công cụ logical dump phù hợp.
- SQL Server: export/import logic hoặc công cụ theo workload.
- Oracle: Data Pump export/import.

Ưu điểm:

- Có thể chọn database, schema, bảng hoặc object.
- Dễ di chuyển giữa một số phiên bản/instance tương thích.
- Có thể kiểm tra nội dung và phục hồi một phần.
- Phù hợp với migration môi trường hoặc lưu snapshot logic.

Giới hạn:

- Restore database lớn có thể chậm.
- Cần chú ý owner, role, grants, routine, trigger, sequence và extension.
- Một dump không nhất thiết chứa transaction log để phục hồi tới từng thời điểm.
- Tùy chọn export có thể bỏ qua object hoặc dữ liệu nếu cấu hình thiếu.

Logical backup phù hợp cho nhiều mục đích, nhưng không mặc nhiên thay thế physical backup và log archiving khi RPO/RTO nghiêm ngặt.

### 4.2. Physical backup

Physical backup sao chép các file dữ liệu hoặc cấu trúc lưu trữ của DBMS theo cách được công cụ hỗ trợ.

Ví dụ:

- PostgreSQL: base backup cùng WAL archive.
- MySQL: physical backup bằng công cụ phù hợp như MySQL Enterprise Backup hoặc Percona XtraBackup, tùy phiên bản/edition.
- SQL Server: backup full/differential/log ở mức database.
- Oracle: RMAN backup.

Ưu điểm:

- Thường phù hợp database lớn.
- Có thể restore nhanh hơn logical export tùy kiến trúc.
- Kết hợp transaction log để hỗ trợ point-in-time recovery.

Giới hạn:

- Thường phụ thuộc phiên bản, kiến trúc, storage và quy tắc của DBMS.
- Cần giữ đủ chuỗi backup/log và metadata.
- Không nên sao chép file database đang hoạt động bằng cách copy file thông thường nếu không dùng cơ chế snapshot/backup nhất quán được DBMS hỗ trợ.

### 4.3. Snapshot storage/cloud

Snapshot có thể tạo bản sao nhanh ở tầng volume hoặc dịch vụ database managed. Cần xác minh snapshot có tính nhất quán ứng dụng/database hay chỉ nhất quán crash-consistent.

Đối với database đang ghi, snapshot nhiều volume phải bảo đảm các volume được chụp tại cùng một điểm nhất quán hoặc có cơ chế recovery phù hợp. Một snapshot riêng lẻ không tự bảo đảm có thể khởi động database an toàn.

Hãy đọc hướng dẫn của nhà cung cấp và diễn tập restore snapshot vào instance khác. Không coi trạng thái snapshot là bằng chứng restore đã thành công.

### 4.4. Full, incremental và differential

| Kiểu backup | Nội dung | Đặc điểm |
|---|---|---|
| Full | Toàn bộ phạm vi dữ liệu được chọn | Đơn giản khi restore, nhưng tốn thời gian/storage |
| Incremental | Thay đổi kể từ backup trước theo cơ chế công cụ | Tiết kiệm dung lượng, cần đủ chuỗi backup |
| Differential | Thay đổi kể từ full backup gần nhất theo cơ chế công cụ | Restore thường cần full gần nhất và differential phù hợp |
| Transaction log/WAL/binlog | Nhật ký thay đổi sau một mốc backup | Cho phép replay hoặc phục hồi tới thời điểm trong giới hạn hỗ trợ |

Tên gọi và semantics incremental/differential khác nhau giữa công cụ. Phải hiểu chính xác chuỗi cần có để restore, thứ tự nạp và điểm mà log có thể replay.

## 5. Tạo bản backup nhất quán

Backup đang diễn ra khi ứng dụng ghi dữ liệu phải phản ánh một trạng thái nhất quán. Nếu không, các bảng liên quan có thể được chụp ở các thời điểm khác nhau, dẫn tới khóa ngoại hoặc quan hệ nghiệp vụ không còn khớp.

Một số cách đảm bảo consistency:

- Cơ chế consistent snapshot do DBMS cung cấp.
- Transaction snapshot theo isolation phù hợp.
- Backup physical có phối hợp với DBMS.
- Quiesce/tạm dừng writes trong cửa sổ backup nếu hệ thống cho phép.
- Snapshot storage có integration với database và transaction log.

Ví dụ PostgreSQL logical dump thường dùng snapshot nhất quán do công cụ quản lý. Với MySQL, tùy chọn transaction-consistent dump như single-transaction phù hợp với bảng transactional như InnoDB, nhưng không tự bảo đảm mọi storage engine hoặc thay đổi DDL đồng thời đều an toàn.

### 5.1. DDL đồng thời với backup

Migration có thể tạo/drop bảng, đổi cột hoặc thay index trong lúc backup. Một số công cụ có thể xử lý snapshot, metadata lock hoặc DDL theo cách riêng. Cần xác định:

- Backup có chạy đồng thời với Liquibase update không?
- Công cụ có đảm bảo schema/data snapshot nhất quán không?
- Có object được tạo sau khi snapshot bắt đầu nhưng trước khi dump metadata không?
- Có transaction dài gây ảnh hưởng vacuum/undo/log không?
- Có cần cửa sổ maintenance hoặc coordination với migration job không?

Đối với thao tác thay đổi schema lớn, hãy lên lịch backup và migration theo runbook đã thử. Không mặc định backup và Liquibase update có thể chạy song song mà không có tác động.

## 6. Transaction log và phục hồi theo thời điểm

Một full backup chỉ cho phép quay lại trạng thái của thời điểm backup, trừ khi kết hợp thêm log backup hoặc cơ chế replication/CDC phù hợp.

Các DBMS có cơ chế nhật ký riêng:

- PostgreSQL: WAL (Write-Ahead Logging) và archive/streaming.
- MySQL/MariaDB: binary log (binlog), cùng redo/undo log ở tầng storage engine.
- SQL Server: transaction log và backup log trong recovery model phù hợp.
- Oracle: archived redo logs và RMAN recovery.

**Point-in-time recovery (PITR)** dùng backup nền cộng với log liên tục để phục hồi tới một thời điểm hoặc transaction boundary được hỗ trợ. Nó hữu ích khi cần phục hồi trước một thao tác xóa nhầm hoặc migration gây lỗi.

PITR chỉ đạt RPO mong muốn khi log được lưu và chuyển đi đầy đủ, đúng thứ tự, không có khoảng trống và có thể truy cập trong sự cố. Hãy giám sát độ trễ archive/log shipping, dung lượng và retention.

### 6.1. Chọn điểm phục hồi

Điểm phục hồi phải nằm trước sự kiện gây hỏng nhưng sau các giao dịch hợp lệ cần giữ. Việc xác định có thể dựa trên:

- Thời điểm migration bắt đầu/kết thúc.
- Thời điểm deploy ứng dụng.
- Audit log hoặc sự kiện nghiệp vụ.
- Transaction ID/LSN/SCN tùy DBMS.
- Log ứng dụng và thời điểm phát hiện bất thường.

Nếu không biết chính xác thời điểm sự cố, có thể restore ra instance riêng ở vài mốc để kiểm tra. Không replay log qua điểm đã biết có dữ liệu bị phá hủy.

### 6.2. PITR không khôi phục tác động bên ngoài database

Một migration hoặc ứng dụng có thể đã gửi message, gọi API, ghi object storage hoặc phát sinh thanh toán bên ngoài database. Restore database về quá khứ không tự hoàn tác các tác động đó.

Cần đối chiếu outbox, event log, payment provider, message broker và hệ thống downstream. Có thể cần quy trình bù trừ (compensation), replay có kiểm soát hoặc reconciliation nghiệp vụ.

## 7. Những gì phải được bảo vệ cùng database

Để phục hồi một hệ thống Liquibase, cần giữ nhiều thành phần có liên quan:

| Thành phần | Vì sao cần |
|---|---|
| Database data files/dump | Nội dung nghiệp vụ và object database |
| DATABASECHANGELOG | Biết changeset nào đã được ghi nhận |
| DATABASECHANGELOGLOCK | Trạng thái điều phối; cần kiểm tra khi restore |
| Master và changelog con | Mã nguồn mô tả migration |
| SQL file được tham chiếu | Nội dung SQL không nằm trực tiếp trong YAML/XML |
| Artifact release | Biết chính xác changelog/ứng dụng đã triển khai |
| Phiên bản Liquibase và JDBC driver | Tái lập cách công cụ đọc và thực thi changelog |
| Cấu hình không chứa secret | URL/schema/context/label/parameter cần thiết |
| Secret và certificate | Kết nối lại dịch vụ; phải lưu trong secret manager riêng |
| Backup catalog/manifest | Xác định chuỗi backup, thời gian và checksum file |

Nếu DATABASECHANGELOG nằm trong cùng database và cùng phạm vi backup, nó thường được phục hồi cùng database. Nếu metadata được đặt ở database/schema độc lập, cần backup/restore đồng bộ và xác định rõ điểm nhất quán giữa hai nơi.

Không restore schema ứng dụng từ một thời điểm nhưng DATABASECHANGELOG từ thời điểm khác mà không có kế hoạch reconcile. Ví dụ, history nói changeset đã chạy nhưng bảng/cột được tạo bởi changeset lại chưa tồn tại, hoặc ngược lại.

## 8. Thiết kế backup cho Liquibase history

DATABASECHANGELOG không phải bản sao của changelog trong Git. Nó lưu lịch sử thực thi, checksum và metadata; không thay thế artifact release. Ngược lại, changelog trong Git cũng không chứng minh database đã chạy đến changeset nào.

Một bộ bằng chứng phục hồi nên có:

1. Backup database tại thời điểm T.
2. DATABASECHANGELOG nằm trong cùng snapshot hoặc được chụp nhất quán tại T.
3. DATABASECHANGELOGLOCK và trạng thái migration tại thời điểm backup.
4. Commit/tag và artifact changelog tương ứng.
5. Phiên bản Liquibase/driver và cấu hình triển khai.
6. Nhật ký job migration gần thời điểm T.

Trước khi backup quan trọng, tránh chạy migration đồng thời nếu công cụ không bảo đảm snapshot nhất quán cho mục tiêu của bạn. Nếu không thể dừng migration, phải hiểu rõ semantics snapshot và kiểm tra history/schema sau restore.

### 8.1. Không sửa lịch sử để làm khớp một bản restore

Sau restore, nếu DATABASECHANGELOG và schema không khớp, không xóa dòng history hoặc chạy changelogSync ngay để làm pipeline xanh. Trước hết so sánh:

- Artifact changelog đúng với thời điểm backup.
- Changeset cuối cùng trong DATABASECHANGELOG.
- Schema và dữ liệu thực tế.
- Điểm PITR đã chọn.
- Những migration hoặc thao tác thủ công xảy ra sau điểm đó.

Chỉ reconcile history bằng quy trình được review khi đã chứng minh trạng thái database tương ứng. Không dùng clear-checksums để sửa sai lệch giữa backup và changelog.

## 9. Bảo vệ backup như một tài sản nhạy cảm

Backup thường chứa toàn bộ dữ liệu nghiệp vụ, đôi khi cả dữ liệu cá nhân, token hoặc thông tin nhạy cảm. Quyền truy cập backup có thể tương đương quyền đọc trực tiếp database.

Các biện pháp cần có:

- Mã hóa khi truyền và khi lưu.
- Quản lý khóa mã hóa tách khỏi nơi lưu backup.
- Role riêng để tạo, đọc, xóa và restore backup.
- Giới hạn quyền tải backup xuống máy cá nhân.
- Audit mọi lần đọc, export, restore và xóa.
- Retention theo yêu cầu pháp lý/nghiệp vụ.
- Bản sao immutable hoặc object lock chống xóa/sửa trái phép.
- Bản sao ở account, region hoặc failure domain khác.
- Kiểm tra quyền truy cập và vòng đời credential định kỳ.

Không lưu password database trong file backup manifest hoặc changelog. Secret cần được phục hồi qua secret manager và quy trình cấp lại quyền, không nên nhúng vào dump.

### 9.1. Backup không được phép bị xóa cùng hệ thống chính

Nếu attacker hoặc lỗi vận hành có thể xóa cả database lẫn backup trong cùng account/quyền quản trị, backup không còn là phương án chống ransomware hay phá hoại.

Có thể dùng:

- Account backup độc lập.
- Quyền xóa tách khỏi quyền ghi.
- Retention lock/object lock.
- Replication sang region hoặc môi trường tách biệt.
- MFA/approval cho thao tác xóa.
- Kiểm tra cảnh báo khi backup bị xóa hoặc retention bị thay đổi.

### 9.2. Retention và dữ liệu nhạy cảm

Retention phải cân bằng khả năng phục hồi, chi phí và yêu cầu lưu trữ/xóa dữ liệu. Nếu một yêu cầu xóa dữ liệu cá nhân áp dụng, cần hiểu chính sách xử lý trên backup cũ, thời điểm hết hạn và nghĩa vụ pháp lý liên quan. Không tự ý kéo dài retention vô hạn.

Bản backup dùng cho test restore phải được bảo vệ như production data. Nếu có thể, dùng dữ liệu đã ẩn danh hoặc kiểm soát chặt quyền và thời gian tồn tại của môi trường phục hồi.

## 10. Kiểm tra backup sau khi tạo

Sau mỗi lần backup:

1. Kiểm tra exit code và log công cụ.
2. Xác nhận file/object hoàn tất, kích thước hợp lý và metadata thời gian.
3. Tính và lưu checksum hoặc manifest theo công cụ.
4. Kiểm tra chuỗi incremental/log có đủ và không có gap.
5. Xác nhận bản sao đã tới vị trí lưu trữ thứ hai.
6. Kiểm tra mã hóa và quyền truy cập.
7. Theo dõi dung lượng, retention và lỗi job.
8. Định kỳ restore thử trên instance cô lập.

Checksum file giúp phát hiện hỏng dữ liệu truyền/lưu trữ nhưng không chứng minh database có thể restore. Một dump bị thiếu object do sai tùy chọn vẫn có thể có checksum hợp lệ.

## 11. Ví dụ lệnh backup theo DBMS

Các lệnh dưới đây chỉ minh họa dạng thao tác. Cần điều chỉnh theo phiên bản, kích thước database, quyền, chính sách secret và hướng dẫn chính thức của DBMS.

### 11.1. PostgreSQL logical dump

~~~bash
pg_dump --format=custom --file=orders.dump --dbname="$DATABASE_URL"
~~~

Định dạng custom thường được khôi phục bằng pg_restore và hỗ trợ chọn object. Cần lưu ý:

- Dump một database không nhất thiết chứa toàn bộ cluster roles/tablespace.
- Nếu cần global objects, đánh giá pg_dumpall hoặc quy trình riêng.
- Bảo đảm role có quyền đọc đủ object.
- Kiểm tra extension và phiên bản server/client.
- Lưu thông tin owner/grants theo chính sách; tùy chọn no-owner có thể thay đổi owner khi restore.

Khôi phục vào database đích đã chuẩn bị:

~~~bash
pg_restore --dbname=orders_restore --no-owner orders.dump
~~~

Chỉ dùng no-owner nếu chủ đích là ánh xạ object sang owner mới; nếu cần giữ owner, phải chuẩn bị role tương ứng và restore theo quyền phù hợp.

### 11.2. PostgreSQL physical backup và WAL

Có thể dùng pg_basebackup để tạo base backup và cấu hình archive_command/continuous archiving hoặc cơ chế WAL shipping phù hợp để giữ WAL. PITR cần base backup hợp lệ, đầy đủ WAL từ điểm bắt đầu tới recovery target và cấu hình recovery đúng phiên bản PostgreSQL.

Không copy trực tiếp thư mục data đang hoạt động bằng file copy thông thường. Dùng công cụ backup hoặc snapshot được PostgreSQL hỗ trợ.

### 11.3. MySQL/MariaDB logical dump

Ví dụ với MySQL và bảng InnoDB:

~~~bash
mysqldump --single-transaction --routines --triggers --events --databases orders > orders.sql
~~~

single-transaction có thể tạo consistent snapshot cho transactional tables, nhưng không bảo đảm cùng tính nhất quán cho mọi storage engine và không loại bỏ rủi ro DDL đồng thời. Kiểm tra quyền, routine, trigger, event, character set và phiên bản client/server.

Với database lớn hoặc yêu cầu RTO thấp, đánh giá physical backup và binlog retention. Giữ đủ binlog từ mốc backup để phục hồi tới thời điểm mong muốn.

### 11.4. SQL Server

SQL Server thường dùng chuỗi full backup, differential backup và transaction log backup theo recovery model. Ví dụ full backup:

~~~sql
BACKUP DATABASE [Orders]
TO DISK = N'D:\SqlBackups\Orders_full.bak'
WITH CHECKSUM, COMPRESSION, INIT;
~~~

Đường dẫn trên là ví dụ trên máy chủ SQL Server. Cần cấu hình quyền ghi của service account, lưu bản backup ra storage phù hợp và kiểm tra checksum. Để PITR, phải giữ chuỗi log backup liên tục và thực hiện restore theo thứ tự với NORECOVERY/RECOVERY đúng quy trình.

### 11.5. Oracle

Oracle thường sử dụng RMAN để backup database, control file, SPFILE và archived redo log theo cấu hình. Ví dụ lệnh RMAN:

~~~sql
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Đây là ví dụ khái quát; chính sách retention, catalog, encryption, control file autobackup và chiến lược recovery cần được DBA thiết kế. Hãy dùng RMAN validate/restore validate và diễn tập trên môi trường phù hợp.

## 12. Chuẩn bị môi trường restore

Không nên thử restore lần đầu trực tiếp lên production. Chuẩn bị một môi trường cô lập có:

- DBMS cùng phiên bản hoặc phiên bản tương thích đã xác minh.
- Dung lượng storage đủ cho data, log, temporary và quá trình restore.
- Network bị giới hạn, không vô tình gửi email/payment/message thật.
- Secret và credential riêng.
- Artifact ứng dụng/changelog cần thiết.
- Quyền restore được cấp tạm thời.
- Monitoring và log để đo thời gian.
- Cơ chế xóa môi trường sau diễn tập theo chính sách dữ liệu.

Nếu restore bản production có dữ liệu nhạy cảm, áp dụng phân quyền và masking phù hợp. Không để database phục hồi mở kết nối tới hệ thống downstream thật nếu chưa có kiểm soát.

## 13. Quy trình restore tổng quát

Một quy trình phục hồi database nên có các bước sau:

### Bước 1. Kích hoạt incident và xác định phạm vi

Xác định database, cluster, schema và dịch vụ bị ảnh hưởng. Ghi nhận thời điểm sự cố, loại dữ liệu hỏng, các ứng dụng đang ghi và mức độ mất dữ liệu có thể chấp nhận.

### Bước 2. Dừng hoặc cô lập writers

Ngăn ứng dụng, batch job, consumer và pipeline migration tiếp tục ghi vào database đang lỗi. Nếu có replication, xác định node nào là nguồn/đích và tránh failover ngoài kế hoạch.

### Bước 3. Bảo toàn bằng chứng và trạng thái hiện tại

Trước khi sửa hoặc restore, giữ snapshot/log hiện trạng nếu có thể. Lưu DATABASECHANGELOG, DATABASECHANGELOGLOCK, log DBMS, pipeline run, commit và artifact gần nhất. Không xóa object dở dang trước khi ghi nhận.

### Bước 4. Chọn recovery point và backup chain

Xác minh full/base backup, incremental/differential và transaction log/WAL/binlog có đầy đủ. Chọn recovery target trước sự kiện gây lỗi, đồng thời đánh giá giao dịch hợp lệ nào có thể bị mất.

### Bước 5. Restore vào instance cô lập

Dựng database đích mới hoặc môi trường restore tách biệt. Nạp backup theo thứ tự, replay log tới recovery target và xác nhận DBMS hoàn tất recovery.

### Bước 6. Kiểm tra tính toàn vẹn

Kiểm tra database mở được, catalog, object, constraint, dữ liệu quan trọng, số lượng bản ghi theo tiêu chí nghiệp vụ và các bảng trọng yếu. Chạy công cụ kiểm tra consistency phù hợp DBMS.

### Bước 7. Kiểm tra Liquibase history

Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK tại điểm phục hồi. Đối chiếu changeset cuối cùng, checksum, artifact changelog và schema thật. Không chạy update ngay trước khi xác minh.

### Bước 8. Kiểm thử ứng dụng và dữ liệu

Khởi động phiên bản ứng dụng tương thích với schema được restore. Chạy smoke test, truy vấn nghiệp vụ, kiểm tra quyền runtime và các luồng đọc/ghi quan trọng.

### Bước 9. Quyết định cutover

Chỉ chuyển traffic khi database đạt tiêu chí kỹ thuật và nghiệp vụ, dữ liệu đã được đối chiếu, endpoint và credential đúng, downstream đã sẵn sàng và người có thẩm quyền chấp thuận.

### Bước 10. Theo dõi sau phục hồi

Theo dõi error rate, latency, replication lag, connection pool, job nền, queue và số liệu nghiệp vụ. Giữ database cũ hoặc snapshot trước phục hồi theo thời gian runbook quy định để hỗ trợ điều tra.

## 14. Kiểm tra Liquibase sau restore

Sau khi database được restore, Liquibase cần thấy lịch sử tương ứng với schema tại cùng recovery point.

Các bước kiểm tra:

1. Dùng đúng phiên bản Liquibase và JDBC driver đã được hỗ trợ.
2. Dùng đúng master changelog và artifact tại hoặc tương thích với recovery point.
3. Chạy validate để kiểm tra changelog/checksum theo cấu hình.
4. Chạy status để xem changeset nào đang pending.
5. Kiểm tra DATABASECHANGELOG có nằm trong phạm vi restore không.
6. Kiểm tra DATABASECHANGELOGLOCK và xác minh không còn job cũ.
7. So sánh schema thật với những changeset đã được ghi nhận.
8. Chỉ chạy update sau khi đã xác nhận kế hoạch đưa database tới release mục tiêu.

Nếu restore về thời điểm trước migration gần nhất, history thường cũng quay về trước changeset đó khi metadata nằm cùng database và được phục hồi cùng thời điểm. Khi update lại, Liquibase có thể áp dụng changeset đang pending. Tuy nhiên, nếu metadata được backup riêng hoặc restore theo phạm vi khác, cần reconcile cẩn thận.

### 14.1. Không trộn lịch sử của hai thời điểm

Ví dụ schema đã restore về thời điểm T1 nhưng DATABASECHANGELOG lại được lấy từ thời điểm T2 sau khi migration T2 đã chạy. Liquibase có thể bỏ qua changeset cần thiết vì history nói đã chạy, trong khi schema thực tế không có đối tượng tương ứng.

Trường hợp ngược lại, schema chứa đối tượng từ T2 nhưng history ở T1 có thể khiến update thử tạo lại object. Cả hai đều là dấu hiệu history/schema không nhất quán.

Không sửa trực tiếp DATABASECHANGELOG, clear-checksums hoặc changelogSync để che vấn đề. Trước hết xác định chính xác nguồn backup và thời điểm của từng thành phần, sau đó lập kế hoạch reconcile có review.

### 14.2. DATABASECHANGELOGLOCK sau restore

Một backup có thể chụp đúng lúc Liquibase đang giữ lock. Khi restore, DATABASECHANGELOGLOCK có thể phản ánh trạng thái locked tại thời điểm snapshot dù process cũ không còn tồn tại trong môi trường mới.

Trước khi release lock:

- Xác nhận không có migration job/session còn hoạt động.
- Xác định backup được tạo khi nào và lock holder là ai.
- Kiểm tra schema/history đã phục hồi.
- Chỉ giải phóng stale lock theo runbook và dùng lệnh Liquibase phù hợp.

Không chạy release-locks tự động ngay sau mọi restore; có thể đang có một migration hợp lệ trong môi trường phục hồi.

## 15. Phục hồi theo phạm vi: database, schema hay bảng?

Không phải mọi sự cố đều cần restore toàn database.

| Phạm vi | Khi cân nhắc | Rủi ro cần đánh giá |
|---|---|---|
| Toàn instance/cluster | Hỏng storage hoặc sự cố diện rộng | Ảnh hưởng nhiều database và dịch vụ |
| Một database | Hỏng dữ liệu hoặc migration ở một database | Phụ thuộc role, login, job và object ngoài database |
| Một schema | Một domain bị ảnh hưởng, DBMS hỗ trợ cách restore phù hợp | Khóa ngoại, synonym, routine hoặc dependency liên schema |
| Một bảng | Xóa nhầm hoặc dữ liệu bị sửa ở phạm vi hẹp | Khôi phục dữ liệu có thể xung đột với ghi mới và FK |
| Một tập hàng | Sai sót nghiệp vụ có khóa định danh rõ | Cần xác định giá trị trước/sau và tính toàn vẹn liên quan |

Logical export/import có thể thuận tiện cho phục hồi object nhỏ. PITR thường tạo database/instance tại mốc thời gian rồi trích xuất dữ liệu cần thiết, sau đó hòa giải vào hệ thống hiện tại.

Không restore một bảng production bằng cách ghi đè mù quáng nếu bảng tiếp tục nhận giao dịch sau sự cố. Cần dừng writes hoặc thiết kế merge/reconciliation để không mất dữ liệu mới.

## 16. Kiểm tra tính toàn vẹn sau restore

Kiểm tra kỹ thuật cần đi cùng kiểm tra nghiệp vụ.

### 16.1. Kiểm tra kỹ thuật

- Database mở và nhận kết nối.
- Catalog/object metadata đọc được.
- Table, index, sequence, view, function, trigger tồn tại.
- Constraint được bật và trạng thái validate đúng.
- Owner, grants và role membership đúng.
- Không có object invalid hoặc transaction dang dở.
- Log DBMS không báo lỗi recovery nghiêm trọng.

Dùng công cụ riêng của DBMS, ví dụ các lệnh consistency check hoặc validate phù hợp phiên bản. Không dùng một truy vấn count đơn giản thay cho kiểm tra toàn vẹn.

### 16.2. Kiểm tra nghiệp vụ

Chọn các bất biến quan trọng:

- Tổng đơn hàng theo trạng thái có hợp lý.
- Tổng thanh toán đối chiếu được với nguồn thanh toán.
- Không có bản ghi con mồ côi.
- Số lượng giao dịch trong khoảng thời gian phục hồi phù hợp.
- Dữ liệu tham chiếu và trạng thái nghiệp vụ nhất quán.
- Outbox/event chưa gửi được xử lý theo chính sách.
- Không tạo trùng khi replay consumer hoặc job nền.

Kiểm tra mẫu và đối soát tổng hợp giúp phát hiện sai lệch mà database consistency checker không biết.

## 17. Bảo vệ dữ liệu mới phát sinh sau recovery point

PITR thường làm mất các giao dịch sau recovery point trong database được restore. Trước khi cutover, cần xác định:

- Có nguồn log/event/audit khác để tái tạo giao dịch không?
- Giao dịch nào đã được gửi sang hệ thống ngoài?
- Có thể replay event mà không tạo tác động trùng không?
- Có cần khóa idempotency key hoặc đối chiếu transaction ID?
- Có cần thông báo chủ nghiệp vụ về khoảng dữ liệu bị mất?

Nếu chọn restore toàn bộ database về quá khứ, các giao dịch hợp lệ sau điểm đó có thể biến mất. Có thể cần restore sang instance mới, trích xuất dữ liệu cần giữ và hòa giải với database đang hoạt động trước cutover.

Không tự động replay tất cả message sau PITR nếu consumer không idempotent. Việc replay có thể gửi thanh toán, email hoặc lệnh downstream lần thứ hai.

## 18. Diễn tập khôi phục: mục đích và tần suất

Một kế hoạch backup cần có lịch diễn tập. Diễn tập chứng minh rằng:

- Backup có thể đọc và restore.
- Log chain không bị thiếu.
- Credential và quyền restore hoạt động.
- Artifact ứng dụng/changelog có thể truy xuất.
- Người vận hành hiểu runbook.
- Thời gian thực tế đáp ứng RTO.
- Dữ liệu đạt RPO mong muốn.
- Các hệ thống phụ thuộc có thể kết nối sau cutover.

Tần suất dựa trên mức độ quan trọng, tốc độ thay đổi và chính sách tổ chức. Hệ thống quan trọng có thể diễn tập restore định kỳ hàng tháng hoặc theo mỗi thay đổi lớn trong chiến lược backup; hệ thống khác có thể theo quý. Điều quan trọng là lịch có owner, bằng chứng và tiêu chí pass/fail.

### 18.1. Các cấp độ diễn tập

| Cấp độ | Nội dung | Bằng chứng |
|---|---|---|
| Backup verification | Kiểm tra file, checksum, manifest, log và retention | Báo cáo backup job |
| Restore test | Restore vào instance cô lập | Log, thời gian và kết quả consistency |
| Application recovery | Khởi động ứng dụng với database đã restore | Smoke test, quyền và kết quả nghiệp vụ |
| PITR exercise | Phục hồi tới thời điểm cụ thể | Recovery target, log chain và dữ liệu đối chiếu |
| Full DR exercise | Phục hồi cả database, app, secret, network và traffic | RTO/RPO thực tế và báo cáo diễn tập |

Một bài test chỉ kiểm tra file backup tồn tại là mức thấp nhất, không thay thế restore test.

## 19. Kịch bản diễn tập mẫu: khôi phục sau migration lỗi

Giả sử một release triển khai changeset đã drop nhầm cột mà một phiên bản ứng dụng cũ vẫn sử dụng. Ứng dụng bắt đầu lỗi đọc/ghi.

### Giai đoạn A — Phản ứng

1. Dừng rollout và ngăn pipeline migration khác.
2. Đánh giá ứng dụng nào còn dùng cột bị drop.
3. Cô lập luồng ghi có thể làm tình trạng tệ hơn.
4. Lưu log deploy, artifact, DATABASECHANGELOG và thời điểm migration.
5. Xác định có thể dùng forward fix hay cần phục hồi dữ liệu.

### Giai đoạn B — Restore thử

1. Chọn recovery point trước changeset gây lỗi.
2. Restore backup và log vào instance riêng.
3. Kiểm tra cột, dữ liệu, index/constraint và DATABASECHANGELOG.
4. Chạy Liquibase validate/status với artifact tại recovery point.
5. Khởi động phiên bản ứng dụng tương thích.
6. Chạy smoke test và đối chiếu dữ liệu.

### Giai đoạn C — Hòa giải giao dịch

1. Xác định giao dịch phát sinh sau recovery point.
2. Đối chiếu với event log, payment provider hoặc nguồn nghiệp vụ.
3. Tái tạo giao dịch hợp lệ bằng quy trình idempotent nếu có thể.
4. Kiểm tra không phát sinh duplicate hoặc mất dữ liệu ngoài dự kiến.

### Giai đoạn D — Cutover và học hỏi

1. DBA và incident commander xác nhận tiêu chí phục hồi.
2. Chuyển ứng dụng tới instance phục hồi.
3. Theo dõi error rate, latency, job nền và đối soát nghiệp vụ.
4. Ghi RPO/RTO thực tế.
5. Tạo action item sửa changeset, bổ sung kiểm thử và cập nhật runbook.

Diễn tập không nhằm chứng minh mọi sự cố đều phải rollback. Nó giúp nhóm biết khi nào restore phù hợp và khi nào forward fix ít rủi ro hơn.

## 20. Diễn tập PITR và kiểm tra RPO

Một bài diễn tập PITR cần tạo ra các mốc giao dịch có thể nhận biết:

1. Ghi một tập giao dịch có ID thử nghiệm trước mốc backup.
2. Tạo backup nền.
3. Tiếp tục ghi các giao dịch có timestamp/ID rõ.
4. Chờ log archive/backup được chuyển tới kho lưu trữ.
5. Tạo một thay đổi gây lỗi có chủ đích trong môi trường test.
6. Restore tới thời điểm ngay trước thay đổi đó.
7. Xác minh giao dịch trước mốc tồn tại và giao dịch sau mốc không tồn tại theo dự kiến.
8. Đo khoảng mất dữ liệu so với thời điểm sự cố và so sánh với RPO.

Cần dùng dữ liệu test riêng và môi trường cô lập. Không thực hiện thao tác phá hủy có chủ ý trên production để diễn tập.

RPO thực tế phải đo từ thời điểm giao dịch cuối cùng có thể phục hồi, không phải từ thời điểm backup job bắt đầu hoặc kết thúc.

## 21. Đo RTO và các điểm nghẽn

RTO thực tế gồm nhiều khoảng thời gian:

| Giai đoạn | Ví dụ điểm nghẽn |
|---|---|
| Phát hiện và quyết định | Alert chậm, thiếu owner, không rõ quyền phê duyệt |
| Cấp hạ tầng | Thiếu quota, storage, network hoặc instance |
| Truy xuất backup | Backup ở region khác, quyền hoặc network bị chặn |
| Restore dữ liệu | Database lớn, I/O chậm, thiếu parallelism |
| Replay log/PITR | Chuỗi log dài, archive thiếu hoặc replay chậm |
| Kiểm tra | Không có script consistency hoặc tiêu chí nghiệp vụ |
| Cutover | DNS, connection pool, secret hoặc replication |
| Ổn định dịch vụ | Warm-up cache, job nền, consumer và monitoring |

Đo từng giai đoạn để biết cần tối ưu ở đâu. Nếu restore chỉ mất 15 phút nhưng quyết định và cấp quyền mất 90 phút, mua storage nhanh hơn sẽ không giải quyết RTO.

## 22. Quản lý backup catalog và bằng chứng

Mỗi backup nên có manifest hoặc metadata đủ để người vận hành xác định:

- Database/cluster và môi trường nguồn.
- DBMS, phiên bản và công cụ backup.
- Thời gian bắt đầu/kết thúc và snapshot/LSN/SCN nếu có.
- Loại backup và phạm vi object.
- Backup chain/dependency cần để restore.
- Checksum, kích thước và trạng thái mã hóa.
- Retention expiry và vị trí bản sao.
- Commit/artifact changelog gần thời điểm backup.
- Kết quả restore test gần nhất.

Không đưa secret hoặc thông tin xác thực vào manifest. Bảo vệ manifest vì nó giúp attacker hiểu vị trí backup và kiến trúc phục hồi.

Giữ catalog ở một failure domain khác với database chính. Nếu catalog mất, nhóm vẫn cần cách tìm backup và dựng lại thứ tự log từ metadata được bảo vệ.

## 23. Phục hồi sau khi backup bị lỗi hoặc thiếu

Nếu một backup bị hỏng, thiếu file hoặc mất log chain:

1. Đánh dấu backup không đủ điều kiện phục hồi.
2. Không xóa các bản backup cũ còn hợp lệ.
3. Kiểm tra bản sao ở region/account khác.
4. Xác định full/base backup gần nhất còn dùng được.
5. Kiểm tra log chain từ base tới recovery target.
6. Nếu cần, chọn recovery point cũ hơn và đánh giá RPO thực tế.
7. Tạo backup mới sau khi dịch vụ ổn định.
8. Điều tra nguyên nhân hỏng/mất và sửa monitoring/retention.

Không ghép log từ các chuỗi khác nhau nếu DBMS yêu cầu sequence liên tục. Hãy dùng công cụ kiểm tra backup chain và recovery catalog của đúng DBMS.

## 24. Runbook khôi phục ngắn

**Kích hoạt**
- Ghi incident ID, database, môi trường và người chỉ huy.
- Xác định ảnh hưởng dữ liệu/ứng dụng.
- Dừng writers và pipeline migration theo kế hoạch.

**Chọn nguồn phục hồi**
- Xác minh full/base backup.
- Xác minh incremental/differential và WAL/binlog/log backup.
- Chọn recovery target và tính RPO dự kiến.
- Kiểm tra quyền, encryption key và catalog.

**Restore và xác minh**
- Restore vào instance cô lập.
- Replay log tới target.
- Kiểm tra DBMS integrity.
- Kiểm tra schema/data và DATABASECHANGELOG/LOCK.
- Dùng đúng artifact changelog và chạy validate/status.
- Kiểm thử ứng dụng, role và nghiệp vụ.

**Cutover**
- Đối chiếu giao dịch sau recovery point.
- Xác nhận downstream và secret.
- Phê duyệt chuyển traffic.
- Theo dõi metrics/logs và giữ bản hiện trạng theo chính sách.

**Kết thúc**
- Ghi RPO/RTO thực tế.
- Lưu bằng chứng backup/restore và quyết định.
- Thu hồi quyền tạm thời.
- Cập nhật runbook và action items.

## 25. Checklist chuẩn bị backup và diễn tập

### Trước khi backup

- [ ] Đã xác định database, schema, cluster và dữ liệu thuộc phạm vi.
- [ ] RPO/RTO được chủ nghiệp vụ và vận hành thống nhất.
- [ ] Chọn loại backup phù hợp với kích thước, DBMS và mục tiêu phục hồi.
- [ ] Có cơ chế snapshot nhất quán khi ứng dụng vẫn ghi dữ liệu.
- [ ] Đã tính tới DDL/migration chạy đồng thời.
- [ ] Có transaction log/WAL/binlog/archive nếu cần PITR.
- [ ] Backup có mã hóa, quyền tối thiểu và bản sao ở failure domain khác.
- [ ] Retention phù hợp chính sách và yêu cầu dữ liệu.
- [ ] Manifest ghi phiên bản DBMS/công cụ, thời gian, chain và artifact Liquibase.
- [ ] Backup job có monitoring, cảnh báo và kiểm tra dung lượng.

### Trước khi restore

- [ ] Đã chọn recovery point và hiểu lượng dữ liệu có thể mất.
- [ ] Đã xác minh full/base backup và toàn bộ log chain.
- [ ] Có encryption key, catalog, quyền và hạ tầng cần thiết.
- [ ] Môi trường restore cô lập, không gửi tác động tới downstream thật.
- [ ] Có bản lưu hiện trạng trước khi thay đổi nếu khả thi.
- [ ] Artifact changelog, SQL file và phiên bản Liquibase tương ứng đã sẵn sàng.
- [ ] Có kế hoạch xử lý DATABASECHANGELOGLOCK và session cũ.

### Sau khi restore

- [ ] DBMS hoàn tất recovery và kiểm tra integrity đạt.
- [ ] Schema, dữ liệu, owner, grants và object phụ thuộc đúng.
- [ ] DATABASECHANGELOG phù hợp với schema tại recovery point.
- [ ] DATABASECHANGELOGLOCK được xác minh, không release mù quáng.
- [ ] Liquibase validate/status chạy với artifact đúng.
- [ ] Ứng dụng và các luồng nghiệp vụ trọng yếu hoạt động.
- [ ] Giao dịch sau recovery point được đối chiếu/replay có kiểm soát.
- [ ] RPO/RTO thực tế được ghi nhận.
- [ ] Credential/quyền tạm thời được thu hồi.
- [ ] Báo cáo diễn tập và action items được lưu.

## 26. Kết luận

Chuẩn bị bản sao lưu và diễn tập khôi phục là một năng lực vận hành liên tục. Nhóm cần xác định RPO/RTO, chọn chiến lược logical/physical/snapshot và log phù hợp, bảo đảm backup nhất quán, mã hóa và có bản sao tách biệt. Sau đó phải restore thử, đo thời gian, kiểm tra dữ liệu và chứng minh ứng dụng có thể hoạt động trở lại.

Với Liquibase, phục hồi phải giữ được mối liên hệ giữa **schema thực tế, DATABASECHANGELOG, DATABASECHANGELOGLOCK và artifact changelog** tại cùng recovery point. Nếu những thành phần này lệch thời điểm, Liquibase có thể bỏ qua thay đổi còn thiếu hoặc cố chạy lại một thay đổi đã tồn tại. Vì vậy, sau restore cần đối chiếu history với schema/data trước khi validate, status hoặc update; không sửa lịch sử để che trạng thái không nhất quán.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, một quy trình backup/restore được diễn tập giúp migration có thể phục hồi, phối hợp an toàn giữa dev/test/production và giữ dịch vụ vận hành trong giới hạn RPO/RTO đã cam kết.

