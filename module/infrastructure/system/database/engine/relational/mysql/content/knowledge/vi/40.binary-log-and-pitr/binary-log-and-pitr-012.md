# Binary log và PITR

## Giới hạn thao tác reset binary log/GTID và thay đổi cú pháp theo phiên bản

Binary log là một phần của chuỗi phục hồi MySQL. Nó ghi lại các thay đổi dữ liệu và cấu trúc được chọn theo cấu hình, hỗ trợ replication và cho phép phát lại giao dịch sau một bản backup để phục hồi đến một thời điểm cụ thể (point-in-time recovery, PITR). Vì vậy, các thao tác xóa log hoặc đặt lại lịch sử GTID có thể ảnh hưởng trực tiếp đến khả năng phục hồi và tính liên tục của replication.

Trong module `DATABASE_MYSQL`, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Khi vận hành binary log, cần hiểu cả trạng thái dữ liệu, lịch sử giao dịch và topology replication: một lệnh quản trị chạy thành công chưa có nghĩa hệ thống vẫn còn đủ dữ liệu để khôi phục.

Bài này tập trung vào ranh giới giữa xoay log, purge log, reset toàn bộ binary log/GTID và reset metadata ở replica; đồng thời giải thích các thay đổi tên lệnh giữa MySQL 5.7, 8.0 và 8.4. Các lệnh reset trong bài có thể xóa lịch sử không thể tái tạo. Hãy chỉ thực hành lệnh phá hủy trên instance lab có thể tạo lại.

### 1. Binary log và GTID lưu điều gì?

Binary log (binlog) ghi các sự kiện thay đổi trên máy chủ theo cấu hình. Tùy `binlog_format`, sự kiện có thể biểu diễn câu lệnh SQL (`STATEMENT`), thay đổi hàng (`ROW`) hoặc kết hợp (`MIXED`). Binary log không phải nhật ký mọi câu `SELECT`; nó phục vụ sao chép thay đổi và phục hồi dữ liệu.

Một số thông tin cần phân biệt:

- **Binary log file:** tệp log có tên tuần tự, ví dụ `binlog.000123`.
- **Binary log index:** tệp chỉ mục ghi danh sách các binary log mà máy chủ quản lý.
- **File/position:** tọa độ sự kiện trong một binary log, thường được ghi cùng backup để biết điểm bắt đầu phát lại.
- **GTID:** định danh giao dịch toàn cục, thường có dạng `server_uuid:transaction_number`.
- **`gtid_executed`:** tập GTID mà máy chủ đã thực thi, bao gồm các giao dịch vẫn còn trong binlog và các giao dịch đã bị purge khỏi binlog.
- **`gtid_purged`:** tập GTID đã thực thi nhưng không còn hiện diện trong các binary log hiện có trên máy chủ.

GTID giúp MySQL nhận diện giao dịch đã chạy mà không phụ thuộc duy nhất vào tên file và vị trí. Nó không chứa nội dung giao dịch để có thể phát lại. Nếu binary log chứa giao dịch đã bị xóa và không có bản archive khác, GTID chỉ cho biết giao dịch từng tồn tại; nó không khôi phục được nội dung đã mất.

Kiểm tra trạng thái hiện tại:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW BINARY LOGS;

SELECT
  @@GLOBAL.gtid_mode AS gtid_mode,
  @@GLOBAL.gtid_executed AS gtid_executed,
  @@GLOBAL.gtid_purged AS gtid_purged;
```

Lệnh xem trạng thái file/position hiện tại thay đổi tên theo phiên bản; bảng ở phần 4 trình bày cách chọn cú pháp. Trên máy chủ nguồn đang bật binlog, hãy ghi lại tên file và vị trí cùng GTID set tại thời điểm tạo backup. Nếu `log_bin` đang tắt, không thể dựa vào binlog của máy chủ đó để thực hiện PITR cho khoảng thời gian không có log.

### 2. Phân biệt rotate, purge và reset

Ba thao tác này có tác động rất khác nhau. Không dùng từ “reset log” chung chung trong runbook; hãy ghi đúng lệnh và kết quả mong muốn.

| Thao tác | Mục đích | Tác động chính | Ảnh hưởng PITR/replication |
|---|---|---|---|
| `FLUSH BINARY LOGS` | Xoay sang file binlog mới | Đóng file hiện tại và tạo file kế tiếp; giữ các file cũ | Thường không phá chuỗi log; file cũ vẫn có thể được đọc |
| `PURGE BINARY LOGS` | Xóa có chọn lọc các file cũ | Xóa các file trước tên file hoặc thời điểm chỉ định; cập nhật trạng thái GTID đã purge | Có thể phá PITR hoặc làm replica thiếu log nếu xóa file vẫn cần |
| `RESET MASTER` (các bản trước 8.4) | Khởi tạo lại toàn bộ lịch sử binlog | Xóa toàn bộ binary log được quản lý và đặt lại trạng thái GTID theo semantics của phiên bản | Phá chuỗi PITR hiện có; có thể làm replication và quản lý GTID mất tính liên tục |
| `RESET BINARY LOGS AND GTIDS` (MySQL 8.4) | Tên lệnh mới cho thao tác reset toàn bộ | Xóa binary log và đặt lại lịch sử GTID | Tác động phá hủy tương đương mục reset; phải lập kế hoạch lại backup/replication |
| `RESET REPLICA` | Đặt lại trạng thái ở máy replica | Xóa relay log và đặt lại metadata replication theo phạm vi lệnh | Không xóa binlog trên source; có thể làm replica cần cấu hình hoặc đồng bộ lại |

#### 2.1. Rotate: bắt đầu file mới nhưng giữ lịch sử

```sql
FLUSH BINARY LOGS;
SHOW BINARY LOGS;
```

Rotate hữu ích để tạo ranh giới file, hỗ trợ archive hoặc chuẩn bị một tọa độ log mới. Lệnh này không xóa các file trước đó và không xóa GTID history. Nếu mục tiêu chỉ là bắt đầu một file binlog mới, hãy dùng rotate thay vì reset.

#### 2.2. Purge: xóa một phần log sau khi xác minh

Có thể purge các file đứng trước một file được chỉ định:

```sql
SHOW BINARY LOGS;
PURGE BINARY LOGS TO 'binlog.000123';
```

Lệnh trên xóa các file đứng trước `binlog.000123`; file đích và các file sau nó được giữ lại. Có thể purge theo thời gian:

```sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

Thời điểm phải được chọn theo chính sách lưu trữ và trạng thái backup/replica. Trước khi purge, hãy xác minh:

1. Mọi replica cần các file sắp xóa đã nhận và áp dụng các giao dịch tương ứng.
2. Không còn replica đang ngừng hoạt động cần quay lại từ những file đó.
3. Kho archive có bản sao binlog đầy đủ, đọc được và được giữ theo thời hạn yêu cầu nếu cần dùng cho PITR.
4. Các full backup và khoảng thời gian PITR cần bảo vệ không phụ thuộc vào những file sắp xóa.
5. Tên file, thời điểm và GTID set đã được ghi nhận trong biên bản vận hành.

Purge không đặt lại toàn bộ `gtid_executed`. Các giao dịch đã bị loại khỏi binlog được phản ánh trong `gtid_purged`. Tuy nhiên, một replica cần giao dịch đã purge có thể không lấy được chúng từ source nữa. Auto-position bằng GTID không thể tạo lại nội dung binlog đã mất.

MySQL có thể tự hết hạn binlog theo cấu hình như `binlog_expire_logs_seconds`. Hãy xem thời hạn tự động xóa như một chính sách retention cần phối hợp với lịch backup, archive và độ trễ replica. Đừng đặt thời hạn ngắn hơn khoảng thời gian mà tổ chức cam kết phục hồi.

#### 2.3. Reset toàn bộ: thao tác phá hủy

Trên các phiên bản trước MySQL 8.4, lệnh reset toàn bộ thường gặp là:

```sql
RESET MASTER;
```

Trên MySQL 8.4, dùng tên lệnh mới:

```sql
RESET BINARY LOGS AND GTIDS;
```

Đây là lệnh quản trị có phạm vi rộng. Nó xóa các binary log được máy chủ quản lý, khởi tạo lại chuỗi file/position và đặt lại lịch sử GTID theo semantics của phiên bản. Khi GTID được sử dụng, thao tác reset làm rỗng trạng thái `gtid_executed` và `gtid_purged` của instance theo hành vi được định nghĩa cho lệnh ở phiên bản đó. Nó không xóa các hàng dữ liệu trong table và không thay thế thao tác restore database. Nhưng sau lệnh, các giao dịch trước đó không còn được phục hồi từ những binlog vừa xóa.

Không chạy reset chỉ để “dọn dung lượng”, “đưa số file về nhỏ” hoặc “sửa lỗi GTID”. Với mục tiêu dọn dung lượng, hãy thiết kế retention và purge có kiểm soát. Với lỗi GTID, hãy điều tra tập GTID, trạng thái dữ liệu và topology trước khi quyết định re-seed hoặc dựng lại replica.

Trước khi reset trong một môi trường được phê duyệt, cần có đầy đủ các điều kiện sau:

- Đã xác định rõ instance và vai trò của nó: source độc lập, replica, thành viên topology nhiều nguồn hay môi trường lab.
- Đã dừng hoặc cô lập các luồng replication theo runbook phù hợp và hiểu trạng thái của từng channel.
- Đã lưu backup nhất quán, binary log cần thiết và metadata file/position hoặc GTID set ở nơi độc lập với máy chủ đang reset.
- Đã xác nhận các replica và hệ thống downstream không còn cần các binlog sắp mất; có phương án re-seed nếu cần.
- Đã đánh giá tác động lên PITR, CDC, audit pipeline và công cụ backup có dùng binlog.
- Đã có kế hoạch khởi tạo lại chuỗi backup/binlog và kiểm tra GTID sau thao tác.

Lệnh reset thường yêu cầu quyền quản trị binlog phù hợp; tên dynamic privilege và quyền tương thích có thể khác giữa các phiên bản. Chỉ cấp quyền tối thiểu cần thiết, không cấp `SUPER` rộng rãi chỉ để tiện chạy lệnh.

### 3. GTID và các giới hạn không thể bỏ qua

GTID giải quyết việc nhận diện giao dịch, không thay thế binary log. Muốn hiểu tác động của reset, cần phân biệt ba việc: máy chủ đã thực thi giao dịch nào, giao dịch nào còn nội dung trong binlog, và replica đã áp dụng giao dịch nào.

#### 3.1. `gtid_executed` và `gtid_purged`

Ví dụ minh họa:

- Máy chủ đã thực thi GTID từ `uuid-a:1-500`.
- Binary log hiện có chỉ còn nội dung của `uuid-a:301-500`.
- Khi đó, `gtid_executed` có thể bao gồm `uuid-a:1-500`, còn `gtid_purged` thể hiện phần đã thực thi nhưng không còn trong binlog, chẳng hạn `uuid-a:1-300`.

Đây là ví dụ về ý nghĩa của hai tập, không phải cú pháp để gán GTID. Giá trị thực tế có thể là hợp của nhiều UUID và khoảng số giao dịch.

Nếu một replica báo thiếu `uuid-a:1-300`, nhưng source đã purge các binlog chứa chúng và không có archive, source không thể gửi các giao dịch đó. `SOURCE_AUTO_POSITION=1` chỉ giúp hai phía trao đổi tập GTID để chọn giao dịch còn có thể truyền; nó không khôi phục giao dịch đã bị xóa.

#### 3.2. Không đặt lại GTID để che một khoảng trống

Không chỉnh `gtid_purged` hoặc reset lịch sử GTID để làm cho hai máy chủ “trông như đồng bộ” khi dữ liệu của chúng chưa giống nhau. Làm như vậy có thể khiến MySQL bỏ qua giao dịch thực sự còn thiếu hoặc xử lý một giao dịch theo trạng thái không phản ánh dữ liệu.

`SET GLOBAL gtid_purged` có các điều kiện về giao nhau giữa tập GTID mới, `gtid_executed`, trạng thái binlog và phiên bản. Trong quy trình dựng replica từ backup, dump có thể chứa lệnh thiết lập GTID đã có trong backup. Lệnh đó chỉ nên được áp dụng theo hướng dẫn của công cụ backup và trên máy chủ đích có trạng thái phù hợp, thường là instance mới được chuẩn bị cho lần restore. Không sao chép một câu `SET GTID_PURGED` từ tài liệu cũ rồi chạy trên máy chủ đang phục vụ.

Khi replica lệch GTID, quy trình điều tra nên là:

1. Thu thập `gtid_executed`, `gtid_purged`, trạng thái replication và lỗi applier ở cả source lẫn replica.
2. Xác định GTID còn thiếu, đã có trên source, nằm trong archive hay đã mất hoàn toàn.
3. Đối chiếu dữ liệu thực tế và thời điểm backup được dùng để dựng replica.
4. Nếu log không còn, lấy lại các giao dịch từ archive đã xác minh hoặc dựng lại replica từ một backup mới tương thích.
5. Chỉ điều chỉnh metadata GTID theo runbook của phiên bản sau khi dữ liệu và tập giao dịch đã được xác nhận.

#### 3.3. Reset binlog khác reset replica

`RESET REPLICA` thao tác trên trạng thái replica: relay log và metadata của replication channel. `RESET REPLICA ALL` còn xóa thông tin kết nối source được lưu cho channel. Trên các phiên bản cũ, lệnh tương ứng dùng từ `SLAVE`.

Reset replica không xóa binary log trên source và không phải cách để reset `gtid_executed` toàn cục. Ngược lại, reset binary log/GTID trên source không tự cấu hình lại relay log hoặc connection metadata ở replica. Trước khi chạy bất kỳ lệnh reset nào, hãy ghi rõ đang thao tác trên máy nào và lớp trạng thái nào.

### 4. Thay đổi cú pháp theo phiên bản MySQL

MySQL đã thay một số tên lệnh từ thuật ngữ `MASTER`/`SLAVE` sang `SOURCE`/`REPLICA`, và MySQL 8.4 đổi tên lệnh reset binary log. Bảng dưới đây giúp chọn cú pháp phù hợp; hãy xác minh tài liệu đúng phiên bản đang chạy, đặc biệt khi dùng bản phân phối có thay đổi riêng.

| Mục đích | MySQL 5.7 và các bản 8.0 cũ | MySQL 8.0 mới | MySQL 8.4 |
|---|---|---|---|
| Xem trạng thái binary log hiện tại | `SHOW MASTER STATUS` | `SHOW MASTER STATUS` vẫn dùng được; thuật ngữ mới xuất hiện ở dòng 8.0 tương ứng | `SHOW BINARY LOG STATUS`; tên cũ bị deprecated |
| Reset toàn bộ binlog và GTID | `RESET MASTER` | `RESET MASTER` | `RESET BINARY LOGS AND GTIDS`; `RESET MASTER` bị deprecated |
| Xem trạng thái replica | `SHOW SLAVE STATUS` | `SHOW REPLICA STATUS` được giới thiệu từ 8.0.22; tên cũ vẫn có thể tồn tại trong các bản chuyển tiếp | `SHOW REPLICA STATUS` |
| Bắt đầu/dừng replication | `START SLAVE`, `STOP SLAVE` | `START REPLICA`, `STOP REPLICA` từ 8.0.22 | `START REPLICA`, `STOP REPLICA` |
| Reset relay log/metadata replica | `RESET SLAVE` | `RESET REPLICA` từ 8.0.22 | `RESET REPLICA` |
| Cấu hình source replication | `CHANGE MASTER TO` | `CHANGE REPLICATION SOURCE TO` được giới thiệu từ 8.0.23 | `CHANGE REPLICATION SOURCE TO` |
| Tùy chọn mysqldump ghi tọa độ nguồn | `--master-data` | `--source-data` được giới thiệu từ 8.0.26; `--master-data` bị deprecated | `--source-data`; tên cũ bị deprecated |

Các điểm chuyển đổi quan trọng:

- MySQL 8.0.22 giới thiệu nhóm lệnh dùng `REPLICA` cho thao tác replication như `START REPLICA`, `STOP REPLICA`, `RESET REPLICA` và `SHOW REPLICA STATUS`.
- MySQL 8.0.23 giới thiệu `CHANGE REPLICATION SOURCE TO` để thay cho `CHANGE MASTER TO`.
- MySQL 8.0.26 giới thiệu tùy chọn `mysqldump --source-data` thay cho `--master-data`; tên cũ bị deprecated.
- MySQL 8.4 giới thiệu `RESET BINARY LOGS AND GTIDS` thay cho `RESET MASTER`, đồng thời có `SHOW BINARY LOG STATUS` thay cho `SHOW MASTER STATUS`; các tên cũ được đánh dấu deprecated ở dòng phiên bản này.

Không suy ra rằng mọi lệnh cũ đã bị xóa ngay khi lệnh mới xuất hiện. Trong các bản chuyển tiếp, lệnh cũ có thể vẫn chạy nhưng phát cảnh báo deprecated. Mã tự động hóa nên có nhánh theo phiên bản hoặc dùng thư viện quản trị tương thích, đồng thời theo dõi warning khi nâng cấp.

Ví dụ truy vấn trạng thái theo phiên bản:

```sql
-- MySQL 5.7 / các bản trước khi có tên mới:
SHOW MASTER STATUS;
SHOW SLAVE STATUS;

-- MySQL 8.0.22+:
SHOW REPLICA STATUS;

-- MySQL 8.4:
SHOW BINARY LOG STATUS;
SHOW REPLICA STATUS;
```

Không chạy tất cả các câu lệnh trong một script không phân nhánh trên mọi phiên bản. Một câu lệnh không được hỗ trợ có thể làm script dừng giữa chừng, dẫn đến báo cáo trạng thái không đầy đủ.

### 5. PITR phụ thuộc vào chuỗi backup và binlog liên tục

PITR là quy trình phục hồi một full backup, sau đó phát lại các sự kiện binary log từ điểm nhất quán của backup đến ngay trước hoặc tại thời điểm cần khôi phục. Chuỗi này chỉ hoạt động nếu mọi đoạn log cần thiết còn tồn tại và đọc được.

Một bộ dữ liệu tối thiểu cho PITR gồm:

- Full backup nhất quán và metadata mô tả cách tạo backup.
- Tọa độ file/position hoặc GTID set tại thời điểm backup.
- Các binary log liên tiếp từ tọa độ đó đến thời điểm mục tiêu.
- Phiên bản MySQL và thông tin cấu hình cần thiết để diễn giải, phát lại log.
- Quy trình kiểm tra dữ liệu sau khi replay.

Nếu một file ở giữa chuỗi bị purge hoặc reset, việc phát lại có thể dừng tại khoảng trống. Backup vẫn có thể khôi phục về thời điểm tạo backup, nhưng không thể tiến đến thời điểm sau đó nếu thiếu giao dịch trung gian và không có bản archive khác.

#### 5.1. Ghi nhận tọa độ khi tạo backup

Với quy trình backup logic, hãy ghi nhận tọa độ binlog/GTID bằng tùy chọn phù hợp của công cụ: `mysqldump --master-data` ở các bản cũ, hoặc `mysqldump --source-data` từ MySQL 8.0.26 trở đi. Tên `--master-data` bị deprecated từ mốc này. Tên tùy chọn và quyền cần thiết thay đổi theo phiên bản; kiểm tra `mysqldump --help` của đúng client. Nếu backup physical, dùng metadata do công cụ physical backup cung cấp, không tự suy ra tọa độ từ file log hiện tại sau khi backup kết thúc.

Ghi lại thông tin máy chủ:

```sql
SELECT
  VERSION() AS mysql_version,
  @@server_uuid AS server_uuid,
  @@GLOBAL.gtid_mode AS gtid_mode,
  @@GLOBAL.gtid_executed AS gtid_executed,
  @@GLOBAL.gtid_purged AS gtid_purged,
  @@GLOBAL.log_bin AS log_bin;
```

Lưu output cùng backup, timestamp và định danh instance. Không chỉ ghi tên file binlog; cần giữ cả vị trí hoặc GTID set chính xác mà công cụ backup xác nhận.

#### 5.2. Phát lại binlog đến thời điểm mục tiêu

Ví dụ minh họa phát lại một khoảng binlog trên máy chủ phục hồi đã được cô lập:

```bash
mysqlbinlog \
  --start-position=154 \
  --stop-datetime="2026-11-18 10:14:59" \
  binlog.000123 binlog.000124 \
  | mysql -h restore-host -u restore_user -p
```

Trong ví dụ, tọa độ bắt đầu phải lấy từ metadata backup; thời điểm dừng là thời điểm trước thao tác lỗi. Hãy thay tên file, vị trí và thời gian bằng giá trị thực tế. Tùy mục tiêu, có thể dùng `--stop-position` để dừng theo ranh giới sự kiện thay vì thời gian. Khi dùng thời gian, cần xác định múi giờ của timestamp và kiểm tra nội dung binlog để tránh phát lại thừa hoặc thiếu giao dịch.

Với binlog được lưu ở máy chủ từ xa hoặc kho archive, tải và xác minh file trước khi replay. Giữ nguyên thứ tự file; kiểm tra checksum và không bỏ qua file trung gian. Nên xuất nội dung ra file SQL để xem xét trước trong những ca khôi phục nhạy cảm, rồi mới thực thi trên instance phục hồi.

#### 5.3. Khi reset làm đứt chuỗi PITR

Giả sử full backup được tạo tại `binlog.000120:800`, nhưng sau đó người vận hành chạy reset toàn bộ. Các file `binlog.000121` trở đi đã bị xóa khỏi máy chủ và chuỗi file bắt đầu lại. Backup vẫn chứa dữ liệu tại tọa độ ban đầu, nhưng không còn binlog trên instance để phát lại các thay đổi sau đó.

Chỉ có thể tiếp tục PITR nếu các file bị xóa đã được archive độc lập, đầy đủ và đúng thứ tự. Nếu archive không tồn tại, giới hạn phục hồi là trạng thái trong backup hoặc một backup khác có sẵn. Không thể dùng GTID set đơn lẻ để tái tạo nội dung giao dịch.

### 6. Quy trình an toàn trước khi purge hoặc reset

Hãy đưa thao tác vào change record và thực hiện theo trình tự sau:

1. **Xác định mục tiêu.** Cần rotate, giải phóng dung lượng bằng purge, dựng lại replica hay khởi tạo instance lab? Chọn đúng lệnh cho đúng mục tiêu.
2. **Xác minh phiên bản.** Ghi `SELECT VERSION()` và kiểm tra cú pháp được hỗ trợ. Không dùng tên lệnh 8.4 trên máy chủ cũ.
3. **Chụp trạng thái trước thay đổi.** Lưu danh sách `SHOW BINARY LOGS`, trạng thái binlog, `gtid_executed`, `gtid_purged`, trạng thái từng replica/channel và metadata backup gần nhất.
4. **Đối chiếu nhu cầu log.** Kiểm tra replica lag, archive, CDC, backup retention và khoảng PITR còn phải bảo vệ.
5. **Bảo đảm bản sao độc lập.** Nếu chính sách yêu cầu giữ binlog, xác minh archive có checksum, dung lượng và khả năng đọc; chỉ thấy file trong thư mục chưa chứng minh archive dùng được.
6. **Thực hiện trong cửa sổ bảo trì.** Dùng tài khoản được cấp quyền tối thiểu, chạy đúng một thao tác đã duyệt và ghi lại output.
7. **Xác minh sau thao tác.** Kiểm tra danh sách binlog, vị trí mới, GTID set, trạng thái replication và cảnh báo. Đối với reset, xác nhận kế hoạch dựng lại backup chain và replica.
8. **Kiểm thử khả năng phục hồi.** Dùng một bản sao hoặc instance thử nghiệm để restore backup và phát lại binlog đã lưu. Ghi nhận thời gian phục hồi và điểm dữ liệu đạt được.

Không dùng `RESET MASTER` hoặc `RESET BINARY LOGS AND GTIDS` như một bước vệ sinh định kỳ. Việc xóa log cần dựa trên retention đã thiết kế, không dựa trên mong muốn làm thư mục log trống.

### 7. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Replica báo không tìm thấy binlog cần đọc | File đã bị purge, reset hoặc archive không còn | Xác định file/GTID thiếu; tìm archive đã xác minh hoặc dựng lại replica từ backup mới |
| `SHOW MASTER STATUS` không chạy sau nâng cấp | Phiên bản mới ưu tiên cú pháp `SHOW BINARY LOG STATUS` | Kiểm tra phiên bản; dùng lệnh mới trên MySQL 8.4 |
| `RESET MASTER` phát cảnh báo deprecated | Đang chạy trên MySQL 8.4 | Dừng script cũ và chuyển sang cú pháp mới sau khi đánh giá lại tác động phá hủy |
| `RESET BINARY LOGS AND GTIDS` không được nhận diện | Server cũ hơn MySQL 8.4 hoặc không hỗ trợ cú pháp đó | Dùng tài liệu đúng phiên bản; không thay thế tự động nếu chưa xác minh semantics |
| `SET GTID_PURGED` bị từ chối | GTID set giao nhau với lịch sử hiện tại, trạng thái binlog hoặc điều kiện phiên bản không phù hợp | Đọc thông báo lỗi, so sánh các tập GTID và chuẩn bị instance đích đúng trạng thái; không xóa lịch sử để ép lệnh chạy |
| Replica auto-position vẫn không đồng bộ | Source đã purge giao dịch replica cần hoặc dữ liệu hai bên không cùng nền tảng | Đối chiếu GTID set, archive và backup; auto-position không phục hồi nội dung binlog đã mất |
| PITR dừng giữa chuỗi | Thiếu file, file hỏng, sai thứ tự hoặc tọa độ bắt đầu không đúng | Kiểm tra index, checksum, metadata backup và khoảng thời gian log; tìm archive bổ sung |
| Script quản trị chạy được trên 8.0 nhưng lỗi trên 8.4 | Tên lệnh cũ đã deprecated hoặc thay thế | Phân nhánh theo `VERSION()` và kiểm thử script trên từng dòng phiên bản trước khi triển khai |

### 8. Checklist kiểm soát thay đổi

Trước khi hoàn tất một change có liên quan binlog/GTID, hãy xác nhận:

- [ ] Đã xác định rõ server đích và vai trò source/replica của nó.
- [ ] Đã ghi nhận phiên bản MySQL và chọn đúng cú pháp.
- [ ] Đã phân biệt rotate, purge, reset binlog và reset replica.
- [ ] Đã lưu `gtid_executed`, `gtid_purged`, file/position và danh sách binlog trước thay đổi.
- [ ] Đã kiểm tra replica lag, channel, CDC consumer và các hệ thống downstream.
- [ ] Đã xác minh archive binlog độc lập nếu cần bảo vệ PITR.
- [ ] Đã xác nhận backup có thể restore và tọa độ của backup chính xác.
- [ ] Đã đánh giá ảnh hưởng của thao tác tới chuỗi PITR và kế hoạch re-seed replica.
- [ ] Đã có phê duyệt, cửa sổ bảo trì, người thực hiện và phương án khôi phục.
- [ ] Đã kiểm tra trạng thái sau thao tác và chạy restore/replay thử nghiệm khi phù hợp.

### 9. Bài tập thực hành

Một hệ thống đang chạy MySQL 8.0.35, bật GTID và có hai replica. Full backup được tạo hôm qua; các binary log từ thời điểm backup đến hiện tại đang được giữ để phục vụ PITR. Một quản trị viên đề nghị chạy `RESET MASTER` để giải phóng dung lượng.

1. Vì sao `FLUSH BINARY LOGS`, `PURGE BINARY LOGS` và `RESET MASTER` không thể thay thế cho nhau?
2. Trước khi purge một file, bạn cần xác minh những gì ở hai replica và kho archive?
3. Giải thích sự khác nhau giữa `gtid_executed` và `gtid_purged` bằng một ví dụ tập GTID.
4. Nếu replica cần một GTID đã bị purge khỏi source, tại sao `SOURCE_AUTO_POSITION=1` không tự giải quyết được?
5. Bạn sẽ chọn cú pháp nào khi chuyển script reset từ MySQL 8.0 sang 8.4? Cần kiểm tra điều gì trước khi triển khai?
6. Nếu reset toàn bộ binlog trên source, backup hôm qua còn phục hồi được đến thời điểm nào? Điều kiện nào cho phép tiếp tục PITR đến hôm nay?
7. Một máy chủ mới được dựng từ logical dump chứa `SET @@GLOBAL.GTID_PURGED`. Vì sao cần kiểm tra trạng thái GTID của máy chủ đích trước khi import?

### 10. Nguyên tắc vận hành

Binary log là một phần của chuỗi phục hồi có thời hạn và có thứ tự. Rotate tạo file mới; purge xóa một phần lịch sử; reset xóa toàn bộ lịch sử binlog và đặt lại trạng thái GTID; reset replica tác động đến relay log và metadata ở replica. Chọn đúng thao tác, đúng phiên bản và xác minh nhu cầu của mọi consumer trước khi xóa log. Khi có nghi ngờ về GTID hoặc replication, hãy điều tra dữ liệu và lịch sử giao dịch trước khi thay đổi metadata. Khả năng PITR chỉ được bảo đảm khi full backup, tọa độ nhất quán và mọi binlog cần thiết còn nguyên vẹn, có thể đọc và được kiểm thử phục hồi.
