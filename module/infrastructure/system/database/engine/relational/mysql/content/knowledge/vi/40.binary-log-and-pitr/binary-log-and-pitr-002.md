# Statement-based, row-based, mixed format và điều kiện phiên bản

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách `STATEMENT`, `ROW` và `MIXED` ghi thay đổi vào binary log.
- So sánh độ an toàn, dung lượng log, hiệu năng và khả năng kiểm tra của từng định dạng.
- Nhận diện câu lệnh không an toàn với statement-based logging và hiểu khi nào mixed format chuyển sang row events.
- Phân biệt `binlog_format` với `binlog_row_image` và các thiết lập binary log khác.
- Kiểm tra định dạng đang chạy, đọc sự kiện bằng `mysqlbinlog` và lập kế hoạch thay đổi định dạng phù hợp với phiên bản MySQL.
- Đánh giá tương thích giữa source, replica, storage engine và công cụ phục hồi theo thời điểm (PITR).

## 1. Binary log ghi lại điều gì?

Binary log (binlog) là nhật ký các sự kiện có thể làm thay đổi dữ liệu hoặc cấu trúc cơ sở dữ liệu. MySQL dùng binlog cho hai mục tiêu chính:

- **Replication:** source gửi các sự kiện trong binlog đến replica để replica áp dụng và tái tạo thay đổi.
- **Point-in-time recovery (PITR):** sau khi phục hồi một bản backup nền, người vận hành phát lại binlog đến thời điểm hoặc vị trí mong muốn.

Định dạng ghi log quyết định MySQL lưu **câu lệnh SQL đã thực thi**, **các thay đổi ở từng hàng**, hay kết hợp hai cách. Nó ảnh hưởng đến kích thước binlog, tính nhất quán khi replica áp dụng thay đổi, khả năng kiểm tra và thời gian phát lại log.

Ba định dạng truyền thống là:

- `STATEMENT` — statement-based logging (SBL/SBR).
- `ROW` — row-based logging (RBL/RBR).
- `MIXED` — mixed-format logging, kết hợp statement và row.

Định dạng chỉ có tác dụng khi binary logging được bật (`log_bin=ON`). Chọn `ROW` không tự bật binlog nếu máy chủ đã được khởi chạy với tùy chọn tắt binary logging.

## 2. Statement-based logging (SBR)

Với `STATEMENT`, MySQL ghi câu lệnh SQL làm thay đổi dữ liệu vào binary log. Replica đọc câu lệnh đó và thực thi lại trên dữ liệu của nó.

Ví dụ trên source:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 42;
```

Binlog statement-based lưu câu lệnh `UPDATE` (cùng thông tin sự kiện và ngữ cảnh cần thiết), thay vì ghi từng hàng bị thay đổi. Replica thực thi câu lệnh tương ứng trên bảng `inventory` của nó.

### 2.1. Ưu điểm

- **Log có thể nhỏ hơn:** một câu `UPDATE` tác động đến hàng triệu dòng vẫn có thể chỉ cần ghi một câu lệnh cùng metadata. Điều này có thể giảm dung lượng log và thời gian truyền khi thay đổi nhiều hàng.
- **Dễ đọc và kiểm tra:** sự kiện SQL thể hiện ý định thao tác, hữu ích khi điều tra hoặc kiểm toán.
- **Replica thực thi câu lệnh:** một câu lệnh có thể tận dụng cấu trúc index và cách tổ chức dữ liệu của replica khi thực thi.

### 2.2. Rủi ro về tính xác định

SBR yêu cầu câu lệnh phải tạo ra kết quả tương đương trên source và replica. Nếu kết quả phụ thuộc vào dữ liệu, thứ tự, trạng thái phiên, môi trường hoặc hàm không xác định, cùng một câu lệnh có thể tạo ra kết quả khác nhau.

Ví dụ nguy hiểm:

```sql
UPDATE jobs
SET priority = priority + 1
WHERE status = 'PENDING'
LIMIT 10;
```

Không có `ORDER BY`, tập 10 hàng được chọn có thể khác nhau nếu thứ tự truy cập hoặc kế hoạch thực thi trên source và replica khác nhau. Cách viết có thứ tự ổn định hơn:

```sql
UPDATE jobs
SET priority = priority + 1
WHERE status = 'PENDING'
ORDER BY job_id
LIMIT 10;
```

Ngay cả khi thêm `ORDER BY`, phải bảo đảm tiêu chí sắp xếp tạo ra thứ tự duy nhất (ví dụ `job_id` là khóa duy nhất). Nếu có nhiều hàng đồng hạng mà không có cột phân định, kết quả vẫn có thể không xác định.

Một số hàm và tình huống thường không an toàn với SBR gồm:

| Trường hợp | Vì sao có rủi ro |
|---|---|
| `UUID()` và `UUID_SHORT()` | Giá trị tạo ra trên source và replica không giống nhau |
| `RAND()` | Giá trị ngẫu nhiên có thể khác khi câu lệnh chạy lại |
| `SYSDATE()` | Phụ thuộc thời điểm thực thi; có ngoại lệ khi cấu hình `--sysdate-is-now` đồng nhất |
| `USER()` hoặc một số hàm danh tính | Danh tính kết nối trên replica có thể khác source |
| `LOAD_FILE()` | Kết quả phụ thuộc tệp trên filesystem của từng máy chủ |
| `UPDATE`/`DELETE` có `LIMIT` nhưng thiếu thứ tự ổn định | Source và replica có thể chọn các hàng khác nhau |
| Stored program hoặc loadable function không xác định | Kết quả có thể phụ thuộc trạng thái ngoài tham số đầu vào |

Không phải mọi hàm liên quan đến thời gian đều không an toàn. Ví dụ, MySQL ghi nhận timestamp của câu lệnh để `NOW()` có thể cho cùng giá trị khi câu lệnh được phát lại; `SYSDATE()` có quy tắc khác và cần được đánh giá riêng.

Danh sách này mang tính đại diện, không phải danh sách đầy đủ. MySQL có cơ chế nhận diện một số câu lệnh không an toàn và phát cảnh báo như `Statement is not safe to log in statement format`. Có thể kiểm tra cảnh báo ngay sau câu lệnh bằng:

```sql
SHOW WARNINGS;
```

Không nên xem việc MySQL phát cảnh báo là một cơ chế tự sửa dữ liệu. Với SBR, câu lệnh không an toàn có thể làm dữ liệu trên replica lệch khỏi source. Ngoài ra, replica phải có cấu trúc bảng và ngữ cảnh thực thi đủ tương thích để câu lệnh cho cùng kết quả.

## 3. Row-based logging (RBR)

Với `ROW`, MySQL ghi các sự kiện mô tả hàng nào đã được thêm, sửa hoặc xóa. Replica áp dụng thay đổi hàng đã ghi, không cần thực thi lại câu lệnh DML ban đầu.

Ví dụ, source chạy:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 42;
```

Với RBR, binlog chứa sự kiện chỉ ra hàng trong `inventory` bị thay đổi và dữ liệu tương ứng trước/sau thay đổi theo cấu hình row image. Replica áp dụng giá trị hàng được ghi trong event. Nếu câu lệnh ban đầu có biểu thức không xác định, replica vẫn nhận thay đổi hàng mà source đã tạo ra.

### 3.1. Ưu điểm

- **Tính nhất quán cao:** replica áp dụng thay đổi hàng cụ thể, giảm rủi ro do hàm ngẫu nhiên, dữ liệu cục bộ hoặc khác biệt trong cách thực thi câu lệnh.
- **Phù hợp với thao tác phức tạp:** các câu lệnh sửa dữ liệu có thể được thực thi một lần trên source; replica nhận kết quả hàng đã thay đổi.
- **Giảm một số loại khóa ở replica:** replica không phải chạy lại toàn bộ truy vấn DML để tìm hàng bị ảnh hưởng.
- **Hữu ích cho PITR:** các thay đổi hàng được ghi rõ, hỗ trợ phát lại chính xác kết quả đã commit khi chuỗi log hợp lệ.

### 3.2. Chi phí và hạn chế

- **Log có thể lớn:** một câu `UPDATE` thay đổi hàng triệu dòng có thể tạo rất nhiều row events, trong khi SBR chỉ ghi câu lệnh.
- **Tốn thời gian truyền và lưu:** log lớn hơn có thể làm tăng I/O, dung lượng kho lưu trữ, băng thông replication và thời gian PITR.
- **Khó đọc trực tiếp:** event nhị phân không hiển thị thành câu SQL gốc. Có thể dùng `mysqlbinlog` để giải mã phần mô tả hàng.
- **Một số thao tác vẫn dùng statement event:** RBR không có nghĩa mọi sự kiện trong binlog đều là row event. Các lệnh DDL như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` vẫn được ghi dưới dạng statement. Các lệnh cập nhật quyền như `GRANT`, `REVOKE` và thao tác tạo/xóa trigger, routine, view cũng được ghi theo quy tắc statement. Với `CREATE TABLE ... SELECT`, phần tạo bảng được ghi như statement còn phần chèn hàng có thể được ghi dưới dạng row events.

### 3.3. Đọc row events

Để xem các thay đổi hàng theo dạng dễ đọc hơn:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  /var/lib/mysql/binlog.000123
```

Tùy chọn `-vv` hiển thị thông tin hàng dưới dạng các dòng chú thích như `### UPDATE`, `### WHERE` và `### SET`. Đây là biểu diễn phục vụ kiểm tra; nó không phải câu SQL gốc đã được thực thi trên source. Không xóa chú thích rồi giả định phần còn lại là một script có thể chạy lại như SQL thông thường.

Nếu cần biết câu lệnh ứng dụng ban đầu để điều tra, có thể cân nhắc bật `binlog_rows_query_log_events` theo phiên bản và yêu cầu vận hành. Sự kiện bổ sung này có thể giúp `mysqlbinlog -vv` hiển thị câu truy vấn liên quan đến row events, nhưng làm tăng lượng thông tin ghi log và không thay đổi cách RBR áp dụng dữ liệu.

## 4. Mixed-format logging

Với `MIXED`, MySQL mặc định ghi statement event và tự chuyển sang row-based logging khi nhận diện câu lệnh hoặc tình huống chỉ có row logging mới bảo đảm kết quả phù hợp.

Ví dụ, câu lệnh sau tạo giá trị UUID khác nhau nếu thực thi riêng trên hai máy:

```sql
INSERT INTO request_log(request_id, message)
VALUES (UUID(), 'payment received');
```

Trong mixed format, MySQL chuyển thao tác này sang row events để replica nhận đúng UUID đã được tạo trên source. Các câu lệnh an toàn khác có thể tiếp tục được ghi dưới dạng statement.

Một số điều kiện có thể khiến MySQL chuyển sang row format gồm:

- Câu lệnh sử dụng `UUID()` hoặc một số hàm không an toàn khác.
- Có `AUTO_INCREMENT` và trigger hoặc stored function được gọi trong tình huống liên quan.
- View hoặc stored program chứa logic cần row-based logging.
- Sử dụng loadable function, `FOUND_ROWS()`, `ROW_COUNT()`, `USER()`, `CURRENT_USER()`, `LOAD_FILE()` hoặc một số system variable trong câu lệnh.
- Loại storage engine hoặc kiểu thao tác không phù hợp với statement logging.

Các điều kiện chính xác phụ thuộc phiên bản MySQL, storage engine và loại câu lệnh. Hãy đọc tài liệu của phiên bản đang chạy và kiểm tra warning/event thực tế. `MIXED` không phải cam kết rằng mọi câu lệnh không xác định đều được phát hiện theo mọi trường hợp có thể có.

Ưu điểm của mixed format là kết hợp log gọn của statement với độ an toàn của row ở những trường hợp MySQL nhận diện được. Hạn chế là định dạng thực tế thay đổi theo câu lệnh; việc ước tính dung lượng và kiểm tra binlog cần hiểu cả hai loại event. Ngoài ra, `binlog_format` đã bị deprecated trong các phiên bản MySQL mới, nên mixed không phải lựa chọn nên dùng cho hệ thống mới.

## 5. So sánh ba định dạng

| Tiêu chí | `STATEMENT` | `ROW` | `MIXED` |
|---|---|---|---|
| Nội dung chính | Câu lệnh SQL | Thay đổi của từng hàng | Statement, tự chuyển sang row khi cần |
| Rủi ro lệch dữ liệu do hàm không xác định | Cao nếu câu lệnh không an toàn | Thấp hơn vì ghi kết quả hàng | Giảm nhờ chuyển các trường hợp được nhận diện |
| Kích thước log | Thường nhỏ với thay đổi nhiều hàng | Có thể lớn khi nhiều hàng thay đổi | Phụ thuộc câu lệnh được ghi theo cách nào |
| Khả năng đọc bằng mắt | Tốt hơn | Cần giải mã row events | Kết hợp cả hai |
| Tác động khi replica áp dụng | Phải thực thi lại câu lệnh | Áp dụng thay đổi hàng | Tùy loại event |
| PITR và điều tra | Có thể đọc ý định SQL trực tiếp | Có thể xem giá trị hàng đã thay đổi | Phải hiểu cả statement và row events |
| Hướng sử dụng | Chỉ duy trì khi có lý do tương thích rõ ràng | Lựa chọn khuyến nghị cho hệ thống mới | Chủ yếu để hiểu và duy trì hệ thống cũ |

Không có định dạng nào thay thế được việc kiểm thử replication và restore. Với đa số hệ thống MySQL hiện đại, `ROW` là lựa chọn phù hợp vì ưu tiên tính nhất quán của thay đổi. Nếu khối lượng cập nhật lớn làm binlog tăng nhanh, hãy đo dung lượng và điều chỉnh `binlog_row_image`, retention, truyền log và lưu trữ trước khi cân nhắc quay lại statement logging.

## 6. Phân biệt `binlog_format` và `binlog_row_image`

Hai thiết lập này thường bị nhầm lẫn:

- `binlog_format` chọn cách ghi sự kiện: `STATEMENT`, `ROW` hoặc `MIXED`.
- `binlog_row_image` quyết định lượng dữ liệu cột được ghi trong row events khi sử dụng row-based logging.

Các giá trị phổ biến của `binlog_row_image`:

| Giá trị | Nội dung ghi cho row events |
|---|---|
| `FULL` | Ghi đầy đủ ảnh hàng trước/sau theo loại thao tác; dễ kiểm tra và phục hồi trong nhiều tình huống |
| `MINIMAL` | Chỉ ghi các cột cần để định danh hàng và các cột thay đổi; giảm kích thước log |
| `NOBLOB` | Ghi các cột, trừ một số cột BLOB/TEXT không thay đổi theo quy tắc của MySQL |

Ví dụ kiểm tra:

```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
```

`MINIMAL` có thể giảm đáng kể dung lượng binlog, nhưng làm cho việc đọc và trích xuất một số thay đổi khó hơn. Với thao tác `UPDATE` hoặc `DELETE`, MySQL và replica cần đủ thông tin để nhận diện đúng hàng. Khi dùng `MINIMAL` hoặc `NOBLOB`, cấu trúc bảng hai bên phải tương thích về số lượng/thứ tự cột, kiểu dữ liệu và định nghĩa khóa chính theo các điều kiện của MySQL; nếu không, replica hoặc consumer có thể không xác định được đúng hàng. Không đổi row image chỉ vì muốn log nhỏ hơn mà chưa kiểm tra quy trình audit, CDC, PITR và công cụ downstream.

## 7. Kiểm tra định dạng và xem binlog

### 7.1. Kiểm tra cấu hình máy chủ

Chạy các truy vấn sau bằng tài khoản có quyền đọc biến hệ thống và trạng thái binlog:

```sql
SELECT VERSION() AS mysql_version;

SHOW VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW SESSION VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_row_image';
SHOW GLOBAL VARIABLES LIKE 'binlog_row_metadata';
```

Phân biệt biến global và session. Giá trị global ảnh hưởng các session mới theo quy tắc áp dụng của biến; session hiện tại có thể vẫn giữ giá trị riêng. Vì vậy, `SHOW SESSION VARIABLES` và `SHOW GLOBAL VARIABLES` có thể trả về kết quả khác nhau.

Để xem các file binlog và event:

```sql
SHOW BINARY LOGS;
SHOW BINLOG EVENTS IN 'binlog.000123' LIMIT 20;
```

Để lấy vị trí binlog hiện tại, chọn lệnh theo phiên bản:

```sql
-- MySQL 8.0
SHOW MASTER STATUS;
```

```sql
-- MySQL 8.2 trở lên
SHOW BINARY LOG STATUS;
```

Tên mới `SHOW BINARY LOG STATUS` được giới thiệu từ MySQL 8.2; MySQL 8.4 đã loại bỏ `SHOW MASTER STATUS`. Kết quả `SHOW BINLOG EVENTS` giúp xem loại event, vị trí và tên file, nhưng không thay thế công cụ giải mã chi tiết.

### 7.2. Đọc log bằng `mysqlbinlog`

Xem nội dung event ở dạng văn bản:

```bash
mysqlbinlog --start-position=4 \
  /var/lib/mysql/binlog.000123
```

Ví dụ trên đọc một file binlog đã được rotate hoặc một bản sao log. Nếu log dùng row format, thêm `--base64-output=DECODE-ROWS -vv` để xem mô tả hàng. Nếu cần theo dõi binlog từ xa đang tiếp tục được ghi, hãy dùng chế độ đọc từ remote server và `--stop-never` theo tài liệu của `mysqlbinlog`. Nếu dùng GTID hoặc PITR theo thời gian, cần xác định chính xác ranh giới transaction và sự kiện dừng trước khi phát lại.

Không chạy thử `mysqlbinlog | mysql` trực tiếp trên production khi chưa xác định điểm dừng và phạm vi tác động. Hãy phát lại vào máy phục hồi cô lập trước, xác minh dữ liệu rồi mới lập kế hoạch đưa kết quả vào môi trường chính.

## 8. Điều kiện phiên bản MySQL

Định dạng mặc định và tình trạng hỗ trợ thay đổi theo phiên bản. Khi nâng cấp hoặc kết nối source/replica khác phiên bản, phải đọc tài liệu tương ứng thay vì suy luận từ cấu hình của máy chủ cũ.

| Phiên bản / nền tảng | Mặc định và lưu ý |
|---|---|
| Trước MySQL 5.7.7 | `STATEMENT` là mặc định; cần kiểm tra cấu hình thực tế khi nâng cấp |
| MySQL 5.7.7 trở lên | `ROW` là mặc định; binary logging không được bật mặc định trong MySQL 5.7 nếu chưa cấu hình `--log-bin` |
| MySQL 8.0 | Binary logging được bật mặc định trong cấu hình chuẩn và định dạng mặc định là `ROW` |
| MySQL 8.0.34 trở lên | `binlog_format` và việc thay đổi định dạng bị deprecated; thao tác đọc/đặt biến có thể phát cảnh báo. Oracle khuyến nghị dùng row-based cho replication mới |
| MySQL 8.4 | Tài liệu vẫn liệt kê `STATEMENT`, `ROW`, `MIXED` là các giá trị hợp lệ của biến deprecated; mặc định là `ROW`. Nên chuyển hệ thống cũ sang row-based và tránh phụ thuộc vào các định dạng sắp bị loại bỏ |
| MySQL NDB Cluster | Có quy tắc riêng: mặc định có thể là `MIXED`; statement-based replication không được hỗ trợ cho NDB tables. Phải theo tài liệu NDB Cluster tương ứng |

Điểm quan trọng: trong MySQL 8.0.34, `binlog_format` đã deprecated chứ không phải lập tức bị xóa. Tài liệu MySQL 8.4 vẫn liệt kê cả ba giá trị, đồng thời cảnh báo biến có thể bị loại bỏ trong phiên bản tương lai. Không nên viết kế hoạch nâng cấp dựa trên giả định rằng 8.4 đã loại bỏ `STATEMENT` và `MIXED`; hãy kiểm tra release notes của đúng bản server đang cài.

MySQL 8.0 cũng thay đổi một số hành vi replication và metadata theo từng bản minor. Bởi vậy, khi nâng cấp qua nhiều nhánh phiên bản, hãy kiểm tra release notes, ma trận tương thích replication và yêu cầu nâng cấp theo từng bước. Một replica cũ có thể không hiểu event hoặc metadata mới do source mới tạo ra, dù cả hai cùng hỗ trợ `ROW`.

## 9. Tương thích source, replica và storage engine

Source ghi event theo cấu hình và khả năng của storage engine. Replica phải có khả năng áp dụng loại event nhận được. Các điểm cần kiểm tra:

- **Định dạng trên replica:** replica tự đọc loại event từ source. Tuy nhiên, nếu replica ghi tiếp binlog cho replication tầng sau (`log_replica_updates`), cấu hình định dạng trên replica phải tương thích với loại event mà nó nhận và phát ra.
- **Không chuyển ROW thành STATEMENT:** replica không thể tự chuyển row events nhận từ source thành câu SQL statement để ghi tiếp. Nếu source phát row events, replica cần dùng `ROW` hoặc `MIXED` cho luồng ghi tiếp phù hợp.
- **Thay đổi định dạng giữa lúc replication chạy:** đổi source từ `STATEMENT` sang `ROW` trong khi replica vẫn ở `STATEMENT` có thể làm replication lỗi. Quy trình an toàn cần dừng replication, đổi cấu hình phù hợp trên source và replica, rồi khởi động và kiểm chứng lại theo hướng dẫn phiên bản.
- **Isolation level:** với InnoDB và isolation level `READ COMMITTED` hoặc `READ UNCOMMITTED`, chỉ row-based logging có thể sử dụng an toàn theo giới hạn của MySQL. Cố chuyển sang `STATEMENT` có thể dẫn đến lỗi khi ghi dữ liệu.
- **DDL:** ngay cả khi `binlog_format=ROW`, các lệnh như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` vẫn được ghi dạng statement. Hãy xem cả loại event lẫn ngữ cảnh khi phân tích binlog.
- **Storage engine khác nhau:** một số engine giới hạn định dạng có thể dùng. NDB Cluster có quy tắc riêng và không hỗ trợ SBR cho bảng NDB.
- **Schema:** với SBR, cấu trúc source và replica cần gần như giống nhau để câu lệnh có cùng ý nghĩa. Với RBR, khác biệt về thứ tự cột, kiểu dữ liệu, khóa và định nghĩa bảng vẫn có thể làm áp dụng hàng sai hoặc thất bại.

Không dùng việc đổi `binlog_format` như một cách chữa replication lag hoặc lỗi schema. Hãy xác định nguyên nhân thực tế từ trạng thái applier, error log, loại event và tương thích phiên bản.

## 10. Thay đổi `binlog_format` có kiểm soát

Trên các phiên bản còn cho phép đặt biến, có thể kiểm tra cú pháp và phạm vi:

```sql
-- Giá trị global áp dụng cho các kết nối mới theo quy tắc của biến.
SET GLOBAL binlog_format = 'ROW';

-- Chỉ áp dụng cho session hiện tại.
SET SESSION binlog_format = 'ROW';
```

Các câu lệnh trên chỉ dùng để minh họa. Trong MySQL 8.0.34 trở lên, thay đổi `binlog_format` đã deprecated và có thể phát cảnh báo. Hãy ưu tiên cấu hình row-based ngay từ đầu và làm theo tài liệu phiên bản trước khi thay đổi một hệ thống đang chạy.

### 10.1. Vì sao không nên đổi trực tiếp trên production?

MySQL giới hạn việc đổi định dạng trong một số trường hợp:

- Không thể đổi từ stored function hoặc trigger.
- Không thể đổi session khi session có temporary table đang mở.
- Không thể đổi global trong một số tình huống replication channel có temporary table hoặc applier thread đang chạy.
- Với NDB, biến có quy tắc riêng.
- Đổi source/replica không đồng bộ có thể làm applier lỗi khi nhận row events nhưng replica đang yêu cầu statement format.

Ngoài ra, temporary table được ghi log theo quy tắc khác nhau giữa statement, row và mixed. Chuyển định dạng trong lúc còn temporary table có thể khiến chuỗi event không thể tái tạo như dự kiến. Không đổi định dạng giữa một phiên nghiệp vụ đang mở.

### 10.2. Quy trình chuyển từ SBR/MIXED sang RBR

1. **Kiểm kê:** lấy phiên bản MySQL của mọi source/replica, cấu hình `binlog_format`, storage engine, isolation level, `log_replica_updates`, GTID và các consumer đọc binlog như CDC.
2. **Đọc cảnh báo:** tìm warning `Statement is not safe to log in statement format`, kiểm tra các câu lệnh dùng hàm không xác định, stored program, trigger và thao tác `LIMIT`.
3. **Đánh giá dung lượng:** ước tính mức tăng binlog khi chuyển sang row events, đặc biệt với batch update/delete lớn và cột BLOB/TEXT. Kiểm tra dung lượng đĩa, retention, băng thông và kho lưu trữ.
4. **Kiểm tra công cụ phụ thuộc:** xác nhận phiên bản `mysqlbinlog`, công cụ backup, CDC, audit và pipeline downstream hiểu row events cùng metadata của phiên bản server.
5. **Thử nghiệm:** chuyển một topology staging có dữ liệu và tải đại diện. Kiểm tra replication, failover, PITR, backup/restore và điều tra binlog.
6. **Lập cửa sổ thay đổi:** lên kế hoạch cho toàn bộ topology. Nếu cần đổi cấu hình khi replication đang chạy, dừng applier theo runbook và đổi định dạng nhất quán trên các máy chủ liên quan.
7. **Triển khai:** chuyển theo trình tự đã kiểm thử, xác nhận từng replica bắt kịp, không có lỗi applier và dung lượng log vẫn trong giới hạn.
8. **Theo dõi:** theo dõi tốc độ tạo binlog, relay log, độ trễ replication, thời gian purge, I/O và thời gian PITR. Giữ kế hoạch quay lui chỉ trong phạm vi các phiên bản còn hỗ trợ định dạng cũ.

Nếu phiên bản đích không còn hỗ trợ lựa chọn cũ trong tương lai, rollback bằng cách quay lại SBR/MIXED có thể không khả thi. Phương án quay lui cần dựa trên phiên bản server và khả năng đọc event thực tế, không chỉ là đổi một biến cấu hình.

## 11. Tình huống thực hành

Một hệ thống MySQL có source và hai replica. Source chạy MySQL 8.0.36 với `binlog_format=MIXED`; một replica ghi tiếp binlog để phục vụ tầng replica thứ hai. Nhóm vận hành dự định nâng cấp source lên MySQL 8.4 và chuyển sang `ROW`. Hệ thống cũng có pipeline CDC đọc binlog để cập nhật kho dữ liệu.

Hãy lập kế hoạch theo thứ tự:

1. Ghi lại phiên bản, định dạng binlog, `log_replica_updates`, storage engine, isolation level và trạng thái replication của cả ba máy chủ.
2. Xác nhận replica trung gian và tầng sau hỗ trợ row events mà source sẽ phát ra; kiểm tra ma trận tương thích phiên bản cho lộ trình nâng cấp 8.0 lên 8.4.
3. Kiểm tra CDC có hỗ trợ row events, `binlog_row_image` đang dùng và các kiểu dữ liệu/metadata có trong bảng. Thử phát lại một đoạn log vào môi trường thử nghiệm.
4. Ước tính lượng log tăng khi các batch update/delete lớn chuyển từ statement sang row; xác nhận dung lượng binlog và relay log đủ cho retention.
5. Diễn tập dừng replication, đổi cấu hình theo hướng dẫn của phiên bản, khởi động lại applier và xác nhận mọi replica bắt kịp.
6. Thử PITR từ một backup nền với row events; xác nhận dữ liệu nghiệp vụ và CDC đều đúng sau phục hồi.
7. Chỉ hoàn tất thay đổi sau khi không còn cảnh báo tương thích, lỗi applier hoặc chênh lệch dữ liệu.

**Câu hỏi tự kiểm tra:**

1. Khi một câu `UPDATE` sửa một triệu hàng, SBR và RBR ghi gì vào binlog? Định dạng nào có thể tạo log lớn hơn?
2. Vì sao `UPDATE ... LIMIT 10` không có `ORDER BY` có thể không an toàn với SBR?
3. Mixed format quyết định chuyển sang row-based logging trong trường hợp nào?
4. `binlog_format=ROW` có nghĩa lệnh `ALTER TABLE` được ghi thành row events không? Giải thích.
5. `binlog_row_image=MINIMAL` thay đổi điều gì và có rủi ro gì cho công cụ CDC?
6. Điều gì có thể xảy ra nếu source chuyển sang `ROW` nhưng replica ghi tiếp binlog vẫn đặt `STATEMENT`?
7. Vì sao cần kiểm tra tình trạng deprecated của `binlog_format` khi nâng cấp MySQL 8.0.34 hoặc 8.4?

## 12. Nguyên tắc lựa chọn

Với hệ thống mới, ưu tiên `ROW` và kiểm thử kích thước log, khả năng đọc binlog, replication, CDC và PITR. RBR giúp giảm nguy cơ lệch dữ liệu do thực thi lại câu lệnh không xác định, đồng thời là định dạng mặc định của các phiên bản MySQL hiện đại.

Chỉ duy trì `STATEMENT` hoặc `MIXED` trong hệ thống cũ khi có yêu cầu tương thích được hiểu rõ, có kiểm thử chứng minh và có kế hoạch chuyển đổi. MySQL đã deprecated việc thay đổi `binlog_format` từ 8.0.34; vì vậy không nên xây dựng topology mới phụ thuộc vào SBR/MIXED.

Hãy đánh giá định dạng theo cả ba góc độ: dữ liệu có tái tạo đúng không, binlog có được lưu và phát lại trong thời gian mục tiêu không, và công cụ vận hành có đọc/giải mã được event hay không. Một lựa chọn phù hợp phải đáp ứng cả replication lẫn PITR trong cùng kiến trúc.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Binary Logging Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html)
- [MySQL 8.4 Reference Manual — Setting the Binary Log Format](https://dev.mysql.com/doc/refman/8.4/en/binary-log-setting.html)
- [MySQL 8.4 Reference Manual — Mixed Binary Logging Format](https://dev.mysql.com/doc/refman/8.4/en/binary-log-mixed.html)
- [MySQL 8.0 Reference Manual — Advantages and Disadvantages of Statement-Based and Row-Based Replication](https://dev.mysql.com/doc/refman/8.0/en/replication-sbr-rbr.html)
- [MySQL 8.0 Release Notes — Changes in MySQL 8.0.34](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-34.html)
