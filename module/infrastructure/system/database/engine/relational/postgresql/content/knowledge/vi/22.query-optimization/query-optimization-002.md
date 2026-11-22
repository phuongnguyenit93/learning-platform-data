# Điều kiện có thể dùng chỉ mục và các dạng ép kiểu gây trở ngại trong PostgreSQL

Một chỉ mục đã tồn tại không có nghĩa PostgreSQL sẽ dùng nó trong mọi câu lệnh có nhắc tới cột được đánh chỉ mục. Truy vấn này có thể tìm rất nhanh:

```sql
SELECT *
FROM orders
WHERE order_id = 12345;
```

Nhưng một truy vấn tưởng như tương đương lại có thể buộc hệ thống duyệt nhiều dữ liệu hơn:

```sql
SELECT *
FROM orders
WHERE order_id::text = '12345';
```

Sự khác biệt nằm ở **biểu thức được đem ra so sánh**. Ở câu đầu, điều kiện dùng trực tiếp giá trị của cột `order_id`, thường phù hợp với B-tree trên cột đó. Ở câu sau, PostgreSQL phải xét **kết quả chuyển mỗi `order_id` thành text**; một index B-tree bình thường trên `order_id BIGINT` không nhất thiết cung cấp thứ tự hay phép so sánh của biểu thức `order_id::text`.

Không nên rút ra quy tắc quá cứng “hễ có `CAST` là mất index”. Một số ép kiểu là **binary-compatible**, một số kiểu có toán tử so sánh chéo trong cùng **operator family**; PostgreSQL đôi khi vẫn sử dụng index. Vấn đề phải phân tích là:

> **Bộ lọc còn khớp với giá trị, biểu thức và toán tử mà index hỗ trợ hay không? Planner có chứng minh được sự phù hợp đó và có thấy index rẻ hơn các đường truy cập khác không?**

Bài thuộc chương **Tối ưu truy vấn** của module *Database Engine Relational PostgreSQL*, tập trung vào cách viết điều kiện có thể tận dụng chỉ mục (*indexable predicates*, thường gọi gần nghĩa là *sargable predicates*) và những kiểu chuyển đổi dữ liệu khiến index khó phát huy tác dụng.

Sau bài học, bạn sẽ:

- Hiểu B-tree index hỗ trợ kiểu phép so sánh nào và vì sao `WHERE` đúng logic chưa chắc có đường truy cập tốt.
- Phân biệt **ép kiểu trên cột**, **ép kiểu literal** và **bind parameter có kiểu đúng**.
- Biết viết bộ lọc theo **khoảng thời gian** thay cho `created_at::date` hoặc `date_trunc(created_at)`.
- Tối ưu tìm kiếm chuỗi với `LIKE`, `ILIKE`, `lower()`, `text_pattern_ops` và `pg_trgm` khi phù hợp.
- Nhận diện ảnh hưởng của `COALESCE`, phép toán số học, hàm xử lý chuỗi, JSONB, `OR`, `IS NULL` và các phép nối giữa cột khác kiểu.
- Sử dụng **expression index**, **partial index**, **index nhiều cột** và dữ liệu được chuẩn hóa khi không thể sửa biểu thức truy vấn.
- Đọc `EXPLAIN`/`EXPLAIN ANALYZE` để phân biệt vấn đề **không dùng được index** với việc **dùng được nhưng planner thấy không đáng dùng**.
- Áp dụng đúng kiểu tham số trong PostgreSQL, JDBC và prepared statements.

> **Phạm vi an toàn:** Các lệnh tạo bảng và index của bài dùng schema riêng `idx_cast_lab`. Chỉ thử ở database học tập. Các câu `EXPLAIN (ANALYZE)` trong bài đều là SELECT đọc thuần trên dữ liệu demo; đối với UPDATE/DELETE/INSERT, `EXPLAIN ANALYZE` sẽ **thực thi DML thật**.

---

## 1. Điều kiện có thể dùng chỉ mục là gì?

### 1.1. Hình dung một B-tree index

Giả sử có index:

```sql
CREATE INDEX orders_customer_id_idx
ON orders (customer_id);
```

Trong mô hình khái niệm, index duy trì các khóa theo thứ tự có thể tra cứu:

```text
           B-tree(customer_id)

          [100] [200] [300]
             |     |     |
       nhiều entry được tổ chức theo thứ tự

WHERE customer_id = 200
    -> xác định vùng khóa 200
    -> tìm các hàng tương ứng
```

Nếu filter biến cột thành biểu thức:

```sql
WHERE customer_id + 100 = 300
```

về toán học có thể tương đương `customer_id=200`, nhưng planner **không được giả định** luôn đảo ngược mọi phép toán hoặc hàm tùy ý để áp điều kiện trực tiếp lên index.

### 1.2. Hai câu hỏi phải tách riêng

**Câu hỏi A — Điều kiện có đường truy cập index phù hợp không?**

- Cột có được dùng trực tiếp không?
- Biểu thức có đúng với expression index hiện có không?
- Kiểu toán tử có được access method và operator class/family hỗ trợ không?
- Với partial index, `WHERE` query có suy ra predicate của index không?
- Với index nhiều cột, điều kiện có tận dụng thứ tự key không?

**Câu hỏi B — Nếu có, planner có chọn index không?**

- Bảng có nhỏ quá không?
- Query lấy ít hàng hay gần toàn bảng?
- Giá trị lọc có chọn lọc tốt không?
- Có phải fetch nhiều heap pages không?
- `ORDER BY` và `LIMIT` có khớp thứ tự index không?
- Thống kê và cost settings có phản ánh workload không?

Một index **có thể dùng** mà PostgreSQL vẫn chọn `Seq Scan` là tình huống hợp lệ. Đừng coi sự xuất hiện của Seq Scan là bằng chứng duy nhất rằng cú pháp `WHERE` đã “phá index”.

### 1.3. “Sargable” là cách gọi thực hành, không phải một nhãn SQL chuẩn

Trong tài liệu tối ưu truy vấn, *sargable* thường nói đến điều kiện có thể dùng cấu trúc truy cập để giới hạn tập hàng thay vì bắt buộc kiểm tra biểu thức trên hầu hết hàng.

Với PostgreSQL cần cụ thể hơn:

| Thành phần | Vì sao quan trọng? |
|---|---|
| **Access method** | B-tree, GIN, GiST, BRIN có khả năng và cách truy cập khác nhau |
| **Operator class/family** | Quyết định loại toán tử và kiểu so sánh được index hiểu |
| **Index key/expression** | Index trên `x` khác index trên `lower(x)` |
| **Collation** | Ảnh hưởng thứ tự và so sánh chuỗi |
| **Query predicate** | Quyết định có thể giới hạn bằng index đến đâu |
| **Planner estimates** | Quyết định có nên chọn index không |

Vì thế, bài này không chỉ liệt kê “hàm làm hỏng index”, mà giải thích **vì sao**, **trường hợp ngoại lệ**, và cách kiểm chứng bằng plan.

---

## 2. B-tree hỗ trợ những điều kiện nào?

Với cột có B-tree index và toán tử phù hợp với operator class, các nhóm thường thuận lợi:

```sql
WHERE id = 100
WHERE id < 100
WHERE id <= 100
WHERE id > 100
WHERE id >= 100
WHERE id BETWEEN 100 AND 200
WHERE id IN (100, 101, 102)
```

PostgreSQL có thể dùng B-tree để thực hiện equality/range lookups và đôi khi phục vụ thứ tự `ORDER BY`.

### 2.1. Mẫu tốt: đẳng thức

```sql
SELECT *
FROM some_table
WHERE id = 100;
```

Với khóa duy nhất, việc tìm ít hàng thường phù hợp với index. Nhưng query lấy toàn bộ bảng với `WHERE status='active'` khi 99% hàng active có thể vẫn nên Seq Scan, dù `=` là toán tử dùng index được.

### 2.2. Mẫu tốt: khoảng nửa mở

```sql
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
```

Điều kiện trên giữ nguyên cột timestamp ở phía index key, giới hạn khoảng bằng hai cận rõ ràng.

### 2.3. BETWEEN có bao gồm hai cận

```sql
WHERE amount BETWEEN 100 AND 200
```

tương đương về mặt điều kiện:

```sql
WHERE amount >= 100
  AND amount <= 200
```

Với **timestamp** muốn lấy toàn bộ một ngày/tháng, cận trên **mở** thường an toàn hơn `BETWEEN ... 23:59:59` vì timestamp có độ chính xác nhỏ hơn giây.

### 2.4. IS NULL có thể dùng B-tree

```sql
WHERE deleted_at IS NULL
```

Một B-tree index trên `deleted_at` có thể phục vụ tìm hàng NULL trong nhiều trường hợp. Không đúng khi nói “B-tree không bao giờ index NULL”. Tính chọn lọc và cost vẫn quyết định plan.

### 2.5. Không phải toán tử nào cũng hợp B-tree

Các điều kiện như:

```sql
WHERE email LIKE '%gmail.com'
WHERE body ~ 'some_regex'
WHERE payload @> '{"category":"audit"}'::jsonb
```

không mặc định có cách truy cập tốt bằng B-tree bình thường trên cùng cột. Có thể cần **trigram GIN/GiST**, **JSONB GIN** hoặc expression index tùy toán tử và workload.

---

## 3. Môi trường thực hành: dữ liệu có số, chuỗi, UUID và timestamp

Để quan sát tác động của ép kiểu, ta cần một bảng có nhiều kiểu dữ liệu và phân bố đủ lớn.

### 3.1. Xác nhận database thực hành

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Các phần tiếp theo giả sử database thử nghiệm còn trống schema `idx_cast_lab`. Nếu đã có schema cùng tên do người khác sở hữu, **không ghi đè hoặc xóa**; chọn một database lab khác.

### 3.2. Tạo schema và bảng

```sql
CREATE SCHEMA idx_cast_lab;

CREATE TABLE idx_cast_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('queued', 'running', 'done', 'failed')),
    customer_email TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    external_id UUID NOT NULL,
    deleted_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

Các cột tạo ra những bài toán điển hình:

| Cột | Kiểu | Bộ lọc thường gặp |
|---|---|---|
| `event_id` | `BIGINT` | Tìm khóa chính, danh sách ID |
| `tenant_id` | `INTEGER` | Giới hạn tổ chức |
| `state` | `TEXT` | Lọc trạng thái |
| `customer_email` | `TEXT` | Tìm email chính xác, không phân biệt hoa/thường, tìm prefix |
| `event_time` | `TIMESTAMPTZ` | Lọc theo ngày, tháng và múi giờ |
| `amount` | `NUMERIC(12,2)` | Tìm mức tiền, so sánh khoảng |
| `external_id` | `UUID` | Tìm định danh từ hệ ngoài |
| `deleted_at` | `TIMESTAMPTZ` nullable | Chỉ bản ghi đang hoạt động |
| `payload` | `JSONB` | Điều kiện trên thuộc tính JSON |

### 3.3. Sinh 100.000 sự kiện demo

```sql
INSERT INTO idx_cast_lab.events
    (tenant_id, state, customer_email, event_time,
     amount, external_id, deleted_at, payload)
SELECT
    1 + (g % 20) AS tenant_id,
    CASE
        WHEN (g * 37) % 101 < 7  THEN 'queued'
        WHEN (g * 37) % 101 < 20 THEN 'running'
        WHEN (g * 37) % 101 < 85 THEN 'done'
        ELSE 'failed'
    END AS state,
    'User' || (1 + (g % 5000))::text || '@Example.test',
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 minute',
    ((g % 1000) + 1)::numeric / 10,
    (
        '00000000-0000-0000-0000-'
        || lpad(g::text, 12, '0')
    )::uuid,
    CASE WHEN g % 100 < 7
         THEN TIMESTAMPTZ '2026-03-01 00:00:00+00'
         ELSE NULL::timestamptz
    END,
    jsonb_build_object(
        'category', CASE
            WHEN g % 9 = 0 THEN 'audit' ELSE 'normal'
        END,
        'source_no', g
    )
FROM generate_series(1, 100000) AS gs(g);
```

Đây là dữ liệu giả định. Dãy `event_id` được identity cấp trong lần nạp mới. `external_id` dùng mẫu UUID xác định để tiện tra cứu, **không phải quy tắc tạo UUID bảo mật hoặc phân tán cho production**.

**Chỉ nạp một lần.** Nếu cố chạy lại, bảng sẽ có thêm hàng và các giả định về số lượng/ID sẽ không giữ nguyên.

### 3.4. Tạo các index nền

```sql
-- event_id đã có B-tree index từ PRIMARY KEY.

CREATE INDEX events_tenant_time_idx
ON idx_cast_lab.events
    (tenant_id, event_time DESC, event_id DESC);

CREATE INDEX events_amount_idx
ON idx_cast_lab.events (amount);

CREATE INDEX events_email_idx
ON idx_cast_lab.events (customer_email);

CREATE INDEX events_external_id_idx
ON idx_cast_lab.events (external_id);

ANALYZE idx_cast_lab.events;
```

Các index giúp ta so sánh điều kiện trực tiếp và biểu thức ép kiểu trên cùng dữ liệu.

### 3.5. Kiểm tra dữ liệu và thống kê

```sql
SELECT COUNT(*) AS total_rows
FROM idx_cast_lab.events;

SELECT state, COUNT(*) AS rows_in_state
FROM idx_cast_lab.events
GROUP BY state
ORDER BY state;

SELECT MIN(event_time), MAX(event_time)
FROM idx_cast_lab.events;
```

Nếu chạy đúng một lần, `total_rows=100000`. Các tỷ lệ trạng thái chỉ **xấp xỉ** mức từ biểu thức modulo, không cần cố dự đoán đúng từng số hàng.

---

## 4. Dùng EXPLAIN để phân biệt khả năng tận dụng index

### 4.1. Xem kế hoạch mà không chạy SELECT

```sql
EXPLAIN
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

Kế hoạch có thể có:

```text
Index Scan using events_pkey on events
  Index Cond: (event_id = 1000)
```

Tên index thực tế của primary key thường là `events_pkey` khi tạo bảng theo ví dụ, nhưng hãy nhìn output server của bạn thay vì coi mẫu plan trên là kết quả luôn cố định.

### 4.2. Xem actual rows và buffers khi query là SELECT thuần

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

Chú ý:

- `Index Scan`, `Index Only Scan`, `Bitmap Heap Scan` hay `Seq Scan`.
- `Index Cond` và `Filter`.
- `rows` ước lượng so với `actual rows`.
- `Rows Removed by Filter`.
- `Buffers: shared hit/read`.
- `Planning Time` và `Execution Time`.

### 4.3. Thế nào là một kết luận có căn cứ?

Không nên nói “query sử dụng index” chỉ vì DDL có index. Cần quan sát một plan thực. Cũng không nói “hàm làm mất index” chỉ vì thấy Seq Scan trên 5 hàng thử nghiệm: **planner có thể chọn Seq Scan vì rẻ hơn**.

Một cách phân tích:

```text
Query SQL
   |
   +-- Điều kiện dùng cột/biểu thức nào?
   |
   +-- Operator có phù hợp index và kiểu dữ liệu?
   |
   +-- Index keys/predicate có khớp?
   |
   +-- EXPLAIN cho Index Cond hay chỉ Filter?
   |
   +-- Estimated/actual rows có hợp lý?
   |
   +-- Kết luận: phù hợp logic, kế hoạch và chi phí
```

### 4.4. EXPLAIN ANALYZE không tự an toàn cho DML

`EXPLAIN (ANALYZE) UPDATE/DELETE/INSERT` **thực thi lệnh ghi**. Không mang thói quen từ các SELECT demo sang câu lệnh ghi trên production. Kể cả `SELECT` gọi `nextval()` hoặc hàm gửi thông báo cũng có thể có tác dụng phụ.

---

## 5. CAST ở phía cột và CAST ở phía giá trị

### 5.1. Điều kiện trực tiếp trên BIGINT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

`event_id` có kiểu `BIGINT` và primary-key B-tree. Đây là truy vấn khóa duy nhất, thường rất thích hợp với index.

### 5.2. Ép BIGINT thành TEXT ngay tại cột

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id::text = '1000';
```

Kết quả so sánh không còn là phép so sánh `BIGINT = BIGINT` trên khóa index nữa, mà là phép so sánh của **biểu thức chuyển event_id sang text**.

Một B-tree index trên `event_id BIGINT` được tạo để phục vụ các toán tử sắp xếp/so sánh phù hợp với khóa BIGINT; nó không mặc nhiên có cấu trúc để tìm nhanh các giá trị **sau khi đổi sang chuỗi**.

### 5.3. Ép giá trị tìm kiếm sang BIGINT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = '1000'::bigint;
```

Giờ cột được giữ nguyên. PostgreSQL có thể dùng B-tree trên `event_id`.

**Nguyên tắc thực hành:** khi cột có kiểu đúng, hãy đưa **literal/parameter** về cùng kiểu hợp lệ của cột, thay vì đổi toàn bộ cột sang kiểu của dữ liệu đầu vào.

### 5.4. Chuỗi literal chưa định kiểu không luôn phá index

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = '1000';
```

Đây **không đồng nghĩa** PostgreSQL sẽ lấy từng `event_id` rồi gọi `::text`.

Một string literal viết trong SQL ban đầu thường có kiểu `unknown`; PostgreSQL dùng ngữ cảnh toán tử để suy ra nó cần được chuyển thành `BIGINT`, nên điều kiện có thể vẫn dùng index.

**Khác biệt:**

```text
event_id = '1000'
    literal kiểu unknown được suy ra thành BIGINT

event_id::text = '1000'
    biểu thức phía cột đã bị chuyển thành TEXT
```

Không dùng hai tình huống trên để kết luận mọi chuỗi trong JDBC đều được tự suy kiểu tương tự: typed parameter của prepared statement có quy tắc riêng.

### 5.5. Literal không đổi kiểu thành công thì lỗi, không fallback vô hạn

```sql
-- Dự kiến lỗi invalid_input_syntax cho BIGINT:
-- SELECT *
-- FROM idx_cast_lab.events
-- WHERE event_id = 'abc';
```

Không nên “sửa” bằng cách ép `event_id::text` để có thể so mọi chuỗi rác. Hãy xác thực định dạng đầu vào, báo lỗi hợp lệ hoặc chuyển giá trị sang đúng kiểu trước khi truy vấn.

### 5.6. Tại sao phép so sánh kiểu dữ liệu còn có vấn đề ngữ nghĩa?

`BIGINT` và `TEXT` có **thứ tự** khác nhau:

```text
Số:     2 < 10
Chuỗi: '10' < '2'  (theo thứ tự từ điển trong nhiều collations)
```

Vì vậy không thể mặc định index sắp theo số cũng sắp đúng theo cách so sánh text.

---

## 6. Không phải mọi phép ép kiểu đều cản trở B-tree

PostgreSQL có hệ thống toán tử và **operator classes/families**. Một B-tree operator family có thể hỗ trợ so sánh giữa các kiểu khác nhau, khi các phép toán tương thích về thứ tự.

### 6.1. Integer và BIGINT

Ví dụ:

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 1000::integer;
```

`event_id` là `BIGINT`, biểu thức phía phải có `INTEGER`. PostgreSQL có các toán tử so sánh phù hợp giữa các kiểu số nguyên và có thể tận dụng B-tree tương ứng **mà không bắt buộc viết `event_id::integer`**.

Đây là ví dụ phản bác phát biểu “kiểu hai vế phải giống hệt mới dùng được index”.

### 6.2. VARCHAR và TEXT

Một số conversion giữa `VARCHAR` và `TEXT` có tính chất tương thích biểu diễn. Những điều kiện:

```sql
-- Hai cột/literal trong các schema khác nhau:
-- text_col = varchar_parameter
-- varchar_col = text_parameter
```

không nhất thiết phá index. Planner có thể xử lý các toán tử/cast phù hợp với B-tree và collation.

Không xem một cast xuất hiện trong `EXPLAIN` là bằng chứng tự động mất chỉ mục. Phải quan sát **cột/biểu thức mà `Index Cond` thực sự áp dụng**.

### 6.3. Vì sao đổi kiểu có thể làm biến đổi kết quả?

Các loại conversion:

- Có thể **mất chính xác**: `NUMERIC` sang `DOUBLE PRECISION`.
- Có thể phụ thuộc **timezone/session**: `TIMESTAMPTZ` sang `DATE` hoặc timestamp không múi giờ.
- Có thể phụ thuộc **collation**: so sánh/chuẩn hóa chuỗi.
- Có thể không có phép chuyển ngầm hợp lệ: `TEXT` sang `UUID`/`BIGINT` tùy ngữ cảnh.

Do vậy, ngay cả khi planner có thể áp index, ép kiểu có thể làm **semantics khác yêu cầu**. Tối ưu trước hết phải giữ đúng kết quả.

### 6.4. Quy tắc tốt hơn câu “tránh mọi CAST”

Hãy kiểm tra bốn yếu tố:

1. Kiểu dữ liệu thật của cột.
2. Kiểu dữ liệu thật của giá trị/parameter.
3. Toán tử PostgreSQL đã chọn sau khi resolve types.
4. Index opclass/family và plan thực tế.

Nếu một CAST biến cột thành **biểu thức mới** không có index tương ứng, hãy xem đó là tín hiệu cần viết lại query hoặc tạo expression index có chủ đích.

---

## 7. Ép kiểu trên cột số học, tiền tệ và phép tính

### 7.1. Tìm NUMERIC bằng điều kiện trực tiếp

```sql
EXPLAIN
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE amount = 50.00::numeric;
```

`amount` có B-tree index và điều kiện dùng kiểu số phù hợp. Đây là một mẫu phù hợp cho equality lookup.

### 7.2. Đổi cột NUMERIC thành chuỗi

```sql
EXPLAIN
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE amount::text = '50.00';
```

Điều kiện đặt phép chuyển đổi trên cột, khác với B-tree trên `amount NUMERIC`. Hơn nữa, biểu diễn chuỗi của số còn có chi tiết về scale/format, làm việc so sánh chuỗi không đồng nghĩa khái niệm số học trong mọi trường hợp.

**Sửa theo mục đích tìm số:**

```sql
WHERE amount = 50.00::numeric
```

### 7.3. Đổi NUMERIC sang DOUBLE PRECISION

```sql
-- Tránh nếu nghiệp vụ cần so sánh tiền với độ chính xác NUMERIC:
-- WHERE amount::double precision = 50.0::double precision
```

Chuyển sang số thực nhị phân có thể ảnh hưởng độ chính xác hoặc điều kiện bằng nhau với những số thập phân. Một index trên `NUMERIC` không mặc nhiên là index trên `amount::double precision`.

Không đổi kiểu dữ liệu tiền sang floating point chỉ để thỏa kiểu parameter từ client; dùng `BigDecimal`/`NUMERIC` phù hợp.

### 7.4. Phép toán số học ở vế cột

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE amount + 5 = 55;
```

Về toán học, với các giá trị hữu hạn và cùng miền:

```sql
WHERE amount = 50
```

diễn đạt mục tiêu đơn giản hơn. PostgreSQL không được kỳ vọng biến đổi mọi phép toán tùy ý để phục vụ B-tree trên `amount`.

### 7.5. Không biến đổi đại số vô điều kiện

Các phép biến đổi có thể sai khi:

- Có `NULL`.
- Có tràn số hoặc giới hạn kiểu.
- Có làm tròn/ép kiểu.
- Có hàm không thuần túy/không một-một.
- Có timezone, collation hoặc quy tắc khác.

Ví dụ `x * 2 = 10` có thể diễn giải thành `x = 5` trong miền số phù hợp, nhưng đừng tự động viết một engine rewrite chung cho tất cả kiểu dữ liệu.

---

## 8. TIMESTAMPTZ::date: bẫy rất phổ biến

Một API muốn lấy sự kiện ngày 10/02/2026 thường viết:

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE event_time::date = DATE '2026-02-10';
```

Câu này có vẻ dễ đọc, nhưng có hai vấn đề:

1. **Cột được đưa qua phép chuyển đổi** từ `TIMESTAMPTZ` sang `DATE`; B-tree trên `event_time` không mặc nhiên cung cấp điều kiện tìm kiếm theo biểu thức mới.
2. Với `TIMESTAMPTZ`, `::date` phụ thuộc **TimeZone của session**. “Ngày” không có ý nghĩa tuyệt đối nếu không xác định vùng giờ.

### 8.1. Kiểm tra TimeZone

```sql
SHOW TIME ZONE;
```

Một thời điểm như `2026-02-09 18:00:00+00` là ngày 09/02 ở UTC nhưng là ngày 10/02 tại Việt Nam (+07). Vì vậy:

```sql
WHERE event_time::date = DATE '2026-02-10'
```

có thể chọn **những tập hàng khác nhau** khi TimeZone của session thay đổi.

### 8.2. Viết bằng khoảng nửa mở trên cột gốc

Muốn lấy **ngày 10/02/2026 theo UTC**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >=
      TIMESTAMPTZ '2026-02-10 00:00:00+00'
  AND event_time <
      TIMESTAMPTZ '2026-02-11 00:00:00+00'
ORDER BY event_time DESC, event_id DESC;
```

Index `(tenant_id, event_time DESC, event_id DESC)` có thể hỗ trợ tenant equality và khoảng thời gian, đồng thời có thứ tự phù hợp với ORDER BY.

### 8.3. Khoảng theo ngày địa phương Việt Nam

Nếu nghiệp vụ nói “ngày 10/02 tại TP.HCM”, cần chuyển **hai đầu mốc local** sang instant:

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >= (
      TIMESTAMP '2026-02-10 00:00:00'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
  )
  AND event_time < (
      TIMESTAMP '2026-02-11 00:00:00'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
  )
ORDER BY event_time DESC, event_id DESC;
```

Hai biểu thức cận trả giá trị `TIMESTAMPTZ`. Cột `event_time` được giữ nguyên, giúp B-tree có cơ hội giới hạn range.

### 8.4. Vì sao không trừ đúng 24 giờ cho mọi timezone?

Nhiều múi giờ có **daylight saving time (DST)**; một ngày lịch địa phương có thể dài 23 hoặc 25 giờ. Thay vì lấy local midnight rồi cộng cố định 24 giờ UTC, hãy **chuyển cả ngày bắt đầu và ngày kế tiếp** từ local timezone sang instant.

Với `Asia/Ho_Chi_Minh` không có DST trong những ngày thông thường hiện nay, cách dựng hai đầu mốc vẫn thể hiện quy tắc rõ hơn và áp dụng được cho các vùng giờ có DST.

### 8.5. Không dùng BETWEEN với “23:59:59”

```sql
-- Có thể bỏ sót các hàng có phần thập phân của giây:
-- WHERE event_time BETWEEN
--       '2026-02-10 00:00:00+07'
--   AND '2026-02-10 23:59:59+07'
```

Dùng:

```sql
WHERE event_time >= :begin_instant
  AND event_time <  :next_day_begin_instant
```

`:begin_instant` là ký hiệu placeholder ở tầng ứng dụng, **không phải cú pháp bind chuẩn của psql**; ở JDBC dùng `?`.

---

## 9. DATE_TRUNC, TO_CHAR, EXTRACT và hàm ở phía timestamp

### 9.1. DATE_TRUNC để nhóm khác với DATE_TRUNC để lọc

Một query báo cáo:

```sql
SELECT date_trunc('month', event_time) AS month_start,
       COUNT(*)
FROM idx_cast_lab.events
GROUP BY date_trunc('month', event_time);
```

có mục đích **gom nhóm** theo tháng. Nhưng để lấy một tháng cố định, nếu viết:

```sql
WHERE date_trunc('month', event_time)
    = TIMESTAMPTZ '2026-02-01 00:00+00'
```

thì phép tính nằm trên **cột**; B-tree bình thường trên `event_time` không nhất thiết dùng trực tiếp để xác định cận.

Với yêu cầu lọc tháng UTC, thường rõ và dễ đánh index hơn:

```sql
WHERE event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-03-01 00:00+00'
```

### 9.2. TO_CHAR đưa thời điểm thành TEXT

```sql
-- Dễ làm cột indexed bị biến thành expression text:
-- WHERE to_char(event_time, 'YYYY-MM') = '2026-02'
```

Ngoài vấn đề index, `to_char` còn liên quan định dạng và ngữ cảnh thời gian. Nếu mục đích là lọc khoảng thời điểm, nên dùng range timestamp rõ mốc. Dùng `to_char` chủ yếu cho **trình bày kết quả** khi cần.

### 9.3. EXTRACT(YEAR ...) không tương đương một khoảng duy nhất trong mọi ngữ cảnh

```sql
WHERE EXTRACT(YEAR FROM event_time) = 2026
```

là một phép biến đổi trên cột. Để lấy các instant thuộc năm 2026 theo UTC:

```sql
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2027-01-01 00:00+00'
```

Nếu nghiệp vụ theo timezone khác, cần chuyển mốc đầu năm theo timezone đó.

### 9.4. Vì sao expression index trên TIMESTAMPTZ::date không đơn giản?

Một expression index phải sử dụng biểu thức **IMMUTABLE** theo yêu cầu PostgreSQL. `event_time::date` từ `TIMESTAMPTZ` phụ thuộc TimeZone của session, nên không thể đơn giản tạo index expression hợp lệ và bất biến bằng cách:

```sql
-- Ví dụ không hợp lệ đối với TIMESTAMPTZ:
-- CREATE INDEX idx_event_day
-- ON idx_cast_lab.events ((event_time::date));
```

Không “lách” bằng cách khai báo một wrapper function phụ thuộc session là IMMUTABLE khi thực tế không đúng.

Nếu thực sự cần expression index cho **ngày UTC**, có thể xét cách **đóng đinh timezone** bằng biểu thức đáp ứng tính bất biến và kiểm chứng trên phiên bản server. Tuy nhiên, với lọc một khoảng thời gian, index trực tiếp trên `event_time` và hai cận thường đơn giản hơn.

---

## 10. LOWER(email) và expression index

### 10.1. Query không phân biệt chữ hoa/thường

Dữ liệu lab dùng địa chỉ dạng `User42@Example.test`. Người dùng nhập `user42@example.test` và cần tìm không phân biệt chữ hoa/thường.

Một câu SQL:

```sql
EXPLAIN
SELECT event_id, customer_email
FROM idx_cast_lab.events
WHERE lower(customer_email) = 'user42@example.test';
```

về mặt nghiệp vụ có thể đúng với quy tắc **case folding** mà hệ thống chọn. Nhưng index nền `events_email_idx` là B-tree trên **`customer_email` gốc**, không phải trên `lower(customer_email)`.

### 10.2. Tạo expression index

```sql
CREATE INDEX events_lower_email_idx
ON idx_cast_lab.events (lower(customer_email));

ANALYZE idx_cast_lab.events;
```

Lúc này query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, customer_email
FROM idx_cast_lab.events
WHERE lower(customer_email) = 'user42@example.test';
```

**có thể** dùng expression index tương ứng. Vẫn còn tính chọn lọc và cost decision.

### 10.3. Expression index không làm mọi query email nhanh

Index:

```sql
ON events (lower(customer_email))
```

phù hợp với query dùng **biểu thức tương ứng**:

```sql
WHERE lower(customer_email) = lower('USER42@example.test')
```

Nhưng nó không tự thay thế index trên `customer_email` cho điều kiện **case-sensitive**:

```sql
WHERE customer_email = 'User42@Example.test'
```

Hai điều kiện có semantics khác nhau và có thể yêu cầu những index khác nhau.

### 10.4. Index expression có chi phí ghi

Khi INSERT/UPDATE làm thay đổi email, PostgreSQL phải tính và duy trì expression key. Index lớn hơn và có thể ảnh hưởng HOT-update eligibility.

Vì vậy expression index là giải pháp khi **không thể hoặc không nên viết lại query thành điều kiện trên cột nguyên dạng**, không phải lý do để đánh index mọi hàm xuất hiện trong SELECT.

### 10.5. Collation và Unicode

`lower()` không phải quy tắc chuẩn hóa email hoàn chỉnh cho mọi miền, Unicode và collation. Nếu nghiệp vụ yêu cầu so sánh không phân biệt hoa/thường, hãy xác định:

- Quy tắc chuẩn hóa chuỗi đầu vào.
- Collation được dùng.
- Có cần case folding theo ngôn ngữ không?
- Có cần dùng `citext` (extension) hoặc collation không phân biệt cấp độ nào không?
- Index và query phải dùng semantics nhất quán.

Không đổi từ `=` sang `lower()` nếu điều đó làm mất yêu cầu phân biệt hoa/thường của nghiệp vụ.

---

## 11. LIKE, ILIKE và vị trí wildcard

Một B-tree index trên `TEXT` có thể giúp một số truy vấn tiền tố, nhưng cần điều kiện về **pattern** và **collation/operator class**.

### 11.1. LIKE có tiền tố cố định

```sql
SELECT event_id, customer_email
FROM idx_cast_lab.events
WHERE customer_email LIKE 'User1%';
```

Pattern có **phần đầu cố định** `User1`, nên có cơ hội biến thành phép tìm vùng chuỗi trong B-tree khi operator class/collation phù hợp.

### 11.2. text_pattern_ops trong collation không phù hợp mặc định

Với các database không dùng collation `C`, một B-tree text index theo opclass mặc định có thể không giúp tối ưu `LIKE 'prefix%'` như kỳ vọng. PostgreSQL có operator class dành cho mẫu tiền tố:

```sql
CREATE INDEX events_email_pattern_idx
ON idx_cast_lab.events
    (customer_email text_pattern_ops);
```

Thử:

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE customer_email LIKE 'User1%';
```

Planner có thể áp dụng các phép so sánh theo prefix phù hợp với opclass. Nhưng vẫn có thể chọn Seq Scan nếu phần lớn hàng cùng tiền tố hoặc bảng nhỏ.

**Không khẳng định mọi collation đều có hành vi giống nhau**, nhất là khi sử dụng nondeterministic collations và các phiên bản PostgreSQL khác nhau.

### 11.3. Wildcard ở đầu chuỗi

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE customer_email LIKE '%example.test';
```

Không có tiền tố cố định để B-tree truyền thống xác định một đoạn liên tục trên thứ tự chuỗi. Index `text_pattern_ops` không tự biến việc tìm suffix thành prefix lookup.

### 11.4. ILIKE và so sánh không phân biệt hoa/thường

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE customer_email ILIKE 'user1%';
```

Không nên mặc định B-tree bình thường xử lý hiệu quả mọi `ILIKE`, vì tính không phân biệt hoa/thường và collation có thể làm mất khả năng suy ra một range đơn giản.

Nếu ứng dụng chọn `lower()` làm semantics:

```sql
WHERE lower(customer_email) LIKE 'user1%'
```

có thể xem xét expression index với pattern opclass:

```sql
CREATE INDEX events_lower_email_pattern_idx
ON idx_cast_lab.events
    ((lower(customer_email)) text_pattern_ops);
```

### 11.5. Trigram index cho chứa chuỗi

Nếu workload thường tìm:

```sql
WHERE customer_email ILIKE '%user42%'
```

thì extension `pg_trgm` và GIN/GiST trigram index thường phù hợp hơn B-tree:

```sql
-- Tùy quyền và chính sách cài extension của database.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX events_email_trgm_idx
ON idx_cast_lab.events
USING gin (customer_email gin_trgm_ops);
```

`pg_trgm` không phải giải pháp không chi phí: cần extension, index có dung lượng và chi phí ghi; pattern rất ngắn hoặc ít ký tự phân biệt có thể kém hiệu quả. Khi không có quyền cài extension, hãy nhờ DBA đánh giá thay vì tự mở rộng quyền.

### 11.6. Bộ lọc pattern và số hàng dự kiến

Ngay cả khi một index hỗ trợ LIKE/ILIKE, truy vấn match 90% bảng có thể vẫn quét tuần tự vì rẻ hơn. Điều này khác với truy vấn có wildcard đầu **không phù hợp cấu trúc B-tree prefix**.

---

## 12. COALESCE, CASE, NULL và hàm quanh cột

### 12.1. Cột nullable trong WHERE

`deleted_at` là `TIMESTAMPTZ` có thể NULL.

Muốn lấy hàng đang hoạt động:

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE deleted_at IS NULL;
```

Điều kiện rõ ràng, có thể được hỗ trợ bởi B-tree trên `deleted_at` hoặc partial index thích hợp.

### 12.2. Dùng COALESCE để thay NULL bằng giá trị giả

```sql
-- Không phải cách viết ưu tiên nếu chỉ cần NULL:
-- WHERE COALESCE(deleted_at,
--      TIMESTAMPTZ '9999-12-31 00:00+00')
--      = TIMESTAMPTZ '9999-12-31 00:00+00'
```

Ngoài việc đặt hàm trên cột, nó còn giả định **không có hàng thật nào mang giá trị sentinel**. Nếu dữ liệu thật có giá trị đó, semantics có thể sai.

**Sửa đúng mục tiêu:** `WHERE deleted_at IS NULL`.

### 12.3. Tạo partial index cho hàng live

```sql
CREATE INDEX events_live_tenant_time_idx
ON idx_cast_lab.events (tenant_id, event_time DESC)
WHERE deleted_at IS NULL;
```

Query:

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND deleted_at IS NULL
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
ORDER BY event_time DESC
LIMIT 20;
```

có bộ lọc suy ra predicate `deleted_at IS NULL`. Partial index có thể phù hợp.

### 12.4. CASE bên trong WHERE

```sql
-- Một biểu thức logic có thể được viết phức tạp không cần thiết:
-- WHERE CASE WHEN deleted_at IS NULL
--            THEN 1 ELSE 0 END = 1
```

Nếu yêu cầu thực tế chỉ là `IS NULL`, viết trực tiếp để giữ ngữ nghĩa rõ và tạo cơ hội cho index.

### 12.5. B-tree cũng có thể hỗ trợ IS NOT NULL

```sql
WHERE deleted_at IS NOT NULL
```

Không được coi `IS NOT NULL` là “chắc chắn không thể dùng index”. Nó có thể phù hợp với một số đường truy cập B-tree hoặc partial index; planner quyết định dựa vào phân bố NULL.

---

## 13. Expression index: khi không thể bỏ hàm trên cột

Không phải mọi yêu cầu có thể viết lại thành điều kiện trực tiếp.

### 13.1. Ví dụ chỉ mục trên lower(email)

```sql
CREATE INDEX events_lower_email_idx
ON idx_cast_lab.events (lower(customer_email));
```

Trong lab, index này đã được tạo ở mục 10. Câu SQL ở đây nhắc lại định nghĩa **về mặt khái niệm**; đừng chạy hai lần cùng tên.

### 13.2. Khớp biểu thức là điều cốt lõi

Index trên:

```sql
lower(customer_email)
```

phù hợp với query:

```sql
WHERE lower(customer_email) = 'user42@example.test'
```

chứ không đồng nghĩa mọi hàm chuyển đổi email:

```sql
WHERE trim(lower(customer_email)) = 'user42@example.test'
```

đều tận dụng được key ấy. Nếu cần trim, có thể phải chuẩn hóa dữ liệu đầu vào khi ghi hoặc thiết kế expression index khác.

### 13.3. Tính bất biến của expression index

PostgreSQL yêu cầu các function/operator trong biểu thức index đáp ứng yêu cầu về **IMMUTABLE**. Một function phụ thuộc thời gian thực, session setting hay dữ liệu bên ngoài có thể không hợp lệ.

Ví dụ không nên thử tạo index trên:

```sql
-- Không hợp lệ vì now() không IMMUTABLE:
-- CREATE INDEX bad_idx
-- ON idx_cast_lab.events ((event_time < now()));
```

Ngay cả khi có thể tự viết wrapper mang nhãn IMMUTABLE, việc **khai báo sai volatility** có thể làm index không phản ánh đúng dữ liệu.

### 13.4. Expression index cần được duy trì

Mỗi INSERT/UPDATE liên quan sẽ đánh giá và duy trì expression index. Nó tốn disk/WAL và có thể ảnh hưởng cập nhật HOT. Hãy:

- Dựa vào workload có thật.
- Ưu tiên biểu thức đơn giản, đúng ngữ nghĩa.
- Tránh trùng index.
- Đo chi phí đọc và ghi trước/sau.
- Xem index có được sử dụng theo plan không.

### 13.5. Generated column hay chuẩn hóa khi ghi

Nếu nhiều truy vấn đều cần `lower(email)` hoặc một khóa chuẩn hóa, có thể cân nhắc:

- Chuẩn hóa dữ liệu ngay khi ghi, nếu nghiệp vụ cho phép.
- Cột dẫn xuất được duy trì có quy tắc rõ.
- Generated column khi biểu thức đáp ứng yêu cầu của PostgreSQL.
- Expression index trên biểu thức ổn định.

Các phương án này có chi phí lưu trữ, cập nhật và migration khác nhau. Không tạo một cột dẫn xuất chỉ để né việc sửa một câu `WHERE` đơn giản.

---

## 14. UUID: tránh đổi khóa thành TEXT khi tìm kiếm

`external_id` trong lab là `UUID`, có index riêng.

### 14.1. So sánh UUID đúng kiểu

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE external_id =
    '00000000-0000-0000-0000-000000000100'::uuid;
```

Điều kiện giữ nguyên kiểu `UUID` ở cột và value. B-tree index trên external_id có cơ hội tìm chính xác.

### 14.2. Ép UUID sang TEXT

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE external_id::text =
    '00000000-0000-0000-0000-000000000100';
```

Một index trên giá trị `UUID` không mặc nhiên là index trên chuỗi mà UUID được format. Tìm theo UUID thì nên **parse đầu vào thành UUID**, không chuyển toàn bộ cột sang text.

### 14.3. UUID string sai phải bị báo lỗi

```sql
-- Chuỗi không hợp lệ cho UUID sẽ lỗi khi cast:
-- WHERE external_id = 'not-a-uuid'::uuid
```

Đây là hành vi đúng: client phải trả lỗi validation phù hợp. Không “sửa” bằng cách cast mọi UUID sang text để tránh lỗi nhập liệu.

### 14.4. UUID và JDBC

Trong Java:

```java
import java.util.UUID;

UUID externalId =
    UUID.fromString(requestExternalId);

preparedStatement.setObject(1, externalId);
```

Với pgJDBC hỗ trợ `java.util.UUID`, việc bind một UUID đúng kiểu giúp server nhận param phù hợp. Không gửi UUID như `String` rồi buộc cột `external_id::text` chỉ để so khớp.

---

## 15. JSONB: toán tử @> và phép trích xuất text

JSONB là ví dụ rõ ràng rằng “dùng index” còn phụ thuộc **loại index** và **toán tử**.

### 15.1. Lọc bằng toán tử containment

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE payload @> '{"category":"audit"}'::jsonb;
```

Toán tử `@>` có thể dùng **GIN index** phù hợp trên `JSONB`.

```sql
CREATE INDEX events_payload_gin_idx
ON idx_cast_lab.events
USING gin (payload);
```

### 15.2. Lọc bằng ->> trả TEXT

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE payload ->> 'category' = 'audit';
```

`payload ->> 'category'` là **một biểu thức trả TEXT**. GIN trên toàn bộ JSONB không mặc định trở thành B-tree equality index của biểu thức TEXT này.

Nếu workload chủ yếu tìm category:

```sql
CREATE INDEX events_payload_category_idx
ON idx_cast_lab.events ((payload ->> 'category'));
```

Đây là B-tree **expression index** cho giá trị text được trích xuất.

### 15.3. Chọn cách nào?

| Nhu cầu | Hướng index thường xét |
|---|---|
| Nhiều truy vấn containment `payload @> ...` | GIN phù hợp với JSONB và các toán tử cần dùng |
| Tìm equality một thuộc tính text `payload->>'category'` | B-tree expression index |
| Tìm khoảng trên số lưu trong JSONB | Cast có kiểm soát, hoặc đưa dữ liệu typed ra cột nếu dùng thường xuyên |
| Tìm toàn văn/text contains | Full-text hoặc trigram tùy mục tiêu |

### 15.4. Cast số lấy từ JSONB có thể khó và nguy hiểm

```sql
-- Minh họa nhu cầu:
-- WHERE (payload ->> 'total')::numeric >= 100
```

Nếu một hàng chứa `"total":"unknown"`, cast sang numeric có thể lỗi. Index expression trên cast ấy cũng có thể không tạo được khi dữ liệu có giá trị không chuyển được.

Không tạo expression index trên giá trị JSONB chưa xác thực. Nếu đây là trường quan trọng và dùng range thường xuyên, cân nhắc **cột NUMERIC có constraint** hoặc quy trình chuẩn hóa dữ liệu.

---

## 16. JOIN hai cột khác kiểu: bẫy ép kiểu ở ON

Một hệ thống lâu năm thường có bảng mới dùng khóa `BIGINT` nhưng bảng import cũ lưu cùng ID dưới dạng `TEXT`.

### 16.1. Tạo bảng staging chứa ID dạng chuỗi

```sql
CREATE TABLE idx_cast_lab.legacy_event_links (
    link_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_event_id TEXT NOT NULL,
    link_type TEXT NOT NULL
);

INSERT INTO idx_cast_lab.legacy_event_links
    (raw_event_id, link_type)
SELECT event_id::text, 'export'
FROM idx_cast_lab.events
WHERE event_id BETWEEN 1 AND 30;

CREATE INDEX legacy_event_links_raw_id_idx
ON idx_cast_lab.legacy_event_links (raw_event_id);
```

### 16.2. JOIN ép BIGINT thành TEXT

```sql
EXPLAIN
SELECT e.event_id, l.link_id
FROM idx_cast_lab.events AS e
JOIN idx_cast_lab.legacy_event_links AS l
  ON e.event_id::text = l.raw_event_id;
```

Join này có thể vẫn được PostgreSQL thực hiện đúng kết quả, nhưng **B-tree trên `e.event_id BIGINT` không tự áp dụng trực tiếp cho biểu thức `e.event_id::text`**.

Planner có thể chọn quét `events`, hash join hoặc dùng index phía `raw_event_id` tùy kích thước và thứ tự join. Không kết luận toàn bộ query “không có index nào có thể dùng”; vấn đề là **đường tra cứu qua index BIGINT của e** đã bị làm khó.

### 16.3. JOIN ép TEXT thành BIGINT

```sql
EXPLAIN
SELECT e.event_id, l.link_id
FROM idx_cast_lab.events AS e
JOIN idx_cast_lab.legacy_event_links AS l
  ON e.event_id = l.raw_event_id::bigint;
```

Với dữ liệu demo đều là chuỗi số hợp lệ, hướng này có thể cho phép lookup trực tiếp vào `events.event_id` từ giá trị sau cast của bảng staging.

**Nhưng:** nếu `raw_event_id` chứa `'abc'`, số tràn miền BIGINT, khoảng trắng/định dạng không phù hợp hoặc giá trị không chuẩn, cast có thể lỗi. Không đem giải pháp này áp production mà chưa kiểm tra dữ liệu.

### 16.4. Thiết kế dài hạn: đồng nhất kiểu khóa

Giải pháp bền vững hơn là dùng cột typed:

```sql
CREATE TABLE idx_cast_lab.typed_event_links (
    link_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL
        REFERENCES idx_cast_lab.events(event_id),
    link_type TEXT NOT NULL
);

-- Chỉ dùng được vì dữ liệu demo đã được tạo từ event_id hợp lệ.
INSERT INTO idx_cast_lab.typed_event_links
    (event_id, link_type)
SELECT raw_event_id::bigint, link_type
FROM idx_cast_lab.legacy_event_links;

CREATE INDEX typed_event_links_event_id_idx
ON idx_cast_lab.typed_event_links (event_id);
```

Truy vấn JOIN giờ có kiểu nhất quán:

```sql
EXPLAIN
SELECT e.event_id, l.link_id
FROM idx_cast_lab.events AS e
JOIN idx_cast_lab.typed_event_links AS l
  ON e.event_id = l.event_id;
```

### 16.5. Migration thực tế cần kiểm tra gì?

Trước khi đổi một cột TEXT legacy sang BIGINT:

1. Giá trị nào không phải số nguyên hợp lệ?
2. Có số vượt phạm vi `BIGINT` không?
3. Có zero padding mang ý nghĩa nghiệp vụ (mã `'00042'` khác `'42'`) không?
4. Có `NULL` hoặc chuỗi rỗng không?
5. FK/constraint và index sẽ thay đổi ra sao?
6. Có ứng dụng/API nào còn mong string không?
7. Chạy migration online hay cần maintenance window?
8. Có kế hoạch rollback và dữ liệu đối chiếu không?

Nếu `'00042'` là **mã định danh chuỗi**, không nên ép thành số chỉ để làm JOIN. Cần lựa chọn kiểu theo **ngữ nghĩa dữ liệu**, không chỉ theo hiệu năng index.

---

## 17. Index nhiều cột: có thể dùng nhưng cột đầu quan trọng

Index nền:

```sql
CREATE INDEX events_tenant_time_idx
ON idx_cast_lab.events
    (tenant_id, event_time DESC, event_id DESC);
```

được tạo ở mục 3; đây là định nghĩa nhắc lại để phân tích.

### 17.1. Tenant equality + time range

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-02 00:00+00'
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

Đây là mẫu thuận lợi: equality trên key dẫn đầu, range trên key kế, thứ tự phù hợp.

### 17.2. Chỉ có time range

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-02 00:00+00';
```

Không có điều kiện `tenant_id`. Planner vẫn **có thể** xem xét index nhiều cột trong một số trường hợp, tùy phiên bản/các kỹ thuật truy cập, nhưng thường **không tận dụng hiệu quả** như khi đã cố định key dẫn đầu. Có thể cần index riêng trên `event_time` nếu workload chủ yếu truy vấn xuyên tenant.

Không khẳng định “không có điều kiện cột đầu thì index nhiều cột tuyệt đối không được dùng” trong mọi phiên bản PostgreSQL.

### 17.3. Ép kiểu ở key đầu gây hại rõ

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE tenant_id::text = '3'
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00';
```

Việc đổi `tenant_id` sang text làm key đầu không còn là phép so sánh trực tiếp như `tenant_id=3`. Query có thể mất lợi thế xác định phạm vi tenant nhanh chóng trong index nhiều cột.

**Sửa:**

```sql
WHERE tenant_id = 3::integer
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
```

### 17.4. B-tree order và range boundary

Với index `(tenant_id, event_time, event_id)`, range trên `event_time` có thể giới hạn vùng truy cập, còn `event_id` tiếp theo giúp thứ tự/giải quyết các hàng cùng timestamp. Tuy nhiên, điều kiện trên cột phía sau range **không tự có hiệu quả giới hạn scan ngang với equality ở các key đầu**.

Thiết kế thứ tự key phải theo workload có thật, không xếp cột tùy theo thứ tự xuất hiện trong SELECT.

---

## 18. Partial index và điều kiện suy ra predicate

Một index một phần chỉ chứa các hàng thỏa điều kiện được định nghĩa khi tạo.

```sql
CREATE INDEX events_queued_tenant_time_idx
ON idx_cast_lab.events (tenant_id, event_time)
WHERE state = 'queued';
```

### 18.1. Truy vấn có thể nằm trọn trong index

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE state = 'queued'
  AND tenant_id = 3
  AND event_time <
      TIMESTAMPTZ '2026-03-01 00:00+00';
```

Toàn bộ hàng query cần đều có `state='queued'`, nên về logic query suy ra predicate của partial index.

### 18.2. Truy vấn không suy ra

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE state IN ('queued', 'running');
```

Truy vấn còn cần hàng `running` nằm ngoài partial index. Index queued **không một mình bao phủ** kết quả.

### 18.3. Generic prepared plan và parameter trạng thái

```sql
PREPARE find_by_state(TEXT, INTEGER) AS
SELECT event_id
FROM idx_cast_lab.events
WHERE state = $1
  AND tenant_id = $2;
```

Nếu PostgreSQL phải tạo **generic plan** đúng cho mọi `$1`, nó không được mặc định `$1='queued'`. Một **custom plan** biết giá trị tham số có thể đưa ra lựa chọn khác.

Trong môi trường hỗ trợ `plan_cache_mode`:

```sql
SET plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE find_by_state('queued', 3);

SET plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE find_by_state('queued', 3);

RESET plan_cache_mode;
DEALLOCATE find_by_state;
```

**Đây là ví dụ đo plan**, không phải khuyến nghị ép `force_custom_plan` toàn ứng dụng. Một custom plan cũng có thể không dùng partial index nếu chi phí dự kiến không tốt.

### 18.4. Hợp đồng query chỉ dùng queued

Nếu endpoint nghiệp vụ thực sự **chỉ tìm queued**, giữ điều kiện trạng thái là hằng:

```sql
PREPARE find_queued(INTEGER) AS
SELECT event_id
FROM idx_cast_lab.events
WHERE state = 'queued'
  AND tenant_id = $1;
```

Query dễ chứng minh suy ra predicate ngay cả khi tenant được bind. Không hardcode queued nếu endpoint phải hỗ trợ cả running/done.

---

## 19. OR, IN, ANY, NOT và độ chọn lọc

### 19.1. IN thường phù hợp với equality lookup

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id IN (100, 101, 102);
```

B-tree primary key có cơ hội xử lý tập khóa nhỏ hiệu quả.

### 19.2. = ANY với mảng typed

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = ANY(ARRAY[100,101,102]::bigint[]);
```

`ANY` là một lựa chọn cho danh sách ID được truyền dưới dạng mảng; query vẫn có điều kiện trên `event_id`, không biến cột thành text. Hiệu quả còn phụ thuộc kích thước danh sách, phân bố và plan.

### 19.3. OR có thể dùng BitmapOr hoặc Seq Scan

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 100
   OR external_id =
      '00000000-0000-0000-0000-000000000200'::uuid;
```

Vì hai nhánh có index riêng, planner có thể kết hợp các kết quả hoặc dùng một đường truy cập khác.

```text
Bitmap Heap Scan
  -> BitmapOr
      -> Bitmap Index Scan on events_pkey
      -> Bitmap Index Scan on events_external_id_idx
```

Đây là **cây plan minh họa**, không cam kết output chính xác. Câu `OR` không mặc định phá tất cả index.

### 19.4. OR trên biểu thức được cast

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id::text = '100'
   OR external_id::text =
      '00000000-0000-0000-0000-000000000200';
```

Hai nhánh đều dùng expression TEXT trên các cột indexed bằng kiểu gốc. Kế hoạch có thể kém thuận lợi hơn đáng kể so với hai toán tử typed.

### 19.5. != và NOT IN

```sql
WHERE state <> 'done'
```

không mặc nhiên là lookup hẹp. Nếu nhiều hàng khác done, planner có thể phải đọc tỷ lệ lớn bảng. `NOT IN` còn có **ngữ nghĩa NULL** cần chú ý: nếu vế phải chứa NULL, kết quả có thể khác ý định.

Không đổi `NOT IN` thành `NOT EXISTS` chỉ vì muốn index; trước hết xác định semantics, NULL và cardinality.

### 19.6. LIKE prefix cùng OR

```sql
WHERE customer_email LIKE 'User1%'
   OR customer_email LIKE 'User2%'
```

Planner có thể xét các đường truy cập pattern index phù hợp và kết hợp chúng. Nếu một nhánh là `LIKE '%42%'`, nhánh đó có thể khiến B-tree prefix index không đủ khả năng bao phủ hiệu quả toàn query.

---

## 20. Prepared statements: kiểu tham số phải có chủ đích

### 20.1. PREPARE kiểu BIGINT

```sql
PREPARE get_event(BIGINT) AS
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = $1;

EXPLAIN EXECUTE get_event(1000);
DEALLOCATE get_event;
```

`$1` được khai báo `BIGINT`. Điều kiện giữ cột nguyên dạng.

### 20.2. PREPARE kiểu TEXT và cast đúng bên

Nếu API nhận ID dạng TEXT nhưng chưa đổi thiết kế client, có thể:

```sql
PREPARE get_event_from_text(TEXT) AS
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = $1::bigint;

EXPLAIN EXECUTE get_event_from_text('1000');
DEALLOCATE get_event_from_text;
```

Cast được áp dụng cho **tham số**, không phải cột `event_id`. Tuy nhiên, dữ liệu text không hợp lệ vẫn gây lỗi khi cast.

**Giải pháp tốt hơn:** ứng dụng xác thực và truyền ID đúng kiểu ngay từ tầng API/driver.

### 20.3. Không chuẩn hóa bằng CAST(event_id AS text)

```sql
-- Không ưu tiên:
-- WHERE event_id::text = $1
```

Đây là cách “sửa lỗi type mismatch” theo hướng đảo ngược: đổi hàng loạt giá trị cột indexed để phù hợp với loại đầu vào của client.

### 20.4. Khi nào typed param vẫn không đủ?

Nếu câu query có:

```sql
WHERE lower(customer_email) = $1::text
```

dù `$1` là text hợp lệ, vẫn cần index trên **`lower(customer_email)`** hoặc phương án thiết kế khác. Bind kiểu đúng **không tự loại bỏ** mọi hàm ở phía cột.

### 20.5. Generic plan không giống custom plan

Kể cả khi SQL không có cast gây hại, generic plan đôi khi không tận dụng được sự chọn lọc của một giá trị tham số cụ thể. Với workload phân bố lệch, planner có thể chọn đường khác nhau khi lập custom plan theo value.

Phân biệt:

- **Type issue:** kiểu/toán tử/index key không phù hợp.
- **Selectivity/plan cache issue:** query có thể dùng index, nhưng generic plan hoặc ước lượng chọn đường khác.

Đừng sửa type casting để “chữa” vấn đề plan cache khi nguyên nhân thật là phân bố dữ liệu.

---

## 21. Java/JDBC: bind đúng kiểu để giữ điều kiện indexable

### 21.1. Tìm BIGINT bằng setLong

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class EventRepository {
    public String findState(Connection connection, long eventId)
            throws SQLException {
        String sql = """
            SELECT state
            FROM idx_cast_lab.events
            WHERE event_id = ?
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, eventId);

            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getString("state") : null;
            }
        }
    }
}
```

Driver gửi tham số số phù hợp với `BIGINT`, không yêu cầu cast cột.

### 21.2. Parse input ngoài transaction database

Nếu API nhận chuỗi:

```java
public long parseEventId(String rawId) {
    try {
        return Long.parseLong(rawId);
    } catch (NumberFormatException e) {
        throw new IllegalArgumentException(
            "eventId phải là số nguyên 64-bit hợp lệ", e
        );
    }
}
```

Ứng dụng nên phân biệt lỗi đầu vào không hợp lệ với “ID hợp lệ nhưng không tồn tại”, và không đưa string tùy ý vào `WHERE event_id::text = ?`.

### 21.3. Tìm UUID

```java
import java.util.UUID;

UUID id = UUID.fromString(rawExternalId);
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT event_id FROM idx_cast_lab.events "
      + "WHERE external_id = ?")) {
    ps.setObject(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả theo hợp đồng ứng dụng.
    }
}
```

Tránh `external_id::text = ?` khi mục đích thật sự là so UUID.

### 21.4. Số thập phân chính xác

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("50.00");
ps.setBigDecimal(1, amount);
```

Giữ kiểu `NUMERIC` phù hợp với số tiền, không chuyển cột `amount::double precision` hoặc `amount::text` để khớp dữ liệu do client gửi.

### 21.5. Timestamp và khoảng ngày

Nên chuyển **ngày theo timezone nghiệp vụ** thành hai instant từ application, sau đó truyền hai cận typed.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.OffsetDateTime;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 2, 10);

ZonedDateTime startLocal = day.atStartOfDay(zone);
ZonedDateTime endLocal = day.plusDays(1).atStartOfDay(zone);

OffsetDateTime begin = startLocal.toOffsetDateTime();
OffsetDateTime end = endLocal.toOffsetDateTime();

String sql = """
    SELECT event_id, event_time
    FROM idx_cast_lab.events
    WHERE tenant_id = ?
      AND event_time >= ?
      AND event_time < ?
    ORDER BY event_time
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setObject(2, begin);
    ps.setObject(3, end);
    // ExecuteQuery và xử lý ResultSet.
}
```

Việc đổi local day thành hai cận độc lập xử lý tốt hơn các ngày DST ở vùng có DST so với giả định mọi ngày dài đúng 24 giờ.

**Lưu ý:** ví dụ JDBC dựa trên driver hỗ trợ `OffsetDateTime` trong bind `TIMESTAMPTZ`. Kiểm tra phiên bản driver/framework thực tế; với framework đã quản lý transaction/connection, tuân thủ boundary của framework.

### 21.6. Không ghép literal từ đầu vào người dùng

Tránh:

```java
// Không làm:
// String sql = "WHERE event_id = " + rawId;
```

Sử dụng `PreparedStatement` vừa tránh SQL injection vừa làm rõ kiểu dữ liệu. **Nhưng** chỉ parameterization không bảo đảm index được dùng; kiểu cột, kiểu parameter, biểu thức và plan vẫn quan trọng.

---

## 22. Expression index, index thông thường hay đổi schema?

Khi thấy một query chậm do cast, đừng vội tạo expression index cho từng câu. Hãy chọn giải pháp theo ý nghĩa dữ liệu.

| Tình huống | Cách ưu tiên |
|---|---|
| `id::text = '123'` nhưng ID thực sự là số | Đổi literal/parameter thành BIGINT và dùng index trên ID |
| `created_at::date = day` khi muốn lọc ngày | Dùng khoảng timestamp nửa mở, đúng timezone |
| `lower(email) = ...` thường xuyên và semantics case-insensitive | Expression index trên `lower(email)` hoặc chiến lược chuẩn hóa |
| `payload->>'category' = ...` truy cập thuộc tính thường xuyên | Expression index, cột typed hoặc thiết kế JSONB/index phù hợp |
| `LIKE '%term%'` thường xuyên | Trigram/full-text tùy ngữ nghĩa, không chỉ B-tree |
| JOIN khóa TEXT với khóa BIGINT | Chuẩn hóa schema/staging typed và validate dữ liệu |
| Bộ lọc theo trạng thái nóng ít hàng | Partial index đúng predicate |
| Truy vấn tenant + time + ORDER BY | Composite index đúng key order |
| Khoảng thời gian rất lớn, dữ liệu vật lý theo thứ tự | Cân nhắc BRIN/partitioning tùy workload |

### 22.1. Đổi query thường ít rủi ro hơn đổi schema

Nếu kết quả vẫn giống nhau với mọi hàng hợp lệ:

```sql
WHERE event_id = $1::bigint
```

thường dễ triển khai hơn tạo index mới trên biểu thức `event_id::text` và duy trì nó vĩnh viễn.

Tương tự, viết timestamp range thường giữ được index đã có mà không cần thêm expression index.

### 22.2. Khi nào expression index có lý?

Khi nghiệp vụ **thật sự cần giá trị đã biến đổi** và không có cách tương đương đơn giản để tìm trong khóa gốc:

```sql
WHERE lower(customer_email) = ...
```

hoặc:

```sql
WHERE payload ->> 'category' = ...
```

Index expression giúp database lưu trước giá trị cần tìm. Đánh đổi là chi phí ghi và không gian.

### 22.3. Khi nào đổi schema là giải pháp dài hạn?

Nếu hệ thống liên tục cast giữa TEXT và BIGINT trong JOIN trên hàng triệu dòng, đó có thể là dấu hiệu **mô hình dữ liệu đang sai kiểu**. Một migration chuẩn hóa khóa (với validation và backward compatibility) có thể tốt hơn một chùm expression index khắp nơi.

Không đổi kiểu TEXT sang số khi TEXT có ý nghĩa như mã có số 0 đầu, nhiều định dạng hoặc chứa ký tự chữ.

---

## 23. Thống kê và selectivity: dùng được index vẫn có thể Seq Scan

### 23.1. So truy vấn hẹp với truy vấn rộng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

so với:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM idx_cast_lab.events
WHERE amount >= 1;
```

Trong dữ liệu seed, gần như mọi hàng có `amount>=1`, nên Seq Scan có thể là phương án tốt, dù `amount` có B-tree.

### 23.2. Xem thống kê theo cột

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname = 'idx_cast_lab'
  AND tablename = 'events'
  AND attname IN ('state', 'tenant_id', 'amount', 'deleted_at');
```

Các thống kê giúp planner dự đoán tần suất và phân bố. Chúng là **ước lượng** và có thể cũ sau bulk changes.

### 23.3. Cập nhật thống kê

```sql
ANALYZE idx_cast_lab.events;
```

Lệnh `ANALYZE table` thu thập thống kê; nó khác `EXPLAIN ANALYZE SELECT` là **thực thi SELECT để đo**.

### 23.4. Nhiều cột tương quan

Nếu tenant, state và loại sự kiện có phân bố phụ thuộc nhau, planner có thể sai cardinality khi dùng thống kê từng cột. PostgreSQL hỗ trợ **extended statistics** trên một số loại phụ thuộc/MCV:

```sql
CREATE STATISTICS events_tenant_state_stats
    (dependencies, mcv)
ON tenant_id, state
FROM idx_cast_lab.events;

ANALYZE idx_cast_lab.events;
```

Không mặc định extended statistics chữa mọi JOIN hoặc biểu thức cast. Nó là công cụ khi các ước lượng thực tế có vấn đề.

### 23.5. Buffers và actual rows mới nói về chi phí thực

Plan:

```text
Seq Scan on events
  Filter: (event_id::text = '1000')
  Rows Removed by Filter: ...
```

là một dấu hiệu biểu thức phía cột khiến index key không được dùng trực tiếp. Nhưng để quyết định tối ưu có đáng, còn cần xem số hàng, thời gian, buffers và tần suất query trong ứng dụng.

---

## 24. Collation, operator class và khả năng dùng index

### 24.1. Collation không phải chỉ ảnh hưởng ORDER BY

Collation quyết định nhiều quy tắc so sánh/sắp xếp text. Với B-tree text index, thứ tự key và cách xử lý `LIKE` phụ thuộc collation và operator class.

```sql
SELECT
    current_setting('lc_collate') AS database_collate;
```

Đây là thông tin môi trường; query/column có thể dùng collation cụ thể khác, nên không suy rằng mọi cột text cùng semantics.

### 24.2. text_pattern_ops

```sql
CREATE INDEX events_email_pattern_idx
ON idx_cast_lab.events
    (customer_email text_pattern_ops);
```

Index được tạo ở mục 11; đây là lời nhắc định nghĩa. Operator class trên dùng cho các điều kiện pattern/prefix tương ứng.

Không lấy pattern index làm bằng chứng mọi so sánh ordering theo locale sẽ được tối ưu như một index text mặc định. Các opclass có mục tiêu khác nhau.

### 24.3. COLLATE trên cột có thể thay biểu thức truy vấn

```sql
-- Ví dụ query thay collation ở biểu thức:
-- WHERE customer_email COLLATE "C" = 'User42@Example.test'
```

Nếu index được tạo theo collation khác, PostgreSQL có thể không dùng được nó cho một số thao tác yêu cầu thứ tự/collation tương ứng. Với truy vấn văn bản phức tạp, cần kiểm tra **collation của index, collation của expression và EXPLAIN**.

### 24.4. CITEXT và nondeterministic collations

`citext` là một extension cung cấp kiểu text không phân biệt hoa/thường theo semantics riêng. Nondeterministic collations cũng có các khả năng riêng tùy phiên bản PostgreSQL. Chúng **không phải lựa chọn thay thế hoàn toàn tương đương** cho `lower(text)` trong mọi ứng dụng.

Muốn chuyển kiểu hoặc collation của cột có dữ liệu thật cần đánh giá uniqueness, khả năng truy vấn pattern, Unicode, migration và hiệu năng trước.

---

## 25. Dọn dẹp và tổ chức thử nghiệm an toàn

### 25.1. Không xóa schema dùng chung

Tài liệu giả định `idx_cast_lab` được tạo riêng cho buổi thực hành. Chỉ khi xác nhận không ai dùng và bạn có quyền:

```sql
-- Chỉ dùng ở database lab sau khi xác nhận phạm vi:
-- DROP SCHEMA idx_cast_lab CASCADE;
```

Không chạy `DROP SCHEMA ... CASCADE` trên môi trường dùng chung nếu có thể làm mất đối tượng của người khác.

### 25.2. Không cần ép mọi plan dùng index

```sql
-- Thử nghiệm chẩn đoán trên session riêng, không bật lâu dài:
SET enable_seqscan = off;

EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 1000;

RESET enable_seqscan;
```

`enable_seqscan=off` chỉ làm phương án Seq Scan bất lợi theo cost model, không cấm tuyệt đối mọi trường hợp. Đó là cách khám phá phương án, **không phải phương pháp tối ưu production**.

### 25.3. Lưu kế hoạch ở môi trường thực tế

Để phân tích một query chậm, ghi nhận:

- PostgreSQL version.
- SQL và kiểu parameter.
- Role/tenant/RLS nếu có.
- DDL các index liên quan.
- Plan từ `EXPLAIN`.
- Plan thực từ `EXPLAIN (ANALYZE, BUFFERS)` nếu việc chạy là an toàn.
- Số rows, loops, buffers, thời gian và tần suất query.
- Phân bố dữ liệu, lịch sử `ANALYZE` và trạng thái cache.

Không đưa nguyên dữ liệu cá nhân hoặc SQL chứa bí mật vào log chia sẻ công khai.

---

## 26. Những sai lầm thường gặp

**1. “Có index trên cột là mọi WHERE nhắc tới cột đều dùng index.”** Sai. Biểu thức, toán tử, opclass và cost quan trọng.

**2. “Hễ xuất hiện CAST là mất index.”** Quá tuyệt đối. Một số cast tương thích và toán tử chéo kiểu vẫn có index support.

**3. “Ép cột BIGINT thành TEXT giống ép literal sang BIGINT.”** Không. Hai thao tác có đường truy cập và semantics khác.

**4. “`event_id = '100'` luôn chuyển cột thành TEXT.”** Sai. Literal string chưa kiểu có thể được suy ra kiểu BIGINT từ ngữ cảnh.

**5. “Chỉ cần truyền mọi parameter dạng String là tốt nhất.”** Không. Dùng bind types đúng với schema và nghiệp vụ.

**6. “`event_id::text='abc'` là cách xử lý input ID không hợp lệ.”** Sai thiết kế. Xác thực đầu vào và dùng kiểu số phù hợp.

**7. “`amount::double precision` giống `NUMERIC` cho mọi số tiền.”** Sai. Có thể mất chính xác và thay semantics.

**8. “`amount+5=55` chắc chắn được planner biến thành `amount=50`.”** Không được bảo đảm cho mọi biểu thức.

**9. “`event_time::date=...` luôn nhanh vì ngày nhỏ hơn timestamp.”** Không. Đó là cast trên cột và có thể không dùng index thường.

**10. “`TIMESTAMPTZ::date` không phụ thuộc TimeZone.”** Sai. Ngày local phụ thuộc session timezone.

**11. “Một ngày luôn dài 24 giờ ở mọi timezone.”** Sai trong vùng có DST.

**12. “BETWEEN 00:00 và 23:59:59 bao phủ mọi timestamp của ngày.”** Có thể bỏ sót phần thập phân giây.

**13. “`date_trunc()` và `to_char()` trên cột không ảnh hưởng đường truy cập.”** Có thể cản trở B-tree trên cột gốc.

**14. “Tạo expression index trên TIMESTAMPTZ::date luôn hợp lệ.”** Không. Biểu thức phụ thuộc timezone session không immutable.

**15. “Index trên email gốc phục vụ mọi `lower(email)`.”** Không mặc định. Có thể cần expression index.

**16. “Expression index lower(email) tự biến query email=... thành case-insensitive.”** Không. SQL predicate quyết định semantics.

**17. “LIKE '%term%' dùng B-tree prefix index tốt như LIKE 'term%'.”** Không. Wildcard đầu mất tiền tố cố định.

**18. “LIKE 'prefix%' luôn có index ở mọi collation.”** Không. Cần xét pattern opclass/collation và plan.

**19. “ILIKE được mọi B-tree xử lý y hệt LIKE.”** Không đúng tổng quát.

**20. “pg_trgm hoàn toàn miễn phí.”** Không. Extension/index có chi phí và giới hạn pattern.

**21. “COALESCE(deleted_at,sentinel) luôn giống IS NULL.”** Không nếu sentinel có thể là giá trị thật.

**22. “IS NULL không thể dùng B-tree.”** Sai. PostgreSQL có thể index và tìm NULL.

**23. “Index trên JSONB tự tối ưu mọi phép ->> text equality.”** Không. Cần phân biệt GIN containment với B-tree expression.

**24. “Cast mọi JSONB value sang NUMERIC luôn an toàn.”** Không. Dữ liệu không chuyển được có thể gây lỗi.

**25. “JOIN BIGINT::TEXT với TEXT luôn tối ưu như JOIN BIGINT=BIGINT.”** Không. Có thể mất lookup qua index số của một phía.

**26. “Thay mọi mã TEXT bằng BIGINT là tối ưu đúng nghiệp vụ.”** Sai nếu mã có ký tự chữ/zero padding mang ý nghĩa.

**27. “Composite index dùng tốt mọi cột theo thứ tự bất kỳ.”** Không. Key dẫn đầu, equality/range và ORDER BY quan trọng.

**28. “Nếu query thiếu key đầu thì PostgreSQL tuyệt đối không bao giờ xem index nhiều cột.”** Quá tuyệt đối. Nhưng hiệu quả thường khác đáng kể.

**29. “Partial index trên queued bao phủ query queued hoặc running.”** Sai. Running nằm ngoài predicate.

**30. “`state=$1` trong generic plan luôn chứng minh state='queued'.”** Sai. `$1` có thể là trạng thái khác.

**31. “Custom plan chắc chắn chọn partial index.”** Không. Vẫn xét chi phí và thống kê.

**32. “OR luôn làm mất mọi index.”** Sai. PostgreSQL có thể dùng BitmapOr/kế hoạch khác.

**33. “NOT IN với NULL giống NOT EXISTS.”** Không mặc định. NULL ảnh hưởng logic SQL.

**34. “Index Scan luôn nhanh hơn Seq Scan.”** Không. Query lấy phần lớn bảng có thể quét tuần tự tốt hơn.

**35. “EXPLAIN có Index Cond là đủ khẳng định API nhanh.”** Không. Còn actual rows, heap, buffers, network và ứng dụng.

**36. “Bật enable_seqscan=off là cách sửa planner.”** Không. Chủ yếu là công cụ chẩn đoán; cần hiểu thống kê/index/query thật.

**37. “Để có index, nên cast cột đến cùng kiểu input thay vì sửa input.”** Thường ngược lại, khi kiểu cột đã đúng.

**38. “Một expression index trên hàm không immutable là ổn nếu developer biết hàm ‘thường không đổi’.”** Không. Cần tuân thủ tính bất biến thật.

**39. “Thêm index luôn không ảnh hưởng ghi.”** Sai. Index làm tăng storage, WAL và công việc duy trì.

**40. “Một plan trên bảng nhỏ đủ chứng minh mọi production workload.”** Không. Dữ liệu, phiên bản, tham số, cache, collation và concurrency đều có thể khác.

---

## 27. Bài tập thực hành có hướng dẫn đáp án

### Bài 1 — Phân biệt ép kiểu ở đâu

Hai điều kiện:

```sql
WHERE event_id::text = '1000'
WHERE event_id = '1000'::bigint
```

**Đáp án:** Câu thứ hai giữ cột `BIGINT` nguyên dạng và phù hợp hơn với B-tree khóa chính. Câu đầu biến cột thành expression TEXT không có index tương ứng trong lab.

### Bài 2 — Chuỗi literal không khai báo kiểu

```sql
WHERE event_id = '1000'
```

**Câu hỏi:** Có chắc planner ép `event_id` sang text?

**Đáp án:** Không. Literal `'1000'` ban đầu thường thuộc kiểu `unknown` và PostgreSQL có thể suy kiểu BIGINT từ phép so sánh.

### Bài 3 — Lọc NUMERIC đúng kiểu

**Yêu cầu:** tìm các event có amount bằng 50.00, tận dụng index trên amount.

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE amount = 50.00::numeric;
```

Không đổi cột thành text/double chỉ để so sánh literal.

### Bài 4 — Cast ở cột tiền

```sql
WHERE amount::text = '50.00'
```

**Đáp án:** Điều kiện dùng biểu thức text thay vì numeric key; nên `WHERE amount=50.00::numeric` nếu nghiệp vụ là so sánh số.

### Bài 5 — Lọc ngày UTC

**Yêu cầu:** lấy toàn bộ ngày 10/02/2026 UTC, không dùng `event_time::date`.

```sql
WHERE event_time >= TIMESTAMPTZ '2026-02-10 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-11 00:00+00'
```

### Bài 6 — Lọc ngày tại Việt Nam

**Đáp án:**

```sql
WHERE event_time >=
    (TIMESTAMP '2026-02-10 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND event_time <
    (TIMESTAMP '2026-02-11 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
```

Đổi hai cận local riêng rẽ để biểu diễn ngày lịch theo vùng giờ chính xác.

### Bài 7 — Vì sao TIMESTAMPTZ::DATE cần cẩn thận?

**Đáp án:** Nó phụ thuộc `TimeZone` session và đặt conversion ở phía cột. Nếu muốn truy vấn một ngày local, hãy dựng khoảng timestamp với timezone xác định.

### Bài 8 — Không thể tạo index trên mọi hàm

```sql
-- CREATE INDEX ... ON ... ((event_time::date));
```

với `event_time TIMESTAMPTZ`.

**Đáp án:** Conversion từ timestamptz sang date phụ thuộc timezone, không thỏa yêu cầu immutability của index expression thông thường.

### Bài 9 — LOWER(email)

**Yêu cầu:** tạo index phù hợp query không phân biệt chữ hoa/thường.

```sql
CREATE INDEX email_lower_exercise_idx
ON idx_cast_lab.events (lower(customer_email));
```

Lab đã có `events_lower_email_idx` tương tự, nên đây là cú pháp minh họa; không giữ index trùng trong production.

### Bài 10 — LIKE tiền tố

**Câu hỏi:** `LIKE 'User1%'` và `LIKE '%User1%'` khác nhau thế nào về B-tree?

**Đáp án:** Query đầu có prefix cố định, có thể dùng B-tree/pattern opclass khi phù hợp; query sau có wildcard đầu nên không có prefix range đơn giản.

### Bài 11 — ILIKE chứa chuỗi

**Yêu cầu:** đề xuất index cho `ILIKE '%user42%'`.

**Đáp án:** Cân nhắc `pg_trgm` với GIN/GiST trigram index và đo workload. Không coi B-tree text bình thường là giải pháp mặc định.

### Bài 12 — IS NULL và COALESCE

**Yêu cầu:** lấy hàng live theo `deleted_at`.

```sql
WHERE deleted_at IS NULL
```

**Đáp án:** Điều kiện tường minh, tránh sentinel giả trong `COALESCE`. Có thể dùng partial index `WHERE deleted_at IS NULL`.

### Bài 13 — UUID

**Yêu cầu:** so `external_id UUID` với ID do client gửi.

**Đáp án:** Parse hoặc bind đúng UUID ở phía client; trong SQL dùng `external_id = ?` với param typed, hoặc literal `'...'::uuid`. Không ưu tiên `external_id::text = ?`.

### Bài 14 — JSONB

**Câu hỏi:** Query `payload->>'category'='audit'` có chắc được GIN trên payload phục vụ như B-tree text không?

**Đáp án:** Không. Đó là expression text equality. Cân nhắc B-tree expression index hoặc viết query containment `payload @> '{"category":"audit"}'::jsonb` và dùng GIN phù hợp.

### Bài 15 — JOIN khóa khác kiểu

```sql
ON e.event_id::text = l.raw_event_id
```

**Đáp án:** Có thể cản index trên `e.event_id BIGINT` vì vế e bị đổi sang expression text. Với dữ liệu legacy hợp lệ, có thể cast phía staging sang bigint; lâu dài nên chuẩn hóa kiểu khóa.

### Bài 16 — Dữ liệu legacy không phải số

**Câu hỏi:** Có nên dùng `raw_event_id::bigint` ngay với dữ liệu import chưa xác thực?

**Đáp án:** Không. Có thể lỗi với ký tự/giá trị vượt phạm vi; trước hết đánh giá ngữ nghĩa và chuẩn hóa/validate dữ liệu.

### Bài 17 — Composite index

Index:

```sql
ON events (tenant_id, event_time DESC, event_id DESC)
```

**Yêu cầu:** viết một query có thể tận dụng tốt.

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-02 00:00+00'
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

### Bài 18 — Composite index và CAST key đầu

```sql
WHERE tenant_id::text = '3'
  AND event_time > TIMESTAMPTZ '2026-02-01 00:00+00'
```

**Đáp án:** Cast ở key đầu khiến điều kiện tenant khó tận dụng index hơn. Nếu tenant là số, viết `tenant_id=3::integer`.

### Bài 19 — Partial index queued

Index:

```sql
ON events (tenant_id, event_time)
WHERE state='queued'
```

**Câu hỏi:** Query `WHERE state IN ('queued','running')` suy ra predicate không?

**Đáp án:** Không; query còn cần running. Partial index queued không tự bao phủ toàn bộ tập kết quả.

### Bài 20 — Prepared statement generic

**Câu hỏi:** `WHERE state=$1` có luôn cho generic plan dùng partial index `state='queued'` không?

**Đáp án:** Không. Generic plan phải hợp lệ khi `$1` là done/running. Custom plan với giá trị queued có thể xét index nhưng vẫn phụ thuộc cost.

### Bài 21 — OR và Index

```sql
WHERE event_id = 100
   OR external_id =
       '00000000-0000-0000-0000-000000000200'::uuid
```

**Đáp án:** PostgreSQL có thể dùng BitmapOr giữa hai index hoặc phương án khác; `OR` không mặc nhiên vô hiệu hóa mọi index.

### Bài 22 — So sánh selectivity

**Câu hỏi:** Query `amount>=1` trả gần như toàn bảng vẫn dùng index amount không?

**Đáp án:** Có thể dùng về mặt kỹ thuật, nhưng planner có thể chọn Seq Scan vì phần lớn hàng phù hợp và index access/heap fetch đắt hơn.

### Bài 23 — EXPLAIN vs EXPLAIN ANALYZE

**Câu hỏi:** Có an toàn khi chạy `EXPLAIN ANALYZE DELETE` để “chỉ xem plan” không?

**Đáp án:** Không. Nó thực thi DELETE. Dùng `EXPLAIN DELETE` không ANALYZE để xem estimated plan.

### Bài 24 — Dùng EXPLAIN để kiểm tra CAST

**Yêu cầu:** so plan của hai câu:

```sql
EXPLAIN
SELECT event_id FROM idx_cast_lab.events
WHERE event_id = 1000;

EXPLAIN
SELECT event_id FROM idx_cast_lab.events
WHERE event_id::text = '1000';
```

**Đáp án:** Quan sát `Index Cond` và `Filter`, đường truy cập, rows ước lượng. Không mặc định chúng dùng cùng B-tree.

### Bài 25 — Chọn đúng giải pháp

**Tình huống:** ứng dụng luôn cần tìm email không phân biệt chữ hoa/thường nhưng bảng lưu email có chữ hoa.

**Đáp án:** Có thể dùng `lower(customer_email)` với expression index, hoặc chuẩn hóa lưu trữ/kiểu/collation có hợp đồng rõ. Không dùng `WHERE customer_email = ...` rồi tuyên bố tìm không phân biệt hoa/thường nếu database semantics không như vậy.

### Bài 26 — Hiệu năng và semantics

**Câu hỏi:** Vì muốn dùng index, có thể thay `amount::text='50.00'` thành `amount=50` mà không xác minh yêu cầu không?

**Đáp án:** Phải xác minh semantics. Nếu nghiệp vụ thật sự tìm **giá trị số 50**, sửa là phù hợp; nếu đang tìm biểu diễn text đặc thù, hai điều kiện có thể không hoàn toàn tương đương. Tối ưu không được âm thầm đổi kết quả nghiệp vụ.

---

## 28. Checklist tối ưu điều kiện để dùng chỉ mục

### Trước khi sửa SQL

1. **Định nghĩa mục tiêu:** query đang tìm theo giá trị số, text, ngày địa phương hay timestamp tuyệt đối?
2. **Xem kiểu cột:** `BIGINT`, `TEXT`, `UUID`, `NUMERIC`, `TIMESTAMPTZ`, `JSONB`?
3. **Xem kiểu parameter:** JDBC/ORM bind kiểu nào? Có chuỗi input bị hiểu nhầm là type của cột không?
4. **Xem index thật:** key, expression, opclass, collation, partial predicate và thứ tự key.
5. **Xem operator:** B-tree có hỗ trợ toán tử và kiểu so sánh đó không?
6. **Tìm hàm ở phía cột:** `::text`, `::date`, `lower()`, `COALESCE`, `date_trunc`, `to_char`, phép số học?
7. **Không áp quy tắc máy móc:** một số cast/operator chéo kiểu vẫn dùng được index.

### Khi viết lại

8. **Ưu tiên cột nguyên dạng:** cast đúng literal/parameter nếu giữ được semantics.
9. **Lọc thời gian bằng hai cận:** `>= begin` và `< end`, timezone được xác định.
10. **Không bỏ sót timestamp fractional seconds:** tránh `23:59:59`.
11. **Giữ quy tắc NULL:** `IS NULL`, `IS NOT NULL`, đừng dùng sentinel tùy tiện.
12. **Đúng semantics chuỗi:** case-sensitive, case-insensitive, collation, prefix hay contains?
13. **LIKE có prefix không:** cân nhắc `text_pattern_ops` hoặc trigram đúng loại.
14. **Giữ type số tiền:** tránh chuyển NUMERIC sang floating point vô lý.
15. **JOIN đúng kiểu khóa:** đừng để một phía phải cast mọi hàng nếu có thể chuẩn hóa schema.
16. **Composite index:** lọc theo key dẫn đầu, range và ORDER BY phù hợp.
17. **Partial index:** query phải suy ra predicate; xem prepared generic/custom plan.
18. **Expression index:** chỉ dùng khi biểu thức không thể bỏ và function thực sự immutable.

### Khi đo và triển khai

19. **So EXPLAIN thực tế:** `Index Cond`, `Filter`, row estimates, sort/heap fetch.
20. **Dùng ANALYZE cho SELECT an toàn:** đo actual rows, buffers và thời gian.
21. **Không chạy EXPLAIN ANALYZE DML tùy tiện:** nó thực thi ghi thật.
22. **Tính selectivity:** index có thể dùng mà planner vẫn chọn Seq Scan hợp lý.
23. **Cập nhật thống kê:** `ANALYZE` và extended statistics khi cần.
24. **Đo trước/sau nhiều lần:** kiểm soát cache, dữ liệu, params và concurrency.
25. **Kiểm tra chi phí ghi:** mỗi index mới ảnh hưởng INSERT/UPDATE/DELETE.
26. **Đo dưới role thật:** RLS và collation/settings có thể làm plan khác.
27. **Không sửa lỗi bằng ép cấu hình toàn server:** tránh `enable_seqscan=off` thường trực.
28. **Ghi nhận thay đổi và hậu kiểm:** đúng dữ liệu, tốc độ, kích thước index và khả năng rollback.

---

## 29. Tổng kết

**Một điều kiện có thể dùng chỉ mục khi toán tử, kiểu dữ liệu và biểu thức trong query phù hợp với cấu trúc mà index lưu trữ; sau đó PostgreSQL planner mới quyết định có chọn index hay không.**

Những nguyên tắc quan trọng nhất:

- **Đừng biến cột đã index thành biểu thức khác nếu không cần thiết**: `event_id::text`, `amount::text`, `event_time::date` hoặc phép toán quanh cột có thể làm khó đường truy cập B-tree gốc.
- **Ưu tiên giá trị/parameter đúng kiểu**: `event_id=$1::bigint`, `amount=$1::numeric`, `external_id=$1::uuid`; với JDBC hãy bind `long`, `BigDecimal` và `UUID` tương ứng.
- **Không phải mọi CAST đều mất index**: PostgreSQL hỗ trợ một số ép kiểu tương thích và toán tử chéo kiểu; quyết định dựa trên opclass/family và `EXPLAIN`.
- **Dùng khoảng timestamp nửa mở thay cho biến đổi timestamp thành ngày**, và xác định múi giờ nghiệp vụ để tránh chọn sai tập hàng.
- **Khi cần tìm theo giá trị đã biến đổi**, cân nhắc expression index (`lower(email)`, trích thuộc tính JSONB) hoặc chuẩn hóa schema, nhưng nhớ chi phí ghi.
- **Chuỗi là bài toán riêng**: prefix `LIKE`, `ILIKE`, collation, pattern opclass và tìm chứa chuỗi bằng trigram không hoàn toàn tương đương.
- **Index nhiều cột và partial index phụ thuộc cấu trúc điều kiện**: key order, predicate implication, prepared generic/custom plan và thống kê.
- **Có đường index không có nghĩa chắc chắn được dùng**: Seq Scan vẫn hợp lý nếu query lấy phần lớn bảng, và một lần `EXPLAIN` không đại diện mọi tham số/workload.

**Câu hỏi cần tự đặt trước mỗi tối ưu:** “Điều kiện đang so sánh **giá trị cột được index** hay **kết quả một phép chuyển đổi trên cột**? Nếu chuyển đổi là bắt buộc, index nào thực sự lưu biểu thức đó? Nếu không bắt buộc, có thể chuyển giá trị ở phía input về đúng kiểu và giữ nguyên cột không?”

### Tài liệu PostgreSQL chính thức

- [Indexes — tổng quan](https://www.postgresql.org/docs/current/indexes.html).
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html).
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html).
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html).
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html).
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/indexes-opclass.html).
- [Indexes and Collations](https://www.postgresql.org/docs/current/indexes-collations.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) và [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [Type Conversion](https://www.postgresql.org/docs/current/typeconv.html).
- [Data Type Formatting Functions](https://www.postgresql.org/docs/current/functions-formatting.html).
- [Date/Time Functions and Operators](https://www.postgresql.org/docs/current/functions-datetime.html).
- [Pattern Matching](https://www.postgresql.org/docs/current/functions-matching.html).
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html).
- [PREPARE — generic/custom plans](https://www.postgresql.org/docs/current/sql-prepare.html).
