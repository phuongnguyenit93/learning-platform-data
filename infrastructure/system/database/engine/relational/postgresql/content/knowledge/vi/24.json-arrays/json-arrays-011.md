# Chỉ mục cho mảng và so sánh với bảng liên kết trong PostgreSQL

## 1. Khi một cột cần lưu nhiều giá trị

Một bài đăng có thể mang nhiều thẻ (tags), một sản phẩm có nhiều thuộc tính, một bài học thuộc nhiều chủ đề, hoặc một người dùng có nhiều mã quyền. Với PostgreSQL, có hai cách mô hình hóa phổ biến:

1. **Mảng trong một cột:** lưu các phần tử cùng kiểu vào `integer[]`, `text[]` hoặc một kiểu mảng khác; thường dùng **GIN index** cho truy vấn membership, containment và overlap.
2. **Bảng liên kết:** mô hình quan hệ nhiều–nhiều với một hàng cho mỗi cặp, chẳng hạn `post_tags(post_id, tag_id)`; thường dùng **B-tree indexes, PRIMARY KEY và FOREIGN KEY** để bảo đảm tính toàn vẹn và phục vụ join.

Ví dụ với một bài đăng:

~~~text
Cách A — cột mảng:

posts_array
+---------+----------------------+----------+
| post_id | title                | tag_ids  |
+---------+----------------------+----------+
| 101     | PostgreSQL căn bản   | {1,2,4}  |
| 102     | JSON và mảng         | {1,5,6}  |
+---------+----------------------+----------+

Cách B — bảng liên kết:

posts                         post_tags
+---------+------------------+   +---------+--------+
| post_id | title            |   | post_id | tag_id |
+---------+------------------+   +---------+--------+
| 101     | PostgreSQL ...   |   | 101     | 1      |
| 102     | JSON và mảng     |   | 101     | 2      |
+---------+------------------+   | 101     | 4      |
                                  | 102     | 1      |
                                  | 102     | 5      |
                                  | 102     | 6      |
                                  +---------+--------+
~~~

Cả hai đều có thể trả lời “bài nào có thẻ PostgreSQL?”. Nhưng chúng khác nhau về **tính toàn vẹn tham chiếu, cấu trúc chỉ mục, cập nhật, báo cáo, số lượng phần tử và vòng đời dữ liệu**.

Điều quan trọng không phải chọn cách nào “hiện đại hơn”, mà là **mô hình nào biểu diễn đúng quan hệ nghiệp vụ và phù hợp kiểu truy vấn thường chạy**.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Hiểu PostgreSQL arrays, kiểu `integer[]`/`text[]`, mảng rỗng, NULL, phần tử trùng và thứ tự phần tử.
- Dùng đúng các toán tử mảng `@>`, `<@`, `&&`, `=` trong SQL.
- Phân biệt `element = ANY(array_column)` với phép containment và hiểu vì sao dạng truy vấn ảnh hưởng khả năng dùng index.
- Tạo **GIN index** bằng `USING gin` và quan sát `Bitmap Index Scan`/`Bitmap Heap Scan` với `EXPLAIN`.
- Phân biệt GIN cho membership với B-tree cho so sánh toàn bộ giá trị mảng.
- Thiết kế bảng liên kết chuẩn hóa với khóa chính, khóa ngoại, index hai chiều.
- Viết tương đương truy vấn tìm “có ít nhất một thẻ”, “có tất cả thẻ”, “không có thẻ”, báo cáo thống kê thẻ.
- Đánh giá UPDATE mảng, MVCC, TOAST, GIN pending list, khóa, concurrency và chi phí lưu trữ.
- Lập kế hoạch chuyển đổi giữa mảng và bảng liên kết mà không làm mất dữ liệu.
- Đọc kết quả benchmark và chọn thiết kế theo ràng buộc thực tế.

> **Phạm vi:** bài viết tập trung vào SQL arrays và nhiều–nhiều trong PostgreSQL. JSONB có các toán tử và GIN operator classes **khác** array, được so sánh riêng để tránh nhầm lẫn. Các SQL thực hành chỉ nên chạy trong database/schema thử nghiệm được phép. `EXPLAIN ANALYZE` thực thi câu lệnh; với DML phải có kế hoạch bảo vệ dữ liệu.

---

## 2. Trước khi chọn index: mảng mang ngữ nghĩa gì?

### 2.1. Mảng là một giá trị có thứ tự và có thể có phần tử lặp

PostgreSQL cho phép:

~~~sql
SELECT
    ARRAY[1, 2, 3]::integer[] AS normal_array,
    ARRAY[1, 1, 2]::integer[] AS duplicate_elements,
    ARRAY[]::integer[] AS empty_array,
    ARRAY[NULL, 2]::integer[] AS with_null;
~~~

Mảng **không phải tập hợp (set) theo nghĩa toán học**:

- Thứ tự phần tử có thể quan trọng khi so sánh toàn mảng, đọc bằng subscripting và `unnest`.
- Phần tử trùng vẫn có thể xuất hiện.
- Phần tử NULL có thể tồn tại, trừ khi thiết kế ứng dụng hoặc constraint ngăn lại.
- Một **cột mảng NULL** khác với **mảng rỗng** và khác mảng chứa một phần tử NULL.

Ví dụ:

~~~sql
SELECT
    ARRAY[1,2]::integer[] = ARRAY[2,1]::integer[]
        AS same_ordered_value,
    ARRAY[1,1]::integer[] = ARRAY[1]::integer[]
        AS same_multiplicity,
    ARRAY[]::integer[] IS NULL
        AS empty_is_null,
    (NULL::integer[]) IS NULL
        AS null_array_is_null;
~~~

### 2.2. Containment không đếm số lần xuất hiện

PostgreSQL định nghĩa containment `@>` theo kiểu **các phần tử có mặt**, không yêu cầu số lần xuất hiện bằng nhau.

~~~sql
SELECT
    ARRAY[1]::integer[] @> ARRAY[1,1]::integer[]
        AS contains_both_occurrences,
    ARRAY[1,1]::integer[] @> ARRAY[1]::integer[]
        AS contains_one,
    ARRAY[1,2]::integer[] && ARRAY[2,3]::integer[]
        AS has_common_element;
~~~

Ở đây cả ba biểu thức đều có thể trả `true`. Đây là yếu tố quyết định khi dùng mảng biểu diễn **set tags**: nếu không ngăn phần tử trùng, bộ dữ liệu có thể chứa một thẻ hai lần nhưng truy vấn `@>` không báo sự bất thường.

### 2.3. Có thể là mảng đa chiều

~~~sql
SELECT ARRAY[[1,2],[3,4]]::integer[][] AS matrix;
~~~

Mảng nhiều chiều phù hợp một số cấu trúc kỹ thuật, nhưng bài toán tags/membership thường nên dùng **mảng một chiều**. PostgreSQL có các chi tiết về dimensions/subscripts, còn `unnest` sẽ trải phẳng phần tử theo thứ tự lưu trữ. Không dùng mảng đa chiều để thay một quan hệ có cấu trúc phức tạp nếu cần FK, uniqueness theo từng cặp hoặc metadata từng phần tử.

### 2.4. Array NULL, empty và phần tử NULL là ba trường hợp khác nhau

| Giá trị | Ý nghĩa minh họa | `cardinality` |
|---|---|---|
| `NULL::integer[]` | Chưa biết/chưa có dữ liệu mảng | NULL |
| `'{}'::integer[]` | Biết chắc không có phần tử | 0 |
| `ARRAY[NULL]::integer[]` | Một vị trí phần tử có giá trị NULL | 1 |
| `ARRAY[1,2]::integer[]` | Có hai phần tử | 2 |

Nếu nghiệp vụ xem “không gắn thẻ” là mảng rỗng, nên dùng `NOT NULL DEFAULT '{}'::integer[]` và quy tắc không cho phần tử NULL.

### 2.5. Kiểu phần tử phải nhất quán

`integer[]` chứa integer, `text[]` chứa text, `uuid[]` chứa UUID. PostgreSQL kiểm tra type; muốn so với literal nên cast rõ khi có nguy cơ mơ hồ:

~~~sql
SELECT ARRAY[1,2,3]::integer[] @> ARRAY[2]::integer[];
~~~

Không dựa vào implicit cast tùy ý khi API truyền JSON/text/UUID, vì operator resolution hoặc index qual có thể khác.

---

## 3. Các toán tử mảng quan trọng

Bốn toán tử chính có liên quan đến GIN `array_ops`:

| Toán tử | Cách đọc | Ví dụ | Kết quả trực giác |
|---|---|---|---|
| `a @> b` | a **chứa mọi phần tử** của b | `'{1,2,3}'::int[] @> '{1,3}'::int[]` | true |
| `a <@ b` | a **là tập con theo phần tử** của b | `'{1,3}'::int[] <@ '{1,2,3}'::int[]` | true |
| `a && b` | a và b **có ít nhất một phần tử chung** | `'{1,2}'::int[] && '{2,4}'::int[]` | true |
| `a = b` | Hai **giá trị mảng bằng nhau** | `'{1,2}'::int[] = '{2,1}'::int[]` | false |

Giải thích tỉ mỉ:

### 3.1. Có tất cả các thẻ: `@>`

~~~sql
SELECT ARRAY[1, 2, 4]::int[] @> ARRAY[1, 4]::int[]
       AS has_all_requested_tags;
~~~

Nếu cột `tag_ids` có `{1,2,4}` và người dùng yêu cầu thẻ 1 **và** 4, predicate là:

~~~sql
WHERE tag_ids @> ARRAY[1,4]::int[]
~~~

`@>` là một phép **containment**, không phải “mảng lớn hơn”.

### 3.2. Có bất kỳ thẻ nào: `&&`

~~~sql
SELECT ARRAY[1, 2, 4]::int[] && ARRAY[4, 5]::int[]
       AS has_any_requested_tag;
~~~

Nếu ứng dụng muốn tìm bài có thẻ 4 **hoặc** 5:

~~~sql
WHERE tag_ids && ARRAY[4,5]::int[]
~~~

Lưu ý: `&&` trên array nghĩa là **overlap phần tử**; cùng ký hiệu toán tử trên range/geometry có semantics riêng theo kiểu dữ liệu.

### 3.3. Mọi thẻ của bài đều nằm trong tập cho phép: `<@`

~~~sql
SELECT ARRAY[1,4]::int[] <@ ARRAY[1,2,4,5]::int[]
       AS only_allowed_tags;
~~~

Tìm bài mà **mọi tag đang gắn** đều thuộc whitelist:

~~~sql
WHERE tag_ids <@ ARRAY[1,2,4,5]::int[]
~~~

Đây không tương đương “bài có đủ tất cả các tag whitelist”. Hướng chứa đảo ngược nhau.

### 3.4. Bằng toàn bộ mảng: `=`

~~~sql
SELECT ARRAY[1,2]::int[] = ARRAY[1,2]::int[] AS equal_value;
~~~

Equality cần quan tâm thứ tự và số phần tử. Khi mục tiêu là “hai bài có cùng **tập** thẻ”, equality có thể không phù hợp nếu lưu mảng không canonical hóa.

### 3.5. Mảng rỗng tạo các trường hợp đặc biệt

~~~sql
SELECT
    ARRAY[1,2]::int[] @> ARRAY[]::int[]
        AS contains_empty_array,
    ARRAY[1,2]::int[] && ARRAY[]::int[]
        AS overlaps_empty_array,
    ARRAY[]::int[] <@ ARRAY[1,2]::int[]
        AS empty_is_contained;
~~~

Về semantics tập hợp phần tử thông thường:

- Mọi mảng không NULL chứa mảng rỗng.
- Không có phần tử chung với một mảng rỗng.
- Mảng rỗng là subset của mọi mảng không NULL.

Với query “có đủ mọi tag được yêu cầu”, nếu danh sách yêu cầu trống, `@> '{}'` có thể trả true cho tất cả bài (trừ SQL NULL). API phải xác định rõ điều đó có đúng mong muốn hay không.

### 3.6. NULL không được xử lý như một tag bình thường

Với biểu thức ba giá trị SQL, phải phân biệt:

- Cột mảng là NULL.
- Mảng có phần tử NULL.
- Toán tử trả TRUE/FALSE/UNKNOWN theo định nghĩa.

Không dùng `ARRAY[NULL]` như “thẻ rỗng”; nếu có nhu cầu biểu diễn “không biết tag”, hãy mô hình hóa trạng thái riêng. Một thiết kế tags dạng set nên loại NULL elements bằng kiểm soát dữ liệu.

---

## 4. `ANY`, `unnest` và toán tử containment có giống nhau không?

### 4.1. Kiểm tra một phần tử bằng ANY

~~~sql
SELECT 4 = ANY(ARRAY[1,2,4]::int[]) AS has_four;
~~~

Trên cột:

~~~sql
WHERE 4 = ANY(tag_ids)
~~~

Đây là cú pháp tự nhiên, phổ biến và đúng cho nhiều mục tiêu truy vấn.

### 4.2. Vì sao ANY không mặc định trở thành GIN index scan?

GIN built-in `array_ops` được thiết kế cho các **array operators** như `@>`, `&&`, `<@` và `=`. Biểu thức `4 = ANY(tag_ids)` dùng **scalar-array comparison**, không phải tự động được planner biến thành `tag_ids @> ARRAY[4]` để sử dụng GIN.

Với workload membership trên cột mảng có GIN, nên thử predicate:

~~~sql
WHERE tag_ids @> ARRAY[4]::int[]
~~~

Và **xác nhận bằng `EXPLAIN`**. Đừng khẳng định mỗi câu có ANY đều dùng/không dùng một chỉ mục khác; biểu thức, phiên bản và access paths khác có thể ảnh hưởng plan.

### 4.3. Khác biệt nhỏ nhưng quan trọng với NULL

Khi mảng chứa NULL elements và không có giá trị khớp, phép `4 = ANY(tag_ids)` có thể trả **UNKNOWN**, còn kết quả containment có thể có semantics khác. Trong `WHERE`, chỉ TRUE mới giữ row, nên một số rewrite vẫn cho **cùng tập hàng được chọn**, nhưng **không nhất thiết là hai biểu thức boolean tương đương** trong mọi ngữ cảnh.

Ví dụ nếu cần trả boolean cho API, dùng `COALESCE` hoặc định nghĩa ràng buộc NULL rõ ràng trước khi thay thế một biểu thức bằng biểu thức khác.

### 4.4. `unnest` biến mảng thành các hàng

~~~sql
SELECT t.tag_id
FROM unnest(ARRAY[1,2,4]::int[]) AS t(tag_id);
~~~

Khi cần đếm từng tag, join với bảng tags hoặc tính aggregation, `unnest` hữu ích. Tuy nhiên:

~~~sql
WHERE 4 IN (SELECT unnest(tag_ids))
~~~

không phải cú pháp nên dùng để chứng minh GIN index trên `tag_ids`. Nó có thể làm phát sinh nhiều phép unnest; với membership bình thường, ưu tiên toán tử array indexable hoặc cấu trúc bảng liên kết.

### 4.5. Chọn biểu thức theo ý nghĩa, không chỉ theo index

| Câu hỏi nghiệp vụ | Hình thức mảng phù hợp |
|---|---|
| Có tag 4 không? | `tag_ids @> ARRAY[4]::int[]` hoặc `4 = ANY(tag_ids)` |
| Có tag 4 **và** 5 không? | `tag_ids @> ARRAY[4,5]::int[]` |
| Có tag 4 **hoặc** 5 không? | `tag_ids && ARRAY[4,5]::int[]` |
| Mọi tag đều thuộc whitelist? | `tag_ids <@ ARRAY[1,2,4,5]::int[]` |
| Không có tag nào? | `cardinality(tag_ids) = 0` nếu NOT NULL |
| Chỉ có chính xác giá trị mảng đó, đúng thứ tự? | `tag_ids = ARRAY[1,2]::int[]` |
| Đếm tag theo bài? | `cardinality(tag_ids)`, lưu ý duplicates |
| Đếm số bài có mỗi tag? | `unnest` + GROUP BY / hoặc bảng liên kết |

---

## 5. GIN index: ý tưởng inverted index

### 5.1. GIN là gì?

**GIN (Generalized Inverted Index)** lập chỉ mục các **thành phần/key bên trong một giá trị tổng hợp**. Với mảng tags, ta có thể hình dung:

~~~text
posts_array rows
101 -> {1,2,4}
102 -> {1,5,6}
103 -> {2,3}
104 -> {3,4}
105 -> {}
106 -> {1,3,4}

GIN (minh họa logic "phần tử -> danh sách row"):
  tag 1 -> 101, 102, 106
  tag 2 -> 101, 103
  tag 3 -> 103, 104, 106
  tag 4 -> 101, 104, 106
  tag 5 -> 102
  tag 6 -> 102
~~~

Đây là hình dung về **inverted entries/posting lists**, không phải mô tả byte layout của GIN pages. PostgreSQL dùng index tuples/posting lists/posting trees và cơ chế bảo trì của GIN.

### 5.2. Lý do GIN phù hợp cho array membership

Với:

~~~sql
WHERE tag_ids @> ARRAY[1,4]::int[]
~~~

GIN có thể thu thập candidates từ các key 1 và 4 rồi áp điều kiện phù hợp; không nhất thiết phải giải mã mọi mảng của toàn bảng. Với:

~~~sql
WHERE tag_ids && ARRAY[4,5]::int[]
~~~

có thể tìm những rows có ít nhất một key trong tập truy vấn.

Hiệu quả tùy mức phổ biến tag, số elements/row, kích thước bảng, quyền chọn lọc và trạng thái cache.

### 5.3. Operator class array_ops

Để thấy built-in operator class của GIN cho array:

~~~sql
SELECT
    am.amname AS access_method,
    opc.opcname AS operator_class,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
WHERE am.amname = 'gin'
  AND opc.opcname = 'array_ops';
~~~

Core `array_ops` hỗ trợ các array operators quan trọng; với cột mảng bình thường, lệnh:

~~~sql
CREATE INDEX idx_posts_tag_ids_gin
ON array_lab.posts_array
USING gin(tag_ids);
~~~

sẽ chọn opclass GIN phù hợp nếu có mặc định.

### 5.4. GIN không phải UNIQUE index cho phần tử

GIN trên `tag_ids` **không ngăn**:

- Hai bài có cùng tag 1.
- Một bài có `{1,1,2}`.
- Tag ID không tồn tại trong bảng định nghĩa tags.
- Bài có quá nhiều tags.

Chỉ mục tăng tốc tìm kiếm, **không thay thế** PRIMARY KEY, FOREIGN KEY, CHECK và business rules.

### 5.5. Một GIN index có thể phục vụ nhiều truy vấn array

Cùng index `USING gin(tag_ids)` có thể hỗ trợ:

~~~sql
WHERE tag_ids @> ARRAY[1,4]::int[]
WHERE tag_ids && ARRAY[3,5]::int[]
WHERE tag_ids <@ ARRAY[1,2,3,4]::int[]
WHERE tag_ids = ARRAY[1,2]::int[]
~~~

Nhưng “opclass hỗ trợ toán tử” khác với “planner chắc chắn sử dụng index” và “index luôn nhanh”. Với selectivity thấp, Seq Scan có thể thắng.

---

## 6. B-tree index trên mảng có vai trò gì?

### 6.1. B-tree hỗ trợ so sánh toàn bộ giá trị mảng

PostgreSQL hỗ trợ so sánh các array values theo quy tắc của kiểu phần tử và chiều/subscript. Vì vậy trong các trường hợp phù hợp có thể tạo B-tree trên cột array:

~~~sql
CREATE INDEX idx_posts_exact_tag_array
ON array_lab.posts_array USING btree(tag_ids);
~~~

Index này có thể phục vụ **equality của toàn bộ mảng** hoặc yêu cầu thứ tự so sánh theo semantics của array comparator; nó không phải inverted index cho mỗi tag.

### 6.2. B-tree không thay GIN cho "chứa tag"

Một B-tree index trên `tag_ids` **không tự động** đáp ứng hiệu quả:

~~~sql
WHERE tag_ids @> ARRAY[4]::int[]
~~~

vì predicate này hỏi **một phần tử nằm trong giá trị mảng**, không phải so sánh toàn bộ array value với một key nguyên vẹn.

### 6.3. B-tree có thể tốt cho exact canonical array

Nếu ứng dụng chuẩn hóa tags thành một mảng được sort tăng, không trùng, và cần tìm “bài có đúng set thẻ {1,2}”, equality với B-tree có thể là một lựa chọn:

~~~sql
WHERE tag_ids = ARRAY[1,2]::int[]
~~~

Nhưng để equality biểu diễn đúng set equality, cần **canonicalize order và duplicates**; GIN không tự áp quy tắc đó lên dữ liệu.

### 6.4. Expression index cho số lượng thẻ

Nếu workload thường tìm bài không có tag:

~~~sql
WHERE cardinality(tag_ids) = 0
~~~

có thể cân nhắc B-tree trên biểu thức:

~~~sql
CREATE INDEX idx_posts_tag_count
ON array_lab.posts_array ((cardinality(tag_ids)));
~~~

Hoặc partial index trên danh tính bài không có tag:

~~~sql
CREATE INDEX idx_posts_without_tags
ON array_lab.posts_array(post_id)
WHERE cardinality(tag_ids) = 0;
~~~

Hai index này là **hai phương án thử nghiệm**, không bắt buộc tạo cả hai. Chúng phục vụ predicate về **số lượng phần tử**, khác GIN membership. Với bảng chỉ vài hàng, chi phí bổ sung có thể lớn hơn lợi ích.

---

## 7. Bộ dữ liệu lab thống nhất cho mảng và bảng liên kết

Dùng một bộ dữ liệu để so sánh hai mô hình. Mọi ví dụ đều thuộc schema riêng, không chạm bảng nghiệp vụ.

### 7.1. Tạo schema và danh mục tags

~~~sql
CREATE SCHEMA IF NOT EXISTS array_lab;

CREATE TABLE array_lab.tags (
    tag_id INTEGER PRIMARY KEY,
    tag_name TEXT NOT NULL UNIQUE
);

INSERT INTO array_lab.tags(tag_id,tag_name)
VALUES
    (1, 'PostgreSQL'),
    (2, 'SQL'),
    (3, 'Java'),
    (4, 'Performance'),
    (5, 'JSON'),
    (6, 'Array');
~~~

Danh mục tags giúp thấy một hạn chế quan trọng của mảng `int[]`: PostgreSQL không cung cấp **FOREIGN KEY trực tiếp trên từng phần tử mảng** đến `tags(tag_id)` giống với FK trên cột scalar ở bảng liên kết.

### 7.2. Tạo posts dạng mảng

~~~sql
CREATE TABLE array_lab.posts_array (
    post_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    tag_ids INTEGER[] NOT NULL DEFAULT '{}'::integer[],
    CHECK (array_position(tag_ids, NULL) IS NULL)
);
~~~

- `NOT NULL` buộc bản thân cột array không NULL.
- `DEFAULT '{}'::integer[]` biểu diễn bài chưa có tag là mảng rỗng.
- `array_position(tag_ids, NULL) IS NULL` là kiểm tra ngăn **phần tử NULL** trong mảng **một chiều** khi PostgreSQL hỗ trợ hàm này. `array_position` dùng so sánh theo semantics phù hợp để tìm cả phần tử NULL.

**Constraint này không loại trùng phần tử**; mảng `{1,1}` vẫn có thể được chèn nếu không có quy tắc khác.

### 7.3. Nạp sáu bài

~~~sql
INSERT INTO array_lab.posts_array(post_id,title,tag_ids)
VALUES
    (101, 'PostgreSQL căn bản',  ARRAY[1,2,4]),
    (102, 'JSON và mảng',       ARRAY[1,5,6]),
    (103, 'Java kết nối SQL',   ARRAY[2,3]),
    (104, 'Tối ưu Java',        ARRAY[3,4]),
    (105, 'Bài chưa gắn thẻ',   ARRAY[]::integer[]),
    (106, 'Java với PostgreSQL',ARRAY[1,3,4]);

SELECT post_id, title, tag_ids, cardinality(tag_ids) AS tag_count
FROM array_lab.posts_array
ORDER BY post_id;
~~~

Kết quả mong đợi (nếu chạy một lần vào bảng trống):

| post_id | title | tag_ids | Số phần tử |
|---:|---|---|---:|
| 101 | PostgreSQL căn bản | `{1,2,4}` | 3 |
| 102 | JSON và mảng | `{1,5,6}` | 3 |
| 103 | Java kết nối SQL | `{2,3}` | 2 |
| 104 | Tối ưu Java | `{3,4}` | 2 |
| 105 | Bài chưa gắn thẻ | `{}` | 0 |
| 106 | Java với PostgreSQL | `{1,3,4}` | 3 |

### 7.4. Tạo GIN index

~~~sql
CREATE INDEX idx_posts_array_tag_ids_gin
ON array_lab.posts_array USING gin (tag_ids);

ANALYZE array_lab.posts_array;
~~~

Đây là một GIN index phục vụ các toán tử array. `ANALYZE` giúp cập nhật thống kê cho planner, **không ép** query dùng index.

### 7.5. Dữ liệu nhỏ thường chọn Seq Scan

Một bảng sáu hàng thường được truy cập nhanh hơn bằng Seq Scan so với GIN lookup và heap fetch. Vì thế nếu `EXPLAIN` thấy:

~~~text
Seq Scan on posts_array ...
~~~

không được coi là lỗi. Các phần sau sẽ hướng dẫn tạo dữ liệu lớn hơn trong lab riêng và so sánh chi phí thật.

---

## 8. Truy vấn mảng: một tag, nhiều tag, whitelist và bài chưa có tag

### 8.1. Bài có tag PostgreSQL (1)

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1]::integer[]
ORDER BY post_id;
~~~

Kết quả mong đợi: **101, 102, 106**.

### 8.2. Bài có tất cả tags PostgreSQL (1) và Performance (4)

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::integer[]
ORDER BY post_id;
~~~

Kết quả mong đợi: **101, 106**.

### 8.3. Bài có ít nhất một trong các tags JSON (5) hoặc Performance (4)

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids && ARRAY[4,5]::integer[]
ORDER BY post_id;
~~~

Kết quả mong đợi: **101, 102, 104, 106**.

### 8.4. Bài mà tất cả tags đều nằm trong {1,2,4}

~~~sql
SELECT post_id, title, tag_ids
FROM array_lab.posts_array
WHERE tag_ids <@ ARRAY[1,2,4]::integer[]
ORDER BY post_id;
~~~

Kết quả mong đợi: **101, 105**. Bài 105 có mảng rỗng, là subset của whitelist theo semantics containment.

### 8.5. Bài chưa gắn thẻ

~~~sql
SELECT post_id, title
FROM array_lab.posts_array
WHERE cardinality(tag_ids) = 0
ORDER BY post_id;
~~~

Kết quả mong đợi: **105**. Với thiết kế `NOT NULL`, đây là cách biểu diễn ổn định. Không dùng `tag_ids IS NULL` để tìm mảng rỗng.

### 8.6. Bài không có một tag cụ thể

~~~sql
SELECT post_id, title
FROM array_lab.posts_array
WHERE NOT (tag_ids @> ARRAY[4]::integer[])
ORDER BY post_id;
~~~

Nếu mảng không NULL, kết quả mong đợi: **102, 103, 105**. Dạng phủ định này có thể khó sử dụng GIN hiệu quả để bỏ qua phần lớn bảng; cần đo với dữ liệu thật.

### 8.7. Một điểm quan trọng về negative predicates

GIN nổi bật ở việc tìm **một số key có mặt**. “Không chứa tag X” có thể giữ phần lớn rows và thường phải kiểm tra nhiều records. Không mặc định `NOT(tag_ids && ...)` có hiệu quả tương đương `tag_ids && ...`.

---

## 9. Kiểm tra plan cho GIN

### 9.1. EXPLAIN trước khi thực thi

~~~sql
EXPLAIN
SELECT post_id, title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::integer[];
~~~

### 9.2. EXPLAIN ANALYZE, BUFFERS

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT post_id, title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::integer[];
~~~

Một dạng kế hoạch minh họa khi planner dùng GIN:

~~~text
Bitmap Heap Scan on posts_array
  Recheck Cond: (tag_ids @> '{1,4}'::integer[])
  Buffers: shared hit=...
  -> Bitmap Index Scan on idx_posts_array_tag_ids_gin
       Index Cond: (tag_ids @> '{1,4}'::integer[])
~~~

**Không bảo đảm** đúng plan này trên bảng sáu rows. Seq Scan có thể được chọn vì rẻ hơn.

### 9.3. Giải thích từng node

- **Bitmap Index Scan:** tìm các vị trí ứng viên theo GIN.
- **Bitmap Heap Scan:** fetch hàng tương ứng từ heap.
- **Index Cond:** điều kiện được dùng để tìm trong chỉ mục.
- **Recheck Cond:** executor có thể kiểm tra lại predicate khi heap bitmap/cơ chế index yêu cầu.
- **Buffers:** số lần truy cập buffer, không phải số hàng.

### 9.4. Recheck không có nghĩa chỉ mục trả kết quả sai cho ứng dụng

Một cơ chế index hoặc bitmap có thể cung cấp candidates, executor bảo đảm chỉ trả rows thỏa predicate. `Recheck Cond` không tự chứng minh từng candidate đều sai hoặc index bị hỏng. Đọc `Heap Blocks: exact/lossy`, `Rows Removed by Index Recheck` nếu output có, và điều kiện cụ thể.

### 9.5. EXPLAIN ANALYZE thực thi câu lệnh

Với SELECT lab thì phù hợp. Với UPDATE/DELETE:

~~~sql
-- KHÔNG chạy trên production chỉ để "xem kế hoạch":
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM array_lab.posts_array WHERE post_id = 101;
~~~

`ANALYZE` ở đây **thực sự xóa hàng**. Để chỉ xem estimates của DML, dùng `EXPLAIN` không ANALYZE; nếu phải đo DML, dùng transaction kiểm soát trong database thử nghiệm và chú ý những side effects không rollback được.

---

## 10. Từ một post có danh sách tags đến quan hệ nhiều–nhiều

### 10.1. Mô hình chuẩn hóa

Bảng liên kết thể hiện **mỗi cặp post–tag là một row riêng**:

~~~text
posts_rel                 post_tags                 tags
+---------+-------+        +---------+--------+      +--------+-------------+
| post_id | title |        | post_id | tag_id |      | tag_id | tag_name    |
+---------+-------+        +---------+--------+      +--------+-------------+
| 101     | ...   |<-------| 101     | 1      |----->| 1      | PostgreSQL  |
| 102     | ...   |        | 101     | 2      |      | 2      | SQL         |
| ...     | ...   |        | 101     | 4      |      | 4      | Performance |
+---------+-------+        | 102     | 1      |      | ...    | ...         |
                           +---------+--------+      +--------+-------------+
~~~

Đây là quan hệ **many-to-many**: một post có nhiều tags, một tag thuộc nhiều posts.

### 10.2. Tạo posts_rel

~~~sql
CREATE TABLE array_lab.posts_rel (
    post_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL
);
~~~

### 10.3. Tạo post_tags có toàn vẹn tham chiếu

~~~sql
CREATE TABLE array_lab.post_tags (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.posts_rel(post_id)
        ON DELETE CASCADE,
    tag_id INTEGER NOT NULL
        REFERENCES array_lab.tags(tag_id),
    PRIMARY KEY (post_id, tag_id)
);
~~~

Giải thích:

- `post_id` phải tham chiếu post có thật.
- `tag_id` phải tham chiếu tag có thật.
- `PRIMARY KEY(post_id,tag_id)` ngăn **một post gắn cùng tag hai lần**.
- `NOT NULL` đã được PK bao hàm, nhưng viết tường minh giúp chủ ý thiết kế rõ.
- `ON DELETE CASCADE` phía post giúp xóa các liên kết khi xóa post, **không tự xóa tag dictionary**.
- Không mặc định `ON DELETE CASCADE` từ tags nếu nghiệp vụ muốn chặn xóa tag đang được tham chiếu.

### 10.4. Nạp bản liên kết từ dữ liệu mảng lab

~~~sql
INSERT INTO array_lab.posts_rel(post_id,title)
SELECT post_id,title
FROM array_lab.posts_array;
~~~

Mảng trong lab không có duplicates và không có NULL nên có thể:

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
SELECT p.post_id, t.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS t(tag_id);
~~~

**Hai bảng trong lab là hai mô hình để so sánh, không phải khuyến nghị production tự động giữ hai bản copy**. Nếu cần chuyển đổi production, phải xử lý ghi đồng thời và nhất quán.

### 10.5. Index hai chiều

PK `(post_id,tag_id)` tạo B-tree phù hợp với truy vấn “lấy mọi tag của một post”:

~~~sql
SELECT tag_id
FROM array_lab.post_tags
WHERE post_id=101;
~~~

Nhưng query “lấy mọi post có tag 4” sẽ hữu ích nếu có index **đảo chiều**:

~~~sql
CREATE INDEX idx_post_tags_tag_post
ON array_lab.post_tags(tag_id,post_id);
~~~

Index B-tree kép này giúp lọc `tag_id` và lấy `post_id` ngay trong index ở những kế hoạch phù hợp; trong PostgreSQL, index PK theo `(post_id,tag_id)` không tự thay thế hiệu quả cho truy vấn bắt đầu bằng `tag_id` trên bảng liên kết rất lớn.

### 10.6. FK và index là hai việc khác nhau

Tạo FOREIGN KEY **không nhất thiết tự tạo index trên cột FK ở bảng tham chiếu**. PostgreSQL cần index/unique ở phía được tham chiếu theo constraints, nhưng thường nên chủ động tạo index cho phía referencing khi workload đòi tìm/xóa/cập nhật quan hệ liên quan. Với `post_tags`, PK phục vụ `post_id` và `idx_post_tags_tag_post` phục vụ `tag_id`.

---

## 11. Query bảng liên kết: any/all/none

### 11.1. Có tag 1

~~~sql
SELECT p.post_id, p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt
  ON pt.post_id = p.post_id
WHERE pt.tag_id=1
ORDER BY p.post_id;
~~~

Kết quả mong đợi: **101, 102, 106**.

PK `(post_id,tag_id)` đảm bảo cùng một post không có nhiều row cho tag 1; query này không cần DISTINCT chỉ để chữa duplicate link.

### 11.2. Có bất kỳ tag 4 hoặc 5

Dùng `EXISTS` để tránh nhân bản post nếu một post có cả 4 và 5:

~~~sql
SELECT p.post_id, p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id IN (4,5)
)
ORDER BY p.post_id;
~~~

Kết quả mong đợi: **101, 102, 104, 106**.

Nếu dùng `JOIN ... WHERE tag_id IN (4,5)`, một post mang cả hai tag có thể xuất hiện **hai dòng**. Khi đầu ra mong muốn một dòng/post, dùng `EXISTS` hoặc `SELECT DISTINCT` với chi phí/semantics phù hợp.

### 11.3. Có tất cả tag 1 và tag 4

Một cách rõ ràng là hai `EXISTS`:

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id AND pt.tag_id=1
)
AND EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id AND pt.tag_id=4
)
ORDER BY p.post_id;
~~~

Kết quả mong đợi: **101, 106**.

### 11.4. Có đủ một tập tags động

Khi tập cần tìm được chuẩn hóa thành danh sách **distinct non-NULL**:

~~~sql
WITH requested(tag_id) AS (
    VALUES (1), (4)
)
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
JOIN requested AS r
  ON r.tag_id=pt.tag_id
GROUP BY p.post_id,p.title
HAVING COUNT(DISTINCT pt.tag_id) =
       (SELECT COUNT(DISTINCT tag_id) FROM requested)
ORDER BY p.post_id;
~~~

Kết quả mong đợi: **101, 106**. Đây là kỹ thuật *relational division*: “post chứa mọi tag thuộc tập yêu cầu”.

Cần làm rõ khi **tập yêu cầu rỗng**: query này dùng JOIN nên không trả bài nào, trong khi logic `@> '{}'` trên mảng thường đúng cho mọi bài. Nếu cần semantics “vacuous truth”, xử lý riêng tập rỗng hoặc dùng một cấu trúc `NOT EXISTS` phù hợp.

### 11.5. Không có tag 4

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id=4
)
ORDER BY p.post_id;
~~~

Kết quả mong đợi: **102, 103, 105**.

### 11.6. Chưa có tag nào

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
)
ORDER BY p.post_id;
~~~

Kết quả mong đợi: **105**. Đối với mô hình bảng liên kết, **không có hàng liên kết** biểu diễn tập tags rỗng; không cần một row “tag_id=NULL”.

---

## 12. Truy vấn thống kê và tổng hợp theo từng tag

Bài toán thực tế không chỉ là “tìm bài chứa một tag”. Đội sản phẩm còn cần biết tag phổ biến, bài nào có nhiều tag, lần gắn tag gần nhất, thứ tự hiển thị hoặc tỉ lệ đồng xuất hiện giữa hai tag.

### 12.1. Đếm số bài của mỗi tag — mô hình mảng

~~~sql
SELECT
    t.tag_id,
    d.tag_name,
    COUNT(DISTINCT p.post_id) AS posts_count
FROM array_lab.tags AS d
JOIN (
    SELECT p.post_id, u.tag_id
    FROM array_lab.posts_array AS p
    CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
) AS t
    ON t.tag_id=d.tag_id
JOIN array_lab.posts_array AS p
    ON p.post_id=t.post_id
GROUP BY t.tag_id,d.tag_name
ORDER BY posts_count DESC, t.tag_id;
~~~

Lệnh này minh họa `unnest` và `COUNT(DISTINCT post_id)`. Có thể viết gọn hơn:

~~~sql
SELECT
    d.tag_id,
    d.tag_name,
    COUNT(DISTINCT p.post_id) AS posts_count
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
JOIN array_lab.tags AS d
  ON d.tag_id=u.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY posts_count DESC,d.tag_id;
~~~

Nếu mảng có phần tử trùng, `COUNT(*)` sẽ **đếm số lần xuất hiện**, còn `COUNT(DISTINCT p.post_id)` đếm **số bài thực có tag đó**. Đây là khác biệt quan trọng.

### 12.2. Đếm số bài của mỗi tag — mô hình liên kết

~~~sql
SELECT
    d.tag_id,
    d.tag_name,
    COUNT(*) AS posts_count
FROM array_lab.post_tags AS pt
JOIN array_lab.tags AS d
  ON d.tag_id=pt.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY posts_count DESC,d.tag_id;
~~~

Vì `PRIMARY KEY(post_id,tag_id)` không cho duplicate pairs, `COUNT(*)` ở đây tương ứng số bài gắn thẻ. Nếu muốn **hiện cả tag chưa được gắn bài nào**, dùng LEFT JOIN:

~~~sql
SELECT
    d.tag_id,
    d.tag_name,
    COUNT(pt.post_id) AS posts_count
FROM array_lab.tags AS d
LEFT JOIN array_lab.post_tags AS pt
  ON pt.tag_id=d.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY d.tag_id;
~~~

Không dùng `COUNT(*)` cho LEFT JOIN nếu muốn tag không có bài hiển thị 0; LEFT JOIN vẫn tạo một row với columns phía pt là NULL, làm `COUNT(*)` thành 1.

### 12.3. Thống kê số lượng tags trên mỗi post — mảng

~~~sql
SELECT
    post_id,
    title,
    cardinality(tag_ids) AS elements_count
FROM array_lab.posts_array
ORDER BY elements_count DESC,post_id;
~~~

`cardinality` đếm **phần tử**, gồm cả duplicates và NULL nếu chúng tồn tại. Nó không tự đếm số tags distinct.

### 12.4. Thống kê số tags trên mỗi post — bảng liên kết

~~~sql
SELECT
    p.post_id,
    p.title,
    COUNT(pt.tag_id) AS distinct_tags_count
FROM array_lab.posts_rel AS p
LEFT JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
GROUP BY p.post_id,p.title
ORDER BY distinct_tags_count DESC,p.post_id;
~~~

Vì PK cấm trùng cặp post–tag, số rows liên kết bằng số tags distinct. Bài 105 không có liên kết vẫn được tính 0.

### 12.5. Lấy danh sách tag names để hiển thị — mảng

~~~sql
SELECT
    p.post_id,
    p.title,
    COALESCE(
        array_agg(d.tag_name ORDER BY u.ordinality)
            FILTER (WHERE d.tag_id IS NOT NULL),
        '{}'::text[]
    ) AS tag_names
FROM array_lab.posts_array AS p
LEFT JOIN LATERAL unnest(p.tag_ids)
    WITH ORDINALITY AS u(tag_id,ordinality)
    ON true
LEFT JOIN array_lab.tags AS d
    ON d.tag_id=u.tag_id
GROUP BY p.post_id,p.title
ORDER BY p.post_id;
~~~

`WITH ORDINALITY` cho phép giữ thứ tự xuất hiện trong mảng. Nếu tag_id trong mảng không tồn tại ở dictionary, LEFT JOIN tạo tag_name NULL; ví dụ ở đây lọc tag không có dictionary ra khỏi danh sách hiển thị, nhưng **không nên âm thầm bỏ qua orphan IDs trong hệ thống thật** — cần kiểm tra/khắc phục.

### 12.6. Lấy danh sách tag names — bảng liên kết

~~~sql
SELECT
    p.post_id,
    p.title,
    COALESCE(
        array_agg(d.tag_name ORDER BY d.tag_id)
            FILTER (WHERE d.tag_id IS NOT NULL),
        '{}'::text[]
    ) AS tag_names
FROM array_lab.posts_rel AS p
LEFT JOIN array_lab.post_tags AS pt ON pt.post_id=p.post_id
LEFT JOIN array_lab.tags AS d ON d.tag_id=pt.tag_id
GROUP BY p.post_id,p.title
ORDER BY p.post_id;
~~~

Ở đây thứ tự hiển thị do `ORDER BY d.tag_id` quyết định. Bảng liên kết không lưu thứ tự gắn tag theo mặc định; nếu thứ tự do người dùng sắp xếp là một requirement, thêm cột `position` rõ ràng.

### 12.7. So sánh chi phí tổng hợp

Một GIN index trên mảng **không bảo đảm** câu `CROSS JOIN LATERAL unnest(...) GROUP BY` được tăng tốc như một GIN lookup. Khi báo cáo phải xử lý mọi tag của mọi bài, việc mở rộng từng mảng có thể trở thành chi phí chính.

Bảng liên kết có mỗi cặp là một row, chỉ mục `(tag_id,post_id)` và hệ thống thống kê quan hệ thông thường có thể phù hợp hơn cho thống kê theo tag, join dimension tables hoặc các báo cáo nhiều bước.

---

## 13. Mô hình quan hệ: tính toàn vẹn là lợi ích rất lớn

### 13.1. Mảng không có FK cho mỗi phần tử

Giả sử app gửi:

~~~sql
INSERT INTO array_lab.posts_array(post_id,title,tag_ids)
VALUES (201,'Tag không tồn tại',ARRAY[9999]);
~~~

Với schema mảng đang có, câu lệnh **không bị FK với `tags` từ chối** vì không có FK riêng cho từng element. Nếu muốn không cho tag 9999, phải có **validation trong app/trigger/quy trình giao dịch** hoặc mô hình khác.

Trong bảng liên kết:

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
VALUES (101,9999);
~~~

sẽ vi phạm FOREIGN KEY đến `tags(tag_id)` nếu tag 9999 chưa tồn tại. Không cần viết trigger tự tay để phát hiện trường hợp này.

> Hai câu INSERT trên được dùng minh họa. Nếu đã thực thi câu đầu, bản ghi 201 sẽ còn trong lab cho đến khi được dọn; đừng chạy dữ liệu sai rồi dùng nó để so sánh công bằng giữa hai mô hình.

### 13.2. Không có ràng buộc unique-per-element mặc định trong mảng

~~~sql
SELECT ARRAY[1,1,2]::integer[] AS tags_with_duplicates;
~~~

PostgreSQL không tự cấm duplicate elements, và GIN index **không** giải quyết việc đó. Trong `post_tags`, `PRIMARY KEY(post_id,tag_id)` tự ngăn duplicate pairs trong tất cả transactions.

Nếu mảng cần semantics “set”, ứng dụng có thể chuẩn hóa:

~~~sql
SELECT COALESCE(
    array_agg(DISTINCT elem ORDER BY elem),
    '{}'::integer[]
) AS canonical_tags
FROM unnest(ARRAY[2,1,1,4]::integer[]) AS u(elem);
~~~

Kết quả là `{1,2,4}`. Nhưng một truy vấn chuẩn hóa khi đọc **không bảo đảm** mọi writer đã ghi dữ liệu chuẩn; để enforce cần schema/quy trình ghi phù hợp.

### 13.3. Tag deletion và cập nhật metadata

Nếu cần xóa tag 3:

- **Bảng liên kết:** FK có thể chặn delete tag đang được tham chiếu, hoặc bạn có thể chủ động đặt `ON DELETE CASCADE` trên FK tag tùy nghiệp vụ.
- **Mảng ID:** xóa `tags.tag_id=3` không tự phát hiện các mảng đang chứa số 3, trừ cơ chế validation riêng.
- **Mảng tên:** khi tag đổi tên, có thể phải cập nhật một lượng lớn arrays; dictionary + linked IDs chỉ cần UPDATE một dòng tag_name.

Nếu tag có tên, mô tả, ngôn ngữ, người tạo, quyền và trạng thái, một bảng tags riêng thường có giá trị lớn bất kể thiết kế membership nào.

### 13.4. Quan hệ có thuộc tính riêng

Nghiệp vụ có thể cần:

- Ai gắn tag này?
- Gắn lúc nào?
- Tag được hệ thống gợi ý hay người dùng tự chọn?
- Tag có mức ưu tiên hay thứ tự hiển thị?
- Có phải tag chính của bài không?

Bảng liên kết có thể mở rộng:

~~~sql
-- Ví dụ mở rộng schema; chỉ chạy nếu muốn thay đổi lab:
ALTER TABLE array_lab.post_tags
ADD COLUMN assigned_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE array_lab.post_tags
ADD COLUMN assigned_by BIGINT;
~~~

Các thuộc tính **thuộc về cạnh quan hệ post–tag**, không chỉ thuộc post hoặc tag. Đây là dấu hiệu mạnh nên dùng bảng liên kết thay vì cố lưu nhiều mảng song song (tags[], assigned_at[], assigned_by[]) rồi phụ thuộc vị trí index — một thiết kế dễ lệch dữ liệu.

### 13.5. Khi cần thứ tự gắn thẻ

Nếu người dùng muốn sắp xếp tags bằng kéo–thả, bảng liên kết có thể thêm:

~~~sql
ALTER TABLE array_lab.post_tags
ADD COLUMN display_order INTEGER;
~~~

Và constraint phù hợp khi business yêu cầu. Cần quyết định liệu một tag có thể xuất hiện nhiều lần hay không. Với PK(post_id,tag_id), tag vẫn chỉ xuất hiện một lần; thứ tự do display_order lưu riêng.

---

## 14. Thay đổi dữ liệu: UPDATE mảng vs INSERT/DELETE liên kết

### 14.1. Thêm tag vào mảng

Ví dụ thêm tag 5 cho bài 103, tránh thêm nếu đã có:

~~~sql
UPDATE array_lab.posts_array
SET tag_ids = array_append(tag_ids,5)
WHERE post_id=103
  AND NOT (tag_ids @> ARRAY[5]::integer[]);
~~~

Đây là một UPDATE một row. Nó tạo **row version mới theo MVCC** và có thể cần duy trì GIN index vì giá trị cột indexed array thay đổi.

### 14.2. Xóa tag trong mảng

~~~sql
UPDATE array_lab.posts_array
SET tag_ids = array_remove(tag_ids,5)
WHERE post_id=103;
~~~

`array_remove` loại **tất cả lần xuất hiện** của phần tử đó. Nếu mảng chứa duplicate tag IDs, một lệnh có thể xóa nhiều occurrences.

### 14.3. Thêm tag ở bảng liên kết

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
VALUES (103,5)
ON CONFLICT (post_id,tag_id) DO NOTHING;
~~~

Với PK phù hợp, thao tác này có thể idempotent theo cặp: lặp lại không chèn thêm duplicate.

### 14.4. Xóa tag ở bảng liên kết

~~~sql
DELETE FROM array_lab.post_tags
WHERE post_id=103 AND tag_id=5;
~~~

Thao tác ảnh hưởng **một cặp** nhờ PK, không phải ghi lại danh sách tags của toàn post.

### 14.5. Tránh hiểu nhầm hành vi khi chạy mẫu

Hai mô hình lab được dùng để **so sánh**, không có trigger/dual-write tự đồng bộ. Nếu chạy UPDATE mảng rồi INSERT/DELETE liên kết không đồng bộ, chúng sẽ khác nhau. Khi làm bài kiểm tra kết quả “hai mô hình tương đương”, hãy giữ dữ liệu mẫu ban đầu hoặc thực hiện thay đổi nhất quán ở cả hai phía trong lab.

### 14.6. Concurrency: read-modify-write ở application có thể mất cập nhật

Ví dụ hai users cùng đọc `tag_ids={1,2}`, người A thêm 3, người B thêm 4:

~~~text
A đọc {1,2}                  B đọc {1,2}
A tính {1,2,3}               B tính {1,2,4}
A UPDATE tag_ids={1,2,3}     B UPDATE tag_ids={1,2,4}
                       -> Có nguy cơ mất tag 3
~~~

Nếu mỗi client ghi đè toàn bộ giá trị tính từ bản đọc cũ, lần ghi sau có thể làm mất thay đổi của lần trước (*lost update* ở tầng ứng dụng). Phải dùng concurrency control phù hợp:

- Một câu `UPDATE SET tag_ids=array_append(tag_ids,...)` với condition phù hợp thay vì app ghi đè snapshot đã cũ.
- Row locking/version column/optimistic concurrency khi cần.
- Transaction và xử lý retry serialization errors đúng cách.

Trong bảng liên kết, hai transactions chèn **hai cặp khác nhau** thường không cần thay thế một field chứa toàn bộ danh sách. Tuy nhiên vẫn cần xử lý constraint/conflict và các quy tắc nghiệp vụ liên quan.

### 14.7. Chi phí update trên bảng lớn

Đối với một post chứa hàng nghìn tags, thêm một tag vào cột mảng có thể tạo giá trị mảng mới, thay đổi TOAST storage và GIN index entries. Trong bảng liên kết, thường chỉ thêm một row nhỏ cùng indexes liên quan.

Điều đó **không có nghĩa bảng liên kết luôn ít I/O hơn**: bảng liên kết có thêm heap rows, index pages, joins và FK checks. Cần benchmark theo số phần tử và tần suất update.

---

## 15. MVCC, HOT, TOAST và viết lại mảng lớn

### 15.1. MVCC không chỉnh sửa trực tiếp một array value ở chỗ cũ

Trong PostgreSQL, UPDATE tạo row version theo MVCC. Vì thế ngay cả khi code chỉ thay một phần tử logic trong array, PostgreSQL vẫn xử lý một giá trị array mới ở row version tương ứng, không phải thao tác sửa một ô “con” như một bảng quan hệ có từng row tag.

### 15.2. HOT updates và indexed columns

**HOT (Heap-Only Tuple) update** có thể giảm index maintenance khi đủ điều kiện, đáng chú ý là không thay đổi những cột được index tham chiếu và còn chỗ trong page phù hợp.

Nếu `tag_ids` có GIN index và bị thay đổi, UPDATE thường không đủ điều kiện HOT theo tiêu chí indexed-column-change. Điều này làm chi phí ghi tăng khi mảng cập nhật thường xuyên.

Nếu chỉ UPDATE `title` còn `tag_ids` không đổi, cơ hội HOT còn phụ thuộc các indexes khác, page space và điều kiện executor/storage.

### 15.3. TOAST cho array lớn

Mảng là giá trị có độ dài biến đổi. Khi array rất lớn, PostgreSQL có thể nén hoặc lưu giá trị theo **TOAST**, tùy cấu hình và kiểu storage.

Hệ quả:

- Fetch toàn bộ array có thể cần đọc/giải nén TOAST data.
- UPDATE thay đổi array lớn có thể tạo dữ liệu TOAST mới.
- VACUUM phải xử lý dead tuples và phiên bản dữ liệu cũ.
- WAL/replication bandwidth có thể tăng.

Không đặt một danh sách không giới hạn thành array chỉ vì “một cột gọn hơn nhiều bảng”.

### 15.4. Bảng liên kết cũng có MVCC và maintenance

`INSERT/DELETE` trên `post_tags` vẫn sinh WAL, index changes và dead tuples (với DELETE); VACUUM và các chỉ mục B-tree vẫn có chi phí. Nhưng cập nhật một quan hệ post–tag **không bắt buộc** ghi lại toàn bộ tập tags của post như thay đổi array column.

### 15.5. Dữ liệu read-mostly vs write-heavy

| Workload | Cột mảng | Bảng liên kết |
|---|---|---|
| Ít tag/post, hiếm thay đổi | Có thể gọn và tiện đọc | Thêm joins/rows nhưng toàn vẹn tốt |
| Tag/post rất lớn | TOAST, index/update pressure | Nhiều rows/index pages nhưng cập nhật từng cặp |
| Nhiều người đồng thời thêm/xóa tag của cùng post | Row contention và read-modify-write cần kiểm soát | Giao dịch trên cặp riêng, PK/FK hỗ trợ |
| Đọc tất cả tags của một post | Một array fetch có thể đơn giản | Scan B-tree theo post_id, aggregate khi cần |
| Tìm tất cả posts có một tag | GIN membership | B-tree `(tag_id,post_id)` |
| Thống kê/report nhiều chiều | Có thể cần unnest nhiều | Mỗi quan hệ là row, tự nhiên cho JOIN/GROUP BY |
| Tag metadata, FK, permission | Cần quy trình phụ | FK/joins rất phù hợp |
| Yêu cầu thứ tự tags | Array lưu thứ tự tự nhiên | Cần cột position riêng |

---

## 16. Chi phí đọc: fetch một post và lọc ngược theo tag là hai bài toán khác nhau

### 16.1. Lấy toàn bộ tags của một post

~~~sql
SELECT tag_ids
FROM array_lab.posts_array
WHERE post_id=101;
~~~

Primary key trên `post_id` lọc đúng một row rồi lấy một array. Với vài tags, cách này rất thuận tiện.

Bảng liên kết:

~~~sql
SELECT tag_id
FROM array_lab.post_tags
WHERE post_id=101
ORDER BY tag_id;
~~~

PK `(post_id,tag_id)` hỗ trợ truy vấn theo post_id và trả danh sách tag IDs theo thứ tự tag_id khi planner thấy phù hợp.

### 16.2. Lọc mọi post có một tag

Cột mảng:

~~~sql
SELECT post_id
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[4]::int[];
~~~

Bảng liên kết:

~~~sql
SELECT post_id
FROM array_lab.post_tags
WHERE tag_id=4;
~~~

GIN và B-tree inverted `(tag_id,post_id)` là hai index structures khác nhau, đều có thể phục vụ reverse lookup. Nếu chỉ cần post IDs, B-tree index phía liên kết có thể cung cấp giá trị trực tiếp, nhưng **index-only scan** còn phụ thuộc visibility map; nếu cần title, cần join/fetch bảng posts.

### 16.3. Một tag quá phổ biến

Nếu 90% posts chứa tag “SQL”, query theo SQL có thể phải trả hầu hết posts:

- GIN phải xử lý posting lists/candidates lớn và heap fetch.
- B-tree tag_post cũng phải duyệt rất nhiều liên kết và có thể JOIN nhiều rows.
- Seq Scan/Hash Join có thể được planner chọn vì rẻ hơn nhiều index lookups.

“Có index” **không làm lượng dữ liệu đầu ra nhỏ lại**. Với tags phổ biến, API nên xem pagination, aggregate và cache nếu phù hợp.

### 16.4. Một tag rất hiếm

Nếu chỉ 0,01% posts chứa tag cụ thể, GIN array membership hoặc B-tree linked lookup có thể giảm đáng kể lượng rows phải xét.

### 16.5. Query nhiều tags

Với tìm “có tất cả 10 tags”, GIN có thể phối hợp các keys trong inverted structure. Bảng liên kết có thể dùng GROUP BY/HAVING, nhiều EXISTS hoặc JOIN. Cái nào nhanh hơn phụ thuộc số tags yêu cầu, selectivity mỗi tag, độ dài postings, số rows và khả năng tận dụng statistics.

---

## 17. Giải bài toán “có tất cả tags” bằng relational division

### 17.1. Array biểu diễn trực tiếp

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,3,4]::int[];
~~~

Kết quả mong đợi: **106**.

### 17.2. Join + GROUP BY/HAVING

~~~sql
SELECT
    p.post_id,
    p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
WHERE pt.tag_id IN (1,3,4)
GROUP BY p.post_id,p.title
HAVING COUNT(DISTINCT pt.tag_id)=3;
~~~

Kết quả mong đợi: **106**.

Công thức đếm bằng 3 chỉ đúng khi tập yêu cầu có **ba tag IDs khác nhau** và bảng liên kết không có dữ liệu NULL theo schema.

### 17.3. Nhiều EXISTS có thể dễ đọc với tập cố định nhỏ

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS x
    WHERE x.post_id=p.post_id AND x.tag_id=1
)
AND EXISTS (
    SELECT 1 FROM array_lab.post_tags AS x
    WHERE x.post_id=p.post_id AND x.tag_id=3
)
AND EXISTS (
    SELECT 1 FROM array_lab.post_tags AS x
    WHERE x.post_id=p.post_id AND x.tag_id=4
);
~~~

Planner có thể chuyển đổi thành các chiến lược semi-join/index lookup phù hợp. **Không kết luận một query luôn nhanh hơn** chỉ từ độ dài SQL.

### 17.4. Cách logic tổng quát với NOT EXISTS lồng nhau

Tìm bài sao cho **không tồn tại tag yêu cầu nào mà bài đó chưa có**:

~~~sql
WITH requested(tag_id) AS (
    VALUES (1),(3),(4)
)
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM requested AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
          AND pt.tag_id=r.tag_id
    )
)
ORDER BY p.post_id;
~~~

Cách này có đặc tính quan trọng: nếu `requested` **rỗng**, “không có tag nào bị thiếu” là TRUE cho **mọi bài**, tương ứng semantics containment với mảng rỗng cho các mảng không NULL.

Tuy nhiên optimizer và execution strategy vẫn tùy dataset; phải benchmark.

### 17.5. Tính đúng trước tối ưu

Nếu input array yêu cầu có duplicates:

~~~text
requested = [1,1,4]
~~~

`@>` không xem multiplicity là hai lần tag 1. Bảng liên kết cần normalize requested với DISTINCT trước khi so `COUNT = number_requested`; nếu dùng `COUNT(*)=3` theo danh sách có lặp, query có thể cho kết quả sai.

---

## 18. Phụ thuộc dữ liệu và cập nhật dictionary

### 18.1. Đổi tên tag

~~~sql
UPDATE array_lab.tags
SET tag_name='Postgres'
WHERE tag_id=1;
~~~

Khi cả mô hình mảng và liên kết dùng **tag IDs**, đổi tên trong dictionary không cần UPDATE tất cả `posts_array.tag_ids` hoặc `post_tags`. Ưu thế của bảng liên kết không phải “mảng ID không thể có dictionary”, mà là **có thể dùng FK** để bảo đảm IDs thật sự hợp lệ.

### 18.2. Xóa tag

Trong linked model, xóa tag đang được tham chiếu bị ràng buộc bởi FK nếu không cấu hình cascade khác. Trong array model, database không có FK trực tiếp kiểm tra từng ID, nên có thể tạo **orphan references**.

Kiểm tra orphan IDs trên array:

~~~sql
SELECT DISTINCT
    p.post_id,
    u.tag_id AS missing_tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
LEFT JOIN array_lab.tags AS d
  ON d.tag_id=u.tag_id
WHERE d.tag_id IS NULL
ORDER BY p.post_id,missing_tag_id;
~~~

Nếu dữ liệu trong lab thuần mẫu, query dự kiến không có hàng. Đây là **audit query**, không phải constraint ngăn lỗi tại lúc ghi.

### 18.3. Xóa một post

Với linked model, FK `ON DELETE CASCADE` trên `post_tags.post_id` có thể tự xóa liên kết khi xóa post, theo transaction. Với array model, tag_ids nằm trong row post nên biến mất cùng row; nhưng dictionary tag vẫn còn.

### 18.4. Metadata trên quan hệ

Nếu người dùng có thể gắn tag với `confidence_score`, `assigned_by` hoặc `assigned_at`, bảng liên kết là nơi tự nhiên lưu thêm các thuộc tính này. Mô hình mảng chỉ chứa tag IDs sẽ phải cấu trúc dữ liệu phức tạp hơn và có thể khó enforce từng phần tử.

---

## 19. Thứ tự, duplicate tags và ranh giới giữa list/set/relation

### 19.1. Ba ngữ nghĩa khác nhau

| Nghiệp vụ | Cần biểu diễn | Thiết kế khả thi |
|---|---|---|
| Một post có **tập tag duy nhất, không thứ tự** | Quan hệ post–tag | Junction PK(post_id,tag_id); hoặc array canonical |
| Một playlist có **các bài theo thứ tự** | Danh sách có thứ tự, có thể lặp | Junction với position/item_id hoặc array nếu nhỏ và ít update |
| Một đơn hàng có **mỗi sản phẩm với số lượng, đơn giá** | Các dòng nghiệp vụ riêng | `order_items`, **không** dùng mảng product_ids đơn thuần |

### 19.2. Bảng liên kết có thể có thứ tự

Nếu tags là một danh sách có thứ tự:

~~~sql
-- Minh họa thiết kế khác, không cần thay đổi bảng post_tags lab:
CREATE TABLE array_lab.post_tag_positions (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.posts_rel(post_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL
        REFERENCES array_lab.tags(tag_id),
    position INTEGER NOT NULL CHECK (position >= 1),
    PRIMARY KEY (post_id,tag_id),
    UNIQUE (post_id,position)
);
~~~

Quy tắc trên bảo đảm mỗi post có tối đa một tag một lần và không có hai tags ở cùng position. Nó **không tự đảm bảo vị trí liên tục** 1,2,3... khi xóa/sửa; app hoặc procedure phải quản lý.

### 19.3. Với phần tử lặp có ý nghĩa

Nếu một danh sách cho phép cùng item xuất hiện nhiều lần, `PRIMARY KEY(post_id,tag_id)` không còn đúng. Có thể dùng `item_id` riêng hoặc PK(post_id,position) và FK tag_id. Mô hình phải đi từ **quy tắc nghiệp vụ**, không lấy cấu trúc đã chọn rồi ép dữ liệu.

### 19.4. Đừng dùng thứ tự ngầm của SQL rows

Một bảng liên kết không bảo đảm SELECT trả rows theo thứ tự INSERT nếu không có `ORDER BY`. Mảng có thứ tự phần tử, còn trong bảng bạn phải lưu/order bằng một khóa xác định khi thứ tự quan trọng.

---

## 20. JSONB array khác SQL array như thế nào?

Vì chương lớn là **JSON và mảng**, cần phân biệt ba kiểu:

| Đặc tính | `integer[]` / `text[]` | `jsonb` chứa array | Bảng liên kết |
|---|---|---|---|
| Kiểu phần tử | Cùng một SQL data type | JSON values (có thể trộn kiểu) | Được định nghĩa theo cột, có FK |
| Mảng rỗng | `'{}'::int[]` | `'[]'::jsonb` | Không có link rows |
| Truy vấn containment | Array `@>` | JSONB `@>` với semantics JSONB | JOIN/EXISTS |
| Toán tử overlap `&&` | Có trên SQL array | Không phải toán tử JSONB mặc định tương đương | `IN`/EXISTS |
| GIN opclass | `array_ops` | `jsonb_ops` hoặc `jsonb_path_ops` | B-tree liên kết |
| Referential integrity từng phần tử | Không có FK trực tiếp | Không có FK trực tiếp | Có FK |
| Metadata gắn với từng link | Khó lưu/tự kiểm soát | Linh hoạt cấu trúc nhưng khó relational constraints | Tự nhiên |
| Truy vấn báo cáo nhiều chiều | `unnest` | JSONB expansion functions | SQL joins/grouping |
| Cập nhật một liên kết | UPDATE array value | UPDATE JSONB value | INSERT/DELETE một row |

### 20.1. SQL array containment

~~~sql
SELECT ARRAY[1,2]::int[] @> ARRAY[2]::int[] AS sql_array_contains;
~~~

### 20.2. JSONB containment có toán tử trùng ký hiệu nhưng khác kiểu

~~~sql
SELECT '[1,2]'::jsonb @> '[2]'::jsonb
       AS jsonb_array_contains;
~~~

Hai toán tử đều viết `@>` nhưng **operator implementation, opclass, kiểu dữ liệu và quy tắc matching** khác nhau. Không chuyển trực tiếp `array_ops` sang cột JSONB.

### 20.3. JSONB document có trường tags

~~~sql
CREATE TABLE array_lab.posts_jsonb (
    post_id BIGINT PRIMARY KEY,
    doc JSONB NOT NULL
);

INSERT INTO array_lab.posts_jsonb(post_id,doc)
VALUES
    (101,'{"title":"PostgreSQL căn bản","tags":["PostgreSQL","SQL","Performance"]}'::jsonb),
    (102,'{"title":"JSON và mảng","tags":["PostgreSQL","JSON","Array"]}'::jsonb);

CREATE INDEX idx_posts_jsonb_doc
ON array_lab.posts_jsonb USING gin(doc);
~~~

Query:

~~~sql
SELECT post_id
FROM array_lab.posts_jsonb
WHERE doc @> '{"tags":["PostgreSQL"]}'::jsonb;
~~~

Ở đây GIN built-in trên JSONB có operator classes khác với GIN array. Một cấu trúc JSONB linh hoạt có thể phù hợp dữ liệu document không cố định, nhưng nếu tags là quan hệ nghiệp vụ cần FK, uniqueness và báo cáo nhiều chiều, bảng liên kết vẫn có ưu thế.

### 20.4. JSONB key existence khác array membership

Toán tử JSONB `?` có semantics key/top-level string-array element existence với những hình thức JSONB phù hợp:

~~~sql
SELECT post_id
FROM array_lab.posts_jsonb
WHERE (doc -> 'tags') ? 'PostgreSQL';
~~~

Index toàn `doc` không tự đảm bảo predicate `(doc->'tags') ? ...` tận dụng đúng index expression; nếu workload truy vấn expression này nhiều, cần cân nhắc GIN expression index riêng:

~~~sql
CREATE INDEX idx_posts_jsonb_tags_expr
ON array_lab.posts_jsonb
USING gin ((doc -> 'tags'));
~~~

Đây là ví dụ khác về **index phải khớp predicate và expression**, không đơn giản “cột có GIN là mọi JSON operator đều nhanh”.

### 20.5. Khi nào JSONB là ứng viên?

- Payload/schema biến đổi liên tục, không cần JOIN/FK trên từng thành phần.
- Lưu document để trao đổi với ứng dụng bên ngoài.
- Nhiều thuộc tính optional lồng nhau.
- Có yêu cầu query bằng JSONB containment/path operators.

Nếu chỉ muốn một tập mã tag integer, SQL `integer[]` rõ type hơn. Nếu muốn quan hệ nhiều–nhiều có FK và metadata, bảng liên kết thường là mô hình nền tảng tốt hơn.

---

## 21. GIN pending list và tác động đến write throughput

### 21.1. GIN lưu inverted entries, không chỉ một key mỗi row

Một post có 30 tags có thể đóng góp nhiều index keys/posting entries cho GIN. Việc chèn hoặc thay đổi mảng lớn có chi phí khác với B-tree một key scalar.

### 21.2. fastupdate

GIN hỗ trợ tùy chọn `fastupdate` để các index entries mới đi qua **pending list** rồi được hợp nhất vào cấu trúc index chính. Điều này có thể giúp chi phí INSERT hàng ngày, nhưng pending list lớn có thể gây:

- Một số query phải xét cả main index và pending entries.
- Dọn pending list tốn CPU/I/O, tạo spikes.
- VACUUM hoặc một đợt cleanup chịu chi phí cao.
- Biến động latency khi workload ghi dồn dập.

### 21.3. Kiểm tra cấu hình

~~~sql
SHOW gin_pending_list_limit;
~~~

Ở mức index, có thể cấu hình storage parameters trong quá trình tạo/ALTER INDEX khi có quyền:

~~~sql
CREATE INDEX idx_posts_array_tags_gin_tuned
ON array_lab.posts_array
USING gin(tag_ids)
WITH (fastupdate=on);
~~~

Đây là **một index thử nghiệm thay thế**, không cần tạo thêm nếu đã có index GIN tương đương. Mục tiêu chỉ minh họa `fastupdate`, không khuyến nghị giữ hai GIN indexes cùng chức năng.

### 21.4. fastupdate off không luôn nhanh hơn

Tắt fastupdate có thể làm INSERT phải cập nhật GIN main structure trực tiếp, tăng chi phí write mỗi statement. Bật fastupdate có thể làm query/cleanup gặp overhead. Lựa chọn tùy:

- Số elements per row.
- Tần suất INSERT/UPDATE.
- Query read latency yêu cầu.
- Autovacuum/maintenance lịch.
- Hạ tầng storage/WAL/replication.

**Không tự thay đổi toàn production để xử lý một lần query chậm** nếu chưa đo và có runbook.

### 21.5. VACUUM và GIN cleanup

Autovacuum/VACUUM xử lý dead tuples và tham gia bảo trì GIN pending list theo cơ chế PostgreSQL. Nếu dữ liệu nhiều DELETE/UPDATE, việc xem VACUUM lag, dead tuples và index bloat quan trọng không kém query plans.

### 21.6. Đừng tắt autovacuum để “tránh GIN bị chậm”

Tắt autovacuum lâu dài có thể làm dead tuples tích tụ và dẫn đến rủi ro MVCC/XID. Khi GIN pending list trở thành bottleneck, cần kiểm tra nguyên nhân, thiết kế index và lịch maintenance, không xóa một thành phần an toàn nền tảng.

---

## 22. Giám sát truy vấn với mảng: EXPLAIN, BUFFERS và thống kê

### 22.1. Plan dùng GIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids && ARRAY[1,5]::int[];
~~~

Tìm:

- `Bitmap Index Scan` trên GIN hay `Seq Scan`.
- `Index Cond` có đúng `&&`/`@>` không?
- `actual rows` so với `estimated rows`.
- `Buffers: shared hit/read` và temp.
- `Rows Removed by Index Recheck` nếu xuất hiện.
- `Execution Time` tổng.

### 22.2. Plan dùng B-tree của bảng liên kết

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id=1
);
~~~

Tìm:

- Có `Index Scan`/`Index Only Scan` trên `idx_post_tags_tag_post` không?
- `Nested Loop`, `Hash Semi Join` hay chiến lược khác?
- Có nhiều heap fetch từ bảng posts không?
- `actual rows`, `loops` và fan-out.

### 22.3. Không cộng buffer/time ở node cha và node con

Buffers/time ở parent thường **bao gồm** công việc của child. Không cộng `Hash Join actual time` + `Seq Scan actual time` + `Index Scan actual time` để suy ra tổng thời gian query; dùng `Execution Time` và xem nhánh con để tìm chi phí.

### 22.4. Thống kê sử dụng index

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname='array_lab'
ORDER BY relname,indexrelname;
~~~

Đây là counters có vòng đời/reset, không chứng minh một index vô ích chỉ vì `idx_scan=0` ngay sau khi tạo.

### 22.5. Dung lượng index

~~~sql
SELECT
    c.oid::regclass AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
    pg_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='array_lab'
  AND c.relkind IN ('i','I')
ORDER BY bytes DESC,index_name::text;
~~~

Một GIN index lớn không nhất thiết chậm hơn B-tree index nhỏ; cần xét query behavior, write overhead và total footprint, kể cả heap/TOAST/link rows.

---

## 23. Benchmark đúng cách: so hai mô hình cùng dữ liệu

### 23.1. Vì sao lab sáu bài không đủ để kết luận?

Bảng sáu hàng có thể Seq Scan nhanh hơn GIN; bảng liên kết thêm join có thể có overhead trong vài microseconds. Kết quả này **không ngoại suy** sang hàng triệu posts với mỗi post có 20–100 tags.

Cần đo trên kích thước và phân bố đại diện, không chỉ nhìn schema gọn hơn.

### 23.2. Tạo dữ liệu synthetic độc lập

Phần này **tùy chọn**; chỉ dùng khi database lab có đủ CPU, disk và thời gian. Bảng này không thay đổi sáu posts mẫu và không dùng FK tags 1..6.

~~~sql
CREATE TABLE array_lab.big_posts (
    post_id BIGINT PRIMARY KEY,
    tag_ids INTEGER[] NOT NULL
);

INSERT INTO array_lab.big_posts(post_id,tag_ids)
SELECT
    g::bigint,
    ARRAY[
        1 + (g % 101),
        1 + ((g / 7) % 101),
        1 + ((g / 37) % 101)
    ]::integer[]
FROM generate_series(1,50000) AS g;
~~~

Mỗi row có ba **vị trí phần tử**; vì công thức có thể cho trùng tag IDs ở một row, không được coi `cardinality(tag_ids)=3` đồng nghĩa ba distinct tags.

### 23.3. Tạo GIN index

~~~sql
CREATE INDEX idx_big_posts_tags_gin
ON array_lab.big_posts USING gin(tag_ids);

ANALYZE array_lab.big_posts;
~~~

### 23.4. Tạo linked data tương ứng

~~~sql
CREATE TABLE array_lab.big_post_tags (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.big_posts(post_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (post_id,tag_id)
);

INSERT INTO array_lab.big_post_tags(post_id,tag_id)
SELECT DISTINCT p.post_id,u.tag_id
FROM array_lab.big_posts AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id);

CREATE INDEX idx_big_post_tags_reverse
ON array_lab.big_post_tags(tag_id,post_id);

ANALYZE array_lab.big_post_tags;
~~~

`DISTINCT` loại cặp trùng do synthetic array có thể trùng phần tử. Không tạo FK đến dictionary `array_lab.tags` vì dữ liệu synthetic dùng tag_id 1..101, trong khi dictionary mẫu chỉ có 1..6.

### 23.5. So query “có tag 17”

Cột mảng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_posts
WHERE tag_ids @> ARRAY[17]::integer[];
~~~

Bảng liên kết:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_post_tags
WHERE tag_id=17;
~~~

Vì `big_post_tags` có PK theo cặp, mỗi post xuất hiện tối đa một lần với tag 17, nên cả hai query đếm cùng ý nghĩa. Dữ liệu synthetic không có NULL arrays.

### 23.6. So query “có bất kỳ tag 17 hoặc 32”

Mảng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_posts
WHERE tag_ids && ARRAY[17,32]::integer[];
~~~

Liên kết:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(DISTINCT post_id)
FROM array_lab.big_post_tags
WHERE tag_id IN (17,32);
~~~

`DISTINCT` ở phía liên kết là cần thiết vì một post có thể có **cả 17 và 32**, tạo hai rows trong kết quả lọc. Bỏ DISTINCT sẽ đổi ý nghĩa đếm posts sang đếm links.

### 23.7. So query “có cả tag 17 và 32”

Mảng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM array_lab.big_posts
WHERE tag_ids @> ARRAY[17,32]::integer[];
~~~

Liên kết:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM (
    SELECT post_id
    FROM array_lab.big_post_tags
    WHERE tag_id IN (17,32)
    GROUP BY post_id
    HAVING COUNT(*)=2
) AS matching_posts;
~~~

`COUNT(*)=2` đúng ở đây vì requested set gồm đúng hai tag IDs phân biệt, PK ngăn duplicate links, filter chỉ lấy hai tags. Nếu requested inputs có duplicates, phải DISTINCT trước.

### 23.8. So total storage chứ không chỉ index size

Mảng có array values trong bảng posts và GIN index. Liên kết có:

- Bảng posts.
- Bảng post_tags với nhiều rows.
- PK(index) trên `(post_id,tag_id)`.
- Reverse index trên `(tag_id,post_id)`.
- Các FK checks và WAL/index maintenance.

So tổng:

~~~sql
SELECT
    'array_big_posts' AS design,
    pg_total_relation_size('array_lab.big_posts'::regclass) AS bytes
UNION ALL
SELECT
    'linked_big_post_tags',
    pg_total_relation_size('array_lab.big_post_tags'::regclass);
~~~

**So sánh này chưa tính** common posts metadata ở một bên tương ứng và khác biệt row storage; cần tính đầy đủ các relations liên quan khi benchmark production. Không dùng hai số này như toàn bộ chi phí của hai kiến trúc.

### 23.9. Đo nhiều loại workload

| Truy vấn/công việc | Cần đo |
|---|---|
| Một tag rất hiếm | Latency p50/p95, buffers |
| Một tag phổ biến | Output size, seq vs index |
| ANY 2–10 tags | Index/postings vs JOIN DISTINCT |
| ALL 2–10 tags | GIN containment vs aggregation/semi-joins |
| Lấy toàn bộ tags của một post | Array fetch vs linked ordered scan |
| Đếm bài theo tag | Unnest/group vs indexed join/group |
| Thêm/xóa một tag | UPDATE array vs INSERT/DELETE link |
| Xóa một post | Index/TOAST vs FK cascade |
| Cập nhật tên tag | Dictionary-only hoặc mass array rewrite |
| Batch import lớn | WAL, pending cleanup, index size |
| VACUUM/reindex | Thời gian bảo trì, disk headroom |

### 23.10. Cache và concurrency

Query chạy lần đầu có thể chậm vì cache lạnh, lần sau nhanh vì data đã vào cache. Đừng kết luận mảng thắng chỉ vì benchmark nó **sau** liên kết. Hoán đổi thứ tự, đo nhiều lần và xem concurrency/write load thực.

---

## 24. Giữ nhất quán khi nhiều clients cùng thay đổi tags

### 24.1. Bài toán đồng thời

Giả sử hai transactions cùng gắn một tag cho bài 101. Mục tiêu nghiệp vụ là “một post–tag chỉ tồn tại một lần”.

Trong mô hình liên kết:

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
VALUES (101,5)
ON CONFLICT (post_id,tag_id) DO NOTHING;
~~~

`PRIMARY KEY(post_id,tag_id)` bảo đảm uniqueness ở tầng database ngay cả khi hai clients chạy đồng thời. Một transaction có thể chờ transaction kia tại unique-index conflict, sau đó xử lý theo isolation/ON CONFLICT semantics.

Trong mô hình mảng, nếu hai clients cùng append 5 mà không có kiểm tra/khóa phù hợp, `{1,2,4,5,5}` có thể xuất hiện. Cần chủ động enforce set semantics.

### 24.2. “Đọc rồi kiểm tra rồi UPDATE” có race

Một code flow:

~~~text
SELECT tag_ids ...
if (5 not in tag_ids):
    UPDATE tag_ids = previous_tags_plus_5
~~~

có thể bị race/lost update nếu hai clients dùng bản sao đã đọc trước khi ghi. Đây là vấn đề giao dịch, không phải do GIN index hoạt động sai.

Một biến thể SQL tập trung việc kiểm tra vào UPDATE:

~~~sql
UPDATE array_lab.posts_array
SET tag_ids = array_append(tag_ids,5)
WHERE post_id=101
  AND NOT (tag_ids @> ARRAY[5]::integer[]);
~~~

có thể giúp tránh nhiều trường hợp app read-modify-write, nhưng **không tự thay thế** mọi yêu cầu concurrency/uniqueness/ordering phức tạp. Với isolation level phù hợp, PostgreSQL có thể chờ, reevaluate điều kiện hay trả lỗi cần retry. Hãy thiết kế và kiểm thử theo transaction semantics cụ thể.

### 24.3. Giới hạn số tags/post

Với cột mảng, một constraint đơn giản có thể được đặt:

~~~sql
ALTER TABLE array_lab.posts_array
ADD CONSTRAINT chk_posts_max_20_tags
CHECK (cardinality(tag_ids) <= 20);
~~~

Dòng này dễ kiểm tra vì toàn bộ tập tags nằm trong một row.

Trong bảng liên kết, ràng buộc “một post tối đa 20 tags” liên quan **số hàng con**, không thể viết một CHECK thông thường trên một row `post_tags` để tự đếm các hàng khác. Cần logic transaction/stored procedure/trigger/locking phù hợp nếu business thật sự đòi invariant ở tầng DB.

### 24.4. Không dùng chỉ CHECK trên cột array để xác nhận FK

Một CHECK chỉ dùng các biểu thức row-local không thể đơn giản tham chiếu mọi hàng của dictionary `tags` như một SQL FOREIGN KEY đa phần tử. Dùng hàm/trigger tùy biến để dò dictionary là khả thi trong một số hệ thống, nhưng phải thiết kế đúng concurrency, snapshot, quyền, thay đổi tag và migration; bảng liên kết cung cấp cơ chế FK chuẩn đơn giản hơn.

### 24.5. Chính sách NULL, duplicate và thứ tự phải được ghi rõ

Một contract khả thi cho array tags:

~~~text
- tag_ids không NULL.
- Mảng rỗng nghĩa là chưa có tag.
- Không cho phần tử NULL.
- Không cho duplicate tag IDs.
- Thứ tự không mang ý nghĩa nghiệp vụ.
- Mọi tag ID phải tồn tại trong dictionary.
- Tối đa 20 tags/post.
~~~

Chỉ một số điều ở trên có thể đảm bảo trực tiếp bằng NOT NULL/DEFAULT/CHECK trên cùng row; những điều còn lại cần validation, trigger hoặc đổi mô hình.

Contract của bảng liên kết có thể được hỗ trợ mạnh bằng NOT NULL/PK/FK; giới hạn 20 tags vẫn cần cơ chế riêng.

---

## 25. B-tree hai chiều cho bảng liên kết: đọc đúng thứ tự cột

### 25.1. PRIMARY KEY(post_id,tag_id) phục vụ chiều post → tags

~~~sql
SELECT tag_id
FROM array_lab.post_tags
WHERE post_id=106
ORDER BY tag_id;
~~~

B-tree nhiều cột có prefix-leading semantics; index PK bắt đầu bằng `post_id` giúp scan các tags của một post.

### 25.2. Index(tag_id,post_id) phục vụ chiều tag → posts

~~~sql
SELECT post_id
FROM array_lab.post_tags
WHERE tag_id=4
ORDER BY post_id;
~~~

Index:

~~~sql
CREATE INDEX idx_post_tags_tag_post_alt
ON array_lab.post_tags(tag_id,post_id);
~~~

Lệnh trên chỉ minh họa một index tương đương với `idx_post_tags_tag_post` đã tạo. **Không chạy để giữ cả hai indexes đảo chiều giống nhau** trong production hoặc lab nếu không có lý do. Ý quan trọng là thứ tự cột.

### 25.3. Không giả định một index nhiều cột làm được mọi chiều

B-tree `(post_id,tag_id)` không tương đương `(tag_id,post_id)` cho workload lọc tag_id riêng. PostgreSQL có thể dùng các kỹ thuật khác tùy version/plan nhưng không nên dựa vào việc truy cập hiệu quả mọi tag bằng index bắt đầu bằng post_id.

### 25.4. Truy vấn với condition bổ sung

Nếu `post_tags` có `assigned_at`, query “tất cả posts có tag 4 mới được gắn trong 7 ngày” có thể cần index phù hợp:

~~~sql
-- Dạng thiết kế; yêu cầu bảng đã có cột assigned_at:
CREATE INDEX idx_post_tags_tag_assigned
ON array_lab.post_tags(tag_id,assigned_at DESC,post_id);
~~~

Không tự tạo trên lab khi chưa thêm cột. Chọn theo `WHERE`, `ORDER BY`, LIMIT và selectivity chứ không chỉ theo tên query.

### 25.5. Index coverage và index-only scan

Với linked table, một truy vấn chỉ cần `post_id` và có B-tree `(tag_id,post_id)` có thể có cơ hội **Index Only Scan** khi visibility map phù hợp. Nhưng có index coverage không đảm bảo zero heap fetch; PostgreSQL vẫn phải xem visibility theo MVCC.

Với GIN, workload membership thường có Bitmap Heap Scan rồi phải fetch các posts; không mặc định GIN cho một index-only scan trả về cả `post_id/title`.

---

## 26. Planner chọn GIN hay Seq Scan như thế nào?

### 26.1. Độ chọn lọc của tag

Nếu tag 1 xuất hiện ở 80% posts, GIN lookup có thể phải fetch phần lớn heap pages. Planner có thể chọn Seq Scan, nhất là khi query yêu cầu title/payload từ hầu hết rows.

Nếu tag 99 chỉ xuất hiện ở 100 trong 10 triệu posts, inverted index có thể có lợi ích lớn.

### 26.2. Thống kê phần tử mảng

PostgreSQL có thống kê riêng cho elements trong array ở những kiểu/phiên bản hỗ trợ. Kiểm tra `pg_stats`:

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_elems,
    most_common_elem_freqs,
    elem_count_histogram
FROM pg_stats
WHERE schemaname='array_lab'
  AND tablename IN ('posts_array','big_posts')
  AND attname='tag_ids'
ORDER BY tablename;
~~~

Các trường:

- `most_common_elems`: những element values phổ biến được thu thập.
- `most_common_elem_freqs`: tần suất các element phổ biến theo thống kê.
- `elem_count_histogram`: phân bố liên quan đến số elements distinct của các arrays.

Không đồng nhất thống kê **elements per array** với `n_distinct` của **toàn array value**. Cần đọc đúng trường và dữ liệu mẫu.

### 26.3. ANALYZE sau bulk load

~~~sql
ANALYZE array_lab.posts_array;
ANALYZE array_lab.big_posts;
ANALYZE array_lab.big_post_tags;
~~~

Nếu hai bảng lớn chưa được tạo, bỏ qua `ANALYZE` của chúng. Sau khi nạp dữ liệu lớn hoặc thay đổi phân bố tags, ANALYZE giúp planner có dữ liệu thống kê mới.

### 26.4. Chọn statistics target có kiểm soát

~~~sql
ALTER TABLE array_lab.big_posts
ALTER COLUMN tag_ids SET STATISTICS 300;

ANALYZE array_lab.big_posts;
~~~

Có thể cải thiện một số ước lượng với phân bố tags phức tạp, nhưng làm thu thập/lưu thống kê tốn thêm tài nguyên. Đừng tăng target mọi cột đến mức cực cao mà chưa có bằng chứng sai estimate.

### 26.5. Không nhầm chi phí node cha và node con

Trong EXPLAIN ANALYZE, chi phí thời gian của node cha thường bao gồm công việc con. Nếu root `Hash Join` mất 100 ms, Index Scan/Seq Scan con đã nằm trong khoảng đó. Không cộng thẳng tất cả actual times để ước lượng tổng; đọc `Execution Time`.

### 26.6. Parameterized queries

Ứng dụng thường có:

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> $1::integer[];
~~~

Đây là hình thức SQL parameterized; kết quả và khả năng dùng index phụ thuộc giá trị `$1`, statistics và generic/custom plan.

Một query với tag rất phổ biến và query cùng cấu trúc với tag hiếm có thể cần plan khác nhau; benchmark trên các nhóm giá trị đại diện.

---

## 27. Migration từ array sang bảng liên kết

Đây là một phần quan trọng của lựa chọn kiến trúc. Nếu hệ thống ban đầu lưu `posts.tag_ids` trong array rồi phát sinh nhu cầu FK, metadata hoặc analytics nặng, không nên đổi schema bằng một lệnh không kiểm soát.

### 27.1. Kiểm tra dữ liệu trước khi backfill

Tìm duplicate elements trong cùng post:

~~~sql
SELECT
    p.post_id,
    u.tag_id,
    COUNT(*) AS occurrences
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
GROUP BY p.post_id,u.tag_id
HAVING COUNT(*) > 1
ORDER BY p.post_id,u.tag_id;
~~~

Tìm orphan tag IDs:

~~~sql
SELECT DISTINCT p.post_id,u.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
LEFT JOIN array_lab.tags AS d ON d.tag_id=u.tag_id
WHERE d.tag_id IS NULL
ORDER BY p.post_id,u.tag_id;
~~~

Tìm NULL arrays hoặc phần tử NULL nếu schema thực cho phép:

~~~sql
SELECT post_id
FROM array_lab.posts_array
WHERE tag_ids IS NULL
   OR array_position(tag_ids,NULL) IS NOT NULL;
~~~

Nếu tồn tại duplicate/orphan/NULL, phải có **quy tắc làm sạch được nghiệp vụ đồng ý**. Không dùng DISTINCT một cách âm thầm nếu duplicate thực sự mang ý nghĩa số lần xuất hiện.

### 27.2. Tạo cấu trúc linked model

Trên production, tạo các bảng/PK/FK/index trong migration với thời điểm, lock và disk budget phù hợp. Ví dụ `posts_rel` và `post_tags` đã được tạo trong lab.

### 27.3. Backfill theo batch

Một query mô hình hóa một batch (lab post IDs 101–106):

~~~sql
INSERT INTO array_lab.post_tags(post_id,tag_id)
SELECT DISTINCT
    p.post_id,
    u.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
WHERE p.post_id BETWEEN 101 AND 106
ON CONFLICT (post_id,tag_id) DO NOTHING;
~~~

Yêu cầu `posts_rel` và `tags` đã có các khóa tham chiếu phù hợp. Trên dữ liệu hàng triệu posts, chia nhiều batch nhỏ, checkpoint/retry, đo WAL, transactions và replication lag.

### 27.4. Đồng bộ ghi phát sinh khi backfill

Đây là chỗ migration dễ lỗi nhất. Trong lúc job copy data, API vẫn có thể thêm/xóa tags. Nếu chỉ copy snapshot rồi chuyển đọc sang linked table, **những thay đổi sau snapshot có thể bị mất**.

Các chiến lược tùy bối cảnh:

- **Dừng ghi ngắn có kiểm soát:** backfill/cutover trong maintenance window phù hợp.
- **Dual-write trong application:** ghi cả hai mô hình **cùng transaction** khi có thể; phải xử lý lỗi và kiểm tra consistency.
- **Triggers / CDC / event log:** theo dõi mọi thay đổi array và phản ánh sang linked rows; phải kiểm soát order, idempotency và lỗi đồng bộ.
- **Source-of-truth rõ ràng:** trong một thời điểm chỉ có một mô hình được công bố là authoritative; tránh hai bên tự cập nhật độc lập.

Không giả định “bật dual-write” đơn thuần là đủ: phải biết thứ tự backfill, những write đang bay, retry và recovery.

### 27.5. Đối chiếu kết quả theo set semantics

So mảng đã chuẩn hóa DISTINCT và link đã sort:

~~~sql
SELECT p.post_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL (
    SELECT COALESCE(
        array_agg(DISTINCT u.tag_id ORDER BY u.tag_id),
        '{}'::integer[]
    ) AS array_set
    FROM unnest(p.tag_ids) AS u(tag_id)
) AS a
CROSS JOIN LATERAL (
    SELECT COALESCE(
        array_agg(pt.tag_id ORDER BY pt.tag_id),
        '{}'::integer[]
    ) AS link_set
    FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
) AS l
WHERE a.array_set IS DISTINCT FROM l.link_set
ORDER BY p.post_id;
~~~

Nếu dữ liệu hai mô hình đã đồng bộ, kết quả dự kiến **không có row**. Lệnh này chỉ đối chiếu posts tồn tại ở `posts_array`; với migration thật, còn phải kiểm tra posts mới/đã xóa và orphan link rows theo chiều ngược lại.

### 27.6. Đối chiếu số hàng không đủ

Hai hệ có thể đều có 1 triệu links nhưng **khác cặp post–tag**. Cần kiểm tra:

- Số posts, số distinct post–tag pairs.
- Orphan IDs và duplicate pairs.
- So sánh theo từng post hoặc partition/batch.
- Sample/full checksums theo contract.
- Write events đang chờ xử lý.
- Query nghiệp vụ và permission rules.

### 27.7. Chuyển đọc, chuyển ghi, giữ rollback

Một lộ trình:

~~~text
Định nghĩa model linked + indexes/FK
                 |
                 v
Audit dữ liệu array hiện tại
                 |
                 v
Backfill linked theo batch
                 |
                 v
Bắt/đồng bộ writes phát sinh
                 |
                 v
So sánh dữ liệu và queries
                 |
                 v
Chuyển reads sang linked dần dần
                 |
                 v
Chuyển source of truth sang linked
                 |
                 v
Theo dõi, giữ phương án rollback
                 |
                 v
Chỉ xóa cột array khi không ai còn dùng
~~~

Nếu cần giữ compatibility để rollback, không bỏ array ngay sau lần kiểm tra đầu tiên. Xác định khi nào có thể ngừng dual-write để tránh trôi dữ liệu.

---

## 28. Trả về mảng từ bảng liên kết mà không lưu hai bản sao

Một lợi thế của linked model là có thể tạo **giao diện trả mảng** cho code cũ mà không bắt buộc lưu `tag_ids` trong posts.

### 28.1. ARRAY(SELECT ... ORDER BY ...)

~~~sql
SELECT
    p.post_id,
    p.title,
    ARRAY(
        SELECT pt.tag_id
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
        ORDER BY pt.tag_id
    ) AS tag_ids
FROM array_lab.posts_rel AS p
ORDER BY p.post_id;
~~~

Một subquery `ARRAY(SELECT ...)` trả mảng rỗng khi không có row; vì vậy bài 105 có `{}`. Mẫu này hữu ích để cung cấp DTO cho ứng dụng hoặc API.

### 28.2. Tạo VIEW để tương thích

~~~sql
CREATE VIEW array_lab.posts_with_tag_array AS
SELECT
    p.post_id,
    p.title,
    ARRAY(
        SELECT pt.tag_id
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
        ORDER BY pt.tag_id
    ) AS tag_ids
FROM array_lab.posts_rel AS p;
~~~

Ứng dụng có thể SELECT từ view và nhận cột array. Tuy nhiên:

- View này **tính danh sách** từ linked rows lúc query; không phải heap array đã được cache.
- Muốn lọc `tag_ids @> ...` trên expression của view, planner **không nhất thiết dùng cùng GIN index** như khi cột array được lưu vật lý.
- Với nhiều posts, subqueries hoặc aggregation có thể tạo chi phí đáng kể.
- Nếu cần cache/materialized view, phải quản lý refresh/invalidation và tính nhất quán.

View hỗ trợ **giao diện dữ liệu**, không phải giải pháp performance tự động.

### 28.3. Giữ một source of truth

Không duy trì hai nơi cùng authoritative chỉ vì hai API cần format khác nhau. Một mô hình được lưu và bảo đảm ràng buộc, mô hình kia có thể **được sinh ra khi đọc** hoặc được cache với chính sách refresh rõ.

---

## 29. Migration ngược: từ linked sang array

Đôi khi sản phẩm chuyển sang workload read-mostly với một tập membership nhỏ và không cần metadata từng link. Có thể cân nhắc lưu array như một projection.

### 29.1. Gom links thành array

~~~sql
SELECT
    p.post_id,
    COALESCE(
        array_agg(pt.tag_id ORDER BY pt.tag_id)
            FILTER (WHERE pt.tag_id IS NOT NULL),
        '{}'::integer[]
    ) AS tag_ids
FROM array_lab.posts_rel AS p
LEFT JOIN array_lab.post_tags AS pt
  ON pt.post_id=p.post_id
GROUP BY p.post_id
ORDER BY p.post_id;
~~~

Nếu `post_tags` có PK theo cặp, không cần DISTINCT để loại trùng. Có ORDER BY đảm bảo thứ tự hiển thị ổn định.

### 29.2. Những dữ liệu có thể bị mất khi chuyển

- `assigned_at`, `assigned_by`, `confidence` của mỗi link.
- Semantics FK/unique theo từng cặp.
- Ràng buộc đặc thù và quyền truy cập từng tag.
- Các thao tác update độc lập từng row.
- Thứ tự nếu gom sai hoặc nếu app cần một thứ tự nghiệp vụ khác tag_id.

Không chuyển sang array chỉ vì một API muốn nhận JSON array; có thể tạo view/DTO từ relational rows.

### 29.3. Khi cần sync một bản array cache

Nếu buộc phải lưu materialized tag array để tăng tốc một nhóm query, hãy xác định:

- Ai cập nhật projection?
- Projection chậm tối đa bao lâu so với source?
- Một update link có invalidate cache nào?
- API nào yêu cầu read-your-writes?
- Có backfill/rebuild projection khi lỗi không?
- Có checksum/monitor drift không?

Đó là bài toán **denormalization có kiểm soát**, không phải dữ liệu hoàn toàn không có chi phí.

---

## 30. Chọn theo nghiệp vụ: bảng quyết định

| Tiêu chí | Cột mảng + GIN | Bảng liên kết + B-tree |
|---|---|---|
| Tập IDs nhỏ, giới hạn rõ, read-mostly | **Ứng viên tốt** | Cũng dùng được nhưng nhiều rows/joins hơn |
| Tìm membership nhanh `@>`/`&&` | **GIN phù hợp** | Index theo tag_id phù hợp |
| Nhiều item tags, cập nhật thường xuyên | Có thể đắt vì thay array/GIN/TOAST | **Thường thuận tiện hơn** cập nhật từng link |
| Referential integrity tới danh mục tags | Không có FK trực tiếp từng element | **FK built-in** |
| Không được trùng post–tag | Cần quy tắc ghi/canonicalization | **Composite PK built-in** |
| Quan hệ có metadata | Khó và kém tự nhiên | **Rất phù hợp** |
| Một post đọc toàn tags | Một column fetch thuận tiện | B-tree theo post_id + aggregate |
| Reverse lookup tất cả posts theo tag | GIN inverted lookup | B-tree `(tag_id,post_id)` |
| Báo cáo “bao nhiêu post/tag” | Unnest + group, có thể nặng | GROUP BY links trực tiếp |
| Permissions theo từng tag/link | Phức tạp nếu mảng | Join/row-level rules tự nhiên hơn |
| Lưu thứ tự tags | Array có thứ tự | Thêm position |
| Không cần dictionary, IDs mang nghĩa nội bộ | Có thể hợp lý | Có thể dư nếu bài toán thật sự rất nhỏ |
| Một tag quá phổ biến | GIN có thể không lợi | B-tree cũng không xóa lượng output |
| Bài toán “cùng một item lặp có số lượng” | Array thiếu metadata | Line-item table phù hợp |
| Cần transactionally enforce giới hạn 20 tags | CHECK trên array dễ | Cần aggregate constraint/locking riêng |
| Khả năng query theo JSONB/path | Mảng không phải JSONB | JSONB/document là ứng viên thứ ba |
| Chi phí migration/đổi model | Có thể khó khi phụ thuộc API array | Cần backfill và cutover khi đổi schema |

### 30.1. Gợi ý lựa chọn mặc định

Nếu **tags là quan hệ nghiệp vụ thực sự** giữa hai entity có danh mục, FK, quyền, report, nhiều writers hoặc metadata, **bảng liên kết** là điểm xuất phát dễ quản trị lâu dài.

Nếu danh sách là **thuộc tính tự thân nhỏ, có giới hạn**, tương đối ít thay đổi và truy vấn chủ đạo là containment/overlap, **cột mảng + GIN** là lựa chọn hợp lý.

Không xem đây là quy tắc tuyệt đối; đo độ trễ, storage, update rate và yêu cầu toàn vẹn.

---

## 31. Sơ đồ chọn mô hình và index

~~~mermaid
flowchart TD
    A["Một đối tượng có nhiều giá trị"] --> B{"Giá trị có entity riêng, FK hoặc metadata từng liên kết?"}
    B -- "Có" --> C["Bảng liên kết post_tags"]
    B -- "Không" --> D{"Danh sách nhỏ, giới hạn rõ và ít update?"}
    D -- "Có" --> E["Cân nhắc SQL array"]
    D -- "Không" --> F["Cân nhắc bảng liên kết hoặc model khác"]
    C --> G["PK(post_id,tag_id) + FK + index(tag_id,post_id)"]
    E --> H{"Query membership hay whole-array equality?"}
    H -- "Membership, ANY/ALL/overlap" --> I["GIN array_ops, @>, &&, <@"]
    H -- "So sánh đúng toàn array" --> J["B-tree array / chuẩn hóa thứ tự"]
    F --> K["Đo workload và data shape"]
    G --> L["EXPLAIN + đo JOIN, write, FK, analytics"]
    I --> L
    J --> L
    K --> L
    L --> M{"Đúng semantics và trade-off chấp nhận?"}
    M -- "Có" --> N["Triển khai, monitoring, kiểm soát consistency"]
    M -- "Không" --> O["Điều chỉnh model/index và đo lại"]
~~~

### 31.1. Nguyên tắc cốt lõi

**Cấu trúc chỉ mục chỉ tăng tốc cách dữ liệu được truy cập; nó không thay đổi ý nghĩa dữ liệu được lưu.** Chọn GIN thay B-tree không biến một mảng IDs thành một quan hệ có FK. Tạo bảng liên kết không tự làm một truy vấn “any/all tag” đúng nếu SQL bị duplicate hoặc thiếu tập yêu cầu.

---

## 32. Vận hành index trên production

### 32.1. Tạo GIN index trên bảng lớn

~~~sql
CREATE INDEX CONCURRENTLY idx_posts_array_tags_gin_online
ON array_lab.posts_array USING gin(tag_ids);
~~~

**Chỉ ví dụ trên lab:** nếu đã có index GIN tương đương, không cần tạo thêm. Trên bảng lớn đang nhận ghi, `CONCURRENTLY` có thể giúp giảm chặn DML thường, nhưng:

- Không được chạy trong transaction block tường minh.
- Có chi phí quét dữ liệu, CPU, WAL và disk.
- Có thể chờ các transactions/snapshots liên quan.
- Có thể để lại index INVALID nếu thất bại/cancel.
- Cần theo dõi tiến độ và thời điểm triển khai.

### 32.2. Kiểm tra index hợp lệ

~~~sql
SELECT
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready,
    pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index AS ix
JOIN pg_class AS idx
  ON idx.oid=ix.indexrelid
JOIN pg_class AS tbl
  ON tbl.oid=ix.indrelid
JOIN pg_namespace AS ns
  ON ns.oid=tbl.relnamespace
WHERE ns.nspname='array_lab'
  AND tbl.relname IN ('posts_array','big_posts')
ORDER BY idx.relname;
~~~

`indisvalid=false` nghĩa là index không được planner sử dụng như một index hợp lệ theo quy tắc thông thường. **Tên index tồn tại không chứng minh build đã thành công**.

### 32.3. Theo dõi build

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
WHERE datname=current_database();
~~~

Nếu không có row, có thể không có build đang chạy tại thời điểm chụp. Không dùng ratio blocks_done/blocks_total làm % toàn job chính xác vì còn nhiều phases/waits.

### 32.4. DROP/REINDEX

Nếu một index thừa/invalid, cần kiểm tra dependency, query usage, quyền và bản sao phục hồi trước khi DROP. `DROP INDEX CONCURRENTLY` và `REINDEX ... CONCURRENTLY` có quy tắc transaction riêng, không nằm trong transaction block tường minh khi dùng những cú pháp đó.

Không tự động xóa index chỉ vì thống kê `idx_scan=0` trong một khoảng quan sát ngắn.

### 32.5. Chi phí thêm index

Mỗi index tăng:

- Disk storage.
- Thời gian chèn/cập nhật/xóa.
- WAL, buffer pressure.
- VACUUM/autovacuum work.
- Thời gian backup, reindex và schema migration.

Không tạo đồng thời GIN array, B-tree array, hai expression indexes và GIN JSONB chỉ “cho chắc” khi query workload chưa cần.

### 32.6. FKs và delete cascades cũng cần đo

Bảng liên kết có FKs nên DELETE post có thể kéo theo nhiều DELETE links. B-tree indexes hỗ trợ tìm các rows liên quan, nhưng vẫn sinh WAL/IO/locks và trigger checks. “Quan hệ chuẩn hóa” không phải miễn phí.

---

## 33. Quy tắc bảo mật và tính đúng khi query array

### 33.1. Không tự ghép chuỗi để xây array literal từ input

Không dùng:

~~~text
SQL = "WHERE tag_ids @> ARRAY[" + raw_user_input + "]"
~~~

Mẫu này có nguy cơ SQL injection và lỗi cast/escaping. Dùng parameterized SQL và kiểu array rõ:

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> $1::integer[];
~~~

Driver phải bind `$1` thành array tương ứng; cú pháp placeholder thực tế tùy driver/ORM.

### 33.2. Validation với tag IDs

Nếu API chỉ cho tags 1..6 trong dictionary, mảng SQL không tự bảo đảm mọi IDs thuộc tập đó. Validate và quản lý concurrency, hoặc dùng FK ở bảng liên kết.

### 33.3. Quyền truy cập từng tag

Một số tags có thể thuộc tenant riêng hoặc permission scope. Mảng chung chứa IDs không tự bảo đảm người dùng không trộn tags thuộc tenant khác. Bảng liên kết có thể thêm tenant_id và composite FK/unique keys phù hợp để enforce. Tuy nhiên **FK một mình không thay thế authorization/RLS**, vẫn cần chính sách dữ liệu đúng.

### 33.4. Không nhầm hiệu năng với bảo mật

GIN chỉ phục vụ filter membership nhanh hơn; nó không ngăn một query đọc tags nhạy cảm nếu role có quyền đọc bảng. Tổ chức quyền và RLS (nếu cần) phải được thiết kế riêng, đo plan đúng dưới role áp dụng.

### 33.5. Với text[] tags, chuẩn hóa tên

Nếu dùng `text[]` như `{'postgres','Postgres','POSTGRES'}`, ứng dụng phải định nghĩa case/collation/synonym semantics. PostgreSQL GIN `array_ops` không tự đồng nhất ba chuỗi nếu loại toán tử/so sánh không coi chúng bằng nhau.

Nếu tags có dictionary chuẩn hóa, dùng IDs và link FK có thể giúp tránh phân mảnh nhãn.

---

## 34. Những lỗi và ngộ nhận thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| “Array là set, tự unique và không có thứ tự” | Duplicate/order tạo kết quả bất ngờ | Xác định list/set semantics |
| “`{1,1}` @> `{1,1,1}` là false” | Hiểu sai multiplicity của containment | `@>` kiểm tra sự hiện diện elements |
| “NULL array giống mảng rỗng” | Query IS NULL/cardinality sai | `NOT NULL DEFAULT '{}'` khi phù hợp |
| “Một element NULL là thẻ chưa xác định” | UNKNOWN/null semantics phức tạp | Không lưu NULL elements nếu là tags |
| “Có GIN là ANY tự chuyển sang index lookup” | Planner có thể không dùng GIN | Dùng `@> ARRAY[element]` và EXPLAIN |
| “GIN hỗ trợ mọi function trên array” | Predicate không dùng operator class | Kiểm tra toán tử `@>/&&/<@/=` |
| “B-tree trên array tìm từng tag nhanh” | B-tree so toàn array value | GIN cho membership |
| “GIN tự ngăn duplicate tags” | Mảng vẫn có thể chứa phần tử lặp | Canonicalization hoặc PK bảng liên kết |
| “GIN tạo FK cho từng element” | Orphan IDs không bị ngăn | Junction FK hoặc validation khác |
| “GIN luôn nhanh hơn Seq Scan” | Tag phổ biến, bảng nhỏ làm index bất lợi | Benchmark selectivity |
| “Có index thì NOT contains cũng nhanh” | Negative filter thường giữ nhiều rows | Đo và xem query requirements |
| “`cardinality=0` dùng GIN nhanh” | Đây là expression-count predicate | Expression/partial index nếu cần |
| “Mảng có 20 slots nghĩa là 20 distinct tags” | Duplicates vẫn được đếm | Chuẩn hóa nếu set |
| “`COUNT(*)` sau unnest là số posts/tag” | Duplicates khiến đếm lớn hơn | `COUNT(DISTINCT post_id)` |
| “JOIN tag IN(...) trả mỗi post một row” | Post có nhiều tags có thể xuất hiện nhiều lần | EXISTS/DISTINCT |
| “COUNT(*)=N trong HAVING dùng được với requested duplicates” | Sai logic ALL tags | Normalize requested set |
| “Tập request rỗng luôn không trả row” | ALL tags của tập rỗng theo logic thường đúng với mọi post | Định nghĩa semantics và SQL tương ứng |
| “FK tự tạo index ở referencing table” | Xóa/update parent có thể scan child | Tạo index theo chiều query/FK |
| “PK(post_id,tag_id) đủ tìm mọi post của tag hiệu quả” | Thứ tự cột không hợp reverse lookup | B-tree `(tag_id,post_id)` |
| “Muốn gắn một tag chỉ update 1 byte trong array” | MVCC tạo row version/TOAST/index changes | Đo write amplification |
| “App read-modify-write toàn array luôn an toàn” | Lost updates/duplicates khi concurrency | SQL atomic update hoặc locking/version |
| “Bảng liên kết luôn ít storage hơn” | Có nhiều rows, FKs và indexes | Đo tổng heap + indexes |
| “Array đọc tất cả tags nhanh hơn trong mọi trường hợp” | TOAST/cache/size có thể chi phối | Benchmark |
| “Bảng liên kết không tạo thêm read overhead” | JOIN/aggregate có cost | Đo index lookups và join |
| “JSONB array dùng cùng opclass array_ops” | GIN JSONB operators khác | `jsonb_ops`/`jsonb_path_ops` đúng predicate |
| “JSONB flexible nên không cần relation” | Không enforce FK/unique từng edge | Thiết kế theo nghiệp vụ |
| “Query view ARRAY(SELECT...) tự dùng GIN cột đã bỏ” | Dữ liệu được tính từ links, không có array GIN vật lý | Đo query/view plan |
| “Chỉ copy dữ liệu rồi đổi đọc là migration xong” | Mất writes phát sinh khi backfill | Sync/cutover và audit |
| “Cùng COUNT tức hai mô hình giống nhau” | Sai cặp links vẫn có tổng bằng nhau | So theo post–tag pairs |
| “GIN pending list không ảnh hưởng latency” | Cleanup hoặc query overhead | Theo dõi fastupdate/maintenance |
| “CREATE INDEX CONCURRENTLY không tốn tài nguyên” | I/O/WAL/locks và invalid state | Monitor, runway, rollback |
| “EXPLAIN ANALYZE DELETE chỉ mô phỏng” | Xóa dữ liệu thật | EXPLAIN không ANALYZE hoặc lab transaction |
| “Index only scan chắc chắn không đọc heap” | Visibility map còn quan trọng | Xem Heap Fetches |
| “SELECT không ORDER BY có thứ tự chèn tags ổn định” | SQL relation không bảo đảm order | Lưu position và ORDER BY |
| “Bỏ cột array ngay khi có bảng liên kết” | App cũ/worker cũ mất compatibility | Expand/backfill/cutover/contract |

---

## 35. Checklist thiết kế trước khi quyết định

### Về dữ liệu

- [ ] Mỗi phần tử là **một tag ID**, một attribute hay một entity thực?
- [ ] Có yêu cầu **không duplicate** không?
- [ ] Có cần thứ tự hay multiplicity?
- [ ] NULL array, empty array và NULL element được hiểu thế nào?
- [ ] Số elements per object trung bình, p95, tối đa?
- [ ] Có dictionary và FK cần enforce không?
- [ ] Có metadata/quyền/timestamp trên từng liên kết không?

### Về truy vấn

- [ ] Query chính lấy tất cả tags của một post hay tìm nhiều posts theo tag?
- [ ] Có truy vấn ANY/ALL/NOT/whitelist không?
- [ ] Có báo cáo GROUP BY tag, join nhiều dimensions không?
- [ ] Tag phổ biến và tag hiếm có phân bố thế nào?
- [ ] API có yêu cầu top-k/pagination không?
- [ ] Index có thể hỗ trợ đúng operator/expression không?

### Về cập nhật

- [ ] Có bao nhiêu writes mỗi giây?
- [ ] Nhiều clients có cùng thay đổi tags trên một post không?
- [ ] Các arrays có thường vượt giới hạn inline/TOAST không?
- [ ] Có bulk import, xóa tag hàng loạt, tag rename?
- [ ] Có cần transaction toàn vẹn đa bảng không?

### Về vận hành

- [ ] Đã đo query trên dữ liệu đại diện, không chỉ sáu posts?
- [ ] Đã xem `EXPLAIN (ANALYZE, BUFFERS)`?
- [ ] Đã tính tổng heap + indexes + TOAST?
- [ ] Đã đo thời gian UPDATE/INSERT/DELETE và VACUUM?
- [ ] Đã chuẩn bị GIN pending list/autovacuum monitoring?
- [ ] Đã tính WAL/replication/backup overhead?
- [ ] Có kế hoạch migration/cutover nếu thay mô hình?
- [ ] Có kiểm tra FK, orphan, duplicate và data consistency?

---

## 36. Bài tập thực hành

Các bài dùng schema `array_lab` và dữ liệu mẫu. Những câu tạo index, sửa bảng hoặc cập nhật dữ liệu nên được làm trên **database thực hành riêng**. Nếu đã chạy phần cập nhật tags ở chương trước, dữ liệu có thể khác ví dụ; để kiểm chứng kết quả mẫu, sử dụng trạng thái ban đầu hoặc tái tạo môi trường lab do bạn sở hữu. Không dùng DROP, DELETE hoặc UPDATE trên bảng production chỉ để kiểm tra bài học.

### Bài 1 — Mảng hay tập hợp?

Giải thích vì sao `ARRAY[1,1,2]` là một mảng hợp lệ nhưng không biểu diễn một tập tag canonical. Nếu business không cho trùng tag, yêu cầu nào cần enforce?

### Bài 2 — NULL khác empty

So sánh `NULL::integer[]`, `'{}'::integer[]` và `ARRAY[NULL]::integer[]`. Viết query trả `cardinality` từng trường hợp.

### Bài 3 — Containment không kiểm multiplicity

Đoán và giải thích:

~~~sql
SELECT ARRAY[1]::int[] @> ARRAY[1,1]::int[];
~~~

Nếu mục tiêu là “có đúng hai lần phần tử 1”, toán tử này có phù hợp không?

### Bài 4 — Array equality

Hai mảng `ARRAY[1,2]` và `ARRAY[2,1]` có bằng nhau theo `=` không? Một query muốn so sánh **cùng tập tags** cần xử lý điều gì?

### Bài 5 — Tìm một thẻ

Viết query tìm bài có tag 1 bằng `@>` trên `array_lab.posts_array`. Nếu dữ liệu ban đầu, trả những post_ids nào?

### Bài 6 — Tìm tất cả tags

Viết query tìm bài có tag 1 **và** 4. Toán tử nào phù hợp? Vì sao không dùng `&&`?

### Bài 7 — Tìm bất kỳ tag nào

Viết query tìm bài có tag 4 **hoặc** 5. Kết quả post_ids dự kiến?

### Bài 8 — Whitelist

Viết truy vấn tìm bài chỉ dùng các tags trong tập {1,2,4}; dùng `<@`. Tại sao bài 105 chưa có tag vẫn thỏa?

### Bài 9 — Không có tags

Viết query tìm bài chưa gắn tag. Phân biệt `cardinality(tag_ids)=0` và `tag_ids IS NULL` trong schema lab.

### Bài 10 — Không có tag 4

Viết truy vấn mảng tìm bài không chứa tag 4. Có thể mặc định GIN sẽ tăng tốc predicate phủ định tốt như predicate dương không?

### Bài 11 — ANY so với GIN

Giải thích:

~~~sql
WHERE 4 = ANY(tag_ids)
~~~

và:

~~~sql
WHERE tag_ids @> ARRAY[4]::integer[]
~~~

Khác nhau thế nào về dạng operator mà GIN `array_ops` hỗ trợ? Có trường hợp NULL cần cẩn thận không?

### Bài 12 — Index GIN

Viết lệnh tạo GIN trên cột `tag_ids`. Tập toán tử nào được hỗ trợ bởi built-in array_ops? Có đảm bảo planner chọn GIN trên bảng sáu row không?

### Bài 13 — B-tree trên mảng

Viết index B-tree trên `tag_ids`. Nó giúp tìm phần tử 4 bên trong mảng như GIN không? Khi nào B-tree array value hợp lý?

### Bài 14 — Index cho count

Nếu thường lọc `cardinality(tag_ids)=0`, viết một expression index hoặc partial index phù hợp và giải thích vì sao GIN membership không tự giải quyết tối ưu trường hợp này.

### Bài 15 — EXPLAIN GIN

Viết `EXPLAIN (ANALYZE, BUFFERS)` cho query tìm bài có tags {1,4}. Nếu có `Bitmap Index Scan` và `Bitmap Heap Scan`, mỗi node làm gì?

### Bài 16 — Recheck

`Recheck Cond` trong Bitmap Heap Scan có nghĩa GIN bị hỏng hoặc kết quả sai không? Cần xem thêm trường nào khi muốn biết false positives/lossy pages?

### Bài 17 — Tạo bảng liên kết

Viết SQL định nghĩa `post_tags(post_id,tag_id)` với PK composite và hai FKs tới `posts_rel`, `tags`. Một tag có thể gắn hai lần vào cùng post không?

### Bài 18 — Index đảo chiều

PK `(post_id,tag_id)` hỗ trợ query nào? Tạo index phù hợp cho query liệt kê mọi post có tag 4.

### Bài 19 — Linked any tag

Viết truy vấn `EXISTS` tìm posts có **ít nhất một** tag trong {4,5}. Vì sao JOIN trực tiếp có thể tạo trùng post?

### Bài 20 — Linked all tags

Viết query linked model tìm posts có **cả** tag 1 và 4 bằng `GROUP BY/HAVING` hoặc hai `EXISTS`.

### Bài 21 — Dynamic ALL request

Một requested set do người dùng gửi có dạng [1,1,4]. Vì sao không dùng `HAVING COUNT(*)=3` trên link rows một cách trực tiếp? Cần chuẩn hóa input thế nào?

### Bài 22 — ALL với tập rỗng

Nếu API yêu cầu “post chứa **tất cả** tags của tập rỗng”, logic nào hợp lý? Vì sao query JOIN/HAVING thông thường có thể không trả gì, còn `@> ARRAY[]` thì đúng cho mọi mảng không NULL?

### Bài 23 — Đếm tags trên bài

Viết SQL cho array model và linked model để tính số tags trên post 101. Khi array có phần tử trùng, hai con số có thể khác nhau thế nào?

### Bài 24 — Báo cáo tag phổ biến

Viết query liên kết đếm số posts của từng tag (bao gồm tag chưa được dùng), và nêu vì sao với LEFT JOIN phải `COUNT(pt.post_id)` thay vì `COUNT(*)`.

### Bài 25 — Đếm bài có tag qua unnest

Viết query mảng thống kê số **distinct posts** theo tag_id bằng `unnest`. Điều gì xảy ra khi dùng COUNT(*) mà mảng có duplicate tag IDs?

### Bài 26 — Gắn tag đồng thời

Hai clients cùng thêm tag 5 cho post 101. Mô hình liên kết với PK + `ON CONFLICT DO NOTHING` giúp ngăn điều gì? Vì sao app read-modify-write toàn array có rủi ro lost update?

### Bài 27 — Append/remove array

Viết SQL thêm tag 5 nếu post chưa có; viết SQL xóa tag 5. `array_remove` xóa một lần hay tất cả occurrences?

### Bài 28 — Referential integrity

Một post chứa tag 9999 nhưng dictionary chỉ có tags 1..6. Vì sao một GIN index không phát hiện lỗi này? Model nào có thể dùng FK built-in để chặn?

### Bài 29 — Xóa tag dictionary

Trong model liên kết FK tag không dùng ON DELETE CASCADE, điều gì thường xảy ra khi DELETE một tag đang được tham chiếu? Với array IDs, điều gì có thể xảy ra?

### Bài 30 — Metadata trên quan hệ

Business cần lưu ai gắn tag, thời gian và mức tin cậy. Bạn chọn mảng IDs, JSONB hay bảng liên kết làm mô hình chính? Giải thích.

### Bài 31 — Thứ tự tags

Nếu user kéo–thả thứ tự tags, bảng liên kết cần thêm cột gì? Có bảo đảm rows mặc định trả theo thứ tự chèn không?

### Bài 32 — ARRAY(SELECT ...)

Viết query trả danh sách tag IDs sorted từ `post_tags` dưới dạng một cột integer[] cho từng post, không lưu array thứ hai trong database.

### Bài 33 — JSONB khác SQL array

Dùng SQL cho `'[1,2]'::jsonb @> '[2]'::jsonb` và `ARRAY[1,2]::int[] @> ARRAY[2]::int[]`. Có dùng cùng GIN operator class không?

### Bài 34 — Mẫu JSONB có tags

Một bảng có cột JSONB `doc` chứa `{"tags":["PostgreSQL"]}`. Viết filter containment và một kiểu index có thể hỗ trợ; vì sao không thể dùng `array_ops`?

### Bài 35 — GIN pending list

`fastupdate` của GIN có ích gì và có thể tạo loại overhead nào? Tại sao tắt autovacuum để tránh cleanup không phải giải pháp an toàn?

### Bài 36 — TOAST và HOT

Một post có 10.000 tags, cập nhật một tag trong indexed array. Những chi phí nào có thể phát sinh? Tại sao linked model có thể có lợi khi cập nhật từng cặp?

### Bài 37 — Benchmark fair

Nêu ít nhất sáu đại lượng/công việc phải đo khi so GIN array với B-tree link trên một triệu posts. Vì sao cần đo tag hiếm và tag phổ biến riêng?

### Bài 38 — Migration kiểm tra dữ liệu

Viết query tìm duplicates và orphan tag IDs trong `posts_array` trước khi chuyển sang linked model.

### Bài 39 — Backfill và concurrent writes

Nêu quy trình chuyển từ array sang linked model không mất các thay đổi phát sinh trong lúc backfill. Vì sao so COUNT(*) hai bảng chưa chứng minh hai tập links bằng nhau?

### Bài 40 — Tổng hợp kiến trúc

Chọn mô hình và chỉ mục khởi đầu cho ba trường hợp:

1. Mỗi row có 3–8 mã cấu hình cố định, gần như không update, thường truy vấn “có một trong các mã”.
2. Mỗi sản phẩm có hàng trăm categories, người quản trị cập nhật thường xuyên, cần FK, category metadata và báo cáo top category.
3. API cần trả một ordered playlist có phần tử lặp, mỗi item có position/created_by và có nhiều writers.

Nêu lý do, trade-off và cách đo để xác nhận lựa chọn.

---

## 37. Gợi ý lời giải

### Bài 1 — Array không tự là set

`ARRAY[1,1,2]` có ba vị trí phần tử, gồm hai lần 1. Nếu tags là set, cần quy tắc không duplicate. Bảng liên kết có `PK(post_id,tag_id)` tự enforce; cột array cần canonicalization/validation có kiểm soát. GIN index không phải unique-per-element constraint.

### Bài 2 — NULL, empty và NULL element

~~~sql
SELECT cardinality(NULL::integer[]) AS null_array_count,
       cardinality('{}'::integer[]) AS empty_array_count,
       cardinality(ARRAY[NULL]::integer[]) AS null_element_count;
~~~

Kỳ vọng lần lượt NULL, 0, 1. Nếu nghiệp vụ “chưa gắn tag” là empty set, dùng `NOT NULL DEFAULT '{}'::int[]` và ngăn NULL elements.

### Bài 3 — Containment không đếm multiplicity

~~~sql
SELECT ARRAY[1]::int[] @> ARRAY[1,1]::int[];
~~~

Kết quả là TRUE: array containment kiểm tra sự hiện diện element, không yêu cầu đủ “hai bản sao”. Nếu multiplicity có ý nghĩa, lưu cấu trúc đếm/line items thích hợp hoặc so array values theo quy tắc khác.

### Bài 4 — Equality có thứ tự

`ARRAY[1,2] = ARRAY[2,1]` là FALSE. Để so cùng set tags, canonicalize thành các phần tử distinct sorted trước khi so equality, hoặc dùng logic hai chiều `a @> b AND b @> a` với lưu ý NULL semantics/dimensions và yêu cầu nghiệp vụ.

### Bài 5 — Một tag

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1]::int[]
ORDER BY post_id;
~~~

Kỳ vọng 101, 102, 106 ở lab ban đầu.

### Bài 6 — Tất cả tags

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::int[]
ORDER BY post_id;
~~~

Kỳ vọng 101,106. `&&` chỉ yêu cầu có **ít nhất một** phần tử chung, không bảo đảm có cả 1 và 4.

### Bài 7 — Ít nhất một tag

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids && ARRAY[4,5]::int[]
ORDER BY post_id;
~~~

Kỳ vọng 101,102,104,106.

### Bài 8 — Whitelist

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids <@ ARRAY[1,2,4]::int[]
ORDER BY post_id;
~~~

Kỳ vọng 101,105. Mảng rỗng là subset của mọi mảng không NULL; đó là semantics logic, không phải lỗi lọc.

### Bài 9 — Empty array

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE cardinality(tag_ids)=0;
~~~

Kỳ vọng post 105. Với `tag_ids NOT NULL`, `tag_ids IS NULL` không trả rows; NULL array khác empty.

### Bài 10 — Không có tag

~~~sql
SELECT post_id,title
FROM array_lab.posts_array
WHERE NOT (tag_ids @> ARRAY[4]::int[])
ORDER BY post_id;
~~~

Kỳ vọng 102,103,105. Negative predicate thường giữ nhiều rows và không mặc định hưởng lợi từ inverted lookup như tìm key có mặt; đọc EXPLAIN.

### Bài 11 — ANY và GIN

`4 = ANY(tag_ids)` là scalar-array comparison; `tag_ids @> ARRAY[4]` dùng array containment operator được GIN `array_ops` hỗ trợ. Không giả định planner tự rewrite ANY thành containment. Nếu có NULL elements, các biểu thức có thể khác ở TRUE/FALSE/UNKNOWN trong một số tình huống, dù có thể chọn cùng rows ở WHERE đối với bài toán membership không NULL.

### Bài 12 — Tạo GIN

~~~sql
CREATE INDEX idx_posts_array_tags_gin_answer
ON array_lab.posts_array USING gin(tag_ids);
~~~

GIN array_ops hỗ trợ `@>`, `<@`, `&&`, `=` theo opclass. Trên sáu rows, Seq Scan có thể rẻ hơn; tồn tại index không ép planner sử dụng.

### Bài 13 — B-tree array

~~~sql
CREATE INDEX idx_posts_exact_tags_btree_answer
ON array_lab.posts_array USING btree(tag_ids);
~~~

B-tree so toàn array value; không phải inverted index để tìm tag ở vị trí bất kỳ. Phù hợp exact equality hoặc ordering trên array values khi semantics và workload thật yêu cầu.

### Bài 14 — Index cho số lượng

~~~sql
CREATE INDEX idx_posts_no_tags_answer
ON array_lab.posts_array(post_id)
WHERE cardinality(tag_ids)=0;
~~~

Hoặc expression index:

~~~sql
CREATE INDEX idx_posts_tag_count_answer
ON array_lab.posts_array ((cardinality(tag_ids)));
~~~

Chọn **một phương án phù hợp**, không phải giữ cả hai. GIN array_ops tối ưu truy vấn theo presence elements, không trực tiếp lập chỉ mục count of elements.

### Bài 15 — EXPLAIN GIN

~~~sql
EXPLAIN (ANALYZE,BUFFERS)
SELECT post_id,title
FROM array_lab.posts_array
WHERE tag_ids @> ARRAY[1,4]::int[];
~~~

Nếu có Bitmap Index Scan, index thu thập vị trí ứng viên; Bitmap Heap Scan lấy heap rows và xác nhận điều kiện khi cần. Với bảng nhỏ có thể Seq Scan.

### Bài 16 — Recheck

Không. Recheck là cơ chế xác minh candidate, không chứng minh index hỏng. Xem `Heap Blocks: exact/lossy`, `Rows Removed by Index Recheck`, index qual và plan tổng thể.

### Bài 17 — Junction constraints

~~~sql
CREATE TABLE array_lab.post_tags_answer (
    post_id BIGINT NOT NULL
        REFERENCES array_lab.posts_rel(post_id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL
        REFERENCES array_lab.tags(tag_id),
    PRIMARY KEY(post_id,tag_id)
);
~~~

Một cặp post–tag không thể lặp hai lần vì PK composite. Nó vẫn cho nhiều post chia sẻ một tag và mỗi post có nhiều tags.

### Bài 18 — Reverse B-tree

PK(post_id,tag_id) phục vụ tìm tags của một post. Để tìm posts theo tag:

~~~sql
CREATE INDEX idx_post_tags_answer_reverse
ON array_lab.post_tags(tag_id,post_id);
~~~

Nếu index cùng định nghĩa đã tồn tại, không cần tạo trùng trong lab.

### Bài 19 — EXISTS any

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
WHERE EXISTS (
    SELECT 1 FROM array_lab.post_tags AS pt
    WHERE pt.post_id=p.post_id
      AND pt.tag_id IN (4,5)
)
ORDER BY p.post_id;
~~~

Kỳ vọng 101,102,104,106. JOIN trực tiếp có thể lặp post nếu cùng post có cả tag 4 và 5; EXISTS chỉ hỏi sự tồn tại.

### Bài 20 — Linked all

~~~sql
SELECT p.post_id,p.title
FROM array_lab.posts_rel AS p
JOIN array_lab.post_tags AS pt ON pt.post_id=p.post_id
WHERE pt.tag_id IN (1,4)
GROUP BY p.post_id,p.title
HAVING COUNT(DISTINCT pt.tag_id)=2
ORDER BY p.post_id;
~~~

Kỳ vọng 101,106. PK ngăn duplicate post-tag links, nhưng COUNT DISTINCT vẫn giúp làm rõ logic ALL cho tập yêu cầu distinct.

### Bài 21 — Requested duplicates

Input [1,1,4] là ba vị trí nhưng chỉ **hai tag IDs phân biệt**. Bảng liên kết có mỗi tag một row, nên `COUNT(*)=3` sẽ sai hoặc không tìm được post đúng. Normalize request với DISTINCT để thành {1,4}, rồi so count bằng 2 hoặc dùng hai EXISTS.

### Bài 22 — ALL với tập rỗng

Theo logic “không có tag yêu cầu nào bị thiếu”, mọi bài đều thỏa ALL(empty set). Array `@> '{}'` true cho mảng không NULL. Một query JOIN bắt đầu từ requested set rỗng sẽ không có rows để GROUP, vì vậy muốn semantics tương đương phải xử lý rỗng riêng hoặc dùng **NOT EXISTS lồng** (relational division với vacuous truth).

### Bài 23 — Đếm tags/post

Mảng:

~~~sql
SELECT post_id,cardinality(tag_ids) AS tag_count
FROM array_lab.posts_array
WHERE post_id=101;
~~~

Liên kết:

~~~sql
SELECT COUNT(*) AS tag_count
FROM array_lab.post_tags
WHERE post_id=101;
~~~

Kỳ vọng cùng bằng 3 ở dữ liệu gốc. Với array chứa duplicates, cardinality đếm tất cả positions, còn PK của links chỉ có distinct pairs.

### Bài 24 — Báo cáo mọi tag

~~~sql
SELECT
    d.tag_id,d.tag_name,
    COUNT(pt.post_id) AS posts_count
FROM array_lab.tags AS d
LEFT JOIN array_lab.post_tags AS pt ON pt.tag_id=d.tag_id
GROUP BY d.tag_id,d.tag_name
ORDER BY d.tag_id;
~~~

COUNT(pt.post_id) bỏ qua NULL của LEFT JOIN, nên tag chưa được dùng có số 0; COUNT(*) có thể đếm một placeholder row.

### Bài 25 — Đếm distinct posts từ arrays

~~~sql
SELECT
    u.tag_id,
    COUNT(DISTINCT p.post_id) AS posts_count
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
GROUP BY u.tag_id
ORDER BY u.tag_id;
~~~

Nếu array có {1,1,2}, COUNT(*) sẽ tính tag 1 hai lần cho cùng post; COUNT(DISTINCT post_id) không bị lỗi đó.

### Bài 26 — Concurrent inserts

PK(post_id,tag_id) ngăn duplicate links ở tầng database; `ON CONFLICT DO NOTHING` có thể xử lý retry theo cặp idempotently. Với mảng, hai app instances đọc cùng bản cũ rồi ghi array mới có nguy cơ mất thay đổi của nhau. Cần một câu UPDATE dựa trên giá trị đang được khóa hoặc optimistic version/transaction control.

### Bài 27 — Append/remove

~~~sql
UPDATE array_lab.posts_array
SET tag_ids=array_append(tag_ids,5)
WHERE post_id=103
  AND NOT (tag_ids @> ARRAY[5]::int[]);

UPDATE array_lab.posts_array
SET tag_ids=array_remove(tag_ids,5)
WHERE post_id=103;
~~~

`array_remove` loại **mọi** occurrences của giá trị 5. Nếu muốn xóa đúng một occurrence trong một ordered list, cần logic khác.

### Bài 28 — FK cho từng element

GIN chỉ index members cho search, không đối chiếu mỗi tag ID với dictionary. Một array {9999} vẫn có thể được ghi nếu không có validation riêng. Bảng liên kết có `FOREIGN KEY(tag_id) REFERENCES tags(tag_id)` chặn orphan IDs.

### Bài 29 — Xóa dictionary tag

Ở linked model với FK mặc định không cascade trên tag side, xóa tag đang có post_tags thường **bị từ chối** vì FK. Với array IDs, dictionary tag có thể bị xóa nhưng số tag_id vẫn nằm trong các arrays, trở thành orphan references.

### Bài 30 — Metadata theo link

Chọn bảng liên kết làm **source of truth**: mỗi row lưu post_id,tag_id,assigned_at,assigned_by,confidence cùng constraints/indexes phù hợp. JSONB/array có thể lưu cấu trúc linh hoạt nhưng việc enforce FK, uniqueness và update từng link phức tạp hơn. Nhu cầu metadata trực thuộc cạnh quan hệ là tín hiệu rõ ràng cho junction table.

### Bài 31 — Thứ tự tags

Thêm `position` hoặc `display_order` trong linked row, kèm constraint ngăn trùng vị trí theo post khi cần. Query phải `ORDER BY display_order,tag_id` hoặc một thứ tự xác định. SQL relation **không bảo đảm** thứ tự chèn khi SELECT không ORDER BY.

### Bài 32 — Sinh array từ links

~~~sql
SELECT
    p.post_id,
    p.title,
    ARRAY(
        SELECT pt.tag_id
        FROM array_lab.post_tags AS pt
        WHERE pt.post_id=p.post_id
        ORDER BY pt.tag_id
    ) AS tag_ids
FROM array_lab.posts_rel AS p
ORDER BY p.post_id;
~~~

Với post chưa có link, `ARRAY(SELECT ...)` cho mảng rỗng. Không cần thêm cột array lưu bản sao thứ hai.

### Bài 33 — SQL array và JSONB array

~~~sql
SELECT ARRAY[1,2]::int[] @> ARRAY[2]::int[] AS sql_array_contains,
       '[1,2]'::jsonb @> '[2]'::jsonb AS jsonb_contains;
~~~

Cả hai minh họa containment nhưng **khác operator class và semantics theo type**: GIN `array_ops` cho SQL arrays; GIN `jsonb_ops`/`jsonb_path_ops` cho JSONB theo operator được hỗ trợ.

### Bài 34 — JSONB tags

~~~sql
SELECT post_id
FROM array_lab.posts_jsonb
WHERE doc @> '{"tags":["PostgreSQL"]}'::jsonb;
~~~

Index ứng viên:

~~~sql
CREATE INDEX idx_posts_jsonb_doc_answer
ON array_lab.posts_jsonb USING gin(doc);
~~~

`array_ops` không áp cho JSONB vì JSONB là kiểu dữ liệu khác, với opclasses/operators riêng. Nếu query expression `(doc->'tags') ? ...`, cân nhắc GIN expression index trên đúng expression.

### Bài 35 — GIN fastupdate

`fastupdate` có thể gom index entries mới vào pending list, giúp nhiều inserts, nhưng làm query/cleanup phải xử lý pending entries và có thể tạo latency spikes khi cleanup. Autovacuum/VACUUM còn có nhiệm vụ MVCC/dead tuples và dọn pending data; **không tắt tự động** chỉ để né cleanup.

### Bài 36 — TOAST và HOT

UPDATE array lớn có thể tạo row version mới, TOAST data mới, GIN changes, WAL và dead tuples, đồng thời thay đổi indexed column thường không đủ điều kiện HOT. Với linked model, thêm/xóa một tag có thể tương ứng một INSERT/DELETE nhỏ ở link table, đổi lại có nhiều rows, PK/FK checks và B-tree maintenance.

### Bài 37 — Benchmark công bằng

Đo ít nhất: p50/p95 query latency, buffers shared hit/read, temp I/O, GIN/B-tree index size, total table+TOAST size, INSERT/UPDATE/DELETE throughput, WAL volume, VACUUM/cleanup, memory, planning time, số rows thực và cardinality estimate.

Tag hiếm thường có index selectivity cao; tag phổ biến có thể yêu cầu phần lớn rows khiến Seq Scan hoặc join path khác hợp lý. Chỉ đo một tag không đại diện workload.

### Bài 38 — Audit trước backfill

Duplicate elements:

~~~sql
SELECT p.post_id,u.tag_id,COUNT(*) AS occurrences
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
GROUP BY p.post_id,u.tag_id
HAVING COUNT(*)>1;
~~~

Orphans:

~~~sql
SELECT DISTINCT p.post_id,u.tag_id
FROM array_lab.posts_array AS p
CROSS JOIN LATERAL unnest(p.tag_ids) AS u(tag_id)
LEFT JOIN array_lab.tags AS d ON d.tag_id=u.tag_id
WHERE d.tag_id IS NULL;
~~~

Cần quyết định cách xử lý từng loại sai lệch trước khi PK/FK ở bảng liên kết có thể nhận dữ liệu.

### Bài 39 — Migration với writes đang chạy

Quy trình:

1. Audit duplicates, orphan, NULL và các rules.
2. Tạo linked schema/PK/FK/indexes.
3. Backfill batches có checkpoint/retry.
4. Đồng bộ changes phát sinh qua dual-write trong transaction, triggers/CDC hoặc maintenance cutover có kiểm soát.
5. Verify theo **từng cặp post–tag**, không chỉ tổng số rows.
6. Dùng shadow reads/canary để so query results.
7. Chuyển source of truth có rollback.
8. Theo dõi drift và dọn array chỉ khi toàn bộ consumers đã chuyển.

Hai bảng cùng COUNT có thể chứa các **cặp khác nhau**; phải so set equality/anti-joins/checksums theo khóa.

### Bài 40 — Ba tình huống

**1. 3–8 mã cấu hình nhỏ, read-mostly:** cột `integer[]` với `NOT NULL DEFAULT '{}'`, kiểm soát duplicates/NULL và GIN cho `@>`/`&&` là ứng viên. Đo query selectivity, size, update overhead; nếu IDs cần FK mạnh thì xem bảng liên kết.

**2. Sản phẩm có hàng trăm categories, metadata và updates thường xuyên:** bảng liên kết `product_categories(product_id,category_id)`, PK composite, FKs, index đảo chiều `(category_id,product_id)`. Đo join throughput, báo cáo theo category, chi phí DML và storage. Mảng có thể là projection đọc nhưng không thay source of truth có constraints.

**3. Ordered playlist cho phép lặp:** bảng `playlist_items(playlist_id,item_id,position,created_by,...)` hoặc row ID riêng, PK/UNIQUE theo vị trí và FKs. Không dùng PK(playlist_id,item_id) nếu cùng item được phép lặp. Cần transaction/locking hoặc optimistic concurrency khi reorder; đo write contention. Array nhỏ có thể phục vụ cache/DTO nhưng không biểu diễn metadata và concurrency tốt như từng row.

---

## 38. Tài liệu PostgreSQL và từ khóa tra cứu

Khi cần đối chiếu theo phiên bản PostgreSQL đang sử dụng, tham khảo:

- [PostgreSQL — Array Types](https://www.postgresql.org/docs/current/arrays.html): khai báo, truy cập và sửa phần tử, array constructors, dimensions.
- [PostgreSQL — Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html): `@>`, `<@`, `&&`, `cardinality`, `array_position`, `unnest`.
- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, GIN, GiST, SP-GiST, BRIN.
- [PostgreSQL — GIN Indexes](https://www.postgresql.org/docs/current/gin.html): inverted index, operator classes, pending-list behavior, fastupdate.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `USING gin`, expression/partial indexes, concurrently.
- [PostgreSQL — Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html): thứ tự cột và phạm vi sử dụng composite indexes.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): PRIMARY KEY, UNIQUE, CHECK, FOREIGN KEY.
- [PostgreSQL — Query Planning Statistics](https://www.postgresql.org/docs/current/planner-stats.html): `pg_stats`, histogram/MCV và ước lượng chọn lọc.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): plan, actual rows/loops, BUFFERS, index vs sequential scans.
- [PostgreSQL — TOAST](https://www.postgresql.org/docs/current/storage-toast.html): cơ chế lưu giá trị có độ dài biến đổi.
- [PostgreSQL — MVCC](https://www.postgresql.org/docs/current/mvcc.html): transaction visibility, row versions.

Đường dẫn `/current/` có thể trỏ đến PostgreSQL major version khác môi trường thực. Khi một operator hoặc hành vi maintenance/DDL là yếu tố quyết định sản xuất, đối chiếu tài liệu **đúng major version** và thử trên staging.

---

## 39. Tổng kết

**Chỉ mục GIN giúp PostgreSQL tìm nhanh các phần tử nằm trong cột mảng; bảng liên kết giúp biểu diễn quan hệ nhiều–nhiều với ràng buộc dữ liệu rõ ràng. Hai lựa chọn giải quyết những lớp vấn đề khác nhau và không nên dùng thay thế nhau mà bỏ qua nghiệp vụ.**

Các điểm cần nhớ:

- SQL arrays là **giá trị có thứ tự, có thể trùng phần tử và có NULL**, không tự là set.
- Các array operators `@>`, `<@`, `&&` và `=` có semantics khác nhau; **`@>` không đếm multiplicity**.
- **GIN `array_ops`** phù hợp membership/overlap/containment trên SQL arrays. `element = ANY(array_col)` không phải cùng indexable array operator; hãy đo `@> ARRAY[element]` khi muốn GIN.
- **B-tree trên array** là so toàn array value, không phải inverted index; biểu thức `cardinality(array)` có thể cần expression/partial index riêng.
- GIN index không tạo FK, UNIQUE-per-element, giới hạn cardinality hay chuẩn hóa data. Nếu cần các invariants đó, phải có cơ chế khác hoặc dùng **bảng liên kết**.
- **Junction table** với `PRIMARY KEY(post_id,tag_id)` và hai FKs chống duplicate pairs/orphan references. Index đảo chiều `(tag_id,post_id)` phục vụ tìm posts theo tag.
- `EXISTS`, `NOT EXISTS` và `GROUP BY/HAVING` biểu diễn ANY/ALL/NONE trên bảng liên kết. Phải cẩn thận duplicate joins và **requested set rỗng**.
- Khi thay đổi một tag, array UPDATE có thể tạo row version/TOAST/GIN work, trong khi linked INSERT/DELETE thường tác động một row quan hệ; chiều ngược lại, array có thể đọc danh sách tags của một post rất tiện.
- Truy vấn thống kê theo tag, metadata trên link, quyền truy cập, đổi tên/xóa dictionary và nhiều writers đồng thời thường khiến **bảng liên kết** dễ bảo trì hơn.
- JSONB array, SQL array và linked relations có **operators và indexes khác nhau**; đừng dùng JSONB chỉ vì input API là JSON khi dữ liệu cần FK/unique.
- Tối ưu phải tính cả **độ trễ truy vấn, chi phí ghi, GIN pending list, VACUUM, total heap/index/TOAST storage, cache và concurrency**, không chỉ một lần EXPLAIN trên bảng nhỏ.
- Khi migration, **backfill + đồng bộ writes + so sánh từng cặp + cutover + rollback** quan trọng hơn script INSERT ... SELECT. Có thể trả array từ bảng liên kết bằng `ARRAY(SELECT ...)` mà không lưu hai sources of truth.

Quy trình thực hành: **xác định phần tử là thuộc tính hay quan hệ → chốt semantics NULL/duplicate/order/FK → chọn array + GIN hoặc junction + B-tree → viết query đúng ANY/ALL/NONE → đo EXPLAIN, thống kê và write overhead → chỉ giữ chỉ mục cần thiết → triển khai và giám sát consistency theo workload thực tế**.
