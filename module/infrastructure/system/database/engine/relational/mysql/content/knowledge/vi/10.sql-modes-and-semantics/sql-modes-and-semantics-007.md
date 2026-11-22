# NO_BACKSLASH_ESCAPES, escape và xử lý literal an toàn

Một ứng dụng lưu đường dẫn `C:\temp\new`, nội dung ghi chú `O'Reilly` và tên sản phẩm có ký tự `%`. Khi ghép các giá trị này trực tiếp vào câu SQL, một dấu nháy hoặc dấu gạch chéo ngược có thể làm câu lệnh sai cú pháp, thay đổi dữ liệu hoặc mở ra lỗ hổng SQL injection. Vấn đề còn phức tạp hơn khi các session MySQL dùng SQL mode khác nhau.

`NO_BACKSLASH_ESCAPES` là một SQL mode thay đổi cách MySQL diễn giải dấu gạch chéo ngược (`\`) trong string literal. Hiểu mode này giúp viết câu SQL nhất quán, nhưng nguyên tắc an toàn quan trọng nhất vẫn là truyền giá trị bằng prepared statement thay vì tự tạo literal từ dữ liệu đầu vào. Khi cần tạo SQL động, phải phân biệt rõ giá trị, tên bảng/cột và cú pháp điều khiển truy vấn.

## 1. SQL mode ảnh hưởng đến cách MySQL phân tích câu lệnh

SQL mode là tập các tùy chọn làm thay đổi cách MySQL phân tích, kiểm tra và thực thi SQL. Một số mode ảnh hưởng đến tính nghiêm ngặt của dữ liệu; một số thay đổi cú pháp hoặc cách diễn giải literal.

Xem SQL mode của kết nối hiện tại và mặc định toàn server:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.sql_mode AS global_sql_mode;
```

`@@SESSION.sql_mode` áp dụng cho connection hiện tại. `@@GLOBAL.sql_mode` là giá trị mặc định được dùng khi tạo connection mới; thay đổi GLOBAL không tự động thay đổi các session đã mở.

Kiểm tra riêng một mode:

```sql
SELECT
    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0
        AS no_backslash_escapes_enabled;
```

Nếu kết quả là `1`, mode đang bật trong session. Nếu là `0`, mode không có trong danh sách hiện tại.

## 2. Quy tắc string literal mặc định

String literal trong MySQL thường được đặt trong dấu nháy đơn (`'...'`). Khi `NO_BACKSLASH_ESCAPES` chưa bật, dấu gạch chéo ngược có thể mở đầu một escape sequence.

Một số escape sequence thường gặp:

| Cách viết trong SQL literal | Ký tự được tạo trong chế độ mặc định |
|---|---|
| `\\` | Một dấu gạch chéo ngược (`\`) |
| `\'` | Một dấu nháy đơn (`'`) |
| `\"` | Một dấu nháy kép (`"`) |
| `\n` | Ký tự xuống dòng LF |
| `\r` | Ký tự carriage return |
| `\t` | Ký tự tab |
| `\0` | Ký tự NUL |
| `\b` | Ký tự backspace |
| `\Z` | Ký tự Ctrl-Z |

Ví dụ:

```sql
SELECT
    'A\nB' AS text_value,
    HEX('A\nB') AS bytes_value;
```

Trong chế độ mặc định, `\n` được diễn giải thành một byte xuống dòng `0A`; kết quả hex tương ứng có dạng `410A42`.

Với các chuỗi không phải escape sequence được nhận diện, MySQL có quy tắc riêng: dấu `\` có thể bị bỏ qua khi phân tích literal. Do đó, không nên tự suy đoán rằng mọi cặp `\x` đều được lưu thành hai ký tự.

## 3. NO_BACKSLASH_ESCAPES thay đổi điều gì?

Khi `NO_BACKSLASH_ESCAPES` được bật, dấu `\` trở thành ký tự bình thường trong string literal. Nó không còn dùng để escape dấu nháy hoặc tạo các escape sequence như `\n`, `\t` và `\\`.

Với cùng ví dụ:

```sql
SELECT
    'A\nB' AS text_value,
    HEX('A\nB') AS bytes_value;
```

Trong chế độ này, chuỗi chứa bốn ký tự `A`, `\`, `n`, `B`; kết quả hex có dạng `415C6E42`. Dấu gạch chéo ngược được giữ nguyên.

| Nội dung literal | Chế độ mặc định | `NO_BACKSLASH_ESCAPES` |
|---|---|---|
| `'A\nB'` | `A`, xuống dòng, `B` | `A`, `\`, `n`, `B` |
| `'C:\\temp'` | Một dấu `\` trước `temp` | Hai dấu `\` trước `temp` |
| `'It\'s'` | Có thể biểu diễn dấu nháy đơn bên trong | Không escape dấu nháy; câu lệnh bị kết thúc tại dấu nháy đó |
| `'It''s'` | Một dấu nháy đơn bên trong | Một dấu nháy đơn bên trong |

Điểm quan trọng: `NO_BACKSLASH_ESCAPES` không làm thay đổi quy tắc nhân đôi dấu nháy đơn. Viết `'It''s'` là cách biểu diễn string literal chứa `It's` ổn định giữa hai chế độ.

## 4. Đặt và khôi phục SQL mode trong session

Để thử nghiệm, chỉ thay đổi session hiện tại. Ví dụ dưới đây lưu mode cũ, thêm `NO_BACKSLASH_ESCAPES` nếu chưa có, kiểm tra rồi khôi phục:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode = IF(
    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'NO_BACKSLASH_ESCAPES')
);

SELECT @@SESSION.sql_mode;
SELECT HEX('A\nB') AS bytes_with_no_backslash_escapes;

SET SESSION sql_mode = @saved_sql_mode;
```

Trong ứng dụng thật, không nên thay SQL mode tùy tiện giữa các câu lệnh. Nếu một connection được mượn từ pool, thay đổi session có thể còn tồn tại khi connection được trả về pool. Hãy cấu hình mode lúc khởi tạo connection hoặc bảo đảm khôi phục trạng thái trước khi trả connection.

### 4.1. SESSION và GLOBAL khác nhau

- `SET SESSION sql_mode = ...` chỉ tác động connection hiện tại.
- `SET GLOBAL sql_mode = ...` thay đổi giá trị mặc định cho các connection mở sau đó; cần quyền quản trị phù hợp.
- Cấu hình lúc khởi động server giúp đặt chính sách mặc định ổn định qua restart.

Không thay toàn bộ `sql_mode` chỉ để bật một mode nếu không chủ ý thay đổi các mode khác. Gán một danh sách mới có thể vô tình tắt `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY` hoặc các quy tắc hiện có.

### 4.2. Stored program và SQL mode lúc tạo

MySQL lưu SQL mode có hiệu lực khi tạo stored procedure, function, trigger hoặc event. Khi các đối tượng này chạy, chúng sử dụng mode được lưu tại thời điểm tạo theo quy tắc của MySQL. Vì vậy, đổi SQL mode của session gọi procedure không nhất thiết thay đổi cách literal bên trong procedure đã được phân tích và lưu.

Khi thay đổi chính sách SQL mode, hãy kiểm tra các stored program liên quan. Nếu cần áp dụng mode mới, phải có kế hoạch tạo lại đối tượng trong môi trường phù hợp và xác minh hành vi sau triển khai.

## 5. Escape dấu nháy đơn an toàn

### 5.1. Nhân đôi dấu nháy đơn

Trong SQL literal, dấu nháy đơn bên trong chuỗi được biểu diễn bằng hai dấu nháy đơn liên tiếp:

```sql
SELECT 'O''Reilly' AS publisher_name;
```

Cách viết này hoạt động cả khi `NO_BACKSLASH_ESCAPES` bật hoặc tắt. Nếu tự viết literal cố định trong file SQL, đây là cách nên dùng.

### 5.2. Không dùng backslash để quote dấu nháy khi mode có thể thay đổi

Ví dụ sau phụ thuộc SQL mode:

```sql
SELECT 'O\'Reilly';
```

Trong chế độ mặc định, `\'` escape dấu nháy đơn. Khi `NO_BACKSLASH_ESCAPES` bật, backslash không escape dấu nháy, nên câu lệnh có thể bị phân tích sai hoặc phát sinh lỗi cú pháp.

Nếu một script phải chạy trên nhiều môi trường có SQL mode khác nhau, dùng dạng nhân đôi dấu nháy:

```sql
SELECT 'O''Reilly';
```

## 6. Escape dấu gạch chéo ngược và đường dẫn

Giả sử ứng dụng cần lưu đường dẫn Windows `C:\temp\new`.

Trong chế độ mặc định, để lưu một dấu `\` trước mỗi thành phần, literal phải nhân đôi dấu gạch chéo ngược:

```sql
INSERT INTO file_jobs (file_path)
VALUES ('C:\\temp\\new');
```

Khi `NO_BACKSLASH_ESCAPES` bật, backslash là ký tự thường, nên literal tương ứng có thể viết:

```sql
INSERT INTO file_jobs (file_path)
VALUES ('C:\temp\new');
```

Hai câu SQL này không thể hoán đổi tùy ý giữa hai SQL mode. Nếu code sinh SQL bằng cách nối chuỗi, thay đổi mode có thể làm số lượng dấu gạch chéo ngược được lưu khác dự kiến.

Đối với dữ liệu đến từ người dùng, không tự xây dựng literal đường dẫn. Hãy dùng parameter binding để truyền nguyên giá trị, bất kể giá trị có backslash, dấu nháy, ký tự xuống dòng hay Unicode.

## 7. LIKE pattern và ký tự wildcard

Trong `LIKE`, hai ký tự có ý nghĩa đặc biệt:

- `%` khớp với không hoặc nhiều ký tự.
- `_` khớp với đúng một ký tự.

Nếu cần tìm dấu `%` hoặc `_` như ký tự thông thường, hãy dùng mệnh đề `ESCAPE` với một ký tự quy ước rõ ràng. Cách này tránh phụ thuộc vào việc backslash có đang được dùng làm escape character hay không.

Ví dụ tìm chuỗi có ký tự `%`:

```sql
SELECT id, product_name
FROM products
WHERE product_name LIKE '%!%%' ESCAPE '!';
```

Trong pattern trên, `!%` có nghĩa là ký tự `%` theo nghĩa đen; hai dấu `%` ngoài cùng vẫn là wildcard.

Ví dụ tìm dấu gạch dưới:

```sql
SELECT id, product_name
FROM products
WHERE product_name LIKE '%!_%' ESCAPE '!';
```

Khi tạo pattern từ input người dùng, cần escape cả ký tự escape `!` trước, rồi mới escape `%` và `_` theo quy tắc của ứng dụng. Ví dụ nếu `!` là escape character, thay `!` trong input bằng `!!`, `%` thành `!%` và `_` thành `!_`; sau đó bind toàn bộ pattern bằng prepared statement.

## 8. Literal, identifier và cú pháp là ba thứ khác nhau

Một câu SQL có thể chứa:

- **Value/literal:** tên khách hàng, email, giá tiền hoặc nội dung ghi chú.
- **Identifier:** tên database, table, column hoặc alias.
- **SQL syntax:** từ khóa, toán tử, hướng sắp xếp, tên hàm và cấu trúc truy vấn.

Prepared statement parameter chỉ đại diện cho value. Không thể dùng `?` để thay thế tên bảng, tên cột hoặc từ khóa SQL.

### 8.1. String literal dùng dấu nháy đơn

```sql
SELECT *
FROM customers
WHERE email = 'alice@example.com';
```

Dấu nháy đơn dùng cho chuỗi. Khi viết literal cố định, nhân đôi dấu nháy đơn bên trong thay vì phụ thuộc vào backslash.

### 8.2. Identifier dùng backtick

```sql
SELECT `order`, `customer name`
FROM `sales data`;
```

Backtick dùng để quote identifier. Nếu tên identifier có backtick bên trong, ký tự backtick được nhân đôi trong identifier quoted. Không dùng string literal để thay thế identifier.

### 8.3. ANSI_QUOTES là mode khác

Khi bật `ANSI_QUOTES`, dấu nháy kép (`"`) được hiểu là dấu quote identifier thay vì string literal. Vì vậy:

```sql
SELECT "status" FROM orders;
```

có thể được hiểu là tham chiếu identifier `status` trong chế độ `ANSI_QUOTES`; trong chế độ thông thường, nó là string literal chứa `status`.

Để tránh phụ thuộc mode, dùng dấu nháy đơn cho string và backtick cho identifier. Không dùng dấu nháy kép như một cách viết string SQL.

## 9. Prepared statement là cách truyền value an toàn

Khi ứng dụng có dữ liệu động, hãy gửi câu SQL với placeholder và truyền value riêng qua driver. Driver xử lý giao thức và kiểu dữ liệu; ứng dụng không cần tự escape dấu nháy hay backslash để ghép thành SQL.

### 9.1. Ví dụ Java JDBC

```java
String sql = "INSERT INTO customers (full_name, note) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, fullName);
    statement.setString(2, note);
    statement.executeUpdate();
}
```

Nếu `fullName` là `O'Reilly` hoặc `note` chứa `C:\temp\new`, driver truyền giá trị như dữ liệu. Nội dung không thể đóng dấu nháy để biến phần còn lại thành SQL syntax.

### 9.2. Ví dụ truy vấn có điều kiện

```java
String sql = "SELECT id, full_name FROM customers WHERE email = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, emailInput);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            long id = result.getLong("id");
            String name = result.getString("full_name");
        }
    }
}
```

Không nối `emailInput` vào chuỗi SQL. Cách bind tham số cũng tránh lỗi quote khi giá trị có Unicode, dấu nháy, backslash hoặc xuống dòng.

### 9.3. Placeholder không thay thế được identifier

Đoạn sau không hoạt động như mong đợi:

```java
String sql = "SELECT * FROM ? WHERE id = ?";
```

Placeholder đầu tiên không thể đại diện cho tên bảng. Nếu cần chọn bảng hoặc cột theo lựa chọn người dùng, dùng allowlist ánh xạ từ lựa chọn hợp lệ sang identifier cố định:

```java
Map<String, String> allowedTables = Map.of(
    "active", "active_customers",
    "archived", "archived_customers"
);

String table = allowedTables.get(requestedView);
if (table == null) {
    throw new IllegalArgumentException("Unsupported view");
}

String sql = "SELECT id, full_name FROM `" + table + "` WHERE id = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    // Thực thi truy vấn...
}
```

Tên bảng trong ví dụ chỉ đến từ allowlist do chương trình kiểm soát; dữ liệu đầu vào không được nối trực tiếp thành identifier. Với `ORDER BY`, hướng `ASC`/`DESC` hoặc tên cột động, cũng dùng allowlist tương tự.

## 10. API escape của driver và giới hạn của tự escape

Một số driver cung cấp hàm quote/escape để tạo literal. Nếu buộc phải tạo SQL text, chỉ dùng API được thiết kế cho đúng connector và connection đang dùng; charset kết nối và SQL mode phải nhất quán với cách API escape.

Không dùng các hàm thay thế chuỗi tự viết như:

```java
input.replace("'", "\\'");
```

Đoạn code này phụ thuộc vào backslash escape, không xử lý đầy đủ charset, byte NUL, các escape sequence và khác biệt SQL mode. Nó cũng không bảo vệ identifier hay cú pháp động.

Prepared statement parameter binding nên là lựa chọn mặc định. API escape chỉ dành cho trường hợp đặc biệt không thể bind tham số, sau khi đã đọc đúng tài liệu driver và kiểm tra cấu hình connection. Không tự triển khai một hàm escape SQL dùng chung cho mọi hệ quản trị.

## 11. SQL mode trong connection pool và stored program

SQL mode là trạng thái session. Trong ứng dụng dùng connection pool, một connection có thể được dùng lại bởi nhiều request. Nếu request A thay đổi `sql_mode` rồi không khôi phục, request B có thể nhận connection với cách phân tích literal khác.

Các biện pháp nên áp dụng:

- Cấu hình SQL mode thống nhất lúc khởi tạo connection.
- Tránh thay đổi SQL mode giữa luồng xử lý nghiệp vụ.
- Nếu phải thay đổi, lưu giá trị cũ và khôi phục trong `finally` hoặc cơ chế cleanup tương đương.
- Khi trả connection về pool, reset session state theo khả năng của pool/driver.
- Kiểm tra SQL mode thực tế trên connection đã mượn, không chỉ kiểm tra `GLOBAL`.
- Kiểm tra mode được lưu cùng stored procedure, function, trigger và event khi deploy thay đổi.

Không dựa vào `@@GLOBAL.sql_mode` để kết luận session hiện tại đang dùng cùng mode. Hai giá trị có thể khác nhau.

## 12. Kiểm thử hành vi literal ở cả hai mode

Có thể dùng một session thử nghiệm và `HEX()` để quan sát byte thực tế:

```sql
-- Lưu lại SQL mode ban đầu.
SET @old_mode = @@SESSION.sql_mode;

-- Bật NO_BACKSLASH_ESCAPES mà giữ các mode hiện có.
SET SESSION sql_mode = IF(
    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'NO_BACKSLASH_ESCAPES')
);

SELECT HEX('A\nB') AS no_backslash_bytes;
SELECT 'O''Reilly' AS quoted_value;

-- Khôi phục mode ban đầu.
SET SESSION sql_mode = @old_mode;

SELECT HEX('A\nB') AS default_mode_bytes;
```

Khi mode bật, byte của `\n` được giữ nguyên thành `5C6E`. Sau khi khôi phục mode mặc định, cùng literal được phân tích thành ký tự xuống dòng (`0A`). Hãy thực hiện trong session thử nghiệm; nếu client hoặc công cụ có cơ chế escape riêng, kiểm tra nội dung SQL thực sự được gửi tới server.

Một bộ kiểm thử nên bao gồm:

- Dữ liệu có dấu nháy đơn: `O'Reilly`.
- Dữ liệu có backslash: `C:\temp\new`.
- Dữ liệu có `%` và `_` khi tìm bằng LIKE.
- Chuỗi có Unicode và ký tự xuống dòng.
- Dữ liệu rỗng và SQL `NULL`.
- Prepared statement với tất cả dữ liệu trên ở cả hai SQL mode.

## 13. Các lỗi và rủi ro thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Câu SQL lỗi cú pháp sau khi bật `NO_BACKSLASH_ESCAPES` | Literal cũ dùng `\'` để quote dấu nháy | Dùng `''` hoặc parameter binding |
| Đường dẫn lưu sai số lượng backslash | Code sinh literal giả định một SQL mode cố định | Bind parameter; nếu là script tĩnh, viết literal theo mode đã xác định |
| `\n` lưu thành xuống dòng ngoài dự kiến | Session đang dùng backslash escape mặc định | Kiểm tra `@@SESSION.sql_mode`; dùng parameter binding hoặc chủ động chọn literal |
| Ký tự `%`/`_` tìm kiếm sai | Nhầm wildcard với ký tự theo nghĩa đen | Dùng `LIKE ... ESCAPE '!'` và escape input theo quy tắc ứng dụng |
| Query động bị SQL injection | Nối input vào SQL text hoặc identifier | Bind value; allowlist identifier và cú pháp động |
| Request khác nhận SQL mode bất ngờ | Connection pool giữ trạng thái session từ request trước | Khởi tạo/reset session state khi mượn/trả connection |
| Chuỗi dùng dấu nháy kép đổi nghĩa | `ANSI_QUOTES` bật | Dùng dấu nháy đơn cho string và backtick cho identifier |

## 14. Quy trình xử lý khi chuyển sang NO_BACKSLASH_ESCAPES

Khi muốn bật mode này cho một ứng dụng hiện hữu, không thay đổi trực tiếp trên production trước khi kiểm kê literal.

1. **Ghi nhận hiện trạng:** thu thập `@@GLOBAL.sql_mode` và `@@SESSION.sql_mode` từ các loại connection của ứng dụng.
2. **Tìm cách tạo SQL:** tìm code nối chuỗi, hàm escape thủ công, script migration, stored program và query builder tự viết.
3. **Kiểm kê literal phụ thuộc backslash:** tập trung vào `\'`, `\\`, `\n`, `\r`, `\t`, đường dẫn, regex và LIKE pattern.
4. **Chuyển giá trị động sang parameter binding:** loại bỏ việc tự quote input; dùng allowlist cho identifier và cú pháp động.
5. **Chuẩn hóa literal tĩnh:** dùng nhân đôi dấu nháy đơn; xem xét lại backslash theo mode mục tiêu.
6. **Kiểm thử hai mode:** chạy bộ test với mode cũ và mode mới trên cùng dữ liệu; so sánh byte bằng `HEX()` và kết quả nghiệp vụ.
7. **Kiểm tra stored program:** xác nhận SQL mode được lưu lúc tạo và tạo lại đối tượng nếu cần.
8. **Triển khai theo nhóm connection:** cập nhật cấu hình, giám sát lỗi cú pháp, dữ liệu ghi sai và connection pool; có phương án quay lại mode trước.

Việc bật `NO_BACKSLASH_ESCAPES` không tự làm ứng dụng an toàn trước SQL injection. Nếu ứng dụng vẫn nối dữ liệu người dùng vào SQL, lỗ hổng vẫn tồn tại; mode chỉ làm thay đổi một phần quy tắc phân tích literal.

## 15. Checklist viết SQL literal an toàn

- Session đang dùng `NO_BACKSLASH_ESCAPES` hay không?
- Câu lệnh có phụ thuộc vào backslash để escape dấu nháy hoặc tạo newline không?
- String literal có dùng dấu nháy đơn và nhân đôi dấu nháy đơn bên trong không?
- Có đang nhầm string literal với identifier hoặc cú pháp SQL không?
- Giá trị đến từ người dùng có được bind bằng prepared statement không?
- Identifier động có được lấy từ allowlist và quote đúng cách không?
- Pattern LIKE có dùng `ESCAPE` rõ ràng cho `%` và `_` theo nghĩa đen không?
- Connection pool có reset SQL mode và session state không?
- Stored program có SQL mode được lưu từ thời điểm tạo khác với cấu hình hiện tại không?
- Đã kiểm thử byte thực tế bằng `HEX()` ở các mode liên quan chưa?

## Kết luận

`NO_BACKSLASH_ESCAPES` làm cho backslash trở thành ký tự bình thường trong string literal; các escape sequence như `\n` và `\'` không còn hoạt động theo cách mặc định. Nhân đôi dấu nháy đơn (`''`) là cách quote chuỗi ổn định giữa hai mode. Với dữ liệu động, hãy dùng prepared statement để truyền value riêng; với identifier và cú pháp động, dùng allowlist. Kiểm tra SQL mode ở đúng session, quản lý trạng thái connection pool và thử nghiệm bằng `HEX()` trước khi thay đổi cấu hình để tránh lỗi dữ liệu và lỗi phân tích SQL.
