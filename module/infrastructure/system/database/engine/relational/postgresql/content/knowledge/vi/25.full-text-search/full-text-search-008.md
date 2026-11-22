# Chỉ mục GIN, GiST và kiểm tra kế hoạch tìm kiếm trong PostgreSQL

Khi người dùng tìm một cụm từ trong vài nghìn tài liệu, truy vấn trực tiếp có thể đủ nhanh. Nhưng nếu một ứng dụng lưu hàng triệu bài viết, mô tả sản phẩm, ghi chú hỗ trợ hoặc tài liệu nghiệp vụ, việc áp dụng xử lý văn bản lên từng hàng trong mỗi lần tìm kiếm có thể tiêu tốn rất nhiều CPU và I/O. PostgreSQL cung cấp cơ chế **Full Text Search (FTS)** với các kiểu dữ liệu `tsvector</BT>, `tsquery</BT>, toán tử so khớp `@@</BT> và các loại chỉ mục thích hợp, đặc biệt là **GIN** và **GiST**.

Một truy vấn tiêu biểu:

~~~sql
SELECT article_id, title
FROM articles
WHERE search_vector @@ plainto_tsquery('simple', 'postgresql gin');
~~~

Nếu `search_vector</BT> đã được lập chỉ mục GIN hoặc GiST phù hợp, PostgreSQL có thể tra chỉ mục để xác định những hàng có khả năng đáp ứng điều kiện, thay vì bắt buộc đánh giá biểu thức tìm kiếm trên toàn bộ bảng. Nhưng **có chỉ mục không có nghĩa planner luôn sử dụng nó**: kế hoạch còn phụ thuộc số hàng, tính chọn lọc, biểu thức được viết, tham số truy vấn, chi phí và trạng thái thống kê.

Bài học thuộc chương **Tìm kiếm văn bản** của module **Database Engine Relational PostgreSQL**. Nội dung đi từ khái niệm FTS, cách tạo `tsvector</BT>/`tsquery</BT>, so sánh GIN với GiST, sự khác biệt giữa **index hit** và **recheck**, cho đến thiết kế bài lab, đọc `EXPLAIN (ANALYZE, BUFFERS)</BT>, bảo trì chỉ mục và xử lý các tình huống truy vấn không dùng index.

## 1. Bản đồ tư duy: từ chuỗi văn bản đến kết quả tìm kiếm

Một hệ thống FTS thường có bốn bước:

~~~text
             DỮ LIỆU
title/body: "PostgreSQL GIN Index and Query Planning"
                 |
                 | to_tsvector(config, document)
                 v
          SEARCHABLE VECTOR
lexemes + thông tin vị trí/trọng số
                 |
                 | GIN hoặc GiST index
                 v
       CANDIDATE MATCHING ROWS
                 ^
                 | toán tử @@
                 |
                 | plainto_tsquery / websearch_to_tsquery / ...
                 |
User input: "gin index"
                 |
                 v
             TSQUERY
                 |
                 v
          Planner + Executor
                 |
                 v
        Rows matched + ranking
~~~

Cần tách ba tầng:

1. **Ngữ nghĩa**: từ nào được coi là lexeme, cách phân tích query, logic AND/OR/phrase.
2. **Access path**: index GIN/GiST giúp tìm ứng viên nào.
3. **Thực thi**: planner chọn kế hoạch nào, có cần recheck ở heap không, phải đọc bao nhiêu buffers và tính ranking cho bao nhiêu hàng.

Nhầm ba tầng sẽ dẫn tới những kết luận sai như “tạo GIN là không cần `to_tsvector</BT>”, “GiST trả kết quả sai vì false positives”, hoặc “EXPLAIN hiện Seq Scan nghĩa index bị hỏng”.

## 2. FTS khác tìm chuỗi con thông thường

So sánh:

~~~sql
SELECT *
FROM articles
WHERE body ILIKE '%postgres%';
~~~

với:

~~~sql
SELECT *
FROM articles
WHERE search_vector @@ plainto_tsquery('simple', 'postgres');
~~~

Hai truy vấn có **ngữ nghĩa khác nhau**.

- `ILIKE '%postgres%'</BT> tìm chuỗi con không phân biệt hoa/thường theo phép so khớp và collation hiện hành.
- FTS phân tích tài liệu thành **lexemes** theo text search configuration, rồi so khớp với một `tsquery</BT>.
- Với cấu hình stemming, từ có thể được chuyển về dạng gốc hoặc chuẩn hóa.
- FTS không mặc nhiên là substring search; tìm `post</BT> không tự đồng nghĩa với khớp mọi từ chứa chuỗi `post</BT>.
- Một query FTS có thể dùng AND, OR, NOT, phrase và prefix lexeme queries.

Nếu yêu cầu là tìm **chuỗi con**, gõ sai gần đúng hoặc autocomplete theo chuỗi ký tự, cần cân nhắc `pg_trgm</BT> hoặc cơ chế phù hợp khác, thay vì sử dụng GIN FTS sai ngữ nghĩa.

## 3. Cấu hình tìm kiếm văn bản quyết định lexemes

PostgreSQL có các text search configurations, ví dụ `simple</BT> và `english</BT>.

~~~sql
SELECT to_tsvector(
    'simple',
    'PostgreSQL provides GIN and GiST indexes'
);

SELECT to_tsvector(
    'english',
    'PostgreSQL provides indexes for searching documents'
);
~~~

### 3.1. Vì sao kết quả khác nhau?

Text search configuration quy định parser, dictionaries, stop words và các bước chuẩn hóa thích hợp. Cấu hình tiếng Anh thường có stemming và xử lý stop words theo từ điển; `simple</BT> có hành vi khác.

Ví dụ, “searching” và “search” có thể quy về cùng lexeme dưới một cấu hình stemming phù hợp. Với `simple</BT>, đừng giả định mọi biến thể từ được quy về cùng gốc.

### 3.2. Kiểm tra cấu hình mặc định

~~~sql
SHOW default_text_search_config;
~~~

Để query dễ dự đoán, thường nên **chỉ rõ cấu hình** trong cả phần tạo vector và phần tạo query thay vì vô tình phụ thuộc cấu hình mặc định của session.

### 3.3. Phải nhất quán giữa index và query

Nếu vector được tạo bằng `simple</BT> nhưng query bằng `english</BT>, việc biến đổi lexemes khác nhau có thể khiến từ không khớp như mong đợi. Không có quy tắc “GIN tự chuyển từ từ điển này sang từ điển kia”.

### 3.4. Giới hạn với tiếng Việt

PostgreSQL mặc định không cung cấp một quy trình phân tách từ tiếng Việt giàu ngôn ngữ như những search engines chuyên biệt. `simple</BT> có thể dùng cho những văn bản đã được phân tách phù hợp hoặc tìm lexemes đơn giản, nhưng từ ghép nhiều âm tiết, dấu tiếng Việt, đồng nghĩa và lỗi gõ có thể cần dictionary, tokenizer hoặc extension chuyên dụng.

Không nên đánh dấu một truy vấn tiếng Việt “chính xác về ngôn ngữ” chỉ vì nó dùng `tsvector</BT> và GIN.

## 4. tsvector chứa những gì?

`tsvector</BT> biểu diễn tài liệu sau khi phân tích văn bản: các **lexemes** và có thể có vị trí cùng trọng số. Ví dụ:

~~~sql
SELECT to_tsvector(
    'simple',
    'gin gist gin planner'
);
~~~

Đầu ra có thể hiển thị dạng khái niệm:

~~~text
'gin':1,3 'gist':2 'planner':4
~~~

PostgreSQL chuẩn hóa và sắp xếp lexemes, có thể gom nhiều vị trí của cùng từ dưới một lexeme.

### 4.1. Vị trí phục vụ phrase/proximity

Thông tin vị trí giúp đánh giá những điều kiện như “gin đứng ngay trước gist”. Đây là ngữ nghĩa so khớp mà chỉ biết “hai từ cùng xuất hiện” chưa đủ.

### 4.2. Trọng số A, B, C, D

Có thể xây vector từ tiêu đề và nội dung với mức ưu tiên khác nhau:

~~~sql
SELECT
    setweight(to_tsvector('simple', 'GIN index'), 'A')
    ||
    setweight(to_tsvector('simple', 'Article about database searching'), 'B');
~~~

Thông thường A dùng cho tiêu đề, B cho nội dung; C/D cho các nguồn khác. Đây là quy ước của ứng dụng, không phải PostgreSQL bắt buộc tiêu đề luôn là A.

### 4.3. tsvector không phải bản gốc của tài liệu

Vector không giữ nguyên toàn bộ văn bản, dấu câu, chữ hoa/thường và khoảng trắng theo cách truy hồi chính xác. Lưu title/body gốc nếu ứng dụng cần hiển thị hoặc trích dẫn văn bản.

### 4.4. Tránh vector NULL

Nếu title/body có thể NULL, dùng `coalesce(title, '')</BT> và `coalesce(body, '')</BT> khi tạo vector để tránh NULL lan truyền.

## 5. tsquery là gì?

`tsquery</BT> biểu diễn điều kiện tìm kiếm theo lexemes và toán tử logic.

~~~sql
SELECT to_tsquery('simple', 'gin & gist');
SELECT to_tsquery('simple', 'gin | gist');
SELECT to_tsquery('simple', 'gin & !deprecated');
SELECT to_tsquery('simple', 'gin <-> gist');
~~~

| Toán tử | Ý nghĩa |
|---|---|
| `&</BT> | AND, các điều kiện đều phải phù hợp |
| `|</BT> | OR, ít nhất một điều kiện |
| `!</BT> | NOT |
| `<-></BT> | Phrase / hai lexemes liền kề theo ngữ nghĩa |
| `<N></BT> | Khoảng cách vị trí N theo cú pháp tsquery |
| `:*</BT> | Prefix matching của lexeme |
| `:A</BT>, `:B</BT> | Ràng buộc lexeme theo weight |

Ví dụ prefix:

~~~sql
SELECT to_tsquery('simple', 'post:*');
~~~

Từ khóa dạng prefix này nhắm những **lexemes** bắt đầu bằng `post</BT>, không tương đương mọi phép tìm chuỗi con ở vị trí bất kỳ của văn bản.

### 5.1. Cẩn thận khi ghép SQL string

Không nên nối trực tiếp user input vào `to_tsquery</BT> hay SQL text bằng chuỗi:

~~~text
"SELECT ... WHERE vector @@ to_tsquery('simple', '" + input + "')"
~~~

Dùng prepared statements và hàm tạo tsquery phù hợp để giảm lỗi cú pháp và tránh SQL injection.

### 5.2. to_tsquery yêu cầu cú pháp tsquery

Nếu input là văn bản người dùng gõ tự do, một chuỗi có dấu câu hoặc operator không đúng có thể gây lỗi cú pháp trong `to_tsquery</BT>. `plainto_tsquery</BT> hoặc `websearch_to_tsquery</BT> thường thuận tiện hơn cho search box.

## 6. Các hàm tạo query cho từng loại input

### 6.1. plainto_tsquery

~~~sql
SELECT plainto_tsquery(
    'simple',
    'gin gist'
);
~~~

Hàm xử lý plain text thành query, thường kết hợp các từ phù hợp bằng AND.

### 6.2. phraseto_tsquery

~~~sql
SELECT phraseto_tsquery(
    'simple',
    'gin gist'
);
~~~

Dùng khi thứ tự/vị trí liền kề của lexemes quan trọng. Cách xử lý stop words phụ thuộc cấu hình.

### 6.3. websearch_to_tsquery

~~~sql
SELECT websearch_to_tsquery(
    'english',
    '"full text search" OR index'
);
~~~

Dùng cho cú pháp gần với search box/web search, hỗ trợ một số cách viết dễ đọc như dấu ngoặc kép cho phrase và OR. Không xem nó là một parser cho mọi biểu thức tsquery nâng cao.

### 6.4. to_tsquery

~~~sql
SELECT to_tsquery(
    'simple',
    'postgresql & (gin | gist)'
);
~~~

Hữu ích khi ứng dụng muốn kiểm soát toán tử tường minh. Cần chuẩn bị query an toàn, không ném user text thô vào cú pháp tsquery.

### 6.5. Không chọn bằng “hàm nhanh nhất”

Chọn hàm theo **ngữ nghĩa người dùng mong đợi**. Query trả ít hàng hơn có thể nhanh hơn nhưng sai nhu cầu; kết quả đúng quan trọng hơn chỉ số thời gian.

## 7. Toán tử @@ kết nối vector và query

Một ví dụ trực tiếp:

~~~sql
SELECT
    to_tsvector('simple', 'GIN GiST planner')
    @@
    plainto_tsquery('simple', 'gin planner')
    AS is_match;
~~~

Kết quả logic là đúng với tài liệu chứa cả lexemes được yêu cầu.

### 7.1. Hướng viết phổ biến

~~~sql
WHERE search_vector @@ plainto_tsquery('simple', :search_text)
~~~

Dùng bind parameter theo driver/framework, không ghép chuỗi SQL thủ công.

### 7.2. Phân biệt điều kiện và ranking

`@@</BT> xác định row có match không. `ts_rank</BT> hoặc `ts_rank_cd</BT> tính điểm xếp hạng. Chỉ mục hỗ trợ tìm ứng viên, không mặc định sắp xếp kết quả theo điểm relevance.

### 7.3. Search kết hợp điều kiện nghiệp vụ

~~~sql
WHERE status = 'published'
  AND tenant_id = 42
  AND search_vector @@ plainto_tsquery('simple', 'gin index')
~~~

Planner có thể phối hợp các access paths và filters. Loại index cần dựa vào toàn workload, không chỉ một điều kiện `@@</BT>.

## 8. GIN là gì?

**GIN (Generalized Inverted Index)** là chỉ mục đảo: từ một khóa trong dữ liệu phức hợp, index giúp tìm những rows chứa khóa đó.

Với full-text search trên `tsvector</BT>, khóa điển hình là **lexemes**.

~~~text
Lexeme -> posting list / posting tree of matching rows

'gin'        -> row 3, row 7, row 19, ...
'gist'       -> row 7, row 25, ...
'planner'    -> row 3, row 7, row 26, ...

Query: gin & planner
  -> tìm ứng viên có cả hai lexemes
  -> xác minh ngữ nghĩa khi cần
~~~

### 8.1. Tạo GIN index cho tsvector

~~~sql
CREATE INDEX articles_search_gin_idx
ON articles
USING GIN (search_vector);
~~~

Đây là cú pháp mẫu; bảng `articles</BT> cần tồn tại. Trong phần lab sẽ có schema/table đầy đủ.

### 8.2. Vì sao GIN thường là lựa chọn mặc định cho FTS?

GIN thường có hiệu quả tra cứu cao khi query lọc theo lexemes, đặc biệt trên tập tài liệu lớn và điều kiện đủ chọn lọc. GIN cũng là lựa chọn thường được PostgreSQL khuyến nghị cho full-text search thông dụng.

### 8.3. GIN không lưu mọi thông tin tsvector

GIN index trên `tsvector</BT> tập trung vào **lexemes**, không lưu đủ mọi thông tin vị trí và weights phục vụ tất cả kiểu query. Với weighted search hoặc phrase/proximity, executor có thể phải **kiểm tra lại row/vector** để đánh giá đầy đủ.

### 8.4. Lợi thế đọc đi kèm chi phí ghi

Index có cấu trúc đảo có thể tốn công duy trì khi INSERT/UPDATE nhiều tài liệu chứa nhiều lexemes. Dung lượng và write latency phải được cân nhắc.

## 9. GiST là gì trong full-text search?

**GiST (Generalized Search Tree)** là một framework chỉ mục tổng quát có thể hỗ trợ nhiều operator classes. Với `tsvector</BT>, GiST thường dùng **chữ ký bit (signature)** của tập lexemes để mô tả khả năng có mặt của từ.

~~~text
Tài liệu 1: gin, gist, planner
    |
    v
GiST signature: các bit tương ứng được bật

Query: planner
    |
    v
Kiểm tra signature:
  bit phù hợp? -> row CÓ THỂ match
  bit không phù hợp? -> loại
~~~

### 9.1. Tạo GiST index

~~~sql
CREATE INDEX articles_search_gist_idx
ON articles
USING GIST (search_vector);
~~~

### 9.2. GiST tsvector thường là lossy

Nhiều tập lexemes có thể ánh xạ đến những bit trùng nhau. Vì thế index có thể báo **một row là ứng viên dù tsvector thực tế không match query**.

Đây là **false positive trong bước tìm ứng viên**, không có nghĩa PostgreSQL trả sai row cuối cùng. Executor thực hiện recheck khi cần để lọc hàng không khớp.

### 9.3. Điều chỉnh chiều dài signature

Với operator class `tsvector_ops</BT> hỗ trợ tham số phù hợp, có thể thử:

~~~sql
CREATE INDEX articles_search_gist_long_idx
ON articles
USING GIST (
    search_vector tsvector_ops(siglen=256)
);
~~~

Signature dài hơn có thể giảm collisions/false positives, nhưng cũng tăng kích thước index và chi phí tương ứng. Cú pháp/giới hạn tham số phụ thuộc PostgreSQL version và operator class, nên cần kiểm tra trên server đích.

### 9.4. GiST cũng không phải “luôn chậm”

GiST có thể hữu ích ở workload hoặc cấu trúc operator class thích hợp. Với FTS phổ biến, GIN thường là lựa chọn tốt để bắt đầu, nhưng kết luận cuối phải đến từ phép đo truy vấn và chi phí ghi thực tế.

## 10. So sánh GIN và GiST cho tsvector

| Tiêu chí | GIN | GiST |
|---|---|---|
| Ý tưởng | Inverted mapping lexeme → rows | Chữ ký gần đúng cho tập lexemes |
| Full-text search | Thường được ưu tiên | Có thể sử dụng |
| False positives do signature | Không theo cách signature GiST | Có thể xảy ra |
| Recheck phrase/weight | Có thể cần | Có thể cần, và thường do chữ ký |
| Chi phí INSERT/UPDATE | Có thể cao với nhiều lexemes | Có đặc tính trade-off khác |
| Dung lượng | Phụ thuộc lexemes/postings | Phụ thuộc signatures/structure |
| Tùy chỉnh siglen | Không phải tham số signature kiểu GiST | Có thể có `siglen</BT> |
| Bitmap plan | Thường gặp | Thường gặp |
| Trả kết quả theo relevance sẵn | Không | Không |
| Cho substring `ILIKE '%abc%'</BT> mặc định | Không với tsvector_ops | Không với tsvector_ops |
| Phụ thuộc operator class | Có | Có |
| Chọn theo workload | Đo cả read và write | Đo false positives và write |

**Không nên so sánh GIN/GiST như hai câu lệnh “một nhanh, một chậm” trên mọi dữ liệu.** Cần biết GIN/GiST đang dùng operator class nào, query operator nào, dữ liệu phân phối ra sao và tần suất cập nhật.

## 11. Operator class: GIN/GiST không tự hiểu mọi phép so khớp

Một PostgreSQL index không chỉ có access method `GIN</BT> hay `GIST</BT>. Nó còn dùng một **operator class** chỉ ra những kiểu operator có thể được index hỗ trợ.

Ví dụ:

~~~sql
CREATE INDEX articles_search_gin_idx
ON articles USING GIN(search_vector);
~~~

Với `tsvector</BT>, PostgreSQL chọn operator class phù hợp cho FTS.

Nhưng nếu tạo GIN với `gin_trgm_ops</BT> trên một cột text để tăng tốc `ILIKE</BT>, đó là một cơ chế tìm kiếm **khác**: key là trigrams, không phải FTS lexeme tree.

### 11.1. Không dùng nhầm operator

- FTS: `tsvector @@ tsquery</BT>.
- Trigram search: `LIKE</BT>, `ILIKE</BT> hoặc similarity operators tùy extension/operator class.
- Equality trên khóa ID: thường xem B-tree.

### 11.2. Một GIN index không giải mọi text predicate

GIN(tsearch_vector) không mặc định giúp `body ILIKE '%gin%'</BT> nếu query không dùng biểu thức/operator được index hỗ trợ.

### 11.3. Full text không mặc định fuzzy matching

FTS tra lexemes sau xử lý từ điển. Gõ nhầm chữ, biến thể dấu và substring giữa từ có thể cần lớp xử lý bổ sung.

## 12. Vì sao query có thể cần recheck?

Một truy vấn FTS có thể diễn ra:

~~~text
Bitmap Index Scan (GIN/GiST)
        |
        v
Ứng viên từ index
        |
        v
Bitmap Heap Scan
  - Recheck Cond
  - loại false positives nếu có
        |
        v
Kết quả chính xác của @@
~~~

### 12.1. Recheck với GiST

GiST signatures có thể bật những bit trùng cho lexemes khác nhau. Executor cần kiểm tra tsvector gốc để xác nhận ứng viên thực sự thỏa query.

### 12.2. Recheck với GIN

GIN lexeme postings có thể đủ thông tin cho những điều kiện cơ bản, nhưng phrase/positions và weights không được lưu đầy đủ trong index nên có thể cần đọc row và recheck điều kiện đầy đủ.

### 12.3. Bitmap lossiness là nguyên nhân khác

Khi bitmap heap scan bị giới hạn bởi bộ nhớ, nó có thể lưu **lossy bitmap pages** thay vì từng TID chính xác. Khi đó recheck có thể cần thiết vì lý do **bitmap memory**, độc lập với chuyện GiST dùng signature.

### 12.4. Recheck không đồng nghĩa trả kết quả sai

Những false positives trong bước ứng viên sẽ bị loại trước khi query hoàn tất theo semantics được bảo đảm. Người dùng không nên thấy những row không match chỉ vì index GiST lossy.

### 12.5. Đọc EXPLAIN đúng

Dòng `Recheck Cond</BT> tự thân **không chứng minh số lượng false positives thực tế**. Hãy xem `Rows Removed by Index Recheck</BT>, `Heap Blocks: exact/lossy</BT> và bối cảnh node trong `EXPLAIN (ANALYZE, BUFFERS)</BT>.

## 13. Lab: chuẩn bị database và bảng kiểm chứng

Các lệnh tiếp theo dùng **database thử nghiệm** với schema riêng. Không chạy DDL/DROP trên production. Nếu schema `search_lab</BT> đã có dữ liệu, dùng tên khác thay vì xóa.

### 13.1. Tạo schema

~~~sql
CREATE SCHEMA search_lab;
~~~

### 13.2. Tạo bảng tài liệu

~~~sql
CREATE TABLE search_lab.articles (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'published')),
    published_at TIMESTAMPTZ NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector('simple'::regconfig, coalesce(title, '')),
            'A'
        )
        ||
        setweight(
            to_tsvector('simple'::regconfig, coalesce(body, '')),
            'B'
        )
    ) STORED
);
~~~

**Lưu ý phiên bản:** Stored generated columns được hỗ trợ từ PostgreSQL 12. Cú pháp này dùng hàm/biểu thức được PostgreSQL cho phép trong generated expression, và cấu hình `simple</BT> được khai báo rõ. Nếu dùng PostgreSQL cũ, cần hướng lưu/cập nhật vector khác.

### 13.3. Vì sao generated column hữu ích?

Ứng dụng ghi title/body; PostgreSQL tính `search_vector</BT> theo biểu thức được khai báo khi row được ghi/cập nhật. Nhờ đó query chỉ cần đọc vector có sẵn và không phải thực hiện `to_tsvector</BT> trên body cho từng row mỗi lần tìm kiếm.

### 13.4. Trọng số tiêu đề và nội dung

`setweight(...,'A')</BT> cho title và `'B'</BT> cho body giúp query xếp hạng hoặc tìm kiếm có điều kiện weight. **Weight không tự làm index sắp xếp theo relevance**; planner vẫn cần đánh giá điểm khi ORDER BY rank.

## 14. Nạp 60.000 bản ghi thử nghiệm

Để thấy sự khác nhau giữa Seq Scan và index paths, lab tạo nhiều rows hơn vài ví dụ bằng tay.

~~~sql
INSERT INTO search_lab.articles(
    tenant_id, title, body, status, published_at
)
SELECT
    (n % 100) + 1,
    CASE
        WHEN n % 23 = 0
            THEN 'PostgreSQL full text search GIN GiST'
        WHEN n % 7 = 0
            THEN 'Hoc Java voi PostgreSQL'
        ELSE
            'Tai lieu nghiep vu so ' || n::text
    END,
    CASE
        WHEN n % 23 = 0
            THEN 'gin gist index planner explain tsquery tsvector'
        WHEN n % 7 = 0
            THEN 'jdbc java connection query'
        ELSE
            'ghi chu van hanh thong ke ban ghi'
    END,
    CASE
        WHEN n % 5 = 0 THEN 'draft'
        ELSE 'published'
    END,
    TIMESTAMPTZ '2026-01-01 00:00+00'
      + n * INTERVAL '1 minute'
FROM generate_series(1, 60000) AS gs(n);
~~~

### 14.1. Những điều kiện đang có trong dữ liệu

- Khoảng 1/23 số hàng có cụm lexemes liên quan GIN, GiST và planner.
- Nhiều hàng khác có `postgresql</BT> trong tiêu đề nhưng không chứa `planner</BT>.
- `status</BT> có hai giá trị.
- `tenant_id</BT> có 100 giá trị.
- `published_at</BT> là timestamp để có thể kết hợp lọc thời gian.

Đây là dữ liệu **tổng hợp**, với phân phối nhân tạo theo modulo. Không suy rộng trực tiếp kết quả thời gian của lab sang production.

### 14.2. Cập nhật thống kê

~~~sql
ANALYZE search_lab.articles;
~~~

Planner sử dụng thống kê để ước lượng số row match. Chưa có GIN/GiST, nhưng thống kê vẫn giúp lựa chọn đường truy cập khác.

### 14.3. Thử điều kiện

~~~sql
SELECT COUNT(*)
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'gin planner');
~~~

Số hàng thực tế sẽ liên quan đến phân phối sinh dữ liệu và các lexemes, không phải một giá trị cố định theo mọi cấu hình ngoài lab.

## 15. Đo baseline khi chưa có GIN/GiST

Chạy query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'planner');
~~~

Vì lab chưa tạo index FTS, planner có thể chọn `Seq Scan</BT> hoặc `Parallel Seq Scan</BT> tùy cấu hình và kích thước.

### 15.1. Ghi những gì?

| Chỉ số | Ý nghĩa |
|---|---|
| `Seq Scan</BT> | Quét relation theo phương án sequential |
| `Filter</BT> | Điều kiện được áp dụng sau khi đọc row |
| `Rows Removed by Filter</BT> | Số row bị loại bởi filter tại node |
| `rows=...</BT> | Ước lượng số row của planner |
| `actual rows=...</BT> | Số row thực tế được node trả |
| `Buffers: shared hit/read</BT> | Các buffer blocks được truy cập từ cache/đọc |
| `Planning Time</BT> | Thời gian lập kế hoạch |
| `Execution Time</BT> | Thời gian thực thi |

### 15.2. Chạy đo nhiều lần

Lần đầu có thể chịu chi phí cache lạnh; lần sau nhiều pages đã nằm trong shared buffers hoặc cache hệ điều hành. Đừng kết luận index nhanh gấp bao nhiêu chỉ từ một phép đo.

### 15.3. Giữ nguyên câu query khi so sánh

Nếu baseline là `'planner'</BT> mà sau khi tạo index bạn đo `'postgresql'</BT>, hai query khác selectivity và không phải so sánh trực tiếp hợp lệ.

## 16. Thử GIN index trong lab

### 16.1. Tạo index

~~~sql
CREATE INDEX articles_search_gin_idx
ON search_lab.articles
USING GIN(search_vector);
~~~

### 16.2. Cập nhật thống kê khi cần

~~~sql
ANALYZE search_lab.articles;
~~~

`CREATE INDEX</BT> khác `ANALYZE</BT>; việc có index không bảo đảm statistics đã mô tả đúng dữ liệu.

### 16.3. Chạy lại cùng query

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'planner');
~~~

Một kế hoạch dùng GIN có thể có dạng khái niệm:

~~~text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ ...)
  Heap Blocks: exact=...
  -> Bitmap Index Scan on articles_search_gin_idx
       Index Cond: (search_vector @@ ...)
~~~

Đây là **sơ đồ ví dụ**, không phải output cố định. PostgreSQL có thể chọn plan khác khi bảng nhỏ, từ phổ biến hoặc tùy settings.

### 16.4. Index Cond là dấu hiệu quan trọng

Nếu `Bitmap Index Scan on articles_search_gin_idx</BT> có `Index Cond</BT> trên `@@</BT>, planner đang dùng GIN để lấy candidates.

### 16.5. So sánh với baseline

So các chỉ số:

- Execution time qua nhiều lần.
- Buffers đọc/hit.
- Estimated vs actual rows.
- Heap blocks được truy cập.
- Số candidate và rechecks.
- Planning time.
- Memory/temp nếu có.

**Không kết luận GIN hiệu quả chỉ từ việc nó được dùng; phải đo lượng công việc giảm trên workload thật.**

## 17. Thử GiST index để so sánh

Để so sánh công bằng và không có hai indexes cùng phục vụ một predicate làm planner tự chọn khó dự đoán, thực hiện trên **database lab** theo trình tự.

### 17.1. Ghi lại kết quả GIN trước

Lưu output và các thông số ở phần trước.

### 17.2. Bỏ index GIN vừa tạo trong lab

~~~sql
DROP INDEX search_lab.articles_search_gin_idx;
~~~

Chỉ thực hiện lệnh này với index **tự tạo trong database thử nghiệm**, không dùng trên production.

### 17.3. Tạo GiST

~~~sql
CREATE INDEX articles_search_gist_idx
ON search_lab.articles
USING GIST(search_vector);

ANALYZE search_lab.articles;
~~~

### 17.4. Chạy lại query giống hệt

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'planner');
~~~

Một kế hoạch có thể có `Bitmap Index Scan on articles_search_gist_idx</BT> và `Bitmap Heap Scan</BT> cần recheck.

### 17.5. Chú ý false positives

Vì GiST tsvector dùng signature lossy, số candidates có thể nhiều hơn matches thật. Quan sát `Rows Removed by Index Recheck</BT> trong plan nếu được hiển thị.

### 17.6. Khôi phục GIN để tiếp tục lab

~~~sql
DROP INDEX search_lab.articles_search_gist_idx;

CREATE INDEX articles_search_gin_idx
ON search_lab.articles
USING GIN(search_vector);
~~~

Những phần sau giả định GIN đã được tạo lại. Nếu muốn khảo sát GiST signature dài hơn, dùng một database test khác hoặc thay index GiST tại đúng giai đoạn so sánh.

## 18. GiST signature dài hơn có thể giảm false positives

Với operator class và phiên bản phù hợp, thử một index GiST:

~~~sql
CREATE INDEX articles_search_gist_sig256_idx
ON search_lab.articles
USING GIST (
    search_vector tsvector_ops(siglen=256)
);
~~~

### 18.1. Mục tiêu của siglen

Signature dài hơn có thể giảm bit collisions, do đó giảm số rows cần recheck không match. Nhưng index có thể lớn hơn và có trade-off ở write/index maintenance.

### 18.2. Kiểm tra thay vì đoán

So:

- Index size.
- Rows Removed by Index Recheck.
- Buffers/heap blocks.
- Execution time.
- DML overhead khi workload cập nhật.

### 18.3. Không nên giữ cả ba indexes mặc định

Trong production, tạo nhiều indexes gần như trùng nhau làm tăng chi phí INSERT/UPDATE và storage. Lab có thể thử nhiều index để học; thiết kế thật nên chọn theo workload đo được.

### 18.4. Chú ý điều kiện phiên bản

Một số operator-class options, cú pháp và giới hạn giá trị khác nhau theo PostgreSQL version. Xác nhận tính năng trên server đang triển khai trước khi đưa vào migration.

## 19. Đọc EXPLAIN: Seq Scan, Index Scan, Bitmap Scan

### 19.1. Seq Scan

~~~text
Seq Scan on articles
  Filter: (search_vector @@ ...)
~~~

PostgreSQL đọc các hàng của relation và đánh giá filter.

### 19.2. Bitmap Index Scan

~~~text
Bitmap Index Scan on articles_search_gin_idx
  Index Cond: (search_vector @@ ...)
~~~

Node này truy cập index để tạo các TIDs/page candidates trong bitmap.

### 19.3. Bitmap Heap Scan

~~~text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ ...)
  Heap Blocks: exact=... lossy=...
~~~

Node truy cập heap pages ứng viên và xác nhận điều kiện khi cần.

### 19.4. Index Scan

Một số access methods và query shapes có thể dẫn tới Index Scan hoặc kế hoạch có sử dụng index khác. Nhưng với GIN full-text search, Bitmap Index Scan + Bitmap Heap Scan là hình dạng thường gặp; không bắt buộc mọi kế hoạch phải có node `Index Scan</BT> mới được coi là sử dụng index.

### 19.5. Parallel Seq Scan

Một query tìm lexeme quá phổ biến có thể dùng Parallel Seq Scan nếu planner ước tính đọc phần lớn bảng rẻ hơn dùng index rồi truy cập nhiều heap pages.

**Tên plan node tự nó chưa đủ để đánh giá chất lượng.**

## 20. Recheck Cond và Rows Removed by Index Recheck

Trong một kế hoạch:

~~~text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ 'planner'::tsquery)
  Rows Removed by Index Recheck: 120
  Heap Blocks: exact=950
  -> Bitmap Index Scan ...
~~~

Dòng này chỉ là ví dụ minh họa, không phải kết quả chạy lab.

### 20.1. Recheck Cond

Thể hiện điều kiện mà heap scan có thể phải xác minh lại. Nó không có nghĩa mọi row ứng viên đều là false positive.

### 20.2. Rows Removed by Index Recheck

Cho thấy số rows bị loại do **kiểm tra điều kiện index ở cấp heap**. Với GiST signatures, con số này giúp nhìn rõ false positives. Với lossy bitmap pages cũng có thể xuất hiện recheck removals.

### 20.3. Heap Blocks exact và lossy

- **exact**: bitmap lưu đủ thông tin TID cụ thể cho heap block.
- **lossy**: bitmap thể hiện page có candidates nhưng không giữ chính xác mọi TIDs; executor cần kiểm tra nhiều tuples hơn.

### 20.4. Hai loại “lossy” không đồng nhất

- GiST signature lossy do hash bit collisions.
- Bitmap heap scan lossy do cách lưu trữ bitmap khi bị giới hạn tài nguyên.

Cả hai có thể dẫn tới recheck, nhưng cần phân biệt nguyên nhân khi tối ưu.

### 20.5. Không có recheck removals không chứng minh index không lossy

Nếu dữ liệu/query hiện tại không có collision hoặc bitmap không mất độ chính xác, có thể không có row bị loại dù GiST dùng signature. Đây là thống kê của một lần chạy, không phải tuyên bố tính chất tổng quát của index.

## 21. AND, OR và điều kiện phủ định trong FTS

### 21.1. Từ phải xuất hiện đồng thời

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'gin & planner');
~~~

Trên dữ liệu lab, nhóm bài có đầy đủ hai lexemes tương đối nhỏ.

### 21.2. Một trong hai từ

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'gin | postgresql');
~~~

OR có thể match nhiều hàng hơn AND. Khi selectivity cao, planner có thể chọn Seq Scan vì index không còn tiết kiệm bao nhiêu heap reads.

### 21.3. NOT không thay toàn bộ truy vấn chọn lọc

~~~sql
SELECT article_id
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'postgresql & !deprecated'
);
~~~

Một phủ định đơn độc có thể match phần lớn bảng hoặc khó sử dụng index hiệu quả. Nên xem ngữ nghĩa và độ chọn lọc thay vì kỳ vọng mọi NOT đều tạo index lookup nhanh.

### 21.4. Toán tử đúng cú pháp

`plainto_tsquery</BT> xử lý plain text chứ không có cùng semantics với một `to_tsquery</BT> chứa AND/OR/NOT operators. Không tráo hai hàm mà không kiểm tra query được tạo.

## 22. Phrase search và vị trí lexemes

So sánh hai tài liệu:

~~~text
A: "gin gist planner"
B: "gin index is different from gist"
~~~

Cả hai có thể chứa gin và gist, nhưng chỉ A có hai từ đứng liền nhau.

### 22.1. AND search

~~~sql
SELECT *
FROM search_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'gin & gist');
~~~

### 22.2. Phrase search

~~~sql
SELECT *
FROM search_lab.articles
WHERE search_vector @@ phraseto_tsquery('simple', 'gin gist');
~~~

### 22.3. Vì sao cần heap recheck với GIN?

GIN index trên tsvector không chứa toàn bộ vị trí các lexemes để tự quyết định mọi phrase relation. Nó có thể tìm candidates chứa các từ, rồi PostgreSQL cần xác minh phrase condition với tsvector của row.

### 22.4. Query có stopwords

Cách `phraseto_tsquery</BT> xử lý stop words và các khoảng cách trong phrase phụ thuộc text search configuration. Không kết luận phrase matching chỉ bằng số ký tự giữa các từ trong text gốc.

### 22.5. Ngữ nghĩa quan trọng hơn tốc độ

Nếu người dùng muốn tài liệu có **cả gin và gist ở bất kỳ vị trí nào**, dùng phrase query sẽ trả ít tài liệu hơn kỳ vọng. Hãy chọn toán tử theo trải nghiệm tìm kiếm mong muốn.

## 23. Weight restrictions và recheck

Vector lab cho title trọng số A và body trọng số B.

### 23.1. Chỉ tìm lexeme trong tiêu đề

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'postgresql:A'
);
~~~

### 23.2. Chỉ tìm lexeme ở body

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'planner:B'
);
~~~

### 23.3. Vì sao GIN vẫn cần kiểm tra?

GIN FTS index không lưu đầy đủ trọng số nên có thể tìm row chứa lexeme nhưng cần recheck xem lexeme có weight yêu cầu không.

### 23.4. Trọng số không tự thành index về ranking

Ngay cả với title A và body B, GIN không tự trả kết quả theo “điểm cao nhất”. Ranking cần một bước tính trên các matches.

## 24. Ranking: ts_rank và ts_rank_cd

Một search UI thường muốn kết quả có độ liên quan cao nhất trước.

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple',
        'postgresql gin'
    ) AS query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.query) AS score
FROM search_lab.articles AS a
CROSS JOIN q
WHERE a.search_vector @@ q.query
ORDER BY score DESC, a.article_id
LIMIT 20;
~~~

### 24.1. Index lọc, rank sắp xếp

GIN/GiST trên tsvector thường giúp tìm candidate documents. `ts_rank</BT> tính điểm từ vector và query; executor có thể phải tính score cho các rows match rồi sort/Top-N.

### 24.2. ts_rank_cd

`ts_rank_cd</BT> sử dụng một cách đánh giá mức độ gần nhau của lexemes (cover density) và có hành vi khác `ts_rank</BT>. Không có hàm ranking tốt nhất tuyệt đối; chọn theo nhu cầu relevance.

### 24.3. ORDER BY thêm cột tie-breaker

Dùng `ORDER BY score DESC, article_id</BT> giúp kết quả có thứ tự xác định khi scores bằng nhau. Điều này hữu ích cho pagination.

### 24.4. Ranking có thể đắt

Nếu query match một triệu hàng rồi LIMIT 20, PostgreSQL vẫn có thể cần đánh giá nhiều matches để tìm top 20. Một GIN index không tự tương đương “top 20 theo score được trả ngay”.

### 24.5. Filtering sớm

Kết hợp status/tenant/time predicates và thiết kế index phù hợp có thể giảm số candidate cần rank. Không chỉ tăng kích thước FTS index để giải bài toán kết quả quá rộng.

## 25. Generated tsvector so với expression index

Có hai hướng thiết kế phổ biến.

### 25.1. Stored generated column

Lab đã dùng:

~~~sql
search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('simple'::regconfig, coalesce(title, '')), 'A')
    ||
    setweight(to_tsvector('simple'::regconfig, coalesce(body, '')), 'B')
) STORED
~~~

Sau đó index trực tiếp:

~~~sql
CREATE INDEX articles_search_gin_idx
ON search_lab.articles USING GIN(search_vector);
~~~

**Ưu điểm:** query dễ viết, vector có sẵn cho ranking/kiểm tra; logic được quản lý một nơi trong schema.

**Chi phí:** thêm dung lượng cột vector và việc tính lại khi dữ liệu liên quan thay đổi.

### 25.2. Expression index

Có thể không lưu vector thành cột riêng:

~~~sql
CREATE INDEX articles_expr_gin_idx
ON search_lab.articles
USING GIN(
    to_tsvector(
        'simple'::regconfig,
        coalesce(title, '') || ' ' || coalesce(body, '')
    )
);
~~~

Đây là một **index bổ sung để minh họa**. Không nên tạo trùng nếu production đã có generated-column GIN phục vụ cùng workload.

### 25.3. Query phải khớp biểu thức phù hợp

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE to_tsvector(
    'simple'::regconfig,
    coalesce(title, '') || ' ' || coalesce(body, '')
) @@ plainto_tsquery('simple', 'gin gist');
~~~

Planner có thể tận dụng expression index khi biểu thức/operator và ngữ nghĩa phù hợp.

### 25.4. Mismatch có thể làm index không được dùng

Nếu index trên `to_tsvector('simple', body)</BT> nhưng query là `to_tsvector('english', body)</BT> hoặc một biểu thức khác, không được giả định planner sẽ tự dùng index đó.

### 25.5. Hàm trong expression index cần hợp lệ

PostgreSQL yêu cầu biểu thức được lập chỉ mục đáp ứng quy tắc immutability. Việc sử dụng phiên bản `to_tsvector(regconfig, text)</BT> với **cấu hình cố định** giúp diễn đạt rõ semantics; một biểu thức phụ thuộc cấu hình session không có cùng hợp đồng.

### 25.6. Generated column khác trigger

Một thiết kế cũ có thể dùng trigger tự cập nhật `tsvector</BT> từ title/body. Generated column có ưu điểm đồng bộ khai báo, nhưng version support, yêu cầu expressions và nhu cầu tùy biến có thể khiến trigger vẫn phù hợp trong một số trường hợp.

## 26. Một ví dụ lỗi: không khớp cấu hình text search

Giả sử:

~~~sql
CREATE INDEX articles_body_simple_gin
ON search_lab.articles
USING GIN (
    to_tsvector('simple'::regconfig, body)
);
~~~

Truy vấn:

~~~sql
SELECT article_id
FROM search_lab.articles
WHERE to_tsvector(
    'english'::regconfig,
    body
) @@ plainto_tsquery('english', 'search');
~~~

### 26.1. Vấn đề

Index được định nghĩa trên **simple(body)**, trong khi query dùng **english(body)**. Đây là biểu thức và cách xử lý từ vựng khác nhau; không thể mặc định index trên simple phục vụ english.

### 26.2. Hướng giải quyết

- Dùng một cấu hình nhất quán cho tính năng tìm kiếm cụ thể.
- Tạo index đúng biểu thức/config thực tế.
- Nếu nhiều ngôn ngữ, thiết kế vector/index phù hợp từng nhóm tài liệu.
- Đọc EXPLAIN để xác minh operator/index được planner sử dụng.

### 26.3. Không đổi config chỉ để làm plan có index

Nếu tiếng Anh cần stemming nhưng bạn đổi hết sang simple cho query dùng index, kết quả FTS có thể thay đổi sai nhu cầu. Trước tiên chọn **ngữ nghĩa đúng**, sau đó tạo index phục vụ ngữ nghĩa đó.

## 27. Partial GIN index: chỉ đánh chỉ mục hàng cần tìm

Một ứng dụng chỉ tìm những bài đã xuất bản:

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE status = 'published'
  AND search_vector @@ plainto_tsquery('simple', 'postgresql');
~~~

Có thể xem xét partial GIN:

~~~sql
CREATE INDEX articles_published_gin_idx
ON search_lab.articles
USING GIN(search_vector)
WHERE status = 'published';
~~~

### 27.1. Lợi ích có thể có

- Index nhỏ hơn nếu draft chiếm tỷ lệ đáng kể.
- Index maintenance chỉ cần với rows thuộc predicate theo semantics partial index.
- Truy vấn published có thể có access path phù hợp.

### 27.2. Điều kiện để sử dụng

Planner phải chứng minh predicate của query **hàm ý** điều kiện partial index, chẳng hạn `status='published'</BT> theo cú pháp/logic phù hợp.

### 27.3. Prepared/generic plans

Nếu query là `WHERE status = $1</BT>, một generic plan không biết giá trị `$1</BT> có thể không chứng minh được điều kiện status luôn là published. Do đó partial index đôi khi không được dùng dù application thường truyền giá trị published.

### 27.4. Không giữ nhiều index trùng mục đích vô hạn

Index full-vector GIN và partial published GIN có thể cùng được planner cân nhắc. Đo cả write overhead và kích thước; chỉ giữ cả hai nếu workload thật biện minh.

## 28. Kết hợp FTS với tenant, status và thời gian

Query thực tế thường là:

~~~sql
SELECT article_id, title, published_at
FROM search_lab.articles
WHERE tenant_id = 42
  AND status = 'published'
  AND published_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
  AND search_vector @@ plainto_tsquery('simple', 'postgresql');
~~~

### 28.1. Một FTS index không đáp ứng mọi predicate

GIN trên search_vector chỉ hỗ trợ phần FTS theo operator class. PostgreSQL có thể phải lọc tenant/status/time ở heap.

### 28.2. B-tree hỗ trợ điều kiện cấu trúc

~~~sql
CREATE INDEX articles_tenant_time_idx
ON search_lab.articles (
    tenant_id,
    published_at
);
~~~

### 28.3. BitmapAnd hoặc phương án khác

Trong một số trường hợp planner có thể kết hợp bitmap từ nhiều indexes, hoặc chọn một index rồi filter điều kiện còn lại. Không bảo đảm mọi query có hai indexes sẽ dùng BitmapAnd; điều đó phụ thuộc chi phí, độ chọn lọc và thống kê.

### 28.4. Chọn đường truy cập bắt đầu từ predicate chọn lọc

Nếu tenant 42 chỉ có một nghìn tài liệu, B-tree tenant có thể thu hẹp dữ liệu rất mạnh rồi đánh giá FTS. Nếu tenant có hàng chục triệu tài liệu và từ hiếm, GIN có thể thuận lợi hơn.

### 28.5. Không gắn mọi cột vào một index bừa bãi

Multicolumn GIN và các operator classes bổ sung tồn tại trong những ngữ cảnh cụ thể, nhưng không nên mặc định có thể thêm mọi kiểu dữ liệu và mọi operator vào một index chuẩn mà không cần extension/opclass phù hợp.

## 29. pg_trgm: GIN/GiST nhưng khác full-text search

Nếu user muốn tìm chuỗi con hoặc fuzzy similarity, extension `pg_trgm</BT> thường đáng cân nhắc.

### 29.1. Cài extension trong môi trường được phép

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

Lệnh này yêu cầu quyền và có thể bị giới hạn bởi chính sách database/server.

### 29.2. Trigram GIN index

~~~sql
CREATE INDEX articles_title_trgm_idx
ON search_lab.articles
USING GIN (title gin_trgm_ops);
~~~

### 29.3. Trigram GiST index

Một lựa chọn khác:

~~~sql
CREATE INDEX articles_title_trgm_gist_idx
ON search_lab.articles
USING GIST (title gist_trgm_ops);
~~~

Không nên tạo cả hai trên production nếu chưa so nhu cầu/chi phí.

### 29.4. Query phù hợp

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE title ILIKE '%postgres%';
~~~

Trigram index có thể hỗ trợ ILIKE pattern phù hợp theo opclass.

### 29.5. Sự khác biệt ngữ nghĩa

| Nhu cầu | Công cụ đáng cân nhắc |
|---|---|
| Tìm tài liệu có lexemes, stemming, phrase | FTS tsvector/tsquery + GIN/GiST |
| Chuỗi con tùy vị trí | pg_trgm + GIN/GiST |
| Gõ gần đúng, lỗi chính tả đơn giản | pg_trgm similarity |
| Khớp ID/keyword nguyên vẹn | B-tree hoặc phép so sánh phù hợp |
| Tìm địa lý/spatial | GiST với operator class phù hợp, không phải tsvector |

**Access method giống nhau không làm hai operator classes có cùng ngữ nghĩa.**

## 30. Tại sao planner không dùng GIN/GiST?

Một số nguyên nhân:

1. Bảng quá nhỏ, Seq Scan rẻ hơn.
2. Lexeme rất phổ biến; query trả phần lớn rows.
3. Thống kê stale hoặc ước lượng selectivity không phù hợp.
4. Query không dùng `@@</BT> tương ứng.
5. Index nằm trên biểu thức/config khác với query.
6. Query dùng `ILIKE</BT> nhưng index là GIN tsvector_ops.
7. Partial index predicate không được chứng minh từ WHERE.
8. Generic prepared plan không có đủ constants.
9. Query có nhiều joins/filters khiến access path khác có lợi hơn.
10. Planner ước tính random heap fetches đắt hơn sequential scan.
11. Ranking/sort chi phối tổng chi phí, index không giải hết.
12. Index chưa được tạo, bị invalid hoặc không tồn tại ở relation đang truy vấn.
13. Bảng partitioned nhưng index không nằm trên leaf phù hợp.
14. Query parse ra rỗng hoặc khác kỳ vọng do config/stop words.
15. Predicate rất phức tạp/OR khiến một phần không indexable.

### 30.1. Không kết luận index hỏng chỉ vì Seq Scan

Planner chọn phương án dự kiến rẻ nhất. Với bảng 100 rows, Seq Scan thường là lựa chọn hoàn toàn hợp lý.

### 30.2. Cách chẩn đoán

- `SHOW default_text_search_config</BT>.
- Xem index definition trong `pg_indexes</BT>.
- Kiểm tra query thực đang dùng `@@</BT>.
- Dùng `EXPLAIN (ANALYZE, BUFFERS)</BT>.
- So estimated rows và actual rows.
- Chạy `ANALYZE</BT> nếu dữ liệu thay đổi nhiều.
- Kiểm tra query text, generated vector và lexemes.

## 31. Kiểm tra index definitions

### 31.1. pg_indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'search_lab'
  AND tablename = 'articles'
ORDER BY indexname;
~~~

### 31.2. Đọc indexdef

Xem:

- `USING gin</BT> hay `USING gist</BT>.
- Cột `search_vector</BT> hay expression `to_tsvector(...)</BT>.
- Operator class nếu được chỉ định.
- Partial predicate `WHERE ...</BT>.
- Số indexes cùng chức năng.

### 31.3. Xem metadata trực tiếp khi cần

`pg_class</BT>, `pg_index</BT>, `pg_am</BT> và `pg_opclass</BT> chứa metadata nội bộ của index. Đối với nhu cầu thông thường, `pg_indexes</BT> dễ đọc và đủ để đối chiếu định nghĩa.

## 32. Đo kích thước và tần suất sử dụng index

### 32.1. Index sizes

~~~sql
SELECT
    indexname,
    pg_size_pretty(
        pg_relation_size(
            (quote_ident(schemaname) || '.' ||
             quote_ident(indexname))::regclass
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'search_lab'
  AND tablename = 'articles'
ORDER BY indexname;
~~~

### 32.2. pg_stat_user_indexes

~~~sql
SELECT
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch
FROM pg_stat_user_indexes AS s
WHERE s.schemaname = 'search_lab'
  AND s.relname = 'articles'
ORDER BY s.indexrelname;
~~~

### 32.3. Hiểu đúng các chỉ số

- `idx_scan</BT>: số lần bắt đầu index scans theo semantics thống kê.
- `idx_tup_read</BT>: index entries/tuples được đọc ở mức phù hợp.
- `idx_tup_fetch</BT>: heap tuples được tìm nạp theo semantics view, **không phải bộ đếm toàn bộ rows được trả bởi mọi Bitmap Heap Scan**.

Cần đọc tài liệu phiên bản nếu diễn giải chi tiết các counter, đặc biệt khi query dùng bitmap scans.

### 32.4. Counter thấp không luôn nghĩa index vô dụng

Một index có thể phục vụ query quan trọng chạy hiếm nhưng bắt buộc nhanh. Đừng DROP chỉ vì idx_scan thấp trong một khoảng thời gian ngắn, không xét stats reset, deployment và workload.

## 33. Chi phí duy trì GIN: fastupdate và pending list

GIN có khả năng sử dụng **pending list** để giảm chi phí trực tiếp của nhiều INSERT/UPDATE nhỏ, nhờ tính năng `fastupdate</BT>.

### 33.1. fastupdate

~~~sql
ALTER INDEX search_lab.articles_search_gin_idx
SET (fastupdate = on);
~~~

Đây là ví dụ thay index trong lab; ở production phải đánh giá ghi, đọc và maintenance.

### 33.2. Pending list là gì?

Khi fastupdate bật, những entries mới có thể vào một pending list trước khi được nhập vào main GIN structure. Cách này có thể giảm latency trung bình của writes, nhưng làm mỗi query phải xét thêm pending entries và có thể tạo các đợt dọn pending list.

### 33.3. Cleanup

Autovacuum/VACUUM và các cơ chế cleanup hỗ trợ xử lý pending list. Một số phiên bản có hàm:

~~~sql
SELECT gin_clean_pending_list(
    'search_lab.articles_search_gin_idx'::regclass
);
~~~

Chỉ dùng khi có lý do vận hành; việc cleanup có thể tốn I/O và ảnh hưởng latency.

### 33.4. gin_pending_list_limit

Có thể điều chỉnh `gin_pending_list_limit</BT> ở cấp cấu hình/index theo khả năng được hỗ trợ. Giới hạn này ảnh hưởng thời điểm/khối lượng dọn pending list, không trực tiếp là giới hạn số rows hoặc số lexemes của tài liệu.

### 33.5. fastupdate=off có phải luôn nhanh hơn?

Không. Khi tắt, mỗi write có thể phải cập nhật cấu trúc chính sớm hơn; workload write-heavy có thể chịu chi phí khác. Đừng đổi chỉ vì thấy pending list tồn tại.

### 33.6. Theo dõi tail latency

Nếu các batches cleanup gây spikes, hãy đo write p95/p99, autovacuum cadence, GIN size, read latency và pending-list behavior trước khi quyết định.

## 34. GiST cũng có trade-off khi ghi

GiST sử dụng cấu trúc search tree và signature representation cho tsvector. Chi phí ghi phụ thuộc dữ liệu, cấu trúc index và kích thước signature.

### 34.1. Không suy luận GiST luôn tốt cho writes

Một index nhỏ hơn trong một phép đo không chắc có write performance tốt hơn trên mọi workload.

### 34.2. Signature dài tăng độ chính xác ứng viên nhưng có giá

Tăng `siglen</BT> có thể giảm false positives nhưng tăng index space và I/O. Cần đánh giá dựa trên data distribution và query workload.

### 34.3. VACUUM và maintenance

Các dạng index vẫn chịu tác động của churn, dead tuples, autovacuum và bloat. Index maintenance là một phần của thiết kế FTS, không thể chỉ đo SELECT.

### 34.4. Chọn GIN hay GiST là quyết định tổng chi phí

Phân tích đồng thời:

- Tỷ lệ SELECT vs INSERT/UPDATE/DELETE.
- Số lexemes trung bình/tài liệu.
- Update frequency của body.
- Query selectivity.
- Latency p95/p99.
- Index size.
- Memory, I/O và autovacuum behavior.

## 35. Bulk load và xây index

Nếu bạn cần nạp một lượng lớn tài liệu mới, thứ tự công việc ảnh hưởng thời gian:

### 35.1. Tạo GIN trước rồi INSERT

Index phải được duy trì khi INSERT, có thể tốn tài nguyên đáng kể.

### 35.2. Nạp dữ liệu vào bảng trước, tạo index sau

Trong một migration/bulk load có kiểm soát, có thể hiệu quả hơn khi COPY/INSERT data rồi mới tạo GIN index. Nhưng cách này không phù hợp nếu hệ thống đang cần search availability hoặc không thể tạm thiếu index.

### 35.3. CREATE INDEX CONCURRENTLY

Với hệ thống đang phục vụ writes, cần xem xét `CREATE INDEX CONCURRENTLY</BT> khi yêu cầu và loại index cho phép, với các hạn chế về transaction block, thời gian và resources. Không giả định nó nhanh hơn CREATE INDEX thường; ưu điểm chính liên quan giảm một số dạng blocking writes trong quá trình xây.

### 35.4. ANALYZE sau nạp

~~~sql
ANALYZE search_lab.articles;
~~~

Statistics mới giúp planner đánh giá số hàng phù hợp sau khi phân phối dữ liệu thay đổi.

### 35.5. Test trên dataset đại diện

60.000 rows trong lab không đủ đại diện cho hàng trăm triệu documents, nhưng có thể dùng để hiểu cú pháp và plan shape. Kiểm chứng sizing trên dữ liệu production-like trước khi chọn phương án bulk load.

## 36. Cập nhật document và search_vector

Với generated column:

~~~sql
UPDATE search_lab.articles
SET title = 'PostgreSQL GIN and query planning'
WHERE article_id = 23;
~~~

PostgreSQL tính lại generated `search_vector</BT> theo biểu thức khai báo khi hàng thay đổi tương ứng. Index FTS được bảo trì để phản ánh vector mới.

### 36.1. Chi phí tăng khi document lớn

Một update body dài có thể thay nhiều lexemes, làm tăng index maintenance và WAL. Hệ thống chat/log với tần suất update liên tục có đặc điểm khác hệ thống bài viết chỉ sửa ít lần.

### 36.2. Cập nhật một cột khác có luôn rẻ?

Phụ thuộc storage, HOT update eligibility, indexes và biểu thức generated. Không nên khẳng định mọi UPDATE chỉ tác động một cột ngoài search_vector luôn không ảnh hưởng FTS index.

### 36.3. Nếu dùng cột tsvector thủ công

Khi application hoặc trigger tự cập nhật vector, phải đảm bảo title/body đổi thì vector cũng đổi đúng transaction. Nếu không, FTS có thể trả kết quả cũ hoặc thiếu hàng dù index được duy trì nhất quán với **vector đã lưu**.

### 36.4. Đừng coi GIN là nguồn sự thật

Chỉ mục phục vụ truy cập dữ liệu. Giá trị search_vector/document và quy tắc update là dữ liệu logic; index có thể được xây lại nhưng không tự sửa một vector do ứng dụng tạo sai.

## 37. FTS đa ngôn ngữ và tiếng Việt

Một hệ thống có cả tiếng Việt/Anh cần xác định **đối với mỗi tài liệu, cấu hình/từ điển nào tạo lexemes**.

### 37.1. Cấu hình theo ngôn ngữ

Có thể lưu language code và tạo vector theo một số cấu hình đã biết. Tuy nhiên, generated expressions và index matching cần tính đến immutability, cấu hình và query predicates; không đơn giản thay session default rồi giả định mọi vectors tự đổi.

### 37.2. Dấu tiếng Việt

Chuỗi có dấu và không dấu có thể không so khớp dưới `simple</BT> nếu không có bước normalize phù hợp. Extension `unaccent</BT> có thể là một phần của pipeline trong một số thiết kế, nhưng phải xem volatility, collation và cách giữ biểu thức index an toàn. Không tự gắn một function wrapper IMMUTABLE nếu thực tế phụ thuộc dictionary/config có thể thay đổi.

### 37.3. Tách từ ghép

Tiếng Việt thường có từ gồm nhiều âm tiết cách nhau bởi khoảng trắng. Parser mặc định có thể xem các âm tiết là token riêng, ảnh hưởng precision/relevance. Có thể cần tokenizer/từ điển chuyên dụng hoặc search engine có hỗ trợ ngôn ngữ thích hợp.

### 37.4. Trải nghiệm người dùng

Nên định nghĩa rõ:

- Có chấp nhận bỏ dấu không?
- Có cần tìm dạng số ít/nhiều?
- Có cần sai chính tả?
- Có cần synonym?
- Có cần phrase đúng thứ tự?
- Có cần prefix/autocomplete?
- Có cần tăng điểm cho title?
- Có cần phân quyền theo tenant/status?

Không có một GIN index duy nhất mặc định giải toàn bộ yêu cầu này.

## 38. Lọc bảo mật và tenant cùng FTS

Một ứng dụng SaaS tìm kiếm bài viết cần đảm bảo không lộ tài liệu tenant khác:

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE tenant_id = 42
  AND status = 'published'
  AND search_vector @@ websearch_to_tsquery(
      'simple',
      'gin gist'
  );
~~~

### 38.1. Chỉ mục không thay authorization

GIN/GiST giúp giảm số hàng đọc, **không tự kiểm soát quyền**. Người dùng cần được xác thực/phân quyền ở ứng dụng và/hoặc RLS, grants phù hợp.

### 38.2. Query RLS có thể ảnh hưởng plan

Row-Level Security thêm các predicates/boundaries cần bảo toàn semantics. Benchmark query bằng superuser có thể cho kế hoạch khác thực tế của application role.

### 38.3. Metadata leak

Tính năng như `ts_headline</BT> có thể trích đoạn từ body. Cần chỉ chạy sau khi đã xác định row được phép truy cập và xử lý output an toàn khi render lên web.

### 38.4. Không để user chọn text search configuration tùy ý nếu thiếu kiểm soát

Cho phép client gửi tên dictionary/config hoặc query syntax SQL bất kỳ có thể gây behavior khó kiểm soát hoặc lộ thông tin về môi trường. Chọn tập cấu hình/kiểu query hợp lệ theo API.

## 39. ts_headline: hiển thị đoạn trích phù hợp

PostgreSQL có hàm:

~~~sql
SELECT
    article_id,
    title,
    ts_headline(
        'simple',
        body,
        plainto_tsquery('simple', 'gin gist')
    ) AS excerpt
FROM search_lab.articles
WHERE search_vector @@ plainto_tsquery('simple', 'gin gist')
LIMIT 10;
~~~

### 39.1. Chỉ tạo excerpt cho hàng đã chọn

Nếu có thể, chọn top N tài liệu trước rồi tính headline cho N rows đó, thay vì gọi ts_headline trên hàng triệu candidates.

### 39.2. Xử lý HTML an toàn

`ts_headline</BT> có thể tạo markup/highlight text, nhưng nó **không được coi là công cụ sanitize HTML** chống XSS. Escape/render an toàn trong ứng dụng; không đưa raw user-controlled HTML vào DOM một cách thiếu kiểm soát.

### 39.3. Highlight không phải ranking

`ts_headline</BT> trình bày đoạn trích; `ts_rank</BT> tính điểm; `@@</BT> lọc matches; GIN/GiST hỗ trợ access path. Đây là bốn chức năng khác nhau.

## 40. Prefix search và autocomplete

FTS hỗ trợ prefix lexeme:

~~~sql
SELECT article_id, title
FROM search_lab.articles
WHERE search_vector @@ to_tsquery(
    'simple',
    'post:*'
);
~~~

### 40.1. Prefix chỉ áp dụng lên lexeme

Không phải mọi substring của một từ sẽ match. Prefix query `post:*</BT> không tương đương `ILIKE '%ost%'</BT>.

### 40.2. Indexability phụ thuộc operator class

GIN/GiST FTS có cơ chế hỗ trợ tsquery operators trong những trường hợp phù hợp. Planner vẫn cân nhắc chi phí và độ chọn lọc. Nếu prefix quá phổ biến, Seq Scan có thể hợp lý.

### 40.3. Autocomplete tên riêng

Nếu yêu cầu gợi ý gần đúng khi người dùng gõ nửa chuỗi, có thể cân nhắc `pg_trgm</BT>, B-tree prefix index trong điều kiện thích hợp hoặc một search service chuyên dụng.

### 40.4. Query input rất ngắn

Từ một hoặc hai ký tự có thể match quá nhiều dữ liệu, khiến query/bộ nhớ/tải I/O tăng. Cần rate limiting, minimum query length theo trải nghiệm ứng dụng và giới hạn kết quả.

## 41. Query không trả hàng: phân biệt dữ liệu và index

Nếu query không trả tài liệu mong đợi:

1. Kiểm tra dữ liệu gốc title/body có chứa từ cần tìm không.
2. Kiểm tra vector đã tạo:

~~~sql
SELECT
    article_id,
    title,
    search_vector
FROM search_lab.articles
WHERE article_id = 23;
~~~

3. Kiểm tra `to_tsvector(config, text)</BT> trực tiếp.
4. Kiểm tra `plainto_tsquery(config, input)</BT> tạo lexemes gì.
5. So config của vector và query.
6. Kiểm tra stop words/stemming/ngôn ngữ/dấu.
7. Kiểm tra Boolean query AND/OR/phrase/weight.
8. Kiểm tra tenant/status/RLS predicates.
9. Kiểm tra dữ liệu vector có stale không nếu dùng trigger/app cập nhật.
10. Kiểm tra bản ghi có commit và visible theo transaction isolation không.

**Có hay không có index thường không thay kết quả logic của một query FTS đúng**; nó thay đổi đường truy cập. Đừng chẩn đoán “kết quả rỗng do GIN bị chậm” khi thực chất vector và query không match.

## 42. Những hiểu lầm phổ biến

### 42.1. “GIN là bắt buộc cho mọi tìm kiếm văn bản”

Sai. Tìm exact value có thể phù hợp B-tree; substring/fuzzy có thể phù hợp pg_trgm; FTS thường dùng GIN/GiST trên tsvector.

### 42.2. “GiST luôn trả kết quả sai vì lossy”

Sai. Signature có thể tạo candidates false-positive, nhưng executor recheck theo ngữ nghĩa của operator.

### 42.3. “GIN không bao giờ cần recheck”

Sai. Phrase/weight conditions hoặc bitmap lossiness có thể cần kiểm tra lại.

### 42.4. “Recheck Cond nghĩa tất cả rows ở node đều không chính xác”

Sai. Nó biểu thị điều kiện có thể cần xác minh; phải xem rows removed.

### 42.5. “GiST signature càng dài thì index càng nhanh trong mọi query”

Sai. Signature dài giảm collisions tiềm năng nhưng tăng storage và một số chi phí khác.

### 42.6. “Có GIN thì PostgreSQL không bao giờ dùng Seq Scan”

Sai. Small tables, common lexemes và cost estimates có thể khiến Seq Scan rẻ hơn.

### 42.7. “GIN tự sắp xếp kết quả theo ts_rank”

Sai. Ranking phải được tính và order phù hợp.

### 42.8. “ILIKE và @@ có cùng ngữ nghĩa”

Sai. Substring matching khác lexical FTS matching.

### 42.9. “GIN tsvector index sẽ giúp ILIKE '%abc%'”

Không mặc định. Đó là kiểu predicate khác; cân nhắc pg_trgm.

### 42.10. “Mọi GIN index có cùng operator class”

Sai. GIN tsvector và GIN trigram khác key/operator semantics.

### 42.11. “Chọn simple/english tùy ý không ảnh hưởng kết quả”

Sai. Text search configurations ảnh hưởng lexemes, stemming và stop words.

### 42.12. “Generated column không tốn dung lượng hay chi phí ghi”

Sai. Vector được lưu và bảo trì khi cập nhật dữ liệu liên quan.

### 42.13. “Expression index và generated-column index chắc chắn giống nhau”

Không nhất thiết. Chúng có storage và query matching semantics khác nhau; cần xem biểu thức thực và kế hoạch.

### 42.14. “Nếu query không dùng index thì chỉ cần SET enable_seqscan=off”

Không phải giải pháp production. Đây chỉ có thể là thao tác chẩn đoán có kiểm soát để quan sát một plan khác, không sửa selectivity, expression mismatch hoặc SQL logic.

### 42.15. “Một GIN index lớn luôn tốt hơn nhiều indexes nhỏ”

Không có quy tắc chung. Cân nhắc workload, partial predicates, write overhead và storage.

### 42.16. “Partial GIN cho published luôn dùng khi query có status parameter”

Không chắc với generic plans nếu planner không chứng minh được predicate status luôn published.

### 42.17. “FTS tiếng Việt mặc định hiểu mọi từ ghép và dấu”

Sai. Cần lựa chọn tokenizer/dictionary/normalization phù hợp.

### 42.18. “Càng nhiều lexemes tìm kiếm luôn càng nhanh”

Không. OR có thể làm kết quả rộng hơn, AND có thể thu hẹp nhưng phrase/weight cần recheck; planner và chi phí thay đổi.

### 42.19. “Rows Removed by Index Recheck là lỗi logic của database”

Không. Đây là thông tin thực thi về candidates bị loại khi recheck.

### 42.20. “Heap Blocks: lossy nhất định do GiST”

Sai. Lossy bitmap là cơ chế liên quan memory của bitmap heap scan; GiST signature là cơ chế lossy khác.

### 42.21. “Đọc idx_tup_fetch là biết mọi heap tuples của Bitmap Heap Scan”

Sai. Counters trong pg_stat_user_indexes có semantics cụ thể, cần kết hợp EXPLAIN và view tương ứng.

### 42.22. “Tạo index rồi không cần ANALYZE”

Sai như một thói quen vận hành. Khi dữ liệu/phân phối đã đổi, cần statistics cập nhật cho planner chọn plan tốt.

### 42.23. “Dữ liệu FTS đã có index thì body thay đổi tự đồng bộ dù vector do app quản lý”

Sai. Nếu vector cập nhật thủ công, cần protocol đảm bảo nhất quán.

### 42.24. “ts_headline là công cụ chống XSS”

Sai. Ứng dụng phải xử lý text/markup an toàn.

### 42.25. “Một benchmark SELECT đủ để chọn GIN thay GiST”

Sai. Đo nhiều query, nhiều lần, cùng dữ liệu và cả chi phí ghi/storage.

## 43. Quy trình điều tra một truy vấn FTS chậm

Một quy trình thực tế theo thứ tự:

1. Ghi lại SQL thật và bind parameters.
2. Xác định user đang cần lexical search hay substring/fuzzy search.
3. Xác định text search configuration đã dùng.
4. Kiểm tra output của `to_tsvector</BT> trên tài liệu mẫu.
5. Kiểm tra output của hàm tạo `tsquery</BT>.
6. Đảm bảo index được tạo đúng cột/biểu thức/operator class.
7. Kiểm tra partial index predicate nếu có.
8. Đảm bảo vector được cập nhật khi dữ liệu nguồn đổi.
9. Chạy `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)</BT> trên query read-only.
10. So estimated rows/actual rows.
11. Xem Seq Scan, Bitmap Index Scan và Bitmap Heap Scan.
12. Kiểm tra `Index Cond</BT> có thực sự dùng `@@</BT>.
13. Xem `Recheck Cond</BT> và `Rows Removed by Index Recheck</BT>.
14. Xem `Heap Blocks: exact/lossy</BT>.
15. Xem shared hit/read và temp I/O nếu có.
16. Kiểm tra chi phí ranking/sort/limit.
17. Kiểm tra tenant/status/date filters và indexes liên quan.
18. Chạy ANALYZE nếu thống kê stale.
19. Benchmark GIN và GiST trên dữ liệu đại diện.
20. Theo dõi write/maintenance cost của các lựa chọn.
21. Chỉ triển khai khi có bằng chứng cải thiện trên workload cần tối ưu.

### 43.1. Không biến chẩn đoán thành thay đổi hệ thống

Có thể thử `SET LOCAL enable_seqscan = off</BT> trong transaction lab để quan sát khả năng dùng index; nhưng đây là **thăm dò**, không phải cấu hình nên bật toàn production vì nó có thể buộc những plans đắt hơn.

### 43.2. Đọc thời gian theo ngữ cảnh

Một query 3ms thay vì 4ms trên bảng 60.000 rows có thể bị biến động cache/tải. Đo nhiều lần, cân bằng quy mô dữ liệu và kiểm tra buffers trước khi kết luận.

### 43.3. EXPLAIN ANALYZE không chỉ xem plan

Nó **thực sự chạy** SQL. Với DML, dùng môi trường thử nghiệm hoặc giao dịch có rollback phù hợp; không chạy UPDATE/DELETE trên production chỉ để “xem plan”.

## 44. Bài tập thực hành

### Bài 1 — Vai trò tsvector

`tsvector</BT> có lưu nguyên văn title/body không?

**Gợi ý:** Không; nó lưu lexemes và thông tin vị trí/trọng số liên quan.

### Bài 2 — Vai trò tsquery

`tsquery</BT> biểu diễn điều gì?

**Đáp án:** Điều kiện tìm kiếm theo lexemes và operators.

### Bài 3 — Toán tử so khớp

Toán tử PostgreSQL nào thường dùng để so `tsvector</BT> với `tsquery</BT>?

**Đáp án:** `@@</BT>.

### Bài 4 — Simple vs english

Vì sao cần thống nhất cấu hình khi tạo vector và query?

**Gợi ý:** Dictionaries, stemming/stop words và normalization ảnh hưởng lexemes.

### Bài 5 — Tạo GIN

Viết chỉ mục GIN cho cột `search_vector</BT> trong bảng lab.

~~~sql
CREATE INDEX articles_test_gin_idx
ON search_lab.articles USING GIN(search_vector);
~~~

Trong lab đã có GIN sau phần so sánh, không cần tạo thêm index này nếu không thử nghiệm mục đích riêng.

### Bài 6 — Tạo GiST

~~~sql
CREATE INDEX articles_test_gist_idx
ON search_lab.articles USING GIST(search_vector);
~~~

### Bài 7 — GIN structure

GIN FTS cơ bản ánh xạ gì?

**Đáp án:** Lexemes tới những row/TID postings.

### Bài 8 — GiST signature

Vì sao GiST có thể trả candidates false-positive?

**Gợi ý:** Signature bit collisions.

### Bài 9 — Recheck

False positives GiST có tự trở thành hàng trong kết quả cuối không?

**Đáp án:** Không, executor rechecks điều kiện.

### Bài 10 — GIN weighted query

Vì sao tìm `planner:B</BT> có thể cần recheck dù dùng GIN?

**Gợi ý:** GIN không lưu đủ thông tin weight.

### Bài 11 — Phrase

Viết query tìm phrase “gin gist”.

~~~sql
SELECT article_id
FROM search_lab.articles
WHERE search_vector @@ phraseto_tsquery(
    'simple',
    'gin gist'
);
~~~

### Bài 12 — AND

`to_tsquery('simple','gin & planner')</BT> khác OR thế nào?

**Gợi ý:** AND cần cả hai lexemes, OR chỉ cần một.

### Bài 13 — Query người dùng

Vì sao không nối user input trực tiếp thành SQL text?

**Đáp án:** SQL injection/cú pháp không an toàn; dùng parameters và hàm parsing phù hợp.

### Bài 14 — Plain input

Search box nhập `gin gist</BT> không có cú pháp nâng cao. Hàm nào phù hợp để thử?

**Gợi ý:** `plainto_tsquery</BT>.

### Bài 15 — Phrase UI

User gõ văn bản trong dấu ngoặc kép, muốn phrase. Có thể cân nhắc gì?

**Gợi ý:** `phraseto_tsquery</BT> hoặc cú pháp websearch phù hợp.

### Bài 16 — Baseline

Lệnh nào hiện plan và buffers thực tế?

**Đáp án:** `EXPLAIN (ANALYZE, BUFFERS)</BT>.

### Bài 17 — Index Cond

Trong EXPLAIN, node nào cho biết index FTS được dùng?

**Gợi ý:** Bitmap Index Scan on tên index, Index Cond trên @@.

### Bài 18 — Recheck Cond

Sự xuất hiện của Recheck Cond có chứng minh 100% rows bị sai không?

**Đáp án:** Không.

### Bài 19 — Rows Removed

Field nào giúp đếm số rows bị loại vì index recheck?

**Đáp án:** `Rows Removed by Index Recheck</BT>.

### Bài 20 — Bitmap lossiness

`Heap Blocks: lossy</BT> khác gì GiST signature lossy?

**Gợi ý:** Một bên là bitmap memory/detail, bên kia là signature collisions.

### Bài 21 — Seq Scan

Một bảng 100 rows dù có GIN vẫn chọn Seq Scan. Có chắc index hỏng không?

**Đáp án:** Không.

### Bài 22 — Common term

Vì sao từ phổ biến khắp bảng có thể khiến GIN ít lợi ích?

**Gợi ý:** Index candidates rất nhiều, vẫn đọc phần lớn heap.

### Bài 23 — Ranking

GIN có tự sắp thứ tự `ts_rank</BT> không?

**Đáp án:** Không.

### Bài 24 — Top N

Một query match 1 triệu hàng, LIMIT 20 theo rank. Tại sao vẫn tốn CPU?

**Gợi ý:** Có thể phải tính rank/sort trên nhiều matches.

### Bài 25 — Expression mismatch

Index trên `to_tsvector('simple',body)</BT> có tự phục vụ query trên `to_tsvector('english',body)</BT> không?

**Đáp án:** Không thể mặc định.

### Bài 26 — Generated vector

Generated search_vector giúp gì?

**Gợi ý:** Vector được duy trì theo biểu thức khi row thay đổi.

### Bài 27 — Partial index

Nếu index GIN chỉ cho published, query draft có được dùng index đó để tìm draft không?

**Đáp án:** Không, index không chứa draft rows.

### Bài 28 — Parameterized partial plan

Vì sao generic plan với `status=$1</BT> có thể không dùng partial index `WHERE status='published'</BT>?

**Gợi ý:** Planner không bảo đảm $1 luôn published.

### Bài 29 — pg_trgm

Muốn tìm `ILIKE '%postgre%'</BT>, index tsvector GIN có là lựa chọn trực tiếp nhất không?

**Gợi ý:** Không; cân nhắc pg_trgm.

### Bài 30 — Trigram

Nêu một khác biệt giữa trigram và FTS lexemes.

**Gợi ý:** Chuỗi bộ ba ký tự so với từ/lexeme đã phân tích.

### Bài 31 — fastupdate

GIN pending list dùng để làm gì?

**Gợi ý:** Giảm chi phí một số updates nhỏ bằng ghi trì hoãn vào main GIN structure.

### Bài 32 — Cleanup

Autovacuum/VACUUM có vai trò gì với GIN?

**Gợi ý:** Giúp cleanup pending list/dead entries theo cơ chế.

### Bài 33 — GiST siglen

Tăng signature length nhằm giảm hiện tượng gì?

**Gợi ý:** Bit collisions/false positives, nhưng tăng storage.

### Bài 34 — Index size

Dùng hàm nào xem kích thước index?

**Đáp án:** `pg_relation_size</BT>, `pg_size_pretty</BT>.

### Bài 35 — Index statistics

View nào có `idx_scan</BT> và `idx_tup_read</BT>?

**Đáp án:** `pg_stat_user_indexes</BT>.

### Bài 36 — Tiếng Việt

Vì sao simple config có thể chưa đủ cho tìm kiếm tiếng Việt chính xác?

**Gợi ý:** Phân tách từ ghép, dấu và từ điển.

### Bài 37 — Tenant security

GIN trên search_vector có tự bảo vệ không lộ bài của tenant khác không?

**Đáp án:** Không; cần authorization/RLS.

### Bài 38 — ts_headline

Có nên render raw headline có markup như HTML an toàn chưa được escape không?

**Đáp án:** Không; không phải công cụ sanitize XSS.

### Bài 39 — Dữ liệu stale

Nếu body đã cập nhật nhưng vector do app quản lý không đổi, index có tự sửa nghĩa tìm kiếm không?

**Đáp án:** Không; cần cập nhật vector đúng.

### Bài 40 — Thiết kế thực tế

Một hệ thống có 50 triệu documents, 95% query tìm lexemes tiếng Anh, 5% tìm substring và dữ liệu được cập nhật liên tục. Bạn cần đo những gì để chọn cấu trúc?

**Gợi ý:** GIN/GiST tsvector, pg_trgm riêng cho substring, selectivity, read/write latency, index sizes, autovacuum/pending list, partial indexes, ranking và FTS config.

## 45. Bảng tra cứu nhanh

| Chủ đề | Ghi nhớ |
|---|---|
| Chuyển text thành lexemes | `to_tsvector(config,text)</BT> |
| Query từ plain text | `plainto_tsquery</BT> |
| Query theo phrase | `phraseto_tsquery</BT> |
| Query kiểu web search | `websearch_to_tsquery</BT> |
| Query cú pháp tường minh | `to_tsquery</BT> |
| So khớp | `tsvector @@ tsquery</BT> |
| AND/OR/NOT | `&</BT>, `|</BT>, `!</BT> |
| Phrase | `<-></BT> |
| Prefix lexeme | `:*</BT> |
| Tiêu đề weight A | `setweight(vector,'A')</BT> |
| GIN full text | `CREATE INDEX ... USING GIN(vector)</BT> |
| GiST full text | `CREATE INDEX ... USING GIST(vector)</BT> |
| GIN structure | Lexeme → postings |
| GiST structure | Signature lossy |
| False positives | Recheck ở heap |
| GIN phrase/weights | Có thể cần recheck |
| Bitmap lossiness | Bitmap exact/lossy blocks |
| Index được dùng | Bitmap Index Scan và Index Cond |
| Candidate heap | Bitmap Heap Scan |
| Recheck removals | Rows Removed by Index Recheck |
| Planner chọn Seq Scan | Có thể đúng với phổ biến/bảng nhỏ |
| Ranking | `ts_rank</BT>, `ts_rank_cd</BT> |
| Highlight | `ts_headline</BT>, vẫn cần escape an toàn |
| Generated vector | `GENERATED ALWAYS AS (...) STORED</BT> |
| Expression index | Index trên biểu thức `to_tsvector(...)</BT> |
| Partial GIN | `WHERE status='published'</BT> |
| Substring/fuzzy | `pg_trgm</BT> với gin_trgm_ops/gist_trgm_ops |
| Index definitions | `pg_indexes</BT> |
| Index usage | `pg_stat_user_indexes</BT> |
| Index size | `pg_relation_size</BT> |
| GIN write buffering | `fastupdate</BT>, pending list |
| Cleanup | VACUUM/autovacuum, `gin_clean_pending_list</BT> |
| Refresh stats | `ANALYZE</BT> |
| Xem plan thực | `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)</BT> |
| Phân quyền | RLS/GRANT/app authorization, không phải index |

---

## Kết luận

**GIN và GiST đều có thể phục vụ Full Text Search của PostgreSQL, nhưng cách tìm ứng viên khác nhau.** Với `tsvector</BT>, GIN xây cấu trúc đảo từ lexemes đến các hàng liên quan và thường là lựa chọn đầu tiên đáng thử cho các truy vấn FTS. GiST dùng biểu diễn signature gần đúng, có thể tạo false-positive candidates và cần recheck. GIN cũng có những tình huống phải recheck, đặc biệt với thông tin vị trí/phrase và weights không có đầy đủ trong index.

Quan trọng hơn tên index là **chất lượng của toàn bộ pipeline**: tạo lexemes bằng cấu hình nhất quán, xây `tsquery</BT> đúng ngữ nghĩa người dùng, dùng `@@</BT> phù hợp operator class và kiểm tra planner qua `EXPLAIN (ANALYZE, BUFFERS)</BT>. Hãy đọc `Index Cond</BT>, `Recheck Cond</BT>, `Rows Removed by Index Recheck</BT>, `Heap Blocks: exact/lossy</BT>, số rows thực tế, buffers và thời gian. Không coi Seq Scan là lỗi nếu tập dữ liệu nhỏ hoặc từ khóa quá phổ biến; không coi sự xuất hiện của Recheck Cond là bằng chứng kết quả tìm kiếm sai.

Trong production, thiết kế còn phải cân nhắc **độ chọn lọc, UPDATE/INSERT overhead, GIN pending lists, autovacuum, expression matching, partial indexes, ranking, tenant filters và ngôn ngữ**. Khi yêu cầu là substring/fuzzy search thay vì lexical FTS, hãy đánh giá `pg_trgm</BT> thay vì dùng sai chỉ mục FTS.

Nguyên tắc thực hành cuối cùng: **chọn đúng ngữ nghĩa tìm kiếm trước; xây index tương ứng sau; dùng kế hoạch thực thi và phép đo read/write trên workload thật để quyết định giữ GIN, GiST hay một cấu trúc khác**.
