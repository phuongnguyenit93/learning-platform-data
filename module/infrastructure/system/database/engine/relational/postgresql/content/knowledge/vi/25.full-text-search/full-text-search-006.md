# Trọng số trường, xếp hạng và làm nổi bật kết quả trong PostgreSQL

Một công cụ tìm kiếm không chỉ cần biết tài liệu nào chứa từ khóa. Khi có hàng nghìn tài liệu cùng khớp, người dùng cần được xem **kết quả phù hợp nhất trước**, đồng thời thấy một **đoạn trích làm rõ vị trí khớp**.

Ví dụ, người dùng tìm `search ranking`. Bài A có hai từ ngay trong tiêu đề; bài B chỉ nhắc hai từ ở cuối nội dung dài; bài C có chúng nằm gần nhau trong một đoạn ngắn; bài D là bản nháp chưa được phép công bố. Một thiết kế tốt phải phân biệt:

- **Matching** — Tài liệu nào thỏa yêu cầu? Dùng `tsvector @@ tsquery`.
- **Ranking** — Tài liệu nào đáng đứng trước? Dùng trọng số `A/B/C/D`, `ts_rank` hoặc `ts_rank_cd`.
- **Highlighting** — Người dùng nên nhìn thấy đoạn văn nào? Dùng `ts_headline` trên văn bản gốc.
- **Authorization** — Tài liệu nào được phép xuất hiện? Dùng bộ lọc/RLS, không dùng điểm rank.

~~~mermaid
flowchart TD
    D["title / summary / category / body"] --> V["setweight + to_tsvector"]
    V --> I["tsvector / GIN"]
    U["Từ khóa người dùng"] --> Q["websearch_to_tsquery"]
    I --> M["@@: chọn tài liệu phù hợp"]
    Q --> M
    M --> R["ts_rank / ts_rank_cd"]
    R --> S["ORDER BY score + tie-breakers"]
    S --> L["LIMIT top-N"]
    L --> H["ts_headline trên văn bản gốc"]
    H --> UI["Renderer an toàn, tránh XSS"]
~~~

Bài này thuộc chương **Tìm kiếm văn bản**, module **Database Engine Relational PostgreSQL**, tập trung vào cách dùng PostgreSQL Full-Text Search (FTS) để ưu tiên từng trường, chấm điểm và tạo đoạn trích có highlight, cùng những hạn chế về hiệu năng và an toàn hiển thị.

## 1. Điều kiện khớp khác điểm xếp hạng

Trong FTS, tài liệu được chuyển thành `tsvector` còn yêu cầu tìm kiếm được chuyển thành `tsquery`.

~~~sql
SELECT
    to_tsvector(
        'english'::regconfig,
        'Search ranking improves search results'
    )
    @@
    plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS matched;
~~~

Ở đây kết quả kỳ vọng là `true`, nhưng không có điểm số.

Nếu cần xếp hạng nhiều tài liệu đã khớp, có thể tính:

~~~sql
SELECT
    ts_rank(
        to_tsvector(
            'english'::regconfig,
            'Search ranking improves search results'
        ),
        plainto_tsquery(
            'english'::regconfig,
            'search ranking'
        )
    ) AS relevance_score;
~~~

`@@` trả boolean; `ts_rank` trả một số điểm dựa trên lexeme và các tín hiệu ranking. **Không dùng điểm số thay cho kiểm tra quyền truy cập.**

## 2. Vì sao FTS không giống ILIKE?

`ILIKE '%search%'` tìm một mẫu ký tự không phân biệt hoa/thường. FTS thực hiện tokenization và dùng dictionary để chuyển từ thành **lexeme**.

~~~sql
SELECT
    to_tsvector(
        'english'::regconfig,
        'Searching through documents'
    ) AS english_vector,
    to_tsvector(
        'simple'::regconfig,
        'Searching through documents'
    ) AS simple_vector;
~~~

Hai configuration có thể tạo lexeme khác nhau do stemming/stop words. FTS không tự giải quyết mọi lỗi chính tả, từ đồng nghĩa hay ý nghĩa ngữ nghĩa như embedding search.

**Quy tắc:** cấu hình phân tích nội dung, cấu hình phân tích từ khóa và cấu hình dùng khi highlight phải tương thích. Nếu thay configuration, dữ liệu tsvector được lưu và index liên quan có thể cần được xây dựng lại.

## 3. Trọng số A, B, C, D

PostgreSQL cho phép gắn nhãn weight vào các vị trí lexeme bằng `setweight`.

| Trọng số | Field gợi ý | Mức ưu tiên mặc định |
| --- | --- | --- |
| A | Tiêu đề | Cao nhất |
| B | Tóm tắt | Cao |
| C | Chuyên mục, nhãn | Trung bình |
| D | Thân bài | Thấp nhất |

Ví dụ:

~~~sql
SELECT
    setweight(
        to_tsvector(
            'english'::regconfig,
            'Search ranking'
        ),
        'A'
    ) AS title_vector,
    setweight(
        to_tsvector(
            'english'::regconfig,
            'Search ranking'
        ),
        'D'
    ) AS body_vector;
~~~

Các lexeme giống nhau có thể mang nhãn trọng số khác nhau. `setweight` **chỉ gắn nhãn**, còn cách dùng nhãn để tính score thuộc hàm ranking.

## 4. Nối nhiều trường bằng toán tử ||

Một bài viết có `title`, `summary`, `category`, `body`. Ta tạo vector chung:

~~~sql
SELECT
      setweight(
          to_tsvector(
              'english'::regconfig,
              'PostgreSQL search ranking'
          ),
          'A'
      )
   || setweight(
          to_tsvector(
              'english'::regconfig,
              'Weighted text search'
          ),
          'B'
      )
   || setweight(
          to_tsvector(
              'english'::regconfig,
              'Database'
          ),
          'C'
      )
   || setweight(
          to_tsvector(
              'english'::regconfig,
              'Search documents and rank matching results'
          ),
          'D'
      ) AS weighted_vector;
~~~

Trong ngữ cảnh này `||` nối các `tsvector`, không phải nối chuỗi text hoặc JSONB.

Nối vector có thể điều chỉnh vị trí lexeme. Điều này quan trọng cho phrase/proximity: nếu một phrase không được phép vượt ranh giới giữa title và summary, hãy kiểm tra phrase riêng trên từng trường thay vì mặc định vector nối có ranh giới tuyệt đối.

### NULL và trường không có nội dung

Dùng `coalesce(field,'')` trước `to_tsvector` nếu field được phép NULL. Chuỗi rỗng cho vector rỗng và không làm mất nội dung từ các trường khác.

## 5. Lab: tạo schema và bảng tài liệu

Các câu SQL dưới đây dùng database thực hành với schema `fts_rank_lab`.

**Cảnh báo:** `DROP SCHEMA ... CASCADE` xóa tất cả đối tượng đang có trong schema đó. Chỉ chạy trong **database lab riêng**, không chạy production.

~~~sql
-- CHỈ CHẠY TRÊN DATABASE THỰC HÀNH.
DROP SCHEMA IF EXISTS fts_rank_lab CASCADE;
CREATE SCHEMA fts_rank_lab;

CREATE TABLE fts_rank_lab.articles (
    article_id bigint PRIMARY KEY,
    title text NOT NULL,
    summary text NOT NULL DEFAULT '',
    category text NOT NULL DEFAULT '',
    body text NOT NULL,
    published_at timestamptz NOT NULL,
    is_published boolean NOT NULL DEFAULT true,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(title, '')
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(summary, '')
            ),
            'B'
        )
        ||
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(category, '')
            ),
            'C'
        )
        ||
        setweight(
            to_tsvector(
                'english'::regconfig,
                coalesce(body, '')
            ),
            'D'
        )
    ) STORED
);
~~~

Stored generated columns có từ PostgreSQL 12. Biểu thức `to_tsvector` dùng `'english'::regconfig` cố định để không phụ thuộc ngầm vào configuration của session và phù hợp yêu cầu tính immutable của generated expression.

### Vì sao lưu search_vector?

- Không phải tự tính lại toàn biểu thức mỗi lần SELECT dùng ranking.
- INSERT/UPDATE tự duy trì cột generated theo quy tắc PostgreSQL.
- Có thể tạo GIN index trên vector đã lưu.
- Nơi matching và ranking cùng dùng một biểu diễn nhất quán.

**Đánh đổi:** giá trị vector được lưu và có chi phí tính toán/ghi khi nguồn thay đổi.

## 6. Nạp seed có nhiều kiểu tài liệu

~~~sql
INSERT INTO fts_rank_lab.articles (
    article_id, title, summary, category,
    body, published_at, is_published
)
VALUES
(
    1,
    'PostgreSQL search ranking',
    'Weighted full-text search and relevant results',
    'Database',
    'Use tsvector and tsquery to search documents. '
        || 'Ranking places useful articles first. '
        || 'Highlights help readers see matched terms.',
    '2026-01-10 08:00:00+00',
    true
),
(
    2,
    'Building a documentation portal',
    'Navigation, layout, and category filters',
    'Architecture',
    'A search ranking system helps users find documents. '
        || 'Search ranking should consider titles and summaries.',
    '2026-02-10 08:00:00+00',
    true
),
(
    3,
    'Search indexes in PostgreSQL',
    'GIN indexes and query planning',
    'Database',
    'A GIN index helps full text search matching. '
        || 'Ranking and highlighting improve the results page.',
    '2026-03-10 08:00:00+00',
    true
),
(
    4,
    'PostgreSQL transaction locks',
    'Concurrency and lock waits',
    'Database',
    'Row locks protect concurrent updates. '
        || 'An index does not remove every lock wait.',
    '2026-04-10 08:00:00+00',
    true
),
(
    5,
    'Relevance and phrase proximity',
    'How distance between words affects ranking',
    'Search',
    'Search systems can reward close matching terms. '
        || 'Full text search ranking can use cover density.',
    '2026-05-10 08:00:00+00',
    true
),
(
    6,
    'High volume logging guide',
    'Operational logging and retention',
    'Operations',
    'This long technical note discusses many operations. '
        || repeat(
            'The application stores events and rotates logs. ',
            6
        )
        || 'It mentions search ranking once near the end.',
    '2026-06-10 08:00:00+00',
    true
),
(
    7,
    'Search results highlighting',
    'Make matching search words easy to see',
    'Search',
    'PostgreSQL ts_headline builds excerpts from original '
        || 'text, but the output is not automatically safe HTML.',
    '2026-07-10 08:00:00+00',
    true
),
(
    8,
    'Ranking product listings',
    'Relevance, freshness, and popularity',
    'Product',
    'Product search can use title and category matches. '
        || 'Query relevance is not the same as popularity.',
    '2026-08-10 08:00:00+00',
    true
),
(
    9,
    'PostgreSQL text search concepts',
    'Lexemes, stop words, stemming, and phrase queries',
    'Database',
    'A vector contains normalized lexemes and positions. '
        || 'A search query should use matching configuration.',
    '2026-09-10 08:00:00+00',
    true
),
(
    10,
    'Writing faster SQL queries',
    'Reduce work and examine query plans',
    'Performance',
    'Search terms may be selective or common. '
        || 'Indexes can reduce I/O but also increase write cost.',
    '2026-10-10 08:00:00+00',
    true
),
(
    11,
    'Search ranking draft',
    'Unpublished experimental ranking notes',
    'Draft',
    'This draft discusses weighted search fields.',
    '2026-11-10 08:00:00+00',
    false
),
(
    12,
    'PostgreSQL and JSONB',
    'Working with JSON documents',
    'Database',
    'JSONB stores flexible structures and supports indexes.',
    '2026-11-11 08:00:00+00',
    true
);

ANALYZE fts_rank_lab.articles;
~~~

Bộ dữ liệu có chủ đích:

- Bài 1 khớp `search ranking` ngay trong title.
- Bài 2 chỉ nhắc cụm đó trong body.
- Bài 5 bàn về proximity.
- Bài 6 có body dài và từ khóa gần cuối.
- Bài 11 chưa xuất bản dù title liên quan.
- Bài 12 không trực tiếp về ranking.

Không cần đoán trước số score cụ thể: kết quả phải được lấy từ truy vấn thực tế.

## 7. Tạo GIN index và xem vector

~~~sql
CREATE INDEX idx_articles_vector_gin
ON fts_rank_lab.articles
USING gin (search_vector);

ANALYZE fts_rank_lab.articles;

SELECT
    article_id,
    title,
    search_vector
FROM fts_rank_lab.articles
WHERE article_id IN (1, 2, 6)
ORDER BY article_id;
~~~

`search_vector` có lexeme và vị trí với các weight labels. Không kỳ vọng vector còn nguyên dấu câu, chữ hoa hay định dạng ban đầu.

Với bảng 12 hàng, PostgreSQL có thể chọn `Seq Scan` vì rất rẻ. Có index không có nghĩa planner bắt buộc dùng nó.

## 8. Chuẩn bị tsquery từ từ khóa người dùng

| Hàm | Ý nghĩa |
| --- | --- |
| `plainto_tsquery` | Từ văn bản thông thường, các lexeme thường nối bằng AND |
| `phraseto_tsquery` | Diễn đạt tìm cụm dựa trên vị trí |
| `websearch_to_tsquery` | Cú pháp kiểu ô tìm kiếm: ngoặc kép, OR, dấu trừ |
| `to_tsquery` | Cú pháp tsquery đầy đủ, dùng khi tự xây biểu thức có kiểm soát |

~~~sql
SELECT
    plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS plain_query,
    phraseto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS phrase_query,
    websearch_to_tsquery(
        'english'::regconfig,
        '"search ranking" OR PostgreSQL'
    ) AS web_query;
~~~

Nên dùng bind parameters khi từ khóa đến từ ứng dụng. Đừng ghép input người dùng trực tiếp vào SQL hoặc cú pháp tsquery raw mà không kiểm soát.

## 9. Tách điều kiện khớp và bộ lọc quyền

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY a.article_id;
~~~

Hai điều kiện có vai trò khác nhau:

- `is_published` là **quy tắc hiển thị bắt buộc**.
- `@@` là **matching**.

Một bài chưa xuất bản không được lộ ra dù rank cao. Với hệ thống đa tenant, phải thêm bộ lọc tenant/authorization hoặc RLS thích hợp. Không biến việc bảo mật thành một số điểm boost.

## 10. Xếp hạng bằng ts_rank

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(
        a.search_vector,
        q.search_query
    ) AS score
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY score DESC, a.article_id DESC;
~~~

Điểm có thể phụ thuộc tần suất lexeme, weight labels, đặc điểm phân bố và normalization. **Đây không phải xác suất rằng bài viết đúng 80% khi score bằng 0.8.**

Một lần nhắc từ ở title được góp phần với weight A; một lần ở body thường được góp phần với D, nhưng **không có quy tắc mọi title match luôn đứng trên mọi body match** vì score còn chịu nhiều yếu tố.

## 11. Truyền trọng số tùy chỉnh: thứ tự D,C,B,A

Đây là điểm quan trọng dễ nhầm.

Hàm `ts_rank` hoặc `ts_rank_cd` nhận mảng bốn hệ số theo thứ tự:

| Phần tử mảng | Weight label | Mặc định thường dùng |
| ---: | --- | ---: |
| 1 | D | 0.1 |
| 2 | C | 0.2 |
| 3 | B | 0.4 |
| 4 | A | 1.0 |

**Thứ tự là D, C, B, A — không phải A, B, C, D.**

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(
        ARRAY[0.05, 0.15, 0.40, 1.00]::real[],
        a.search_vector,
        q.search_query
    ) AS custom_score
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY custom_score DESC, a.article_id DESC;
~~~

Ở đây D = 0.05, C = 0.15, B = 0.40, A = 1.00. Ta giảm đóng góp của body so với title; điều kiện `@@` **không đổi**.

Trọng số là lựa chọn nghiệp vụ: tên sản phẩm có thể quan trọng hơn mô tả; với một số văn bản luật, đoạn điều khoản có thể quan trọng hơn tiêu đề.

## 12. ts_rank_cd và độ gần của từ khóa

`ts_rank_cd` dùng **cover-density ranking**, tận dụng positional information để đánh giá các lần khớp gần nhau.

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.search_query) AS rank_simple,
    ts_rank_cd(
        a.search_vector,
        q.search_query
    ) AS rank_cover_density
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY rank_cover_density DESC, a.article_id DESC;
~~~

Trực giác: `search ranking` ở hai từ kề nhau có thể thể hiện sự liên quan khác với `search` ở đầu bài và `ranking` rất xa ở cuối bài.

| Đặc điểm | `ts_rank` | `ts_rank_cd` |
| --- | --- | --- |
| Tính điểm từ lexeme/weights | Có | Có |
| Xét proximity/cover theo công thức riêng | Không | Có |
| Cần vị trí để tính cover | Không giống ts_rank_cd | Có |
| Luôn tốt hơn trên mọi loại dữ liệu | Không | Không |

Không chọn hàm chỉ vì một cái nghe có vẻ nâng cao hơn; hãy so chất lượng top-K trên corpus thật.

### Vì sao không strip positions?

~~~sql
SELECT
    ts_rank_cd(
        to_tsvector(
            'english'::regconfig,
            'Search ranking improves results'
        ),
        plainto_tsquery(
            'english'::regconfig,
            'search ranking'
        )
    ) AS with_positions,
    ts_rank_cd(
        strip(
            to_tsvector(
                'english'::regconfig,
                'Search ranking improves results'
            )
        ),
        plainto_tsquery(
            'english'::regconfig,
            'search ranking'
        )
    ) AS without_positions;
~~~

`strip` loại vị trí lexeme; `ts_rank_cd` thiếu thông tin cover và có thể cho điểm bằng 0. Không strip vector tùy tiện nếu cần proximity ranking.

## 13. Normalization và tài liệu dài

Tài liệu dài có thể nhắc từ khóa nhiều lần nhưng không nhất thiết liên quan hơn một đoạn ngắn trả lời chính xác. PostgreSQL hỗ trợ `normalization` dưới dạng bitmask.

| Bit | Ý nghĩa |
| ---: | --- |
| 0 | Không normalization thêm |
| 1 | Chia theo `1 + log(document length)` |
| 2 | Chia theo document length |
| 4 | Mean harmonic distance giữa extents, dùng với `ts_rank_cd` |
| 8 | Chia theo số lexeme duy nhất |
| 16 | Chia theo `1 + log(số lexeme duy nhất)` |
| 32 | Chuyển điểm thành `rank / (rank + 1)` |

Kết hợp bit `2 | 32 = 34`:

~~~sql
SELECT ts_rank(
    to_tsvector(
        'english'::regconfig,
        'Search ranking and search ranking'
    ),
    plainto_tsquery(
        'english'::regconfig,
        'search ranking'
    ),
    34
);
~~~

### Cờ 32 không biến rank thành xác suất

Nếu điểm là `r`:

\[
r_{\mathrm{new}}=\frac{r}{r+1}
\]

Với điểm không âm, giá trị được biến đổi vào khoảng từ 0 đến dưới 1. Đây chỉ là phép biến đổi thang điểm, không có nghĩa “0.8 = tài liệu phù hợp 80%”. Nếu chỉ áp cùng phép biến đổi đơn điệu, thứ tự các điểm không thay đổi vì riêng phép biến đổi đó.

### Không so score với cấu hình khác nhau

`ts_rank(...,0)` và `ts_rank(...,34)` không nhất thiết có cùng thang. Nếu đổi weights/normalization, phải xem lại thresholds/ranking evaluation.

## 14. Query ranking đầy đủ

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_rank_cd(
        ARRAY[0.10, 0.20, 0.45, 1.00]::real[],
        a.search_vector,
        q.search_query,
        32
    ) AS relevance_score
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.is_published
  AND a.search_vector @@ q.search_query
ORDER BY
    relevance_score DESC,
    a.published_at DESC,
    a.article_id DESC
LIMIT 10;
~~~

Cấu trúc này cho thấy ba lớp độc lập:

- `WHERE ... @@`: chỉ tài liệu khớp được xét.
- `ts_rank_cd`: chấm điểm.
- `ORDER BY/ LIMIT`: lấy danh sách ưu tiên.

**LIMIT nhỏ không đảm bảo database chỉ phải tính score cho bấy nhiêu hàng.** PostgreSQL vẫn có thể cần đánh giá nhiều ứng viên để chọn top.

## 15. Chỉ khớp title bằng weight restriction

Nếu nghiệp vụ muốn từ `search` bắt buộc nằm trong title thay vì chỉ có điểm cao hơn:

~~~sql
SELECT
    to_tsquery(
        'english'::regconfig,
        'search:A'
    ) AS title_only,
    to_tsquery(
        'english'::regconfig,
        'search:AB'
    ) AS title_or_summary;
~~~

Dùng:

~~~sql
SELECT article_id, title
FROM fts_rank_lab.articles
WHERE is_published
  AND search_vector @@ to_tsquery(
      'english'::regconfig,
      'search:A'
  );
~~~

Đây là **điều kiện lọc**, khác việc gán A=1.0 để title được cộng nhiều điểm.

### GIN và recheck

GIN index trên tsvector chủ yếu lưu lexeme để tìm ứng viên, **không lưu toàn bộ weight labels theo cách đủ để xử lý mọi weight-restricted query chỉ từ index**. Với truy vấn `:A`, PostgreSQL có thể cần recheck hàng phù hợp.

## 16. Phrase matching khác cover-density ranking

~~~sql
SELECT
    phraseto_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS phrase_query,
    to_tsquery(
        'english'::regconfig,
        'search <-> ranking'
    ) AS adjacent_query;
~~~

`<->` diễn đạt các lexeme kề nhau. Các biểu thức proximity khác có thể dùng cú pháp khoảng cách của tsquery.

- Phrase query quyết định **có khớp hay không** theo vị trí.
- Cover-density rank quyết định **điểm** từ những khớp và vị trí của chúng.

Một tài liệu có hai từ cách rất xa có thể khớp AND query nhưng không khớp phrase adjacency. Khi nối nhiều vector trường, phải xét việc vị trí được ghép có thể khiến phrase xuyên ranh giới field theo cấu trúc đang dùng.

## 17. Prefix, stemming và giới hạn từ vựng

~~~sql
SELECT to_tsquery(
    'english'::regconfig,
    'rank:*'
);
~~~

Prefix search trên lexeme **không giống** tìm chuỗi con `ILIKE '%ank%'`. FTS cũng không tự sửa mọi lỗi chính tả, hiểu mọi từ đồng nghĩa hay tìm được tất cả paraphrase.

Với autocomplete, typo tolerance, tìm chuỗi con hoặc semantic search, có thể cân nhắc `pg_trgm`, dictionary synonym, search engine khác hoặc kết hợp embedding. Đừng chọn công nghệ khác nếu chưa có mục tiêu cụ thể và số liệu thực tế.

## 18. Query rỗng và stop words

Input như `the and of` có thể không còn lexeme hữu ích sau xử lý tiếng Anh.

~~~sql
SELECT
    websearch_to_tsquery(
        'english'::regconfig,
        'the and of'
    ) AS query,
    numnode(
        websearch_to_tsquery(
            'english'::regconfig,
            'the and of'
        )
    ) AS node_count;
~~~

Nên có chính sách sản phẩm:

1. Yêu cầu nhập từ khác.
2. Hiển thị thông báo từ khóa không có nội dung tìm kiếm.
3. Trả danh sách mới nhất/phổ biến theo bộ lọc quyền an toàn.
4. Dùng cơ chế khác được thiết kế cho input rỗng.

Đừng vô tình chấm điểm toàn corpus hoặc tạo hàng nghìn `ts_headline` chỉ vì input thiếu lexeme.

## 19. Tie-breaker giúp kết quả ổn định

Nếu hai tài liệu có cùng score, `ORDER BY score DESC` **không cam kết thứ tự tương đối** giữa chúng.

Thêm:

~~~sql
ORDER BY
    relevance_score DESC,
    published_at DESC,
    article_id DESC
~~~

Trong đó `article_id` duy nhất để phá ties. Điều này hữu ích cho giao diện, kiểm thử và phân trang.

Một lựa chọn khác là ưu tiên tài liệu mới trước rồi mới so rank, nhưng đó là **chính sách tìm kiếm khác**. Phải quyết định có chủ ý.

## 20. Kết hợp relevance với freshness/popularity

Một số ứng dụng cần kết hợp điểm văn bản với tín hiệu ngoài FTS.

\[
S_{\mathrm{total}} =
\alpha S_{\mathrm{text}} +
\beta S_{\mathrm{freshness}} +
\gamma S_{\mathrm{quality}}
\]

Đây là một mô hình khái niệm, **không phải công thức mặc định PostgreSQL**. Muốn cộng các thành phần phải hiệu chỉnh thang đo, kiểm soát gaming/manipulation và đánh giá bằng dữ liệu có nhãn.

Đặc biệt:

- **Authorization/tenant/is_published** phải là filter, không phải boost.
- Một bài mới nhưng không liên quan không nên tự thắng bài đúng nhu cầu chỉ vì freshness lớn.
- `ts_rank` là điểm từ vựng, không phải xác suất.

## 21. ts_headline tạo đoạn trích từ văn bản gốc

~~~sql
SELECT ts_headline(
    'english'::regconfig,
    'PostgreSQL full text search improves search results.',
    plainto_tsquery(
        'english'::regconfig,
        'search results'
    )
) AS highlighted_text;
~~~

`ts_headline` nhận **text gốc** và `tsquery`, chọn một đoạn text chứa các từ khớp và thêm marker. Giá trị `tsvector` vốn được chuẩn hóa thành lexeme/vị trí, không phù hợp dùng làm đoạn hiển thị nguyên văn.

Các marker mặc định có thể là markup dạng `<b>`, tùy options.

## 22. Tùy chỉnh marker StartSel và StopSel

~~~sql
SELECT ts_headline(
    'english'::regconfig,
    'Search ranking improves search results.',
    websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ),
    'StartSel=<mark>,StopSel=</mark>'
) AS snippet;
~~~

Ý nghĩa output:

~~~text
<mark>Search</mark> <mark>ranking</mark>
improves <mark>search</mark> results.
~~~

Output có marker là **text**, chưa phải HTML an toàn. Có thể dùng marker kiểu `[[...]]` cho giao diện plain text, hoặc xây renderer trả các text segments và trạng thái highlight riêng.

## 23. Tạo snippet ngắn với MaxFragments

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    a.title,
    ts_headline(
        'english'::regconfig,
        a.body,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,'
            || 'MaxFragments=2,MinWords=5,MaxWords=18,'
            || 'FragmentDelimiter=...'
    ) AS snippet
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.article_id = 2;
~~~

| Option | Ý nghĩa |
| --- | --- |
| `StartSel` | Marker mở |
| `StopSel` | Marker đóng |
| `MaxFragments` | Số fragment tối đa |
| `MinWords` | Số từ tối thiểu theo cơ chế fragment |
| `MaxWords` | Giới hạn độ dài theo cơ chế fragment |
| `FragmentDelimiter` | Ngăn cách giữa các fragment |
| `HighlightAll` | Chế độ highlight toàn văn |
| `ShortWord` | Cách xử lý từ ngắn |

Số từ đầu ra và vị trí fragment phụ thuộc thuật toán/chế độ của `ts_headline`, không nhất thiết đúng số ký tự/từ cố định. Cần thử với body thực tế.

## 24. Highlight title và body theo cách riêng

~~~sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
)
SELECT
    a.article_id,
    ts_headline(
        'english'::regconfig,
        a.title,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,HighlightAll=true'
    ) AS highlighted_title,
    ts_headline(
        'english'::regconfig,
        a.body,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,'
            || 'MaxFragments=2,MinWords=6,MaxWords=24'
    ) AS body_snippet
FROM fts_rank_lab.articles AS a
CROSS JOIN q
WHERE a.article_id = 1;
~~~

Title ngắn có thể dùng `HighlightAll=true`; body dài nên dùng snippet fragment.

### Có trường hợp tài liệu khớp nhưng body không highlight?

Có. Matching dùng vector kết hợp title, summary, category và body. Tài liệu có thể khớp từ khóa ở **title** nhưng **không có từ đó trong body**. `ts_headline(body, ...)` khi đó có thể không đánh dấu gì.

Giao diện nên highlight cả title và summary khi phù hợp, thay vì coi body snippet là bằng chứng duy nhất rằng tài liệu khớp.

## 25. XSS: ts_headline không tự sanitize HTML

Đây là điểm an toàn bắt buộc khi đưa kết quả tới trình duyệt.

`ts_headline` **không phải HTML sanitizer**. Văn bản gốc trong database có thể chứa HTML hay ký tự do người dùng/nguồn ngoài cung cấp. Hàm chèn marker vào text; nó không đảm bảo mọi ký tự khác đã được escape.

Nếu frontend đưa output raw vào `innerHTML`, có nguy cơ HTML injection và **cross-site scripting (XSS)**.

**Quy tắc an toàn:**

1. Coi cả snippet và title là dữ liệu không tin cậy.
2. Không render trực tiếp output `ts_headline` như HTML đã được chứng nhận sạch.
3. Nếu cần rich markup, dùng sanitizer/escaping đúng ngữ cảnh, chỉ cho phép các thẻ/thuộc tính đã được kiểm soát.
4. Ưu tiên renderer tạo **text nodes** và thẻ `mark` riêng theo các đoạn highlight đã được phân tích an toàn.
5. Không tự dùng regex sơ sài để “xóa các thẻ nguy hiểm”.

### SQL injection và XSS khác nhau

- **SQL injection**: input bị đưa vào câu SQL không an toàn; phòng bằng parameterized queries.
- **XSS**: output không tin cậy được hiển thị trong trình duyệt không an toàn; phòng bằng output encoding/safe rendering.

Có thể chống SQL injection tốt nhưng vẫn gặp XSS nếu render `ts_headline` raw.

## 26. Xếp hạng trước, highlight sau LIMIT

Một lỗi hiệu năng phổ biến là tạo `ts_headline` cho 100.000 ứng viên rồi chỉ hiển thị 20 kết quả.

`ts_headline` có thể phải phân tích text gốc và tìm fragment, tốn CPU/I/O. Nên:

1. Match tài liệu bằng `@@`.
2. Tính `ts_rank`/`ts_rank_cd`.
3. Sort và `LIMIT 20`.
4. Chỉ highlight 20 kết quả.

Ví dụ:

~~~sql
WITH
q AS MATERIALIZED (
    SELECT websearch_to_tsquery(
        'english'::regconfig,
        'search ranking'
    ) AS search_query
),
top_hits AS MATERIALIZED (
    SELECT
        a.article_id,
        a.published_at,
        ts_rank_cd(
            ARRAY[0.10, 0.20, 0.40, 1.00]::real[],
            a.search_vector,
            q.search_query,
            32
        ) AS score
    FROM fts_rank_lab.articles AS a
    CROSS JOIN q
    WHERE a.is_published
      AND a.search_vector @@ q.search_query
    ORDER BY
        score DESC,
        a.published_at DESC,
        a.article_id DESC
    LIMIT 20
)
SELECT
    a.article_id,
    a.title,
    h.score,
    ts_headline(
        'english'::regconfig,
        a.title,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,HighlightAll=true'
    ) AS highlighted_title,
    ts_headline(
        'english'::regconfig,
        a.body,
        q.search_query,
        'StartSel=<mark>,StopSel=</mark>,'
            || 'MaxFragments=2,MinWords=6,MaxWords=24'
    ) AS body_snippet
FROM top_hits AS h
JOIN fts_rank_lab.articles AS a
    ON a.article_id = h.article_id
CROSS JOIN q
ORDER BY
    h.score DESC,
    h.published_at DESC,
    a.article_id DESC;
~~~

### Vì sao dùng MATERIALIZED?

Ở PostgreSQL 12+, CTE có thể được inlined theo điều kiện. `MATERIALIZED` ở đây làm rõ việc tính `top_hits` trước khi gọi `ts_headline` bên ngoài.

**MATERIALIZED không phải mẹo luôn tốt:** nó có thể cản tối ưu pushdown khác. Dùng khi có chủ đích và đo với `EXPLAIN`.

`LIMIT` vẫn không giúp bỏ toàn bộ công việc tính rank: nếu rất nhiều tài liệu khớp, server có thể cần chấm điểm nhiều ứng viên để tìm top 20.

## 27. JDBC: dùng bind parameter cho input người dùng

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void search(
        Connection connection,
        String userQuery
) throws SQLException {

    String sql = """
        WITH q AS (
            SELECT websearch_to_tsquery(
                'english'::regconfig,
                ?
            ) AS search_query
        )
        SELECT
            a.article_id,
            a.title,
            ts_rank(
                a.search_vector,
                q.search_query
            ) AS score
        FROM fts_rank_lab.articles AS a
        CROSS JOIN q
        WHERE a.is_published
          AND a.search_vector @@ q.search_query
        ORDER BY score DESC, a.article_id DESC
        LIMIT 20
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setString(1, userQuery);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                long id = rs.getLong("article_id");
                String title = rs.getString("title");
                float score = rs.getFloat("score");
                System.out.println(
                    id + ": " + title + " (" + score + ")"
                );
            }
        }
    }
}
~~~

JDBC dùng `?` và `setString`. Không xây SQL bằng nối chuỗi chứa từ khóa. Khi triển khai thật, bổ sung bộ lọc quyền, kiểm soát input rỗng, giới hạn kết quả, timeout và renderer an toàn.

## 28. GIN không sắp sẵn theo rank

GIN index trên `search_vector` giúp tìm lexeme. Điểm ranking phụ thuộc vào **tsquery cụ thể của người dùng** nên không có một thứ tự score cố định để GIN trả top-N trực tiếp.

Một plan có thể về mặt khái niệm:

~~~text
Bitmap Index Scan on GIN
  -> Bitmap Heap Scan lấy ứng viên
     -> Tính ts_rank / ts_rank_cd
        -> Sort score DESC
           -> Limit
~~~

Không bắt buộc mọi plan có đúng những node đó. Với query rất rộng hoặc table nhỏ, PostgreSQL có thể chọn `Seq Scan`.

**Không coi việc xuất hiện Sort tự động là dấu hiệu sai**, vì query-dependent score thường cần tính và sắp xếp.

## 29. Benchmark trên bảng lớn hơn

Bảng 12 hàng phù hợp học cú pháp nhưng không đại diện cho một hệ thống nhiều triệu tài liệu. Tạo một bảng bench riêng:

~~~sql
CREATE TABLE fts_rank_lab.search_bench (
    article_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('english'::regconfig, title),
            'A'
        )
        ||
        setweight(
            to_tsvector('english'::regconfig, body),
            'D'
        )
    ) STORED
);

INSERT INTO fts_rank_lab.search_bench (
    article_id, title, body
)
SELECT
    g::bigint,
    CASE
        WHEN g % 500 = 0
            THEN 'Search ranking explained'
        WHEN g % 13 = 0
            THEN 'PostgreSQL query guide'
        ELSE 'Technical article ' || g
    END,
    CASE
        WHEN g % 500 = 0
            THEN 'Full text search ranking and highlighting'
        WHEN g % 13 = 0
            THEN 'A guide to efficient database indexing'
        ELSE
            'Background notes about database design '
            || 'and application development'
    END
FROM generate_series(1, 50000) AS s(g);

ANALYZE fts_rank_lab.search_bench;
~~~

Baseline:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id
FROM fts_rank_lab.search_bench
WHERE search_vector @@ plainto_tsquery(
    'english'::regconfig,
    'search ranking'
);
~~~

Thêm index:

~~~sql
CREATE INDEX idx_search_bench_vector_gin
ON fts_rank_lab.search_bench
USING gin (search_vector);

ANALYZE fts_rank_lab.search_bench;
~~~

Đo lại cùng SQL. Không đoán trước số mili giây vì còn phụ thuộc CPU, cache, disk, thống kê và cấu hình.

### Truy vấn phổ biến có thể có plan khác

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id
FROM fts_rank_lab.search_bench
WHERE search_vector @@ plainto_tsquery(
    'english'::regconfig,
    'database'
);
~~~

Một từ rất phổ biến có thể khớp phần lớn hàng, làm giảm lợi ích index. Cần kiểm tra từng nhóm query phổ biến/hiếm theo workload thật.

## 30. Đọc EXPLAIN cho FTS

Các dấu hiệu cần xem:

| Node/thông tin | Ý nghĩa cần kiểm tra |
| --- | --- |
| `Seq Scan` | Bảng nhỏ hoặc matching quá rộng? |
| `Bitmap Index Scan` | Điều kiện `@@` dùng GIN được không? |
| `Bitmap Heap Scan` | Bao nhiêu heap block/tuple được đọc? |
| `Index Cond` | Những điều kiện nào được đẩy vào index? |
| `Recheck Cond` | Có cần kiểm tra lại do weight/bitmap/operator? |
| `Filter` | Có loại nhiều tài liệu vì trạng thái/quyền? |
| `Sort Key` | Có sort theo rank đúng không? |
| `Sort Method` | Top-N heapsort hay dùng temp disk? |
| `Buffers: shared hit/read` | Hoạt động buffer như thế nào? |
| `Execution Time` | Server mất bao lâu trong lần chạy này? |

`shared read` không nhất thiết là disk physical read; nó có thể đến từ OS page cache.

`EXPLAIN ANALYZE` đo một lần thực thi, có overhead và không tương đương p95/p99 độ trễ end-to-end của API. Để đo SLO, cần telemetry/load benchmark phù hợp.

## 31. Chi phí cập nhật search_vector và GIN

Với stored generated `search_vector` và GIN index:

~~~sql
BEGIN;

UPDATE fts_rank_lab.articles
SET title = 'Advanced PostgreSQL search ranking'
WHERE article_id = 2
RETURNING
    article_id, title, search_vector;

ROLLBACK;
~~~

Khi tiêu đề thay đổi, giá trị generated cần được duy trì, và GIN index có thể phải cập nhật entry.

Các chi phí có thể có:

- CPU để tạo lexeme và weights.
- Row version mới theo MVCC.
- Index maintenance.
- WAL và dirty pages.
- VACUUM và cleanup phiên bản cũ.
- Cạnh tranh I/O/cache khi số bài được cập nhật lớn.

Một index giúp SELECT nhanh nhưng làm INSERT/UPDATE đắt hơn là một trade-off cần đo. Kho tài liệu chỉ nhập một lần rồi đọc rất nhiều có thể chấp nhận chi phí này; hệ thống chỉnh sửa nội dung liên tục cần thận trọng hơn.

### Đo index size và thống kê

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size(
            'fts_rank_lab.idx_search_bench_vector_gin'::regclass
        )
    ) AS gin_size;
~~~

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'fts_rank_lab'
ORDER BY relname, indexrelname;
~~~

Đừng xóa index vì `idx_scan=0` sau một khoảng ngắn. Thống kê có thể chưa bao phủ các đợt tìm kiếm quan trọng, hoặc vừa reset.

## 32. Chất lượng ranking cần bộ dữ liệu gán nhãn

Có hai loại kiểm thử riêng:

**Quality test:** một tập query tiêu biểu có các tài liệu được chấm mức liên quan. Có thể dùng Precision@K, Recall@K, MRR hoặc NDCG@K.

**Performance test:** corpus lớn, tần suất từ phổ biến/hiếm, nhiều clients, đo p50/p95/p99, buffers, CPU/WAL, index size và chi phí ghi.

Ví dụ:

| Query | Kết quả nên ưu tiên |
| --- | --- |
| `search ranking` | Bài giải thích ranking/trọng số |
| `postgresql indexes` | Bài về GIN/text search indexing |
| `transaction locks` | Bài về concurrency/lock waits |
| `search highlighting` | Bài về `ts_headline` |
| `product relevance` | Bài về thứ tự kết quả sản phẩm |

Không chọn mảng weights chỉ dựa vào một query trông đẹp. Thay weights có thể làm tốt một truy vấn nhưng làm hỏng nhiều truy vấn khác.

## 33. Phân trang kết quả và sự thay đổi thứ tự

Một câu:

~~~sql
ORDER BY score DESC, published_at DESC, article_id DESC
LIMIT 20 OFFSET 20;
~~~

có thể tốn công khi OFFSET sâu vì vẫn phải xếp hạng/sắp nhiều ứng viên trước khi bỏ qua các hàng đầu.

Nếu corpus đang cập nhật, title/body hoặc ngày xuất bản thay đổi có thể làm score và vị trí bài đổi giữa hai lần lấy trang.

Hướng xử lý:

1. Luôn dùng tie-breaker duy nhất.
2. Giới hạn pagination depth khi cần.
3. Nếu cần search session ổn định, cân nhắc snapshot/result caching hoặc cursor policy.
4. Với keyset theo score, cần dùng cùng query/weights/filters và chú ý kiểu số thực.
5. Định nghĩa UX khi có bài mới hoặc bài bị ẩn giữa hai lần gọi.

Không mặc định kết quả tìm kiếm là danh sách bất biến mãi mãi.

## 34. Ngôn ngữ tiếng Việt và dấu

Văn bản có dấu như:

~~~text
Hướng dẫn tối ưu tìm kiếm văn bản PostgreSQL
~~~

không mặc nhiên khớp truy vấn không dấu:

~~~text
toi uu tim kiem van ban
~~~

nếu chưa có pipeline chuẩn hóa nhất quán.

Các hướng cân nhắc:

- `simple` configuration cho tokenization cơ bản.
- `unaccent` extension nếu môi trường hỗ trợ và quy tắc nghiệp vụ cho phép.
- Dictionary/tokenizer tiếng Việt cho từ ghép.
- Chuẩn hóa Unicode và kiểm tra chữ hoa, dấu, dấu câu.
- Rebuild vector/index khi thay đổi quy tắc phân tích.

Chỉ cài `unaccent` không có nghĩa toàn bộ tsvector và tsquery đã tự chuyển sang cùng quy tắc. Phải cấu hình đúng phía dữ liệu, phía query và cân nhắc highlight trên text gốc.

## 35. Lỗi phổ biến

1. **Nhầm matching với ranking:** `@@` không cho điểm.
2. **Truyền mảng weights sai thứ tự:** phải là D,C,B,A.
3. **Nghĩ title match luôn thắng body match:** score còn nhiều yếu tố.
4. **Coi điểm rank là xác suất:** `0.8` không nghĩa 80% phù hợp.
5. **Dùng ts_rank_cd sau strip:** mất thông tin vị trí.
6. **Dùng khác configuration khi tạo vector/query/headline.**
7. **Mong dictionary english xử lý toàn bộ tiếng Việt.**
8. **Dùng GIN và nghĩ index tự sort theo score.**
9. **Không có tie-breakers khi nhiều bài có cùng score.**
10. **Không lọc bản nháp/tenant/quyền trước khi trả kết quả.**
11. **Gọi ts_headline cho mọi ứng viên trước LIMIT.**
12. **Render raw ts_headline HTML và tạo nguy cơ XSS.**
13. **Nghĩ body luôn có highlight nếu vector tổng đã khớp.**
14. **Ghép user input vào SQL/to_tsquery không kiểm soát.**
15. **Không xử lý input rỗng/stop words.**
16. **Benchmark trên bảng 12 hàng rồi suy hiệu năng production.**
17. **Chỉ đo SELECT, bỏ chi phí INSERT/UPDATE generated vector và GIN.**
18. **Chỉ tối ưu latency, không đo chất lượng kết quả.**
19. **Tune weights theo một query rồi kết luận cho mọi người dùng.**
20. **Dùng MATERIALIZED ở mọi CTE dù có thể cản tối ưu khác.**
21. **Pagination bằng OFFSET sâu và nghĩ LIMIT làm mọi thứ rẻ.**
22. **Nhầm snippet với giải thích đầy đủ của score.**
23. **Quên version PostgreSQL của stored generated columns.**
24. **Thay ranking mà không kiểm thử quyền và độ ổn định kết quả.**

## 36. Bài tập có đáp án

Dùng schema `fts_rank_lab` từ phần lab. Chỉ chạy DDL/DML trong database thực hành; nếu cần UPDATE, bọc `BEGIN ... ROLLBACK`.

### Bài 1. Matching khác ranking thế nào?

**Đáp án:** `@@` trả boolean; `ts_rank`/`ts_rank_cd` tính score cho tài liệu phù hợp.

### Bài 2. Weight mạnh nhất mặc định?

**Đáp án:** A; tiếp theo B, C và D.

### Bài 3. Thứ tự mảng weights?

**Đáp án:** D, C, B, A.

### Bài 4. Tạo title vector A

~~~sql
SELECT setweight(
    to_tsvector('english', 'Search ranking'),
    'A'
);
~~~

**Đáp án:** Các lexeme phù hợp nhận weight A.

### Bài 5. Ghép title và body

~~~sql
SELECT
    setweight(
        to_tsvector('english', 'Search ranking'),
        'A'
    )
    ||
    setweight(
        to_tsvector('english', 'Ranking search results'),
        'D'
    );
~~~

**Đáp án:** Có các lexeme từ hai trường, với nhãn A và D.

### Bài 6. Vì sao coalesce?

**Đáp án:** Trường NULL được thay bằng text rỗng, tránh làm hỏng vector tổng hợp.

### Bài 7. Kiểm tra AND query

~~~sql
SELECT
    to_tsvector('english', 'Search ranking improves results')
    @@
    plainto_tsquery('english', 'search ranking');
~~~

**Đáp án:** `true` khi cả hai lexeme phù hợp.

### Bài 8. Chỉ tìm từ search trong title

~~~sql
SELECT article_id, title
FROM fts_rank_lab.articles
WHERE search_vector @@ to_tsquery(
    'english', 'search:A'
);
~~~

**Đáp án:** Chỉ match vị trí có weight A.

### Bài 9. Vì sao vẫn phải lọc is_published?

**Đáp án:** Matching/rank không bảo đảm quyền hiển thị. Bài 11 chưa được công bố.

### Bài 10. ts_rank_cd khác ts_rank?

**Đáp án:** `ts_rank_cd` dùng cover/proximity; không có hàm luôn thắng mọi corpus.

### Bài 11. Vì sao strip ảnh hưởng cover-density?

**Đáp án:** `strip` bỏ positional information mà `ts_rank_cd` cần.

### Bài 12. Cờ normalization 32?

**Đáp án:** Biến đổi `r/(r+1)`, không biến rank thành xác suất.

### Bài 13. Kết hợp cờ 2 và 32?

**Đáp án:** `34`.

### Bài 14. Phrase query

~~~sql
SELECT phraseto_tsquery(
    'english', 'search ranking'
);
~~~

**Đáp án:** Tạo query với semantics vị trí/phrase.

### Bài 15. Prefix query

~~~sql
SELECT to_tsquery('english', 'rank:*');
~~~

**Đáp án:** Prefix lexeme, khác substring `ILIKE '%ank%'`.

### Bài 16. Highlight title

~~~sql
SELECT ts_headline(
    'english',
    title,
    plainto_tsquery('english', 'search ranking'),
    'StartSel=<mark>,StopSel=</mark>,HighlightAll=true'
)
FROM fts_rank_lab.articles
WHERE article_id = 1;
~~~

**Đáp án:** Tạo text title có marker quanh từ khớp.

### Bài 17. Highlight body với tối đa hai fragments

~~~sql
SELECT ts_headline(
    'english',
    body,
    plainto_tsquery('english', 'search ranking'),
    'StartSel=<mark>,StopSel=</mark>,'
        || 'MaxFragments=2,MinWords=6,MaxWords=20'
)
FROM fts_rank_lab.articles
WHERE article_id = 2;
~~~

**Đáp án:** Trích tối đa hai đoạn theo options và đánh dấu từ phù hợp.

### Bài 18. Có thể render raw HTML từ ts_headline không?

**Đáp án:** Không an toàn. Hàm không sanitize nội dung nguồn; cần output encoding/safe rendering để tránh XSS.

### Bài 19. Vì sao highlight sau LIMIT?

**Đáp án:** Giảm chi phí phân tích text gốc cho những ứng viên không được hiển thị.

### Bài 20. GIN index có sort theo rank không?

**Đáp án:** Không; nó hỗ trợ lexeme matching, score phụ thuộc query.

### Bài 21. Đánh giá relevance bằng gì?

**Đáp án:** Có thể dùng Precision@K, MRR hoặc NDCG@K trên tập query/tài liệu được gán nhãn.

### Bài 22. Query chỉ stop words thì sao?

**Đáp án:** Có thể tạo tsquery rỗng. Kiểm tra `numnode` và xử lý ở ứng dụng.

### Bài 23. Vì sao body không highlight dù tài liệu match?

**Đáp án:** Match có thể đến từ title, summary hoặc category trong vector tổng.

### Bài 24. Tạo GIN index ảnh hưởng UPDATE body?

**Đáp án:** Vector và GIN entries có thể phải được cập nhật, tăng chi phí CPU/I/O/WAL và ảnh hưởng cơ hội HOT.

### Bài 25. Score 0.9 có nghĩa tài liệu phù hợp 90% không?

**Đáp án:** Không, score không được hiệu chỉnh thành xác suất.

### Bài 26. Tại sao phải có tie-breaker?

**Đáp án:** Hai bài cùng score có thể đổi thứ tự. `published_at DESC, article_id DESC` tạo sắp xếp ổn định hơn.

## 37. Checklist trước khi triển khai

- [ ] Xác định ngôn ngữ, tokenizer và text search configuration.
- [ ] Chọn title/summary/category/body, gán weight theo nghiệp vụ.
- [ ] Nhớ mảng weights theo thứ tự **D,C,B,A**.
- [ ] Dùng `coalesce` cho trường text có thể NULL.
- [ ] Cân nhắc generated vector hoặc expression index theo workload/version.
- [ ] Tạo GIN cho `@@` khi selectivity và dữ liệu đủ lớn.
- [ ] Dùng bind parameters và hàm parse tsquery phù hợp.
- [ ] Xử lý empty/stopword/broad queries.
- [ ] Lọc tenant, permission và is_published.
- [ ] Tính rank với weights và normalization được kiểm thử.
- [ ] Thử phrase/proximity và title-only query theo yêu cầu.
- [ ] Sắp xếp rank DESC kèm tie-breaker duy nhất.
- [ ] Tạo snippet sau LIMIT, không trước.
- [ ] Dùng text gốc và cùng configuration cho `ts_headline`.
- [ ] Không render output headline raw như HTML đáng tin.
- [ ] Hiểu field match có thể khác field snippet.
- [ ] Đo EXPLAIN/BUFFERS với corpus đủ lớn.
- [ ] Đo quality top-K, không chỉ response time.
- [ ] Đo write overhead, GIN size và WAL khi dữ liệu cập nhật.
- [ ] Kiểm thử Unicode, tiếng Việt có dấu và không dấu.
- [ ] Có kế hoạch rebuild vector/index khi đổi configuration.
- [ ] Có phương án cho pagination, dữ liệu mới và tài liệu bị ẩn.
- [ ] Ghi PostgreSQL major version và weights để tái lập.
- [ ] Không hy sinh bảo mật hoặc SLO ghi để tăng điểm rank.

## 38. Tài liệu PostgreSQL chính thức

Tra tài liệu **đúng major version** của server:

- [Full Text Search](https://www.postgresql.org/docs/current/textsearch.html) — tổng quan FTS.
- [Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html) — matching, weighting, ranking, highlighting.
- [Text Search Functions and Operators](https://www.postgresql.org/docs/current/functions-textsearch.html) — `setweight`, `ts_rank`, `ts_rank_cd`, `ts_headline`, `numnode`.
- [Preferred Index Types for Text Search](https://www.postgresql.org/docs/current/textsearch-indexes.html) — GIN/GiST.
- [Text Search Configuration](https://www.postgresql.org/docs/current/textsearch-configuration.html) — dictionary/parser.
- [Unaccent](https://www.postgresql.org/docs/current/unaccent.html) — hỗ trợ xử lý dấu theo cấu hình phù hợp.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html) — stored generated tsvector.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html) — expression indexes.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — scan, sort, buffers.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index build và maintenance.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — thống kê index/table.

`/current/` trỏ tới tài liệu PostgreSQL hiện hành; với server cũ, kiểm tra giới hạn stored generated columns, MATERIALIZED CTE và các tùy chọn cụ thể theo version.

## 39. Tổng kết

**Trọng số, rank và highlight giải quyết ba vấn đề bổ sung nhau nhưng không thể thay thế nhau.**

1. **`tsvector @@ tsquery`** quyết định tài liệu nào khớp.
2. **`setweight`** phân biệt field A/B/C/D; cách tính điểm thực tế thuộc `ts_rank`/`ts_rank_cd`.
3. **Thứ tự mảng weights là D,C,B,A**. Đảo ngược có thể ưu tiên nhầm body thay vì title.
4. **`ts_rank_cd`** xét cover/proximity, cần positional information; `strip` có thể làm mất dữ liệu cần thiết.
5. **Normalization** đổi thang điểm nhưng không làm rank thành xác suất.
6. **GIN hỗ trợ matching nhưng không sort sẵn theo rank**. Cần đánh giá cả plan và chất lượng thứ tự.
7. **`ts_headline` làm nổi bật đoạn text gốc**; nên chạy sau khi đã chọn top-N và phải render an toàn tránh XSS.
8. **Cấu hình FTS phải nhất quán** ở vector, query và headline, nhất là khi triển khai tiếng Việt.
9. **Ranking không thay permission filters**. Chỉ xếp hạng những tài liệu người dùng có quyền xem.
10. **Đo cả relevance và performance**, bao gồm độ trễ, index size, WAL và chi phí cập nhật.

Khi kết hợp đúng **trọng số trường, chấm điểm, sắp xếp ổn định và snippet an toàn**, PostgreSQL có thể cung cấp tìm kiếm văn bản phù hợp nhu cầu, dễ giải thích và có chi phí vận hành được kiểm soát.
