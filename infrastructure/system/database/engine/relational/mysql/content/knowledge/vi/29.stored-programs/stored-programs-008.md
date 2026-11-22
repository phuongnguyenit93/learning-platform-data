# Thời điểm lưu SQL mode cho stored program

MySQL lưu giá trị sql_mode đang có hiệu lực trong session tại thời điểm tạo stored program. Khi stored procedure hoặc stored function được gọi, MySQL thực thi phần thân chương trình với SQL mode đã lưu cùng object, thay vì đơn giản dùng SQL mode hiện tại của session gọi. Sau khi routine kết thúc, SQL mode của session gọi được khôi phục.

Điều này có nghĩa hai procedure được tạo ở hai thời điểm với hai SQL mode khác nhau có thể cho kết quả hoặc hành vi khác nhau, ngay cả khi được gọi từ cùng một connection và cùng một câu CALL. Đổi @@GLOBAL.sql_mode hoặc @@SESSION.sql_mode sau khi tạo routine không tự cập nhật SQL mode đã lưu của routine hiện có.

Trong module **DATABASE_MYSQL**, stored program giúp đóng gói logic SQL ở phía server. Muốn hành vi của procedure/function ổn định giữa môi trường phát triển, staging và production, cần kiểm soát SQL mode của connection chạy DDL, biết cách kiểm tra metadata và có quy trình tạo lại routine khi cần đổi mode.

## 1. SQL mode là gì?

sql_mode là biến hệ thống chứa một hoặc nhiều chế độ ảnh hưởng đến cách MySQL phân tích câu lệnh, kiểm tra dữ liệu và xử lý một số trường hợp đặc biệt.

Kiểm tra SQL mode của session và server:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.sql_mode AS global_sql_mode;
```

- @@SESSION.sql_mode áp dụng cho connection hiện tại.
- @@GLOBAL.sql_mode là giá trị mặc định được dùng khi khởi tạo session mới; thay đổi nó không tự thay đổi session đang tồn tại.
- Stored program lưu SQL mode của session thực hiện lệnh CREATE tại thời điểm object được tạo.

Không nên cho rằng global mode và session mode luôn giống nhau. Connection pool có thể giữ connection được tạo từ trước, ứng dụng có thể đặt session mode riêng, và migration tool có thể sử dụng một connection khác với connection chạy ứng dụng.

### 1.1. Một số SQL mode thường gặp

| SQL mode | Ảnh hưởng tiêu biểu |
|---|---|
| STRICT_TRANS_TABLES | Xử lý nghiêm ngặt nhiều giá trị không hợp lệ khi ghi vào transactional table; trường hợp lỗi phụ thuộc statement và storage engine |
| STRICT_ALL_TABLES | Áp dụng strict behavior rộng hơn cho các storage engine |
| ANSI_QUOTES | Dấu nháy kép dùng để quote identifier thay vì string literal |
| NO_BACKSLASH_ESCAPES | Dấu gạch chéo ngược không còn là ký tự escape trong string literal |
| PIPES_AS_CONCAT | || được hiểu là phép nối chuỗi thay vì toán tử OR |
| ONLY_FULL_GROUP_BY | Giới hạn các biểu thức SELECT/HAVING/ORDER BY không được nhóm hoặc không phụ thuộc hàm vào cột GROUP BY theo quy tắc MySQL |
| NO_ENGINE_SUBSTITUTION | Không âm thầm thay storage engine khi engine được yêu cầu không khả dụng |

SQL mode là danh sách kết hợp. Một giá trị session có thể chứa nhiều mode, phân tách bằng dấu phẩy. Tập mode mặc định thay đổi giữa các phiên bản MySQL, vì vậy nên kiểm tra và cấu hình tường minh thay vì dựa vào default của máy.

## 2. Thời điểm SQL mode được lưu

Khi chạy CREATE PROCEDURE hoặc CREATE FUNCTION, MySQL ghi lại giá trị @@SESSION.sql_mode của connection thực hiện DDL vào metadata của routine.

Vòng đời có thể hình dung như sau:

1. Migration connection được mở.
2. Session SQL mode được thiết lập.
3. CREATE PROCEDURE hoặc CREATE FUNCTION được thực thi.
4. MySQL lưu SQL mode cùng định nghĩa routine.
5. Một session khác gọi routine.
6. Routine chạy với SQL mode đã lưu khi tạo.
7. Khi routine trả về, session caller tiếp tục với SQL mode trước lúc gọi.

Ví dụ: procedure A được tạo với ANSI_QUOTES; procedure B được tạo khi mode rỗng. Cùng một connection gọi cả hai thì A và B vẫn giữ mode riêng của chúng.

SQL mode được lưu ở cấp từng stored program. Đổi mode cho một routine không tự đổi mode của các routine khác trong cùng schema.

### 2.1. SQL mode lúc tạo khác SQL mode lúc gọi

Giả sử:

```sql
-- Connection tạo procedure
SET SESSION sql_mode = 'ANSI_QUOTES';

DELIMITER //
CREATE PROCEDURE p_created_with_ansi()
BEGIN
    SELECT "status" AS result;
END//
DELIMITER ;
```

Sau đó một connection khác có thể dùng mode khác:

```sql
SET SESSION sql_mode = '';

CALL p_created_with_ansi();
```

Procedure vẫn chạy theo mode đã lưu khi tạo. Với ANSI_QUOTES, "status" được phân tích như identifier. Nếu không có cột hoặc đối tượng tên status trong ngữ cảnh SELECT, câu lệnh có thể báo lỗi unknown column; nếu có cột đó, nó trả giá trị cột.

Không được kết luận rằng SET SESSION sql_mode = '' ở caller sẽ biến "status" bên trong procedure thành string literal. Stored program có SQL mode riêng.

## 3. SQL mode ảnh hưởng cả cách phân tích lẫn cách thực thi

Một số mode thay đổi cách parser hiểu cú pháp. Những mode khác ảnh hưởng việc kiểm tra và chuyển đổi dữ liệu khi câu lệnh chạy.

Ví dụ:

- ANSI_QUOTES thay đổi ý nghĩa dấu nháy kép trong câu SQL.
- NO_BACKSLASH_ESCAPES thay đổi cách dấu gạch chéo ngược được xử lý trong string literal.
- PIPES_AS_CONCAT thay đổi ý nghĩa toán tử ||.
- STRICT_TRANS_TABLES ảnh hưởng cách MySQL xử lý giá trị không hợp lệ khi ghi dữ liệu.
- ONLY_FULL_GROUP_BY ảnh hưởng việc chấp nhận một số biểu thức trong truy vấn nhóm.

Do đó, thay đổi SQL mode sau khi routine đã được tạo có thể không có hiệu lực như mong đợi. Một routine có thể tiếp tục dùng cách diễn giải SQL cũ cho đến khi được tạo lại với mode mới.

### 3.1. Ví dụ với ANSI_QUOTES

Khi không bật ANSI_QUOTES:

```sql
SELECT "status" AS result;
```

"status" được hiểu là string literal và kết quả là chuỗi status.

Khi bật ANSI_QUOTES:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';

SELECT "status" AS result
FROM orders;
```

Trong ví dụ này, cột status được tham chiếu tường minh. Khi dùng ANSI_QUOTES, "status" cũng được phân tích như tên cột status. Đây là khác biệt có thể làm routine trả kết quả khác hoặc báo lỗi sau khi triển khai sang môi trường có mode khác.

Để code dễ đọc và ít phụ thuộc mode hơn, hãy dùng dấu nháy đơn cho string literal và quote identifier nhất quán theo quy ước của dự án.

```sql
SELECT status AS result
FROM orders
WHERE status = 'PAID';
```

Không nên dùng dấu nháy kép một cách tùy tiện nếu môi trường có thể bật ANSI_QUOTES.

## 4. Thực nghiệm: hai procedure được tạo với hai SQL mode khác nhau

Thực nghiệm này cho thấy mode được lưu tại thời điểm CREATE, không phải lấy lại từ caller ở mỗi lần CALL.

Tạo bảng thử:

```sql
CREATE TABLE sql_mode_demo (
    id INT NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

INSERT INTO sql_mode_demo (id, status)
VALUES (1, 'PAID');
```

Dùng MySQL command-line client. DELIMITER là lệnh của client để nhận biết dấu kết thúc routine; nó không phải câu SQL gửi trực tiếp tới server.

Tạo procedure với ANSI_QUOTES:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';

DELIMITER //
CREATE PROCEDURE p_identifier_mode()
BEGIN
    SELECT "status" AS result
    FROM sql_mode_demo
    WHERE id = 1;
END//
DELIMITER ;
```

Tạo procedure khác khi ANSI_QUOTES tắt:

```sql
SET SESSION sql_mode = '';

DELIMITER //
CREATE PROCEDURE p_literal_mode()
BEGIN
    SELECT "status" AS result
    FROM sql_mode_demo
    WHERE id = 1;
END//
DELIMITER ;
```

Bây giờ đặt session caller về ANSI_QUOTES rồi gọi cả hai:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';

CALL p_identifier_mode();
CALL p_literal_mode();

SELECT @@SESSION.sql_mode;
```

Kết quả kỳ vọng:

| Procedure | SQL mode lúc tạo | Ý nghĩa của "status" trong routine | Kết quả |
|---|---|---|---|
| p_identifier_mode | ANSI_QUOTES | Identifier/cột status | PAID |
| p_literal_mode | Mode rỗng | String literal | status |

Dù caller đang bật ANSI_QUOTES, p_literal_mode vẫn thực thi theo mode đã lưu lúc tạo. Sau mỗi CALL, session caller tiếp tục với mode của chính nó; câu SELECT cuối vẫn cho thấy ANSI_QUOTES.

Nếu dùng JDBC hoặc một migration framework thay vì mysql client, không gửi DELIMITER như SQL. Gửi toàn bộ câu CREATE PROCEDURE ... BEGIN ... END như một statement theo cách driver hỗ trợ.

## 5. Ví dụ với strict mode và chuyển đổi dữ liệu

Strict mode có thể làm một routine từ chối giá trị không hợp lệ mà routine khác được tạo ở mode không strict có thể chuyển đổi và phát warning.

Tạo bảng lab:

```sql
CREATE TABLE sql_mode_insert_demo (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    amount INT NOT NULL
) ENGINE = InnoDB;
```

Tạo procedure trong strict mode:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

DELIMITER //
CREATE PROCEDURE p_insert_strict()
BEGIN
    INSERT INTO sql_mode_insert_demo (amount)
    VALUES ('not-a-number');
END//
DELIMITER ;
```

Tạo procedure khi strict mode tắt:

```sql
SET SESSION sql_mode = 'NO_ENGINE_SUBSTITUTION';

DELIMITER //
CREATE PROCEDURE p_insert_non_strict()
BEGIN
    INSERT INTO sql_mode_insert_demo (amount)
    VALUES ('not-a-number');
END//
DELIMITER ;
```

Gọi hai procedure trong một session có strict mode:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

CALL p_insert_strict();
CALL p_insert_non_strict();

SELECT *
FROM sql_mode_insert_demo;
```

Với InnoDB, procedure được tạo dưới strict mode dự kiến báo lỗi chuyển đổi dữ liệu ở lệnh INSERT. Procedure được tạo trong mode không strict có thể chuyển giá trị không hợp lệ thành giá trị số mặc định như 0 và phát warning. Hãy đọc lỗi/warning trên đúng phiên bản và cấu hình server đang dùng.

Thực nghiệm này minh họa rủi ro vận hành: một routine tạo ở môi trường permissive có thể tiếp tục nhận dữ liệu theo behavior đó sau khi ứng dụng chuyển sang môi trường strict. Cấu hình strict mode cho connection chạy migration trước khi tạo routine là một phần của kiểm soát chất lượng schema.

## 6. Session mode và global mode khi triển khai

SET GLOBAL sql_mode thay đổi giá trị mặc định cho các session được tạo sau đó. Nó không tự đổi mode của connection hiện tại và cũng không sửa SQL mode đã lưu trong stored program.

Ví dụ:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;

SET GLOBAL sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

Sau câu SET GLOBAL, hai giá trị có thể khác nhau vì session hiện tại vẫn giữ mode trước đó. Một connection mới thường khởi tạo session mode theo global mode tại thời điểm kết nối, trừ khi client hoặc cấu hình connection đặt giá trị khác.

Để tạo routine với mode đã chọn, hãy thiết lập session mode trên chính connection thực hiện CREATE:

```sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;

CREATE PROCEDURE ...;
```

Không chỉ SET GLOBAL rồi giả định migration connection đã nhận giá trị mới.

### 6.1. Connection pool và migration connection

Connection pool thường tái sử dụng connection lâu dài. Nếu một connection đã được mở trước khi global mode thay đổi, session của nó có thể vẫn giữ mode cũ. Một migration tool cũng có thể mở connection với cấu hình riêng.

Quy trình đáng tin cậy:

1. Dùng connection riêng cho migration.
2. Đọc @@SESSION.sql_mode trước khi chạy DDL.
3. Thiết lập mode mong muốn bằng SET SESSION.
4. Đọc lại giá trị để xác nhận.
5. Tạo routine trên chính connection đó.
6. Kiểm tra SQL mode đã lưu trong metadata.
7. Sau khi migration kết thúc, đóng connection hoặc khôi phục session mode nếu tiếp tục tái sử dụng connection.

Không dựa vào mode của connection ứng dụng để suy ra mode của migration connection.

## 7. Kiểm tra SQL mode đã lưu của stored program

### 7.1. SHOW CREATE PROCEDURE

Lệnh:

```sql
SHOW CREATE PROCEDURE p_identifier_mode;
```

Kết quả có cột sql_mode cùng phần Create Procedure, character_set_client, collation_connection và metadata liên quan. Trường sql_mode cho biết mode được lưu khi routine được tạo.

Với function:

```sql
SHOW CREATE FUNCTION calculate_total;
```

Đây là cách trực tiếp để kiểm tra một routine cụ thể.

### 7.2. INFORMATION_SCHEMA.ROUTINES

Có thể xem các routine trong schema hiện tại:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    SQL_MODE,
    DEFINER,
    SECURITY_TYPE,
    CREATED,
    LAST_ALTERED
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

Cột SQL_MODE là metadata của routine. Giá trị có thể là danh sách mode phân tách bằng dấu phẩy hoặc chuỗi rỗng nếu routine được tạo khi session không bật mode nào.

Quyền xem metadata phụ thuộc quyền truy cập của account. Nếu không thấy object, kiểm tra schema và grants trước khi kết luận routine không tồn tại.

### 7.3. Không sửa trực tiếp system table

Trong MySQL 8.0, metadata stored program được quản lý bởi data dictionary. Không sửa trực tiếp bảng hệ thống nội bộ để thay đổi SQL mode. Dùng DDL được hỗ trợ và kiểm tra metadata qua SHOW CREATE hoặc INFORMATION_SCHEMA.

## 8. Có thể đổi SQL mode của routine bằng ALTER PROCEDURE không?

Không có mệnh đề SQL_MODE trong cú pháp ALTER PROCEDURE để thay đổi mode đã lưu. ALTER PROCEDURE dùng để thay đổi một số characteristics như comment hoặc SQL SECURITY, không thay đổi phần thân routine và không đặt lại SQL mode đã lưu.

Muốn thay đổi SQL mode, cần tạo lại routine dưới session mode mới:

1. Ghi nhận định nghĩa hiện tại bằng SHOW CREATE PROCEDURE.
2. Ghi nhận grants và các dependency liên quan.
3. Chuẩn bị script CREATE với định nghĩa mong muốn.
4. Đặt @@SESSION.sql_mode trước khi CREATE.
5. Thực hiện migration có kiểm soát.
6. Kiểm tra SHOW CREATE PROCEDURE và INFORMATION_SCHEMA.ROUTINES.
7. Kiểm thử bằng caller có quyền thực tế.

Ví dụ khung triển khai:

```sql
-- Chạy trên migration connection với quyền phù hợp.
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

-- Dùng định nghĩa đầy đủ đã được review để tạo lại routine.
-- DROP/CREATE có thể làm gián đoạn caller trong thời gian migration.
DROP PROCEDURE IF EXISTS p_identifier_mode;

DELIMITER //
CREATE PROCEDURE p_identifier_mode()
BEGIN
    SELECT status AS result
    FROM sql_mode_demo
    WHERE id = 1;
END//
DELIMITER ;

SHOW CREATE PROCEDURE p_identifier_mode;
```

Đây là khung minh họa. Trong production, không chạy DROP trước khi đã chuẩn bị bản CREATE hợp lệ và kế hoạch rollback. Việc drop/recreate có thể ảnh hưởng quyền EXECUTE đã cấp và các ứng dụng gọi routine; kiểm tra và cấp lại grants cần thiết sau migration.

Nếu chỉ cần thay đổi comment hoặc một characteristic mà ALTER PROCEDURE hỗ trợ, dùng ALTER PROCEDURE. Nếu mục tiêu là đổi SQL mode đã lưu, cần tạo lại object.

## 9. Stored function, trigger và event

Cơ chế lưu SQL mode không chỉ áp dụng cho procedure.

- Stored procedure và stored function lưu SQL mode khi được tạo.
- Trigger lưu SQL mode tại thời điểm CREATE TRIGGER.
- Event lưu SQL mode tại thời điểm CREATE EVENT và dùng mode đó khi event scheduler thực thi event.

Vì mỗi object có metadata riêng, không nên chỉ kiểm tra procedure mà bỏ qua trigger hoặc event có liên quan đến cùng luồng dữ liệu.

### 9.1. Kiểm tra trigger

```sql
SHOW CREATE TRIGGER orders_before_insert;
```

Hoặc:

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    SQL_MODE,
    DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY TRIGGER_NAME;
```

Nếu cần thay đổi SQL mode của trigger, tạo lại trigger trong session đã đặt mode mong muốn. Kiểm tra lại metadata sau DDL.

### 9.2. Kiểm tra event

```sql
SHOW CREATE EVENT purge_old_orders;
```

Hoặc:

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    STATUS,
    SQL_MODE,
    DEFINER,
    LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
```

Event được thực thi bởi Event Scheduler, không phải trực tiếp bởi session của người dùng đang gọi một procedure. Vì vậy, không thể dựa vào @@SESSION.sql_mode của ứng dụng để suy ra mode của event.

### 9.3. Routine gọi routine khác

Khi một stored program gọi routine khác, mỗi routine có SQL mode được lưu riêng. Hãy kiểm tra mode của từng routine trong chuỗi gọi, đặc biệt khi procedure cũ gọi function mới hoặc ngược lại. Không giả định rằng mode của routine ngoài sẽ trở thành mode tạo ra của routine bên trong.

Trigger được kích hoạt bởi DML trong routine cũng có SQL mode riêng đã lưu lúc tạo trigger. Điều này quan trọng khi cùng một câu INSERT đi qua trigger và procedure có các mode khác nhau.

## 10. SQL mode khác với SQL SECURITY và routine characteristics

Không nhầm sql_mode với các thuộc tính khác của stored program.

| Thuộc tính | Vai trò |
|---|---|
| SQL_MODE | Chế độ SQL được lưu khi tạo và dùng khi thực thi stored program |
| SQL SECURITY DEFINER/INVOKER | Security context dùng để kiểm tra quyền truy cập object |
| DETERMINISTIC / NOT DETERMINISTIC | Khai báo routine có trả cùng kết quả với cùng input theo semantics của routine hay không |
| CONTAINS SQL, READS SQL DATA, MODIFIES SQL DATA, NO SQL | Khai báo đặc tính truy cập dữ liệu của routine |
| COMMENT | Mô tả routine |

Ví dụ routine có thể là SQL SECURITY INVOKER nhưng vẫn lưu STRICT_TRANS_TABLES làm SQL mode. Hai thiết lập giải quyết hai vấn đề độc lập: một bên là quyền, một bên là cách SQL được xử lý.

## 11. Chuẩn hóa SQL mode cho nhiều môi trường

Nếu dev, staging và production dùng SQL mode khác nhau, cùng một script CREATE có thể tạo ra routine có metadata khác nhau. Điều đó làm hành vi runtime khó dự đoán.

Một quy trình chuẩn hóa nên:

- Chốt danh sách SQL mode mà ứng dụng yêu cầu.
- Đặt mode tường minh trong migration trước DDL routine.
- Không dựa vào default của phiên bản MySQL hoặc cấu hình máy.
- Ghi lại SELECT @@SESSION.sql_mode trong log migration.
- Kiểm tra SQL_MODE sau CREATE bằng SHOW CREATE hoặc INFORMATION_SCHEMA.
- Đưa kiểm tra metadata vào bước xác nhận deployment.
- Khi thay đổi mode, tạo lại routine theo quy trình có kiểm soát.
- Đồng bộ procedure, function, trigger và event có liên quan.
- Kiểm thử trên phiên bản MySQL mục tiêu vì tập mode được hỗ trợ có thể thay đổi.

Ví dụ kiểm tra trước khi migration:

```sql
SELECT
    VERSION() AS mysql_version,
    @@SESSION.sql_mode AS migration_session_sql_mode,
    @@GLOBAL.sql_mode AS server_default_sql_mode;
```

Sau khi tạo routine, xác minh:

```sql
SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
  AND ROUTINE_NAME = 'p_identifier_mode';
```

Đừng chỉ xác nhận CREATE PROCEDURE trả về thành công. Hãy kiểm tra mode được lưu đúng với kỳ vọng.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ routine dùng SQL mode hiện tại của caller | Hành vi khác với mode đã lưu | Kiểm tra SQL_MODE của routine |
| Chỉ SET GLOBAL trước migration | Connection hiện tại có thể vẫn giữ session mode cũ | SET SESSION trên đúng migration connection |
| Đổi SQL mode sau CREATE và mong routine tự đổi | Routine tiếp tục dùng mode cũ | Tạo lại routine với mode mới |
| Dùng default SQL mode của từng môi trường | Dev/staging/prod có thể tạo routine khác nhau | Đặt mode tường minh trong migration |
| Chỉ kiểm tra procedure, bỏ qua trigger/event | Luồng DML vẫn có object chạy với mode khác | Kiểm tra metadata mọi stored program liên quan |
| Nhầm SQL SECURITY với SQL_MODE | Cấu hình quyền và cú pháp bị lẫn lộn | Quản lý hai thuộc tính độc lập |
| Dùng dấu nháy kép cho string literal | Có thể thành identifier khi ANSI_QUOTES bật | Dùng dấu nháy đơn cho string |
| Drop/recreate mà quên grants | Account ứng dụng có thể mất EXECUTE | Ghi nhận và cấp lại quyền sau migration |
| Tin rằng ALTER PROCEDURE đổi SQL_MODE | Metadata không thay đổi như mong đợi | Recreate routine |
| Không kiểm tra phiên bản MySQL | Một số mode có thể khác hoặc không còn hỗ trợ | Kiểm tra VERSION() và tài liệu đúng phiên bản |

## 13. Checklist triển khai stored program

**Trước khi CREATE:**

- Xác định MySQL version và SQL mode chuẩn của ứng dụng.
- Dùng connection migration riêng.
- Đọc @@SESSION.sql_mode.
- Đặt SET SESSION sql_mode theo cấu hình mong muốn.
- Kiểm tra lại giá trị session trước DDL.
- Xác định mode ảnh hưởng đến quote, expression, grouping và data conversion trong routine.

**Sau khi CREATE:**

- Chạy SHOW CREATE PROCEDURE hoặc SHOW CREATE FUNCTION.
- Kiểm tra INFORMATION_SCHEMA.ROUTINES.SQL_MODE.
- Với trigger/event, kiểm tra SHOW CREATE và metadata tương ứng.
- Thử gọi routine từ session có SQL mode khác để xác nhận behavior được lưu.
- Kiểm tra lỗi và warning khi ghi dữ liệu.
- Kiểm tra quyền EXECUTE và security context riêng biệt.

**Khi thay đổi SQL mode:**

- Chuẩn bị định nghĩa routine mới.
- Ghi nhận grants và dependency.
- Tạo lại routine trong session mode mới.
- Kiểm tra lại metadata và behavior.
- Cấp lại grants nếu bị ảnh hưởng.
- Đồng bộ trigger/event/function liên quan.
- Có kế hoạch rollback nếu migration thất bại.

## 14. Ghi nhớ

- MySQL lưu @@SESSION.sql_mode của connection tại thời điểm tạo stored program.
- Procedure/function chạy theo SQL mode đã lưu, không đơn giản theo mode hiện tại của caller.
- Sau khi routine kết thúc, SQL mode của session caller được khôi phục.
- SET GLOBAL sql_mode không tự thay đổi session hiện tại và không sửa SQL mode đã lưu của routine.
- ANSI_QUOTES, NO_BACKSLASH_ESCAPES, PIPES_AS_CONCAT có thể thay đổi cách parser hiểu SQL; strict mode ảnh hưởng xử lý dữ liệu.
- Hai routine được tạo với mode khác nhau có thể hành xử khác nhau dù cùng được gọi từ một session.
- SHOW CREATE PROCEDURE, SHOW CREATE FUNCTION và INFORMATION_SCHEMA.ROUTINES cho biết mode đã lưu.
- Trigger và event cũng lưu SQL mode riêng tại thời điểm tạo.
- ALTER PROCEDURE không có clause để thay đổi SQL mode đã lưu; cần tạo lại routine.
- Kiểm soát SQL mode của migration connection giúp giữ hành vi nhất quán giữa dev, staging và production.
- SQL_MODE độc lập với SQL SECURITY, DETERMINISTIC và các routine characteristics khác.
- Không sửa trực tiếp system table để thay đổi metadata stored program.

SQL mode là một phần của định nghĩa vận hành stored program. Hãy thiết lập nó trên đúng session trước khi chạy CREATE, xác minh metadata sau khi tạo và xem việc đổi mode là một migration cần kiểm thử, không phải một thay đổi cấu hình có thể áp dụng hồi tố.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — SQL Modes: https://dev.mysql.com/doc/refman/8.0/en/sql-mode.html
- MySQL 8.0 Reference Manual — Stored Program Restrictions: https://dev.mysql.com/doc/refman/8.0/en/stored-program-restrictions.html
- MySQL 8.0 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION Statements: https://dev.mysql.com/doc/refman/8.0/en/create-procedure.html
- MySQL 8.0 Reference Manual — SHOW CREATE PROCEDURE Statement: https://dev.mysql.com/doc/refman/8.0/en/show-create-procedure.html
- MySQL 8.0 Reference Manual — The ROUTINES Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-routines-table.html
- MySQL 8.0 Reference Manual — The TRIGGERS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-triggers-table.html
- MySQL 8.0 Reference Manual — The EVENTS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-events-table.html

