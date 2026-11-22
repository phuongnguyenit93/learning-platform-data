# Parser mặc định, ngram parser và điều kiện sử dụng

MySQL Full-Text Search không so khớp văn bản theo từng ký tự như LIKE '%text%'. Khi tạo FULLTEXT index, MySQL dùng một parser để tách nội dung thành token, loại bỏ token không được lập chỉ mục theo quy tắc cấu hình, rồi lưu các token để phục vụ MATCH() AGAINST(). Parser vì vậy quyết định văn bản được chia thành những đơn vị nào và ảnh hưởng trực tiếp đến kết quả tìm kiếm.

MySQL có parser mặc định dựa trên từ và ngram parser dựa trên chuỗi ký tự liên tiếp. Parser mặc định phù hợp với văn bản mà từ được phân tách rõ bằng khoảng trắng hoặc dấu phân cách. Ngram parser thường phù hợp hơn với tiếng Trung, tiếng Nhật, tiếng Hàn và các văn bản không có ranh giới từ rõ ràng. Hai parser có cách tạo token khác nhau nên cùng một câu truy vấn có thể trả về tập kết quả khác nhau.

Trong module **DATABASE_MYSQL**, lựa chọn parser là một quyết định thiết kế index. Bài học này trình bày cách parser mặc định và ngram parser tạo token, các giới hạn về độ dài token và stopword, cách tạo FULLTEXT index, cách truy vấn và tiêu chí lựa chọn theo ngôn ngữ, dữ liệu và yêu cầu tìm kiếm.

## 1. Full-Text Search và vai trò của parser

Full-Text Search lập chỉ mục nội dung văn bản để tìm theo từ hoặc token. Các cột được lập chỉ mục phải thuộc kiểu CHAR, VARCHAR hoặc TEXT. InnoDB và MyISAM hỗ trợ FULLTEXT index, nhưng một số thiết lập token và stopword khác nhau theo storage engine.

Ví dụ bảng bài viết:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB;
```

Tạo FULLTEXT index trên body:

```sql
CREATE FULLTEXT INDEX ft_articles_body
ON articles (body);
```

Truy vấn:

```sql
SELECT
    article_id,
    title,
    MATCH(body) AGAINST (
        'database index'
        IN NATURAL LANGUAGE MODE
    ) AS relevance
FROM articles
WHERE MATCH(body) AGAINST (
    'database index'
    IN NATURAL LANGUAGE MODE
)
ORDER BY relevance DESC;
```

Trong quá trình tạo index, parser đọc nội dung body và tạo token. Khi chạy MATCH() AGAINST(), MySQL dùng parser gắn với FULLTEXT index để xử lý chuỗi tìm kiếm theo cách tương ứng.

Parser không chỉ ảnh hưởng tốc độ. Nó quyết định khái niệm "từ" của hệ thống tìm kiếm. Nếu parser không tạo token tương ứng với cách người dùng nhập truy vấn, FULLTEXT index có thể không tìm thấy nội dung mong đợi dù chuỗi đó vẫn tồn tại trong cột.

## 2. Parser mặc định: tách văn bản thành từ

Parser mặc định của MySQL nhận diện các từ dựa trên ranh giới từ, thường được phân tách bằng khoảng trắng và dấu câu. Các token được tạo ra sẽ chịu thêm quy tắc về độ dài tối thiểu, độ dài tối đa và stopword.

Ví dụ văn bản:

```text
MySQL provides reliable database indexing.
A database index can improve query performance.
```

Parser mặc định có thể tạo các token như:

```text
mysql
provides
reliable
database
indexing
a
can
improve
query
performance
```

Danh sách trên chỉ minh họa ý tưởng. Token thực tế được giữ hay loại bỏ còn phụ thuộc stopword, min/max token size, charset và cấu hình server.

### 2.1. Ranh giới từ và dấu phân cách

Parser mặc định thích hợp khi dữ liệu có ranh giới từ tương đối rõ. Ví dụ tiếng Anh và nhiều ngôn ngữ viết bằng alphabet Latin dùng khoảng trắng để phân tách từ.

Văn bản:

```text
relational database
database-engine
query, index, transaction
```

Các dấu phân cách có thể làm parser chia văn bản thành các token riêng. Vì vậy, tìm kiếm một cụm từ, từ ghép có dấu gạch nối hoặc một phần của từ cần được thử nghiệm bằng dữ liệu thực tế.

FULLTEXT parser mặc định không phải tokenizer ngôn ngữ tự nhiên hoàn chỉnh. Nó không hiểu ngữ nghĩa, không tự suy ra từ đồng nghĩa và không bảo đảm nhận diện mọi biến thể hình thái của một từ. Nếu yêu cầu tìm kiếm cần stemming, synonym, fuzzy matching hoặc phân đoạn ngôn ngữ chuyên biệt, cần xử lý bổ sung ở tầng ứng dụng hoặc dùng hệ thống tìm kiếm chuyên dụng.

### 2.2. Giới hạn độ dài token

Token quá ngắn hoặc quá dài có thể bị bỏ qua. Giá trị mặc định phụ thuộc storage engine:

| Storage engine | Độ dài tối thiểu mặc định | Độ dài tối đa mặc định | Biến cấu hình |
|---|---:|---:|---|
| InnoDB, parser mặc định | 3 ký tự | 84 ký tự | innodb_ft_min_token_size, innodb_ft_max_token_size |
| MyISAM, parser mặc định | 4 ký tự | 84 ký tự | ft_min_word_len, ft_max_word_len |

Ví dụ với InnoDB mặc định, token như id có thể ngắn hơn ngưỡng tối thiểu và không được lập chỉ mục. Với MyISAM, ngưỡng mặc định còn cao hơn một ký tự.

Điều này ảnh hưởng đến mã định danh, từ viết tắt và thuật ngữ kỹ thuật. Các token như C, Go, UI, SQL hoặc NoSQL có thể không được xử lý như mong muốn tùy độ dài và cách viết thực tế. Không nên mặc định rằng mọi từ nhìn thấy trong cột đều có thể tìm bằng FULLTEXT.

### 2.3. Stopword

Stopword là các từ bị loại khỏi FULLTEXT index vì thường xuất hiện quá nhiều và ít giúp phân biệt kết quả. Ví dụ tiếng Anh thường có các từ như the, a, is, of.

MySQL cung cấp danh sách stopword mặc định; InnoDB và MyISAM có cơ chế cấu hình stopword riêng. Với InnoDB có thể kiểm soát việc bật/tắt stopword và sử dụng bảng stopword tùy chỉnh. MyISAM có biến cấu hình chỉ tới stopword file.

Ví dụ văn bản:

```text
the database is reliable
database indexing improves performance
```

Nếu the hoặc is nằm trong stopword list, chúng không trở thành token tìm kiếm. Tìm kiếm các từ này riêng lẻ thường không cho kết quả như tìm một thuật ngữ thông thường.

Stopword hữu ích để giảm nhiễu và kích thước index, nhưng có thể gây bất ngờ nếu từ nghiệp vụ quan trọng trùng với stopword. Ví dụ ứng dụng tìm kiếm mã sản phẩm, tên viết tắt hoặc cụm từ ngắn cần đánh giá danh sách stopword trước khi triển khai.

### 2.4. Ảnh hưởng của charset và collation

Parser làm việc trên văn bản của cột, vì vậy charset và collation là một phần của thiết kế tìm kiếm. Collation ảnh hưởng cách so sánh văn bản, ví dụ phân biệt hay không phân biệt chữ hoa/chữ thường và dấu.

Với dữ liệu tiếng Việt, cần thử nghiệm các trường hợp có dấu và không dấu, chữ hoa và chữ thường, cũng như collation đang dùng. Không nên cho rằng parser mặc định tự động chuẩn hóa mọi biến thể tiếng Việt thành cùng một token.

## 3. Ngram parser: chia văn bản thành các chuỗi ký tự liên tiếp

Ngram parser chia văn bản thành các nhóm ký tự có độ dài cố định n, gọi là n-gram. Thay vì phụ thuộc vào dấu cách để xác định ranh giới từ, parser tạo các token từ những chuỗi ký tự liên tiếp.

Ví dụ với ngram_token_size = 2, chuỗi:

```text
database
```

được chia thành các bigram minh họa:

```text
da
at
ta
ab
ba
as
se
```

Mỗi token gồm hai ký tự liền nhau. Với ngram_token_size = 3, chuỗi được chia thành trigram:

```text
dat
ata
tab
aba
bas
ase
```

Ngram parser đặc biệt hữu ích cho ngôn ngữ mà từ không được phân tách bằng khoảng trắng hoặc ranh giới từ không thể suy ra đơn giản từ dấu cách, chẳng hạn tiếng Trung, tiếng Nhật và tiếng Hàn.

### 3.1. ngram_token_size

Biến ngram_token_size xác định số ký tự trong mỗi token:

| Thiết lập | Kết quả với chuỗi "abcdef" |
|---|---|
| 1 | a, b, c, d, e, f |
| 2 | ab, bc, cd, de, ef |
| 3 | abc, bcd, cde, def |
| 4 | abcd, bcde, cdef |

Trong MySQL, ngram_token_size mặc định là 2 và nhận giá trị từ 1 đến 10. Đây là biến cấu hình cấp server chỉ thiết lập khi khởi động, không thể thay đổi tùy ý cho từng index hoặc sửa động trong phiên làm việc. Cần chọn giá trị phù hợp với ngôn ngữ và độ dài truy vấn phổ biến.

- n nhỏ tạo nhiều token hơn, có thể tăng kích thước index và số kết quả khớp.
- n lớn tạo ít token hơn, thường làm truy vấn ngắn khó khớp và có thể giảm khả năng tìm chuỗi ngắn.
- n quá nhỏ dễ tạo token phổ biến, làm tăng nhiễu.
- n quá lớn có thể bỏ lỡ truy vấn ngắn hơn độ dài token.

Nếu search term ngắn hơn ngram_token_size, truy vấn có thể không tạo được token phù hợp và không trả kết quả mong muốn. Hãy kiểm tra các từ khóa ngắn nhất mà người dùng thực tế sẽ nhập.

### 3.2. Ví dụ với văn bản tiếng Trung

Giả sử nội dung có chuỗi tiếng Trung:

```text
数据库索引
```

Với ngram_token_size = 2, các bigram minh họa là:

```text
数据
据库
库索
索引
```

Khi người dùng tìm một chuỗi con đủ độ dài, parser có thể tạo các bigram tương ứng để so khớp trong FULLTEXT index. Cơ chế này cho phép tìm kiếm mà không cần biết chính xác ranh giới từ.

Ví dụ khác với tiếng Nhật hoặc tiếng Hàn cũng có thể tạo chuỗi n-gram theo quy tắc tương tự. Tuy nhiên, việc tạo token theo ký tự không có nghĩa là MySQL hiểu nghĩa của từ hoặc cụm từ. Kết quả phụ thuộc ngram_token_size, stopword và cách truy vấn được chuyển thành token.

### 3.3. Khoảng trắng và dấu câu

Ngram parser xử lý chuỗi theo n-gram và loại khoảng trắng khỏi token. Điều này khác parser mặc định, vốn dựa vào ranh giới từ. Dấu câu và ký tự đặc biệt có thể làm thay đổi chuỗi token thực tế, vì vậy cần thử nghiệm với dữ liệu có dấu gạch nối, dấu chấm, mã định danh, URL và ký tự đa byte.

Đặc biệt, không nên tự tính số token bằng cách đếm byte UTF-8. ngram_token_size nói về ký tự theo parser, không phải số byte của chuỗi. Một ký tự Unicode có thể chiếm nhiều byte khi lưu ở UTF-8.

### 3.4. Stopword trong ngram parser

Ngram parser vẫn có thể áp dụng stopword filtering. Stopword có thể khiến một số n-gram bị loại khỏi index, vì vậy không phải mọi bigram/trigram được tạo ra đều chắc chắn được lưu.

Khi tìm kiếm tiếng CJK hoặc chuỗi ký tự ngắn, hãy kiểm tra tương tác giữa ngram_token_size và stopword list. Một cấu hình stopword phù hợp với tìm kiếm theo từ trong tiếng Anh có thể không phù hợp với n-gram, vì các chuỗi ngắn có thể xuất hiện bên trong nhiều từ khác nhau.

Không nên tắt stopword một cách mặc định. Hãy đánh giá tỷ lệ token phổ biến, kích thước index và độ chính xác kết quả trên corpus đại diện trước khi thay đổi.

## 4. Tạo FULLTEXT index với parser mặc định

Nếu không chỉ định parser, MySQL sử dụng parser mặc định. Ví dụ:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_documents_title_content (title, content)
) ENGINE = InnoDB;
```

Index trên title và content là một FULLTEXT index kết hợp. Truy vấn MATCH phải chỉ định cùng tập cột:

```sql
SELECT
    document_id,
    MATCH(title, content) AGAINST (
        'mysql full text'
        IN NATURAL LANGUAGE MODE
    ) AS score
FROM documents
WHERE MATCH(title, content) AGAINST (
    'mysql full text'
    IN NATURAL LANGUAGE MODE
)
ORDER BY score DESC;
```

Nếu muốn tìm riêng title hoặc content với access path độc lập, cân nhắc tạo FULLTEXT index riêng cho từng cột. Hãy thiết kế index theo đúng mẫu MATCH được ứng dụng sử dụng.

### 4.1. Tạo index sau khi bảng đã tồn tại

```sql
ALTER TABLE documents
ADD FULLTEXT INDEX ft_documents_content (content);
```

Khi thêm FULLTEXT index, MySQL phân tích dữ liệu hiện có và tạo token theo parser/cấu hình tại thời điểm xây dựng index. Với bảng lớn, thao tác này có thể tiêu tốn CPU, I/O, dung lượng tạm và thời gian migration. Cần dự trù thời gian và tải hệ thống khi triển khai.

### 4.2. MATCH() AGAINST() và các search mode

Natural language mode là chế độ mặc định nếu không chỉ định mode:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('transaction isolation');
```

Boolean mode cho phép biểu diễn điều kiện bắt buộc, loại trừ hoặc tiền tố:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('+transaction -replication' IN BOOLEAN MODE);
```

Query expansion có thể mở rộng tìm kiếm dựa trên những tài liệu phù hợp ban đầu:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('database' WITH QUERY EXPANSION);
```

Các chế độ này dùng cùng FULLTEXT index nhưng cách diễn giải truy vấn khác nhau. Parser vẫn quyết định cách chuỗi tìm kiếm được tách thành token. Query expansion có thể tăng recall nhưng cũng làm kết quả rộng và nhiễu hơn; chỉ bật khi phù hợp với trải nghiệm tìm kiếm.

## 5. Tạo FULLTEXT index với ngram parser

Để sử dụng ngram parser, chỉ định WITH PARSER ngram khi tạo FULLTEXT index:

```sql
CREATE TABLE cjk_articles (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_cjk_content (content) WITH PARSER ngram
) ENGINE = InnoDB;
```

Hoặc thêm index vào bảng hiện có:

```sql
ALTER TABLE cjk_articles
ADD FULLTEXT INDEX ft_cjk_title (title) WITH PARSER ngram;
```

Ngram parser là parser được MySQL cung cấp sẵn. Không cần tự viết tokenizer riêng để dùng cú pháp WITH PARSER ngram, nhưng cần bảo đảm server có hỗ trợ parser và phiên bản triển khai phù hợp.

Truy vấn dùng MATCH() AGAINST() như FULLTEXT index thông thường:

```sql
SELECT
    article_id,
    MATCH(content) AGAINST (
        '数据库'
        IN NATURAL LANGUAGE MODE
    ) AS relevance
FROM cjk_articles
WHERE MATCH(content) AGAINST (
    '数据库'
    IN NATURAL LANGUAGE MODE
)
ORDER BY relevance DESC;
```

MySQL dùng ngram parser được gắn với index để phân tích chuỗi tìm kiếm. Không cần viết hàm tách bigram thủ công trong câu MATCH.

### 5.1. Kiểm tra ngram_token_size

Xem cấu hình hiện tại:

```sql
SHOW VARIABLES LIKE 'ngram_token_size';
```

Nếu dùng giá trị mặc định 2, ngram parser tạo bigram. Với dữ liệu và truy vấn thực tế, hãy thử một tập từ khóa ngắn, dài, có khoảng trắng và dấu câu để xác nhận cách token hóa đáp ứng nhu cầu.

ngram_token_size được cấu hình ở cấp server khi khởi động. Khi thay đổi, cần restart instance với giá trị mới, triển khai cấu hình nhất quán trên các node liên quan và xây dựng lại FULLTEXT index để token trong index khớp với quy tắc mới. Không nên thay đổi tham số trên một server rồi tiếp tục dùng index cũ mà không kiểm tra.

### 5.2. Ví dụ so sánh parser mặc định và ngram

Giả sử lưu cùng nội dung:

```text
数据库索引优化
```

Parser mặc định dựa trên ranh giới từ và có thể không tạo được token hữu ích nếu không có dấu phân tách phù hợp. Ngram parser với ngram_token_size = 2 có thể tạo:

```text
数据
据库
库索
索引
引优
优化
```

Nếu người dùng tìm chuỗi con 索引, parser ngram có thể tạo bigram tương ứng. Đây là lý do ngram phù hợp hơn cho loại văn bản này.

Ngram không phải luôn tốt hơn parser mặc định. Với văn bản tiếng Anh được phân tách rõ, bigram tạo nhiều token chồng lấn như da, at, ta, làm index lớn hơn và có thể tăng kết quả không liên quan. Hãy chọn parser dựa trên ngôn ngữ và kiểu truy vấn, không dựa trên việc parser nào có nhiều token hơn.

## 6. Cách parser ảnh hưởng kết quả tìm kiếm

Cùng một cột văn bản nhưng hai parser có thể tạo index khác nhau:

| Đặc điểm | Parser mặc định | Ngram parser |
|---|---|---|
| Đơn vị token | Từ | Chuỗi n ký tự liên tiếp |
| Ranh giới chính | Khoảng trắng, dấu phân cách | Cửa sổ n ký tự |
| Cấu hình độ dài | Min/max token size theo engine | ngram_token_size |
| Ngôn ngữ phù hợp | Văn bản có ranh giới từ rõ | CJK và văn bản không có ranh giới từ rõ |
| Từ khóa ngắn | Có thể bị loại do min token size | Có thể không đủ n ký tự |
| Kích thước index | Phụ thuộc số từ và stopword | Có thể tăng do nhiều n-gram chồng lấn |
| Tìm chuỗi con | Không phải mục tiêu chính | Có thể hỗ trợ ở mức n-gram |

### 6.1. Token hóa và tìm kiếm cụm từ

Trong natural language mode, MySQL tìm theo token và tính relevance. Trong boolean mode, có thể dùng toán tử để yêu cầu hoặc loại trừ token. Với phrase search, đặt cụm từ trong dấu nháy kép trong boolean mode:

```sql
SELECT document_id
FROM documents
WHERE MATCH(content)
AGAINST ('"database index"' IN BOOLEAN MODE);
```

Với ngram parser, cụm tìm kiếm cũng được chuyển thành n-gram theo cấu hình parser. Do đó, thay đổi ngram_token_size có thể làm thay đổi cách phrase được chia và cách index khớp cụm.

Không diễn giải phrase search như kiểm tra chuỗi byte nguyên văn trong cột. FULLTEXT vẫn áp dụng semantics token của parser và search mode.

### 6.2. Từ khóa quá ngắn

Với parser mặc định, token ngắn hơn ngưỡng tối thiểu có thể không tồn tại trong index. Với ngram parser, chuỗi tìm kiếm ngắn hơn ngram_token_size không tạo đủ token để khớp.

Ví dụ nếu ngram_token_size = 2, một truy vấn chỉ có một ký tự có thể không trả kết quả. Nếu sản phẩm cần tìm theo mã ngắn, ký tự đơn hoặc prefix, hãy cân nhắc B-tree index, LIKE theo prefix, cột mã riêng hoặc một cơ chế tìm kiếm khác.

### 6.3. Tìm kiếm không đồng nghĩa tìm chuỗi con tùy ý

FULLTEXT được thiết kế để tìm token, không phải thay thế cho mọi dạng substring search. Parser ngram có thể làm cho tìm kiếm chuỗi con hiệu quả hơn ở mức n-gram, nhưng vẫn phụ thuộc độ dài n, stopword và semantics của MATCH.

Nếu yêu cầu là tìm chuỗi bất kỳ trong cột, kể cả một phần rất ngắn, LIKE '%abc%' có semantics khác. Truy vấn LIKE với wildcard đầu thường không dùng B-tree index thông thường. Có thể cần thiết kế index chuyên biệt, generated search key hoặc hệ thống tìm kiếm riêng tùy quy mô.

## 7. Chọn parser theo ngôn ngữ và dữ liệu

### 7.1. Khi nên dùng parser mặc định

Chọn parser mặc định khi:

- Văn bản có ranh giới từ rõ bằng khoảng trắng hoặc dấu phân cách.
- Người dùng tìm theo từ, cụm từ và relevance.
- Min/max token size phù hợp với độ dài thuật ngữ.
- Stopword list có thể chấp nhận hoặc tùy chỉnh.
- Muốn index theo đơn vị từ thay vì mọi chuỗi ký tự liên tiếp.

Ví dụ: bài viết kỹ thuật tiếng Anh, mô tả sản phẩm bằng tiếng Anh, tài liệu có khoảng trắng phân tách từ.

### 7.2. Khi nên dùng ngram parser

Cân nhắc ngram parser khi:

- Văn bản dùng hệ chữ không có khoảng trắng phân tách từ như tiếng Trung, tiếng Nhật hoặc tiếng Hàn.
- Người dùng thường tìm một chuỗi con trong văn bản.
- Cần tìm nội dung mà parser mặc định không tách thành token hữu ích.
- Có thể kiểm soát và thử nghiệm ngram_token_size.
- Chấp nhận chi phí index và kết quả rộng hơn do token chồng lấn.

Ngram parser không thực hiện phân tích ngôn ngữ, không tự xác định từ ghép và không biết ý nghĩa của chuỗi ký tự. Nó chỉ tạo các n-gram theo kích thước cấu hình.

### 7.3. Lưu ý riêng với tiếng Việt

Tiếng Việt sử dụng khoảng trắng giữa các âm tiết, nhưng một từ có thể gồm nhiều âm tiết. Parser mặc định có thể lập chỉ mục từng âm tiết như token riêng. Điều này đôi khi làm tìm kiếm theo cụm từ hoặc từ ghép không khớp với mong muốn nghiệp vụ.

Ngram parser có thể hữu ích nếu sản phẩm cần tìm theo chuỗi ký tự con, nhưng nó không phải bộ phân đoạn từ tiếng Việt. Chẳng hạn, n-gram có thể tạo nhiều token từ các ký tự liền nhau mà không biết ranh giới từ ghép hoặc ý nghĩa của cụm từ. Vì vậy, không nên chuyển toàn bộ tìm kiếm tiếng Việt sang ngram chỉ vì tiếng Việt có từ nhiều âm tiết.

Với tìm kiếm tiếng Việt, hãy xác định trước yêu cầu:

- Tìm từng âm tiết hay cụm từ nhiều âm tiết?
- Có cần tìm không dấu khi dữ liệu có dấu?
- Có cần khớp từ ghép, biến thể hoặc từ đồng nghĩa?
- Người dùng thường nhập từ đầy đủ hay một đoạn ký tự?
- Có cần xếp hạng relevance theo nội dung và tiêu đề?

Có thể dùng parser mặc định kết hợp phrase search và collation phù hợp; nếu cần phân đoạn từ, có thể chuẩn hóa/tokenize ở tầng ứng dụng trước khi ghi vào cột search riêng. Nếu cần search không dấu, synonym hoặc ranking phức tạp, hãy thiết kế thêm search field hoặc dùng search engine chuyên dụng. Luôn kiểm thử bằng tập truy vấn tiếng Việt thực tế.

### 7.4. Ma trận quyết định

| Dữ liệu và yêu cầu | Lựa chọn ban đầu | Cần kiểm tra |
|---|---|---|
| Tiếng Anh, tìm theo từ | Parser mặc định | Stopword, min/max token |
| Tiếng Trung, Nhật, Hàn | Ngram parser | ngram_token_size, stopword |
| Mã ngắn và ký hiệu | Không mặc định FULLTEXT | Độ dài token, B-tree hoặc cột riêng |
| Tiếng Việt, tìm theo âm tiết | Parser mặc định có thể phù hợp | Cụm từ, dấu, collation |
| Tiếng Việt, tìm substring | Thử ngram hoặc giải pháp khác | Kết quả nhiễu, độ dài n |
| Tìm synonym, stemming, fuzzy | Parser mặc định/ngram chưa đủ | Xử lý ứng dụng hoặc search engine |

## 8. Cấu hình token size và stopword

Cấu hình token size ảnh hưởng trực tiếp nội dung FULLTEXT index. Các biến thường gặp:

| Biến | Phạm vi | Giá trị mặc định thường gặp |
|---|---|---:|
| innodb_ft_min_token_size | InnoDB, parser mặc định | 3 |
| innodb_ft_max_token_size | InnoDB, parser mặc định | 84 |
| ft_min_word_len | MyISAM, parser mặc định | 4 |
| ft_max_word_len | MyISAM, parser mặc định | 84 |
| ngram_token_size | ngram parser | 2 |

Các giá trị này có thể phụ thuộc phiên bản và cấu hình server. Hãy kiểm tra trực tiếp trên instance:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
SHOW VARIABLES LIKE 'ngram_token_size';
```

### 8.1. Thay đổi token size

Khi thay đổi min/max token size hoặc ngram_token_size, cần bảo đảm FULLTEXT index được xây dựng lại theo cấu hình mới. Những token đã bị bỏ khi index cũ được tạo sẽ không tự xuất hiện chỉ vì biến cấu hình đã thay đổi.

Quy trình triển khai tổng quát:

1. Thu thập các từ khóa người dùng thường tìm và độ dài của chúng.
2. Xác định storage engine và parser của từng FULLTEXT index.
3. Chọn token size phù hợp với ngôn ngữ và corpus.
4. Đặt cấu hình server theo yêu cầu phiên bản; restart nếu biến là startup-only.
5. Drop/recreate hoặc rebuild các FULLTEXT index liên quan.
6. Chạy lại bộ truy vấn kiểm thử và so sánh kết quả.
7. Đo dung lượng index, thời gian ghi và độ trễ tìm kiếm.

Không thay đổi biến trên production mà chưa ước lượng thời gian rebuild và tác động đến tải máy chủ. Với hệ thống replication, cần có kế hoạch cấu hình nhất quán trên các node.

### 8.2. Tùy chỉnh stopword

Stopword list mặc định có thể không phù hợp với tên miền nghiệp vụ. Ví dụ từ phổ biến trong ngôn ngữ tự nhiên có thể là mã hoặc thuật ngữ quan trọng trong hệ thống.

Trước khi tùy chỉnh:

- Liệt kê các từ thường bị loại nhưng nghiệp vụ cần tìm.
- Xác định engine đang dùng.
- Chọn cơ chế stopword tương ứng với engine.
- Kiểm tra biến enable/disable stopword và bảng/file stopword tùy chỉnh theo phiên bản.
- Rebuild FULLTEXT index sau khi thay đổi danh sách.
- Đo ảnh hưởng tới kích thước index và độ nhiễu của kết quả.

InnoDB có các biến như innodb_ft_enable_stopword và cơ chế server/user stopword table. MyISAM dùng ft_stopword_file. Không áp dụng nhầm cấu hình của engine này sang engine kia.

## 9. Kết hợp nhiều cột và nhiều parser

Một FULLTEXT index có thể lập chỉ mục nhiều cột văn bản:

```sql
CREATE FULLTEXT INDEX ft_articles_title_body
ON articles (title, body);
```

Truy vấn cần MATCH đúng danh sách cột đã được lập chỉ mục:

```sql
SELECT article_id
FROM articles
WHERE MATCH(title, body)
AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
```

Nếu muốn index title theo parser mặc định và content theo ngram, có thể tạo các FULLTEXT index riêng với parser tương ứng:

```sql
CREATE FULLTEXT INDEX ft_articles_title
ON articles (title);

CREATE FULLTEXT INDEX ft_articles_content_ngram
ON articles (content) WITH PARSER ngram;
```

Mỗi MATCH expression cần dùng đúng tập cột tương ứng với FULLTEXT index mà optimizer có thể sử dụng. Việc có nhiều index làm tăng chi phí lưu trữ và cập nhật; chỉ tạo khi có mẫu truy vấn thực sự cần.

## 10. Kiểm tra parser và FULLTEXT index

Xem định nghĩa bảng:

```sql
SHOW CREATE TABLE articles;
```

Xem index:

```sql
SHOW INDEX FROM articles;
```

Xem cấu hình parser:

```sql
SHOW VARIABLES LIKE 'ngram_token_size';
SHOW VARIABLES LIKE 'innodb_ft%';
SHOW VARIABLES LIKE 'ft_%';
```

Có thể xem plugin đang có:

```sql
SHOW PLUGINS;
```

Để xác nhận parser và index hoạt động đúng, không chỉ kiểm tra DDL. Hãy tạo bộ dữ liệu đại diện gồm từ ngắn, từ dài, dấu câu, khoảng trắng, stopword, chuỗi CJK và truy vấn có độ dài khác nhau. Chạy MATCH AGAINST() trên bộ truy vấn đó và kiểm tra cả kết quả lẫn relevance.

### 10.1. Kiểm tra FULLTEXT index bằng truy vấn mẫu

Ví dụ kiểm tra index mặc định:

```sql
SELECT article_id
FROM articles
WHERE MATCH(body)
AGAINST ('database' IN NATURAL LANGUAGE MODE);
```

Ví dụ kiểm tra boolean mode:

```sql
SELECT article_id
FROM articles
WHERE MATCH(body)
AGAINST ('+database -legacy' IN BOOLEAN MODE);
```

Ví dụ kiểm tra index ngram:

```sql
SELECT article_id
FROM cjk_articles
WHERE MATCH(content)
AGAINST ('数据库' IN NATURAL LANGUAGE MODE);
```

Nếu kết quả rỗng ngoài dự kiến, kiểm tra token size, stopword, parser được gắn vào index, charset/collation và nội dung thực tế đã được index.

## 11. Hiệu năng và chi phí vận hành

Ngram parser thường tạo nhiều token chồng lấn. Với văn bản dài, số token có thể lớn hơn đáng kể so với parser theo từ. Điều này làm tăng:

- Dung lượng FULLTEXT index.
- CPU và I/O khi tạo hoặc cập nhật index.
- Chi phí ghi khi INSERT, UPDATE hoặc DELETE văn bản.
- Số ứng viên cần đánh giá khi token phổ biến.
- Thời gian rebuild khi thay đổi cấu hình.

Parser mặc định cũng có chi phí stopword và token size, nhưng thường tạo số token gần với số từ được nhận diện hơn.

Để chọn parser, đo ít nhất:

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Index size | Index tăng bao nhiêu khi chuyển sang ngram? |
| Build time | Thời gian tạo/rebuild index có chấp nhận được? |
| Write latency | INSERT/UPDATE nội dung tăng chi phí bao nhiêu? |
| Query latency | Truy vấn thường gặp nhanh hay chậm hơn? |
| Recall | Có tìm được các tài liệu người dùng kỳ vọng? |
| Precision | Có quá nhiều kết quả không liên quan? |
| Relevance | Thứ tự kết quả có hợp lý không? |

Không đánh giá parser chỉ bằng một vài câu query. Cần có tập truy vấn thực tế, bao gồm cả trường hợp người dùng nhập sai chính tả, từ ngắn, cụm từ, ký tự đặc biệt và truy vấn nhiều ngôn ngữ nếu hệ thống hỗ trợ.

## 12. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng parser mặc định cho văn bản không có ranh giới từ | Token không phản ánh nội dung cần tìm | Thử ngram parser |
| Dùng ngram cho mọi loại văn bản | Index lớn, nhiều kết quả nhiễu | Chọn parser theo ngôn ngữ và truy vấn |
| Không kiểm tra min/max token size | Từ ngắn hoặc dài không được index | Kiểm tra biến theo engine |
| Quên stopword | Thuật ngữ cần tìm bị loại | Kiểm tra và tùy chỉnh stopword |
| Đổi token size nhưng không rebuild index | Index vẫn chứa token theo cấu hình cũ | Rebuild FULLTEXT index |
| Dùng ngram_token_size quá lớn | Truy vấn ngắn không tạo đủ token | Chọn n nhỏ hơn và đánh giá nhiễu |
| Dùng ngram_token_size quá nhỏ | Quá nhiều token phổ biến | Đo index size và precision |
| Nghĩ ngram hiểu ngữ nghĩa từ | Kết quả chỉ dựa trên chuỗi ký tự | Dùng tokenizer/search engine có phân tích ngôn ngữ khi cần |
| Nhầm byte UTF-8 với ký tự | Dự đoán sai n-gram | Kiểm thử bằng ký tự Unicode thật |
| MATCH() dùng danh sách cột không khớp FULLTEXT index | Không dùng được index phù hợp hoặc truy vấn lỗi | Khớp chính xác tập cột của index |
| Dùng FULLTEXT cho substring một ký tự | Không có token tương ứng | Dùng cột mã, B-tree hoặc search strategy khác |
| Không đo chi phí ghi | Index tìm nhanh nhưng cập nhật dữ liệu chậm | Benchmark cả read và write workload |

## 13. Quy trình chọn parser cho hệ thống thực tế

1. Xác định ngôn ngữ và loại văn bản trong cột.
2. Thu thập truy vấn thực tế và xác định người dùng tìm theo từ, cụm từ hay substring.
3. Chọn parser mặc định làm baseline cho văn bản có ranh giới từ rõ.
4. Thử ngram parser trên corpus đại diện nếu văn bản không có ranh giới từ hoặc cần tìm chuỗi con.
5. Kiểm tra min/max token size, ngram_token_size và stopword.
6. Tạo index thử nghiệm và chạy tập truy vấn chuẩn.
7. Đo precision, recall, relevance, index size và write latency.
8. Chọn cấu hình đáp ứng yêu cầu sản phẩm và khả năng vận hành.
9. Lập kế hoạch rebuild index và triển khai nhất quán trên các node.
10. Theo dõi chất lượng tìm kiếm sau khi phát hành.

## 14. Checklist trước khi triển khai

**Dữ liệu và ngôn ngữ:**

- Xác định charset/collation của các cột văn bản.
- Xác định ranh giới từ có rõ hay không.
- Kiểm thử chữ hoa, chữ thường, dấu và ký tự Unicode.
- Kiểm thử từ ngắn, từ dài, mã định danh và dấu câu.
- Với tiếng Việt, kiểm thử cụm từ nhiều âm tiết và truy vấn không dấu.

**Parser và index:**

- Xác nhận storage engine InnoDB hoặc MyISAM.
- Chọn parser mặc định hay ngram cho từng FULLTEXT index.
- Kiểm tra min/max token size hoặc ngram_token_size.
- Kiểm tra stopword list.
- Đảm bảo MATCH column list khớp FULLTEXT index.
- Đánh giá số lượng FULLTEXT index và dung lượng.

**Vận hành:**

- Lập kế hoạch cấu hình startup và restart nếu cần.
- Rebuild index sau khi đổi parser/tokenization/stopword.
- Đo thời gian tạo index và tải ghi.
- Kiểm thử replication và các node tìm kiếm.
- Chuẩn bị bộ truy vấn hồi quy để kiểm tra kết quả sau migration.
- Theo dõi index size, query latency và tỷ lệ kết quả không liên quan.

## 15. Ghi nhớ

- FULLTEXT parser quyết định cách MySQL tách văn bản thành token khi lập chỉ mục và khi phân tích chuỗi tìm kiếm.
- Parser mặc định tách theo từ và chịu ảnh hưởng của min/max token size cùng stopword.
- InnoDB mặc định có innodb_ft_min_token_size = 3 và innodb_ft_max_token_size = 84; MyISAM thường có ft_min_word_len = 4 và ft_max_word_len = 84.
- Ngram parser chia chuỗi thành các nhóm n ký tự liên tiếp.
- ngram_token_size mặc định là 2 và có phạm vi 1 đến 10.
- Ngram parser phù hợp với CJK và văn bản không có ranh giới từ rõ; nó không hiểu ngữ nghĩa hoặc phân đoạn từ.
- Với tiếng Việt, cần đánh giá cụm từ nhiều âm tiết, dấu và yêu cầu tìm kiếm; ngram không thay thế bộ phân đoạn từ.
- Stopword có thể làm token cần tìm bị loại khỏi index.
- InnoDB và MyISAM có biến token size/stopword khác nhau.
- Thay đổi parser hoặc quy tắc tokenization cần xây dựng lại FULLTEXT index.
- MATCH() AGAINST() cần dùng đúng tập cột đã được FULLTEXT index hỗ trợ.
- Ngram có thể tăng index size và write cost do token chồng lấn.
- Dùng bộ truy vấn thực tế để đánh giá precision, recall, relevance, latency và dung lượng.
- Nếu cần stemming, synonym, fuzzy search hoặc phân tích ngôn ngữ sâu, cân nhắc xử lý ở ứng dụng hoặc search engine chuyên dụng.

Chọn parser theo ngôn ngữ và hành vi tìm kiếm mà sản phẩm cần hỗ trợ. Parser mặc định phù hợp với tìm kiếm theo từ có ranh giới rõ; ngram phù hợp với tìm kiếm theo chuỗi ký tự ở các ngôn ngữ như CJK. Sau khi chọn, hãy cố định quy tắc tokenization, xây dựng lại index đúng cách và kiểm thử chất lượng bằng truy vấn thực tế.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — Full-Text Search Functions: https://dev.mysql.com/doc/refman/8.0/en/fulltext-search.html
- MySQL 8.0 Reference Manual — Full-Text Stopwords: https://dev.mysql.com/doc/refman/8.0/en/fulltext-stopwords.html
- MySQL 8.0 Reference Manual — ngram Full-Text Parser: https://dev.mysql.com/doc/refman/8.0/en/fulltext-search-ngram.html
- MySQL 8.0 Reference Manual — Fine-Tuning MySQL Full-Text Search: https://dev.mysql.com/doc/refman/8.0/en/fulltext-fine-tuning.html
- MySQL 8.0 Reference Manual — InnoDB FULLTEXT Indexes: https://dev.mysql.com/doc/refman/8.0/en/innodb-fulltext-index.html

