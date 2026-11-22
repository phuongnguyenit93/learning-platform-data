# TINYTEXT/TEXT/MEDIUMTEXT/LONGTEXT và các kiểu BLOB tương ứng

Bài học thuộc chương **Kiểu dữ liệu** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Nhóm `TEXT` và `BLOB` phục vụ các cột có giá trị biến độ dài và có thể rất lớn, nhưng chúng khác nhau ở cách MySQL hiểu nội dung, so sánh, lập chỉ mục và truyền dữ liệu.

Sau bài này, bạn có thể chọn đúng cấp độ `TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT` hoặc kiểu `BLOB` tương ứng; giải thích giới hạn theo byte; phân biệt dữ liệu ký tự với dữ liệu nhị phân; tạo prefix index hoặc FULLTEXT index phù hợp; và nhận diện các giới hạn lưu trữ, truy vấn, packet và hiệu năng.

## 1. TEXT và BLOB giải quyết vấn đề gì?

MySQL có hai họ kiểu dữ liệu lớn, biến độ dài:

- **TEXT** lưu chuỗi ký tự. Giá trị có character set và collation, vì vậy MySQL có thể xử lý theo ngôn ngữ, quy tắc so sánh, thứ tự sắp xếp và chuyển đổi ký tự.
- **BLOB** lưu chuỗi byte. Giá trị được xử lý như dữ liệu nhị phân, có character set và collation là `binary`; so sánh và sắp xếp dựa trên giá trị byte.

Ví dụ:

| Dữ liệu | Kiểu thường phù hợp | Lý do |
|---|---|---|
| Nội dung bài viết, mô tả dài, ghi chú nhiều dòng | `TEXT` hoặc `MEDIUMTEXT` | Nội dung là văn bản cần charset và collation |
| Nội dung HTML, Markdown, văn bản tiếng Việt | `TEXT` hoặc `MEDIUMTEXT` | Cần lưu và so sánh như chuỗi ký tự |
| Tệp ảnh, PDF, âm thanh, dữ liệu nén | `BLOB` tương ứng | Cần giữ nguyên từng byte của tệp |
| Payload đã mã hóa hoặc dữ liệu serialization dạng byte | `BLOB` tương ứng | Không nên diễn giải byte như văn bản |
| Nội dung log hoặc văn bản có kích thước rất lớn | `MEDIUMTEXT` hoặc `LONGTEXT` | Giới hạn của `VARCHAR` có thể không phù hợp |

Không nên chọn `BLOB` chỉ vì dữ liệu có vẻ dài, cũng không nên chọn `LONGTEXT` chỉ vì muốn “dư chỗ”. Hãy xác định nội dung là văn bản hay byte nhị phân, kích thước thực tế, cách truy vấn và vòng đời dữ liệu trước khi chọn kiểu.

## 2. Bốn cấp độ dung lượng

Mỗi họ có bốn kiểu tương ứng. Các giới hạn dưới đây là số byte tối đa của phần giá trị:

| Kiểu TEXT | Kiểu BLOB tương ứng | Dung lượng tối đa | Byte lưu độ dài |
|---|---|---:|---:|
| `TINYTEXT` | `TINYBLOB` | 255 byte | 1 byte |
| `TEXT` | `BLOB` | 65.535 byte (64 KiB - 1) | 2 byte |
| `MEDIUMTEXT` | `MEDIUMBLOB` | 16.777.215 byte (16 MiB - 1) | 3 byte |
| `LONGTEXT` | `LONGBLOB` | 4.294.967.295 byte (4 GiB - 1) | 4 byte |

Hai cột trong cùng một hàng có giới hạn dung lượng và yêu cầu lưu trữ tương ứng. Khác biệt chính là TEXT lưu chuỗi ký tự còn BLOB lưu byte.

### Giới hạn byte không phải lúc nào cũng bằng số ký tự

Với kiểu TEXT, dung lượng tối đa được tính theo byte sau khi mã hóa. Số ký tự thực tế phụ thuộc character set.

Ví dụ, `utf8mb4` có thể dùng tối đa 4 byte cho một ký tự. Nếu mọi ký tự đều cần đủ 4 byte thì giới hạn lý thuyết gần đúng là:

| Kiểu | Byte tối đa | Số ký tự tối đa ước lượng với 4 byte/ký tự |
|---|---:|---:|
| `TINYTEXT` | 255 | 63 |
| `TEXT` | 65.535 | 16.383 |
| `MEDIUMTEXT` | 16.777.215 | 4.194.303 |
| `LONGTEXT` | 4.294.967.295 | 1.073.741.823 |

Đây là ước lượng khi toàn bộ ký tự sử dụng 4 byte. Nhiều ký tự ASCII chỉ dùng 1 byte, các ký tự tiếng Việt có thể cần nhiều byte khác nhau. Vì vậy không thể suy ra chính xác số ký tự chỉ từ tên kiểu TEXT.

Với BLOB, giới hạn luôn được tính theo byte vì nội dung là chuỗi byte. Không có khái niệm “số ký tự” để xác định sức chứa của BLOB.

### Phần lưu độ dài

MySQL lưu giá trị TEXT/BLOB dưới dạng dữ liệu có độ dài biến đổi. Ngoài byte nội dung, cần thêm 1, 2, 3 hoặc 4 byte để lưu độ dài, tùy kiểu.

Nếu một giá trị MEDIUMTEXT có độ dài thực tế là 10.000 byte, phần dữ liệu và tiền tố độ dài cần khoảng 10.003 byte trước khi tính overhead của hàng, record, trang, con trỏ off-page và các cấu trúc lưu trữ khác.

Không nên dùng công thức này để ước lượng chính xác dung lượng toàn bảng. Dung lượng thực tế còn phụ thuộc storage engine, row format, kích thước hàng, page size, index và khả năng nén.

## 3. So sánh TEXT và BLOB

### TEXT: chuỗi ký tự có charset và collation

TEXT là kiểu chuỗi không nhị phân. Có thể khai báo character set và collation ở cấp cột:

~~~sql
CREATE TABLE articles (
    id BIGINT UNSIGNED PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
);
~~~

Trong ví dụ:

- `utf8mb4` cho phép lưu Unicode, bao gồm tiếng Việt và các ký tự ngoài BMP.
- `utf8mb4_0900_ai_ci` là collation không phân biệt hoa/thường và dấu theo quy tắc của collation đó.
- So sánh, tìm kiếm và sắp xếp trên `body` tuân theo collation.

Collation cụ thể có thể làm hai chuỗi khác byte được xem là bằng nhau khi so sánh. Chẳng hạn, một collation không phân biệt hoa/thường có thể coi `'MySQL'` và `'mysql'` là bằng nhau. Hãy chọn collation theo yêu cầu ngôn ngữ và nghiệp vụ.

Kiểm tra charset/collation thực tế:

~~~sql
SELECT
    CHARSET(body) AS character_set_name,
    COLLATION(body) AS collation_name
FROM articles
LIMIT 1;
~~~

### BLOB: chuỗi byte nhị phân

BLOB có character set và collation là `binary`. MySQL không tự diễn giải nội dung BLOB theo UTF-8 hay một bảng mã văn bản khác.

~~~sql
CREATE TABLE attachments (
    id BIGINT UNSIGNED PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    payload MEDIUMBLOB NOT NULL
);
~~~

Ví dụ, hai byte có giá trị `0x41` và `0x61` được so sánh theo byte, nên khác nhau. BLOB không có quy tắc không phân biệt hoa/thường hoặc dấu như một số collation của TEXT.

Kiểm tra kiểu chuỗi:

~~~sql
SELECT
    CHARSET(payload) AS character_set_name,
    COLLATION(payload) AS collation_name,
    LENGTH(payload) AS byte_length,
    HEX(payload) AS hex_value
FROM attachments;
~~~

Kết quả của `CHARSET(payload)` và `COLLATION(payload)` là `binary`.

### Chuyển đổi giữa BLOB và TEXT

Chỉ chuyển BLOB sang TEXT khi biết byte được mã hóa bằng character set nào. Ví dụ, nếu BLOB thực sự chứa UTF-8:

~~~sql
SELECT CONVERT(payload USING utf8mb4) AS decoded_text
FROM attachments;
~~~

Nếu byte là JPEG, PDF, dữ liệu nén hoặc ciphertext, chuyển sang TEXT không làm nó trở thành văn bản hợp lệ. Kết quả có thể chứa ký tự không hợp lệ hoặc bị biến đổi khi xử lý.

Ngược lại, nếu cần lấy byte của một chuỗi văn bản, có thể dùng `CONVERT(... USING BINARY)` hoặc hàm phù hợp với mục tiêu mã hóa. Hãy phân biệt chuyển đổi charset với việc giữ nguyên byte gốc.

## 4. Chọn cấp độ nào?

| Kiểu | Nên dùng khi | Ví dụ |
|---|---|---|
| `TINYTEXT` / `TINYBLOB` | Nội dung rất ngắn, giới hạn tối đa 255 byte | Mẩu ghi chú ngắn, payload nhị phân nhỏ |
| `TEXT` / `BLOB` | Nội dung không vượt quá khoảng 64 KiB | Mô tả dài, tài liệu nhỏ |
| `MEDIUMTEXT` / `MEDIUMBLOB` | Nội dung có thể đạt vài MiB | Bài viết lớn, nội dung HTML, tệp đính kèm cỡ vừa |
| `LONGTEXT` / `LONGBLOB` | Có yêu cầu thực tế về dữ liệu nhiều trăm MiB hoặc lớn hơn | Nội dung rất lớn hoặc tệp lớn được lưu trong database |

Một số nguyên tắc lựa chọn:

- Chọn kiểu nhỏ nhất có thể đáp ứng giới hạn dữ liệu đã biết và dự kiến tăng trưởng hợp lý.
- Nếu dữ liệu luôn ngắn và có giới hạn rõ, ưu tiên `VARCHAR(N)` hoặc `VARBINARY(N)` thay vì TEXT/BLOB.
- Chọn TEXT cho nội dung cần charset/collation, BLOB cho nội dung cần giữ byte.
- Không chọn LONG chỉ để tránh suy nghĩ về kích thước; dữ liệu lớn ảnh hưởng tới packet, bộ nhớ, backup, replication, I/O và thời gian truy vấn.
- Kiểm tra kích thước lớn nhất mà ứng dụng thực sự gửi và nhận, không chỉ giới hạn lý thuyết của kiểu.

### TEXT/BLOB khác VARCHAR/VARBINARY ở đâu?

Có thể xem TEXT như một kiểu tương tự VARCHAR rất lớn, và BLOB tương tự VARBINARY rất lớn. Tuy nhiên, chúng có một số khác biệt đáng chú ý:

| Đặc điểm | VARCHAR / VARBINARY | TEXT / BLOB |
|---|---|---|
| Độ dài khai báo | Bắt buộc có giới hạn `N` | Có thể bỏ qua giới hạn; có bốn cấp độ |
| Ý nghĩa độ dài | VARCHAR tính theo ký tự; VARBINARY tính theo byte | TEXT giới hạn theo byte sau mã hóa; BLOB theo byte |
| DEFAULT | Có thể khai báo DEFAULT theo quy tắc phiên bản | Không hỗ trợ DEFAULT |
| Index B-tree | Có thể index toàn bộ cột nếu giới hạn cho phép | Phải khai báo prefix length |
| Lưu trữ InnoDB | Có thể lưu off-page nếu hàng lớn | Có thể lưu off-page nếu hàng lớn |
| Mục đích | Chuỗi có giới hạn rõ ràng | Nội dung lớn, biến độ dài |

Ví dụ khai báo `body TEXT DEFAULT ''` là không hợp lệ vì TEXT/BLOB không hỗ trợ giá trị DEFAULT. Nếu cần giá trị ban đầu, ứng dụng có thể truyền rõ chuỗi rỗng khi INSERT hoặc dùng logic ở tầng ứng dụng.

Một khác biệt nhỏ nhưng quan trọng khi dùng TEXT làm khóa: giá trị TEXT không được tự động đệm hoặc loại bỏ byte khi INSERT/SELECT. Tuy nhiên, phép so sánh các entry của index TEXT có quy tắc đệm dấu cách ở cuối. Vì vậy, nếu tạo unique index trên TEXT, hai giá trị chỉ khác số dấu cách cuối có thể bị xem là trùng khóa. Quy tắc này không áp dụng tương tự cho BLOB. Tránh dùng TEXT làm định danh duy nhất nếu nghiệp vụ yêu cầu phân biệt chính xác từng byte hoặc dấu cách cuối.

## 5. Cách InnoDB lưu TEXT/BLOB

TEXT và BLOB là kiểu biến độ dài. Trong InnoDB, các cột lớn có thể được lưu ngoài trang dữ liệu chính (off-page) trên các overflow pages.

Cách lưu phụ thuộc row format và kích thước của hàng:

- Với `ROW_FORMAT=DYNAMIC` hoặc `COMPRESSED`, InnoDB có thể lưu toàn bộ giá trị dài ở off-page. Bản ghi trong clustered index giữ con trỏ 20 byte tới overflow pages.
- Với `ROW_FORMAT=COMPACT` hoặc `REDUNDANT`, 768 byte đầu của cột BLOB/TEXT/VARCHAR có thể nằm trong bản ghi clustered index, phần còn lại nằm ở overflow pages kèm con trỏ.
- Với `DYNAMIC`, các giá trị TEXT/BLOB ngắn hơn hoặc bằng 40 byte luôn được lưu inline; quyết định lưu off-page còn phụ thuộc tổng kích thước hàng và page size.

Row format mặc định của InnoDB hiện là DYNAMIC trong cấu hình mặc định. Tuy vậy, khi phân tích một bảng cũ hoặc môi trường được tùy chỉnh, hãy kiểm tra row format thực tế:

~~~sql
SHOW TABLE STATUS
FROM your_database
LIKE 'articles';
~~~

Hoặc:

~~~sql
SELECT
    NAME,
    ROW_FORMAT
FROM INFORMATION_SCHEMA.INNODB_TABLES
WHERE NAME = 'your_database/articles';
~~~

Việc lưu off-page không có nghĩa là truy vấn cột lớn luôn rẻ. Khi SELECT nội dung lớn, MySQL vẫn phải đọc overflow pages, truyền dữ liệu qua protocol và đưa dữ liệu tới client. Nếu truy vấn chỉ cần ID, tiêu đề hoặc trạng thái, đừng lấy cột nội dung lớn một cách không cần thiết.

## 6. Index trên TEXT và BLOB

### B-tree index bắt buộc có prefix length

Với CHAR/VARCHAR, prefix length là tùy chọn. Với TEXT/BLOB, khi tạo B-tree index phải chỉ định số ký tự hoặc byte đầu tiên được lập chỉ mục.

~~~sql
CREATE TABLE article_search (
    id BIGINT UNSIGNED PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    KEY idx_body_prefix (body(100))
) ENGINE=InnoDB;
~~~

Ở đây, index chỉ lưu 100 ký tự đầu của `body`. Với BLOB, prefix length được tính bằng byte:

~~~sql
CREATE TABLE binary_objects (
    id BIGINT UNSIGNED PRIMARY KEY,
    payload LONGBLOB NOT NULL,
    KEY idx_payload_prefix (payload(32))
) ENGINE=InnoDB;
~~~

### Giới hạn prefix index

Prefix length bị giới hạn theo storage engine, row format và page size. Với InnoDB page size mặc định 16 KiB:

| InnoDB row format | Prefix index tối đa |
|---|---:|
| REDUNDANT hoặc COMPACT | 767 byte |
| DYNAMIC hoặc COMPRESSED | 3.072 byte |

MyISAM có giới hạn prefix 1.000 byte. Giới hạn thực tế có thể thấp hơn khi page size nhỏ hơn hoặc do tổng độ dài key của index nhiều cột.

Trong MySQL 9.7, B-tree index trên TEXT/BLOB được hỗ trợ bởi InnoDB, MyISAM và BLACKHOLE. Khả năng index và giới hạn cụ thể còn phụ thuộc storage engine; không suy rộng các giới hạn InnoDB sang mọi engine.

Một điểm dễ nhầm:

- Prefix length trong câu lệnh index của TEXT được hiểu là số ký tự.
- Prefix length của BLOB được hiểu là số byte.
- Giới hạn kỹ thuật của index được đo bằng byte.

Ví dụ `body(200)` với `utf8mb4` có thể cần tối đa 800 byte cho phần prefix, vì một ký tự có thể dùng tới 4 byte. Đừng lấy giới hạn 3.072 byte rồi khai báo 3.072 ký tự cho cột TEXT utf8mb4.

### Prefix index không lưu toàn bộ nội dung

Index `body(100)` chỉ giúp MySQL tìm các giá trị có phần đầu phù hợp. Nếu điều kiện tìm kiếm yêu cầu so sánh toàn bộ giá trị, máy chủ có thể phải đọc hàng và kiểm tra phần còn lại.

~~~sql
SELECT id
FROM article_search
WHERE body = 'A long article body ...';
~~~

Index prefix có thể giúp loại bỏ các hàng có prefix khác, nhưng vẫn cần xác minh giá trị đầy đủ. Hai nội dung khác nhau nhưng cùng 100 ký tự đầu sẽ có cùng prefix index.

Vì thế:

- Chọn prefix có độ phân biệt đủ cao dựa trên dữ liệu thật.
- Dùng `SHOW INDEX` để xem prefix đã tạo.
- Dùng `EXPLAIN` để xác nhận optimizer có sử dụng index.
- Không dùng unique prefix index nếu yêu cầu nghiệp vụ là bảo đảm toàn bộ nội dung duy nhất.

Nếu cần nhận diện nội dung lớn theo toàn bộ giá trị, có thể tính hash như SHA-256 ở tầng ứng dụng rồi lưu vào `BINARY(32)` và index cột hash. Khi so sánh chính xác, vẫn nên kiểm tra lại nội dung để xử lý khả năng va chạm hash theo yêu cầu nghiệp vụ.

~~~sql
CREATE TABLE documents (
    id BIGINT UNSIGNED PRIMARY KEY,
    body MEDIUMTEXT NOT NULL,
    body_sha256 BINARY(32) NOT NULL,
    KEY idx_body_sha256 (body_sha256)
);
~~~

### FULLTEXT index cho văn bản

Nếu mục tiêu là tìm từ hoặc cụm từ trong nội dung, prefix B-tree không phải công cụ tìm kiếm toàn văn. MySQL hỗ trợ FULLTEXT index trên CHAR, VARCHAR và TEXT với InnoDB hoặc MyISAM.

~~~sql
CREATE TABLE knowledge_articles (
    id BIGINT UNSIGNED PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE=InnoDB;
~~~

Truy vấn:

~~~sql
SELECT
    id,
    MATCH(title, body) AGAINST ('transaction index' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_articles
WHERE MATCH(title, body) AGAINST ('transaction index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

FULLTEXT có tokenizer, stopword, minimum token length và quy tắc tìm kiếm riêng. Kết quả không tương đương tìm chuỗi con tùy ý bằng `LIKE '%word%'`. Hãy kiểm tra cấu hình parser và ngôn ngữ của dữ liệu trước khi dùng cho tìm kiếm tiếng Việt.

## 7. Các giới hạn khi truy vấn TEXT/BLOB

### max_sort_length

Khi sắp xếp BLOB/TEXT, MySQL chỉ dùng số byte đầu được xác định bởi biến `max_sort_length`. Giá trị mặc định là 1024 byte. Nếu phần dữ liệu cần phân biệt nằm sau đoạn đầu này, thứ tự sắp xếp hoặc nhóm có thể không phản ánh toàn bộ nội dung như mong đợi.

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'max_sort_length';
~~~

Nếu nghiệp vụ thật sự cần so sánh/sắp xếp nội dung dài, hãy đánh giá tác động khi tăng biến này ở cấp session hoặc server. Sắp xếp một lượng lớn nội dung dài vẫn tốn tài nguyên; tốt hơn là sắp xếp theo cột khóa, thời gian, tiêu đề hoặc metadata có kích thước nhỏ nếu phù hợp.

### Temporary table và SELECT *

Nếu kết quả của truy vấn cần temporary table và chứa cột TEXT/BLOB, MySQL có thể phải dùng temporary table trên đĩa vì MEMORY engine không hỗ trợ các kiểu này. Điều đó làm tăng I/O và có thể ảnh hưởng hiệu năng.

Ví dụ nên tránh khi không cần nội dung:

~~~sql
-- Lấy tất cả cột, bao gồm body rất lớn
SELECT *
FROM articles
WHERE id = 100;
~~~

Thay bằng:

~~~sql
-- Chỉ lấy metadata cần cho danh sách
SELECT id, title, created_at
FROM articles
WHERE id = 100;
~~~

Chỉ lấy nội dung khi màn hình hoặc nghiệp vụ thực sự cần đọc nó.

### max_allowed_packet và bộ nhớ

Giới hạn kiểu dữ liệu không đồng nghĩa client có thể gửi một giá trị lớn như vậy trong một lần truyền. Kích thước packet và bộ nhớ khả dụng có thể giới hạn dữ liệu thực tế.

Biến `max_allowed_packet` ảnh hưởng kích thước message mà client/server có thể xử lý. Khi truyền BLOB/TEXT lớn, phải kiểm tra cả phía server và client như mysql client hoặc mysqldump. Nếu packet quá lớn, có thể gặp lỗi `Packet too large` hoặc kết nối bị đóng.

Kiểm tra phía server:

~~~sql
SHOW VARIABLES LIKE 'max_allowed_packet';
~~~

Không tăng packet lên mức tối đa một cách tùy tiện. Cần cân nhắc bộ nhớ, số kết nối đồng thời, ứng dụng, connector và nguy cơ một request lớn gây áp lực lên máy chủ.

### Strict SQL mode và dữ liệu vượt giới hạn

Nếu gán giá trị vượt quá giới hạn cột:

- Khi strict SQL mode được bật, MySQL báo lỗi và không chấp nhận giá trị bị cắt.
- Khi strict SQL mode tắt, giá trị có thể bị cắt để vừa cột và phát sinh warning.
- Việc cắt các dấu cách dư ở cuối giá trị TEXT có quy tắc cảnh báo riêng.

Kiểm tra SQL mode:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Không dựa vào hành vi tự cắt dữ liệu. Hãy kiểm tra độ dài đầu vào ở tầng ứng dụng, thiết lập strict mode phù hợp và xử lý lỗi rõ ràng để tránh mất nội dung mà không biết.

## 8. Ví dụ thiết kế bảng thực tế

### Lưu bài viết

~~~sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    slug VARCHAR(200) NOT NULL,
    title VARCHAR(300) NOT NULL,
    summary TEXT,
    body MEDIUMTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_articles_slug (slug),
    FULLTEXT KEY ft_articles_content (title, body)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
~~~

Giải thích:

- `slug` có giới hạn rõ ràng và cần unique nên dùng VARCHAR.
- `title` là chuỗi ngắn, dùng VARCHAR.
- `summary` là đoạn văn ngắn có thể thay đổi độ dài; TEXT là một lựa chọn.
- `body` là nội dung bài viết dài; MEDIUMTEXT thường phù hợp hơn TEXT nếu bài có thể lớn hơn 64 KiB.
- FULLTEXT index phục vụ tìm kiếm toàn văn trên tiêu đề và nội dung.

Nếu chỉ truy xuất tiêu đề và thời gian cho trang danh sách, không cần SELECT `body`.

### Lưu tệp đính kèm

~~~sql
CREATE TABLE attachments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id BIGINT UNSIGNED NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    byte_size BIGINT UNSIGNED NOT NULL,
    sha256 BINARY(32) NOT NULL,
    payload LONGBLOB NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_attachments_owner_created (owner_id, created_at),
    KEY idx_attachments_sha256 (sha256)
) ENGINE=InnoDB;
~~~

Giải thích:

- Tên file và MIME type là chuỗi ký tự có giới hạn, dùng VARCHAR.
- Kích thước file là số byte, dùng BIGINT UNSIGNED.
- SHA-256 là 32 byte, dùng BINARY(32), không cần BLOB.
- Nội dung file có thể dùng LONGBLOB nếu có yêu cầu lưu trong MySQL.

Với tệp lớn hoặc số lượng tệp nhiều, hãy cân nhắc object storage hoặc hệ thống file riêng. Database có thể chỉ lưu metadata, checksum, kích thước, storage key và quyền truy cập. Cách này giúp backup database nhỏ hơn và tránh truyền các tệp lớn qua truy vấn thường xuyên. Quyết định phụ thuộc yêu cầu transaction, retention, replication, bảo mật và hạ tầng của ứng dụng.

## 9. Các hàm hữu ích để kiểm tra nội dung

| Hàm | Ý nghĩa |
|---|---|
| `CHAR_LENGTH(expr)` | Số ký tự trong chuỗi |
| `LENGTH(expr)` | Số byte của chuỗi |
| `OCTET_LENGTH(expr)` | Số byte, tương đương LENGTH |
| `CHARSET(expr)` | Character set của biểu thức |
| `COLLATION(expr)` | Collation của biểu thức |
| `HEX(expr)` | Biểu diễn byte dưới dạng hệ thập lục phân |
| `CONVERT(expr USING charset)` | Chuyển chuỗi sang character set chỉ định |

Ví dụ với dữ liệu Unicode:

~~~sql
SELECT
    'Cơ sở dữ liệu' AS sample_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    LENGTH('Cơ sở dữ liệu') AS byte_count,
    CHARSET('Cơ sở dữ liệu') AS character_set_name,
    COLLATION('Cơ sở dữ liệu') AS collation_name;
~~~

Nếu connection character set là utf8mb4, số byte có thể lớn hơn số ký tự vì các ký tự Unicode không phải ASCII cần nhiều byte hơn. `CHAR_LENGTH` đo ký tự; `LENGTH` đo byte.

## 10. Bài thực hành: TEXT, BLOB và prefix index

Thực hiện trên database lab riêng.

### Bước 1: tạo bảng thử nghiệm

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_large_values_lab;
USE mysql_large_values_lab;

CREATE TABLE notes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (id),
    KEY idx_body_prefix (body(100))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE binary_samples (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(100) NOT NULL,
    payload MEDIUMBLOB NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
~~~

### Bước 2: thêm văn bản Unicode

~~~sql
INSERT INTO notes (title, body)
VALUES (
    'Giới thiệu MySQL',
    'Cơ sở dữ liệu quan hệ lưu trữ dữ liệu theo bảng. MySQL hỗ trợ transaction, index và nhiều kiểu dữ liệu văn bản.'
);
~~~

Đọc nội dung và kiểm tra kích thước:

~~~sql
SELECT
    id,
    title,
    CHAR_LENGTH(body) AS character_count,
    OCTET_LENGTH(body) AS byte_count,
    CHARSET(body) AS character_set_name,
    COLLATION(body) AS collation_name
FROM notes;
~~~

Quan sát `byte_count` lớn hơn hoặc bằng `character_count`. Sự chênh lệch phụ thuộc ký tự và encoding.

### Bước 3: thêm byte nhị phân

~~~sql
INSERT INTO binary_samples (label, payload)
VALUES
    ('sample-bytes', X'0041FF7F');
~~~

Đọc dữ liệu:

~~~sql
SELECT
    id,
    label,
    LENGTH(payload) AS byte_count,
    HEX(payload) AS payload_hex,
    CHARSET(payload) AS character_set_name,
    COLLATION(payload) AS collation_name
FROM binary_samples;
~~~

Kết quả HEX phải thể hiện đúng dãy byte `0041FF7F`. Byte `00` và `FF` vẫn là dữ liệu hợp lệ trong BLOB.

### Bước 4: kiểm tra index

~~~sql
SHOW INDEX FROM notes;

EXPLAIN
SELECT id
FROM notes
WHERE body LIKE 'Cơ sở dữ liệu%';
~~~

Quan sát cột `Sub_part` của index để thấy prefix length đã khai báo. Kết quả EXPLAIN phụ thuộc số hàng, thống kê và độ chọn lọc; với bảng rất nhỏ, optimizer có thể chọn table scan. Không kết luận index hỏng chỉ vì bảng lab ít dữ liệu.

### Bước 5: thử truy vấn chỉ lấy metadata

~~~sql
SELECT id, title
FROM notes
ORDER BY id DESC
LIMIT 20;
~~~

Sau đó so sánh với:

~~~sql
SELECT *
FROM notes
ORDER BY id DESC
LIMIT 20;
~~~

Khi nội dung body lớn, truy vấn đầu giảm lượng dữ liệu cần đọc và truyền nếu màn hình chỉ cần tiêu đề. Đây là thói quen quan trọng khi thiết kế API và trang danh sách.

### Bước 6: dọn dẹp

~~~sql
DROP DATABASE mysql_large_values_lab;
~~~

Chỉ chạy lệnh này trên database lab vừa tạo. Lệnh sẽ xóa toàn bộ dữ liệu thực hành trong database.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Data too long for column` | Giá trị vượt giới hạn kiểu hoặc byte sau khi mã hóa | Kiểm tra kiểu TEXT/BLOB, charset, kích thước thực tế và strict mode |
| `Packet too large` | Giá trị gửi vượt packet limit của client/server | Kiểm tra `max_allowed_packet` ở cả hai phía và bộ nhớ |
| Không thể tạo index | TEXT/BLOB thiếu prefix length hoặc prefix vượt giới hạn | Khai báo prefix phù hợp và kiểm tra row format, page size |
| `BLOB/TEXT column can't have a default value` | Cố khai báo DEFAULT cho TEXT/BLOB | Bỏ DEFAULT; truyền giá trị tường minh từ ứng dụng |
| Tìm kiếm không phân biệt dấu/hoa thường như mong muốn | Collation của TEXT không phù hợp | Chọn collation đúng hoặc dùng phép chuyển đổi/collation rõ ràng |
| BLOB hiển thị thành hex | Client hiển thị chuỗi nhị phân theo dạng hexadecimal | Dùng HEX để kiểm tra byte; giải mã ở ứng dụng theo encoding đã biết |
| Truy vấn chậm khi SELECT * | Lấy nội dung lớn không cần thiết hoặc tạo temporary table trên đĩa | Chỉ SELECT cột cần dùng, phân trang và lấy nội dung ở request chi tiết |
| Kết quả sắp xếp TEXT dài không như mong đợi | `max_sort_length` chỉ xét số byte đầu theo cấu hình | Kiểm tra biến này và cân nhắc sắp xếp theo metadata phù hợp |

## 12. Quy tắc chọn kiểu trong thiết kế schema

Trước khi tạo cột lớn, hãy trả lời các câu hỏi sau:

1. Nội dung là văn bản hay byte nhị phân?
2. Cần so sánh theo ngôn ngữ/collation hay so sánh byte chính xác?
3. Kích thước lớn nhất thực tế tính theo byte là bao nhiêu?
4. Có cần tìm kiếm toàn văn, tìm prefix, so sánh toàn bộ hay chỉ lấy nội dung theo ID?
5. Dữ liệu có được đọc trong các truy vấn danh sách hay chỉ đọc ở màn hình chi tiết?
6. Có nên lưu nội dung trong database hay object storage phù hợp hơn?
7. Connector, client, server, backup và replication có xử lý được kích thước dữ liệu dự kiến không?

Một số quy tắc nhanh:

- Văn bản ngắn có giới hạn rõ: dùng VARCHAR.
- Văn bản dài, cần Unicode và collation: dùng TEXT family.
- Byte nhị phân cần giữ nguyên: dùng BLOB family.
- Nội dung thường nằm trong 64 KiB: cân nhắc TEXT/BLOB.
- Nội dung có thể vượt 64 KiB nhưng dưới 16 MiB: cân nhắc MEDIUMTEXT/MEDIUMBLOB.
- Chỉ dùng LONGTEXT/LONGBLOB khi yêu cầu dung lượng thực tế đòi hỏi.
- Không lấy cột lớn trong truy vấn danh sách nếu không cần.
- Prefix index chỉ phù hợp cho truy vấn theo phần đầu; tìm kiếm ngôn ngữ tự nhiên nên đánh giá FULLTEXT.
- Khi lưu tệp lớn, cân nhắc metadata trong MySQL và nội dung ở object storage.

## Tài liệu tham khảo chính thức

Các giới hạn và hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [The BLOB and TEXT Types](https://dev.mysql.com/doc/refman/9.7/en/blob.html): khác biệt chuỗi ký tự và chuỗi byte, giới hạn, DEFAULT, prefix index, max_sort_length và max_allowed_packet.
2. [String Data Type Syntax](https://dev.mysql.com/doc/refman/9.7/en/string-type-syntax.html): các cấp TINY/TEXT/MEDIUM/LONG và byte lưu độ dài.
3. [Data Type Storage Requirements](https://dev.mysql.com/doc/refman/9.7/en/storage-requirements.html): cách tính dung lượng lưu trữ và ảnh hưởng của character set.
4. [Column Indexes](https://dev.mysql.com/doc/refman/9.7/en/column-indexes.html): prefix index và FULLTEXT index.
5. [CREATE INDEX Statement](https://dev.mysql.com/doc/refman/9.7/en/create-index.html): cú pháp prefix, giới hạn theo storage engine và quy tắc unique prefix.
6. [InnoDB Row Formats](https://dev.mysql.com/doc/refman/9.7/en/innodb-row-format.html): inline/off-page storage của cột biến độ dài.
7. [Character Sets and Collations](https://dev.mysql.com/doc/refman/9.7/en/charset.html): character set, collation và quy tắc so sánh chuỗi.

