# Chỉ mục tìm kiếm toàn văn và khác biệt với tìm chuỗi bằng LIKE

Ứng dụng thường cần tìm nội dung trong tiêu đề, mô tả, ghi chú, tài liệu hoặc nội dung do người dùng nhập. Có hai cách tiếp cận phổ biến: dùng điều kiện chuỗi như LIKE để so khớp mẫu ký tự, hoặc dùng chỉ mục tìm kiếm toàn văn (full-text index) để tìm từ và cụm từ theo cách ngôn ngữ tự nhiên.

Hai cách này phục vụ những yêu cầu khác nhau. LIKE kiểm tra một chuỗi có khớp mẫu ký tự hay không; full-text search phân tích văn bản thành token hoặc lexeme, áp dụng quy tắc ngôn ngữ và tìm theo từ, cụm từ hoặc toán tử tìm kiếm. Chọn sai cơ chế có thể làm truy vấn quét nhiều hàng, tạo kết quả không đúng kỳ vọng hoặc tăng chi phí ghi mà không cải thiện trải nghiệm tìm kiếm.

Trong phạm vi DATABASE_PERFORMANCE, cần hiểu cách chỉ mục chuyên biệt tổ chức dữ liệu, điều kiện mà bộ tối ưu có thể tận dụng, chi phí cập nhật và cách đo hiệu quả trên workload thật. Bài học này giải thích full-text index, so sánh với LIKE, trình bày cách triển khai trên các hệ quản trị phổ biến và quy trình kiểm chứng.

## 1. LIKE tìm mẫu ký tự như thế nào?

LIKE là toán tử so khớp mẫu chuỗi. Hai ký tự đại diện thường gặp:

- % khớp với không hoặc nhiều ký tự.
- _ khớp với đúng một ký tự.

Ví dụ:

```sql
-- Tìm giá trị bắt đầu bằng "Data"
SELECT id, title
FROM articles
WHERE title LIKE 'Data%';

-- Tìm giá trị kết thúc bằng "Guide"
SELECT id, title
FROM articles
WHERE title LIKE '%Guide';

-- Tìm chuỗi "base" ở bất kỳ vị trí nào
SELECT id, title
FROM articles
WHERE title LIKE '%base%';

-- Ký tự "_" đại diện cho một ký tự
SELECT code
FROM products
WHERE code LIKE 'A_7%';
```

LIKE so sánh ký tự theo collation và quy tắc của hệ quản trị. Collation có thể ảnh hưởng đến phân biệt hoa/thường, dấu, thứ tự ký tự và cách so sánh. Vì vậy, cùng một mẫu LIKE có thể cho kết quả khác giữa hai cột hoặc hai hệ quản trị có collation khác nhau.

Nếu cần tìm ký tự % hoặc _ theo nghĩa đen, phải escape chúng theo cú pháp của hệ quản trị. Mỗi SQL dialect có quy tắc chuỗi escape và cách biểu diễn dấu gạch chéo ngược riêng; hãy kiểm tra cú pháp của DBMS thay vì ghép pattern tùy tiện.

### LIKE có sử dụng B-tree index không?

Khả năng tận dụng B-tree phụ thuộc hình dạng pattern, collation, kiểu dữ liệu và hệ quản trị:

- Pattern có tiền tố cố định như Data% có thể được chuyển thành một khoảng tìm kiếm trên B-tree nếu điều kiện và collation cho phép.
- Pattern bắt đầu bằng wildcard như %Data hoặc %Data% thường không xác định được điểm bắt đầu trong thứ tự B-tree, nên chỉ mục B-tree thông thường không thể thu hẹp phạm vi theo tiền tố.
- Một số hệ quản trị có thể tối ưu thêm các dạng pattern hoặc dùng loại chỉ mục khác; cần xác minh bằng execution plan.

Ví dụ, chỉ mục trên title có thể hỗ trợ truy vấn LIKE tiền tố:

```sql
CREATE INDEX idx_articles_title
ON articles (title);

SELECT id, title
FROM articles
WHERE title LIKE 'Data%';
```

Nhưng chỉ mục B-tree đó thường không giải quyết được truy vấn:

```sql
SELECT id, title
FROM articles
WHERE title LIKE '%database%';
```

Với mẫu có wildcard đầu, DB có thể phải quét nhiều hoặc toàn bộ hàng rồi kiểm tra từng chuỗi. Nếu bảng nhỏ, quét tuần tự vẫn có thể rẻ hơn truy cập chỉ mục; việc dùng scan không tự động chứng minh thiếu chỉ mục.

LIKE phù hợp khi cần khớp một mẫu ký tự, tìm tiền tố hoặc hậu tố đơn giản, tìm đoạn ký tự con, hoặc truy vấn trên tập dữ liệu nhỏ. LIKE không tự hiểu từ đồng nghĩa, hình thái từ, từ dừng, trọng số từ hoặc thứ hạng liên quan. Nó cũng không tự phân tích câu thành các token ngôn ngữ.

## 2. Full-text search tổ chức dữ liệu khác LIKE

Chỉ mục toàn văn thường phân tích văn bản thành các đơn vị tìm kiếm. Quy trình khái quát gồm:

1. Tách văn bản thành token theo bộ phân tích (parser/tokenizer).
2. Chuẩn hóa token, chẳng hạn chuyển chữ hoa thành chữ thường hoặc chuẩn hóa dạng từ.
3. Có thể loại bỏ stop words như một số từ quá phổ biến.
4. Có thể áp dụng stemming hoặc lemmatization để gom các dạng từ về một gốc hoặc dạng chuẩn.
5. Ghi nhận vị trí token trong tài liệu và tạo cấu trúc chỉ mục đảo (inverted index).
6. Khi tìm kiếm, phân tích truy vấn theo quy tắc tương ứng rồi tra các token trong chỉ mục.

Inverted index ánh xạ một token tới danh sách tài liệu hoặc vị trí xuất hiện. Nhờ vậy, hệ thống có thể tìm tài liệu chứa một từ mà không phải so sánh toàn bộ văn bản của mọi hàng.

Tùy hệ quản trị, full-text search có thể hỗ trợ tìm tất cả từ hoặc một số từ trong truy vấn, tìm cụm từ theo thứ tự và khoảng cách, toán tử AND/OR/NOT, tìm dạng từ liên quan, xếp hạng kết quả và trọng số khác nhau cho tiêu đề, mô tả, nội dung. Không phải mọi hệ quản trị cung cấp cùng tập tính năng; cần đọc cú pháp và quy tắc của DBMS đang sử dụng.

### Full-text search không phải tìm chuỗi con tùy ý

Full-text search thường tìm theo token hoặc lexeme. Nếu người dùng tìm base, kết quả có thể gồm tài liệu chứa token base, nhưng không nhất thiết gồm mọi từ có chuỗi con base như database. Kết quả phụ thuộc parser, stemming, dictionary và chế độ truy vấn.

Ngược lại, LIKE '%base%' có thể khớp database, based hoặc một đoạn nằm giữa từ. Nó không cần hiểu ranh giới từ.

| Yêu cầu | LIKE | Full-text search |
|---|---|---|
| Khớp một đoạn ký tự bất kỳ | Có thể, với wildcard | Thường không phải mục tiêu chính |
| Tìm từ theo token | Có thể nếu mẫu chuỗi phù hợp, nhưng không hiểu ngôn ngữ | Có |
| Tìm cụm từ | Phải tự biểu diễn mẫu ký tự, dễ phụ thuộc định dạng | Thường có cú pháp phrase |
| Stemming/biến thể từ | Không tự hỗ trợ | Có thể hỗ trợ qua analyzer/dictionary |
| Stop words | Không tự loại bỏ | Có thể được loại bỏ theo cấu hình |
| Ranking mức liên quan | Không có sẵn | Thường có |
| B-tree với tiền tố cố định | Có thể tận dụng | Dùng cấu trúc full-text riêng |
| Tìm substring với wildcard đầu | B-tree thường không hiệu quả | Không bảo đảm khớp substring |

## 3. Chọn cơ chế theo yêu cầu tìm kiếm

Trước khi tạo chỉ mục, hãy mô tả chính xác người dùng mong muốn tìm gì:

- **Tiền tố:** tìm tên bắt đầu bằng chuỗi nhập vào, ví dụ Tran%.
- **Chuỗi con:** tìm chuỗi ký tự ở bất kỳ vị trí nào, ví dụ %phan%.
- **Từ:** tìm tài liệu có một từ độc lập hoặc token tương ứng.
- **Cụm từ:** tìm các từ xuất hiện liền nhau theo thứ tự.
- **Tất cả từ / bất kỳ từ:** xác định quan hệ logic giữa các token.
- **Ngôn ngữ và biến thể:** xử lý dấu, hoa/thường, từ ghép, biến thể từ và từ dừng.
- **Xếp hạng:** kết quả nào nên đứng đầu khi có nhiều tài liệu khớp?

| Tình huống | Cơ chế nên xem xét | Lý do |
|---|---|---|
| Mã SKU bắt đầu bằng chuỗi người dùng nhập | B-tree và LIKE tiền tố | Có tiền tố cố định |
| Tìm tên sản phẩm có chứa một đoạn ký tự bất kỳ | Cơ chế substring như trigram hoặc giải pháp tương đương | Có wildcard đầu, cần tìm đoạn nằm giữa từ |
| Tìm bài viết chứa các từ liên quan đến database tuning | Full-text index | Cần phân tích token và xếp hạng |
| Tìm cụm từ chính xác query plan | Full-text phrase search hoặc so khớp chuỗi tùy yêu cầu | Cần giữ thứ tự và khoảng cách từ |
| Tìm số điện thoại hoặc mã định danh | So khớp chính xác/prefix theo kiểu dữ liệu | Không cần stemming hay ranking ngôn ngữ |
| Tìm tên gần giống do gõ sai | Fuzzy search, trigram hoặc công cụ tìm kiếm phù hợp | Cần đo độ tương tự, không chỉ token |

Không nên dùng full-text search cho mọi cột văn bản. Mã đơn hàng, email, SKU, số điện thoại và chuỗi định danh thường cần quy tắc so khớp chính xác hoặc tiền tố. Cũng không nên dùng LIKE trên nội dung dài chỉ vì cú pháp đơn giản nếu workload thực tế phải quét hàng triệu tài liệu.

## 4. PostgreSQL: tsvector, tsquery và GIN

PostgreSQL cung cấp text search tích hợp. Văn bản được chuyển thành tsvector, còn truy vấn tìm kiếm được chuyển thành tsquery. Toán tử @@ kiểm tra một vector có khớp truy vấn hay không.

### Tạo chỉ mục toàn văn

Giả sử bảng articles có title và body. Có thể tạo GIN index trên biểu thức kết hợp:

```sql
CREATE INDEX idx_articles_fts
ON articles
USING GIN (
    to_tsvector(
        'simple',
        coalesce(title, '') || ' ' || coalesce(body, '')
    )
);
```

Trong ví dụ, cấu hình simple chuẩn hóa token nhưng không thực hiện stemming theo ngôn ngữ. Nếu cần stemming hoặc stop words, hãy chọn text search configuration phù hợp với ngôn ngữ và dữ liệu. Tên cấu hình có sẵn phụ thuộc bản cài đặt.

Truy vấn phải dùng biểu thức và cấu hình tương ứng:

```sql
SELECT id, title
FROM articles
WHERE to_tsvector(
    'simple',
    coalesce(title, '') || ' ' || coalesce(body, '')
) @@ plainto_tsquery('simple', 'database optimization');
```

Các hàm tạo truy vấn thường dùng:

- plainto_tsquery: chuyển văn bản thông thường thành điều kiện AND giữa các từ sau phân tích.
- phraseto_tsquery: tạo truy vấn cụm từ, giữ quan hệ vị trí giữa token.
- websearch_to_tsquery: hỗ trợ cú pháp tìm kiếm gần với cách người dùng nhập trên giao diện web.
- to_tsquery: dùng cú pháp tsquery rõ ràng, cho phép toán tử truy vấn chuyên biệt.

Ví dụ tìm cụm từ và xếp hạng:

```sql
SELECT
    id,
    title,
    ts_rank(
        to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, '')),
        phraseto_tsquery('simple', 'database optimization')
    ) AS rank
FROM articles
WHERE to_tsvector(
    'simple',
    coalesce(title, '') || ' ' || coalesce(body, '')
) @@ phraseto_tsquery('simple', 'database optimization')
ORDER BY rank DESC
LIMIT 20;
```

Để tránh tính biểu thức lặp lại trong truy vấn và bảo đảm biểu thức khớp với chỉ mục, có thể dùng generated column lưu tsvector nếu phiên bản và biểu thức đáp ứng yêu cầu tính bất biến:

```sql
ALTER TABLE articles
ADD COLUMN search_document tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(body, '')), 'B')
) STORED;

CREATE INDEX idx_articles_search_document
ON articles
USING GIN (search_document);

SELECT id, title
FROM articles
WHERE search_document @@ plainto_tsquery('simple', 'database optimization');
```

Trọng số A/B giúp ưu tiên token từ tiêu đề hơn nội dung khi tính ranking bằng các hàm phù hợp. Cột generated stored làm tăng dung lượng hàng và chi phí ghi vì vector cần được cập nhật khi nguồn thay đổi.

### Kiểm tra parser và cấu hình ngôn ngữ

PostgreSQL có thể hiển thị cách một cấu hình phân tích văn bản bằng ts_debug:

```sql
SELECT *
FROM ts_debug('simple', 'Tối ưu hiệu năng cơ sở dữ liệu');
```

Với nội dung tiếng Việt, không nên mặc định rằng cấu hình english hoặc một cấu hình bất kỳ sẽ tách từ, chuẩn hóa dấu và xử lý từ ghép theo kỳ vọng. Cần kiểm tra parser, dictionary, stop words và từ điển của cấu hình đang cài. Nếu ứng dụng cần tìm substring hoặc tên riêng, có thể cần cơ chế khác song song.

### GIN và GiST

GIN thường là lựa chọn phổ biến cho tìm kiếm toàn văn vì lưu quan hệ token tới các tài liệu chứa token. GiST cũng có thể hỗ trợ text search trong một số trường hợp, nhưng có thể dùng biểu diễn lossy và cần recheck hàng ứng viên. Hãy đo kích thước, tốc độ truy vấn, tốc độ cập nhật và thời gian build trên dữ liệu thực tế.

## 5. MySQL: FULLTEXT và MATCH ... AGAINST

MySQL hỗ trợ FULLTEXT index trên các cột kiểu CHAR, VARCHAR hoặc TEXT tùy engine và phiên bản. Với InnoDB, có thể tạo chỉ mục:

```sql
ALTER TABLE articles
ADD FULLTEXT INDEX ft_articles_title_body (title, body);
```

Truy vấn natural language:

```sql
SELECT
    id,
    title,
    MATCH(title, body)
        AGAINST ('database optimization' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH(title, body)
        AGAINST ('database optimization' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC
LIMIT 20;
```

Danh sách cột trong MATCH() cần tương ứng với FULLTEXT index phù hợp. Natural language mode phân tích từ theo parser và quy tắc của MySQL, sau đó tính điểm liên quan.

Boolean mode cho phép biểu diễn điều kiện tìm kiếm bằng cú pháp riêng:

```sql
SELECT id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+database +optimization -deprecated' IN BOOLEAN MODE);
```

Các ký hiệu Boolean, quy tắc bắt buộc/loại trừ, prefix và phrase cần được dùng theo cú pháp MySQL. Không được coi chuỗi truy vấn Boolean là SQL; vẫn phải truyền nó qua parameter binding để tránh SQL injection.

### Những yếu tố ảnh hưởng kết quả MySQL FULLTEXT

- **Stopword list:** từ phổ biến có thể bị loại khỏi chỉ mục hoặc truy vấn.
- **Token size:** InnoDB có giới hạn kích thước token tối thiểu/tối đa theo cấu hình.
- **Parser:** parser mặc định tách token theo quy tắc của engine; parser ngram có thể phù hợp với một số ngôn ngữ không phân cách từ bằng dấu cách hoặc yêu cầu phân đoạn đặc biệt.
- **Collation và charset:** ảnh hưởng chuẩn hóa và so sánh ký tự.
- **Engine/version:** hành vi và giới hạn có thể khác giữa InnoDB, MyISAM và các phiên bản.

Có thể kiểm tra parser và thống kê full-text của InnoDB bằng các bảng hệ thống trong INFORMATION_SCHEMA hoặc INNODB_FT_* tùy phiên bản và cấu hình. Khi thay đổi stopword hoặc token-size settings, cần lập kế hoạch rebuild index và kiểm thử trên môi trường tương ứng.

MySQL FULLTEXT tìm token theo parser. Nó không tự động biến thành tìm chuỗi con tùy ý như LIKE '%base%'. Nếu yêu cầu là tìm substring, cần đánh giá ngram parser hoặc giải pháp chuyên biệt và xác nhận chính xác quy tắc khớp.

## 6. SQL Server: Full-Text Catalog và CONTAINS/FREETEXT

SQL Server dùng Full-Text Search với full-text catalog và full-text index. Chỉ mục liên kết với một unique key index để định danh hàng.

Ví dụ tạo catalog và chỉ mục:

```sql
CREATE FULLTEXT CATALOG ArticleCatalog AS DEFAULT;
GO

CREATE FULLTEXT INDEX ON dbo.Articles
(
    Title LANGUAGE 1033,
    Body LANGUAGE 1033
)
KEY INDEX PK_Articles
ON ArticleCatalog
WITH CHANGE_TRACKING AUTO;
GO
```

1033 là LCID tiếng Anh trong ví dụ. Chọn language phù hợp với nội dung thực tế và các word breaker, stemmer được cài đặt. Tên khóa PK_Articles phải là unique key index thực có của bảng.

CONTAINS cho phép truy vấn điều kiện toàn văn rõ ràng:

```sql
SELECT a.ArticleId, a.Title
FROM dbo.Articles AS a
WHERE CONTAINS((a.Title, a.Body), '"database optimization"');
```

FREETEXT cho phép truyền cụm từ tự nhiên để SQL Server phân tích theo ngôn ngữ:

```sql
SELECT a.ArticleId, a.Title
FROM dbo.Articles AS a
WHERE FREETEXT((a.Title, a.Body), 'improve database query performance');
```

Có thể dùng CONTAINSTABLE hoặc FREETEXTTABLE để nhận khóa hàng và rank:

```sql
SELECT a.ArticleId, a.Title, ft.RANK
FROM CONTAINSTABLE(
    dbo.Articles,
    (Title, Body),
    '"database optimization"'
) AS ft
JOIN dbo.Articles AS a
    ON a.ArticleId = ft.[KEY]
ORDER BY ft.RANK DESC;
```

Full-text population có thể được theo dõi qua các catalog view và trạng thái population. Với change tracking, cần hiểu cách SQL Server cập nhật thay đổi vào full-text index và thời gian để nội dung mới có thể tìm thấy.

SQL Server Full-Text Search dùng word breaker, stemmer và stoplist theo ngôn ngữ. Nó phù hợp với tìm kiếm ngôn ngữ tự nhiên nhưng không phải phép so khớp substring tùy ý. LIKE '%term%' và CONTAINS có ngữ nghĩa khác nhau; kết quả của chúng không nhất thiết giống nhau.

## 7. Oracle Text: CONTEXT index và CONTAINS

Oracle Text cung cấp khả năng tìm kiếm tài liệu và nội dung văn bản. Với kiểu index CONTEXT, có thể tạo chỉ mục trên cột nội dung:

```sql
CREATE INDEX idx_articles_text
ON articles(body)
INDEXTYPE IS CTXSYS.CONTEXT;
```

Sau đó tìm theo toán tử Oracle Text:

```sql
SELECT id, title, SCORE(1) AS score
FROM articles
WHERE CONTAINS(body, 'database AND optimization', 1) > 0
ORDER BY score DESC;
```

Oracle Text có lexer, stoplist, section group và các thành phần cấu hình để phân tích nội dung. Có thể tạo preference phù hợp với định dạng hoặc ngôn ngữ, sau đó gắn preference vào index. Cần xác định chính sách đồng bộ chỉ mục; với CONTEXT index, thay đổi dữ liệu nguồn có thể cần đồng bộ theo cấu hình, chẳng hạn dùng CTX_DDL.SYNC_INDEX theo lịch hoặc cơ chế phù hợp.

Ví dụ đồng bộ thủ công:

```sql
BEGIN
  CTX_DDL.SYNC_INDEX('IDX_ARTICLES_TEXT');
END;
/
```

Thời điểm dữ liệu mới xuất hiện trong kết quả tìm kiếm phụ thuộc loại index và chính sách đồng bộ. Nếu nghiệp vụ yêu cầu dữ liệu vừa commit phải tìm thấy ngay, cần kiểm thử độ trễ cập nhật và chọn cấu hình phù hợp.

Oracle Text hỗ trợ nhiều toán tử truy vấn và khả năng xếp hạng. Cú pháp, preference và quyền thực thi phụ thuộc phiên bản, schema và cấu hình Oracle Text đang triển khai.

## 8. Tiếng Việt, dấu và phân đoạn từ

Văn bản tiếng Việt đặt ra một số yêu cầu riêng:

- Có dấu và không dấu: cơ sở dữ liệu và co so du lieu có nên được xem là tương đương không?
- Từ ghép và ranh giới từ: một cụm có thể gồm nhiều tiếng; việc tách theo khoảng trắng chưa chắc phản ánh đơn vị tìm kiếm nghiệp vụ.
- Biến thể viết: chữ hoa/thường, dấu câu, ký tự Unicode tổ hợp và dạng chuẩn hóa Unicode.
- Từ dừng: từ xuất hiện thường xuyên có thể ít giá trị tìm kiếm nhưng việc loại bỏ có thể làm mất ý nghĩa của cụm.
- Tên riêng, mã và thuật ngữ: có thể cần giữ nguyên token hoặc hỗ trợ từ điển riêng.

Không nên giả định mọi full-text engine đều xử lý tiếng Việt tốt chỉ vì hỗ trợ Unicode. Unicode cho phép lưu và so sánh ký tự, nhưng không tự cung cấp bộ phân tích từ tiếng Việt hoặc quy tắc bỏ dấu.

### Xác định quy tắc tìm kiếm trước khi tạo index

Hãy xây dựng bộ ví dụ đại diện:

| Văn bản trong dữ liệu | Truy vấn cần thử | Câu hỏi |
|---|---|---|
| Cơ sở dữ liệu quan hệ | cơ sở dữ liệu | Có tìm thấy đủ cụm từ mong muốn không? |
| Tối ưu hóa truy vấn | toi uu hoa truy van | Có cần hỗ trợ truy vấn không dấu không? |
| Database performance | database | Tìm token độc lập hay cả chuỗi con trong từ? |
| Hệ quản trị CSDL | CSDL | Có cần từ điển đồng nghĩa hoặc alias không? |
| Nguyễn Văn An | nguyen van an | Chuẩn hóa dấu và tên riêng được xử lý ra sao? |
| SQL Server 2022 | SQL 2022 | Mã và số có được giữ làm token không? |

Nếu cần tìm không dấu, có thể tạo trường chuẩn hóa riêng hoặc cấu hình analyzer phù hợp. Cần giữ nguyên dữ liệu gốc để hiển thị và bảo đảm chính sách chuẩn hóa nhất quán giữa lúc index và lúc query. Không nên chỉ bỏ dấu ở truy vấn mà không chuẩn hóa nội dung đã lập chỉ mục theo cùng quy tắc.

Đối với nội dung tiếng Việt quan trọng, hãy thử parser/dictionary chuyên biệt hoặc search engine phù hợp với ngôn ngữ. Đánh giá precision (tỷ lệ kết quả trả về có liên quan) và recall (tỷ lệ tài liệu liên quan được tìm thấy), không chỉ đo tốc độ.

## 9. Tìm substring bằng trigram hoặc cơ chế tương tự

Nếu yêu cầu thực sự là tìm một chuỗi con ở bất kỳ vị trí nào, full-text token search có thể không phù hợp. Một số hệ quản trị có chỉ mục chuyên biệt cho substring.

PostgreSQL có extension pg_trgm, biểu diễn chuỗi thành các trigram (nhóm ba ký tự liên tiếp) và hỗ trợ một số phép so khớp như LIKE/ILIKE hoặc similarity. Ví dụ:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_articles_title_trgm
ON articles
USING GIN (title gin_trgm_ops);

SELECT id, title
FROM articles
WHERE title ILIKE '%database%';
```

Chỉ mục trigram có thể giúp truy vấn wildcard đầu mà B-tree thông thường không hỗ trợ hiệu quả. Tuy nhiên, chuỗi tìm quá ngắn hoặc không tạo đủ trigram hữu ích có thể khiến index không giúp nhiều. Trigram index cũng có dung lượng và chi phí cập nhật riêng.

Một số hệ quản trị hoặc search engine khác có parser ngram, reverse index hoặc cấu trúc tương tự. Cần xác định đúng ngữ nghĩa, vì ngram và full-text tokenization không tương đương. Nếu người dùng cần tìm một phần mã hoặc tên, trigram/fuzzy search có thể phù hợp hơn full-text.

## 10. Chi phí lưu trữ và cập nhật chỉ mục toàn văn

Full-text index tạo cấu trúc bổ sung ngoài dữ liệu gốc. Dung lượng phụ thuộc số lượng token duy nhất, số lần xuất hiện, vị trí, số cột được index, độ dài văn bản, cấu hình analyzer và cách DBMS lưu trữ.

Các chi phí cần tính:

- Dung lượng index và metadata.
- CPU để phân tích token khi insert/update.
- I/O và log phát sinh trong quá trình cập nhật.
- Thời gian build hoặc rebuild index trên bảng lớn.
- Độ trễ giữa thay đổi dữ liệu và khả năng tìm thấy nội dung mới.
- Chi phí backup, replication và bảo trì.
- Tài nguyên truy vấn khi tìm kiếm rộng hoặc trả về quá nhiều kết quả.

Nếu một hàng có nội dung dài được cập nhật thường xuyên, full-text index có thể tạo nhiều công việc bảo trì. Có thể cân nhắc tách nội dung ít thay đổi, giới hạn trường được index hoặc đưa cập nhật tìm kiếm vào pipeline bất đồng bộ nếu nghiệp vụ chấp nhận độ trễ.

Đối với index được cập nhật bất đồng bộ, cần theo dõi backlog, thời gian xử lý và lỗi đồng bộ. Không được giả định dữ liệu đã commit chắc chắn xuất hiện ngay trong kết quả full-text nếu cơ chế index chưa hoàn tất.

## 11. Đo hiệu năng và chất lượng kết quả

Một benchmark tìm kiếm nên có dữ liệu đại diện và bộ truy vấn thực tế. Đừng chỉ chạy một từ phổ biến trên bảng nhỏ rồi kết luận full-text index hiệu quả.

### Baseline cho LIKE

Ghi lại thời gian p50/p95/p99 và số truy vấn mỗi giây; số hàng được kiểm tra và số hàng trả về; logical reads/physical reads hoặc chỉ số tương đương; CPU, I/O và dung lượng dữ liệu; pattern cụ thể; và execution plan cho biết scan hay seek, có dùng chỉ mục hay không.

### Baseline cho full-text

Ghi lại thời gian tìm kiếm và ranking; số token trong truy vấn và số tài liệu ứng viên; số hàng cuối cùng sau filter bổ sung; kích thước full-text index và thời gian build; chi phí insert/update/delete; độ trễ đồng bộ; precision/recall trên bộ truy vấn được đánh giá.

### So sánh công bằng

1. Dùng cùng tập dữ liệu và cùng bộ truy vấn đại diện.
2. Định nghĩa trước ngữ nghĩa mong muốn: substring, token, phrase hay Boolean.
3. Không so sánh hai truy vấn có ngữ nghĩa khác nhau như thể chúng trả lời cùng câu hỏi.
4. Đo cả cache ấm và tình huống cache lạnh nếu workload có liên quan.
5. Đo nhiều lần, tách thời gian build index khỏi thời gian truy vấn.
6. Đo cả đọc và ghi để thấy chi phí duy trì index.
7. Kiểm tra số lượng và độ liên quan của kết quả, không chỉ thời gian.

Kế hoạch thực thi có thể cho thấy full-text index được sử dụng, nhưng cần xem số ứng viên, filter còn lại và ranking. Một truy vấn full-text quá rộng có thể trả về hàng trăm nghìn tài liệu; việc sort theo rank hoặc join sang bảng khác vẫn có thể tốn kém.

## 12. Kết hợp tìm kiếm toàn văn với điều kiện nghiệp vụ

Trong ứng dụng thực tế, tìm kiếm văn bản thường đi kèm filter theo tenant, trạng thái, quyền truy cập, ngày hoặc danh mục. Ví dụ:

```sql
SELECT id, title
FROM articles
WHERE tenant_id = ?
  AND status = 'PUBLISHED'
  AND /* full-text predicate phù hợp với DBMS */;
```

Full-text index giúp tìm tài liệu theo nội dung; chỉ mục B-tree hoặc cấu trúc khác có thể giúp lọc theo tenant/status. Bộ tối ưu cần kết hợp hai tập ứng viên. Hiệu năng phụ thuộc độ chọn lọc, khả năng kết hợp chỉ mục và thứ tự xử lý.

Các nguyên tắc quan trọng:

- Luôn áp dụng kiểm tra quyền truy cập và tenant ở phía DB hoặc lớp bảo vệ đáng tin cậy; không dựa vào ranking để giới hạn dữ liệu người dùng được phép xem.
- Đánh giá số tài liệu ứng viên trước và sau filter.
- Nếu một tenant chiếm phần lớn dữ liệu, cân nhắc partitioning hoặc chiến lược index theo phạm vi nếu DBMS hỗ trợ.
- Tránh trả về quá nhiều kết quả; dùng top-k, pagination hoặc cursor phù hợp.
- Ranking nên được tính trên tập ứng viên cần thiết; filter nghiệp vụ phải được áp dụng đúng để không lộ dữ liệu.
- Dùng parameter binding cho nội dung truy vấn và kiểm soát cú pháp đặc biệt của full-text query language.

Full-text query có thể có cú pháp riêng cho dấu ngoặc, dấu cộng/trừ, wildcard hoặc phrase. Parameter binding bảo vệ lớp SQL, nhưng ứng dụng vẫn cần kiểm tra cú pháp tìm kiếm mà người dùng được phép sử dụng và giới hạn độ phức tạp truy vấn.

## 13. Ví dụ lựa chọn cho chức năng tìm kiếm bài viết

Một ứng dụng có bảng articles gồm id, tenant_id, status, title, body và created_at. Người dùng có thể tìm mã bài, tên bài hoặc nội dung.

### Yêu cầu 1: mã bài bắt đầu bằng chuỗi nhập

Nếu article_code được tìm theo tiền tố, B-tree và LIKE tiền tố là phù hợp:

```sql
CREATE INDEX idx_articles_code
ON articles(article_code);

SELECT id, article_code, title
FROM articles
WHERE article_code LIKE 'DB-20%';
```

### Yêu cầu 2: tìm từ trong tiêu đề và nội dung

Dùng full-text index với analyzer phù hợp. Truy vấn cần kết hợp điều kiện tenant và trạng thái, sau đó xếp hạng kết quả trong phạm vi được phép.

### Yêu cầu 3: tìm đoạn ký tự nằm giữa tên

Nếu người dùng nhập tabase và muốn tìm cả database, full-text token search có thể không trả về kết quả đó. Cần substring index như trigram hoặc cơ chế ngram đã được kiểm chứng.

### Yêu cầu 4: tìm cụm từ chính xác

Dùng phrase query của full-text engine nếu quy tắc token và khoảng cách từ phù hợp. Nếu nghiệp vụ yêu cầu chuỗi ký tự liên tiếp tuyệt đối, cần dùng phép so khớp chuỗi và quy tắc chuẩn hóa rõ ràng.

Một ô tìm kiếm trên giao diện có thể định tuyến nhiều kiểu truy vấn theo loại đầu vào hoặc chế độ người dùng chọn. Không nên ép tất cả yêu cầu vào một câu LIKE hoặc một full-text query duy nhất.

## 14. Quy trình triển khai an toàn

1. **Thu thập truy vấn thực tế.** Phân loại prefix, substring, token, phrase, fuzzy và mã định danh.
2. **Định nghĩa ngữ nghĩa.** Xác định hoa/thường, dấu, stop words, stemming, từ ghép, thứ hạng và độ mới dữ liệu.
3. **Chọn cơ chế.** B-tree cho exact/prefix phù hợp; full-text cho token/phrase; trigram hoặc ngram cho substring/fuzzy khi được hỗ trợ.
4. **Kiểm tra parser/analyzer.** Dùng tập dữ liệu ngôn ngữ đại diện, bao gồm tên riêng, dấu, từ ghép và mã.
5. **Tạo index trong môi trường thử nghiệm.** Đo thời gian build, dung lượng, ảnh hưởng ghi và khả năng đồng bộ.
6. **Kiểm tra execution plan.** Xác nhận truy vấn dùng index dự kiến và số ứng viên hợp lý.
7. **Đánh giá relevance.** Kiểm tra precision, recall, phrase matching và ranking.
8. **Thử tải đồng thời.** Kết hợp truy vấn tìm kiếm với insert/update và workload giao dịch thông thường.
9. **Triển khai có theo dõi.** Theo dõi p95/p99, lỗi, index size, write latency và độ trễ cập nhật.
10. **Giữ phương án hoàn tác.** Xác định cách bỏ index hoặc quay lại chế độ truy vấn cũ nếu kết quả không đạt.

Không nên xây dựng chỉ mục toàn văn chỉ dựa trên một ví dụ tìm kiếm. Cần có bộ truy vấn và dữ liệu đại diện để tránh tối ưu cho một từ khóa hiếm hoặc một trường hợp ngôn ngữ đơn giản.

## 15. Những sai lầm thường gặp

- **Dùng LIKE '%term%' trên bảng rất lớn mà không đo:** B-tree thông thường thường không thể thu hẹp phạm vi theo wildcard đầu.
- **Dùng full-text để thay thế mọi LIKE:** full-text tìm theo token, không bảo đảm tìm substring ở giữa từ.
- **Cho rằng full-text index luôn nhanh:** truy vấn quá rộng, ranking hoặc filter bổ sung vẫn có thể tốn CPU và I/O.
- **Không kiểm tra analyzer:** từ bị tách, chuẩn hóa hoặc loại bỏ ngoài kỳ vọng khiến kết quả thiếu hoặc sai.
- **Bỏ qua tiếng Việt và Unicode:** hỗ trợ Unicode không đồng nghĩa có bộ phân tích từ tiếng Việt phù hợp.
- **Quên chi phí ghi:** mọi thay đổi nội dung được index đều có thể làm tăng CPU, I/O, log và thời gian cập nhật.
- **Không kiểm tra độ trễ đồng bộ:** index bất đồng bộ có thể chưa chứa tài liệu vừa commit.
- **Dùng cú pháp full-text do người dùng ghép trực tiếp vào SQL:** tạo nguy cơ injection và truy vấn quá phức tạp.
- **So sánh hiệu năng nhưng không so sánh ngữ nghĩa:** LIKE substring và full-text token search có thể trả về tập kết quả khác nhau.
- **Không kiểm tra kế hoạch và số ứng viên:** index có thể được dùng nhưng vẫn tạo tập kết quả trung gian rất lớn.

## 16. Checklist chọn và kiểm chứng chỉ mục tìm kiếm

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Người dùng cần tìm prefix, substring, token, phrase hay fuzzy? | Ngữ nghĩa tìm kiếm được mô tả rõ |
| LIKE hiện tại có wildcard đầu không? | Đã kiểm tra khả năng B-tree và execution plan |
| DBMS hỗ trợ full-text index nào? | Chọn đúng tính năng và phiên bản |
| Analyzer có xử lý đúng ngôn ngữ và dấu không? | Có bộ truy vấn kiểm thử đại diện |
| Stop words, stemming và ranking có phù hợp không? | Kết quả được đánh giá về relevance |
| Dữ liệu mới xuất hiện trong index sau bao lâu? | Đã xác định chính sách đồng bộ |
| Dung lượng và chi phí ghi tăng bao nhiêu? | Đã đo trên dữ liệu gần thực tế |
| Query có filter tenant/quyền truy cập không? | Điều kiện bảo vệ dữ liệu được giữ nguyên |
| Truy vấn có dùng đúng index và trả ít ứng viên không? | Đã xem execution plan và số hàng |
| p95/p99 và workload ghi có đạt mục tiêu không? | Có số liệu trước/sau cùng điều kiện |

## 17. Nguyên tắc ra quyết định

LIKE và full-text search không phải hai cách viết khác nhau của cùng một phép tìm kiếm. LIKE kiểm tra mẫu ký tự; full-text search phân tích văn bản thành token và áp dụng quy tắc ngôn ngữ. B-tree thường phù hợp với exact match và một số truy vấn prefix; wildcard ở đầu mẫu thường khiến B-tree không thể thu hẹp phạm vi. Full-text index phù hợp với tìm từ, cụm từ và xếp hạng liên quan; substring hoặc fuzzy search có thể cần trigram, ngram hoặc cơ chế riêng.

Hãy bắt đầu từ cách người dùng mong đợi kết quả, sau đó chọn cấu trúc chỉ mục phù hợp với DBMS và ngôn ngữ dữ liệu. Đo cả thời gian tìm kiếm, độ liên quan, dung lượng, chi phí ghi và độ trễ đồng bộ. Một giải pháp tốt phải trả về đúng loại kết quả với độ trễ đạt yêu cầu và duy trì được hiệu năng của workload cơ sở dữ liệu còn lại.
