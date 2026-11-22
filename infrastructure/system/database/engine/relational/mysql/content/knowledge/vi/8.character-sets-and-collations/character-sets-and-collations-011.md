# Chuyển bộ ký tự/collation và đánh giá dữ liệu trùng sau chuyển đổi

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Khi thay đổi character set hoặc collation, cần hiểu dữ liệu đang được lưu bằng encoding nào, quy tắc so sánh mới ảnh hưởng ra sao và liệu các giá trị trước đây được xem là khác nhau có trở thành tương đương hay không.

Một lần chuyển đổi có thể tác động đến dữ liệu, index, unique constraint, foreign key và hành vi tìm kiếm của ứng dụng. Đặc biệt, đổi sang collation không phân biệt hoa/thường hoặc dấu có thể làm xuất hiện xung đột duy nhất. Vì vậy, quy trình đúng phải kiểm tra dữ liệu theo chính character set và collation đích trước khi thay đổi schema.

## 1. Phân biệt chuyển character set và chuyển collation

Character set xác định cách mã hóa ký tự thành byte và tập ký tự có thể biểu diễn. Collation xác định cách so sánh, sắp xếp và xác định hai chuỗi có tương đương trong các phép so sánh hay không.

| Thay đổi | Điều thay đổi | Ví dụ |
|---|---|---|
| Character set | Encoding dùng để lưu ký tự | latin1 sang utf8mb4 |
| Collation | Quy tắc so sánh và sắp xếp chuỗi | utf8mb4_bin sang utf8mb4_0900_ai_ci |
| Cả hai | Encoding và quy tắc so sánh | latin1/latin1_swedish_ci sang utf8mb4/utf8mb4_0900_ai_ci |

Đổi collation trong cùng character set thường không yêu cầu thay đổi ý nghĩa ký tự được lưu, nhưng làm thay đổi phép so sánh, thứ tự sắp xếp, kết quả GROUP BY, JOIN và ràng buộc UNIQUE. Đổi character set yêu cầu MySQL chuyển các ký tự từ encoding nguồn sang encoding đích; nếu encoding nguồn được khai báo sai hoặc dữ liệu đã bị hỏng trước đó, thao tác chuyển đổi có thể giữ nguyên hoặc làm nặng thêm văn bản lỗi.

Không coi việc đổi charset/collation là thao tác đổi tên thuộc tính đơn giản. Hãy xác định chính xác mục tiêu: chuẩn hóa encoding, thay đổi quy tắc so sánh hay sửa dữ liệu đã bị mã hóa sai.

## 2. Hiểu dữ liệu trước khi chuyển đổi

### 2.1. Dữ liệu ký tự gồm byte và metadata

MySQL diễn giải dữ liệu chuỗi dựa trên character set được khai báo cho cột và charset của kết nối. Khi client gửi chuỗi, server chuyển dữ liệu từ character set của client sang character set đích của cột. Khi đọc dữ liệu, server chuyển đổi kết quả theo charset của kết nối.

Do đó, văn bản hiển thị sai có thể xuất phát từ nhiều nơi:

- Byte đã được ghi sai vào cột do client khai báo sai charset khi gửi dữ liệu.
- Cột khai báo charset không khớp với encoding thực tế của byte được lưu.
- Dữ liệu được lưu đúng nhưng client đọc kết quả bằng charset không phù hợp.
- Quá trình export/import dùng charset khác với nguồn hoặc đích.

Chỉ nhìn chuỗi hiển thị trên terminal hoặc giao diện không đủ để xác định byte trong database có sai hay không. Trước khi sửa dữ liệu, cần kiểm tra metadata của cột, charset kết nối và biểu diễn byte của một số mẫu đã biết.

### 2.2. Kiểm tra charset và collation hiện tại

Xem charset/collation ở cấp server và session:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';

SHOW SESSION VARIABLES LIKE 'character_set%';
SHOW SESSION VARIABLES LIKE 'collation%';
~~~

Các biến kết nối cần chú ý gồm:

- character_set_client: charset mà server dùng để diễn giải dữ liệu client gửi.
- character_set_connection: charset dùng trong quá trình xử lý biểu thức chuỗi ở connection.
- character_set_results: charset dùng khi server gửi kết quả về client.
- collation_connection: collation mặc định cho các biểu thức chuỗi liên quan đến connection.

Xem charset/collation của database:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';
~~~

Xem thuộc tính của các cột chuỗi trong một bảng:

~~~sql
SELECT COLUMN_NAME,
       COLUMN_TYPE,
       IS_NULLABLE,
       CHARACTER_SET_NAME,
       COLLATION_NAME,
       CHARACTER_MAXIMUM_LENGTH,
       CHARACTER_OCTET_LENGTH
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

CHARACTER_MAXIMUM_LENGTH thể hiện giới hạn theo ký tự; CHARACTER_OCTET_LENGTH thể hiện giới hạn theo byte. Hai giá trị này giúp đánh giá tác động khi chuyển sang charset có số byte tối đa trên mỗi ký tự lớn hơn.

Xem định nghĩa thực tế của bảng:

~~~sql
SHOW CREATE TABLE sales.customers;
~~~

SHOW CREATE TABLE giúp kiểm tra đầy đủ kiểu cột, NULL/NOT NULL, DEFAULT, index, foreign key, generated column, comment và các thuộc tính khác cần được giữ khi thay đổi định nghĩa.

### 2.3. Kiểm tra charset đích có được hỗ trợ

Không giả định mọi phiên bản MySQL đều có cùng danh sách collation:

~~~sql
SHOW CHARACTER SET LIKE 'utf8mb4';
SHOW COLLATION WHERE Charset = 'utf8mb4';
~~~

Ví dụ, utf8mb4_0900_ai_ci thuộc dòng MySQL 8.0; không có sẵn trên MySQL 5.7. Hãy chọn collation có trong đúng phiên bản và kiểm tra cả môi trường production lẫn môi trường khôi phục.

Trong MySQL, tên utf8 từng được dùng như alias cho utf8mb3. Nếu cần hỗ trợ đầy đủ Unicode, bao gồm ký tự ngoài BMP như nhiều emoji, hãy dùng utf8mb4 và kiểm tra khả năng tương thích của ứng dụng, driver và schema.

## 3. Chọn mục tiêu chuyển đổi

### 3.1. Chuyển sang utf8mb4

utf8mb4 là lựa chọn phổ biến cho dữ liệu Unicode hiện đại. Mỗi ký tự có thể cần từ 1 đến 4 byte. Khi chuyển từ charset có giới hạn nhỏ hơn như latin1 hoặc utf8mb3 sang utf8mb4, MySQL chuyển ký tự theo encoding nguồn đã khai báo.

Ví dụ mục tiêu:

~~~sql
ALTER DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh này chỉ đổi mặc định charset/collation của database cho các đối tượng được tạo sau đó. Nó không tự chuyển các bảng và cột hiện có. Muốn chuyển dữ liệu đang tồn tại, cần thao tác ở cấp bảng hoặc cột.

### 3.2. Chỉ đổi collation

Nếu cột đã dùng utf8mb4 và mục tiêu chỉ là thay quy tắc so sánh, có thể giữ nguyên character set và chọn collation mới. Ví dụ chuyển từ collation nhị phân sang collation không phân biệt hoa/thường và dấu:

~~~sql
ALTER TABLE customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Lệnh trên áp dụng cho các cột ký tự trong bảng và đặt collation đích. Dù charset giữ nguyên, cách so sánh chuỗi sẽ thay đổi. Hãy kiểm tra trùng lặp trước khi thực hiện nếu có UNIQUE index trên các cột liên quan.

### 3.3. Chuyển một cột riêng lẻ

Nếu chỉ một cột cần đổi, dùng MODIFY COLUMN với định nghĩa đầy đủ:

~~~sql
ALTER TABLE customers
  MODIFY COLUMN email VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL;
~~~

Khi dùng MODIFY COLUMN, cần khai báo lại mọi thuộc tính cần giữ như kiểu dữ liệu, độ dài, NULL/NOT NULL, DEFAULT, COMMENT, generated expression và các thuộc tính khác. Nếu bỏ sót thuộc tính, định nghĩa cột sau thay đổi có thể khác định nghĩa ban đầu. Luôn xem SHOW CREATE TABLE trước và sau migration.

### 3.4. Đổi mặc định của bảng không chuyển cột hiện có

Lệnh sau đổi mặc định cho bảng:

~~~sql
ALTER TABLE customers
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Nó điều chỉnh mặc định của bảng cho các cột ký tự được tạo sau đó. Nó không tự chuyển charset/collation của các cột đã tồn tại. Phân biệt rõ:

| Câu lệnh | Phạm vi tác động |
|---|---|
| ALTER DATABASE ... CHARACTER SET ... | Mặc định của database |
| ALTER TABLE ... DEFAULT CHARACTER SET ... | Mặc định của bảng |
| ALTER TABLE ... CONVERT TO CHARACTER SET ... | Chuyển các cột ký tự hiện có trong bảng |
| ALTER TABLE ... MODIFY COLUMN ... CHARACTER SET ... | Chuyển và đặt thuộc tính cho cột được chỉ định |

## 4. Chuyển đổi dữ liệu hiện có

### 4.1. CONVERT TO CHARACTER SET

Để chuyển các cột ký tự trong một bảng sang charset/collation đích:

~~~sql
ALTER TABLE customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

MySQL chuyển dữ liệu chuỗi từ character set được khai báo hiện tại sang charset đích và áp dụng collation đích cho các cột ký tự. Cột dạng binary như BINARY, VARBINARY và BLOB không được xử lý như cột văn bản theo cùng cách.

Khi chuyển đổi, MySQL có thể điều chỉnh kiểu dữ liệu văn bản như TEXT sang một kiểu TEXT lớn hơn để duy trì khả năng lưu số ký tự tối đa khi charset đích cần nhiều byte hơn. Vì vậy, phải xem lại SHOW CREATE TABLE sau chuyển đổi, không giả định kiểu cột và kích thước lưu trữ luôn giữ nguyên.

### 4.2. MODIFY COLUMN cho một cột

Ví dụ cột ghi chú cần chuyển riêng:

~~~sql
ALTER TABLE support_tickets
  MODIFY COLUMN note TEXT
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NULL;
~~~

Nếu cột ban đầu có DEFAULT, COMMENT hoặc thuộc tính khác, phải giữ lại trong định nghĩa MODIFY. Với cột có index, generated column hoặc ràng buộc liên quan, kiểm tra phụ thuộc trước khi sửa.

### 4.3. Chuyển đổi chuỗi bằng CONVERT và CAST để kiểm tra

Có thể kiểm tra biểu diễn sau khi chuyển mà chưa thay đổi cột:

~~~sql
SELECT
    username,
    CONVERT(username USING utf8mb4) AS username_utf8mb4,
    CHARSET(CONVERT(username USING utf8mb4)) AS target_charset,
    COLLATION(CONVERT(username USING utf8mb4)) AS expression_collation
FROM users
LIMIT 20;
~~~

CONVERT(expr USING charset) chuyển biểu thức sang character set được chỉ định. Đây là công cụ để kiểm tra hoặc xây dựng biểu thức truy vấn; nó không thay đổi định nghĩa cột hay dữ liệu đang lưu.

Nếu cần đặt collation cho biểu thức thử nghiệm:

~~~sql
SELECT CONVERT(username USING utf8mb4)
         COLLATE utf8mb4_0900_ai_ci AS normalized_username
FROM users;
~~~

Chỉ dùng collation đã được xác nhận có trong server. Biểu thức này hữu ích khi mô phỏng phép so sánh theo collation đích trước migration.

## 5. Đánh giá dữ liệu trùng theo collation đích

### 5.1. Vì sao đổi collation có thể tạo xung đột?

Hai chuỗi khác nhau theo collation hiện tại có thể được xem là bằng nhau theo collation đích. Ví dụ, collation có hậu tố ai_ci không phân biệt dấu và hoa/thường. Những cặp như sau có thể trở thành tương đương trong so sánh:

| Giá trị thứ nhất | Giá trị thứ hai | Khả năng dưới collation ai_ci |
|---|---|---|
| Admin | admin | Có thể bằng nhau do không phân biệt hoa/thường |
| resume | résumé | Có thể bằng nhau do không phân biệt dấu |
| A | a | Có thể bằng nhau do không phân biệt hoa/thường |

Kết quả cụ thể phụ thuộc collation đích và quy tắc Unicode mà collation đó sử dụng. Không tự viết hàm LOWER hoặc loại dấu để phỏng đoán kết quả; hãy yêu cầu chính MySQL so sánh theo collation sẽ dùng sau migration.

Nếu cột có UNIQUE index, hai giá trị trước đây khác nhau có thể vi phạm tính duy nhất sau khi chuyển. MySQL sẽ từ chối tạo hoặc duy trì unique index nếu dữ liệu sau chuyển đổi không còn duy nhất. Không có cơ chế tự động gộp hai hàng thành một; cần xử lý xung đột theo quy tắc nghiệp vụ trước.

### 5.2. Liệt kê nhóm trùng theo collation đích

Giả sử users.username hiện đang dùng charset khác hoặc collation khác. Kiểm tra theo charset/collation đích:

~~~sql
SELECT
    CONVERT(username USING utf8mb4)
      COLLATE utf8mb4_0900_ai_ci AS target_username,
    COUNT(*) AS duplicate_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

Truy vấn gom các giá trị được xem là bằng nhau theo collation đích và chỉ liệt kê nhóm có nhiều hơn một hàng. Điều kiện username IS NOT NULL phù hợp khi kiểm tra một UNIQUE index đơn cột, vì MySQL cho phép nhiều giá trị NULL trong unique index.

Nếu cột đã là utf8mb4, có thể bỏ CONVERT và chỉ định collation:

~~~sql
SELECT username COLLATE utf8mb4_0900_ai_ci AS target_username,
       COUNT(*) AS duplicate_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

Nếu collation đích thuộc một charset khác với charset biểu thức nguồn, cần chuyển biểu thức sang charset đích trước khi áp dụng COLLATE.

### 5.3. Xem các hàng tạo thành xung đột

Để xác định các bản ghi cụ thể trong nhóm trùng:

~~~sql
SELECT
    a.user_id AS first_id,
    a.username AS first_username,
    b.user_id AS second_id,
    b.username AS second_username
FROM users AS a
JOIN users AS b
  ON a.user_id < b.user_id
 AND CONVERT(a.username USING utf8mb4) COLLATE utf8mb4_0900_ai_ci
     = CONVERT(b.username USING utf8mb4) COLLATE utf8mb4_0900_ai_ci
WHERE a.username IS NOT NULL
  AND b.username IS NOT NULL
ORDER BY a.user_id, b.user_id;
~~~

Điều kiện user_id < b.user_id tránh trả cả cặp đảo ngược và tự ghép một hàng với chính nó. Thay user_id bằng primary key thực tế của bảng. Nếu một nhóm có nhiều hơn hai hàng, truy vấn sẽ trả nhiều cặp; cần tổng hợp kết quả trước khi quyết định bản ghi nào được giữ.

### 5.4. Kiểm tra UNIQUE index ghép

Giả sử có unique index trên (tenant_id, username). Khi mô phỏng xung đột, phải so sánh toàn bộ các thành phần của khóa:

~~~sql
SELECT tenant_id,
       CONVERT(username USING utf8mb4)
         COLLATE utf8mb4_0900_ai_ci AS target_username,
       COUNT(*) AS duplicate_count
FROM users
WHERE tenant_id IS NOT NULL
  AND username IS NOT NULL
GROUP BY tenant_id, target_username
HAVING COUNT(*) > 1;
~~~

Với UNIQUE index ghép của MySQL, các hàng có ít nhất một thành phần khóa là NULL có thể cùng tồn tại mà không vi phạm uniqueness. Do đó, khi kiểm tra xung đột cho unique index, chỉ nhóm các hàng mà mọi thành phần của khóa đều không NULL. Nếu nghiệp vụ yêu cầu duy nhất kể cả khi có NULL, cần mô hình hóa quy tắc riêng.

### 5.5. Index dùng prefix hoặc biểu thức

Nếu unique index chỉ đánh index một prefix của cột chuỗi, việc kiểm tra phải mô phỏng đúng prefix và collation của index. Ví dụ index trên 20 ký tự đầu của username cần được kiểm tra theo biểu thức tương đương LEFT(..., 20), không chỉ nhóm theo toàn bộ username:

~~~sql
SELECT
    LEFT(
      CONVERT(username USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
      20
    ) AS target_prefix,
    COUNT(*) AS duplicate_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_prefix
HAVING COUNT(*) > 1;
~~~

Với functional index hoặc generated column được dùng trong unique key, phải mô phỏng chính biểu thức được index sử dụng. Kiểm tra SHOW CREATE TABLE và INFORMATION_SCHEMA.STATISTICS để xác định index, thứ tự cột, prefix length và thuộc tính liên quan.

### 5.6. Quy tắc khoảng trắng và Unicode

Collation còn có thể khác nhau ở quy tắc xử lý khoảng trắng cuối chuỗi. Một số collation dùng PAD SPACE, số khác dùng NO PAD. Vì vậy, chuỗi có dấu cách cuối có thể được so sánh khác nhau tùy collation. Hãy kiểm tra thuộc tính collation trên phiên bản hỗ trợ:

~~~sql
SELECT COLLATION_NAME, CHARACTER_SET_NAME, PAD_ATTRIBUTE
FROM information_schema.COLLATIONS
WHERE COLLATION_NAME = 'utf8mb4_0900_ai_ci';
~~~

Một số collation Unicode cũng áp dụng quy tắc so sánh tương đương cho các chuỗi có cách biểu diễn Unicode khác nhau. Không chỉ kiểm tra chữ hoa/thường và dấu tiếng Việt; hãy thử dữ liệu thật của ứng dụng, gồm ký tự tổ hợp, khoảng trắng, dấu câu và ký tự ngoài BMP nếu có.

## 6. Kiểm tra ảnh hưởng đến index và ràng buộc

### 6.1. Unique index

Unique index đảm bảo tính duy nhất theo quy tắc so sánh của collation gắn với cột/index. Khi đổi collation, tập giá trị được coi là bằng nhau có thể thay đổi. Nếu dữ liệu tạo ra xung đột, ALTER TABLE có thể thất bại khi xây dựng lại index.

Kiểm tra index hiện có:

~~~sql
SELECT INDEX_NAME,
       NON_UNIQUE,
       SEQ_IN_INDEX,
       COLUMN_NAME,
       SUB_PART,
       COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'users'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

NON_UNIQUE = 0 cho biết index là unique. SUB_PART cho biết prefix length nếu index chỉ dùng một phần cột. Xem thêm SHOW CREATE TABLE để hiểu toàn bộ định nghĩa.

### 6.2. Primary key và foreign key dạng chuỗi

Nếu primary key hoặc foreign key chứa cột chuỗi, thay đổi charset/collation có thể ảnh hưởng đến index và quan hệ tham chiếu. Các cột chuỗi tương ứng trong foreign key của InnoDB cần có kiểu tương thích và cùng character set/collation. Không chuyển một phía của quan hệ rồi bỏ qua phía còn lại.

Trước migration:

- Liệt kê bảng cha, bảng con và các cột chuỗi trong foreign key.
- Xác định index hỗ trợ foreign key và unique constraint liên quan.
- Lập thứ tự chuyển đổi cả hai phía.
- Nếu cần tạm tháo constraint, phải có kế hoạch khóa ghi, xác minh dữ liệu tham chiếu và tạo lại constraint ngay sau chuyển đổi.
- Kiểm tra kiểu, charset và collation của cả hai phía sau migration.

Không dùng SET FOREIGN_KEY_CHECKS = 0 như cách bỏ qua phân tích. Tắt kiểm tra không tự xác minh lại mọi dữ liệu khi bật lại; cần kiểm tra tính toàn vẹn và tạo lại constraint có kiểm soát.

### 6.3. Độ dài index sau khi chuyển sang utf8mb4

utf8mb4 có thể cần tối đa 4 byte cho mỗi ký tự. Một index từng vừa giới hạn byte với charset cũ có thể vượt giới hạn sau khi chuyển. Giới hạn khóa phụ thuộc phiên bản MySQL, InnoDB page size, row format và loại index. Hãy kiểm tra độ dài khóa ghép và prefix index theo cấu hình thực tế.

Không cắt ngắn cột hoặc prefix chỉ để ALTER chạy thành công mà chưa đánh giá ảnh hưởng đến tính duy nhất và tìm kiếm. Nếu index không thể tạo vì vượt giới hạn, xem lại thiết kế khóa, độ dài cột, prefix, row format và phiên bản trước khi quyết định.

## 7. Dữ liệu đã bị mã hóa sai: đừng chuyển đổi mù quáng

Có hai tình huống cần phân biệt:

1. **Dữ liệu được lưu đúng, client hiển thị sai:** byte và metadata cột phù hợp nhưng charset kết nối hoặc terminal không đúng. Điều chỉnh connection/client charset có thể giải quyết mà không cần sửa dữ liệu.
2. **Dữ liệu đã bị ghi sai:** byte được ghi theo một encoding nhưng server diễn giải theo encoding khác, khiến nội dung lưu trữ đã thành văn bản lỗi. Chuyển cột sang utf8mb4 theo metadata hiện tại có thể chỉ chuyển phần văn bản lỗi đó sang encoding mới.

Kiểm tra một số mẫu:

~~~sql
SELECT
    id,
    display_name,
    HEX(display_name) AS stored_bytes,
    CHARSET(display_name) AS declared_charset,
    COLLATION(display_name) AS declared_collation
FROM customers
WHERE id IN (101, 102, 103);
~~~

So sánh stored_bytes với chuỗi gốc đã biết và metadata cột. Đồng thời kiểm tra charset của connection:

~~~sql
SHOW SESSION VARIABLES LIKE 'character_set_client';
SHOW SESSION VARIABLES LIKE 'character_set_connection';
SHOW SESSION VARIABLES LIKE 'character_set_results';
~~~

Nếu nghi ngờ dữ liệu bị mojibake, hãy sao chép một tập mẫu sang database thử nghiệm và thử quy trình khôi phục trên bản sao. Không áp dụng các chuỗi CAST/CONVERT qua BINARY trên toàn bộ production nếu chưa xác định chính xác encoding gốc và cách byte được ghi. Một phép chuyển đổi sai có thể làm mất khả năng khôi phục nội dung ban đầu.

## 8. Quy trình migration an toàn

Chuyển charset/collation trên bảng lớn có thể rebuild bảng và index, tiêu tốn CPU, I/O, dung lượng tạm và thời gian. Quy trình cần được thử trên dữ liệu đại diện trước khi áp dụng production.

ALTER TABLE là DDL và gây implicit commit theo quy tắc MySQL. Không đặt migration trong transaction ứng dụng rồi kỳ vọng ROLLBACK sẽ hoàn tác thay đổi schema. Cần chuẩn bị backup, cửa sổ triển khai và phương án khôi phục riêng.

### Bước 1 — Xác định phạm vi

Liệt kê database, bảng, cột văn bản, charset/collation hiện tại, index, foreign key, generated column và các ứng dụng ghi/đọc dữ liệu. Phân biệt thay đổi mặc định với chuyển đổi cột hiện có.

### Bước 2 — Chốt mục tiêu và tương thích

Chọn character set và collation có trên phiên bản MySQL đích. Xác minh driver, client, migration tool, replication topology và các môi trường phục hồi đều hỗ trợ. Ghi lại yêu cầu so sánh: có phân biệt dấu, hoa/thường, khoảng trắng cuối chuỗi hay không.

### Bước 3 — Backup và kiểm tra restore

Tạo backup có thể khôi phục và kiểm tra restore trên môi trường độc lập. Với InnoDB, logical dump có thể dùng consistent snapshot, nhưng cần đánh giá DDL đồng thời và các đối tượng ngoài transaction. Backup phải bao gồm dữ liệu cùng các đối tượng cần thiết như routine, trigger, event và quyền triển khai theo yêu cầu.

Không coi việc có file backup là bằng chứng đủ. Chỉ bắt đầu migration khi đã chứng minh có thể khôi phục dữ liệu và cấu hình.

### Bước 4 — Tạo bản sao thử nghiệm

Khôi phục backup vào môi trường staging có phiên bản, charset/collation và cấu hình gần với production. Thử migration trên bản sao có quy mô và phân bố dữ liệu đại diện. Ghi lại thời gian, dung lượng, lock, warning và lỗi.

### Bước 5 — Kiểm tra dữ liệu trùng trước

Chạy các truy vấn mô phỏng collation đích cho từng unique index, bao gồm unique key ghép, prefix index và functional index. Lưu danh sách khóa xung đột và xác định chủ sở hữu nghiệp vụ của từng bản ghi. Không tự xóa hoặc gộp bản ghi chỉ để migration vượt qua.

### Bước 6 — Xử lý xung đột

Lựa chọn cách giải quyết theo nghiệp vụ:

- Chuẩn hóa một giá trị và cập nhật các tham chiếu đến bản ghi đó.
- Đổi một trong các giá trị bị trùng theo quy tắc đặt tên đã thống nhất.
- Giữ collation phân biệt hoa/thường hoặc dấu nếu đó là yêu cầu thật của nghiệp vụ.
- Thiết kế lại khóa duy nhất, ví dụ đưa tenant hoặc phạm vi tổ chức vào unique key nếu tính duy nhất chỉ có ý nghĩa trong phạm vi đó.

Trước khi gộp hai bản ghi, kiểm tra foreign key, lịch sử giao dịch, dữ liệu liên quan và khóa ngoại ở các hệ thống khác. Chuyển đổi charset/collation không phải lý do hợp lệ để tự động xóa dữ liệu.

### Bước 7 — Chuyển đổi trong cửa sổ triển khai

Chọn cách chuyển đổi phù hợp với kích thước bảng và mức downtime cho phép. Với bảng nhỏ có thể dùng ALTER TABLE trực tiếp sau khi backup. Với bảng lớn, đánh giá online DDL hoặc công cụ migration theo kiểu shadow table; kiểm tra khả năng hỗ trợ của phiên bản, engine và loại thay đổi cụ thể.

Trong thời gian chuyển đổi, kiểm soát ghi đồng thời để không phát sinh giá trị trùng mới sau bước kiểm tra. Nếu dùng shadow table, cần có cơ chế đồng bộ thay đổi, đối chiếu số hàng và cutover có kiểm soát.

### Bước 8 — Xác minh sau chuyển đổi

- Đọc SHOW CREATE TABLE và INFORMATION_SCHEMA để xác nhận charset/collation của mọi cột mục tiêu.
- So sánh số hàng, số lượng NULL, độ dài chuỗi và các giá trị mẫu trước/sau.
- Chạy lại các truy vấn phát hiện duplicate theo collation đích.
- Xác minh unique index, foreign key và các constraint đã được tạo lại.
- Thử insert, update, lookup, sort, join và tìm kiếm với dữ liệu tiếng Việt, ký tự hoa/thường, dấu và ký tự Unicode ngoài BMP.
- Theo dõi error log, replication lag, thời gian truy vấn và lỗi ứng dụng sau cutover.

### Bước 9 — Giữ đường khôi phục

Giữ backup và bản sao cũ trong khoảng thời gian được quy định. Nếu có vấn đề, dừng ghi hoặc chuyển ứng dụng về cấu hình cũ theo kế hoạch đã thử. Không giả định đổi ngược collation hoặc charset luôn khôi phục byte ban đầu; một chuyển đổi đã mất ký tự hoặc đã hợp nhất ý nghĩa so sánh có thể không đảo ngược được.

## 9. Connection charset và dữ liệu đi qua ứng dụng

Chuyển cột sang utf8mb4 chưa đủ nếu client tiếp tục gửi dữ liệu bằng charset không phù hợp. Trong MySQL CLI, có thể thiết lập charset của kết nối bằng:

~~~sql
SET NAMES utf8mb4;
~~~

SET NAMES thiết lập character_set_client, character_set_connection và character_set_results; collation_connection được đặt theo charset hoặc collation chỉ định. Đây là thiết lập session, không đổi charset của cột hay database.

Với ứng dụng Java, hãy cấu hình MySQL Connector/J theo phiên bản driver và dùng Unicode trong JDBC. Không tự đặt các tham số connection cũ theo hướng dẫn dành cho phiên bản driver khác. Kiểm tra charset thực tế bằng SHOW SESSION VARIABLES và thử round-trip với chuỗi đại diện.

Một phép thử round-trip nên gồm:

1. Ứng dụng gửi chuỗi tiếng Việt có dấu và một số ký tự Unicode ngoài BMP.
2. Đọc lại cùng giá trị bằng chính ứng dụng và bằng MySQL CLI được cấu hình utf8mb4.
3. So sánh giá trị ký tự và HEX ở database với dữ liệu đầu vào đã biết.
4. Kiểm tra collation khi so sánh và sắp xếp, vì hiển thị đúng không có nghĩa quy tắc so sánh đúng yêu cầu.

## 10. Ví dụ migration hoàn chỉnh cho cột username

Giả sử bảng users có username với unique index và cần chuyển sang utf8mb4_0900_ai_ci.

**Trước tiên, xem định nghĩa và index:**

~~~sql
SHOW CREATE TABLE users;

SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, SUB_PART
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

**Kiểm tra nhóm trùng theo collation đích:**

~~~sql
SELECT
    CONVERT(username USING utf8mb4)
      COLLATE utf8mb4_0900_ai_ci AS target_username,
    COUNT(*) AS row_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn trả kết quả, xem các hàng liên quan và giải quyết theo nghiệp vụ. Nếu không trả nhóm trùng, vẫn cần kiểm tra unique key ghép, prefix hoặc functional index nếu schema có chúng.

**Sau backup, thử trên bản sao rồi mới chuyển cột:**

~~~sql
ALTER TABLE users
  MODIFY COLUMN username VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL;
~~~

Ví dụ giả định username ban đầu là VARCHAR(100) NOT NULL và không có thuộc tính bổ sung. Nếu định nghĩa thật khác, phải giữ nguyên các thuộc tính đó trong câu MODIFY.

**Xác minh sau chuyển:**

~~~sql
SELECT COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME,
       IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
  AND COLUMN_NAME = 'username';

SHOW CREATE TABLE users;
~~~

Chạy lại truy vấn duplicate theo collation đích và thử đăng nhập/tìm kiếm bằng các biến thể hoa/thường, có dấu/không dấu mà nghiệp vụ cho phép. Unique index hiện hữu phải tiếp tục được tạo thành công và duy trì tính duy nhất theo collation mới.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ALTER TABLE báo Duplicate entry | Dữ liệu trở nên tương đương theo collation mới hoặc unique key ghép có xung đột | Mô phỏng bằng GROUP BY theo collation đích, xử lý từng nhóm trước migration |
| Incorrect string value | Charset đích hoặc cột không biểu diễn được ký tự, dữ liệu đầu vào sai encoding | Kiểm tra charset nguồn, dữ liệu mẫu, connection charset và chế độ SQL |
| Văn bản vẫn lỗi sau khi đổi sang utf8mb4 | Byte đã bị ghi sai từ trước hoặc client hiển thị sai | Kiểm tra HEX, charset cột và connection; thử phục hồi trên bản sao |
| Index too long hoặc không tạo được index | Số byte tối đa tăng khi chuyển sang utf8mb4 hoặc vượt giới hạn index | Kiểm tra tổng độ dài key, prefix, row format, page size và phiên bản |
| Foreign key không thể thay đổi | Cột chuỗi hai phía không còn cùng kiểu/charset/collation hoặc index phụ thuộc | Lập kế hoạch chuyển cả cặp cột và constraint theo thứ tự |
| Tìm kiếm trả kết quả khác trước | Collation mới thay đổi cách so sánh, hoa/thường, dấu hoặc khoảng trắng | Xác minh collation đích và điều chỉnh truy vấn/unique rule theo nghiệp vụ |
| ALTER TABLE kéo dài hoặc ảnh hưởng ứng dụng | Bảng phải rebuild, index phải tạo lại hoặc DDL gây lock/I/O | Đo trên staging, chọn cửa sổ triển khai và đánh giá online DDL |
| Đổi ALTER DATABASE nhưng cột cũ không đổi | Chỉ mặc định database được cập nhật | Chuyển cột/bảng hiện có bằng CONVERT TO hoặc MODIFY COLUMN |

## 12. Bài thực hành: mô phỏng collation collision

Thực hiện trong database lab trên MySQL 8.0 có hỗ trợ utf8mb4_0900_ai_ci. Không dùng bảng production.

**Bước 1 — Tạo bảng với collation phân biệt hoa/thường:**

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    username VARCHAR(100)
      CHARACTER SET utf8mb4
      COLLATE utf8mb4_0900_as_cs NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_lab_username (username)
) ENGINE=InnoDB;
~~~

**Bước 2 — Chèn các giá trị khác nhau theo collation nguồn:**

~~~sql
INSERT INTO lab_accounts (account_id, username) VALUES
    (1, 'Admin'),
    (2, 'admin'),
    (3, 'resume'),
    (4, 'résumé');
~~~

**Bước 3 — Kiểm tra theo collation nguồn và đích:**

~~~sql
SELECT username, COUNT(*)
FROM lab_accounts
GROUP BY username;

SELECT
    username COLLATE utf8mb4_0900_ai_ci AS target_username,
    COUNT(*) AS duplicate_count
FROM lab_accounts
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

Quan sát các nhóm bị gộp khi so sánh theo collation đích không phân biệt hoa/thường và dấu.

**Bước 4 — Thử chuyển đổi trên bản lab.** Có thể thử ALTER TABLE đổi collation; thao tác sẽ thất bại nếu unique index không thể bảo đảm tính duy nhất theo collation mới. Ghi lại thông báo và xác nhận bảng vẫn có dữ liệu để tiếp tục điều tra.

~~~sql
ALTER TABLE lab_accounts
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

**Bước 5 — Xử lý dữ liệu trùng theo quy tắc thử nghiệm.** Chọn một username chuẩn, đổi các giá trị còn lại thành tên duy nhất theo quy tắc lab hoặc xóa hàng thử nghiệm sau khi ghi lại kết quả. Không áp dụng cách xử lý này cho dữ liệu thật nếu chưa đánh giá quan hệ tham chiếu.

**Bước 6 — Chạy lại kiểm tra và chuyển đổi.** Xác nhận truy vấn duplicate không còn trả nhóm xung đột, sau đó chạy ALTER TABLE và kiểm tra SHOW CREATE TABLE.

**Bước 7 — Dọn lab.**

~~~sql
DROP TABLE lab_accounts;
~~~

Chỉ xóa bảng lab đã tạo cho bài thực hành.

**Kết quả cần đạt:** giải thích được vì sao collation mới có thể tạo duplicate, mô phỏng được phép so sánh theo collation đích, nhận diện xung đột unique index và thực hiện chuyển đổi sau khi dữ liệu đã đáp ứng quy tắc mới.

## 13. Checklist trước khi chuyển đổi production

- Xác nhận phiên bản MySQL và collation đích được hỗ trợ trên mọi môi trường liên quan.
- Kiểm kê charset/collation ở cấp database, table, column và connection.
- Xác định dữ liệu có bị ghi sai encoding hay chỉ hiển thị sai.
- Đọc SHOW CREATE TABLE, index, foreign key, generated column và các ràng buộc phụ thuộc.
- Kiểm tra duplicate theo collation đích cho mọi unique key, kể cả khóa ghép, prefix và functional index.
- Loại các hàng có thành phần NULL khỏi phép kiểm tra duplicate của unique key theo đúng semantics MySQL.
- Đánh giá độ dài byte của cột và index sau khi chuyển sang charset đích.
- Backup và thử restore; chạy thử migration trên bản sao đại diện.
- Chốt phương án xử lý dữ liệu trùng với chủ sở hữu nghiệp vụ.
- Lập cửa sổ triển khai, kiểm soát ghi đồng thời, kế hoạch giám sát và phương án khôi phục.
- Sau chuyển đổi, xác minh metadata, số hàng, giá trị mẫu, index, foreign key, replication và hành vi ứng dụng.

## 14. Nguyên tắc cần ghi nhớ

- Character set quyết định encoding; collation quyết định cách so sánh và sắp xếp.
- ALTER DATABASE hoặc ALTER TABLE DEFAULT CHARACTER SET chỉ đổi mặc định, không chuyển dữ liệu hiện có.
- CONVERT TO CHARACTER SET chuyển các cột ký tự trong bảng; MODIFY COLUMN phù hợp khi cần chuyển riêng một cột và phải khai báo lại đầy đủ thuộc tính.
- Dữ liệu đã bị ghi sai encoding không tự được sửa bằng cách đổi charset; cần kiểm tra byte, metadata và charset kết nối.
- Collation không phân biệt dấu/hoa thường có thể làm nhiều giá trị trở thành tương đương và gây xung đột UNIQUE.
- Kiểm tra duplicate phải mô phỏng chính collation, prefix và toàn bộ thành phần của unique key đích.
- Với unique key, nhiều hàng có thành phần NULL có thể hợp lệ theo quy tắc MySQL; không coi chúng là duplicate chỉ vì GROUP BY gom NULL.
- Chuyển sang utf8mb4 có thể tăng dung lượng byte và ảnh hưởng giới hạn index.
- Foreign key trên cột chuỗi cần được chuyển đổi đồng bộ ở cả hai phía.
- Backup, restore thử nghiệm, kiểm tra sau migration và kế hoạch khôi phục là các phần bắt buộc của thay đổi production.

Chuyển charset/collation an toàn đòi hỏi kiểm soát cả encoding lẫn quy tắc tương đương của dữ liệu. Khi kiểm tra duplicate bằng collation đích trước, hiểu các phụ thuộc index và thử migration trên bản sao, bạn có thể thay đổi chuẩn Unicode mà vẫn bảo vệ được tính toàn vẹn dữ liệu và hành vi của ứng dụng.
