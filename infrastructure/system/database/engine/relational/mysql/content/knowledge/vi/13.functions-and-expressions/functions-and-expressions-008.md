# REGEXP_LIKE, REGEXP_SUBSTR, REGEXP_REPLACE theo phiên bản

MySQL cung cấp các hàm regular expression (regex) để kiểm tra chuỗi theo mẫu, trích xuất phần khớp và thay thế nội dung khớp. Ba hàm quan trọng là **REGEXP_LIKE()**, **REGEXP_SUBSTR()** và **REGEXP_REPLACE()**. Chúng giúp xử lý mã định danh, chuẩn hóa dữ liệu nhập, tìm mẫu trong văn bản và trích xuất thành phần từ chuỗi.

Điểm quan trọng là các hàm regex phụ thuộc phiên bản MySQL. MySQL 5.7 chủ yếu cung cấp toán tử REGEXP/RLIKE với bộ máy regex cũ; MySQL 8.0 chuyển sang ICU và bổ sung bộ hàm regex. Cú pháp pattern, Unicode, cách điều khiển phân biệt hoa/thường và hành vi của một số pattern có thể khác giữa các phiên bản. Không nên lấy một regex chạy được ở Java, MySQL 5.7 hoặc MariaDB rồi mặc định nó có cùng kết quả trên MySQL 8.0.

Trong module **DATABASE_MYSQL**, các hàm này là công cụ xử lý biểu thức và dữ liệu chuỗi. Chúng cần được kết hợp với kiểu dữ liệu, character set, collation, index, kiểm tra dữ liệu đầu vào và truy vấn có tham số. Bài học tập trung vào khác biệt phiên bản, chữ ký hàm, cách viết pattern an toàn, giới hạn hiệu năng và quy trình kiểm thử trước khi triển khai.

## 1. Khác biệt phiên bản: MySQL 5.7 và MySQL 8.0

### 1.1. MySQL 5.7: REGEXP và RLIKE

Trong MySQL 5.7, cách phổ biến để kiểm tra chuỗi theo regex là toán tử:

```sql
SELECT *
FROM users
WHERE username REGEXP '^[a-z][a-z0-9_]{2,19}$';
```

`REGEXP` và `RLIKE` là hai cách viết tương đương cho phép kiểm tra mẫu. MySQL 5.7 sử dụng bộ máy regex cũ dựa trên Henry Spencer, xử lý theo byte và không an toàn đầy đủ với chuỗi đa byte. Cách xử lý Unicode vì thế khác đáng kể so với ICU được dùng trong MySQL 8.0.

MySQL 5.7 không cung cấp bộ ba hàm `REGEXP_LIKE()`, `REGEXP_SUBSTR()` và `REGEXP_REPLACE()` như MySQL 8.0. Nếu ứng dụng cần trích xuất hoặc thay thế theo pattern trên 5.7, thường phải dùng các hàm chuỗi khác, xử lý ở ứng dụng hoặc nâng cấp server.

### 1.2. MySQL 8.0: ICU và các hàm regex

Từ dòng MySQL 8.0.4, MySQL thay bộ máy regex cũ bằng thư viện ICU (International Components for Unicode) và cung cấp các hàm regex chuyên biệt. MySQL 8.0.4 là bản Developer Milestone; dòng MySQL 8.0 GA bắt đầu từ 8.0.11.

| Khả năng | MySQL 5.7 | MySQL 8.0 GA |
|---|---|---|
| Kiểm tra regex | Toán tử REGEXP/RLIKE | REGEXP_LIKE(), REGEXP/RLIKE |
| Trích xuất phần khớp | Không có REGEXP_SUBSTR() | REGEXP_SUBSTR() |
| Thay thế theo pattern | Không có REGEXP_REPLACE() | REGEXP_REPLACE() |
| Bộ máy regex | Henry Spencer | ICU |
| Unicode và ký tự đa byte | Hạn chế, không tương đương ICU | Hỗ trợ Unicode theo ICU |
| Cú pháp pattern | Quy tắc của bộ máy cũ | Cú pháp ICU; một số pattern cũ cần điều chỉnh |

MySQL 8.0 không chỉ bổ sung tên hàm. Việc thay bộ máy có thể làm một pattern cũ trả kết quả khác hoặc phát lỗi nếu cú pháp không còn phù hợp. Khi nâng cấp, cần chạy bộ kiểm thử regex trên đúng phiên bản đích.

### 1.3. Xác định phiên bản trước khi viết truy vấn

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution;
```

Kiểm tra server thực tế, không chỉ kiểm tra phiên bản connector hoặc phiên bản thư viện trong ứng dụng. Với dịch vụ tương thích MySQL, hãy xác minh tài liệu của chính sản phẩm đó; MariaDB có lịch sử và bộ máy regex riêng, không thể mặc định mọi hàm hoặc pattern của MySQL đều tương thích.

## 2. Ba hàm regex và mục đích sử dụng

| Hàm | Mục đích | Kết quả |
|---|---|---|
| REGEXP_LIKE(expr, pat[, match_type]) | Kiểm tra expr có khớp pattern không | 1, 0 hoặc NULL |
| REGEXP_SUBSTR(expr, pat[, pos[, occurrence[, match_type]]]) | Trả về phần chuỗi khớp pattern | Chuỗi khớp hoặc NULL |
| REGEXP_REPLACE(expr, pat, repl[, pos[, occurrence[, match_type]]]) | Thay phần khớp bằng chuỗi thay thế | Chuỗi đã xử lý |

Trong các hàm này:

- `expr` là chuỗi cần kiểm tra hoặc xử lý.
- `pat` là biểu thức chính quy.
- `repl` là chuỗi thay thế, dùng với `REGEXP_REPLACE()`.
- `pos` là vị trí bắt đầu tìm, tính từ 1.
- `occurrence` là lần khớp cần lấy hoặc thay.
- `match_type` là chuỗi cờ điều khiển cách khớp.

Các đối số tùy chọn có giá trị mặc định. Với `REGEXP_SUBSTR()`, mặc định bắt đầu từ vị trí 1 và lấy lần khớp đầu tiên. Với `REGEXP_REPLACE()`, mặc định bắt đầu từ vị trí 1 và thay tất cả lần khớp (occurrence = 0).

Nếu đối số bắt buộc hoặc tùy chọn có giá trị NULL, kết quả thường là NULL. Pattern sai cú pháp có thể khiến câu lệnh phát lỗi regex thay vì trả 0.

## 3. REGEXP_LIKE(): kiểm tra chuỗi theo mẫu

`REGEXP_LIKE(expr, pat[, match_type])` trả về:

- `1` nếu chuỗi khớp pattern.
- `0` nếu không khớp.
- `NULL` nếu một đối số cần thiết là NULL.

Ví dụ kiểm tra mã sản phẩm gồm hai chữ in hoa và sáu chữ số:

```sql
SELECT
    REGEXP_LIKE('AB123456', '^[A-Z]{2}[0-9]{6}$', 'c')
        AS valid_product_code,
    REGEXP_LIKE('Ab123456', '^[A-Z]{2}[0-9]{6}$', 'c')
        AS invalid_product_code;
```

Kết quả đầu tiên là 1, kết quả thứ hai là 0 do cờ `c` yêu cầu phân biệt hoa/thường.

### 3.1. Anchors và lượng từ

Các ký hiệu regex cơ bản thường dùng:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `^` | Đầu chuỗi (hoặc đầu dòng khi bật multiline) | `^ABC` |
| `$` | Cuối chuỗi (hoặc cuối dòng khi bật multiline) | `XYZ$` |
| `.` | Một ký tự, trừ line terminator theo chế độ mặc định | `A.C` |
| `*` | 0 hoặc nhiều lần | `ab*` |
| `+` | 1 hoặc nhiều lần | `[0-9]+` |
| `?` | 0 hoặc 1 lần | `colou?r` |
| `{m,n}` | Từ m đến n lần | `[0-9]{2,4}` |
| `[abc]` | Một ký tự thuộc tập | `[A-F]` |
| `[^abc]` | Một ký tự ngoài tập | `[^0-9]` |
| `( ... )` | Nhóm bắt giữ (capturing group) | `([A-Z]{2})` |

Toán tử lựa chọn nhánh trong ICU là `|`. Ví dụ, pattern `cat|dog` khớp chuỗi `cat` hoặc `dog`.

Ví dụ kiểm tra tên người dùng chỉ gồm chữ cái ASCII, chữ số và dấu gạch dưới, độ dài từ 3 đến 20:

```sql
SELECT REGEXP_LIKE(
    'student_2026',
    '^[A-Za-z0-9_]{3,20}$',
    'c'
) AS valid_username;
```

Dấu `^` và `$` rất quan trọng. Nếu bỏ chúng, pattern có thể chỉ cần tìm thấy một đoạn con khớp. Ví dụ `[0-9]+` sẽ khớp chuỗi `order-123-finished`, dù toàn bộ chuỗi không phải một số.

### 3.2. Kiểm tra NULL rõ ràng

Do hàm trả NULL khi đầu vào NULL, điều kiện WHERE với kết quả NULL không được xem là TRUE:

```sql
SELECT user_id, phone
FROM users
WHERE REGEXP_LIKE(phone, '^[0-9]{10}$');
```

Các hàng có `phone IS NULL` không xuất hiện. Nếu cần phân loại cả dữ liệu thiếu:

```sql
SELECT
    user_id,
    CASE
        WHEN phone IS NULL THEN 'MISSING'
        WHEN REGEXP_LIKE(phone, '^[0-9]{10}$') THEN 'VALID'
        ELSE 'INVALID'
    END AS phone_status
FROM users;
```

## 4. match_type: điều khiển cách khớp

`match_type` có thể chứa một hoặc nhiều ký tự cờ:

| Cờ | Tác dụng |
|---|---|
| `c` | Khớp phân biệt hoa/thường |
| `i` | Khớp không phân biệt hoa/thường |
| `m` | Multiline: `^` và `$` xử lý ranh giới dòng |
| `n` | Dấu chấm `.` cũng khớp line terminator |
| `u` | Chỉ nhận diện line ending kiểu Unix khi áp dụng quy tắc dòng |

Ví dụ không phân biệt hoa/thường:

```sql
SELECT REGEXP_LIKE('MySQL', '^mysql$', 'i') AS matched;
```

Ép phân biệt hoa/thường:

```sql
SELECT REGEXP_LIKE('MySQL', '^mysql$', 'c') AS matched;
```

Nếu cả `c` và `i` xuất hiện trong cùng `match_type`, cờ xuất hiện sau cùng quyết định chế độ phân biệt hoa/thường.

Mặc định, tính phân biệt hoa/thường còn chịu ảnh hưởng của collation áp dụng cho các đối số chuỗi. Nếu kết quả cần ổn định và dễ đọc, hãy chỉ định `c` hoặc `i` tường minh thay vì dựa vào collation ngầm định.

### 4.1. Multiline và dấu chấm

Mặc định, `^` và `$` áp dụng cho đầu/cuối chuỗi. Cờ `m` làm chúng nhận diện ranh giới từng dòng. Cờ `n` cho phép dấu chấm khớp cả line terminator.

Trong MySQL, `||` là toán tử logic OR ở chế độ SQL mặc định, không phải phép nối chuỗi. Dùng `CONCAT()` để ghép các dòng:

```sql
SELECT
    REGEXP_LIKE(
        CONCAT('first line', CHAR(10), 'second line'),
        '^second',
        'm'
    ) AS multiline_match,
    REGEXP_LIKE(
        CONCAT('first line', CHAR(10), 'second line'),
        'line.second',
        'n'
    ) AS dot_matches_newline;
```

Cờ `u` liên quan đến cách xử lý line ending kiểu Unix. Chỉ thêm cờ khi dữ liệu nhiều dòng có yêu cầu cụ thể; với văn bản thông thường, pattern không cần các cờ này.

## 5. REGEXP_SUBSTR(): trích xuất phần khớp

`REGEXP_SUBSTR()` trả về đoạn con khớp pattern. Nếu không tìm thấy, hàm trả NULL.

Ví dụ lấy mã số thứ hai trong chuỗi:

```sql
SELECT REGEXP_SUBSTR(
    'order-2026-00125',
    '[0-9]+',
    1,
    2
) AS extracted_value;
```

Lần khớp thứ nhất là `2026`; lần thứ hai là `00125`. Vì vậy, giá trị trả về là `00125`.

Các đối số vị trí và lần xuất hiện:

- `pos = 1` bắt đầu từ ký tự đầu tiên.
- `pos = 5` bắt đầu tìm từ ký tự thứ năm.
- `occurrence = 1` lấy lần khớp đầu tiên.
- `occurrence = 2` lấy lần khớp thứ hai.

Ví dụ lấy phần mã sau tiền tố:

```sql
SELECT REGEXP_SUBSTR(
    'INV-2026-000123',
    '[0-9]+',
    1,
    2
) AS invoice_sequence;
```

### 5.1. REGEXP_SUBSTR trả về toàn bộ phần khớp

Một điểm dễ nhầm: `REGEXP_SUBSTR()` trả về toàn bộ đoạn khớp với pattern, không có tham số riêng để yêu cầu trả về một capturing group như một số API regex ở ngôn ngữ khác.

Ví dụ pattern có nhóm:

```sql
SELECT REGEXP_SUBSTR(
    'user@example.com',
    '^[^@]+@([^@]+)$'
) AS matched_text;
```

Kết quả là toàn bộ `user@example.com`, không chỉ `example.com`.

Nếu cần lấy nhóm con, có thể dùng `REGEXP_REPLACE()` để thay phần khớp toàn bộ bằng backreference của nhóm, hoặc dùng các hàm chuỗi chuyên biệt khi cấu trúc dữ liệu đơn giản.

## 6. REGEXP_REPLACE(): thay thế phần khớp

`REGEXP_REPLACE(expr, pat, repl[, pos[, occurrence[, match_type]]])` thay phần khớp pattern bằng chuỗi thay thế.

Ví dụ loại bỏ dấu phân cách khỏi số điện thoại:

```sql
SELECT REGEXP_REPLACE(
    '+84 (912) 345-678',
    '[^0-9]',
    ''
) AS normalized_phone;
```

Kết quả là chuỗi chỉ còn chữ số. Hàm này không tự xác nhận số điện thoại hợp lệ; nó chỉ thực hiện thay thế theo pattern.

### 6.1. Thay mọi lần khớp hoặc một lần cụ thể

Mặc định, `occurrence = 0` thay tất cả lần khớp:

```sql
SELECT REGEXP_REPLACE(
    'A12-B34-C56',
    '[0-9]+',
    '#'
) AS replace_all;
```

Kết quả: `A#-B#-C#`.

Nếu chỉ muốn thay lần khớp thứ hai:

```sql
SELECT REGEXP_REPLACE(
    'A12-B34-C56',
    '[0-9]+',
    '#',
    1,
    2
) AS replace_second;
```

Kết quả: `A12-B#-C56`.

Tham số `pos` xác định nơi bắt đầu tìm; `occurrence` xác định lần khớp sẽ thay. Đọc kỹ hai tham số này vì thứ tự đối số khác với một số thư viện regex trong ứng dụng.

### 6.2. Dùng capturing group trong chuỗi thay thế

Trong `REGEXP_REPLACE()`, có thể tham chiếu nhóm bắt giữ bằng `\N`, trong đó N là số thứ tự nhóm. Với SQL string literal mặc định của MySQL, dấu gạch chéo ngược cần được escape.

Ví dụ đổi định dạng `Nguyen, An` thành `An Nguyen`:

```sql
SELECT REGEXP_REPLACE(
    'Nguyen, An',
    '^([^,]+),[[:space:]]*(.+)$',
    '\\2 \\1'
) AS formatted_name;
```

Chuỗi thay thế `'\\2 \\1'` được MySQL diễn giải để regex engine nhận các backreference nhóm. Nếu session bật `NO_BACKSLASH_ESCAPES`, quy tắc xử lý string literal khác; cần điều chỉnh chuỗi thay thế và kiểm thử trên session thực tế.

Có thể dùng nhóm để trích domain từ email:

```sql
SELECT REGEXP_REPLACE(
    'user@example.com',
    '^[^@]+@([^@]+)$',
    '\\1'
) AS email_domain;
```

Pattern này chỉ là ví dụ cho cấu trúc email đơn giản. Địa chỉ email thực tế có quy tắc phức tạp; không dùng một regex ngắn để khẳng định mọi email hợp lệ theo chuẩn.

## 7. Một số pattern thực tế

### 7.1. Kiểm tra mã nhân viên

Mã nhân viên có dạng hai chữ cái, dấu gạch ngang và năm chữ số:

```sql
SELECT REGEXP_LIKE(
    'HR-01234',
    '^[A-Z]{2}-[0-9]{5}$',
    'c'
) AS valid_employee_code;
```

Pattern có neo đầu/cuối nên toàn bộ chuỗi phải đúng cấu trúc.

### 7.2. Trích xuất mã đơn hàng

```sql
SELECT REGEXP_SUBSTR(
    'created order: ORD-2026-000981 successfully',
    'ORD-[0-9]{4}-[0-9]{6}'
) AS order_code;
```

Hàm trả về phần mã đơn hàng khớp pattern. Nếu log có nhiều mã, hãy xác định rõ occurrence cần lấy.

### 7.3. Chuẩn hóa khoảng trắng

```sql
SELECT REGEXP_REPLACE(
    '  MySQL     database   engine  ',
    '[[:space:]]+',
    ' '
) AS normalized_text;
```

Kết quả có một dấu cách thay cho mỗi dãy khoảng trắng. Pattern không tự loại khoảng trắng ở đầu/cuối; có thể kết hợp với `TRIM()`:

```sql
SELECT TRIM(
    REGEXP_REPLACE(
        '  MySQL     database   engine  ',
        '[[:space:]]+',
        ' '
    )
) AS normalized_text;
```

### 7.4. Tìm chuỗi có ký tự ngoài tập cho phép

```sql
SELECT username
FROM users
WHERE REGEXP_LIKE(username, '[^A-Za-z0-9_]');
```

Pattern trên tìm chuỗi có ít nhất một ký tự không thuộc tập ASCII cho phép. Nếu muốn chỉ trả các username không hợp lệ theo toàn bộ quy tắc, cần kiểm tra cả độ dài, chuỗi rỗng và NULL.

### 7.5. Tìm dòng bắt đầu bằng từ khóa

```sql
SELECT log_id, message
FROM application_logs
WHERE REGEXP_LIKE(message, '^ERROR:', 'm');
```

Cờ multiline cho phép tìm dòng bắt đầu bằng ERROR trong một cột văn bản nhiều dòng. Nếu chỉ cần tìm tiền tố ở đầu chuỗi, `LIKE 'ERROR:%'` thường đơn giản và có cơ hội tận dụng index tốt hơn.

## 8. Character set, collation và binary string

Các hàm regex của MySQL 8.0 xử lý chuỗi theo character set/collation và engine ICU. Một số điểm cần nhớ:

- Pattern và chuỗi nên dùng character set tương thích; ưu tiên `utf8mb4` cho văn bản Unicode.
- Collation có thể ảnh hưởng đến mặc định phân biệt hoa/thường; dùng `match_type` để thể hiện rõ yêu cầu.
- Chuỗi nhị phân có thể gây lỗi character set mismatch với regex functions của MySQL 8.0. Nếu dữ liệu là binary, hãy chuyển đổi có chủ đích sang character set văn bản sau khi xác định encoding.
- Không dùng `BINARY` hoặc `CAST(... AS BINARY)` như cách ép regex chạy theo byte nếu mục tiêu là xử lý Unicode.

Kiểm tra charset và collation của cột:

```sql
SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
  AND COLUMN_NAME = 'username';
```

Kiểm tra collation connection:

```sql
SELECT
    @@character_set_connection,
    @@collation_connection;
```

Nếu cần kiểm tra phân biệt hoa/thường, truyền cờ `c` hoặc `i` rõ ràng thay vì dựa vào cấu hình connection hoặc collation mặc định.

## 9. Hiệu năng và khả năng sử dụng index

Regex rất linh hoạt, nhưng thường không thể dùng B-tree index để tìm kiếm theo pattern như một phép so sánh bằng hoặc một prefix range đơn giản. Điều kiện như:

```sql
SELECT user_id
FROM users
WHERE REGEXP_LIKE(username, '^admin');
```

có thể phải kiểm tra regex trên nhiều hàng. Ngay cả khi pattern bắt đầu bằng `^admin`, optimizer không bảo đảm chuyển nó thành range scan trên index thông thường.

Nếu yêu cầu chỉ là tìm tiền tố, hãy dùng LIKE:

```sql
SELECT user_id
FROM users
WHERE username LIKE 'admin%';
```

Với collation và pattern phù hợp, `LIKE 'admin%'` có cơ hội dùng index B-tree cho range scan. Cần kiểm tra bằng `EXPLAIN`; wildcard ở đầu như `'%admin'` thường không tận dụng được range của index B-tree.

### 9.1. Lọc sơ bộ bằng index trước khi chạy regex

Nếu cần regex phức tạp, hãy giảm số hàng đầu vào bằng các điều kiện có index khi logic cho phép:

```sql
SELECT user_id, username
FROM users
WHERE tenant_id = 42
  AND created_at >= '2026-01-01'
  AND REGEXP_LIKE(username, '^[A-Za-z][A-Za-z0-9_]{2,19}$', 'c');
```

Index phù hợp trên `tenant_id` hoặc tổ hợp với `created_at` có thể thu hẹp tập ứng viên trước khi regex được đánh giá. Thứ tự và loại index phải dựa trên phân bố dữ liệu cùng workload thực tế.

### 9.2. Đo kế hoạch và thời gian

```sql
EXPLAIN
SELECT user_id
FROM users
WHERE REGEXP_LIKE(username, '^[A-Za-z0-9_]{3,20}$', 'c');
```

Trên phiên bản hỗ trợ, dùng `EXPLAIN ANALYZE` để xem thời gian và số hàng thực tế. Nó thực thi câu SELECT, vì vậy cần đánh giá dữ liệu và tải trước khi chạy trên production.

Nếu regex được dùng trong mọi lần đọc một bảng lớn, hãy xem xét chuẩn hóa và xác thực dữ liệu khi ghi. Có thể lưu một cột trạng thái đã xác thực hoặc một giá trị chuẩn hóa để truy vấn bằng index, thay vì chạy regex lặp lại trên toàn bộ dữ liệu.

### 9.3. Giới hạn tài nguyên regex

MySQL 8.0 cung cấp các biến như `regexp_time_limit` và `regexp_stack_limit` để giới hạn công việc và stack mà bộ máy regex có thể sử dụng. Chúng giúp giảm rủi ro pattern phức tạp tiêu tốn tài nguyên quá mức.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'regexp_%';
```

`regexp_time_limit` giới hạn số bước xử lý của engine regex, không nên hiểu đơn giản là số giây wall-clock. `regexp_stack_limit` giới hạn stack được dùng. Giá trị mặc định và phạm vi thay đổi phụ thuộc phiên bản; hãy kiểm tra tài liệu đúng bản MySQL đang triển khai.

Không cho phép người dùng gửi pattern tùy ý vào truy vấn chạy trên bảng lớn mà không có giới hạn. Pattern phức tạp, nhiều nhánh hoặc lượng tử lồng nhau có thể gây chi phí cao. Cần giới hạn độ dài pattern, quyền sử dụng, thời gian truy vấn và số lượng hàng được xét.

## 10. Dùng regex trong Java và JDBC

Khi ứng dụng Java gửi regex tới MySQL, pattern được diễn giải bởi bộ máy regex của MySQL, không phải `java.util.regex.Pattern`. Hai engine có thể khác cú pháp, Unicode behavior và nhóm tính năng. Hãy kiểm thử pattern trên MySQL đích.

Dùng prepared statement để truyền pattern như tham số:

```java
String sql = """
    SELECT user_id, username
    FROM users
    WHERE REGEXP_LIKE(username, ?, 'c')
    """;

String pattern = "^[A-Za-z][A-Za-z0-9_]{2,19}$";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, pattern);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("user_id")
                    + ": " + rs.getString("username"));
        }
    }
}
```

Prepared statement bảo vệ cấu trúc SQL khỏi việc nối trực tiếp pattern vào câu lệnh. Tuy nhiên, nó không làm regex rẻ hơn hoặc tự giới hạn độ phức tạp của pattern. Nếu pattern do người dùng cung cấp, vẫn cần kiểm tra quyền và giới hạn.

Ví dụ trên dùng Java text block, có từ Java 15. Với phiên bản Java cũ hơn, dùng chuỗi nối hoặc string literal thông thường. Nếu pattern chứa dấu gạch chéo ngược, cần xử lý escape theo hai lớp: Java string literal và SQL parameter. Khi bind bằng JDBC, pattern được gửi như giá trị nên không cần tự escape theo cú pháp SQL string.

## 11. REGEXP và CHECK constraint: kiểm tra dữ liệu ở đâu?

Regex có thể dùng để kiểm tra định dạng ở câu SELECT, nhưng nếu dữ liệu phải luôn hợp lệ, hãy cân nhắc xác thực ở ranh giới ghi.

Ví dụ MySQL 8.0.16 trở lên thực thi CHECK constraint:

```sql
CREATE TABLE employee_codes (
    employee_id BIGINT PRIMARY KEY,
    employee_code VARCHAR(8) NOT NULL,
    CONSTRAINT chk_employee_code
        CHECK (
            REGEXP_LIKE(employee_code, '^[A-Z]{2}[0-9]{6}$', 'c')
        )
) ENGINE = InnoDB;
```

Trên MySQL trước 8.0.16, CHECK constraint được phân tích nhưng không được thực thi như ràng buộc dữ liệu. Vì vậy, kiểm tra version trước khi dựa vào CHECK để bảo vệ dữ liệu.

Dù có CHECK, ứng dụng vẫn nên validate để phản hồi lỗi thân thiện. Database constraint là lớp bảo vệ cuối cùng khi có nhiều client hoặc đường ghi khác nhau. Nếu định dạng mã có thể mô tả bằng kiểu dữ liệu, foreign key, unique key hoặc constraint đơn giản hơn, hãy ưu tiên quy tắc cấu trúc rõ ràng.

Không dùng regex thay cho:

- `UNIQUE` khi cần bảo đảm không trùng.
- `FOREIGN KEY` khi cần bảo đảm quan hệ.
- Kiểu số/ngày giờ khi dữ liệu có bản chất số/ngày giờ.
- Kiểm tra độ dài và nullability khi có thể khai báo trực tiếp trong schema.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc sửa |
|---|---|---|
| `FUNCTION REGEXP_LIKE does not exist` | Server cũ như MySQL 5.7 hoặc sản phẩm không tương thích | Kiểm tra `VERSION()`; dùng toán tử có sẵn hoặc nâng cấp |
| Pattern chạy khác sau nâng cấp | MySQL 8.0 dùng ICU thay bộ máy cũ | Kiểm thử lại cú pháp và kết quả trên version đích |
| Regex khớp một phần ngoài ý muốn | Thiếu `^` và `$` | Neo pattern nếu cần khớp toàn chuỗi |
| Hoa/thường cho kết quả bất ngờ | Collation hoặc match_type mặc định | Truyền `c` hoặc `i` |
| Regex Unicode lỗi hoặc sai ký tự | Charset/binary string không phù hợp | Kiểm tra charset/collation; dùng văn bản `utf8mb4` |
| Truy vấn chậm trên bảng lớn | Regex phải kiểm tra nhiều hàng; index B-tree không hỗ trợ pattern | Lọc bằng điều kiện có index trước, đo EXPLAIN |
| Pattern sai cú pháp | Cú pháp thuộc engine khác hoặc escape sai | Kiểm thử pattern nhỏ trên MySQL đích |
| REGEXP_REPLACE không thay đúng nhóm | Escape backreference sai ở SQL string literal | Kiểm tra `NO_BACKSLASH_ESCAPES` và dùng `\\1`, `\\2` phù hợp |
| Regex chạy quá lâu | Pattern phức tạp hoặc input lớn | Giới hạn pattern, hàng đầu vào và regexp resource limits |

## 13. Quy trình triển khai regex an toàn

Khi đưa regex vào truy vấn hoặc schema, thực hiện theo thứ tự:

1. **Xác nhận phiên bản server.** Kiểm tra MySQL 5.7, MySQL 8.0 và bản phân phối cụ thể; không dựa vào version JDBC.
2. **Xác định mục tiêu.** Cần kiểm tra toàn chuỗi, tìm đoạn con, trích xuất hay thay thế?
3. **Chọn hàm phù hợp.** Dùng REGEXP_LIKE cho kiểm tra, REGEXP_SUBSTR cho trích xuất và REGEXP_REPLACE cho chuẩn hóa/thay thế.
4. **Viết pattern có chủ đích.** Dùng anchor khi cần toàn chuỗi, nhóm và lượng từ rõ ràng; tránh pattern quá rộng.
5. **Kiểm tra Unicode và collation.** Xác định character set, phân biệt hoa/thường, dấu và line ending.
6. **Kiểm thử dữ liệu biên.** Bao gồm chuỗi rỗng, NULL, ký tự Unicode, newline, ký tự escape, chuỗi quá dài và dữ liệu sai định dạng.
7. **Đo hiệu năng.** Dùng EXPLAIN/EXPLAIN ANALYZE và lọc sơ bộ bằng index khi có thể.
8. **Giới hạn tài nguyên.** Xem regexp_time_limit, regexp_stack_limit và giới hạn pattern do người dùng cung cấp.
9. **Xác thực lúc ghi.** Dùng ứng dụng và CHECK constraint nếu phiên bản hỗ trợ; không chỉ lọc dữ liệu sai khi đọc.
10. **Kiểm thử nâng cấp.** Chạy bộ pattern trên cả version hiện tại và version đích trước khi thay đổi production.

## 14. Ghi nhớ

- MySQL 5.7 chủ yếu có toán tử REGEXP/RLIKE với bộ máy regex cũ; MySQL 8.0 dùng ICU và có REGEXP_LIKE, REGEXP_SUBSTR, REGEXP_REPLACE.
- Bộ ba hàm regex xuất hiện từ MySQL 8.0.4; dòng MySQL 8.0 GA bắt đầu ở 8.0.11.
- REGEXP_LIKE kiểm tra mẫu và trả 1/0/NULL; REGEXP_SUBSTR trả toàn bộ đoạn khớp; REGEXP_REPLACE thay các đoạn khớp.
- pos bắt đầu từ 1; occurrence của SUBSTR chọn lần khớp; occurrence của REPLACE mặc định 0 để thay tất cả.
- match_type có các cờ c, i, m, n, u; chỉ định rõ phân biệt hoa/thường khi cần kết quả ổn định.
- REGEXP_SUBSTR không trả riêng capturing group; REGEXP_REPLACE có thể dùng backreference trong chuỗi thay thế.
- Pattern được diễn giải bởi engine MySQL, không phải Java regex; kiểm thử trên server đích.
- Regex thường không tận dụng B-tree index như phép so sánh bằng hoặc prefix LIKE; hãy lọc sơ bộ và đo execution plan.
- Giới hạn pattern do người dùng cung cấp và kiểm tra regexp_time_limit, regexp_stack_limit.
- CHECK constraint chỉ được thực thi từ MySQL 8.0.16; vẫn cần xác thực ở ứng dụng và dùng UNIQUE/FOREIGN KEY cho các ràng buộc tương ứng.

Hãy chọn đúng hàm theo mục tiêu, viết pattern phù hợp engine và phiên bản MySQL, rồi đo hiệu năng trên dữ liệu thật. Regex là công cụ mạnh cho xử lý chuỗi, nhưng cần được đặt trong thiết kế kiểu dữ liệu, constraint, index và validation rõ ràng để tránh truy vấn chậm hoặc dữ liệu sai.

