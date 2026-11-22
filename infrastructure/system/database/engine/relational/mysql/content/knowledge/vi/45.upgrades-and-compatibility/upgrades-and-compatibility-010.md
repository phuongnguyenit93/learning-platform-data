# Sao lưu trước thay đổi, diễn tập phục hồi và giới hạn downgrade

Trong module **DATABASE_MYSQL**, thay đổi schema, nâng cấp phiên bản hoặc thay thế máy chủ có thể tác động đến dữ liệu và khả năng vận hành của toàn hệ thống. Một câu lệnh DDL có thể hoàn tất nhưng ứng dụng vẫn lỗi vì view, trigger, routine hoặc dữ liệu phụ thuộc đã thay đổi. Một lần nâng cấp có thể làm thay đổi data dictionary, metadata hoặc định dạng lưu trữ theo cách phiên bản cũ không còn đọc được.

Vì vậy, trước thay đổi quan trọng cần có bản sao lưu có thể khôi phục, kế hoạch phục hồi theo mốc thời gian và một lần diễn tập trên môi trường cô lập. Bài học này trình bày cách chọn phương pháp backup, bảo toàn binary log, phục hồi đến một thời điểm, kiểm tra kết quả và đánh giá giới hạn khi muốn quay về phiên bản MySQL cũ.

Trong phạm vi DATABASE_MYSQL, chủ đề này kết nối với thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời. Việc diễn tập phục hồi cũng dựa trên khả năng đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và nguyên tắc

Sau bài học, bạn có thể:

- Xác định dữ liệu, cấu hình và đối tượng cần bảo vệ trước khi thay đổi schema hoặc nâng cấp.
- Phân biệt backup logic, backup vật lý, snapshot lưu trữ và binary log.
- Tạo bản backup có metadata cần thiết cho point-in-time recovery (PITR).
- Phục hồi backup vào một máy chủ cô lập và phát lại binary log đến mốc đã chọn.
- Diễn tập các tình huống lỗi, đo RPO/RTO và xác minh dữ liệu sau restore.
- Giải thích vì sao rollback ứng dụng và downgrade máy chủ là hai việc khác nhau.
- Chọn phương án phục hồi an toàn khi phiên bản mới không thể downgrade tại chỗ.

Một bản backup chỉ có giá trị vận hành khi có thể khôi phục được. File đã tạo, kích thước lớn hoặc checksum hợp lệ chưa chứng minh rằng MySQL có thể mở dữ liệu, ứng dụng có thể truy cập và các ràng buộc nghiệp vụ vẫn đúng.

Trước khi thực hiện thay đổi, cần trả lời bốn câu hỏi:

1. Nếu thao tác thất bại, cần khôi phục dữ liệu về thời điểm nào?
2. Mức mất dữ liệu tối đa chấp nhận được là bao nhiêu?
3. Mất bao lâu để khôi phục và đưa dịch vụ hoạt động trở lại?
4. Phiên bản MySQL cũ có thể đọc dữ liệu sau thay đổi hay cần phục hồi một bản backup riêng?

## 2. RPO, RTO và phạm vi phục hồi

**RPO (Recovery Point Objective)** là khoảng dữ liệu tối đa có thể mất, tính theo thời gian hoặc mốc giao dịch. Nếu RPO là 5 phút, hệ thống cần có khả năng phục hồi dữ liệu đến một mốc không cũ hơn quá 5 phút trước sự cố.

**RTO (Recovery Time Objective)** là thời gian tối đa để khôi phục dịch vụ đến trạng thái có thể vận hành. RTO cần tính cả thời gian chuẩn bị máy chủ, restore backup, phát lại binary log, kiểm tra dữ liệu, chuyển endpoint và mở lại traffic.

| Mục tiêu | Câu hỏi cần trả lời | Biện pháp thường dùng |
|---|---|---|
| RPO | Có thể mất tối đa bao nhiêu giao dịch? | Full backup định kỳ, binary log lưu liên tục, PITR |
| RTO | Cần bao lâu để dịch vụ hoạt động lại? | Backup có tốc độ restore phù hợp, tài nguyên dự phòng, runbook đã diễn tập |
| Phạm vi | Khôi phục cả instance, schema, bảng hay một số bản ghi? | Backup phù hợp và môi trường restore riêng |
| Tính nhất quán | Dữ liệu có giữ đúng ranh giới transaction và quan hệ nghiệp vụ không? | Snapshot nhất quán, phát lại log đúng thứ tự, kiểm tra invariant |

Không nên chọn chu kỳ backup chỉ dựa trên dung lượng hoặc chi phí lưu trữ. Chu kỳ cần phù hợp với RPO, tốc độ phát sinh dữ liệu và thời gian cần thiết để restore. Nếu binary log chỉ được giữ trong 24 giờ nhưng sự cố có thể chỉ được phát hiện sau 2 ngày, PITR sẽ không đạt mục tiêu.

## 3. Những gì cần sao lưu trước khi thay đổi

### 3.1. Dữ liệu và cấu trúc

Trước khi đổi schema hoặc nâng cấp, kiểm kê:

- Database, table, partition, index, constraint và tablespace.
- View, trigger, stored procedure, function và event.
- Dữ liệu nghiệp vụ, dữ liệu tham chiếu và bảng audit/ledger.
- Charset, collation, SQL mode, time zone và các biến cấu hình quan trọng.
- User, role, grant, authentication plugin và định nghĩa quyền.
- Cấu hình replication, GTID, binary log và trạng thái cluster.
- Plugin, component, keyring, chứng thư TLS và khóa mã hóa cần thiết.
- File cấu hình máy chủ, tham số khởi động, service và script vận hành.

Hướng dẫn nâng cấp MySQL 8.4 yêu cầu bản backup trước nâng cấp bao gồm cả schema hệ thống **mysql**, nơi lưu data dictionary và system tables. Điều này quan trọng khi cần phục hồi toàn bộ instance về phiên bản trước nâng cấp. Tuy nhiên, khi chuyển dữ liệu logic sang một phiên bản khác, không được mặc định import nguyên các bảng hệ thống từ phiên bản nguồn; hãy dùng quy trình tương thích để tạo lại user và quyền.

Không phải tất cả các mục trên đều nằm trong một bản dump dữ liệu. Ví dụ, file cấu hình, chứng thư, khóa mã hóa, secret, plugin bên ngoài và khóa keyring cần được bảo vệ theo quy trình riêng.

### 3.2. User, role và quyền

Tài khoản MySQL là một phần của khả năng khôi phục ứng dụng. Nếu dữ liệu đã restore nhưng tài khoản kết nối, role hoặc quyền bị thiếu, dịch vụ vẫn không hoạt động.

Có thể kiểm tra tài khoản và quyền bằng các lệnh:

~~~sql
SHOW CREATE USER 'app_user'@'%';
SHOW GRANTS FOR 'app_user'@'%';
~~~

Lưu lại định nghĩa user, role, grant và chính sách xác thực bằng phương pháp phù hợp với phiên bản. Không sao chép thủ công các bảng hệ thống của schema mysql giữa những phiên bản không tương thích. Khi phục hồi sang phiên bản khác, hãy tạo lại tài khoản bằng câu lệnh SQL được phiên bản đích hỗ trợ hoặc công cụ xuất user tương thích.

### 3.3. Cấu hình và khóa mã hóa

Nếu dữ liệu dùng tablespace encryption, keyring hoặc mã hóa backup, cần bảo vệ cả khóa và metadata cần thiết để giải mã. Backup có dữ liệu mã hóa nhưng mất keyring có thể không khôi phục được.

Lưu trữ riêng, có kiểm soát truy cập:

- File cấu hình MySQL và tham số khởi động.
- Keyring và khóa mã hóa theo quy trình bảo mật.
- Chứng thư CA, certificate và private key phục vụ kết nối TLS.
- Plugin hoặc component cần thiết để mở dữ liệu.
- Thông tin phiên bản và checksum của công cụ backup.

Không ghi secret hoặc private key vào repository, tài liệu chia sẻ hay log của job backup. Kiểm tra quy trình khôi phục khóa trong một lần diễn tập riêng.

## 4. Chọn phương pháp backup

Có ba nhóm phương pháp thường gặp. Chúng có thể được kết hợp để đạt mục tiêu RPO/RTO.

| Phương pháp | Nội dung | Ưu điểm | Giới hạn cần lưu ý |
|---|---|---|---|
| Logical backup | Xuất DDL và dữ liệu thành SQL hoặc các file dump | Linh hoạt, dễ chuyển dữ liệu giữa máy chủ tương thích | Restore có thể chậm với dữ liệu lớn; cần kiểm tra tương thích schema |
| Physical backup | Sao chép dữ liệu vật lý và metadata cần thiết bằng công cụ backup | Restore thường nhanh hơn với tập dữ liệu lớn | Phụ thuộc phiên bản, nền tảng, công cụ và quy trình prepare/restore |
| Storage snapshot | Snapshot volume hoặc filesystem chứa dữ liệu | Có thể tạo nhanh, thuận tiện cho lưu trữ lớn | Phải bảo đảm snapshot nhất quán; snapshot đơn thuần có thể chỉ crash-consistent |
| Binary log archive | Lưu các thay đổi sau backup nền | Hỗ trợ PITR và phục hồi đến mốc giao dịch | Không thay thế full backup; cần chuỗi log liên tục và đúng thứ tự |

### 4.1. Logical backup với mysqldump

Ví dụ dump một schema InnoDB trước khi thay đổi:

~~~bash
mysqldump --login-path=backup \
  --single-transaction --quick \
  --source-data=2 \
  --routines --events --triggers --hex-blob \
  --databases appdb \
  > appdb-before-change.sql
~~~

Ý nghĩa các tùy chọn:

- **--single-transaction** tạo snapshot nhất quán cho các bảng transactional như InnoDB.
- **--quick** đọc hàng theo luồng, tránh tải toàn bộ bảng vào bộ nhớ client.
- **--source-data=2** ghi tọa độ binary log tương ứng vào dump dưới dạng chú thích, hữu ích cho PITR hoặc replication theo file/position.
- **--routines**, **--events**, **--triggers** đưa các đối tượng tương ứng vào bản dump.
- **--hex-blob** xuất dữ liệu nhị phân theo dạng an toàn cho SQL.

**--single-transaction** không bảo đảm snapshot nhất quán cho bảng không hỗ trợ transaction. Trong lúc dump, tránh chạy DDL như ALTER TABLE, DROP TABLE, RENAME TABLE hoặc TRUNCATE TABLE trên các bảng liên quan; DDL đồng thời có thể làm dump không nhất quán hoặc thất bại.

Khi dùng **--source-data**, binary log phải được bật và tài khoản cần quyền phù hợp để lấy trạng thái log. Công cụ có thể cần global read lock trong một khoảng ngắn để chụp tọa độ nhất quán. Kiểm tra mã thoát của lệnh, phần đầu file dump và log công cụ trước khi coi backup là hoàn tất.

Ví dụ này chỉ dump schema appdb; nó không tự bảo vệ toàn bộ cấu hình máy chủ, khóa mã hóa, file cấu hình hoặc mọi tài khoản của hệ thống. Với backup toàn instance trước nâng cấp, chọn phương pháp bao gồm schema hệ thống mysql và các database nghiệp vụ.

### 4.2. Logical backup với MySQL Shell

Với dữ liệu lớn, MySQL Shell cung cấp các tiện ích dump/load có khả năng chia chunk và chạy nhiều worker:

~~~javascript
util.dumpSchemas(
  ['appdb'],
  '/backup/appdb-before-change',
  {
    threads: 8,
    bytesPerChunk: '128M',
    consistent: true,
    checksum: true
  }
);
~~~

Có thể dump toàn instance bằng **util.dumpInstance()** khi phạm vi backup cần bao gồm nhiều schema và đối tượng cấp instance. Hãy chọn đúng phạm vi user và metadata theo tài liệu của phiên bản MySQL Shell đang dùng.

Một số điểm cần kiểm tra:

- Snapshot có nhất quán đối với tất cả engine được sử dụng không?
- Dump có metadata GTID và tọa độ binary log tương ứng không?
- Tất cả chunk và file metadata đã được tạo đầy đủ chưa?
- Checksum có được kiểm tra khi dump và load không?
- Tài khoản dump có đủ quyền nhưng vẫn theo nguyên tắc tối thiểu không?
- Vùng backup có đủ dung lượng và được chuyển đến nơi lưu trữ độc lập không?

Số worker và kích thước chunk cần được điều chỉnh theo CPU, I/O, mạng và tải production. Tăng worker có thể làm nguồn bị quá tải hoặc khiến các truy vấn nghiệp vụ chậm hơn.

### 4.3. Physical backup và storage snapshot

Với tập dữ liệu lớn, công cụ physical backup có thể giảm thời gian restore. Dùng công cụ được hỗ trợ cho đúng phiên bản MySQL, hệ điều hành và storage engine; ví dụ MySQL Enterprise Backup hoặc một công cụ tương thích như Percona XtraBackup theo ma trận hỗ trợ của nhà cung cấp.

Một quy trình physical backup thường gồm:

1. Chạy full backup ban đầu.
2. Chạy incremental backup theo lịch nếu công cụ hỗ trợ.
3. Lưu metadata về phiên bản, GTID và tọa độ binary log.
4. Chạy bước prepare/apply-log theo yêu cầu công cụ.
5. Chuyển backup đến vùng lưu trữ độc lập.
6. Thực hiện restore thử nghiệm trên máy chủ tương thích.

Không sao chép trực tiếp thư mục data directory của một MySQL Server đang chạy rồi coi đó là backup nhất quán. Storage snapshot cần được phối hợp với cơ chế flush/quiesce hoặc công cụ hỗ trợ snapshot của hệ thống để bảo đảm tính nhất quán. Snapshot chỉ crash-consistent vẫn cần được kiểm tra bằng quy trình phục hồi thực tế.

Không dùng physical backup của phiên bản mới để mở bằng phiên bản cũ nếu tài liệu MySQL và công cụ không xác nhận đường downgrade đó được hỗ trợ.

## 5. Binary log và point-in-time recovery

### 5.1. Vì sao backup cần đi cùng binary log?

Full backup phản ánh trạng thái dữ liệu tại một mốc. Các giao dịch sau mốc đó được ghi trong binary log. Khi kết hợp backup nền với chuỗi binary log liên tục, có thể phát lại thay đổi để phục hồi đến một thời điểm cụ thể.

Kiểm tra cấu hình và trạng thái:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOG STATUS;
SHOW BINARY LOGS;
~~~

Lưu ý:

- **log_bin** phải bật nếu cần lưu binary log.
- Tọa độ file/position hoặc GTID set phải được ghi lại cùng backup.
- Phải lưu đủ các file log liên tiếp từ mốc backup đến mốc phục hồi.
- Không để chính sách purge xóa log trước khi backup hết thời hạn PITR.
- Nên sao chép binary log sang nơi lưu trữ độc lập để bảo vệ trước sự cố mất máy chủ.

GTID giúp nhận diện giao dịch và theo dõi tập giao dịch đã thực thi. File/position xác định vị trí sự kiện trong một file binary log cụ thể. Chọn một cách quản lý mốc phục hồi nhất quán và ghi nhận metadata ngay khi backup hoàn tất.

### 5.2. Phát lại log đến mốc cần thiết

Giả sử backup được tạo tại tọa độ đã ghi nhận, sau đó một câu lệnh DROP TABLE chạy nhầm lúc 14:35. Mục tiêu là khôi phục trạng thái ngay trước sự kiện đó.

Có thể dùng **mysqlbinlog** để đọc các file log theo thứ tự và giới hạn phạm vi phát lại:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 14:34:59" \
  /backup/mysql-bin.000123 \
  /backup/mysql-bin.000124 \
  > /restore/replay-before-error.sql
~~~

Ví dụ chỉ minh họa cách tạo file log phát lại; cần thay tọa độ, thời điểm, tên file và múi giờ bằng metadata thực tế. Với sự cố cần độ chính xác cao, hãy xác định vị trí event và ranh giới transaction thay vì dựa duy nhất vào timestamp.

Trước khi thực thi:

- Kiểm tra các file log liên tục và đúng thứ tự.
- Xác định event gây lỗi và mốc dừng trước event đó.
- Kiểm tra GTID, BEGIN, COMMIT/Xid và end_log_pos.
- Đọc file output để bảo đảm không phát lại giao dịch ngoài phạm vi.
- Thử trên bản restore cô lập trước khi áp dụng vào môi trường phục hồi chính.

Sau khi kiểm tra, có thể phát lại vào máy chủ phục hồi:

~~~bash
mysql --login-path=recovery < /restore/replay-before-error.sql
~~~

Không phát lại trực tiếp trên production khi chưa biết chính xác nội dung và mốc dừng. DDL thường có implicit commit; không thể dựa vào ROLLBACK để hoàn tác một lệnh DROP TABLE đã commit.

### 5.3. Bảo toàn chuỗi log

Một chuỗi binary log thiếu file hoặc thiếu đoạn giao dịch sẽ làm PITR không thể đi đến mốc mong muốn. Cần có quy trình:

- Lưu trữ file log ngoài máy chủ nguồn.
- Ghi manifest gồm tên file, kích thước, checksum và thứ tự.
- Theo dõi thời gian retention và dung lượng archive.
- Xác minh file log có thể đọc được bằng mysqlbinlog.
- Bảo vệ quyền truy cập vì binary log có thể chứa dữ liệu nhạy cảm.
- Không purge log chỉ dựa vào tuổi file nếu còn replica hoặc quy trình PITR cần dùng.

## 6. Backup trước thay đổi schema hoặc nâng cấp

### 6.1. Chốt mốc trước thay đổi

Trước một thay đổi có rủi ro như DROP COLUMN, đổi kiểu dữ liệu, thay đổi partition, rebuild bảng hoặc nâng cấp phiên bản:

1. Xác định phạm vi ảnh hưởng và dữ liệu có thể mất hoặc chuyển đổi.
2. Chọn backup full hoặc logical/physical phù hợp.
3. Ghi GTID set hoặc tọa độ binary log.
4. Lưu cấu hình, tài khoản, quyền, khóa và plugin cần thiết.
5. Xác minh backup và binary log đã được lưu ở nơi độc lập.
6. Ghi nhận phiên bản MySQL, phiên bản công cụ và thời điểm backup.
7. Chạy restore rehearsal trên môi trường cô lập.

Không chỉ tạo backup ngay trước lệnh DDL. Cần có thời gian kiểm tra restore trước khi bắt đầu thay đổi. Nếu lần restore thử nghiệm thất bại, hãy sửa quy trình backup trước khi thực hiện thao tác không dễ đảo ngược.

### 6.2. Diễn tập migration trên bản sao

Dùng một bản clone hoặc môi trường staging có cấu trúc và kích thước gần production:

- Restore backup nền.
- Phát lại binary log đến mốc kiểm tra.
- Chạy migration schema hoặc nâng cấp phiên bản.
- Chạy smoke test ứng dụng và truy vấn quan trọng.
- Kiểm tra dữ liệu, constraint, index, view, trigger và routine.
- Đo thời gian DDL, thời gian restore và tác động tài nguyên.
- Thử phương án phục hồi khi migration lỗi giữa chừng.

Một migration chạy thành công trên cơ sở dữ liệu thử nghiệm nhỏ chưa chứng minh sẽ hoàn tất trong thời gian chấp nhận được trên production. Kích thước dữ liệu, độ phân mảnh, index, metadata lock và tải đồng thời có thể làm thay đổi đáng kể thời gian thực thi.

### 6.3. DDL không phải lúc nào cũng rollback được

Nhiều câu lệnh DDL trong MySQL có implicit commit. Atomic DDL trong các phiên bản hỗ trợ giúp một số thao tác được bảo vệ tốt hơn trước crash, nhưng không có nghĩa người dùng có thể chạy ROLLBACK để khôi phục trạng thái trước DDL sau khi câu lệnh đã hoàn tất.

Ví dụ:

~~~sql
ALTER TABLE appdb.orders
  DROP COLUMN legacy_code;
~~~

Nếu lệnh hoàn tất và ứng dụng phát hiện vẫn cần dữ liệu legacy_code, một câu ROLLBACK không khôi phục được cột và giá trị đã xóa. Cần restore backup hoặc tái tạo dữ liệu từ nguồn khác, sau đó đối soát các giao dịch phát sinh kể từ mốc backup.

Với thay đổi không thể đảo ngược, nên xem backup và khả năng restore là một phần của kế hoạch triển khai, không phải bước khắc phục sau khi sự cố xảy ra.

## 7. Diễn tập phục hồi trên môi trường cô lập

### 7.1. Chuẩn bị môi trường restore

Môi trường diễn tập cần:

- Máy chủ MySQL tương thích với phiên bản backup và công cụ restore.
- Dung lượng đủ cho data, temporary files, relay/binlog và file backup.
- Mạng cô lập hoặc firewall ngăn ứng dụng production kết nối nhầm.
- Tài khoản phục hồi riêng, không dùng credential production không cần thiết.
- Keyring, plugin, certificate và cấu hình cần thiết để mở dữ liệu.
- Endpoint và DNS riêng, dễ nhận biết là môi trường thử nghiệm.
- Nơi lưu log và kết quả kiểm tra.

Không restore đè lên máy chủ production chỉ để kiểm tra backup. Việc diễn tập cần có khả năng lặp lại mà không làm ảnh hưởng dữ liệu thật.

### 7.2. Trình tự restore

Một runbook tổng quát:

1. Cấp phát máy chủ phục hồi và cài đúng phiên bản MySQL mục tiêu.
2. Áp dụng cấu hình tương thích, plugin, keyring và quyền filesystem.
3. Restore full backup bằng công cụ tương ứng.
4. Với physical backup, thực hiện bước prepare/restore theo tài liệu công cụ.
5. Kiểm tra MySQL khởi động và mở được tất cả tablespace.
6. Xác minh database, table, index, view, trigger, routine và user cần thiết.
7. Phát lại binary log từ tọa độ backup đến mốc phục hồi.
8. Chạy kiểm tra dữ liệu và invariant nghiệp vụ.
9. Chạy smoke test bằng tài khoản ứng dụng thử nghiệm.
10. Ghi thời gian từng bước, lỗi phát sinh và kết quả cuối.

Nếu restore backup logic, kiểm tra mã thoát và log của client; một file SQL có thể được nạp một phần trước khi lỗi. Nếu restore physical, kiểm tra log prepare, log server và trạng thái tablespace sau khi khởi động.

### 7.3. Kiểm tra dữ liệu sau restore

Kiểm tra ở nhiều lớp:

**Cấu trúc**

- Đủ schema, bảng, partition, index, constraint.
- Định nghĩa cột, charset, collation và engine đúng.
- View, trigger, routine và event cần thiết hoạt động.
- User, role và grant đúng phạm vi.

**Dữ liệu**

- Số hàng của các bảng trọng yếu.
- Tổng tiền, số dư, tổng đơn hàng hoặc số lượng nghiệp vụ.
- Giá trị min/max và phạm vi thời gian.
- Bản ghi khóa ngoại mồ côi hoặc khóa duy nhất trùng.
- Checksum hoặc so sánh dữ liệu theo chunk khi công cụ hỗ trợ.

**Nghiệp vụ**

- Có thể đọc và cập nhật bản ghi mẫu bằng ứng dụng.
- Trạng thái đơn hàng, thanh toán và audit khớp nhau.
- Job nền, event và consumer hoạt động đúng.
- Không có bản ghi bị mất do phát lại thiếu hoặc lặp giao dịch.

Ví dụ kiểm tra số lượng và tổng giá trị:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount,
       MIN(created_at) AS first_order,
       MAX(created_at) AS last_order
FROM appdb.orders;
~~~

So sánh với nguồn hoặc báo cáo chuẩn tại cùng mốc dữ liệu. Nếu so sánh hai máy chủ ở các thời điểm khác nhau trong khi nguồn vẫn nhận ghi, chênh lệch có thể chỉ do thời điểm lấy mẫu. Hãy so sánh tại cùng mốc snapshot/GTID hoặc trong môi trường đã dừng ghi.

### 7.4. Đo RTO/RPO thực tế

Ghi nhận thời gian:

| Giai đoạn | Thời điểm bắt đầu/kết thúc | Thời lượng |
|---|---|---|
| Cấp phát máy phục hồi | Theo log diễn tập | Đo thực tế |
| Restore backup | Theo log công cụ | Đo thực tế |
| Apply binary log | Theo mốc PITR | Đo thực tế |
| Kiểm tra dữ liệu | Theo checklist | Đo thực tế |
| Smoke test và mở dịch vụ | Theo runbook | Đo thực tế |

RTO thực tế là tổng thời gian cần để dịch vụ trở lại trạng thái vận hành được, không chỉ là thời gian chạy lệnh restore. RPO thực tế được xác định bởi mốc dữ liệu cuối cùng có thể phục hồi và mức mất dữ liệu trong kịch bản thử nghiệm.

Nếu thời gian restore vượt RTO, cần thay đổi công cụ, lịch full/incremental backup, tài nguyên, kiến trúc standby hoặc phạm vi kiểm tra. Không ghi RTO đạt yêu cầu chỉ vì backup được tạo nhanh.

## 8. Giới hạn của downgrade MySQL

### 8.1. Downgrade khác với rollback ứng dụng

Rollback ứng dụng là đưa code hoặc cấu hình về phiên bản trước trong khi database vẫn giữ schema tương thích. Downgrade MySQL là đưa máy chủ hoặc định dạng dữ liệu về phiên bản cũ hơn. Hai thao tác có rủi ro và yêu cầu khác nhau.

Một ứng dụng cũ có thể không chạy với schema mới, nhưng điều đó không có nghĩa phải hạ phiên bản MySQL. Có thể cần một migration schema tương thích, một bản ứng dụng trung gian hoặc phục hồi dữ liệu trên máy chủ riêng.

### 8.2. Không mặc định có thể downgrade tại chỗ

Không được giả định rằng MySQL có thể mở data directory của phiên bản mới bằng binary server cũ. Qua các phiên bản, data dictionary, redo/undo, metadata, system schema và định dạng lưu trữ có thể thay đổi.

Downgrade cần được kiểm tra theo đúng dòng phát hành, phiên bản nguồn/đích và phương pháp được tài liệu hỗ trợ. Với MySQL 8.4, tài liệu downgrade phân biệt rõ các trường hợp:

| Đường downgrade | Phương pháp được tài liệu 8.4 liệt kê | Điều kiện đáng chú ý |
|---|---|---|
| Trong cùng dòng LTS 8.4.y về 8.4.x | In-place, logical dump/load, Clone hoặc replication | Phải kiểm tra downgrade threshold và đúng cặp patch release |
| Từ 8.4.x LTS về 8.0.y | Logical dump/load hoặc replication | Chỉ dành cho rollback nếu dữ liệu chưa sử dụng chức năng mới của server |
| Từ 8.4.x LTS về 8.3.0 Innovation | Logical dump/load hoặc replication | Chỉ dành cho rollback nếu dữ liệu chưa sử dụng chức năng mới của server |
| Về MySQL 5.7 hoặc cũ hơn | Không hỗ trợ | Không thực hiện downgrade |

Các phương pháp và điều kiện trên là thông tin theo tài liệu MySQL 8.4; không áp dụng nguyên xi cho mọi phiên bản MySQL khác. Với một cặp patch release trong cùng dòng LTS, kiểm tra ngưỡng downgrade mà server ghi nhận; một bản phát hành có thể từ chối quay về patch quá cũ. Khi tài liệu của phiên bản hoặc trạng thái downgrade validation không xác nhận đường đi, hãy dùng phương án restore backup trước nâng cấp.

Lưu ý rằng trang **Before You Begin** của cùng bộ tài liệu MySQL 8.4 có một cảnh báo thận trọng hơn về downgrade từ 8.4 xuống 8.3 hoặc một bản 8.4 trước đó, trong khi bảng ở chương **Downgrading MySQL** liệt kê các phương pháp được hỗ trợ theo dòng phát hành. Khi các trang tài liệu có cách diễn đạt khác nhau, không tự suy ra rằng cặp phiên bản cụ thể được phép downgrade tại chỗ. Kiểm tra release notes, downgrade validation và chính sách hỗ trợ cho đúng bản build; nếu chưa xác nhận được, dùng backup trước nâng cấp làm phương án quay lui.

### 8.3. Những thay đổi có thể cản trở downgrade

Một số yếu tố cần rà soát:

- Data dictionary hoặc định dạng metadata thay đổi giữa các phiên bản.
- Kiểu dữ liệu, thuộc tính cột hoặc cú pháp DDL mới mà phiên bản cũ không hiểu.
- Collation, charset hoặc quy tắc so sánh mới.
- Functional index, invisible index, generated column hoặc expression default.
- Plugin, component, authentication plugin hoặc định dạng account mới.
- Định dạng redo/undo, tablespace hoặc metadata InnoDB.
- System table, role, grant và cấu trúc schema mysql.
- Tính năng replication, GTID hoặc metadata binlog phụ thuộc phiên bản.

Danh sách trên là các nhóm rủi ro cần kiểm tra, không phải khẳng định rằng mọi tính năng đều tự động chặn mọi downgrade. Hãy đối chiếu tài liệu chính thức cho đúng phiên bản và kiểm thử trên bản sao đại diện.

### 8.4. Phương án quay về phiên bản cũ

Nếu phiên bản mới gặp sự cố và đường downgrade tại chỗ không được hỗ trợ, các phương án thường là:

**Phục hồi backup trước nâng cấp.** Dựng một máy chủ bằng phiên bản cũ tương ứng, restore full backup được tạo trước khi nâng cấp, rồi phát lại binary log đến mốc chấp nhận được nếu chuỗi log và định dạng tương thích. Đây là phương án trực tiếp để trở lại trạng thái trước nâng cấp.

**Logical export/import.** Nếu cần chuyển dữ liệu từ phiên bản mới về máy chủ cũ, xuất schema và dữ liệu ở dạng logic, điều chỉnh DDL/kiểu dữ liệu/tính năng không tương thích, rồi import vào máy chủ cũ. Phải kiểm tra kỹ các tính năng không được phiên bản cũ hỗ trợ. Đây là migration dữ liệu, không phải downgrade vật lý.

**Chạy song song và chuyển endpoint.** Khởi tạo máy chủ phiên bản cũ từ backup, đồng bộ dữ liệu theo một phương án đã kiểm thử, rồi chuyển ứng dụng sau khi đối soát. Nếu máy chủ mới đã nhận ghi, cần replication ngược hoặc CDC/reconciliation để không mất các giao dịch phát sinh sau mốc backup.

Không copy thư mục data directory từ máy chủ mới sang máy chủ cũ, không sửa trực tiếp system table để ép máy chủ khởi động và không bỏ qua lỗi upgrade/downgrade. Những thao tác này có thể làm hỏng dữ liệu và khiến việc phục hồi khó hơn.

## 9. Kế hoạch trước và sau nâng cấp

### 9.1. Trước nâng cấp

1. Ghi lại phiên bản MySQL, hệ điều hành, cấu hình, plugin và topology replication.
2. Chạy công cụ kiểm tra tương thích nâng cấp phù hợp với phiên bản đích, ví dụ MySQL Shell Upgrade Checker khi được hỗ trợ.
3. Xử lý cảnh báo về cú pháp, kiểu dữ liệu, reserved word, system variable và tính năng bị loại bỏ.
4. Tạo full backup bao gồm schema hệ thống cần thiết và lưu binary log từ mốc backup.
5. Lưu định nghĩa user/role/grant, file cấu hình, keyring và chứng thư.
6. Restore thử nghiệm backup trên môi trường cô lập.
7. Diễn tập nâng cấp và phương án phục hồi trên bản sao đại diện.
8. Xác nhận RPO/RTO và thời gian maintenance với chủ hệ thống.

Upgrade Checker giúp phát hiện nhiều vấn đề tương thích; nó không thay thế backup, restore rehearsal hoặc kiểm thử ứng dụng.

### 9.2. Trong lúc nâng cấp

- Đưa ứng dụng vào chế độ bảo trì hoặc giới hạn ghi theo runbook.
- Xác nhận backup và binary log đã sẵn sàng.
- Dừng hoặc xử lý các job có thể ghi vào database trong lúc nâng cấp.
- Thực hiện nâng cấp theo đúng đường phiên bản được hỗ trợ.
- Theo dõi error log, tiến trình upgrade và dung lượng.
- Không cho ứng dụng nhận traffic cho đến khi kiểm tra server và schema hoàn tất.

### 9.3. Sau nâng cấp

- Xác nhận phiên bản server và trạng thái service.
- Kiểm tra schema, index, view, trigger, routine và event.
- Kiểm tra user, role, grant, plugin, TLS và keyring.
- Kiểm tra replication/cluster và trạng thái binary log.
- Chạy truy vấn trọng yếu, smoke test và đối soát dữ liệu.
- Theo dõi execution plan, latency, deadlock và tải hệ thống.
- Giữ backup trước nâng cấp và binary log theo thời hạn rollback đã phê duyệt.

Nếu phải quay lại phiên bản cũ sau khi hệ thống mới đã nhận giao dịch, hãy xác định cách đồng bộ những giao dịch mới đó trước khi chuyển endpoint. Đưa ứng dụng về máy chủ cũ mà không chuyển dữ liệu phát sinh ở máy chủ mới có thể làm mất giao dịch hoặc tạo hai nhánh dữ liệu.

## 10. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Backup có file nhưng restore thất bại | File thiếu, hỏng, công cụ không tương thích hoặc metadata không đầy đủ | Kiểm tra checksum, log backup và phiên bản công cụ; tạo lại backup nếu cần |
| MySQL không mở được tablespace sau restore | Thiếu file dữ liệu, keyring, plugin hoặc bước prepare | Kiểm tra log, khóa mã hóa, quyền filesystem và quy trình restore |
| PITR dừng vì thiếu binary log | Retention quá ngắn hoặc archive không đầy đủ | Khôi phục từ backup khác và chuỗi log còn đủ; điều chỉnh chính sách lưu |
| Restore xong nhưng ứng dụng không kết nối | Thiếu user/grant, authentication plugin hoặc TLS | Khôi phục tài khoản bằng phương thức tương thích và kiểm tra quyền |
| Dữ liệu khác nguồn | Sai mốc log, bỏ sót event, restore không nhất quán hoặc phát lại trùng | Kiểm tra tọa độ/GTID, chuỗi log và invariant nghiệp vụ |
| DDL thất bại do metadata lock | Transaction dài hoặc truy vấn đang giữ metadata lock | Tìm blocker, drain transaction và thử lại trong cửa sổ phù hợp |
| Phiên bản cũ không khởi động với data directory mới | Downgrade tại chỗ không được hỗ trợ hoặc vượt downgrade threshold | Dựng phiên bản cũ riêng và restore backup trước nâng cấp |
| Logical import báo lỗi cú pháp | DDL hoặc tính năng mới không được phiên bản cũ hỗ trợ | Chuyển đổi schema và dữ liệu có kiểm soát trước khi import |
| Khôi phục mất quá nhiều thời gian | Backup/restore chưa được tối ưu hoặc thiếu tài nguyên | Dùng physical backup phù hợp, tăng tài nguyên và diễn tập lại |
| Quay lại máy chủ cũ làm mất giao dịch | Máy chủ mới đã nhận ghi sau mốc backup | Đồng bộ ngược hoặc đối soát dữ liệu trước khi chuyển endpoint |

Không bỏ qua lỗi restore, applier hoặc upgrade chỉ để đạt trạng thái service Running. Một máy chủ khởi động được vẫn có thể thiếu bảng, thiếu giao dịch hoặc sai quyền.

## 11. Checklist trước thay đổi quan trọng

### Backup

- [ ] Xác định RPO/RTO và phạm vi cần phục hồi.
- [ ] Chọn logical/physical backup phù hợp với kích thước và phiên bản.
- [ ] Ghi GTID set hoặc tọa độ binary log của backup.
- [ ] Lưu binary log liên tục và bảo đảm retention đủ dài.
- [ ] Bảo vệ cấu hình, user/role/grant, plugin, keyring và certificate.
- [ ] Mã hóa backup và giới hạn quyền truy cập.
- [ ] Kiểm tra checksum và log công cụ.
- [ ] Lưu bản backup ngoài máy chủ nguồn.

### Diễn tập phục hồi

- [ ] Restore trên môi trường cô lập.
- [ ] Dùng đúng phiên bản và công cụ tương thích.
- [ ] Phát lại binary log đến mốc đã chọn.
- [ ] Kiểm tra schema, đối tượng, user và quyền.
- [ ] Đối soát số hàng, checksum và invariant nghiệp vụ.
- [ ] Chạy smoke test ứng dụng.
- [ ] Đo thời gian restore và thời gian đưa dịch vụ hoạt động.
- [ ] Ghi lại lỗi và cập nhật runbook.

### Downgrade/rollback

- [ ] Kiểm tra đường downgrade có được tài liệu hỗ trợ cho đúng phiên bản hay không.
- [ ] Kiểm tra downgrade threshold nếu downgrade trong cùng dòng LTS.
- [ ] Không giả định data directory mới tương thích với server cũ.
- [ ] Có backup trước nâng cấp và binary log cần thiết.
- [ ] Xác định cách chuyển giao dịch phát sinh sau khi phiên bản mới nhận ghi.
- [ ] Chuẩn bị máy chủ cũ riêng nếu cần restore.
- [ ] Kiểm thử logical export/import nếu đây là phương án dự phòng.
- [ ] Xác định người phê duyệt và điều kiện chuyển endpoint.

## 12. Tự kiểm tra

**Tình huống 1:** Một DBA tạo file mysqldump nhưng chưa từng restore thử. Có thể xem hệ thống đã có phương án backup đáng tin cậy chưa?

**Gợi ý:** Chưa. File tồn tại không chứng minh có thể restore. Cần phục hồi trên môi trường cô lập, kiểm tra cấu trúc, dữ liệu và ứng dụng.

**Tình huống 2:** Một bảng InnoDB được dump bằng --single-transaction, trong lúc dump có người chạy ALTER TABLE trên cùng bảng. Có thể giả định dump vẫn nhất quán không?

**Gợi ý:** Không. --single-transaction không bảo vệ dump khỏi DDL đồng thời. Cần đóng băng DDL trên đối tượng liên quan trong thời gian snapshot.

**Tình huống 3:** Một lệnh DROP TABLE chạy nhầm và đã hoàn tất. Có thể dùng ROLLBACK để lấy lại bảng không?

**Gợi ý:** Không. DDL có implicit commit. Cần restore backup vào môi trường phục hồi và phát lại binary log đến trước event DROP, sau đó xác minh dữ liệu.

**Tình huống 4:** Sau nâng cấp, ứng dụng lỗi và nhóm muốn chạy binary MySQL cũ trên data directory hiện tại. Đây có phải phương án downgrade an toàn không?

**Gợi ý:** Không được giả định như vậy. Cần kiểm tra downgrade path chính thức và downgrade threshold. Nếu không hỗ trợ, dựng máy chủ phiên bản cũ riêng và restore backup trước nâng cấp hoặc logical export/import đã kiểm tra tương thích.

**Tình huống 5:** Backup được tạo lúc 01:00, sự cố xảy ra lúc 09:00 nhưng chỉ có binary log đến 06:00. RPO thực tế có thể đạt đến đâu?

**Gợi ý:** Không thể phục hồi các giao dịch sau mốc log cuối cùng có sẵn. Mốc phục hồi tối đa bị giới hạn bởi backup cộng với chuỗi binary log liên tục; RPO không thể tốt hơn dữ liệu log còn lưu.

## 13. Điểm cần ghi nhớ

- Backup chỉ đáng tin khi đã restore và kiểm tra trên môi trường cô lập.
- Chọn backup theo RPO/RTO và phạm vi phục hồi; logical, physical, snapshot và binary log có vai trò khác nhau.
- Snapshot nhất quán cần phối hợp đúng với engine và DDL; --single-transaction chỉ bảo đảm snapshot transaction cho bảng InnoDB.
- Lưu GTID hoặc tọa độ binlog cùng backup và giữ chuỗi binary log liên tục để hỗ trợ PITR.
- Bảo vệ cả user, role, grant, cấu hình, plugin, keyring và chứng thư cần thiết để mở dữ liệu.
- DDL có implicit commit; atomic DDL không đồng nghĩa với khả năng ROLLBACK sau khi thao tác đã hoàn tất.
- Diễn tập restore phải kiểm tra cấu trúc, dữ liệu, nghiệp vụ, bảo mật và thời gian phục hồi.
- Downgrade tại chỗ phụ thuộc dòng LTS/Innovation, cặp phiên bản và downgrade threshold; không dùng một quy tắc chung cho mọi phiên bản.
- Khi cần quay về phiên bản cũ, ưu tiên restore backup trước nâng cấp vào máy chủ tương thích hoặc logical export/import đã kiểm thử.
- Nếu phiên bản mới đã nhận ghi, phải đồng bộ giao dịch mới trước khi chuyển ứng dụng trở lại máy chủ cũ.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Backup and Recovery](https://dev.mysql.com/doc/refman/8.4/en/backup-and-recovery.html) — các phương pháp backup và restore.
- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html) — logical backup, snapshot và tọa độ binary log.
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html) — phục hồi bằng binary log.
- [MySQL 8.4 Reference Manual: Upgrade Paths](https://dev.mysql.com/doc/refman/8.4/en/upgrade-paths.html) — các đường nâng cấp được hỗ trợ.
- [MySQL 8.4 Reference Manual: Downgrading MySQL](https://dev.mysql.com/doc/refman/8.4/en/downgrading.html) — các phương pháp và điều kiện downgrade theo phiên bản.
- [MySQL 8.4 Reference Manual: Before You Begin an Upgrade](https://dev.mysql.com/doc/refman/8.4/en/upgrade-before-you-begin.html) — yêu cầu backup trước nâng cấp, bao gồm schema hệ thống mysql.
- [MySQL Shell 8.4 Reference: Upgrade Checker Utility](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-shell-utilities-upgrade.html) — kiểm tra tương thích trước nâng cấp.
