# Trích xuất JSON bằng toán tử theo khóa và đường dẫn trong PostgreSQL

Trong một hệ thống bán hàng, mỗi đơn hàng có thể chứa thông tin khách hàng, địa chỉ, các dòng sản phẩm, nhãn phân loại và thuộc tính linh hoạt. Nếu lưu một phần dữ liệu đó trong cột `jsonb`, bạn có thể truy vấn một thuộc tính sâu bên trong tài liệu mà không cần đưa toàn bộ JSON về Java để phân tích.

Ví dụ, với tài liệu:

~~~json
{
  "customer": {
    "id": 101,
    "name": "An",
    "address": {"city": "Hà Nội"}
  },
  "items": [
    {"sku": "BOOK-01", "qty": 2},
    {"sku": "PEN-01", "qty": 1}
  ],
  "paid": true
}
~~~

PostgreSQL hỗ trợ những cách lấy giá trị rất ngắn gọn:

~~~sql
-- Giá trị JSON/JSONB con:
SELECT payload -> 'customer' FROM orders;

-- Chuỗi SQL text:
SELECT payload -> 'customer' ->> 'name' FROM orders;

-- JSON/JSONB tại một đường dẫn nhiều cấp:
SELECT payload #> '{customer,address,city}' FROM orders;

-- Text tại đường dẫn nhiều cấp:
SELECT payload #>> '{customer,address,city}' FROM orders;
~~~

Điểm quan trọng nhất là phân biệt **toán tử trả JSON/JSONB** với **toán tử trả text**, **khóa object** với **vị trí trong array**, và **khóa không tồn tại** với **JSON null** hay **SQL NULL**. Khi những khác biệt này được hiểu đúng, bạn mới có thể ép kiểu, lọc, join, lập index và xử lý dữ liệu không đồng nhất một cách an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích JSON và JSONB, biết khi nào nên dùng mỗi kiểu.
2. Dùng `->` và `->>` để trích xuất theo **khóa object** hoặc **chỉ số phần tử array**.
3. Dùng `#>` và `#>>` với một **đường dẫn `text[]`** xuyên qua nhiều cấp object/array.
4. Viết chuỗi truy cập lồng nhau như `payload -> 'customer' -> 'address' ->> 'city'`.
5. Phân biệt đầu ra `jsonb`, `json`, `text`, `boolean`, `numeric` sau các phép chuyển kiểu.
6. Xử lý đúng **khóa thiếu**, **JSON null**, **SQL NULL**, **array rỗng**, **sai kiểu** và **chỉ số ngoài phạm vi**.
7. Truy vấn những khóa có dấu chấm, dấu cách, dấu phẩy hoặc ký tự đặc biệt mà không nhầm với ký pháp đường dẫn.
8. Trích xuất phần tử mảng theo vị trí và biến mảng JSON thành tập hàng bằng `jsonb_array_elements`/`LATERAL`.
9. Dùng `jsonb_typeof` để kiểm tra kiểu trước khi ép sang số, boolean hoặc timestamp.
10. Phân biệt đường dẫn `text[]` của `#>`/`#>>` với **SQL/JSON path** bắt đầu bằng `$`.
11. Viết điều kiện `WHERE`, `ORDER BY` và index biểu thức trên giá trị lấy từ JSON.
12. Nhận biết khi nào B-tree expression index hay GIN index phù hợp, thay vì lập index sai loại.
13. Sử dụng tham số truy vấn an toàn trong ứng dụng Java/JDBC, tránh nối trực tiếp khóa/đường dẫn từ người dùng thành SQL.
14. Hoàn thành các bài tập tình huống về tài liệu JSON lồng nhau trong PostgreSQL.

## 2. JSON và JSONB: nền tảng cần biết

PostgreSQL có hai kiểu dữ liệu lưu tài liệu JSON:

| Tiêu chí | `json` | `jsonb` |
| --- | --- | --- |
| Lưu trữ | Giữ nội dung văn bản JSON sau kiểm tra cú pháp | Lưu dạng nhị phân đã phân tích và chuẩn hóa |
| Whitespace/order khóa | Giữ nguyên những chi tiết trình bày của input | Không bảo đảm giữ nguyên whitespace/thứ tự khóa |
| Khóa trùng trong object | Có thể giữ khóa trùng ở văn bản lưu | Không giữ khóa trùng như các cặp riêng; giá trị cuối được dùng |
| Phép đọc/truy vấn | Có các toán tử trích xuất | Có các toán tử trích xuất và nhiều toán tử/index hỗ trợ hơn |
| Index cho cấu trúc JSON | Hạn chế hơn | Có thể dùng GIN cho containment/key/path queries |
| Tình huống thường gặp | Cần giữ văn bản JSON gốc ở mức phù hợp | Truy vấn/cập nhật tài liệu JSON thường xuyên |

Trong đa số ứng dụng cần tìm kiếm theo field JSON, **`jsonb` là điểm bắt đầu hợp lý**. Nhưng không thể đánh đồng JSONB với một bảng quan hệ được schema ràng buộc chặt: nếu không có constraint hoặc validation, hai hàng có thể có cùng field mang các kiểu hoàn toàn khác nhau.

### 2.1. Tạo giá trị JSON và JSONB

~~~sql
SELECT
    '{"name":"An","age":20}'::json AS as_json,
    '{"name":"An","age":20}'::jsonb AS as_jsonb;
~~~

Các phép cast `::json` và `::jsonb` buộc PostgreSQL kiểm tra cú pháp tài liệu. Một chuỗi sai JSON sẽ phát sinh lỗi thay vì được lưu như một object hợp lệ.

### 2.2. JSON value và SQL value không giống nhau

~~~sql
SELECT
    pg_typeof('{"x":1}'::jsonb) AS column_type,
    pg_typeof('{"x":1}'::jsonb -> 'x') AS json_result_type,
    pg_typeof('{"x":1}'::jsonb ->> 'x') AS text_result_type;
~~~

Kết quả về **kiểu SQL** tương ứng:

| Biểu thức | Kiểu SQL |
| --- | --- |
| `'{"x":1}'::jsonb` | `jsonb` |
| `'{"x":1}'::jsonb -> 'x'` | `jsonb` |
| `'{"x":1}'::jsonb ->> 'x'` | `text` |

Giá trị JSON `1` là một **JSON number**; khi dùng `->>`, PostgreSQL trả chuỗi SQL `'1'`. Muốn tính toán số học, cần một bước kiểm tra/ép kiểu phù hợp.

### 2.3. Đừng dùng JSONB thay cho mọi cột quan hệ

Khóa chính đơn hàng, quan hệ khóa ngoại, tiền, thời điểm nghiệp vụ và các trường được truy vấn rất thường xuyên nhiều khi phù hợp với cột có kiểu rõ ràng hơn. JSONB thích hợp cho cấu trúc linh hoạt hoặc thuộc tính ít đồng nhất; không nên tự động chuyển mọi dữ liệu vào một blob JSONB rồi ép kiểu ở mọi query.

## 3. Bộ dữ liệu lab dùng xuyên suốt bài

Các ví dụ dưới đây thuộc schema riêng `json_lab_307`. Chỉ chạy các lệnh tạo bảng/ghi dữ liệu trên database lab hoặc môi trường được phép. Nếu schema đã tồn tại, đổi tên thay vì xóa dữ liệu không rõ nguồn gốc.

### 3.1. Tạo bảng

~~~sql
CREATE SCHEMA json_lab_307;

CREATE TABLE json_lab_307.orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB
);
~~~

`payload` cố ý **cho phép SQL NULL** để minh họa trường hợp không có tài liệu JSON. Hệ thống production có thể dùng `payload JSONB NOT NULL` và constraint kiểm tra root phải là object.

### 3.2. Nạp tài liệu có object, array, null và khóa thiếu

~~~sql
INSERT INTO json_lab_307.orders
    (order_id, created_at, payload)
VALUES
(
    1,
    TIMESTAMPTZ '2026-11-12 09:00:00+07',
    $json$
    {
      "customer": {
        "id": 101,
        "name": "An",
        "contact": {"email": "An@Example.com"},
        "address": {
          "city": "Hà Nội",
          "postal_code": "100000"
        }
      },
      "items": [
        {"sku": "BOOK-01", "qty": 2, "price": 120000},
        {"sku": "PEN-01",  "qty": 1, "price": 15000}
      ],
      "tags": ["new", "vip"],
      "paid": true,
      "total": 255000,
      "coupon": null,
      "note": "",
      "a.b": {"x y": "special-value"}
    }
    $json$::jsonb
),
(
    2,
    TIMESTAMPTZ '2026-11-13 11:30:00+07',
    $json$
    {
      "customer": {
        "id": 102,
        "name": "Bình",
        "contact": {"email": "binh@example.com"},
        "address": {"city": "Đà Nẵng"}
      },
      "items": [
        {"sku": "MOUSE-01", "qty": 1, "price": 320000}
      ],
      "tags": [],
      "paid": false,
      "total": 320000,
      "coupon": "WELCOME"
    }
    $json$::jsonb
),
(
    3,
    TIMESTAMPTZ '2026-11-14 08:00:00+07',
    $json$
    {
      "customer": {
        "id": 103,
        "name": "Chi",
        "address": {"city": "TP Hồ Chí Minh"}
      },
      "items": [],
      "tags": ["vip"],
      "paid": true,
      "total": 0
    }
    $json$::jsonb
),
(
    4,
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    $json$
    {
      "customer": {
        "id": 104,
        "name": "Dũng",
        "address": null
      },
      "items": null,
      "paid": true,
      "total": 50000
    }
    $json$::jsonb
),
(
    5,
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    $json$
    {
      "customer": {
        "id": 105,
        "name": "Em"
      },
      "items": {"sku": "NOT-AN-ARRAY"},
      "tags": ["trial"],
      "paid": false,
      "total": "50000",
      "coupon": null
    }
    $json$::jsonb
),
(
    6,
    TIMESTAMPTZ '2026-11-14 11:00:00+07',
    NULL
);
~~~

**Chủ ý của lab:**

| order_id | Tình huống |
| ---: | --- |
| 1 | Object nhiều cấp, 2 phần tử array, JSON null, chuỗi rỗng, khóa `a.b` và `x y` |
| 2 | Array một phần tử, `tags=[]`, boolean false, coupon là chuỗi |
| 3 | `items=[]`, thiếu `contact` và `coupon` |
| 4 | `address=null` và `items=null` (JSON null), không có `tags` |
| 5 | `items` là object chứ không phải array; `total` là JSON string thay vì number |
| 6 | `payload` là **SQL NULL** chứ không phải JSON object |

Các hàng bất thường (4–6) có tác dụng dạy cách **đọc an toàn khi cấu trúc thay đổi**. Không nên mặc định mọi JSON sản xuất đều có một schema thống nhất nếu database không thực thi yêu cầu đó.

### 3.3. Xem kiểu dữ liệu gốc

~~~sql
SELECT
    order_id,
    pg_typeof(payload) AS sql_type,
    jsonb_typeof(payload) AS json_root_type
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Các hàng 1–5 có root `object`; hàng 6 trả SQL NULL cho cả `payload` và `jsonb_typeof(payload)`.

## 4. Bốn toán tử trích xuất trọng tâm

| Toán tử | Toán hạng phải | Cách hoạt động | Kiểu SQL trả về với `jsonb` |
| --- | --- | --- | --- |
| `->` | `text` (khóa) hoặc `integer` (array index) | Lấy giá trị con, giữ dạng JSON | `jsonb` |
| `->>` | `text` hoặc `integer` | Lấy giá trị con dưới dạng text | `text` |
| `#>` | `text[]` (đường dẫn nhiều phần tử) | Lấy JSON tại đường dẫn | `jsonb` |
| `#>>` | `text[]` | Lấy text tại đường dẫn | `text` |

Nếu **nguồn là `json`** thay vì `jsonb`, `->` và `#>` trả về `json`; còn `->>` và `#>>` vẫn trả `text`. PostgreSQL không bắt buộc tự đổi toàn bộ tài liệu thành `jsonb` chỉ vì bạn truy cập một field.

### 4.1. Ví dụ tối giản

~~~sql
SELECT
    '{"x":{"value":42}}'::jsonb -> 'x'
        AS nested_object,
    '{"x":{"value":42}}'::jsonb ->> 'x'
        AS nested_object_as_text,
    '{"x":{"value":42}}'::jsonb #> '{x,value}'
        AS json_number,
    '{"x":{"value":42}}'::jsonb #>> '{x,value}'
        AS text_number;
~~~

Diễn giải:

| Cột | Giá trị mô tả | Kiểu |
| --- | --- | --- |
| `nested_object` | `{"value": 42}` | `jsonb` |
| `nested_object_as_text` | Chuỗi SQL biểu diễn object JSON | `text` |
| `json_number` | JSON number `42` | `jsonb` |
| `text_number` | Chuỗi SQL `'42'` | `text` |

**`->>` không chỉ dành cho JSON string**. Nó còn biểu diễn JSON number, boolean, object và array dưới dạng text; nếu muốn truy cập tiếp cấu trúc lồng nhau, hãy **giữ JSON bằng `->`/`#>` trước**, rồi chỉ đổi ra text ở cấp cuối.

### 4.2. Sơ đồ chọn toán tử

~~~mermaid
flowchart TD
    A["Cần đọc dữ liệu trong JSON/JSONB"] --> B{"Truy cập một cấp hay nhiều cấp?"}
    B -->|Một cấp| C{"Muốn JSON hay SQL text?"}
    C -->|JSON| D["->"]
    C -->|text| E["->>"]
    B -->|Nhiều cấp| F{"Đường dẫn đã là text[]?"}
    F -->|Có| G{"Muốn JSON hay text?"}
    F -->|Không| H["Có thể nối nhiều toán tử ->"]
    G -->|JSON| I["#>"]
    G -->|text| J["#>>"]
    H --> K["Ở cấp cuối dùng ->> để lấy text"]
~~~

## 5. Toán tử ->: lấy JSON theo khóa

~~~sql
SELECT
    order_id,
    payload -> 'customer' AS customer_json,
    payload -> 'items' AS items_json,
    payload -> 'paid' AS paid_json
FROM json_lab_307.orders
WHERE order_id IN (1, 2)
ORDER BY order_id;
~~~

Với order 1:

- `payload -> 'customer'` là một **JSON object**.
- `payload -> 'items'` là một **JSON array**.
- `payload -> 'paid'` là một **JSON boolean** `true`, **không phải SQL boolean**.

### 5.1. Giữ JSON để truy cập tiếp

~~~sql
SELECT
    payload -> 'customer' -> 'address' AS address_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Kết quả là JSON object có `city` và `postal_code`.

~~~sql
SELECT
    payload -> 'customer' -> 'address' -> 'city'
        AS city_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Kết quả vẫn là JSON string (ví dụ hiển thị `"Hà Nội"`, có dấu ngoặc kép của JSON).

### 5.2. Toán tử theo khóa chỉ xem cấp hiện tại

~~~sql
SELECT
    payload -> 'city' AS top_level_city,
    payload -> 'customer' -> 'address' -> 'city'
        AS nested_city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`payload -> 'city'` trả **SQL NULL** vì ở root không có khóa `city`. PostgreSQL không tự tìm đệ quy mọi khóa cùng tên trong tất cả object lồng nhau.

### 5.3. Phân biệt kiểu kết quả

~~~sql
SELECT
    pg_typeof(payload -> 'customer') AS customer_type,
    jsonb_typeof(payload -> 'customer') AS customer_json_kind,
    pg_typeof(payload -> 'paid') AS paid_sql_type,
    jsonb_typeof(payload -> 'paid') AS paid_json_kind
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`pg_typeof` nói **kiểu cột/biểu thức PostgreSQL**; `jsonb_typeof` nói **kiểu giá trị bên trong JSON**.

## 6. Toán tử ->>: lấy SQL text theo khóa

~~~sql
SELECT
    order_id,
    payload ->> 'paid' AS paid_as_text,
    payload ->> 'total' AS total_as_text
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 5)
ORDER BY order_id;
~~~

Trong output, `paid_as_text` là chuỗi `'true'` hoặc `'false'`; `total_as_text` là chuỗi số. Ngay cả khi JSON gốc có `"total":255000` (number), `->>` vẫn trả `text`.

### 6.1. Khi nào chọn ->>?

Thường dùng khi:

- Muốn SELECT text như tên khách hàng/email/city;
- Muốn so sánh chuỗi trong `WHERE`;
- Muốn đưa giá trị vào `LOWER`, `BTRIM`, các hàm text;
- Muốn ép kiểu rõ ràng sang `integer`, `numeric`, `boolean` hoặc timestamp **sau khi kiểm tra schema**.

~~~sql
SELECT
    order_id,
    payload -> 'customer' ->> 'name' AS customer_name
FROM json_lab_307.orders
WHERE order_id BETWEEN 1 AND 5
ORDER BY order_id;
~~~

### 6.2. Không dùng ->> ở giữa chuỗi nếu còn muốn truy cập JSON

**Sai ý tưởng:**

~~~sql
-- payload ->> 'customer' trả text, không còn là JSONB.
-- Truy cập tiếp -> 'address' trên text sẽ lỗi kiểu toán tử.
--
-- SELECT payload ->> 'customer' -> 'address'
-- FROM json_lab_307.orders;
~~~

**Đúng:**

~~~sql
SELECT
    payload -> 'customer' -> 'address' ->> 'city'
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

**Quy tắc nhớ nhanh:** mỗi cấp trung gian dùng `->`; cấp cuối dùng `->>` nếu cần text.

### 6.3. JSON number và SQL numeric

~~~sql
SELECT
    order_id,
    payload ->> 'total' AS total_text,
    (payload ->> 'total')::numeric AS total_numeric
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3, 4, 5)
ORDER BY order_id;
~~~

Với bộ dữ liệu lab, `'50000'` của order 5 có thể ép sang numeric dù JSON gốc **là string**, nhưng điều này không chứng minh tài liệu đã tuân thủ schema. Nếu một hàng khác chứa `"total":"not-a-number"`, phép `::numeric` phát sinh lỗi.

### 6.4. JSON boolean và SQL boolean

~~~sql
SELECT
    order_id,
    payload ->> 'paid' AS paid_text,
    (payload ->> 'paid')::boolean AS paid_boolean
FROM json_lab_307.orders
WHERE order_id BETWEEN 1 AND 5
ORDER BY order_id;
~~~

Để giữ ngữ nghĩa JSON chính xác, đặc biệt với dữ liệu không đồng nhất, bạn nên kiểm tra `jsonb_typeof(payload -> 'paid') = 'boolean'` trước khi ép kiểu.

## 7. Truy cập nhiều cấp bằng chuỗi -> và ->>

JSON object lồng sâu:

~~~json
{
  "customer": {
    "contact": {
      "email": "An@Example.com"
    }
  }
}
~~~

Truy vấn:

~~~sql
SELECT
    order_id,
    payload -> 'customer' -> 'contact' ->> 'email'
        AS customer_email
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Khi một cấp trung gian không tồn tại, kết quả truy xuất thường là **SQL NULL**, không tự phát sinh lỗi chỉ vì khóa thiếu. Ví dụ order 3 có `customer` nhưng không có `contact`, nên email trả NULL.

### 7.1. Quy tắc đánh giá trái sang phải

~~~text
payload
   |
   +-- -> 'customer' : jsonb object
            |
            +-- -> 'contact' : jsonb object
                     |
                     +-- ->> 'email' : SQL text
~~~

Nếu muốn giữ email ở dạng **JSON string**, dùng `-> 'email'` ở cấp cuối thay vì `->>`.

### 7.2. Viết rõ ngoặc để dễ đọc

~~~sql
SELECT
    ((payload -> 'customer') -> 'address') ->> 'city'
        AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Với chuỗi đơn giản, PostgreSQL hỗ trợ viết liên tiếp không cần nhóm ngoặc cho từng bước. Khi trộn với cast, phép so sánh hoặc toán tử khác, **dùng dấu ngoặc để tránh mơ hồ về kiểu và precedence**.

## 8. #> và #>>: đường dẫn dạng text[]

Thay vì nhiều lần `->`, ta có thể cung cấp cả đường dẫn dưới dạng **mảng PostgreSQL kiểu `text[]`**.

~~~sql
SELECT
    order_id,
    payload #> '{customer,address,city}' AS city_json,
    payload #>> '{customer,address,city}' AS city_text
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3)
ORDER BY order_id;
~~~

Khi nguồn là `jsonb`:

- `#>` trả `jsonb`, với giá trị JSON string như `"Hà Nội"`.
- `#>>` trả `text`, với chuỗi SQL `Hà Nội` (không giữ dấu ngoặc kép JSON).

### 8.1. Đường dẫn là text[], không phải chuỗi “a.b.c”

Literal:

~~~sql
'{customer,address,city}'::text[]
~~~

đại diện **ba phần tử text**: `customer`, `address`, `city`. Đây là **cú pháp array literal của PostgreSQL**, không phải JSONPath và không phải dot notation JavaScript.

### 8.2. Cách viết ARRAY[] dễ đọc và dễ tham số hóa

~~~sql
SELECT
    payload #>> ARRAY['customer', 'address', 'city']
        AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`ARRAY['customer', 'address', 'city']` được xác định thành một `text[]` phù hợp theo ngữ cảnh toán tử; khi cần, ghi rõ `::text[]`.

~~~sql
SELECT
    payload #>> ARRAY['customer','address','city']::text[]
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

### 8.3. So sánh hai cú pháp

~~~sql
SELECT
    payload -> 'customer' -> 'address' ->> 'city'
        AS by_chaining,
    payload #>> '{customer,address,city}'
        AS by_path
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Hai biểu thức có cùng mục đích trích xuất **SQL text của city**. Không suy ra chúng có cùng cost/plan trong mọi bối cảnh; kiểm tra khi workload đủ lớn.

### 8.4. Lấy object/array con bằng #>

~~~sql
SELECT
    payload #> '{customer,address}' AS address_json,
    payload #> '{items}' AS items_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`#>` hữu ích khi bạn cần giữ một object/array để xử lý tiếp bằng JSONB functions hoặc trả nguyên cấu trúc con.

### 8.5. Đường dẫn chỉ một phần tử cũng hợp lệ

~~~sql
SELECT
    payload #> '{customer}' AS customer_json,
    payload #>> '{paid}' AS paid_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Với một khóa duy nhất, `->`/`->>` thường dễ đọc hơn, nhưng `#>`/`#>>` thuận tiện khi ứng dụng đã có đường dẫn dạng mảng động.

## 9. Truy cập phần tử JSON array bằng chỉ số

Trong PostgreSQL, **chỉ số của JSON array bắt đầu từ 0**:

~~~text
JSON array items:

[
  {"sku": "BOOK-01", "qty": 2},  ← index 0
  {"sku": "PEN-01",  "qty": 1}   ← index 1
]
~~~

### 9.1. Lấy phần tử ở vị trí 0

~~~sql
SELECT
    payload -> 'items' -> 0 AS first_item_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Kết quả là JSON object của `BOOK-01`. Dấu `-> 0` dùng **toán hạng integer**, không phải tên khóa text `'0'`.

### 9.2. Lấy field trong phần tử mảng

~~~sql
SELECT
    payload -> 'items' -> 0 ->> 'sku'
        AS first_sku,
    payload -> 'items' -> 0 ->> 'qty'
        AS first_quantity_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

| Kết quả | Giá trị | Kiểu SQL |
| --- | --- | --- |
| `first_sku` | `BOOK-01` | `text` |
| `first_quantity_text` | `2` | `text` |

Nếu cần tính số lượng:

~~~sql
SELECT
    (payload -> 'items' -> 0 ->> 'qty')::integer
        AS first_quantity
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Hãy đặt ngoặc quanh toàn bộ phép trích xuất **trước khi ép kiểu**.

### 9.3. Đường dẫn mảng bằng #> và #>>

~~~sql
SELECT
    payload #> '{items,0}' AS first_item_json,
    payload #>> '{items,0,sku}' AS first_sku,
    payload #>> '{items,1,sku}' AS second_sku
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Đường dẫn `'{items,0,sku}'` được hiểu:

1. Từ object root lấy khóa `items`;
2. Trên JSON array lấy phần tử index `0`;
3. Từ object phần tử lấy khóa `sku`.

### 9.4. Chỉ số âm lấy từ cuối mảng

Các toán tử trích xuất JSON cho phép **chỉ số âm** để đếm từ cuối mảng:

~~~sql
SELECT
    payload -> 'items' -> -1 ->> 'sku' AS last_sku,
    payload #>> '{items,-1,sku}' AS last_sku_by_path
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Ở order 1, hai biểu thức đều lấy `PEN-01`. `-1` là phần tử cuối, `-2` là phần tử áp cuối nếu tồn tại. Đừng nhầm cú pháp này với SQL array index chuẩn.

### 9.5. Chỉ số vượt phạm vi

~~~sql
SELECT
    payload -> 'items' -> 99 AS out_of_range_json,
    payload -> 'items' ->> 99 AS out_of_range_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Hai giá trị đều là **SQL NULL**. Các toán tử trích xuất JSON thường trả NULL khi không thể đi theo cấu trúc yêu cầu; chúng không tự ném lỗi chỉ vì index ngoài phạm vi.

### 9.6. Lấy phần tử cuối có số lượng thay đổi

~~~sql
SELECT
    order_id,
    payload -> 'items' -> -1 AS last_item
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3)
ORDER BY order_id;
~~~

- Order 1: item `PEN-01`.
- Order 2: item `MOUSE-01`.
- Order 3: SQL NULL vì `items=[]`.

Đây là lợi ích của negative index: không phải tính độ dài mảng trước khi lấy phần tử cuối. Tuy nhiên, nếu logic nghiệp vụ cần **mọi** phần tử, không nên cố truy cập `0`, `1`, `2` bằng số lượng chỉ số cố định; dùng **set-returning function** như `jsonb_array_elements`.

## 10. JSON array khác với PostgreSQL SQL array

Điểm rất dễ nhầm:

| Đối tượng | Ví dụ | Chỉ số |
| --- | --- | --- |
| JSON array | `'[10,20,30]'::jsonb` | **0, 1, 2** |
| PostgreSQL SQL array mặc định | `ARRAY[10,20,30]` | Thông thường **1, 2, 3** |
| `text[]` truyền vào `#>` | `ARRAY['items','0','sku']` | Các phần tử là **tên khóa/index trong JSON** |

~~~sql
SELECT
    '[10,20,30]'::jsonb -> 0 AS first_json_value,
    (ARRAY[10,20,30])[1] AS first_sql_array_value;
~~~

Để subscript một biểu thức SQL array tạo trực tiếp, dùng ngoặc quanh `ARRAY[...]`:

~~~sql
SELECT
    (ARRAY[10,20,30])[1] AS first_sql_array_value,
    '[10,20,30]'::jsonb -> 0 AS first_json_value;
~~~

Hai giá trị logic đều là `10`, nhưng một bên là `integer`, một bên là `jsonb`. SQL array còn có thể được tạo với lower bound khác 1; **đừng lấy mặc định của SQL arrays làm quy tắc cho JSON arrays**.

### 10.1. Đường dẫn text[] không được đánh chỉ số giống JSON

Trong:

~~~sql
payload #>> ARRAY['items', '0', 'sku']
~~~

`ARRAY[...]` chỉ là **vật chứa ba path components** truyền cho toán tử. Chuỗi `'0'` được PostgreSQL diễn giải như **JSON array index** tại cấp `items`, chứ không có nghĩa đang lấy phần tử `0` của chính SQL array literal.

### 10.2. Object có khóa "0" vẫn là object

~~~sql
SELECT
    '{"0":"object-value"}'::jsonb -> '0'
        AS from_object,
    '["array-value"]'::jsonb -> 0
        AS from_array;
~~~

Toán hạng `text` dùng khóa object; toán hạng `integer` dùng chỉ số JSON array. Nếu không chắc cấu trúc, kiểm tra `jsonb_typeof` trước khi trích xuất.

## 11. Khóa chứa dấu chấm, dấu cách hoặc dấu phẩy

JSON cho phép khóa là chuỗi tùy ý, không chỉ tên cột SQL hợp lệ.

Ở order 1 có:

~~~json
{
  "a.b": {
    "x y": "special-value"
  }
}
~~~

### 11.1. Dấu chấm là một phần của tên khóa

~~~sql
SELECT
    payload -> 'a.b' ->> 'x y' AS special_value
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Kết quả: `special-value`.

`'a.b'` là **một khóa nguyên vẹn**, không tự được chia thành `a` rồi `b`.

### 11.2. Dùng #>> với ARRAY[] để tránh nhầm cú pháp

~~~sql
SELECT
    payload #>> ARRAY['a.b', 'x y']::text[]
        AS special_value
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Việc xây `text[]` bằng `ARRAY[]` thường dễ hiểu hơn tự viết một literal có nhiều dấu ngoặc kép/escape, nhất là khi khóa chứa dấu phẩy, khoảng trắng, ngoặc nhọn hoặc ký tự đặc biệt.

### 11.3. Nếu một khóa chứa dấu phẩy

Ví dụ độc lập:

~~~sql
SELECT
    '{"a,b":{"c d":77}}'::jsonb
        #>> ARRAY['a,b', 'c d']::text[]
        AS extracted;
~~~

Kết quả là chuỗi text `77`. Cách này tránh nhầm dấu phẩy trong tên khóa với dấu phẩy **phân tách phần tử** của PostgreSQL array literal.

### 11.4. JSON không dùng SQL identifier quoting

Không viết:

~~~sql
-- Không đúng ngữ nghĩa khóa JSON:
-- payload -> "customer"
~~~

Trong SQL, dấu ngoặc kép `"customer"` thường là **identifier**, ví dụ tên cột. Muốn key JSON tên customer, dùng **string literal** `'customer'`, hoặc bind parameter text an toàn.

## 12. Khóa không tồn tại, JSON null và SQL NULL

Đây là phần rất quan trọng khi lọc dữ liệu JSON:

1. **Khóa không tồn tại:** object không chứa key ấy.
2. **JSON null:** object chứa key với giá trị JSON literal `null`.
3. **SQL NULL:** biểu thức/cột SQL không có giá trị, hoặc phép trích xuất không tìm thấy cấu trúc.
4. **Chuỗi "null":** JSON string `"null"` hoặc SQL text `'null'`, **khác** JSON null.
5. **Chuỗi rỗng:** `""`, **khác** null và khác khóa thiếu.

### 12.1. Xét một object chứa null và một khóa thiếu

~~~sql
SELECT
    '{"coupon":null}'::jsonb -> 'coupon'
        AS present_json_null,
    '{"coupon":null}'::jsonb -> 'missing'
        AS absent_sql_null;
~~~

- `present_json_null` là **giá trị JSONB null**, bản thân biểu thức không phải SQL NULL.
- `absent_sql_null` là **SQL NULL** vì khóa `missing` không tồn tại.

### 12.2. Kiểm tra bằng IS NULL

~~~sql
SELECT
    ('{"coupon":null}'::jsonb -> 'coupon') IS NULL
        AS json_null_is_sql_null,
    ('{"coupon":null}'::jsonb -> 'missing') IS NULL
        AS missing_is_sql_null;
~~~

| Biểu thức | Kết quả |
| --- | --- |
| `json_null_is_sql_null` | `false` |
| `missing_is_sql_null` | `true` |

**Đừng suy đoán từ cách SQL client in chữ `null`**: một số clients hiển thị SQL NULL và JSONB null giống nhau về mặt hình ảnh. Hãy dùng `IS NULL` hoặc `jsonb_typeof` để phân biệt.

### 12.3. Dùng ->> thì JSON null trở thành SQL NULL

~~~sql
SELECT
    ('{"coupon":null}'::jsonb ->> 'coupon') IS NULL
        AS json_null_text_is_null,
    ('{"coupon":null}'::jsonb ->> 'missing') IS NULL
        AS missing_text_is_null;
~~~

Hai biểu thức đều `true`. Khi trích xuất ra text bằng `->>`, bạn **không còn phân biệt được** “khóa tồn tại nhưng JSON null” với “khóa không tồn tại” chỉ bằng giá trị trả về.

### 12.4. Dùng toán tử ? để kiểm tra key tồn tại

~~~sql
SELECT
    order_id,
    payload ? 'coupon' AS has_coupon_key,
    payload -> 'coupon' AS coupon_as_json,
    payload ->> 'coupon' AS coupon_as_text
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3, 5)
ORDER BY order_id;
~~~

Kết quả về ngữ nghĩa:

| order_id | `has_coupon_key` | `coupon_as_json` | `coupon_as_text` |
| ---: | --- | --- | --- |
| 1 | true | JSON null | SQL NULL |
| 2 | true | JSON string `"WELCOME"` | `WELCOME` |
| 3 | false | SQL NULL | SQL NULL |
| 5 | true | JSON null | SQL NULL |

**`?` là toán tử hỗ trợ của `jsonb` để kiểm tra sự tồn tại ở cấp đang xét** (key của object hoặc element string top-level của array), không phải toán tử trích xuất như `->`.

### 12.5. Kiểm tra loại giá trị JSON

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload -> 'coupon') AS coupon_json_type
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3, 5)
ORDER BY order_id;
~~~

| order_id | Loại |
| ---: | --- |
| 1 | chuỗi text `null` (tên kiểu JSON null) |
| 2 | `string` |
| 3 | SQL NULL (không có key) |
| 5 | `null` |

`jsonb_typeof` trả **text mô tả JSON type** như `'object'`, `'array'`, `'string'`, `'number'`, `'boolean'`, `'null'`. Với **SQL NULL input**, kết quả là SQL NULL.

### 12.6. Tìm những hàng có khóa tồn tại và bằng JSON null

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload ? 'coupon'
  AND payload -> 'coupon' = 'null'::jsonb
ORDER BY order_id;
~~~

Kết quả: **1** và **5**.

### 12.7. Tìm những hàng thiếu khóa

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE jsonb_typeof(payload) = 'object'
  AND NOT (payload ? 'coupon')
ORDER BY order_id;
~~~

Kết quả: **3** và **4**. Hàng 6 có **SQL NULL document** nên không được coi là một object rỗng thiếu khóa; điều kiện root object loại nó ra.

Nếu ứng dụng muốn gộp cả document NULL vào nhóm “không có coupon”, phải định nghĩa rõ:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload IS NULL
   OR NOT (payload ? 'coupon')
ORDER BY order_id;
~~~

### 12.8. COALESCE che mất khác biệt nếu dùng không cẩn thận

~~~sql
SELECT
    order_id,
    COALESCE(payload ->> 'coupon', '<none>')
        AS display_coupon
FROM json_lab_307.orders
ORDER BY order_id;
~~~

`COALESCE` thuận tiện cho **hiển thị**, nhưng kết quả `'<none>'` sẽ gộp JSON null, missing key và SQL NULL thành cùng một biểu diễn. Không dùng điều này như dữ liệu kiểm toán mà yêu cầu phân biệt đủ ba trường hợp.

### 12.9. So sánh = NULL luôn sai ý định

~~~sql
-- Không tìm SQL NULL:
-- WHERE payload ->> 'coupon' = NULL
~~~

Trong SQL, so sánh thông thường với NULL cho **UNKNOWN**, không phải true. Dùng `IS NULL` hoặc `IS NOT NULL`, sau đó bổ sung `?`/`jsonb_typeof` nếu cần phân biệt JSON null và missing.

## 13. JSON string rỗng, JSON null và giá trị thiếu

Lab order 1 có `"note":""`. Câu:

~~~sql
SELECT
    payload -> 'note' AS note_json,
    payload ->> 'note' AS note_text,
    (payload ->> 'note') = '' AS is_empty_text,
    (payload ->> 'note') IS NULL AS is_sql_null
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`is_empty_text=true` nhưng `is_sql_null=false`. Một input rỗng không nên bị xử lý như không có key nếu nghiệp vụ phân biệt “người dùng cố ý xóa ghi chú” và “không cung cấp trường ghi chú”.

### 13.1. Một JSON string chứa chữ "null" cũng khác

~~~sql
SELECT
    '"null"'::jsonb AS json_string_null,
    'null'::jsonb AS json_null_value,
    jsonb_typeof('"null"'::jsonb) AS kind_1,
    jsonb_typeof('null'::jsonb) AS kind_2;
~~~

`kind_1='string'`, `kind_2='null'`. JSON number `0`, boolean `false` và string `"false"` cũng là các giá trị khác nhau.

## 14. Truy cập sâu khi cấu trúc không đúng kiểu

Các toán tử `->`/`->>`/`#>`/`#>>` thường trả **SQL NULL** khi cấu trúc tại một cấp không phù hợp, thay vì báo lỗi “object expected” cho mỗi đường dẫn sai.

Ví dụ order 4 có `"customer":{"address":null}`:

~~~sql
SELECT
    payload -> 'customer' -> 'address' AS address_value,
    payload -> 'customer' -> 'address' ->> 'city'
        AS city_text
FROM json_lab_307.orders
WHERE order_id = 4;
~~~

`address_value` là **JSON null**, còn `city_text` là **SQL NULL** vì không thể truy cập khóa `city` trên JSON null.

### 14.1. Trường không phải array

Ở order 5 có `"items":{"sku":"NOT-AN-ARRAY"}`. Câu:

~~~sql
SELECT
    payload -> 'items' -> 0 AS first_item
FROM json_lab_307.orders
WHERE order_id = 5;
~~~

không tìm được phần tử array nên trả **SQL NULL**. Nhưng lời gọi:

~~~sql
-- Trên order 5 sẽ phát sinh lỗi:
-- SELECT jsonb_array_length(payload -> 'items')
-- FROM json_lab_307.orders WHERE order_id = 5;
~~~

có thể **báo lỗi** vì `jsonb_array_length` kỳ vọng JSON array, còn input là object. Đây là khác biệt lớn: **toán tử trích xuất thường mềm dẻo khi path sai; một số hàm xử lý JSON có kiểm tra kiểu nghiêm ngặt**.

### 14.2. Không đánh giá kiểu từ “truy cập được index 0”

Nếu `payload -> 'items' -> 0` trả NULL, có thể là:

- Array rỗng;
- Index vượt giới hạn;
- Key `items` thiếu;
- Giá trị `items` là JSON null;
- `items` là object/scalar khác array;
- Cả `payload` là SQL NULL.

Nếu logic nghiệp vụ cần biết lý do, hãy truy vấn **loại cấu trúc** bằng `jsonb_typeof` và sự tồn tại khóa trước khi kết luận.

### 14.3. Kiểm tra toàn bộ các tình huống trong lab

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload) AS root_type,
    jsonb_typeof(payload -> 'items') AS items_type,
    payload -> 'items' -> 0 ->> 'sku' AS first_sku
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Kết quả:

| order_id | Root type | Items type | First SKU |
| ---: | --- | --- | --- |
| 1 | object | array | BOOK-01 |
| 2 | object | array | MOUSE-01 |
| 3 | object | array | SQL NULL |
| 4 | object | null | SQL NULL |
| 5 | object | object | SQL NULL |
| 6 | SQL NULL | SQL NULL | SQL NULL |

**Đừng dùng mỗi `first_sku IS NULL` để suy rằng khách hàng không mua hàng**: nhiều loại dữ liệu lỗi có thể tạo cùng triệu chứng.

## 15. Truy vấn lọc theo giá trị JSON text

Với cú pháp:

~~~sql
SELECT
    order_id,
    payload #>> '{customer,address,city}' AS city
FROM json_lab_307.orders
WHERE payload #>> '{customer,address,city}' = 'Hà Nội';
~~~

Kết quả: order **1**.

### 15.1. Phân biệt so sánh text và JSON

Hai biểu thức sau thể hiện những cách so sánh khác nhau:

~~~sql
-- So sánh SQL text:
SELECT order_id
FROM json_lab_307.orders
WHERE payload -> 'customer' ->> 'name' = 'An';

-- So sánh giá trị JSONB string:
SELECT order_id
FROM json_lab_307.orders
WHERE payload -> 'customer' -> 'name' = '"An"'::jsonb;
~~~

Cả hai có thể lấy order 1, nhưng bên phải phép so sánh thứ hai là **JSONB string**, có dấu ngoặc kép thuộc JSON literal. Khi làm việc với text thường, `->>` dễ đọc và dễ truyền tham số hơn.

### 15.2. So sánh boolean theo kiểu

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload -> 'paid' = 'true'::jsonb
ORDER BY order_id;
~~~

Kết quả: **1, 3, 4**. Điều kiện yêu cầu giá trị JSON boolean `true`, không phải JSON string `"true"`.

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload ->> 'paid' = 'true'
ORDER BY order_id;
~~~

Trong dữ liệu lab hai truy vấn tình cờ cho cùng nhóm. Nhưng truy vấn text có thể khớp cả JSON string `"true"` nếu tài liệu không đồng nhất. **Nếu phải kiểm soát kiểu**, hãy dùng `jsonb_typeof(payload -> 'paid') = 'boolean'` hoặc so JSONB boolean.

### 15.3. Lọc số: tránh so sánh theo thứ tự chữ

~~~sql
-- Sai về ngữ nghĩa số:
-- WHERE payload ->> 'total' > '90000'
~~~

Đây là phép so sánh **text** theo collation, không phải số học. Ví dụ chuỗi `'100000'` có thể được so khác với số 100000 theo thứ tự từ điển.

**Đúng khi dữ liệu numeric hợp lệ:**

~~~sql
SELECT
    order_id,
    (payload ->> 'total')::numeric AS total_numeric
FROM json_lab_307.orders
WHERE (payload ->> 'total')::numeric >= 100000
ORDER BY order_id;
~~~

Kết quả: **1** và **2**. Nhưng câu này chỉ an toàn khi mọi giá trị `total` có thể parse sang `numeric` hoặc SQL NULL; nếu có một chuỗi không phải số, query có thể lỗi. Phần sau sẽ đưa mẫu cast có guard.

## 16. Ép kiểu an toàn sau khi trích xuất JSON

Một nguyên tắc trong hệ thống có dữ liệu linh hoạt:

> **Đừng ép kiểu mù một giá trị trích xuất nếu field có thể bị thiếu hoặc đổi kiểu.** Xác nhận JSON type hoặc dùng validation/schema trước khi cast.

### 16.1. Numeric trong JSON khác SQL numeric

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload -> 'total') AS json_type,
    pg_typeof(payload ->> 'total') AS extracted_sql_type,
    payload ->> 'total' AS extracted_text
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Ở hàng 1–4, `total` là JSON number. Ở hàng 5, `total` là JSON **string**, mặc dù text sau khi trích xuất trông cũng như số. Hàng 6 là SQL NULL.

### 16.2. CASE bảo vệ cast theo JSON type

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END AS strict_total_numeric
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Trong ví dụ này, order 5 bị coi là **không hợp lệ về kiểu**, nên kết quả `strict_total_numeric` là SQL NULL dù chuỗi `"50000"` có thể parse được.

### 16.3. Vì sao dùng CASE thay vì hai điều kiện AND?

Một cách viết tưởng an toàn:

~~~sql
-- Không dựa vào thứ tự thực thi để bảo vệ cast:
-- WHERE jsonb_typeof(payload -> 'total') = 'number'
--   AND (payload ->> 'total')::numeric > 100000
~~~

PostgreSQL có thể sắp xếp lại cách đánh giá các biểu thức Boolean trong `WHERE` theo các quy tắc tối ưu. **Không nên dựa vào “điều kiện bên trái được chạy trước” để ngăn một cast gây lỗi**.

Khi cần bảo vệ phép chuyển kiểu có thể lỗi, đặt trong `CASE`:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END >= 100000
ORDER BY order_id;
~~~

Kết quả trên dữ liệu lab: **1, 2**.

### 16.4. Nếu business cho phép chuỗi chứa số

Một số nguồn JSON gửi `"50000"` thay vì `50000`. Nếu business cho phép cả hai, phải định nghĩa **quy tắc validation** trước khi cast.

Ví dụ chỉ chấp nhận chuỗi số không âm đơn giản, cho phép phần thập phân:

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        WHEN jsonb_typeof(payload -> 'total') = 'string'
             AND (payload ->> 'total')
                 ~ '^[0-9]+(\.[0-9]+)?$'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END AS normalized_total
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Regex chỉ là ví dụ cho **chính sách input đơn giản**, không bao phủ dấu âm, ký hiệu mũ, khoảng trắng hoặc mọi biểu diễn số hợp lệ theo nghiệp vụ. Khi cần xử lý tiền, còn phải kiểm tra **phạm vi, precision/scale, đơn vị tiền tệ và rounding**; regex không thay validation đầy đủ.

### 16.5. Ép JSON boolean đúng ngữ nghĩa

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'paid') = 'boolean'
        THEN (payload ->> 'paid')::boolean
        ELSE NULL
    END AS paid_boolean
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Nếu field `paid` là JSON string `"true"`, quy tắc này **không tự chuyển** nó thành boolean. Đó là lựa chọn có chủ đích để phát hiện dữ liệu sai schema.

### 16.6. Timestamps dạng chuỗi cần timezone

Với JSON:

~~~json
{"shipping":{"requested_at":"2026-11-14T10:30:00+07:00"}}
~~~

Cách chuyển cơ bản:

~~~sql
SELECT
    (
      '{"shipping":{"requested_at":"2026-11-14T10:30:00+07:00"}}'::jsonb
      #>> '{shipping,requested_at}'
    )::timestamptz AS requested_at;
~~~

**Cảnh báo:** `::timestamptz` có thể lỗi với chuỗi ngày sai định dạng, và string không có offset/timezone có thể bị diễn giải theo `TimeZone` session. Để lưu một instant có thể trao đổi giữa các hệ thống, nên yêu cầu định dạng chuẩn có timezone/offset rõ ràng và kiểm tra ở tầng nhận dữ liệu.

### 16.7. Không so số bằng text

~~~sql
SELECT
    ('100'::text < '9'::text) AS text_comparison,
    (100::numeric < 9::numeric) AS numeric_comparison;
~~~

Hai biểu thức có thể cho kết quả khác do một bên so ký tự, một bên so số. Khi `ORDER BY payload ->> 'total'`, PostgreSQL sắp theo **text**, không theo số học. Với nghiệp vụ tiền/số lượng, hãy dùng kiểu dữ liệu numeric/integers thích hợp.

## 17. Lấy độ dài và kiểm tra array trước khi xử lý

Hàm:

~~~sql
jsonb_array_length(jsonb_value)
~~~

trả độ dài **JSON array**. Nhưng sẽ lỗi nếu input không phải array (ví dụ object, JSON null hoặc scalar khác).

### 17.1. Trường hợp tốt

~~~sql
SELECT
    order_id,
    jsonb_array_length(payload -> 'items') AS item_count
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3)
ORDER BY order_id;
~~~

Kết quả: order 1 có 2, order 2 có 1, order 3 có 0 phần tử.

### 17.2. Guard cho toàn bộ dữ liệu

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'items') = 'array'
        THEN jsonb_array_length(payload -> 'items')
        ELSE NULL
    END AS item_count_if_array
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Đây là cách phân biệt **array hợp lệ có 0 phần tử** với **field có kiểu sai**. Nếu business muốn quy mọi giá trị không phải array thành array rỗng, có thể trả 0 ở `ELSE`, nhưng cần cân nhắc liệu như vậy có che giấu lỗi dữ liệu không.

### 17.3. COALESCE không phải phép thay thế kiểm tra kiểu

~~~sql
-- Nếu items là JSON null (khác SQL NULL), COALESCE
-- không tự thay nó bằng array rỗng:
-- jsonb_array_length(COALESCE(payload -> 'items', '[]'::jsonb))
~~~

Với order 4, `payload -> 'items'` là **JSONB null** không phải SQL NULL, nên `COALESCE` giữ nguyên giá trị JSON null và `jsonb_array_length` vẫn lỗi. **Dùng `jsonb_typeof`** nếu cần chuẩn hóa loại dữ liệu.

## 18. Trích xuất tất cả phần tử bằng jsonb_array_elements

Toán tử `-> 0` thích hợp khi cần **một vị trí cụ thể**. Để liệt kê tất cả sản phẩm trong đơn, PostgreSQL có **set-returning function**:

~~~sql
jsonb_array_elements(jsonb_array)
~~~

Nó biến các phần tử của một JSON array thành **nhiều hàng SQL**, mỗi hàng vẫn giữ kiểu `jsonb`.

### 18.1. Ví dụ đơn hàng có array hợp lệ

~~~sql
SELECT
    o.order_id,
    item.value AS item_json,
    item.value ->> 'sku' AS sku,
    (item.value ->> 'qty')::integer AS qty
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items')
    AS item(value)
WHERE o.order_id = 1;
~~~

Kết quả hai hàng:

| order_id | sku | qty |
| ---: | --- | ---: |
| 1 | BOOK-01 | 2 |
| 1 | PEN-01 | 1 |

### 18.2. LATERAL là gì?

`LATERAL` cho phép subquery hoặc table function trong `FROM` **tham chiếu cột của hàng nằm bên trái**, ở đây là `o.payload`.

~~~mermaid
flowchart LR
    A["Mỗi hàng orders o"] --> B["Lấy o.payload -> 'items'"]
    B --> C["jsonb_array_elements(...)"]
    C --> D["0..N rows JSONB"]
    D --> E["Trích sku, qty, price"]
    E --> F["Kết quả quan hệ có nhiều hàng"]
~~~

Với `CROSS JOIN LATERAL`, nếu array rỗng, table function trả 0 hàng thì **hàng order cũng không xuất hiện** trong kết quả.

### 18.3. Cẩn thận kiểu sai ở những hàng khác

Lời gọi `jsonb_array_elements(o.payload -> 'items')` có thể lỗi khi `items` là object (order 5) hoặc JSON null (order 4). **Không dựa vào điều kiện `WHERE o.order_id=1` để “chắc chắn” bảo vệ mọi query phức tạp**; với dữ liệu không đồng nhất, hãy chuẩn hóa tham số đầu vào table function.

### 18.4. LATERAL an toàn với các kiểu sai

~~~sql
SELECT
    o.order_id,
    line.item ->> 'sku' AS sku,
    line.item ->> 'qty' AS qty_text
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS line(item)
ORDER BY o.order_id, sku;
~~~

Kết quả:

| order_id | sku | qty_text |
| ---: | --- | --- |
| 1 | BOOK-01 | 2 |
| 1 | PEN-01 | 1 |
| 2 | MOUSE-01 | 1 |

Các orders 3–6 không tạo hàng item vì đầu vào được thay bằng mảng rỗng khi không phù hợp. Đây là **chính sách đọc mềm dẻo**; nếu không muốn che dữ liệu sai, cần ghi nhận `jsonb_typeof(items) != 'array'` để báo lỗi/kiểm toán ở tầng ứng dụng.

### 18.5. Giữ đơn hàng không có items bằng LEFT JOIN LATERAL

~~~sql
SELECT
    o.order_id,
    line.item ->> 'sku' AS sku
FROM json_lab_307.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS line(item)
ON TRUE
ORDER BY o.order_id, sku;
~~~

Với `LEFT JOIN LATERAL ... ON TRUE`, orders có array rỗng/không hợp lệ vẫn xuất hiện một lần với `sku` SQL NULL. Đây là công cụ hữu ích để làm báo cáo **đếm orders ngay cả khi không có item**.

### 18.6. WITH ORDINALITY: lấy vị trí phần tử

~~~sql
SELECT
    o.order_id,
    line.position AS sql_ordinality,
    line.position - 1 AS json_index,
    line.item ->> 'sku' AS sku
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items')
    WITH ORDINALITY AS line(item, position)
WHERE o.order_id = 1
ORDER BY line.position;
~~~

**`WITH ORDINALITY` đánh số từ 1**, giống thứ tự hàng SQL, còn JSON array index **bắt đầu từ 0**:

| sql_ordinality | json_index | sku |
| ---: | ---: | --- |
| 1 | 0 | BOOK-01 |
| 2 | 1 | PEN-01 |

Không gửi `position=1` trực tiếp vào toán tử `-> 1` để lấy **phần tử đầu tiên**; đó sẽ là phần tử thứ hai theo quy tắc JSON index.

### 18.7. jsonb_array_elements_text

Với mảng chỉ gồm các scalar string:

~~~sql
SELECT tag.value AS tag
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.payload -> 'tags')
    AS tag(value)
WHERE o.order_id = 1;
~~~

Kết quả: hai hàng `new` và `vip`, kiểu `text`. Khi array có object, `jsonb_array_elements_text` trả biểu diễn text của các giá trị, **không giữ object dưới dạng `jsonb` để truy cập tiếp bằng `->`**.

### 18.8. Một truy vấn tính thành tiền từng item

~~~sql
SELECT
    o.order_id,
    li.item ->> 'sku' AS sku,
    (li.item ->> 'qty')::integer AS qty,
    (li.item ->> 'price')::numeric AS unit_price,
    (li.item ->> 'qty')::integer
        * (li.item ->> 'price')::numeric
        AS line_total
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS li(item)
WHERE o.order_id IN (1, 2)
ORDER BY o.order_id, sku;
~~~

Kết quả:

| order_id | sku | qty | price | line_total |
| ---: | --- | ---: | ---: | ---: |
| 1 | BOOK-01 | 2 | 120000 | 240000 |
| 1 | PEN-01 | 1 | 15000 | 15000 |
| 2 | MOUSE-01 | 1 | 320000 | 320000 |

Với dữ liệu thực, nên validate `qty`/`price` trước khi cast và áp constraint nghiệp vụ như không âm, precision/scale, mã tiền. Ví dụ này dựa trên **những dòng items hợp lệ của lab**.

## 19. Trích object thành nhiều cột bằng jsonb_to_record

Nếu muốn ánh xạ một **JSON object** thành các cột SQL có tên và kiểu cố định, dùng `jsonb_to_record`:

~~~sql
SELECT
    o.order_id,
    customer.id,
    customer.name
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_to_record(o.payload -> 'customer')
    AS customer(id integer, name text)
WHERE o.order_id = 1;
~~~

Kết quả khách hàng ID 101, name An. PostgreSQL dùng tên field `id`/`name` để ánh xạ; field thiếu có thể thành SQL NULL, và field có kiểu/giá trị không thể convert sang kiểu SQL yêu cầu có thể báo lỗi.

### 19.1. jsonb_to_recordset cho array các object

~~~sql
SELECT
    o.order_id,
    li.sku,
    li.qty,
    li.price
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_to_recordset(o.payload -> 'items')
    AS li(sku text, qty integer, price numeric)
WHERE o.order_id IN (1, 2)
ORDER BY o.order_id, li.sku;
~~~

Khi input đúng là JSON array gồm các objects phù hợp, hàm chuyển trực tiếp thành recordset với cột typed. **Nó không phải phép thay thế vô điều kiện cho validation**: order 4/5 có `items` là JSON null/object, nên cần guard hoặc loại/ghi nhận dữ liệu không hợp lệ trước khi dùng trên toàn bảng.

### 19.2. Khi nào chọn cách nào?

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Chỉ lấy field lồng nhau | `->`, `->>`, `#>`, `#>>` |
| Truy cập một phần tử theo vị trí | `-> integer` hoặc `#> text[]` |
| Liệt kê tất cả phần tử array | `jsonb_array_elements` |
| Liệt kê array scalar dưới dạng text | `jsonb_array_elements_text` |
| Chuyển object thành cột typed | `jsonb_to_record` |
| Chuyển array objects thành bảng typed | `jsonb_to_recordset` |
| Tìm kiếm theo mẫu cấu trúc/đường dẫn | JSONPath hoặc GIN/containment khi phù hợp |

**Phần lõi vẫn là cách trích xuất**; các hàm trả tập hàng chỉ là bước mở rộng khi dữ liệu JSON chứa nhiều phần tử.

## 20. Duyệt các khóa của object với jsonb_each

Khi không biết trước tên khóa, `jsonb_each` có thể biến một object thành các hàng `(key,value)`:

~~~sql
SELECT
    kv.key,
    kv.value
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_each(o.payload -> 'customer')
    AS kv(key, value)
WHERE o.order_id = 1
ORDER BY kv.key;
~~~

Kết quả có các key như `address`, `contact`, `id` và `name`. `value` là `jsonb`, nên có thể tiếp tục dùng `->` nếu là object/array phù hợp.

### 20.1. jsonb_each_text

~~~sql
SELECT
    kv.key,
    kv.value AS text_value
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_each_text(o.payload -> 'customer')
    AS kv(key, value)
WHERE o.order_id = 1;
~~~

`value` là `text`. Các object con trở thành văn bản biểu diễn JSON; không tự trở thành những cột SQL typed hay các row con.

### 20.2. Chỉ dùng trên object phù hợp

`jsonb_each` kỳ vọng object; gọi với array/scalar có thể báo lỗi. Trong lab, `customer` của các orders 1–5 đều là object; order 6 có payload SQL NULL. Trong dữ liệu nguồn không tin cậy, kiểm tra `jsonb_typeof` trước hoặc thiết kế constraint.

## 21. text[] path và SQL/JSON path là hai cú pháp khác nhau

Đây là điểm dễ nhầm khi chuyển từ `#>`/`#>>` sang các JSONPath functions:

| Kiểu đường dẫn | Ví dụ | Sử dụng bởi |
| --- | --- | --- |
| PostgreSQL `text[]` path | `'{customer,address,city}'::text[]` | `#>`, `#>>`, `jsonb_extract_path` |
| SQL/JSON `jsonpath` | `'$.customer.address.city'::jsonpath` | `jsonb_path_query_first`, `jsonb_path_exists`, `@?`, `@@` |

**Không viết `payload #>> '$.customer.address.city'`**: toán tử `#>>` cần `text[]`, không cần `jsonpath` hay một chuỗi dot notation.

### 21.1. Cùng giá trị, hai ngôn ngữ đường dẫn

~~~sql
SELECT
    payload #>> '{customer,address,city}'
        AS city_by_text_array,
    jsonb_path_query_first(
        payload,
        '$.customer.address.city'
    ) AS city_by_jsonpath
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Điểm khác:

- `city_by_text_array` là **SQL text**.
- `jsonb_path_query_first` trả **jsonb** (JSON string).

Muốn text từ kết quả JSONPath, phải có bước chuyển phù hợp sau khi đã biết loại giá trị, hoặc dùng trích xuất dựa trên `#>>` khi path cụ thể đã biết.

### 21.2. JSONPath có wildcard, text[] path thì không

~~~sql
SELECT
    jsonb_path_query_first(
        payload,
        '$.items[*].sku'
    ) AS one_sku_as_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`[*]` là một wildcard lựa chọn các phần tử array trong JSONPath. Trong `'{items,*,sku}'::text[]`, ký tự `*` **không có nghĩa wildcard** đối với `#>`; nó được xem như một path component text và sẽ không duyệt tất cả phần tử mảng.

### 21.3. Lấy nhiều kết quả JSONPath

~~~sql
SELECT
    o.order_id,
    sku.value AS sku_json
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_path_query(
        o.payload,
        '$.items[*].sku'
    ) AS sku(value)
WHERE o.order_id = 1;
~~~

Trên order 1, hàm trả hai JSONB string `"BOOK-01"` và `"PEN-01"`. Với những truy vấn cần **cột số lượng/giá** cho mỗi object, `jsonb_array_elements` hoặc `jsonb_to_recordset` thường trực quan hơn.

### 21.4. JSONPath lax và strict

SQL/JSON path trong PostgreSQL hỗ trợ các chế độ xử lý cấu trúc **lax** và **strict**. Ở chế độ lax, hệ thống có thể tự điều chỉnh một số khác biệt cấu trúc (ví dụ bọc/mở array ở những tình huống phù hợp); strict yêu cầu cấu trúc khớp chặt hơn và có thể báo lỗi.

**Không mặc định rằng JSONPath `$.items[*].sku` và `#> '{items,0,sku}'` có cùng hành vi trên dữ liệu sai kiểu như `items` là object ở order 5.** JSONPath và toán tử dựa trên text[] path có ngữ nghĩa và độ mềm dẻo khác nhau.

### 21.5. Key có dấu chấm trong JSONPath

~~~sql
SELECT
    payload #>> ARRAY['a.b', 'x y']::text[]
        AS by_text_array,
    jsonb_path_query_first(
        payload,
        '$."a.b"."x y"'
    ) AS by_jsonpath
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Trong JSONPath, dùng dấu ngoặc kép để coi `a.b` là **một key** thay vì hai cấp đường dẫn. Lại một lần nữa, `#>>` trả text còn JSONPath function ở ví dụ trả JSONB.

### 21.6. Version support

Các JSONPath operators/functions như `@?`, `@@`, `jsonb_path_query` được giới thiệu trong PostgreSQL 12; không thể giả định chúng có ở các bản quá cũ. Bốn toán tử `->`/`->>`/`#>`/`#>>` là nền tảng phù hợp khi cần đường dẫn xác định.

## 22. Tìm dữ liệu theo đường dẫn với JSONPath và toán tử hỗ trợ

Khi chỉ muốn một giá trị cụ thể, `#>>` thường dễ đọc nhất. Khi muốn hỏi “**có phần tử nào trong mảng thỏa điều kiện không?**”, JSONPath có thể phù hợp hơn:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @? '$.items[*] ? (@.sku == "BOOK-01")'
ORDER BY order_id;
~~~

Với dữ liệu lab, kết quả là order **1**.

### 22.1. @? khác với toán tử ? đơn lẻ

- `payload ? 'coupon'`: kiểm tra key/element tồn tại **ở cấp cao nhất** của JSONB hiện tại.
- `payload @? '$.items[*] ? (...)'`: kiểm tra một **JSONPath** có trả phần tử khớp không.

Hai toán tử có tên gần giống nhưng khác loại toán hạng và ngữ nghĩa.

### 22.2. @@ kiểm tra predicate JSONPath

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @@ '$.paid == true'
ORDER BY order_id;
~~~

`@@` đánh giá một JSONPath predicate và xử lý kết quả Boolean theo ngữ nghĩa JSONPath. Với dữ liệu đồng nhất như lab, có thể lấy orders 1, 3, 4. Khác biệt về kiểu, JSON null và lax mode cần được kiểm tra trước khi dùng cho chính sách truy cập quan trọng.

### 22.3. Chọn công cụ đúng mục tiêu

Nếu chỉ đọc `customer.address.city`, không cần áp dụng một JSONPath engine chỉ vì cú pháp trông quen. Nếu cần filter phần tử mảng theo nhiều điều kiện hoặc duyệt wildcard, JSONPath có thể giảm số lượng thao tác thủ công.

### 22.4. Không ghép JSONPath không tin cậy vào SQL

JSONPath động cần được truyền dưới dạng **giá trị tham số có kiểu `jsonpath`** khi dùng trong truy vấn, không xây string SQL bằng phép nối trực tiếp đầu vào người dùng. Ngoài SQL injection, còn cần hạn chế **những đường dẫn dữ liệu người dùng được phép truy cập**, vì một JSON document có thể chứa thông tin nhạy cảm ở các nhánh khác nhau.

## 23. Hàm jsonb_extract_path và jsonb_extract_path_text

PostgreSQL cung cấp hai hàm có thể giúp diễn đạt đường dẫn dưới dạng những đối số text:

~~~sql
jsonb_extract_path(jsonb_value, VARIADIC text[])
jsonb_extract_path_text(jsonb_value, VARIADIC text[])
~~~

Về mặt mục tiêu:

- `jsonb_extract_path` tương ứng với cách trích xuất JSONB của `#>`.
- `jsonb_extract_path_text` tương ứng với cách trích xuất text của `#>>`.

### 23.1. Ví dụ nhiều đối số khóa

~~~sql
SELECT
    order_id,
    jsonb_extract_path(
        payload, 'customer', 'address', 'city'
    ) AS city_json,
    jsonb_extract_path_text(
        payload, 'customer', 'address', 'city'
    ) AS city_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

### 23.2. So sánh hàm và toán tử

~~~sql
SELECT
    payload #>> ARRAY['customer','address','city']
        AS via_operator,
    jsonb_extract_path_text(
        payload,
        'customer',
        'address',
        'city'
    ) AS via_function
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Hai cách cùng trích text `Hà Nội` trong ví dụ. Chọn cách nào dễ đọc/dễ tham số hóa hơn cho ứng dụng, sau đó xem plan nếu đây là đường truy vấn hiệu năng quan trọng.

### 23.3. Khi đã có mảng đường dẫn

~~~sql
SELECT
    jsonb_extract_path_text(
        payload,
        VARIADIC ARRAY['customer','address','city']::text[]
    ) AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Với `VARIADIC text[]`, bạn có thể chuyển mảng các path components vào hàm thay vì liệt kê lần lượt. Toán tử `#>>` thường ngắn gọn hơn:

~~~sql
SELECT
    payload #>> ARRAY['customer','address','city']::text[] AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

### 23.4. Hàm tương ứng cho kiểu json

Nếu nguồn là `json` thay vì `jsonb`, PostgreSQL có những hàm tương ứng `json_extract_path` và `json_extract_path_text`. Hãy chọn chữ ký theo kiểu thực tế; không cần convert qua `jsonb` chỉ để dùng đúng một toán tử `#>>` cơ bản.

## 24. Dùng đường dẫn động và prepared statement

Đôi khi ứng dụng cần người gọi chọn một trong các field đã được cho phép:

~~~text
customer.address.city
customer.contact.email
customer.name
~~~

Thay vì nối trực tiếp chuỗi thành SQL, có thể truyền **mảng path components**:

~~~sql
PREPARE find_orders_by_json_path(text[], text) AS
SELECT order_id
FROM json_lab_307.orders
WHERE payload #>> $1 = $2
ORDER BY order_id;

EXECUTE find_orders_by_json_path(
    ARRAY['customer','address','city']::text[],
    'Hà Nội'
);

DEALLOCATE find_orders_by_json_path;
~~~

Kết quả: order **1**.

### 24.1. Lợi ích

- Key/path được gửi như **giá trị dữ liệu**, không phải SQL source code.
- Không phải tự xây chuỗi `'{"a","b"}'` với rất nhiều escape.
- Dễ đặt giới hạn số cấp, các field được phép truy cập và kiểu kết quả.
- Giảm rủi ro SQL injection do ghép chuỗi tùy tiện.

### 24.2. Tham số hóa không tự thay authorization

Nếu ứng dụng cho phép truyền **bất kỳ đường dẫn nào** trong JSON, người dùng có thể thử đọc cả những field không dành cho họ (ví dụ dữ liệu liên hệ riêng tư hoặc metadata nội bộ).

Phải có **allowlist đường dẫn** theo API, và kiểm soát quyền trên dữ liệu SQL/JSON tương ứng. Truy vấn có bind parameter chỉ giúp SQL an toàn hơn về cú pháp; nó **không quyết định quyền nghiệp vụ**.

### 24.3. Dynamic path không đồng nghĩa index cố định luôn được dùng

Một index biểu thức trên:

~~~sql
payload #>> '{customer,address,city}'
~~~

được xây cho **một đường dẫn cụ thể**. Query có `payload #>> $1::text[]` không đương nhiên được optimizer coi là cùng biểu thức cho **mọi** giá trị `$1` trong một generic plan.

Nếu một vài field rất quan trọng cần index, tạo index rõ ràng cho những đường truy cập đó và giữ query predicate tương thích; không kỳ vọng một B-tree expression index duy nhất tăng tốc mọi đường dẫn động.

## 25. Truy vấn ORDER BY và GROUP BY trên field JSON

### 25.1. GROUP BY theo thành phố

~~~sql
SELECT
    payload #>> '{customer,address,city}' AS city,
    COUNT(*) AS orders_count
FROM json_lab_307.orders
WHERE payload IS NOT NULL
GROUP BY payload #>> '{customer,address,city}'
ORDER BY city NULLS LAST;
~~~

Các orders 4 và 5 không có city đọc được, nên vào nhóm **SQL NULL** khi grouping. Đây là ví dụ cần phân biệt **không có field** với giá trị city rỗng.

### 25.2. GROUP BY với nhãn dự phòng

~~~sql
SELECT
    COALESCE(
        payload #>> '{customer,address,city}',
        '<unknown>'
    ) AS city_bucket,
    COUNT(*) AS orders_count
FROM json_lab_307.orders
GROUP BY
    COALESCE(
        payload #>> '{customer,address,city}',
        '<unknown>'
    )
ORDER BY city_bucket;
~~~

Phù hợp cho báo cáo hiển thị, nhưng sẽ gộp city thiếu, JSON null và SQL NULL document vào `'<unknown>'`. Nếu muốn phân tích chất lượng dữ liệu, hãy tách các nhóm lỗi bằng `CASE` và `jsonb_typeof`.

### 25.3. ORDER BY số phải dùng kiểu số

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END AS total_numeric
FROM json_lab_307.orders
ORDER BY total_numeric DESC NULLS LAST, order_id;
~~~

Nếu viết `ORDER BY payload ->> 'total'`, PostgreSQL sắp **text** và có thể tạo thứ tự sai cho giá trị số.

### 25.4. Đừng mặc định mỗi path là cột có schema ổn định

Một field city có thể là text ở hàng này, object hoặc array ở hàng khác nếu không có constraint. `#>>` có thể trả text của cả một object/array; GROUP BY trên đó tạo các nhóm theo biểu diễn text, chưa chắc có ý nghĩa nghiệp vụ. Nên kiểm tra JSON type hoặc enforce schema tại nguồn.

## 26. Lập B-tree expression index cho một đường dẫn

Nếu truy vấn thành phố xuất hiện thường xuyên và bảng đủ lớn, có thể cân nhắc index biểu thức:

~~~sql
CREATE INDEX idx_orders_customer_city_307
ON json_lab_307.orders (
    (payload #>> '{customer,address,city}')
);
~~~

### 26.1. Cách dùng

~~~sql
EXPLAIN
SELECT
    order_id,
    payload #>> '{customer,address,city}' AS city
FROM json_lab_307.orders
WHERE payload #>> '{customer,address,city}' = 'Hà Nội';
~~~

Vì index lưu kết quả biểu thức `#>> '{customer,address,city}'`, PostgreSQL có thể dùng B-tree equality khi query có biểu thức tương thích.

### 26.2. Truy vấn phải khớp biểu thức index

Index `#>> '{customer,address,city}'` không tự được planner dùng trong mọi câu nhìn như tương đương:

~~~sql
WHERE payload -> 'customer' -> 'address' ->> 'city'
      = 'Hà Nội'
~~~

Hai cách có thể trả cùng kết quả cho tài liệu hợp lệ, nhưng optimizer **không có nghĩa vụ suy diễn mọi tương đương cấu trúc giữa những phép trích xuất** để khớp expression index. Trên đường truy vấn có index, nên thống nhất dạng biểu thức rồi kiểm tra `EXPLAIN`.

### 26.3. Expression index không miễn phí

Khi `INSERT`/`UPDATE` thay đổi những cột được tham chiếu, PostgreSQL phải duy trì khóa index đã trích xuất. Tạo quá nhiều index cho các JSON fields hiếm truy vấn sẽ:

- Tăng dung lượng index và WAL;
- Làm `INSERT`/`UPDATE` chậm hơn;
- Có thể giảm cơ hội HOT update;
- Tăng công việc VACUUM và bảo trì;
- Gây chi phí tính toán biểu thức trên nhiều rows.

**Không tạo index cho mọi path chỉ vì JSON có nhiều key.** Ưu tiên các predicate được truy vấn thường xuyên và có tính chọn lọc tốt.

### 26.4. Bảng lab rất nhỏ

Với chỉ sáu hàng, `EXPLAIN` có thể chọn `Seq Scan` dù index biểu thức đã tạo. Đây là **lựa chọn chi phí hợp lý**, không chứng minh index sai. Benchmark cần dữ liệu và phân bố truy vấn đại diện.

### 26.5. Index trên giá trị numeric đã trích xuất

Nếu trường `total` có schema bắt buộc là JSON number, có thể cân nhắc:

~~~sql
CREATE INDEX idx_orders_total_numeric_307
ON json_lab_307.orders (
    ((payload ->> 'total')::numeric)
);
~~~

Trong lab hiện tại, order 5 có JSON string `"50000"` vẫn parse được sang numeric, nên index này có thể tạo thành công. Nhưng một insert mới chứa `"total":"error"` sẽ làm phép tính index key lỗi và khiến statement ghi thất bại.

Nếu muốn enforce **chỉ JSON number**, cần constraint/validation rõ ràng thay vì trông đợi cast “vô tình chấp nhận” các chuỗi số.

### 26.6. Không lập chỉ mục trên hàm không IMMUTABLE

PostgreSQL yêu cầu các hàm trong expression index phải có tính bất biến thích hợp. Phép trích xuất JSON cố định từ `jsonb` thường phù hợp yêu cầu này; nhưng nếu bọc bằng UDF phụ thuộc dữ liệu bảng khác, timezone/session hoặc đồng hồ hiện tại mà khai báo `IMMUTABLE` sai, index có thể giữ khóa lỗi thời.

## 27. GIN index cho các toán tử containment và key/path

Trong một số workload, bạn không muốn tìm **một path cố định** mà muốn hỏi tài liệu JSONB có chứa cấu trúc nào đó:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @> '{"paid":true}'::jsonb
ORDER BY order_id;
~~~

`@>` là toán tử **JSONB containment**: tài liệu bên trái có chứa cấu trúc/giá trị ở bên phải hay không, theo ngữ nghĩa containment JSONB.

### 27.1. GIN trên toàn cột jsonb

~~~sql
CREATE INDEX idx_orders_payload_gin_307
ON json_lab_307.orders
USING gin (payload);
~~~

Index GIN có thể hỗ trợ các dạng tìm kiếm JSONB như containment, key existence và một số JSONPath queries theo operator class tương ứng. Nó có mục tiêu khác B-tree index của `payload #>> '{customer,address,city}'`.

### 27.2. Containment trên object lồng sâu

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @> $json$
{
  "customer": {
    "address": {"city": "Hà Nội"}
  }
}
$json$::jsonb;
~~~

Kết quả: order **1**.

### 27.3. jsonb_ops và jsonb_path_ops

GIN có các operator classes thường gặp:

| Operator class | Đặc tính khái quát |
| --- | --- |
| `jsonb_ops` | Mặc định, hỗ trợ nhiều toán tử JSONB, gồm top-level key existence `?` và containment |
| `jsonb_path_ops` | Tối ưu hơn cho một số workload containment/JSONPath; không hỗ trợ mọi key-existence operator như `jsonb_ops` |

Ví dụ tùy nhu cầu:

~~~sql
CREATE INDEX idx_orders_payload_pathops_307
ON json_lab_307.orders
USING gin (payload jsonb_path_ops);
~~~

Không nên giữ cả hai GIN indexes trong production mà không có bằng chứng nhu cầu. Chúng chiếm đĩa và tăng chi phí ghi; chọn operator class từ **các toán tử WHERE thực sự dùng**.

### 27.4. Đừng nhầm @> với -> và #>>

- `payload #>> '{customer,address,city}'`: **trích giá trị text**.
- `payload @> '{"customer":{"address":{"city":"Hà Nội"}}}'`: **kiểm tra containment**, trả boolean.

Một GIN index trên toàn cột có thể hữu ích cho `@>` nhưng không tự cho phép PostgreSQL tra cứu biểu thức text `#>>` như B-tree index chuyên biệt. Ngược lại, B-tree trên city text không tự hỗ trợ mọi JSONB containment/path predicate.

### 27.5. JSONPath và GIN không phải tự động tăng tốc mọi truy vấn

Một số JSONPath predicates có thể trích được điều kiện tìm kiếm phù hợp với GIN; những path expressions phức tạp, wildcard hoặc điều kiện không hỗ trợ có thể không khai thác index hiệu quả. **`EXPLAIN` và dữ liệu thực** vẫn cần thiết.

## 28. Chọn kiểu index theo dạng SQL thực tế

| SQL phổ biến | Index ứng viên |
| --- | --- |
| `WHERE payload #>> '{customer,address,city}' = 'Hà Nội'` | B-tree expression index trên đúng `#>>` path |
| `WHERE payload ->> 'status' = 'paid'` | B-tree expression index trên `payload ->> 'status'` |
| `WHERE payload @> '{"paid":true}'::jsonb` | GIN trên `payload` |
| `WHERE payload ? 'coupon'` | GIN `jsonb_ops` trên `payload` khi có lợi |
| `WHERE payload @? '$.items[*] ? (...)'` | GIN có thể hỗ trợ một số path predicate có điều kiện khai thác được |
| `WHERE (payload ->> 'total')::numeric > 100000` | B-tree numeric expression index nếu dữ liệu được validate và query phổ biến |
| `ORDER BY created_at DESC LIMIT 20` | B-tree trên **cột `created_at`** thường phù hợp hơn JSON index |

### 28.1. Query plan và thống kê

~~~sql
ANALYZE json_lab_307.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM json_lab_307.orders
WHERE payload #>> '{customer,address,city}' = 'Hà Nội';
~~~

`EXPLAIN ANALYZE` thực thi câu SQL. Trên SELECT lab nhỏ, phù hợp để minh họa; với DML hoặc SELECT chứa hàm side effect, phải đánh giá tác động trước khi bật `ANALYZE`.

### 28.2. Đọc định nghĩa index

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'json_lab_307'
ORDER BY tablename, indexname;
~~~

Đối chiếu **đúng biểu thức**, operator class, predicate partial và kiểu kết quả. Không chỉ nhìn tên `idx_city` rồi đoán nó được tạo trên key nào.

### 28.3. Một đường dẫn động có thể không dùng expression index cố định

Nếu ứng dụng gửi path bất kỳ như `'{customer,address,city}'` hôm nay và `'{customer,contact,email}'` ngày mai, B-tree trên city path không trở thành index cho email path. Định nghĩa những field quan trọng như các đường truy cập cố định, hoặc cân nhắc thiết kế cột quan hệ/GIN khi workload phù hợp.

## 29. JSONB subscripting: cú pháp khác để đọc lồng nhau

Các phiên bản PostgreSQL hiện đại (PostgreSQL 14 trở lên) hỗ trợ cú pháp **subscripting JSONB**:

~~~sql
SELECT
    payload['customer']['address']['city']
        AS city_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Ví dụ trả về giá trị **jsonb** tương ứng JSON string `"Hà Nội"`. Cú pháp này gần với truy cập object/array trong một số ngôn ngữ lập trình, nhưng cần nhớ:

- Các key dùng **chuỗi SQL** như `'customer'`, không phải identifier không quote.
- JSON array index vẫn bắt đầu từ **0**.
- Kết quả subscripting cơ bản **giữ dạng JSONB**, không tương đương trực tiếp kiểu text của `->>`/`#>>`.
- Cú pháp có giới hạn theo **major version** và ngữ nghĩa thao tác khác SQL native arrays.

### 29.1. Lấy phần tử mảng với subscripting

~~~sql
SELECT
    payload['items'][0]['sku'] AS sku_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Đây là giá trị JSONB string. Nếu API cần chuỗi SQL, `payload #>> '{items,0,sku}'` hoặc `payload -> 'items' -> 0 ->> 'sku'` thường rõ ràng hơn.

### 29.2. Không trộn nhầm kiểu kết quả

~~~sql
SELECT
    pg_typeof(payload['customer']['name']) AS subscript_type,
    pg_typeof(payload -> 'customer' ->> 'name') AS arrow_text_type
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`subscript_type` là `jsonb` còn `arrow_text_type` là `text`.

### 29.3. Index expression phải phù hợp query

Một index trên `payload #>> '{customer,address,city}'` không tự có nghĩa PostgreSQL sẽ xem mọi cú pháp subscripting tương đương và dùng cùng index trong mọi query. Để tối ưu, thống nhất biểu thức SQL quan trọng và đo `EXPLAIN`.

## 30. Đường dẫn khi cập nhật JSON: liên quan nhưng khác việc đọc

Trong các bài toán update một giá trị lồng nhau, PostgreSQL có hàm `jsonb_set`:

~~~sql
jsonb_set(target jsonb, path text[], new_value jsonb, create_if_missing boolean)
~~~

Đường dẫn `text[]` ở đây có hình thức giống toán tử `#>`/`#>>`, nhưng hành động khác: thay một phần của JSONB và trả **tài liệu JSONB mới**.

### 30.1. Lab UPDATE có rollback

~~~sql
BEGIN;

UPDATE json_lab_307.orders
SET payload = jsonb_set(
    payload,
    '{customer,address,city}',
    to_jsonb('Huế'::text),
    false
)
WHERE order_id = 1;

SELECT
    order_id,
    payload #>> '{customer,address,city}' AS new_city
FROM json_lab_307.orders
WHERE order_id = 1;

ROLLBACK;
~~~

Trong transaction, `new_city=Huế`; sau `ROLLBACK`, dữ liệu quay lại giá trị `Hà Nội`.

### 30.2. Path không tồn tại

`create_if_missing` không có nghĩa PostgreSQL tự tạo đầy đủ **mọi object trung gian** trong một đường dẫn sâu khi chúng không tồn tại. Nếu `customer` hoặc `address` thiếu/sai kiểu, cần định nghĩa logic cập nhật thích hợp và kiểm tra cấu trúc.

### 30.3. Đừng biến một bài đọc thành thay đổi dữ liệu

Các toán tử `->`, `->>`, `#>`, `#>>` ở `SELECT` **không sửa JSON**. `jsonb_set`, assignment với JSONB subscripting hoặc `UPDATE` là hoạt động ghi, chịu MVCC, WAL, locks và index maintenance.

Tránh viết luồng “đọc bằng cách cập nhật một giá trị phụ” chỉ để truy xuất nested field.

## 31. Kiểm soát schema và chất lượng dữ liệu JSON

JSONB linh hoạt nhưng không có nghĩa dữ liệu không cần schema. Hãy xác định:

- Root bắt buộc là object hay có thể là array/scalar?
- `customer.id` bắt buộc là number/integer, có phải khóa ngoại không?
- `customer.address.city` có thể thiếu hoặc null không?
- `items` bắt buộc array, có thể rỗng không?
- Trong `items`, `qty`/`price` là số dương hay có thể là string?
- `total` là số hay string số? Ai chịu trách nhiệm đồng bộ với tổng item?
- `coupon` thiếu khác JSON null thế nào?
- Có những field mang PII cần che khỏi các đường dẫn tùy chọn không?

### 31.1. Một CHECK constraint cho root

Nếu nghiệp vụ cho phép SQL NULL nhưng khi có JSON thì root phải là object:

~~~sql
ALTER TABLE json_lab_307.orders
ADD CONSTRAINT ck_orders_payload_root_object_307
CHECK (
    payload IS NULL
    OR jsonb_typeof(payload) = 'object'
);
~~~

Constraint này tương thích với sáu hàng lab: 1–5 là object, 6 là SQL NULL. Nó **chỉ kiểm tra root**, chưa đảm bảo các field bên trong hợp lệ.

### 31.2. Constraint cho items nếu dữ liệu đã sạch

Ý tưởng:

~~~sql
-- Chỉ áp dụng SAU KHI xử lý các hàng items sai kiểu.
-- Trong lab hiện tại order 4 và 5 làm CHECK này thất bại.
--
-- ALTER TABLE json_lab_307.orders
-- ADD CONSTRAINT ck_items_are_arrays
-- CHECK (
--     payload IS NULL
--     OR NOT (payload ? 'items')
--     OR jsonb_typeof(payload -> 'items') = 'array'
-- );
~~~

Không nên thêm constraint rồi tự động xóa những hàng “lỗi” nếu chưa có quyết định nghiệp vụ. Có thể cần làm sạch dữ liệu hoặc chuyển những record sai sang vùng quarantine để đối soát.

### 31.3. Constraint kiểu số đơn giản

Để giữ `total` nếu tồn tại là JSON number:

~~~sql
-- Ví dụ nguyên tắc, sẽ bị chặn bởi order 5 trong lab:
--
-- ALTER TABLE json_lab_307.orders
-- ADD CONSTRAINT ck_total_is_number
-- CHECK (
--     payload IS NULL
--     OR NOT (payload ? 'total')
--     OR jsonb_typeof(payload -> 'total') = 'number'
-- );
~~~

CHECK ở đây không bắt buộc số không âm hoặc trong giới hạn tiền; các điều kiện nghiệp vụ tiếp theo vẫn cần được định nghĩa.

### 31.4. Nếu customer_id là dữ liệu quan hệ trọng yếu

Nếu `customer.id` cần liên kết tới bảng `customers(customer_id)`, bạn không thể mặc định một phép `payload #>> '{customer,id}'` sẽ có đầy đủ các đặc tính foreign key của cột SQL thông thường.

Khi quan hệ tham chiếu, join và unique constraints là trọng tâm, cân nhắc **đưa customer_id ra cột typed** hoặc thiết kế generated/stored field phù hợp (với các giới hạn immutability), rồi áp constraint rõ ràng.

### 31.5. Không để dữ liệu JSON quyết định toàn bộ kiểu trả về API

Nếu client chờ `total` là number mà một số record trả string, API cần:

1. Enforce schema ngay lúc ingest;
2. Hoặc validate/normalize trước khi trả;
3. Hoặc trả lỗi dữ liệu có kiểm soát;
4. Không lặng lẽ biến string không hợp lệ thành zero.

Sự khác biệt JSON null, missing và SQL NULL phải được mô tả trong hợp đồng dữ liệu.

## 32. Mẫu phân loại dữ liệu bất thường

### 32.1. Phân loại items

~~~sql
SELECT
    order_id,
    CASE
        WHEN payload IS NULL THEN 'sql_null_document'
        WHEN jsonb_typeof(payload) <> 'object'
             THEN 'unexpected_root_type'
        WHEN NOT (payload ? 'items')
             THEN 'missing_items_key'
        WHEN jsonb_typeof(payload -> 'items') = 'null'
             THEN 'json_null_items'
        WHEN jsonb_typeof(payload -> 'items') = 'array'
             THEN 'valid_array'
        ELSE 'wrong_items_type'
    END AS items_status
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Kết quả dự kiến:

| order_id | items_status |
| ---: | --- |
| 1 | valid_array |
| 2 | valid_array |
| 3 | valid_array |
| 4 | json_null_items |
| 5 | wrong_items_type |
| 6 | sql_null_document |

Đây là kiểu truy vấn hữu ích để **điều tra dữ liệu nhập** mà không làm biến mất những tình huống khác nhau dưới một `COALESCE(..., '[]')`.

### 32.2. Phân loại coupon

~~~sql
SELECT
    order_id,
    CASE
        WHEN payload IS NULL
             THEN 'sql_null_document'
        WHEN NOT (payload ? 'coupon')
             THEN 'missing_coupon'
        WHEN jsonb_typeof(payload -> 'coupon') = 'null'
             THEN 'json_null_coupon'
        WHEN jsonb_typeof(payload -> 'coupon') = 'string'
             THEN 'coupon_code'
        ELSE 'wrong_coupon_type'
    END AS coupon_status
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Kết quả:

| order_id | coupon_status |
| ---: | --- |
| 1 | json_null_coupon |
| 2 | coupon_code |
| 3 | missing_coupon |
| 4 | missing_coupon |
| 5 | json_null_coupon |
| 6 | sql_null_document |

### 32.3. Truy vấn tổng hợp số record theo loại lỗi

~~~sql
WITH classification AS (
    SELECT
        CASE
            WHEN payload IS NULL THEN 'sql_null_document'
            WHEN NOT (payload ? 'items') THEN 'missing_items'
            WHEN jsonb_typeof(payload -> 'items') = 'array'
                 THEN 'array'
            WHEN jsonb_typeof(payload -> 'items') = 'null'
                 THEN 'json_null'
            ELSE 'wrong_type'
        END AS kind
    FROM json_lab_307.orders
)
SELECT kind, COUNT(*) AS row_count
FROM classification
GROUP BY kind
ORDER BY kind;
~~~

Lệnh này nhóm dữ liệu mà không gọi `jsonb_array_length` trên các values không phải array, tránh lỗi giữa chừng.

## 33. Tích hợp Java/JDBC: trả text hoặc JSON đúng kiểu

Trong ứng dụng Java, nếu chỉ cần một field dạng text, hãy để PostgreSQL trích xuất `text` bằng `#>>` rồi đọc bằng `ResultSet.getString`.

### 33.1. PreparedStatement với path cố định

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JsonOrderQueries {
    public static String findCity(Connection connection, long orderId)
            throws SQLException {
        String sql = """
            SELECT payload #>> '{customer,address,city}' AS city
            FROM json_lab_307.orders
            WHERE order_id = ?
            """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, orderId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null; // Không có order_id.
                }
                return rs.getString("city");
                // NULL ở đây có thể do thiếu path / JSON null /
                // SQL NULL document, không thể tự phân biệt.
            }
        }
    }
}
~~~

Ví dụ dùng cú pháp Java text blocks (Java 15+). Nếu dự án dùng Java cũ hơn, thay bằng chuỗi nối hợp lệ trong Java.

### 33.2. Truyền path dạng text[] từ Java

~~~java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JsonPathLookup {
    public static void findOrdersByCity(Connection conn)
            throws SQLException {
        String sql = """
            SELECT order_id, payload #>> ?::text[] AS city
            FROM json_lab_307.orders
            WHERE payload #>> ?::text[] = ?
            ORDER BY order_id
            """;

        String[] components = {"customer", "address", "city"};
        Array sqlPath = conn.createArrayOf("text", components);

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setArray(1, sqlPath);
            ps.setArray(2, sqlPath);
            ps.setString(3, "Hà Nội");

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long orderId = rs.getLong("order_id");
                    String city = rs.getString("city");
                    System.out.println(orderId + ": " + city);
                }
            }
        } finally {
            sqlPath.free();
        }
    }
}
~~~

**Lưu ý:** syntax `?::text[]` là placeholder JDBC `?` đi kèm cast PostgreSQL. Tất cả đường dẫn và so sánh đều được truyền qua bound parameters; không ghép chuỗi SQL trực tiếp từ request.

### 33.3. Hạn chế dynamic path theo allowlist

~~~java
import java.util.Map;

Map<String, String[]> allowedPaths = Map.of(
    "customerName", new String[]{"customer", "name"},
    "customerCity", new String[]{"customer", "address", "city"},
    "contactEmail", new String[]{"customer", "contact", "email"}
);
~~~

API có thể nhận tên field logic như `customerCity`, tra trong map được kiểm soát rồi truyền `String[]` tương ứng sang `createArrayOf("text", ...)`. Tránh cho client gửi một path arbitrary có thể đọc dữ liệu ngoài quyền hạn.

### 33.4. Chọn -> hay ->> trong API

~~~sql
SELECT
    payload -> 'customer' AS customer_json,
    payload ->> 'paid' AS paid_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`customer_json` là PostgreSQL `jsonb`; driver có thể trả đối tượng đặc thù như `PGobject` khi dùng `getObject`, tùy driver/cấu hình. `paid_text` là `text`, nên `getString` trả chuỗi `"true"` theo cách biểu diễn Java string (không phải Java `boolean`).

Không lấy `String paid = rs.getString("paid_text")` rồi mặc định nó là một boolean typed; nếu API cần boolean, hãy cast/validate trong SQL hoặc Java theo hợp đồng dữ liệu.

### 33.5. Đọc SQL NULL từ ResultSet

~~~java
String city = rs.getString("city");
if (city == null) {
    // Có thể key thiếu, JSON null, hoặc document SQL NULL.
}
~~~

Với `getString`, SQL NULL được đọc thành Java `null`. Nếu dùng các getter primitive `getInt`/`getBoolean`, cần dùng `rs.wasNull()` sau getter khi giá trị SQL NULL có ý nghĩa.

### 33.6. JSON parsing ở application vẫn có chỗ đứng

Nếu API cần toàn bộ object hoặc thực hiện validation phức tạp trên mảng lớn, thư viện Java như Jackson có thể thích hợp để parse JSON trả về từ database. Nhưng đừng mặc định gửi về **toàn bộ payload JSONB** khi chỉ cần một city hoặc SKU: trích field trong SQL có thể giảm dữ liệu network và application parsing.

## 34. Truy vấn theo JSON: hiệu năng, consistency và chi phí lưu trữ

### 34.1. Chỉ lấy field cần dùng

~~~sql
SELECT
    order_id,
    payload #>> '{customer,name}' AS customer_name,
    payload #>> '{customer,address,city}' AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Không cần `SELECT payload` nếu client chỉ hiển thị hai field. Với JSON document rất lớn, giảm output có thể giảm network/serialization.

### 34.2. JSONB không biến thành cấu trúc được index tự động

Một cột `jsonb` có thể truy cập nhiều field, nhưng PostgreSQL không tự tạo B-tree trên từng path. Nếu query theo city chậm, cần xem:

- Có bao nhiêu rows? Selectivity của city?
- Query có phù hợp với một expression index không?
- Có thể rewrite thành containment và GIN hay không?
- Dữ liệu có đồng nhất/đủ điều kiện cast không?
- Chi phí duy trì thêm index so với lợi ích đọc?

### 34.3. Tránh làm mất index bằng biến đổi biểu thức

Nếu index lưu `payload #>> '{customer,address,city}'`, câu query dùng `lower(payload #>> '{customer,address,city}')` là **biểu thức khác**. Có thể cần index trên `lower(...)` nếu tìm case-insensitive thực sự phổ biến, với lưu ý collation và tính bất biến.

### 34.4. JSONB update có thể ghi lại tuple

Thay một trường lồng sâu bằng `jsonb_set` trong `UPDATE` vẫn là một thao tác thay đổi dữ liệu theo MVCC. Nó không phải “thay đúng vài byte tại chỗ mà không có index/WAL” trong mọi trường hợp. Khi JSONB lớn và UPDATE thường xuyên, cân nhắc đưa field biến động mạnh thành cột quan hệ hoặc bảng con.

### 34.5. Schema linh hoạt không miễn trách nhiệm versioning

Nếu khách hàng nhập `address.city` theo schema v1 nhưng schema v2 chuyển thành `shipping.address.city`, query `#>> '{customer,address,city}'` chỉ đọc được v1. Cần:

- Schema version/contract rõ ràng;
- Migration hoặc query hỗ trợ tương thích có chủ đích;
- Metric tỷ lệ missing/wrong-type;
- Không ngầm gộp dữ liệu lỗi vào NULL mà bỏ qua.

### 34.6. Không dựa vào thứ tự key JSONB

`jsonb` không bảo đảm giữ nguyên thứ tự key của văn bản input. Nếu cần thứ tự dòng sản phẩm, hãy lưu trong **JSON array** và dùng chỉ số/`WITH ORDINALITY`. Không cố dùng thứ tự object keys để thể hiện thứ tự nghiệp vụ.

### 34.7. Không mặc định PostgreSQL là JSON document search engine cho mọi nhu cầu

JSONB rất mạnh để lưu/truy vấn cấu trúc bán linh hoạt, nhưng các phép tìm kiếm full-text, thống kê phân tích cực lớn, hoặc những truy vấn cần nhiều joins/constraints có thể phù hợp hơn với cột quan hệ, full-text index, materialized views hoặc hệ phân tích khác. Lựa chọn dựa trên workload và mô hình dữ liệu.

## 35. Quy trình kiểm tra một phép trích xuất JSON

Trước khi đưa query dùng `->`/`#>>` vào code sản phẩm, hãy tự hỏi:

1. **Root là `json` hay `jsonb`?** Kiểu SQL trả về của toán tử là gì?
2. **Field là object hay array?** Path component là text key hay integer index?
3. **Muốn JSON hay SQL text?** Chọn `->`/`#>` hoặc `->>`/`#>>`.
4. **Key thiếu khác JSON null không?** Có cần toán tử `?` hoặc `jsonb_typeof`?
5. **Field có thể bị sai kiểu không?** Cast cần `CASE`/schema validation không?
6. **JSON array có thể rỗng không?** Dùng index 0 hay explode bằng LATERAL?
7. **Có cần giữ order của array không?** Dùng `WITH ORDINALITY`.
8. **Path có ký tự đặc biệt không?** Dùng `ARRAY[...]::text[]` hoặc quote JSONPath đúng.
9. **Cần index không?** Predicate nào thực sự chạy nhiều lần? B-tree expression hay GIN?
10. **Cần quyền truy cập nào?** Có field PII hoặc path do người dùng điều khiển không?
11. **SQL được bind parameter hóa chưa?** Tránh nối chuỗi dynamic SQL.
12. **Schema có version không?** Query phải xử lý dữ liệu cũ thế nào?
13. **Đã đo bằng EXPLAIN khi bảng lớn chưa?** Không đánh giá plan từ vài dòng lab.
14. **Dữ liệu trả về có đúng hợp đồng API không?** Ví dụ numeric/boolean thay vì text?
15. **Có nên đưa field ra cột quan hệ không?** Nếu cần foreign key, constraints hoặc cập nhật thường xuyên.

## 36. Những lỗi thường gặp

| Nhầm lẫn / lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `->` và `->>` giống nhau | Sai kiểu SQL, so sánh/cast sai | `->` giữ JSON; `->>` trả text |
| Dùng `->>` ở cấp giữa rồi truy cập `->` tiếp | Lỗi operator trên text | Các cấp giữa dùng `->` |
| Viết `payload #>> 'a.b.c'` | Không phải `text[]` path | `#>> '{a,b,c}'` hoặc `ARRAY[...]` |
| Viết `payload -> "name"` | Dấu ngoặc kép là identifier SQL | Dùng `'name'` |
| Coi `'a.b'` là hai cấp path | Lấy sai field | `-> 'a.b'` là một key |
| JSON array index bắt đầu từ 1 | Lấy nhầm phần tử | JSON index bắt đầu từ 0 |
| `WITH ORDINALITY` bắt đầu 0 | Sai thứ tự/position | Ordinality bắt đầu từ 1 |
| `-1` là phần tử đầu | Lấy sai hàng | Negative index lấy từ cuối array |
| Khóa thiếu chắc chắn lỗi | Nhầm kết quả SQL NULL | Toán tử trích xuất thường trả NULL khi path không phù hợp |
| JSON null và SQL NULL giống nhau | Không phân biệt input thiếu/null | Kiểm tra `IS NULL`, `?`, `jsonb_typeof` |
| `->>` giữ được khác biệt missing vs JSON null | Mất thông tin | Dùng `?`/`->` trước khi ra text |
| `= NULL` để tìm NULL | SQL UNKNOWN | Dùng `IS NULL` |
| `'null'` là JSON null | Sai loại giá trị | Phân biệt JSON string và JSON null |
| Chuỗi rỗng `''` giống NULL | Làm sai nghiệp vụ | Kiểm tra riêng empty text |
| `jsonb_array_length` với object/null | Có thể phát sinh lỗi | Guard bằng `jsonb_typeof` |
| `COALESCE(jsonb_null, '[]')` trả array rỗng | JSON null không phải SQL NULL | `CASE` theo JSON type |
| `payload -> 'items' -> 0` trả NULL nghĩa không có items | Sai khi items là object/null | Phân loại type trước |
| `jsonb_array_elements` trên mọi row | Lỗi khi field không phải array | Normalize/validate đầu vào |
| `CROSS JOIN LATERAL` giữ order có mảng rỗng | Hàng bị loại khi không có item | Dùng `LEFT JOIN LATERAL` nếu cần |
| Lấy `jsonb_to_recordset` như validator | Cast có thể lỗi/nhận dữ liệu sai | Schema validation riêng |
| `payload ->> 'total' > '90000'` | So sánh text | Cast có guard thành numeric |
| WHERE guard được đánh giá trái sang phải | Cast vẫn có thể lỗi do optimizer reorder | Dùng `CASE`/constraint |
| `jsonb_typeof(...)=number` không cần xử lý null | SQL NULL vẫn tồn tại | Định nghĩa rõ missing/null behavior |
| `#>>` và JSONPath `$.x.y` cùng một cú pháp | Lỗi kiểu/semantics | text[] path khác jsonpath |
| `'{items,*,sku}'` duyệt toàn array | `*` không là wildcard của text[] | JSONPath `$.items[*].sku` hoặc LATERAL |
| JSONPath lax/strict giống `#>` | Có thể khác hành vi khi sai cấu trúc | Chọn ngữ nghĩa cần, thử các cases |
| `?` kiểm tra mọi key lồng nhau | Chỉ kiểm tra cấp hiện tại | Đi vào object con hoặc dùng JSONPath |
| JSONB có index tự động cho mọi key | Seq Scan có thể xảy ra | B-tree expression/GIN theo workload |
| GIN trên payload tối ưu mọi `#>>` | Dạng operator/access khác | Tạo expression index khi phù hợp |
| B-tree trên city giúp mọi path động | Khóa index cố định | Chọn field chủ đạo hoặc kiểu index khác |
| `EXPLAIN ANALYZE` luôn chỉ đọc | Thực thi SQL, kể cả DML | Thử trên SELECT lab an toàn |
| Gắn JSONPath do người dùng nhập trực tiếp vào SQL | SQL injection/quyền dữ liệu | Bind + allowlist + authorization |
| JSONB giữ thứ tự object keys | Thứ tự không được bảo đảm | Dùng JSON array cho ordered data |
| JSONB thay được mọi FK/constraint | Thiếu ràng buộc quan hệ | Lưu field quan trọng vào cột typed |
| Chỉ cần `COALESCE(...,'')` để hết dữ liệu lỗi | Che giấu khác biệt missing/null/wrong type | Phân loại và báo chất lượng dữ liệu |

## 37. Bài tập thực hành

Các bài dưới đây dùng bảng `json_lab_307.orders`, trừ khi đề bài nói sử dụng JSON literal độc lập. Một số bài yêu cầu **dự đoán lỗi**; không phải mọi câu cố ý sai đều cần chạy trong database. Khi làm bài, luôn ghi rõ **kiểu SQL** của kết quả nếu đề bài yêu cầu.

### Bài 1 — Trích khóa cấp root bằng ->

Viết query lấy `payload -> 'customer'` của order 1.

**Câu hỏi:** kết quả là SQL text hay JSONB? Nó chứa những key nào?

**Gợi ý:** `->` giữ `jsonb`; customer là object có `id`, `name`, `contact`, `address`.

### Bài 2 — Lấy tên khách hàng dưới dạng text

Truy xuất tên khách hàng của order 1 bằng:

~~~sql
SELECT payload -> 'customer' ->> 'name' AS customer_name
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

**Kết quả:** An; kiểu SQL là `text`.

### Bài 3 — Hai đường tới city

Viết hai biểu thức cho city:

~~~sql
payload -> 'customer' -> 'address' ->> 'city'
payload #>> '{customer,address,city}'
~~~

**Câu hỏi:** với order 1, cả hai trả gì? Kiểu là JSONB hay text?

**Đáp án:** cùng trả SQL text `Hà Nội`.

### Bài 4 — #> khác #>>

~~~sql
SELECT
    payload #> '{customer,address,city}' AS a,
    payload #>> '{customer,address,city}' AS b
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Giải thích vì sao `a` là JSONB string còn `b` là SQL text. Nếu dùng `pg_typeof(a)` và `pg_typeof(b)`, bạn kỳ vọng gì?

### Bài 5 — Không dùng ->> quá sớm

Vì sao truy vấn sau không hợp lệ theo kiểu toán tử?

~~~sql
-- Sai:
-- SELECT payload ->> 'customer' ->> 'name'
-- FROM json_lab_307.orders;
~~~

**Đáp án:** sau `->> 'customer'`, giá trị là `text`, không thể dùng tiếp `->>` như trên JSONB. Sửa thành `payload -> 'customer' ->> 'name'`.

### Bài 6 — Chỉ số đầu tiên của items

Viết query lấy SKU của item đầu trong order 1 bằng `-> 0`.

**Đáp án:** `BOOK-01`. Vì sao dùng `-> 1` cho phần tử đầu là sai?

### Bài 7 — Lấy item thứ hai bằng đường dẫn

Dùng `#>> '{items,1,sku}'` trên order 1.

**Đáp án:** `PEN-01`.

### Bài 8 — Lấy item cuối

Dùng negative index của toán tử `->` hoặc `#>>` để lấy SKU cuối trong order 1 và 2.

**Kết quả:** order 1 `PEN-01`; order 2 `MOUSE-01`.

### Bài 9 — Chỉ số vượt giới hạn

Dự đoán:

~~~sql
SELECT payload -> 'items' ->> 50
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

**Đáp án:** SQL NULL. Trình bày lý do vì sao toán tử không tự ném lỗi.

### Bài 10 — SQL array vs JSON array

So sánh:

~~~sql
SELECT
    (ARRAY[10,20,30])[1] AS sql_first,
    '[10,20,30]'::jsonb -> 0 AS json_first;
~~~

**Câu hỏi:** hai giá trị logic có giống nhau không? Kiểu SQL của từng giá trị?

**Đáp án:** cùng số 10, nhưng `integer` so với `jsonb`.

### Bài 11 — Khóa chứa dấu chấm và dấu cách

Truy xuất `special-value` từ order 1 bằng hai cách:

~~~sql
payload -> 'a.b' ->> 'x y'
payload #>> ARRAY['a.b','x y']::text[]
~~~

Giải thích vì sao `a.b` là **một key**, không phải hai cấp.

### Bài 12 — Khóa chứa dấu phẩy

Với:

~~~json
{"a,b":{"c d":77}}
~~~

viết `#>>` dùng `ARRAY['a,b','c d']::text[]`, rồi giải thích vì sao cách này ít rủi ro sai escaping hơn một text-array literal tự viết.

### Bài 13 — Key thiếu khác JSON null

Trên order 1:

~~~sql
payload -> 'coupon'
payload -> 'not_found'
~~~

**Câu hỏi:** biểu thức nào là JSONB null, biểu thức nào là SQL NULL? Khi kiểm tra `IS NULL`, kết quả khác nhau ra sao?

### Bài 14 — Khi ->> làm mất khác biệt

Trên order 1:

~~~sql
payload ->> 'coupon'
payload ->> 'not_found'
~~~

**Đáp án:** cả hai là SQL NULL. Dùng thao tác nào để biết khóa `coupon` thực sự tồn tại?

**Gợi ý:** `payload ? 'coupon'`.

### Bài 15 — Tìm order chứa coupon JSON null

Viết query chỉ trả orders có key `coupon` và giá trị đúng JSON null.

**Đáp án gợi ý:**

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload ? 'coupon'
  AND payload -> 'coupon' = 'null'::jsonb
ORDER BY order_id;
~~~

**Kết quả:** 1 và 5.

### Bài 16 — Phân biệt coupon thiếu

Viết query tìm những orders có root là object nhưng không có key `coupon`.

**Kết quả:** 3 và 4. Tại sao order 6 cần xử lý riêng nếu business muốn tính cả SQL NULL document?

### Bài 17 — Chuỗi rỗng khác null

Với order 1, `payload ->> 'note'` có bằng `''` không? `IS NULL` không?

**Đáp án:** bằng chuỗi rỗng, nhưng không phải SQL NULL.

### Bài 18 — JSON string "null"

So sánh:

~~~sql
SELECT
    jsonb_typeof('"null"'::jsonb),
    jsonb_typeof('null'::jsonb);
~~~

**Đáp án:** `string` và `null`.

### Bài 19 — Kiểm tra loại của items

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload -> 'items') AS items_type
FROM json_lab_307.orders
ORDER BY order_id;
~~~

**Câu hỏi:** orders 3, 4, 5 và 6 khác nhau ra sao?

**Gợi ý:** array rỗng, JSON null, object sai kiểu và SQL NULL document.

### Bài 20 — jsonb_array_length có guard

Viết `CASE` trả độ dài items khi `jsonb_typeof(...)= 'array'`, còn lại trả SQL NULL.

**Kết quả:** order 1 = 2, order 2 = 1, order 3 = 0, các hàng 4–6 = NULL.

### Bài 21 — Vì sao COALESCE chưa đủ?

Giải thích:

~~~sql
jsonb_array_length(
    COALESCE(payload -> 'items', '[]'::jsonb)
)
~~~

Tại sao vẫn có thể lỗi trên order 4?

**Đáp án:** JSONB null là một giá trị không phải SQL NULL; `COALESCE` giữ JSON null và hàm yêu cầu array.

### Bài 22 — Trích total thành số

Viết query `(payload ->> 'total')::numeric` cho order 1 và 2.

**Câu hỏi:** một chuỗi `"total":"abc"` sẽ gây lỗi gì về nguyên tắc? Vì sao cần validation?

### Bài 23 — Kiểm soát total JSON number

Viết `CASE WHEN jsonb_typeof(payload -> 'total')='number' THEN (payload ->> 'total')::numeric ELSE NULL END`.

**Câu hỏi:** order 5 trả SQL NULL hay 50000? Tại sao?

**Đáp án:** SQL NULL vì loại JSON của total là `string`, dù văn bản `"50000"` parse được.

### Bài 24 — So sánh số với text

Giải thích vì sao:

~~~sql
WHERE payload ->> 'total' > '90000'
~~~

không tương đương việc tìm những đơn có tổng tiền lớn hơn 90.000. Viết lại phép so sánh numeric có guard.

### Bài 25 — Boolean thật và string boolean

So:

~~~sql
payload -> 'paid' = 'true'::jsonb
payload ->> 'paid' = 'true'
~~~

**Câu hỏi:** nếu tài liệu có `"paid":"true"` (JSON string), câu nào có thể khớp? Câu nào kiểm tra đúng JSON boolean?

### Bài 26 — Tách items thành nhiều hàng

Viết query `CROSS JOIN LATERAL jsonb_array_elements` lấy `sku`/`qty` từ order 1.

**Kết quả:** BOOK-01 / 2 và PEN-01 / 1.

### Bài 27 — LATERAL trên dữ liệu sai kiểu

Cho order 4/5 có `items` không phải array.

**Bài tập:** dùng `CASE` thay bằng `'[]'::jsonb` trước khi truyền vào `jsonb_array_elements`. Vì sao cần bước này?

### Bài 28 — Giữ order không có items

Thay `CROSS JOIN LATERAL` bằng `LEFT JOIN LATERAL ... ON TRUE` với đầu vào đã bảo vệ.

**Câu hỏi:** order 3–6 có xuất hiện không? Giá trị `sku` của chúng?

**Đáp án:** mỗi order xuất hiện một dòng với SQL NULL `sku`.

### Bài 29 — WITH ORDINALITY

Trên order 1, dùng `WITH ORDINALITY` trả `position` và `position-1 AS json_index`.

**Kết quả:** BOOK-01 có SQL position 1/JSON index 0, PEN-01 có SQL position 2/JSON index 1.

### Bài 30 — jsonb_to_recordset

Viết query ánh xạ từng item trong order 1/2 thành `(sku text,qty integer,price numeric)` bằng `jsonb_to_recordset`.

**Câu hỏi:** nếu `items` không phải array hoặc `qty` có string không thể parse thành integer, chuyện gì có thể xảy ra?

### Bài 31 — jsonb_each

Liệt kê key của `payload -> 'customer'` ở order 1 bằng `jsonb_each`.

**Câu hỏi:** `value` có kiểu `jsonb` hay `text`? Nếu dùng `jsonb_each_text` thì khác gì?

### Bài 32 — text[] path khác JSONPath

Cho:

~~~text
{items,0,sku}
$.items[0].sku
~~~

**Bài tập:** biểu diễn thứ nhất dùng với `#>>` ra sao; biểu diễn thứ hai dùng với `jsonb_path_query_first` thế nào? Kết quả kiểu SQL có giống nhau không?

### Bài 33 — Wildcard

Vì sao `#> '{items,*,sku}'` không có ý nghĩa “lấy tất cả SKU” như `jsonb_path_query(payload,'$.items[*].sku')`?

**Đáp án:** `text[]` path không có wildcard `*`; mỗi thành phần là một key/index cụ thể.

### Bài 34 — JSONPath key có dấu chấm

Truy xuất `a.b -> x y` bằng JSONPath:

~~~sql
SELECT jsonb_path_query_first(
    payload,
    '$."a.b"."x y"'
)
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Giải thích tác dụng của dấu ngoặc kép trong JSONPath.

### Bài 35 — @? và ?

So hai yêu cầu:

1. Payload có key `coupon` ở root?
2. Có bất kỳ item nào có SKU `BOOK-01`?

**Gợi ý:** yêu cầu 1 dùng `?`; yêu cầu 2 dùng `@?` với JSONPath hoặc `LATERAL` + `EXISTS`.

### Bài 36 — B-tree expression index

Tạo index:

~~~sql
CREATE INDEX idx_city_practice_307
ON json_lab_307.orders (
    (payload #>> '{customer,address,city}')
);
~~~

Sau đó `EXPLAIN` query lọc city. Vì sao planner vẫn có thể chọn Seq Scan trên bảng chỉ sáu hàng?

### Bài 37 — GIN containment

Viết query `payload @> '{"paid":true}'::jsonb` và giải thích nó khác việc đọc `payload ->> 'paid'`.

**Kết quả:** orders 1, 3, 4 theo dữ liệu lab.

### Bài 38 — Operator class

Giải thích vì sao `jsonb_ops` có thể phù hợp với key existence `?` trong khi `jsonb_path_ops` hướng tới containment/JSONPath và có phạm vi toán tử khác.

**Không kết luận mọi truy vấn JSONB đều nên có hai GIN indexes.**

### Bài 39 — Prepared text[] path

Viết `PREPARE find_orders(text[],text)` tìm `payload #>> $1 = $2` rồi `EXECUTE` bằng path city và text Hà Nội.

**Câu hỏi:** tại sao truyền `text[]` qua bind parameter an toàn hơn ghép path SQL từ người dùng?

### Bài 40 — Java/JDBC

Viết một phương thức Java sử dụng `PreparedStatement`, `Connection.createArrayOf("text", ...)` và `ResultSet` để trích city của một order.

**Yêu cầu:** không tạo SQL bằng cách nối giá trị người dùng, đóng tài nguyên và xác định hành vi SQL NULL.

### Bài 41 — Allowlist đường dẫn

Một API chấp nhận `field=customerCity`, `field=contactEmail` hoặc `field=customerName`.

**Bài tập:** xây map từ field logic sang mảng path components cố định. Vì sao không nên cho phép arbitrary JSONPath để truy cập mọi nhánh payload?

### Bài 42 — CASE phân loại dữ liệu

Viết query phân loại `items` thành: `valid_array`, `json_null_items`, `wrong_items_type`, `sql_null_document`.

**Đáp án:** orders 1–3 hợp lệ array, order 4 JSON null, order 5 sai kiểu, order 6 SQL NULL document.

### Bài 43 — GROUP BY city

Viết query `GROUP BY payload #>> '{customer,address,city}'`.

**Câu hỏi:** orders 4/5/6 được nhóm như thế nào khi kết quả trích city là SQL NULL? Khi dùng `COALESCE(...,'<unknown>')` thì dữ liệu lỗi có bị gộp không?

### Bài 44 — ORDER BY total đúng kiểu

Viết query sắp xếp `total` giảm dần dưới dạng numeric, với `CASE` chỉ nhận JSON number, và `NULLS LAST`.

**Câu hỏi:** order 5 sẽ nằm đâu? Nếu business cho phép string số, cần sửa validation/normalization thế nào?

### Bài 45 — JSONB UPDATE có rollback

Trong transaction lab, dùng `jsonb_set` đổi city order 1 sang Huế rồi `ROLLBACK`.

**Câu hỏi:** lúc transaction đang mở `#>>` đọc được gì, sau rollback đọc được gì? Vì sao `#>>` chỉ đọc còn `jsonb_set` dùng trong UPDATE là ghi?

### Bài 46 — CHECK constraint

Thiết kế CHECK đảm bảo payload là SQL NULL hoặc JSON object. Vì sao constraint này chưa đủ để đảm bảo `items` là array và `total` là number?

### Bài 47 — Quy tắc dữ liệu tiền

Một field JSON `"price":"100000"` (string) có được coi như JSON number `100000` không? Nếu ứng dụng tài chính cần chính xác, nên ép kiểu ở đâu, dùng numeric scale nào và xử lý dữ liệu không hợp lệ ra sao?

### Bài 48 — Thiết kế schema

Một ứng dụng phải join hàng triệu orders với customers theo `customer.id` trong payload, cần foreign key và uniqueness.

**Câu hỏi:** khi nào nên tạo cột `customer_id BIGINT` riêng thay vì chỉ lưu field lồng JSON? Những lợi ích của quan hệ typed là gì?

### Bài 49 — Trường hợp string key "0"

So JSON object `{"0":"A"}` với JSON array `["A"]`.

**Bài tập:** truy cập bằng `-> '0'` và `-> 0` phù hợp với loại nguồn nào?

### Bài 50 — Capstone: truy vấn và API an toàn

Thiết kế API đọc thông tin đơn hàng có yêu cầu:

- Trả `order_id`, `customerName` và `city`;
- Trả `total` dạng số, nhưng chỉ khi JSON type đúng;
- Phân biệt coupon không có, coupon JSON null và coupon có mã;
- Liệt kê items với `sku`, `qty`, `price`;
- Giữ thứ tự items như trong JSON array;
- Không báo lỗi khi gặp order 3 rỗng hoặc order 4/5 sai kiểu; thay vào đó báo chất lượng dữ liệu;
- Không cho client đọc arbitrary JSON path;
- Có chiến lược index khi query thường xuyên tìm theo city hoặc JSON containment;
- Có prepared statements cho các input đến từ client.

**Hướng triển khai:**

1. Dùng `#>>` cho name/city; `CASE + jsonb_typeof` cho total.
2. Dùng `payload ? 'coupon'` và `payload -> 'coupon'` để phân biệt trạng thái coupon.
3. Dùng `LEFT JOIN LATERAL jsonb_array_elements(CASE ...) WITH ORDINALITY` cho items.
4. Báo các hàng `items` sai schema riêng, không biến chúng thành “đơn hàng có 0 sản phẩm” một cách âm thầm.
5. Dùng B-tree expression index cho city query cố định, GIN khi workload containment phù hợp.
6. Truyền các tham số SQL an toàn, hạn chế những field mà người gọi có thể yêu cầu.
7. Trên dữ liệu lớn, đo plan bằng `EXPLAIN`, kiểm tra output types và kiểm thử các trường hợp JSON null/missing/wrong-type.

## 38. Checklist khi thiết kế truy vấn JSON trong PostgreSQL

1. [ ] Đã biết cột là `json` hay `jsonb`.
2. [ ] Đã xác định JSON root type.
3. [ ] Đã phân biệt object key với array index.
4. [ ] Chỉ số array được xử lý theo 0-based, không nhầm `WITH ORDINALITY`.
5. [ ] Các phần trung gian truy cập bằng `->` hoặc `#>` khi còn cần JSON.
6. [ ] Phần cần trả text dùng `->>` hoặc `#>>`.
7. [ ] Đường dẫn `text[]` không bị nhầm với SQL/JSON path.
8. [ ] Key chứa dấu chấm/dấu cách/dấu phẩy được quote đúng.
9. [ ] Có quy tắc riêng cho missing key, JSON null, SQL NULL, chuỗi rỗng.
10. [ ] Dùng `jsonb_typeof`/constraints trước các phép cast có thể lỗi.
11. [ ] Không so sánh numeric dưới dạng text.
12. [ ] Không dựa vào thứ tự đánh giá điều kiện `WHERE` để bảo vệ cast.
13. [ ] Không gọi `jsonb_array_length`/`jsonb_array_elements` trên object/scalar.
14. [ ] Chọn `CROSS` hay `LEFT JOIN LATERAL` đúng yêu cầu giữ orders rỗng.
15. [ ] Có `WITH ORDINALITY` nếu cần thứ tự mảng.
16. [ ] Không biến field thiếu thành giá trị mặc định mà che mất lỗi quan trọng.
17. [ ] Đã xác định field nào cần được lưu thành cột typed.
18. [ ] Có validation cho những JSON documents đến từ nguồn không tin cậy.
19. [ ] Query thường xuyên có index phù hợp, đúng biểu thức/toán tử.
20. [ ] Đã cân nhắc B-tree expression vs GIN containment và chi phí ghi.
21. [ ] Đã đo planner trên dữ liệu đủ lớn thay vì ép index ở bảng nhỏ.
22. [ ] Các tham số được bind; đường dẫn động dùng allowlist/quyền truy cập.
23. [ ] Đã kiểm tra hành vi Java/JDBC với SQL NULL và JSONB result.
24. [ ] Có test cho document NULL, JSON null, missing, wrong-type, empty array.
25. [ ] Có kế hoạch schema-versioning và migration khi đường dẫn thay đổi.

## 39. Tài liệu PostgreSQL chính thức

Khi triển khai, hãy chọn tài liệu của **đúng major version PostgreSQL** đang sử dụng. Các liên kết dưới đây trỏ tới tài liệu PostgreSQL hiện hành:

- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): sự khác nhau giữa `json` và `jsonb`, cách lưu trữ, containment, indexing và JSONPath.
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): bảng `->`, `->>`, `#>`, `#>>`, `?`, `@>`, `@?`, `@@` và các hàm JSON/JSONB.
- [SQL/JSON Path Language](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-SQLJSON-PATH): cú pháp `$`, accessors, filters, lax và strict.
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html): PostgreSQL SQL arrays, khác JSON arrays.
- [Array Types](https://www.postgresql.org/docs/current/arrays.html): subscript/lower bounds của SQL arrays.
- [Set Returning Functions](https://www.postgresql.org/docs/current/functions-srf.html): cách mở rộng dữ liệu thành nhiều rows.
- [LATERAL Subqueries](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-LATERAL): `LATERAL` trong `FROM`, phối hợp table function với row bên trái.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, GIN, GiST và các phương thức truy cập.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): B-tree trên giá trị trích xuất từ JSON.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index methods, operator classes, expression index và các giới hạn.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): cách xem optimizer plan, tác dụng chạy thật của `ANALYZE`.
- [Data Definition / Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, NOT NULL, FK và các ràng buộc dữ liệu quan hệ.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): tham số hóa statements.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): cập nhật hàng khi dùng `jsonb_set` trong SET expression.
- [JSONB Subscripting](https://www.postgresql.org/docs/current/datatype-json.html#DATATYPE-JSONB-SUBSCRIPTING): cú pháp subscripting JSONB ở các phiên bản hỗ trợ.

Các toán tử trích xuất `->`, `->>`, `#>`, `#>>` là nền tảng lâu đời của PostgreSQL. Những tính năng bổ sung như SQL/JSON path và JSONB subscripting có ngưỡng hỗ trợ theo phiên bản; không tự sao chép cú pháp từ tài liệu mới sang server cũ mà không xác nhận.

## 40. Tổng kết

**Trích xuất JSON trong PostgreSQL** dựa trên bốn toán tử cần nhớ:

| Toán tử | Ghi nhớ nhanh |
| --- | --- |
| **`->`** | Lấy một khóa object hoặc index JSON array, **trả JSON/JSONB** |
| **`->>`** | Lấy một khóa object hoặc index JSON array, **trả SQL text** |
| **`#>`** | Đi qua nhiều cấp bằng **`text[]` path**, **trả JSON/JSONB** |
| **`#>>`** | Đi qua nhiều cấp bằng **`text[]` path**, **trả SQL text** |

Với object lồng nhau, bạn có thể viết `payload -> 'customer' -> 'address' ->> 'city'` hoặc `payload #>> '{customer,address,city}'`. Với array, JSON index bắt đầu từ **0**; các chỉ số âm đếm từ cuối, và `WITH ORDINALITY` của SQL **bắt đầu từ 1**. Khi cần mọi phần tử array, hãy mở rộng bằng `jsonb_array_elements`/`LATERAL` thay vì liệt kê chỉ số cố định.

Khi gặp dữ liệu không đồng nhất, **đừng đánh đồng** key thiếu, JSON null, SQL NULL, string rỗng và sai kiểu. Các toán tử trích xuất thường trả SQL NULL nếu không tìm được đường dẫn, nhưng một số hàm như `jsonb_array_length` có thể báo lỗi nếu input không phải array. `jsonb_typeof`, `?`, `CASE` và validation/constraints giúp bạn xác định đúng trường hợp trước khi ép kiểu.

Đường dẫn `text[]` của `#>`/`#>>` khác với **SQL/JSON path** dạng `$.customer.address.city`. JSONPath có wildcard và predicates; còn `#>>` đơn giản và phù hợp khi biết chính xác các cấp cần truy cập. Với truy vấn nhiều hàng, chọn index theo operator thực tế: **B-tree expression index** cho một path trích xuất cố định, **GIN** cho những JSONB containment/key/path conditions được hỗ trợ.

Cuối cùng, **truy vấn đúng kiểu và đúng quyền quan trọng hơn cú pháp ngắn**. Hãy parameterize đường dẫn từ JDBC, giới hạn các field được phép đọc, bảo đảm JSON schema rõ ràng và cân nhắc đưa các field cốt lõi thành cột quan hệ typed. Khi nắm chắc bốn toán tử và các tình huống null/array/type, bạn có thể trích xuất JSON linh hoạt mà vẫn giữ được tính đúng, khả năng bảo trì và hiệu năng của PostgreSQL.
