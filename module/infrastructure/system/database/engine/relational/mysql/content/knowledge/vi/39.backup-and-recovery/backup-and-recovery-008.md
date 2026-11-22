# Hot/cold backup, khóa cần thiết và tính nhất quán bộ file

Sao lưu MySQL chỉ có thể phục hồi đáng tin cậy khi bản sao chứa một trạng thái cơ sở dữ liệu nhất quán. Với backup logic, tính nhất quán thường đến từ một transaction snapshot. Với backup vật lý, công cụ phải phối hợp việc sao chép các file dữ liệu với redo log và cơ chế khóa phù hợp. Cold backup đạt tính nhất quán bằng cách dừng MySQL sạch trước khi sao chép toàn bộ bộ file cần thiết.

Bài học này thuộc chương **Sao lưu và phục hồi** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền và vận hành, sao lưu là cách bảo vệ kết quả của toàn bộ hoạt động đó. Phần trọng tâm ở đây là lựa chọn hot/cold backup, hiểu khóa nào cần dùng và giữ các file thuộc cùng một điểm phục hồi.

## 1. Hot backup và cold backup

**Hot backup** được thực hiện khi máy chủ MySQL vẫn đang chạy và phục vụ ứng dụng. Người dùng có thể tiếp tục đọc hoặc ghi dữ liệu tùy phương pháp sao lưu. Cách này giảm thời gian gián đoạn, nhưng cần cơ chế giữ snapshot nhất quán hoặc phối hợp dữ liệu thay đổi trong lúc sao chép.

**Cold backup** được thực hiện sau khi MySQL đã dừng sạch. Khi không còn tiến trình ghi dữ liệu, các file có thể được sao chép như một bộ hoàn chỉnh. Cách này dễ hiểu và ít phụ thuộc vào khóa trong lúc copy, nhưng cần thời gian dừng dịch vụ.

| Tiêu chí | Hot backup | Cold backup |
|---|---|---|
| Trạng thái MySQL | Đang chạy | Đã dừng sạch |
| Ảnh hưởng dịch vụ | Có thể tiếp tục phục vụ; tùy khóa và công cụ | Phải ngừng dịch vụ trong thời gian sao lưu |
| Cách giữ nhất quán | Transaction snapshot, backup lock, global read lock hoặc công cụ vật lý có xử lý redo | Dừng sạch rồi sao chép trọn bộ file |
| Phù hợp | Hệ thống cần tính sẵn sàng cao | Hệ thống có cửa sổ bảo trì hoặc cần bản sao vật lý đơn giản |
| Rủi ro chính | DDL hoặc ghi đồng thời làm snapshot không nhất quán nếu chọn sai cơ chế | Sao chép thiếu file, khởi động lại khi copy chưa xong hoặc dừng không sạch |

Hot/cold mô tả trạng thái của máy chủ khi sao lưu. Logical/physical mô tả cách biểu diễn bản sao. Vì vậy, có thể tạo logical hot backup bằng `mysqldump`, physical hot backup bằng công cụ như Percona XtraBackup hoặc MySQL Enterprise Backup, và physical cold backup bằng cách copy datadir sau khi MySQL dừng sạch.

## 2. Logical hot backup với mysqldump

Với bảng InnoDB, `mysqldump --single-transaction` tạo một transaction snapshot để các câu lệnh đọc dữ liệu nhìn thấy cùng một trạng thái nhất quán. MySQL vẫn có thể tiếp tục nhận DML trong lúc dump. Tùy chọn `--quick` đọc và ghi từng hàng theo luồng, giúp giảm nhu cầu giữ toàn bộ kết quả trong bộ nhớ.

Ví dụ sao lưu một database:

~~~bash
mysqldump \
  --user=backup_user \
  --password \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  --databases appdb \
  > appdb.sql
~~~

Khi chạy, client yêu cầu mật khẩu tương tác. Không ghi mật khẩu trực tiếp vào câu lệnh hoặc đưa nó vào script, log hay lịch sử shell. Trong môi trường tự động hóa, dùng cơ chế quản lý thông tin xác thực được bảo vệ theo chính sách của hệ thống.

Các tùy chọn có ý nghĩa như sau:

- `--single-transaction`: tạo snapshot nhất quán cho các bảng transactional như InnoDB. Nó không làm cho MyISAM hoặc engine không transactional trở nên nhất quán.
- `--quick`: stream dữ liệu thay vì đệm toàn bộ tập kết quả trong bộ nhớ client.
- `--routines` và `--events`: đưa stored procedure/function và event vào bản dump.
- `--triggers`: yêu cầu đưa trigger vào bản dump; trigger thường được dump mặc định, nhưng ghi rõ giúp ý định dễ đọc.
- `--hex-blob`: biểu diễn dữ liệu nhị phân theo dạng hex trong SQL dump.
- `--databases appdb`: dump database được chỉ định, bao gồm câu lệnh tạo database và chọn database khi import.

### Giới hạn của transaction snapshot

`--single-transaction` dựa trên MVCC của InnoDB. Trong khi dump, tránh chạy DDL trên các bảng đang được sao lưu. Các thao tác như `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc `TRUNCATE TABLE` có thể làm dump lỗi hoặc khiến kết quả không còn đáp ứng kỳ vọng về snapshot.

Nếu database có bảng MyISAM hoặc engine không transactional, snapshot InnoDB không bảo vệ được các bảng đó. Có thể chọn một trong các hướng:

- Dừng ghi vào các bảng không transactional trong suốt thời gian sao lưu.
- Dùng khóa đọc phù hợp, ví dụ `--lock-all-tables`, nếu chấp nhận khóa ghi trong thời gian dump.
- Chuyển các bảng cần tính nhất quán sang InnoDB sau khi đánh giá đặc tính ứng dụng.
- Dùng công cụ backup hỗ trợ engine và mô hình nhất quán đang triển khai.

`--single-transaction` và `--lock-all-tables` là hai cách bảo vệ khác nhau và không tương thích khi dùng cùng nhau trong `mysqldump`. Hãy chọn tùy chọn phù hợp với engine và mức khóa có thể chấp nhận.

## 3. Các loại khóa liên quan đến backup

Khóa cần dùng phụ thuộc vào engine, cách sao lưu và mục tiêu nhất quán. Ba cơ chế thường gặp là transaction snapshot, backup lock và global read lock.

### Transaction snapshot

Với InnoDB, một transaction ở mức cô lập phù hợp có thể đọc dữ liệu tại một snapshot nhất quán mà không khóa toàn bộ bảng để ngăn DML. `mysqldump --single-transaction` sử dụng cách tiếp cận này.

Snapshot bảo vệ góc nhìn dữ liệu của transaction; nó không đóng băng cấu trúc schema. Vì vậy, cần tránh DDL ảnh hưởng các bảng trong lúc dump. Nó cũng không bảo vệ dữ liệu của engine không transactional.

### Backup lock: LOCK INSTANCE FOR BACKUP

MySQL 8.0.3 trở lên cung cấp backup lock ở cấp instance:

~~~sql
LOCK INSTANCE FOR BACKUP;

-- Công cụ backup thực hiện phần công việc cần bảo vệ.

UNLOCK INSTANCE;
~~~

Tài khoản cần quyền `BACKUP_ADMIN` để sử dụng cơ chế này. Có thể cấp quyền cho tài khoản backup theo phạm vi quản trị phù hợp:

~~~sql
GRANT BACKUP_ADMIN ON *.* TO 'backup_user'@'localhost';
~~~

Backup lock được thiết kế để ngăn các thao tác có thể làm thay đổi cấu trúc hoặc file cần cho backup vật lý, chẳng hạn một số hoạt động DDL và quản lý tablespace. Nó cho phép DML tiếp tục trong những trường hợp được MySQL hỗ trợ. Vì vậy, đây không phải là global read lock và cũng không tự tạo ra một bản sao vật lý nhất quán.

Công cụ backup vật lý vẫn phải theo dõi và áp dụng redo log để đưa các trang dữ liệu đã sao chép về một trạng thái nhất quán. Hãy dùng đúng phiên bản công cụ tương thích với phiên bản MySQL và tuân theo trình tự lock, copy, prepare mà công cụ quy định. Không tự thay thế quy trình đó bằng việc copy file thủ công.

### Global read lock: FLUSH TABLES WITH READ LOCK

Câu lệnh sau lấy global read lock:

~~~sql
FLUSH TABLES WITH READ LOCK;

-- Thực hiện thao tác cần điểm nhất quán toàn cục.

UNLOCK TABLES;
~~~

Lệnh này flush và khóa bảng để ngăn các thao tác ghi trong thời gian giữ khóa. Nó ảnh hưởng rộng tới hoạt động ghi của máy chủ, vì vậy không nên giữ khóa trong suốt một lần copy vật lý kéo dài nếu có thể tạo storage snapshot nhanh.

Một mô hình thường gặp là lấy khóa, tạo snapshot lưu trữ tại một thời điểm nhất quán, ghi nhận vị trí binary log hoặc GTID nếu cần, rồi giải phóng khóa ngay. Việc tạo snapshot phải được hệ thống lưu trữ hỗ trợ và phải bao phủ đầy đủ các volume chứa dữ liệu liên quan.

Global read lock hữu ích khi cần đồng bộ trạng thái nhiều engine hoặc ghi nhận tọa độ replication/binlog. Tuy nhiên, nó làm giảm khả năng ghi trong thời gian khóa. Lên lịch, đo thời gian giữ khóa và theo dõi tác động tới ứng dụng trước khi áp dụng trên hệ thống thật.

### So sánh nhanh

| Cơ chế | Ngăn DML? | Ngăn DDL ảnh hưởng file? | Phạm vi sử dụng |
|---|---|---|---|
| InnoDB transaction snapshot | Không khóa DML toàn cục | Không tự ngăn DDL | Logical dump nhất quán của InnoDB |
| `LOCK INSTANCE FOR BACKUP` | Thông thường cho phép DML | Có, với các thao tác được MySQL quy định | Công cụ physical backup trên phiên bản hỗ trợ |
| `FLUSH TABLES WITH READ LOCK` | Có, trên phạm vi toàn cục | Có trong thời gian giữ khóa | Snapshot toàn cục, tọa độ binlog và engine cần khóa |

Không có một câu lệnh khóa duy nhất phù hợp cho mọi loại backup. Hãy chọn dựa trên storage engine, công cụ backup, yêu cầu RPO/RTO và mức gián đoạn có thể chấp nhận.

## 4. Physical hot backup và vai trò của redo log

Physical backup sao chép các file dữ liệu ở định dạng MySQL/InnoDB. Công cụ như Percona XtraBackup hoặc MySQL Enterprise Backup có thể đọc file trong khi máy chủ vẫn hoạt động. Trong lúc copy, InnoDB có thể thay đổi trang dữ liệu và ghi redo log. Vì vậy, một bộ file vừa được copy không nhất thiết đã tự nhất quán ngay tại thời điểm kết thúc.

Một quy trình physical hot backup thường có các bước:

1. Khởi tạo phiên backup và áp dụng khóa cần thiết để bảo vệ metadata/file theo yêu cầu của công cụ.
2. Sao chép các file dữ liệu trong khi ghi nhận redo log phát sinh.
3. Kết thúc giai đoạn copy và lưu lại thông tin điểm backup, chẳng hạn GTID hoặc vị trí binary log khi công cụ hỗ trợ.
4. Chạy bước **prepare** để áp dụng redo cần thiết, phục hồi các trang dữ liệu về một trạng thái nhất quán.
5. Kiểm tra kết quả backup và chỉ sau đó mới dùng nó làm nguồn restore.

Ví dụ bước prepare với Percona XtraBackup:

~~~bash
xtrabackup --prepare --target-dir=/backup/mysql/full
~~~

Đường dẫn chỉ là ví dụ; dùng đúng lệnh và tùy chọn theo phiên bản XtraBackup đang triển khai. Một thư mục backup chưa qua bước prepare có thể chưa ở trạng thái sẵn sàng để restore. Không bỏ qua bước này chỉ vì các file đã xuất hiện đầy đủ.

Redo log chứa thông tin cần thiết để phục hồi các thay đổi InnoDB. Công cụ backup vật lý theo dõi redo trong lúc copy và dùng nó để xử lý sự khác biệt giữa thời điểm sao chép các trang. Không xóa, thay thế hoặc bỏ sót redo log theo cách thủ công.

## 5. Cold physical backup: dừng sạch rồi copy

Cold backup vật lý là lựa chọn đơn giản khi hệ thống có cửa sổ bảo trì. Quy trình cơ bản:

1. Thông báo và chuyển ứng dụng sang chế độ bảo trì; dừng các job có thể ghi vào database.
2. Dừng MySQL bằng cơ chế quản trị dịch vụ hoặc lệnh shutdown được hỗ trợ.
3. Xác minh tiến trình MySQL đã kết thúc và quá trình shutdown hoàn tất bình thường.
4. Sao chép toàn bộ datadir cùng các file nằm ngoài datadir nhưng thuộc bộ dữ liệu cần phục hồi.
5. Bảo toàn quyền sở hữu, permission, symbolic link và metadata file theo yêu cầu của hệ điều hành.
6. Ghi lại phiên bản MySQL, cấu hình liên quan, plugin, keyring và thông tin vị trí binary log/GTID nếu cần phục hồi theo thời điểm.
7. Xác minh bản sao đã hoàn tất trước khi khởi động lại MySQL và mở ứng dụng.

Với cold backup, không cần giữ `LOCK INSTANCE FOR BACKUP` hay `FLUSH TABLES WITH READ LOCK` trong lúc copy vì MySQL đã dừng. Điều kiện quan trọng là shutdown phải sạch và bộ file được sao chép đầy đủ.

Không copy một phần datadir rồi cho rằng có thể ghép với file từ một lần backup khác. Cũng không khởi động MySQL trong lúc tiến trình copy vẫn đang đọc các file nguồn; nếu server tiếp tục ghi, bản sao có thể chứa những file thuộc các thời điểm khác nhau.

## 6. Tính nhất quán của bộ file

Một bản physical backup không chỉ là tập hợp file có cùng tên. Các file phải cùng mô tả một trạng thái cơ sở dữ liệu có thể phục hồi. MySQL có thể sử dụng nhiều loại file, tùy cấu hình và tính năng đang bật:

- **System tablespace:** chứa các cấu trúc dữ liệu nội bộ của InnoDB. Data dictionary có vị trí lưu trữ phụ thuộc phiên bản; ở MySQL 8.0, dữ liệu dictionary được lưu trong các file/tablespace riêng, bao gồm `mysql.ibd`.
- **File tablespace theo bảng:** thường là các file `.ibd` khi cấu hình dùng file-per-table.
- **Undo tablespace:** lưu thông tin phục vụ rollback và MVCC; vị trí có thể phụ thuộc cấu hình và phiên bản.
- **Redo log:** hỗ trợ crash recovery và hoàn tất các thay đổi cần thiết.
- **Binary log:** cần khi thực hiện point-in-time recovery hoặc tái tạo chuỗi sự kiện sau full backup.
- **Relay log và metadata replication:** có thể cần để tiếp tục hoặc chẩn đoán trạng thái replica.
- **Tablespace đặt ngoài datadir, keyring và thành phần mã hóa:** phải được bảo vệ cùng bản sao nếu database sử dụng chúng.

Danh sách cụ thể phụ thuộc phiên bản MySQL, engine, cấu hình và công cụ backup. Hãy dựa vào tài liệu của phiên bản đang chạy để xác định chính xác các file và metadata cần lưu.

### Vì sao không được trộn file từ nhiều thời điểm?

Giả sử một bảng có tablespace riêng và InnoDB đang cập nhật dữ liệu:

- File tablespace được copy lúc 10:00.
- Redo log bị bỏ qua hoặc lấy từ một bản sao khác lúc 10:05.
- Metadata hoặc system tablespace được copy lúc 10:10.

Ba thành phần có thể không mô tả cùng một trạng thái. MySQL có thể không khởi động được, không thể hoàn tất crash recovery hoặc đưa ra dữ liệu không nhất quán.

Với physical hot backup, công cụ giải quyết vấn đề này bằng cách ghi nhận redo và prepare bộ file. Với cold backup, dừng sạch MySQL trước khi copy giúp các file nguồn ổn định trong suốt quá trình sao chép. Với storage snapshot, cần snapshot nhất quán trên tất cả volume liên quan tại cùng một điểm thời gian; snapshot riêng lẻ được tạo lệch thời điểm có thể không đủ.

### Những lỗi thường gặp

| Lỗi | Hậu quả có thể xảy ra | Cách phòng tránh |
|---|---|---|
| Copy datadir khi MySQL vẫn chạy bằng lệnh copy thông thường | Các file được chụp ở thời điểm khác nhau, thiếu redo cần thiết | Dùng công cụ physical backup có hỗ trợ InnoDB hoặc dừng sạch trước khi copy |
| Chỉ copy các file `.ibd` | Thiếu metadata, tablespace hệ thống, undo hoặc redo | Sao lưu toàn bộ bộ file theo hướng dẫn công cụ |
| Bỏ redo log khỏi physical hot backup | Không thể prepare hoặc phục hồi đúng trạng thái | Để công cụ theo dõi và lưu redo |
| Copy datadir nhưng bỏ qua tablespace ngoài datadir | Thiếu bảng hoặc tablespace khi restore | Kiểm kê đường dẫn dữ liệu và snapshot tất cả volume liên quan |
| Dùng file keyring khác hoặc thiếu keyring | Không giải mã được dữ liệu mã hóa | Sao lưu và kiểm tra quy trình phục hồi keyring an toàn |
| Dump InnoDB bằng snapshot nhưng có DDL đồng thời | Dump có thể lỗi hoặc không đạt tính nhất quán mong muốn | Tạm dừng DDL trong cửa sổ dump |
| Dùng `--single-transaction` cho MyISAM mà không khóa | Các bảng có thể phản ánh thời điểm khác nhau | Khóa đọc hoặc dừng ghi cho engine không transactional |
| Chỉ kiểm tra file tồn tại | Bản backup có thể không restore được | Thử restore trên máy độc lập và kiểm tra dữ liệu |

## 7. Kết hợp full backup với binary log

Full backup cung cấp điểm khởi đầu để phục hồi. Nếu cần khôi phục đến một thời điểm sau đó, hãy lưu binary log liên tục kể từ điểm backup. Quy trình point-in-time recovery thường là:

1. Restore full backup đã được kiểm tra.
2. Xác định GTID hoặc vị trí binary log tương ứng với thời điểm backup.
3. Phát lại các sự kiện binary log từ sau điểm đó đến trước thời điểm cần dừng.
4. Kiểm tra dữ liệu và xác nhận ứng dụng hoạt động đúng.

Không dùng binary log từ một máy chủ hoặc một chuỗi replication không liên quan mà không xác minh nguồn và thứ tự. Nếu backup tool ghi lại tọa độ binlog/GTID, lưu metadata đó cùng backup. Bảo vệ binary log và bản backup theo cùng chính sách lưu trữ, quyền truy cập và mã hóa phù hợp.

## 8. Quy trình chọn phương pháp

Có thể dùng các câu hỏi sau để quyết định cách sao lưu:

| Điều kiện | Phương án thường phù hợp |
|---|---|
| Các bảng đều là InnoDB, cần bản dump dễ đọc và restore logic | `mysqldump --single-transaction --quick` |
| Cần backup vật lý khi dịch vụ vẫn chạy | Công cụ physical backup hỗ trợ phiên bản MySQL, redo và backup lock phù hợp |
| Có bảng không transactional và chấp nhận khóa ghi | Dùng khóa đọc phù hợp hoặc dừng ghi trong thời gian dump |
| Có cửa sổ bảo trì đủ dài | Dừng sạch MySQL, copy toàn bộ bộ file vật lý |
| Cần snapshot lưu trữ rất nhanh | Phối hợp khóa/flush, snapshot đồng bộ mọi volume và lưu tọa độ phục hồi |
| Cần khôi phục đến một thời điểm cụ thể | Full backup kèm binary log/GTID liên tục |

Trước khi triển khai, xác định RPO (mức mất dữ liệu tối đa có thể chấp nhận) và RTO (thời gian phục hồi tối đa). Sau đó chọn chu kỳ full/incremental backup, thời gian lưu giữ, nơi lưu bản sao và thời gian thử restore. Bản backup chỉ hữu ích khi thời điểm phục hồi đáp ứng yêu cầu nghiệp vụ.

## 9. Xác minh backup trước khi coi là hoàn thành

Một lệnh backup kết thúc không có lỗi chưa chứng minh rằng dữ liệu có thể phục hồi. Hãy kiểm tra:

- Mã thoát của công cụ, log và thông báo lỗi/cảnh báo.
- Kích thước file, số lượng file, checksum và dung lượng lưu trữ.
- Metadata backup: phiên bản MySQL, thời điểm, database, GTID/binlog, tùy chọn và trạng thái prepare.
- Sự hiện diện của file ngoài datadir, keyring hoặc dữ liệu mã hóa cần thiết.
- Khả năng restore trên một instance thử nghiệm có phiên bản tương thích.
- Số lượng bản ghi, cấu trúc bảng, trigger, routine, event, quyền truy cập và các truy vấn nghiệp vụ quan trọng.
- Thời gian thực tế để hoàn thành restore và đưa ứng dụng hoạt động trở lại.

Nên thử phục hồi định kỳ trên môi trường cô lập. Chỉ kiểm tra checksum hoặc mở file dump không thay thế được một lần restore thực tế.

## 10. Ghi nhớ

- Hot backup giữ dịch vụ chạy, nhưng cần snapshot hoặc công cụ biết xử lý thay đổi đồng thời.
- Cold backup cần dừng MySQL sạch và sao chép đầy đủ bộ file liên quan.
- `--single-transaction` phù hợp với InnoDB; không bảo vệ bảng không transactional và không ngăn DDL.
- `LOCK INSTANCE FOR BACKUP` bảo vệ cấu trúc/file trước các thao tác được MySQL quy định; nó không đóng băng DML và không thay thế bước xử lý redo.
- `FLUSH TABLES WITH READ LOCK` tạo global read lock, có thể ảnh hưởng ghi trên toàn máy chủ; hãy giảm tối đa thời gian giữ khóa.
- Physical hot backup phải lưu đủ file và redo, sau đó prepare trước khi restore.
- Không trộn data file, redo, metadata, tablespace ngoài datadir hoặc keyring từ những điểm thời gian không tương thích.
- Backup chỉ được xem là đáng tin khi đã thử restore và kiểm tra kết quả.

Hãy luôn xác định engine, loại backup, khóa cần thiết và danh sách file trước khi chạy. Khi bộ file cùng phản ánh một trạng thái phục hồi và quy trình restore đã được thử nghiệm, bản sao mới có giá trị vận hành thực tế.

