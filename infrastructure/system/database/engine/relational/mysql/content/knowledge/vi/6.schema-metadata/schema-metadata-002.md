# CREATE DATABASE, USE và phạm vi database mặc định

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Trước khi tạo bảng và thao tác dữ liệu, cần biết cách tổ chức database, đặt bộ ký tự mặc định và chọn database làm ngữ cảnh cho câu lệnh SQL.

Trong MySQL, từ **database** và **schema** được dùng như hai tên gọi tương đương. Database là namespace chứa các đối tượng như table, view, trigger, procedure và event. CREATE DATABASE tạo namespace này; USE đặt database mặc định cho session hiện tại để các tên bảng chưa được định danh đầy đủ được tìm trong đúng phạm vi.

## 1. Database và schema trong MySQL

Một MySQL instance có thể quản lý nhiều database. Mỗi database chứa các đối tượng có tên riêng trong phạm vi của nó. Ví dụ, hai database sales và support có thể cùng chứa bảng tên customers:

~~~text
MySQL Server
├── sales
│   ├── customers
│   ├── orders
│   └── order_items
└── support
    ├── customers
    └── tickets
~~~

Khi truy vấn, có thể chỉ rõ database để tránh nhầm lẫn:

~~~sql
SELECT * FROM sales.customers;
SELECT * FROM support.customers;
~~~

Trong MySQL, cú pháp CREATE SCHEMA là synonym của CREATE DATABASE; cả hai đều tạo một database. Điều này khác với một số hệ quản trị khác, nơi schema có thể là một namespace nằm bên trong database.

Database không đồng nghĩa với một file đơn lẻ. InnoDB quản lý bảng và metadata thông qua tablespace, data dictionary và các cấu trúc lưu trữ riêng. Không thao tác trực tiếp với thư mục hoặc file trên đĩa để thay đổi database; hãy dùng SQL và công cụ quản trị MySQL.

## 2. Quy tắc đặt tên database

Tên database là identifier (định danh), không phải chuỗi ký tự dùng làm giá trị. Một số nguyên tắc hữu ích:

- Dùng chữ thường, chữ số và dấu gạch dưới để tên dễ đọc, nhất quán giữa các hệ điều hành.
- Chọn tên ngắn nhưng thể hiện rõ phạm vi nghiệp vụ, chẳng hạn sales, inventory hoặc customer_portal.
- Tránh tên trùng với từ khóa SQL hoặc tên gây nhầm với database hệ thống như mysql, sys, performance_schema và information_schema.
- MySQL giới hạn độ dài tên database ở mức 64 ký tự.
- Đừng dựa vào khác biệt chữ hoa/chữ thường để phân biệt database. Việc phân biệt tên có thể phụ thuộc hệ điều hành và cấu hình lower_case_table_names.

Nếu identifier chứa ký tự đặc biệt hoặc trùng từ khóa, có thể đặt trong dấu backtick. Backtick dùng để quote identifier. Dấu nháy đơn dùng cho string literal, ví dụ 'PAID'; không viết CREATE DATABASE 'sales' vì tên database không phải string literal.

Để ứng dụng chạy nhất quán trên Windows, Linux và macOS, nên thống nhất tên database bằng chữ thường và dấu gạch dưới, đồng thời không phụ thuộc vào cách filesystem xử lý chữ hoa/chữ thường.

## 3. Tạo database bằng CREATE DATABASE

### 3.1. Cú pháp cơ bản

~~~sql
CREATE DATABASE database_name;
~~~

Ví dụ:

~~~sql
CREATE DATABASE sales;
CREATE SCHEMA support;
~~~

Hai câu lệnh trên lần lượt tạo database sales và support. Nếu tên đã tồn tại, MySQL trả lỗi trừ khi dùng IF NOT EXISTS.

CREATE DATABASE là câu lệnh DDL và gây implicit commit theo quy tắc MySQL. Không thể đặt việc tạo database trong một transaction nghiệp vụ rồi kỳ vọng ROLLBACK sẽ xóa database vừa tạo.

Người thực hiện cần có quyền CREATE phù hợp ở cấp server. Trong môi trường tổ chức, thường chỉ DBA hoặc tài khoản triển khai schema được cấp quyền tạo database. Không cấp quyền quản trị rộng cho tài khoản ứng dụng chỉ để ứng dụng tự tạo database khi khởi động.

### 3.2. Tránh lỗi khi database đã tồn tại

Có thể dùng IF NOT EXISTS để tránh lỗi khi database đã được tạo:

~~~sql
CREATE DATABASE IF NOT EXISTS sales;
~~~

Nếu sales chưa tồn tại, MySQL tạo database. Nếu đã tồn tại, câu lệnh không tạo thêm database và thường trả về một warning/note.

**Điểm cần nhớ:** IF NOT EXISTS không đồng bộ cấu hình database đã tồn tại. Nếu database hiện có dùng charset hoặc collation khác, câu lệnh trên không tự thay đổi chúng. Sau khi dùng IF NOT EXISTS, hãy kiểm tra metadata nếu cần bảo đảm cấu hình.

### 3.3. Chọn character set và collation ngay khi tạo

Database có các giá trị mặc định về character set và collation. Các giá trị này được dùng làm mặc định khi tạo bảng hoặc cột mà không chỉ định riêng.

Ví dụ cho MySQL 8.0:

~~~sql
CREATE DATABASE customer_portal
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

- CHARACTER SET utf8mb4 cho phép lưu đầy đủ Unicode, gồm tiếng Việt và emoji.
- COLLATE utf8mb4_0900_ai_ci quy định quy tắc so sánh và sắp xếp chuỗi theo bộ ký tự utf8mb4.
- Hậu tố _ai_ci thể hiện quy tắc không phân biệt dấu (accent-insensitive) và không phân biệt hoa/thường (case-insensitive) trong collation này.

utf8mb4_0900_ai_ci thuộc MySQL 8.0. Với MySQL 5.7 hoặc môi trường cần tương thích phiên bản cũ hơn, hãy chọn collation có sẵn trên phiên bản đó, ví dụ utf8mb4_unicode_ci. Không sao chép collation từ một máy khác mà chưa kiểm tra máy đích hỗ trợ hay không.

Nếu bỏ qua CHARACTER SET và COLLATE, MySQL sử dụng giá trị mặc định của server. Vì vậy, hai môi trường có cấu hình server khác nhau có thể tạo database với mặc định khác nhau dù cùng chạy một câu CREATE DATABASE không chỉ định charset/collation.

### 3.4. Chọn charset và collation theo nhu cầu

Character set xác định tập ký tự có thể biểu diễn; collation xác định cách so sánh, sắp xếp và đánh giá tính tương đương của chuỗi. Hai database có cùng charset vẫn có thể dùng collation khác nhau.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Character set | Có thể lưu những ký tự nào? | utf8mb4 |
| Collation | Chuỗi được so sánh và sắp xếp theo quy tắc nào? | utf8mb4_0900_ai_ci |

Với ứng dụng tiếng Việt và dữ liệu đa ngôn ngữ, utf8mb4 thường là lựa chọn phù hợp. Collation cần chọn theo yêu cầu tìm kiếm và so sánh. Một collation không phân biệt dấu có thể coi một số chuỗi có/không dấu là tương đương khi so sánh; điều này có lợi cho một số tìm kiếm nhưng có thể không phù hợp với định danh hoặc nghiệp vụ cần phân biệt dấu.

Có thể xem các charset và collation hiện có:

~~~sql
SHOW CHARACTER SET LIKE 'utf8mb4';
SHOW COLLATION LIKE 'utf8mb4%';
~~~

Collation phải thuộc character set tương ứng. Không chọn một collation của latin1 cho database dùng utf8mb4.

## 4. Kiểm tra database vừa tạo

### 4.1. Liệt kê database

~~~sql
SHOW DATABASES;
SHOW DATABASES LIKE 'sales';
~~~

Danh sách database mà một tài khoản nhìn thấy có thể bị giới hạn theo quyền của tài khoản. Nếu database không xuất hiện, hãy kiểm tra tài khoản và quyền hiện tại trước khi kết luận database chưa tồn tại.

### 4.2. Xem cấu hình database

~~~sql
SHOW CREATE DATABASE sales;
~~~

Lệnh này trả về câu lệnh tạo database cùng các thuộc tính như character set và collation mặc định. Đây là cách nhanh để kiểm tra cấu hình mà MySQL đang lưu.

Cũng có thể truy vấn information_schema.SCHEMATA:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';
~~~

information_schema là metadata interface để tra cứu thông tin database và các đối tượng. Kết quả chỉ phản ánh những metadata mà tài khoản hiện tại được phép xem.

### 4.3. Phân biệt mặc định server và mặc định database

Kiểm tra mặc định ở cấp server:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';
~~~

Kiểm tra mặc định ở database:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = DATABASE();
~~~

Hai cấp này có thể khác nhau. Một database được tạo với CHARACTER SET utf8mb4 sẽ giữ mặc định của chính database ngay cả khi mặc định server thay đổi sau đó.

## 5. Thay đổi mặc định bằng ALTER DATABASE

Khi cần thay đổi mặc định cho các đối tượng được tạo mới, có thể dùng:

~~~sql
ALTER DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh này thay đổi default character set và collation của database. Nó **không tự chuyển đổi** character set hoặc collation của các bảng và cột đã tồn tại. Những bảng hiện tại tiếp tục giữ thuộc tính riêng của chúng.

Nếu cần chuyển đổi dữ liệu hiện có, phải lập kế hoạch riêng cho từng bảng/cột, kiểm tra độ dài dữ liệu, index, unique constraint và tác động ứng dụng. ALTER TABLE ... CONVERT TO CHARACTER SET ... có thể chuyển đổi dữ liệu và có thể cần rebuild bảng; không chạy hàng loạt trên production mà chưa đánh giá thời gian, dung lượng, khóa và backup.

Kiểm tra lại sau khi thay đổi:

~~~sql
SHOW CREATE DATABASE sales;
SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';
~~~

## 6. Chọn database mặc định bằng USE

### 6.1. Cú pháp và phạm vi

~~~sql
USE sales;
SELECT DATABASE();
~~~

USE sales đặt sales làm database mặc định của **kết nối/session hiện tại**. Từ đó, các câu lệnh dùng tên bảng không kèm database sẽ tìm bảng trong sales:

~~~sql
SELECT * FROM customers;
SELECT * FROM orders;
~~~

Có thể đổi database mặc định trong cùng session:

~~~sql
USE support;
SELECT DATABASE();
SELECT * FROM tickets;
~~~

Database mặc định tồn tại cho đến khi session kết thúc hoặc một câu USE khác được thực hiện trên chính session đó. Nó không phải cấu hình toàn server và không tự động áp dụng cho kết nối khác.

### 6.2. Kiểm tra database hiện tại

Hàm DATABASE() trả về tên database mặc định của session; nếu chưa chọn database mặc định, hàm trả về NULL.

~~~sql
SELECT DATABASE() AS current_database;
SELECT SCHEMA() AS current_schema;
~~~

Trong MySQL, SCHEMA() là synonym của DATABASE(). Hai hàm giúp xác minh ngữ cảnh trước khi chạy script có nhiều câu lệnh.

### 6.3. USE không cấp quyền

USE chỉ thay đổi ngữ cảnh tên đối tượng cho session. Nó không cấp quyền đọc, ghi, tạo hoặc xóa đối tượng. Khi thực hiện câu lệnh trên bảng, MySQL vẫn kiểm tra quyền của tài khoản đối với database và đối tượng tương ứng.

Ví dụ, chọn sales làm database mặc định không có nghĩa tài khoản tự có quyền SELECT trên sales.orders. Hãy kiểm tra quyền:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Khi gặp lỗi Access denied, xác định tài khoản đang dùng, host match và quyền cần thiết. Không nhầm việc chọn database thành việc được cấp quyền trên database đó.

## 7. Tên bảng không định danh đầy đủ và tên đầy đủ

Khi đã chọn database mặc định, có thể tham chiếu bảng bằng tên ngắn:

~~~sql
USE sales;
SELECT order_id, total_amount
FROM orders;
~~~

Nếu chưa chọn database hoặc muốn chỉ rõ nguồn dữ liệu, dùng tên đầy đủ:

~~~sql
SELECT order_id, total_amount
FROM sales.orders;
~~~

Trong MySQL, tên đối tượng có thể được định danh theo dạng:

~~~text
database_name.table_name
database_name.table_name.column_name
~~~

Tên đầy đủ đặc biệt hữu ích khi:

- Một câu truy vấn join các bảng ở nhiều database.
- Script triển khai cần chạy rõ ràng dù client chưa chọn database mặc định.
- Ứng dụng dùng nhiều schema và muốn tránh phụ thuộc trạng thái session.
- DBA điều tra cùng lúc các đối tượng có tên giống nhau ở database khác nhau.

Ví dụ join hai database:

~~~sql
SELECT c.customer_id, c.full_name, t.ticket_id
FROM sales.customers AS c
JOIN support.tickets AS t
  ON t.customer_id = c.customer_id;
~~~

Nếu identifier cần quote, quote từng thành phần bằng dấu backtick. Không quote toàn bộ chuỗi sales.orders như một identifier duy nhất; dấu chấm là dấu phân cách database và table.

## 8. Database mặc định trong MySQL CLI và ứng dụng

### 8.1. MySQL CLI

Có thể chọn database ngay khi mở kết nối:

~~~bash
mysql --host=127.0.0.1 --port=3306 --user=app_user --password sales
~~~

Ở đây sales là database mặc định được chọn khi client đăng nhập. Sau khi vào CLI, có thể kiểm tra:

~~~sql
SELECT DATABASE();
STATUS;
~~~

Hoặc chọn database sau khi đã kết nối bằng USE sales.

### 8.2. JDBC và MySQL Connector/J

Ứng dụng Java thường chỉ định database mặc định trong JDBC URL:

~~~java
String url = "jdbc:mysql://db.example.internal:3306/sales";
Connection connection = DriverManager.getConnection(url, user, password);
~~~

Phần /sales trong URL xác định database mặc định cho kết nối. Ứng dụng vẫn có thể tham chiếu database khác bằng tên đầy đủ nếu tài khoản có quyền phù hợp.

Khi dùng connection pool, mỗi connection vật lý có trạng thái session riêng. Nếu một luồng gọi USE support rồi trả connection về pool, luồng tiếp theo mượn đúng connection đó có thể nhận trạng thái database mặc định đã bị thay đổi nếu pool hoặc ứng dụng không reset trạng thái. Vì vậy:

- Giữ một database mặc định nhất quán cho pool khi có thể.
- Nếu ứng dụng chuyển database theo từng request, phải đặt lại catalog/schema một cách rõ ràng khi mượn connection và hiểu cách driver/pool quản lý trạng thái.
- Dùng tên bảng đầy đủ khi câu SQL cần truy cập nhiều database hoặc phải độc lập với database mặc định.
- Không giả định các connection trong cùng pool chia sẻ chung một USE; mỗi session có trạng thái riêng.

Không ghép tên database do người dùng nhập trực tiếp vào SQL. Identifier không thể truyền như một bind parameter thông thường; nếu phải chọn database động, hãy kiểm tra tên theo allowlist và quote identifier đúng cách.

## 9. Charset và collation được kế thừa như thế nào?

Khi tạo đối tượng mà không chỉ định charset/collation riêng, MySQL có cơ chế kế thừa mặc định theo cấp:

~~~text
Server defaults
    ↓
Database defaults
    ↓
Table defaults
    ↓
Column defaults (nếu có override)
~~~

Ví dụ, database sales được tạo với utf8mb4 và utf8mb4_0900_ai_ci; khi tạo bảng mà không chỉ định charset/collation, bảng thường kế thừa mặc định của database. Các cột ký tự không đặt riêng có thể kế thừa từ bảng.

~~~sql
CREATE DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE sales;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
);
~~~

Kiểm tra charset/collation của bảng và cột:

~~~sql
SHOW TABLE STATUS LIKE 'customers';

SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'customers';
~~~

Không phải mọi cột đều có character set. Các cột số, ngày giờ hoặc nhị phân không dùng collation theo cách cột chuỗi sử dụng.

## 10. Metadata liên quan đến database

MySQL cung cấp nhiều cách kiểm tra database và đối tượng:

| Lệnh hoặc view | Thông tin |
|---|---|
| SHOW DATABASES | Danh sách database mà tài khoản hiện tại được phép nhìn thấy |
| SHOW CREATE DATABASE db_name | Câu lệnh và thuộc tính tạo database |
| SELECT DATABASE() | Database mặc định của session |
| information_schema.SCHEMATA | Tên database, charset và collation mặc định |
| information_schema.TABLES | Metadata bảng, gồm database và storage engine |
| information_schema.COLUMNS | Metadata cột, kiểu dữ liệu, charset/collation nếu có |

Ví dụ lấy danh sách database cùng mặc định charset/collation:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
ORDER BY SCHEMA_NAME;
~~~

Ví dụ tìm các bảng trong database hiện tại:

~~~sql
SELECT TABLE_NAME, TABLE_TYPE, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
~~~

Kết quả metadata giúp kiểm tra môi trường triển khai và phát hiện khác biệt giữa development, staging và production. Khi so sánh, cần dùng tài khoản có quyền xem đầy đủ các đối tượng liên quan; danh sách bị giới hạn quyền có thể khiến báo cáo thiếu dữ liệu.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Can't create database hoặc Access denied | Tài khoản thiếu quyền CREATE, tên không hợp lệ hoặc lỗi filesystem/server | Kiểm tra SHOW GRANTS, error log và tên database; nhờ DBA tạo database nếu cần |
| Database exists | Database đã tồn tại | Kiểm tra SHOW CREATE DATABASE; dùng IF NOT EXISTS nếu mục tiêu chỉ là tạo khi chưa có |
| Chạy IF NOT EXISTS nhưng charset vẫn khác mong muốn | Database cũ đã tồn tại; câu lệnh không cập nhật mặc định | Dùng SHOW CREATE DATABASE, sau đó ALTER DATABASE nếu cần thay mặc định |
| No database selected | Session chưa có database mặc định và câu lệnh dùng tên bảng không đầy đủ | Chạy USE db_name hoặc dùng db_name.table_name |
| Table doesn't exist dù bảng có ở database khác | Database mặc định đang trỏ sai nơi | Chạy SELECT DATABASE() và tham chiếu bằng tên đầy đủ |
| Truy cập bảng bị Access denied sau USE | Chọn database không cấp quyền đối với bảng | Kiểm tra user-host match và SHOW GRANTS |
| Ký tự tiếng Việt hiển thị sai hoặc so sánh không như mong đợi | Charset/collation ở server, database, table, column hoặc connection không đồng nhất | Kiểm tra metadata và biến charset của kết nối; sửa đúng cấp cần thiết |
| Cùng tên database hoạt động khác nhau trên các hệ điều hành | Khác biệt case sensitivity hoặc lower_case_table_names | Dùng tên chữ thường nhất quán và kiểm tra cấu hình trước khi triển khai |

Khi điều tra, hãy xác định lỗi thuộc bước tạo database, chọn database mặc định, phân giải tên, quyền truy cập hay chuyển đổi ký tự. Mỗi bước có nguyên nhân và cách kiểm tra khác nhau.

## 12. Bài thực hành: tạo database và làm việc với phạm vi mặc định

Thực hiện trong instance MySQL lab hoặc môi trường phát triển mà bạn được phép tạo database. Tài khoản cần có quyền CREATE ở cấp phù hợp.

**Bước 1 — Kiểm tra môi trường.** Chạy:

~~~sql
SELECT VERSION(), DATABASE();
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';
~~~

Ghi lại phiên bản MySQL, database mặc định ban đầu và charset/collation mặc định của server.

**Bước 2 — Tạo database.** Tạo database lab với charset utf8mb4 và collation được phiên bản hiện tại hỗ trợ:

~~~sql
CREATE DATABASE mysql_schema_lab
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Nếu server không hỗ trợ collation trên, kiểm tra SHOW COLLATION LIKE 'utf8mb4%'; và chọn collation utf8mb4 phù hợp với phiên bản.

**Bước 3 — Xác minh metadata.** Chạy SHOW CREATE DATABASE mysql_schema_lab; và truy vấn information_schema.SCHEMATA. Đối chiếu charset/collation trả về với giá trị đã chỉ định.

**Bước 4 — Chọn database mặc định.** Chạy:

~~~sql
USE mysql_schema_lab;
SELECT DATABASE();
~~~

Tạo một bảng nhỏ không chỉ định charset/collation ở cấp bảng:

~~~sql
CREATE TABLE notes (
    note_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    note_text VARCHAR(200) NOT NULL,
    PRIMARY KEY (note_id)
);
~~~

Kiểm tra charset/collation của bảng và cột trong information_schema.

**Bước 5 — So sánh tên ngắn và tên đầy đủ.** Khi đang dùng mysql_schema_lab, chạy SELECT * FROM notes;. Sau đó đổi sang database khác bằng USE (nếu tài khoản có quyền) và chạy SELECT * FROM mysql_schema_lab.notes;. Ghi nhận tên đầy đủ không phụ thuộc database mặc định.

**Bước 6 — Kiểm tra phạm vi session.** Mở hai kết nối độc lập. Chạy USE mysql_schema_lab ở kết nối thứ nhất và SELECT DATABASE() ở cả hai. Quan sát chỉ session thứ nhất thay đổi database mặc định.

**Bước 7 — Kiểm tra hành vi IF NOT EXISTS.** Chạy lại CREATE DATABASE IF NOT EXISTS mysql_schema_lab;, sau đó dùng SHOW CREATE DATABASE để xác minh câu lệnh này không tự thay đổi charset/collation của database hiện hữu.

**Bước 8 — Dọn lab theo quyền được cấp.** Nếu database chỉ được tạo cho bài thực hành và không chứa dữ liệu cần giữ, xác nhận đúng tên database rồi xóa theo quy trình lab của bạn. Không chạy lệnh xóa trên database dùng chung hoặc database không do bạn tạo.

**Kết quả cần đạt:** tạo và xác minh được database, hiểu charset/collation mặc định, chọn database theo session, phân biệt tên bảng ngắn với tên đầy đủ và chứng minh USE không thay đổi session khác.

## 13. Nguyên tắc sử dụng trong dự án

- Tạo database bằng migration hoặc quy trình triển khai có kiểm soát; hạn chế quyền CREATE DATABASE ở tài khoản ứng dụng runtime.
- Chọn utf8mb4 và collation theo yêu cầu ngôn ngữ, tìm kiếm và so sánh của nghiệp vụ.
- Dùng SHOW CREATE DATABASE và information_schema.SCHEMATA để xác minh cấu hình thay vì chỉ tin vào file migration.
- Đặt database mặc định nhất quán cho mỗi connection pool; không giả định USE có phạm vi toàn server.
- Dùng tên đầy đủ khi truy vấn nhiều database hoặc khi muốn giảm phụ thuộc vào session state.
- Không xem CREATE DATABASE IF NOT EXISTS là cơ chế cập nhật cấu hình database hiện có.
- Khi thay đổi charset/collation, phân biệt thay đổi mặc định database với chuyển đổi dữ liệu của table và column.
- Kiểm tra quyền riêng biệt cho việc tạo database và thao tác trên từng đối tượng bên trong database.

Nắm được CREATE DATABASE, USE và phạm vi database mặc định giúp tổ chức schema rõ ràng, triển khai môi trường nhất quán và tránh lỗi truy vấn do session trỏ nhầm database. Đây là nền tảng để tiếp tục quản lý metadata, tạo bảng, ràng buộc và các đối tượng trong MySQL.
