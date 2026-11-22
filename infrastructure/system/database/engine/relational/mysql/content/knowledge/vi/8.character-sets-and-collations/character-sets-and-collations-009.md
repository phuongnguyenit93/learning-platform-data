# Khoảng trắng cuối, PAD SPACE/NO PAD và ảnh hưởng đến UNIQUE

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt dữ liệu chuỗi thực sự được lưu với cách collation so sánh chuỗi.
- Giải thích thuộc tính PAD SPACE và NO PAD trong MySQL.
- Dự đoán khi nào hai giá trị chỉ khác khoảng trắng cuối vẫn bị xem là bằng nhau.
- Hiểu vì sao UNIQUE index có thể từ chối hai chuỗi nhìn khác nhau.
- Kiểm tra collation, byte dữ liệu và các nhóm giá trị có thể xung đột trước khi tạo hoặc thay đổi unique key.
- Lập kế hoạch đổi collation và chuẩn hóa dữ liệu mà không làm mất thông tin nghiệp vụ.

Khi làm việc với mã khách hàng, username, mã đơn hàng hoặc khóa tự nhiên, một chi tiết nhỏ như dấu cách ở cuối chuỗi có thể quyết định hai bản ghi có được xem là trùng nhau hay không. Trong MySQL, điều đó phụ thuộc vào collation của chuỗi. Hai chuỗi có thể được lưu với số byte khác nhau nhưng vẫn được so sánh là bằng nhau. Nếu cột có UNIQUE index, việc chèn giá trị thứ hai có thể bị từ chối.

Bài học tập trung vào chuỗi không nhị phân như CHAR, VARCHAR và TEXT. Dữ liệu nhị phân như BINARY, VARBINARY và BLOB có quy tắc so sánh theo byte, không dùng thuộc tính PAD SPACE/NO PAD của collation ký tự.

## 1. Hai lớp khác nhau: lưu chuỗi và so sánh chuỗi

Một giá trị chuỗi có thể được xem ở hai góc độ:

- **Biểu diễn được lưu:** các ký tự và byte thực tế trong cột.
- **Quy tắc so sánh:** collation quyết định hai chuỗi bằng nhau, khác nhau, hoặc được sắp xếp theo thứ tự nào.

Ví dụ, hai giá trị VARCHAR có thể chứa lần lượt `'SKU-100'` và `'SKU-100 '`. Giá trị thứ hai có thêm một dấu cách ASCII ở cuối. Với một số collation, MySQL bỏ qua khoảng trắng cuối khi so sánh; với collation khác, dấu cách đó có ý nghĩa.

Vì vậy, không nên suy luận kết quả so sánh chỉ bằng cách nhìn chuỗi hiển thị. Cần biết kiểu cột, character set và collation đang áp dụng.

### 1.1. Character set và collation

**Character set** xác định cách mã hóa ký tự thành byte. Ví dụ, `utf8mb4` có thể biểu diễn các ký tự Unicode bằng tối đa bốn byte cho mỗi ký tự.

**Collation** xác định cách so sánh và sắp xếp chuỗi trong một character set. Tên collation thường thể hiện một số đặc tính:

- `_ci`: so sánh không phân biệt chữ hoa/chữ thường (case-insensitive).
- `_cs`: phân biệt chữ hoa/chữ thường (case-sensitive), nếu collation đó hỗ trợ.
- `_ai`: không phân biệt dấu (accent-insensitive).
- `_as`: phân biệt dấu (accent-sensitive).
- Các collation UCA có hậu tố phiên bản như `_0900` dựa trên thuật toán Unicode Collation Algorithm tương ứng.

Những hậu tố này không nói trực tiếp collation có PAD SPACE hay NO PAD. Muốn biết chính xác, cần xem thuộc tính `PAD_ATTRIBUTE` trong metadata.

### 1.2. Ví dụ về hai chuỗi có byte khác nhau

Có thể dùng các hàm sau để xem độ dài và byte:

~~~sql
SELECT
    'SKU-100' AS value_without_space,
    'SKU-100 ' AS value_with_space,
    CHAR_LENGTH('SKU-100') AS chars_without_space,
    CHAR_LENGTH('SKU-100 ') AS chars_with_space,
    OCTET_LENGTH('SKU-100') AS bytes_without_space,
    OCTET_LENGTH('SKU-100 ') AS bytes_with_space,
    HEX('SKU-100') AS hex_without_space,
    HEX('SKU-100 ') AS hex_with_space;
~~~

Với chuỗi ASCII này, `CHAR_LENGTH` và `OCTET_LENGTH` đều tăng thêm một ở giá trị có dấu cách. Byte cuối của dấu cách ASCII là `20` trong hệ thập lục phân.

Các hàm hữu ích:

| Hàm | Ý nghĩa |
|---|---|
| `CHAR_LENGTH(value)` | Số ký tự trong chuỗi |
| `OCTET_LENGTH(value)` | Số byte trong chuỗi |
| `LENGTH(value)` | Số byte; tương đương OCTET_LENGTH trong MySQL |
| `HEX(value)` | Biểu diễn byte dưới dạng ký tự hệ 16 |
| `RTRIM(value)` | Loại bỏ dấu cách ở cuối chuỗi |
| `COLLATION(value)` | Cho biết collation của biểu thức chuỗi |
| `CHARSET(value)` | Cho biết character set của biểu thức chuỗi |

`RTRIM()` mặc định xử lý dấu cách thông thường ở cuối; nó không phải công cụ tổng quát để loại bỏ mọi loại khoảng trắng Unicode. Tab, xuống dòng và non-breaking space là những ký tự khác dấu cách ASCII.

## 2. PAD SPACE và NO PAD là gì?

Thuộc tính `PAD_ATTRIBUTE` của collation xác định cách xử lý dấu cách ở cuối chuỗi trong các phép so sánh chuỗi không nhị phân.

- **PAD SPACE:** MySQL xem các dấu cách ASCII ở cuối là phần đệm và bỏ qua chúng khi so sánh. Ví dụ, `'code'` và `'code '` được xem là bằng nhau.
- **NO PAD:** dấu cách ở cuối là một phần có ý nghĩa của chuỗi. Ví dụ, `'code'` và `'code '` được xem là khác nhau.

Đây là quy tắc so sánh. Nó không có nghĩa MySQL tự xóa dấu cách khỏi giá trị VARCHAR được lưu.

### 2.1. So sánh trực tiếp với hai collation

Trong MySQL 8.0, hai collation utf8mb4 minh họa rõ khác biệt:

- `utf8mb4_general_ci`: PAD SPACE.
- `utf8mb4_0900_ai_ci`: NO PAD.

Chạy phép so sánh tường minh:

~~~sql
SELECT
    _utf8mb4'code' COLLATE utf8mb4_general_ci =
    _utf8mb4'code ' COLLATE utf8mb4_general_ci
        AS pad_space_equal,
    _utf8mb4'code' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'code ' COLLATE utf8mb4_0900_ai_ci
        AS no_pad_equal;
~~~

Kết quả khái quát:

| Biểu thức | Kết quả |
|---|---:|
| So sánh bằng PAD SPACE | 1 |
| So sánh bằng NO PAD | 0 |

Hai collation trong ví dụ còn khác nhau về quy tắc Unicode và phiên bản thuật toán. Mục đích ở đây là minh họa PAD_ATTRIBUTE; khi chọn collation thực tế, hãy đánh giá cả phân biệt hoa/thường, dấu, ký tự Unicode và khả năng tương thích ứng dụng.

### 2.2. Kiểm tra PAD_ATTRIBUTE trong MySQL

Không nên suy đoán từ tên collation. Hãy truy vấn metadata của server đang dùng:

~~~sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    PAD_ATTRIBUTE
FROM INFORMATION_SCHEMA.COLLATIONS
WHERE CHARACTER_SET_NAME = 'utf8mb4'
  AND COLLATION_NAME IN (
      'utf8mb4_general_ci',
      'utf8mb4_0900_ai_ci'
  );
~~~

Có thể xem thêm các collation có sẵn:

~~~sql
SHOW COLLATION
WHERE Charset = 'utf8mb4';
~~~

Thuộc tính `PAD_ATTRIBUTE` có trong metadata của các phiên bản MySQL hỗ trợ nó. Nếu đang dùng phiên bản cũ không có cột metadata này hoặc không có collation `_0900`, hãy tra danh sách collation đúng phiên bản server; không sao chép tên collation từ một máy MySQL khác.

## 3. Vì sao PAD SPACE ảnh hưởng đến UNIQUE?

UNIQUE index kiểm tra tính duy nhất theo quy tắc so sánh của kiểu dữ liệu và collation của các cột trong key. Nếu collation xem hai giá trị là bằng nhau, unique key xem chúng là một khóa trùng.

Với PAD SPACE, `'INV-42'` và `'INV-42 '` được so sánh bằng nhau. Do đó, một unique index trên cột VARCHAR có thể từ chối giá trị thứ hai.

### 3.1. Ví dụ UNIQUE với PAD SPACE

~~~sql
CREATE TABLE product_code_pad (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(40)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_general_ci
        NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_product_code (code)
) ENGINE = InnoDB;

INSERT INTO product_code_pad (code)
VALUES ('INV-42');

-- Có thể nhận lỗi Duplicate entry vì collation PAD SPACE
-- xem 'INV-42' và 'INV-42 ' là bằng nhau.
INSERT INTO product_code_pad (code)
VALUES ('INV-42 ');
~~~

Lệnh INSERT thứ hai bị lỗi trùng khóa. Dấu cách vẫn có thể tồn tại trong giá trị VARCHAR được lưu, nhưng collation không xem nó là khác biệt khi kiểm tra UNIQUE.

Ngoài khoảng trắng cuối, collation `utf8mb4_general_ci` cũng không phân biệt chữ hoa/chữ thường. Vì vậy, `'INV-42'` và `'inv-42'` cũng có thể xung đột. Một unique key phản ánh toàn bộ quy tắc collation, không chỉ PAD_ATTRIBUTE.

### 3.2. Ví dụ UNIQUE với NO PAD

~~~sql
CREATE TABLE product_code_no_pad (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(40)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_product_code (code)
) ENGINE = InnoDB;

INSERT INTO product_code_no_pad (code)
VALUES ('INV-42');

-- Được phép vì dấu cách cuối có ý nghĩa với NO PAD.
INSERT INTO product_code_no_pad (code)
VALUES ('INV-42 ');
~~~

Với collation NO PAD này, hai giá trị khác nhau vì dấu cách cuối được tính đến. Tuy nhiên, `_ai_ci` vẫn không phân biệt dấu và chữ hoa/chữ thường theo quy tắc của collation. Vì vậy, việc đổi sang NO PAD không đồng nghĩa mọi chuỗi khác byte đều trở thành khác nhau.

### 3.3. UNIQUE trên nhiều cột

Quy tắc collation vẫn áp dụng cho từng phần chuỗi trong composite unique index.

~~~sql
CREATE TABLE tenant_product (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    product_code VARCHAR(40)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_general_ci
        NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tenant_product_code (tenant_id, product_code)
) ENGINE = InnoDB;
~~~

Với cùng `tenant_id`, hai mã chỉ khác dấu cách cuối có thể bị xem là trùng nếu `product_code` dùng PAD SPACE. Với `tenant_id` khác nhau, composite key vẫn khác nhau.

Trong MySQL, unique index cho phép nhiều hàng có giá trị NULL ở một hoặc nhiều cột key vì NULL không được xem là bằng một giá trị NULL khác theo quy tắc kiểm tra unique. Nếu nghiệp vụ yêu cầu mọi mã phải có giá trị và duy nhất, hãy khai báo cột là NOT NULL thay vì chỉ dựa vào UNIQUE.

## 4. CHAR, VARCHAR và dữ liệu nhị phân

PAD SPACE/NO PAD không phải lý do duy nhất khiến dấu cách cuối khó xử lý. Kiểu cột cũng có quy tắc lưu trữ riêng.

| Kiểu | Đặc điểm | Khi dấu cách cuối quan trọng |
|---|---|---|
| CHAR(N) | Độ dài cố định; giá trị được đệm bằng dấu cách và dấu cách đệm thường bị loại khi đọc | Không phù hợp để bảo toàn sự khác biệt giữa các dấu cách cuối do người dùng nhập |
| VARCHAR(N) | Độ dài biến đổi; giữ dấu cách cuối trong giá trị được lưu và trả về | Có thể phân biệt theo collation NO PAD |
| BINARY(N) | Chuỗi byte độ dài cố định; đệm bằng byte 0x00 | So sánh theo byte, không theo PAD_ATTRIBUTE |
| VARBINARY(N) | Chuỗi byte độ dài biến đổi | Giữ và so sánh byte thực tế, phù hợp mã định danh nhị phân |
| TEXT | Chuỗi ký tự dài, dùng character set và collation | Hành vi so sánh phụ thuộc collation |
| BLOB | Dữ liệu nhị phân lớn | So sánh theo byte, không dùng collation ký tự |

Nếu nghiệp vụ coi dấu cách cuối là dữ liệu có ý nghĩa, `VARCHAR` với collation NO PAD thường phù hợp hơn `CHAR`. Nếu cần so sánh chính xác từng byte, cân nhắc `VARBINARY` và tự định nghĩa cách mã hóa dữ liệu.

Đừng đổi từ VARCHAR sang VARBINARY chỉ để tránh một lỗi duplicate. Thay đổi đó cũng làm mất các quy tắc so sánh ngôn ngữ như không phân biệt hoa/thường hoặc dấu, và ứng dụng phải chịu trách nhiệm xử lý byte, encoding và chuẩn hóa.

## 5. Collation còn ảnh hưởng những phép so sánh nào?

PAD_ATTRIBUTE tác động đến phép so sánh chuỗi, vì vậy ảnh hưởng không chỉ giới hạn ở câu lệnh INSERT vào unique key.

Các hoạt động thường bị ảnh hưởng:

- Phép so sánh `=`, `<>`, `<`, `>` và các điều kiện lọc.
- `GROUP BY` và `DISTINCT`, vì các giá trị được gom nhóm theo quy tắc so sánh.
- `ORDER BY`, vì collation quyết định thứ tự sắp xếp.
- Join giữa các cột chuỗi tương thích.
- Kiểm tra trùng dữ liệu trước khi thêm UNIQUE.
- Các ràng buộc khóa ngoại trên cột chuỗi, vốn yêu cầu kiểu và collation tương thích giữa hai phía.

`LIKE` có ngữ nghĩa so khớp mẫu riêng, được thực hiện theo ký tự; không nên suy luận kết quả LIKE hoàn toàn từ phép so sánh bằng. Nếu ứng dụng tìm chuỗi có dấu cách cuối bằng LIKE, hãy kiểm tra đúng biểu thức và collation thực tế.

Ngoài PAD_ATTRIBUTE, collation có thể coi các chuỗi khác nhau về hoa/thường, dấu, hoặc một số biến thể Unicode là bằng nhau. Ví dụ với collation không phân biệt dấu, `'cafe'` và `'café'` có thể so sánh bằng. Trước khi tạo UNIQUE, hãy kiểm tra toàn bộ quy tắc tương đương của collation đích.

## 6. Chẩn đoán dữ liệu có dấu cách cuối và nhóm có thể trùng

### 6.1. Xem dữ liệu thực tế

Khi nghi ngờ dữ liệu có khoảng trắng cuối, xem giá trị, số ký tự, số byte và biểu diễn HEX:

~~~sql
SELECT
    id,
    code,
    CHAR_LENGTH(code) AS character_count,
    OCTET_LENGTH(code) AS byte_count,
    HEX(code) AS hex_value
FROM external_identifier
ORDER BY id;
~~~

Ví dụ, nếu `code` là VARCHAR và hai hàng hiển thị gần giống nhau, HEX có thể cho thấy một hàng kết thúc bằng byte `20`, còn hàng kia không có byte đó.

Để tìm các giá trị có dấu cách ASCII ở cuối, có thể dùng biểu thức theo byte. Một cách đơn giản là so sánh độ dài trước và sau RTRIM:

~~~sql
SELECT
    id,
    code,
    HEX(code) AS hex_value,
    OCTET_LENGTH(code) AS original_bytes,
    OCTET_LENGTH(RTRIM(code)) AS trimmed_bytes
FROM external_identifier
WHERE OCTET_LENGTH(code) <> OCTET_LENGTH(RTRIM(code));
~~~

Điều kiện này tìm các dấu cách mà RTRIM loại bỏ. Nó không phát hiện mọi ký tự whitespace Unicode. Nếu nghiệp vụ cần xử lý tab, newline hoặc non-breaking space, phải xác định rõ tập ký tự cần chuẩn hóa và viết kiểm tra riêng.

### 6.2. Tìm các nhóm trùng theo collation đích

Giả sử chuẩn bị tạo unique key bằng `utf8mb4_general_ci`. Trước khi ALTER, có thể nhóm theo collation đích:

~~~sql
SELECT
    code COLLATE utf8mb4_general_ci AS comparison_value,
    COUNT(*) AS row_count,
    GROUP_CONCAT(id ORDER BY id) AS row_ids
FROM external_identifier
WHERE code IS NOT NULL
GROUP BY code COLLATE utf8mb4_general_ci
HAVING COUNT(*) > 1;
~~~

Truy vấn này tìm các nhóm mà collation đích xem là bằng nhau. Nó có thể phát hiện xung đột do:

- Dấu cách ASCII ở cuối theo PAD SPACE.
- Chữ hoa/chữ thường theo hậu tố `_ci`.
- Dấu theo hậu tố `_ai`.
- Những quy tắc tương đương Unicode khác của collation.

Nếu mục tiêu là `utf8mb4_0900_ai_ci`, hãy thay collation trong cả hai vị trí bằng collation đó. Luôn dùng đúng character set/collation dự kiến áp dụng cho cột đích.

Không dùng kết quả GROUP BY hiện tại của cột nếu collation hiện tại khác collation sắp chuyển sang. Hai collation có thể gom nhóm dữ liệu theo cách khác nhau.

### 6.3. Xem định nghĩa cột và index hiện tại

~~~sql
SHOW CREATE TABLE external_identifier;

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_identifier';

SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_identifier'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

`SHOW CREATE TABLE` giúp xem đầy đủ unique key, prefix index và collation khai báo. Metadata giúp xác định cột nào có character set/collation riêng thay vì kế thừa mặc định từ table hoặc database.

## 7. Thay đổi collation hoặc thêm UNIQUE an toàn

Một migration đổi collation có thể làm thay đổi nhóm giá trị được xem là bằng nhau. Nếu collation mới dùng PAD SPACE hoặc có quy tắc case/accent khác, những hàng trước đây hợp lệ có thể trở thành trùng theo unique key mới.

Ví dụ, cột hiện đang dùng NO PAD và chứa cả `'ACCT-9'` lẫn `'ACCT-9 '`. Nếu chuyển sang PAD SPACE rồi thêm UNIQUE, hai giá trị có thể xung đột.

### Bước 1: Ghi nhận trạng thái hiện tại

~~~sql
SHOW CREATE TABLE external_identifier;

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_identifier';
~~~

Ghi lại collation hiện tại, kiểu cột, độ dài, NULL, default, index và các thuộc tính khác cần giữ khi dùng MODIFY COLUMN.

### Bước 2: Chọn quy tắc so sánh theo nghiệp vụ

Hãy quyết định rõ:

- Mã có phân biệt chữ hoa/chữ thường không?
- Dấu tiếng Việt có phân biệt không?
- Dấu cách cuối có phải một phần hợp lệ của mã không?
- Có cần bảo toàn chính xác chuỗi người dùng nhập không?
- Mã có cần chuẩn hóa trước khi lưu không?

Nếu dấu cách cuối không mang ý nghĩa nghiệp vụ, có thể chuẩn hóa dữ liệu đầu vào ở ứng dụng hoặc trong migration sau khi xác định cách xử lý các bản ghi đã tồn tại. Nếu dấu cách có ý nghĩa, chọn kiểu/collation giữ được sự khác biệt đó.

Không tự động TRIM toàn bộ dữ liệu trước khi hỏi nghiệp vụ. Hai mã khác nhau có thể bị gộp nhầm nếu khoảng trắng thực sự có ý nghĩa.

### Bước 3: Tìm xung đột theo collation đích

Dùng GROUP BY với collation dự kiến như phần trước. Xử lý mọi nhóm trùng trước khi thêm unique key. Với cột nullable, nhớ rằng UNIQUE của MySQL cho phép nhiều NULL; nếu cần tính duy nhất cho mọi hàng, cân nhắc NOT NULL.

### Bước 4: Làm sạch hoặc ánh xạ dữ liệu

Nếu nghiệp vụ xác nhận dấu cách cuối là không cần thiết, có thể chuẩn hóa có kiểm soát. Ví dụ minh họa cho một cột VARCHAR:

~~~sql
UPDATE external_identifier
SET code = RTRIM(code)
WHERE OCTET_LENGTH(code) <> OCTET_LENGTH(RTRIM(code));
~~~

Đây chỉ là ví dụ sau khi đã quyết định quy tắc dữ liệu. Trước khi chạy trên bảng lớn, cần sao lưu phù hợp, xác định các hàng sẽ thay đổi, kiểm tra xung đột mới sau chuẩn hóa và thực hiện theo lô nếu cần. Nếu hai hàng trở thành cùng mã, phải có quy tắc chọn bản ghi chuẩn, chuyển tham chiếu và xử lý dữ liệu phụ thuộc.

### Bước 5: Ngăn dữ liệu trùng phát sinh trong lúc migration

Một truy vấn kiểm tra trước migration không khóa được tương lai. Ứng dụng vẫn có thể ghi thêm một giá trị gây xung đột sau khi kiểm tra nhưng trước khi tạo UNIQUE.

Hãy chọn cơ chế kiểm soát ghi trong cửa sổ chuyển đổi: triển khai validation tương thích, tạm dừng luồng ghi liên quan, dùng trạng thái migration hoặc biện pháp điều phối phù hợp với kiến trúc. Unique index sau cùng vẫn là ràng buộc có thẩm quyền ở database.

### Bước 6: Đổi collation và tạo unique key

Ví dụ minh họa nếu cột đã được làm sạch và collation đích là NO PAD:

~~~sql
ALTER TABLE external_identifier
    MODIFY COLUMN code VARCHAR(64)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    ADD UNIQUE KEY uq_external_identifier_code (code);
~~~

Phải khai báo lại đầy đủ thuộc tính cột thực tế, chẳng hạn DEFAULT, COMMENT và các thuộc tính khác. Đừng dùng nguyên câu lệnh trên nếu cột của bạn có định nghĩa khác.

DDL có thể cần metadata lock và có thể rebuild table tùy thay đổi, phiên bản MySQL, storage engine và kích thước dữ liệu. Hãy thử trên bản sao dữ liệu đại diện, ước lượng dung lượng tạm, thời gian, I/O và replication lag. Không giả định mọi ALTER TABLE đều instant hoặc không khóa.

### Bước 7: Xác minh sau migration

~~~sql
SHOW CREATE TABLE external_identifier;

SELECT
    code,
    COUNT(*) AS row_count
FROM external_identifier
WHERE code IS NOT NULL
GROUP BY code
HAVING COUNT(*) > 1;

SHOW INDEX FROM external_identifier;
~~~

Kiểm tra thêm các trường hợp biên bằng những lần ghi thử trên môi trường test:

- Hai chuỗi chỉ khác dấu cách cuối.
- Hai chuỗi chỉ khác chữ hoa/chữ thường.
- Hai chuỗi chỉ khác dấu.
- Chuỗi có ký tự Unicode nhiều byte.
- Giá trị NULL nếu cột cho phép NULL.

Xác nhận hành vi thực tế phù hợp với hợp đồng dữ liệu của ứng dụng và các hệ thống tích hợp.

## 8. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ VARCHAR luôn phân biệt dấu cách cuối | Có thể gặp Duplicate entry dù hai chuỗi nhìn khác nhau | Kiểm tra PAD_ATTRIBUTE của collation |
| Chỉ nhìn dữ liệu hiển thị | Không nhận ra byte 0x20 cuối chuỗi | Kiểm tra HEX, CHAR_LENGTH và OCTET_LENGTH |
| Đổi sang NO PAD rồi cho rằng mọi giá trị đều khác nhau | Case/accent-insensitive vẫn có thể gom nhiều chuỗi thành một | Kiểm tra toàn bộ quy tắc collation |
| Dùng TRIM mà chưa có quy tắc nghiệp vụ | Làm mất dữ liệu có ý nghĩa | Xác định chuẩn mã và lập kế hoạch ánh xạ |
| Kiểm tra trùng bằng collation cũ | Bỏ sót xung đột theo collation đích | GROUP BY với collation sẽ áp dụng |
| Chỉ kiểm tra dữ liệu một lần trước ALTER | Ghi đồng thời có thể tạo duplicate mới | Kiểm soát luồng ghi đến khi unique key được tạo |
| Nghĩ BINARY/VARBINARY cũng dùng PAD_ATTRIBUTE | Nhầm quy tắc chuỗi với quy tắc byte | Phân biệt dữ liệu ký tự và dữ liệu nhị phân |
| Bỏ qua CHAR khi điều tra dấu cách | CHAR có quy tắc đệm và loại bỏ dấu cách riêng | Dùng VARCHAR nếu cần bảo toàn dấu cách cuối |

## 9. Bài tập thực hành

### Bài 1: So sánh PAD SPACE và NO PAD

Chạy hai biểu thức so sánh ở phần 2.1. Thay đổi chuỗi để kiểm tra chữ hoa/chữ thường và dấu. Ghi nhận khác biệt nào đến từ PAD_ATTRIBUTE, khác biệt nào đến từ thuộc tính ci/ai.

### Bài 2: Quan sát UNIQUE với PAD SPACE

Tạo bảng `product_code_pad`, chèn `'INV-42'`, sau đó thử chèn `'INV-42 '`. Ghi lại lỗi và kiểm tra giá trị đã lưu bằng HEX.

### Bài 3: Quan sát UNIQUE với NO PAD

Tạo bảng `product_code_no_pad`, chèn hai giá trị chỉ khác dấu cách cuối. Xác nhận cả hai tồn tại. Sau đó thử chèn giá trị chỉ khác chữ hoa/chữ thường để hiểu rằng NO PAD không đồng nghĩa binary comparison.

### Bài 4: Tìm duplicate trước khi tạo unique index

Tạo bảng dữ liệu mã hàng có nhiều giá trị gần giống. Chạy GROUP BY với collation PAD SPACE và NO PAD. So sánh các nhóm xung đột.

### Bài 5: Diễn tập đổi collation

Trên database thực hành riêng, tạo dữ liệu có dấu cách cuối, chữ hoa/thường và dấu. Chọn collation đích, tìm nhóm xung đột, xây dựng quy tắc chuẩn hóa và thử tạo UNIQUE. Ghi lại trường hợp nào được chấp nhận và trường hợp nào bị từ chối.

## Kết luận

PAD SPACE và NO PAD là thuộc tính của collation, quyết định dấu cách ASCII ở cuối chuỗi có được xem là phần đệm khi so sánh hay không. Vì UNIQUE index tuân theo quy tắc so sánh của cột, hai chuỗi có byte khác nhau vẫn có thể xung đột.

Trước khi tạo unique key hoặc đổi collation, hãy kiểm tra metadata, xem byte thực tế, nhóm dữ liệu theo collation đích và xử lý xung đột theo quy tắc nghiệp vụ. Việc kiểm soát luồng ghi trong lúc migration và xác minh sau DDL giúp bảo vệ tính duy nhất của dữ liệu trong suốt quá trình thay đổi.

