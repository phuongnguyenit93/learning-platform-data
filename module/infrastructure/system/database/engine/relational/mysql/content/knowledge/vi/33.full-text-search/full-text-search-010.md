# Chi phí cập nhật FULLTEXT và lựa chọn công cụ tìm kiếm chuyên biệt

MySQL `FULLTEXT` giúp tìm theo từ và xếp hạng tài liệu, nhưng mỗi lần INSERT, DELETE hoặc UPDATE các cột được lập chỉ mục đều có thể phát sinh công việc duy trì inverted index. Khi dữ liệu lớn, write workload cao hoặc có nhiều FULLTEXT index, chi phí CPU, I/O, dung lượng và độ trễ ghi cần được tính vào thiết kế. Nếu sản phẩm cần fuzzy matching, autocomplete, synonym, analyzer theo ngôn ngữ hoặc mở rộng search độc lập với OLTP, một search engine chuyên dụng có thể phù hợp hơn nhưng sẽ bổ sung pipeline đồng bộ và chi phí vận hành.

Chiến lược tìm kiếm cần bắt đầu từ hai phía: chất lượng kết quả mà người dùng cần và chi phí duy trì chỉ mục theo nhịp ghi dữ liệu. Cần phân loại yêu cầu exact/prefix/substring/term/phrase/fuzzy; xác định ngôn ngữ, tokenization, stopword, độ dài token, ranking, pagination, độ trễ đồng bộ và quy mô corpus. Không có một loại index hay một công cụ duy nhất tối ưu cho mọi yêu cầu.

Chọn chiến lược bắt đầu từ hành vi người dùng và đặc tính dữ liệu, sau đó mới chọn engine, parser, mode và index. Cần xác định ngôn ngữ, cách tách từ, stopword, độ dài token, độ chính xác mong muốn, thứ tự xếp hạng, yêu cầu phân trang, độ trễ cập nhật và quy mô dữ liệu. Một truy vấn chạy nhanh nhưng bỏ mất từ quan trọng hoặc xếp hạng kết quả sai vẫn là một giải pháp tìm kiếm kém.

Bài học thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, execution plan, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là lựa chọn đúng giữa FULLTEXT, các kiểu tìm kiếm SQL khác và dịch vụ tìm kiếm bên ngoài; triển khai chỉ mục phù hợp; sau đó đo chất lượng lẫn hiệu năng bằng dữ liệu đại diện.

Sau bài học, bạn có thể:

- Phân biệt tìm kiếm từ, cụm từ, tiền tố, chuỗi con và tìm kiếm gần nghĩa.
- Quyết định khi nào dùng B-tree, `LIKE`, `FULLTEXT` hoặc search engine chuyên dụng.
- Chọn InnoDB, parser, natural language mode, boolean mode và query expansion.
- Thiết kế FULLTEXT index một cột hoặc nhiều cột cho tiêu đề/nội dung.
- Hiểu ảnh hưởng của stopword, token size, collation và ngôn ngữ.
- Chọn ngram parser cho ngôn ngữ không phân tách từ bằng khoảng trắng như tiếng Trung, Nhật và Hàn.
- Viết `MATCH() AGAINST()` có xếp hạng, lọc và phân trang ổn định.
- Đánh giá giới hạn FULLTEXT, chi phí ghi và ảnh hưởng tới replication.
- Ước lượng chi phí INSERT/UPDATE/DELETE trên cột FULLTEXT, bulk load và rebuild index.
- Giảm write amplification bằng cách chọn đúng số lượng index và tổ chức ingest phù hợp.
- Chọn giữa MySQL FULLTEXT và search engine chuyên dụng theo tính năng, tải đọc/ghi, freshness và chi phí vận hành.
- Kiểm thử relevance, precision/recall, latency và tính mới của chỉ mục.

## 1. Bắt đầu từ loại tìm kiếm cần hỗ trợ

Trước khi tạo index, hãy phân loại truy vấn mà sản phẩm cần thực hiện.

| Nhu cầu | Ví dụ | Cơ chế phù hợp thường gặp |
| --- | --- | --- |
| So khớp chính xác | Email, mã đơn, SKU | `=` với UNIQUE/B-tree |
| Tìm tiền tố | Tên bắt đầu bằng `dat` | `LIKE 'dat%'` với B-tree phù hợp hoặc range predicate |
| Tìm chuỗi con bất kỳ | Mã chứa `-2026-`, tên có đoạn ký tự giữa | `LIKE '%...%'` trên tập nhỏ; specialized n-gram/trigram index hoặc search service khi lớn |
| Tìm theo từ | Tài liệu có các từ `database`, `index` | FULLTEXT |
| Tìm cụm từ | Cụm `query optimizer` | FULLTEXT phrase search hoặc search engine |
| Bắt buộc/loại trừ từ | Có `mysql`, không có `deprecated` | FULLTEXT boolean mode |
| Tự động hoàn thành | Gợi ý khi đang gõ `mys...` | Prefix index, bảng suggestion hoặc search service |
| Sai chính tả/fuzzy | `myqsl` gần với `mysql` | Search engine có fuzzy matching hoặc logic ứng dụng |
| Đồng nghĩa/ngôn ngữ | `car` và `automobile` | Synonym dictionary/analyzer ở ứng dụng hoặc search engine; thiết kế riêng nếu dùng MySQL |
| Tìm nhiều điều kiện và facet | Văn bản + danh mục + khoảng giá + đếm facet | FULLTEXT kết hợp SQL filter nếu quy mô phù hợp; search engine khi cần facet/search analytics lớn |

Không dùng FULLTEXT chỉ vì dữ liệu là `VARCHAR` hoặc `TEXT`. FULLTEXT phân tích nội dung thành token theo parser và quy tắc ngôn ngữ; nó không phải index tổng quát cho mọi chuỗi con.

## 2. Chọn giữa B-tree, LIKE, FULLTEXT và search service

### 2.1. B-tree cho equality và prefix

B-tree là lựa chọn tự nhiên khi tìm khóa chính xác:

```sql
CREATE INDEX idx_article_slug ON article (slug);

SELECT article_id, title
FROM article
WHERE slug = 'mysql-full-text-search';
```

Với tìm tiền tố, một pattern không bắt đầu bằng wildcard có thể tận dụng B-tree:

```sql
SELECT article_id, title
FROM article
WHERE title LIKE 'MySQL%';
```

Khả năng dùng index phụ thuộc collation, biểu thức và kiểu pattern. B-tree không giải quyết tốt tìm chuỗi con có wildcard ở đầu.

### 2.2. LIKE cho tập nhỏ hoặc chuỗi con đơn giản

```sql
SELECT product_id, product_name
FROM product
WHERE product_name LIKE '%adapter%';
```

Pattern `%adapter%` thường không có điểm bắt đầu để B-tree định vị range, nên có thể quét nhiều hàng. Với bảng nhỏ, dữ liệu ít thay đổi hoặc yêu cầu tìm đúng chuỗi ký tự, cách này vẫn có thể là lựa chọn đơn giản và chính xác. Đo bằng `EXPLAIN` và dữ liệu thật trước khi thay thế.

FULLTEXT không phải phương án thay thế trực tiếp cho `LIKE '%term%'`: FULLTEXT tìm token theo parser, thường bỏ token quá ngắn hoặc stopword và không tìm mọi chuỗi ký tự nằm giữa một token.

### 2.3. FULLTEXT cho tìm kiếm theo từ

FULLTEXT xây dựng inverted index: mỗi token được ánh xạ tới các tài liệu chứa token đó. Truy vấn có thể tìm từ, cụm từ hoặc điều kiện boolean, đồng thời tính điểm relevance.

```sql
CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    published_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_article_title_body (title, body),
    KEY idx_article_status_date (status, published_at)
) ENGINE = InnoDB;
```

Truy vấn:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM article
WHERE MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
  AND status = 'PUBLISHED'
ORDER BY score DESC, article_id DESC
LIMIT 20;
```

`MATCH()` nhận đúng danh sách cột được lập FULLTEXT index. Khi thiết kế, dùng cùng danh sách cột và thứ tự nhất quán với định nghĩa index để tránh lỗi hoặc khiến truy vấn không khớp index mong muốn. Một FULLTEXT index nhiều cột cho phép tìm trên tổ hợp trường đó; không giả định rằng một index chỉ có `title` cũng phục vụ được `MATCH(title, body)`.

### 2.4. Search engine chuyên dụng

Cân nhắc OpenSearch, Elasticsearch hoặc dịch vụ tương đương khi sản phẩm cần một hay nhiều tính năng sau:

- Fuzzy matching, typo tolerance, synonym graph và analyzer theo ngôn ngữ.
- Autocomplete, search-as-you-type, highlighting hoặc suggest.
- Facet/aggregation tìm kiếm phức tạp trên lượng dữ liệu lớn.
- Phân phối chỉ mục, shard, scale độc lập và tuning search workload riêng.
- Relevance model hoặc ranking tùy biến nhiều tín hiệu.
- Nhiều nguồn dữ liệu và pipeline đồng bộ chỉ mục.

Search engine thường là bản chiếu phục vụ đọc, không nên tự trở thành nguồn dữ liệu nghiệp vụ thứ hai. Giữ MySQL làm source of truth; đồng bộ sang search service bằng outbox/CDC hoặc pipeline có thể retry, theo dõi lag và rebuild index.

## 3. Chọn storage engine và kiểu cột

MySQL hỗ trợ FULLTEXT index trên các cột kiểu `CHAR`, `VARCHAR` và `TEXT` với InnoDB hoặc MyISAM. Với ứng dụng giao dịch hiện đại, InnoDB thường là lựa chọn mặc định vì transaction, crash recovery và row-level locking. MyISAM là engine cũ, không có transaction và có mô hình khóa khác; chỉ chọn khi có lý do tương thích/đặc thù đã được đánh giá.

Ví dụ bảng InnoDB:

```sql
CREATE TABLE knowledge_document (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(400) NOT NULL,
    summary TEXT NULL,
    content LONGTEXT NOT NULL,
    language_code VARCHAR(10) NOT NULL,
    visibility VARCHAR(20) NOT NULL DEFAULT 'PUBLIC',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_knowledge_title_content (title, content),
    KEY idx_knowledge_language_visibility (language_code, visibility)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

Ở đây có một FULLTEXT index tổ hợp cho `title` và `content`, phục vụ truy vấn tìm trên hai trường cùng lúc. Một FULLTEXT index khác trên `content` hoặc `title` riêng chỉ cần thiết nếu workload có chế độ tìm độc lập trên từng trường hoặc cần trọng số riêng. Mỗi index bổ sung đều có chi phí lưu trữ và cập nhật.

### 3.1. Một index nhiều cột hay nhiều index riêng?

Nếu giao diện tìm kiếm luôn coi title và body là một tập văn bản chung, một index `FULLTEXT(title, body)` là lựa chọn rõ ràng. Nếu có hai chế độ riêng biệt (chỉ tìm tiêu đề và tìm toàn văn), có thể cần index khác nhau hoặc thiết kế cột tìm kiếm riêng. Đừng mặc định FULLTEXT index trên từng cột tự động kết hợp thành một index nhiều cột.

Ví dụ index riêng:

```sql
ALTER TABLE knowledge_document
ADD FULLTEXT KEY ft_knowledge_title (title),
ADD FULLTEXT KEY ft_knowledge_content (content);
```

Sau đó có thể truy vấn:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title) AGAINST ('transaction' IN NATURAL LANGUAGE MODE);
```

Các index riêng này là lựa chọn bổ sung cho những workload cần tìm title-only/content-only hoặc tính trọng số riêng. Chúng làm tăng dung lượng và chi phí ghi; nếu chỉ tìm title+content như một corpus, giữ index tổ hợp ban đầu và bỏ qua hai index riêng. Nếu cần cả ba kiểu truy vấn, có thể giữ cả ba sau khi đo chi phí.

### 3.2. Dữ liệu cần tìm có thực sự là văn bản?

Không nên đưa mọi thuộc tính vào một trường `TEXT` để tiện tìm. Mã định danh, trạng thái, ngày tháng, tenant, category và số tiền nên là cột có kiểu phù hợp và index quan hệ. FULLTEXT xử lý nội dung ngôn ngữ; B-tree xử lý filter/join/sort có cấu trúc.

## 4. Natural language mode

Natural language mode là chế độ mặc định của `MATCH() AGAINST()`. MySQL phân tích query thành từ và tính relevance dựa trên sự xuất hiện của các từ trong tài liệu và tập tài liệu.

```sql
SELECT
    document_id,
    title,
    MATCH(title, content)
        AGAINST ('transaction isolation mysql' IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title, content)
        AGAINST ('transaction isolation mysql' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC, document_id DESC
LIMIT 20;
```

Đặc điểm:

- Phù hợp với ô tìm kiếm tự do, người dùng nhập một vài từ khóa.
- Kết quả được xếp hạng theo relevance; điểm số không phải xác suất đúng.
- Từ quá ngắn, quá dài hoặc nằm trong stopword list có thể bị bỏ qua.
- Thứ tự từ trong query không đồng nghĩa với yêu cầu cụm từ chính xác.
- Relevance phụ thuộc tập dữ liệu và thuật toán; không so sánh trực tiếp điểm giữa hai bảng hoặc hai corpus khác nhau.

Natural language mode phù hợp khi người dùng muốn tìm tài liệu liên quan đến một chủ đề mà không cần biểu diễn logic bắt buộc/loại trừ.

## 5. Boolean mode

Boolean mode cho phép điều khiển từ nào bắt buộc, từ nào bị loại, nhóm từ và một số điều chỉnh relevance.

```sql
SELECT
    document_id,
    title,
    MATCH(title, content)
        AGAINST ('+mysql +index -deprecated' IN BOOLEAN MODE) AS score
FROM knowledge_document
WHERE MATCH(title, content)
        AGAINST ('+mysql +index -deprecated' IN BOOLEAN MODE)
ORDER BY score DESC, document_id DESC
LIMIT 20;
```

Các toán tử thường dùng:

| Ký hiệu | Ý nghĩa thường gặp |
| --- | --- |
| `+word` | Từ phải xuất hiện |
| `-word` | Loại tài liệu có từ đó |
| `word` | Từ tùy chọn; nếu không có toán tử bắt buộc, hành vi theo boolean query rules |
| `"a phrase"` | Tìm cụm từ theo thứ tự token |
| `word*` | Prefix/truncation của token |
| `>` và `<` | Tăng/giảm đóng góp relevance của từ |
| `~word` | Giảm điểm khi từ xuất hiện |
| `( ... )` | Nhóm biểu thức |

Ví dụ yêu cầu `mysql`, đồng thời có `replication` hoặc `binary log`, nhưng loại `deprecated`:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (
    '+mysql +(replication "binary log") -deprecated'
    IN BOOLEAN MODE
);
```

Boolean mode phù hợp với giao diện tìm kiếm nâng cao hoặc bộ lọc từ khóa có quy tắc. Cú pháp là một ngôn ngữ truy vấn riêng: bind parameter bảo vệ SQL khỏi injection nhưng không tự giới hạn toán tử boolean mà người dùng có thể gửi. Nếu sản phẩm chỉ cho phép một tập toán tử, hãy parse/validate query grammar ở ứng dụng.

Không mặc định kết quả boolean mode được sắp xếp theo score giống natural language mode. Nếu cần ranking, lấy giá trị `MATCH() AGAINST()` và quy định `ORDER BY` rõ ràng; kiểm thử relevance trên tập truy vấn thực tế.

## 6. Phrase search và query expansion

### 6.1. Tìm cụm từ

Phrase search dùng dấu ngoặc kép trong query string:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (
    '"query optimizer"' IN BOOLEAN MODE
);
```

Phrase search dựa trên token do parser tạo ra. Nó không giống tìm chuỗi byte liên tiếp bằng `LIKE '%query optimizer%'`. Dấu câu, stopword và tokenization ảnh hưởng cách cụm từ được hiểu. Kiểm thử với dữ liệu và ngôn ngữ thực tế.

### 6.2. Query expansion

`WITH QUERY EXPANSION` thực hiện tìm kiếm mở rộng: MySQL lấy các tài liệu phù hợp với query ban đầu, dùng các từ liên quan từ những tài liệu đó để mở rộng lần tìm tiếp theo.

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (
    'mysql replication' WITH QUERY EXPANSION
)
LIMIT 20;
```

Chế độ này có thể tìm tài liệu không chứa đầy đủ từ khóa ban đầu nhưng có nội dung liên quan qua các tài liệu ban đầu. Nó cũng có thể khuếch đại nhiễu nếu kết quả vòng đầu không tốt hoặc corpus có nhiều thuật ngữ chung. Chỉ bật khi sản phẩm thực sự cần expansion và relevance test chứng minh lợi ích.

## 7. Tokenization, stopword và độ dài từ

FULLTEXT không lập chỉ mục nguyên văn từng ký tự. Parser tách nội dung thành token; sau đó MySQL áp dụng quy tắc stopword và độ dài token. Vì vậy, hai query giống nhau về chuỗi có thể cho kết quả khác nếu parser/config khác.

### 7.1. Độ dài token tối thiểu/tối đa

Các biến phổ biến:

| Engine/parser | Biến | Giá trị mặc định thường gặp |
| --- | --- | --- |
| InnoDB built-in parser | `innodb_ft_min_token_size` | 3 |
| InnoDB built-in parser | `innodb_ft_max_token_size` | 84 |
| MyISAM built-in parser | `ft_min_word_len` | 4 |
| MyISAM built-in parser | `ft_max_word_len` | 84 |

Xác minh giá trị trên server:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
```

Thay đổi các biến cấu hình token size thường yêu cầu cấu hình server và rebuild FULLTEXT index để nội dung được token hóa lại. Chỉ thay biến mà không rebuild index có thể khiến truy vấn và index không cùng quy tắc. Lập kế hoạch bảo trì và kiểm tra thời gian xây dựng lại trên dữ liệu có kích thước gần production.

### 7.2. Stopword

Stopword là các từ phổ biến bị loại khỏi FULLTEXT index hoặc query theo cấu hình. Điều này giảm index size và nhiễu nhưng có thể làm mất các từ có ý nghĩa trong domain. Ví dụ một hệ thống tìm mã kỹ thuật hoặc thuật ngữ ngắn có thể cần điều chỉnh stopword/token rules.

MySQL có danh sách stopword mặc định và hỗ trợ cấu hình danh sách riêng theo engine. Trước khi thay đổi, xác định:

- Những từ nào cần được tìm dù phổ biến.
- Danh sách dùng chung toàn server hay riêng cho một bảng.
- Cách đồng bộ cấu hình giữa primary và replica.
- Quy trình rebuild FULLTEXT index sau khi thay đổi.
- Tác động đến relevance và dung lượng index.

Với InnoDB, các biến và bảng cấu hình stopword gồm `innodb_ft_enable_stopword`, `innodb_ft_server_stopword_table` và `innodb_ft_user_stopword_table`. MyISAM có cấu hình stopword riêng như `ft_stopword_file`. Không áp dụng cấu hình của một engine cho engine còn lại.

## 8. Charset, collation và ngôn ngữ

Chọn charset/collation ngay từ đầu. Với ứng dụng mới, `utf8mb4` là lựa chọn thông dụng để hỗ trợ Unicode đầy đủ. Collation ảnh hưởng so sánh văn bản và có thể ảnh hưởng hành vi phân biệt hoa/thường, dấu tùy theo collation được chọn. Không mặc định rằng mọi FULLTEXT search đều bỏ dấu hoặc xử lý ngôn ngữ giống nhau.

Kiểm tra cấu hình cột và bảng:

```sql
SHOW FULL COLUMNS FROM knowledge_document;
SHOW CREATE TABLE knowledge_document;
```

Đối với tiếng Việt:

- Một từ tiếng Việt có dấu có thể được lưu dưới dạng Unicode; cần thống nhất chuẩn hóa Unicode giữa nguồn nhập và query.
- Cách viết có dấu/không dấu, từ ghép, từ đồng âm và cách tách từ là các quyết định relevance riêng.
- Built-in parser của MySQL chủ yếu phân tách token theo quy tắc parser, không phải bộ phân tích ngôn ngữ tiếng Việt hoàn chỉnh.
- Ngram parser có thể hữu ích cho tìm theo chuỗi ký tự/ngram nhưng không tự hiểu ranh giới từ hay ngữ nghĩa tiếng Việt.
- Nếu cần bỏ dấu, synonym, stemming hoặc phân đoạn từ chất lượng cao, hãy chuẩn hóa ở ingestion/query layer hoặc dùng search engine có analyzer phù hợp; kiểm thử bằng bộ query tiếng Việt thật.

## 9. Ngram parser cho ngôn ngữ không có dấu cách phân tách từ

Built-in parser mặc định thường dựa trên khoảng trắng và dấu câu để nhận diện từ. Với tiếng Trung, Nhật và Hàn, cách phân tách này không phù hợp như các ngôn ngữ dùng khoảng trắng giữa các từ. MySQL cung cấp ngram full-text parser để chia văn bản thành các chuỗi ký tự liên tiếp có độ dài cố định.

Ví dụ tạo bảng dùng ngram parser:

```sql
CREATE TABLE product_description_cjk (
    product_id BIGINT UNSIGNED NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (product_id),
    FULLTEXT KEY ft_product_description (description) WITH PARSER ngram
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Kích thước ngram được điều khiển bởi biến `ngram_token_size` (mặc định thường là 2). Đây là biến cấu hình server; thay đổi yêu cầu xây dựng lại FULLTEXT index để token mới được tạo theo kích thước mới. Ngram parser cũng có quy tắc stopword riêng: stopword được áp dụng theo ngram thay vì nguyên từ đầy đủ.

Ngram phù hợp khi yêu cầu tìm theo đoạn ký tự và ngôn ngữ không có ranh giới từ rõ. Tuy nhiên:

- Token size nhỏ làm index lớn và có thể tăng false positive.
- Token size lớn giảm index nhưng có thể bỏ lỡ query ngắn.
- Phrase matching và relevance cần kiểm thử theo ngôn ngữ.
- Không thay thế analyzer chuyên dụng nếu cần hiểu từ, ngữ pháp, synonym hoặc typo.

Không áp dụng ngram cho mọi bảng chỉ vì dữ liệu có Unicode. Với tiếng Việt hoặc tiếng Anh, built-in parser có thể phù hợp hơn; chọn bằng test set và query log.

## 10. Xây dựng FULLTEXT index và kiểm tra metadata

Nếu bảng hiện có chưa có FULLTEXT index tổ hợp này, có thể thêm bằng ALTER TABLE. Bảng mẫu tạo ở mục 3 đã có index `ft_knowledge_title_content`, vì vậy không chạy lại câu lệnh này trên chính fixture đó:

```sql
ALTER TABLE knowledge_document
ADD FULLTEXT KEY ft_knowledge_title_content (title, content);
```

Kiểm tra định nghĩa:

```sql
SHOW CREATE TABLE knowledge_document;
SHOW INDEX FROM knowledge_document;
```

Tạo index có thể tiêu thụ CPU, I/O, temporary space và ảnh hưởng workload ghi/đọc. Trên bảng lớn, lập kế hoạch dung lượng và thời gian; kiểm tra khả năng online DDL theo đúng phiên bản, engine và thao tác. Không giả định thêm FULLTEXT index luôn không khóa hoặc không ảnh hưởng replica lag.

FULLTEXT index được cập nhật khi dữ liệu thay đổi. Mỗi INSERT/UPDATE/DELETE liên quan cột được index đều có chi phí duy trì inverted index. Nếu có nhiều FULLTEXT index trùng lặp, write amplification và dung lượng index tăng đáng kể.

### 10.1. Công việc phát sinh khi ghi dữ liệu

FULLTEXT index lưu các token và quan hệ giữa token với tài liệu chứa token đó. Vì vậy:

- **INSERT:** MySQL phải phân tích văn bản trong các cột FULLTEXT và thêm các token vào chỉ mục.
- **UPDATE cột được index:** các token cũ có thể phải được loại bỏ và token mới được thêm vào. Đổi một đoạn văn bản dài thường tốn nhiều công việc hơn đổi một trường ngắn.
- **DELETE:** các mục chỉ mục liên quan tới tài liệu bị xóa phải được xử lý; xóa hàng loạt có thể làm tăng I/O và công việc dọn dẹp.
- **UPDATE cột không được FULLTEXT index:** không cần phân tích lại token của các cột văn bản không đổi, dù row và các B-tree index khác vẫn có thể phát sinh chi phí.

Chi phí phụ thuộc độ dài văn bản, số token, số FULLTEXT index, parser, tần suất thay đổi và mức cạnh tranh tài nguyên. Một bảng có ba FULLTEXT index cho cùng một nội dung sẽ có write amplification lớn hơn bảng chỉ giữ index tổ hợp mà workload thực sự dùng. InnoDB quản lý các cấu trúc và cache nội bộ cho full-text; do đó thời gian một câu DML riêng lẻ không phải lúc nào cũng thể hiện toàn bộ công việc index được xử lý về sau.

### 10.2. Tổ chức bulk load, batch và rebuild

Với bảng mới và dữ liệu được nạp theo lô lớn, thường nên cân nhắc nạp dữ liệu trước rồi xây FULLTEXT index sau. Cách này tránh duy trì inverted index cho từng hàng trong suốt giai đoạn import. Với bảng đang phục vụ production, không thể tùy tiện bỏ index; hãy dùng staging table hoặc cửa sổ bảo trì nếu cần dựng lại chỉ mục, rồi chuyển dữ liệu theo quy trình đã kiểm thử.

```sql
-- Ví dụ cho bảng staging mới: tạo bảng và nạp dữ liệu trước.
CREATE TABLE knowledge_document_stage (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(400) NOT NULL,
    content LONGTEXT NOT NULL,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;

-- Sau khi import và kiểm tra dữ liệu staging:
ALTER TABLE knowledge_document_stage
ADD FULLTEXT KEY ft_stage_title_content (title, content);
```

Đây là ví dụ về thứ tự thao tác, không phải lệnh thay thế bảng production hoàn chỉnh. Khi dựng index trên bảng lớn, dự trù CPU, I/O, temporary space, thời gian DDL và replication lag; kiểm tra khả năng online DDL theo đúng phiên bản MySQL và thao tác cụ thể.

Với luồng ghi liên tục:

- Chỉ tạo các FULLTEXT index phục vụ query thực tế; tránh index tổ hợp và index riêng trùng lặp nếu không có workload tương ứng.
- Gộp các thay đổi văn bản cùng một document vào một UPDATE thay vì nhiều lần cập nhật nhỏ liên tiếp khi nghiệp vụ cho phép.
- Chia bulk write thành batch vừa phải để giới hạn transaction, undo và thời gian giữ tài nguyên.
- Nếu chỉ đổi `visibility`, `status` hoặc metadata khác, không ghi lại toàn bộ `content` nếu không cần thiết.
- Khi đổi parser, stopword hoặc token-size setting, lập kế hoạch rebuild vì nội dung index cũ được tạo theo quy tắc trước đó.

### 10.3. Đo write cost thay vì chỉ đo tốc độ SELECT

Benchmark cần chạy cả workload đọc lẫn ghi. So sánh ít nhất ba trạng thái trên dữ liệu có kích thước tương đương: chưa có FULLTEXT index, có một index phù hợp, và có thêm các index riêng nếu sản phẩm cần. Ghi nhận:

- INSERT/UPDATE/DELETE throughput và p95/p99 latency.
- CPU, I/O, dung lượng FULLTEXT index và tổng kích thước bảng.
- Thời gian import, thời gian tạo/rebuild index và dung lượng tạm cần thiết.
- Replication lag trong lúc import, rebuild và ghi liên tục.
- Query latency, relevance và số kết quả để bảo đảm giảm chi phí ghi không làm mất yêu cầu tìm kiếm.

Không lấy việc một câu SELECT nhanh hơn làm bằng chứng rằng toàn bộ chiến lược tốt hơn. Nếu write workload là chủ đạo và nhu cầu tìm kiếm đơn giản, một index ít hơn hoặc tìm theo B-tree có thể phù hợp hơn.

### 10.4. Khi nào chọn search engine chuyên dụng?

| Tiêu chí | MySQL FULLTEXT | Search engine chuyên dụng |
| --- | --- | --- |
| Nguồn dữ liệu | Dữ liệu và tìm kiếm nằm cùng database | Thường là read model đồng bộ từ MySQL hoặc nhiều nguồn |
| Độ mới | Tìm kiếm theo trạng thái commit của MySQL | Thường eventual consistency tùy pipeline |
| Phân tích ngôn ngữ | Parser built-in và ngram | Analyzer, synonym, stemming và tokenizer phong phú hơn tùy sản phẩm |
| Tìm nâng cao | Natural language, boolean, phrase, query expansion | Fuzzy, autocomplete, typo tolerance, highlighting, facet và ranking tùy biến |
| Chi phí ghi | Duy trì FULLTEXT index trong transaction/database workload | Ghi MySQL cộng thêm đồng bộ, index và vận hành search cluster |
| Vận hành | Ít thành phần hơn nếu MySQL đã là nền tảng chính | Cần quản lý cluster, mapping, pipeline, retry, lag, rebuild và monitoring |

Ưu tiên MySQL FULLTEXT khi corpus và tải tìm kiếm phù hợp với database, cần độ mới gần transaction, truy vấn chủ yếu theo từ/cụm từ và muốn giữ kiến trúc đơn giản. Chọn search engine riêng khi yêu cầu analyzer/ranking vượt khả năng parser tích hợp, cần typo/fuzzy/autocomplete/facet, có nhiều nguồn dữ liệu hoặc cần scale search độc lập với OLTP.

Nếu tách search service, coi chỉ mục ngoài là bản chiếu có thể tái tạo. Dùng outbox hoặc CDC để đồng bộ, xử lý retry/idempotency, theo dõi lag và có quy trình rebuild từ MySQL. Đừng gửi HTTP trực tiếp từ trigger vì transaction MySQL không thể rollback side effect đã xảy ra ở dịch vụ ngoài.

## 11. MATCH() AGAINST() và xếp hạng kết quả

### 11.1. Mẫu truy vấn cơ bản

```sql
SELECT
    document_id,
    title,
    MATCH(title, content)
        AGAINST (? IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title, content)
        AGAINST (? IN NATURAL LANGUAGE MODE)
  AND visibility = 'PUBLIC'
ORDER BY relevance DESC, document_id DESC
LIMIT ?;
```

Dấu `?` minh họa prepared statement parameter. Trong ứng dụng, bind cùng search text cho hai vị trí và bind limit theo kiểu số. Không nối chuỗi người dùng trực tiếp vào SQL.

### 11.2. Tăng trọng số title

Nếu cần title có trọng số cao hơn content, có thể tạo truy vấn tính điểm từ hai FULLTEXT index:

Đây là phương án ranking tùy chọn, chỉ chạy khi đã tạo hai index riêng `ft_knowledge_title` và `ft_knowledge_content` ở mục 3.1. Nếu workload chỉ dùng index tổ hợp `(title, content)`, bỏ qua truy vấn này và dùng điểm relevance chung ở mục 11.1.

```sql
SELECT
    document_id,
    title,
    2.0 * MATCH(title) AGAINST (? IN NATURAL LANGUAGE MODE)
      + MATCH(content) AGAINST (? IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title) AGAINST (? IN NATURAL LANGUAGE MODE)
   OR MATCH(content) AGAINST (? IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC, document_id DESC
LIMIT 20;
```

Truy vấn này yêu cầu hai FULLTEXT index riêng cho `title` và `content` (được thêm trong mục 3.1). Trọng số `2.0` chỉ là ví dụ; chọn trọng số bằng đánh giá relevance và phản hồi người dùng, không dùng như hằng số phổ quát.

Nếu dùng một FULLTEXT index tổ hợp `(title, content)`, điểm số không tự cung cấp trọng số riêng cho title. Hãy chọn cấu trúc index và cách tính score phù hợp với yêu cầu ranking.

### 11.3. Filter có cấu trúc

FULLTEXT xử lý phần văn bản, còn các filter như tenant, status, category và date range nên dùng cột có kiểu và index phù hợp:

```sql
SELECT
    document_id,
    title,
    MATCH(title, content) AGAINST (? IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_document
WHERE MATCH(title, content) AGAINST (? IN NATURAL LANGUAGE MODE)
  AND language_code = 'vi'
  AND visibility = 'PUBLIC'
  AND created_at >= '2026-01-01'
ORDER BY relevance DESC, document_id DESC
LIMIT 50;
```

FULLTEXT và B-tree không phải lúc nào cũng được optimizer kết hợp theo cách trực giác. Dùng `EXPLAIN`/`EXPLAIN ANALYZE`, kiểm tra số hàng thực tế và benchmark trên phân bố tenant/status thật. Với multi-tenant, luôn đặt điều kiện tenant/authorization ở SQL; không dựa vào search index hoặc filter UI để bảo vệ dữ liệu.

## 12. Phân trang và tính ổn định

`LIMIT offset, count` dễ dùng cho trang đầu nhưng chi phí có thể tăng khi offset lớn vì server phải tìm/đọc và bỏ qua nhiều kết quả. Với relevance ranking, thứ hạng cũng có thể thay đổi khi corpus được cập nhật.

Các lựa chọn:

- Giới hạn page depth và chỉ hỗ trợ offset nhỏ.
- Dùng keyset pagination với khóa ổn định nếu thứ tự chủ yếu theo khóa/ngày.
- Với relevance, lưu snapshot/result ID hoặc dùng search service hỗ trợ point-in-time/search-after khi cần duyệt sâu ổn định.
- Thêm tie-breaker duy nhất như `document_id` để kết quả cùng score có thứ tự xác định.

Ví dụ offset đơn giản:

```sql
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY MATCH(title, content)
             AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) DESC,
         document_id DESC
LIMIT 20 OFFSET 40;
```

Không hứa rằng trang 3 luôn chứa đúng các hàng như lần tìm trước nếu document được thêm/xóa hoặc score thay đổi giữa các request. Contract API nên mô tả semantics của pagination và tính mới dữ liệu.

## 13. FULLTEXT và transaction

Với InnoDB, thao tác ghi bảng và cập nhật FULLTEXT index tuân theo transaction của bảng. Transaction chưa commit không nên được xem như đã xuất hiện trong kết quả tìm kiếm của session khác. Khi ứng dụng cần đọc ngay dữ liệu vừa ghi, hãy commit trước khi truy vấn từ transaction/session khác và kiểm thử visibility theo isolation level.

Một transaction ghi nhiều document rồi commit có thể làm index cập nhật theo batch transaction. Transaction dài giữ thay đổi chưa commit lâu hơn, làm tăng chi phí undo/lock và có thể trì hoãn việc các session khác nhìn thấy dữ liệu.

Không dùng FULLTEXT relevance làm cơ chế khóa hoặc kiểm tra uniqueness. Nếu một từ khóa/mã phải duy nhất, dùng UNIQUE constraint trên cột phù hợp.

## 14. Giới hạn và trường hợp FULLTEXT không phù hợp

- Tìm substring tùy ý ở giữa token không phải mục tiêu của built-in FULLTEXT parser.
- Token quá ngắn, stopword hoặc tokenization không phù hợp có thể khiến từ bị bỏ qua.
- Typo tolerance, stemming, synonym và ngữ nghĩa ngôn ngữ không phải chức năng tổng quát của built-in parser.
- FULLTEXT index có chi phí lưu trữ và duy trì khi dữ liệu thay đổi.
- Relevance score phụ thuộc corpus và thuật toán; không phải xác suất hay điểm có thể so sánh giữa mọi tập dữ liệu.
- Kết hợp filter B-tree với FULLTEXT cần kiểm tra execution plan; không giả định mọi index được intersect tối ưu.
- Search-as-you-type và autocomplete thường cần mô hình prefix/suggestion riêng.
- Search trên JSON tùy ý không được giải quyết bằng việc tạo FULLTEXT index trực tiếp trên JSON column; trích nội dung cần tìm sang cột văn bản được quản lý rõ ràng hoặc dùng search pipeline.
- Khi cần search trên nhiều nguồn dữ liệu, facet phức tạp hoặc scale đọc độc lập, một search service thường phù hợp hơn.

## 15. Quan sát execution plan và vận hành

Kiểm tra truy vấn:

```sql
EXPLAIN
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content)
      AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE);
```

Trên MySQL hỗ trợ `EXPLAIN ANALYZE`, có thể dùng để xem thời gian và số hàng thực tế; lệnh này thực thi truy vấn nên chỉ chạy với câu SELECT và môi trường phù hợp:

```sql
EXPLAIN ANALYZE
SELECT document_id, title
FROM knowledge_document
WHERE MATCH(title, content)
      AGAINST ('mysql transaction' IN NATURAL LANGUAGE MODE)
LIMIT 20;
```

Theo dõi:

- Query latency p50/p95/p99 và số request tìm kiếm.
- Số kết quả trung bình, query trả rỗng và query có token bị bỏ qua.
- FULLTEXT index size và tổng dung lượng bảng.
- CPU, I/O, buffer pool pressure và write latency khi bulk load.
- Replication lag sau import/rebuild hoặc batch cập nhật lớn.
- Thời gian rebuild index và dung lượng trống cần thiết.
- Relevance metrics từ bộ query chuẩn và phản hồi người dùng.

Nếu thay đổi stopword, token size, parser hoặc collation, hãy lên kế hoạch rebuild FULLTEXT index và kiểm thử lại relevance. Cấu hình phải nhất quán giữa primary, replica và môi trường triển khai.

## 16. Chọn kiến trúc đồng bộ với search engine ngoài

Nếu MySQL là source of truth và search service là read model, cần xử lý cập nhật không đồng bộ:

1. Transaction nghiệp vụ cập nhật document trong MySQL.
2. Cùng transaction đó ghi một outbox event chứa document ID và version.
3. Worker/CDC đọc outbox hoặc binlog, lấy phiên bản dữ liệu cần index.
4. Worker upsert/delete document trong search engine theo ID và version.
5. Ghi nhận checkpoint, retry lỗi tạm thời và đưa lỗi lâu dài vào dead-letter queue.
6. Có cơ chế rebuild toàn bộ index từ MySQL và đối soát số lượng/version.

Đừng gửi HTTP trực tiếp từ trigger. Database transaction không thể rollback một thao tác đã gửi sang search service. Outbox giữ ý định đồng bộ cùng transaction và cho phép worker retry độc lập.

Thiết kế phải chấp nhận eventual consistency: document vừa commit có thể chưa xuất hiện ngay trong kết quả tìm kiếm. Nếu nghiệp vụ yêu cầu read-your-writes, có thể trả dữ liệu vừa tạo trực tiếp từ transaction, chờ index acknowledgment hoặc bổ sung lookup trực tiếp theo ID.

## 17. Bảo mật và an toàn truy vấn

- Dùng prepared statement để bind search text, filter và limit.
- Với boolean mode, parse/validate toán tử theo grammar mà sản phẩm cho phép; bind parameter không ngăn người dùng gửi toán tử boolean hợp lệ nhưng không mong muốn.
- Luôn áp dụng tenant ID, visibility và authorization filter ở server-side SQL.
- Không trả nội dung nhạy cảm chỉ vì FULLTEXT match; áp dụng quyền đọc sau khi tìm kiếm.
- Giới hạn độ dài query, số token, page size và thời gian thực thi.
- Không log nguyên văn truy vấn nếu nó có thể chứa dữ liệu nhạy cảm; log dạng đã mask hoặc hash theo chính sách.
- Dùng account ứng dụng chỉ có quyền SELECT trên các bảng cần tìm; quyền DDL/rebuild index thuộc DBA/deployment.

## 18. Ma trận lựa chọn nhanh

| Bối cảnh | Chọn | Lý do và lưu ý |
| --- | --- | --- |
| Mã đơn, email, slug chính xác | B-tree/UNIQUE | Equality có tính xác định, hỗ trợ constraint |
| Gợi ý tên theo tiền tố | B-tree prefix | Nhanh, dễ kiểm soát, cần pattern không có wildcard đầu |
| Tìm đoạn ký tự ở giữa trong bảng nhỏ | LIKE | Đơn giản; đo full scan và giới hạn dữ liệu |
| Tìm từ trong title/body, corpus vừa phải | InnoDB FULLTEXT | Có inverted index và relevance tích hợp |
| Người dùng nhập từ bắt buộc/loại trừ | FULLTEXT boolean mode | Có cú pháp truy vấn nâng cao; cần validate grammar |
| Tìm cụm từ | FULLTEXT phrase search | Tokenization/stopword ảnh hưởng semantics |
| Tiếng Trung/Nhật/Hàn | Ngram hoặc search analyzer chuyên dụng | Chọn token size bằng test set |
| Tiếng Việt cần phân đoạn từ, bỏ dấu, synonym | Analyzer ứng dụng/search engine | Built-in FULLTEXT không phải bộ NLP tiếng Việt |
| Typo, fuzzy, autocomplete, facet lớn | Search engine chuyên dụng | Cần analyzer/ranking và scale độc lập |
| Search đa nguồn, phân phối toàn cụm | Search engine + outbox/CDC | Tách read model khỏi OLTP, chấp nhận eventual consistency |

## 19. Quy trình triển khai một chiến lược tìm kiếm

1. Thu thập query mẫu từ người dùng và phân loại exact/prefix/substring/term/phrase/fuzzy.
2. Xác định ngôn ngữ, charset, collation, normalization, stopword và token size.
3. Chọn engine; ưu tiên InnoDB cho dữ liệu giao dịch.
4. Thiết kế cột văn bản và FULLTEXT index đúng tập cột sẽ tìm.
5. Viết truy vấn mẫu cho natural language/boolean/phrase và filter có cấu trúc.
6. Tạo bộ query chuẩn cùng kết quả liên quan được đánh nhãn.
7. Đo precision, recall, top-k relevance và latency trên corpus đại diện.
8. Dùng EXPLAIN/EXPLAIN ANALYZE kiểm tra access path và số hàng thực tế.
9. Đo chi phí ghi, dung lượng index, rebuild và replication lag.
10. Chạy thử nghiệm với traffic/corpus gần production; rollout theo giai đoạn và theo dõi.
11. Nếu dùng search service, xây outbox/CDC, retry, idempotency, rebuild và đối soát.
12. Tài liệu hóa giới hạn tìm kiếm để sản phẩm không hứa hành vi mà engine không hỗ trợ.

## 20. Đo chất lượng tìm kiếm

Tốc độ không đủ để đánh giá search. Tạo tập query đại diện và gán nhãn tài liệu liên quan, sau đó đo:

- **Precision@k:** trong k kết quả đầu, tỷ lệ kết quả thực sự liên quan.
- **Recall@k:** trong các tài liệu liên quan đã biết, tỷ lệ xuất hiện trong k kết quả đầu.
- **NDCG@k:** đánh giá chất lượng thứ tự khi relevance có nhiều mức.
- **Zero-result rate:** tỷ lệ query không có kết quả.
- **Latency:** p50/p95/p99 dưới concurrency dự kiến.
- **Freshness:** độ trễ từ commit MySQL tới lúc tài liệu xuất hiện trong search.

Chia bộ query theo ngôn ngữ, độ dài, có dấu/không dấu, từ hiếm/phổ biến, phrase, typo và filter. Khi đổi parser, stopword hoặc token size, chạy lại toàn bộ bộ test để phát hiện hồi quy.

## 21. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| FULLTEXT không tìm được từ ngắn | Token nhỏ hơn min token size | Kiểm tra biến token size và cân nhắc index rebuild |
| Từ phổ biến không xuất hiện | Stopword list | Kiểm tra danh sách stopword và relevance requirement |
| MATCH báo không có FULLTEXT index phù hợp | Danh sách cột MATCH không khớp index | Tạo index đúng tổ hợp cột và dùng cùng danh sách trong MATCH |
| `%word%` nhanh chậm bất thường | FULLTEXT không tìm substring tùy ý | Chọn LIKE cho tập nhỏ hoặc ngram/search service |
| Tìm tiếng CJK kém | Built-in parser không phân đoạn từ phù hợp | Thử ngram parser và chọn token size bằng dữ liệu thật |
| Kết quả tiếng Việt không như kỳ vọng | Tokenization, dấu, chuẩn hóa và từ ghép | Chuẩn hóa/analyze ở ứng dụng hoặc search service |
| Boolean query trả quá nhiều/ít | Toán tử hoặc stopword/tokenization | Validate grammar và test từng query pattern |
| Relevance thay đổi sau import | Corpus và thống kê token thay đổi | Đánh giá lại ranking trên query set chuẩn |
| UPDATE/INSERT chậm sau thêm FULLTEXT | Chi phí duy trì inverted index | Giảm index trùng, batch và đo write workload |
| Search engine ngoài thiếu dữ liệu mới | Pipeline đồng bộ bị lag/lỗi | Outbox/CDC checkpoint, retry, dead-letter và rebuild |
| Người dùng thấy tài liệu tenant khác | Thiếu authorization filter | Bắt buộc tenant/visibility filter ở server-side SQL |

## 22. Bài tập thực hành

1. Tạo bảng `knowledge_document` InnoDB với title, summary, content, language và visibility.
2. Tạo FULLTEXT index trên `(title, content)` và thử natural language mode.
3. Thử boolean query `+mysql -deprecated` và phrase query `"transaction isolation"`.
4. So sánh FULLTEXT với `LIKE '%mysql%'` bằng EXPLAIN và latency trên corpus tăng dần.
5. Tạo index title riêng; so sánh relevance của `MATCH(title)` và `MATCH(title, content)`.
6. Kiểm tra `innodb_ft_min_token_size` và stopword; chọn một từ ngắn để xác nhận hành vi.
7. Trong lab riêng, thay stopword/token size, rebuild index và so sánh kết quả trước/sau.
8. Tạo bảng dùng `WITH PARSER ngram`; thử query CJK với nhiều `ngram_token_size` trong môi trường thử nghiệm.
9. Tạo bộ 20 query tiếng Việt gồm từ có dấu, không dấu, từ ghép, phrase và thuật ngữ ngắn; gán nhãn kết quả liên quan.
10. Thêm filter `language_code`, `visibility` và tenant; xác minh không rò dữ liệu giữa tenant.
11. Dùng `EXPLAIN ANALYZE` và ghi lại actual rows/time cho các truy vấn phổ biến.
12. Đo write latency và index size trước/sau khi thêm FULLTEXT index thứ hai.
13. Thiết kế outbox/CDC đồng bộ một document sang search engine và mô phỏng worker retry.
14. Viết decision record chọn FULLTEXT, B-tree, LIKE hoặc search engine cho một chức năng cụ thể.

## 23. Checklist trước khi phát hành

- [ ] Đã phân loại đúng yêu cầu exact, prefix, substring, term, phrase, fuzzy hoặc autocomplete.
- [ ] FULLTEXT chỉ dùng cho nội dung văn bản cần token search.
- [ ] Engine và charset/collation được chọn có chủ đích.
- [ ] Danh sách cột trong MATCH khớp FULLTEXT index.
- [ ] Đã kiểm tra natural language/boolean/phrase mode bằng query thật.
- [ ] Đã đánh giá stopword, token size và parser theo từng ngôn ngữ.
- [ ] Đã cân nhắc ngram cho ngôn ngữ không phân tách từ bằng khoảng trắng.
- [ ] Filter tenant, visibility và authorization luôn chạy ở server side.
- [ ] Có ranking, tie-breaker và giới hạn pagination rõ ràng.
- [ ] Đã kiểm tra EXPLAIN/EXPLAIN ANALYZE và latency p95/p99.
- [ ] Đã đo index size, write overhead, rebuild time và replication lag.
- [ ] Có relevance test set và precision/recall hoặc NDCG phù hợp.
- [ ] Có quy trình đồng bộ/rebuild nếu dùng search service ngoài.
- [ ] Query được bind parameter và boolean grammar được validate.
- [ ] Có monitoring, giới hạn query và runbook khi index lỗi/lag.

## 24. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể nhận một yêu cầu tìm kiếm thực tế, phân loại kiểu matching, chọn cơ chế và engine phù hợp, thiết kế FULLTEXT index đúng cột, viết truy vấn natural language/boolean/phrase, giải thích ảnh hưởng của tokenization/stopword/ngôn ngữ, kết hợp filter có cấu trúc an toàn và chứng minh chất lượng bằng test relevance cùng benchmark. Bạn cũng cần biết khi nào MySQL FULLTEXT không đáp ứng được và cách đồng bộ MySQL sang một search engine chuyên dụng.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Full-Text Search Functions](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search.html)
- [MySQL 8.4 Reference Manual — Natural Language Full-Text Searches](https://dev.mysql.com/doc/refman/8.4/en/fulltext-natural-language.html)
- [MySQL 8.4 Reference Manual — Boolean Full-Text Searches](https://dev.mysql.com/doc/refman/8.4/en/fulltext-boolean.html)
- [MySQL 8.4 Reference Manual — Full-Text Stopwords](https://dev.mysql.com/doc/refman/8.4/en/fulltext-stopwords.html)
- [MySQL 8.4 Reference Manual — ngram Full-Text Parser](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html)
- [MySQL 8.4 Reference Manual — Fine-Tuning MySQL Full-Text Search](https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html)
