# Chạy câu lệnh, script SQL và ghi lại kết quả thực hành

Khi học và vận hành MySQL, một câu lệnh chạy thành công trong SQL Editor mới chỉ là một phần của công việc. Bạn còn cần biết mình đang kết nối tới máy chủ nào, đang dùng tài khoản và cơ sở dữ liệu nào, câu lệnh nào thực sự được gửi đi, kết quả trả về ra sao, và làm thế nào để người khác có thể chạy lại đúng quy trình đó.

Bài học này thuộc phạm vi `DATABASE_MYSQL`: thực hành truy vấn, thao tác dữ liệu, transaction, phân quyền và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là hình thành quy trình làm việc có thể lặp lại: **kết nối đúng môi trường → chạy câu lệnh hoặc script → kiểm tra kết quả → ghi lại bằng chứng → có thể tái hiện lần chạy**.

## 1. Các cách làm việc với MySQL

Ứng dụng client gửi câu lệnh SQL tới MySQL Server thông qua một kết nối. Server kiểm tra quyền, thực thi câu lệnh và trả về dữ liệu hoặc thông tin trạng thái. Công cụ client hiển thị kết quả, lưu lịch sử hoặc ghi log theo khả năng của nó.

Một số công cụ thường dùng:

| Công cụ | Cách sử dụng | Phù hợp khi |
|---|---|---|
| MySQL Command-Line Client (`mysql`) | Gõ SQL trực tiếp trong terminal hoặc chạy file SQL | Học cú pháp, tự động hóa, chạy script, kiểm tra nhanh |
| MySQL Workbench | Kết nối bằng giao diện, viết SQL trong tab Editor, xem kết quả ở grid | Học tập, phát triển, quản trị và trực quan hóa schema |
| MySQL Shell (`mysqlsh`) | Làm việc ở chế độ SQL, JavaScript hoặc Python | Quản trị và tự động hóa nâng cao; thực hiện các thao tác bằng nhiều ngôn ngữ |
| DBeaver và các SQL IDE khác | Quản lý nhiều kết nối, viết SQL, xem dữ liệu và xuất kết quả | Làm việc với nhiều hệ quản trị hoặc cần công cụ giao diện tổng quát |
| Ứng dụng và thư viện kết nối | Gửi câu lệnh qua JDBC, Connector/Python, Node.js connector và các driver khác | Tích hợp SQL vào chương trình, dịch vụ và quy trình kiểm thử |

Dù giao diện khác nhau, các công cụ đều cần thông tin kết nối và chịu sự kiểm soát quyền của MySQL Server. Một tài khoản chỉ có quyền đọc không thể tự nhiên chạy được lệnh `UPDATE` chỉ vì bạn sử dụng Workbench thay cho terminal.

Cần phân biệt ba loại lệnh:

- **SQL gửi đến server:** `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`, `GRANT`...
- **Lệnh riêng của client:** `source`, `tee`, `status`, `delimiter`, `quit` trong MySQL Command-Line Client. Server không nhận chúng như câu lệnh SQL thông thường.
- **Lệnh của hệ điều hành:** chạy chương trình `mysql.exe`, chuyển hướng đầu vào/đầu ra, tạo thư mục log hoặc gọi script từ terminal.

Hiểu đúng loại lệnh giúp tránh gửi nhầm một lệnh dành cho client vào SQL Editor hoặc đưa câu lệnh SQL vào shell của hệ điều hành.

## 2. Chuẩn bị thông tin kết nối

Trước khi mở client, cần có các thông tin do người quản trị hoặc môi trường phát triển cung cấp:

| Thông tin | Ví dụ | Ý nghĩa |
|---|---|---|
| Host | `127.0.0.1`, `db-dev.example.net` | Máy chủ MySQL cần kết nối |
| Port | `3306` | Cổng TCP của MySQL; có thể đã được thay đổi |
| User | `lab_user` | Tài khoản MySQL dùng để xác thực |
| Password | Nhập tại dấu nhắc | Bí mật xác thực của tài khoản |
| Database | `mysql_practice` | Schema mặc định sau khi kết nối |
| TLS/CA | CA certificate và chế độ xác minh | Bảo vệ và xác minh kết nối tới máy chủ |

Không nên đoán host, port, database hoặc tài khoản từ tên project. Môi trường local, development, staging và production có thể có cấu hình khác nhau. Trước khi chạy câu lệnh thay đổi dữ liệu, hãy xác nhận rõ môi trường đích.

### 2.1. Kết nối bằng MySQL Command-Line Client

Ví dụ kết nối tới MySQL chạy trên máy local:

~~~bash
mysql --host=127.0.0.1 --port=3306 --user=lab_user --password --database=mysql_practice --default-character-set=utf8mb4
~~~

Tùy chọn `--password` không có giá trị phía sau khiến client hỏi mật khẩu tương tác. Không nên ghi mật khẩu trực tiếp trong câu lệnh như `--password=my-secret`: mật khẩu có thể xuất hiện trong lịch sử shell, log hoặc danh sách tiến trình.

Nếu chưa có database mặc định, bỏ `--database=mysql_practice`, sau đó chọn database trong phiên làm việc:

~~~sql
USE mysql_practice;
~~~

Khi kết nối tới máy chủ production hoặc qua mạng không tin cậy, cần cấu hình TLS theo chứng chỉ và hướng dẫn của nhà cung cấp. Ví dụ với CA certificate đã được cấp:

~~~bash
mysql --host=db.example.net --port=3306 --user=app_reader --password --ssl-mode=VERIFY_IDENTITY --ssl-ca=/path/to/ca.pem --default-character-set=utf8mb4
~~~

`VERIFY_IDENTITY` yêu cầu xác minh chứng chỉ và danh tính host. Tên host phải phù hợp với chứng chỉ. Đường dẫn CA ở ví dụ cần thay bằng đường dẫn thực tế. Không tắt xác minh TLS chỉ để làm cho kết nối hết lỗi; hãy kiểm tra CA, tên host, thời hạn chứng chỉ và cấu hình máy chủ.

### 2.2. Lưu thông tin đăng nhập thuận tiện hơn

MySQL cung cấp `mysql_config_editor` để tạo login path cho Command-Line Client:

~~~bash
mysql_config_editor set --login-path=practice --host=127.0.0.1 --user=lab_user --port=3306 --password
~~~

Chương trình hỏi mật khẩu và lưu thông tin đăng nhập trong file cấu hình riêng của người dùng. Sau đó có thể kết nối bằng:

~~~bash
mysql --login-path=practice --database=mysql_practice
~~~

Login path giúp tránh phải gõ mật khẩu vào dòng lệnh mỗi lần. Tuy nhiên, thông tin trong file login path được làm rối (obfuscate), không phải một kho bí mật mã hóa mạnh. Cần bảo vệ file bằng quyền truy cập hệ điều hành phù hợp và không chia sẻ file đó cho người khác.

Trong ứng dụng thực tế, nên dùng secret manager hoặc cơ chế quản lý bí mật của môi trường triển khai. Không đưa password, token, private key hay file cấu hình chứa bí mật vào Git.

### 2.3. Xác minh đúng máy chủ và tài khoản

Ngay sau khi kết nối, hãy chạy một truy vấn nhận diện môi trường:

~~~sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    DATABASE() AS current_database,
    USER() AS client_identity,
    CURRENT_USER() AS privilege_identity,
    @@autocommit AS autocommit_mode,
    @@sql_mode AS sql_mode;
~~~

Các giá trị có ý nghĩa khác nhau:

- `VERSION()` cho biết phiên bản MySQL mà kết nối đang sử dụng.
- `@@version_comment` mô tả bản phân phối hoặc sản phẩm engine.
- `@@hostname` và `@@port` giúp nhận diện máy chủ theo thông tin server công bố.
- `DATABASE()` cho biết database mặc định hiện tại; kết quả có thể là `NULL` nếu chưa chọn database.
- `USER()` thể hiện danh tính client gửi tới server.
- `CURRENT_USER()` thể hiện tài khoản mà MySQL dùng để kiểm tra quyền.
- `@@autocommit` và `@@sql_mode` cho biết hai thiết lập ảnh hưởng trực tiếp đến cách câu lệnh hoạt động.

Đừng chỉ nhìn tên tab hoặc tên connection profile. Hãy xác minh bằng truy vấn, đặc biệt trước các thao tác `DROP`, `TRUNCATE`, `DELETE`, `UPDATE`, migration hoặc thay đổi cấu trúc.

## 3. Chạy câu lệnh tương tác

Sau khi kết nối bằng `mysql`, bạn có thể nhập SQL trực tiếp:

~~~sql
SELECT DATABASE();

SHOW TABLES;

SELECT VERSION();
~~~

Trong MySQL Command-Line Client, câu lệnh SQL thường kết thúc bằng dấu chấm phẩy (`;`). Khi nhấn Enter mà câu lệnh chưa kết thúc, client tiếp tục chờ phần còn lại. Dấu chấm phẩy là dấu kết thúc câu lệnh trong chế độ thông thường; không phải cứ xuống dòng là server thực thi.

Một số lệnh client hữu ích:

| Lệnh client | Tác dụng |
|---|---|
| `status` hoặc `\s` | Hiển thị trạng thái kết nối và thông tin phiên |
| `source file.sql` hoặc `\. file.sql` | Đọc và chạy lệnh từ file |
| `tee file.log` | Ghi bản sao đầu ra của client vào file |
| `notee` | Dừng ghi đầu ra bằng `tee` |
| `delimiter //` | Đổi dấu kết thúc câu lệnh mà client nhận diện |
| `warnings` | Hiển thị cảnh báo sau câu lệnh |
| `nowarning` | Tắt chế độ tự hiển thị cảnh báo |
| `clear` hoặc `\c` | Hủy phần câu lệnh đang nhập dở |
| `quit` hoặc `\q` | Thoát client |

Đây là lệnh của MySQL Command-Line Client. Một số IDE có chức năng tương tự nhưng tên menu và cách thao tác khác nhau.

### 3.1. Chạy một câu lệnh từ terminal

Tùy chọn `--execute` (viết tắt `-e`) cho phép gửi câu lệnh rồi thoát:

~~~bash
mysql --login-path=practice --database=mysql_practice --execute="SELECT CURRENT_TIMESTAMP AS checked_at, DATABASE() AS db_name;"
~~~

Có thể chạy nhiều câu lệnh trong cùng một chuỗi, phân tách bằng dấu chấm phẩy:

~~~bash
mysql --login-path=practice --database=mysql_practice --execute="SHOW TABLES; SELECT COUNT(*) AS total_tables FROM information_schema.tables WHERE table_schema = DATABASE();"
~~~

Cách này phù hợp với kiểm tra nhanh hoặc một bước nhỏ trong script tự động. Với quy trình nhiều câu lệnh, file SQL thường dễ đọc, review và lưu phiên bản hơn.

### 3.2. Chạy câu lệnh đang chọn trong SQL Editor

Trong MySQL Workbench hoặc DBeaver:

1. Mở connection profile và xác minh host, database, user.
2. Mở SQL Editor gắn với kết nối đó.
3. Viết một hoặc nhiều câu lệnh SQL.
4. Chọn câu lệnh cần chạy hoặc đặt con trỏ trong câu lệnh theo cách công cụ hỗ trợ.
5. Dùng chức năng Execute để gửi câu lệnh tới server.
6. Đọc vùng kết quả, thông báo lỗi, thời gian chạy và số dòng bị ảnh hưởng.

Cần phân biệt nút chạy câu lệnh hiện tại, chạy phần đang chọn và chạy toàn bộ nội dung editor. Nếu editor có nhiều câu lệnh, chọn nhầm chế độ chạy có thể làm thực thi nhiều thao tác hơn dự kiến.

Workbench thường hiển thị kết quả truy vấn dạng grid, thông báo trạng thái và lịch sử câu lệnh. DBeaver cũng cung cấp các tab kết quả và chức năng xuất dữ liệu. Tên menu hoặc phím tắt có thể thay đổi theo phiên bản; hãy xác nhận vùng SQL được chọn trước khi thực thi.

## 4. Tổ chức câu lệnh thành file SQL

Một file `.sql` giúp lưu lại chuỗi thao tác để có thể review, chạy lại, đưa vào Git hoặc chuyển cho thành viên khác.

Ví dụ cấu trúc thư mục thực hành:

~~~text
mysql-practice/
├── sql/
│   ├── 00-check-connection.sql
│   ├── 01-create-schema.sql
│   ├── 02-seed-data.sql
│   └── 03-verify-result.sql
├── logs/
│   └── .gitkeep
└── README.md
~~~

Có thể chia file theo mục đích:

- File kiểm tra môi trường và quyền.
- File tạo schema, bảng, index và ràng buộc.
- File dữ liệu mẫu.
- File truy vấn thực hành.
- File xác minh kết quả.
- File migration hoặc rollback tương ứng khi dự án có quy trình migration.

Không cần tách mọi câu lệnh thành một file riêng. Hãy nhóm theo một mục đích có thể review và chạy độc lập.

### 4.1. Ví dụ file kiểm tra kết nối

Nội dung của `00-check-connection.sql`:

~~~sql
-- Xác nhận kết nối trước khi chạy các thao tác thay đổi dữ liệu.
SELECT
    CURRENT_TIMESTAMP AS checked_at,
    VERSION() AS server_version,
    DATABASE() AS database_name,
    CURRENT_USER() AS privilege_identity;

SHOW ENGINES;
SHOW GRANTS;
~~~

Chạy file trong phiên `mysql`:

~~~text
source C:/lab/mysql-practice/sql/00-check-connection.sql
~~~

Dùng dấu gạch chéo xuôi trong đường dẫn thường thuận tiện với MySQL client trên Windows. Thay đường dẫn bằng vị trí file thật trên máy của bạn.

### 4.2. Ví dụ một script có thể chạy lại

Tạo file `01-practice.sql` với nội dung:

~~~sql
-- Lưu file bằng UTF-8 để giữ nguyên dữ liệu tiếng Việt.
CREATE DATABASE IF NOT EXISTS mysql_practice;
USE mysql_practice;

CREATE TABLE IF NOT EXISTS practice_item (
    item_id INT UNSIGNED NOT NULL,
    item_name VARCHAR(100) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;

-- Đưa dữ liệu về trạng thái ban đầu để có thể chạy lại bài thực hành.
INSERT INTO practice_item (item_id, item_name, quantity)
VALUES (1, 'Bàn phím', 10)
ON DUPLICATE KEY UPDATE
    item_name = 'Bàn phím',
    quantity = 10;

-- Thử một thay đổi trong transaction rồi hoàn tác.
START TRANSACTION;

UPDATE practice_item
SET quantity = quantity - 1
WHERE item_id = 1 AND quantity > 0;

SELECT ROW_COUNT() AS affected_rows;

SELECT item_id, item_name, quantity
FROM practice_item
WHERE item_id = 1;

ROLLBACK;

-- Xác nhận dữ liệu sau ROLLBACK vẫn ở trạng thái ban đầu.
SELECT item_id, item_name, quantity, updated_at
FROM practice_item
ORDER BY item_id;
~~~

Script minh họa một số điểm:

- `CREATE DATABASE IF NOT EXISTS` và `CREATE TABLE IF NOT EXISTS` tránh lỗi tạo mới khi đối tượng đã tồn tại.
- Câu lệnh `INSERT ... ON DUPLICATE KEY UPDATE` đưa dòng mẫu về giá trị xác định, giúp chạy lại bài thực hành có kết quả ổn định.
- `START TRANSACTION` mở transaction cho thao tác dữ liệu.
- `ROW_COUNT()` trả về số dòng bị ảnh hưởng bởi câu lệnh ngay trước đó.
- `ROLLBACK` hoàn tác thay đổi dữ liệu trong transaction.
- Truy vấn cuối cùng cho thấy số lượng vẫn bằng 10.

Lưu ý: tạo database và tạo bảng là các thao tác DDL. Trong MySQL, nhiều câu lệnh DDL gây implicit commit, vì vậy không nên nghĩ rằng đặt toàn bộ file vào `START TRANSACTION` sẽ làm mọi thao tác cấu trúc có thể rollback. Ví dụ trên tạo database/bảng trước rồi mới mở transaction cho thao tác dữ liệu.

Script cần quyền tạo database và table. Nếu tài khoản thực hành không có các quyền đó, người quản trị có thể tạo sẵn schema/bảng và cấp quyền cần thiết; khi đó bỏ các lệnh tạo đối tượng khỏi file.

### 4.3. Chạy file bằng lệnh source

Kết nối vào database:

~~~bash
mysql --login-path=practice --database=mysql_practice
~~~

Sau đó chạy trong MySQL client:

~~~text
source C:/lab/mysql-practice/sql/01-practice.sql
~~~

Client đọc nội dung file và thực thi lần lượt. Nếu có lỗi, đọc thông báo lỗi cùng số dòng để xác định câu lệnh gây lỗi. Sau khi sửa file, chạy lại và kiểm tra trạng thái dữ liệu.

### 4.4. Chạy file qua chuyển hướng đầu vào

Trong Windows Command Prompt, Git Bash hoặc shell kiểu Unix, có thể chuyển nội dung file vào stdin của client:

~~~bash
mysql --login-path=practice --database=mysql_practice --table --verbose --show-warnings < C:/lab/mysql-practice/sql/01-practice.sql
~~~

Ý nghĩa:

- `--table` trình bày kết quả dạng bảng.
- `--verbose` hiển thị câu lệnh mà client thực thi, hữu ích khi ghi log.
- `--show-warnings` hiển thị cảnh báo sau câu lệnh khi có.
- Dấu `<` chuyển nội dung file làm đầu vào cho client.

Nếu muốn ghi cả stdout và stderr vào log trong CMD hoặc shell tương thích:

~~~bash
mysql --login-path=practice --database=mysql_practice --table --verbose --show-warnings < C:/lab/mysql-practice/sql/01-practice.sql > C:/lab/mysql-practice/logs/run-01.log 2>&1
~~~

PowerShell có quy tắc chuyển hướng và xử lý tiến trình native riêng. Nếu dùng PowerShell, bạn có thể mở MySQL client rồi chạy `source`, hoặc gọi cú pháp chuyển hướng trong `cmd.exe`/Git Bash. Tránh dùng một lệnh chuyển hướng chưa kiểm chứng cho quy trình production.

## 5. Chạy script có procedure, function hoặc trigger

Các routine thường chứa nhiều dấu chấm phẩy bên trong thân lệnh. Nếu client coi dấu chấm phẩy đầu tiên là kết thúc câu lệnh, phần còn lại sẽ bị gửi sai hoặc báo lỗi cú pháp.

MySQL Command-Line Client có lệnh `DELIMITER` để đổi dấu kết thúc mà client nhận diện. Ví dụ:

~~~sql
DELIMITER //

CREATE PROCEDURE show_practice_time()
BEGIN
    SELECT CURRENT_TIMESTAMP AS practice_time;
    SELECT DATABASE() AS database_name;
END//

DELIMITER ;
~~~

Trong ví dụ này:

- `DELIMITER //` yêu cầu client chờ tới `//` mới gửi toàn bộ định nghĩa procedure.
- Các dấu chấm phẩy bên trong `BEGIN ... END` vẫn được giữ như dấu kết thúc câu lệnh SQL bên trong routine.
- `DELIMITER ;` đưa client về dấu kết thúc mặc định.

`DELIMITER` là chỉ thị của client, không phải câu lệnh SQL gửi tới MySQL Server. Vì vậy, khi chạy script qua một thư viện JDBC hoặc driver trong ứng dụng, không thể mặc định gửi nguyên văn chỉ thị `DELIMITER` cho server. Chương trình cần gửi định nghĩa routine như một câu lệnh phù hợp với API/driver.

Workbench cũng hỗ trợ delimiter trong SQL script. Với các công cụ khác, hãy kiểm tra cách chúng phân tích routine và câu lệnh nhiều dòng trước khi chạy.

## 6. Chọn định dạng kết quả và ghi log

Kết quả cần được lưu theo mục đích sử dụng. Log dành cho người đọc cần dễ hiểu; dữ liệu dành cho chương trình xử lý cần có cấu trúc ổn định.

### 6.1. Kết quả dễ đọc trong terminal

Mặc định, MySQL client thường hiển thị kết quả truy vấn dạng bảng. Có thể yêu cầu định dạng bảng rõ ràng bằng `--table`:

~~~bash
mysql --login-path=practice --database=mysql_practice --table --execute="SELECT item_id, item_name, quantity FROM practice_item ORDER BY item_id;"
~~~

Định dạng này phù hợp để xem trực tiếp hoặc đính kèm log cho báo cáo thực hành.

### 6.2. Kết quả dạng batch cho xử lý tự động

Tùy chọn `--batch` xuất kết quả theo dạng phân tách bằng tab, phù hợp với một số script xử lý:

~~~bash
mysql --login-path=practice --database=mysql_practice --batch --skip-column-names --execute="SELECT item_id, item_name, quantity FROM practice_item ORDER BY item_id;"
~~~

`--skip-column-names` bỏ dòng tiêu đề. Tùy chọn `--raw` tắt một số cơ chế escape của output batch. Chỉ dùng khi chương trình nhận kết quả đã biết cách xử lý tab, xuống dòng và ký tự đặc biệt; không mặc định coi output này là CSV hợp lệ.

Nếu cần CSV hoặc XLSX để phân tích, hãy dùng chức năng export của Workbench/DBeaver hoặc một chương trình xuất dữ liệu có quy tắc quoting và encoding rõ ràng. Không đổi tên file TSV thành CSV rồi giả định các cột đã được escape đúng chuẩn CSV.

### 6.3. Ghi lại phiên làm việc bằng tee

Trong MySQL Command-Line Client:

~~~text
tee C:/lab/mysql-practice/logs/practice-session.log
source C:/lab/mysql-practice/sql/01-practice.sql
notee
~~~

Lệnh `tee` ghi bản sao đầu ra của client vào file. Dùng `notee` để dừng ghi. Có thể bật tee trước khi chạy script để giữ lại kết quả và thông báo trong phiên thực hành.

Log có thể chứa dữ liệu trả về từ truy vấn, tên bảng, thông tin môi trường hoặc giá trị nhạy cảm. Không ghi password vào câu lệnh, không đưa dữ liệu cá nhân hoặc bí mật vào log nếu không cần thiết, và kiểm tra log trước khi chia sẻ hoặc commit.

### 6.4. Xuất kết quả từ Workbench hoặc DBeaver

Khi truy vấn trả về một result grid:

1. Kiểm tra truy vấn có `ORDER BY` nếu thứ tự dòng có ý nghĩa.
2. Xem số dòng và các cột có đúng kỳ vọng không.
3. Dùng chức năng Export của công cụ để chọn CSV, JSON, SQL hoặc định dạng được hỗ trợ.
4. Chọn encoding phù hợp, thường là UTF-8.
5. Lưu file vào thư mục kết quả thực hành hoặc vị trí artifact đã thống nhất.
6. Mở lại file xuất để xác minh dấu tiếng Việt, dấu phân cách, tiêu đề cột và số dòng.

Không nên chỉ chụp ảnh màn hình khi cần đối chiếu dữ liệu nhiều dòng. Ảnh hữu ích để minh họa giao diện hoặc thông báo, còn file xuất có cấu trúc phù hợp hơn cho việc kiểm tra và phân tích.

## 7. Kiểm tra kết quả và xử lý lỗi

Một câu lệnh không báo lỗi chưa chắc đã đáp ứng yêu cầu nghiệp vụ. Sau khi chạy, cần kiểm tra dữ liệu và trạng thái thực tế.

### 7.1. Kiểm tra số dòng bị ảnh hưởng

Sau một lệnh `INSERT`, `UPDATE` hoặc `DELETE`, có thể xem số dòng bị ảnh hưởng bằng:

~~~sql
SELECT ROW_COUNT() AS affected_rows;
~~~

Hãy chạy ngay sau câu lệnh cần kiểm tra vì các câu lệnh tiếp theo có thể làm thay đổi ý nghĩa của thông tin trạng thái trước đó. Số dòng bị ảnh hưởng không phải lúc nào cũng bằng số dòng khớp điều kiện; ví dụ, `UPDATE` đặt giá trị về đúng giá trị cũ có thể không làm thay đổi dòng nào.

Đối với lệnh `INSERT` dùng cột tự tăng, có thể đọc giá trị sinh ra trong cùng kết nối:

~~~sql
SELECT LAST_INSERT_ID() AS generated_id;
~~~

Không dùng `LAST_INSERT_ID()` của một kết nối khác để suy ra ID của thao tác hiện tại.

### 7.2. Kiểm tra cảnh báo

Trong MySQL client, chạy ngay sau câu lệnh cần điều tra:

~~~sql
SHOW WARNINGS;
~~~

Có thể dùng `SHOW ERRORS` để xem lỗi gần nhất mà server ghi nhận. Các lệnh này giúp phân biệt trường hợp câu lệnh chạy nhưng có cảnh báo, chẳng hạn dữ liệu bị chuyển đổi hoặc bị cắt theo chế độ SQL hiện hành.

Không nên bỏ qua warning chỉ vì số dòng đã được ghi. Hãy kiểm tra nguyên nhân và xác định cảnh báo có chấp nhận được trong bài thực hành hay trong ứng dụng thật không.

### 7.3. Một số lỗi thường gặp

| Mã lỗi | Tình huống | Hướng kiểm tra |
|---|---|---|
| 1045 | Access denied | Kiểm tra user, password, host được phép kết nối và cơ chế xác thực |
| 1049 | Unknown database | Kiểm tra tên database và quyền nhìn thấy database |
| 1064 | Lỗi cú pháp SQL | Kiểm tra từ khóa, dấu phẩy, dấu nháy, delimiter và phiên bản cú pháp |
| 1146 | Table doesn't exist | Kiểm tra database hiện tại, tên bảng và thứ tự chạy script |
| 2003 | Không kết nối được server | Kiểm tra host, port, service MySQL, firewall và mạng |
| 1205 | Lock wait timeout | Điều tra transaction giữ khóa, thời gian chờ và thứ tự truy cập |
| 1213 | Deadlock | Kiểm tra transaction cạnh tranh; ứng dụng cần có chiến lược retry phù hợp |

Khi gặp lỗi:

1. Lưu nguyên văn thông báo lỗi và mã lỗi.
2. Xác định câu lệnh và dòng trong file đã gây lỗi.
3. Xác minh kết nối, database hiện tại và tài khoản.
4. Kiểm tra schema, quyền, kiểu dữ liệu, constraint và trạng thái transaction.
5. Sửa nguyên nhân rồi chạy lại phần cần thiết.
6. Xác minh dữ liệu sau khi sửa; nếu script có thể đã chạy một phần, không chạy lại mù quáng.

Trong các script chạy batch, mặc định nên để client dừng khi gặp lỗi để người vận hành nhận ra lần chạy chưa hoàn tất. Tùy chọn `--force` khiến client tiếp tục dù có SQL error; chỉ dùng khi đã có lý do rõ ràng và quy trình kiểm soát từng câu lệnh sau lỗi. Với migration hoặc script thay đổi dữ liệu, tiếp tục sau lỗi có thể tạo ra trạng thái dở dang khó khôi phục.

## 8. Quy trình thực hành có thể tái hiện

Một lần thực hành tốt cần cho biết đã chạy trên môi trường nào, dùng script nào và kết quả mong đợi là gì.

Quy trình đề xuất:

1. **Chuẩn bị:** lưu file SQL ở thư mục dự án, kiểm tra encoding UTF-8 và đọc lại nội dung trước khi chạy.
2. **Kết nối:** dùng profile đúng môi trường; xác minh server version, host, database và user.
3. **Kiểm tra quyền:** chạy `SHOW GRANTS` và xác định tài khoản có đủ quyền cần thiết.
4. **Chạy thử:** bắt đầu bằng truy vấn đọc hoặc thao tác trong schema thực hành riêng.
5. **Thực thi:** chạy câu lệnh hoặc file SQL; không chạy toàn bộ editor nếu chỉ cần một phần.
6. **Xác minh:** kiểm tra số dòng, dữ liệu sau thao tác, warning, trạng thái transaction và kết quả kỳ vọng.
7. **Ghi log:** lưu đầu ra, thông báo lỗi và thông tin lần chạy; loại bỏ bí mật và dữ liệu nhạy cảm.
8. **Đánh giá:** ghi rõ PASS/FAIL, nguyên nhân, cách khắc phục và bước tiếp theo.
9. **Dọn dẹp:** chỉ xóa dữ liệu hoặc schema thực hành khi chắc chắn đang ở đúng môi trường và không còn cần bằng chứng.

### 8.1. Mẫu ghi nhận một lần chạy

Có thể dùng mẫu Markdown sau trong README hoặc sổ tay thực hành:

~~~markdown
## Lần chạy: SQL Practice 01

- Thời gian:
- Người thực hiện:
- Môi trường: local / development / staging
- MySQL server version:
- Host và port (không ghi thông tin bí mật):
- Database:
- Tài khoản/role:
- Client và phiên bản:
- Script:
- Git commit hoặc phiên bản script:
- Mục tiêu:
- Kết quả mong đợi:
- Kết quả thực tế:
- Số dòng bị ảnh hưởng:
- Warning/error:
- Log hoặc file kết quả:
- Trạng thái: PASS / FAIL
- Ghi chú và bước tiếp theo:
~~~

Không ghi password, access token, private key hoặc nội dung secret vào mẫu. Nếu cần chia sẻ log, hãy che dữ liệu nhạy cảm và xác nhận người nhận được phép xem dữ liệu đó.

### 8.2. Vì sao cần ORDER BY khi lưu kết quả?

SQL không đảm bảo thứ tự dòng nếu truy vấn không chỉ định `ORDER BY`. Hai lần chạy cùng một truy vấn có thể trả về các dòng theo thứ tự khác nhau do thay đổi kế hoạch thực thi, index hoặc dữ liệu.

Ví dụ, khi muốn lưu danh sách mặt hàng theo mã:

~~~sql
SELECT item_id, item_name, quantity
FROM practice_item
ORDER BY item_id;
~~~

Nếu kết quả được dùng để so sánh giữa hai lần chạy, cần cố định thứ tự và các điều kiện lọc. Khi so sánh dữ liệu có thể thay đổi theo thời gian, hãy ghi lại mốc thời gian, bộ lọc và snapshot hoặc transaction phù hợp.

## 9. Lưu script và kết quả trong Git

SQL là mã nguồn của quy trình thao tác dữ liệu, nên có thể được review và quản lý phiên bản như các file code khác.

Nên đưa vào Git:

- File SQL đã được review và có mục đích rõ ràng.
- README giải thích thứ tự chạy, yêu cầu quyền và kết quả mong đợi.
- Dữ liệu mẫu giả lập, không chứa dữ liệu khách hàng thật.
- Mẫu log hoặc kết quả đã loại bỏ thông tin nhạy cảm nếu cần làm tài liệu.

Không nên đưa vào Git:

- Password, token, private key và file cấu hình chứa bí mật.
- Dump dữ liệu production chưa được phép chia sẻ.
- Log chứa thông tin cá nhân, dữ liệu tài khoản hoặc nội dung nhạy cảm.
- File export lớn hoặc dữ liệu sinh tự động không cần thiết cho bài học.

Khi script đã được dùng để thay đổi môi trường chung, cần có quy trình migration, review và rollback rõ ràng. Không nên sửa tùy tiện một file migration đã được áp dụng trên môi trường khác; hãy tạo migration mới để ghi lại thay đổi tiếp theo. Trước khi chạy migration trên production, phải xác định tác động, backup/restore, thời gian khóa bảng và phương án phục hồi.

## 10. Checklist trước và sau khi chạy SQL

**Trước khi chạy**

- [ ] Đã xác minh host, port, server version và database.
- [ ] Đã xác minh user/role và quyền cần thiết.
- [ ] Đã kiểm tra đúng tab editor hoặc đúng file script.
- [ ] Đã đọc các câu lệnh có thể thay đổi hoặc xóa dữ liệu.
- [ ] Đã xác định transaction, implicit commit và khả năng rollback.
- [ ] Đã bảo vệ password và các thông tin xác thực.
- [ ] Đã xác định vị trí lưu log và kết quả.

**Sau khi chạy**

- [ ] Đã kiểm tra thông báo lỗi và warning.
- [ ] Đã xác minh số dòng bị ảnh hưởng.
- [ ] Đã truy vấn lại dữ liệu để kiểm tra kết quả.
- [ ] Đã xác nhận transaction đã COMMIT hoặc ROLLBACK theo dự kiến.
- [ ] Đã lưu script, log và thông tin môi trường cần thiết.
- [ ] Đã loại bỏ secret và dữ liệu nhạy cảm khỏi artifact chia sẻ.
- [ ] Đã ghi PASS/FAIL và nguyên nhân nếu thất bại.

## 11. Bài tập thực hành

### Bài 1: Xác minh kết nối

Kết nối vào database thực hành và chạy truy vấn nhận diện ở mục 2.3. Ghi lại server version, database hiện tại, tài khoản kiểm tra quyền và chế độ autocommit.

**Kết quả cần có:** một bản ghi xác nhận đúng máy chủ, đúng database và đúng tài khoản.

### Bài 2: Chạy file SQL hai lần

Lưu script ở mục 4.2 thành `01-practice.sql`. Chạy file hai lần và quan sát:

- Lần chạy thứ hai có tạo lỗi trùng database hoặc table không?
- Dòng dữ liệu mẫu có được đưa về trạng thái quantity = 10 không?
- Sau transaction và ROLLBACK, quantity có còn bằng 10 không?
- `ROW_COUNT()` báo bao nhiêu dòng được cập nhật?

**Kết quả cần có:** file SQL, log của hai lần chạy và lời giải thích về tính lặp lại của script.

### Bài 3: Cố ý tạo một lỗi có kiểm soát

Trong schema thực hành, thử truy vấn một bảng không tồn tại hoặc viết sai tên cột. Ghi lại mã lỗi, vị trí lỗi, cách xác định nguyên nhân và câu lệnh đã sửa.

Không cố ý gây lỗi trên database production hoặc schema chứa dữ liệu thật.

**Kết quả cần có:** log trước/sau khi sửa và truy vấn xác minh thành công.

### Bài 4: Xuất kết quả có thứ tự

Chạy truy vấn danh sách mặt hàng có `ORDER BY item_id`, xuất kết quả thành CSV hoặc TSV, sau đó mở file bằng trình soạn thảo hoặc bảng tính.

**Kết quả cần có:** file xuất UTF-8, số dòng đúng và các cột không bị lệch do dấu phân cách.

## 12. Tổng kết

Làm việc hiệu quả với MySQL đòi hỏi nhiều hơn việc gõ SQL và nhìn thấy một bảng kết quả. Bạn cần quản lý thông tin kết nối, phân biệt SQL với lệnh của client, tổ chức câu lệnh thành script có thể review và chạy lại, hiểu cách ghi log, kiểm tra lỗi và xác minh trạng thái dữ liệu.

Một lần chạy đáng tin cậy phải trả lời được: **đã chạy ở đâu, bằng tài khoản nào, chạy file hoặc câu lệnh gì, kết quả thực tế ra sao và có thể tái hiện như thế nào**. Khi ghi lại được các thông tin này, kết quả thực hành trở thành bằng chứng có thể kiểm tra và quy trình SQL có thể được chia sẻ, review và tự động hóa.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – mysql, the MySQL Command-Line Client](https://dev.mysql.com/doc/refman/8.4/en/mysql.html)
- [MySQL 8.4 Reference Manual – mysql client commands](https://dev.mysql.com/doc/refman/8.4/en/mysql-commands.html)
- [MySQL 8.4 Reference Manual – Executing SQL Statements from a Text File](https://dev.mysql.com/doc/refman/8.4/en/batch-mode.html)
- [MySQL 8.4 Reference Manual – mysql_config_editor](https://dev.mysql.com/doc/refman/8.4/en/mysql-config-editor.html)
- [MySQL 8.4 Reference Manual – mysql client options](https://dev.mysql.com/doc/refman/8.4/en/mysql-command-options.html)
- [MySQL Workbench Manual](https://dev.mysql.com/doc/workbench/en/)
- [MySQL Shell User Guide](https://dev.mysql.com/doc/mysql-shell/8.4/en/)

