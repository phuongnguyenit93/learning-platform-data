# utf8mb4, các tên utf8 lịch sử và khả năng lưu emoji

Khi ứng dụng MySQL lưu tên người dùng, nội dung tin nhắn hoặc mô tả sản phẩm bằng nhiều ngôn ngữ, bộ ký tự (character set) quyết định những ký tự nào có thể được biểu diễn và cách chúng được mã hóa thành byte. Collation quyết định cách so sánh và sắp xếp các chuỗi thuộc bộ ký tự đó. Chọn đúng character set ở cả schema lẫn kết nối là điều kiện cần để dữ liệu tiếng Việt, ký tự ngoài bảng chữ cái Latin và emoji được lưu, đọc và tìm kiếm chính xác.

Trong MySQL, `utf8mb4` là lựa chọn phù hợp cho dữ liệu Unicode hiện đại vì nó hỗ trợ tối đa bốn byte cho một code point. Tên `utf8` lịch sử trong MySQL lại là alias của `utf8mb3`, bộ mã chỉ hỗ trợ tối đa ba byte. Vì vậy, một cột khai báo `CHARACTER SET utf8` có thể lưu tiếng Việt có dấu và nhiều ký tự phổ biến nhưng không lưu được các code point emoji nằm ngoài vùng BMP, chẳng hạn `😀` (U+1F600).

Bài học này giải thích sự khác biệt đó, cách kiểm tra charset/collation ở từng cấp, cách thử lưu emoji và những điểm cần rà soát khi chuyển một schema cũ sang `utf8mb4`.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt character set với collation và hiểu vai trò của từng loại.
- Giải thích `utf8` trong MySQL là tên lịch sử cho `utf8mb3`, không phải cách gọi đầy đủ của UTF-8 bốn byte.
- Chọn `utf8mb4` để lưu Unicode mở rộng và emoji.
- Kiểm tra charset/collation ở cấp server, database, table, column và connection.
- Dùng `CHAR_LENGTH()`, `LENGTH()` và `HEX()` để kiểm tra nội dung chuỗi.
- Chẩn đoán lỗi lưu emoji, ký tự bị thay bằng `?` và hiện tượng mojibake.
- Lập kế hoạch chuyển đổi dữ liệu cũ sang `utf8mb4` mà không làm sai nội dung hoặc quy tắc so sánh.

## 1. Character set và collation khác nhau thế nào?

**Character set** là tập ký tự và cách mã hóa mỗi ký tự thành byte. Ví dụ, `utf8mb4` biểu diễn Unicode bằng một đến bốn byte cho mỗi code point. **Collation** là tập quy tắc dùng để so sánh và sắp xếp chuỗi trong một character set, bao gồm cách xử lý chữ hoa/chữ thường, dấu và thứ tự ngôn ngữ.

Ví dụ:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Character set | `utf8mb4` | Xác định ký tự có thể biểu diễn và cách mã hóa |
| Collation | `utf8mb4_unicode_ci` | Xác định cách so sánh/sắp xếp chuỗi |
| Collation hậu tố `_ci` | case-insensitive | Không phân biệt chữ hoa và chữ thường trong so sánh |
| Collation hậu tố `_ai` | accent-insensitive | Không phân biệt dấu trong so sánh theo quy tắc collation đó |

Một character set có thể có nhiều collation. Chọn `utf8mb4` không tự quyết định chuỗi có phân biệt hoa thường hoặc dấu hay không; bạn còn phải chọn collation phù hợp với yêu cầu tìm kiếm, uniqueness và sắp xếp.

Ví dụ, với collation không phân biệt hoa thường, hai chuỗi `An` và `AN` có thể được xem là bằng nhau trong phép so sánh và ràng buộc `UNIQUE`. Nếu nghiệp vụ cần phân biệt chúng, phải chọn collation phù hợp thay vì chỉ thay đổi cách viết truy vấn.

## 2. `utf8`, `utf8mb3` và `utf8mb4` trong MySQL

Trong MySQL, tên `utf8` là alias lịch sử của `utf8mb3`. `utf8mb3` dùng tối đa ba byte cho một code point Unicode. `utf8mb4` mở rộng cách mã hóa lên tối đa bốn byte, nhờ đó biểu diễn được các code point ngoài Basic Multilingual Plane (BMP).

| Tên trong MySQL | Số byte tối đa cho một code point | Khả năng biểu diễn |
|---|---:|---|
| `utf8` (alias lịch sử của `utf8mb3`) | 3 | Unicode trong phạm vi mà UTF-8 ba byte hỗ trợ; không biểu diễn code point ngoài BMP |
| `utf8mb3` | 3 | Tương tự tên `utf8` lịch sử |
| `utf8mb4` | 4 | Unicode đầy đủ, bao gồm code point ngoài BMP và nhiều emoji hiện đại |

Tên `utf8` trong MySQL dễ gây hiểu nhầm vì UTF-8 tiêu chuẩn có thể dùng tối đa bốn byte. Trong MySQL, khi muốn lưu đầy đủ Unicode, hãy khai báo rõ `utf8mb4` thay vì dựa vào tên `utf8`.

MySQL đã đánh dấu `utf8mb3` và alias `utf8` là tên cũ/deprecated trong các phiên bản MySQL 8.0 mới. Mốc cảnh báo cụ thể phụ thuộc minor release. Khi tạo schema mới, nên dùng `utf8mb4`; khi duy trì hệ thống cũ, cần kiểm tra phiên bản máy chủ và tài liệu tương ứng trước khi lập kế hoạch loại bỏ tên cũ.

### 2.1. Vì sao tiếng Việt có dấu vẫn chạy với utf8mb3?

Phần lớn chữ cái tiếng Việt thông dụng, kể cả các chữ có dấu được mã hóa ở vùng BMP, có thể biểu diễn bằng `utf8mb3`. Vì vậy, một ứng dụng có thể đã lưu tên `Nguyễn`, `Trường`, `Đặng` trong nhiều năm mà không gặp lỗi rõ ràng.

Tuy nhiên, dữ liệu Unicode không chỉ gồm chữ cái tiếng Việt. Emoji như `😀` có code point U+1F600, nằm ngoài BMP và cần bốn byte trong UTF-8. Một số ký hiệu, emoji hoặc ký tự của các hệ chữ khác cũng nằm ngoài BMP. Khi ứng dụng bắt đầu nhận các ký tự này, giới hạn ba byte của `utf8mb3` sẽ xuất hiện.

### 2.2. Emoji không phải lúc nào cũng là một code point

Một emoji đơn giản như `😀` là một code point. Nhưng hình ảnh người dùng nhìn thấy có thể được tạo từ nhiều code point kết hợp: emoji + variation selector, emoji + skin tone modifier, hai regional indicator tạo thành cờ quốc gia, hoặc nhiều emoji nối bằng zero-width joiner (ZWJ) để tạo hình gia đình/nghề nghiệp.

Do đó, một biểu tượng hiển thị như một hình có thể gồm nhiều code point và nhiều byte. `utf8mb4` hỗ trợ các code point cần thiết; collation, font và ứng dụng hiển thị vẫn ảnh hưởng đến việc chuỗi được so sánh hoặc render ra sao.

## 3. Thử nghiệm khả năng lưu emoji

Hãy thực hành trong database sandbox. Trước hết, xem phiên bản MySQL và charset/collation của session:

```sql
SELECT VERSION() AS mysql_version;

SELECT
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation,
    @@character_set_client AS client_charset,
    @@character_set_connection AS connection_charset,
    @@character_set_results AS results_charset,
    @@collation_connection AS connection_collation;
```

Thiết lập kết nối hiện tại dùng `utf8mb4`:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
```

`SET NAMES` thiết lập charset của client, connection và results cho session, đồng thời thiết lập collation kết nối nếu được chỉ rõ. Trong ứng dụng thật, hãy cấu hình charset qua driver/connection string để mọi kết nối được khởi tạo nhất quán; không dựa vào lệnh thủ công trong một cửa sổ SQL.

Tạo bảng thử nghiệm với charset được khai báo tường minh:

```sql
CREATE TABLE unicode_message_demo (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    message_text VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci
        NOT NULL,
    PRIMARY KEY (message_id)
) ENGINE = InnoDB;

INSERT INTO unicode_message_demo (message_text)
VALUES
    ('Xin chào Việt Nam'),
    ('Chúc bạn một ngày vui 😀'),
    ('Biểu tượng: 🚀 🎉 🌱');

SELECT
    message_id,
    message_text,
    CHAR_LENGTH(message_text) AS character_count,
    LENGTH(message_text) AS byte_count,
    HEX(message_text) AS stored_bytes
FROM unicode_message_demo
ORDER BY message_id;
```

Các dòng có emoji được lưu thành công nếu cả cột lẫn kết nối đều dùng charset tương thích. Với chuỗi chỉ gồm một emoji `😀`, `CHAR_LENGTH()` trả về `1`, còn `LENGTH()` trả về `4` khi chuỗi được mã hóa UTF-8. Với câu có chữ tiếng Việt và emoji, số byte thường lớn hơn số ký tự vì các code point có độ dài mã hóa khác nhau.

`HEX()` cho biết byte thực tế của chuỗi mà MySQL trả về. Với code point `😀` được mã hóa UTF-8, dãy byte là `F09F9880`. Đây là cách hữu ích để kiểm tra dữ liệu khi giao diện terminal không hiển thị được ký tự.

## 4. Kiểm tra giới hạn utf8mb3

Để hiểu sự khác biệt, có thể tạo một bảng riêng dùng `utf8mb3` nếu phiên bản MySQL của bạn còn hỗ trợ tên này:

```sql
CREATE TABLE utf8mb3_message_demo (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    message_text VARCHAR(100)
        CHARACTER SET utf8mb3
        COLLATE utf8mb3_unicode_ci
        NOT NULL,
    PRIMARY KEY (message_id)
) ENGINE = InnoDB;
```

Thử chèn chuỗi tiếng Việt:

```sql
INSERT INTO utf8mb3_message_demo (message_text)
VALUES ('Xin chào Việt Nam');
```

Chuỗi tiếng Việt trên có thể được lưu. Sau đó thử chèn code point ngoài BMP:

```sql
INSERT INTO utf8mb3_message_demo (message_text)
VALUES ('Ký tự ngoài BMP: 😀');
```

Trong điều kiện kết nối gửi đúng UTF-8, lệnh thứ hai sẽ thất bại vì `utf8mb3` không thể biểu diễn code point U+1F600. Thông báo lỗi thường cho biết chuỗi không hợp lệ cho character set của cột. Nếu SQL mode hoặc client có hành vi chuyển đổi khác, hãy kiểm tra lỗi và cảnh báo; không chấp nhận việc ký tự bị thay bằng `?` hoặc bị mất.

Nếu phiên bản đã loại bỏ hoặc không cung cấp collation `utf8mb3_unicode_ci`, bỏ qua bước tạo bảng thử nghiệm này và dùng thông tin phiên bản/tài liệu để xác nhận giới hạn. Không đổi tên `utf8mb3` thành `utf8` để kỳ vọng có khả năng lưu bốn byte: trong MySQL, `utf8` là alias của bộ mã ba byte này.

## 5. Các cấp cấu hình character set và collation

MySQL có thể đặt mặc định ở nhiều cấp. Cấu hình ở cấp cao hơn thường cung cấp giá trị mặc định cho đối tượng được tạo sau đó; khai báo ở cấp thấp hơn có thể ghi đè.

| Cấp | Cách kiểm tra | Ảnh hưởng chính |
|---|---|---|
| Server | `@@character_set_server`, `@@collation_server` | Giá trị mặc định khi tạo database mới nếu không chỉ rõ |
| Database | `information_schema.schemata` | Giá trị mặc định cho bảng mới trong database |
| Table | `SHOW CREATE TABLE`, `information_schema.tables` | Giá trị mặc định cho cột ký tự mới trong bảng |
| Column | `SHOW FULL COLUMNS`, `information_schema.columns` | Charset/collation thực tế của từng cột ký tự |
| Connection | `@@character_set_client`, `@@character_set_connection`, `@@character_set_results` | Cách MySQL nhận, chuyển đổi và trả dữ liệu cho client |

### 5.1. Kiểm tra cấp server

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
```

Hoặc dùng `SELECT @@GLOBAL.character_set_server, @@GLOBAL.collation_server;`. Các biến global cho biết mặc định ở cấp máy chủ; thay đổi chúng không tự chuyển đổi dữ liệu đã tồn tại.

### 5.2. Kiểm tra cấp database

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM information_schema.schemata
WHERE SCHEMA_NAME = DATABASE();
```

Tạo database mới với mặc định tường minh:

```sql
CREATE DATABASE app_unicode
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

Đổi mặc định của database đã tồn tại:

```sql
ALTER DATABASE app_unicode
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

`ALTER DATABASE` thay đổi mặc định cho các đối tượng tạo sau đó. Lệnh này không tự chuyển đổi charset của các bảng và cột đã tồn tại.

### 5.3. Kiểm tra cấp table và column

```sql
SHOW CREATE TABLE unicode_message_demo;

SHOW FULL COLUMNS FROM unicode_message_demo;
```

Hoặc truy vấn metadata:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    CHARACTER_MAXIMUM_LENGTH
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'unicode_message_demo'
ORDER BY ORDINAL_POSITION;
```

Các cột số và một số kiểu không phải chuỗi có thể có `CHARACTER_SET_NAME` và `COLLATION_NAME` là `NULL`; điều đó là bình thường. Charset của table là mặc định cho cột mới, còn từng cột ký tự có thể có charset/collation riêng.

### 5.4. Kiểm tra cấp connection

```sql
SHOW SESSION VARIABLES LIKE 'character_set%';
SHOW SESSION VARIABLES LIKE 'collation%';
```

Các biến quan trọng:

- `character_set_client`: charset mà MySQL giả định client dùng để gửi câu lệnh.
- `character_set_connection`: charset mà MySQL dùng khi chuyển đổi literal nhận được và xử lý biểu thức chuỗi.
- `character_set_results`: charset mà MySQL dùng khi trả kết quả cho client.
- `collation_connection`: collation mặc định cho các phép so sánh chuỗi literal trong connection khi không có collation cụ thể khác.

Một cột đã là `utf8mb4` vẫn có thể gặp lỗi nếu ứng dụng kết nối bằng charset ba byte. Ngược lại, kết nối `utf8mb4` không làm cột `utf8mb3` tự lưu được code point bốn byte. Cần kiểm tra cả hai phía.

## 6. Chọn collation phù hợp cho utf8mb4

Collation ảnh hưởng đến phép so sánh, sắp xếp, `GROUP BY`, `ORDER BY`, phép nối chuỗi và ràng buộc `UNIQUE`. Một số collation phổ biến:

| Collation | Đặc điểm khái quát | Lưu ý |
|---|---|---|
| `utf8mb4_general_ci` | Collation cũ, so sánh không phân biệt hoa thường | Có thể dùng quy tắc đơn giản hơn; không phải lựa chọn tốt nhất cho mọi ngôn ngữ |
| `utf8mb4_unicode_ci` | Quy tắc Unicode theo phiên bản UCA cũ hơn | Được hỗ trợ rộng trong các phiên bản MySQL phổ biến |
| `utf8mb4_0900_ai_ci` | Collation Unicode 9.0 trong MySQL 8.0, không phân biệt dấu và hoa thường | Không có trong MySQL 5.7; cần kiểm tra khi triển khai đa phiên bản |
| `utf8mb4_bin` | So sánh theo giá trị nhị phân của chuỗi | Hữu ích khi cần so sánh phân biệt mã hóa/hoa thường theo byte; không thay thế mọi quy tắc nghiệp vụ |

Tên collation có hậu tố mô tả đặc tính. `_ci` thường là case-insensitive; `_cs` là case-sensitive; `_ai` là accent-insensitive; `_as` là accent-sensitive; `_bin` là dạng so sánh nhị phân. Không phải mọi kết hợp hậu tố đều tồn tại cho mọi charset và phiên bản.

Kiểm tra collation có sẵn trên server:

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

Hoặc:

```sql
SELECT COLLATION_NAME, CHARACTER_SET_NAME, IS_DEFAULT
FROM information_schema.collations
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
```

Đối với ứng dụng đa ngôn ngữ, hãy chọn collation theo yêu cầu tìm kiếm và tính duy nhất. Ví dụ, nếu email được chuẩn hóa về chữ thường ở tầng ứng dụng, collation không phân biệt hoa thường có thể phù hợp; nếu mã định danh phân biệt hoa thường, cần cân nhắc collation khác. Đừng đổi collation của bảng chỉ để sửa lỗi emoji: khả năng lưu ký tự do character set quyết định.

## 7. Độ dài ký tự và độ dài byte

Với dữ liệu đa byte, `CHAR_LENGTH()` và `LENGTH()` trả về hai khái niệm khác nhau:

- `CHAR_LENGTH(string)` đếm số ký tự theo character set của chuỗi.
- `LENGTH(string)` đếm số byte của chuỗi.

Ví dụ với một emoji:

```sql
SET NAMES utf8mb4;

SELECT
    '😀' AS emoji,
    CHAR_LENGTH('😀') AS character_count,
    LENGTH('😀') AS byte_count,
    HEX('😀') AS utf8_hex;
```

Kết quả dự kiến là một ký tự, bốn byte và chuỗi hex `F09F9880`. Nếu client terminal không hỗ trợ hiển thị emoji, `HEX()` vẫn giúp xác nhận byte được MySQL xử lý.

Lưu ý: `CHAR_LENGTH()` không đếm “ký tự nhìn thấy” theo cách người dùng cảm nhận. Một emoji ghép bằng nhiều code point có thể hiển thị như một biểu tượng nhưng được đếm thành nhiều ký tự. Chuỗi có dấu kết hợp (combining mark) cũng có thể chứa nhiều code point cho một ký tự hiển thị.

Với `VARCHAR(n)`, `n` là số ký tự tối đa theo charset, không phải số byte cố định. Trong `utf8mb4`, một cột `VARCHAR(100)` có thể cần tối đa khoảng 400 byte cho phần nội dung, chưa tính overhead và các giới hạn hàng/index liên quan. Điều này cần được tính đến khi thiết kế row size, index và migration.

## 8. Vì sao ứng dụng có thể vẫn lỗi dù cột đã dùng utf8mb4?

Để emoji đi từ thiết bị người dùng đến database và quay lại đúng, toàn bộ đường đi phải tương thích:

```text
Thiết bị / trình duyệt
        |
        v
Ứng dụng và request encoding
        |
        v
MySQL driver / connection charset
        |
        v
character_set_client -> character_set_connection
        |
        v
Cột và bảng utf8mb4
        |
        v
character_set_results -> driver -> giao diện hiển thị
```

Các nguyên nhân thường gặp:

- Cột vẫn là `utf8mb3`, dù database mặc định đã đổi sang `utf8mb4`.
- Driver mở kết nối với charset ba byte hoặc charset không khớp dữ liệu gửi lên.
- File SQL hoặc script migration được lưu bằng encoding khác với encoding mà client giả định.
- Ứng dụng chuyển đổi chuỗi sai trước khi gửi đến MySQL.
- Dữ liệu đã bị thay bằng `?` hoặc mojibake trước khi được lưu; đổi charset sau đó không thể tự khôi phục nội dung gốc.
- Giao diện, font hoặc terminal không có glyph để hiển thị emoji, dù byte trong database đã đúng.

Khi điều tra, hãy tách ba câu hỏi: MySQL có nhận đúng chuỗi không, cột có lưu đúng byte không, và client có hiển thị đúng không. Dùng `CHARACTER_SET_NAME`, `@@character_set_client`, `HEX(column)` và so sánh kết quả ở từng tầng để tìm vị trí sai.

## 9. Chẩn đoán lỗi mojibake và dữ liệu bị hỏng encoding

Mojibake là hiện tượng byte của một encoding bị diễn giải như encoding khác, khiến chuỗi hiển thị sai nhưng vẫn có thể được lưu thành một chuỗi ký tự hợp lệ. Ví dụ, một chuỗi UTF-8 bị giải mã nhầm theo Latin-1/Windows-1252 có thể xuất hiện thành các ký tự lạ.

Không nên chạy `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` ngay khi thấy chữ bị lỗi. Lệnh chuyển đổi giả định dữ liệu hiện tại đúng theo charset mà cột khai báo. Nếu byte đã bị diễn giải sai trước khi lưu, chuyển đổi có thể bảo toàn chính chuỗi sai đó hoặc làm sai thêm.

Quy trình điều tra:

1. Kiểm tra charset/collation thực tế của database, table và column.
2. Kiểm tra charset kết nối ở thời điểm dữ liệu được ghi nếu có log hoặc cấu hình ứng dụng.
3. Dùng `HEX(column)` để xem byte được lưu và so sánh với byte UTF-8 mong đợi từ nguồn đáng tin cậy.
4. Kiểm tra dữ liệu ở tầng ứng dụng trước khi gửi và sau khi đọc về.
5. Sao lưu bản dữ liệu gốc và thử quy trình sửa trên bản sao; không thử chuyển đổi trực tiếp trên dữ liệu production.

Nếu byte trong database đã trở thành dấu hỏi `3F` thay cho byte UTF-8 của emoji, thông tin gốc thường đã mất và không thể suy ra lại chỉ bằng đổi charset. Cần khôi phục từ nguồn dữ liệu gốc, bản sao lưu hoặc hệ thống upstream. Nếu byte còn nguyên nhưng bị diễn giải sai, có thể có phương án chuyển đổi có kiểm soát sau khi xác định chính xác encoding thực tế.

## 10. Chuyển đổi schema cũ sang utf8mb4

Đổi mặc định database không tự chuyển các bảng hiện hữu. Để chuyển một bảng, MySQL có cú pháp:

```sql
ALTER TABLE ten_bang
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

Lệnh này chuyển các cột ký tự trong bảng sang character set/collation đích. Cần kiểm tra kết quả bằng `SHOW CREATE TABLE` và `INFORMATION_SCHEMA.COLUMNS` sau khi chạy.

Một kế hoạch chuyển đổi an toàn thường gồm:

1. **Kiểm kê:** tìm tất cả schema, bảng, cột ký tự và collation hiện tại; xác định cột nào đã là `utf8mb4`, cột nào còn `utf8mb3` hoặc charset khác.
2. **Đánh giá dữ liệu:** kiểm tra nội dung, byte, giá trị có nguy cơ lỗi encoding và các unique key có thể thay đổi kết quả so sánh khi đổi collation.
3. **Đánh giá cấu trúc:** kiểm tra độ dài cột, tổng kích thước hàng, index và giới hạn key length của phiên bản/row format đang dùng.
4. **Sao lưu và thử nghiệm:** thử chuyển đổi trên bản sao dữ liệu gần production; so sánh số hàng, giá trị `HEX()`, kết quả truy vấn và constraint.
5. **Chuẩn hóa kết nối:** cấu hình driver dùng `utf8mb4` trước khi triển khai cột mới hoặc ghi dữ liệu mới.
6. **Triển khai:** chọn cửa sổ thay đổi hoặc công cụ migration phù hợp với kích thước bảng và yêu cầu uptime; theo dõi thời gian, khóa, dung lượng tạm và replication lag.
7. **Xác minh:** kiểm tra lại charset/collation từng cột, thử lưu emoji, đọc lại từ ứng dụng và kiểm tra các truy vấn so sánh/unique.

Ví dụ đổi mặc định database cho bảng mới và chuyển một bảng hiện tại là hai thao tác khác nhau:

```sql
-- Mặc định cho đối tượng mới trong database
ALTER DATABASE app_unicode
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Chuyển dữ liệu và cột ký tự của bảng hiện tại
ALTER TABLE customer_message
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

Đổi collation có thể làm thay đổi tính bằng nhau của chuỗi, thứ tự sắp xếp và kết quả `UNIQUE`. Ví dụ hai chuỗi trước đây được xem là khác có thể trở thành bằng nhau theo collation mới, khiến việc tạo hoặc duy trì unique index thất bại. Hãy kiểm tra trùng lặp theo collation đích trước khi chuyển.

Ngoài ra, `ALTER TABLE ... CONVERT` có thể dựng lại bảng, tăng I/O, cần dung lượng tạm và gây khóa tùy phiên bản, engine, kích thước dữ liệu và thuật toán DDL. Không chạy lệnh chuyển đổi lớn trên production khi chưa đo đạc và chuẩn bị phương án phục hồi.

## 11. Checklist kiểm tra utf8mb4 và emoji

- Đã xác nhận MySQL version và không nhầm `utf8` lịch sử với `utf8mb4`.
- Đã dùng `utf8mb4` cho database, table và các cột cần lưu Unicode mở rộng.
- Đã chọn collation theo quy tắc hoa thường, dấu, sắp xếp và uniqueness của nghiệp vụ.
- Đã kiểm tra charset/collation thực tế của từng cột bằng `SHOW CREATE TABLE` hoặc `INFORMATION_SCHEMA.COLUMNS`.
- Đã cấu hình driver/connection dùng `utf8mb4` và kiểm tra các biến session.
- Đã thử lưu và đọc lại một emoji ngoài BMP, ví dụ `😀`.
- Đã so sánh `CHAR_LENGTH()`, `LENGTH()` và `HEX()` để phân biệt ký tự với byte.
- Đã kiểm tra các chuỗi emoji ghép, variation selector và ZWJ nếu sản phẩm cần hỗ trợ.
- Đã đánh giá kích thước cột, row size, index và giới hạn key length khi chuyển đổi.
- Đã kiểm tra dữ liệu mojibake bằng byte thực tế trước khi chạy lệnh convert.
- Đã sao lưu, thử migration trên bản sao và kiểm tra tác động collation lên unique key.

`utf8mb4` giúp MySQL lưu được Unicode đầy đủ, bao gồm emoji cần bốn byte. Nhưng để dữ liệu đi qua ứng dụng an toàn, charset phải nhất quán từ client, connection đến column; collation phải được chọn theo quy tắc so sánh của nghiệp vụ. Hiểu giới hạn của `utf8mb3`, kiểm tra byte bằng `HEX()` và chuyển đổi có kế hoạch sẽ giúp tránh lỗi mất ký tự, mojibake và thay đổi bất ngờ trong truy vấn hoặc unique index.
