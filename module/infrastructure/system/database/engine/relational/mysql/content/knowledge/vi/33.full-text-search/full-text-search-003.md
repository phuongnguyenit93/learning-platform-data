# MATCH AGAINST trong natural language mode

Full-text search trong MySQL giúp tìm từ hoặc cụm từ đã được bộ phân tích văn bản tách thành token trong các cột văn bản. Với natural language mode, câu tìm kiếm được hiểu như ngôn ngữ tự nhiên: MySQL phân tích các từ, tìm tài liệu có từ phù hợp và tính điểm liên quan để xếp hạng kết quả. Cú pháp trung tâm là MATCH(...) AGAINST(...).

Trong module DATABASE_MYSQL, bài học này tập trung vào cách tạo FULLTEXT index, viết MATCH AGAINST ở natural language mode, đọc relevance score, hiểu tokenization và stopword, cùng các khác biệt quan trọng giữa InnoDB và MyISAM. Natural language mode phù hợp với tìm kiếm nội dung dạng từ khóa; nó không phải phép so khớp chuỗi con hay tìm chính xác một cụm từ theo thứ tự.

## 1. FULLTEXT search hoạt động như thế nào?

FULLTEXT index lưu cấu trúc tra cứu dựa trên token được trích xuất từ nội dung văn bản. Khi chạy MATCH(...) AGAINST(...), MySQL phân tích chuỗi tìm kiếm, tra các token trong FULLTEXT index và tính mức độ liên quan giữa tài liệu với truy vấn.

Một quy trình tổng quát:

1. Tạo FULLTEXT index trên một hoặc nhiều cột văn bản.
2. MySQL phân tích nội dung cột thành token và xây dựng chỉ mục.
3. Ứng dụng gửi chuỗi tìm kiếm cho AGAINST.
4. MySQL phân tích chuỗi truy vấn theo parser và cấu hình full-text.
5. MATCH tìm tài liệu phù hợp và trả điểm relevance.
6. Ứng dụng lọc và sắp xếp kết quả theo điểm hoặc tiêu chí bổ sung.

FULLTEXT index khác B-tree index thông thường. B-tree phù hợp với phép so sánh giá trị, khoảng và thứ tự; FULLTEXT index phục vụ tìm kiếm token trong văn bản.

## 2. Tạo bảng và FULLTEXT index

FULLTEXT index của MySQL áp dụng cho các cột CHAR, VARCHAR hoặc TEXT. Ví dụ bảng bài viết:

~~~sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    status VARCHAR(20) NOT NULL DEFAULT 'PUBLISHED',
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_status_published (status, published_at)
) ENGINE=InnoDB;
~~~

Chỉ mục ft_articles_title_body là FULLTEXT index ghép trên title và body. Index status/published_at là B-tree index thông thường để hỗ trợ điều kiện lọc và sắp xếp theo trạng thái/thời điểm nếu optimizer thấy có lợi.

Có thể thêm FULLTEXT index sau khi bảng đã được tạo:

~~~sql
ALTER TABLE articles
    ADD FULLTEXT INDEX ft_articles_title_body (title, body);
~~~

Không tạo lại index nếu bảng đã có index cùng tên. Khi triển khai migration, hãy kiểm tra schema hiện tại và dùng đúng một trong hai cách tạo index.

## 3. Dữ liệu ví dụ

Thêm một số bài viết:

~~~sql
INSERT INTO articles (title, body, status)
VALUES
(
    'MySQL transaction basics',
    'A transaction groups database changes. Commit saves changes and rollback cancels uncommitted work.',
    'PUBLISHED'
),
(
    'Understanding database indexes',
    'An index helps MySQL locate rows efficiently. A fulltext index supports searching words in text documents.',
    'PUBLISHED'
),
(
    'Transaction isolation in InnoDB',
    'InnoDB provides transaction isolation levels. Consistent reads and locking reads have different behavior.',
    'PUBLISHED'
),
(
    'Text search and relevance',
    'Fulltext search analyzes words and calculates relevance scores for matching documents.',
    'DRAFT'
);
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT article_id, title, status
FROM articles
ORDER BY article_id;
~~~

Các ví dụ tiếp theo dùng bảng này. Kết quả thực tế còn phụ thuộc parser, stopword list, minimum token size, collation và phiên bản MySQL.

## 4. Cú pháp MATCH AGAINST trong natural language mode

Cú pháp:

~~~sql
MATCH (col_name [, col_name] ...)
AGAINST (expr [search_modifier])
~~~

Với natural language mode:

~~~sql
MATCH (title, body)
AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE)
~~~

IN NATURAL LANGUAGE MODE có thể được ghi tường minh để người đọc hiểu ý định. Nếu bỏ search modifier, natural language mode là chế độ mặc định.

Danh sách cột trong MATCH phải tương ứng với danh sách cột của một FULLTEXT index trên bảng theo yêu cầu của engine. Trong ví dụ, MATCH(title, body) sử dụng ft_articles_title_body. Nếu muốn tìm chỉ trên title, hãy thiết kế FULLTEXT index tương ứng với title và dùng MATCH(title), thay vì giả định index ghép sẽ luôn phục vụ mọi tập con cột.

Các cột được MATCH phải thuộc cùng một bảng. FULLTEXT index không thay thế index quan hệ cho khóa ngoại, điều kiện bằng hoặc sắp xếp thông thường.

## 5. Tìm kiếm từ khóa cơ bản

Truy vấn các bài có liên quan đến transaction:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC, article_id;
~~~

MATCH AGAINST trong SELECT trả về điểm relevance. Cùng biểu thức trong WHERE lọc các hàng có kết quả tìm kiếm phù hợp. ORDER BY relevance DESC đưa tài liệu có điểm cao hơn lên trước; article_id là tiêu chí phụ để thứ tự ổn định khi điểm bằng nhau.

Không nên giả định một giá trị relevance cụ thể sẽ luôn giống nhau giữa các phiên bản, engine, tập dữ liệu hoặc cấu hình. Hãy dùng điểm như tín hiệu xếp hạng, không coi nó là xác suất hay điểm chất lượng tuyệt đối.

## 6. Natural language mode tìm theo token, không phải chuỗi con

Natural language mode phân tích chuỗi truy vấn thành các từ. Tài liệu có token phù hợp có thể xuất hiện trong kết quả; truy vấn không yêu cầu các từ nằm liền nhau hoặc theo đúng thứ tự như một phép so khớp phrase.

Ví dụ:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('database transaction' IN NATURAL LANGUAGE MODE);
~~~

Đây là tìm kiếm theo các từ database và transaction sau khi parser xử lý. Không nên diễn giải truy vấn trên là yêu cầu chuỗi nguyên văn database transaction.

Nếu cần tìm chuỗi con tùy ý, LIKE có ý nghĩa khác:

~~~sql
SELECT article_id, title
FROM articles
WHERE body LIKE '%transaction%';
~~~

LIKE '%...%' có thể tìm chuỗi con nằm giữa một từ hoặc một đoạn văn bản. FULLTEXT search tìm token theo quy tắc parser và có thể xếp hạng relevance. Hai cách có mục đích và đặc tính hiệu năng khác nhau.

Natural language mode cũng không tự động thực hiện stemming hoặc hiểu mọi biến thể ngữ pháp. Ví dụ, các dạng từ khác nhau có thể được xem là token khác nhau tùy parser. Nếu cần tìm theo ngôn ngữ có biến tố, cần đánh giá parser hoặc chiến lược chuẩn hóa phù hợp.

## 7. Relevance score dùng để xếp hạng

Điểm relevance thể hiện mức độ liên quan tương đối giữa tài liệu và chuỗi tìm kiếm theo thuật toán của engine. Điểm có thể chịu ảnh hưởng bởi:

- Tần suất token xuất hiện trong tài liệu.
- Mức độ phổ biến của token trong tập tài liệu.
- Độ dài tài liệu và phân bố token.
- Các cột được đưa vào MATCH.
- Engine, parser và cấu hình full-text.

Ví dụ:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('fulltext search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH(title, body)
        AGAINST ('fulltext search' IN NATURAL LANGUAGE MODE) > 0
ORDER BY score DESC, published_at DESC;
~~~

Điểm cao hơn thường biểu thị kết quả liên quan hơn trong cùng ngữ cảnh truy vấn. Không so sánh trực tiếp điểm giữa hai bảng có nội dung, engine hoặc index khác nhau. Nếu giao diện cần ngưỡng hiển thị, hãy đánh giá ngưỡng bằng dữ liệu thực tế và theo dõi thay đổi khi dữ liệu tăng.

## 8. Tìm kiếm trên nhiều cột

FULLTEXT index ghép cho phép tìm trong nhiều cột:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) > 0
ORDER BY relevance DESC;
~~~

Trong một index ghép, nội dung title và body cùng tham gia việc tìm kiếm. Nếu title quan trọng hơn body trong xếp hạng nghiệp vụ, có thể cân nhắc:

- Dùng hai FULLTEXT index riêng và kết hợp điểm trong truy vấn nếu cấu trúc index/engine cho phép.
- Tách truy vấn title và body, sau đó kết hợp kết quả có kiểm soát.
- Tạo một cột nội dung tìm kiếm đã chuẩn hóa với quy tắc rõ ràng.
- Đưa trọng số nghiệp vụ vào tầng ứng dụng sau khi nhận relevance.

Không tự ý cộng điểm từ các truy vấn khác nhau mà không kiểm tra thang điểm và tập dữ liệu, vì relevance có thể không cùng miền so sánh.

## 9. Kết hợp FULLTEXT với điều kiện lọc thông thường

Một ứng dụng thường chỉ tìm trong dữ liệu đang được xuất bản:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE) > 0
ORDER BY relevance DESC, published_at DESC
LIMIT 20;
~~~

FULLTEXT index phục vụ phần tìm kiếm token; B-tree index có thể hỗ trợ điều kiện status hoặc published_at. Optimizer quyết định kế hoạch dựa trên thống kê và chi phí. Không có bảo đảm mọi truy vấn kết hợp sẽ dùng cả hai index theo cách mong muốn.

Dùng EXPLAIN để quan sát kế hoạch:

~~~sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH(title, body)
        AGAINST ('transaction' IN NATURAL LANGUAGE MODE);
~~~

Kiểm tra key, access type, rows estimate và Extra. Dữ liệu nhỏ có thể khiến optimizer chọn kế hoạch khác với production; hãy đo trên tập dữ liệu có kích thước và phân bố gần thực tế.

## 10. Stopword: từ bị bỏ qua khi lập chỉ mục hoặc tìm kiếm

Stopword là các từ phổ biến mà full-text parser bỏ qua để giảm nhiễu và kích thước chỉ mục. Ví dụ trong tiếng Anh có thể gồm các từ chức năng rất thường gặp như the, a hoặc is, tùy stopword list đang dùng.

Nếu truy vấn chỉ chứa stopword, kết quả có thể rỗng vì token đó không được đưa vào tìm kiếm. Ví dụ, tìm một từ quá phổ biến thường không hữu ích.

InnoDB và MyISAM có cơ chế stopword và cấu hình riêng. InnoDB dùng danh sách stopword mặc định hoặc danh sách được cấu hình; MyISAM có cấu hình stopword tương ứng. Khi thay đổi stopword list, cần xây dựng lại FULLTEXT index để nội dung được phân tích lại theo danh sách mới.

Đừng xóa toàn bộ stopword chỉ để làm một truy vấn cụ thể có kết quả. Việc thay đổi ảnh hưởng đến kích thước index, relevance và mọi truy vấn trên index đó. Hãy thử nghiệm bằng dữ liệu đại diện trước khi áp dụng.

## 11. Minimum token size và từ quá ngắn

Các token ngắn hơn giới hạn cấu hình có thể không được lập chỉ mục. Giá trị mặc định thường gặp:

| Engine | Cấu hình | Mặc định thường gặp |
|---|---|---:|
| InnoDB | innodb_ft_min_token_size | 3 ký tự |
| MyISAM | ft_min_word_len | 4 ký tự |

Ví dụ mã như SQL, C, R hoặc tên sản phẩm có thể bị bỏ qua nếu token ngắn hơn giới hạn. Cần kiểm tra cấu hình thực tế trên server thay vì dựa vào mặc định.

Khi thay đổi minimum token size, cần rebuild FULLTEXT index để token được lập chỉ mục theo giới hạn mới. Chỉ thay biến cấu hình mà không xây dựng lại index không làm dữ liệu cũ tự được token hóa lại.

Với ngôn ngữ không phân tách từ bằng khoảng trắng như tiếng Trung, tiếng Nhật hoặc tiếng Hàn, parser mặc định có thể không phù hợp. MySQL cung cấp ngram parser cho tìm kiếm theo chuỗi n ký tự; cấu hình ngram_token_size ảnh hưởng cách phân đoạn và cần được xem xét khi tạo/rebuild index.

## 12. Khác biệt InnoDB và MyISAM trong natural language mode

Hai engine có các khác biệt đáng chú ý:

| Đặc điểm | InnoDB | MyISAM |
|---|---|---|
| FULLTEXT support | Có từ MySQL 5.6.4 | Có từ các phiên bản MySQL đời trước |
| Transaction | Có, theo đặc tính InnoDB | Không transactional |
| Minimum token mặc định thường gặp | 3 | 4 |
| Stopword | Cơ chế và cấu hình InnoDB | Cơ chế và cấu hình MyISAM |
| Ngưỡng 50% từ phổ biến trong natural language | Không áp dụng như MyISAM | Có thể loại từ xuất hiện trong hơn 50% hàng |
| Khả năng phục hồi khi rollback | Thay đổi transactional của InnoDB được rollback | Không có bảo đảm transaction tương đương |

Ngưỡng 50% là đặc điểm đặc biệt của MyISAM natural language search: từ xuất hiện trong hơn một nửa số hàng có thể bị xem là quá phổ biến và không được dùng để tìm. Không áp dụng quy tắc này cho InnoDB.

Điều này giải thích vì sao cùng một dữ liệu và truy vấn có thể cho kết quả khác nhau khi chuyển engine. Không chuyển engine chỉ để thay đổi kết quả tìm kiếm mà chưa đánh giá transaction, locking, crash recovery và workload ghi.

## 13. Collation và phân biệt chữ hoa/thường

Hành vi so khớp full-text chịu ảnh hưởng của character set và collation của các cột được lập chỉ mục. Với collation không phân biệt hoa/thường, tìm kiếm thường không phân biệt chữ hoa/thường. Collation binary hoặc collation phân biệt hoa/thường có thể tạo hành vi khác.

Kiểm tra định nghĩa cột:

~~~sql
SHOW FULL COLUMNS FROM articles;
~~~

Nếu ứng dụng cần quy tắc tìm kiếm nhất quán, hãy chọn character set/collation ngay từ thiết kế schema và kiểm thử các trường hợp chữ hoa, chữ thường, dấu tiếng Việt và ký tự Unicode. Đừng giả định parser xử lý mọi ngôn ngữ như tiếng Anh.

## 14. Tìm kiếm tiếng Việt và parser

Văn bản tiếng Việt có dấu và có dấu cách giữa các âm tiết. Parser mặc định phân tích token theo quy tắc của nó, không nhất thiết hiểu ranh giới từ tiếng Việt giống bộ tách từ chuyên dụng. Kết quả tìm kiếm có thể khác kỳ vọng khi người dùng nhập cụm từ, từ ghép hoặc dạng có/không dấu.

Các hướng cần thử nghiệm:

- Lưu nội dung ở character set utf8mb4 và collation phù hợp.
- Kiểm thử cùng từ khóa ở dạng có dấu và không dấu.
- Đánh giá parser mặc định trên corpus tiếng Việt thực tế.
- Cân nhắc ngram parser nếu phù hợp với yêu cầu tìm kiếm chuỗi ký tự.
- Nếu cần tách từ theo ngôn ngữ, cân nhắc tiền xử lý nội dung ở tầng ứng dụng hoặc giải pháp search chuyên dụng.

Ví dụ tạo index dùng ngram parser:

~~~sql
ALTER TABLE articles
    ADD FULLTEXT INDEX ft_articles_ngram (title, body)
    WITH PARSER ngram;
~~~

Đây là một index bổ sung cho mục đích thử nghiệm; không tạo trùng trên production nếu chưa đánh giá dung lượng và cách truy vấn. Ngram chia văn bản thành các đoạn n ký tự, nên có thể tìm chuỗi con theo cách khác parser từ thông thường nhưng index có thể lớn hơn và relevance cần được hiệu chỉnh.

## 15. Natural language mode không phải Boolean mode

Natural language mode diễn giải chuỗi tìm kiếm như các từ khóa thông thường. Các ký hiệu điều khiển như dấu cộng, dấu trừ, dấu sao hoặc dấu ngoặc không có ý nghĩa toán tử Boolean theo cách của Boolean mode.

Ví dụ natural language:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE);
~~~

Nếu cần cú pháp bắt buộc/loại trừ từ, wildcard cuối từ hoặc cụm từ chính xác, hãy nghiên cứu Boolean mode riêng. Ví dụ sau chỉ minh họa khác biệt cú pháp, không phải natural language mode:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('+"transaction isolation" -rollback' IN BOOLEAN MODE);
~~~

Không trộn hai bộ quy tắc trong cùng một truy vấn. Chọn mode dựa trên hành vi sản phẩm mong muốn: tìm tự nhiên và xếp hạng, hay truy vấn có toán tử điều khiển rõ ràng.

## 16. Natural language mode và phrase search

Truy vấn:

~~~sql
MATCH(title, body) AGAINST ('database transaction' IN NATURAL LANGUAGE MODE)
~~~

không yêu cầu hai từ database và transaction phải đứng cạnh nhau theo đúng thứ tự. Nó tìm theo token và relevance.

Nếu yêu cầu nghiệp vụ là cụm từ chính xác, dùng Boolean mode với cụm từ đặt trong dấu nháy kép:

~~~sql
MATCH(title, body)
    AGAINST ('"database transaction"' IN BOOLEAN MODE)
~~~

Phrase search vẫn chịu quy tắc tokenization, stopword và parser. Nó không tương đương tìm mọi chuỗi byte nguyên văn bằng LIKE.

## 17. Phân trang kết quả và xếp hạng ổn định

Ví dụ lấy 20 kết quả đầu:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH(title, body)
        AGAINST ('database index' IN NATURAL LANGUAGE MODE) > 0
ORDER BY relevance DESC, published_at DESC, article_id DESC
LIMIT 20;
~~~

ORDER BY có thêm tiêu chí phụ để thứ tự ổn định khi nhiều tài liệu có cùng relevance. Với trang sâu, LIMIT offset lớn có thể tốn chi phí. Hãy đo truy vấn và cân nhắc chiến lược phân trang theo nghiệp vụ; không giả định relevance là khóa phân trang duy nhất vì điểm có thể thay đổi khi dữ liệu/index thay đổi.

## 18. Cập nhật nội dung và bảo trì FULLTEXT index

Khi hàng được INSERT, UPDATE hoặc DELETE, FULLTEXT index được MySQL duy trì theo cơ chế của engine. Với InnoDB, thay đổi dữ liệu và chỉ mục tham gia transaction; việc xây dựng lại index có thể cần tài nguyên đáng kể.

Các hoạt động cần quản lý:

- Tạo index trên bảng lớn có thể tiêu tốn CPU, I/O và thời gian.
- Thay đổi parser, stopword hoặc minimum token size thường yêu cầu rebuild index.
- Thay đổi character set/collation có thể ảnh hưởng cách token hóa và so khớp.
- Sau migration, kiểm tra truy vấn tìm kiếm và relevance bằng bộ từ khóa chuẩn.
- Theo dõi dung lượng index, tốc độ ghi và độ trễ truy vấn.

Không xóa rồi tạo lại FULLTEXT index tùy tiện trong giờ cao điểm. Hãy lập kế hoạch triển khai, kiểm tra tác động khóa/DDL và có phương án rollback phù hợp với phiên bản MySQL.

## 19. Kiểm tra FULLTEXT index và kế hoạch thực thi

Liệt kê index:

~~~sql
SHOW INDEX FROM articles;
~~~

Xem định nghĩa bảng:

~~~sql
SHOW CREATE TABLE articles;
~~~

Kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
    AGAINST ('transaction' IN NATURAL LANGUAGE MODE);
~~~

Quan sát key và access type để xác nhận FULLTEXT index phù hợp được dùng. Nếu không thấy kế hoạch như mong đợi, kiểm tra:

- Danh sách cột trong MATCH có khớp FULLTEXT index không.
- Bảng có đúng engine và index đã tồn tại chưa.
- Chuỗi tìm kiếm có token nào bị stopword hoặc minimum token size loại bỏ không.
- Cấu hình parser và collation có phù hợp không.
- Câu truy vấn có biểu thức hoặc điều kiện làm thay đổi kế hoạch không.

EXPLAIN cho biết kế hoạch dự kiến, không đo đầy đủ độ trễ thực tế. Hãy benchmark với tập dữ liệu, độ dài văn bản và phân bố từ khóa gần production.

## 20. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
|---|---|---|
| MATCH AGAINST báo lỗi thiếu FULLTEXT index | Chưa tạo index hoặc danh sách cột không khớp | SHOW INDEX và đối chiếu cột MATCH |
| Không tìm thấy từ rất ngắn | Bị loại bởi minimum token size | Kiểm tra innodb_ft_min_token_size hoặc ft_min_word_len |
| Từ phổ biến không có kết quả trên MyISAM | Quy tắc ngưỡng 50% | Kiểm tra engine; InnoDB không dùng ngưỡng này |
| Truy vấn chỉ có stopword trả rỗng | Token bị stopword list bỏ qua | Kiểm tra danh sách stopword và chọn từ khóa có ý nghĩa |
| LIKE tìm thấy nhưng FULLTEXT không thấy | LIKE tìm substring, FULLTEXT tìm token | Xác định đúng kiểu tìm kiếm mong muốn |
| Cụm từ không đứng cạnh nhau vẫn khớp | Natural language không phải exact phrase | Dùng Boolean phrase search nếu yêu cầu cụm từ |
| Tìm tiếng Việt không như kỳ vọng | Parser mặc định không tách từ theo ngôn ngữ nghiệp vụ | Kiểm thử utf8mb4, collation, ngram hoặc tiền xử lý |
| Kết quả xếp hạng thay đổi | Corpus, token, index hoặc engine thay đổi | Đánh giá relevance theo tập dữ liệu hiện tại |
| Tạo index làm hệ thống chậm | DDL/build index tiêu tốn tài nguyên | Lập kế hoạch và theo dõi tài nguyên |

## 21. Quy trình triển khai natural language search

1. Xác định cột văn bản cần tìm và engine của bảng.
2. Chọn danh sách cột FULLTEXT phù hợp với truy vấn.
3. Tạo FULLTEXT index và kiểm tra SHOW CREATE TABLE.
4. Xác nhận character set, collation và parser.
5. Kiểm tra minimum token size và stopword list.
6. Viết MATCH(...) AGAINST(... IN NATURAL LANGUAGE MODE).
7. Trả relevance score và sắp xếp giảm dần.
8. Kết hợp điều kiện trạng thái/ngày tháng theo nhu cầu ứng dụng.
9. Dùng EXPLAIN và benchmark trên dữ liệu đại diện.
10. Kiểm thử từ ngắn, stopword, từ phổ biến, Unicode và truy vấn không có kết quả.
11. Xác định cách xử lý phrase search hoặc Boolean operator nếu sản phẩm cần.
12. Đo lại sau khi thay đổi parser, stopword, engine hoặc nội dung index.

## 22. Bài tập thực hành

1. Tạo bảng articles với title, body và FULLTEXT index ghép.
2. Chèn ít nhất 10 bài viết có nội dung và từ khóa khác nhau.
3. Tìm từ transaction bằng natural language mode và hiển thị relevance.
4. Tìm hai từ database index; kiểm tra tài liệu khớp một hoặc nhiều token.
5. Sắp xếp theo relevance DESC và thêm article_id làm tiêu chí phụ.
6. Kết hợp MATCH AGAINST với điều kiện status = 'PUBLISHED'.
7. Thử từ ngắn như SQL và quan sát ảnh hưởng minimum token size trên engine đang dùng.
8. Thử một stopword và một từ hiếm; so sánh số kết quả.
9. So sánh kết quả FULLTEXT với LIKE '%transaction%'.
10. So sánh natural language với Boolean phrase search để thấy khác biệt về ý nghĩa.
11. Dùng EXPLAIN và SHOW INDEX xác nhận FULLTEXT index được dùng.
12. Thử văn bản tiếng Việt có dấu/không dấu và đánh giá parser mặc định so với ngram trên dữ liệu test.
13. Nếu môi trường cho phép, so sánh hành vi InnoDB và MyISAM, đặc biệt quy tắc 50% của MyISAM.
14. Viết checklist triển khai thay đổi stopword hoặc minimum token size và nêu rõ vì sao phải rebuild index.

Bạn hoàn thành bài khi tạo được FULLTEXT index phù hợp, viết MATCH AGAINST ở natural language mode, giải thích được relevance score, dự đoán được ảnh hưởng của stopword/minimum token size và phân biệt tìm kiếm token với tìm chuỗi con hoặc phrase chính xác. Hãy xem natural language mode là một cơ chế tìm kiếm và xếp hạng văn bản có quy tắc parser rõ ràng, không phải phép tìm chuỗi tổng quát.
