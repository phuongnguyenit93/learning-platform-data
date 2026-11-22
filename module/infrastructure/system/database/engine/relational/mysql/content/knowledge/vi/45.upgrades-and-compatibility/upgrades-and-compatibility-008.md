# Data dictionary, system table và tính tương thích thư mục dữ liệu

MySQL cần lưu metadata để biết một database có những bảng nào, mỗi bảng có cột và index gì, tài khoản nào được phép truy cập và các đối tượng phụ thuộc ra sao. Metadata này được quản lý bởi **data dictionary** (từ điển dữ liệu), cùng với các system table và schema hệ thống phục vụ quản trị, giám sát và vận hành.

Kiến trúc metadata thay đổi đáng kể giữa các thế hệ MySQL. MySQL 5.7 và các phiên bản cũ dựa nhiều vào file metadata như `.frm` và các system table theo định dạng cũ. Từ MySQL 8.0, data dictionary được chuyển thành metadata transactional dựa trên InnoDB. Vì vậy, thư mục dữ liệu của một phiên bản không thể được xem như một tập file độc lập để tùy ý mở bằng binary của phiên bản khác.

Khi nâng cấp, di chuyển hoặc khôi phục MySQL, cần hiểu metadata nằm ở đâu, system schema chứa loại thông tin nào, công cụ nào là giao diện quản trị được hỗ trợ và những thuộc tính nào phải tương thích giữa source với target. Bài học này tập trung vào MySQL 8.0 và các nguyên tắc nâng cấp từ những phiên bản trước.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của data dictionary và thay đổi kiến trúc metadata trong MySQL 8.0.
- Phân biệt `INFORMATION_SCHEMA`, `mysql`, `performance_schema` và `sys`.
- Tra cứu metadata bằng `SHOW` và các view hệ thống được hỗ trợ.
- Hiểu vì sao không được sửa trực tiếp system table hoặc tự ghép file data directory giữa các phiên bản.
- Nhận diện các yếu tố ảnh hưởng đến tính tương thích của data directory và tablespace.
- Lập quy trình backup, kiểm tra, nâng cấp, xác minh và phương án phục hồi.

## 1. Data dictionary là gì?

Data dictionary là nơi MySQL quản lý metadata mô tả các đối tượng của database và quan hệ giữa chúng. Metadata bao gồm thông tin như:

- Database, table, view và cấu trúc cột.
- Index, khóa chính, unique key, foreign key và constraint.
- Stored procedure, function, trigger và event.
- Tablespace, partition và thuộc tính lưu trữ.
- Thông tin về các đối tượng cần thiết để server phân tích câu SQL, kiểm tra quyền và thực thi thao tác.

Khi chạy `SELECT * FROM app.orders`, MySQL cần biết bảng `orders` tồn tại, cột nào có trong bảng, kiểu dữ liệu, index, constraint và quyền của tài khoản hiện tại. Data dictionary cung cấp metadata để server thực hiện các bước đó.

Metadata khác với dữ liệu nghiệp vụ. Dữ liệu nghiệp vụ là các hàng trong `orders`, `customers` hoặc `payments`; metadata mô tả cấu trúc và thuộc tính của những đối tượng này. Backup và nâng cấp phải bảo toàn cả hai loại thông tin.

## 2. Thay đổi kiến trúc metadata từ MySQL 5.7 sang 8.0

### 2.1. Cách lưu metadata trước MySQL 8.0

Ở MySQL 5.7 và các phiên bản cũ, metadata của bảng được lưu một phần trong các file riêng như `.frm`; partition, trigger và một số đối tượng khác có thể dùng các file metadata riêng. System table trong schema `mysql` lưu thông tin tài khoản, quyền và nhiều metadata quản trị. Cách lưu trữ này khiến metadata bị phân tán qua nhiều định dạng và có những thao tác không có cùng đặc tính transactional với dữ liệu InnoDB.

Ví dụ, file `.frm` mô tả định nghĩa bảng, còn dữ liệu InnoDB có thể nằm trong tablespace riêng `.ibd` hoặc system tablespace. Chỉ sao chép file `.ibd` mà không mang theo metadata và thực hiện quy trình import tablespace được hỗ trợ không đủ để khôi phục một bảng hoàn chỉnh.

### 2.2. Data dictionary transactional trong MySQL 8.0

Từ MySQL 8.0, metadata được quản lý bởi một data dictionary transactional dựa trên InnoDB. Các bảng nội bộ của data dictionary nằm trong system schema `mysql` và được server quản lý. Các bảng nội bộ này không phải giao diện SQL công khai để ứng dụng tự đọc hoặc cập nhật; người dùng truy cập metadata thông qua `INFORMATION_SCHEMA`, `SHOW` và các giao diện được tài liệu MySQL hỗ trợ.

Việc chuyển sang data dictionary transactional mang lại một số lợi ích:

- Metadata được quản lý theo cơ chế transactional của InnoDB.
- Metadata và thao tác DDL có mô hình crash recovery nhất quán hơn.
- Không còn phụ thuộc vào file `.frm` cho metadata định nghĩa bảng như các phiên bản trước.
- Server có thể quản lý metadata của nhiều loại đối tượng theo kiến trúc thống nhất hơn.

Điều này cũng tạo ra yêu cầu nâng cấp: khi mở data directory cũ bằng MySQL 8.0, server phải chuyển đổi metadata sang kiến trúc mới. Đây là một phần của quá trình upgrade, không phải việc có thể thực hiện bằng cách đổi tên hoặc sao chép file thủ công.

### 2.3. Không sửa trực tiếp data dictionary

Không dùng câu lệnh `INSERT`, `UPDATE` hoặc `DELETE` trực tiếp trên các bảng nội bộ của data dictionary. Không tạo, xóa hay thay thế file metadata trong thư mục dữ liệu để ép server nhận một cấu trúc bảng khác.

Thay đổi đối tượng bằng các câu lệnh SQL được hỗ trợ:

```sql
CREATE TABLE app.orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  KEY idx_orders_customer (customer_id)
) ENGINE = InnoDB;

ALTER TABLE app.orders
  ADD COLUMN source_channel VARCHAR(30) NULL;

DROP TABLE app.temporary_import;
```

Các câu lệnh DDL cập nhật metadata theo quy trình mà MySQL quản lý, bao gồm khóa, kiểm tra phụ thuộc và crash recovery. Nếu metadata có vẻ sai sau sự cố, hãy dùng log, công cụ kiểm tra và quy trình phục hồi được hỗ trợ thay vì sửa system table.

## 3. Các schema hệ thống trong MySQL

MySQL cung cấp một số schema dành cho metadata, tài khoản, giám sát và tiện ích vận hành. Chúng có mục đích khác nhau.

| Schema | Vai trò | Cách sử dụng |
|---|---|---|
| `mysql` | System table, tài khoản, quyền, role và metadata quản trị | Dùng câu lệnh quản trị tài khoản/quyền; chỉ đọc các bảng hoặc view được tài liệu hỗ trợ |
| `INFORMATION_SCHEMA` | Các view cung cấp metadata về database, table, cột, index, constraint và routine | Tra cứu cấu trúc bằng SQL; không xem đây là thư mục file vật lý |
| `performance_schema` | Instrumentation và số liệu runtime về statement, wait, lock, thread và hoạt động server | Điều tra hiệu năng và vận hành; dữ liệu chủ yếu phản ánh trạng thái runtime |
| `sys` | Các view và procedure tiện dụng xây trên `performance_schema` và `INFORMATION_SCHEMA` | Dùng các view tổng hợp để chẩn đoán và quan sát |

`INFORMATION_SCHEMA`, `performance_schema` và `sys` không phải ba bản sao của data dictionary. Chúng cung cấp các góc nhìn khác nhau: metadata đối tượng, instrumentation runtime và các truy vấn tổng hợp dễ dùng.

### 3.1. Tra cứu metadata bằng INFORMATION_SCHEMA

Liệt kê các bảng nghiệp vụ và storage engine:

```sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  ENGINE,
  ROW_FORMAT,
  TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'app'
ORDER BY TABLE_NAME;
```

Xem định nghĩa cột theo thứ tự:

```sql
SELECT
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  EXTRA,
  ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Liệt kê index:

```sql
SELECT
  INDEX_NAME,
  NON_UNIQUE,
  SEQ_IN_INDEX,
  COLUMN_NAME,
  INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Tra cứu foreign key:

```sql
SELECT
  CONSTRAINT_NAME,
  COLUMN_NAME,
  REFERENCED_TABLE_SCHEMA,
  REFERENCED_TABLE_NAME,
  REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'orders'
  AND REFERENCED_TABLE_NAME IS NOT NULL;
```

Các view này giúp công cụ migration, audit schema và script kiểm tra tự động đọc metadata mà không cần phân tích file nội bộ của MySQL.

### 3.2. Dùng SHOW để xem định nghĩa chính xác

Khi cần xem định nghĩa bảng để lưu vào migration hoặc đối chiếu giữa hai môi trường, `SHOW CREATE TABLE` thường hữu ích hơn một truy vấn tổng hợp:

```sql
SHOW CREATE TABLE app.orders\G
SHOW CREATE VIEW app.active_orders\G
SHOW CREATE PROCEDURE app.rebuild_summary\G
```

`SHOW CREATE TABLE` trả về định nghĩa bảng, gồm cột, index, constraint, engine, charset/collation và các thuộc tính liên quan. Hãy lưu kết quả cùng phiên bản MySQL và thời điểm thu thập để có thể so sánh sau nâng cấp.

Không phải mọi metadata đều xuất hiện trong một câu `SHOW`. Đối với audit toàn diện, cần kết hợp các view thích hợp trong `INFORMATION_SCHEMA`, các lệnh `SHOW` và tài liệu về đối tượng đang kiểm tra.

### 3.3. Vai trò của mysql system schema

Schema `mysql` chứa các system table và view mà server dùng để quản lý tài khoản, quyền, role, thông tin múi giờ, component/plugin và một số metadata vận hành.

Trong MySQL 8.0, `mysql.user` là view tương thích để đọc thông tin tài khoản; thông tin quyền tài khoản được lưu theo cấu trúc nội bộ mới, trong đó có `mysql.global_priv`. Không nên dựa vào cấu trúc vật lý của các bảng này hoặc sửa chúng trực tiếp. Cấu trúc system schema có thể thay đổi giữa các bản phát hành.

Tạo tài khoản và cấp quyền bằng giao diện được hỗ trợ:

```sql
CREATE USER 'report_reader'@'10.20.5.12'
  IDENTIFIED BY '<mat-khau-tu-secret-manager>';

GRANT SELECT
  ON app.reporting_view
  TO 'report_reader'@'10.20.5.12';

SHOW GRANTS FOR 'report_reader'@'10.20.5.12';
```

Khi di chuyển tài khoản sang instance mới, hãy xuất hoặc tái tạo định nghĩa tài khoản, authentication plugin, role và grants bằng các câu lệnh được hỗ trợ. Không sao chép riêng các file hoặc bảng system schema từ một phiên bản khác vào thư mục `mysql` của server mới.

### 3.4. Performance Schema và sys schema

`performance_schema` ghi nhận hoạt động runtime như statement, wait, lock, file I/O và thread. Nó hữu ích khi điều tra truy vấn chậm hoặc migration bị chặn, nhưng không thay thế metadata định nghĩa bảng và không phải nơi lưu dữ liệu nghiệp vụ lâu dài.

`sys` cung cấp view tổng hợp để dễ đọc số liệu. Ví dụ:

```sql
SELECT *
FROM sys.schema_table_statistics
WHERE table_schema = 'app'
ORDER BY rows_fetched + rows_inserted + rows_updated + rows_deleted DESC;
```

View cụ thể và cột có thể khác theo phiên bản. Kiểm tra `SHOW CREATE VIEW` hoặc tài liệu đi kèm trước khi phụ thuộc vào một view trong automation.

## 4. Data directory chứa những gì?

Data directory là thư mục MySQL dùng để lưu dữ liệu và nhiều trạng thái cần thiết để server hoạt động. Đường dẫn thực tế được cấu hình theo môi trường, có thể kiểm tra bằng:

```sql
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'innodb_data_home_dir';
SHOW GLOBAL VARIABLES LIKE 'innodb_file_per_table';
```

Tùy cấu hình, data directory có thể chứa:

- Các thư mục database và tablespace dữ liệu.
- InnoDB system tablespace và undo tablespace.
- Redo log của InnoDB.
- Data dictionary và system schema.
- File nhận diện server như `auto.cnf`.
- Binary log và relay log nếu cấu hình đặt chúng trong data directory.
- File tạm, file trạng thái hoặc metadata phục vụ một số tính năng.

Không phải mọi thành phần đều bắt buộc nằm trong `datadir`; biến cấu hình có thể đặt redo log, binary log, relay log hoặc tablespace ở vị trí khác. Khi lập kế hoạch backup/di chuyển, cần kiểm kê toàn bộ đường dẫn thực tế, không chỉ sao chép một thư mục rồi giả định đã đủ.

### 4.1. Data directory là một đơn vị có quan hệ nội bộ

Các file dữ liệu, metadata và log phối hợp với nhau. Ví dụ, InnoDB cần metadata để biết tablespace nào thuộc bảng nào; redo log để phục hồi thay đổi chưa được checkpoint; undo để hỗ trợ transaction và rollback; binary log để replication và PITR.

Nếu lấy file `.ibd` từ một thời điểm, rồi ghép với data dictionary hoặc redo log từ thời điểm khác, server có thể không mở được tablespace hoặc dữ liệu không nhất quán. Tương tự, sao chép data directory khi MySQL đang chạy mà không dùng cơ chế backup nhất quán có thể tạo ra tập file không đồng bộ.

### 4.2. Kiểm tra cấu hình lưu trữ quan trọng

Trước khi di chuyển hoặc nâng cấp, ghi lại các biến liên quan:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'datadir',
  'innodb_data_home_dir',
  'innodb_data_file_path',
  'innodb_file_per_table',
  'innodb_page_size',
  'lower_case_table_names',
  'character_set_server',
  'collation_server',
  'log_bin',
  'log_bin_basename',
  'relay_log_basename'
);
```

Không phải biến nào cũng có thể thay đổi trên instance đã khởi tạo. Một số thuộc tính, như `innodb_page_size` và `lower_case_table_names`, gắn với cách instance được khởi tạo và không thể đổi tùy ý sau đó. Khi tạo target mới để phục hồi hoặc di chuyển vật lý, phải xác nhận các thuộc tính này tương thích với source và backup.

## 5. Tính tương thích của data directory

### 5.1. Không mở data directory mới bằng binary cũ

Sau khi MySQL mới nâng cấp data dictionary hoặc định dạng lưu trữ, không khởi động lại bằng binary của phiên bản cũ trên cùng data directory như một cách rollback. Phiên bản cũ có thể không hiểu metadata hoặc định dạng file đã được phiên bản mới cập nhật, dẫn tới lỗi khởi động hoặc nguy cơ hỏng dữ liệu.

Quy tắc vận hành an toàn:

- Không dùng chung một data directory cho hai instance MySQL khác phiên bản.
- Không chép file nội bộ từ data directory của phiên bản mới vào phiên bản cũ.
- Không khôi phục một bản backup vật lý vào phiên bản không nằm trong ma trận tương thích của công cụ backup.
- Không giả định data directory có thể được hạ cấp chỉ bằng cách cài binary cũ.

Nếu cần quay lại phiên bản cũ, hãy dùng một phương án downgrade được hỗ trợ rõ ràng cho đúng cặp phiên bản, hoặc dựng instance mới ở phiên bản cũ rồi phục hồi bằng logical dump có schema và dữ liệu tương thích. Việc logical restore cũng cần kiểm tra kiểu dữ liệu, collation, reserved word và tính năng không tồn tại ở phiên bản cũ.

### 5.2. Khác biệt MySQL 5.7 và 8.0

Khi chuyển từ 5.7 sang 8.0, server phải chuyển metadata cũ sang data dictionary mới và nâng cấp system schema. Các file `.frm` không còn là nguồn metadata định nghĩa bảng như trước. Vì vậy:

- Không xóa `.frm` hoặc tự tạo lại file metadata để sửa lỗi.
- Không copy nguyên thư mục `mysql` từ 5.7 vào một instance 8.0 đã khởi tạo.
- Không dùng các script tự cập nhật system table theo cấu trúc 5.7 trên server 8.0.
- Dùng quy trình upgrade chính thức để server chuyển đổi metadata và system schema.

Từ MySQL 8.0.16, server tự thực hiện các tác vụ nâng cấp trước đây do `mysql_upgrade` đảm nhiệm khi khởi động với data directory cần nâng cấp. `mysql_upgrade` đã bị deprecated; không xây dựng quy trình mới dựa trên việc chạy utility này như bước bắt buộc sau mỗi lần khởi động. Hãy đọc release notes của phiên bản đích để biết các thay đổi upgrade cụ thể.

### 5.3. Các thuộc tính cần tương thích

| Thuộc tính | Vì sao quan trọng |
|---|---|
| Phiên bản MySQL và định dạng data dictionary | Server phải hiểu định dạng metadata và quy trình upgrade của data directory |
| `innodb_page_size` | Page size gắn với cấu trúc tablespace; không thể tùy tiện đổi khi dùng lại dữ liệu vật lý |
| `lower_case_table_names` | Ảnh hưởng cách lưu và so sánh tên database/table; phải chọn đúng khi khởi tạo target và phù hợp source |
| `innodb_data_file_path` và system tablespace | Xác định bố cục và kích thước file dữ liệu hệ thống |
| Tablespace file-per-table | File `.ibd` cần metadata tương ứng và quy trình import tablespace được hỗ trợ |
| Character set và collation | Có thể làm thay đổi so sánh chuỗi, index, sort và kết quả truy vấn |
| Plugin/component và authentication plugin | Server mới có thể không có plugin cũ hoặc cấu hình xác thực tương ứng |
| Binary log/redo/undo format | Phải tương thích với phiên bản server và công cụ phục hồi/replication |
| `server_uuid` và `server_id` | Cần định danh duy nhất trong topology replication sau clone hoặc restore |

Đặc biệt, `lower_case_table_names` phải được thiết lập đúng khi khởi tạo data directory. Không đổi biến này trên một data directory đã có dữ liệu để cố khắc phục khác biệt chữ hoa/chữ thường giữa Windows, Linux và các hệ điều hành khác.

## 6. Di chuyển vật lý và logical migration

Có hai hướng phổ biến để chuyển dữ liệu sang instance khác. Chọn cách nào phụ thuộc yêu cầu downtime, kích thước dữ liệu, phiên bản và mức tương thích.

### 6.1. Physical backup/restore

Physical backup giữ lại file dữ liệu ở dạng vật lý. Cách này thường phù hợp khi cần phục hồi nhanh hoặc chuyển một instance lớn mà công cụ backup hỗ trợ phiên bản và cấu hình tương ứng.

Các điểm cần kiểm tra:

- Backup phải nhất quán theo cơ chế của công cụ; không tự copy file khi server đang chạy.
- Phiên bản MySQL và phiên bản công cụ backup phải nằm trong ma trận tương thích.
- Các file tablespace, redo/undo, data dictionary và cấu hình liên quan phải được xử lý cùng nhau.
- Target phải có cấu hình tương thích, quyền filesystem và dung lượng đủ.
- Nếu clone sang một node replication mới, xác minh `server_uuid` và `server_id` không bị trùng.

Physical backup thường không phải lựa chọn để chuyển trực tiếp giữa các major version bất kỳ. Khi công cụ không hỗ trợ cặp phiên bản, dùng đường upgrade được hỗ trợ hoặc logical migration.

### 6.2. Logical dump/restore

Logical migration xuất cấu trúc và dữ liệu thành các câu lệnh SQL hoặc định dạng dump logic, rồi nạp vào instance mới. Ví dụ với `mysqldump`:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --databases app \
  > app_dump.sql
```

`--single-transaction` tạo snapshot nhất quán cho các bảng transactional như InnoDB trong điều kiện phù hợp; nó không bảo đảm snapshot nhất quán cho bảng nontransactional và không ngăn DDL đồng thời làm ảnh hưởng quá trình dump. Với dữ liệu rất lớn, MySQL Shell dump/load utilities có thể hỗ trợ song song và theo chunk; hãy chọn công cụ phù hợp với phiên bản nguồn/đích.

Logical migration giúp server mới tạo lại metadata theo data dictionary của phiên bản đích thay vì mang theo file nội bộ của phiên bản nguồn. Tuy nhiên, cần kiểm tra các đối tượng và tính năng SQL không tương thích, tài khoản, role, event, routine, charset, collation và thứ tự tạo phụ thuộc.

### 6.3. Không dump/restore system schema như database nghiệp vụ

Không nên dump toàn bộ schema `mysql` từ một phiên bản rồi nạp nguyên xi vào phiên bản khác. System table có cấu trúc và cách quản lý thay đổi theo release. Tài khoản, role và quyền cần được xuất/tạo lại bằng giao diện SQL được hỗ trợ, còn metadata nội bộ phải do server đích quản lý.

Với ứng dụng, dump các schema nghiệp vụ cùng routine, trigger, event và view cần thiết. Với tài khoản, tạo lại account và grants theo chính sách bảo mật. Với cấu hình server, quản lý file cấu hình riêng và rà soát từng biến trên phiên bản đích.

## 7. Quy trình nâng cấp an toàn

Nâng cấp MySQL là thay đổi cả binary, system schema, data dictionary và đôi khi cả định dạng dữ liệu. Cần chuẩn bị trước và xác minh sau khi server mới khởi động.

### 7.1. Trước khi nâng cấp

1. Ghi lại phiên bản hiện tại, edition, plugin/component, engine, cấu hình và topology replication.
2. Xác nhận đường nâng cấp được MySQL hỗ trợ từ đúng phiên bản nguồn tới phiên bản đích.
3. Chạy công cụ kiểm tra tương thích phù hợp, chẳng hạn MySQL Shell Upgrade Checker, và xử lý cảnh báo về cú pháp, kiểu dữ liệu, collation, reserved word, plugin hoặc system table.
4. Kiểm tra dung lượng data directory, redo/undo, binary log, temporary directory và filesystem.
5. Tạo full backup và kiểm tra restore trên môi trường độc lập.
6. Lưu định nghĩa schema, tài khoản/role/grants, cấu hình server và thông tin replication cần thiết.
7. Thử toàn bộ quy trình trên bản sao có dữ liệu và workload gần production.
8. Chuẩn bị thời gian dừng ghi, cách chuyển traffic, người chịu trách nhiệm và tiêu chí rollback.

Không bắt đầu nâng cấp production chỉ dựa trên việc server mới có thể cài đặt thành công. Cần xác nhận ứng dụng, driver, connector, backup tool, monitoring và quy trình vận hành tương thích.

### 7.2. Trong khi nâng cấp

- Dừng hoặc điều phối ghi theo kế hoạch; tránh có migration schema đồng thời.
- Tạo backup cuối cùng hoặc checkpoint đã được xác minh.
- Dừng MySQL theo quy trình sạch nếu đường nâng cấp yêu cầu.
- Cài binary mới và giữ nguyên data directory theo hướng dẫn upgrade chính thức.
- Khởi động server mới với cấu hình tương thích để server thực hiện upgrade metadata/system schema.
- Theo dõi error log trong toàn bộ giai đoạn upgrade; không khởi động lại bằng binary cũ nếu quá trình đã chuyển đổi metadata.
- Chỉ mở traffic khi server hoàn tất upgrade và kiểm tra hệ thống đạt yêu cầu.

Không xóa backup, log hoặc bản cài cũ cho đến khi đã xác nhận hệ thống ổn định và chính sách lưu giữ cho phép.

### 7.3. Sau khi nâng cấp

Kiểm tra phiên bản và đường dẫn data directory:

```sql
SELECT VERSION();
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'lower_case_table_names';
```

Tiếp tục xác minh:

- Error log không còn lỗi upgrade hoặc lỗi mở tablespace.
- Database, table, view, routine, trigger, event và index tồn tại đúng.
- Tài khoản, authentication plugin, role và grants hoạt động.
- Character set, collation, SQL mode và system variable có giá trị dự kiến.
- Replication, GTID, binary log và backup tiếp tục hoạt động.
- Truy vấn quan trọng cho kết quả đúng và execution plan không suy giảm ngoài dự kiến.
- Ứng dụng, connector, monitoring và job nền kết nối thành công.
- Có backup mới sau upgrade và đã thử phục hồi theo quy trình.

Không coi việc `mysqld` khởi động thành công là bằng chứng đủ rằng mọi đối tượng và workload đã tương thích.

## 8. Điều tra lỗi data dictionary hoặc system table

Một số dấu hiệu cho thấy vấn đề liên quan metadata hoặc tương thích data directory:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Server báo data dictionary version không tương thích | Dùng binary không phù hợp với data directory hoặc upgrade chưa hoàn tất | Dùng đúng phiên bản theo quy trình upgrade; đọc error log và không thử binary cũ tùy tiện |
| Bảng không mở được sau khi copy file | Thiếu metadata, tablespace không đồng bộ hoặc copy không nhất quán | Khôi phục từ backup nhất quán hoặc dùng quy trình import tablespace được hỗ trợ |
| Thiếu system table/cột sau nâng cấp | System schema upgrade chưa hoàn tất hoặc upgrade bị lỗi | Kiểm tra error log và quy trình upgrade của release; không tự thêm cột vào system table |
| Tài khoản không đăng nhập được | Authentication plugin, hash, role hoặc grant khác phiên bản | Kiểm tra `SHOW CREATE USER`, `SHOW GRANTS`, plugin có sẵn và chính sách xác thực |
| Tên bảng khác nhau giữa hệ điều hành | `lower_case_table_names` hoặc quy tắc filesystem khác | Kiểm tra cấu hình lúc khởi tạo và lập kế hoạch chuyển đổi tên rõ ràng |
| Không import được tablespace `.ibd` | Page size, schema, tablespace metadata hoặc phiên bản không tương thích | Dùng quy trình transportable tablespace chính thức hoặc logical restore |

### 8.1. Import tablespace không phải là copy file tùy ý

InnoDB hỗ trợ transportable tablespace trong các điều kiện cụ thể. Quy trình thường gồm chuẩn bị bảng tương thích ở target, export tablespace trên source bằng `FLUSH TABLES ... FOR EXPORT`, copy file theo hướng dẫn, rồi dùng `ALTER TABLE ... DISCARD TABLESPACE` và `IMPORT TABLESPACE` ở target. Chi tiết phụ thuộc bảng, phiên bản, encryption, page size và các thuộc tính tablespace.

Ví dụ minh họa một phần quy trình:

```sql
-- Trên source: chuẩn bị bảng để export
FLUSH TABLES app.orders FOR EXPORT;

-- Sau khi copy file theo hướng dẫn và đóng trạng thái export:
UNLOCK TABLES;

-- Trên target: bảng đã được tạo với định nghĩa tương thích
ALTER TABLE app.orders DISCARD TABLESPACE;
-- Copy file tablespace vào đúng vị trí theo hướng dẫn của MySQL
ALTER TABLE app.orders IMPORT TABLESPACE;
```

Đây chỉ là sơ đồ khái niệm, không phải quy trình hoàn chỉnh để chạy nguyên văn. Việc export có thể tạo file metadata phụ và yêu cầu copy trong lúc bảng đang ở trạng thái export. Cần làm theo tài liệu transportable tablespace của đúng phiên bản, kiểm tra checksum và xác minh constraint/index sau import.

## 9. Những điều không nên làm

- **Không sửa trực tiếp system table:** dùng `CREATE USER`, `ALTER USER`, `GRANT`, `REVOKE` và DDL được hỗ trợ.
- **Không xóa file `.frm` hoặc metadata cũ bằng tay:** để quy trình upgrade và server quản lý metadata.
- **Không copy riêng thư mục `mysql` giữa major version:** system schema có cấu trúc riêng theo release.
- **Không mở data directory của phiên bản mới bằng binary cũ:** đây không phải chiến lược downgrade an toàn.
- **Không copy data directory đang hoạt động bằng file manager:** dùng physical backup nhất quán hoặc cơ chế snapshot được hỗ trợ.
- **Không coi `INFORMATION_SCHEMA` là thư mục file vật lý:** đây là giao diện truy vấn metadata.
- **Không dùng `performance_schema` làm nơi lưu metadata lâu dài:** nó phản ánh instrumentation runtime.
- **Không giả định file `.ibd` độc lập với data dictionary:** cần metadata và quy trình tablespace tương ứng.
- **Không khởi tạo target với `lower_case_table_names` hoặc `innodb_page_size` không phù hợp:** các thuộc tính này ảnh hưởng khả năng dùng lại dữ liệu vật lý.
- **Không xóa backup ngay sau khi upgrade:** chỉ dọn khi đã kiểm tra ứng dụng, dữ liệu, replication và khả năng restore.

## 10. Bài thực hành

Một hệ thống đang chạy MySQL 5.7 trên Linux, dùng InnoDB file-per-table và có nhiều database nghiệp vụ. Nhóm vận hành cần chuyển sang MySQL 8.0 trên máy chủ mới. Hệ thống có stored procedure, trigger, event, tài khoản ứng dụng riêng và một số replica.

Hãy lập kế hoạch nâng cấp và trả lời:

1. Data dictionary của MySQL 5.7 khác gì so với kiến trúc transactional DD của MySQL 8.0?
2. Vì sao không thể chỉ copy các file `.ibd` và thư mục `mysql` sang server mới rồi khởi động?
3. Bạn sẽ dùng `INFORMATION_SCHEMA`, `SHOW CREATE TABLE` và các công cụ nào để thu thập metadata trước nâng cấp?
4. Những thuộc tính nào như `lower_case_table_names`, `innodb_page_size`, charset/collation và plugin cần được kiểm tra trên target?
5. Khi nào chọn physical backup/restore và khi nào chọn logical dump/restore? Nêu yêu cầu tương thích của từng cách.
6. Vì sao không nên dump toàn bộ system schema từ 5.7 rồi nạp nguyên xi vào 8.0?
7. MySQL 8.0.16 trở lên xử lý các tác vụ trước đây của `mysql_upgrade` như thế nào?
8. Hãy mô tả backup, kiểm tra restore, upgrade, kiểm tra error log và xác minh ứng dụng sau nâng cấp.
9. Nếu cần rollback về 5.7 sau khi data dictionary đã được nâng cấp, bạn sẽ phục hồi theo hướng nào?
10. Nếu chỉ cần chuyển một bảng InnoDB sang instance khác, khi nào transportable tablespace phù hợp và vì sao không thể copy `.ibd` tùy ý?

Một kế hoạch tốt phải nêu rõ phiên bản nguồn/đích, đường nâng cấp được hỗ trợ, loại backup, thuộc tính target, bước kiểm tra tương thích, tiêu chí mở traffic và phương án phục hồi đã diễn tập.

## Kết luận

Data dictionary là nguồn metadata cốt lõi để MySQL hiểu cấu trúc và quan hệ giữa các đối tượng. MySQL 8.0 chuyển metadata sang kiến trúc transactional dựa trên InnoDB; `INFORMATION_SCHEMA`, `SHOW`, `mysql`, `performance_schema` và `sys` cung cấp các giao diện với mục đích khác nhau. Data directory chứa các file dữ liệu, metadata và log có quan hệ chặt chẽ, nên không thể ghép hoặc mở tùy ý giữa các phiên bản. Hãy dùng quy trình upgrade chính thức, backup có thể restore, kiểm tra tương thích trước và xác minh schema, tài khoản, replication cùng ứng dụng sau khi nâng cấp.
