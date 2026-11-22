# Illegal mix of collations và dữ liệu sai bộ ký tự

Lỗi **Illegal mix of collations** xuất hiện khi MySQL phải so sánh hoặc kết hợp các biểu thức chuỗi nhưng không thể chọn một collation hợp lệ theo quy tắc ưu tiên của nó. Lỗi thường gặp có mã **1267**; các phép kết hợp nhiều chuỗi có thể trả lỗi **1271**. Một vấn đề gần kề là dữ liệu tiếng Việt bị thành dấu hỏi, ký tự thay thế hoặc lỗi **Incorrect string value** (thường là mã **1366**). Hai nhóm sự cố có liên quan nhưng không giống nhau: collation quyết định cách so sánh/sắp xếp chuỗi, còn character set quyết định cách mã hóa ký tự thành byte.

Bài học thuộc module **DATABASE_MYSQL**, chương **Xử lý sự cố**. Mục tiêu là chẩn đoán đúng nguồn gây lỗi trong bảng, cột, literal SQL, connection hoặc dữ liệu đã lưu; chọn cách sửa phù hợp; và chuyển đổi charset/collation mà không làm hỏng dữ liệu hay tạo xung đột khóa.

## 1. Phân biệt character set và collation

Hai khái niệm này luôn đi cùng nhau nhưng giải quyết hai vấn đề khác nhau:

- **Character set** định nghĩa tập ký tự và cách mã hóa ký tự thành byte. Ví dụ **utf8mb4** có thể lưu mọi ký tự Unicode, gồm tiếng Việt, emoji và các ký tự ngoài Basic Multilingual Plane.
- **Collation** định nghĩa quy tắc so sánh và sắp xếp chuỗi thuộc một character set. Nó quyết định các chuỗi có được xem là bằng nhau khi khác chữ hoa/thường hoặc dấu hay không.

Ví dụ, cùng character set utf8mb4 có thể dùng các collation khác nhau:

| Collation | Quy tắc chính | Ví dụ hành vi |
|---|---|---|
| utf8mb4_0900_ai_ci | Accent-insensitive, case-insensitive theo Unicode Collation Algorithm 9.0 | Thường xem a, A và á tương đương trong so sánh |
| utf8mb4_0900_as_cs | Accent-sensitive, case-sensitive | Phân biệt dấu và chữ hoa/thường |
| utf8mb4_bin | So sánh theo giá trị nhị phân của chuỗi | Phân biệt byte/ký tự theo quy tắc binary |
| utf8mb4_general_ci | Quy tắc tổng quát, cũ hơn | Không hoàn toàn tương đương với collation UCA mới |

Tên collation thường có hậu tố:

- **_ai:** accent-insensitive, không phân biệt dấu.
- **_as:** accent-sensitive, phân biệt dấu.
- **_ci:** case-insensitive, không phân biệt hoa/thường.
- **_cs:** case-sensitive, phân biệt hoa/thường.
- **_bin:** so sánh theo giá trị nhị phân.

Không thể chỉ nhìn tên utf8mb4 để kết luận hai cột có cùng cách so sánh. Hai cột cùng character set nhưng khác collation vẫn có thể gây xung đột khi JOIN, UNION, CONCAT hoặc so sánh biểu thức.

### Vì sao lỗi charset và lỗi collation khác nhau?

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| Illegal mix of collations | Các biểu thức chuỗi có collation không tương thích hoặc có độ ưu tiên ngang nhau nhưng không thể hòa giải |
| COLLATION ... is not valid for CHARACTER SET ... | Chọn collation không thuộc character set của biểu thức |
| Incorrect string value | Byte gửi đến server không hợp lệ với character set đích hoặc ký tự không thể biểu diễn trong charset đích |
| Dữ liệu hiện dấu ? hoặc � | Có thể sai charset ở client, kết quả hiển thị hoặc dữ liệu đã bị thay thế/mất byte từ trước |
| Tiếng Việt thành mojibake, ví dụ Tiáº¿ng Viá»‡t | Byte UTF-8 có thể đã bị diễn giải như một charset khác hoặc chuyển đổi nhiều lần |

Đổi collation không thể khôi phục ký tự đã bị thay thế thành dấu hỏi. Ngược lại, đổi character set cũng không tự giải quyết mọi xung đột collation trong truy vấn.

## 2. Những nơi MySQL lấy charset và collation

MySQL có cấu hình ở nhiều cấp. Một chuỗi trong câu SQL có thể mang charset/collation khác với cột mà nó được so sánh.

### Cấp server

Các biến mặc định toàn server gồm:

- **character_set_server:** character set mặc định cho database mới nếu không chỉ định.
- **collation_server:** collation mặc định cho database mới nếu không chỉ định.

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

### Cấp database

Database có default character set và collation riêng. Chúng được dùng làm mặc định khi tạo bảng hoặc đối tượng mới nếu không khai báo rõ:

~~~sql
SELECT
  SCHEMA_NAME,
  DEFAULT_CHARACTER_SET_NAME,
  DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'app';
~~~

Thay default database không tự chuyển đổi các bảng hoặc cột đã tồn tại. Nó chỉ ảnh hưởng mặc định của đối tượng tạo sau đó.

### Cấp bảng và cột

Mỗi bảng có default charset/collation; từng cột chuỗi có thể ghi đè bằng cấu hình riêng.

~~~sql
SHOW CREATE TABLE app.customers\G
~~~

Kiểm tra chi tiết cột:

~~~sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  COLUMN_NAME,
  DATA_TYPE,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

Chỉ cột kiểu ký tự mới có character set và collation. Các cột số, ngày giờ hoặc binary thường có hai trường này là NULL.

### Cấp connection/session

Các biến sau quyết định cách client và server trao đổi chuỗi:

| Biến | Vai trò |
|---|---|
| character_set_client | Character set mà server giả định cho câu lệnh client gửi lên |
| character_set_connection | Character set dùng sau bước chuyển đổi từ client khi server xử lý chuỗi literal |
| character_set_results | Character set dùng để gửi kết quả chuỗi về client |
| collation_connection | Collation mặc định của chuỗi literal và một số biểu thức trong connection |

Kiểm tra trong đúng session gây lỗi:

~~~sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@collation_connection;
~~~

Kết quả trong một cửa sổ SQL client khác không chứng minh connection của ứng dụng có cùng cấu hình. Mỗi connection trong pool có thể được tạo hoặc khởi tạo khác nhau.

## 3. Tái hiện lỗi Illegal mix of collations

Giả sử hệ thống có hai bảng cũ và mới. Cột tên khách hàng ở bảng cũ dùng utf8mb4_general_ci, còn bảng mới dùng utf8mb4_0900_ai_ci.

~~~sql
CREATE TABLE app.customer_legacy (
  customer_id BIGINT PRIMARY KEY,
  customer_name VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_general_ci
) ENGINE=InnoDB;

CREATE TABLE app.customer_new (
  customer_id BIGINT PRIMARY KEY,
  customer_name VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB;
~~~

Một phép JOIN có thể phát sinh xung đột collation:

~~~sql
SELECT
  old.customer_id,
  new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON old.customer_name = new.customer_name;
~~~

Tùy quy tắc coercibility và phiên bản MySQL, biểu thức trên có thể trả lỗi 1267. Cần kiểm tra chính xác collation của từng biểu thức trong session đang chạy:

~~~sql
SELECT
  COLLATION(old.customer_name) AS old_collation,
  COLLATION(new.customer_name) AS new_collation,
  COERCIBILITY(old.customer_name) AS old_coercibility,
  COERCIBILITY(new.customer_name) AS new_coercibility
FROM app.customer_legacy AS old
CROSS JOIN app.customer_new AS new
LIMIT 1;
~~~

Không nên sửa bằng cách đổi collation của toàn database trước khi biết cột nào đang gây lỗi. Truy vấn có thể kết hợp nhiều nguồn khác nhau: cột bảng, literal, tham số prepared statement, biểu thức CASE, CONCAT, view hoặc temporary table.

## 4. Quy tắc coercibility: MySQL chọn collation nào?

Khi kết hợp các biểu thức chuỗi, MySQL dùng độ ưu tiên gọi là **coercibility** để xác định collation kết quả. Giá trị càng nhỏ thì mức ưu tiên càng cao.

| Coercibility | Nguồn biểu thức thường gặp | Ý nghĩa |
|---:|---|---|
| 0 | Biểu thức có COLLATE tường minh | Explicit |
| 1 | Kết quả kết hợp các chuỗi có collation khác nhau | No collation |
| 2 | Cột, tham số routine hoặc biến local có collation khai báo | Implicit |
| 3 | Một số hằng hệ thống như USER() hoặc DATABASE() | System constant |
| 4 | Chuỗi literal | Coercible |
| 5 | Giá trị số hoặc temporal được chuyển thành chuỗi | Numeric |
| 6 | NULL | Ignorable |

Có thể kiểm tra bằng:

~~~sql
SELECT
  COLLATION('Xin chào') AS literal_collation,
  COERCIBILITY('Xin chào') AS literal_coercibility,
  COLLATION('Xin chào' COLLATE utf8mb4_0900_ai_ci) AS explicit_collation,
  COERCIBILITY('Xin chào' COLLATE utf8mb4_0900_ai_ci)
    AS explicit_coercibility;
~~~

Một cột thường có coercibility 2; literal thường có coercibility 4. Vì vậy literal có thể được chuyển theo collation của cột trong một phép so sánh. Nhưng nếu hai cột có cùng độ ưu tiên và collation không thể hòa giải, MySQL có thể báo Illegal mix of collations.

Quy tắc có thêm trường hợp đặc biệt cho binary/nonbinary, character set khác nhau và phép toán cụ thể. Hãy dùng COLLATION() và COERCIBILITY() trên chính các biểu thức trong truy vấn để xác minh, thay vì tự đoán theo tên bảng.

## 5. Các biểu thức thường gây xung đột

Không chỉ phép = trong WHERE mới gặp lỗi. Hãy rà soát các phép kết hợp chuỗi sau:

- **JOIN / WHERE:** so sánh cột đến từ hai bảng có collation khác nhau.
- **UNION / UNION ALL:** các cột tương ứng ở hai SELECT có charset/collation không tương thích.
- **CONCAT / CONCAT_WS:** ghép các biểu thức chuỗi từ nhiều nguồn.
- **CASE / IF / COALESCE:** các nhánh trả về chuỗi có collation khác nhau.
- **GROUP BY / DISTINCT:** xác định hai chuỗi có bằng nhau hay không theo collation.
- **ORDER BY:** sắp xếp theo quy tắc collation của biểu thức.
- **LIKE / IN:** so sánh chuỗi với pattern hoặc danh sách literal/column khác collation.
- **View, stored routine, temporary table:** đối tượng được tạo từ thời điểm hoặc session có default khác.

Ví dụ với UNION:

~~~sql
SELECT customer_name
FROM app.customer_legacy
UNION ALL
SELECT customer_name
FROM app.customer_new;
~~~

Ví dụ với CASE:

~~~sql
SELECT
  CASE
    WHEN status_code = 1 THEN 'Đang hoạt động'
    ELSE description
  END AS status_label
FROM app.customer_new;
~~~

Khi truy vấn lỗi, rút gọn dần biểu thức và dùng COLLATION(expr) để xác định nguồn. Với view hoặc routine, kiểm tra định nghĩa và thời điểm tạo; default charset của database có thể đã thay đổi sau khi đối tượng được tạo.

## 6. Quy trình chẩn đoán theo từng bước

Không bắt đầu bằng việc thay đổi collation. Trước hết cần tái hiện lỗi trong đúng connection và thu thập bằng chứng.

### Bước 1 — Ghi lại lỗi đầy đủ

Thu thập:

- Error number và SQLState.
- Toàn bộ câu SQL đã được thực thi, đã loại bỏ dữ liệu nhạy cảm.
- Tên database, bảng, cột và alias liên quan.
- Phiên bản MySQL Server và Connector/J/client.
- Lỗi xuất hiện ở JOIN, UNION, WHERE, INSERT, UPDATE hay khi đọc kết quả.
- Lỗi có xảy ra với mọi dữ liệu hay chỉ một số giá trị.

Các mã thường gặp:

| Mã | Thông báo/nhóm lỗi | Ý nghĩa |
|---:|---|---|
| 1267 | Illegal mix of collations | Xung đột collation trong phép so sánh |
| 1271 | Illegal mix of collations for operation | Xung đột khi kết hợp nhiều biểu thức chuỗi |
| 1253 | COLLATION is not valid for CHARACTER SET | Collation được chọn không thuộc charset của biểu thức |
| 1366 | Incorrect string value | Giá trị không thể chuyển đổi hợp lệ sang charset đích |
| 1300 | Invalid ... character string | Chuỗi byte không hợp lệ theo character set được diễn giải |

### Bước 2 — Kiểm tra charset/collation của session

Chạy trong đúng connection đang gặp lỗi:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@character_set_client AS client_charset,
  @@character_set_connection AS connection_charset,
  @@character_set_results AS results_charset,
  @@collation_connection AS connection_collation;
~~~

Nếu lỗi chỉ xảy ra trong ứng dụng, chạy câu lệnh qua chính datasource hoặc log thông tin session từ ứng dụng. Không so sánh kết quả từ MySQL Workbench với session của connection pool rồi kết luận chúng giống nhau.

### Bước 3 — Kiểm tra database, bảng và cột

~~~sql
SELECT
  SCHEMA_NAME,
  DEFAULT_CHARACTER_SET_NAME,
  DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'app';

SELECT
  TABLE_NAME,
  TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_TYPE = 'BASE TABLE';

SELECT
  TABLE_NAME,
  COLUMN_NAME,
  COLUMN_TYPE,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND CHARACTER_SET_NAME IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
~~~

Nếu kết quả có nhiều collation, chưa chắc đó là lỗi: một schema có thể cố ý dùng collation khác nhau cho các cột. Hãy tập trung vào các cột cùng xuất hiện trong biểu thức đang lỗi.

### Bước 4 — Kiểm tra biểu thức cụ thể

Với từng biểu thức:

~~~sql
SELECT
  COLLATION(column_a),
  COERCIBILITY(column_a),
  COLLATION(column_b),
  COERCIBILITY(column_b);
~~~

Nếu biểu thức có literal, kiểm tra cả literal:

~~~sql
SELECT
  CHARSET('Đặng'),
  COLLATION('Đặng'),
  COERCIBILITY('Đặng');
~~~

Rút gọn query bằng cách bỏ lần lượt JOIN, CASE, CONCAT hoặc UNION cho đến khi tìm được biểu thức làm lỗi xuất hiện. Sau đó xác định có cần chuyển charset, ép collation hay chuẩn hóa schema.

### Bước 5 — Phân biệt lỗi so sánh với dữ liệu bị mã hóa sai

Nếu truy vấn chạy được nhưng tiếng Việt hiển thị sai, kiểm tra byte lưu trữ:

~~~sql
SELECT
  customer_id,
  customer_name,
  HEX(customer_name) AS stored_hex,
  LENGTH(customer_name) AS byte_length,
  CHAR_LENGTH(customer_name) AS character_length
FROM app.customers
WHERE customer_id = 1001;
~~~

Với chuỗi Unicode, LENGTH() đếm byte còn CHAR_LENGTH() đếm ký tự theo charset của cột. Chênh lệch là bình thường với UTF-8; nó không tự chứng minh dữ liệu bị lỗi. Hãy so sánh HEX() với byte UTF-8 mong đợi của một giá trị đã biết và kiểm tra cùng dữ liệu qua client khác.

## 7. Sửa xung đột collation trong một truy vấn

Nếu hai cột cùng character set nhưng khác collation, có thể chỉ định một collation chung cho phép so sánh.

~~~sql
SELECT old.customer_id, new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON old.customer_name COLLATE utf8mb4_0900_ai_ci
   = new.customer_name COLLATE utf8mb4_0900_ai_ci;
~~~

Ví dụ này chỉ hợp lệ nếu cả hai biểu thức có character set utf8mb4 và collation được chọn tồn tại trên phiên bản MySQL đang chạy. Nó áp dụng quy tắc so sánh mới cho phép JOIN, nhưng không thay đổi định nghĩa cột hoặc dữ liệu đã lưu.

### Khi hai biểu thức khác character set

Nếu một cột là latin1 và cột kia là utf8mb4, trước tiên chuyển biểu thức về cùng character set, rồi chỉ định collation hợp lệ:

~~~sql
SELECT old.customer_id, new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON CONVERT(old.customer_name USING utf8mb4)
       COLLATE utf8mb4_0900_ai_ci
   = new.customer_name COLLATE utf8mb4_0900_ai_ci;
~~~

CONVERT(... USING utf8mb4) yêu cầu MySQL chuyển đổi ký tự từ charset nguồn sang utf8mb4. Điều này chỉ đúng nếu charset khai báo của dữ liệu nguồn phản ánh đúng byte đã lưu. Nếu byte UTF-8 bị khai báo nhầm là latin1, phép CONVERT có thể tạo mojibake thay vì sửa dữ liệu.

### Chuẩn hóa literal

Với literal, có thể dùng character set introducer và COLLATE:

~~~sql
SELECT customer_id
FROM app.customers
WHERE customer_name =
  _utf8mb4'Đặng' COLLATE utf8mb4_0900_ai_ci;
~~~

Introducer cho server biết literal thuộc character set nào; COLLATE chọn quy tắc so sánh. Nó không thay thế việc cấu hình đúng charset của client gửi câu SQL. Nếu client đã gửi byte sai, introducer không thể tự khôi phục nội dung ban đầu.

### Lưu ý hiệu năng

Áp dụng COLLATE hoặc CONVERT trực tiếp lên cột trong JOIN/WHERE có thể khiến MySQL khó dùng index theo cách tối ưu, tùy biểu thức và kế hoạch thực thi. Sau khi sửa để query chạy đúng:

~~~sql
EXPLAIN
SELECT old.customer_id, new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON old.customer_name COLLATE utf8mb4_0900_ai_ci
   = new.customer_name COLLATE utf8mb4_0900_ai_ci;
~~~

Kiểm tra access type, key, rows và thời gian thực tế. Nếu đây là truy vấn nóng, giải pháp bền vững thường là chuẩn hóa charset/collation ở schema hoặc tạo cột chuẩn hóa được index theo thiết kế phù hợp, thay vì ép chuyển đổi mỗi lần truy vấn.

Không dùng BINARY hoặc CAST AS BINARY như cách sửa mặc định. So sánh nhị phân thay đổi semantics: khác biệt hoa/thường, dấu và byte trở thành quan trọng, có thể làm kết quả nghiệp vụ thay đổi.

## 8. Sửa cấu hình charset của connection

Nếu vấn đề nằm ở cách client gửi hoặc nhận dữ liệu, cần sửa cấu hình connection. Thao tác này không đổi charset/collation của cột hiện có.

### Trong SQL client hoặc session quản trị

Với một client SQL tương tác, có thể đặt:

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

SET NAMES thiết lập character_set_client, character_set_connection, character_set_results và collation_connection cho session. Chỉ dùng collation có sẵn và tương thích với utf8mb4 trên server. Kiểm tra lại bằng SHOW VARIABLES sau khi thiết lập.

### Trong ứng dụng Java với Connector/J

Với JDBC, để Connector/J quản lý thương lượng charset theo phiên bản driver và cấu hình của nó. Không tùy tiện chạy SET NAMES trong mỗi lần lấy connection nếu driver cũng đang quản lý charset; hai cơ chế có thể không đồng bộ.

Các điểm cần xác minh:

- Phiên bản Connector/J thực tế.
- Charset/collation session qua SELECT @@character_set_client, @@character_set_connection, @@character_set_results, @@collation_connection.
- Cấu hình character encoding hoặc connection collation theo tài liệu của đúng phiên bản Connector/J.
- Charset của dữ liệu gửi từ ứng dụng và cách framework bind tham số PreparedStatement.
- Character set kết quả được client/driver giải mã như thế nào.

Với Connector/J hiện đại, UTF-8/utf8mb4 thường được hỗ trợ tự động; không thêm property cũ chỉ vì tìm thấy trong cấu hình của một ứng dụng legacy. Nếu cần cố định collation connection, dùng thuộc tính được tài liệu phiên bản driver hỗ trợ và kiểm tra session sau khi pool tạo connection.

### Với connection pool

Connection pool tái sử dụng nhiều session. Cấu hình khởi tạo phải được áp dụng nhất quán cho mọi connection mới. Nếu thay đổi charset bằng SET NAMES trên một connection rồi trả về pool, request tiếp theo có thể nhận session với trạng thái khác dự kiến. Tránh thay đổi session tùy tiện giữa các request; nếu cần, chuẩn hóa qua cấu hình DataSource hoặc connection initialization đã được kiểm thử.

## 9. Chuẩn hóa default charset/collation của schema

Khi đã xác định các cột và dữ liệu được mã hóa đúng, có thể chuẩn hóa mặc định cho đối tượng mới và chuyển đổi các bảng hiện hữu theo kế hoạch.

### Đổi default của database

~~~sql
ALTER DATABASE app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh này thay đổi mặc định của database cho các đối tượng tạo sau đó. Nó **không tự chuyển đổi** dữ liệu hoặc collation của bảng/cột đã tồn tại.

### Đổi default của bảng

~~~sql
ALTER TABLE app.customers
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh này thay default charset/collation của bảng, ảnh hưởng đến cột chuỗi tạo mới nếu không khai báo rõ. Nó **không chuyển đổi** collation của các cột chuỗi hiện tại.

### Chuyển đổi các cột chuỗi hiện có

~~~sql
ALTER TABLE app.customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

CONVERT TO CHARACTER SET yêu cầu MySQL chuyển đổi các cột ký tự của bảng sang charset/collation đích. Đây là thay đổi dữ liệu và metadata, có thể rebuild bảng, tạo tải I/O, giữ metadata lock và cần thêm dung lượng. Đọc tài liệu đúng phiên bản về thuật toán DDL được hỗ trợ; không giả định lệnh này luôn INSTANT hoặc không khóa.

Trong một số trường hợp, MySQL có thể đổi kiểu cột để bảo toàn dung lượng ký tự sau khi chuyển sang charset có số byte tối đa lớn hơn, ví dụ từ VARCHAR sang TEXT. Luôn kiểm tra lại SHOW CREATE TABLE sau migration và xác minh các ứng dụng, ORM, index hoặc giới hạn độ dài có phụ thuộc kiểu cột cũ hay không.

Nếu chỉ muốn đổi một cột:

~~~sql
ALTER TABLE app.customers
  MODIFY customer_name VARCHAR(150)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL;
~~~

Khi dùng MODIFY, phải khai báo lại đầy đủ thuộc tính cột hiện có như kiểu dữ liệu, độ dài, NULL/NOT NULL, DEFAULT, COMMENT, generated expression và các thuộc tính khác. Bỏ sót thuộc tính có thể làm schema thay đổi ngoài ý muốn. Hãy lấy SHOW CREATE TABLE làm cơ sở để soạn DDL.

### Kiểm tra collation có tồn tại trên server

~~~sql
SHOW COLLATION LIKE 'utf8mb4_0900_ai_ci';
SHOW CHARACTER SET LIKE 'utf8mb4';
~~~

Collation utf8mb4_0900_* thuộc dòng MySQL 8.0; MySQL 5.7 không có các collation UCA 9.0 này. MariaDB có danh sách và tên collation riêng theo phiên bản. Không dùng tên collation từ một MySQL mới trên server cũ hoặc MariaDB mà chưa xác minh.

## 10. Dữ liệu đã bị lưu sai charset

Đây là tình huống nguy hiểm hơn một lỗi collation thông thường. Ví dụ, cột được khai báo latin1 nhưng byte thực tế bên trong lại là byte UTF-8. MySQL diễn giải từng byte theo latin1 nên nội dung hiển thị thành mojibake. Nếu chạy CONVERT TO CHARACTER SET utf8mb4 trực tiếp, MySQL sẽ chuyển đổi ký tự theo khai báo latin1 hiện tại; kết quả có thể tiếp tục sai.

### Phân biệt ba trường hợp

1. **Khai báo đúng, connection sai:** dữ liệu trong bảng hợp lệ nhưng client gửi hoặc đọc bằng charset không đúng. Sửa cấu hình connection; không sửa dữ liệu.
2. **Cột khai báo sai, byte vẫn còn nguyên:** byte có thể là UTF-8 nhưng được lưu trong cột khai báo latin1 hoặc charset khác. Cần phục hồi byte và diễn giải lại theo charset thực tế.
3. **Byte đã bị thay thế hoặc mất:** dữ liệu đã thành dấu hỏi hoặc ký tự thay thế trước khi lưu. Chuyển charset không thể khôi phục phần thông tin đã mất; cần nguồn backup hoặc nguồn dữ liệu gốc.

### Kiểm tra byte trước khi chuyển đổi

~~~sql
SELECT
  customer_id,
  customer_name,
  HEX(customer_name) AS raw_hex,
  LENGTH(customer_name) AS byte_length,
  CHAR_LENGTH(customer_name) AS character_length
FROM app.customers
WHERE customer_id IN (1001, 1002, 1003);
~~~

Chọn các giá trị đã biết chính xác và so sánh HEX với byte mong đợi. Kiểm tra nhiều nhóm dữ liệu, gồm chữ ASCII, tiếng Việt có dấu, emoji nếu hệ thống có lưu và các giá trị được nhập từ nguồn khác nhau. Một bảng có thể chứa dữ liệu được ghi ở nhiều thời kỳ với cách mã hóa khác nhau.

Không dùng riêng ảnh chụp màn hình từ một GUI để kết luận byte đã đúng. GUI có thể tự chuyển đổi charset khi hiển thị.

### Quy trình phục hồi khi byte UTF-8 bị khai báo nhầm

Nếu đã xác nhận byte trong cột thực sự là UTF-8 nhưng cột khai báo một charset khác, có thể cần giữ nguyên byte ở một cột nhị phân tạm rồi diễn giải byte đó thành utf8mb4 trong cột đích. Mô hình minh họa:

~~~sql
-- 1. Tạo bản sao hoặc cột staging đủ lớn để giữ nguyên byte.
ALTER TABLE app.customers
  ADD COLUMN customer_name_raw VARBINARY(1024) NULL;

-- 2. Sao chép byte hiện tại, không chuyển đổi theo collation.
UPDATE app.customers
SET customer_name_raw = CAST(customer_name AS BINARY);

-- 3. Tạo cột đích có charset đúng.
ALTER TABLE app.customers
  ADD COLUMN customer_name_fixed VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NULL;

-- 4. Diễn giải byte staging theo UTF-8 sau khi đã xác minh dữ liệu.
UPDATE app.customers
SET customer_name_fixed =
    CONVERT(customer_name_raw USING utf8mb4);
~~~

Đây chỉ là mô hình để giải thích quy trình, không phải script chạy trực tiếp trên production. Cần chọn kích thước staging theo byte tối đa, kiểm tra byte sequence hợp lệ, xử lý NULL, xác minh độ dài, đối chiếu dữ liệu và thử trên bản sao. Nếu byte nguồn không phải UTF-8 hợp lệ, bước CONVERT có thể lỗi hoặc tạo dữ liệu không mong muốn.

Chỉ sau khi đối soát đầy đủ mới lập kế hoạch đổi ứng dụng sang cột đã sửa, cập nhật index/constraint, đổi tên cột hoặc loại bỏ cột cũ. Giữ bản gốc cho đến khi có backup và bằng chứng phục hồi đạt yêu cầu.

### Không thể khôi phục ký tự đã mất

Nếu client gửi một ký tự không thể biểu diễn trong charset cột và server đã lưu thành dấu hỏi, byte gốc không còn trong database. Đổi cột sang utf8mb4 chỉ làm cột có thể lưu Unicode trong tương lai; nó không biến dấu hỏi thành ký tự ban đầu. Phải khôi phục từ backup, log nguồn hoặc dữ liệu gốc đã được giữ ở hệ thống khác.

## 11. Những rủi ro khi đổi collation

Đổi collation có thể thay đổi kết quả so sánh và tính duy nhất của dữ liệu, ngay cả khi byte không thay đổi.

### Unique key có thể phát sinh trùng

Giả sử trước đây collation phân biệt hoa/thường, nên các giá trị sau cùng tồn tại:

~~~text
Admin
admin
~~~

Nếu đổi sang collation case-insensitive, hai giá trị có thể được xem là bằng nhau. Khi cột có UNIQUE index, ALTER có thể thất bại vì duplicate key.

Kiểm tra trước bằng collation đích:

~~~sql
SELECT
  customer_name COLLATE utf8mb4_0900_ai_ci AS normalized_name,
  COUNT(*) AS duplicate_count
FROM app.customers
WHERE customer_name IS NOT NULL
GROUP BY customer_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

Truy vấn này chỉ phù hợp khi cột nguồn có character set utf8mb4 và là khóa đơn không NULL. Nếu cột đang ở charset khác, chuyển đổi biểu thức sang utf8mb4 trước rồi áp dụng collation đích. Với unique index nhiều cột, phải nhóm theo toàn bộ cột khóa và xử lý NULL theo đúng semantics của index. Kiểm tra các nhóm trùng bằng dữ liệu nghiệp vụ trước khi thay đổi unique constraint.

### Index và giới hạn độ dài

utf8mb4 có thể dùng tối đa bốn byte cho mỗi ký tự. Chuyển cột từ charset một byte sang utf8mb4 có thể làm kích thước index tăng. Kiểm tra:

- Tổng byte của các cột trong composite index.
- Độ dài prefix index.
- InnoDB row format và page size.
- Phiên bản MySQL và giới hạn index tương ứng.
- Khả năng rebuild index và dung lượng tạm.

Không giả định mọi VARCHAR(255) đều có thể tạo full index trên mọi phiên bản/cấu hình. Với hệ thống cũ, giới hạn index có thể thấp hơn các cấu hình InnoDB hiện đại.

### Thay đổi semantics ứng dụng

Collation mới có thể làm thay đổi:

- Kết quả tìm kiếm và LIKE.
- Số nhóm trong GROUP BY và DISTINCT.
- Thứ tự ORDER BY.
- Kết quả JOIN và so sánh khóa.
- Hành vi unique key và upsert.

Ngoài phân biệt dấu và hoa/thường, collation còn có thuộc tính PAD SPACE hoặc NO PAD. Một số collation cũ bỏ qua khoảng trắng ở cuối khi so sánh, trong khi các collation UCA 9.0 dạng 0900 dùng NO PAD. Vì vậy, chuyển sang collation 0900 có thể làm thay đổi kết quả so sánh chuỗi có trailing spaces và hành vi unique key. Hãy thử dữ liệu có khoảng trắng cuối trước khi đổi.

Ví dụ, một ứng dụng trước đây cho phép hai username chỉ khác chữ hoa/thường có thể không còn tạo được cả hai sau khi đổi collation sang case-insensitive. Đây là thay đổi quy tắc nghiệp vụ, không chỉ là thay đổi kỹ thuật.

## 12. Kế hoạch migration an toàn

Chuyển đổi charset/collation trên bảng production cần có kế hoạch riêng, đặc biệt với bảng lớn hoặc bảng chứa khóa duy nhất.

### Trước khi thay đổi

1. Ghi lại SHOW CREATE TABLE, index, foreign key, trigger và collation của từng cột.
2. Xác nhận byte dữ liệu hiện có đúng với charset khai báo.
3. Chọn charset/collation đích tương thích với tất cả server trong topology.
4. Kiểm tra unique collision theo collation đích.
5. Ước lượng dung lượng, thời gian rebuild, I/O và replica lag.
6. Backup và thử khôi phục; thử migration trên bản sao dữ liệu gần production.
7. Kiểm thử ứng dụng với quy tắc so sánh mới.

### Khi thực hiện

- Chọn cửa sổ thay đổi phù hợp với tải.
- Theo dõi metadata lock, transaction dài, dung lượng đĩa và replica lag.
- Với bảng lớn, đánh giá DDL online gốc của MySQL hoặc công cụ online schema change theo đúng điều kiện hỗ trợ.
- Chia nhỏ theo bảng/cột nếu cần để dễ kiểm soát và rollback.
- Không thay đổi charset/collation đồng thời với nhiều thay đổi schema không liên quan.

### Sau khi thay đổi

- So sánh SHOW CREATE TABLE và metadata cột với thiết kế đích.
- Đối chiếu số hàng, NULL, độ dài và các giá trị mẫu bằng HEX.
- Kiểm tra unique key, foreign key, index và query plan.
- Chạy integration test cho tìm kiếm, JOIN, ORDER BY, GROUP BY và ghi tiếng Việt.
- Xác minh replication và ứng dụng không phát sinh lỗi mới.
- Chỉ xóa cột staging hoặc bản sao cũ sau khi hết thời gian xác minh và backup được xác nhận.

## 13. Xử lý Incorrect string value và dữ liệu tiếng Việt lỗi

Lỗi 1366 thường xảy ra khi MySQL không thể chuyển dữ liệu gửi đến thành character set của cột hoặc khi byte đầu vào không hợp lệ. Với ứng dụng tiếng Việt, nguyên nhân thường nằm ở một trong các điểm:

- Client gửi UTF-8 nhưng session khai báo charset khác.
- Cột hoặc bảng đích dùng charset không thể lưu ký tự đầu vào.
- Ứng dụng đã chuyển đổi chuỗi nhiều lần trước khi bind parameter.
- Dữ liệu import từ CSV có encoding khác với khai báo trong lệnh LOAD DATA.
- File được đọc bằng charset sai trước khi gửi đến database.

### Kiểm tra cấu hình cột

~~~sql
SHOW CREATE TABLE app.customers\G

SELECT
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'customer_name';
~~~

### Kiểm tra session

~~~sql
SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@collation_connection;
~~~

### Kiểm tra byte đầu vào và byte lưu trữ

Tạo một bản ghi thử bằng đúng đường đi của ứng dụng, rồi đọc HEX từ MySQL. So sánh byte với UTF-8 mong đợi của chuỗi thử. Nếu ghi qua SQL client thành công nhưng qua ứng dụng thất bại, tập trung kiểm tra driver, cấu hình DataSource và cách framework bind parameter.

Không tắt strict SQL mode để che lỗi 1366. Việc chuyển lỗi thành warning hoặc thay ký tự có thể làm mất dữ liệu mà ứng dụng không biết.

### Khi import file

Khai báo character set của file trong lệnh import:

~~~sql
LOAD DATA INFILE '/var/lib/mysql-files/customers.csv'
INTO TABLE app.customers_import
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
(customer_id, customer_name);
~~~

Đảm bảo file thật sự là UTF-8. Khai báo CHARACTER SET utf8mb4 không chuyển một file Windows-1258 hoặc encoding khác thành UTF-8 một cách tự động và chính xác nếu byte nguồn không khớp.

## 14. Phòng ngừa lỗi charset/collation tái diễn

Để tránh mỗi bảng hoặc mỗi ứng dụng tự chọn một cấu hình khác nhau, cần thống nhất chính sách ở tầng schema và connection.

### Chọn một chuẩn cho dữ liệu văn bản

- Ưu tiên **utf8mb4** cho dữ liệu Unicode mới.
- Chọn một collation phù hợp với quy tắc nghiệp vụ, ví dụ không phân biệt hoa/thường và dấu hay cần phân biệt cả hai.
- Dùng cùng chuẩn cho các cột thường xuyên JOIN hoặc so sánh với nhau.
- Chỉ dùng collation binary cho trường hợp thực sự cần semantics so sánh nhị phân.
- Không dựa vào default ngầm; khai báo charset/collation rõ trong DDL quan trọng.

### Cẩn trọng với tên utf8

Trong MySQL, tên **utf8** là alias của **utf8mb3** trên các phiên bản còn hỗ trợ alias đó. utf8mb3 chỉ hỗ trợ tối đa ba byte cho mỗi ký tự, nên không lưu được một số ký tự Unicode như nhiều emoji. Với schema mới, dùng utf8mb4. Khi kiểm tra hệ thống cũ, không thay chuỗi utf8 bằng utf8mb4 một cách máy móc; cần kiểm tra dữ liệu, index, unique constraint và ứng dụng trước.

utf8mb3 đã được đánh dấu deprecated từ MySQL 8.0.28. MySQL 8.0 thường dùng utf8mb4_0900_ai_ci làm collation mặc định cho utf8mb4, nhưng hệ thống nâng cấp từ phiên bản cũ có thể vẫn giữ collation cũ ở database, table và column. Không suy ra collation thực tế chỉ từ phiên bản server.

### Đồng bộ môi trường và topology

- Dùng cùng phiên bản MySQL hoặc tập collation giao nhau giữa primary, replica và môi trường phục hồi.
- Kiểm tra collation tồn tại trước khi chạy migration hoặc restore.
- Giữ cấu hình charset connection nhất quán trong DataSource và mọi connection pool.
- Chuẩn hóa cách đọc file CSV/import và encoding của ứng dụng.
- Ghi rõ charset/collation trong migration script để môi trường mới không phụ thuộc default server.

### Kiểm thử dữ liệu Unicode

Tạo bộ dữ liệu thử có:

- Chữ tiếng Việt có dấu và không dấu.
- Chữ hoa/chữ thường.
- Chuỗi có dấu kết hợp Unicode nếu ứng dụng nhận đầu vào từ nhiều nguồn.
- Ký tự ngoài BMP như emoji nếu nghiệp vụ cần.
- Chuỗi rỗng, NULL, dấu nháy và ký tự đặc biệt.

Kiểm thử cả ghi, đọc, tìm kiếm, JOIN, GROUP BY, ORDER BY và unique key. Một thao tác INSERT thành công chưa đủ chứng minh toàn bộ luồng xử lý văn bản đúng.

## 15. Bảng quyết định xử lý nhanh

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| Lỗi 1267 khi JOIN hai bảng | COLLATION() và COERCIBILITY() của hai cột | Chuẩn hóa collation trong query hoặc schema |
| Lỗi 1271 khi UNION/CONCAT/CASE | Collation của từng nhánh/đối số | Ép các nhánh về cùng charset và collation |
| Lỗi 1253 | Character set của biểu thức và collation được chỉ định | Chọn collation thuộc đúng character set |
| Lỗi 1366 khi INSERT tiếng Việt | Charset session, charset cột và byte đầu vào | Sửa connection/column hoặc import encoding sau khi xác minh |
| Ký tự hiển thị sai nhưng query không lỗi | HEX(), charset_results và client display | Xác định byte sai ở lúc ghi hay chỉ sai lúc đọc/hiển thị |
| Dữ liệu mojibake trong cột latin1 | SHOW CREATE TABLE và HEX() | Xác minh byte gốc; phục hồi qua staging nhị phân nếu đúng trường hợp |
| ALTER đổi collation báo duplicate key | Các giá trị trùng theo collation đích | Giải quyết xung đột nghiệp vụ trước khi tạo lại UNIQUE index |
| Ứng dụng lỗi nhưng SQL client chạy được | Session variables qua đúng DataSource | Kiểm tra Connector/J, pool initialization và bind parameter |

## 16. Checklist trước và sau khi sửa

**Chẩn đoán**

- [ ] Đã ghi nhận error number, SQLState và câu SQL gây lỗi.
- [ ] Đã xác định đúng session/connection phát sinh lỗi.
- [ ] Đã kiểm tra charset/collation server, database, table và column.
- [ ] Đã dùng COLLATION() và COERCIBILITY() trên biểu thức liên quan.
- [ ] Đã phân biệt xung đột collation với byte dữ liệu bị mã hóa sai.
- [ ] Đã kiểm tra HEX() với giá trị mẫu đã biết.

**Sửa lỗi truy vấn/connection**

- [ ] Collation đích tồn tại và tương thích với character set.
- [ ] Chỉ ép COLLATE/CONVERT ở biểu thức cần thiết.
- [ ] Đã kiểm tra EXPLAIN sau khi thêm conversion vào JOIN/WHERE.
- [ ] Connection pool có cấu hình charset nhất quán.
- [ ] Không dùng SET NAMES tùy tiện trong từng request JDBC.

**Chuyển đổi schema/dữ liệu**

- [ ] Đã backup và thử khôi phục.
- [ ] Đã xác nhận byte dữ liệu phù hợp với charset khai báo.
- [ ] Đã kiểm tra unique collision theo collation đích.
- [ ] Đã đánh giá độ dài index, dung lượng, DDL lock và replica lag.
- [ ] Đã thử migration trên bản sao dữ liệu đại diện.
- [ ] Đã xác minh dữ liệu tiếng Việt, Unicode và query plan sau chuyển đổi.
- [ ] Đã giữ dữ liệu gốc cho đến khi đối soát hoàn tất.

## Tài liệu tham khảo

- [MySQL Reference Manual — Character Sets and Collations](https://dev.mysql.com/doc/refman/8.0/en/charset.html)
- [MySQL Reference Manual — Connection Character Sets and Collations](https://dev.mysql.com/doc/refman/8.0/en/charset-connection.html)
- [MySQL Reference Manual — Collation Coercibility in Expressions](https://dev.mysql.com/doc/refman/8.0/en/charset-collation-coercibility.html)
- [MySQL Reference Manual — Column Character Set Conversion](https://dev.mysql.com/doc/refman/8.0/en/charset-conversion.html)
- [MySQL Reference Manual — ALTER TABLE](https://dev.mysql.com/doc/refman/8.0/en/alter-table.html)
- [MySQL Reference Manual — Character Set utf8mb4](https://dev.mysql.com/doc/refman/8.0/en/charset-unicode-utf8mb4.html)

## Kết luận

Illegal mix of collations là vấn đề về quy tắc so sánh chuỗi; dữ liệu tiếng Việt sai ký tự thường là vấn đề về byte, character set hoặc connection. Hãy xác định charset/collation của từng biểu thức và session bằng metadata, COLLATION() và COERCIBILITY() trước khi sửa. Dùng COLLATE hoặc CONVERT để xử lý truy vấn cụ thể khi phù hợp; chuẩn hóa schema khi cần giải pháp lâu dài. Nếu byte đã bị khai báo sai, phải xác minh HEX và phục hồi có kiểm soát trước khi ALTER. Cuối cùng, kiểm tra unique key, index, query plan và luồng JDBC để bảo đảm thay đổi không làm sai semantics hoặc gây mất dữ liệu.
