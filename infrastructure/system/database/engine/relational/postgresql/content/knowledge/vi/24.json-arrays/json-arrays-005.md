# Chuyển JSON thành hàng, tập bản ghi và chiều ngược lại trong PostgreSQL

PostgreSQL vừa hỗ trợ **dữ liệu quan hệ có kiểu**, vừa có kiểu **JSON/JSONB** cho tài liệu linh hoạt. Một API có thể gửi đơn hàng dưới dạng một object chứa mảng các dòng chi tiết:

~~~json
{
  "order_id": 1001,
  "customer_id": 501,
  "status": "paid",
  "items": [
    {"sku": "BOOK-01", "quantity": 2, "unit_price": 45000.00},
    {"sku": "PEN-02", "quantity": 3, "unit_price": 12000.00}
  ]
}
~~~

Để tính tổng, JOIN với bảng sản phẩm hoặc áp dụng khóa ngoại, chúng ta thường muốn chuyển mảng `items` thành các **hàng SQL**:

| order_id | line_no | sku | quantity | unit_price |
|---:|---:|---|---:|---:|
| 1001 | 1 | BOOK-01 | 2 | 45000.00 |
| 1001 | 2 | PEN-02 | 3 | 12000.00 |

Chiều ngược lại cũng phổ biến: từ bảng `orders` và `order_items` tạo lại **một JSON object có mảng items** để trả cho API hoặc xuất dữ liệu.

Bài học **“Chuyển JSON thành hàng, tập bản ghi và chiều ngược lại”**, thuộc chương **JSON và mảng** của module **Database Engine Relational PostgreSQL**, giải thích đầy đủ hai chiều:

- **JSON → SQL:** `jsonb_to_record`, `jsonb_to_recordset`, `jsonb_populate_record`, `jsonb_populate_recordset`, `jsonb_array_elements`, `jsonb_each`, `LATERAL` và `WITH ORDINALITY`.
- **SQL → JSON:** `row_to_json`, `to_jsonb`, `jsonb_build_object`, `jsonb_agg` và `jsonb_object_agg`.
- **Tính đúng:** cách xử lý key thiếu, JSON null, SQL NULL, loại dữ liệu, thứ tự mảng, duplicate keys, JOIN làm nhân bản hàng, validation và constraints.
- **Vận hành:** import theo batch, JDBC, kiểm soát kích thước payload, tối ưu lọc/index và đo kế hoạch.

> **An toàn:** những lệnh tạo schema, bảng và nhập dữ liệu trong bài chỉ dành cho database thực hành riêng. Không chạy lại trên production nếu chưa xác định quyền, trạng thái và chính sách đồng bộ.

---

## 1. Hai chiều chuyển đổi cần phân biệt

Một JSON document có thể có nhiều hình dạng:

~~~json
{"id":1,"name":"An"}
~~~

~~~json
[
  {"id":1,"name":"An"},
  {"id":2,"name":"Bình"}
]
~~~

~~~json
{"id":1,"items":[{"sku":"A"},{"sku":"B"}]}
~~~

Mỗi hình dạng cần một kỹ thuật phù hợp:

| Hình dạng đầu vào | Mong muốn ở SQL | Công cụ |
|---|---|---|
| Object đơn | Một record có cột typed | `jsonb_to_record` |
| Array các objects | Nhiều rows | `jsonb_to_recordset` |
| Array các giá trị bất kỳ | Một hàng mỗi phần tử | `jsonb_array_elements` |
| Array cần giữ vị trí | Phần tử kèm chỉ số 1,2,... | `WITH ORDINALITY` |
| Object với key động | Nhiều cặp key/value | `jsonb_each` |
| Object theo composite type có sẵn | Một composite row | `jsonb_populate_record` |
| Array objects theo composite type | Một tập composite rows | `jsonb_populate_recordset` |

Chiều ngược:

| Hình dạng SQL | Mong muốn JSON | Công cụ |
|---|---|---|
| Một row/composite | Object JSON | `row_to_json` hoặc `to_jsonb` |
| Những cột chọn lọc | Object với key tùy ý | `jsonb_build_object` |
| Nhiều rows | JSON array | `jsonb_agg` |
| Những cặp key/value | JSON object | `jsonb_object_agg` |
| Row cha + nhiều rows con | Object chứa array con | `jsonb_build_object` + `jsonb_agg` |

Không có một hàm tự động suy ra mọi schema nested hoặc business rules. Đầu tiên phải xác định **shape của dữ liệu**.

## 2. Kiểu json và jsonb

PostgreSQL hỗ trợ `json` và `jsonb`.

| Thuộc tính | `json` | `jsonb` |
|---|---|---|
| Biểu diễn | Lưu bản văn JSON đã kiểm tra cú pháp | Biểu diễn nhị phân được phân tích |
| Whitespace đầu vào | Được giữ | Không giữ nguyên |
| Thứ tự các key object | Giữ theo văn bản | Không bảo đảm như đầu vào |
| Duplicate object keys | Có thể giữ trong văn bản | Chỉ còn một giá trị/key |
| Các toán tử và GIN indexing | Ít hơn | Nhiều hơn |
| Hàm chuyển thành record | `json_to_record` | `jsonb_to_record` |
| Hàm chuyển thành recordset | `json_to_recordset` | `jsonb_to_recordset` |

`jsonb` thường phù hợp khi cần lọc, biến đổi, index và xử lý JSON trong PostgreSQL. `json` có ích khi yêu cầu giữ gần nguyên văn input.

**Chú ý:** JSON object không phải tập key có thứ tự nghiệp vụ. Trong khi đó, **JSON array có thứ tự**, nên cần lưu vị trí khi việc tái tạo thứ tự là quan trọng.

### 2.1. Kiểu JSON không giống kiểu SQL

JSON phân biệt string, number, boolean, null, array và object. SQL còn có `BIGINT`, `INTEGER`, `NUMERIC(12,2)`, `TIMESTAMPTZ`, `TEXT[]`, composite type và nhiều kiểu khác.

Việc cast hoặc ánh xạ sang kiểu SQL sẽ quyết định độ chính xác, giới hạn giá trị và khả năng sử dụng toán tử/index.

## 3. Các toán tử ->, ->>, #> và #>>

Trước khi chuyển JSON thành rows, cần hiểu cách lấy giá trị:

~~~sql
SELECT
    '{"id":1001,"status":"paid"}'::jsonb -> 'id'
        AS id_jsonb,
    '{"id":1001,"status":"paid"}'::jsonb ->> 'id'
        AS id_text;
~~~

- `->`: lấy một giá trị dưới dạng JSON/JSONB.
- `->>`: lấy giá trị dưới dạng TEXT.
- `#>`: lấy giá trị JSON/JSONB theo đường dẫn nhiều cấp.
- `#>>`: lấy giá trị TEXT theo đường dẫn nhiều cấp.

Ví dụ nested path:

~~~sql
SELECT
    '{"customer":{"address":{"city":"HCM"}}}'::jsonb
        #> '{customer,address}' AS address_json,
    '{"customer":{"address":{"city":"HCM"}}}'::jsonb
        #>> '{customer,address,city}' AS city_text;
~~~

### 3.1. ->> không tự trả BIGINT

~~~sql
SELECT
    ('{"id":1001}'::jsonb ->> 'id')::BIGINT
        AS id_number;
~~~

`->>` trả TEXT. `::BIGINT` mới biến nó thành số. Nếu input là `"abc"` hoặc vượt phạm vi BIGINT thì cast có thể lỗi.

Khi cần nhiều cột typed, `jsonb_to_record` thường rõ ràng hơn hàng loạt cast riêng lẻ.

## 4. Chuyển một object thành record với jsonb_to_record

~~~sql
SELECT x.*
FROM jsonb_to_record(
    '{
      "order_id":1001,
      "customer_id":501,
      "status":"paid",
      "amount":126000.50,
      "priority":true,
      "ordered_at":"2026-11-01T10:15:00Z",
      "note":null
    }'::jsonb
) AS x(
    order_id BIGINT,
    customer_id BIGINT,
    status TEXT,
    amount NUMERIC(12,2),
    priority BOOLEAN,
    ordered_at TIMESTAMPTZ,
    note TEXT
);
~~~

Kết quả logic là một hàng:

| order_id | customer_id | status | amount | priority | note |
|---:|---:|---|---:|---|---|
| 1001 | 501 | paid | 126000.50 | true | NULL |

`ordered_at` được phân tích thành `TIMESTAMPTZ`. Cách hiển thị timezone của PostgreSQL phụ thuộc cấu hình session, nhưng vẫn có thể biểu diễn cùng instant.

### 4.1. Vì sao phải khai báo AS x(...)?

`jsonb_to_record` trả kiểu `record` không có cấu trúc cố định tại thời điểm định nghĩa hàm. Trong `FROM`, SQL cần biết **tên và kiểu của các cột đầu ra**.

Vì vậy mẫu đúng là:

~~~sql
FROM jsonb_to_record(source_jsonb)
AS alias_name(column_a type_a, column_b type_b)
~~~

Không chỉ viết `SELECT * FROM jsonb_to_record(...)` rồi kỳ vọng PostgreSQL tự tạo schema quan hệ theo tất cả JSON keys.

### 4.2. Cột không có trong JSON

Nếu khai báo một cột không tồn tại trong object, thông thường giá trị cột là SQL NULL, trừ ngữ cảnh sử dụng base composite khác có quy tắc giữ giá trị.

### 4.3. Key không khai báo

Nếu object có thêm `"trace_id":"abc"` nhưng AS list chỉ có `order_id` và `status`, key thừa không được đưa ra thành cột.

### 4.4. json_to_record

Nếu nguồn có kiểu `json`:

~~~sql
SELECT *
FROM json_to_record(
    '{"id":1,"name":"Mai"}'::json
) AS x(id INTEGER, name TEXT);
~~~

Nó thực hiện cùng loại ánh xạ nhưng nhận input `json`.

## 5. jsonb_to_recordset: một mảng objects thành nhiều hàng

~~~sql
SELECT *
FROM jsonb_to_recordset(
    '[
      {"sku":"BOOK-01","quantity":2,"unit_price":45000.00},
      {"sku":"PEN-02","quantity":3,"unit_price":12000.00}
    ]'::jsonb
) AS x(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
);
~~~

Kết quả:

| sku | quantity | unit_price |
|---|---:|---:|
| BOOK-01 | 2 | 45000.00 |
| PEN-02 | 3 | 12000.00 |

Có thể tính toán ngay:

~~~sql
SELECT
    SUM(quantity * unit_price) AS total_amount
FROM jsonb_to_recordset(
    '[
      {"sku":"BOOK-01","quantity":2,"unit_price":45000},
      {"sku":"PEN-02","quantity":3,"unit_price":12000}
    ]'::jsonb
) AS x(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
);
~~~

Kết quả là:

\[
2\times45000+3\times12000=126000
\]

### 5.1. Mảng rỗng

~~~sql
SELECT *
FROM jsonb_to_recordset('[]'::jsonb)
AS x(sku TEXT, quantity INTEGER);
~~~

Trả **0 hàng** chứ không phải một hàng với cột NULL.

### 5.2. json_to_recordset

~~~sql
SELECT *
FROM json_to_recordset(
    '[{"id":1},{"id":2}]'::json
) AS x(id INTEGER);
~~~

Dùng khi nguồn là kiểu `json`.

### 5.3. Đầu vào phải có đúng shape

`jsonb_to_recordset` được thiết kế cho **array các objects**. Object đơn nên dùng `jsonb_to_record`. Nếu array có những phần tử không phù hợp, việc chuyển đổi có thể lỗi, không tự bỏ qua dữ liệu sai.

## 6. jsonb_array_elements: mở JSON array từng phần tử

`jsonb_array_elements` trả một hàng cho mỗi phần tử mảng, giữ phần tử dưới dạng JSONB:

~~~sql
SELECT elem
FROM jsonb_array_elements(
    '[10,"hello",null,{"id":1},[1,2]]'::jsonb
) AS x(elem);
~~~

Khác với `jsonb_to_recordset`, hàm này:

- Không yêu cầu mọi phần tử là object có cùng cột.
- Có thể trả scalar, object và array dưới dạng JSONB.
- Giúp xử lý nested/hỗn hợp theo nhiều bước.
- Có thể kết hợp `WITH ORDINALITY` để lấy vị trí.

### 6.1. Mảng scalar thành text

~~~sql
SELECT
    value
FROM jsonb_array_elements_text(
    '["red","blue","green"]'::jsonb
) AS x(value);
~~~

`jsonb_array_elements_text` trả TEXT. Với mảng số, cần cast về INTEGER/NUMERIC nếu muốn tính toán.

### 6.2. Hàm array_elements khác hàm recordset

| Hàm | Mỗi hàng chứa gì? |
|---|---|
| `jsonb_array_elements` | Một cột JSONB là toàn bộ phần tử |
| `jsonb_array_elements_text` | Một cột TEXT là phần tử dạng text |
| `jsonb_to_recordset` | Nhiều cột typed theo AS definition |

Chọn theo việc cần giữ nguyên phần tử hay muốn tách ngay thành các cột.

## 7. WITH ORDINALITY: vị trí phần tử trong JSON array

SQL rows **không có thứ tự được bảo đảm** trừ khi có `ORDER BY`. Trong khi đó, thứ tự JSON array có thể mang nghĩa nghiệp vụ (dòng 1, dòng 2, ...).

~~~sql
SELECT
    x.ordinality AS line_no,
    x.item
FROM jsonb_array_elements(
    '[{"sku":"A"},{"sku":"B"},{"sku":"C"}]'::jsonb
) WITH ORDINALITY AS x(item, ordinality)
ORDER BY x.ordinality;
~~~

Kết quả:

| line_no | item |
|---:|---|
| 1 | `{"sku":"A"}` |
| 2 | `{"sku":"B"}` |
| 3 | `{"sku":"C"}` |

`WITH ORDINALITY` đánh số từ **1**. Chỉ số mảng trong JSON path thường bắt đầu từ **0**, nên không nhầm hai quy ước.

### 7.1. Kết hợp ordinality với jsonb_to_record

~~~sql
SELECT
    a.ordinality::INTEGER AS line_no,
    x.sku,
    x.quantity,
    x.unit_price
FROM jsonb_array_elements(
    '[
      {"sku":"BOOK-01","quantity":2,"unit_price":45000},
      {"sku":"PEN-02","quantity":3,"unit_price":12000}
    ]'::jsonb
) WITH ORDINALITY AS a(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    a.item
) AS x(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
)
ORDER BY a.ordinality;
~~~

Mỗi phần tử vừa có cột typed vừa có `line_no`. Đây là cách rõ ràng để lưu thứ tự vào bảng quan hệ, rồi khôi phục khi xuất JSON.

## 8. LATERAL: mở mảng của từng hàng cha

Giả sử bảng staging có mỗi hàng chứa một JSON object và `items` là một array. Ta muốn mở từng item nhưng vẫn giữ ID hàng cha.

`LATERAL` cho phép một phần tử trong `FROM` tham chiếu các cột của các phần tử ở bên trái:

~~~sql
WITH docs(doc_id, payload) AS (
    VALUES
        (1, '{"items":[{"sku":"A"},{"sku":"B"}]}'::jsonb),
        (2, '{"items":[{"sku":"C"}]}'::jsonb)
)
SELECT
    d.doc_id,
    a.ordinality AS item_no,
    a.item ->> 'sku' AS sku
FROM docs AS d
CROSS JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) WITH ORDINALITY AS a(item, ordinality)
ORDER BY d.doc_id, a.ordinality;
~~~

Kết quả:

| doc_id | item_no | sku |
|---:|---:|---|
| 1 | 1 | A |
| 1 | 2 | B |
| 2 | 1 | C |

### 8.1. CROSS JOIN LATERAL so với LEFT JOIN LATERAL

Nếu `items=[]`, `CROSS JOIN LATERAL` không sinh item row, nên hàng cha bị loại khỏi kết quả.

`LEFT JOIN LATERAL ... ON TRUE` có thể giữ hàng cha và trả cột bên phải NULL:

~~~sql
WITH docs(doc_id, payload) AS (
    VALUES
        (1, '{"items":[{"sku":"A"}]}'::jsonb),
        (2, '{"items":[]}'::jsonb)
)
SELECT
    d.doc_id,
    a.item ->> 'sku' AS sku
FROM docs AS d
LEFT JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) AS a(item) ON TRUE
ORDER BY d.doc_id;
~~~

Dòng `doc_id=2` vẫn xuất hiện, với `sku=NULL`.

### 8.2. Function trong FROM có thể ngầm lateral

Trong PostgreSQL, một function trong FROM thường có thể tham chiếu bảng bên trái mà không cần viết tường minh `LATERAL`. Việc viết `CROSS JOIN LATERAL`/`LEFT JOIN LATERAL` giúp biểu đạt rõ quan hệ cha–con và cách giữ/bỏ hàng.

## 9. jsonb_each: object thành các cặp key/value

Không phải JSON nào cũng có array. Một object chứa key động:

~~~json
{"red":5,"blue":8,"green":3}
~~~

có thể biến thành rows:

~~~sql
SELECT key, value
FROM jsonb_each(
    '{"red":5,"blue":8,"green":3}'::jsonb
);
~~~

Mỗi hàng có `key TEXT` và `value JSONB`. Thứ tự rows không được bảo đảm nếu không ORDER BY.

### 9.1. jsonb_each_text

~~~sql
SELECT key, value
FROM jsonb_each_text(
    '{"region":"VN","currency":"VND"}'::jsonb
);
~~~

Trong phiên bản này, `value` là TEXT.

### 9.2. jsonb_object_keys

~~~sql
SELECT key
FROM jsonb_object_keys(
    '{"a":1,"b":2}'::jsonb
) AS x(key)
ORDER BY key;
~~~

Hữu ích khi muốn biết những keys đang xuất hiện để validation hoặc đối soát dynamic fields.

### 9.3. Không dùng jsonb_each trên array

`jsonb_each` dùng cho object; với `[1,2,3]` dùng `jsonb_array_elements`. Hai shape không thể thay thế nhau.

## 10. JSON null, SQL NULL và key không tồn tại

Ba payload có nghĩa khác nhau:

~~~json
{"note":null}
~~~

~~~json
{}
~~~

~~~json
{"note":"null"}
~~~

- Trường note tồn tại với JSON null.
- Trường note vắng mặt.
- Trường note có TEXT literal `"null"`.

~~~sql
SELECT
    '{"note":null}'::jsonb -> 'note' AS json_null,
    '{}'::jsonb -> 'note' AS missing,
    '{"note":null}'::jsonb ->> 'note' AS null_text,
    '{"note":"null"}'::jsonb ->> 'note' AS literal_text;
~~~

`->` trả JSONB null nếu key chứa JSON null, còn key thiếu cho SQL NULL. `->>` thường trả SQL NULL cho cả JSON null và key thiếu. Literal string vẫn thành TEXT `'null'`.

### 10.1. Kiểm tra key có mặt

~~~sql
SELECT
    '{"note":null}'::jsonb ? 'note' AS has_note,
    jsonb_typeof(
        '{"note":null}'::jsonb -> 'note'
    ) AS type_of_note,
    jsonb_typeof(
        '{}'::jsonb -> 'note'
    ) AS type_of_missing;
~~~

Kết quả logic: `has_note=TRUE`; type đầu là chuỗi `'null'`; type của key thiếu là SQL NULL.

### 10.2. Khi chuyển thành record, hai tình huống có thể cùng ra SQL NULL

~~~sql
SELECT *
FROM jsonb_to_record(
    '{"note":null}'::jsonb
) AS x(note TEXT);
~~~

và:

~~~sql
SELECT *
FROM jsonb_to_record(
    '{}'::jsonb
) AS x(note TEXT);
~~~

thường cùng có cột note là SQL NULL. Nếu ứng dụng dùng patch semantics, key vắng mặt có thể nghĩa “giữ nguyên”, còn JSON null nghĩa “xóa giá trị”. Khi đó **phải giữ thêm thông tin key presence**, không dựa vào record đã typed một mình.

## 11. Mapping và lỗi chuyển kiểu

~~~sql
SELECT *
FROM jsonb_to_record(
    '{
      "id":12,
      "price":25000.75,
      "paid":true,
      "ordered_at":"2026-11-01T09:30:00Z",
      "tags":["priority","gift"],
      "metadata":{"channel":"web"}
    }'::jsonb
) AS x(
    id BIGINT,
    price NUMERIC(12,2),
    paid BOOLEAN,
    ordered_at TIMESTAMPTZ,
    tags TEXT[],
    metadata JSONB
);
~~~

Các hàm record conversion có thể dùng cơ chế chuyển đổi đệ quy cho SQL arrays/composite types phù hợp, nhưng kiểu đích phải chấp nhận dữ liệu thực tế.

Nếu:

~~~sql
SELECT *
FROM jsonb_to_record(
    '{"quantity":"not-an-integer"}'::jsonb
) AS x(quantity INTEGER);
~~~

PostgreSQL có thể báo lỗi chuyển kiểu. Nó **không tự loại hàng lỗi** và trả dữ liệu còn lại.

### 11.1. Kiểm tra required fields

Thiếu key thường tạo SQL NULL cho cột được khai báo. Một cột `NOT NULL` ở bảng đích sau đó sẽ từ chối khi INSERT; một hàm `jsonb_to_record` đứng riêng không thay thế toàn bộ schema validation.

### 11.2. Tránh lưu tiền dưới dạng floating point nếu cần độ chính xác thập phân

Khi tính tiền, `NUMERIC(12,2)` có thể phù hợp hơn `DOUBLE PRECISION`. Kiểu số, scale, rounding và currency rules phải được thiết kế theo nghiệp vụ.

## 12. Tên JSON key và tên SQL column

`jsonb_to_record` ánh xạ theo **tên key**, không tự chuyển camelCase ↔ snake_case.

~~~sql
SELECT x."productId" AS product_id
FROM jsonb_to_record(
    '{"productId":10}'::jsonb
) AS x("productId" BIGINT);
~~~

Nếu khai báo `product_id BIGINT` thay cho `"productId" BIGINT` trong ví dụ này, giá trị không tự được map.

Giải pháp:

- Alias cột bằng đúng tên JSON rồi đổi alias ở SELECT.
- Chuẩn hóa JSON input trong pipeline.
- Dùng `->>` để lấy trường và đặt tên SQL theo ý muốn.
- Quy định contract upstream nhất quán.

Không viết logic tự động đoán tên field nếu tên là một phần của API contract.

## 13. Kiểm tra root type và tránh nhầm COALESCE

`jsonb_to_recordset` cần mảng. `jsonb_array_elements` cũng cần mảng. Có thể kiểm tra:

~~~sql
SELECT
    jsonb_typeof('[1,2]'::jsonb) AS array_type,
    jsonb_typeof('{"id":1}'::jsonb) AS object_type,
    jsonb_typeof('null'::jsonb) AS null_type;
~~~

Kỳ vọng là `array`, `object`, `null`.

### 13.1. COALESCE không thay JSON null thành []

~~~sql
COALESCE(payload -> 'items', '[]'::jsonb)
~~~

chỉ thay **SQL NULL** (ví dụ key thiếu) bằng array rỗng. Nếu payload chứa `"items":null`, giá trị `payload -> 'items'` là **JSONB null**, không bị COALESCE thay.

Nếu contract cho phép coi mọi giá trị không phải array thành array rỗng, có thể dùng:

~~~sql
CASE
    WHEN jsonb_typeof(payload -> 'items') = 'array'
    THEN payload -> 'items'
    ELSE '[]'::jsonb
END
~~~

Nhưng với import nghiêm ngặt, **từ chối** non-array thường tốt hơn việc âm thầm làm mất dữ liệu. Cần quyết định theo schema contract.

## 14. Thiết kế schema lab cho đơn hàng

Trong **database thực hành trống**, tạo các bảng:

~~~sql
CREATE SCHEMA json_lab;

CREATE TABLE json_lab.incoming_documents (
    doc_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE json_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('new','paid','cancelled')),
    source_payload JSONB NOT NULL
);

CREATE TABLE json_lab.order_items (
    order_id BIGINT NOT NULL
        REFERENCES json_lab.orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Giải thích:

- `incoming_documents` lưu JSONB trước khi chuyển.
- `orders` chứa header typed và bản JSONB nguồn trong lab.
- `order_items` chứa một hàng cho mỗi item.
- `line_no` giữ vị trí phần tử mảng.
- FK, CHECK và PK bảo vệ tính toàn vẹn.

Lệnh CREATE sẽ lỗi nếu schema/bảng đã tồn tại. Không tự động DROP schema production chỉ để chạy lại ví dụ; dùng database lab riêng hoặc reset có kiểm soát.

## 15. Nạp dữ liệu JSONB mẫu

~~~sql
INSERT INTO json_lab.incoming_documents(payload)
VALUES
(
    '{
      "order_id":1001,
      "customer_id":501,
      "ordered_at":"2026-11-01T10:15:00Z",
      "status":"paid",
      "items":[
        {"sku":"BOOK-01","quantity":2,"unit_price":45000.00},
        {"sku":"PEN-02","quantity":3,"unit_price":12000.00}
      ],
      "note":null
    }'::jsonb
),
(
    '{
      "order_id":1002,
      "customer_id":502,
      "ordered_at":"2026-11-02T09:00:00Z",
      "status":"new",
      "items":[
        {"sku":"BAG-03","quantity":1,"unit_price":89000.00}
      ]
    }'::jsonb
);
~~~

Có 2 order documents và 3 item objects.

Kiểm tra root và mảng:

~~~sql
SELECT
    doc_id,
    jsonb_typeof(payload) AS root_type,
    jsonb_typeof(payload -> 'items') AS items_type,
    payload ->> 'status' AS status_text
FROM json_lab.incoming_documents
ORDER BY doc_id;
~~~

Các query này kiểm tra dạng dữ liệu, chưa thay thế kiểm tra đầy đủ business constraints.

## 16. Tách header theo từng document

~~~sql
SELECT
    d.doc_id,
    h.order_id,
    h.customer_id,
    h.ordered_at,
    h.status
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS h(
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
)
ORDER BY d.doc_id;
~~~

`jsonb_to_record` tạo một typed record cho mỗi JSON object. `LATERAL` liên kết kết quả với `doc_id` của hàng staging.

Không dùng `jsonb_to_recordset(d.payload)` ở đây vì root của mỗi document là **object** chứ không phải array orders.

## 17. Tách items có line_no

~~~sql
SELECT
    d.doc_id,
    (d.payload ->> 'order_id')::BIGINT AS order_id,
    a.ordinality::INTEGER AS line_no,
    i.sku,
    i.quantity,
    i.unit_price,
    i.quantity * i.unit_price AS line_total
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) WITH ORDINALITY AS a(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    a.item
) AS i(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
)
ORDER BY d.doc_id, a.ordinality;
~~~

Kỳ vọng:

| order_id | line_no | sku | quantity | unit_price | line_total |
|---:|---:|---|---:|---:|---:|
| 1001 | 1 | BOOK-01 | 2 | 45000.00 | 90000.00 |
| 1001 | 2 | PEN-02 | 3 | 12000.00 | 36000.00 |
| 1002 | 1 | BAG-03 | 1 | 89000.00 | 89000.00 |

`jsonb_array_elements` mở mảng, `WITH ORDINALITY` gắn thứ tự, `jsonb_to_record` ánh xạ từng item thành các cột.

## 18. Nhập header vào bảng typed

Sau validation phù hợp, có thể INSERT:

~~~sql
INSERT INTO json_lab.orders (
    order_id, customer_id, ordered_at, status, source_payload
)
SELECT
    h.order_id,
    h.customer_id,
    h.ordered_at,
    h.status,
    d.payload
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS h(
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
);
~~~

Với schema mới tạo và hai order_id khác nhau, câu lệnh chèn 2 rows.

### 18.1. Chạy lại sẽ có thể trùng khóa

`PRIMARY KEY(order_id)` từ chối order_id trùng. Một pipeline thật phải có chính sách:

- Batch chỉ được nhập một lần.
- UPSERT theo source version.
- Reject duplicate.
- Dùng idempotency key.
- Ghi log những sự kiện đã áp dụng.

Không mặc định `ON CONFLICT DO NOTHING` là đúng; nó có thể âm thầm bỏ qua một bản cập nhật thực sự cần thiết.

### 18.2. Ví dụ UPSERT có điều kiện áp dụng

~~~sql
INSERT INTO json_lab.orders (
    order_id, customer_id, ordered_at, status, source_payload
)
SELECT
    h.order_id,
    h.customer_id,
    h.ordered_at,
    h.status,
    d.payload
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS h(
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
)
ON CONFLICT (order_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    ordered_at = EXCLUDED.ordered_at,
    status = EXCLUDED.status,
    source_payload = EXCLUDED.source_payload;
~~~

Mẫu này hợp lệ khi upstream được phép overwrite và input không có duplicate order_id bất thường. Nếu cần version/time conflict policy, bổ sung điều kiện tương ứng.

## 19. Nhập items vào bảng typed

Sau khi headers đã được tạo:

~~~sql
INSERT INTO json_lab.order_items (
    order_id, line_no, sku, quantity, unit_price
)
SELECT
    (d.payload ->> 'order_id')::BIGINT,
    a.ordinality::INTEGER,
    i.sku,
    i.quantity,
    i.unit_price
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) WITH ORDINALITY AS a(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    a.item
) AS i(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
);
~~~

Kết quả dự kiến từ database rỗng là 3 item rows.

### 19.1. Vì sao nhập header trước?

`order_items.order_id` tham chiếu `orders.order_id`. Nếu chưa có order tương ứng và FK không cho phép, INSERT items thất bại.

### 19.2. Cần transaction

Một quy trình nhiều bước nên dùng một transaction:

~~~sql
BEGIN;

-- Kiểm tra payload/batch.
-- INSERT/UPSERT orders.
-- INSERT/REPLACE items theo chính sách.
-- Ghi trạng thái xử lý batch.

COMMIT;
~~~

Đây là workflow khái niệm; các comment không tự chạy bước tương ứng. Với lab có thể bao các câu INSERT đã nêu trong cùng transaction.

### 19.3. Khi một order giảm số items

UPSERT từng item không tự xóa những dòng không còn trong snapshot mới. Nếu source là **full snapshot** của order, cần chính sách replace/soft-delete details trong transaction. Nếu source là **delta**, không xóa những dòng vắng mặt.

Đây là semantics đồng bộ, không phải chức năng mặc định của JSON conversion.

## 20. Root JSON là mảng orders

Nếu input:

~~~json
[
  {"order_id":2001,"customer_id":601,"status":"new"},
  {"order_id":2002,"customer_id":602,"status":"paid"}
]
~~~

dùng:

~~~sql
SELECT *
FROM jsonb_to_recordset(
    '[
      {"order_id":2001,"customer_id":601,"status":"new"},
      {"order_id":2002,"customer_id":602,"status":"paid"}
    ]'::jsonb
) AS o(
    order_id BIGINT,
    customer_id BIGINT,
    status TEXT
);
~~~

Nếu mảng nằm trong một object:

~~~json
{"batch_id":123,"orders":[{"order_id":2001},{"order_id":2002}]}
~~~

cần trích `orders`:

~~~sql
WITH src AS (
    SELECT '{
      "batch_id":123,
      "orders":[{"order_id":2001},{"order_id":2002}]
    }'::jsonb AS doc
)
SELECT o.*
FROM src
CROSS JOIN LATERAL jsonb_to_recordset(
    doc -> 'orders'
) AS o(order_id BIGINT);
~~~

Không truyền cả root object cho recordset và kỳ vọng nó tự tìm mảng con.

## 21. Composite type và jsonb_populate_record

Khi nhiều query cần cùng một định nghĩa row, có thể tạo composite type:

~~~sql
CREATE TYPE json_lab.order_header_type AS (
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
);
~~~

Rồi dùng:

~~~sql
SELECT *
FROM jsonb_populate_record(
    NULL::json_lab.order_header_type,
    '{
      "order_id":1001,
      "customer_id":501,
      "ordered_at":"2026-11-01T10:15:00Z",
      "status":"paid"
    }'::jsonb
);
~~~

`jsonb_populate_record(base, from_jsonb)` dùng **kiểu composite của base** làm output. Nếu base là NULL::type, những field thiếu thường thành SQL NULL; nếu base là giá trị composite không NULL, các field không có trong JSON có thể giữ giá trị từ base theo quy tắc của hàm.

`json_populate_record` là phiên bản nhận kiểu `json`.

### 21.1. Khi nào dùng composite type?

- Schema payload ổn định.
- Cần tái sử dụng định nghĩa typed record.
- Dùng trong nhiều function/query.
- Có nested composite/array.

Không nhất thiết tạo composite type cho một object tạm chỉ dùng một lần; `jsonb_to_record` thường gọn hơn.

## 22. jsonb_populate_recordset

Với kiểu `json_lab.order_header_type` đã tạo:

~~~sql
SELECT *
FROM jsonb_populate_recordset(
    NULL::json_lab.order_header_type,
    '[
      {
        "order_id":2001,
        "customer_id":601,
        "ordered_at":"2026-11-01T10:00:00Z",
        "status":"new"
      },
      {
        "order_id":2002,
        "customer_id":602,
        "ordered_at":"2026-11-02T11:00:00Z",
        "status":"paid"
      }
    ]'::jsonb
);
~~~

Trả nhiều rows cùng composite type.

| Hàm | Số record | Nơi quy định cấu trúc |
|---|---|---|
| `jsonb_to_record` | Một | `AS x(col type,...)` |
| `jsonb_to_recordset` | Nhiều | `AS x(col type,...)` |
| `jsonb_populate_record` | Một | Composite type của base |
| `jsonb_populate_recordset` | Nhiều | Composite type của base |

Các phiên bản `json_...` nhận `json` thay cho `jsonb`.

## 23. Nested object: giữ JSONB hoặc tách ra

Ví dụ:

~~~json
{
  "order_id":1001,
  "customer":{"id":501,"name":"Lan"}
}
~~~

**Giữ object nested:**

~~~sql
SELECT x.order_id, x.customer
FROM jsonb_to_record(
    '{
      "order_id":1001,
      "customer":{"id":501,"name":"Lan"}
    }'::jsonb
) AS x(order_id BIGINT, customer JSONB);
~~~

**Tách object nested thành cột:**

~~~sql
WITH src AS (
    SELECT '{
      "order_id":1001,
      "customer":{"id":501,"name":"Lan"}
    }'::jsonb AS doc
)
SELECT
    (doc ->> 'order_id')::BIGINT AS order_id,
    c.id AS customer_id,
    c.name AS customer_name
FROM src
CROSS JOIN LATERAL jsonb_to_record(
    doc -> 'customer'
) AS c(id BIGINT, name TEXT);
~~~

Nếu chỉ cần một field, biểu thức `doc #>> '{customer,name}'` có thể đơn giản hơn tạo composite riêng.

## 24. Nested arrays: mở nhiều tầng

Payload:

~~~json
{
  "shipment_id":9001,
  "packages":[
    {
      "package_code":"PK-1",
      "items":[{"sku":"A","qty":2},{"sku":"B","qty":3}]
    },
    {
      "package_code":"PK-2",
      "items":[{"sku":"C","qty":1}]
    }
  ]
}
~~~

Có thể mở hai cấp mảng:

~~~sql
WITH src AS (
    SELECT '{
      "shipment_id":9001,
      "packages":[
        {
          "package_code":"PK-1",
          "items":[
            {"sku":"A","qty":2},
            {"sku":"B","qty":3}
          ]
        },
        {
          "package_code":"PK-2",
          "items":[{"sku":"C","qty":1}]
        }
      ]
    }'::jsonb AS doc
)
SELECT
    (s.doc ->> 'shipment_id')::BIGINT AS shipment_id,
    p.ordinality AS package_no,
    p.pkg ->> 'package_code' AS package_code,
    i.ordinality AS item_no,
    x.sku,
    x.qty
FROM src AS s
CROSS JOIN LATERAL jsonb_array_elements(
    s.doc -> 'packages'
) WITH ORDINALITY AS p(pkg, ordinality)
CROSS JOIN LATERAL jsonb_array_elements(
    p.pkg -> 'items'
) WITH ORDINALITY AS i(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    i.item
) AS x(sku TEXT, qty INTEGER)
ORDER BY p.ordinality, i.ordinality;
~~~

Kết quả có 3 item rows, kèm vị trí package/item.

### 24.1. Cardinality explosion

Nếu 100 packages mỗi package có 1000 items, một document mở thành 100.000 rows. Nếu JOIN sai sang bảng nhiều hàng, số hàng có thể còn tăng gấp bội. Luôn tính số phần tử, lọc nguồn đúng phạm vi và dùng `EXPLAIN` khi dữ liệu lớn.

## 25. JSON array và SQL array là hai cấu trúc khác nhau

JSON array:

~~~sql
SELECT '["red","blue","green"]'::jsonb;
~~~

SQL array:

~~~sql
SELECT ARRAY['red','blue','green']::TEXT[];
~~~

Để chuyển JSON array sang `TEXT[]` có thứ tự rõ:

~~~sql
SELECT COALESCE(
    array_agg(value ORDER BY ordinality),
    ARRAY[]::TEXT[]
) AS sql_tags
FROM jsonb_array_elements_text(
    '["red","blue","green"]'::jsonb
) WITH ORDINALITY AS x(value, ordinality);
~~~

Để chuyển SQL array sang JSONB:

~~~sql
SELECT to_jsonb(
    ARRAY['red','blue','green']::TEXT[]
) AS json_tags;
~~~

`array_agg` trên 0 rows trả SQL NULL, nên `COALESCE` hữu ích nếu muốn SQL empty array. Không nhầm `'{}'::TEXT[]` hoặc `ARRAY[]::TEXT[]` với JSON array `'[]'::jsonb`.

## 26. Chuyển object key–value động thành typed rows

Ví dụ điểm số:

~~~json
{"math":8.5,"java":9.0,"sql":8.0}
~~~

~~~sql
SELECT
    key AS subject,
    value::NUMERIC(3,1) AS score
FROM jsonb_each_text(
    '{"math":8.5,"java":9.0,"sql":8.0}'::jsonb
) AS x(key, value)
ORDER BY key;
~~~

Đối với object có trường động, `jsonb_each_text` là lựa chọn tự nhiên. Nếu một value không thể cast thành NUMERIC, query có thể lỗi.

Đối với cấu trúc nghiệp vụ có field names cố định, các cột typed thường dễ áp dụng constraint hơn kiểu key–value tự do.

## 27. row_to_json: một SQL row thành JSON object

~~~sql
SELECT row_to_json(x) AS doc
FROM (
    SELECT
        1001::BIGINT AS order_id,
        501::BIGINT AS customer_id,
        'paid'::TEXT AS status
) AS x;
~~~

Kết quả:

~~~json
{"order_id":1001,"customer_id":501,"status":"paid"}
~~~

Tên cột trong subquery trở thành tên JSON keys. Nếu muốn tên khác, alias cột.

### 27.1. row_to_json trả json

`row_to_json` trả kiểu `json`. Khi muốn JSONB, có thể ép:

~~~sql
SELECT row_to_json(x)::jsonb
FROM (
    SELECT 1001::BIGINT AS order_id
) AS x;
~~~

Hoặc dùng `to_jsonb(x)` trực tiếp.

## 28. to_json và to_jsonb: SQL value thành JSON

~~~sql
SELECT
    to_jsonb(1001::BIGINT) AS numeric_json,
    to_jsonb(TRUE) AS boolean_json,
    to_jsonb(ARRAY[10,20,30]) AS array_json;
~~~

Composite row:

~~~sql
SELECT to_jsonb(x) AS doc
FROM (
    SELECT
        1001::BIGINT AS order_id,
        'paid'::TEXT AS status
) AS x;
~~~

Kết quả logic:

~~~json
{"order_id":1001,"status":"paid"}
~~~

### 28.1. Serialize cả table row

~~~sql
SELECT to_jsonb(o) AS doc
FROM json_lab.orders AS o
ORDER BY o.order_id;
~~~

Trả tất cả các cột của orders, gồm `source_payload`.

**Không dùng `to_jsonb(o)` không chọn lọc cho API public** nếu bảng có trường nội bộ hoặc nhạy cảm. Schema có thể thêm cột sau này và response vô tình tiết lộ dữ liệu.

Chỉ lấy public columns qua subquery, hoặc dùng `jsonb_build_object` đặt keys rõ ràng.

## 29. jsonb_build_object: tự đặt key/value

~~~sql
SELECT jsonb_build_object(
    'order_id', 1001,
    'status', 'paid',
    'amount', 126000.00,
    'priority', TRUE
) AS doc;
~~~

Kết quả logic:

~~~json
{
  "order_id":1001,
  "status":"paid",
  "amount":126000,
  "priority":true
}
~~~

Hàm nhận các đối số xen kẽ **key/value**, trả JSONB object. `json_build_object` trả kiểu JSON.

### 29.1. Tạo object từ cột SQL

~~~sql
SELECT jsonb_build_object(
    'id', o.order_id,
    'customer_id', o.customer_id,
    'status', o.status,
    'ordered_at', o.ordered_at
) AS doc
FROM json_lab.orders AS o
ORDER BY o.order_id;
~~~

Đây là cách thiết kế output schema có kiểm soát, không bị ảnh hưởng bởi việc thêm cột nội bộ vào bảng.

### 29.2. Không cố lưu nhiều values qua duplicate keys

JSONB object chỉ có một value cho một key. Nếu cần lưu nhiều giá trị cùng tên, dùng JSON array hoặc array các objects.

## 30. jsonb_agg: nhiều rows thành JSON array

~~~sql
SELECT jsonb_agg(
    jsonb_build_object(
        'sku', x.sku,
        'quantity', x.quantity
    )
    ORDER BY x.sku
) AS items
FROM (
    VALUES
        ('BOOK-01'::TEXT, 2::INTEGER),
        ('PEN-02'::TEXT, 3::INTEGER)
) AS x(sku, quantity);
~~~

Kết quả:

~~~json
[
  {"sku":"BOOK-01","quantity":2},
  {"sku":"PEN-02","quantity":3}
]
~~~

`jsonb_agg` trả JSONB array. `json_agg` trả JSON array.

### 30.1. Thứ tự phải nằm trong aggregate

Không trông chờ rows đi vào `jsonb_agg` theo thứ tự vật lý hoặc một index scan tình cờ. Để giữ thứ tự:

~~~sql
jsonb_agg(expression ORDER BY sort_column)
~~~

Khi output là JSON array, **ORDER BY trong aggregate** là kỹ thuật quan trọng.

### 30.2. Tập rỗng

`jsonb_agg` trên **0 rows** thường trả SQL NULL, không tự trả `[]`.

~~~sql
SELECT COALESCE(
    jsonb_agg(x.value),
    '[]'::jsonb
)
FROM (
    SELECT 1 AS value
    WHERE FALSE
) AS x;
~~~

Trả JSON array rỗng.

### 30.3. Một hàng NULL khác 0 rows

Nếu aggregate một hàng SQL NULL, có thể tạo JSON array chứa phần tử `null`. Không nhầm nó với mảng rỗng. Điều này đặc biệt quan trọng sau LEFT JOIN.

## 31. jsonb_object_agg: nhiều cặp key/value thành object

~~~sql
SELECT
    jsonb_object_agg(x.key, x.value) AS attributes
FROM (
    VALUES
        ('red'::TEXT, 5::INTEGER),
        ('blue'::TEXT, 8::INTEGER)
) AS x(key, value);
~~~

Kết quả logic:

~~~json
{"red":5,"blue":8}
~~~

### 31.1. NULL key

JSON object key phải có tên. Nếu SQL key là NULL, aggregate có thể báo lỗi. Nên validate/filter key NULL:

~~~sql
-- Mẫu với bảng attributes giả định:
SELECT jsonb_object_agg(key, value)
FROM attributes
WHERE key IS NOT NULL;
~~~

### 31.2. Duplicate key

Nếu nhiều rows cùng key, JSONB không thể giữ hai values dưới cùng key. Không dựa vào order ngầm để quyết định value nào được giữ. Cần:

- Unique constraint.
- Deduplicate có policy và tie-breaker xác định.
- Hoặc chuyển thành array nếu key có nhiều values hợp lệ.

### 31.3. Object rỗng

Với 0 rows, dùng:

~~~sql
COALESCE(
    jsonb_object_agg(key, value),
    '{}'::jsonb
)
~~~

để trả object rỗng theo API contract.

## 32. Xuất các items của từng order thành JSON array

~~~sql
SELECT
    i.order_id,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'sku', i.sku,
                'quantity', i.quantity,
                'unit_price', i.unit_price
            )
            ORDER BY i.line_no
        ),
        '[]'::jsonb
    ) AS items
FROM json_lab.order_items AS i
GROUP BY i.order_id
ORDER BY i.order_id;
~~~

Với sample data:

- Order 1001 có hai item objects.
- Order 1002 có một item object.

`ORDER BY i.line_no` được đặt **trong jsonb_agg** để giữ thứ tự từ JSON source.

### 32.1. Khi order không có items

Nếu bắt đầu từ bảng `order_items`, order không có items không xuất hiện. Muốn xuất cả empty orders, bắt đầu từ `orders` và dùng LEFT JOIN hoặc correlated subquery.

## 33. Tạo JSON object nested cho từng order

~~~sql
SELECT
    jsonb_build_object(
        'order_id', o.order_id,
        'customer_id', o.customer_id,
        'ordered_at', o.ordered_at,
        'status', o.status,
        'items', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'sku', i.sku,
                        'quantity', i.quantity,
                        'unit_price', i.unit_price
                    )
                    ORDER BY i.line_no
                ),
                '[]'::jsonb
            )
            FROM json_lab.order_items AS i
            WHERE i.order_id = o.order_id
        )
    ) AS order_document
FROM json_lab.orders AS o
ORDER BY o.order_id;
~~~

Một kết quả logic:

~~~json
{
  "order_id":1001,
  "customer_id":501,
  "ordered_at":"2026-11-01T10:15:00+00:00",
  "status":"paid",
  "items":[
    {"sku":"BOOK-01","quantity":2,"unit_price":45000.00},
    {"sku":"PEN-02","quantity":3,"unit_price":12000.00}
  ]
}
~~~

Cách hiển thị timestamp và thứ tự object keys có thể khác theo PostgreSQL/session/JSONB serialization. Điều quan trọng là ý nghĩa của các giá trị.

### 33.1. Vì sao correlated subquery phù hợp?

- Mỗi order được giữ một lần.
- `items` được aggregate theo khóa order_id.
- Không có items → `[]` nhờ `COALESCE`.
- Tránh vô tình nhân bản item khi JOIN thêm các bảng một-nhiều khác.

Trên dữ liệu lớn, cần `EXPLAIN` và index phù hợp để quyết định chiến lược hiệu năng. Không khẳng định correlated subquery luôn nhanh hơn mọi dạng JOIN.

## 34. LEFT JOIN và lỗi sinh [null]

Một cách khác là JOIN rồi GROUP BY:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'sku', i.sku,
                'quantity', i.quantity,
                'unit_price', i.unit_price
            )
            ORDER BY i.line_no
        ) FILTER (WHERE i.order_id IS NOT NULL),
        '[]'::jsonb
    ) AS items
FROM json_lab.orders AS o
LEFT JOIN json_lab.order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id, o.customer_id
ORDER BY o.order_id;
~~~

**Tại sao cần FILTER?**

Với order không có item, LEFT JOIN vẫn sinh một hàng parent và các cột child NULL. Nếu aggregate nguyên hàng đó, ta có thể nhận object `{"sku":null,...}` hoặc `[null]`, chứ không phải mảng rỗng.

`FILTER (WHERE i.order_id IS NOT NULL)` loại hàng child giả; `COALESCE` chuyển aggregate không có input thành `[]`.

### 34.1. COUNT(*) sau LEFT JOIN

`COUNT(*)` có thể là 1 cho order không có child vì hàng parent vẫn được giữ. Nếu muốn đếm child, dùng `COUNT(i.order_id)` hoặc cột NOT NULL khác ở child.

## 35. Đóng gói tất cả orders thành JSON array

Có thể xây JSON object của từng order trước, sau đó aggregate thành một array:

~~~sql
WITH order_docs AS (
    SELECT
        o.order_id,
        jsonb_build_object(
            'order_id', o.order_id,
            'status', o.status,
            'items', (
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'sku', i.sku,
                            'quantity', i.quantity,
                            'unit_price', i.unit_price
                        )
                        ORDER BY i.line_no
                    ),
                    '[]'::jsonb
                )
                FROM json_lab.order_items AS i
                WHERE i.order_id = o.order_id
            )
        ) AS doc
    FROM json_lab.orders AS o
)
SELECT jsonb_build_object(
    'orders',
    COALESCE(
        jsonb_agg(doc ORDER BY order_id),
        '[]'::jsonb
    )
) AS response
FROM order_docs;
~~~

Output shape:

~~~json
{
  "orders":[
    {"order_id":1001,"status":"paid","items":[...]},
    {"order_id":1002,"status":"new","items":[...]}
  ]
}
~~~

Đây là cách tổng hợp hai tầng:

1. `items` theo `line_no`.
2. `orders` theo `order_id`.

Không sử dụng cách này để gom hàng triệu orders thành một JSONB value khổng lồ trong API thông thường; cần phân trang/streaming.

## 36. Cách xuất object map theo key động

Ví dụ output:

~~~json
{"1001":"paid","1002":"new"}
~~~

~~~sql
SELECT COALESCE(
    jsonb_object_agg(
        o.order_id::TEXT,
        o.status
    ),
    '{}'::jsonb
) AS order_status_map
FROM json_lab.orders AS o;
~~~

Cast `order_id::TEXT` làm rõ rằng JSON object keys là chuỗi. Nếu đầu vào bị duplicate order_id do JOIN, kết quả có thể bất định theo cách duplicate được xử lý; bảo đảm nguồn duy nhất trước khi aggregate.

## 37. JSON null trong chiều SQL → JSON

~~~sql
SELECT jsonb_build_object(
    'id', 1,
    'note', NULL
) AS doc;
~~~

Trả object chứa `"note":null`.

Nếu API contract yêu cầu bỏ keys có giá trị null:

~~~sql
SELECT jsonb_strip_nulls(
    jsonb_build_object(
        'id', 1,
        'note', NULL
    )
) AS doc;
~~~

Kết quả logic:

~~~json
{"id":1}
~~~

### 37.1. [] khác null và key thiếu

Ba payload:

~~~json
{"items":[]}
~~~

~~~json
{"items":null}
~~~

~~~json
{}
~~~

có thể có semantics khác nhau: danh sách rỗng, chưa biết/không áp dụng, hoặc trường không được cung cấp. Không dùng `jsonb_strip_nulls` hay `COALESCE` làm thay đổi API contract mà chưa quyết định chính sách.

## 38. Distinct, duplicate rows và nhiều JOIN

Nếu muốn JSON array các tags duy nhất:

~~~sql
WITH tags(tag) AS (
    VALUES
        ('A'::TEXT),
        ('B'::TEXT),
        ('A'::TEXT)
),
unique_tags AS (
    SELECT DISTINCT tag
    FROM tags
)
SELECT COALESCE(
    jsonb_agg(tag ORDER BY tag),
    '[]'::jsonb
)
FROM unique_tags;
~~~

Kết quả `["A","B"]`.

**Nhưng đừng dùng DISTINCT tùy tiện.** Hai order lines có cùng SKU nhưng khác line_no vẫn có thể là hai dòng hợp lệ. Xóa duplicate sẽ làm mất nghiệp vụ.

### 38.1. Join multiplication

Nếu một order có 3 items và 2 payments, JOIN order → items → payments có thể tạo 6 hàng. `jsonb_agg(items)` sẽ lặp item.

Giải pháp:

~~~text
orders
  +--> aggregate items riêng GROUP BY order_id
  +--> aggregate payments riêng GROUP BY order_id
  +--> JOIN hai kết quả đã aggregate
~~~

Không dùng DISTINCT như biện pháp duy nhất để vá join sai vì nó có thể xóa dữ liệu thực sự khác nhau về identity.

## 39. Giữ thứ tự đi–về

Để round-trip JSON arrays đúng thứ tự:

~~~text
JSON array đầu vào
         |
         v
jsonb_array_elements WITH ORDINALITY
         |
         v
Lưu line_no (1,2,3,...) vào SQL table
         |
         v
SELECT child rows theo order_id
         |
         v
jsonb_agg(jsonb_build_object(...) ORDER BY line_no)
         |
         v
JSON array đầu ra có thứ tự mong muốn
~~~

Một query ngoài cùng có `ORDER BY order_id` chỉ sắp các **hàng kết quả SQL**, không tự sắp những elements bên trong `jsonb_agg`. Luôn đặt ORDER BY tại đúng cấp cần bảo đảm thứ tự.

## 40. Round-trip không bảo đảm giống từng byte

JSON → SQL → JSON có thể biến đổi biểu diễn:

- JSONB không giữ whitespace ban đầu.
- JSONB không bảo toàn thứ tự object keys.
- Duplicate object keys bị chuẩn hóa.
- `NUMERIC(12,2)` có scale/rounding theo kiểu SQL.
- `TIMESTAMPTZ` được biểu diễn theo timezone của session.
- Các trường thiếu/không khai báo có thể bị bỏ đi.
- JSON null/missing có thể thành cùng SQL NULL nếu mất thông tin key presence.

Ví dụ round-trip typed fields:

~~~sql
WITH src AS (
    SELECT '{"order_id":1001,"status":"paid"}'::jsonb AS doc
),
typed AS (
    SELECT x.*
    FROM src
    CROSS JOIN LATERAL jsonb_to_record(
        src.doc
    ) AS x(order_id BIGINT, status TEXT)
)
SELECT to_jsonb(typed) AS rebuilt
FROM typed;
~~~

Ở ví dụ đơn giản, hai object có thể bằng nhau theo **JSONB semantic equality**. Nhưng với các trường không được ánh xạ, nested types hoặc precision changes, output không nhất thiết bằng input.

Nếu cần lưu bản tin pháp lý/audit nguyên gốc, lưu raw payload theo chính sách riêng, không dùng round-trip typed làm bằng chứng bảo toàn text.

## 41. Tính tổng tiền trực tiếp từ recordset

Không cần nhập bảng typed mới dùng được SQL aggregation:

~~~sql
WITH lines AS (
    SELECT
        (d.payload ->> 'order_id')::BIGINT AS order_id,
        i.quantity,
        i.unit_price
    FROM json_lab.incoming_documents AS d
    CROSS JOIN LATERAL jsonb_to_recordset(
        d.payload -> 'items'
    ) AS i(
        sku TEXT,
        quantity INTEGER,
        unit_price NUMERIC(12,2)
    )
)
SELECT
    order_id,
    SUM(quantity * unit_price) AS total_amount
FROM lines
GROUP BY order_id
ORDER BY order_id;
~~~

Kết quả:

| order_id | total_amount |
|---:|---:|
| 1001 | 126000.00 |
| 1002 | 89000.00 |

Dùng `jsonb_to_recordset` vì không cần line_no ở phép tổng hợp này. Nếu cần bảo toàn thứ tự hoặc xử lý từng item theo vị trí, dùng `jsonb_array_elements WITH ORDINALITY`.

## 42. Hiệu năng: recordset hay ->>?

Hai cách đều hợp lệ:

~~~sql
SELECT
    (payload ->> 'order_id')::BIGINT AS order_id,
    payload ->> 'status' AS status
FROM json_lab.incoming_documents;
~~~

và:

~~~sql
SELECT
    x.order_id,
    x.status
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS x(
    order_id BIGINT,
    status TEXT
);
~~~

`jsonb_to_record` thuận tiện khi trích nhiều trường typed; toán tử `->>` có thể gọn cho 1–2 trường. Không khẳng định một cách luôn nhanh hơn.

Những yếu tố chi phí thường quan trọng:

- Bao nhiêu documents cần mở?
- Mỗi document có bao nhiêu phần tử?
- Predicate có lọc trước không?
- Có ép kiểu nhiều lần không?
- Có JOIN làm tăng cardinality?
- Output JSON có quá lớn không?
- Có index phù hợp cho điều kiện lọc parent?

## 43. GIN và expression indexes trên JSONB

Một index GIN trên JSONB:

~~~sql
CREATE INDEX idx_incoming_payload_gin
ON json_lab.incoming_documents
USING GIN (payload);
~~~

có thể hỗ trợ những predicate phù hợp, ví dụ containment:

~~~sql
SELECT doc_id
FROM json_lab.incoming_documents
WHERE payload @> '{"status":"paid"}'::jsonb;
~~~

Hoặc expression index cho text value:

~~~sql
CREATE INDEX idx_incoming_status
ON json_lab.incoming_documents (
    (payload ->> 'status')
);
~~~

để phục vụ:

~~~sql
SELECT doc_id
FROM json_lab.incoming_documents
WHERE payload ->> 'status' = 'paid';
~~~

### 43.1. GIN không tự tăng tốc mọi lần mở mảng

Index có thể giúp **giảm số documents nguồn phải xử lý**, nhưng `jsonb_to_recordset(payload->'items')` vẫn phải mở mảng của từng document được chọn.

Nếu thường JOIN và lọc theo order_id, customer_id, status, các cột SQL typed và B-tree indexes tương ứng có thể có lợi hơn việc parse JSONB liên tục.

### 43.2. Cẩn thận expression index có cast

Một expression index kiểu `((payload->>'order_id')::BIGINT)` có thể thất bại khi xây index nếu có hàng chứa `order_id` không chuyển được. Validate nguồn trước khi tạo index hoặc thiết kế cột typed.

## 44. Lọc trước khi mở mảng lớn

Với nhiều documents, tránh mở toàn bộ mảng rồi mới kiểm tra thông tin parent.

~~~sql
SELECT
    d.doc_id,
    i.sku,
    i.quantity
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_recordset(
    d.payload -> 'items'
) AS i(
    sku TEXT,
    quantity INTEGER
)
WHERE d.payload ->> 'status' = 'paid';
~~~

Optimizer có thể áp dụng predicate parent sớm theo kế hoạch, nhưng cần `EXPLAIN` để xem khi query phức tạp. Có thể lọc trong subquery/CTE để diễn đạt rõ input set nếu cần.

### 44.1. Không parse trường không sử dụng

Nếu query chỉ cần `sku` và `quantity`, đừng khai báo hàng chục field nested không sử dụng chỉ vì input có chúng. Càng nhiều cast/đối tượng trung gian, càng có khả năng tăng overhead.

## 45. EXPLAIN với Function Scan/LATERAL

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    d.doc_id,
    i.sku,
    i.quantity
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_recordset(
    d.payload -> 'items'
) AS i(
    sku TEXT,
    quantity INTEGER
)
WHERE d.payload ->> 'status' = 'paid';
~~~

Có thể gặp:

- `Seq Scan`/`Index Scan` trên staging.
- `Function Scan` trên `jsonb_to_recordset`.
- `Nested Loop` giữa parent rows và function output.
- `Aggregate` và `Sort` nếu nhóm/định thứ tự.

Đọc `estimated rows`, `actual rows`, `loops`, buffers và execution time. Với các arrays có độ dài rất khác nhau, ước lượng số rows trung gian có thể khó chính xác.

`EXPLAIN ANALYZE` thực thi query; khi dùng với INSERT/UPDATE/DELETE, nó thực hiện thay đổi thật. Chỉ benchmark DML trong môi trường test có kiểm soát.

## 46. Khi nào nên phân trang/streaming?

Một query gom hàng triệu rows:

~~~sql
SELECT jsonb_agg(to_jsonb(x))
FROM enormous_table AS x;
~~~

có thể gây:

- Aggregate state lớn.
- CPU/memory cao.
- Network payload lớn.
- Thời gian phản hồi và timeout cao.
- Khó retry khi lỗi gần cuối.
- Giới hạn kích thước dữ liệu JSONB/result.

Thay vì xuất toàn bộ thành một value:

1. Chọn orders theo keyset pagination.
2. Xuất từng batch.
3. Dùng stream/cursor phù hợp.
4. Dùng `COPY` cho bulk export khi thích hợp.
5. Xây JSON nested chỉ cho tập parent được chọn.

Ví dụ giới hạn trước khi aggregate:

~~~sql
WITH selected_orders AS (
    SELECT
        order_id,
        customer_id,
        status
    FROM json_lab.orders
    WHERE order_id > 0
    ORDER BY order_id
    LIMIT 100
)
SELECT COALESCE(
    jsonb_agg(to_jsonb(o) ORDER BY o.order_id),
    '[]'::jsonb
)
FROM selected_orders AS o;
~~~

Trong API thật, cursor/page boundary và snapshot semantics cần được thiết kế để không bỏ/trùng dữ liệu khi dữ liệu thay đổi đồng thời.

## 47. Validation theo nhiều lớp

JSON từ client là **untrusted input**. Nên kiểm tra:

| Lớp | Ví dụ |
|---|---|
| Cú pháp | JSON parse/cast được |
| Root shape | Object hay array đúng |
| Field presence | Có order_id, items không |
| Field JSON type | items thật sự là array |
| SQL type | quantity là integer hợp lệ |
| Domain | quantity > 0, price >= 0 |
| Uniqueness | order_id/line_no không trùng |
| Referential integrity | order_id/customer_id hợp lệ |
| Authorization | Client được thao tác đúng order/tenant |
| Resource limits | Kích thước JSON và số phần tử hợp lý |
| Idempotency | Batch chạy lại không chèn/cộng trùng |

Một JSON document hợp lệ về cú pháp không đồng nghĩa hợp lệ về nghiệp vụ.

### 47.1. Lỗi cast có thể abort cả statement

Nếu một item trong array có `quantity="abc"`, `jsonb_to_recordset` ép sang INTEGER có thể lỗi. PostgreSQL không tự trả 99 items hợp lệ còn lại rồi bỏ item sai.

Nếu muốn xử lý từng hàng lỗi:

- Nạp raw JSON vào staging.
- Mở từng phần tử bằng `jsonb_array_elements WITH ORDINALITY`.
- Kiểm tra JSON type và format trước khi cast.
- Lưu vị trí/item lỗi vào bảng báo cáo.
- Chỉ INSERT những hàng được validation chấp nhận.
- Giữ FK/CHECK/UNIQUE làm lớp bảo vệ cuối.

### 47.2. Đừng chỉ dùng regex thay cho type validation

Một chuỗi toàn chữ số vẫn có thể vượt phạm vi INTEGER/BIGINT. Cần kiểm tra range và lỗi chuyển kiểu theo kiểu đích.

## 48. JDBC: bind JSON vào recordset

Trong Java, không nối JSON raw vào SQL string. Dùng bind parameters:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JsonItemReader {
    public void readItems(
        Connection connection,
        String jsonArray
    ) throws SQLException {
        String sql = """
            SELECT x.sku, x.quantity, x.unit_price
            FROM jsonb_to_recordset(CAST(? AS jsonb))
            AS x(
                sku text,
                quantity integer,
                unit_price numeric(12,2)
            )
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setString(1, jsonArray);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    String sku = rs.getString("sku");
                    int quantity = rs.getInt("quantity");
                    java.math.BigDecimal price =
                        rs.getBigDecimal("unit_price");
                    // Xử lý từng item đã được ánh xạ kiểu.
                }
            }
        }
    }
}
~~~

Ví dụ giả định Java 17+, PostgreSQL JDBC driver và Connection đã cấu hình.

### 48.1. SQL NULL với getInt

`ResultSet.getInt` trả primitive int. Khi cột SQL NULL, giá trị nhận có thể là 0; dùng `rs.wasNull()` hoặc getter nullable tương ứng khi cần phân biệt. Đối với quantity bắt buộc, nên kiểm tra NOT NULL/positive trước.

### 48.2. Không truyền identifier bằng bind parameter

`?` là giá trị, không biến thành tên bảng/cột SQL. Nếu cấu trúc query động, phải whitelist identifier/template; không ghép raw input chưa tin cậy.

## 49. Bulk import và batch idempotency

Khi nhập nhiều JSON documents:

~~~text
API / file
   |
   v
Kiểm tra giới hạn kích thước + authorization
   |
   v
Raw JSONB staging kèm batch_id
   |
   v
Validate root/items/typed fields
   |
   v
Phân loại lỗi, duplicate và conflicts
   |
   v
BEGIN
   |
   +--> Upsert order headers theo policy
   +--> Insert/replace items theo snapshot/delta semantics
   +--> Lưu checkpoint và audit
   |
   v
COMMIT
~~~

**Không tự động DELETE những items không xuất hiện trong một batch delta**. Nếu nguồn gửi full snapshot, cần xác định phạm vi và đầy đủ của snapshot mới được quyết định replace.

Cũng không cho rằng vì dùng JSONB mà transaction, FK, unique constraints hoặc authorization trở nên không cần thiết.

## 50. Những sai lầm thường gặp

### Sai lầm 1 — Dùng recordset cho object đơn

`jsonb_to_recordset` cần array; object đơn dùng `jsonb_to_record`.

### Sai lầm 2 — Dùng record cho array

Đầu vào nhiều objects nên dùng recordset hoặc mở array từng phần tử.

### Sai lầm 3 — Quên khai báo AS columns

Hàm trả `record` cần danh sách cột typed.

### Sai lầm 4 — Tưởng ->> trả numeric

`->>` trả TEXT; cần cast/record conversion.

### Sai lầm 5 — Tự map camelCase sang snake_case

Key names không tự chuyển; cần alias/normalize.

### Sai lầm 6 — Nhầm JSON null và key thiếu

`->>` có thể trả SQL NULL cho cả hai; khi cần phân biệt dùng `?` và `jsonb_typeof`.

### Sai lầm 7 — COALESCE xử lý mọi JSON null

Không. JSONB null khác SQL NULL.

### Sai lầm 8 — Dùng jsonb_each với array

`jsonb_each` cho object; `jsonb_array_elements` cho array.

### Sai lầm 9 — Dựa vào thứ tự rows sau recordset

SQL rows không có order mặc định; dùng ordinality và ORDER BY.

### Sai lầm 10 — CROSS JOIN LATERAL vẫn giữ parent có mảng rỗng

Không. Cần LEFT JOIN LATERAL nếu muốn giữ parent.

### Sai lầm 11 — jsonb_agg tự trả []

Với 0 rows, aggregate thường trả SQL NULL. Dùng COALESCE.

### Sai lầm 12 — LEFT JOIN tạo array một item NULL

Dùng FILTER để bỏ child placeholder.

### Sai lầm 13 — jsonb_object_agg nhận NULL key

Key NULL không hợp lệ; validate/filter.

### Sai lầm 14 — Duplicate object keys biểu diễn nhiều values

JSONB giữ một value cho key; dùng array nếu cần.

### Sai lầm 15 — ORDER BY ngoài aggregate sắp được JSON array

Phải dùng ORDER BY trong `jsonb_agg`.

### Sai lầm 16 — Serialize toàn hàng public API

Có thể lộ internal columns; whitelist keys.

### Sai lầm 17 — Record conversion tự áp business constraints

Cần CHECK/FK/UNIQUE, validation và auth.

### Sai lầm 18 — Một item lỗi sẽ tự được bỏ qua

Cast lỗi có thể làm cả statement thất bại.

### Sai lầm 19 — JOIN một-nhiều trước aggregate làm JSON lặp items

Aggregate từng quan hệ con riêng trước khi JOIN.

### Sai lầm 20 — DISTINCT chữa mọi duplicate

Có thể xóa các dòng hợp lệ khác nhau theo identity.

### Sai lầm 21 — GIN index tự tối ưu mọi recordset

Index có thể lọc parent, không làm biến mất chi phí mở array.

### Sai lầm 22 — Gom hàng triệu rows thành một JSONB response

Tốn memory/network; cần paging/streaming.

### Sai lầm 23 — Round-trip phải bằng từng byte JSON text

JSONB/type conversion chuẩn hóa biểu diễn; so semantics.

### Sai lầm 24 — Mọi JSON timestamp đều rõ timezone

Timestamp không có offset có thể phụ thuộc session/contract; yêu cầu ISO 8601 kèm timezone khi cần instant.

### Sai lầm 25 — Dữ liệu JSON hợp lệ thì có quyền sửa order đó

Authorization/tenant scoping phải độc lập với parse.

### Sai lầm 26 — Reimport đồng nghĩa có thể INSERT lại

Có thể duplicate PK; cần batch ID, conflict policy và idempotency.

### Sai lầm 27 — Import items trước headers

Foreign key có thể từ chối.

### Sai lầm 28 — Dùng FLOAT cho tiền không xét rounding

Cân nhắc NUMERIC phù hợp.

### Sai lầm 29 — Filter sau khi expand một array khổng lồ

Có thể tạo nhiều rows trung gian; lọc parent khi thích hợp.

### Sai lầm 30 — EXPLAIN ANALYZE DML luôn vô hại

Nó thực thi DML thật; chỉ thử trong test an toàn.

## 51. Checklist chuyển JSON thành SQL

1. Input là `json` hay `jsonb`?
2. Root là object hay array?
3. Object/array nested ở key nào?
4. Có kiểm tra JSON types trước recordset/array_elements?
5. Các field bắt buộc có mặt?
6. Key missing, JSON null và SQL NULL có khác semantics không?
7. Cột SQL đích dùng đúng kiểu và range?
8. Có field names camelCase/case-sensitive?
9. Có cần giữ thứ tự mảng bằng WITH ORDINALITY?
10. CROSS JOIN hay LEFT JOIN LATERAL phù hợp?
11. Source có duplicate business keys không?
12. Có CHECK/PK/FK/authorization/idempotency?
13. Dữ liệu nhập là snapshot hay delta?
14. Có giới hạn payload/array size?
15. Có cơ chế ghi nhận lỗi theo doc_id/ordinality?
16. Có transaction để bảo đảm tính nhất quán header/items?

## 52. Checklist chuyển SQL thành JSON

1. Output là object, array hay object nested?
2. Các keys được xuất có được whitelist không?
3. Có tránh lộ cột nội bộ/PII không?
4. Các cột NUMERIC/TIMESTAMPTZ có đúng contract?
5. Đã đặt ORDER BY bên trong jsonb_agg?
6. Những hàng con vắng mặt nên tạo [] hay null?
7. LEFT JOIN có sinh child placeholder không?
8. Có FILTER và COALESCE cần thiết?
9. Nhiều JOIN có làm nhân bản items?
10. Duplicate keys có chính sách rõ?
11. Có phân trang trước khi aggregate?
12. Có đối soát row count/totals/identity?
13. Có xử lý NULL theo contract?
14. Có giới hạn response size/network?
15. Có đo EXPLAIN/BUFFERS nếu payload lớn?

## 53. Bài tập thực hành

### Bài 1 — Một object

Chuyển `{"id":1,"name":"An"}` thành `id INTEGER, name TEXT`.

**Gợi ý:** `jsonb_to_record(... ) AS x(id integer,name text)`.

### Bài 2 — Mảng objects

Chuyển `[{"id":1},{"id":2}]` thành hai hàng.

**Gợi ý:** `jsonb_to_recordset`.

### Bài 3 — json và jsonb

Nêu hai khác biệt về duplicate keys, whitespace hoặc indexing.

**Gợi ý:** jsonb chuẩn hóa và hỗ trợ nhiều toán tử/index.

### Bài 4 — -> và ->>

`payload->>'quantity'` trả kiểu gì?

**Gợi ý:** TEXT, không phải INTEGER.

### Bài 5 — Cast số

Chuyển `[{"price":12000.50}]` thành `NUMERIC(12,2)`.

**Gợi ý:** dùng recordset với column definition list.

### Bài 6 — Thiếu trường

JSON thiếu `quantity` nhưng khai báo quantity INTEGER thì giá trị thường là gì?

**Gợi ý:** SQL NULL.

### Bài 7 — Key thừa

JSON có extra_field không khai báo trong AS. Nó có tự thành cột mới không?

**Gợi ý:** không.

### Bài 8 — JSON null

Phân biệt `{"note":null}` và `{}` bằng cách nào?

**Gợi ý:** `?` và `jsonb_typeof`.

### Bài 9 — Mảng rỗng

`jsonb_to_recordset('[]'::jsonb)` trả bao nhiêu hàng?

**Gợi ý:** 0.

### Bài 10 — Ordinality

Mở `["A","B","C"]` kèm chỉ số 1,2,3.

**Gợi ý:** `jsonb_array_elements_text WITH ORDINALITY`.

### Bài 11 — LATERAL

Tại sao function mở `d.payload->'items'` tham chiếu được từng hàng d?

**Gợi ý:** LATERAL.

### Bài 12 — Mảng rỗng ở LEFT JOIN

Làm sao vẫn giữ order nếu items rỗng?

**Gợi ý:** LEFT JOIN LATERAL ... ON TRUE.

### Bài 13 — Object key/value

Chuyển `{"A":10,"B":20}` thành các hàng key/value.

**Gợi ý:** `jsonb_each_text`.

### Bài 14 — Composite type

`jsonb_to_record` khác `jsonb_populate_record` ở đâu?

**Gợi ý:** column list so với base composite type.

### Bài 15 — Composite recordset

Chuyển array JSON vào `json_lab.order_header_type`.

**Gợi ý:** `jsonb_populate_recordset(NULL::json_lab.order_header_type, ...)`.

### Bài 16 — Nested object

Lấy customer.name từ JSON nested.

**Gợi ý:** `#>> '{customer,name}'`.

### Bài 17 — Nested arrays

Shipment có packages, mỗi package có items. Cần mở bao nhiêu lớp mảng?

**Gợi ý:** hai jsonb_array_elements.

### Bài 18 — SQL array

Chuyển `["red","blue"]` sang TEXT[] có thứ tự.

**Gợi ý:** `array_agg(value ORDER BY ordinality)`.

### Bài 19 — to_jsonb

Chuyển `ARRAY[1,2,3]` thành JSONB array.

**Gợi ý:** `to_jsonb`.

### Bài 20 — row_to_json

Chuyển row có order_id, status thành JSON object.

**Gợi ý:** `row_to_json(alias)` hoặc `to_jsonb(alias)`.

### Bài 21 — build_object

Tạo object với keys id, status, active.

**Gợi ý:** `jsonb_build_object`.

### Bài 22 — jsonb_agg

Gom hàng sản phẩm thành JSON array có thứ tự SKU.

**Gợi ý:** `jsonb_agg(... ORDER BY sku)`.

### Bài 23 — Empty aggregate

Vì sao cần `COALESCE(jsonb_agg(...),'[]'::jsonb)`?

**Gợi ý:** 0 rows cho SQL NULL.

### Bài 24 — LEFT JOIN child placeholder

Vì sao JSON output có một object với sku NULL khi order không có items? Cách sửa?

**Gợi ý:** `FILTER (WHERE i.order_id IS NOT NULL)`.

### Bài 25 — Order preservation

Làm sao output items theo line_no?

**Gợi ý:** ORDER BY bên trong jsonb_agg.

### Bài 26 — Object map

Tạo object `order_id::TEXT → status`.

**Gợi ý:** `jsonb_object_agg`.

### Bài 27 — NULL object key

Có thể aggregate SQL NULL thành JSON object key không?

**Gợi ý:** không; cần validate.

### Bài 28 — Round-trip

Vì sao JSON text không bảo đảm giống từng byte sau typed conversion?

**Gợi ý:** JSONB canonicalization, numeric/timestamp formatting.

### Bài 29 — Validation

`{"quantity":-5}` chuyển thành INTEGER được không? Có hợp lệ với CHECK(quantity>0) không?

**Gợi ý:** chuyển kiểu được, nhưng constraint từ chối.

### Bài 30 — Cast lỗi

Một item có quantity="abc" có chắc các item khác vẫn được INSERT không?

**Gợi ý:** không; statement có thể lỗi toàn bộ.

### Bài 31 — GIN index

GIN index trên payload có tự làm recordset nhanh hơn với mọi input không?

**Gợi ý:** không; chủ yếu hỗ trợ predicate lọc phù hợp.

### Bài 32 — JSON output lớn

Vì sao không nên jsonb_agg hàng triệu orders thành một response?

**Gợi ý:** memory, latency và network.

### Bài 33 — Authorization

Có thể tin customer_id/tenant_id trong JSON client để sửa mọi order không?

**Gợi ý:** không; cần quyền và scope.

### Bài 34 — DISTINCT

Hai order lines cùng SKU nhưng khác line_no có được tự DISTINCT không?

**Gợi ý:** không khi là hai dòng hợp lệ.

### Bài 35 — JOIN multiplication

Một order có 3 items, 2 payments; JOIN cả hai rồi aggregate items có rủi ro gì?

**Gợi ý:** tạo 6 hàng trung gian; aggregate từng nhánh riêng.

## 54. Câu hỏi thường gặp

### Nên dùng json hay jsonb?

JSONB thường tiện cho truy vấn/index/biến đổi; JSON phù hợp khi cần giữ gần nguyên văn bản đầu vào. Không có lựa chọn tốt nhất cho mọi ứng dụng.

### jsonb_to_recordset có giữ thứ tự JSON array không?

Tập SQL không có thứ tự bảo đảm nếu thiếu ORDER BY. Nếu thứ tự là yêu cầu, dùng jsonb_array_elements WITH ORDINALITY và lưu vị trí.

### jsonb_to_record tự tìm ra kiểu SQL từ JSON không?

Không. Nó cần AS column definitions. jsonb_populate_record dùng composite type của base.

### Có chuyển nested objects được không?

Có, bằng JSONB columns, LATERAL/record conversion, JSON paths hoặc composite types. Chọn dựa trên fields cần.

### Key thiếu khác JSON null thế nào?

Về JSONB có thể phân biệt; khi chuyển thành SQL record hoặc dùng ->>, cả hai có thể thành SQL NULL. Cần kiểm tra key presence nếu nghiệp vụ phụ thuộc khác biệt.

### Round-trip có bảo toàn nguyên văn JSON input không?

Không bảo đảm. JSONB và SQL types có thể chuẩn hóa biểu diễn. Hãy kiểm tra semantics và business fields.

### jsonb_agg có phù hợp export hàng triệu hàng không?

Thường cần phân trang/batch/streaming thay vì một JSONB aggregate quá lớn.

### Có nên lưu mọi thuộc tính vào JSONB thay vì cột SQL?

Các trường linh hoạt có thể phù hợp JSONB; những trường ổn định cần FK, CHECK, JOIN, index và analytics thường được quản lý dễ hơn bằng typed columns. Có thể kết hợp.

### Vì sao một recordset lỗi khi một phần tử sai?

Một phép chuyển kiểu thất bại có thể làm toàn statement lỗi. Nếu cần xử lý riêng từng item, lưu raw staging, mở từng phần tử và validate trước cast.

## 55. Tổng kết

- **JSON object → một typed row:** `jsonb_to_record` / `json_to_record`.
- **JSON array of objects → nhiều typed rows:** `jsonb_to_recordset` / `json_to_recordset`.
- **JSON theo composite type có sẵn:** `jsonb_populate_record` / `jsonb_populate_recordset`.
- **JSON array → từng phần tử:** `jsonb_array_elements`; thêm `WITH ORDINALITY` nếu cần giữ vị trí.
- **Hàng cha + mảng con:** `CROSS JOIN LATERAL` hoặc `LEFT JOIN LATERAL` theo việc muốn bỏ/giữ parent khi mảng rỗng.
- **JSON object key/value → rows:** `jsonb_each` và `jsonb_each_text`.
- **`->` trả JSON(B), `->>` trả TEXT**; muốn kiểu số/thời gian thì phải cast hoặc dùng hàm record typed.
- JSON null, SQL NULL và key thiếu khác nhau; `COALESCE` không tự thay JSONB null bằng [].
- **SQL row → JSON object:** `row_to_json` / `to_jsonb`.
- **SQL values → JSON object tùy biến:** `jsonb_build_object`.
- **SQL rows → JSON array:** `jsonb_agg`; **SQL key/value rows → JSON object:** `jsonb_object_agg`.
- **ORDER BY trong jsonb_agg** quyết định thứ tự JSON array; `WITH ORDINALITY` giữ thứ tự input.
- **FILTER + COALESCE** giúp tránh child placeholder và trả [] khi không có items.
- Nested JSON xuất từ nhiều bảng nên aggregate từng quan hệ con đúng khóa để tránh JOIN multiplication.
- Typed conversion không thay constraints, authorization, idempotency hay validation.
- JSONB indexing có thể giúp lọc nguồn, không tự tăng tốc mọi thao tác mở mảng.
- Round-trip qua JSONB/SQL types không bảo đảm văn bản JSON giống byte-for-byte.
- Với dữ liệu lớn, lọc sớm, giới hạn input/output, phân trang và quan sát kế hoạch thực thi.

Tư duy cốt lõi là **xác định đúng hình dạng dữ liệu trước và sau chuyển đổi**: một object hay mảng, một hàng hay nhiều hàng, một parent hay nhiều child. Khi tách đúng mỗi tầng, PostgreSQL cho phép kết hợp tính linh hoạt của JSON với sức mạnh kiểu dữ liệu, JOIN, aggregate và ràng buộc của mô hình quan hệ một cách rõ ràng, có kiểm soát và hữu ích cho cả ETL lẫn API.
