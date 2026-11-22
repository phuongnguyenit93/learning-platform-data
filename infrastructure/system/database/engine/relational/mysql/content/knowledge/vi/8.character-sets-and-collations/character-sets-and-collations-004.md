# character_set_client, character_set_connection và character_set_results

Khi ứng dụng gửi SQL đến MySQL, dữ liệu chuỗi đi qua nhiều bước chuyển đổi trước khi được lưu hoặc trả về. Ứng dụng mã hóa ký tự thành byte theo một character set; MySQL nhận các byte đó, diễn giải câu lệnh và literal theo cấu hình phiên; khi trả kết quả, server có thể chuyển chuỗi sang character set mà client mong đợi. Nếu hai phía không thống nhất cách diễn giải byte, dữ liệu có thể bị lỗi, hiển thị sai hoặc không thể lưu.

Ba biến phiên quan trọng điều khiển đường đi này là:

- **character_set_client**: character set mà MySQL dùng để diễn giải dữ liệu câu lệnh nhận từ client.
- **character_set_connection**: character set mà MySQL dùng cho các literal sau khi chuyển đổi từ character_set_client; nó cũng là character set mặc định cho các literal trong câu lệnh.
- **character_set_results**: character set mà MySQL dùng để chuyển đổi dữ liệu kết quả trước khi gửi về client.

Hiểu đúng ba biến này giúp xử lý lỗi tiếng Việt, emoji, dữ liệu đa ngôn ngữ, chuỗi literal trong SQL và kết quả trả về ứng dụng. Bài viết tập trung vào MySQL 8.x và khuyến nghị dùng utf8mb4 cho phần lớn ứng dụng hiện đại.

## 1. Character set và collation khác nhau thế nào?

**Character set** xác định tập ký tự có thể biểu diễn và cách mã hóa ký tự thành byte. Ví dụ, utf8mb4 có thể biểu diễn các ký tự Unicode ngoài Basic Multilingual Plane, gồm nhiều emoji và ký tự bổ sung.

**Collation** xác định cách so sánh và sắp xếp các chuỗi thuộc một character set. Một character set có thể có nhiều collation. Chẳng hạn, các collation khác nhau có thể phân biệt hoặc bỏ qua khác biệt chữ hoa/chữ thường, dấu hoặc quy tắc ngôn ngữ trong phép so sánh.

Ví dụ:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Character set | utf8mb4 | Biểu diễn ký tự bằng byte |
| Collation | utf8mb4_0900_ai_ci | Quy tắc so sánh và sắp xếp chuỗi |

Tên collation ví dụ có thể được hiểu như sau:

- utf8mb4: character set mà collation thuộc về.
- 0900: bộ quy tắc collation dựa trên UCA 9.0 trong MySQL.
- ai: accent-insensitive, không phân biệt dấu trong so sánh.
- ci: case-insensitive, không phân biệt chữ hoa/chữ thường trong so sánh.

Character set quyết định ký tự có thể được biểu diễn hay không; collation quyết định cách so sánh các giá trị chuỗi đã được biểu diễn. Hai khái niệm liên quan nhưng không thể thay thế cho nhau.

## 2. Đường đi của chuỗi qua một kết nối MySQL

Giả sử ứng dụng gửi truy vấn:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE full_name = 'Nguyễn An';
~~~

Để xử lý literal tiếng Việt trong câu lệnh và trả kết quả về ứng dụng, MySQL cần biết byte client gửi được mã hóa theo character set nào và client có thể nhận kết quả theo character set nào.

Luồng khái niệm:

~~~text
Ứng dụng
  |
  | Mã hóa câu SQL thành byte theo charset client
  v
MySQL nhận câu lệnh
  |
  | character_set_client
  | Diễn giải byte client gửi
  v
Chuyển literal sang charset kết nối
  |
  | character_set_connection
  | collation_connection áp dụng cho literal
  v
Phân tích và thực thi SQL
  |
  | Đọc dữ liệu từ cột theo charset/collation của cột
  v
Chuyển dữ liệu kết quả
  |
  | character_set_results
  v
Ứng dụng nhận byte và giải mã để hiển thị
~~~

Ba biến tham gia vào các đoạn khác nhau:

1. **Client gửi lên:** MySQL giả định byte của câu lệnh được mã hóa theo character_set_client.
2. **Server xử lý literal:** MySQL chuyển literal từ character_set_client sang character_set_connection; collation_connection ảnh hưởng đến phép so sánh chuỗi literal trong các trường hợp áp dụng.
3. **Server trả về:** MySQL chuyển dữ liệu kết quả sang character_set_results nếu biến này không phải NULL.

Nếu ứng dụng gửi byte UTF-8 nhưng khai báo character_set_client là một encoding khác, MySQL có thể diễn giải sai byte ngay từ đầu. Nếu server trả UTF-8 nhưng ứng dụng lại giải mã bằng encoding khác, dữ liệu có thể bị hiển thị sai ở phía client.

## 3. character_set_client: MySQL diễn giải dữ liệu nhận từ client

### 3.1. Vai trò

character_set_client cho MySQL biết byte trong câu lệnh SQL do client gửi được mã hóa theo character set nào. Điều này quan trọng với literal chuỗi, tên đối tượng có ký tự đặc biệt và nội dung SQL chứa ký tự ngoài ASCII.

Ví dụ, ứng dụng gửi:

~~~sql
INSERT INTO customers (full_name)
VALUES ('Trần Thị Mai');
~~~

Nếu ứng dụng thực sự mã hóa câu lệnh bằng UTF-8 nhưng server hiểu byte đó theo một character set khác, nội dung literal có thể bị diễn giải sai hoặc phát sinh lỗi chuyển đổi.

### 3.2. Kiểm tra giá trị hiện tại

Trong một phiên kết nối:

~~~sql
SELECT @@SESSION.character_set_client;
~~~

Xem cùng lúc ba biến:

~~~sql
SHOW SESSION VARIABLES
WHERE Variable_name IN (
    'character_set_client',
    'character_set_connection',
    'character_set_results'
);
~~~

Có thể xem giá trị mặc định toàn server:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'character_set_client';
~~~

Giá trị SESSION mới là giá trị áp dụng cho câu lệnh đang chạy trong kết nối hiện tại. Thay đổi GLOBAL không nhất thiết thay đổi ngay các phiên đã mở.

### 3.3. Khi nào cần thay đổi?

Trong ứng dụng hiện đại, nên cấu hình connector gửi dữ liệu theo UTF-8 và thương lượng hoặc thiết lập phiên MySQL phù hợp. Với MySQL 8.x, utf8mb4 thường là lựa chọn thích hợp cho dữ liệu Unicode.

Không nên đặt character_set_client theo cảm tính. Giá trị phải phản ánh encoding byte mà client thực sự gửi. Nếu client gửi UTF-8 mà khai báo latin1, đổi sang utf8mb4 ở server sau khi byte đã bị gửi sai không thể khôi phục nội dung ban đầu.

## 4. character_set_connection: character set dùng để xử lý literal

### 4.1. Vai trò

Sau khi nhận câu lệnh, MySQL chuyển literal từ character_set_client sang character_set_connection. Các chuỗi literal không có character set introducer thường sử dụng character set kết nối và collation kết nối làm mặc định.

Một literal có thể khai báo character set tường minh bằng introducer:

~~~sql
SELECT _utf8mb4'Tiếng Việt 🙂' AS explicit_charset_text;
~~~

Introducer chỉ định character set của literal đó; nó không thay đổi ba biến phiên và không sửa được byte đã bị client mã hóa sai trước khi gửi.

Ví dụ:

~~~sql
SELECT
    'Xin chào' AS greeting,
    CHARSET('Xin chào') AS literal_charset,
    COLLATION('Xin chào') AS literal_collation;
~~~

Kết quả CHARSET và COLLATION giúp quan sát character set và collation mà MySQL gán cho literal trong ngữ cảnh phiên hiện tại.

### 4.2. Collation kết nối

Biến collation_connection đi cùng character_set_connection. Nó xác định collation mặc định cho các literal chuỗi trong kết nối và có thể ảnh hưởng đến kết quả so sánh giữa các biểu thức chuỗi theo quy tắc coercibility của MySQL.

Kiểm tra:

~~~sql
SHOW SESSION VARIABLES
WHERE Variable_name IN (
    'character_set_connection',
    'collation_connection'
);
~~~

Ví dụ:

~~~sql
SELECT
    COLLATION('A') AS current_collation,
    ('a' = 'A') AS equal_under_collation;
~~~

Kết quả so sánh phụ thuộc collation áp dụng cho biểu thức. Với collation không phân biệt hoa thường, hai literal có thể được xem là bằng nhau. Với collation phân biệt hoa thường, kết quả có thể khác.

Collation của cột vẫn là một phần quan trọng trong phép so sánh. Khi biểu thức kết hợp literal với cột, MySQL áp dụng quy tắc chọn collation giữa các operand; không nên suy luận rằng chỉ cần thay collation_connection là mọi phép so sánh trong schema đều đổi theo.

### 4.3. Chuyển đổi có thể thất bại

MySQL phải chuyển chuỗi từ character_set_client sang character_set_connection. Nếu character set đích không thể biểu diễn một ký tự, chuyển đổi có thể phát sinh lỗi hoặc mất thông tin tùy ngữ cảnh và quy tắc chuyển đổi.

Ví dụ, một character set cũ không thể biểu diễn mọi ký tự Unicode. Dùng utf8mb4 ở cả phía client và connection giúp tránh nhiều lỗi khi câu lệnh chứa tiếng Việt, ký tự bổ sung hoặc emoji.

## 5. character_set_results: character set của dữ liệu trả về

### 5.1. Vai trò

character_set_results cho MySQL biết character set mà client mong đợi khi nhận result set. Server chuyển đổi dữ liệu chuỗi trong kết quả, metadata và thông báo lỗi theo cấu hình này trước khi gửi về client.

Ví dụ:

~~~sql
SELECT customer_id, full_name
FROM customers
ORDER BY customer_id;
~~~

Nếu cột full_name dùng utf8mb4 nhưng character_set_results của phiên là một character set không thể biểu diễn ký tự trong dữ liệu, việc chuyển đổi kết quả có thể thất bại hoặc không giữ nguyên nội dung như mong muốn.

### 5.2. Kiểm tra

~~~sql
SELECT @@SESSION.character_set_results;
~~~

Hoặc:

~~~sql
SHOW SESSION VARIABLES LIKE 'character_set_results';
~~~

Giá trị NULL có ý nghĩa đặc biệt: server không thực hiện bước chuyển đổi character set cho kết quả. Khi đó client phải hiểu và giải mã byte được gửi theo encoding thực tế mà server cung cấp.

Không nên đặt NULL trừ khi ứng dụng hoặc giao thức client biết chính xác cách xử lý kết quả không qua chuyển đổi. Với ứng dụng thông thường, để connector quản lý character_set_results phù hợp sẽ an toàn và dễ bảo trì hơn.

### 5.3. Kết quả không chỉ gồm giá trị cột

character_set_results còn liên quan đến cách server gửi metadata và thông báo lỗi có nội dung chuỗi. Vì vậy, khi gặp lỗi hiển thị sai ở cả dữ liệu lẫn thông báo server, cần kiểm tra đường truyền kết quả chứ không chỉ kiểm tra charset của bảng.

## 6. Thiết lập ba biến bằng SET NAMES

### 6.1. Cú pháp

SET NAMES là cách thuận tiện để thiết lập các biến character set chính của phiên:

~~~sql
SET NAMES utf8mb4;
~~~

Lệnh này tương đương về mục tiêu với việc thiết lập:

~~~sql
SET character_set_client = utf8mb4;
SET character_set_connection = utf8mb4;
SET character_set_results = utf8mb4;
~~~

Khi thực hiện SET NAMES, MySQL cũng đặt collation_connection theo collation mặc định của character set nếu không chỉ định COLLATE. Có thể chỉ định collation rõ ràng:

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh này cũng thiết lập collation_connection theo collation đã chọn.

### 6.2. Phạm vi tác động

SET NAMES thay đổi cấu hình của phiên hiện tại. Nó không tự thay đổi character set và collation mặc định của database, bảng hoặc cột. Nó cũng không tự chuyển đổi dữ liệu đã lưu trong bảng.

Nếu chạy SET NAMES trong một kết nối, các kết nối khác không bị ảnh hưởng. Khi kết nối đóng, thay đổi session đó không trở thành cấu hình mặc định bền vững cho server.

### 6.3. Vì sao không nên chỉ đổi một biến?

Nếu chỉ đổi character_set_client mà không đổi character_set_connection và character_set_results, đường đi của chuỗi có thể không đồng nhất. Client gửi một encoding, server diễn giải literal theo encoding khác và trả kết quả theo một encoding thứ ba.

SET NAMES giúp thiết lập đồng bộ ba biến theo cùng một character set. Tuy nhiên, khi dùng connector hiện đại, nên ưu tiên cấu hình charset qua API hoặc thuộc tính kết nối của driver. Một số driver duy trì trạng thái encoding riêng; gửi SET NAMES thủ công có thể làm trạng thái client và server lệch nhau nếu driver không biết thay đổi đó.

## 7. Phân biệt SET NAMES và SET CHARACTER SET

Hai lệnh này có hành vi khác nhau:

| Lệnh | character_set_client | character_set_connection | character_set_results | collation_connection |
|---|---|---|---|---|
| SET NAMES utf8mb4 | utf8mb4 | utf8mb4 | utf8mb4 | Collation mặc định của utf8mb4 |
| SET CHARACTER SET utf8mb4 | utf8mb4 | Character set mặc định của database hiện tại (hoặc server nếu không có database mặc định) | utf8mb4 | Collation mặc định tương ứng của database (hoặc server) |

SET CHARACTER SET đặt character_set_client và character_set_results theo character set được chỉ định, còn character_set_connection và collation_connection theo mặc định của database hiện tại. Nếu chưa chọn database, giá trị mặc định của server được dùng.

Ví dụ:

~~~sql
USE shop;
SET CHARACTER SET utf8mb4;

SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.collation_connection;
~~~

Nếu database có default character set hoặc collation khác với mong đợi, character_set_connection sau SET CHARACTER SET có thể không giống utf8mb4. Khi mục tiêu là thiết lập cả ba biến về cùng utf8mb4, SET NAMES thường rõ ràng hơn.

## 8. Phân biệt charset của kết nối với charset của database, table và column

Ba biến đang học điều khiển giao tiếp của một phiên client. Chúng không thay thế các thiết lập charset ở cấp schema.

MySQL có các phạm vi cấu hình khác:

| Phạm vi | Biến hoặc metadata | Ý nghĩa |
|---|---|---|
| Server | character_set_server, collation_server | Giá trị mặc định ở cấp server |
| Database | DEFAULT CHARACTER SET, DEFAULT COLLATE | Giá trị mặc định cho đối tượng mới trong database |
| Table | DEFAULT CHARSET, COLLATE trong DDL | Giá trị mặc định cho cột chuỗi mới của bảng |
| Column | CHARACTER SET, COLLATE của cột | Cách lưu và so sánh chuỗi trong cột đó |
| Connection | character_set_client, character_set_connection, character_set_results | Cách diễn giải câu lệnh, xử lý literal và trả kết quả cho một phiên |

Ví dụ xem thiết lập database:

~~~sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'shop';
~~~

Xem charset và collation của cột:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND CHARACTER_SET_NAME IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
~~~

Đặt charset mặc định cho database mới:

~~~sql
CREATE DATABASE shop_utf8
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Đặt charset mặc định cho bảng:

~~~sql
CREATE TABLE notes (
    note_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    body TEXT NOT NULL,
    PRIMARY KEY (note_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Nếu một cột đã có character set riêng, thay đổi charset kết nối không tự thay đổi charset của cột. Ngược lại, đổi charset của bảng không tự bảo đảm ứng dụng gửi và nhận byte đúng encoding.

## 9. Ví dụ thực hành với dữ liệu tiếng Việt và emoji

### 9.1. Kiểm tra cấu hình phiên

Kết nối đến MySQL và chạy:

~~~sql
SELECT
    @@SESSION.character_set_client AS client_charset,
    @@SESSION.character_set_connection AS connection_charset,
    @@SESSION.character_set_results AS results_charset,
    @@SESSION.collation_connection AS connection_collation;
~~~

Với một ứng dụng Unicode hiện đại, cấu hình thường mong muốn là utf8mb4 cho cả ba biến và một collation phù hợp với yêu cầu so sánh chuỗi.

### 9.2. Thử truyền literal

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

SELECT
    'Tiếng Việt có dấu' AS vietnamese_text,
    '🙂' AS emoji_text,
    CHARSET('Tiếng Việt có dấu') AS literal_charset,
    COLLATION('Tiếng Việt có dấu') AS literal_collation;
~~~

Nếu terminal hoặc công cụ SQL hiển thị sai, cần xác định lỗi ở lớp nào: terminal, driver, character_set_client, character_set_connection, character_set_results hay font. Không phải mọi lỗi hiển thị đều bắt nguồn từ MySQL.

### 9.3. Thử lưu và đọc

~~~sql
CREATE TABLE IF NOT EXISTS charset_demo (
    demo_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    message VARCHAR(200) NOT NULL,
    PRIMARY KEY (demo_id)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

INSERT INTO charset_demo (message)
VALUES ('Xin chào Việt Nam 🙂');

SELECT demo_id, message
FROM charset_demo
ORDER BY demo_id DESC
LIMIT 1;
~~~

Thử nghiệm này chỉ nên chạy trên database kiểm thử hoặc bảng được phép tạo. Nếu lưu dữ liệu sản xuất, cần dùng migration và quy trình quản lý schema của dự án.

## 10. Ví dụ lỗi do charset không đồng nhất

Giả sử ứng dụng mã hóa chuỗi bằng UTF-8 nhưng kết nối khai báo character_set_client là latin1. Byte UTF-8 có thể bị diễn giải như các ký tự latin1 riêng biệt. Tùy chuỗi và bước chuyển đổi, kết quả có thể thành mojibake hoặc phát sinh lỗi khi chuyển sang character_set_connection.

Một trường hợp khác: client và server giao tiếp đúng UTF-8, dữ liệu được lưu đúng trong cột utf8mb4, nhưng character_set_results lại là một character set không thể biểu diễn một số ký tự. Khi server chuyển kết quả, dữ liệu có thể bị lỗi hoặc không thể trả về nguyên vẹn.

Ngược lại, nếu server gửi byte UTF-8 nhưng ứng dụng giải mã theo Windows-1252 hoặc latin1, người dùng vẫn có thể thấy ký tự sai dù dữ liệu trong database hoàn toàn đúng.

Các bước điều tra:

1. Kiểm tra encoding mà ứng dụng thực sự dùng để mã hóa request.
2. Kiểm tra character_set_client, character_set_connection và character_set_results của đúng session.
3. Kiểm tra character set và collation của database, bảng và cột.
4. Xác định dữ liệu sai ngay khi gửi lên, khi lưu, hay chỉ khi đọc và hiển thị.
5. Dùng dữ liệu thử có tiếng Việt, ký tự ngoài BMP và emoji để tái hiện.
6. Sửa cấu hình ở đúng lớp rồi kiểm thử cả INSERT, SELECT, so sánh và sắp xếp.

Không nên sửa dữ liệu đã bị mojibake bằng cách đổi charset kết nối một cách ngẫu nhiên. Trước tiên cần xác định byte gốc đang được lưu là gì và lớp nào đã diễn giải sai; nếu không, thao tác chuyển đổi có thể làm hỏng dữ liệu thêm.

## 11. Cách cấu hình trong ứng dụng

### 11.1. Để connector quản lý kết nối

Với JDBC, Python, .NET, PHP hoặc Node.js, nên cấu hình encoding và collation bằng tùy chọn chính thức của connector. Driver có thể thiết lập charset khi bắt tay, gửi lệnh phiên hoặc quản lý cách encode/decode ở phía client.

Không có một tên thuộc tính cấu hình chung cho mọi driver. Hãy dùng tài liệu đúng connector và phiên bản đang triển khai. Sau khi kết nối, có thể xác minh bằng truy vấn:

~~~sql
SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.collation_connection;
~~~

Nếu ứng dụng dùng connection pool, cần bảo đảm mọi kết nối vật lý trong pool được tạo với cấu hình nhất quán. Cũng cần chú ý việc thay đổi session state trên một connection rồi trả connection đó về pool: trạng thái có thể được giữ lại cho request tiếp theo nếu pool không reset session.

### 11.2. Khi dùng SET NAMES thủ công

Trong môi trường thử nghiệm hoặc client dòng lệnh, có thể dùng:

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

Với ứng dụng dùng driver quản lý charset, tránh gửi lệnh này tùy tiện sau khi driver đã khởi tạo kết nối. Nếu driver không được thông báo về thay đổi session, cách encode/decode ở client có thể lệch với cấu hình server.

### 11.3. Kiểm tra sau khi lấy connection từ pool

Khi ứng dụng mượn connection từ pool, nên dựa vào cấu hình pool/driver và cơ chế reset connection được hỗ trợ. Nếu code thay đổi session variable, hãy khôi phục trạng thái ban đầu trước khi trả kết nối hoặc cấu hình pool reset session phù hợp. Điều này ngăn request này ảnh hưởng request khác.

## 12. Những nhầm lẫn thường gặp

**“character_set_client là charset của cột.”** Không. Nó mô tả encoding mà MySQL dùng để diễn giải byte câu lệnh từ client.

**“character_set_connection quyết định charset của toàn bộ bảng.”** Không. Nó điều khiển character set mặc định cho literal và xử lý chuỗi trong phiên; charset của cột được định nghĩa riêng.

**“character_set_results quyết định cách MySQL lưu dữ liệu.”** Không. Nó điều khiển chuyển đổi kết quả gửi về client.

**“SET NAMES thay đổi charset của database.”** Không. SET NAMES thay đổi các biến của phiên kết nối.

**“utf8 trong MySQL luôn là UTF-8 đầy đủ.”** Trong MySQL, tên utf8 historically là alias của utf8mb3 ở các phiên bản hiện đại; utf8mb3 chỉ hỗ trợ tối đa ba byte cho mỗi ký tự. Dùng utf8mb4 khi cần đầy đủ Unicode, gồm emoji và ký tự ngoài BMP.

**“Đổi charset kết nối sẽ sửa dữ liệu đã lưu sai.”** Không. Nó chỉ thay đổi cách diễn giải hoặc chuyển đổi dữ liệu trong phiên. Muốn sửa dữ liệu đã bị lưu sai phải xác định encoding byte hiện có và lập kế hoạch chuyển đổi dữ liệu riêng.

**“Nếu MySQL trả chuỗi sai thì chắc chắn database lưu sai.”** Không. Lỗi có thể ở request encoding, cấu hình session, result conversion, driver, terminal hoặc font.

## 13. Checklist khi xử lý lỗi tiếng Việt

Khi gặp lỗi dấu tiếng Việt, ký tự đặc biệt hoặc emoji, hãy kiểm tra theo thứ tự:

1. Ứng dụng tạo chuỗi Unicode đúng trước khi gọi driver.
2. Connector được cấu hình để gửi và nhận UTF-8/utf8mb4.
3. character_set_client khớp encoding byte mà client gửi.
4. character_set_connection và collation_connection phù hợp với cách xử lý literal.
5. character_set_results phù hợp với encoding mà client giải mã.
6. Database, table và column có character set đủ khả năng biểu diễn dữ liệu.
7. Collation của cột phù hợp với quy tắc tìm kiếm, so sánh và sắp xếp.
8. Connection pool không giữ session state sai từ request trước.
9. Kiểm thử round-trip: ghi chuỗi rồi đọc lại và so sánh chính xác với chuỗi ban đầu.

Một truy vấn tổng hợp hữu ích:

~~~sql
SELECT
    @@SESSION.character_set_client AS character_set_client,
    @@SESSION.character_set_connection AS character_set_connection,
    @@SESSION.character_set_results AS character_set_results,
    @@SESSION.collation_connection AS collation_connection,
    @@GLOBAL.character_set_server AS character_set_server,
    @@GLOBAL.collation_server AS collation_server;
~~~

Truy vấn này giúp phân biệt cấu hình phiên với mặc định server. Để xác minh charset của cột, hãy truy vấn INFORMATION_SCHEMA.COLUMNS như ví dụ ở phần trước.

## Kết luận

character_set_client cho MySQL biết encoding của byte câu lệnh nhận từ client; character_set_connection xác định character set và collation mặc định dùng khi xử lý literal; character_set_results quyết định cách server chuyển dữ liệu, metadata và thông báo về client. Ba biến tạo thành một đường đi liên tục từ request đến response.

Với ứng dụng hiện đại, hãy dùng utf8mb4 xuyên suốt ở connector và các cột cần lưu Unicode, chọn collation theo yêu cầu so sánh, rồi xác minh cấu hình session thực tế. Khi phát hiện dữ liệu hiển thị sai, hãy xác định đúng lớp xảy ra lỗi trước khi chuyển đổi hoặc sửa dữ liệu. Cách tiếp cận này giúp bảo toàn tiếng Việt, emoji và dữ liệu đa ngôn ngữ trong ứng dụng MySQL.
