# SUBSTRING, LEFT, RIGHT, LOCATE và thao tác chuỗi

Trong một hệ thống bán hàng, dữ liệu chuỗi thường cần được tách, tìm và chuẩn hóa trước khi hiển thị hoặc đối chiếu. Bạn có thể lấy mã vùng từ số điện thoại, tách domain từ email, tìm vị trí dấu phân cách trong mã đơn hàng, cắt tiền tố của SKU hoặc loại bỏ khoảng trắng thừa khỏi tên khách hàng.

MySQL cung cấp các hàm như `SUBSTRING`, `LEFT`, `RIGHT` và `LOCATE` để thao tác vị trí ký tự; các hàm `CONCAT`, `TRIM`, `REPLACE`, `SUBSTRING_INDEX` hỗ trợ ghép và biến đổi chuỗi. Dùng đúng hàm giúp câu SQL dễ đọc, nhưng cần hiểu cách đếm ký tự, xử lý `NULL`, collation và tác động đến index để tránh kết quả sai hoặc truy vấn chậm.

## 1. Chuẩn bị: ký tự, byte và chuỗi trong MySQL

### 1.1. CHAR_LENGTH và LENGTH

Với dữ liệu Unicode như tiếng Việt, số ký tự và số byte không giống nhau:

- `CHAR_LENGTH(str)` trả về số ký tự theo character set.
- `LENGTH(str)` trả về số byte của chuỗi.

Ví dụ:

```sql
SELECT
    'Đặng' AS sample,
    CHAR_LENGTH('Đặng') AS character_count,
    LENGTH('Đặng') AS byte_count,
    HEX('Đặng') AS utf8_bytes;
```

Nếu connection dùng `utf8mb4`, `CHAR_LENGTH('Đặng')` đếm bốn ký tự, còn `LENGTH('Đặng')` đếm số byte UTF-8 được dùng để mã hóa chúng. Một ký tự có thể chiếm từ một đến bốn byte.

Các hàm `SUBSTRING`, `LEFT`, `RIGHT` và `LOCATE` làm việc theo vị trí ký tự đối với chuỗi nonbinary. Với dữ liệu nhị phân như `BINARY`, `VARBINARY` hoặc đối số được chuyển sang binary string, thao tác được tính theo byte. Không dùng `LENGTH()` để quyết định vị trí cắt chuỗi tiếng Việt.

Lưu ý thêm: một ký tự mà người dùng nhìn thấy có thể được tạo bởi nhiều Unicode code point, chẳng hạn ký tự cơ sở kết hợp combining mark. `CHAR_LENGTH()` đếm code point theo character set, không đếm cụm ký tự hiển thị (grapheme cluster). Nếu giao diện cần cắt theo cụm ký tự người dùng nhìn thấy, hãy xử lý Unicode grapheme ở tầng ứng dụng.

### 1.2. Character set và collation

Character set xác định cách mã hóa chuỗi; collation xác định cách so sánh và sắp xếp. Với dữ liệu tiếng Việt mới, nên dùng `utf8mb4` và chọn collation phù hợp yêu cầu nghiệp vụ.

Collation có thể ảnh hưởng đến việc `LOCATE` tìm thấy chuỗi con theo so sánh không phân biệt hoa/thường hoặc dấu. Ngược lại, `REPLACE()` thực hiện tìm chuỗi con theo cách phân biệt hoa/thường. Vì vậy, hai hàm tìm chuỗi không nhất thiết có cùng hành vi.

Kiểm tra cấu hình của biểu thức:

```sql
SELECT
    CHARSET('Tiếng Việt') AS character_set_name,
    COLLATION('Tiếng Việt') AS collation_name,
    @@SESSION.character_set_connection AS connection_charset,
    @@SESSION.collation_connection AS connection_collation;
```

## 2. SUBSTRING: lấy một phần của chuỗi

`SUBSTRING()` (có alias `SUBSTR()`) trả về một phần chuỗi từ vị trí bắt đầu. Cú pháp:

```sql
SUBSTRING(str, pos)
SUBSTRING(str, pos, len)
```

- `str`: chuỗi nguồn.
- `pos`: vị trí bắt đầu, tính từ 1.
- `len`: số ký tự muốn lấy; nếu bỏ qua, lấy đến cuối chuỗi.

Ví dụ:

```sql
SELECT
    SUBSTRING('abcdef', 2) AS from_second,
    SUBSTRING('abcdef', 2, 3) AS three_chars,
    SUBSTRING('abcdef', -3) AS last_three,
    SUBSTRING('abcdef', -4, 2) AS from_fourth_from_end;
```

Kết quả:

| Biểu thức | Kết quả | Giải thích |
|---|---|---|
| `SUBSTRING('abcdef', 2)` | `bcdef` | Bắt đầu từ ký tự thứ 2 đến cuối |
| `SUBSTRING('abcdef', 2, 3)` | `bcd` | Lấy 3 ký tự từ vị trí 2 |
| `SUBSTRING('abcdef', -3)` | `def` | Đếm vị trí từ cuối chuỗi |
| `SUBSTRING('abcdef', -4, 2)` | `cd` | Bắt đầu ở vị trí thứ 4 tính từ cuối, lấy 2 ký tự |

### 2.1. Vị trí 0 và độ dài

Vị trí bắt đầu trong `SUBSTRING` là 1-based. Nếu `pos = 0`, kết quả là chuỗi rỗng. Nếu `len` là số âm, kết quả cũng là chuỗi rỗng. Nếu `pos` vượt quá chiều dài chuỗi, không có ký tự nào được trả về.

```sql
SELECT
    SUBSTRING('abcdef', 0, 3) AS position_zero,
    SUBSTRING('abcdef', 2, 0) AS zero_length,
    SUBSTRING('abcdef', 2, -1) AS negative_length,
    SUBSTRING('abcdef', 20, 2) AS beyond_end;
```

Các trường hợp này trả về chuỗi rỗng. Nếu `str` là SQL `NULL`, kết quả là `NULL`.

### 2.2. Cú pháp SQL chuẩn

MySQL cũng hỗ trợ cách viết:

```sql
SELECT
    SUBSTRING('abcdef' FROM 2) AS value_1,
    SUBSTRING('abcdef' FROM 2 FOR 3) AS value_2;
```

Cách viết này có cùng ý nghĩa với `SUBSTRING(str, pos)` và `SUBSTRING(str, pos, len)`. Trong code ứng dụng, nên thống nhất một kiểu viết để dễ đọc và bảo trì.

### 2.3. Tách phần chuỗi theo vị trí tìm được

Kết hợp `LOCATE` và `SUBSTRING` để tách phần trước/sau một dấu phân cách. Ví dụ lấy domain của email:

```sql
SELECT
    email,
    SUBSTRING(email, LOCATE('@', email) + 1) AS email_domain
FROM customers;
```

Ví dụ trên giả định email hợp lệ và có đúng dấu `@` cần tìm. Nếu `LOCATE` trả về `0`, phép tính bắt đầu ở vị trí 1 và có thể trả lại toàn bộ chuỗi; vì vậy cần kiểm tra dữ liệu trước khi tách:

```sql
SELECT
    email,
    CASE
        WHEN LOCATE('@', email) > 1
        THEN SUBSTRING(email, LOCATE('@', email) + 1)
        ELSE NULL
    END AS email_domain
FROM customers;
```

Đây chỉ là thao tác tách chuỗi, không phải bộ xác thực email đầy đủ. Nếu cần xác thực địa chỉ email, hãy dùng quy tắc phù hợp ở tầng ứng dụng.

## 3. LEFT và RIGHT: lấy phần đầu hoặc cuối chuỗi

`LEFT(str, len)` lấy `len` ký tự từ bên trái; `RIGHT(str, len)` lấy `len` ký tự từ bên phải.

```sql
SELECT
    LEFT('MYSQL-2026-001', 5) AS prefix,
    RIGHT('MYSQL-2026-001', 3) AS suffix;
```

Kết quả lần lượt là `MYSQL` và `001`.

### 3.1. Quy tắc độ dài

- `len` được tính theo ký tự đối với chuỗi nonbinary.
- `len = 0` trả chuỗi rỗng.
- `len` âm trả chuỗi rỗng.
- Nếu `len` lớn hơn chiều dài chuỗi, hàm trả toàn bộ chuỗi.
- Nếu `str` là SQL `NULL`, kết quả là `NULL`.

Ví dụ với tiếng Việt:

```sql
SELECT
    LEFT('Cơ sở dữ liệu', 2) AS first_two,
    RIGHT('Cơ sở dữ liệu', 5) AS last_five;
```

`LEFT` và `RIGHT` phù hợp khi lấy tiền tố/hậu tố có độ dài cố định, như mã vùng, phần đuôi mã đơn hàng hoặc ký hiệu phân loại. Không dùng chúng để cắt một chuỗi theo byte khi chuỗi có thể chứa Unicode nhiều byte.

### 3.2. LEFT và RIGHT so với SUBSTRING

Các biểu thức sau tương đương trong trường hợp độ dài hợp lệ:

```sql
SELECT
    LEFT('abcdef', 3) AS left_value,
    SUBSTRING('abcdef', 1, 3) AS substring_value,
    RIGHT('abcdef', 2) AS right_value,
    SUBSTRING('abcdef', -2) AS substring_from_end;
```

`LEFT`/`RIGHT` diễn đạt ý định rõ hơn khi chỉ lấy từ một đầu chuỗi. Dùng `SUBSTRING` khi vị trí bắt đầu hoặc độ dài được tính động.

## 4. LOCATE: tìm vị trí của chuỗi con

`LOCATE()` trả về vị trí xuất hiện đầu tiên của một chuỗi con trong chuỗi nguồn. Cú pháp:

```sql
LOCATE(substr, str)
LOCATE(substr, str, pos)
```

- `substr`: chuỗi cần tìm.
- `str`: chuỗi nguồn.
- `pos`: vị trí bắt đầu tìm, tính từ 1; nếu bỏ qua, bắt đầu từ đầu chuỗi.

Ví dụ:

```sql
SELECT
    LOCATE('at', 'catalog') AS first_match,
    LOCATE('at', 'catalog', 3) AS match_from_position_3,
    LOCATE('xyz', 'catalog') AS not_found;
```

Kết quả:

| Biểu thức | Kết quả | Giải thích |
|---|---:|---|
| `LOCATE('at', 'catalog')` | `2` | Chuỗi `at` bắt đầu ở vị trí 2 |
| `LOCATE('at', 'catalog', 3)` | `4` | Bắt đầu tìm từ vị trí 3, tìm thấy ở vị trí 4 |
| `LOCATE('xyz', 'catalog')` | `0` | Không tìm thấy |

Nếu không tìm thấy, hàm trả `0`, không trả `NULL`. Nếu một đối số là SQL `NULL`, kết quả là `NULL`.

### 4.1. LOCATE và collation

Với chuỗi nonbinary, việc tìm kiếm của `LOCATE` chịu ảnh hưởng bởi collation. Ví dụ một collation không phân biệt hoa/thường có thể tìm thấy `mysql` trong `MySQL`; một collation không phân biệt dấu có thể xem các dạng chữ có dấu và không dấu là tương đương theo quy tắc collation.

Kiểm tra trên collation cụ thể:

```sql
SELECT
    LOCATE(
        _utf8mb4'mysql' COLLATE utf8mb4_0900_ai_ci,
        _utf8mb4'MySQL Server' COLLATE utf8mb4_0900_ai_ci
    ) AS case_insensitive_match,
    LOCATE(
        _utf8mb4'mysql' COLLATE utf8mb4_0900_as_cs,
        _utf8mb4'MySQL Server' COLLATE utf8mb4_0900_as_cs
    ) AS case_sensitive_match;
```

Các collation `utf8mb4_0900_*` có trên MySQL 8.0. Hãy chọn collation thực sự có trên server bằng `SHOW COLLATION` và kiểm thử theo yêu cầu của ứng dụng.

Nếu cần tìm theo byte chính xác, có thể dùng binary string hoặc collation binary phù hợp. Ví dụ:

```sql
SELECT LOCATE(BINARY 'mysql', BINARY 'MySQL Server') AS exact_match;
```

Phép tìm binary phân biệt chữ hoa/thường và byte. Cần cân nhắc charset và encoding trước khi dùng để đối chiếu dữ liệu Unicode.

### 4.2. LOCATE, INSTR và POSITION

Ba cách viết dưới đây có cùng mục đích tìm vị trí chuỗi con:

```sql
SELECT
    LOCATE('SQL', 'MySQL Server') AS locate_result,
    INSTR('MySQL Server', 'SQL') AS instr_result,
    POSITION('SQL' IN 'MySQL Server') AS position_result;
```

`LOCATE` nhận chuỗi cần tìm làm đối số thứ nhất; `INSTR` nhận chuỗi nguồn trước; `POSITION` dùng cú pháp `substr IN str`. Chọn cách viết nhất quán để người đọc không nhầm thứ tự đối số.

## 5. SUBSTRING_INDEX: tách theo dấu phân cách

`SUBSTRING_INDEX(str, delim, count)` trả về phần chuỗi nằm trước hoặc sau một số lần xuất hiện của delimiter:

- `count` dương: lấy phần bên trái đến lần xuất hiện thứ `count` từ trái.
- `count` âm: lấy phần bên phải tính từ lần xuất hiện thứ `|count|` từ phải.
- `count = 0`: trả chuỗi rỗng.
- Nếu delimiter không xuất hiện đủ số lần, trả lại toàn bộ chuỗi theo phía được yêu cầu.

Ví dụ:

```sql
SELECT
    SUBSTRING_INDEX('www.mysql.com', '.', 1) AS first_label,
    SUBSTRING_INDEX('www.mysql.com', '.', 2) AS first_two_labels,
    SUBSTRING_INDEX('www.mysql.com', '.', -1) AS top_level_domain;
```

Kết quả lần lượt là `www`, `www.mysql` và `com`.

Lấy phần trước dấu `@` trong email:

```sql
SELECT SUBSTRING_INDEX('alice@example.com', '@', 1) AS local_part;
```

Lấy phần domain:

```sql
SELECT SUBSTRING_INDEX('alice@example.com', '@', -1) AS domain_part;
```

`SUBSTRING_INDEX` rất tiện khi delimiter có cấu trúc ổn định. Nếu dữ liệu có thể thiếu delimiter hoặc chứa nhiều delimiter ngoài dự kiến, hãy xác thực số lần xuất hiện trước khi dùng kết quả cho nghiệp vụ.

## 6. Ghép chuỗi với CONCAT và CONCAT_WS

### 6.1. CONCAT

`CONCAT(str1, str2, ...)` nối các đối số thành một chuỗi:

```sql
SELECT CONCAT('Order-', 2026, '-', '0001') AS order_code;
```

Kết quả là `Order-2026-0001`. Nếu bất kỳ đối số nào là SQL `NULL`, `CONCAT` trả `NULL`:

```sql
SELECT CONCAT('Nguyễn', ' ', NULL) AS full_name;
```

Kết quả là `NULL`. Nếu cần bỏ qua giá trị NULL, cân nhắc `CONCAT_WS`.

### 6.2. CONCAT_WS

`CONCAT_WS(separator, str1, str2, ...)` nối các giá trị với separator ở giữa. Các đối số sau separator có giá trị `NULL` sẽ bị bỏ qua; chuỗi rỗng không bị bỏ qua. Nếu separator là `NULL`, toàn bộ kết quả là `NULL`.

```sql
SELECT
    CONCAT_WS(' ', 'Nguyễn', NULL, 'An') AS display_name,
    CONCAT_WS('-', 'HN', '', '001') AS code_with_empty_part;
```

Kết quả là `Nguyễn An` và `HN--001`. Điều này hữu ích khi ghép tên có thể thiếu tên đệm hoặc địa chỉ có thành phần tùy chọn.

## 7. TRIM, LTRIM và RTRIM

Khoảng trắng đầu/cuối thường xuất hiện khi nhập dữ liệu, import CSV hoặc nhận input từ hệ thống khác. MySQL có:

- `TRIM(str)`: bỏ ký tự space ở đầu và cuối.
- `LTRIM(str)`: bỏ space ở đầu.
- `RTRIM(str)`: bỏ space ở cuối.
- `TRIM(BOTH remstr FROM str)`: bỏ chuỗi `remstr` lặp lại ở cả hai đầu.
- `TRIM(LEADING remstr FROM str)`: chỉ bỏ ở đầu.
- `TRIM(TRAILING remstr FROM str)`: chỉ bỏ ở cuối.

Ví dụ:

```sql
SELECT
    TRIM('   MySQL   ') AS trimmed,
    LTRIM('   MySQL   ') AS left_trimmed,
    RTRIM('   MySQL   ') AS right_trimmed,
    TRIM(BOTH '-' FROM '---SKU-100---') AS clean_code;
```

Kết quả lần lượt là `MySQL`, `MySQL   `, `   MySQL` và `SKU-100`.

Mặc định `TRIM` xử lý space thông thường; không đồng nghĩa với loại bỏ mọi whitespace Unicode như tab, newline hoặc nonbreaking space. Nếu cần chuẩn hóa nhiều loại whitespace, hãy xác định danh sách ký tự và dùng hàm phù hợp hoặc xử lý ở tầng ứng dụng.

## 8. REPLACE và INSERT dùng như hàm chuỗi

### 8.1. REPLACE

`REPLACE(str, from_str, to_str)` thay mọi lần xuất hiện của chuỗi con `from_str` bằng `to_str`:

```sql
SELECT REPLACE('2026/11/19', '/', '-') AS normalized_date_text;
```

Kết quả là `2026-11-19`. `REPLACE()` tìm chuỗi con theo cách phân biệt hoa/thường. Nếu cần quy tắc không phân biệt hoa/thường, hãy thiết kế phép chuẩn hóa rõ ràng; đừng giả định collation của cột sẽ làm `REPLACE` bỏ qua khác biệt hoa/thường.

### 8.2. INSERT() là hàm thay một đoạn chuỗi

Hàm `INSERT(str, pos, len, newstr)` thay `len` ký tự trong chuỗi nguồn bắt đầu từ vị trí `pos` bằng `newstr`. Nó không phải câu lệnh SQL `INSERT INTO`.

```sql
SELECT
    INSERT('abcdef', 2, 3, 'XYZ') AS replaced_part,
    INSERT('abcdef', 4, 0, '-') AS inserted_separator;
```

Kết quả là `aXYZef` và `abc-def`. Vị trí tính từ 1; độ dài bằng 0 chèn `newstr` mà không xóa ký tự nào. Nếu vị trí bắt đầu vượt quá chiều dài chuỗi, chuỗi nguồn được trả lại.

## 9. Kết hợp nhiều hàm trong một truy vấn thực tế

Giả sử bảng `products` lưu mã SKU theo dạng `VN-HCM-000123`, còn bảng `customers` lưu email và tên. Có thể tách thành phần mã và email bằng các hàm chuỗi:

```sql
SELECT
    sku,
    SUBSTRING_INDEX(sku, '-', 1) AS country_code,
    SUBSTRING_INDEX(SUBSTRING_INDEX(sku, '-', 2), '-', -1) AS city_code,
    RIGHT(sku, 6) AS sequence_no
FROM products;
```

Với email:

```sql
SELECT
    email,
    CASE
        WHEN LOCATE('@', email) > 1
        THEN SUBSTRING_INDEX(email, '@', 1)
        ELSE NULL
    END AS email_user,
    CASE
        WHEN LOCATE('@', email) > 1
        THEN SUBSTRING_INDEX(email, '@', -1)
        ELSE NULL
    END AS email_domain
FROM customers;
```

Để làm sạch tên hiển thị:

```sql
SELECT
    CONCAT_WS(
        ' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    ) AS display_name
FROM customer_profiles;
```

`NULLIF(value, '')` chuyển chuỗi rỗng thành SQL `NULL`, nhờ đó `CONCAT_WS` bỏ qua thành phần trống. Không dùng truy vấn hiển thị này thay cho quy trình chuẩn hóa dữ liệu gốc nếu các cột nguồn vẫn chứa khoảng trắng hoặc giá trị không hợp lệ.

## 10. NULL và chuỗi rỗng trong thao tác chuỗi

Các hàm chuỗi thường trả `NULL` nếu đối số bắt buộc là SQL `NULL`. Điều này khác với chuỗi rỗng `''`:

```sql
SELECT
    CONCAT('A', NULL) AS concat_null,
    CONCAT('A', '') AS concat_empty,
    LEFT(NULL, 2) AS left_null,
    LEFT('', 2) AS left_empty,
    LOCATE('x', NULL) AS locate_null,
    LOCATE('x', '') AS locate_empty;
```

Kết quả có thể là `NULL`, chuỗi `A`, `NULL`, chuỗi rỗng, `NULL` và `0` tương ứng.

Khi viết điều kiện, cần xử lý SQL NULL tường minh:

```sql
SELECT id, email
FROM customers
WHERE email IS NOT NULL
  AND LOCATE('@', email) > 1;
```

Không so sánh `email = NULL`; dùng `IS NULL` hoặc `IS NOT NULL`. Nếu cần thay NULL bằng chuỗi mặc định, dùng `COALESCE` hoặc `IFNULL` có chủ đích.

## 11. Vị trí ký tự và dữ liệu Unicode

Với chuỗi `Tiếng Việt`, vị trí trong `SUBSTRING`, `LEFT`, `RIGHT` và `LOCATE` là vị trí ký tự, không phải vị trí byte, khi đối số là chuỗi ký tự nonbinary. Điều này giúp tránh cắt giữa byte của một ký tự UTF-8.

Ví dụ:

```sql
SELECT
    CHAR_LENGTH('Tiếng Việt') AS char_count,
    LENGTH('Tiếng Việt') AS byte_count,
    SUBSTRING('Tiếng Việt', 1, 5) AS first_five_chars,
    RIGHT('Tiếng Việt', 4) AS last_four_chars;
```

Nếu ứng dụng nhận dữ liệu ở dạng binary, hoặc dùng `CAST(... AS BINARY)`, kết quả cắt có thể dựa trên byte. Không chuyển chuỗi Unicode sang binary chỉ để tìm kiếm hoặc cắt chuỗi thông thường.

Đối với Unicode normalization, hai chuỗi hiển thị giống nhau có thể có cách mã hóa khác nhau (NFC/NFD). Collation có thể xử lý các dạng này theo quy tắc riêng, nhưng hàm cắt vẫn dựa trên code point chứ không phải cụm ký tự hiển thị. Nên chuẩn hóa Unicode nhất quán ở tầng ứng dụng trước khi lưu nếu nghiệp vụ cần so sánh ổn định.

## 12. Ảnh hưởng của hàm chuỗi đến index và hiệu năng

### 12.1. Bọc cột trong hàm thường làm mất khả năng dùng index trực tiếp

Giả sử `products.sku` có B-tree index. Truy vấn:

```sql
SELECT id, sku
FROM products
WHERE LEFT(sku, 3) = 'VN-';
```

đang áp dụng hàm lên cột được index. MySQL thường không thể dùng index thông thường để tìm range trực tiếp theo biểu thức `LEFT(sku, 3)`. Có thể viết điều kiện tiền tố:

```sql
SELECT id, sku
FROM products
WHERE sku LIKE 'VN-%';
```

Với pattern có tiền tố cố định và collation phù hợp, optimizer có thể dùng B-tree index để tìm range. Hãy xác nhận bằng `EXPLAIN`.

Tương tự, điều kiện:

```sql
WHERE LOCATE('HCM', sku) > 0
```

thường phải kiểm tra chuỗi trong nhiều hàng. `LIKE '%HCM%'` cũng thường không dùng được B-tree để định vị substring vì wildcard nằm ở đầu pattern.

### 12.2. Generated column hoặc functional index

Nếu một biểu thức chuỗi được truy vấn thường xuyên, có thể tạo generated column rồi lập index:

```sql
ALTER TABLE products
ADD COLUMN sku_prefix VARCHAR(3)
    GENERATED ALWAYS AS (LEFT(sku, 3)) STORED,
ADD INDEX idx_sku_prefix (sku_prefix);
```

Truy vấn:

```sql
SELECT id, sku
FROM products
WHERE sku_prefix = 'VN-';
```

MySQL 8.0.13 trở lên còn hỗ trợ functional index cho biểu thức được phép. Generated column có tên thường dễ quan sát và tái sử dụng hơn. Cần cân nhắc chi phí lưu trữ, cập nhật index và tính xác định của biểu thức.

### 12.3. Đo bằng EXPLAIN

```sql
EXPLAIN
SELECT id, sku
FROM products
WHERE sku LIKE 'VN-%';
```

So sánh `key`, `type`, số hàng ước lượng và `Extra` giữa các cách viết. Không giả định một cách viết luôn nhanh hơn trên mọi dữ liệu; độ chọn lọc, kích thước bảng và thống kê optimizer đều ảnh hưởng kế hoạch.

## 13. Tránh dùng hàm chuỗi để ghép SQL động

Không dùng `CONCAT()` để ghép trực tiếp input người dùng vào câu SQL:

```sql
-- Không an toàn nếu user_input đến từ request.
SET @sql = CONCAT(
    'SELECT * FROM customers WHERE full_name = ''',
    @user_input,
    ''''
);
```

Ghép chuỗi như vậy có thể làm dữ liệu đầu vào thay đổi cú pháp SQL và tạo lỗ hổng SQL injection. Với giá trị, dùng prepared statement và parameter binding:

```sql
PREPARE customer_query FROM
    'SELECT id, full_name FROM customers WHERE full_name = ?';

SET @name_value = 'Nguyễn An';
EXECUTE customer_query USING @name_value;
DEALLOCATE PREPARE customer_query;
```

Với tên bảng/cột hoặc hướng sắp xếp động, placeholder không thể thay thế identifier. Dùng allowlist các lựa chọn hợp lệ do ứng dụng kiểm soát rồi mới dựng câu lệnh. Không xem `REPLACE`, `QUOTE` hay một hàm tự escape chuỗi là phương án thay thế prepared statement.

## 14. Các lỗi và tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Cắt chuỗi tiếng Việt bị lỗi hoặc lệch ký tự | Dùng byte length/byte position thay vì ký tự | Dùng hàm trên chuỗi nonbinary, kiểm tra `CHAR_LENGTH` và `LENGTH` |
| `LOCATE` trả `0` | Không tìm thấy chuỗi con hoặc bắt đầu tìm từ vị trí quá muộn | Kiểm tra đối số, collation và vị trí `pos` |
| `LOCATE` trả `NULL` | Một đối số là SQL `NULL` | Kiểm tra `IS NULL` và xử lý NULL rõ ràng |
| Tìm kiếm hoa/thường khác mong đợi | Collation không phù hợp hoặc đối số binary | Kiểm tra `COLLATION()` và thử dữ liệu thực tế |
| `REPLACE` không thay chữ khác hoa/thường | `REPLACE()` tìm chuỗi phân biệt hoa/thường | Chuẩn hóa dữ liệu hoặc dùng giải pháp phù hợp yêu cầu |
| `CONCAT` làm cả kết quả thành NULL | Một đối số là NULL | Dùng `CONCAT_WS`, `COALESCE` hoặc `NULLIF` có chủ đích |
| `LIKE` không tìm literal `%` hoặc `_` | Hai ký tự đang được hiểu là wildcard | Dùng mệnh đề `ESCAPE` và escape input |
| Truy vấn chậm sau khi dùng SUBSTRING/LOCATE trong WHERE | Hàm được áp dụng lên cột index | Viết lại thành range/prefix nếu được; cân nhắc generated column/index |
| Cắt mất một phần ký tự hiển thị | Một grapheme có nhiều code point | Chuẩn hóa và cắt theo grapheme ở tầng ứng dụng |

## 15. Checklist khi thao tác chuỗi

- Chuỗi là character string hay binary string?
- Cần đếm ký tự bằng `CHAR_LENGTH` hay byte bằng `LENGTH`?
- Vị trí bắt đầu là 1-based và có thể âm hay không?
- `LOCATE` trả `0` khi không tìm thấy; ứng dụng đã xử lý trường hợp đó chưa?
- Collation có làm phép tìm kiếm phân biệt/bỏ qua hoa thường hoặc dấu đúng yêu cầu không?
- SQL NULL, chuỗi rỗng và giá trị thiếu có được phân biệt không?
- `CONCAT` có thể trả NULL vì một đối số NULL không?
- `TRIM` có loại đúng loại whitespace cần xử lý không?
- `REPLACE` có yêu cầu phân biệt hoa/thường không?
- Điều kiện có bọc cột được index trong hàm và làm truy vấn mất khả năng dùng index không?
- Dữ liệu động có được bind bằng prepared statement thay vì ghép SQL không?
- Đã kiểm tra ví dụ Unicode, dấu nháy, delimiter thiếu và chuỗi rỗng chưa?

## Kết luận

`SUBSTRING` lấy đoạn chuỗi theo vị trí, `LEFT` và `RIGHT` lấy tiền tố/hậu tố, còn `LOCATE` tìm vị trí chuỗi con và trả `0` nếu không tìm thấy. `SUBSTRING_INDEX`, `CONCAT`, `CONCAT_WS`, `TRIM`, `REPLACE` và `INSERT()` hỗ trợ tách, ghép, làm sạch và thay thế nội dung. Hãy phân biệt ký tự với byte, xử lý SQL NULL và collation có chủ đích, kiểm tra tác động của hàm lên index, đồng thời dùng prepared statement cho dữ liệu động. Những quy tắc này giúp thao tác chuỗi tiếng Việt và dữ liệu ứng dụng chính xác, an toàn và dễ tối ưu.
