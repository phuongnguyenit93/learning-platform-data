# LIKE, ILIKE, biểu thức chính quy và giới hạn hiệu năng trong PostgreSQL

## 1. Từ tìm kiếm một tiền tố đến truy vấn quét hàng triệu bản ghi

Giả sử ứng dụng có bảng tài liệu gồm tiêu đề, nội dung và đường dẫn:

```sql
SELECT document_id, title
FROM documents
WHERE title LIKE 'PostgreSQL%';
```

Đây là tìm kiếm **tiền tố**: tiêu đề bắt đầu bằng `PostgreSQL`. Với B-tree index thích hợp, PostgreSQL có thể giới hạn phạm vi index phải đọc. Nhưng khi đổi thành:

```sql
SELECT document_id, title
FROM documents
WHERE title ILIKE '%postgresql%';
```

bài toán đã khác:

- `ILIKE` so khớp **không phân biệt hoa/thường** theo quy tắc locale/collation liên quan.
- Dấu `%` đầu mẫu cho phép chữ cần tìm ở **bất kỳ vị trí nào**.
- B-tree thông thường khó dùng để thu hẹp index range cho điều kiện kiểu “chuỗi chứa ở đâu đó”.
- Nếu bảng lớn, một `Seq Scan` có thể phải xem rất nhiều hàng.

Với biểu thức chính quy:

```sql
SELECT document_id, title
FROM documents
WHERE title ~* '^(PostgreSQL|Java).*index';
```

ta còn phải tính đến độ phức tạp pattern, khả năng trích xuất prefix/trigrams, thống kê, CPU và rủi ro cho phép người dùng cung cấp regex tùy ý.

**Bài học này không chỉ dạy cú pháp.** Mục tiêu là chọn phép so khớp đúng, giữ truy vấn an toàn và biết **khi nào, bằng cách nào PostgreSQL có thể dùng index**.

```text
Người dùng nhập truy vấn
         |
         +--> Chỉ biết chuỗi bắt đầu? ------> LIKE 'prefix%'
         |
         +--> Tìm trong bất kỳ vị trí? -----> LIKE '%term%'
         |
         +--> Không phân biệt chữ hoa? -----> ILIKE / lower(...)
         |
         +--> Cần quy luật ký tự? ----------> POSIX regex ~ / ~*
         |
         +--> Cần tìm văn bản lớn? ---------> pg_trgm / Full Text Search
         |
         +--> Đều cần EXPLAIN, dữ liệu thật và giới hạn chi phí
```

> **Nguyên tắc cốt lõi:** độ mạnh của phép so khớp và khả năng dùng index là hai quyết định liên quan nhưng khác nhau. Một truy vấn “đúng kết quả” vẫn có thể không phù hợp để thực thi trên nhiều triệu hàng ở mỗi request.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ký tự đại diện `%` và `_` trong `LIKE` / `ILIKE`.
2. Viết mẫu tiền tố, hậu tố, chứa chuỗi, tìm đúng toàn chuỗi và nhiều đoạn theo thứ tự.
3. Escape ký tự `%`, `_` và ký tự escape khi **người dùng muốn tìm chúng như văn bản**.
4. Phân biệt `LIKE`, `ILIKE`, `SIMILAR TO` và toán tử POSIX regex `~`, `~*`, `!~`, `!~*`.
5. Viết regex với anchor, character class, quantifier, grouping và alternation.
6. Sử dụng `regexp_match`, `regexp_matches`, `regexp_replace` và `regexp_split_to_array` theo đúng semantics.
7. Hiểu NULL, locale/collation, Unicode và khác biệt case-insensitive so với accent-insensitive.
8. Giải thích vì sao B-tree index thường phù hợp hơn với `LIKE 'prefix%'` so với `LIKE '%term%'`.
9. Dùng `text_pattern_ops` và expression index `lower(...)` cho những kiểu prefix search thích hợp.
10. Hiểu extension `pg_trgm` cùng GIN/GiST trigram indexes cho substring, ILIKE và regex.
11. Nhận ra mẫu quá ngắn/không có trigrams trích xuất được và chi phí recheck.
12. Đọc `EXPLAIN (ANALYZE, BUFFERS)` cho `Seq Scan`, `Index Scan` và `Bitmap Heap Scan`.
13. Xây dựng Java/JDBC `PreparedStatement` an toàn, không nhầm **SQL injection** với **pattern injection**.
14. Chọn khi nào nên chuyển sang PostgreSQL Full Text Search.
15. Thiết kế giới hạn truy vấn, phân trang, timeout và benchmark trên dữ liệu đại diện.

## 3. Bảng so sánh nhanh các công cụ tìm mẫu

| Cơ chế | Mục tiêu phổ biến | Phân biệt hoa/thường | Mẫu |
| --- | --- | --- | --- |
| `LIKE` | Wildcard đơn giản | Thường có, theo collation | `title LIKE 'PostgreSQL%'` |
| `ILIKE` | Wildcard đơn giản không phân biệt hoa/thường | Không, theo locale liên quan | `title ILIKE '%postgresql%'` |
| `NOT LIKE` | Phủ định LIKE | Tương tự LIKE | `title NOT LIKE 'tmp%'` |
| `NOT ILIKE` | Phủ định ILIKE | Tương tự ILIKE | `title NOT ILIKE '%draft%'` |
| `SIMILAR TO` | Pattern kiểu SQL kết hợp LIKE và regex | Phụ thuộc semantics/collation | `title SIMILAR TO '(Java|SQL)%'` |
| `~` | POSIX regular expression | Phân biệt hoa/thường | `title ~ '^PostgreSQL'` |
| `~*` | POSIX regex không phân biệt hoa/thường | Không phân biệt hoa/thường | `title ~* 'postgresql'` |
| `!~` | Phủ định case-sensitive regex | Phân biệt hoa/thường | `title !~ '[[:digit:]]'` |
| `!~*` | Phủ định case-insensitive regex | Không phân biệt hoa/thường | `title !~* 'draft'` |
| `pg_trgm` | Chỉ mục và phép đo tương tự dựa trên trigrams | Theo operator | Index GIN/GiST với `gin_trgm_ops` |
| Full Text Search | Tìm theo từ/lexeme và cú pháp tìm kiếm | Theo text-search configuration | `to_tsvector(...) @@ plainto_tsquery(...)` |

Một số cơ chế có giới hạn khi dùng **nondeterministic collations**, và chi tiết hỗ trợ có thể thay đổi theo phiên bản PostgreSQL. Đừng đồng nhất `ILIKE` với collation không phân biệt dấu hoặc với chức năng tìm kiếm ngôn ngữ tự nhiên.

## 4. Tạo schema lab với dữ liệu đủ lớn để đo

Các lệnh trong bài nên chạy trên **database thử nghiệm**. Nạp dữ liệu và tạo GIN index có chi phí đáng kể; không copy trực tiếp lên production.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS text_search_lab;

CREATE TABLE text_search_lab.documents (
    document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    slug text NOT NULL,
    body text NOT NULL,
    category text NOT NULL,
    created_at timestamptz NOT NULL,
    archived boolean NOT NULL DEFAULT false
);
```

`document_id` có B-tree index từ `PRIMARY KEY`, nhưng index này **không tự giúp tìm chuỗi trong title/body**.

### 4.2. Nạp 120.000 tài liệu

```sql
INSERT INTO text_search_lab.documents
    (title, slug, body, category, created_at, archived)
SELECT
    CASE
        WHEN g % 100 = 0
            THEN 'PostgreSQL performance guide ' || g
        WHEN g % 17 = 0
            THEN 'Java indexing patterns ' || g
        WHEN g % 29 = 0
            THEN 'Café and Unicode notes ' || g
        ELSE
            'Database tutorial ' || g
    END AS title,
    'doc_' || lpad(g::text, 6, '0') AS slug,
    repeat('storage and query planning example. ', 3)
        || CASE
             WHEN g % 31 = 0
               THEN 'Search tuning with pg_trgm and index scans. '
             WHEN g % 37 = 0
               THEN 'Regular expression exercises and metadata. '
             ELSE 'General database foundations. '
           END
        || g::text AS body,
    CASE WHEN g % 10 = 0 THEN 'advanced'
         ELSE 'beginner'
    END AS category,
    timestamptz '2025-01-01 00:00:00+00'
       + g * interval '1 minute' AS created_at,
    (g % 19 = 0) AS archived
FROM generate_series(1, 120000) AS s(g);
```

Lưu ý: `CASE` chọn **nhánh phù hợp đầu tiên**; một hàng chia hết cho 100 và 17 sẽ có title PostgreSQL, không phải Java.

### 4.3. Thống kê và kiểm tra dữ liệu

```sql
ANALYZE text_search_lab.documents;

SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (
        WHERE title LIKE 'PostgreSQL%'
    ) AS postgresql_prefix,
    COUNT(*) FILTER (
        WHERE title LIKE 'Java%'
    ) AS java_prefix,
    COUNT(*) FILTER (
        WHERE body LIKE '%pg_trgm%'
    ) AS trigram_mentions,
    COUNT(*) FILTER (
        WHERE archived
    ) AS archived_documents
FROM text_search_lab.documents;
```

Các tỷ lệ trong dataset là tương đối xác định, còn **plan** lựa chọn vẫn phụ thuộc phiên bản, indexes, cache, tham số planner và máy.

### 4.4. Dùng EXPLAIN trước khi tạo index tìm chuỗi

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

Khi chưa có index trên `title`, dễ gặp `Seq Scan`. Nhưng câu lệnh có thể được optimizer thay đổi tùy môi trường. Ghi lại actual rows, buffers và Execution Time để có mốc so sánh.

Không dùng `COUNT(*)` làm benchmark thay thế hoàn toàn một query trả `body` hoặc nhiều cột: projection thay đổi có thể làm access path khác.

## 5. LIKE: cú pháp và nguyên tắc so khớp toàn chuỗi

Cú pháp:

```sql
expression LIKE pattern [ESCAPE escape_character]
```

Hai wildcard quan trọng:

- `%` khớp **không, một hoặc nhiều ký tự**.
- `_` khớp **đúng một ký tự** trong chuỗi theo semantics ký tự của PostgreSQL.

Khác với POSIX regex, `LIKE` so khớp **toàn bộ chuỗi**. Dù pattern có `%` ở đầu/cuối, việc “tìm ở giữa” là do wildcard đó chứ không phải mặc định regex-style substring matching.

### 5.1. Ví dụ ngắn

```sql
SELECT
    'PostgreSQL 18' LIKE 'PostgreSQL%' AS prefix_match,
    'PostgreSQL 18' LIKE '%SQL%' AS contains_sql,
    'AB7' LIKE 'AB_' AS one_character,
    'AB77' LIKE 'AB_' AS too_many_characters,
    'PostgreSQL' LIKE 'SQL' AS not_full_match;
```

Ý nghĩa:

| Mẫu | Kết quả |
| --- | --- |
| `'PostgreSQL 18' LIKE 'PostgreSQL%'` | true |
| `'PostgreSQL 18' LIKE '%SQL%'` | true |
| `'AB7' LIKE 'AB_'` | true |
| `'AB77' LIKE 'AB_'` | false |
| `'PostgreSQL' LIKE 'SQL'` | false |

### 5.2. Prefix search

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

Tìm những tiêu đề **bắt đầu** bằng `PostgreSQL`.

### 5.3. Suffix search

```sql
SELECT document_id, slug
FROM text_search_lab.documents
WHERE slug LIKE '%001';
```

Tìm slug **kết thúc** bằng `001`. B-tree thông thường khó thu hẹp range cho pattern bắt đầu bằng `%`.

### 5.4. Substring search

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

Tìm `indexing` ở bất kỳ vị trí nào trong title.

### 5.5. Các đoạn theo thứ tự

```sql
SELECT
    'PostgreSQL query optimizer' LIKE
    'PostgreSQL%optimizer' AS matched;
```

`%` đại diện phần giữa, nhưng các đoạn văn bản khác vẫn phải xuất hiện đúng thứ tự.

### 5.6. Tìm chính xác toàn chuỗi

```sql
SELECT 'Java' LIKE 'Java' AS exact_text;
```

Nếu không dùng wildcard, `LIKE` có hành vi so khớp mẫu nguyên vẹn. Trong query equality thông thường nên ưu tiên:

```sql
WHERE title = $1
```

khi nghiệp vụ thật sự muốn so khớp bằng, vì đây là semantics rõ ràng hơn và thường dễ tận dụng equality index.

## 6. Dấu gạch dưới trong LIKE có ý nghĩa đặc biệt

Một lỗi rất thường gặp:

```sql
WHERE slug LIKE 'doc_0001%'
```

Ở đây `_` **không phải ký tự underscore literal**; nó khớp một ký tự bất kỳ.

Điều kiện trên có thể match cả `docX0001...` nếu chuỗi khác khớp.

### 6.1. Escape underscore bằng ký tự tùy chọn

```sql
SELECT
    'doc_000123' LIKE 'doc!_000%' ESCAPE '!' AS literal_underscore,
    'docX000123' LIKE 'doc!_000%' ESCAPE '!' AS reject_other_character;
```

Ký tự `!` được chỉ định là **escape character**. Vì vậy:

- `!_` nghĩa là underscore literal.
- `!%` nghĩa là percent literal.
- `!!` nghĩa là dấu `!` literal.

### 6.2. Ví dụ escape phần trăm

```sql
SELECT
    '50% discount' LIKE '50!%%' ESCAPE '!' AS literal_percent,
    '500 discount' LIKE '50!%%' ESCAPE '!' AS not_same;
```

Pattern `50!%%` gồm `50`, percent literal (`!%`), rồi `%` wildcard.

### 6.3. Escape chính ký tự escape

```sql
SELECT
    'hello!world' LIKE 'hello!!world' ESCAPE '!' AS matched;
```

Việc chọn một ký tự escape tường minh giúp tránh nhầm với nhiều lớp backslash escaping của SQL literal, Java string và regex.

### 6.4. Backslash mặc định và standard_conforming_strings

Trong PostgreSQL, dấu `\` thường được dùng làm escape mặc định của LIKE. Đồng thời SQL string literal có quy tắc xử lý backslash chịu ảnh hưởng của `standard_conforming_strings` và cú pháp `E'...'`.

Vì có thể tồn tại **hai lớp escape**, trong bài và trong ứng dụng ta ưu tiên:

```sql
LIKE $1 ESCAPE '!'
```

khi muốn escape wildcard literal. Không ghép thủ công nhiều dấu `\` mà chưa kiểm tra từng lớp SQL/regex/ứng dụng.

## 7. LIKE, NULL và toán tử phủ định

Cũng như các so sánh SQL khác, nếu một toán hạng là `NULL`, kết quả so khớp thông thường là `NULL`, không phải false.

```sql
SELECT
    NULL::text LIKE 'a%' AS null_input,
    'abc' LIKE NULL::text AS null_pattern,
    NOT ('abc' LIKE NULL::text) AS null_negation;
```

Cả ba expression đều cho kết quả NULL.

### 7.1. NOT LIKE không tự giữ rows có NULL

```sql
WHERE title NOT LIKE 'tmp%'
```

không tự bao gồm các rows có `title IS NULL`. Nếu nghiệp vụ muốn bao gồm NULL:

```sql
WHERE title NOT LIKE 'tmp%'
   OR title IS NULL
```

Trong lab `title NOT NULL`, nhưng quy tắc này rất quan trọng với các bảng thực tế.

### 7.2. `LIKE '%'` không match NULL

```sql
SELECT
    'anything' LIKE '%' AS any_nonnull,
    NULL::text LIKE '%' AS null_is_not_true;
```

`LIKE '%'` đúng với mọi chuỗi **không NULL**, kể cả chuỗi rỗng, nhưng kết quả là NULL đối với input NULL.

### 7.3. Chuỗi rỗng khác NULL

```sql
SELECT
    '' LIKE '%' AS empty_matches_percent,
    '' LIKE '_' AS empty_does_not_match_underscore,
    '' LIKE '' AS empty_matches_empty;
```

Đừng dùng một kiểm tra LIKE thay cho quy tắc ứng dụng phân biệt missing, empty string và null.

## 8. ILIKE: không phân biệt hoa/thường nhưng không tự bỏ dấu

PostgreSQL hỗ trợ `ILIKE` để so khớp wildcard kiểu LIKE mà không phân biệt hoa/thường theo quy tắc locale/collation tương ứng.

```sql
SELECT
    'PostgreSQL' ILIKE 'postgresql' AS same_ignoring_case,
    'Java INDEX' ILIKE '%index%' AS contains_ignoring_case,
    'PostgreSQL' LIKE 'postgresql' AS like_can_differ;
```

### 8.1. Trong bảng tài liệu

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%POSTGRESQL%';
```

Điều kiện có thể match cả tiêu đề `PostgreSQL ...` dù pattern viết hoa.

### 8.2. ILIKE không phải tìm kiếm accent-insensitive

`ILIKE '%cafe%'` **không có bảo đảm** match `Café` khi dấu khác nhau. Phân biệt chữ hoa/thường khác với phân biệt dấu, Unicode normalization và các quy tắc so sánh theo ngôn ngữ.

Nếu sản phẩm yêu cầu “cafe” tìm được “Café”, phải thiết kế normalization/collation/search strategy phù hợp và kiểm tra dữ liệu đa ngôn ngữ.

### 8.3. Unicode và ký tự hiển thị

Một ký tự người dùng nhìn thấy có thể gồm nhiều code points (ví dụ dấu tổ hợp). Vì vậy, wildcard `_` và các regex character classes không nhất thiết tương đương **một grapheme hiển thị** theo cách con người nhìn trên UI.

Không xây validation độ dài tên người dùng chỉ bằng “mẫu có đúng N dấu underscore” nếu nghiệp vụ cần đếm grapheme clusters.

### 8.4. ILIKE trong truy vấn không có index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE 'postgresql%';
```

Nếu chỉ có B-tree thông thường trên title, PostgreSQL thường không thể tận dụng B-tree cho prefix case-insensitive theo cách đơn giản như `LIKE 'PostgreSQL%'`.

Hai giải pháp cần biết:

1. Index trên expression `lower(title)` cho **prefix pattern** trên expression tương ứng.
2. Trigram index `pg_trgm` cho các kiểu `ILIKE`/substring/pattern linh hoạt.

## 9. POSIX regular expressions: khác LIKE về bản chất

PostgreSQL cung cấp các toán tử regular expression:

| Toán tử | Ý nghĩa |
| --- | --- |
| `~` | Regex match, phân biệt hoa/thường |
| `~*` | Regex match, không phân biệt hoa/thường |
| `!~` | Regex không match, phân biệt hoa/thường |
| `!~*` | Regex không match, không phân biệt hoa/thường |

Điểm quan trọng: regex operator thường tìm **một phần chuỗi phù hợp**, không ngầm buộc toàn bộ chuỗi match như LIKE.

```sql
SELECT
    'PostgreSQL indexing' ~ 'SQL' AS substring_regex,
    'PostgreSQL indexing' ~ '^SQL' AS not_at_start,
    'PostgreSQL indexing' ~ 'indexing$' AS at_end,
    'PostgreSQL indexing' ~* 'postgresql' AS ignore_case;
```

### 9.1. Anchor ở đầu chuỗi: `^`

```sql
SELECT 'Java indexing' ~ '^Java' AS starts_java;
```

### 9.2. Anchor cuối chuỗi: `$`

```sql
SELECT 'guide.sql' ~ '\.sql$' AS ends_sql;
```

`\.` có ý nghĩa **dấu chấm literal**, vì dấu chấm regex `.` bình thường match một ký tự bất kỳ theo semantics regex.

### 9.3. Buộc toàn bộ chuỗi: `^...$`

```sql
SELECT
    'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$' AS valid_code,
    'prefix AB-1234 suffix' ~ '^[A-Z]{2}-[0-9]{4}$' AS invalid_full;
```

Dùng anchor khi validation yêu cầu toàn bộ chuỗi, thay vì chỉ tìm một đoạn con.

### 9.4. Không nhầm regex `.*` với LIKE `%`

| Ý nghĩa | LIKE | Regex |
| --- | --- | --- |
| Bất kỳ chuỗi ký tự | `%` | `.*` |
| Một ký tự bất kỳ | `_` | `.` |
| Đầu chuỗi | Ngầm match toàn chuỗi; pattern tiền tố không cần anchor | `^` |
| Cuối chuỗi | Ngầm match toàn chuỗi; pattern hậu tố không cần anchor | `$` |
| Một chữ số | Không có character class | `[0-9]` hoặc `[[:digit:]]` |
| “abc” ở bất kỳ vị trí | `'%abc%'` | `'abc'` |

**Không dùng regex syntax trong LIKE:** `LIKE 'A.*B'` tìm chuỗi có dấu chấm và dấu sao literal, không có ý nghĩa “A rồi bất kỳ thứ gì rồi B”.

## 10. Regex character classes và quantifiers

### 10.1. Character class

```sql
SELECT
    'user007' ~ '[[:digit:]]' AS contains_digit,
    'A7' ~ '^[A-Z][0-9]$' AS uppercase_and_digit,
    'B' ~ '^[A-Z]$' AS one_uppercase,
    'B' ~ '^[^0-9]+$' AS no_digits;
```

Những lớp POSIX hay gặp:

| Lớp | Ý nghĩa khái quát |
| --- | --- |
| `[[:digit:]]` | Chữ số |
| `[[:alpha:]]` | Chữ cái theo quy tắc locale/regex |
| `[[:alnum:]]` | Chữ cái hoặc số |
| `[[:space:]]` | Ký tự khoảng trắng |
| `[[:lower:]]` | Chữ thường |
| `[[:upper:]]` | Chữ hoa |

Phạm vi Unicode và locale của character classes phải được xác nhận trong môi trường thực tế nếu dùng để kiểm tra danh tính/mã hóa ngôn ngữ.

### 10.2. Quantifiers

| Quantifier | Ý nghĩa |
| --- | --- |
| `*` | 0 hoặc nhiều lần |
| `+` | 1 hoặc nhiều lần |
| `?` | 0 hoặc 1 lần |
| `{n}` | Đúng n lần |
| `{n,}` | Ít nhất n lần |
| `{n,m}` | Từ n đến m lần |

Ví dụ:

```sql
SELECT
    'abc' ~ '^a.*c$' AS any_between,
    'abbbc' ~ '^ab+c$' AS one_or_more_b,
    'ac' ~ '^ab?c$' AS optional_b,
    'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$' AS code_format;
```

### 10.3. Alternation và grouping

```sql
SELECT
    'PostgreSQL guide' ~ '^(PostgreSQL|Java)' AS starts_supported,
    'Python guide' ~ '^(PostgreSQL|Java)' AS not_supported;
```

Dấu `|` trong regex là **OR bên trong pattern**, khác với toán tử boolean `OR` giữa hai điều kiện SQL.

### 10.4. Word boundaries

PostgreSQL hỗ trợ các escape xác định ranh giới từ trong regex (theo engine/locale phù hợp), ví dụ `\m` ở đầu từ và `\M` ở cuối từ:

```sql
SELECT
    'learn PostgreSQL today' ~ '\mPostgreSQL\M'
        AS whole_word_found,
    'learn PostgreSQLish today' ~ '\mPostgreSQL\M'
        AS not_whole_word;
```

Đừng mặc định các word boundaries này hiểu đầy đủ mọi quy tắc tách từ của tiếng Việt hoặc những ngôn ngữ không dùng dấu cách đơn giản.

### 10.5. Thực hành trên dataset

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~ '^(PostgreSQL|Java)'
ORDER BY document_id
LIMIT 20;
```

Một regex có literal prefix/alternation rõ ràng có thể giúp planner và `pg_trgm` trích xuất điều kiện ứng viên, nhưng không có bảo đảm mọi alternation sẽ sử dụng index hiệu quả.

## 11. Những điều regex không làm giống một công cụ ngôn ngữ tự nhiên

Regex mạnh trong việc **nhận dạng mẫu ký tự**, không tự hiểu:

- Từ đồng nghĩa (database ↔ cơ sở dữ liệu).
- Từ gốc và biến thể hình thái.
- Lỗi chính tả và xếp hạng mức liên quan.
- Phân tách từ tiếng Việt theo nghĩa ngôn ngữ học.
- Unicode normalization của dữ liệu nhiều nguồn.
- Khoảng cách chỉnh sửa (*edit distance*) theo UX mong muốn.

Nếu người dùng nhập “hướng dẫn postgres index” và muốn tìm tài liệu có nhiều từ liên quan ở bất kỳ vị trí nào, PostgreSQL Full Text Search có thể phù hợp hơn hàng loạt điều kiện `ILIKE '%...%'`, dù vẫn cần đánh giá hỗ trợ ngôn ngữ.

## 12. Regex trong SQL string: hai lớp escaping

Có thể có hai lớp:

1. **SQL string literal** xử lý chuỗi được truyền cho regex engine.
2. **Regex engine** diễn giải ký tự như `.`, `*`, `+`, `\` và anchors.

Ví dụ:

```sql
SELECT 'report.sql' ~ '\.sql$' AS match_extension;
```

Với `standard_conforming_strings = on`, dấu backslash trong SQL string thông thường được giữ nguyên để regex engine nhận `\.`.

Nếu dùng escape string syntax `E'...'`, cần escape backslash ở lớp SQL:

```sql
SELECT 'report.sql' ~ E'\\.sql$' AS match_extension;
```

### 12.1. Kiểm tra setting

```sql
SHOW standard_conforming_strings;
```

Trong ứng dụng, nên **bind regex pattern** bằng parameter khi cần, thay vì tự nối chuỗi SQL và backslash.

### 12.2. Không nhầm với Java string escaping

Trong Java source:

```java
String pattern = "\\.sql$";
```

giá trị Java runtime là `\.sql$`, được truyền tới PostgreSQL regex engine qua bind parameter.

Nếu bạn đặt Java literal `"\.sql$"`, đó không phải cú pháp Java string hợp lệ vì escape `\.` không được Java hỗ trợ trực tiếp.

### 12.3. Literal text và regex patterns

Nếu người dùng nhập dấu chấm `.` với ý định tìm đúng dấu chấm, đưa nguyên giá trị này vào toán tử regex sẽ match nhiều ký tự khác.

Parameterization bảo vệ cấu trúc SQL nhưng **không tự biến regex metacharacters thành literal**. Cần validation/quoting phù hợp hoặc chọn LIKE với escape literal.

## 13. Các hàm regex thường dùng

PostgreSQL có nhóm hàm hỗ trợ lấy match, thay thế và tách chuỗi. Những hàm mới hơn có thể khác theo phiên bản; tập ví dụ dưới ưu tiên các hàm phổ biến.

### 13.1. `regexp_match`: match đầu tiên dưới dạng mảng

```sql
SELECT regexp_match(
    'Order AB-1234 received',
    '([A-Z]{2})-([0-9]{4})'
) AS captured_groups;
```

Kết quả kiểu `text[]` chứa các nhóm bắt được, ví dụ `{AB,1234}`. Nếu pattern không khớp, kết quả thường là NULL.

Nếu regex có capture groups, array chứa những groups tương ứng; nếu không có capture group, có thể chứa toàn bộ phần match.

### 13.2. Lấy một nhóm cụ thể

```sql
SELECT
    (regexp_match(
        'Order AB-1234 received',
        '([A-Z]{2})-([0-9]{4})'
    ))[1] AS prefix,
    (regexp_match(
        'Order AB-1234 received',
        '([A-Z]{2})-([0-9]{4})'
    ))[2] AS number_part;
```

Trong query thực tế, tránh gọi nhiều lần cùng regex đắt nếu có thể tính một lần trong subquery/LATERAL.

### 13.3. `regexp_matches`: hàm trả tập kết quả

```sql
SELECT m.parts
FROM regexp_matches(
    'A-12 B-34 C-56',
    '([A-Z])-([0-9]+)',
    'g'
) AS m(parts);
```

Flag `g` nghĩa là **global**: trả nhiều matches. Vì đây là **set-returning function**, nếu không match nó có thể không phát ra dòng kết quả nào; đó là khác biệt quan trọng với `regexp_match` trả NULL.

### 13.4. Regex matches theo từng row

```sql
SELECT
    d.document_id,
    m.parts[1] AS first_number
FROM text_search_lab.documents AS d
CROSS JOIN LATERAL regexp_matches(
    d.title,
    '([0-9]+)',
    'g'
) AS m(parts)
WHERE d.document_id <= 10
ORDER BY d.document_id;
```

`LATERAL` cho phép mỗi row chạy hàm với title của row đó. Một document có thể phát nhiều rows nếu pattern match nhiều lần.

### 13.5. `regexp_replace`

```sql
SELECT regexp_replace(
    'Invoice AB-1234 / CD-9999',
    '[0-9]+',
    '[NUMBER]',
    'g'
) AS redacted;
```

Kết quả thay mọi nhóm chữ số bằng `[NUMBER]`. Không nhầm “redact bằng regex demo” với một quy trình xóa dữ liệu nhạy cảm được kiểm chứng; biểu thức có thể bỏ sót những định dạng thực tế.

### 13.6. `regexp_split_to_array`

```sql
SELECT regexp_split_to_array(
    'java,postgresql; index ;query',
    '[,;][[:space:]]*'
) AS keywords;
```

Tách dựa trên dấu phẩy/chấm phẩy và khoảng trắng theo pattern.

### 13.7. Hàm nâng cao theo phiên bản

Một số phiên bản PostgreSQL có thêm `regexp_count`, `regexp_instr`, `regexp_like`, `regexp_substr` và những chữ ký mở rộng.

Trước khi dùng trong code production, kiểm tra phiên bản/cú pháp cụ thể bằng tài liệu hoặc hệ thống đang chạy. Trong bài này, các toán tử `~` và hàm `regexp_match(es)`, `regexp_replace`, `regexp_split_to_array` đủ cho phần nền tảng.

## 14. SIMILAR TO: cú pháp SQL regex lai, không phải POSIX regex

`SIMILAR TO` kết hợp wildcard `%`, `_` kiểu LIKE với một số cấu trúc regex.

```sql
SELECT
    'PostgreSQL indexing' SIMILAR TO '(PostgreSQL|Java)%'
        AS one_of_two_prefixes,
    'Python indexing' SIMILAR TO '(PostgreSQL|Java)%'
        AS not_supported;
```

**Khác với `~`**, `SIMILAR TO` yêu cầu pattern match **toàn chuỗi**.

### 14.1. Các điểm cần nhớ

- `%` và `_` vẫn có nghĩa theo kiểu SQL pattern.
- `|` và `()` có thể tạo alternation/grouping.
- Không mặc định thay `%` bằng `.*` như POSIX regex.
- Khả năng tối ưu và hỗ trợ nondeterministic collation khác với LIKE/regex tùy phiên bản.

### 14.2. Nên dùng công cụ nào?

| Yêu cầu | Ưu tiên xem xét |
| --- | --- |
| Bắt đầu bằng một literal prefix | `LIKE 'prefix%'` |
| Chứa một chuỗi literal | `LIKE '%term%'` hoặc trigram |
| Case-insensitive wildcard | `ILIKE` / normalizing expression |
| Mẫu phức tạp với class/quantifier | `~` / `~*` |
| Ngữ nghĩa pattern kiểu SQL với alternation | `SIMILAR TO` nếu thật sự cần |
| Tìm theo từ khóa văn bản | Full Text Search |

Thông thường dùng `LIKE` hoặc POSIX regex sẽ dễ giải thích hơn cố ép mọi trường hợp vào `SIMILAR TO`.

## 15. Vì sao LIKE có thể nhanh hoặc rất chậm?

Xét ba truy vấn:

```sql
-- A. So khớp toàn bộ giá trị:
SELECT document_id
FROM text_search_lab.documents
WHERE title = 'Java indexing patterns 17';

-- B. So khớp tiền tố:
SELECT document_id
FROM text_search_lab.documents
WHERE title LIKE 'Java indexing%';

-- C. Chứa chuỗi ở bất kỳ vị trí:
SELECT document_id
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

Khả năng dùng B-tree thông thường không giống nhau:

1. Equality thường có index path rõ ràng.
2. Literal prefix có thể được biến thành một **index range** khi operator class/collation thích hợp.
3. Leading wildcard `%` làm mất thông tin “giá trị bắt đầu từ đâu”, nên B-tree không dễ tìm một phạm vi khóa liên tục để đọc.

### 15.1. Đừng định nghĩa “có index” là “query sẽ dùng index”

PostgreSQL planner so sánh chi phí:

- Scan toàn heap tuần tự.
- Đọc index + heap cho các rows phù hợp.
- Bitmap scan theo index.
- Các yếu tố sort, LIMIT, cache và row width.

Với bảng rất nhỏ hoặc pattern match 90% rows, `Seq Scan` có thể hợp lý dù index hỗ trợ được predicate.

### 15.2. Selectivity quan trọng

`LIKE 'PostgreSQL%'` có thể match 1% rows trong lab.

`LIKE 'Database%'` match phần lớn rows.

Cả hai đều có prefix, nhưng phương án tối ưu không nhất thiết giống nhau.

### 15.3. Rows returned và rows scanned khác nhau

```sql
SELECT COUNT(*)
FROM text_search_lab.documents
WHERE body ILIKE '%database%';
```

Query chỉ trả **một số đếm** cho client, nhưng executor vẫn phải tìm/kiểm tra các rows cần thiết để đếm.

Đừng suy “query trả một dòng nên chắc nhanh”.

## 16. B-tree index cho LIKE tiền tố

Tạo B-tree index:

```sql
CREATE INDEX documents_title_btree_idx
ON text_search_lab.documents (title);

ANALYZE text_search_lab.documents;
```

Trong một số collations, planner có thể dùng B-tree thông thường cho:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

Nhưng trong các locale không phải C, operator class mặc định có thể **không hỗ trợ tối ưu prefix LIKE theo cách bạn mong đợi**.

### 16.1. `text_pattern_ops`

Với cột `text`:

```sql
CREATE INDEX documents_title_prefix_idx
ON text_search_lab.documents (title text_pattern_ops);
```

`text_pattern_ops` là B-tree operator class hỗ trợ các pattern comparisons thích hợp cho prefix searches trong collations nơi index mặc định không thuận lợi.

Các operator classes tương ứng khác tồn tại cho `varchar`/`char` trong những tình huống phù hợp.

### 16.2. Cách dùng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

Một dạng plan có thể là:

```text
Index Scan using documents_title_prefix_idx on documents
  Index Cond: (
    (title ~>=~ 'PostgreSQL'::text)
    AND (title ~<~ 'PostgreSQM'::text)
  )
  Filter: (title ~~ 'PostgreSQL%'::text)
```

Các operator nội bộ và upper bound trong ví dụ chỉ **minh họa cơ chế prefix range**; tên toán tử/giá trị bound chính xác do planner sinh và có thể khác. Đọc plan thực tế trên máy, không chép cấu trúc text này như SQL.

### 16.3. Không phải mọi regex/pattern đều dùng text_pattern_ops

Ví dụ:

```sql
WHERE title LIKE '%PostgreSQL'
```

có leading wildcard, nên index B-tree không tự tạo được một phạm vi prefix hữu ích từ chữ PostgreSQL ở cuối mẫu.

Tương tự, biểu thức nhiều wildcard phức tạp có thể chỉ khai thác được **đoạn prefix literal đầu tiên**, rồi lọc phần còn lại.

### 16.4. Index type phải phù hợp cột

Nếu `title` là `varchar`, cân nhắc operator class tương ứng. Không tùy tiện cast mọi dữ liệu sang text và tạo index không cần thiết.

### 16.5. Pattern index không thay thế index so sánh theo collation

`text_pattern_ops` được thiết kế cho pattern comparisons; nó không nhất thiết phục vụ các range/order theo locale giống B-tree operator class mặc định.

Nếu workload có cả `ORDER BY title` theo locale và `LIKE 'prefix%'`, có thể cần đánh giá những index definitions khác nhau và tổng write cost.

## 17. Expression index trên lower(title) cho prefix case-insensitive

Một cách thay `ILIKE 'postgresql%'` bằng predicate dùng expression là:

```sql
WHERE lower(title) LIKE 'postgresql%'
```

Tạo expression index:

```sql
CREATE INDEX documents_lower_title_prefix_idx
ON text_search_lab.documents
    ((lower(title)) text_pattern_ops);
```

Thử:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE 'postgresql%';
```

Planner có thể dùng index trên **đúng expression** `lower(title)`.

### 17.1. Vì sao index trên title chưa đủ?

Index trên:

```sql
(title text_pattern_ops)
```

không tự tương đương index trên:

```sql
(lower(title) text_pattern_ops)
```

vì `lower(title)` là một expression khác với cột gốc.

### 17.2. Khi người dùng truyền tiền tố

Giữ parameter binding:

```sql
PREPARE title_prefix(text) AS
SELECT document_id, title
FROM text_search_lab.documents
WHERE lower(title) LIKE $1;
```

Ở ứng dụng, bind giá trị đã chuẩn hóa kiểu `postgresql%`. Nếu cần bảo đảm custom plan tận dụng prefix tham số, so EXPLAIN custom/generic theo `plan_cache_mode` và các index thật.

### 17.3. Vì sao generic plan có thể ảnh hưởng lựa chọn index?

Một generic prepared plan với:

```sql
WHERE lower(title) LIKE $1
```

không được tối ưu dựa trên prefix literal của từng lần chạy giống custom plan. Nếu planner không thể suy ra một prefix cố định để giới hạn index range khi lập kế hoạch, nó có thể chọn access path khác.

Không kết luận rằng “tạo expression index là generic plan chắc chắn dùng nó cho mọi pattern”.

### 17.4. Case normalization không đồng nghĩa accent normalization

`lower('Café')` thay chữ hoa/thường theo quy tắc liên quan nhưng không tự biến `é` thành `e` trong mọi cấu hình.

Nếu cần tìm kiếm accent-insensitive, phải xác định normalization/collation và index strategy tương thích. Extension `unaccent` có thể hữu ích trong một số hệ thống, nhưng cách sử dụng trực tiếp trong expression index cần hiểu volatility/immutable assumptions và dictionary configuration; không nên copy một wrapper `IMMUTABLE` tùy tiện vào production.

### 17.5. Không tạo nhiều index cùng chức năng

Trong lab ta tạo nhiều indexes để so sánh. Production cần đánh giá hiệu quả và chi phí ghi trước khi giữ lại tất cả.

## 18. Leading wildcard: vì sao B-tree không đủ?

Hai patterns:

```sql
WHERE title LIKE 'PostgreSQL%'
WHERE title LIKE '%PostgreSQL%'
```

khác nhau về thông tin đầu vào của B-tree.

### 18.1. Prefix là một range

Những chuỗi bắt đầu bằng `PostgreSQL` nằm gần nhau trong một thứ tự từ điển phù hợp. B-tree có thể giới hạn phạm vi ứng viên.

### 18.2. Contains không có một range từ khóa đơn giản

Chuỗi chứa `PostgreSQL` có thể bắt đầu bằng:

```text
A PostgreSQL guide
Best PostgreSQL book
Learn PostgreSQL
PostgreSQL guide
Why PostgreSQL?
```

Các khóa không nằm trong một prefix range duy nhất. B-tree bình thường có thể phải xét gần như mọi key/row.

### 18.3. Suffix cũng tương tự

```sql
WHERE title LIKE '%guide'
```

chỉ biết đuôi, không biết đầu.

Nếu suffix query cực quan trọng, một chiến lược riêng có thể dùng **expression index trên chuỗi đảo ngược** và truy vấn prefix trên chuỗi đảo ngược; nhưng cần đồng bộ expression, collation, Unicode semantics và workload. Không coi đây là giải pháp chung tốt hơn trigram.

### 18.4. Thử LIKE chứa chuỗi

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%indexing%';
```

Trước khi tạo trigram index, Seq Scan có thể là đường truy cập hợp lý, vì index B-tree prefix không trực tiếp phục vụ leading wildcard.

## 19. `pg_trgm`: index cho substring, ILIKE và regex

PostgreSQL có extension `pg_trgm`, cung cấp thao tác similarity và operator classes cho **trigram indexing**.

**Trigram** là nhóm ba ký tự liên tiếp theo cơ chế chuẩn hóa/tách từ của extension. Chỉ mục lưu thông tin về các trigrams trong văn bản, giúp tìm **candidate rows** có khả năng chứa pattern.

### 19.1. Bật extension trong database lab

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Lệnh cần extension khả dụng trên server và quyền phù hợp. Trên managed PostgreSQL, danh sách extension và quyền cài đặt có thể bị giới hạn.

### 19.2. Tạo GIN trigram index trên title

```sql
CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

Với extension/operator class được cài trong schema có thể tra cứu qua `search_path`, định nghĩa này có thể dùng trực tiếp. Nếu extension nằm ở schema khác, cần định danh operator class phù hợp.

### 19.3. LIKE contains có thể dùng trigram index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

Một plan minh họa:

```text
Bitmap Heap Scan on documents
  Recheck Cond: (title ~~ '%indexing%'::text)
  Heap Blocks: exact=...
  -> Bitmap Index Scan on documents_title_trgm_idx
       Index Cond: (title ~~ '%indexing%'::text)
```

Lưu ý:

- Đây là **plan minh họa**, không bảo đảm planner luôn chọn nó.
- `pg_trgm` xác định candidate rows từ trigrams rồi phải xác nhận điều kiện LIKE thật sự.
- `Recheck Cond` là điểm quan trọng khi đọc bitmap scans.

### 19.4. ILIKE cũng có thể được hỗ trợ

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%POSTGRESQL%';
```

Trigram index có thể hữu ích với case-insensitive contains search.

### 19.5. Regex trên title

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~* 'postgreSQL.*guide';
```

Với regex có thể trích xuất các literal trigrams hữu ích, `pg_trgm` cũng có khả năng hỗ trợ tìm candidates. Không phải mọi regex đều index-friendly.

### 19.6. Không phải extension là “máy tìm regex” thay executor

Index dùng để lọc candidates; PostgreSQL vẫn phải áp dụng semantics đầy đủ của LIKE/ILIKE/regex, nhất là với wildcard/alternation phức tạp.

Không kết luận rằng index trả về một candidate là **đã được xác nhận match** mà không cần recheck.

## 20. GIN và GiST trigram indexes: khác nhau

`pg_trgm` hỗ trợ cả GIN và GiST operator classes.

### 20.1. GIN

```sql
CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

GIN thường được cân nhắc cho các truy vấn lọc văn bản theo trigrams, ví dụ LIKE/ILIKE có phần literal đủ dài.

### 20.2. GiST

```sql
CREATE INDEX documents_title_trgm_gist_idx
ON text_search_lab.documents
USING gist (title gist_trgm_ops);
```

GiST có các đặc điểm phục vụ similarity/distance ordering, bên cạnh pattern matching trong những trường hợp hỗ trợ.

### 20.3. Lựa chọn thực tế

| Khía cạnh | GIN trigram | GiST trigram |
| --- | --- | --- |
| Contains/ILIKE/regex filtering | Có thể tốt | Có thể tốt |
| Cách lưu trigrams | Inverted index dạng GIN | Signature/representation theo GiST opclass |
| Recheck/false positives | Phụ thuộc pattern/index path | Có thể phát sinh nhiều rechecks tùy signature |
| Similarity nearest-neighbor order | Không cùng khả năng KNN index ordering như GiST | Hữu ích cho KNN với distance operator thích hợp |
| Chi phí lưu trữ/ghi | Phụ thuộc dữ liệu, pending list và workload | Phụ thuộc signature length và workload |
| Có phương án “luôn nhanh nhất”? | Không | Không |

Đừng tự tạo **cả hai index** cho cùng cột trong production mà chưa đo vì chúng cùng tăng storage và write amplification.

### 20.4. GIN pending list và write workload

GIN indexes có cơ chế pending entries tùy cấu hình, có thể ảnh hưởng tốc độ INSERT và thời điểm cleanup. Với bảng cập nhật liên tục, cần theo dõi write latency, autovacuum và kích thước index.

Chọn GIN/GiST dựa trên tỷ lệ đọc/ghi, dạng pattern, yêu cầu ranking và benchmark.

## 21. Trigram không hiệu quả với mọi pattern

Nhược điểm quan trọng là **phải trích xuất được những trigrams hữu ích** từ pattern.

### 21.1. Mẫu quá ngắn

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%ab%';
```

Chuỗi literal `ab` chỉ có hai ký tự. Điều này có thể không cung cấp một tập trigrams đủ chọn lọc cho index.

### 21.2. Regex quá mơ hồ

```sql
WHERE title ~ '.*'
```

match hầu hết non-NULL values theo regex semantics, không tạo điều kiện ứng viên có ích. Một trigram index không thể biến pattern không chọn lọc thành phép tìm kiếm nhanh.

### 21.3. Ký tự đặc biệt chia nhỏ các đoạn literal

Ví dụ:

```sql
WHERE title LIKE '%a%b%c%'
```

có nhiều wildcard và mỗi literal run rất ngắn. Index có thể phải scan lượng lớn candidate entries hoặc không có trigrams hữu ích.

### 21.4. Trigram recheck và false positives

Trigram index tìm những candidate rows có thể thỏa pattern; việc xuất hiện các trigrams không nhất thiết chứng minh thứ tự/vị trí/case/điều kiện regex đầy đủ.

Executor vẫn cần kiểm tra điều kiện thực tế với operator tương ứng.

### 21.5. Nếu không trích xuất được trigrams

Trong những trường hợp pattern không cho phép trích xuất trigrams, cách tìm bằng trigram index có thể thoái hóa thành **quét rất nhiều hoặc toàn bộ index entries**, khiến hiệu năng kém hơn mong đợi.

Đừng hứa “GIN trigram index sẽ tăng tốc mọi `ILIKE '%...%'`”.

### 21.6. Kiểm tra selectivity

Dù có literal dài, nếu nó xuất hiện ở 95% rows, đọc phần lớn bảng vẫn có thể rẻ hơn index-driven heap lookups.

Sự hữu ích của index phụ thuộc cả **độ dài literal** và **tần suất thực tế**.

## 22. Trigram index trên body: chi phí và giới hạn

`body` thường dài hơn `title`. Một GIN trigram index trên body có thể rất lớn.

### 22.1. Thử riêng trong lab

```sql
CREATE INDEX documents_body_trgm_idx
ON text_search_lab.documents
USING gin (body gin_trgm_ops);

ANALYZE text_search_lab.documents;
```

### 22.2. Query chứa cụm kỹ thuật

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE body ILIKE '%pg_trgm%';
```

**Chú ý:** dấu `_` trong LIKE là wildcard. Nếu muốn tìm đúng chuỗi literal `pg_trgm`:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE body ILIKE '%pg!_trgm%' ESCAPE '!';
```

### 22.3. Vì sao index trên body đắt?

- Mỗi hàng có thể chứa rất nhiều trigrams.
- GIN index có nhiều entries/postings.
- INSERT/UPDATE body cần bảo trì index.
- Build/reindex có thể tốn I/O, CPU, WAL và disk.
- Truy vấn kết quả rất phổ biến vẫn có thể kém chọn lọc.

### 22.4. Đừng index tất cả cột văn bản

Hãy xem nhóm query thật sự được người dùng gọi:

- Chỉ tìm title?
- Tìm slug/identifier?
- Tìm body?
- Tìm nhiều từ/đoạn?
- Tìm toàn văn có ranking?

Thiết kế chỉ mục theo workload. Có thể một FTS index cho body và trigram index cho title là cân bằng hơn GIN trigram trên mọi cột.

## 23. So sánh với PostgreSQL Full Text Search

Full Text Search (FTS) được thiết kế cho **tìm theo từ/lexeme**, không giống substring matching.

### 23.1. Ví dụ trên body

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE to_tsvector('simple', body)
      @@ plainto_tsquery('simple', 'query planning')
LIMIT 20;
```

`'simple'` là một text-search configuration cơ bản, không có nghĩa PostgreSQL có stemming/word segmentation hoàn chỉnh cho mọi ngôn ngữ.

### 23.2. Index FTS

```sql
CREATE INDEX documents_body_fts_idx
ON text_search_lab.documents
USING gin (to_tsvector('simple', body));
```

### 23.3. FTS vs trigram

| Nhu cầu | LIKE/ILIKE + trigram | FTS |
| --- | --- | --- |
| Chứa chuỗi con ở bất kỳ vị trí | Thường phù hợp | Không phải mục tiêu trực tiếp |
| Tìm một từ khóa theo lexeme | Có thể | Phù hợp |
| Nhiều từ với toán tử logic | Regex/LIKE có thể rối | Có cú pháp tsquery phù hợp |
| Ranking mức độ liên quan | Có similarity theo trigrams | Có ts_rank/ts_rank_cd theo cấu hình |
| Prefix của từ | Có LIKE prefix | Có truy vấn lexeme prefix trong điều kiện hỗ trợ |
| Tìm lỗi gõ/chuỗi gần đúng | `pg_trgm` similarity có ích | FTS thông thường không phải fuzzy edit-distance |
| Tiếng Việt và từ tách phức tạp | Cần xử lý normalization | Cần tokenizer/config phù hợp; không mặc định có sẵn |

### 23.4. Đừng kỳ vọng FTS tìm mọi substring

Ví dụ người dùng tìm `gres` ở giữa `PostgreSQL`: FTS theo lexeme không nhất thiết tìm substring này; trigram phù hợp hơn nếu sản phẩm muốn contains/fuzzy matching.

### 23.5. Tránh chuỗi điều kiện ILIKE nhiều từ không kiểm soát

```sql
WHERE body ILIKE '%postgresql%'
  AND body ILIKE '%index%'
  AND body ILIKE '%plan%'
```

Có thể đúng về mặt literal substrings nhưng không có ngữ nghĩa tách từ/ranking như một search engine. Với nhiều từ, hãy cân nhắc FTS để query được mô hình hóa rõ hơn.

## 24. Case, accent, Unicode và collation

### 24.1. Collation ảnh hưởng so sánh chuỗi

Kết quả so khớp case-insensitive và khả năng B-tree dùng pattern optimization chịu ảnh hưởng của locale/collation và phiên bản.

PostgreSQL có các kiểu collations khác nhau, trong đó một số **nondeterministic collations** hỗ trợ so sánh không phân biệt những khác biệt nhất định. Tuy nhiên, **khả năng áp dụng các pattern operators trong nondeterministic collation không đồng nhất giữa LIKE, ILIKE và regex** và có thể khác theo phiên bản.

Vì vậy, với ứng dụng đa ngôn ngữ cần thử đúng:

- PostgreSQL version.
- Database/column/expression collation.
- Chuỗi có dấu, hoa/thường, dấu tổ hợp.
- Kế hoạch query và index matching.

### 24.2. Không đánh đồng ILIKE với “không dấu”

`Café` có thể khác `Cafe` dù phép so khớp không phân biệt chữ hoa/thường. Nếu UX yêu cầu tìm không dấu, cần normalization có chủ đích.

### 24.3. Unicode normalization

Hai chuỗi trông giống nhau có thể có biểu diễn Unicode khác nhau (precomposed vs combining code points). LIKE/regex không phải một bước chuẩn hóa Unicode tự động theo yêu cầu ứng dụng.

Cần thống nhất chuẩn lưu trữ và kiểm thử dữ liệu từ nhiều nguồn.

### 24.4. Regex character classes và locale

`[[:alpha:]]` và cách xác định ranh giới từ chịu ảnh hưởng quy tắc engine/locale, không phải một parser ngôn ngữ học đa ngôn ngữ hoàn chỉnh.

Nếu validate mã kỹ thuật phải thuộc ASCII, nên viết pattern rõ:

```sql
SELECT 'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$';
```

Nếu validate tên người, địa chỉ hoặc văn bản đa ngôn ngữ, đừng đơn giản giới hạn bằng `[A-Za-z]+` rồi kết luận hợp lệ cho mọi người dùng.

### 24.5. Kiểm thử ví dụ tiếng Việt

```sql
SELECT
    'Cơ sở dữ liệu' ILIKE '%dữ liệu%' AS case_insensitive,
    'Cơ sở dữ liệu' ILIKE '%du lieu%' AS no_automatic_unaccent;
```

Kết quả phụ thuộc collation/phiên bản trong một số trường hợp, nên đừng dùng ví dụ này như một lời hứa bất biến về mọi deployment. Điều cần hiểu là yêu cầu tìm kiếm **không dấu** phải được xác định rõ ràng và kiểm thử.

## 25. EXPLAIN cho LIKE/ILIKE/regex

Công cụ quan trọng nhất:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%indexing%';
```

### 25.1. Seq Scan

Khi không có index phù hợp hoặc pattern match quá nhiều rows:

```text
Seq Scan on documents
  Filter: (title ~~* '%indexing%'::text)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

`~~*` là cách PostgreSQL có thể hiển thị operator tương ứng `ILIKE` trong plan text.

### 25.2. Index Scan B-tree prefix

Với prefix index phù hợp:

```text
Index Scan using documents_title_prefix_idx on documents
  Index Cond: (...)
  Filter: (title ~~ 'PostgreSQL%'::text)
```

Index giúp tìm một khoảng candidate keys, rồi có thể vẫn cần Filter LIKE đầy đủ.

### 25.3. Bitmap Heap Scan từ trigram index

```text
Bitmap Heap Scan on documents
  Recheck Cond: (title ~~* '%indexing%'::text)
  Heap Blocks: exact=...
  -> Bitmap Index Scan on documents_title_trgm_idx
       Index Cond: (title ~~* '%indexing%'::text)
```

Bitmap Index Scan tìm candidate positions, Bitmap Heap Scan đọc heap và xác nhận predicate.

### 25.4. Recheck có phải index kém?

Không. Recheck là một phần semantics hợp lệ của bitmap/index access paths. Tuy nhiên, nếu `Rows Removed by Index Recheck` rất cao hoặc có lossy heap blocks, hãy điều tra selectivity/work_mem/index type.

### 25.5. Chỉ số quan trọng

| Trường EXPLAIN | Câu hỏi |
| --- | --- |
| `cost` | Planner ước lượng chi phí thế nào? |
| `rows` | Số hàng dự đoán? |
| `actual rows` | Số hàng thực tế? |
| `Rows Removed by Filter` | Bao nhiêu hàng bị lọc sau khi scan? |
| `Index Cond` | Điều kiện nào thật sự dùng để truy cập index? |
| `Recheck Cond` | Predicate nào cần được xác nhận lại? |
| `Heap Blocks: exact/lossy` | Bitmap có mất độ chính xác không? |
| `Buffers: shared hit/read` | Khối nào từ shared buffers, khối nào cần đọc vào? |
| `Planning Time` | Thời gian lập kế hoạch? |
| `Execution Time` | Thời gian executor chạy? |
| `loops` | Node chạy bao nhiêu lần? |

### 25.6. Cost không phải mili-giây

`cost=0.00..3000.00` là đơn vị chi phí ước lượng, không phải “3 giây”.

### 25.7. Buffers không đồng nghĩa physical disk reads

`shared hit` là block đã ở shared buffers. `shared read` là block cần đọc vào shared buffers, có thể được OS filesystem cache phục vụ. Cần đo nhiều lần trong điều kiện cache/tải được ghi nhận.

### 25.8. EXPLAIN ANALYZE thật sự thực thi query

Với SELECT, nó thực thi nhưng không cần gửi toàn bộ result rows tới ứng dụng như SELECT thông thường. Với DML:

```sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE ...
```

sẽ thực sự UPDATE dữ liệu. Không dùng DML EXPLAIN ANALYZE tùy tiện trên production; trong lab, dùng transaction/ROLLBACK và hiểu side effects còn lại.

## 26. Tính chọn lọc, thống kê và pattern parameter

PostgreSQL dùng thống kê để ước lượng số hàng có thể match một predicate.

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'text_search_lab'
  AND tablename = 'documents'
  AND attname IN ('title', 'category', 'slug')
ORDER BY attname;
```

### 26.1. Prefix estimate khác substring estimate

Prefix `'PostgreSQL%'` có thể giúp planner ước lượng theo phân bố chuỗi và index range trong những điều kiện phù hợp.

Pattern `'%sql%'` hay regex phức tạp khó ước lượng hơn vì phụ thuộc vị trí và tổ hợp các ký tự.

### 26.2. Prepared statements và generic plans

```sql
PREPARE search_title(text) AS
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE $1;
```

Có thể chạy:

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('PostgreSQL%');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('%sql%');

ROLLBACK;
```

Với custom plan, planner có thể xem pattern cụ thể để ước lượng prefix/contains.

### 26.3. So generic

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('PostgreSQL%');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_title('%sql%');

ROLLBACK;
```

Generic plan cần dùng được cho mọi giá trị `$1`, không thể giả định pattern nào cũng có prefix dài. Vì vậy, shape của plan có thể khác custom.

```sql
DEALLOCATE search_title;
```

### 26.4. Không bỏ parameter binding để ép custom

Bind parameter vẫn nên được dùng để giữ cấu trúc SQL an toàn. Nếu generic plan thực sự gây regression, đánh giá `plan_cache_mode` ở scope hẹp, query variants được khai báo trước hoặc index phù hợp, thay vì nối pattern người dùng trực tiếp vào SQL text.

### 26.5. ANALYZE không là thần dược

```sql
ANALYZE text_search_lab.documents;
```

cập nhật thống kê, nhưng không tạo trigrams, không thay đổi phép toán và không biến `LIKE '%abc%'` thành B-tree prefix query.

## 27. SQL injection và pattern injection là hai vấn đề khác

Giả sử người dùng nhập chuỗi:

```text
50%_off
```

Ứng dụng muốn tìm **literal** `50%_off` trong title.

### 27.1. Bind parameter chỉ bảo vệ cú pháp SQL

Ví dụ tốt:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE $1 ESCAPE '!';
```

Nếu client bind `%50%_off%` mà **không escape wildcard**, người dùng đã vô tình/đúng chủ ý tạo một mẫu rộng hơn văn bản literal.

Không phải SQL injection, nhưng có thể là **pattern injection** hoặc sai semantics tìm kiếm.

### 27.2. Escape thứ tự đúng

Khi chọn `!` làm escape:

1. Đổi `!` thành `!!`.
2. Đổi `%` thành `!%`.
3. Đổi `_` thành `!_`.
4. Sau đó chỉ thêm `%` do ứng dụng chủ động muốn dùng để tìm contains.

### 27.3. Ví dụ Java

```java
static String escapeLikeLiteral(String input) {
    return input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
```

Dùng:

```java
String literal = escapeLikeLiteral(userText);
String pattern = "%" + literal + "%";

try (var ps = connection.prepareStatement(
        "SELECT document_id, title " +
        "FROM text_search_lab.documents " +
        "WHERE title LIKE ? ESCAPE '!' " +
        "ORDER BY document_id LIMIT 100")) {
    ps.setString(1, pattern);
    try (var rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("document_id")
                + ": " + rs.getString("title"));
        }
    }
}
```

Cách này:

- Giữ SQL syntax tách biệt khỏi input.
- Giải quyết wildcard escaping theo semantics literal substring.
- Dùng LIMIT nhằm giới hạn số rows trả về.
- Không phải cơ chế giới hạn CPU tuyệt đối nếu pattern quá mơ hồ hoặc index không giúp được.

### 27.4. Prefix search trong Java

Nếu sản phẩm muốn tìm “bắt đầu bằng input literal”:

```java
String pattern = escapeLikeLiteral(userText) + "%";
```

Không thêm dấu `%` phía trước. Một thay đổi nhỏ này có thể quyết định khả năng tận dụng B-tree prefix index.

### 27.5. Nếu muốn hỗ trợ wildcard do người dùng nhập?

Khi thiết kế một search syntax cho phép người dùng dùng `%`/`_` có chủ đích, hãy nói rõ trong UI và kiểm soát:

- Giới hạn độ dài pattern.
- Số lượng wildcard.
- Các pattern quá rộng.
- Timeouts/quota.
- Kế hoạch index.
- Rate limiting và pagination.

Không trộn lẫn “tìm văn bản literal” với “người dùng được viết query pattern” mà không xác định contract.

## 28. Regex từ người dùng: an toàn SQL chưa đủ an toàn hiệu năng

Ứng dụng có thể cho người dùng nhập regex:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ~* $1;
```

Bind parameter bảo vệ khỏi SQL injection, nhưng regex vẫn có thể:

- Quá dài.
- Quá rộng, match mọi row.
- Chứa tổ hợp phức tạp tốn CPU/memory.
- Không cung cấp literal trigrams để index.
- Tạo độ trễ lớn khi phải xét nhiều body texts.
- Bị lạm dụng nếu API không có quota.

### 28.1. Không nhận regex tự do nếu UX chỉ cần contains

Nếu người dùng chỉ muốn tìm từ khóa, dùng LIKE với escaped literal + trigram index hoặc FTS, không tự cho họ toàn bộ regex language.

### 28.2. Statement timeout

Trong transaction thử nghiệm:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

SELECT COUNT(*)
FROM text_search_lab.documents
WHERE title ~* '^(PostgreSQL|Java).*';

ROLLBACK;
```

`statement_timeout` hạn chế thời gian thực thi statement trên server. Đây là **hàng rào vận hành**, không thay thế thiết kế query/index/authorization.

### 28.3. Giới hạn và kiểm soát đầu vào

Một API hỗ trợ regex tự do nên có:

- Xác thực/phân quyền.
- Giới hạn pattern length.
- Policy những constructs được phép.
- Giới hạn dữ liệu/domain search.
- Query timeout.
- Rate limit/concurrency limit.
- Kết quả tối đa và pagination.
- Logging/observability có che dữ liệu nhạy cảm.

Regex engine có thể tiêu thụ thời gian và memory đáng kể. Không tin một chỉ mục sẽ chặn mọi pattern nguy hiểm.

### 28.4. Không tự validate regex bằng cách execute trên dữ liệu thật

Nếu muốn báo lỗi syntax cho regex của người dùng, cần validation có kiểm soát; đừng để bước validate quét toàn bộ bảng vì query vô tình không giới hạn.

### 28.5. Regex lỗi syntax

Một pattern sai có thể làm PostgreSQL báo lỗi regex. Ứng dụng cần xử lý và trả thông báo phù hợp, không để lỗi thô/stack trace gây lộ chi tiết hệ thống.

## 29. Chọn lọc theo category và ngày trước khi tìm văn bản

Một search endpoint có thể có các filter khác:

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE category = 'advanced'
  AND archived = false
  AND created_at >= timestamptz '2025-02-01 00:00:00+00'
  AND title ILIKE '%PostgreSQL%'
ORDER BY created_at DESC
LIMIT 50;
```

### 29.1. Giảm phạm vi candidate rows

Predicate category, archived và thời gian có thể giảm số rows cần kiểm tra pattern, nếu planner tìm được một kế hoạch tốt.

### 29.2. Không tự cho rằng SQL WHERE chạy theo thứ tự viết

SQL declarative; optimizer có quyền thay đổi cách đánh giá và access path trong giới hạn semantics. Viết `category` trước `ILIKE` **không bảo đảm** database luôn lọc category trước rồi mới chạy pattern.

### 29.3. Index tổ hợp hay hai index riêng?

Có thể cân nhắc:

- B-tree trên `(category, created_at)`.
- Partial index cho `archived = false` khi phần dữ liệu archived lớn.
- GIN trigram trên `title`.
- Kết hợp bitmap indexes trong các tình huống planner hỗ trợ.
- Một query variant có selective prefix.

Không có một index kết hợp B-tree+trigram thần kỳ hỗ trợ mọi predicate và mọi ORDER BY. Đo từng phương án với các patterns thực tế.

### 29.4. LIMIT và ORDER BY

`LIMIT 50` giúp hạn chế kết quả, nhưng nếu planner phải kiểm tra rất nhiều rows hoặc sort candidates để tìm 50 hàng mới nhất, query vẫn có thể đắt.

Một access path phù hợp ORDER BY có thể tránh Sort, nhưng có thể phải kiểm tra nhiều titles trước khi đủ 50 matches.

### 29.5. Keyset pagination

Với trang sâu, `OFFSET 100000` có thể phải xử lý rất nhiều rows trước khi trả trang tiếp theo. Cân nhắc keyset pagination theo `(created_at, document_id)` khi order key ổn định và index/phân trang được thiết kế phù hợp.

## 30. Dùng partial index khi workload rõ ràng

Nếu phần lớn truy vấn chỉ xem tài liệu chưa archived:

```sql
CREATE INDEX documents_active_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops)
WHERE archived = false;
```

Trigram index một phần có thể nhỏ hơn full index nếu dữ liệu archived chiếm phần lớn.

### 30.1. Dataset lab archived chỉ khoảng 5%

Trong bộ dữ liệu mẫu, `archived = true` xuất hiện khoảng 1/19 hàng. Partial index cho active vẫn gần bằng full index, nên **chưa chắc mang lại lợi ích đáng kể**.

Không tạo partial index chỉ vì syntax đẹp.

### 30.2. Generic prepared plan và partial predicate

Nếu query là:

```sql
WHERE archived = $1
  AND title ILIKE $2
```

generic plan không thể giả định `$1 = false` trong mọi lần chạy để dùng partial index có predicate `archived = false` theo cách an toàn.

Nếu endpoint nghiệp vụ **luôn chỉ tìm active documents**, có thể viết một query variant:

```sql
WHERE archived = false
  AND title ILIKE $1
```

vẫn bind text input, nhưng predicate archived là hằng rõ ràng để planner cân nhắc partial index.

### 30.3. Partial index không thay thế authorization

Nếu một document cần kiểm soát quyền theo owner/tenant, index archived không phải cơ chế bảo mật. Query vẫn phải bảo đảm chính sách truy cập.

## 31. Đo thời gian, buffers và chi phí index

### 31.1. Đo baseline trước khi tạo index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%PostgreSQL%';
```

### 31.2. Tạo trigram index và đo lại

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

Nếu đã tạo index trong phần trước, **không chạy lại CREATE INDEX cùng tên**. Trong lab này, mỗi DDL ví dụ chỉ nên tạo một lần.

```sql
ANALYZE text_search_lab.documents;

EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM text_search_lab.documents
WHERE title ILIKE '%PostgreSQL%';
```

### 31.3. Không kết luận từ một lượt chạy

Lượt sau có thể nhanh hơn vì cache nóng, không hoàn toàn do index. Hãy chạy nhiều lượt trong điều kiện tải tương đương và ghi rõ:

- PostgreSQL version/config.
- Dung lượng bảng/index.
- Query/pattern.
- Estimated và actual rows.
- Shared buffers hit/read.
- Planning Time/Execution Time.
- Cache, concurrency, máy.
- Chi phí INSERT/UPDATE sau khi thêm index.

### 31.4. So sánh index storage

```sql
SELECT
    indexname,
    pg_size_pretty(
        pg_relation_size(
            (quote_ident(schemaname) || '.'
             || quote_ident(indexname))::regclass
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'text_search_lab'
  AND tablename = 'documents'
ORDER BY indexname;
```

Các chỉ mục được tạo trong lab phục vụ so sánh, không có nghĩa production nên giữ tất cả.

### 31.5. Cân bằng read và write

GIN trigram index trên body có thể giúp tìm contains nhanh hơn nhưng khiến write workload nặng hơn. Cần đo cả:

- INSERT throughput.
- UPDATE body/title.
- WAL.
- VACUUM/index maintenance.
- Disk.
- Read latency ở phân vị p95/p99.

Tối ưu một query không được tự động xem là tối ưu cả hệ thống.

## 32. Những lỗi hiệu năng khó thấy

### 32.1. Query dùng hàm trên cột nhưng index không tương ứng

```sql
WHERE lower(title) LIKE 'postgresql%'
```

không tự tận dụng index trên `title` như index đúng expression `lower(title)`.

### 32.2. Pattern bắt đầu bằng percent

```sql
WHERE title ILIKE '%postgresql%'
```

không phải B-tree prefix search. Xem trigram index hoặc đổi UX sang starts-with nếu nghiệp vụ cho phép.

### 32.3. Pattern rất ngắn

```sql
WHERE title ILIKE '%a%'
```

có thể ít hữu ích với trigram index và match rất nhiều rows.

### 32.4. Query không giới hạn kết quả

```sql
SELECT *
FROM text_search_lab.documents
WHERE body ILIKE '%database%';
```

có thể trả hàng chục nghìn rows cùng body dài qua network.

### 32.5. Regex có nhiều alternatives không chọn lọc

```sql
WHERE title ~* '(a|b|c)'
```

có thể match rất nhiều rows và không có literal trigrams đủ tốt.

### 32.6. Dynamic optional OR

```sql
WHERE ($1 IS NULL OR title ILIKE $1)
```

generic plan phải phục vụ cả trạng thái NULL (không lọc) và pattern có thể rất selective. Tách query variants có thể phù hợp hơn.

### 32.7. Client tự chạy nhiều truy vấn mỗi ký tự

Autocomplete gửi request cho mỗi phím bấm, không debounce/rate limit, có thể tạo nhiều expensive ILIKE/regex scans đồng thời.

### 32.8. Dữ liệu không chuẩn hóa chữ có dấu

Người dùng gõ `cafe` nhưng dữ liệu lưu `Café`; tăng index không sửa sự khác biệt semantics.

### 32.9. Phụ thuộc một lần EXPLAIN với pattern dễ

Test `'%PostgreSQL%'` dài và ít gặp không đại diện cho `'%a%'`, `'%%'` hoặc input rỗng.

### 32.10. Xem `cost` như thời gian thực

Planner cost không phải milliseconds; luôn đối chiếu `EXPLAIN ANALYZE` và telemetry ứng dụng.

## 33. Bài tập thực hành và lời giải

Các bài tập dùng bảng `text_search_lab.documents` đã tạo. Những query DDL/index chỉ chạy một lần trong lab; các kết quả plan là quan sát thực tế, không có đáp án node cố định.

### Bài 1. LIKE dùng những wildcard nào?

**Đáp án:** `%` khớp 0 hoặc nhiều ký tự; `_` khớp đúng một ký tự.

### Bài 2. Tìm title bắt đầu bằng PostgreSQL

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE 'PostgreSQL%';
```

**Đáp án:** mẫu prefix; có thể tận dụng B-tree phù hợp khi cost/selectivity tốt.

### Bài 3. Tìm title kết thúc bằng chữ guide

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%guide';
```

**Đáp án:** mẫu suffix; leading wildcard cản B-tree prefix range.

### Bài 4. Tìm từ “indexing” ở giữa

```sql
SELECT document_id, title
FROM text_search_lab.documents
WHERE title LIKE '%indexing%';
```

**Đáp án:** contains pattern, `pg_trgm` thường là phương án index đáng xem xét.

### Bài 5. ILIKE khác LIKE thế nào?

**Đáp án:** ILIKE không phân biệt hoa/thường theo locale/collation, còn LIKE thông thường phân biệt case trong các collation deterministic phổ biến.

### Bài 6. ILIKE có tự tìm không dấu không?

**Đáp án:** không có bảo đảm. Case folding và accent normalization là hai nhu cầu khác nhau.

### Bài 7. Vì sao LIKE `'a_c'` không chỉ match underscore?

**Đáp án:** `_` là một wildcard đại diện một ký tự bất kỳ.

### Bài 8. Escape underscore literal

```sql
SELECT 'doc_000001' LIKE 'doc!_000%' ESCAPE '!';
```

**Đáp án:** true; `!_` nghĩa là dấu underscore literal.

### Bài 9. Escape dấu % literal

```sql
SELECT '50% off' LIKE '50!%%' ESCAPE '!';
```

**Đáp án:** true; `!%` là percent literal, `%` cuối vẫn là wildcard.

### Bài 10. Escape chính dấu !

```sql
SELECT 'hello!world' LIKE 'hello!!world' ESCAPE '!';
```

**Đáp án:** true.

### Bài 11. NULL LIKE '%' bằng true hay false?

**Đáp án:** NULL. Trong WHERE, UNKNOWN không được giữ như TRUE.

### Bài 12. `NOT LIKE` có bao gồm title NULL?

**Đáp án:** không tự bao gồm; phải thêm `OR title IS NULL` nếu nghiệp vụ muốn.

### Bài 13. Regex operator `~` khác LIKE thế nào?

**Đáp án:** `~` dùng POSIX regex và có thể match substring; LIKE dùng wildcard SQL và so khớp toàn chuỗi.

### Bài 14. Regex case-insensitive operator nào?

**Đáp án:** `~*`.

### Bài 15. Regex phủ định case-insensitive?

**Đáp án:** `!~*`.

### Bài 16. Regex cho mã AB-1234

```sql
SELECT 'AB-1234' ~ '^[A-Z]{2}-[0-9]{4}$';
```

**Đáp án:** true, nếu chuỗi có đúng hai chữ A-Z, dấu gạch ngang và bốn chữ số.

### Bài 17. Tại sao `^` và `$` quan trọng?

**Đáp án:** chúng neo đầu/cuối pattern; không có neo, regex có thể chỉ match một đoạn nhỏ của chuỗi.

### Bài 18. Regex của LIKE `'%SQL%'` là gì?

**Đáp án gợi ý:** `~ 'SQL'` để tìm substring, với lưu ý case-sensitive; `~* 'sql'` nếu muốn không phân biệt hoa/thường.

### Bài 19. Dấu chấm trong regex có nghĩa gì?

**Đáp án:** `.` match một ký tự bất kỳ theo semantics regex; muốn dấu chấm literal dùng `\.`.

### Bài 20. Alternation viết ra sao?

```sql
SELECT 'Java indexing' ~ '^(Java|PostgreSQL)';
```

**Đáp án:** true. `|` là OR trong regex.

### Bài 21. `SIMILAR TO` có match substring như `~` không?

**Đáp án:** không. SIMILAR TO yêu cầu match toàn chuỗi theo semantics pattern kiểu SQL.

### Bài 22. `regexp_match` trả gì khi không khớp?

**Đáp án:** thường NULL; khi khớp trả text array của captured groups hoặc toàn match.

### Bài 23. `regexp_matches` có `g` khác gì?

**Đáp án:** trả một set of rows cho nhiều matches; no-match có thể không phát dòng, khác với một scalar NULL.

### Bài 24. Thay mọi nhóm chữ số

```sql
SELECT regexp_replace(
    'A12 B345',
    '[0-9]+',
    '#',
    'g'
);
```

**Đáp án:** `A# B#`.

### Bài 25. Tách bằng dấu phẩy hoặc chấm phẩy

```sql
SELECT regexp_split_to_array(
    'a,b;c',
    '[,;]'
);
```

**Đáp án:** một text array chứa a, b, c.

### Bài 26. Vì sao `LIKE 'prefix%'` có thể dùng B-tree?

**Đáp án:** prefix xác định một phạm vi khóa trong B-tree ordering thích hợp, giúp thu hẹp candidate keys.

### Bài 27. Vì sao `LIKE '%term%'` thường không được B-tree hỗ trợ tốt?

**Đáp án:** không biết chuỗi bắt đầu bằng gì, nên không có một contiguous prefix key range thuận lợi.

### Bài 28. Khi nào `text_pattern_ops` hữu ích?

**Đáp án:** khi cần B-tree prefix LIKE trong những collations mà operator class mặc định không cho access path mong muốn.

### Bài 29. `text_pattern_ops` có làm ILIKE substring nhanh không?

**Đáp án:** không tự làm vậy; hãy xem lower(expression) index cho prefix hoặc trigram cho substring/ILIKE.

### Bài 30. Tạo expression index prefix case-insensitive

```sql
CREATE INDEX documents_lower_title_prefix_idx
ON text_search_lab.documents
    ((lower(title)) text_pattern_ops);
```

**Đáp án:** index hỗ trợ expression `lower(title)` trong điều kiện phù hợp; nếu đã tạo trong lab, không tạo lại.

### Bài 31. Vì sao index trên title không tương đương index trên lower(title)?

**Đáp án:** một cái lưu cột gốc, một cái lưu giá trị expression; planner cần access path phù hợp với query expression.

### Bài 32. Extension nào hỗ trợ trigram indexing?

**Đáp án:** `pg_trgm`.

### Bài 33. GIN trigram index tạo như thế nào?

```sql
CREATE INDEX documents_title_trgm_idx
ON text_search_lab.documents
USING gin (title gin_trgm_ops);
```

**Đáp án:** dùng `gin_trgm_ops` sau khi extension có sẵn; không tạo trùng nếu đã có.

### Bài 34. GIN trigram có tăng tốc mọi pattern ngắn không?

**Đáp án:** không. Mẫu thiếu literal trigrams hoặc rất phổ biến có thể không hưởng lợi.

### Bài 35. Vì sao trigram index vẫn cần Recheck Cond?

**Đáp án:** index xác định candidates từ trigrams; executor phải xác nhận chúng match toàn bộ LIKE/ILIKE/regex predicate.

### Bài 36. GIN và GiST trigram có giống nhau hoàn toàn?

**Đáp án:** không. Cấu trúc và đặc tính recheck, write cost, similarity/distance-order khác nhau; đo theo workload.

### Bài 37. Khi nào dùng Full Text Search thay vì LIKE?

**Đáp án:** khi cần tìm theo từ/lexeme, nhiều từ, logic tìm kiếm và ranking; không phải khi cần substring bất kỳ ở giữa từ.

### Bài 38. Vì sao `ILIKE '%pg_trgm%'` không đảm bảo tìm đúng underscore?

**Đáp án:** `_` là LIKE wildcard; dùng `ILIKE '%pg!_trgm%' ESCAPE '!'` để tìm literal underscore.

### Bài 39. Bind parameter có tự escape % và _ không?

**Đáp án:** không. Bind chống SQL injection, còn LIKE wildcard semantics vẫn hoạt động; ứng dụng phải escape literal search text khi cần.

### Bài 40. Cách escape LIKE literal trong Java?

**Đáp án:** lần lượt thay `! -> !!`, `% -> !%`, `_ -> !_`, rồi thêm wildcard do ứng dụng chủ động yêu cầu và bind.

### Bài 41. Người dùng nhập regex `.*` có nguy cơ gì?

**Đáp án:** pattern quá rộng, có thể match rất nhiều rows và tốn CPU/I/O; cần giới hạn input, timeout, quota và query scope.

### Bài 42. `statement_timeout` có làm query luôn nhanh không?

**Đáp án:** không. Nó có thể hủy query vượt giới hạn, nhưng không làm access path tốt hơn.

### Bài 43. Vì sao LIMIT 20 chưa chắc làm substring search rẻ?

**Đáp án:** executor có thể phải kiểm tra nhiều rows hoặc sort trước khi tìm đủ 20 kết quả đúng thứ tự.

### Bài 44. `cost=1000` có phải 1000 ms không?

**Đáp án:** không. Đây là đơn vị chi phí của planner.

### Bài 45. Thấy Seq Scan trên bảng nhỏ có phải lỗi?

**Đáp án:** không. Đọc bảng nhỏ tuần tự có thể rẻ hơn index lookup, ngay khi index tồn tại.

### Bài 46. Có nên tăng số index vô hạn?

**Đáp án:** không. Mỗi index tăng dung lượng, WAL và chi phí ghi/bảo trì. Chỉ tạo khi có workload chứng minh lợi ích.

### Bài 47. Test regex case-insensitive có dùng `ILIKE` thay được mọi regex không?

**Đáp án:** không. ILIKE chỉ có wildcard %/_; nó không hỗ trợ đầy đủ character class, alternation và quantifier regex.

### Bài 48. Trình bày một quy trình benchmark search

**Đáp án gợi ý:** đo baseline; tạo đúng index; ANALYZE; đo lại EXPLAIN ANALYZE BUFFERS với prefix/contains/ILIKE/regex ngắn/dài; đo nhiều lượt và concurrency; so planning/execution time, buffers, rows, write impact, storage và p95/p99.

## 34. Bảng quyết định tìm kiếm trong thực tế

| Yêu cầu | Phương án đầu tiên | Khi dữ liệu lớn |
| --- | --- | --- |
| Exact title | `title = ?` | B-tree index phù hợp |
| Starts with, phân biệt hoa/thường | `title LIKE 'abc%'` | B-tree `text_pattern_ops` trong collation phù hợp |
| Starts with, không phân biệt hoa/thường | `lower(title) LIKE 'abc%'` | Expression B-tree `lower(title) text_pattern_ops` |
| Contains literal | `title LIKE '%abc%'` | `pg_trgm` GIN/GiST nếu pattern đủ chọn lọc |
| Contains case-insensitive | `title ILIKE '%abc%'` | Trigram index và đo selectivity |
| Suffix | `title LIKE '%abc'` | Trigram hoặc index expression đảo chuỗi khi justified |
| Pattern ký tự phức tạp | `title ~ regex` | Trigram nếu trích xuất được literal trigrams |
| Fuzzy/typo | Trigram similarity | GIN/GiST theo operator, ranking UX |
| Tìm nhiều từ theo lexeme | Full Text Search | GIN tsvector + config theo ngôn ngữ |
| Tìm không dấu | Normalization/search design | Index phù hợp với normalized expression và collation |
| Input tùy ý từ user | Bind + escaping + policy | Timeout, rate limit, quota, index |
| Autocomplete | Prefix và LIMIT | Prefix index, debounce, keyset |
| Truy vấn hiếm, bảng nhỏ | LIKE/ILIKE đơn giản | Seq Scan có thể đủ |

Không có một lựa chọn tốt nhất cho mọi bài toán. Hãy bắt đầu từ **ngữ nghĩa sản phẩm**, sau đó thiết kế index và kiểm tra bằng dữ liệu.

## 35. Checklist trước khi đưa tính năng search vào production

| Câu hỏi | Cần xác minh |
| --- | --- |
| Người dùng muốn exact, prefix hay contains? | Chọn đúng operator/wildcards |
| Input %/_ là literal hay wildcard? | Escape LIKE tương ứng |
| Cần case-insensitive? | ILIKE/normalization |
| Cần accent-insensitive? | Test Unicode/collation/normalization |
| Cần regex hay chỉ substring? | Không mở regex miễn phí khi không cần |
| Regex user có thể quá phức tạp? | Limit length/constructs/time |
| Có input rỗng hay chỉ 1-2 ký tự? | Tránh scan không chọn lọc |
| Có index cho prefix? | B-tree pattern_ops / expression index |
| Có index cho contains? | pg_trgm nếu hữu ích |
| Pattern có đủ literal trigrams? | Xem EXPLAIN với mẫu thật |
| Body index có quá lớn? | Đo size/write cost |
| Có FTS phù hợp hơn? | Lexeme, ranking, language config |
| PostgreSQL version/collation? | Kiểm tra semantics và khả năng index |
| Query dùng prepared params? | So custom/generic khi patterns lệch |
| Có ORDER BY / LIMIT? | Đọc toàn plan, không chỉ Filter |
| Có predicate status/category? | Index strategy và partial indexes |
| Có tenant authorization? | Không để search vượt phạm vi quyền |
| Có pagination? | Giới hạn rows/network |
| Có debouncing/rate limiting? | Tránh mỗi phím là một full scan |
| Có timeout? | statement_timeout phù hợp |
| Có EXPLAIN ANALYZE BUFFERS? | Đo thật scan/index/recheck |
| Có benchmark pattern ngắn/dài? | Tránh lấy một case tốt làm đại diện |
| Có đo p95/p99 và concurrency? | Bảo vệ production |
| Có log pattern nhạy cảm? | Redact/aggregate metadata |
| Có đo write cost sau index? | WAL/INSERT/UPDATE/VACUUM |
| Có kế hoạch ANALYZE? | Stats mới cho planner |
| Có phương án rollback index? | Phối hợp migration |
| Có cảnh báo query chậm? | Observability |
| Có test chính tả/Unicode? | Semantics đúng với người dùng |

## 36. Tổng kết

### LIKE

- `%` khớp không hoặc nhiều ký tự.
- `_` khớp đúng một ký tự.
- LIKE so khớp **toàn chuỗi** theo pattern.
- `LIKE 'prefix%'` thường có cơ hội dùng B-tree index phù hợp.
- `LIKE '%term%'` thường không có B-tree prefix range thuận lợi.

### ILIKE

- Wildcard giống LIKE nhưng không phân biệt hoa/thường theo locale/collation liên quan.
- Không tự có nghĩa tìm không dấu hoặc normalize mọi Unicode.
- `lower(title)` + expression B-tree có thể hỗ trợ case-insensitive prefix.
- Trigram index có thể hỗ trợ case-insensitive contains.

### POSIX regex

- `~` phân biệt case, `~*` không phân biệt case.
- Regex operator có thể match một **substring**, nên dùng `^...$` khi cần so khớp toàn chuỗi.
- Có character classes, quantifiers, grouping, alternation.
- Regex từ người dùng phải được giới hạn để tránh pattern quá rộng/phức tạp.

### Hiệu năng

- B-tree tốt với **equality/prefix** khi collation/operator class phù hợp.
- `text_pattern_ops` và `lower(...)` expression index giải quyết nhiều bài toán prefix.
- `pg_trgm` với GIN/GiST hỗ trợ nhiều mẫu **contains/ILIKE/regex**, nhưng cần literal trigrams đủ chọn lọc và có chi phí index/recheck.
- Full Text Search phù hợp khi cần semantics **lexeme/từ khóa**, không phải substring tùy ý.
- `EXPLAIN (ANALYZE, BUFFERS)` giúp phân biệt Seq Scan, Index Scan, Bitmap Scan và đo rows/buffers/timing.
- Query shape, pattern length, case/locale, dữ liệu và ORDER BY/LIMIT đều ảnh hưởng plan.

### An toàn

- Dùng `PreparedStatement` và bind parameters để tránh SQL injection.
- Nếu tìm **literal text**, escape `%`, `_` và escape character trước khi thêm wildcard.
- Bind parameter **không** tự ngăn pattern injection hoặc regex quá đắt.
- Đặt giới hạn input, timeouts, pagination và quota cho search endpoint.
- Đừng tạo mọi index có thể có; đo lợi ích đọc, chi phí ghi và disk.

**Quy tắc cuối cùng:** trước khi tối ưu một điều kiện `LIKE`, `ILIKE` hay regex, hãy trả lời bốn câu hỏi: **(1) mẫu này cần match chính xác điều gì, (2) chuỗi literal chọn lọc đến đâu, (3) index nào thực sự có thể giới hạn candidates, và (4) EXPLAIN cho thấy PostgreSQL đã đọc bao nhiêu rows/blocks?**. Khi trả lời được cả bốn, bạn mới có cơ sở để quyết định dùng B-tree, trigram, Full Text Search hay chỉnh lại thiết kế tính năng tìm kiếm.
