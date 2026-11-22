# Phạm vi lọc khi phát lại log và nguy cơ thiếu phụ thuộc giao dịch

Trong module **DATABASE_MYSQL**, binary log là một phần quan trọng của sao lưu và phục hồi. Sau khi khôi phục bản backup nền, quản trị viên có thể phát lại các sự kiện trong binary log để đưa dữ liệu đến một thời điểm mong muốn. Với hệ thống nhiều schema, đôi khi cần chỉ phát lại một schema bằng tùy chọn lọc. Cách làm này cần được đánh giá kỹ vì phạm vi lọc phụ thuộc vào định dạng ghi log và ngữ cảnh thực thi của câu lệnh.

Bài học này tập trung vào `mysqlbinlog --database`, sự khác nhau giữa statement-based và row-based logging, hành vi của MIXED, cùng nguy cơ bỏ sót thay đổi có liên quan trong một giao dịch nhiều schema. Mục tiêu là xây dựng quy trình PITR có thể kiểm chứng, giữ nguyên tính nhất quán và tránh tạo ra một trạng thái dữ liệu chỉ đúng một phần.

Trong phạm vi DATABASE_MYSQL, chủ đề này bổ sung cho việc làm chủ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời; nó cũng liên quan đến đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và bối cảnh

Sau bài học, bạn có thể:

- Giải thích binary log lưu thay đổi theo statement, row event và nhóm giao dịch.
- Phân biệt cách `mysqlbinlog --database` lọc log theo từng định dạng ghi.
- Dự đoán trường hợp một câu lệnh bị đưa vào hoặc bị loại khỏi đầu ra dù tên schema trong câu SQL có vẻ phù hợp.
- Nhận diện giao dịch cập nhật nhiều schema, trigger hoặc routine có tác động phụ thuộc.
- Chọn cách khôi phục toàn bộ log hay lọc theo schema dựa trên yêu cầu nhất quán.
- Kiểm tra mốc backup, GTID, tọa độ log và kết quả phục hồi trước khi đưa dữ liệu trở lại sử dụng.

Binary log ghi lại các sự kiện thay đổi dữ liệu và một số thay đổi cấu trúc theo thứ tự. Tùy cấu hình, sự kiện có thể chứa câu SQL hoặc mô tả thay đổi hàng. Khi giao dịch InnoDB được commit, các sự kiện của giao dịch được ghi theo nhóm để có thể phát lại theo thứ tự. Vì vậy, phạm vi lọc cần được xem xét cùng ranh giới giao dịch, không chỉ theo tên bảng.

Một quy trình PITR thông thường gồm:

1. Khôi phục bản full backup phù hợp.
2. Xác định vị trí hoặc GTID của bản backup làm điểm bắt đầu.
3. Thu thập chuỗi binary log liên tục từ điểm đó.
4. Phát lại sự kiện theo thứ tự đến trước thời điểm hoặc giao dịch cần loại bỏ.
5. Kiểm tra dữ liệu và các ràng buộc nghiệp vụ trước khi mở dịch vụ.

Nếu cần khôi phục một schema riêng, bước lọc có thể làm thay đổi tập sự kiện được phát lại. Đó là lý do cần hiểu chính xác quy tắc lọc trước khi chạy lệnh trên máy chủ đích.

## 2. Ba định dạng ghi binary log

MySQL hỗ trợ ba định dạng ghi chính:

| Định dạng | Nội dung ghi | Cách phát lại |
|---|---|---|
| STATEMENT | Câu lệnh SQL đã thực thi cùng ngữ cảnh cần thiết | Thực thi lại câu SQL |
| ROW | Sự kiện mô tả hàng được thêm, sửa hoặc xóa | Áp dụng thay đổi hàng |
| MIXED | Kết hợp statement và row tùy loại câu lệnh | Phụ thuộc định dạng thực tế của từng sự kiện |

Kiểm tra cấu hình hiện tại:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
~~~

Giá trị `binlog_format` hiện tại không chứng minh mọi sự kiện lịch sử đều được ghi theo cùng định dạng. MIXED có thể đổi định dạng theo từng câu lệnh; một số thao tác như DDL vẫn được ghi dưới dạng câu lệnh. Khi phân tích log cũ, hãy đọc chính các sự kiện trong file thay vì chỉ dựa vào cấu hình hiện tại.

Có thể xem nội dung binary log để điều tra:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  /archive/mysql-bin.000123 > /tmp/binlog-inspect.sql
~~~

`-vv` và `DECODE-ROWS` giúp hiển thị chi tiết row event dưới dạng chú thích dễ đọc. Đây là chế độ phục vụ kiểm tra; không dùng đầu ra đã giải mã này làm luồng thực thi phục hồi. Khi cần tái thực thi log, giữ chế độ xuất mặc định để `mysqlbinlog` tạo đầy đủ các câu lệnh `BINLOG` cần thiết cho row event.

## 3. Quy tắc của mysqlbinlog --database

Tùy chọn `--database=db_name` (viết tắt `-d`) lọc các mục được xuất từ binary log cục bộ. Nó chỉ nhận một schema; nếu truyền nhiều lần, lần xuất hiện cuối cùng được sử dụng. Quy tắc lọc phụ thuộc vào định dạng của sự kiện.

### 3.1. Statement-based logging: lọc theo database mặc định

Với STATEMENT, `mysqlbinlog --database=shop` xét schema mặc định được chọn bởi câu lệnh `USE`. Nó không đơn giản kiểm tra mọi tên schema được ghi đầy đủ trong câu SQL.

Ví dụ:

~~~sql
USE audit;
UPDATE shop.orders
SET status = 'PAID'
WHERE order_id = 1001;
~~~

Dù câu lệnh cập nhật bảng `shop.orders`, schema mặc định là `audit`. Khi lọc log bằng `--database=shop`, câu lệnh trên có thể bị loại khỏi đầu ra vì `shop` không phải schema mặc định tại thời điểm câu lệnh được ghi.

Chiều ngược lại cũng có thể xảy ra:

~~~sql
USE shop;
INSERT INTO audit.order_events(order_id, event_type)
VALUES (1001, 'PAID');
~~~

Schema mặc định là `shop`, nên `--database=shop` có thể giữ câu lệnh này dù bảng đích thuộc schema `audit`.

Điều đó tạo ra hai rủi ro:

- **Bỏ sót thay đổi cần khôi phục:** câu lệnh có bảng thuộc schema đích nhưng được thực thi khi schema mặc định khác.
- **Phát lại thay đổi ngoài phạm vi dự kiến:** câu lệnh được giữ vì schema mặc định khớp, dù nó tác động đến schema khác.

Tên bảng có tiền tố schema trong câu SQL không làm thay đổi ngữ cảnh `USE`. Ngoại lệ được MySQL xử lý riêng là `CREATE DATABASE`, `ALTER DATABASE` và `DROP DATABASE`: schema được tạo, sửa hoặc xóa được dùng để xét điều kiện lọc.

### 3.2. Row-based logging: lọc theo schema của bảng thay đổi

Với ROW, `mysqlbinlog --database=shop` giữ những sự kiện làm thay đổi bảng thuộc schema `shop`. Schema mặc định được chọn bằng `USE` không quyết định kết quả lọc.

Ví dụ:

~~~sql
USE audit;
UPDATE shop.orders
SET status = 'PAID'
WHERE order_id = 1001;
~~~

Ở định dạng ROW, các row event của `shop.orders` vẫn thuộc phạm vi `shop` và có thể được đưa vào đầu ra được lọc.

Ngược lại:

~~~sql
USE shop;
INSERT INTO audit.order_events(order_id, event_type)
VALUES (1001, 'PAID');
~~~

Row event thay đổi bảng `audit.order_events`, nên nó không thuộc phạm vi `--database=shop`, dù schema mặc định là `shop`.

Khác biệt này rất quan trọng khi một giao dịch ghi vào nhiều schema. Nếu một giao dịch cập nhật `shop.orders` và thêm sự kiện vào `audit.order_events`, bộ lọc ROW có thể chỉ giữ phần thay đổi của `shop` và bỏ phần thay đổi của `audit`. Khi phát lại, dữ liệu có thể không còn phản ánh đầy đủ một giao dịch nghiệp vụ ban đầu.

### 3.3. Mixed và DDL

MIXED sử dụng cả statement event và row event. Do đó, cùng một tùy chọn `--database` có thể áp dụng hai cách lọc khác nhau trong cùng một file log:

- Sự kiện ghi theo statement được xét theo schema mặc định.
- Row event được xét theo schema của bảng thay đổi.
- DDL như `CREATE TABLE` và `ALTER TABLE` được ghi dưới dạng câu lệnh, nên áp dụng quy tắc statement.

Với MIXED, nếu muốn lọc log theo schema, cần bảo đảm các bảng bị thay đổi nằm trong schema được chọn bằng `USE`; đặc biệt tránh câu lệnh cập nhật chéo schema. Trong thực tế, điều này khó bảo đảm nếu ứng dụng dùng trigger, stored routine hoặc câu lệnh có tên bảng định danh đầy đủ.

Bảng dưới đây tóm tắt cách hiểu:

| Trường hợp | STATEMENT | ROW | MIXED |
|---|---|---|---|
| `USE audit`, cập nhật `shop.orders` | Lọc theo `audit` | Lọc theo `shop` | Theo định dạng sự kiện |
| `USE shop`, ghi vào `audit.order_events` | Lọc theo `shop` | Lọc theo `audit` | Theo định dạng sự kiện |
| DDL như `CREATE TABLE` | Theo schema mặc định và quy tắc ngoại lệ của database DDL | Vẫn là statement event | Theo quy tắc statement |
| Một giao dịch ghi vào nhiều schema | Giữ/bỏ câu lệnh theo default database; có thể bao gồm tác động nhiều schema | Có thể chỉ giữ row event của schema được chọn | Có thể trộn cả hai kiểu lọc |

Không suy ra kết quả chỉ từ câu SQL hiển thị. Cần đọc sự kiện thực tế, biết định dạng được dùng khi ghi và thử đầu ra trong môi trường phục hồi cô lập.

## 4. Giao dịch nhiều schema và phụ thuộc dữ liệu

### 4.1. Một giao dịch có thể đại diện cho nhiều thay đổi nghiệp vụ

Một ứng dụng bán hàng có thể cập nhật đơn hàng, ghi sổ thanh toán và tạo sự kiện kiểm toán trong cùng một giao dịch:

~~~sql
USE shop;

START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

INSERT INTO audit.order_events(order_id, event_type, created_at)
VALUES (1001, 'PAID', NOW());

INSERT INTO accounting.payment_ledger(order_id, amount, created_at)
VALUES (1001, 250000, NOW());

COMMIT;
~~~

Đây là một đơn vị nghiệp vụ: đơn hàng đã thanh toán, sự kiện kiểm toán được ghi và sổ thanh toán được cập nhật. Nếu phục hồi chỉ giữ thay đổi của `shop`, trạng thái đơn hàng có thể là `PAID` nhưng audit và ledger không có bản ghi tương ứng. Nếu lọc theo schema khác, sổ thanh toán có thể tồn tại mà đơn hàng chưa chuyển trạng thái.

Các phụ thuộc có thể nằm ở:

- Bảng nghiệp vụ và bảng lịch sử/audit.
- Bảng tổng hợp, bảng đối soát hoặc bảng outbox.
- Trigger ghi thêm dữ liệu khi bảng chính thay đổi.
- Stored procedure hoặc function đọc/ghi nhiều schema.
- Các quy tắc nghiệp vụ được ứng dụng thực hiện trong cùng một giao dịch.
- Các thao tác DDL và dữ liệu được triển khai theo một trình tự phụ thuộc.

Không phải mọi phụ thuộc đều được MySQL biểu diễn thành khóa ngoại. Một giao dịch có thể cần nhiều bảng để duy trì tính đúng đắn theo nghiệp vụ dù cơ sở dữ liệu không có ràng buộc trực tiếp giữa chúng.

### 4.2. Điều gì xảy ra khi lọc bỏ một phần?

Với row-based logging, bộ lọc theo schema có thể bỏ các row event thuộc schema khác trong khi vẫn giữ thay đổi của schema được chọn. Kết quả phát lại có thể thể hiện một phần của giao dịch ban đầu.

Các hậu quả thường gặp:

- Trạng thái đơn hàng không khớp với sổ thanh toán.
- Bảng chính có dữ liệu nhưng bảng audit hoặc outbox thiếu sự kiện.
- Bản ghi tổng hợp không khớp với dữ liệu chi tiết.
- Quy trình downstream không nhận được sự kiện cần thiết.
- Một lần phục hồi sau đó không thể tái tạo trạng thái nghiệp vụ như ban đầu chỉ bằng cách phát lại phần log đã lọc.

Với statement-based logging, bộ lọc có thể giữ cả câu lệnh có tác động đến schema ngoài phạm vi, hoặc bỏ câu lệnh cập nhật schema đích vì `USE` đang chọn schema khác. Vì vậy, lọc theo schema không đồng nghĩa với việc cắt bỏ chính xác mọi thao tác ngoài schema đó.

Ranh giới giao dịch ở cấp MySQL vẫn có ý nghĩa khi phát lại, nhưng việc lọc sự kiện có thể làm mất các thay đổi cần thiết để bảo toàn ý nghĩa nghiệp vụ của giao dịch. Một giao dịch còn lại một phần sự kiện không còn tương đương với giao dịch ban đầu.

### 4.3. GTID không tự sửa được phần thay đổi bị thiếu

GTID nhận diện giao dịch trong chuỗi binary log và hỗ trợ theo dõi giao dịch đã thực thi. GTID không tự phân tích quan hệ nghiệp vụ giữa các schema và cũng không bổ sung các row event đã bị bộ lọc loại bỏ.

Nếu đầu ra phát lại giữ thông tin GTID của giao dịch nhưng chỉ còn một phần thay đổi, trạng thái GTID sau phục hồi có thể khiến việc phát lại lại cùng giao dịch không phải là cách an toàn để bù phần bị thiếu. Không chỉnh sửa GTID hoặc ghép log thủ công để chữa một bản phục hồi đã lọc khi chưa hiểu trạng thái thực tế. Hãy khôi phục lại từ mốc sạch và thực hiện quy trình đã kiểm chứng.

## 5. Phân biệt các lớp lọc

Tên tùy chọn gần giống nhau nhưng thời điểm áp dụng khác nhau:

| Cơ chế | Áp dụng ở đâu? | Tác động |
|---|---|---|
| `mysqlbinlog --database` | Khi đọc và xuất binary log cục bộ | Lọc nội dung được xuất để kiểm tra hoặc phát lại |
| `--binlog-do-db` / `--binlog-ignore-db` | Trên máy chủ ghi binary log | Quyết định sự kiện nào được ghi vào binary log |
| `replicate-do-db` / `replicate-ignore-db` | Trên replica khi áp dụng sự kiện replication | Quyết định sự kiện nào được áp dụng trên replica |

Không dùng `mysqlbinlog --database` để suy luận rằng binary log gốc đã được ghi đầy đủ. Nếu nguồn đã loại bỏ thay đổi bằng `--binlog-do-db` hoặc `--binlog-ignore-db`, những sự kiện không được ghi có thể không tồn tại trong chuỗi log để PITR. Cần kiểm tra cấu hình nguồn, định dạng log và phạm vi dữ liệu đã ghi từ trước.

Quy tắc lọc của replication cũng phụ thuộc vào định dạng log. Đừng lấy kết quả của một thử nghiệm `mysqlbinlog --database` rồi mặc định rằng nó giống hoàn toàn với quy tắc lọc của replica. Hai cơ chế phục vụ các giai đoạn khác nhau và cần được kiểm thử riêng.

## 6. Quy trình điều tra trước khi lọc log

Trước khi tạo luồng SQL phục hồi, hãy thu thập các thông tin sau:

1. **Mục tiêu khôi phục:** cần khôi phục toàn máy chủ, một schema, một bảng hay chỉ một nhóm bản ghi?
2. **Mốc dữ liệu nền:** backup nào được chọn, thời điểm hoàn tất và GTID set hoặc tọa độ binary log tương ứng?
3. **Chuỗi log:** có đủ các file theo thứ tự, không thiếu đoạn hoặc bị hỏng không?
4. **Định dạng sự kiện:** STATEMENT, ROW hay MIXED; có DDL, trigger hoặc routine liên quan không?
5. **Phạm vi phụ thuộc:** giao dịch có chạm nhiều schema hoặc ghi vào bảng audit, ledger, outbox, summary không?
6. **Mốc dừng:** cần dừng trước giao dịch nào, tại timestamp hay vị trí event nào?
7. **Môi trường đích:** có phải bản sao cô lập tương thích phiên bản, charset, collation, engine và plugin cần thiết không?

Các lệnh kiểm tra cơ bản:

~~~sql
SHOW BINARY LOGS;
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
~~~

`SHOW BINARY LOGS` cho biết các file log hiện có trên máy chủ đang truy vấn. Với kho lưu trữ ngoài máy chủ, cần đối chiếu manifest và danh sách file đã chuyển. Giá trị `binlog_format` là cấu hình hiện tại; nó không thay thế việc kiểm tra sự kiện lịch sử.

Đọc log với chế độ hiển thị chi tiết:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  --start-position=12345 \
  /archive/mysql-bin.000123
~~~

Kiểm tra các dấu mốc `GTID`, `BEGIN`, `COMMIT`/`Xid`, `Query`, `Table_map` và row event. Ghi nhận `# at` và `end_log_pos` để xác định vị trí sự kiện. Nếu giao dịch có nhiều schema, lập danh sách tất cả bảng bị tác động trong cùng nhóm giao dịch trước khi quyết định lọc.

Không dùng `SHOW GLOBAL VARIABLES LIKE 'binlog_format'` làm bằng chứng duy nhất rằng toàn bộ file log được ghi theo một định dạng. Hãy kiểm tra sự kiện và cấu hình lịch sử có liên quan.

## 7. Chọn chiến lược phục hồi

### 7.1. Khôi phục toàn bộ log rồi tách dữ liệu sau

Đây thường là cách dễ bảo toàn phụ thuộc nhất khi cần khôi phục một schema từ máy chủ có nhiều schema:

1. Tạo một máy chủ khôi phục cô lập có cấu hình tương thích.
2. Khôi phục đầy đủ bản backup nền, bao gồm các schema liên quan.
3. Phát lại binary log đầy đủ, không dùng `--database` để cắt bỏ sự kiện.
4. Kiểm tra dữ liệu và trạng thái tại mốc cần phục hồi.
5. Trích xuất schema hoặc bảng mục tiêu từ môi trường khôi phục.
6. Đưa dữ liệu đã kiểm tra vào hệ thống đích theo quy trình triển khai riêng.

Cách này giữ lại những thay đổi phụ thuộc giữa các schema trong quá trình phát lại. Sau đó, có thể quyết định dữ liệu nào cần chuyển sang môi trường đích. Việc trích xuất vẫn cần kiểm tra các phụ thuộc nghiệp vụ nếu schema đích được sử dụng độc lập.

### 7.2. Chỉ lọc khi phạm vi dữ liệu thực sự độc lập

Có thể cân nhắc `--database` khi:

- Schema đích không có giao dịch ghi chéo schema.
- Không có trigger, routine hoặc luồng nghiệp vụ tạo tác động phụ thuộc ngoài schema.
- Định dạng ghi log đã được xác định và quy tắc lọc đã được kiểm tra.
- Mốc bắt đầu và kết thúc không cắt ngang giao dịch cần giữ.
- Đầu ra được phát lại thành công trong môi trường thử nghiệm và dữ liệu đạt kiểm tra nghiệp vụ.

Ví dụ tạo đầu ra được lọc để xem xét:

~~~bash
mysqlbinlog --database=shop \
  --start-position=12345 \
  --stop-position=67890 \
  /archive/mysql-bin.000123 \
  > /tmp/shop-filtered.sql
~~~

Đây là bước tạo file để kiểm tra. Không đưa trực tiếp đầu ra này vào production chỉ vì lệnh chạy thành công. Hãy đọc file, xác định các giao dịch được giữ, so sánh với sự kiện gốc và chạy thử trên clone trước.

Nếu đã chứng minh phạm vi lọc an toàn, có thể phát lại trong môi trường thử nghiệm:

~~~bash
set -o pipefail
mysqlbinlog --database=shop \
  --start-position=12345 \
  --stop-position=67890 \
  /archive/mysql-bin.000123 \
  | mysql --login-path=pitr-test
~~~

Ví dụ chỉ minh họa một file log. Khi cần nhiều file, truyền tất cả file theo thứ tự đúng và bảo đảm không thiếu khoảng giữa các file. Không ghép các file bằng cách sắp xếp tên không kiểm chứng; dùng danh sách log và metadata từ nguồn backup.

### 7.3. Khi không thể chứng minh độc lập

Nếu không thể xác nhận schema không có phụ thuộc, hãy phục hồi toàn bộ vào môi trường cô lập rồi trích xuất sau. Nếu không thể khôi phục toàn bộ vì thiếu backup hoặc log, hãy xác định rõ phần dữ liệu có thể khôi phục, phần thiếu và ảnh hưởng nghiệp vụ; không gắn nhãn kết quả là PITR đầy đủ.

## 8. Mốc bắt đầu, mốc dừng và ranh giới giao dịch

PITR cần bắt đầu đúng vị trí của backup nền và dừng đúng trước hoặc sau giao dịch mục tiêu theo yêu cầu. Tọa độ position thuộc về một file binary log cụ thể; không dùng một position của file này cho file khác.

Các nguyên tắc:

- Lấy GTID set hoặc file/position từ metadata của backup, không ước lượng từ thời điểm file được tạo.
- Phát lại log theo thứ tự file và sự kiện.
- Chọn mốc dừng ở ranh giới giao dịch đã xác định.
- Khi loại bỏ một giao dịch gây lỗi, xác định event bắt đầu của giao dịch đó và kiểm tra các giao dịch trước/sau.
- Đối chiếu thời gian trong log với múi giờ và timestamp thực tế của hệ thống.
- Giữ nguyên bản gốc của binary log; tạo bản làm việc và manifest riêng.

Có thể dùng `--start-position`, `--stop-position`, `--start-datetime` hoặc `--stop-datetime` của `mysqlbinlog` để giới hạn phạm vi đọc. Timestamp thường có độ hạt và cách diễn giải phụ thuộc môi trường; khi cần độ chính xác cao, ưu tiên tọa độ event hoặc GTID đã được xác minh. Không chọn một `stop-position` tùy ý nằm giữa các event của giao dịch.

Ví dụ phát lại log không lọc schema:

~~~bash
set -o pipefail
mysqlbinlog \
  --start-position=12345 \
  --stop-position=67890 \
  /archive/mysql-bin.000123 \
  /archive/mysql-bin.000124 \
  | mysql --login-path=pitr-test
~~~

Đây là mô hình phát lại liên tục từ hai file đã xác minh. Với GTID, cần kiểm tra trạng thái GTID của backup và máy chủ đích để tránh áp dụng lặp hoặc bỏ qua giao dịch. Không trộn lẫn quy trình phục hồi theo file/position và quy trình quản lý GTID mà không có kế hoạch rõ ràng.

## 9. Kiểm tra sau khi phát lại

Sau khi phục hồi, kiểm tra ít nhất bốn lớp:

**Tính toàn vẹn cấu trúc**

- Bảng, index, view, trigger, routine và event cần thiết tồn tại.
- Charset, collation, engine và định nghĩa cột đúng phiên bản mong muốn.
- Các tài khoản và quyền cần thiết đã được phục hồi theo chính sách.

**Tính toàn vẹn dữ liệu**

- Số hàng ở các bảng quan trọng.
- Khóa chính, khóa duy nhất và các quan hệ dữ liệu.
- Giá trị tổng hợp như số dư, tổng đơn hàng, tổng thanh toán.
- Bản ghi audit, ledger và outbox có tương ứng với thay đổi bảng chính không.

**Tính nhất quán nghiệp vụ**

- Một đơn hàng đã thanh toán phải có bản ghi thanh toán tương ứng.
- Một thay đổi trạng thái phải có sự kiện kiểm toán nếu nghiệp vụ yêu cầu.
- Số liệu tổng hợp phải khớp dữ liệu chi tiết.
- Không có bản ghi mồ côi hoặc sự kiện downstream bị bỏ sót.

**Khả năng tiếp tục vận hành**

- Ứng dụng kết nối được và truy vấn chính chạy đúng.
- Job nền, event scheduler và luồng đồng bộ có trạng thái phù hợp.
- GTID hoặc tọa độ phục hồi được ghi lại.
- Thời gian phục hồi và điểm dữ liệu đạt RTO/RPO đã thống nhất.

Kiểm tra vài hàng mẫu không đủ để chứng minh toàn bộ giao dịch đã được phục hồi. Hãy chọn các invariant nghiệp vụ có thể đo được và so sánh trước/sau bằng truy vấn hoặc báo cáo đối soát.

## 10. Lỗi thường gặp khi lọc và phát lại

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Không thấy cập nhật bảng mục tiêu trong output | Statement event được ghi khi schema mặc định khác schema mục tiêu | Kiểm tra `USE` và định dạng event; không chỉ tìm tên bảng |
| Output chứa thao tác ở schema ngoài phạm vi | Statement event được giữ vì default database khớp | Kiểm tra toàn bộ bảng mà câu lệnh hoặc routine tác động |
| Thiếu bản ghi audit/ledger sau restore | Row event của schema phụ thuộc bị bộ lọc loại | Phân tích giao dịch nhiều schema và phát lại toàn bộ trong clone |
| Cùng một lệnh lọc cho kết quả khác nhau giữa môi trường | Định dạng log khác nhau hoặc MIXED đổi theo từng sự kiện | Đọc event thực tế, kiểm tra định dạng theo sự kiện |
| DDL bị lọc khác với dự đoán | DDL được ghi dưới dạng statement event | Xét schema mặc định và quy tắc DDL riêng |
| PITR thiếu một khoảng thay đổi | Thiếu file log, source đã lọc log hoặc mốc backup sai | Đối chiếu manifest, GTID, position và cấu hình nguồn |
| Phát lại lỗi do giao dịch hoặc GTID | Mốc bắt đầu/dừng không đúng, log trùng hoặc trạng thái GTID không tương thích | Khôi phục lại clone sạch và kiểm tra metadata trước khi phát lại |

Khi gặp lỗi, không khắc phục bằng cách bỏ qua event hoặc sửa file binlog gốc. Hãy tạo lại môi trường thử nghiệm từ backup nền, kiểm tra chuỗi log và xác định chính xác giao dịch bị thiếu hoặc bị lặp.

## 11. Tự kiểm tra

**Tình huống 1:** Log được ghi theo STATEMENT. Ứng dụng chạy `USE audit; UPDATE shop.orders ...`. Vì sao `mysqlbinlog --database=shop` có thể không xuất câu lệnh?

**Gợi ý:** Với statement-based logging, bộ lọc xét schema mặc định được chọn bằng `USE`. Tên bảng `shop.orders` không tự đổi schema mặc định từ `audit` thành `shop`.

**Tình huống 2:** Log được ghi theo ROW. Giao dịch cập nhật `shop.orders` và thêm bản ghi vào `audit.order_events`. Khi lọc `--database=shop`, điều gì có thể xảy ra?

**Gợi ý:** Bộ lọc giữ row event thuộc `shop` và bỏ row event thuộc `audit`. Nếu phát lại phần còn lại, trạng thái nghiệp vụ có thể thiếu bản ghi audit vốn nằm trong cùng giao dịch.

**Tình huống 3:** Máy chủ dùng MIXED. Có thể suy luận rằng `--database=shop` luôn lọc theo bảng bị thay đổi không?

**Gợi ý:** Không. Kết quả phụ thuộc định dạng thực tế của từng event. Statement event dùng ngữ cảnh database mặc định; row event dùng schema của bảng thay đổi. DDL cũng được ghi dạng statement.

**Tình huống 4:** Một nhóm chỉ muốn khôi phục schema `shop` và không biết ứng dụng có trigger ghi sang schema khác hay không. Nên làm gì trước?

**Gợi ý:** Kiểm tra trigger, routine và luồng nghiệp vụ; phục hồi đầy đủ vào clone và phát lại log không lọc. Sau khi dữ liệu nhất quán, mới trích xuất schema cần đưa về môi trường đích.

**Tình huống 5:** `mysqlbinlog --database=shop` tạo file SQL và không báo lỗi. Điều đó đã chứng minh bản phục hồi đúng chưa?

**Gợi ý:** Chưa. Cần kiểm tra định dạng event, các giao dịch bị giữ/bỏ, phụ thuộc liên schema, giải pháp GTID/position, rồi phát lại trên clone và kiểm tra invariant nghiệp vụ.

## 12. Điểm cần ghi nhớ

- `mysqlbinlog --database` lọc log cục bộ; cách lọc phụ thuộc định dạng ghi của từng sự kiện.
- STATEMENT lọc theo schema mặc định được chọn bằng `USE`, không đơn thuần theo tên bảng đã định danh đầy đủ.
- ROW lọc theo schema của bảng có row event; giao dịch nhiều schema có thể bị giữ lại một phần.
- MIXED kết hợp hai quy tắc; DDL vẫn là statement event.
- Giao dịch nhiều schema có thể chứa thay đổi nghiệp vụ phụ thuộc như audit, ledger, outbox hoặc bảng tổng hợp.
- GTID nhận diện giao dịch nhưng không khôi phục các sự kiện đã bị bộ lọc loại.
- Nếu chưa chứng minh schema độc lập, hãy phục hồi đầy đủ trong môi trường cô lập rồi trích xuất dữ liệu sau.
- Luôn xác minh backup nền, chuỗi log, GTID/position, ranh giới giao dịch và kết quả nghiệp vụ trước khi mở dịch vụ.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: mysqlbinlog](https://dev.mysql.com/doc/refman/8.4/en/mysqlbinlog.html) — quy tắc `--database`, định dạng output và các tùy chọn vị trí.
- [MySQL 8.4 Reference Manual: Binary Logging Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html) — STATEMENT, ROW và MIXED.
- [MySQL 8.4 Reference Manual: Evaluation of Database-Level Replication and Binary Logging Options](https://dev.mysql.com/doc/refman/8.4/en/replication-rules-db-options.html) — cách đánh giá các quy tắc lọc ở cấp database.
