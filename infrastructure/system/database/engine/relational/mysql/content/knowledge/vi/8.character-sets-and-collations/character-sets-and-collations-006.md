# Phân biệt hoa/thường, dấu và ý nghĩa các hậu tố collation

Trong MySQL, character set quyết định cách mã hóa ký tự thành byte; collation quyết định cách so sánh và sắp xếp chuỗi thuộc character set đó. Hai chuỗi có byte khác nhau vẫn có thể được xem là bằng nhau theo collation. Vì vậy, lựa chọn collation ảnh hưởng trực tiếp tới tìm kiếm, lọc, sắp xếp, nhóm dữ liệu và ràng buộc UNIQUE.

Bài học thuộc phạm vi \`DATABASE_MYSQL\`: thiết kế schema và kiểu dữ liệu phù hợp, truy vấn văn bản chính xác, kiểm soát tính duy nhất, tối ưu index và tránh lỗi khi chuyển đổi charset/collation giữa các môi trường.

## 1. Character set và collation giải quyết hai vấn đề khác nhau

**Character set** (bộ ký tự) xác định tập ký tự và cách mã hóa ký tự thành byte. Ví dụ, \`utf8mb4\` hỗ trợ Unicode với tối đa bốn byte cho mỗi ký tự.

**Collation** xác định quy tắc so sánh và sắp xếp các chuỗi thuộc một character set. Quy tắc đó có thể xem chữ hoa và chữ thường là tương đương, xem chữ có dấu và không dấu là tương đương, hoặc phân biệt chúng.

| Thành phần | Câu hỏi |
|---|---|
| Character set | Ký tự được mã hóa thành byte như thế nào? |
| Collation | Hai chuỗi được so sánh và sắp xếp theo quy tắc nào? |

Ví dụ, \`'Cafe'\` và \`'café'\` có nội dung byte khác nhau. Với collation không phân biệt hoa/thường và dấu, chúng có thể được xem là bằng nhau. Với collation phân biệt cả hai, chúng được xem là khác nhau.

### 1.1. Cùng dữ liệu nhưng kết quả truy vấn khác nhau

~~~sql
CREATE TABLE account_name (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL
);
~~~

Với collation \`utf8mb4_0900_ai_ci\`, điều kiện \`WHERE username = 'nguyen'\` có thể tìm các biến thể khác chữ hoa/thường và dấu theo quy tắc collation. Khi đổi sang collation phân biệt dấu hoặc hoa/thường, tập kết quả có thể thay đổi dù dữ liệu không đổi.

Điều này ảnh hưởng tới tìm kiếm tài khoản, kiểm tra tên đăng nhập trùng lặp, phân nhóm khách hàng và sắp xếp danh sách.

## 2. Ý nghĩa các hậu tố collation

Các hậu tố thường gặp trong tên collation Unicode của MySQL:

| Hậu tố | Tên đầy đủ | Ý nghĩa |
|---|---|---|
| \`_ci\` | Case-insensitive | Không phân biệt chữ hoa và chữ thường |
| \`_cs\` | Case-sensitive | Phân biệt chữ hoa và chữ thường |
| \`_ai\` | Accent-insensitive | Không phân biệt dấu/diacritics theo quy tắc collation |
| \`_as\` | Accent-sensitive | Phân biệt dấu/diacritics theo quy tắc collation |
| \`_bin\` | Binary collation | So sánh theo giá trị mã ký tự, không theo quy tắc ngôn ngữ thông thường |

Hai nhóm \`_ci\`/\`_cs\` và \`_ai\`/\`_as\` là hai chiều độc lập. Một collation có thể không phân biệt hoa/thường nhưng vẫn phân biệt dấu, hoặc ngược lại.

### 2.1. Bốn tổ hợp phổ biến

| Hậu tố | Hoa/thường | Dấu | Ý nghĩa |
|---|---|---|---|
| \`_ai_ci\` | Không phân biệt | Không phân biệt | Cafe và café có thể bằng nhau |
| \`_as_ci\` | Không phân biệt | Phân biệt | Cafe khác café; Cafe và CAFE có thể bằng nhau |
| \`_ai_cs\` | Phân biệt | Không phân biệt | Cafe khác CAFE; dấu có thể được bỏ qua |
| \`_as_cs\` | Phân biệt | Phân biệt | Phân biệt cả chữ hoa/thường và dấu |

Đây là cách đọc thuộc tính collation. Kết quả cụ thể vẫn phụ thuộc collation đầy đủ, phiên bản UCA, quy tắc ngôn ngữ và ký tự đang so sánh.

### 2.2. Ví dụ collation UCA 9.0

Các collation sau minh họa bốn tổ hợp:

- \`utf8mb4_0900_ai_ci\`: không phân biệt dấu và hoa/thường.
- \`utf8mb4_0900_as_ci\`: phân biệt dấu, không phân biệt hoa/thường.
- \`utf8mb4_0900_ai_cs\`: không phân biệt dấu, phân biệt hoa/thường.
- \`utf8mb4_0900_as_cs\`: phân biệt dấu và hoa/thường.

Hậu tố \`_0900\` cho biết collation dựa trên Unicode Collation Algorithm (UCA) phiên bản 9.0.0. Đây không phải độ dài ký tự hay phiên bản MySQL. Không phải mọi character set hoặc phiên bản server đều cung cấp đủ tổ hợp trên; hãy kiểm tra danh sách collation thực tế.

## 3. Phân biệt hoa/thường với _ci và _cs

### 3.1. Case-insensitive

Collation có hậu tố \`_ci\` không phân biệt chữ hoa và chữ thường theo quy tắc collation.

~~~sql
SELECT
    _utf8mb4'MySQL' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'mysql' COLLATE utf8mb4_0900_ai_ci AS same_case_ci;
~~~

Kết quả là 1 (TRUE) vì hai chuỗi chỉ khác cách viết hoa/thường.

### 3.2. Case-sensitive

Collation có hậu tố \`_cs\` phân biệt chữ hoa và chữ thường.

~~~sql
SELECT
    _utf8mb4'MySQL' COLLATE utf8mb4_0900_as_cs =
    _utf8mb4'mysql' COLLATE utf8mb4_0900_as_cs AS same_case_cs;
~~~

Kết quả là 0 (FALSE).

Không nên mặc định rằng mọi cột \`VARCHAR\` đều phân biệt hoa/thường. Cần xem collation thực tế của cột.

### 3.3. _ci không đơn giản là LOWER()

Collation không phân biệt hoa/thường không chỉ gọi \`LOWER()\` rồi so sánh. MySQL dùng quy tắc trọng số (collation weights) để xác định ký tự tương đương và thứ tự sắp xếp. Một số quy tắc Unicode không thể mô tả đầy đủ bằng cách chuyển toàn bộ chuỗi thành chữ thường.

Khi cần tìm kiếm không phân biệt hoa/thường, ưu tiên chọn collation phù hợp cho cột hoặc biểu thức. Không tự động bọc mọi cột bằng \`LOWER()\` nếu chưa đánh giá ảnh hưởng tới index.

## 4. Phân biệt dấu với _ai và _as

### 4.1. Accent-insensitive

Collation có hậu tố \`_ai\` không phân biệt dấu/diacritics theo quy tắc của collation.

~~~sql
SELECT
    _utf8mb4'cafe' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'café' COLLATE utf8mb4_0900_ai_ci AS same_accent_ai;
~~~

Với collation accent-insensitive phù hợp, kết quả là 1 (TRUE). Điều này hữu ích cho tìm kiếm khi người dùng có thể bỏ dấu lúc nhập từ khóa. Tuy nhiên, tên người, địa danh, mã định danh và dữ liệu pháp lý có thể cần phân biệt chính xác dấu.

### 4.2. Accent-sensitive

Collation có hậu tố \`_as\` phân biệt dấu:

~~~sql
SELECT
    _utf8mb4'cafe' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'café' COLLATE utf8mb4_0900_as_ci AS same_accent_as;
~~~

Kết quả là 0 (FALSE), dù \`_as_ci\` vẫn không phân biệt chữ hoa và chữ thường.

### 4.3. Kiểm thử với tiếng Việt

Tiếng Việt có nhiều chữ cái mang dấu thanh và dấu phụ: \`a\`, \`á\`, \`à\`, \`ả\`, \`ã\`, \`ạ\`, \`ă\`, \`â\`, \`ê\`, \`ô\`, \`ơ\`, \`ư\`... Có nghiệp vụ tìm kiếm muốn chấp nhận tên không dấu, nhưng dữ liệu chính thức vẫn cần giữ nguyên dấu.

~~~sql
SELECT
    _utf8mb4'hoa' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'hòa' COLLATE utf8mb4_0900_ai_ci AS equal_ai_ci,
    _utf8mb4'hoa' COLLATE utf8mb4_0900_as_cs =
    _utf8mb4'hòa' COLLATE utf8mb4_0900_as_cs AS equal_as_cs;
~~~

Với dữ liệu tiếng Việt thực tế, hãy kiểm thử dấu thanh, dấu phụ, chữ \`đ\`, ký tự ghép Unicode và quy tắc sắp xếp cần có. Nếu server có collation dành riêng cho tiếng Việt, có thể kiểm tra:

~~~sql
SHOW COLLATION LIKE 'utf8mb4_vi%';
~~~

Không giả định collation tiếng Việt có mặt trong mọi phiên bản, bản build hoặc dịch vụ tương thích MySQL. Cũng không suy luận rằng mọi chữ tiếng Việt có dấu đều tương đương với chữ không dấu chỉ từ hậu tố \`_ai\`; các chữ cái riêng như \`đ\` và thứ tự từ điển cần được kiểm thử.

## 5. Hậu tố _bin và binary string

### 5.1. Binary collation

Collation có hậu tố \`_bin\` so sánh theo giá trị mã ký tự thay vì quy tắc ngôn ngữ thông thường. Nó thường phân biệt hoa/thường và dấu vì các ký tự có mã khác nhau được so sánh riêng.

~~~sql
SELECT
    _utf8mb4'MySQL' COLLATE utf8mb4_0900_bin =
    _utf8mb4'mysql' COLLATE utf8mb4_0900_bin AS same_binary_collation;
~~~

Kết quả là 0. Binary collation vẫn là collation của một character set: chuỗi vẫn là chuỗi ký tự thuộc character set đó.

### 5.2. _bin không giống kiểu BINARY

| Đặc điểm | Collation \`utf8mb4_0900_bin\` | Kiểu \`BINARY(M)\` |
|---|---|---|
| Bản chất | Quy tắc so sánh cho chuỗi thuộc utf8mb4 | Kiểu chuỗi byte có độ dài cố định |
| Nội dung | Ký tự mã hóa bằng utf8mb4 | Byte |
| Character set | Có | Không |
| Collation | Có, là binary collation | Không |
| Đệm | Theo PAD ATTRIBUTE của collation | Đệm byte \`0x00\` tới độ dài khai báo |
| Ngữ nghĩa | So sánh theo giá trị mã ký tự | So sánh chuỗi byte |

Nếu cần phân biệt chuỗi ký tự theo mã Unicode, có thể dùng binary collation. Nếu cần lưu hash, token, UUID dạng byte hoặc payload, hãy dùng \`BINARY\`, \`VARBINARY\` hoặc \`BLOB\` phù hợp.

Không đổi cột văn bản thành kiểu BINARY chỉ để tìm kiếm phân biệt hoa/thường vì điều đó thay đổi kiểu dữ liệu và cách mã hóa.

## 6. Phiên bản UCA và tên collation

Tên collation có thể chứa thông tin về thuật toán và phiên bản UCA.

| Collation | Ý nghĩa khái quát |
|---|---|
| \`utf8mb4_general_ci\` | Collation legacy với quy tắc tổng quát, không phân biệt hoa/thường |
| \`utf8mb4_unicode_ci\` | Collation Unicode dựa trên UCA đời cũ, không phân biệt hoa/thường |
| \`utf8mb4_unicode_520_ci\` | Collation Unicode dựa trên UCA 5.2.0 |
| \`utf8mb4_0900_ai_ci\` | UCA 9.0.0, không phân biệt dấu và hoa/thường |
| \`utf8mb4_0900_as_cs\` | UCA 9.0.0, phân biệt dấu và hoa/thường |
| \`utf8mb4_0900_bin\` | Binary collation thuộc nhóm 0900 |

Các collation \`general_ci\` và \`unicode_ci\` có quy tắc khác nhau. \`general_ci\` được thiết kế đơn giản, nhưng không cung cấp đầy đủ hành vi sắp xếp theo UCA như collation Unicode. Khi cần xử lý ngôn ngữ chính xác, hãy chọn collation Unicode phù hợp.

\`utf8mb4_0900_ai_ci\` có từ MySQL 8.0 và không có trong MySQL 5.7. Khi triển khai nhiều phiên bản hoặc chuyển sang MariaDB/engine tương thích, phải kiểm tra tên collation được hỗ trợ trên server đích.

## 7. PAD SPACE và NO PAD

Ngoài hoa/thường và dấu, collation còn có thuộc tính về cách xử lý khoảng trắng cuối chuỗi:

- **PAD SPACE:** khoảng trắng cuối thường không làm thay đổi kết quả so sánh bằng nhau.
- **NO PAD:** khoảng trắng cuối là một phần có ý nghĩa trong phép so sánh.

Các collation UCA 9.0 trong MySQL 8.0 thường có thuộc tính NO PAD; nhiều collation legacy có PAD SPACE. Không suy luận thuộc tính này từ \`_ci\` hay \`_cs\`; hãy đọc \`PAD_ATTRIBUTE\`.

~~~sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    IS_DEFAULT,
    PAD_ATTRIBUTE
FROM information_schema.collations
WHERE COLLATION_NAME IN (
    'utf8mb4_0900_ai_ci',
    'utf8mb4_unicode_ci',
    'utf8mb4_bin'
)
ORDER BY COLLATION_NAME;
~~~

Thử so sánh:

~~~sql
SELECT
    _utf8mb4'abc' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'abc ' COLLATE utf8mb4_0900_ai_ci AS no_pad_equal,
    _utf8mb4'abc' COLLATE utf8mb4_unicode_ci =
    _utf8mb4'abc ' COLLATE utf8mb4_unicode_ci AS pad_space_equal;
~~~

Với các collation trong ví dụ, NO PAD có thể phân biệt khoảng trắng cuối, còn PAD SPACE xem hai chuỗi bằng nhau. Xác nhận thuộc tính trên server cụ thể.

Điều này ảnh hưởng tới unique index: với PAD SPACE, hai giá trị chỉ khác khoảng trắng cuối có thể xung đột unique key; với NO PAD, chúng có thể là hai giá trị khác nhau. Kiểu \`CHAR\` cũng có quy tắc lưu/trả về khoảng trắng riêng, không nhầm hành vi đó với thuộc tính padding của collation.

## 8. Collation ảnh hưởng tới truy vấn

### 8.1. So sánh bằng, IN và BETWEEN

Collation quyết định hai chuỗi có được xem là bằng nhau hay không:

~~~sql
SELECT customer_id, customer_name
FROM customer
WHERE customer_name = 'nguyen van a';
~~~

Nếu cột dùng \`utf8mb4_0900_ai_ci\`, kết quả có thể bao gồm biến thể khác hoa/thường và dấu theo quy tắc collation. Với \`utf8mb4_0900_as_cs\`, điều kiện phân biệt cả hai. Các phép \`IN\`, \`=\`, \`<>\`, \`BETWEEN\` và so sánh chuỗi cũng chịu ảnh hưởng tương tự.

### 8.2. LIKE

~~~sql
SELECT customer_id, customer_name
FROM customer
WHERE customer_name LIKE '%hoa%';
~~~

Trong collation không phân biệt hoa/thường, pattern có thể khớp với chữ hoa tương ứng. Với collation phân biệt hoa/thường, kết quả có thể khác. Dấu \`%\` ở đầu pattern thường khiến B-tree index không thể định vị một range đơn giản; đây là vấn đề về pattern và access path, không chỉ do collation.

### 8.3. ORDER BY

~~~sql
SELECT customer_name
FROM customer
ORDER BY customer_name;
~~~

Collation xác định thứ tự sắp xếp. Collation ngôn ngữ có thể dùng trọng số UCA hoặc quy tắc riêng, khác với thứ tự mã byte. Nếu sản phẩm cần thứ tự từ điển tiếng Việt, hãy chọn collation locale phù hợp nếu có và kiểm thử trên dữ liệu thật.

### 8.4. GROUP BY và DISTINCT

~~~sql
SELECT customer_name, COUNT(*) AS total
FROM customer
GROUP BY customer_name
ORDER BY customer_name;
~~~

Với collation không phân biệt hoa/thường và dấu, một số chuỗi khác cách viết có thể thuộc cùng nhóm. \`DISTINCT\` cũng dùng quy tắc so sánh tương ứng để xác định giá trị khác nhau. Nếu thống kê cần phân biệt chính xác cách nhập, hãy chọn collation hoặc biểu thức so sánh rõ ràng.

## 9. Collation và UNIQUE index

Collation là một phần của quy tắc xác định trùng lặp trong unique index.

~~~sql
CREATE TABLE username_demo (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    UNIQUE KEY uq_username (username)
);
~~~

Với collation không phân biệt hoa/thường và dấu, \`'Admin'\` và \`'admin'\` có thể được xem là trùng nhau. Các biến thể có dấu cũng có thể xung đột nếu collation xem chúng tương đương.

Nếu username cần phân biệt chính xác:

~~~sql
CREATE TABLE username_exact (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL,
    UNIQUE KEY uq_username_exact (username)
);
~~~

### 9.1. Kiểm tra duplicate trước khi đổi collation

~~~sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS compared_username,
    COUNT(*) AS duplicate_count
FROM username_exact
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn trả về nhóm có nhiều hơn một dòng, unique index theo collation đích có thể không tạo được hoặc thao tác chuyển đổi có thể thất bại do duplicate key.

Hãy quyết định cách xử lý dữ liệu trùng trước khi ALTER. Không xóa hoặc gộp tài khoản tự động chỉ để DDL chạy thành công; cần quy tắc nghiệp vụ và kiểm tra tham chiếu.

## 10. Collation ở cấp server, database, table, column và expression

MySQL cho phép đặt default charset/collation ở nhiều cấp. Cấp thấp hơn có thể kế thừa mặc định từ cấp cao hơn, nhưng có thể khai báo ghi đè.

### 10.1. Cấp server

~~~sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

Server default được dùng khi tạo database mà không chỉ định charset/collation. Cấu hình thường nằm trong option file hoặc tham số khởi động.

### 10.2. Cấp database

~~~sql
CREATE DATABASE customer_app
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

SHOW CREATE DATABASE customer_app;

ALTER DATABASE customer_app
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

Thay đổi default database ảnh hưởng tới đối tượng mới được tạo sau đó. Nó không tự động chuyển đổi collation của bảng và cột đã tồn tại.

### 10.3. Cấp table

~~~sql
CREATE TABLE customer_app.customer (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL
) CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Các cột văn bản kế thừa default của bảng nếu không khai báo riêng.

### 10.4. Cấp column

~~~sql
CREATE TABLE customer_app.user_account (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL
);
~~~

Username phân biệt hoa/thường và dấu; display name tìm kiếm không phân biệt hoa/thường và dấu theo collation đã chọn.

### 10.5. Cấp expression

~~~sql
SELECT
    username,
    username COLLATE utf8mb4_0900_as_cs = 'Admin' AS exact_match
FROM customer_app.user_account;
~~~

Có thể áp dụng collation cho biểu thức mà không thay đổi định nghĩa cột. Tuy nhiên, COLLATE trong biểu thức có thể ảnh hưởng tới khả năng dùng index; hãy kiểm tra \`EXPLAIN\`.

## 11. Charset và collation của kết nối

Kết nối client-server có các thiết lập riêng:

- \`character_set_client\`: character set client dùng để gửi câu lệnh.
- \`character_set_connection\`: character set server dùng để diễn giải chuỗi sau khi nhận.
- \`collation_connection\`: collation cho các phép so sánh chuỗi literal trong một số ngữ cảnh.
- \`character_set_results\`: character set server dùng để trả kết quả cho client.

~~~sql
SHOW VARIABLES LIKE 'character_set_%';
SHOW VARIABLES LIKE 'collation_%';

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

\`SET NAMES\` đặt các thiết lập charset/collation của kết nối theo quy tắc của lệnh. Trong ứng dụng, nên cấu hình driver/connection pool đúng cách thay vì chạy lệnh tùy tiện ở từng truy vấn.

Nếu client gửi UTF-8 nhưng kết nối bị khai báo sai charset, server có thể diễn giải sai byte và lưu dữ liệu lỗi. Đổi collation của cột sau đó không tự sửa được dữ liệu đã bị mã hóa sai.

## 12. Kiểm tra collation trên server

Không nên đoán tên collation. Hãy tra danh sách server hỗ trợ.

~~~sql
SHOW CHARACTER SET;
SHOW COLLATION LIKE 'utf8mb4%';

SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    IS_DEFAULT,
    IS_COMPILED,
    PAD_ATTRIBUTE
FROM information_schema.collations
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
~~~

Các cột trong \`INFORMATION_SCHEMA.COLLATIONS\` có thể khác theo phiên bản. Kiểm tra tài liệu đúng phiên bản trước khi phụ thuộc vào thuộc tính như \`PAD_ATTRIBUTE\`.

Xem collation của cột:

~~~sql
SHOW FULL COLUMNS FROM customer_app.user_account;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'customer_app'
  AND TABLE_NAME = 'user_account'
ORDER BY ORDINAL_POSITION;
~~~

Xem DDL đầy đủ:

~~~sql
SHOW CREATE TABLE customer_app.user_account\\G
~~~

## 13. Chuyển đổi collation an toàn

Đổi collation có thể làm thay đổi kết quả so sánh và unique constraint. Không chạy ALTER trực tiếp trên production khi chưa kiểm tra dữ liệu.

### 13.1. Chỉ đổi default của bảng

~~~sql
ALTER TABLE customer_app.customer
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh này đổi default cho cột văn bản được tạo sau đó; không chuyển đổi collation của các cột đã tồn tại.

### 13.2. Chuyển đổi tất cả cột văn bản

~~~sql
ALTER TABLE customer_app.customer
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh này chuyển đổi các cột ký tự của bảng sang character set/collation đích. MySQL có thể điều chỉnh kiểu dữ liệu để bảo toàn giới hạn độ dài theo ký tự khi số byte tối đa thay đổi. Một số cột TEXT có thể được nâng lên loại lớn hơn nếu cần.

Việc chuyển đổi có thể rebuild bảng/index, tiêu tốn I/O, thời gian và không gian tạm. Khả năng online phụ thuộc phiên bản, storage engine, kiểu thay đổi và cấu hình.

### 13.3. Chuyển đổi một cột

~~~sql
ALTER TABLE customer_app.customer
    MODIFY display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL;
~~~

Khi dùng \`MODIFY\`, khai báo lại đầy đủ thuộc tính cột cần giữ như NULL/NOT NULL, DEFAULT, COMMENT, GENERATED và các thuộc tính khác. Nếu bỏ sót, thuộc tính cột có thể bị thay đổi ngoài ý muốn.

### 13.4. Quy trình migration

1. Ghi nhận charset/collation hiện tại ở server, database, table và column.
2. Xác định mục tiêu nghiệp vụ: tìm kiếm có bỏ dấu không, có phân biệt hoa/thường không, có cần sắp xếp theo ngôn ngữ không.
3. Kiểm tra collation đích có trên phiên bản và dịch vụ đang chạy không.
4. Tìm giá trị sẽ trở thành trùng theo collation đích, đặc biệt với unique index.
5. Backup dữ liệu và thử restore trên môi trường riêng.
6. Chạy chuyển đổi trên bản sao gần kích thước production; đo thời gian, I/O, lock và dung lượng.
7. Thực hiện migration theo kế hoạch, theo dõi duplicate key và lỗi ứng dụng.
8. Kiểm tra lại DDL, index, kết quả truy vấn và luồng nhập/xuất tiếng Việt.
9. Ghi lại collation mới và cập nhật cấu hình ứng dụng/driver.

## 14. Collation, index và hiệu năng

Index chuỗi được xây dựng theo thứ tự so sánh của collation gắn với cột. Vì vậy, đổi collation có thể làm thay đổi thứ tự index và yêu cầu xây dựng lại index.

### 14.1. Điều kiện lọc có thể dùng index

~~~sql
CREATE INDEX idx_customer_name
ON customer_app.customer(display_name);

EXPLAIN
SELECT customer_id
FROM customer_app.customer
WHERE display_name = 'Nguyen Van A';
~~~

Kiểm tra access type, key, rows ước tính và điều kiện lọc.

### 14.2. Tránh chuyển đổi từng dòng không cần thiết

~~~sql
SELECT customer_id
FROM customer_app.customer
WHERE LOWER(display_name) = LOWER('Nguyen Van A');
~~~

Bọc cột trong hàm có thể khiến index thông thường không được sử dụng như mong muốn. Nếu nhu cầu nghiệp vụ là tìm kiếm không phân biệt hoa/thường, hãy chọn collation phù hợp ngay ở cột hoặc xem xét generated column/index biểu thức được hỗ trợ.

### 14.3. So sánh bằng collation khác trong một truy vấn

~~~sql
EXPLAIN
SELECT customer_id
FROM customer_app.user_account
WHERE username COLLATE utf8mb4_0900_as_cs = 'Admin';
~~~

Biểu thức COLLATE có thể làm thay đổi khả năng dùng index nếu collation của biểu thức không tương thích với index của cột. Kiểm tra kế hoạch thực thi thay vì suy luận chỉ từ cú pháp.

Nếu thường xuyên cần cả tìm kiếm không phân biệt hoa/thường và exact-case, có thể thiết kế thêm cột/generated column phù hợp hoặc cấu trúc tìm kiếm riêng. Đánh giá chi phí lưu trữ, cập nhật và tính nhất quán trước khi thêm index.

## 15. Lỗi thường gặp liên quan tới collation

| Vấn đề | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Chuỗi khác chữ hoa nhưng truy vấn vẫn khớp | Cột dùng collation \`_ci\` | Xem COLLATION_NAME |
| Chuỗi có dấu và không dấu được xem là bằng nhau | Collation dùng \`_ai\` | Kiểm tra hậu tố và thử truy vấn |
| Unique key báo duplicate | Collation xem hai chuỗi là tương đương | GROUP BY theo collation đích |
| Không tìm thấy collation khi restore | Collation không có trong phiên bản đích | SHOW COLLATION trên server đích |
| Illegal mix of collations | Biểu thức chuỗi có collation không tương thích | Kiểm tra charset/collation của cột và literal |
| Tiếng Việt hiển thị sai | Charset kết nối sai hoặc dữ liệu đã mã hóa sai | Kiểm tra client/connection/results |
| ORDER BY khác môi trường | Phiên bản UCA/collation khác | Kiểm tra tên collation và phiên bản |
| Truy vấn chậm sau khi đổi collation | Index rebuild hoặc biểu thức không dùng index | EXPLAIN và thống kê |
| Chuỗi chỉ khác khoảng trắng cuối bị coi là trùng | PAD SPACE | Kiểm tra PAD_ATTRIBUTE |
| DDL đổi collation thất bại | Duplicate key hoặc lỗi chuyển đổi | Preflight dữ liệu và error log |

Lỗi 1267 thường xuất hiện khi MySQL không thể phối hợp các collation trong một biểu thức. Có thể dùng \`COLLATE\` để chỉ định quy tắc rõ ràng nếu các chuỗi có character set tương thích. Nếu character set khác nhau, cần chuyển đổi bằng \`CONVERT(... USING charset)\` trước rồi áp dụng collation phù hợp.

Không thêm COLLATE một cách máy móc để che lỗi; trước tiên hãy xác định vì sao các nguồn dữ liệu có charset/collation khác nhau.

## 16. Ví dụ tổng hợp: tìm kiếm tên và username

Một hệ thống có hai nhu cầu:

- Tên hiển thị cần tìm kiếm thuận tiện, không phân biệt hoa/thường và dấu.
- Username cần phân biệt chính xác chữ hoa/thường và dấu.

~~~sql
CREATE TABLE app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_app_user_username (username),
    KEY idx_app_user_display_name (display_name)
) ENGINE = InnoDB;
~~~

Truy vấn username exact-case:

~~~sql
SELECT user_id, username
FROM app_user
WHERE username = 'Admin';
~~~

Truy vấn display name không phân biệt hoa/thường và dấu:

~~~sql
SELECT user_id, display_name
FROM app_user
WHERE display_name = 'nguyen van a';
~~~

Collation không thay thế quy tắc chuẩn hóa dữ liệu ứng dụng. Nếu username cần quy tắc định danh riêng (Unicode normalization, danh sách ký tự được phép hoặc kiểm soát ký tự nhìn giống nhau), cần xử lý thêm ở tầng ứng dụng và/hoặc schema. Case-sensitive không đồng nghĩa chống được mọi dạng giả mạo Unicode.

## 17. Checklist lựa chọn collation

- [ ] Đã chọn character set phù hợp, thường là \`utf8mb4\` cho dữ liệu Unicode.
- [ ] Đã xác định có cần phân biệt hoa/thường không.
- [ ] Đã xác định có cần phân biệt dấu/diacritics không.
- [ ] Đã kiểm tra hậu tố \`_ci\`, \`_cs\`, \`_ai\`, \`_as\`.
- [ ] Đã phân biệt \`_bin\` với kiểu dữ liệu \`BINARY\`/\`VARBINARY\`.
- [ ] Đã kiểm tra UCA/version và collation có sẵn trên server đích.
- [ ] Đã kiểm tra PAD SPACE/NO PAD nếu dữ liệu có khoảng trắng cuối.
- [ ] Đã xác minh default ở server, database, table, column và connection.
- [ ] Đã kiểm tra tác động tới equality, LIKE, ORDER BY, GROUP BY và DISTINCT.
- [ ] Đã tìm duplicate theo collation đích trước khi đổi unique index.
- [ ] Đã đo tác động tới index, thời gian DDL và dung lượng.
- [ ] Đã kiểm thử tiếng Việt, ký tự ghép và dữ liệu thực tế.
- [ ] Đã backup, thử restore và có kế hoạch rollback.

## 18. Bài tập thực hành

### Bài 1: So sánh hoa/thường

Chạy biểu thức so sánh \`'MySQL'\` với \`'mysql'\` bằng \`utf8mb4_0900_ai_ci\` và \`utf8mb4_0900_as_cs\`. Ghi lại kết quả và giải thích hậu tố.

### Bài 2: So sánh dấu

So sánh \`'cafe'\` và \`'café'\` bằng collation \`_ai_ci\` và \`_as_ci\`. Thử thêm các từ tiếng Việt có dấu và ghi lại kết quả.

### Bài 3: Kiểm tra PAD SPACE và NO PAD

Dùng \`INFORMATION_SCHEMA.COLLATIONS\` để đọc \`PAD_ATTRIBUTE\`. So sánh \`'abc'\` và \`'abc '\` dưới hai collation. Tạo unique index để quan sát tác động của khoảng trắng cuối.

### Bài 4: Unique key và duplicate

Tạo bảng username với collation case-insensitive. Thử chèn \`Admin\` và \`admin\`. Sau đó chuyển sang collation case-sensitive trong lab và so sánh kết quả.

### Bài 5: Kiểm tra index

Tạo index cho cột tên. So sánh \`EXPLAIN\` của truy vấn equality, truy vấn dùng \`LOWER()\` và truy vấn dùng \`COLLATE\`. Ghi nhận access path.

## 19. Kết luận

Các hậu tố collation mô tả quy tắc so sánh quan trọng: \`_ci\` không phân biệt hoa/thường, \`_cs\` phân biệt hoa/thường, \`_ai\` không phân biệt dấu và \`_as\` phân biệt dấu. \`_bin\` dùng quy tắc so sánh theo giá trị mã ký tự. PAD SPACE và NO PAD quyết định khoảng trắng cuối có ảnh hưởng tới phép so sánh hay không.

Collation ảnh hưởng trực tiếp tới tìm kiếm, sắp xếp, nhóm dữ liệu, unique index và kế hoạch truy vấn. Hãy chọn collation theo yêu cầu nghiệp vụ, xác minh phiên bản UCA và hỗ trợ của server, kiểm thử dữ liệu tiếng Việt, rồi đánh giá tác động tới index trước khi chuyển đổi. Character set bảo đảm dữ liệu được mã hóa đúng; collation bảo đảm dữ liệu được so sánh theo đúng quy tắc mong muốn.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual – Collation Naming Conventions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-names.html)
- [MySQL 8.4 Reference Manual – Supported Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset-charsets.html)
- [MySQL 8.4 Reference Manual – Unicode Character Sets](https://dev.mysql.com/doc/refman/8.4/en/charset-unicode-sets.html)
- [MySQL 8.4 Reference Manual – Collation Implementation Types](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-implementations.html)
- [MySQL 8.4 Reference Manual – Character Set and Collation of Expressions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-expressions.html)
- [MySQL 8.4 Reference Manual – Collation Coercibility in Expressions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-coercibility.html)
- [MySQL 8.4 Reference Manual – Connection Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset-connection.html)
- [MySQL 8.4 Reference Manual – Database Character Set and Collation](https://dev.mysql.com/doc/refman/8.4/en/charset-database.html)
- [MySQL 8.4 Reference Manual – Table Character Set and Collation](https://dev.mysql.com/doc/refman/8.4/en/charset-table.html)
- [MySQL 8.4 Reference Manual – Column Character Set and Collation](https://dev.mysql.com/doc/refman/8.4/en/charset-column.html)

