# NULL biểu thị gì và khác gì với số 0 hoặc chuỗi rỗng

Trong SQL, **`NULL` biểu thị việc không có một giá trị được xác định** tại vị trí của một cột hoặc biểu thức. Tùy ngữ cảnh nghiệp vụ, điều này có thể nghĩa là thông tin chưa biết, chưa được cung cấp, chưa áp dụng hoặc chưa phát sinh. `NULL` **không phải** số `0`, chuỗi rỗng `''`, chuỗi `'NULL'`, cũng không phải một giá trị thông thường để so sánh bằng dấu `=`.

Sự khác nhau này tác động trực tiếp đến phép so sánh, điều kiện `WHERE`, phép tổng hợp, `JOIN`, ràng buộc và thiết kế dữ liệu. Nếu coi `NULL = 0` hoặc `NULL = ''`, một hệ thống có thể đưa người chưa được khảo sát vào nhóm “đã xác nhận bằng không”, đếm sai số bản ghi hợp lệ hoặc bỏ sót dữ liệu khi lọc.

Các ví dụ sử dụng **PostgreSQL** để có câu SQL thực hành cụ thể. Phần lớn ngữ nghĩa `NULL` là kiến thức SQL chung; những khác biệt theo hệ quản trị, đặc biệt là chuỗi rỗng trong Oracle, sẽ được chỉ rõ.

## 1. Phân biệt bốn giá trị dễ nhầm

| Cách viết SQL | Bản chất | Ví dụ nghiệp vụ |
| --- | --- | --- |
| `NULL` | Không có giá trị xác định | Chưa biết số người phụ thuộc; chưa có ngày giao hàng |
| `0` | Một giá trị số đã biết | Khách hàng **có 0** người phụ thuộc; số dư đúng bằng 0 |
| `''` | Chuỗi văn bản có độ dài 0 trong PostgreSQL | Một trường ghi chú chứa chuỗi rỗng |
| `'NULL'` | Văn bản gồm bốn ký tự N-U-L-L | Người dùng thực sự gõ chữ “NULL” |
| `'0'` | Văn bản gồm ký tự số 0 | Mã phân loại được lưu dưới dạng văn bản |

Thử trực tiếp:

```sql
SELECT
    NULL IS NULL       AS null_is_missing,       -- true
    0 IS NULL          AS zero_is_missing,       -- false
    '' IS NULL         AS empty_is_missing,      -- false
    LENGTH('')         AS empty_length,          -- 0
    LENGTH('NULL')     AS text_null_length;      -- 4
```

Giá trị `0` có thể dùng trong tính toán số học; giá trị `''` có kiểu văn bản và có thể so sánh với chuỗi khác. `NULL` chỉ tình trạng *không có giá trị đã xác định* theo ngữ cảnh biểu thức/cột. Một marker NULL thường nhận kiểu theo cột hoặc phép ép kiểu, không nên tưởng tượng nó là một chuỗi đặc biệt được lưu.

### 1.1. “Không biết” khác “biết là không có”

Trong một bảng hồ sơ:

- `dependents_count = 0`: đã xác nhận **không có** người phụ thuộc.
- `dependents_count = 2`: đã xác nhận có **hai** người phụ thuộc.
- `dependents_count IS NULL`: hiện **chưa có** số người phụ thuộc được xác định.

Nếu nhập dữ liệu bằng cách biến mọi giá trị bị bỏ trống thành `0`, không thể phân biệt người chưa được hỏi với người đã trả lời “0”. Điều này làm sai các mẫu số thống kê, gợi ý dịch vụ và báo cáo tình trạng hoàn thiện hồ sơ.

Tương tự:

- `note IS NULL` khác `note = ''`.
- `note = ''` khác `note = ' '` (một khoảng trắng).
- `note = 'NULL'` là chuỗi có nội dung thật, không phải SQL NULL.

Chuỗi rỗng **có thể được sản phẩm quy định** là “người dùng chủ động bỏ trống”, hoặc đơn giản là một dữ liệu chưa được chuẩn hóa. SQL chỉ cung cấp các cách biểu diễn; **ý nghĩa nghiệp vụ phải được quy định rõ**.

### 1.2. NULL có thể che nhiều nguyên nhân

Một số điện thoại phụ NULL có thể là chưa hỏi, từ chối cung cấp hoặc không có số phụ. Ngày giao hàng NULL có thể là đơn chưa giao, đơn bị hủy hoặc chưa đồng bộ. Nếu sản phẩm cần phân biệt các lý do, chỉ một cột nullable là chưa đủ. Có thể phải thêm trạng thái, thời điểm hoặc cấu trúc quan hệ để lưu chính xác sự kiện và nguyên nhân.

## 2. Bộ dữ liệu minh họa trong PostgreSQL

Tạo bảng tạm để chạy các truy vấn mà không thay đổi dữ liệu của ứng dụng:

```sql
CREATE TEMP TABLE demo_customer_profiles (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    nickname TEXT NULL,
    dependents_count INTEGER NULL
        CHECK (dependents_count >= 0),
    note TEXT NULL
);

INSERT INTO demo_customer_profiles
    (customer_id, customer_name, nickname, dependents_count, note)
VALUES
    (1, 'An',   NULL,  NULL, NULL),
    (2, 'Binh', '',    0,    ''),
    (3, 'Chi',  'Chi', 2,    'Đã xác nhận'),
    (4, 'Dung', NULL,  0,    'NULL'),
    (5, 'Em',   '',    NULL, '0');
```

| ID | Khách hàng | nickname | dependents_count | note |
| ---: | --- | --- | ---: | --- |
| 1 | An | NULL | NULL | NULL |
| 2 | Binh | Chuỗi rỗng | 0 | Chuỗi rỗng |
| 3 | Chi | Chi | 2 | Đã xác nhận |
| 4 | Dung | NULL | 0 | Chuỗi `'NULL'` |
| 5 | Em | Chuỗi rỗng | NULL | Chuỗi `'0'` |

Trong bảng minh họa, chữ **NULL** không có dấu nháy chỉ SQL NULL; các mục “Chuỗi ...” là những giá trị văn bản có thật.

So sánh các kết quả:

```sql
-- An, Em: chưa có số người phụ thuộc.
SELECT customer_name
FROM demo_customer_profiles
WHERE dependents_count IS NULL
ORDER BY customer_id;

-- Binh, Dung: đã biết số người phụ thuộc bằng 0.
SELECT customer_name
FROM demo_customer_profiles
WHERE dependents_count = 0
ORDER BY customer_id;

-- Binh, Em: nickname là chuỗi rỗng.
SELECT customer_name
FROM demo_customer_profiles
WHERE nickname = ''
ORDER BY customer_id;

-- An, Dung: nickname chưa có giá trị xác định.
SELECT customer_name
FROM demo_customer_profiles
WHERE nickname IS NULL
ORDER BY customer_id;
```

Hai truy vấn về số người phụ thuộc trả hai nhóm không trùng nhau. Hai truy vấn về biệt danh cũng trả hai nhóm khác nhau. Những khác biệt này mất đi nếu ứng dụng coi tất cả trường bị bỏ trống là một giá trị mặc định duy nhất.

## 3. NULL và logic ba giá trị của SQL

Trong các điều kiện SQL, ngoài `TRUE` và `FALSE` còn có **`UNKNOWN`**, biểu thị việc chưa thể kết luận đúng/sai vì dữ liệu thiếu. Trong kết quả biểu thức kiểu boolean, trạng thái UNKNOWN thường được hiển thị là **NULL**.

```sql
SELECT
    0 = 0       AS is_true,        -- TRUE
    0 = 1       AS is_false,       -- FALSE
    NULL = 0    AS is_unknown_1,   -- NULL / UNKNOWN
    NULL = NULL AS is_unknown_2;   -- NULL / UNKNOWN
```

**`NULL = NULL` không trả `TRUE`.** Việc hai vị trí đều chưa biết không chứng minh rằng hai giá trị thực, nếu được biết, sẽ giống nhau.

### 3.1. Bảng chân trị

| p | `NOT p` |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

| p | q | `p AND q` | `p OR q` |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Điểm cần nhớ:

- `FALSE AND UNKNOWN` là FALSE, vì một vế sai đã đủ kết luận.
- `TRUE OR UNKNOWN` là TRUE, vì một vế đúng đã đủ kết luận.
- `NOT UNKNOWN` vẫn UNKNOWN.
- `TRUE AND UNKNOWN` và `FALSE OR UNKNOWN` đều UNKNOWN.

Đối với `WHERE` và `HAVING`, chỉ những điều kiện cho **TRUE** được giữ lại. Điều kiện FALSE hoặc UNKNOWN đều không làm hàng/nhóm xuất hiện trong kết quả, dù chúng khác nhau về ý nghĩa logic.

### 3.2. Vì sao không dùng dấu bằng với NULL?

```sql
-- Không lấy được các hàng có dependents_count NULL:
SELECT customer_name
FROM demo_customer_profiles
WHERE dependents_count = NULL;

-- Cũng không lấy được hàng có dependents_count khác NULL:
SELECT customer_name
FROM demo_customer_profiles
WHERE dependents_count <> NULL;
```

Các phép so sánh ấy cho UNKNOWN ở mọi hàng. Cần kiểm tra sự vắng mặt bằng phép riêng:

```sql
WHERE dependents_count IS NULL

-- Hoặc kiểm tra đã có giá trị:
WHERE dependents_count IS NOT NULL
```

`IS NULL`/`IS NOT NULL` trả boolean TRUE hoặc FALSE theo trạng thái vắng mặt, không trả UNKNOWN.

### 3.3. Khác số 0 không có nghĩa “kể cả NULL”

```sql
SELECT customer_name
FROM demo_customer_profiles
WHERE dependents_count <> 0;
-- Chỉ có Chi.
```

Giá trị 2 của Chi khác 0. Giá trị 0 của Binh và Dung không khớp; NULL của An và Em dẫn tới UNKNOWN, cũng không được WHERE chọn.

Nếu nghiệp vụ muốn “khác 0 **hoặc chưa biết**”, cần viết rõ:

```sql
WHERE dependents_count <> 0
   OR dependents_count IS NULL
```

PostgreSQL hỗ trợ các phép so sánh **null-safe**:

```sql
-- NULL được coi là khác giá trị 0:
WHERE dependents_count IS DISTINCT FROM 0

-- Cả hai là NULL -> TRUE:
SELECT NULL IS NOT DISTINCT FROM NULL;
```

`IS DISTINCT FROM` và `IS NOT DISTINCT FROM` không trả UNKNOWN. Đây cũng là tính năng của chuẩn SQL, nhưng không phải DBMS nào cũng có đúng cú pháp này. Khi chuyển hệ quản trị, cần kiểm tra cách so sánh tương đương.

## 4. Số 0 trong tính toán; NULL khi chưa có toán hạng

Với phép số học thông thường, toán hạng NULL thường khiến kết quả NULL vì chưa đủ thông tin để xác định số:

```sql
SELECT
    0 + 5                 AS five,          -- 5
    NULL::INTEGER + 5     AS unknown_sum,   -- NULL
    0 * 100               AS zero_result,   -- 0
    NULL::INTEGER * 100   AS unknown_result;-- NULL
```

SQL không tự chuyển phép cộng NULL thành cộng số 0. Nếu giá trị bị thiếu là một khoản phí chưa xác định, giữ kết quả NULL có thể là cách trung thực để thông báo tổng hiện chưa đủ dữ liệu.

### 4.1. COUNT(*) khác COUNT(cột)

```sql
SELECT
    COUNT(*) AS all_profiles,
    COUNT(dependents_count) AS known_profiles,
    COUNT(*) - COUNT(dependents_count) AS unknown_profiles,
    COUNT(DISTINCT dependents_count) AS distinct_known_values
FROM demo_customer_profiles;
```

| Biểu thức | Điều được đếm | Kết quả |
| --- | --- | ---: |
| `COUNT(*)` | Tất cả hàng | 5 |
| `COUNT(dependents_count)` | Hàng có giá trị số khác NULL, **kể cả 0** | 3 |
| Hiệu hai COUNT trên | Hàng có dependents_count NULL | 2 |
| `COUNT(DISTINCT dependents_count)` | Hai giá trị khác nhau là 0 và 2 | 2 |

**COUNT(cột) bỏ qua NULL nhưng không bỏ qua 0.** Chọn COUNT(*) khi muốn biết có bao nhiêu hàng, chọn COUNT(cột) khi muốn biết có bao nhiêu hàng đã có dữ liệu ở cột đó.

### 4.2. SUM/AVG bỏ qua NULL, vẫn tính 0

```sql
SELECT
    SUM(dependents_count) AS total_known,
    AVG(dependents_count) AS mean_among_known,
    COUNT(dependents_count) AS how_many_known
FROM demo_customer_profiles;
```

Ba giá trị số xác định là 0, 2, 0. Vì vậy SUM bằng **2**, COUNT bằng **3**, AVG bằng **2/3 ≈ 0,667**. Hai hàng NULL bị bỏ qua trong SUM/AVG.

So sánh truy vấn đổi NULL thành 0:

```sql
SELECT AVG(COALESCE(dependents_count, 0))
FROM demo_customer_profiles;
-- 0.4, do đã giả định hai hồ sơ chưa biết = 0.
```

AVG ở đây tính **2/5**, khác hoàn toàn với trung bình của những giá trị đã khai báo. Thay NULL bằng 0 để “đẹp báo cáo” có thể làm sai nghĩa thống kê và kết luận nghiệp vụ.

### 4.3. SUM/AVG trên toàn NULL không cho số 0

```sql
WITH amounts(amount) AS (
    VALUES (NULL::NUMERIC), (NULL::NUMERIC)
)
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS known_count,
    SUM(amount) AS sum_amount,
    AVG(amount) AS avg_amount
FROM amounts;
```

Kết quả `row_count = 2`, `known_count = 0`, còn SUM/AVG là NULL. Với tập không có hàng, COUNT trả 0, nhưng SUM/AVG cũng thường trả NULL. Có thể dùng `COALESCE(SUM(amount), 0)` **nếu** nghiệp vụ muốn trình bày tổng trên tập rỗng là 0. Phải hiểu đây là quy ước bổ sung.

Các hàm SUM, AVG, MIN, MAX thông dụng bỏ qua giá trị NULL. COUNT(*) là ngoại lệ vì đếm hàng; những hàm tổng hợp đặc thù khác có thể có quy tắc riêng.

## 5. Chuỗi rỗng `''`: có phải SQL NULL?

**Không, trong PostgreSQL.** Chuỗi rỗng là một giá trị văn bản dài 0 ký tự:

```sql
SELECT
    LENGTH('') AS empty_length,             -- 0
    '' = '' AS empty_equals_empty,           -- TRUE
    '' IS NULL AS empty_is_null,            -- FALSE
    NULL::TEXT IS NULL AS null_is_null;     -- TRUE
```

Do đó, cột `TEXT NOT NULL` vẫn nhận `''`, vì NOT NULL chỉ cấm SQL NULL:

```sql
CREATE TEMP TABLE demo_labels (
    label_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

INSERT INTO demo_labels (label_id, label)
VALUES (1, ''); -- Hợp lệ với PostgreSQL.
```

Nếu trường văn bản bắt buộc có ít nhất một ký tự khác khoảng trắng thông thường, phải thêm điều kiện riêng:

```sql
ALTER TABLE demo_labels
ADD CONSTRAINT label_not_blank CHECK (BTRIM(label) <> '');
```

`BTRIM` trong PostgreSQL mặc định bỏ dấu cách hai đầu. Với Unicode whitespace hoặc quy tắc chuẩn hóa phức tạp hơn, cần thiết kế phép kiểm tra tương ứng; không suy ra rằng BTRIM xử lý mọi loại ký tự trắng.

### 5.1. Chuỗi rỗng, dấu cách và giá trị NULL

```sql
SELECT
    LENGTH('') AS len_empty,          -- 0
    LENGTH(' ') AS len_one_space,     -- 1
    LENGTH('  ') AS len_two_spaces,   -- 2
    LENGTH(TRIM('  ')) AS trimmed;     -- 0
```

Một ô hiển thị “trống” trong giao diện có thể là chuỗi rỗng, chuỗi khoảng trắng hoặc giá trị NULL. Chúng không tự tương đương trong PostgreSQL với kiểu TEXT. Kiểu CHAR(n) có quy tắc đệm khoảng trắng và so sánh riêng nên cũng cần phân biệt.

### 5.2. Khác biệt về chuỗi rỗng giữa các DBMS

| Hệ quản trị | Xử lý phổ biến với chuỗi rỗng của kiểu ký tự |
| --- | --- |
| PostgreSQL | `''` khác NULL |
| MySQL | `''` khác NULL |
| SQL Server | `''` khác NULL |
| Oracle Database, với kiểu như VARCHAR2 | `''` hiện được xử lý như NULL |

Ví dụ ứng dụng dựa vào `WHERE nickname = ''` trong PostgreSQL có thể không hoạt động theo cùng cách nếu chuyển sang Oracle. Khi migration, phải kiểm tra đặc tính kiểu dữ liệu, ràng buộc NOT NULL/UNIQUE, dữ liệu nhập và logic báo cáo.

### 5.3. Nối chuỗi với NULL

```sql
SELECT
    'Hello' || ''          AS text_with_empty, -- 'Hello'
    'Hello' || NULL::TEXT  AS text_with_null;  -- NULL
```

Trong PostgreSQL, toán tử `||` với NULL thường cho NULL. Tuy nhiên, hàm `CONCAT('Hello', NULL)` của PostgreSQL bỏ qua đối số NULL và trả `'Hello'`. Không suy đoán mọi hàm nối chuỗi đều có chung quy tắc; cần kiểm tra từng hàm của DBMS sử dụng.

## 6. COALESCE, NULLIF và CASE: làm rõ cách diễn giải

Các biểu thức này tạo giá trị mới trong truy vấn; chúng **không tự thay đổi dữ liệu lưu trữ** nếu chỉ xuất hiện trong SELECT.

### 6.1. COALESCE chọn giá trị đầu tiên không NULL

```sql
SELECT
    customer_name,
    nickname,
    COALESCE(nickname, '(chưa khai báo)') AS display_nickname
FROM demo_customer_profiles
ORDER BY customer_id;
```

An và Dung có nickname NULL nên nhận nhãn `(chưa khai báo)`. Binh và Em có nickname là `''` nên **vẫn nhận chuỗi rỗng**: COALESCE không coi chuỗi rỗng là NULL trong PostgreSQL.

```sql
SELECT
    COALESCE(NULL::INTEGER, 0) AS default_number, -- 0
    COALESCE(0, 99) AS keep_zero,                 -- 0
    COALESCE(NULL::TEXT, 'N/A') AS display_text,  -- 'N/A'
    COALESCE('', 'N/A') AS keep_empty;             -- ''
```

COALESCE yêu cầu các đối số tương thích về kiểu. Chỉ dùng COALESCE để thay NULL thành 0 khi đã xác định điều đó đúng với nhu cầu của phép tính hoặc giao diện, không làm thay đổi ý nghĩa của một dữ kiện chưa biết.

### 6.2. NULLIF chuyển một giá trị đặc biệt thành NULL

`NULLIF(a, b)` trả NULL khi a bằng b; nếu không, trả a:

```sql
SELECT
    NULLIF('', '') AS empty_to_null,  -- NULL
    NULLIF('Chi', '') AS keep_text,   -- 'Chi'
    NULLIF(0, 0) AS zero_to_null,    -- NULL
    NULLIF(2, 0) AS keep_two;        -- 2
```

Không áp dụng `NULLIF(number, 0)` tùy tiện với số đếm, số tiền hay số lượng, vì 0 có thể là giá trị hợp lệ.

Nếu quy định biệt danh chỉ gồm khoảng trắng được xem là chưa khai báo:

```sql
SELECT
    customer_name,
    COALESCE(
        NULLIF(BTRIM(nickname), ''),
        '(chưa khai báo)'
    ) AS normalized_nickname
FROM demo_customer_profiles
ORDER BY customer_id;
```

Với nickname NULL, BTRIM trả NULL; với nickname `''`, NULLIF chuyển thành NULL; COALESCE sau đó dùng nhãn thay thế. Các giá trị gốc trong bảng không bị sửa.

### 6.3. CASE phân biệt đủ ba tình trạng

```sql
SELECT
    customer_name,
    CASE
        WHEN dependents_count IS NULL THEN 'Chưa biết'
        WHEN dependents_count = 0 THEN 'Không có'
        ELSE 'Có người phụ thuộc'
    END AS dependents_status
FROM demo_customer_profiles
ORDER BY customer_id;
```

An và Em được phân loại “Chưa biết”; Binh và Dung là “Không có”; Chi là “Có người phụ thuộc”. Một nhánh WHEN được chọn khi điều kiện cho TRUE, không phải khi điều kiện UNKNOWN.

## 7. Bẫy NOT IN với NULL

Xét câu:

```sql
SELECT id
FROM (VALUES (1), (2), (3)) AS candidate(id)
WHERE id NOT IN (1, NULL);
```

**Không có hàng nào được trả về.** Có thể hiểu `x NOT IN (1, NULL)` như `x <> 1 AND x <> NULL`:

- Với x = 1: vế đầu FALSE, kết quả FALSE.
- Với x = 2 hoặc 3: vế đầu TRUE, vế sau UNKNOWN, kết quả UNKNOWN.

WHERE không giữ FALSE hoặc UNKNOWN, nên không có kết quả. Đây là lỗi thường xảy ra khi `NOT IN (SELECT ...)` lấy dữ liệu từ cột nullable mà người viết không để ý.

Nếu yêu cầu là “không có bản ghi cấm nào khớp theo khóa id”, có thể dùng NOT EXISTS:

```sql
SELECT c.id
FROM (VALUES (1), (2), (3)) AS c(id)
WHERE NOT EXISTS (
    SELECT 1
    FROM (VALUES (1), (NULL)) AS forbidden(id)
    WHERE forbidden.id = c.id
)
ORDER BY c.id;
-- Kết quả: 2, 3.
```

NOT EXISTS chỉ cần kiểm tra có **hàng phụ thỏa điều kiện TRUE**. Giá trị NULL ở forbidden.id không khớp id nào bằng phép `=` thông thường. Nếu muốn hai phía đều NULL được coi là khớp, phải mô tả riêng, ví dụ bằng `IS NOT DISTINCT FROM`. Không tự động coi “bỏ qua NULL” là đúng cho mọi trường hợp.

## 8. NULL có thể xuất hiện do OUTER JOIN

Kết quả SELECT có NULL không nhất thiết vì bản ghi nguồn đã lưu NULL. Với **LEFT JOIN**, những hàng phía trái không có hàng phù hợp ở phía phải vẫn được giữ; các cột phía phải nhận NULL do phép JOIN bổ sung.

Tạo bảng tin nhắn:

```sql
CREATE TEMP TABLE demo_customer_messages (
    message_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_customer_profiles(customer_id),
    body TEXT NOT NULL
);

INSERT INTO demo_customer_messages (message_id, customer_id, body)
VALUES
    (101, 1, 'Chào An'),
    (102, 1, 'Tin thứ hai'),
    (103, 3, 'Chào Chi');
```

Đếm tin nhắn của mọi khách:

```sql
SELECT
    p.customer_id,
    p.customer_name,
    COUNT(m.message_id) AS message_count
FROM demo_customer_profiles AS p
LEFT JOIN demo_customer_messages AS m
    ON m.customer_id = p.customer_id
GROUP BY p.customer_id, p.customer_name
ORDER BY p.customer_id;
```

| Khách | message_count |
| --- | ---: |
| An | 2 |
| Binh | 0 |
| Chi | 1 |
| Dung | 0 |
| Em | 0 |

Với Binh, Dung và Em, LEFT JOIN tạo một **hàng bù** có m.message_id = NULL. `COUNT(m.message_id)` vì vậy trả 0; nhưng `COUNT(*)` trả **1** đối với các nhóm ấy vì có một hàng kết quả được bù.

Để tìm khách **không có tin nhắn**:

```sql
SELECT p.customer_name
FROM demo_customer_profiles AS p
LEFT JOIN demo_customer_messages AS m
    ON m.customer_id = p.customer_id
WHERE m.message_id IS NULL
ORDER BY p.customer_id;
-- Binh, Dung, Em.
```

Khi kiểm tra NULL theo mẫu này, nên dùng khóa chính hoặc cột được bảo đảm NOT NULL của bảng bên phải. Kiểm tra một cột có thể NULL dù hàng đã tồn tại sẽ dễ nhầm “bản ghi thật có cột thiếu” với “không có bản ghi ghép”.

### 8.1. ON và WHERE không luôn hoán đổi được

Muốn giữ mọi khách nhưng chỉ đếm tin nhắn có nội dung chính xác `'Chào An'`:

```sql
SELECT p.customer_name, COUNT(m.message_id) AS matching_count
FROM demo_customer_profiles AS p
LEFT JOIN demo_customer_messages AS m
    ON m.customer_id = p.customer_id
   AND m.body = 'Chào An'
GROUP BY p.customer_id, p.customer_name
ORDER BY p.customer_id;
```

Điều kiện m.body ở **ON** cho phép tất cả khách xuất hiện với số đếm 0 nếu không có tin nhắn khớp. Chuyển `m.body = 'Chào An'` xuống **WHERE** khiến hàng bù NULL bị loại do điều kiện UNKNOWN, làm biến mất các khách không khớp. Đây là khác biệt **ngữ nghĩa**, không chỉ là khác biệt hiệu năng.

## 9. NULL trong GROUP BY, DISTINCT và ORDER BY

### 9.1. GROUP BY gom nhiều NULL vào cùng nhóm

```sql
SELECT nickname, COUNT(*) AS profile_count
FROM demo_customer_profiles
GROUP BY nickname
ORDER BY nickname NULLS LAST;
```

Với năm bản ghi:

| nickname | profile_count |
| --- | ---: |
| `''` | 2 |
| `'Chi'` | 1 |
| NULL | 2 |

Các giá trị NULL được gom làm **một nhóm** cho GROUP BY, dù biểu thức `NULL = NULL` vẫn UNKNOWN. So sánh bằng trong WHERE và quy tắc nhóm của GROUP BY là hai cơ chế ngữ nghĩa khác nhau. `SELECT DISTINCT nickname` cũng trả một bản ghi đại diện cho NULL khi có nhiều NULL.

### 9.2. Vị trí NULL khi ORDER BY

```sql
SELECT customer_name, dependents_count
FROM demo_customer_profiles
ORDER BY dependents_count ASC NULLS LAST, customer_id ASC;
```

PostgreSQL hỗ trợ `NULLS FIRST` / `NULLS LAST` để xác định vị trí hàng NULL. Các DBMS có thể có thứ tự mặc định và cú pháp khác nhau. Với phân trang, thêm khóa phụ duy nhất để tránh việc các hàng cùng giá trị thay đổi thứ tự giữa các lần chạy.

## 10. NULL trong ràng buộc và mặc định của bảng

### 10.1. NULL và NOT NULL là quyết định về kiểu dữ liệu nghiệp vụ

```sql
CREATE TEMP TABLE demo_forms (
    form_id INTEGER PRIMARY KEY,
    answer_count INTEGER NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    comment TEXT NOT NULL DEFAULT ''
);
```

- `answer_count INTEGER NULL`: cho phép chưa có số câu trả lời được xác định.
- `status TEXT NOT NULL DEFAULT 'DRAFT'`: chưa cung cấp trạng thái thì là bản nháp, không phải NULL.
- `comment TEXT NOT NULL DEFAULT ''`: cột comment luôn có một giá trị chuỗi, có thể rỗng.

Trong mô hình comment mặc định `''`, ứng dụng **không còn phân biệt** “chưa bao giờ thu thập ghi chú” và “người dùng đã chọn để trống”, trừ khi lưu thêm trạng thái/sự kiện.

### 10.2. DEFAULT không tự thay mọi NULL

```sql
-- Bỏ qua comment: nhận DEFAULT ''.
INSERT INTO demo_forms (form_id)
VALUES (1);

-- Chỉ định DEFAULT: nhận ''.
INSERT INTO demo_forms (form_id, comment)
VALUES (2, DEFAULT);

-- Gửi NULL tường minh: lỗi do cột NOT NULL.
-- INSERT INTO demo_forms (form_id, comment)
-- VALUES (3, NULL);
```

Với cột cho phép NULL và không khai báo DEFAULT, bỏ qua cột khi INSERT thường tạo SQL NULL. Nhưng **không cung cấp cột**, **chỉ định DEFAULT** và **gửi NULL tường minh** có thể khác nhau khi schema quy định mặc định.

### 10.3. CHECK không cấm NULL nếu chỉ kiểm tra >= 0

Ở bảng demo_customer_profiles, cột:

```sql
dependents_count INTEGER NULL
    CHECK (dependents_count >= 0)
```

CHECK trong PostgreSQL chỉ từ chối khi biểu thức kiểm tra cho FALSE. Với NULL, `dependents_count >= 0` là UNKNOWN và không bị CHECK từ chối. Nếu giá trị phải có mặt và không âm, cần **cả hai điều kiện**:

```sql
dependents_count INTEGER NOT NULL
    CHECK (dependents_count >= 0)
```

Lúc này 0 vẫn hợp lệ, nhưng NULL không hợp lệ.

### 10.4. UNIQUE và nhiều giá trị NULL

PostgreSQL mặc định cho phép **nhiều NULL** trong một cột UNIQUE, do các NULL mặc định được coi là khác nhau cho mục đích kiểm tra tính duy nhất:

```sql
CREATE TEMP TABLE demo_optional_codes (
    id INTEGER PRIMARY KEY,
    external_code TEXT UNIQUE
);

INSERT INTO demo_optional_codes (id, external_code)
VALUES
    (1, NULL),
    (2, NULL),  -- Hợp lệ với UNIQUE mặc định PostgreSQL.
    (3, '');

-- (4, '') sẽ vi phạm UNIQUE vì chuỗi rỗng là giá trị xác định.
```

PostgreSQL từ phiên bản 15 hỗ trợ `UNIQUE NULLS NOT DISTINCT` nếu cần coi NULL như trùng nhau khi kiểm tra UNIQUE. DBMS khác có quy tắc và cú pháp khác; không giả định hành vi về NULL trong UNIQUE là giống nhau ở mọi hệ. Nếu mã là thông tin bắt buộc, **NOT NULL + UNIQUE** diễn đạt yêu cầu rõ ràng hơn.

## 11. NULL ở ranh giới API, ứng dụng và SQL

Dữ liệu đi vào ứng dụng qua JSON, HTML form, CSV hoặc hệ thống ngoài có thể ở những tình trạng khác nhau:

1. Thuộc tính **không xuất hiện** trong yêu cầu.
2. Thuộc tính có giá trị **JSON null**.
3. Thuộc tính có **chuỗi `""`**.
4. Thuộc tính có **số 0**.
5. Thuộc tính có **chuỗi toàn khoảng trắng**.
6. Thuộc tính có **giá trị thật**.

Những trạng thái ở tầng API **chưa mặc nhiên là SQL NULL**. Với cập nhật một phần, không gửi trường có thể nghĩa là “giữ nguyên”; gửi JSON null có thể nghĩa là “xóa giá trị”; gửi chuỗi rỗng có thể nghĩa là “lưu chuỗi rỗng”. Quy tắc mapping phải có trong hợp đồng API.

Trong PostgreSQL, SQL NULL ở cột JSON/JSONB, JSON literal `null` bên trong giá trị JSON và khóa không tồn tại trong đối tượng JSON cũng là các tình huống khác nhau. Khi dùng JSON không được ngầm coi mọi trạng thái thiếu là một.

### 11.1. Câu hỏi cần trả lời trước khi quyết định NULL hay giá trị mặc định

| Câu hỏi | Gợi ý quyết định |
| --- | --- |
| Số 0 có ý nghĩa xác định không? | Giữ 0; dùng NULL khi số liệu chưa biết |
| Chuỗi rỗng có ý nghĩa riêng không? | Nếu không, có thể chuẩn hóa thành NULL có chủ đích |
| Có phải phân biệt “chưa biết”, “không áp dụng”, “từ chối”? | Mô hình thêm trạng thái hoặc sự kiện |
| Cột bắt buộc phải có giá trị không? | `NOT NULL` và `CHECK` nếu cần |
| Bỏ qua trường khi INSERT phải tạo gì? | `DEFAULT` hoặc NULL theo chính sách |
| Báo cáo cần đếm hàng hay giá trị đã nhập? | `COUNT(*)` hoặc `COUNT(column)` tương ứng |
| Giá trị thay thế chỉ phục vụ hiển thị? | Có thể `COALESCE` khi hiển thị, giữ nguyên dữ liệu gốc |

### 11.2. Chuẩn hóa đầu vào theo đúng miền dữ liệu

Ví dụ quy định biệt danh chỉ chứa khoảng trắng là chưa khai báo:

```sql
INSERT INTO demo_customer_profiles
    (customer_id, customer_name, nickname, dependents_count, note)
VALUES
    (6, 'Giang', NULLIF(BTRIM('   '), ''), NULL, NULL);
-- nickname được lưu thành NULL.
```

Không áp dụng `NULLIF(number, 0)` cho một cột số có số 0 hợp lệ. Các cách xử lý kiểu “mọi giá trị falsy đều là thiếu” có nguy cơ làm mất **0**, **FALSE** và **chuỗi rỗng** vốn mang những ý nghĩa khác nhau.

Trong **Java/JDBC**, `ResultSet.getInt()` khi đọc SQL NULL trả về giá trị số nguyên 0, nên cần kiểm tra `ResultSet.wasNull()` hoặc dùng cơ chế đọc kiểu đối tượng phù hợp để không đánh đồng NULL với 0. Khi ghi SQL NULL, dùng bind tham số NULL theo driver và kiểu cột, không truyền văn bản `'NULL'`.

## 12. Những nhầm lẫn hay gặp

| Nhầm lẫn | Hậu quả | Cách hiểu/cách viết phù hợp |
| --- | --- | --- |
| `column = NULL` tìm ra hàng thiếu | Điều kiện UNKNOWN | `column IS NULL` |
| `column <> NULL` tìm ra hàng có giá trị | Điều kiện vẫn UNKNOWN | `column IS NOT NULL` |
| `column <> 0` bao gồm NULL | Hàng NULL bị WHERE loại | Thêm `OR column IS NULL` nếu cần |
| `COALESCE(value, 0)` luôn vô hại | Mất khác biệt “chưa biết” và 0 | Chỉ dùng khi 0 là quy ước chính xác |
| `COUNT(column)` đếm mọi hàng | Bỏ hàng có cột NULL | `COUNT(*)` để đếm hàng |
| `COUNT(*)` sau LEFT JOIN đếm bản ghi con | Tính cả hàng bù NULL | `COUNT(child.primary_key)` |
| `NOT IN` luôn hoạt động khi danh sách có NULL | UNKNOWN có thể loại mọi hàng | Dùng NOT EXISTS/lọc NULL đúng nghiệp vụ |
| `TEXT NOT NULL` cấm chuỗi rỗng | PostgreSQL vẫn cho `''` | Thêm CHECK phù hợp |
| `NULL = NULL` là TRUE | Kết quả UNKNOWN | IS NULL / IS NOT DISTINCT FROM tùy yêu cầu |
| `'NULL'` và SQL NULL giống nhau | Lưu nhầm dữ liệu văn bản | Bind NULL thật, không truyền chuỗi |
| UNIQUE chỉ cho một NULL ở mọi DBMS | PostgreSQL mặc định cho nhiều NULL | Xác định quy tắc theo DBMS |
| Mọi DBMS phân biệt `''` và NULL | Oracle có quy tắc khác | Kiểm tra cách xử lý của DBMS |

## 13. Bài tập ứng dụng

Hãy dự đoán kết quả bằng lý luận trước khi chạy, rồi sử dụng bảng demo_customer_profiles của mục 2 để quan sát.

### Bài 1 — Ba trạng thái của số lượng

Viết truy vấn trả tên khách và một nhãn:

- `dependents_count IS NULL` → “Chưa biết”.
- `dependents_count = 0` → “Không có”.
- Giá trị dương → “Có người phụ thuộc”.

Gợi ý: `CASE WHEN ... IS NULL THEN ... WHEN ... = 0 THEN ... ELSE ... END`. Vì sao không nên dùng COALESCE(dependents_count, 0) trước khi phân loại?

### Bài 2 — Đếm hồ sơ đã xác nhận

Đếm tổng hồ sơ, hồ sơ có số người phụ thuộc đã biết, hồ sơ thiếu số liệu và hồ sơ đã xác nhận có 0 người phụ thuộc:

```sql
SELECT
    COUNT(*) AS total_profiles,
    COUNT(dependents_count) AS known_profiles,
    COUNT(*) - COUNT(dependents_count) AS unknown_profiles,
    COUNT(*) FILTER (WHERE dependents_count = 0) AS zero_profiles
FROM demo_customer_profiles;
```

Với năm hàng ban đầu, kết quả là **5, 3, 2, 2**. PostgreSQL hỗ trợ `FILTER (WHERE ...)` trên các hàm tổng hợp để đếm có điều kiện.

### Bài 3 — Hai loại biệt danh bị bỏ trống

Viết hai truy vấn riêng lấy khách có `nickname IS NULL` và `nickname = ''`. Sau đó viết truy vấn lấy cả hai tình trạng theo một chính sách chung:

```sql
WHERE nickname IS NULL OR nickname = ''
```

Nếu chính sách muốn gộp cả các chuỗi chỉ có dấu cách, hãy thử `NULLIF(BTRIM(nickname), '') IS NULL` và giải thích vì sao đây là quyết định nghiệp vụ, không phải quy tắc mặc định của SQL.

### Bài 4 — NOT IN chứa NULL

```sql
SELECT id
FROM (VALUES (10), (20), (30)) AS candidate(id)
WHERE id NOT IN (10, NULL);
```

Vì sao không trả 20, 30? Hãy viết lại bằng NOT EXISTS để loại đúng 10.

### Bài 5 — LEFT JOIN và đếm hàng bù

Kết hợp demo_customer_profiles và demo_customer_messages để liệt kê mọi khách và số tin nhắn. So sánh COUNT(*) và COUNT(m.message_id) cho Binh, Dung, Em; giải thích nguồn gốc NULL trong kết quả JOIN.

### Bài 6 — Thiết kế lược đồ phản ánh đúng ý nghĩa

Hệ thống cần lưu: (1) bộ đếm đăng nhập sai, khởi đầu đã biết là 0; (2) thời điểm xác minh tài khoản, chưa xác minh thì chưa có thời điểm.

```sql
failed_login_count INTEGER NOT NULL DEFAULT 0
    CHECK (failed_login_count >= 0),
verified_at TIMESTAMPTZ NULL
```

Giải thích vì sao bộ đếm dùng 0 còn thời điểm dùng NULL; khi nào cần thêm trạng thái để phân biệt những lý do chưa xác minh?

## 14. Ghi nhớ để không làm mất ý nghĩa dữ liệu

```text
Trạng thái thông tin
├── Không có giá trị được xác định
│   └── SQL NULL
└── Đã có giá trị
    ├── Giá trị số: 0, 1, 2, ...
    ├── Giá trị chuỗi: '', 'Chi', 'NULL', ...
    ├── Giá trị logic: TRUE, FALSE
    └── Ngày giờ, mã định danh hoặc kiểu dữ liệu khác
```

`NULL` biểu thị **không có giá trị được xác định** và đưa trạng thái `UNKNOWN` vào logic điều kiện SQL. `0` và `''` là **giá trị có thật** trong ngữ cảnh kiểu số và kiểu văn bản của PostgreSQL. Điều này giải thích tại sao cần dùng IS NULL, vì sao COUNT(cột) và AVG bỏ qua NULL, vì sao NOT IN có thể gây bất ngờ, và tại sao LEFT JOIN tạo ra những hàng bù NULL.

**Nguyên tắc cốt lõi: đừng tự biến “chưa biết” thành “biết chắc là không có”.** Chọn NULL, số 0, chuỗi rỗng và giá trị mặc định dựa trên ý nghĩa nghiệp vụ, đồng thời lưu ý cách hệ quản trị cụ thể xử lý chuỗi rỗng và các ràng buộc.
