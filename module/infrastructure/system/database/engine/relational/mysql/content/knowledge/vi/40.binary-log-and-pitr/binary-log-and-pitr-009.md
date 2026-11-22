# Xác định mốc thời gian, vị trí hoặc GTID trước thao tác sai

Khi một câu lệnh xóa nhầm, cập nhật nhầm hoặc một migration gây hỏng dữ liệu, binary log giúp xác định chính xác giao dịch đã gây ra sự cố. Để phục hồi đến ngay trước giao dịch đó, người vận hành cần tìm được ba thông tin liên quan: **thời điểm xảy ra**, **ranh giới file/position** và, nếu server bật GTID, **mã GTID của giao dịch**.

Ba thông tin này có vai trò khác nhau. Thời gian giúp thu hẹp vùng cần điều tra. GTID nhận diện một giao dịch trong lịch sử replication. File/position xác định nơi `mysqlbinlog` bắt đầu hoặc dừng đọc. Một thời điểm gần đúng hay một GTID tìm thấy trong log chưa đủ để dừng phục hồi an toàn; phải xác định ranh giới bắt đầu của toàn bộ giao dịch sai và kiểm tra lại trên bản phục hồi thử.

## 1. Hiểu ranh giới của một giao dịch trong binary log

Binary log lưu các event theo thứ tự. Với giao dịch InnoDB có GTID và row-based logging, một nhóm event thường có dạng khái quát:

```text
# at 1200
# ... GTID ...
SET @@SESSION.GTID_NEXT='3e11fa47-71ca-11e1-9e33-c80aa9429562:501'/*!*/;

# at 1265
START TRANSACTION

# at 1330
# ... Table_map: `appdb`.`orders` ...

# at 1400
# ... Update_rows ...
### UPDATE `appdb`.`orders`
### WHERE
###   @1=9001
### SET
###   @3='CANCELLED'

# at 1550
# ... Xid = ...
COMMIT/*!*/;
```

Đây là ví dụ minh họa cấu trúc, không phải output cố định cho mọi phiên bản hay mọi `binlog_format`. Những dấu mốc quan trọng khi đọc output của `mysqlbinlog` là:

- `# at N`: vị trí bắt đầu của event trong file binary log.
- `end_log_pos M`: vị trí ngay sau event đó, thường là vị trí bắt đầu của event kế tiếp.
- `GTID` và `SET @@SESSION.GTID_NEXT`: nhận diện giao dịch khi GTID được bật.
- `BEGIN`/`START TRANSACTION` và `Xid`/`COMMIT`: giúp xác định phạm vi của giao dịch.
- `Table_map`, `Write_rows`, `Update_rows`, `Delete_rows`: cho biết bảng và loại thay đổi khi dùng row-based logging.

Muốn phục hồi đến trước một giao dịch, cần dừng tại vị trí bắt đầu của event mở đầu giao dịch đó, thường là GTID event trong chế độ GTID. Không lấy `end_log_pos` của event cuối giao dịch làm điểm dừng trước giao dịch: đó là vị trí sau event, tức giao dịch đã được đọc qua. Với server không dùng GTID, hãy xác định event mở đầu nhóm giao dịch hoặc event chứa câu lệnh sai nếu đó là một statement tự commit.

Một transaction có thể gồm nhiều row event và chỉ hoàn tất tại `Xid`/`COMMIT`. Không dừng giữa các event của cùng transaction. Nếu dừng giữa chừng, đầu ra có thể chứa một phần giao dịch và không đại diện cho trạng thái dữ liệu hợp lệ mà ta muốn phục hồi.

## 2. Bảo toàn log và xác định khoảng thời gian sự cố

Ngay khi phát hiện lỗi, hãy giữ nguyên binary log có liên quan và ngăn cơ chế retention xóa chúng trước khi sao lưu ra nơi an toàn. Thu thập thời gian từ log ứng dụng, audit log, lịch triển khai, thông báo lỗi và người vận hành. Chuẩn hóa các mốc về UTC, đồng thời ghi lại timezone của ứng dụng, MySQL và máy chạy công cụ đọc log.

Trên MySQL 8.4, kiểm tra trạng thái binary log bằng:

```sql
SHOW BINARY LOG STATUS;
SHOW BINARY LOGS;

SELECT
    @@GLOBAL.server_uuid AS server_uuid,
    @@GLOBAL.gtid_mode AS gtid_mode,
    @@GLOBAL.gtid_executed AS gtid_executed,
    @@GLOBAL.gtid_purged AS gtid_purged;

SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
```

Trên phiên bản cũ, `SHOW MASTER STATUS` là tên lệnh thường dùng để xem trạng thái binary log hiện tại. `SHOW BINARY LOG STATUS` hoặc `SHOW MASTER STATUS` chỉ cho biết coordinate hiện tại tại thời điểm chạy lệnh; chúng không tìm ngược được position của sự cố đã xảy ra. `SHOW BINARY LOGS` giúp xác định file nào còn trên server, nhưng phải kiểm tra cả kho lưu trữ log bên ngoài nếu log cũ đã được purge.

Sao chép các file log liên quan cùng checksum, bảo toàn thứ tự file và ghi lại nguồn, thời điểm lấy, kích thước. Không chạy `PURGE BINARY LOGS` trong lúc điều tra. Nếu cần chuyển log từ source, dùng quy trình archive đã được kiểm soát và xác minh bản sao đọc được trước khi thay đổi retention.

Một số thông tin nên ghi vào biên bản sự cố:

| Thông tin | Ví dụ | Mục đích |
|---|---|---|
| Nguồn | `server_uuid`, hostname, phiên bản MySQL | Tránh đọc nhầm log từ máy khác hoặc từ replica khác lịch sử. |
| Cửa sổ thời gian | Từ 10:20 đến 10:35 UTC | Thu hẹp file và vùng event cần phân tích. |
| Phạm vi dữ liệu | `appdb.orders`, các khóa đơn hàng liên quan | Đối chiếu row event với dữ liệu và log ứng dụng. |
| Tác nhân | Tài khoản DB, dịch vụ, migration/job | Tìm câu lệnh hoặc giao dịch khởi phát. |
| Trạng thái log | Danh sách file, checksum, GTID set hiện có | Xác nhận log phục vụ điều tra còn đầy đủ. |

## 3. Dùng thời gian để khoanh vùng event

Nếu đã biết khoảng thời gian gần đúng, dùng `mysqlbinlog` để đọc một đoạn nhỏ thay vì mở toàn bộ lịch sử. Ví dụ với file log đã archive tại máy điều tra:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 10:20:00" \
  --stop-datetime="2026-11-19 10:35:00" \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000120 > incident-window.txt
```

`--start-datetime` và `--stop-datetime` giúp thu hẹp khoảng event theo timestamp. Hãy xác minh timezone được dùng khi diễn giải timestamp và đối chiếu với đồng hồ của ứng dụng. Thời gian thường có độ phân giải đến giây, nên nhiều giao dịch có thể cùng timestamp hoặc nằm rất sát nhau. Event timestamp cũng không thay thế thời điểm commit nghiệp vụ do ứng dụng ghi nhận.

Với sự cố đi qua nhiều file, đọc các file liên tiếp trong khoảng thời gian đó:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 10:20:00" \
  --stop-datetime="2026-11-19 10:35:00" \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000120 mysql-bin.000121 mysql-bin.000122 \
  > incident-window.txt
```

Đây là bước tìm kiếm, chưa phải lệnh phục hồi. Đầu ra có thể chứa nhiều giao dịch hợp lệ cùng khoảng thời gian; không chọn điểm dừng chỉ dựa trên dòng timestamp đầu tiên khớp.

Nếu biết tên bảng hoặc khóa bản ghi bị ảnh hưởng, đối chiếu chúng với event trong cửa sổ thời gian. Với row-based logging, `mysqlbinlog --verbose --base64-output=DECODE-ROWS` giải mã row event thành phần mô tả `###` để con người đọc. Các dòng này là chú thích phân tích, không phải câu SQL có thể chạy trực tiếp. Khi phát lại log, dùng đầu ra `mysqlbinlog` ở chế độ mặc định, không dùng bản đã decode thành chú thích.

## 4. Xác nhận đúng giao dịch gây lỗi

Không nên kết luận một giao dịch là nguyên nhân chỉ vì nó xuất hiện gần thời điểm ứng dụng báo lỗi. Hãy xác nhận ít nhất các điểm sau:

1. Đúng server nguồn và đúng file binary log.
2. Timestamp nằm trong cửa sổ sự cố sau khi đã quy đổi timezone.
3. Schema, bảng, thao tác và khóa bản ghi trùng với phạm vi bị ảnh hưởng.
4. Nội dung before/after image hoặc câu SQL thể hiện đúng thay đổi sai.
5. Đã xác định ranh giới transaction từ event mở đầu đến event commit.

Ví dụ, với row-based logging, một update có thể được hiển thị như sau:

```text
### UPDATE `appdb`.`orders`
### WHERE
###   @1=9001
###   @2='ORD-9001'
###   @3='PAID'
### SET
###   @1=9001
###   @2='ORD-9001'
###   @3='CANCELLED'
```

Các số `@1`, `@2`, `@3` đại diện cho thứ tự cột trong bảng; cần xem `Table_map` và schema tương ứng để hiểu tên, kiểu và ý nghĩa của cột. `binlog_row_image=FULL` ghi hình ảnh hàng đầy đủ hơn. Với `MINIMAL`, before/after image có thể chỉ chứa các cột cần để nhận diện hàng và các cột bị thay đổi; không được giả định các cột không xuất hiện có giá trị rỗng.

Nếu binary log dùng statement-based logging, event có thể chứa câu SQL gốc. Nếu dùng mixed format, một số thao tác có thể được ghi dưới dạng statement, một số dưới dạng row event. Đọc đúng loại event thay vì mặc định mọi log đều chứa câu SQL dễ hiểu.

Có thể dùng `SHOW BINLOG EVENTS` để xem danh sách event và vị trí cơ bản:

```sql
SHOW BINLOG EVENTS
IN 'mysql-bin.000120'
FROM 1200
LIMIT 50;
```

Lệnh này hữu ích để kiểm tra thứ tự event và position. Với row event, nội dung dữ liệu thường cần `mysqlbinlog` để giải mã và phân tích.

## 5. Tìm GTID của giao dịch sai

Nếu `gtid_mode` đang bật, mỗi giao dịch được ghi vào binary log có một GTID. Trong output `mysqlbinlog`, tìm dòng `SET @@SESSION.GTID_NEXT` gần nhóm event chứa thay đổi sai. Ví dụ:

```text
# at 184320
# ... GTID ...
SET @@SESSION.GTID_NEXT='3e11fa47-71ca-11e1-9e33-c80aa9429562:501'/*!*/;
```

Trong ví dụ, GTID của giao dịch là:

```text
3e11fa47-71ca-11e1-9e33-c80aa9429562:501
```

Có thể lọc riêng giao dịch theo GTID để đọc nội dung:

```bash
mysqlbinlog \
  --include-gtids='3e11fa47-71ca-11e1-9e33-c80aa9429562:501' \
  --base64-output=DECODE-ROWS \
  --verbose \
  mysql-bin.000120
```

`--include-gtids` hữu ích để xem giao dịch đã xác định. Nếu không biết GTID, trước hết đọc theo khoảng thời gian và bảng/khóa bị ảnh hưởng rồi lấy GTID từ event. GTID set như `@@GLOBAL.gtid_executed` chỉ cho biết tập giao dịch đã thực thi; bản thân set không chứa mapping trực tiếp từ một GTID sang file/position. Muốn tìm position của GTID, cần đọc binary log có chứa giao dịch đó.

Nếu server không dùng GTID, vẫn có thể xác định transaction bằng file/position và ranh giới event. Trong trường hợp này, không có GTID để lọc hay so sánh; cần giữ cặp file/position cùng thông tin nguồn thật chính xác.

## 6. Tìm file/position để dừng trước giao dịch sai

Khi đã xác nhận giao dịch lỗi, đọc phần đầu của nhóm event đó trong output `mysqlbinlog`. Giả sử output có dạng:

```text
# at 184320
# ... GTID ...
SET @@SESSION.GTID_NEXT='3e11fa47-71ca-11e1-9e33-c80aa9429562:501'/*!*/;

# at 184385
START TRANSACTION
```

Vị trí `184320` là điểm bắt đầu GTID event trong ví dụ. Nếu cần phục hồi đến trạng thái ngay trước giao dịch `...:501`, hãy đặt điểm dừng tại `184320`, tức trước event mở đầu transaction. `end_log_pos` của event trước đó thường trùng với vị trí này, nhưng hãy dùng và kiểm tra `# at` của event mở đầu để tránh nhầm với vị trí kết thúc một event khác.

Với transaction không có GTID, tìm event `BEGIN`/`START TRANSACTION` mở đầu nhóm hoặc event đầu tiên của giao dịch trong file. Với statement tự commit như một số DDL, bản thân event chứa câu lệnh là ranh giới cần dừng trước. Những thao tác DDL có implicit commit; không áp dụng giả định transaction rollback được như DML InnoDB.

Nếu giao dịch nằm trong file `mysql-bin.000122` và có start position `184320`, có thể dùng:

```bash
mysqlbinlog \
  --stop-position=184320 \
  mysql-bin.000122 > before-bad-transaction.sql
```

`--stop-position` dừng trước event đầu tiên có vị trí bằng hoặc lớn hơn mốc được chỉ định. Position là offset trong file được chỉ định, không phải offset dùng chung cho mọi file binary log. Hãy lưu lại tên file cùng position; chỉ ghi `184320` mà thiếu tên file sẽ không xác định được mốc.

Nếu cần bắt đầu từ một backup cũ và phát lại qua nhiều file, `--start-position` áp dụng cho file đầu tiên trong danh sách và `--stop-position` áp dụng cho file cuối cùng. Ví dụ, backup kết thúc ở position `45600` của file đầu tiên và giao dịch lỗi bắt đầu tại position `184320` của file cuối:

```bash
mysqlbinlog \
  --start-position=45600 \
  --stop-position=184320 \
  mysql-bin.000120 mysql-bin.000121 mysql-bin.000122 \
  > replay-before-incident.sql
```

Danh sách file phải liên tục theo thứ tự; không được thiếu file ở giữa. Kiểm tra nội dung file SQL được tạo để chắc chắn nó bắt đầu sau mốc backup và kết thúc trước GTID event của giao dịch sai. Trước khi dùng thật, chạy thử trên một server phục hồi cô lập.

## 7. Dùng mốc thời gian, position và GTID đúng mục đích

| Mốc | Dùng để làm gì | Hạn chế cần nhớ |
|---|---|---|
| Thời gian (`--start-datetime`, `--stop-datetime`) | Khoanh vùng event theo cửa sổ sự cố. | Có thể có nhiều transaction cùng giây; timezone và timestamp cần được xác minh. |
| File/position (`--start-position`, `--stop-position`) | Chỉ định ranh giới đọc chính xác trong binary log. | Position chỉ có nghĩa trong một file cụ thể; phải chọn ranh giới transaction hợp lệ. |
| GTID (`--include-gtids`, `--exclude-gtids`) | Nhận diện hoặc lọc giao dịch trong topology GTID. | GTID không chứa dữ liệu và không tự cho biết file/position nếu chưa đọc log. |

Khi mục tiêu là dừng phục hồi trước giao dịch sai, file/position tại đầu transaction thường là mốc trực tiếp nhất. GTID là bằng chứng nhận diện mạnh để xác nhận đã chọn đúng transaction và đối chiếu với replica. Thời gian là tín hiệu để tìm kiếm, không nên là căn cứ duy nhất cho ranh giới phục hồi chính xác.

`--exclude-gtids` có thể bỏ qua một GTID cụ thể trong luồng đầu ra rồi tiếp tục các giao dịch sau đó:

```bash
mysqlbinlog \
  --exclude-gtids='3e11fa47-71ca-11e1-9e33-c80aa9429562:501' \
  mysql-bin.000120 mysql-bin.000121 \
  > replay-without-one-transaction.sql
```

Đây là cách lọc một transaction, không đồng nghĩa phục hồi đến trước transaction đó. Các giao dịch sau vẫn có thể được phát lại và có thể phụ thuộc vào dữ liệu mà transaction bị bỏ qua tạo ra. Chỉ dùng khi đã phân tích quan hệ phụ thuộc và xác nhận các giao dịch sau vẫn hợp lệ. Nếu cần trạng thái nhất quán trước sự cố, dừng tại đầu transaction lỗi rồi kiểm tra, sau đó quyết định có chọn lọc giao dịch hợp lệ nào cần phát lại.

## 8. Phát lại đến trước thao tác sai trên máy phục hồi

Quy trình an toàn thường bắt đầu từ một backup nhất quán được khôi phục lên server cô lập. Không thử nghiệm lệnh replay trực tiếp trên server production đang chứa dữ liệu bị lỗi. Trước khi chạy, xác nhận:

- Backup và metadata thuộc đúng `server_uuid`/nguồn.
- File/position bắt đầu replay đúng với snapshot.
- Tất cả binary log từ mốc backup đến file có giao dịch lỗi còn đầy đủ và liên tục.
- GTID state trên server đích phù hợp với backup; nếu dump đã thiết lập `GTID_PURGED`, không đánh dấu lại hoặc phát lại các GTID đã có trong snapshot.
- Đích đã được cách ly khỏi ứng dụng ghi dữ liệu trong suốt quá trình phục hồi.

Ví dụ replay từ coordinate backup đến trước transaction lỗi qua ba file:

```bash
mysqlbinlog \
  --start-position=45600 \
  --stop-position=184320 \
  mysql-bin.000120 mysql-bin.000121 mysql-bin.000122 \
  | mysql --host=restore-db.internal --user=recovery
```

Lệnh giả định `mysql-bin.000122:184320` là đầu transaction sai, còn `mysql-bin.000120:45600` là mốc tiếp tục ngay sau snapshot. `mysql` sẽ yêu cầu mật khẩu nếu tài khoản cần xác thực; không đặt mật khẩu thật trong dòng lệnh hoặc lịch sử shell. Thay hostname, tài khoản, file và position bằng thông tin đã xác minh từ manifest và log thực tế.

Sau khi replay, kiểm tra dữ liệu bị ảnh hưởng, số hàng, khóa chính, ràng buộc, các bảng liên quan và trạng thái nghiệp vụ. Đối chiếu với thời điểm trước sự cố nếu có dữ liệu tham chiếu. Khi cần giữ các giao dịch hợp lệ phát sinh sau thao tác sai, hãy lập kế hoạch trích xuất và áp dụng chọn lọc trên bản phục hồi đã kiểm chứng; không tự động replay toàn bộ phần log còn lại.

## 9. Các tình huống dễ xác định sai mốc

| Tình huống | Nguy cơ | Cách kiểm tra |
|---|---|---|
| Đồng hồ ứng dụng và MySQL lệch nhau | Chọn sai cửa sổ thời gian. | Kiểm tra NTP, timezone, log ứng dụng và timestamp event; chuẩn hóa UTC. |
| Nhiều transaction trong cùng một giây | Dừng sau transaction sai hoặc dừng trước quá nhiều giao dịch hợp lệ. | Dùng nội dung event, GTID và file/position để phân biệt. |
| Dừng tại `end_log_pos` của event cuối transaction | Giao dịch sai đã được đưa vào luồng replay. | Xác định `# at` của event mở đầu transaction và dừng tại vị trí đó. |
| Dừng giữa row event hoặc trước `Xid` | Phát lại một phần transaction, tạo luồng không hoàn chỉnh. | Kiểm tra đầy đủ nhóm event từ đầu đến commit; chọn mốc trước transaction. |
| Giao dịch lỗi nằm sát thời điểm rotate log | Bỏ sót file hoặc đọc nhầm position. | Kiểm tra event cuối file trước và event đầu file sau; giữ thứ tự file liên tục. |
| Binary log đã purge khỏi source | Không thể tìm hoặc phát lại giao dịch từ source. | Tìm bản archive; xác minh checksum và khoảng file còn thiếu. |
| Row image ở chế độ `MINIMAL` | Không thấy toàn bộ cột của hàng. | Đối chiếu schema, khóa định danh và các cột được ghi trong before/after image. |
| Một giao dịch ứng dụng gọi nhiều câu SQL | Chỉ nhìn thấy một event và bỏ qua phần còn lại của transaction. | Theo GTID/BEGIN đến Xid hoặc COMMIT, không tách transaction theo từng row event. |
| DDL hoặc câu lệnh tự commit | Giả định rollback transaction không còn đúng. | Xác định implicit commit và phục hồi bằng bản sao trước DDL. |
| Bỏ qua GTID nhưng phát lại giao dịch sau | Giao dịch sau có thể phụ thuộc dữ liệu đã bị bỏ qua. | Kiểm tra phụ thuộc nghiệp vụ và đối soát dữ liệu trước khi chọn lọc replay. |

## 10. Checklist trước khi xác nhận mốc PITR

- [ ] Đã xác định đúng server nguồn và giữ bản sao các binary log liên quan.
- [ ] Đã ghi nhận cửa sổ thời gian, timezone và nguồn chứng cứ của sự cố.
- [ ] Đã xác nhận schema, bảng, loại thao tác và bản ghi bị ảnh hưởng.
- [ ] Đã đọc trọn transaction từ event mở đầu đến commit hoặc event tự commit.
- [ ] Đã ghi GTID nếu có, cùng tên file và position của event mở đầu.
- [ ] Đã chọn `--stop-position` trước transaction sai, không dùng `end_log_pos` của event cuối.
- [ ] Đã kiểm tra đủ các file liên tiếp từ coordinate backup đến mốc dừng.
- [ ] Đã khôi phục và replay thử trên server cô lập.
- [ ] Đã xác minh dữ liệu trước khi quyết định đưa hệ thống phục hồi vào hoạt động.

Một mốc PITR đáng tin cậy phải chỉ rõ **file + position**, mô tả đúng **ranh giới transaction**, và được đối chiếu với **GTID** nếu có. Thời gian giúp tìm ra vùng log cần xem; nội dung row/statement event xác nhận thao tác sai; position tại đầu giao dịch cho phép dừng replay trước khi thay đổi đó được áp dụng. Lưu lại toàn bộ bằng chứng này cùng biên bản phục hồi để lần xử lý sau có thể kiểm tra và tái hiện quyết định.
