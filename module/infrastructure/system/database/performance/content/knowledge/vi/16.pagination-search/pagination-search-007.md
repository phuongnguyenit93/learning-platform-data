# Tìm kiếm toàn văn: chỉ số liên quan, giới hạn kết quả và chi phí

Tìm kiếm toàn văn (full-text search) cho phép truy vấn nội dung ngôn ngữ tự nhiên trong các trường văn bản dài như tiêu đề, mô tả, bài viết, tài liệu hoặc ghi chú. DBMS thường xây dựng cấu trúc chỉ mục chuyên biệt để ánh xạ từ hoặc token sang các tài liệu chứa chúng. Nhờ đó, truy vấn không phải quét và tìm chuỗi trong mọi hàng như một phép so sánh văn bản thông thường. Tuy nhiên, một từ phổ biến có thể khớp với hàng triệu tài liệu; việc tính điểm liên quan, sắp xếp kết quả và đếm tổng số kết quả vẫn có thể rất tốn kém dù đã có full-text index.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Phân trang và tìm kiếm** giúp người học hiểu cách tổ chức full-text index, đọc chỉ số liên quan (relevance), đặt giới hạn kết quả và đánh giá chi phí của một truy vấn tìm kiếm. Bài học tập trung vào cách DBMS tách văn bản thành token, lập chỉ mục đảo, tìm tập ứng viên, tính điểm và chọn top-k; đồng thời phân tích tác động của ngôn ngữ, stopword, truy vấn phổ biến, phân trang sâu, exact count, bộ lọc metadata và chi phí duy trì index.

Sau bài học, người học có thể:

- Giải thích cách full-text search chuyển văn bản thành token/term và sử dụng inverted index.
- Phân biệt full-text index với B-tree index và tìm chuỗi bằng LIKE.
- Nhận biết các thành phần ảnh hưởng đến relevance như tần suất từ, độ dài tài liệu, vị trí và trọng số trường.
- Đọc kế hoạch thực thi để xác định số tài liệu ứng viên, số hàng được xếp hạng và chi phí sort.
- Hiểu vì sao LIMIT nhỏ không nhất thiết làm truy vấn tìm kiếm rẻ.
- Thiết kế giới hạn kết quả, phân trang và cách trả has-more phù hợp.
- Đánh giá exact count, ranking, phrase search, prefix search và các bộ lọc metadata.
- Cân bằng chi phí đọc, ghi, dung lượng, cache và bảo trì full-text index.
- Đo trước/sau bằng workload đại diện và kiểm tra chất lượng kết quả.

## 1. Full-text search giải quyết vấn đề gì?

### 1.1. Tìm chuỗi và tìm kiếm theo ngôn ngữ là hai việc khác nhau

Một điều kiện tìm chuỗi thông thường có thể viết:

~~~sql
SELECT article_id, title
FROM articles
WHERE body LIKE '%database performance%';
~~~

Với mẫu bắt đầu bằng ký tự đại diện, B-tree thông thường thường không thể định vị trực tiếp vị trí bắt đầu phù hợp. DBMS có thể phải quét nhiều hàng và kiểm tra nội dung từng hàng. Nếu body chứa văn bản dài, lượng dữ liệu phải đọc và so sánh có thể rất lớn.

Full-text search xử lý văn bản trước khi truy vấn. Engine thường tách văn bản thành token, chuẩn hóa chữ hoa/thường, loại bỏ một số từ phổ biến, áp dụng quy tắc ngôn ngữ hoặc stemming, rồi lưu quan hệ giữa term và tài liệu trong một inverted index.

Ví dụ, tài liệu:

~~~text
Database performance depends on indexes and query plans.
~~~

Có thể được phân tích thành các term chuẩn hóa như database, performance, depend, index và query plan, tùy cấu hình ngôn ngữ. Chỉ mục lưu danh sách tài liệu chứa từng term, đôi khi kèm vị trí hoặc thông tin trọng số.

Khi người dùng tìm từ database, DBMS có thể tra term trong inverted index để lấy tập tài liệu ứng viên thay vì quét toàn bộ văn bản.

### 1.2. Inverted index

B-tree thường sắp xếp khóa theo thứ tự để hỗ trợ tìm kiếm bằng khóa, phạm vi hoặc thứ tự. Inverted index tổ chức theo chiều ngược lại: từ mỗi term đến danh sách tài liệu chứa term đó.

Mô hình khái niệm:

~~~text
Tài liệu
  doc-1: "database index performance"
  doc-2: "query plan and database"
  doc-3: "index design for search"

             |
             v
       Phân tích văn bản
             |
             v
       Inverted index

  database -> [doc-1, doc-2]
  index    -> [doc-1, doc-3]
  performance -> [doc-1]
  query    -> [doc-2]
  search   -> [doc-3]
~~~

Đây là mô hình đơn giản. Full-text index thực tế có thể lưu thêm tần suất term, vị trí token, thông tin trường, trọng số hoặc cấu trúc nén. Các chi tiết phụ thuộc DBMS và loại index.

### 1.3. Full-text index khác B-tree index

B-tree phù hợp với các điều kiện như:

- So sánh bằng trên một giá trị có kiểu dữ liệu phù hợp.
- Tìm phạm vi số hoặc thời gian.
- Sắp xếp theo khóa.
- Tra cứu prefix trong một số collation và dạng truy vấn phù hợp.

Full-text index phù hợp với:

- Tìm một hoặc nhiều từ trong văn bản dài.
- Tìm các term xuất hiện cùng nhau.
- Tìm cụm từ hoặc gần nhau nếu engine hỗ trợ.
- Tính điểm liên quan.
- Tìm theo từ đã chuẩn hóa hoặc dạng ngôn ngữ.

Full-text index không thay thế mọi index khác. Một truy vấn tìm tài liệu theo tenant, trạng thái và nội dung có thể cần cả B-tree cho metadata lẫn full-text index cho nội dung. Optimizer có thể kết hợp các access path nếu engine hỗ trợ và ước lượng chi phí phù hợp.

### 1.4. Full-text search khác tìm chuỗi con

Tìm chuỗi con như '%perf%' có nghĩa là tìm mọi vị trí chứa dãy ký tự perf, kể cả bên trong một từ. Full-text search thường tìm token đã được phân tích, nên không nhất thiết khớp chuỗi con tùy ý.

Ví dụ, tìm performance có thể không tìm thấy perform nếu stemming, tokenizer hoặc cấu hình ngôn ngữ không tạo ra quan hệ phù hợp. Ngược lại, tìm một token có thể khớp nhiều biến thể từ nếu engine áp dụng stemming.

Nếu yêu cầu là tìm một đoạn ký tự bất kỳ, cần đánh giá công cụ phù hợp như trigram index, n-gram parser hoặc search engine chuyên dụng. Không nên ép full-text index xử lý một yêu cầu substring mà semantics của nó không hỗ trợ.

## 2. Tokenization, ngôn ngữ và chất lượng chỉ mục

### 2.1. Tokenization

Tokenization là quá trình tách văn bản thành đơn vị tìm kiếm. Quy tắc tách phụ thuộc ngôn ngữ, dấu câu, ký tự Unicode, dấu gạch nối, số, tên riêng và parser.

Ví dụ:

~~~text
"high-performance database, SQL Server 2026"
~~~

Parser có thể tạo các token khác nhau tùy cấu hình: high, performance, database, SQL, Server, 2026 hoặc một tổ hợp khác. Khi thiết kế hệ thống tìm kiếm, phải xác định cách parser xử lý dấu gạch nối, email, URL, mã sản phẩm và tên riêng.

Với tiếng Việt, ranh giới từ không đơn giản như việc tách theo khoảng trắng trong mọi trường hợp. Nhiều từ đa âm tiết được viết cách nhau bằng dấu cách, nên tokenizer chỉ tách theo khoảng trắng có thể làm mất đơn vị từ vựng mong muốn. Cần kiểm tra khả năng parser tiếng Việt của DBMS hoặc dùng bộ phân tích/ngữ đoạn phù hợp nếu yêu cầu tìm kiếm tiếng Việt có chất lượng cao.

### 2.2. Chuẩn hóa chữ hoa/thường và dấu

Full-text engine thường chuẩn hóa một số đặc điểm văn bản để từ có cách viết khác nhau có thể được so khớp. Nhưng quy tắc bỏ dấu, chuẩn hóa Unicode hoặc xử lý chữ ghép không giống nhau giữa các DBMS.

Ví dụ, người dùng có thể nhập từ có dấu hoặc không dấu. Nếu sản phẩm yêu cầu cả hai cách tìm phải cho kết quả tương đương, cần thiết kế analyzer, cột chuẩn hóa hoặc hệ thống search hỗ trợ điều đó. Không nên giả định full-text index mặc định luôn xử lý tiếng Việt không dấu theo mong muốn.

### 2.3. Stopword

Stopword là những từ phổ biến thường bị loại khỏi chỉ mục hoặc bị giảm vai trò trong tìm kiếm, chẳng hạn một số từ nối hoặc giới từ. Việc loại stopword có thể giảm kích thước index và tránh truy vấn tạo tập ứng viên quá lớn cho các từ ít mang ý nghĩa phân biệt.

Nhưng stopword cũng ảnh hưởng semantics. Nếu người dùng tìm cụm từ có chứa từ phổ biến, engine có thể xử lý cụm từ theo quy tắc riêng. Một truy vấn chỉ chứa stopword có thể trả về ít kết quả, không có kết quả hoặc bị xem là truy vấn rỗng tùy hệ thống.

Cần kiểm tra:

- Danh sách stopword theo ngôn ngữ.
- Cách engine xử lý truy vấn chỉ có stopword.
- Ảnh hưởng tới phrase search.
- Khả năng tùy chỉnh stopword và thời điểm rebuild index khi thay đổi.
- Sự nhất quán giữa analyzer khi index và analyzer khi truy vấn.

### 2.4. Stemming và từ đồng nghĩa

Stemming đưa các biến thể của từ về một dạng gốc gần đúng. Ví dụ, một số ngôn ngữ có thể gom các dạng số ít/số nhiều hoặc biến thể chia động từ. Lemmatization sử dụng phân tích ngôn ngữ sâu hơn để đưa từ về dạng từ điển.

Synonym expansion cho phép một truy vấn khớp từ đồng nghĩa hoặc thuật ngữ tương đương. Các cơ chế này có thể cải thiện recall nhưng làm tăng số term và số tài liệu ứng viên, đồng thời có thể thay đổi thứ tự relevance.

Không nên bật stemming hoặc synonym một cách tùy tiện. Cần kiểm thử trên bộ truy vấn và tài liệu thực tế, đặc biệt với tên sản phẩm, mã kỹ thuật, tên người và thuật ngữ nghiệp vụ.

### 2.5. Cấu hình index và query phải nhất quán

Nếu lúc lập chỉ mục dùng một cấu hình ngôn ngữ nhưng lúc truy vấn dùng cấu hình khác, term có thể không khớp như mong đợi. Điều này dẫn đến truy vấn thiếu kết quả hoặc chất lượng ranking không ổn định.

Cần ghi nhận cấu hình analyzer, parser, language, stopword và synonym cùng với phiên bản dữ liệu. Khi thay đổi cấu hình, có thể phải tái lập chỉ mục hoặc cập nhật vector đã lưu. Hãy tính chi phí build lại, dung lượng tạm, I/O và thời gian hệ thống chịu tải.

## 3. Các mô hình full-text index theo DBMS

Tên gọi và cách thực hiện full-text search khác nhau giữa hệ quản trị. Không nên áp dụng cú pháp hoặc giả định của một engine cho engine khác.

### 3.1. PostgreSQL: tsvector và GIN

PostgreSQL cung cấp kiểu tsvector để lưu các term đã chuẩn hóa và kiểu tsquery để biểu diễn truy vấn tìm kiếm. Hàm to_tsvector phân tích văn bản; plainto_tsquery, phraseto_tsquery và websearch_to_tsquery tạo biểu thức truy vấn theo những cách khác nhau.

Ví dụ tạo cột tìm kiếm:

~~~sql
ALTER TABLE articles
ADD COLUMN search_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'B')
) STORED;
~~~

Ở đây, title được gán trọng số A và body được gán trọng số B. Trọng số là đầu vào cho các hàm ranking; chúng không tự bảo đảm mọi truy vấn tiêu đề sẽ luôn đứng trước mọi truy vấn nội dung.

Tạo GIN index:

~~~sql
CREATE INDEX idx_articles_search_vector
ON articles
USING GIN (search_vector);
~~~

GIN thường là lựa chọn phổ biến cho tìm kiếm toàn văn vì có thể tra term và danh sách tài liệu chứa term hiệu quả. PostgreSQL cũng hỗ trợ GiST cho full-text search, nhưng GiST dùng chữ ký có thể mất thông tin và cần recheck; GIN thường có đặc tính phù hợp hơn cho workload tìm kiếm term phổ biến.

Truy vấn:

~~~sql
SELECT article_id, title
FROM articles
WHERE search_vector @@ websearch_to_tsquery('english', 'database performance');
~~~

Toán tử @@ kiểm tra tsvector có khớp tsquery hay không. Query parser và cú pháp truy vấn ảnh hưởng đến cách kết hợp term, phrase và toán tử.

### 3.2. PostgreSQL: tính relevance

Có thể dùng ts_rank hoặc ts_rank_cd để tính điểm:

~~~sql
SELECT
    article_id,
    title,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('english', 'database performance')
    ) AS relevance
FROM articles
WHERE search_vector @@ websearch_to_tsquery('english', 'database performance')
ORDER BY relevance DESC, article_id
LIMIT 20;
~~~

Điểm rank là một hàm tính toán dựa trên vector và query; không nên xem nó là xác suất hoặc thước đo chất lượng tuyệt đối. Trọng số, độ dài tài liệu, tần suất term và cách chuẩn hóa có thể ảnh hưởng kết quả.

GIN index giúp tìm các tài liệu khớp term, nhưng không lưu sẵn thứ tự theo ts_rank_cd. DBMS thường vẫn cần tính điểm cho các tài liệu ứng viên rồi chọn top kết quả. Nếu query khớp hàng trăm nghìn tài liệu, LIMIT 20 không có nghĩa chỉ 20 tài liệu được đánh giá.

### 3.3. PostgreSQL: expression index và cấu hình

Nếu không lưu cột tsvector, có thể tạo expression index:

~~~sql
CREATE INDEX idx_articles_body_fts
ON articles
USING GIN (to_tsvector('english', coalesce(body, '')));
~~~

Truy vấn cần dùng biểu thức tương thích để optimizer có thể nhận diện index. Dùng cấu hình ngôn ngữ rõ ràng giúp tính ổn định và tránh phụ thuộc cấu hình mặc định theo session.

Expression index có thể tiết kiệm cột lưu trữ riêng nhưng biểu thức phải được tính khi cập nhật hàng và index phải được duy trì. Cột tsvector được lưu có thể hữu ích khi nhiều truy vấn cần tái sử dụng vector hoặc cần gán trọng số nhiều trường; đổi lại nó chiếm thêm dung lượng bảng.

### 3.4. MySQL InnoDB: FULLTEXT

MySQL InnoDB hỗ trợ FULLTEXT index trên các cột văn bản thuộc kiểu được hỗ trợ. Truy vấn thường dùng MATCH ... AGAINST.

Ví dụ:

~~~sql
CREATE TABLE articles (
    article_id BIGINT PRIMARY KEY,
    title VARCHAR(500),
    body TEXT,
    FULLTEXT KEY ft_articles_title_body (title, body)
) ENGINE = InnoDB;
~~~

Truy vấn natural language:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('database performance' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body)
        AGAINST ('database performance' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC
LIMIT 20;
~~~

Danh sách cột trong MATCH cần phù hợp với FULLTEXT index được dùng. MySQL có các chế độ truy vấn khác nhau như natural language và boolean mode. Token size, stopword, parser và collation có thể ảnh hưởng term nào được index và tìm thấy.

InnoDB có các giới hạn và quy tắc tokenization riêng theo phiên bản. Với tiếng Trung, Nhật hoặc Hàn và một số yêu cầu phân đoạn từ, có thể cần ngram parser. Hãy kiểm tra cấu hình thực tế thay vì giả định parser mặc định phù hợp với mọi ngôn ngữ.

### 3.5. SQL Server: Full-Text Catalog và CONTAINS

SQL Server sử dụng full-text catalog và full-text index để lập chỉ mục nội dung. Các predicate như CONTAINS và FREETEXT cho phép tìm theo term, cụm từ hoặc dạng ngôn ngữ tùy cú pháp.

Ví dụ truy vấn:

~~~sql
SELECT
    a.ArticleId,
    a.Title
FROM dbo.Articles AS a
WHERE CONTAINS((a.Title, a.Body), '"database performance"');
~~~

Để lấy điểm rank, có thể dùng CONTAINSTABLE:

~~~sql
SELECT
    a.ArticleId,
    a.Title,
    ft.[RANK]
FROM CONTAINSTABLE(
    dbo.Articles,
    (Title, Body),
    '"database performance"',
    LANGUAGE 1033,
    100
) AS ft
JOIN dbo.Articles AS a
    ON a.ArticleId = ft.[KEY]
ORDER BY ft.[RANK] DESC, a.ArticleId;
~~~

Tham số top_n_by_rank trong CONTAINSTABLE có thể giới hạn số khóa được trả về theo rank. Cần hiểu rằng đây là cơ chế riêng của SQL Server; không thể suy ra hành vi tương đương từ LIMIT của PostgreSQL hoặc MySQL.

SQL Server dùng word breaker, stemmer và stoplist theo ngôn ngữ. Full-text population có thể được quản lý theo change tracking hoặc lịch cập nhật. Độ trễ cập nhật index cần được tính vào yêu cầu tìm kiếm gần thời gian thực.

### 3.6. Oracle Text

Oracle Text cung cấp các loại index như CONTEXT để tìm kiếm văn bản qua operator CONTAINS và tính điểm qua SCORE. Cấu hình lexer, stoplist, section group và cách đồng bộ index ảnh hưởng đến semantics và độ trễ cập nhật.

Một ví dụ khái quát:

~~~sql
SELECT
    article_id,
    title,
    SCORE(1) AS relevance
FROM articles
WHERE CONTAINS(body, 'database AND performance', 1) > 0
ORDER BY relevance DESC;
~~~

Cách đồng bộ index, tham số lexer và khả năng dùng các tính năng phụ thuộc phiên bản Oracle Text. Cần xem tài liệu của phiên bản đang vận hành và chính sách license của môi trường.

### 3.7. So sánh khái quát

| DBMS | Cấu trúc/cú pháp phổ biến | Điểm cần chú ý |
|---|---|---|
| PostgreSQL | tsvector, tsquery, GIN/GiST, ts_rank | GIN tìm term nhưng không sắp sẵn theo rank; cần xem candidate count và sort |
| MySQL InnoDB | FULLTEXT, MATCH ... AGAINST | Token size, stopword, parser và chế độ tìm ảnh hưởng kết quả |
| SQL Server | Full-Text Catalog, CONTAINS, CONTAINSTABLE | Top-N theo rank có cú pháp riêng; population và word breaker cần theo dõi |
| Oracle Text | CONTEXT, CONTAINS, SCORE | Lexer, stoplist và cơ chế sync ảnh hưởng nội dung được tìm |

Các engine có ranking và parser khác nhau. Không so sánh điểm relevance trực tiếp giữa chúng nếu chưa chuẩn hóa bộ truy vấn, tài liệu và tiêu chí đánh giá.

## 4. Chỉ số liên quan (relevance) và chi phí xếp hạng

### 4.1. Relevance là điểm xếp hạng, không phải xác suất

Relevance score giúp sắp xếp tài liệu theo mức độ phù hợp với truy vấn. Công thức có thể dựa trên:

- Tần suất term trong tài liệu.
- Mức phổ biến của term trong toàn bộ tập tài liệu.
- Độ dài tài liệu.
- Vị trí term hoặc khoảng cách giữa các term.
- Trọng số trường như title, heading hoặc body.
- Các tín hiệu bổ sung của engine hoặc ứng dụng.

Một điểm 0,8 không có nghĩa tài liệu đúng 80%. Điểm thường chỉ có ý nghĩa tương đối trong cùng truy vấn, cùng cấu hình và cùng engine. Không nên đặt ngưỡng relevance cố định rồi áp dụng cho mọi truy vấn nếu chưa kiểm thử.

### 4.2. Tập ứng viên và tập kết quả cuối

Quy trình tìm kiếm có thể chia thành:

1. Phân tích query thành term và toán tử.
2. Dùng inverted index để lấy tập tài liệu ứng viên.
3. Áp dụng các điều kiện bổ sung và kiểm tra phù hợp.
4. Tính relevance cho tài liệu ứng viên.
5. Sắp xếp hoặc chọn top-k.
6. Đọc các cột cần trả về và gửi kết quả cho ứng dụng.

Tập ứng viên có thể lớn hơn nhiều so với số kết quả trả về. Nếu một từ rất phổ biến xuất hiện trong 70% tài liệu, truy vấn chỉ chứa từ đó có thể tạo candidate set rất lớn. Nếu truy vấn gồm các term hiếm kết hợp bằng AND, candidate set thường nhỏ hơn, nhưng điều này phụ thuộc semantics và thống kê.

### 4.3. Ranking có thể là phần tốn kém sau khi index đã tìm được tài liệu

Full-text index giúp thu hẹp dữ liệu, nhưng ranking có thể cần đọc vector hoặc thông tin tài liệu và tính điểm cho mỗi ứng viên. Sau đó DBMS phải tìm top-k theo score.

Ví dụ, truy vấn khớp 400.000 tài liệu nhưng chỉ trả 20 kết quả. DBMS có thể phải tính rank cho một tập lớn rồi duy trì cấu trúc chọn top 20. Thuật toán top-N sort có thể giảm bộ nhớ so với sort toàn bộ, nhưng vẫn phải xem xét nhiều ứng viên để biết tài liệu nào có điểm cao nhất nếu index không cung cấp thứ tự rank.

Do đó, hai truy vấn cùng trả 20 hàng có thể có chi phí rất khác nhau nếu một truy vấn khớp 30 tài liệu và truy vấn kia khớp 400.000 tài liệu.

### 4.4. Trọng số trường và độ dài tài liệu

Một hệ thống có thể muốn tiêu đề quan trọng hơn nội dung. Trong PostgreSQL, setweight có thể gán trọng số khác nhau cho các phần tsvector; hàm rank sử dụng các trọng số này. Các engine khác có cơ chế field weighting hoặc ranking riêng.

Tài liệu dài có nhiều cơ hội chứa term hơn. Công thức ranking có thể chuẩn hóa theo độ dài để tránh tài liệu dài luôn được ưu tiên, nhưng cách chuẩn hóa khác nhau. Nếu ứng dụng tự kết hợp điểm full-text với popularity, freshness hoặc business score, cần chuẩn hóa và kiểm thử từng thành phần.

Một công thức ứng dụng minh họa:

\[
Score = w_r \times Relevance
      + w_f \times Freshness
      + w_p \times Popularity
\]

Đây là mô hình ví dụ. Các trọng số w_r, w_f và w_p phải được hiệu chỉnh bằng bộ truy vấn đánh giá và mục tiêu sản phẩm. Khi đưa tín hiệu bên ngoài vào, DBMS có thể phải tính biểu thức và sort trên nhiều ứng viên; chi phí ranking tổng hợp cũng cần được đo.

### 4.5. Phrase search và proximity

Phrase search yêu cầu các từ xuất hiện theo thứ tự hoặc trong một khoảng cách nhất định. Proximity search cho phép các term gần nhau trong tài liệu.

Các truy vấn này thường cần thông tin vị trí token hoặc kiểm tra thêm sau khi lấy ứng viên. Một inverted index chỉ lưu danh sách tài liệu có term có thể chưa đủ để xác nhận phrase; engine cần dữ liệu vị trí hoặc bước recheck.

Truy vấn phrase có thể giảm số kết quả nhưng tăng chi phí kiểm tra trên mỗi ứng viên. Hãy đo cả candidate count và số tài liệu thực sự vượt qua điều kiện phrase.

## 5. Vì sao LIMIT nhỏ không luôn làm tìm kiếm rẻ?

### 5.1. LIMIT giới hạn đầu ra, không nhất thiết giới hạn công việc đầu vào

Câu truy vấn:

~~~sql
SELECT article_id, title
FROM articles
WHERE search_vector @@ websearch_to_tsquery('english', 'database')
ORDER BY ts_rank_cd(
    search_vector,
    websearch_to_tsquery('english', 'database')
) DESC
LIMIT 20;
~~~

chỉ trả tối đa 20 hàng. Nhưng để biết 20 hàng nào có rank cao nhất, DBMS thường phải tìm các tài liệu phù hợp, tính điểm và so sánh ứng viên. Nếu full-text index không lưu thứ tự theo score, engine không thể dừng ngay khi gặp 20 hàng đầu tiên theo thứ tự bất kỳ.

LIMIT có thể giảm:

- Số hàng cuối cùng gửi về client.
- Số hàng cần giữ trong top-N structure so với sort toàn bộ, tùy kế hoạch.
- Số lần đọc cột payload nếu truy vấn được viết và optimizer có thể trì hoãn việc lấy chi tiết.

LIMIT không nhất thiết giảm:

- Số term phải tra trong inverted index.
- Số tài liệu ứng viên phải hợp nhất hoặc kiểm tra.
- Số tài liệu cần tính rank.
- Số trang phải đọc để xác định top-k.
- Chi phí exact count nếu ứng dụng yêu cầu tổng số kết quả.

### 5.2. Top-N sort và full sort

Khi cần ORDER BY rank DESC LIMIT 20, optimizer có thể dùng thuật toán top-N heapsort hoặc top-N sort thay vì sắp xếp toàn bộ danh sách. Cách này giảm bộ nhớ cần giữ kết quả và có thể giảm số phép so sánh so với full sort.

Tuy nhiên, nếu score được tính cho mọi ứng viên, DBMS vẫn phải duyệt candidate set để xác định top 20. Top-N sort không biến full-text search thành truy cập trực tiếp 20 hàng.

Trong execution plan, hãy xem:

- Số dòng đầu vào Sort.
- Số dòng đầu ra sau Limit.
- Sort Method, memory hoặc spill.
- Thời gian tính rank và tổng thời gian.
- Buffer reads/hits và temporary I/O.
- Có bộ lọc metadata nào được áp dụng trước ranking không.

### 5.3. Đếm tổng số kết quả có thể đắt

Giao diện thường muốn hiển thị “1.234 kết quả”. Để có exact count, DBMS có thể phải đánh giá toàn bộ predicate tìm kiếm và đếm mọi tài liệu phù hợp. Việc này có thể tốn gần bằng hoặc nhiều hơn truy vấn lấy top-k, nhất là khi candidate set lớn.

Nếu sản phẩm chỉ cần biết còn trang tiếp theo hay không, có thể lấy limit + 1 hàng. Ví dụ cần 20 kết quả thì yêu cầu 21; nếu nhận được 21, đặt has_more = true và chỉ hiển thị 20. Cách này tránh yêu cầu exact count cho mọi lần tìm kiếm.

Nếu giao diện thực sự cần tổng số chính xác, hãy đo riêng truy vấn count và cân nhắc cache, count gần đúng hoặc tính theo thời điểm. Không nên chạy COUNT(*) độc lập cho mọi request mà không đánh giá tải.

### 5.4. Bộ lọc metadata và thứ tự áp dụng

Tìm kiếm thường kết hợp nội dung với metadata:

- Tenant hoặc tổ chức.
- Trạng thái đã xuất bản.
- Loại tài liệu.
- Khoảng thời gian.
- Quyền truy cập.
- Ngôn ngữ.
- Danh mục hoặc sản phẩm.

Nếu chỉ tìm toàn văn rồi mới lọc metadata, DBMS có thể tạo tập ứng viên lớn hơn cần thiết. Một số engine có thể kết hợp full-text access path với B-tree hoặc bitmap filter; khả năng và thứ tự thực thi phụ thuộc optimizer.

Ví dụ PostgreSQL:

~~~sql
SELECT article_id, title
FROM articles
WHERE tenant_id = 42
  AND status = 'PUBLISHED'
  AND search_vector @@ websearch_to_tsquery('english', 'database performance')
ORDER BY ts_rank_cd(
    search_vector,
    websearch_to_tsquery('english', 'database performance')
) DESC
LIMIT 20;
~~~

B-tree index trên tenant_id/status có thể hỗ trợ lọc metadata; GIN hỗ trợ full-text. PostgreSQL có thể kết hợp bitmap từ các index nếu chi phí ước lượng phù hợp. Nhưng không có bảo đảm mọi trường hợp sẽ dùng bitmap AND; cần đọc plan và thống kê.

Quyền truy cập là điều kiện đúng đắn và bảo mật. Không được lấy top-k toàn cục rồi lọc quyền sau đó nếu điều đó có thể bỏ sót tài liệu hợp lệ ở phía sau hoặc làm rò rỉ thông tin qua count/rank. Predicate quyền phải được áp dụng đúng trong semantics truy vấn.

## 6. Phân trang kết quả tìm kiếm

### 6.1. OFFSET/LIMIT

Một cách phân trang phổ biến:

~~~sql
SELECT article_id, title
FROM articles
WHERE search_vector @@ websearch_to_tsquery('english', 'database performance')
ORDER BY ts_rank_cd(
    search_vector,
    websearch_to_tsquery('english', 'database performance')
) DESC, article_id
LIMIT 20 OFFSET 1000;
~~~

OFFSET yêu cầu DBMS bỏ qua các hàng trước vị trí bắt đầu rồi trả trang hiện tại. Với kết quả được sắp theo rank tính toán, engine có thể vẫn phải xử lý nhiều hoặc toàn bộ ứng viên để xếp hạng. OFFSET lớn làm tăng công việc bỏ qua và có thể khiến truy vấn trang sâu chậm hơn.

Nếu rank được tính từ full-text vector và không có index lưu sẵn thứ tự rank cho từng query, chuyển từ OFFSET sang keyset không tự loại bỏ chi phí tính rank trên candidate set. Tuy nhiên, keyset có thể tránh việc sắp xếp và bỏ qua một đoạn đầu trong một số kế hoạch hoặc khi kết quả đã được materialize/cached.

### 6.2. Keyset pagination

Keyset pagination dùng giá trị của hàng cuối trang trước để yêu cầu các hàng tiếp theo. Với sắp xếp theo thời gian, ví dụ:

~~~sql
SELECT article_id, title, created_at
FROM articles
WHERE tenant_id = 42
  AND created_at < TIMESTAMP '2026-10-01 10:00:00'
ORDER BY created_at DESC, article_id DESC
LIMIT 20;
~~~

Ở trang tiếp theo, cursor gồm created_at và article_id của hàng cuối trang trước. Index phù hợp trên (tenant_id, created_at DESC, article_id DESC) có thể hỗ trợ tiếp tục từ vị trí đó.

Với relevance score được tính động, cursor có thể gồm score và khóa duy nhất:

~~~sql
WHERE relevance < :last_score
   OR (relevance = :last_score AND article_id > :last_article_id)
ORDER BY relevance DESC, article_id ASC
LIMIT 20;
~~~

Đây là mô tả logic; không thể dùng alias relevance trong WHERE cùng cấp ở mọi DBMS, và việc tính score có thể phải lặp lại qua CTE/subquery. Quan trọng hơn, nếu rank vẫn phải tính cho toàn bộ candidate set thì keyset không loại bỏ phần chi phí đó. Nó giúp phân trang ổn định và tránh OFFSET lớn trong một số kiến trúc, nhưng cần đo thực tế.

### 6.3. Sắp xếp ổn định và tie-breaker

Nếu chỉ ORDER BY relevance DESC, nhiều tài liệu có cùng điểm có thể xuất hiện ở thứ tự không ổn định giữa các lần chạy. Khi phân trang, điều này có thể làm lặp hoặc bỏ sót kết quả.

Thêm một khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY relevance DESC, article_id ASC
~~~

Cursor cần lưu cả relevance và article_id. Cũng cần xác định cách xử lý khi nội dung tài liệu thay đổi làm score thay đổi giữa hai lần tải trang. Nếu cần snapshot ổn định, có thể phải lưu tập kết quả hoặc phiên tìm kiếm trong một khoảng thời gian.

### 6.4. Giới hạn độ sâu phân trang

Tìm kiếm thường không cần cho phép người dùng đi đến hàng triệu kết quả bằng số trang. Có thể:

- Giới hạn số trang hoặc độ sâu tối đa.
- Khuyến khích lọc hẹp hơn khi candidate set quá lớn.
- Dùng cursor thay cho offset ở các luồng phù hợp.
- Trả has_more thay vì exact total.
- Cache kết quả hoặc snapshot cho phiên tìm kiếm dài.
- Yêu cầu thêm từ khóa khi truy vấn quá rộng.

Giới hạn phải phản ánh yêu cầu sản phẩm. Không đặt LIMIT quá thấp khiến người dùng không tìm thấy tài liệu hợp lệ, nhưng cũng không để truy vấn phổ biến gây tải không kiểm soát.

## 7. Kiểm soát truy vấn rộng và từ khóa phổ biến

### 7.1. Từ phổ biến tạo candidate set lớn

Một từ như database hoặc product có thể xuất hiện trong tỷ lệ lớn tài liệu. Truy vấn chỉ gồm từ này có thể tạo candidate set rất lớn, làm tăng:

- Số posting list phải đọc.
- Công việc giao các danh sách term.
- Số tài liệu cần xác minh phrase hoặc điều kiện bổ sung.
- Số lần tính relevance.
- Công việc sort/top-N.

Các truy vấn nhiều term có thể thu hẹp tập kết quả tùy toán tử AND/OR và analyzer. Tuy nhiên, không nên tự động yêu cầu mọi từ phải xuất hiện nếu sản phẩm cần tìm kiếm linh hoạt.

### 7.2. Truy vấn rỗng hoặc chỉ có stopword

Người dùng có thể gửi chuỗi rỗng, chỉ chứa dấu câu hoặc các từ bị analyzer loại bỏ. Nếu ứng dụng không kiểm tra, truy vấn có thể trả không kết quả, lỗi hoặc hành vi không mong muốn.

Nên:

- Chuẩn hóa input trước khi gửi DBMS.
- Phát hiện query không còn term hữu ích sau phân tích nếu API hỗ trợ.
- Trả hướng dẫn nhập thêm từ khóa.
- Đặt giới hạn độ dài query và số term.
- Kiểm tra truy vấn có wildcard hoặc toán tử quá rộng.
- Không tự động chạy truy vấn rỗng thành full scan.

### 7.3. Boolean query và wildcard

Boolean search có thể cho phép AND, OR, NOT, prefix hoặc các toán tử nâng cao. Một truy vấn wildcard/prefix quá rộng có thể khớp rất nhiều term trong dictionary. Chi phí phụ thuộc cách engine mở rộng term và cấu trúc index.

Cần giới hạn:

- Số toán tử và độ sâu biểu thức.
- Prefix quá ngắn.
- Wildcard ở đầu từ nếu engine phải mở rộng rất nhiều term.
- Số term được mở rộng.
- Truy vấn chứa nhiều nhánh OR.
- Query syntax không hợp lệ hoặc quá dài.

Không nên tự ghép chuỗi query bằng cách nối input thô nếu cú pháp full-text có toán tử. Dùng parameter binding và parser phù hợp để tránh lỗi cú pháp, injection và truy vấn ngoài ý muốn.

### 7.4. Rate limit và concurrency

Một truy vấn tìm kiếm rộng có thể tốn CPU và I/O hơn truy vấn tra cứu khóa. Khi nhiều người dùng gửi truy vấn phổ biến cùng lúc, DBMS có thể bị bão hòa dù mỗi request chỉ trả 10 hoặc 20 kết quả.

Có thể cần:

- Rate limit theo user, tenant hoặc API key.
- Giới hạn concurrency của endpoint tìm kiếm.
- Timeout và cancellation phù hợp.
- Cache cho truy vấn phổ biến nếu freshness cho phép.
- Hạn chế exact count và phân trang sâu.
- Giám sát query latency và số candidate/returned.
- Cách ly workload tìm kiếm nặng khỏi transaction OLTP quan trọng khi cần.

Rate limit phải công bằng và phù hợp với yêu cầu sản phẩm; timeout không thay thế việc tối ưu query.

## 8. Chi phí duy trì full-text index

### 8.1. INSERT và UPDATE văn bản

Khi nội dung mới được thêm, DBMS phải phân tích văn bản, tạo token và cập nhật inverted index. Khi title hoặc body thay đổi, engine phải cập nhật các term liên quan. Một tài liệu dài có nhiều term và vị trí có thể tạo nhiều entry hơn tài liệu ngắn.

Chi phí phụ thuộc:

- Độ dài văn bản.
- Số trường được index.
- Số term duy nhất và tần suất term.
- Parser, stemming, synonym và stopword.
- Số lượng index hoặc cột full-text.
- Cách engine đồng bộ index.
- Tốc độ ghi và mức đồng thời.

Nếu ứng dụng cập nhật body thường xuyên nhưng chỉ tìm theo title, cần đánh giá xem có nên index body liên tục hay tách nội dung thay đổi nhanh sang cấu trúc khác.

### 8.2. DELETE và cập nhật chỉ mục nền

Xóa tài liệu hoặc thay đổi term có thể tạo công việc loại bỏ posting và dọn dẹp cấu trúc. Một số engine dùng cơ chế nền hoặc population queue; index có thể không phản ánh thay đổi ngay lập tức tùy chế độ cập nhật.

SQL Server full-text population có thể theo change tracking và cơ chế population. Oracle Text có các tùy chọn đồng bộ index. PostgreSQL GIN có pending list khi fastupdate được bật. MySQL InnoDB cập nhật full-text index theo cơ chế riêng của engine.

Cần xác định độ trễ chấp nhận được giữa lúc tài liệu thay đổi và lúc tìm kiếm thấy nội dung mới. Nếu yêu cầu near-real-time, phải đo thời gian cập nhật index và tải nền.

### 8.3. PostgreSQL GIN: pending list và fastupdate

GIN hỗ trợ fastupdate bằng cách đưa thay đổi vào pending list rồi hợp nhất vào cấu trúc chính theo cơ chế phù hợp. Điều này có thể giảm chi phí cập nhật đồng bộ trong một số workload, nhưng pending list lớn có thể làm truy vấn phải xem thêm dữ liệu hoặc khiến công việc cleanup/merge tạo đột biến I/O.

Cần theo dõi kích thước pending list, thời gian cleanup, autovacuum và latency truy vấn/ghi. Tắt fastupdate không phải lúc nào cũng tốt hơn; thay đổi cấu hình cần dựa trên tỷ lệ đọc/ghi và hành vi tải.

### 8.4. Dung lượng và cache

Inverted index có thể lớn do lưu term, posting list, vị trí và metadata. Một corpus lớn với nhiều từ duy nhất hoặc nhiều trường được index có thể chiếm dung lượng đáng kể.

Index lớn làm tăng:

- Dung lượng lưu trữ và backup.
- Số trang cần cache.
- Buffer reads khi truy vấn.
- Thời gian build/rebuild.
- Chi phí replication và khôi phục.
- Áp lực lên cache của các index B-tree và dữ liệu OLTP khác.

Không nên index mọi trường văn bản dài theo mặc định. Chỉ index những trường có giá trị tìm kiếm và xác định cách xếp hạng phù hợp.

### 8.5. Tách nội dung tìm kiếm khỏi payload lớn

Nếu body là tài liệu rất lớn, truy vấn tìm kiếm thường chỉ cần ID, title, score và một đoạn trích. Có thể tìm top-k ID trước rồi lấy payload cần thiết sau. Điều này giảm lượng dữ liệu lớn phải đi qua sort hoặc hash và giảm network transfer.

Tuy nhiên, nếu DBMS phải fetch body cho mọi candidate trước khi tính rank, việc tách query cần được kiểm tra kỹ. Hãy xem execution plan, projection và thời điểm truy cập heap/table. Chỉ lấy các cột cần hiển thị sau khi đã xác định top-k khi có thể.

## 9. Kết hợp full-text với metadata và phân vùng

### 9.1. Lọc tenant và trạng thái

Một bảng tài liệu đa tenant có thể cần điều kiện tenant_id, status, language và full-text query. Nếu query chỉ tìm term toàn cục rồi lọc tenant sau, lượng candidate có thể lớn.

Cần xem DBMS có thể kết hợp full-text index với B-tree hoặc partition pruning hay không. Với PostgreSQL, planner có thể dùng bitmap index combination trong các trường hợp phù hợp. Với SQL Server, full-text key có thể được join với bảng và filter metadata. Với MySQL, kế hoạch kết hợp FULLTEXT với các điều kiện khác có thể khác theo phiên bản và optimizer.

Không giả định engine luôn đẩy mọi filter vào inverted index. Hãy đọc actual plan và số dòng sau mỗi bước.

### 9.2. Partial index hoặc filtered index theo trạng thái

Nếu chỉ tìm tài liệu đã xuất bản, một partial/filtered index hoặc cấu trúc tách riêng có thể giảm phạm vi tìm kiếm, nếu DBMS hỗ trợ và optimizer chứng minh được predicate.

Ví dụ PostgreSQL có thể tạo GIN index chỉ trên hàng đã xuất bản:

~~~sql
CREATE INDEX idx_published_articles_fts
ON articles
USING GIN (search_vector)
WHERE status = 'PUBLISHED';
~~~

Truy vấn cần có điều kiện phù hợp để planner dùng index. Khi status thay đổi vào hoặc ra khỏi PUBLISHED, index cần được cập nhật. Lợi ích giảm kích thước và candidate set phải được cân bằng với chi phí ghi và tính phức tạp.

### 9.3. Partitioning

Partitioning có thể giảm phạm vi dữ liệu nếu truy vấn có predicate phù hợp như tenant, thời gian hoặc vùng. Partition pruning có thể bỏ qua các partition không liên quan trước khi full-text search.

Nhưng partitioning không tự động làm full-text query nhanh. Cần xem mỗi partition có full-text index riêng hay cấu trúc global, cách optimizer kết hợp kết quả, chi phí merge/rank và số partition được truy cập.

Nếu truy vấn tìm kiếm toàn bộ lịch sử mà không có predicate partition key, DBMS có thể phải truy cập nhiều partition và hợp nhất kết quả. Đánh giá bằng plan thực tế.

## 10. Đọc execution plan và đo full-text search

### 10.1. PostgreSQL EXPLAIN ANALYZE

Dùng EXPLAIN với BUFFERS để xem access path và số trang:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    article_id,
    title,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('english', 'database performance')
    ) AS relevance
FROM articles
WHERE search_vector @@ websearch_to_tsquery('english', 'database performance')
ORDER BY relevance DESC, article_id
LIMIT 20;
~~~

Một kế hoạch có thể gồm Bitmap Index Scan trên GIN, Bitmap Heap Scan, Sort và Limit. Hãy xem:

- Số dòng do bitmap index scan tìm được.
- Số dòng thực tế sau heap recheck và filter.
- Shared hit/read và temp read/write.
- Số dòng đầu vào Sort so với 20 dòng đầu ra.
- Sort Method và memory/spill.
- Thời gian từng nút và tổng thời gian.

Nếu Sort nhận hàng trăm nghìn dòng nhưng Limit chỉ trả 20, chi phí ranking và top-N có thể chi phối truy vấn. Nếu Bitmap Heap Scan đọc nhiều block hoặc recheck nhiều dòng, cần xem term phổ biến, selectivity và metadata filter.

### 10.2. Tách candidate count khỏi returned count

Trong quá trình thử nghiệm, nên ghi riêng:

- Số tài liệu thỏa full-text predicate trước filter bổ sung nếu đo được.
- Số tài liệu sau filter tenant/status/permission.
- Số tài liệu được tính rank.
- Số tài liệu được sort hoặc xét cho top-k.
- Số kết quả trả về.
- Số trang hoặc block được đọc.
- Số hàng bị recheck hoặc loại bỏ.

Các số liệu này giúp xác định chi phí đến từ inverted index, filter, ranking, sort hay fetch payload. Nếu chỉ ghi thời gian tổng, khó biết nên tối ưu analyzer, index, predicate hay giới hạn kết quả.

### 10.3. Đo độ trễ theo loại truy vấn

Một bộ benchmark tìm kiếm nên gồm:

- Term hiếm, chỉ khớp vài tài liệu.
- Term phổ biến, khớp phần lớn corpus.
- Nhiều term kết hợp AND.
- Nhiều term kết hợp OR.
- Phrase/proximity query.
- Prefix hoặc wildcard nếu sản phẩm hỗ trợ.
- Query có filter tenant/status.
- Query rỗng hoặc chỉ stopword.
- Query có ranking và sort.
- Trang đầu, trang tiếp theo và trang sâu.

Ghi p50, p95, p99, throughput, lỗi, timeout, CPU, buffer reads, temp I/O và số candidate. Chạy cả cache ấm và tình huống cache lạnh nếu có ý nghĩa vận hành.

### 10.4. Kiểm tra concurrency

Tìm kiếm thường có biến động lớn theo term. Một query hiếm có thể hoàn thành nhanh; một query phổ biến có thể quét hàng trăm nghìn ứng viên. Benchmark một client không thể phản ánh áp lực khi nhiều truy vấn rộng chạy đồng thời.

Tăng số client theo từng bước và ghi:

- Query rate thực tế.
- Candidate count trung bình và phân vị cao.
- p95/p99 theo loại query.
- CPU và I/O.
- Buffer cache hit/read.
- Temporary file hoặc spill.
- Thời gian chờ kết nối và lock.
- Độ trễ cập nhật full-text index.

Nếu DBMS bị bão hòa bởi truy vấn rộng, tăng connection pool có thể làm nhiều truy vấn cạnh tranh CPU và cache hơn. Cần giới hạn concurrency hoặc tách workload khi số liệu chứng minh cần thiết.

## 11. Tối ưu top-k và giới hạn kết quả

### 11.1. Chỉ trả các cột cần thiết

Tránh SELECT * trong truy vấn tìm kiếm. Chỉ lấy ID, title, score và metadata cần hiển thị. Cột body lớn có thể được đọc ở bước sau khi đã xác định top-k.

Ví dụ:

~~~sql
WITH top_hits AS (
    SELECT
        article_id,
        ts_rank_cd(
            search_vector,
            websearch_to_tsquery('english', 'database performance')
        ) AS relevance
    FROM articles
    WHERE search_vector @@ websearch_to_tsquery('english', 'database performance')
    ORDER BY relevance DESC, article_id
    LIMIT 20
)
SELECT
    a.article_id,
    a.title,
    a.summary,
    h.relevance
FROM top_hits AS h
JOIN articles AS a
    ON a.article_id = h.article_id
ORDER BY h.relevance DESC, a.article_id;
~~~

Tùy optimizer, CTE có thể được inline hoặc materialize. Hãy kiểm tra plan để xác nhận body không bị đọc cho toàn bộ candidate set trước khi top-k được chọn. Không dựa vào hình thức CTE để khẳng định thứ tự thực thi.

### 11.2. Giới hạn số term và độ dài query

API tìm kiếm nên xác định giới hạn hợp lý cho:

- Số ký tự đầu vào.
- Số term sau phân tích.
- Số toán tử Boolean.
- Độ sâu biểu thức lồng nhau.
- Số trường được tìm.
- Số kết quả tối đa mỗi request.
- Độ sâu phân trang.

Giới hạn cần thông báo rõ và có xử lý input hợp lệ. Nếu người dùng nhập query quá rộng, có thể đề nghị thêm từ khóa hoặc bộ lọc thay vì thực hiện một phép tìm kiếm tốn kém.

### 11.3. Tránh exact count mặc định

Nếu giao diện không thực sự cần tổng số chính xác, hãy dùng has_more hoặc một ước lượng. Một request lấy 21 hàng để hiển thị 20 có thể đủ để biết có trang tiếp theo.

Nếu dùng cache count, cần xác định độ mới dữ liệu và cách invalidation. Một con số gần đúng hoặc cập nhật chậm phải được hiển thị phù hợp với yêu cầu sản phẩm.

### 11.4. Cache truy vấn phổ biến

Các query phổ biến có thể được cache kết quả trong một khoảng thời gian. Cache có thể lưu ID và score hoặc toàn bộ kết quả hiển thị. Cần cân nhắc:

- Query normalization để các chuỗi tương đương dùng chung cache.
- Tenant và quyền truy cập phải nằm trong cache key.
- Thời hạn cache và invalidation khi nội dung thay đổi.
- Thứ tự relevance có ổn định giữa các lần chạy không.
- Kết quả có phụ thuộc người dùng, ngôn ngữ hoặc thời gian không.
- Cache có tạo áp lực bộ nhớ hoặc stale result không.

Không cache kết quả tìm kiếm mà bỏ qua tenant hoặc permission context. Điều đó có thể làm lộ tài liệu giữa người dùng hoặc tổ chức.

## 12. Ví dụ phân tích truy vấn tìm kiếm chậm

### 12.1. Bối cảnh

Một cổng tri thức có 8 triệu bài viết. API tìm kiếm nhận query và trả 20 tài liệu có relevance cao nhất:

~~~sql
SELECT
    article_id,
    title,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('english', :query)
    ) AS relevance
FROM articles
WHERE status = 'PUBLISHED'
  AND tenant_id = :tenant_id
  AND search_vector @@ websearch_to_tsquery('english', :query)
ORDER BY relevance DESC, article_id
LIMIT 20;
~~~

Giả sử query phổ biến database khớp 1,2 triệu tài liệu trên toàn corpus, trong đó tenant hiện tại có 420.000 tài liệu đã xuất bản. API chỉ trả 20 hàng nhưng DBMS có thể phải đánh giá nhiều ứng viên để tính rank và chọn top.

### 12.2. Kế hoạch giả định

Một kế hoạch PostgreSQL minh họa:

~~~text
Limit
  -> Sort
       Sort Key: ts_rank_cd(search_vector, query) DESC, article_id
       Sort Method: top-N heapsort
       -> Bitmap Heap Scan on articles
            Recheck Cond: (search_vector @@ query)
            Filter: (status = 'PUBLISHED' AND tenant_id = ...)
            -> Bitmap Index Scan on idx_articles_search_vector
                 Index Cond: (search_vector @@ query)
~~~

Đây là sơ đồ minh họa, không phải kết quả đo của một hệ thống thật. Nó cho thấy GIN tìm ứng viên, heap scan đọc và lọc metadata, sau đó Sort chọn top 20.

Nếu bitmap index scan tạo ra số lượng rất lớn trước filter tenant, có thể cần cải thiện cách kết hợp metadata với full-text predicate, dùng partial index cho trạng thái phù hợp hoặc partition theo tenant nếu workload và quy mô cho phép. Nhưng cần xem actual rows tại từng node để xác nhận.

### 12.3. Các giả thuyết cần kiểm chứng

- Term database quá phổ biến nên candidate set lớn.
- Filter tenant/status loại bỏ phần lớn ứng viên sau bước full-text.
- Rank được tính cho hàng trăm nghìn tài liệu.
- Sort top-N vẫn phải xét toàn bộ candidate sau filter.
- Nội dung body lớn làm tăng chi phí heap fetch.
- Index GIN lớn tạo buffer reads và cache pressure.
- Query count riêng đang tạo tải tương đương hoặc lớn hơn query lấy kết quả.

### 12.4. Các phương án thử

1. Kiểm tra liệu filter tenant/status có thể kết hợp hiệu quả hơn với full-text access path.
2. Xem xét partial GIN index chỉ chứa tài liệu PUBLISHED nếu phù hợp với tần suất cập nhật trạng thái.
3. Chỉ lấy ID, title và score trong giai đoạn top-k; đọc payload sau.
4. Giới hạn query quá rộng và yêu cầu thêm term khi candidate set vượt ngưỡng.
5. Bỏ exact count nếu sản phẩm chỉ cần has_more.
6. Cache truy vấn phổ biến theo tenant và quyền truy cập.
7. Đánh giá partitioning nếu predicate tenant hoặc thời gian có thể prune rõ rệt.
8. Đo lại với term hiếm, phổ biến và các tổ hợp từ.

Không áp dụng tất cả thay đổi cùng lúc. Thử từng giả thuyết hoặc nhóm thay đổi có thể tách biệt để xác định tác động.

### 12.5. Bảng kết quả minh họa

| Chỉ số | Trước | Sau thử nghiệm | Ý nghĩa |
|---|---:|---:|---|
| Candidate sau filter | 420.000 | 95.000 | Phạm vi cần rank giảm |
| Kết quả trả về | 20 | 20 | Giữ giới hạn API |
| p95 | 1.450 ms | 390 ms | Độ trễ giảm |
| Shared blocks read | 35.000 | 9.200 | Ít trang được nạp hơn |
| Temp blocks written | 0 | 0 | Không có spill trong lần thử |
| Index size | 18 GB | 19 GB | Tăng nhẹ do cấu trúc thử |

Số liệu chỉ mang tính minh họa. Candidate count cần được xác định đúng điểm trong plan; không được nhầm số dòng trả về với số dòng được xếp hạng. Nếu index size tăng nhưng latency giảm, cần đánh giá thêm cache footprint và chi phí ghi.

## 13. Các lỗi thường gặp khi tối ưu full-text search

**Cho rằng full-text index làm mọi query nhanh.**  
Term phổ biến vẫn có thể tạo candidate set lớn. Phải đo số ứng viên và ranking cost.

**Cho rằng LIMIT 20 chỉ xử lý 20 tài liệu.**  
DBMS có thể phải tính rank và xét nhiều ứng viên trước khi xác định top 20.

**Dùng LIKE với wildcard đầu chuỗi trên corpus lớn.**  
B-tree thường không hỗ trợ tìm substring theo cách này. Chọn full-text, trigram hoặc n-gram theo semantics cần thiết.

**Dùng analyzer khác nhau khi index và query.**  
Tokenization, stopword và stemming không nhất quán có thể làm mất kết quả hoặc thay đổi relevance.

**Không kiểm tra tiếng Việt và Unicode.**  
Tách từ theo khoảng trắng có thể không đáp ứng chất lượng tìm kiếm tiếng Việt. Phải thử với corpus và truy vấn thật.

**Luôn yêu cầu exact count.**  
Đếm toàn bộ kết quả có thể tốn kém dù API chỉ hiển thị một trang. Cân nhắc has_more hoặc count gần đúng.

**Dùng OFFSET rất sâu cho kết quả relevance.**  
DBMS có thể phải xử lý và bỏ qua nhiều ứng viên. Dùng cursor khi phù hợp và đo xem ranking có còn là chi phí chính không.

**Thêm metadata filter sau khi đã lấy top-k toàn cục.**  
Có thể bỏ sót kết quả hợp lệ của tenant hoặc làm sai bảo đảm quyền. Filter phải nằm đúng trong ngữ nghĩa tìm kiếm.

**Index mọi trường văn bản.**  
Index lớn làm tăng dung lượng, cache pressure và chi phí ghi. Chọn trường dựa trên nhu cầu tìm kiếm.

**Bỏ qua chi phí cập nhật index.**  
Văn bản thay đổi có thể tạo nhiều công việc tokenization, posting update, population hoặc cleanup.

**So sánh relevance score giữa các DBMS.**  
Ranking khác công thức và cấu hình. Cần đánh giá bằng bộ truy vấn và relevance judgment thống nhất.

## 14. Quy trình kiểm thử và báo cáo

Một bài benchmark full-text search nên ghi lại:

### Mục tiêu và corpus

- Số tài liệu và kích thước văn bản.
- Phân bố độ dài tài liệu.
- Ngôn ngữ, analyzer, parser, stopword và synonym.
- Tỷ lệ tài liệu được xuất bản hoặc có quyền truy cập.
- Tần suất INSERT/UPDATE/DELETE văn bản.

### Bộ truy vấn

- Term phổ biến và term hiếm.
- AND/OR, phrase, prefix và boolean query.
- Truy vấn có metadata filter.
- Query rỗng, stopword và input dài.
- Trang đầu, trang tiếp theo, trang sâu.
- Query có exact count và query chỉ cần has_more.

### Chỉ số hiệu năng

- p50/p95/p99 và throughput.
- Candidate count, filtered count, ranked count và returned count.
- Buffer hit/read, logical/physical I/O.
- CPU, memory, temp I/O và sort.
- Index size và tốc độ cập nhật index.
- Population lag, replication lag và lỗi/timeout.

### Chất lượng tìm kiếm

- Precision@k: tỷ lệ kết quả trong top-k được đánh giá là phù hợp.
- Recall@k hoặc recall trên tập đánh giá: khả năng tìm được tài liệu liên quan.
- NDCG@k nếu cần đánh giá thứ tự relevance có trọng số.
- Kết quả theo ngôn ngữ, tenant, loại query và nhóm tài liệu.

Tối ưu hiệu năng không được làm chất lượng tìm kiếm giảm ngoài giới hạn chấp nhận. Giảm số ứng viên bằng cách bỏ term hoặc filter quá mạnh có thể làm query nhanh nhưng bỏ sót tài liệu liên quan.

### Kết luận thử nghiệm

Báo cáo nên nêu:

- Điều kiện và phiên bản DBMS.
- Cấu hình full-text index.
- Workload và mức đồng thời.
- Execution plan trước/sau.
- Candidate set và chi phí ranking.
- Độ trễ, throughput, I/O, cache và dung lượng.
- Chất lượng top-k.
- Tác động ghi và độ trễ cập nhật index.
- Giới hạn và giả thuyết chưa xác nhận.

## 15. Kết luận

Full-text search dùng inverted index để tìm tài liệu theo term đã phân tích, sau đó có thể phải lọc, tính relevance và chọn top-k. Index giúp tránh quét toàn bộ văn bản trong nhiều tình huống, nhưng không bảo đảm truy vấn rẻ khi term phổ biến hoặc candidate set lớn. LIMIT nhỏ chỉ giới hạn số kết quả trả về; ranking, sort và exact count vẫn có thể phải xử lý rất nhiều tài liệu.

Tối ưu cần xem đồng thời analyzer, ngôn ngữ, stopword, cấu trúc index, filter metadata, ranking, phân trang và concurrency. PostgreSQL GIN, MySQL FULLTEXT, SQL Server Full-Text Catalog và Oracle Text có semantics, parser và cơ chế cập nhật khác nhau. Hãy đọc execution plan đúng engine, đo candidate count và số hàng được xếp hạng, kiểm tra buffer/I/O và đánh giá chi phí ghi cùng dung lượng.

Một giải pháp tốt giữ được chất lượng tìm kiếm, bảo đảm quyền truy cập và đáp ứng mục tiêu độ trễ dưới tải thực tế. Chỉ số relevance cần được đánh giá theo bộ truy vấn đại diện; kết quả benchmark phải được lặp lại với cùng corpus, cấu hình và mức đồng thời.

## Câu hỏi tự kiểm tra

1. Inverted index tổ chức dữ liệu khác B-tree index như thế nào?
2. Vì sao full-text search không tương đương tìm chuỗi con bằng LIKE?
3. Tokenization, stopword và stemming ảnh hưởng kết quả tìm kiếm ra sao?
4. Vì sao GIN index trong PostgreSQL giúp tìm term nhưng không tự sắp kết quả theo ts_rank_cd?
5. Relevance score có phải xác suất tài liệu đúng hay không? Giải thích.
6. Một truy vấn trả 20 hàng nhưng khớp 400.000 tài liệu. DBMS có thể phải thực hiện những công việc nào?
7. Top-N sort giảm chi phí nào và không loại bỏ chi phí nào?
8. Vì sao exact count có thể tốn gần bằng truy vấn lấy top-k?
9. Keyset pagination theo relevance có giới hạn gì khi score được tính động?
10. Khi nào partial/filtered index theo trạng thái có thể giảm candidate set và khi nào nó làm tăng chi phí ghi?
11. Vì sao cần kiểm tra analyzer tiếng Việt thay vì chỉ dựa vào tách từ theo khoảng trắng?
12. Hãy lập kế hoạch đo một API tìm kiếm gồm term hiếm, term phổ biến, ranking, has_more và tải đồng thời.

Khi đánh giá một truy vấn full-text, hãy hỏi: analyzer tạo ra những term nào, inverted index trả về bao nhiêu ứng viên, filter giữ lại bao nhiêu tài liệu, bao nhiêu tài liệu phải tính rank và DBMS cần làm gì để chọn top-k. Những con số đó cho biết chi phí thực sự nằm ở đâu.

