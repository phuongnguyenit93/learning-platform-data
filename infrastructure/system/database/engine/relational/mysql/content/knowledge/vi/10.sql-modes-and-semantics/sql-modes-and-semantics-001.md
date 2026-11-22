# Phạm vi GLOBAL/SESSION của sql_mode và cách kiểm tra cấu hình hiệu lực

`sql_mode` là biến hệ thống điều khiển một số quy tắc cú pháp và cách MySQL xử lý dữ liệu trong câu lệnh SQL. Nó có thể được đặt ở hai phạm vi: `GLOBAL` làm giá trị mặc định cho các kết nối mới, còn `SESSION` quyết định hành vi trên connection hiện tại. Khi ứng dụng dùng connection pool, mỗi connection có thể giữ `sql_mode` riêng, vì vậy giá trị global nhìn từ một phiên quản trị không nhất thiết là giá trị mà câu lệnh của ứng dụng đang dùng.

Trong module `DATABASE_MYSQL`, hiểu đúng phạm vi và cấu hình hiệu lực của `sql_mode` giúp dự đoán cách MySQL kiểm tra dữ liệu, xử lý giá trị ngoài miền, đánh giá `GROUP BY`, phân tích dấu nháy và thực thi các biểu thức. Đây là một phần quan trọng của thiết kế schema, truy vấn SQL, transaction và vận hành cơ sở dữ liệu.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt `@@GLOBAL.sql_mode` và `@@SESSION.sql_mode`.
- Giải thích cách session kế thừa giá trị global khi mở kết nối.
- Kiểm tra `sql_mode` thực sự đang áp dụng trên connection chạy truy vấn.
- Đọc nguồn cấu hình qua Performance Schema và phân biệt cấu hình runtime với cấu hình persistent.
- Thay đổi mode ở session, global hoặc lưu qua restart bằng đúng cơ chế.
- Nhận diện các mode ảnh hưởng tới strict validation, `GROUP BY`, cú pháp chuỗi và tương thích ứng dụng.
- Lập quy trình triển khai và khôi phục thay đổi `sql_mode` an toàn.

## 1. `sql_mode` là gì?

`sql_mode` là một danh sách các chế độ được phân tách bằng dấu phẩy. Mỗi chế độ điều chỉnh một phần hành vi của MySQL, chẳng hạn:

- Kiểm tra dữ liệu có nằm trong miền cột hay không.
- Xử lý ngày tháng không hợp lệ hoặc phép chia cho 0.
- Yêu cầu các cột trong `SELECT` phải phù hợp với `GROUP BY`.
- Diễn giải dấu nháy kép và ký tự escape trong chuỗi.
- Xử lý khi storage engine được chỉ định không khả dụng.

Ví dụ, hai session có thể chạy cùng một câu `INSERT` nhưng nhận kết quả khác nhau nếu một session bật strict mode và session kia không bật. Tương tự, một câu `SELECT` có thể hợp lệ trong mode cũ nhưng bị từ chối khi `ONLY_FULL_GROUP_BY` được bật.

`sql_mode` không phải danh sách quyền truy cập và cũng không thay thế constraint của schema. Nó điều chỉnh cách server diễn giải và kiểm tra câu lệnh; quyền `GRANT`, `REVOKE`, transaction và constraint vẫn có vai trò riêng.

## 2. Phạm vi GLOBAL và SESSION

MySQL duy trì hai giá trị của `sql_mode`:

| Phạm vi | Cách đọc | Ý nghĩa | Ảnh hưởng |
|---|---|---|---|
| Global | `@@GLOBAL.sql_mode` | Giá trị mặc định của server dành cho kết nối mới | Được dùng làm giá trị khởi đầu cho session mới; thay đổi không sửa các session đang mở |
| Session | `@@SESSION.sql_mode` | Giá trị mode của connection hiện tại | Điều khiển câu lệnh được thực thi trên chính connection đó |

Khi client kết nối, MySQL khởi tạo session với giá trị global hiện hành. Sau đó, session có thể thay đổi riêng bằng `SET SESSION sql_mode = ...`. Thay đổi này không ảnh hưởng tới connection khác và không tự cập nhật giá trị global.

### 2.1. Minh họa kế thừa khi kết nối

Giả sử server có global mode là:

```text
ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
```

Khi một ứng dụng mở connection mới, session thường bắt đầu với cùng danh sách đó. Nếu connection chạy:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';
```

thì chỉ connection hiện tại chuyển sang `ANSI_QUOTES`. Những connection đã mở khác vẫn giữ mode trước đó; connection mở sau vẫn nhận giá trị global, trừ khi cấu hình khởi tạo của client/pool thay đổi session ngay sau khi kết nối.

### 2.2. Thay đổi GLOBAL không cập nhật session đang chạy

Ví dụ quản trị viên chạy:

```sql
SET GLOBAL sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Các kết nối mới sau đó sẽ kế thừa danh sách global mới. Một connection đã tồn tại trước lệnh này vẫn giữ `@@SESSION.sql_mode` cũ cho tới khi chính connection đó thay đổi session hoặc bị đóng và tạo lại.

Điểm này rất quan trọng với connection pool: restart MySQL không phải lúc nào cũng là cách duy nhất cần thiết để làm mới session. Nếu pool giữ các connection cũ, cần recycle/reconnect chúng hoặc chủ động cấu hình session trên từng connection.

## 3. Kiểm tra giá trị đang có hiệu lực

Đừng chỉ kiểm tra file cấu hình hoặc giá trị global. Hãy đọc giá trị session ngay trên connection thực thi truy vấn.

### 3.1. Xem cả hai phạm vi

```sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@sql_mode AS unqualified_sql_mode,
    CONNECTION_ID() AS connection_id;
```

`@@sql_mode` không ghi rõ phạm vi được hiểu là giá trị session khi biến có phạm vi session. Vì vậy, trong script vận hành và tài liệu, nên viết rõ `@@GLOBAL.sql_mode` hoặc `@@SESSION.sql_mode` để tránh nhầm lẫn.

### 3.2. Dùng SHOW VARIABLES

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

Lệnh `SHOW VARIABLES LIKE 'sql_mode'` không ghi phạm vi thường trả về giá trị session của connection hiện tại. Khi cần đối chiếu cấu hình server và connection, hãy dùng cả hai câu lệnh có chỉ định phạm vi.

### 3.3. Kiểm tra trên đúng connection của ứng dụng

Nếu ứng dụng dùng JDBC, chạy truy vấn kiểm tra qua chính `Connection` được lấy từ pool:

```java
String sql = "SELECT CONNECTION_ID(), @@GLOBAL.sql_mode, @@SESSION.sql_mode";

try (PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet resultSet = statement.executeQuery()) {
    if (resultSet.next()) {
        long connectionId = resultSet.getLong(1);
        String globalMode = resultSet.getString(2);
        String sessionMode = resultSet.getString(3);
        // Ghi nhận các giá trị này trong log chẩn đoán, không ghi credential.
    }
}
```

Một phiên terminal quản trị và một connection ứng dụng có thể có `SESSION` khác nhau. Khi điều tra lỗi chỉ xảy ra trong service, hãy log `CONNECTION_ID()` cùng `@@SESSION.sql_mode` từ connection gây lỗi thay vì suy luận từ một phiên khác.

## 4. Đọc nguồn cấu hình hiệu lực

Giá trị runtime cho biết MySQL đang dùng mode nào. Khi cần biết giá trị đến từ đâu, có thể xem metadata trong Performance Schema.

### 4.1. `performance_schema.variables_info`

Trên các phiên bản MySQL 8.0 có bảng này, truy vấn:

```sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'sql_mode';
```

Bảng này cung cấp nguồn của biến global, đường dẫn option file nếu có, thời điểm đặt runtime và thông tin user/host đã đặt biến. Các giá trị `VARIABLE_SOURCE` có thể cho biết biến đến từ mặc định biên dịch, option file, command line, persisted setting hoặc thay đổi runtime. Tập giá trị cụ thể và metadata có thể khác theo phiên bản.

Nếu Performance Schema bị tắt hoặc bảng không có trong phiên bản đang dùng, vẫn có thể kiểm tra giá trị qua `@@GLOBAL.sql_mode` và `SHOW GLOBAL VARIABLES`. Khi đó, kiểm tra thêm cấu hình server và tham số khởi động theo quyền truy cập vận hành.

### 4.2. Kiểm tra cấu hình đã persist

Với MySQL 8.0.11 trở lên, `SET PERSIST` có thể lưu biến global vào file cấu hình tự quản lý `mysqld-auto.cnf`. Nếu Performance Schema có bảng `persisted_variables`, kiểm tra:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'sql_mode';
```

Giá trị persisted là thông tin về cấu hình được lưu để áp dụng khi server khởi động. Nó không thay thế việc kiểm tra `@@GLOBAL.sql_mode` và `@@SESSION.sql_mode` hiện tại.

### 4.3. Phân biệt các nguồn

| Nguồn | Ví dụ | Khi nào có hiệu lực |
|---|---|---|
| Mặc định của MySQL | Giá trị mặc định theo phiên bản | Khi không có cấu hình khác ghi đè |
| Option file | `sql_mode=...` trong phần `[mysqld]` | Khi server khởi động và đọc option file |
| Command line | `--sql-mode=...` khi khởi động server | Khi server khởi động với tham số đó |
| Persisted setting | `SET PERSIST sql_mode = ...` | Được lưu để áp dụng qua lần khởi động; cũng thay đổi global runtime khi dùng `SET PERSIST` |
| Runtime global | `SET GLOBAL sql_mode = ...` | Ngay lập tức cho giá trị global và các connection mở mới; không ghi bền sau restart nếu không có cấu hình lưu khác |
| Runtime session | `SET SESSION sql_mode = ...` | Ngay lập tức trên connection hiện tại |

Khi nhiều nguồn cùng cấu hình một biến, không đoán nguồn cuối cùng chỉ bằng cách đọc một tệp. Hãy xem `VARIABLE_SOURCE`/`VARIABLE_PATH` nếu có, sau đó xác minh giá trị runtime. `mysqld-auto.cnf` do MySQL quản lý; không chỉnh sửa trực tiếp file này bằng editor.

## 5. Thay đổi sql_mode ở SESSION

`SET SESSION` thay đổi mode của connection hiện tại. Đây là cách phù hợp để thử nghiệm, chạy migration có phạm vi hẹp hoặc cấu hình một ứng dụng có yêu cầu tương thích riêng.

```sql
SET SESSION sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
```

Khi gán một chuỗi mới, MySQL thay toàn bộ danh sách hiện tại bằng danh sách được chỉ định. Nếu vô tình bỏ một mode đang cần, session sẽ không còn mode đó. Vì vậy, hãy đọc và lưu giá trị ban đầu trước khi thay đổi.

### 5.1. Thêm hoặc bỏ một mode

Nếu MySQL Sys Schema có sẵn, có thể dùng `sys.list_add()` và `sys.list_drop()` để thao tác với danh sách:

```sql
SET SESSION sql_mode =
  sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');

SET SESSION sql_mode =
  sys.list_drop(@@SESSION.sql_mode, 'ANSI_QUOTES');
```

Hai hàm này giúp giữ các mode khác trong danh sách. Nếu Sys Schema không có hoặc không dùng được, hãy gán toàn bộ chuỗi mode mong muốn một cách tường minh.

### 5.2. Lưu và khôi phục giá trị trước khi thử

Trong lab, có thể lưu giá trị cũ vào biến session:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
  sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');

SELECT @@SESSION.sql_mode;

SET SESSION sql_mode = @saved_sql_mode;
```

Biến `@saved_sql_mode` cũng thuộc session và tồn tại sau statement. Nếu connection được trả về pool, phải khôi phục cả biến và session state trước khi trả kết nối. Trong ứng dụng, nên dùng cấu hình pool cố định thay vì mỗi request tùy tiện thay đổi mode.

## 6. Thay đổi sql_mode ở GLOBAL

`SET GLOBAL` thay đổi giá trị global đang chạy:

```sql
SET GLOBAL sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode;
```

Thao tác này yêu cầu quyền quản trị hệ thống phù hợp, thường là `SYSTEM_VARIABLES_ADMIN` (hoặc quyền `SUPER` cũ trong các phiên bản tương ứng). Người dùng thông thường có thể đặt session mode của chính connection nếu biến cho phép, nhưng không được tự ý thay đổi global.

`SET GLOBAL` không cập nhật session đang mở và thay đổi runtime sẽ mất sau restart nếu không được lưu trong option file hoặc persisted setting. Hãy kiểm tra các connection mới và connection cũ riêng biệt sau khi thay đổi.

## 7. Lưu cấu hình qua restart

Có ba cách phổ biến để làm cho mode tồn tại sau khi server khởi động lại. Chọn một nguồn quản lý rõ ràng để tránh cấu hình trùng lặp và khó truy vết.

### 7.1. Cấu hình trong option file

Trong tệp cấu hình MySQL, đặt `sql_mode` dưới phần `[mysqld]`:

```ini
[mysqld]
sql_mode=ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
```

Đường dẫn file phụ thuộc bản phân phối và cách cài đặt, ví dụ `/etc/my.cnf`, `/etc/mysql/my.cnf` hoặc các file include. Sau khi sửa, cần khởi động lại MySQL theo quy trình vận hành rồi kiểm tra lại `@@GLOBAL.sql_mode` và session mới.

Không thay toàn bộ danh sách mặc định bằng một chuỗi rút gọn nếu chưa hiểu các mode bị loại bỏ. Khi cấu hình mới, nên lấy danh sách hiện tại, xác định mode cần thêm/bỏ và ghi lại đầy đủ danh sách mong muốn.

### 7.2. `SET PERSIST`

MySQL 8.0.11 trở lên hỗ trợ:

```sql
SET PERSIST sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

`SET PERSIST` cập nhật giá trị global runtime và lưu cấu hình để áp dụng qua lần restart. Thao tác này cần quyền quản trị phù hợp. Sau khi chạy, xác minh cả giá trị global và bản ghi persisted nếu Performance Schema hỗ trợ.

### 7.3. `SET PERSIST_ONLY`

Nếu chỉ muốn ghi giá trị cho lần khởi động sau mà không thay đổi global runtime hiện tại:

```sql
SET PERSIST_ONLY sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

`SET PERSIST_ONLY` phù hợp khi muốn chuẩn bị cấu hình restart theo kế hoạch bảo trì. Nó không đổi giá trị `@@GLOBAL.sql_mode` hiện tại; session mới trước khi restart vẫn kế thừa global hiện tại.

### 7.4. Xóa một persisted setting

Nếu cần loại bỏ persisted override của biến:

```sql
RESET PERSIST IF EXISTS sql_mode;
```

Lệnh này xóa cấu hình persisted của `sql_mode`; nó không tự khôi phục giá trị global runtime đã bị thay đổi trước đó. Nếu cần thay đổi giá trị đang chạy, đặt `SET GLOBAL` về danh sách mong muốn rồi xác minh. Sau restart, server sẽ lấy giá trị từ các nguồn cấu hình còn lại.

Không xóa hoặc sửa `mysqld-auto.cnf` thủ công. Sử dụng câu lệnh quản trị của MySQL để quản lý persisted setting.

## 8. Các mode thường ảnh hưởng tới ứng dụng

Danh sách mode mặc định phụ thuộc phiên bản và bản dựng. MySQL 8.0/8.4 thường bật một số mode như `ONLY_FULL_GROUP_BY`, `STRICT_TRANS_TABLES`, `NO_ZERO_IN_DATE`, `NO_ZERO_DATE`, `ERROR_FOR_DIVISION_BY_ZERO` và `NO_ENGINE_SUBSTITUTION`. Luôn xem giá trị thực tế của server thay vì giả định mọi môi trường có cùng mặc định.

| Mode | Tác động chính | Điều cần kiểm tra trong ứng dụng |
|---|---|---|
| `STRICT_TRANS_TABLES` | Từ chối nhiều giá trị không hợp lệ hoặc ngoài miền đối với bảng transactional; xử lý bảng nontransactional có quy tắc riêng | Validate dữ liệu và xử lý lỗi insert/update |
| `STRICT_ALL_TABLES` | Áp dụng strict validation rộng hơn cho cả bảng nontransactional; lỗi giữa multi-row statement có thể để lại các hàng đã ghi trước đó | Không giả định mọi engine đều rollback được một statement |
| `ONLY_FULL_GROUP_BY` | Yêu cầu cột không aggregate trong SELECT/HAVING/ORDER BY phải hợp lệ với GROUP BY hoặc phụ thuộc hàm vào khóa nhóm | Sửa truy vấn tổng hợp mơ hồ, không tắt mode chỉ để truy vấn chạy |
| `NO_ZERO_DATE` | Hạn chế hoặc từ chối giá trị ngày zero theo tổ hợp SQL mode/strict mode | Dùng `NULL` hoặc giá trị nghiệp vụ hợp lệ thay cho ngày giả |
| `NO_ZERO_IN_DATE` | Hạn chế ngày có tháng hoặc ngày bằng 0 | Validate ngày trước khi ghi |
| `ERROR_FOR_DIVISION_BY_ZERO` | Điều chỉnh xử lý phép chia cho 0 khi ghi và trong một số ngữ cảnh biểu thức | Kiểm tra mẫu số và xử lý `NULL`/lỗi theo nghiệp vụ |
| `NO_ENGINE_SUBSTITUTION` | Báo lỗi nếu engine được yêu cầu không khả dụng thay vì âm thầm thay bằng engine mặc định | Kiểm tra engine cài đặt và DDL |
| `ANSI_QUOTES` | Dùng dấu nháy kép cho identifier; chuỗi ký tự nên dùng dấu nháy đơn | Tìm các câu SQL dùng `"text"` để biểu diễn literal |
| `NO_BACKSLASH_ESCAPES` | Dấu backslash không còn escape chuỗi theo cách mặc định | Kiểm tra literal và SQL được sinh từ code cũ |
| `PIPES_AS_CONCAT` | Toán tử `||` được hiểu là nối chuỗi thay vì OR logic | Kiểm tra biểu thức SQL dùng `||` |

Một số mode cũ đã bị deprecated hoặc loại bỏ trong MySQL 8.0. Ví dụ, `NO_AUTO_CREATE_USER` đã bị loại bỏ từ MySQL 8.0.11; không sao chép nguyên danh sách mode từ cấu hình MySQL 5.6/5.7 sang server mới mà không kiểm tra. Alias như `ANSI` hoặc `TRADITIONAL` đại diện cho nhóm mode; hãy đọc danh sách hiệu lực sau khi gán để biết server đang áp dụng những thành phần nào.

### 8.1. Ví dụ strict mode và dữ liệu ngoài miền

Tạo bảng lab:

```sql
CREATE TABLE mode_quantity (
    id INT NOT NULL PRIMARY KEY,
    quantity TINYINT UNSIGNED NOT NULL
) ENGINE=InnoDB;
```

Trong session có strict mode:

```sql
SET SESSION sql_mode =
  sys.list_add(@@SESSION.sql_mode, 'STRICT_TRANS_TABLES');

INSERT INTO mode_quantity (id, quantity)
VALUES (1, 300);
```

`TINYINT UNSIGNED` chỉ nhận giá trị 0–255. Với strict mode, giá trị 300 bị từ chối thay vì âm thầm lưu thành giá trị giới hạn. Kiểm tra lỗi và trạng thái bảng:

```sql
SHOW WARNINGS;
SELECT * FROM mode_quantity;
```

Trong môi trường non-strict, MySQL có thể điều chỉnh giá trị ngoài miền và phát warning. `INSERT IGNORE` cũng có thể chuyển một số lỗi thành warning và tiếp tục xử lý. Không dựa vào clipping hoặc `IGNORE` để thay thế validation dữ liệu.

### 8.2. Ví dụ ONLY_FULL_GROUP_BY

Giả sử bảng `orders` có nhiều đơn hàng cho mỗi khách hàng. Truy vấn sau mơ hồ vì một khách hàng có thể có nhiều `status`:

```sql
SELECT customer_id, status, COUNT(*)
FROM orders
GROUP BY customer_id;
```

Khi `ONLY_FULL_GROUP_BY` được bật, MySQL từ chối nếu `status` không được nhóm, không được aggregate và không phụ thuộc hàm vào `customer_id`. Sửa truy vấn theo ý nghĩa cần lấy:

```sql
SELECT customer_id, status, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id, status;
```

Hoặc nếu cần một trạng thái tổng hợp, dùng biểu thức aggregate có chủ đích như `MAX(status)` chỉ khi cách chọn đó đúng nghiệp vụ. Không tắt `ONLY_FULL_GROUP_BY` để che truy vấn không xác định.

### 8.3. Ví dụ ANSI_QUOTES

Khi `ANSI_QUOTES` tắt, dấu nháy kép có thể dùng để bao chuỗi trong một số cấu hình. Khi bật, dấu nháy kép được dùng cho identifier:

```sql
SET SESSION sql_mode = sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');

SELECT "customer_name" FROM customer;
SELECT 'customer_name' AS label;
```

Trong câu đầu, `"customer_name"` được hiểu là tên cột; trong câu thứ hai, `'customer_name'` là literal chuỗi. Để tương thích tốt giữa các mode, luôn dùng dấu nháy đơn cho string literal và backtick cho identifier cần quote.

## 9. SQL mode và stored programs

MySQL lưu giá trị `sql_mode` đang có hiệu lực khi tạo stored procedure, stored function, trigger và event. Khi các đối tượng này thực thi, chúng dùng mode đã ghi nhận lúc tạo, không đơn giản lấy mode session hiện tại của người gọi.

Điều này có thể gây bất ngờ khi quản trị viên thay đổi global/session mode nhưng một procedure cũ vẫn xử lý biểu thức theo quy tắc trước đây. Khi cần đồng bộ, phải xem xét tạo lại hoặc thay đổi đối tượng bằng quy trình migration có kiểm thử.

Kiểm tra mode đã lưu cho routine:

```sql
SELECT ROUTINE_NAME, ROUTINE_TYPE, SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE();
```

Kiểm tra trigger và event:

```sql
SELECT TRIGGER_NAME, SQL_MODE
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE();

SELECT EVENT_NAME, SQL_MODE
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = DATABASE();
```

Khi deploy routine/trigger/event, hãy ghi nhận `sql_mode` của migration connection. Nếu build pipeline và production có mode khác nhau, đối tượng được tạo có thể lưu mode khác nhau.

## 10. Connection pool và cấu hình từng ứng dụng

Với ứng dụng Java hoặc service nhiều worker, một pool có thể duy trì hàng chục connection. Mỗi connection là một session độc lập, vì vậy việc đặt `SET SESSION sql_mode` trên một connection không cấu hình các connection còn lại.

Các nguyên tắc thực tế:

- Đặt global mode phù hợp với chuẩn chung của server.
- Cấu hình session mode nhất quán khi pool tạo connection hoặc khi khởi tạo connection mới.
- Không thay đổi session mode tùy tiện theo request; nếu bắt buộc, phải khôi phục trước khi connection về pool.
- Khi đổi global, recycle pool hoặc kiểm tra/reconfigure các connection hiện có nếu muốn chúng cùng nhận mode mới.
- Log `CONNECTION_ID()` và `@@SESSION.sql_mode` khi cần chẩn đoán một connection cụ thể.
- Kiểm tra mode của migration tool, job nền, CLI và service; chúng có thể mở session với cấu hình khác nhau.

Một kiểm tra đơn giản trên connection lấy từ pool:

```sql
SELECT
    CONNECTION_ID(),
    @@GLOBAL.sql_mode,
    @@SESSION.sql_mode;
```

Không xem một truy vấn kiểm tra từ terminal quản trị là bằng chứng rằng mọi session trong pool đều có cùng cấu hình.

## 11. Quy trình thay đổi sql_mode an toàn

Khi chuẩn hóa mode cho một môi trường, thực hiện theo trình tự:

1. Ghi lại phiên bản MySQL, `@@GLOBAL.sql_mode` và `@@SESSION.sql_mode` từ server và từ connection ứng dụng.
2. Xác định nguồn cấu hình qua `performance_schema.variables_info`, persisted variables và option file nếu có quyền kiểm tra.
3. Tìm các truy vấn, migration, stored program và trigger phụ thuộc vào mode cũ.
4. Thử mode mục tiêu trên session lab hoặc môi trường staging; chạy kiểm thử dữ liệu biên, truy vấn tổng hợp và SQL sinh từ ứng dụng.
5. Nếu chỉ một ứng dụng cần mode riêng, cấu hình `SESSION` qua connection pool. Nếu là chuẩn server, lên kế hoạch thay đổi `GLOBAL` và persistent source.
6. Sau thay đổi, kiểm tra global, tạo connection mới để xác nhận giá trị kế thừa, rồi kiểm tra các connection pool đã được recycle.
7. Theo dõi lỗi SQL, warning, job thất bại và kết quả migration; lưu lại danh sách mode trước/sau cùng kế hoạch rollback.

Ví dụ ghi lại trạng thái trước khi thay đổi:

```sql
SELECT VERSION(), @@GLOBAL.sql_mode, @@SESSION.sql_mode;

SELECT VARIABLE_NAME, VARIABLE_SOURCE, VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'sql_mode';
```

Ví dụ khôi phục runtime global về giá trị đã lưu trong kế hoạch thay đổi:

```sql
SET GLOBAL sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Danh sách trên chỉ là ví dụ. Khi rollback, dùng chính xác danh sách đã ghi nhận trước thay đổi của môi trường đó. Nếu đã dùng `SET PERSIST`, cần xử lý persisted override riêng; đặt lại global runtime không tự xóa cấu hình persisted.

## 12. Bài thực hành

Thực hiện trên database lab hoặc staging được phép:

1. Ghi lại `VERSION()`, `@@GLOBAL.sql_mode`, `@@SESSION.sql_mode` và `CONNECTION_ID()`.
2. Mở hai connection độc lập. Đặt `SESSION sql_mode` khác nhau trên mỗi connection và chứng minh thay đổi của connection A không ảnh hưởng connection B.
3. Thay đổi `GLOBAL sql_mode`, sau đó so sánh session cũ với một connection mới để xác nhận cơ chế kế thừa.
4. Dùng `sys.list_add()` để thêm `ANSI_QUOTES` và `sys.list_drop()` để bỏ mode; xác minh danh sách sau mỗi thao tác.
5. Thử insert giá trị ngoài miền vào cột `TINYINT UNSIGNED` với strict mode bật/tắt trong lab; đọc lỗi và warning.
6. Thử truy vấn tổng hợp vi phạm `ONLY_FULL_GROUP_BY`, sau đó sửa bằng `GROUP BY`/aggregate đúng nghiệp vụ.
7. Đọc `performance_schema.variables_info` và `persisted_variables` nếu phiên bản hỗ trợ; xác định nguồn cấu hình global.
8. Tạo một stored procedure trong session có mode cụ thể, sau đó thay đổi session mode và kiểm tra `information_schema.ROUTINES.SQL_MODE`.
9. Dùng connection pool trong ứng dụng mẫu, lấy nhiều connection và xác minh từng session có mode như dự kiến.
10. Viết quy trình triển khai/rollback ngắn cho một thay đổi mode, nêu rõ connection cũ, connection mới và persisted setting.

Bạn hoàn thành bài khi giải thích được tại sao giá trị global và session có thể khác nhau, biết cách truy vấn cấu hình hiệu lực trên đúng connection và thay đổi mode mà không làm các ứng dụng khác bị bất ngờ.

## 13. Nguyên tắc cần ghi nhớ

- `@@GLOBAL.sql_mode` là mặc định cho connection mới; `@@SESSION.sql_mode` điều khiển connection hiện tại.
- `SET GLOBAL` không thay đổi session đang mở; connection pool có thể tiếp tục giữ mode cũ.
- `SET SESSION` thay thế danh sách mode của connection hiện tại; không bỏ mode hiện hữu ngoài ý muốn.
- Dùng `performance_schema.variables_info` để xem nguồn biến global và `persisted_variables` để xem cấu hình đã lưu khi phiên bản hỗ trợ.
- `SET PERSIST` thay đổi global runtime và lưu qua restart; `SET PERSIST_ONLY` chỉ lưu cho lần khởi động sau.
- `RESET PERSIST` xóa persisted override nhưng không tự khôi phục global runtime.
- Mặc định mode thay đổi theo phiên bản; luôn kiểm tra `VERSION()` và giá trị thực tế.
- Kiểm thử strict mode, `ONLY_FULL_GROUP_BY` và cú pháp chuỗi trước khi thay đổi trên production.
- Stored programs, triggers và events có thể lưu `sql_mode` tại thời điểm tạo; kiểm tra metadata khi hành vi khác kỳ vọng.
- Ghi lại trạng thái trước/sau, xác minh connection mới và recycle pool theo kế hoạch triển khai.
