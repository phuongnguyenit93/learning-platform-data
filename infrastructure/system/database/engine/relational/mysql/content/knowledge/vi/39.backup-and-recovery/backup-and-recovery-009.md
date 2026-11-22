# GTID, binary log coordinates và metadata đi kèm bản sao

Một bản sao lưu MySQL chỉ cho biết dữ liệu tại một thời điểm. Khi cần phục hồi đến một thời điểm muộn hơn, hoặc dựng lại một replica, ta còn cần biết chính xác bản sao lưu dừng ở đâu trong lịch sử giao dịch. MySQL cung cấp hai cách biểu diễn mốc này: **GTID** và **binary log coordinates** (tên file binary log cùng vị trí byte trong file). Metadata đi kèm bản sao lưu liên kết mốc đó với snapshot dữ liệu, giúp quá trình phục hồi có thể tiếp tục đúng từ giao dịch kế tiếp.

Nếu chỉ giữ file dump mà không giữ mốc giao dịch và các binary log cần thiết, ta có thể phục hồi được một phần dữ liệu nhưng không thể chứng minh dữ liệu đã được cập nhật đến đâu. Ngược lại, một GTID set hoặc cặp file/position đứng riêng cũng không chứa dữ liệu để khôi phục. Bản sao dữ liệu, mốc nhất quán và chuỗi log phải được quản lý cùng nhau.

## 1. Hai loại mốc giao dịch

### Binary log coordinates

Binary log ghi lại các sự kiện thay đổi dữ liệu và một số thay đổi cấu trúc để replica hoặc công cụ phục hồi có thể phát lại. Một coordinate gồm hai thành phần:

- **File**: tên binary log, ví dụ `mysql-bin.000042`.
- **Position**: offset byte trong file, ví dụ `123456`.

Khi một công cụ sao lưu ghi lại coordinate, ý nghĩa của nó phải là ranh giới phù hợp với snapshot: các giao dịch đã có trong bản sao lưu nằm trước mốc đó; các giao dịch cần phát lại bắt đầu từ mốc đó. File và position luôn là một cặp. Chỉ lưu tên file mà thiếu position sẽ không xác định được điểm bắt đầu chính xác.

Ví dụ, một metadata có thể ghi:

```text
File:     mysql-bin.000042
Position: 123456
```

Position là vị trí trong một file cụ thể, không phải số thứ tự giao dịch toàn cục. Nếu binary log đã bị xóa khỏi máy nguồn và không có bản lưu ở nơi khác, coordinate vẫn mô tả được mốc nhưng không thể giúp phát lại những sự kiện đã mất.

### GTID

GTID (Global Transaction Identifier) gắn một định danh duy nhất cho mỗi giao dịch được ghi vào binary log trong chế độ GTID. Dạng cơ bản là:

```text
source_uuid:transaction_id
```

Ví dụ:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:100
```

Một GTID set có thể chứa nhiều GTID và nén các khoảng liên tiếp:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:1-100:105:110-115,
8A1B2C3D-1111-2222-3333-444455556666:1-20
```

Phần UUID xác định nguồn đã tạo giao dịch; phần số là số thứ tự giao dịch trong lịch sử của UUID đó. Một set có thể bao gồm giao dịch từ nhiều nguồn, vì vậy không nên giả định GTID set luôn chỉ có một UUID.

Ba trạng thái thường gặp:

| Biến | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `@@GLOBAL.gtid_executed` | Tập GTID mà server đã thực thi. Tập này bao gồm giao dịch còn trong binary log và giao dịch đã bị purge khỏi binary log. | Ghi lại lịch sử giao dịch đã được áp dụng tại mốc chụp metadata. |
| `@@GLOBAL.gtid_purged` | Tập GTID đã thực thi nhưng binary log chứa chúng đã bị purge. Đây là tập con của `gtid_executed`. | Đánh giá phần lịch sử không còn sẵn để đọc từ binary log trên server đó. |
| `@@GLOBAL.gtid_mode` | Trạng thái bật/tắt GTID của server. | Xác định topology có thể sử dụng cơ chế GTID hay không. |

GTID giúp nhận diện giao dịch mà không phụ thuộc tên file hoặc offset. Nó hữu ích cho replication tự định vị, so sánh lịch sử giữa các server và xác định giao dịch đã có trên replica. Tuy nhiên, GTID không chứa nội dung giao dịch và không thay thế bản sao dữ liệu hoặc binary log. Biết một giao dịch có GTID không có nghĩa là ta còn giữ được dữ liệu để phát lại giao dịch đó.

## 2. Quan hệ giữa snapshot và mốc giao dịch

Điều quan trọng nhất là mốc giao dịch phải tương ứng với đúng snapshot dữ liệu. Giả sử quá trình sao lưu đọc bảng `orders` tại thời điểm T1, nhưng lại chạy `SHOW BINARY LOG STATUS` riêng ở T2 sau khi ứng dụng đã ghi thêm đơn hàng. Nếu dùng coordinate tại T2 để phục hồi bản dump ở T1, giao dịch xảy ra giữa hai thời điểm có thể bị bỏ qua. Nếu chọn mốc sớm hơn snapshot, giao dịch đã nằm trong dump có thể bị phát lại lần nữa.

Vì vậy, không nên tự ghép một bản dump với GTID hoặc coordinate được lấy tùy ý trước hay sau khi dump chạy. Hãy dùng tính năng của công cụ sao lưu để chụp mốc tại cùng ranh giới nhất quán, hoặc dùng quy trình khóa và snapshot đã được kiểm chứng cho đúng phiên bản và storage engine.

Với InnoDB, `--single-transaction` của `mysqldump` tạo một consistent snapshot bằng transaction. Khi kết hợp với `--source-data`, công cụ lấy binary log coordinates đồng bộ với snapshot bằng một global read lock ngắn ở đầu quá trình. Trong lúc dump, cần tránh các thao tác DDL làm thay đổi cấu trúc bảng; DDL không được bảo vệ như dữ liệu InnoDB trong snapshot. `--single-transaction` cũng không đảm bảo nhất quán cho bảng dùng storage engine không hỗ trợ transaction, chẳng hạn MyISAM.

Coordinate và GTID là hai cách biểu diễn mốc có liên quan nhưng không thể thay thế máy móc cho nhau. File/position cho biết nơi bắt đầu đọc trong chuỗi binary log; GTID set cho biết các giao dịch nào đã được thực thi. Khi metadata lưu cả hai, chúng phải mô tả cùng một ranh giới snapshot. Nếu hai giá trị mâu thuẫn, hãy dừng và điều tra nguồn tạo metadata trước khi phục hồi.

## 3. Thu thập trạng thái GTID và binary log

Trên MySQL 8.4, dùng `SHOW BINARY LOG STATUS` để xem binary log hiện tại và coordinate. Trên các phiên bản cũ hơn, lệnh thường gặp là `SHOW MASTER STATUS`:

```sql
SHOW BINARY LOG STATUS;
-- MySQL phiên bản cũ:
-- SHOW MASTER STATUS;

SHOW BINARY LOGS;

SELECT
    @@GLOBAL.server_uuid AS server_uuid,
    @@GLOBAL.gtid_mode AS gtid_mode,
    @@GLOBAL.enforce_gtid_consistency AS enforce_gtid_consistency,
    @@GLOBAL.gtid_executed AS gtid_executed,
    @@GLOBAL.gtid_purged AS gtid_purged;

SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
```

`SHOW BINARY LOG STATUS` cho biết mốc hiện tại tại thời điểm lệnh được thực hiện. Nếu chạy lệnh độc lập sau khi snapshot đã hoàn thành, kết quả không tự động trở thành mốc của snapshot cũ. Hãy dùng nó để kiểm tra trạng thái server hoặc đối chiếu metadata; đối với một bản dump, nên lấy mốc từ chính quy trình dump.

Khi bật GTID, cấu hình thường cần có:

```ini
[mysqld]
server_id = 101
log_bin = mysql-bin
gtid_mode = ON
enforce_gtid_consistency = ON
```

`server_id` phải duy nhất trong topology replication. `server_uuid` cũng phải duy nhất giữa các server đang hoạt động đồng thời. Khi clone một datadir để dựng máy mới, cần bảo đảm máy mới có UUID riêng trước khi tham gia topology; hai server cùng UUID có thể gây xung đột định danh GTID. Việc bật GTID trên hệ thống đang chạy cần theo lộ trình chuyển đổi phù hợp phiên bản, không nên chỉ thêm hai dòng cấu hình rồi restart tùy tiện.

Để dùng binary log cho phục hồi theo thời điểm, cần bật `log_bin`, giữ đủ các file log và chuyển chúng sang nơi lưu trữ độc lập trước khi server tự purge. Thời gian giữ log phải dài hơn khoảng thời gian mà tổ chức cần phục hồi. Một bản backup đầy đủ nhưng thiếu đoạn binary log từ mốc backup đến thời điểm cần khôi phục sẽ không thể thực hiện PITR đến thời điểm đó.

## 4. Ghi metadata cùng bản sao lưu logic

Với InnoDB, một lệnh `mysqldump` thường dùng để tạo bản dump có thông tin mốc như sau:

Ví dụ giả định source đã bật GTID (`gtid_mode=ON`) và đích phục hồi được chuẩn bị theo kế hoạch GTID. Nếu source không dùng GTID, hãy bỏ `--set-gtid-purged=ON` và lưu coordinate cùng metadata phù hợp; không bật tùy chọn này một cách máy móc.

```bash
mysqldump \
  --single-transaction \
  --source-data=2 \
  --set-gtid-purged=ON \
  --routines \
  --events \
  --triggers \
  --databases appdb \
  > appdb.sql
```

Ý nghĩa các tùy chọn chính:

- `--single-transaction`: đọc dữ liệu InnoDB từ một consistent snapshot.
- `--source-data=2`: ghi câu lệnh `CHANGE REPLICATION SOURCE TO` dưới dạng comment trong dump, kèm file và position tại ranh giới phù hợp với snapshot. Giá trị `1` ghi câu lệnh không comment; `2` giúp lưu mốc mà không tự thực thi câu lệnh khi import. Các bản MySQL cũ có tên tùy chọn `--master-data`.
- `--set-gtid-purged=ON`: ghi GTID set của nguồn vào dump bằng câu lệnh thiết lập `GTID_PURGED`. Khi restore, câu lệnh này ảnh hưởng lịch sử GTID trên server đích; cần đánh giá trạng thái GTID và lịch sử hiện có của đích trước khi import. Không áp dụng mù quáng vào server đang có lịch sử giao dịch khác.
- `--routines`, `--events`, `--triggers`: đưa stored routine, event và trigger vào phạm vi dump. Nếu cần tài khoản, role, grants hoặc cấu hình ngoài schema, phải có quy trình sao lưu riêng cho các thành phần đó.

`--source-data` cần quyền phù hợp để lấy thông tin và khóa cần thiết. Việc lấy global read lock chỉ diễn ra trong khoảng thời gian ngắn khi kết hợp đúng với `--single-transaction`, nhưng vẫn có thể chờ hoặc ảnh hưởng thao tác ghi tại thời điểm bắt đầu. Hãy thử trên phiên bản MySQL thực tế và lập lịch phù hợp với tải hệ thống. Không để DDL chạy đồng thời trong lúc dump đang đọc snapshot.

Trong dump, phần đầu file có thể chứa thông tin GTID và câu lệnh tọa độ. Hãy lưu nguyên file dump và trích metadata đó vào manifest kiểm kê để hệ thống phục hồi có thể tìm kiếm mà không cần đọc thủ công toàn bộ file. Nếu dùng `--set-gtid-purged=AUTO`, kết quả phụ thuộc trạng thái GTID của server và hành vi mặc định của phiên bản; khi cần hành vi xác định, hãy chọn rõ `ON` hoặc `OFF` theo kế hoạch phục hồi.

Với bản sao vật lý, công cụ backup thường cung cấp metadata riêng, ví dụ checkpoint/LSN và binary log coordinates hoặc GTID set tại checkpoint. Dùng metadata do chính công cụ tạo ra. Không lấy coordinate từ một lệnh SQL chạy sau khi copy datadir rồi ghép vào bản sao, vì hai thao tác có thể phản ánh hai thời điểm khác nhau. Sau khi chuẩn bị bản backup vật lý, cần giữ trạng thái backup đã hoàn tất/đã prepare theo đúng yêu cầu của công cụ.

## 5. Manifest nên đi cùng backup

Một manifest tốt giúp người trực vận hành biết bản sao lưu đến từ đâu, bao gồm những gì và có thể phát lại log nào. Ví dụ cấu trúc metadata nội bộ:

```yaml
backup_id: appdb-2026-11-19T010000Z
created_at_utc: "2026-11-19T01:00:00Z"
backup_type: logical
tool: mysqldump
tool_version: "8.4.x"
source:
  server_uuid: "3e11fa47-71ca-11e1-9e33-c80aa9429562"
  server_version: "8.4.x"
  schemas: [appdb]
  gtid_mode: ON
snapshot:
  consistency: "InnoDB consistent snapshot"
  ddl_frozen: true
  binlog_file: mysql-bin.000042
  binlog_position: 123456
  gtid_executed: "3E11FA47-71CA-11E1-9E33-C80AA9429562:1-100"
  gtid_purged: "3E11FA47-71CA-11E1-9E33-C80AA9429562:1-20"
artifacts:
  - path: appdb.sql
    size_bytes: 123456789
    sha256: "<sha256-checksum>"
binary_logs:
  first_required_file: mysql-bin.000042
  last_archived_file: mysql-bin.000050
encryption:
  encrypted: true
  key_reference: backup-key-prod-01
```

Các giá trị trong ví dụ chỉ minh họa cấu trúc; phải lấy giá trị thật từ công cụ và hệ thống lưu trữ. `gtid_purged` là tập GTID đã purge, không phải điểm bắt đầu phát lại. `gtid_executed` mô tả tập giao dịch đã thực thi tại mốc; nếu lưu GTID set quá lớn, có thể lưu trong file metadata riêng có checksum thay vì cắt ngắn chuỗi.

Manifest nên có ít nhất các nhóm thông tin sau:

| Nhóm | Thông tin nên lưu | Lý do |
|---|---|---|
| Nhận dạng | ID backup, thời điểm UTC, máy nguồn, `server_uuid`, phiên bản MySQL | Phân biệt backup và tái tạo đúng môi trường tương thích. |
| Phạm vi | Schema/table bao gồm và loại trừ, routines, triggers, events, tài khoản/grants có được sao lưu không | Tránh tưởng rằng dump chứa những thành phần thực tế đã bị bỏ qua. |
| Nhất quán | Storage engine, snapshot/lock mode, thời điểm bắt đầu và kết thúc, DDL có bị đóng băng không | Đánh giá bản sao có thể đại diện cho một trạng thái dữ liệu nhất quán hay không. |
| Mốc log | Binary log file/position, `gtid_executed`, `gtid_purged`, UUID nguồn | Xác định điểm nối giữa snapshot và lịch sử giao dịch. |
| Công cụ | Tên, phiên bản, tham số, mã thoát và log kết quả | Tái hiện quy trình và điều tra lỗi sao lưu. |
| Tính toàn vẹn | Kích thước, checksum, số phần, trạng thái upload/copy | Phát hiện file bị thiếu hoặc hỏng trong lưu trữ/truyền tải. |
| Phụ thuộc | Keyring, khóa mã hóa, plugin, cấu hình, chứng thư và secrets theo quy trình riêng | Bảo đảm có thể giải mã và khởi động hệ thống sau phục hồi. |
| Log tiếp nối | Danh sách binary log đã lưu, khoảng thời gian, checksum và vị trí lưu | Kiểm tra chuỗi log có liên tục từ mốc backup đến thời điểm cần phục hồi. |

Metadata phải được bảo vệ cùng mức với backup. GTID set, tên schema, địa chỉ máy chủ và tên file log có thể tiết lộ thông tin vận hành. Checksum giúp phát hiện hỏng file nhưng không chứng minh nguồn backup đáng tin; cần thêm kiểm soát quyền ghi, chữ ký hoặc kho lưu trữ bất biến nếu quy trình yêu cầu.

## 6. Dùng mốc để phục hồi đến một thời điểm

Quy trình point-in-time recovery (PITR) có ba phần:

1. Chọn bản backup nhất quán gần nhất nhưng có trước thời điểm cần phục hồi.
2. Khôi phục bản backup lên một server đích phù hợp và xác nhận trạng thái ban đầu.
3. Phát lại binary log từ đúng mốc backup đến ngay trước giao dịch cần loại bỏ hoặc đến mốc phục hồi đã chọn.

Giả sử manifest cho biết snapshot tương ứng với `mysql-bin.000042` tại position `123456`. Sau khi import dump, phát lại các log tiếp theo từ mốc đó:

```bash
mysqlbinlog \
  --start-position=123456 \
  --stop-position=987654 \
  mysql-bin.000042 mysql-bin.000043 \
  | mysql
```

`--start-position` áp dụng cho file đầu tiên trong danh sách. `--stop-position` giới hạn điểm dừng trong file cuối cùng được xử lý theo lệnh; cần xác định đúng file chứa điểm dừng và chọn ranh giới sự kiện/giao dịch hợp lệ. Trong thực tế, nếu điểm dừng nằm ở file khác, hãy chỉ rõ file đó và position tương ứng. Không đoán position bằng cách cộng kích thước hoặc dùng một offset từ file khác.

Có thể dùng `--stop-datetime` khi cần dừng theo thời gian:

```bash
mysqlbinlog \
  --start-position=123456 \
  --stop-datetime="2026-11-19 10:25:00" \
  mysql-bin.000042 mysql-bin.000043 \
  | mysql
```

Mốc thời gian phụ thuộc timezone và timestamp của sự kiện; nhiều giao dịch có thể nằm rất gần nhau. Với thao tác xóa nhầm hoặc cập nhật nhầm cần dừng chính xác, hãy đọc log, xác định giao dịch và dùng ranh giới position phù hợp. Luôn kiểm tra thời gian của máy nguồn, máy phục hồi và timezone được dùng khi phân tích.

Trước khi phát lại, kiểm tra đủ các file liên tiếp từ mốc backup. Binary log có thể được đọc để điều tra bằng:

```bash
mysqlbinlog \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000042 > binlog-review.txt
```

Chế độ decode/verbose này hữu ích để xem row event và điều tra, nhưng file đầu ra có phần mô tả phục vụ đọc hiểu; không dùng bản đã biến đổi cho mục đích replay thay cho luồng `mysqlbinlog` thực thi bình thường. Bảo toàn file binary log gốc và kiểm tra checksum trước khi sử dụng.

Nếu backup đã ghi `GTID_PURGED`, các GTID của snapshot được đánh dấu là đã có trên server phục hồi. Vì thế, log phát lại phải bắt đầu sau ranh giới snapshot tương ứng. Nếu phát lại giao dịch đã nằm trong dump, server có thể từ chối giao dịch GTID trùng hoặc tạo ra lỗi phục hồi. Không dùng GTID set được chụp ở một thời điểm khác để thay cho coordinate của dump.

## 7. GTID trong dựng replica và chuyển đổi server

Với GTID, replica có thể yêu cầu source gửi những giao dịch mà replica chưa có, thay vì người vận hành phải tự tính file/position. Trên MySQL phiên bản hỗ trợ cú pháp mới:

```sql
CHANGE REPLICATION SOURCE TO
    SOURCE_HOST = 'mysql-source.internal',
    SOURCE_PORT = 3306,
    SOURCE_USER = 'replication_user',
    SOURCE_PASSWORD = 'managed-secret',
    SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

Các bản cũ dùng cú pháp `CHANGE MASTER TO` và `MASTER_AUTO_POSITION=1`. Không đặt mật khẩu thật trong script hoặc lịch sử shell; dùng cơ chế secret phù hợp. `SOURCE_AUTO_POSITION=1` chỉ hoạt động khi cấu hình GTID và trạng thái lịch sử trên hai phía tương thích.

Khi dựng replica từ backup của source, GTID set đã có trong backup giúp source biết replica đã nhận những giao dịch nào. Source chỉ có thể gửi tiếp các GTID replica còn thiếu nếu binary log tương ứng vẫn còn được giữ trên source. Nếu source đã purge giao dịch cần thiết, auto-position không thể tự tái tạo phần log đã mất; cần cấp lại một backup mới hơn hoặc nạp lại replica từ nguồn backup có đủ lịch sử.

GTID set không đảm bảo hai server có dữ liệu giống nhau. Có thể xuất hiện giao dịch được thực thi thủ công trên replica, giao dịch bị bỏ qua, hoặc dữ liệu bị thay đổi ngoài replication. Trước khi đưa replica vào topology, hãy so sánh GTID set, kiểm tra errant transactions, xác nhận dữ liệu bằng checksum/đối soát và đánh giá replication filters. Không dùng việc `START REPLICA` thành công làm bằng chứng duy nhất rằng dữ liệu đã đồng nhất.

## 8. Lỗi thường gặp khi quản lý mốc và metadata

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Lấy `SHOW BINARY LOG STATUS` sau khi dump rồi gắn vào dump | Coordinate mới hơn snapshot; giao dịch phát sinh trong khoảng chênh lệch không được phản ánh đúng. | Lấy mốc bằng tùy chọn của công cụ backup hoặc quy trình snapshot đã đồng bộ. |
| Chỉ lưu file mà quên position | Không biết bắt đầu đọc binary log ở byte nào. | Lưu cặp file/position nguyên vẹn và kiểm tra lại từ metadata gốc. |
| Binary log đã bị purge | Chuỗi log không còn đủ từ mốc backup đến thời điểm cần phục hồi. | Lưu trữ log ngoài máy nguồn, đặt retention theo RPO và thử khôi phục định kỳ. |
| Dùng GTID set của server khác | UUID và lịch sử giao dịch không khớp nguồn backup. | Gắn GTID set với `server_uuid`, backup ID và metadata của cùng snapshot. |
| Import dump có `GTID_PURGED` lên server đã có lịch sử khác | GTID set đích xung đột hoặc không thỏa điều kiện thiết lập. | Dùng server phục hồi sạch theo kế hoạch; đánh giá GTID hiện có trước khi import. |
| Clone server nhưng giữ `server_uuid` trùng | Hai server cùng nhận diện là một nguồn GTID. | Cấp UUID riêng cho máy clone trước khi tham gia replication. |
| Dump chỉ có InnoDB nhưng schema có bảng MyISAM | `--single-transaction` không tạo snapshot nhất quán cho bảng không transactional. | Chuyển engine phù hợp hoặc dùng chiến lược khóa/backup khác bao phủ các bảng đó. |
| DDL chạy trong lúc dump | Thay đổi cấu trúc không được bảo vệ như snapshot dữ liệu. | Điều phối cửa sổ backup và kiểm soát migration/DDL. |
| Có file dump nhưng thiếu khóa mã hóa | Dữ liệu không thể giải mã sau sự cố. | Sao lưu keyring và tài liệu khôi phục khóa theo quy trình kiểm soát truy cập riêng. |
| Chỉ kiểm tra exit code, không kiểm tra file | File có thể thiếu, hỏng, upload chưa xong hoặc manifest không khớp. | Kiểm tra kích thước, checksum, metadata, khả năng đọc và phục hồi thử. |

## 9. Quy trình vận hành và kiểm chứng

Trước khi đánh dấu một backup là sẵn sàng phục hồi, thực hiện các bước sau:

1. **Xác nhận nguồn và cấu hình.** Ghi lại phiên bản MySQL, `server_uuid`, trạng thái binary log, GTID mode, storage engine và topology replication.
2. **Tạo snapshot nhất quán.** Dùng phương thức phù hợp với loại backup; kiểm soát DDL và các bảng không transactional.
3. **Ghi mốc cùng snapshot.** Lưu file/position và GTID set do công cụ backup cung cấp. Không ghép metadata lấy ở thời điểm khác.
4. **Lưu binary log tiếp nối.** Archive liên tục các file bắt đầu từ mốc cần thiết, giữ thứ tự và checksum, đồng thời giám sát khoảng trống trong chuỗi log.
5. **Lưu manifest và phụ thuộc.** Ghi phạm vi dữ liệu, công cụ, tham số, trạng thái nhất quán, khóa mã hóa, cấu hình và các object ngoài bảng dữ liệu.
6. **Kiểm tra tính toàn vẹn.** Xác minh file backup, manifest, checksum và log có thể đọc được; cảnh báo nếu metadata thiếu hoặc không khớp.
7. **Thử phục hồi.** Khôi phục vào môi trường cô lập, phát lại log đến một mốc đã chọn, kiểm tra ứng dụng và ghi nhận thời gian thực tế.
8. **Đo RPO/RTO.** RPO phụ thuộc tần suất snapshot và độ liên tục của binary log; RTO phụ thuộc tốc độ restore, replay, kiểm tra và chuyển ứng dụng sang hệ thống phục hồi.

Một lần backup chỉ nên được coi là đạt yêu cầu sau khi có thể chứng minh ba việc: snapshot có tính nhất quán, metadata chỉ đúng ranh giới giao dịch của snapshot, và chuỗi binary log cần thiết còn đầy đủ để tiến đến mốc phục hồi. Hãy tự động cảnh báo khi binary log archive bị gián đoạn, retention trên source sắp xóa log chưa lưu, hoặc manifest không có GTID/coordinate tương ứng.

## 10. Checklist review một bản sao lưu

- [ ] Có backup ID, thời điểm UTC, server version và `server_uuid`.
- [ ] Phạm vi schema/table và các thành phần routines, triggers, events được ghi rõ.
- [ ] Cơ chế snapshot phù hợp với storage engine; DDL được kiểm soát trong thời gian backup.
- [ ] Coordinate gồm đủ binary log file và position, lấy từ đúng snapshot.
- [ ] GTID set được lưu đầy đủ và gắn với cùng nguồn, cùng snapshot.
- [ ] `gtid_purged` không bị hiểu nhầm là toàn bộ giao dịch đã thực thi hoặc là nội dung backup.
- [ ] Binary log từ mốc backup đến thời điểm cần phục hồi được archive liên tục và có checksum.
- [ ] Manifest, backup và khóa mã hóa được lưu an toàn, có thể truy cập khi xảy ra sự cố.
- [ ] Có quy trình xử lý GTID khi restore lên server đã có lịch sử giao dịch.
- [ ] Đã thử restore và PITR, xác nhận dữ liệu và đo thời gian phục hồi.

GTID phù hợp để mô tả tập giao dịch đã thực thi và hỗ trợ replication tự định vị. Binary log coordinates phù hợp để chỉ ra vị trí bắt đầu đọc trong chuỗi log. Metadata đi kèm backup là phần nối hai khái niệm này với snapshot dữ liệu thực tế. Khi cả ba được tạo, lưu trữ và kiểm chứng đồng bộ, đội vận hành mới có thể phục hồi có kiểm soát và giải thích chính xác dữ liệu đã được khôi phục đến đâu.
