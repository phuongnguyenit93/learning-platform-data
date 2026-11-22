# Bài toán tìm kiếm văn bản và khác biệt với LIKE

Tìm kiếm văn bản xuất hiện trong nhiều chức năng ứng dụng: tìm bài viết theo nội dung, tìm sản phẩm theo tên/mô tả, tra cứu tài liệu, lọc bình luận hoặc tìm thông tin trong mô tả sự kiện. Dù đều có thể bắt đầu bằng `LIKE`, không phải mọi bài toán tìm kiếm đều là bài toán so khớp chuỗi.

`LIKE` kiểm tra một chuỗi có khớp với pattern hay không. Nó phù hợp với tìm chuỗi con, tiền tố hoặc mẫu ký tự đơn giản. Full-text search (tìm kiếm toàn văn) phân tích văn bản thành token/term, lập chỉ mục từ và hỗ trợ tìm theo từ, cụm từ, toán tử tìm kiếm cùng điểm liên quan (relevance). Hai cách có ngữ nghĩa và access path khác nhau.

Chọn đúng cơ chế phụ thuộc vào câu hỏi của người dùng: cần tìm đúng một đoạn ký tự nằm ở bất kỳ vị trí nào, cần gợi ý theo tiền tố, hay cần tìm tài liệu nói về một chủ đề và xếp hạng kết quả? `LIKE '%term%'` không phải một full-text engine; ngược lại, FULLTEXT không thay thế mọi phép tìm chuỗi con.

## 1. Hai bài toán khác nhau

Giả sử bảng `articles` chứa tiêu đề và nội dung bài viết. Người dùng nhập `transaction`.

Với `LIKE`, database kiểm tra chuỗi có chứa đúng dãy ký tự `transaction` theo collation hay không. Nó không hiểu đây là một từ, không phân tích mức liên quan và không tự xếp hạng bài viết.

Với full-text search, MySQL phân tích nội dung thành các token, lưu cấu trúc chỉ mục toàn văn và tìm các tài liệu có token phù hợp. Chế độ natural language có thể trả về điểm relevance để xếp hạng kết quả.

| Câu hỏi | Cơ chế thường phù hợp |
| --- | --- |
| Tên mã có chứa chuỗi `AB-12` ở giữa không? | `LIKE '%AB-12%'` hoặc phép tìm chuỗi chuyên biệt |
| Tên người dùng bắt đầu bằng `nguy` không? | `LIKE 'nguy%'` với index phù hợp |
| Bài viết nào nói về transaction và isolation? | FULLTEXT |
| Tìm chính xác một cụm từ trong nội dung? | FULLTEXT phrase search hoặc `LIKE` nếu cần khớp chuỗi nguyên văn |
| Tìm mọi vị trí xuất hiện của một đoạn ký tự bất kỳ, kể cả giữa từ? | `LIKE '%...%'` hoặc hệ thống substring/ngram chuyên dụng |
| Xếp hạng tài liệu theo mức liên quan đến nhiều từ khóa? | FULLTEXT hoặc search engine chuyên dụng |

Trước khi viết SQL, hãy xác định rõ “khớp” nghĩa là khớp ký tự, tiền tố, từ đã tách, cụm từ hay chủ đề.

## 2. LIKE: so khớp pattern ký tự

`LIKE` dùng hai wildcard chính:

- `%`: khớp với không, một hoặc nhiều ký tự.
- `_`: khớp đúng một ký tự.

Ví dụ:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'wireless%';
```

Truy vấn tìm tên sản phẩm bắt đầu bằng `wireless`.

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%wireless%';
```

Truy vấn tìm chuỗi `wireless` ở bất kỳ vị trí nào trong tên sản phẩm.

```sql
SELECT product_id, product_name
FROM products
WHERE product_code LIKE 'AB_12';
```

Pattern này khớp `AB` + một ký tự bất kỳ + `12`; `_` không đại diện cho dấu gạch dưới literal.

`LIKE` không tự tách từ, không bỏ stopword, không tính relevance và không hiểu quan hệ ngữ nghĩa giữa các từ. Nó chỉ áp dụng quy tắc so khớp pattern theo charset/collation của biểu thức.

## 3. Escape ký tự wildcard khi cần tìm literal

Nếu người dùng cần tìm chính ký tự `%` hoặc `_`, phải escape chúng. Ví dụ tìm mã có dấu gạch dưới literal:

```sql
SELECT product_id, product_code
FROM products
WHERE product_code LIKE '%\\_%' ESCAPE '\\';
```

Trong ví dụ này, backslash là ký tự escape, nên `\\_` trong chuỗi SQL biểu diễn dấu gạch dưới literal; `%` ở hai đầu vẫn là wildcard. Có thể chọn một ký tự escape khác để tránh khác biệt do `NO_BACKSLASH_ESCAPES` SQL mode.

Khi xây dựng truy vấn từ input người dùng, đừng nối input vào SQL. Dùng prepared statement và escape wildcard theo đúng ngữ nghĩa tìm kiếm mà sản phẩm muốn cung cấp. Parameter binding ngăn SQL injection, nhưng tự nó không biến `%` và `_` thành ký tự literal.

## 4. Collation ảnh hưởng kết quả LIKE

So sánh chuỗi chịu ảnh hưởng charset và collation. Với collation không phân biệt hoa/thường (case-insensitive), `LIKE 'mysql%'` có thể khớp `MySQL Server`; với collation phân biệt hoa/thường, kết quả khác. Accent sensitivity cũng phụ thuộc collation.

Kiểm tra collation:

```sql
SHOW FULL COLUMNS FROM products;

SELECT
    COLLATION(product_name),
    CHARSET(product_name)
FROM products
LIMIT 1;
```

Không giả định mọi cột text đều có cùng quy tắc so sánh. Khi yêu cầu tìm kiếm phân biệt hoa/thường hoặc dấu, xác định collation phù hợp và kiểm tra bằng dữ liệu thực tế.

## 5. LIKE và khả năng dùng B-tree index

Với B-tree index thông thường trên cột chuỗi, pattern có tiền tố cố định có thể cho phép range lookup:

```sql
CREATE INDEX idx_products_name
ON products (product_name);

SELECT product_id, product_name
FROM products
WHERE product_name LIKE 'wireless%';
```

Optimizer có thể dùng index vì phần đầu pattern là chuỗi cố định. Khả năng dùng index còn phụ thuộc kiểu dữ liệu, collation, biểu thức và ước lượng chi phí; hãy xác nhận bằng `EXPLAIN`.

Ngược lại:

```sql
SELECT product_id, product_name
FROM products
WHERE product_name LIKE '%wireless%';
```

Wildcard ở đầu pattern khiến B-tree không xác định được một khoảng liên tiếp bắt đầu từ tiền tố nào. Truy vấn thường phải kiểm tra nhiều hàng (thường là table scan hoặc index scan). Index trên cột vẫn có thể được chọn trong một số trường hợp đặc biệt, nhưng không thể dùng nó như một range lookup theo tiền tố.

Điều này không có nghĩa `LIKE '%...%'` luôn sai. Với bảng nhỏ, lượng dữ liệu ít hoặc truy vấn hiếm, cách này có thể đủ đơn giản. Vấn đề xuất hiện khi bảng lớn, truy vấn thường xuyên và số hàng cần kiểm tra cao.

## 6. LIKE không xếp hạng độ liên quan

Giả sử ba bài viết đều chứa từ `transaction`:

- Bài A có từ này trong tiêu đề và xuất hiện 20 lần trong nội dung.
- Bài B chỉ nhắc một lần trong phần cuối.
- Bài C có chuỗi `transaction` trong một đoạn code dài.

Một điều kiện `LIKE '%transaction%'` chỉ xác định hàng nào có chuỗi phù hợp. Nếu không thêm logic riêng, nó không biết bài A đáng hiển thị trước bài B.

Có thể tự tạo điểm bằng `CASE`, số lần xuất hiện hoặc trọng số tiêu đề, nhưng đó là logic xếp hạng do ứng dụng/SQL xây dựng. FULLTEXT cung cấp cơ chế tìm token và điểm relevance tích hợp phù hợp hơn với bài toán tìm tài liệu theo từ khóa.

## 7. Full-text search là gì?

Full-text search phân tích văn bản thành các đơn vị tìm kiếm (token/term), lập chỉ mục các token và ánh xạ chúng về tài liệu/hàng chứa token. Khi tìm, MySQL tra cứu chỉ mục toàn văn thay vì so sánh một pattern ký tự trên mọi giá trị chuỗi.

Full-text index khác B-tree index:

- B-tree sắp xếp giá trị khóa để hỗ trợ equality, range và prefix lookup.
- FULLTEXT lập chỉ mục các từ/token xuất hiện trong văn bản.
- Một token có thể xuất hiện ở nhiều hàng; chỉ mục toàn văn lưu quan hệ giữa token và tài liệu.
- Truy vấn FULLTEXT có thể tính relevance để xếp hạng kết quả.
- Tokenization, stopword và giới hạn độ dài token ảnh hưởng từ nào được đưa vào chỉ mục.

FULLTEXT hướng đến tìm kiếm nội dung ngôn ngữ tự nhiên. Nó không phải chỉ mục cho mọi chuỗi con tùy ý và không thay thế khóa chính, unique index hoặc B-tree index dùng cho JOIN.

## 8. FULLTEXT index trong MySQL

MySQL hỗ trợ `FULLTEXT` index trên cột `CHAR`, `VARCHAR` và `TEXT`. InnoDB hỗ trợ full-text index từ MySQL 5.6.4; MyISAM cũng hỗ trợ FULLTEXT. Với ứng dụng mới, InnoDB thường là lựa chọn mặc định vì transaction và khả năng phục hồi, nhưng cần kiểm tra phiên bản và engine đang triển khai.

Ví dụ tạo bảng bài viết có FULLTEXT index ghép trên tiêu đề và nội dung:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    published_at DATETIME NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_published (published_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Nếu bảng đã tồn tại:

```sql
ALTER TABLE articles
ADD FULLTEXT INDEX ft_articles_title_body (title, body);
```

FULLTEXT index ghép cho phép tìm trên tập cột được lập chỉ mục. Danh sách cột trong `MATCH()` cần tương ứng với danh sách cột của FULLTEXT index được dùng. Nếu cần tìm riêng `title`, cân nhắc tạo FULLTEXT index riêng trên `title` thay vì giả định index `(title, body)` có thể thay thế mọi index con.

## 9. MATCH() AGAINST(): truy vấn full-text

Cú pháp cơ bản:

```sql
MATCH (col1, col2, ...) AGAINST (search_text [search_modifier])
```

Ví dụ tìm bài viết về transaction isolation:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction isolation') AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation')
ORDER BY relevance DESC;
```

`MATCH() AGAINST()` trả điểm relevance; điều kiện trong `WHERE` lọc các hàng phù hợp và `ORDER BY relevance DESC` ưu tiên hàng có điểm cao hơn. Điểm này là thước đo nội bộ của full-text engine, không phải xác suất nội dung đúng hay mức độ hài lòng của người dùng.

`MATCH()` cần dùng đúng các cột đã được khai báo trong FULLTEXT index tương ứng. Nếu không có index phù hợp, truy vấn có thể báo lỗi thay vì tự quét chuỗi như LIKE.

## 10. Natural language mode

Nếu không chỉ định modifier, MySQL dùng `IN NATURAL LANGUAGE MODE`:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
```

Natural language mode xem input là truy vấn ngôn ngữ tự nhiên gồm các từ cần tìm. MySQL tìm tài liệu chứa các token phù hợp và tính relevance dựa trên thống kê của tập tài liệu/index.

Đây là chế độ phù hợp cho ô tìm kiếm nội dung phổ thông. Tuy nhiên, không nên diễn giải nó như một bộ hiểu ngữ nghĩa: MySQL không tự hiểu ý định, từ đồng nghĩa hoặc quan hệ khái niệm như một hệ thống search/AI chuyên biệt.

## 11. Boolean mode

Boolean mode cho phép dùng toán tử để điều khiển cách kết hợp token:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('+transaction +isolation -oracle' IN BOOLEAN MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+transaction +isolation -oracle' IN BOOLEAN MODE)
ORDER BY relevance DESC;
```

Một số toán tử thường gặp:

| Toán tử | Ý nghĩa khái quát |
| --- | --- |
| `+word` | Từ phải xuất hiện |
| `-word` | Loại tài liệu có từ này |
| `word` | Từ tùy chọn, có thể đóng góp relevance |
| `"phrase"` | Tìm cụm từ theo thứ tự token |
| `word*` | Tiền tố token; dấu `*` đặt ở cuối từ |
| `>word`, `<word` | Tăng/giảm đóng góp relevance của từ |
| `( ... )` | Nhóm biểu thức để điều khiển kết hợp |

Ví dụ tìm cụm từ:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('"transaction isolation"' IN BOOLEAN MODE);
```

Boolean mode phù hợp khi sản phẩm cần từ bắt buộc, từ loại trừ hoặc prefix token. Cú pháp boolean của MySQL có quy tắc riêng; không giả định mọi toán tử của Elasticsearch/Lucene đều có cùng ý nghĩa.

## 12. LIKE và FULLTEXT: so sánh trực tiếp

| Tiêu chí | `LIKE` | `FULLTEXT` |
| --- | --- | --- |
| Đơn vị so khớp | Chuỗi ký tự theo pattern | Token/term được parser tách ra |
| Tìm chuỗi con giữa từ | Có thể dùng `%term%` | Không phải mục tiêu của FULLTEXT mặc định |
| Tìm tiền tố | `term%` có thể dùng B-tree | Boolean mode có token prefix `term*` |
| Stopword | Không tự loại stopword | Có thể bỏ qua stopword theo cấu hình/parser |
| Từ quá ngắn | Vẫn so khớp nếu pattern phù hợp | Có thể bị loại theo min token size |
| Relevance score | Không có sẵn | Có điểm relevance |
| Phrase search | So khớp chuỗi literal bằng pattern | Boolean phrase search theo token |
| Index | B-tree có thể hỗ trợ equality/range/prefix | Cần FULLTEXT index |
| Kết quả | Hàng khớp/không khớp pattern | Hàng có token phù hợp, có thể xếp hạng |
| Use case | Mã, tiền tố, chuỗi con, pattern đơn giản | Bài viết, mô tả, tài liệu và nội dung nhiều từ |

Không có cơ chế nào tốt hơn trong mọi trường hợp. Chọn theo semantics tìm kiếm mà ứng dụng cần cung cấp.

## 13. Tokenization: MySQL tách từ như thế nào?

Full-text parser phân tích văn bản thành token trước khi lập chỉ mục và tìm kiếm. Parser mặc định dùng quy tắc phân tách từ dựa trên ký tự phân cách. Dấu câu và khoảng trắng thường tạo ranh giới token; một số ký tự thuộc từ phụ thuộc charset/parser.

Ví dụ nội dung:

```text
MySQL transaction isolation protects concurrent updates.
```

Parser có thể lập chỉ mục các token như `mysql`, `transaction`, `isolation`, `protects`, `concurrent`, `updates`, sau khi áp dụng quy tắc độ dài và stopword.

Vì tokenization, FULLTEXT tìm từ đã được tách chứ không tìm mọi dãy ký tự con. Tìm `trans` có thể không tìm thấy token `transaction` trong natural language mode. Boolean prefix `trans*` là một cơ chế khác, chỉ tìm token bắt đầu bằng tiền tố đó khi cú pháp và index cho phép.

## 14. Stopword và độ dài token tối thiểu

Stopword là những từ bị loại khỏi full-text index hoặc bị bỏ qua khi tìm kiếm, thường vì chúng xuất hiện quá phổ biến và ít giúp phân biệt tài liệu. Ngoài ra, parser có giới hạn độ dài token tối thiểu/tối đa.

Các biến cấu hình phổ biến:

| Engine | Giới hạn token tối thiểu | Giới hạn token tối đa |
| --- | --- | --- |
| InnoDB | `innodb_ft_min_token_size` (mặc định thường là 3) | `innodb_ft_max_token_size` (mặc định thường là 84) |
| MyISAM | `ft_min_word_len` (mặc định thường là 4) | `ft_max_word_len` (mặc định thường là 84) |

Giá trị thực tế cần kiểm tra trên server:

```sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
```

Nếu người dùng cần tìm từ ngắn như `SQL`, `C`, `R`, hoặc mã ngắn, cần xem token size và stopword. Thay đổi cấu hình full-text thường yêu cầu khởi động lại server và rebuild FULLTEXT index để nội dung được lập chỉ mục theo quy tắc mới.

Không nên giảm min token size tùy tiện: index có thể lớn hơn đáng kể và chứa nhiều token ít giá trị. Hãy kiểm thử workload tìm kiếm và kế hoạch vận hành rebuild trước khi thay đổi.

## 15. Stopword ảnh hưởng kết quả như thế nào?

Nếu một từ nằm trong stopword list, người dùng có thể nhập từ đó nhưng full-text search không xử lý nó như token thông thường. Vì vậy, tìm kiếm một từ rất phổ biến hoặc một từ bị cấu hình loại bỏ có thể không trả kết quả mong đợi.

InnoDB có cấu hình stopword riêng, gồm danh sách mặc định và khả năng dùng bảng stopword tùy chỉnh. MyISAM có cơ chế cấu hình stopword riêng. Không giả định hai engine có cùng cấu hình hoặc cùng kết quả.

Khi domain có từ chuyên ngành phổ biến nhưng quan trọng, ví dụ `order`, `status`, `select` hoặc tên sản phẩm ngắn, hãy kiểm tra stopword list và cân nhắc cấu hình riêng. Thay đổi stopword cũng cần rebuild index để token bị loại trước đó được đưa vào chỉ mục.

## 16. Tìm kiếm tiếng Việt và giới hạn parser mặc định

Tìm kiếm tiếng Việt cần được kiểm thử bằng dữ liệu thật. Tiếng Việt có nhiều từ ghép gồm các âm tiết được viết cách nhau bằng khoảng trắng; parser mặc định có thể xử lý từng phần theo ranh giới token, không nhất thiết nhận biết một từ ghép theo từ điển ngôn ngữ.

Ví dụ, cụm `cơ sở dữ liệu` có thể được phân tích thành các token riêng. Điều này có thể phù hợp với tìm từng âm tiết nhưng không tương đương với một bộ phân tích từ tiếng Việt có hiểu biết từ vựng, dấu, biến thể hoặc từ đồng nghĩa.

Các điểm cần kiểm tra:

- Dữ liệu có dấu và không dấu có cần được xem là tương đương không?
- Người dùng tìm cả cụm hay chỉ một từ/âm tiết?
- Từ ngắn có bị loại bởi min token size hoặc stopword không?
- Collation có xử lý hoa/thường và dấu theo yêu cầu không?
- Có cần stemming, synonym, typo tolerance hoặc ranking theo domain không?

MySQL có ngram parser, thường dùng cho ngôn ngữ không có ranh giới từ bằng khoảng trắng như tiếng Trung, Nhật và Hàn. Ngram chia văn bản thành các chuỗi ký tự có độ dài cấu hình; nó không tự trở thành bộ hiểu ngữ nghĩa tiếng Việt. Nếu sản phẩm cần phân đoạn từ tiếng Việt, sửa lỗi chính tả, đồng nghĩa hoặc ranking phức tạp, cân nhắc pipeline phân tích riêng hoặc search engine chuyên dụng.

## 17. Một ví dụ cùng dữ liệu, hai semantics

Giả sử `articles.body` chứa:

```text
The database transaction protects the account balance.
```

So sánh:

```sql
-- Tìm đúng chuỗi ký tự "trans" ở bất kỳ vị trí nào.
SELECT article_id, title
FROM articles
WHERE body LIKE '%trans%';

-- Tìm token "transaction" trong full-text index.
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction' IN NATURAL LANGUAGE MODE);

-- Tìm token có tiền tố "trans" trong boolean mode.
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('trans*' IN BOOLEAN MODE);
```

Ba truy vấn có thể trả kết quả khác nhau:

- `LIKE '%trans%'` khớp chuỗi `transaction` vì chứa dãy ký tự `trans`.
- Natural language search cho `transaction` tìm token `transaction`, không mặc nhiên tìm mọi từ có tiền tố `trans`.
- Boolean `trans*` tìm token có tiền tố `trans` nếu token được lập chỉ mục và không bị loại bởi cấu hình.

Đây là lý do cần xác định rõ hợp đồng tìm kiếm trước khi chọn SQL.

## 18. Kết hợp điều kiện quan hệ với FULLTEXT

Ứng dụng thường cần lọc kết quả theo tenant, trạng thái hoặc thời gian cùng với từ khóa:

```sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('mysql indexing' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('mysql indexing' IN NATURAL LANGUAGE MODE)
  AND published_at >= '2026-01-01'
ORDER BY relevance DESC, published_at DESC
LIMIT 20;
```

FULLTEXT tìm nội dung theo token; điều kiện quan hệ lọc phạm vi kết quả theo ngày/trạng thái/tenant. Thiết kế B-tree index cho các điều kiện quan hệ vẫn có ý nghĩa, nhưng optimizer sẽ chọn kế hoạch kết hợp dựa trên chi phí. Không giả định một index đơn có thể giải quyết toàn bộ truy vấn.

Với dữ liệu đa tenant, điều kiện `tenant_id` phải được áp dụng như một ràng buộc bảo mật/ủy quyền rõ ràng, không chỉ dựa vào từ khóa. Full-text search không thay thế authorization.

## 19. Kiểm tra execution plan và chi phí

Dùng `EXPLAIN` để xem cách MySQL dự định thực hiện truy vấn:

```sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE);
```

So sánh với truy vấn `LIKE`:

```sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE body LIKE '%transaction%';
```

Quan sát access type, key, rows ước lượng và Extra. FULLTEXT cần index phù hợp; `LIKE` có wildcard đầu thường phải kiểm tra nhiều hàng. Kết quả thực tế còn phụ thuộc số tài liệu, phân bố token, độ phổ biến từ khóa và điều kiện lọc bổ sung.

Khi phù hợp với phiên bản MySQL, dùng `EXPLAIN ANALYZE` cho truy vấn SELECT để xem actual rows và thời gian iterator. Chạy benchmark với dữ liệu và tham số đại diện; một từ khóa phổ biến có thể trả về nhiều tài liệu hơn một từ khóa hiếm.

## 20. Khi nào LIKE vẫn là lựa chọn đúng?

`LIKE` vẫn phù hợp khi:

- Bảng nhỏ và truy vấn không thường xuyên.
- Tìm mã định danh, mã sản phẩm hoặc chuỗi có cấu trúc cố định.
- Tìm tiền tố để autocomplete (`prefix%`) với B-tree index.
- Cần tìm substring literal ở giữa chuỗi (`%substring%`).
- Cần khớp một pattern ký tự đơn giản chứ không phải từ ngữ.
- Kết quả chỉ cần đúng/sai, không cần relevance ranking.

Ví dụ tìm email kết thúc bằng domain:

```sql
SELECT user_id, email
FROM users
WHERE email LIKE '%@example.com';
```

Pattern này là phép tìm chuỗi theo ký tự; FULLTEXT không phải công cụ phù hợp để kiểm tra hậu tố email. Nếu cần hiệu năng cao cho hậu tố hoặc substring, cân nhắc cột chuẩn hóa, reverse index hoặc cấu trúc tìm kiếm chuyên biệt sau khi đo workload.

## 21. Khi nào FULLTEXT phù hợp?

FULLTEXT thường phù hợp khi:

- Tìm từ khóa trong nội dung dài như bài viết, mô tả, tài liệu hoặc bình luận.
- Cần kết quả theo mức relevance.
- Cần tìm nhiều token hoặc cụm từ.
- Dữ liệu có cấu trúc văn bản và parser có thể tách token phù hợp.
- Muốn tìm kiếm tích hợp ngay trong MySQL mà không triển khai hệ thống search riêng.

FULLTEXT có thể không đủ khi cần:

- Tìm substring tùy ý giữa token.
- Fuzzy matching, sửa lỗi chính tả hoặc typo tolerance nâng cao.
- Synonym, stemming hoặc semantic search theo domain.
- Phân tích ngôn ngữ phức tạp mà parser mặc định không hỗ trợ.
- Ranking tùy biến nhiều tín hiệu như độ mới, độ phổ biến, quyền truy cập và cá nhân hóa.

Trong các trường hợp đó, MySQL có thể giữ dữ liệu giao dịch chuẩn, còn một search engine chuyên dụng đảm nhiệm indexing/ranking; cần thiết kế đồng bộ, eventual consistency và xử lý xóa/cập nhật tài liệu.

## 22. Những hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| `LIKE '%word%'` là full-text search | Đây là pattern matching ký tự | Dùng FULLTEXT khi cần tìm token và relevance |
| FULLTEXT tìm mọi substring | FULLTEXT tìm token theo parser | Dùng LIKE/ngram/search engine cho substring |
| `LIKE 'prefix%'` và `LIKE '%prefix%'` giống nhau về index | Prefix có thể dùng B-tree range; leading wildcard thường không | Kiểm tra EXPLAIN |
| FULLTEXT tự hiểu nghĩa câu | Parser chủ yếu phân tích token và relevance thống kê | Dùng search engine/semantic layer nếu cần hiểu ngữ nghĩa |
| Từ nào cũng được index | Stopword và token-size limit có thể loại từ | Kiểm tra cấu hình và dữ liệu index |
| FULLTEXT có thể dùng cho mọi cột | Chỉ hỗ trợ CHAR, VARCHAR, TEXT và cần FULLTEXT index | Thiết kế cột/index đúng loại |
| FULLTEXT index thay thế B-tree | Hai index giải quyết hai access pattern khác nhau | Duy trì B-tree cho JOIN/filter/range phù hợp |
| Boolean mode dùng cú pháp Lucene | MySQL có cú pháp boolean riêng | Theo đúng toán tử MySQL |
| Tìm tiếng Việt mặc định luôn đúng từ ghép | Parser không nhất thiết phân đoạn theo từ điển tiếng Việt | Kiểm thử tokenization hoặc dùng parser/search service phù hợp |
| MATCH() có thể dùng tùy ý một phần cột của index ghép | Cột MATCH cần tương ứng với FULLTEXT index | Tạo index phù hợp cho từng tập cột cần tìm |

## 23. Quy trình chọn và triển khai cơ chế tìm kiếm

1. Xác định semantics: substring, prefix, token, phrase hay relevance.
2. Thu thập ví dụ truy vấn thật và kết quả người dùng mong đợi.
3. Kiểm tra charset/collation và ngôn ngữ dữ liệu.
4. Nếu dùng LIKE, xác định pattern có leading wildcard không và B-tree có thể hỗ trợ không.
5. Nếu dùng FULLTEXT, chọn cột `CHAR`/`VARCHAR`/`TEXT` và tạo FULLTEXT index.
6. Kiểm tra parser, stopword, min/max token size và từ ngắn quan trọng.
7. Chọn natural language hoặc boolean mode theo trải nghiệm tìm kiếm.
8. Kết hợp filter tenant/trạng thái/thời gian và bảo đảm authorization.
9. Dùng `EXPLAIN`/`EXPLAIN ANALYZE` và benchmark với từ khóa phổ biến/hiếm.
10. Đo latency, số kết quả, relevance và chi phí cập nhật index.
11. Kiểm thử insert/update/delete, rebuild index và quy trình triển khai cấu hình.
12. Nếu yêu cầu ngôn ngữ/ranking vượt khả năng FULLTEXT, cân nhắc search engine chuyên dụng.

## 24. Bài tập thực hành

1. Tạo bảng `articles` có `title`, `body` và FULLTEXT index ghép.
2. Chèn ít nhất 20 bài viết với từ khóa phổ biến, hiếm, từ ngắn và cụm từ.
3. So sánh `LIKE '%transaction%'` với FULLTEXT natural language mode.
4. So sánh `LIKE 'trans%'` với boolean prefix `trans*`.
5. Tìm một cụm từ bằng `LIKE` và boolean phrase search; ghi lại trường hợp kết quả khác nhau.
6. Dùng `EXPLAIN` cho `LIKE 'prefix%'` và `LIKE '%prefix%'`; so sánh access path.
7. Dùng `EXPLAIN` cho `MATCH() AGAINST()` và xác nhận FULLTEXT index được dùng.
8. Thử boolean operators `+`, `-`, `>`, `<`, `*` và nhóm ngoặc.
9. Kiểm tra min token size và stopword; thử tìm `SQL`, `C` hoặc từ rất phổ biến.
10. Thử truy vấn tiếng Việt có dấu/không dấu và cụm nhiều âm tiết; ghi nhận giới hạn parser.
11. Kết hợp FULLTEXT với filter `tenant_id`, `published_at` và sắp xếp relevance.
12. Viết đề xuất chọn LIKE, FULLTEXT hay search engine cho ba chức năng: autocomplete, tìm mã sản phẩm và tìm bài viết.

## 25. Ghi nhớ

`LIKE` so khớp chuỗi theo pattern: `%` khớp không hoặc nhiều ký tự, `_` khớp một ký tự. B-tree có thể hỗ trợ pattern có tiền tố cố định như `abc%`, nhưng pattern bắt đầu bằng `%` như `%abc%` thường không thể dùng range lookup. LIKE không tách từ và không xếp hạng relevance; kết quả còn phụ thuộc collation.

FULLTEXT lập chỉ mục token trong cột `CHAR`, `VARCHAR` hoặc `TEXT`; truy vấn bằng `MATCH(...) AGAINST(...)`. Natural language mode phù hợp tìm nội dung theo từ khóa và relevance; boolean mode hỗ trợ từ bắt buộc/loại trừ, phrase và token prefix. Parser, stopword, min/max token size và ngôn ngữ ảnh hưởng kết quả; từ ngắn hoặc từ phổ biến có thể bị loại. FULLTEXT không tìm mọi substring và không phải semantic search. Hãy chọn theo semantics: LIKE cho pattern ký tự/prefix/substring; FULLTEXT cho tìm token trong văn bản; search engine chuyên dụng khi cần phân tích ngôn ngữ, typo, synonym hoặc ranking phức tạp.
