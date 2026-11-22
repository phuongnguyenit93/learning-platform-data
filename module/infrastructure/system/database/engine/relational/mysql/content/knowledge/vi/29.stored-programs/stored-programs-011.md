# PREPARE, EXECUTE, DEALLOCATE PREPARE và phạm vi SQL động được phép

MySQL cho phép tạo và chạy một câu SQL từ chuỗi trong lúc chương trình đang thực thi. Cơ chế này thường được gọi là **dynamic SQL**. Với SQL-level prepared statement, vòng đời cơ bản gồm ba lệnh:

1. `PREPARE` phân tích câu SQL và đăng ký một prepared statement trong session hiện tại.
2. `EXECUTE` chạy statement đã chuẩn bị, có thể truyền giá trị vào các parameter marker `?`.
3. `DEALLOCATE PREPARE` giải phóng statement khi không còn dùng.

Dynamic SQL hữu ích khi cấu trúc câu lệnh thực sự thay đổi lúc chạy, chẳng hạn tên bảng được chọn từ một tập bảng cho phép hoặc thứ tự sắp xếp được chọn từ một chế độ đã định nghĩa. Với dữ liệu đầu vào thông thường, hãy dùng parameter marker thay vì nối giá trị vào chuỗi SQL. Parameter marker bảo vệ vị trí giá trị; nó không thay thế được tên bảng, tên cột, keyword hoặc cú pháp SQL.

Trong module `DATABASE_MYSQL`, bài học này giúp bạn hiểu vòng đời prepared statement, phạm vi session, giới hạn khi dùng trong stored program và cách xây dynamic SQL có kiểm soát. Ví dụ tập trung vào stored procedure; SQL-level prepared statement không được dùng trong stored function hoặc trigger vì statement có phạm vi session và có thể tồn tại sau khi routine kết thúc.

## 1. Dynamic SQL và prepared statement

Một câu SQL thông thường có cấu trúc cố định khi được gửi tới server:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';
```

Nếu ứng dụng muốn đổi giá trị tenant hoặc status, không cần tạo chuỗi SQL mới bằng cách nối các giá trị. Có thể chuẩn bị một câu lệnh có parameter marker:

```sql
PREPARE stmt_orders FROM
    'SELECT order_id, status, total_amount
     FROM orders
     WHERE tenant_id = ? AND status = ?';

SET @tenant_id = 42;
SET @order_status = 'PAID';

EXECUTE stmt_orders USING @tenant_id, @order_status;
DEALLOCATE PREPARE stmt_orders;
```

Server phân tích statement ở bước `PREPARE`; `EXECUTE` cung cấp các giá trị tương ứng cho dấu `?`. Sau khi chạy xong, `DEALLOCATE PREPARE` giải phóng statement.

### SQL-level prepared statement và prepared statement của driver

Có hai cách phổ biến để dùng prepared statement:

- **SQL-level:** gửi các lệnh `PREPARE`, `EXECUTE`, `DEALLOCATE PREPARE` trực tiếp qua SQL.
- **Client API/protocol:** dùng API của driver như `prepare()` và `execute()`; driver giao tiếp với server bằng prepared-statement protocol.

Hai cách có mục tiêu tương tự nhưng giao diện và phạm vi quản lý khác nhau. Bài này tập trung vào SQL-level prepared statement bên trong MySQL và stored procedure. Khi viết ứng dụng, nên ưu tiên parameter binding của driver thay vì tự ghép chuỗi SQL.

## 2. Cú pháp và vòng đời ba lệnh

### PREPARE

Cú pháp:

```sql
PREPARE statement_name FROM preparable_statement;
```

`preparable_statement` là string literal hoặc user-defined variable chứa một câu SQL có thể chuẩn bị. Ví dụ:

```sql
SET @sql_text =
    'SELECT order_id FROM orders WHERE tenant_id = ?';

PREPARE stmt_find_orders FROM @sql_text;
```

Ở bước này, MySQL phân tích câu SQL và tạo prepared statement có tên `stmt_find_orders` trong session hiện tại. Nếu cú pháp hoặc loại statement không được hỗ trợ, lỗi xuất hiện ngay ở `PREPARE`.

### EXECUTE

Cú pháp:

```sql
EXECUTE statement_name
USING @user_variable [, @user_variable] ...;
```

Ví dụ:

```sql
SET @tenant_id = 42;
EXECUTE stmt_find_orders USING @tenant_id;
```

Số biến trong `USING` phải khớp số parameter marker `?` trong statement, theo đúng thứ tự xuất hiện. Giá trị của từng user variable được dùng cho marker tương ứng.

### DEALLOCATE PREPARE

Cú pháp:

```sql
DEALLOCATE PREPARE statement_name;
```

Lệnh này giải phóng prepared statement trong session. `DROP PREPARE statement_name` là cú pháp đồng nghĩa được MySQL hỗ trợ.

### Vòng đời tổng quát

```text
SQL text (string literal hoặc @user_variable)
                    |
                    v
             PREPARE stmt
                    |
          statement tồn tại trong session
                    |
                    v
        EXECUTE stmt USING @value...
                    |
          có thể EXECUTE nhiều lần
                    |
                    v
          DEALLOCATE PREPARE stmt
                    |
             giải phóng statement
```

Không nên để statement tồn tại lâu hơn nhu cầu. Prepared statement chưa được deallocate vẫn chiếm tài nguyên và tính vào giới hạn prepared statement của server.

## 3. Parameter marker `?` dùng cho giá trị

Parameter marker đại diện cho **data value** tại vị trí mà cú pháp SQL cho phép một giá trị. Ví dụ:

```sql
SET @sql_text =
    'SELECT order_id, total_amount
     FROM orders
     WHERE tenant_id = ?
       AND status = ?
       AND created_at >= ?
       AND created_at < ?';

PREPARE stmt_orders_by_range FROM @sql_text;

SET @p_tenant = 42;
SET @p_status = 'PAID';
SET @p_from = '2026-01-01 00:00:00';
SET @p_until = '2026-02-01 00:00:00';

EXECUTE stmt_orders_by_range
USING @p_tenant, @p_status, @p_from, @p_until;

DEALLOCATE PREPARE stmt_orders_by_range;
```

Thứ tự `USING` tương ứng:

| Parameter marker | User variable |
|---:|---|
| Dấu `?` thứ nhất | `@p_tenant` |
| Dấu `?` thứ hai | `@p_status` |
| Dấu `?` thứ ba | `@p_from` |
| Dấu `?` thứ tư | `@p_until` |

Parameter marker giúp tách dữ liệu khỏi cấu trúc SQL. Giá trị như chuỗi có dấu nháy, dấu gạch hoặc nội dung do người dùng nhập không được diễn giải như một phần cú pháp SQL.

### Parameter marker không phải biến SQL tổng quát

`?` chỉ dùng trong prepared statement và ở vị trí giá trị hợp lệ. Nó không thể thay thế một đoạn cú pháp tùy ý. Ví dụ sau không có nghĩa là “chọn bảng theo giá trị truyền vào”:

```sql
-- Không hợp lệ để bind tên bảng bằng parameter marker
SELECT * FROM ?;
```

Tương tự, không thể dùng `?` để truyền tên cột hoặc keyword `ASC`/`DESC`:

```sql
-- Không biến ? thành tên cột cần sắp xếp
SELECT order_id, total_amount
FROM orders
ORDER BY ?;
```

Trong trường hợp `ORDER BY ?`, marker biểu diễn một giá trị biểu thức; nó không được phân tích lại thành identifier. Nếu cần thay đổi identifier hoặc hướng sort, phải chọn từ whitelist rồi ghép phần cú pháp đã được kiểm soát vào SQL text.

### Một số vị trí giá trị thường có thể dùng marker

Trong statement được hỗ trợ, marker có thể đại diện cho:

- Giá trị trong biểu thức `WHERE` hoặc `HAVING`.
- Giá trị trong `INSERT ... VALUES`.
- Giá trị gán trong `UPDATE ... SET`.
- Biên `LIMIT` khi cú pháp/version cho phép.
- Giá trị so sánh trong điều kiện JOIN hoặc biểu thức.

Khả năng chính xác phụ thuộc cú pháp của statement và phiên bản MySQL. Nếu marker được đặt ở vị trí không phải data value, server sẽ báo lỗi hoặc hiểu nó như một biểu thức giá trị chứ không phải tên đối tượng.

## 4. EXECUTE USING yêu cầu user-defined variables

Với SQL-level `EXECUTE ... USING`, các đối số phải là user-defined variables (`@variable`). Không truyền trực tiếp local variable hoặc parameter của stored procedure vào `USING`.

Ví dụ không dùng trực tiếp local variable:

```sql
-- Trong stored procedure, cách này không hợp lệ:
-- EXECUTE stmt_find USING p_tenant_id;
```

Hãy copy giá trị từ routine parameter/local variable sang user variable trước:

```sql
SET @sp_tenant_id = p_tenant_id;
EXECUTE stmt_find USING @sp_tenant_id;
```

User-defined variables có phạm vi session, không phải phạm vi routine. Vì vậy cần đặt tên có tiền tố riêng để tránh xung đột và xóa giá trị sau khi hoàn thành:

```sql
SET @sp_tenant_id = NULL;
```

Nếu connection được trả về pool, user variable có thể còn tồn tại khi connection được tái sử dụng. Việc dọn dẹp là một phần của thiết kế routine an toàn.

## 5. PREPARE nhận string literal hoặc user variable

SQL text có thể được cung cấp trực tiếp bằng string literal:

```sql
PREPARE stmt_count FROM
    'SELECT COUNT(*) FROM orders WHERE tenant_id = ?';
```

Hoặc qua user variable:

```sql
SET @sql_text =
    'SELECT COUNT(*) FROM orders WHERE tenant_id = ?';
PREPARE stmt_count FROM @sql_text;
```

Trong stored procedure, cách thường dùng là xây chuỗi bằng `CONCAT()` rồi gán cho user variable:

```sql
SET @sql_text = CONCAT(
    'SELECT order_id FROM orders ',
    'WHERE tenant_id = ?'
);
PREPARE stmt_orders FROM @sql_text;
```

Local variable có thể được dùng để xây dựng chuỗi qua `CONCAT()`, nhưng nguồn đưa vào `PREPARE` vẫn phải là string literal hoặc user variable theo cú pháp SQL-level. Không truyền local variable trực tiếp vào `PREPARE ... FROM`.

### Một PREPARE chỉ chuẩn bị một statement

SQL text phải là một statement có thể chuẩn bị. Không ghép nhiều câu lệnh phân tách bằng dấu chấm phẩy để mong `PREPARE` chạy như một script:

```sql
-- Không dùng một prepared statement để chạy hai câu độc lập
SET @sql_text =
    'UPDATE orders SET status = ? WHERE order_id = ?; SELECT * FROM orders';
```

Hãy chuẩn bị và thực thi từng statement riêng, hoặc thiết kế stored procedure với các lệnh SQL tĩnh cần thiết. Không bật multi-statements bằng cách ghép chuỗi tùy ý.

## 6. Phạm vi session của prepared statement

SQL-level prepared statement thuộc về **session/connection hiện tại**:

- Một connection có thể chuẩn bị và thực thi statement của chính nó.
- Connection khác không thể thực thi statement name đã tạo trong session này.
- Statement tồn tại sau khi stored procedure tạo nó kết thúc.
- Statement được giải phóng khi `DEALLOCATE PREPARE` hoặc khi session kết thúc.
- Tên statement nằm trong namespace của session; các routine dùng tên trùng có thể ảnh hưởng nhau nếu cùng chạy trên một connection.
- Nếu `PREPARE` dùng tên đang tồn tại, MySQL tự deallocate statement cũ trước khi chuẩn bị statement mới cùng tên; nếu lần prepare mới thất bại thì tên đó không còn statement cũ để dùng.

Ví dụ:

```sql
-- Session A
PREPARE stmt_session_demo FROM 'SELECT 1';
EXECUTE stmt_session_demo;
```

```sql
-- Session B: không thể dùng statement đã tạo trong Session A
EXECUTE stmt_session_demo;
```

Session B không có statement `stmt_session_demo`, nên câu `EXECUTE` thất bại. Việc đặt tên statement không tạo một đối tượng toàn cục dùng chung cho mọi connection.

### Prepared statement có thể tồn tại sau khi procedure kết thúc

Đây là điểm cần nhớ khi viết stored procedure. `PREPARE` trong procedure tạo statement ở session scope, không phải local scope. Nếu procedure return mà không deallocate, statement vẫn tồn tại trên connection gọi procedure.

Do đó:

- Luôn deallocate sau khi dùng.
- Dùng statement name riêng, dễ nhận diện.
- Dọn user variables được routine tạo.
- Có handler để cleanup khi `EXECUTE` phát sinh exception.
- Không giả định kết thúc procedure sẽ tự giải phóng statement.

## 7. Phạm vi SQL động được phép trong Stored Program

SQL-level prepared statement được hỗ trợ trong stored procedure, nhưng không được dùng trong stored function hoặc trigger. Lý do cốt lõi là prepared statement và user variable có phạm vi session, trong khi local variable của function/trigger có vòng đời ngắn hơn.

| Ngữ cảnh | SQL-level PREPARE/EXECUTE |
|---|---|
| SQL session bình thường | Được dùng nếu statement cụ thể được hỗ trợ. |
| Stored procedure | Được dùng, tuân theo các quy tắc session/user variable và statement support. |
| Stored function | Không được phép dùng SQL-level prepared statement. |
| Trigger | Không được phép dùng SQL-level prepared statement. |

Một stored procedure có thể dùng dynamic SQL để chọn bảng hoặc cấu trúc câu lệnh từ lựa chọn đã kiểm soát. Điều đó không có nghĩa procedure được phép thực thi bất kỳ chuỗi SQL nào nhận từ người gọi.

### Statement nào có thể PREPARE?

MySQL hỗ trợ prepared statement cho nhiều loại SQL, nhưng không phải mọi câu lệnh đều có thể chuẩn bị. Việc hỗ trợ phụ thuộc statement và phiên bản server. Ví dụ, các lệnh quản trị, lệnh điều khiển session hoặc lệnh định nghĩa stored routine có thể có hạn chế riêng.

Các nguyên tắc an toàn:

1. Chỉ chuẩn bị một statement thuộc nhóm MySQL hỗ trợ.
2. Không cố PREPARE một `PREPARE`, `EXECUTE` hoặc `DEALLOCATE PREPARE` khác để tạo chuỗi lồng nhau.
3. Không dùng prepared statement để gửi một script nhiều statement.
4. Kiểm tra tài liệu của đúng phiên bản MySQL khi cần dùng câu lệnh quản trị đặc biệt.
5. Xử lý lỗi tại `PREPARE` và `EXECUTE`; không giả định câu lệnh hợp lệ chỉ vì chuỗi đã được tạo.

## 8. Dynamic SQL không thay thế được identifier bằng parameter marker

Giả sử ứng dụng cần truy vấn một trong hai bảng `orders_current` hoặc `orders_archive`. Tên bảng là identifier, không phải data value. Cách sau không làm việc:

```sql
SET @table_name = 'orders_current';
PREPARE stmt_bad FROM 'SELECT COUNT(*) FROM ?';
EXECUTE stmt_bad USING @table_name;
```

Nếu cần dynamic identifier, hãy:

1. Nhận một mã lựa chọn từ caller.
2. Ánh xạ mã đó sang tên bảng/cột cố định trong whitelist.
3. Không dùng trực tiếp chuỗi caller gửi làm identifier.
4. Quote identifier đúng quy tắc sau khi đã whitelist.
5. Dùng parameter marker cho mọi giá trị dữ liệu còn lại.

### Ví dụ whitelist tên bảng

```sql
DELIMITER //

CREATE PROCEDURE count_orders_from_source(
    IN p_source VARCHAR(20),
    IN p_tenant_id BIGINT UNSIGNED
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_table_name VARCHAR(64);

    CASE p_source
        WHEN 'current' THEN
            SET v_table_name = 'orders_current';
        WHEN 'archive' THEN
            SET v_table_name = 'orders_archive';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported order source';
    END CASE;

    SET @sp_count_orders_sql = CONCAT(
        'SELECT COUNT(*) AS order_count FROM `',
        REPLACE(v_table_name, '`', '``'),
        '` WHERE tenant_id = ?'
    );
    SET @sp_count_orders_tenant = p_tenant_id;

    PREPARE stmt_count_orders FROM @sp_count_orders_sql;
    EXECUTE stmt_count_orders USING @sp_count_orders_tenant;
    DEALLOCATE PREPARE stmt_count_orders;

    SET @sp_count_orders_sql = NULL;
    SET @sp_count_orders_tenant = NULL;
END//

DELIMITER ;
```

`p_source` chỉ được nhận hai giá trị đã định nghĩa. Tên bảng trong SQL text được lấy từ whitelist, còn `p_tenant_id` đi qua parameter marker. Việc quote identifier bổ sung bảo vệ cú pháp tên đối tượng, nhưng whitelist mới là bước quyết định caller có được chọn đối tượng đó hay không.

Procedure minh họa giả định hai bảng đã tồn tại và có cột `tenant_id`. Trong môi trường thật, cần kiểm soát quyền truy cập hai bảng và chính sách dữ liệu archive.

## 9. Ví dụ chọn ORDER BY từ whitelist

Một use case thường gặp là cho phép người dùng chọn kiểu sắp xếp. Không thể bind tên cột hoặc hướng `ASC`/`DESC` bằng marker. Hãy ánh xạ lựa chọn sang đoạn SQL cố định:

```sql
DELIMITER //

CREATE PROCEDURE find_orders_dynamic_sort(
    IN p_tenant_id BIGINT UNSIGNED,
    IN p_sort_mode VARCHAR(20),
    IN p_sort_direction VARCHAR(4),
    IN p_limit INT UNSIGNED
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_order_column VARCHAR(32);
    DECLARE v_direction VARCHAR(4);
    DECLARE v_limit INT UNSIGNED;

    CASE p_sort_mode
        WHEN 'created' THEN
            SET v_order_column = 'created_at';
        WHEN 'amount' THEN
            SET v_order_column = 'total_amount';
        WHEN 'id' THEN
            SET v_order_column = 'order_id';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported sort column';
    END CASE;

    CASE UPPER(p_sort_direction)
        WHEN 'ASC' THEN
            SET v_direction = 'ASC';
        WHEN 'DESC' THEN
            SET v_direction = 'DESC';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported sort direction';
    END CASE;

    SET v_limit = LEAST(COALESCE(p_limit, 50), 100);

    SET @sp_find_orders_sql = CONCAT(
        'SELECT order_id, status, created_at, total_amount ',
        'FROM orders WHERE tenant_id = ? ',
        'ORDER BY `', v_order_column, '` ', v_direction,
        ', order_id DESC LIMIT ?'
    );
    SET @sp_find_orders_tenant = p_tenant_id;
    SET @sp_find_orders_limit = v_limit;

    PREPARE stmt_find_orders FROM @sp_find_orders_sql;
    EXECUTE stmt_find_orders
        USING @sp_find_orders_tenant, @sp_find_orders_limit;
    DEALLOCATE PREPARE stmt_find_orders;

    SET @sp_find_orders_sql = NULL;
    SET @sp_find_orders_tenant = NULL;
    SET @sp_find_orders_limit = NULL;
END//

DELIMITER ;
```

Chỉ `v_order_column` và `v_direction` được ghép vào SQL text, và cả hai đã được ánh xạ từ whitelist. `p_tenant_id` và `v_limit` là giá trị nên được bind qua `?`. `order_id DESC` là tie-breaker cố định để kết quả có thứ tự xác định khi nhiều hàng bằng nhau ở cột sort chính.

Giới hạn `LIMIT` ở ví dụ là chính sách ứng dụng, không phải giới hạn bắt buộc của MySQL. Giá trị đầu vào được kiểm soát trước khi bind để tránh một caller yêu cầu tập kết quả quá lớn.

## 10. Cleanup khi có lỗi

Nếu `EXECUTE` thất bại mà procedure thoát ngay, prepared statement có thể vẫn tồn tại trong session. Dùng `EXIT HANDLER` để giải phóng statement nếu nó đã được tạo, dọn user variables và phát lại lỗi ban đầu bằng `RESIGNAL`.

Ví dụ khung xử lý:

```sql
DELIMITER //

CREATE PROCEDURE count_orders_safe(
    IN p_tenant_id BIGINT UNSIGNED
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_prepared BOOLEAN DEFAULT FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_prepared THEN
            DEALLOCATE PREPARE stmt_count_orders_safe;
        END IF;

        SET @sp_count_orders_safe_sql = NULL;
        SET @sp_count_orders_safe_tenant = NULL;
        RESIGNAL;
    END;

    SET @sp_count_orders_safe_sql =
        'SELECT COUNT(*) AS order_count
         FROM orders
         WHERE tenant_id = ?';
    SET @sp_count_orders_safe_tenant = p_tenant_id;

    PREPARE stmt_count_orders_safe
        FROM @sp_count_orders_safe_sql;
    SET v_prepared = TRUE;

    EXECUTE stmt_count_orders_safe
        USING @sp_count_orders_safe_tenant;

    DEALLOCATE PREPARE stmt_count_orders_safe;
    SET v_prepared = FALSE;

    SET @sp_count_orders_safe_sql = NULL;
    SET @sp_count_orders_safe_tenant = NULL;
END//

DELIMITER ;
```

Biến `v_prepared` chỉ được đặt TRUE sau khi `PREPARE` thành công. Nếu `PREPARE` lỗi, handler không cố deallocate một statement chưa tồn tại. Nếu `EXECUTE` lỗi, handler giải phóng statement rồi `RESIGNAL` để caller vẫn nhận lỗi gốc.

Trong procedure thực tế, hãy dùng statement name riêng cho từng routine và không tái sử dụng cùng tên cho nhiều mục đích trong một session. Nếu một routine có nhiều nhánh dynamic SQL, cần theo dõi rõ statement nào đã được prepare để cleanup đúng statement.

## 11. Bảo vệ khỏi SQL injection

SQL injection xảy ra khi dữ liệu không tin cậy bị diễn giải thành cú pháp SQL. Prepared statement giúp ngăn lỗi này ở vị trí giá trị vì dữ liệu được truyền riêng qua parameter marker.

### Cách không an toàn

```sql
-- Không ghép input trực tiếp vào literal SQL
SET @sql_text = CONCAT(
    'SELECT order_id FROM orders WHERE status = ''',
    @user_status,
    ''''
);
```

Nếu `@user_status` chứa nội dung có dấu nháy và cú pháp SQL, cấu trúc câu lệnh có thể bị thay đổi.

### Cách an toàn cho data value

```sql
SET @sql_text =
    'SELECT order_id FROM orders WHERE status = ?';
SET @user_status = 'PAID';

PREPARE stmt_status FROM @sql_text;
EXECUTE stmt_status USING @user_status;
DEALLOCATE PREPARE stmt_status;
```

Giá trị `@user_status` được truyền như data, không được nối vào cú pháp SQL.

### Với identifier, dùng allowlist

Parameter marker không thể bind tên bảng/cột. Không nhận trực tiếp identifier từ caller rồi nối vào chuỗi. Hãy dùng enum/mã lựa chọn và ánh xạ tới danh sách identifier cố định như ví dụ `p_source` và `p_sort_mode` ở trên.

Quote identifier bằng backtick giúp bảo vệ cú pháp khi tên có ký tự đặc biệt; nó không tự cấp quyền truy cập và không thay thế whitelist. Không dùng `QUOTE()` như cách thay thế parameter binding cho giá trị; `QUOTE()` tạo biểu diễn string literal, còn prepared marker mới giữ dữ liệu tách khỏi SQL text.

## 12. SQL SECURITY DEFINER và SQL SECURITY INVOKER

Stored procedure có thể khai báo ngữ cảnh quyền thực thi:

- `SQL SECURITY DEFINER`: routine chạy với quyền của definer.
- `SQL SECURITY INVOKER`: routine chạy với quyền của caller.

Dynamic SQL bên trong procedure chịu ảnh hưởng của ngữ cảnh bảo mật routine. Vì vậy, một procedure `SQL SECURITY DEFINER` có thể thực thi câu dynamic SQL với quyền rộng hơn caller. Nếu identifier được ghép từ input không tin cậy, rủi ro có thể trở thành truy cập ngoài phạm vi dữ liệu mà caller được phép.

Nguyên tắc:

1. Chọn DEFINER/INVOKER theo yêu cầu quyền tối thiểu.
2. Whitelist table/column/sort mode.
3. Parameterize mọi data value.
4. Không cho caller cung cấp nguyên câu SQL để procedure thực thi.
5. Kiểm tra tenant scope và quyền truy cập ở mọi nhánh dynamic SQL.
6. Dùng account definer có quyền tối thiểu cần thiết.

`SQL SECURITY INVOKER` không tự động làm dynamic SQL an toàn nếu câu SQL vẫn bị ghép từ input không tin cậy. Parameterization và whitelist vẫn bắt buộc.

## 13. Statement name, user variable và connection pool

Prepared statement name và user-defined variable đều thuộc session. Khi một connection được tái sử dụng từ pool, trạng thái session có thể còn lại từ request trước.

Ví dụ các trạng thái cần dọn:

```sql
DEALLOCATE PREPARE stmt_find_orders;
SET @sp_find_orders_sql = NULL;
SET @sp_find_orders_tenant = NULL;
SET @sp_find_orders_limit = NULL;
```

Không chạy `DEALLOCATE` một cách mù quáng nếu không biết statement có tồn tại; có thể phát sinh lỗi “unknown prepared statement handler”. Dùng handler/flag như ví dụ cleanup để chỉ deallocate khi đã prepare thành công.

Nếu hai routine trên cùng connection cùng dùng một prepared statement name, routine sau có thể va chạm với statement đang tồn tại. Chọn tên có tiền tố riêng và bảo đảm cleanup trước khi connection được trả về pool.

## 14. Giới hạn tài nguyên và quan sát prepared statement

MySQL giới hạn tổng số prepared statement đồng thời bằng biến `max_prepared_stmt_count`. Prepared statement không được deallocate có thể làm số lượng tăng và cuối cùng khiến lệnh `PREPARE` mới thất bại.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'max_prepared_stmt_count';
```

Kiểm tra số statement hiện đang được chuẩn bị:

```sql
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
```

Có thể xem statement được Performance Schema instrument ghi nhận:

```sql
SELECT
    STATEMENT_ID,
    STATEMENT_NAME,
    SQL_TEXT,
    OWNER_THREAD_ID
FROM performance_schema.prepared_statements_instances;
```

Khả năng quan sát phụ thuộc Performance Schema và instrumentation của server. Không phải mọi client-side prepared statement đều nhất thiết được nhìn giống nhau trong bảng này; hãy xác định đúng loại prepared statement đang điều tra.

Nếu `Prepared_stmt_count` tăng liên tục, kiểm tra routine có bỏ quên `DEALLOCATE PREPARE`, connection pool có giữ session lâu hay không và ứng dụng có tạo statement name mới không giới hạn không.

## 15. Prepared statement có luôn nhanh hơn SQL thường không?

Prepared statement có thể giảm chi phí parse lặp lại khi cùng một cấu trúc statement được thực thi nhiều lần với các giá trị khác nhau. Nó cũng tách dữ liệu khỏi cú pháp và giúp tránh SQL injection ở vị trí value.

Nhưng không có nghĩa mọi dynamic SQL hoặc prepared statement đều nhanh hơn:

- Nếu chỉ chạy một lần, chi phí `PREPARE` có thể không được bù lại.
- Nếu cấu trúc SQL thay đổi liên tục, lợi ích tái sử dụng statement giảm.
- Optimizer vẫn phải chọn execution plan và chi phí đọc dữ liệu/index vẫn tồn tại.
- Thay đổi metadata có thể khiến server phải kiểm tra hoặc prepare lại statement.
- Dynamic identifier tạo ra nhiều câu SQL khác nhau, không thể dùng cùng một statement text cho mọi identifier.
- Nối chuỗi SQL không làm truy vấn nhanh hơn; nó chỉ tạo SQL text khác nhau.

Hãy đo workload thực tế và cân nhắc prepared statement vì an toàn, quản lý tham số và khả năng tái sử dụng; không dùng nó như mẹo tối ưu hiệu năng mặc định.

## 16. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `?` cho tên bảng/cột | Marker chỉ đại diện data value | Dùng whitelist identifier và ghép phần cú pháp đã kiểm soát. |
| Ghép user input vào SQL text | Có thể tạo SQL injection | Bind giá trị qua `EXECUTE ... USING`. |
| Truyền local variable trực tiếp vào `USING` | SQL-level EXECUTE yêu cầu user variable | Copy sang `@user_variable` trước. |
| PREPARE từ local variable | Nguồn PREPARE phải là string literal hoặc user variable | Gán SQL text vào `@sql` rồi PREPARE từ đó. |
| Không DEALLOCATE | Statement tồn tại trong session sau procedure | Luôn cleanup ở đường thành công và exception handler. |
| Nghĩ statement tự mất khi procedure kết thúc | Statement có session scope | Deallocate rõ ràng. |
| Dùng PREPARE trong stored function/trigger | SQL-level prepared statement không được phép trong các ngữ cảnh này | Dùng SQL tĩnh hoặc chuyển logic phù hợp sang stored procedure. |
| Ghép nhiều câu SQL vào một PREPARE | Một prepared statement chỉ chứa một statement | Prepare/execute từng statement riêng. |
| Không kiểm tra số marker và USING arguments | Số lượng/thứ tự tham số không khớp | Đối chiếu từng dấu `?` với user variable tương ứng. |
| Dùng tên statement chung trong nhiều routine | Va chạm namespace session | Dùng tên riêng và cleanup đúng vòng đời. |
| Chọn SQL SECURITY DEFINER mà không whitelist | Dynamic SQL có thể chạy với quyền definer | Quyền tối thiểu, whitelist và kiểm tra tenant scope. |
| Nghĩ PREPARE luôn làm query nhanh | Bỏ qua parse cost, plan và I/O thực tế | Đo trước/sau với cùng workload. |

## 17. Quy trình viết dynamic SQL an toàn

Khi một stored procedure thực sự cần dynamic SQL, thực hiện theo trình tự:

1. Xác định phần nào của SQL buộc phải thay đổi: table, column, sort mode hay một nhánh statement.
2. Giữ mọi giá trị dữ liệu ở dạng parameter marker `?`.
3. Xác định identifier được phép bằng whitelist hoặc mapping nội bộ.
4. Quote identifier theo quy tắc MySQL sau khi đã xác nhận nó thuộc allowlist.
5. Xây đúng một statement SQL trong user variable.
6. Gán user variables cho các parameter marker theo đúng thứ tự.
7. `PREPARE` với statement name riêng.
8. Đánh dấu trạng thái đã prepare để handler biết có cần cleanup.
9. `EXECUTE ... USING` và kiểm tra kết quả/lỗi.
10. `DEALLOCATE PREPARE` trong đường thành công.
11. Dùng exception handler để cleanup và `RESIGNAL` khi có lỗi.
12. Xóa user variables và kiểm tra không để trạng thái session rò rỉ sang request kế tiếp.
13. Đo hiệu năng và kiểm chứng tính đúng trên các lựa chọn identifier hợp lệ.

Nếu cấu trúc SQL không cần thay đổi, ưu tiên câu SQL tĩnh hoặc prepared statement của driver. Dynamic SQL làm tăng độ phức tạp kiểm soát cú pháp, quyền và cleanup.

## 18. Bài tập thực hành

### Bài tập A — Vòng đời PREPARE/EXECUTE/DEALLOCATE

1. Tạo `@sql_text` cho SELECT theo `tenant_id`.
2. PREPARE statement.
3. EXECUTE với hai tenant khác nhau.
4. DEALLOCATE statement.
5. Thử EXECUTE lại sau khi deallocate và giải thích lỗi.

### Bài tập B — Thứ tự parameter marker

1. Chuẩn bị SELECT có bốn marker: tenant, status, from time và until time.
2. EXECUTE bằng bốn user variables.
3. Đổi thứ tự hai biến và quan sát kết quả.
4. Thử thiếu một biến trong USING.
5. Giải thích vì sao thứ tự và số lượng marker phải khớp.

### Bài tập C — Identifier không thể bind

1. Thử `SELECT * FROM ?` và giải thích vì sao không hoạt động như tên bảng động.
2. Viết stored procedure nhận `p_source`.
3. Map `current`/`archive` vào hai tên bảng cố định.
4. Từ chối mọi lựa chọn ngoài whitelist bằng `SIGNAL`.
5. Bind `tenant_id` qua parameter marker.

### Bài tập D — ORDER BY có kiểm soát

1. Cho phép sort theo `created_at`, `total_amount` hoặc `order_id`.
2. Cho phép hướng `ASC` hoặc `DESC`.
3. Whitelist cột và hướng sort.
4. Bind tenant và limit bằng marker.
5. Thêm tie-breaker để thứ tự ổn định.

### Bài tập E — Cleanup khi exception

1. Viết procedure có `EXIT HANDLER FOR SQLEXCEPTION`.
2. Theo dõi flag `v_prepared`.
3. Gây lỗi có kiểm soát trong EXECUTE.
4. Kiểm tra statement đã được deallocate và user variables đã được dọn.
5. Xác nhận lỗi gốc được trả lại bằng `RESIGNAL`.

### Bài tập F — Phạm vi session

1. PREPARE statement trong Session A.
2. Thử EXECUTE statement name đó trong Session B.
3. Gọi stored procedure tạo prepared statement nhưng cố ý chưa deallocate trong môi trường thử nghiệm.
4. Sau khi procedure kết thúc, kiểm tra statement còn trong session.
5. DEALLOCATE và xác nhận tài nguyên được giải phóng.

Bạn hoàn thành bài khi có thể mô tả vòng đời ba lệnh, phân biệt session scope với routine scope, bind đúng giá trị bằng user variable, whitelist identifier và giải thích vì sao SQL-level prepared statement chỉ được dùng trong stored procedure chứ không trong stored function/trigger.

## 19. Nguyên tắc cần ghi nhớ

- `PREPARE` phân tích một SQL statement và tạo prepared statement trong session hiện tại.
- `EXECUTE ... USING` truyền giá trị theo đúng thứ tự parameter marker `?`.
- `DEALLOCATE PREPARE` giải phóng statement; đừng dựa vào việc procedure kết thúc để tự cleanup.
- SQL text của PREPARE là string literal hoặc user-defined variable; trong routine, dùng `@variable` làm nguồn PREPARE.
- SQL-level `EXECUTE ... USING` nhận user-defined variables, không nhận trực tiếp local variable hoặc routine parameter.
- Parameter marker dùng cho data value, không dùng cho tên bảng, tên cột, keyword hoặc đoạn cú pháp.
- Dynamic identifier phải được chọn từ whitelist và quote đúng quy tắc; mọi data value vẫn phải bind.
- Một prepared statement chứa một statement có thể chuẩn bị; không ghép script nhiều câu lệnh.
- Prepared statement và user variable có session scope; connection pool có thể tái sử dụng trạng thái còn sót.
- SQL-level prepared statement được dùng trong stored procedure, không được dùng trong stored function hoặc trigger.
- Statement support phụ thuộc loại SQL và phiên bản MySQL; kiểm tra tài liệu đúng phiên bản.
- Dùng exception handler, flag trạng thái và `RESIGNAL` để cleanup khi EXECUTE lỗi.
- Chọn SQL SECURITY DEFINER/INVOKER theo quyền tối thiểu; dynamic SQL không được vượt phạm vi quyền dự kiến.
- Prepared statement hỗ trợ an toàn và tái sử dụng, nhưng không tự động làm mọi query nhanh hơn.

Khi nắm rõ `PREPARE`, `EXECUTE`, `DEALLOCATE PREPARE` và phạm vi SQL động được phép, bạn có thể xây stored procedure linh hoạt mà vẫn giữ giá trị dữ liệu tách khỏi cú pháp, giới hạn identifier theo whitelist và giải phóng tài nguyên đúng vòng đời session.
