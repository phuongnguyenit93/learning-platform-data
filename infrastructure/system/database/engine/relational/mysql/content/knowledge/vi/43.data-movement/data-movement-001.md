# Chọn phạm vi di chuyển: dữ liệu, schema, tài khoản và cấu hình

Bài học này thuộc module **DATABASE_MYSQL**. Khi chuyển MySQL sang máy chủ mới, nâng cấp phiên bản, tách một ứng dụng khỏi database dùng chung hoặc dựng môi trường thử nghiệm, bước đầu tiên là xác định chính xác những gì cần di chuyển. Một lần migration có thể bao gồm dữ liệu, schema, tài khoản và quyền, cấu hình máy chủ, hoặc toàn bộ instance. Mỗi nhóm có cách xuất, nhập, kiểm tra và phụ thuộc khác nhau.

Chọn sai phạm vi thường dẫn đến hai kiểu sự cố: thiếu thành phần khiến ứng dụng không hoạt động sau cutover, hoặc mang theo quá nhiều trạng thái cũ làm máy chủ đích nhận cấu hình, quyền truy cập và dữ liệu không phù hợp. Vì vậy, cần lập danh mục đối tượng và phụ thuộc trước khi chọn công cụ.

## 1. Bốn phạm vi di chuyển chính

| Phạm vi | Bao gồm | Ví dụ nhu cầu | Cách xử lý thường dùng |
|---|---|---|---|
| **Schema** | Database, table, view, index, constraint, trigger, routine, event | Tạo cấu trúc database mới hoặc chuyển sang phiên bản khác | Logical dump schema, migration script, MySQL Shell |
| **Dữ liệu** | Các hàng trong bảng, có thể toàn bộ hoặc một tập được chọn | Chuyển dữ liệu nghiệp vụ, nạp dữ liệu lịch sử, đồng bộ một số bảng | Logical dump, `LOAD DATA`, replication, công cụ ETL |
| **Tài khoản và quyền** | User, role, authentication plugin, grants, default role, thuộc tính tài khoản | Cho ứng dụng và người vận hành truy cập máy chủ mới | `SHOW CREATE USER`, `SHOW GRANTS`, script quản trị |
| **Cấu hình và thành phần vận hành** | System variables, file cấu hình, plugin/component, TLS, keyring, đường dẫn, lịch backup và replication | Dựng máy chủ thay thế hoặc chuyển môi trường | Kiểm kê và áp dụng cấu hình có chọn lọc, triển khai thành phần phụ trợ |

Một lần chuyển toàn bộ instance thường cần cả bốn phạm vi. Một lần chuyển riêng database cho một dịch vụ có thể chỉ cần schema, dữ liệu và các tài khoản liên quan. Dù phạm vi nào, hãy xác định các phụ thuộc nằm ngoài database như secret, chứng thư, DNS, ứng dụng, job nền và công cụ giám sát.

## 2. Khảo sát nguồn và đích trước khi chọn phạm vi

Trước khi export, thu thập thông tin từ máy chủ nguồn và máy chủ đích. Các lệnh cơ bản:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution,
       @@hostname AS server_name,
       @@server_id AS server_id,
       @@server_uuid AS server_uuid;

SHOW DATABASES;
SHOW ENGINES;
SHOW PLUGINS;
SHOW GLOBAL VARIABLES;
```

Với từng schema cần di chuyển, lập danh sách bảng, view và đối tượng khác:

```sql
SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS,
       DATA_LENGTH, INDEX_LENGTH
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_TYPE, TABLE_NAME;

SELECT ROUTINE_NAME, ROUTINE_TYPE, DEFINER, SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop';

SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_TIMING,
       EVENT_MANIPULATION, DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'shop';

SELECT EVENT_NAME, STATUS, DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'shop';
```

`TABLE_ROWS` với InnoDB thường là số liệu ước lượng, không nên dùng làm bằng chứng duy nhất để xác nhận dữ liệu đã chuyển đủ. Các truy vấn `information_schema` cũng có thể bị giới hạn bởi quyền của tài khoản khảo sát.

Kiểm tra các điểm tương thích:

- Phiên bản MySQL và nhánh phân phối của nguồn/đích.
- Storage engine, charset, collation và `sql_mode`.
- Dung lượng dữ liệu, tốc độ ghi, số lượng bảng và thời gian dump/restore.
- View, trigger, procedure, function, event và các đối tượng có `DEFINER`.
- Foreign key, thứ tự phụ thuộc giữa bảng và các bảng tham chiếu ngoài phạm vi.
- Plugin xác thực, plugin/component, TLS, keyring và dữ liệu mã hóa.
- Binary log, GTID, replication channel và các tác vụ backup hiện có.

Không phải mọi phiên bản MySQL đều có thể trao đổi trực tiếp mọi định dạng dump hoặc physical backup. Hãy kiểm tra ma trận tương thích, ghi lại khác biệt và thử import trên một máy đích tương đương trước khi lập lịch cutover.

## 3. Chọn mức độ di chuyển

Có thể chia yêu cầu thành bốn mức từ nhỏ đến lớn:

1. **Chỉ dữ liệu:** schema đích đã tồn tại và tương thích; chỉ nạp hoặc đồng bộ các hàng.
2. **Schema và dữ liệu của một database:** tạo lại đối tượng và nạp dữ liệu cho một ứng dụng.
3. **Nhiều database cùng các tài khoản liên quan:** di chuyển nhiều ứng dụng, role và quyền cần thiết.
4. **Toàn instance hoặc toàn môi trường:** dữ liệu, cấu hình, tài khoản, plugin, khóa, replication và quy trình vận hành.

Chọn mức nhỏ nhất vẫn đáp ứng mục tiêu. Nếu chỉ cần một schema, không nên sao chép cả system database hoặc cấu hình máy chủ không liên quan. Ngược lại, nếu ứng dụng phụ thuộc vào event scheduler, routine, user-defined function hoặc tài khoản `DEFINER`, một dump chỉ gồm các bảng và dữ liệu là chưa đủ.

### 3.1. Ma trận chọn phạm vi theo tình huống

| Tình huống | Phạm vi cần xem xét | Câu hỏi phải trả lời |
|---|---|---|
| Tạo môi trường test từ production | Schema, dữ liệu đã ẩn danh, tài khoản test, cấu hình riêng | Có dữ liệu cá nhân/secret nào cần loại bỏ? Có nên giảm dung lượng dữ liệu? |
| Tách một ứng dụng khỏi database dùng chung | Schema, bảng liên quan, routine/view/trigger/event, user và grants | Có truy vấn hoặc khóa ngoại tham chiếu schema khác không? |
| Nâng cấp MySQL | Schema, dữ liệu, user/role, cấu hình tương thích, plugin | Có cú pháp, collation, auth plugin hoặc biến cấu hình đã thay đổi không? |
| Chuyển sang máy chủ mới cùng phiên bản | Dữ liệu, schema, tài khoản, cấu hình được duyệt, TLS/keyring | Dùng logical hay physical backup? Có giữ binlog/GTID để đồng bộ phần phát sinh không? |
| Khôi phục một bảng bị xóa | Dữ liệu và có thể schema của bảng, cùng phụ thuộc liên quan | Có thể restore vào instance tạm rồi trích xuất bảng không? |
| Dựng replica mới | Snapshot dữ liệu, metadata file/position hoặc GTID, cấu hình replication và user | Snapshot tương ứng chính xác với điểm bắt đầu nào? |

## 4. Di chuyển schema

Schema mô tả cấu trúc và hành vi của database. Một schema đầy đủ có thể bao gồm:

- Database và các thuộc tính charset/collation.
- Table, column, kiểu dữ liệu, default, generated column và index.
- Primary key, unique key, foreign key, check constraint.
- View và định nghĩa `DEFINER`.
- Trigger.
- Stored procedure và function.
- Event Scheduler events.

Không nên chỉ kiểm tra rằng các bảng đã xuất hiện. Ứng dụng có thể phụ thuộc vào view, routine, trigger hoặc event để thực hiện nghiệp vụ.

### 4.1. Export schema bằng `mysqldump`

Ví dụ xuất cấu trúc database `shop` mà không xuất hàng dữ liệu:

```bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --no-data \
  --routines \
  --events \
  --triggers \
  --databases shop \
  > shop-schema.sql
```

`--no-data` bỏ phần dữ liệu hàng. Dump vẫn có thể chứa định nghĩa database, bảng, view và các đối tượng được chọn. Trigger được dump mặc định trong `mysqldump`; ghi rõ `--triggers` giúp thể hiện chủ đích. `--routines` và `--events` yêu cầu đưa procedure/function và event vào dump.

Trước khi import, kiểm tra các lệnh `CREATE DATABASE`, `USE`, `DEFINER`, charset, collation và các câu lệnh có thể ghi đè đối tượng hiện có. Nếu đích đã có schema, cần quyết định rõ có tạo schema mới, điều chỉnh tên hay áp dụng migration tăng dần.

### 4.2. Export schema bằng migration script

Với ứng dụng phát triển liên tục, có thể quản lý schema bằng các migration script có version thay vì dump lại toàn bộ cấu trúc mỗi lần triển khai. Một migration nên:

1. Có mã version hoặc tên duy nhất.
2. Thể hiện thay đổi cụ thể, ví dụ thêm cột, index hoặc bảng.
3. Được thử trên bản sao dữ liệu đại diện.
4. Có kế hoạch xử lý khi migration thất bại hoặc mất nhiều thời gian.
5. Được ghi nhận để biết môi trường nào đã áp dụng đến version nào.

DDL trong MySQL thường gây implicit commit và nhiều thao tác DDL không thể rollback như DML thông thường. Không giả định một chuỗi `ALTER TABLE` có thể được hoàn tác bằng `ROLLBACK`. Với bảng lớn, cần đánh giá thời gian khóa, thuật toán DDL, dung lượng tạm và ảnh hưởng tới replication.

### 4.3. Xử lý `DEFINER`

View, trigger, routine và event có thể lưu người định nghĩa (`DEFINER`). Nếu tài khoản này không tồn tại trên máy chủ đích hoặc thiếu quyền phù hợp, đối tượng có thể lỗi khi tạo hoặc khi thực thi. Hãy kiểm kê `DEFINER`, tạo tài khoản/role phù hợp theo chính sách hoặc thay đổi định nghĩa có kiểm soát. Không thay mọi `DEFINER` thành một tài khoản quản trị dùng chung.

## 5. Di chuyển dữ liệu

Trước khi export dữ liệu, xác định rõ bảng nào, hàng nào, cột nào và thời điểm nhất quán cần giữ. Có ba kiểu phạm vi thường gặp:

- **Toàn bộ dữ liệu của schema:** phù hợp khi chuyển một database hoàn chỉnh.
- **Một tập bảng:** phù hợp khi tách một phần ứng dụng hoặc chỉ khôi phục một số bảng.
- **Một tập hàng hoặc cột:** phù hợp khi chuyển dữ liệu lịch sử, ẩn danh dữ liệu test hoặc ETL.

### 5.1. Export dữ liệu mà không tạo lại bảng

Nếu schema đích đã được tạo và xác minh tương thích, có thể dump dữ liệu của một số bảng:

```bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --single-transaction \
  --no-create-info \
  --skip-triggers \
  shop customers orders order_items \
  > shop-data.sql
```

- `--no-create-info` không xuất câu lệnh tạo bảng.
- `--skip-triggers` tránh xuất trigger trong dump dữ liệu khi trigger đã được chuyển ở bước schema.
- `--single-transaction` tạo consistent snapshot cho các bảng transactional như InnoDB.

Schema đích phải có các bảng và cấu trúc tương thích trước khi nạp. Với dữ liệu có foreign key, cần hiểu thứ tự nạp và trạng thái các bảng tham chiếu. Ưu tiên nạp theo thứ tự phụ thuộc với kiểm tra ràng buộc được bật. Nếu buộc phải tạm tắt `FOREIGN_KEY_CHECKS`, cần xác minh lại tính toàn vẹn sau đó vì bật lại biến không tự động quét và xác thực các hàng đã nạp trước đó.

### 5.2. Chỉ xuất một tập hàng

`mysqldump --where` có thể lọc hàng cho một bảng:

```bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --no-create-info \
  --skip-triggers \
  --where="created_at >= '2026-01-01'" \
  shop orders \
  > recent-orders.sql
```

Điều kiện `WHERE` cần được kiểm tra kỹ để không bỏ sót hoặc lấy trùng dữ liệu. Nếu di chuyển nhiều bảng có quan hệ, một bộ lọc trên từng bảng phải bảo toàn quan hệ nghiệp vụ và khóa ngoại. Ví dụ, lấy đơn hàng theo ngày nhưng không lấy các dòng `order_items` tương ứng sẽ tạo dữ liệu không đầy đủ.

### 5.3. Nạp dữ liệu

Với dump SQL, dùng MySQL client để import vào database đích:

```bash
mysql \
  --host=db02.example.net \
  --user=restore_user \
  --password \
  < shop-schema.sql

mysql \
  --host=db02.example.net \
  --user=restore_user \
  --password \
  < shop-data.sql
```

Nếu dump chỉ định database khác với tên mong muốn, hãy xử lý schema đích trước và kiểm tra các lệnh `USE` trong dump. Không sửa chuỗi SQL hàng loạt bằng thay thế văn bản đơn giản khi tên database xuất hiện trong view, routine, dữ liệu hoặc câu lệnh có quoting.

Với dữ liệu dạng CSV, `LOAD DATA` có thể nhanh hơn việc thực thi từng câu `INSERT`, nhưng cần kiểm soát charset, delimiter, escape, NULL, định dạng ngày giờ, thứ tự cột và quyền truy cập file. Ví dụ:

```sql
LOAD DATA LOCAL INFILE 'orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, created_at, status);
```

`LOCAL` đọc file từ phía client; việc dùng nó phụ thuộc cấu hình client/server và chính sách bảo mật. Chỉ bật khi cần thiết, giới hạn nguồn file và không cho phép client không tin cậy nạp file tùy ý.

### 5.4. Nhất quán trong lúc export

`--single-transaction` của `mysqldump` thường phù hợp với InnoDB vì dump đọc từ một consistent snapshot mà không cần giữ khóa đọc toàn bộ thời gian. Tuy nhiên:

1. Nó không tạo cùng bảo đảm snapshot cho MyISAM hoặc storage engine không transactional.
2. Không chạy DDL như `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc `TRUNCATE TABLE` trên đối tượng đang dump.
3. Giao dịch ghi dài hoặc snapshot kéo dài có thể làm tăng lượng undo history cần giữ.
4. Nếu cần đồng bộ các bảng/đối tượng thuộc nhiều nguồn hoặc nhiều engine, phải thiết kế cửa sổ khóa hoặc cơ chế snapshot phù hợp.

Với migration cần downtime rất ngắn, có thể dùng một snapshot ban đầu rồi theo dõi phần thay đổi phát sinh bằng replication/binlog, sau đó dừng ghi ngắn để áp dụng phần cuối và cutover. Cần lưu chính xác tọa độ binlog hoặc GTID gắn với snapshot.

## 6. Di chuyển tài khoản và quyền

Tài khoản MySQL có định danh theo cặp `user` và `host`. `app@localhost` và `app@192.0.2.20` là hai tài khoản riêng, có thể có phương thức xác thực, mật khẩu, trạng thái khóa và quyền khác nhau. Vì vậy, chuyển user không chỉ là sao chép tên tài khoản.

### 6.1. Kiểm kê user và role

Người quản trị có thể xem danh sách tài khoản bằng truy vấn được cấp quyền:

```sql
SELECT User, Host, plugin, account_locked
FROM mysql.user
ORDER BY User, Host;
```

`mysql.user` là bảng hệ thống để đọc thông tin tài khoản; không cập nhật trực tiếp bảng này. Hãy dùng câu lệnh quản trị được MySQL hỗ trợ để tạo, sửa, khóa hoặc xóa tài khoản.

Với từng tài khoản ứng dụng hoặc quản trị cần di chuyển, ghi lại:

- Tên và host được phép kết nối.
- Authentication plugin và yêu cầu TLS.
- Trạng thái khóa, thời hạn mật khẩu, giới hạn tài nguyên và thuộc tính tài khoản.
- Các global/schema/table/column privileges.
- Role được cấp, role mặc định và quan hệ role lồng nhau.
- Đối tượng có `DEFINER` phụ thuộc vào tài khoản.

Không nhất thiết phải chuyển mọi tài khoản trên source. Tài khoản nội bộ, tài khoản cá nhân đã hết hạn hoặc tài khoản thuộc nền tảng quản lý có thể không phù hợp trên máy chủ đích.

### 6.2. Xuất định nghĩa và quyền

Với mỗi tài khoản cần chuyển, chạy:

```sql
SHOW CREATE USER 'app'@'192.0.2.20';
SHOW GRANTS FOR 'app'@'192.0.2.20';
```

`SHOW CREATE USER` cung cấp câu lệnh tạo tài khoản cùng các thuộc tính xác thực được máy chủ biểu diễn. `SHOW GRANTS` cung cấp các câu lệnh cấp quyền và role. Lưu kết quả trong khu vực được bảo vệ vì output có thể chứa authentication string hoặc thông tin nhạy cảm.

Thứ tự áp dụng thường là:

1. Kiểm tra authentication plugin cần thiết đã có trên đích.
2. Tạo role trước nếu user sẽ được cấp role.
3. Tạo user với host phù hợp và thuộc tính xác thực được duyệt.
4. Áp dụng grants, role grants và default role.
5. Kiểm tra quyền hiệu lực bằng `SHOW GRANTS` và thử kết nối từ đúng nguồn.

Ví dụ tạo tài khoản và cấp quyền tối thiểu trên máy chủ đích:

```sql
CREATE USER 'app'@'192.0.2.20'
  IDENTIFIED BY 'replace-with-a-new-secret'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE
  ON shop.* TO 'app'@'192.0.2.20';

SHOW GRANTS FOR 'app'@'192.0.2.20';
```

Mật khẩu trong ví dụ là placeholder. Khi di chuyển, có thể giữ nguyên danh tính nếu host và plugin tương thích, hoặc thay đổi theo chính sách bảo mật. Không sao chép password hash thủ công nếu chưa hiểu plugin và định dạng xác thực.

### 6.3. Kiểm tra host và authentication plugin

Host của tài khoản source có thể không còn đúng trên đích. Ví dụ, ứng dụng trước đây kết nối từ `10.0.1.15`, nhưng sau khi chuyển sang VPC mới sẽ đi ra từ `10.20.4.12`. Cần xác định IP mà MySQL đích thực sự nhìn thấy, bao gồm NAT, proxy và container gateway.

Authentication plugin cũng phải tồn tại và được hỗ trợ trên máy chủ đích. Nếu source dùng plugin xác thực bên ngoài, plugin đó có thể yêu cầu thư viện, cấu hình hoặc dịch vụ xác thực bổ sung. Chuyển câu lệnh `CREATE USER` mà không chuyển dependency tương ứng sẽ khiến đăng nhập thất bại.

Không cấp quyền rộng như `ALL PRIVILEGES ON *.*` chỉ để tránh lỗi quyền sau migration. Hãy xác định câu lệnh ứng dụng cần thực hiện và cấp quyền ở phạm vi nhỏ nhất phù hợp.

## 7. Di chuyển cấu hình và thành phần vận hành

Cấu hình MySQL gồm biến khởi động, biến động, tệp cấu hình, plugin/component và phụ thuộc bên ngoài. Không nên sao chép nguyên tệp cấu hình từ source sang đích mà chưa rà soát vì hai máy có thể khác CPU, RAM, storage, hệ điều hành, đường dẫn và vai trò topology.

### 7.1. Kiểm kê system variables

Có thể xuất danh sách biến hiện tại:

```sql
SHOW GLOBAL VARIABLES;
```

Tập trung vào các nhóm:

| Nhóm | Ví dụ | Câu hỏi khi chuyển |
|---|---|---|
| Bộ ký tự và collation | `character_set_server`, `collation_server` | Có tương thích dữ liệu và ứng dụng không? |
| SQL behavior | `sql_mode`, `time_zone`, `system_time_zone` | Có làm thay đổi kết quả truy vấn hoặc thời gian không? |
| InnoDB | `innodb_buffer_pool_size`, `innodb_flush_log_at_trx_commit`, `innodb_redo_log_capacity` | Có phù hợp RAM, I/O và yêu cầu durability của đích không? |
| Kết nối | `max_connections`, `connect_timeout`, `wait_timeout` | Có đáp ứng connection pool và tải thực tế không? |
| Binary log | `log_bin`, `binlog_format`, `sync_binlog`, `binlog_expire_logs_seconds` | Đích là source, replica hay máy độc lập? |
| Replication | `server_id`, `gtid_mode`, `enforce_gtid_consistency`, `log_replica_updates` | Có cần định danh và trạng thái replication mới không? |
| Bảo mật | `require_secure_transport`, TLS variables, audit settings | Chứng thư, CA và chính sách có sẵn trên đích không? |

Danh sách biến chỉ là dữ liệu khảo sát. Mỗi biến cần được phân loại là cấu hình bắt buộc, cấu hình tối ưu theo phần cứng, cấu hình theo vai trò hoặc cấu hình có thể bỏ. Giá trị của source không nhất thiết phù hợp với đích.

### 7.2. Tệp cấu hình và đường dẫn

MySQL thường đọc cấu hình từ `my.cnf` trên Unix-like hoặc `my.ini` trên Windows, cùng các tệp include tùy cách cài đặt. Khi chuyển, cần kiểm tra:

- `datadir`, `tmpdir`, socket, PID, error log, slow query log và binary log path.
- Quyền sở hữu và quyền truy cập filesystem của tài khoản chạy MySQL.
- Kích thước RAM/CPU, storage throughput và giới hạn hệ điều hành.
- `server_id` phải duy nhất trong topology replication.
- `server_uuid` được MySQL tạo cho instance; không nhân bản identity từ source sang một instance mới.
- `lower_case_table_names` có ràng buộc theo nền tảng và thời điểm khởi tạo data directory; không coi đây là biến có thể đổi tùy ý sau khi đã tạo dữ liệu.

Giữ bản cấu hình source để tham khảo, nhưng áp dụng từng thiết lập đã được duyệt vào cấu hình đích. Ghi lại giá trị trước/sau và cách rollback. Tránh copy các đường dẫn hoặc socket không tồn tại trên hệ điều hành đích.

### 7.3. Plugin, component, TLS và keyring

Nếu ứng dụng hoặc database phụ thuộc vào plugin/component, cần kiểm tra binary tương thích, phiên bản, cấu hình load và license nếu có. Không phải plugin đã cài trên source đều tự có trên đích.

Với mã hóa dữ liệu, việc di chuyển file tablespace có thể chưa đủ. Cần bảo toàn keyring hoặc hệ thống quản lý khóa tương ứng, quyền truy cập, master key và quy trình phục hồi khóa. Mất khóa có thể khiến dữ liệu đã mã hóa không thể đọc được.

Với TLS, cần chuyển hoặc cấp mới certificate, private key, CA chain và cấu hình xác minh danh tính. Private key phải được bảo vệ như secret. Kiểm tra kết nối từ ứng dụng và replication sau khi cài đặt.

### 7.4. Không sao chép nguyên system database

Không dùng việc dump/copy nguyên schema `mysql` như cách di chuyển user và quyền giữa các phiên bản khác nhau. Cấu trúc system table và data dictionary có thể thay đổi theo phiên bản; ghi đè chúng có thể làm hỏng metadata hoặc gây lỗi khởi động/nâng cấp. Hãy di chuyển tài khoản bằng các câu lệnh quản trị được hỗ trợ và để MySQL quản lý system tables theo quy trình cài đặt/nâng cấp.

## 8. Chọn công cụ theo phạm vi và kích thước

| Công cụ/phương thức | Phạm vi phù hợp | Điểm mạnh | Giới hạn cần cân nhắc |
|---|---|---|---|
| `mysqldump` | Schema, dữ liệu logic, bảng chọn lọc | Dễ đọc, dễ lọc và phù hợp di chuyển chọn lọc | Restore có thể chậm với dữ liệu lớn; cần đủ tùy chọn đối tượng |
| MySQL Shell dump/load utilities | Instance, schema hoặc table ở dạng logical dump | Hỗ trợ chunking và nạp song song; phù hợp tập dữ liệu lớn | Cần kiểm tra phiên bản, tùy chọn và tương thích đích |
| Physical backup | Toàn instance hoặc phạm vi mà công cụ hỗ trợ | Thường nhanh với lượng dữ liệu lớn, giữ layout vật lý | Phụ thuộc phiên bản, engine, công cụ, cấu hình và keyring |
| `LOAD DATA` | Nạp dữ liệu dạng file như CSV | Nạp hàng loạt hiệu quả | Cần xử lý charset, delimiter, NULL, quyền và định dạng |
| Replication/binlog | Đồng bộ thay đổi sau snapshot | Giảm thời gian dừng ghi khi cutover | Cần giữ log liên tục và xử lý lag/GTID/điểm bắt đầu |
| ETL hoặc ứng dụng chuyển đổi | Chọn lọc, biến đổi hoặc hợp nhất dữ liệu | Linh hoạt với mapping và làm sạch | Phải thiết kế tính nhất quán, retry và đối soát |

Không có một công cụ tối ưu cho mọi phạm vi. Với một vài bảng nhỏ, logical dump có thể đủ. Với hàng terabyte và downtime hạn chế, physical backup cộng replication/binlog có thể phù hợp hơn. Quyết định cần dựa trên thử nghiệm thời gian export, truyền, import, kiểm tra và cutover.

## 9. Trình tự migration an toàn

Một kế hoạch migration nên chia thành các giai đoạn có thể kiểm chứng.

### 9.1. Trước khi di chuyển

1. Xác định mục tiêu, phạm vi, chủ sở hữu dữ liệu, cửa sổ downtime, RTO/RPO và tiêu chí thành công.
2. Kiểm kê schema, dữ liệu, user/role, grants, config, plugin, certificate, keyring và job phụ thuộc.
3. So sánh phiên bản, charset, collation, SQL mode, storage engine và tính năng không tương thích.
4. Chọn logical, physical, replication hoặc ETL; xác định cách tạo snapshot nhất quán.
5. Tạo backup có thể restore và kiểm tra trên môi trường độc lập.
6. Chuẩn bị máy chủ đích, dung lượng, tài khoản quản trị, firewall, TLS và giám sát.
7. Thử migration trên dữ liệu đại diện, đo thời gian và cập nhật runbook.

### 9.2. Trong khi di chuyển

1. Tạo snapshot/dump tại một thời điểm đã xác định và lưu metadata binlog/GTID nếu cần đồng bộ phần phát sinh.
2. Di chuyển schema và các đối tượng phụ thuộc.
3. Tạo user/role và áp dụng quyền đã được duyệt.
4. Nạp dữ liệu theo thứ tự phụ thuộc; theo dõi lỗi, tốc độ, dung lượng và tiến độ.
5. Nếu dùng replication, cấu hình receiver/applier và chờ replica bắt kịp.
6. Đối chiếu dữ liệu, schema, quyền và các đối tượng trước cutover.

### 9.3. Cutover

1. Thông báo và kích hoạt cửa sổ chuyển đổi.
2. Dừng hoặc khóa các luồng ghi mới vào nguồn theo cách ứng dụng hỗ trợ.
3. Áp dụng phần dữ liệu cuối cùng hoặc chờ replication đạt điểm đồng bộ đã xác định.
4. Xác nhận transaction cuối, GTID/binlog position và tính nhất quán.
5. Chuyển endpoint, secret hoặc cấu hình kết nối ứng dụng sang đích.
6. Chạy smoke test cho các luồng nghiệp vụ quan trọng.
7. Mở lại traffic theo từng bước và theo dõi lỗi, latency, connection, deadlock và dữ liệu.

Không cho phép source và target cùng nhận ghi độc lập trong lúc chuyển đổi trừ khi kiến trúc đã thiết kế cơ chế multi-writer và xử lý xung đột rõ ràng. Hai nơi cùng nhận ghi ngoài kiểm soát có thể làm dữ liệu phân kỳ và rất khó hợp nhất.

### 9.4. Sau migration và rollback

Giữ source ở trạng thái có thể đối chiếu trong khoảng thời gian đã định, nhưng ngăn ghi nhầm vào source cũ. Theo dõi ứng dụng và so sánh kết quả nghiệp vụ trước khi kết thúc cửa sổ rollback.

Rollback cần có điều kiện rõ ràng: lỗi nào khiến quay lại, ai quyết định, dữ liệu phát sinh trên target sẽ được xử lý thế nào và source cũ có thể nhận lại ghi ở thời điểm nào. Nếu target đã nhận ghi mới, không thể chỉ đổi endpoint về source mà bỏ qua các giao dịch đó; cần đồng bộ ngược hoặc thực hiện quy trình phục hồi dữ liệu có kiểm soát.

## 10. Xác minh kết quả di chuyển

Không kết luận thành công chỉ vì câu lệnh import kết thúc với exit code 0. Kiểm tra theo từng phạm vi:

| Phạm vi | Kiểm tra |
|---|---|
| Schema | So sánh `SHOW CREATE TABLE`, view, index, constraint, trigger, routine và event |
| Dữ liệu | Đếm hàng, đối chiếu tổng hợp nghiệp vụ, checksum hoặc hash theo lô, kiểm tra mẫu |
| Quan hệ | Kiểm tra orphan rows, khóa ngoại, quan hệ giữa bảng cha/con và tính toàn vẹn nghiệp vụ |
| Tài khoản | Kiểm tra `SHOW CREATE USER`, `SHOW GRANTS`, role mặc định, plugin và kết nối từ đúng host |
| Cấu hình | So sánh các biến bắt buộc, plugin, TLS, keyring, log path, replication và tham số bảo mật |
| Ứng dụng | Chạy smoke test, luồng ghi/đọc, job nền, báo cáo, event và các nghiệp vụ trọng yếu |
| Vận hành | Backup mới, restore thử, cảnh báo, giám sát, rotation và runbook |

Ví dụ kiểm tra số hàng và tổng giá trị đơn hàng:

```sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS order_total
FROM shop.orders;
```

Chạy cùng một truy vấn trên nguồn và đích tại hai trạng thái dữ liệu tương ứng. Nếu nguồn vẫn có ghi trong lúc so sánh, kết quả khác nhau có thể là do thời điểm snapshot. Với bảng lớn, đối chiếu theo khóa hoặc theo khoảng thời gian để dễ khoanh vùng sai lệch.

Kiểm tra foreign key logic bằng một truy vấn anti-join, ví dụ:

```sql
SELECT oi.order_id
FROM shop.order_items AS oi
LEFT JOIN shop.orders AS o
  ON o.order_id = oi.order_id
WHERE o.order_id IS NULL
LIMIT 20;
```

Kết quả cần được đánh giá theo quy tắc nghiệp vụ. Một truy vấn không trả về hàng nào là dấu hiệu tốt cho quan hệ này, nhưng chưa chứng minh mọi ràng buộc và dữ liệu đều đúng.

## 11. Các lỗi thường gặp khi chọn phạm vi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bảng có nhưng ứng dụng báo thiếu object | Chưa dump view, routine, trigger hoặc event | Kiểm kê đối tượng và xuất lại phần còn thiếu |
| View/routine lỗi quyền | `DEFINER` không tồn tại hoặc thiếu quyền | Tạo/điều chỉnh definer theo chính sách và kiểm tra grants |
| User đăng nhập thất bại | Sai host, auth plugin không có, TLS hoặc password policy khác | Kiểm tra `SHOW CREATE USER`, plugin, host thực tế và log xác thực |
| Import lỗi collation | Đích không hỗ trợ collation từ nguồn | Chọn kế hoạch tương thích, thử chuyển đổi charset/collation và kiểm tra kết quả |
| Dữ liệu thiếu hoặc trùng | Snapshot không nhất quán, export filter sai hoặc chạy import lặp | Xác minh mốc snapshot, khóa duy nhất, transaction và quy trình retry |
| Migration kéo dài | Dump SQL lớn, index/constraint, I/O hoặc import tuần tự | Đo từng giai đoạn, cân nhắc MySQL Shell, physical backup hoặc nạp song song có kiểm soát |
| Đích hoạt động khác nguồn | Cấu hình, SQL mode, time zone, plugin hoặc biến hệ thống khác | So sánh cấu hình có ảnh hưởng và kiểm thử ứng dụng |
| Không giải mã được dữ liệu mã hóa | Thiếu keyring hoặc khóa tương ứng | Khôi phục khóa qua quy trình quản lý khóa được phê duyệt |
| Replica không bắt kịp sau snapshot | Thiếu binlog, sai position/GTID hoặc retention quá ngắn | Kiểm tra metadata và chuỗi log; tạo snapshot mới nếu không còn log cần thiết |

## 12. Checklist chọn phạm vi và cutover

- [ ] Đã xác định database, bảng, hàng và cột cần di chuyển.
- [ ] Đã kiểm kê view, index, constraint, trigger, routine và event.
- [ ] Đã kiểm tra `DEFINER` và các phụ thuộc giữa schema.
- [ ] Đã quyết định user/role nào cần chuyển, host nào cần điều chỉnh và quyền nào cần cấp.
- [ ] Đã kiểm tra authentication plugin, TLS, certificate, keyring và secret.
- [ ] Đã kiểm kê cấu hình nguồn và chọn giá trị phù hợp cho phần cứng/vai trò của đích.
- [ ] Đã kiểm tra tương thích phiên bản, charset, collation, SQL mode và storage engine.
- [ ] Đã chọn công cụ export/import phù hợp với dung lượng và downtime.
- [ ] Đã có snapshot nhất quán cùng binlog/GTID metadata nếu cần đồng bộ phần phát sinh.
- [ ] Đã thử restore/import trên môi trường tương đương.
- [ ] Đã có tiêu chí đối chiếu schema, dữ liệu, quyền và nghiệp vụ.
- [ ] Đã chuẩn bị cửa sổ cutover, fencing nguồn ghi và kế hoạch rollback.
- [ ] Đã kiểm tra backup mới và quy trình vận hành sau khi chuyển đổi.

## 13. Tự kiểm tra

1. Khi chỉ chuyển một database cho một ứng dụng, vì sao cần kiểm tra cả routine, trigger, event và `DEFINER`?
2. Khác biệt giữa `mysqldump --no-data` và `--no-create-info` là gì?
3. `--single-transaction` có bảo đảm snapshot nhất quán cho mọi storage engine không? Những thao tác nào cần tránh trong lúc dump?
4. Vì sao không nên sao chép nguyên schema `mysql` sang một máy chủ có phiên bản khác?
5. Khi di chuyển tài khoản, vì sao phải kiểm tra cả `user@host`, authentication plugin, role và grants?
6. Vì sao không nên copy nguyên file cấu hình từ source sang target mà không rà soát?
7. Một database dùng mã hóa cần chuyển thêm những thành phần nào ngoài data file?
8. Khi dùng snapshot ban đầu và replication để giảm downtime, cần lưu metadata nào để bắt đầu đồng bộ chính xác?
9. Vì sao phải dừng hoặc kiểm soát ghi trước cutover và không cho hai máy chủ cùng nhận ghi độc lập?
10. Hãy lập phạm vi migration cho một ứng dụng bán hàng gồm orders, order_items, khách hàng, tài khoản ứng dụng, event gửi báo cáo và cấu hình TLS; nêu cách kiểm tra sau chuyển đổi.

Một kế hoạch migration tốt bắt đầu từ danh mục đối tượng và phụ thuộc, sau đó mới chọn công cụ. Hãy bảo đảm từng phạm vi có cách export, import, xác minh và rollback rõ ràng; như vậy việc chuyển MySQL mới có thể được đánh giá bằng dữ liệu và kết quả kiểm thử cụ thể.
