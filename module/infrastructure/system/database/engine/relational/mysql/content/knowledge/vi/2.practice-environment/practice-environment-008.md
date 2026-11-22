# Kiểm tra phiên bản, storage engine và các biến cấu hình quan trọng

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định phiên bản và bản phân phối của máy chủ MySQL đang kết nối, đồng thời phân biệt với phiên bản client.
- Kiểm tra storage engine được máy chủ hỗ trợ, engine mặc định và engine thực tế của từng bảng.
- Đọc các biến cấu hình quan trọng liên quan đến kết nối, bộ nhớ, transaction, charset, log và replication.
- Phân biệt biến cấu hình cấp global với session, biến cấu hình với chỉ số trạng thái, và biết cách thu thập thông tin an toàn trước khi thay đổi cấu hình.

## 1. Vì sao cần kiểm tra môi trường trước khi làm việc?

Hai máy chủ cùng chạy MySQL có thể khác nhau về phiên bản, bản phân phối, storage engine, giới hạn kết nối, bộ nhớ, chế độ SQL và cấu hình transaction. Những khác biệt này ảnh hưởng trực tiếp đến cú pháp được hỗ trợ, cách lưu dữ liệu, tính toàn vẹn, hiệu năng và khả năng khôi phục.

Trước khi tạo schema, chạy migration, điều tra truy vấn chậm hoặc triển khai ứng dụng, hãy ghi nhận môi trường thực tế. Không nên suy luận cấu hình từ tên máy chủ, file cấu hình mẫu, cổng `3306` hay phiên bản của chương trình client. Máy chủ đang xử lý truy vấn mới là nguồn thông tin cần kiểm tra.

Trong bài này, các lệnh chủ yếu là lệnh đọc thông tin. Bạn có thể chạy chúng bằng MySQL client, MariaDB client hoặc công cụ quản trị tương thích, miễn là tài khoản có quyền xem các thông tin tương ứng.

## 2. Xác định phiên bản và bản phân phối của server

### 2.1. Truy vấn từ phiên kết nối

Sau khi đăng nhập vào server, chạy:

```sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@version_compile_os AS operating_system,
    @@version_compile_machine AS architecture;
```

- `VERSION()` trả về chuỗi phiên bản do server công bố. Chuỗi này thường giúp nhận biết MySQL, MariaDB hoặc một bản phân phối tương thích.
- `@@version_comment` cung cấp mô tả bản phân phối hoặc gói máy chủ.
- `@@version_compile_os` và `@@version_compile_machine` mô tả hệ điều hành và kiến trúc dùng để biên dịch server trong các bản hỗ trợ các biến này.

Có thể xem riêng nhóm biến phiên bản:

```sql
SHOW GLOBAL VARIABLES LIKE 'version%';
```

Ví dụ, `VERSION()` có thể trả về chuỗi chứa `8.0.x` trên MySQL hoặc `10.x-MariaDB` trên MariaDB. Đây chỉ là ví dụ minh họa; hãy ghi lại nguyên văn kết quả từ môi trường đang kiểm tra. Các dịch vụ cloud và bản phân phối tùy biến có thể bổ sung thông tin riêng.

### 2.2. Phân biệt phiên bản client và server

Ở terminal, lệnh sau hiển thị phiên bản client được cài trên máy đang chạy lệnh:

```bash
mysql --version

# Nếu cài MariaDB client:
mariadb --version
```

Lệnh trên **không** hỏi máy chủ từ xa về phiên bản của nó. Client MySQL có thể kết nối đến MariaDB hoặc một hệ tương thích giao thức MySQL; vì vậy kết quả `mysql --version` không chứng minh server cũng là MySQL.

Để ghi nhận môi trường ứng dụng, nên lưu riêng hai thông tin: phiên bản client/driver và phiên bản server lấy từ truy vấn SQL. Khi báo lỗi, hãy cung cấp cả hai cùng hệ điều hành, bản phân phối và cách triển khai (máy vật lý, VM, container hay dịch vụ cloud).

## 3. Kiểm tra storage engine được hỗ trợ

Storage engine là thành phần chịu trách nhiệm lưu trữ và truy xuất dữ liệu cho bảng. MySQL có kiến trúc cho phép các bảng khác nhau sử dụng engine khác nhau, tùy engine được cài đặt và hỗ trợ.

Chạy:

```sql
SHOW ENGINES;
```

Kết quả thường có các cột như `Engine`, `Support`, `Comment`, `Transactions`, `XA` và `Savepoints` (các cột có thể khác nhau theo phiên bản). Cột `Support` cho biết trạng thái hỗ trợ của engine:

| Giá trị thường gặp | Ý nghĩa |
|---|---|
| `DEFAULT` | Engine mặc định của server |
| `YES` | Engine có sẵn và được hỗ trợ |
| `NO` | Engine không được hỗ trợ trong bản server hiện tại |
| `DISABLED` | Engine có trong bản build nhưng đang bị vô hiệu hóa |

Không phải server nào cũng cung cấp cùng danh sách engine. InnoDB là engine giao dịch phổ biến và thường là mặc định trên MySQL hiện đại. MariaDB có thể cung cấp thêm các engine như Aria. MyISAM, MEMORY, CSV, ARCHIVE hoặc NDB chỉ xuất hiện và có khả năng sử dụng tùy bản phân phối, cấu hình và phiên bản.

Có thể tra cứu qua metadata:

```sql
SELECT
    ENGINE,
    SUPPORT,
    TRANSACTIONS,
    XA,
    SAVEPOINTS
FROM information_schema.ENGINES
ORDER BY ENGINE;
```

Nếu một engine không xuất hiện hoặc không có trạng thái hỗ trợ, đừng giả định có thể tạo bảng bằng engine đó. Hãy kiểm tra tài liệu đúng phiên bản và cấu hình server.

## 4. Kiểm tra engine mặc định và engine của từng bảng

### 4.1. Engine mặc định

Đọc engine được chọn làm mặc định cho các bảng mới:

```sql
SHOW GLOBAL VARIABLES LIKE 'default_storage_engine';
```

Hoặc:

```sql
SELECT @@GLOBAL.default_storage_engine;
```

Biến `default_storage_engine` ảnh hưởng đến việc tạo bảng mới khi câu lệnh `CREATE TABLE` không chỉ định `ENGINE`. Nó **không tự chuyển đổi** các bảng đã tồn tại. Vì vậy, engine mặc định hiện tại không đủ để kết luận toàn bộ database đang dùng engine nào.

### 4.2. Xem engine thực tế của bảng

Để liệt kê bảng trong database đang chọn:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

`TABLE_ROWS` có thể là giá trị ước lượng, đặc biệt với InnoDB; không nên dùng nó làm số đếm chính xác cho đối soát dữ liệu. `DATA_LENGTH` và `INDEX_LENGTH` thể hiện dung lượng theo cách engine báo cáo và có thể khác cách tính giữa các engine.

Muốn xem định nghĩa đầy đủ của một bảng, gồm engine, charset, collation, cột, index và constraint:

```sql
SHOW CREATE TABLE orders\G
```

Ký hiệu `\G` là cách hiển thị kết quả theo chiều dọc của MySQL client; nếu công cụ không hỗ trợ, dùng `SHOW CREATE TABLE orders;`.

### 4.3. Vì sao phải quan tâm engine?

| Engine | Đặc điểm chính | Lưu ý khi thiết kế |
|---|---|---|
| InnoDB | Hỗ trợ transaction, khóa dòng, foreign key và cơ chế phục hồi sau sự cố | Phù hợp với phần lớn ứng dụng OLTP cần tính toàn vẹn và cập nhật đồng thời |
| MyISAM | Engine cũ, không hỗ trợ transaction theo cách InnoDB cung cấp; dùng khóa bảng | Cần cân nhắc kỹ về tính toàn vẹn, ghi đồng thời và phục hồi |
| MEMORY | Lưu dữ liệu bảng trong bộ nhớ; dữ liệu bảng mất khi server dừng, cấu trúc bảng vẫn được định nghĩa | Chỉ phù hợp dữ liệu tạm có thể tái tạo; cần tính đến giới hạn bộ nhớ |
| CSV | Lưu dữ liệu theo định dạng CSV | Hữu ích cho một số trao đổi dữ liệu đơn giản; không có đầy đủ khả năng của engine giao dịch |
| ARCHIVE | Tối ưu cho lưu trữ dữ liệu theo kiểu nén và truy xuất phù hợp với engine | Kiểm tra giới hạn cập nhật, index và truy vấn theo phiên bản |
| Aria (MariaDB) | Engine riêng của MariaDB, có các chế độ và đặc điểm phục hồi riêng | Không mặc định xem là thay thế trực tiếp cho InnoDB trong workload giao dịch |

Không chọn engine chỉ dựa trên tên hoặc một phép đo tốc độ đơn lẻ. Hãy xét transaction, foreign key, loại khóa, khối lượng đọc/ghi, phục hồi sau crash, backup và khả năng vận hành.

## 5. Cách đọc biến cấu hình

### 5.1. Liệt kê và lọc biến

Xem tất cả biến global:

```sql
SHOW GLOBAL VARIABLES;
```

Lọc theo nhóm:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb%';
SHOW GLOBAL VARIABLES LIKE 'character_set%';
SHOW GLOBAL VARIABLES LIKE 'collation%';
SHOW GLOBAL VARIABLES LIKE 'log_%';
```

Xem một biến cụ thể:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
```

Có thể đọc một số biến trực tiếp bằng biểu thức `@@`:

```sql
SELECT
    @@GLOBAL.port AS server_port,
    @@GLOBAL.max_connections AS max_connections,
    @@GLOBAL.default_storage_engine AS default_engine,
    @@SESSION.sql_mode AS session_sql_mode;
```

Nếu biến không tồn tại ở phiên bản hoặc bản phân phối hiện tại, truy vấn có thể báo lỗi. Khi viết script kiểm tra dùng cho nhiều hệ, nên tra cứu biến theo từng nhóm hoặc xử lý biến tùy chọn thay vì giả định mọi server có cùng bộ biến.

### 5.2. Phân biệt GLOBAL và SESSION

Một biến có thể có phạm vi global, session hoặc cả hai, tùy biến và phiên bản:

- **GLOBAL** là giá trị áp dụng ở cấp server. Với biến có phạm vi session, giá trị global thường được dùng làm giá trị khởi tạo cho kết nối mới.
- **SESSION** là giá trị trong kết nối hiện tại. Một thay đổi session thường chỉ ảnh hưởng phiên đang mở và không tự thay đổi các kết nối khác.
- Một số biến chỉ đọc hoặc chỉ có một phạm vi; không thể suy luận rằng mọi biến đều thay đổi được ở cả hai cấp.

Ví dụ xem SQL mode của server và phiên hiện tại:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Ứng dụng dùng connection pool cần chú ý session state. Nếu một kết nối thay đổi `sql_mode`, `time_zone` hoặc isolation level, trạng thái đó có thể tồn tại khi connection được trả lại pool và được một request khác sử dụng, tùy cách pool quản lý reset kết nối.

### 5.3. Biến cấu hình khác với trạng thái hoạt động

`SHOW VARIABLES` trả về cấu hình hiện tại. `SHOW STATUS` trả về bộ đếm hoặc trạng thái hoạt động của server. Hai nhóm này trả lời các câu hỏi khác nhau.

```sql
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Questions';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
```

Ví dụ, `max_connections` là giới hạn cấu hình; `Threads_connected` cho biết số kết nối hiện tại tại thời điểm lấy mẫu. Để đánh giá có cần tăng giới hạn hay không, cần theo dõi xu hướng và mức đỉnh, không chỉ nhìn một lần chụp trạng thái.

## 6. Các nhóm biến quan trọng nên kiểm tra

Tên biến, giá trị mặc định và khả năng thay đổi có thể khác nhau giữa MySQL, MariaDB và các phiên bản. Các lệnh dưới đây là điểm bắt đầu để kiểm tra, không phải bộ cấu hình tối ưu áp dụng cho mọi máy chủ.

### 6.1. Nhận diện server và kết nối

```sql
SHOW GLOBAL VARIABLES LIKE 'port';
SHOW GLOBAL VARIABLES LIKE 'bind_address';
SHOW GLOBAL VARIABLES LIKE 'socket';
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'hostname';
SHOW GLOBAL VARIABLES LIKE 'server_id';
```

- `port`: cổng TCP server lắng nghe, thường là `3306` nếu không thay đổi.
- `bind_address`: địa chỉ mạng server dùng để lắng nghe; giá trị cụ thể ảnh hưởng khả năng truy cập từ máy khác.
- `socket`: đường dẫn socket trên hệ thống hỗ trợ Unix socket.
- `datadir`: thư mục dữ liệu của server.
- `hostname`: tên host mà server công bố.
- `server_id`: định danh server, có ý nghĩa trong các cấu hình replication dựa trên binary log.

Không công khai thông tin mạng, đường dẫn nội bộ hoặc cấu hình hạ tầng trong log chia sẻ rộng rãi nếu chúng là dữ liệu nhạy cảm của tổ chức.

### 6.2. Kết nối và giới hạn gói tin

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW GLOBAL VARIABLES LIKE 'connect_timeout';
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';
```

- `max_connections` giới hạn số kết nối đồng thời được server cho phép. Tăng quá cao có thể làm tăng áp lực bộ nhớ và tài nguyên hệ điều hành.
- `max_allowed_packet` giới hạn kích thước packet mà client/server có thể xử lý trong những ngữ cảnh liên quan; giá trị quá thấp có thể gây lỗi với payload lớn.
- `connect_timeout` liên quan thời gian chờ trong quá trình kết nối.
- `wait_timeout` và `interactive_timeout` kiểm soát thời gian chờ của các kết nối nhàn rỗi theo loại phiên.

Khi điều tra lỗi “too many connections”, cần đối chiếu giới hạn với số kết nối thực tế, số kết nối trong pool của từng ứng dụng, kết nối bị rò rỉ và thời gian giữ kết nối. Chỉ tăng `max_connections` mà không xem xét bộ nhớ có thể khiến server thiếu tài nguyên.

### 6.3. Bộ nhớ và InnoDB

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_instances';
SHOW GLOBAL VARIABLES LIKE 'innodb_log_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'innodb_file_per_table';
```

- `innodb_buffer_pool_size` là dung lượng buffer pool của InnoDB, dùng cache dữ liệu và index. Cần cân đối với RAM, các tiến trình khác và số kết nối.
- `innodb_buffer_pool_instances` có mặt và có ý nghĩa tùy phiên bản; một số phiên bản đã thay đổi hoặc loại bỏ cách cấu hình này.
- `innodb_log_buffer_size` điều khiển vùng đệm log của InnoDB.
- `innodb_flush_log_at_trx_commit` ảnh hưởng cách InnoDB flush log khi commit, từ đó tác động đến độ bền dữ liệu và hiệu năng.
- `innodb_file_per_table` liên quan cách tổ chức tablespace cho bảng InnoDB ở các phiên bản hỗ trợ biến này.

Không tự thay đổi các biến liên quan flush, log hoặc buffer pool chỉ dựa trên một bài viết tối ưu chung. Hãy xác định yêu cầu durability, dung lượng RAM, workload ghi và hướng dẫn của đúng phiên bản trước khi điều chỉnh.

### 6.4. Transaction và hành vi SQL

```sql
SHOW GLOBAL VARIABLES LIKE 'transaction_isolation';
SHOW GLOBAL VARIABLES LIKE 'tx_isolation';
SHOW GLOBAL VARIABLES LIKE 'autocommit';
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
```

Một số phiên bản dùng tên biến `transaction_isolation`, phiên bản cũ hoặc bản phân phối khác có thể cung cấp tên tương thích như `tx_isolation`. Hãy kiểm tra biến thực sự tồn tại.

- Isolation level quyết định mức cô lập giữa các transaction và ảnh hưởng hiện tượng đọc đồng thời.
- `autocommit` quyết định chế độ commit tự động mặc định cho phiên; ứng dụng vẫn có thể quản lý transaction tường minh.
- `sql_mode` bật các quy tắc kiểm tra và hành vi SQL như xử lý giá trị không hợp lệ, group by hoặc chế độ nghiêm ngặt. Khác biệt SQL mode có thể khiến cùng một câu lệnh hoạt động khác nhau.

Kiểm tra cả giá trị global lẫn session khi lỗi chỉ xuất hiện trong ứng dụng. Kết nối qua client quản trị có thể có session state khác với kết nối do framework hoặc connection pool tạo ra.

### 6.5. Charset, collation và múi giờ

```sql
SHOW GLOBAL VARIABLES LIKE 'character_set%';
SHOW GLOBAL VARIABLES LIKE 'collation%';
SHOW GLOBAL VARIABLES LIKE 'time_zone';
SHOW GLOBAL VARIABLES LIKE 'system_time_zone';
```

- `character_set_server` và `collation_server` là mặc định ở cấp server cho những đối tượng hoặc kết nối không chỉ định giá trị khác.
- `character_set_client`, `character_set_connection` và `character_set_results` liên quan cách client gửi, server xử lý và trả dữ liệu trong session.
- `time_zone` có thể có giá trị `SYSTEM` hoặc một múi giờ được cấu hình; `system_time_zone` mô tả múi giờ hệ thống mà server nhận diện.

Giá trị mặc định của server không chứng minh mọi bảng đều dùng cùng charset/collation. Hãy kiểm tra database và bảng bằng `information_schema.SCHEMATA`, `information_schema.TABLES`, `SHOW CREATE TABLE` khi điều tra lỗi tiếng Việt, so sánh chuỗi hoặc chuyển dữ liệu. Ứng dụng nên xác định múi giờ rõ ràng để tránh lệch thời gian giữa các môi trường.

### 6.6. Log và giám sát truy vấn chậm

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error';
SHOW GLOBAL VARIABLES LIKE 'general_log';
SHOW GLOBAL VARIABLES LIKE 'general_log_file';
SHOW GLOBAL VARIABLES LIKE 'slow_query_log';
SHOW GLOBAL VARIABLES LIKE 'slow_query_log_file';
SHOW GLOBAL VARIABLES LIKE 'long_query_time';
```

- Error log ghi nhận sự kiện và lỗi server.
- General query log có thể ghi các kết nối và câu lệnh, nhưng bật liên tục có thể tạo lượng I/O và dữ liệu log lớn.
- Slow query log ghi các truy vấn thỏa điều kiện chậm theo cấu hình, hỗ trợ tìm truy vấn cần tối ưu.
- `long_query_time` là ngưỡng thời gian liên quan việc ghi nhận truy vấn chậm.

Khi bật log để điều tra, cần cân nhắc dung lượng đĩa, quyền truy cập, vòng đời lưu trữ và dữ liệu nhạy cảm có thể xuất hiện trong câu SQL. Ưu tiên quy trình giám sát có kiểm soát và tắt hoặc xoay vòng log theo chính sách vận hành.

### 6.7. Binary log và replication

```sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW GLOBAL VARIABLES LIKE 'expire_logs_days';
SHOW GLOBAL VARIABLES LIKE 'read_only';
SHOW GLOBAL VARIABLES LIKE 'super_read_only';
```

Các biến này có thể khác tên hoặc khác mức hỗ trợ theo phiên bản và bản phân phối:

- `log_bin` cho biết binary logging có được bật hay không.
- `binlog_format` mô tả định dạng ghi sự kiện binary log trong những phiên bản hỗ trợ.
- Các biến hết hạn log kiểm soát thời gian lưu binary log; tên biến thay đổi giữa một số thế hệ phiên bản.
- `read_only` và `super_read_only` liên quan hạn chế ghi trên server, thường được dùng trong vai trò replica hoặc khi bảo trì. Quy tắc ngoại lệ và quyền có thể khác nhau theo phiên bản.

Không xóa binary log thủ công khỏi thư mục dữ liệu. Việc dọn log phải theo cơ chế SQL và chính sách replication/backup để tránh làm replica mất dữ liệu cần đọc hoặc phá vỡ khả năng phục hồi theo thời điểm.

## 7. Một quy trình kiểm tra môi trường có thể lặp lại

Khi nhận một môi trường MySQL mới hoặc chuẩn bị điều tra sự cố, thực hiện theo trình tự sau:

1. **Xác định server:** lấy `VERSION()`, `@@version_comment`, hệ điều hành và kiến trúc nếu có.
2. **Xác định kết nối:** ghi nhận port, bind address, socket và các giới hạn kết nối cần thiết.
3. **Kiểm tra engine:** chạy `SHOW ENGINES`, xem `default_storage_engine`, sau đó liệt kê engine thực tế của các bảng quan trọng.
4. **Kiểm tra hành vi phiên:** lấy SQL mode, isolation level, autocommit, charset, collation và time zone ở cả global/session khi cần.
5. **Kiểm tra tài nguyên:** ghi nhận giới hạn kết nối, packet, buffer pool và các biến bộ nhớ phù hợp với phiên bản.
6. **Kiểm tra vận hành:** xem error log, slow query log, binary log, read-only và các chỉ số trạng thái liên quan.
7. **Lưu kết quả có ngữ cảnh:** kèm thời điểm lấy mẫu, endpoint/môi trường, phiên bản client/driver và quyền của tài khoản kiểm tra.

Một bộ truy vấn khởi đầu gọn có thể là:

```sql
-- 1. Phiên bản server
SELECT VERSION() AS server_version,
       @@version_comment AS distribution;

-- 2. Engine được hỗ trợ
SHOW ENGINES;

-- 3. Engine mặc định
SHOW GLOBAL VARIABLES LIKE 'default_storage_engine';

-- 4. Engine của các bảng trong database hiện tại
SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

-- 5. Các biến thường cần đối chiếu
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';
SHOW GLOBAL VARIABLES LIKE 'time_zone';

-- 6. Một số trạng thái tại thời điểm kiểm tra
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
```

Đây là bộ kiểm tra ban đầu, không phải báo cáo cấu hình đầy đủ. Nếu một biến không được hỗ trợ, ghi nhận điều đó và kiểm tra tài liệu của server đang dùng; không thay bằng một giá trị phỏng đoán.

## 8. Đọc kết quả và tránh những kết luận sai

| Quan sát | Kết luận có thể rút ra | Điều chưa thể kết luận |
|---|---|---|
| `VERSION()` trả về chuỗi phiên bản MySQL | Server tự công bố phiên bản MySQL tương ứng | Chưa biết edition, mọi tính năng được bật hay cấu hình workload |
| `SHOW ENGINES` đánh dấu InnoDB là `DEFAULT` | InnoDB là engine mặc định cho bảng mới khi không chỉ định engine | Chưa biết tất cả bảng hiện tại đều dùng InnoDB |
| `max_connections = 300` | Giới hạn cấu hình là 300 kết nối theo phạm vi biến đó | Chưa biết server có đủ RAM hoặc ứng dụng cần 300 kết nối |
| `Threads_connected = 120` | Có 120 kết nối tại thời điểm đọc trạng thái | Chưa biết đây là mức đỉnh hay có rò rỉ kết nối |
| `slow_query_log = ON` | Slow query log đang bật theo biến được đọc | Chưa biết file log còn đủ dung lượng hoặc đã được phân tích |
| `read_only = ON` | Server đang bật chế độ read-only theo biến đó | Chưa thể suy ra toàn bộ thao tác ghi đều bị chặn trong mọi phiên bản và với mọi quyền |

Đặc biệt, không đồng nhất giá trị cấu hình với tình trạng thực tế. Ví dụ, buffer pool lớn không tự chứng minh hiệu năng tốt; cần xem workload, hit rate, I/O và độ trễ. Slow query log bật không có nghĩa mọi truy vấn chậm đã được ghi nếu còn các ngưỡng hoặc bộ lọc khác.

## 9. An toàn khi thu thập và thay đổi cấu hình

Các lệnh `SHOW` và `SELECT` trong bài chủ yếu phục vụ kiểm tra. Việc thay đổi biến là thao tác quản trị riêng, có thể cần quyền cao và ảnh hưởng tất cả ứng dụng đang kết nối.

Trước khi thay đổi một biến, hãy xác minh:

- Biến có tồn tại và được hỗ trợ ở đúng phiên bản không?
- Biến có phạm vi GLOBAL, SESSION hay cả hai; có phải biến động (dynamic) không?
- Giá trị mới có ảnh hưởng kết nối đang hoạt động, transaction, durability hoặc replication không?
- Thay đổi chỉ tồn tại trong runtime hay được lưu để áp dụng sau khi restart? Cơ chế lưu cấu hình khác nhau giữa phiên bản và bản phân phối.
- Có baseline, cửa sổ bảo trì, cách rollback và giám sát sau thay đổi không?

Ví dụ, `SET GLOBAL max_connections = 300;` có thể thay đổi giá trị runtime nếu biến cho phép và tài khoản có quyền phù hợp. Câu lệnh này không nên được chạy như một bước thử nghiệm tùy tiện trên production; cách lưu bền qua restart phải theo cơ chế cấu hình được hỗ trợ bởi server cụ thể.

Khi chia sẻ kết quả kiểm tra, hãy loại bỏ mật khẩu, token, chuỗi kết nối chứa thông tin đăng nhập và dữ liệu nghiệp vụ. Một số biến có thể để lộ hostname, địa chỉ mạng, đường dẫn thư mục hoặc tên file nội bộ; chỉ chia sẻ với đúng người có quyền truy cập.

## 10. Kết luận

Kiểm tra phiên bản cho biết bạn đang làm việc với server nào; kiểm tra `SHOW ENGINES` và metadata bảng cho biết khả năng lưu trữ cũng như engine đang dùng; kiểm tra biến cấu hình giúp hiểu giới hạn kết nối, bộ nhớ, transaction, charset, log và replication.

Hãy đọc cấu hình cùng trạng thái hoạt động và metadata thực tế của bảng. Luôn ghi rõ phiên bản, phạm vi GLOBAL/SESSION và thời điểm lấy mẫu để tránh so sánh sai giữa các môi trường. Đây là bước nền tảng trước khi thiết kế schema, tối ưu truy vấn hoặc thay đổi cấu hình MySQL trong vận hành.
