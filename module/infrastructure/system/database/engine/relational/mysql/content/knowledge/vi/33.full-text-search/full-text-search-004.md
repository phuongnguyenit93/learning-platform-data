# Boolean mode, toán tử tìm kiếm và ý nghĩa kết quả

MySQL FULLTEXT hỗ trợ tìm kiếm theo nội dung của cột văn bản. Khi ứng dụng cần tìm tài liệu theo một chuỗi từ khóa, FULLTEXT có thể phân tích token, tra cứu inverted index và tính mức độ liên quan của từng hàng. Boolean mode cho phép mô tả yêu cầu tìm kiếm bằng các toán tử như bắt buộc có từ, loại trừ từ, tăng hoặc giảm trọng số, tìm cụm từ và tìm các từ ở gần nhau.

Boolean mode phù hợp khi người dùng cần điều khiển rõ hơn điều kiện tìm kiếm. Ví dụ, một người có thể yêu cầu bài viết phải có từ mysql, không được có từ oracle, ưu tiên bài viết nhắc đến index và giảm điểm bài viết có từ legacy.

Bài học này tập trung vào cú pháp IN BOOLEAN MODE, ý nghĩa của từng toán tử, cách kết hợp biểu thức, cách đọc relevance score và các yếu tố ảnh hưởng đến kết quả như FULLTEXT index, parser, stopword và độ dài token. Các ví dụ sử dụng InnoDB và bảng bài viết có FULLTEXT index trên title và body.

## 1. Boolean mode trong MySQL FULLTEXT

MySQL có hai cách tìm kiếm FULLTEXT thường gặp:

- Natural language mode: diễn giải chuỗi tìm kiếm như ngôn ngữ tự nhiên và xếp hạng tài liệu dựa trên mức độ liên quan.
- Boolean mode: diễn giải chuỗi tìm kiếm như một biểu thức có toán tử, cho phép yêu cầu hoặc loại trừ các từ và cụm từ cụ thể.

Boolean mode không phải toán tử AND/OR của SQL. Đây là cú pháp riêng bên trong chuỗi truyền cho MATCH() AGAINST(). Các điều kiện quan hệ thông thường vẫn được viết bằng WHERE, JOIN và những toán tử SQL khác.

Cú pháp:

~~~sql
MATCH(column_list)
AGAINST('search_expression' IN BOOLEAN MODE)
~~~

Ví dụ:

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

Truy vấn trên yêu cầu tài liệu phải chứa cả hai từ mysql và index theo token mà FULLTEXT parser nhận diện.

### 1.1. Boolean mode giải quyết tình huống nào?

Giả sử người dùng tìm tài liệu kỹ thuật và nhập:

~~~text
+mysql +index -oracle
~~~

Ý nghĩa:

- Tài liệu phải có mysql.
- Tài liệu phải có index.
- Tài liệu không được có oracle.

Một truy vấn tự do như mysql index không diễn đạt rõ ràng các yêu cầu bắt buộc. Boolean mode cho phép biểu diễn chúng trực tiếp.

### 1.2. Boolean mode không thay thế bộ lọc SQL

FULLTEXT chỉ xác định những hàng phù hợp với biểu thức văn bản. Các điều kiện như trạng thái xuất bản, tenant, quyền truy cập hoặc khoảng ngày vẫn cần được kiểm tra bằng SQL:

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE status = 'PUBLISHED'
  AND tenant_id = 42
  AND MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

Không đưa các điều kiện phân quyền vào nội dung tìm kiếm rồi xem chúng như một biện pháp kiểm soát truy cập. Quyền đọc hàng phải được áp dụng bằng điều kiện quan hệ hoặc cơ chế bảo mật phù hợp.

## 2. Chuẩn bị FULLTEXT index

Boolean mode cần FULLTEXT index trên các cột được tìm kiếm. InnoDB hỗ trợ FULLTEXT index cho các cột kiểu CHAR, VARCHAR và TEXT.

Tạo bảng ví dụ:

~~~sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(250) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at DATETIME NULL,
    PRIMARY KEY (article_id),
    KEY idx_articles_tenant_status_date
        (tenant_id, status, published_at),
    FULLTEXT KEY ft_articles_title_body (title, body)
) ENGINE = InnoDB;
~~~

FULLTEXT index ft_articles_title_body lập chỉ mục chung cho title và body. Truy vấn tìm kiếm tương ứng phải dùng đúng danh sách cột:

~~~sql
MATCH(title, body)
AGAINST('+mysql +index' IN BOOLEAN MODE)
~~~

Với InnoDB, danh sách cột trong MATCH() phải khớp với các cột của một FULLTEXT index, theo cùng thứ tự. Nếu muốn tìm chỉ trong title, hãy tạo một FULLTEXT index riêng trên title và dùng MATCH(title). Không nên giả định một FULLTEXT index ghép bất kỳ có thể phục vụ mọi tổ hợp cột.

Nếu không khai báo FULLTEXT index trong CREATE TABLE, có thể thêm index sau khi tạo bảng:

~~~sql
ALTER TABLE articles
ADD FULLTEXT INDEX ft_articles_title_body (title, body);
~~~

Chọn một trong hai cách tạo index: khai báo trong CREATE TABLE hoặc thêm bằng ALTER TABLE. Không chạy cả hai ví dụ trên cùng một bảng vì tên index sẽ bị trùng.

### 2.1. Thêm dữ liệu minh họa

~~~sql
INSERT INTO articles
    (article_id, tenant_id, title, body, status, published_at)
VALUES
(
    1, 42, 'MySQL index fundamentals',
    'Learn how a MySQL index helps the optimizer find rows efficiently.',
    'PUBLISHED', '2026-01-10 09:00:00'
),
(
    2, 42, 'MySQL query optimization',
    'Use EXPLAIN to inspect a query plan and improve database performance.',
    'PUBLISHED', '2026-01-12 10:00:00'
),
(
    3, 42, 'Oracle index concepts',
    'This article discusses index design in Oracle and relational databases.',
    'PUBLISHED', '2026-01-14 11:00:00'
),
(
    4, 42, 'Database engine internals',
    'The storage engine manages pages, transactions, indexes, and recovery.',
    'DRAFT', NULL
),
(
    5, 84, 'MySQL and full text search',
    'Boolean full text search supports required and excluded terms.',
    'PUBLISHED', '2026-01-18 13:00:00'
);
~~~

Dữ liệu minh họa giúp so sánh kết quả khi thay đổi toán tử. Trong môi trường thực tế, token có thể bị bỏ qua vì stopword hoặc quy tắc độ dài token; phần sau sẽ giải thích vì sao một từ xuất hiện trong chuỗi tìm kiếm chưa chắc đã được lập chỉ mục.

## 3. Các toán tử Boolean

Boolean mode hỗ trợ những toán tử chính sau:

| Toán tử | Ý nghĩa | Tác động đến kết quả |
|---|---|---|
| + | Từ bắt buộc phải có | Hàng phải khớp từ này |
| - | Từ không được có | Loại hàng chứa từ này |
| Không có toán tử | Từ tùy chọn | Hàng khớp từ này có thể được trả về |
| > | Tăng đóng góp vào relevance | Ưu tiên hàng chứa từ này |
| < | Giảm đóng góp vào relevance | Hạ điểm tương đối |
| ~ | Đóng góp âm vào relevance | Hạ điểm, không loại hàng |
| * | Tìm theo tiền tố token | Khớp từ bắt đầu bằng tiền tố |
| () | Nhóm biểu thức | Kết hợp các điều kiện thành nhóm |
| " | Tìm cụm từ | Tìm các từ theo cụm được đặt trong dấu quote |
| @distance | Tìm các từ ở gần nhau | Giới hạn khoảng cách giữa các từ trong cụm, InnoDB |

Các toán tử +, -, >, <, ~ được đặt trước từ hoặc biểu thức tương ứng. Toán tử * được đặt sau token.

## 4. Từ bắt buộc với toán tử cộng

Dấu cộng + yêu cầu token phải xuất hiện trong hàng được trả về.

### 4.1. Yêu cầu một từ

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql' IN BOOLEAN MODE);
~~~

Chỉ các bài có token mysql mới đáp ứng biểu thức này.

### 4.2. Yêu cầu nhiều từ

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

Cả mysql và index đều bắt buộc. Nếu hàng chỉ có mysql mà không có index, hàng đó không được trả về.

### 4.3. Phân biệt hai toán tử cộng với chuỗi không có toán tử

| Biểu thức | Ý nghĩa |
|---|---|
| +mysql | Phải có mysql |
| +mysql +index | Phải có cả mysql và index |
| mysql index | Các từ là tùy chọn; khớp một trong các từ có thể đủ để trả hàng |
| +mysql index | Phải có mysql; index là từ tùy chọn |

Từ không có toán tử không mặc nhiên là bắt buộc. Đây là điểm quan trọng khi chuyển yêu cầu tìm kiếm từ giao diện người dùng thành biểu thức Boolean.

## 5. Loại trừ từ với toán tử trừ

Dấu trừ - loại hàng chứa token được đánh dấu khỏi tập kết quả.

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql -oracle' IN BOOLEAN MODE);
~~~

Truy vấn yêu cầu:

- Có mysql.
- Không có oracle.

Toán tử trừ thường được dùng cùng ít nhất một điều kiện dương. Một biểu thức chỉ có các từ bị loại trừ, ví dụ -oracle, không xác định tập tài liệu cần lấy và trả về tập rỗng.

### 5.1. Điều kiện loại trừ không phải phủ định toàn bộ truy vấn SQL

-oracle chỉ loại tài liệu có token oracle trong nội dung được FULLTEXT index. Nó không có nghĩa là tìm mọi hàng không chứa oracle trong toàn bộ bảng nếu không có từ dương làm cơ sở.

Nếu cần truy vấn toàn bộ hàng không chứa một từ, hãy cân nhắc điều kiện SQL hoặc thiết kế truy vấn phù hợp. FULLTEXT Boolean mode được tối ưu cho tìm kiếm nội dung theo token, không phải thay thế mọi phép phủ định trên bảng.

### 5.2. Kết hợp bắt buộc và loại trừ

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index -oracle' IN BOOLEAN MODE)
  AND status = 'PUBLISHED';
~~~

Ở đây FULLTEXT lọc nội dung; điều kiện status lọc trạng thái bản ghi. Hai lớp điều kiện có trách nhiệm riêng và có thể được kết hợp trong cùng WHERE.

## 6. Từ tùy chọn

Token không có toán tử là tùy chọn. Hàng có token đó có thể được trả về và token có thể đóng góp vào relevance.

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('mysql index' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('mysql index' IN BOOLEAN MODE);
~~~

Với mysql index, tài liệu có thể khớp mysql, index hoặc cả hai. Nếu nghiệp vụ yêu cầu cả hai, phải viết +mysql +index.

Một từ tùy chọn không giống điều kiện SQL OR theo nghĩa tổng quát. Nó được diễn giải trong ngữ cảnh tokenization và relevance của FULLTEXT.

## 7. Tăng và giảm relevance bằng > và <

> và < thay đổi mức đóng góp của một token vào điểm relevance:

- > tăng trọng số tương đối của token.
- < giảm trọng số tương đối của token.

Hai toán tử này không biến từ thành điều kiện bắt buộc hoặc loại trừ. Muốn bắt buộc vẫn dùng +; muốn loại trừ vẫn dùng -.

Ví dụ ưu tiên bài viết có mysql và tăng mức ưu tiên cho index:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql >index' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql >index' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

+mysql bắt buộc có mysql. >index làm token index đóng góp mạnh hơn vào relevance nếu xuất hiện; index không trở thành điều kiện bắt buộc chỉ vì có dấu lớn hơn.

Có thể giảm trọng số:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql <legacy' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql <legacy' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

Trong ví dụ này, legacy là token tùy chọn nhưng có đóng góp thấp hơn. Nếu muốn loại tài liệu chứa legacy hoàn toàn, thay <legacy bằng -legacy.

## 8. Hạ điểm thay vì loại hàng với ~

Dấu ngã ~ làm đóng góp relevance của token trở thành âm. Khác với dấu trừ, nó không loại hàng khỏi kết quả.

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql ~legacy' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql ~legacy' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

Ý nghĩa:

- mysql là bắt buộc.
- legacy không phải điều kiện loại trừ.
- Nếu tài liệu có legacy, điểm relevance bị giảm.
- Tài liệu vẫn có thể xuất hiện nếu đáp ứng điều kiện dương.

So sánh:

| Biểu thức | Hành vi với hàng chứa token |
|---|---|
| +mysql -legacy | Bị loại nếu có legacy |
| +mysql ~legacy | Vẫn có thể được trả về nhưng điểm bị giảm |
| +mysql <legacy | Vẫn có thể được trả về, đóng góp của legacy thấp hơn |

Chọn toán tử theo ý nghĩa sản phẩm. Nếu nội dung bị cấm xuất hiện trong kết quả thì dùng -; nếu chỉ muốn giảm ưu tiên thì dùng ~ hoặc <.

## 9. Tìm tiền tố bằng *

Dấu sao * là toán tử truncation, được nối vào cuối token để tìm các token bắt đầu bằng tiền tố đó.

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+optim*' IN BOOLEAN MODE);
~~~

Biểu thức có thể khớp các token như optimize, optimization hoặc optimizer nếu chúng được parser lập chỉ mục dưới dạng token bắt đầu bằng optim.

### 9.1. Dấu sao phải ở cuối token

Đúng:

~~~text
optim*
+optim*
~~~

Không dùng dấu sao ở đầu để yêu cầu tìm hậu tố:

~~~text
*ization
~~~

FULLTEXT Boolean mode không phải công cụ tìm chuỗi con tùy ý. Toán tử * thực hiện tìm tiền tố token, không hỗ trợ wildcard hai phía như một số pattern matching khác.

### 9.2. Kết hợp wildcard với điều kiện bắt buộc

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +optim*' IN BOOLEAN MODE);
~~~

Tài liệu cần có mysql và một token bắt đầu bằng optim.

Wildcard có thể làm tập token khớp rộng hơn, vì vậy cần giới hạn tiền tố hợp lý. Tiền tố quá ngắn có thể tạo nhiều kết quả và làm truy vấn kém chọn lọc.

## 10. Nhóm biểu thức bằng dấu ngoặc

Dấu ngoặc đơn () gom các token thành một nhóm để áp dụng toán tử cho cả nhóm hoặc tổ chức các điều kiện tìm kiếm phức tạp.

Ví dụ yêu cầu mysql và ít nhất một trong hai từ index hoặc optimizer:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +(index optimizer)' IN BOOLEAN MODE);
~~~

Nhóm thứ hai được đánh dấu + nên ít nhất một token trong nhóm phải khớp. mysql cũng là điều kiện bắt buộc độc lập.

### 10.1. Nhóm với trọng số

Có thể kết hợp dấu ngoặc với toán tử trọng số:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql +(>index <optimizer)' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +(>index <optimizer)' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

Biểu thức yêu cầu mysql và một trong các token trong nhóm. index được tăng trọng số tương đối; optimizer được giảm trọng số tương đối. Cách nhóm giúp diễn đạt điều kiện phức hợp mà không cần tách thành nhiều truy vấn.

### 10.2. Không dùng dấu ngoặc thay cho toán tử bắt buộc

Dấu ngoặc chỉ nhóm biểu thức. Nếu muốn toàn bộ nhóm là điều kiện bắt buộc, đặt toán tử + trước dấu ngoặc mở. Nếu không có +, không nên suy luận rằng mọi token bên trong đều bắt buộc.

## 11. Tìm cụm từ bằng dấu ngoặc kép

Đặt nhiều từ trong dấu ngoặc kép để tìm cụm từ theo thứ tự được chỉ định:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('"query optimizer"' IN BOOLEAN MODE);
~~~

Biểu thức tìm cụm query optimizer. Đây là cách diễn đạt khác với việc tìm hai token riêng lẻ ở bất kỳ vị trí nào trong tài liệu.

Có thể kết hợp cụm từ với toán tử bắt buộc:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+"query optimizer" +mysql' IN BOOLEAN MODE);
~~~

Tài liệu phải có cụm query optimizer và token mysql.

### 11.1. Cụm từ vẫn phụ thuộc parser

Phrase search hoạt động trên các token do FULLTEXT parser tạo ra. Dấu câu và cách tách từ có thể ảnh hưởng đến token sequence; không nên hiểu cụm từ là so sánh byte-for-byte với đoạn văn bản gốc.

Nếu token trong cụm bị bỏ qua vì stopword hoặc quy tắc độ dài token, kết quả có thể khác kỳ vọng. Hãy thử cụm từ với cấu hình parser thực tế và kiểm tra danh sách stopword trước khi đưa vào giao diện tìm kiếm.

## 12. Tìm kiếm gần nhau với @distance

InnoDB hỗ trợ toán tử proximity search @distance trong Boolean mode. Toán tử này theo sau một cụm được đặt trong dấu ngoặc kép và giới hạn khoảng cách giữa các từ của cụm, tính theo số từ.

Ví dụ:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('"database optimizer" @5' IN BOOLEAN MODE);
~~~

Truy vấn tìm tài liệu có các từ database và optimizer nằm trong phạm vi khoảng cách được chỉ định. Giá trị distance là số nguyên không âm theo cú pháp của toán tử; khoảng cách được tính theo vị trí từ, không phải số ký tự.

### 12.1. Proximity search khác phrase search

| Kiểu tìm | Mục tiêu |
|---|---|
| "database optimizer" | Tìm cụm từ theo thứ tự và cấu trúc cụm |
| "database optimizer" @5 | Cho phép khoảng cách giữa các từ trong phạm vi proximity |

Proximity hữu ích khi người dùng muốn tìm hai khái niệm xuất hiện gần nhau nhưng không nhất thiết liền kề.

### 12.2. Giới hạn của @distance

- @distance là tính năng của InnoDB Boolean full-text search.
- Cụm từ phải được đặt trong dấu ngoặc kép trước toán tử khoảng cách.
- Khoảng cách được đo theo từ do parser nhận diện.
- Kết quả vẫn phụ thuộc stopword, token size và parser.
- Không xem proximity search như tìm kiếm ngữ nghĩa hoặc tìm từ đồng nghĩa.

Nếu ứng dụng dùng MyISAM hoặc parser tùy chỉnh, hãy xác minh tính năng và cú pháp trên đúng engine/parser trước khi triển khai.

## 13. Kết hợp toán tử thành biểu thức thực tế

Boolean mode trở nên hữu ích khi ghép các toán tử theo mục tiêu tìm kiếm.

### 13.1. Tài liệu phải có hai từ, không được có từ thứ ba

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +transaction -oracle' IN BOOLEAN MODE);
~~~

Dùng khi người dùng muốn giới hạn chủ đề rõ ràng.

### 13.2. Tìm một trong hai khái niệm bổ sung

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +(index optimizer)' IN BOOLEAN MODE);
~~~

Tài liệu phải có mysql và có ít nhất một token trong nhóm index/optimizer.

### 13.3. Ưu tiên một từ và hạ điểm từ khác

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql >index ~legacy' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql >index ~legacy' IN BOOLEAN MODE)
ORDER BY score DESC, article_id;
~~~

mysql là bắt buộc. index làm tăng relevance nếu xuất hiện. legacy làm giảm relevance nếu xuất hiện nhưng không loại hàng.

### 13.4. Tìm cụm từ và loại trừ tài liệu cũ

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+"query optimizer" -legacy' IN BOOLEAN MODE);
~~~

Tài liệu phải có cụm query optimizer và không được chứa token legacy.

## 14. Ý nghĩa relevance score

MATCH() AGAINST() trả về điểm relevance cho hàng khớp. Trong Boolean mode, điểm này có thể được dùng để xếp hạng, nhưng MySQL không tự động sắp xếp kết quả theo relevance như natural language mode.

Ví dụ:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql index' IN BOOLEAN MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql index' IN BOOLEAN MODE)
ORDER BY relevance DESC, article_id ASC;
~~~

ORDER BY relevance DESC đưa tài liệu có điểm cao lên trước. article_id ASC là khóa phụ để thứ tự ổn định khi nhiều tài liệu có cùng điểm.

### 14.1. Điểm relevance không phải xác suất

Relevance score không phải xác suất một tài liệu đúng, cũng không phải phần trăm độ chính xác. Điểm phụ thuộc vào:

- Các token trong biểu thức tìm kiếm.
- Tần suất token trong tài liệu.
- Phân bố token trong tập dữ liệu được lập chỉ mục.
- Trọng số và toán tử trong Boolean expression.
- Cấu hình parser và stopword.

Không nên hiển thị điểm như một tỷ lệ phần trăm nếu sản phẩm chưa có bước hiệu chuẩn riêng.

### 14.2. Điểm có thể thay đổi theo dữ liệu

Khi tài liệu được thêm, xóa hoặc cập nhật, phân bố từ trong index thay đổi. Điểm relevance có thể thay đổi theo corpus. Vì vậy:

- Không lưu score như thuộc tính cố định của bài viết.
- Không so sánh score của hai truy vấn khác nhau như cùng một thang đo tuyệt đối.
- Không giả định cùng một tài liệu luôn có score giống nhau sau khi corpus thay đổi.
- Nên đo lường chất lượng xếp hạng bằng tập truy vấn và đánh giá người dùng.

### 14.3. Boolean mode không tự sắp xếp theo điểm

Đây là khác biệt cần nhớ:

| Chế độ | Hành vi sắp xếp |
|---|---|
| Natural language mode | Thông thường kết quả được sắp xếp theo relevance |
| Boolean mode | Không tự động sắp xếp theo relevance |

Nếu giao diện cần kết quả tốt nhất trước, luôn viết ORDER BY score DESC và thêm khóa phụ để phân trang ổn định.

## 15. Boolean mode và natural language mode

Hai chế độ cùng dùng FULLTEXT index nhưng diễn giải chuỗi tìm kiếm khác nhau.

| Khía cạnh | Natural language mode | Boolean mode |
|---|---|---|
| Mục đích | Tìm theo cụm từ tự nhiên | Tìm theo biểu thức có toán tử |
| Bắt buộc có token | Không có toán tử + | Dùng + |
| Loại token | Không có toán tử - | Dùng - |
| Điều chỉnh trọng số | Không có cú pháp Boolean tương ứng | Dùng >, <, ~ |
| Nhóm điều kiện | Không dùng cú pháp Boolean | Dùng dấu ngoặc |
| Sắp xếp | Thông thường theo relevance | Không tự động sắp xếp theo relevance |

Ví dụ natural language:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body) AGAINST('mysql index') AS score
FROM articles
WHERE MATCH(title, body) AGAINST('mysql index');
~~~

Ví dụ Boolean:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql +index -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index -oracle' IN BOOLEAN MODE)
ORDER BY score DESC;
~~~

Boolean mode cho phép diễn đạt điều kiện rõ ràng hơn. Đổi lại, ứng dụng phải hiểu cách xây dựng biểu thức và giải thích cho người dùng vì sao một tài liệu được giữ hoặc bị loại.

### 15.1. Ngưỡng 50% và Boolean mode

MyISAM natural-language search có quy tắc ngưỡng 50%: một từ xuất hiện trong quá nhiều hàng có thể bị xem là ít hữu ích và không được dùng để trả kết quả ở chế độ này. Quy tắc đó không áp dụng cho Boolean mode.

InnoDB natural-language search cũng không áp dụng ngưỡng 50% kiểu MyISAM. Vì vậy, không nên giải thích mọi khác biệt kết quả giữa InnoDB và MyISAM bằng một ngưỡng chung; cần xét engine, mode, parser và cấu hình index.

## 16. Parser, stopword và độ dài token

Boolean mode chỉ tìm những token mà FULLTEXT parser đưa vào index. Chuỗi truy vấn được phân tích theo quy tắc parser tương ứng; một từ có mặt trong nội dung nguồn chưa chắc tồn tại trong FULLTEXT index.

Các nguyên nhân thường gặp:

- Từ nằm trong stopword list.
- Token ngắn hơn độ dài tối thiểu.
- Token dài hơn giới hạn tối đa.
- Parser tách từ khác với kỳ vọng của ứng dụng.
- Ngôn ngữ hoặc cách viết không phù hợp với parser mặc định.

### 16.1. Độ dài token của InnoDB và MyISAM

Một số cấu hình mặc định thường gặp:

| Engine | Cấu hình | Mặc định thường gặp |
|---|---|---:|
| InnoDB | innodb_ft_min_token_size | 3 |
| InnoDB | innodb_ft_max_token_size | 84 |
| MyISAM | ft_min_word_len | 4 |
| MyISAM | ft_max_word_len | 84 |

Các giá trị thực tế có thể đã được quản trị viên thay đổi. Kiểm tra cấu hình server trước khi kết luận vì sao một token không tìm thấy.

Có thể xem một số biến InnoDB:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
~~~

Với MyISAM, kiểm tra các biến ft_min_word_len và ft_max_word_len:

~~~sql
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
SHOW VARIABLES LIKE 'ft_stopword_file';
~~~

Thay đổi token size hoặc stopword configuration không tự làm các token đã bỏ qua trước đó xuất hiện trong index cũ. Sau khi thay đổi cấu hình, cần xây dựng lại FULLTEXT index liên quan theo quy trình vận hành phù hợp.

### 16.2. Stopword

Stopword là các từ phổ biến bị loại khỏi FULLTEXT index để giảm nhiễu. MySQL cung cấp danh sách stopword mặc định; InnoDB cũng hỗ trợ cấu hình danh sách stopword riêng ở cấp server hoặc bảng theo cơ chế của engine.

Ví dụ, nếu một từ nằm trong stopword list thì việc viết dấu + trước từ đó không thể biến nó thành token đã được lập chỉ mục. Điều kiện bắt buộc chỉ có ý nghĩa với token mà index có thể tìm thấy.

Khi thiết kế tìm kiếm tiếng Việt hoặc thuật ngữ chuyên ngành:

- Kiểm tra danh sách stopword hiện tại.
- Xác định từ nghiệp vụ nào không được phép bị loại.
- Cân nhắc danh sách stopword tùy chỉnh nếu phù hợp.
- Kiểm tra tác động tới kích thước index và chất lượng kết quả.
- Rebuild index sau khi thay đổi cấu hình stopword.

Không nên loại toàn bộ stopword một cách máy móc. Những từ quá phổ biến có thể làm tăng kích thước index và tạo nhiều kết quả ít hữu ích.

### 16.3. Parser mặc định và ngôn ngữ

Parser mặc định tách nội dung thành token dựa trên ranh giới từ và quy tắc ký tự của MySQL. Với văn bản có khoảng trắng như tiếng Việt, parser mặc định thường làm việc theo các ranh giới từ mà nó nhận diện; tuy nhiên, dấu câu, dấu nối, cách viết tên riêng và stopword vẫn có thể ảnh hưởng kết quả.

Đối với ngôn ngữ không dùng khoảng trắng để phân tách từ, chẳng hạn tiếng Trung, tiếng Nhật hoặc tiếng Hàn, parser mặc định có thể không đáp ứng yêu cầu. MySQL cung cấp ngram parser cho các ngôn ngữ này:

~~~sql
CREATE TABLE multilingual_documents (
    document_id BIGINT UNSIGNED NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (document_id),
    FULLTEXT KEY ft_content (content) WITH PARSER ngram
) ENGINE = InnoDB;
~~~

ngram parser chia văn bản thành các chuỗi n-gram. Kích thước token được điều khiển bởi biến ngram_token_size; mặc định thường là 2. Cấu hình này ảnh hưởng trực tiếp cách lập chỉ mục và cách truy vấn phải được phân tích.

Không chọn ngram chỉ vì tài liệu có ký tự Unicode. Hãy chọn parser theo đặc điểm ngôn ngữ, cách người dùng nhập truy vấn và kết quả kiểm thử thực tế.

## 17. InnoDB và MyISAM trong Boolean search

Boolean mode được hỗ trợ bởi cả InnoDB và MyISAM, nhưng có khác biệt về triển khai và cấu hình.

| Khía cạnh | InnoDB | MyISAM |
|---|---|---|
| FULLTEXT index | Có | Có |
| Boolean operators cơ bản | Có | Có |
| Proximity operator @distance | Có | Không hỗ trợ như InnoDB |
| Token size setting | innodb_ft_min_token_size / innodb_ft_max_token_size | ft_min_word_len / ft_max_word_len |
| Stopword configuration | Có cơ chế riêng của InnoDB | Dùng cấu hình stopword của MyISAM |
| Transactional storage | Có | Không |

Với ứng dụng mới sử dụng InnoDB, cần lưu ý @distance là tính năng gắn với InnoDB Boolean full-text search. Nếu chuyển engine hoặc dùng parser khác, hãy kiểm tra lại những biểu thức nâng cao.

## 18. Dùng Boolean mode trong ứng dụng

Ứng dụng thường nhận truy vấn từ ô tìm kiếm, sau đó gửi biểu thức đến MySQL. Có hai vấn đề cần giải quyết riêng:

1. Bảo vệ câu SQL khỏi SQL injection.
2. Quy định người dùng được phép sử dụng những toán tử Boolean nào.

### 18.1. Dùng prepared statement

Không nối trực tiếp chuỗi tìm kiếm vào câu SQL:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body) AGAINST(? IN BOOLEAN MODE) AS score
FROM articles
WHERE tenant_id = ?
  AND status = 'PUBLISHED'
  AND MATCH(title, body) AGAINST(? IN BOOLEAN MODE)
ORDER BY score DESC, article_id ASC
LIMIT ?;
~~~

Ứng dụng bind tham số tìm kiếm, tenant_id và limit bằng prepared statement. Nếu dùng cùng một biểu thức cho SELECT và WHERE, bind giá trị tương ứng ở cả hai vị trí.

Prepared statement bảo vệ cấu trúc SQL. Nó không tự giới hạn các toán tử Boolean bên trong chuỗi tìm kiếm; dấu +, -, * hoặc ngoặc vẫn có ý nghĩa đối với FULLTEXT parser.

### 18.2. Quy định cú pháp mà giao diện cho phép

Nếu sản phẩm chỉ muốn hỗ trợ tìm từ đơn giản, hãy nhận danh sách từ khóa rồi tự tạo biểu thức Boolean từ các token đã xác thực. Nếu muốn hỗ trợ cú pháp nâng cao, hãy định nghĩa grammar rõ ràng và kiểm tra đầu vào trước khi gửi đến MySQL.

Ví dụ quy tắc sản phẩm:

- Cho phép dấu + để yêu cầu từ.
- Cho phép dấu - để loại từ.
- Giới hạn độ dài và số lượng token.
- Giới hạn độ sâu nhóm ngoặc.
- Chỉ cho phép phrase search nếu giao diện có hướng dẫn.
- Chỉ cho phép @distance khi hệ thống chạy InnoDB và đã kiểm thử.
- Không cho phép người dùng thay đổi tenant hoặc điều kiện quyền truy cập qua chuỗi FULLTEXT.

Đừng xóa hoặc escape mọi ký tự đặc biệt một cách tùy tiện nếu giao diện tuyên bố hỗ trợ Boolean syntax; điều đó có thể làm thay đổi ý nghĩa truy vấn. Hãy chọn một hợp đồng đầu vào rõ ràng: tìm kiếm tự do đã chuẩn hóa hoặc Boolean query có grammar được kiểm soát.

### 18.3. Giới hạn truy vấn

Một biểu thức dài với nhiều nhánh, phrase và wildcard có thể tốn tài nguyên. Có thể giới hạn:

- Số token trong một truy vấn.
- Số nhóm và độ sâu ngoặc.
- Độ dài tối đa của mỗi token.
- Số cụm phrase.
- Khoảng cách proximity tối đa.
- Số hàng trả về và thời gian truy vấn.

Các giới hạn nên được áp dụng ở tầng ứng dụng và kết hợp với giám sát ở database.

## 19. Hiệu năng và vận hành

FULLTEXT index giúp tìm token hiệu quả hơn so với quét nội dung bằng LIKE với wildcard đầu chuỗi, nhưng chi phí vẫn phụ thuộc số token, độ dài tài liệu, số kết quả và độ phức tạp của biểu thức.

### 19.1. Kết hợp FULLTEXT với index quan hệ

Trong ví dụ articles, FULLTEXT index phục vụ điều kiện nội dung; index B-tree trên tenant_id, status và published_at phục vụ các điều kiện quan hệ. Hai loại index có mục đích khác nhau.

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST('+mysql +index' IN BOOLEAN MODE) AS score
FROM articles
WHERE tenant_id = 42
  AND status = 'PUBLISHED'
  AND published_at >= '2026-01-01'
  AND MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE)
ORDER BY score DESC, article_id
LIMIT 20;
~~~

Hãy kiểm tra kế hoạch thực thi và số hàng thực tế trên dữ liệu đại diện. Không giả định rằng index quan hệ và FULLTEXT index luôn được kết hợp theo đúng thứ tự mong muốn chỉ dựa vào thứ tự điều kiện trong WHERE.

### 19.2. Đọc EXPLAIN

~~~sql
EXPLAIN
SELECT article_id, title
FROM articles
WHERE tenant_id = 42
  AND MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

Kiểm tra:

- FULLTEXT index có được chọn cho điều kiện MATCH() không.
- Ước lượng số hàng có hợp lý không.
- Các điều kiện tenant/status có được áp dụng hiệu quả không.
- Có bước sort hoặc xử lý bổ sung đáng kể không.
- Biểu thức Boolean có trả quá nhiều hàng trung gian không.

Nếu cần xem số hàng và thời gian thực tế, có thể dùng EXPLAIN ANALYZE trên phiên bản hỗ trợ:

~~~sql
EXPLAIN ANALYZE
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST('+mysql +index' IN BOOLEAN MODE);
~~~

EXPLAIN ANALYZE thực thi truy vấn để đo. Chỉ dùng với truy vấn đọc phù hợp và dữ liệu đại diện; không nhầm nó với EXPLAIN chỉ đọc kế hoạch.

### 19.3. FULLTEXT index được cập nhật cùng dữ liệu

Với InnoDB, thao tác INSERT, UPDATE và DELETE làm thay đổi nội dung được lập chỉ mục sẽ được phản ánh vào FULLTEXT index theo cơ chế của engine. Ứng dụng không cần tự duy trì một bảng từ khóa phụ chỉ để cập nhật index cơ bản.

Tuy vậy, cần theo dõi:

- Thời gian ghi khi tài liệu dài hoặc số lượng cập nhật lớn.
- Kích thước FULLTEXT index.
- Độ trễ và tài nguyên trong quá trình bulk load hoặc rebuild.
- Ảnh hưởng của thay đổi parser, stopword và token size.

Nếu thay đổi cấu hình tokenization, lập kế hoạch rebuild và kiểm tra kết quả sau rebuild trước khi đưa cấu hình mới vào sản xuất.

### 19.4. Khi LIKE phù hợp hơn

FULLTEXT tìm theo token và các quy tắc parser. Nếu yêu cầu là tìm chuỗi con tùy ý, ví dụ một đoạn mã nằm giữa chuỗi dài, LIKE có thể diễn đạt đúng hơn:

~~~sql
SELECT article_id, title
FROM articles
WHERE title LIKE '%abc-123%';
~~~

LIKE với wildcard đầu chuỗi thường không tận dụng B-tree index theo cách tìm tiền tố có thể làm được. Với dữ liệu lớn, hãy cân nhắc thiết kế cột chuẩn hóa, ngram hoặc một hệ thống search chuyên dụng tùy yêu cầu.

## 20. Những lỗi thường gặp

### 20.1. Quên toán tử cộng

Người viết truy vấn muốn cả hai từ nhưng lại dùng:

~~~text
mysql index
~~~

Đây là các từ tùy chọn. Nếu cả hai phải xuất hiện, hãy dùng:

~~~text
+mysql +index
~~~

### 20.2. Dùng dấu trừ khi chỉ muốn hạ điểm

~~~text
+mysql -legacy
~~~

loại hàng có legacy khỏi tập kết quả vốn phải có mysql. Nếu chỉ muốn giảm điểm của hàng có legacy, dùng:

~~~text
+mysql ~legacy
~~~

Hàng có mysql vẫn có thể được trả về dù chứa legacy, nhưng điểm relevance bị giảm.

Chọn theo yêu cầu nghiệp vụ; không đánh đồng loại trừ và giảm trọng số.

### 20.3. Chỉ có từ bị loại trừ

Biểu thức -oracle không tạo tập kết quả gồm mọi tài liệu không có oracle. Hãy có ít nhất một điều kiện dương hoặc dùng điều kiện SQL phù hợp nếu bài toán là phủ định trên toàn bảng.

### 20.4. Boolean mode không tự sắp xếp theo relevance

Nếu giao diện cần bài phù hợp nhất trước, phải chọn score và ORDER BY score DESC. Không dựa vào thứ tự hàng trả về tình cờ.

### 20.5. Tìm một từ quá ngắn hoặc là stopword

Một token có thể không có trong FULLTEXT index vì cấu hình token size hoặc stopword. Kiểm tra cấu hình và parser trước khi kết luận MATCH() bị lỗi.

### 20.6. MATCH() không khớp FULLTEXT index

Với InnoDB, các cột trong MATCH() phải khớp một FULLTEXT index theo đúng danh sách và thứ tự. Nếu cần tìm nhiều tổ hợp cột, hãy thiết kế index tương ứng hoặc điều chỉnh truy vấn.

### 20.7. Kỳ vọng wildcard tìm chuỗi con

optim* tìm token bắt đầu bằng optim. Nó không tìm một chuỗi con xuất hiện ở giữa token. Dùng LIKE hoặc công cụ tìm kiếm khác nếu cần substring search.

### 20.8. Dùng @distance trên engine không hỗ trợ

@distance là tính năng proximity của InnoDB Boolean search. Kiểm tra storage engine và parser trước khi dùng.

### 20.9. Tưởng prepared statement vô hiệu hóa Boolean operators

Prepared statement ngăn dữ liệu làm thay đổi cấu trúc SQL, nhưng chuỗi được bind vẫn được FULLTEXT parser diễn giải. Nếu ứng dụng không muốn người dùng nhập toán tử, phải giới hạn grammar ở tầng ứng dụng.

### 20.10. Quên lọc quyền truy cập

FULLTEXT index không biết người dùng hiện tại có quyền xem tài liệu nào. Luôn kết hợp điều kiện tenant, trạng thái, ACL hoặc phạm vi dữ liệu theo thiết kế bảo mật.

## 21. Bài thực hành

Các bài tập dùng bảng articles và FULLTEXT index ft_articles_title_body ở phần đầu.

### 21.1. Bắt buộc có hai từ

Viết truy vấn chỉ trả về bài viết có cả mysql và index. Trả về article_id, title và relevance score; sắp xếp score giảm dần.

### 21.2. Loại trừ một chủ đề

Mở rộng truy vấn trước để loại tài liệu có oracle. Giải thích vì sao điều kiện này không tương đương với truy vấn tất cả hàng không có oracle.

### 21.3. Từ tùy chọn và từ bắt buộc

So sánh kết quả của ba biểu thức:

~~~text
mysql index
+mysql index
+mysql +index
~~~

Nêu rõ token nào bắt buộc và token nào tùy chọn trong từng biểu thức.

### 21.4. Thay đổi relevance

Viết truy vấn bắt buộc mysql, tăng trọng số index và giảm đóng góp của legacy. Sau đó thay toán tử giảm trọng số bằng toán tử loại trừ và so sánh tập hàng.

### 21.5. Tìm tiền tố

Tìm tài liệu có token bắt đầu bằng optim. Thử một tiền tố ngắn hơn và quan sát số lượng kết quả cũng như thời gian truy vấn.

### 21.6. Nhóm điều kiện

Viết biểu thức yêu cầu mysql và ít nhất một trong hai token index hoặc optimizer. Thử bỏ dấu + trước nhóm và giải thích sự thay đổi.

### 21.7. Tìm cụm từ và proximity

Tìm cụm query optimizer. Sau đó thử proximity search trên InnoDB với khoảng cách 5. So sánh kết quả và giải thích tại sao proximity không phải tìm kiếm ngữ nghĩa.

### 21.8. Kết hợp quyền truy cập

Viết truy vấn Boolean chỉ tìm nội dung phù hợp trong tenant_id của người dùng hiện tại và chỉ trả bài PUBLISHED. Giải thích vì sao tenant và status phải nằm trong điều kiện SQL.

### 21.9. Điều tra token không tìm thấy

Chọn một từ ngắn hoặc một stopword. Kiểm tra token size và stopword configuration. Giải thích vì sao thêm dấu + không thể bắt MySQL tìm token không có trong index.

### 21.10. Thiết kế grammar đầu vào

Đề xuất grammar cho ô tìm kiếm hỗ trợ:

- Từ bắt buộc.
- Từ loại trừ.
- Cụm từ.
- Nhóm điều kiện.

Nêu giới hạn số token, độ dài truy vấn và độ sâu nhóm. Phân biệt kiểm soát SQL injection với kiểm soát Boolean operators.

## 22. Checklist trước khi phát hành tìm kiếm Boolean

- [ ] Engine của bảng hỗ trợ FULLTEXT và đáp ứng cú pháp cần dùng.
- [ ] Có FULLTEXT index trên đúng cột được truyền vào MATCH().
- [ ] Với InnoDB, thứ tự cột trong MATCH() khớp index.
- [ ] Người dùng hiểu sự khác nhau giữa từ bắt buộc, từ tùy chọn và từ loại trừ.
- [ ] Biểu thức chỉ có từ loại trừ được xử lý theo đúng ý định sản phẩm.
- [ ] Dùng > và < để điều chỉnh relevance, không nhầm chúng với điều kiện bắt buộc.
- [ ] Dùng ~ để hạ điểm, không nhầm với toán tử loại trừ -.
- [ ] Dùng * ở cuối token khi tìm tiền tố.
- [ ] Dùng dấu ngoặc để nhóm điều kiện và kiểm thử biểu thức lồng nhau.
- [ ] Phrase search và @distance được kiểm tra trên parser/engine thực tế.
- [ ] Đã kiểm tra stopword list và token size.
- [ ] Đã kiểm tra parser với ngôn ngữ và dữ liệu thực tế.
- [ ] Đã rebuild FULLTEXT index sau thay đổi tokenization cần áp dụng.
- [ ] Có ORDER BY relevance DESC nếu sản phẩm cần xếp hạng.
- [ ] Có khóa phụ ổn định khi phân trang.
- [ ] Dùng prepared statement cho giá trị tìm kiếm và tham số SQL.
- [ ] Grammar Boolean được giới hạn theo tính năng giao diện.
- [ ] Tenant, ACL, trạng thái và các bộ lọc nghiệp vụ vẫn được áp dụng bằng SQL.
- [ ] Đã dùng EXPLAIN hoặc EXPLAIN ANALYZE trên dữ liệu đại diện.
- [ ] Đã đo số kết quả, thời gian truy vấn và chi phí cập nhật FULLTEXT index.

## Kết luận

Boolean mode cho phép điều khiển FULLTEXT search bằng toán tử. Dấu + yêu cầu token xuất hiện; dấu - loại token; token không có toán tử là tùy chọn; > và < điều chỉnh đóng góp relevance; ~ hạ điểm mà không loại hàng; * tìm tiền tố; ngoặc nhóm biểu thức; dấu quote tìm cụm từ; và @distance hỗ trợ proximity search trên InnoDB.

Kết quả cuối cùng luôn phụ thuộc token mà parser lập chỉ mục. Stopword, token size, engine và parser có thể làm một từ trong chuỗi truy vấn không tham gia tìm kiếm như mong đợi. Trong ứng dụng, hãy dùng prepared statement, kiểm soát grammar Boolean, áp dụng điều kiện phân quyền bằng SQL và sắp xếp relevance tường minh khi cần xếp hạng.
