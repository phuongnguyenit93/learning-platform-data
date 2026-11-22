# So sánh chuỗi nhị phân, chuỗi văn bản và ký tự có dấu

Trong MySQL, hai giá trị chuỗi có thể được xem là bằng nhau theo quy tắc văn bản dù byte lưu trữ của chúng khác nhau. Ngược lại, hai giá trị trông giống nhau trên màn hình vẫn có thể khác byte vì được mã hóa hoặc chuẩn hóa theo cách khác. Nguyên nhân nằm ở sự khác biệt giữa **character set**, **collation** và **kiểu chuỗi nhị phân**.

Character set quy định cách mã hóa ký tự thành byte. Collation quy định cách so sánh và sắp xếp chuỗi ký tự: có phân biệt chữ hoa/thường không, có phân biệt dấu không, xử lý khoảng trắng cuối ra sao và thứ tự từ vựng thế nào. Chuỗi nhị phân như `BINARY` hoặc `VARBINARY` được so sánh theo byte, không dùng quy tắc ngôn ngữ của collation văn bản.

Với dữ liệu tiếng Việt, lựa chọn này ảnh hưởng trực tiếp tới tìm kiếm tên, kiểm tra trùng lặp, unique index, join, group và thứ tự hiển thị. Ví dụ, nếu collation không phân biệt dấu, `hoa` và `hòa` có thể được xem là tương đương trong một số phép so sánh. Điều đó có thể hữu ích cho tìm kiếm gần đúng, nhưng không phải lúc nào cũng phù hợp với quy tắc định danh hoặc dữ liệu nghiệp vụ.

## 1. Phân biệt ba lớp: byte, character set và collation

Hãy hình dung chuỗi `á` được lưu trong một cột `VARCHAR` dùng `utf8mb4`:

1. **Ký tự:** người dùng nhập chữ `á`.
2. **Character set:** `utf8mb4` mã hóa ký tự Unicode đó thành một dãy byte UTF-8.
3. **Collation:** khi so sánh với một chuỗi khác, MySQL áp dụng quy tắc collation của biểu thức hoặc cột để quyết định chúng bằng nhau hay đứng trước/sau nhau.

Ba lớp có nhiệm vụ khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Byte | Dữ liệu thực tế đang gồm những byte nào? | `HEX(name)`, `OCTET_LENGTH(name)` |
| Character set | Các byte được giải mã thành ký tự theo bảng mã nào? | `utf8mb4`, `latin1` |
| Collation | Hai chuỗi được so sánh và sắp xếp theo quy tắc nào? | `utf8mb4_0900_ai_ci`, `utf8mb4_0900_as_cs` |

`utf8mb4` hỗ trợ toàn bộ miền Unicode hiện đại, bao gồm ký tự ngoài BMP và emoji. Nhưng chỉ chọn `utf8mb4` chưa quyết định được `A` có bằng `a`, `a` có bằng `á`, hay dấu thanh tiếng Việt được sắp xếp thế nào. Những quyết định đó thuộc collation.

Có thể xem byte và số ký tự của một chuỗi:

```sql
SELECT
    'á' AS displayed_text,
    HEX('á') AS encoded_bytes,
    CHAR_LENGTH('á') AS character_count,
    OCTET_LENGTH('á') AS byte_count;
```

Kết quả hiển thị phụ thuộc `character_set_connection` của phiên. Với `utf8mb4`, chữ `á` thông thường là một ký tự Unicode nhưng chiếm hai byte UTF-8. Vì vậy `CHAR_LENGTH()` đếm ký tự còn `OCTET_LENGTH()` đếm byte.

## 2. So sánh chuỗi văn bản theo collation

Collation gắn với character set và chứa các quy tắc so sánh. MySQL 8.0 có các collation Unicode UCA 9.0 như `utf8mb4_0900_ai_ci` và `utf8mb4_0900_as_cs`.

Các hậu tố thường gặp:

- `ai`: accent-insensitive, không phân biệt dấu/diacritics trong phép so sánh.
- `as`: accent-sensitive, phân biệt dấu/diacritics.
- `ci`: case-insensitive, không phân biệt chữ hoa và chữ thường.
- `cs`: case-sensitive, phân biệt chữ hoa và chữ thường.
- `bin`: collation nhị phân của character set, sắp xếp theo giá trị mã ký tự; đây vẫn là collation của chuỗi ký tự.

Một số ví dụ kiểm tra trực tiếp:

```sql
SELECT
    _utf8mb4'An' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'an' COLLATE utf8mb4_0900_ai_ci AS same_case_insensitive,
    _utf8mb4'cafe' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'café' COLLATE utf8mb4_0900_ai_ci AS same_accent_insensitive,
    _utf8mb4'An' COLLATE utf8mb4_0900_as_cs =
        _utf8mb4'an' COLLATE utf8mb4_0900_as_cs AS same_case_sensitive,
    _utf8mb4'cafe' COLLATE utf8mb4_0900_as_cs =
        _utf8mb4'café' COLLATE utf8mb4_0900_as_cs AS same_accent_sensitive;
```

Với các collation UCA 9.0 nêu trên, hai phép so sánh đầu có thể trả về `1`, hai phép so sánh sau trả về `0`. Điều này cho thấy “bằng nhau” trong SQL là bằng nhau theo collation đang áp dụng, không nhất thiết là byte giống hệt.

Có thể thử trực tiếp với một cặp tiếng Việt:

```sql
SELECT
    _utf8mb4'hoa' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'hòa' COLLATE utf8mb4_0900_ai_ci AS accent_insensitive,
    _utf8mb4'hoa' COLLATE utf8mb4_0900_as_cs =
        _utf8mb4'hòa' COLLATE utf8mb4_0900_as_cs AS accent_sensitive;
```

Phép so sánh accent-insensitive bỏ qua trọng số dấu; phép so sánh accent-sensitive giữ khác biệt này. Hãy chạy trên phiên bản MySQL đích để xác nhận hành vi mà ứng dụng sẽ dựa vào.

### Bốn tổ hợp case và accent sensitivity

| Collation suffix | `A` so với `a` | `a` so với `á` | Trường hợp thường dùng |
|---|---|---|---|
| `_ai_ci` | Xem là bằng nhau | Xem là bằng nhau theo trọng số accent | Tìm kiếm thân thiện, không muốn người dùng phải nhập đúng hoa/thường và dấu. |
| `_as_ci` | Xem là bằng nhau | Phân biệt | Không phân biệt hoa/thường nhưng cần giữ khác biệt dấu. |
| `_ai_cs` | Phân biệt | Xem là bằng nhau theo trọng số accent | Cần phân biệt kiểu chữ nhưng bỏ qua dấu. |
| `_as_cs` | Phân biệt | Phân biệt | So sánh văn bản chặt chẽ hơn, cần giữ khác biệt hoa/thường và dấu. |

Không phải mọi character set hoặc phiên bản đều có đủ mọi tổ hợp collation. Hãy xem danh sách collation trên server thật bằng `SHOW COLLATION` hoặc `INFORMATION_SCHEMA.COLLATIONS`, rồi kiểm thử các trường hợp nghiệp vụ quan trọng.

## 3. Chuỗi nhị phân: so sánh đúng từng byte

Các kiểu `BINARY`, `VARBINARY` và họ `BLOB` lưu chuỗi nhị phân. MySQL so sánh các giá trị này theo byte, không áp dụng quy tắc case-insensitive hay accent-insensitive.

Ví dụ:

```sql
SELECT
    CAST(_utf8mb4'An' AS BINARY) =
        CAST(_utf8mb4'an' AS BINARY) AS same_bytes_case,
    CAST(_utf8mb4'a' AS BINARY) =
        CAST(_utf8mb4'á' AS BINARY) AS same_bytes_accent;
```

Hai kết quả đều là `0`, vì các chuỗi UTF-8 có byte khác nhau. `CAST(... AS BINARY)` được dùng ở đây để minh họa phép so sánh nhị phân; trong thiết kế schema, hãy chọn `BINARY`/`VARBINARY` nếu bản chất dữ liệu là byte thô.

Xem nội dung byte:

```sql
SELECT
    HEX(_utf8mb4'a') AS plain_a,
    HEX(_utf8mb4'á') AS accented_a,
    HEX(_utf8mb4'Á') AS uppercase_accented_a;
```

Chuỗi nhị phân phù hợp với digest, token opaque, khóa nhị phân hoặc payload mà mọi byte đều có ý nghĩa. Nó không phù hợp để thay thế kiểu văn bản cho tên người, địa chỉ hoặc nội dung cần sắp xếp theo ngôn ngữ.

### Collation `_bin` không giống kiểu `BINARY`

Hai khái niệm dễ bị nhầm:

- `VARCHAR(...) COLLATE utf8mb4_0900_bin` vẫn là cột văn bản. Nó có character set `utf8mb4`, chứa ký tự và dùng collation nhị phân của character set để so sánh.
- `VARBINARY(...)` là cột byte. Nó không có character set hoặc collation văn bản; phép so sánh dựa trên byte.

Nếu cần xử lý văn bản với quy tắc so sánh phân biệt theo mã ký tự, một collation `_bin` có thể phù hợp. Nếu cần bảo toàn byte tùy ý, dùng kiểu nhị phân.

## 4. Ký tự có dấu và tiếng Việt

Tiếng Việt sử dụng chữ cái có dấu nguyên âm và dấu thanh. Những ký tự như `a`, `ă`, `â`, `á`, `à`, `ả`, `ã`, `ạ` có thể mang ý nghĩa từ vựng khác nhau. Vì vậy, chọn collation không phân biệt dấu có tác động nghiệp vụ lớn hơn việc chỉ bỏ dấu trang trí.

Ví dụ, với collation accent-insensitive, các dạng `a` và `á` có thể so sánh bằng nhau. Điều đó có thể giúp ô tìm kiếm chấp nhận người dùng nhập không dấu, nhưng nếu dùng collation này làm unique key cho tên định danh, hệ thống có thể từ chối hai giá trị mà nghiệp vụ coi là khác nhau.

Hãy phân biệt hai nhu cầu:

1. **Tìm kiếm tiện lợi:** người dùng nhập `hoa` và mong tìm được `hòa`, `hóa` hoặc các biến thể phù hợp. Có thể dùng một cột tìm kiếm riêng, biểu thức chuẩn hóa hoặc collation không phân biệt dấu sau khi kiểm thử.
2. **Định danh và tính duy nhất:** hệ thống phải giữ khác biệt của tên, mã hoặc dữ liệu nghiệp vụ theo quy tắc chính xác. Chọn collation phân biệt dấu hoặc dùng khóa nhị phân/khóa chuẩn hóa được định nghĩa rõ.

Collation tổng quát UCA không nhất thiết phản ánh đúng thứ tự từ điển riêng của mọi ngôn ngữ. Nếu sản phẩm cần sắp xếp tiếng Việt theo quy tắc từ điển cụ thể, hãy kiểm tra danh sách locale-specific collation mà phiên bản MySQL hỗ trợ; nếu không có collation đáp ứng yêu cầu, cân nhắc xử lý thứ tự ở tầng ứng dụng hoặc xây dựng khóa sắp xếp riêng. Đừng giả định rằng mọi collation `utf8mb4_0900_*` đều có quy tắc riêng cho tiếng Việt.

### Ký tự dựng sẵn và ký tự tổ hợp

Một ký tự người dùng nhìn thấy có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng một ký tự cơ sở kết hợp với combining mark. Ví dụ chữ `é` có thể được mã hóa dưới dạng U+00E9 hoặc hai code point U+0065 và U+0301.

Hai chuỗi đó có thể trông giống nhau nhưng byte UTF-8 khác nhau. Collation Unicode có thể gán trọng số tương đương cho một số chuỗi tương đương chuẩn tắc, tùy phiên bản và quy tắc collation; điều đó không có nghĩa MySQL tự viết lại hoặc chuẩn hóa byte đã lưu. Nếu hệ thống cần một biểu diễn chuẩn duy nhất, hãy chuẩn hóa ở tầng ứng dụng theo một dạng Unicode được chọn (thường là NFC) trước khi lưu và kiểm thử lại với dữ liệu hiện có.

Có thể xem byte và độ dài của hai cách biểu diễn trong một phiên UTF-8:

```sql
SELECT
    HEX(_utf8mb4'é') AS composed_hex,
    HEX(_utf8mb4'é') AS decomposed_hex,
    OCTET_LENGTH(_utf8mb4'é') AS composed_bytes,
    OCTET_LENGTH(_utf8mb4'é') AS decomposed_bytes;
```

Trong dòng thứ hai, phần sau `e` là combining acute accent. Hãy sao chép cẩn thận hoặc tạo dữ liệu kiểm thử từ code point trong ứng dụng để tránh editor tự chuẩn hóa văn bản nguồn. Không dựa vào hình dạng hiển thị để xác định hai chuỗi có cùng byte hay không.

## 5. Khoảng trắng cuối và quy tắc PAD SPACE / NO PAD

Collation còn quyết định cách xử lý khoảng trắng ở cuối chuỗi. Một số collation có thuộc tính `PAD SPACE`: khi so sánh, chuỗi ngắn có thể được đệm khoảng trắng để so với chuỗi dài. Các collation `NO PAD` xem khoảng trắng cuối là một phần có ý nghĩa trong phép so sánh.

Nhiều collation cũ có quy tắc `PAD SPACE`, trong khi các collation UCA 9.0 có hậu tố `_0900_` của MySQL 8.0 thường là `NO PAD`. Không nên suy đoán chỉ từ tên chung; kiểm tra thuộc tính của collation cụ thể:

```sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    PAD_ATTRIBUTE
FROM information_schema.collations
WHERE COLLATION_NAME IN (
    'utf8mb4_general_ci',
    'utf8mb4_0900_ai_ci',
    'utf8mb4_0900_as_cs'
);
```

So sánh minh họa:

```sql
SELECT
    _utf8mb4'abc' COLLATE utf8mb4_general_ci =
        _utf8mb4'abc ' COLLATE utf8mb4_general_ci AS old_pad_space,
    _utf8mb4'abc' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'abc ' COLLATE utf8mb4_0900_ai_ci AS uca_no_pad;
```

Với các collation thông dụng nêu trên, phép so sánh đầu có thể xem hai chuỗi là bằng nhau do `PAD SPACE`; phép so sánh thứ hai phân biệt khoảng trắng cuối do `NO PAD`. Hãy xác minh trên đúng phiên bản MySQL vì danh sách collation và thuộc tính có thể khác.

Sự khác biệt này có thể ảnh hưởng unique index. Nếu một collation xem `abc` và `abc ` là bằng nhau, unique key có thể từ chối giá trị thứ hai. Nếu collation `NO PAD`, chúng có thể được xem là hai giá trị khác nhau. Cần quyết định khoảng trắng cuối là dữ liệu hợp lệ, bị cấm hay được chuẩn hóa trước khi lưu.

## 6. Collation tác động đến UNIQUE, JOIN, GROUP BY và ORDER BY

Collation không chỉ ảnh hưởng câu `SELECT` đơn giản. Nó có thể thay đổi hành vi của các ràng buộc và phép toán trên dữ liệu.

### Unique index và kiểm tra trùng lặp

```sql
CREATE TABLE usernames_ci_demo (
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (username)
) ENGINE=InnoDB;

INSERT INTO usernames_ci_demo (username) VALUES ('An');

-- Có thể bị lỗi duplicate key vì collation không phân biệt hoa/thường.
INSERT INTO usernames_ci_demo (username) VALUES ('an');
```

Unique index kiểm tra tính duy nhất theo quy tắc so sánh của collation trên cột. Nếu accent-insensitive, các từ khác dấu có thể xung đột. Trước khi chọn collation cho username, mã định danh hoặc email, hãy định nghĩa rõ chính sách hoa/thường, dấu, khoảng trắng và chuẩn hóa.

### JOIN và GROUP BY

Khi nối hai cột văn bản có collation tương thích, phép so sánh join sử dụng quy tắc collation của biểu thức. Nếu hai cột có collation khác nhau, MySQL có thể báo lỗi illegal mix of collations hoặc cần xác định quy tắc chuyển đổi phù hợp.

```sql
SELECT a.customer_code, b.customer_name
FROM source_a AS a
JOIN source_b AS b
  ON a.customer_code COLLATE utf8mb4_0900_as_cs =
     b.customer_code COLLATE utf8mb4_0900_as_cs;
```

Ví dụ ép collation tường minh giúp minh họa quy tắc so sánh, nhưng trong ứng dụng nên thiết kế hai cột dùng character set/collation thống nhất để tránh phải ép kiểu trong mọi truy vấn. `GROUP BY` và `DISTINCT` cũng gom các chuỗi theo quy tắc collation, nên số nhóm có thể thay đổi khi đổi collation.

### ORDER BY

```sql
SELECT display_name
FROM customers
ORDER BY display_name COLLATE utf8mb4_0900_ai_ci;
```

`ORDER BY` dùng trọng số collation để xác định thứ tự. Nếu cần thứ tự tiếng Việt đúng theo từ điển hoặc quy ước sản phẩm, phải kiểm thử bằng tập tên đại diện, bao gồm nguyên âm có dấu và dấu thanh. Một collation accent-insensitive có thể gom nhiều từ vào cùng trọng số ở cấp accent, do đó thứ tự có thể không đúng mong muốn.

## 7. Chọn collation cho dữ liệu thực tế

Không có một collation tốt nhất cho mọi cột. Hãy bắt đầu từ quy tắc nghiệp vụ của từng loại dữ liệu:

| Dữ liệu | Câu hỏi thiết kế | Hướng lựa chọn |
|---|---|---|
| Tên người, địa chỉ tiếng Việt | Có cần phân biệt dấu trong tìm kiếm? Thứ tự hiển thị phải theo quy tắc nào? | Dùng `utf8mb4`; chọn collation theo yêu cầu tìm kiếm và sắp xếp sau khi kiểm thử dữ liệu Việt. |
| Username | Có phân biệt hoa/thường? Có cho phép hai tên khác dấu? | Xác định chính sách định danh trước khi tạo unique index; có thể cần collation case-sensitive hoặc khóa chuẩn hóa riêng. |
| Email | Có chuẩn hóa chữ hoa/thường ở tầng ứng dụng không? | Định nghĩa chính sách so sánh rõ ràng; không mặc định mọi phần của email đều có cùng quy tắc theo mọi chuẩn. |
| Mã giao dịch hoặc external ID | Mỗi ký tự có ý nghĩa chính xác không? | Cân nhắc collation phân biệt hoa/thường hoặc `VARBINARY` nếu dữ liệu là byte opaque. |
| Token, digest, binary key | Có phải dãy byte chính xác? | Dùng `BINARY`/`VARBINARY`, không dùng collation văn bản. |
| Nội dung tìm kiếm không dấu | Có muốn bỏ qua dấu để tiện tra cứu? | Dùng collation accent-insensitive hoặc cột tìm kiếm phụ; vẫn giữ giá trị gốc để hiển thị và định danh. |

Đối với tiếng Việt, không nên mặc định dùng accent-insensitive cho mọi cột chỉ vì người dùng đôi khi tìm kiếm không dấu. Dấu có thể làm thay đổi nghĩa từ. Một thiết kế thường hữu ích là giữ cột gốc để lưu và hiển thị, sau đó tạo một cơ chế tìm kiếm riêng được chuẩn hóa theo nhu cầu sản phẩm.

## 8. Kiểm tra character set và collation trong MySQL

### Kiểm tra cấu hình server và session

```sql
SELECT
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation,
    @@character_set_database AS database_charset,
    @@collation_database AS database_collation,
    @@character_set_connection AS connection_charset,
    @@collation_connection AS connection_collation,
    @@character_set_client AS client_charset,
    @@character_set_results AS results_charset;
```

Các biến server/database là mặc định cho đối tượng mới hoặc ngữ cảnh tương ứng; chúng không tự động chứng minh charset/collation của mọi cột đã tồn tại. `character_set_database` và `collation_database` đã bị đánh dấu deprecated trong MySQL 8.0; dùng `SHOW CREATE DATABASE` để xem rõ default của schema. Các biến connection/client/results phản ánh phiên hiện tại và ảnh hưởng cách client gửi, server diễn giải và trả về chuỗi.

### Kiểm tra schema, bảng và cột

```sql
SHOW CREATE DATABASE learning_shop;
SHOW CREATE TABLE learning_shop.customers;
SHOW FULL COLUMNS FROM learning_shop.customers;
```

Hoặc truy vấn metadata:

```sql
SELECT
    table_name,
    column_name,
    character_set_name,
    collation_name,
    column_type
FROM information_schema.columns
WHERE table_schema = 'learning_shop'
  AND character_set_name IS NOT NULL
ORDER BY table_name, ordinal_position;
```

Để xem các collation có sẵn:

```sql
SHOW COLLATION WHERE Charset = 'utf8mb4';
```

Tên và thuộc tính collation phụ thuộc phiên bản. MySQL 8.0 có các collation UCA 9.0 như `utf8mb4_0900_ai_ci`; MySQL 5.7 không có nhóm `_0900_` này và thường dùng các collation cũ hơn như `utf8mb4_unicode_ci` hoặc `utf8mb4_general_ci`. Khi triển khai trên nhiều phiên bản, chọn collation được hỗ trợ ở tất cả môi trường hoặc lập kế hoạch nâng cấp tương ứng.

## 9. Literal, connection collation và ép collation trong truy vấn

Chuỗi literal không có introducer thường được diễn giải theo `character_set_connection` và `collation_connection` của session. Vì vậy, cùng một câu SQL có thể có hành vi khác nếu các phiên có cấu hình kết nối khác nhau.

Kiểm tra trước khi debug:

```sql
SELECT
    @@character_set_client,
    @@character_set_connection,
    @@collation_connection,
    @@character_set_results;
```

Có thể khai báo introducer cho literal UTF-8:

```sql
SELECT _utf8mb4'Tiếng Việt' COLLATE utf8mb4_0900_ai_ci;
```

`COLLATE` áp dụng quy tắc so sánh cho biểu thức chuỗi tương thích với character set của collation. Nó không chuyển byte từ charset này sang charset khác. Nếu cần chuyển character set, dùng `CONVERT(expr USING charset)` hoặc sửa cấu hình/đường truyền dữ liệu đúng cách.

Không nên rải `COLLATE` khắp truy vấn như cách chữa lâu dài cho schema không thống nhất. Hãy sửa cấu hình column/table/database hoặc chuẩn hóa cách bind tham số ở driver. Khi dùng prepared statement, kiểm tra driver gửi dữ liệu với character set phù hợp và tránh chuyển chuỗi qua encoding mặc định của hệ điều hành.

## 10. Index và hiệu năng khi đổi collation

Collation quyết định trọng số dùng để so sánh và sắp xếp, nên nó cũng ảnh hưởng cách index văn bản được xây dựng và sử dụng. Khi tạo index trên `VARCHAR`, index tuân theo collation của cột. Nếu đổi collation, thứ tự và tính bằng nhau có thể thay đổi; MySQL có thể cần dựng lại index.

Một số nguyên tắc:

- Giữ collation của cột phù hợp với điều kiện `WHERE`, `JOIN`, `ORDER BY` thường dùng.
- Tránh áp dụng hàm hoặc ép collation khác nhau trên cột được index trong mọi truy vấn nếu không cần thiết.
- Nếu cần hai cách tìm kiếm khác nhau, cân nhắc cột tìm kiếm phụ hoặc generated column được thiết kế rõ, sau đó tạo index tương ứng.
- Chạy `EXPLAIN` trước và sau khi đổi biểu thức hoặc collation để kiểm tra index được chọn.
- Kiểm tra dung lượng index và thời gian ghi sau khi đổi collation, nhất là với bảng lớn.

Ví dụ truy vấn có thể dùng index theo collation mặc định của cột:

```sql
EXPLAIN
SELECT id
FROM customers
WHERE display_name = 'Nguyễn An';
```

Nếu viết `WHERE display_name COLLATE ... = ...` với collation khác cột, optimizer có thể không dùng index hiện tại theo cùng cách. Cần xác minh bằng `EXPLAIN`; nếu truy vấn là đường đi quan trọng, hãy cân nhắc lưu một biểu diễn tìm kiếm phụ với collation phù hợp.

## 11. Thay đổi collation trên schema đang có dữ liệu

Thay đổi default collation của database chỉ ảnh hưởng đối tượng được tạo sau đó; nó không tự chuyển các cột hiện có. Để đổi bảng và chuyển dữ liệu văn bản sang character set/collation mới, có thể dùng:

```sql
ALTER TABLE customers
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_as_cs;
```

Lệnh này là ví dụ minh họa cho MySQL 8.0 có hỗ trợ collation nêu trên. Nó có thể chuyển đổi dữ liệu, dựng lại bảng và index, cần thời gian, I/O và dung lượng bổ sung. Hãy thử trên bản sao trước khi chạy ở môi trường thật.

Trước khi migration, kiểm tra:

1. Phiên bản MySQL ở dev, test, staging và production có hỗ trợ collation đích không.
2. Các cột văn bản nào sẽ bị chuyển đổi; cột binary không nên bị chuyển đổi như văn bản.
3. Unique index có thể phát sinh xung đột mới hay không, ví dụ `An` và `an` hoặc hai từ khác dấu trở thành bằng nhau.
4. Truy vấn `JOIN`, `GROUP BY`, `DISTINCT` và `ORDER BY` có thay đổi kết quả không.
5. Dung lượng index, thời gian dựng lại và mức độ khóa bảng trong phiên bản/cấu hình thực tế.
6. Có backup, kế hoạch rollback/restore và bước đối soát dữ liệu sau migration.

Có thể tìm các giá trị trùng theo collation đích trước khi tạo unique index hoặc đổi collation:

```sql
SELECT
    display_name COLLATE utf8mb4_0900_ai_ci AS comparison_key,
    COUNT(*) AS duplicate_count
FROM customers
GROUP BY display_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Truy vấn này gom các giá trị theo collation đích để phát hiện những chuỗi có thể trở thành trùng lặp. Với bảng lớn, chạy kiểm tra trên bản sao hoặc trong cửa sổ bảo trì phù hợp; kiểm tra thêm khóa ghép và các unique constraint khác.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `utf8mb4` tự quyết định phân biệt dấu hay hoa/thường | Kết quả so sánh không như mong muốn | Kiểm tra collation của cột và session. |
| Dùng `_ai_ci` cho mọi cột tiếng Việt | Các từ khác dấu có thể bị xem là bằng nhau và xung đột unique key | Chọn theo mục đích từng cột; tách tìm kiếm tiện lợi khỏi định danh. |
| Nghĩ collation `_bin` giống `VARBINARY` | Nhầm chuỗi ký tự với dữ liệu byte thô | Chọn kiểu dữ liệu theo bản chất dữ liệu. |
| Tin hai chuỗi trông giống nhau thì byte giống nhau | Bỏ sót khác biệt do Unicode composition hoặc encoding | Dùng `HEX()`, `OCTET_LENGTH()` và chuẩn hóa ở ứng dụng khi cần. |
| Đổi database default và nghĩ cột cũ đã đổi | Schema có nhiều collation khác nhau | Kiểm tra `information_schema.columns`; migration cột/bảng riêng khi cần. |
| Đổi collation mà không kiểm tra unique index | Migration có thể thất bại do duplicate key | Gom nhóm theo collation đích và xử lý xung đột trước. |
| Ép `COLLATE` khác nhau trong mọi truy vấn | Có thể mất khả năng dùng index hoặc gây lỗi mix collation | Chuẩn hóa schema và cấu hình driver. |
| Chọn collation tổng quát nhưng mong thứ tự từ điển tiếng Việt chính xác | Thứ tự tên có thể không theo quy ước sản phẩm | Kiểm thử bộ dữ liệu tiếng Việt và dùng quy tắc sắp xếp phù hợp. |

## 13. Bài tập thực hành

### Bài tập A — So sánh case và accent

1. Chạy các phép so sánh `An` với `an` dưới `utf8mb4_0900_ai_ci` và `utf8mb4_0900_as_cs`.
2. So sánh `hoa`, `hòa`, `hóa` và `hoà` dưới hai collation.
3. Ghi lại kết quả và giải thích ảnh hưởng của case/accent sensitivity.
4. So sánh cùng các chuỗi sau khi `CAST(... AS BINARY)`.

### Bài tập B — Unique index và khoảng trắng cuối

1. Tạo hai bảng có cùng cột `VARCHAR` nhưng collation khác nhau.
2. Tạo unique index trên cột.
3. Thử insert `An`, `an`, `cafe`, `café`, `abc` và `abc `.
4. Kiểm tra `PAD_ATTRIBUTE` của từng collation.
5. Giải thích vì sao một số insert bị duplicate key.

### Bài tập C — Unicode composition

1. Tạo hai chuỗi `é` dựng sẵn và `e` cộng combining acute accent.
2. So sánh `HEX()`, `OCTET_LENGTH()` và `CHAR_LENGTH()`.
3. So sánh dưới collation Unicode và dưới `CAST(... AS BINARY)`.
4. Thử chuẩn hóa NFC ở tầng ứng dụng rồi so sánh byte trước/sau.
5. Ghi rõ collation có thể so sánh tương đương nhưng không tự chuẩn hóa dữ liệu lưu trữ.

### Bài tập D — Migration collation

1. Tạo bảng tên người với collation hiện tại và một unique index.
2. Chèn dữ liệu có khác biệt chữ hoa/thường và dấu.
3. Chạy truy vấn nhóm theo collation đích để tìm xung đột.
4. Đề xuất cách xử lý dữ liệu trùng trước migration.
5. Chạy `EXPLAIN` cho truy vấn tìm kiếm trước và sau khi chuyển trên môi trường thử nghiệm.

Bạn hoàn thành bài khi có thể giải thích sự khác nhau giữa byte, character set và collation; dự đoán kết quả so sánh theo case/accent sensitivity; hiểu tác động của PAD SPACE/NO PAD; lựa chọn collation cho dữ liệu tiếng Việt; và đánh giá rủi ro của unique index cùng migration.

## 14. Nguyên tắc cần ghi nhớ

- Character set quyết định cách mã hóa ký tự thành byte; collation quyết định cách so sánh và sắp xếp chuỗi văn bản.
- `utf8mb4` hỗ trợ Unicode đầy đủ nhưng không tự quyết định chính sách phân biệt hoa/thường hoặc dấu.
- `_ai_ci` bỏ qua khác biệt accent và case; `_as_cs` phân biệt cả hai trong các collation hỗ trợ hậu tố này.
- `BINARY`/`VARBINARY` so sánh byte; collation `_bin` vẫn thuộc chuỗi ký tự.
- Dữ liệu tiếng Việt cần được kiểm thử với dấu nguyên âm và dấu thanh; tìm kiếm không dấu không đồng nghĩa định danh không dấu.
- Hai chuỗi Unicode có thể hiển thị giống nhau nhưng có byte khác nhau; collation không tự chuẩn hóa byte đã lưu.
- PAD SPACE và NO PAD ảnh hưởng so sánh khoảng trắng cuối và tính duy nhất của index.
- Đổi collation có thể thay đổi kết quả truy vấn, unique key và cấu trúc index; luôn kiểm tra xung đột và thử migration trước.

Khi phân biệt được so sánh theo byte với so sánh theo collation, bạn có thể thiết kế dữ liệu văn bản và dữ liệu nhị phân chính xác hơn, tránh lỗi trùng lặp và tìm kiếm sai, đồng thời giữ hành vi nhất quán giữa các môi trường MySQL.
