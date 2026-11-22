# Row image, transaction event và dung lượng binary log

Binary log (binlog) ghi lại các thay đổi mà MySQL cần dùng cho replication, khôi phục theo thời điểm (point-in-time recovery, PITR) và một số hệ thống thu thập thay đổi dữ liệu (CDC). Khi dùng row-based logging, MySQL ghi các row event mô tả hàng đã thay đổi. Tùy chọn `binlog_row_image` quyết định mỗi event chứa bao nhiêu cột của hàng trước và sau thay đổi.

Dung lượng binlog phụ thuộc vào số giao dịch, số hàng bị tác động, kích thước dữ liệu được ghi trong row image, overhead của event và thời gian giữ log. Giao dịch lớn còn sử dụng transaction cache trước khi được ghi vào file binlog. Hiểu các thành phần này giúp chọn cấu hình phù hợp, dự báo dung lượng và giữ đủ log cho replica cũng như PITR.

Bài học thuộc chương **Binary log và PITR** của module `DATABASE_MYSQL`. Module bao quát thiết kế bảng, SQL, index, transaction, phân quyền, sao lưu và vận hành MySQL. Các ví dụ dưới đây dùng MySQL 8.0 trở lên; hãy kiểm tra tài liệu của đúng phiên bản server và client trước khi thay đổi cấu hình production.

Sau bài học, bạn có thể:

- Phân biệt statement-based, row-based và mixed binary logging.
- Giải thích `FULL`, `MINIMAL` và `NOBLOB` trong `binlog_row_image`.
- Đọc cấu trúc cơ bản của một transaction event group.
- Hiểu vai trò của transaction cache và các chỉ số cache trên đĩa.
- Ước lượng, giám sát và kiểm soát dung lượng binlog.
- Thiết lập thời gian lưu log phù hợp với replication và PITR.

## 1. Binary log lưu những gì?

Binary log là chuỗi file do MySQL tạo ra để ghi các sự kiện làm thay đổi dữ liệu hoặc cấu trúc. Khi bật `log_bin`, server ghi các thay đổi cần thiết vào binlog theo `binlog_format`.

Ba chế độ chính là:

| Chế độ | Nội dung ghi | Đặc điểm |
|---|---|---|
| `STATEMENT` | Câu SQL đã thực thi | File có thể nhỏ hơn với một câu lệnh tác động nhiều hàng, nhưng kết quả phụ thuộc tính xác định của câu lệnh và môi trường replica. |
| `ROW` | Các thay đổi ở mức hàng | Replica áp dụng thay đổi hàng; row image quyết định những cột nào được ghi. |
| `MIXED` | Kết hợp statement và row event | MySQL chọn dạng ghi theo quy tắc của server; một số câu lệnh được chuyển sang row-based để bảo đảm an toàn replication. |

Trong các hệ thống MySQL hiện đại, `ROW` là lựa chọn thường dùng cho replication và CDC. Tuy nhiên, cần xem xét khả năng tương thích của replica, công cụ đọc binlog và yêu cầu dung lượng trước khi đổi chế độ.

Kiểm tra trạng thái:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
```

`binlog_row_image` chỉ ảnh hưởng đến các row event. Nếu server ghi một câu lệnh dưới dạng statement event, tùy chọn row image không thay đổi nội dung câu SQL được ghi. Với `MIXED`, row image chỉ có tác dụng khi một thao tác được ghi dưới dạng row event.

## 2. Row event và before image / after image

Trong row-based logging, MySQL ghi thông tin về hàng trước và sau thao tác. Hai khái niệm quan trọng:

- **Before image**: các giá trị của hàng trước khi thay đổi. Thường dùng để xác định hàng cần cập nhật hoặc xóa.
- **After image**: các giá trị của hàng sau khi thay đổi. Dùng để tái tạo trạng thái mới trên replica hoặc hệ thống đọc CDC.

Loại thao tác quyết định image nào xuất hiện:

| Thao tác | Image thường được ghi |
|---|---|
| `INSERT` | After image của hàng mới. |
| `UPDATE` | Before image và after image. |
| `DELETE` | Before image của hàng bị xóa. |

Ví dụ bảng `sales.orders` có các cột `order_id`, `customer_id`, `status`, `note` và `total`. Một câu lệnh đổi trạng thái:

```sql
UPDATE sales.orders
SET status = 'shipped'
WHERE order_id = 105;
```

Với `FULL`, row event có thể chứa toàn bộ giá trị cột trước và sau cập nhật. Với `MINIMAL`, before image có thể chỉ cần khóa nhận diện `order_id`, còn after image chỉ cần giá trị `status` đã đổi. Đây là lý do row image ảnh hưởng đáng kể đến dung lượng khi bảng có nhiều cột hoặc có các trường lớn.

## 3. Ba chế độ binlog_row_image

`binlog_row_image` có ba giá trị chính: `FULL`, `MINIMAL` và `NOBLOB`. Giá trị mặc định của MySQL là `FULL` trong các phiên bản phổ biến hiện nay. Tùy chọn này có thể được đặt ở phạm vi global hoặc session tùy phiên bản; luôn kiểm tra giá trị hiệu lực của kết nối tạo ra thay đổi.

### 3.1. FULL

`FULL` ghi toàn bộ cột trong before image và after image của row event.

```ini
[mysqld]
binlog_format=ROW
binlog_row_image=FULL
```

Ưu điểm:

- Row event chứa nhiều ngữ cảnh về hàng trước và sau thay đổi.
- Dễ kiểm tra thay đổi, hỗ trợ điều tra sự cố và một số hệ thống CDC cần giá trị cũ.
- Ít phụ thuộc vào việc downstream phải tự ghép giá trị cũ với schema hoặc trạng thái trước đó.

Đổi lại, `FULL` có thể tạo log lớn khi table có nhiều cột, nhiều trường `BLOB`/`TEXT` hoặc các giao dịch cập nhật số lượng hàng lớn. Giá trị cũ và mới của dữ liệu nhạy cảm cũng có thể xuất hiện trong binlog, vì vậy file log cần được bảo vệ như dữ liệu production.

### 3.2. MINIMAL

`MINIMAL` chỉ ghi các cột cần thiết để nhận diện hàng trong before image và các cột cần thiết trong after image. Với `UPDATE`, after image thường chỉ chứa các cột đã thay đổi. Với `DELETE`, before image phải đủ để xác định hàng cần xóa. Với `INSERT`, after image phải đủ để tái tạo hàng mới theo quy tắc row event.

```ini
[mysqld]
binlog_format=ROW
binlog_row_image=MINIMAL
```

Để nhận diện hàng, MySQL ưu tiên primary key hoặc unique key phù hợp. Nếu table không có khóa chính hay unique key có thể dùng để nhận diện duy nhất hàng, before image có thể phải chứa toàn bộ cột. Vì vậy, `MINIMAL` không bảo đảm mọi table đều giảm dung lượng như nhau.

Ưu điểm là giảm lượng dữ liệu lặp lại trong event, đặc biệt với bảng rộng mà mỗi lần cập nhật chỉ đổi một vài cột. Hạn chế là công cụ CDC hoặc quy trình audit có thể không nhận đủ giá trị cũ và các cột không thay đổi. Consumer phải hiểu partial row image và ghép trạng thái theo đúng cách.

### 3.3. NOBLOB

`NOBLOB` gần với `FULL`, nhưng bỏ qua các cột `BLOB` và `TEXT` không cần thiết để nhận diện hàng. Các cột BLOB/TEXT vẫn có thể được ghi nếu cần để xác định hàng hoặc theo yêu cầu của thay đổi.

```ini
[mysqld]
binlog_format=ROW
binlog_row_image=NOBLOB
```

Chế độ này có thể giảm dung lượng khi bảng lưu tài liệu, ảnh, nội dung dài hoặc payload lớn trong `BLOB`/`TEXT`. Tuy nhiên, nếu hệ thống CDC cần giá trị đầy đủ của các trường này, việc bỏ chúng khỏi row image sẽ làm mất thông tin mà consumer mong đợi.

### 3.4. So sánh nhanh

| Tiêu chí | `FULL` | `MINIMAL` | `NOBLOB` |
|---|---|---|---|
| Before image | Toàn bộ cột | Cột cần để nhận diện hàng | Gần như toàn bộ, trừ BLOB/TEXT không cần thiết |
| After image | Toàn bộ cột | Cột cần thiết cho hàng mới hoặc cột đã đổi | Gần như toàn bộ, trừ BLOB/TEXT không cần thiết |
| Dung lượng | Thường lớn nhất | Thường nhỏ nhất nếu table có khóa phù hợp | Có thể giảm đáng kể với cột lớn |
| Phân tích giá trị cũ | Đầy đủ hơn | Có thể thiếu cột không đổi | Có thể thiếu BLOB/TEXT |
| CDC | Phù hợp với consumer cần ảnh đầy đủ | Consumer phải hỗ trợ partial image | Consumer phải chấp nhận thiếu trường BLOB/TEXT không cần thiết |

Không có chế độ tối ưu cho mọi hệ thống. Chọn theo yêu cầu của replica, công cụ CDC, audit, điều tra sự cố và ngân sách lưu trữ.

## 4. Khóa chính ảnh hưởng đến row image như thế nào?

Trong `MINIMAL`, MySQL cần xác định chính xác hàng trước khi cập nhật hoặc xóa. Primary key là lựa chọn rõ ràng nhất. Một unique key cũng có thể dùng nếu đáp ứng yêu cầu nhận diện duy nhất, gồm các cột cần thiết và không cho phép giá trị `NULL` theo quy tắc áp dụng.

Ví dụ table có primary key:

```sql
CREATE TABLE sales.orders (
  order_id BIGINT NOT NULL PRIMARY KEY,
  customer_id BIGINT NOT NULL,
  status VARCHAR(24) NOT NULL,
  note TEXT,
  total DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;
```

Khi cập nhật `status`, before image tối thiểu có thể chỉ cần `order_id`; after image có thể chỉ cần `status`. Nếu table không có khóa nhận diện phù hợp, MySQL có thể phải ghi nhiều hoặc toàn bộ cột trong before image để replica xác định đúng hàng.

Khóa chính có lợi ích vượt ra ngoài binlog: nó xác định danh tính hàng, hỗ trợ index clustered của InnoDB và giúp replication/CDC xử lý update/delete đáng tin cậy. Khi thiết kế schema, hãy cân nhắc primary key ổn định, duy nhất và không cần thay đổi thường xuyên.

## 5. Xem row image bằng mysqlbinlog

`mysqlbinlog` là công cụ đọc và giải mã binary log. Với row-based logging, dùng `--base64-output=DECODE-ROWS -vv` để hiển thị row event dưới dạng chú thích dễ đọc.

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000123
```

Output có thể có dạng minh họa:

```text
### UPDATE `sales`.`orders`
### WHERE
###   @1=105
### SET
###   @3='shipped'
```

`@1`, `@3` là vị trí cột trong table map của event, không phải tên cột được đảm bảo hiển thị. Dùng metadata table và schema tương ứng để diễn giải đúng. Với `FULL`, có thể thấy nhiều cột trong phần `WHERE` và `SET`; với `MINIMAL`, chỉ một tập con cần thiết có thể xuất hiện.

Một số lệnh kiểm tra khác:

```sql
SHOW BINARY LOGS;
SHOW BINLOG EVENTS IN 'mysql-bin.000123' LIMIT 20;
```

`SHOW BINLOG EVENTS` cho biết loại event, vị trí bắt đầu/kết thúc và thông tin khái quát. Với row event, `mysqlbinlog -vv` thường hữu ích hơn để xem nội dung chi tiết. Output giải mã là dạng diễn giải phục vụ kiểm tra; các dòng `###` không phải câu SQL có thể chạy trực tiếp.

Khi đọc log, hãy lưu ý schema tại thời điểm event được tạo. Nếu table đã thay đổi cấu trúc sau đó, ánh xạ vị trí cột trong row event với schema hiện tại có thể sai.

## 6. Transaction event group

Các event của một transaction được ghi thành một nhóm logic. Với InnoDB và row-based logging, một nhóm thường có dạng khái quát:

```text
GTID_LOG_EVENT (nếu GTID được bật)
QUERY_EVENT: BEGIN
TABLE_MAP_EVENT
WRITE_ROWS_EVENT / UPDATE_ROWS_EVENT / DELETE_ROWS_EVENT
XID_EVENT (commit)
```

Đây là sơ đồ minh họa, không phải danh sách event cố định cho mọi phiên bản hoặc mọi cấu hình. Có thể xuất hiện event bổ sung như metadata, annotation, checksum hoặc event phục vụ GTID. Với statement-based logging, thay đổi thường được ghi bằng `QUERY_EVENT` chứa câu SQL. DDL cũng thường được ghi dưới dạng statement event ngay cả khi `binlog_format=ROW`.

Các event chính:

- `GTID_LOG_EVENT`: đánh dấu transaction bằng GTID khi chế độ GTID áp dụng.
- `QUERY_EVENT`: ghi câu lệnh SQL như `BEGIN` hoặc DDL; với statement-based logging, có thể chứa câu SQL thay đổi dữ liệu.
- `TABLE_MAP_EVENT`: ánh xạ table ID trong row event sang database, table và metadata cột.
- `WRITE_ROWS_EVENT`: ghi hàng được thêm.
- `UPDATE_ROWS_EVENT`: ghi before image và after image của hàng được cập nhật.
- `DELETE_ROWS_EVENT`: ghi before image của hàng bị xóa.
- `XID_EVENT`: đánh dấu commit của transaction transactional, thường là InnoDB.

### 6.1. Vì sao transaction được ghi theo nhóm?

Với transaction InnoDB, MySQL giữ thay đổi binlog trong transaction cache trong khi transaction đang chạy. Khi commit, các event của transaction được đưa vào binary log như một nhóm. Khi rollback, phần thay đổi transactional chưa commit không được ghi như một transaction đã commit trong binlog.

Nhờ nhóm event và commit marker, replica có thể áp dụng transaction theo ranh giới commit. Khi đọc log để PITR, cần tránh dừng giữa một nhóm event nếu mục tiêu là tái tạo trạng thái nhất quán. Hãy chọn vị trí kết thúc tại ranh giới transaction phù hợp.

### 6.2. Transaction lớn và engine không transactional

Transaction InnoDB lớn có thể tạo ra lượng row event đáng kể. Nếu transaction bị rollback, thay đổi transactional không trở thành transaction đã commit trong binlog, nhưng tài nguyên cache và công việc đã tiêu tốn trong lúc chạy vẫn có thể lớn.

Các thay đổi trên table nontransactional như MyISAM không có khả năng rollback giống InnoDB. MySQL sử dụng statement cache cho một số thay đổi nontransactional. Khi một thao tác kết hợp transactional và nontransactional, không nên giả định toàn bộ thay đổi có tính nguyên tử như một transaction chỉ dùng InnoDB. Với hệ thống cần replication và PITR đáng tin cậy, ưu tiên engine transactional và tránh trộn engine nếu không có lý do rõ ràng.

## 7. Transaction cache và giới hạn bộ nhớ

Trước khi transaction được ghi vào file binlog, MySQL dùng cache trong bộ nhớ theo kết nối. Các biến quan trọng:

| Biến | Vai trò |
|---|---|
| `binlog_cache_size` | Kích thước cache ban đầu cho thay đổi của transaction. |
| `max_binlog_cache_size` | Giới hạn kích thước transaction cache; transaction vượt giới hạn có thể thất bại. |
| `binlog_stmt_cache_size` | Kích thước cache cho các statement cần statement cache, thường liên quan thay đổi nontransactional. |
| `max_binlog_stmt_cache_size` | Giới hạn statement cache. |

Khi transaction cache vượt dung lượng bộ nhớ được cấp, MySQL có thể ghi phần vượt vào file tạm. Điều này giúp giao dịch lớn không cần giữ toàn bộ nội dung trong RAM, nhưng làm tăng I/O tạm thời. Tăng `binlog_cache_size` quá cao có thể làm tăng mức sử dụng bộ nhớ khi có nhiều kết nối đồng thời; không nên tăng chỉ vì thấy một giao dịch lớn.

Kiểm tra biến hiện hành:

```sql
SHOW VARIABLES LIKE 'binlog_cache_size';
SHOW VARIABLES LIKE 'max_binlog_cache_size';
SHOW VARIABLES LIKE 'binlog_stmt_cache_size';
SHOW VARIABLES LIKE 'max_binlog_stmt_cache_size';
```

Theo dõi các bộ đếm:

```sql
SHOW GLOBAL STATUS LIKE 'Binlog_cache_use';
SHOW GLOBAL STATUS LIKE 'Binlog_cache_disk_use';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache_use';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache_disk_use';
```

- `Binlog_cache_use`: số lần transaction cache được sử dụng.
- `Binlog_cache_disk_use`: số lần transaction cache phải dùng file tạm trên đĩa.
- `Binlog_stmt_cache_use`: số lần statement cache được sử dụng.
- `Binlog_stmt_cache_disk_use`: số lần statement cache phải dùng file tạm.

Các giá trị status thường là bộ đếm tích lũy từ khi server khởi động. Hãy so sánh chênh lệch trong một khoảng thời gian, kết hợp với số transaction và tải thực tế. Một số lần spill ra đĩa không tự động là sự cố; cần đánh giá tần suất, độ trễ và tải I/O.

## 8. Điều gì quyết định dung lượng binary log?

Dung lượng binlog là tổng của dữ liệu thay đổi và overhead của event. Có thể hình dung gần đúng:

\[
\text{Binlog volume} \approx
\text{row images} + \text{event overhead} + \text{transaction metadata}
\]

Các yếu tố chính:

1. **Số lượng transaction và hàng bị tác động.** Một câu lệnh cập nhật hàng triệu bản ghi có thể tạo log lớn dù SQL rất ngắn.
2. **Kích thước hàng và kiểu dữ liệu.** `BLOB`, `TEXT`, JSON lớn hoặc cột chuỗi dài có thể làm row image tăng đáng kể.
3. **Row image.** `FULL` thường ghi nhiều giá trị hơn `MINIMAL`; `NOBLOB` có thể giảm log khi có trường BLOB/TEXT không cần thiết.
4. **Tần suất cập nhật.** Một bảng rộng được cập nhật thường xuyên có thể tạo binlog lớn ngay cả khi số hàng không tăng.
5. **Transaction và metadata.** GTID, table map, row event header, checksum và commit marker đều góp phần tạo overhead.
6. **Kiểu logging.** Statement-based có thể gọn với thao tác hàng loạt, trong khi row-based phản ánh dữ liệu hàng đã đổi và thường dễ dự đoán hơn cho replication.

Ví dụ định tính: một bảng có nhiều cột mô tả, trường ghi chú dài và một primary key. Nếu mỗi lần chỉ đổi cột `status`, `FULL` có thể ghi lại nhiều giá trị không đổi; `MINIMAL` có thể chỉ cần khóa nhận diện và cột trạng thái mới. Ngược lại, nếu cập nhật phần lớn cột hoặc không có khóa duy nhất, mức giảm dung lượng sẽ nhỏ hơn.

Để ước lượng dung lượng thực tế, hãy đo tốc độ tăng binlog trong các khoảng tải bình thường và cao điểm. Không chỉ dựa vào kích thước schema hoặc số câu SQL vì hai hệ thống có cùng số câu lệnh có thể tạo lượng row event rất khác nhau.

## 9. Xoay vòng file và giới hạn kích thước

`max_binlog_size` đặt ngưỡng kích thước mục tiêu cho mỗi file binary log. Khi file đạt ngưỡng, MySQL xoay sang file tiếp theo tại ranh giới phù hợp.

```ini
[mysqld]
max_binlog_size=512M
```

Giá trị mặc định trong nhiều bản MySQL 8.0 là 1 GiB; hãy xác nhận trên phiên bản đang dùng. `max_binlog_size` là ngưỡng xoay vòng, không phải giới hạn cứng cho mọi file. Một transaction không bị chia giữa các file binlog; nếu transaction đơn lẻ lớn hơn ngưỡng, file có thể vượt `max_binlog_size` trước khi xoay vòng sau khi transaction kết thúc.

Không nên đặt file quá nhỏ chỉ để tạo nhiều file log. Quá nhiều file làm tăng công việc quản lý và kiểm tra. Cũng không nên đặt quá lớn nếu quy trình sao chép, upload hoặc lưu trữ cần xử lý từng file trong khoảng thời gian ngắn. Chọn kích thước theo tốc độ ghi, cách vận chuyển log và khả năng vận hành.

Kiểm tra file hiện có:

```sql
SHOW BINARY LOGS;
```

Kết quả liệt kê tên file và kích thước. Tổng kích thước các file chưa hết hạn cho biết lượng dung lượng binlog hiện đang chiếm dụng trên server.

## 10. Thời gian lưu log và dung lượng đĩa

`binlog_expire_logs_seconds` điều khiển thời gian MySQL giữ binary log trước khi tự động xóa log hết hạn. Đây là cấu hình quan trọng đối với replication và PITR.

```sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
```

Có thể cấu hình trong file cấu hình server:

```ini
[mysqld]
binlog_expire_logs_seconds=1209600
```

Ví dụ trên đặt thời gian lưu là 14 ngày. Đây chỉ là giá trị minh họa; thời gian phù hợp phải dựa trên lịch backup, thời gian phục hồi, độ trễ replica và mục tiêu PITR. Các phiên bản cũ có thể còn hỗ trợ `expire_logs_days`; hãy ưu tiên cấu hình được khuyến nghị cho phiên bản MySQL đang vận hành và tránh đặt hai biến với ý nghĩa không rõ ràng.

### 10.1. Ước lượng dung lượng cần giữ

Một phép ước lượng thực tế:

\[
\text{Dung lượng dự kiến} \approx
\text{Binlog trung bình mỗi ngày} \times
\text{Số ngày lưu} \times
\text{Hệ số dự phòng}
\]

Ví dụ, nếu đo được trung bình 18 GiB binlog mỗi ngày và cần giữ 14 ngày, dung lượng cơ sở là 252 GiB. Cần cộng thêm biên an toàn cho ngày cao điểm, transaction lớn, độ trễ replica và các file khác trên volume. Hãy đo cả ngày có batch job, import hoặc migration lớn vì chúng có thể làm tốc độ tăng log cao hơn nhiều so với ngày bình thường.

Theo dõi dung lượng filesystem cùng `SHOW BINARY LOGS`. Không đợi đến khi đĩa gần đầy mới thay đổi retention; binlog có thể tăng nhanh trong thời gian tải ghi cao.

### 10.2. Retention phải đáp ứng replication

Replica cần đọc được các binary log mà nó chưa nhận hoặc chưa áp dụng. Nếu source xóa file mà replica còn cần, replication có thể dừng và phải đồng bộ lại bằng một bản backup hoặc quy trình phục hồi khác.

Trước khi giảm thời gian lưu hoặc purge log thủ công, hãy kiểm tra trạng thái replica:

```sql
SHOW REPLICA STATUS\G
```

Kiểm tra file/position mà replica đang đọc, trạng thái I/O và SQL thread, độ trễ và các lỗi gần nhất. Nếu có nhiều replica hoặc replication channel, phải kiểm tra tất cả các consumer liên quan.

### 10.3. Retention phải đáp ứng PITR

PITR cần một bản full backup làm mốc và chuỗi binary log liên tục từ thời điểm backup đến thời điểm cần khôi phục. Nếu thiếu một file trong chuỗi, không thể phát lại các thay đổi sau điểm bị thiếu theo cách thông thường.

Thời gian lưu binlog phải bao phủ ít nhất:

- Khoảng cách giữa các lần full backup.
- Thời gian phát hiện và xử lý sự cố.
- Thời gian cần để tải, chuẩn bị và restore backup.
- Khoảng thời gian cần phục hồi đến một mốc trước sự cố.
- Biên an toàn cho replication lag và gián đoạn lưu trữ.

Ví dụ, nếu full backup chạy mỗi tuần nhưng tổ chức cần khả năng phục hồi về bất kỳ thời điểm nào trong 10 ngày gần nhất, giữ log 7 ngày là không đủ. Hãy đặt retention theo mục tiêu khôi phục thực tế và kiểm tra rằng backup cùng toàn bộ binlog cần thiết đã được sao chép sang nơi lưu trữ an toàn.

## 11. Purge binary log an toàn

MySQL có thể tự động xóa log hết hạn theo retention. Quản trị viên cũng có thể xóa thủ công bằng `PURGE BINARY LOGS`, nhưng phải xác minh replica và PITR trước khi thực hiện.

Xóa các file cũ hơn file được chỉ định:

```sql
PURGE BINARY LOGS TO 'mysql-bin.000250';
```

Lệnh này xóa các file đứng trước `mysql-bin.000250`; file được chỉ định vẫn được giữ. Hoặc xóa các file trước một thời điểm:

```sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

Không chạy lệnh purge chỉ để giải phóng dung lượng khi chưa biết replica hoặc kế hoạch PITR có cần các file đó hay không. Nếu xóa nhầm log, việc phục hồi có thể buộc phải dựng lại replica hoặc chấp nhận mất khả năng PITR trong khoảng thời gian bị xóa.

Quy trình purge nên gồm: xác định file/position cũ nhất còn cần cho từng replica; xác định mốc PITR thấp nhất còn phải hỗ trợ; xác nhận bản backup liên quan đã được kiểm tra; chọn mốc purge sau các mốc cần giữ; ghi nhận thao tác và kiểm tra lại replication sau khi thực hiện.

## 12. Transaction lớn, event lớn và vận hành

Giao dịch lớn có thể làm tăng đồng thời dung lượng binlog, transaction cache, thời gian commit và độ trễ replication. Các biện pháp vận hành thường hữu ích:

- Chia batch cập nhật rất lớn thành các transaction nhỏ khi nghiệp vụ cho phép.
- Tránh cập nhật lại cùng một giá trị nếu không cần thiết.
- Thiết kế primary key ổn định để `MINIMAL` có thể nhận diện hàng hiệu quả.
- Đánh giá BLOB/TEXT lớn và chọn `NOBLOB` chỉ khi replica/CDC không cần các trường đó.
- Theo dõi `Binlog_cache_disk_use` để nhận biết transaction cache spill ra đĩa.
- Đảm bảo filesystem binlog có dung lượng dự phòng và cảnh báo trước ngưỡng nguy hiểm.
- Kiểm tra tốc độ apply của replica sau batch lớn, import hoặc migration.

`binlog_row_event_max_size` là ngưỡng mục tiêu cho kích thước row event. Một hàng đơn lẻ quá lớn vẫn có thể khiến event vượt ngưỡng; biến này không giới hạn tổng kích thước transaction hay file binlog. Không nhầm nó với `max_binlog_size` hoặc `max_binlog_cache_size`.

## 13. PITR và ranh giới transaction

Khi cần phục hồi tới một thời điểm cụ thể, quy trình thường là restore full backup rồi phát lại binary log từ mốc backup đến ngay trước thao tác gây sự cố. Với row-based logging, `mysqlbinlog` có thể giải mã row event để hỗ trợ xác định transaction và thay đổi cần dừng.

Ví dụ đọc log theo khoảng thời gian:

```bash
mysqlbinlog \
  --start-datetime='2026-11-18 09:00:00' \
  --stop-datetime='2026-11-18 10:30:00' \
  mysql-bin.000250 mysql-bin.000251
```

Có thể dùng `--start-position` và `--stop-position` khi đã xác định vị trí event chính xác. Trong phục hồi production, cần kiểm tra ranh giới transaction: dừng giữa các row event của một transaction có thể tạo trạng thái không nhất quán. Hãy xác định điểm kết thúc tại ranh giới commit phù hợp và thử quy trình trên bản sao trước khi chạy trên hệ thống phục hồi thật.

`FULL` giúp đọc giá trị cũ và mới rõ hơn trong nhiều tình huống điều tra. Tuy nhiên, row image không tự tạo ra thao tác rollback an toàn. Việc đảo ngược một transaction cần hiểu logic nghiệp vụ, thứ tự phụ thuộc và các tác động ngoài database. Không chỉnh sửa file binlog gốc; hãy làm việc trên bản sao và giữ nguyên chuỗi log dùng cho phục hồi.

## 14. Ví dụ cấu hình theo mục tiêu

### 14.1. Hệ thống ưu tiên CDC và điều tra

```ini
[mysqld]
log_bin=mysql-bin
binlog_format=ROW
binlog_row_image=FULL
binlog_expire_logs_seconds=1209600
max_binlog_size=512M
```

Cấu hình này ưu tiên row image đầy đủ để consumer có thể đọc giá trị cũ/mới thuận tiện hơn. Đổi lại, dung lượng log có thể cao. Hãy kiểm tra consumer có thực sự cần full image và đo dung lượng trước khi chốt retention.

### 14.2. Hệ thống cập nhật bảng rộng, CDC hỗ trợ partial image

```ini
[mysqld]
log_bin=mysql-bin
binlog_format=ROW
binlog_row_image=MINIMAL
binlog_expire_logs_seconds=1209600
max_binlog_size=512M
```

`MINIMAL` có thể giảm đáng kể lượng dữ liệu nếu bảng có khóa duy nhất phù hợp và mỗi lần cập nhật chỉ thay đổi một vài cột. Trước khi áp dụng, kiểm thử replica và CDC consumer với cả `UPDATE` lẫn `DELETE`, đặc biệt ở table không có primary key.

### 14.3. Thay đổi runtime và phạm vi session

Một số biến có thể thay đổi động. Ví dụ:

```sql
SET GLOBAL binlog_row_image = 'MINIMAL';
```

Giá trị global thường là mặc định cho các kết nối mới; các session đang tồn tại có thể giữ giá trị session riêng. Nếu ứng dụng dùng connection pool, hãy kiểm tra giá trị trong session thực sự thực hiện DML. Cấu hình trong file cấu hình server hoặc cơ chế persist phù hợp để bảo đảm giá trị sau khi restart.

Không đổi row image hoặc binlog format giữa chừng mà không kiểm thử toàn bộ replica, CDC, công cụ backup và quy trình audit. Thay đổi cấu hình có thể làm thay đổi hình dạng event mà consumer nhận được.

## 15. Checklist giám sát binary log

Các lệnh sau cung cấp góc nhìn ban đầu về trạng thái log và cache:

```sql
-- Các file và kích thước
SHOW BINARY LOGS;

-- Cấu hình liên quan
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'max_binlog_size';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';

-- Cache transaction và statement
SHOW GLOBAL STATUS LIKE 'Binlog_cache_use';
SHOW GLOBAL STATUS LIKE 'Binlog_cache_disk_use';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache_use';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache_disk_use';

-- Trạng thái replica trên replica server
SHOW REPLICA STATUS\G
```

Khi xây dựng dashboard hoặc cảnh báo, theo dõi:

| Chỉ số | Câu hỏi vận hành |
|---|---|
| Tổng kích thước binlog | Tốc độ tăng log có vượt dự báo hoặc dung lượng volume không? |
| Kích thước log mới theo phút/giờ | Có batch hoặc transaction bất thường làm log tăng đột biến không? |
| Tuổi của file log cũ nhất | Cửa sổ PITR còn được bảo đảm bao lâu? |
| Replica lag và file/position | Replica có kịp đọc log trước khi hết hạn không? |
| `Binlog_cache_disk_use` | Giao dịch có thường xuyên phải spill cache xuống đĩa không? |
| Lỗi ghi log và dung lượng filesystem | Server có nguy cơ không ghi được binlog hoặc dừng ghi dữ liệu không? |

Đặt cảnh báo theo cả dung lượng tuyệt đối và tốc độ tăng. Một volume còn nhiều dung lượng vẫn có thể đầy nhanh nếu một tác vụ import tạo binlog lớn bất thường.

## 16. Bài tập thực hành

### Bài 1: So sánh row image

Trên môi trường thử nghiệm, tạo table có primary key, nhiều cột và một cột `TEXT`. Bật row-based logging rồi thực hiện cùng một câu `UPDATE` dưới các cấu hình `FULL`, `MINIMAL` và `NOBLOB`.

```sql
CREATE TABLE lab_orders (
  order_id BIGINT NOT NULL PRIMARY KEY,
  customer_id BIGINT NOT NULL,
  status VARCHAR(24) NOT NULL,
  note TEXT,
  total DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO lab_orders
  (order_id, customer_id, status, note, total)
VALUES
  (1, 1001, 'new', REPEAT('x', 10000), 125.00);

UPDATE lab_orders
SET status = 'shipped'
WHERE order_id = 1;
```

Đọc binlog bằng `mysqlbinlog --base64-output=DECODE-ROWS -vv`. Ghi lại cột xuất hiện trong before/after image và so sánh kích thước file. Thực hiện thêm một table không có khóa chính để quan sát khác biệt trong before image.

### Bài 2: Quan sát transaction event group

Mở transaction, cập nhật hai table rồi commit:

```sql
START TRANSACTION;
UPDATE sales.orders
SET status = 'processing'
WHERE order_id = 105;

UPDATE sales.order_items
SET quantity = quantity + 1
WHERE order_id = 105 AND product_id = 7;
COMMIT;
```

Dùng `SHOW BINLOG EVENTS` hoặc `mysqlbinlog -vv` để tìm GTID, `BEGIN`, table map, row event và commit marker. Sau đó chạy một transaction tương tự nhưng `ROLLBACK` và so sánh nội dung binlog.

### Bài 3: Theo dõi transaction cache

Tạo một transaction cập nhật nhiều hàng trên môi trường thử nghiệm. Ghi lại `Binlog_cache_use` và `Binlog_cache_disk_use` trước/sau. Thử tăng khối lượng transaction để quan sát khi cache phải dùng file tạm. Không dùng production để tạo transaction lớn chỉ nhằm thử nghiệm.

### Bài 4: Xây dựng chính sách retention

Giả sử full backup chạy mỗi ngày, replica có thể chậm tối đa 36 giờ và tổ chức cần PITR trong 7 ngày. Hãy xác định retention cần lớn hơn cửa sổ PITR 7 ngày và có biên an toàn cho thời gian phục hồi, replica lag và gián đoạn vận hành. Đo binlog trung bình mỗi ngày, tính dung lượng cần thiết rồi xác định ngưỡng cảnh báo volume.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Binlog tăng nhanh sau khi chuyển sang `ROW` | Nhiều hàng bị cập nhật hoặc row image lớn | Kiểm tra tốc độ ghi, loại table, `binlog_row_image` và các batch job. |
| `MINIMAL` không giảm nhiều dung lượng | Table thiếu primary key/unique key phù hợp hoặc nhiều cột thay đổi | Kiểm tra schema và row event thực tế bằng `mysqlbinlog -vv`. |
| CDC thiếu giá trị cũ | Consumer đang đọc partial image | Kiểm tra `binlog_row_image`, cấu hình connector và yêu cầu dữ liệu cũ/mới. |
| File binlog vượt `max_binlog_size` | Một transaction lớn hơn ngưỡng | Kiểm tra transaction lớn; nhớ rằng transaction không bị chia giữa các file. |
| `Binlog_cache_disk_use` tăng | Transaction cache vượt vùng bộ nhớ và spill ra đĩa | Kiểm tra kích thước transaction, I/O và cache; chỉ điều chỉnh sau khi đo. |
| Replica dừng vì thiếu binlog | File cần thiết đã bị purge hoặc hết hạn | Đối chiếu file/position replica với danh sách log; có thể cần dựng lại replica. |
| Không thể PITR đến mốc mong muốn | Thiếu một file trong chuỗi binlog hoặc retention quá ngắn | Kiểm tra full backup, chuỗi log đã lưu và quy trình archive. |
| Đĩa đầy dù mỗi file có giới hạn | `max_binlog_size` chỉ điều khiển kích thước file, không giới hạn tổng log | Kiểm tra retention, tổng dung lượng, tốc độ tăng và purge policy. |

## 18. Quy trình chọn row image và quản lý dung lượng

1. **Xác định consumer.** Liệt kê replica, CDC, audit, công cụ backup và yêu cầu điều tra cần đọc binlog.
2. **Kiểm kê schema.** Xác định table có primary key/unique key, cột lớn và tần suất cập nhật.
3. **Chọn row image.** Dùng `FULL` nếu cần ảnh đầy đủ; cân nhắc `MINIMAL` nếu consumer hỗ trợ partial image; dùng `NOBLOB` khi các trường BLOB/TEXT không cần thiết.
4. **Đo dữ liệu thực tế.** So sánh tốc độ tăng binlog dưới tải bình thường và cao điểm trước khi áp dụng rộng.
5. **Thiết lập cache hợp lý.** Theo dõi cache spill, kích thước transaction và I/O trước khi điều chỉnh các biến cache.
6. **Thiết lập file rotation và retention.** Chọn `max_binlog_size`, `binlog_expire_logs_seconds` và dung lượng volume theo tốc độ ghi cùng yêu cầu PITR.
7. **Bảo vệ chuỗi log.** Archive log ra nơi lưu trữ phù hợp, kiểm tra tính liên tục và bảo vệ quyền truy cập.
8. **Kiểm thử phục hồi.** Restore full backup rồi phát lại log đến một mốc thử nghiệm; xác minh kết quả và thời gian phục hồi.

Binary log là một phần của thiết kế phục hồi dữ liệu. Row image quyết định mức chi tiết của thay đổi, transaction event group xác định ranh giới commit, còn cache và retention quyết định server có thể ghi và giữ log trong bao lâu. Hãy cấu hình ba phần này dựa trên nhu cầu replication, CDC, PITR và số liệu tải thực tế; sau đó xác minh bằng cách đọc log và diễn tập phục hồi định kỳ.
