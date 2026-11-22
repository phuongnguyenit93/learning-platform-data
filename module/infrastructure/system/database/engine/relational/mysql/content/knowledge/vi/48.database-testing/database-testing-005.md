# Kiểm thử

## Kiểm thử NULL, chuỗi rỗng, Unicode, emoji và collation

Lỗi dữ liệu văn bản thường không xuất hiện trong một truy vấn SELECT đơn giản. Một cột có thể nhận NULL, chuỗi rỗng, dấu cách hoặc chuỗi Unicode nhiều code point; hai giá trị nhìn giống nhau trên màn hình có thể được MySQL so sánh là bằng nhau theo collation, nhưng khác nhau ở byte. Emoji có thể bị từ chối hoặc biến thành ký tự thay thế nếu một tầng kết nối chỉ hỗ trợ UTF-8 ba byte. Một unique index cũng có thể từ chối hai tên khác nhau về chữ hoa/thường hoặc dấu nếu collation không phân biệt các khác biệt đó.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Kiểm thử dữ liệu văn bản là một phần của các kỹ năng này: thiết kế schema đúng, hiểu phép so sánh, bảo vệ unique constraint và xác minh dữ liệu đi xuyên suốt ứng dụng đến MySQL mà không bị biến đổi.

Bài này xây dựng một bộ kiểm thử cho NULL, chuỗi rỗng, whitespace, tiếng Việt có dấu, Unicode tổ hợp, emoji và collation. Các ví dụ hướng đến MySQL 8.0/8.4 với InnoDB và utf8mb4; collation cụ thể có thể khác theo phiên bản, vì vậy hãy xác nhận các tên collation được hỗ trợ trên máy chủ đích.

### 1. Phân biệt NULL, chuỗi rỗng và whitespace

Ba trường hợp sau không giống nhau:

- NULL: không có giá trị hoặc chưa biết giá trị theo mô hình dữ liệu.
- '': một chuỗi có độ dài bằng 0.
- '   ': chuỗi chứa một hoặc nhiều ký tự dấu cách; nó vẫn là một giá trị.

Tab, xuống dòng, non-breaking space (NBSP) và zero-width space cũng là các ký tự có thật. Chúng có thể trông như khoảng trống nhưng không đồng nghĩa với chuỗi rỗng.

#### 1.1. SQL NULL cần phép so sánh riêng

Không dùng = NULL hoặc <> NULL. Phép so sánh thông thường với NULL cho kết quả UNKNOWN, không phải TRUE/FALSE. Dùng IS NULL và IS NOT NULL:

~~~sql
SELECT
  customer_id,
  display_name,
  display_name IS NULL AS is_missing,
  display_name = '' AS is_empty
FROM appdb.customers;

SELECT COUNT(*) AS missing_count
FROM appdb.customers
WHERE display_name IS NULL;

SELECT COUNT(*) AS empty_count
FROM appdb.customers
WHERE display_name = '';
~~~

Nếu cần coi NULL và chuỗi rỗng là cùng một nhóm trong báo cáo, viết quy tắc rõ ràng:

~~~sql
SELECT
  CASE
    WHEN display_name IS NULL THEN 'MISSING'
    WHEN display_name = '' THEN 'EMPTY'
    ELSE 'PRESENT'
  END AS value_state,
  COUNT(*) AS row_count
FROM appdb.customers
GROUP BY value_state;
~~~

Đừng dùng COALESCE(display_name, '') ở mọi nơi chỉ để đơn giản hóa truy vấn. Làm vậy có thể xóa mất ý nghĩa khác nhau giữa “chưa biết” và “đã biết là rỗng”, ảnh hưởng validation, báo cáo và logic nghiệp vụ.

#### 1.2. Kiểm tra chuỗi chỉ có dấu cách

TRIM() mặc định loại bỏ ký tự space ASCII ở hai đầu, không phải mọi ký tự mà người dùng nhìn nhận là whitespace:

~~~sql
SELECT
  display_name,
  display_name = '' AS equals_empty,
  TRIM(display_name) = '' AS blank_after_trim,
  CHAR_LENGTH(display_name) AS char_count,
  LENGTH(display_name) AS byte_count,
  HEX(display_name) AS raw_hex
FROM appdb.customers;
~~~

Với dữ liệu Unicode, TRIM() mặc định không tự loại bỏ mọi NBSP, tab, newline hoặc zero-width character. Nếu nghiệp vụ yêu cầu chuẩn hóa whitespace, hãy định nghĩa chính xác tập ký tự được phép loại bỏ ở tầng ứng dụng hoặc dùng biểu thức SQL được kiểm thử theo bộ ký tự đó. Không âm thầm xóa mọi ký tự vô hình vì chúng có thể có ý nghĩa trong một số định danh hoặc ngôn ngữ.

#### 1.3. CHAR và VARCHAR

CHAR(n) là kiểu độ dài cố định và có quy tắc đệm khoảng trắng; cách lưu/trả khoảng trắng cuối còn chịu ảnh hưởng của kiểu dữ liệu, SQL mode và phiên bản. VARCHAR(n) lưu chuỗi độ dài biến đổi. Với tên người dùng, email, mã ngoài hệ thống và văn bản tùy ý, VARCHAR thường phù hợp hơn CHAR, nhưng lựa chọn cuối cùng phải dựa trên miền dữ liệu.

Không kiểm thử chuỗi rỗng chỉ trên một cột CHAR. Hãy kiểm thử trên đúng kiểu cột production, vì padding và cách so sánh dấu cách cuối có thể làm kết quả khác.

### 2. Tạo fixture kiểm thử có chủ đích

Tạo một bảng lab với utf8mb4 và một cột văn bản có collation chỉ định rõ:

~~~sql
CREATE DATABASE IF NOT EXISTS text_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE text_test.text_cases (
  case_id BIGINT NOT NULL PRIMARY KEY,
  label VARCHAR(80) CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NULL,
  notes VARCHAR(255) CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NULL
) ENGINE=InnoDB;
~~~

Collation utf8mb4_0900_ai_ci là một ví dụ cho MySQL 8.0 trở lên. Nếu phiên bản hoặc môi trường không hỗ trợ, chọn collation được liệt kê trên server và ghi lại lựa chọn đó trong kết quả test.

Chèn các trường hợp đại diện:

~~~sql
INSERT INTO text_test.text_cases (case_id, label, notes) VALUES
  (1, NULL, 'SQL NULL'),
  (2, '', 'empty string'),
  (3, '   ', 'three ASCII spaces'),
  (4, 'A', 'uppercase A'),
  (5, 'a', 'lowercase a'),
  (6, 'cafe', 'without accent'),
  (7, 'café', 'with accent'),
  (8, 'Tieng Viet', 'ASCII approximation'),
  (9, 'Tiếng Việt có dấu', 'Vietnamese text'),
  (10, '😊', 'supplementary-plane emoji'),
  (11, '👨‍👩‍👧‍👦', 'emoji sequence with joiners'),
  (12, 'é', 'e plus combining acute accent'),
  (13, 'é', 'precomposed e acute');
~~~

Hai giá trị ở case 12 và 13 có thể trông giống nhau nhưng cách mã hóa Unicode khác nhau: một chuỗi dùng e cộng combining acute accent; chuỗi kia dùng ký tự é dựng sẵn. Chúng hữu ích để kiểm tra normalization và hành vi collation.

Với fixture chứa emoji hoặc ký tự ngoài BMP, đảm bảo file SQL, terminal và client gửi truy vấn cũng đang dùng UTF-8. Nếu ký tự đã bị thay thế trước khi đến MySQL, kiểm tra trong database không thể khôi phục dữ liệu gốc.

### 3. utf8mb4 và đường đi của ký tự

MySQL có charset utf8mb4 hỗ trợ tối đa bốn byte cho mỗi Unicode code point. Charset utf8 trong MySQL là bí danh lịch sử của utf8mb3, chỉ hỗ trợ tối đa ba byte và không lưu được nhiều ký tự ngoài BMP, trong đó có phần lớn emoji hiện đại.

Đối với dữ liệu mới, chọn utf8mb4 cho database/table/column và xác minh cả kết nối client. Chỉ đổi charset của cột mà không kiểm tra character_set_client, character_set_connection và character_set_results có thể vẫn để lại lỗi ở tầng giao tiếp.

Kiểm tra charset và collation:

~~~sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@character_set_server,
  @@character_set_database,
  @@collation_connection,
  @@collation_server,
  @@collation_database;
~~~

Kiểm tra định nghĩa database, table và column:

~~~sql
SHOW CREATE DATABASE text_test;
SHOW CREATE TABLE text_test.text_cases;

SELECT
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME,
  COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'text_test'
  AND TABLE_NAME = 'text_cases';
~~~

Một cột utf8mb4 không đủ nếu client gửi bytes theo charset khác. Khi dùng command-line client, có thể kết nối với charset rõ ràng hoặc thiết lập session phù hợp. Trong ứng dụng, hãy kiểm tra driver đã thương lượng charset đúng và không chỉ dựa vào giá trị mặc định.

#### 3.1. Round-trip test

Round-trip test xác minh ký tự đi từ client đến server, được lưu, đọc lại và trả về client mà không đổi:

~~~sql
SELECT
  case_id,
  label,
  HEX(label) AS stored_bytes,
  CHAR_LENGTH(label) AS character_count,
  LENGTH(label) AS byte_count
FROM text_test.text_cases
ORDER BY case_id;
~~~

CHAR_LENGTH() đếm ký tự theo chuỗi của MySQL; LENGTH() trả số byte. Với UTF-8, hai số thường khác nhau. Ví dụ một emoji có thể là một code point nhưng chiếm bốn byte. Một chuỗi có dấu kết hợp có thể chứa nhiều code point dù người dùng nhìn thấy một ký tự.

Để kiểm tra từng code point trong dữ liệu, HEX() giúp quan sát byte UTF-8. So sánh kết quả giữa nguồn, target và giá trị ứng dụng gửi đi. Nếu byte khác nhau, xác định thay đổi xảy ra ở serializer, driver, connection charset hay schema conversion.

### 4. Code point, grapheme và emoji

Khái niệm “một ký tự” có thể chỉ ba điều khác nhau:

- **Byte:** đơn vị lưu trữ; UTF-8 dùng từ một đến bốn byte cho mỗi code point.
- **Unicode code point:** một giá trị Unicode. CHAR_LENGTH() gần với số code point trong chuỗi, không phải số byte.
- **Grapheme cluster:** đơn vị người dùng cảm nhận như một ký tự hiển thị. Một grapheme có thể gồm nhiều code point.

Ví dụ emoji gia đình 👨‍👩‍👧‍👦 được tạo bởi nhiều emoji nối với nhau bằng zero-width joiner (ZWJ). Nó có thể hiển thị như một hình duy nhất nhưng chứa nhiều code point và nhiều byte. Không dùng CHAR_LENGTH() để đếm số ký tự hiển thị trong giao diện.

Test dữ liệu emoji nên bao gồm:

- Một emoji đơn giản như 😊.
- Emoji có modifier màu da như 👍🏽.
- Cờ quốc gia được tạo từ regional indicator.
- Chuỗi ZWJ như 👨‍👩‍👧‍👦.
- Ký tự ngoài BMP không phải emoji.
- Chuỗi kết hợp dấu tiếng Việt hoặc dấu combining.

Kiểm tra byte và độ dài:

~~~sql
SELECT
  label,
  CHAR_LENGTH(label) AS code_point_count,
  OCTET_LENGTH(label) AS utf8_byte_count,
  HEX(label) AS utf8_hex
FROM text_test.text_cases
WHERE case_id IN (9, 10, 11, 12, 13);
~~~

OCTET_LENGTH() tương đương LENGTH() đối với chuỗi byte. Kết quả của một chuỗi ZWJ phụ thuộc số code point thực tế; hãy đo dữ liệu thật thay vì hard-code giả định rằng emoji hiển thị là một code point.

### 5. Unicode normalization

Unicode cho phép một số ký tự hiển thị giống nhau được biểu diễn bằng các chuỗi code point khác nhau. Ví dụ ký tự có dấu có thể được biểu diễn ở dạng dựng sẵn (precomposed) hoặc bằng chữ cái cơ sở cộng combining mark.

MySQL không nên được xem như một tầng tự động chuẩn hóa mọi chuỗi đầu vào về NFC/NFD. Hành vi so sánh của collation UCA có thể xử lý một số dạng tương đương theo quy tắc collation, nhưng điều đó không đồng nghĩa byte lưu trữ được chuẩn hóa giống nhau.

Vì vậy, hãy xác định yêu cầu:

1. **Bảo toàn byte:** hai chuỗi khác byte vẫn được coi là khác.
2. **So sánh văn bản theo ngôn ngữ:** một số biến thể Unicode/case/accent có thể được coi là tương đương.
3. **Canonical storage:** ứng dụng chuẩn hóa đầu vào về một dạng, ví dụ NFC, trước khi lưu.

Nếu hệ thống cần canonical storage, chuẩn hóa ở tầng ứng dụng bằng thư viện Unicode đã chọn, rồi kiểm thử round-trip và migration dữ liệu cũ. Không thay thế ký tự bằng một bảng mapping thủ công nhỏ vì Unicode có nhiều tổ hợp và ngôn ngữ.

So sánh hai dạng trong MySQL:

~~~sql
SELECT
  HEX('é') AS decomposed_hex,
  HEX('é') AS precomposed_hex,
  'é' = 'é' COLLATE utf8mb4_0900_ai_ci
    AS equal_under_ai_ci,
  BINARY 'é' = BINARY 'é'
    AS equal_as_bytes;
~~~

Kết quả phép so sánh phụ thuộc collation cụ thể. Phép so sánh BINARY thể hiện khác biệt byte của hai chuỗi trong ví dụ. Dùng truy vấn này như test trên đúng phiên bản server và lưu kết quả mong đợi của hệ thống.

### 6. Collation quyết định so sánh và sắp xếp

Charset xác định cách mã hóa ký tự; collation xác định cách so sánh và sắp xếp chuỗi. Hai cột cùng utf8mb4 nhưng khác collation có thể cho kết quả =, ORDER BY, GROUP BY, DISTINCT, LIKE và unique index khác nhau.

Một số hậu tố thường gặp trong tên collation:

| Hậu tố | Ý nghĩa tổng quát |
|---|---|
| _ai | Accent-insensitive: không phân biệt dấu theo quy tắc collation |
| _as | Accent-sensitive: phân biệt dấu |
| _ci | Case-insensitive: không phân biệt hoa/thường |
| _cs | Case-sensitive: phân biệt hoa/thường |
| _bin | Collation nhị phân theo giá trị ký tự/byte của charset |
| _0900 | Họ collation UCA 9.0 trong MySQL 8.0 trở lên |

Không phải mọi tổ hợp hậu tố đều tồn tại trên mọi phiên bản. Xem danh sách collation thực tế:

~~~sql
SHOW COLLATION LIKE 'utf8mb4%';

SELECT
  COLLATION_NAME,
  CHARACTER_SET_NAME,
  IS_DEFAULT,
  PAD_ATTRIBUTE
FROM INFORMATION_SCHEMA.COLLATIONS
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
~~~

PAD_ATTRIBUTE có thể giúp nhận biết quy tắc xử lý dấu cách cuối (PAD SPACE hoặc NO PAD) ở các phiên bản có cột này. Đừng suy ra padding chỉ từ tên collation; kiểm tra metadata và chạy phép thử.

#### 6.1. Kiểm tra case và accent sensitivity

Ép collation trực tiếp trong truy vấn để so sánh:

~~~sql
SELECT
  'A' COLLATE utf8mb4_0900_ai_ci =
    'a' COLLATE utf8mb4_0900_ai_ci AS case_equal_ai_ci,
  'cafe' COLLATE utf8mb4_0900_ai_ci =
    'café' COLLATE utf8mb4_0900_ai_ci AS accent_equal_ai_ci,
  'A' COLLATE utf8mb4_0900_as_cs =
    'a' COLLATE utf8mb4_0900_as_cs AS case_equal_as_cs,
  'cafe' COLLATE utf8mb4_0900_as_cs =
    'café' COLLATE utf8mb4_0900_as_cs AS accent_equal_as_cs;
~~~

Với collation _ai_ci, chữ hoa/thường và dấu thường không phân biệt theo trọng số collation. Với _as_cs, cả dấu và hoa/thường đều được phân biệt. Hãy xác nhận trên đúng collation và dữ liệu thực tế.

#### 6.2. Kiểm tra trailing spaces

Hai chuỗi chỉ khác dấu cách ở cuối có thể được coi là bằng nhau dưới collation PAD SPACE, trong khi NO PAD phân biệt chúng. Hành vi này quan trọng với email, username, mã định danh và unique index:

~~~sql
SELECT
  'abc' COLLATE utf8mb4_general_ci =
    'abc ' COLLATE utf8mb4_general_ci AS equal_under_pad_space,
  'abc' COLLATE utf8mb4_0900_ai_ci =
    'abc ' COLLATE utf8mb4_0900_ai_ci AS equal_with_trailing_space,
  HEX('abc') AS first_hex,
  HEX('abc ') AS second_hex;
~~~

Trong các phiên bản phổ biến, utf8mb4_general_ci là ví dụ collation PAD SPACE còn utf8mb4_0900_ai_ci là NO PAD; xác nhận PAD_ATTRIBUTE trên server trước khi dùng kết quả làm tiêu chí. Chạy phép thử với collation đang dùng ở production. Đối với cột CHAR, quy tắc padding riêng của kiểu dữ liệu cũng cần được tính đến; dùng VARCHAR trong test nếu muốn cô lập hành vi collation.

#### 6.3. LIKE, ORDER BY và GROUP BY

Không chỉ phép = chịu ảnh hưởng. Hãy kiểm thử các thao tác mà ứng dụng thực sự dùng:

~~~sql
SELECT label, COUNT(*)
FROM text_test.text_cases
GROUP BY label
ORDER BY label;

SELECT DISTINCT label
FROM text_test.text_cases
ORDER BY label;

SELECT case_id, label
FROM text_test.text_cases
WHERE label LIKE 'cafe%';
~~~

Nếu nghiệp vụ cần tìm kiếm phân biệt dấu hoặc hoa/thường, dùng collation phù hợp hoặc thiết kế cột/search key riêng. Không đổi collation tùy tiện ở mỗi truy vấn vì có thể làm index không được sử dụng tối ưu; kiểm tra EXPLAIN sau khi thêm COLLATE vào predicate.

### 7. Collation và unique index

Unique index kiểm tra tính duy nhất theo quy tắc so sánh của collation trên cột chuỗi. Nếu collation không phân biệt hoa/thường hoặc dấu, các chuỗi khác byte vẫn có thể xung đột.

Ví dụ:

~~~sql
CREATE TABLE text_test.user_names (
  user_id BIGINT NOT NULL PRIMARY KEY,
  username VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NOT NULL,
  UNIQUE KEY uq_user_names_username (username)
) ENGINE=InnoDB;

INSERT INTO text_test.user_names VALUES (1, 'Cafe');
-- Giá trị tiếp theo có thể vi phạm unique key theo collation:
INSERT INTO text_test.user_names VALUES (2, 'café');
~~~

Trong collation accent-insensitive và case-insensitive, Cafe và café có thể được coi là cùng giá trị. Đừng giả định unique index bảo đảm duy nhất theo byte nếu collation không làm điều đó.

Trước khi đổi collation của cột có unique index:

1. Kiểm tra duplicate theo collation đích.
2. Xác định quy tắc nghiệp vụ về case, dấu, whitespace và Unicode normalization.
3. Làm sạch hoặc phân giải các giá trị xung đột.
4. Thử tạo unique index trên bản sao dữ liệu.
5. Đánh giá lock, thời gian DDL và tác động replication.
6. Chỉ triển khai khi đã có quy tắc xử lý xung đột được phê duyệt.

Truy vấn phát hiện nhóm trùng phải chạy trên dữ liệu nguồn hoặc staging trước khi tạo unique index. Ví dụ staging table chưa có constraint duy nhất:

~~~sql
CREATE TABLE text_test.user_names_staging (
  user_id BIGINT NOT NULL PRIMARY KEY,
  username VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NOT NULL
) ENGINE=InnoDB;

INSERT INTO text_test.user_names_staging VALUES
  (1, 'Cafe'),
  (2, 'café'),
  (3, 'CAFE');
~~~

Truy vấn phát hiện nhóm trùng theo collation đích:

~~~sql
SELECT
  username COLLATE utf8mb4_0900_ai_ci AS comparison_key,
  COUNT(*) AS duplicate_count,
  GROUP_CONCAT(user_id ORDER BY user_id) AS user_ids
FROM text_test.user_names_staging
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

GROUP_CONCAT() có giới hạn độ dài; với dữ liệu lớn, lấy danh sách khóa theo nhóm bằng truy vấn riêng thay vì phụ thuộc toàn bộ chuỗi tổng hợp.

Unique index trên cột nullable trong MySQL cho phép nhiều hàng có NULL vì NULL không được xem là bằng nhau trong kiểm tra unique. Nếu nghiệp vụ yêu cầu chỉ có một giá trị “chưa biết”, cần mô hình hóa hoặc constraint khác; đừng mặc định unique index sẽ giới hạn NULL thành một hàng.

### 8. Bộ ca kiểm thử tối thiểu

Một bộ test dữ liệu văn bản nên có các nhóm:

| Nhóm | Dữ liệu mẫu | Điều cần xác minh |
|---|---|---|
| Missing | NULL | IS NULL, count, default và constraint |
| Empty | '' | Độ dài bằng 0, không bị biến thành NULL |
| ASCII whitespace | space, tab, CR/LF | Quy tắc trim và validation |
| Unicode whitespace | NBSP, zero-width space | Không bị xử lý nhầm như ASCII space |
| Case | A, a | Equality, LIKE, GROUP BY và unique |
| Accent | cafe, café | Accent sensitivity |
| Vietnamese | Tiếng Việt, Đặng, ắ, ộ | Round-trip và collation |
| Normalization | NFC/NFD tương đương về hiển thị | Byte, comparison và chuẩn hóa |
| Emoji | 😊, 👍🏽, cờ, ZWJ family | utf8mb4, byte count và round-trip |
| Boundary | chuỗi rỗng, chuỗi dài tối đa, ký tự cuối | Độ dài cột và index |
| Duplicate | giá trị khác byte nhưng tương đương theo collation | Unique constraint |
| Invalid encoding | byte sequence không hợp lệ | Lỗi, warning hoặc reject theo driver/SQL mode |

Với mỗi ca, ghi:

- Input gốc tại tầng ứng dụng.
- Bytes/Unicode code point dự kiến nếu cần kiểm tra encoding.
- Charset/collation của column và connection.
- Giá trị lưu trong database qua HEX().
- Giá trị đọc ngược ở ứng dụng.
- Kết quả equality, LIKE, ORDER BY, GROUP BY và unique constraint.
- Kết quả mong đợi và kết quả thực tế trên từng phiên bản MySQL được hỗ trợ.

### 9. Kiểm thử từ Java với Connector/J

Kiểm thử SQL trực tiếp bằng command-line client chưa đủ nếu ứng dụng sử dụng Connector/J. Cần xác minh cả giá trị truyền bằng JDBC và dữ liệu đọc ngược.

Ví dụ JUnit-style test dùng PreparedStatement:

~~~java
String value = "Tiếng Việt 😊 👨‍👩‍👧‍👦";

try (Connection conn = dataSource.getConnection()) {
    try (PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO text_test.text_cases(case_id, label, notes) VALUES (?, ?, ?)")) {
        ps.setLong(1, 100L);
        ps.setString(2, value);
        ps.setString(3, "round-trip");
        assertEquals(1, ps.executeUpdate());
    }

    try (PreparedStatement ps = conn.prepareStatement(
            "SELECT label FROM text_test.text_cases WHERE case_id = ?")) {
        ps.setLong(1, 100L);
        try (ResultSet rs = ps.executeQuery()) {
            assertTrue(rs.next());
            assertEquals(value, rs.getString("label"));
            assertFalse(rs.next());
        }
    }
}
~~~

Test cần chạy qua đúng phiên bản Connector/J, JDK và pool production. Kiểm tra thêm session charset:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT @@character_set_client, " +
         "@@character_set_connection, " +
         "@@character_set_results, @@collation_connection");
     ResultSet rs = ps.executeQuery()) {
    assertTrue(rs.next());
    // Assert theo charset/collation được thiết kế cho ứng dụng.
}
~~~

Không hard-code kỳ vọng của session nếu pool hoặc cấu hình kết nối có thể đặt giá trị khác. Điều quan trọng là giá trị thực tế khớp với cấu hình đã thống nhất.

Trong Connector/J, hãy dùng cấu hình charset/collation được tài liệu của đúng phiên bản hỗ trợ. Sau khi kết nối, đọc character_set_client, character_set_connection, character_set_results và collation_connection để xác minh. Tránh gọi SET NAMES tùy tiện trong mỗi request vì thay đổi session có thể rò rỉ qua connection pool nếu không được reset.

### 10. SQL mode, warnings và dữ liệu không hợp lệ

SQL mode ảnh hưởng cách MySQL xử lý dữ liệu ngoài miền, chuyển kiểu và lỗi. Trong chế độ strict, một số giá trị không hợp lệ sẽ bị từ chối thay vì âm thầm chuyển đổi. Hãy ghi lại mode dùng trong test:

~~~sql
SELECT @@SESSION.sql_mode, @@GLOBAL.sql_mode;
-- Chạy INSERT/UPDATE đang được kiểm thử ngay trước câu lệnh kế tiếp.
SHOW WARNINGS;
~~~

Không chỉ kiểm tra exception. Sau INSERT/UPDATE, đọc SHOW WARNINGS ngay trong cùng session để phát hiện truncation hoặc conversion warning. Warning có thể bị mất khi chạy câu lệnh tiếp theo.

Thử dữ liệu vượt độ dài cột, ký tự không thể biểu diễn trong charset đích và bytes không hợp lệ. Kỳ vọng nên là reject rõ ràng hoặc hành vi chuyển đổi đã được chấp thuận; không chấp nhận dữ liệu bị cắt hoặc thay bằng ?/replacement character mà không có cảnh báo.

### 11. Kiểm tra schema và migration collation

Khi đổi cột từ charset/collation cũ sang utf8mb4 hoặc collation mới, migration có thể thay đổi:

- Dữ liệu byte và cách chuyển mã.
- Kết quả so sánh và sắp xếp.
- Các nhóm DISTINCT/GROUP BY.
- Tính duy nhất của unique index.
- Khả năng sử dụng index của truy vấn.
- Dung lượng index do số byte tối đa của ký tự tăng.

Trước khi chạy ALTER:

~~~sql
SHOW CREATE TABLE appdb.customers;

SELECT
  COUNT(*) AS total_rows,
  SUM(display_name IS NULL) AS null_rows,
  SUM(display_name = '') AS empty_rows,
  MAX(CHAR_LENGTH(display_name)) AS max_char_length,
  MAX(OCTET_LENGTH(display_name)) AS max_byte_length
FROM appdb.customers;
~~~

Kiểm tra duplicate theo collation đích trước khi xây unique index. Kiểm tra kích thước index và giới hạn key length theo row format, page size và phiên bản. Dùng staging clone để thử ALTER và đo thời gian/replication lag.

Không dùng ALTER TABLE ... CONVERT TO CHARACTER SET mà chưa backup và kiểm tra dữ liệu có thể chuyển đổi. Khi có chuỗi byte sai charset từ trước, chuyển charset có thể làm sai dữ liệu thêm. Xác định charset nguồn thực sự trước khi chuyển.

### 12. Ma trận kiểm thử theo tầng

| Tầng | Kiểm tra | Bằng chứng |
|---|---|---|
| Input/UI | Người dùng nhập NULL, empty, whitespace, tiếng Việt, emoji | Giá trị trước khi serialize |
| Application | Validation, normalization, Java String handling | Unit test và log an toàn |
| JDBC/Driver | Charset thương lượng, setString/getString, reconnect | Connector/J integration test |
| MySQL session | character_set_*, collation_connection, sql_mode | Query metadata trong session |
| Schema | Charset/collation cột, kiểu, độ dài, index | SHOW CREATE TABLE, INFORMATION_SCHEMA |
| SQL semantics | NULL, equality, LIKE, GROUP BY, ORDER BY | Kết quả truy vấn theo test case |
| Constraint | Unique key và nullable column | INSERT test có kiểm soát |
| Persistence | Byte và giá trị đọc lại | HEX(), CHAR_LENGTH(), LENGTH() |
| Upgrade/migration | Chuyển charset/collation trên dữ liệu thật | Restore rehearsal, duplicate report, post-migration test |

Tách unit test khỏi integration test. Unit test kiểm tra validation/normalization của ứng dụng; integration test kiểm tra hành vi thật của MySQL và Connector/J. Một test mock JDBC không thể chứng minh server collation đang phân biệt hay gộp hai chuỗi theo đúng yêu cầu.

### 13. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Emoji lưu thành ? hoặc bị từ chối | Cột hoặc connection dùng utf8mb3/charset khác | Kiểm tra charset của column và session; so sánh input với HEX() |
| Tiếng Việt bị lỗi dấu | Bytes được diễn giải sai charset hoặc file/client encoding không đúng | Kiểm tra charset ở từng chặng và test round-trip |
| NULL không lọc được | Dùng = NULL thay cho IS NULL | Sửa predicate và kiểm thử cả UNKNOWN semantics |
| Chuỗi rỗng bị coi là thiếu | Ứng dụng hoặc SQL gộp '' với NULL | Xác định contract dữ liệu, dùng điều kiện riêng |
| Hai username khác nhau nhưng unique index báo trùng | Collation không phân biệt case/accent hoặc trailing space | Kiểm tra collation, PAD_ATTRIBUTE và nhóm trùng theo collation đích |
| Hai chuỗi nhìn giống nhau nhưng hash khác | NFC/NFD hoặc byte encoding khác | So sánh HEX(), code point và quy tắc normalization |
| LIKE trả kết quả ngoài mong đợi | Collation và wildcard semantics | Kiểm tra collation, escape %/_ và chạy ca kiểm thử biên |
| Sau migration xuất hiện duplicate | Collation đích gộp các giá trị trước đây khác nhau | Phân tích duplicate trước ALTER, giải quyết theo nghiệp vụ |
| Kết quả khác giữa CLI và Java | Driver/session charset hoặc collation khác | Query session variables từ đúng connection của ứng dụng |
| Dữ liệu bị cắt nhưng INSERT không fail | SQL mode không strict hoặc warning bị bỏ qua | Kiểm tra SQL mode và SHOW WARNINGS ngay sau statement |

### 14. Bài tập thực hành

Một ứng dụng quản lý tài khoản lưu username trong cột VARCHAR(100). Hệ thống cũ dùng collation không phân biệt hoa/thường và dấu. Sau khi chuyển sang utf8mb4_0900_ai_ci, migration tạo unique index thất bại vì có các giá trị Cafe, café và CAFE. Một số người dùng cũng báo emoji trong tên hiển thị bị lưu thành dấu hỏi.

1. Viết truy vấn phân biệt NULL, chuỗi rỗng và chuỗi chỉ có ASCII space.
2. Dùng CHAR_LENGTH, OCTET_LENGTH và HEX để kiểm tra tiếng Việt và emoji.
3. Làm thế nào xác định charset của column khác charset của connection?
4. Viết truy vấn tìm username trùng theo collation đích.
5. Vì sao ba username trên có thể vi phạm unique index?
6. Hãy thiết kế test NFC/NFD và giải thích vì sao byte giống nhau không phải điều kiện duy nhất cho equality theo collation.
7. Viết integration test Connector/J gửi và đọc lại chuỗi có tiếng Việt và emoji.
8. Trước khi đổi collation production, cần báo cáo và xử lý những nhóm duplicate nào?

### 15. Checklist nghiệm thu

- [ ] Đã phân biệt NULL, '', whitespace và giá trị mặc định trong contract dữ liệu.
- [ ] Test IS NULL/IS NOT NULL; không dùng = NULL.
- [ ] Đã kiểm tra CHAR/VARCHAR, dấu cách cuối và quy tắc padding.
- [ ] Database, table, column và connection dùng charset/collation đã định nghĩa.
- [ ] Emoji và ký tự ngoài BMP round-trip thành công qua đúng Connector/J.
- [ ] HEX, CHAR_LENGTH và OCTET_LENGTH khớp với dữ liệu mong đợi.
- [ ] Có test case tiếng Việt, combining mark, NFC/NFD, emoji modifier và ZWJ.
- [ ] Đã kiểm tra case/accent sensitivity, LIKE, ORDER BY, GROUP BY và DISTINCT.
- [ ] Đã kiểm tra PAD_ATTRIBUTE hoặc hành vi trailing-space của collation.
- [ ] Đã phát hiện duplicate theo collation đích trước khi tạo unique index.
- [ ] Đã kiểm tra nhiều NULL trong unique index theo đúng quy tắc nghiệp vụ.
- [ ] SQL mode và warning được ghi nhận; không có truncation/conversion ngoài ý muốn.
- [ ] Migration charset/collation đã được rehearsal trên bản sao dữ liệu và có backup.
- [ ] Unit test và integration test đều chạy qua tầng ứng dụng thực tế.

### 16. Nguyên tắc vận hành

Đừng coi mọi khoảng trống là chuỗi rỗng hoặc mọi chuỗi nhìn giống nhau là cùng một giá trị. Phân biệt NULL, empty và whitespace bằng điều kiện riêng; dùng utf8mb4 cho dữ liệu Unicode hiện đại và xác minh charset ở cả cột lẫn connection. Kiểm tra byte bằng HEX(), độ dài bằng CHAR_LENGTH() và OCTET_LENGTH(), rồi thử equality, LIKE, grouping và unique index dưới collation thật. Trước khi đổi collation, tìm duplicate theo quy tắc đích và giải quyết theo nghiệp vụ. Một bộ test đáng tin cậy phải chạy qua đúng ứng dụng, Connector/J, pool và phiên bản MySQL sẽ được triển khai.
