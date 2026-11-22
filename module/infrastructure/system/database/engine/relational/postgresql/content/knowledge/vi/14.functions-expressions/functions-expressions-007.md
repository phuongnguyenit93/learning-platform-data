# So sánh hàng, mảng và toán tử ANY hoặc ALL trong PostgreSQL

Khi lọc dữ liệu bằng SQL, phép so sánh không chỉ giới hạn ở một cột với một giá trị. Một ứng dụng có thể cần so sánh **hai cặp khóa** như `(department, grade)`, kiểm tra kỹ năng có nằm trong **mảng** hay không, hoặc xác nhận điểm của nhân viên **lớn hơn mọi** mức chuẩn trong một danh sách. PostgreSQL hỗ trợ ba nhóm công cụ gần nhau về cú pháp nhưng khác ý nghĩa:

- **So sánh hàng (row constructor comparison):** so các bộ giá trị theo từng cột tương ứng, chẳng hạn `ROW(2, 18000000) < ROW(3, 10000000)`.
- **So sánh và toán tử mảng:** làm việc với `integer[]`, `text[]`, kiểm tra bằng nhau, chứa, bị chứa, giao nhau và duyệt phần tử.
- **`ANY` / `SOME` và `ALL`:** áp một toán tử so sánh giữa một giá trị và **từng phần tử của mảng hoặc từng hàng do subquery trả về**, rồi kết hợp kết quả theo ý nghĩa “có ít nhất một” hoặc “tất cả”.

Điểm mấu chốt là **`NULL`, mảng rỗng và tập con rỗng có những ngữ nghĩa riêng**. Ví dụ `2 = ANY(ARRAY[1, NULL])` không trả `FALSE` mà có thể trả `NULL`; `2 = ANY('{}'::integer[])` trả `FALSE`; còn `2 = ALL('{}'::integer[])` trả `TRUE`. Với `NOT IN`, chỉ một giá trị `NULL` trong tập so sánh có thể làm truy vấn loại những hàng mà người viết tưởng sẽ được chọn.

Bài học giải thích các quy tắc này bằng một bộ dữ liệu PostgreSQL thực hành, nhiều truy vấn có kết quả dự kiến, bài tập về hiệu năng/index và các lưu ý khi sử dụng SQL từ Java/JDBC.

## 1. Mục tiêu và sơ đồ khái niệm

Sau bài học, người học có thể:

1. Viết `ROW(...)` hoặc `(a, b)` để so sánh nhiều cột và hiểu **thứ tự so sánh từ trái sang phải**.
2. Phân biệt `=`, `<>`, `<`, `>`, `IS DISTINCT FROM` và kiểm tra `IS NULL` trên row constructor.
3. Tạo, truy cập, so sánh và duyệt các mảng PostgreSQL có kiểu phần tử xác định.
4. Dùng `@>`, `<@`, `&&` để hỏi về thành viên/tập phần tử, không nhầm chúng với phép bằng mảng.
5. Dùng `= ANY(array)`, `<> ALL(array)`, `> ALL(subquery)`, `< ANY(subquery)` đúng ý nghĩa.
6. Phân biệt `FALSE` với `NULL` khi mảng có phần tử `NULL`, mảng là `NULL` hoặc không có phần tử.
7. Tránh bẫy `NOT IN` và chọn `NOT EXISTS` khi thích hợp, đặc biệt khi nguồn dữ liệu nullable.
8. Biết khi nào index B-tree hoặc GIN hữu ích và khi nào nên chuyển từ mảng sang bảng quan hệ.

~~~text
ROW(a, b)                  ARRAY[1, 2, 3]          x = ANY(array)
    |                             |                      |
    v                             v                      v
so cột tương ứng             tập phần tử có thứ tự   so x với từng phần tử
    |                             |                      |
    v                             v                      v
lexicographic / NULL         =, @>, <@, &&         TRUE/FALSE/UNKNOWN
~~~

**Ba cấu trúc không thay thế nhau:** row giữ các **vị trí cột có ý nghĩa khác nhau** (chẳng hạn phòng ban và cấp bậc); mảng thường chứa **nhiều giá trị cùng kiểu**; `ANY`/`ALL` là **lượng từ trên phép so sánh**, không phải cấu trúc dữ liệu.

## 2. Bộ dữ liệu thực hành

Tạo schema riêng trên **database học tập**. Không chạy lệnh tạo schema hoặc seed trên môi trường có dữ liệu thật. Nếu `expr_lab_180` đã tồn tại, hãy dùng một tên lab khác thay vì xóa dữ liệu cũ.

### 2.1. Bảng nhân viên với cột mảng

~~~sql
CREATE SCHEMA expr_lab_180;

CREATE TABLE expr_lab_180.employees (
    employee_id BIGINT PRIMARY KEY,
    employee_name TEXT NOT NULL,
    department TEXT NOT NULL,
    grade INTEGER NULL,
    salary NUMERIC(12, 2) NULL,
    skills TEXT[] NULL,

    CONSTRAINT employee_grade_check
        CHECK (grade BETWEEN 1 AND 5),
    CONSTRAINT employee_salary_check
        CHECK (salary >= 0)
);
~~~

`skills TEXT[]` chứa một mảng kỹ năng. Cột cho phép `NULL` để phân biệt:

- **Mảng NULL:** chưa biết danh sách kỹ năng.
- **Mảng rỗng `{}`:** danh sách đã được xác nhận là chưa có phần tử.
- **Mảng có phần tử NULL:** biết một số phần tử nhưng có một vị trí chưa xác định.

Những trạng thái đó không giống nhau, dù cách hiển thị trên giao diện có thể khá tương tự.

### 2.2. Nạp mười nhân viên

~~~sql
INSERT INTO expr_lab_180.employees
    (employee_id, employee_name, department, grade, salary, skills)
VALUES
    (1,  'An',   'ENG',   2, 18000000, ARRAY['sql', 'postgres', 'java']),
    (2,  'Bình', 'ENG',   3, 25000000, ARRAY['sql', 'python']),
    (3,  'Chi',  'OPS',   1, 12000000, ARRAY['linux', 'postgres']),
    (4,  'Dũng', 'OPS',   NULL, NULL,   ARRAY[]::text[]),
    (5,  'Hà',   'SALES', 2, 16000000, ARRAY['crm', 'excel']),
    (6,  'Khôi', 'ENG',   2, 20000000, ARRAY['sql', NULL::text, 'kafka']),
    (7,  'Lan',  'ENG',   1, 14000000, NULL::text[]),
    (8,  'Minh', 'SALES', NULL, 13000000, ARRAY['crm']),
    (9,  'Nga',  'QA',    1, 11000000, ARRAY[]::text[]),
    (10, 'Phúc', 'RND',   1, 21000000, NULL::text[]);
~~~

Ở nhân viên 6, mảng có ba vị trí nhưng **vị trí thứ hai là `NULL`**. Nhân viên 4 và 9 có **mảng rỗng**, còn nhân viên 7 và 10 có **mảng `NULL`**.

### 2.3. Bảng quy tắc chứa mảng cấp bậc được phép

~~~sql
CREATE TABLE expr_lab_180.department_rules (
    department TEXT PRIMARY KEY,
    allowed_grades INTEGER[] NULL
);

INSERT INTO expr_lab_180.department_rules
    (department, allowed_grades)
VALUES
    ('ENG', ARRAY[1, 2, 3]),
    ('OPS', ARRAY[1, 2]),
    ('SALES', ARRAY[2, 3]),
    ('QA', ARRAY[]::integer[]),
    ('RND', NULL::integer[]);
~~~

Quy ước bài tập:

- ENG cho các cấp `1, 2, 3`.
- OPS cho các cấp `1, 2`.
- SALES cho các cấp `2, 3`.
- QA có danh sách **rỗng** (không cấp nào được cho phép theo danh sách này).
- RND có danh sách **chưa biết** (`NULL`), khác với QA.

### 2.4. Bảng quy tắc theo cặp cột

~~~sql
CREATE TABLE expr_lab_180.eligible_pairs (
    department TEXT NOT NULL,
    grade INTEGER NOT NULL,
    CONSTRAINT eligible_pairs_pk
        PRIMARY KEY (department, grade)
);

INSERT INTO expr_lab_180.eligible_pairs
    (department, grade)
VALUES
    ('ENG', 2),
    ('ENG', 3),
    ('OPS', 1),
    ('SALES', 2);
~~~

Đây là ví dụ về **quan hệ giữa hai giá trị**: cùng grade 2 nhưng không phải department nào cũng được phép; cặp `('ENG', 1)` không nằm trong `eligible_pairs` dù grade 1 tự nó là một số hợp lệ.

### 2.5. Xem dữ liệu

~~~sql
SELECT
    employee_id,
    employee_name,
    department,
    grade,
    salary,
    skills
FROM expr_lab_180.employees
ORDER BY employee_id;
~~~

| ID | Bộ phận | Grade | Lương | Tình trạng mảng skills |
| ---: | --- | ---: | ---: | --- |
| 1 | ENG | 2 | 18.000.000 | `{sql,postgres,java}` |
| 2 | ENG | 3 | 25.000.000 | `{sql,python}` |
| 3 | OPS | 1 | 12.000.000 | `{linux,postgres}` |
| 4 | OPS | `NULL` | `NULL` | `{}` |
| 5 | SALES | 2 | 16.000.000 | `{crm,excel}` |
| 6 | ENG | 2 | 20.000.000 | Có `sql`, `NULL`, `kafka` |
| 7 | ENG | 1 | 14.000.000 | `NULL` (mảng chưa biết) |
| 8 | SALES | `NULL` | 13.000.000 | `{crm}` |
| 9 | QA | 1 | 11.000.000 | `{}` |
| 10 | RND | 1 | 21.000.000 | `NULL` |

Trong bảng, `NULL` ở grade/salary/skills phải được hiểu theo từng cột. SQL không tự coi grade `NULL` như 0 hoặc mảng `NULL` như mảng rỗng.

## 3. Row constructor: một hàng gồm nhiều trường

PostgreSQL cho phép tạo một giá trị dạng row:

~~~sql
SELECT
    ROW('ENG', 2) AS explicit_row,
    ('ENG', 2) AS implicit_row,
    pg_typeof(ROW('ENG', 2)) AS row_type;
~~~

Trong ngữ cảnh cú pháp thích hợp, `ROW('ENG', 2)` và `('ENG', 2)` đều tạo row gồm hai trường. Mỗi **vị trí** có ý nghĩa riêng: trường thứ nhất là mã bộ phận, trường thứ hai là grade.

~~~text
ROW('ENG', 2)
     |     |
     |     +-- vị trí 2: grade
     +-------- vị trí 1: department
~~~

Một row constructor có thể chứa kiểu hỗn hợp:

~~~sql
SELECT ROW(
    1::bigint,
    'An'::text,
    DATE '2026-11-14',
    TRUE
) AS person_snapshot;
~~~

Đây không phải mảng: mảng PostgreSQL lưu các phần tử **cùng kiểu phần tử**; row có thể chứa `bigint`, `text`, `date`, `boolean` trong cùng một giá trị.

### 3.1. Row có thể dùng trong phép so sánh

~~~sql
SELECT
    ROW(1, 2) = ROW(1, 2) AS equal_rows,
    ROW(1, 2) <> ROW(1, 3) AS different_rows,
    ROW(1, 2) < ROW(1, 3) AS less_than,
    ROW(2, 1) > ROW(1, 999) AS greater_than;
~~~

Kết quả lần lượt đều là **`TRUE`**.

PostgreSQL hỗ trợ những toán tử so sánh B-tree thích hợp với từng cặp trường trong row, phổ biến là `=`, `<>`, `<`, `<=`, `>` và `>=`. Kiểu của các trường tương ứng phải có toán tử so sánh phù hợp; không thể so hai row với số trường khác nhau rồi kỳ vọng PostgreSQL tự điền giá trị còn thiếu.

### 3.2. So sánh cặp cột trong bảng

~~~sql
SELECT
    employee_id,
    department,
    grade,
    (department, grade) = ('ENG', 2)
        AS is_engineer_grade_two
FROM expr_lab_180.employees
ORDER BY employee_id;
~~~

Các nhân viên **1** và **6** có cặp `('ENG', 2)` nên biểu thức là `TRUE`. Nhân viên có grade `NULL` có thể có kết quả `NULL` thay vì `FALSE` tùy cột còn lại và điều kiện so sánh, như phần sau.

### 3.3. Khi nào dùng cặp thay cho hai điều kiện AND?

Hai biểu thức:

~~~sql
WHERE department = 'ENG'
  AND grade = 2
~~~

và:

~~~sql
WHERE (department, grade) = ('ENG', 2)
~~~

thể hiện cùng điều kiện bằng nhau từng cột trong trường hợp thông thường. Dạng row hữu ích khi:

- So sánh **khóa tổng hợp**;
- Lọc theo **nhiều cột cùng thứ tự**;
- Dùng `IN` với danh sách các bộ giá trị;
- Phân trang bằng so sánh thứ tự nhiều cột.

Không phải cứ có hai điều kiện `AND` là bắt buộc chuyển thành row; chọn dạng dễ đọc và thuận tiện cho planner/index.

## 4. So sánh bằng nhau và khác nhau giữa hai row

Với row constructors, các phép `=` và `<>` có quy tắc NULL đặc biệt:

- `row_a = row_b` là `TRUE` khi **tất cả** cặp trường tương ứng đều **khác NULL và bằng nhau**.
- `row_a = row_b` là `FALSE` khi có **ít nhất một** cặp trường khác NULL và **không bằng nhau**.
- Nếu chưa có cặp nào chứng minh khác nhau nhưng có cặp chứa `NULL`, kết quả là **`NULL`/UNKNOWN**.
- `row_a <> row_b` là `TRUE` khi có cặp trường khác NULL và khác nhau; là `FALSE` khi tất cả cặp đều khác NULL và bằng nhau; còn lại là `NULL`.

### 4.1. Ví dụ với cặp trường NULL

~~~sql
SELECT
    ROW(1, NULL::integer) = ROW(1, NULL::integer)
        AS equal_with_unknown,
    ROW(1, NULL::integer) = ROW(2, NULL::integer)
        AS proven_different,
    ROW(1, NULL::integer) <> ROW(2, NULL::integer)
        AS not_equal_proven,
    ROW(1, NULL::integer) <> ROW(1, NULL::integer)
        AS not_equal_unknown;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `ROW(1,NULL) = ROW(1,NULL)` | `NULL` |
| `ROW(1,NULL) = ROW(2,NULL)` | `FALSE` |
| `ROW(1,NULL) <> ROW(2,NULL)` | `TRUE` |
| `ROW(1,NULL) <> ROW(1,NULL)` | `NULL` |

Ở hàng thứ hai, trường đầu `1 <> 2` đủ chứng minh hai row **khác nhau**, dù trường thứ hai là `NULL`.

### 4.2. Dùng IS [NOT] DISTINCT FROM để so sánh có xét NULL

Khi cần kết quả boolean chắc chắn, dùng `IS DISTINCT FROM` hoặc `IS NOT DISTINCT FROM`:

~~~sql
SELECT
    ROW(1, NULL::integer)
        IS NOT DISTINCT FROM
    ROW(1, NULL::integer) AS same_nullable_values,

    ROW(1, NULL::integer)
        IS DISTINCT FROM
    ROW(1, 2) AS different_nullable_values,

    ROW(1, NULL::integer)
        IS DISTINCT FROM
    ROW(2, NULL::integer) AS different_first_field;
~~~

Kết quả đều **`TRUE`**.

`IS NOT DISTINCT FROM` xem hai giá trị `NULL` tương ứng như **không khác nhau** cho mục tiêu so sánh. Đây là lựa chọn tốt trong câu hỏi “hai bộ trường nullable có thay đổi không?”, chẳng hạn đối chiếu dữ liệu trước/sau:

~~~sql
-- Ví dụ ý tưởng đối chiếu hai bản ghi:
-- WHERE (old_value, old_note)
--       IS DISTINCT FROM
--       (new_value, new_note)
~~~

Phải phân biệt rõ `IS NOT DISTINCT FROM` với `=`: hai phép có quy tắc NULL khác nhau.

## 5. Row IS NULL và IS NOT NULL không đơn thuần là hai vế đối nhau

Một trường hợp rất dễ gây bất ngờ trong PostgreSQL là **row có một số trường NULL**.

Theo ngữ nghĩa kiểm tra row constructor:

- `row IS NULL` là `TRUE` khi bản thân row là giá trị NULL **hoặc tất cả các trường của row đều NULL**.
- `row IS NOT NULL` là `TRUE` khi bản thân row không NULL **và tất cả các trường đều khác NULL**.
- Với một row có **một số trường NULL, một số trường khác NULL**, **cả hai biểu thức có thể là `FALSE`**.

~~~sql
SELECT
    ROW(NULL::integer, NULL::text) IS NULL
        AS all_fields_null,
    ROW(1, NULL::text) IS NULL
        AS partially_null_row_is_null,
    ROW(1, NULL::text) IS NOT NULL
        AS partially_null_row_is_not_null,
    ROW(1, 'ok'::text) IS NOT NULL
        AS all_fields_present;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| Hai trường NULL, `IS NULL` | `TRUE` |
| Một trường có giá trị, một trường NULL, `IS NULL` | `FALSE` |
| Một trường có giá trị, một trường NULL, `IS NOT NULL` | `FALSE` |
| Hai trường có giá trị, `IS NOT NULL` | `TRUE` |

**Không kết luận mọi row đều thỏa một trong hai điều kiện `IS NULL` và `IS NOT NULL`.** Với dữ liệu từng cột, nếu muốn xác định đúng “một trường cụ thể bị thiếu”, hãy viết `grade IS NULL`; nếu muốn “bất kỳ trường nào bị thiếu”, viết các điều kiện rõ ràng hoặc `NOT (ROW(...) IS NOT NULL)` theo đúng mục tiêu.

### 5.1. Ghi chú về row constructor và composite-type value

PostgreSQL có cả **row constructors** và **giá trị composite type** (kiểu hàng được đặt tên, ví dụ qua `CREATE TYPE`). Trong một số ngữ cảnh so sánh composite để phục vụ sorting/indexing, PostgreSQL có quy tắc xử lý các trường NULL khác so với so sánh row constructors ở biểu thức SQL.

Vì vậy, **không suy ra mọi biểu thức so sánh record/composite đều có hành vi NULL giống hệt nhau** chỉ vì chúng cùng trông như “một hàng”. Bài học chủ yếu dùng cú pháp row constructor `ROW(...)`; khi lưu array của composite type hoặc tạo index trên cột composite, cần đối chiếu ngữ nghĩa kiểu cụ thể theo tài liệu PostgreSQL.

## 6. So sánh thứ tự row theo quy tắc từ điển

Các phép `<`, `<=`, `>`, `>=` trên row constructor thực hiện **so sánh từ trái sang phải**, tương tự từ điển (*lexicographic order*):

1. So cặp trường đầu.
2. Nếu hai trường đầu **khác nhau** và xác định được thứ tự, dừng và quyết định ngay.
3. Nếu bằng nhau, chuyển sang cặp trường tiếp.
4. Nếu tới cặp cần quyết định mà có `NULL` không so sánh được, kết quả có thể là `NULL`.

### 6.1. Trường đầu quan trọng hơn trường sau

~~~sql
SELECT
    ROW(1, 999) < ROW(2, 0) AS first_field_decides,
    ROW(2, 10) < ROW(2, 20) AS second_field_decides,
    ROW(3, 0) > ROW(2, 999999) AS larger_first_field;
~~~

Cả ba đều **`TRUE`**. Trong ví dụ đầu, `999` lớn hơn `0` nhưng không ảnh hưởng kết quả, vì cặp trường thứ nhất `1 < 2` đã quyết định.

### 6.2. NULL chỉ ảnh hưởng khi cần tới trường đó

~~~sql
SELECT
    ROW(1, NULL::integer) < ROW(2, 0)
        AS decided_before_null,
    ROW(1, NULL::integer) < ROW(1, 9)
        AS needs_unknown_field;
~~~

Kết quả:

- `decided_before_null = TRUE` vì cặp đầu `1 < 2` đủ quyết định.
- `needs_unknown_field = NULL` vì cặp đầu bằng nhau và cặp thứ hai chứa `NULL`.

**Đừng coi row comparison là một phép kiểm tra tất cả cột rồi AND các kết quả `<`.** Đó là so sánh theo thứ tự ưu tiên của các cột, không phải mỗi cột của trái đều phải nhỏ hơn cột phải.

### 6.3. Ứng dụng: keyset pagination

Giả sử có bảng sự kiện:

~~~sql
-- Ví dụ schema giả định:
-- events(event_id BIGINT PRIMARY KEY,
--        occurred_at TIMESTAMPTZ NOT NULL, ...)
~~~

Để lấy trang tiếp theo sau một mốc đã xem với thứ tự tăng dần:

~~~sql
SELECT
    event_id,
    occurred_at
FROM events
WHERE (occurred_at, event_id) >
      (TIMESTAMPTZ '2026-11-14 09:30:00+07', 1000::bigint)
ORDER BY occurred_at ASC, event_id ASC
LIMIT 50;
~~~

Điều kiện tương đương về mặt ý nghĩa với:

~~~sql
WHERE occurred_at > :last_time
   OR (occurred_at = :last_time AND event_id > :last_id)
~~~

trong tình huống hai cột sắp xếp đều **NOT NULL** và thứ tự đều tăng. `event_id` là tie-breaker duy nhất để các sự kiện cùng timestamp vẫn có thứ tự ổn định.

**Các điều kiện cần nhớ:**

- `ORDER BY` và phép so sánh tuple phải dùng **cùng thứ tự cột**.
- Với thứ tự giảm dần, thường dùng `<` thay vì `>`; trộn ASC/DESC đòi biểu thức điều kiện tương ứng, không thay duy nhất dấu so sánh một cách máy móc.
- Nếu có khóa sắp xếp nullable, phải xử lý `NULLS FIRST/LAST` và logic NULL tường minh.
- Index B-tree phù hợp như `(occurred_at, event_id)` có thể giúp keyset pagination.
- Dữ liệu thay đổi giữa các lần lấy trang vẫn có thể ảnh hưởng tính ổn định theo snapshot/transaction.

## 7. Row IN: kiểm tra một bộ giá trị thuộc danh sách bộ giá trị

Thay vì kiểm tra riêng từng cột:

~~~sql
WHERE (department = 'ENG' AND grade = 2)
   OR (department = 'OPS' AND grade = 1)
~~~

có thể dùng:

~~~sql
SELECT
    employee_id,
    department,
    grade
FROM expr_lab_180.employees
WHERE (department, grade) IN (
    ('ENG', 2),
    ('OPS', 1)
)
ORDER BY employee_id;
~~~

Kết quả **1, 3, 6**: nhân viên 1 và 6 là ENG grade 2; nhân viên 3 là OPS grade 1.

### 7.1. Row IN với subquery hai cột

~~~sql
SELECT
    employee_id,
    department,
    grade
FROM expr_lab_180.employees AS e
WHERE (e.department, e.grade) IN (
    SELECT r.department, r.grade
    FROM expr_lab_180.eligible_pairs AS r
)
ORDER BY employee_id;
~~~

Kết quả **1, 2, 3, 5, 6**. Subquery phải trả **đúng số cột tương ứng** với row ở vế trái và kiểu có thể so sánh.

### 7.2. Không nhầm cặp với hai danh sách độc lập

Hai điều kiện:

~~~sql
WHERE department IN ('ENG', 'OPS')
  AND grade IN (1, 2)
~~~

chọn **mọi tổ hợp** từ hai tập: ENG-1, ENG-2, OPS-1, OPS-2. Nhưng:

~~~sql
WHERE (department, grade) IN (
    ('ENG', 2),
    ('OPS', 1)
)
~~~

chỉ cho phép **hai cặp cụ thể**. Đây là lý do so sánh row hữu ích với khóa tổng hợp, chính sách theo tổ hợp và dữ liệu đa tenant.

### 7.3. NULL trong multi-column IN

Nếu `grade IS NULL`, không nên cho rằng `(department, grade) IN (...)` luôn trả `FALSE`. Một số phép so sánh cặp có thể UNKNOWN và `IN` có thể trả `NULL` khi không chứng minh được trùng hay khác hoàn toàn.

Với bài toán kiểm tra tồn tại quy tắc:

~~~sql
SELECT
    e.employee_id,
    EXISTS (
        SELECT 1
        FROM expr_lab_180.eligible_pairs AS r
        WHERE r.department = e.department
          AND r.grade = e.grade
    ) AS has_matching_rule
FROM expr_lab_180.employees AS e
ORDER BY e.employee_id;
~~~

`EXISTS` trả **TRUE/FALSE** dựa trên việc có hàng match thực sự. Nếu grade của nhân viên NULL, phép `=` với grade của bảng rule không TRUE, không có hàng match, nên `EXISTS` trả FALSE. Nếu nghiệp vụ muốn **NULL khớp NULL**, cần dùng điều kiện so sánh null-safe như `IS NOT DISTINCT FROM` và quy định rõ dữ liệu.

## 8. Mảng PostgreSQL: kiểu phần tử và cách tạo

Mảng PostgreSQL là một giá trị chứa **nhiều phần tử có cùng kiểu**. Cú pháp thường gặp:

~~~sql
SELECT
    ARRAY[1, 2, 3] AS integer_array,
    ARRAY['sql', 'postgres']::text[] AS text_array,
    ARRAY[]::integer[] AS empty_integer_array,
    NULL::integer[] AS unknown_integer_array,
    ARRAY[1, NULL::integer, 3] AS array_with_null_element;
~~~

Những biểu thức đầu có kiểu `integer[]` hoặc `text[]` tương ứng.

### 8.1. Mảng rỗng cần kiểu tường minh

~~~sql
SELECT
    ARRAY[]::integer[] AS empty_grades,
    ARRAY[]::text[] AS empty_skills;
~~~

PostgreSQL không thể tự suy ra kiểu phần tử từ một mảng **không có phần tử** nếu không có ngữ cảnh kiểu. Vì thế nên viết `ARRAY[]::integer[]` thay vì chỉ `ARRAY[]` trong SQL độc lập.

### 8.2. Mảng một chiều và nhiều chiều

~~~sql
SELECT
    ARRAY[10, 20, 30] AS vector,
    ARRAY[
        [1, 2],
        [3, 4]
    ] AS matrix;
~~~

Mảng đầu có một chiều; mảng sau có hai chiều. PostgreSQL hỗ trợ mảng nhiều chiều với kích thước phù hợp.

~~~sql
SELECT
    array_ndims(ARRAY[[1, 2], [3, 4]]) AS number_of_dimensions,
    cardinality(ARRAY[[1, 2], [3, 4]]) AS total_elements,
    array_length(ARRAY[[1, 2], [3, 4]], 1) AS first_dimension_size,
    array_length(ARRAY[[1, 2], [3, 4]], 2) AS second_dimension_size;
~~~

Kết quả: **2 chiều, 4 phần tử, chiều thứ nhất dài 2, chiều thứ hai dài 2**.

### 8.3. Mảng với dấu ngoặc nhọn và kiểu tường minh

~~~sql
SELECT
    '{1,2,3}'::integer[] AS postgres_array_literal,
    '{"sql","postgres"}'::text[] AS text_literal;
~~~

Kiểu `'{}'::integer[]` là một mảng rỗng. Khi dữ liệu chứa dấu phẩy, dấu nháy, backslash hoặc ký tự đặc biệt, cú pháp chuỗi literal của PostgreSQL có quy tắc escape riêng. Trong application, nên truyền mảng qua **typed parameter** thay vì tự nối chuỗi như `'{...}'`.

## 9. Truy cập phần tử, lấy kích thước và duyệt mảng

Trong mảng được tạo theo cú pháp thông thường, index đầu tiên là **1**, không phải 0 như nhiều mảng Java:

~~~sql
SELECT
    (ARRAY['sql', 'postgres', 'java'])[1] AS first_skill,
    (ARRAY['sql', 'postgres', 'java'])[2] AS second_skill,
    (ARRAY['sql', 'postgres', 'java'])[3] AS third_skill;
~~~

Kết quả là `sql`, `postgres`, `java`.

### 9.1. Truy cập phần tử ngoài phạm vi

~~~sql
SELECT
    (ARRAY[10, 20, 30])[5] AS out_of_bounds,
    (ARRAY[10, 20, 30])[0] AS below_default_lower_bound;
~~~

Với mảng thông thường có lower bound 1, cả hai truy cập trên trả `NULL`. Nhưng **`NULL` tại vị trí truy cập không chứng minh phần tử đó có mặt và bằng NULL**; cũng có thể vì index ngoài phạm vi.

PostgreSQL hỗ trợ mảng với lower bound khác 1 trong một số ngữ cảnh. Khi cần xử lý dữ liệu có bounds đặc biệt, dùng `array_lower`/`array_upper` thay vì luôn giả định index bắt đầu bằng 1.

### 9.2. cardinality so với array_length

~~~sql
SELECT
    cardinality(ARRAY[10, 20, 30]) AS elements,
    cardinality(ARRAY[]::integer[]) AS empty_elements,
    array_length(ARRAY[]::integer[], 1) AS empty_first_dim_length;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | ---: |
| `cardinality(ARRAY[10,20,30])` | 3 |
| `cardinality(ARRAY[]::integer[])` | 0 |
| `array_length(ARRAY[]::integer[],1)` | `NULL` |

`cardinality` thuận tiện khi cần hỏi “có tổng cộng bao nhiêu phần tử?”, đặc biệt với mảng rỗng. Với mảng `NULL`, `cardinality(NULL::integer[])` cũng là `NULL`, **không phải 0**.

### 9.3. unnest: biến mảng thành nhiều hàng

~~~sql
SELECT
    skill
FROM unnest(ARRAY['sql', 'postgres', 'java']) AS u(skill);
~~~

Kết quả có ba hàng. Muốn biết **vị trí gốc**:

~~~sql
SELECT
    skill,
    position
FROM unnest(ARRAY['sql', NULL::text, 'kafka'])
    WITH ORDINALITY AS u(skill, position)
ORDER BY position;
~~~

| position | skill |
| ---: | --- |
| 1 | `sql` |
| 2 | `NULL` |
| 3 | `kafka` |

`WITH ORDINALITY` thêm số thứ tự một-based cho những hàng được tạo ra từ set-returning function. Một phần tử `NULL` **vẫn được unnest thành hàng**; không tự biến mất.

### 9.4. Duyệt skills của từng nhân viên

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    u.skill,
    u.position
FROM expr_lab_180.employees AS e
CROSS JOIN LATERAL unnest(e.skills)
    WITH ORDINALITY AS u(skill, position)
ORDER BY e.employee_id, u.position;
~~~

`CROSS JOIN LATERAL` không tạo hàng từ mảng rỗng hoặc mảng `NULL`. Vì vậy nhân viên 4, 7, 9, 10 **không xuất hiện trong kết quả unnest**.

Nếu muốn giữ cả nhân viên chưa có kỹ năng, dùng `LEFT JOIN LATERAL ... ON TRUE`, rồi xác định ngữ nghĩa hàng không ghép:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    u.skill
FROM expr_lab_180.employees AS e
LEFT JOIN LATERAL unnest(e.skills) AS u(skill)
    ON TRUE
ORDER BY e.employee_id, u.skill NULLS LAST;
~~~

Khi đếm kỹ năng sau `LEFT JOIN`, nên dùng `COUNT(u.skill)` nếu muốn đếm **phần tử có nội dung khác NULL**; `COUNT(*)` sẽ tính cả hàng bổ sung do outer join.

## 10. So sánh hai mảng bằng = và <>

Hai mảng bằng nhau khi chúng tương thích theo quy tắc so sánh mảng của PostgreSQL: **giá trị phần tử tương ứng** phải bằng nhau và cấu trúc chiều/bounds cũng có thể ảnh hưởng khi các phần tử tương ứng trùng nhau.

~~~sql
SELECT
    ARRAY[1, 2, 3] = ARRAY[1, 2, 3] AS same_values,
    ARRAY[1, 2] = ARRAY[2, 1] AS reordered_values,
    ARRAY[1, 1] = ARRAY[1] AS duplicate_matters,
    ARRAY[1, 2] <> ARRAY[1, 3] AS different_values;
~~~

Kết quả: `TRUE`, `FALSE`, `FALSE`, `TRUE`.

**Mảng là cấu trúc có thứ tự; không phải tập hợp toán học.** `ARRAY[1,2]` và `ARRAY[2,1]` có cùng thành viên nhưng **không bằng nhau**.

### 10.1. So sánh thứ tự mảng

~~~sql
SELECT
    ARRAY[1, 2] < ARRAY[1, 3] AS lexicographic_less,
    ARRAY[2, 0] > ARRAY[1, 999] AS first_element_decides;
~~~

Cả hai đều `TRUE`. PostgreSQL so sánh các phần tử theo thứ tự dựa trên phép so sánh B-tree của kiểu phần tử. Nếu các phần tử so được là tương đương, số chiều và thông tin kích thước có thể quyết định thêm thứ tự.

Không nên dùng `<`/`>` trên mảng như một cách kiểm tra “mảng này là tập con của mảng kia”. Với quan hệ chứa tập phần tử, sử dụng `@>`/`<@`.

### 10.2. Mảng NULL khác mảng rỗng

~~~sql
SELECT
    NULL::integer[] = ARRAY[]::integer[] AS unknown_vs_empty,
    ARRAY[]::integer[] = ARRAY[]::integer[] AS two_empty_arrays,
    ARRAY[NULL::integer] IS NULL AS non_null_array_with_null_item;
~~~

Kết quả: `NULL`, `TRUE`, `FALSE`.

Một **mảng có phần tử `NULL`** vẫn là **giá trị mảng tồn tại**; nó không trở thành một mảng `NULL`.

### 10.3. Những điều không nên suy ra từ =

So sánh `ARRAY['sql','java'] = ARRAY['java','sql']` là FALSE vì khác thứ tự, dù cả hai chứa cùng kỹ năng. Nếu nghiệp vụ quan tâm đến **tập kỹ năng bất kể thứ tự**, có thể dùng toán tử containment/overlap, chuẩn hóa sắp xếp hoặc chuyển thành bảng liên kết; không mặc định phép `=` của mảng đã so “hai tập hợp”.

## 11. Toán tử mảng @>, <@ và &&

PostgreSQL cung cấp các toán tử chuyên biệt trên mảng:

| Toán tử | Cách đọc | Ví dụ |
| --- | --- | --- |
| `a @> b` | a **chứa** tất cả phần tử của b | `ARRAY[1,2,3] @> ARRAY[1,3]` |
| `a <@ b` | a được **chứa trong** b | `ARRAY[1,3] <@ ARRAY[1,2,3]` |
| `a && b` | a và b có **ít nhất một phần tử chung** | `ARRAY[1,2] && ARRAY[2,3]` |
| `a || b` | Nối mảng/phần tử theo overload phù hợp | `ARRAY[1,2] || ARRAY[3]` |

### 11.1. Ví dụ về chứa và giao nhau

~~~sql
SELECT
    ARRAY[1, 2, 3] @> ARRAY[1, 3] AS contains_two_items,
    ARRAY[1, 3] <@ ARRAY[1, 2, 3] AS is_contained,
    ARRAY[1, 2] && ARRAY[2, 3] AS has_overlap,
    ARRAY[1, 2] && ARRAY[3, 4] AS disjoint,
    ARRAY[1, 2] || ARRAY[3, 4] AS concatenated;
~~~

Kết quả: `TRUE`, `TRUE`, `TRUE`, `FALSE`, mảng `{1,2,3,4}`.

### 11.2. Dùng containment để tìm nhân viên có kỹ năng

~~~sql
SELECT
    employee_id,
    employee_name,
    skills
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[]
ORDER BY employee_id;
~~~

Kết quả: nhân viên **1, 2, 6**.

Tìm người có **đồng thời sql và postgres**:

~~~sql
SELECT employee_id, employee_name
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql', 'postgres']::text[]
ORDER BY employee_id;
-- Nhân viên 1.
~~~

Tìm người có **ít nhất một** kỹ năng `sql` hoặc `postgres`:

~~~sql
SELECT employee_id, employee_name
FROM expr_lab_180.employees
WHERE skills && ARRAY['sql', 'postgres']::text[]
ORDER BY employee_id;
-- Nhân viên 1, 2, 3, 6.
~~~

### 11.3. Containment không tính số lần xuất hiện

Một điểm bất ngờ:

~~~sql
SELECT
    ARRAY[1] @> ARRAY[1, 1] AS duplicate_not_counted,
    ARRAY[1, 1] @> ARRAY[1] AS inverse_contains,
    ARRAY[1] = ARRAY[1, 1] AS arrays_not_equal;
~~~

Kết quả: `TRUE`, `TRUE`, `FALSE`.

`@>`/`<@` kiểm tra **sự tồn tại phần tử** theo ngữ nghĩa containment, không coi mảng là **multiset** có số lượng xuất hiện phải khớp. Ngược lại, phép `=` vẫn phân biệt mảng một phần tử và hai phần tử.

### 11.4. Không coi tất cả toán tử giống nhau khi có NULL

Khi mảng có phần tử `NULL`, ý nghĩa tìm thấy, không tìm thấy và UNKNOWN có thể khác giữa `= ANY(...)`, phép bằng cả mảng và toán tử containment. Các toán tử có đặc tả riêng; **đừng thay `= ANY` bằng `@>` một cách máy móc** nếu dữ liệu có NULL hoặc cần giữ đúng kết quả ba giá trị.

Nếu nghiệp vụ cấm kỹ năng NULL, nên **làm sạch/kiểm soát mảng khi ghi** hoặc dùng bảng quan hệ có cột `NOT NULL`, thay vì dựa vào những phép so sánh mơ hồ trên đầu vào chưa được chuẩn hóa.

## 12. ANY và ALL: lượng từ trên kết quả so sánh

Cú pháp cốt lõi:

~~~sql
scalar_value comparison_operator ANY (array_expression)
scalar_value comparison_operator ALL (array_expression)
~~~

hoặc:

~~~sql
scalar_value comparison_operator ANY (subquery)
scalar_value comparison_operator ALL (subquery)
~~~

`comparison_operator` thường là `=`, `<>`, `<`, `<=`, `>` hoặc `>=`, và phải là toán tử trả boolean thích hợp.

**`ANY` nghĩa là “có ít nhất một phần tử cho kết quả so sánh TRUE”.**  
**`ALL` nghĩa là “mọi phần tử đều cho kết quả so sánh TRUE”.**

Tên khác của `ANY` trong cú pháp SQL là **`SOME`**:

~~~sql
SELECT
    2 = ANY(ARRAY[1, 2, 3]) AS any_match,
    2 = SOME(ARRAY[1, 2, 3]) AS some_match;
-- TRUE, TRUE
~~~

`ANY` và `ALL` **không phải hàm nhận một mảng rồi tự trả boolean độc lập**. Chúng phải đi cùng **toán tử so sánh bên trái**, ví dụ `x = ANY(...)`, `x < ALL(...)`.

### 12.1. Ví dụ đầu tiên

~~~sql
SELECT
    2 = ANY(ARRAY[1, 2, 3]) AS belongs_to_list,
    9 = ANY(ARRAY[1, 2, 3]) AS not_in_list,
    4 > ALL(ARRAY[1, 2, 3]) AS greater_than_all,
    2 > ALL(ARRAY[1, 2, 3]) AS not_greater_than_all;
~~~

Kết quả: `TRUE`, `FALSE`, `TRUE`, `FALSE`.

Ở `4 > ALL(ARRAY[1,2,3])`, cả ba phép `4>1`, `4>2`, `4>3` đều TRUE nên toàn bộ là TRUE. Ở `2 > ALL(...)`, phép `2>2` FALSE nên kết quả là FALSE.

### 12.2. Bảng quy tắc tổng hợp TRUE/FALSE/UNKNOWN

Giả sử một toán tử so sánh với từng phần tử tạo chuỗi kết quả:

| Kết quả từng phần tử | Kết quả `ANY` | Kết quả `ALL` |
| --- | --- | --- |
| TRUE, TRUE, TRUE | TRUE | TRUE |
| FALSE, FALSE, FALSE | FALSE | FALSE |
| TRUE, FALSE | TRUE | FALSE |
| TRUE, UNKNOWN | TRUE | UNKNOWN |
| FALSE, UNKNOWN | UNKNOWN | FALSE |
| UNKNOWN, UNKNOWN | UNKNOWN | UNKNOWN |
| **Không có phần tử** | **FALSE** | **TRUE** |

Với `ANY`, **một TRUE đủ quyết định**. Nếu không có TRUE nhưng có UNKNOWN, chưa thể kết luận FALSE.

Với `ALL`, **một FALSE đủ quyết định**. Nếu không có FALSE nhưng có UNKNOWN, chưa thể kết luận TRUE.

Đây là logic ba giá trị của SQL; `UNKNOWN` được biểu diễn bởi giá trị boolean `NULL` trong kết quả.

## 13. = ANY(array): kiểm tra một giá trị có trong mảng

Ví dụ:

~~~sql
SELECT
    employee_id,
    employee_name,
    skills
FROM expr_lab_180.employees
WHERE 'sql' = ANY(skills)
ORDER BY employee_id;
~~~

Kết quả **1, 2, 6**.

Đọc biểu thức:

~~~text
'sql' = ANY(skills)
        |
        +-- có ít nhất một phần tử skill bằng 'sql'?
~~~

### 13.1. Phép so sánh dùng giá trị chứ không dùng vị trí

~~~sql
SELECT
    'sql' = ANY(ARRAY['sql', 'java']) AS first_position,
    'sql' = ANY(ARRAY['java', 'sql']) AS second_position;
-- TRUE, TRUE
~~~

`ANY` không yêu cầu phần tử nằm ở vị trí đầu. Trong khi đó, phép `ARRAY['sql','java'] = ARRAY['java','sql']` là FALSE vì **bằng cả mảng** phụ thuộc thứ tự phần tử.

### 13.2. = ANY với cột mảng và phép lọc

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade,
    r.allowed_grades,
    e.grade = ANY(r.allowed_grades) AS grade_is_allowed
FROM expr_lab_180.employees AS e
JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
ORDER BY e.employee_id;
~~~

Kết quả logic:

| ID | Department | Grade | Mảng allowed | `grade_is_allowed` |
| ---: | --- | ---: | --- | --- |
| 1 | ENG | 2 | `{1,2,3}` | TRUE |
| 2 | ENG | 3 | `{1,2,3}` | TRUE |
| 3 | OPS | 1 | `{1,2}` | TRUE |
| 4 | OPS | `NULL` | `{1,2}` | NULL |
| 5 | SALES | 2 | `{2,3}` | TRUE |
| 6 | ENG | 2 | `{1,2,3}` | TRUE |
| 7 | ENG | 1 | `{1,2,3}` | TRUE |
| 8 | SALES | `NULL` | `{2,3}` | NULL |
| 9 | QA | 1 | `{}` | FALSE |
| 10 | RND | 1 | `NULL` | NULL |

Chú ý nhân viên **9** trả FALSE vì danh sách có mặt nhưng rỗng; nhân viên **10** trả NULL vì chưa biết danh sách quy tắc.

### 13.3. WHERE chỉ giữ TRUE

~~~sql
SELECT
    e.employee_id,
    e.employee_name
FROM expr_lab_180.employees AS e
JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
WHERE e.grade = ANY(r.allowed_grades)
ORDER BY e.employee_id;
~~~

Kết quả **1, 2, 3, 5, 6, 7**. Trong `WHERE`:

- TRUE → hàng được giữ.
- FALSE → hàng bị loại.
- NULL/UNKNOWN → hàng cũng bị loại.

Vì vậy, chỉ nhìn danh sách được chọn **không cho biết** các hàng bị loại do “không nằm trong quy tắc” hay “chưa đủ dữ liệu kiểm tra”.

## 14. ALL(array): mọi phần tử đều thỏa điều kiện

Ví dụ:

~~~sql
SELECT
    10 > ALL(ARRAY[2, 4, 6]) AS above_every_number,
    10 > ALL(ARRAY[2, 12, 6]) AS not_above_every_number,
    2 = ALL(ARRAY[2, 2, 2]) AS all_equal_two,
    2 = ALL(ARRAY[2, 2, 3]) AS some_not_equal;
~~~

Kết quả: TRUE, FALSE, TRUE, FALSE.

### 14.1. Lớn hơn tất cả các ngưỡng

Giả sử nhân viên chỉ đạt một tiêu chí nếu grade lớn hơn **mọi** grade trong danh sách cũ:

~~~sql
SELECT
    employee_id,
    grade,
    grade > ALL(ARRAY[1, 2]) AS higher_than_all_benchmarks
FROM expr_lab_180.employees
WHERE department = 'ENG'
ORDER BY employee_id;
~~~

Nhân viên 2 có grade 3 → TRUE; nhân viên 1 và 6 có grade 2 → FALSE; nhân viên 7 grade 1 → FALSE.

Với ngữ nghĩa “ít nhất bằng tất cả”, dùng `>= ALL`. Chỉ cần một phần tử lớn hơn giá trị đang xét là điều kiện bị phá vỡ.

### 14.2. Sai lầm: = ALL không có nghĩa “thuộc danh sách”

~~~sql
SELECT
    2 = ANY(ARRAY[1, 2, 3]) AS member_of_list,
    2 = ALL(ARRAY[1, 2, 3]) AS equal_to_every_item;
-- TRUE, FALSE
~~~

`= ALL` đòi hỏi **mọi phần tử đều bằng 2**, không chỉ tồn tại một phần tử bằng 2. Nếu mục tiêu là membership, dùng `= ANY` hoặc `IN`.

## 15. Mảng rỗng: ANY là FALSE, ALL là TRUE

Một tập rỗng không chứa phần tử nào:

~~~sql
SELECT
    2 = ANY(ARRAY[]::integer[]) AS any_on_empty,
    2 <> ALL(ARRAY[]::integer[]) AS all_not_equal_on_empty,
    2 > ALL(ARRAY[]::integer[]) AS greater_than_all_empty,
    2 = ALL(ARRAY[]::integer[]) AS equals_all_empty;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `2 = ANY('{}'::integer[])` | FALSE |
| `2 <> ALL('{}'::integer[])` | TRUE |
| `2 > ALL('{}'::integer[])` | TRUE |
| `2 = ALL('{}'::integer[])` | TRUE |

Thoạt nhìn, `2 = ALL(empty)` trả TRUE có thể khó hiểu. Theo logic lượng từ, “mọi phần tử của tập rỗng đều bằng 2” **không có phản ví dụ**, nên điều kiện ALL được xem là TRUE. Quy tắc này gọi là **vacuous truth**.

### 15.1. Tập rỗng khác tập chỉ chứa NULL

~~~sql
SELECT
    2 = ANY(ARRAY[]::integer[]) AS empty_any,
    2 = ANY(ARRAY[NULL::integer]) AS null_element_any,
    2 = ALL(ARRAY[]::integer[]) AS empty_all,
    2 = ALL(ARRAY[NULL::integer]) AS null_element_all;
~~~

Kết quả: FALSE, NULL, TRUE, NULL.

**Không suy ra mảng chứa một phần tử NULL tương đương mảng rỗng.** Nó có một phép so sánh không biết kết quả, thay vì không có phép so sánh nào.

### 15.2. Tác động tới quy tắc nghiệp vụ

Nếu danh sách `allowed_grades = '{}'` biểu thị **không cho phép grade nào**, `grade = ANY(allowed_grades)` trả FALSE, đúng với mục tiêu membership.

Ngược lại, nếu một ứng dụng viết:

~~~sql
grade <> ALL(allowed_grades)
~~~

thì với danh sách rỗng, biểu thức trả TRUE — có thể đúng nếu mục tiêu là “grade không trùng bất kỳ mã cấm nào” và danh sách cấm trống, nhưng **không phải** cách kiểm tra “grade có được cho phép hay không”.

## 16. NULL ở bên trái, NULL array và NULL phần tử

Có ba chỗ `NULL` có thể xuất hiện:

1. **Vế trái** của phép so sánh là `NULL`.
2. **Giá trị mảng** là `NULL`.
3. **Một phần tử trong mảng** là `NULL`.

Chúng tạo các kết quả khác nhau tùy việc có phép so sánh TRUE/FALSE quyết định được hay không.

### 16.1. Vế trái NULL

~~~sql
SELECT
    NULL::integer = ANY(ARRAY[1, 2, 3]) AS left_null_any,
    NULL::integer = ALL(ARRAY[1, 2, 3]) AS left_null_all;
-- NULL, NULL
~~~

Với toán tử so sánh `=` thông thường, `NULL = 1`, `NULL = 2`, `NULL = 3` đều UNKNOWN, nên kết quả lượng từ cũng UNKNOWN.

### 16.2. Toàn bộ array là NULL

~~~sql
SELECT
    2 = ANY(NULL::integer[]) AS null_array_any,
    2 = ALL(NULL::integer[]) AS null_array_all;
-- NULL, NULL
~~~

Không có thông tin về danh sách để đánh giá. Đây không phải trường hợp mảng rỗng.

### 16.3. Phần tử NULL nhưng đã có match TRUE

~~~sql
SELECT
    3 = ANY(ARRAY[1, NULL::integer, 3])
        AS match_wins_over_unknown,
    2 = ANY(ARRAY[1, NULL::integer, 3])
        AS no_match_but_unknown_remains;
~~~

Kết quả: TRUE, NULL.

Trong ví dụ đầu, `3 = 3` là TRUE nên ANY chắc chắn TRUE dù có phép so sánh UNKNOWN ở vị trí khác.

Trong ví dụ thứ hai, `2 = 1` FALSE, `2 = NULL` UNKNOWN, `2 = 3` FALSE. Không có TRUE, nhưng vì một phần tử không biết có thể là 2, ta **không thể kết luận FALSE**, nên kết quả là NULL.

### 16.4. ALL với phần tử NULL

~~~sql
SELECT
    4 > ALL(ARRAY[1, NULL::integer, 3])
        AS no_false_but_unknown,
    3 > ALL(ARRAY[1, NULL::integer, 3])
        AS false_wins_over_unknown,
    2 = ALL(ARRAY[2, NULL::integer])
        AS equality_not_fully_known;
~~~

Kết quả: NULL, FALSE, NULL.

Khi `3 > 3` là FALSE, ALL chắc chắn FALSE, không cần biết phần tử NULL. Nhưng khi mọi so sánh xác định được đều TRUE và vẫn còn UNKNOWN, ALL trả NULL.

### 16.5. Bảng phân biệt ba trạng thái của array

| Trạng thái | Ví dụ | `cardinality` | `2 = ANY(...)` | `2 <> ALL(...)` |
| --- | --- | ---: | --- | --- |
| Mảng rỗng | `ARRAY[]::integer[]` | 0 | FALSE | TRUE |
| Mảng NULL | `NULL::integer[]` | NULL | NULL | NULL |
| Mảng chứa NULL | `ARRAY[NULL::integer]` | 1 | NULL | NULL |
| Mảng chứa 2 và NULL | `ARRAY[2, NULL::integer]` | 2 | TRUE | FALSE |
| Mảng chứa 1 và NULL | `ARRAY[1, NULL::integer]` | 2 | NULL | NULL |

Đây là một trong những bảng quan trọng nhất của bài: **UNKNOWN không đồng nghĩa FALSE**, nhất là khi dùng điều kiện phủ định.

## 17. IN, NOT IN và hai biểu thức lượng từ tương ứng

Với những giá trị thông thường:

~~~sql
2 IN (1, 2, 3)
~~~

tương đương về ý nghĩa membership với:

~~~sql
2 = ANY(ARRAY[1, 2, 3])
~~~

Tương tự, biểu thức:

~~~sql
2 NOT IN (1, 3, 5)
~~~

tương ứng với:

~~~sql
2 <> ALL(ARRAY[1, 3, 5])
~~~

**NOT IN là “khác tất cả”, không phải “khác ít nhất một”.**

### 17.1. <> ANY là lỗi logic phổ biến

~~~sql
SELECT
    2 <> ANY(ARRAY[1, 2]) AS different_from_at_least_one,
    2 <> ALL(ARRAY[1, 2]) AS different_from_everyone,
    2 = ANY(ARRAY[1, 2]) AS member_of_array;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `2 <> ANY({1,2})` | TRUE |
| `2 <> ALL({1,2})` | FALSE |
| `2 = ANY({1,2})` | TRUE |

`2 <> ANY({1,2})` là TRUE vì `2 <> 1`. Điều đó **không chứng minh 2 không có trong mảng**. Muốn phủ định membership:

~~~sql
NOT (2 = ANY(ARRAY[1, 2]))
~~~

hoặc:

~~~sql
2 <> ALL(ARRAY[1, 2])
~~~

với việc vẫn phải xét ngữ nghĩa `NULL`.

### 17.2. NOT IN và phần tử NULL

~~~sql
SELECT
    2 NOT IN (1, NULL::integer, 3) AS not_in_with_unknown,
    2 <> ALL(ARRAY[1, NULL::integer, 3])
        AS all_not_equal_with_unknown;
-- NULL, NULL
~~~

Không có phần tử nào được biết là bằng 2, nhưng phần tử `NULL` có thể là 2 hoặc giá trị khác. Vì vậy phép phủ định membership **không được kết luận TRUE**.

Trong `WHERE`, hàng có điều kiện NULL **bị loại**. Đây là lý do một truy vấn `NOT IN` dùng subquery có cột nullable có thể trả ít hàng hơn dự kiến, thậm chí không trả hàng nào.

### 17.3. NOT IN với giá trị vế trái NULL

~~~sql
SELECT
    NULL::integer NOT IN (1, 2, 3) AS unknown_left;
-- NULL
~~~

Nếu cột đầu vào nullable, cần quyết định liệu giá trị NULL có được xem là “không thuộc danh sách” hay **không đủ thông tin**. Không dùng `COALESCE(..., TRUE)` một cách mù quáng, vì nó thay đổi nghiệp vụ của dữ liệu thiếu.

## 18. ANY hoặc ALL với subquery

Ngoài mảng, PostgreSQL cho phép so một giá trị với tập **các hàng do subquery trả về**:

~~~sql
value operator ANY (SELECT single_column FROM ...)
value operator ALL (SELECT single_column FROM ...)
~~~

Đối với phép so sánh vô hướng ở đây, subquery cần trả **một cột** có kiểu tương thích với vế trái.

### 18.1. = ANY(subquery) tương tự IN(subquery)

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade = ANY (
    SELECT r.grade
    FROM expr_lab_180.eligible_pairs AS r
    WHERE r.department = 'ENG'
)
ORDER BY e.employee_id;
~~~

Subquery trả các grade của ENG: `2` và `3`. Kết quả của query ngoài gồm các nhân viên có grade 2 hoặc 3 trên **mọi department**, vì điều kiện ngoài không giới hạn bộ phận: **1, 2, 5, 6**.

Nếu chỉ muốn **nhân viên ENG** đạt grade được phép theo ENG, thêm:

~~~sql
AND e.department = 'ENG'
~~~

hoặc dùng subquery tương quan theo `e.department`:

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade = ANY (
    SELECT r.grade
    FROM expr_lab_180.eligible_pairs AS r
    WHERE r.department = e.department
)
ORDER BY e.employee_id;
-- 1, 2, 3, 5, 6
~~~

Ở đây subquery **tương quan (correlated)** vì nó tham chiếu `e.department` của truy vấn ngoài.

### 18.2. > ALL(subquery): lớn hơn mọi phần tử tập con

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade > ALL (
    SELECT grade
    FROM expr_lab_180.employees
    WHERE department = 'OPS'
      AND grade IS NOT NULL
)
ORDER BY e.employee_id;
~~~

Đối với OPS, grade đã biết là **1** (nhân viên 3); nhân viên 4 có grade NULL đã được loại bằng `IS NOT NULL`. Vì vậy truy vấn chọn những nhân viên có grade **lớn hơn 1**: **1, 2, 5, 6**.

### 18.3. Nếu quên lọc NULL trong subquery

~~~sql
SELECT
    3 > ALL (
        SELECT grade
        FROM expr_lab_180.employees
        WHERE department = 'OPS'
    ) AS above_every_ops_grade;
~~~

Subquery có `1` và `NULL`. `3>1` TRUE, `3>NULL` UNKNOWN, nên kết quả là **NULL**, không phải TRUE.

Khi nghiệp vụ chỉ xét **các grade đã biết**, hãy ghi rõ `AND grade IS NOT NULL` trong subquery. Khi NULL nghĩa là một giá trị cần được đối soát, không nên bỏ qua nó âm thầm.

### 18.4. ANY/ALL trên subquery rỗng

~~~sql
SELECT
    2 = ANY (
        SELECT grade
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS any_empty_subquery,
    2 > ALL (
        SELECT grade
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS all_empty_subquery;
~~~

Kết quả: **FALSE** và **TRUE**, tương tự mảng rỗng.

Không có hàng ở subquery là một tình huống **khác** với subquery trả một hàng mà giá trị của cột là NULL.

## 19. NOT EXISTS: thay thế đáng tin cậy cho một số bài toán NOT IN

`EXISTS(subquery)` trả TRUE khi subquery có **ít nhất một hàng**, ngược lại FALSE. `NOT EXISTS` là phủ định của điều kiện này.

### 19.1. Cạm bẫy NOT IN khi nguồn có NULL

Xét:

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade NOT IN (
    SELECT grade
    FROM expr_lab_180.employees
    WHERE department = 'OPS'
)
ORDER BY e.employee_id;
~~~

Subquery trả `1` và `NULL`. Với grade khác 1, kết quả so sánh là UNKNOWN; với grade bằng 1, kết quả là FALSE; với grade NULL cũng không TRUE. Vì vậy truy vấn có thể trả **0 hàng**, dù rõ ràng nhiều nhân viên có grade 2 hoặc 3.

### 19.2. Dùng NOT EXISTS để kiểm tra không có giá trị bằng

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE e.grade IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM expr_lab_180.employees AS ops
      WHERE ops.department = 'OPS'
        AND ops.grade = e.grade
  )
ORDER BY e.employee_id;
~~~

Kết quả là nhân viên có grade **2 hoặc 3**: **1, 2, 5, 6**.

`NOT EXISTS` quan tâm **có hàng nào match điều kiện tương quan không**, không bị một dòng `ops.grade IS NULL` làm phủ định membership thành UNKNOWN. Ta vẫn ghi `e.grade IS NOT NULL` để **không tự xem grade chưa biết như một cấp đã xác nhận khác các grade ở OPS**.

### 19.3. Nếu muốn NULL được xem là một giá trị để so khớp

~~~sql
SELECT
    e.employee_id,
    e.grade
FROM expr_lab_180.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM expr_lab_180.employees AS ops
    WHERE ops.department = 'OPS'
      AND ops.grade IS NOT DISTINCT FROM e.grade
)
ORDER BY e.employee_id;
~~~

Ở đây `IS NOT DISTINCT FROM` coi hai `NULL` là không khác nhau cho điều kiện join. Vì OPS có grade NULL, những nhân viên grade NULL sẽ bị xem là có match và **không được chọn**. Kết quả vẫn là nhóm grade 2 hoặc 3 trong dataset.

**Chọn `=` hay `IS NOT DISTINCT FROM` phụ thuộc định nghĩa nghiệp vụ của NULL.** `NOT EXISTS` không tự giải quyết mọi câu hỏi về ý nghĩa giá trị thiếu; nó cho phép diễn đạt quy tắc match một cách tường minh hơn.

## 20. > ALL, < ANY và MIN/MAX: tương đương có điều kiện

Với một tập **không rỗng**, toàn giá trị **khác NULL**, và giá trị trái có thể so sánh:

~~~text
x > ALL(values)   tương đương x > MAX(values)
x >= ALL(values)  tương đương x >= MAX(values)
x < ALL(values)   tương đương x < MIN(values)
x <= ALL(values)  tương đương x <= MIN(values)

x > ANY(values)   tương đương x > MIN(values)
x < ANY(values)   tương đương x < MAX(values)
~~~

Đây là cách tư duy hữu ích, **không phải lời hứa hai dạng luôn tương đương trên tập rỗng/nullable**.

### 20.1. Đối chiếu trên dữ liệu chắc chắn khác NULL

~~~sql
SELECT
    4 > ALL(ARRAY[1, 2, 3]) AS all_comparison,
    4 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[1, 2, 3]) AS u(x)
    ) AS comparison_to_max;
-- TRUE, TRUE
~~~

### 20.2. Khác biệt khi tập rỗng

~~~sql
SELECT
    4 > ALL(ARRAY[]::integer[]) AS all_on_empty,
    4 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[]::integer[]) AS u(x)
    ) AS greater_than_max_of_empty;
~~~

Kết quả:

- `all_on_empty = TRUE`.
- `greater_than_max_of_empty = NULL`, vì `MAX` trên tập rỗng trả NULL.

Nếu muốn dùng `MAX` thay `ALL` phải quyết định cách xử lý **tập rỗng** riêng.

### 20.3. Khác biệt khi tập có NULL

~~~sql
SELECT
    4 > ALL(ARRAY[1, NULL::integer, 3])
        AS all_with_unknown,
    4 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[1, NULL::integer, 3]) AS u(x)
    ) AS against_max_ignoring_null;
~~~

Kết quả:

- `all_with_unknown = NULL`.
- `against_max_ignoring_null = TRUE`, vì `MAX` bỏ qua NULL và trả 3.

Điều này chứng minh **so sánh lượng từ trên tập có NULL** và **so với MIN/MAX đã bỏ qua NULL** không luôn có cùng nghĩa.

## 21. ANY(array) so với toán tử containment khi lọc cột mảng

Hai cách phổ biến để tìm nhân viên có `'sql'` trong `skills`:

~~~sql
-- Cách 1: quantified comparison
SELECT employee_id
FROM expr_lab_180.employees
WHERE 'sql' = ANY(skills)
ORDER BY employee_id;
~~~

~~~sql
-- Cách 2: array containment
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[]
ORDER BY employee_id;
~~~

Trong bộ dữ liệu, cả hai chọn **1, 2, 6**. Nhưng:

- `= ANY` hỏi “có phần tử nào bằng giá trị tra cứu?”.
- `@>` hỏi “mảng trái có chứa các phần tử của mảng phải không?”.
- `@>` có thể biểu diễn nhiều phần tử cần có cùng lúc.
- Các trường hợp có `NULL` và cách xử lý kết quả UNKNOWN cần đối chiếu theo quy tắc từng toán tử.
- Khả năng dùng **GIN index** cho containment có thể khác với khả năng dùng index cho `= ANY` trên một **cột mảng**.

Đừng đánh đồng hai cách chỉ vì một tập dữ liệu đơn giản cho cùng danh sách hàng.

### 21.1. Tra cứu trên scalar column với mảng đầu vào lại là bài toán khác

~~~sql
SELECT
    employee_id,
    employee_name
FROM expr_lab_180.employees
WHERE grade = ANY(ARRAY[1, 3]::integer[])
ORDER BY employee_id;
~~~

Ở đây **cột được lọc là `grade INTEGER`**, không phải mảng `skills`. Khi có B-tree index trên `grade` và điều kiện phù hợp, PostgreSQL có thể dùng index cho phép so sánh `grade = ANY(parameter_array)`. Đây là trường hợp khác với việc tìm **một phần tử nằm bên trong cột mảng**.

## 22. Toán tử ANY/ALL với LIKE, ILIKE và phép so sánh khác

Ngoài `=`, `<>`, `>`, PostgreSQL còn cho phép các toán tử boolean thích hợp đứng trước `ANY`/`ALL`, chẳng hạn so khớp mẫu văn bản.

~~~sql
SELECT
    'PostgreSQL Developer' ILIKE ANY(
        ARRAY['%postgres%', '%java%']
    ) AS matches_at_least_one_pattern,
    'PostgreSQL Developer' ILIKE ALL(
        ARRAY['%postgres%', '%developer%']
    ) AS matches_all_patterns;
-- TRUE, TRUE
~~~

### 22.1. ILIKE ANY không phải phép tìm substring tùy ý

`ILIKE` dùng quy tắc pattern matching không phân biệt hoa/thường theo PostgreSQL. `%` khớp không hoặc nhiều ký tự, `_` khớp một ký tự. Nếu muốn tìm chuỗi con theo pattern, viết đúng ký tự wildcard và kiểm soát ký tự escape.

### 22.2. Chú ý phủ định lượng từ

Giống `<> ANY`, biểu thức:

~~~sql
value NOT ILIKE ANY(pattern_array)
~~~

không có nghĩa “value không khớp **bất kỳ** pattern nào”. Nó hỏi **có ít nhất một** pattern mà value không khớp hay không.

Để phủ định “khớp ít nhất một”:

~~~sql
NOT (value ILIKE ANY(pattern_array))
~~~

hoặc diễn đạt “không khớp tất cả” bằng toán tử/`ALL` tương ứng, với điều kiện hiểu rõ NULL. Đây là một ví dụ khác của quy tắc logic:

\[
\neg(\exists x : P(x)) \equiv \forall x : \neg P(x)
\]

Không thay `ANY` thành `ALL` mà quên **phủ định toán tử**.

## 23. ARRAY và ARRAY_AGG trong truy vấn

Ngoài khai báo mảng cố định, PostgreSQL có thể xây mảng từ tập hàng:

~~~sql
SELECT ARRAY(
    SELECT employee_id
    FROM expr_lab_180.employees
    WHERE department = 'ENG'
    ORDER BY employee_id
) AS engineering_ids;
~~~

Kết quả: `{1,2,6,7}`. Cú pháp `ARRAY(subquery)` yêu cầu subquery trả **một cột** và có thể trả mảng rỗng khi subquery không có hàng.

### 23.1. ARRAY(subquery) so với array_agg

~~~sql
SELECT
    array_agg(employee_id ORDER BY employee_id)
        AS engineering_ids
FROM expr_lab_180.employees
WHERE department = 'ENG';
~~~

Truy vấn trả mảng `{1,2,6,7}`. Nhưng trên tập rỗng:

~~~sql
SELECT
    ARRAY(
        SELECT employee_id
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS array_from_empty_subquery,
    (
        SELECT array_agg(employee_id)
        FROM expr_lab_180.employees
        WHERE department = 'NON_EXISTENT'
    ) AS aggregate_from_empty_input;
~~~

- `ARRAY(subquery rỗng)` trả **mảng rỗng** có kiểu tương ứng.
- `array_agg(...)` trên tập không có hàng trả **`NULL`**, như nhiều aggregate khác ngoại trừ `COUNT`.

Điều này có ảnh hưởng nếu dùng kết quả với `ANY`/`ALL`: mảng rỗng và mảng NULL **không cùng nghĩa**.

### 23.2. Chuẩn hóa array_agg rỗng

Nếu hợp đồng API yêu cầu một danh sách rỗng khi không có hàng:

~~~sql
SELECT
    COALESCE(
        array_agg(employee_id ORDER BY employee_id),
        ARRAY[]::bigint[]
    ) AS employee_ids
FROM expr_lab_180.employees
WHERE department = 'NON_EXISTENT';
~~~

`COALESCE` ở đây là một **quyết định dữ liệu có chủ đích**, không phải một bước thay đổi nên áp dụng cho mọi mảng nullable.

### 23.3. array_agg có thể chứa phần tử NULL

~~~sql
SELECT
    array_agg(grade ORDER BY employee_id)
        AS all_grades_including_unknown
FROM expr_lab_180.employees
WHERE department = 'OPS';
~~~

Kết quả là một mảng chứa grade `1` và một phần tử `NULL`, không phải mảng chỉ có một grade.

Muốn bỏ grade NULL khỏi mảng:

~~~sql
SELECT
    COALESCE(
        array_agg(grade ORDER BY employee_id)
            FILTER (WHERE grade IS NOT NULL),
        ARRAY[]::integer[]
    ) AS known_grades
FROM expr_lab_180.employees
WHERE department = 'OPS';
-- {1}
~~~

**Array aggregate giữ hay bỏ NULL** là quyết định quan trọng khi sau đó đem mảng vào `ANY`/`ALL`.

## 24. array_position, array_remove và kiểm tra phần tử NULL

Với mảng, PostgreSQL có các hàm thao tác trực tiếp trên phần tử:

~~~sql
SELECT
    array_position(
        ARRAY['sql', NULL::text, 'kafka'],
        'kafka'
    ) AS kafka_position,
    array_position(
        ARRAY['sql', NULL::text, 'kafka'],
        NULL::text
    ) AS null_position,
    array_remove(
        ARRAY['sql', NULL::text, 'kafka'],
        NULL::text
    ) AS cleaned_array;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| Vị trí `kafka` | 3 |
| Vị trí phần tử `NULL` | 2 |
| Mảng sau khi bỏ phần tử `NULL` | `{sql,kafka}` |

Các hàm `array_position` và `array_remove` dùng ngữ nghĩa so sánh kiểu **`IS NOT DISTINCT FROM`** cho mục tiêu tìm phần tử, nên có thể tìm/xóa phần tử `NULL`. Điều này **khác** với phép bằng `= ANY` thông thường, nơi `NULL = NULL` không trả TRUE.

### 24.1. Không đồng nhất “mảng không có NULL” với “mảng có ít nhất một phần tử”

~~~sql
SELECT
    cardinality(ARRAY[]::text[]) AS empty_size,
    array_position(ARRAY[]::text[], NULL::text)
        AS null_position_in_empty;
~~~

Mảng rỗng có kích thước 0 và không có phần tử NULL nào. Một mảng chứa ba kỹ năng đều khác NULL có kích thước 3 và cũng không có phần tử NULL. Nếu cần kiểm tra cả hai tính chất, viết điều kiện riêng.

## 25. Dùng ANY/ALL trong UPDATE và truy vấn nghiệp vụ

Ví dụ một câu lệnh `UPDATE` chỉ áp dụng cho những grade thuộc danh sách được phép. Hãy dùng transaction thực hành để không thay đổi dữ liệu seed sau ví dụ:

~~~sql
BEGIN;

UPDATE expr_lab_180.employees
SET salary = salary * 1.05
WHERE department = 'ENG'
  AND grade = ANY(ARRAY[2, 3]::integer[])
  AND salary IS NOT NULL;

-- Kiểm tra bản ghi thay đổi trong transaction:
SELECT employee_id, grade, salary
FROM expr_lab_180.employees
WHERE department = 'ENG'
ORDER BY employee_id;

ROLLBACK;
~~~

Ở đây nhân viên ENG grade 2 hoặc 3 có lương đã biết được cập nhật trong transaction; `ROLLBACK` đưa dữ liệu về giá trị gốc. **Đây là ví dụ SQL học tập**, không phải chính sách tăng lương có thật.

### 25.1. Chọn tất cả bản ghi không thuộc danh sách cấm

~~~sql
SELECT
    employee_id,
    grade
FROM expr_lab_180.employees
WHERE grade <> ALL(ARRAY[4, 5]::integer[])
ORDER BY employee_id;
~~~

Các grade **1,2,3** được chọn; grade `NULL` không xuất hiện do điều kiện UNKNOWN. Nếu mục tiêu là “chỉ giữ người có grade đã xác nhận và không thuộc 4/5”, truy vấn này phù hợp. Nếu mục tiêu là “kể cả người chưa có grade”, cần quy định và thêm điều kiện `grade IS NULL` **tường minh**.

### 25.2. Chọn theo nhiều bộ khóa

~~~sql
SELECT
    employee_id,
    department,
    grade
FROM expr_lab_180.employees
WHERE (department, grade) IN (
    ('ENG', 2),
    ('SALES', 2)
)
ORDER BY employee_id;
-- 1, 5, 6
~~~

Ở đây row `(department,grade)` hợp lý hơn hai danh sách độc lập nếu cặp thuộc quy tắc.

## 26. Chỉ mục B-tree và GIN: chọn theo cấu trúc truy vấn

### 26.1. Index B-tree cho nhiều cột scalar

~~~sql
CREATE INDEX idx_employees_department_grade_180
ON expr_lab_180.employees(department, grade);
~~~

Index này có thể giúp một số truy vấn như:

~~~sql
SELECT *
FROM expr_lab_180.employees
WHERE (department, grade) = ('ENG', 2);
~~~

hoặc truy vấn có điều kiện/sắp xếp phù hợp với **tiền tố index**. Trên bảng chỉ mười hàng, PostgreSQL có thể chọn sequential scan vì chi phí rẻ hơn.

### 26.2. Index B-tree cho scalar = ANY(parameter_array)

~~~sql
CREATE INDEX idx_employees_grade_180
ON expr_lab_180.employees(grade);

SELECT
    employee_id, grade
FROM expr_lab_180.employees
WHERE grade = ANY(ARRAY[1, 3]::integer[]);
~~~

PostgreSQL có khả năng tối ưu phép so sánh scalar với mảng đầu vào bằng kế hoạch index phù hợp trong nhiều tình huống. Nhưng **không có đảm bảo mọi truy vấn `= ANY` luôn dùng index**; còn tùy kích thước bảng, số phần tử mảng, thống kê, độ chọn lọc và plan.

### 26.3. GIN index cho cột mảng

~~~sql
CREATE INDEX idx_employees_skills_gin_180
ON expr_lab_180.employees
USING GIN (skills);
~~~

GIN (*Generalized Inverted Index*) phù hợp với một số toán tử mảng như `@>`, `<@` và `&&` với operator class mặc định tương ứng:

~~~sql
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[];
~~~

~~~sql
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills && ARRAY['sql', 'postgres']::text[];
~~~

Một GIN index trên `skills` **không có nghĩa mọi biểu thức `'sql' = ANY(skills)` đều được tối ưu theo cùng cách**. Planner cần một dạng điều kiện mà index/operator class có thể hỗ trợ; với dữ liệu có NULL hoặc ngữ nghĩa đặc biệt, không rewrite vô điều kiện.

### 26.4. Đọc kế hoạch với EXPLAIN

~~~sql
EXPLAIN
SELECT
    employee_id,
    employee_name
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[];
~~~

Một kế hoạch trên dữ liệu lớn có thể dùng Bitmap Index Scan qua GIN và Bitmap Heap Scan, nhưng với bảng lab ít dòng, sequential scan là bình thường. Chỉ kết luận hiệu năng sau khi đo trên tập dữ liệu và workload đại diện.

~~~sql
-- Trên môi trường an toàn, EXPLAIN ANALYZE chạy query thật:
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    employee_id
FROM expr_lab_180.employees
WHERE grade = ANY(ARRAY[1, 3]::integer[]);
~~~

`EXPLAIN (ANALYZE, BUFFERS)` thực thi truy vấn để đo; không chạy trên production nếu chưa biết chi phí và mục đích.

### 26.5. Tối ưu phụ thuộc dạng lưu trữ dữ liệu

Nếu cần truy vấn thành viên **rất thường xuyên**, điều kiện:

~~~sql
skills @> ARRAY['sql']::text[]
~~~

có thể tận dụng index GIN phù hợp. Nhưng nếu cần lưu thuộc tính riêng cho từng kỹ năng (trình độ, ngày xác nhận, nguồn chứng chỉ), một bảng liên kết sẽ dễ đặt FK, UNIQUE, CHECK và index có chủ đích hơn. Index không thể thay một mô hình dữ liệu phù hợp.

## 27. Mảng so với bảng liên kết quan hệ

Một cột `skills TEXT[]` phù hợp khi danh sách nhỏ, cùng kiểu và thường được đọc/ghi như **một khối giá trị**. Nhưng có những tình huống nên dùng bảng liên kết:

~~~sql
CREATE TABLE expr_lab_180.skills_catalog (
    skill_code TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL
);

CREATE TABLE expr_lab_180.employee_skills (
    employee_id BIGINT NOT NULL
        REFERENCES expr_lab_180.employees(employee_id),
    skill_code TEXT NOT NULL
        REFERENCES expr_lab_180.skills_catalog(skill_code),
    confirmed_at TIMESTAMPTZ NULL,

    CONSTRAINT employee_skills_pk
        PRIMARY KEY (employee_id, skill_code)
);
~~~

Mô hình này có:

- Một dòng cho mỗi cặp nhân viên–kỹ năng.
- Khóa ngoại để ngăn mã kỹ năng không tồn tại.
- `PRIMARY KEY(employee_id, skill_code)` để tránh cặp trùng.
- Có thể thêm metadata cho quan hệ, ví dụ ngày xác nhận.

Trong khi `skills TEXT[]` không tự bảo đảm mỗi phần tử tồn tại ở bảng danh mục chỉ nhờ một FK thông thường. Nếu cần quy tắc toàn vẹn ở cấp **từng phần tử**, relational junction table thường có lợi.

### 27.1. So sánh hai cách hỏi “có kỹ năng sql”

Cột mảng:

~~~sql
SELECT employee_id
FROM expr_lab_180.employees
WHERE skills @> ARRAY['sql']::text[];
~~~

Bảng liên kết (sau khi có dữ liệu phù hợp):

~~~sql
SELECT employee_id
FROM expr_lab_180.employee_skills
WHERE skill_code = 'sql';
~~~

Không có một cách tối ưu cho mọi hệ thống. Phải xét quy mô, tần suất đọc/ghi, yêu cầu toàn vẹn tham chiếu, độ phức tạp truy vấn và tính linh hoạt của schema.

## 28. Tham số mảng từ Java/JDBC

Khi giao diện cho người dùng chọn nhiều grade để lọc, **không nên tạo một chuỗi SQL bằng cách ghép từng ID**. Có thể dùng JDBC `java.sql.Array` và prepared statement:

~~~java
Integer[] grades = {1, 3};

String sql = """
    SELECT employee_id, employee_name, grade
    FROM expr_lab_180.employees
    WHERE grade = ANY(?::integer[])
    ORDER BY employee_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    java.sql.Array gradeArray =
        connection.createArrayOf("int4", grades);

    try {
        ps.setArray(1, gradeArray);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(
                    rs.getLong("employee_id") + " " +
                    rs.getString("employee_name")
                );
            }
        }
    } finally {
        gradeArray.free();
    }
}
~~~

Đoạn code giả định `connection` là JDBC `Connection` đã mở, và môi trường Java hỗ trợ text block. `int4` là tên kiểu phần tử PostgreSQL tương ứng với `integer`. Hành vi hỗ trợ driver và cách quản lý `Array.free()` nên được đối chiếu theo phiên bản PostgreSQL JDBC đang dùng.

### 28.1. Danh sách rỗng và NULL khi nhận từ API

Ứng dụng phải quyết định rõ:

- **Danh sách chọn rỗng `[]`:** có nghĩa “không chọn grade nào”, vậy `grade = ANY('{}')` trả FALSE và truy vấn không chọn hàng.
- **Không gửi trường filter:** có nghĩa “không áp dụng bộ lọc grade”, thường nên **không thêm điều kiện `grade = ANY(...)`**.
- **Gửi `null`:** có nghĩa chưa biết hay không áp dụng? Không nên âm thầm biến thành mảng rỗng nếu hợp đồng API không quy định như vậy.

Đây là khác biệt giữa **dữ liệu không có phần tử** và **người dùng không yêu cầu lọc**. Nhầm hai trạng thái có thể làm trang danh sách trả rỗng ngoài ý muốn.

### 28.2. Truyền array parameter giúp giữ kiểu

~~~sql
WHERE grade = ANY(?::integer[])
~~~

Giữ kiểu integer giúp PostgreSQL chọn toán tử so sánh phù hợp; các phép bind tránh nội suy SQL không an toàn. Tuy nhiên, dùng prepared statement **không tự giới hạn kích thước mảng quá lớn**; application vẫn cần giới hạn input và đánh giá chi phí truy vấn.

### 28.3. Đọc cột mảng

~~~java
String sql = """
    SELECT employee_id, skills
    FROM expr_lab_180.employees
    WHERE employee_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.sql.Array sqlArray = rs.getArray("skills");
            if (sqlArray != null) {
                try {
                    Object[] values = (Object[]) sqlArray.getArray();
                    System.out.println(
                        java.util.Arrays.toString(values)
                    );
                } finally {
                    sqlArray.free();
                }
            }
        }
    }
}
~~~

Lưu ý JDBC trả `null` khi **toàn bộ cột mảng là NULL**; một mảng rỗng có thể trả một Java array độ dài 0; mảng có phần tử SQL NULL có thể chứa phần tử Java `null`. Cách ánh xạ phần tử cụ thể phụ thuộc driver và kiểu SQL.

## 29. Những lỗi phổ biến

| Cách hiểu hoặc cách viết sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| `(a,b) < (x,y)` nghĩa là `a<x AND b<y` | Row so theo thứ tự từ điển | Trường đầu có thể quyết định ngay |
| `ROW(1,NULL) = ROW(1,NULL)` là TRUE | Phép bằng row có thể UNKNOWN | Dùng `IS NOT DISTINCT FROM` khi cần null-safe |
| `ROW(1,NULL) IS NOT NULL` là TRUE | Row có một trường NULL không thỏa | Kiểm tra quy tắc `IS NULL`/`IS NOT NULL` của row |
| `(department,grade) IN (...)` tương đương hai IN độc lập | Hai IN độc lập tạo mọi tổ hợp | Dùng row IN khi cần **cặp** đúng |
| `ARRAY[1,2] = ARRAY[2,1]` là TRUE | Mảng phân biệt thứ tự | Dùng containment/tập nếu chỉ cần thành viên |
| `ARRAY[1] @> ARRAY[1,1]` là FALSE | Containment không tính số lần | Không dùng @> để so multiset |
| `NULL::int[]` giống mảng rỗng | Một bên chưa biết, một bên biết rỗng | Phân biệt NULL array và `{}` |
| `ARRAY[NULL]` là mảng NULL | Mảng tồn tại, có một phần tử NULL | Phân biệt cột mảng NULL với phần tử NULL |
| `2 = ANY({1,NULL})` là FALSE | Có UNKNOWN nên kết quả NULL | Xử lý/phân loại NULL tường minh |
| `2 = ALL({1,2,3})` kiểm tra membership | Nó yêu cầu bằng **mọi** phần tử | Dùng `= ANY` |
| `2 <> ANY({1,2})` nghĩa là NOT IN | Chỉ cần khác **một** phần tử | `<> ALL` hoặc `NOT (= ANY)` |
| `ALL(empty)` là FALSE | ALL trên tập rỗng là TRUE | Hiểu vacuous truth |
| `NOT IN (SELECT nullable_col...)` luôn an toàn | NULL có thể làm điều kiện UNKNOWN | Cân nhắc `NOT EXISTS` và quy tắc NULL |
| `x > ALL(values)` luôn bằng `x > MAX(values)` | Khác ở tập rỗng/NULL | Chỉ thay khi điều kiện tương đương được bảo đảm |
| `= ANY` trên cột mảng luôn dùng GIN | Không mặc định indexable như @> | Đo plan, chọn toán tử/index phù hợp |
| `array_length(empty,1)` bằng 0 | PostgreSQL có thể trả NULL | Dùng `cardinality` cho số phần tử |
| `unnest(array)` tự bỏ phần tử NULL | Phần tử NULL tạo hàng NULL | Lọc tường minh khi cần |
| `array_agg` rỗng trả `{}` | Aggregate có thể trả NULL | `COALESCE(array_agg(...), ARRAY[]::type[])` khi phù hợp |
| `SEARCH/ROW/ARRAY` có thể thay schema quan hệ | Mảng không tự có FK tới từng phần tử | Dùng junction table nếu cần toàn vẹn |
| Danh sách filter rỗng đồng nghĩa không lọc | `= ANY('{}')` luôn FALSE | Phân biệt filter trống và không gửi filter |

## 30. Bài tập thực hành

Các bài tập dùng bộ dữ liệu `expr_lab_180` đã tạo. Hãy viết query trước khi xem gợi ý/kết quả và giải thích không chỉ giá trị được chọn mà cả các hàng bị loại do `NULL`.

### Bài 1 — So sánh hai row

Dự đoán:

~~~sql
SELECT
    ROW(1, 100) < ROW(2, 0) AS a,
    ROW(1, 100) < ROW(1, 200) AS b,
    ROW(2, 100) < ROW(1, 999) AS c;
~~~

**Đáp án:** TRUE, TRUE, FALSE. Giải thích thứ tự từ trái sang phải.

### Bài 2 — NULL trong row equality

~~~sql
SELECT
    ROW(1, NULL::integer) = ROW(1, NULL::integer)
        AS ordinary_equality,
    ROW(1, NULL::integer)
        IS NOT DISTINCT FROM ROW(1, NULL::integer)
        AS null_safe_equality;
~~~

**Đáp án:** NULL và TRUE. Vì sao hai biểu thức không giống nhau?

### Bài 3 — Row IS NULL

Chạy:

~~~sql
SELECT
    ROW(NULL::integer, NULL::text) IS NULL AS all_null,
    ROW(1, NULL::text) IS NULL AS mixed_is_null,
    ROW(1, NULL::text) IS NOT NULL AS mixed_is_not_null;
~~~

**Đáp án:** TRUE, FALSE, FALSE. Tại sao row có một trường NULL có thể khiến hai phép kiểm tra đều FALSE?

### Bài 4 — Lọc cặp department–grade

Dùng `(department, grade) IN (('ENG',2),('OPS',1))`. Các ID nào được chọn?

**Đáp án:** **1, 3, 6**.

Sau đó so với `department IN ('ENG','OPS') AND grade IN (1,2)`; tìm nhân viên xuất hiện thêm và giải thích vì sao.

### Bài 5 — Row IN với bảng điều kiện

Viết truy vấn dùng `(department,grade) IN (SELECT department,grade FROM eligible_pairs)`.

**Đáp án:** **1, 2, 3, 5, 6**. Nhân viên 7 có `('ENG',1)` không được chọn dù grade 1 là một giá trị hợp lệ ở department khác.

### Bài 6 — Mảng rỗng và phần tử NULL

So sánh:

~~~sql
SELECT
    cardinality(ARRAY[]::integer[]) AS a,
    array_length(ARRAY[]::integer[], 1) AS b,
    cardinality(NULL::integer[]) AS c,
    cardinality(ARRAY[NULL::integer]) AS d;
~~~

**Đáp án:** 0, NULL, NULL, 1.

### Bài 7 — Thứ tự trong mảng và containment

Dự đoán:

~~~sql
SELECT
    ARRAY[1, 2] = ARRAY[2, 1] AS a,
    ARRAY[1, 2] @> ARRAY[2] AS b,
    ARRAY[1, 2] && ARRAY[2, 3] AS c,
    ARRAY[1] @> ARRAY[1, 1] AS d;
~~~

**Đáp án:** FALSE, TRUE, TRUE, TRUE. Phân biệt phép bằng mảng với quan hệ tập phần tử.

### Bài 8 — ANY cơ bản

Tìm mọi nhân viên có `'sql'` trong mảng `skills` bằng `'sql' = ANY(skills)`.

**Đáp án:** **1, 2, 6**. Nếu dùng `skills @> ARRAY['sql']::text[]`, bộ dữ liệu mẫu có cho cùng danh sách không?

### Bài 9 — Hai kỹ năng đồng thời và ít nhất một

Viết hai truy vấn:

1. Có **cả** `sql` và `postgres`.
2. Có **sql hoặc postgres**.

**Gợi ý:** `@> ARRAY['sql','postgres']` và `&& ARRAY['sql','postgres']`.

**Đáp án:** nhóm 1: **1**; nhóm 2: **1, 2, 3, 6**.

### Bài 10 — ANY/ALL trên mảng rỗng

~~~sql
SELECT
    9 = ANY(ARRAY[]::integer[]) AS a,
    9 <> ALL(ARRAY[]::integer[]) AS b,
    9 > ALL(ARRAY[]::integer[]) AS c;
~~~

**Đáp án:** FALSE, TRUE, TRUE. Giải thích “vacuous truth”.

### Bài 11 — ANY với NULL phần tử

~~~sql
SELECT
    2 = ANY(ARRAY[1, NULL::integer, 3]) AS a,
    3 = ANY(ARRAY[1, NULL::integer, 3]) AS b,
    3 <> ALL(ARRAY[1, NULL::integer, 3]) AS c;
~~~

**Đáp án:** NULL, TRUE, FALSE. Xác định phép so sánh nào đã quyết định ở b và c.

### Bài 12 — Phân biệt mảng NULL và mảng rỗng trong luật

Join `employees` với `department_rules` rồi trả `grade = ANY(allowed_grades)` cho các nhân viên 9, 10.

**Đáp án:** nhân viên QA **9 → FALSE** vì `{}`; nhân viên RND **10 → NULL** vì `allowed_grades IS NULL`.

### Bài 13 — <> ANY không phải NOT IN

~~~sql
SELECT
    2 <> ANY(ARRAY[1, 2]) AS wrong_not_in,
    2 <> ALL(ARRAY[1, 2]) AS correct_not_in;
~~~

**Đáp án:** TRUE, FALSE. Hãy viết một câu tiếng Việt cho từng biểu thức.

### Bài 14 — Bẫy NOT IN với subquery

Viết truy vấn lấy nhân viên có grade **không bằng bất kỳ grade đã biết** của OPS. So sánh:

- `grade NOT IN (SELECT grade FROM employees WHERE department='OPS')`;
- `NOT EXISTS (SELECT 1 ... WHERE ops.grade = e.grade)` với `e.grade IS NOT NULL`.

**Gợi ý:** OPS có grade 1 và NULL. Truy vấn `NOT IN` có thể trả **0 hàng**, còn cách `NOT EXISTS` có điều kiện đã nêu chọn nhân viên grade 2 hoặc 3.

### Bài 15 — ALL và MAX khác ở tập rỗng

~~~sql
SELECT
    5 > ALL(ARRAY[]::integer[]) AS a,
    5 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[]::integer[]) AS u(x)
    ) AS b;
~~~

**Đáp án:** TRUE và NULL. Giải thích vì sao không thể thay `> ALL` bằng `> MAX` trong mọi trường hợp.

### Bài 16 — ALL và MAX khác khi có NULL

~~~sql
SELECT
    5 > ALL(ARRAY[1, NULL::integer, 3]) AS a,
    5 > (
        SELECT MAX(x)
        FROM unnest(ARRAY[1, NULL::integer, 3]) AS u(x)
    ) AS b;
~~~

**Đáp án:** NULL và TRUE. `MAX` bỏ qua NULL nhưng lượng từ ALL vẫn nhận UNKNOWN.

### Bài 17 — Array_agg và ARRAY(subquery)

Tạo danh sách employee_id của department không tồn tại bằng cả `ARRAY(SELECT...)` và `array_agg(...)`. Kết quả khác nhau như thế nào?

**Đáp án:** `ARRAY(SELECT...)` trả mảng rỗng, `array_agg` trả NULL. Dùng `COALESCE` khi hợp đồng API cần `[]`.

### Bài 18 — Kiểm tra phần tử NULL bằng array_position

~~~sql
SELECT
    array_position(ARRAY['sql', NULL::text, 'kafka'], NULL::text)
        AS position_of_null,
    array_remove(ARRAY['sql', NULL::text, 'kafka'], NULL::text)
        AS without_null;
~~~

**Đáp án:** vị trí **2**, mảng **{sql,kafka}**. Vì sao tìm `NULL` bằng `array_position` có thể thành công, trong khi `NULL = ANY(...)` không trả TRUE?

### Bài 19 — Phân trang theo hai cột

Giả sử một bảng có `(created_at TIMESTAMPTZ NOT NULL, id BIGINT PRIMARY KEY)`. Viết một query lấy 20 bản ghi sau `(last_created_at, last_id)`, sắp ASC theo hai cột.

**Gợi ý:** `WHERE (created_at,id) > (:last_created_at,:last_id) ORDER BY created_at,id LIMIT 20`. Giải thích lý do cần ID tie-breaker.

### Bài 20 — Chỉ mục

So sánh hai mục tiêu:

1. Lọc `grade = ANY(ARRAY[1,3])` trên cột grade kiểu INTEGER.
2. Lọc `skills @> ARRAY['sql']` trên cột skills kiểu TEXT[].

Hãy chọn loại index ứng viên và giải thích vì sao một index B-tree scalar khác GIN trên mảng. Sau đó xem `EXPLAIN` trên dữ liệu lab và giải thích vì sao index có thể chưa được dùng ở bảng nhỏ.

### Bài 21 — Thiết kế API lọc đa lựa chọn

Một frontend gửi:

~~~text
grade_filter = [1, 3]
grade_filter = []
grade_filter không được gửi
grade_filter = null
~~~

Hãy xác định hợp đồng xử lý bốn trường hợp. Có nên coi `[]` và “không gửi trường” như nhau không? Nếu không, SQL cần được xây theo nhánh nào để trả đúng kết quả?

### Bài 22 — Chọn array hay junction table

Một sản phẩm có nhiều nhãn, mỗi nhãn phải có người duyệt, ngày tạo, trạng thái và khóa ngoại tới bảng nhãn hợp lệ. Nên dùng `text[]` hay bảng quan hệ `product_labels(product_id,label_id,reviewed_by,created_at,status)`? Trình bày ưu/nhược về FK, UNIQUE, truy vấn và ghi dữ liệu.

## 31. Mẫu truy vấn tổng hợp

Một báo cáo quản trị có thể cần đồng thời:

- Số nhân viên mỗi bộ phận;
- Bao nhiêu người có kỹ năng SQL;
- Bao nhiêu người có grade hợp lệ theo mảng quy tắc;
- Bao nhiêu người bị thiếu grade hoặc danh sách quy tắc.

Ví dụ dùng `LEFT JOIN` với bảng quy tắc:

~~~sql
SELECT
    e.department,
    COUNT(*) AS employee_count,
    COUNT(*) FILTER (
        WHERE 'sql' = ANY(e.skills)
    ) AS sql_skill_count,
    COUNT(*) FILTER (
        WHERE e.grade = ANY(r.allowed_grades)
    ) AS allowed_grade_count,
    COUNT(*) FILTER (
        WHERE e.grade IS NULL
    ) AS missing_grade_count,
    COUNT(*) FILTER (
        WHERE r.allowed_grades IS NULL
    ) AS missing_rule_array_count,
    COUNT(*) FILTER (
        WHERE r.allowed_grades = ARRAY[]::integer[]
    ) AS empty_rule_array_count
FROM expr_lab_180.employees AS e
LEFT JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
GROUP BY e.department
ORDER BY e.department;
~~~

Diễn giải:

- `COUNT(*) FILTER (WHERE 'sql' = ANY(skills))` chỉ đếm khi membership **TRUE**, không đếm UNKNOWN.
- `allowed_grade_count` không xem quy tắc NULL như cho phép hoặc cấm tất cả; nó **không đếm hàng chưa thể xác nhận**.
- `missing_rule_array_count` xem tất cả nhân viên có mảng rule NULL; với một department không có dòng join, `r.allowed_grades` cũng NULL, nên nếu cần phân biệt **không có rule record** và **rule record có cột NULL**, phải xét `r.department IS NULL`.
- `empty_rule_array_count` đếm mảng đã xác nhận rỗng, không gộp với NULL.

Ví dụ báo cáo này cho thấy việc dùng `ANY` trong aggregate không chỉ để lọc; nó còn giúp phân loại **đúng, sai và chưa xác định** nếu ta thiết kế thêm các cột KPI tương ứng.

### 31.1. Báo cáo ba trạng thái cho quy tắc grade

~~~sql
SELECT
    e.employee_id,
    e.department,
    e.grade,
    CASE
        WHEN r.department IS NULL
            THEN 'Không tìm thấy quy tắc'
        WHEN r.allowed_grades IS NULL
            THEN 'Danh sách quy tắc chưa xác định'
        WHEN e.grade IS NULL
            THEN 'Grade chưa xác định'
        WHEN e.grade = ANY(r.allowed_grades)
            THEN 'Được phép'
        ELSE 'Không được phép'
    END AS rule_decision
FROM expr_lab_180.employees AS e
LEFT JOIN expr_lab_180.department_rules AS r
    ON r.department = e.department
ORDER BY e.employee_id;
~~~

Khác với một `WHERE grade = ANY(...)` chỉ trả những hàng TRUE, `CASE` này **giữ và diễn giải** các trường hợp NULL/thiếu dữ liệu. Đó là cách phù hợp hơn khi người quản trị cần biết **vì sao** một nhân viên không được xác nhận hợp lệ.

## 32. Tổng kết

**Row constructor** cho phép so sánh nhiều giá trị theo đúng **vị trí tương ứng**. `=`/`<>` có thể trả `NULL` khi gặp trường chưa biết; `IS [NOT] DISTINCT FROM` hữu ích khi cần so sánh null-safe. Các phép `<`/`>` trên row dùng **thứ tự từ điển**, rất phù hợp với khóa tổng hợp và keyset pagination. Mệnh đề `(a,b) IN (...)` biểu diễn **cặp được phép** — khác với hai điều kiện `a IN (...) AND b IN (...)` độc lập.

**Mảng PostgreSQL** lưu các phần tử cùng kiểu và giữ **thứ tự**. Phép `=` so giá trị mảng, trong khi `@>`, `<@` và `&&` hỏi về chứa/giao nhau và không đếm số lần phần tử xuất hiện. **Mảng rỗng**, **mảng NULL** và **mảng có phần tử NULL** là ba trạng thái khác nhau; `cardinality`, `unnest`, `array_agg`, `array_position` và `array_remove` giúp xử lý chúng có chủ đích.

**`ANY`/`SOME` nghĩa là “ít nhất một”, `ALL` nghĩa là “tất cả”** đối với kết quả của một toán tử so sánh. Vì SQL có logic ba giá trị, một phần tử NULL có thể khiến kết quả là UNKNOWN; với **tập rỗng**, ANY trả FALSE và ALL trả TRUE. `IN` gần với `= ANY`, còn `NOT IN` gần với `<> ALL` — **không phải `<> ANY`**. Khi dữ liệu nguồn có NULL và cần anti-join, `NOT EXISTS` cùng điều kiện so sánh được định nghĩa rõ thường dễ kiểm soát hơn.

Cuối cùng, hãy chọn cấu trúc phù hợp với mục tiêu: **row** cho tổ hợp khóa, **array** cho danh sách nhỏ cùng kiểu, **subquery/EXISTS** cho quan hệ dữ liệu, **B-tree** cho điều kiện trên scalar và **GIN** cho một số toán tử trên cột mảng. Viết SQL đúng không chỉ là chọn ký hiệu đúng; còn là xác định **tập rỗng có nghĩa gì, dữ liệu NULL biểu thị điều gì, và kết quả TRUE/FALSE/UNKNOWN được phép tác động ra sao tới nghiệp vụ**.
