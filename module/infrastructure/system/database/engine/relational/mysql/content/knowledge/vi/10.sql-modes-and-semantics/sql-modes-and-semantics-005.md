# ANSI_QUOTES, định danh và dấu ngoặc kép

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa dấu nháy đơn, dấu nháy kép và dấu backtick trong MySQL.
- Mô tả cách SQL mode `ANSI_QUOTES` thay đổi cách parser diễn giải dấu nháy kép.
- Viết truy vấn phân biệt string literal với identifier.
- Tránh lỗi `Unknown column` và lỗi cú pháp khi bật ANSI_QUOTES.
- Kiểm tra và thay đổi SQL mode ở phạm vi session/global một cách có kiểm soát.
- Viết DDL, truy vấn động và migration tương thích hơn giữa các môi trường MySQL.

## 1. Identifier và string literal là hai loại thành phần khác nhau

Trong SQL, **identifier** là tên của đối tượng trong database, chẳng hạn tên database, table, column, index hoặc alias. **String literal** là một giá trị văn bản được viết trực tiếp trong câu lệnh, chẳng hạn `'Nguyen An'` hoặc `'PAID'`.

Ví dụ:

```sql
SELECT customer_name
FROM customers
WHERE status = 'ACTIVE';
```

Trong câu lệnh này:

- `customer_name`, `customers` và `status` là identifier.
- `'ACTIVE'` là string literal.

MySQL có nhiều cách viết identifier và literal. Dấu nháy đơn luôn là cách thông dụng để viết string literal. Dấu backtick dùng để quote identifier theo cú pháp MySQL. Dấu nháy kép có ý nghĩa phụ thuộc SQL mode, đặc biệt là `ANSI_QUOTES`.

## 2. Quy tắc mặc định của MySQL

Khi `ANSI_QUOTES` không được bật:

- Dấu nháy đơn `'...'` biểu diễn string literal.
- Dấu nháy kép `"..."` cũng biểu diễn string literal.
- Dấu backtick `` `...` `` biểu diễn identifier.

Ví dụ:

```sql
SELECT
    'hello' AS single_quoted_text,
    "hello" AS double_quoted_text,
    `customer_name` AS customer_name_column
FROM customers;
```

Ở đây, cả `'hello'` và `"hello"` đều là chuỗi cố định. `` `customer_name` `` là tên cột. Nếu bảng không có cột `customer_name`, câu lệnh sẽ báo lỗi.

Một ví dụ dễ gây nhầm:

```sql
SELECT "customer_name"
FROM customers;
```

Ở chế độ mặc định, câu lệnh trên trả về chuỗi văn bản `customer_name` cho mỗi hàng, chứ không đọc giá trị của column. Nếu muốn đọc column, hãy viết:

```sql
SELECT customer_name
FROM customers;

-- Hoặc quote identifier theo cú pháp MySQL
SELECT `customer_name`
FROM customers;
```

Khi đọc code cũ, không thể chỉ nhìn dấu nháy kép rồi kết luận đó là tên cột. Cần biết SQL mode của session thực thi câu lệnh.

## 3. ANSI_QUOTES thay đổi ý nghĩa của dấu nháy kép

`ANSI_QUOTES` là một SQL mode của MySQL. Khi mode này được bật, dấu nháy kép được dùng để quote identifier, tương tự cách SQL chuẩn sử dụng dấu nháy kép. Dấu nháy kép **không còn dùng để viết string literal**.

Khi bật `ANSI_QUOTES`:

- `'...'` vẫn là string literal.
- `"..."` là identifier.
- `` `...` `` vẫn là identifier theo cú pháp MySQL.

Ví dụ:

```sql
-- Với ANSI_QUOTES bật, "customer_name" là tên cột
SELECT "customer_name"
FROM customers
WHERE "status" = 'ACTIVE';
```

Trong câu lệnh này, `"customer_name"` và `"status"` là identifier; `'ACTIVE'` vẫn là string literal.

Ngược lại, câu lệnh sau không còn mang nghĩa chuỗi cố định khi `ANSI_QUOTES` bật:

```sql
SELECT "hello" AS greeting;
```

MySQL sẽ diễn giải `"hello"` như identifier có tên `hello`. Nếu không có column hoặc identifier phù hợp trong ngữ cảnh đó, câu lệnh có thể báo `Unknown column 'hello' in 'field list'`. Để lấy chuỗi `hello`, phải dùng:

```sql
SELECT 'hello' AS greeting;
```

### 3.1. So sánh trước và sau khi bật mode

Giả sử có bảng:

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;
```

| Câu lệnh | Không có `ANSI_QUOTES` | Có `ANSI_QUOTES` |
|---|---|---|
| `SELECT "customer_name" FROM customers;` | Trả về chuỗi `customer_name` ở mỗi hàng | Đọc column `customer_name` |
| `SELECT 'customer_name' FROM customers;` | Trả về chuỗi `customer_name` ở mỗi hàng | Trả về chuỗi `customer_name` ở mỗi hàng |
| ``SELECT `customer_name` FROM customers;`` | Đọc column `customer_name` | Đọc column `customer_name` |
| `WHERE status = "ACTIVE"` | So sánh với string literal `ACTIVE` | Diễn giải `ACTIVE` là identifier; có thể báo lỗi nếu không tồn tại |
| `WHERE status = 'ACTIVE'` | So sánh với string literal `ACTIVE` | So sánh với string literal `ACTIVE` |

Đây là lý do một ứng dụng có thể chạy bình thường ở môi trường phát triển nhưng lỗi sau khi triển khai: hai môi trường có `sql_mode` khác nhau.

## 4. Quote identifier đúng cách

### 4.1. Dùng backtick theo cú pháp MySQL

Backtick là cách quote identifier truyền thống của MySQL và vẫn có tác dụng khi `ANSI_QUOTES` bật:

```sql
SELECT `order`, `group`, `select`
FROM `sales-data`.`order details`;
```

Ví dụ minh họa các tên có dấu cách, dấu gạch nối hoặc trùng từ khóa. Trong thiết kế mới, nên tránh tên có dấu cách hoặc tên trùng từ khóa nếu không có lý do rõ ràng. Quote identifier giúp parser nhận diện đúng tên nhưng không làm tên đó trở nên dễ bảo trì hơn.

### 4.2. Dùng dấu nháy kép khi ANSI_QUOTES được bật

Với `ANSI_QUOTES`, có thể dùng dấu nháy kép để quote identifier:

```sql
SELECT "customer_name"
FROM "customers";
```

Nếu cần tương thích với server/session có SQL mode khác nhau, backtick thường là lựa chọn MySQL-specific dễ dự đoán hơn. Nếu chủ đích dùng cú pháp ANSI, phải bảo đảm mode được cấu hình nhất quán ở mọi kết nối và môi trường.

### 4.3. Escape ký tự quote bên trong identifier

Khi tên identifier chứa chính ký tự dùng để quote, nhân đôi ký tự quote đó.

Với backtick:

```sql
SELECT `column``name`
FROM `sample``table`;
```

Với dấu nháy kép trong chế độ `ANSI_QUOTES`:

```sql
SELECT "column""name"
FROM "sample""table";
```

Không dùng backslash một cách tùy tiện để escape identifier. Quy tắc quote identifier khác với quy tắc escape string literal.

### 4.4. Quote identifier không thay đổi phân biệt hoa thường

Quote một identifier không tự làm cho tên table hoặc column trở nên case-sensitive. Quy tắc phân biệt hoa thường của tên database/table có thể phụ thuộc hệ điều hành và `lower_case_table_names`; tên column có quy tắc riêng của MySQL. Đừng dùng việc thêm backtick hoặc dấu nháy kép để giải quyết một vấn đề khác biệt hoa thường.

## 5. Viết string literal an toàn

### 5.1. Dùng dấu nháy đơn

Để viết văn bản trong câu SQL, hãy dùng dấu nháy đơn:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE status = 'ACTIVE';
```

Quy tắc này vẫn đúng khi `ANSI_QUOTES` bật. Vì vậy, dùng dấu nháy đơn cho literal giúp câu lệnh ít phụ thuộc SQL mode hơn.

### 5.2. Escape dấu nháy đơn trong chuỗi

Một dấu nháy đơn bên trong string literal có thể được biểu diễn bằng hai dấu nháy đơn liên tiếp:

```sql
SELECT 'Customer''s order' AS description;
```

Kết quả là `Customer's order`. Cách viết này thể hiện rõ quy tắc quote SQL. Hành vi của backslash trong string literal phụ thuộc mode như `NO_BACKSLASH_ESCAPES`, vì vậy không nên xây dựng chuỗi SQL bằng cách tự nối và escape thủ công.

### 5.3. Không dùng double quote cho string literal trong code mới

Code sau dễ chạy ở môi trường mặc định nhưng hỏng khi bật `ANSI_QUOTES`:

```sql
-- Không nên dùng cho string literal
SELECT "PAID" AS payment_status;

-- Cách viết ổn định hơn
SELECT 'PAID' AS payment_status;
```

Khi chuẩn hóa codebase, tìm các literal đang dùng dấu nháy kép và chuyển sang dấu nháy đơn sau khi xác nhận chúng thật sự là giá trị văn bản, không phải identifier.

## 6. Kiểm tra SQL mode hiện tại

SQL mode là tập hợp các tùy chọn làm thay đổi cách MySQL phân tích hoặc xử lý SQL. `ANSI_QUOTES` là một thành viên trong danh sách này.

Kiểm tra ở phạm vi SESSION và GLOBAL:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Hoặc:

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

Kiểm tra riêng `ANSI_QUOTES` có đang bật trong session không:

```sql
SELECT FIND_IN_SET('ANSI_QUOTES', @@SESSION.sql_mode) > 0
       AS ansi_quotes_enabled;
```

Kết quả `1` nghĩa là bật; `0` nghĩa là không có mode này trong danh sách session. Không suy luận SQL mode của server từ cấu hình client hoặc từ một kết nối khác.

## 7. Bật ANSI_QUOTES trong một session thử nghiệm

Để thử mà không tác động các kết nối khác, có thể thay đổi SQL mode của session hiện tại. Trước tiên lưu lại giá trị cũ:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode = IF(
    FIND_IN_SET('ANSI_QUOTES', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'ANSI_QUOTES')
);
```

Đoạn lệnh thêm `ANSI_QUOTES` nếu chưa có, đồng thời giữ các mode session khác. Kiểm tra:

```sql
SELECT @@SESSION.sql_mode;
SELECT 'hello' AS string_literal;
```

Sau khi bật, có thể thử:

```sql
-- "customer_name" là identifier
SELECT "customer_name"
FROM customers;

-- "hello" được hiểu là identifier, không phải string literal
SELECT "hello" AS greeting;
```

Lệnh thứ hai sẽ chỉ chạy nếu có identifier phù hợp trong ngữ cảnh; nếu không, nó báo lỗi. Để khôi phục mode ban đầu trong session thử nghiệm:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

Biến `@saved_sql_mode` chỉ tồn tại trong connection hiện tại. Nếu đóng connection, session state và biến người dùng này kết thúc.

Không dùng `SET SESSION sql_mode = 'ANSI_QUOTES'` trong ứng dụng nếu mục tiêu chỉ là thêm mode này: câu lệnh đó thay toàn bộ danh sách mode của session và có thể vô tình loại bỏ các chế độ như `STRICT_TRANS_TABLES`.

## 8. Phạm vi GLOBAL và ảnh hưởng tới ứng dụng

`SET GLOBAL sql_mode = ...` thay đổi mặc định cho các session được tạo sau đó; các session đã mở thường giữ `@@SESSION.sql_mode` hiện tại. Vì vậy, bật `ANSI_QUOTES` ở GLOBAL không bảo đảm mọi connection pool đang chạy lập tức dùng mode mới.

Trước khi thay đổi GLOBAL hoặc cấu hình bền vững, cần:

1. Kiểm tra mode hiện tại ở cả GLOBAL và SESSION.
2. Kiểm kê ứng dụng, job, công cụ migration và client có dùng dấu nháy kép cho string literal hay không.
3. Thử trên môi trường staging với cùng driver, ORM, migration và phiên bản server.
4. Xác định cách rollout tới connection pool và xử lý session cũ.
5. Theo dõi lỗi cú pháp và `Unknown column` sau khi thay đổi.

Muốn giữ cấu hình qua restart, hãy dùng file cấu hình hoặc cơ chế persist phù hợp phiên bản MySQL và quy trình quản lý cấu hình của môi trường. Không chỉnh GLOBAL trên production chỉ để thử cú pháp của một câu lệnh.

## 9. ANSI_QUOTES trong view, routine và migration

SQL mode có thể ảnh hưởng cách một câu lệnh được phân tích tại thời điểm tạo đối tượng. MySQL lưu SQL mode liên quan khi tạo stored procedure, function, trigger và event; các đối tượng này thực thi theo mode đã được ghi nhận khi tạo. View cũng lưu mode tạo view và dùng mode đó khi xử lý định nghĩa view.

Điều này có nghĩa là thay đổi GLOBAL sau này không tự viết lại cách quote trong những đối tượng đã tồn tại. Khi chuyển môi trường hoặc chuẩn hóa SQL mode, cần xem xét cả:

- Stored procedure và function.
- Trigger và event.
- View.
- Script migration và script khởi tạo schema.
- SQL được sinh bởi ORM, query builder hoặc ứng dụng.

Nếu một routine được tạo khi không có `ANSI_QUOTES`, dấu nháy kép trong thân routine có thể đã được hiểu là string literal. Chỉ bật `ANSI_QUOTES` ở server sau đó không làm định nghĩa đã lưu tự biến thành identifier. Ngược lại, routine tạo khi mode bật có thể phụ thuộc vào cách diễn giải identifier đó. Hãy kiểm tra và tạo lại đối tượng bằng DDL đã được xác minh nếu cần chuẩn hóa.

## 10. Prepared statement và truy vấn động

Prepared statement tách giá trị dữ liệu khỏi cấu trúc câu SQL. Placeholder `?` dùng cho giá trị, không dùng để thay thế tên table, column hoặc keyword.

Ví dụ Java JDBC:

```java
String sql = "SELECT customer_id, customer_name "
           + "FROM customers WHERE status = ?";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, "ACTIVE");
    try (var result = statement.executeQuery()) {
        while (result.next()) {
            long id = result.getLong("customer_id");
            String name = result.getString("customer_name");
        }
    }
}
```

Giá trị `'ACTIVE'` được truyền qua parameter; không cần tự thêm dấu nháy đơn hoặc nháy kép.

Nếu cần chọn column hoặc table động, không thể viết `SELECT ? FROM ?` rồi mong placeholder được thay bằng identifier. Hãy ánh xạ lựa chọn từ whitelist cố định:

```java
String selectedColumn = switch (requestedSort) {
    case "name" -> "customer_name";
    case "created" -> "created_at";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String sql = "SELECT customer_id, customer_name FROM customers ORDER BY `"
           + selectedColumn + "`";
```

Ví dụ chỉ nối identifier đã được chọn từ whitelist do ứng dụng kiểm soát. Không đưa trực tiếp tên column/table do người dùng gửi lên vào SQL. Nếu phải quote identifier động, dùng hàm quote đúng theo driver/database và vẫn xác thực tên qua whitelist; quote không thay thế kiểm soát đầu vào.

## 11. Quy ước viết SQL dễ tương thích

Để giảm lỗi khi môi trường bật/tắt `ANSI_QUOTES`, nên áp dụng các quy ước:

- Dùng dấu nháy đơn cho mọi string literal.
- Dùng backtick cho identifier khi cần cú pháp quote riêng của MySQL.
- Tránh tên table/column có dấu cách, dấu gạch nối hoặc trùng từ khóa trong schema mới.
- Không giả định SQL mode ở một máy giống với môi trường khác; kiểm tra `@@SESSION.sql_mode` từ connection thực tế.
- Không thay toàn bộ `sql_mode` chỉ để thêm một mode; bảo toàn các mode hiện có.
- Kiểm tra routine, trigger, event, view và script migration khi thay đổi mode.
- Dùng prepared statement cho giá trị; whitelist cho identifier động.

Ví dụ truy vấn theo quy ước:

```sql
SELECT
    `customer_id`,
    `customer_name`
FROM `customers`
WHERE `status` = 'ACTIVE'
  AND `created_at` >= '2026-01-01';
```

Câu lệnh trên dùng backtick cho identifier và nháy đơn cho literal, do đó không phụ thuộc vào việc `ANSI_QUOTES` có bật hay không.

## 12. Checklist khi bật ANSI_QUOTES hoặc chuyển môi trường

- [ ] Đã ghi nhận `@@GLOBAL.sql_mode` và `@@SESSION.sql_mode`.
- [ ] Đã tìm các string literal đang viết bằng dấu nháy kép.
- [ ] Đã xác minh những dấu nháy kép còn lại có phải identifier hay không.
- [ ] Đã đổi literal sang dấu nháy đơn trong code cần tương thích.
- [ ] Đã kiểm tra tên identifier, từ khóa và cách quote trong DDL.
- [ ] Đã rà soát view, stored procedure, function, trigger và event.
- [ ] Đã thử migration, ORM và query được sinh trên staging.
- [ ] Đã xác định cách cập nhật connection pool và session cũ.
- [ ] Đã có kế hoạch rollback SQL mode nếu ứng dụng gặp lỗi.

## 13. Kết luận

`ANSI_QUOTES` thay đổi ý nghĩa của dấu nháy kép trong MySQL: khi mode tắt, dấu nháy kép biểu diễn string literal; khi mode bật, nó quote identifier. Dấu nháy đơn tiếp tục dùng cho string literal và backtick tiếp tục quote identifier theo cú pháp MySQL.

Hãy dùng dấu nháy đơn cho văn bản, quote identifier một cách nhất quán, kiểm tra SQL mode từ đúng session và thử mọi thay đổi trên môi trường tương đương trước khi triển khai. Quy ước này giúp câu SQL dễ đọc, giảm lỗi `Unknown column` và tránh phụ thuộc ngoài ý muốn vào cấu hình SQL mode.
