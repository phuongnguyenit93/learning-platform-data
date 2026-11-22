# Tìm vị trí, tách chuỗi và xử lý biểu thức chính quy theo phương ngữ

Trong cơ sở dữ liệu, dữ liệu văn bản không chỉ là tên người hay phần mô tả. Nhiều hệ thống lưu **mã giao dịch** như `ORD-2025-0017`, **địa chỉ email** như `an@example.com`, **danh sách nhãn** như `sql|java|backend` hoặc **dòng log** chứa mã lỗi và thời điểm. Khi truy vấn, chúng ta có thể cần tìm dấu phân cách nằm ở đâu, lấy một phần của chuỗi, tách các trường, kiểm tra một định dạng hoặc thay thế những đoạn khớp một mẫu.

SQL có các hàm xử lý chuỗi để làm việc đó, nhưng **tên hàm, cú pháp và khả năng biểu thức chính quy (regular expression/regex) khác nhau giữa các hệ quản trị**. Ví dụ, PostgreSQL có `POSITION`, `SPLIT_PART` và toán tử `~`; MySQL có `LOCATE`, `SUBSTRING_INDEX` và `REGEXP_SUBSTR`; SQL Server có `CHARINDEX` và `STRING_SPLIT`; Oracle có `INSTR` và họ hàm `REGEXP_*`; SQLite cung cấp `instr`, `substr` nhưng không có một bộ regex tích hợp tiêu chuẩn tương đương.

Bài này giải thích cách chọn công cụ đúng với ba mục tiêu **tìm vị trí → tách chuỗi → xử lý mẫu phức tạp**, thực hành đầy đủ trên **PostgreSQL**, sau đó đối chiếu với MySQL, SQL Server, Oracle Database và SQLite.

## 1. Phân biệt ba loại công việc

| Nhu cầu | Cách giải quyết thường phù hợp | Ví dụ |
|---|---|---|
| **Tìm vị trí** của một chuỗi con hoặc dấu phân cách | `POSITION`, `STRPOS`, `LOCATE`, `INSTR`, `CHARINDEX` | Dấu `@` bắt đầu ở ký tự thứ mấy trong email? |
| **Tách chuỗi theo dấu phân cách cố định** | `SPLIT_PART`, `STRING_SPLIT`, `SUBSTRING_INDEX`, `SUBSTR`/`SUBSTRING` | Lấy phần `2025` từ `ORD-2025-0017` |
| **Kiểm tra, trích xuất hoặc thay thế theo mẫu** | Regex: `REGEXP_LIKE`, `REGEXP_SUBSTR`, `REGEXP_REPLACE`, `~`, ... | Kiểm tra mã theo dạng ba chữ cái, dấu gạch ngang, bốn chữ số |

**Không phải mọi bài toán tìm kiếm chuỗi đều cần regex.** Nếu chỉ muốn lấy phần đứng sau một dấu `@` hoặc tách theo dấu `|` cố định, hàm tìm vị trí và tách chuỗi thường dễ đọc hơn. Regex phù hợp khi ký tự cần tìm **thay đổi theo một quy tắc**, chẳng hạn “một hoặc nhiều chữ số”, “khoảng trắng tùy ý” hoặc “mã phải khớp toàn bộ định dạng”.

Trước khi viết SQL, hãy làm rõ:

1. Cần **vị trí** (con số), **giá trị tách ra** (chuỗi), hay **các hàng** sau khi tách?
2. Có một dấu phân cách cố định hay nhiều biến thể?
3. Nếu không tìm thấy dấu phân cách, kết quả mong muốn là `NULL`, chuỗi ban đầu hay lỗi?
4. Dữ liệu có thể là `NULL`, chuỗi rỗng hoặc chứa nhiều dấu phân cách liên tiếp không?
5. Truy vấn phải chạy trên **DBMS và phiên bản** nào?

## 2. Dữ liệu mẫu cho các ví dụ PostgreSQL

Chạy các lệnh sau trong **database học tập riêng**, chẳng hạn qua `psql` hoặc trình soạn thảo SQL của PostgreSQL:

```sql
CREATE TABLE text_samples (
    id INTEGER PRIMARY KEY,
    external_code TEXT,
    tags TEXT,
    contact TEXT
);

INSERT INTO text_samples (id, external_code, tags, contact)
VALUES
    (1, 'ORD-2025-0017', 'sql|java|backend', 'an@example.com'),
    (2, 'ORD-2025-0018', 'database|report', 'binh@company.vn'),
    (3, 'REQ-2026-0005', 'sql|testing', 'not-an-email'),
    (4, 'ORD-2025-0020', NULL, NULL),
    (5, NULL, 'sql||advanced', 'chi@example.com');

SELECT id, external_code, tags, contact
FROM text_samples
ORDER BY id;
```

| id | external_code | tags | contact |
|---:|---|---|---|
| 1 | ORD-2025-0017 | sql\|java\|backend | an@example.com |
| 2 | ORD-2025-0018 | database\|report | binh@company.vn |
| 3 | REQ-2026-0005 | sql\|testing | not-an-email |
| 4 | ORD-2025-0020 | `NULL` | `NULL` |
| 5 | `NULL` | sql\|\|advanced | chi@example.com |

Các trường hợp được chọn có chủ đích: mã bắt đầu bằng `ORD` hoặc `REQ`; nhãn có số phần khác nhau; dòng 5 có **hai dấu `|` liền nhau** tạo một phần rỗng; có email thiếu `@` và ô dữ liệu `NULL`. Các truy vấn kết quả sau đây sử dụng đúng năm hàng này.

## 3. Tìm vị trí chuỗi con

### 3.1. POSITION và STRPOS trong PostgreSQL

`POSITION` theo cú pháp:

```sql
POSITION(chuoi_can_tim IN chuoi_nguon)
```

Ví dụ:

```sql
SELECT POSITION('2025' IN 'ORD-2025-0017') AS pos_year;
-- 5

SELECT POSITION('-' IN 'ORD-2025-0017') AS first_dash;
-- 4
```

PostgreSQL còn có hàm `STRPOS` với thứ tự đối số **chuỗi nguồn trước, chuỗi cần tìm sau**:

```sql
SELECT STRPOS('an@example.com', '@') AS at_pos;
-- 3
```

Các hàm tìm vị trí thường trả vị trí bắt đầu của **lần khớp đầu tiên**. Với `POSITION` và `STRPOS` của PostgreSQL:

- Vị trí bắt đầu ở **1**, không phải 0 như chỉ số chuỗi trong nhiều ngôn ngữ lập trình.
- Nếu **không tìm thấy** mẫu, kết quả là **0**.
- Nếu chuỗi nguồn hoặc mẫu cần tìm là `NULL`, kết quả thường là **`NULL`**.

Thử trên bảng mẫu:

```sql
SELECT
    id,
    external_code,
    POSITION('2025' IN external_code) AS year_pos,
    STRPOS(contact, '@') AS at_pos
FROM text_samples
ORDER BY id;
```

| id | year_pos | at_pos |
|---:|---:|---:|
| 1 | 5 | 3 |
| 2 | 5 | 5 |
| 3 | 0 | 0 |
| 4 | 5 | `NULL` |
| 5 | `NULL` | 4 |

**Phân biệt `0` với `NULL`:** `0` nghĩa là *có chuỗi nguồn nhưng không tìm thấy mẫu*; `NULL` nghĩa là *đầu vào chưa biết hoặc thiếu*, vì vậy không thể xác định vị trí.

### 3.2. Dùng vị trí để lọc dữ liệu

Tìm các dòng có dấu `@` trong `contact`:

```sql
SELECT id, contact
FROM text_samples
WHERE POSITION('@' IN contact) > 0
ORDER BY id;
-- id: 1, 2, 5
```

Điều kiện `> 0` loại các giá trị không có dấu `@`. Hàng `contact = NULL` cũng không được giữ, vì so sánh `NULL > 0` cho `UNKNOWN` và `WHERE` chỉ giữ điều kiện `TRUE`.

**Có dấu `@` chưa đủ để email hợp lệ.** Chuỗi `'a@@b'` cũng chứa dấu `@`; kiểm tra email thực tế còn liên quan quy tắc định dạng, chuẩn hóa, xác minh và yêu cầu sản phẩm.

### 3.3. Kết hợp POSITION với SUBSTRING

Muốn lấy phần **trước dấu `@`**:

```sql
SELECT
    id,
    contact,
    CASE
        WHEN POSITION('@' IN contact) > 0
        THEN SUBSTRING(contact FROM 1 FOR POSITION('@' IN contact) - 1)
        ELSE NULL
    END AS local_part
FROM text_samples
ORDER BY id;
```

Kết quả lần lượt: **`an`, `binh`, `NULL`, `NULL`, `chi`**.

Ở đây:

- `POSITION('@' IN contact)` xác định vị trí dấu phân cách.
- `SUBSTRING(contact FROM 1 FOR n)` lấy `n` ký tự từ vị trí 1.
- `CASE` chỉ gọi phép tách khi tìm thấy dấu phân cách; nếu không tìm thấy hoặc dữ liệu thiếu, kết quả là `NULL`.

Lấy phần **sau dấu `@`**:

```sql
SELECT
    id,
    CASE
        WHEN STRPOS(contact, '@') > 0
        THEN SUBSTRING(contact FROM STRPOS(contact, '@') + 1)
        ELSE NULL
    END AS domain_part
FROM text_samples
ORDER BY id;
```

Kết quả: **`example.com`, `company.vn`, `NULL`, `NULL`, `example.com`**.

Nếu thiếu dấu phân cách, nhiều cách viết ngây thơ như `SUBSTRING(contact FROM STRPOS(contact, '@') + 1)` sẽ bắt đầu ở vị trí 1 và trả **toàn bộ chuỗi không hợp lệ**. Bọc `CASE` giúp xử lý tình huống này có chủ đích.

## 4. Tách chuỗi theo dấu phân cách cố định

### 4.1. SPLIT_PART: lấy phần thứ N trong PostgreSQL

`SPLIT_PART` phù hợp khi biết **dấu phân cách** và muốn lấy một phần theo số thứ tự:

```sql
SPLIT_PART(chuoi_nguon, dau_phan_cach, so_thu_tu)
```

`so_thu_tu` thông thường bắt đầu từ **1**:

```sql
SELECT
    SPLIT_PART('ORD-2025-0017', '-', 1) AS loai,
    SPLIT_PART('ORD-2025-0017', '-', 2) AS nam,
    SPLIT_PART('ORD-2025-0017', '-', 3) AS so_hieu;
-- ORD | 2025 | 0017
```

Không cần regex cho định dạng đơn giản này. Tách trực tiếp dữ liệu trong bảng:

```sql
SELECT
    id,
    SPLIT_PART(external_code, '-', 1) AS prefix,
    SPLIT_PART(external_code, '-', 2) AS year_text,
    SPLIT_PART(external_code, '-', 3) AS serial_text
FROM text_samples
ORDER BY id;
```

Với ba phần của `ORD-2025-0017`, các giá trị là `ORD`, `2025` và `0017`. Chúng vẫn là **chuỗi**, vì vậy phần `0017` không bị mất số 0 ở đầu. Nếu dùng `CAST(... AS INTEGER)`, `0017` sẽ trở thành số `17`; chỉ chuyển kiểu khi đó là điều nghiệp vụ mong muốn.

### 4.2. Phần rỗng khác phần không tồn tại

Xem nhãn:

```sql
SELECT
    SPLIT_PART('sql|java|backend', '|', 2) AS second_a,
    SPLIT_PART('sql||advanced', '|', 2) AS second_b,
    SPLIT_PART('sql|java', '|', 3) AS third_c;
```

| second_a | second_b | third_c |
|---|---|---|
| java | `''` | `''` |

Trong PostgreSQL, phần thứ hai của `sql||advanced` là **chuỗi rỗng** do hai dấu `|` liền nhau. Còn phần thứ ba của `sql|java` không tồn tại nhưng `SPLIT_PART` cũng trả **chuỗi rỗng**. Nếu hai tình huống cần được phân biệt, không nên dựa một mình vào kết quả `SPLIT_PART`; cần kiểm tra số dấu phân cách hoặc dùng biểu diễn mảng/bảng với quy tắc dữ liệu rõ ràng.

Với `tags = NULL`, `SPLIT_PART(tags, '|', 1)` trả `NULL`, không phải chuỗi rỗng. Không tự động biến thiếu dữ liệu thành nhãn rỗng nếu chưa có quy tắc nghiệp vụ.

### 4.3. STRING_TO_ARRAY và UNNEST: tách thành nhiều hàng

Khi muốn phân tích toàn bộ nhãn, PostgreSQL có thể chuyển chuỗi thành **mảng**:

```sql
SELECT STRING_TO_ARRAY('sql|java|backend', '|') AS tag_array;
-- {sql,java,backend}
```

Để đưa các phần thành **nhiều hàng** với số thứ tự, kết hợp `UNNEST` và `WITH ORDINALITY`:

```sql
SELECT
    t.id,
    x.ordinality AS tag_position,
    x.tag
FROM text_samples AS t
CROSS JOIN LATERAL
    UNNEST(STRING_TO_ARRAY(t.tags, '|'))
    WITH ORDINALITY AS x(tag, ordinality)
WHERE t.id IN (1, 5)
ORDER BY t.id, x.ordinality;
```

| id | tag_position | tag |
|---:|---:|---|
| 1 | 1 | sql |
| 1 | 2 | java |
| 1 | 3 | backend |
| 5 | 1 | sql |
| 5 | 2 | `''` |
| 5 | 3 | advanced |

`WITH ORDINALITY` bổ sung cột vị trí; `ORDER BY` cuối câu truy vấn làm thứ tự hiển thị được xác định. Nếu nguồn `tags` là `NULL`, `UNNEST(STRING_TO_ARRAY(NULL, '|'))` không tạo phần tử để nối bằng `CROSS JOIN LATERAL`. Khi muốn giữ hàng nguồn không có nhãn, cần cân nhắc `LEFT JOIN LATERAL ... ON TRUE`.

**Lưu ý thiết kế dữ liệu:** nếu nhãn được truy vấn, lọc hoặc cập nhật thường xuyên, bảng quan hệ `sample_tags(sample_id, tag)` thường phù hợp hơn việc nhét mọi nhãn vào một cột văn bản với dấu `|`. Tách chuỗi hữu ích khi nạp dữ liệu bên ngoài hoặc làm sạch dữ liệu legacy, không phải lúc nào cũng là lựa chọn thiết kế lưu trữ tối ưu.

## 5. Khi nào cần biểu thức chính quy?

**Regex** diễn tả một **mẫu ký tự** thay vì một chuỗi cố định. Chẳng hạn:

- `[0-9]`: một chữ số từ 0 đến 9.
- `[0-9]{4}`: đúng bốn chữ số liên tiếp.
- `[A-Z]+`: một hoặc nhiều chữ cái từ A đến Z.
- `^` và `$`: neo ở đầu và cuối chuỗi (cần xem ngữ nghĩa neo và chế độ nhiều dòng của từng engine).
- `(...)`: nhóm biểu thức, thường được dùng để trích xuất các phần khớp.
- `[[:space:]]*`: không hoặc nhiều ký tự khoảng trắng theo lớp ký tự POSIX được hỗ trợ.

Bảng ký hiệu phổ biến:

| Ký hiệu mẫu | Ý nghĩa thường gặp | Minh họa |
|---|---|---|
| `^ABC` | Bắt đầu bằng ABC | `ABC-01` |
| `XYZ$` | Kết thúc bằng XYZ | `01-XYZ` |
| `[0-9]` | Một chữ số ASCII | `7` |
| `[A-Z]{3}` | Ba chữ cái in hoa ASCII | `ORD` |
| `.` | Một ký tự theo quy tắc regex engine | `a` |
| `*` | Lặp 0 hoặc nhiều lần | `a*` |
| `+` | Lặp 1 hoặc nhiều lần | `a+` |
| `?` | Có hoặc không có một lần | `a?` |
| `(foo\|bar)` | Một trong hai nhánh | `foo` hoặc `bar` |
| `[^|]+` | Một hoặc nhiều ký tự khác dấu `|` | `java` |

Regex có nhiều **phương ngữ**: các engine có thể khác nhau về lớp Unicode, tham chiếu nhóm, lookaround, cờ không phân biệt hoa/thường, xử lý xuống dòng hoặc cách escape ký tự. Một mẫu chạy trên PostgreSQL không mặc nhiên có cùng ý nghĩa trên MySQL, Oracle hay SQL Server.

### 5.1. LIKE không phải regex

SQL `LIKE` hỗ trợ hai ký tự đại diện thông dụng:

- `%`: không hoặc nhiều ký tự.
- `_`: đúng một ký tự.

Ví dụ:

```sql
SELECT id, external_code
FROM text_samples
WHERE external_code LIKE 'ORD-%'
ORDER BY id;
-- id: 1, 2, 4
```

Đó là tìm **tiền tố cố định**, không cần regex. Trong regex, ký hiệu `.*` thường dùng cho số lượng ký tự tùy ý; `%` của `LIKE` **không có cùng nghĩa** trong regex. Không trộn các mẫu `LIKE` và regex như thể chúng cùng cú pháp.

## 6. Regex trong PostgreSQL: so khớp, trích xuất, thay thế và tách

### 6.1. Kiểm tra cả chuỗi có đúng định dạng không

Giả sử mã đơn hợp lệ phải có dạng:

```text
ORD-YYYY-NNNN

Ví dụ: ORD-2025-0017
```

Trong đó `YYYY` và `NNNN` gồm đúng bốn chữ số. PostgreSQL sử dụng toán tử `~` để kiểm tra mẫu regex phân biệt hoa/thường:

```sql
SELECT id, external_code
FROM text_samples
WHERE external_code ~ '^ORD-[0-9]{4}-[0-9]{4}$'
ORDER BY id;
-- id: 1, 2, 4
```

Giải thích:

- `^ORD-` yêu cầu mã bắt đầu bằng đúng `ORD-`.
- `[0-9]{4}` yêu cầu đúng bốn chữ số.
- Dấu `-` tiếp theo là ký tự phân cách cố định.
- `[0-9]{4}$` yêu cầu bốn chữ số cuối và kết thúc chuỗi.

Nếu bỏ neo `^` hoặc `$`, regex có thể khớp **một phần** của chuỗi dài hơn, khiến mã có tiền tố/hậu tố thừa được chấp nhận. Trong kiểm tra định dạng toàn chuỗi, hai neo thường rất quan trọng.

Các toán tử hữu ích của PostgreSQL:

| Toán tử | Ý nghĩa |
|---|---|
| `text ~ pattern` | Khớp regex, phân biệt hoa/thường |
| `text ~* pattern` | Khớp regex, không phân biệt hoa/thường |
| `text !~ pattern` | Không khớp regex, phân biệt hoa/thường |
| `text !~* pattern` | Không khớp regex, không phân biệt hoa/thường |

Khi `external_code` là `NULL`, các phép so khớp thông thường trả `NULL`/`UNKNOWN`, nên `WHERE` không giữ hàng đó. Nếu nghiệp vụ muốn coi `NULL` là không hợp lệ, có thể biểu diễn:

```sql
WHERE external_code IS NULL
   OR external_code !~ '^ORD-[0-9]{4}-[0-9]{4}$'
```

Với dữ liệu mẫu, biểu thức này trả **id 3 và id 5**. Kết quả phản ánh đúng hai loại lỗi: sai định dạng và thiếu mã.

### 6.2. Trích xuất một đoạn khớp regex

`SUBSTRING(... FROM pattern)` của PostgreSQL có biến thể sử dụng regex:

```sql
SELECT
    id,
    external_code,
    SUBSTRING(external_code FROM '[0-9]{4}$') AS last_four_digits
FROM text_samples
ORDER BY id;
```

| id | last_four_digits |
|---:|---|
| 1 | 0017 |
| 2 | 0018 |
| 3 | 0005 |
| 4 | 0020 |
| 5 | `NULL` |

Phép trích xuất trả **chuỗi**, vì vậy số 0 ở đầu được giữ. Lưu ý ví dụ trên trích xuất bốn chữ số cuối của cả mã `REQ`; **trích xuất được một đoạn không đồng nghĩa cả mã đã hợp lệ theo mẫu `ORD`**. Khi cần bảo đảm đúng định dạng, hãy kiểm tra toàn chuỗi trước.

Để lấy nhiều nhóm, PostgreSQL có `REGEXP_MATCH`:

```sql
SELECT
    id,
    REGEXP_MATCH(
        external_code,
        '^([A-Z]+)-([0-9]{4})-([0-9]{4})$'
    ) AS code_parts
FROM text_samples
WHERE id = 1;
-- code_parts: {ORD,2025,0017}
```

Các cặp ngoặc tạo **ba nhóm bắt**: tiền tố, năm và số hiệu. `REGEXP_MATCH` trả một **mảng văn bản** trong PostgreSQL; muốn đưa thành ba cột, có thể truy cập phần tử mảng (PostgreSQL đánh số mảng mặc định từ 1). Nếu không khớp hoặc chuỗi nguồn là `NULL`, kết quả là `NULL`.

### 6.3. Thay thế mọi đoạn khớp regex

`REGEXP_REPLACE` thay những đoạn khớp một mẫu:

```sql
SELECT REGEXP_REPLACE('a1b2c3', '[0-9]', '', 'g') AS letters_only;
-- abc
```

Trong PostgreSQL, đối số `'g'` là cờ **global**: thay **tất cả** các vị trí khớp, không chỉ vị trí đầu tiên. So sánh:

```sql
SELECT
    REGEXP_REPLACE('a1b2c3', '[0-9]', '') AS first_only,
    REGEXP_REPLACE('a1b2c3', '[0-9]', '', 'g') AS every_match;
-- first_only: ab2c3
-- every_match: abc
```

Một tình huống khác là chuẩn hóa khoảng trắng trong văn bản nhập:

```sql
SELECT REGEXP_REPLACE(
    '  SQL   va    Database  ',
    '[[:space:]]+',
    ' ',
    'g'
) AS normalized_spaces;
-- ' SQL va Database ' (vẫn còn một khoảng trắng ở đầu và cuối)
```

Nếu muốn bỏ cả khoảng trắng ở hai đầu, có thể bọc thêm `BTRIM(...)`:

```sql
SELECT BTRIM(REGEXP_REPLACE(
    '  SQL   va    Database  ',
    '[[:space:]]+',
    ' ',
    'g'
)) AS normalized_text;
-- 'SQL va Database'
```

Những thao tác này chỉ làm thay đổi **kết quả biểu thức**. Muốn cập nhật dữ liệu lưu trong bảng phải dùng `UPDATE ... SET col = REGEXP_REPLACE(...)` sau khi đã xác định phạm vi và quy tắc nghiệp vụ.

### 6.4. Tách bằng nhiều dấu phân cách

Nếu dữ liệu dùng cả dấu phẩy và dấu chấm phẩy, còn khoảng trắng có thể xuất hiện tùy ý, một dấu phân cách cố định là chưa đủ. PostgreSQL cung cấp:

```sql
SELECT REGEXP_SPLIT_TO_TABLE(
    'sql, java; database',
    '[[:space:]]*[,;][[:space:]]*'
) AS token;
```

Kết quả gồm ba hàng: **`sql`**, **`java`**, **`database`**.

Ở đây:

- `[,;]` khớp một dấu phẩy hoặc một dấu chấm phẩy.
- `[[:space:]]*` ở hai bên cho phép bỏ khoảng trắng liền kề dấu phân cách.
- `REGEXP_SPLIT_TO_TABLE` trả **nhiều hàng**; `REGEXP_SPLIT_TO_ARRAY` trả **mảng**.

Tách bằng dấu `|` cố định cũng có thể viết:

```sql
SELECT REGEXP_SPLIT_TO_ARRAY('sql|java|backend', '[|]');
-- {sql,java,backend}
```

Ở regex, dấu `|` thường có nghĩa **hoặc** (alternation). Đặt nó trong lớp ký tự `[|]` giúp khớp **dấu gạch đứng literal**, tránh nhầm với toán tử regex.

### 6.5. Trích xuất nhiều lần khớp

Khi một văn bản chứa nhiều mã số, `REGEXP_MATCHES` với cờ `'g'` có thể trả nhiều hàng:

```sql
SELECT REGEXP_MATCHES(
    'id=12; id=34; id=56',
    'id=([0-9]+)',
    'g'
) AS captured_id;
```

Kết quả là ba hàng mảng: **`{12}`**, **`{34}`**, **`{56}`**. Hàm này trả tập kết quả (*set-returning function*), khác với `REGEXP_MATCH` chỉ trả kết quả của lần khớp đầu tiên. Nếu ứng dụng cần danh sách các vị trí và nội dung khớp, phải chọn hàm phù hợp với phiên bản PostgreSQL và cách tổ chức kết quả mong muốn.

## 7. Đối chiếu cú pháp giữa các phương ngữ SQL

Để tránh học thuộc một câu lệnh rồi áp dụng sai trên DBMS khác, hãy xem các lựa chọn thường gặp:

| Hệ quản trị | Tìm vị trí chuỗi con | Tách chuỗi | Regex tiêu biểu |
|---|---|---|---|
| **PostgreSQL** | `POSITION(sub IN s)`, `STRPOS(s, sub)` | `SPLIT_PART`, `STRING_TO_ARRAY`, `REGEXP_SPLIT_TO_TABLE` | `~`, `~*`, `REGEXP_MATCH`, `REGEXP_REPLACE` |
| **MySQL 8.0** | `LOCATE(sub, s)`, `INSTR(s, sub)` | `SUBSTRING_INDEX`; kết hợp nhiều lần cho phần thứ N | `REGEXP_LIKE`, `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_REPLACE` |
| **SQL Server** | `CHARINDEX(sub, s)` | `STRING_SPLIT` trả hàng; `SUBSTRING` + `CHARINDEX` cho phần cụ thể | Khả năng regex bản địa phụ thuộc phiên bản/nền tảng; `LIKE`/`PATINDEX` không phải regex đầy đủ |
| **Oracle Database** | `INSTR(s, sub[, start[, occurrence]])` | `SUBSTR`, `INSTR`, `REGEXP_SUBSTR` | `REGEXP_LIKE`, `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_REPLACE` |
| **SQLite** | `instr(s, sub)` | `substr`, CTE đệ quy hoặc xử lý ở ứng dụng | Không có bộ hàm regex đầy đủ mặc định; có thể bổ sung extension/hàm người dùng |

Đa số hàm tìm vị trí thông dụng trong bảng trên **đánh số ký tự từ 1** và trả **0 khi không tìm thấy**; tuy vậy, hãy kiểm tra hành vi đối với chuỗi rỗng, `NULL`, vị trí bắt đầu, kiểu nhị phân và ký tự Unicode của **hàm và phiên bản cụ thể**. Thứ tự đối số cũng khác nhau: `LOCATE(sub, s)` của MySQL **ngược** `STRPOS(s, sub)` của PostgreSQL.

### 7.1. MySQL 8.0: LOCATE, SUBSTRING_INDEX và REGEXP_*

Tìm vị trí:

```sql
-- MySQL
SELECT LOCATE('2025', 'ORD-2025-0017') AS pos_year;
-- 5

SELECT INSTR('an@example.com', '@') AS at_pos;
-- 3
```

`LOCATE(substr, str[, pos])` cho phép truyền vị trí bắt đầu tìm kiếm. `INSTR(str, substr)` nhận chuỗi nguồn ở đối số đầu tiên.

Để lấy phần thứ hai trong chuỗi có dấu `|`:

```sql
-- MySQL
SELECT SUBSTRING_INDEX(
    SUBSTRING_INDEX('sql|java|backend', '|', 2),
    '|',
    -1
) AS second_tag;
-- java
```

`SUBSTRING_INDEX(str, delim, count)` với `count > 0` lấy phần **bên trái đến trước lần xuất hiện thứ `count`** của dấu phân cách; với `count < 0` lấy từ phía bên phải. Kết hợp hai lần có thể lấy phần thứ N. Nhưng nếu chuỗi **thiếu dấu phân cách**, một số trường hợp sẽ trả cả chuỗi nguồn hoặc phần không mong đợi; cần kiểm tra định dạng trước khi dùng như parser tổng quát.

MySQL 8.0 cung cấp các hàm regex dựa trên engine hỗ trợ Unicode:

```sql
-- MySQL 8.0
SELECT REGEXP_LIKE(
    'ORD-2025-0017',
    '^ORD-[0-9]{4}-[0-9]{4}$'
) AS valid_code;
-- 1 (đúng)

SELECT REGEXP_SUBSTR(
    'ORD-2025-0017',
    '[0-9]{4}$'
) AS serial_text;
-- 0017

SELECT REGEXP_REPLACE('a1b2c3', '[0-9]', '') AS letters_only;
-- abc
```

**Khác PostgreSQL:** `REGEXP_REPLACE` trong MySQL 8.0 thay **tất cả lần khớp theo mặc định**; PostgreSQL cần cờ `'g'` để thay tất cả trong dạng hàm ba đối số. Các hàm regex MySQL có thêm tham số vị trí, lần xuất hiện và `match_type` tùy hàm; ví dụ cờ `'i'` hoặc `'c'` có thể ảnh hưởng phân biệt hoa/thường. Hành vi còn phụ thuộc kiểu chuỗi và collation, vì vậy không giả định regex luôn cùng quy tắc với PostgreSQL.

### 7.2. SQL Server: CHARINDEX, STRING_SPLIT, PATINDEX

Tìm vị trí:

```sql
-- SQL Server
SELECT CHARINDEX('2025', 'ORD-2025-0017') AS pos_year;
-- 5

SELECT CHARINDEX('@', 'not-an-email') AS at_pos;
-- 0
```

`CHARINDEX(expressionToFind, expressionToSearch[, start_location])` nhận mẫu cần tìm trước, chuỗi nguồn sau.

Tách danh sách thành **nhiều hàng**:

```sql
-- SQL Server 2022+ và những nền tảng hỗ trợ enable_ordinal
SELECT value, ordinal
FROM STRING_SPLIT('sql|java|backend', '|', 1)
ORDER BY ordinal;
```

| value | ordinal |
|---|---:|
| sql | 1 |
| java | 2 |
| backend | 3 |

`STRING_SPLIT` nhận chuỗi nguồn và dấu phân cách; **các hàng do `STRING_SPLIT` trả về không có thứ tự được bảo đảm**. Tham số thứ ba `1` yêu cầu cột `ordinal` trên **những phiên bản hỗ trợ** (chẳng hạn SQL Server 2022 trở lên với cấu hình phù hợp); cần thêm `ORDER BY ordinal` nếu muốn đúng thứ tự ban đầu. Ở phiên bản cũ hơn, `STRING_SPLIT` có thể không hỗ trợ tham số thứ ba và không cung cấp ordinal.

`PATINDEX` tìm vị trí theo mẫu **`LIKE`**, không phải một engine regex đầy đủ:

```sql
-- SQL Server
SELECT PATINDEX('%[0-9]%', 'code-A7') AS first_digit_pos;
-- 7
```

Ký hiệu `[0-9]` ở đây thuộc **cú pháp mẫu của SQL Server/LIKE**, không có nghĩa rằng `PATINDEX` hỗ trợ đầy đủ `+`, `{4}`, nhóm bắt hoặc lookaround như regex. Các phiên bản/nền tảng SQL Server mới có thể cung cấp thêm hàm regex bản địa; phải kiểm tra **phiên bản, mức tương thích và tài liệu tính năng** trước khi dùng, thay vì giả định mọi SQL Server đều hỗ trợ hoặc đều không hỗ trợ regex.

### 7.3. Oracle Database: INSTR, SUBSTR và REGEXP_SUBSTR

Tìm vị trí:

```sql
-- Oracle
SELECT INSTR('ORD-2025-0017', '2025') AS pos_year
FROM dual;
-- 5
```

`INSTR(source, substring[, position[, occurrence]])` có thể tìm **lần xuất hiện thứ N** và cho phép điều khiển hướng tìm bằng tham số vị trí. `SUBSTR(source, start[, length])` lấy một phần chuỗi theo vị trí.

Để tách phần thứ hai bằng regex:

```sql
-- Oracle
SELECT REGEXP_SUBSTR('sql|java|backend', '[^|]+', 1, 2) AS second_tag
FROM dual;
-- java
```

Biểu thức `[^|]+` lấy **nhóm ký tự không phải `|`, có ít nhất một ký tự**. Nó **bỏ qua các phần rỗng**: với `sql||advanced`, lần khớp thứ hai của mẫu này là `advanced`, không phải chuỗi rỗng ở giữa hai dấu. Nếu cần bảo toàn phần rỗng, phải dùng kỹ thuật tách khác và định nghĩa rõ quy tắc.

Một vài hàm regex:

```sql
-- Oracle
SELECT REGEXP_SUBSTR(
    'ORD-2025-0017',
    '[0-9]{4}$'
) AS serial_text
FROM dual;
-- 0017

SELECT REGEXP_REPLACE(
    'a1b2c3',
    '[0-9]',
    ''
) AS letters_only
FROM dual;
-- abc
```

Trong Oracle, `REGEXP_REPLACE` có thể thay tất cả lần khớp khi không chỉ định lần xuất hiện. Một điểm đặc thù khác: trong nhiều thao tác dữ liệu ký tự của Oracle, **chuỗi rỗng `''` được xem như `NULL`**; vì vậy việc phân biệt phần rỗng với phần thiếu có thể khác PostgreSQL. Đây là lý do cần thử dữ liệu biên trước khi chuyển một parser giữa các DBMS.

### 7.4. SQLite: instr, substr và giới hạn regex mặc định

SQLite cung cấp hai hàm cơ bản:

```sql
-- SQLite
SELECT instr('ORD-2025-0017', '2025') AS pos_year;
-- 5

SELECT substr('ORD-2025-0017', 5, 4) AS year_text;
-- 2025
```

`instr` trả vị trí tìm thấy đầu tiên (bắt đầu từ 1) hoặc 0 nếu không thấy; `substr` lấy phần chuỗi theo vị trí. SQLite không cung cấp sẵn một hàm `SPLIT_PART` hay `STRING_SPLIT` phổ quát. Nếu bắt buộc tách thành hàng chỉ bằng SQLite SQL, có thể dùng **CTE đệ quy**:

```sql
-- SQLite: tách chuỗi theo dấu | và giữ thứ tự
WITH RECURSIVE parts(pos, rest, part) AS (
    SELECT 0, 'sql|java|backend|', NULL
    UNION ALL
    SELECT
        pos + 1,
        substr(rest, instr(rest, '|') + 1),
        substr(rest, 1, instr(rest, '|') - 1)
    FROM parts
    WHERE rest <> ''
)
SELECT pos, part
FROM parts
WHERE pos > 0
ORDER BY pos;
```

Kết quả: `(1, sql)`, `(2, java)`, `(3, backend)`. Ở đây ta thêm dấu `|` cuối chuỗi để thuật toán lấy được phần cuối. Đoạn mã minh họa trường hợp đơn giản có dấu phân cách một ký tự; với dữ liệu lớn, đầu vào rỗng, dấu phân cách phức tạp hoặc yêu cầu hiệu năng, nên lựa chọn chiến lược phù hợp hơn.

SQLite có cú pháp `REGEXP` như một điểm mở rộng, nhưng **hàm xử lý `regexp` không được tích hợp mặc định trong mọi bản cài đặt**. Muốn sử dụng phải cung cấp hàm/extension tương ứng. Không dựa vào sự tồn tại của regex khi triển khai lên một bản SQLite khác nếu chưa kiểm soát extension.

## 8. Những khác biệt phải hiểu trước khi chuyển phương ngữ

### 8.1. Vị trí bắt đầu và giá trị không tìm thấy

| Tình huống | Kết quả thường gặp | Hàm ví dụ |
|---|---|---|
| Mẫu nằm tại ký tự đầu tiên | `1` | `POSITION('A' IN 'ABC')` |
| Mẫu nằm giữa chuỗi | Vị trí `>= 2` | `STRPOS('ABC', 'B') = 2` |
| Không có mẫu trong chuỗi đã biết | `0` | `CHARINDEX('@', 'abc') = 0` |
| Chuỗi nguồn là `NULL` | `NULL` | `STRPOS(NULL, '@')` |

Không dùng vị trí 0 như vị trí ký tự đầu tiên. Với dữ liệu Unicode, cách đếm ký tự, code point, byte và độ dài có thể khác nhau giữa kiểu dữ liệu và các hàm. Đừng trộn `LENGTH`/`CHAR_LENGTH`, độ dài byte, `SUBSTRING` và vị trí nhận được từ hàm khác khi chúng không cùng đơn vị đo.

### 8.2. Quy tắc escape trong chuỗi SQL và regex

Một regex đi qua **hai lớp cú pháp**: SQL literal và ngôn ngữ regex. Ví dụ, dấu `|` có nghĩa **hoặc** trong regex nên muốn khớp ký tự `|` có thể dùng `[|]`. Dấu gạch chéo ngược `\` cũng có quy tắc escape riêng tùy DBMS, chế độ chuỗi SQL và regex engine.

Để những ví dụ đơn giản dễ di chuyển, bài này dùng `[0-9]` và `[[:space:]]` thay vì giả định mọi phương ngữ đều nhận `\d` hoặc `\s` giống nhau. Khi viết regex phức tạp, kiểm tra cách escape dấu gạch chéo, dấu nháy đơn và các ký tự đặc biệt trên **DBMS thật**, không chỉ trong một trình thử regex trên web.

### 8.3. Chuỗi rỗng, NULL và phần tách rỗng

Ba trường hợp có thể mang ý nghĩa khác nhau:

| Đầu vào | Ý nghĩa ví dụ |
|---|---|
| `NULL` | Chưa có chuỗi nguồn |
| `''` | Có chuỗi nhưng rỗng |
| `'a||c'` | Có ba vị trí phần tách, phần thứ hai rỗng |

PostgreSQL cho phép phân biệt `NULL` và `''`; còn Oracle thường coi `''` là `NULL` đối với chuỗi ký tự. Một số hàm tách có thể **bỏ qua** phần rỗng. Nếu xử lý định dạng dữ liệu giữa nhiều DBMS, phải xác định rõ cách biểu diễn phần thiếu và phần rỗng.

### 8.4. Phân biệt hoa/thường và collation

`'abc'` so với `'ABC'` có thể được xem là bằng hoặc khác tùy kiểu dữ liệu, collation, hàm và cờ. Với regex:

- PostgreSQL có `~` và `~*` để chọn phân biệt hoặc không phân biệt hoa/thường.
- MySQL `REGEXP_LIKE` có thể dùng `match_type`, còn collation cũng tác động.
- Oracle `REGEXP_LIKE` hỗ trợ tham số kiểm soát cách so khớp, chẳng hạn `'i'` cho không phân biệt hoa/thường theo các quy tắc áp dụng.
- SQL Server `CHARINDEX` và `PATINDEX` chịu ảnh hưởng collation; regex bản địa nếu có phải xem tài liệu phiên bản.

Không dùng phép chuyển `LOWER` hoặc cờ `i` như một bảo đảm tuyệt đối cho mọi bảng chữ cái Unicode. Với mã định danh nghiệp vụ, nên thống nhất chuẩn lưu trữ và quy tắc so khớp.

### 8.5. Một regex phù hợp trên DBMS này có thể không phù hợp nơi khác

Các engine khác nhau ở nhóm bắt, backreference, lookahead/lookbehind, lớp ký tự Unicode, chế độ nhiều dòng, cờ toàn cục và giới hạn độ dài mẫu. Chẳng hạn:

- PostgreSQL yêu cầu cờ `'g'` để `REGEXP_REPLACE` thay **tất cả** trong cú pháp ba đối số mở rộng.
- MySQL 8.0 và Oracle có hành vi thay nhiều lần khớp mặc định tương ứng của chúng.
- `PATINDEX` trong SQL Server là mẫu kiểu `LIKE`, không thay thế mọi chức năng regex.
- SQLite cần extension hoặc hàm do ứng dụng cung cấp nếu muốn regex.

Vì vậy, khi chuyển một truy vấn sang DBMS khác, hãy kiểm tra **cả ý nghĩa đầu ra và các trường hợp biên**, không chỉ thay tên hàm.

## 9. Ví dụ nghiệp vụ: phân tích mã và dữ liệu nhập

### 9.1. Chỉ nhận mã đơn đúng mẫu, rồi tách từng phần

Giả sử hệ thống chỉ muốn xử lý mã `ORD-YYYY-NNNN`. Dùng regex để **kiểm tra**, sau đó dùng hàm tách đơn giản để **lấy phần**:

```sql
-- PostgreSQL
SELECT
    id,
    external_code,
    SPLIT_PART(external_code, '-', 2) AS year_text,
    SPLIT_PART(external_code, '-', 3) AS serial_text
FROM text_samples
WHERE external_code ~ '^ORD-[0-9]{4}-[0-9]{4}$'
ORDER BY id;
```

| id | external_code | year_text | serial_text |
|---:|---|---|---|
| 1 | ORD-2025-0017 | 2025 | 0017 |
| 2 | ORD-2025-0018 | 2025 | 0018 |
| 4 | ORD-2025-0020 | 2025 | 0020 |

Đây là mẫu phối hợp rất thực tế: **regex cho điều kiện định dạng**, **SPLIT_PART cho phần dữ liệu có vị trí đã biết**. Nếu chỉ tách mà không kiểm tra, một chuỗi sai cấu trúc vẫn có thể tạo ra các phần có vẻ hợp lệ.

### 9.2. Tách domain từ email để thống kê sơ bộ

```sql
-- PostgreSQL
WITH parsed AS (
    SELECT
        id,
        CASE WHEN STRPOS(contact, '@') > 0
             THEN SUBSTRING(contact FROM STRPOS(contact, '@') + 1)
             ELSE NULL
        END AS domain_part
    FROM text_samples
)
SELECT domain_part, COUNT(*) AS contact_count
FROM parsed
WHERE domain_part IS NOT NULL
GROUP BY domain_part
ORDER BY contact_count DESC, domain_part;
```

Kết quả:

| domain_part | contact_count |
|---|---:|
| example.com | 2 |
| company.vn | 1 |

Đây chỉ là **thống kê thử trên chuỗi có dấu @**, không phải quá trình xác thực email hoàn chỉnh. Với dữ liệu thực tế, cần xử lý trường hợp nhiều dấu `@`, tên miền rỗng, khoảng trắng, định dạng quốc tế và yêu cầu xác minh.

### 9.3. Làm sạch mã nhập không đồng nghĩa sửa đúng dữ liệu

Thay toàn bộ ký tự không phải chữ và số:

```sql
-- PostgreSQL: ví dụ minh họa biến đổi chuỗi
SELECT REGEXP_REPLACE(
    'AB-12 / 34',
    '[^A-Za-z0-9]',
    '',
    'g'
) AS compact_code;
-- AB1234
```

Thao tác này có thể hữu ích với một quy ước mã cho phép bỏ dấu phân cách, nhưng cũng có thể **gộp những giá trị vốn khác nhau** thành cùng một chuỗi. Ví dụ `'AB-12'` và `'AB 12'` cùng thành `'AB12'`. Không áp dụng làm sạch tự động cho khóa nghiệp vụ nếu chưa xác định quy tắc và rủi ro trùng lặp.

## 10. Hiệu năng và an toàn khi xử lý chuỗi

### 10.1. Ưu tiên biểu thức đơn giản đủ giải quyết bài toán

Nếu điều kiện chỉ là tiền tố cố định, `LIKE 'ORD-%'` có thể dễ hiểu hơn regex `'^ORD-.*'`. Nếu chỉ có một dấu phân cách cố định, `SPLIT_PART` hoặc `SUBSTRING_INDEX` thường dễ đọc hơn mẫu regex dài. Điều này cũng giúp code dễ chuyển phương ngữ và dễ kiểm thử.

Regex có thể đắt khi xử lý chuỗi dài hoặc nhiều hàng, nhất là với các mẫu có nhiều nhánh và lặp lồng nhau. Không kết luận một regex sẽ nhanh chỉ vì câu lệnh ngắn. Cần đo kế hoạch thực thi và thời gian trên dữ liệu đại diện.

### 10.2. Hàm trên cột và khả năng dùng chỉ mục

Ví dụ:

```sql
-- PostgreSQL
WHERE LOWER(contact) = 'an@example.com'
```

Hàm `LOWER(contact)` tính biểu thức từ giá trị cột. Một chỉ mục B-tree thông thường trên `contact` **không nhất thiết** phục vụ trực tiếp điều kiện đó; có thể cần chỉ mục biểu thức, kiểu dữ liệu/collation phù hợp hoặc cách tìm khác. Tương tự, tìm regex không được bảo đảm sử dụng chỉ mục B-tree thông thường.

PostgreSQL có những loại chỉ mục và extension hỗ trợ một số phép tìm văn bản, nhưng lựa chọn phụ thuộc mẫu truy vấn, dữ liệu, khối lượng ghi và kế hoạch tối ưu. Bài thực hành nhỏ không cần tạo chỉ mục; với hệ thống lớn, nên xem `EXPLAIN` và đo trên dữ liệu đại diện trước khi tối ưu.

### 10.3. Không ghép chuỗi đầu vào trực tiếp vào SQL

Nếu người dùng cung cấp mẫu tìm kiếm hoặc giá trị cần tìm, ứng dụng nên dùng **prepared statement/truy vấn có tham số**. Ví dụ với JDBC:

```java
String sql = """
    SELECT id, contact
    FROM text_samples
    WHERE contact LIKE ?
    ORDER BY id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "%@example.com");
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("id") + ": "
                    + rs.getString("contact"));
        }
    }
}
```

Đoạn Java minh họa cần `Connection` và import JDBC tương ứng để chạy hoàn chỉnh. Tham số hóa giúp giá trị không bị hiểu thành cú pháp SQL. Nhưng nếu người dùng tự nhập **mẫu `LIKE` hoặc regex**, tham số hóa **không vô hiệu hóa ký tự đặc biệt trong chính ngôn ngữ mẫu**; ứng dụng vẫn cần quyết định người dùng được tìm literal hay được nhập pattern, giới hạn độ dài và độ phức tạp khi cần.

### 10.4. Đừng dùng regex thay thế toàn bộ mô hình dữ liệu

Một cột `tags` chứa `sql|java|backend` có thể tiện để nhập dữ liệu mẫu, nhưng nếu hệ thống cần truy vấn “mọi bài có thẻ Java”, kiểm tra khóa ngoại đến danh mục thẻ, xóa một thẻ cụ thể hay xây dựng chỉ mục, **bảng liên kết quan hệ** thường phù hợp hơn.

Tương tự, một mã hóa đơn có thể được tạo từ các phần độc lập (`type`, `year`, `serial`) nhưng việc **tách lại từ một chuỗi đã ghép** không phải lúc nào cũng nên là nguồn sự thật cho nghiệp vụ. Có thể lưu các thành phần có ý nghĩa ở các cột riêng rồi tạo chuỗi hiển thị khi cần.

## 11. Những lỗi thường gặp

**Nhầm vị trí bắt đầu từ 0 và 1.** SQL text functions thường trả vị trí đầu tiên là 1; “không tìm thấy” là 0. Đừng dùng 0 như chỉ số đầu tiên khi tính `SUBSTRING`.

**Đổi thứ tự đối số giữa các phương ngữ.** PostgreSQL `STRPOS(source, needle)`, MySQL `LOCATE(needle, source)` và SQL Server `CHARINDEX(needle, source)` không cùng thứ tự tham số. Kiểm tra chữ ký hàm.

**Tách chuỗi mà không kiểm tra cấu trúc.** Nếu thiếu dấu phân cách, hàm có thể trả cả chuỗi hoặc phần rỗng, khiến ứng dụng hiểu sai dữ liệu. Hãy xác định cách xử lý khi không đủ phần.

**Cho rằng chuỗi rỗng và NULL luôn giống nhau.** PostgreSQL phân biệt hai giá trị; Oracle có những khác biệt đáng kể. Đặc biệt các phần tách rỗng cần được giải quyết rõ ràng.

**Cho rằng SUBSTRING_INDEX và SPLIT_PART có cùng cú pháp.** `SPLIT_PART` chọn phần thứ N từ trái; `SUBSTRING_INDEX` chọn phần ở bên trái/bên phải theo số lần dấu phân cách và có thể cần lồng hai lần để lấy phần giữa.

**Dùng dấu `|` trực tiếp trong regex khi muốn tách literal.** Trong nhiều regex engine, `|` là phép chọn nhánh. Dùng `[|]` hoặc cú pháp escape đúng engine.

**Nhầm LIKE với regex.** `LIKE 'ORD-%'` dùng ký tự `%`; regex `'^ORD-.*'` dùng `.*`. `PATINDEX` của SQL Server cũng không phải regex đầy đủ.

**Quên thay thế toàn cục.** PostgreSQL `REGEXP_REPLACE` không có cờ `'g'` thường chỉ thay lần khớp đầu tiên; MySQL/Oracle có hành vi và đối số riêng.

**Nhầm regex khớp một phần với kiểm tra định dạng toàn chuỗi.** Một mẫu `[0-9]{4}` tìm thấy bốn chữ số ở bất cứ đâu; muốn kiểm tra mã `ORD-YYYY-NNNN` phải dùng mẫu và neo phù hợp.

**Bỏ qua phiên bản DBMS.** Một số hàm regex hoặc khả năng lấy ordinal trong kết quả tách chỉ có ở các phiên bản nhất định. Truy vấn hợp lệ ở máy phát triển không nhất thiết chạy trên phiên bản cũ.

## 12. Bài tập thực hành

### Bài 1 — Tìm vị trí và phân biệt không tìm thấy với NULL

Với bảng `text_samples`, chạy:

```sql
SELECT id,
       POSITION('2025' IN external_code) AS pos
FROM text_samples
ORDER BY id;
```

Dự đoán kết quả `pos` theo id từ 1 đến 5. **Đáp án:** `5, 5, 0, 5, NULL`. Giải thích vì sao id 3 trả 0 nhưng id 5 trả `NULL`.

### Bài 2 — Tách phần từ mã định danh

Viết truy vấn lấy `prefix`, `year_text` và `serial_text` của những mã hợp lệ `ORD-YYYY-NNNN` bằng `SPLIT_PART`. Chỉ lấy các hàng hợp lệ bằng regex.

```sql
SELECT id,
       SPLIT_PART(external_code, '-', 1) AS prefix,
       SPLIT_PART(external_code, '-', 2) AS year_text,
       SPLIT_PART(external_code, '-', 3) AS serial_text
FROM text_samples
WHERE external_code ~ '^ORD-[0-9]{4}-[0-9]{4}$'
ORDER BY id;
```

**Đáp án:** id **1, 2, 4**; `serial_text` lần lượt là `0017`, `0018` và `0020`. Vì là chuỗi, chúng giữ số 0 ở đầu.

### Bài 3 — Phần rỗng khi tách

Trên `tags = 'sql||advanced'`:

```sql
SELECT
    SPLIT_PART('sql||advanced', '|', 1) AS part_1,
    SPLIT_PART('sql||advanced', '|', 2) AS part_2,
    SPLIT_PART('sql||advanced', '|', 3) AS part_3;
```

**Đáp án:** `'sql'`, `''`, `'advanced'`. Hãy giải thích vì sao không nên tự bỏ phần rỗng nếu số thứ tự mang ý nghĩa.

### Bài 4 — Kiểm tra mã bằng regex

Cho các giá trị:

```text
ORD-2025-0017
ORD-25-0017
XORD-2025-0017
ORD-2025-0017-extra
REQ-2026-0005
```

Với mẫu `^ORD-[0-9]{4}-[0-9]{4}$`, **chỉ chuỗi đầu tiên** hợp lệ. Hãy chỉ ra lỗi của từng chuỗi còn lại: năm thiếu chữ số, thừa tiền tố, thừa hậu tố và sai loại mã.

### Bài 5 — Regex replacement theo phương ngữ

Muốn chuyển `'a1b2c3'` thành `'abc'`, hãy viết cách làm cho PostgreSQL, MySQL 8.0 và Oracle:

```sql
-- PostgreSQL
SELECT REGEXP_REPLACE('a1b2c3', '[0-9]', '', 'g');

-- MySQL 8.0
SELECT REGEXP_REPLACE('a1b2c3', '[0-9]', '');

-- Oracle
SELECT REGEXP_REPLACE('a1b2c3', '[0-9]', '') FROM dual;
```

Giải thích tại sao PostgreSQL cần cờ `'g'` trong ví dụ này, còn hai cú pháp còn lại mặc định xử lý mọi lần khớp.

### Bài 6 — Tách thành hàng và giữ thứ tự

Dùng `STRING_TO_ARRAY`, `UNNEST` và `WITH ORDINALITY` để tách `'sql|java|backend'` thành ba hàng kèm số thứ tự 1, 2, 3. Sau đó thử `'sql||advanced'` và quan sát phần thứ hai rỗng.

Trên SQL Server 2022+ có tính năng phù hợp, viết cách tương ứng với `STRING_SPLIT('sql|java|backend', '|', 1)` và `ORDER BY ordinal`. Giải thích vì sao không nên tin thứ tự hàng trả về nếu không có `ORDER BY`.

### Bài 7 — Chọn giải pháp thay vì mặc định dùng regex

Với các yêu cầu sau, hãy chọn một hướng tiếp cận:

1. Lấy năm từ chuỗi đã được kiểm tra dạng `ORD-YYYY-NNNN`: dùng **`SPLIT_PART`** hoặc hàm tách tương đương.
2. Kiểm tra cả chuỗi phải có ba chữ cái, dấu `-` và bốn chữ số: dùng **regex có neo đầu/cuối**.
3. Tìm những mã bắt đầu bằng `ORD-`: **`LIKE 'ORD-%'`** thường đủ.
4. Truy vấn và quản lý thẻ của hàng triệu bài viết: cân nhắc **bảng quan hệ cho thẻ**, không phụ thuộc tách chuỗi ở mọi truy vấn.

## Kết luận

Khi xử lý văn bản trong SQL, hãy chọn công cụ theo **bản chất câu hỏi**:

- **Tìm vị trí:** dùng `POSITION`/`STRPOS`, `LOCATE`/`INSTR`, `CHARINDEX` hoặc `instr` theo DBMS; chú ý chỉ số bắt đầu từ 1 và giá trị 0 khi không tìm thấy.
- **Tách chuỗi:** dùng `SPLIT_PART`, `STRING_TO_ARRAY`, `SUBSTRING_INDEX`, `STRING_SPLIT` hoặc `SUBSTR`/`INSTR`; cần quyết định cách xử lý thiếu dấu phân cách, phần rỗng và thứ tự phần tử.
- **Xử lý mẫu phức tạp:** dùng regex để so khớp, trích xuất, thay thế và tách theo quy tắc; lưu ý cú pháp, cờ, engine và phiên bản của từng phương ngữ.

Trong ứng dụng thực tế, điều quan trọng không chỉ là viết một biểu thức chạy được, mà còn là **giữ đúng ý nghĩa dữ liệu khi gặp `NULL`, chuỗi rỗng, ký tự Unicode và đầu vào không hợp lệ**. Dùng hàm đơn giản khi đủ, kiểm tra định dạng trước khi trích xuất, xác định rõ phiên bản DBMS và kiểm chứng các trường hợp biên sẽ giúp truy vấn dễ hiểu, dễ bảo trì và ít sai lệch giữa các môi trường.
