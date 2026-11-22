# Error log, general log, slow query log và phạm vi dữ liệu ghi nhận

MySQL có nhiều loại log để trả lời những câu hỏi vận hành khác nhau. Khi server khởi động thất bại, InnoDB recovery hoặc plugin gặp lỗi, cần xem **error log**. Khi cần biết client nào đã kết nối và gửi câu SQL nào, có thể bật **general query log**. Khi cần tìm những câu lệnh chạy lâu hoặc đọc quá nhiều hàng, dùng **slow query log**.

Ba log này ghi nhận các phạm vi dữ liệu khác nhau. Error log tập trung vào sự kiện và chẩn đoán của server; general log ghi rộng các kết nối/lệnh server nhận được; slow query log chỉ ghi các câu lệnh thỏa điều kiện lọc. Không log nào tự nó là bản ghi đầy đủ mọi thay đổi dữ liệu ở mức từng hàng hoặc là hệ thống audit hoàn chỉnh.

Việc bật log cũng có chi phí: ghi đĩa, CPU, dung lượng lưu trữ, I/O và nguy cơ lộ câu SQL chứa dữ liệu nhạy cảm. Người vận hành cần biết log nào trả lời câu hỏi nào, bật trong bao lâu, log ghi tới đâu, ai được đọc và cách xoay vòng/xóa dữ liệu theo retention policy.

## 1. Ba loại log giải quyết ba câu hỏi khác nhau

| Log | Câu hỏi chính | Nội dung thường ghi | Mặc định thường gặp |
| --- | --- | --- | --- |
| Error log | Server gặp chuyện gì? | Lỗi, cảnh báo, ghi chú, startup/shutdown, recovery, component/plugin messages | Được bật |
| General query log | Client đã gửi những lệnh nào? | Kết nối/ngắt kết nối và câu lệnh server nhận được | Tắt |
| Slow query log | Câu lệnh nào cần điều tra hiệu năng? | Câu lệnh thỏa ngưỡng thời gian/số hàng và metadata thực thi | Tắt |

Error log không thay thế general log; general log không cho biết đầy đủ kế hoạch thực thi; slow query log không ghi mọi truy vấn. Chọn log dựa trên câu hỏi điều tra thay vì bật tất cả trong thời gian dài.

## 2. Error log ghi nhận điều gì?

Error log là kênh chẩn đoán chính của MySQL server. Nó ghi các thông báo về vòng đời server và những sự kiện cần chú ý, ví dụ:

- Server bắt đầu khởi động, đọc cấu hình và mở cổng.
- Plugin/component không tải được hoặc cấu hình không hợp lệ.
- InnoDB phát hiện recovery, rollback hoặc lỗi lưu trữ.
- Server phát cảnh báo về cấu hình, tài nguyên hoặc trạng thái nội bộ.
- Server shutdown bình thường hoặc kết thúc do lỗi.
- Các sự kiện liên quan replication, kết nối nội bộ hoặc subsystem có thông báo lỗi.

Error log thường có timestamp, mức độ thông báo và nội dung message. Định dạng cụ thể phụ thuộc error-log component, sink và phiên bản MySQL. Nó không được thiết kế để ghi toàn bộ SQL của mọi ứng dụng hoặc từng giá trị OLD/NEW của mỗi hàng.

Không phải mọi lỗi do một câu SQL của client gây ra đều nhất thiết xuất hiện trong error log. Nhiều lỗi statement-level được trả về trực tiếp cho client; muốn biết client đã gửi câu lệnh nào, xem general log trong thời gian điều tra hoặc log ứng dụng. Error log tập trung vào sự kiện/chẩn đoán server, không phải nhật ký đầy đủ của mọi lỗi nghiệp vụ.

## 3. Xác định nơi ghi error log

Kiểm tra biến cấu hình hiện hành:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error';
SHOW GLOBAL VARIABLES LIKE 'log_error_services';
SHOW GLOBAL VARIABLES LIKE 'log_error_verbosity';
SHOW GLOBAL VARIABLES LIKE 'log_timestamps';
```

`log_error` cho biết đường dẫn file error log nếu server dùng file sink. Tùy nền tảng, service manager hoặc container, thông báo cũng có thể được chuyển tới standard error, system journal hoặc một sink khác. Không mặc định mọi cài đặt đều ghi vào cùng một file `hostname.err`.

Trên Linux dùng systemd, có thể cần kiểm tra journal của service; trong container, log có thể được thu từ stdout/stderr. Trên Windows, kiểm tra đường dẫn file do `log_error` cấu hình và cấu hình Windows Service tương ứng.

## 4. Mức độ thông báo trong error log

`log_error_verbosity` điều khiển mức độ chi tiết của thông báo error log trong các cấu hình dùng internal log filter:

| Giá trị | Nội dung |
| --- | --- |
| `1` | Chỉ lỗi (errors) |
| `2` | Lỗi và cảnh báo (errors, warnings) |
| `3` | Lỗi, cảnh báo và ghi chú (errors, warnings, notes) |

Kiểm tra:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error_verbosity';
```

Giảm verbosity có thể làm mất thông tin hữu ích khi điều tra. Tăng verbosity có thể tạo thêm log. Chọn mức theo chính sách vận hành và theo dõi dung lượng; không dùng thay đổi verbosity để che giấu một lỗi đang cần xử lý.

## 5. Error-log components và sink

Trong MySQL 8.0, error logging được tổ chức theo component. `log_error_services` xác định các component filter và sink tham gia xử lý thông báo. Cấu hình mặc định thường gồm internal filter và internal sink; các bản cài đặt có thể thay đổi để tích hợp nơi nhận log khác.

Kiểm tra:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error_services';
```

Một filter có thể điều chỉnh thông báo trước khi sink ghi chúng. Sink quyết định nơi xuất log. Khi thay đổi chuỗi component, phải dùng đúng tên component có sẵn và thứ tự được tài liệu phiên bản hỗ trợ. Cấu hình sai có thể làm mất kênh log quan trọng; hãy thử trên staging và giữ khả năng rollback.

## 6. Timestamp và múi giờ của log

`log_timestamps` điều khiển múi giờ timestamp được ghi trong error log, general query log và slow query log:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_timestamps';
```

Các giá trị thường dùng là `UTC` và `SYSTEM`. Dùng UTC giúp gom log từ nhiều server ở các múi giờ khác nhau và đối chiếu với hệ thống tập trung. Nếu dùng `SYSTEM`, timestamp theo múi giờ hệ điều hành của host.

Khi điều tra sự cố, xác định timezone của log trước khi đối chiếu với log ứng dụng, trace hoặc metric. Không cộng/trừ giờ theo cảm tính; lưu lại timezone và đồng bộ đồng hồ host bằng NTP hoặc cơ chế tương đương.

## 7. Error log trong Performance Schema

Trên các phiên bản hỗ trợ bảng `performance_schema.error_log` (MySQL 8.0.22 trở lên), có thể đọc một phần error log từ SQL:

```sql
SELECT
    LOGGED,
    PRIO,
    ERROR_CODE,
    SUBSYSTEM,
    DATA
FROM performance_schema.error_log
ORDER BY LOGGED DESC
LIMIT 100;
```

Bảng này hữu ích cho truy vấn/chẩn đoán tập trung, nhưng không nên giả định nó giữ toàn bộ lịch sử vô hạn hoặc thay thế file/journal và hệ thống log aggregation. Phạm vi dữ liệu có sẵn phụ thuộc phiên bản, component và cấu hình. Khi cần lịch sử dài hạn, cấu hình chuyển log tới hệ thống lưu trữ tập trung với retention phù hợp.

## 8. General query log ghi nhận điều gì?

General query log ghi rộng hoạt động client mà server nhận được, gồm:

- Thời điểm client kết nối và ngắt kết nối.
- User/host và thread/connection ID liên quan.
- Loại command được gửi.
- Nội dung câu lệnh hoặc command text mà server nhận.

Log này giúp điều tra một client có đang gửi câu SQL lặp bất thường, một tài khoản có kết nối vào thời điểm nào hoặc một câu lệnh có được gửi đến server hay không.

General log ghi command khi server nhận được, trước khi có thể kết luận statement thành công. Với nhiều connection đồng thời, thứ tự nhận command trong log không nhất thiết là thứ tự statement hoàn tất hoặc transaction commit. Log không ghi result set trả về cho client, không phải ảnh chụp dữ liệu trước/sau mỗi hàng và không tự cung cấp đầy đủ thời gian thực thi hay execution plan. Một câu lệnh xuất hiện trong general log có nghĩa server đã nhận command; không nên suy ra rằng statement chắc chắn commit thành công.

## 9. Bật và tắt general query log

Kiểm tra trạng thái và nơi ghi:

```sql
SHOW GLOBAL VARIABLES LIKE 'general_log';
SHOW GLOBAL VARIABLES LIKE 'general_log_file';
SHOW GLOBAL VARIABLES LIKE 'log_output';
```

Bật tạm thời:

```sql
SET GLOBAL general_log = ON;
```

Tắt sau khi thu thập xong:

```sql
SET GLOBAL general_log = OFF;
```

General log thường tắt mặc định vì ghi mọi command có thể tạo tải và dữ liệu rất lớn. Bật trong một cửa sổ điều tra ngắn, ghi rõ thời điểm bật/tắt và xác nhận lại trạng thái sau khi hoàn thành.

Thay đổi `general_log` là thay đổi global; cần quyền quản trị phù hợp. Nếu muốn cấu hình qua restart, đặt option `general_log` trong group server, nhưng không nên bật vô thời hạn nếu không có lý do vận hành rõ ràng.

## 10. General log ghi vào FILE hay TABLE?

`log_output` điều khiển đích ghi của general query log và slow query log:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_output';
```

Các lựa chọn:

| Giá trị | Hành vi |
| --- | --- |
| `FILE` | Ghi ra file log |
| `TABLE` | Ghi vào các bảng log trong schema `mysql` |
| `FILE,TABLE` | Ghi vào cả file và table |
| `NONE` | Không ghi general/slow query log dù biến bật |

Ví dụ:

```sql
SET GLOBAL log_output = 'FILE';
```

`log_output` áp dụng cho general và slow query log; nó không điều khiển error log. Error log có cấu hình component/sink riêng.

Nếu `log_output='NONE'`, general/slow query log không ghi ra FILE hoặc TABLE dù `general_log` hay `slow_query_log` đang ON. Khi điều tra “đã bật log nhưng không thấy file”, phải kiểm tra cả cờ bật log lẫn `log_output`.

## 11. Đọc general log từ bảng mysql.general_log

Khi `log_output` có `TABLE`, general query log được ghi vào `mysql.general_log`:

```sql
SELECT
    event_time,
    user_host,
    thread_id,
    command_type,
    argument
FROM mysql.general_log
ORDER BY event_time DESC
LIMIT 100;
```

Các trường thường gặp gồm thời điểm, user/host, thread ID, command type và nội dung argument. Schema bảng log phụ thuộc phiên bản MySQL. Cần quyền đọc bảng `mysql.general_log`; không cấp quyền này rộng cho user ứng dụng.

Khi log volume lớn, truy vấn trực tiếp bảng log cũng có thể tốn tài nguyên. Giới hạn khoảng thời gian, chọn cột cần thiết và giới hạn số hàng; không dùng `SELECT *` để tải toàn bộ log.

## 12. General log ra file

Kiểm tra file đích:

```sql
SHOW GLOBAL VARIABLES LIKE 'general_log_file';
```

Đường dẫn có thể được đặt bằng startup option `general_log_file` hoặc thay đổi theo cấu hình runtime nếu biến hỗ trợ. Process MySQL cần quyền ghi vào thư mục đích. Nếu file không xuất hiện, kiểm tra `log_output`, `general_log`, đường dẫn và quyền filesystem.

File log thường được đọc bằng công cụ hệ điều hành hoặc đưa vào pipeline log aggregation. Cần bảo vệ quyền đọc vì nội dung SQL có thể chứa email, số điện thoại, token, thông tin cá nhân hoặc literal nhạy cảm.

## 13. Slow query log ghi nhận điều gì?

Slow query log ghi các câu lệnh thỏa điều kiện được cấu hình, thường dựa trên thời gian thực thi và số hàng được kiểm tra. Nó giúp tìm truy vấn có độ trễ cao, scan quá nhiều hàng hoặc thao tác quản trị tốn thời gian.

Một entry thường chứa:

- Thời điểm truy vấn bắt đầu.
- User/host, thread ID và database nếu có.
- `Query_time`: thời gian thực thi được ghi nhận.
- `Lock_time`: thời gian chờ lock được ghi nhận theo định nghĩa log.
- `Rows_sent`: số hàng trả về.
- `Rows_examined`: số hàng được kiểm tra.
- Nội dung SQL.

Slow log không tự giải thích nguyên nhân chậm. Sau khi tìm được truy vấn, tiếp tục dùng `EXPLAIN`, `EXPLAIN ANALYZE` (khi phiên bản hỗ trợ), Performance Schema và dữ liệu thống kê để xác định access path, lock wait, I/O hoặc nguyên nhân khác.

## 14. Bật slow query log

Kiểm tra:

```sql
SHOW GLOBAL VARIABLES LIKE 'slow_query_log';
SHOW GLOBAL VARIABLES LIKE 'slow_query_log_file';
SHOW GLOBAL VARIABLES LIKE 'long_query_time';
SHOW GLOBAL VARIABLES LIKE 'min_examined_row_limit';
```

Bật log:

```sql
SET GLOBAL slow_query_log = ON;
```

Đặt ngưỡng một giây cho session hiện tại:

```sql
SET SESSION long_query_time = 1;
```

Hoặc đặt global default cho các session mới:

```sql
SET GLOBAL long_query_time = 1;
```

`long_query_time` có cả global và session scope. Thay đổi global thường ảnh hưởng giá trị mặc định mà session mới kế thừa; connection đang tồn tại có thể vẫn giữ session value cũ. Nếu đang thử nghiệm ngay trong connection hiện tại, đặt `SET SESSION` hoặc đọc `@@SESSION.long_query_time` để xác nhận.

## 15. long_query_time và min_examined_row_limit

`long_query_time` xác định ngưỡng thời gian để một statement được xem là chậm. Giá trị mặc định thường là 10 giây; biến hỗ trợ độ chính xác dưới giây. Cấu hình thực tế cần căn cứ SLA và loại workload.

`min_examined_row_limit` cho phép bỏ qua những statement kiểm tra ít hơn số hàng quy định, kể cả khi thời gian vượt ngưỡng. Ví dụ:

```sql
SET GLOBAL long_query_time = 0.5;
SET GLOBAL min_examined_row_limit = 100;
```

Hai tham số cần được xem cùng nhau. Nếu đặt `min_examined_row_limit` quá cao, có thể bỏ lỡ một truy vấn chậm do lock hoặc I/O nhưng chỉ kiểm tra ít hàng. Nếu đặt ngưỡng thời gian quá thấp, log có thể tăng rất nhanh.

## 16. Ghi truy vấn không dùng index

`log_queries_not_using_indexes` có thể yêu cầu ghi các truy vấn không sử dụng index vào slow query log, ngay cả khi chúng không vượt `long_query_time`:

```sql
SET GLOBAL log_queries_not_using_indexes = ON;
```

Không dùng index không đồng nghĩa chắc chắn truy vấn có vấn đề. Table scan có thể là lựa chọn tốt nhất khi bảng nhỏ hoặc truy vấn cần phần lớn hàng. Cần xem số hàng, độ chọn lọc, execution plan và tần suất chạy.

Nếu bật logging cho truy vấn không dùng index, log có thể tăng đột biến. Có thể cấu hình `log_throttle_queries_not_using_indexes` để giới hạn số entry loại này trong một khoảng thời gian theo quy tắc MySQL.

## 17. Ghi các câu lệnh quản trị chậm

`log_slow_admin_statements` cho phép ghi các câu lệnh quản trị đủ điều kiện thời gian vào slow query log, ví dụ một số thao tác `ALTER TABLE`, `CREATE INDEX`, `DROP INDEX`, `ANALYZE TABLE`, `OPTIMIZE TABLE` hoặc `REPAIR TABLE` tùy engine/phiên bản.

Kiểm tra và bật khi cần:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_slow_admin_statements';
SET GLOBAL log_slow_admin_statements = ON;
```

Điều này hữu ích khi điều tra migration hoặc maintenance kéo dài. Không nên bật thêm mọi tùy chọn log mà không xác định mục tiêu; theo dõi volume và tắt cấu hình mở rộng khi kết thúc điều tra.

## 18. Slow log ra FILE hoặc TABLE

Slow query log dùng chung `log_output` với general log. Nếu `log_output='FILE'`, kiểm tra file đích:

```sql
SHOW GLOBAL VARIABLES LIKE 'slow_query_log_file';
```

Nếu `log_output='TABLE'`, đọc từ `mysql.slow_log`:

```sql
SELECT
    start_time,
    user_host,
    query_time,
    lock_time,
    rows_sent,
    rows_examined,
    sql_text
FROM mysql.slow_log
ORDER BY start_time DESC
LIMIT 100;
```

Tên/cấu trúc cột có thể thay đổi theo phiên bản. Dùng `SHOW CREATE TABLE mysql.slow_log` hoặc metadata trên server trước khi viết công cụ phụ thuộc schema.

## 19. Phạm vi dữ liệu của ba log

| Dữ liệu | Error log | General log | Slow query log |
| --- | --- | --- | --- |
| Startup/shutdown và recovery messages | Có | Không phải mục tiêu | Không phải mục tiêu |
| Kết nối/ngắt kết nối client | Không phải phạm vi chính | Có | Không ghi đầy đủ |
| Nội dung SQL nhận được | Chỉ khi message lỗi có liên quan | Ghi rộng | Chỉ statement thỏa điều kiện |
| Query time/rows examined | Không | Không | Có các trường tương ứng |
| Result set trả cho client | Không | Không | Không |
| Ảnh OLD/NEW của từng hàng | Không | Không | Không |
| Execution plan đầy đủ | Không | Không | Không |
| Mọi statement nhanh | Không | Có, nếu general log bật | Không |

Không dùng general hoặc slow query log như row-based audit trail. Nếu cần biết chính xác hàng nào đã đổi từ giá trị nào sang giá trị nào, cần audit mechanism hoặc CDC/binlog được thiết kế cho mục tiêu đó.

General log cũng không phải security audit hoàn chỉnh: nó không tự gắn kết mỗi câu SQL với danh tính người dùng cuối của ứng dụng, không chứng minh commit và không ghi đầy đủ before/after image. Với yêu cầu truy vết truy cập hoặc tuân thủ, dùng giải pháp audit chuyên biệt, quản lý danh tính và retention rõ ràng.

## 20. General log không chứng minh transaction đã commit

General log ghi command server nhận. Một câu `UPDATE` có thể xuất hiện trong general log nhưng transaction sau đó rollback; một câu lệnh có thể thất bại vì constraint hoặc quyền; client có thể mất kết nối trước khi nhận kết quả.

Do đó, khi điều tra “ai đã gửi câu lệnh nào”, general log hữu ích. Khi điều tra “thay đổi nào đã commit”, cần đối chiếu transaction state, binary log, audit/CDC hoặc dữ liệu ứng dụng theo kiến trúc hệ thống. Không suy ra commit chỉ từ việc thấy SQL trong general log.

## 21. Prepared statements và nội dung được ghi

Ứng dụng có thể gửi câu lệnh theo protocol prepared statement. Log thể hiện command/SQL theo cách MySQL ghi nhận ở từng loại log và phiên bản; không nên xây công cụ dựa trên giả định mọi prepared statement sẽ xuất hiện đúng một chuỗi SQL đã nội suy đầy đủ mọi parameter.

Nếu cần điều tra giá trị parameter, kiểm tra hành vi driver/server trên phiên bản cụ thể trong môi trường an toàn. Không bật general log production chỉ để cố lấy mọi parameter nếu chưa đánh giá rủi ro lộ dữ liệu và chi phí.

## 22. Chi phí và rủi ro khi bật log

General log có thể ghi mỗi command và connection event, vì vậy volume tăng theo QPS và số kết nối. Slow log thường chọn lọc hơn, nhưng có thể tăng mạnh khi ngưỡng thấp hoặc bật log truy vấn không dùng index. Error log cần duy trì để chẩn đoán nhưng cũng cần quản lý sink, dung lượng và retention.

Các chi phí cần tính:

- CPU để tạo/format log entry.
- I/O và dung lượng file/table.
- Lock/contention bổ sung khi ghi log table.
- Network và chi phí ingest nếu chuyển tới hệ thống tập trung.
- Chi phí lưu trữ, tìm kiếm và retention.
- Rủi ro lộ SQL literal, thông tin cá nhân hoặc dữ liệu bí mật.

Không bật general log trong thời gian dài trên workload có lưu lượng lớn nếu chưa đo tác động. Dùng slow log với ngưỡng phù hợp để điều tra hiệu năng thường hữu ích hơn.

## 23. Bảo vệ dữ liệu nhạy cảm trong log

SQL text có thể chứa literal như email, số điện thoại, địa chỉ, access token hoặc dữ liệu thanh toán. Bất kỳ người nào đọc file general/slow log hoặc bảng `mysql.general_log`/`mysql.slow_log` có thể tiếp cận thông tin đó.

Biện pháp vận hành:

- Hạn chế quyền đọc file và bảng log cho nhóm DBA/on-call cần thiết.
- Không cấp `SELECT` trên schema `mysql` cho tài khoản ứng dụng chỉ để tiện tra cứu.
- Tránh đặt password/token trực tiếp trong câu SQL hoặc command line.
- Dùng prepared statements và cơ chế secret phù hợp; lưu ý log vẫn có thể chứa statement/parameter context tùy đường thực thi.
- Che/redact dữ liệu trước khi gửi log tới ticket, chat hoặc dịch vụ bên ngoài.
- Mã hóa log khi lưu/truyền nếu chính sách dữ liệu yêu cầu.
- Thiết lập retention và xóa log theo chính sách bảo vệ dữ liệu.

Log có thể chứa dữ liệu nhạy cảm ngay cả khi mục tiêu ban đầu chỉ là debug. Xử lý log theo phân loại dữ liệu tương đương nguồn dữ liệu mà nó ghi nhận.

## 24. Xoay vòng và quản lý dung lượng log

Với log file, có thể yêu cầu MySQL đóng/mở lại file bằng lệnh FLUSH phù hợp:

```sql
FLUSH ERROR LOGS;
FLUSH GENERAL LOGS;
FLUSH SLOW LOGS;
```

Hoặc dùng:

```sql
FLUSH LOGS;
```

Lệnh flush/reopen cần quyền quản trị phù hợp. Khi dùng logrotate hoặc hệ thống quản lý file bên ngoài, phối hợp thao tác rename/rotate với việc yêu cầu MySQL mở file mới; nếu chỉ xóa/di chuyển file đang được process mở, MySQL có thể tiếp tục ghi vào file descriptor cũ.

Nếu log ghi vào TABLE, quản lý dung lượng bảng log và retention theo cách phù hợp với phiên bản. Trước khi truncate hoặc thay đổi log table, tham khảo hướng dẫn MySQL và tắt logging tương ứng nếu cần; không thao tác tùy tiện trên bảng hệ thống đang được server ghi.

## 25. Đọc slow log và đi từ log tới nguyên nhân

Quy trình điều tra truy vấn chậm:

1. Lọc các entry theo `Query_time`, `Rows_examined`, user/host và database.
2. Gom nhóm câu SQL tương tự để nhận diện mẫu lặp, không chỉ nhìn một entry riêng lẻ.
3. Kiểm tra query có tham số nào làm cardinality khác biệt đáng kể không.
4. Chạy `EXPLAIN` để xem access type, key, estimated rows và join order.
5. Dùng `EXPLAIN ANALYZE` trên môi trường phù hợp để so sánh actual rows/time với estimate.
6. Kiểm tra index, statistics, lock waits, I/O, buffer pool và contention.
7. Sửa truy vấn/index hoặc dữ liệu phù hợp; đo lại bằng workload đại diện.
8. Điều chỉnh ngưỡng slow log sau khi hoàn tất điều tra.

`Rows_examined` lớn so với `Rows_sent` là tín hiệu cần xem xét, nhưng không tự chứng minh thiếu index. Truy vấn aggregate, báo cáo hoặc truy vấn cần đọc nhiều dữ liệu có thể hợp lý khi examine nhiều hàng.

## 26. Kết hợp log với Performance Schema và sys schema

Slow query log là nguồn hữu ích để tìm statement chậm theo ngưỡng. Performance Schema cung cấp thống kê statement, wait, stage, transaction và metadata lock chi tiết hơn tùy instrument/consumer được bật. `sys` schema trình bày nhiều thống kê theo dạng dễ đọc.

Ví dụ xem digest statement theo thời gian và số lần thực thi:

```sql
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    rows_examined,
    rows_sent
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
```

View và cột của sys schema có thể khác theo phiên bản. Performance Schema có buffer hữu hạn và một số consumer/instrument có thể tắt; không coi nó là lịch sử vô hạn. Dùng log file/monitoring platform cho lịch sử dài hạn và Performance Schema để drill down trạng thái hiện tại/gần đây.

## 27. Bật log qua cấu hình startup

Có thể cấu hình trong option file:

```ini
[mysqld]
log_error=/var/log/mysql/error.log
log_error_verbosity=3
log_timestamps=UTC

general_log=OFF
slow_query_log=ON
slow_query_log_file=/var/log/mysql/slow.log
long_query_time=1
min_examined_row_limit=100
log_output=FILE
```

Đường dẫn là ví dụ Linux; trên Windows dùng path phù hợp và bảo đảm tài khoản service có quyền ghi. Error log được cấu hình độc lập với `log_output`. Chỉ bật general log qua startup khi có yêu cầu điều tra/kiểm soát được phê duyệt và retention phù hợp.

## 28. Runbook điều tra theo triệu chứng

| Triệu chứng | Log/nguồn bắt đầu | Bước tiếp theo |
| --- | --- | --- |
| MySQL không khởi động | Error log, system journal | Kiểm tra option sai, permission, port, InnoDB recovery và disk |
| Server restart bất ngờ | Error log, OS/service manager logs | Xác định crash, OOM kill, shutdown signal hoặc lỗi host |
| Không rõ client gửi SQL nào | General log bật trong thời gian ngắn | Lọc theo user/host/thread và timestamp |
| API có độ trễ cao | Slow query log, Performance Schema | Phân tích digest, EXPLAIN, lock wait và rows examined |
| Nhiều table scan | Slow log + `log_queries_not_using_indexes` có kiểm soát | Phân biệt scan hợp lý với thiếu index |
| Log tăng nhanh | Kiểm tra general/slow settings, `log_output`, QPS | Tắt logging mở rộng, throttle, rotate và retention |
| Log chứa dữ liệu nhạy cảm | File/table log và quyền truy cập | Hạn chế quyền, redact, rotate và xử lý theo chính sách |

## 29. Bài tập thực hành

1. Xem `log_error`, `log_error_verbosity`, `log_timestamps` và xác định error log thực tế trên môi trường lab.
2. Tạo một lỗi cấu hình trong môi trường thử nghiệm; đọc thông báo tương ứng trong error log.
3. Bật general log trong một khoảng thời gian ngắn; thực hiện connect, SELECT, INSERT thất bại và disconnect; quan sát entry.
4. Tắt general log và xác nhận trạng thái global đã OFF.
5. Đặt `log_output='TABLE'`; đọc `mysql.general_log` và xác định các trường event_time, user_host, thread_id, command_type, argument.
6. Bật slow query log với `long_query_time` thấp trên lab; chạy một truy vấn có chủ đích chậm.
7. Thử thay đổi `long_query_time` global và session; so sánh giá trị trong connection hiện tại với connection mới.
8. Đặt `min_examined_row_limit`; quan sát truy vấn ít hàng có bị loại khỏi slow log không.
9. Bật `log_queries_not_using_indexes` trong thời gian ngắn; xem log tăng ra sao và tắt lại.
10. Bật `log_slow_admin_statements`; thực hiện một thao tác maintenance trong lab và quan sát slow log.
11. So sánh FILE và TABLE output; đo tác động khi log volume tăng.
12. Dùng `EXPLAIN` và `EXPLAIN ANALYZE` để phân tích một truy vấn được tìm thấy trong slow log.
13. Thực hiện `FLUSH SLOW LOGS` sau khi rotate file trong môi trường thử nghiệm.
14. Kiểm tra quyền đọc log và tạo quy tắc che dữ liệu nhạy cảm trước khi chia sẻ.

## 30. Ghi nhớ

Error log ghi sự kiện và thông báo chẩn đoán của server như startup/shutdown, lỗi, cảnh báo, recovery và component messages. General query log ghi rộng connection event và command/SQL server nhận, nhưng không ghi result set, row image hay chứng minh transaction đã commit. Slow query log ghi statement thỏa ngưỡng như `long_query_time` và `min_examined_row_limit`, cùng metadata như `Query_time`, `Lock_time`, `Rows_sent`, `Rows_examined`; nó không ghi mọi query nhanh.

`log_output` điều khiển FILE/TABLE/NONE cho general và slow log, không điều khiển error log. `general_log` và `slow_query_log` thường tắt mặc định; bật general log trong thời gian ngắn vì volume và chi phí cao. `long_query_time` có global/session scope nên cần kiểm tra giá trị session đang chạy. Dùng error-log verbosity/timestamps/components đúng mục tiêu; đọc log qua file, system journal hoặc bảng Performance Schema phù hợp phiên bản. Bảo vệ log như dữ liệu nhạy cảm, giới hạn quyền, xoay vòng/retention, và dùng slow log để tìm ứng viên rồi tiếp tục phân tích bằng EXPLAIN, Performance Schema và sys schema. Không coi ba log này là hệ thống audit row-level hoàn chỉnh.
