# Hàm trả tập và sử dụng trong FROM

Trong PostgreSQL, nhiều hàm không chỉ trả về **một giá trị** mà có thể trả về **không, một hoặc nhiều hàng**. Những hàm như `generate_series()`, `unnest()`, `jsonb_array_elements()`, `jsonb_to_recordset()` và các hàm do lập trình viên định nghĩa thường được gọi là **set-returning functions (SRF)** — *hàm trả tập*. Khi đặt trong mệnh đề **`FROM`**, kết quả của chúng được đối xử như một **nguồn hàng** mà câu truy vấn có thể lọc, kết hợp, tổng hợp hoặc sắp xếp.

Hãy hình dung một dự án có mảng các nhãn `['java', 'postgresql', 'api']`. Thay vì lưu ba cột `tag1`, `tag2` và `tag3`, bạn có thể giữ một mảng `text[]` rồi dùng `unnest()` biến từng phần tử thành một hàng. Khi muốn tạo lịch báo cáo bảy ngày liên tiếp, `generate_series()` sinh các mốc mà không cần lưu sẵn bảng lịch. Khi nhận một JSON array gồm nhiều thành viên, `jsonb_to_recordset()` có thể biến các object thành những cột có kiểu rõ ràng.

Khó khăn quan trọng nhất xuất hiện khi SRF **phụ thuộc vào từng hàng của một bảng khác**: từ khóa **`LATERAL`**, thứ tự nguồn trong `FROM` và lựa chọn **`CROSS JOIN` hay `LEFT JOIN`** sẽ quyết định hàng nào được giữ lại. Một SRF trả **0 hàng** có thể làm mất hàng cha khỏi kết quả nếu sử dụng phép join không phù hợp.

Trong bài này, bạn sẽ:

- Hiểu SRF, table function, kiểu trả về `SETOF`, `TABLE` và cách gọi trong `FROM`.
- Dùng `generate_series()` tạo dãy số, thời gian và khung ngày.
- Trải phẳng mảng với `unnest()`, đọc vị trí bằng `WITH ORDINALITY` và `generate_subscripts()`.
- Tách JSON array/object bằng `jsonb_array_elements()`, `jsonb_to_recordset()` và các hàm liên quan.
- Phân biệt **SRF trong `FROM`**, **truy vấn con** và quy tắc `LATERAL`.
- Dùng `LEFT JOIN LATERAL ... ON TRUE` để giữ hàng cha dù hàm không trả hàng.
- Viết hàm trả tập bằng SQL và PL/pgSQL, rồi kết hợp với bảng khác.
- Tránh lỗi nhân số hàng, lỗi phạm vi alias, dữ liệu JSON sai cấu trúc, kết quả thiếu thứ tự và các nút thắt hiệu năng.

> **Môi trường:** Các ví dụ dùng PostgreSQL hiện đại và một database lab. Dùng tên schema `lesson_srf` để không phụ thuộc `search_path`. Những thao tác `CREATE SCHEMA`, `CREATE TABLE` và `CREATE FUNCTION` yêu cầu quyền phù hợp; không chạy trên database production có dữ liệu quan trọng.

## 1. Từ hàm trả một giá trị đến hàm trả một tập

Hàm thông thường nhận đối số và tạo **một giá trị**:

```sql
SELECT upper('postgresql') AS result;
-- POSTGRESQL

SELECT length('postgresql') AS character_count;
-- 10
```

Hàm trả tập có thể tạo **nhiều hàng** từ một lời gọi:

```sql
SELECT n
FROM generate_series(1, 5) AS g(n);
```

Kết quả:

```text
 n
---
 1
 2
 3
 4
 5
```

`generate_series(1, 5)` là một **nguồn dữ liệu** trong `FROM`. `AS g(n)` đặt:

- `g`: tên nguồn/alias của hàm.
- `n`: tên cột đầu ra do nguồn này cung cấp.

Giống như một bảng, nguồn SRF có thể tham gia `JOIN`, `WHERE`, `GROUP BY`, `ORDER BY` và các truy vấn con.

### Một hàm, số lượng hàng thay đổi

```sql
SELECT n FROM generate_series(1, 3) AS g(n);
-- 3 hàng

SELECT n FROM generate_series(1, 1) AS g(n);
-- 1 hàng

SELECT n FROM generate_series(5, 1) AS g(n);
-- 0 hàng khi step mặc định là +1
```

Không nên nghĩ một lời gọi hàm trong `FROM` luôn tạo chính xác một hàng giống hàm scalar. Khi kết hợp với bảng khác, **độ lớn kết quả** phụ thuộc số hàng mà hàm trả về ở mỗi lần gọi.

### SRF và aggregate không phải một khái niệm

| Loại | Hướng biến đổi điển hình | Ví dụ |
|---|---|---|
| **Scalar function** | Một đầu vào → một giá trị. | `upper('abc')` → `'ABC'`. |
| **Set-returning function** | Một lời gọi → 0..N hàng. | `generate_series(1,3)` → 1, 2, 3. |
| **Aggregate** | N hàng trong một nhóm → một giá trị. | `array_agg(x ORDER BY ...)` → một mảng. |
| **Window function** | Xử lý các hàng trong partition/frame mà không nhất thiết giảm số hàng đầu ra. | `row_number() OVER (...)`. |

Trong thực tế, bạn có thể **trải phẳng với SRF** rồi **tổng hợp lại bằng aggregate**. Cần phân biệt bước nào làm **tăng** và bước nào làm **giảm** số hàng.

## 2. Các kiểu hàm trả tập trong PostgreSQL

Một SRF có thể trả về:

1. **Một cột scalar**: `generate_series()` trả `integer`/`bigint`/`numeric`/timestamp tùy overload; `unnest(text[])` trả từng `text`.
2. **Một kiểu composite**: nhiều cột theo kiểu bảng, kiểu composite hoặc `record` có khai báo phù hợp.
3. **Một bảng kết quả có tên cột** qua `RETURNS TABLE(...)`.
4. **Một tập JSON/record** được mở ra thành những hàng có cột được định nghĩa ở `FROM`.

Ví dụ đơn cột:

```sql
SELECT x.value
FROM unnest(ARRAY[10, 20, 30]) AS x(value);
```

Ví dụ nhiều cột từ JSON:

```sql
SELECT m.name, m.role
FROM jsonb_to_recordset(
    '[{"name":"An","role":"dev"},
      {"name":"Bình","role":"reviewer"}]'::jsonb
) AS m(name text, role text);
```

Ở ví dụ thứ hai, `AS m(name text, role text)` không chỉ đổi tên: nó định nghĩa **kiểu và tên cột** của kết quả recordset. PostgreSQL dùng những thông tin đó để chuyển các giá trị JSON sang cột SQL tương ứng.

## 3. Dữ liệu mẫu: dự án, nhãn và công việc

Để theo dõi SRF với dữ liệu thật, tạo một schema và hai bảng:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_srf;

CREATE TABLE lesson_srf.projects (
    project_id BIGINT PRIMARY KEY,
    project_name TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    members JSONB NOT NULL DEFAULT '[]'::jsonb,
    CONSTRAINT chk_members_is_array
        CHECK (jsonb_typeof(members) = 'array')
);

CREATE TABLE lesson_srf.tasks (
    task_id BIGINT PRIMARY KEY,
    project_id BIGINT NOT NULL
        REFERENCES lesson_srf.projects(project_id),
    task_title TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('TODO', 'DOING', 'DONE')),
    created_at TIMESTAMPTZ NOT NULL
);
```

Chèn dữ liệu:

```sql
INSERT INTO lesson_srf.projects(
    project_id, project_name, tags, members
)
VALUES
    (
        1,
        'Alpha',
        ARRAY['java', 'postgresql', 'api']::text[],
        '[
           {"name":"An","role":"developer"},
           {"name":"Bình","role":"reviewer"}
         ]'::jsonb
    ),
    (
        2,
        'Beta',
        ARRAY['frontend', 'api']::text[],
        '[]'::jsonb
    ),
    (
        3,
        'Gamma',
        ARRAY[]::text[],
        '[{"name":"Chi","role":"lead"}]'::jsonb
    );

INSERT INTO lesson_srf.tasks(
    task_id, project_id, task_title, status, created_at
)
VALUES
    (11, 1, 'Thiết kế schema', 'DONE',
        TIMESTAMPTZ '2026-11-10 09:00:00+07'),
    (12, 1, 'Viết API', 'DOING',
        TIMESTAMPTZ '2026-11-11 10:00:00+07'),
    (13, 1, 'Kiểm thử API', 'TODO',
        TIMESTAMPTZ '2026-11-12 11:00:00+07'),
    (21, 2, 'Xây UI', 'DOING',
        TIMESTAMPTZ '2026-11-13 14:00:00+07');
```

Tổng quan:

| Project | Nhãn `tags` | `members` | Số task |
|---|---|---|---:|
| Alpha (1) | java, postgresql, api | An, Bình | 3 |
| Beta (2) | frontend, api | Mảng JSON rỗng | 1 |
| Gamma (3) | Mảng text rỗng | Chi | 0 |

Bộ dữ liệu giúp quan sát hai tình huống hay gặp: **mảng rỗng** khiến SRF trả 0 hàng và **dự án chưa có task** cần vẫn được giữ trong báo cáo.

## 4. Cú pháp SRF trong FROM và alias

Dạng cơ bản:

```sql
SELECT t.column_name
FROM some_set_returning_function(arguments)
     AS t(column_name);
```

Với hàm nhiều cột, danh sách cột có thể gồm nhiều tên, và đối với hàm trả `record` chưa có cấu trúc cố định thì có thể cần **kiểu dữ liệu**:

```sql
SELECT x.name, x.role
FROM jsonb_to_recordset(
    '[{"name":"An","role":"developer"}]'::jsonb
) AS x(name text, role text);
```

### Tại sao nên đặt alias?

Alias giúp tránh những tên mặc định khó đọc như `generate_series` hoặc `unnest`, đặc biệt khi có nhiều hàm:

```sql
SELECT g.number, t.tag
FROM generate_series(1, 2) AS g(number)
CROSS JOIN unnest(ARRAY['java', 'sql']::text[]) AS t(tag)
ORDER BY g.number, t.tag;
```

Kết quả gồm **2 × 2 = 4 hàng**, vì đây là `CROSS JOIN` của hai tập độc lập.

### Phạm vi tên vẫn giống nguồn bảng

Trong:

```sql
FROM generate_series(1, 5) AS series(value)
```

`series` là alias nguồn và `value` là cột có thể dùng ở `SELECT`/`WHERE`. Nếu trong cùng query block bạn đặt alias, hãy dùng alias ấy để chỉ nguồn thay vì cố tham chiếu tên hàm như một tên bảng cũ.

## 5. generate_series(): tạo dãy số nguyên

Một overload phổ biến:

```sql
generate_series(start, stop [, step])
```

Trong PostgreSQL, `stop` **được bao gồm nếu dãy bước tới đúng mốc ấy**.

```sql
SELECT n
FROM generate_series(1, 5) AS s(n);
-- 1, 2, 3, 4, 5

SELECT n
FROM generate_series(2, 10, 2) AS s(n);
-- 2, 4, 6, 8, 10

SELECT n
FROM generate_series(5, 1, -2) AS s(n);
-- 5, 3, 1
```

### Hướng bước và giới hạn

| Gọi | Kết quả | Giải thích |
|---|---|---|
| `generate_series(1,5)` | 1,2,3,4,5 | Bước mặc định +1. |
| `generate_series(1,5,2)` | 1,3,5 | Bước dương. |
| `generate_series(5,1,-2)` | 5,3,1 | Bước âm. |
| `generate_series(5,1,1)` | 0 hàng | Start lớn hơn stop khi bước dương. |
| `generate_series(1,5,-1)` | 0 hàng | Start nhỏ hơn stop khi bước âm. |
| `generate_series(1,5,0)` | Lỗi | Bước bằng 0 không tạo tiến trình hữu hạn. |

Với các overload số, nếu một tham số bắt buộc là SQL `NULL`, hàm thường trả **0 hàng** chứ không trả một hàng chứa null. Điều này khác hàm scalar thông thường có thể trả một giá trị null.

### Lọc những số sinh ra

```sql
SELECT s.n
FROM generate_series(1, 20) AS s(n)
WHERE s.n % 3 = 0
ORDER BY s.n;
```

Kết quả: 3, 6, 9, 12, 15, 18. SRF tạo nguồn hàng; `WHERE` lọc theo phép chia lấy dư.

### Sinh số bằng numeric

```sql
SELECT x.value
FROM generate_series(
    0.0::numeric,
    1.0::numeric,
    0.25::numeric
) AS x(value);
-- 0.0, 0.25, 0.50, 0.75, 1.00
```

Chọn kiểu `numeric` khi muốn bước thập phân chính xác theo biểu diễn số thập phân, thay vì tự tạo dữ liệu tiền tệ bằng kiểu floating-point mà không xét sai số.

## 6. generate_series() với timestamp và interval

PostgreSQL có overload sinh mốc thời gian từ start tới stop theo một `interval`:

```sql
SELECT t.day_start
FROM generate_series(
    TIMESTAMP '2026-11-10 00:00:00',
    TIMESTAMP '2026-11-14 00:00:00',
    INTERVAL '1 day'
) AS t(day_start)
ORDER BY t.day_start;
```

Ví dụ tạo 5 mốc midnight, mỗi mốc là `timestamp without time zone`.

### Tạo khung ngày cho báo cáo

```sql
SELECT g.day_start::date AS report_date
FROM generate_series(
    TIMESTAMP '2026-11-10',
    TIMESTAMP '2026-11-14',
    INTERVAL '1 day'
) AS g(day_start)
ORDER BY report_date;
```

Kết quả gồm những ngày 10, 11, 12, 13, 14/11/2026. Lịch được sinh từ hàm, không đòi có sẵn bảng calendar.

### Lưu ý múi giờ và DST

`timestamp without time zone` mô tả ngày/giờ theo đồng hồ, không phải một instant gắn múi giờ. `timestamptz` biểu diễn thời điểm tuyệt đối. Ở các vùng có daylight saving time, bước **một ngày theo lịch địa phương** không phải lúc nào cũng là đúng **24 giờ tuyệt đối**.

Khi ứng dụng cần khung ngày theo vùng địa lý như `Europe/Berlin`, hãy xác định quy tắc lập lịch, vùng giờ IANA và cách chuyển đổi ranh giới ngày. Đừng mặc định mọi interval 1 day có cùng ý nghĩa với interval 24 hours trong mọi ngữ cảnh.

### Không sinh dãy quá lớn từ input chưa kiểm soát

`generate_series(1, 1000000000)` có thể tạo lượng hàng rất lớn. Với input từ API, nên kiểm tra start/stop/step, số phần tử dự kiến và giới hạn tài nguyên trước khi sinh.

Một cách kiểm soát trong ví dụ lab:

```sql
WITH request_params AS (
    SELECT
        1::integer AS start_value,
        100::integer AS stop_value
)
SELECT g.n
FROM request_params AS p
CROSS JOIN LATERAL generate_series(
    p.start_value,
    LEAST(p.stop_value, p.start_value + 99)
) AS g(n)
ORDER BY g.n;
```

Đây chỉ là minh họa giới hạn dãy cho **bước +1**; với step âm, số lớn, overflow hoặc đối số null cần validation riêng, không áp dụng máy móc công thức.

## 7. unnest(): biến mảng PostgreSQL thành nhiều hàng

Một mảng `text[]` có thể chứa nhiều nhãn. `unnest()` tạo một hàng cho từng phần tử:

```sql
SELECT t.tag
FROM unnest(ARRAY['java', 'postgresql', 'api']::text[])
     AS t(tag);
```

Kết quả gồm ba hàng, tương ứng ba nhãn. Khi input là mảng số:

```sql
SELECT n.value
FROM unnest(ARRAY[10, 20, 30]) AS n(value);
```

Cột `value` có kiểu `integer` trong ví dụ này, **không phải text**.

### unnest trên mảng rỗng

```sql
SELECT x.tag
FROM unnest(ARRAY[]::text[]) AS x(tag);
-- 0 hàng
```

### unnest trên NULL array

```sql
SELECT x.tag
FROM unnest(NULL::text[]) AS x(tag);
-- 0 hàng
```

Phân biệt:

- `ARRAY[]::text[]`: một **mảng có 0 phần tử**.
- `NULL::text[]`: không có giá trị mảng.
- `ARRAY[NULL::text]`: **một mảng có 1 phần tử null**.

Với trường hợp cuối:

```sql
SELECT x.tag
FROM unnest(ARRAY[NULL::text]) AS x(tag);
-- 1 hàng, giá trị tag = SQL NULL
```

Đây là sự khác biệt quan trọng khi kết hợp với `LEFT JOIN` hoặc `COUNT(*)`.

## 8. WITH ORDINALITY: giữ vị trí của phần tử

`unnest` tạo một nguồn hàng, nhưng đôi khi bạn cần biết **phần tử thứ mấy của mảng gốc**. Cú pháp `WITH ORDINALITY` bổ sung một cột số thứ tự bắt đầu từ **1**.

```sql
SELECT
    x.position,
    x.tag
FROM unnest(ARRAY['java', 'postgresql', 'api']::text[])
     WITH ORDINALITY AS x(tag, position)
ORDER BY x.position;
```

Kết quả:

| position | tag |
|---:|---|
| 1 | java |
| 2 | postgresql |
| 3 | api |

### Vì sao còn cần ORDER BY position?

`WITH ORDINALITY` gắn số thứ tự cho **những hàng hàm tạo ra**. Nhưng sau `JOIN`, `WHERE`, `GROUP BY` và các thao tác của planner, **thứ tự hàng đầu ra cuối cùng không tự được bảo đảm**. Nếu cần hiển thị theo đúng trình tự, thêm:

```sql
ORDER BY x.position
```

### Áp dụng trên nhiều dự án

```sql
SELECT
    p.project_id,
    p.project_name,
    tag.position,
    tag.value AS tag_name
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS tag(value, position)
ORDER BY p.project_id, tag.position;
```

Với dự án Alpha sẽ có ba hàng tương ứng thứ tự nhãn. Beta có hai hàng. **Gamma không có hàng** vì `tags` là mảng rỗng; phần sau sẽ giải thích cách giữ Gamma.

### Ordinality không phải khóa nghiệp vụ

Nếu bạn sửa mảng, chèn phần tử ở vị trí đầu hoặc đổi thứ tự, các giá trị ordinality cũng thay đổi. Dùng `WITH ORDINALITY` để phản ánh **vị trí trong kết quả SRF**, không tự xem nó là ID ổn định của một thực thể.

## 9. generate_subscripts(): lấy chỉ số mảng

Khi muốn truy cập chỉ số thật của một chiều mảng, PostgreSQL có `generate_subscripts(array, dimension)`.

```sql
SELECT
    s.idx,
    p.tags[s.idx] AS tag_name
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL generate_subscripts(p.tags, 1) AS s(idx)
WHERE p.project_id = 1
ORDER BY s.idx;
```

Với mảng một chiều trong ví dụ, chỉ số là 1, 2, 3. Cách này hữu ích khi cần thao tác bằng cú pháp `array[index]`.

### generate_subscripts và WITH ORDINALITY không luôn là một

`WITH ORDINALITY` đánh số **hàng được hàm tạo ra**, bắt đầu từ 1. `generate_subscripts()` trả **chỉ số hợp lệ của mảng trên chiều được chọn**.

PostgreSQL có thể lưu mảng với **lower bound không phải 1**. Khi đó, chỉ số mảng và ordinality khác nhau.

Ví dụ:

```sql
SELECT
    array_lower('[0:2]={10,20,30}'::integer[], 1)
        AS array_first_index;
-- 0

SELECT idx
FROM generate_subscripts(
    '[0:2]={10,20,30}'::integer[],
    1
) AS s(idx)
ORDER BY idx;
-- 0, 1, 2
```

Nếu dùng `unnest(... ) WITH ORDINALITY` cho chính mảng trên, ordinality sẽ là **1, 2, 3**. Đừng nhầm chỉ số trong mảng với thứ tự hàng khi cần bảo toàn địa chỉ phần tử.

## 10. LATERAL: SRF nhìn thấy cột của nguồn đứng trước

Một trong những khả năng mạnh nhất của SRF trong `FROM` là **đối số hàm có thể phụ thuộc vào cột của nguồn khác trong cùng `FROM`**.

Ví dụ:

```sql
SELECT
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
ORDER BY p.project_id, t.tag;
```

`unnest(p.tags)` dùng **mảng của từng hàng `p`**. Về mặt tư duy:

```text
projects
   ├── Alpha, tags=[java, postgresql, api]
   │       └── unnest → 3 hàng
   ├── Beta, tags=[frontend, api]
   │       └── unnest → 2 hàng
   └── Gamma, tags=[]
           └── unnest → 0 hàng

CROSS JOIN LATERAL → 5 hàng kết quả
```

**`LATERAL`** nói rằng biểu thức bên phải được phép tham chiếu những cột của nguồn bên trái hợp lệ trong ngữ cảnh ấy.

### Với table functions, LATERAL thường là tùy chọn

PostgreSQL cho phép **đối số của hàm trong `FROM`** tham chiếu nguồn đứng trước theo cơ chế lateral, ngay cả khi không viết từ khóa `LATERAL`:

```sql
SELECT p.project_id, t.tag
FROM lesson_srf.projects AS p
CROSS JOIN unnest(p.tags) AS t(tag)
ORDER BY p.project_id, t.tag;
```

Ở đây, `unnest(p.tags)` vẫn sử dụng `p.tags` từng hàng. Dù `LATERAL` thường là tùy chọn đối với *table function*, **viết tường minh** có thể làm ý định rõ ràng và nhất quán với truy vấn con lateral.

## 11. CROSS JOIN LATERAL khác LEFT JOIN LATERAL

Sự khác biệt đặc biệt quan trọng khi SRF trả **0 hàng**.

### CROSS JOIN LATERAL: không có phần tử thì mất hàng cha

```sql
SELECT
    p.project_id,
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
ORDER BY p.project_id, t.tag;
```

Gamma có `tags = ARRAY[]::text[]` nên `unnest` trả **0 hàng**. Với `CROSS JOIN`, dự án Gamma **không xuất hiện** trong kết quả.

Đây có thể là điều mong muốn nếu yêu cầu là “liệt kê **mọi tag thực sự có**”.

### LEFT JOIN LATERAL: giữ hàng cha

```sql
SELECT
    p.project_id,
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
ORDER BY p.project_id, t.tag NULLS LAST;
```

Gamma được giữ lại với `t.tag = NULL`. Đây là **hàng null-extended** do `LEFT JOIN` tạo khi không có kết quả phù hợp từ hàm.

### So sánh nhanh

| Điều kiện | `CROSS JOIN LATERAL` | `LEFT JOIN LATERAL ... ON TRUE` |
|---|---|---|
| SRF trả 3 hàng | 3 kết quả cho hàng cha | 3 kết quả cho hàng cha |
| SRF trả 1 hàng | 1 kết quả | 1 kết quả |
| SRF trả 0 hàng | **Không còn hàng cha** | **Một hàng cha**, cột SRF bằng `NULL` |
| Mục tiêu phù hợp | Trải phẳng tất cả phần tử thật. | Báo cáo giữ tất cả entity kể cả không có phần tử. |

**Quy tắc thiết kế:** Nếu nghiệp vụ hỏi “mọi dự án và các nhãn nếu có”, ưu tiên `LEFT JOIN LATERAL`. Nếu hỏi “mọi nhãn hiện có của các dự án”, `CROSS JOIN LATERAL` thường phù hợp.

## 12. ON TRUE có tác dụng gì?

Trong:

```sql
LEFT JOIN LATERAL unnest(p.tags) AS t(tag) ON TRUE
```

`ON TRUE` nghĩa là **không thêm điều kiện join ngoài việc hàm đã được gọi với tham số của hàng cha**. Nếu SRF trả bất kỳ hàng nào, tất cả các hàng đó đều phù hợp với `ON TRUE`. Nếu SRF trả 0 hàng, `LEFT JOIN` vẫn giữ hàng cha.

Bạn có thể thêm điều kiện nếu cần:

```sql
SELECT
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON t.tag LIKE 'a%'
ORDER BY p.project_id, t.tag;
```

Điều kiện trong `ON` chỉ cho các nhãn bắt đầu bằng `a` ghép vào. Dự án không có nhãn phù hợp vẫn được giữ với cột nhãn `NULL`.

Nếu thay bằng:

```sql
SELECT
    p.project_name,
    t.tag
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
WHERE t.tag LIKE 'a%';
```

thì `WHERE` loại những hàng có `t.tag = NULL` vì điều kiện trả unknown, làm **dự án không có nhãn phù hợp biến mất**. Đây là cùng một quy tắc quan trọng của `LEFT JOIN` thông thường.

## 13. COUNT(*) khi LEFT JOIN một SRF trả 0 hàng

Giả sử muốn đếm số nhãn của từng dự án:

```sql
SELECT
    p.project_id,
    COUNT(*) AS row_count,
    COUNT(t.tag) AS nonnull_tag_count
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
GROUP BY p.project_id
ORDER BY p.project_id;
```

Với Gamma, `LEFT JOIN` giữ **một hàng null-extended**:

```text
project_id = 3, t.tag = NULL
```

Vì thế:

- `COUNT(*)` = **1**.
- `COUNT(t.tag)` = **0**.

Nếu `tags` được phép chứa **phần tử null thật**, `COUNT(t.tag)` cũng không đếm những phần tử ấy. Khi cần đếm **số phần tử kể cả null**, dùng `WITH ORDINALITY` và đếm cột vị trí:

```sql
SELECT
    p.project_id,
    COUNT(t.position) AS array_element_count
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS t(tag, position)
  ON TRUE
GROUP BY p.project_id
ORDER BY p.project_id;
```

`position` không null đối với một hàng thật của `unnest`, nhưng null ở hàng mở rộng bởi `LEFT JOIN`. Do đó `COUNT(t.position)` phản ánh đúng **số phần tử của mảng** trong trường hợp này.

Với mảng một chiều thông thường, `cardinality(p.tags)` còn là lựa chọn trực tiếp hơn khi chỉ cần số phần tử mà **không cần trải phẳng**:

```sql
SELECT
    project_id,
    cardinality(tags) AS tag_count
FROM lesson_srf.projects
ORDER BY project_id;
```

## 14. LATERAL subquery: cùng ý tưởng, không nhất thiết là hàm

`LATERAL` cũng áp dụng cho **truy vấn con trong `FROM`** khi truy vấn con cần tham chiếu nguồn bên trái.

Ví dụ lấy **hai task mới nhất của mỗi dự án**:

```sql
SELECT
    p.project_id,
    p.project_name,
    recent.task_id,
    recent.task_title,
    recent.created_at
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL (
    SELECT
        t.task_id,
        t.task_title,
        t.created_at
    FROM lesson_srf.tasks AS t
    WHERE t.project_id = p.project_id
    ORDER BY t.created_at DESC, t.task_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY p.project_id, recent.created_at DESC NULLS LAST,
         recent.task_id DESC;
```

Trong dữ liệu mẫu:

- Alpha nhận task 13 và 12.
- Beta nhận task 21.
- Gamma **vẫn có một hàng** với cột `recent.* = NULL`.

Nếu dùng `CROSS JOIN LATERAL`, Gamma sẽ biến mất.

### Derived subquery thông thường không được nhìn nguồn bên trái

Ví dụ sai:

```sql
-- Sai: thiếu LATERAL đối với derived subquery
-- muốn tham chiếu p.project_id.
SELECT p.project_id, recent.task_id
FROM lesson_srf.projects AS p
LEFT JOIN (
    SELECT task_id
    FROM lesson_srf.tasks AS t
    WHERE t.project_id = p.project_id
) AS recent ON TRUE;
```

PostgreSQL không cho phép một derived subquery trong `FROM` tham chiếu nguồn đứng trước như trên khi thiếu `LATERAL` thích hợp.

**Phân biệt:** Với **function call** trong `FROM`, tham chiếu nguồn bên trái trong đối số thường được cho phép dù không viết `LATERAL`; với **subquery** cần tham chiếu bên trái, viết `LATERAL`.

## 15. SRF và LATERAL không phải vòng lặp thủ công của Java

Cách hình dung “mỗi dự án gọi `unnest(p.tags)`” rất hữu ích để hiểu ngữ nghĩa:

```text
for each project p:
    for each tag in p.tags:
        emit (p.project_id, tag)
```

Nhưng đây chỉ là **mô hình logic**. PostgreSQL optimizer có thể chọn cách tổ chức execution phù hợp với dependency, join, filter và kế hoạch truy vấn. Không nên suy đoán số lần gọi thực tế hoặc thứ tự chạy vật lý chỉ từ cách diễn đạt vòng lặp.

Đối với hàm có **side effect** hoặc phụ thuộc trạng thái, cần xem **volatility** và ngữ nghĩa của hàm. Hàm dùng trong truy vấn SQL không nên dựa vào việc được gọi đúng một lần trên mỗi hàng theo một thứ tự không được bảo đảm.

## 16. unnest nhiều mảng: ghép theo vị trí, không phải nhân Descartes

PostgreSQL hỗ trợ biến thể `unnest` nhận nhiều mảng trong `FROM`:

```sql
SELECT
    x.id,
    x.label
FROM unnest(
    ARRAY[10, 20, 30]::integer[],
    ARRAY['A', 'B', 'C']::text[]
) AS x(id, label);
```

Kết quả:

| id | label |
|---:|---|
| 10 | A |
| 20 | B |
| 30 | C |

Các phần tử được **ghép theo vị trí**, không phải mỗi ID ghép với mọi label.

### Mảng có độ dài khác nhau

```sql
SELECT x.id, x.label
FROM unnest(
    ARRAY[10, 20, 30]::integer[],
    ARRAY['A', 'B']::text[]
) AS x(id, label);
```

Kết quả:

| id | label |
|---:|---|
| 10 | A |
| 20 | B |
| 30 | NULL |

Khi các mảng không cùng độ dài, PostgreSQL có thể **đệm SQL NULL** cho mảng ngắn hơn theo cú pháp multi-argument `unnest`.

Nếu ứng dụng yêu cầu ghép một-một nghiêm ngặt, hãy **kiểm tra độ dài mảng đầu vào** thay vì âm thầm cho phép dữ liệu bị đệm null.

### Khác với CROSS JOIN hai lần unnest

```sql
SELECT ids.id, names.label
FROM unnest(ARRAY[10, 20, 30]::integer[]) AS ids(id)
CROSS JOIN unnest(ARRAY['A', 'B']::text[]) AS names(label);
```

Truy vấn này trả **3 × 2 = 6 hàng** do `CROSS JOIN` hai tập độc lập. Nó **không** ghép cùng vị trí. Cần chọn đúng cú pháp theo mục tiêu: **zip theo vị trí** hay **mọi tổ hợp**.

## 17. ROWS FROM: gom nhiều table functions song song

PostgreSQL có cú pháp **`ROWS FROM (...)`** để kết hợp đầu ra nhiều table functions thành các cột của một nguồn.

```sql
SELECT
    r.number,
    r.label,
    r.position
FROM ROWS FROM (
    generate_series(1, 3),
    unnest(ARRAY['A', 'B']::text[])
) WITH ORDINALITY AS r(number, label, position)
ORDER BY r.position;
```

Kết quả:

| number | label | position |
|---:|---|---:|
| 1 | A | 1 |
| 2 | B | 2 |
| 3 | NULL | 3 |

Các hàm được kết hợp **song song theo hàng kết quả**; nguồn ngắn hơn được đệm null tới số hàng của hàm dài nhất.

### ROWS FROM khác CROSS JOIN

```text
generate_series → 1, 2, 3
unnest           → A, B

ROWS FROM:
1-A
2-B
3-NULL

CROSS JOIN:
1-A
1-B
2-A
2-B
3-A
3-B
```

Đây là hai phép biến đổi dữ liệu khác hẳn. `ROWS FROM` hữu ích khi các hàm trả các chuỗi tương ứng theo vị trí; nếu cần join bằng một khóa nghiệp vụ, tốt hơn dùng điều kiện `JOIN ... ON` rõ ràng.

## 18. JSONB array thành nhiều hàng

JSON là nguồn dữ liệu phổ biến của API. PostgreSQL hỗ trợ **`jsonb_array_elements()`** để trải phẳng một JSON array thành các giá trị JSONB:

```sql
SELECT e.element
FROM jsonb_array_elements(
    '["java", "postgresql", "api"]'::jsonb
) AS e(element);
```

Kết quả là ba hàng, mỗi hàng chứa một giá trị **`jsonb`** là JSON string.

Nếu muốn trực tiếp lấy **text**:

```sql
SELECT e.tag
FROM jsonb_array_elements_text(
    '["java", "postgresql", "api"]'::jsonb
) AS e(tag);
```

`jsonb_array_elements_text` phù hợp khi phần tử là chuỗi và bạn muốn biểu thức text trong SQL.

### Dữ liệu JSON có cấu trúc khác nhau

| Input JSONB | `jsonb_array_elements` |
|---|---|
| `'["a","b"]'::jsonb` | Hai hàng JSONB string. |
| `'[]'::jsonb` | 0 hàng. |
| `NULL::jsonb` | 0 hàng trong lời gọi hàm thông thường. |
| `'[null]'::jsonb` | Một hàng chứa **JSON null**. |
| `'{"a":1}'::jsonb` | Lỗi: input không phải array. |
| `'null'::jsonb` | Lỗi vì đây là giá trị JSON scalar null, không phải SQL NULL/array. |

**SQL `NULL` và JSON `null` khác nhau.** Một giá trị `jsonb` có nội dung JSON null vẫn là **một JSON scalar**, không phải một mảng rỗng.

### Với JSON array từ bảng projects

```sql
SELECT
    p.project_id,
    e.member
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL jsonb_array_elements(p.members)
     AS e(member)
ORDER BY p.project_id;
```

Alpha cho hai object; Beta không có hàng vì `members = []`; Gamma cho một object.

## 19. WITH ORDINALITY cho JSON array

Khi thứ tự phần tử JSON array có ý nghĩa, dùng:

```sql
SELECT
    p.project_id,
    e.position,
    e.member ->> 'name' AS member_name,
    e.member ->> 'role' AS member_role
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL jsonb_array_elements(p.members)
     WITH ORDINALITY AS e(member, position)
  ON TRUE
ORDER BY p.project_id, e.position NULLS LAST;
```

Giải thích:

- `jsonb_array_elements` tạo từng JSON object thành một hàng.
- `WITH ORDINALITY` bổ sung **`position` bắt đầu từ 1** trong mỗi lần mở mảng.
- `->> 'name'` và `->> 'role'` lấy thuộc tính dưới dạng text.
- `LEFT JOIN LATERAL` giữ cả Beta khi mảng members rỗng.

Kết quả khái niệm:

| project_id | position | member_name | member_role |
|---:|---:|---|---|
| 1 | 1 | An | developer |
| 1 | 2 | Bình | reviewer |
| 2 | NULL | NULL | NULL |
| 3 | 1 | Chi | lead |

Nếu mục tiêu là **chỉ các thành viên thật**, dùng `CROSS JOIN LATERAL` thay vì `LEFT JOIN`.

### JSON string, SQL text và JSON object

`jsonb_array_elements` trả `jsonb`. `->` trích giá trị vẫn dưới dạng JSONB; `->>` trả dạng text:

```sql
SELECT
    e.member -> 'name' AS as_jsonb,
    e.member ->> 'name' AS as_text
FROM jsonb_array_elements(
    '[{"name":"An"}]'::jsonb
) AS e(member);
```

Chọn `->>` khi cần so sánh chuỗi, hiển thị hoặc ánh xạ vào cột text. Với số liệu, cần chuyển kiểu và kiểm soát dữ liệu đầu vào.

## 20. jsonb_to_recordset: mở mảng object thành các cột có kiểu

`jsonb_array_elements()` trả một cột JSONB cho mỗi object. Khi muốn dùng nhiều thuộc tính như cột SQL có kiểu, `jsonb_to_recordset()` rất hữu ích.

```sql
SELECT
    m.name,
    m.role
FROM jsonb_to_recordset(
    '[
       {"name":"An","role":"developer"},
       {"name":"Bình","role":"reviewer"}
     ]'::jsonb
) AS m(name text, role text)
ORDER BY m.name;
```

Cú pháp `AS m(name text, role text)` định nghĩa cột:

- `m.name` kiểu `text`.
- `m.role` kiểu `text`.

### Dùng trên từng hàng projects

```sql
SELECT
    p.project_id,
    p.project_name,
    m.name AS member_name,
    m.role AS member_role
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL jsonb_to_recordset(p.members)
     AS m(name text, role text)
  ON TRUE
ORDER BY p.project_id, m.name NULLS LAST;
```

Với Beta có mảng rỗng, hai cột member nhận `NULL` trong hàng được giữ bởi `LEFT JOIN`.

### Khóa bị thiếu và kiểu không hợp lệ

Nếu một object không có key `role`, cột `role` có thể thành SQL `NULL`. Nếu bạn khai báo một trường là `integer` nhưng JSON chứa chuỗi không chuyển được sang integer, PostgreSQL có thể **báo lỗi chuyển kiểu**.

Ví dụ đọc `age`:

```sql
SELECT x.name, x.age
FROM jsonb_to_recordset(
    '[
       {"name":"An","age":25},
       {"name":"Bình","age":31}
     ]'::jsonb
) AS x(name text, age integer);
```

Các cột được trích theo tên key mà bạn khai báo; nếu schema JSON dùng key `fullName` nhưng bạn khai báo `name`, đừng kỳ vọng PostgreSQL tự suy ra rằng đó là cùng ý nghĩa.

### Lưu ý input không phải array of objects

`jsonb_to_recordset` được thiết kế cho **mảng JSON gồm các object**. Nếu input là JSON object đơn, số scalar hoặc mảng chứa cấu trúc không phù hợp, hàm có thể lỗi. Hãy validate cấu trúc JSON ở ranh giới ứng dụng/database.

## 21. Bảo vệ truy vấn khi JSONB có thể sai kiểu

Schema lab đã có:

```sql
CHECK (jsonb_typeof(members) = 'array')
```

Ràng buộc đó cùng `NOT NULL` giúp `projects.members` luôn là JSON array theo dữ liệu được chấp nhận. Nhưng với dữ liệu JSON bên ngoài không được kiểm soát, bạn nên kiểm tra kiểu trước khi gọi SRF cần array.

Một mẫu fallback:

```sql
SELECT
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(
                '{"name":"An"}'::jsonb
            ) = 'array'
            THEN '{"name":"An"}'::jsonb
            ELSE '[]'::jsonb
        END
    ) AS element;
-- 0 hàng
```

Trong thực tế, giá trị JSON nên được lấy từ cột/parameter thay cho literal ví dụ. `CASE` ở đây đảm bảo hàm nhận **JSON array** kể cả khi input là object/scalar.

Không nên biến mọi dữ liệu sai định dạng thành mảng rỗng một cách âm thầm. Tùy hợp đồng, ứng dụng có thể cần **từ chối input, ghi lỗi validation** thay vì giả vờ không có phần tử.

## 22. jsonb_each và jsonb_each_text: mở JSON object

Array và object có hình dạng khác nhau. Muốn tạo hàng từ các **cặp key/value của JSON object**, dùng `jsonb_each()`:

```sql
SELECT
    e.key,
    e.value
FROM jsonb_each(
    '{"db":"postgresql","language":"java"}'::jsonb
) AS e(key, value)
ORDER BY e.key;
```

Kết quả gồm hai hàng. `value` là kiểu `jsonb`.

Nếu muốn value dạng text:

```sql
SELECT
    e.key,
    e.value
FROM jsonb_each_text(
    '{"db":"postgresql","language":"java"}'::jsonb
) AS e(key, value)
ORDER BY e.key;
```

### Thứ tự key của JSON object không phải thứ tự nghiệp vụ

JSON object không nên được xem như một danh sách có thứ tự như JSON array. Khi cần trình bày ổn định theo key:

```sql
ORDER BY e.key
```

Nếu cần giữ thứ tự người dùng nhập từng mục, thiết kế một **JSON array các object có vị trí** hoặc một bảng quan hệ có cột `sort_order`, thay vì dựa vào thứ tự key JSONB.

### Cần phân biệt đầu vào

- `jsonb_array_elements`: nhận **array**, tạo từng phần tử.
- `jsonb_to_recordset`: nhận **array of objects**, tạo cột có kiểu.
- `jsonb_each`: nhận **object**, tạo hàng `key/value`.

Chọn sai hàm theo hình dạng input thường dẫn đến lỗi hoặc kết quả không như mong muốn.

## 23. regexp_split_to_table và string_to_table: tách chuỗi thành hàng

Không phải nguồn dữ liệu nhiều phần tử nào cũng là mảng/JSON. Khi nhận chuỗi có dấu phân cách, PostgreSQL có các hàm tách thành **nhiều hàng**.

### string_to_table

Ở các phiên bản PostgreSQL hỗ trợ hàm này:

```sql
SELECT t.token
FROM string_to_table('java,postgresql,api', ',')
     AS t(token);
```

Kết quả:

```text
java
postgresql
api
```

`string_to_table` tách theo **chuỗi delimiter**, không phải regex. Hàm có biến thể xử lý token null tùy chữ ký được hỗ trợ.

### regexp_split_to_table

Nếu dấu phân cách là một **mẫu regex**, dùng:

```sql
SELECT t.token
FROM regexp_split_to_table(
    'java ; postgresql, api',
    '\s*[,;]\s*'
) AS t(token);
```

Biểu thức chính quy có ý nghĩa: dấu phẩy hoặc chấm phẩy, có thể kèm khoảng trắng hai bên.

### Đừng coi chuỗi phân tách là mô hình danh sách lý tưởng

Nếu một giá trị thực chứa dấu phân cách (ví dụ tên sản phẩm `"A, B"`), tách chuỗi đơn giản có thể làm mất cấu trúc. Với dữ liệu đã có mảng/JSON, ưu tiên **`unnest`/`jsonb_array_elements`** thay vì đổi về chuỗi rồi tách lại.

`regexp_split_to_table` hữu ích cho dữ liệu đầu vào thô có format xác định, nhưng không tự thay thế một parser CSV hoặc một chuẩn dữ liệu có escaping đầy đủ.

## 24. Viết hàm trả tập của riêng mình bằng SQL

PostgreSQL cho phép tạo hàm SQL với `RETURNS SETOF <type>` hoặc `RETURNS TABLE(...)`.

### 24.1. RETURNS TABLE: nhiều cột có tên

Ví dụ hàm lấy các task gần nhất của một dự án:

```sql
CREATE FUNCTION lesson_srf.recent_tasks(
    p_project_id BIGINT,
    p_limit INTEGER DEFAULT 2
)
RETURNS TABLE (
    task_id BIGINT,
    task_title TEXT,
    created_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        t.task_id,
        t.task_title,
        t.created_at
    FROM lesson_srf.tasks AS t
    WHERE t.project_id = p_project_id
    ORDER BY t.created_at DESC, t.task_id DESC
    LIMIT p_limit
$$;
```

Giải thích:

- `p_project_id`: tham số dự án cần lọc.
- `p_limit`: số task tối đa; mặc định 2 trong ví dụ.
- `RETURNS TABLE` mô tả ba cột và kiểu trả về.
- `LANGUAGE sql`: nội dung là truy vấn SQL.
- `STABLE`: thể hiện hàm đọc dữ liệu và được kỳ vọng cho kết quả nhất quán theo quy tắc snapshot/stability của PostgreSQL trong phạm vi statement, không giả định dữ liệu không bao giờ thay đổi.
- `ORDER BY ... LIMIT ...`: xác định những task mới nhất.

Gọi trực tiếp trong `FROM`:

```sql
SELECT r.task_id, r.task_title, r.created_at
FROM lesson_srf.recent_tasks(1, 2) AS r
ORDER BY r.created_at DESC, r.task_id DESC;
```

### Mục đích ORDER BY ở hàm và truy vấn ngoài

`ORDER BY ... LIMIT` trong hàm chọn **top N task** phù hợp. Để hiển thị những hàng kết quả cuối theo thứ tự yêu cầu, câu truy vấn ngoài vẫn nên có **`ORDER BY` của chính nó**. Không dựa vào việc đầu ra của table function luôn được giữ nguyên thứ tự qua mọi phép join/filter.

### Sử dụng hàm trong LEFT JOIN LATERAL

```sql
SELECT
    p.project_id,
    p.project_name,
    r.task_id,
    r.task_title
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL lesson_srf.recent_tasks(p.project_id, 2)
     AS r
  ON TRUE
ORDER BY p.project_id, r.created_at DESC NULLS LAST,
         r.task_id DESC;
```

Alpha cho hai task mới nhất; Beta cho một; Gamma vẫn xuất hiện với `r.task_id IS NULL`. Đây là ví dụ kết hợp **hàm do người dùng định nghĩa** và `LATERAL` giống các SRF built-in.

### Hàm nhận giới hạn cần được kiểm soát

Trong ứng dụng thực tế, không nên để client truyền `p_limit` tùy ý hoặc âm mà không validate. Có thể thêm quy tắc giới hạn trong ứng dụng hoặc trong hàm, và quyết định ý nghĩa của input null/0/âm. `LIMIT NULL` và `LIMIT 0` không mang cùng ý nghĩa.

## 25. RETURNS SETOF: trả nhiều giá trị của một kiểu

Nếu hàm chỉ trả một cột `text`, `RETURNS SETOF text` có thể đơn giản hơn `RETURNS TABLE(tag text)`.

```sql
CREATE FUNCTION lesson_srf.project_tags(
    p_project_id BIGINT
)
RETURNS SETOF TEXT
LANGUAGE sql
STABLE
AS $$
    SELECT x.tag
    FROM lesson_srf.projects AS p
    CROSS JOIN LATERAL unnest(p.tags) AS x(tag)
    WHERE p.project_id = p_project_id
$$;
```

Gọi:

```sql
SELECT tag.value
FROM lesson_srf.project_tags(1) AS tag(value);
```

Kết quả có ba hàng: java, postgresql, api. Với dự án Gamma:

```sql
SELECT tag.value
FROM lesson_srf.project_tags(3) AS tag(value);
-- 0 hàng
```

Hàm trả `SETOF` **không có nghĩa chỉ trả một mảng**. Nó trả **nhiều hàng** kiểu text. Nếu muốn một mảng, có thể dùng aggregate:

```sql
SELECT COALESCE(
    array_agg(tag.value ORDER BY tag.value),
    ARRAY[]::text[]
) AS tags
FROM lesson_srf.project_tags(1) AS tag(value);
```

### RETURNS SETOF composite type

Hàm có thể khai báo `RETURNS SETOF lesson_srf.tasks`, nghĩa là mỗi hàng có cấu trúc tương ứng một composite row type của bảng `tasks`. Điều này tiện trong một số ngữ cảnh, nhưng đồng thời có thể làm API của hàm phụ thuộc cấu trúc bảng. Với interface rõ và ổn định, `RETURNS TABLE(...)` thường dễ kiểm soát tập cột xuất ra hơn.

## 26. PL/pgSQL với RETURN QUERY

Với logic cần câu lệnh điều khiển, điều kiện hoặc nhiều bước, PostgreSQL cho phép hàm `LANGUAGE plpgsql` trả tập bằng `RETURN QUERY`.

Ví dụ:

```sql
CREATE FUNCTION lesson_srf.tasks_by_status(
    p_status TEXT
)
RETURNS TABLE (
    task_id BIGINT,
    task_title TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.task_id,
        t.task_title
    FROM lesson_srf.tasks AS t
    WHERE t.status = p_status
    ORDER BY t.task_id;
END;
$$;
```

Gọi:

```sql
SELECT s.task_id, s.task_title
FROM lesson_srf.tasks_by_status('DOING') AS s
ORDER BY s.task_id;
```

Kết quả dự kiến: task 12 và 21.

### RETURN QUERY khác RETURN NEXT

- **`RETURN QUERY SELECT ...`** thêm nhiều hàng từ kết quả một truy vấn.
- **`RETURN NEXT ...`** thêm một hàng mỗi lần gọi trong hàm `RETURNS SETOF` thích hợp.
- **`RETURN;`** kết thúc thực thi hàm.

`RETURN QUERY` không phải lệnh `COMMIT` hay `ROLLBACK`. Các hàng do hàm tạo ra vẫn thuộc câu truy vấn và transaction của lời gọi.

### Lưu ý bộ nhớ với hàm PL/pgSQL trả nhiều hàng

Một số cách triển khai hàm PL/pgSQL trả tập có thể **tích lũy kết quả trước khi trả** ở mức executor/tuplestore, tùy phiên bản và kế hoạch, thay vì streaming vô hạn với bộ nhớ cố định. Đừng viết hàm trả hàng triệu hàng chỉ vì nghĩ `RETURN NEXT` luôn có chi phí O(1) cho toàn hàm.

## 27. Hàm trả record không có cấu trúc cố định

Trong PostgreSQL, một hàm khai báo `RETURNS SETOF record` có thể cần **định nghĩa cột** tại vị trí gọi nếu thông tin cấu trúc chưa được xác định qua kiểu có tên hoặc thông số output.

Ví dụ khái niệm:

```sql
-- Giả sử có hàm trả SETOF record với hai trường.
SELECT r.id, r.label
FROM some_record_function(...)
     AS r(id bigint, label text);
```

Ví dụ trên chỉ minh họa cách gọi; hàm `some_record_function` chưa được tạo trong bài.

Trong khi đó, với hàm `RETURNS TABLE(task_id bigint, task_title text)`, tên và kiểu các cột **đã được khai báo khi tạo hàm**, nên thường chỉ cần:

```sql
SELECT x.task_id, x.task_title
FROM lesson_srf.tasks_by_status('DOING') AS x;
```

Không tự thêm danh sách kiểu sau alias cho một hàm đã có output signature theo cách mâu thuẫn; đọc signature thực tế của hàm trước khi viết câu gọi.

## 28. ROWS và COST: giúp planner ước lượng SRF tự định nghĩa

Khi PostgreSQL lập kế hoạch truy vấn, nó cần **ước lượng hàm trả bao nhiêu hàng** và **chi phí gọi hàm**. Với hàm do người dùng định nghĩa, người tạo có thể cung cấp một số metadata:

- **`ROWS n`**: ước lượng số hàng mà một lời gọi SRF trả về.
- **`COST n`**: ước lượng chi phí thực thi tương đối, phụ thuộc ngôn ngữ/cách planner tính.

Ví dụ:

```sql
CREATE FUNCTION lesson_srf.small_numbers(
    p_max INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE sql
IMMUTABLE
ROWS 10
AS $$
    SELECT g.n
    FROM generate_series(1, p_max) AS g(n)
$$;
```

`ROWS 10` là **ước lượng**, không phải giới hạn cứng: nếu gọi `small_numbers(1000)`, hàm vẫn có thể trả 1.000 hàng. Hàm trong ví dụ trả kết quả chỉ từ đối số, nên `IMMUTABLE` phù hợp về mặt ý nghĩa.

### Khi ước lượng sai

Nếu planner tưởng hàm trả 10 hàng nhưng thực tế thường trả hàng triệu hàng, nó có thể chọn thứ tự join/phương pháp join không phù hợp, dẫn đến hiệu năng kém.

Với các SRF đắt tiền:

1. Ước lượng số hàng trung bình/thường gặp theo workload.
2. Cập nhật `ROWS`/`COST` khi có bằng chứng đo.
3. Quan sát `EXPLAIN (ANALYZE, BUFFERS)` để so sánh **estimated rows** và **actual rows**.
4. Cân nhắc biến truy vấn có thể inline thành SQL trực tiếp hoặc set-based operation nếu phù hợp.

Không xem `ROWS` là cơ chế an toàn chống trả quá nhiều dữ liệu. Giới hạn phải nằm trong **logic hàm/truy vấn và validation input**.

## 29. Volatility và PARALLEL SAFE: khai báo đúng tính chất

PostgreSQL hỗ trợ các mức volatility cho function:

| Thuộc tính | Ý nghĩa khái quát |
|---|---|
| **`IMMUTABLE`** | Với cùng đối số, kết quả được kỳ vọng không thay đổi và không phụ thuộc trạng thái database/timezone/thiết lập thay đổi được theo ngữ cảnh. |
| **`STABLE`** | Kết quả được kỳ vọng ổn định cho cùng đối số trong phạm vi một statement theo hợp đồng volatility, có thể đọc dữ liệu mà không thực hiện ghi side effect. |
| **`VOLATILE`** | Kết quả có thể thay đổi giữa các lần gọi hoặc có side effect; planner phải xử lý theo quy tắc của loại này. |

Hàm `lesson_srf.project_tags(p_project_id)` đọc bảng `projects` nên **không thể gọi là IMMUTABLE** chỉ vì bản thân chuỗi SQL ngắn. Nếu tags thay đổi sau commit, lời gọi ở thời điểm khác có thể cho tập phần tử khác.

### Độ an toàn chạy song song

Các hàm tùy chỉnh còn có đánh dấu **`PARALLEL SAFE`**, `PARALLEL RESTRICTED` hoặc `PARALLEL UNSAFE` theo đặc tính của chúng. Không nên đánh dấu mọi hàm SRF là `PARALLEL SAFE` chỉ để planner tăng tốc:

- Nếu hàm truy cập tài nguyên không an toàn cho parallel worker, side effects, session state hoặc đối tượng tạm, cần xem lại.
- Việc khai báo sai có thể dẫn đến lỗi hoặc hành vi không mong muốn trong parallel query.
- Với PL/pgSQL và code mở rộng, cần đánh giá các lời gọi bên trong trước khi gắn nhãn.

Những thuộc tính này thuộc **hợp đồng của hàm với optimizer/executor**, không phải nhãn trang trí.

## 30. Hiệu năng: SRF có thể nhân số hàng rất nhanh

Giả sử bảng `projects` có 10.000 hàng và mỗi dự án có trung bình 100 phần tử trong mảng tags:

```text
10.000 projects
       ×
100 tags mỗi project
       │
       ▼
~1.000.000 hàng sau CROSS JOIN LATERAL unnest(tags)
```

Nếu sau đó còn join với bảng tasks một-nhiều, số hàng có thể tăng tiếp theo quan hệ giữa các nguồn. Vì thế:

- **Lọc hàng cha trước** nếu chỉ quan tâm một nhóm dự án.
- Chỉ trải phẳng **cột cần thiết**.
- Không sinh dãy `generate_series` khổng lồ theo input người dùng.
- Tránh join đồng thời nhiều tập một-nhiều nếu chỉ cần tổng hợp mỗi tập.
- Đặt `LIMIT` đúng tầng: `LIMIT` ngoài thường chỉ giới hạn **hàng kết quả cuối**, không đảm bảo giảm công việc sinh toàn bộ tập bên trong.
- Sử dụng chỉ mục phù hợp khi gọi `LATERAL` truy vấn con để lấy top N theo khóa cha.

### Ví dụ index cho top-N tasks mỗi dự án

```sql
CREATE INDEX ix_tasks_project_recent
ON lesson_srf.tasks(
    project_id,
    created_at DESC,
    task_id DESC
);
```

Với truy vấn:

```sql
SELECT
    p.project_id,
    t.task_id,
    t.created_at
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL (
    SELECT task_id, created_at
    FROM lesson_srf.tasks
    WHERE project_id = p.project_id
    ORDER BY created_at DESC, task_id DESC
    LIMIT 2
) AS t ON TRUE;
```

Index có thể giúp lấy top-N theo mỗi `project_id` mà không phải quét/sắp tất cả tasks của dự án, tùy thống kê, số hàng và plan được chọn. Không phải mọi LATERAL query đều nhanh hơn window function; cần đo theo dữ liệu thực.

## 31. EXPLAIN: đọc kế hoạch khi dùng function trong FROM

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.project_id,
    t.tag
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags) AS t(tag)
WHERE p.project_id = 1;
```

Kế hoạch có thể xuất hiện các node như **Function Scan**, Nested Loop hoặc các node khác tùy cách PostgreSQL tối ưu. Điều cần quan sát:

1. **Actual rows** mà function trả.
2. **Rows estimated** có sát thực tế không.
3. **Loops** của những node thực thi hàm.
4. Thời gian thực thi, I/O buffer và số hàng bị lọc.
5. Có nguồn nào bị nhân số hàng ngoài dự kiến không.

`EXPLAIN ANALYZE` thực sự thực thi câu truy vấn; ví dụ trên chỉ dùng `SELECT` trong lab. Với SRF có side effect hoặc câu SQL ghi, phải đặc biệt thận trọng trước khi chạy `EXPLAIN ANALYZE`.

### So sánh với không trải phẳng

Nếu chỉ muốn biết một dự án **có tag `postgresql` hay không**, có thể không cần `unnest`:

```sql
SELECT
    p.project_id,
    'postgresql' = ANY(p.tags) AS has_postgresql
FROM lesson_srf.projects AS p
ORDER BY p.project_id;
```

Hoặc dùng toán tử mảng phù hợp:

```sql
SELECT p.project_id
FROM lesson_srf.projects AS p
WHERE p.tags @> ARRAY['postgresql']::text[];
```

Đối với một số truy vấn mảng, GiN index phù hợp có thể giúp tra cứu containment, trong khi trải phẳng toàn bộ rồi lọc không phải lúc nào hiệu quả. **Đừng dùng SRF chỉ vì có thể**; chọn thao tác đúng bài toán.

## 32. SRF trong SELECT list: vì sao nên thận trọng?

PostgreSQL có hỗ trợ những SRF trong danh sách `SELECT` ở các ngữ cảnh thích hợp:

```sql
SELECT generate_series(1, 3);
```

Nhưng cách này có những khác biệt so với hàm scalar:

- Số hàng kết quả có thể tăng.
- Với nhiều SRF cùng `SELECT`, ngữ nghĩa kết hợp phần tử phụ thuộc các quy tắc PostgreSQL hiện đại, không nên nhầm với mọi tích Descartes.
- SRF trong biểu thức phức tạp có các hạn chế, đặc biệt khi dùng trong vị trí như điều kiện `CASE`/`COALESCE`.
- Việc đọc execution plan và hiểu vị trí mở rộng hàng có thể khó hơn.

### Viết rõ bằng FROM

Thay:

```sql
SELECT generate_series(1, 3) AS n;
```

bằng:

```sql
SELECT s.n
FROM generate_series(1, 3) AS s(n);
```

Hai câu đơn giản này có ý nghĩa kết quả tương tự. Cách `FROM`:

- Làm rõ hàm là **nguồn hàng**, không phải scalar expression thông thường.
- Cho phép đặt alias và dùng `WITH ORDINALITY`.
- Dễ kết hợp `CROSS JOIN`/`LEFT JOIN LATERAL`.
- Làm rõ những nguồn nào có thể biến mất khi SRF trả 0 hàng.

### SRF không được đặt tùy tiện trong WHERE

Không nên viết:

```sql
-- Sai về vị trí set-returning function:
-- WHERE kỳ vọng biểu thức điều kiện boolean,
-- không phải một nguồn hàng từ generate_series.
SELECT p.project_id
FROM lesson_srf.projects AS p
WHERE generate_series(1, 3) > 1;
```

Nếu muốn lọc các giá trị do SRF tạo, đưa hàm vào `FROM` rồi sử dụng cột:

```sql
SELECT s.n
FROM generate_series(1, 3) AS s(n)
WHERE s.n > 1;
```

Kết quả là 2 và 3.

## 33. SRF kết hợp aggregate: trải phẳng rồi tổng hợp lại

Một tình huống phổ biến là **tách mảng thành hàng**, lọc, rồi **gom thành JSON array** theo dự án.

```sql
SELECT
    p.project_id,
    COALESCE(
        jsonb_agg(
            upper(t.tag)
            ORDER BY t.position
        ) FILTER (WHERE t.position IS NOT NULL),
        '[]'::jsonb
    ) AS upper_tags
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS t(tag, position)
  ON TRUE
GROUP BY p.project_id
ORDER BY p.project_id;
```

Ý nghĩa:

1. `unnest` tạo nhiều hàng từ từng mảng tags.
2. `WITH ORDINALITY` giữ vị trí phần tử.
3. `upper` biến đổi từng tag.
4. `jsonb_agg(... ORDER BY t.position)` gom thành array JSON theo thứ tự gốc.
5. `FILTER` loại hàng null-extended do `LEFT JOIN`.
6. `COALESCE` cho Gamma một JSON array rỗng `[]`.

### Vì sao không dùng aggregate(SRF(...)) trực tiếp?

Một lỗi thường gặp là viết:

```sql
-- Không nên: aggregate không nhận lời gọi SRF trực tiếp
-- ở vị trí đối số theo cách này.
SELECT array_agg(unnest(tags))
FROM lesson_srf.projects;
```

PostgreSQL có thể báo **`aggregate function calls cannot contain set-returning function calls`** và gợi ý dùng `LATERAL FROM`.

Cách đúng:

```sql
SELECT array_agg(t.tag ORDER BY p.project_id, t.position)
FROM lesson_srf.projects AS p
CROSS JOIN LATERAL unnest(p.tags)
     WITH ORDINALITY AS t(tag, position);
```

Chuyển SRF thành **nguồn hàng trong `FROM`**, sau đó aggregate nhận **cột của nguồn** như bình thường.

## 34. Dùng LATERAL để tránh lặp công việc trong truy vấn

Giả sử cần cả số lượng nhãn và danh sách nhãn cho từng dự án. Nếu chỉ cần thông tin từ một mảng, có thể lấy `cardinality(tags)` trực tiếp mà không trải phẳng:

```sql
SELECT
    p.project_id,
    cardinality(p.tags) AS tag_count,
    p.tags
FROM lesson_srf.projects AS p;
```

Khi cần xử lý từng tag (lọc, biến đổi, join), SRF có ý nghĩa. Nhưng nếu chỉ dùng:

```sql
SELECT
    p.project_id,
    COUNT(t.tag)
FROM lesson_srf.projects AS p
LEFT JOIN LATERAL unnest(p.tags) AS t(tag)
  ON TRUE
GROUP BY p.project_id;
```

thì bạn đã tạo thêm hàng chỉ để đếm, và `COUNT(t.tag)` còn không tính phần tử null thật. Đừng coi trải phẳng là lựa chọn mặc định; **hàm trên mảng gốc** có thể đơn giản và hiệu quả hơn.

Một ví dụ cần LATERAL thật sự là khi phải **lấy các phần tử theo điều kiện rồi join với bảng lookup**. Khi đó, dùng `unnest` có vị trí, khóa liên kết và lọc phù hợp.

## 35. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Dự án có mảng rỗng biến mất | `CROSS JOIN LATERAL` với SRF trả 0 hàng. | Nếu phải giữ dự án, dùng `LEFT JOIN LATERAL ... ON TRUE`. |
| Đếm 1 thay vì 0 với mảng rỗng | `COUNT(*)` đếm hàng null-extended của outer join. | Dùng `COUNT(position)` từ `WITH ORDINALITY` hoặc `cardinality(tags)`. |
| Các phần tử sau join không đúng thứ tự | Không có `ORDER BY` cuối truy vấn. | Dùng `WITH ORDINALITY` và `ORDER BY position`. |
| Một JSON value gây lỗi “cannot extract elements” | Input không phải JSON array đúng kiểu. | Validate `jsonb_typeof`/schema, hoặc xử lý lỗi input. |
| Cột `record` không tồn tại/không có kiểu | Chưa khai báo output columns của recordset. | Thêm `AS x(name text, age integer)` theo signature. |
| Lỗi tham chiếu cột nguồn trong derived table | Thiếu `LATERAL` cho truy vấn con trong `FROM`. | Dùng `LEFT/CROSS JOIN LATERAL` và alias hợp lệ. |
| Nhiều hàng hơn dự kiến | `CROSS JOIN` hoặc SRF trả nhiều phần tử trên mỗi hàng. | Xác định cardinality trước, lọc/giới hạn. |
| Multi-unnest tạo NULL ở mảng ngắn | Cú pháp multi-argument `unnest` zip theo vị trí và đệm null. | Kiểm tra độ dài đầu vào. |
| `ROWS FROM` cho số hàng khác `CROSS JOIN` | Hai cú pháp có ngữ nghĩa kết hợp khác nhau. | Chọn zip hay tích Descartes đúng mục tiêu. |
| Truy vấn chậm trên dữ liệu lớn | SRF tạo rất nhiều hàng hoặc lateral subquery quét lặp nhiều lần. | Lọc hàng cha, index, giới hạn dãy, đo `EXPLAIN`. |
| Hàm do user tạo có plan sai | `ROWS`/`COST` ước lượng khác thực tế. | Đo actual rows và điều chỉnh metadata/SQL. |
| `array_agg(unnest(...))` bị lỗi | Aggregate chứa SRF trực tiếp trong đối số. | Đưa `unnest` vào `FROM` rồi `array_agg(t.value)`. |

### Bắt đầu chẩn đoán từ đâu?

1. Xác nhận đối số hàm có đúng **kiểu PostgreSQL** không (`text[]`, `jsonb`, timestamp...).
2. Gọi SRF **độc lập** với một input cụ thể để xem số hàng và tên cột:

   ```sql
   SELECT *
   FROM unnest(ARRAY['java', 'sql']::text[]) AS x(tag);
   ```

3. Đếm số hàng theo từng nguồn trước khi thêm join phức tạp.
4. Với `LATERAL`, kiểm tra nguồn bên trái và số hàng SRF trả cho **mỗi hàng cha**.
5. Kiểm tra cần giữ entity rỗng hay loại khỏi kết quả.
6. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp khi vấn đề là hiệu năng.

Không chỉ nhìn thấy câu SQL chạy thành công rồi kết luận đúng: **một SRF trả ít hoặc nhiều hàng hơn dự kiến có thể làm báo cáo sai dù không báo lỗi**.

## 36. Java/JDBC: nhận kết quả SRF như một ResultSet thông thường

Từ phía ứng dụng Java, kết quả một SRF đặt trong `FROM` là các hàng có cột, đọc bằng `ResultSet` như kết quả truy vấn bảng.

```java
String sql = """
    SELECT
        p.project_id,
        x.position,
        x.tag
    FROM lesson_srf.projects AS p
    CROSS JOIN LATERAL unnest(p.tags)
         WITH ORDINALITY AS x(tag, position)
    WHERE p.project_id = ?
    ORDER BY x.position
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long projectId = rs.getLong("project_id");
            long position = rs.getLong("position");
            String tag = rs.getString("tag");

            // Xử lý từng hàng tag trong thứ tự đã yêu cầu.
        }
    }
}
```

Đây là đoạn minh họa Java text block; giả định đã có `Connection connection` hợp lệ, imports và cơ chế xử lý `SQLException`.

### Khi LEFT JOIN làm cột vị trí NULL

Với `LEFT JOIN LATERAL`, hàng dự án rỗng có `x.position = NULL`. `ResultSet.getLong()` trả 0 đối với SQL NULL và cần gọi `rs.wasNull()` để phân biệt.

Ví dụ:

```java
long position = rs.getLong("position");
if (rs.wasNull()) {
    // Hàng cha không có phần tử từ SRF.
} else {
    // position là thứ tự phần tử thực.
}
```

### Dùng placeholder cho giá trị, không phải tên hàm/table

`PreparedStatement` hỗ trợ tham số **giá trị**:

```sql
SELECT n
FROM generate_series(1, ?) AS g(n);
```

Nhưng không dùng `?` làm tên hàm hoặc tên schema/table. Nếu ứng dụng chọn loại dữ liệu cần trải phẳng từ input, hãy map sang tập hàm/SQL đã được xác nhận cho phép; không ghép một tên hàm tùy ý từ HTTP request vào SQL.

## 37. Bảo mật khi định nghĩa và sử dụng hàm trả tập

Hàm do ứng dụng định nghĩa có thể chạy với quyền theo cấu hình PostgreSQL:

- **`SECURITY INVOKER`** (thông thường): quyền của người gọi được áp dụng theo ngữ nghĩa của function.
- **`SECURITY DEFINER`**: chạy với quyền của owner function trong các điều kiện liên quan.

Nếu function `SECURITY DEFINER` trả dữ liệu từ bảng nhạy cảm, người tạo phải kiểm soát **quyền EXECUTE**, input và `search_path`. Một function trả tập có thể làm lộ **nhiều hàng**, nên rủi ro cao hơn một hàm scalar chỉ trả trạng thái nhỏ.

### Quy tắc thiết kế

1. Đừng dùng `SECURITY DEFINER` khi không có nhu cầu rõ.
2. Với function có đặc quyền, đặt `search_path` an toàn và dùng **schema-qualified names** cho các bảng/hàm quan trọng.
3. Không cho role không tin cậy có `CREATE` trên schema được function tìm theo `search_path`.
4. Kiểm tra quyền theo tenant, role và điều kiện lọc **bên trong** function khi function là ranh giới dữ liệu.
5. Không coi alias của query hoặc `WHERE` do client tự thêm là cơ chế bảo mật đủ mạnh.
6. Cẩn thận với SRF gọi extension/network hoặc có side effects; planner có thể đánh giá biểu thức theo cách không giống vòng lặp Java đơn giản.

Chỉ vì function được gọi từ `SELECT` không có nghĩa nó chắc chắn vô hại: hàm `VOLATILE` có thể thực hiện công việc khác tùy quyền và nội dung triển khai.

## 38. Khi nào nên sử dụng SRF trong FROM?

| Bài toán | Cách dùng điển hình | Ghi chú |
|---|---|---|
| Sinh dãy số để tạo dữ liệu báo cáo | `generate_series(1, N)` | Giới hạn N nếu xuất phát từ client. |
| Sinh danh sách ngày | `generate_series(start_ts, end_ts, interval)` | Chú ý timezone/DST và ngày cuối có được tính. |
| Trải mảng thành hàng | `unnest(array_col)` | Mảng rỗng trả 0 hàng. |
| Giữ vị trí phần tử mảng | `unnest(...) WITH ORDINALITY` | Thêm `ORDER BY position` khi hiển thị. |
| Truy cập chỉ số mảng thật | `generate_subscripts(arr, 1)` | Khác ordinality nếu lower bound mảng không phải 1. |
| Trải JSON array | `jsonb_array_elements(...)` | Input phải là array. |
| Trải JSON array object thành cột | `jsonb_to_recordset(...) AS x(...)` | Khai báo kiểu cột rõ ràng. |
| Trải JSON object key/value | `jsonb_each(...)` | Không tin vào thứ tự key object. |
| Tách chuỗi nhiều dòng | `string_to_table`, `regexp_split_to_table` | Dữ liệu delimiter cần hợp đồng rõ. |
| Một hàng cha có nhiều phần tử phụ | `CROSS JOIN LATERAL SRF(parent.col)` | Cha có 0 phần tử sẽ biến mất. |
| Vẫn cần mọi hàng cha | `LEFT JOIN LATERAL ... ON TRUE` | Cha không có phần tử giữ một hàng với cột SRF null. |
| Top-N bản ghi liên quan mỗi entity | `LEFT JOIN LATERAL (SELECT ... LIMIT N)` | Index theo khóa cha + sort key có thể hữu ích. |
| Logic nghiệp vụ trả nhiều hàng | `RETURNS TABLE`/`RETURNS SETOF` | Thiết kế signature, quyền và cardinality. |

Hãy dùng SRF khi **biến một giá trị có cấu trúc hoặc một quy tắc sinh thành các hàng quan hệ** mang lại lợi ích. Nếu bài toán chỉ cần hỏi “mảng có chứa X?” hoặc “mảng có bao nhiêu phần tử?”, các toán tử/hàm mảng trực tiếp có thể dễ hiểu và hiệu quả hơn.

## 39. Bài tập thực hành

### Bài 1 — Sinh dãy tăng, giảm và dãy rỗng

Viết ba câu dùng `generate_series` trong `FROM` tạo các dãy:

1. 1, 2, 3, 4, 5.
2. 10, 8, 6, 4, 2.
3. Dãy rỗng do hướng step không phù hợp.

Giải thích vì sao step bằng 0 gây lỗi và vì sao stop được bao gồm khi bước đi tới đúng mốc.

### Bài 2 — Tạo khung ngày

Dùng `generate_series(timestamp, timestamp, interval '1 day')` sinh các ngày từ **10/11 đến 16/11/2026**. Ép kết quả thành `date`, đặt tên cột `report_day` và sắp theo ngày. Nêu rủi ro khi coi mọi ngày địa phương đều dài 24 giờ.

### Bài 3 — Trải phẳng mảng tags

Với `lesson_srf.projects`, viết truy vấn trả `project_id`, `project_name` và một `tag` trên mỗi hàng bằng `CROSS JOIN LATERAL unnest(tags)`. Dự đoán Gamma có xuất hiện không.

### Bài 4 — Giữ dự án rỗng

Sửa bài 3 thành `LEFT JOIN LATERAL ... ON TRUE` để vẫn trả Gamma. Cho biết tại Gamma, cột `tag` có giá trị nào và vì sao.

### Bài 5 — Thứ tự phần tử

Dùng `WITH ORDINALITY` trả các tags của Alpha kèm `position`. Sắp `ORDER BY position`. Nếu người dùng thêm một tag mới vào vị trí đầu mảng, các position có thể đổi ra sao?

### Bài 6 — COUNT(*) so với COUNT(position)

Với `LEFT JOIN LATERAL unnest(tags) WITH ORDINALITY`, tính cả `COUNT(*)` lẫn `COUNT(position)` theo dự án. Giải thích vì sao Gamma có thể có count 1 ở cột thứ nhất nhưng 0 ở cột thứ hai.

### Bài 7 — generate_subscripts

Tạo mảng `'[0:2]={10,20,30}'::integer[]`. Dùng `generate_subscripts(array,1)` tìm chỉ số thật, rồi dùng `unnest(... ) WITH ORDINALITY`. So sánh hai bộ số chỉ mục.

### Bài 8 — Hai mảng ghép theo vị trí

So sánh:

```sql
FROM unnest(
    ARRAY[10,20,30],
    ARRAY['A','B']
) AS x(id,label)
```

với:

```sql
FROM unnest(ARRAY[10,20,30]) AS ids(id)
CROSS JOIN unnest(ARRAY['A','B']) AS labels(label)
```

Đếm số hàng và giải thích vị trí nào bị đệm null ở trường hợp đầu.

### Bài 9 — ROWS FROM

Dùng `ROWS FROM (generate_series(1,4), unnest(ARRAY['x','y'])) WITH ORDINALITY`. Dự đoán số hàng, số thứ tự và phần tử null được đệm.

### Bài 10 — Mở JSON array members

Dùng `jsonb_array_elements(p.members)` trên bảng projects. Trả `project_id`, `name` và `role` của từng member bằng `->>`. Phân tích sự khác nhau giữa `CROSS JOIN` và `LEFT JOIN` với Beta.

### Bài 11 — jsonb_to_recordset

Viết `jsonb_to_recordset` cho:

```json
[
  {"name":"An","age":25},
  {"name":"Bình","age":31}
]
```

Khai báo hai cột `name text`, `age integer`. Nếu phần tử thiếu `age`, cột sẽ có giá trị gì? Nếu `age` là chuỗi không thể chuyển thành số, điều gì có thể xảy ra?

### Bài 12 — Phân biệt SQL NULL và JSON null

So sánh kết quả và lỗi có thể gặp khi gọi:

```sql
jsonb_array_elements(NULL::jsonb)
jsonb_array_elements('[]'::jsonb)
jsonb_array_elements('[null]'::jsonb)
jsonb_array_elements('null'::jsonb)
```

Giải thích vì sao trường hợp thứ ba có một phần tử JSON null còn trường hợp thứ tư không phải một JSON array hợp lệ.

### Bài 13 — Top 2 task trên mỗi dự án

Viết `LEFT JOIN LATERAL` lấy hai task mới nhất của mỗi project theo `created_at DESC, task_id DESC`. Giải thích vì sao Gamma vẫn xuất hiện và tại sao cần `task_id` làm tie-breaker.

### Bài 14 — Hàm RETURNS TABLE

Định nghĩa một SQL function nhận `project_id` và trả `task_id`, `task_title` của những task có `status='DOING'`. Dùng `RETURNS TABLE`, đặt tên cột rõ và gọi hàm trong `FROM`.

### Bài 15 — Hàm RETURNS SETOF

Viết một hàm `RETURNS SETOF text` để trả các tags của một project. Với project Gamma, dự đoán số hàng khi gọi hàm độc lập, khi `CROSS JOIN LATERAL` và khi `LEFT JOIN LATERAL`.

### Bài 16 — RETURN QUERY trong PL/pgSQL

Viết hàm `LANGUAGE plpgsql` nhận `p_status` và `RETURN QUERY SELECT` những task phù hợp. Giải thích sự khác biệt giữa `RETURN QUERY`, `RETURN NEXT` và `RETURN;`.

### Bài 17 — Trải phẳng rồi gom lại

Dùng `LEFT JOIN LATERAL unnest(tags) WITH ORDINALITY` và `jsonb_agg(upper(tag) ORDER BY position)` để trả một mảng JSON tag viết hoa cho mỗi project. Beta và Gamma có kết quả gì? Hãy dùng `FILTER` và `COALESCE('[]'::jsonb)`.

### Bài 18 — Đo số hàng và hiệu năng

Giả sử 100.000 dự án, mỗi dự án trung bình 50 tags. Ước lượng số hàng sau `CROSS JOIN LATERAL unnest(tags)` nếu mọi dự án đều có nhãn. Nêu các bước quan sát bằng `EXPLAIN (ANALYZE, BUFFERS)` và cách giảm lượng dữ liệu phải tạo.

### Bài 19 — Chọn khi nào không cần SRF

Với câu hỏi “Dự án nào có tag `postgresql`?”, so sánh:

```sql
WHERE 'postgresql' = ANY(tags)
```

với cách `CROSS JOIN LATERAL unnest(tags)` rồi `WHERE tag = 'postgresql'`. Nêu sự khác nhau về số hàng, nguy cơ trùng kết quả và khả năng dùng toán tử/chỉ mục mảng.

### Bài 20 — Phạm vi tên và bảo mật

Một ứng dụng Java cho phép client chọn trực tiếp tên function tùy ý để thực thi qua `FROM`, đồng thời function được tạo `SECURITY DEFINER`. Hãy chỉ ra rủi ro, đề xuất danh sách hàm được phép, kiểm soát `EXECUTE`, search path và giới hạn số hàng trả về.

## Kết luận

**Hàm trả tập (SRF)** là cầu nối giữa những giá trị có cấu trúc hoặc quy tắc sinh dữ liệu và **mô hình hàng–cột của SQL**. Trong PostgreSQL, đặt hàm ở **`FROM`** giúp kết quả có alias, tham gia `JOIN`, `WHERE`, `GROUP BY` và được quan sát như một nguồn quan hệ. `generate_series` sinh số/ngày; `unnest` và `generate_subscripts` xử lý mảng; `jsonb_array_elements`, `jsonb_to_recordset` và `jsonb_each` mở JSON thành các hàng; `ROWS FROM` kết hợp đầu ra nhiều table functions theo vị trí.

Điểm cần nhớ nhất là **cardinality và `LATERAL`**: một SRF có thể trả **0..N hàng cho mỗi hàng nguồn**. `CROSS JOIN LATERAL` phù hợp khi chỉ muốn các phần tử thật; `LEFT JOIN LATERAL ... ON TRUE` giữ cả entity không có phần tử. `WITH ORDINALITY` giúp lưu lại vị trí khi mở mảng hoặc JSON array, nhưng muốn thứ tự kết quả cuối ổn định vẫn cần **`ORDER BY`**.

Khi triển khai nâng cao, có thể định nghĩa `RETURNS SETOF`/`RETURNS TABLE` và dùng `RETURN QUERY` trong PL/pgSQL. Tuy nhiên, cần thiết kế rõ **kiểu cột, tính ổn định, quyền, giới hạn hàng, hành vi với NULL và chi phí thực thi**. Đừng trải phẳng hàng triệu phần tử khi một phép kiểm tra mảng trực tiếp là đủ, đừng giả định một SRF luôn trả một hàng, và đừng coi `ROWS` metadata là giới hạn cứng. Sử dụng SRF đúng cách giúp truy vấn PostgreSQL **linh hoạt, rõ nguồn dữ liệu, an toàn về ngữ nghĩa và dễ tối ưu**.
