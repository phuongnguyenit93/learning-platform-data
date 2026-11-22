# Tìm kiếm toàn văn và khác biệt với LIKE

Một trang bán hàng có ô tìm kiếm “tai nghe không dây”; hệ thống tài liệu cần tìm những bài chứa các khái niệm “SQL index”; một diễn đàn muốn tìm bài viết có từ “search” và sắp xếp theo mức độ liên quan. Ta có thể bắt đầu bằng **LIKE**, nhưng khi dữ liệu lớn và yêu cầu tìm kiếm phức tạp hơn, SQL thường cung cấp thêm các cơ chế **full-text search** (*tìm kiếm toàn văn*).

Hai cơ chế này không chỉ khác nhau về hiệu năng. Quan trọng hơn, chúng **trả lời những câu hỏi khác nhau**:

- **LIKE** hỏi: *Chuỗi ký tự này có khớp một mẫu ký tự hay không?*
- **Full-text search (FTS)** hỏi: *Tài liệu này chứa những từ/lexeme phù hợp với một biểu thức tìm kiếm sau khi tách và chuẩn hóa văn bản hay không?*

Ví dụ, từ khóa **SQL** có thể xuất hiện như một **chuỗi con** trong **PostgreSQL** hoặc **MySQL**. Với một phép LIKE kiểu **'%sql%'**, những tên này có thể cùng khớp. Nhưng với tìm kiếm toàn văn dùng tokenizer thông thường, **sql**, **postgresql** và **mysql** là **ba lexeme riêng**, nên truy vấn từ **sql** không tự động khớp hai tên hệ quản trị kia.

Đó là một khác biệt **ngữ nghĩa**, không phải lỗi của chỉ mục. Ngược lại, nếu cần tìm mã sản phẩm chứa chuỗi “AB-17” hoặc tìm dấu phần trăm trong mô tả, LIKE có thể phù hợp hơn FTS.

Bài **“Tìm kiếm toàn văn và khác biệt với LIKE”** thuộc chương **Dữ liệu mở rộng**, module **Database SQL**. Phần thực hành chính dùng **PostgreSQL 15 trở lên** với **tsvector**, **tsquery**, toán tử **@@**, **GIN index**, đánh giá relevance và **pg_trgm**. Phần cuối đối chiếu **MySQL FULLTEXT**, **SQL Server Full-Text Search**, **SQLite FTS5** và **Oracle Text**, đồng thời giải thích những điểm đặc biệt khi tìm kiếm **tiếng Việt**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả chính xác **LIKE**, **ILIKE**, ký tự đại diện **%** và **_**.
2. Giải thích tại sao LIKE không phải một hệ thống tìm kiếm theo từ, không có ranking tích hợp.
3. Mô tả pipeline FTS: **văn bản → token/lexeme → chỉ mục đảo → tsquery → kết quả/ranking**.
4. Dùng **to_tsvector**, **plainto_tsquery**, **phraseto_tsquery**, **websearch_to_tsquery** và **to_tsquery** trên PostgreSQL.
5. Dùng **@@** để tìm tài liệu theo AND, OR, NOT, cụm từ và tiền tố lexeme.
6. Tạo cột **tsvector generated stored**, cho tiêu đề trọng số cao hơn nội dung và đánh chỉ mục **GIN**.
7. Sắp xếp theo **ts_rank/ts_rank_cd** và tạo trích đoạn bằng **ts_headline**.
8. Phân biệt khả năng tìm theo từ với tìm **chuỗi con**, **prefix ký tự** hoặc **fuzzy/trigram**.
9. Nhận biết tác động của từ dừng, stemming, cấu hình ngôn ngữ và dấu tiếng Việt.
10. Thiết kế tìm kiếm có lọc **tenant**, quyền truy cập, trạng thái xuất bản và tham số an toàn.
11. Đọc EXPLAIN và chọn chiến lược chỉ mục phù hợp với đặc điểm truy vấn.
12. Chuyển khái niệm FTS sang các phương ngữ khác mà không nhầm cú pháp.

## 2. LIKE hoạt động như thế nào?

Trong SQL, **LIKE** so sánh một chuỗi với một **pattern**.

Hai wildcard phổ biến:

| Wildcard | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **%** | Khớp **0 hoặc nhiều** ký tự | 'SQL%' khớp chuỗi bắt đầu với SQL |
| **_** | Khớp **đúng một** ký tự | 'A_1' khớp 'AB1' nhưng không khớp 'A1' |

Ví dụ PostgreSQL:

~~~sql
SELECT
    'SQL tutorial' LIKE 'SQL%' AS starts_with_sql,
    'PostgreSQL' LIKE '%SQL%' AS contains_sql,
    'AB1' LIKE 'A_1' AS three_chars,
    'A1' LIKE 'A_1' AS only_two_chars;
~~~

Các kết quả theo thứ tự là **TRUE, TRUE, TRUE, FALSE** trong trường hợp so khớp ký tự như các chuỗi mẫu này.

### 2.1. LIKE có phân biệt hoa/thường?

Trong PostgreSQL, **LIKE** thông thường có thể phân biệt hoa/thường theo quy tắc so khớp và collation được dùng; **ILIKE** là cú pháp riêng của PostgreSQL để so khớp không phân biệt hoa/thường theo locale hiện hành:

~~~sql
SELECT
    'sql notes' LIKE '%SQL%' AS like_result,
    'sql notes' ILIKE '%SQL%' AS ilike_result;
~~~

Với những chuỗi ASCII này trong môi trường PostgreSQL thông dụng:

~~~text
like_result  = FALSE
ilike_result = TRUE
~~~

Không port **ILIKE** nguyên văn sang mọi hệ SQL. MySQL/SQL Server có thể dùng collation không phân biệt hoa/thường, hoặc cơ chế riêng tùy cấu hình; Oracle và SQLite cũng có quy tắc tương ứng. **Case-insensitive search** không phải một đặc tính độc nhất của FTS.

### 2.2. LIKE chỉ biết ký tự, không hiểu ranh giới từ

~~~sql
SELECT
    'PostgreSQL' ILIKE '%sql%' AS substring_match,
    'MySQL' ILIKE '%sql%' AS another_substring_match,
    'SQL' ILIKE '%sql%' AS whole_word_match;
~~~

Cả ba có thể khớp vì pattern chỉ yêu cầu có dãy ký tự “sql” ở đâu đó. LIKE không biết “SQL” là một từ độc lập hay phần cuối tên sản phẩm/công nghệ.

**Khi ứng dụng cần tìm một từ thay vì một chuỗi con, đây là lý do phải cân nhắc FTS.**

## 3. Escaping wildcard và NULL trong LIKE

Nếu người dùng thực sự tìm **ký tự phần trăm** hoặc **dấu gạch dưới**, không thể đưa chúng vào pattern như wildcard:

~~~sql
SELECT
    'Giảm 20%' LIKE '%!%%' ESCAPE '!' AS has_percent,
    'ma_sp_01' LIKE '%!_%' ESCAPE '!' AS has_underscore,
    'A!B' LIKE '%!!%' ESCAPE '!' AS has_bang;
~~~

Trong các pattern:

- **!%** nghĩa là ký tự **%** thật.
- **!_** nghĩa là ký tự **_** thật.
- **!!** nghĩa là ký tự **!** thật.
- **ESCAPE '!'** chọn dấu ! làm ký tự escape thay vì dựa vào quy tắc dấu backslash khác nhau theo môi trường.

**LIKE còn chịu tác động của NULL.**

~~~sql
SELECT
    NULL::TEXT LIKE '%sql%' AS null_left,
    'SQL' LIKE NULL::TEXT AS null_pattern;
~~~

Cả hai trả **NULL/UNKNOWN**, không phải FALSE. Khi lọc với **WHERE ... LIKE ...**, hàng có điều kiện UNKNOWN thường không được chọn.

### 3.1. Không nối trực tiếp input vào SQL

Câu lệnh nguy hiểm:

~~~text
sql = "SELECT ... WHERE title LIKE '%" + userInput + "%'"
~~~

có thể gây **SQL injection** nếu xây SQL bằng nối chuỗi thô. Cách đúng là dùng **bind parameter** cho pattern, đồng thời escape wildcard khi người dùng muốn tìm chuỗi **literal**, không phải nhập một pattern LIKE.

Ví dụ PostgreSQL prepared statement:

~~~sql
PREPARE demo_title_contains (TEXT) AS
SELECT title
FROM lab369_articles
WHERE title ILIKE '%' || $1 || '%'
ORDER BY title;
~~~

Đây là một **tham số SQL an toàn về mặt tách dữ liệu khỏi cú pháp truy vấn**, nhưng người dùng truyền **%** hoặc **_** vẫn có thể tạo hiệu ứng wildcard. Muốn so khớp literal, cần thêm bước escape theo đúng ESCAPE đã chọn hoặc xây pattern bằng hàm/ứng dụng có kiểm soát.

Không chạy câu PREPARE này trước khi tạo bảng **lab369_articles** ở phần thực hành bên dưới.

## 4. Khi LIKE bắt đầu không đủ

Những nhu cầu sau có thể vượt quá LIKE:

1. **Nhiều từ khóa:** “SQL indexes” có nghĩa cả hai từ, một trong hai, hay đúng thứ tự?
2. **Ngôn ngữ:** “running” và “run” có nên được coi là liên quan?
3. **Từ dừng:** các từ quá phổ biến như “the” có nên ảnh hưởng ranking?
4. **Ranking:** bài nào phù hợp hơn nếu nhiều bài cùng chứa từ khóa?
5. **Trọng số:** từ khóa trong **title** có quan trọng hơn trong body?
6. **Hiệu năng:** quét văn bản dài bằng wildcard giữa chuỗi trên hàng triệu bản ghi.
7. **Cụm từ:** “full text” xuất hiện cạnh nhau khác với “full ... text”.
8. **Tách từ tiếng Việt:** “điện thoại”, “cơ sở dữ liệu” không chỉ là các từ tiếng Anh tách theo khoảng trắng.
9. **Lỗi chính tả:** “postgress” có nên gợi ý “postgres”?
10. **Bảo mật:** người dùng chỉ được tìm trong tập tài liệu đã được cấp phép.

FTS giải quyết **một phần quan trọng** các nhu cầu này, nhưng không tự giải quyết tất cả. Ví dụ, PostgreSQL FTS mặc định **không phải một công cụ sửa chính tả hay tìm kiếm ngữ nghĩa bằng vector embeddings**; tìm fuzzy thường cần pg_trgm hoặc một hệ thống bổ sung.

## 5. Full-text search hoạt động theo pipeline nào?

Mô hình khái quát:

~~~text
  TÀI LIỆU ĐẦU VÀO
  "PostgreSQL full text search"
              |
              v
      Parser / tokenizer
              |
              v
      Token theo cấu hình
              |
              v
  Dictionary / normalization
  chữ thường, stop words, stemming
              |
              v
      Lexeme + vị trí
              |
              v
   TSVECTOR và GIN index
              |
       truy vấn TSQUERY
              |
              v
    @@ kiểm tra phù hợp
              |
              v
     Rank / highlight
~~~

**Token** là đơn vị văn bản mà bộ phân tích phát hiện. **Lexeme** là dạng được chuẩn hóa/dictionary xử lý để phục vụ tìm kiếm. Với ngôn ngữ có stemming, các từ biến thể có thể cùng dẫn về một lexeme. Với cấu hình đơn giản, lexeme có thể gần với token đã chuyển chữ thường.

### 5.1. Chỉ mục đảo là gì?

Thay vì mỗi lần tìm từ “SQL” phải đọc toàn bộ nội dung tài liệu, hệ thống có thể duy trì thông tin đại khái:

~~~text
"sql"       → tài liệu 1, 6, 7
"postgresql"→ tài liệu 2, 4, 12
"search"    → tài liệu 2, 5, 8, 11
"indexes"   → tài liệu 1, 7, 8
~~~

Đây là minh họa logic **inverted index (chỉ mục đảo)** cho tập dữ liệu của bài; không phải định dạng lưu trữ nội bộ chính xác của GIN.

Tìm “sql” qua chỉ mục có thể bắt đầu từ những tài liệu chứa lexeme “sql”. Nhưng việc lọc trạng thái, tenant, ranking và kiểm tra lại điều kiện vẫn quan trọng; không nên suy luận GIN luôn trả kết quả theo độ liên quan đã sắp sẵn.

## 6. Tạo dữ liệu thực hành PostgreSQL

Chúng ta tạo **12 tài liệu** thuộc **hai tenant**. Có bài viết tiếng Anh về SQL/PostgreSQL/MySQL, hai tài liệu tiếng Việt và một bài **chưa xuất bản**. Điểm cần quan sát là sự khác nhau giữa từ **SQL** và chuỗi con **SQL** nằm trong các tên sản phẩm.

### 6.1. Bảng và cột tsvector

~~~sql
CREATE TEMP TABLE lab369_articles (
    article_id    INTEGER PRIMARY KEY,
    tenant_id     INTEGER NOT NULL,
    title         TEXT NOT NULL,
    body          TEXT,
    published     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    DATE NOT NULL,
    search_doc    TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'pg_catalog.simple'::REGCONFIG,
                COALESCE(title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'pg_catalog.simple'::REGCONFIG,
                COALESCE(body, '')
            ),
            'B'
        )
    ) STORED
);
~~~

Giải thích:

- **search_doc** là cột **tsvector generated stored**, được tính từ title/body khi dữ liệu hàng thay đổi.
- **to_tsvector** biến nội dung thành lexeme có vị trí.
- Cấu hình **pg_catalog.simple** dùng dictionary đơn giản, không stemming theo tiếng Anh.
- **setweight(...,'A')** gán trọng số A cho từ trong title; **'B'** cho body.
- Toán tử **||** ở đây nối **tsvector**, không phải chỉ nối chuỗi text thông thường.
- **COALESCE(body,'')** tránh trường hợp body NULL làm mất khả năng tạo vector từ tiêu đề.
- Cấu hình text search được truyền **tường minh**, thay vì phụ thuộc vào default_text_search_config thay đổi giữa các môi trường.

PostgreSQL hỗ trợ stored generated columns ở các phiên bản hiện đại. Biểu thức generated phải thỏa các quy tắc tính xác định/immutable của engine; việc chỉ định regconfig rõ ràng giúp chọn đúng biến thể **to_tsvector(regconfig,text)** thích hợp.

### 6.2. Nạp dữ liệu

~~~sql
INSERT INTO lab369_articles
    (article_id, tenant_id, title, body, published, created_at)
VALUES
    (1, 10,
     'SQL query optimization',
     'Indexes help SQL query performance',
     TRUE, DATE '2026-01-01'),
    (2, 10,
     'PostgreSQL full text search',
     'PostgreSQL uses tsvector and tsquery for search',
     TRUE, DATE '2026-01-02'),
    (3, 10,
     'LIKE pattern matching',
     'LIKE matches character patterns with percent and underscore',
     TRUE, DATE '2026-01-03'),
    (4, 10,
     'Java database access',
     'Java connects to PostgreSQL using JDBC',
     TRUE, DATE '2026-01-04'),
    (5, 10,
     'Search engine ranking',
     'Search ranking and relevance use document terms',
     TRUE, DATE '2026-01-05'),
    (6, 10,
     'Notebook for SQL',
     NULL,
     FALSE, DATE '2026-01-06'),
    (7, 20,
     'SQL indexes',
     'Btree and GIN indexes support different queries',
     TRUE, DATE '2026-02-01'),
    (8, 20,
     'MySQL text search',
     'MySQL offers FULLTEXT indexes and MATCH AGAINST',
     TRUE, DATE '2026-02-02'),
    (9, 20,
     'Coffee in Viet Nam',
     'Cà phê và cà phê sữa được nhiều người yêu thích',
     TRUE, DATE '2026-02-03'),
    (10, 20,
     'Phone review',
     'Điện thoại và tai nghe Bluetooth',
     TRUE, DATE '2026-02-04'),
    (11, 20,
     'Searchable documents',
     'Document search should respect tenant access',
     TRUE, DATE '2026-02-05'),
    (12, 20,
     'PostgreSQL JSONB basics',
     'JSONB indexing with GIN supports containment',
     TRUE, DATE '2026-02-06');
~~~

Tự đếm:

~~~sql
SELECT
    COUNT(*) AS articles,
    COUNT(*) FILTER (WHERE published) AS published_articles,
    COUNT(*) FILTER (WHERE tenant_id = 10) AS tenant10_articles,
    COUNT(*) FILTER (WHERE tenant_id = 20) AS tenant20_articles
FROM lab369_articles;
~~~

| articles | published_articles | tenant10_articles | tenant20_articles |
| ---: | ---: | ---: | ---: |
| 12 | 11 | 6 | 6 |

**Bảng TEMP chỉ sống trong phiên PostgreSQL hiện tại**. Không mở connection mới giữa các phần nếu muốn tiếp tục dùng cùng bộ dữ liệu.

## 7. Thí nghiệm quan trọng: ILIKE '%sql%' so với FTS 'sql'

### 7.1. LIKE tìm chuỗi con

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE title ILIKE '%sql%'
ORDER BY article_id;
~~~

Kết quả mong đợi:

| article_id | title | Vì sao khớp? |
| ---: | --- | --- |
| 1 | SQL query optimization | Title chứa SQL độc lập |
| 2 | PostgreSQL full text search | Postgre**SQL** có chuỗi con sql |
| 6 | Notebook for SQL | Title chứa SQL độc lập |
| 7 | SQL indexes | Title chứa SQL độc lập |
| 8 | MySQL text search | My**SQL** có chuỗi con sql |
| 12 | PostgreSQL JSONB basics | Postgre**SQL** có chuỗi con sql |

**Sáu hàng**, trong đó cả tên PostgreSQL và MySQL đều khớp vì ILIKE xử lý chuỗi ký tự.

### 7.2. Full-text search tìm lexeme

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ plainto_tsquery('pg_catalog.simple', 'sql')
ORDER BY article_id;
~~~

Kết quả mong đợi:

| article_id | title |
| ---: | --- |
| 1 | SQL query optimization |
| 6 | Notebook for SQL |
| 7 | SQL indexes |

**Ba hàng**. Từ “SQL” là lexeme riêng trong các tài liệu ấy. “PostgreSQL” thường được phân tích thành lexeme “postgresql”, “MySQL” thành “mysql”, nên chúng **không tự khớp** truy vấn chỉ tìm lexeme “sql”.

Lưu ý bài 6 **chưa xuất bản** và bài 7 thuộc **tenant 20**. Ở đây ta cố ý chưa lọc để quan sát ngữ nghĩa; trong hệ thật phải kết hợp điều kiện quyền và published như các phần sau.

### 7.3. Hai câu SQL có ý nghĩa khác nhau

~~~text
ILIKE '%sql%'
    → tìm vị trí chuỗi ký tự "sql" trong title

search_doc @@ plainto_tsquery('simple','sql')
    → tìm tài liệu có lexeme "sql" trong title/body
~~~

**FTS không phải LIKE “được tăng tốc”**. Nó là một cơ chế lập chỉ mục và so khớp với ngữ nghĩa khác.

## 8. Hiểu TSVECTOR trong PostgreSQL

Xem trực tiếp kết quả phân tích văn bản:

~~~sql
SELECT to_tsvector(
    'pg_catalog.simple',
    'SQL query optimization and PostgreSQL'
) AS lexemes;
~~~

Kết quả là một **tsvector**, chứa các lexeme chuẩn hóa và thông tin vị trí. Có thể thấy dạng text gần với:

~~~text
'and':4 'optimization':3 'postgresql':5 'query':2 'sql':1
~~~

Thứ tự hiển thị lexeme trong tsvector không nhất thiết là thứ tự từ xuất hiện trong câu; **vị trí** bên cạnh lexeme mới giúp diễn đạt vị trí gốc cho những toán tử tìm cụm từ. Định dạng in có thể khác theo phiên bản và cấu hình.

### 8.1. Tại sao pg_catalog.simple?

Cấu hình **simple** thường:

- Chuẩn hóa chữ hoa/thường trong những token được hỗ trợ.
- Không dùng stemming tiếng Anh như cấu hình **english**.
- Không bỏ những stop words tiếng Anh phổ biến theo cùng cách cấu hình english.

Điều này khiến ví dụ “sql” dễ đối chiếu với LIKE, nhưng không có nghĩa **simple là cấu hình tốt nhất cho mọi ngôn ngữ**.

### 8.2. Xem vector đã tạo của một bài

~~~sql
SELECT article_id, title, search_doc
FROM lab369_articles
WHERE article_id IN (1, 2, 6)
ORDER BY article_id;
~~~

Do title có trọng số A và body có trọng số B, PostgreSQL có thể in các ký hiệu như **:1A** hay **:5B** để chỉ vị trí/weight. Với bài 6 body NULL, COALESCE giúp **vector vẫn chứa các từ trong title**.

### 8.3. TSVECTOR không phải bản sao nguyên văn

Từ thông tin lexeme đã chuẩn hóa **không thể luôn tái tạo chính xác câu gốc** với dấu câu, chữ hoa/thường hoặc vị trí khoảng trắng. Vì vậy, lưu **title/body gốc** để hiển thị, còn search_doc dùng để so khớp và xếp hạng.

## 9. Hiểu TSQUERY và toán tử @@

**tsquery** mô tả yêu cầu tìm kiếm dưới dạng lexeme và các toán tử logic. **@@** trả TRUE khi một tsvector phù hợp với tsquery:

~~~sql
SELECT
    to_tsvector('pg_catalog.simple', 'SQL query optimization')
    @@
    to_tsquery('pg_catalog.simple', 'sql & query')
    AS matched;
~~~

Kết quả là **TRUE**.

### 9.1. Các cách tạo tsquery

| Hàm | Input mẫu | Ý nghĩa điển hình |
| --- | --- | --- |
| **to_tsquery** | 'sql & indexes' | Tự viết biểu thức tsquery có toán tử |
| **plainto_tsquery** | 'sql indexes' | Biến văn bản thường thành các lexeme kết hợp AND |
| **phraseto_tsquery** | 'full text search' | Cố gắng tìm cụm từ theo thứ tự/vị trí |
| **websearch_to_tsquery** | '"full text" OR mysql' | Chấp nhận kiểu cú pháp web search thân thiện hơn |

Các hàm đều phụ thuộc **text search configuration** được chọn. Khi tìm trên vector tạo bằng **simple**, ví dụ của bài chủ yếu tạo tsquery bằng **simple** tương ứng.

### 9.2. plainto_tsquery: mặc định kết hợp các từ

~~~sql
SELECT plainto_tsquery(
    'pg_catalog.simple',
    'sql indexes'
) AS query_ast;
~~~

Với cấu hình simple, kết quả thường là:

~~~text
'sql' & 'indexes'
~~~

Đó là **AND**, không phải tìm tài liệu có bất kỳ từ nào.

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ plainto_tsquery('pg_catalog.simple', 'sql indexes')
ORDER BY article_id;
~~~

Hai tài liệu phù hợp là **article_id 1** và **7**, vì cả hai có lexeme **sql** và **indexes**. Hãy chú ý: cấu hình simple không stemming “indexes” thành “index” theo tiếng Anh.

## 10. Các toán tử của to_tsquery

### 10.1. AND: dấu &

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ to_tsquery(
    'pg_catalog.simple',
    'postgresql & search'
)
ORDER BY article_id;
~~~

Với dữ liệu mẫu, **article_id 2** thỏa vì có cả “postgresql” lẫn “search”.

### 10.2. OR: dấu |

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ to_tsquery(
    'pg_catalog.simple',
    'sql | mysql'
)
ORDER BY article_id;
~~~

Kết quả mong đợi gồm **1, 6, 7, 8**: ba tài liệu có lexeme “sql” và tài liệu MySQL có lexeme “mysql”.

### 10.3. NOT: dấu !

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ to_tsquery(
    'pg_catalog.simple',
    'sql & !indexes'
)
ORDER BY article_id;
~~~

Với dữ liệu mẫu, chỉ còn **article_id 6**: tiêu đề có SQL, nhưng không có lexeme indexes. Nó chưa xuất bản, nên trong báo cáo người dùng phải có thêm điều kiện published.

**Không dùng NOT riêng làm bộ lọc an ninh hoặc chiến lược tìm toàn bộ dữ liệu lớn.** Truy vấn phủ định thường có giới hạn tối ưu hóa và ngữ nghĩa khác tìm một lexeme tích cực; hãy kết hợp quyền/tenant bằng điều kiện đáng tin.

### 10.4. Phrase: toán tử <->

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ to_tsquery(
    'pg_catalog.simple',
    'full <-> text'
)
ORDER BY article_id;
~~~

Với bộ dữ liệu này, **article_id 2** có cụm “full text” liên tiếp trong title. Toán tử **<->** diễn đạt vị trí kề nhau trong chuỗi lexeme.

### 10.5. Prefix lexeme: :*

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ to_tsquery(
    'pg_catalog.simple',
    'postgre:*'
)
ORDER BY article_id;
~~~

Kết quả mong đợi: **2, 4, 12**, do lexeme “postgresql” bắt đầu bằng chuỗi **postgre**.

**Đây là tiền tố lexeme**, không phải ký tự đại diện tùy ý giữa một từ như **'%gre%'** của LIKE. Cú pháp **:* ** không biến FTS thành công cụ tìm mọi substring bên trong token.

### 10.6. Tính ưu tiên toán tử

Với điều kiện phức tạp, luôn dùng dấu ngoặc khi cần:

~~~sql
SELECT to_tsquery(
    'pg_catalog.simple',
    '(sql | mysql) & indexes'
);
~~~

Giá trị biểu thức khác với:

~~~sql
SELECT to_tsquery(
    'pg_catalog.simple',
    'sql | (mysql & indexes)'
);
~~~

Dấu ngoặc làm hợp đồng tìm kiếm rõ ràng, tránh phụ thuộc vào việc người đọc nhớ thứ tự ưu tiên của parser.

## 11. phraseto_tsquery và websearch_to_tsquery

### 11.1. Tìm cụm từ được nhập như văn bản

~~~sql
SELECT
    phraseto_tsquery('pg_catalog.simple', 'full text search')
        AS phrase_query;
~~~

Với cấu hình simple và chuỗi này, truy vấn cần các lexeme theo thứ tự/cạnh nhau tương ứng. Thử:

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ phraseto_tsquery(
    'pg_catalog.simple',
    'full text search'
)
ORDER BY article_id;
~~~

Tài liệu **2** có title “PostgreSQL full text search” nên thỏa.

**Lưu ý:** với một cấu hình loại bỏ stop words, khoảng cách lexeme trong phrase query có thể khác đơn giản “từ nào cũng cách một vị trí”; không đoán cách parser xử lý nếu đang sử dụng english hoặc dictionary tùy biến.

### 11.2. Cú pháp tìm kiếm kiểu web

~~~sql
SELECT websearch_to_tsquery(
    'pg_catalog.simple',
    '"full text" OR mysql -jdbc'
) AS web_query;
~~~

Trong PostgreSQL, websearch_to_tsquery nhận một số cấu trúc thân thiện với người dùng:

- Từ khóa thông thường thường được ghép với **AND**.
- Cụm trong dấu nháy kép có ý nghĩa tìm phrase.
- Từ **OR** viết hoa biểu diễn phép OR.
- Dấu trừ trước từ khóa biểu diễn phủ định.

Hàm này thích hợp hơn việc chuyển input của người dùng trực tiếp vào **to_tsquery**, vốn yêu cầu cú pháp tsquery chuyên biệt như **&**, **|**, **!** và có thể báo lỗi với đầu vào không hợp lệ.

### 11.3. Không giả định websearch là trình phân tích ngôn ngữ tự nhiên

websearch_to_tsquery không tự hiểu rằng:

~~~text
"cơ sở dữ liệu" ≈ "database" ≈ "DBMS"
~~~

Nó tạo truy vấn lexeme theo text search configuration, không phải hệ thống embeddings hoặc bộ máy trả lời bằng ngữ nghĩa. Muốn hỗ trợ synonym, đa ngôn ngữ hoặc semantic retrieval phải thiết kế thêm từ điển, query expansion hay công nghệ khác.

## 12. English stemming và stop words

Kết quả tìm kiếm phụ thuộc cấu hình ngôn ngữ.

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'the running indexes'
    ) AS simple_vector,
    to_tsvector(
        'pg_catalog.english',
        'the running indexes'
    ) AS english_vector;
~~~

Với **simple**, các token thường được giữ dưới dạng chữ thường, không stem tiếng Anh. Với **english**, hệ có thể loại stop word như “the” và đưa “running”/“indexes” về các lexeme đã stem theo dictionary tiếng Anh.

### 12.1. Vì sao chọn cùng cấu hình ở cả hai phía?

Nếu cột search_doc được tạo bằng **simple**, nhưng query được xử lý bằng **english**, truy vấn “indexes” có thể được stem thành một lexeme khác với “indexes” trong vector. Khi đó dữ liệu có từ hiển nhiên nhưng **không khớp**.

~~~sql
-- Cấu hình query khớp với cấu hình lúc tạo vector.
SELECT article_id
FROM lab369_articles
WHERE search_doc @@ plainto_tsquery(
    'pg_catalog.simple',
    'indexes'
);
~~~

**Quy tắc:** hãy dùng cấu hình tương ứng ở lúc index và lúc query, trừ khi có lý do và thiết kế nhiều cấu hình rõ ràng.

### 12.2. Stop words có thể tạo query rỗng

Nếu người dùng chỉ nhập các từ bị loại bởi dictionary, tsquery sau chuẩn hóa có thể không còn lexeme hữu ích. PostgreSQL có thể kiểm tra bằng **numnode(tsquery)**:

~~~sql
SELECT
    plainto_tsquery('pg_catalog.english', 'the and')
        AS query_value,
    numnode(
        plainto_tsquery('pg_catalog.english', 'the and')
    ) AS query_nodes;
~~~

Với cấu hình english mặc định, những từ dừng như vậy thường tạo tsquery không có node hữu ích. Ứng dụng nên quyết định trả **không kết quả**, thông báo “hãy nhập từ khóa rõ hơn”, hoặc một chiến lược riêng — **không vô tình trả tất cả tài liệu** khi query rỗng.

## 13. Tạo GIN index cho full-text search

Đây là bước quan trọng khi số tài liệu lớn:

~~~sql
CREATE INDEX lab369_search_doc_gin
ON lab369_articles
USING GIN (search_doc);

ANALYZE lab369_articles;
~~~

**GIN (Generalized Inverted Index)** là lựa chọn thông dụng cho cột tsvector trên PostgreSQL. Nó giúp tra các lexeme xuất hiện trong tài liệu mà không phải quét và tách toàn bộ văn bản mỗi lần.

### 13.1. GIN không thay ranking

GIN có nhiệm vụ giúp **tìm candidate phù hợp**. Nếu truy vấn:

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ plainto_tsquery('pg_catalog.simple', 'search');
~~~

thì kết quả có thể được lấy qua index. Nhưng **GIN không tự quyết định thứ tự bài nào hay hơn**; ranking cần biểu thức xếp hạng như ts_rank hoặc ts_rank_cd và ORDER BY.

### 13.2. GIN có chi phí ghi

Khi INSERT/UPDATE/DELETE tài liệu, PostgreSQL phải duy trì dữ liệu cột generated và chỉ mục tương ứng. Với hệ ghi rất nhiều, cần cân đối:

- Chi phí tăng của insert/update.
- Kích thước index.
- Khối lượng VACUUM/maintenance.
- Tần suất truy vấn tìm kiếm và yêu cầu độ mới.
- Độ dài trường được index.

**Có chỉ mục không có nghĩa miễn phí.** Nó đánh đổi một phần chi phí ghi và dung lượng để cải thiện truy vấn đọc phù hợp.

### 13.3. Vì sao vẫn có Seq Scan?

Với **12 hàng** của bài, PostgreSQL hoàn toàn có thể chọn **Seq Scan** thay vì Index Scan/Bitmap Index Scan vì đọc một bảng rất nhỏ là rẻ hơn dùng chỉ mục.

Không được kết luận GIN “hỏng” chỉ vì EXPLAIN trên bộ dữ liệu nhỏ không hiển thị sử dụng index.

## 14. Ranking: bài nào liên quan hơn?

Một điều kiện **@@** chỉ kiểm tra phù hợp hay không. Khi nhiều tài liệu cùng khớp, cần sắp xếp theo **điểm relevance**.

PostgreSQL có **ts_rank** và **ts_rank_cd**:

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'search'
    ) AS tsq
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(a.search_doc, q.tsq) AS relevance
FROM lab369_articles AS a
CROSS JOIN q
WHERE a.search_doc @@ q.tsq
ORDER BY
    relevance DESC,
    a.article_id;
~~~

Với từ “search”, nhiều tài liệu chứa lexeme này ở title/body. Tài liệu có từ khóa xuất hiện trong **title trọng số A** và body trọng số B có thể được cho điểm khác. **Không nên hardcode thứ tự cụ thể** như một quy tắc toán học bất biến khi chưa xác định hàm rank, trọng số, cấu hình và dữ liệu.

### 14.1. ts_rank khác ts_rank_cd thế nào?

Hai hàm cung cấp phương pháp tính điểm khác nhau. **ts_rank_cd** sử dụng phương pháp *cover density*, tận dụng thông tin về vị trí và độ gần giữa các lexeme trong những trường hợp liên quan. **ts_rank** cũng dùng tần suất/trọng số theo thuật toán của nó.

Không có một hàm nào mặc định “đo đúng ngữ nghĩa con người”. Ranking là heuristic; cần kiểm thử bằng tập truy vấn thực tế của người dùng.

### 14.2. Trọng số A/B/C/D

Cột search_doc của bài được tạo bằng:

~~~sql
setweight(to_tsvector(...title...), 'A')
||
setweight(to_tsvector(...body...), 'B')
~~~

Các ký hiệu A/B là nhãn trọng số lưu ở lexeme; mức ảnh hưởng thực tế còn phụ thuộc **mảng weights** của hàm rank. PostgreSQL có thể nhận một mảng trọng số tường minh theo thứ tự **D, C, B, A**:

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'search'
    ) AS tsq
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(
        ARRAY[0.05, 0.10, 0.30, 1.00]::REAL[],
        a.search_doc,
        q.tsq
    ) AS relevance
FROM lab369_articles AS a
CROSS JOIN q
WHERE a.search_doc @@ q.tsq
ORDER BY relevance DESC, a.article_id;
~~~

Ở ví dụ này **A** quan trọng hơn **B**. Không cần dùng cả C/D nếu không gán chúng trong vector, nhưng biết thứ tự mảng giúp tránh gán ngược khiến body quan trọng hơn title ngoài ý muốn.

### 14.3. Rank không phải xác suất

Điểm relevance không mặc định là xác suất từ 0 đến 1 và không thể so sánh tùy tiện giữa hai loại truy vấn, hai hàm rank hoặc hai cấu hình khác nhau. Đừng diễn giải **score = 0.8** thành “tài liệu phù hợp 80%” nếu không có hiệu chuẩn riêng.

## 15. Highlight kết quả bằng ts_headline

Người dùng thường muốn xem một trích đoạn có từ khóa được đánh dấu.

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'search'
    ) AS tsq
)
SELECT
    a.article_id,
    a.title,
    ts_headline(
        'pg_catalog.simple',
        COALESCE(a.body, ''),
        q.tsq,
        'StartSel=[[, StopSel=]], MaxWords=15, MinWords=3'
    ) AS snippet
FROM lab369_articles AS a
CROSS JOIN q
WHERE a.search_doc @@ q.tsq
ORDER BY a.article_id;
~~~

Ở đây **StartSel=[[** và **StopSel=]]** là ký hiệu đơn giản để người đọc dễ thấy vị trí match. Trong ứng dụng web, có thể dùng thẻ HTML như mark, nhưng phải có chiến lược **HTML escaping** đáng tin để không đưa nội dung tài liệu thiếu tin cậy thành XSS.

### 15.1. Highlight không làm thay điều kiện tìm kiếm

Điều kiện **@@** quyết định tài liệu có khớp hay không; **ts_headline** chỉ giúp hiển thị những phần liên quan. Một tài liệu khớp vì lexeme trong **title** nhưng không có trong **body** vẫn có thể tạo trích đoạn body không được đánh dấu gì.

### 15.2. Kết quả snippet không phải bản gốc

Highlight có thể rút gọn văn bản, thêm marker hoặc cắt theo quy tắc. Không lưu snippet đã highlight ngược vào nội dung bài gốc như thể nó là bản văn nguyên thủy.

## 16. Lọc tenant và trạng thái xuất bản

Trong hệ thật, **tìm kiếm không được bỏ qua quyền xem dữ liệu**.

Với dữ liệu mẫu:

- Tenant 10 có bài **1–6**.
- Tenant 20 có bài **7–12**.
- Bài **6** chưa xuất bản.

Một truy vấn tìm từ **sql** cho tenant 10:

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'sql'
    ) AS tsq
)
SELECT
    a.article_id,
    a.title
FROM lab369_articles AS a
CROSS JOIN q
WHERE a.tenant_id = 10
  AND a.published IS TRUE
  AND a.search_doc @@ q.tsq
ORDER BY a.article_id;
~~~

Kết quả chỉ là **article_id 1**:

- Article 1: có sql, đã xuất bản, thuộc tenant 10.
- Article 6: có sql nhưng **chưa xuất bản**.
- Article 7: có sql, đã xuất bản nhưng thuộc **tenant 20**.

### 16.1. Tại sao không chỉ tin tenant_id từ request?

Nếu user có thể tự truyền **tenant_id = 20** và server không xác minh quyền, điều kiện WHERE trên không còn là ranh giới bảo mật đáng tin.

Ứng dụng cần lấy tenant của người dùng từ **ngữ cảnh xác thực đã kiểm chứng**, hoặc dùng chính sách **Row-Level Security (RLS)**/phân quyền phù hợp ở database. Không cấp quyền SELECT trực tiếp quá rộng lên bảng chứa nhiều tenant nếu không có cơ chế bảo vệ thích hợp.

### 16.2. Ranking cũng không được rò rỉ tài liệu bị cấm

Khi lấy điểm, số kết quả, gợi ý từ khóa hay snippet, chỉ nên dựa trên **tập tài liệu được phép truy cập**. Một ô “có 5 bài phù hợp” tính trên cả dữ liệu tenant khác có thể làm lộ thông tin ngay cả khi cuối cùng chỉ hiển thị những bài được cấp quyền.

### 16.3. Index không thay quyền

GIN giúp tìm từ nhanh; nó **không xác thực người dùng, không kiểm tra tenant và không tự hạn chế published**. Các điều kiện quyền vẫn là phần bắt buộc của truy vấn hoặc chính sách database.

## 17. Dùng parameter an toàn khi tìm toàn văn

Không đưa input thô trực tiếp vào một đoạn SQL tự ghép:

~~~text
sql = "SELECT ... WHERE search_doc @@ to_tsquery('simple','"
      + userInput + "')"
~~~

Điều này có thể gây SQL injection, lỗi nháy và khó kiểm soát ngữ nghĩa parser.

Một prepared statement PostgreSQL phù hợp:

~~~sql
PREPARE lab369_search (TEXT, INTEGER) AS
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        $1
    ) AS tsq
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(a.search_doc, q.tsq) AS relevance
FROM lab369_articles AS a
CROSS JOIN q
WHERE a.tenant_id = $2
  AND a.published IS TRUE
  AND numnode(q.tsq) > 0
  AND a.search_doc @@ q.tsq
ORDER BY relevance DESC, a.article_id
LIMIT 20;

EXECUTE lab369_search('sql', 10);

DEALLOCATE lab369_search;
~~~

- **$1** là text query do caller bind.
- **$2** là tenant_id đã được server xác thực trong ứng dụng thật.
- **websearch_to_tsquery** xử lý input thành cú pháp tìm kiếm kiểu web, không đòi người dùng tự viết dấu & và |.
- **numnode(q.tsq) > 0** tránh coi query không còn lexeme hữu ích như một yêu cầu trả toàn bộ tài liệu.
- **ORDER BY relevance DESC, article_id** tạo một thứ tự ổn định hơn cho các kết quả có cùng điểm.
- **LIMIT 20** kiểm soát số hàng trả cho một trang.

### 17.1. Trong JDBC

Ở Java, SQL thường dùng placeholder **?** của **PreparedStatement**, rồi setString và setInt; không chèn các chuỗi đã escape bằng nối text để giả lập bind.

Ví dụ khung:

~~~java
String sql = """
    WITH q AS (
      SELECT websearch_to_tsquery('pg_catalog.simple', ?) AS tsq
    )
    SELECT a.article_id, a.title,
           ts_rank_cd(a.search_doc, q.tsq) AS score
    FROM lab369_articles AS a
    CROSS JOIN q
    WHERE a.tenant_id = ?
      AND a.published IS TRUE
      AND numnode(q.tsq) > 0
      AND a.search_doc @@ q.tsq
    ORDER BY score DESC, a.article_id
    LIMIT 20
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, searchText);
    ps.setInt(2, authorizedTenantId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("article_id"));
        }
    }
}
~~~

Đoạn Java giả định biến **connection**, **searchText** và **authorizedTenantId** đã tồn tại, Java hỗ trợ text blocks và có import JDBC thích hợp. Tài liệu mô tả cách sử dụng, không phải chương trình Java hoàn chỉnh tự chạy.

## 18. Vietnamese full-text search: những lưu ý đặc biệt

Tiếng Việt đặt ra vấn đề quan trọng: **một từ về ngữ nghĩa có thể gồm nhiều âm tiết cách nhau bởi khoảng trắng**.

Ví dụ:

~~~text
điện thoại
cơ sở dữ liệu
trí tuệ nhân tạo
máy học
~~~

Nếu tokenizer mặc định tách theo các đơn vị chữ dựa trên khoảng trắng/dấu câu, kết quả có thể là nhiều lexeme riêng như **điện** và **thoại**, thay vì một đơn vị từ ghép mang ý nghĩa “điện thoại”.

### 18.1. Thử simple với nội dung tiếng Việt

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'Điện thoại và tai nghe Bluetooth'
    ) AS vi_vector;
~~~

PostgreSQL có thể phân tích thành những lexeme riêng dựa theo parser/dictionary, nhưng **simple không phải một Vietnamese word segmenter/lemmatizer chuyên dụng**.

Vì thế:

- Tìm “điện thoại” bằng AND có thể khớp những tài liệu chứa **điện** và **thoại** ở vị trí không liên tiếp.
- Dùng **phraseto_tsquery** buộc thứ tự/độ gần theo token, nhưng vẫn không tự hiểu mọi cụm từ tiếng Việt như một khái niệm.
- Tìm “máy tính” khác tìm “máy ảnh”; AND quá rộng có thể tạo false positives nếu từ xuất hiện ở những ngữ cảnh khác nhau.

### 18.2. Dấu tiếng Việt

Hai chuỗi:

~~~text
cà phê
ca phe
~~~

không nên mặc định khớp giống nhau dưới mọi cấu hình. PostgreSQL **simple** không tự bảo đảm tìm kiếm bỏ dấu tiếng Việt. Collation, normalization và dictionary sẽ quyết định hành vi tương ứng, không phải chỉ việc có GIN index.

### 18.3. Extension unaccent

PostgreSQL có extension **unaccent** có thể được dùng trong một text-search dictionary pipeline hoặc bước chuẩn hóa phù hợp:

~~~sql
-- Tùy chọn, cần quyền cài extension trên database.
CREATE EXTENSION IF NOT EXISTS unaccent;

SELECT unaccent('Cà phê sữa') AS folded_text;
~~~

Kết quả thường là **Ca phe sua** theo mapping của extension. Nhưng cần phân biệt:

- **unaccent(text)** là một bước xử lý văn bản, không tự biến mọi câu truy vấn thành full-text search.
- Nếu vector index được tạo trên **cấu hình có dấu** mà query được biến thành **không dấu**, có thể không khớp; cần **cùng pipeline chuẩn hóa ở index và query**.
- Việc gọi **unaccent** trực tiếp trong biểu thức **generated stored** không mặc định hợp lệ như các hàm immutable, vì đặc tính volatility và dictionary của extension; không tùy tiện đánh dấu một wrapper là IMMUTABLE để lách quy tắc khi từ điển có thể thay đổi.
- Cài extension hoặc sửa cấu hình text search cần quyền và quy trình của database, không phải thao tác mặc định cho mọi user.

### 18.4. Một pipeline tiếng Việt nghiêm túc

Với yêu cầu production, có thể cần:

1. Chuẩn hóa Unicode nhất quán.
2. Quyết định **có giữ dấu hay cho phép không dấu**, và có lưu cả hai dạng hay không.
3. Tokenization/word segmentation tiếng Việt phù hợp.
4. Dictionary từ đồng nghĩa và từ khóa chuyên ngành theo nhu cầu.
5. Cập nhật search index khi nội dung thay đổi.
6. Kiểm thử bằng truy vấn thật: “điện thoại”, “dien thoai”, “tai nghe”, lỗi gõ, chữ viết tắt.
7. Đo precision/recall và độ trễ thay vì chỉ đếm số bài trả về.

**Không tuyên bố FTS của PostgreSQL mặc định hiểu tiếng Việt ngang các công cụ search chuyên dụng.** Cần chọn phân tích văn bản theo ngôn ngữ và nghiệp vụ cụ thể.

## 19. Full-text search không phải tìm kiếm fuzzy

FTS chuẩn hóa lexeme, nhưng nếu người dùng gõ:

~~~text
PostgreSQ
postgress
mysssql
~~~

FTS không mặc định sửa mọi lỗi chính tả. **Prefix query** như postgre:* có thể giúp trường hợp thiếu phần cuối, nhưng không giải quyết các lỗi gõ nằm ở giữa từ hay đảo ký tự.

Một công cụ bổ sung trên PostgreSQL là **pg_trgm**, cung cấp khái niệm **trigram** (chuỗi ba ký tự) và các phép đo tương tự.

### 19.1. Cài pg_trgm nếu có quyền

~~~sql
-- Tùy chọn trên database học tập; có thể cần quyền phù hợp.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

### 19.2. Trigram hỗ trợ ILIKE '%...%'

~~~sql
CREATE INDEX lab369_title_trgm_gin
ON lab369_articles
USING GIN (title gin_trgm_ops);
~~~

Với index phù hợp, PostgreSQL có thể tăng tốc những truy vấn **LIKE/ILIKE chứa wildcard ở đầu** mà B-tree thông thường khó hỗ trợ:

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE title ILIKE '%sql%'
ORDER BY article_id;
~~~

Tuy nhiên, hiệu quả phụ thuộc pattern, số trigram có thể trích, kích thước tập dữ liệu và planner. Pattern quá ngắn hoặc không chứa đủ trigram phân biệt có thể không hưởng lợi đáng kể.

### 19.3. Similarity/fuzzy

~~~sql
SELECT
    article_id,
    title,
    similarity(title, 'PostgreSQ') AS score
FROM lab369_articles
ORDER BY score DESC, article_id
LIMIT 5;
~~~

**similarity** là độ tương tự dựa trên trigram, khác **ts_rank_cd** của FTS. Giá trị và threshold phải được thử nghiệm trên dữ liệu thật.

Có toán tử so sánh similarity như **%** trong pg_trgm, nhưng đừng nhầm nó với wildcard **% của LIKE**: cùng ký hiệu, **ngữ cảnh và ý nghĩa hoàn toàn khác**.

## 20. Ba kiểu tìm kiếm hay bị nhầm

| Yêu cầu | Cơ chế gợi ý | Lý do |
| --- | --- | --- |
| Mã sản phẩm bắt đầu bằng 'AB' | LIKE 'AB%' | Prefix **ký tự** rõ ràng |
| Một cột chứa chính xác một phần mã '%20' | LIKE với ESCAPE hoặc hàm chuỗi | Cần so khớp **literal substring** |
| Bài viết có từ “SQL” | FTS với lexeme sql | Cần **từ/token** |
| Bài có cả “SQL” và “indexes” | FTS AND | Truy vấn nhiều lexeme |
| Bài có cụm “full text” theo thứ tự | FTS phrase | Quan hệ vị trí giữa lexeme |
| Kết quả tìm kiếm có relevance | FTS + ts_rank | Xếp hạng theo từ và trọng số |
| Tìm chuỗi giữa một tên sản phẩm | ILIKE '%...%' + pg_trgm | Substring ký tự |
| Gợi ý khi gõ sai một vài ký tự | pg_trgm/fuzzy | Độ tương tự ký tự |
| Tìm tài liệu gần nghĩa nhưng không có chung từ | Semantic/vector search bổ sung | Lexeme matching không đủ |

**Không có một cơ chế duy nhất tốt nhất cho mọi cột.** Hệ tìm kiếm thực tế đôi khi kết hợp FTS, prefix và trigram theo loại dữ liệu.

## 21. B-tree, GIN FTS và trigram khác nhau thế nào?

### 21.1. LIKE 'prefix%'

Truy vấn:

~~~sql
SELECT article_id, title
FROM lab369_articles
WHERE title LIKE 'SQL%';
~~~

về nguyên tắc là tìm prefix ký tự. Một B-tree index trên title có thể hữu ích tùy collation và operator class. PostgreSQL hỗ trợ **text_pattern_ops** cho một số trường hợp pattern matching:

~~~sql
CREATE INDEX lab369_title_prefix_btree
ON lab369_articles (title text_pattern_ops);
~~~

**Không suy ra B-tree này tự tăng tốc mọi ILIKE '%sql%'**. Wildcard đầu chuỗi làm pattern không có prefix cố định để B-tree thông thường sử dụng như một range hữu ích; case-insensitive matching còn phụ thuộc operator/collation.

### 21.2. FTS với @@

~~~sql
CREATE INDEX lab369_search_doc_gin
ON lab369_articles
USING GIN (search_doc);
~~~

Chỉ mục GIN trên tsvector thích hợp cho những truy vấn **search_doc @@ tsquery**. Nó không tự tăng tốc một LIKE bất kỳ trên title vì kiểu biểu thức và toán tử khác.

### 21.3. ILIKE '%substring%' với trigram

~~~sql
-- Yêu cầu pg_trgm đã được cài.
CREATE INDEX lab369_title_trgm_gin
ON lab369_articles
USING GIN (title gin_trgm_ops);
~~~

Đây là một index khác, hữu ích với nhiều pattern LIKE/ILIKE và similarity tùy trường hợp. Cả hai đều dùng **GIN** nhưng **operator class và loại dữ liệu phục vụ truy vấn khác nhau**.

### 21.4. Bảng lựa chọn index

| Truy vấn chủ yếu | Index cân nhắc | Giới hạn |
| --- | --- | --- |
| title = 'SQL indexes' | B-tree trên title | So khớp giá trị |
| title LIKE 'SQL%' | B-tree / text_pattern_ops tùy collation | Prefix có điều kiện |
| title ILIKE '%sql%' | GIN/GiST trigram | Pattern quá ngắn có thể kém |
| search_doc @@ tsquery | GIN trên tsvector | Không tự giải bài toán typo/substrings |
| ORDER BY created_at mới nhất | B-tree trên created_at khi phù hợp | Không thay index FTS |
| Lọc tenant/published + FTS | Chỉ mục và chiến lược truy vấn phối hợp | Planner chọn theo thống kê/độ chọn lọc |

## 22. EXPLAIN: đo thay vì đoán

Với PostgreSQL:

~~~sql
EXPLAIN
SELECT article_id, title
FROM lab369_articles
WHERE search_doc @@ plainto_tsquery(
    'pg_catalog.simple',
    'sql'
);
~~~

Kế hoạch có thể hiển thị:

- **Seq Scan** khi bảng nhỏ.
- **Bitmap Index Scan** trên GIN và **Bitmap Heap Scan** khi số hàng/truy vấn khiến index có lợi.
- Các bước filter bổ sung, aggregate/sort khi truy vấn yêu cầu.

Để đo thực tế:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM lab369_articles
WHERE published IS TRUE
  AND search_doc @@ plainto_tsquery(
      'pg_catalog.simple',
      'sql'
  );
~~~

**EXPLAIN ANALYZE thực sự chạy truy vấn** để lấy số liệu. Với các câu UPDATE/INSERT/DELETE, việc chạy ANALYZE cũng có thể thực thi DML; không thử trên dữ liệu thật thiếu kiểm soát.

### 22.1. Không so sánh tốc độ chỉ bằng một ví dụ 12 hàng

Để so hiệu năng LIKE và FTS một cách có ý nghĩa:

1. Dùng khối lượng dữ liệu đại diện, không chỉ 12 hàng.
2. So truy vấn có **ý nghĩa tương đương** nếu mục tiêu là đo tốc độ; LIKE '%sql%' và FTS 'sql' trả tập kết quả khác nhau nên không phải benchmark apples-to-apples.
3. Giữ giống nhau các điều kiện tenant/published.
4. Xem thời gian, buffers, index usage và số hàng được lọc.
5. Tính cả chi phí index maintenance khi có ghi.
6. Thử query phổ biến lẫn query hiếm, từ ngắn và dài, có nhiều/ít stop words.

**Một con số thời gian đơn lẻ trên dữ liệu nhỏ không chứng minh cơ chế này luôn nhanh hơn cơ chế kia.**

## 23. Cập nhật tài liệu có làm search_doc mới ngay không?

Trong bài, **search_doc là generated stored column**. Khi title/body thay đổi, PostgreSQL tính lại biểu thức tương ứng cho hàng được UPDATE.

Ví dụ thực hành có ROLLBACK:

~~~sql
BEGIN;

UPDATE lab369_articles
SET body = COALESCE(body, '') || ' SQL'
WHERE article_id = 4;

SELECT
    article_id,
    title,
    search_doc @@ plainto_tsquery(
        'pg_catalog.simple',
        'sql'
    ) AS now_matches_sql
FROM lab369_articles
WHERE article_id = 4;

ROLLBACK;
~~~

Ban đầu bài 4 có từ “PostgreSQL” nhưng **không có lexeme sql riêng**. Sau khi thêm chuỗi “ SQL”, **now_matches_sql = TRUE** trong transaction. ROLLBACK khôi phục nội dung cũ và vector tương ứng.

### 23.1. Các cách duy trì search vector

PostgreSQL có thể dùng:

- **Generated stored tsvector column:** biểu thức từ cùng hàng, tự tính khi ghi.
- **Expression index** trực tiếp trên to_tsvector với cấu hình tường minh.
- **Column tsvector cập nhật bằng trigger/ứng dụng:** linh hoạt hơn với một số pipeline nhưng cần kiểm tra đồng bộ.
- **Materialized/search table riêng:** có thể dùng cho hệ phức tạp, đổi lại cần chiến lược refresh/đồng bộ và có nguy cơ dữ liệu trễ.

**Không mặc định mọi hệ FTS tự đồng bộ dữ liệu giống PostgreSQL generated column.** MySQL, SQL Server, SQLite FTS5 external-content và Oracle Text có những cơ chế index/sync riêng.

## 24. Ranking, paging và thứ tự ổn định

Tìm kiếm thường trả nhiều kết quả. Một mẫu:

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'search'
    ) AS tsq
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(a.search_doc, q.tsq) AS score
FROM lab369_articles AS a
CROSS JOIN q
WHERE a.published IS TRUE
  AND a.tenant_id = 20
  AND a.search_doc @@ q.tsq
ORDER BY score DESC, a.article_id
LIMIT 10 OFFSET 0;
~~~

**ORDER BY score DESC, article_id** giúp phá hòa khi hai bài có cùng điểm, tránh thứ tự không xác định do chỉ ORDER BY score.

### 24.1. LIMIT/OFFSET có giới hạn

OFFSET lớn có thể khiến database phải xử lý/bỏ qua nhiều hàng. Với ứng dụng thật, cân nhắc:

- Giới hạn số trang sâu.
- Keyset pagination/cursor sử dụng **score và article_id** khi có thể.
- Cố định các tham số query/config và phân tích ảnh hưởng khi dữ liệu/ranking thay đổi giữa hai request.
- Định nghĩa tiêu chí sort ổn định nếu cần một snapshot nhất quán.

Điểm rank có thể thay đổi khi title/body cập nhật; cursor dựa trên rank phải xử lý điều đó theo yêu cầu sản phẩm.

### 24.2. Kết hợp freshness và relevance

Một số ứng dụng muốn ưu tiên bài mới nhưng vẫn tôn trọng relevance. Có thể cộng thêm điểm theo thời gian hoặc dùng **ORDER BY relevance DESC, created_at DESC**, nhưng hai cách mang ý nghĩa khác nhau:

- Sắp xếp relevance trước rồi dùng ngày phá hòa.
- Trộn relevance với freshness theo một hàm điểm mới.

Không tự thêm hệ số ranking mà không kiểm thử: có thể khiến bài mới nhưng ít liên quan vượt bài thực sự phù hợp.

## 25. Kiểm thử chất lượng tìm kiếm

Không nên chỉ kiểm tra SQL không báo lỗi. Một hệ tìm kiếm còn cần kiểm tra **tập kết quả đúng và khả năng sử dụng**.

### 25.1. Các câu hỏi cho mỗi test query

1. Người dùng muốn **substring**, **whole term**, **phrase** hay **fuzzy**?
2. Có cần khớp hoa/thường, dấu tiếng Việt, từ số nhiều không?
3. Bộ dữ liệu có bao gồm kết quả đúng và trường hợp dễ nhầm không?
4. Các bài chưa xuất bản/tenant khác có bị loại không?
5. Thứ tự relevance có hợp lý với title/body weight không?
6. Query rỗng hoặc toàn stop words xử lý thế nào?
7. Có input đặc biệt như **%**, **_**, dấu nháy, **&**, **|**, dấu trừ không?
8. Query dài bất thường có giới hạn tài nguyên hay không?

### 25.2. Precision và recall

Hai thước đo trong Information Retrieval:

\[
\text{precision}
=\frac{\text{số kết quả trả về có liên quan}}
{\text{tổng số kết quả trả về}}
\]

\[
\text{recall}
=\frac{\text{số kết quả liên quan được tìm thấy}}
{\text{tổng số tài liệu thực sự liên quan}}
\]

Ví dụ với từ “SQL”:

- **ILIKE '%sql%'** có thể trả thêm PostgreSQL/MySQL; nếu người dùng chỉ muốn bài về **ngôn ngữ SQL như một từ**, chúng có thể là false positives.
- **FTS 'sql'** cho ít kết quả hơn theo lexeme; nhưng nếu người dùng muốn cả bài liên quan đến hệ quản trị SQL, kết quả đó có thể lại là **false negatives** theo ý định rộng hơn.

**Chất lượng tìm kiếm phụ thuộc định nghĩa “liên quan” của người dùng**, không chỉ vào việc một hàm SQL cho nhiều hay ít hàng hơn.

## 26. MySQL: FULLTEXT index và MATCH ... AGAINST

MySQL 8.0 hỗ trợ **FULLTEXT index** trên các loại bảng/engine hỗ trợ phù hợp, phổ biến là InnoDB.

Giả sử có bảng **articles(article_id, title, body)** trên MySQL:

~~~sql
CREATE FULLTEXT INDEX ft_articles_title_body
ON articles(title, body);
~~~

Tìm ở chế độ natural language:

~~~sql
SELECT
    article_id,
    title,
    MATCH(title, body)
        AGAINST ('sql indexes' IN NATURAL LANGUAGE MODE)
        AS relevance
FROM articles
WHERE MATCH(title, body)
      AGAINST ('sql indexes' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
~~~

### 26.1. Boolean mode

MySQL có cú pháp boolean FTS riêng:

~~~sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+sql +indexes' IN BOOLEAN MODE);
~~~

Hai dấu **+** biểu diễn yêu cầu những thuật ngữ tương ứng theo ngữ nghĩa Boolean mode của MySQL. Đừng chuyển nguyên văn **'sql & indexes'** của PostgreSQL to_tsquery sang MySQL.

### 26.2. Token size, stopwords và parser

Kết quả MySQL FULLTEXT chịu tác động bởi:

- Cấu hình stopwords.
- Giới hạn độ dài token (ví dụ các biến cấu hình cho InnoDB).
- Collation và parser.
- Phiên bản và cách xây chỉ mục.
- Những chế độ tìm kiếm như natural language/boolean.

Một từ quá ngắn có thể không được index theo cấu hình; một truy vấn có stopwords có thể cho kết quả khác mong đợi. **Không cam kết kết quả giống hệt ví dụ PostgreSQL** vì tokenizer và semantics khác.

### 26.3. Tiếng Việt trên MySQL

MySQL có cơ chế parser/ngram trong những ngữ cảnh ngôn ngữ phù hợp, nhưng cần cấu hình và đánh giá độ chính xác thực tế. Không mặc định FULLTEXT của MySQL tự tách đúng mọi từ ghép tiếng Việt hoặc tự bỏ dấu.

## 27. SQL Server: Full-Text Search

SQL Server có hạ tầng **Full-Text Search** với full-text catalog/index, tokenizer/word breaker theo ngôn ngữ được hỗ trợ.

Ví dụ **chỉ là mẫu triển khai**, giả sử:

- Feature Full-Text Search đã được cài/kích hoạt.
- Bảng **dbo.Articles(ArticleId, Title, Body)** đã tồn tại.
- Có unique key index thích hợp **PK_Articles** trên ArticleId.
- Người dùng có quyền cần thiết.

~~~sql
CREATE FULLTEXT CATALOG ArticleCatalog AS DEFAULT;

CREATE FULLTEXT INDEX ON dbo.Articles (
    Title LANGUAGE 1033,
    Body LANGUAGE 1033
)
KEY INDEX PK_Articles;
~~~

**LANGUAGE 1033** chỉ ngôn ngữ tiếng Anh cho ví dụ. Không dùng mã này rồi mong word breaker tiếng Việt hoạt động đúng; hỗ trợ ngôn ngữ phụ thuộc thành phần và phiên bản đã cài.

### 27.1. CONTAINS và FREETEXT

~~~sql
SELECT ArticleId, Title
FROM dbo.Articles
WHERE CONTAINS(
    (Title, Body),
    '"sql" AND "indexes"'
);
~~~

SQL Server có **CONTAINS** với cú pháp tìm kiếm riêng và **FREETEXT** với cách xử lý ngôn ngữ tự nhiên khác. Không nhầm **FREETEXT** của SQL Server với từ khóa TEXT bình thường trong PostgreSQL.

### 27.2. CONTAINSTABLE trả điểm RANK

~~~sql
SELECT
    a.ArticleId,
    a.Title,
    k.[RANK] AS relevance
FROM CONTAINSTABLE(
    dbo.Articles,
    (Title, Body),
    '"sql" AND "indexes"'
) AS k
JOIN dbo.Articles AS a
    ON a.ArticleId = k.[KEY]
ORDER BY k.[RANK] DESC, a.ArticleId;
~~~

**RANK** trong CONTAINSTABLE thuộc cách chấm điểm của SQL Server; không thể so trực tiếp số này với **ts_rank_cd** PostgreSQL như thể chúng cùng thang đo.

### 27.3. Vòng đời index

SQL Server Full-Text Search còn có quản lý **population/indexing**. Khi thay đổi dữ liệu, cần hiểu chế độ change tracking, population và độ trễ cập nhật của cấu hình thực tế, không mặc định luôn giống generated tsvector + GIN của PostgreSQL.

## 28. SQLite FTS5: virtual table riêng

SQLite cung cấp extension **FTS5** trên các bản build có hỗ trợ. Khác ordinary LIKE trên một cột bảng, FTS5 thường dùng **virtual table**:

~~~sql
CREATE VIRTUAL TABLE articles_fts
USING fts5(
    title,
    body,
    tokenize = 'unicode61'
);
~~~

Nạp dữ liệu mẫu vào FTS5:

~~~sql
INSERT INTO articles_fts(rowid, title, body)
VALUES
    (1, 'SQL query optimization',
     'Indexes help SQL query performance'),
    (2, 'PostgreSQL full text search',
     'PostgreSQL uses text search'),
    (3, 'MySQL text search',
     'MySQL offers FULLTEXT indexes');
~~~

Tìm:

~~~sql
SELECT rowid, title
FROM articles_fts
WHERE articles_fts MATCH 'sql AND indexes';
~~~

Với cấu hình dữ liệu và tokenizer mẫu, hàng 1 có cả hai token “sql” và “indexes”.

### 28.1. Ranking của FTS5

~~~sql
SELECT
    rowid,
    title,
    bm25(articles_fts) AS score
FROM articles_fts
WHERE articles_fts MATCH 'search'
ORDER BY score ASC, rowid;
~~~

**Chú ý dấu sắp xếp:** trong FTS5, **giá trị bm25 nhỏ hơn thường biểu diễn mức phù hợp tốt hơn** theo cách FTS5 tính điểm, vì thế thường sắp **ASC**. Đừng mang ORDER BY score DESC của PostgreSQL sang rồi đảo ngược ranking của SQLite.

### 28.2. Tokenizer và tiếng Việt

Tokenizer **unicode61** nhận biết nhiều ký tự Unicode và có tùy chọn xử lý dấu trong các trường hợp hỗ trợ, nhưng không đồng nghĩa với bộ tách từ/ngữ nghĩa tiếng Việt chuyên dụng. Cần thử với dữ liệu tiếng Việt và cấu hình tokenizer thực tế.

### 28.3. Đồng bộ dữ liệu bảng thường và FTS5

Một virtual table FTS5 độc lập không tự biết mọi UPDATE của một bảng khác nếu không có liên kết/cơ chế đồng bộ. SQLite FTS5 hỗ trợ **external-content/contentless** và trigger hoặc quy trình update index theo mô hình tương ứng, nhưng việc đó cần được thiết kế chính xác.

**Tạo bảng FTS5 rồi quên cập nhật nó là một lỗi đồng bộ phổ biến.**

## 29. Oracle Text: CONTAINS và CONTEXT index

Trong Oracle Database có thành phần **Oracle Text** để tìm kiếm toàn văn.

Giả sử đã có bảng **articles(article_id, body)** và quyền cần thiết:

~~~sql
CREATE INDEX article_body_ctx
ON articles(body)
INDEXTYPE IS CTXSYS.CONTEXT;
~~~

Tìm:

~~~sql
SELECT
    article_id,
    SCORE(1) AS relevance
FROM articles
WHERE CONTAINS(body, 'sql AND indexes', 1) > 0
ORDER BY SCORE(1) DESC, article_id;
~~~

Các thành phần:

- **CTXSYS.CONTEXT** xác định loại Oracle Text index.
- **CONTAINS** dùng cú pháp truy vấn riêng của Oracle Text.
- **SCORE(1)** cho điểm với label 1 tương ứng trong CONTAINS.

### 29.1. Chú ý đồng bộ index

Oracle Text CONTEXT index có cơ chế **synchronization/maintenance** riêng. Tùy cấu hình, nội dung vừa INSERT/UPDATE chưa chắc đã tìm thấy ngay trước khi index được sync. Cần chọn chính sách cập nhật, tối ưu và vận hành phù hợp.

### 29.2. Không suy luận cú pháp từ PostgreSQL

Oracle không dùng **to_tsvector @@ to_tsquery** theo cùng cách PostgreSQL. Tương tự, query string **'sql AND indexes'** trong Oracle Text phải hiểu theo parser của Oracle Text, không thể bê nguyên mọi toán tử của PostgreSQL/MySQL/SQL Server sang.

## 30. Đối chiếu nhanh các phương ngữ

| Khía cạnh | PostgreSQL | MySQL | SQL Server | SQLite FTS5 | Oracle Text |
| --- | --- | --- | --- | --- | --- |
| So khớp ký tự | LIKE/ILIKE | LIKE + collation | LIKE + collation | LIKE/GLOB theo ngữ cảnh | LIKE |
| Full text native | TSVECTOR/TSQUERY | FULLTEXT index | Full-Text index/catalog | Virtual table FTS5 | Oracle Text index |
| Lệnh tìm | @@ | MATCH ... AGAINST | CONTAINS/FREETEXT | MATCH | CONTAINS |
| Nhiều từ | tsquery & / \| | Boolean mode +/- | Cú pháp CONTAINS | FTS5 query syntax | Oracle Text query syntax |
| Tìm phrase | <-> / phraseto_tsquery | Boolean phrase/cú pháp hỗ trợ | Quoted phrase trong CONTAINS | Quoted phrase | Oracle Text phrase syntax |
| Ranking | ts_rank/ts_rank_cd | Relevance từ MATCH | RANK từ CONTAINSTABLE | bm25 | SCORE |
| Tạo chỉ mục | GIN trên tsvector | FULLTEXT | CREATE FULLTEXT INDEX | FTS5 virtual table | CTXSYS.CONTEXT |
| Từ điển/ngôn ngữ | Regconfig, dictionaries | Parser/stopwords/token size | Word breaker/language | Tokenizer | Lexer/stoplist/wordlist |
| Dữ liệu mới | Tùy generated/trigger/index | Theo FULLTEXT engine | Theo population/tracking | Tùy content/sync | Tùy index sync |

**Chú ý:** cú pháp boolean và phrase **không tương thích từng ký tự** giữa các hệ. Một tính năng có tên “full-text” vẫn cần kiểm tra lexer, stopwords, index maintenance, ranking và ngôn ngữ theo phiên bản cụ thể.

## 31. Một chiến lược tìm kiếm hỗn hợp trong ứng dụng

Đối với một ứng dụng bán hàng/tài liệu, có thể chia trường:

~~~text
SKU / mã đơn
    └── Exact = hoặc LIKE 'prefix%'

Tiêu đề ngắn
    ├── FTS theo từ/phrase
    └── Trigram cho typo/substrings

Nội dung dài
    └── FTS + relevance + snippet

Từ khóa tiếng Việt
    └── Tokenization/normalize dấu phù hợp

Phân quyền
    └── Tenant + published + RLS/ACL
~~~

### 31.1. Không OR tùy tiện mọi phép tìm

Một truy vấn:

~~~sql
WHERE title ILIKE '%sql%'
   OR search_doc @@ plainto_tsquery('simple','sql')
~~~

có thể trả nhiều hơn cả hai cơ chế riêng, nhưng những kết quả phụ từ substring vẫn tồn tại. Nếu muốn kết hợp, cần quyết định:

- Kết quả FTS có điểm cao hơn kết quả substring không?
- Kết quả trùng giữa hai nhánh được khử thế nào?
- Có cần giới hạn candidate trước khi ranking?
- Cả hai nhánh có cùng điều kiện tenant/published không?
- Query rỗng/đặc biệt có làm mở rộng tập kết quả ngoài ý muốn không?

**Kết hợp kỹ thuật chỉ tốt khi có hợp đồng relevance rõ ràng.**

### 31.2. Search as you type

Khi người dùng gõ từng ký tự “pos”, “post”, “postg”:

- Prefix lexeme **postg:* ** có thể hỗ trợ từ một độ dài nhất định.
- Prefix **LIKE 'post%'** phù hợp nếu chỉ tìm ở đầu title/mã.
- Trigram có thể hỗ trợ gần đúng/substrings nhưng quá ít ký tự có thể kém hiệu quả.
- Ứng dụng nên debounce/giới hạn tần suất và LIMIT.

FTS toàn văn phù hợp với tìm bài, nhưng **autocomplete tên sản phẩm** đôi khi cần một chỉ mục/thuật toán riêng.

## 32. Những lỗi thường gặp

| Nhầm lẫn/lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi LIKE '%sql%' là tìm từ SQL | PostgreSQL/MySQL cũng khớp | Dùng FTS theo lexeme khi cần tìm từ |
| Coi FTS là LIKE chạy nhanh hơn | Tập kết quả khác vì tokenization | Chọn theo ngữ nghĩa cần tìm |
| Dùng LIKE khi cần ranking | Không có relevance mặc định | FTS + ts_rank/ts_rank_cd |
| Dùng FTS để tìm chuỗi con bất kỳ | Không khớp bên trong token | LIKE/ILIKE + pg_trgm |
| Quên wildcard _ trong LIKE | Ký tự đơn bất kỳ được khớp | Escape bằng ESCAPE hợp lệ |
| Truyền trực tiếp input vào SQL nối chuỗi | SQL injection | Bind parameter |
| Cho input thô vào to_tsquery | Lỗi cú pháp/sai toán tử | plainto_tsquery hoặc websearch_to_tsquery |
| Tạo vector bằng simple, query bằng english | Lexeme có thể khác | Đồng bộ text search config |
| Tưởng English stemming áp dụng cho tiếng Việt | Sai token/không hiểu từ ghép | Pipeline tiếng Việt chuyên dụng |
| Tưởng bỏ dấu tự động | “ca phe” có thể không khớp “cà phê” | Cấu hình normalize/unaccent nhất quán |
| Chỉ lập chỉ mục body mà mong rank ưu tiên title | Tiêu đề không được weighting | setweight cho từng trường |
| Gán weights A/B nhưng hiểu sai thứ tự mảng | Ranking sai mục tiêu | Mảng D,C,B,A trong ts_rank |
| Không ORDER BY khi hiển thị | Kết quả không ổn định | ORDER BY score + tie-breaker |
| Cho score là xác suất | Diễn giải sai relevance | Score là heuristic |
| Dùng ORDER BY DESC cho bm25 FTS5 | Đảo hướng ranking | bm25 thường ASC |
| Tạo GIN rồi kỳ vọng LIKE dùng | Index/operator không khớp | GIN tsvector cho @@; trigram cho ILIKE |
| Tạo index trên 12 hàng rồi bắt buộc phải thấy index scan | Planner chọn Seq Scan hợp lý | Đo trên dữ liệu đại diện |
| Bỏ tenant/published trong search | Rò rỉ dữ liệu | Điều kiện quyền/RLS đáng tin |
| Tính total count trên toàn bộ tài liệu | Lộ thông tin qua thống kê | Lọc ACL trước mọi thống kê |
| Kết quả ts_headline đưa HTML thô | Có thể tạo XSS khi render | Escape/allowlist phù hợp |
| Coi ts_headline là dữ liệu gốc | Dữ liệu bị thay marker/cắt đoạn | Giữ title/body gốc |
| Dùng stop words query rỗng để trả hết tài liệu | Rò rỉ/đọc quá nhiều | Kiểm tra numnode, UX rõ |
| Đo benchmark LIKE và FTS với hai tập kết quả khác nhau | Kết luận tốc độ không công bằng | So cùng semantics và dataset |
| Không đồng bộ index ngoài/generated | Tìm thiếu dữ liệu mới | Thiết kế update/refresh/sync |
| Port &/|/:* sang MySQL/Oracle nguyên văn | Sai parser | Dùng cú pháp của hệ |
| SQLite FTS5 virtual table không cập nhật sau INSERT bảng gốc | Index cũ | Trigger hoặc sync phù hợp |

## 33. Bài tập thực hành

Các bài PostgreSQL dùng **lab369_articles** ở phần 6. Các bài MySQL/SQL Server/SQLite/Oracle yêu cầu hệ tương ứng; đừng gửi cú pháp của hệ khác tới PostgreSQL.

1. Giải thích vì sao **LIKE '%sql%'** khớp PostgreSQL/MySQL nhưng FTS lexeme **sql** không khớp hai tên đó.
2. Tạo bảng lab369_articles với cột search_doc generated stored và nạp 12 tài liệu.
3. Kiểm tra tổng 12 bài, 11 bài published và số bài theo tenant.
4. Viết ILIKE tìm tiêu đề có chuỗi con “sql”; đối chiếu các article_id 1,2,6,7,8,12.
5. Viết FTS tìm lexeme “sql”; đối chiếu các article_id 1,6,7.
6. Chỉ hiển thị bài published của tenant 10 khi tìm “sql”; bài nào còn?
7. Tìm lexeme “postgresql”; khác gì ILIKE '%sql%'?
8. Dùng plainto_tsquery('simple','sql indexes'); vì sao kết quả gồm 1 và 7?
9. Dùng to_tsquery với **sql | mysql**. Đối chiếu tài liệu MySQL và SQL riêng.
10. Dùng to_tsquery **postgresql & search**; xác định bài phù hợp.
11. Dùng **sql & !indexes**; vì sao bài 6 có thể xuất hiện nếu không lọc published?
12. Dùng phrase **full <-> text** tìm bài 2.
13. Dùng phraseto_tsquery với “full text search”; nêu sự khác nhau với plainto_tsquery ba từ.
14. Dùng prefix lexeme **postgre:* **. Prefix này có khớp “MySQL” không? Vì sao?
15. Dùng websearch_to_tsquery cho '"full text" OR mysql -jdbc', xem biểu thức tạo ra.
16. So sánh to_tsvector('simple', ...) với to_tsvector('english', ...) trên câu có “running”, “indexes” và “the”.
17. Điều gì xảy ra nếu index dùng simple nhưng query dùng english stemming?
18. Dùng numnode để kiểm tra truy vấn english chỉ chứa stop words.
19. Tạo GIN index trên search_doc; dùng EXPLAIN truy vấn lexeme.
20. Vì sao EXPLAIN vẫn có thể chọn Seq Scan với 12 tài liệu?
21. Sắp xếp bài khớp “search” theo ts_rank_cd, thêm article_id phá hòa.
22. Thử mảng weights cho title A cao hơn body B; vì sao mảng có thứ tự D,C,B,A?
23. Dùng ts_headline tạo snippet, thảo luận cách tránh XSS nếu hiển thị HTML.
24. Trong transaction, thêm từ SQL vào body bài 4; xem search_doc khớp, rồi ROLLBACK.
25. Tạo text_pattern_ops index cho title và giải thích truy vấn LIKE 'SQL%' khác ILIKE '%sql%'.
26. Cài pg_trgm nếu có quyền, tạo trigram index trên title và so sánh kết quả ILIKE substring.
27. Dùng similarity đo độ gần của “PostgreSQ” với các title.
28. Thử tìm “cà phê” và “ca phe”; giải thích vì sao pipeline bỏ dấu phải nhất quán.
29. Mô tả vấn đề từ ghép “điện thoại” khi tokenizer tách thành nhiều lexeme.
30. Đề xuất pipeline hỗ trợ tìm tiếng Việt có dấu/không dấu và từ đồng nghĩa.
31. Viết prepared statement nhận text query và tenant_id, giới hạn 20 bài published.
32. Vì sao tenant_id truyền từ browser mà chưa xác minh không phải biện pháp bảo mật?
33. Viết MySQL FULLTEXT index và MATCH ... AGAINST trong Boolean mode với hai từ bắt buộc.
34. Phân biệt natural language mode của MySQL với plainto_tsquery của PostgreSQL.
35. Viết SQL Server CONTAINS và CONTAINSTABLE, giải thích cột RANK.
36. Tạo một SQLite FTS5 virtual table và truy vấn MATCH; vì sao FTS5 external content cần cơ chế đồng bộ?
37. Vì sao bm25(fts5_table) thường sắp ASC chứ không DESC?
38. Viết Oracle Text CONTAINS và SCORE, giải thích sync index.
39. Thiết kế tìm kiếm sản phẩm theo SKU prefix, tên gần đúng và mô tả dài: mỗi trường nên dùng gì?
40. Lập bộ test precision/recall gồm từ đúng, lỗi chính tả, NULL, dấu tiếng Việt, stop words, tenant khác và bài chưa xuất bản.

### Câu hỏi tự kiểm tra

**Câu 1.** LIKE và FTS có cùng ngữ nghĩa, chỉ khác index không?

**Đáp án:** **Không.** LIKE so khớp mẫu ký tự; FTS so khớp lexeme đã xử lý theo text search configuration.

**Câu 2.** Với title “PostgreSQL”, ILIKE '%sql%' và FTS 'sql' có chắc cho kết quả giống nhau không?

**Đáp án:** **Không.** ILIKE khớp chuỗi con; FTS thường coi “postgresql” là lexeme riêng, không phải “sql”.

**Câu 3.** FTS có tự hiểu dấu tiếng Việt và tách mọi từ ghép chính xác không?

**Đáp án:** **Không mặc định.** Cần thiết kế tokenizer/dictionary/normalization cho tiếng Việt.

**Câu 4.** plainto_tsquery('simple','sql indexes') thường nối hai từ bằng OR hay AND?

**Đáp án:** **AND**.

**Câu 5.** GIN index trên tsvector có mặc định tăng tốc title ILIKE '%sql%' không?

**Đáp án:** **Không.** Đây là toán tử/biểu thức khác; có thể cân nhắc pg_trgm cho substring.

**Câu 6.** Có GIN index thì kết quả @@ tự xếp theo mức độ liên quan?

**Đáp án:** **Không.** Cần tính ts_rank/ts_rank_cd và ORDER BY nếu muốn relevance.

**Câu 7.** Người dùng gửi chuỗi ký tự tùy ý có nên nối thẳng vào to_tsquery trong SQL không?

**Đáp án:** **Không.** Dùng bind parameter và parser phù hợp như websearch_to_tsquery/plainto_tsquery.

**Câu 8.** Nếu một bài thuộc tenant khác nhưng FTS match tốt, có được hiển thị không?

**Đáp án:** **Không nếu người dùng không có quyền.** Điều kiện ACL/tenant và published luôn phải được áp dụng đáng tin.

**Câu 9.** bm25 của SQLite FTS5 có cùng chiều sắp xếp với ts_rank_cd PostgreSQL không?

**Đáp án:** **Không.** PostgreSQL relevance thường sắp DESC; FTS5 bm25 thường sắp ASC.

**Câu 10.** Full-text index có chắc phản ánh dữ liệu mới ngay trên mọi RDBMS?

**Đáp án:** **Không.** PostgreSQL generated tsvector và GIN theo cơ chế cập nhật của bảng; SQL Server, SQLite external-content và Oracle Text có chiến lược đồng bộ riêng.

## 34. Ghi nhớ cốt lõi

**LIKE khớp ký tự. Full-text search khớp lexeme.** Không chọn FTS chỉ vì nghe nhanh hơn, cũng không dùng LIKE như thể nó hiểu từ, stemming, phrase hoặc ranking.

Trong PostgreSQL:

~~~text
LIKE / ILIKE                   → mẫu ký tự, substring, prefix
to_tsvector(config, text)      → lexeme + vị trí
plainto_tsquery(config, text)  → từ khóa thường, kết hợp AND
phraseto_tsquery(config, text) → cụm từ theo thứ tự
websearch_to_tsquery(...)      → cú pháp nhập thân thiện kiểu web
to_tsquery(config, expression) → AND / OR / NOT / prefix / phrase
tsvector @@ tsquery            → so khớp tài liệu
GIN(tsvector)                  → chỉ mục full-text thông dụng
ts_rank / ts_rank_cd           → điểm relevance
ts_headline                    → đoạn trích có đánh dấu
pg_trgm                        → substring/fuzzy ký tự bổ sung
~~~

**Chọn cùng text search configuration cho index và query**; đừng mặc định simple/english hỗ trợ đầy đủ ngôn ngữ tiếng Việt, từ ghép, bỏ dấu hoặc sửa lỗi chính tả. Cần pipeline phù hợp với dữ liệu/người dùng thực tế.

**Tìm kiếm luôn gắn với quyền truy cập.** Dù query match tốt, vẫn phải lọc tenant, published và ACL theo nguồn tin cậy; bind input an toàn; tránh rò rỉ qua kết quả đếm, gợi ý và snippet. Khi đo hiệu năng, dùng dữ liệu đại diện và so những truy vấn có cùng mục tiêu ngữ nghĩa.

Cuối cùng, mỗi RDBMS có cơ chế riêng: **MySQL MATCH ... AGAINST**, **SQL Server CONTAINS/FREETEXT**, **SQLite FTS5 MATCH**, **Oracle Text CONTAINS**. Kiến thức chung là tokenization, index, query và relevance; **cú pháp, ngôn ngữ, cách cập nhật index và điểm ranking không thể port nguyên văn** giữa các hệ.
