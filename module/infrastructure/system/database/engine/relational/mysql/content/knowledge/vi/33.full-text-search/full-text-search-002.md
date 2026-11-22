# FULLTEXT index và điều kiện engine/cột hỗ trợ

MySQL cung cấp **FULLTEXT index** để tìm kiếm từ hoặc cụm từ trong nội dung văn bản. Khác với B-tree index thường dùng cho so sánh bằng, khoảng giá trị và sắp xếp, FULLTEXT index phân tích văn bản thành các token rồi lập chỉ mục để phục vụ tìm kiếm ngôn ngữ tự nhiên hoặc truy vấn Boolean.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Tìm kiếm văn bản**, bài này tập trung vào FULLTEXT index và các điều kiện về storage engine, kiểu cột và parser. `SPECIAL_NOTE` được cung cấp rỗng, vì vậy không có ràng buộc riêng bổ sung cho bài.

## 1. FULLTEXT index giải quyết bài toán nào?

Giả sử bảng bài viết có tiêu đề và nội dung dài. Ứng dụng cần tìm những bài chứa các từ khóa như `mysql`, `index` hoặc cụm từ `query optimizer`.

Nếu chỉ dùng:

```sql
SELECT *
FROM articles
WHERE body LIKE '%mysql%';
```

MySQL phải kiểm tra nội dung của các hàng phù hợp. B-tree index thông thường không giúp tìm hiệu quả với wildcard ở đầu chuỗi (`%mysql%`). Khi dữ liệu văn bản lớn, kiểu tìm kiếm này có thể tốn nhiều I/O và CPU.

FULLTEXT index lập chỉ mục token trong văn bản để hỗ trợ các truy vấn tìm kiếm:

```sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
```

FULLTEXT không phải công cụ thay thế mọi phép tìm chuỗi. Nếu cần tìm một đoạn ký tự con, mã định danh, chuỗi chính xác hoặc pattern tùy ý, `LIKE`, B-tree trên cột phù hợp hoặc giải pháp tìm kiếm khác có thể thích hợp hơn.

## 2. Storage engine nào hỗ trợ FULLTEXT?

Trong MySQL, FULLTEXT index được hỗ trợ bởi hai storage engine chính:

| Storage engine | FULLTEXT | Đặc điểm đáng chú ý |
|---|---|---|
| InnoDB | Có | Engine transactional, thường là lựa chọn mặc định cho ứng dụng mới. |
| MyISAM | Có | Engine cũ, không có transaction và có cơ chế khóa bảng. |
| MEMORY | Không | Không hỗ trợ FULLTEXT index. |
| CSV | Không | Không hỗ trợ FULLTEXT index. |
| Các engine khác | Tùy engine | Không được mặc định là có hỗ trợ; kiểm tra tài liệu engine đang dùng. |

Với phần lớn ứng dụng mới, nên ưu tiên InnoDB vì transaction, phục hồi sau sự cố và khóa ở mức hàng. MyISAM vẫn có thể gặp trong hệ thống cũ hoặc workload đặc thù, nhưng cần tính đến việc engine không hỗ trợ transaction và có hành vi khóa khác InnoDB.

Kiểm tra engine của bảng:

```sql
SHOW TABLE STATUS
LIKE 'articles';

SHOW CREATE TABLE articles;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles';
```

Nếu bảng đang dùng engine không hỗ trợ FULLTEXT, việc khai báo FULLTEXT index sẽ thất bại. Có thể cân nhắc chuyển bảng sang InnoDB sau khi đánh giá tương thích, dung lượng, khóa ngoại, kiểu dữ liệu và kế hoạch migration:

```sql
ALTER TABLE articles ENGINE = InnoDB;
```

Chuyển engine là thao tác thay đổi cấu trúc và có thể tốn thời gian, I/O, không gian tạm cũng như khóa bảng trong một phần quá trình. Hãy thử trên bản sao dữ liệu và lên kế hoạch triển khai phù hợp.

## 3. Kiểu cột nào có thể được lập FULLTEXT index?

FULLTEXT index chỉ áp dụng trực tiếp cho các cột ký tự thuộc một trong các kiểu:

- `CHAR`
- `VARCHAR`
- `TEXT` và các biến thể thuộc họ TEXT như `TINYTEXT`, `MEDIUMTEXT`, `LONGTEXT`

Các kiểu số như `INT`, `BIGINT`, `DECIMAL`, kiểu ngày giờ, `BLOB` và kiểu JSON không phải các kiểu cột trực tiếp được FULLTEXT index hỗ trợ.

Ví dụ hợp lệ:

```sql
CREATE TABLE articles (
    article_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    summary TEXT,
    body LONGTEXT,
    published_at DATETIME,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE = InnoDB;
```

FULLTEXT index ở trên bao gồm hai cột ký tự của cùng một bảng. Không thể tạo một FULLTEXT index kết hợp cột từ nhiều bảng khác nhau.

Ví dụ không hợp lệ về kiểu cột:

```sql
CREATE TABLE invalid_fulltext_example (
    id BIGINT NOT NULL PRIMARY KEY,
    title VARCHAR(200),
    payload JSON,
    created_at DATETIME,
    FULLTEXT KEY ft_payload (payload)
) ENGINE = InnoDB;
```

`payload` có kiểu JSON nên không thể đưa trực tiếp vào FULLTEXT index theo quy tắc kiểu cột. Nếu cần tìm kiếm nội dung nằm trong JSON, hãy thiết kế một thuộc tính văn bản riêng hoặc một mô hình trích xuất phù hợp, rồi xác minh kiểu cột và khả năng index với phiên bản MySQL đang triển khai.

## 4. Điều kiện về bảng và danh sách cột

Khi tạo FULLTEXT index, cần bảo đảm:

1. Bảng sử dụng storage engine có hỗ trợ FULLTEXT, thường là InnoDB hoặc MyISAM.
2. Mỗi cột trong danh sách index có kiểu CHAR, VARCHAR hoặc TEXT.
3. Các cột thuộc cùng một bảng.
4. Bảng có charset/collation phù hợp với nội dung và cách tìm kiếm mong muốn.
5. Danh sách cột trong `MATCH()` tương ứng với danh sách cột của một FULLTEXT index đã tạo.

Một FULLTEXT index có thể lập chỉ mục một cột hoặc nhiều cột. Ví dụ:

```sql
-- Ví dụ bổ sung index riêng cho tiêu đề.
ALTER TABLE articles
ADD FULLTEXT KEY ft_title (title);
```

Bảng articles trong ví dụ ở mục 3 đã có index kết hợp title/body. Chỉ bổ sung index riêng cho title nếu workload thực sự có truy vấn `MATCH(title)`; không tạo index trùng với index đã có. Câu truy vấn `MATCH(title, body)` phải dùng đúng tập cột được lập chỉ mục tương ứng.

FULLTEXT index không nhận prefix length theo cách khai báo như B-tree index. Không viết `FULLTEXT KEY ft_body (body(100))`.

## 5. Tạo FULLTEXT index

Có thể tạo FULLTEXT index ngay khi tạo bảng:

```sql
CREATE TABLE product_documents (
    document_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    description TEXT,
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_title_description (title, description)
) ENGINE = InnoDB;
```

Hoặc tạo sau khi bảng đã tồn tại:

```sql
ALTER TABLE articles
ADD FULLTEXT INDEX ft_articles_title_body (title, body);
```

Hoặc dùng cú pháp:

```sql
CREATE FULLTEXT INDEX ft_articles_title_body
ON articles (title, body);
```

Các cách trên đều tạo FULLTEXT index cho tập cột được chỉ định. Tạo index trên bảng lớn có thể cần đọc và phân tích nhiều dữ liệu, tốn CPU, I/O và dung lượng lưu trữ; đánh giá thời gian và tác động khóa trước khi thực hiện trên production.

Các câu lệnh ở mục này là các cách tạo index thay thế nhau. Chỉ dùng một cách và chỉ khi bảng chưa có FULLTEXT index trên cùng tập cột; ví dụ ở mục 3 đã tạo index title/body ngay trong CREATE TABLE.

## 6. Dùng MATCH ... AGAINST

`MATCH()` xác định các cột cần tìm kiếm; `AGAINST()` cung cấp chuỗi truy vấn và search mode.

Ví dụ:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
```

Trong ví dụ:

- `MATCH(title, body)` tìm trong hai cột đã được lập chỉ mục cùng nhau.
- `AGAINST(...)` chỉ định từ khóa tìm kiếm.
- `IN NATURAL LANGUAGE MODE` yêu cầu chế độ ngôn ngữ tự nhiên.
- Điểm `relevance` biểu thị mức độ phù hợp tương đối của kết quả theo thuật toán FULLTEXT.

Nếu bỏ qua search mode, MySQL mặc định dùng natural language mode. Tuy nhiên, nên ghi rõ mode trong truy vấn để người đọc hiểu hành vi mong muốn.

Không nên diễn giải relevance như xác suất hay điểm chất lượng tuyệt đối. Đây là điểm xếp hạng của MySQL dựa trên nội dung, token và thống kê của tập dữ liệu.

Natural language mode của MyISAM còn có ngưỡng 50%: từ xuất hiện trong hơn một nửa số hàng có thể bị xem là không đủ khả năng phân biệt và bị bỏ qua trong kết quả. InnoDB không áp dụng ngưỡng 50% này. Vì vậy, cùng một dữ liệu và truy vấn có thể cho kết quả khác nhau khi đổi engine.

## 7. Các search mode cơ bản

MySQL có ba cách tìm kiếm FULLTEXT thường gặp:

| Mode | Cú pháp | Mục đích |
|---|---|---|
| Natural language | `IN NATURAL LANGUAGE MODE` | Tìm theo ý nghĩa từ khóa và xếp hạng relevance. |
| Boolean | `IN BOOLEAN MODE` | Dùng toán tử để yêu cầu, loại trừ hoặc kết hợp từ khóa. |
| Query expansion | `WITH QUERY EXPANSION` | Mở rộng truy vấn dựa trên các kết quả ban đầu. |

### 7.1. Natural language mode

`IN NATURAL LANGUAGE MODE` là mode mặc định. MySQL phân tích từ khóa, tính relevance và trả về các hàng phù hợp:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
```

Các từ bị xem là stopword hoặc ngắn hơn ngưỡng token có thể bị bỏ qua. Vì vậy, truy vấn một từ quá ngắn hoặc phổ biến có thể không trả kết quả như người mới mong đợi.

### 7.2. Boolean mode

Boolean mode cho phép dùng toán tử để biểu đạt điều kiện tìm kiếm:

| Toán tử | Ý nghĩa phổ biến |
|---|---|
| `+word` | Từ phải xuất hiện. |
| `-word` | Loại kết quả có từ đó. |
| `word*` | Tìm token có tiền tố word. |
| `"a phrase"` | Tìm cụm từ theo thứ tự. |
| `word` | Từ được phép xuất hiện nhưng không nhất thiết bắt buộc. |

Ví dụ yêu cầu có `mysql`, đồng thời không có `oracle`:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('+mysql -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+mysql -oracle' IN BOOLEAN MODE)
ORDER BY score DESC;
```

Ví dụ tìm tiền tố:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transact*' IN BOOLEAN MODE);
```

Boolean mode có quy tắc cú pháp riêng; không ghép toán tử một cách tùy ý. Đặc biệt, dấu `+` và `-` phải gắn đúng với token mà chúng bổ nghĩa.

### 7.3. Query expansion

`WITH QUERY EXPANSION` thực hiện tìm kiếm lần đầu, sau đó dùng một số tài liệu phù hợp để mở rộng từ khóa cho lần tìm tiếp theo:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' WITH QUERY EXPANSION);
```

Mode này có thể tìm thêm tài liệu liên quan về từ ngữ nhưng cũng có thể làm kết quả lệch khỏi ý định ban đầu. Chỉ bật khi đã kiểm thử chất lượng kết quả với dữ liệu và truy vấn thực tế.

## 8. FULLTEXT index nhiều cột và MATCH()

Nếu tạo index:

```sql
FULLTEXT KEY ft_title_body (title, body)
```

thì truy vấn tương ứng:

```sql
MATCH(title, body) AGAINST ('mysql' IN NATURAL LANGUAGE MODE)
```

Danh sách cột trong MATCH phải tương ứng với một FULLTEXT index. Không tạo index kết hợp `(title, body)` rồi truy vấn `MATCH(title)` và kỳ vọng MySQL tự dùng index kết hợp đó.

Nếu nhu cầu tìm riêng title và tìm kết hợp title/body đều quan trọng, có thể duy trì hai FULLTEXT index như ví dụ đã tạo ở mục 3 và 4:

| FULLTEXT index | Câu MATCH tương ứng |
|---|---|
| `ft_title_body (title, body)` | `MATCH(title, body)` |
| `ft_title (title)` | `MATCH(title)` |

Mỗi index tăng dung lượng lưu trữ và chi phí duy trì khi INSERT, UPDATE hoặc DELETE. Chỉ tạo các tổ hợp phục vụ truy vấn có thật.

## 9. Token, stopword và độ dài từ tối thiểu

FULLTEXT không lập chỉ mục mọi chuỗi ký tự theo từng byte. Parser phân tích văn bản thành các **token**. Một số token có thể bị bỏ qua:

- Token ngắn hơn giới hạn độ dài tối thiểu.
- Token dài hơn giới hạn tối đa.
- Stopword nằm trong danh sách từ dừng của cấu hình.
- Token không được parser nhận diện theo quy tắc tách từ đang dùng.

Giá trị mặc định thường gặp:

| Engine | Biến cấu hình | Mặc định |
|---|---|---:|
| InnoDB | `innodb_ft_min_token_size` | 3 |
| MyISAM | `ft_min_word_len` | 4 |

Ví dụ, với cấu hình mặc định, từ rất ngắn như `db` có thể không được lập chỉ mục bởi parser mặc định. Stopword như một số từ phổ biến cũng có thể bị loại bỏ nên không dùng được làm từ tìm kiếm hữu ích trong natural language mode.

Có thể kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
SHOW VARIABLES LIKE 'ft_stopword_file';
```

Các biến cấu hình token-size liên quan thường được đặt ở thời điểm khởi động server. Khi thay đổi ngưỡng hoặc stopword configuration, cần làm theo hướng dẫn phiên bản MySQL đang dùng và **rebuild FULLTEXT index** để các token đã lưu được tạo lại theo cấu hình mới. Chỉ đổi biến cấu hình không làm các index cũ tự phân tích lại.

Với InnoDB, có thể cấu hình stopword table ở cấp server hoặc cấp người dùng; với MyISAM có cơ chế cấu hình stopword riêng. Không giả định danh sách stopword hoặc hành vi giữa hai engine giống hệt nhau.

## 10. Charset và collation ảnh hưởng kết quả tìm kiếm

FULLTEXT phân tích văn bản theo character set và collation của cột. Các thuộc tính này ảnh hưởng cách so sánh chữ hoa/chữ thường, dấu và ký tự đa byte.

Ví dụ:

```sql
CREATE TABLE multilingual_articles (
    article_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(250)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci,
    body TEXT
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci,
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE = InnoDB;
```

Collation `utf8mb4_unicode_ci` có quy tắc so sánh Unicode không phân biệt chữ hoa/chữ thường và dấu. Collation khác có thể tạo ra hành vi so khớp khác. Khi xây dựng tìm kiếm đa ngôn ngữ, hãy thử với chữ có dấu, chữ hoa/thường, dấu câu và ký tự ngoài ASCII thực tế của ứng dụng.

Không nên coi đổi collation là thay đổi hiển thị đơn thuần. Nó có thể ảnh hưởng so sánh, uniqueness, sort order và cách FULLTEXT phân tích/so khớp nội dung. Kiểm tra dữ liệu hiện có và rebuild index khi cần theo quy trình thay đổi schema.

## 11. Parser mặc định và ngram parser

Parser mặc định thường tách token theo ranh giới từ và dấu phân cách mà parser nhận diện. Cách này phù hợp với nhiều ngôn ngữ dùng khoảng trắng để phân tách từ. Tuy nhiên, một số ngôn ngữ không có ranh giới từ bằng khoảng trắng rõ ràng, hoặc có quy tắc phân đoạn từ phức tạp.

MySQL cung cấp ngram full-text parser để chia văn bản thành các chuỗi ký tự liên tiếp có độ dài cố định (n-gram). Parser này hữu ích cho tìm kiếm CJK như tiếng Trung, Nhật và Hàn.

Tạo index dùng ngram:

```sql
CREATE TABLE cjk_documents (
    document_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    content TEXT NOT NULL,
    FULLTEXT KEY ft_content_ngram (content) WITH PARSER ngram
) ENGINE = InnoDB;
```

Độ dài n-gram được điều khiển bởi biến `ngram_token_size`; mặc định là 2. Cấu hình này ảnh hưởng cách văn bản được chia token, kích thước index và khả năng khớp từ khóa. Nếu thay đổi giá trị, cần xây dựng lại các FULLTEXT index sử dụng ngram parser.

Có thể kiểm tra biến:

```sql
SHOW VARIABLES LIKE 'ngram_token_size';
```

Ngram không phải bộ phân tích ngôn ngữ hoàn chỉnh. Với tiếng Việt, parser mặc định có thể coi các âm tiết cách nhau bằng dấu cách là các token riêng; ngram không tự hiểu mọi quy tắc từ ghép hay ngữ nghĩa tiếng Việt. Hãy kiểm thử chất lượng tìm kiếm trên tập văn bản thực tế trước khi chọn parser.

## 12. Các giới hạn cần biết trước khi thiết kế

Một số giới hạn ảnh hưởng trực tiếp đến thiết kế bảng:

- FULLTEXT chỉ hỗ trợ các kiểu CHAR, VARCHAR và TEXT; không áp dụng trực tiếp lên cột số, ngày giờ, BLOB hoặc JSON.
- Engine của bảng phải hỗ trợ FULLTEXT, thông thường là InnoDB hoặc MyISAM.
- Các cột trong một FULLTEXT index phải thuộc cùng một bảng.
- FULLTEXT index không hỗ trợ prefix length như B-tree index.
- FULLTEXT index không được hỗ trợ trên bảng đã partition.
- Danh sách cột trong MATCH phải khớp với một FULLTEXT index tương ứng.
- Stopword và token-size có thể khiến một từ không được đưa vào index.
- Parser và collation ảnh hưởng cách nội dung được phân tích và khớp.

Nếu ứng dụng cần tìm nội dung JSON, hãy xác định rõ trường văn bản nào cần tìm. Có thể trích xuất nội dung đó thành một cột văn bản được duy trì theo hợp đồng dữ liệu, sau đó lập FULLTEXT index trên cột phù hợp. Không thể đơn giản khai báo FULLTEXT trên cột JSON.

## 13. Xác minh FULLTEXT index đã được tạo

Xem index của bảng:

```sql
SHOW INDEX FROM articles;
```

Hoặc truy vấn metadata:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    INDEX_TYPE,
    COLUMN_NAME,
    SEQ_IN_INDEX
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Với FULLTEXT index, trường INDEX_TYPE hiển thị loại FULLTEXT. Các cột trong index ghép có cùng INDEX_NAME và thứ tự cột được biểu diễn bởi SEQ_IN_INDEX.

Kiểm tra kiểu cột và charset/collation:

```sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles'
ORDER BY ORDINAL_POSITION;
```

Kiểm tra cả định nghĩa bảng và metadata trước khi kết luận index có đúng tập cột, engine và kiểu dữ liệu mong muốn.

## 14. Kiểm tra kế hoạch thực thi

Sau khi tạo index, dùng EXPLAIN để xem optimizer có chọn FULLTEXT access hay không:

```sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
```

Khi FULLTEXT index được dùng, kế hoạch có thể hiển thị access type là `fulltext`. Hãy đọc cả cột key, possible_keys, rows và Extra; không kết luận chỉ từ việc câu truy vấn chạy thành công.

Nếu không thấy FULLTEXT index được chọn, kiểm tra theo thứ tự:

1. Engine bảng có phải InnoDB hoặc MyISAM không?
2. Cột index có thuộc CHAR, VARCHAR hoặc TEXT không?
3. Index có được tạo trên đúng bảng và đúng tập cột không?
4. Danh sách cột trong MATCH có khớp index không?
5. Từ khóa có bị loại bởi token-size hoặc stopword không?
6. Có dùng parser, charset hoặc collation khác với dự kiến không?
7. Truy vấn có đúng cú pháp và search mode không?

EXPLAIN mô tả kế hoạch optimizer dự kiến. Với workload thực tế, cần đo thời gian, số hàng trả về, tải CPU/I/O và hành vi khi dữ liệu tăng.

## 15. Lab: tạo và truy vấn FULLTEXT trên InnoDB

Lab dùng bảng riêng để thực hành điều kiện engine/cột, tạo index và truy vấn. Chạy trong schema thử nghiệm; nếu bảng đã tồn tại, kiểm tra trước khi tạo lại.

### 15.1. Tạo bảng

```sql
CREATE TABLE fts_lab_articles (
    article_id BIGINT NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_lab_title_body (title, body)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;
```

### 15.2. Thêm dữ liệu

```sql
INSERT INTO fts_lab_articles (title, body)
VALUES
    (
        'MySQL full text search',
        'MySQL supports FULLTEXT indexes for searching words in text columns.'
    ),
    (
        'InnoDB transaction basics',
        'InnoDB provides transactions, row locks, and crash recovery.'
    ),
    (
        'Database indexing',
        'B-tree indexes help equality and range queries; FULLTEXT helps text search.'
    );
```

### 15.3. Tìm kiếm tự nhiên

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql fulltext' IN NATURAL LANGUAGE MODE) AS score
FROM fts_lab_articles
WHERE MATCH(title, body)
      AGAINST ('mysql fulltext' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
```

### 15.4. Tìm kiếm Boolean

```sql
SELECT article_id, title
FROM fts_lab_articles
WHERE MATCH(title, body)
      AGAINST ('+mysql -transaction' IN BOOLEAN MODE);
```

### 15.5. Kiểm tra index và kế hoạch

```sql
SHOW INDEX FROM fts_lab_articles;

EXPLAIN
SELECT article_id, title
FROM fts_lab_articles
WHERE MATCH(title, body)
      AGAINST ('mysql fulltext' IN NATURAL LANGUAGE MODE);
```

Đối chiếu index `ft_lab_title_body`, kiểu cột, engine và access type trong EXPLAIN. Kết quả cụ thể còn phụ thuộc phiên bản server, cấu hình token và nội dung dữ liệu.

## 16. Chi phí duy trì và quản lý FULLTEXT index

FULLTEXT index giúp tăng tốc truy vấn tìm kiếm nhưng cần dung lượng và chi phí duy trì:

- INSERT phải phân tích nội dung và thêm token vào index.
- UPDATE các cột được lập chỉ mục có thể làm thay đổi nhiều token.
- DELETE phải loại bỏ các mục chỉ mục liên quan.
- Tạo hoặc rebuild index trên bảng lớn tiêu tốn CPU, I/O và dung lượng tạm.
- Nhiều FULLTEXT index với các tổ hợp cột khác nhau làm tăng chi phí ghi.

Chỉ lập chỉ mục các cột thực sự được dùng trong truy vấn. Nếu không còn cần index, có thể xóa:

```sql
ALTER TABLE articles
DROP INDEX ft_articles_title_body;
```

Trước khi xóa, kiểm tra truy vấn ứng dụng có phụ thuộc vào index hay không. Thay đổi index trên bảng lớn cần được lên lịch và theo dõi như một thay đổi schema.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tạo được FULLTEXT index | Engine không hỗ trợ | Dùng InnoDB hoặc MyISAM sau khi đánh giá migration. |
| Báo lỗi kiểu cột không hợp lệ | Cột là số, ngày giờ, BLOB hoặc JSON | Dùng CHAR, VARCHAR hoặc TEXT phù hợp. |
| MATCH không dùng được index | Danh sách cột không khớp FULLTEXT index | Tạo index đúng tập cột hoặc sửa MATCH. |
| Tìm từ rất ngắn không ra kết quả | Token ngắn hơn min token size | Kiểm tra cấu hình engine và cân nhắc ngưỡng phù hợp. |
| Tìm từ phổ biến không ra kết quả | Stopword hoặc ngưỡng 50% của MyISAM | Kiểm tra stopword và khác biệt engine. |
| Tìm kiếm tiếng CJK kém | Parser mặc định không phân đoạn phù hợp | Đánh giá ngram parser và ngram_token_size. |
| Từ có dấu cho kết quả bất ngờ | Charset/collation không như mong muốn | Kiểm tra charset/collation và dữ liệu thực tế. |
| Tạo index mất nhiều thời gian | Bảng lớn, văn bản dài hoặc I/O hạn chế | Đo tải, dung lượng và chọn cửa sổ triển khai. |
| LIKE nhanh/chậm khác dự kiến | FULLTEXT và LIKE có ngữ nghĩa, kế hoạch khác nhau | Chọn công cụ đúng loại tìm kiếm và đo trên dữ liệu thật. |
| Index có nhưng kết quả thiếu | Tokenization, stopword, parser hoặc mode | Kiểm tra cấu hình và truy vấn theo từng bước. |

## 18. Quy trình thiết kế và kiểm tra

Khi bổ sung FULLTEXT vào một bảng đang hoạt động, thực hiện theo thứ tự:

1. Xác định chính xác các truy vấn tìm kiếm và cột văn bản cần tìm.
2. Kiểm tra engine của bảng; ưu tiên InnoDB cho ứng dụng cần transaction.
3. Kiểm tra kiểu cột là CHAR, VARCHAR hoặc TEXT.
4. Xác định có cần index một cột hay tổ hợp nhiều cột.
5. Kiểm tra charset/collation và parser phù hợp với ngôn ngữ dữ liệu.
6. Kiểm tra min/max token size và stopword configuration.
7. Tạo FULLTEXT index trong môi trường thử nghiệm.
8. Thử natural language, boolean và query expansion nếu có nhu cầu.
9. Kiểm tra metadata bằng SHOW INDEX và INFORMATION_SCHEMA.STATISTICS.
10. Dùng EXPLAIN để xác nhận kế hoạch truy vấn.
11. Đo chất lượng kết quả, độ trễ truy vấn và chi phí ghi khi INSERT/UPDATE/DELETE.
12. Lên kế hoạch tạo, rebuild hoặc xóa index trên production.

## 19. Bài tập thực hành

### Bài tập 1: Kiểm tra engine

Tạo bảng văn bản trên InnoDB và thử tạo FULLTEXT index. Kiểm tra engine bằng SHOW TABLE STATUS và INFORMATION_SCHEMA.TABLES.

**Yêu cầu:** giải thích vì sao engine là một điều kiện trước khi tạo FULLTEXT.

### Bài tập 2: Kiểm tra kiểu cột

Tạo một bảng có title VARCHAR, body TEXT, amount DECIMAL và payload JSON.

**Yêu cầu:** xác định cột nào có thể đưa trực tiếp vào FULLTEXT index và giải thích vì sao các cột còn lại không phù hợp.

### Bài tập 3: Index một cột và nhiều cột

Tạo FULLTEXT index riêng cho title và index kết hợp title/body.

**Yêu cầu:** viết hai truy vấn MATCH tương ứng; giải thích vì sao danh sách cột phải khớp index.

### Bài tập 4: Natural language và Boolean

Tìm tài liệu có từ mysql, sau đó yêu cầu có mysql và loại trừ oracle bằng Boolean mode.

**Yêu cầu:** so sánh kết quả và relevance.

### Bài tập 5: Token-size và stopword

Kiểm tra cấu hình min token size và thử tìm một từ ngắn cùng một từ phổ biến.

**Yêu cầu:** giải thích tại sao kết quả có thể bị bỏ qua; không thay đổi cấu hình production trong bài tập.

### Bài tập 6: Parser ngram

Tạo FULLTEXT index dùng ngram parser trên một cột văn bản thử nghiệm.

**Yêu cầu:** kiểm tra ngram_token_size và so sánh cách tìm kiếm với parser mặc định trên dữ liệu CJK.

### Bài tập 7: EXPLAIN

Chạy EXPLAIN cho truy vấn MATCH ... AGAINST.

**Yêu cầu:** xác định access type, key và giải thích liệu FULLTEXT index có được dùng hay không.

## 20. Checklist review FULLTEXT

- [ ] Đã xác nhận storage engine hỗ trợ FULLTEXT.
- [ ] Đã xác nhận các cột index là CHAR, VARCHAR hoặc TEXT.
- [ ] Các cột trong index thuộc cùng một bảng.
- [ ] Không dùng prefix length cho FULLTEXT index.
- [ ] Danh sách cột MATCH khớp với FULLTEXT index.
- [ ] Đã chọn một cột hay nhiều cột theo truy vấn thực tế.
- [ ] Đã kiểm tra charset/collation.
- [ ] Đã kiểm tra parser, stopword và min/max token size.
- [ ] Đã cân nhắc ngram cho dữ liệu CJK.
- [ ] Đã hiểu khác biệt ngưỡng 50% của MyISAM natural language mode.
- [ ] Đã kiểm tra index qua SHOW INDEX hoặc INFORMATION_SCHEMA.STATISTICS.
- [ ] Đã kiểm tra kế hoạch bằng EXPLAIN.
- [ ] Đã đánh giá chi phí INSERT/UPDATE/DELETE và dung lượng index.
- [ ] Đã kiểm thử chất lượng tìm kiếm trên dữ liệu đại diện.

## 21. Ghi nhớ

FULLTEXT index dùng để tìm kiếm token trong nội dung văn bản và được hỗ trợ bởi InnoDB và MyISAM. Các cột được lập chỉ mục phải thuộc kiểu CHAR, VARCHAR hoặc TEXT; index nhiều cột chỉ kết hợp các cột của cùng một bảng. Danh sách cột trong MATCH phải tương ứng với một FULLTEXT index. FULLTEXT không dùng prefix length và không hỗ trợ bảng partition.

Truy vấn dùng MATCH ... AGAINST với natural language, boolean hoặc query expansion. Kết quả phụ thuộc parser, charset/collation, stopword và giới hạn token-size. InnoDB và MyISAM có khác biệt cấu hình, trong đó MyISAM natural language mode có ngưỡng 50% còn InnoDB không áp dụng ngưỡng đó. Dùng SHOW INDEX, INFORMATION_SCHEMA và EXPLAIN để xác minh cấu trúc và kế hoạch; đo cả chi phí tìm kiếm lẫn chi phí duy trì index trước khi triển khai.

