# Xem binary log bằng mysqlbinlog và giải mã row event

Binary log ghi lại các thay đổi dữ liệu và sự kiện cần thiết để MySQL replication hoặc khôi phục dữ liệu theo thời điểm (point-in-time recovery, PITR). Khi cần điều tra một giao dịch, xác định thời điểm dữ liệu bị sửa hoặc chuẩn bị phát lại log sau khi phục hồi backup, công cụ chính để đọc binary log là `mysqlbinlog`.

Với log ghi theo định dạng `ROW`, nội dung thay đổi được lưu dưới dạng row event thay vì câu lệnh SQL ban đầu. `mysqlbinlog` có thể giải mã các event này thành biểu diễn dễ đọc để quản trị viên kiểm tra giá trị trước và sau khi cập nhật. Phần giải mã là dạng trình bày phục vụ phân tích; nó không tái tạo chính xác câu SQL mà ứng dụng đã gửi.

Bài học dùng MySQL 8.0/8.4 và công cụ `mysqlbinlog` cùng phiên bản tương thích với máy chủ. Một số tùy chọn và định dạng event có thể khác giữa các bản phát hành; hãy kiểm tra `mysqlbinlog --help` và tài liệu đúng phiên bản khi vận hành hệ thống cụ thể.

## Mục tiêu

Sau bài học, bạn có thể:

- Xác định binary log đang bật, liệt kê file log và đọc vị trí event.
- Dùng `mysqlbinlog` để xem log cục bộ hoặc đọc log từ máy chủ từ xa.
- Giải mã `WRITE_ROWS`, `UPDATE_ROWS` và `DELETE_ROWS` bằng `--base64-output=DECODE-ROWS` và `-vv`.
- Hiểu mối liên hệ giữa GTID, `TABLE_MAP`, row event và ranh giới transaction.
- Đọc `@N`, giá trị trước/sau cập nhật và ảnh hưởng của `binlog_row_image`.
- Lọc log theo vị trí, thời gian hoặc GTID và tránh các lỗi thường gặp khi chuẩn bị PITR.

## 1. Binary log lưu những gì?

Binary log là chuỗi file do máy chủ MySQL ghi ra khi bật binary logging. Nó phục vụ replication, audit ở mức thay đổi dữ liệu và phục hồi bằng cách phát lại các thay đổi sau một bản backup. Binary log không phải bản backup đầy đủ: nó chỉ chứa các event được ghi trong khoảng thời gian tương ứng và cần kết hợp với một bản backup phù hợp để phục hồi dữ liệu.

Kiểm tra trạng thái và cấu hình trên máy chủ:

```sql
-- Kiểm tra binary logging có được bật không.
SHOW VARIABLES LIKE 'log_bin';

-- Xem danh sách file binary log hiện có.
SHOW BINARY LOGS;

-- Xem file log và vị trí ghi hiện tại (MySQL 8.4).
SHOW BINARY LOG STATUS;

-- Kiểm tra định dạng log và cách ghi row image.
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
```

`SHOW BINARY LOG STATUS` là cú pháp hiện hành trong MySQL 8.4; trên các phiên bản cũ hơn, tài liệu có thể dùng `SHOW MASTER STATUS`. Việc bật binary logging cần được cấu hình khi khởi động máy chủ, thường qua `log_bin` trong file cấu hình. Nếu `log_bin` là `OFF`, không có binary log mới để đọc.

Các định dạng ghi log:

| Định dạng | Nội dung chính | Đặc điểm |
|---|---|---|
| `STATEMENT` | Câu lệnh SQL | Log câu lệnh thay đổi dữ liệu; cần lưu ý tính xác định và các hàm phụ thuộc trạng thái. |
| `ROW` | Thay đổi trên từng hàng | Ghi row event; phù hợp cho replication và giải mã thay đổi dữ liệu. |
| `MIXED` | Kết hợp statement và row | MySQL lựa chọn định dạng theo loại câu lệnh và điều kiện an toàn. |

Trong các hệ thống MySQL hiện đại, `ROW` là lựa chọn phổ biến và là mặc định của nhiều cấu hình MySQL 8.x. `binlog_format` đã bị đánh dấu deprecated trong các bản MySQL 8.0 mới; hãy kiểm tra tài liệu của đúng phiên bản trước khi dựa vào khả năng chuyển đổi sang `STATEMENT` hoặc `MIXED`. Dù dùng row-based logging, các lệnh DDL như `CREATE TABLE` hoặc `ALTER TABLE` vẫn được ghi dưới dạng câu lệnh.

## 2. Cấu trúc event trong một giao dịch

Một giao dịch row-based thường chứa một chuỗi event. Các tên dưới đây là những loại thường gặp; tên cụ thể có thể có hậu tố phiên bản như `WRITE_ROWS_EVENTv2`.

| Event | Vai trò |
|---|---|
| `GTID_LOG_EVENT` hoặc `ANONYMOUS_GTID_LOG_EVENT` | Nhận diện giao dịch theo GTID hoặc giao dịch anonymous. |
| `QUERY_EVENT` | Chứa câu lệnh như `BEGIN`, DDL hoặc các câu lệnh được log theo statement. |
| `TABLE_MAP_EVENT` | Ánh xạ table ID trong row event sang database, table và metadata cột. |
| `WRITE_ROWS_EVENT` | Ghi các hàng được thêm (`INSERT`). |
| `UPDATE_ROWS_EVENT` | Ghi ảnh hàng trước và sau cập nhật (`UPDATE`). |
| `DELETE_ROWS_EVENT` | Ghi ảnh hàng bị xóa (`DELETE`). |
| `XID_EVENT` | Đánh dấu commit của giao dịch transactional. |

Một luồng đơn giản có thể được hình dung như sau:

```text
GTID
  |
BEGIN (QUERY_EVENT)
  |
TABLE_MAP (db.orders)
  |
WRITE_ROWS / UPDATE_ROWS / DELETE_ROWS
  |
XID (COMMIT)
```

`TABLE_MAP` rất quan trọng: row event tham chiếu table ID, không lặp lại tên bảng và toàn bộ định nghĩa cột trong từng event. `TABLE_MAP` cung cấp thông tin cần để giải mã row event theo đúng bảng. Nếu giao dịch chứa nhiều bảng, có thể xuất hiện nhiều cặp `TABLE_MAP` và row event.

Với InnoDB, các thay đổi transactional thường kết thúc bằng `XID_EVENT`. Giao dịch có thể gồm nhiều row event nhưng được commit như một đơn vị. Khi đọc log để điều tra hoặc phục hồi, cần xác định ranh giới transaction; phát lại một phần event nằm giữa giao dịch có thể tạo trạng thái không nhất quán.

## 3. Đọc binary log cục bộ bằng mysqlbinlog

`mysqlbinlog` thường được cài cùng bộ công cụ MySQL client. Trên máy có file log, lệnh cơ bản là:

```bash
mysqlbinlog binlog.000123
```

Đầu ra có thể chứa các dòng chú thích và câu lệnh `BINLOG` được mã hóa Base64. Để đọc row event dưới dạng dễ hiểu, dùng:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123
```

Hai tùy chọn quan trọng:

- `--base64-output=DECODE-ROWS` yêu cầu hiển thị row event ở dạng đã giải mã thay vì chỉ trình bày payload Base64.
- `-vv` tương đương bật `--verbose` hai lần; nó in thêm metadata kiểu cột và thông tin nullability để hỗ trợ đọc giá trị.

Có thể lưu đầu ra vào file văn bản để tìm kiếm và đối chiếu:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123 > binlog-decoded.txt
```

Đầu ra `DECODE-ROWS` thường trình bày các row change bằng dòng chú thích bắt đầu với `###`. Các dòng này là bản diễn giải để đọc; không phải câu SQL có thể chạy trực tiếp. Nếu cần giữ payload Base64 để phát lại, hãy dùng chế độ xuất mặc định phù hợp và lưu bản log gốc riêng.

### 3.1. Đọc vị trí và thời gian event

Trong đầu ra `mysqlbinlog`, chú ý các dòng như:

```text
# at 1842
# ... server id 12  end_log_pos 1937  CRC32 0x...
```

- `# at 1842` là vị trí bắt đầu của event trong file.
- `end_log_pos 1937` là vị trí ngay sau event theo thông tin log.
- Timestamp trong header cho biết thời điểm event được ghi; khi đối chiếu với log ứng dụng, cần tính đến múi giờ và độ lệch đồng hồ giữa các máy.

Vị trí là offset byte trong file binary log, không phải số thứ tự giao dịch. Khi cần khoanh vùng một transaction, tìm event GTID/BEGIN tương ứng, các row event của nó và event commit. Nên lưu cả tên file lẫn vị trí vì vị trí chỉ có ý nghĩa bên trong đúng file đó.

### 3.2. Xem nhanh event bằng SQL

Có thể dùng `SHOW BINLOG EVENTS` để xem danh sách event cơ bản:

```sql
SHOW BINLOG EVENTS IN 'binlog.000123' FROM 4 LIMIT 30;
```

Câu lệnh này hữu ích để xem loại event, vị trí và thông tin khái quát. Nó không giải mã đầy đủ giá trị của row event; dùng `mysqlbinlog -vv` khi cần xem nội dung hàng. Với file log lớn, tránh truy vấn không giới hạn vì việc đọc toàn bộ event có thể tốn tài nguyên và tạo đầu ra rất lớn.

## 4. Giải mã row event

Giả sử ứng dụng thực hiện các thao tác sau:

```sql
INSERT INTO sales_db.orders (order_id, status, total)
VALUES (501, 'NEW', 125000);

UPDATE sales_db.orders
SET status = 'PAID'
WHERE order_id = 501;

DELETE FROM sales_db.orders
WHERE order_id = 501;
```

Với `binlog_format=ROW`, MySQL ghi các thay đổi hàng. Khi chạy `mysqlbinlog --base64-output=DECODE-ROWS -vv`, đầu ra minh họa có dạng:

```text
### INSERT INTO `sales_db`.`orders`
### SET
###   @1=501 /* INT meta=0 nullable=0 is_null=0 */
###   @2='NEW' /* VARSTRING(...) ... */
###   @3=125000 /* DECIMAL(...) ... */

### UPDATE `sales_db`.`orders`
### WHERE
###   @1=501 /* INT ... */
###   @2='NEW' /* VARSTRING(...) ... */
###   @3=125000 /* DECIMAL(...) ... */
### SET
###   @2='PAID' /* VARSTRING(...) ... */

### DELETE FROM `sales_db`.`orders`
### WHERE
###   @1=501 /* INT ... */
```

Đây là ví dụ giản lược để minh họa cấu trúc, không phải bản chép nguyên văn đầu ra của mọi phiên bản. Phần `@1`, `@2`, `@3` biểu thị vị trí cột trong thứ tự định nghĩa bảng tại thời điểm event được ghi:

- `INSERT` dùng `### SET` để hiển thị giá trị của hàng được thêm.
- `UPDATE` dùng `### WHERE` cho ảnh hàng trước cập nhật và `### SET` cho ảnh hàng sau cập nhật.
- `DELETE` dùng `### WHERE` để hiển thị ảnh hàng bị xóa.

Các chú thích kiểu dữ liệu như `INT`, `DECIMAL`, `VARSTRING`, `meta`, `nullable` và `is_null` giúp hiểu cách giá trị được giải mã. Một giá trị có thể được hiển thị dưới dạng chuỗi, số, `NULL`, biểu diễn nhị phân hoặc dạng đặc thù tùy kiểu cột và phiên bản công cụ.

### 4.1. Vì sao mysqlbinlog dùng @1, @2 thay vì tên cột?

Row event lưu giá trị theo thứ tự cột và `TABLE_MAP` cung cấp metadata để giải mã. Đầu ra verbose thường đánh số cột là `@1`, `@2`, ... thay vì luôn hiển thị tên cột. Để xác định `@2` là `status` hay một cột khác, cần đối chiếu với định nghĩa bảng có hiệu lực tại thời điểm event được tạo:

```sql
SHOW CREATE TABLE sales_db.orders\G
```

Không nên mặc định schema hiện tại giống schema lúc event được ghi. Nếu bảng đã được `ALTER TABLE` sau đó, thứ tự hoặc kiểu cột có thể đã đổi. Hãy dùng schema snapshot từ backup hoặc metadata migration tại thời điểm cần phân tích. Khi máy chủ được cấu hình `binlog_row_metadata=FULL`, binary log có thể chứa thêm metadata cột; mức metadata `MINIMAL` lưu ít thông tin hơn. Metadata đầy đủ vẫn không thay thế việc đối chiếu đúng phiên bản schema.

### 4.2. Ảnh hàng và binlog_row_image

`binlog_row_image` quyết định MySQL ghi bao nhiêu cột trong row event:

| Giá trị | Nội dung |
|---|---|
| `FULL` | Ghi ảnh đầy đủ của hàng. Với `UPDATE`, có ảnh trước và sau đầy đủ. |
| `MINIMAL` | Chỉ ghi các cột cần để nhận diện hàng và các cột thay đổi. |
| `NOBLOB` | Ghi gần như đầy đủ, nhưng có thể bỏ các cột BLOB/TEXT không thay đổi. |

Với `MINIMAL`, ảnh trước của `UPDATE`/`DELETE` giữ các cột cần thiết để xác định hàng, thường dựa vào primary key hoặc unique key phù hợp; ảnh sau của `UPDATE` chỉ cần các cột thay đổi. Do đó, khi giải mã, bạn có thể không thấy toàn bộ giá trị cũ hoặc toàn bộ hàng. Đây là hành vi có chủ đích nhằm giảm kích thước binary log.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
```

Nếu cần điều tra thay đổi với đầy đủ ảnh hàng, hãy kiểm tra cấu hình tại thời điểm log được tạo. Đổi `binlog_row_image` hôm nay không thể bổ sung những cột đã không được ghi vào các file log cũ. Trong môi trường production, chọn `FULL` hay `MINIMAL` cần cân bằng khả năng điều tra, kích thước log, lưu trữ và yêu cầu replication.

## 5. Đọc binary log từ máy chủ từ xa

Khi file log còn nằm trên máy chủ cơ sở dữ liệu, `mysqlbinlog` có thể đọc trực tiếp qua kết nối client/server:

```bash
mysqlbinlog \
  --read-from-remote-server \
  --host=db.example.internal \
  --port=3306 \
  --user=binlog_reader \
  --password \
  --base64-output=DECODE-ROWS -vv \
  binlog.000123
```

`--password` không kèm giá trị để công cụ hỏi mật khẩu tương tác. Không đặt mật khẩu trực tiếp trong command line vì có thể lộ qua lịch sử shell hoặc danh sách tiến trình. Tài khoản đọc log cần các quyền replication phù hợp với phiên bản MySQL và thao tác được thực hiện. Khi kết nối qua mạng, hãy bật TLS và xác minh chứng thư máy chủ theo chính sách bảo mật của hệ thống.

Nếu mục tiêu là tải bản binary log gốc về máy phân tích, dùng `--raw` cùng `--read-from-remote-server`:

```bash
mysqlbinlog \
  --read-from-remote-server --raw \
  --host=db.example.internal \
  --user=binlog_reader --password \
  --result-file=/secure/binlog-copy/ \
  binlog.000123
```

Ở chế độ `--raw`, công cụ lưu file log thô thay vì in bản giải mã ra stdout. Thư mục đích phải tồn tại và tài khoản hệ điều hành cần quyền ghi. Bảo vệ bản log tải về như dữ liệu nhạy cảm: row event có thể chứa thông tin khách hàng, giao dịch hoặc dữ liệu cá nhân.

## 6. Lọc phạm vi log cần xem

Một file binary log có thể chứa hàng triệu event. Thu hẹp phạm vi giúp phân tích nhanh và tránh đọc nhầm giao dịch.

### 6.1. Lọc theo vị trí

```bash
mysqlbinlog \
  --base64-output=DECODE-ROWS -vv \
  --start-position=1842 \
  --stop-position=5200 \
  binlog.000123
```

`--start-position` và `--stop-position` nhận offset byte trong file log. Hãy lấy offset từ header event của chính file đó và chọn ranh giới transaction. Không dùng vị trí ước lượng giữa một event hoặc giữa các event của cùng giao dịch. Nếu cần phục hồi, ghi lại chính xác tên file, vị trí bắt đầu và vị trí kết thúc để có thể tái lập quy trình.

### 6.2. Lọc theo thời gian

```bash
mysqlbinlog \
  --start-datetime='2026-11-19 09:00:00' \
  --stop-datetime='2026-11-19 09:30:00' \
  --base64-output=DECODE-ROWS -vv \
  binlog.000123
```

Lọc theo thời gian thuận tiện khi đã biết khoảng thời gian sự cố. Tuy nhiên, timestamp event không thay thế việc xác minh vị trí và transaction boundary. Cần kiểm tra múi giờ của máy chủ, máy chạy `mysqlbinlog` và hệ thống ứng dụng trước khi chọn mốc thời gian; các giao dịch sát ranh giới có thể cần kiểm tra thêm.

### 6.3. Lọc theo GTID

Khi GTID được bật, có thể chọn giao dịch theo GTID set:

```bash
mysqlbinlog \
  --include-gtids='3E11FA47-71CA-11E1-9E33-C80AA9429562:1-120' \
  --base64-output=DECODE-ROWS -vv \
  binlog.000123
```

`--include-gtids` chỉ giữ các giao dịch thuộc GTID set; `--exclude-gtids` loại bỏ các giao dịch thuộc set được nêu. GTID set gồm SID (UUID nguồn) và các khoảng transaction number. Hãy lấy GTID từ nguồn tin cậy như log replication hoặc metadata backup, không tự suy đoán SID hay khoảng số.

### 6.4. Lọc theo database

```bash
mysqlbinlog --database=sales_db --base64-output=DECODE-ROWS -vv binlog.000123
```

`--database` có cách áp dụng khác nhau tùy `binlog_format`. Với statement-based logging, việc lọc phụ thuộc database mặc định của session; với row-based logging, việc lọc dựa trên database của các row event. DDL và câu lệnh truy cập nhiều database có thể khiến kết quả không giống suy nghĩ ban đầu. Vì vậy, không dùng `--database` làm ranh giới an toàn duy nhất khi phục hồi dữ liệu quan trọng; phải kiểm tra nội dung log và kế hoạch áp dụng.

## 7. Phân tích một giao dịch UPDATE

Quy trình thực hành sau giúp tìm một thay đổi cụ thể:

1. Xác định file log bao phủ khoảng thời gian nghi vấn bằng `SHOW BINARY LOGS` và thông tin backup/replication.
2. Dùng `mysqlbinlog --base64-output=DECODE-ROWS -vv` để giải mã file hoặc khoảng vị trí liên quan.
3. Tìm tên database/table trong phần `### UPDATE` và xác định `TABLE_MAP` tương ứng.
4. Đối chiếu các cột `@N` với schema tại thời điểm event được ghi.
5. Đọc `### WHERE` như ảnh hàng trước thay đổi và `### SET` như ảnh hàng sau thay đổi; chú ý `binlog_row_image` có thể làm ảnh không đầy đủ.
6. Tìm GTID và event commit để xác định transaction chứa thay đổi.
7. Đối chiếu thời gian, tài khoản ứng dụng, audit log và log nghiệp vụ để tìm nguyên nhân.

Không thể suy ra chắc chắn câu SQL gốc chỉ từ row event. Ví dụ, nhiều câu lệnh khác nhau có thể tạo ra cùng một thay đổi hàng; row event cho biết trạng thái dữ liệu được ghi, không cho biết đầy đủ câu lệnh, điều kiện, biến ứng dụng hay ý định của người dùng. Muốn tìm câu lệnh gốc, cần thêm general log (nếu đã bật), audit log, tracing hoặc log ứng dụng.

## 8. Dùng mysqlbinlog trong quy trình PITR

PITR thường gồm hai phần: phục hồi một bản full backup được tạo trước sự cố, sau đó phát lại binary log từ thời điểm backup đến ngay trước giao dịch gây lỗi. `mysqlbinlog` hỗ trợ chọn phạm vi và xuất log để áp dụng; nó không tự xác định bản backup đúng hoặc tự quyết định giao dịch nào an toàn.

Quy trình khái quát:

```text
Full backup tại T0
       |
       v
Phục hồi backup vào môi trường đích
       |
       v
Xác định binlog file + position hoặc GTID tại T0
       |
       v
Đọc và lọc binlog từ T0 đến trước giao dịch lỗi
       |
       v
Kiểm tra phạm vi và ranh giới transaction
       |
       v
Áp dụng log lên môi trường đã phục hồi
       |
       v
Đối chiếu dữ liệu và xác nhận kết quả
```

Ví dụ xuất một khoảng log để xem trước:

```bash
mysqlbinlog \
  --start-position=120 \
  --stop-position=9800 \
  binlog.000123 > replay-candidate.sql
```

Đối với phát lại thực tế, quy trình thường chuyển đầu ra phù hợp của `mysqlbinlog` tới client `mysql` kết nối vào máy chủ đã phục hồi. Trước khi làm điều đó, cần xác minh:

- Backup và binary log thuộc cùng chuỗi dữ liệu và không thiếu file log trung gian.
- File/position hoặc GTID bắt đầu khớp với metadata của backup.
- Điểm dừng nằm trước giao dịch gây lỗi và không cắt ngang một transaction cần giữ.
- Các event được chọn không tác động ngoài phạm vi dự kiến, đặc biệt khi có DDL hoặc nhiều database.
- Máy đích đã được phục hồi đúng trạng thái và có bản sao an toàn để quay lui nếu cần.

Không phát lại file được tạo bằng `--base64-output=DECODE-ROWS` như thể đó là SQL phục hồi. Các row event đã giải mã được trình bày thành chú thích `###`; chúng dành cho con người đọc. Khi cần replay, phải tạo đầu ra ở chế độ phù hợp để giữ các câu lệnh `BINLOG` cần thiết và áp dụng theo quy trình PITR đã kiểm chứng.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tìm thấy file log | Sai thư mục, sai tên file hoặc log đã bị purge | Kiểm tra `SHOW BINARY LOGS`, `log_bin_basename` và chính sách lưu giữ. |
| Không đọc được log từ xa | Sai host/port, quyền replication chưa đủ hoặc TLS không hợp lệ | Kiểm tra kết nối, tài khoản, quyền và cấu hình TLS. |
| Chỉ thấy Base64, không thấy giá trị hàng | Chưa bật chế độ giải mã row event | Dùng `--base64-output=DECODE-ROWS -vv`. |
| Chỉ thấy một số cột | `binlog_row_image=MINIMAL` hoặc `NOBLOB` | Kiểm tra cấu hình tại thời điểm event được ghi. |
| Không biết `@2` là cột nào | Thiếu schema đúng thời điểm | Đối chiếu `SHOW CREATE TABLE` từ schema snapshot hoặc backup tương ứng. |
| Không thấy câu SQL UPDATE gốc | Log dùng row-based format | Dùng audit/general/application log nếu đã được thu thập. |
| Phát lại log bị lỗi hoặc dữ liệu sai | Sai điểm bắt đầu, thiếu file log, transaction bị cắt hoặc schema không khớp | Kiểm tra backup metadata, GTID/position và ranh giới transaction. |
| File log rất lớn hoặc đầu ra quá nhiều | Đọc cả file hoặc bật hexdump không cần thiết | Thu hẹp bằng vị trí, thời gian hoặc GTID; chỉ dùng `--hexdump` khi phân tích byte-level. |

Một số tùy chọn hữu ích khác:

```bash
# Xác minh checksum event khi đọc file log.
mysqlbinlog --verify-binlog-checksum binlog.000123

# Hiển thị hexdump để điều tra dữ liệu ở mức byte.
mysqlbinlog --hexdump binlog.000123

# Xem cú pháp và tùy chọn được hỗ trợ bởi bản cài đặt.
mysqlbinlog --help
```

`--hexdump` dành cho phân tích sâu và có thể tạo đầu ra rất dài. Chỉ dùng khi cần xem cấu trúc byte hoặc điều tra lỗi giải mã. Không chỉnh sửa trực tiếp binary log; nếu file hỏng, hãy giữ nguyên bản gốc để điều tra và khôi phục từ bản sao đáng tin cậy.

## 10. Nguyên tắc vận hành an toàn

1. **Giữ binary log đủ lâu.** Thời gian lưu phải bao phủ cửa sổ backup, replication lag và mục tiêu PITR. Purge log quá sớm có thể làm mất khả năng phục hồi.
2. **Lưu metadata backup.** Ghi nhận binlog file/position hoặc GTID tại thời điểm backup để biết điểm bắt đầu replay.
3. **Bảo vệ file log.** Binary log có thể chứa dữ liệu nhạy cảm; giới hạn quyền đọc, mã hóa nơi lưu trữ và kiểm soát bản sao.
4. **Dùng công cụ tương thích.** Ưu tiên `mysqlbinlog` cùng phiên bản hoặc phiên bản được MySQL hỗ trợ cho định dạng log nguồn.
5. **Giữ transaction nguyên vẹn.** Chọn start/stop position tại ranh giới event phù hợp và xác minh giao dịch cuối cùng được giữ.
6. **Đối chiếu schema theo thời điểm.** Không dùng schema hiện tại để diễn giải event cũ nếu bảng đã thay đổi cấu trúc.
7. **Phân biệt đọc và replay.** Đầu ra giải mã row event để đọc không phải script replay.
8. **Thử PITR trên môi trường cô lập.** Kiểm tra dữ liệu sau phục hồi trước khi chuyển kết quả vào production.

## 11. Bài tập tự kiểm tra

1. Vì sao `SHOW BINLOG EVENTS` không thay thế được `mysqlbinlog -vv` khi cần xem giá trị của một hàng?
2. Trong đầu ra row event, `### WHERE` và `### SET` của một `UPDATE` biểu thị điều gì?
3. Nếu `binlog_row_image=MINIMAL`, vì sao có thể chỉ thấy primary key và các cột thay đổi?
4. Một event cho biết `@3='PAID'`. Bạn cần nguồn thông tin nào để biết `@3` là cột `status`?
5. Vì sao không nên dùng đầu ra `--base64-output=DECODE-ROWS` làm script replay PITR?
6. Khi lọc theo thời gian, những yếu tố nào có thể khiến bạn chọn sai ranh giới giao dịch?

**Gợi ý đáp án:** (1) `SHOW BINLOG EVENTS` chỉ liệt kê thông tin event khái quát; `mysqlbinlog -vv` giải mã payload row event. (2) `WHERE` là ảnh hàng trước cập nhật dùng để nhận diện/biểu diễn hàng cũ; `SET` là các giá trị sau cập nhật. (3) `MINIMAL` chỉ ghi cột cần để nhận diện hàng và cột có thay đổi nhằm giảm dung lượng log. (4) Schema snapshot đúng tại thời điểm event được ghi, với thứ tự cột tương ứng. (5) Bản giải mã trình bày row event thành chú thích để đọc, không giữ payload replay theo cách cần thiết. (6) Múi giờ, lệch đồng hồ, độ chính xác timestamp và transaction kéo dài qua ranh giới thời gian.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: mysqlbinlog — Utility for Processing Binary Log Files](https://dev.mysql.com/doc/refman/8.4/en/mysqlbinlog.html)
- [MySQL 8.4 Reference Manual: mysqlbinlog Row Event Display](https://dev.mysql.com/doc/refman/8.4/en/mysqlbinlog-row-events.html)
- [MySQL 8.4 Reference Manual: Binary Log](https://dev.mysql.com/doc/refman/8.4/en/binary-log.html)
- [MySQL 8.4 Reference Manual: Binary Log Options and Variables](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html)
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html)
