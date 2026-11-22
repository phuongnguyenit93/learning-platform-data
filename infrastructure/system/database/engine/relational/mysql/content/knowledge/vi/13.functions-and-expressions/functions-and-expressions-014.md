# LAST_INSERT_ID, CONNECTION_ID và các giá trị gắn với phiên

Trong một ứng dụng bán hàng, sau khi tạo đơn hàng, ứng dụng thường cần lấy ngay ID vừa được MySQL cấp để ghi các dòng chi tiết. Khi một câu lệnh lỗi hoặc transaction rollback, ứng dụng phải biết có thể tin vào ID đó hay không. Khi điều tra một truy vấn chạy lâu, DBA lại cần xác định connection nào đang thực thi câu lệnh và connection đó đang dùng database, user hay SQL mode nào.

MySQL cung cấp `LAST_INSERT_ID()` để đọc giá trị `AUTO_INCREMENT` gần nhất của connection hiện tại và `CONNECTION_ID()` để nhận diện connection đang kết nối đến server. Ngoài ra, mỗi connection có session variables, user-defined variables và nhiều trạng thái riêng. Hiểu đúng phạm vi connection giúp tránh lấy nhầm ID, rò rỉ trạng thái qua connection pool và chẩn đoán nhầm session.

## 1. Connection và session trong MySQL

Một client kết nối đến MySQL Server tạo ra một connection. Trong suốt vòng đời connection, server duy trì trạng thái session gắn với connection đó. Trạng thái này có thể gồm:

- Connection ID do server cấp.
- Database mặc định, tài khoản kết nối và các giá trị nhận diện session.
- SQL mode, timezone, character set, collation và các session system variable khác.
- User-defined variables như `@current_order_id`.
- Giá trị do `LAST_INSERT_ID()` ghi nhớ.
- Transaction đang mở, isolation level và các lock mà transaction đang giữ.
- Temporary table, prepared statement và một số trạng thái khác gắn với session.

Hai connection khác nhau có trạng thái session riêng. Nếu connection A vừa insert một hàng có ID `101`, `LAST_INSERT_ID()` trên connection B không tự động trả về `101`. Tương tự, `SET @x = 10` trong A không làm `@x` xuất hiện trong B.

Session không đồng nghĩa với một HTTP request hoặc một transaction. Một connection có thể chạy nhiều transaction liên tiếp; với connection pool, cùng một connection vật lý có thể được tái sử dụng bởi nhiều request ở các thời điểm khác nhau.

## 2. LAST_INSERT_ID(): lấy ID AUTO_INCREMENT vừa tạo

`LAST_INSERT_ID()` không có đối số trả về giá trị `AUTO_INCREMENT` đầu tiên được tạo thành công bởi câu lệnh `INSERT` gần nhất có sinh giá trị tự tăng trên connection hiện tại.

Ví dụ tạo bảng đơn hàng:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_note VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Chèn đơn hàng và đọc ID:

```sql
INSERT INTO orders (customer_id, order_note)
VALUES (120, 'Giao trong giờ hành chính');

SELECT LAST_INSERT_ID() AS new_order_id;
```

Hai câu lệnh phải chạy trên cùng một connection. Nếu `INSERT` tạo ID `101`, lệnh `SELECT LAST_INSERT_ID()` ngay sau đó trên connection này trả `101`.

### 2.1. Giá trị thuộc về connection hiện tại

Giả sử hai session A và B cùng kết nối tới server:

| Thao tác | Session A | Session B |
|---|---|---|
| Trạng thái ban đầu | `LAST_INSERT_ID()` có giá trị riêng của A | `LAST_INSERT_ID()` có giá trị riêng của B |
| A insert một đơn hàng | Sinh ID `101` | Không thay đổi |
| B insert một đơn hàng | Vẫn giữ giá trị gần nhất của A | Sinh ID `102` |
| A gọi `LAST_INSERT_ID()` | Trả `101` | Không ảnh hưởng |
| B gọi `LAST_INSERT_ID()` | Không ảnh hưởng | Trả `102` |

Đây là lý do `LAST_INSERT_ID()` an toàn hơn cách dùng `SELECT MAX(id)` để tìm ID vừa tạo. `MAX(id)` có thể trả ID của một transaction khác vừa insert đồng thời; `LAST_INSERT_ID()` trả giá trị do chính connection đó tạo.

### 2.2. Không lấy ID bằng MAX(id)

Không nên làm như sau:

```sql
INSERT INTO orders (customer_id)
VALUES (120);

SELECT MAX(id) FROM orders;
```

Nếu một connection khác insert đơn hàng trước khi câu `SELECT MAX(id)` chạy, kết quả có thể là ID của connection khác. Dùng `LAST_INSERT_ID()` để lấy ID vừa được connection hiện tại cấp.

### 2.3. ID đầu tiên của INSERT nhiều hàng

Khi một câu lệnh chèn nhiều hàng, `LAST_INSERT_ID()` trả về giá trị tự tăng đầu tiên được tạo bởi câu lệnh đó:

```sql
INSERT INTO orders (customer_id, order_note)
VALUES
    (120, 'Đơn A'),
    (121, 'Đơn B'),
    (122, 'Đơn C');

SELECT LAST_INSERT_ID() AS first_generated_id;
```

Kết quả là ID đầu tiên được cấp trong câu lệnh insert nhiều hàng, không phải danh sách tất cả ID. Không tự suy ra ID các hàng còn lại bằng cách cộng `1`, vì `auto_increment_increment`, `auto_increment_offset`, cơ chế cấp ID, lỗi hoặc cạnh tranh đồng thời có thể khiến dãy ID không liên tục.

Nếu ứng dụng cần tất cả generated keys, hãy dùng API generated-keys của driver nếu driver hỗ trợ cho loại câu lệnh đó, hoặc truy vấn lại theo một khóa nghiệp vụ duy nhất đã biết. Đừng dựa vào giả định dãy AUTO_INCREMENT luôn liên tục.

## 3. LAST_INSERT_ID(expr): đặt giá trị trả về của connection

MySQL còn hỗ trợ dạng:

```sql
LAST_INSERT_ID(expr)
```

Dạng này trả về `expr` và ghi nhớ giá trị đó làm giá trị mà lần gọi `LAST_INSERT_ID()` không đối số tiếp theo trên cùng connection sẽ trả về.

Ví dụ:

```sql
SELECT LAST_INSERT_ID(9001) AS assigned_value;
SELECT LAST_INSERT_ID() AS remembered_value;
```

Cả hai kết quả đều là `9001`. Đây là trạng thái riêng của session, không phải thao tác cấp phát một giá trị AUTO_INCREMENT mới và không tự ghi hàng vào bảng.

Không dùng `LAST_INSERT_ID(expr)` để thay thế sequence hoặc cơ chế cấp ID bền vững do ứng dụng quản lý. Giá trị chỉ có ý nghĩa trên connection hiện tại và có thể bị thay đổi bởi thao tác tiếp theo.

### 3.1. Dùng với INSERT ... ON DUPLICATE KEY UPDATE

Một mẫu phổ biến là lấy ID của bản ghi dù thao tác insert tạo mới hay rơi vào nhánh cập nhật khi khóa duy nhất đã tồn tại.

Tạo bảng có khóa nghiệp vụ duy nhất:

```sql
CREATE TABLE external_orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_key VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_external_key (external_key)
) ENGINE=InnoDB;
```

Chạy:

```sql
INSERT INTO external_orders (external_key, status)
VALUES ('EXT-2026-0001', 'NEW')
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id);

SELECT LAST_INSERT_ID() AS order_id;
```

- Nếu `external_key` chưa tồn tại, MySQL insert hàng mới và `LAST_INSERT_ID()` trả ID vừa sinh.
- Nếu `external_key` đã tồn tại, nhánh `UPDATE` gán `id` bằng chính giá trị hiện có thông qua `LAST_INSERT_ID(id)`. Hàm ghi nhớ ID đó cho connection, vì vậy câu `SELECT` sau trả ID của hàng đã có.

Mẫu này hữu ích cho thao tác upsert cần lấy lại khóa chính. Cần bảo đảm `external_key` thực sự là khóa duy nhất đại diện cho cùng một thực thể và câu lệnh chỉ có xung đột theo khóa mà ứng dụng dự kiến. Nếu bảng có nhiều unique key, nhánh duplicate có thể được kích hoạt bởi một khóa khác; hãy hiểu rõ tất cả constraint trước khi dùng mẫu này.

## 4. LAST_INSERT_ID, transaction và rollback

Giá trị `LAST_INSERT_ID()` không phải bằng chứng rằng dữ liệu đã commit. Với InnoDB, có thể insert thành công trong transaction rồi rollback:

```sql
START TRANSACTION;

INSERT INTO orders (customer_id, order_note)
VALUES (120, 'Đơn thử nghiệm');

SELECT LAST_INSERT_ID() AS generated_id;

ROLLBACK;
```

Trong session đó, `LAST_INSERT_ID()` có thể vẫn giữ ID vừa được tạo dù hàng đã bị rollback. Rollback không khôi phục giá trị `LAST_INSERT_ID()` về giá trị trước transaction.

Vì vậy:

- ID đã được cấp không chứng minh hàng vẫn tồn tại.
- Sau rollback, hãy coi ID của hàng đã rollback là không còn hợp lệ về mặt nghiệp vụ.
- Không gửi xác nhận đơn hàng ra ngoài trước khi transaction commit thành công.
- Nếu cần xác minh, truy vấn lại hàng sau khi commit trên cùng hoặc một connection phù hợp.

AUTO_INCREMENT của InnoDB cũng không bảo đảm không có khoảng trống. Rollback, insert thất bại, `INSERT IGNORE`, cạnh tranh đồng thời và cơ chế cấp ID có thể để lại gap. Không dùng ID tự tăng làm số thứ tự nghiệp vụ liên tục hoặc bằng chứng đếm số bản ghi.

### 4.1. Khi câu INSERT thất bại

Nếu câu lệnh insert thất bại hoặc không insert thành công hàng nào, giá trị `LAST_INSERT_ID()` được xem là không xác định theo ngữ nghĩa của câu lệnh đó. Không dùng giá trị cũ trong session để kết luận lần insert vừa rồi đã tạo ra hàng nào.

Hãy kiểm tra kết quả thực thi của chính câu lệnh. Nếu driver báo exception, xử lý lỗi trước; không gọi `LAST_INSERT_ID()` rồi mặc định giá trị trả về thuộc lần insert thất bại.

### 4.2. Stored procedure, function và trigger

Thay đổi `LAST_INSERT_ID()` trong stored procedure vẫn có thể được nhìn thấy bởi câu lệnh gọi sau khi procedure kết thúc. Với stored function và trigger, giá trị được khôi phục về giá trị trước khi function/trigger bắt đầu khi chúng kết thúc. Điều này ngăn thay đổi nội bộ trong function hoặc trigger làm thay đổi trạng thái `LAST_INSERT_ID()` của caller.

Khi procedure trả ID, hãy xác định rõ nó lấy ID từ insert nào và có thể đã bị một câu lệnh khác trong procedure thay đổi hay không. Có thể trả ID bằng OUT parameter để hợp đồng của procedure rõ ràng hơn.

## 5. Lấy generated key trong ứng dụng

Trong ứng dụng, ưu tiên API generated-keys của driver vì API này gắn kết quả với chính statement đã thực thi.

Ví dụ Java JDBC:

```java
String sql = "INSERT INTO orders (customer_id, order_note) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    statement.setLong(1, customerId);
    statement.setString(2, note);

    int affected = statement.executeUpdate();
    if (affected != 1) {
        throw new SQLException("Expected one inserted order");
    }

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("MySQL did not return a generated key");
        }
        long orderId = keys.getLong(1);
        // Dùng orderId trong cùng transaction/luồng nghiệp vụ.
    }
}
```

Nếu dùng `SELECT LAST_INSERT_ID()` thay cho `getGeneratedKeys()`, phải chạy truy vấn trên cùng `Connection` vật lý vừa thực hiện insert. Không gọi lại pool để mượn một connection khác rồi chạy `LAST_INSERT_ID()`; session khác sẽ có giá trị khác.

## 6. CONNECTION_ID(): nhận diện connection hiện tại

`CONNECTION_ID()` trả về connection ID do MySQL Server gán cho client đang kết nối.

```sql
SELECT CONNECTION_ID() AS connection_id;
```

Giá trị này giúp DBA đối chiếu session hiện tại với danh sách process, log hoặc hoạt động trong Performance Schema.

### 6.1. Xem connection đang chạy

```sql
SHOW PROCESSLIST;
```

Trong kết quả, cột `Id` tương ứng với connection ID. Có thể lọc connection hiện tại trong Performance Schema:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID AS connection_id,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE
FROM performance_schema.threads
WHERE PROCESSLIST_ID = CONNECTION_ID();
```

`PROCESSLIST_ID` là connection ID mà các lệnh như `SHOW PROCESSLIST` hiển thị. `THREAD_ID` là định danh nội bộ của Performance Schema; hai giá trị này không cùng một loại ID và không nên hoán đổi cho nhau.

Quyền xem đầy đủ process list hoặc session của người dùng khác phụ thuộc quyền tài khoản và phiên bản MySQL. Nếu kết quả thiếu session, kiểm tra quyền và cấu hình Performance Schema trước khi kết luận connection không tồn tại.

### 6.2. CONNECTION_ID không phải ID người dùng hay ID request

Connection ID nhận diện một connection tới MySQL Server trong vòng đời kết nối. Nó không nhận diện:

- Người dùng cuối đang đăng nhập ứng dụng.
- Một HTTP request hoặc một job cụ thể.
- Một transaction nghiệp vụ.
- Một connection lâu dài có định danh ổn định qua reconnect.

Khi connection đóng và client kết nối lại, connection mới có ID khác. ID cũ cũng không phải khóa vĩnh viễn để lưu trong bảng nghiệp vụ. Không dùng `CONNECTION_ID()` làm user ID, order ID hoặc correlation ID xuyên suốt nhiều lần kết nối.

Trong ứng dụng có connection pool, nhiều request khác nhau có thể dùng cùng một connection vật lý vào các thời điểm khác nhau. Log `CONNECTION_ID()` hữu ích để điều tra session MySQL, nhưng hãy dùng request ID/trace ID do ứng dụng tạo để theo dõi một request xuyên qua nhiều service.

## 7. Các hàm nhận diện và giá trị session thường dùng

Ngoài hai hàm trọng tâm, MySQL có nhiều hàm và system variable giúp biết connection đang hoạt động trong ngữ cảnh nào.

| Hàm/biến | Giá trị cung cấp | Lưu ý |
|---|---|---|
| `CONNECTION_ID()` | ID của connection hiện tại | Chỉ có ý nghĩa trong vòng đời connection |
| `LAST_INSERT_ID()` | ID tự tăng gần nhất của connection | Không chứng minh hàng đã commit |
| `DATABASE()` | Database mặc định hiện tại | Trả `NULL` nếu chưa chọn database |
| `USER()` | User và host mà client dùng để kết nối | Có thể khác tài khoản thực tế được dùng để kiểm tra quyền |
| `CURRENT_USER()` | Account MySQL dùng cho kiểm tra quyền trong ngữ cảnh hiện tại | Có thể khác `USER()`, đặc biệt trong stored routine có DEFINER |
| `CURRENT_ROLE()` | Các role đang hoạt động trong session | Phụ thuộc role và phiên bản MySQL |
| `@@SESSION.sql_mode` | SQL mode của connection | Khác với `@@GLOBAL.sql_mode` |
| `@@SESSION.time_zone` | Time zone session | Ảnh hưởng một số thao tác ngày giờ và chuyển đổi timestamp |
| `@@SESSION.autocommit` | Trạng thái autocommit | Ảnh hưởng cách transaction được bắt đầu/kết thúc |
| `@@SESSION.transaction_isolation` | Isolation level mặc định của transaction session | Có thể được thay đổi theo session |
| `@@SESSION.character_set_client` | Charset client dùng gửi câu lệnh | Cần phù hợp encoding của ứng dụng |
| `@@SESSION.collation_connection` | Collation dùng cho biểu thức chuỗi theo connection | Có thể ảnh hưởng so sánh chuỗi literal |

Lấy nhanh một số giá trị:

```sql
SELECT
    CONNECTION_ID() AS connection_id,
    DATABASE() AS current_database,
    USER() AS login_identity,
    CURRENT_USER() AS privilege_identity,
    CURRENT_ROLE() AS active_roles,
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.autocommit AS autocommit_mode;
```

`USER()` thường phản ánh danh tính được gửi từ client cùng host nguồn; `CURRENT_USER()` phản ánh account MySQL được dùng để kiểm tra quyền. Trong stored routine chạy với quyền `SQL SECURITY DEFINER`, `CURRENT_USER()` có thể là definer trong khi `USER()` vẫn là người kết nối ban đầu. Sự khác biệt này rất hữu ích khi điều tra lỗi quyền.

## 8. User-defined session variables

MySQL cho phép tạo biến do người dùng định nghĩa bằng tiền tố `@`. Biến tồn tại trong session hiện tại và không cần khai báo trước:

```sql
SET @current_customer_id = 120;
SET @display_name = 'Nguyễn An';

SELECT
    @current_customer_id,
    @display_name;
```

Session khác không nhìn thấy các biến này. Khi connection kết thúc, biến cũng kết thúc.

### 8.1. Gán và sử dụng biến

Có thể gán giá trị bằng `SET`:

```sql
SET @tax_rate = 0.08;
SET @subtotal = 1250000;

SELECT @subtotal * (1 + @tax_rate) AS total_amount;
```

Hoặc gán kết quả một truy vấn scalar:

```sql
SELECT COUNT(*)
INTO @open_order_count
FROM orders
WHERE status = 'OPEN';

SELECT @open_order_count;
```

Biến user-defined có kiểu động theo giá trị được gán; nó không có khai báo kiểu tĩnh như local variable trong stored procedure. Khi cần phép tính chính xác, hãy CAST giá trị về kiểu mong muốn và không dùng biến để thay thế ràng buộc kiểu của schema.

### 8.2. Biến session không thuộc transaction

`COMMIT` và `ROLLBACK` không xóa hay hoàn tác giá trị user-defined variable:

```sql
SET @step_marker = 'before';

START TRANSACTION;
SET @step_marker = 'inside';
ROLLBACK;

SELECT @step_marker;
```

Kết quả vẫn là `inside`. Biến session là trạng thái của connection, không phải dữ liệu transactional trong bảng InnoDB. Không dùng `@variable` làm cơ chế rollback nghiệp vụ.

### 8.3. Tránh đọc và gán cùng một user variable trong một biểu thức

Không dựa vào thứ tự đánh giá biểu thức khi vừa đọc vừa gán cùng một user-defined variable trong một câu lệnh:

```sql
-- Không nên dựa vào cách đánh giá này.
SELECT @row_num := @row_num + 1, id
FROM orders;
```

Thứ tự đánh giá biểu thức có thể không được bảo đảm như người viết mong đợi. Với MySQL 8.0, hãy dùng window function như `ROW_NUMBER()` cho nhu cầu đánh số thứ tự:

```sql
SELECT
    ROW_NUMBER() OVER (ORDER BY id) AS row_num,
    id
FROM orders;
```

## 9. System variable SESSION và GLOBAL

System variable có thể được đọc theo phạm vi:

- `@@SESSION.variable_name` hoặc `@@LOCAL.variable_name`: giá trị của connection hiện tại.
- `@@GLOBAL.variable_name`: giá trị mặc định cấp server cho các session mới, nếu biến hỗ trợ phạm vi global.
- `@@variable_name`: thường tương đương giá trị session khi biến có phạm vi session.

Ví dụ:

```sql
SELECT
    @@SESSION.sql_mode AS session_mode,
    @@GLOBAL.sql_mode AS global_default,
    @@SESSION.time_zone AS session_zone,
    @@GLOBAL.time_zone AS global_zone;
```

Thay đổi session:

```sql
SET SESSION time_zone = '+07:00';
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Gán toàn bộ danh sách `sql_mode` sẽ thay thế danh sách hiện tại. Không chỉ thêm một mode bằng cách gán chuỗi rút gọn nếu muốn giữ các mode đang có; hãy đọc giá trị cũ và xây dựng thay đổi có chủ đích.

Một số system variable chỉ cho phép đọc, một số cho phép thay đổi session hoặc global, và một số thay đổi cần quyền quản trị. Hãy kiểm tra tài liệu của biến và phiên bản server trước khi thay đổi.

## 10. Connection pool và trạng thái session còn sót

Connection pool giữ một tập connection vật lý để tái sử dụng. Khi request A thay đổi trạng thái session rồi trả connection về pool, request B có thể nhận lại chính connection đó.

Ví dụ request A chạy:

```sql
SET @current_order_id = 7001;
SET SESSION time_zone = '+00:00';
SET SESSION foreign_key_checks = 0;
```

Nếu pool không reset session, request B có thể thấy:

- `@current_order_id` vẫn còn giá trị `7001`.
- `time_zone` không còn là giá trị mặc định của ứng dụng.
- `foreign_key_checks` vẫn đang tắt trên connection đó.

Đây là lỗi rò rỉ trạng thái giữa request. Với `LAST_INSERT_ID()`, một request mới cũng có thể đọc giá trị từ lần insert trước nếu nó gọi hàm mà không thực hiện insert thành công của chính mình trước đó.

### 10.1. Nguyên tắc quản lý connection pool

- Không dựa vào session variable còn sót từ request trước.
- Khởi tạo các session setting bắt buộc khi tạo hoặc mượn connection.
- Nếu thay đổi trạng thái session, lưu giá trị cũ và khôi phục trong `finally`.
- Bảo đảm transaction được `COMMIT` hoặc `ROLLBACK` trước khi trả connection.
- Reset connection theo tính năng của driver/pool nếu được hỗ trợ và kiểm tra hành vi reset đối với temporary table, prepared statement và user variable.
- Không trả connection về pool khi transaction hoặc trạng thái session chưa được dọn dẹp.
- Dùng request ID/trace ID của ứng dụng để liên kết log; chỉ dùng connection ID như thông tin chẩn đoán tại thời điểm truy vấn.

### 10.2. Kiểm tra trạng thái trước khi dùng

Một truy vấn chẩn đoán có thể ghi lại:

```sql
SELECT
    CONNECTION_ID() AS connection_id,
    LAST_INSERT_ID() AS last_insert_id,
    DATABASE() AS current_database,
    USER() AS client_identity,
    CURRENT_USER() AS privilege_identity,
    @@SESSION.autocommit AS autocommit_mode,
    @@SESSION.sql_mode AS sql_mode,
    @@SESSION.time_zone AS time_zone,
    @@SESSION.foreign_key_checks AS foreign_key_checks;
```

Không đưa toàn bộ kết quả này vào log ở mọi request nếu chi phí và dung lượng không cần thiết. Dùng trong chẩn đoán, health check hoặc log có chọn lọc; tránh ghi thông tin kết nối nhạy cảm.

## 11. Chẩn đoán connection bằng PROCESSLIST và Performance Schema

Khi có truy vấn chạy lâu hoặc session giữ lock, DBA thường cần biết connection ID để đối chiếu:

```sql
SHOW FULL PROCESSLIST;
```

Các cột hữu ích gồm `Id`, `User`, `Host`, `db`, `Command`, `Time`, `State` và `Info`. `SHOW FULL PROCESSLIST` giúp xem toàn bộ nội dung query thay vì phần bị cắt ngắn trong chế độ thường, nhưng thông tin có thể nhạy cảm; chỉ cấp quyền cho người cần thiết.

Có thể lọc connection đang chờ hoặc đang chạy qua Performance Schema:

```sql
SELECT
    PROCESSLIST_ID AS connection_id,
    THREAD_ID,
    PROCESSLIST_USER,
    PROCESSLIST_DB,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_ID IS NOT NULL
ORDER BY PROCESSLIST_TIME DESC;
```

`PROCESSLIST_TIME` cho biết thời gian ở trạng thái command hiện tại theo đơn vị giây; nó không nhất thiết là tổng tuổi đời connection. Để điều tra statement và wait event chi tiết hơn, có thể kết hợp các bảng `events_statements_current`, `events_waits_current` và view `sys` nếu Performance Schema được bật và có đủ quyền.

### 11.1. KILL QUERY và KILL CONNECTION

Sau khi xác định đúng connection, MySQL hỗ trợ:

```sql
KILL QUERY 12345;
KILL CONNECTION 12345;
```

- `KILL QUERY` dừng statement hiện tại của connection, connection vẫn còn.
- `KILL CONNECTION` kết thúc connection.

Đây là thao tác quản trị có tác động. Trước khi kill, xác nhận connection ID, user, host, câu SQL, transaction và tác động đến ứng dụng. Kết thúc connection có thể làm transaction đang mở rollback và khiến client không biết kết quả commit cuối cùng nếu mất kết nối đúng thời điểm đó. Quyền cần thiết phụ thuộc phiên bản và quyền quản trị được cấp.

Không lưu connection ID rồi dùng lại sau thời gian dài để kill; connection cũ có thể đã đóng và ID có thể không còn đại diện cho session ban đầu. Luôn truy vấn lại process list ngay trước thao tác.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách tránh |
|---|---|---|
| `LAST_INSERT_ID()` là ID lớn nhất của bảng | Đây là giá trị được connection hiện tại ghi nhớ từ thao tác insert phù hợp | Không dùng `MAX(id)` để lấy ID vừa insert |
| ID trả về chứng minh transaction đã commit | ID có thể vẫn được ghi nhớ sau rollback | Chỉ xác nhận nghiệp vụ sau commit thành công |
| ID AUTO_INCREMENT liên tục, không có gap | Rollback và nhiều tình huống khác có thể tạo gap | Không dùng ID làm số thứ tự liên tục |
| Insert nhiều hàng trả danh sách ID qua `LAST_INSERT_ID()` | Hàm trả ID đầu tiên được tạo bởi statement | Dùng generated keys của driver hoặc khóa nghiệp vụ |
| `LAST_INSERT_ID()` dùng chung cho mọi client | Giá trị được giữ riêng theo connection | Chạy truy vấn trên cùng connection vật lý |
| `CONNECTION_ID()` là ID request | Nó chỉ nhận diện connection tới MySQL | Dùng request ID/trace ID ở ứng dụng |
| Connection pool tạo connection mới cho mỗi request | Pool thường tái sử dụng connection vật lý | Reset session state trước khi trả/nhận connection |
| `ROLLBACK` xóa user variable | User variable là trạng thái session, không phải dữ liệu transactional | Chủ động reset hoặc không dùng biến qua request |
| `USER()` và `CURRENT_USER()` luôn giống nhau | Hai hàm có mục đích khác nhau | Dùng đúng hàm khi điều tra quyền |
| `THREAD_ID` là `CONNECTION_ID()` | Performance Schema thread ID khác processlist connection ID | Đối chiếu `PROCESSLIST_ID` với `CONNECTION_ID()` |

## 13. Quy trình an toàn khi tạo bản ghi và lấy ID

Với một nghiệp vụ tạo đơn hàng, quy trình điển hình là:

1. Mượn một connection từ pool và bảo đảm session ở trạng thái chuẩn.
2. Bắt đầu transaction nếu cần ghi nhiều bảng.
3. Thực hiện `INSERT` vào `orders` bằng prepared statement.
4. Lấy generated key từ chính statement hoặc gọi `LAST_INSERT_ID()` trên cùng connection.
5. Dùng ID đó để insert `order_items` trong cùng transaction.
6. Chỉ commit khi tất cả thao tác cần thiết thành công.
7. Nếu có lỗi, rollback và không công bố ID như một đơn hàng đã hoàn tất.
8. Trước khi trả connection về pool, bảo đảm transaction và session state đã được dọn dẹp.

Ví dụ SQL minh họa:

```sql
START TRANSACTION;

INSERT INTO orders (customer_id, order_note)
VALUES (120, 'Đơn hàng mới');

SET @new_order_id = LAST_INSERT_ID();

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (@new_order_id, 42, 2);

COMMIT;

SELECT @new_order_id AS committed_order_id;
```

Ví dụ giả định bảng `order_items` có các cột tương ứng và insert chi tiết thành công. `@new_order_id` là session variable nên chỉ dùng trong cùng connection. Trong ứng dụng, nên giữ ID trong biến cục bộ của code thay vì dựa vào user-defined variable nếu driver đã trả generated key.

Nếu bất kỳ thao tác nào trước commit thất bại, ứng dụng phải rollback và không coi ID vừa lấy là bản ghi đã tồn tại. Nếu client mất kết nối trong lúc gửi `COMMIT`, trạng thái commit có thể không xác định ở phía client; hãy đối soát theo khóa idempotency hoặc khóa nghiệp vụ duy nhất trước khi gửi lại request.

## 14. Checklist khi làm việc với giá trị gắn với session

- `LAST_INSERT_ID()` được gọi trên đúng connection vừa insert chưa?
- Câu insert có thực sự thành công và có tạo AUTO_INCREMENT không?
- Nếu insert nhiều hàng, ứng dụng có hiểu hàm chỉ trả ID đầu tiên không?
- Có đang dùng `MAX(id)` hoặc tự cộng ID thay cho generated keys không?
- Transaction đã commit chưa? Có rollback hoặc lỗi statement không?
- Driver có hỗ trợ `getGeneratedKeys()` và ứng dụng đã dùng đúng statement chưa?
- `CONNECTION_ID()` đang được dùng để chẩn đoán connection, không dùng làm business ID/request ID chứ?
- `PROCESSLIST_ID` và `THREAD_ID` có bị nhầm lẫn không?
- Session variables, SQL mode, timezone và transaction state có được reset trong connection pool không?
- User variable có bị giả định là transactional hoặc dùng chung giữa connection không?
- Khi kill connection, đã xác minh session hiện tại và tác động rollback chưa?
- Khi mất kết nối quanh thời điểm commit, có cơ chế idempotency/đối soát không?

## Kết luận

`LAST_INSERT_ID()` cung cấp ID AUTO_INCREMENT do câu lệnh gần nhất tạo ra trên connection hiện tại; dạng `LAST_INSERT_ID(expr)` còn có thể đặt giá trị mà lần gọi tiếp theo trả về, hữu ích trong mẫu upsert. Giá trị này không chứng minh transaction đã commit và không được khôi phục bởi rollback. `CONNECTION_ID()` nhận diện connection để chẩn đoán, nhưng không phải ID người dùng hoặc request. User-defined variables và session system variables cũng gắn với connection, tồn tại qua nhiều transaction và có thể rò rỉ qua connection pool nếu không reset. Hãy lấy generated key trên cùng connection, xác nhận commit, quản lý session state rõ ràng và dùng request ID riêng ở tầng ứng dụng.
