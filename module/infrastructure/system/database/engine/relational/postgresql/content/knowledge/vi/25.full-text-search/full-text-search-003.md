# tsvector, tsquery và luồng xử lý tìm kiếm toàn văn

Khi người dùng gõ “tối ưu truy vấn PostgreSQL” vào ô tìm kiếm, họ muốn thấy những bài học có **nội dung liên quan**, chứ không chỉ các hàng chứa nguyên vẹn một chuỗi ký tự. Họ còn cần lọc tài liệu theo tổ chức và quyền truy cập, tìm cụm từ, xếp hạng kết quả, hiển thị đoạn trích và trả kết quả nhanh trên tập dữ liệu lớn.

PostgreSQL hỗ trợ **Full-Text Search (FTS)** ngay trong cơ sở dữ liệu quan hệ. Hai kiểu dữ liệu cốt lõi là:

- **`tsvector`**: biểu diễn văn bản thành các **lexeme** (đơn vị từ vựng sau khi phân tích/chuẩn hóa), có thể mang vị trí và trọng số.
- **`tsquery`**: biểu diễn điều kiện tìm kiếm trên lexeme bằng phép toán AND, OR, NOT, cụm từ, khoảng cách và tiền tố.

Toán tử **`@@`** kiểm tra vector có khớp với truy vấn hay không. Nhưng một hệ thống tìm kiếm thực tế còn cần phân tích ngôn ngữ, index GIN, ranking, snippets, phân trang, chống SQL injection, quản lý quyền truy cập và cơ chế cập nhật vector nhất quán.

> **Môi trường:** Bài dùng PostgreSQL hiện đại; một số cú pháp như JSONPath có giới hạn phiên bản nhưng không phải trọng tâm bài này. Các ví dụ tiếng Việt dùng `pg_catalog.simple` để minh họa; cấu hình này **không phải bộ tách từ hoặc stemming tiếng Việt đầy đủ**. Kết quả tokenization/ranking/plan có thể khác theo cấu hình, dữ liệu và phiên bản. Hãy chạy SQL tạo bảng/index ở database thực hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích pipeline **source text → parser/dictionary → tsvector → GIN → tsquery → @@ → rank → snippet**.
2. Phân biệt full-text search với `LIKE`, `ILIKE`, trigram và semantic search.
3. Dùng `to_tsvector`, `ts_debug`, `setweight`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery` và `to_tsquery`.
4. Viết các điều kiện `@@` kết hợp tenant, trạng thái, thời gian và quyền truy cập.
5. Tạo **stored generated tsvector column** và chỉ mục GIN đúng cấu hình.
6. Xếp hạng bằng `ts_rank`/`ts_rank_cd` và hiển thị kết quả với `ts_headline` an toàn.
7. Hiểu phrase search, prefix, stop words, từ đồng nghĩa và giới hạn với tiếng Việt.
8. Chọn generated column, expression index, trigger hoặc bảng projection tìm kiếm.
9. Đọc `EXPLAIN (ANALYZE, BUFFERS)`, benchmark và chẩn đoán các trường hợp tìm không ra/chậm.
10. Kết nối Java/JDBC/Spring mà không ghép SQL hoặc làm lộ tài liệu sai quyền.

## 2. Tìm kiếm toàn văn khác LIKE như thế nào?

Truy vấn:

```sql
SELECT *
FROM articles
WHERE body ILIKE '%index%';
```

là phép tìm **chuỗi con**, không phải tìm theo đơn vị từ vựng. Nó có ích khi cần khớp ký tự, nhưng không tự làm stemming, loại stop words, đánh trọng số title/body hoặc xếp hạng tài liệu.

Với FTS:

```sql
SELECT *
FROM articles
WHERE search_vector @@
      plainto_tsquery('pg_catalog.simple', 'postgresql index');
```

`search_vector` giả định là cột `tsvector` đã tạo. Từ khóa được chuyển thành `tsquery`, sau đó engine kiểm tra lexemes và có thể sử dụng GIN index.

### FTS không phải fuzzy hay semantic search

- **FTS**: khớp lexical terms, dictionaries, phrase, weights.
- **`LIKE/ILIKE`**: khớp chuỗi theo mẫu.
- **`pg_trgm`**: có thể hỗ trợ độ giống ký tự, substring, lỗi gõ theo mức ký tự.
- **Semantic/vector search**: dựa trên biểu diễn ngữ nghĩa/embedding nếu hệ thống có triển khai.

Một phương án có thể kết hợp các lớp trên. Không kỳ vọng `to_tsvector` tự hiểu ý nghĩa xa, từ đồng nghĩa ngoài dictionary hoặc mọi lỗi chính tả.

## 3. Sơ đồ luồng tìm kiếm

```text
                Nguồn: title / summary / body
                              │
                              ▼
                   Text search configuration
                        parser + dictionary
                              │
                              ▼
                           tsvector
                     lexeme, position, weight
                              │
                              ▼
                           GIN index
                              │
User input ──► query constructor ──► tsquery
                              │
                              ▼
                      @@ tìm ứng viên
                              │
                 tenant / status / ACL filter
                              │
                              ▼
                    ts_rank / ts_rank_cd
                              │
                              ▼
                 sort + LIMIT + ts_headline
                              │
                              ▼
                       API search result
```

Quan trọng nhất là **nhất quán giữa cấu hình phân tích tài liệu và phân tích câu tìm kiếm**. Nếu vector được tạo bằng `english` nhưng query được phân tích bằng `simple`, hai bên có thể dùng lexemes khác nhau.

## 4. Parser, token, dictionary và lexeme

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Document | Văn bản đầu vào | “The runners are running” |
| Parser | Nhận diện các token types | Word, number, email, URL |
| Token | Đơn vị parser tách được | “running” |
| Dictionary | Chuẩn hóa/loại token | Stemming hoặc stop word |
| Lexeme | Đơn vị được lưu/truy vấn | “run” trong cấu hình tiếng Anh |
| Text search configuration | Gắn parser/dictionary với token types | `simple`, `english` |
| `tsvector` | Chỉ mục hóa lexemes của document | `'run':...` |
| `tsquery` | Biểu thức kiểm tra các lexemes | `'run' & 'index'` |

Ví dụ:

```sql
SELECT
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        'running runs'
    ) AS simple_vector,
    to_tsvector(
        'pg_catalog.english'::regconfig,
        'running runs'
    ) AS english_vector;
```

Với `simple`, các từ thường giữ hình thức gần nguyên bản; với `english`, stemming có thể tạo lexeme chung. Không tự suy diễn một từ sẽ được stem thành dạng nào khi chưa kiểm tra cấu hình server.

## 5. Chọn text search configuration

Kiểm tra:

```sql
SHOW default_text_search_config;

SELECT current_setting('default_text_search_config');
```

Hai lựa chọn phổ biến:

- `pg_catalog.simple`: cấu hình đơn giản, phù hợp để học và cho một số corpus không cần stemming đặc thù.
- `pg_catalog.english`: phân tích tiếng Anh với stop words/stemming.

Nên **ghi rõ config**:

```sql
SELECT to_tsvector(
    'pg_catalog.simple'::regconfig,
    'Tìm kiếm toàn văn trong PostgreSQL'
);
```

Việc phụ thuộc `default_text_search_config` trong công thức index/generation dễ gây bất nhất giữa session hoặc môi trường. Với expression index và stored generated column, dạng `to_tsvector(regconfig,text)` chỉ rõ cấu hình còn đáp ứng tính xác định cần thiết của biểu thức.

## 6. Phân tích một chuỗi bằng ts_debug

```sql
SELECT *
FROM ts_debug(
    'pg_catalog.english'::regconfig,
    'The runners are running through indexes'
);
```

`ts_debug` cho thấy:

- Token được nhận diện.
- Loại token/alias.
- Dictionary được thử.
- Lexeme được tạo ra hoặc bị loại.

Đây là công cụ đầu tiên khi một từ xuất hiện trong tài liệu nhưng tìm không ra.

### Stop words

Các từ như `the`, `and`, `of` có thể bị loại trong cấu hình english. Với cấu hình khác, chúng có thể vẫn được giữ. Đừng nhầm **stop words** với những từ bị ngăn vì quyền truy cập; đó là hai loại logic độc lập.

## 7. tsvector chứa lexeme và vị trí

```sql
SELECT to_tsvector(
    'pg_catalog.simple'::regconfig,
    'PostgreSQL database PostgreSQL indexing'
) AS document_vector;
```

Biểu diễn có dạng:

```text
'database':2 'indexing':4 'postgresql':1,3
```

Các vị trí sau dấu hai chấm cho biết lexeme đã xuất hiện ở đâu trong chuỗi sau phân tích. Một lexeme có thể xuất hiện nhiều vị trí.

### Không dùng tsvector để tái dựng văn bản gốc

Vector không giữ nguyên formatting, dấu câu, toàn bộ stop words hay cách viết nguyên bản. Cần giữ `title`/`body` gốc cho hiển thị, audit và `ts_headline`.

### Vị trí quan trọng vì sao?

Vị trí cho phép truy vấn cụm từ và một số phương pháp ranking chú ý tới khoảng cách giữa các lexemes. `ts_rank_cd` đặc biệt dựa vào thông tin vị trí; loại bỏ positions có thể ảnh hưởng mạnh tới kết quả.

## 8. Trọng số A, B, C, D cho nhiều trường

Một từ trong **tiêu đề** thường quan trọng hơn từ đó nằm sâu trong **nội dung**. PostgreSQL cho phép gán weight:

- `A`: ưu tiên cao (ví dụ title).
- `B`: tiếp theo (summary).
- `C`: một nhóm trung gian khác.
- `D`: mặc định (body).

```sql
SELECT
    setweight(
        to_tsvector('pg_catalog.simple', 'GIN index PostgreSQL'),
        'A'
    )
    ||
    setweight(
        to_tsvector(
            'pg_catalog.simple',
            'Tìm kiếm toàn văn dùng chỉ mục GIN'
        ),
        'D'
    ) AS weighted_vector;
```

`||` nối hai vectors, phối hợp vị trí phù hợp. Gán weights **trước** khi nối nếu muốn phân biệt trường.

### Không phải điểm relevance tuyệt đối

Weight A không tự đảm bảo mọi title match luôn đứng trên mọi body match. Kết quả còn phụ thuộc hàm rank, tần suất, positions và normalization.

## 9. tsquery: các phép toán cốt lõi

| Toán tử | Nghĩa | Ví dụ |
|---|---|---|
| `&` | AND | `postgresql & index` |
| `\|` | OR | `postgresql \| mysql` |
| `!` | NOT | `postgresql & !mysql` |
| `<->` | Lexemes liền kề | `postgresql <-> index` |
| `<N>` | Khoảng cách vị trí cụ thể | `postgresql <2> index` |
| `:*` | Prefix lexeme | `postgres:*` |

Ví dụ:

```sql
SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql & index'
);

SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql | mysql'
);

SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql & !mysql'
);
```

`to_tsquery` nhận biểu thức theo cú pháp đặc thù, không phải một “câu nói” bất kỳ. Các ký tự toán tử thiếu ngữ cảnh hoặc cú pháp sai có thể gây exception.

## 10. Bốn cách tạo tsquery

| Hàm | Cách hiểu input | Dùng khi |
|---|---|---|
| `plainto_tsquery` | Văn bản thông thường, các lexemes thường nối AND | Ô search đơn giản |
| `phraseto_tsquery` | Quan hệ vị trí/cụm từ, xét stopword gaps | Tìm một cụm |
| `websearch_to_tsquery` | Cú pháp tìm kiếm kiểu web: dấu ngoặc kép, OR, dấu trừ | Ô search public |
| `to_tsquery` | Biểu thức query có AND/OR/NOT/prefix/weights | Search nâng cao có kiểm soát |

```sql
SELECT
    plainto_tsquery(
        'pg_catalog.simple',
        'PostgreSQL index'
    ) AS plain_q,
    phraseto_tsquery(
        'pg_catalog.simple',
        'PostgreSQL index'
    ) AS phrase_q,
    websearch_to_tsquery(
        'pg_catalog.simple',
        '"PostgreSQL index" OR tuning'
    ) AS web_q;
```

### Quy tắc sử dụng

Với input người dùng tự do, thường ưu tiên `plainto_tsquery` hoặc `websearch_to_tsquery`. `to_tsquery` thích hợp hơn khi **hệ thống chủ động xây** các thành phần và đã kiểm tra cú pháp.

## 11. Phrase search và positions

```sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'Hướng dẫn tối ưu truy vấn PostgreSQL'
    )
    @@
    phraseto_tsquery(
        'pg_catalog.simple',
        'tối ưu truy vấn'
    ) AS phrase_match;
```

Nếu các lexemes liên tiếp theo đúng thứ tự, câu query có thể match. `phraseto_tsquery` hiểu khoảng cách vị trí khi stop words bị loại, khác với tự nối `<->` dựa trên whitespace.

**Phrase matching không phải exact substring:** tokenization, dấu câu, stemming và stop words có thể khiến hai biểu diễn khác nhau nhưng có cùng lexeme sequence, hoặc ngược lại.

Nếu sản phẩm cần đúng chuỗi ký tự nguyên văn, hãy xem `LIKE/ILIKE` hoặc `pg_trgm` bên cạnh FTS.

## 12. Prefix không tự sửa lỗi chính tả

```sql
SELECT to_tsquery(
    'pg_catalog.simple',
    'postgres:*'
);
```

`:*` là **prefix search** trên lexeme, không phải:

- Substring tìm ở giữa từ.
- Edit distance hoặc fuzzy matching.
- Một bộ gợi ý chính tả.
- Một hệ thống hiểu từ đồng nghĩa.

Truy vấn prefix quá ngắn có thể có tập kết quả rất lớn; cần giới hạn input/độ dài prefix cho UX thực tế.

## 13. Query phủ định và truy vấn quá rộng

```sql
SELECT to_tsquery(
    'pg_catalog.simple',
    'postgresql & !mysql'
);
```

đòi PostgreSQL xuất hiện nhưng MySQL không xuất hiện.

Ngược lại, chỉ dùng:

```sql
SELECT to_tsquery('pg_catalog.simple', '!mysql');
```

không có lexeme dương để tra cứu chọn lọc, nên có thể dẫn tới nhiều công việc.

`querytree` giúp quan sát phần có thể dùng cho index scan:

```sql
SELECT querytree(
    to_tsquery(
        'pg_catalog.simple',
        'postgresql & !mysql'
    )
);
```

Không xem `querytree` như lời đảm bảo planner chọn index hay toàn bộ phép đánh giá chi phí.

## 14. Xử lý input rỗng hoặc chỉ có stop words

```sql
SELECT numnode(
    plainto_tsquery(
        'pg_catalog.english',
        'the and of'
    )
) AS number_of_nodes;
```

Một query tiếng Anh chỉ chứa stop words có thể không còn lexemes hữu ích. Ứng dụng cần chính sách:

- Báo nhập từ khóa có ích.
- Trả danh sách rỗng với thông báo rõ.
- Cho phép một search mode thay thế có kiểm soát.

**Không tự chuyển query rỗng thành truy vấn lấy toàn bộ hàng** nếu nghiệp vụ không chủ ý như vậy.

## 15. SQL lab: thiết lập schema

```sql
CREATE SCHEMA IF NOT EXISTS lesson_fts;
```

Một bảng tài liệu đa tenant:

```sql
CREATE TABLE lesson_fts.articles (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    body TEXT NOT NULL,
    language_code TEXT NOT NULL DEFAULT 'vi'
        CHECK (language_code IN ('vi','en')),
    status TEXT NOT NULL DEFAULT 'PUBLISHED'
        CHECK (status IN ('DRAFT','PUBLISHED')),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(
            to_tsvector(
                'pg_catalog.simple'::regconfig,
                title
            ),
            'A'
        )
        ||
        setweight(
            to_tsvector(
                'pg_catalog.simple'::regconfig,
                COALESCE(summary, '')
            ),
            'B'
        )
        ||
        setweight(
            to_tsvector(
                'pg_catalog.simple'::regconfig,
                body
            ),
            'D'
        )
    ) STORED,
    CONSTRAINT uq_articles_tenant_slug
        UNIQUE (tenant_id, slug)
);
```

### Vì sao dùng STORED GENERATED?

Khi INSERT/UPDATE title, summary hoặc body, PostgreSQL tự tính lại vector theo expression. Ứng dụng không phải duy trì riêng một cột text search vector bằng tay.

Config `simple` được cố định cho **cả vi và en trong lab** để tập trung vào cơ chế. Cột `language_code` chỉ là metadata ở ví dụ này, chưa tự chọn analyzer theo mỗi hàng.

## 16. Dữ liệu thử nghiệm

```sql
INSERT INTO lesson_fts.articles (
    tenant_id, slug, title, summary, body,
    language_code, status, published_at
)
VALUES
    (
      10, 'postgres-index',
      'Chỉ mục PostgreSQL',
      'Hướng dẫn tạo và chọn chỉ mục',
      'PostgreSQL hỗ trợ B-tree và GIN index. Chỉ mục giúp truy vấn lọc dữ liệu hiệu quả.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-01 09:00:00+07'
    ),
    (
      10, 'query-tuning',
      'Tối ưu truy vấn PostgreSQL',
      'Đọc EXPLAIN ANALYZE và đánh giá index',
      'Tối ưu truy vấn cần xem thống kê, chỉ mục, bộ nhớ và thời gian thực thi.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-02 09:00:00+07'
    ),
    (
      10, 'row-locks',
      'Giao dịch và khóa hàng',
      'Phân tích blocking và deadlock',
      'PostgreSQL sử dụng MVCC và các loại khóa để điều phối giao dịch đồng thời.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-03 09:00:00+07'
    ),
    (
      10, 'gin-fts',
      'GIN index cho tìm kiếm toàn văn',
      'Sử dụng tsvector, tsquery và toán tử đối sánh',
      'Tìm kiếm toàn văn dùng text search configuration và chỉ mục GIN trên tsvector.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-04 09:00:00+07'
    ),
    (
      10, 'english-search',
      'PostgreSQL full text search',
      'Ranking and phrase search',
      'English searching uses lexemes, stemming, dictionaries and ranking.',
      'en', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-05 09:00:00+07'
    ),
    (
      10, 'vietnamese-search',
      'Tìm kiếm toàn văn tiếng Việt',
      'Tách từ và cấu hình từ điển tiếng Việt',
      'Tìm kiếm tiếng Việt cần quan tâm đến dấu, từ ghép và cấu hình phân tích văn bản.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-06 09:00:00+07'
    ),
    (
      20, 'postgres-index',
      'PostgreSQL index của tenant 20',
      'Một tài liệu thuộc tổ chức khác',
      'Bài này có cùng từ khóa nhưng không thuộc tenant 10.',
      'vi', 'PUBLISHED',
      TIMESTAMPTZ '2026-10-07 09:00:00+07'
    ),
    (
      10, 'draft-fts',
      'Tối ưu chỉ mục chưa xuất bản',
      'Bản nháp dành cho biên tập viên',
      'Bản nháp nói về PostgreSQL và tối ưu truy vấn.',
      'vi', 'DRAFT',
      TIMESTAMPTZ '2026-10-08 09:00:00+07'
    );
```

Hai tenant có thể dùng cùng slug vì `UNIQUE(tenant_id,slug)` chỉ bảo vệ tổ hợp. Phải áp dụng filter đúng tenant khi tìm kiếm.

## 17. GIN index và B-tree index

```sql
CREATE INDEX ix_articles_fts_gin
ON lesson_fts.articles
USING GIN (search_vector);

CREATE INDEX ix_articles_tenant_status_time
ON lesson_fts.articles (
    tenant_id,
    status,
    published_at DESC,
    article_id DESC
);

ANALYZE lesson_fts.articles;
```

**GIN(search_vector)** giúp tra tài liệu theo lexemes. **B-tree** giúp lọc tenant/status và có thể hỗ trợ thứ tự thời gian. Planner có thể chọn index, bitmap combination hoặc Seq Scan tùy thống kê và chi phí.

Với bảng chỉ có tám hàng, thấy Seq Scan là bình thường; đừng ép index vì muốn output EXPLAIN có một node tên Index Scan.

## 18. Truy vấn cơ bản với @@

```sql
SELECT
    article_id, slug, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.simple',
      'postgresql'
  )
ORDER BY article_id;
```

`@@` là phép đối sánh FTS. Nó không tự thực thi quy tắc tenant hoặc publish status; các điều kiện quan hệ đó phải được giữ rõ ràng.

### Kết hợp nhiều từ

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.simple',
      'postgresql index'
  );
```

Với `plainto_tsquery`, các lexemes thường được kết hợp theo AND: phải có cả hai trong vector, không nhất thiết sát nhau.

## 19. Query constructor dùng lại bằng CTE

```sql
WITH input_query AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS q
)
SELECT
    a.article_id,
    a.title
FROM lesson_fts.articles AS a
CROSS JOIN input_query AS i
WHERE a.tenant_id = 10
  AND a.status = 'PUBLISHED'
  AND a.search_vector @@ i.q
ORDER BY a.article_id;
```

CTE làm rõ một query được sử dụng cho lọc, ranking và snippets. Nó không nhất thiết bắt buộc phải materialize; planner có thể inline theo điều kiện/phiên bản.

## 20. Ranking với ts_rank

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.search) AS rank_score
FROM lesson_fts.articles AS a
CROSS JOIN q
WHERE a.tenant_id = 10
  AND a.status = 'PUBLISHED'
  AND a.search_vector @@ q.search
ORDER BY
    rank_score DESC,
    a.published_at DESC,
    a.article_id DESC;
```

Điểm rank là **điểm phù hợp theo công thức**, không phải xác suất tài liệu đúng 90%. Kết quả còn chịu ảnh hưởng title/summary/body weights, số lần và vị trí xuất hiện từ khóa, normalization.

### Tại sao vẫn phải SORT?

GIN giúp tìm ứng viên chứ không tự trả theo `ts_rank(search_vector,q)` của mọi truy vấn động. Bởi vậy `ORDER BY rank_score DESC` có thể yêu cầu xử lý/sắp xếp các ứng viên.

## 21. ts_rank_cd và cover density

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    title,
    ts_rank(search_vector, q.search) AS score_basic,
    ts_rank_cd(search_vector, q.search) AS score_cover_density
FROM lesson_fts.articles
CROSS JOIN q
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ q.search
ORDER BY score_cover_density DESC, title;
```

`ts_rank_cd` chú ý tới các vùng/vị trí match theo cách khác `ts_rank`. Nếu vector không còn positions hữu ích, kết quả có thể không phản ánh proximity như kỳ vọng.

Không có một hàm rank mặc định tốt nhất cho mọi lĩnh vực. Đo bằng một tập truy vấn và relevance labels của sản phẩm.

## 22. Normalization và thứ tự trọng số

`ts_rank`/`ts_rank_cd` có các overload nhận trọng số và normalization flags. Một ví dụ:

```sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple',
        'postgresql'
    ) AS search
)
SELECT
    title,
    ts_rank(search_vector, q.search, 32) AS normalized_score
FROM lesson_fts.articles
CROSS JOIN q
WHERE search_vector @@ q.search
  AND tenant_id = 10
  AND status = 'PUBLISHED'
ORDER BY normalized_score DESC, article_id;
```

Normalization `32` là một cờ được PostgreSQL định nghĩa, không biến rank thành xác suất “chất lượng” đã được hiệu chuẩn.

Khi truyền mảng weights trong các hàm rank, thứ tự là **`{D,C,B,A}`**, không phải A,B,C,D. Điều này dễ bị đảo nhầm khi tinh chỉnh độ ưu tiên title/body.

## 23. Trích đoạn bằng ts_headline

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    a.title,
    ts_headline(
        'pg_catalog.simple',
        a.body,
        q.search,
        'StartSel=**, StopSel=**, MaxWords=20, MinWords=5'
    ) AS snippet
FROM lesson_fts.articles AS a
CROSS JOIN q
WHERE a.tenant_id = 10
  AND a.status = 'PUBLISHED'
  AND a.search_vector @@ q.search;
```

`ts_headline` giúp lựa chọn/đánh dấu đoạn có từ khớp. Để tránh tốn CPU, thường chỉ cần gọi nó cho **những kết quả cuối cùng được hiển thị**.

### Cảnh báo HTML/XSS

`ts_headline` **không phải công cụ HTML sanitizer**. Nếu body do người dùng cung cấp, phải escape nội dung và chỉ tạo markup highlight từ UI an toàn; không lấy output có `StartSel=<b>` làm bằng chứng HTML đã sạch.

## 24. Một pipeline lọc, rank, giới hạn rồi tạo snippet

```sql
WITH input_query AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS q
),
ranked AS (
    SELECT
        a.article_id,
        a.slug,
        a.title,
        a.body,
        a.published_at,
        ts_rank(a.search_vector, i.q) AS score
    FROM lesson_fts.articles AS a
    CROSS JOIN input_query AS i
    WHERE a.tenant_id = 10
      AND a.status = 'PUBLISHED'
      AND a.search_vector @@ i.q
    ORDER BY
        score DESC,
        a.published_at DESC,
        a.article_id DESC
    LIMIT 10
)
SELECT
    r.article_id,
    r.slug,
    r.title,
    r.score,
    ts_headline(
        'pg_catalog.simple',
        r.body,
        (SELECT q FROM input_query),
        'StartSel=**, StopSel=**, MaxWords=18'
    ) AS snippet
FROM ranked AS r
ORDER BY r.score DESC, r.published_at DESC, r.article_id DESC;
```

### Chú ý

- Không bỏ điều kiện tenant/visibility khi xây query.
- Có tie-breaker để thứ tự nhất quán nếu rank bằng nhau.
- `LIMIT` áp vào tập đã match/rank, không ngầm giới hạn số tài liệu GIN phải xét.
- Trong hệ thống thật, cần kết hợp authorization theo người dùng/ACL, không chỉ tenant và status.

## 25. Khi cập nhật văn bản, vector được đồng bộ ra sao?

```sql
INSERT INTO lesson_fts.articles (
    tenant_id, slug, title, summary, body, status
)
VALUES (
    10,
    'window-functions',
    'Window functions trong PostgreSQL',
    'ROW_NUMBER và PARTITION BY',
    'Hướng dẫn sử dụng hàm cửa sổ khi truy vấn dữ liệu.',
    'PUBLISHED'
);

UPDATE lesson_fts.articles
SET title = 'Window functions và tối ưu truy vấn'
WHERE tenant_id = 10
  AND slug = 'window-functions';
```

Vì `search_vector` là stored generated column, PostgreSQL tính lại từ title/summary/body theo expression khi hàng thay đổi phù hợp và cập nhật index liên quan.

### Chi phí

Sinh vector và cập nhật GIN index tiêu thụ CPU/WAL/storage. Với tài liệu được biên tập thỉnh thoảng, sự nhất quán này đáng giá. Với nội dung thay đổi liên tục, cần đánh giá write amplification.

## 26. Một cách khác: expression GIN index

Không phải mọi trường hợp đều cần lưu cột `tsvector`:

```sql
CREATE INDEX ix_articles_title_fts_expr
ON lesson_fts.articles
USING GIN (
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        title
    )
);
```

Query phù hợp:

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE to_tsvector(
          'pg_catalog.simple'::regconfig,
          title
      ) @@ plainto_tsquery(
          'pg_catalog.simple',
          'postgresql'
      );
```

### So sánh

| Thiết kế | Lợi ích | Đổi lại |
|---|---|---|
| Stored generated `search_vector` + GIN | Có vector dùng cho ranking và query nhiều trường | Lưu vector, tính lại khi ghi |
| Expression GIN trên `to_tsvector(...)` | Không cần cột vector riêng | Query phải tương ứng expression, tính vector khi rank nếu cần |
| Cột `tsvector` cập nhật bằng trigger | Tùy biến cơ chế cập nhật | Dễ phát sinh nghĩa vụ backfill/đồng bộ |
| Search projection riêng | Có thể tổng hợp nhiều bảng/loại tài liệu | Cần quản lý lag, delete, auth và rebuild |

Trong lab đã có GIN trên full vector; index title-only có mục tiêu khác. Không tạo nhiều indexes trùng lặp chỉ vì ví dụ có nhiều phương án.

## 27. Vì sao phải chỉ định config ở index expression?

`to_tsvector(text)` dùng default text search config của session; đây không phải biểu thức bất biến theo dữ liệu đầu vào trong mọi môi trường.

Với index:

```sql
CREATE INDEX ix_articles_body_fts_expr
ON lesson_fts.articles
USING GIN (
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        body
    )
);
```

thì cấu hình cố định trong định nghĩa index. Nếu query dùng một config khác, planner không thể giả định vector mang cùng lexemes hoặc biểu thức tương đương.

**Không đổi default config trong connection pool rồi mong indexed document tự được phân tích lại.**

## 28. GIN và GiST

Hai index methods thường được đề cập cho PostgreSQL FTS:

- **GIN**: inverted index cho lexemes, thường là lựa chọn phổ biến với FTS.
- **GiST**: trade-off khác về cấu trúc/signature/recheck, có thể hữu ích trong một số workload.

Ví dụ GiST thay thế:

```sql
CREATE INDEX ix_articles_fts_gist
ON lesson_fts.articles
USING GiST (search_vector);
```

Trong lab đã có GIN; không cần giữ cả hai nếu không có benchmark/nhu cầu cụ thể.

### GIN không tự làm các việc khác

GIN không xếp theo rank, không tạo snippet, không tự sửa typo hoặc hiểu từ đồng nghĩa, không thực thi chính sách tenant/ACL và không khiến mọi query bắt buộc dùng index.

## 29. Partial GIN index

Nếu phần lớn truy vấn chỉ tìm bài published:

```sql
CREATE INDEX ix_articles_published_fts
ON lesson_fts.articles
USING GIN (search_vector)
WHERE status = 'PUBLISHED';
```

Predicate giới hạn tập tài liệu trong index. Nhưng planner cần chứng minh điều kiện query hàm ý predicate; prepared statement `status = $1` với generic plan không luôn dùng được partial index.

Không dùng predicate dựa trên thời gian hiện tại như `published_at < now()` để xây index “tự thay đổi theo thời gian”; index predicates chịu giới hạn về tính bất biến và không tự cập nhật khi đồng hồ trôi.

## 30. Full-text search kết hợp structured filters

Một API tìm bài học có thể cần:

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND published_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.simple',
      'postgresql index'
  );
```

FTS xử lý lexemes. B-tree/typed columns xử lý tenant, trạng thái, timestamp, giá, mã hoặc khóa ngoại. Không nên chuyển những điều kiện chính xác thành một chuỗi text rồi tìm bằng FTS.

### Ranh giới bảo mật

Tenant_id nhận từ request **không tự chứng minh người dùng được phép xem tenant ấy**. Backend phải áp dụng authorization/RLS theo nguồn quyền đáng tin, ngay cả khi query FTS đã match đúng.

## 31. Đọc kế hoạch thực thi FTS

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    article_id,
    title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.simple',
      'postgresql index'
  );
```

Trên corpus lớn và query đủ chọn lọc, bạn có thể thấy cấu trúc như:

```text
Bitmap Heap Scan on articles
  Recheck Cond: (search_vector @@ ...)
  Filter: (...)
  Buffers: shared hit=... read=...
  -> Bitmap Index Scan on ix_articles_fts_gin
       Index Cond: (search_vector @@ ...)
```

Đây là output minh họa, không phải kết quả đo của bảng tám hàng.

### Các trường cần phân tích

- **Index Cond**: Có đang tra cứu FTS bằng index không?
- **Recheck Cond**: Những hàng ứng viên có được kiểm tra lại điều kiện không?
- **Actual Rows / Plan Rows**: Planner ước lượng khớp bao nhiêu, thực tế bao nhiêu?
- **Rows Removed by Filter**: Bao nhiêu hàng bị loại bởi điều kiện không được push xuống index?
- **Buffers**: Có quét nhiều trang dữ liệu/index không?
- **Execution Time**: Thời gian thực thi trong lần đo.
- **Sort**: Có cần sort theo rank không, có spill temporary files không?

Không kết luận “index không hiệu quả” chỉ vì Seq Scan xuất hiện ở tập dữ liệu quá nhỏ hoặc từ khóa quá phổ biến.

## 32. Đánh giá độ chọn lọc và từ khóa phổ biến

Từ `postgresql` có thể xuất hiện ở gần như mọi bài trong một kho tài liệu chuyên về PostgreSQL. Ngược lại `deadlock` có thể chỉ xuất hiện ở vài bài.

Một truy vấn:

```sql
search_vector @@ plainto_tsquery('simple', 'postgresql')
```

có khả năng tạo nhiều ứng viên hơn:

```sql
search_vector @@ plainto_tsquery('simple', 'deadlock')
```

Do đó hiệu năng không chỉ phụ thuộc số lexemes của query, mà còn phụ thuộc **document frequency** và bộ lọc quan hệ.

### Chọn benchmark inputs

Hãy có ít nhất các nhóm:

1. Một từ rất phổ biến.
2. Một từ hiếm.
3. Hai từ AND.
4. Một phrase hiếm.
5. OR nhiều terms.
6. Prefix dài và prefix ngắn.
7. Stopword-only query.
8. Input tiếng Việt có dấu/không dấu.
9. Query ở tenant có rất nhiều tài liệu và tenant có ít tài liệu.

Không benchmark một từ khóa duy nhất rồi áp kết luận cho toàn hệ thống.

## 33. Không dùng FTS để thay bộ lọc dữ liệu cấu trúc

Ví dụ một trang thương mại muốn tìm “laptop workstation” nhưng chỉ:

- Giá dưới 40 triệu.
- Còn tồn kho.
- Thuộc tenant đang đăng nhập.
- Trạng thái ACTIVE.

Phần search có thể là:

```sql
search_vector @@ websearch_to_tsquery(
    'simple',
    'laptop workstation'
)
```

Nhưng **giá** phải dùng `NUMERIC` với phép so sánh range, **tồn kho** dùng quantity/warehouse constraints, **trạng thái** dùng cột typed và **tenant** dùng authorization. Không nhét mọi điều kiện vào một chuỗi text rồi coi việc match lexemes là chứng minh dữ liệu hợp lệ.

FTS giải quyết **textual relevance**; quan hệ và ràng buộc giải quyết **integrity + filtering chính xác**.

## 34. Search index khi tài liệu có nhiều bảng liên quan

Một bài viết có tác giả, category, tags:

```text
articles(article_id, title, body, author_id)
authors(author_id, author_name)
article_tags(article_id, tag_id)
tags(tag_id, tag_name)
```

Một stored generated column trên `articles` không thể trực tiếp chứa subquery join tùy ý tới các bảng khác để lấy tên tác giả/tags. Nếu muốn search toàn bộ các trường đó, cần quyết định:

- **Cách A:** Vector chỉ chứa title/body; tag/category lọc bằng SQL JOIN.
- **Cách B:** Duy trì cột denormalized keywords, cập nhật đúng khi tags đổi.
- **Cách C:** Bảng search projection tổng hợp dữ liệu từ nhiều bảng.
- **Cách D:** Một search service riêng được đồng bộ từ PostgreSQL.

### Vì sao phải tính tới thay đổi ở bảng liên quan?

Nếu tác giả đổi tên, vector của bài có thể vẫn chứa tên cũ. Nếu tag bị gỡ, search kết quả có thể sai. Một thiết kế search nhiều bảng phải định nghĩa **dependency graph và cơ chế invalidation/re-index**, không chỉ logic khi INSERT article.

## 35. Tạo bảng search projection riêng

```sql
CREATE TABLE lesson_fts.search_documents (
    document_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    document_type TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL CHECK (source_version >= 0),
    title TEXT NOT NULL,
    search_vector TSVECTOR NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, document_type, source_id)
);

CREATE INDEX ix_search_documents_vector
ON lesson_fts.search_documents
USING GIN (search_vector);
```

### Ưu điểm

- Có thể tìm nhiều loại đối tượng trên cùng một giao diện.
- Tách phần search-focused khỏi schema OLTP nhiều quan hệ.
- Có thể gộp title/body/tags/author theo trọng số.
- Dễ tái xây projection khi đổi analyzer.

### Trách nhiệm đi kèm

- Đảm bảo UPSERT idempotent theo source key.
- Tránh event cũ ghi đè source_version mới.
- Đồng bộ khi xóa/đổi trạng thái/ACL.
- Theo dõi thời gian chậm giữa nguồn và index.
- Không lấy projection bất đồng bộ làm nguồn quyền duy nhất.

Nếu projection là **eventually consistent**, người dùng có thể tìm chưa thấy bài vừa xuất bản. Đây là trade-off cần chấp nhận theo yêu cầu sản phẩm, không phải lỗi ngẫu nhiên.

## 36. Dùng trigger để duy trì cột tsvector

Khi không dùng generated column, PostgreSQL có cơ chế trigger hỗ trợ cập nhật vector:

```sql
CREATE TABLE lesson_fts.legacy_articles (
    article_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    search_vector TSVECTOR
);

CREATE TRIGGER legacy_articles_tsvector_update
BEFORE INSERT OR UPDATE OF title, body
ON lesson_fts.legacy_articles
FOR EACH ROW
EXECUTE FUNCTION tsvector_update_trigger(
    search_vector,
    'pg_catalog.simple',
    title,
    body
);
```

### So với generated column

Stored generated column rất phù hợp khi vector được xác định **từ các cột cùng hàng** bằng expression hợp lệ. Trigger có thể phù hợp với thiết kế cũ hoặc logic tùy biến, nhưng thêm nghĩa vụ:

- Xử lý những hàng đã có trước khi tạo trigger.
- Bảo đảm mọi đường ghi làm vector đúng.
- Tái tạo khi đổi config/dictionary.
- Tính đến write path, trigger costs và migration.

Không cố gán giá trị trực tiếp vào một generated column bằng trigger như cột thường; các cơ chế có quy tắc khác nhau.

## 37. Backfill và migration cho bảng hiện có

Khi thêm FTS vào bảng có hàng triệu bài:

1. Chốt lựa chọn config và từ điển theo ngôn ngữ.
2. Chốt những trường tham gia vector và weights.
3. Chọn **stored generated column**, **expression index** hoặc **projection table**.
4. Đo chi phí sinh vector trên tập dữ liệu staging.
5. Backfill nếu dùng cột thường/trigger hoặc projection.
6. Tạo GIN index theo chiến lược triển khai phù hợp.
7. Đổi API queries và authorization filters.
8. Kiểm tra số bài chưa được index, lỗi config, chất lượng kết quả.
9. Có rollback plan nếu latency/quality giảm mạnh.

### Tạo index concurrently

```sql
CREATE INDEX CONCURRENTLY ix_search_documents_vector_online
ON lesson_fts.search_documents
USING GIN (search_vector);
```

Đây là cú pháp minh họa cho migration online; bảng đã có GIN khác trong lab, nên không cần giữ cả hai indexes nếu trùng mục đích. `CREATE INDEX CONCURRENTLY` **không chạy trong transaction block tường minh**, vẫn tiêu thụ I/O và có thể để lại index invalid khi thất bại.

Thêm stored generated column vào bảng lớn cũng có thể yêu cầu quét/rewrite và locks, tùy phiên bản/cách triển khai. Không giả định mọi ALTER TABLE đều “online” chỉ vì SQL ngắn.

## 38. Khi sửa dictionary/config phải tái lập vector

Giả sử trước đây mọi tài liệu dùng `simple`, nay tiếng Anh chuyển sang `english`.

`simple` có thể giữ các hình thức như `running`/`runs` riêng, trong khi `english` có thể stem về lexeme chung. Vector đã lưu **không tự thay đổi** khi bạn đổi cấu hình session.

Cần:

1. Định nghĩa phiên bản cấu hình/từ điển mới.
2. Tính lại vector của corpus ảnh hưởng.
3. Đảm bảo GIN index phản ánh vector mới.
4. Tạo query với config tương ứng.
5. Kiểm thử recall/ranking trước và sau.
6. Có kế hoạch rollback khi quality giảm.

Ngay cả khi tên config không đổi nhưng dictionaries/extension được cập nhật, những vector/index đã xây có thể cần được tái tạo để bảo đảm tính nhất quán về lexemes.

## 39. Tiếng Việt với simple: lợi ích và giới hạn

```sql
SELECT to_tsvector(
    'pg_catalog.simple',
    'Tối ưu tìm kiếm toàn văn tiếng Việt'
);
```

Cấu hình `simple` là một điểm khởi đầu cho tài liệu có dấu và nhiều mã kỹ thuật, nhưng không tự cung cấp đầy đủ:

- Word segmentation tiếng Việt theo ngữ nghĩa.
- Xử lý đúng mọi từ ghép như “cơ sở dữ liệu”, “tìm kiếm”, “học máy”.
- Đồng nghĩa: “CSDL” và “cơ sở dữ liệu”.
- Gõ không dấu: “tim kiem” với “tìm kiếm”.
- Khắc phục typo.
- Semantic search.

### Vì sao “tìm kiếm” đặc biệt?

Trong tiếng Việt, nhiều đơn vị từ vựng có thể gồm nhiều âm tiết được viết cách nhau. Parser theo whitespace có thể tách thành các lexemes độc lập; phrase search giúp yêu cầu vị trí nhưng không biến nó thành một hệ word segmentation/ngữ nghĩa đầy đủ.

Nếu hệ thống có corpus Việt Nam lớn và quality quan trọng, cần **bộ từ điển/tách từ chuyên biệt hoặc pipeline search riêng** được kiểm chứng.

## 40. Truy vấn không dấu và unaccent

Người dùng nhập:

```text
tim kiem
```

trong khi tài liệu có:

```text
tìm kiếm
```

`simple` không mặc định cam kết hai cách viết này tương đương.

PostgreSQL có extension `unaccent` trong nhiều môi trường, nhưng muốn dùng hiệu quả với FTS cần xây **text search configuration/dictionary chain nhất quán**, không chỉ cài extension rồi tin vector lưu sẵn đã đổi.

### Checklist

- Extension được phép cài trên server không?
- Ingest/query có dùng cùng analyzer không?
- Có cần index cả dạng có dấu và không dấu?
- Bỏ dấu có tạo nhập nhằng, giảm precision không?
- Đã rebuild vector/index sau khi thay dictionary chưa?
- Unicode composed/decomposed forms có được chuẩn hóa nhất quán không?

Không dùng một lời hứa “bỏ dấu luôn tốt” thay việc đánh giá query set.

## 41. Từ đồng nghĩa và tên viết tắt

Người dùng tìm:

```text
CSDL
```

nhưng bài viết chỉ có “cơ sở dữ liệu”. FTS không tự biết hai cách nói là tương đương.

Các hướng:

- Thêm canonical keywords vào search document.
- Mở rộng query theo synonym list có version.
- Dùng thesaurus dictionary nếu phù hợp vận hành.
- Kết hợp lexical với semantic retrieval nếu cần.

### Cẩn thận false positives

Một từ viết tắt có thể có nhiều nghĩa. Mở rộng mọi từ viết tắt thành hàng chục cụm khác nhau có thể làm precision giảm. Cần kiểm tra chất lượng theo miền nghiệp vụ.

## 42. Search đa ngôn ngữ

Một corpus có tiếng Việt và tiếng Anh. Có ba chiến lược:

**A. Dùng simple cho tất cả:** triển khai đơn giản, nhưng bỏ qua stemming đặc thù tiếng Anh.

**B. Một vector/config cho từng ngôn ngữ:** quản lý language_code và index/query tương ứng.

**C. Nhiều vector hoặc projection:** lưu nhiều dạng phân tích để có fallback search, đổi lại chi phí index/ghi.

### Điều cần thiết kế

- Ngôn ngữ được xác định từ đâu (biên tập, detect hay metadata)?
- Vector có được tạo bằng config tương ứng không?
- Query nhập tiếng Việt có cần tìm tài liệu tiếng Anh không?
- Điểm rank giữa hai language configurations có so sánh trực tiếp hợp lý không?
- Có yêu cầu tìm tên riêng/identifier xuyên ngôn ngữ không?
- Có kế hoạch reindex khi cấu hình thay đổi không?

Lab sử dụng `simple` thống nhất để tránh đưa vào quá nhiều biến số; **không có nghĩa hệ thống đa ngôn ngữ production nên làm giống hệt**.

## 43. JSONB và tìm kiếm toàn văn

Một document:

```json
{
  "title": "PostgreSQL",
  "body": "Tìm kiếm toàn văn",
  "keywords": ["GIN", "index"],
  "price": 120
}
```

PostgreSQL có những overload của `to_tsvector` với dữ liệu JSON/JSONB tùy phiên bản:

```sql
SELECT to_tsvector(
    'pg_catalog.simple'::regconfig,
    '{"title":"PostgreSQL","body":"Tìm kiếm toàn văn"}'::jsonb
);
```

### Cần thận trọng

- JSONB không cam kết giữ nguyên thứ tự object keys.
- Positions của lexemes qua những field values có quy tắc riêng.
- Phrase query qua các fields có thể không khớp thứ tự mà ứng dụng nghĩ.
- Các giá trị number/boolean/object khác text, cần biết hàm sẽ trích những gì.

Nếu title phải weight A, body D, thường rõ hơn khi lấy **hai phần cụ thể** rồi dùng `setweight`, thay vì index toàn bộ JSONB không có chính sách trường.

### FTS không thay containment

`attributes @> '{"price":120}'::jsonb` là truy vấn cấu trúc; không dùng lexical FTS để thay kiểm tra số giá chính xác.

## 44. FTS với SQL array hoặc tags

Một article có tags là những thực thể có thể được quản trị, đổi tên hoặc dùng làm facet. Nếu tags có FK/metadata riêng, **bảng nối** thường phù hợp:

```text
articles
article_tags(article_id, tag_id)
tags(tag_id, tag_code, display_name)
```

Khi người dùng lọc đúng tag:

```text
tag_id = 42
```

thì dùng quan hệ và B-tree/equality, không biến tag thành lexeme rồi hy vọng parser giữ đúng mọi ký tự.

Tên hiển thị tag vẫn có thể được thêm vào search vector để hỗ trợ search theo từ khóa, nhưng phải có cơ chế cập nhật khi tag đổi tên.

## 45. Tài liệu dài và chunking

Một tài liệu nhiều MB có thể làm vector lớn, khiến `ts_headline`, ranking và việc duy trì index tốn tài nguyên. Một mô hình khác là chia tài liệu thành các đoạn:

```sql
CREATE TABLE lesson_fts.article_chunks (
    article_id BIGINT NOT NULL
        REFERENCES lesson_fts.articles(article_id)
        ON DELETE CASCADE,
    chunk_no INTEGER NOT NULL CHECK (chunk_no > 0),
    chunk_text TEXT NOT NULL,
    chunk_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector(
            'pg_catalog.simple'::regconfig,
            chunk_text
        )
    ) STORED,
    PRIMARY KEY (article_id, chunk_no)
);

CREATE INDEX ix_article_chunks_fts
ON lesson_fts.article_chunks
USING GIN (chunk_vector);
```

### Trade-offs

- Có thể trả snippet đúng đoạn.
- Hỗ trợ tìm đoạn phù hợp trong tài liệu dài.
- Nhưng tăng số rows/index entries và cần gom kết quả theo article.
- Phrase search **xuyên hai chunks** không tự được xử lý như một vector toàn bài.

Chunking chỉ đáng dùng nếu kích thước tài liệu/UX yêu cầu; đừng chia mọi bài ngắn thành nhiều hàng vô ích.

## 46. Markdown/HTML phải được xử lý trước khi index?

Một bài viết có:

```text
# Hướng dẫn PostgreSQL

Sử dụng **EXPLAIN ANALYZE** để xem kế hoạch.

Một code block chứa SELECT * FROM products.
```

Nếu cho nguyên markup vào `to_tsvector`, một số ký hiệu, code identifiers hoặc thẻ HTML có thể tạo các tokens không mong muốn.

Một pipeline phù hợp:

1. Lưu source Markdown/HTML cho việc biên tập/hiển thị.
2. Dùng parser thích hợp trích xuất phần **searchable plain text**.
3. Ưu tiên title, headings, summary theo weights.
4. Cân nhắc index code blocks nếu người dùng thực sự tìm theo code.
5. Lưu phiên bản extraction logic và reindex khi thay đổi.

Không dùng một regex ngắn để tuyên bố đã sanitize HTML an toàn. Extract text và bảo vệ XSS khi render là hai việc riêng.

## 47. Cập nhật vector và concurrency

Với generated column, PostgreSQL tính lại vector trong cùng transaction cập nhật title/body:

```sql
BEGIN;

UPDATE lesson_fts.articles
SET body = body || ' Bổ sung về hiệu năng tìm kiếm.'
WHERE tenant_id = 10
  AND slug = 'query-tuning';

COMMIT;
```

### Điều gì xảy ra?

- UPDATE thay đổi bản ghi theo MVCC.
- Generated search_vector được tính lại phù hợp với cột nguồn.
- GIN index được duy trì như một cấu trúc index.
- Khi transaction commit, trạng thái mới xuất hiện theo visibility rules.

Đây là tính nhất quán mạnh của việc index trực tiếp trên bảng. Với projection cập nhật bất đồng bộ, freshness có thể chậm và cần theo dõi lag.

### Rủi ro khác: sửa cùng bài từ hai ứng dụng

Nếu hai editor dùng read-modify-write trên body, vẫn có nguy cơ **lost update ở tầng application** nếu ghi đè snapshot cũ. Generated vector không tự giải quyết tranh chấp biên tập; cần optimistic locking/versions hoặc quy trình merge hợp lý.

## 48. WAL và write amplification

Để quan sát chi phí ghi trong lab:

```sql
BEGIN;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL
)
UPDATE lesson_fts.articles
SET body = body || ' Thêm hướng dẫn về GIN index.'
WHERE tenant_id = 10
  AND slug = 'gin-fts';

ROLLBACK;
```

**`EXPLAIN ANALYZE` thực thi câu UPDATE thật.** `ROLLBACK` hoàn nguyên dữ liệu transactional, nhưng WAL đã tạo, locks và buffer activity không “biến mất” chỉ vì rollback.

Ghi text lớn có thể tạo:

- Heap tuple version mới.
- Vector mới và công việc GIN index maintenance.
- WAL và áp lực cache.
- Dead tuples cần VACUUM xử lý.

Nếu bài được biên tập thỉnh thoảng, đây có thể là chi phí phù hợp. Nếu có hàng nghìn writes/giây với body dài, phải phân tích throughput và chiến lược indexing.

## 49. Trạng thái publish và an toàn dữ liệu

Document đang PUBLISHED chuyển thành DRAFT/PRIVATE:

```sql
UPDATE lesson_fts.articles
SET status = 'DRAFT'
WHERE tenant_id = 10
  AND slug = 'query-tuning';
```

FTS index vẫn có thể chứa lexemes của bài, nhưng query public **phải lọc status** hoặc áp dụng policy tương ứng. Không xem search index là quyền truy cập.

Nếu dùng projection bất đồng bộ, cập nhật quyền có thể nhanh hơn cập nhật document index; cần kiểm tra permission từ source of truth tại lúc trả kết quả. **Không cho phép indexing lag tạo authorization lag.**

## 50. Pagination khi sắp theo rank

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql'
    ) AS search
)
SELECT
    article_id,
    title,
    ts_rank(search_vector, q.search) AS score
FROM lesson_fts.articles
CROSS JOIN q
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ q.search
ORDER BY score DESC, published_at DESC, article_id DESC
LIMIT 10 OFFSET 0;
```

### Nhược điểm của OFFSET lớn

`OFFSET 10000` có thể buộc PostgreSQL tìm/rank/sort rồi bỏ qua nhiều kết quả. Đối với một corpus lớn, deep pagination cần cân nhắc giới hạn.

### Keyset pagination

Nếu sort theo `score DESC, published_at DESC, article_id DESC`, cursor phải chứa **đủ khóa sắp xếp** tương ứng. Chỉ dùng `article_id > cursor` không tái tạo được thứ tự rank. Ngoài ra, score/document có thể đổi giữa các request, nên cần chiến lược consistency/tie-breaking phù hợp.

Không cố xây một B-tree index cố định trên `ts_rank(vector, query)` khi `query` thay đổi theo từng người dùng rồi kỳ vọng PostgreSQL trả mọi kết quả đã đúng rank.

## 51. Một chiến lược snippet hiệu quả

`ts_headline` phải phân tích text để chọn đoạn có match, nên không nên chạy trên mọi document chỉ vì cần 10 kết quả cuối.

Một quy trình:

1. Lọc FTS+ACL để tìm ứng viên.
2. Tính rank cho tập ứng viên.
3. Chọn trang kết quả bằng LIMIT/OFFSET hoặc cursor hợp lệ.
4. Chỉ tạo `ts_headline` cho những IDs được hiển thị.
5. Escape/sanitize ở UI theo chính sách HTML.

Đừng xem `ts_headline` là công cụ tự động đánh dấu HTML an toàn cho input không tin cậy.

## 52. Input gây truy vấn quá rộng

Người dùng có thể gửi:

```text
a OR b OR c OR d OR e ...
```

hoặc prefix một ký tự, khiến candidate set tăng mạnh.

Các cơ chế bảo vệ:

- Input length limit.
- Giới hạn số lexemes/operators.
- Quy tắc tối thiểu cho prefix/phrase.
- Rate limit theo tenant/user.
- Statement timeout hoặc deadline phù hợp.
- Limit page size.
- Monitoring top heavy queries.

`numnode(tsquery)` chỉ là một tín hiệu, không thể mô tả toàn bộ chi phí; một từ rất phổ biến có thể nặng hơn nhiều từ hiếm.

## 53. SQL injection và cú pháp search query

Phải phân biệt:

**SQL injection:** nối input vào SQL và thay đổi ý nghĩa câu lệnh.

**Search syntax:** `websearch_to_tsquery`/`to_tsquery` diễn giải dấu ngoặc kép, OR, dấu trừ... thành điều kiện tìm kiếm.

Sử dụng **PreparedStatement**:

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = ?
  AND status = 'PUBLISHED'
  AND search_vector @@ websearch_to_tsquery(
      'pg_catalog.simple'::regconfig,
      ?
  );
```

Ở đây `?` là **placeholder JDBC**, không phải cú pháp native SQL được gõ trực tiếp trong psql. Phía server sẽ nhận parameter do driver bind.

Không ghép:

```java
String sql = "SELECT ... to_tsquery('" + userInput + "')";
```

ngoài việc mất an toàn, nó còn dễ lỗi escaping.

## 54. Ví dụ Java/JDBC

Giả định đã có PostgreSQL JDBC driver và `DataSource`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ArticleSearchRepository {
    private final DataSource dataSource;

    public ArticleSearchRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void search(long authorizedTenantId, String input)
            throws SQLException {
        String sql = """
            WITH q AS (
                SELECT websearch_to_tsquery(
                    'pg_catalog.simple'::regconfig, ?
                ) AS search
            )
            SELECT
                a.article_id,
                a.title,
                ts_rank(a.search_vector, q.search) AS score
            FROM lesson_fts.articles AS a
            CROSS JOIN q
            WHERE a.tenant_id = ?
              AND a.status = 'PUBLISHED'
              AND a.search_vector @@ q.search
            ORDER BY score DESC,
                     a.published_at DESC,
                     a.article_id DESC
            LIMIT 20
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, input);
            ps.setLong(2, authorizedTenantId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("article_id");
                    String title = rs.getString("title");
                    float score = rs.getFloat("score");
                    // Map sang DTO theo giao diện của ứng dụng.
                }
            }
        }
    }
}
```

### Điểm cần nhớ

- `authorizedTenantId` phải đến từ ngữ cảnh quyền đáng tin, không tin tùy ý client input.
- Validate độ dài và chính sách query trước khi gửi SQL.
- Có thể dùng timeout/rate limit cho query nặng.
- Không trả raw body/secret fields nếu không cần.
- Rank score không có nghĩa “phần trăm chính xác”.

## 55. Spring/JdbcTemplate

Một ví dụ đơn giản với parameter binding:

```java
String sql = """
    SELECT article_id, title
    FROM lesson_fts.articles
    WHERE tenant_id = ?
      AND status = 'PUBLISHED'
      AND search_vector @@ websearch_to_tsquery(
          'pg_catalog.simple'::regconfig, ?
      )
    ORDER BY published_at DESC, article_id DESC
    LIMIT 20
    """;

var results = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new ArticleResult(
        rs.getLong("article_id"),
        rs.getString("title")
    ),
    authorizedTenantId,
    inputText
);
```

Đoạn trên là skeleton, cần class/record `ArticleResult` và biến `jdbcTemplate`. Trong dự án thật, hãy kiểm tra transaction management, validation và exception mapping.

Annotation ORM không tự tạo text search dictionary, GIN index, ranking hay ACL. Schema migrations và truy vấn thực tế vẫn phải được quản lý.

## 56. Prepared statements và plan khác nhau

Các từ khóa có độ phổ biến rất khác. Prepared query:

```sql
WHERE tenant_id = $1
  AND search_vector @@ websearch_to_tsquery('simple', $2)
```

có thể được server lập generic/custom plans theo tình huống, cấu hình và cơ chế driver. Một plan tốt cho `deadlock` có thể không tốt cho `postgresql` nếu từ sau xuất hiện khắp corpus.

Khi benchmark:

- Thử input phổ biến và hiếm.
- So sánh corpus/tenant sizes.
- Quan sát `EXPLAIN` theo cách application dùng prepared statements.
- Kiểm tra statistics, config và parameter selectivity.

Không suy luận mọi sai khác hiệu năng từ `work_mem` hoặc driver chỉ vì hai request có cùng SQL template.

## 57. Metrics nên thu thập

| Metric | Mục đích |
|---|---|
| p50/p95/p99 search latency | Theo dõi độ nhanh và tail latency |
| Query count và timeout/error rate | Tải và độ ổn định |
| Zero-result rate | Phát hiện quality/lexeme/config issues |
| Candidate/result count | Đánh giá độ rộng của query |
| CTR hoặc search success (khi có cơ sở hợp lệ) | Chất lượng xếp hạng |
| GIN index size và write cost | Chi phí lưu trữ/cập nhật |
| Indexing lag | Freshness của search projection |
| Buffer reads/temp writes | Bottlenecks executor |
| Split theo tenant/language/query type | Tìm nhóm dữ liệu có vấn đề |

### Quyền riêng tư

Search input có thể chứa PII/secrets. Không log nguyên văn mọi query mặc định; dùng fingerprint/metadata/redaction theo chính sách, giới hạn người được xem logs và thời gian lưu.

## 58. pg_stat_statements trong điều tra FTS

Nếu extension đã được cài/cấu hình:

```sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    LEFT(query, 180) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Nó cho thống kê **tích lũy theo query fingerprint**, không phải toàn bộ cây plan của từng input. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trên các trường hợp có thể tái hiện an toàn để tìm operator/chỉ mục gây bottleneck.

Không chạy lệnh truy vấn view này rồi kết luận “FTS hỏng” nếu extension chưa được cài.

## 59. Runbook khi tìm không thấy tài liệu

1. Kiểm tra document còn tồn tại, đúng tenant và được phép trả không.
2. Kiểm tra status PUBLISHED/DRAFT.
3. Đọc title, summary và body gốc.
4. Đọc `search_vector` thực tế.
5. In `tsquery` do constructor tạo.
6. So config của document và query.
7. Dùng `ts_debug` để xem token, dictionary, stemming/stop words.
8. Dùng `numnode` để loại trường hợp query rỗng.
9. Phân biệt AND, phrase, prefix và substring kỳ vọng.
10. Kiểm tra vector/index có được cập nhật sau lần sửa nội dung gần nhất không.

### Tránh sửa sai vấn đề

Nếu tài liệu không xuất hiện vì bị lọc tenant đúng chính sách, **không bỏ điều kiện tenant** để “sửa search”. Nếu người dùng cần truy cập, đó là vấn đề authorization khác.

## 60. Runbook khi FTS chậm

1. Lấy query shape, language/config, tenant scope và input thật đã được redact.
2. Lấy `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` trên môi trường phù hợp.
3. Xem có GIN index scan/bitmap recheck hay Seq Scan.
4. So estimated vs actual rows, candidate counts.
5. Xem query có quá phổ biến, OR dài, prefix ngắn hoặc NOT-only không.
6. Tìm Sort theo rank và `temp read/written`.
7. Kiểm tra `ts_headline` có chạy trước LIMIT cho quá nhiều hàng không.
8. Kiểm tra B-tree filters, status/tenant/ACL.
9. Kiểm tra GIN index size, write patterns, stats và VACUUM.
10. Đo nhiều lần với cache/concurrency đại diện.

Không chỉ tăng `work_mem` nếu gốc vấn đề là một query quá rộng hoặc chạy headline trên hàng triệu documents.

## 61. Khi nào PostgreSQL FTS đủ dùng?

Thường phù hợp nếu:

- Dữ liệu đã nằm trong PostgreSQL.
- Cần lexical search, phrase và ranking cơ bản.
- Các bộ lọc quan hệ/phân quyền gắn chặt với dữ liệu.
- Không muốn vận hành một search cluster riêng.
- Corpus/workload có thể đáp ứng SLA sau benchmark.

Có thể cần mở rộng hoặc thay giải pháp khi:

- Cần typo tolerance/semantic retrieval rất cao.
- Cần word segmentation nâng cao cho nhiều ngôn ngữ.
- Có faceting/autocomplete/personalized ranking phức tạp.
- Workload search quá lớn gây cạnh tranh nghiêm trọng với OLTP.
- Có yêu cầu độc lập scale/availability giữa search và dữ liệu giao dịch.

Không chọn search engine bên ngoài chỉ dựa vào số hàng; hãy dựa vào **SLA, quality và tổng chi phí vận hành**.

## 62. Những hiểu nhầm thường gặp

**“tsvector là bản sao nguyên văn của text.”** Không. Nó chứa lexemes/positions/weights và không giữ đủ văn bản gốc.

**“tsquery là một chuỗi tìm kiếm tùy ý.”** Không. Nó có cú pháp/đơn vị lexeme cụ thể.

**“LIKE '%term%' tương đương FTS.”** Không. Một bên là substring, bên kia là lexical retrieval.

**“plainto_tsquery dùng OR mặc định.”** Không; lexemes thường được nối AND.

**“to_tsquery nhận mọi input của người dùng mà không có lỗi.”** Không. Dùng constructor phù hợp và bind parameters.

**“Prefix sẽ tìm mọi lỗi gõ.”** Không; `:*` là tiền tố lexeme.

**“Phrase query là so sánh nguyên byte trong body.”** Không; phrase dựa vào lexeme positions sau parsing.

**“Gin index tự xếp kết quả theo ts_rank.”** Không. Rank/sort là bước riêng.

**“Cứ có GIN thì planner luôn dùng GIN.”** Không. Bảng nhỏ hoặc truy vấn rộng có thể chọn Seq Scan.

**“Weight A đảm bảo tiêu đề luôn đứng đầu.”** Không, còn phụ thuộc ranking và matching.

**“ts_rank là xác suất tài liệu đúng.”** Không; đó là relevance score theo công thức.

**“ts_headline escape HTML an toàn.”** Không; cần bảo vệ XSS khi hiển thị.

**“Đổi config thì vector lưu sẵn tự đổi.”** Không; cần tái tạo dữ liệu/index theo ngữ nghĩa mới.

**“simple đã hiểu đầy đủ từ ghép tiếng Việt.”** Không; chất lượng cần đánh giá theo ngôn ngữ/corpus.

**“unaccent tự kích hoạt khi cài extension.”** Không; cần pipeline phân tích nhất quán.

**“FTS tự nhận biết CSDL và cơ sở dữ liệu là đồng nghĩa.”** Không mặc định.

**“JSONB chứa title/body thì khỏi cần cân nhắc phrase positions.”** Không; thứ tự keys và cách trích lexemes có thể ảnh hưởng.

**“Search vector không có chi phí ghi.”** Không; INSERT/UPDATE tạo vector và bảo trì GIN.

**“Generated column có thể join bảng authors/tags trong expression.”** Không được giả định; cần projection/trigger/job.

**“Search projection eventual consistency vẫn an toàn nếu quyền tài liệu đổi.”** Không; phải kiểm quyền ở nguồn đáng tin tại lúc trả kết quả.

**“tenant_id do client gửi chứng minh quyền truy cập.”** Không.

**“Với numnode nhỏ, query chắc chắn nhẹ.”** Không; từ rất phổ biến vẫn có thể match nhiều hàng.

**“Search không cần rate limiting.”** Không; OR/prefix/NOT-only có thể tốn tài nguyên.

**“Chỉ cần một lần EXPLAIN trên dữ liệu tám hàng là đủ.”** Không; benchmark phải dùng corpus/queries đại diện.

## 63. Bộ câu lệnh thực hành nhanh

**A — Vector và positions:**

```sql
SELECT
    article_id, title, search_vector
FROM lesson_fts.articles
WHERE tenant_id = 10
ORDER BY article_id;
```

**B — So sánh analyzer:**

```sql
SELECT
    to_tsvector('simple', 'running runs') AS simple_v,
    to_tsvector('english', 'running runs') AS english_v;
```

**C — Truy vấn tenant-safe:**

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.simple',
      'postgresql'
  );
```

**D — Phrase:**

```sql
SELECT article_id, title
FROM lesson_fts.articles
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ phraseto_tsquery(
      'pg_catalog.simple',
      'tối ưu truy vấn'
  );
```

**E — Xếp hạng:**

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple',
        'postgresql index'
    ) AS search
)
SELECT
    title,
    ts_rank(search_vector, q.search) AS score
FROM lesson_fts.articles
CROSS JOIN q
WHERE tenant_id = 10
  AND status = 'PUBLISHED'
  AND search_vector @@ q.search
ORDER BY score DESC, title;
```

**F — Dò parser:**

```sql
SELECT *
FROM ts_debug(
    'pg_catalog.simple',
    'Tối ưu truy vấn PostgreSQL'
);
```

**G — Execution plan:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id
FROM lesson_fts.articles
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.simple',
    'postgresql index'
);
```

## 64. Bài tập thực hành

### Bài 1 — Token và lexeme

Chạy `to_tsvector('simple','PostgreSQL database PostgreSQL indexing')`. Xác định lexemes/vị trí; vì sao không thể tái dựng văn bản gốc từ vector?

### Bài 2 — Simple và English

Thử `running runs runner` với simple/english, dùng `ts_debug` để xác định stemming.

### Bài 3 — Stop words

Chạy `ts_debug('english','The runners are running')`. Token nào bị loại theo dictionary và tại sao?

### Bài 4 — Tường minh config

Vì sao nên dùng `to_tsvector('pg_catalog.simple'::regconfig,title)` trong expression index/generated column?

### Bài 5 — Trọng số

Tạo vector title weight A và body weight D rồi nối bằng `||`. Giải thích positions và weights.

### Bài 6 — Ba constructors

Với `postgresql index`, so `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`. Mỗi hàm phục vụ UX nào?

### Bài 7 — AND và OR

Viết `to_tsquery` với AND/OR cho PostgreSQL và index. Dự đoán query nào có thể trả nhiều hàng hơn.

### Bài 8 — NOT

Viết query tìm PostgreSQL nhưng không có MySQL. Vì sao `!mysql` đơn độc có thể khó tối ưu bằng index?

### Bài 9 — Phrase search

Tìm cụm “tối ưu truy vấn”, so với plain AND query cùng các từ. Giải thích khác biệt.

### Bài 10 — Prefix search

Thử `postgres:*`. Vì sao query này không tương đương `ILIKE '%postgres%'` hoặc sửa typo?

### Bài 11 — Empty tsquery

Thử input `the and of` với config english và `numnode`. Đề xuất hành vi API khi query không còn lexemes.

### Bài 12 — Generated vector

Chèn một bài mới, đọc search_vector; cập nhật title/body rồi đọc lại. Vì sao nó tự đồng bộ?

### Bài 13 — GIN index

Tạo GIN trên search_vector; chạy `EXPLAIN`. Tại sao với tám bài PostgreSQL có thể chọn Seq Scan?

### Bài 14 — Ranking

Tính `ts_rank` cho query PostgreSQL index và sắp theo rank, published_at, article_id. Vì sao cần tie-breaker?

### Bài 15 — Cover density

So sánh `ts_rank` và `ts_rank_cd` khi hai lexemes sát nhau so với nằm xa nhau.

### Bài 16 — Normalization

Thử một normalization flag; giải thích vì sao score không phải xác suất.

### Bài 17 — Headline

Tạo snippet với `ts_headline`. Nếu body chứa HTML không đáng tin, cách bảo vệ XSS là gì?

### Bài 18 — Pipeline hoàn chỉnh

Viết CTE tạo query một lần, lọc tenant/status, rank, LIMIT 10, tạo snippet ở ngoài tập giới hạn.

### Bài 19 — Tenant isolation

Một bài tenant 20 có cùng từ khóa. Viết SQL đảm bảo tài khoản tenant 10 không nhận nó.

### Bài 20 — Draft visibility

Một bản DRAFT có rank rất cao. Tại sao public search không được trả nó? Ở đâu nên áp dụng ACL?

### Bài 21 — Expression index

Tạo expression GIN cho `to_tsvector('simple',title)`, so sánh với stored generated vector.

### Bài 22 — Partial GIN

Tạo GIN chỉ cho PUBLISHED. Vì sao generic prepared plan với `status=$1` có thể không dùng index đó?

### Bài 23 — Trigger

Dùng `tsvector_update_trigger` trong bảng legacy. Thử INSERT/UPDATE và so sánh với generated column.

### Bài 24 — Projection

Thiết kế search_documents gộp title, author name, tags. Khi tác giả đổi tên hoặc tag bị xóa, cơ chế reindex nào cần có?

### Bài 25 — Migration config

Đổi corpus tiếng Anh từ simple sang english stemming. Viết kế hoạch rebuild vectors/indexes và chuyển query config.

### Bài 26 — Tiếng Việt

Lấy “cơ sở dữ liệu”, “tìm kiếm”, “học máy”. Dùng simple, nêu những giới hạn word segmentation và phrase.

### Bài 27 — Không dấu

User nhập `tim kiem`, source có `tìm kiếm`. Đề xuất normalization/dictionary nhất quán và chính sách khi bỏ dấu gây nhập nhằng.

### Bài 28 — Đa ngôn ngữ

Corpus vi/en cần tìm theo language; thiết kế cấu hình/index/query để không dùng english stemming cho mọi tài liệu tiếng Việt.

### Bài 29 — Substring và trigram

Một khách cần tìm chuỗi chính xác `foo.bar`. Khi nào FTS không đủ và nên cân nhắc `LIKE/pg_trgm`?

### Bài 30 — JSONB

Một sản phẩm chứa title/description/keywords trong JSONB. Thiết kế vector có title weight A và mô tả weight D; nêu rủi ro phrase across JSON fields.

### Bài 31 — Chunking

Tài liệu dài 3 MB. Thiết kế article_chunks, GIN và nhóm kết quả theo article_id; xử lý phrase xuyên chunks thế nào?

### Bài 32 — HTML/Markdown

Nêu chiến lược extract plain text từ markup và làm sao loại code blocks khỏi index khi code không liên quan search.

### Bài 33 — Query quá rộng

User nhập prefix một ký tự với OR nhiều vế. Thiết kế input limit, rate limit, statement timeout và monitoring.

### Bài 34 — JDBC

Viết repository dùng `PreparedStatement` bind input và tenant đã xác thực, có LIMIT 20; không ghép SQL.

### Bài 35 — ACL và indexing lag

Một tài liệu bị đổi PRIVATE, projection chưa cập nhật. Làm sao không để public search trả tài liệu ấy?

### Bài 36 — EXPLAIN

Đọc Bitmap Index Scan/Heap Scan nếu có, Recheck Cond, estimated/actual rows, shared reads và execution time.

### Bài 37 — Pagination

Sắp theo score DESC/published_at DESC/article_id DESC. Vì sao cursor chỉ có article_id sẽ gây sai thứ tự?

### Bài 38 — Quality metrics

Lập 20 queries có relevance labels. Chọn metric kiểm thử zero-result, precision/recall, ranking và latency.

### Bài 39 — Write amplification

Trong transaction lab, UPDATE body với `EXPLAIN (ANALYZE, BUFFERS, WAL)` rồi rollback. Vì sao rollback không xóa WAL đã phát sinh?

### Bài 40 — Thiết kế hệ thống tổng hợp

Một nền tảng đa tenant lưu một triệu bài tiếng Việt/Anh, cần title/body/tags search, phrase, ranking, snippets, search suggestions, RLS và khả năng cập nhật nội dung:

1. Thiết kế bảng nguồn, vector, weights, cấu hình ngôn ngữ.
2. Lựa chọn generated column hoặc projection, GIN/B-tree indexes.
3. Định nghĩa query constructors cho input thường, phrase và advanced syntax.
4. Đảm bảo tenant/status/ACL trên mọi đường tìm.
5. Thiết kế ranking, stable pagination và safe highlighting.
6. Đề xuất phương án không dấu, synonym, typo tolerance và semantic fallback khi cần.
7. Mô tả migration/rebuild và theo dõi indexing lag.
8. Đặt metrics performance/relevance để xác nhận hệ thống đáp ứng SLA.

## Kết luận

**`tsvector` biểu diễn tài liệu thành những lexemes có vị trí/trọng số; `tsquery` biểu diễn biểu thức tìm kiếm; `@@` là phép đối sánh cốt lõi của PostgreSQL Full-Text Search.** Dùng `to_tsvector` với cấu hình rõ ràng để phân tích nguồn, `plainto_tsquery`/`phraseto_tsquery`/`websearch_to_tsquery` cho các tình huống input phù hợp, còn `to_tsquery` dành cho biểu thức tìm kiếm có cú pháp được kiểm soát.

**GIN index** thường là lựa chọn chính giúp tìm ứng viên, nhưng không tự xếp theo rank, tạo snippet hay bảo vệ quyền tài liệu. **`setweight`**, **`ts_rank`/`ts_rank_cd`** và **`ts_headline`** đáp ứng các bước ưu tiên và trình bày kết quả; ứng dụng vẫn phải áp dụng tenant/status/ACL và escape nội dung hiển thị.

Với **tiếng Việt**, `simple` là khởi đầu có ích nhưng không giải quyết toàn bộ vấn đề từ ghép, không dấu, synonyms và typo. Với corpus đa ngôn ngữ, hãy giữ **cấu hình phân tích nhất quán giữa document và query**, đồng thời có kế hoạch rebuild khi dictionaries/normalization thay đổi. Stored generated vector phù hợp khi dữ liệu đến từ chính hàng; trigger hoặc search projection phù hợp hơn khi cần tổng hợp nhiều bảng, đổi lại chi phí cập nhật và freshness.

Một hệ thống FTS tốt không chỉ trả về những hàng có từ khóa. Nó cần một **luồng có thể kiểm soát từ ingest đến query**, dữ liệu gốc đáng tin, chỉ mục đúng, truy vấn an toàn, xếp hạng có kiểm chứng, bảo vệ tenant/ACL, pagination hợp lý và đo lường hiệu năng trên workload đại diện. Khi những yếu tố này được thiết kế cùng nhau, PostgreSQL có thể cung cấp tìm kiếm toàn văn mạnh mẽ ngay trong hệ quản trị quan hệ.
