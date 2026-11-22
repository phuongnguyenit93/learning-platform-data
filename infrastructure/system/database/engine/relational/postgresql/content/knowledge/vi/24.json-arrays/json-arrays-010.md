# Toán tử mảng, ANY, ALL và tìm phần giao trong PostgreSQL

Trong cơ sở dữ liệu quan hệ, chúng ta thường biểu diễn quan hệ nhiều-nhiều bằng bảng liên kết. Tuy nhiên, PostgreSQL còn có **kiểu mảng** (*array*) cho phép một cột lưu nhiều phần tử cùng kiểu, ví dụ `TEXT[]` chứa nhãn, `INTEGER[]` chứa các điểm số hoặc `UUID[]` chứa một danh sách tham chiếu.

Khi làm việc với mảng, câu hỏi thường không còn đơn giản là `column = value`. Ứng dụng có thể cần:

- “Tài liệu có chứa **cả hai** nhãn `sql` và `postgresql` không?”
- “Tài liệu có **ít nhất một** nhãn thuộc nhóm `gin`, `api` không?”
- “Một giá trị có nằm trong mảng hay không?”
- “Điểm số `90` có lớn hơn **mọi** ngưỡng trong mảng không?”
- “Hai mảng có những phần tử **giao nhau** nào?”
- “Nếu có phần tử `NULL`, mảng rỗng hoặc mảng `NULL` thì câu điều kiện trả `TRUE`, `FALSE` hay `NULL`?”
- “Tìm phần giao dưới dạng **tập hợp phân biệt** hay phải giữ **số lần xuất hiện** của phần tử?”

PostgreSQL cung cấp các toán tử mảng như `@>`, `<@`, `&&`, các biểu thức lượng hóa `ANY`/`ALL`, các hàm như `unnest`, `array_position`, `array_agg` và phép tập hợp `INTERSECT`. Những công cụ này rất mạnh nhưng **không tương đương nhau trong mọi trường hợp**.

Ví dụ:

```sql
SELECT
    ARRAY['sql', 'postgresql']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS contains_sql,
    ARRAY['sql', 'postgresql']::TEXT[]
        && ARRAY['python', 'sql']::TEXT[] AS overlaps,
    'sql' = ANY(ARRAY['sql', 'postgresql']::TEXT[])
        AS scalar_matches,
    10 > ALL(ARRAY[2, 3, 5]::INTEGER[])
        AS greater_than_every_threshold;
```

Cả bốn biểu thức trên có thể trả `TRUE`, nhưng chúng kiểm tra **bốn quan hệ logic khác nhau**. Việc hiểu đúng quan hệ này quyết định tính đúng của truy vấn, khả năng tận dụng chỉ mục GIN và cách thiết kế dữ liệu.

Bài học thuộc chương **JSON và mảng** của module **Database Engine Relational PostgreSQL**, tập trung vào cách dùng mảng SQL PostgreSQL trong truy vấn, các trường hợp biên của `ANY`/`ALL`, tìm phần giao và kỹ thuật viết câu SQL an toàn, rõ nghĩa, có thể tối ưu.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Khai báo, khởi tạo, đọc và phân biệt mảng PostgreSQL với chuỗi JSON hoặc chuỗi text ngăn bằng dấu phẩy.
2. Sử dụng các toán tử mảng `@>`, `<@`, `&&` và `=` đúng theo ngữ nghĩa.
3. Phân biệt mảng **có chứa toàn bộ** một tập phần tử với mảng **có giao không rỗng**.
4. Giải thích sự khác nhau giữa biểu thức `value = ANY(array)` và `array_column @> ARRAY[value]`, đặc biệt về khả năng dùng index.
5. Hiểu `ANY`/`SOME` và `ALL` với các toán tử so sánh như `=`, `<>`, `<`, `>`.
6. Dự đoán kết quả `TRUE`, `FALSE`, `NULL` khi mảng rỗng, mảng NULL, phần tử NULL hoặc toán hạng NULL.
7. Hiểu `value <> ALL(array)` và `NOT (value = ANY(array))`, đồng thời tránh bẫy `NOT IN` với NULL.
8. Tìm **giao tập hợp** của hai mảng bằng `unnest` và `INTERSECT`, hoặc bằng lọc `= ANY(...)`.
9. Phân biệt `INTERSECT` với `INTERSECT ALL` và tránh hiểu nhầm `@>` là phép so sánh số lượng bản sao.
10. Giữ thứ tự khi tháo mảng bằng `WITH ORDINALITY` và xây lại mảng bằng `array_agg(... ORDER BY ...)`.
11. Làm việc với `cardinality`, `array_length`, `array_position`, `array_positions`, `array_append`, `array_remove` và các hàm liên quan.
12. Biết khi nào cần chỉ mục GIN `array_ops`, cách đọc `EXPLAIN` và giới hạn của index đối với `ANY`.
13. Lựa chọn giữa mảng và **bảng quan hệ con** khi cần khóa ngoại, uniqueness, truy vấn nhiều chiều hoặc thay đổi phần tử thường xuyên.
14. Dùng bind parameters trong Java/JDBC khi truyền một mảng vào truy vấn.
15. Viết và kiểm thử các truy vấn tìm phần giao, lọc theo nhãn, loại trừ nhãn, thống kê số phần tử và cập nhật mảng không gây ghi đè dữ liệu cũ.

> **Lưu ý:** Các câu `DROP TABLE`, `INSERT` và `UPDATE` trong lab chỉ dành cho cơ sở dữ liệu thử nghiệm được phép thay đổi. Nội dung bài giải thích chức năng PostgreSQL; không mặc định các truy vấn có `EXPLAIN` sẽ chọn giống nhau trên mọi phiên bản hoặc kích thước dữ liệu.

---

## 2. Kiểu mảng trong PostgreSQL

Một cột mảng có thể chứa nhiều phần tử cùng kiểu:

```sql
CREATE TABLE example_arrays (
    item_id BIGINT PRIMARY KEY,
    tags TEXT[],
    scores INTEGER[],
    prices NUMERIC(12,2)[],
    flags BOOLEAN[]
);
```

Hậu tố `[]` biểu diễn **kiểu mảng**:

| Kiểu | Ví dụ phần tử | Mục đích thường gặp |
| --- | --- | --- |
| `TEXT[]` | `'sql'`, `'api'` | Nhãn, nhóm từ khóa |
| `INTEGER[]` | `10`, `20` | Các mã hoặc điểm số |
| `UUID[]` | UUID | Danh sách mã tham chiếu |
| `NUMERIC[]` | `12.50`, `100.00` | Bộ giá trị số chính xác |
| `BOOLEAN[]` | `TRUE`, `FALSE` | Bộ cờ điều kiện |
| `TIMESTAMPTZ[]` | Timestamp | Các mốc thời gian |

Các phần tử mảng thường cùng kiểu hoặc được PostgreSQL ép về một kiểu chung phù hợp. Không coi `TEXT[]` là “JSON array”; JSON/JSONB có cách biểu diễn và các toán tử riêng.

### 2.1. Tạo mảng bằng ARRAY[...]

```sql
SELECT
    ARRAY['sql', 'postgresql', 'array']::TEXT[] AS tags,
    ARRAY[10, 20, 30]::INTEGER[] AS scores,
    ARRAY[TRUE, FALSE, TRUE]::BOOLEAN[] AS flags;
```

Khi PostgreSQL suy luận được kiểu từ các phần tử, có thể bỏ cast. Tuy nhiên, cast rõ ràng giúp truy vấn giáo trình, tham số hóa và mảng rỗng dễ hiểu hơn.

### 2.2. Cú pháp literal có dấu ngoặc nhọn

PostgreSQL cũng chấp nhận array literal:

```sql
SELECT
    '{"sql","postgresql","array"}'::TEXT[] AS tags,
    '{10,20,30}'::INTEGER[] AS scores;
```

Dấu ngoặc nhọn ở đây thuộc **cú pháp giá trị mảng PostgreSQL**, không phải JSON object.

Trong câu SQL động, nên dùng bind parameters hoặc `ARRAY[...]` thay vì tự ghép một literal text có nhiều ký tự escape phức tạp.

### 2.3. Mảng rỗng khác NULL

```sql
SELECT
    ARRAY[]::TEXT[] AS empty_tags,
    NULL::TEXT[] AS unknown_tags,
    ARRAY[NULL::TEXT] AS one_null_element;
```

Ba giá trị này khác nhau:

- `ARRAY[]::TEXT[]`: mảng **đã biết rỗng**, có 0 phần tử.
- `NULL::TEXT[]`: giá trị **toàn bộ cột mảng là NULL**.
- `ARRAY[NULL::TEXT]`: mảng **có một phần tử, nhưng phần tử đó NULL**.

Đây là khác biệt cơ bản nhất khi học `ANY`, `ALL` và `unnest`.

### 2.4. Chỉ số phần tử

Mảng một chiều thông thường được truy cập từ vị trí 1:

```sql
SELECT
    (ARRAY['sql', 'api', 'db']::TEXT[])[1] AS first_tag,
    (ARRAY['sql', 'api', 'db']::TEXT[])[3] AS third_tag;
```

PostgreSQL cho phép mảng có lower bound khác 1 trong một số trường hợp; không nên coi chỉ số từ 1 là một bất biến của mọi mảng được lưu. Khi tháo mảng với `WITH ORDINALITY`, ordinality là số thứ tự được sinh từ 1, không nhất thiết bằng subscript gốc của mảng.

---

## 3. Bộ lab: tài liệu có tags và scores

Ta tạo một bảng nhỏ để mọi toán tử đều có trường hợp kiểm thử.

### 3.1. Tạo schema và bảng

> **Cảnh báo:** Lệnh `DROP TABLE` sẽ xóa bảng lab cùng tên. Chỉ chạy trên database dành riêng cho thực hành.

```sql
CREATE SCHEMA IF NOT EXISTS array_ops_lab;

DROP TABLE IF EXISTS array_ops_lab.documents;

CREATE TABLE array_ops_lab.documents (
    doc_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    tags TEXT[],
    scores INTEGER[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Tạm thời ta **cho phép cả tags=NULL và phần tử NULL** để giải thích đầy đủ ngữ nghĩa SQL ba giá trị. Trong ứng dụng thật, có thể chọn ràng buộc nghiêm ngặt hơn.

### 3.2. Nạp dữ liệu

```sql
INSERT INTO array_ops_lab.documents (
    doc_id, title, tags, scores
)
VALUES
    (
        1, 'PostgreSQL arrays',
        ARRAY['sql','postgresql','array']::TEXT[],
        ARRAY[10,20,30]::INTEGER[]
    ),
    (
        2, 'Java backend',
        ARRAY['java','api','backend']::TEXT[],
        ARRAY[8,6]::INTEGER[]
    ),
    (
        3, 'SQL and JSON',
        ARRAY['sql','json','search']::TEXT[],
        ARRAY[3,4,5]::INTEGER[]
    ),
    (
        4, 'Duplicate tags',
        ARRAY['sql','sql','etl']::TEXT[],
        ARRAY[7,7]::INTEGER[]
    ),
    (
        5, 'Empty arrays',
        ARRAY[]::TEXT[],
        ARRAY[]::INTEGER[]
    ),
    (
        6, 'Unknown arrays',
        NULL::TEXT[],
        NULL::INTEGER[]
    ),
    (
        7, 'Partially unknown tags',
        ARRAY['sql',NULL::TEXT,'qa'],
        ARRAY[NULL::INTEGER,5,10]
    ),
    (
        8, 'Only NULL elements',
        ARRAY[NULL::TEXT],
        ARRAY[NULL::INTEGER]
    ),
    (
        9, 'GIN search',
        ARRAY['postgresql','gin','search']::TEXT[],
        ARRAY[1,2,3]::INTEGER[]
    ),
    (
        10, 'PostgreSQL intersection',
        ARRAY['sql','postgresql','gin','array']::TEXT[],
        ARRAY[8,9]::INTEGER[]
    );

ANALYZE array_ops_lab.documents;
```

### 3.3. Kiểm tra dữ liệu

```sql
SELECT
    doc_id,
    title,
    tags,
    scores,
    cardinality(tags) AS tag_count
FROM array_ops_lab.documents
ORDER BY doc_id;
```

Một số mốc quan trọng:

| doc_id | tags | Ý nghĩa |
| ---: | --- | --- |
| 1 | `{sql,postgresql,array}` | Đủ cả SQL và PostgreSQL |
| 2 | `{java,api,backend}` | Không có SQL |
| 3 | `{sql,json,search}` | Có SQL, không có PostgreSQL |
| 4 | `{sql,sql,etl}` | Có phần tử trùng |
| 5 | `{}` | Mảng rỗng |
| 6 | `NULL` | Cả mảng NULL |
| 7 | `{sql,NULL,qa}` | Có SQL và một phần tử NULL |
| 8 | `{NULL}` | Chỉ có phần tử NULL |
| 9 | `{postgresql,gin,search}` | Có PostgreSQL và GIN |
| 10 | `{sql,postgresql,gin,array}` | Có SQL, PostgreSQL và GIN |

Các ví dụ dưới đây mặc định lab chưa bị UPDATE từ những phần thực hành khác.

---

## 4. Ba toán tử mảng quan trọng: @>, <@ và &&

Bảng sau là “từ điển” ngắn nhất để không nhầm ngữ nghĩa:

| Toán tử | Đọc là | Hỏi điều gì? |
| --- | --- | --- |
| `left @> right` | left chứa right | Tất cả phần tử yêu cầu từ right có trong left? |
| `left <@ right` | left nằm trong right | Tất cả phần tử của left có trong right? |
| `left && right` | hai mảng overlap | Có ít nhất một phần tử xuất hiện trong cả hai? |
| `left = right` | hai mảng bằng nhau | Giá trị mảng bằng nhau theo so sánh mảng? |
| `left <> right` | hai mảng khác nhau | Không bằng nhau theo so sánh mảng? |

Với mảng text/int một chiều gồm **các phần tử không NULL**, các mô hình này rất trực quan.

### 4.1. @> — mảng chứa tập phần tử yêu cầu

```sql
SELECT
    doc_id, title, tags
FROM array_ops_lab.documents
WHERE tags @> ARRAY['sql','postgresql']::TEXT[]
ORDER BY doc_id;
```

Kết quả mong đợi từ lab:

| doc_id | title |
| ---: | --- |
| 1 | PostgreSQL arrays |
| 10 | PostgreSQL intersection |

Dùng `@>` khi nghiệp vụ yêu cầu **AND trên tập nhãn**, tức tài liệu phải chứa cả hai nhãn.

### 4.2. @> với chỉ một phần tử

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags @> ARRAY['gin']::TEXT[]
ORDER BY doc_id;
```

Kết quả: doc 9 và 10.

Đây là dạng rất hữu ích khi cột tags có chỉ mục GIN: điều kiện là một toán tử mảng được operator class hỗ trợ.

### 4.3. && — tồn tại ít nhất một phần tử chung

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags && ARRAY['gin','api']::TEXT[]
ORDER BY doc_id;
```

Kết quả:

| doc_id | Vì sao khớp |
| ---: | --- |
| 2 | Có `api` |
| 9 | Có `gin` |
| 10 | Có `gin` |

`&&` diễn đạt **OR trên tập nhãn yêu cầu**: chỉ cần một phần tử chung.

### 4.4. <@ — mọi nhãn của hàng thuộc tập cho phép

```sql
SELECT doc_id, title, tags
FROM array_ops_lab.documents
WHERE tags <@ ARRAY[
    'sql','postgresql','array','gin','etl'
]::TEXT[]
ORDER BY doc_id;
```

Điều kiện này hỏi mọi phần tử của `tags` có nằm trong tập cho phép không; nó không hỏi “có ít nhất một nhãn được cho phép”. Với các hàng không có phần tử NULL, ví dụ doc 1, 4, 5 và 10 đáp ứng điều kiện theo nghĩa tập hợp.

### 4.5. Dễ nhầm nhất: @> và &&

```sql
SELECT
    ARRAY['sql','gin']::TEXT[]
        @> ARRAY['sql','api']::TEXT[] AS contains_all,
    ARRAY['sql','gin']::TEXT[]
        && ARRAY['sql','api']::TEXT[] AS overlaps_any;
```

Kết quả:

```text
contains_all = FALSE
overlaps_any = TRUE
```

Một nhãn chung đủ cho `&&`, nhưng không đủ cho `@>`.

---

## 5. Toán tử <@ cần cẩn thận với mảng rỗng

Về trực giác tập hợp, mọi phần tử của mảng rỗng đều nằm trong bất kỳ tập cho phép nào. Vì vậy:

```sql
SELECT
    ARRAY[]::TEXT[] <@ ARRAY['sql']::TEXT[] AS empty_is_subset,
    ARRAY[]::TEXT[] @> ARRAY[]::TEXT[] AS empty_contains_empty,
    ARRAY['sql']::TEXT[] @> ARRAY[]::TEXT[] AS every_array_contains_empty,
    ARRAY[]::TEXT[] && ARRAY['sql']::TEXT[] AS empty_overlaps;
```

Với các mảng không NULL trong ví dụ:

| Biểu thức | Kết quả |
| --- | --- |
| `{} <@ {'sql'}` | `TRUE` |
| `{} @> {}` | `TRUE` |
| `{'sql'} @> {}` | `TRUE` |
| `{} && {'sql'}` | `FALSE` |

Điều này có thể gây bất ngờ:

- Một danh sách nhãn trống **thỏa** điều kiện “mọi nhãn đều được cho phép”.
- Một danh sách nhãn trống **không thỏa** điều kiện “có giao với nhãn được yêu cầu”.
- Một mảng không NULL bất kỳ chứa mảng rỗng theo ý nghĩa containment.

Nếu nghiệp vụ yêu cầu “có **ít nhất một** nhãn và tất cả đều hợp lệ”, phải kiểm tra cả:

```sql
WHERE cardinality(tags) > 0
  AND tags <@ ARRAY['sql','postgresql','gin']::TEXT[]
```

Không dùng `<@` một mình để suy ra mảng không rỗng.

---

## 6. Duplicate: containment không đếm số bản sao

PostgreSQL array containment **không coi số lần lặp là một yêu cầu số lượng**.

```sql
SELECT
    ARRAY['sql']::TEXT[]
        @> ARRAY['sql','sql']::TEXT[] AS one_contains_two,
    ARRAY['sql','sql']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS two_contains_one,
    ARRAY['sql','sql']::TEXT[]
        = ARRAY['sql']::TEXT[] AS arrays_equal;
```

Kết quả:

| one_contains_two | two_contains_one | arrays_equal |
| --- | --- | --- |
| `TRUE` | `TRUE` | `FALSE` |

Như vậy:

- `@>` kiểm tra sự hiện diện của phần tử, không phải số bản sao.
- `=` so sánh giá trị mảng, trong đó số phần tử và thứ tự có ý nghĩa.
- Không dùng `@>` để kiểm tra “có ít nhất hai lần xuất hiện của nhãn sql”.

### 6.1. Thứ tự có quan trọng không?

Với mảng một chiều:

```sql
SELECT
    ARRAY['sql','gin']::TEXT[]
        = ARRAY['gin','sql']::TEXT[] AS same_array,
    ARRAY['sql','gin']::TEXT[]
        @> ARRAY['gin','sql']::TEXT[] AS contains_elements,
    ARRAY['gin','sql']::TEXT[]
        @> ARRAY['sql','gin']::TEXT[] AS reverse_contains;
```

`same_array` là `FALSE` vì thứ tự khác; hai phép contains đều `TRUE` vì tập phần tử trùng nhau.

**Kết luận:** Nếu ứng dụng coi tags như tập hợp, cần chuẩn hóa/deduplicate khi lưu hoặc viết truy vấn mang ngữ nghĩa tập hợp. Không coi mảng SQL mặc nhiên là một set với tính duy nhất và không quan tâm thứ tự.

### 6.2. Muốn đếm số lần xuất hiện thực sự

```sql
SELECT
    d.doc_id,
    COUNT(*) FILTER (WHERE x.tag = 'sql') AS sql_occurrences
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags) AS x(tag)
WHERE d.doc_id = 4
GROUP BY d.doc_id;
```

Doc 4 có hai phần tử `sql` nên `sql_occurrences=2`.

Không có ràng buộc mặc định cấm phần tử trùng trong kiểu `TEXT[]`.

---

## 7. ANY: so sánh một giá trị với từng phần tử trong mảng

Dạng phổ biến:

```sql
value operator ANY(array_expression)
```

PostgreSQL đánh giá phép so sánh giữa `value` và mỗi phần tử mảng, rồi kết hợp theo ý nghĩa **“có ít nhất một phép so sánh đúng”**.

Ví dụ:

```sql
SELECT
    7 = ANY(ARRAY[3,7,9]::INTEGER[]) AS contains_seven,
    7 > ANY(ARRAY[10,2,20]::INTEGER[]) AS greater_than_one,
    'sql' = ANY(ARRAY['java','sql','api']::TEXT[])
        AS string_member;
```

Tất cả đều là `TRUE`.

### 7.1. = ANY nghĩa là membership

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE 'sql' = ANY(tags)
ORDER BY doc_id;
```

Với lab, các hàng khớp rõ ràng là **1, 3, 4, 7, 10**.

`'sql' = ANY(tags)` hỏi phần tử scalar `'sql'` có bằng **ít nhất một** phần tử tags hay không.

### 7.2. Không phải lúc nào toán tử cũng là dấu bằng

```sql
SELECT
    9 > ANY(ARRAY[10,20,5]::INTEGER[]) AS greater_than_some,
    9 < ANY(ARRAY[10,20,5]::INTEGER[]) AS less_than_some,
    9 <> ANY(ARRAY[9,9,10]::INTEGER[]) AS different_from_some;
```

Cả ba có thể là `TRUE`:

- `9 > ANY({10,20,5})` đúng vì 9 > 5.
- `9 < ANY({10,20,5})` đúng vì 9 < 10.
- `9 <> ANY({9,9,10})` đúng vì 9 khác 10, **dù mảng có hai số 9**.

Đây là bẫy quan trọng: `x <> ANY(array)` **không có nghĩa** “x không nằm trong mảng”. Nó chỉ hỏi “có ít nhất một phần tử khác x không?”.

### 7.3. SOME là từ đồng nghĩa của ANY

PostgreSQL hỗ trợ `SOME` trong ngữ nghĩa so sánh lượng hóa:

```sql
SELECT
    9 > SOME(ARRAY[2,15]::INTEGER[]) AS some_result,
    9 > ANY(ARRAY[2,15]::INTEGER[]) AS any_result;
```

Hai kết quả tương đương.

### 7.4. Chú ý cú pháp: ARRAY ở phía phải

```sql
-- Có ý nghĩa: scalar so sánh với các phần tử của mảng.
WHERE 'sql' = ANY(tags)

-- Một câu hỏi khác: cả mảng tags chứa phần tử sql.
WHERE tags @> ARRAY['sql']::TEXT[]
```

Hai biểu thức có thể chọn cùng những hàng trong dữ liệu chỉ chứa phần tử text không NULL, nhưng **không tự tương đương về tất cả ngữ nghĩa NULL và khả năng sử dụng index**.

---

## 8. ALL: so sánh phải đúng với mọi phần tử

Cú pháp:

```sql
value operator ALL(array_expression)
```

Biểu thức có ý nghĩa **“mọi phép so sánh tương ứng đều đúng”**.

```sql
SELECT
    10 > ALL(ARRAY[2,3,5]::INTEGER[]) AS greater_than_all,
    10 > ALL(ARRAY[2,30,5]::INTEGER[]) AS not_greater_than_all,
    'sql' = ALL(ARRAY['sql','sql']::TEXT[])
        AS every_element_is_sql;
```

Các kết quả lần lượt:

```text
TRUE
FALSE
TRUE
```

### 8.1. <> ALL nghĩa là không có phần tử bằng x

Một cách phổ biến để hỏi “giá trị x không thuộc mảng”:

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE 'sql' <> ALL(tags)
ORDER BY doc_id;
```

Với lab:

- Doc 2 và 9 không có `sql` và mọi phần tử đều khác `sql`.
- Doc 5 có mảng rỗng: `<> ALL({})` là `TRUE`.
- Doc 1, 3, 4, 7, 10 có `sql` nên `<> ALL` là `FALSE`.
- Doc 6 có cả mảng NULL: kết quả là `NULL`.
- Doc 8 chỉ có phần tử NULL: kết quả là `NULL`.

Vì `WHERE` chỉ giữ những điều kiện trả `TRUE`, doc 6 và 8 không được chọn.

### 8.2. 5 > ALL khác 5 > ANY

```sql
SELECT
    5 > ALL(ARRAY[1,2,3]::INTEGER[]) AS greater_than_every,
    5 > ANY(ARRAY[1,8,9]::INTEGER[]) AS greater_than_one,
    5 > ALL(ARRAY[1,8,9]::INTEGER[]) AS greater_than_every_mixed;
```

Kết quả:

```text
greater_than_every       = TRUE
greater_than_one         = TRUE
greater_than_every_mixed = FALSE
```

### 8.3. ALL thường dùng để viết ràng buộc phạm vi, nhưng không phải giải pháp cho mọi việc

Ví dụ:

```sql
SELECT 80 >= ALL(ARRAY[50,60,70]::INTEGER[]);
```

Nếu score ≥ mọi ngưỡng, điều kiện đúng. Tuy nhiên, nếu mảng có NULL hoặc rỗng, ý nghĩa sẽ khác với dự đoán “lớn hơn max”. Phải hiểu phần tiếp theo trước khi biến biểu thức thành business rule.

---

## 9. Bảng chân trị: ANY/ALL, mảng rỗng và NULL

SQL dùng **logic ba giá trị**: `TRUE`, `FALSE`, `UNKNOWN` (được biểu diễn bằng `NULL`).

Với những toán tử so sánh **strict** phổ biến như `=`, `<>`, `>`, `<`:

- `ANY` trả TRUE nếu có **ít nhất một** phép so sánh TRUE.
- Nếu không có TRUE nhưng có kết quả NULL, `ANY` trả NULL.
- Nếu tất cả phép so sánh là FALSE, `ANY` trả FALSE.
- `ALL` trả FALSE nếu có **ít nhất một** phép so sánh FALSE.
- Nếu không có FALSE nhưng có kết quả NULL, `ALL` trả NULL.
- Nếu tất cả phép so sánh là TRUE, `ALL` trả TRUE.

### 9.1. ANY trên mảng rỗng

```sql
SELECT
    5 = ANY(ARRAY[]::INTEGER[]) AS any_empty,
    5 > ANY(ARRAY[]::INTEGER[]) AS any_empty_compare;
```

Kết quả đều `FALSE`. Không có phần tử nào để tồn tại một phép so sánh TRUE.

### 9.2. ALL trên mảng rỗng

```sql
SELECT
    5 = ALL(ARRAY[]::INTEGER[]) AS all_empty_equal,
    5 > ALL(ARRAY[]::INTEGER[]) AS all_empty_compare;
```

Kết quả đều `TRUE`. Không có phản ví dụ nào làm điều kiện “mọi phần tử” sai — đây là **chân lý rỗng** (*vacuous truth*) trong logic lượng hóa.

### 9.3. Toàn bộ mảng là NULL

```sql
SELECT
    5 = ANY(NULL::INTEGER[]) AS any_null_array,
    5 = ALL(NULL::INTEGER[]) AS all_null_array;
```

Cả hai trả `NULL` vì chưa biết mảng đầu vào.

### 9.4. Phần tử NULL

```sql
SELECT
    5 = ANY(ARRAY[6,NULL::INTEGER]) AS any_unknown,
    5 = ALL(ARRAY[5,NULL::INTEGER]) AS all_unknown,
    5 = ANY(ARRAY[5,NULL::INTEGER]) AS any_has_match,
    5 = ALL(ARRAY[6,NULL::INTEGER]) AS all_has_mismatch;
```

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `5 = ANY({6,NULL})` | `NULL` | FALSE và UNKNOWN; không có TRUE |
| `5 = ALL({5,NULL})` | `NULL` | TRUE và UNKNOWN; không có FALSE |
| `5 = ANY({5,NULL})` | `TRUE` | Có ít nhất một TRUE |
| `5 = ALL({6,NULL})` | `FALSE` | Có ít nhất một FALSE |

### 9.5. Một bảng tóm tắt cần nhớ

| Array / phép so sánh | `x = ANY(array)` | `x = ALL(array)` |
| --- | --- | --- |
| `ARRAY[]` | FALSE | TRUE |
| `NULL::type[]` | NULL | NULL |
| `ARRAY[x]`, x không NULL | TRUE | TRUE |
| `ARRAY[y]`, y khác x | FALSE | FALSE |
| `ARRAY[x, NULL]` | TRUE | NULL |
| `ARRAY[y, NULL]`, y khác x | NULL | FALSE |
| `ARRAY[NULL]` | NULL | NULL |

Bảng giả định toán tử `=` strict thông thường và `x` không NULL. Với toán tử tùy biến không strict hoặc phép so sánh đặc biệt, phải xét ngữ nghĩa của toán tử.

### 9.6. Toán hạng trái NULL

```sql
SELECT
    NULL::INTEGER = ANY(ARRAY[1,2]::INTEGER[]) AS unknown_any,
    NULL::INTEGER = ALL(ARRAY[1,2]::INTEGER[]) AS unknown_all,
    NULL::INTEGER = ANY(ARRAY[]::INTEGER[]) AS empty_any,
    NULL::INTEGER = ALL(ARRAY[]::INTEGER[]) AS empty_all;
```

Với toán tử strict, NULL so với các phần tử khác tạo UNKNOWN. Nhưng mảng rỗng vẫn cho `ANY=FALSE` và `ALL=TRUE` vì không có phép so sánh cụ thể nào phải thực hiện.

---

## 10. Bẫy NOT IN, <> ANY và <> ALL

Ba cách viết dưới đây **không có cùng nghĩa**:

```sql
x <> ANY(array)
x <> ALL(array)
NOT (x = ANY(array))
```

### 10.1. <> ANY thường không phải điều bạn muốn

```sql
SELECT
    5 <> ANY(ARRAY[5,6]::INTEGER[]) AS not_equal_to_some,
    5 <> ALL(ARRAY[5,6]::INTEGER[]) AS not_equal_to_all;
```

Kết quả:

```text
not_equal_to_some = TRUE
not_equal_to_all  = FALSE
```

Một phần tử 6 đủ làm `5 <> ANY` đúng, dù mảng vẫn chứa 5.

Nếu muốn “không có phần tử bằng 5”, dùng `5 <> ALL(array)` hoặc phủ định `5 = ANY(array)` trong các ngữ nghĩa bình thường, đồng thời xử lý NULL rõ ràng.

### 10.2. De Morgan trong logic ba giá trị

Với toán tử `=` và `<>` thông thường:

```sql
NOT (5 = ANY(ARRAY[5,6]::INTEGER[]))
```

tương ứng với:

```sql
5 <> ALL(ARRAY[5,6]::INTEGER[])
```

Trong các trường hợp strict/SQL ba giá trị, hai cách đều bảo toàn UNKNOWN khi mảng có NULL không thể quyết định.

Chúng không có nghĩa “không tìm thấy phần tử bằng 5 thì luôn TRUE”, nếu còn một phần tử NULL có thể che giấu giá trị không biết.

### 10.3. NOT IN có bẫy NULL tương tự

```sql
SELECT
    5 NOT IN (6,7) AS without_null,
    5 NOT IN (6,NULL::INTEGER) AS with_null;
```

Kết quả:

- `without_null` là TRUE.
- `with_null` là NULL.

Vì không biết phần tử NULL có bằng 5 hay không, SQL không trả TRUE.

### 10.4. Khi muốn “không có nhãn sql” bao gồm cả mảng NULL?

Trước tiên phải xác định nghiệp vụ:

- NULL tags nghĩa **không biết nhãn**, không nên coi là “không có sql” → loại khỏi kết quả.
- NULL tags nghĩa **không lưu nhãn nào**, muốn coi như mảng rỗng → có thể `COALESCE`.
- Mảng có phần tử NULL nghĩa nhãn chưa biết → có chấp nhận kết luận “không có sql” không?

Ví dụ chọn chính sách “NULL toàn mảng coi như rỗng”, nhưng **vẫn giữ UNKNOWN từ phần tử NULL**:

```sql
WHERE 'sql' <> ALL(
    COALESCE(tags, ARRAY[]::TEXT[])
)
```

Nếu muốn coi cả các phần tử NULL là “không phải sql”, phải diễn đạt rõ chính sách khác; không tự động xem SQL UNKNOWN là FALSE.

---

## 11. ANY với mảng khác ANY với truy vấn con

PostgreSQL có cả:

```sql
scalar = ANY(array_expression)
```

và:

```sql
scalar = ANY(subquery)
```

Ví dụ truy vấn con:

```sql
SELECT
    d.doc_id, d.title
FROM array_ops_lab.documents AS d
WHERE d.doc_id = ANY (
    SELECT x.doc_id
    FROM array_ops_lab.documents AS x
    WHERE x.title ILIKE '%SQL%'
);
```

Ở đây vế phải là **một tập hàng do SELECT sinh ra**, không phải một cột mảng. PostgreSQL có cơ chế tối ưu semi-join/subquery tương ứng.

### 11.1. Membership trong một danh sách hằng

```sql
SELECT 3 = ANY(ARRAY[1,2,3]::INTEGER[]);
```

có ý nghĩa gần với:

```sql
SELECT 3 IN (1,2,3);
```

Khi có NULL trong danh sách, cả hai đều chịu logic ba giá trị.

### 11.2. Membership của cột scalar từ một tham số mảng

Ví dụ bảng orders có `status TEXT`:

```sql
SELECT *
FROM orders
WHERE status = ANY($1::TEXT[]);
```

Đây là mẫu rất hữu ích khi một request gửi danh sách trạng thái cần lọc, vì cột `status` là **scalar**. Với index B-tree thích hợp trên status và query đủ chọn lọc, PostgreSQL có thể có access path dùng index.

### 11.3. Membership trong một cột mảng

```sql
SELECT *
FROM array_ops_lab.documents
WHERE 'sql' = ANY(tags);
```

Đây là mẫu khác: mỗi hàng có một mảng tags cần xét phần tử. Tùy truy vấn, planner có thể phải đọc hàng và đánh giá biểu thức, trong khi GIN array index không mặc định tối ưu đúng dạng biểu thức này.

**Đừng dùng từ ANY mà quên hỏi: vế phải là một mảng tham số cho cột scalar, một mảng lưu trong cột, hay một subquery?** Chúng có thể có access paths rất khác nhau.

---

## 12. ANY và ALL với so sánh số

Với `INTEGER[]`, ta không chỉ kiểm tra membership mà còn kiểm tra điều kiện ngưỡng.

### 12.1. Ít nhất một score lớn hơn 9

```sql
SELECT doc_id, title, scores
FROM array_ops_lab.documents
WHERE 9 < ANY(scores)
ORDER BY doc_id;
```

Ý nghĩa: có ít nhất một phần tử score lớn hơn 9.

Lưu ý bên trái là 9:

```text
9 < ANY(scores)
= có ít nhất một score sao cho 9 < score
```

### 12.2. Mọi score đều dưới 50

```sql
SELECT doc_id, title, scores
FROM array_ops_lab.documents
WHERE 50 > ALL(scores)
ORDER BY doc_id;
```

Với scores không NULL, điều kiện đúng khi mọi điểm nhỏ hơn 50. Nhưng **scores rỗng cũng thỏa** và **scores chứa NULL có thể cho UNKNOWN**, nên nếu business rule yêu cầu “ít nhất một score và không có NULL”, cần thêm điều kiện.

### 12.3. Chỉ chấp nhận mảng không rỗng

```sql
SELECT doc_id, title, scores
FROM array_ops_lab.documents
WHERE cardinality(scores) > 0
  AND 50 > ALL(scores)
ORDER BY doc_id;
```

Điều này loại mảng rỗng và toàn bộ mảng NULL. Nhưng một mảng có phần tử NULL vẫn có thể khiến ALL là NULL nên không được chọn, đúng với policy “không kết luận khi thiếu dữ liệu”.

### 12.4. MIN/MAX có tương đương với ANY/ALL không?

Với một mảng không rỗng và không NULL:

```sql
x > ALL(array)
```

tương đương với x lớn hơn max phần tử mảng; còn:

```sql
x > ANY(array)
```

tương đương x lớn hơn min phần tử.

Nhưng:

- ALL trên mảng rỗng là TRUE.
- ANY trên mảng rỗng là FALSE.
- `MIN`/`MAX` qua `unnest` thường bỏ qua NULL và trả NULL khi không có giá trị non-NULL.
- ANY/ALL có cách lan truyền UNKNOWN từ phần tử NULL.

Vì vậy không thay máy móc ANY/ALL bằng MIN/MAX khi dữ liệu có empty/NULL.

---

## 13. Tìm phần giao: trước tiên xác định “giao” là gì

Giả sử:

```text
A = {sql, postgres, gin, sql}
B = {sql, api, gin, gin}
```

Có ít nhất ba câu hỏi khác nhau:

1. **Có phần tử chung hay không?** → dùng `A && B`.
2. **Những giá trị phân biệt nào xuất hiện ở cả hai?** → giao tập hợp: `{gin,sql}`.
3. **Có bao nhiêu bản sao mỗi giá trị trong giao đa tập?** → lấy số lần nhỏ hơn của mỗi phần tử: `{sql,gin}` trong ví dụ.

PostgreSQL có toán tử `&&` cho câu hỏi (1), còn để tạo một **mảng kết quả chứa chính các phần tử giao**, thường cần `unnest`, `INTERSECT` hoặc `array_agg`.

### 13.1. Chỉ cần biết giao có rỗng không

```sql
SELECT
    ARRAY['sql','postgres','gin']::TEXT[]
    && ARRAY['api','gin']::TEXT[]
        AS has_common_element;
```

Kết quả TRUE.

### 13.2. Giao có bao nhiêu giá trị phân biệt?

Bạn cần **trích phần tử chung**, loại trùng, rồi đếm. `cardinality(A)` hoặc `cardinality(B)` không trả số phần tử giao.

### 13.3. Giao cần giữ thứ tự không?

Một tập hợp theo nghĩa toán học không có thứ tự. Mảng PostgreSQL có thứ tự. Nếu API cần trả kết quả theo:

- Thứ tự alphabet.
- Thứ tự xuất hiện trong A.
- Thứ tự ưu tiên do người dùng chọn.
- Số lần xuất hiện của phần tử.

thì phải chỉ định logic đó. Không để kết quả của JOIN/INTERSECT tình cờ quyết định thứ tự sản phẩm.

---

## 14. Tìm giao phân biệt với unnest + INTERSECT

`unnest(anyarray)` tách một mảng thành nhiều hàng.

```sql
SELECT element
FROM unnest(ARRAY['sql','gin','sql']::TEXT[])
    AS x(element);
```

Ý niệm các dòng là `sql`, `gin`, `sql`. Khi cần thứ tự ổn định, phải kèm `WITH ORDINALITY` và `ORDER BY` như các phần sau.

Để lấy giao của hai mảng:

```sql
SELECT element
FROM unnest(
    ARRAY['sql','postgresql','gin','sql']::TEXT[]
) AS a(element)

INTERSECT

SELECT element
FROM unnest(
    ARRAY['sql','api','gin','gin']::TEXT[]
) AS b(element)

ORDER BY element;
```

Kết quả:

```text
gin
sql
```

### 14.1. Vì sao INTERSECT bỏ trùng?

`INTERSECT` theo mặc định có ngữ nghĩa **tập hợp**: kết quả chỉ chứa giá trị phân biệt xuất hiện ở cả hai tập đầu vào.

Vì vậy mặc dù A có `sql` hai lần và B có `gin` hai lần, kết quả `gin` và `sql` mỗi giá trị chỉ có một dòng.

### 14.2. Trả về một mảng thay vì nhiều hàng

```sql
SELECT COALESCE(
    ARRAY_AGG(element ORDER BY element),
    ARRAY[]::TEXT[]
) AS common_tags
FROM (
    SELECT element
    FROM unnest(
        ARRAY['sql','postgresql','gin','sql']::TEXT[]
    ) AS a(element)

    INTERSECT

    SELECT element
    FROM unnest(
        ARRAY['sql','api','gin','gin']::TEXT[]
    ) AS b(element)
) AS intersection;
```

Kết quả là một `TEXT[]` có phần tử `gin` và `sql` theo thứ tự alphabet.

### 14.3. Khi không có giao

Nếu subquery `INTERSECT` trả 0 dòng, `array_agg(...)` trả NULL. Ta dùng:

```sql
COALESCE(array_agg(...), ARRAY[]::TEXT[])
```

để trả mảng rỗng rõ ràng cho API, nếu đó là contract mong muốn.

### 14.4. Tại sao cần alias?

Khi dùng `unnest` và các subquery, alias như `AS a(element)` giúp câu SQL rõ ràng, tránh cột tên mặc định không mong muốn, nhất là khi có nhiều mảng cùng tham gia.

---

## 15. INTERSECT ALL: giao có giữ số lần xuất hiện

Nếu nghiệp vụ coi danh sách là **đa tập** (*multiset*) thay vì tập hợp, PostgreSQL hỗ trợ:

```sql
SELECT element
FROM unnest(
    ARRAY['a','a','b']::TEXT[]
) AS a(element)

INTERSECT ALL

SELECT element
FROM unnest(
    ARRAY['a','a','a','c']::TEXT[]
) AS b(element)

ORDER BY element;
```

Kết quả gồm **hai dòng `a`**. Lý do:

- A có 2 bản sao `a`.
- B có 3 bản sao `a`.
- Giao đa tập có `min(2,3) = 2` bản sao `a`.
- `b` và `c` không có ở cả hai.

So sánh:

| Biểu thức | Kết quả khái niệm |
| --- | --- |
| `INTERSECT` | `{a}` |
| `INTERSECT ALL` | `{a,a}` |
| `ARRAY['a'] @> ARRAY['a','a']` | TRUE |
| `ARRAY['a'] = ARRAY['a','a']` | FALSE |

**Containment không phải giao đa tập.** Đây là một khác biệt quan trọng khi nghiệp vụ có số lượng hoặc số lần xuất hiện của phần tử.

### 15.1. NULL trong INTERSECT

Các toán tử tập hợp SQL như `INTERSECT` xử lý các giá trị NULL theo cơ chế so khớp bản ghi cho việc loại trùng và giao tập hợp. Chẳng hạn, nếu mỗi đầu vào đều có một hàng chứa NULL, giao có thể chứa một hàng NULL.

Điều này **khác** với:

```sql
NULL::TEXT = ANY(ARRAY[NULL::TEXT])
```

vì phép bằng SQL thông thường giữa NULL và NULL trả UNKNOWN.

Nếu cần tìm “NULL là một phần tử chung hợp lệ” theo chính sách set operation, `INTERSECT` có ngữ nghĩa khác với so sánh `= ANY`; hãy chọn có chủ đích.

---

## 16. Tìm giao bằng = ANY và array_agg

Một cách khác là tháo A thành từng phần tử, rồi giữ những phần tử có trong B:

```sql
WITH input AS (
    SELECT
        ARRAY['sql','postgresql','gin','sql']::TEXT[]
            AS left_tags,
        ARRAY['sql','api','gin','gin']::TEXT[]
            AS right_tags
)
SELECT
    COALESCE(
        ARRAY_AGG(DISTINCT elem ORDER BY elem),
        ARRAY[]::TEXT[]
    ) AS common_tags
FROM input
CROSS JOIN LATERAL unnest(left_tags) AS a(elem)
WHERE elem = ANY(right_tags);
```

Kết quả gồm `gin` và `sql`.

Giải thích:

1. `unnest(left_tags)` sinh một hàng cho từng phần tử A.
2. `elem = ANY(right_tags)` giữ phần tử có ít nhất một giá trị bằng ở B.
3. `DISTINCT` loại trùng khi A có cùng phần tử nhiều lần.
4. `ORDER BY elem` cho thứ tự kết quả xác định.
5. `COALESCE` biến aggregate rỗng từ NULL thành mảng rỗng theo contract.

### 16.1. Ưu điểm

- Dễ đọc khi chỉ cần kiểm tra membership của các phần tử A trong B.
- Có thể thêm điều kiện vào `WHERE`.
- Có thể giữ thứ tự hoặc giữ duplicate nếu bỏ DISTINCT và tự điều chỉnh logic.

### 16.2. Hạn chế

- Nếu cả hai mảng dài, thực hiện so sánh membership nhiều lần có thể tốn CPU.
- Nếu có phần tử NULL, `elem = ANY(right_tags)` không coi NULL bằng NULL theo phép `=` thông thường.
- Nếu cần giao đa tập theo số lượng bản sao, không được đơn giản bỏ DISTINCT; làm thế sẽ giữ **mọi** bản sao từ A nếu B chứa ít nhất một bản sao, thay vì lấy minimum count.

### 16.3. Khi nào nên dùng INTERSECT?

Dùng `INTERSECT` khi muốn **giao tập hợp** của hai nguồn hàng và cần set semantics rõ ràng, đặc biệt nếu muốn NULL từ hai phía được xem là giá trị chung theo set operation.

Dùng `unnest` + `= ANY` khi điều kiện membership thuận tiện, cần điều khiển xử lý phần tử và chấp nhận semantics của toán tử so sánh.

---

## 17. Giao giữa hai cột mảng của một hàng

Giả sử một bảng chứa cả:

```text
requested_tags TEXT[]
available_tags TEXT[]
```

Muốn tạo cột `common_tags` cho mỗi bản ghi, có thể dùng `LATERAL`:

```sql
WITH requests(request_id, requested_tags, available_tags) AS (
    VALUES
      (1,
       ARRAY['sql','gin','api']::TEXT[],
       ARRAY['sql','json','gin']::TEXT[]),
      (2,
       ARRAY['java']::TEXT[],
       ARRAY['sql','api']::TEXT[]),
      (3,
       ARRAY[]::TEXT[],
       ARRAY['sql']::TEXT[])
)
SELECT
    r.request_id,
    COALESCE(c.common_tags, ARRAY[]::TEXT[]) AS common_tags
FROM requests AS r
LEFT JOIN LATERAL (
    SELECT ARRAY_AGG(DISTINCT x.tag ORDER BY x.tag)
        AS common_tags
    FROM unnest(r.requested_tags) AS x(tag)
    WHERE x.tag = ANY(r.available_tags)
) AS c ON TRUE
ORDER BY r.request_id;
```

Kết quả mong đợi:

| request_id | common_tags |
| ---: | --- |
| 1 | `{gin,sql}` |
| 2 | `{}` |
| 3 | `{}` |

### 17.1. Vì sao dùng LATERAL?

Subquery bên phải dùng các cột của hàng `requests` hiện tại:

```text
r.requested_tags
r.available_tags
```

`LATERAL` cho phép tính biểu thức phụ thuộc hàng phía ngoài. Cú pháp này hữu ích khi cần xử lý mỗi cặp mảng riêng biệt.

### 17.2. Không gọi hàm giao tập hợp không tồn tại mặc định

PostgreSQL core **không có một hàm phổ quát tên `array_intersection(anyarray, anyarray)`** cho mọi kiểu với mọi chính sách trùng/NULL. Một số extension hoặc dự án có cung cấp hàm riêng; không nên viết `array_intersection` rồi giả định PostgreSQL luôn nhận diện.

Có thể biểu diễn giao bằng `INTERSECT`, `unnest`/`array_agg` hoặc tự định nghĩa SQL function nếu ứng dụng thường xuyên cần cùng một contract.

---

## 18. Tìm phần giao có giữ thứ tự của mảng gốc

Một API có thể yêu cầu **giao phần tử theo thứ tự xuất hiện đầu tiên trong A**, thay vì sort alphabet.

Ví dụ:

```text
A = [gin, sql, api, gin, postgres]
B = [postgres, sql, gin]

Giao phân biệt theo thứ tự A:
[gin, sql, postgres]
```

Dùng `WITH ORDINALITY`:

```sql
WITH inputs AS (
    SELECT
        ARRAY['gin','sql','api','gin','postgres']::TEXT[]
            AS left_tags,
        ARRAY['postgres','sql','gin']::TEXT[]
            AS right_tags
),
first_positions AS (
    SELECT
        x.tag,
        MIN(x.ord) AS first_ord
    FROM inputs AS i
    CROSS JOIN LATERAL unnest(i.left_tags)
        WITH ORDINALITY AS x(tag, ord)
    WHERE x.tag = ANY(i.right_tags)
    GROUP BY x.tag
)
SELECT COALESCE(
    ARRAY_AGG(tag ORDER BY first_ord),
    ARRAY[]::TEXT[]
) AS ordered_intersection
FROM first_positions;
```

Kết quả:

```text
{gin,sql,postgres}
```

### 18.1. Vì sao MIN(ord)?

A chứa `gin` hai lần. Ta muốn một bản sao trong giao phân biệt, đặt tại **vị trí xuất hiện đầu tiên**. `MIN(ord)` xác định vị trí đó.

### 18.2. Đừng tin thứ tự tình cờ của SELECT

Dù `unnest` thường phát phần tử theo thứ tự lưu trữ trong trường hợp đơn giản, **thứ tự đầu ra của một truy vấn quan hệ không được bảo đảm nếu không có ORDER BY thích hợp**. Khi ghép JOIN, GROUP BY hoặc aggregate, thứ tự càng không thể giả định.

Trong `array_agg`, đặt `ORDER BY` **bên trong aggregate** nếu thứ tự của phần tử mảng kết quả có ý nghĩa.

---

## 19. Tìm giao NULL-safe có chủ đích

Một số ứng dụng coi NULL là một giá trị phân biệt trong phép giao; số khác muốn loại bỏ NULL hoàn toàn.

### 19.1. Chính sách A: bỏ tất cả phần tử NULL

```sql
WITH a(tag) AS (
    SELECT * FROM unnest(
        ARRAY['sql', NULL::TEXT, 'gin']::TEXT[]
    )
),
b(tag) AS (
    SELECT * FROM unnest(
        ARRAY['gin', NULL::TEXT, 'api']::TEXT[]
    )
)
SELECT tag
FROM a
WHERE tag IS NOT NULL

INTERSECT

SELECT tag
FROM b
WHERE tag IS NOT NULL

ORDER BY tag;
```

Kết quả chỉ còn `gin`.

### 19.2. Chính sách B: NULL là phần tử chung hợp lệ

```sql
SELECT tag
FROM unnest(
    ARRAY['sql',NULL::TEXT,'gin']::TEXT[]
) AS a(tag)

INTERSECT

SELECT tag
FROM unnest(
    ARRAY['gin',NULL::TEXT,'api']::TEXT[]
) AS b(tag);
```

Kết quả có `gin` **và một hàng NULL** theo semantics của set operations.

### 19.3. So sánh NULL-safe trong JOIN

Nếu cần một phép JOIN xem hai NULL tương ứng nhau, PostgreSQL có:

```sql
a.tag IS NOT DISTINCT FROM b.tag
```

Ví dụ:

```sql
SELECT a.tag
FROM unnest(ARRAY['sql',NULL::TEXT]::TEXT[]) AS a(tag)
JOIN unnest(ARRAY['api',NULL::TEXT]::TEXT[]) AS b(tag)
  ON a.tag IS NOT DISTINCT FROM b.tag;
```

Phép `IS NOT DISTINCT FROM` khác với `=` khi hai toán hạng NULL. Nhưng nếu mỗi bên có phần tử trùng, JOIN sẽ nhân số cặp match; cần DISTINCT/GROUP BY tùy contract.

### 19.4. Không cố viết IS NOT DISTINCT FROM ANY

`IS NOT DISTINCT FROM` là cấu trúc so sánh NULL-safe trong SQL, **không phải toán tử nhị phân tùy ý có thể đặt trực tiếp vào mọi vị trí `operator ANY(...)`**. Khi cần NULL-safe membership, dùng JOIN/subquery `EXISTS` với điều kiện `IS NOT DISTINCT FROM` hoặc cấu trúc thích hợp thay vì giả định tồn tại cú pháp `IS NOT DISTINCT FROM ANY`.

---

## 20. ANY/ALL và phép đếm phần tử bằng aggregate

Có thể kiểm tra “ít nhất hai giá trị >= 10” bằng tháo mảng:

```sql
SELECT
    d.doc_id,
    COUNT(*) FILTER (WHERE s.score >= 10) AS count_ge_10
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.scores) AS s(score)
GROUP BY d.doc_id
HAVING COUNT(*) FILTER (WHERE s.score >= 10) >= 2
ORDER BY d.doc_id;
```

Trong lab, doc 1 có ba scores >= 10.

### 20.1. ANY không thay được câu hỏi về số lượng

```sql
10 <= ANY(scores)
```

chỉ cho biết có **ít nhất một** điểm đạt ngưỡng, không trả lời “có hai điểm trở lên”.

### 20.2. ALL không phải COUNT đạt 100%

Nếu mảng rỗng, `x <= ALL(array)` là TRUE theo logic lượng hóa, trong khi câu “100% điểm trong danh sách đạt” có thể không hợp lệ nếu danh sách không có điểm.

Cần thêm điều kiện `cardinality(scores) > 0` nếu chính sách nghiệp vụ yêu cầu tập phần tử không rỗng.

### 20.3. Mảng có NULL và aggregate

Các aggregate như `COUNT(score)` và `AVG(score)` bỏ qua NULL; `COUNT(*)` đếm cả dòng chứa NULL.

Ví dụ:

```sql
SELECT
    COUNT(*) AS all_elements,
    COUNT(score) AS known_elements,
    AVG(score) AS average_known_score
FROM unnest(
    ARRAY[10,NULL::INTEGER,20]::INTEGER[]
) AS s(score);
```

Số dòng là 3, số score biết giá trị là 2 và average của hai score đã biết là 15.

Đây **không tương đương** tự động với ngữ nghĩa UNKNOWN của `ANY`/`ALL`; không thay cơ chế mà chưa xác định cách xử lý giá trị thiếu.

---

## 21. Các hàm quan sát mảng

### 21.1. cardinality — tổng số phần tử

```sql
SELECT
    cardinality(ARRAY[1,2,3]::INTEGER[]) AS three,
    cardinality(ARRAY[]::INTEGER[]) AS zero,
    cardinality(NULL::INTEGER[]) AS unknown;
```

Kết quả:

```text
three   = 3
zero    = 0
unknown = NULL
```

`cardinality` hỗ trợ mảng đa chiều và trả tổng số phần tử ở mọi chiều.

### 21.2. array_length — độ dài một chiều

```sql
SELECT
    array_length(ARRAY[1,2,3]::INTEGER[], 1) AS first_dim,
    array_length(ARRAY[]::INTEGER[], 1) AS empty_dim,
    array_length(NULL::INTEGER[], 1) AS null_dim;
```

Kết quả:

- `first_dim=3`.
- `empty_dim=NULL`, không phải 0.
- `null_dim=NULL`.

Vì vậy:

```sql
WHERE array_length(tags, 1) = 0
```

**không phải cách đáng tin để tìm mảng rỗng**. Dùng `cardinality(tags)=0` hoặc so mảng với `ARRAY[]::TEXT[]` theo contract.

### 21.3. array_dims, array_lower và array_upper

```sql
SELECT
    array_dims(ARRAY[10,20,30]::INTEGER[]) AS dimensions,
    array_lower(ARRAY[10,20,30]::INTEGER[], 1) AS lower_bound,
    array_upper(ARRAY[10,20,30]::INTEGER[], 1) AS upper_bound;
```

Các hàm này giúp hiểu số chiều và chỉ số gốc, nhất là khi làm việc với dữ liệu mảng không bắt đầu tại chỉ số 1.

### 21.4. Mảng NULL vs rỗng trong báo cáo

```sql
SELECT
    COUNT(*) AS documents,
    COUNT(*) FILTER (WHERE tags IS NULL) AS null_arrays,
    COUNT(*) FILTER (WHERE cardinality(tags) = 0)
        AS empty_arrays,
    COUNT(*) FILTER (WHERE cardinality(tags) > 0)
        AS nonempty_arrays
FROM array_ops_lab.documents;
```

Mỗi metric mang ý nghĩa khác nhau. Không coi missing data (NULL) tự động bằng empty collection.

---

## 22. Tìm vị trí phần tử: array_position và array_positions

### 22.1. array_position

```sql
SELECT
    array_position(
        ARRAY['sql','gin','sql']::TEXT[], 'sql'
    ) AS first_position,
    array_position(
        ARRAY['sql','gin','sql']::TEXT[], 'java'
    ) AS absent_position;
```

Kết quả:

```text
first_position  = 1
absent_position = NULL
```

Hàm trả vị trí xuất hiện đầu tiên trong mảng một chiều; không trả TRUE/FALSE như ANY.

### 22.2. array_positions

```sql
SELECT array_positions(
    ARRAY['sql','gin','sql']::TEXT[],
    'sql'
) AS all_positions;
```

Kết quả là mảng các vị trí, ví dụ `{1,3}`.

### 22.3. Tìm phần tử NULL bằng array_position

Một ưu điểm: `array_position`/`array_positions` dùng ngữ nghĩa so sánh phù hợp với `IS NOT DISTINCT FROM` để tìm phần tử, nên có thể tìm được **vị trí phần tử NULL**:

```sql
SELECT
    array_position(
        ARRAY['sql',NULL::TEXT,'gin']::TEXT[],
        NULL::TEXT
    ) AS null_position;
```

Kết quả là 2.

Điều này khác với:

```sql
NULL::TEXT = ANY(
    ARRAY['sql',NULL::TEXT,'gin']::TEXT[]
)
```

vốn trả UNKNOWN với toán tử bằng strict.

### 22.4. Khi nào dùng array_position?

- Cần biết **vị trí**.
- Cần tìm phần tử NULL theo chính sách thích hợp.
- Cần sửa/thay một phần tử ở vị trí cụ thể.

Khi chỉ cần membership và có GIN index trên cột mảng, `tags @> ARRAY['x']` thường là biểu thức thích hợp hơn cho access path.

---

## 23. unnest và WITH ORDINALITY

`unnest` biến mảng thành nhiều hàng để dùng những công cụ SQL quan hệ quen thuộc: JOIN, GROUP BY, DISTINCT, ORDER BY, INTERSECT.

### 23.1. Tháo một mảng

```sql
SELECT element
FROM unnest(
    ARRAY['sql','gin','array']::TEXT[]
) AS t(element);
```

### 23.2. Giữ vị trí

```sql
SELECT element, ord
FROM unnest(
    ARRAY['sql','gin','array']::TEXT[]
) WITH ORDINALITY AS t(element, ord)
ORDER BY ord;
```

Kết quả theo thứ tự:

| ord | element |
| ---: | --- |
| 1 | sql |
| 2 | gin |
| 3 | array |

### 23.3. Tháo mảng của từng hàng

```sql
SELECT
    d.doc_id,
    t.ord,
    t.tag
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags)
    WITH ORDINALITY AS t(tag, ord)
WHERE d.doc_id IN (1,4)
ORDER BY d.doc_id, t.ord;
```

Doc 4 thể hiện rõ hai vị trí có cùng nhãn `sql`.

### 23.4. Mảng rỗng và mảng NULL sau unnest

`unnest(ARRAY[]::TEXT[])` và `unnest(NULL::TEXT[])` không tạo các phần tử bình thường để lặp. Với `CROSS JOIN LATERAL`, các hàng cha không có phần tử được loại khỏi kết quả.

Nếu muốn **giữ mọi hàng cha** dù mảng rỗng/NULL, dùng `LEFT JOIN LATERAL ... ON TRUE`, rồi cẩn thận rằng có thể xuất hiện **một hàng null-extended** cho mỗi hàng cha không có phần tử:

```sql
SELECT
    d.doc_id,
    t.tag,
    t.ord
FROM array_ops_lab.documents AS d
LEFT JOIN LATERAL unnest(d.tags)
    WITH ORDINALITY AS t(tag, ord) ON TRUE
WHERE d.doc_id IN (5,6)
ORDER BY d.doc_id;
```

Đừng dùng `COUNT(*)` sau LEFT JOIN LATERAL để suy ra số phần tử mảng: với hàng không có phần tử, COUNT(*) có thể vẫn bằng 1. Dùng `COUNT(t.ord)` hoặc `cardinality(tags)` theo mục đích.

---

## 24. array_agg và ARRAY(SELECT ...)

### 24.1. Gộp các dòng trở lại thành mảng

```sql
SELECT
    array_agg(tag ORDER BY tag) AS tags_sorted
FROM (
    VALUES ('sql'::TEXT),('gin'),('postgresql')
) AS x(tag);
```

Kết quả là một mảng text theo thứ tự alphabet.

### 24.2. Loại trùng

```sql
SELECT
    array_agg(DISTINCT tag ORDER BY tag) AS unique_tags
FROM (
    VALUES ('sql'::TEXT),('gin'),('sql'),('array')
) AS x(tag);
```

Kết quả có một `sql`, không lặp.

### 24.3. array_agg có thể đưa NULL vào mảng

Nếu input chứa NULL, `array_agg` có thể chứa phần tử NULL. Muốn loại bỏ:

```sql
SELECT
    array_agg(DISTINCT tag ORDER BY tag)
        FILTER (WHERE tag IS NOT NULL) AS known_tags
FROM (
    VALUES ('sql'::TEXT),(NULL::TEXT),('gin')
) AS x(tag);
```

### 24.4. Không có dòng thì sao?

`array_agg` với 0 input rows trả NULL. Nếu API muốn mảng rỗng, dùng `COALESCE` với mảng rỗng đúng kiểu:

```sql
SELECT COALESCE(
    array_agg(tag ORDER BY tag),
    ARRAY[]::TEXT[]
)
FROM (
    SELECT 'sql'::TEXT AS tag WHERE FALSE
) AS x;
```

### 24.5. ARRAY(SELECT ...) có hành vi hữu ích

PostgreSQL cũng cho phép:

```sql
SELECT ARRAY(
    SELECT tag
    FROM (
        VALUES ('sql'::TEXT),('gin'),('api')
    ) AS x(tag)
    ORDER BY tag
) AS tags_array;
```

Với subquery không trả hàng nào, array constructor kiểu này có thể tạo mảng rỗng, khác với `array_agg` trả NULL khi không có input. Chọn cách diễn đạt phù hợp ngữ nghĩa và dữ liệu.

---

## 25. Tạo một danh sách nhãn phân biệt từ toàn bảng

Một báo cáo cần “mọi nhãn đang được dùng”:

```sql
SELECT COALESCE(
    array_agg(DISTINCT t.tag ORDER BY t.tag),
    ARRAY[]::TEXT[]
) AS all_known_tags
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags) AS t(tag)
WHERE t.tag IS NOT NULL;
```

Mô hình:

```text
documents.tags
    |
    v
unnest từng hàng
    |
    v
lọc phần tử NULL
    |
    v
DISTINCT và ORDER BY
    |
    v
array_agg
```

### 25.1. Số tài liệu trên mỗi nhãn

```sql
SELECT
    t.tag,
    COUNT(DISTINCT d.doc_id) AS document_count
FROM array_ops_lab.documents AS d
CROSS JOIN LATERAL unnest(d.tags) AS t(tag)
WHERE t.tag IS NOT NULL
GROUP BY t.tag
ORDER BY document_count DESC, t.tag;
```

Tại sao `COUNT(DISTINCT d.doc_id)`?

Doc 4 chứa hai bản sao `sql`. Nếu dùng `COUNT(*)` ngay sau unnest, doc 4 có thể bị đếm hai lần cho cùng tag, trong khi metric ở đây là **số tài liệu có nhãn**, không phải số lần nhãn xuất hiện.

### 25.2. Nếu muốn đếm số lần xuất hiện?

Thay bằng `COUNT(*)` để nhận frequency của phần tử. Đây là metric khác; không dùng DISTINCT nếu nghiệp vụ muốn đếm duplicate.

---

## 26. Mảng nhiều chiều và việc tháo phần tử

PostgreSQL hỗ trợ mảng nhiều chiều:

```sql
SELECT
    ARRAY[[1,2],[3,4]]::INTEGER[] AS grid,
    array_length(ARRAY[[1,2],[3,4]]::INTEGER[], 1)
        AS first_dim_length,
    array_length(ARRAY[[1,2],[3,4]]::INTEGER[], 2)
        AS second_dim_length,
    cardinality(ARRAY[[1,2],[3,4]]::INTEGER[])
        AS total_elements;
```

Kết quả số:

```text
first_dim_length  = 2
second_dim_length = 2
total_elements    = 4
```

`unnest` của mảng nhiều chiều đưa các phần tử thành một dòng theo thứ tự lưu trữ khi gọi hàm:

```sql
SELECT element
FROM unnest(
    ARRAY[[1,2],[3,4]]::INTEGER[]
) AS x(element);
```

### 26.1. Không đồng nhất shape với set semantics

Mảng nhiều chiều mang thông tin về hình dạng và vị trí. Một lệnh `array_agg` hoặc `unnest` có thể bỏ cấu trúc chiều nếu không tự lưu vị trí/shape để xây lại.

Nếu nghiệp vụ là “lưới 2×2”, không được tự coi nó như một tập không thứ tự chứa 1,2,3,4.

### 26.2. Một số hàm chỉ hỗ trợ mảng một chiều

Những hàm như `array_position`/`array_positions` có giới hạn liên quan mảng một chiều. Khi làm việc với ma trận nhiều chiều, cần kiểm tra hợp đồng hàm thay vì áp dụng mọi ví dụ 1D nguyên xi.

### 26.3. Mảng đa chiều không phải thay thế mặc định cho bảng quan hệ

Nếu mỗi phần tử có id, timestamp, FK và cần update độc lập, bảng quan hệ với các cột tọa độ/hàng/cột thường rõ hơn trong thiết kế OLTP. Mảng đa chiều phù hợp khi dữ liệu thật sự là một giá trị cấu trúc được xử lý cùng nhau.

---

## 27. GIN index cho các toán tử mảng

Một lợi ích mạnh của PostgreSQL là có thể lập chỉ mục GIN cho cột mảng:

```sql
CREATE INDEX idx_documents_tags_gin
ON array_ops_lab.documents
USING GIN (tags);

ANALYZE array_ops_lab.documents;
```

GIN là **Generalized Inverted Index**: về ý tưởng, nó liên kết từng phần tử/tag với những hàng có chứa tag đó.

```text
"sql"        -> doc 1,3,4,7,10
"postgresql" -> doc 1,9,10
"gin"        -> doc 9,10
"api"        -> doc 2
```

Đây là sơ đồ khái niệm, không phải byte layout thực của GIN.

### 27.1. Các toán tử array_ops hỗ trợ

GIN operator class mặc định cho kiểu mảng phù hợp thường hỗ trợ các toán tử như:

- `@>` — contains.
- `<@` — contained by.
- `&&` — overlap.
- `=` — equality.

Ví dụ:

```sql
SELECT doc_id
FROM array_ops_lab.documents
WHERE tags @> ARRAY['sql','postgresql']::TEXT[];
```

Planner có thể dùng GIN để lấy các hàng có cả hai phần tử.

### 27.2. Tại sao = ANY(tags) có thể không tận dụng GIN?

```sql
WHERE 'sql' = ANY(tags)
```

là biểu thức lượng hóa scalar. GIN array_ops được xây để hỗ trợ **các toán tử mảng** ở các dạng được index hóa. Không nên kỳ vọng planner tự chuyển mọi `= ANY(array_column)` thành điều kiện GIN tương ứng.

Khi muốn tìm một tag và sử dụng GIN, viết:

```sql
WHERE tags @> ARRAY['sql']::TEXT[]
```

là lựa chọn dễ kiểm tra hơn.

**Cảnh báo về semantics:** Trên những mảng có NULL, `'x' = ANY(tags)` có thể trả UNKNOWN khi không có phần tử khớp, còn `tags @> ARRAY['x']` có thể trả FALSE trong cùng tình huống. Với `WHERE` chỉ chọn TRUE, hai điều kiện có thể chọn cùng hàng trong nhiều ca; nhưng chúng **không tương đương như giá trị Boolean dưới SQL ba giá trị**, nên đừng thay thế trong biểu thức `NOT`/CASE mà chưa kiểm tra.

### 27.3. Query dùng overlap để lọc OR

```sql
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags && ARRAY['gin','api']::TEXT[]
ORDER BY doc_id;
```

Đây là mẫu rõ nghĩa cho “ít nhất một nhãn thuộc danh sách” và có operator GIN hỗ trợ.

### 27.4. Truy vấn nào không được hỗ trợ tự động?

Không mặc định GIN array index tối ưu mọi truy vấn kiểu:

```sql
WHERE array_to_string(tags, ',') ILIKE '%sql%'
WHERE cardinality(tags) > 5
WHERE tags[2] = 'sql'
WHERE 'sql' = ANY(tags)
```

Những biểu thức này hỏi các thuộc tính khác: chuỗi nối, độ dài, phần tử tại vị trí, hoặc lượng hóa. Có thể cần expression index, cấu trúc lưu trữ khác hoặc scan, tùy workload.

### 27.5. Một bảng nhỏ vẫn có thể chọn Seq Scan

Lab chỉ có mười hàng, nên:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id, title
FROM array_ops_lab.documents
WHERE tags @> ARRAY['sql']::TEXT[];
```

có thể hiện `Seq Scan` dù GIN index tồn tại. Trên mười hàng, quét bảng có thể rẻ hơn đi qua GIN rồi heap. Không xem đó là index thất bại.

---

## 28. Quan sát kế hoạch GIN

Một plan có thể chứa:

```text
Bitmap Heap Scan on documents
  Recheck Cond: (tags @> '{sql}'::text[])
  -> Bitmap Index Scan on idx_documents_tags_gin
       Index Cond: (tags @> '{sql}'::text[])
```

Đây là mẫu minh họa. Tên node, cost và số hàng thay đổi theo phiên bản và thống kê.

### 28.1. Bitmap Index Scan

GIN tìm các hàng ứng viên dựa trên phần tử mảng. PostgreSQL có thể tạo bitmap vị trí cần truy cập.

### 28.2. Bitmap Heap Scan

Executor dùng bitmap để truy cập heap theo cách phù hợp. Một số điều kiện có thể cần kiểm tra lại:

```text
Recheck Cond: ...
```

Recheck không tự có nghĩa index sai. Với bitmap lossy hoặc operator class yêu cầu, xác minh heap giúp bảo đảm kết quả chính xác.

### 28.3. Thử một index path trong lab

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT doc_id
FROM array_ops_lab.documents
WHERE tags && ARRAY['gin','api']::TEXT[];

ROLLBACK;
```

Lệnh `SET LOCAL` chỉ tồn tại trong transaction này. Nó giúp **quan sát một phương án dùng index**, không chứng minh phương án đó tối ưu hơn.

Không bật `enable_seqscan=off` như một thiết lập production chỉ để ép kế hoạch dùng GIN.

### 28.4. Đọc kết quả EXPLAIN

Chú ý:

- `Planning Time` và `Execution Time`.
- `actual rows` so với `rows` ước lượng.
- `Buffers: shared hit/read`.
- `Rows Removed by Filter` và `Rows Removed by Index Recheck`.
- Các node `Seq Scan`, `Bitmap Index Scan`, `Bitmap Heap Scan`.
- Có thêm sort theo `ORDER BY` hay không.

GIN tốt cho membership, nhưng **không tự sắp xếp tài liệu theo thời gian**. Query `ORDER BY created_at DESC LIMIT 20` có thể vẫn cần Sort hoặc index B-tree riêng.

---

## 29. Hiệu năng: khi nào GIN có lợi?

Lợi ích thường rõ hơn khi:

- Bảng lớn.
- Mỗi hàng có nhiều tags.
- Query lọc các tags tương đối hiếm/chọn lọc.
- Truy vấn thường dùng `@>` và `&&`.
- Chi phí đọc được ưu tiên hơn chi phí cập nhật tags liên tục.

### 29.1. Tag quá phổ biến

Nếu 95% tài liệu có `sql`, query:

```sql
WHERE tags @> ARRAY['sql']::TEXT[]
```

vẫn trả gần toàn bảng. GIN có thể không tiết kiệm nhiều I/O; Seq Scan hoặc parallel scan có thể là phương án hợp lý.

### 29.2. Mỗi UPDATE vẫn có chi phí

PostgreSQL MVCC thường tạo tuple version mới khi UPDATE. Khi cập nhật giá trị tags:

- GIN index có thể cần duy trì các phần tử được index.
- WAL phát sinh với bảng logged.
- Chi phí VACUUM/index cleanup tồn tại.
- Update của một giá trị mảng lớn không mặc định là một phép đổi phần tử tại chỗ với chi phí miễn phí.

Nếu mỗi item cập nhật nhãn hàng nghìn lần mỗi giây, cần đo write amplification trước khi chọn GIN.

### 29.3. GIN pending list

GIN có cơ chế `fastupdate` và pending list trong các cấu hình phổ biến. Nó có thể gom phần công việc index update và cleanup sau, giúp throughput ghi ở một số workload nhưng tạo thêm công việc đọc/maintenance khi pending list lớn.

Không hiểu `fastupdate` là “tắt chi phí ghi index”. VACUUM/autovacuum và index maintenance vẫn quan trọng.

### 29.4. Chỉ mục trên scalar khác chỉ mục trên mảng

Một câu:

```sql
WHERE category = ANY($1::TEXT[])
```

với `category TEXT` có thể dùng **B-tree** trên category.

Một câu:

```sql
WHERE tags && $1::TEXT[]
```

với `tags TEXT[]` có thể dùng **GIN** trên tags.

Mẫu truy vấn và vị trí của cột indexed quan trọng hơn việc thấy từ `ANY` hoặc `ARRAY`.

---

## 30. ARRAY trong mô hình quan hệ: khi nào nên dùng bảng con?

Một mảng tags rất tiện:

```sql
CREATE TABLE documents (
    doc_id BIGINT PRIMARY KEY,
    tags TEXT[]
);
```

Nhưng hãy xem các yêu cầu sau:

- Mỗi tag phải tham chiếu đến bảng `tags_catalog` bằng foreign key.
- Không cho một tag xuất hiện hai lần trên cùng tài liệu.
- Mỗi lần gán tag cần timestamp, user_id và metadata riêng.
- Cần tìm “top tag theo doanh thu” hoặc JOIN tag với nhiều bảng khác.
- Cần cập nhật một tag rất thường xuyên và độc lập.
- Có hàng chục nghìn phần tử ở một tài liệu.

Khi đó một bảng quan hệ thường dễ bảo vệ invariant hơn:

```sql
CREATE TABLE documents (
    doc_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE tags_catalog (
    tag_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE document_tags (
    doc_id BIGINT NOT NULL REFERENCES documents(doc_id),
    tag_id BIGINT NOT NULL REFERENCES tags_catalog(tag_id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (doc_id, tag_id)
);
```

### 30.1. So sánh hai mô hình

| Nhu cầu | Mảng trong một cột | Bảng liên kết |
| --- | --- | --- |
| Đọc tất cả tags theo một document | Tiện | JOIN/aggregate |
| Filter theo nhãn | GIN `@>`/`&&` | B-tree/foreign key/index trên tag_id |
| Foreign key từng tag | Không trực tiếp theo từng phần tử | Tự nhiên |
| Unique từng phần tử | Cần chuẩn hóa/logic riêng | PK composite |
| Metadata trên quan hệ doc–tag | Bất tiện | Tự nhiên |
| Update một quan hệ riêng | Thường sửa giá trị mảng | INSERT/DELETE một hàng |
| Truy vấn theo tag và nhiều thuộc tính | Có thể phức tạp | Dễ join/aggregate |
| Lưu tập nhỏ, ít thay đổi | Có thể rất phù hợp | Có overhead JOIN |

Không có quy tắc cứng “mảng là phi quan hệ nên luôn sai”. PostgreSQL hỗ trợ mảng như một kiểu dữ liệu thực thụ; thiết kế đúng là thiết kế phù hợp **ràng buộc và workload**.

### 30.2. Không tự thay foreign key bằng danh sách IDs

Một cột `related_ids BIGINT[]` không tự enforce FK cho từng ID vào bảng đích. Nếu yêu cầu toàn vẹn tham chiếu thực sự, bảng liên kết với FK thường an toàn hơn so với chỉ lưu IDs trong array.

### 30.3. JSONB không giải quyết vấn đề FK này

Thay mảng SQL bằng JSONB array cũng không tự có FK từng phần tử. Chọn JSONB khi cấu trúc dữ liệu và truy vấn cần sự linh hoạt của JSON, không phải để né mọi ràng buộc quan hệ.

---

## 31. Cập nhật phần tử mảng trong PostgreSQL

PostgreSQL có nhiều hàm và toán tử giúp biến đổi mảng:

### 31.1. array_append

```sql
SELECT array_append(
    ARRAY['sql','api']::TEXT[],
    'gin'
) AS appended;
```

Kết quả `{sql,api,gin}`.

### 31.2. array_prepend

```sql
SELECT array_prepend(
    'gin',
    ARRAY['sql','api']::TEXT[]
) AS prepended;
```

Kết quả `{gin,sql,api}`.

### 31.3. array_cat hoặc ||

```sql
SELECT
    array_cat(
        ARRAY['sql']::TEXT[],
        ARRAY['gin','api']::TEXT[]
    ) AS concatenated,
    ARRAY['sql']::TEXT[] || ARRAY['gin','api']::TEXT[]
        AS with_operator;
```

Hai biểu thức đều nối các mảng theo ngữ nghĩa tương ứng.

### 31.4. array_remove

```sql
SELECT array_remove(
    ARRAY['sql','gin','sql']::TEXT[],
    'sql'
) AS removed;
```

Kết quả còn `{gin}` — **tất cả** phần tử bằng `sql` bị loại, không chỉ lần xuất hiện đầu.

`array_remove` có thể xử lý NULL theo ngữ nghĩa `IS NOT DISTINCT FROM` thích hợp khi cần loại các phần tử NULL:

```sql
SELECT array_remove(
    ARRAY['sql',NULL::TEXT,'gin']::TEXT[],
    NULL::TEXT
);
```

### 31.5. array_replace

```sql
SELECT array_replace(
    ARRAY['sql','gin','sql']::TEXT[],
    'sql',
    'postgresql'
) AS replaced;
```

Cả hai vị trí `sql` đều được thay.

### 31.6. Không lẫn append với set-add

`array_append(tags,'sql')` **có thể thêm trùng** nếu mảng đã có sql. Nếu API coi tags như tập hợp, cần kiểm tra membership hoặc normalize/deduplication:

```sql
UPDATE array_ops_lab.documents
SET tags = array_append(
    COALESCE(tags, ARRAY[]::TEXT[]),
    'new-tag'
)
WHERE doc_id = 5
  AND NOT COALESCE(
      tags @> ARRAY['new-tag']::TEXT[],
      FALSE
  )
RETURNING doc_id, tags;
```

Đây là cập nhật có điều kiện theo hàng. Trên dữ liệu gốc, doc 5 có mảng rỗng nên được thêm nhãn mới một lần.

**Cảnh báo:** Câu này thay đổi dữ liệu lab; nếu muốn dùng kết quả của các ví dụ trước, reset dữ liệu hoặc rollback trong transaction.

---

## 32. Concurrency khi sửa mảng: tránh lost update

Một kiểu lỗi ứng dụng:

```text
A đọc tags = [sql]
B đọc tags = [sql]

A thêm gin trên client:
    UPDATE tags = [sql,gin]
    COMMIT

B thêm api trên client bằng bản đọc cũ:
    UPDATE tags = [sql,api]
    COMMIT

Kết quả: [sql,api]
Thay đổi gin của A bị ghi đè.
```

Đây là **lost update ở tầng ứng dụng**, không phải lỗi của GIN hay `ANY`.

### 32.1. Dùng atomic UPDATE trên giá trị hiện tại

Thay vì client tính mảng mới từ bản cũ rồi gửi mảng tuyệt đối:

```sql
UPDATE array_ops_lab.documents
SET tags = array_append(
    COALESCE(tags, ARRAY[]::TEXT[]),
    'gin'
)
WHERE doc_id = 1;
```

Việc tính `array_append(tags,...)` trong database có thể giúp phối hợp cập nhật cùng hàng theo quy tắc row locking của PostgreSQL.

Tuy nhiên, nếu muốn tránh nhãn trùng, cần thêm điều kiện không chứa nhãn vào cùng UPDATE:

```sql
UPDATE array_ops_lab.documents
SET tags = array_append(
    COALESCE(tags, ARRAY[]::TEXT[]),
    'gin'
)
WHERE doc_id = 1
  AND NOT COALESCE(
      tags @> ARRAY['gin']::TEXT[],
      FALSE
  )
RETURNING tags;
```

### 32.2. Khi người dùng sửa cả tập nhãn

Nếu API cho phép thay toàn bộ danh sách tags đã đọc từ trước, nên cân nhắc **optimistic version** để phát hiện stale form:

```sql
-- Mẫu schema giả định có row_version.
UPDATE application_documents
SET tags = :new_tags,
    row_version = row_version + 1
WHERE doc_id = :doc_id
  AND row_version = :expected_version
RETURNING row_version;
```

Ứng dụng chỉ báo lưu thành công khi cập nhật đúng một hàng và transaction commit thành công. Không tự thay expected version mới rồi ghi lại payload cũ nếu nghiệp vụ không cho phép.

### 32.3. Khi nào bảng liên kết có lợi hơn?

Nếu nhiều worker thêm/xóa các tag độc lập, bảng `document_tags` với `PRIMARY KEY(doc_id,tag_id)` có thể giảm việc sửa cả giá trị mảng và giúp uniqueness/tác động cạnh tranh được biểu diễn bằng ràng buộc quan hệ.

---

## 33. Truyền tham số mảng qua Java/JDBC

Khi ứng dụng Java nhận danh sách tags cần lọc, **không** ghép các phần tử vào chuỗi SQL như:

```java
// Sai hướng: ghép input người dùng trực tiếp vào SQL.
String sql = "SELECT * FROM documents WHERE tags && '{"
        + userInput + "}'";
```

Vừa dễ sai escaping, vừa có rủi ro SQL injection.

### 33.1. Dùng PreparedStatement và SQL Array

Ví dụ PostgreSQL JDBC:

```java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

String sql = """
    SELECT doc_id, title
    FROM array_ops_lab.documents
    WHERE tags && ?::text[]
    ORDER BY doc_id
    """;

String[] requiredAnyTags = {"gin", "api"};

Array sqlArray = connection.createArrayOf(
    "text",
    requiredAnyTags
);

try {
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setArray(1, sqlArray);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                int docId = rs.getInt("doc_id");
                String title = rs.getString("title");
                // Xử lý kết quả.
            }
        }
    }
} finally {
    sqlArray.free();
}
```

### 33.2. Truy vấn yêu cầu đủ tất cả nhãn

Chỉ thay toán tử:

```sql
WHERE tags @> ?::TEXT[]
```

Với required tags gồm `sql` và `postgresql`, câu hỏi là AND của hai nhãn.

### 33.3. Truy vấn yêu cầu ít nhất một nhãn

```sql
WHERE tags && ?::TEXT[]
```

Với input gồm `gin` và `api`, câu hỏi là OR giữa các nhãn.

### 33.4. Nếu danh sách request rỗng?

Phải xác định hợp đồng endpoint:

- “Có **ít nhất một** trong tập rỗng” → điều kiện overlap với mảng rỗng là FALSE cho mảng không NULL, nên không có hàng phù hợp.
- “Chứa **tất cả** nhãn của tập rỗng” → mọi mảng không NULL thỏa containment.
- “Danh sách lọc rỗng nghĩa là **không áp dụng filter**” → cần bỏ predicate theo logic API, không máy móc sử dụng toán tử và kỳ vọng có kết quả “tất cả”.

Đặc biệt, việc truyền `NULL::TEXT[]` vào placeholder không đồng nghĩa truyền mảng rỗng. Chúng có ý nghĩa khác trong SQL.

### 33.5. BIGINT và type binding

Cần truyền đúng kiểu element: với `UUID[]` dùng `uuid`, với `INTEGER[]` dùng `int4`/kiểu JDBC tương ứng. Không gửi mọi mảng dưới dạng chuỗi text rồi tự cast lỏng lẻo; ép kiểu mơ hồ có thể gây lỗi, không tận dụng index hoặc nhận semantics ngoài ý muốn.

---

## 34. Phân biệt kiểu mảng SQL với JSONB array

Trong PostgreSQL:

```sql
SELECT
    ARRAY['sql','gin']::TEXT[] AS sql_array,
    '["sql","gin"]'::JSONB AS jsonb_array;
```

Hai giá trị có thể trông tương tự trong giao diện nhưng **khác kiểu và khác hệ toán tử**.

### 34.1. Mảng SQL

```sql
SELECT
    ARRAY['sql','gin']::TEXT[]
        && ARRAY['api','gin']::TEXT[] AS overlap,
    ARRAY['sql','gin']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS contains;
```

### 34.2. JSONB

```sql
SELECT
    '["sql","gin"]'::JSONB
        @> '["sql"]'::JSONB AS jsonb_contains;
```

JSONB có semantics JSON containment và có các toán tử existence/JSONPath phù hợp; không mặc định hỗ trợ `&&` với ý nghĩa overlap của mảng SQL.

### 34.3. Khi nào chọn JSONB?

- Cấu trúc hỗn hợp object/array/key/value thay đổi linh hoạt.
- Cần truy vấn cấu trúc JSON sâu hoặc JSONPath.
- Phần tử có thể là object phức tạp, không chỉ giá trị đồng nhất.

Chọn mảng SQL khi tập giá trị đồng kiểu rõ ràng và phép toán PostgreSQL array đúng nhu cầu. Chọn bảng con khi có FK/metadata/unique quan hệ. Đừng chọn kiểu chỉ vì biểu diễn JSON dễ truyền qua API.

---

## 35. Tìm giao trong truy vấn thực tế: nhãn và quyền

Giả sử một tính năng tìm tài liệu có tags giao với tags mà người dùng quan tâm:

```sql
SELECT
    doc_id,
    title,
    tags
FROM array_ops_lab.documents
WHERE tags && ARRAY['sql','api']::TEXT[]
ORDER BY doc_id;
```

Đây là **phép lọc theo sở thích**, không phải kiểm tra quyền truy cập.

### 35.1. Không dùng array tags làm quyền mặc định

Nếu `tags` có nội dung do người dùng tự sửa, kẻ khác có thể thay đổi tags để xuất hiện trong kết quả tìm kiếm. Quyền truy cập cần được xác định từ authentication/authorization hoặc RLS theo kiến trúc, không chỉ từ một mảng labels.

### 35.2. Tính giao và số nhãn khớp để xếp hạng

Một bài toán tìm kiếm có thể muốn xếp tài liệu theo số **nhãn phân biệt chung**:

```sql
WITH query_tags AS (
    SELECT ARRAY['sql','postgresql','gin']::TEXT[]
        AS requested
),
matches AS (
    SELECT
        d.doc_id,
        d.title,
        COUNT(DISTINCT t.tag) AS matched_tag_count
    FROM array_ops_lab.documents AS d
    CROSS JOIN query_tags AS q
    CROSS JOIN LATERAL unnest(d.tags) AS t(tag)
    WHERE t.tag = ANY(q.requested)
    GROUP BY d.doc_id, d.title
)
SELECT *
FROM matches
ORDER BY matched_tag_count DESC, doc_id ASC;
```

Ý nghĩa:

- `COUNT(DISTINCT t.tag)` đếm số nhãn chung phân biệt.
- Doc có duplicate tag không được lợi thêm điểm chỉ vì lưu `sql` hai lần.
- Những tài liệu không có nhãn khớp không xuất hiện vì inner/CROSS LATERAL không tạo hàng thỏa WHERE.

### 35.3. GIN hỗ trợ lọc trước, aggregation tính điểm sau

Ở quy mô lớn, một hướng viết kết hợp:

```sql
WITH query_tags AS (
    SELECT ARRAY['sql','postgresql','gin']::TEXT[]
        AS requested
)
SELECT
    d.doc_id,
    d.title,
    (
        SELECT COUNT(DISTINCT t.tag)
        FROM unnest(d.tags) AS t(tag)
        WHERE t.tag = ANY(q.requested)
    ) AS matched_tag_count
FROM array_ops_lab.documents AS d
CROSS JOIN query_tags AS q
WHERE d.tags && q.requested
ORDER BY matched_tag_count DESC, d.doc_id
LIMIT 20;
```

Predicate `d.tags && q.requested` có cơ hội dùng GIN để **giảm số tài liệu ứng viên** trước khi tính điểm giao cho chúng.

Tuy nhiên, khi tag rất phổ biến hoặc số ứng viên lớn, vẫn cần nhiều unnest/aggregation và sort. Không hiểu GIN tự tạo `matched_tag_count` hoặc trả kết quả theo số nhãn chung.

---

## 36. Các tình huống biên cần test trước khi dùng production

### 36.1. Mảng rỗng

```sql
SELECT
    'sql' = ANY(ARRAY[]::TEXT[]) AS any_empty,
    'sql' = ALL(ARRAY[]::TEXT[]) AS all_empty,
    ARRAY[]::TEXT[] && ARRAY['sql']::TEXT[]
        AS overlap_empty,
    ARRAY['sql']::TEXT[] @> ARRAY[]::TEXT[]
        AS contains_empty;
```

### 36.2. Mảng NULL

```sql
SELECT
    'sql' = ANY(NULL::TEXT[]) AS any_unknown,
    'sql' = ALL(NULL::TEXT[]) AS all_unknown,
    NULL::TEXT[] && ARRAY['sql']::TEXT[]
        AS overlap_unknown;
```

### 36.3. Phần tử NULL

```sql
SELECT
    'gin' = ANY(ARRAY['sql',NULL::TEXT]::TEXT[])
        AS no_known_match_but_unknown,
    'sql' = ANY(ARRAY['sql',NULL::TEXT]::TEXT[])
        AS known_match,
    array_position(
        ARRAY['sql',NULL::TEXT]::TEXT[],
        NULL::TEXT
    ) AS null_position;
```

### 36.4. Mảng có phần tử trùng

```sql
SELECT
    ARRAY['sql','sql']::TEXT[]
        @> ARRAY['sql']::TEXT[] AS contains,
    cardinality(ARRAY['sql','sql']::TEXT[]) AS cardinality_two;
```

### 36.5. Khác biệt chữ hoa/thường

```sql
SELECT
    'SQL' = ANY(ARRAY['sql']::TEXT[]) AS exact_text_match;
```

Với phép so sánh text thông thường trong cấu hình phân biệt chữ hoa/thường, không nên mong `'SQL'` và `'sql'` tự bằng nhau. Nếu hệ thống muốn nhãn case-insensitive:

- Chuẩn hóa dữ liệu khi ghi (ví dụ chữ thường theo một chính sách nhất quán).
- Chọn collation/type/operator phù hợp.
- Đảm bảo cả dữ liệu và tham số truy vấn được chuẩn hóa giống nhau.
- Thiết kế index theo cùng biểu thức.

Không tự bọc một phần bằng `LOWER` rồi kỳ vọng chỉ mục GIN trên `tags TEXT[]` tự hỗ trợ phép so sánh đã đổi.

### 36.6. Chuỗi có dấu và Unicode

`'tìm kiếm'` khác `'tim kiem'` theo cách xử lý thông thường. Nếu muốn tìm không dấu, cần một pipeline normalization riêng, có test trường hợp Unicode/collation. GIN array_ops giúp tìm **phần tử được lưu**, không tự làm tiếng Việt không dấu tương đương tiếng Việt có dấu.

---

## 37. Lỗi thường gặp

| Lỗi | Vì sao sai? | Cách đúng hơn |
| --- | --- | --- |
| Dùng `@>` khi chỉ cần một nhãn bất kỳ | @> yêu cầu tất cả nhãn | Dùng `&&` |
| Dùng `&&` khi cần đủ mọi nhãn | && chỉ cần một nhãn chung | Dùng `@>` |
| Dùng `x <> ANY(arr)` để nói “x không thuộc arr” | Chỉ cần một phần tử khác x | Dùng `x <> ALL(arr)` cùng chính sách NULL |
| Cho rằng `x = ANY(empty)` là NULL | ANY tập rỗng là FALSE | Kiểm tra theo lượng hóa |
| Cho rằng `x = ALL(empty)` là FALSE | ALL tập rỗng là TRUE | Thêm cardinality>0 nếu cần |
| Coi `NULL::TEXT[]` là `ARRAY[]::TEXT[]` | Unknown khác rỗng | Xử lý riêng |
| Coi mảng có NULL là mảng NULL | Một phần tử NULL khác toàn mảng NULL | Phân biệt rõ |
| Cho rằng `NULL = ANY({NULL})` là TRUE | So sánh strict với NULL ra UNKNOWN | Dùng semantics NULL-safe nếu muốn |
| Dùng `NOT IN` với danh sách có NULL và mong TRUE | UNKNOWN lan truyền | Rà chính sách NULL |
| Dùng `@>` để đếm duplicate | Containment không dùng multiplicity | unnest và COUNT |
| Coi `ARRAY[a,b] = ARRAY[b,a]` | Mảng có thứ tự | Nếu cần set, normalize/sort/distinct |
| Coi `@>` là phép giao trả mảng | @> trả Boolean | Dùng unnest/INTERSECT/array_agg |
| Dùng `INTERSECT ALL` mà muốn distinct | ALL giữ số bản sao theo minimum count | Dùng INTERSECT |
| Bỏ DISTINCT khi tự tìm giao và muốn tập hợp | Một bên có duplicate | Dùng INTERSECT hoặc DISTINCT |
| Dùng `= ANY` để tìm giao NULL-safe | '=' không coi NULL = NULL | INTERSECT hoặc IS NOT DISTINCT FROM |
| Quên ORDER BY khi array_agg | Thứ tự không ổn định | ORDER BY bên trong aggregate |
| Dùng `array_length(empty,1)=0` | Hàm trả NULL cho chiều không tồn tại | Dùng cardinality |
| Dùng COUNT(*) sau LEFT JOIN LATERAL unnest | Hàng không có phần tử vẫn được giữ | COUNT(ordinality) hoặc cardinality |
| Tưởng `array_agg` không có input trả {} | Trả NULL | COALESCE hoặc ARRAY constructor |
| Dùng array_to_string + LIKE để tìm tag chính xác | Chuỗi con và delimiter dễ false positive | @>/&& |
| Tưởng `'x'=ANY(array_col)` tự dùng GIN | Không cùng dạng operator indexable | `array_col @> ARRAY['x']` |
| Tạo GIN rồi thấy Seq Scan và kết luận index hỏng | Bảng nhỏ hoặc điều kiện không chọn lọc | Đọc EXPLAIN và đo |
| Tưởng GIN trả kết quả theo ORDER BY date | GIN không là B-tree sắp timestamp | Index khác/sort |
| Luôn dùng ARRAY thay bảng liên kết | Có thể mất FK/unique per element | Thiết kế theo invariant |
| Truyền array bằng string interpolation | Quoting/injection/type errors | PreparedStatement và SQL Array |
| Ghép toàn bộ tags từ client rồi ghi đè | Stale payload gây lost update | Atomic UPDATE/version guard |
| Coi JSONB array và SQL array có cùng toán tử | Hai type systems khác nhau | Đọc operator theo kiểu |
| Bỏ qua tags NULL trong endpoint filter | Có thể làm contract thay đổi | Quy định null/empty semantics |
| Không test duplicate | Metric count/tag frequency sai | Test mảng có phần tử trùng |
| Đếm số item bằng COUNT(*) sau unnest LEFT JOIN | Null-extended rows làm sai | COUNT(t.ord) |
| Tự chọn kiểu mảng từ string không cast | Dễ lỗi unknown type ở mảng rỗng | `ARRAY[]::TYPE[]` |
| Tưởng mọi kiểu có GIN array ops và mọi toán tử giống nhau | Opclass/type phụ thuộc khả năng hỗ trợ | Kiểm tra operator class và EXPLAIN |

---

## 38. Bài tập thực hành

### Bài 1 — Tạo và phân biệt ba trạng thái

Viết ba biểu thức tạo `ARRAY[]::INTEGER[]`, `NULL::INTEGER[]` và `ARRAY[NULL::INTEGER]`. Sử dụng `cardinality` để giải thích sự khác nhau.

### Bài 2 — @> chứa tất cả

Tìm các tài liệu chứa đồng thời nhãn `sql` và `postgresql`. Dự đoán doc_id từ lab.

### Bài 3 — && chứa bất kỳ

Tìm tài liệu có ít nhất một trong các nhãn `gin`, `api`. Tại sao không dùng `@> ARRAY['gin','api']`?

### Bài 4 — <@ tập cho phép

Viết truy vấn chỉ lấy hàng có mọi tag thuộc tập `{'sql','gin','array','postgresql','etl'}`. Tại sao mảng rỗng có thể xuất hiện trong kết quả?

### Bài 5 — Array equality vs containment

Kiểm tra `ARRAY['a','b'] = ARRAY['b','a']` và hai phép contains hai chiều. Giải thích vì sao kết quả không giống nhau.

### Bài 6 — Duplicate không làm thay @>

So sánh `ARRAY['a'] @> ARRAY['a','a']` với `ARRAY['a']=ARRAY['a','a']`. Nếu cần đúng hai bản sao, viết hướng SQL phù hợp.

### Bài 7 — Scalar membership

Tìm hàng có tag `sql` bằng `'sql' = ANY(tags)`. So sánh kết quả hàng được chọn với `tags @> ARRAY['sql']` trên lab.

### Bài 8 — ANY trên mảng rỗng

Dự đoán `5 = ANY(ARRAY[]::INT[])` và `5 > ANY(ARRAY[]::INT[])`. Giải thích logic lượng hóa tồn tại.

### Bài 9 — ALL trên mảng rỗng

Dự đoán `5 = ALL(ARRAY[]::INT[])` và `5 > ALL(ARRAY[]::INT[])`. Vì sao TRUE không đồng nghĩa mảng có giá trị?

### Bài 10 — NULL toàn mảng

Dự đoán `5 = ANY(NULL::INT[])` và `5 = ALL(NULL::INT[])`. So với empty array.

### Bài 11 — NULL trong mảng ANY

Dự đoán `5 = ANY(ARRAY[6,NULL::INT])`, `5 = ANY(ARRAY[5,NULL::INT])` và giải thích thứ tự ưu tiên giữa TRUE, FALSE, UNKNOWN.

### Bài 12 — NULL trong mảng ALL

Dự đoán `5 = ALL(ARRAY[5,NULL::INT])`, `5 = ALL(ARRAY[6,NULL::INT])`.

### Bài 13 — <> ANY và <> ALL

Kiểm tra `5 <> ANY(ARRAY[5,6])` và `5 <> ALL(ARRAY[5,6])`. Cách nào diễn đạt “không có phần tử bằng 5”?

### Bài 14 — NOT IN có NULL

So sánh `5 NOT IN (6,7)` với `5 NOT IN (6,NULL)`. Tại sao cùng không thấy 5 mà kết quả khác?

### Bài 15 — Scores: ít nhất một và mọi phần tử

Viết query chọn hàng có ít nhất một score > 9, và query chọn hàng có mọi score < 50. Cách nào vô tình chọn mảng rỗng? Sửa theo contract “phải có score”.

### Bài 16 — ANY với cột scalar

Giả sử `orders.status TEXT`. Viết `WHERE status = ANY($1::TEXT[])`. So sánh khả năng index với `'sql' = ANY(tags)` ở bảng có cột mảng.

### Bài 17 — Giao hai mảng

Viết `INTERSECT` giữa `ARRAY['sql','gin','sql']` và `ARRAY['sql','api']`. Kết quả có mấy dòng sql?

### Bài 18 — Giao đa tập

Dùng `INTERSECT ALL` cho `A={a,a,b}` và `B={a,a,a,c}`. Vì sao có hai dòng a?

### Bài 19 — Tạo array từ INTERSECT

Dùng `ARRAY_AGG(... ORDER BY ...)` và `COALESCE` để trả mảng giao phân biệt, kể cả khi không có phần tử chung.

### Bài 20 — Giao bằng = ANY

Dùng `unnest(A)` và `elem = ANY(B)` tìm giao; thêm `DISTINCT`. Vì sao cách này khác `INTERSECT ALL` về duplicate?

### Bài 21 — NULL trong giao

Cho hai mảng cùng chứa NULL. So `INTERSECT` với `NULL = ANY(...)`. Làm thế nào để bỏ NULL khỏi giao?

### Bài 22 — Giao giữ thứ tự của A

Dùng `WITH ORDINALITY` và `MIN(ord)` để trả các phần tử giao phân biệt theo thứ tự xuất hiện đầu tiên trong A.

### Bài 23 — Vị trí phần tử

Dùng `array_position` tìm `sql` trong `{gin,sql,sql}` và `array_positions` tìm mọi vị trí. Kết quả ra sao?

### Bài 24 — Tìm vị trí NULL

Dùng `array_position(ARRAY['sql',NULL::TEXT],NULL::TEXT)`. Vì sao tìm được vị trí trong khi `NULL = ANY(...)` trả UNKNOWN?

### Bài 25 — Đếm phần tử theo tags

Viết query đếm số tài liệu mỗi tag bằng `unnest` và `COUNT(DISTINCT doc_id)`. Vì sao doc 4 có hai tag sql nhưng chỉ được tính là một tài liệu cho tag đó?

### Bài 26 — Đếm số lần xuất hiện

Viết query đếm số lần `sql` xuất hiện trên mọi phần tử tags của tất cả tài liệu, **không loại trùng**. So với số tài liệu có sql.

### Bài 27 — array_agg và NULL

Dùng `array_agg(tag)` trên tập có NULL, sau đó thêm `FILTER (WHERE tag IS NOT NULL)`. Khi không có hàng, cần làm gì để trả mảng rỗng?

### Bài 28 — array_length và cardinality

So sánh hai hàm trên mảng rỗng, mảng NULL và ma trận 2×2. Vì sao `array_length(tags,1)=0` không phát hiện mảng rỗng?

### Bài 29 — WITH ORDINALITY

Tháo `{sql,gin,array}` thành ba hàng có ordinality. Dùng ORDER BY ord để bảo đảm thứ tự xuất.

### Bài 30 — Mảng nhiều chiều

Tạo `ARRAY[[1,2],[3,4]]`, dùng cardinality, array_length ở chiều 1/2 và unnest. Khi nào việc flatten làm mất thông tin cấu trúc?

### Bài 31 — GIN index

Tạo GIN trên `tags`. Viết truy vấn `tags @> ARRAY['gin']` và `tags && ARRAY['api','gin']`, kiểm tra EXPLAIN. Vì sao bảng mười hàng có thể chọn Seq Scan?

### Bài 32 — GIN và = ANY

So sánh EXPLAIN của `'sql' = ANY(tags)` và `tags @> ARRAY['sql']`. Vì sao operator class quan trọng hơn sự tương đương trực quan của câu hỏi?

### Bài 33 — Case-insensitive tags

Nếu lưu `SQL` và `sql` như hai nhãn, đặt chính sách normalize ra sao? Làm sao bảo đảm truy vấn và index cùng dùng một cách chuẩn hóa?

### Bài 34 — Atomic append

Viết UPDATE thêm `gin` vào tags của doc 1 nếu chưa có, dùng `array_append` và predicate containment trong cùng statement. Điều gì xảy ra nếu chạy lại cùng câu?

### Bài 35 — Lost update

Mô tả hai client cùng đọc tags của một tài liệu rồi gửi mảng mới tuyệt đối. Đề xuất atomic UPDATE hoặc optimistic version để ngăn ghi đè.

### Bài 36 — JDBC parameter array

Viết PreparedStatement dùng `createArrayOf("text", ...)` và `WHERE tags && ?::TEXT[]`. Tại sao không nối user input vào SQL?

### Bài 37 — JSONB array và SQL array

Tạo `TEXT[]` và `JSONB` array cùng hai nhãn. Dùng toán tử contains tương ứng. Vì sao không gọi `&&` trực tiếp trên JSONB rồi giả định có operator như TEXT[]?

### Bài 38 — Bảng quan hệ con

Thiết kế schema `documents`, `tags_catalog`, `document_tags` với FOREIGN KEY và PRIMARY KEY(doc_id,tag_id). Khi nào mô hình này mạnh hơn lưu `TEXT[]`?

### Bài 39 — Bài toán giao và xếp hạng

Một query nhận 10 nhãn quan tâm, cần trả 20 tài liệu có ít nhất một nhãn chung, xếp theo **số nhãn chung phân biệt**. Viết phương án dùng GIN overlap để chọn ứng viên, rồi unnest và COUNT DISTINCT để xếp hạng.

### Bài 40 — Thiết kế truy vấn an toàn với NULL

Một API yêu cầu “tài liệu **không chứa nhãn sql**” nhưng schema cho tags=NULL và mảng có phần tử NULL. Đề xuất ít nhất hai contract khác nhau, viết SQL tương ứng và giải thích khác biệt của kết quả.

---

## 39. Checklist khi thiết kế truy vấn mảng trong ứng dụng

| Câu hỏi | Hướng kiểm tra |
| --- | --- |
| Cột chứa mảng SQL hay JSONB? | Kiểu dữ liệu thực tế |
| Mảng gồm kiểu phần tử nào? | TEXT/INTEGER/UUID/... |
| Có thể là toàn bộ mảng NULL? | `IS NULL` khác mảng rỗng |
| Có thể chứa phần tử NULL? | ANY/ALL có UNKNOWN |
| Có cần phần tử duy nhất? | Chuẩn hóa hoặc bảng liên kết |
| Có cần giữ thứ tự? | `WITH ORDINALITY`, `ORDER BY` |
| Muốn đủ mọi tags? | `@>` |
| Muốn ít nhất một tag chung? | `&&` |
| Muốn mọi tag thuộc tập cho phép? | `<@` |
| Muốn scalar bằng một phần tử? | `= ANY` |
| Muốn scalar khác mọi phần tử? | `<> ALL`, xét NULL |
| Có mảng rỗng? | ANY FALSE, ALL TRUE |
| Mảng NULL xử lý sao? | Không tự coi như empty |
| Có đang dùng `<> ANY` sai? | Đó không phải `NOT IN` |
| Cần giao Boolean hay array? | `&&` vs `INTERSECT/unnest` |
| Giao là set hay multiset? | `INTERSECT` vs `INTERSECT ALL` |
| NULL có là phần tử chung? | Set operations / NULL-safe join |
| Giao cần thứ tự A không? | Ordinality và first occurrence |
| Có muốn số phần tử giao? | DISTINCT và COUNT đúng |
| Có dùng COUNT sau unnest? | Đếm item hay đếm document? |
| Có cần array output rỗng? | `COALESCE(array_agg,ARRAY[]::type[])` |
| Có phần tử duplicate? | `@>` không đếm số lượng |
| Cần vị trí? | `array_position`/`array_positions` |
| Có mảng nhiều chiều? | cardinality và shape |
| Có dùng cardinality thay array_length đúng? | Empty array trả 0 vs NULL |
| Query có phù hợp GIN array_ops? | `@>`, `&&`, `<@`, `=` |
| Có đang dùng `=ANY(array_col)` rồi mong GIN? | Xem toán tử và EXPLAIN |
| Có input parameter list? | Bind SQL Array, đúng type |
| Input list rỗng nghĩa gì? | Không filter vs không có match |
| Có case/diacritic normalization? | Lưu và tìm đồng nhất |
| Có cần FK/unique từng element? | Cân nhắc bảng liên kết |
| Có cập nhật tags nhiều lần? | Update overhead, HOT/WAL/GIN |
| Có concurrent updates? | Atomic UPDATE hoặc version guard |
| Có query rất ít chọn lọc? | Seq Scan có thể tốt |
| Có benchmark đọc và ghi? | EXPLAIN, buffers, latency |
| Có tenant/quyền truy cập? | Authn/authz hoặc RLS riêng |
| Có test SQL ba giá trị? | Empty/NULL element/NULL array |
| Có test set vs multiset? | Duplicate và INTERSECT ALL |

## Kết luận

**Toán tử mảng, ANY, ALL và tìm phần giao** cung cấp nhiều cách diễn đạt điều kiện trên dữ liệu nhiều phần tử trong PostgreSQL. Điều quan trọng không phải nhớ càng nhiều ký hiệu càng tốt, mà là chọn đúng **ngữ nghĩa phép toán**:

- `tags @> ARRAY['a','b']`: tags phải chứa **tất cả** phần tử yêu cầu.
- `tags && ARRAY['a','b']`: tags có **ít nhất một** phần tử chung.
- `tags <@ ARRAY[...]`: mọi phần tử tags thuộc tập cho phép.
- `x = ANY(arr)`: tồn tại ít nhất một phần tử bằng x.
- `x <> ALL(arr)`: mọi phần tử đều khác x, **nhưng phải xét UNKNOWN khi có NULL**.
- `x <> ANY(arr)` **không** có nghĩa “x không nằm trong mảng”.
- `ANY(empty)` là FALSE và `ALL(empty)` là TRUE; mảng NULL lại là UNKNOWN trong các so sánh strict phổ biến.
- `INTERSECT` tạo **giao tập hợp phân biệt**; `INTERSECT ALL` tạo giao có số bản sao theo minimum multiplicity.
- `unnest` và `array_agg` biến đổi giữa dạng mảng và dạng hàng; `WITH ORDINALITY` cùng `ORDER BY` giúp kiểm soát thứ tự.
- `array_position` có ngữ nghĩa NULL-safe khác phép bằng scalar thông thường.
- GIN là lựa chọn mạnh cho các truy vấn mảng dùng `@>`/`&&`, nhưng không phải mọi biểu thức `ANY` hay mọi phép xử lý array đều tự động dùng chỉ mục.
- Khi phần tử cần FOREIGN KEY, uniqueness hoặc metadata độc lập, **bảng liên kết quan hệ** thường là lựa chọn thiết kế rõ hơn.

Nếu hiểu đúng sự khác biệt giữa **membership, containment, overlap, logic ba giá trị và phép giao tập hợp**, bạn có thể viết những truy vấn mảng PostgreSQL vừa chính xác với dữ liệu rỗng/NULL/duplicate, vừa có đường tối ưu hợp lý khi dữ liệu tăng trưởng.
