# Chỉ mục GIN, chỉ mục biểu thức và operator class cho jsonb trong PostgreSQL

Một cột `jsonb` có thể chứa tài liệu rất linh hoạt: thuộc tính người dùng, các nhãn (*tags*), tập quyền, danh sách sản phẩm, số tiền, các cờ trạng thái và những đối tượng lồng nhau. Sự linh hoạt ấy khiến một truy vấn kiểu:

```sql
SELECT event_id
FROM audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

khó xử lý hiệu quả nếu PostgreSQL phải đọc và phân tích từng JSON document của hàng triệu bản ghi. **GIN index** giúp tìm những hàng chứa khóa/giá trị cần thiết mà không nhất thiết quét mọi tài liệu. Nhưng không có một chỉ mục JSON duy nhất tối ưu cho mọi phép truy vấn:

```sql
-- Containment: tìm tài liệu có cặp đường dẫn/giá trị
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb

-- Key existence: khóa có xuất hiện ở mức trên cùng?
WHERE payload ? 'actor'

-- Array membership: nhãn "urgent" ở mảng con
WHERE payload -> 'labels' ? 'urgent'

-- Equality trên giá trị text trích xuất
WHERE payload #>> '{actor,id}' = '42'

-- Khoảng số
WHERE (payload ->> 'amount')::numeric >= 100
```

Các điều kiện trên có **toán tử, kiểu kết quả và cấu trúc biểu thức khác nhau**. Chỉ mục `GIN (payload)`, `GIN (payload jsonb_path_ops)`, `GIN ((payload->'labels'))` và `B-tree ((payload#>>'{actor,id}'))` có phạm vi sử dụng khác nhau.

Bài thuộc chương **JSON và mảng** trong module *Database Engine Relational PostgreSQL*, đi sâu vào:

- GIN (*Generalized Inverted Index*) trên `jsonb`.
- Hai operator class quan trọng: **`jsonb_ops`** (mặc định) và **`jsonb_path_ops`**.
- Những toán tử `@>`, `?`, `?|`, `?&`, `@?`, `@@`, cùng giới hạn với `=`, `->` và `->>`.
- **Chỉ mục biểu thức** cho thuộc tính/mảng lồng nhau và so sánh dạng text/số.
- Kết hợp GIN với B-tree, partial index, điều kiện tenant, sorting và pagination.
- Đọc `EXPLAIN`, đánh giá thống kê, chi phí cập nhật GIN, pending list và vận hành index trên bảng lớn.
- Cách thiết kế JSONB phù hợp kiểu dữ liệu, xử lý `NULL`, tham số SQL/JDBC và bài tập thực hành.

> **Phạm vi an toàn:** Ví dụ dùng schema riêng `jsonb_index_lab` trên database thực hành, không tác động bảng nghiệp vụ. `EXPLAIN (ANALYZE)` thực sự chạy câu lệnh; các ví dụ có `ANALYZE` ở đây chỉ dùng SELECT thông thường. Không thử `EXPLAIN ANALYZE DELETE/UPDATE` trên hệ thống thật để “xem trước”.

---

## 1. JSON, JSONB và lý do cần chỉ mục ngược

### 1.1. JSONB lưu tài liệu đã được phân tích thành dạng nhị phân

PostgreSQL cung cấp hai kiểu dữ liệu JSON phổ biến:

| Kiểu | Khía cạnh đáng chú ý |
|---|---|
| `json` | Giữ văn bản JSON đầu vào, bao gồm những khác biệt định dạng nhất định |
| `jsonb` | Lưu dạng nhị phân đã xử lý, hỗ trợ nhiều toán tử và index hơn |

`jsonb` không giữ nguyên mọi chi tiết văn bản ban đầu như thứ tự khóa hoặc các khóa trùng lặp. Trong ứng dụng cần truy vấn cấu trúc JSON thường xuyên, `jsonb` thường phù hợp hơn `json`.

Tuy nhiên, bản thân việc dùng `jsonb` **không tự động tạo chỉ mục cho các thuộc tính trong nó**.

### 1.2. Ví dụ một JSON document

```json
{
  "actor": {
    "id": "42",
    "team": "risk"
  },
  "labels": ["urgent", "review"],
  "severity": "high",
  "amount": 150.50,
  "flags": {
    "approved": false
  }
}
```

Một câu `WHERE payload @> '{"severity":"high"}'` phải tìm các row có phần dữ liệu tương ứng. Nếu không có đường truy cập phù hợp, PostgreSQL có thể phải đọc nhiều row và kiểm tra document của chúng.

### 1.3. GIN đảo chiều từ “hàng → giá trị” thành “giá trị → hàng”

Hình dung một inverted index:

```text
Tài liệu nguồn:

  row #11 -> actor.id=42, labels=[urgent, review]
  row #12 -> actor.id=18, labels=[normal]
  row #13 -> actor.id=42, labels=[review]

GIN (khái niệm):

  entry cho actor/id/42 ----> row #11, row #13
  entry cho label urgent ---> row #11
  entry cho label review ---> row #11, row #13
```

Đây là **sơ đồ tư duy**, không phải mô tả chính xác cách mỗi operator class mã hóa key/value ở mức byte. Đặc biệt `jsonb_ops` và `jsonb_path_ops` lưu các mục index khác nhau.

### 1.4. Không nhầm GIN với B-tree

- **B-tree** tổ chức các key theo thứ tự để tìm equality, range và có thể hỗ trợ `ORDER BY`.
- **GIN** có nhiều index entries trỏ tới cùng một row, phù hợp truy vấn **thành phần xuất hiện bên trong giá trị phức hợp**, ví dụ JSONB, SQL arrays hoặc full-text.
- GIN `jsonb` **không** mặc nhiên cho phép trả hàng theo `created_at DESC` như B-tree trên `created_at`.

Nếu một API vừa lọc JSON vừa cần sắp theo thời gian, có thể phải phối hợp GIN với B-tree, một kế hoạch bitmap/sort hoặc một cách thiết kế truy vấn khác.

---

## 2. Sáu nhóm toán tử JSONB cần phân biệt

### 2.1. Containment với @>

```sql
SELECT '{"actor":{"id":"42","team":"risk"},"severity":"high"}'::jsonb
       @> '{"actor":{"id":"42"}}'::jsonb
       AS contains_actor_id;
```

Kết quả là `true`. Toán tử `@>` hỏi **tài liệu bên trái có chứa cấu trúc/giá trị bên phải theo ngữ nghĩa JSONB containment không?**

Ví dụ:

```sql
SELECT '["urgent","review"]'::jsonb
       @> '["urgent"]'::jsonb AS contains_urgent;
```

Mảng bên trái chứa giá trị yêu cầu nên kết quả `true`.

### 2.2. Key existence với ?

```sql
SELECT '{"actor":{"id":"42"}}'::jsonb ? 'actor'
       AS has_actor;

SELECT '{"actor":{"id":"42"}}'::jsonb ? 'id'
       AS has_top_level_id;
```

Kết quả:

```text
has_actor       = true
has_top_level_id = false
```

**`?` kiểm tra ở mức trên cùng của giá trị JSONB đang xét**, không tự đệ quy xuống mọi object con. Nếu bên trái là một JSONB array chứa các chuỗi, toán tử cũng có thể kiểm tra sự xuất hiện của phần tử chuỗi ở mức array đó.

### 2.3. Any-key existence với ?|

```sql
SELECT '{"severity":"high","labels":[]}'::jsonb
       ?| ARRAY['severity', 'priority']
       AS has_any_key;
```

`?|` trả `true` nếu **ít nhất một** chuỗi trong SQL `text[]` được tìm thấy ở cấp JSONB đang xét.

### 2.4. All-keys existence với ?&

```sql
SELECT '{"severity":"high","labels":[]}'::jsonb
       ?& ARRAY['severity', 'labels']
       AS has_all_keys;
```

`?&` trả `true` khi **mọi** chuỗi được cung cấp đều tồn tại ở mức được kiểm tra.

### 2.5. JSONPath existence với @?

```sql
SELECT '{"actor":{"id":"42"}}'::jsonb
       @? '$.actor.id ? (@ == "42")'
       AS path_has_id_42;
```

`@?` kiểm tra JSONPath có trả ít nhất một item phù hợp không. PostgreSQL hỗ trợ JSONPath từ phiên bản 12; các biểu thức path, strict/lax mode và khả năng tối ưu hóa có quy tắc riêng.

### 2.6. JSONPath predicate với @@

```sql
SELECT '{"amount":150.5}'::jsonb
       @@ '$.amount > 100'
       AS amount_above_100;
```

`@@` đánh giá một **JSONPath predicate**. Đừng coi `@?` và `@@` là cùng một cú pháp khác tên: kiểu kết quả và cách viết JSONPath có khác biệt.

### 2.7. Bảng tổng hợp

| Toán tử | Ý nghĩa chính | Ví dụ |
|---|---|---|
| `@>` | JSONB bên trái chứa JSONB bên phải | `payload @> '{"severity":"high"}'::jsonb` |
| `?` | Có key/chuỗi cấp trên cùng | `payload ? 'actor'` |
| `?|` | Có ít nhất một key/chuỗi trong mảng | `payload ?| ARRAY['actor','labels']` |
| `?&` | Có tất cả key/chuỗi trong mảng | `payload ?& ARRAY['actor','labels']` |
| `@?` | JSONPath trả item phù hợp | `payload @? '$.labels[*] ? (@ == "urgent")'` |
| `@@` | JSONPath predicate check | `payload @@ '$.amount > 100'` |

**Quan trọng:** khả năng hỗ trợ index của một toán tử tùy **operator class, biểu thức phía trái và dạng JSONPath cụ thể**, không chỉ việc cột được định nghĩa `jsonb`.

---

## 3. Phòng thực hành độc lập: audit_events

### 3.1. Xác minh môi trường

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Bạn cần quyền tạo schema, bảng và index trong một database thử nghiệm. Nếu schema `jsonb_index_lab` đã thuộc buổi lab khác, không xóa nó; chọn database riêng khác.

### 3.2. Tạo bảng

```sql
CREATE SCHEMA jsonb_index_lab;

CREATE TABLE jsonb_index_lab.audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('security', 'billing', 'activity')),
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

Cột `payload` được yêu cầu chứa JSON **object** để các query có ý nghĩa nhất quán. CHECK chỉ xác minh kiểu object ở cấp trên cùng; nó **không** bảo đảm tất cả object đều có `actor.id`, `labels` hoặc `amount` đúng kiểu.

### 3.3. Chèn các sự kiện dễ quan sát

```sql
INSERT INTO jsonb_index_lab.audit_events
    (tenant_id, event_type, created_at, payload)
VALUES
(
    3,
    'security',
    TIMESTAMPTZ '2026-11-01 08:00:00+00',
    '{
      "actor":{"id":"42","team":"risk"},
      "labels":["urgent","review"],
      "severity":"high",
      "amount":150.50,
      "flags":{"approved":false}
    }'::jsonb
),
(
    3,
    'activity',
    TIMESTAMPTZ '2026-11-01 09:00:00+00',
    '{
      "actor":{"id":"42","team":"support"},
      "labels":["routine"],
      "severity":"normal",
      "amount":20,
      "flags":{"approved":true}
    }'::jsonb
),
(
    9,
    'billing',
    TIMESTAMPTZ '2026-11-01 10:00:00+00',
    '{
      "actor":{"id":"18","team":"billing"},
      "labels":["review"],
      "severity":"normal",
      "amount":250,
      "flags":{"approved":null}
    }'::jsonb
);
```

Những tài liệu nhỏ này giúp giải thích semantics. Để quan sát planner có cơ hội chọn index trong thực tế, ta nạp thêm dữ liệu.

### 3.4. Chèn 60.000 hàng có phân bố trạng thái

```sql
INSERT INTO jsonb_index_lab.audit_events
    (tenant_id, event_type, created_at, payload)
SELECT
    1 + (g % 12) AS tenant_id,
    CASE
        WHEN g % 10 = 0 THEN 'security'
        WHEN g % 10 < 4 THEN 'billing'
        ELSE 'activity'
    END AS event_type,
    TIMESTAMPTZ '2026-09-01 00:00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    jsonb_build_object(
        'actor', jsonb_build_object(
            'id', (g % 500)::text,
            'team', CASE
                WHEN g % 5 = 0 THEN 'risk'
                WHEN g % 5 = 1 THEN 'support'
                ELSE 'operations'
            END
        ),
        'labels', CASE
            WHEN g % 20 = 0 THEN
                jsonb_build_array('urgent', 'review')
            WHEN g % 5 = 0 THEN
                jsonb_build_array('review')
            ELSE
                jsonb_build_array('routine')
        END,
        'severity', CASE
            WHEN g % 15 = 0 THEN 'high'
            ELSE 'normal'
        END,
        'amount', (g % 1000)::numeric / 10,
        'flags', jsonb_build_object(
            'approved', (g % 2 = 0)
        )
    ) AS payload
FROM generate_series(1, 60000) AS gs(g);
```

Với các hàng seed:

- Khoảng 10% có `event_type='security'`.
- Khoảng 5% có nhãn `urgent`.
- Giá trị `actor.id` nằm trong tập chuỗi `'0'` đến `'499'`.
- `amount` được lưu thành JSON **number**, không phải JSON string.

Ba hàng thủ công được chèn trước giúp những bài query đơn giản có kết quả dễ thấy; chúng cũng làm thống kê tổng không hoàn toàn bằng số hàng của seed.

**Chạy seed một lần.** Chạy lại sẽ thêm 60.000 hàng nữa, làm kết quả đếm và kế hoạch khác giả định. Không xóa schema trong database dùng chung để “reset nhanh”.

### 3.5. Cập nhật thống kê và kiểm tra

```sql
ANALYZE jsonb_index_lab.audit_events;

SELECT COUNT(*) AS total_rows
FROM jsonb_index_lab.audit_events;

SELECT event_type, COUNT(*) AS n
FROM jsonb_index_lab.audit_events
GROUP BY event_type
ORDER BY event_type;
```

Nếu các khối INSERT chạy đúng một lần, tổng số hàng là **60.003**.

---

## 4. GIN index toàn cột: jsonb_ops mặc định

### 4.1. Cú pháp

```sql
CREATE INDEX audit_events_payload_ops_idx
ON jsonb_index_lab.audit_events
USING GIN (payload);
```

Với `jsonb`, operator class GIN mặc định là **`jsonb_ops`**. Có thể viết tường minh:

```sql
-- Cùng định hướng opclass; không tạo thêm index trùng trong lab:
-- CREATE INDEX another_ops_idx
-- ON jsonb_index_lab.audit_events
-- USING GIN (payload jsonb_ops);
```

GIN lưu các mục index cho các thành phần JSONB theo cách `jsonb_ops` quy định. Nó có thể giúp PostgreSQL xác định các hàng **có khả năng** thỏa toán tử containment hoặc existence rồi kiểm tra lại nếu cần.

### 4.2. Truy vấn containment

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"severity":"high"}'::jsonb;
```

PostgreSQL có thể chọn:

```text
Bitmap Heap Scan on audit_events
  Recheck Cond: (payload @> '{"severity":"high"}'::jsonb)
  -> Bitmap Index Scan on audit_events_payload_ops_idx
       Index Cond: (payload @> '{"severity":"high"}'::jsonb)
```

Đây là **hình dạng plan minh họa**, không phải kết quả cố định. Với bảng nhỏ hoặc predicate nhiều hàng, planner có thể chọn Seq Scan vì rẻ hơn.

### 4.3. Truy vấn existence

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ? 'actor';
```

`jsonb_ops` hỗ trợ toán tử `?`. Trong dữ liệu seed gần như mọi hàng đều có `actor`, nên **Seq Scan vẫn có thể là lựa chọn tốt hơn**. Tính hỗ trợ toán tử và tính chọn lọc là hai vấn đề khác nhau.

### 4.4. ?| và ?&

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ?| ARRAY['severity', 'priority'];

EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ?& ARRAY['actor', 'labels'];
```

Hai toán tử này cũng được `jsonb_ops` hỗ trợ. Nếu hầu hết tài liệu đều có những khóa đó, planner vẫn có thể quét tuần tự.

### 4.5. GIN không “biết” mọi kiểu phép toán trên giá trị

Ví dụ:

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload ->> 'amount')::numeric >= 50;
```

Điều kiện dùng **biểu thức scalar NUMERIC**. GIN `jsonb_ops` trên toàn bộ `payload` không phải một B-tree range index trên `amount` trích ra. Để tối ưu range, cần suy nghĩ theo **B-tree expression index hoặc cột typed**.

---

## 5. jsonb_path_ops: GIN chuyên cho containment và JSONPath

### 5.1. Tạo index với operator class tường minh

```sql
CREATE INDEX audit_events_payload_path_idx
ON jsonb_index_lab.audit_events
USING GIN (payload jsonb_path_ops);
```

Khác với index mặc định, `jsonb_path_ops` lưu thông tin tìm kiếm theo hướng **đường dẫn cùng giá trị**. Trong nhiều workload containment cụ thể, index có thể nhỏ hơn hoặc chọn lọc hơn so với `jsonb_ops`.

**Không suy rằng nó luôn nhanh/nhỏ hơn**; kết quả phụ thuộc dữ liệu, số key/value, truy vấn và thao tác ghi.

### 5.2. Hai operator class dùng cơ chế trích entry khác nhau

Sơ đồ khái niệm:

```text
Document:
  {"actor":{"id":"42","team":"risk"}}

jsonb_ops:
  đánh index các key và value theo cơ chế riêng
  khi tìm containment có thể phối hợp nhiều entry

jsonb_path_ops:
  dùng thông tin gắn với đường dẫn tới value
  ví dụ actor -> id -> "42"
  có thể chọn lọc hơn với đường dẫn cụ thể
```

Đây không phải một format mã hóa byte chính xác; chỉ là cách hiểu sự khác nhau về **granularity của key index**.

### 5.3. Query containment vẫn được hỗ trợ

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

Cả `jsonb_ops` lẫn `jsonb_path_ops` đều có thể hỗ trợ `@>`. Nếu cả hai index cùng tồn tại, planner chọn theo chi phí; **không thể quy mọi lần dùng index cho một operator class chỉ dựa trên việc đã tạo nó**.

### 5.4. jsonb_path_ops KHÔNG hỗ trợ ?

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ? 'actor';
```

`jsonb_path_ops` **không hỗ trợ** các toán tử tồn tại khóa `?`, `?|`, `?&`. Muốn tối ưu kiểu existence này bằng GIN trên toàn cột, hãy xét `jsonb_ops`.

Nếu chỉ có `jsonb_path_ops`, PostgreSQL không thể dùng nó như một index `?` tương đương `jsonb_ops`.

### 5.5. JSONPath: cả hai operator class đều có thể hỗ trợ

Trên các phiên bản có JSONPath:

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @? '$.actor.id ? (@ == "42")';

EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @@ '$.actor.id == "42"';
```

`jsonb_ops` và `jsonb_path_ops` đều hỗ trợ các toán tử `@?`, `@@` trong những trường hợp có thể trích điều kiện tìm kiếm phù hợp. Nhưng điều này **không có nghĩa mọi JSONPath đều tạo được index condition có ích**.

### 5.6. Bảng so sánh quan trọng

| Toán tử / tính năng | GIN `jsonb_ops` | GIN `jsonb_path_ops` |
|---|---|---|
| `@>` containment | Có | Có |
| `?` key existence | Có | **Không** |
| `?|` any-key existence | Có | **Không** |
| `?&` all-key existence | Có | **Không** |
| `@?` JSONPath | Có | Có |
| `@@` JSONPath predicate | Có | Có |
| Mục index cho key/value | Key/value theo cơ chế riêng | Thông tin path + value |
| Tra cứu containment cụ thể | Phù hợp | Có thể chọn lọc/nhỏ hơn |
| Tìm object không chứa value như `{"a":{}}` | Có những khả năng tìm entry khác | Có thể rất kém vì thiếu entry cụ thể |

### 5.7. Cấu trúc rỗng là trường hợp đặc biệt

Ví dụ:

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"metadata":{}}'::jsonb;
```

Với cấu trúc không có value bên trong object rỗng, `jsonb_path_ops` có thể **không tạo entry hữu ích** tương ứng với cấu trúc đó. Việc tìm có thể rất tốn kém vì cần quét phạm vi index rộng hoặc nhiều hàng.

Nếu workload thường xuyên kiểm tra tồn tại object rỗng, khóa vắng/một cấu trúc không có leaf value, **đừng chọn `jsonb_path_ops` chỉ vì thấy nó nhỏ hơn trên benchmark khác**.

### 5.8. Không tạo cả hai index trong production nếu không cần

Trong lab, ta tạo cả hai để tìm hiểu. Trên bảng lớn, duy trì cả hai GIN trên cùng `payload` có thể tốn đáng kể dung lượng, CPU, WAL và cập nhật.

Quyết định dựa vào **tần suất toán tử truy vấn**:

- Nhiều `?`/`?|`/`?&`: ưu tiên xem xét `jsonb_ops`.
- Chủ yếu `@>` trên đường dẫn/giá trị cụ thể: đánh giá `jsonb_path_ops`.
- Chủ yếu equality/range trên vài thuộc tính scalar: B-tree expression indexes có thể phù hợp hơn GIN toàn cột.

---

## 6. JSONPath và giới hạn khả năng suy ra index condition

### 6.1. JSONPath có nhiều khả năng hơn index

JSONPath cho phép biểu thức phức tạp, có thể lọc mảng/object, so sánh và duyệt các cấu trúc lồng nhau. Nhưng GIN chỉ tận dụng được **những điều kiện có thể trích xuất thành tra cứu phù hợp**.

### 6.2. Mẫu equality trong JSONPath

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @? '$.actor.id ? (@ == "42")';
```

Trong một số trường hợp, PostgreSQL có thể trích điều kiện dạng:

```text
accessor_chain == constant
```

với `accessor_chain` đi theo các khóa/phần tử mảng để GIN xác định candidate rows.

### 6.3. Wildcards hỗ trợ khác nhau theo opclass

Trong quá trình trích điều kiện JSONPath:

- `jsonb_ops` hỗ trợ những accessor phổ biến như `.key`, `[*]`, `[index]` và có khả năng đối với một số wildcard object/recursive như `.*`, `.**`.
- `jsonb_path_ops` hỗ trợ `.key` và các accessor mảng phổ biến nhưng **không** tương đương hoàn toàn với `jsonb_ops` cho mọi dạng wildcard.

Không viết một JSONPath rất tổng quát rồi mặc định cả hai opclass dùng index ngang nhau.

### 6.4. So sánh lớn hơn không giống containment equality

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @@ '$.amount > 80';
```

Đây là JSONPath predicate so sánh **khoảng số**. Không suy rằng GIN JSONB đã trở thành một B-tree numeric trên mọi giá trị `amount`; những phần của JSONPath không thể trích thành entry phù hợp có thể vẫn phải được kiểm tra trên từng candidate/row.

Với range theo amount chạy thường xuyên, B-tree expression index là lựa chọn cần so sánh.

### 6.5. Đừng đồng nhất một plan có GIN với toàn bộ điều kiện được xử lý trong index

`EXPLAIN` có thể cho thấy:

```text
Bitmap Index Scan ...
Bitmap Heap Scan ...
Recheck Cond: (...)
Filter: (...)
```

GIN thường giúp **giới hạn candidate rows**; executor vẫn có thể phải đánh giá điều kiện đầy đủ cho candidate. Mức giảm công việc mới là điều cần đo, không chỉ tên node.

---

## 7. Biểu thức nằm ở đâu quyết định GIN có dùng được không

### 7.1. GIN (payload) hỗ trợ toán tử đặt trực tiếp trên payload

```sql
WHERE payload @> '{"labels":["urgent"]}'::jsonb
```

Toán tử `@>` áp vào **chính cột `payload`**, phù hợp với index `GIN (payload)`.

### 7.2. Toán tử ? đặt trên payload -> 'labels'

```sql
WHERE payload -> 'labels' ? 'urgent'
```

Ở đây toán tử `?` không áp vào `payload` mà áp vào **biểu thức `payload -> 'labels'`**. Index `GIN (payload)` không tự động trở thành GIN index trên mọi biểu thức trích xuất từ payload.

### 7.3. Viết lại với containment khi giữ nguyên ý nghĩa

Nếu `labels` là JSON array chứa string:

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"labels":["urgent"]}'::jsonb;
```

Câu này giữ toán tử trên **payload gốc** và có thể dùng GIN toàn cột. Nhưng chỉ viết lại khi bạn đã xác định **ngữ nghĩa dữ liệu** tương thích: containment array và existence trên JSONB có các quy tắc riêng với scalar/object/array.

### 7.4. Tạo GIN expression index

Nếu query chủ yếu dùng:

```sql
WHERE payload -> 'labels' ? 'urgent'
```

có thể tạo:

```sql
CREATE INDEX audit_events_labels_gin_idx
ON jsonb_index_lab.audit_events
USING GIN ((payload -> 'labels'));
```

Biểu thức trong index key là **`payload -> 'labels'`**, còn operator class mặc định của kết quả `jsonb` là `jsonb_ops`.

### 7.5. Kiểm tra expression index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload -> 'labels') ? 'urgent';
```

PostgreSQL có thể sử dụng `audit_events_labels_gin_idx` vì toán tử `?` được áp đúng lên biểu thức index key. Nhưng vẫn phải xét selectivity và cost.

### 7.6. Tại sao GIN expression index có thể nhỏ hơn?

Với một document:

```json
{
  "actor": {"id": "42", "team": "risk"},
  "labels": ["urgent", "review"],
  "severity": "high",
  "flags": {"approved": false}
}
```

GIN toàn cột có thể duy trì entry cho nhiều thành phần. GIN expression index trên `payload -> 'labels'` chỉ tập trung vào JSONB labels, nên **có cơ hội** nhỏ hơn và phù hợp hơn với workload tìm nhãn.

Không coi “nhỏ hơn” là định luật: dữ liệu, số lượng labels, cấu trúc, pending list và lịch sử ghi quyết định kích thước thực.

### 7.7. Expression khác nhau là index khác nhau

```sql
WHERE payload -> 'labels' ? 'urgent'
```

khác:

```sql
WHERE payload ->> 'labels' = '["urgent", "review"]'
```

`->` trả `jsonb`; `->>` trả `text`. Không thể dùng toán tử `?` JSONB trực tiếp lên text kết quả `->>`, và so sánh chuỗi JSON serialized cũng không cùng ngữ nghĩa membership.

---

## 8. B-tree expression index cho giá trị scalar trong JSONB

### 8.1. Trích actor.id thành TEXT

```sql
SELECT
    event_id,
    payload #>> '{actor,id}' AS actor_id_text
FROM jsonb_index_lab.audit_events
WHERE event_id <= 3;
```

Toán tử `#>>` trích giá trị theo **đường dẫn** và trả `text`. Khi actor.id được thiết kế là string ID, B-tree trên biểu thức đó phù hợp với equality.

### 8.2. Tạo B-tree index cho actor.id

```sql
CREATE INDEX audit_events_actor_id_btree_idx
ON jsonb_index_lab.audit_events
    ((payload #>> '{actor,id}'));
```

Truy vấn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE payload #>> '{actor,id}' = '42';
```

Query có biểu thức đúng với index key, nên PostgreSQL có thể sử dụng B-tree expression index.

### 8.3. So với GIN containment

Hai query có mục đích gần nhau khi tài liệu tuân theo một schema rõ:

```sql
-- Containment, có thể dùng GIN whole-document
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb

-- Equality trên scalar text, có thể dùng B-tree expression
WHERE payload #>> '{actor,id}' = '42'
```

Nhưng **không tự khẳng định hai query luôn tương đương cho mọi JSON**. Ví dụ tài liệu có `"id":42` dưới dạng JSON number có thể khác điều kiện chứa string `"42"`, trong khi `#>>` đưa ra biểu diễn text.

### 8.4. Range trên amount cần kiểu NUMERIC

```sql
CREATE INDEX audit_events_amount_btree_idx
ON jsonb_index_lab.audit_events
    (((payload ->> 'amount')::numeric));
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload ->> 'amount')::numeric >= 50
  AND (payload ->> 'amount')::numeric < 80;
```

Một B-tree trên giá trị `NUMERIC` phù hợp với điều kiện **range** và có thứ tự số học. GIN JSONB toàn cột không phải lựa chọn mặc định cho loại truy vấn này.

### 8.5. Không so số bằng text nếu cần thứ tự số học

```sql
-- Sai ngữ nghĩa khi muốn range số học:
-- WHERE payload ->> 'amount' >= '80'
```

So sánh text có quy tắc thứ tự khác số:

```text
Text:    '100' có thể đứng trước '80' theo từ điển
Numeric: 100 > 80
```

Đừng để việc index-friendly làm thay đổi semantics của nghiệp vụ.

### 8.6. Cẩn thận dữ liệu amount thiếu hoặc không hợp lệ

Trong seed, mọi row đều có `amount` dạng JSON number. Nhưng một hệ thống thật có thể chứa:

```json
{"amount":"unknown"}
```

Khi chạy `(payload ->> 'amount')::numeric`, PostgreSQL có thể báo lỗi kiểu **invalid input syntax for type numeric**. Tạo expression index sẽ phải tính biểu thức trên dữ liệu hiện có và có thể thất bại nếu có row không chuyển được.

Không dùng cast thẳng cho dữ liệu chưa kiểm soát. Các hướng thiết kế:

- Validate dữ liệu khi ghi.
- Dùng constraint/hợp đồng JSON rõ ràng.
- Lưu scalar quan trọng thành **cột typed riêng** và chỉ để JSONB cho phần mở rộng.
- Làm sạch dữ liệu legacy trước khi tạo expression index.

### 8.7. Không đánh index mọi thuộc tính JSON

Một document có 50 trường không có nghĩa cần 50 expression indexes. Mỗi index có chi phí:

- Tính toán expression khi ghi.
- Lưu trữ entry và WAL.
- Bảo trì, vacuum, reindex.
- Có thể ảnh hưởng HOT updates.
- Tăng số phương án planner xem xét.

Hãy bắt đầu từ **query workload được đo** chứ không từ số key JSON có thể xuất hiện.

---

## 9. Operator class là gì và vì sao phải chọn đúng?

### 9.1. Operator class gắn index key với nhóm toán tử

Một index không chỉ gồm cột và phương pháp truy cập. **Operator class** cho biết cách index xử lý những loại toán tử phù hợp với key. Cú pháp:

```sql
CREATE INDEX ...
ON table_name
USING gin (payload jsonb_path_ops);
```

Nếu bỏ tên operator class, PostgreSQL dùng **opclass mặc định** cho kiểu dữ liệu và access method tương ứng khi có.

### 9.2. jsonb_ops là mặc định cho GIN jsonb

```sql
USING gin (payload)
```

thường tương đương mục đích dùng `jsonb_ops` cho `payload jsonb`.

### 9.3. jsonb_path_ops chủ động đánh đổi toán tử

```sql
USING gin (payload jsonb_path_ops)
```

thường phục vụ tốt các truy vấn containment/JSONPath thích hợp nhưng không hỗ trợ key-existence operators `?`, `?|`, `?&`.

Không đổi opclass của index chỉ vì thấy `jsonb_path_ops` có tên “path”, tưởng rằng mọi truy vấn truy cập đường dẫn `->`/`->>` đều sẽ tự dùng nó.

### 9.4. Opclass và biểu thức là hai trục độc lập

Có thể có:

```sql
USING gin (payload jsonb_ops)
```

và:

```sql
USING gin ((payload -> 'labels') jsonb_ops)
```

Cả hai cùng opclass, nhưng **key được index khác nhau**. Query áp `?` lên `payload -> 'labels'` thường cần expression index tương ứng, không phải cứ có cùng opclass là đủ.

### 9.5. Kết luận lựa chọn

Trước khi tạo GIN:

1. Query áp toán tử nào?
2. Toán tử nằm trên **payload** hay một expression?
3. Opclass có hỗ trợ toán tử đó không?
4. Index entries có chọn lọc với dữ liệu thực không?
5. Có cần range/sort scalar mà B-tree phù hợp hơn không?

---

## 10. JSON null, SQL NULL và khóa không tồn tại

Đây là một trong những nguồn lỗi logic phổ biến nhất khi truy vấn JSONB.

### 10.1. Ba trạng thái khác nhau

```json
{}
```

```json
{"note":null}
```

```json
{"note":"null"}
```

Ba document này **không giống nhau**:

- Document thứ nhất **thiếu key** `note`.
- Document thứ hai có key `note` với **JSON null**.
- Document thứ ba có key `note` chứa chuỗi `"null"`.

### 10.2. Toán tử ? chỉ hỏi key hiện diện

```sql
SELECT
    '{}'::jsonb ? 'note' AS missing_note,
    '{"note":null}'::jsonb ? 'note' AS json_null_note,
    '{"note":"null"}'::jsonb ? 'note' AS text_null_note;
```

Kết quả:

| Trường hợp | `? 'note'` |
|---|---|
| Missing key | false |
| JSON null | true |
| Chuỗi "null" | true |

### 10.3. -> và ->> có khác biệt

```sql
SELECT
    '{"note":null}'::jsonb -> 'note' AS jsonb_value,
    '{"note":null}'::jsonb ->> 'note' AS text_value;
```

`->` trả giá trị JSONB, ở đây là **JSON null**. `->>` trả text, và với JSON null thì kết quả SQL có thể là **NULL**. Truy cập key không tồn tại bằng các toán tử này cũng có thể trả SQL NULL.

Vì vậy:

```sql
WHERE payload ->> 'note' IS NULL
```

không phân biệt rõ **missing** với **JSON null**.

### 10.4. Containment phân biệt giá trị JSON

```sql
WHERE payload @> '{"note":null}'::jsonb
```

chỉ tìm tài liệu có giá trị JSON null phù hợp theo containment, khác với điều kiện key tồn tại `payload ? 'note'`.

### 10.5. Không dùng cast và COALESCE để che trạng thái dữ liệu

```sql
-- Có thể nhập nhằng missing, JSON null hoặc text rỗng:
-- WHERE COALESCE(payload ->> 'note', '') = ''
```

Nếu nghiệp vụ cần phân biệt missing/JSON null/text, hãy viết điều kiện và schema rõ. Index chỉ tối ưu một điều kiện **đã đúng**, không sửa được lỗi semantics.

---

## 11. JSONB arrays và SQL arrays không phải một kiểu

Chương “JSON và mảng” dễ gây nhầm giữa:

```sql
'["urgent","review"]'::jsonb
```

và:

```sql
ARRAY['urgent', 'review']::text[]
```

### 11.1. Toán tử JSONB ?

```sql
SELECT '["urgent","review"]'::jsonb ? 'urgent'
       AS jsonb_has_urgent;
```

### 11.2. Toán tử SQL array @>

```sql
SELECT ARRAY['urgent','review']::text[]
       @> ARRAY['urgent']::text[]
       AS sql_array_contains_urgent;
```

Kết quả logic gần nhau, nhưng **kiểu hai vế, operator class và index definition khác**.

### 11.3. GIN cho native text[]

Ví dụ một bảng riêng:

```sql
CREATE TABLE jsonb_index_lab.task_labels (
    task_id BIGINT PRIMARY KEY,
    labels TEXT[] NOT NULL
);

INSERT INTO jsonb_index_lab.task_labels
VALUES
    (1, ARRAY['urgent', 'review']),
    (2, ARRAY['routine']),
    (3, ARRAY['review']);

CREATE INDEX task_labels_gin_idx
ON jsonb_index_lab.task_labels
USING GIN (labels);
```

Query:

```sql
SELECT task_id
FROM jsonb_index_lab.task_labels
WHERE labels @> ARRAY['urgent']::text[];
```

Đây là GIN cho **native array** với operator class tương ứng, **không** phải `jsonb_ops`/`jsonb_path_ops`.

### 11.4. Chọn JSONB array hay native array

| Nhu cầu | Lựa chọn thường cân nhắc |
|---|---|
| Danh sách đồng nhất kiểu, không có metadata phức tạp | `TEXT[]` hoặc bảng quan hệ phụ |
| Tài liệu linh hoạt có object/array lồng nhau | `JSONB` |
| Cần quan hệ nhiều-nhiều, FK và truy vấn phức tạp | Bảng quan hệ chuẩn hóa |
| Cần GIN existence/containment bên trong JSON document | `JSONB` và opclass phù hợp |

Không chuyển dữ liệu quan hệ rõ ràng sang JSONB chỉ vì GIN nghe có vẻ nhanh. Tính đúng đắn, constraints, query pattern và chi phí cập nhật là các yếu tố quan trọng hơn.

---

## 12. Multitenant: kết hợp JSONB filter với tenant_id

### 12.1. Query thực tế thường có nhiều điều kiện

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE tenant_id = 3
  AND payload @> '{"severity":"high"}'::jsonb;
```

GIN trên `payload` có thể thu hẹp theo JSON. B-tree trên `tenant_id` có thể thu hẹp theo tenant.

### 12.2. Tạo B-tree cho tenant

```sql
CREATE INDEX audit_events_tenant_time_idx
ON jsonb_index_lab.audit_events
    (tenant_id, created_at DESC, event_id DESC);
```

Một query tìm sự kiện mới nhất của tenant:

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE tenant_id = 3
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

có thể tận dụng thứ tự index B-tree mà không liên quan GIN.

### 12.3. BitmapAnd có thể kết hợp nhiều index

Kế hoạch giả định:

```text
Bitmap Heap Scan on audit_events
  Recheck Cond: (...)
  -> BitmapAnd
       -> Bitmap Index Scan on audit_events_payload_ops_idx
       -> Bitmap Index Scan on audit_events_tenant_time_idx
```

Planner **có thể** kết hợp bitmap từ nhiều index, nhưng không bắt buộc. Nó có thể thấy dùng một index rồi filter điều kiện còn lại rẻ hơn, hoặc Seq Scan phù hợp hơn.

### 12.4. GIN không giữ thứ tự created_at của kết quả

Với query:

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE tenant_id = 3
  AND payload @> '{"severity":"high"}'::jsonb
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

có thể có hai hướng:

1. Dùng GIN để lấy các row JSON phù hợp, lọc tenant, sau đó sort/top-N.
2. Dùng B-tree theo tenant/time để đọc theo thứ tự mới nhất, filter JSON cho đến khi đủ 20 hàng.

Đường tốt nhất phụ thuộc **tỷ lệ JSON match trong tenant, số row cần lấy và phân bố thời gian**. Không có công thức “GIN + ORDER BY luôn nhanh”.

### 12.5. Tránh một GIN index cho mỗi tenant

Một ý tưởng:

```sql
-- Ví dụ cực kỳ chuyên biệt, chưa nên tạo trên mọi tenant:
-- CREATE INDEX audit_events_tenant3_gin_idx
-- ON jsonb_index_lab.audit_events
-- USING gin (payload)
-- WHERE tenant_id = 3;
```

Partial GIN có thể hợp lý cho một số workload nóng, nhưng tạo hàng nghìn index theo tenant làm tăng DDL, disk, WAL, planning và chi phí ghi.

Đầu tiên nên hiểu workload và xem liệu **index chung + điều kiện tenant** đã đủ.

### 12.6. Index không phải cơ chế phân quyền

Filter `tenant_id=3` trong SQL hỗ trợ đúng phạm vi truy vấn và hiệu năng, nhưng index không tự ngăn role xem tenant khác. Sử dụng quyền, RLS và validation tầng ứng dụng phù hợp.

---

## 13. Partial GIN index cho tập dữ liệu nóng

Giả sử chỉ khoảng 10% event mang loại `security`, và hệ thống thường tìm dấu hiệu trong JSON của những sự kiện đó.

### 13.1. Tạo chỉ mục một phần

```sql
CREATE INDEX audit_events_security_gin_idx
ON jsonb_index_lab.audit_events
USING GIN (payload jsonb_path_ops)
WHERE event_type = 'security';
```

Chỉ những hàng `event_type='security'` được đưa vào index này.

### 13.2. Query suy ra predicate

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE event_type = 'security'
  AND payload @> '{"severity":"high"}'::jsonb;
```

Vì query chứa `event_type='security'`, tập hàng cần tìm nằm trong partial index. Planner có thể chọn nó nếu phù hợp chi phí.

### 13.3. Query không suy ra predicate

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"severity":"high"}'::jsonb;
```

Query này còn muốn lấy `billing`/`activity`, không thể dùng **chỉ** partial index security để đáp ứng đầy đủ toàn bộ tập kết quả.

### 13.4. Prepared statement và generic plan

```sql
PREPARE find_by_type(TEXT, JSONB) AS
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE event_type = $1
  AND payload @> $2;
```

Một **generic plan** phải hợp lệ cho cả `event_type='billing'` và `event_type='security'`, nên không thể mặc định tham số `$1` luôn suy ra predicate security. Một custom plan biết giá trị `$1` có thể lựa chọn khác.

Nếu phiên bản hỗ trợ:

```sql
SET plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE find_by_type(
    'security',
    '{"severity":"high"}'::jsonb
);

SET plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE find_by_type(
    'security',
    '{"severity":"high"}'::jsonb
);

RESET plan_cache_mode;
DEALLOCATE find_by_type;
```

Đây là **thí nghiệm**, không phải khuyến nghị cưỡng bức custom plan toàn ứng dụng. Planner có thể chọn một GIN khác hoặc Seq Scan ngay cả khi partial index có thể dùng.

### 13.5. Partial index và operator class là hai lựa chọn riêng

Ở index security:

```sql
USING GIN (payload jsonb_path_ops)
WHERE event_type='security'
```

ta đã chọn **hai đặc tính**:

1. `jsonb_path_ops`: nhóm toán tử/khoản mục GIN hỗ trợ.
2. `WHERE event_type='security'`: chỉ những row nào được đưa vào index.

Đừng nhầm “partial GIN” với “jsonb_path_ops”; có thể có GIN `jsonb_ops` toàn bảng, GIN `jsonb_path_ops` toàn bảng hoặc mỗi loại đều là partial tùy nhu cầu.

---

## 14. Equality JSONB, tồn tại key và khác biệt so với B-tree

### 14.1. Toán tử = so toàn bộ JSONB

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload = '{"actor":{"id":"42"}}'::jsonb;
```

Câu trên yêu cầu **toàn bộ document bằng chính JSONB phía phải** theo semantics JSONB. Nó khác containment:

```sql
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb
```

vốn chấp nhận document có thêm `labels`, `severity` hoặc các key khác.

### 14.2. GIN jsonb_ops không phải index mặc định cho =

`jsonb_ops` thường được dùng cho `@>` và existence/jsonpath operators. Không được cho rằng GIN trên `payload` tự tối ưu **mọi** phép `payload = ...` như một B-tree trên toàn document.

Nếu thật sự cần equality toàn document và dữ liệu có kích thước phù hợp, PostgreSQL có hỗ trợ **B-tree comparison cho jsonb** theo quy tắc riêng, nhưng B-tree trên document lớn thường không phải lựa chọn đầu tiên. Phần lớn ứng dụng sẽ truy vấn một số **field cụ thể** thay vì equality của mọi JSON key/value.

### 14.3. Trích xuất scalar rồi so sánh

```sql
WHERE payload ->> 'severity' = 'high'
```

phù hợp với:

```sql
CREATE INDEX audit_events_severity_btree_idx
ON jsonb_index_lab.audit_events
    ((payload ->> 'severity'));
```

nhưng nếu `severity='high'` chiếm phần rất lớn bảng, planner có thể vẫn thấy Seq Scan rẻ hơn. Indexable không đồng nghĩa luôn được chọn.

### 14.4. Loại bỏ sự nhập nhằng của JSON number/string

```sql
SELECT
    '{"amount":42}'::jsonb
      @> '{"amount":42}'::jsonb AS number_match,
    '{"amount":"42"}'::jsonb
      @> '{"amount":42}'::jsonb AS string_vs_number;
```

`number_match` là true, `string_vs_number` là false. Nếu bạn biến mọi giá trị thành text qua `->>`, có thể làm mất phân biệt kiểu JSON mà business logic cần.

---

## 15. EXPLAIN: kiểm tra index có thật sự được chọn không

### 15.1. Xem estimated plan

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

`EXPLAIN` chỉ lập kế hoạch trong trường hợp SELECT thông thường và không thực hiện truy vấn để đo actual rows.

### 15.2. Đo actual plan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

Những phần cần đọc:

| Thành phần | Ý nghĩa |
|---|---|
| `Bitmap Index Scan` | GIN có thể được dùng để lấy candidate tuple locations |
| `Bitmap Heap Scan` | Truy cập heap theo bitmap, xử lý visibility/recheck |
| `Index Cond` | Toán tử/điều kiện dùng ở bước index |
| `Recheck Cond` | Điều kiện được kiểm tra lại khi cần |
| `Filter` | Điều kiện cần loại thêm sau khi lấy row |
| `Rows Removed by Filter` | Số hàng bị loại tại filter, khi được báo |
| `Heap Blocks: exact/lossy` | Chẩn đoán độ chính xác bitmap |
| `Buffers: shared hit/read` | Trang được truy cập/cấp vào cache |
| `actual rows` và `loops` | Hàng thực và số lần node chạy |

### 15.3. Recheck không đồng nghĩa index hỏng

GIN thường trả candidate tuple IDs dựa trên những phần tử được index. Một query JSONB phức tạp có thể cần kiểm tra lại điều kiện đầy đủ để bảo đảm đúng kết quả.

Nếu bitmap heap scan dùng lossy pages do giới hạn bộ nhớ, recheck càng quan trọng. Đây là **một phần bình thường của cơ chế truy cập**, không phải lỗi index.

### 15.4. Seq Scan có thể là đúng

Nếu:

```sql
WHERE payload ? 'actor'
```

và 99,99% row có key `actor`, việc dùng GIN rồi đọc hầu hết heap pages có thể không rẻ hơn Seq Scan. Query vẫn có toán tử được `jsonb_ops` hỗ trợ, nhưng optimizer hợp lý khi chọn cách khác.

### 15.5. So estimated và actual rows

```text
cost=... rows=100 ...
actual time=... rows=10000 loops=1
```

Sai lệch lớn về số hàng có thể dẫn đến chọn scan/join không tốt. Hãy xem thống kê, giá trị JSON phổ biến, mức phân bố theo tenant, điều kiện kết hợp và generic/custom plan trước khi thay index.

### 15.6. Đo trước/sau với cùng query và dữ liệu

- So cùng SQL và literal/parameter.
- Đảm bảo index đã tạo xong, thống kê cập nhật hợp lý.
- Đo nhiều lần vì cache nóng/lạnh khác nhau.
- So `BUFFERS` và work done, không chỉ 1 lần execution time.
- Đừng tạo index chỉ vì mong một tên node xuất hiện.

---

## 16. GIN maintenance: pending list, fastupdate và VACUUM

### 16.1. GIN index có chi phí cập nhật

Một JSON document có nhiều key/value có thể sinh **nhiều entry** trong GIN. Khi INSERT/UPDATE/DELETE:

- PostgreSQL phải xử lý các entry liên quan.
- Có thêm ghi WAL và storage.
- Việc cập nhật cả `payload` lớn có thể tốn CPU hơn cập nhật vài scalar columns.
- Index có thể tăng kích thước hoặc xuất hiện bloat theo thời gian.

### 16.2. fastupdate và pending list

GIN có tùy chọn **`fastupdate`** (thường bật mặc định) để một số entry mới được ghi vào **pending list** trước khi hợp nhất vào phần chính của index.

Mô hình khái quát:

```text
INSERT/UPDATE JSONB
       |
       v
GIN pending list
       |
       | cleanup / merge
       v
GIN main structure
```

Điều này có thể giúp giảm chi phí cập nhật trung bình, nhưng pending list cần được xử lý và có thể gây biến động latency khi cleanup diễn ra.

### 16.3. Cấu hình fastupdate

Ví dụ cú pháp tùy chọn khi tạo index:

```sql
-- Mẫu minh họa, KHÔNG tạo thêm index trùng trong lab:
-- CREATE INDEX example_payload_gin
-- ON jsonb_index_lab.audit_events
-- USING gin (payload)
-- WITH (fastupdate = on);
```

Thay đổi `fastupdate` không tự động “dọn sạch” mọi pending entry đã tồn tại. Việc tuning phải dựa vào tốc độ ghi/đọc, maintenance và khả năng giám sát thực tế.

### 16.4. gin_pending_list_limit

PostgreSQL có tham số để giới hạn mức pending list trước khi cleanup trong những trường hợp tương ứng. Quá trình cleanup có thể liên quan `VACUUM` hoặc thao tác xử lý khi pending list đạt ngưỡng.

**Không** tăng/giảm `gin_pending_list_limit` toàn hệ thống tùy tiện để “chữa query chậm”: đánh đổi giữa write latency, cleanup bursts, index size và tổng IO.

### 16.5. VACUUM và AUTOVACUUM

GIN không tách rời cơ chế MVCC của PostgreSQL. DELETE/UPDATE làm xuất hiện tuple versions cần được dọn khi không còn snapshot cần chúng. Autovacuum/VACUUM hỗ trợ việc thu hồi dọn dẹp và quản lý index theo cơ chế tương ứng.

Một giao dịch giữ snapshot lâu có thể làm việc dọn tuple versions chậm hơn. Vì vậy tránh transaction mở quá lâu trong workload có JSONB updates nặng.

### 16.6. Xem kích thước index

```sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid))
        AS index_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_index AS i
    ON i.indexrelid = c.oid
WHERE n.nspname = 'jsonb_index_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

Kích thước phản ánh cấu trúc index, số entry, giá trị, pending list và lịch sử maintenance. Không suy ra index `jsonb_path_ops` luôn nhỏ hơn `jsonb_ops` ở mọi bảng từ một phép đo demo.

### 16.7. Thống kê index usage

```sql
SELECT
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'jsonb_index_lab'
ORDER BY relname, indexrelname;
```

`idx_scan` thấp không tự chứng minh index vô dụng: xem cửa sổ thống kê và workload, và nhớ unique index có thể cần để bảo vệ dữ liệu dù ít SELECT dùng tới.

---

## 17. Triển khai index GIN trên bảng lớn

### 17.1. CREATE INDEX thông thường

```sql
CREATE INDEX new_payload_gin_idx
ON jsonb_index_lab.audit_events
USING GIN (payload jsonb_path_ops);
```

Đây là cú pháp minh họa; lab đã có index path_ops. Không tạo một bản trùng để tăng dung lượng vô ích. Trên bảng ghi nhiều, `CREATE INDEX` thông thường có yêu cầu khóa ảnh hưởng writers.

### 17.2. CREATE INDEX CONCURRENTLY

Một lựa chọn khi triển khai online:

```sql
-- Chỉ chạy khi thực sự cần thêm index mới
-- và đã kiểm tra không có tên/định nghĩa trùng:
-- CREATE INDEX CONCURRENTLY audit_events_new_path_idx
-- ON jsonb_index_lab.audit_events
-- USING gin (payload jsonb_path_ops);
```

`CONCURRENTLY` được thiết kế để giảm việc chặn các thao tác ghi trong quá trình xây index, nhưng:

- Có thể chạy lâu và sử dụng nhiều tài nguyên.
- Có thể chờ transaction/snapshot khác.
- **Không chạy trong transaction block tường minh**.
- Nếu thất bại, có thể để lại index **invalid** cần xử lý có kiểm soát.
- Vẫn cần giám sát tiến độ và tải trên hệ thống.

Không hiểu “concurrently” là hoàn toàn không có lock/IO/chi phí.

### 17.3. Kiểm tra index còn hợp lệ

```sql
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c
    ON c.oid = i.indexrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'jsonb_index_lab'
ORDER BY c.relname;
```

Nếu `indisvalid=false`, không mặc định optimizer sẽ dùng index như thường. Phải xác định nguyên nhân và thực hiện bước dọn/rebuild theo quy trình, đặc biệt với concurrent creation bị lỗi.

### 17.4. Chỉ mục GIN và cột lớn

GIN rất có ích cho containment, nhưng index một document JSONB có hàng nghìn trường/nhãn trên hàng triệu rows có thể gây chi phí đáng kể. Nếu workload chỉ dùng vài field:

- Cân nhắc expression indexes tập trung.
- Cân nhắc cột typed cho field quan trọng.
- Cân nhắc partitioning theo thời gian/tenant nếu lifecycle thật sự phù hợp.
- Tránh index toàn bộ JSON “đề phòng mọi query” mà không có dữ liệu đo.

---

## 18. Prepared statements, kiểu tham số và GIN

### 18.1. Bind JSONB đúng kiểu

```sql
PREPARE find_actor(JSONB) AS
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> $1;

EXPLAIN EXECUTE find_actor(
    '{"actor":{"id":"42"}}'::jsonb
);

DEALLOCATE find_actor;
```

Khai báo `$1` là `JSONB` giữ toán tử `@>` đúng kiểu. PostgreSQL có thể sử dụng GIN nếu operator class hỗ trợ và cost hợp lý.

### 18.2. Không ép cả cột JSONB sang text

```sql
-- Không nên dùng để tìm phần tử JSON:
-- WHERE payload::text LIKE '%"id":"42"%'
```

Cách này vừa phụ thuộc biểu diễn chuỗi JSON, vừa không dùng containment GIN theo đúng semantics, có thể sai với khoảng trắng, thứ tự key, escaping và dữ liệu lồng nhau.

Đúng mục tiêu containment:

```sql
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb
```

### 18.3. Giá trị typed so với chuỗi JSON

Nếu actor.id là string:

```sql
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb
```

khác với:

```sql
WHERE payload @> '{"actor":{"id":42}}'::jsonb
```

Vế thứ hai tìm JSON number. Đừng đổi kiểu chỉ vì API nhận số 42; hãy giữ type theo hợp đồng JSON.

### 18.4. Generic plan không có nghĩa GIN bị vô hiệu

`payload @> $1` có toán tử `@>` trực tiếp trên cột và kiểu JSONB rõ ràng. Generic plan **vẫn có thể xem xét GIN**, dù không biết trước nội dung cụ thể của `$1`; việc chọn index phụ thuộc ước lượng/cost.

Đừng nhầm với partial index có predicate `event_type='security'`: generic plan `event_type=$2` không thể tự giả định mọi giá trị của `$2` đều là security.

### 18.5. JDBC với pgJDBC

Trong ứng dụng Java:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.postgresql.util.PGobject;

public final class AuditEventRepository {
    public long countByContainment(
            Connection connection, String jsonFilter
    ) throws SQLException {
        String sql = """
            SELECT COUNT(*)
            FROM jsonb_index_lab.audit_events
            WHERE payload @> ?
            """;

        PGobject parameter = new PGobject();
        parameter.setType("jsonb");
        parameter.setValue(jsonFilter);

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setObject(1, parameter);
            try (ResultSet rs = statement.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        }
    }
}
```

Đây là ví dụ dùng **pgJDBC** và Java text block (Java 15+). Ứng dụng vẫn cần validate cấu trúc JSON filter, quyền/tenant và giới hạn truy vấn; việc bind parameter ngăn nối trực tiếp SQL nhưng không tự ngăn truy vấn quá rộng.

### 18.6. JDBC trích xuất scalar

Với actor.id:

```java
String sql = """
    SELECT event_id
    FROM jsonb_index_lab.audit_events
    WHERE payload #>> '{actor,id}' = ?
    """;

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setString(1, actorId);
    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý hàng trả về.
    }
}
```

Index phù hợp là B-tree expression trên `(payload #>> '{actor,id}')`. Không cần tự cắt document thành chuỗi rồi tìm kiếm bằng LIKE.

### 18.7. Không tạo JSONPath động không kiểm soát

JSONPath có cú pháp riêng. Nếu ứng dụng ghép trực tiếp chuỗi path từ input người dùng, nó có thể làm thay đổi câu truy vấn hoặc gây lỗi/chi phí ngoài dự kiến.

Ưu tiên cố định path khi hợp đồng dữ liệu rõ ràng, bind các giá trị bằng cơ chế phù hợp hoặc dùng chức năng nhận biến JSONPath có kiểm soát; validate những phần path phải được tạo động.

---

## 19. GIN, B-tree, BRIN và full-text: không một index giải quyết hết

| Yêu cầu | Index thường cân nhắc | Lưu ý |
|---|---|---|
| JSONB containment `@>` | GIN `jsonb_ops` hoặc `jsonb_path_ops` | Chọn theo query operators và phân bố |
| Key existence `?`, `?|`, `?&` | GIN `jsonb_ops` | `jsonb_path_ops` không hỗ trợ |
| JSONPath `@?`/`@@` | GIN phù hợp | Chỉ một số dạng path trích được điều kiện |
| Membership trong `payload->'labels'` | GIN expression hoặc containment trên toàn cột | Expression phải khớp query |
| Equality `payload#>>'{actor,id}' = ...` | B-tree expression | Scalar text |
| Range `(payload->>'amount')::numeric >= ...` | B-tree expression hoặc cột numeric | Dữ liệu phải cast hợp lệ |
| `ORDER BY created_at DESC LIMIT 20` | B-tree theo thời gian/tenant | GIN không cung cấp thứ tự này |
| Toàn văn nội dung văn bản | `tsvector` GIN / full-text | Khác JSON key containment |
| Contains substring `ILIKE '%term%'` | Trigram GIN/GiST khi phù hợp | Cần extension `pg_trgm` và đo selectivity |
| Bảng sự kiện khổng lồ theo thời gian | BRIN hoặc partitioning + index phù hợp | Không thay chức năng JSONB GIN |

### 19.1. B-tree scalar đôi khi vượt GIN toàn cột

Nếu 95% workload là:

```sql
WHERE payload #>> '{actor,id}' = $1
```

một B-tree expression index hẹp có thể nhỏ và ít tốn write maintenance hơn một GIN index trên toàn bộ document. Cần đo, không áp kết luận tổng quát không có dữ liệu.

### 19.2. GIN không thay việc chuẩn hóa dữ liệu quan hệ

Nếu `actor.id` thật ra là foreign key tới bảng người dùng, lưu nó chỉ trong JSONB có thể làm khó việc dùng FK constraint, join typed và kiểm tra toàn vẹn.

Một thiết kế hỗn hợp thường hợp lý:

```sql
event_id      BIGINT PRIMARY KEY
tenant_id     INTEGER NOT NULL
actor_id      BIGINT NOT NULL
created_at    TIMESTAMPTZ NOT NULL
payload       JSONB NOT NULL
```

Các field quan trọng và tham gia ràng buộc/joins ở **cột typed**; JSONB giữ phần mở rộng có cấu trúc linh hoạt.

### 19.3. Không dùng JSONB để bỏ qua schema governance

JSONB cho phép nhiều shape, nhưng nghiệp vụ vẫn phải xác định:

- Những key nào bắt buộc?
- Kiểu của các scalar?
- Key vắng và JSON null có khác nhau?
- Version của document?
- Có giới hạn kích thước và số phần tử mảng?
- Có quyền đọc/ghi những key nhạy cảm nào?

Index chỉ giúp truy cập, không bảo đảm schema hoặc bảo mật.

---

## 20. Những sai lầm thường gặp khi tối ưu jsonb

**1. “Có `jsonb` thì PostgreSQL đã index các key.”** Không. Phải tạo index phù hợp hoặc dùng đường truy cập khác.

**2. “GIN (payload) dùng được mọi phép toán trên JSON.”** Không. Tùy opclass và biểu thức phía trái.

**3. “`jsonb_path_ops` hỗ trợ `?`.”** Sai. Nó không hỗ trợ các toán tử key-existence `?`/`?|`/`?&`.

**4. “`jsonb_ops` và `jsonb_path_ops` có cùng index entries.”** Sai. Cách tạo mục index và khả năng chọn lọc khác.

**5. “`jsonb_path_ops` luôn nhỏ và nhanh hơn.”** Không. Dữ liệu và workload quyết định; cấu trúc rỗng đặc biệt bất lợi.

**6. “`@>` giống `=`.”** Sai. Containment chấp nhận document có thêm thành phần.

**7. “`?` tìm key sâu trong mọi object.”** Sai. Nó kiểm tra mức trên cùng của JSONB biểu thức phía trái.

**8. “`payload ? 'id'` tìm id trong `payload.actor.id`.”** Không. Cần toán tử trên object con hoặc containment/JSONPath phù hợp.

**9. “`payload -> 'labels' ? 'urgent'` chắc dùng GIN(payload).”** Không mặc định; toán tử nằm trên expression.

**10. “`->` và `->>` là cùng kiểu.”** Sai. `->` trả JSONB, `->>` trả text.

**11. “GIN JSONB tốt cho mọi range NUMERIC.”** Không. B-tree trên scalar typed có thể phù hợp hơn.

**12. “So `amount` bằng text giữ đúng thứ tự số học.”** Sai. Text sorting có semantics khác numeric.

**13. “Index expression numeric luôn tạo được dù dữ liệu có `'unknown'`.”** Không. Cast có thể lỗi.

**14. “JSON number 42 tương đương JSON string '42'.”** Không. JSONB giữ phân biệt kiểu.

**15. “Thiếu key giống key có JSON null.”** Không. Key existence và containment phân biệt chúng.

**16. “`payload->>'note' IS NULL` phân biệt missing và JSON null.”** Không; cả hai có thể ra SQL NULL.

**17. “GIN trả rows theo created_at DESC.”** Không. Cần sort/B-tree phù hợp.

**18. “Có hai index thì PostgreSQL luôn BitmapAnd chúng.”** Không. Cost planner có thể chọn một hoặc quét bảng.

**19. “Có index hỗ trợ toán tử thì planner bắt buộc dùng.”** Không. Truy vấn lấy đa số hàng có thể chọn Seq Scan.

**20. “Recheck Cond chứng minh GIN trả kết quả sai.”** Không. Recheck là một phần bình thường của bitmap/index semantics.

**21. “Một path JSONPath phức tạp luôn trích được index key.”** Không. Khả năng extraction có giới hạn.

**22. “Generic prepared plan luôn không dùng được GIN.”** Không. Toán tử `payload @> $1` typed vẫn có thể dùng GIN.

**23. “Partial GIN security dùng cho query mọi event_type.”** Không. Nó thiếu các hàng ngoài predicate.

**24. “Partial index và path_ops là cùng một thứ.”** Không. Một cái chọn hàng, một cái chọn operator class.

**25. “Một GIN index trên toàn cột luôn nhỏ hơn các expression indexes.”** Không có bảo đảm; cần đo kích thước và workload.

**26. “Thêm GIN không ảnh hưởng INSERT/UPDATE.”** Sai. GIN duy trì nhiều entries và có chi phí WAL/disk/CPU.

**27. “fastupdate có nghĩa không bao giờ phải cleanup.”** Sai. Pending list phải được hợp nhất/dọn.

**28. “Tăng pending list limit vô hạn sẽ tối ưu mọi workload.”** Không. Có trade-off về latency và maintenance.

**29. “`CREATE INDEX CONCURRENTLY` chạy được trong `BEGIN`.”** Sai.

**30. “CONCURRENTLY hoàn toàn không tạo tải hoặc chờ lock.”** Sai. Vẫn tiêu thụ tài nguyên, chờ và có thể thất bại.

**31. “Index usage thấp chứng minh nên drop ngay.”** Không. Phải xem thời gian quan sát và nhu cầu toàn workload.

**32. “JSONB array và `TEXT[]` dùng cùng operator class `jsonb_ops`.”** Sai. Native array có hệ toán tử/opclass riêng.

**33. “Dùng payload::text LIKE sẽ tận dụng JSONB GIN.”** Không. Đây là biểu thức text và ngữ nghĩa tìm kiếm khác.

**34. “GIN bảo đảm tenant isolation.”** Không. RLS/permissions thuộc lớp bảo mật.

**35. “Trên một bảng lab 100 dòng Seq Scan nghĩa index vô dụng.”** Không. Planner tối ưu theo chi phí.

**36. “EXPLAIN ANALYZE DML chỉ đo, không ghi.”** Sai. Nó thực thi statement.

**37. “Index expression không liên quan chuyện hàm immutable.”** Sai. PostgreSQL yêu cầu biểu thức index có tính bất biến phù hợp.

**38. “Chuyển mọi cột scalar sang JSONB luôn giúp database linh hoạt hơn mà không mất gì.”** Không. Có thể mất ràng buộc typed/FK và tăng chi phí query/index.

---

## 21. Bài tập thực hành và đáp án

### Bài 1 — Chọn toán tử cho containment

**Yêu cầu:** tìm event có `actor.id` là chuỗi `"42"`, cho phép có những thuộc tính khác.

**Đáp án:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

Có thể dùng GIN toàn cột `jsonb_ops` hoặc `jsonb_path_ops` nếu planner thấy hợp lý.

### Bài 2 — Key existence ở cấp trên

**Yêu cầu:** tìm event có key `actor`, không cần kiểm tra nội dung actor.

**Đáp án:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ? 'actor';
```

GIN `jsonb_ops` hỗ trợ `?`, còn `jsonb_path_ops` không.

### Bài 3 — Chìa khóa lồng nhau

**Câu hỏi:** tại sao `payload ? 'id'` không tìm được actor.id?

**Đáp án:** `?` chỉ xét mức top-level của biểu thức `payload`. Có thể dùng `payload -> 'actor' ? 'id'`, containment hoặc JSONPath với semantics phù hợp.

### Bài 4 — Tìm ít nhất một key

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ?| ARRAY['severity', 'priority'];
```

**Đáp án:** Trả hàng có ít nhất một key ở cấp trên cùng. Dùng `jsonb_ops` nếu muốn hỗ trợ GIN loại existence này.

### Bài 5 — Tìm đủ hai key

```sql
WHERE payload ?& ARRAY['actor','labels']
```

**Đáp án:** Yêu cầu có cả actor và labels ở cấp trên cùng; `jsonb_ops` hỗ trợ toán tử.

### Bài 6 — jsonb_path_ops có dùng cho ? không?

**Đáp án:** Không. Nó hỗ trợ `@>`, `@?`, `@@` trong những trường hợp phù hợp, không hỗ trợ `?`/`?|`/`?&`.

### Bài 7 — Membership của labels bằng containment

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"labels":["urgent"]}'::jsonb;
```

**Đáp án:** Query có thể dùng GIN toàn document vì toán tử `@>` đặt trên `payload`.

### Bài 8 — Membership bằng ? trên expression

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload -> 'labels' ? 'urgent';
```

**Câu hỏi:** index nào gần trực tiếp với biểu thức này?

**Đáp án:** `GIN ((payload -> 'labels'))` với `jsonb_ops`, vì `?` áp lên biểu thức trích array.

### Bài 9 — Tạo expression GIN

```sql
CREATE INDEX exercise_labels_gin_idx
ON jsonb_index_lab.audit_events
USING GIN ((payload -> 'labels'));
```

**Đáp án:** Đúng cú pháp ví dụ. Trong lab đã có `audit_events_labels_gin_idx` tương ứng; không cần giữ index gần trùng nếu không phục vụ mục tiêu riêng.

### Bài 10 — B-tree trên actor.id

**Yêu cầu:** tìm actor.id bằng equality text.

**Đáp án:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload #>> '{actor,id}' = '42';
```

Index B-tree expression `((payload #>> '{actor,id}'))` có thể phù hợp.

### Bài 11 — Range amount

**Yêu cầu:** tìm amount từ 50 đến dưới 80 với nghĩa số học.

**Đáp án:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload ->> 'amount')::numeric >= 50
  AND (payload ->> 'amount')::numeric < 80;
```

Chỉ dùng cast trực tiếp khi đã bảo đảm dữ liệu numeric hợp lệ; B-tree expression hoặc cột numeric thật phù hợp hơn.

### Bài 12 — Nguy cơ text comparison

**Câu hỏi:** `payload->>'amount' >= '80'` có an toàn nếu amount là số?

**Đáp án:** Không. `->>` cho text; so sánh có thể theo thứ tự từ điển thay vì số học.

### Bài 13 — JSON number và string

```sql
SELECT
  '{"id":"42"}'::jsonb @> '{"id":42}'::jsonb AS matched;
```

**Đáp án:** `false`, vì JSON string và JSON number khác kiểu.

### Bài 14 — Key missing và JSON null

**Câu hỏi:** `payload ? 'note'` có true cho `{"note":null}` không?

**Đáp án:** Có, vì key vẫn hiện diện. Với `{}` thì false.

### Bài 15 — Vì sao path_ops không thích object rỗng?

**Đáp án:** `jsonb_path_ops` tạo entry theo path/value; object không chứa value leaf như `{"a":{}}` có thể thiếu key index hữu ích, khiến tra cứu containment kiểu này rất tốn kém.

### Bài 16 — JSONPath equality

**Yêu cầu:** viết JSONPath tìm actor.id `"42"`.

**Đáp án:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @? '$.actor.id ? (@ == "42")';
```

Không phải mọi JSONPath đều được tối ưu bằng GIN; đo `EXPLAIN`.

### Bài 17 — JSONPath range

```sql
WHERE payload @@ '$.amount > 80'
```

**Câu hỏi:** GIN JSONB có phải B-tree numeric range không?

**Đáp án:** Không. JSONPath có thể được thực thi nhưng không suy ra mọi range được xử lý hoàn toàn trong GIN. Với range thường xuyên, xem B-tree trên scalar numeric.

### Bài 18 — Partial GIN

**Yêu cầu:** tìm security events có severity high.

**Đáp án:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE event_type = 'security'
  AND payload @> '{"severity":"high"}'::jsonb;
```

Điều kiện suy ra predicate của `audit_events_security_gin_idx`.

### Bài 19 — Query không suy ra partial predicate

```sql
WHERE payload @> '{"severity":"high"}'::jsonb
```

**Đáp án:** Không đủ để dùng partial index security như nguồn bao phủ toàn bộ query, vì còn nhiều event_type khác.

### Bài 20 — Generic plan

**Câu hỏi:** `WHERE event_type=$1` trong generic plan có luôn dùng partial GIN `WHERE event_type='security'` không?

**Đáp án:** Không; `$1` có thể là billing/activity. Custom plan biết `$1='security'` có thể xét index, nhưng vẫn không bảo đảm được chọn.

### Bài 21 — GIN và ORDER BY

**Yêu cầu:** lấy 20 security events mới nhất có JSON severity high.

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE event_type = 'security'
  AND payload @> '{"severity":"high"}'::jsonb
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

**Đáp án:** GIN có thể thu hẹp JSON candidates nhưng không trực tiếp cung cấp thứ tự created_at. PostgreSQL có thể sort/top-N hoặc chọn B-tree/time rồi filter, tùy cost.

### Bài 22 — Đọc Bitmap Heap Scan

Plan có `Bitmap Index Scan` và `Recheck Cond`.

**Đáp án:** Index xác định candidate rows, heap scan lấy tuples và có thể recheck để bảo đảm đúng điều kiện. Đây không tự động là lỗi.

### Bài 23 — Seq Scan dù có GIN

Query `payload ? 'actor'` match gần toàn bảng.

**Đáp án:** Seq Scan có thể rẻ hơn index/heap random access. Cần xem selectivity, rows và buffers.

### Bài 24 — GIN maintenance

**Câu hỏi:** fastupdate giúp gì và có chi phí gì?

**Đáp án:** GIN có thể gom các entry mới vào pending list để giảm chi phí ghi trung bình; pending list cần cleanup/merge, có thể gây biến động latency và thêm công việc bảo trì.

### Bài 25 — So sánh index sizes

**Đáp án gợi ý:**

```sql
SELECT
    c.relname,
    pg_size_pretty(pg_relation_size(c.oid))
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_index i ON i.indexrelid = c.oid
WHERE n.nspname = 'jsonb_index_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

Không kết luận một loại index luôn nhỏ hơn loại khác từ dữ liệu lab.

### Bài 26 — Native array và JSONB

**Câu hỏi:** `TEXT[]` dùng GIN `jsonb_ops` không?

**Đáp án:** Không. Native arrays có toán tử và opclass riêng; `labels @> ARRAY['urgent']::text[]` khác `jsonb_labels ? 'urgent'`.

### Bài 27 — SELECT và DML trong EXPLAIN

**Câu hỏi:** Có được chạy `EXPLAIN ANALYZE UPDATE` để “xem thử index” không?

**Đáp án:** Nó **thực thi UPDATE thật**. Dùng `EXPLAIN UPDATE` không ANALYZE để xem estimated plan, hoặc thử trên bản sao cô lập với kế hoạch rõ ràng.

### Bài 28 — Khi nào nên đưa field ra cột typed?

**Đáp án:** Khi field được dùng thường xuyên trong JOIN, FK, unique/range/order, cần constraints mạnh hoặc truy vấn rất nhiều, một cột typed có thể giúp schema và index đơn giản hơn; JSONB giữ các thuộc tính linh hoạt.

---

## 22. Checklist thiết kế chỉ mục JSONB

### Xác định query

1. **Toán tử gì?** `@>`, `?`, `?|`, `?&`, `@?`, `@@` hay equality/range scalar?
2. **Toán tử đặt trên đâu?** `payload` hay `payload->'labels'`?
3. **Kiểu trả về?** `jsonb` với `->` hay `text` với `->>`/`#>>`?
4. **Tập dữ liệu match có nhỏ không?** Query phổ biến trả 1% hay 99% hàng?
5. **JSON shape có ổn định không?** Có missing keys, JSON null, dữ liệu lỗi kiểu?
6. **Mảng là JSONB hay native SQL array?** Không nhầm toán tử/opclass.

### Chọn index

7. **Cần key existence?** Xem `jsonb_ops`, không chọn `jsonb_path_ops` theo thói quen.
8. **Chủ yếu containment path/value cụ thể?** So `jsonb_ops` với `jsonb_path_ops`.
9. **Có object rỗng thường được truy vấn?** Đánh giá hạn chế của `jsonb_path_ops`.
10. **Query dùng expression con?** GIN expression hoặc viết lại containment đúng semantics.
11. **Equality scalar?** B-tree expression hoặc cột typed.
12. **Range numeric/date?** Không so text; dùng numeric/timestamp index phù hợp.
13. **ORDER BY/LIMIT?** GIN không thay B-tree ordering.
14. **Tenant/partition key?** Xem phối hợp index và partition pruning theo workload.
15. **Partial index?** Query phải suy ra predicate và plan cache phải được xét.
16. **Index trùng không?** Đừng duy trì cả GIN ops/path/expression chỉ vì có thể.

### Kiểm chứng và vận hành

17. **EXPLAIN:** xem Index Cond, Recheck Cond, Filter và node.
18. **EXPLAIN ANALYZE cho SELECT an toàn:** đo actual rows, loops, buffers và temp I/O.
19. **Kiểm tra estimate:** dữ liệu JSON có phân bố lệch theo tenant/loại sự kiện không?
20. **Cập nhật thống kê:** `ANALYZE` sau bulk load/biến động lớn khi phù hợp.
21. **Chi phí ghi:** JSONB cập nhật thường xuyên sẽ làm các GIN/expression indexes đắt.
22. **Pending list:** hiểu fastupdate, cleanup và tác động latency.
23. **Kích thước:** đo `pg_relation_size`, không đoán theo số key.
24. **Index usage:** xem `pg_stat_user_indexes` cùng khung thời gian workload.
25. **Triển khai trên bảng lớn:** `CREATE INDEX CONCURRENTLY` ngoài transaction, theo dõi invalid index.
26. **Quyền/RLS:** chỉ mục không thay authorization hay phân tách tenant.
27. **JDBC bind type:** dùng JSONB typed parameter hoặc scalar đúng kiểu, không cast toàn document sang text.
28. **Giữ đúng ngữ nghĩa:** JSON number/string/null/array/object không được đánh đồng.

---

## 23. Tóm tắt và nguyên tắc ghi nhớ

PostgreSQL có nhiều công cụ để tối ưu truy vấn `jsonb`, nhưng **chọn chỉ mục bắt đầu từ toán tử và biểu thức của query**:

- **GIN `jsonb_ops`** là lựa chọn linh hoạt cho containment, key existence và những JSONPath phù hợp.
- **GIN `jsonb_path_ops`** tập trung vào containment/JSONPath dựa trên path-value, thường đáng đánh giá khi workload chủ yếu dùng `@>`; đổi lại **không** hỗ trợ `?`/`?|`/`?&` và có trường hợp khó với cấu trúc rỗng.
- **GIN expression index** như `GIN ((payload->'labels'))` phục vụ truy vấn áp toán tử JSONB lên **một biểu thức con**, thay vì toàn bộ document.
- **B-tree expression index** như `((payload#>>'{actor,id}'))` hoặc `(((payload->>'amount')::numeric))` phù hợp với equality, range và ordering của **scalar**.
- GIN JSONB **không tự hỗ trợ mọi biến đổi `->>`, phép so sánh text/numeric hay `ORDER BY`**. Query phải dùng toán tử/index key tương thích.
- **JSONB semantics là một phần của correctness**: missing key, JSON null, SQL NULL, JSON number và JSON string không được nhập nhằng chỉ để truy vấn nhanh hơn.
- **Có index hợp lệ chưa đủ**: PostgreSQL vẫn cân nhắc cost, selectivity, heap fetch, thống kê, prepared plans và khối lượng ghi.
- **Mỗi index có giá**: disk, WAL, pending list, cleanup, cập nhật JSONB và thời gian xây index. Không tạo đủ mọi loại index trên cùng document khi không có bằng chứng workload.

**Câu hỏi chốt:** Trước khi viết `CREATE INDEX ... USING GIN`, hãy lấy một query quan trọng và đánh dấu chính xác **biểu thức phía trái của toán tử**. Đó là `payload`, `payload -> 'labels'`, `payload #>> '{actor,id}'` hay `(payload->>'amount')::numeric`? Trả lời đúng câu hỏi này sẽ dẫn bạn đến **GIN toàn cột, GIN biểu thức, B-tree biểu thức hoặc cột typed**, thay vì tạo index theo cảm giác.

### Tài liệu PostgreSQL chính thức

- [JSON Types — `json` và `jsonb`](https://www.postgresql.org/docs/current/datatype-json.html).
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html).
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html).
- [GIN Built-in Operator Classes](https://www.postgresql.org/docs/current/gin-builtin-opclasses.html).
- [GIN Implementation and Fast Update](https://www.postgresql.org/docs/current/gin-implementation.html).
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html).
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html).
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/indexes-opclass.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [CREATE INDEX — GIN, operator class, CONCURRENTLY](https://www.postgresql.org/docs/current/sql-createindex.html).
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html).
- [PREPARE and Custom/Generic Plans](https://www.postgresql.org/docs/current/sql-prepare.html).
