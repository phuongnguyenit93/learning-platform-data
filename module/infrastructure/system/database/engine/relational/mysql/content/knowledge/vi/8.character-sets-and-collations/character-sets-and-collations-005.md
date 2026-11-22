# Độ dài theo ký tự, độ dài theo byte và giới hạn chỉ mục

Khi thiết kế cột văn bản và index trong MySQL, cần phân biệt **số ký tự** với **số byte**. Một chuỗi có thể gồm ít ký tự nhưng chiếm nhiều byte vì character set mã hóa mỗi ký tự bằng số byte khác nhau. Giới hạn độ dài của `CHAR`/`VARCHAR` được khai báo theo ký tự, trong khi giới hạn kích thước hàng và giới hạn key của index được tính theo byte.

Sự khác biệt này đặc biệt quan trọng với `utf8mb4`: một ký tự có thể cần tối đa 4 byte. Ví dụ, một index trên 200 ký tự `utf8mb4` có thể cần đến 800 byte cho phần giá trị chuỗi. Nếu index ghép nhiều cột, tổng độ dài byte của các key part cùng quyết định index có vượt giới hạn hay không.

Bài học này hướng dẫn đo độ dài bằng SQL, đọc metadata charset/cột/index, tính kích thước tối đa của chuỗi và đánh giá giới hạn index của InnoDB. Các ví dụ hướng tới MySQL 8.x với InnoDB; giới hạn thực tế còn phụ thuộc phiên bản, `innodb_page_size`, row format và loại storage engine.

## 1. Ký tự và byte là hai đơn vị khác nhau

Ký tự là đơn vị mà người dùng nhìn thấy hoặc nhập vào văn bản. Byte là đơn vị dữ liệu được mã hóa và lưu trữ. Một character set ánh xạ ký tự sang một hoặc nhiều byte.

Ví dụ thường gặp:

| Character set | Số byte tối đa cho một ký tự | Nhận xét |
| --- | ---: | --- |
| `ascii` | 1 | Chỉ biểu diễn tập ký tự ASCII |
| `latin1` | 1 | Mỗi ký tự dùng một byte trong character set này |
| `utf8mb3` | 3 | Bộ UTF-8 cũ của MySQL, không biểu diễn đầy đủ mọi Unicode code point |
| `utf8mb4` | 4 | Hỗ trợ đầy đủ Unicode, bao gồm nhiều ký tự bổ sung và emoji |

Không thể suy ra số byte chỉ từ số ký tự nếu chưa biết charset và nội dung cụ thể. Với `utf8mb4`, chuỗi ASCII có thể vẫn chỉ dùng một byte mỗi ký tự; tiếng Việt có dấu hoặc emoji có thể cần nhiều byte hơn.

## 2. Đo độ dài bằng CHAR_LENGTH, LENGTH và OCTET_LENGTH

MySQL cung cấp các hàm sau:

- `CHAR_LENGTH(str)` trả về số ký tự trong chuỗi.
- `CHARACTER_LENGTH(str)` là tên đồng nghĩa của `CHAR_LENGTH`.
- `LENGTH(str)` trả về số byte của chuỗi theo character set của giá trị.
- `OCTET_LENGTH(str)` là tên đồng nghĩa của `LENGTH`.

Ví dụ với ký tự ASCII, ký tự có dấu và emoji:

```sql
SET NAMES utf8mb4;

SELECT
    _utf8mb4'Aé😊' AS sample_text,
    CHAR_LENGTH(_utf8mb4'Aé😊') AS character_count,
    LENGTH(_utf8mb4'Aé😊') AS byte_count,
    OCTET_LENGTH(_utf8mb4'Aé😊') AS octet_count;
```

Với chuỗi ví dụ này, số ký tự là 3: `A`, `é` và `😊`. Số byte trong `utf8mb4` là 7: `A` dùng 1 byte, `é` dùng 2 byte và emoji dùng 4 byte. `LENGTH()` và `OCTET_LENGTH()` trả về cùng kết quả.

Lưu ý rằng hàm đếm ký tự của MySQL đếm đơn vị ký tự theo character set/code point, không đếm cụm ký tự hiển thị (grapheme cluster) theo cách mắt người cảm nhận. Một chữ có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc một ký tự cơ sở cộng dấu kết hợp; hai chuỗi nhìn giống nhau vì vậy có thể có số code point và số byte khác nhau.

Không nên dùng `LENGTH()` để kiểm tra giới hạn nghiệp vụ được định nghĩa theo số ký tự. Ngược lại, không nên chỉ dùng `CHAR_LENGTH()` khi cần đánh giá dung lượng lưu trữ hoặc giới hạn index.

## 3. Character set cho biết số byte tối đa

Có thể xem các character set mà MySQL hỗ trợ và `MAXLEN` của chúng:

```sql
SELECT
    CHARACTER_SET_NAME,
    DEFAULT_COLLATE_NAME,
    MAXLEN
FROM INFORMATION_SCHEMA.CHARACTER_SETS
WHERE CHARACTER_SET_NAME IN ('ascii', 'latin1', 'utf8mb3', 'utf8mb4')
ORDER BY CHARACTER_SET_NAME;
```

Với `utf8mb4`, `MAXLEN` bằng 4. Đây là số byte tối đa cho một ký tự, không có nghĩa mọi ký tự trong cột đều luôn chiếm 4 byte.

Trong MySQL, tên `utf8` trước đây thường là alias của `utf8mb3`. Với schema mới, nên khai báo `utf8mb4` rõ ràng để tránh nhầm lẫn và hỗ trợ đầy đủ Unicode.

Có thể xem charset và collation mặc định của database hiện tại:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = DATABASE();
```

Charset/collation có thể được đặt ở cấp server, database, table hoặc column. Giá trị thực tế của từng cột mới là thông tin cần dùng khi tính giới hạn byte của index.

## 4. Độ dài khai báo của CHAR và VARCHAR

Với chuỗi không nhị phân, `CHAR(n)` và `VARCHAR(n)` khai báo giới hạn theo số ký tự, không phải số byte.

Ví dụ:

```sql
CREATE TABLE text_length_demo (
    ascii_code VARCHAR(100)
        CHARACTER SET ascii,
    vietnamese_text VARCHAR(100)
        CHARACTER SET utf8mb4,
    fixed_country_code CHAR(2)
        CHARACTER SET ascii
) ENGINE=InnoDB;
```

Hai cột `VARCHAR(100)` đều cho phép tối đa 100 ký tự, nhưng giới hạn byte tối đa khác nhau:

- `ascii_code`: tối đa khoảng 100 byte cho dữ liệu ký tự ASCII.
- `vietnamese_text`: tối đa 400 byte dữ liệu ký tự theo giới hạn 4 byte/ký tự của `utf8mb4`.

`VARCHAR` còn có byte tiền tố để lưu độ dài thực tế. MySQL thường dùng một byte tiền tố nếu độ dài tối đa của cột tính theo byte không vượt 255; nếu lớn hơn thì dùng hai byte. Vì vậy, `VARCHAR(100)` với `ascii` có thể dùng một byte tiền tố, trong khi `VARCHAR(100)` với `utf8mb4` có khả năng tối đa 400 byte và cần hai byte tiền tố.

Đây là cách ước tính phần chuỗi của một cột, không phải công thức tính toàn bộ kích thước hàng InnoDB. Record còn có metadata, null bitmap, transaction metadata, index và các chi phí tổ chức trang dữ liệu. Row format cũng ảnh hưởng đến cách dữ liệu dài được lưu.

## 5. Xem giới hạn ký tự và byte từ INFORMATION_SCHEMA

Metadata cột cung cấp cả độ dài theo ký tự lẫn độ dài tối đa theo byte:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    CHARACTER_MAXIMUM_LENGTH,
    CHARACTER_OCTET_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND CHARACTER_MAXIMUM_LENGTH IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Ý nghĩa hai cột quan trọng:

- `CHARACTER_MAXIMUM_LENGTH`: độ dài tối đa theo ký tự.
- `CHARACTER_OCTET_LENGTH`: độ dài tối đa theo byte.

Ví dụ, một cột `VARCHAR(100)` dùng `utf8mb4` thường có `CHARACTER_MAXIMUM_LENGTH = 100` và `CHARACTER_OCTET_LENGTH = 400`. Nếu cột dùng `ascii`, hai giá trị thường đều là 100.

Khi đánh giá schema hiện có, hãy đọc metadata thay vì suy luận charset từ tên cột hoặc mặc định database. Một bảng có thể có cột dùng charset/collation khác nhau do lịch sử migration.

## 6. Giới hạn kích thước hàng không giống giới hạn index

MySQL có giới hạn kích thước hàng định nghĩa tối đa 65.535 byte, được chia sẻ giữa các cột và chịu ảnh hưởng của overhead. Với cột `VARCHAR`, phần dữ liệu tối đa được tính theo số byte mà charset có thể cần, cộng phần lưu độ dài. Vì vậy, nhiều cột `VARCHAR` lớn có thể khiến câu lệnh `CREATE TABLE` vượt giới hạn hàng dù từng cột riêng lẻ có độ dài hợp lệ.

Với InnoDB, một số dữ liệu dài như `TEXT`/`BLOB` hoặc giá trị biến độ dài có thể được lưu ngoài trang dữ liệu chính tùy row format và kích thước record. Cách lưu ngoài trang không loại bỏ mọi giới hạn định nghĩa của MySQL; phần metadata hoặc con trỏ lưu trữ vẫn có chi phí.

Giới hạn hàng và giới hạn index là hai kiểm tra riêng:

- Giới hạn hàng quyết định định nghĩa và dữ liệu của một record có thể được tổ chức hợp lệ hay không.
- Giới hạn index quyết định tổng kích thước key part của một chỉ mục có vượt giới hạn engine hay không.

Một bảng có thể tạo được nhưng index trên cột văn bản dài vẫn thất bại. Ngược lại, một index ngắn không có nghĩa toàn bộ định nghĩa hàng chắc chắn hợp lệ.

## 7. Vì sao index được tính theo byte?

Index B-tree cần lưu giá trị khóa để sắp xếp và tìm kiếm. Với cột chuỗi, giá trị khóa được biểu diễn theo character set và collation của cột; kích thước tối đa phụ thuộc số byte có thể cần cho các ký tự.

Với `utf8mb4`, có thể ước tính phần dữ liệu chuỗi tối đa như sau:

\[
\text{Max bytes} = \text{Indexed characters} \times 4
\]

Ví dụ:

| Độ dài index theo ký tự | Charset | Byte tối đa cho phần chuỗi |
| ---: | --- | ---: |
| 100 | `ascii` | 100 |
| 100 | `utf8mb4` | 400 |
| 191 | `utf8mb4` | 764 |
| 255 | `utf8mb4` | 1.020 |
| 500 | `utf8mb4` | 2.000 |

Đây là phép tính cho phần dữ liệu chuỗi của key part. Index thực tế còn có thể gồm các cột khác, kiểu số, cột nullable và metadata nội bộ. Với index ghép, phải cộng giới hạn byte của tất cả key part thay vì chỉ nhìn cột dài nhất.

## 8. Giới hạn key length của InnoDB

Với InnoDB sử dụng page size mặc định 16 KB và row format `DYNAMIC` hoặc `COMPRESSED`, giới hạn key length phổ biến là 3.072 byte. Giới hạn này giảm theo page size nhỏ hơn: 1.536 byte với page 8 KB và 768 byte với page 4 KB.

Với row format cũ `COMPACT` hoặc `REDUNDANT`, giới hạn prefix/key length ở cấu hình page 16 KB là 767 byte. Đây là lý do nhiều hướng dẫn cũ đề xuất `VARCHAR(191)` cho index `utf8mb4`: 191 × 4 = 764 byte, nằm trong giới hạn 767 byte. Trên cấu hình MySQL 8.x hiện đại với InnoDB `DYNAMIC` và page 16 KB, không cần áp dụng máy móc con số 191 cho mọi cột.

Kiểm tra page size:

```sql
SHOW VARIABLES LIKE 'innodb_page_size';
```

Kiểm tra row format của bảng:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

Giới hạn thực tế còn phụ thuộc phiên bản MySQL, engine và cấu hình. `innodb_page_size` được xác định khi khởi tạo instance; không thể thay đổi tùy ý bằng một biến runtime trên instance đang chạy. Nếu môi trường dùng page size hoặc row format khác mặc định, hãy kiểm tra tài liệu phiên bản trước khi thiết kế index.

## 9. Index prefix và cách khai báo độ dài

Với cột chuỗi, có thể tạo index trên toàn bộ giá trị hoặc một phần đầu (prefix) của giá trị. Ví dụ:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(500) NOT NULL,
    body TEXT,
    PRIMARY KEY (id),
    KEY idx_articles_title (title(150)),
    KEY idx_articles_body_prefix (body(100))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Với cột chuỗi không nhị phân như `CHAR`, `VARCHAR` hoặc `TEXT`, độ dài prefix trong DDL được tính theo ký tự. Vì vậy `title(150)` có thể cần tối đa 600 byte cho phần prefix trong `utf8mb4`. Với kiểu nhị phân như `BINARY`, `VARBINARY` hoặc `BLOB`, độ dài prefix được tính theo byte.

Index prefix giúp giảm kích thước key, nhưng có giới hạn:

- Index chỉ lưu phần đầu của giá trị, nên nhiều giá trị khác nhau có thể có cùng prefix.
- Truy vấn cần phân biệt toàn bộ chuỗi có thể phải đọc hàng để kiểm tra phần còn lại.
- Prefix quá ngắn có độ chọn lọc thấp và có thể không giúp truy vấn nhiều.
- Prefix index không tương đương index đầy đủ về ngữ nghĩa.

Đặc biệt, unique prefix index chỉ bảo đảm phần prefix là duy nhất. Nếu hai chuỗi có cùng 100 ký tự đầu nhưng khác ở phần sau, unique index trên `column(100)` vẫn xem chúng là xung đột. Nếu nghiệp vụ yêu cầu toàn bộ email hoặc mã định danh phải duy nhất, cần index đầy đủ hoặc một thiết kế khóa khác bảo đảm đúng ngữ nghĩa.

## 10. Giới hạn của index ghép

Với index nhiều cột, tổng độ dài tối đa của các key part phải nằm trong giới hạn engine. Ví dụ:

```sql
CREATE TABLE tenant_documents (
    tenant_id BIGINT UNSIGNED NOT NULL,
    slug VARCHAR(200) NOT NULL,
    title VARCHAR(300) NOT NULL,
    PRIMARY KEY (tenant_id, slug),
    KEY idx_tenant_title (tenant_id, title(100))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Ước tính cho primary key:

- `tenant_id`: 8 byte.
- `slug`: tối đa 200 × 4 = 800 byte.
- Tổng phần key value: khoảng 808 byte trước các overhead nội bộ.

Ước tính cho `idx_tenant_title`:

- `tenant_id`: 8 byte.
- Prefix `title(100)`: tối đa 100 × 4 = 400 byte.
- Tổng phần key value: khoảng 408 byte trước các overhead nội bộ.

Hai index này nằm dưới giới hạn 3.072 byte thường gặp của InnoDB 16 KB với row format hiện đại, nhưng index primary key có thể vượt giới hạn 767 byte ở cấu hình legacy `COMPACT`/`REDUNDANT`. Đây là lý do cần tính tổng key part và kiểm tra row format thay vì chỉ xem từng cột riêng lẻ.

Index ghép còn có quy tắc leftmost prefix về khả năng sử dụng. Một index `(tenant_id, status, created_at)` thường hỗ trợ điều kiện bắt đầu từ `tenant_id`; nó không tự động tương đương với index chỉ trên `status`. Thiết kế thứ tự cột phải dựa trên truy vấn thực tế và `EXPLAIN`, không chỉ dựa trên phép tính byte.

## 11. Kiểm tra index và prefix từ metadata

`SHOW INDEX` hoặc `SHOW KEYS` cho biết các cột và thứ tự trong index:

```sql
SHOW INDEX FROM tenant_documents;
```

Có thể đọc metadata chi tiết bằng `INFORMATION_SCHEMA.STATISTICS`:

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

`SUB_PART` cho biết độ dài prefix nếu index chỉ dùng một phần cột; giá trị `NULL` thường biểu thị index dùng toàn bộ cột. Với chuỗi không nhị phân, `SUB_PART` là số ký tự; với kiểu nhị phân, nó là số byte.

Để kiểm tra kế hoạch truy vấn:

```sql
EXPLAIN
SELECT id, title
FROM articles
WHERE title LIKE 'MySQL%';
```

`EXPLAIN` giúp xem optimizer có chọn index hay không. Một prefix index không bảo đảm mọi truy vấn trên cột đều được tối ưu; điều kiện tìm kiếm, collation, pattern, thống kê và phân bố dữ liệu đều ảnh hưởng kế hoạch.

## 12. Ví dụ lỗi key quá dài và cách xử lý

Giả sử một bảng có cột `title VARCHAR(1000) CHARACTER SET utf8mb4` và tạo index đầy đủ:

```sql
CREATE TABLE long_titles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(1000) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_long_titles_title (title)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Phần giá trị chuỗi của index có thể cần tối đa 4.000 byte. Con số này vượt giới hạn 3.072 byte thường gặp của InnoDB với page 16 KB, vì vậy việc tạo index có thể thất bại với lỗi key length.

Các cách xử lý cần cân nhắc theo nhu cầu:

1. **Giảm độ dài cột** nếu quy tắc nghiệp vụ thực sự giới hạn chuỗi ngắn hơn.
2. **Dùng prefix index** nếu truy vấn chỉ cần tìm theo một prefix đủ chọn lọc và không cần bảo đảm uniqueness của toàn chuỗi bằng prefix đó.
3. **Thiết kế index ghép hợp lý hơn**, bỏ các key part không cần thiết hoặc giảm prefix dựa trên truy vấn.
4. **Chọn kiểu dữ liệu phù hợp**, chẳng hạn `TEXT` cho nội dung dài và chỉ index prefix cần thiết; nhớ rằng `TEXT` cũng cần prefix khi lập chỉ mục thông thường.
5. **Kiểm tra row format/page size** và giới hạn thực tế của server trước khi thay đổi cấu hình hoặc di chuyển dữ liệu.

Không nên đổi `utf8mb4` sang `latin1` chỉ để index vừa giới hạn nếu dữ liệu cần Unicode. Việc đó có thể làm mất khả năng lưu ký tự hợp lệ và tạo lỗi chuyển đổi dữ liệu. Cũng không nên dùng prefix index làm unique key nếu nghiệp vụ yêu cầu duy nhất toàn bộ chuỗi.

## 13. Đo dữ liệu thực tế trước khi chọn prefix

Giới hạn tối đa giúp kiểm tra schema, nhưng độ dài thực tế và độ phân biệt của dữ liệu giúp chọn prefix hữu ích. Có thể đo độ dài lớn nhất:

```sql
SELECT
    MAX(CHAR_LENGTH(title)) AS max_characters,
    MAX(OCTET_LENGTH(title)) AS max_bytes,
    AVG(CHAR_LENGTH(title)) AS average_characters
FROM articles;
```

Để đánh giá độ chọn lọc của prefix, có thể so sánh số lượng prefix khác nhau với tổng số hàng:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT LEFT(title, 50)) AS distinct_prefix_50,
    COUNT(DISTINCT LEFT(title, 100)) AS distinct_prefix_100
FROM articles;
```

Các phép đo này chỉ là điểm khởi đầu. Cần thử trên dữ liệu đại diện, cân nhắc phân bố theo tenant hoặc trạng thái và đo truy vấn thực tế. Với cột có nhiều giá trị trùng đầu chuỗi, prefix dài hơn có thể tăng độ chọn lọc nhưng cũng tăng kích thước index.

## 14. Quy trình thiết kế cột chuỗi và index

Trước khi tạo cột hoặc index, hãy làm theo trình tự:

1. Xác định dữ liệu là văn bản hay byte nhị phân.
2. Chọn charset phù hợp với tập ký tự nghiệp vụ; với văn bản Unicode hiện đại thường ưu tiên `utf8mb4`.
3. Xác định giới hạn nghiệp vụ theo số ký tự và kiểm tra `CHARACTER_OCTET_LENGTH`.
4. Tính byte tối đa cho mỗi key part dựa trên charset và prefix length.
5. Cộng kích thước tối đa của toàn bộ key part trong index ghép.
6. Kiểm tra `innodb_page_size`, row format và giới hạn của phiên bản/storage engine.
7. Xác định index đầy đủ hay prefix; kiểm tra unique semantics trước khi chọn prefix.
8. Đọc truy vấn thật, dùng `EXPLAIN` và đo hiệu năng sau khi tạo index.
9. Kiểm tra metadata bằng `SHOW CREATE TABLE`, `SHOW INDEX` và `INFORMATION_SCHEMA`.

## 15. Bài tập thực hành

1. Chạy `CHAR_LENGTH`, `LENGTH` và `OCTET_LENGTH` với chuỗi ASCII, tiếng Việt có dấu và emoji; giải thích chênh lệch.
2. Truy vấn `INFORMATION_SCHEMA.CHARACTER_SETS` để xem `MAXLEN` của `ascii`, `latin1` và `utf8mb4`.
3. Tạo hai cột `VARCHAR(100)`, một dùng `ascii`, một dùng `utf8mb4`; so sánh `CHARACTER_MAXIMUM_LENGTH` và `CHARACTER_OCTET_LENGTH`.
4. Kiểm tra `innodb_page_size` và `ROW_FORMAT` của bảng InnoDB trong môi trường lab.
5. Tính kích thước tối đa của index trên `VARCHAR(191)`, `VARCHAR(255)` và `VARCHAR(500)` dùng `utf8mb4`.
6. Tạo index prefix trên cột `VARCHAR(500)` và kiểm tra `SUB_PART` qua `INFORMATION_SCHEMA.STATISTICS`.
7. Tạo một unique prefix index trong schema lab, thử hai chuỗi có cùng prefix nhưng khác phần cuối và quan sát kết quả.
8. Tạo index ghép gồm một cột `BIGINT` và một cột `VARCHAR` dùng `utf8mb4`; tính tổng byte tối đa và so sánh với giới hạn của server.
9. Dùng `EXPLAIN` để kiểm tra truy vấn có tận dụng index prefix như mong muốn hay không.

## 16. Ghi nhớ

Độ dài khai báo của `CHAR`/`VARCHAR` được tính theo ký tự; `CHAR_LENGTH()` đếm ký tự còn `LENGTH()`/`OCTET_LENGTH()` đếm byte. Với `utf8mb4`, mỗi ký tự có thể cần tối đa 4 byte. `INFORMATION_SCHEMA.COLUMNS` cung cấp cả `CHARACTER_MAXIMUM_LENGTH` và `CHARACTER_OCTET_LENGTH` để kiểm tra metadata.

Giới hạn index được tính theo byte và áp dụng cho tổng các key part. InnoDB hiện đại với page 16 KB và row format `DYNAMIC`/`COMPRESSED` thường hỗ trợ key length tối đa 3.072 byte; cấu hình page nhỏ hơn hoặc row format legacy có giới hạn thấp hơn. Prefix index có thể giảm kích thước key nhưng làm thay đổi ngữ nghĩa uniqueness nếu dùng trên unique index. Hãy tính byte theo charset, kiểm tra page size/row format, xác minh metadata và đo truy vấn trước khi quyết định thiết kế index.
