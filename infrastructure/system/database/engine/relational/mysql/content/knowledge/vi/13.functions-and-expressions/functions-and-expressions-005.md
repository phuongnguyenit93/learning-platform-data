# LENGTH, CHAR_LENGTH và dữ liệu nhiều byte

Trong MySQL, một chuỗi có thể chiếm nhiều byte dù chỉ hiển thị một ký tự. Ví dụ chữ `á` trong UTF-8 thường chiếm hai byte, một ký tự CJK có thể chiếm ba byte và một emoji ngoài BMP chiếm bốn byte. Vì vậy, khi đo độ dài chuỗi, cần phân biệt **số byte** với **số ký tự**. `LENGTH()` trả về số byte; `CHAR_LENGTH()` trả về số ký tự theo cách MySQL diễn giải chuỗi và character set.

Sự khác biệt này ảnh hưởng tới kiểm tra dữ liệu đầu vào, giới hạn cột `VARCHAR`, kích thước truyền qua mạng, index, import/export và xử lý văn bản tiếng Việt. Nếu dùng `LENGTH()` để kiểm tra giới hạn ký tự, ứng dụng có thể từ chối chuỗi hợp lệ; nếu dùng `CHAR_LENGTH()` để ước lượng dung lượng byte, ứng dụng có thể đánh giá thiếu kích thước thực tế.

Trong module `DATABASE_MYSQL`, bài học này giúp bạn hiểu các hàm đo độ dài, kiểm tra dữ liệu nhiều byte và chọn đúng phép đo theo mục đích. Trọng tâm là `LENGTH()`, `CHAR_LENGTH()`, các hàm liên quan, character set và cách áp dụng trong schema cũng như ứng dụng.

## 1. Byte và ký tự là hai đại lượng khác nhau

Máy tính lưu văn bản dưới dạng byte. Character set quy định cách ánh xạ ký tự sang byte và ngược lại. Với UTF-8, một code point Unicode có thể cần từ một đến bốn byte. Do đó, độ dài byte không nhất thiết bằng số ký tự.

Ví dụ với `utf8mb4`:

| Nội dung | Số ký tự Unicode | Số byte UTF-8 thường gặp | Giải thích |
|---|---:|---:|---|
| `A` | 1 | 1 | Ký tự ASCII. |
| `á` | 1 | 2 | Ký tự Latin có dấu trong dạng dựng sẵn. |
| `中` | 1 | 3 | Ký tự CJK. |
| `😀` | 1 | 4 | Code point ngoài BMP. |

Đây là số liệu cho từng chuỗi ở dạng Unicode tương ứng. Nếu cùng một hình dạng được biểu diễn bằng một ký tự dựng sẵn hoặc một ký tự cơ sở cộng dấu kết hợp (combining mark), số code point và số byte có thể khác.

### Character set quyết định cách đọc byte

`utf8mb4` là character set UTF-8 đầy đủ của MySQL, hỗ trợ tối đa bốn byte cho một code point. Tên `utf8` trong MySQL historically là alias của `utf8mb3`, chỉ hỗ trợ tối đa ba byte và không thể lưu mọi ký tự Unicode, chẳng hạn nhiều emoji. Với schema mới cần Unicode đầy đủ, ưu tiên khai báo `utf8mb4` tường minh.

Kiểm tra character set của session:

```sql
SELECT
    @@character_set_client AS client_charset,
    @@character_set_connection AS connection_charset,
    @@character_set_results AS results_charset,
    @@collation_connection AS connection_collation;
```

Các biến này cho biết client gửi dữ liệu bằng character set nào, server dùng character set nào để xử lý literal/biểu thức và kết quả được chuyển về client theo character set nào. Nếu driver cấu hình sai, dữ liệu có thể bị chuyển mã sai trước khi `LENGTH()` hoặc `CHAR_LENGTH()` được thực thi.

## 2. `LENGTH()` đo số byte

Cú pháp:

```sql
LENGTH(str)
```

`LENGTH()` trả về độ dài của chuỗi tính bằng byte. Nó là synonym của `OCTET_LENGTH()`.

```sql
SELECT
    LENGTH(_utf8mb4'A') AS ascii_bytes,
    LENGTH(_utf8mb4'á') AS vietnamese_bytes,
    LENGTH(_utf8mb4'中') AS cjk_bytes,
    LENGTH(_utf8mb4'😀') AS emoji_bytes;
```

Với các literal được diễn giải đúng bằng `utf8mb4`, kết quả thường lần lượt là `1`, `2`, `3`, `4`. Đây là phép đo hữu ích khi cần biết số byte của chuỗi sau khi mã hóa theo character set đang áp dụng.

`LENGTH()` thường được dùng khi:

- Kiểm tra kích thước payload theo byte.
- Đối chiếu giới hạn truyền dữ liệu hoặc định dạng giao thức.
- Ước lượng dung lượng byte của giá trị chuỗi.
- Kiểm tra dữ liệu nhị phân hoặc chuỗi đã mã hóa.
- Phân tích vì sao một chuỗi có số byte lớn hơn số ký tự.

### `OCTET_LENGTH()` là tên diễn đạt rõ mục đích

```sql
SELECT
    LENGTH(_utf8mb4'Xin chào') AS length_bytes,
    OCTET_LENGTH(_utf8mb4'Xin chào') AS octet_length_bytes;
```

Hai kết quả bằng nhau. Khi đọc SQL, `OCTET_LENGTH()` có thể làm rõ rằng phép đo là byte/octet; `LENGTH()` ngắn gọn và phổ biến hơn. Chọn cách viết nhất quán trong dự án.

### `BIT_LENGTH()` đo số bit

```sql
SELECT
    LENGTH(_utf8mb4'á') AS bytes,
    OCTET_LENGTH(_utf8mb4'á') AS octets,
    BIT_LENGTH(_utf8mb4'á') AS bits;
```

Với chuỗi hai byte, `BIT_LENGTH()` trả về 16 bit. Đây là độ dài bit của biểu diễn byte, không phải số bit thông tin hay số ký tự.

## 3. `CHAR_LENGTH()` đo số ký tự

Cú pháp:

```sql
CHAR_LENGTH(str)
```

`CHAR_LENGTH()` trả về số ký tự trong chuỗi theo character set của chuỗi. `CHARACTER_LENGTH()` là synonym của hàm này.

```sql
SELECT
    CHAR_LENGTH(_utf8mb4'A') AS ascii_chars,
    CHAR_LENGTH(_utf8mb4'á') AS vietnamese_chars,
    CHAR_LENGTH(_utf8mb4'中') AS cjk_chars,
    CHAR_LENGTH(_utf8mb4'😀') AS emoji_chars;
```

Với các chuỗi ví dụ trên, mỗi giá trị có một code point nên `CHAR_LENGTH()` trả về `1`, dù số byte khác nhau.

`CHAR_LENGTH()` phù hợp khi:

- Kiểm tra số ký tự người dùng nhập so với giới hạn nghiệp vụ.
- Đếm độ dài văn bản theo character set.
- Xác định vị trí hoặc số ký tự cần xử lý trong chuỗi văn bản.
- Kiểm tra dữ liệu có vượt giới hạn ký tự của một trường hay không.

Không nên hiểu `CHAR_LENGTH()` là số ký tự người dùng nhìn thấy theo cách đếm từ/ngữ âm. Hàm đếm ký tự theo cách MySQL xử lý chuỗi Unicode; nó không đếm grapheme cluster (cụm ký tự hiển thị) hoặc ký tự ngôn ngữ theo nhận thức của người dùng.

## 4. So sánh `LENGTH()` và `CHAR_LENGTH()` trực tiếp

Chạy truy vấn sau để quan sát cùng một chuỗi:

```sql
SELECT
    _utf8mb4'Xin chào 😀' AS sample_text,
    LENGTH(_utf8mb4'Xin chào 😀') AS byte_length,
    OCTET_LENGTH(_utf8mb4'Xin chào 😀') AS octet_length,
    CHAR_LENGTH(_utf8mb4'Xin chào 😀') AS character_length,
    BIT_LENGTH(_utf8mb4'Xin chào 😀') AS bit_length;
```

Với `utf8mb4`, dấu cách và các ký tự ASCII thường chiếm một byte; các chữ tiếng Việt có dấu và emoji có thể chiếm nhiều byte. `CHAR_LENGTH()` đếm mỗi code point theo một đơn vị ký tự, còn `LENGTH()` cộng số byte mã hóa.

Có thể tạo bảng so sánh để kiểm tra từng trường hợp:

```sql
SELECT
    sample,
    HEX(sample) AS encoded_hex,
    LENGTH(sample) AS bytes,
    CHAR_LENGTH(sample) AS characters
FROM (
    SELECT _utf8mb4'A' AS sample
    UNION ALL SELECT _utf8mb4'á'
    UNION ALL SELECT _utf8mb4'中'
    UNION ALL SELECT _utf8mb4'😀'
    UNION ALL SELECT _utf8mb4'Xin chào'
) AS samples;
```

`HEX()` giúp nhìn thấy byte thực tế thay vì chỉ dựa vào cách terminal hoặc công cụ quản trị hiển thị ký tự. Đây là cách kiểm tra hữu ích khi điều tra lỗi encoding.

## 5. Ký tự dựng sẵn và dấu kết hợp: một hình dạng có thể có nhiều code point

Unicode có thể biểu diễn một chữ có dấu theo nhiều cách. Chẳng hạn, chữ `á` có thể được mã hóa bằng một code point dựng sẵn U+00E1, hoặc bằng chữ `a` U+0061 cộng combining acute accent U+0301.

Hai cách biểu diễn có thể trông giống nhau nhưng số byte và số code point khác nhau. Có thể tạo chúng bằng hex để tránh editor tự chuẩn hóa literal:

```sql
SELECT
    CONVERT(X'C3A1' USING utf8mb4) AS composed_text,
    CONVERT(X'61CC81' USING utf8mb4) AS decomposed_text,
    HEX(CONVERT(X'C3A1' USING utf8mb4)) AS composed_hex,
    HEX(CONVERT(X'61CC81' USING utf8mb4)) AS decomposed_hex,
    LENGTH(CONVERT(X'C3A1' USING utf8mb4)) AS composed_bytes,
    LENGTH(CONVERT(X'61CC81' USING utf8mb4)) AS decomposed_bytes,
    CHAR_LENGTH(CONVERT(X'C3A1' USING utf8mb4)) AS composed_chars,
    CHAR_LENGTH(CONVERT(X'61CC81' USING utf8mb4)) AS decomposed_chars;
```

Kết quả điển hình:

| Biểu diễn | Byte hex | Số byte | Số code point |
|---|---|---:|---:|
| `á` dựng sẵn | `C3A1` | 2 | 1 |
| `a` + dấu sắc kết hợp | `61CC81` | 3 | 2 |

`CHAR_LENGTH()` đếm các code point theo chuỗi, không gộp một ký tự cơ sở và combining mark thành một grapheme cluster. Nếu yêu cầu giao diện là giới hạn số ký tự người dùng cảm nhận, cần xử lý grapheme cluster ở tầng ứng dụng bằng thư viện Unicode phù hợp.

## 6. Emoji và chuỗi nhiều code point

Một emoji đơn giản có thể là một code point bốn byte trong `utf8mb4`. Nhưng nhiều biểu tượng người dùng nhìn thấy như một ký tự có thể được ghép từ nhiều code point: emoji có màu da, cờ, gia đình hoặc chuỗi có zero-width joiner (ZWJ).

Ví dụ một chuỗi gia đình có thể chứa các code point người, ZWJ và các thành viên gia đình. `CHAR_LENGTH()` có thể trả về số code point trong chuỗi, lớn hơn số biểu tượng nhìn thấy; `LENGTH()` trả về tổng byte UTF-8. Vì số code point của emoji phức hợp phụ thuộc chính xác chuỗi được nhập, không nên hard-code một con số chung cho mọi cách biểu diễn emoji.

Khi giới hạn độ dài nội dung do người dùng nhập:

- Nếu quy tắc nghiệp vụ định nghĩa độ dài theo code point, `CHAR_LENGTH()` là phép đo phù hợp trong MySQL.
- Nếu quy tắc giao diện định nghĩa theo grapheme cluster, kiểm tra ở tầng ứng dụng bằng thư viện Unicode.
- Nếu cần giới hạn payload hoặc byte gửi qua mạng, dùng `LENGTH()`/`OCTET_LENGTH()`.
- Nếu dữ liệu có thể chứa emoji, dùng `utf8mb4`; `utf8mb3` không lưu được mọi code point này.

## 7. `VARCHAR(n)` giới hạn ký tự, không phải số byte

Với cột `VARCHAR(n)`, `n` biểu thị số ký tự tối đa theo character set của cột. Nó không có nghĩa cột chỉ chiếm tối đa `n` byte. Với `utf8mb4`, một ký tự có thể cần tối đa bốn byte, vì vậy `VARCHAR(100)` có thể cần tới khoảng 400 byte cho phần dữ liệu ký tự, chưa tính phần lưu độ dài và overhead hàng.

Ví dụ:

```sql
CREATE TABLE customer_profiles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    display_name VARCHAR(100)
        CHARACTER SET utf8mb4
        NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`display_name` cho phép tối đa 100 ký tự theo character set. Một chuỗi có 100 ký tự tiếng Việt hoặc emoji có thể có số byte lớn hơn 100. Ngoài giới hạn cột, tổng kích thước hàng, giới hạn index, row format và các giới hạn server vẫn có thể ảnh hưởng khả năng lưu trữ.

### Metadata cho độ dài ký tự và độ dài byte tối đa

`INFORMATION_SCHEMA.COLUMNS` cung cấp hai thông tin hữu ích:

- `CHARACTER_MAXIMUM_LENGTH`: độ dài tối đa theo ký tự.
- `CHARACTER_OCTET_LENGTH`: độ dài tối đa theo byte/octet.

```sql
SELECT
    column_name,
    data_type,
    character_set_name,
    collation_name,
    character_maximum_length,
    character_octet_length
FROM information_schema.columns
WHERE table_schema = 'learning_shop'
  AND table_name = 'customer_profiles'
  AND column_name = 'display_name';
```

Với `VARCHAR(100)` dùng `utf8mb4`, metadata thường cho thấy tối đa 100 ký tự và tối đa 400 byte cho dữ liệu ký tự. Giá trị byte tối đa không phải cam kết rằng mọi hàng sẽ chiếm đúng số byte đó.

## 8. `CHAR`, `VARCHAR`, `TEXT` và dữ liệu nhiều byte

Các kiểu chuỗi văn bản có quy tắc lưu trữ khác nhau:

| Kiểu | Đặc điểm độ dài | Ghi nhớ khi đo |
|---|---|---|
| `CHAR(n)` | Độ dài khai báo cố định theo ký tự; giá trị được đệm khoảng trắng theo quy tắc kiểu | Việc đọc lại có thể loại bỏ khoảng trắng cuối tùy mode/phiên bản; kiểm tra thực tế khi cần đo padding. |
| `VARCHAR(n)` | Độ dài biến đổi, tối đa `n` ký tự | `CHAR_LENGTH()` đo ký tự; `LENGTH()` đo byte của giá trị. |
| `TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | Văn bản biến đổi với giới hạn dung lượng khác nhau | Byte phụ thuộc character set và nội dung; xem thêm giới hạn row/packet. |

Với `VARCHAR`, khoảng trắng cuối là một phần giá trị và được tính trong phép đo độ dài. Với `CHAR`, MySQL có quy tắc padding và có thể loại bỏ khoảng trắng cuối khi đọc giá trị; `PAD_CHAR_TO_FULL_LENGTH` từng ảnh hưởng cách trả về nhưng không nên dựa vào mode này làm hợp đồng ứng dụng. Nếu cần bảo toàn chính xác khoảng trắng cuối, hãy chọn kiểu phù hợp và kiểm thử hành vi của phiên bản đang dùng.

Đừng suy ra số byte vật lý trên đĩa chỉ từ `LENGTH(column)`. InnoDB còn có metadata hàng, page layout, compression, index và các cơ chế lưu trữ khác. `LENGTH()` đo byte của giá trị chuỗi ở cấp SQL, không phải dung lượng vật lý chính xác mà hàng chiếm trong tablespace.

## 9. `BINARY` và `VARBINARY` là dữ liệu byte

`BINARY(n)` và `VARBINARY(n)` lưu chuỗi nhị phân thay vì văn bản theo character set. Chúng phù hợp với digest, token, mã byte hoặc payload opaque.

- `BINARY(n)` có độ dài cố định; giá trị ngắn được đệm bên phải bằng byte zero (`0x00`).
- `VARBINARY(n)` giữ độ dài byte thực tế và không tự đệm tới `n`.

Với dữ liệu nhị phân, dùng `LENGTH()`/`OCTET_LENGTH()` để đo số byte và `HEX()` để quan sát nội dung. Không dùng `CHAR_LENGTH()` để diễn giải số ký tự người dùng vì chuỗi byte không nhất thiết là văn bản hợp lệ.

```sql
SELECT
    HEX(X'410042') AS binary_hex,
    LENGTH(X'410042') AS binary_bytes,
    BIT_LENGTH(X'410042') AS binary_bits;
```

Kết quả cho biết chuỗi gồm ba byte, trong đó byte giữa là `0x00`. Khi bind từ Java, dùng `byte[]`, `PreparedStatement.setBytes()` và `ResultSet.getBytes()` thay vì chuyển tùy tiện qua `String`.

## 10. `LENGTH()` và `CHAR_LENGTH()` khi giá trị là NULL hoặc rỗng

Hai hàm trả về `NULL` khi đối số là SQL `NULL`:

```sql
SELECT
    LENGTH(NULL) AS null_bytes,
    CHAR_LENGTH(NULL) AS null_chars,
    LENGTH('') AS empty_bytes,
    CHAR_LENGTH('') AS empty_chars;
```

Kết quả:

| Biểu thức | Kết quả |
|---|---:|
| `LENGTH(NULL)` | `NULL` |
| `CHAR_LENGTH(NULL)` | `NULL` |
| `LENGTH('')` | 0 |
| `CHAR_LENGTH('')` | 0 |

Không nhầm chuỗi rỗng với NULL. Nếu cần kiểm tra cột chưa có nội dung, có thể cần kiểm tra cả hai trạng thái:

```sql
SELECT id
FROM customer_profiles
WHERE display_name IS NULL
   OR CHAR_LENGTH(display_name) = 0;
```

Nếu khoảng trắng cũng được xem là không có nội dung, quy tắc phải được nói rõ. Có thể dùng `TRIM()` cho khoảng trắng ASCII thông thường, nhưng xử lý mọi loại Unicode whitespace cần logic phù hợp ở tầng ứng dụng hoặc biểu thức chuyên biệt.

## 11. Kiểm tra độ dài đầu vào theo đúng yêu cầu

Trước khi viết điều kiện, hãy hỏi giới hạn đang nói về điều gì:

| Yêu cầu | Phép đo phù hợp |
|---|---|
| Tối đa 80 ký tự trong trường tên hiển thị | `CHAR_LENGTH(value) <= 80` |
| Payload không vượt 1.024 byte | `LENGTH(value) <= 1024` |
| Dữ liệu văn bản không vượt 2.000 code point | `CHAR_LENGTH(value) <= 2000` |
| Dữ liệu nhị phân không vượt 64 byte | `LENGTH(binary_value) <= 64` |
| Kiểm tra giới hạn lưu trữ theo metadata cột | `CHARACTER_MAXIMUM_LENGTH` và `CHARACTER_OCTET_LENGTH` |

Ví dụ kiểm tra dữ liệu trước khi insert:

```sql
SET @display_name = _utf8mb4'Nguyễn Minh An';

SELECT
    CHAR_LENGTH(@display_name) AS characters,
    LENGTH(@display_name) AS bytes,
    CHAR_LENGTH(@display_name) <= 100 AS within_character_limit,
    LENGTH(@display_name) <= 400 AS within_example_byte_budget;
```

Giới hạn byte `400` ở ví dụ chỉ là ngân sách minh họa cho tối đa 100 ký tự `utf8mb4`; giới hạn nghiệp vụ và giới hạn schema phải được định nghĩa riêng. Không dùng phép kiểm tra byte để thay cho giới hạn ký tự nếu sản phẩm yêu cầu số ký tự.

### Ràng buộc ở database và validation ở ứng dụng

Ứng dụng nên kiểm tra đầu vào sớm để đưa thông báo thân thiện cho người dùng. Database vẫn cần định nghĩa kiểu dữ liệu và giới hạn phù hợp để bảo vệ dữ liệu trước mọi client. Nếu cần constraint về độ dài, có thể dùng `CHECK` trên phiên bản hỗ trợ và kiểm thử:

```sql
CREATE TABLE product_labels (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(100) CHARACTER SET utf8mb4 NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_product_label_chars
        CHECK (CHAR_LENGTH(label) <= 100)
) ENGINE=InnoDB;
```

Trong ví dụ này, `VARCHAR(100)` đã giới hạn số ký tự tối đa; `CHECK` minh họa cách diễn đạt quy tắc rõ ràng. Không cần thêm constraint trùng lặp nếu nó không tăng giá trị kiểm soát. Hãy kiểm tra phiên bản MySQL vì khả năng thực thi `CHECK` khác nhau giữa các phiên bản cũ và mới.

## 12. Kiểm tra dữ liệu nhiều byte trong schema hiện có

Để xác minh một cột đang dùng character set nào và độ dài tối đa ra sao, truy vấn metadata:

```sql
SELECT
    table_name,
    column_name,
    column_type,
    character_set_name,
    collation_name,
    character_maximum_length,
    character_octet_length
FROM information_schema.columns
WHERE table_schema = 'learning_shop'
  AND character_set_name IS NOT NULL
ORDER BY table_name, ordinal_position;
```

Với một giá trị cụ thể, kiểm tra cùng lúc nội dung, byte và ký tự:

```sql
SELECT
    display_name,
    HEX(display_name) AS encoded_hex,
    LENGTH(display_name) AS bytes,
    OCTET_LENGTH(display_name) AS octets,
    CHAR_LENGTH(display_name) AS characters
FROM customer_profiles
WHERE id = 1;
```

Nếu chuỗi hiển thị sai nhưng `HEX()` khác với byte UTF-8 mong đợi, cần kiểm tra đường truyền encoding từ client, connection, cột và dữ liệu import. Đổi collation không tự sửa byte đã bị lưu sai encoding.

## 13. Ảnh hưởng tới index và hiệu năng

`LENGTH()` và `CHAR_LENGTH()` thường được dùng trong biểu thức. Nếu áp dụng hàm lên cột trong `WHERE`, optimizer có thể không sử dụng index B-tree thông thường trên cột đó như khi so sánh trực tiếp.

Ví dụ:

```sql
-- Điều kiện theo giá trị trực tiếp thường thân thiện với index hơn
SELECT id
FROM customer_profiles
WHERE display_name = _utf8mb4'Nguyễn Minh An';

-- Hàm trên cột có thể cần tính cho từng hàng
SELECT id
FROM customer_profiles
WHERE CHAR_LENGTH(display_name) > 80;
```

Nếu truy vấn tìm chuỗi vượt một giới hạn là workload thường xuyên, hãy đo bằng `EXPLAIN` và cân nhắc generated column được index hoặc lưu thuộc tính đã tính nếu có lý do rõ ràng. Không thêm index chỉ để tối ưu một truy vấn hiếm khi chưa đo.

Độ dài byte cũng ảnh hưởng index key. Với `utf8mb4`, một ký tự có thể chiếm tối đa bốn byte; index trên cột văn bản dài có thể gặp giới hạn key length tùy phiên bản, InnoDB page size và cấu hình. Khi tạo unique index hoặc composite index trên các cột `VARCHAR`, cần tính đến kích thước byte tối đa chứ không chỉ số ký tự khai báo.

Ví dụ kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT id
FROM customer_profiles
WHERE display_name = _utf8mb4'Nguyễn Minh An';
```

So sánh với truy vấn có `CHAR_LENGTH()` trên cột và xem `key`, `type`, `rows` trong kết quả. Optimizer có thể chọn table scan nếu bảng nhỏ hoặc điều kiện không chọn lọc; hãy thử trên dữ liệu đại diện.

## 14. Làm việc với dữ liệu nhiều byte từ ứng dụng Java

Trong Java, `String.length()` trả về số UTF-16 code unit, không phải số byte UTF-8 và cũng không luôn bằng số code point. Vì vậy, nó không tương đương trực tiếp với MySQL `CHAR_LENGTH()` đối với mọi ký tự ngoài BMP.

Các phép đo trong Java:

```java
import java.nio.charset.StandardCharsets;

String value = "Xin chào 😀";

int utf16CodeUnits = value.length();
int codePoints = value.codePointCount(0, value.length());
int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;
```

- `value.length()` đếm UTF-16 code unit.
- `codePointCount()` đếm Unicode code point.
- `getBytes(UTF_8).length` đếm số byte sau khi mã hóa UTF-8.

Với chuỗi tiếng Việt dựng sẵn thông thường, số UTF-16 code unit và code point có thể trùng nhau; với emoji ngoài BMP, một code point chiếm hai UTF-16 code unit. Với chuỗi có combining mark, số code point có thể lớn hơn số grapheme cluster mà người dùng nhìn thấy.

Khi cần kiểm tra giới hạn tương ứng với MySQL:

- So sánh với `CHAR_LENGTH()` của chuỗi văn bản `utf8mb4`: dùng số code point trong Java và bảo đảm hai bên áp dụng cùng quy ước chuẩn hóa.
- So sánh với `LENGTH()` của chuỗi `utf8mb4`: dùng số byte sau khi encode UTF-8.
- Nếu quy tắc sản phẩm tính grapheme cluster: dùng thư viện Unicode ở ứng dụng; không dùng `String.length()` hoặc `CHAR_LENGTH()` như một phép đo giao diện.

### Truyền dữ liệu bằng JDBC

Với cột văn bản, dùng `setString()` và cấu hình Connector/J để trao đổi `utf8mb4` đúng cách. Với dữ liệu byte, dùng `setBytes()`.

```java
String sql = "INSERT INTO customer_profiles (display_name) VALUES (?)";

try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement(sql)) {
    statement.setString(1, "Nguyễn Minh An 😀");
    statement.executeUpdate();
}
```

Sau khi ghi, có thể kiểm tra ở MySQL:

```sql
SELECT
    CHAR_LENGTH(display_name) AS characters,
    LENGTH(display_name) AS bytes,
    HEX(display_name) AS encoded_hex
FROM customer_profiles
ORDER BY id DESC
LIMIT 1;
```

Nếu số byte hoặc ký tự không đúng mong đợi, hãy xác minh character set của cột và cấu hình connection trước khi sửa dữ liệu. Tránh tự chuyển `String` qua charset mặc định của hệ điều hành.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `LENGTH()` để giới hạn số ký tự | Chuỗi tiếng Việt/emoji hợp lệ bị từ chối vì chiếm nhiều byte | Dùng `CHAR_LENGTH()` cho giới hạn ký tự. |
| Dùng `CHAR_LENGTH()` để giới hạn payload byte | Dữ liệu có thể vượt ngân sách truyền tải | Dùng `LENGTH()` hoặc `OCTET_LENGTH()`. |
| Nghĩ `VARCHAR(n)` là tối đa `n` byte | Đánh giá sai dung lượng và giới hạn hàng/index | `n` là số ký tự; xem thêm `CHARACTER_OCTET_LENGTH`. |
| Nghĩ một emoji luôn là một grapheme và một code point | Đếm thiếu chuỗi emoji phức hợp | Phân biệt code point với grapheme cluster. |
| Dùng `utf8` mà nghĩ hỗ trợ mọi Unicode | Không lưu được một số code point ngoài BMP | Dùng `utf8mb4` cho Unicode đầy đủ. |
| Chỉ nhìn ký tự hiển thị khi debug encoding | Bỏ sót byte sai hoặc Unicode composition khác nhau | Dùng `HEX()`, `LENGTH()` và `CHAR_LENGTH()`. |
| Dùng `String.length()` như số ký tự MySQL | Sai với một số ký tự ngoài BMP | Dùng `codePointCount()` và byte UTF-8 khi đối chiếu. |
| Coi `LENGTH(column)` là dung lượng vật lý trên đĩa | Đánh giá sai kích thước tablespace/index | Phân biệt độ dài giá trị với storage overhead và page layout. |
| Dùng hàm trên cột trong mọi điều kiện lọc | Có thể làm giảm khả năng dùng index | Đo bằng `EXPLAIN`, cân nhắc generated column nếu cần. |

## 16. Bài tập thực hành

### Bài tập A — Đo chuỗi ASCII và UTF-8

1. Chạy `LENGTH()` và `CHAR_LENGTH()` với `A`, `á`, `中` và `😀`.
2. Ghi lại `HEX()` của từng giá trị.
3. Giải thích vì sao số byte khác số ký tự.
4. Lặp lại với một chuỗi tiếng Việt dài như `Xin chào Việt Nam`.

### Bài tập B — Unicode composition

1. Tạo chữ `á` dựng sẵn từ `X'C3A1'`.
2. Tạo dạng `a` cộng dấu sắc từ `X'61CC81'`.
3. So sánh `HEX()`, `LENGTH()` và `CHAR_LENGTH()`.
4. Giải thích vì sao hai chuỗi nhìn giống nhau nhưng có số code point và byte khác nhau.

### Bài tập C — Metadata và giới hạn cột

1. Tạo bảng có `VARCHAR(100) CHARACTER SET utf8mb4`.
2. Đọc `CHARACTER_MAXIMUM_LENGTH` và `CHARACTER_OCTET_LENGTH` từ `INFORMATION_SCHEMA.COLUMNS`.
3. Chèn chuỗi gồm ASCII, tiếng Việt có dấu và emoji.
4. So sánh số ký tự với số byte của từng hàng.

### Bài tập D — Đối chiếu Java và MySQL

1. Trong Java, tính `String.length()`, `codePointCount()` và số byte UTF-8.
2. Ghi chuỗi qua JDBC `setString()`.
3. Đọc lại bằng `CHAR_LENGTH()`, `LENGTH()` và `HEX()`.
4. Thử emoji ngoài BMP và chuỗi có combining mark.
5. Giải thích sự khác nhau giữa UTF-16 code unit, code point, byte và grapheme cluster.

### Bài tập E — Kiểm tra index

1. Tạo index trên `display_name`.
2. Chạy `EXPLAIN` cho điều kiện so sánh trực tiếp.
3. Chạy `EXPLAIN` cho điều kiện `CHAR_LENGTH(display_name) > ...`.
4. So sánh kế hoạch và số hàng ước lượng.
5. Đề xuất cách tối ưu nếu truy vấn theo độ dài là một yêu cầu thường xuyên.

Bạn hoàn thành bài khi có thể giải thích chính xác byte và ký tự, dự đoán kết quả của hai hàm với dữ liệu nhiều byte, đọc metadata độ dài cột, đối chiếu Java với MySQL và lựa chọn phép đo đúng cho giới hạn nghiệp vụ.

## 17. Nguyên tắc cần ghi nhớ

- `LENGTH()` và `OCTET_LENGTH()` đo số byte; `CHAR_LENGTH()` và `CHARACTER_LENGTH()` đo số ký tự.
- `BIT_LENGTH()` đo số bit của biểu diễn byte.
- Với `utf8mb4`, một code point có thể chiếm từ một đến bốn byte.
- `CHAR_LENGTH()` không phải phép đếm grapheme cluster; một ký tự hiển thị có thể gồm nhiều code point.
- `VARCHAR(n)` giới hạn số ký tự; `CHARACTER_OCTET_LENGTH` cho biết giới hạn byte tối đa theo character set.
- Dùng `HEX()` để kiểm tra byte khi điều tra encoding và Unicode composition.
- Dùng `utf8mb4` khi cần hỗ trợ Unicode đầy đủ, bao gồm emoji.
- Trong Java, phân biệt UTF-16 code unit, Unicode code point và byte UTF-8 khi đối chiếu với MySQL.
- Đo độ dài giá trị không đồng nghĩa đo dung lượng vật lý của hàng hoặc index trên đĩa.
- Chọn `LENGTH()` cho giới hạn byte và `CHAR_LENGTH()` cho giới hạn ký tự theo yêu cầu nghiệp vụ.

Khi hiểu rõ sự khác biệt giữa byte và ký tự, bạn có thể kiểm tra dữ liệu Unicode chính xác, thiết kế giới hạn cột phù hợp, tránh lỗi với tiếng Việt và emoji, đồng thời đồng bộ cách đo độ dài giữa MySQL và ứng dụng.
