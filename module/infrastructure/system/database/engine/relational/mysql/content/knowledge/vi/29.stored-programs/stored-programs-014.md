# Stored function so với loadable function và ranh giới bảo mật

MySQL có hai cơ chế thường được gọi là “user-defined function” nhưng khác nhau về kiến trúc: **stored function** được viết bằng SQL và lưu trong database; **loadable function** (UDF) là hàm native được biên dịch thành thư viện chia sẻ rồi nạp vào tiến trình `mysqld`. Cả hai đều có thể được gọi trong biểu thức SQL, nhưng vòng đời, cách triển khai, quyền và rủi ro bảo mật rất khác nhau.

Stored function phù hợp khi muốn đóng gói phép tính hoặc quy tắc dữ liệu trong SQL, kiểm soát quyền bằng `SQL SECURITY DEFINER`/`INVOKER` và cấp quyền `EXECUTE` theo routine. Loadable function chỉ nên cân nhắc khi cần mã native mà built-in function hoặc stored function không đáp ứng được; thư viện UDF chạy bên trong tiến trình máy chủ nên có thể ảnh hưởng trực tiếp tới tính ổn định và an toàn của database server.

Trong module `DATABASE_MYSQL`, cần chọn đúng loại function dựa trên nơi mã chạy và ranh giới tin cậy: stored function chạy trong ngữ cảnh quyền SQL của MySQL; loadable function đưa mã native vào tiến trình `mysqld`. Bài học tập trung vào MySQL 8.0 trở lên, InnoDB và các nguyên tắc triển khai an toàn.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt stored function với loadable function/UDF.
- Nhận diện cú pháp tạo từng loại function và phạm vi đăng ký của chúng.
- Viết stored function scalar với `RETURNS`, `RETURN` và các characteristic phù hợp.
- Hiểu ý nghĩa của `DETERMINISTIC`, `NO SQL`, `READS SQL DATA` và `MODIFIES SQL DATA`.
- Phân biệt `SQL SECURITY DEFINER` và `SQL SECURITY INVOKER`.
- Thiết kế quyền `CREATE ROUTINE`, `ALTER ROUTINE` và `EXECUTE` theo least privilege.
- Hiểu giới hạn của stored function khi truy cập dữ liệu hoặc được gọi từ câu lệnh SQL.
- Mô tả cách cài đặt, gỡ bỏ và triển khai loadable UDF trên các MySQL server.
- Đánh giá rủi ro khi thư viện native chạy trong tiến trình `mysqld`.
- Chọn built-in function, stored function, loadable function hoặc code ở ứng dụng theo đúng bài toán.
- Kiểm tra metadata, quyền và hành vi function trước khi triển khai.

## 1. Hai loại function, hai mô hình thực thi

### 1.1. Stored function

Stored function là routine được định nghĩa bằng SQL và lưu trong schema của MySQL. Nó có tham số đầu vào, một kiểu trả về và kết thúc bằng `RETURN`. Có thể gọi stored function trong biểu thức của `SELECT`, `WHERE`, `ORDER BY`, phép gán hoặc các biểu thức SQL khác.

Ví dụ đơn giản:

```sql
USE appdb;

DELIMITER //

CREATE FUNCTION line_total(
    p_quantity INT UNSIGNED,
    p_unit_price DECIMAL(12, 2)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
NO SQL
SQL SECURITY INVOKER
BEGIN
    RETURN p_quantity * p_unit_price;
END//

DELIMITER ;

SELECT line_total(3, 12.50) AS total_amount;
```

Function nhận hai giá trị, tính tích và trả về một giá trị `DECIMAL`. Nó không cần truy cập bảng nên khai báo `NO SQL`; cùng tham số đầu vào sẽ cho cùng kết quả nên `DETERMINISTIC` phù hợp.

### 1.2. Loadable function (UDF)

Loadable function là hàm được viết bằng ngôn ngữ native như C/C++, biên dịch thành shared library rồi đăng ký để MySQL nạp. Trên Linux thường là thư viện `.so`, trên Windows thường là `.dll`.

Ví dụ cú pháp đăng ký một UDF scalar đã được biên dịch và cài vào thư mục plugin hợp lệ:

```sql
SHOW VARIABLES LIKE 'plugin_dir';

CREATE FUNCTION normalize_code
RETURNS STRING
SONAME 'normalize_code.so';

SELECT normalize_code(' ab-123 ');
```

`normalize_code.so` là thư viện native đã được xây dựng trước; câu lệnh SQL không biên dịch mã nguồn. MySQL nạp hàm từ thư viện được chỉ định và gọi entry point theo UDF API.

### 1.3. Cùng được gọi trong SQL nhưng không cùng ranh giới

```text
SQL statement
   |
   +-- Stored function
   |      -> routine definition trong schema
   |      -> SQL routine interpreter
   |      -> SQL SECURITY DEFINER hoặc INVOKER
   |      -> quyền EXECUTE và quyền truy cập object theo security context
   |
   +-- Loadable UDF
          -> function đăng ký với MySQL server
          -> native shared library
          -> mã chạy trong tiến trình mysqld
          -> ranh giới tin cậy của server/OS và plugin directory
```

Stored function được quản lý như routine trong database. Loadable UDF là mã native được server nạp; nó không có cùng cơ chế `SQL SECURITY` của stored routine.

## 2. So sánh stored function và loadable function

| Tiêu chí | Stored function | Loadable function/UDF |
|---|---|---|
| Cách triển khai | SQL routine | Mã native biên dịch thành shared library |
| Nơi lưu định nghĩa | Schema/database trong MySQL data dictionary | Đăng ký function và tên thư viện trong server; thư viện nằm trong môi trường cài đặt MySQL |
| Phạm vi tên | Thuộc một schema; có thể gọi bằng `schema.function()` | Đăng ký ở cấp MySQL server, không phải routine thuộc schema ứng dụng |
| Cách gọi | Trong biểu thức SQL | Trong biểu thức SQL |
| Kiểu trả về | Kiểu dữ liệu SQL được khai báo sau `RETURNS` | Các kiểu UDF như `STRING`, `INTEGER`, `REAL`, `DECIMAL` |
| Quyền | `CREATE ROUTINE`, `ALTER ROUTINE`, `EXECUTE`; security context DEFINER/INVOKER | Quyền cài/gỡ UDF và quyền vận hành server; không có `SQL SECURITY DEFINER/INVOKER` như stored routine |
| Mã thực thi | SQL routine body | Native code bên trong tiến trình `mysqld` |
| Phụ thuộc triển khai | Schema migration và definer/privileges | Đúng thư viện, OS/architecture, ABI và cấu hình plugin trên từng server |
| Rủi ro | Lộ dữ liệu hoặc thao tác vượt quyền nếu thiết kế DEFINER sai | Crash, memory corruption hoặc thực thi hành động native với quyền OS của mysqld |
| Lựa chọn mặc định | Ưu tiên khi logic phù hợp với SQL | Chỉ dùng khi có yêu cầu native rõ ràng và quy trình kiểm soát chặt |

Không chọn loadable UDF chỉ vì muốn viết một phép tính phức tạp. Trước tiên xem built-in function, biểu thức SQL, generated column, stored function hoặc xử lý ở ứng dụng có đáp ứng được không.

## 3. Cú pháp và đặc tính của stored function

Cấu trúc khái quát:

```sql
CREATE [DEFINER = user]
FUNCTION function_name ([parameter[,...]])
RETURNS return_type
    [characteristic ...]
routine_body
```

Các characteristic thường gặp:

```sql
LANGUAGE SQL
| [NOT] DETERMINISTIC
| {CONTAINS SQL | NO SQL | READS SQL DATA | MODIFIES SQL DATA}
| SQL SECURITY {DEFINER | INVOKER}
| COMMENT 'text'
```

Stored function chỉ có tham số đầu vào; không dùng `OUT` hoặc `INOUT` như stored procedure. Giá trị kết quả được trả bằng `RETURN` và phải phù hợp kiểu khai báo sau `RETURNS`.

### 3.1. Function thuần, không đọc bảng

```sql
USE appdb;

DELIMITER //

CREATE FUNCTION apply_discount(
    p_amount DECIMAL(12, 2),
    p_percent DECIMAL(5, 2)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
CONTAINS SQL
SQL SECURITY INVOKER
BEGIN
    IF p_amount IS NULL OR p_percent IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_percent < 0 OR p_percent > 100 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Discount percent must be between 0 and 100';
    END IF;

    RETURN p_amount * (1 - p_percent / 100);
END//

DELIMITER ;

SELECT apply_discount(250.00, 10.00) AS discounted_amount;
```

Kết quả là `225.00`. Function chỉ tính từ tham số, không phụ thuộc trạng thái database hoặc thời điểm gọi.

### 3.2. Function đọc dữ liệu

Một stored function có thể đọc bảng và trả một giá trị scalar:

```sql
USE appdb;

CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_status VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

DELIMITER //

CREATE FUNCTION get_customer_status(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT NULL;

    SELECT customer_status
      INTO v_status
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_status;
END//

DELIMITER ;

SELECT get_customer_status(100) AS customer_status;
```

Function này phụ thuộc dữ liệu hiện tại trong `customer_profile`; cùng một `customer_id` có thể trả kết quả khác sau khi bảng được cập nhật, nên không nên khai báo `DETERMINISTIC`. `SELECT ... INTO` lấy một giá trị vào biến cục bộ thay vì trả result set cho client.

Nếu không tìm thấy hàng, `SELECT ... INTO` phát sinh cảnh báo `NOT FOUND` và biến giữ giá trị ban đầu (`NULL` trong ví dụ). Nếu truy vấn trả nhiều hơn một hàng, MySQL báo lỗi; primary key giúp bảo đảm tối đa một hàng ở đây.

### 3.3. Function không trả result set

Stored function trả một giá trị theo kiểu `RETURNS`. Không viết một câu `SELECT` trần trong function với ý định gửi nhiều hàng về client:

```sql
-- Không hợp lệ như một cách trả result set từ stored function:
-- SELECT customer_id, customer_status FROM customer_profile;
```

Nếu cần trả nhiều hàng, dùng stored procedure với result set, view hoặc truy vấn SQL trực tiếp. Nếu cần dùng dữ liệu nhiều hàng nội bộ trong function, có thể cân nhắc cursor theo các giới hạn của stored program, nhưng function vẫn chỉ trả một giá trị cuối cùng.

### 3.4. Dọn routine và cập nhật định nghĩa

```sql
USE appdb;

SHOW CREATE FUNCTION apply_discount\G

ALTER FUNCTION apply_discount
COMMENT 'Calculate a percentage discount';

DROP FUNCTION IF EXISTS apply_discount;
```

`ALTER FUNCTION` chỉ thay đổi các characteristic được hỗ trợ, không thay phần thân routine. Khi cần thay body, quy trình migration thường là `DROP FUNCTION` rồi `CREATE FUNCTION` lại; phải lập kế hoạch quyền và phụ thuộc trước khi thực hiện. Không giả định cú pháp `CREATE OR REPLACE FUNCTION` của hệ quản trị khác có sẵn trong MySQL.

## 4. DETERMINISTIC và SQL data access characteristics

Các characteristic mô tả hành vi mà routine khai báo với MySQL. Chúng có ý nghĩa đối với binary logging và quản trị, nhưng không phải bộ kiểm chứng tự động cho logic bên trong.

### 4.1. DETERMINISTIC và NOT DETERMINISTIC

- `DETERMINISTIC`: cùng tham số đầu vào phải luôn tạo cùng kết quả.
- `NOT DETERMINISTIC`: kết quả có thể thay đổi dù tham số không đổi.

Ví dụ phù hợp với `DETERMINISTIC`:

```sql
USE appdb;

CREATE FUNCTION tax_amount(
    p_net DECIMAL(12, 2),
    p_rate DECIMAL(5, 2)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN p_net * p_rate / 100;
```

Ví dụ không nên khai báo deterministic:

```sql
USE appdb;

CREATE FUNCTION current_label()
RETURNS VARCHAR(40)
NOT DETERMINISTIC
NO SQL
RETURN DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:%s');
```

`NOW()` phụ thuộc thời điểm thực thi. Những hàm như `RAND()` hoặc `UUID()` cũng không tạo kết quả cố định theo cùng tham số rỗng.

Khai báo `DETERMINISTIC` không làm một function vốn phụ thuộc thời gian trở nên deterministic. MySQL không phân tích đầy đủ body để chứng minh lời khai báo là đúng; người viết routine chịu trách nhiệm khai báo trung thực.

### 4.2. SQL data access characteristics

| Characteristic | Ý nghĩa khai báo | Ví dụ |
|---|---|---|
| `NO SQL` | Routine không chứa câu lệnh SQL | Phép tính từ tham số |
| `CONTAINS SQL` | Có câu lệnh SQL nhưng không đọc/ghi dữ liệu | Một số thao tác SQL không truy cập bảng |
| `READS SQL DATA` | Có thể đọc dữ liệu | `SELECT ... INTO` từ bảng |
| `MODIFIES SQL DATA` | Có thể thay đổi dữ liệu | `INSERT`, `UPDATE`, `DELETE` trong phạm vi được phép |

Nếu bỏ qua, MySQL dùng characteristic mặc định theo cú pháp của routine; nên khai báo rõ để reviewer hiểu ý định. MySQL không xác minh body có tuân thủ đúng các nhãn này hay không.

### 4.3. Đừng khai báo sai để vượt kiểm tra binary logging

Khi binary logging bật, việc tạo stored function có các kiểm tra bổ sung nhằm giảm rủi ro replication không nhất quán. Tùy phiên bản và cấu hình, các kiểm tra liên quan đến `log_bin_trust_function_creators`, characteristic `DETERMINISTIC`/`NO SQL`/`READS SQL DATA` và quyền quản trị.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_trust_function_creators';
```

Không khai báo `DETERMINISTIC` hoặc `NO SQL` chỉ để DDL được chấp nhận nếu function thực tế đọc dữ liệu hay phụ thuộc trạng thái ngoài. Không bật `log_bin_trust_function_creators` ở production chỉ để bỏ qua review; đánh giá chính sách binary logging, replication mode và quyền cần thiết theo đúng phiên bản MySQL đang chạy.

## 5. SQL SECURITY DEFINER và INVOKER

Stored function có hai security context chính:

- `SQL SECURITY DEFINER`: body chạy với quyền của tài khoản definer được ghi trong định nghĩa routine.
- `SQL SECURITY INVOKER`: body chạy với quyền của tài khoản đang gọi function.

Nếu không khai báo, mặc định là `DEFINER`. Đây là ranh giới bảo mật quan trọng: người có quyền `EXECUTE` trên function DEFINER có thể thực hiện thao tác mà tài khoản đó không được cấp trực tiếp trên bảng nền, trong phạm vi function cho phép.

### 5.1. DEFINER dùng quyền của ai?

Ví dụ function đọc trạng thái khách hàng với security context DEFINER:

```sql
USE appdb;

DELIMITER //

CREATE DEFINER = 'customer_fn_owner'@'localhost'
FUNCTION customer_status_for_app(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT NULL;

    SELECT customer_status
      INTO v_status
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_status;
END//

DELIMITER ;
```

Khi ứng dụng gọi function, MySQL kiểm tra quyền `EXECUTE` của caller. Các câu lệnh bên trong function chạy theo quyền của `customer_fn_owner`@`localhost`. Caller không nhất thiết cần `SELECT` trực tiếp trên `customer_profile` nếu function được thiết kế và cấp quyền đúng.

Definer phải tồn tại và có các quyền cần thiết trên object mà body truy cập. Nếu tài khoản definer bị xóa, đổi quyền hoặc object bị thay đổi, function có thể lỗi khi thực thi. Vì vậy, definer là một dependency vận hành cần quản lý cùng routine.

### 5.2. INVOKER dùng quyền của người gọi

```sql
USE appdb;

DELIMITER //

CREATE FUNCTION customer_status_for_caller(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT NULL;

    SELECT customer_status
      INTO v_status
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_status;
END//

DELIMITER ;
```

Với INVOKER, caller cần `EXECUTE` trên function và quyền cần thiết để thực hiện các câu SQL trong body, ví dụ `SELECT` trên `customer_profile`. INVOKER phù hợp khi function chỉ đóng gói logic và không nhằm cấp một lối truy cập vượt quyền tới bảng nền.

### 5.3. So sánh quyền thực thi

| Tình huống | DEFINER | INVOKER |
|---|---|---|
| Ai cung cấp quyền cho câu SQL trong body? | Tài khoản definer | Tài khoản gọi |
| Caller cần `EXECUTE`? | Có | Có |
| Caller cần quyền trực tiếp trên bảng nền? | Thường không, nếu body chạy bằng quyền definer và function không yêu cầu truy cập khác | Có, theo các thao tác body thực hiện |
| Có thể dùng để công bố một API dữ liệu có kiểm soát? | Có, nếu body giới hạn chặt dữ liệu và quyền | Có, nhưng caller vẫn cần quyền trên object nền |
| Rủi ro chính | Function có thể trở thành đường vượt quyền nếu lộ dữ liệu hoặc nhận tham số thiếu kiểm soát | Caller phải có quyền nền; bề mặt cấp quyền thường rộng hơn |

## 6. Thiết kế definer theo least privilege

Không nên dùng tài khoản DBA, `root` hoặc tài khoản ứng dụng có toàn quyền làm definer. Tạo một tài khoản chuyên biệt chỉ có các quyền tối thiểu cần thiết cho body.

Ví dụ mô hình quyền:

```sql
-- Thực hiện bởi DBA theo chính sách tài khoản của hệ thống.
CREATE USER 'customer_fn_owner'@'localhost' ACCOUNT LOCK;

GRANT SELECT ON appdb.customer_profile
TO 'customer_fn_owner'@'localhost';

GRANT CREATE ROUTINE ON appdb.*
TO 'routine_deployer'@'localhost';

GRANT EXECUTE ON FUNCTION appdb.customer_status_for_app
TO 'app_runtime'@'%';
```

Tài khoản `customer_fn_owner` chỉ có quyền đọc bảng khách hàng. `app_runtime` được gọi function đã công bố nhưng không được cấp `SELECT` trực tiếp trên bảng nền trong mô hình này. Tài khoản bị khóa đăng nhập có thể được dùng làm definer theo chính sách/phiên bản phù hợp; cần xác minh hành vi và quy trình quản lý definer của môi trường triển khai.

### 6.1. Quyền thường gặp với stored routine

- `CREATE ROUTINE`: tạo stored procedure hoặc stored function trong schema.
- `ALTER ROUTINE`: thay đổi hoặc quản lý routine theo quyền được cấp.
- `EXECUTE`: gọi stored procedure/function.
- Quyền trên bảng/view: phụ thuộc `SQL SECURITY DEFINER` hay `INVOKER` và câu lệnh trong body.
- Quyền đặc biệt để chỉ định một definer khác: phụ thuộc phiên bản và chính sách dynamic privilege của MySQL; không cấp quyền này rộng rãi.

Trong một số cấu hình, `automatic_sp_privileges` tự động cấp một số quyền routine cho creator. Không dựa vào mặc định đó làm chính sách phân quyền; kiểm tra grants thực tế và cấp rõ quyền cho tài khoản runtime/deployer.

### 6.2. Không để function DEFINER trở thành API đọc tùy ý

Một function nhận `customer_id` và trả trạng thái có thể được giới hạn tốt. Nhưng nếu function nhận tham số tùy ý rồi trả nội dung nhạy cảm hoặc truy cập dữ liệu ngoài phạm vi caller, người có `EXECUTE` có thể dùng nó để lấy dữ liệu mà lẽ ra không được đọc.

Với dữ liệu multi-tenant, không tin `tenant_id` do client gửi nếu caller có thể giả mạo giá trị. Cần xác định tenant từ security context đáng tin cậy hoặc kiểm tra quyền sở hữu trong body bằng dữ liệu mà caller không thể tự sửa. `SQL SECURITY DEFINER` không tự tạo row-level security.

## 7. Ranh giới bảo mật của loadable UDF

Loadable UDF là native code được nạp vào process `mysqld`. Khi function được gọi, mã C/C++ chạy trong cùng tiến trình server và có thể sử dụng khả năng của process theo quyền hệ điều hành mà `mysqld` đang có.

Điều này khác căn bản với stored function:

- `SQL SECURITY DEFINER/INVOKER` không áp dụng cho UDF.
- MySQL không sandbox UDF thành một process OS độc lập.
- Lỗi bộ nhớ, con trỏ hoặc concurrency trong thư viện có thể làm hỏng hoặc dừng server.
- Mã native có thể truy cập file hoặc tài nguyên hệ điều hành mà user OS chạy `mysqld` được phép truy cập.
- Một thư viện độc hại hoặc bị thay thế có thể trở thành đường thực thi mã trong server.

Vì vậy, quyền ghi vào `plugin_dir` và quyền đăng ký UDF là quyền có tác động cao. Không cho tài khoản ứng dụng thông thường khả năng cài thư viện native.

### 7.1. Quy trình kiểm soát thư viện

Trước khi triển khai UDF:

1. Xác định rõ yêu cầu không thể đáp ứng bằng built-in function, stored function hoặc ứng dụng.
2. Review mã nguồn C/C++, dependency và cách xử lý lỗi/giải phóng bộ nhớ.
3. Build từ nguồn tin cậy trên toolchain và nền tảng đã kiểm soát.
4. Kiểm tra tương thích OS, kiến trúc CPU, ABI và phiên bản MySQL.
5. Kiểm tra hash/signature của artifact và quyền ghi thư mục plugin.
6. Thử trên staging với dữ liệu biên, tải đồng thời và tình huống lỗi.
7. Cài cùng thư viện trên mọi node có thể thực thi function, gồm replica/failover node theo kiến trúc.
8. Đăng ký UDF, xác minh function được nạp và thử rollback/uninstall.
9. Theo dõi lỗi server, memory, CPU và thời gian truy vấn sau triển khai.
10. Có kế hoạch gỡ đăng ký và xóa artifact an toàn khi không còn dùng.

Không copy một file `.so`/`.dll` không rõ nguồn gốc vào `plugin_dir`. Không cho phép upload file tùy ý vào thư mục này.

## 8. Cài đặt và gỡ loadable function

### 8.1. Kiểm tra thư mục plugin

```sql
SHOW VARIABLES LIKE 'plugin_dir';
```

Thư viện phải được cài trong vị trí MySQL cho phép nạp loadable function và phải phù hợp với nền tảng server. Tên thư viện trong `SONAME` là tên file, không phải đường dẫn tùy ý do client truyền vào.

### 8.2. Đăng ký UDF scalar

```sql
CREATE FUNCTION normalize_code
RETURNS STRING
SONAME 'normalize_code.so';
```

Lệnh chỉ đăng ký một function có implementation native tương ứng trong thư viện. Nếu symbol, kiểu trả về hoặc UDF API không tương thích, việc đăng ký hoặc thực thi sẽ thất bại.

### 8.3. UDF aggregate

MySQL cũng hỗ trợ loadable aggregate function. Cú pháp đăng ký có từ khóa `AGGREGATE`:

```sql
CREATE AGGREGATE FUNCTION weighted_stat
RETURNS REAL
SONAME 'analytics_udf.so';
```

Chỉ dùng cú pháp này khi thư viện đã triển khai đầy đủ giao diện aggregate UDF phù hợp. Không thể biến một UDF scalar thành aggregate chỉ bằng cách thêm từ khóa `AGGREGATE`.

### 8.4. Gỡ UDF

```sql
DROP FUNCTION IF EXISTS normalize_code;
```

Gỡ đăng ký function trước khi loại bỏ file thư viện khỏi môi trường server. Kiểm tra mọi query, routine hoặc ứng dụng còn phụ thuộc UDF. Không sửa trực tiếp bảng hệ thống để đăng ký/gỡ UDF; dùng câu lệnh SQL được hỗ trợ.

### 8.5. Quyền cài đặt UDF

Quyền tạo/gỡ loadable function khác mô hình `CREATE ROUTINE`/`EXECUTE` của stored function. MySQL có yêu cầu quyền trên schema hệ thống `mysql` đối với thao tác đăng ký/gỡ loadable function; chi tiết phụ thuộc phiên bản. Đây là quyền nhạy cảm, không cấp rộng cho runtime account và không dùng quyền ghi tùy ý lên system schema như cách triển khai ứng dụng.

Kiểm tra quyền theo tài liệu đúng phiên bản đang chạy. Tuyệt đối không chỉnh trực tiếp registry của UDF trong bảng hệ thống để thay thế `CREATE FUNCTION ... SONAME` hoặc `DROP FUNCTION`.

## 9. Stored function không phải stored procedure

Hai loại routine này đều được lưu trong schema nhưng có giao diện khác:

| Đặc điểm | Stored function | Stored procedure |
|---|---|---|
| Cách gọi | Trong biểu thức SQL, ví dụ `SELECT f(x)` | Bằng `CALL p(...)` |
| Kết quả | Một giá trị theo `RETURNS` | Có thể trả result set, OUT/INOUT hoặc thay đổi trạng thái |
| Tham số | Chỉ đầu vào | IN, OUT, INOUT |
| Dùng trong WHERE/SELECT expression | Có | Không gọi procedure trực tiếp như biểu thức |
| Phù hợp | Phép tính/tra cứu scalar | Workflow nhiều bước, trả nhiều hàng hoặc thao tác nghiệp vụ |

Nếu mục tiêu là trả một scalar để sử dụng trong biểu thức, stored function phù hợp. Nếu cần trả danh sách hàng hoặc điều khiển transaction nhiều bước, cân nhắc stored procedure hoặc truy vấn trực tiếp.

## 10. Các giới hạn quan trọng của stored function

Stored function chạy trong ngữ cảnh của một câu lệnh gọi và chịu các giới hạn của stored routine. Những giới hạn cần nhớ:

- Function phải trả giá trị scalar; không trả result set trực tiếp.
- Không dùng `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK` để tự quản lý transaction bên trong function.
- Không dùng dynamic SQL qua `PREPARE`/`EXECUTE` trong stored function.
- Không thực hiện thao tác gây implicit commit như một workflow DDL thông thường bên trong function.
- Không sửa một bảng đang được câu lệnh gọi function sử dụng; có thể gặp lỗi như 1442.
- Không dựa vào thứ tự hoặc số lần optimizer đánh giá biểu thức function để thực hiện side effect.

Ví dụ, tránh thiết kế function được gọi trong `UPDATE customer_profile ...` rồi bên trong function lại cập nhật chính `customer_profile`. Nếu cần thay đổi nhiều bảng, dùng stored procedure hoặc transaction ở tầng ứng dụng với ranh giới rõ ràng.

### 10.1. Không dùng function có side effect như biểu thức thuần

Một function được gọi trong `SELECT`, `WHERE` hoặc `ORDER BY` có thể được đánh giá theo cách phụ thuộc kế hoạch thực thi. Không dựa vào việc function sẽ chạy đúng một lần cho mỗi hàng, chạy theo thứ tự trái sang phải hoặc chỉ chạy sau một predicate cụ thể.

Nếu function thay đổi dữ liệu, gửi thông báo hoặc tạo side effect, việc dùng nó trong biểu thức có thể gây hành vi khó dự đoán. Ưu tiên function thuần chỉ tính/trả giá trị; đặt thao tác thay đổi dữ liệu trong procedure hoặc lệnh DML rõ ràng.

### 10.2. Gọi function trên nhiều hàng có thể tốn chi phí

Ví dụ:

```sql
SELECT
    customer_id,
    get_customer_status(customer_id)
FROM customer_profile;
```

Nếu bảng có hàng triệu khách hàng, function có thể được gọi rất nhiều lần và mỗi lần lại truy vấn bảng. Một JOIN trực tiếp thường dễ tối ưu hơn:

```sql
SELECT customer_id, customer_status
FROM customer_profile;
```

Đóng gói logic không đồng nghĩa truy vấn tự động nhanh hơn. Đo bằng `EXPLAIN ANALYZE`, latency và workload đại diện; tránh gọi function đọc bảng theo từng hàng khi có thể viết phép JOIN/biểu thức set-based.

## 11. Stored function và index/sargability

Đặt function lên cột được index có thể khiến điều kiện không còn sargable theo index gốc:

```sql
-- Có thể không dùng range lookup trên email theo cách mong muốn:
SELECT customer_id
FROM customer_account
WHERE normalize_email(email) = 'user@example.com';
```

Nếu có thể chuẩn hóa giá trị đầu vào trước khi so sánh, hãy giữ cột index ở dạng trực tiếp:

```sql
SELECT customer_id
FROM customer_account
WHERE email = 'user@example.com';
```

Nếu chuẩn hóa là quy tắc lưu trữ bắt buộc, cân nhắc lưu thêm cột đã chuẩn hóa hoặc generated column được index, thay vì gọi function trên từng hàng mỗi lần truy vấn. Luôn kiểm tra bằng `EXPLAIN`/`EXPLAIN ANALYZE` trên schema thực tế.

## 12. Metadata và kiểm tra quyền

### 12.1. Kiểm tra stored function

```sql
SHOW FUNCTION STATUS
WHERE Db = 'appdb';

SHOW CREATE FUNCTION appdb.customer_status_for_app\G
```

`INFORMATION_SCHEMA.ROUTINES` cung cấp metadata của stored function và procedure:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SQL_MODE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb'
  AND ROUTINE_TYPE = 'FUNCTION'
ORDER BY ROUTINE_NAME;
```

Một số metadata definition có thể bị ẩn hoặc giới hạn theo quyền của tài khoản truy vấn. Dùng tài khoản kiểm toán có quyền phù hợp và không cấp quyền cao hơn mức cần thiết cho ứng dụng chỉ để xem metadata.

### 12.2. Kiểm tra grants

```sql
SHOW GRANTS FOR 'app_runtime'@'%';
SHOW GRANTS FOR 'customer_fn_owner'@'localhost';
```

Đối chiếu quyền `EXECUTE`, quyền truy cập bảng của definer/invoker và quyền tạo/sửa routine. Kiểm tra cả role được gán và quyền kế thừa trong phiên bản MySQL đang dùng.

### 12.3. Kiểm tra loadable UDF

Registry loadable function được MySQL quản lý ở cấp server. Có thể kiểm tra metadata registry bằng tài khoản quản trị phù hợp:

```sql
SELECT name, ret, dl, type
FROM mysql.func
ORDER BY name;
```

Chỉ đọc registry để kiểm tra. Không `INSERT`, `UPDATE` hoặc `DELETE` trực tiếp trên `mysql.func`; dùng `CREATE FUNCTION ... SONAME` và `DROP FUNCTION` để MySQL cập nhật trạng thái đúng cách.

## 13. Replication và triển khai trên nhiều server

### 13.1. Stored function

Stored function là đối tượng schema. Khi triển khai qua migration hoặc replication, cần bảo đảm định nghĩa, definer và quyền tồn tại phù hợp ở các server liên quan. Với statement-based binary logging, function không deterministic hoặc khai báo characteristic sai có thể dẫn tới kết quả khác nhau giữa source và replica.

Trước triển khai, kiểm tra:

- Function có thực sự deterministic hay phụ thuộc thời gian/trạng thái không?
- Characteristic đã khai báo có phản ánh đúng body không?
- Binary logging đang ở chế độ nào và có kiểm tra routine creator nào?
- Definer có tồn tại và được cấp quyền tương ứng trên các server cần thực thi không?
- Migration có xử lý thứ tự tạo bảng, tạo function và cấp grants không?

### 13.2. Loadable UDF

Đăng ký UDF ở một server không tự bảo đảm shared library có mặt trên các server khác. Mọi node có thể thực thi statement chứa UDF cần có đúng library, đúng phiên bản và cấu hình nạp tương thích.

Với replication/failover, nếu replica được nâng thành primary hoặc nhận truy vấn trực tiếp, thiếu thư viện có thể khiến câu SQL gọi UDF thất bại. Hãy đưa artifact native và bước đăng ký vào quy trình provisioning/deployment của từng node, không chỉ chạy DDL trên primary.

## 14. Chọn loại function theo bài toán

| Nhu cầu | Lựa chọn ưu tiên | Lý do |
|---|---|---|
| Phép tính scalar từ tham số, không truy cập bảng | Built-in hoặc stored function | Dễ triển khai và quản lý bằng SQL |
| Logic SQL dùng lại trong nhiều truy vấn | Stored function hoặc view/CTE tùy hình dạng kết quả | Được quản lý theo schema và quyền SQL |
| Trả nhiều hàng hoặc thực hiện workflow nhiều bước | Stored procedure hoặc truy vấn SQL | Function chỉ trả scalar |
| Tính toán native đặc thù, không thể biểu đạt hợp lý bằng SQL/app | Loadable UDF sau security review | Cần native code chạy trong mysqld |
| Gọi API HTTP, message broker hoặc dịch vụ ngoài | Ứng dụng/service layer | Không biến MySQL server thành nơi chạy tích hợp ngoài |
| Xử lý dữ liệu lớn theo tập | SQL set-based, JOIN, aggregate | Tránh gọi function theo từng hàng |

Không đưa logic vào UDF chỉ để giảm một lần round trip giữa ứng dụng và database. Chi phí và rủi ro vận hành của native library thường lớn hơn lợi ích đó.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm stored function với loadable UDF | Áp dụng sai quyền và cách triển khai | Xác định function chạy bằng SQL routine hay shared library native |
| Khai báo `DETERMINISTIC` cho function dùng `NOW()`/`RAND()` | Metadata sai, rủi ro binary logging/replication | Khai báo trung thực và kiểm tra body |
| Khai báo `NO SQL` dù function đọc bảng | Characteristic không phản ánh hành vi | Dùng `READS SQL DATA` hoặc characteristic đúng |
| Dùng DEFINER là `root` | Caller có thể tiếp cận dữ liệu/quyền quá rộng qua function | Dùng definer chuyên biệt, least privilege |
| Không cấp `EXECUTE` cho runtime account | Caller không gọi được stored function | Cấp quyền routine-level đúng function |
| Xóa definer mà không kiểm tra routine phụ thuộc | Function có thể lỗi khi chạy | Kiểm kê `INFORMATION_SCHEMA.ROUTINES` và migration quyền |
| Dùng stored function để trả nhiều hàng | Không phù hợp contract scalar | Dùng procedure/view/query |
| Function sửa bảng mà statement gọi cũng đang dùng | Có thể gặp lỗi 1442 | Tách thao tác thành procedure hoặc transaction rõ ràng |
| Gọi function đọc bảng cho từng hàng lớn | Nhiều lần lookup, query chậm | Viết JOIN hoặc xử lý set-based |
| Dùng UDF không rõ nguồn gốc | Native code có thể làm hỏng server hoặc truy cập OS | Chỉ cài artifact đã review, ký và kiểm soát |
| Chỉ cài UDF trên primary | Failover/replica có thể thiếu library | Provision và kiểm tra mọi node cần thực thi |
| Sửa trực tiếp `mysql.func` | Registry không nhất quán | Dùng `CREATE FUNCTION ... SONAME`/`DROP FUNCTION` |

## 16. Quy trình review stored function

Trước khi đưa stored function vào production:

1. Xác định contract: tham số, kiểu trả về, NULL behavior và lỗi có thể phát sinh.
2. Kiểm tra function có thực sự cần tồn tại hay built-in/biểu thức SQL đã đủ.
3. Xác định function deterministic hay phụ thuộc bảng/thời gian/trạng thái.
4. Khai báo SQL data access characteristic đúng với body.
5. Chọn `SQL SECURITY DEFINER` hay `INVOKER` dựa trên mô hình quyền.
6. Nếu dùng DEFINER, tạo tài khoản riêng với quyền tối thiểu và có vòng đời quản lý rõ.
7. Cấp `EXECUTE` cho đúng runtime principal; tránh cấp quyền rộng trên schema.
8. Kiểm tra các giới hạn stored function và side effect.
9. Đo tác động khi function được gọi trên tập nhiều hàng.
10. Kiểm tra binary logging, replication và definer trên các node.
11. Thêm migration tạo function, grants và migration rollback có kiểm soát.
12. Kiểm tra `SHOW CREATE FUNCTION`, `INFORMATION_SCHEMA.ROUTINES` và `SHOW GRANTS` sau deploy.

## 17. Quy trình review loadable UDF

Trước khi cho phép native UDF:

1. Viết lý do kỹ thuật tại sao stored function/built-in/app code không đáp ứng.
2. Review nguồn native và dependency; xác định API mà thư viện gọi.
3. Kiểm tra memory safety, concurrency, xử lý NULL, lỗi và giới hạn input.
4. Build artifact tin cậy cho từng OS/architecture/ABI.
5. Giới hạn quyền ghi vào `plugin_dir` và quyền đăng ký UDF.
6. Kiểm tra artifact trên staging đúng phiên bản MySQL.
7. Kiểm thử tải, lỗi và failover; quan sát ảnh hưởng tới process `mysqld`.
8. Cài và đăng ký trên mọi node cần function.
9. Ghi nhận owner, phiên bản thư viện, hash và quy trình nâng cấp/gỡ bỏ.
10. Có phương án rollback trước khi triển khai production.

## 18. Bài thực hành

Thực hiện trong MySQL lab riêng; không cài native UDF không rõ nguồn gốc trên production:

1. Tạo stored function `line_total` với `DETERMINISTIC`, `NO SQL`, `SQL SECURITY INVOKER`; gọi bằng `SELECT`.
2. Thử tham số `NULL` và xác định contract trả về.
3. Tạo function `get_customer_status` dùng `SELECT ... INTO`; kiểm tra trường hợp có hàng và không có hàng.
4. Thay đổi dữ liệu bảng rồi gọi lại function; giải thích vì sao function đọc dữ liệu không deterministic theo tham số đơn thuần.
5. Xem `SHOW CREATE FUNCTION` và `INFORMATION_SCHEMA.ROUTINES` để xác nhận characteristic.
6. Tạo hai tài khoản lab: definer chỉ có `SELECT` trên một bảng và invoker là runtime user.
7. Tạo function DEFINER; cấp `EXECUTE` cho runtime user nhưng không cấp `SELECT` bảng nền; kiểm tra caller gọi function được trong phạm vi đã công bố.
8. Tạo function INVOKER; kiểm tra runtime user cần quyền bảng nền và so sánh lỗi khi thiếu quyền.
9. Thu hồi quyền `EXECUTE`; xác nhận caller không còn gọi được routine.
10. Kiểm tra `SHOW GRANTS` của definer và runtime user; giải thích quyền nào được dùng trong body.
11. Xem `log_bin` và `log_bin_trust_function_creators`; ghi lại yêu cầu tạo function trong cấu hình lab.
12. Chạy `EXPLAIN` cho truy vấn gọi function theo từng hàng; viết lại bằng JOIN/biểu thức SQL khi phù hợp và so sánh.
13. Đọc cú pháp `CREATE FUNCTION ... SONAME` và xác định các thành phần cần có để một UDF native được nạp; không dùng thư viện không tin cậy.
14. Nếu môi trường có một UDF mẫu đã được phê duyệt, kiểm tra `plugin_dir`, đăng ký, gọi, kiểm tra registry và gỡ bằng `DROP FUNCTION`.
15. Viết threat model so sánh stored function DEFINER với loadable UDF: database privileges, OS privileges, deployment và failure domain.
16. Viết runbook triển khai stored function trên source/replica và runbook phân phối native library trên các node.

Bạn hoàn thành bài khi giải thích được nơi mã chạy, ai cấp quyền cho body, ai có thể gọi function, cách function được triển khai và rủi ro lớn nhất của từng loại.

## 19. Nguyên tắc cần ghi nhớ

- Stored function là SQL routine thuộc schema; loadable UDF là native library được MySQL server nạp.
- Cả hai có thể được gọi trong biểu thức SQL nhưng không có cùng mô hình quyền hoặc deployment.
- Stored function trả một giá trị scalar bằng `RETURN`; procedure phù hợp hơn khi cần result set hoặc workflow nhiều bước.
- `DETERMINISTIC` và SQL data access characteristics là lời khai báo; MySQL không chứng minh body đúng với nhãn đó.
- Function phụ thuộc thời gian, ngẫu nhiên hoặc trạng thái bảng không nên khai báo deterministic một cách tùy tiện.
- `SQL SECURITY DEFINER` chạy body bằng quyền definer; `INVOKER` dùng quyền caller.
- Caller cần `EXECUTE`; quyền trên bảng nền phụ thuộc security context.
- Dùng definer chuyên biệt và least privilege; không dùng `root` làm definer.
- Stored function có giới hạn transaction, dynamic SQL, result set và sửa bảng đang được statement gọi sử dụng.
- Không dựa vào số lần/thứ tự optimizer gọi function để tạo side effect.
- Gọi stored function đọc bảng trên hàng triệu dòng có thể tốn hơn JOIN/set-based SQL.
- Loadable UDF chạy trong tiến trình `mysqld`; native code có thể ảnh hưởng toàn bộ server và quyền OS của process.
- Kiểm soát chặt thư viện, plugin directory, quyền cài đặt, artifact và tương thích trên mọi node.
- Không sửa trực tiếp registry UDF trong system schema; dùng lệnh CREATE/DROP được hỗ trợ.
- Chỉ chọn UDF khi native execution thực sự cần thiết và có quy trình security/operations tương xứng.
