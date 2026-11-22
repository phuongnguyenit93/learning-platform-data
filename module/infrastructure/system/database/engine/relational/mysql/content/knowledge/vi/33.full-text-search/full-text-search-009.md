# Tính điểm, sắp xếp độ liên quan và phân trang kết quả

Bài học thuộc chương **Tìm kiếm văn bản** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Full-text search không chỉ trả lời một hàng có chứa từ khóa hay không; hàm MATCH() còn tính điểm liên quan (relevance score) để ước lượng mức độ phù hợp của nội dung với truy vấn. Muốn xây dựng trang tìm kiếm đúng và ổn định, cần hiểu cách score được tính, chủ động sắp xếp theo score, xử lý các hàng đồng điểm, chọn chiến lược phân trang và nhận diện tác động khi tập tài liệu thay đổi.

Sau bài này, bạn có thể lấy relevance score bằng MATCH() AGAINST(), phân biệt natural-language và Boolean ranking, giải thích các yếu tố ảnh hưởng đến score, viết ORDER BY có tie-breaker duy nhất, hiểu điều kiện tự sắp xếp theo relevance và tối ưu Top-N của InnoDB, so sánh OFFSET với keyset pagination, nhận diện vì sao cursor dựa trên score có thể thay đổi giữa các request, và lưu snapshot kết quả khi cần phân trang nhất quán.

## 1. Relevance score là gì?

Với full-text search, một hàng có thể khớp truy vấn nhưng mức độ phù hợp không giống nhau. Ví dụ tìm mysql index:

- Tài liệu A nhắc cả hai từ nhiều lần và tập trung vào cách thiết kế index.
- Tài liệu B chỉ nhắc mysql một lần trong phần giới thiệu.
- Tài liệu C nhắc index nhiều lần nhưng không có mysql.
- Tài liệu D không chứa từ nào trong truy vấn.

MATCH() AGAINST() trả về một giá trị số biểu diễn mức độ liên quan của hàng với chuỗi tìm kiếm. Giá trị này thường được đặt tên là score, relevance hoặc rank.

Cú pháp:

~~~sql
MATCH (title, body)
AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
~~~

MATCH() xác định tập cột văn bản cần tìm. AGAINST() nhận chuỗi truy vấn và search modifier. Nếu không ghi modifier, MySQL dùng natural-language mode.

Ví dụ lấy score:

~~~sql
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles;
~~~

Truy vấn trên tính score cho từng hàng, kể cả hàng không có từ khớp. Score bằng 0 có nghĩa không có độ tương đồng theo cách đánh giá của full-text search.

### Score không phải xác suất

Không diễn giải score như xác suất hoặc phần trăm:

- Score 0.8 không có nghĩa nội dung đúng 80%.
- Score 2.4 không có nghĩa phù hợp 2,4 lần theo một thang đo phổ quát.
- Score của hai truy vấn khác nhau không nhất thiết so sánh trực tiếp được.
- Score có thể thay đổi khi tập tài liệu trong collection thay đổi.

Score là giá trị phục vụ xếp hạng trong phạm vi thuật toán, parser, index và collection đang dùng.

### Collection và document

Trong ngữ cảnh full-text:

- **Document** là phần văn bản được index của một hàng.
- **Collection** là tập các cột trong FULLTEXT index trên các hàng được tìm kiếm.

Ví dụ FULLTEXT index trên (title, body) tạo collection từ nội dung hai cột đó. Độ dài document, số từ duy nhất và tần suất từ trong toàn collection có thể ảnh hưởng đến relevance.

## 2. Lấy score và lọc kết quả bằng MATCH() AGAINST()

Ví dụ bảng bài viết:

~~~sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(250) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at DATETIME(6) NOT NULL,
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_status_published (status, published_at)
) ENGINE=InnoDB;
~~~

Tìm các bài có nội dung liên quan đến mysql index:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE);
~~~

Ở đây MATCH() xuất hiện hai lần:

1. Trong SELECT để trả score cho client.
2. Trong WHERE để lọc các hàng có kết quả tìm kiếm.

Khi hai biểu thức MATCH() giống hệt nhau, MySQL optimizer nhận diện và không gọi lại full-text search engine thêm một lần chỉ vì biểu thức được viết hai chỗ.

### MATCH() phải khớp FULLTEXT index

Với InnoDB, danh sách cột trong MATCH() phải khớp chính xác danh sách cột trong một FULLTEXT index.

Nếu index được tạo:

~~~sql
FULLTEXT KEY ft_articles_title_body (title, body)
~~~

thì biểu thức phù hợp là:

~~~sql
MATCH (title, body)
~~~

Không mặc định rằng index (title, body) cũng phục vụ được MATCH(title) hoặc MATCH(body). Nếu cần tìm riêng title, tạo FULLTEXT index riêng cho title.

Ngoại lệ Boolean mode trên MyISAM có thể tìm cột không có FULLTEXT index, nhưng thường chậm; không áp dụng ngoại lệ đó cho InnoDB.

### AGAINST() cần chuỗi hằng trong lúc đánh giá query

AGAINST() nhận giá trị chuỗi không thay đổi theo từng hàng trong quá trình đánh giá truy vấn. Không thể dùng một cột khác của bảng làm chuỗi tìm kiếm riêng cho từng hàng.

Trong ứng dụng, nên truyền search text bằng parameter binding của prepared statement:

~~~sql
SELECT
    article_id,
    MATCH (title, body) AGAINST (? IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body) AGAINST (? IN NATURAL LANGUAGE MODE);
~~~

Hai placeholder nhận cùng search text. Parameter binding giúp tránh ghép chuỗi SQL trực tiếp từ dữ liệu người dùng.

## 3. Những yếu tố ảnh hưởng đến relevance score

Trong natural-language mode, score là giá trị floating-point không âm. Score bằng 0 biểu thị không có similarity. MySQL tính relevance dựa trên các yếu tố như:

- Số từ trong document.
- Số từ duy nhất trong document.
- Tổng số từ trong collection.
- Số hàng chứa một từ cụ thể.

Ý nghĩa trực quan:

- Một từ xuất hiện nhiều lần trong document có thể làm tăng mức liên quan.
- Một từ xuất hiện trong ít document thường có sức phân biệt cao hơn từ xuất hiện ở hầu hết document.
- Độ dài document và phân bố từ trong collection cũng ảnh hưởng kết quả.
- Các từ bị loại bởi stopword hoặc giới hạn độ dài token không đóng góp như một từ được index bình thường.

Không nên tự áp dụng một công thức duy nhất cho mọi storage engine và search mode. Natural-language ranking và Boolean ranking có khác biệt về thuật toán, đặc biệt giữa InnoDB và MyISAM.

### InnoDB Boolean ranking và TF-IDF

Với Boolean full-text search trên InnoDB, MySQL mô tả thuật toán xếp hạng dựa trên BM25 và TF-IDF. Một cách diễn giải cho truy vấn một từ:

- TF (term frequency): số lần từ xuất hiện trong document.
- IDF (inverse document frequency): mức độ hiếm của từ trong collection.

Tài liệu mô tả:

\[
IDF = \log_{10}\left(\frac{N}{n}\right)
\]

Trong đó:

- N là tổng số record trong collection.
- n là số record chứa từ đang xét.

Với một document có từ đó nhiều lần, phần đóng góp được mô tả là:

\[
TF \times IDF
\]

và công thức ranking ví dụ cho một từ trong InnoDB Boolean mode là:

\[
rank = TF \times IDF^2
\]

Đây là mô tả thuật toán InnoDB Boolean ranking trong tài liệu, không phải công thức chung cho mọi full-text search. MyISAM có cách tính relevance khác; natural-language mode cũng cần được hiểu theo mô tả riêng của tài liệu.

### Vì sao score có thể thay đổi?

Giả sử hôm nay collection có 10.000 bài và từ replication xuất hiện trong 100 bài. Sau khi nhập thêm nhiều bài mới, số document và tần suất xuất hiện của từ có thể đổi. IDF và score tương ứng có thể thay đổi.

Score cũng có thể thay đổi khi:

- Nội dung của document được cập nhật.
- Document được thêm hoặc xóa.
- FULLTEXT index được xây dựng lại sau khi thay đổi parser hoặc stopword.
- Query text hoặc search mode thay đổi.
- Storage engine hoặc cách cấu hình full-text search thay đổi.

Vì vậy, không lưu một cursor score từ nhiều ngày trước rồi mặc định nó luôn đại diện cho cùng vị trí trong một collection đã thay đổi.

## 4. Natural-language mode và Boolean mode xếp hạng khác nhau

Hai mode thường được dùng cho hai kiểu trải nghiệm khác nhau.

| Tiêu chí | Natural-language mode | Boolean mode |
|---|---|---|
| Cách diễn đạt query | Cụm từ tự nhiên | Có toán tử điều khiển |
| Mục tiêu | Tìm và xếp hạng nội dung liên quan | Kiểm soát từ bắt buộc, loại trừ, cụm từ |
| Relevance score | Có | Có thể lấy bằng MATCH() AGAINST() |
| Tự sắp xếp giảm dần theo score | Có trong một số điều kiện | Không |
| Toán tử +, -, >, <, ~ | Không dùng như Boolean operators | Có |
| 50% threshold của MyISAM | Có thể áp dụng theo ranking MyISAM | Không áp dụng |
| InnoDB | Hỗ trợ | Hỗ trợ |

### Natural-language mode

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Đây là dạng phổ biến cho trang tìm kiếm. MySQL tìm các hàng liên quan rồi sắp xếp score giảm dần. article_id là tie-breaker để thứ tự xác định khi nhiều hàng có cùng score.

### Boolean mode

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('+mysql +replication -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('+mysql +replication -oracle' IN BOOLEAN MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Trong ví dụ:

- +mysql: hàng phải có từ mysql.
- +replication: hàng phải có từ replication.
- -oracle: loại hàng có oracle.
- ORDER BY score DESC: xếp hàng phù hợp hơn trước.
- article_id ASC: xử lý trường hợp đồng điểm.

Boolean mode không tự sắp xếp kết quả theo relevance. Nếu cần xếp hạng, hãy SELECT score và viết ORDER BY rõ ràng.

Các toán tử > và < có thể tăng hoặc giảm phần đóng góp của một từ vào relevance trong Boolean mode. ~ làm phần đóng góp âm, trong khi - loại hàng chứa từ đó khỏi tập kết quả phù hợp. Không nhầm hai hành vi này.

## 5. Tự sắp xếp theo relevance có điều kiện

Trong natural-language search, khi MATCH() nằm trong WHERE, MySQL có thể tự trả hàng theo score giảm dần nếu đồng thời thỏa các điều kiện:

1. Không có ORDER BY tường minh.
2. Search sử dụng full-text index scan thay vì table scan.
3. Nếu có JOIN, bảng được full-text index scan phải là bảng không hằng số đứng đầu trong thứ tự join.

Ví dụ:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE);
~~~

Trong điều kiện thích hợp, hàng có relevance cao hơn được trả trước.

Nhưng không nên dựa vào hành vi ngầm này cho API hoặc giao diện có phân trang. Khi cần thứ tự được định nghĩa rõ, hãy viết:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql replication' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC;
~~~

Việc thêm ORDER BY có nghĩa ứng dụng chịu trách nhiệm chỉ rõ thứ tự. Nó cũng giúp người đọc SQL hiểu rõ hợp đồng kết quả.

### Tie-breaker là bắt buộc cho phân trang ổn định

Score có thể trùng nhau. Ví dụ hai bài cùng nhắc một từ với tần suất tương đương. Nếu chỉ viết:

~~~sql
ORDER BY score DESC
~~~

thứ tự giữa các hàng đồng điểm không được xác định. Khi execution plan, dữ liệu hoặc index thay đổi, các hàng đồng điểm có thể đổi vị trí.

Thêm một khóa duy nhất:

~~~sql
ORDER BY score DESC, article_id ASC
~~~

Khóa phụ phải duy nhất trong tập kết quả. Primary key thường là lựa chọn tốt.

Không dùng ROUND(score, 2) làm khóa xếp hạng nếu không có chủ đích gom điểm. Làm tròn có thể biến các score khác nhau thành bằng nhau và thay đổi thứ tự nghiệp vụ. Có thể ROUND để hiển thị, nhưng nên sắp xếp theo score gốc.

## 6. Tối ưu Top-N full-text search

Một truy vấn Top-N thường có dạng:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

MySQL có tối ưu riêng cho một số truy vấn FULLTEXT trên một bảng InnoDB. Tài liệu nêu các dạng đặc biệt hiệu quả:

- Chỉ trả về document ID, hoặc document ID cùng search rank.
- Sắp xếp hàng khớp theo score giảm dần và dùng LIMIT lấy Top-N.
- Không có WHERE clause.
- Chỉ có một ORDER BY theo chiều giảm dần.

Đây là điều kiện hẹp của một tối ưu Top-N cụ thể. Truy vấn ứng dụng có thêm bộ lọc status, JOIN hoặc tie-breaker có thể không thuộc đúng dạng tối ưu này. Không suy ra rằng mọi truy vấn MATCH() AGAINST() ORDER BY score DESC LIMIT N đều dùng cùng một kế hoạch.

### Lấy ít cột trước

Nếu trang đầu chỉ cần ID và score, tránh kéo toàn bộ body dài qua bước xếp hạng:

~~~sql
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Sau đó, nếu cần, lấy chi tiết theo danh sách ID đã chọn. Việc tách bước có thể giảm lượng dữ liệu phải materialize hoặc truyền đi, nhưng cần đo kế hoạch thực tế và cân nhắc thêm round trip.

### Bộ lọc thông thường có thể làm thay đổi kế hoạch

Ví dụ:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH (title, body)
      AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Điều kiện status có thể làm thay đổi kế hoạch. FULLTEXT index và B-tree index trên status phục vụ các mục đích khác nhau; optimizer phải cân nhắc cách kết hợp chúng.

Không giả định rằng index status luôn được dùng trước full-text index hoặc ngược lại. Kiểm tra EXPLAIN, số hàng thực tế và độ chọn lọc của từng điều kiện.

## 7. OFFSET pagination cho kết quả tìm kiếm

Cách phân trang quen thuộc:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20 OFFSET 40;
~~~

Truy vấn bỏ qua 40 hàng đầu rồi trả 20 hàng tiếp theo.

Ưu điểm:

- SQL đơn giản.
- Phù hợp với giao diện có số trang.
- Dễ nhảy đến trang bất kỳ.
- Dễ đồng bộ với API truyền page/pageSize.

Nhược điểm:

- OFFSET càng lớn, server càng phải đi qua nhiều hàng trước vị trí cần trả.
- Full-text search vẫn phải tìm tập hàng khớp và xếp hạng.
- Thêm hoặc xóa document giữa các request có thể làm vị trí hàng dịch chuyển.
- Người dùng có thể thấy một bài bị lặp hoặc bị bỏ qua khi chuyển trang.

Ví dụ:

~~~sql
LIMIT 20 OFFSET 0;
LIMIT 20 OFFSET 20;
LIMIT 20 OFFSET 40;
~~~

Trang càng sâu, chi phí bỏ qua càng lớn. Với kết quả tìm kiếm rất lớn, cần cân nhắc keyset hoặc snapshot.

### LIMIT không biến score thành index có thể seek

Score là biểu thức được tính từ MATCH() AGAINST(), không phải một cột B-tree có sẵn. MySQL không thể dùng một B-tree index thông thường để nhảy trực tiếp đến score 0.75 như khi phân trang trên một cột đã index.

Vì vậy, keyset theo score có thể tránh đếm bỏ qua OFFSET, nhưng không có nghĩa MySQL tránh được toàn bộ công việc full-text matching và ranking. Cần benchmark trên tập dữ liệu thật.

## 8. Keyset pagination theo score và khóa phụ

Keyset pagination dùng khóa của hàng cuối trang hiện tại làm cursor.

Giả sử thứ tự:

~~~sql
ORDER BY score DESC, article_id ASC
~~~

Hàng cuối trang trước có:

- score = 0.7421
- article_id = 500

Trang kế tiếp cần lấy:

- Hàng có score nhỏ hơn 0.7421.
- Hoặc score bằng 0.7421 nhưng article_id lớn hơn 500.

Điều kiện:

~~~sql
score < 0.7421
OR (score = 0.7421 AND article_id > 500)
~~~

Ví dụ dùng derived table để có thể lọc theo alias score:

~~~sql
SELECT
    article_id,
    title,
    score
FROM (
    SELECT
        article_id,
        title,
        MATCH (title, body)
            AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
) AS ranked
WHERE score < 0.7421
   OR (score = 0.7421 AND article_id > 500)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Trong ứng dụng, truyền last_score và last_article_id bằng parameter binding:

~~~sql
WHERE score < ?
   OR (score = ? AND article_id > ?)
ORDER BY score DESC, article_id ASC
LIMIT ?;
~~~

Hai tham số score phải dùng cùng giá trị score gốc của hàng cuối trang. Không làm tròn score trước khi lưu cursor.

### Điều kiện để cursor score hoạt động đúng

- Query text giống hệt trang trước.
- Search mode giống hệt.
- MATCH column list và FULLTEXT index không thay đổi.
- Bộ lọc và quyền truy cập dữ liệu giống hệt.
- Score được lấy từ đúng lần tính trước, không bị làm tròn.
- Tập document và nội dung được index không thay đổi theo cách ảnh hưởng ranking trong suốt phiên phân trang.

Nếu corpus thay đổi, score có thể thay đổi. Một document mới làm IDF thay đổi có thể khiến các hàng đã xem dịch chuyển. Một bài được cập nhật có thể tăng hoặc giảm score. Keyset không đóng băng thứ tự của toàn bộ tập kết quả.

### Keyset theo score không tương đương keyset theo B-tree

Với một bảng giao dịch, cursor (created_at, id) có thể tận dụng composite B-tree index để seek đến vị trí tiếp theo. Với full-text score, score là giá trị tính toán từ search engine; nó không phải key part trong B-tree index.

Keyset theo score có lợi ích về logic phân trang và tránh OFFSET lớn, nhưng không đảm bảo giảm số document phải đánh giá hoặc sort. Hãy xem execution plan và đo thực tế.

## 9. Snapshot kết quả tìm kiếm khi cần thứ tự ổn định

Nếu sản phẩm yêu cầu:

- Người dùng mở trang 1 hôm nay.
- Sau vài phút quay lại trang 2.
- Dữ liệu nguồn có thể thay đổi trong thời gian đó.
- Mọi trang phải thuộc cùng một thứ tự tìm kiếm đã chốt.

thì không nên tính lại score từ corpus đang thay đổi cho từng request. Có thể lưu snapshot kết quả.

### Bảng phiên tìm kiếm

~~~sql
CREATE TABLE search_session (
    search_id BINARY(16) NOT NULL PRIMARY KEY,
    query_text VARCHAR(500) NOT NULL,
    search_mode VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;
~~~

### Bảng kết quả đã xếp hạng

~~~sql
CREATE TABLE search_result (
    search_id BINARY(16) NOT NULL,
    position_no BIGINT UNSIGNED NOT NULL,
    article_id BIGINT UNSIGNED NOT NULL,
    relevance_score DOUBLE NOT NULL,
    PRIMARY KEY (search_id, position_no),
    UNIQUE KEY uq_search_article (search_id, article_id),
    KEY idx_search_article (article_id),
    CONSTRAINT fk_search_result_session
        FOREIGN KEY (search_id)
        REFERENCES search_session(search_id)
) ENGINE=InnoDB;
~~~

Khi người dùng bắt đầu tìm kiếm:

1. Tạo search_id duy nhất.
2. Lưu query text, mode, filter và thời điểm tạo.
3. Tính relevance cho tập kết quả.
4. Gán position_no bằng ROW_NUMBER() theo score DESC, article_id ASC.
5. Lưu các ID và score vào search_result.
6. Phân trang theo position_no.

Ví dụ tạo snapshot Top-500:

~~~sql
INSERT INTO search_result (
    search_id,
    position_no,
    article_id,
    relevance_score
)
SELECT
    UUID_TO_BIN('11111111-1111-1111-1111-111111111111'),
    ROW_NUMBER() OVER (
        ORDER BY score DESC, article_id ASC
    ) AS position_no,
    article_id,
    score
FROM (
    SELECT
        article_id,
        MATCH (title, body)
            AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
    ORDER BY score DESC, article_id ASC
    LIMIT 500
) AS ranked;
~~~

Trong production, search_id được tạo ở tầng ứng dụng và truyền vào prepared statement. Ví dụ UUID trên chỉ để minh họa.

### Lấy từng trang từ snapshot

Trang đầu:

~~~sql
SELECT
    sr.position_no,
    sr.article_id,
    sr.relevance_score,
    a.title
FROM search_result AS sr
JOIN articles AS a
    ON a.article_id = sr.article_id
WHERE sr.search_id = UUID_TO_BIN('11111111-1111-1111-1111-111111111111')
ORDER BY sr.position_no
LIMIT 20;
~~~

Trang tiếp theo:

~~~sql
SELECT
    sr.position_no,
    sr.article_id,
    sr.relevance_score,
    a.title
FROM search_result AS sr
JOIN articles AS a
    ON a.article_id = sr.article_id
WHERE sr.search_id = UUID_TO_BIN('11111111-1111-1111-1111-111111111111')
  AND sr.position_no > 20
ORDER BY sr.position_no
LIMIT 20;
~~~

Lúc này thứ tự và score được lưu tại thời điểm tạo snapshot. Dữ liệu bài viết hiển thị vẫn có thể thay đổi hoặc bị xóa; nếu cần nội dung cũng nhất quán, phải lưu thêm snapshot các trường hiển thị hoặc áp dụng versioning cho document.

### Chi phí của snapshot

Snapshot tăng:

- Dung lượng lưu trữ.
- Chi phí tạo kết quả ban đầu.
- Chi phí dọn dữ liệu hết hạn.
- Số lượng hàng phải ghi khi tạo phiên.

Không cần lưu toàn bộ hàng nghìn kết quả nếu giao diện chỉ cho phép xem 10 trang đầu. Có thể giới hạn Top-K theo sản phẩm và đặt TTL để dọn snapshot cũ.

## 10. Phân trang theo khóa tài liệu thay vì score

Một số hệ thống có thể chọn thứ tự đơn giản hơn:

~~~sql
ORDER BY published_at DESC, article_id DESC
~~~

Lúc này cursor là (published_at, article_id) và có thể được hỗ trợ bằng composite B-tree index.

Ví dụ:

~~~sql
CREATE INDEX idx_articles_published
ON articles (status, published_at DESC, article_id DESC);
~~~

Truy vấn:

~~~sql
SELECT
    article_id,
    title
FROM articles
WHERE status = 'PUBLISHED'
  AND (
      published_at < '2026-11-18 10:00:00'
      OR (
          published_at = '2026-11-18 10:00:00'
          AND article_id < 500
      )
  )
ORDER BY published_at DESC, article_id DESC
LIMIT 20;
~~~

Đây không còn là relevance ranking thuần túy. Nó là một lựa chọn sản phẩm: ưu tiên mới nhất trong tập bài có chứa từ khóa.

Có thể kết hợp relevance và freshness bằng một score tự định nghĩa, nhưng cần xác định công thức, chuẩn hóa thang đo và kiểm thử chất lượng kết quả. Không cộng trực tiếp các score có thang đo khác nhau mà không hiểu phân bố của chúng.

## 11. Kết hợp score từ title và body

Nếu muốn tăng trọng số cho title, có thể tạo hai FULLTEXT index riêng:

~~~sql
CREATE TABLE articles_weighted (
    article_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(250) NOT NULL,
    body TEXT NOT NULL,
    FULLTEXT KEY ft_title (title),
    FULLTEXT KEY ft_body (body)
) ENGINE=InnoDB;
~~~

Sau đó tạo custom score:

~~~sql
SELECT
    article_id,
    title,
    3.0 * MATCH (title)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
    +
    1.0 * MATCH (body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles_weighted
WHERE MATCH (title)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
   OR MATCH (body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Đây là ví dụ heuristic. Hệ số 3.0 và 1.0 không phải giá trị mặc định hay khuyến nghị phổ quát. Cần đánh giá relevance bằng tập query và kết quả mong đợi của sản phẩm.

Mỗi MATCH() phải có FULLTEXT index tương ứng với đúng danh sách cột. Nếu muốn dùng một FULLTEXT index ghép (title, body), hãy dùng MATCH(title, body) và chấp nhận cách MySQL tính relevance trên collection ghép đó.

Không nên cộng score của hai collection khác nhau mà chưa kiểm tra thang đo và phân bố score. Kết quả có thể thiên lệch mạnh về một trường.

## 12. Query expansion ảnh hưởng đến tập kết quả và thứ tự

MySQL hỗ trợ query expansion:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST (
            'database'
            WITH QUERY EXPANSION
        ) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST (
        'database'
        WITH QUERY EXPANSION
    )
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Query expansion thực hiện tìm kiếm hai lần:

1. Tìm các document phù hợp với query gốc.
2. Chọn một số document có relevance cao từ lần đầu.
3. Ghép các từ trong những document đó vào query.
4. Thực hiện lần tìm kiếm thứ hai với query mở rộng.

Điều này có thể tìm thêm tài liệu liên quan về ngữ nghĩa, dù chúng không chứa từ khóa gốc. Nhưng nó cũng làm thay đổi tập kết quả và thứ tự score.

Không bật query expansion mặc định cho mọi truy vấn. Nó có thể làm kết quả ít trực tiếp hơn, đặc biệt với query ngắn hoặc từ khóa mơ hồ. Hãy kiểm thử với dữ liệu và nhu cầu tìm kiếm thực tế.

## 13. Parser, stopword và token ảnh hưởng đến score

Score chỉ được tính từ những token mà full-text parser đưa vào index.

Các yếu tố cần kiểm tra:

- Parser mặc định tách từ theo quy tắc của ngôn ngữ.
- Stopword có thể bị bỏ khỏi index và query.
- Từ quá ngắn hoặc quá dài có thể bị bỏ theo cấu hình token size.
- Charset/collation ảnh hưởng cách so sánh chữ hoa/thường và ký tự.
- Với ngôn ngữ không có ranh giới từ bằng khoảng trắng như tiếng Trung hoặc tiếng Nhật, parser mặc định không đủ; MySQL cung cấp ngram parser và MeCab plugin cho các trường hợp phù hợp.

Với InnoDB, innodb_ft_min_token_size và innodb_ft_max_token_size điều khiển giới hạn độ dài token của built-in parser. Với MyISAM, các biến tương ứng là ft_min_word_len và ft_max_word_len. ngram parser dùng ngram_token_size.

Thay đổi cấu hình token size thường cần restart server và rebuild FULLTEXT index để có hiệu lực. Đừng thay cấu hình production chỉ để một từ ngắn xuất hiện trong kết quả mà chưa đánh giá chi phí index và ảnh hưởng toàn bộ collection.

### Các cột trong một FULLTEXT index phải thống nhất charset/collation

Các cột được ghép trong cùng một FULLTEXT index phải dùng cùng character set và collation. Nếu cần tìm kiếm không phân biệt hoa thường hoặc phân biệt dấu, hãy lựa chọn collation có chủ đích và kiểm thử query.

Không dùng % như wildcard của LIKE trong full-text search. Full-text Boolean mode có toán tử truncation * riêng, với semantics khác.

## 14. Dữ liệu mới và thời điểm cập nhật FULLTEXT index

Với InnoDB, DML liên quan đến cột có FULLTEXT index được xử lý trong quá trình COMMIT. Ví dụ INSERT được token hóa và thêm vào các cấu trúc full-text khi transaction commit.

Do đó, full-text search chỉ trả về dữ liệu đã commit. Một hàng vừa INSERT nhưng transaction chưa commit không được xem như một kết quả full-text đã được index.

Điều này quan trọng với ứng dụng:

- Không kỳ vọng tìm thấy nội dung chưa commit trong một transaction.
- Sau khi COMMIT, nội dung được đưa vào full-text index theo cơ chế InnoDB.
- Khi kiểm thử, hãy commit dữ liệu trước khi chạy query search từ session khác.
- Với workload ghi lớn, đo tác động full-text index lên thời gian commit và dung lượng index.

## 15. EXPLAIN và các lưu ý hiệu năng

Dùng EXPLAIN để kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 20;
~~~

Các trường nên quan sát:

| Trường | Ý nghĩa cần kiểm tra |
|---|---|
| possible_keys | FULLTEXT index có thể được dùng |
| key | Index optimizer chọn |
| type/access type | Cách truy cập bảng |
| rows | Ước lượng số hàng |
| filtered | Tỷ lệ hàng qua điều kiện còn lại |
| Extra | Các bước bổ sung và thông tin tối ưu |

EXPLAIN cho truy vấn full-text có thể chậm hơn truy vấn thông thường vì MySQL đánh giá full-text expression ngay trong giai đoạn tối ưu để xây dựng kế hoạch. Trong một số trường hợp, Extra có thể hiển thị Select tables optimized away vì matching đã diễn ra trong optimizer và không cần truy cập bảng ở giai đoạn thực thi tiếp theo.

Đừng so sánh thời gian chạy EXPLAIN của full-text query với một SELECT thông thường rồi kết luận query sẽ có cùng độ trễ khi thực thi.

### Đo với dữ liệu thực

Khi đánh giá truy vấn tìm kiếm, ghi lại:

- Query text và search mode.
- Số hàng khớp.
- Thời gian lấy Top-10, Top-20 và trang sâu.
- Số cột được trả về.
- Tỷ lệ filter status/category.
- Kích thước collection.
- Tần suất INSERT/UPDATE/DELETE.
- Tỷ lệ query có kết quả rỗng hoặc quá phổ biến.

Nếu cần đo thời gian iterator thực tế, có thể dùng EXPLAIN ANALYZE trên truy vấn SELECT phù hợp. Lưu ý EXPLAIN ANALYZE thực thi câu truy vấn; chỉ dùng với truy vấn và môi trường có thể chạy an toàn.

## 16. Các giới hạn full-text search liên quan đến xếp hạng

Một số giới hạn ảnh hưởng trực tiếp đến cách viết query và phân trang:

- FULLTEXT chỉ được hỗ trợ bởi InnoDB và MyISAM.
- FULLTEXT search không được hỗ trợ trên partitioned tables.
- FULLTEXT index chỉ tạo trên CHAR, VARCHAR hoặc TEXT.
- Danh sách MATCH() phải khớp chính xác danh sách cột trong một FULLTEXT index đối với InnoDB.
- AGAINST() cần chuỗi không đổi trong quá trình đánh giá query.
- Các cột trong một FULLTEXT index phải cùng character set và collation.
- % không phải wildcard của full-text search.
- Boolean mode không tự sắp xếp theo score.
- Score natural-language là floating-point; không nên dùng score đã làm tròn làm cursor.
- Score phụ thuộc collection; thay đổi dữ liệu có thể làm thay đổi ranking.

Những giới hạn này cần được tính vào thiết kế schema và API tìm kiếm, không chỉ xử lý ở giao diện.

## 17. Bài thực hành: xếp hạng và phân trang bài viết

Lab tạo dữ liệu nhỏ có nội dung trùng từ khóa để quan sát score, tie-breaker và phân trang. Không đặt trước giá trị score vì score phụ thuộc toàn bộ collection và cấu hình full-text.

### Bước 1: tạo database và bảng

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_fulltext_ranking_lab;
USE mysql_fulltext_ranking_lab;

CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    title VARCHAR(250) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    published_at DATETIME(6) NOT NULL,
    FULLTEXT KEY ft_articles_title_body (title, body),
    KEY idx_articles_status_published (status, published_at)
) ENGINE=InnoDB;
~~~

### Bước 2: nạp dữ liệu

~~~sql
INSERT INTO articles (
    article_id,
    title,
    body,
    status,
    published_at
)
VALUES
    (1, 'MySQL index basics',
     'Learn how MySQL indexes help query execution and database performance.',
     'PUBLISHED', '2026-11-18 08:00:00'),
    (2, 'Full-text search in MySQL',
     'MySQL full-text search uses MATCH AGAINST and a FULLTEXT index.',
     'PUBLISHED', '2026-11-18 09:00:00'),
    (3, 'MySQL query optimization',
     'Query optimization uses indexes, statistics, and execution plans.',
     'PUBLISHED', '2026-11-18 10:00:00'),
    (4, 'Database indexing guide',
     'An index can reduce the amount of data read by a query.',
     'DRAFT', '2026-11-18 11:00:00'),
    (5, 'MySQL full-text ranking',
     'Relevance ranking sorts full-text search results by score.',
     'PUBLISHED', '2026-11-18 12:00:00'),
    (6, 'Search relevance and pagination',
     'Stable pagination needs deterministic ordering and a unique tie breaker.',
     'PUBLISHED', '2026-11-18 13:00:00'),
    (7, 'MySQL storage engines',
     'InnoDB supports FULLTEXT indexes and transactional data changes.',
     'PUBLISHED', '2026-11-18 14:00:00'),
    (8, 'Index maintenance',
     'Index maintenance and query plans help diagnose slow database workloads.',
     'PUBLISHED', '2026-11-18 15:00:00'),
    (9, 'MySQL search tutorial',
     'This article explains MySQL full-text search, relevance, and search ranking.',
     'PUBLISHED', '2026-11-18 16:00:00'),
    (10, 'Pagination patterns',
     'OFFSET and keyset pagination are useful for browsing search results.',
     'PUBLISHED', '2026-11-18 17:00:00');
~~~

### Bước 3: xem score không lọc kết quả

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
ORDER BY article_id;
~~~

Quan sát:

- Hàng không có từ phù hợp có thể có score 0.
- Hàng chứa các từ truy vấn có score dương.
- Score có thể khác nhau giữa các hàng.
- Không giả định score nằm trong khoảng 0 đến 1.

### Bước 4: tìm kiếm và sắp xếp ổn định

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 5;
~~~

Kiểm tra score giảm dần. Nếu hai hàng đồng điểm, article_id ASC quyết định thứ tự.

### Bước 5: so sánh Boolean mode

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('+mysql +index -oracle' IN BOOLEAN MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('+mysql +index -oracle' IN BOOLEAN MODE)
ORDER BY score DESC, article_id ASC;
~~~

So sánh tập hàng với natural-language mode. Boolean mode không tự sắp xếp relevance; ORDER BY trong ví dụ là chủ động.

### Bước 6: lọc theo trạng thái

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE status = 'PUBLISHED'
  AND MATCH (title, body)
      AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 5;
~~~

Kiểm tra bài DRAFT không xuất hiện. Quan sát EXPLAIN để xem bộ lọc status ảnh hưởng kế hoạch thế nào.

### Bước 7: OFFSET pagination

Trang đầu:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 3 OFFSET 0;
~~~

Trang thứ hai:

~~~sql
SELECT
    article_id,
    title,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 3 OFFSET 3;
~~~

Đối chiếu hai tập ID và xác nhận không trùng khi collection không thay đổi.

### Bước 8: keyset pagination theo score

Lấy score và article_id của hàng cuối trang đầu. Thay hai giá trị dưới đây bằng kết quả thực tế:

~~~sql
SELECT
    article_id,
    title,
    score
FROM (
    SELECT
        article_id,
        title,
        MATCH (title, body)
            AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
) AS ranked
WHERE score < 0.5000
   OR (score = 0.5000 AND article_id > 3)
ORDER BY score DESC, article_id ASC
LIMIT 3;
~~~

Thay 0.5000 và 3 bằng score gốc và ID của hàng cuối trang trước. Không dùng score làm tròn từ giao diện.

Đối chiếu kết quả với OFFSET khi dữ liệu không thay đổi. Sau đó thêm một bài mới chứa nhiều từ khóa và chạy lại cả hai truy vấn. Quan sát thứ tự có thể thay đổi vì collection và relevance score thay đổi.

### Bước 9: kiểm tra execution plan

~~~sql
EXPLAIN
SELECT
    article_id,
    MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH (title, body)
    AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, article_id ASC
LIMIT 3;
~~~

Kiểm tra access type, key, rows, Extra và thời gian EXPLAIN. Bảng nhỏ có thể không thể hiện rõ khác biệt hiệu năng; mục tiêu là nhận biết FULLTEXT access và sort.

### Bước 10: tạo snapshot Top-N

~~~sql
CREATE TABLE search_result_snapshot (
    search_id BINARY(16) NOT NULL,
    position_no BIGINT UNSIGNED NOT NULL,
    article_id BIGINT UNSIGNED NOT NULL,
    relevance_score DOUBLE NOT NULL,
    PRIMARY KEY (search_id, position_no),
    UNIQUE KEY uq_search_article (search_id, article_id)
) ENGINE=InnoDB;
~~~

Lưu kết quả xếp hạng:

~~~sql
INSERT INTO search_result_snapshot (
    search_id,
    position_no,
    article_id,
    relevance_score
)
SELECT
    UUID_TO_BIN('22222222-2222-2222-2222-222222222222'),
    ROW_NUMBER() OVER (
        ORDER BY score DESC, article_id ASC
    ),
    article_id,
    score
FROM (
    SELECT
        article_id,
        MATCH (title, body)
            AGAINST ('mysql search' IN NATURAL LANGUAGE MODE) AS score
    FROM articles
    WHERE MATCH (title, body)
        AGAINST ('mysql search' IN NATURAL LANGUAGE MODE)
) AS ranked;
~~~

Đọc trang đầu từ snapshot:

~~~sql
SELECT
    position_no,
    article_id,
    relevance_score
FROM search_result_snapshot
WHERE search_id = UUID_TO_BIN('22222222-2222-2222-2222-222222222222')
ORDER BY position_no
LIMIT 3;
~~~

Đọc trang kế:

~~~sql
SELECT
    position_no,
    article_id,
    relevance_score
FROM search_result_snapshot
WHERE search_id = UUID_TO_BIN('22222222-2222-2222-2222-222222222222')
  AND position_no > 3
ORDER BY position_no
LIMIT 3;
~~~

Sau khi tạo snapshot, thêm bài viết mới rồi đọc lại snapshot. ID và thứ tự snapshot không đổi vì score đã được lưu tại thời điểm tạo.

### Bước 11: dọn dẹp

~~~sql
DROP DATABASE mysql_fulltext_ranking_lab;
~~~

Chỉ chạy DROP DATABASE trên database lab vừa tạo.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không thấy cột score | MATCH() chỉ nằm trong WHERE | Đưa MATCH() AGAINST() vào SELECT list |
| Score bằng 0 | Không có token được index khớp hoặc token bị stopword/too short | Kiểm tra parser, stopword, token size và dữ liệu |
| Kết quả tự sắp xếp nhưng không ổn định | Dựa vào implicit relevance order hoặc score có tie | Viết ORDER BY score DESC, primary_key |
| Boolean mode không theo score | Boolean mode không tự sort relevance | SELECT score và ORDER BY tường minh |
| MATCH() báo không có FULLTEXT index phù hợp | Danh sách cột MATCH không khớp index | Tạo index đúng cột hoặc sửa MATCH list |
| Không thể dùng cột bảng khác trong AGAINST | AGAINST cần chuỗi hằng trong lúc đánh giá | Dùng parameter binding với search text |
| Trang sâu chậm | OFFSET lớn và phải xử lý tập kết quả full-text | Dùng keyset khi phù hợp hoặc lưu snapshot |
| Keyset lặp/bỏ sót khi score trùng | Cursor chỉ chứa score | Thêm khóa duy nhất vào ORDER BY và cursor |
| Keyset đổi kết quả giữa các request | Corpus thay đổi làm score và vị trí thay đổi | Lưu snapshot result cho phiên tìm kiếm |
| Keyset không nhanh hơn nhiều | Score là biểu thức động, không có B-tree index để seek | Đo EXPLAIN/latency; không kỳ vọng keyset loại bỏ full-text matching |
| Score thay đổi sau khi thêm bài | IDF và thống kê collection thay đổi | Chấp nhận ranking động hoặc snapshot kết quả |
| Score title/body bị thiên lệch | Cộng hai score khác collection với hệ số tùy ý | Đánh giá relevance và hiệu chỉnh trọng số bằng tập query |
| EXPLAIN full-text chậm | Optimizer đánh giá full-text expression khi lập kế hoạch | Hiểu đặc thù và đo query thực tế |
| Không tìm thấy dữ liệu vừa INSERT | InnoDB cập nhật FULLTEXT index tại COMMIT | Commit transaction trước khi tìm kiếm từ session khác |
| Không tìm được từ rất ngắn | Token size hoặc stopword loại từ khỏi index | Kiểm tra cấu hình, parser và rebuild index khi thay đổi |
| Query có % không hoạt động như LIKE | % không phải wildcard full-text | Dùng Boolean truncation * nếu phù hợp |
| Full-text search không hoạt động trên bảng partitioned | MySQL không hỗ trợ FULLTEXT search trên partitioned table | Đánh giá lại schema hoặc kiến trúc tìm kiếm |

## 19. Checklist thiết kế API tìm kiếm và phân trang

- [ ] Đã chọn natural-language hay Boolean mode theo yêu cầu.
- [ ] Đã xác định chính xác danh sách cột MATCH() và FULLTEXT index tương ứng.
- [ ] AGAINST() nhận search text qua parameter binding.
- [ ] Đã lấy score trong SELECT nếu API cần hiển thị hoặc phân trang theo score.
- [ ] Không xem score là xác suất hoặc phần trăm.
- [ ] Không so sánh score giữa query khác nhau như cùng thang đo.
- [ ] Đã viết ORDER BY score DESC tường minh.
- [ ] Đã thêm primary key/unique key làm tie-breaker.
- [ ] Không ROUND score trước khi sắp xếp hoặc tạo cursor.
- [ ] Đã kiểm tra điều kiện tự sắp xếp relevance của natural-language mode.
- [ ] Đã hiểu Boolean mode không tự sắp xếp relevance.
- [ ] Đã kiểm tra điều kiện đặc biệt của Top-N FULLTEXT optimization.
- [ ] Đã đo OFFSET ở trang sâu.
- [ ] Nếu dùng keyset theo score, cursor chứa score gốc và khóa phụ.
- [ ] Đã hiểu score có thể thay đổi khi collection thay đổi.
- [ ] Nếu cần thứ tự ổn định qua nhiều request, đã cân nhắc snapshot result.
- [ ] Đã đặt TTL và quy trình dọn snapshot.
- [ ] Đã đánh giá parser, stopword, token size, charset và collation.
- [ ] Đã đo tác động FULLTEXT index lên INSERT/UPDATE/DELETE và COMMIT.
- [ ] Đã kiểm tra EXPLAIN trên dữ liệu gần production.
- [ ] Đã kiểm thử các trường hợp query rỗng, quá phổ biến, đồng điểm và không có kết quả.

## 20. Nguyên tắc cần ghi nhớ

1. MATCH() AGAINST() trả relevance score cho document trong collection được index.
2. Natural-language score là floating-point không âm; score 0 biểu thị không có similarity.
3. Score không phải xác suất và không có thang đo cố định giữa các query.
4. Natural-language ranking phụ thuộc nội dung document và thống kê collection.
5. InnoDB Boolean ranking dựa trên BM25/TF-IDF; không áp dụng công thức đó như công thức chung cho mọi engine/mode.
6. Natural-language mode chỉ tự sắp xếp score trong các điều kiện cụ thể.
7. Boolean mode không tự sắp xếp theo relevance; phải ORDER BY tường minh.
8. Luôn thêm khóa duy nhất vào cuối ORDER BY để xử lý đồng điểm.
9. Không ROUND score trước khi sắp xếp hoặc tạo cursor.
10. FULLTEXT Top-N optimization chỉ áp dụng cho một số query shape hẹp.
11. OFFSET đơn giản nhưng trang sâu có thể tốn kém và dễ dịch chuyển khi dữ liệu thay đổi.
12. Keyset theo score giúp định nghĩa cursor rõ ràng nhưng không tạo B-tree seek trên score động.
13. Score có thể thay đổi khi document hoặc collection thay đổi.
14. Snapshot result phù hợp khi cần phân trang ổn định qua nhiều request.
15. Query expansion có thể mở rộng tập kết quả và thay đổi ranking.
16. Parser, stopword, token size, charset và collation quyết định từ nào được index.
17. InnoDB cập nhật FULLTEXT index theo COMMIT; full-text search chỉ trả dữ liệu đã commit.

## Tài liệu tham khảo chính thức

Các cú pháp và hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual**:

1. [Natural Language Full-Text Searches](https://dev.mysql.com/doc/refman/9.7/en/fulltext-natural-language.html): MATCH() AGAINST(), relevance score, điều kiện tự sắp xếp và các yếu tố ảnh hưởng score.
2. [Boolean Full-Text Searches](https://dev.mysql.com/doc/refman/9.7/en/fulltext-boolean.html): toán tử Boolean, cách sắp xếp, InnoDB TF-IDF/BM25 và relevance ranking.
3. [Full-Text Search Functions](https://dev.mysql.com/doc/refman/9.7/en/fulltext-search.html): cú pháp MATCH/AGAINST và các search modifier.
4. [Full-Text Restrictions](https://dev.mysql.com/doc/refman/9.7/en/fulltext-restrictions.html): giới hạn engine, partitioning, charset/collation, MATCH column list và cập nhật index theo COMMIT.
5. [Column Indexes — FULLTEXT Indexes](https://dev.mysql.com/doc/refman/9.7/en/column-indexes.html): điều kiện tối ưu FULLTEXT Top-N, LIMIT và EXPLAIN.
6. [Full-Text Searches with Query Expansion](https://dev.mysql.com/doc/refman/9.7/en/fulltext-query-expansion.html): cơ chế mở rộng truy vấn và ảnh hưởng đến tập kết quả.
7. [Fine-Tuning MySQL Full-Text Search](https://dev.mysql.com/doc/refman/9.7/en/fulltext-fine-tuning.html): token size, stopword và rebuild FULLTEXT index.

