# Data dictionary, metadata cache và table definition cache

MySQL phải biết cấu trúc của database trước khi có thể phân tích và thực thi câu lệnh SQL. Khi nhận một truy vấn như `SELECT order_id, total FROM sales.orders`, server cần xác định schema `sales`, bảng `orders`, các cột, kiểu dữ liệu, index, quyền truy cập và storage engine. Những thông tin mô tả đối tượng này là **metadata**.

Đọc metadata từ nơi lưu trữ liên tục cho mọi câu lệnh sẽ tốn thời gian. Vì vậy MySQL tổ chức metadata thành data dictionary và giữ các đối tượng thường dùng trong nhiều lớp cache bộ nhớ. Hiểu đúng từng lớp giúp bạn điều tra việc mở bảng chậm, hệ thống có nhiều bảng, tải đồng thời cao hoặc DDL bị chờ.

Bài học đặt nội dung trong phạm vi `DATABASE_MYSQL`: làm chủ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn, index, transaction, kiểm soát đồng thời và vận hành. Data dictionary cùng các cache liên quan là một phần của kiến trúc server, ảnh hưởng đến cách MySQL phân giải tên đối tượng, mở bảng và xử lý DDL.

## 1. Metadata và data dictionary là gì?

**Metadata** là dữ liệu mô tả dữ liệu. Với MySQL, metadata mô tả các đối tượng và thuộc tính mà server cần để hiểu và quản lý database, ví dụ:

- Schema và bảng.
- Cột, kiểu dữ liệu, giá trị mặc định, thuộc tính NULL và thứ tự cột.
- Primary key, unique key, foreign key và index.
- View và định nghĩa view.
- Stored procedure, function, trigger và event.
- Tablespace, partition và các thuộc tính lưu trữ.
- Thông tin cần thiết để kiểm tra quyền và thực thi câu lệnh trên đối tượng.

Metadata khác với dữ liệu nghiệp vụ trong các hàng của bảng. Ví dụ, trong bảng `sales.orders`, các hàng chứa đơn hàng là dữ liệu nghiệp vụ; định nghĩa `order_id BIGINT PRIMARY KEY`, kiểu của `total`, index và engine là metadata.

**Data dictionary** là thành phần quản lý tập trung metadata của các đối tượng database. Nó cho phép server tra cứu định nghĩa đối tượng một cách nhất quán thay vì phải dựa vào nhiều nguồn metadata rời rạc.

Có thể hình dung luồng xử lý khái quát như sau:

~~~text
Câu lệnh SQL
    |
    v
Phân tích cú pháp và phân giải tên đối tượng
    |
    v
Tra cứu metadata / data dictionary
    |
    +--> Các đối tượng metadata đang có trong cache
    |
    +--> Đọc metadata từ data dictionary khi cần
    |
    v
Kiểm tra quyền, chuẩn bị đối tượng bảng và thực thi
    |
    v
Storage engine xử lý dữ liệu
~~~

Đây là sơ đồ khái niệm. Việc tra cứu dictionary, cache và mở bảng có nhiều bước nội bộ hơn, có thể khác theo loại câu lệnh và phiên bản MySQL.

## 2. Data dictionary trong MySQL 8.0 trở lên

### 2.1. Data dictionary dạng giao dịch

Từ MySQL 8.0, MySQL sử dụng transactional data dictionary. Metadata được lưu trữ tập trung trong các bảng dictionary do server quản lý, sử dụng InnoDB. Việc lưu trữ này có các lợi ích quan trọng:

- Metadata được quản lý tập trung và nhất quán.
- Các thay đổi dictionary có tính giao dịch và khả năng phục hồi sau sự cố.
- Một số thao tác DDL có hỗ trợ atomic DDL, giúp thay đổi metadata và thao tác storage liên quan được phục hồi như một đơn vị theo phạm vi được hỗ trợ.
- Cơ chế cache metadata được tổ chức tập trung hơn.
- Nhiều truy vấn metadata qua `INFORMATION_SCHEMA` có thể sử dụng dictionary thay vì quét các file định nghĩa rời rạc.

Ở các phiên bản MySQL cũ, metadata bảng từng được lưu trong các file như `.frm` và một số nguồn khác. Khi nâng cấp lên MySQL 8.0, không nên tiếp tục giả định file `.frm` là nguồn định nghĩa bảng. Hãy dùng giao diện SQL được hỗ trợ để xem metadata.

### 2.2. Dictionary table không phải bảng ứng dụng thông thường

MySQL có các bảng nội bộ để lưu data dictionary, nhưng các bảng dictionary được bảo vệ và không được truy vấn hoặc chỉnh sửa trực tiếp trong bản build thông thường. Để đọc metadata, sử dụng các giao diện được hỗ trợ:

- Lệnh `SHOW`, ví dụ `SHOW CREATE TABLE`, `SHOW COLUMNS`, `SHOW INDEX`.
- Các view và bảng trong `INFORMATION_SCHEMA`.
- Những bảng giám sát trong `performance_schema`.
- Các view tiện ích trong `sys` schema.

Không sửa trực tiếp các bảng dictionary hoặc can thiệp vào file dữ liệu nội bộ để đổi định nghĩa bảng. Làm vậy có thể khiến metadata và trạng thái storage engine không nhất quán, thậm chí làm instance không thể hoạt động.

Cũng cần phân biệt **data dictionary tables** với **system tables** trong schema `mysql`. Dictionary tables chứa metadata cốt lõi mà server cần để thực thi câu lệnh; system tables thông thường lưu thông tin hỗ trợ như tài khoản, quyền, múi giờ và dữ liệu hệ thống khác. Cả hai đều do MySQL quản lý, nhưng có vai trò và quy trình nâng cấp khác nhau.

### 2.3. Atomic DDL không có nghĩa mọi DDL đều rollback được

Transactional data dictionary giúp MySQL hỗ trợ atomic DDL cho các thao tác và storage engine thuộc phạm vi hỗ trợ. Điều này có nghĩa server có thể phục hồi thao tác DDL theo cách nhất quán khi xảy ra lỗi hoặc crash.

Tuy nhiên, không nên hiểu atomic DDL là có thể đặt mọi lệnh `CREATE`, `ALTER`, `DROP` vào transaction của người dùng rồi dùng `ROLLBACK` để hoàn tác. Nhiều câu lệnh DDL vẫn gây implicit commit. Atomic DDL là cơ chế đảm bảo tính nguyên tử ở cấp server cho thao tác DDL được hỗ trợ, không thay thế quy tắc transaction SQL của ứng dụng.

## 3. Những lớp cache metadata cần phân biệt

Từ “metadata cache” thường được dùng như một tên gọi chung. Trong MySQL có nhiều cache liên quan tới metadata nhưng chúng không phải một cấu trúc duy nhất.

| Thành phần | Nội dung chính | Cấu hình/quan sát |
|---|---|---|
| Dictionary Object Cache | Đối tượng data dictionary đã được truy cập, giữ trong bộ nhớ dùng chung | Các partition dictionary; một số giới hạn có biến cấu hình riêng |
| Table definition cache | Định nghĩa bảng được server cache để giảm chi phí mở/tra cứu định nghĩa | `table_definition_cache`, `Open_table_definitions`, `Opened_table_definitions` |
| Table open cache | Các table instance đang mở, phục vụ truy cập đồng thời từ session | `table_open_cache`, `table_open_cache_instances`, `Open_tables`, `Opened_tables` |
| INFORMATION_SCHEMA statistics cache | Một số thống kê bảng và index được cache để truy vấn metadata nhanh hơn | `information_schema_stats_expiry`, `ANALYZE TABLE` |
| Metadata lock (MDL) | Khóa phối hợp truy cập metadata giữa các session | `performance_schema.metadata_locks` |

Bốn cache đầu liên quan đến việc lưu giữ hoặc tái sử dụng thông tin/đối tượng trong bộ nhớ. Metadata lock là cơ chế đồng bộ và bảo vệ tính nhất quán, **không phải cache**.

### 3.1. Dictionary Object Cache

Dictionary Object Cache là cache toàn cục dùng chung, lưu các đối tượng data dictionary đã được truy cập để có thể tái sử dụng và giảm I/O. Cache sử dụng chiến lược LRU (Least Recently Used): khi cần giải phóng chỗ, các đối tượng ít được sử dụng gần đây sẽ được ưu tiên loại bỏ.

Trong MySQL 8.4, Dictionary Object Cache được chia thành các partition theo loại đối tượng. Một số partition có biến cấu hình, một số có giới hạn nội bộ. Ví dụ:

- Tablespace definition cache partition: giới hạn bởi `tablespace_definition_cache`.
- Schema definition cache partition: giới hạn bởi `schema_definition_cache`.
- Table definition cache partition bên trong Dictionary Object Cache: giới hạn đối tượng gắn với `max_connections`.
- Stored program definition cache partition: liên quan đến `stored_program_definition_cache`.
- Character set và collation definition cache partition: có giới hạn nội bộ.

Điểm dễ nhầm: table definition cache partition bên trong Dictionary Object Cache **tồn tại song song** với table definition cache được điều khiển bởi biến `table_definition_cache`. Hai cache đều lưu table definition nhưng phục vụ các phần khác nhau của server; sự tồn tại của một đối tượng trong cache này không phụ thuộc vào việc đối tượng có nằm trong cache kia hay không.

Không nên gom tất cả các lớp trên thành một con số “metadata cache size”. Khi phân tích bộ nhớ hoặc thay đổi cấu hình, cần biết biến đang điều khiển partition nào.

## 4. Table definition cache

### 4.1. Vai trò

Table definition cache giữ định nghĩa bảng để server có thể tái sử dụng khi mở hoặc truy cập bảng. Định nghĩa này chứa thông tin cấu trúc như cột, kiểu dữ liệu và các thuộc tính liên quan đến bảng.

Khi ứng dụng thường xuyên truy cập một tập lớn bảng, cache định nghĩa đủ lớn có thể giảm việc phải nạp lại định nghĩa từ data dictionary. Cache này thường cần ít bộ nhớ hơn table open cache và không sử dụng file descriptor như cache các bảng đang mở.

Biến cấu hình chính là:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
~~~

Trong MySQL 8.4, biến này có phạm vi GLOBAL, có thể thay đổi động, giá trị tối thiểu là 400 và giá trị mặc định `-1` biểu thị tự động tính toán. Công thức mặc định được tài liệu MySQL 8.4 mô tả là:

~~~text
MIN(400 + table_open_cache / 2, 2000)
~~~

Không nên áp dụng mặc định này cho mọi phiên bản MySQL. Hãy đọc giá trị thực trên instance và tài liệu đúng phiên bản.

### 4.2. Tương tác với InnoDB

Với InnoDB, `table_definition_cache` còn hoạt động như một giới hạn mềm đối với số table instance trong Dictionary Object Cache và số file-per-table tablespace có thể được mở cùng lúc. Khi vượt giới hạn, MySQL đánh dấu các đối tượng phù hợp để loại bỏ theo LRU và chỉ đóng tablespace không còn hoạt động khi đủ điều kiện.

Đây là lý do không nên diễn giải `table_definition_cache` đơn giản là “số file .frm được lưu trong RAM”. Từ MySQL 8.0, data dictionary không còn dựa trên file `.frm` theo mô hình cũ; biến này tác động đến cache định nghĩa và một số giới hạn liên quan đến InnoDB.

### 4.3. Quan sát cache định nghĩa

Hai status variable hữu ích:

- `Open_table_definitions`: số định nghĩa bảng hiện đang được cache.
- `Opened_table_definitions`: số thao tác định nghĩa bảng đã được cache kể từ khi server khởi động hoặc bộ đếm được reset theo cơ chế tương ứng.

Có thể xem nhanh:

~~~sql
SHOW GLOBAL STATUS LIKE 'Open_table_definitions';
SHOW GLOBAL STATUS LIKE 'Opened_table_definitions';
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
~~~

Đọc các giá trị theo thời gian và cùng workload. Không tăng cache chỉ vì `Opened_table_definitions` lớn: đây là bộ đếm tích lũy, không tự nó chứng minh cache thiếu. Cần xem số lượng bảng, mức tái sử dụng bảng, áp lực bộ nhớ và các chỉ số khác.

## 5. Table open cache

### 5.1. Vai trò

Table open cache giữ các table instance đang mở để các thread có thể sử dụng lại, giảm chi phí mở bảng lặp lại. Một bảng được nhiều session truy cập đồng thời có thể cần nhiều table instance vì trạng thái làm việc của các session khác nhau.

Biến `table_open_cache` quy định số lượng mục trong cache bảng mở cho toàn bộ các thread. Đây không phải số bảng trong database và cũng không phải số bảng mà một session được phép truy cập.

Ví dụ: một ứng dụng có 300 session hoạt động, các truy vấn thường join 4 đến 6 bảng. Số lượng table instance cần giữ có thể lớn hơn nhiều so với số bảng mà một truy vấn đơn lẻ tham chiếu. Cấu hình cache phải được đánh giá theo mức đồng thời, mẫu truy vấn và giới hạn file descriptor.

### 5.2. Cấu hình và giới hạn

Xem các biến liên quan:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'table_open_cache',
    'table_open_cache_instances',
    'table_definition_cache',
    'max_connections',
    'open_files_limit'
);
~~~

Trong MySQL 8.4, tài liệu mô tả các giá trị mặc định phổ biến:

| Biến | Giá trị mặc định MySQL 8.4 | Ý nghĩa |
|---|---:|---|
| `table_open_cache` | 4000 | Số mục table open cache cho tất cả thread |
| `table_open_cache_instances` | 16 | Số cache instance được phân vùng |
| `table_definition_cache` | -1 (tự tính) | Số table definition được lưu trong cache cấu hình |

Đây là giá trị mặc định tham khảo của MySQL 8.4, không phải cấu hình khuyến nghị cho mọi máy chủ. Dịch vụ cloud, bản phân phối khác hoặc file cấu hình có thể đặt giá trị khác.

Tăng `table_open_cache` làm tăng số file descriptor mà mysqld cần. Giá trị hiệu lực còn bị ràng buộc bởi `open_files_limit` và `max_connections`. Nếu đặt quá cao so với giới hạn hệ điều hành, server có thể gặp lỗi mở file, từ chối kết nối hoặc không thực thi được truy vấn.

### 5.3. Table open cache instances

`table_open_cache_instances` chia table open cache thành nhiều cache nhỏ để giảm tranh chấp khi nhiều session cùng truy cập cache. Một session có thể khóa một cache instance khi thao tác DML thay vì cùng tranh chấp một cache lớn.

Trong MySQL 8.4, giá trị mặc định là 16 và biến này không thể thay đổi động. DDL vẫn cần khóa toàn bộ cache, dù DDL thường ít xảy ra hơn DML. Việc tăng số instance không tự động cải thiện hiệu năng; nhiều cache instance cũng có thể làm tăng mức sử dụng bộ nhớ trong một số workload.

## 6. Phân biệt table definition cache và table open cache

Đây là hai khái niệm thường bị nhầm:

| Tiêu chí | Table definition cache | Table open cache |
|---|---|---|
| Biến cấu hình | `table_definition_cache` | `table_open_cache` |
| Giữ gì | Định nghĩa/metadata của bảng | Table instance đang mở để session sử dụng |
| Mục tiêu | Giảm chi phí nạp lại định nghĩa bảng | Giảm thao tác mở/đóng bảng và hỗ trợ truy cập đồng thời |
| File descriptor | Không dùng file descriptor theo cách table open cache sử dụng | Có ảnh hưởng đến số file descriptor cần thiết |
| Chỉ số quan sát | `Open_table_definitions`, `Opened_table_definitions` | `Open_tables`, `Opened_tables`, `Table_open_cache_*` |
| Vấn đề thường gặp | Nhiều bảng, định nghĩa bị nạp lại thường xuyên | Cache mở bảng quá nhỏ, file descriptor hoặc áp lực đồng thời |

Ví dụ:

- Nếu server có hàng chục nghìn bảng nhưng tại một thời điểm chỉ có một phần nhỏ được truy cập, table definition cache có thể cần đủ lớn để tái sử dụng metadata.
- Nếu server có nhiều session cùng mở các bảng và thường xuyên join nhiều bảng, table open cache có thể cần điều chỉnh để tránh mở/đóng bảng liên tục.
- Nếu hệ thống thiếu file descriptor, tăng `table_open_cache` có thể làm tình hình xấu hơn dù mục tiêu ban đầu là giảm thao tác mở bảng.

Vì hai cache có mục đích khác nhau, không nên chỉ tăng cả hai cùng lúc. Hãy đo và xác định lớp nào đang gây chi phí.

## 7. Cache thống kê của INFORMATION_SCHEMA

Một lớp cache khác dễ bị nhầm với data dictionary là cache thống kê bảng và index được truy vấn qua `INFORMATION_SCHEMA`.

Trong MySQL 8.4, một số giá trị thống kê trong các bảng `INFORMATION_SCHEMA.TABLES` và `INFORMATION_SCHEMA.STATISTICS` được cache. Biến `information_schema_stats_expiry` xác định thời gian cache thống kê hết hạn; mặc định của MySQL 8.4 là 86400 giây (24 giờ).

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'information_schema_stats_expiry';
~~~

Khi cần lấy thống kê mới từ storage engine, có thể chạy:

~~~sql
ANALYZE TABLE sales.orders;
~~~

Hoặc đặt `information_schema_stats_expiry = 0` cho session cần đọc thống kê mới trực tiếp từ storage engine:

~~~sql
SET SESSION information_schema_stats_expiry = 0;
~~~

Đổi lại, truy vấn metadata có thể chậm hơn vì không sử dụng giá trị thống kê được cache. Chỉ nên dùng khi có lý do cần số liệu mới nhất; không nên mặc định đặt bằng 0 cho mọi session.

Cần nhớ: cache thống kê không phải cache định nghĩa bảng. Nếu số liệu `TABLE_ROWS` hoặc cardinality chưa cập nhật, điều đó không có nghĩa data dictionary hoặc table definition cache đang lỗi.

## 8. Đọc metadata qua giao diện SQL

Data dictionary có thể được tra cứu thông qua các giao diện được hỗ trợ. Các truy vấn sau hữu ích khi điều tra schema và xác minh định nghĩa bảng.

### 8.1. Liệt kê bảng trong một schema

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    CREATE_OPTIONS
FROM information_schema.tables
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
~~~

Với InnoDB, `TABLE_ROWS` thường là ước lượng, không phải số dòng chính xác. Nếu cần đếm chính xác, chạy `SELECT COUNT(*)` trên bảng và cân nhắc chi phí đọc dữ liệu.

### 8.2. Đọc định nghĩa cột

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Truy vấn cho biết thứ tự cột, kiểu dữ liệu, thuộc tính NULL, default và thuộc tính bổ sung như auto increment.

### 8.3. Đọc index

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

`CARDINALITY` là thống kê ước lượng về số giá trị khác nhau của index; không nên coi đó là số liệu chính xác tuyệt đối. Khi cần cập nhật thống kê, đánh giá `ANALYZE TABLE` và thời gian cache thống kê.

### 8.4. Xem định nghĩa đầy đủ

~~~sql
SHOW CREATE TABLE sales.orders\G
~~~

Lệnh này thường là cách nhanh nhất để xem đầy đủ DDL của một bảng, gồm cột, index, constraint, engine, charset và các tùy chọn liên quan.

### 8.5. Liệt kê database và schema

~~~sql
SELECT SCHEMA_NAME
FROM information_schema.schemata
ORDER BY SCHEMA_NAME;
~~~

Các truy vấn trên chỉ hiển thị đối tượng mà tài khoản hiện tại được phép nhìn thấy theo quyền và chính sách server.

## 9. Metadata locking: khóa metadata không phải cache

Metadata locking (MDL) điều phối truy cập đồng thời tới các đối tượng như bảng, schema, stored procedure, function, trigger, event và tablespace. Mục tiêu là đảm bảo câu lệnh không sử dụng định nghĩa đối tượng trong khi một thao tác khác đang thay đổi định nghĩa đó theo cách xung đột.

Ví dụ:

1. Session A bắt đầu transaction và đọc bảng `sales.orders`.
2. Transaction của Session A còn mở nên vẫn giữ metadata lock phù hợp với đối tượng.
3. Session B chạy `ALTER TABLE sales.orders ...` và phải chờ metadata lock tương thích.
4. Nếu transaction của Session A không kết thúc, DDL của Session B có thể chờ lâu.
5. Một số truy vấn khác có thể bị ảnh hưởng bởi hàng đợi lock đang chờ DDL.

MDL khác với row lock của InnoDB:

- Row lock bảo vệ các bản ghi dữ liệu trong transaction.
- Metadata lock bảo vệ định nghĩa và trạng thái metadata của đối tượng.
- Cache giữ lại thông tin/đối tượng trong bộ nhớ để tái sử dụng.

Tăng `table_definition_cache` hoặc `table_open_cache` không giải quyết được transaction giữ metadata lock quá lâu.

### 9.1. Kiểm tra metadata lock đang chờ

Performance Schema cung cấp bảng `performance_schema.metadata_locks`. Có thể lọc các yêu cầu lock đang chờ:

~~~sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS = 'PENDING'
ORDER BY OBJECT_SCHEMA, OBJECT_NAME;
~~~

Kết quả có thể rỗng nếu không có lock đang chờ tại thời điểm truy vấn. Để xác định session liên quan, nối `OWNER_THREAD_ID` với `performance_schema.threads`:

~~~sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    t.PROCESSLIST_ID,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    t.PROCESSLIST_TIME,
    t.PROCESSLIST_STATE,
    t.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
    ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS IN ('PENDING', 'GRANTED')
ORDER BY ml.OBJECT_SCHEMA, ml.OBJECT_NAME, ml.LOCK_STATUS;
~~~

Cần quyền đọc Performance Schema phù hợp. Kết quả là ảnh chụp tại thời điểm truy vấn; trạng thái lock có thể thay đổi ngay sau đó.

### 9.2. Cách xử lý DDL bị chờ

Khi `ALTER TABLE` hoặc `DROP TABLE` bị chờ metadata lock:

1. Xác định đối tượng và session đang chờ trong `metadata_locks`.
2. Tìm session đang giữ lock và kiểm tra transaction có còn mở không.
3. Xem câu lệnh và thời gian chạy trong process list hoặc Performance Schema.
4. Xác định transaction có thể commit/rollback theo nghiệp vụ hay không.
5. Nếu cần hủy session, đánh giá ảnh hưởng trước khi dùng `KILL`.
6. Lập lịch DDL trong thời gian phù hợp và kiểm soát thời gian chờ bằng cấu hình/chiến lược migration thích hợp.

Không nên tự động kill mọi session có thời gian chạy dài. Một transaction có thể đang xử lý công việc hợp lệ; cần xác định chủ sở hữu và tác động trước khi can thiệp.

## 10. Theo dõi cache và đánh giá có cần điều chỉnh không

### 10.1. Lấy snapshot cấu hình

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'table_definition_cache',
    'table_open_cache',
    'table_open_cache_instances',
    'max_connections',
    'open_files_limit',
    'information_schema_stats_expiry'
);
~~~

Lưu kết quả cùng thời gian lấy mẫu, phiên bản server và loại workload. Với dịch vụ managed database, một số biến có thể không được phép thay đổi hoặc cần cấu hình qua parameter group.

### 10.2. Lấy snapshot status

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_table_definitions',
    'Opened_table_definitions',
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files'
);
~~~

Ý nghĩa:

| Chỉ số | Cách đọc |
|---|---|
| `Open_table_definitions` | Số định nghĩa bảng hiện đang được cache |
| `Opened_table_definitions` | Số lần server mở/nạp định nghĩa bảng theo bộ đếm |
| `Open_tables` | Số bảng hiện đang mở |
| `Opened_tables` | Số thao tác mở bảng kể từ lúc server khởi động hoặc reset bộ đếm |
| `Table_open_cache_hits` | Số lần tìm thấy mục trong table open cache |
| `Table_open_cache_misses` | Số lần không tìm thấy mục trong table open cache |
| `Table_open_cache_overflows` | Số lần cache instance bị overflow theo định nghĩa của server |
| `Open_files` | Số file đang mở mà server theo dõi |

### 10.3. Đọc số liệu theo khoảng thời gian

Một snapshot đơn lẻ thường không đủ để kết luận cache đang thiếu. Hãy lấy hai hoặc nhiều snapshot trong khoảng thời gian workload đại diện đang chạy và so sánh mức tăng:

- `Opened_tables` tăng nhanh trong khi ứng dụng không thường xuyên chạy `FLUSH TABLES` có thể là dấu hiệu table open cache chưa đủ.
- `Table_open_cache_misses` và `Table_open_cache_overflows` tăng trong giờ cao điểm cần được xem cùng `hits`, số session đồng thời và số bảng được truy cập.
- `Open_files` tiến gần giới hạn file descriptor là tín hiệu cần thận trọng trước khi tăng table open cache.
- `Opened_table_definitions` tăng nhanh cần được xem cùng `Open_table_definitions`, số lượng bảng và workload; không dùng một bộ đếm tích lũy để kết luận cache definition thiếu.

Nếu muốn tính tỷ lệ miss cho một khoảng lấy mẫu, dùng delta giữa hai lần đo:

~~~text
miss_rate = delta(Table_open_cache_misses)
            / (delta(Table_open_cache_hits)
               + delta(Table_open_cache_misses))
~~~

Tỷ lệ này chỉ có ý nghĩa khi mẫu số lớn hơn 0 và các bộ đếm được lấy trong cùng khoảng thời gian. Tỷ lệ miss cao là tín hiệu để điều tra, không phải bằng chứng duy nhất rằng cần tăng cache. Một workload truy cập hàng triệu bảng khác nhau có thể có tỷ lệ miss cao nhưng không nhất thiết cải thiện được bằng cách cấp thêm bộ nhớ.

### 10.4. Quy trình tuning có kiểm soát

1. Ghi lại phiên bản MySQL, cấu hình cache, số bảng, `max_connections` và `open_files_limit`.
2. Lấy baseline dưới workload thực tế: cache hits/misses, số bảng mở, số lần mở bảng và độ trễ truy vấn.
3. Xác định vấn đề thuộc table definition cache, table open cache, file descriptor hay metadata lock.
4. Thay đổi một tham số tại một thời điểm trên môi trường thử nghiệm hoặc theo quy trình cấu hình production.
5. Đo lại cùng workload và cùng khoảng thời gian.
6. So sánh độ trễ, thông lượng, bộ nhớ, file descriptor và các chỉ số cache.
7. Giữ thay đổi nếu có lợi ích đo được và tài nguyên vẫn trong giới hạn; nếu không, khôi phục cấu hình cũ.

Đừng tăng cache vô hạn. Cache lớn tiêu thụ tài nguyên và có thể làm server thiếu file descriptor hoặc bộ nhớ cho workload quan trọng hơn.

## 11. Ví dụ điều tra: server có nhiều bảng và mở bảng liên tục

Giả sử một hệ thống multi-tenant có 12.000 bảng, mỗi tenant có các bảng riêng. Trong giờ cao điểm, nhiều session chạy truy vấn trên các tenant khác nhau. Server có độ trễ tăng và bộ đếm `Opened_tables` tăng nhanh.

Không nên lập tức tăng cả `table_definition_cache` và `table_open_cache`. Thực hiện theo thứ tự:

**Bước 1: Xác định cấu hình**

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'table_definition_cache',
    'table_open_cache',
    'table_open_cache_instances',
    'max_connections',
    'open_files_limit'
);
~~~

**Bước 2: Lấy số liệu cache**

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_table_definitions',
    'Opened_table_definitions',
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files'
);
~~~

**Bước 3: Phân loại dấu hiệu**

- Nếu `Opened_tables` tăng nhanh và cache open table thường xuyên miss/overflow, kiểm tra table open cache và giới hạn file descriptor.
- Nếu nhiều bảng được truy cập luân phiên và định nghĩa phải nạp lại, xem xét table definition cache và số lượng bảng hoạt động.
- Nếu các lệnh DDL chờ, kiểm tra metadata lock và transaction giữ lock.
- Nếu truy vấn metadata chậm do thống kê, xem `information_schema_stats_expiry` và thời điểm `ANALYZE TABLE`.

**Bước 4: Thử thay đổi có kiểm soát**

Điều chỉnh tham số phù hợp trên môi trường thử nghiệm, chạy cùng bộ truy vấn, ghi lại các chỉ số và so sánh. Khi triển khai, kiểm tra giới hạn của hệ điều hành hoặc dịch vụ managed database. Một số nền tảng tự quản lý tham số hoặc giới hạn giá trị tối đa.

**Bước 5: Xác minh sau thay đổi**

Kiểm tra lại độ trễ, throughput, cache counters, memory và open files. Nếu chỉ số cache tốt hơn nhưng độ trễ không cải thiện, có thể bottleneck nằm ở I/O dữ liệu, lock, CPU, index hoặc query plan. Không nên tiếp tục tăng cache nếu không có bằng chứng rằng nó giải quyết nguyên nhân.

## 12. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Data dictionary là nơi lưu các hàng dữ liệu nghiệp vụ | Data dictionary lưu metadata mô tả các đối tượng database |
| Dictionary Object Cache và `table_definition_cache` là cùng một cache | Trong MySQL 8.4, chúng tồn tại song song và phục vụ các phần khác nhau |
| `table_open_cache` là số bảng tối đa trong schema | Đây là cache các table instance đang mở cho tất cả thread |
| Tăng `table_definition_cache` sẽ giải quyết mọi lỗi mở bảng | Nó không thay thế table open cache, file descriptor hay metadata lock |
| Metadata lock là một cache | MDL là cơ chế đồng bộ truy cập đối tượng |
| Có thể chỉnh trực tiếp bảng nội bộ của data dictionary | Hãy dùng `INFORMATION_SCHEMA` và `SHOW`; không sửa dictionary table trực tiếp |
| `Opened_tables` lớn luôn chứng minh cache quá nhỏ | Đây là bộ đếm tích lũy; cần xem mức tăng theo thời gian và các chỉ số liên quan |
| `FLUSH TABLES` là cách tối ưu cache định kỳ | Flush đóng bảng và buộc server mở lại; dùng sai thời điểm có thể tạo thêm chi phí |
| `TABLE_ROWS` trong INFORMATION_SCHEMA luôn chính xác | Với InnoDB, đây thường là giá trị ước lượng |
| Atomic DDL đồng nghĩa có thể rollback DDL bằng transaction ứng dụng | Atomic DDL là cơ chế phục hồi nguyên tử của server cho thao tác được hỗ trợ |

## 13. Checklist vận hành

- [ ] Đã xác định phiên bản MySQL đang chạy và đặc điểm data dictionary của phiên bản đó.
- [ ] Dùng `SHOW` hoặc `INFORMATION_SCHEMA` để đọc metadata.
- [ ] Không truy cập hoặc sửa trực tiếp các bảng data dictionary nội bộ.
- [ ] Phân biệt Dictionary Object Cache, table definition cache và table open cache.
- [ ] Hiểu `table_definition_cache` và `table_open_cache` điều khiển những lớp khác nhau.
- [ ] Đã ghi nhận `max_connections` và `open_files_limit` trước khi điều chỉnh table open cache.
- [ ] Đã lấy baseline và so sánh delta status variables trong workload đại diện.
- [ ] Đã phân biệt cache thống kê INFORMATION_SCHEMA với cache định nghĩa bảng.
- [ ] Đã kiểm tra metadata lock khi DDL chờ lâu.
- [ ] Đã đo lại hiệu năng và mức tiêu thụ tài nguyên sau khi thay đổi cấu hình.

## 14. Kết luận

Data dictionary là nền tảng quản lý metadata của MySQL. Dictionary Object Cache giữ các đối tượng metadata trong bộ nhớ; table definition cache giữ định nghĩa bảng để tái sử dụng; table open cache giữ các table instance đang mở cho session; cache thống kê INFORMATION_SCHEMA giúp truy vấn một số số liệu metadata nhanh hơn. Metadata lock phối hợp truy cập đồng thời tới định nghĩa đối tượng và cần được điều tra riêng.

Khi vận hành, hãy xác định đúng lớp đang gây vấn đề trước khi thay đổi cấu hình. Dùng `INFORMATION_SCHEMA` và `SHOW` để đọc định nghĩa, dùng status variables để theo dõi cache, dùng Performance Schema để điều tra metadata lock, rồi đo lại dưới workload thực tế. Cách tiếp cận theo bằng chứng giúp tránh tăng bộ nhớ hoặc file descriptor mà không giải quyết được bottleneck.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – MySQL Data Dictionary](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary.html)
- [MySQL 8.4 Reference Manual – Data Dictionary Schema](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-schema.html)
- [MySQL 8.4 Reference Manual – Dictionary Object Cache](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-object-cache.html)
- [MySQL 8.4 Reference Manual – Server System Variables: table_definition_cache and table_open_cache](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual – How MySQL Opens and Closes Tables](https://dev.mysql.com/doc/refman/8.4/en/table-cache.html)
- [MySQL 8.4 Reference Manual – Server Status Variables](https://dev.mysql.com/doc/refman/8.4/en/server-status-variables.html)
- [MySQL 8.4 Reference Manual – Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual – The Performance Schema metadata_locks Table](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-metadata-locks-table.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA and Data Dictionary Integration](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-information-schema.html)

