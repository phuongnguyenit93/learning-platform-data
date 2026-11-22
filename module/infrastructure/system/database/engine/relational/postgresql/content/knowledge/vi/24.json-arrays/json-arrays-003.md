# Toán tử chứa, tồn tại và so sánh jsonb trong PostgreSQL

Một cột `jsonb` cho phép PostgreSQL lưu dữ liệu bán cấu trúc, chẳng hạn thuộc tính sản phẩm, cấu hình, metadata hoặc payload từ sự kiện. Tuy nhiên, **có một key**, **có một giá trị**, **chứa một cấu trúc JSON**, và **so sánh hai tài liệu JSON** là những câu hỏi khác nhau.

Ví dụ, xét tài liệu:

~~~json
{
  "sku": "KB-01",
  "active": true,
  "tags": ["tech", "sale"],
  "vendor": {"name": "A", "country": "VN"},
  "notes": null
}
~~~

Cần phân biệt:

~~~sql
-- Có key "vendor" ở cấp ngoài cùng?
doc ? 'vendor'

-- Tài liệu chứa đối tượng vendor có country = VN?
doc @> '{"vendor":{"country":"VN"}}'::jsonb

-- Trong đối tượng vendor có key "country"?
(doc -> 'vendor') ? 'country'

-- Tags chứa giá trị chuỗi "sale"?
doc @> '{"tags":["sale"]}'::jsonb

-- Có key notes với JSON null hay không?
doc @> '{"notes":null}'::jsonb
~~~

Tất cả đều là biểu thức hợp lệ, nhưng chúng **không đồng nghĩa**. Một sai sót nhỏ có thể làm lọc thiếu bản ghi, so sánh sai kiểu hoặc xây chỉ mục không được sử dụng.

Bài học giải thích ba nhóm toán tử chính:

1. **Chứa (*containment*):** `@>` và `<@`, bao gồm các quy tắc riêng cho object và array.
2. **Tồn tại (*existence*):** `?`, `?|`, `?&` để kiểm tra key của object hoặc phần tử chuỗi ở cấp đang xét.
3. **So sánh (*comparison*):** `=`, `<>`, `<`, `<=`, `>`, `>=` và những vấn đề về cấu trúc, kiểu JSON, thứ tự B-tree, SQL `NULL`.

Ngoài ra, bài giới thiệu `@?`/`@@` của SQL/JSON path, cách khai thác GIN `jsonb_ops`/`jsonb_path_ops`, B-tree, expression index, `EXPLAIN`, bài lab và bài tập có lời giải.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu sự khác biệt giữa kiểu `json` và `jsonb` trong PostgreSQL.
2. Dùng `@>` và `<@` để truy vấn tài liệu chứa object, array và cấu trúc lồng nhau.
3. Hiểu vì sao thứ tự phần tử và phần tử trùng trong array có ý nghĩa khác khi xét containment so với equality.
4. Dùng `?`, `?|`, `?&` đúng phạm vi cấp JSON hiện tại.
5. Phân biệt key thiếu, key có giá trị `null` và cả biểu thức SQL `NULL`.
6. So sánh hai giá trị `jsonb` mà không chuyển tùy tiện sang text.
7. Hiểu thứ tự mặc định của kiểu JSON khi dùng B-tree hoặc `ORDER BY` trên `jsonb`.
8. Dùng toán tử JSONPath `@?` và `@@` khi cần kiểm tra cấu trúc sâu hơn.
9. Chọn GIN operator class tương ứng với các toán tử được ứng dụng sử dụng.
10. Biết khi nào cần expression index hay B-tree thay vì một GIN index toàn tài liệu.
11. Đọc `EXPLAIN (ANALYZE, BUFFERS)` để xác minh index có được dùng thật hay không.
12. Nhận ra giới hạn của JSONB và khi nào nên dùng cột quan hệ có kiểu rõ ràng.

## 2. JSON khác JSONB ở điểm nào?

PostgreSQL cung cấp hai kiểu dữ liệu JSON quen thuộc:

| Tiêu chí | `json` | `jsonb` |
| --- | --- | --- |
| Cách lưu | Giữ biểu diễn văn bản JSON được phân tích hợp lệ | Lưu biểu diễn nhị phân đã phân tích |
| Khoảng trắng và thứ tự key đầu vào | Giữ trong biểu diễn gốc | Không giữ như chuỗi gốc |
| Key trùng trong object | Có thể giữ biểu diễn đầu vào chứa key trùng | Giữ một giá trị cho key, thường là giá trị xuất hiện sau cùng |
| Toán tử containment `@>` | Không có cùng tập toán tử trực tiếp như JSONB | Hỗ trợ |
| So sánh bằng/toán tử thứ tự | `json` không có tập so sánh B-tree thông thường | `jsonb` có equality và B-tree ordering |
| GIN indexing | Thường cần chuyển/biểu thức theo nhu cầu | Có opclasses GIN chuyên dụng |
| Cập nhật toàn tài liệu | Phải xử lý giá trị JSON | Phải xây dựng giá trị jsonb mới khi thay đổi |

Ví dụ:

~~~sql
SELECT
    '{"a":1,"a":2}'::json AS raw_json,
    '{"a":1,"a":2}'::jsonb AS normalized_jsonb;
~~~

Với `jsonb`, kết quả chỉ giữ một giá trị cho key `a`, tương ứng giá trị cuối. Không nên dựa vào **thứ tự key** của JSONB khi serialize ra ngoài.

### 2.1. JSONB không phải bảng quan hệ thu nhỏ hoàn hảo

JSONB hữu ích cho thuộc tính linh hoạt, nhưng không tự có:

- Kiểu cột riêng cho từng key.
- `NOT NULL` và `CHECK` riêng cho mọi trường nếu không khai báo.
- Foreign key tự động trên ID nằm sâu trong JSON.
- Thống kê tương đương mọi cột quan hệ cho mọi đường dẫn JSON.

Với dữ liệu nghiệp vụ ổn định như `customer_id`, `amount`, `created_at`, bảng quan hệ/cột có kiểu rõ ràng thường vẫn có lợi thế về constraint, truy vấn và thống kê.

### 2.2. Dùng JSONB khi cần ngữ nghĩa cấu trúc

Nếu mục tiêu là hỏi “tài liệu có chứa những thuộc tính này không?” hoặc “key này có tồn tại không?”, `jsonb` và toán tử/index chuyên dụng là lựa chọn đáng cân nhắc.

## 3. Chuẩn bị schema và dữ liệu thực hành

Các ví dụ sử dụng **database lab**, không ghi vào hệ thống sản xuất. Để tái lập từ đầu, tạo schema riêng.

~~~sql
CREATE SCHEMA json_lab;

CREATE TABLE json_lab.products (
    product_id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    created_at timestamptz NOT NULL
);
~~~

Ý nghĩa:

- `product_id`: ID quan hệ, có `PRIMARY KEY`.
- `doc`: tài liệu JSONB, bắt buộc không phải **SQL NULL**.
- `created_at`: cột thời gian có kiểu rõ ràng để phục vụ lọc/sắp xếp.

### 3.1. Chèn mười tài liệu có cấu trúc khác nhau

~~~sql
INSERT INTO json_lab.products
    (product_id, doc, created_at)
VALUES
    (
      1,
      '{
        "sku":"KB-01",
        "category":"keyboard",
        "price":120,
        "active":true,
        "tags":["tech","sale"],
        "stock":12,
        "vendor":{"name":"A","country":"VN"},
        "notes":null
      }'::jsonb,
      '2026-01-01 10:00:00+00'
    ),
    (
      2,
      '{
        "sku":"MS-02",
        "category":"mouse",
        "price":45,
        "active":true,
        "tags":["tech"],
        "stock":0,
        "vendor":{"name":"B","country":"VN"}
      }'::jsonb,
      '2026-01-02 10:00:00+00'
    ),
    (
      3,
      '{
        "sku":"BK-03",
        "category":"book",
        "price":18,
        "active":false,
        "tags":["education","sale"],
        "vendor":{"name":"A","country":"US"},
        "notes":"used"
      }'::jsonb,
      '2026-01-03 10:00:00+00'
    ),
    (
      4,
      '{
        "sku":"MN-04",
        "category":"monitor",
        "price":300,
        "active":true,
        "tags":["tech","office"],
        "stock":3,
        "vendor":{"name":"C","country":"JP"},
        "attributes":{"dimensions":{"width":24}}
      }'::jsonb,
      '2026-01-04 10:00:00+00'
    ),
    (
      5,
      '{
        "sku":"PN-05",
        "category":"pen",
        "price":2.5,
        "active":true,
        "tags":["office"],
        "stock":null,
        "vendor":{"name":"B","country":"VN"}
      }'::jsonb,
      '2026-01-05 10:00:00+00'
    ),
    (
      6,
      '{
        "sku":"HD-06",
        "category":"headphones",
        "price":80,
        "active":false,
        "tags":[],
        "stock":4,
        "vendor":{"name":"A","country":"VN"}
      }'::jsonb,
      '2026-01-06 10:00:00+00'
    ),
    (
      7,
      '{
        "sku":"ST-07",
        "category":"stand",
        "price":70,
        "active":true,
        "tags":["office","sale"],
        "stock":6,
        "vendor":{"name":"C","country":"VN"}
      }'::jsonb,
      '2026-01-07 10:00:00+00'
    ),
    (
      8,
      '{
        "sku":"CB-08",
        "category":"cable",
        "price":"20",
        "active":true,
        "tags":["tech"],
        "stock":10,
        "vendor":{"name":"D","country":"VN"}
      }'::jsonb,
      '2026-01-08 10:00:00+00'
    ),
    (
      9,
      '{
        "sku":"MT-09",
        "category":"mount",
        "price":90,
        "active":true,
        "tags":["tech","sale"],
        "stock":null,
        "notes":null
      }'::jsonb,
      '2026-01-09 10:00:00+00'
    ),
    (
      10,
      '{
        "sku":"PL-10",
        "category":"planner",
        "price":15,
        "active":true,
        "tags":["office"],
        "stock":3,
        "vendor":{"name":"C","country":"VN"},
        "attributes":{
          "sizes":[
            {"name":"small","units":2},
            {"name":"large","units":5}
          ]
        }
      }'::jsonb,
      '2026-01-10 10:00:00+00'
    );
~~~

Dữ liệu cố ý bao gồm:

- `tags` là JSON array chứa chuỗi.
- `vendor` là object lồng.
- `notes` **thiếu** ở một số tài liệu, **JSON null** ở tài liệu khác.
- `stock` có số, JSON null hoặc không có.
- `price` chủ yếu là JSON number nhưng tài liệu `CB-08` lưu chuỗi `"20"`, để minh họa lỗi không nhất quán kiểu.
- Tài liệu `MT-09` không có key `vendor`.

### 3.2. Xem dữ liệu

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku,
    doc -> 'price' AS json_price,
    jsonb_typeof(doc -> 'price') AS price_type
FROM json_lab.products
ORDER BY product_id;
~~~

### 3.3. Nguyên tắc đọc ví dụ

Khi bài ghi “trả các ID”, đó là kết quả dựa trên **mười tài liệu vừa chèn**. Nếu bạn sửa dữ liệu lab, kết quả có thể đổi. Những kế hoạch `EXPLAIN` phụ thuộc môi trường; không kỳ vọng kiểu scan cố định trên bảng chỉ mười hàng.

## 4. Tổng quan các toán tử JSONB trọng tâm

| Nhóm | Toán tử | Ý nghĩa |
| --- | --- | --- |
| Chứa | `left @> right` | JSONB trái chứa JSONB phải |
| Được chứa | `left <@ right` | JSONB trái được JSONB phải chứa |
| Tồn tại | `value ? text` | Có key của object hoặc phần tử chuỗi của array **ở cấp hiện tại** |
| Bất kỳ | `value ?| text[]` | Có ít nhất một key/phần tử trong danh sách |
| Tất cả | `value ?& text[]` | Có đủ mọi key/phần tử trong danh sách |
| Bằng | `left = right` | Hai JSONB có giá trị bằng nhau theo ngữ nghĩa cấu trúc |
| Khác | `left <> right` | Hai JSONB không bằng nhau |
| Thứ tự | `<`, `<=`, `>`, `>=` | So sánh theo thứ tự B-tree của JSONB |
| JSONPath existence | `value @? jsonpath` | Có item khớp biểu thức path hay không |
| JSONPath predicate | `value @@ jsonpath` | Đánh giá kết quả boolean predicate của JSONPath |

Các toán tử truy cập:

~~~sql
doc ->  'key'
doc ->> 'key'
doc #>  '{path,to,key}'
doc #>> '{path,to,key}'
~~~

không thuộc nhóm existence/containment, nhưng rất quan trọng để **chuyển điểm kiểm tra xuống một object/array lồng nhau**.

## 5. Toán tử chứa @>: ý nghĩa cơ bản

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
    @> '{"a":1}'::jsonb AS contains_a;
~~~

Kết quả là `true`: object bên trái có mọi cặp key/value mà object bên phải yêu cầu.

### 5.1. Chứa không có nghĩa hai tài liệu bằng nhau

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb @> '{"a":1}'::jsonb
        AS contains_subset,
    '{"a":1,"b":2}'::jsonb = '{"a":1}'::jsonb
        AS structurally_equal;
~~~

Kết quả:

- `contains_subset = true`.
- `structurally_equal = false`.

Object bên trái được phép **có thêm key** khi xét `@>`.

### 5.2. Chứa object có giá trị khác thì false

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
    @> '{"a":3}'::jsonb AS contains_wrong_value;
~~~

Kết quả `false`: chỉ có key `a` chưa đủ, **giá trị** cũng phải khớp.

### 5.3. Truy vấn sản phẩm theo thuộc tính

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"active":true}'::jsonb
ORDER BY product_id;
~~~

Predicate tìm tài liệu có key `active` nhận đúng JSON boolean `true`, **không** nhận chuỗi `"true"` hay số `1`.

### 5.4. JSON number khác JSON string

~~~sql
SELECT
    '{"price":20}'::jsonb
      @> '{"price":20}'::jsonb AS number_matches,
    '{"price":"20"}'::jsonb
      @> '{"price":20}'::jsonb AS text_vs_number;
~~~

Kết quả lần lượt `true`, `false`. PostgreSQL không ép chuỗi `"20"` thành số `20` để thỏa containment.

## 6. Chứa cấu trúc lồng nhau

JSONB containment hoạt động **theo cấu trúc**.

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{
  "vendor": {
    "country": "VN"
  }
}'::jsonb
ORDER BY product_id;
~~~

Predicate chỉ yêu cầu key `vendor` là object có `country='VN'`. Object `vendor` được phép có thêm `name`.

### 6.1. Tại sao phép chứa này đúng?

Trong tài liệu `KB-01`:

~~~json
{"vendor":{"name":"A","country":"VN"}}
~~~

Object `vendor` thực sự có cấu trúc:

~~~json
{"country":"VN"}
~~~

như một tập con cặp key/value.

### 6.2. Không đi xuyên tầng nếu RHS khác cấu trúc

~~~sql
SELECT
    '{"vendor":{"country":"VN"}}'::jsonb
    @> '{"country":"VN"}'::jsonb
    AS top_level_contains_country;
~~~

Kết quả `false`. Key `country` nằm bên trong `vendor`, không nằm ở cấp ngoài cùng. `@>` **không phải phép tìm mọi key giống tên ở bất kỳ độ sâu nào**.

### 6.3. Có thể truy vấn sâu hơn bằng cấu trúc đầy đủ

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{
  "attributes": {
    "dimensions": {"width":24}
  }
}'::jsonb;
~~~

Query khớp tài liệu `MN-04` với đường dẫn `attributes.dimensions.width` bằng JSON number `24`.

### 6.4. Không tự suy tìm sâu như một phép bằng text

~~~sql
WHERE doc::text LIKE '%"country": "VN"%'
~~~

không phải sự thay thế tương đương cho containment. Thứ tự key, khoảng trắng, kiểu dữ liệu, escaped strings và hiệu năng đều khiến tìm trên biểu diễn text rất mong manh.

## 7. Containment với JSON array

Xét:

~~~sql
SELECT
    '["tech","sale","office"]'::jsonb
      @> '["sale"]'::jsonb
      AS contains_sale,
    '["tech","sale"]'::jsonb
      @> '["office"]'::jsonb
      AS contains_office;
~~~

Kết quả: `true` và `false`.

### 7.1. Thứ tự phần tử không quan trọng với containment

~~~sql
SELECT
    '["tech","sale"]'::jsonb
      @> '["sale","tech"]'::jsonb
      AS contains_reordered;
~~~

Kết quả `true`: khi kiểm tra `@>`, thứ tự trong array không quyết định kết quả theo cách equality quyết định.

### 7.2. Phần tử trùng được coi một lần khi xét containment

~~~sql
SELECT
    '["sale"]'::jsonb
      @> '["sale","sale"]'::jsonb
      AS contains_repeated;
~~~

Kết quả `true` trong ngữ nghĩa JSONB containment. Khi tìm containment, sự lặp lại một phần tử array không tạo yêu cầu “phải xuất hiện hai lần”.

**Đừng áp kết luận này sang phép bằng (`=`)**: hai array với số phần tử/trật tự khác nhau không tự bằng nhau.

### 7.3. Kiểu phần tử phải tương thích

~~~sql
SELECT
    '[1,2,3]'::jsonb @> '[2]'::jsonb AS number_two,
    '[1,2,3]'::jsonb @> '["2"]'::jsonb AS string_two;
~~~

Kết quả `true` và `false`.

### 7.4. Truy vấn tags

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"tags":["sale"]}'::jsonb
ORDER BY product_id;
~~~

Với dữ liệu lab, kết quả có `product_id` **1, 3, 7, 9**.

### 7.5. Tìm các tag cùng lúc

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"tags":["tech","sale"]}'::jsonb
ORDER BY product_id;
~~~

Ví dụ này yêu cầu array tags chứa **cả** `tech` và `sale` (không cần cùng vị trí thứ tự).

## 8. Ngoại lệ: array có thể chứa giá trị nguyên thủy

PostgreSQL hỗ trợ một trường hợp containment đặc biệt: **một array có thể chứa một primitive value**.

~~~sql
SELECT
    '["tech","sale"]'::jsonb @> '"sale"'::jsonb
      AS array_contains_primitive,
    '"sale"'::jsonb @> '["sale"]'::jsonb
      AS primitive_contains_array;
~~~

Kết quả thường là:

- Array chứa primitive `"sale"`: `true`.
- Primitive chứa array `["sale"]`: `false`.

Điều này **không** có nghĩa mọi object có thể chứa một primitive nằm sâu bên trong object đó.

### 8.1. Tại sao vẫn khuyên dùng cấu trúc RHS?

Khi lọc bảng:

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

diễn đạt rất rõ ràng “key tags chứa sale”, tránh nhầm `sale` là một field/giá trị ở vị trí khác.

### 8.2. Containment không phải tìm kiếm substring

~~~sql
SELECT
    '["sale"]'::jsonb @> '["sal"]'::jsonb AS substring_match;
~~~

Kết quả `false`. JSONB containment xét **giá trị/phần tử**, không xét chuỗi con. Muốn tìm substring phải dùng phép tìm text thích hợp, có thể kết hợp expression/trigram index theo workload.

## 9. Containment của array chứa object

Một ứng dụng có thể lưu:

~~~json
{
  "lines": [
    {"sku":"A-01","qty":2,"price":50},
    {"sku":"B-02","qty":1,"price":80}
  ]
}
~~~

Truy vấn:

~~~sql
SELECT
    '{
      "lines": [
        {"sku":"A-01","qty":2,"price":50},
        {"sku":"B-02","qty":1,"price":80}
      ]
    }'::jsonb
    @> '{
      "lines": [
        {"sku":"A-01","qty":2}
      ]
    }'::jsonb
    AS has_matching_line;
~~~

Kết quả `true`. RHS chỉ yêu cầu một phần tử object với những field tối thiểu. Object bên trái có thể có thêm field `price`.

### 9.1. Không đồng nhất “cùng một phần tử object” với hai phần tử độc lập

Nếu nghiệp vụ đòi **cùng một line có SKU A-01 và qty 2**, viết:

~~~sql
WHERE doc @> '{"lines":[{"sku":"A-01","qty":2}]}'::jsonb
~~~

diễn đạt rõ hai điều kiện trên **một object line**.

Không thay bằng hai điều kiện riêng kiểu:

~~~sql
WHERE doc @> '{"lines":[{"sku":"A-01"}]}'::jsonb
  AND doc @> '{"lines":[{"qty":2}]}'::jsonb
~~~

vì điều kiện SKU và điều kiện qty có thể được thỏa bởi **hai object line khác nhau**.

### 9.2. Đây là sai lệch logic thường gặp

Cách tốt nhất là mô tả đúng cấu trúc và tính đồng thời của điều kiện. Nếu logic phức tạp, có thể dùng JSONPath với filter trên **cùng item** hoặc chuẩn hóa mảng thành bảng con.

## 10. Toán tử được chứa <@

`left <@ right` là chiều ngược của `right @> left`.

~~~sql
SELECT
    '{"country":"VN"}'::jsonb
      <@ '{"country":"VN","name":"A"}'::jsonb
      AS subset_of_object;
~~~

Kết quả `true`.

### 10.1. Hai cách diễn đạt tương đương về hướng

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
      @> '{"a":1}'::jsonb AS left_contains_right,
    '{"a":1}'::jsonb
      <@ '{"a":1,"b":2}'::jsonb AS right_is_contained;
~~~

Hai phép đều hỏi một quan hệ containment, nhưng **vị trí toán hạng đã đổi**.

### 10.2. Chú ý khi chọn index

GIN index trên cột `doc` thường được sử dụng với **toán tử và phía toán hạng mà operator class hỗ trợ**. Truy vấn:

~~~sql
WHERE doc @> '{"active":true}'::jsonb
~~~

là mẫu tự nhiên cho GIN chứa dữ liệu của `doc`.

Không tự suy:

~~~sql
WHERE '{"active":true}'::jsonb @> doc
~~~

hoặc viết lại với `doc <@ ...` sẽ khai thác chính cùng index theo cách giống nhau. Semantics và index strategy phụ thuộc **hướng toán tử**.

### 10.3. <@ hữu ích để biểu diễn tập con

~~~sql
SELECT
    '["sale"]'::jsonb <@ '["tech","sale"]'::jsonb
      AS sale_is_subset;
~~~

Nhưng đừng coi `<@` là một phép “tìm key” chuyên dụng; với kiểm tra tồn tại key đơn giản, `?` thường rõ ý nghĩa hơn.

## 11. Toán tử tồn tại ?: key ở cấp hiện tại

~~~sql
SELECT
    '{"sku":"KB-01","price":120}'::jsonb
      ? 'sku' AS sku_exists,
    '{"sku":"KB-01"}'::jsonb
      ? 'vendor' AS vendor_exists;
~~~

Kết quả `true` và `false`.

### 11.1. Chỉ hỏi key, không hỏi giá trị

~~~sql
SELECT
    '{"notes":null}'::jsonb ? 'notes'
      AS notes_key_exists,
    '{"notes":null}'::jsonb
      @> '{"notes":null}'::jsonb
      AS notes_is_json_null;
~~~

Cả hai `true`, nhưng câu hỏi khác nhau:

- `? 'notes'`: key có mặt, **bất kể giá trị**.
- `@> '{"notes":null}'`: key có mặt và giá trị **JSON null**.

### 11.2. ? không đi sâu tự động

~~~sql
SELECT
    '{"vendor":{"country":"VN"}}'::jsonb
      ? 'country' AS top_level_country;
~~~

Kết quả `false` vì key `country` chỉ ở object con.

### 11.3. Query ở bảng lab

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc ? 'vendor'
ORDER BY product_id;
~~~

Chọn các tài liệu có key `vendor` cấp ngoài, bất kể trong vendor có key nào.

## 12. ? với JSON array

Đối với **JSON array**, `?` có thể kiểm tra **phần tử chuỗi ở cấp hiện tại**.

~~~sql
SELECT
    '["tech","sale"]'::jsonb ? 'sale'
      AS array_has_sale,
    '["tech","sale"]'::jsonb ? 'office'
      AS array_has_office;
~~~

Kết quả `true`, `false`.

### 12.1. Không đồng nhất ? với tìm mọi JSON number

~~~sql
SELECT
    '[1,2,3]'::jsonb ? '2'
      AS numeric_array_has_text_two,
    '[1,2,3]'::jsonb @> '2'::jsonb
      AS numeric_array_contains_number_two;
~~~

`? '2'` kiểm tra **chuỗi** `"2"`, không phải JSON number `2`. Phép `@> '2'::jsonb` phù hợp hơn nếu muốn containment với giá trị số.

### 12.2. Không đi qua array objects theo key

~~~sql
SELECT
    '[{"sku":"A-01"}]'::jsonb
    ? 'sku' AS array_of_objects_has_sku_at_top;
~~~

Không tìm `sku` bên trong từng object con. Với cấu trúc này, dùng containment:

~~~sql
SELECT
    '[{"sku":"A-01"}]'::jsonb
    @> '[{"sku":"A-01"}]'::jsonb
    AS object_present;
~~~

### 12.3. Toán tử tồn tại có phụ thuộc cấp

Nếu cột `doc` là object chứa key `tags`, câu:

~~~sql
WHERE doc ? 'sale'
~~~

**không** tương đương:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

Đầu tiên tìm top-level key `sale` trong doc; thứ hai kiểm tra chuỗi `sale` trong array tags.

## 13. Toán tử ?|: tồn tại ít nhất một

`?|` nhận danh sách kiểu PostgreSQL `text[]` và kiểm tra xem **ít nhất một** key/phần tử chuỗi có tồn tại ở cấp hiện tại hay không.

~~~sql
SELECT
    '{"sku":"KB-01","price":120}'::jsonb
      ?| ARRAY['sku','name']
      AS has_sku_or_name;
~~~

Kết quả `true`, vì có `sku`.

### 13.1. Tìm tài liệu có vendor hoặc notes

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc ?| ARRAY['vendor','notes']
ORDER BY product_id;
~~~

Điều kiện chỉ yêu cầu **một** trong hai key.

### 13.2. Dùng với tags

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE (doc -> 'tags') ?| ARRAY['sale','office']
ORDER BY product_id;
~~~

Truy vấn có nghĩa: array tags chứa `sale` **hoặc** `office`.

### 13.3. Kiểu của toán hạng phải đúng

Đối số phải là `text[]`:

~~~sql
-- Kiểu mảng PostgreSQL, không phải JSON array:
ARRAY['sale','office']
~~~

Không nhầm:

~~~sql
'["sale","office"]'::jsonb
~~~

với `text[]`. Hai cấu trúc mảng của PostgreSQL/JSONB là hai kiểu khác nhau.

## 14. Toán tử ?&: tồn tại tất cả

~~~sql
SELECT
    '{"sku":"KB-01","price":120,"active":true}'::jsonb
      ?& ARRAY['sku','price']
      AS has_both_fields;
~~~

Kết quả `true` vì object có cả `sku` và `price`.

### 14.1. Tìm tags đồng thời

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE (doc -> 'tags') ?& ARRAY['tech','sale']
ORDER BY product_id;
~~~

Trong lab, sản phẩm `KB-01` và `MT-09` có cả hai tag.

### 14.2. ?| và ?& chỉ khác phép logic

| Expression | Ý nghĩa |
| --- | --- |
| `? 'tech'` | Có tech |
| `?| ARRAY['tech','sale']` | Có tech **hoặc** sale |
| `?& ARRAY['tech','sale']` | Có tech **và** sale |

### 14.3. Không nhầm ?& với array equality

~~~sql
SELECT
    '["tech","sale","office"]'::jsonb
      ?& ARRAY['tech','sale'] AS all_exist;
~~~

Kết quả `true` dù array bên trái có thêm `office`. `?&` kiểm tra sự tồn tại các phần tử chuỗi, không yêu cầu hai array bằng nhau.

### 14.4. Trường hợp danh sách đầu vào rỗng

Với các lượng từ logic, “ít nhất một trong danh sách rỗng” không có phần tử để thỏa, còn “tất cả phần tử trong danh sách rỗng” là điều kiện đúng rỗng. Trong SQL thực, nên thiết kế API xử lý danh sách đầu vào rỗng **rõ ràng theo yêu cầu nghiệp vụ**, thay vì để logic nhiều toán tử và đặc tính trả về gây bất ngờ.

## 15. Toán tử và mức lồng nhau: bảng phân biệt

Giả sử:

~~~json
{
  "sku": "KB-01",
  "tags": ["tech", "sale"],
  "vendor": {
    "country": "VN"
  }
}
~~~

| Điều kiện | Đúng/sai | Vì sao? |
| --- | --- | --- |
| `doc ? 'sku'` | Đúng | Key sku cấp ngoài |
| `doc ? 'country'` | Sai | country chỉ nằm sâu trong vendor |
| `(doc -> 'vendor') ? 'country'` | Đúng | Đã chuyển tới object vendor |
| `doc ? 'sale'` | Sai | sale không phải key cấp ngoài |
| `(doc -> 'tags') ? 'sale'` | Đúng | sale là phần tử chuỗi của tags |
| `doc @> '{"tags":["sale"]}'` | Đúng | Containment theo cấu trúc |
| `doc @> '{"vendor":{"country":"VN"}}'` | Đúng | Nested object containment |
| `doc @> '{"country":"VN"}'` | Sai | RHS yêu cầu country ở cấp ngoài |
| `doc ?& ARRAY['sku','tags']` | Đúng | Cả hai top-level keys có mặt |
| `doc ?| ARRAY['discount','sku']` | Đúng | Ít nhất sku có mặt |

**Quy tắc nhớ nhanh:** `?`, `?|`, `?&` kiểm tra **cấp đang xét**; `@>` so khớp **cấu trúc RHS**, có thể bao gồm cấu trúc con được mô tả.

## 16. Đi sâu bằng ->, ->>, #> và #>>

| Toán tử | Kiểu kết quả | Dùng khi |
| --- | --- | --- |
| `doc -> 'key'` | `jsonb` | Lấy giá trị JSONB của key để tiếp tục dùng JSONB operators |
| `doc ->> 'key'` | `text` | Lấy giá trị dạng văn bản |
| `doc #> '{a,b}'` | `jsonb` | Lấy JSONB tại đường dẫn nhiều cấp |
| `doc #>> '{a,b}'` | `text` | Lấy text tại đường dẫn nhiều cấp |

### 16.1. Lấy object con để kiểm tra key

~~~sql
SELECT
    product_id,
    doc #> '{vendor}' AS vendor_doc
FROM json_lab.products
WHERE (doc #> '{vendor}') ? 'country';
~~~

### 16.2. Lấy field con dạng text để so sánh

~~~sql
SELECT
    product_id,
    doc #>> '{vendor,country}' AS vendor_country
FROM json_lab.products
WHERE doc #>> '{vendor,country}' = 'VN'
ORDER BY product_id;
~~~

### 16.3. So sánh text khác so JSONB string

~~~sql
SELECT
    '"VN"'::jsonb AS jsonb_string,
    ('"VN"'::jsonb #>> '{}') AS text_value;
~~~

Một bên là JSONB string, một bên là SQL text. Trong ứng dụng, bind parameter và chọn toán tử đúng kiểu thay vì ép text/JSONB tùy tiện.

### 16.4. Đường dẫn không hợp lệ thường trả SQL NULL

Khi field/element không tồn tại hoặc cấu trúc không phù hợp, những toán tử truy cập JSON thường trả **SQL NULL** thay vì báo một lỗi chỉ vì thiếu key. Điều này rất quan trọng khi kiểm tra `IS NULL`.

## 17. Ba trạng thái: key thiếu, JSON null và SQL NULL

Một lỗi logic rất thường gặp là coi ba trạng thái sau như một:

1. Tài liệu **không có key**.
2. Tài liệu **có key**, giá trị là JSON `null`.
3. Toàn biểu thức/cột là **SQL `NULL`**.

Ví dụ:

~~~sql
SELECT
    '{}'::jsonb ? 'notes'
      AS missing_has_key,
    '{"notes":null}'::jsonb ? 'notes'
      AS json_null_has_key;
~~~

Kết quả `false` và `true`.

### 17.1. Kiểm tra bằng -> và IS NULL

~~~sql
SELECT
    ('{}'::jsonb -> 'notes') IS NULL
      AS missing_is_sql_null,
    ('{"notes":null}'::jsonb -> 'notes') IS NULL
      AS json_null_is_sql_null;
~~~

Kết quả:

- Key thiếu: `->` trả **SQL NULL**, nên `IS NULL` là `true`.
- Key có JSON null: `->` trả một **giá trị JSONB null**, không phải SQL NULL, nên `IS NULL` là `false`.

### 17.2. ->> làm mất một phần phân biệt này

~~~sql
SELECT
    ('{}'::jsonb ->> 'notes') IS NULL
      AS missing_text_null,
    ('{"notes":null}'::jsonb ->> 'notes') IS NULL
      AS json_null_text_null;
~~~

Với `->>`, cả key thiếu và JSON null đều có thể cho SQL NULL. Vì vậy, nếu cần phân biệt **không có key** với **key null**, dùng `?` và/hoặc `->` theo đúng ngữ nghĩa.

### 17.3. Kiểm tra JSON null qua JSONB equality

~~~sql
SELECT
    ('{"notes":null}'::jsonb -> 'notes')
      = 'null'::jsonb AS is_json_null;
~~~

Kết quả `true`. Điều này khác:

~~~sql
WHERE (doc -> 'notes') IS NULL
~~~

vốn tìm những trường hợp expression trả SQL NULL.

### 17.4. Truy vấn ba loại trên bảng lab

Tài liệu **có key notes**:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc ? 'notes'
ORDER BY product_id;
~~~

Tài liệu có **JSON null** ở notes:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"notes":null}'::jsonb
ORDER BY product_id;
~~~

Tài liệu **không có key notes**:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE NOT (doc ? 'notes')
ORDER BY product_id;
~~~

Tài liệu chứa key notes có JSON null là `1` và `9`. Tài liệu `3` có notes là chuỗi `"used"`. Các tài liệu còn lại không có notes.

### 17.5. Cột doc đã NOT NULL vẫn có JSON null

`doc jsonb NOT NULL` chỉ ngăn **SQL NULL của toàn cột doc**. Nó không tự ngăn:

~~~sql
INSERT INTO json_lab.products(product_id, doc, created_at)
VALUES (
    11,
    'null'::jsonb,
    now()
);
~~~

Giá trị `'null'::jsonb` là một tài liệu JSONB hợp lệ (JSON null), **khác SQL NULL**. Nếu ứng dụng bắt buộc doc là object, cần thêm constraint phù hợp, chẳng hạn `CHECK (jsonb_typeof(doc) = 'object')`.

## 18. jsonb_typeof giúp kiểm tra kiểu

Hàm `jsonb_typeof(jsonb)` trả tên kiểu JSON:

~~~sql
SELECT
    jsonb_typeof('{"a":1}'::jsonb) AS object_type,
    jsonb_typeof('[1,2]'::jsonb) AS array_type,
    jsonb_typeof('"hello"'::jsonb) AS string_type,
    jsonb_typeof('42'::jsonb) AS number_type,
    jsonb_typeof('true'::jsonb) AS boolean_type,
    jsonb_typeof('null'::jsonb) AS json_null_type;
~~~

Các tên tương ứng:

~~~text
object, array, string, number, boolean, null
~~~

### 18.1. SQL NULL ở tham số

~~~sql
SELECT jsonb_typeof(NULL::jsonb) AS sql_null_type;
~~~

Kết quả SQL NULL (không phải chuỗi `'null'`).

### 18.2. Kiểm tra price là JSON number

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku,
    jsonb_typeof(doc -> 'price') AS price_type
FROM json_lab.products
ORDER BY product_id;
~~~

Trong lab, `CB-08` có `price_type='string'`, còn đa số hàng khác là `'number'`.

### 18.3. CHECK bảo vệ kiểu

Với hệ thống yêu cầu `price` là số, có thể dùng CHECK phù hợp:

~~~sql
CREATE TABLE json_lab.validated_docs (
    id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    CONSTRAINT doc_is_object
      CHECK (jsonb_typeof(doc) = 'object'),
    CONSTRAINT doc_has_numeric_price
      CHECK (
        doc ? 'price'
        AND jsonb_typeof(doc -> 'price') = 'number'
      )
);
~~~

Giúp phát hiện dữ liệu nhập không đúng kiểu sớm. Nếu cần constraint phức tạp hơn, có thể kết hợp schema validation phía ứng dụng với constraints ở database.

## 19. Toán tử bằng = trên JSONB

JSONB hỗ trợ equality theo **giá trị cấu trúc**, không đòi chuỗi JSON gốc giống hệt.

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
      = '{"b":2,"a":1}'::jsonb
      AS same_object_different_key_order;
~~~

Kết quả `true`. Thứ tự viết các key trong object không làm hai JSONB khác nhau.

### 19.1. Equality khác containment

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
      = '{"a":1}'::jsonb
      AS same_value,
    '{"a":1,"b":2}'::jsonb
      @> '{"a":1}'::jsonb
      AS contains;
~~~

`same_value=false` nhưng `contains=true`.

### 19.2. Array equality tôn trọng thứ tự

~~~sql
SELECT
    '["tech","sale"]'::jsonb
      = '["sale","tech"]'::jsonb
      AS equal_arrays,
    '["tech","sale"]'::jsonb
      @> '["sale","tech"]'::jsonb
      AS containing_arrays;
~~~

Kết quả `false` và `true`.

### 19.3. Array equality tôn trọng số lần xuất hiện

~~~sql
SELECT
    '["sale"]'::jsonb
      = '["sale","sale"]'::jsonb
      AS equality_with_duplicates,
    '["sale"]'::jsonb
      @> '["sale","sale"]'::jsonb
      AS containment_with_duplicates;
~~~

Kết quả `false` và `true`. **Không dùng `@>` thay cho `=` nếu cần đối chiếu chính xác array.**

### 19.4. JSONB numeric normalization

~~~sql
SELECT
    '{"qty":1}'::jsonb
      = '{"qty":1.0}'::jsonb
      AS numeric_value_equal;
~~~

Trong ngữ nghĩa so sánh JSONB number, `1` và `1.0` có thể được xem là **cùng giá trị số**. Điều này khác với yêu cầu so sánh nguyên bản từng byte JSON đầu vào.

### 19.5. JSONB string luôn khác JSONB number

~~~sql
SELECT
    '"1"'::jsonb = '1'::jsonb AS string_equals_number;
~~~

Kết quả `false`. Không mặc định một chuỗi số bằng giá trị số JSON.

## 20. Toán tử khác <> và NULL-aware comparison

~~~sql
SELECT
    '{"a":1}'::jsonb
      <> '{"a":2}'::jsonb
      AS different_values;
~~~

Kết quả `true`.

### 20.1. SQL NULL làm so sánh thường thành unknown

~~~sql
SELECT
    NULL::jsonb = '{"a":1}'::jsonb
      AS normal_equal,
    NULL::jsonb <> '{"a":1}'::jsonb
      AS normal_not_equal;
~~~

Cả hai kết quả là **SQL NULL/unknown**, không phải false/true.

### 20.2. IS DISTINCT FROM để so sánh null-safe

~~~sql
SELECT
    NULL::jsonb IS DISTINCT FROM '{"a":1}'::jsonb
      AS null_differs_from_object,
    NULL::jsonb IS NOT DISTINCT FROM NULL::jsonb
      AS both_sql_null;
~~~

Đây là những phép so sánh SQL xử lý SQL NULL có chủ đích.

### 20.3. JSON null không bằng SQL NULL

~~~sql
SELECT
    'null'::jsonb IS DISTINCT FROM NULL::jsonb
      AS json_null_differs_from_sql_null;
~~~

Kết quả `true`.

### 20.4. Khi nào dùng =

Dùng equality khi muốn kiểm tra **toàn bộ giá trị JSONB**:

~~~sql
WHERE doc -> 'active' = 'true'::jsonb
~~~

Nhưng nếu chỉ cần một trường trong object rất lớn, biểu thức scalar hoặc containment:

~~~sql
WHERE doc @> '{"active":true}'::jsonb
~~~

có thể phù hợp hơn cho việc dùng **GIN index trên toàn doc**.

## 21. Các toán tử thứ tự <, <=, >, >=

PostgreSQL cung cấp **B-tree comparison semantics** cho `jsonb`, nên có thể so sánh:

~~~sql
SELECT
    '2'::jsonb < '10'::jsonb AS two_lt_ten,
    '"2"'::jsonb < '"10"'::jsonb AS text_two_lt_ten;
~~~

Với JSONB number, `2 < 10` là `true`. Với JSONB strings, so sánh chuỗi có quy tắc khác so với số; không coi `"2"` và `"10"` là số.

### 21.1. Thứ tự giữa các kiểu JSONB

Theo quy tắc thứ tự B-tree của JSONB, nhóm kiểu có thứ tự ưu tiên tổng quát:

~~~text
Object > Array > Boolean > Number > String > JSON null
~~~

Trong cùng một nhóm, PostgreSQL có các quy tắc so sánh tiếp theo:

- Number so sánh như số.
- String theo ngữ nghĩa so sánh chuỗi thích hợp.
- Boolean theo giá trị boolean.
- Array theo cấu trúc, loại phần tử và thứ tự.
- Object theo cấu trúc key/value được chuẩn hóa.

### 21.2. Không sử dụng thứ tự kiểu JSONB làm thứ tự nghiệp vụ

~~~sql
SELECT product_id, doc -> 'price' AS price
FROM json_lab.products
ORDER BY doc -> 'price';
~~~

Query đang sắp theo **JSONB values**, không phải một cột `numeric` có kiểu đồng nhất. Nếu các hàng trộn JSON number và JSON string, thứ tự giữa các loại sẽ không giống thứ tự giá thực.

### 21.3. So sánh giá trị cùng kiểu

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND (doc -> 'price') > '50'::jsonb
ORDER BY product_id;
~~~

Ở đây cả giá trị `price` hợp lệ của tài liệu và RHS đều là JSON numbers. Điều kiện loại hàng có JSON string price.

### 21.4. Không bỏ kiểm tra kiểu khi dữ liệu dị thể

~~~sql
WHERE (doc -> 'price') > '50'::jsonb
~~~

có thể dẫn đến kết quả khó hiểu nếu `price` là chuỗi, boolean, object hoặc array, vì so sánh JSONB giữa các **loại JSON khác nhau vẫn có thứ tự**.

Đối với tiền và số lượng, một cột `numeric` có constraint thường rõ ràng và dễ tối ưu hơn nếu trường đó là nghiệp vụ cốt lõi.

## 22. Tránh so sánh số theo text

~~~sql
SELECT
    '100'::text > '20'::text AS lexical_comparison,
    100::numeric > 20::numeric AS numeric_comparison;
~~~

So sánh text có thể cho thứ tự từ điển, không phải thứ tự số.

### 22.1. Khi lấy ->> nhận text

~~~sql
SELECT
    product_id,
    doc ->> 'price' AS text_price
FROM json_lab.products
ORDER BY doc ->> 'price';
~~~

`ORDER BY` này sắp theo chuỗi. Không dùng làm báo cáo giá tiền chính xác khi dữ liệu có nhiều chữ số.

### 22.2. Một cách an toàn khi chỉ nhận JSON number

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku,
    CASE
      WHEN jsonb_typeof(doc -> 'price') = 'number'
      THEN (doc ->> 'price')::numeric
      ELSE NULL
    END AS numeric_price
FROM json_lab.products
ORDER BY numeric_price DESC NULLS LAST;
~~~

Biểu thức `CASE` mô tả rõ nhánh chuyển kiểu. Không tự đưa string bất kỳ vào phép cast numeric mà chưa có quy tắc kiểm soát đầu vào.

### 22.3. Dùng một kiểu dữ liệu ổn định hơn

Đối với ứng dụng thật, nên cân nhắc:

~~~sql
CREATE TABLE json_lab.stock_items (
    item_id bigint PRIMARY KEY,
    price numeric(12,2) NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

Giá tiền được PostgreSQL đảm bảo là numeric, còn thuộc tính linh hoạt ở JSONB. Điều này tránh những so sánh dị thể và hỗ trợ index/statistics hiệu quả hơn.

## 23. Tập hợp, GROUP BY và DISTINCT với JSONB

Vì JSONB có ngữ nghĩa equality, có thể dùng:

~~~sql
SELECT
    doc -> 'active' AS active_jsonb,
    COUNT(*) AS n
FROM json_lab.products
GROUP BY doc -> 'active'
ORDER BY active_jsonb;
~~~

### 23.1. GROUP BY cấu trúc

~~~sql
SELECT
    doc -> 'vendor' AS vendor,
    COUNT(*) AS n
FROM json_lab.products
GROUP BY doc -> 'vendor';
~~~

Hai object vendor bằng nhau theo JSONB equality được gom chung, không phụ thuộc thứ tự key trong JSON text đầu vào.

### 23.2. COUNT(DISTINCT ...)

~~~sql
SELECT
    COUNT(DISTINCT doc -> 'category') AS categories
FROM json_lab.products;
~~~

Đếm các giá trị category phân biệt theo biểu thức JSONB.

### 23.3. SQL NULL và GROUP BY

Khi đường dẫn thiếu, `doc -> 'vendor'` trả SQL NULL, nên các hàng thiếu vendor có thể được gom vào nhóm SQL NULL. Tài liệu có `vendor: null` sẽ là **JSONB null**, có thể tạo nhóm khác với SQL NULL.

Nếu yêu cầu nghiệp vụ phân biệt “thiếu key” với “key null”, hãy giữ thông tin `doc ? 'vendor'` trong biểu thức nhóm hoặc điều kiện.

## 24. JSONPath khi điều kiện sâu hơn containment

PostgreSQL hỗ trợ **SQL/JSON path** để chọn item và kiểm tra điều kiện trên các phần tử lồng nhau. Hai toán tử quan trọng với `jsonb`:

- `@?`: hỏi có item nào thỏa đường dẫn/path filter hay không.
- `@@`: đánh giá một JSONPath predicate, nhận kết quả boolean phù hợp (có thể là SQL NULL nếu biểu thức path không trả boolean như mong đợi).

### 24.1. JSONPath existence

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @? '$.tags[*] ? (@ == "sale")'
ORDER BY product_id;
~~~

Ý nghĩa:

1. `$.tags` lấy tags từ root.
2. `[*]` duyệt các item trong array.
3. `? (@ == "sale")` giữ item bằng chuỗi `sale`.
4. `@?` trả true nếu tìm được ít nhất một item.

### 24.2. Filter trên object cùng cấp

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
ORDER BY product_id;
~~~

Với dữ liệu lab, tài liệu `PL-10` chứa một size có `units=5` và có thể thỏa điều kiện.

Điểm quan trọng: filter `@.units >= 5` áp lên **mỗi object size**, không vô tình trộn `units` của hai objects khác nhau.

### 24.3. Dùng @@ với predicate

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @@ '$.price > 50'
ORDER BY product_id;
~~~

`@@` dùng với một biểu thức JSONPath **predicate**. Khi dữ liệu dị thể như `"price":"20"`, cần xác định quy tắc kiểu của JSONPath và bảo đảm input hợp lệ; không coi mọi chuỗi số như JSON number.

### 24.4. @? và @@ không thể đổi chỗ máy móc

~~~sql
doc @? '$.tags[*] ? (@ == "sale")'
~~~

biểu thị “path có ít nhất một item khớp”.

~~~sql
doc @@ '$.active == true'
~~~

biểu thị “biểu thức predicate JSONPath đánh giá là true”.

JSONPath có các chế độ và quy tắc riêng với nhiều kết quả/missing fields. Không chỉ thay ký hiệu `@?` bằng `@@` mà giữ nguyên path, rồi giả định kết quả không đổi.

### 24.5. Một số lỗi được suppress

Các toán tử `@?` và `@@` xử lý một số lỗi cấu trúc/kiểu trong JSONPath theo ngữ nghĩa được tài liệu PostgreSQL mô tả, hữu ích với dữ liệu dị thể. Nhưng không nên dùng điều đó để thay thế schema validation quan trọng hoặc che giấu tất cả lỗi nhập liệu.

## 25. Khi nào @> đủ, khi nào cần JSONPath?

| Yêu cầu | Cách diễn đạt thường hợp lý |
| --- | --- |
| vendor.country = VN | `doc @> '{"vendor":{"country":"VN"}}'` |
| tags chứa sale | `doc @> '{"tags":["sale"]}'` |
| top-level key notes tồn tại | `doc ? 'notes'` |
| nested vendor có key country | `(doc -> 'vendor') ? 'country'` |
| có size với units >= 5 | `doc @? '$.attributes.sizes[*] ? (@.units >= 5)'` |
| so giá JSON number > 50 | JSONPath predicate hoặc biểu thức numeric có kiểm tra kiểu |
| toàn tài liệu đúng bằng cấu trúc X | `doc = X::jsonb` |

### 25.1. @> dễ đọc khi so khớp cấu trúc cụ thể

Nếu mọi điều kiện đều là “chứa cặp key/value này”, `@>` thường ngắn gọn, rõ ràng và có hỗ trợ GIN phù hợp.

### 25.2. JSONPath mạnh hơn nhưng cần thận trọng

JSONPath có thể biểu diễn điều kiện range, array filters, existence ở sâu, nhiều nhánh. Đổi lại:

- Cần học ngữ nghĩa path và kiểu.
- Không phải mọi JSONPath đều được chỉ mục hỗ trợ hiệu quả.
- Query phức tạp khó kiểm chứng hơn biểu thức containment đơn giản.

### 25.3. Dữ liệu quan hệ vẫn có thể là lựa chọn tốt hơn

Nếu bạn thường cần lọc `size.units >= 5` và join `size_id` sang bảng khác, tách các lines/sizes ra bảng quan hệ có khóa ngoại và index numeric có thể phù hợp hơn việc liên tục truy vấn array JSONB lớn.

## 26. GIN index cho JSONB

PostgreSQL có phương thức chỉ mục **GIN (Generalized Inverted Index)**, phù hợp khi một giá trị JSONB chứa nhiều thành phần có thể tìm kiếm.

~~~sql
CREATE INDEX idx_products_doc_gin
ON json_lab.products
USING gin (doc);
~~~

Với `jsonb` và GIN, opclass mặc định thường là `jsonb_ops`.

### 26.1. GIN giúp những toán tử nào?

GIN `jsonb_ops` hỗ trợ những toán tử thường dùng:

- `@>`.
- `?`, `?|`, `?&`.
- `@?`, `@@` trong những trường hợp JSONPath được hỗ trợ.

Không nên suy GIN có thể xử lý **mọi biểu thức liên quan tới JSONB** như phép bằng toàn tài liệu, mọi so sánh thứ tự hoặc chuyển kiểu text.

### 26.2. Truy vấn containment có thể dùng GIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"tags":["sale"]}'::jsonb;
~~~

Nếu planner thấy có lợi, kế hoạch có thể gồm `Bitmap Index Scan` trên GIN và `Bitmap Heap Scan` để lấy tuple.

### 26.3. Truy vấn existence có thể dùng GIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc ?& ARRAY['sku','price'];
~~~

GIN `jsonb_ops` có thể hỗ trợ operator `?&`.

### 26.4. Bảng nhỏ vẫn có thể Seq Scan

Chỉ có mười hàng, PostgreSQL thường có lý do chọn `Seq Scan` vì đọc hết bảng rẻ. **Plan không chọn index trên bảng nhỏ không chứng minh index bị sai.**

## 27. jsonb_ops và jsonb_path_ops

Hai GIN operator classes thường gặp:

~~~sql
-- Opclass mặc định, hỗ trợ tập toán tử rộng:
CREATE INDEX idx_products_doc_ops
ON json_lab.products
USING gin (doc jsonb_ops);

-- Opclass khác, tập toán tử hẹp hơn:
CREATE INDEX idx_products_doc_path
ON json_lab.products
USING gin (doc jsonb_path_ops);
~~~

### 27.1. Ma trận hỗ trợ quan trọng

| Toán tử được index hỗ trợ | GIN `jsonb_ops` | GIN `jsonb_path_ops` |
| --- | :---: | :---: |
| `@>` | Có | Có |
| `?` | Có | Không |
| `?|` | Có | Không |
| `?&` | Có | Không |
| `@?` | Có, tùy dạng path | Có, tùy dạng path |
| `@@` | Có, tùy dạng path | Có, tùy dạng path |
| JSONB equality `=` trên toàn doc | Không phải operator GIN strategy tương ứng | Không |
| JSONB thứ tự `<`/`>` | Không | Không |

### 27.2. Vì sao jsonb_path_ops có ích?

`jsonb_path_ops` dùng cách lập chỉ mục chuyên biệt cho các giá trị theo đường dẫn, thường có thể **gọn và chọn lọc hơn** đối với containment/path matching phù hợp.

Nhưng nó **không** có cùng khả năng top-level key existence như `jsonb_ops`.

### 27.3. Chọn theo workload

Nếu ứng dụng chủ yếu hỏi:

~~~sql
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb
~~~

thì cả hai có thể là ứng viên.

Nếu ứng dụng thường hỏi:

~~~sql
WHERE doc ? 'vendor'
WHERE doc ?| ARRAY['stock','notes']
~~~

thì `jsonb_ops` có tập hỗ trợ phù hợp hơn.

### 27.4. Điều kiện có object rỗng

Các cấu trúc như:

~~~sql
WHERE doc @> '{"attributes":{}}'::jsonb
~~~

cần đánh giá riêng. `jsonb_path_ops` không lập entry cho một số cấu trúc rỗng không có giá trị, nên truy vấn dạng này có thể kém hiệu quả dù index rất nhỏ.

### 27.5. Không duy trì tất cả index mà không có lý do

Trong bài, tạo nhiều index để minh họa. Trên production, mỗi index tăng:

- Dung lượng lưu trữ.
- Chi phí cập nhật/chèn/xóa.
- Bảo trì GIN và WAL.
- Dung lượng cache và thời gian xây lại index.

Chọn một bộ chỉ mục dựa trên **độ thường xuyên, độ chọn lọc, tốc độ ghi và số liệu EXPLAIN**.

## 28. GIN trên toàn doc khác GIN trên expression

Giả sử đã có:

~~~sql
CREATE INDEX idx_products_doc_gin
ON json_lab.products USING gin (doc);
~~~

Truy vấn:

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

trực tiếp áp `@>` lên cột `doc`, phù hợp hình dạng index toàn doc.

Nhưng:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

áp `?` lên **biểu thức `doc -> 'tags'`**, không phải trực tiếp lên cột `doc`. Planner không nhất thiết dùng GIN trên toàn doc để xử lý expression đó.

### 28.1. Expression GIN index

~~~sql
CREATE INDEX idx_products_tags_gin
ON json_lab.products
USING gin ((doc -> 'tags'));
~~~

Query tương ứng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE (doc -> 'tags') ? 'sale';
~~~

Đây là ví dụ quan trọng về việc **biểu thức được index phải phù hợp với toán hạng SQL đang truy vấn**.

### 28.2. Chọn giữa hai dạng truy vấn

Nếu chỉ cần tìm tags sale, có thể viết:

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

để dùng GIN toàn doc, hoặc:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

với index chuyên biệt trên tags.

Hai cách có thể trả cùng kết quả **khi schema bảo đảm tags luôn là array chuỗi**, nhưng không nên coi chúng tương đương với mọi JSON dị thể (tags thiếu, tags là object, kiểu giá trị khác).

### 28.3. Expression index tiết kiệm hay tăng chi phí?

Index chuyên biệt trên tags có thể nhỏ hơn index toàn doc nếu tags chỉ chiếm phần nhỏ của tài liệu. Nhưng nếu vẫn cần nhiều truy vấn trên vendor, attributes và các keys khác, duy trì nhiều expression indexes cũng có chi phí.

## 29. B-tree index cho equality và thứ tự

JSONB có B-tree comparison semantics, nên có thể tạo B-tree index:

~~~sql
CREATE INDEX idx_products_doc_btree
ON json_lab.products USING btree (doc);
~~~

### 29.1. Kiểm tra bằng toàn bộ tài liệu

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc = '{"sku":"ONLY","active":true}'::jsonb;
~~~

Về mặt toán tử, B-tree có thể hỗ trợ equality trên JSONB. Nhưng giá trị JSONB có thể lớn và thay đổi nhiều: **B-tree trên toàn tài liệu thường không phải lựa chọn đầu tiên** cho truy vấn thuộc tính riêng lẻ.

### 29.2. B-tree cho ORDER BY doc

~~~sql
SELECT product_id, doc
FROM json_lab.products
ORDER BY doc
LIMIT 5;
~~~

Câu SQL có nghĩa theo **thứ tự JSONB B-tree**, nhưng thứ tự đó thường không tương ứng với thứ tự tên hàng, giá tiền hoặc thời gian nghiệp vụ.

### 29.3. GIN không phục vụ sort như B-tree

GIN `jsonb_ops` không tự cung cấp thứ tự:

~~~sql
ORDER BY doc ->> 'sku'
~~~

Nếu workload thường sắp theo SKU, nên cân nhắc **cột riêng hoặc expression B-tree index** cho SKU.

### 29.4. Giới hạn kích thước key

Một tài liệu JSONB lớn có thể vượt các giới hạn kích thước entry của B-tree index, ngoài việc tăng dung lượng và overhead. Không tạo B-tree toàn doc chỉ vì kiểu JSONB hỗ trợ phép `=`.

## 30. B-tree expression index cho key văn bản

~~~sql
CREATE INDEX idx_products_sku
ON json_lab.products ((doc ->> 'sku'));
~~~

Sau đó:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc ->> 'sku' = 'KB-01';
~~~

### 30.1. Phép bằng text khác containment

~~~sql
WHERE doc ->> 'sku' = 'KB-01'
~~~

có thể được B-tree expression index trên `doc ->> 'sku'` hỗ trợ.

~~~sql
WHERE doc @> '{"sku":"KB-01"}'::jsonb
~~~

lại là phép containment có thể được GIN toàn doc hỗ trợ.

Hai truy vấn có thể khớp cùng một bản ghi với cấu trúc sạch, nhưng **access path** và behavior với dữ liệu dị thể khác nhau.

### 30.2. Chỉ mục cho nested scalar

~~~sql
CREATE INDEX idx_products_vendor_country
ON json_lab.products (
    (doc #>> '{vendor,country}')
);
~~~

Query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc #>> '{vendor,country}' = 'VN';
~~~

### 30.3. Một SQL có thể có nhiều access paths

Truy vấn lọc vendor country có thể dùng GIN containment toàn doc hoặc B-tree expression theo scalar. Cách nào nhanh hơn phụ thuộc dữ liệu, selectivity, output và index footprints.

## 31. Expression index numeric và dữ liệu không đồng nhất

Một số ứng dụng cần:

~~~sql
WHERE price_numeric > 50
ORDER BY price_numeric DESC
~~~

Nếu `price` được lưu trong JSONB, hãy kiểm soát kiểu.

### 31.1. Kiểu JSON number

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND (doc -> 'price') > '50'::jsonb
ORDER BY product_id;
~~~

Điều này sử dụng toán tử JSONB comparison khi hai phía là number. Nếu cần arithmetic hoặc sort giá tiền, giải pháp có kiểu `numeric` thường dễ bảo trì hơn.

### 31.2. Chuyển kiểu có bảo vệ

~~~sql
SELECT
    product_id,
    CASE
      WHEN jsonb_typeof(doc -> 'price') = 'number'
      THEN (doc ->> 'price')::numeric
      ELSE NULL
    END AS price_numeric
FROM json_lab.products
ORDER BY price_numeric DESC NULLS LAST;
~~~

### 31.3. Cột sinh hoặc cột quan hệ

Nếu giá được tìm và sort rất thường xuyên, cân nhắc đưa `price` ra cột numeric có ràng buộc; nếu giữ JSONB làm source, có thể dùng generated column/validation theo phiên bản và yêu cầu hàm bất biến.

Không coi GIN index JSONB là thay thế trực tiếp cho một B-tree range index trên số.

## 32. Partial index và điều kiện tồn tại

Giả sử chỉ 10% tài liệu có key `vendor` trong hệ thống thật, và các query thường xuyên đọc nhóm này:

~~~sql
CREATE INDEX idx_products_has_vendor
ON json_lab.products (created_at)
WHERE doc ? 'vendor';
~~~

Query:

~~~sql
SELECT product_id, created_at
FROM json_lab.products
WHERE doc ? 'vendor'
ORDER BY created_at DESC;
~~~

Có thể được planner cân nhắc sử dụng partial B-tree index nếu query chứng minh predicate và yêu cầu sort phù hợp.

### 32.1. Partial index không phải GIN

Index trên dùng B-tree key `created_at`, còn `doc ? 'vendor'` là **điều kiện lựa chọn những hàng được giữ trong index**.

### 32.2. Query phải hàm ý predicate

Nếu query không chứa điều kiện được planner chứng minh là `doc ? 'vendor'`, PostgreSQL không thể tùy tiện bỏ các hàng không nằm trong partial index.

### 32.3. Tránh nhiều partial indexes ít dùng

Mỗi index dù partial vẫn tiêu tốn storage/maintenance. Đừng tạo một partial index cho **mỗi key JSON** mà chưa có workload thật.

## 33. JSONPath và GIN: không phải mọi path đều được tối ưu

GIN `jsonb_ops` và `jsonb_path_ops` hỗ trợ các toán tử `@?`/`@@` trong các dạng JSONPath nhất định. Trong thực tế, PostgreSQL có thể trích một số mệnh đề so khớp cụ thể như:

~~~text
accessor_chain == constant
~~~

để xây search keys có thể dùng GIN.

### 33.1. Ví dụ equality có khả năng được index

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc @? '$.vendor.country ? (@ == "VN")';
~~~

Đây là dạng path có điều kiện bằng hằng số trên một đường dẫn rõ ràng; có thể được GIN hỗ trợ tùy opclass và plan.

### 33.2. So sánh range phức tạp

~~~sql
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
~~~

có thể không trích được search key hiệu quả tương tự equality. **Việc JSONPath có cú pháp hợp lệ không đảm bảo index sẽ giảm dữ liệu đọc**.

### 33.3. Các toán tử trong JSONPath khác SQL operators

Trong chuỗi JSONPath:

~~~text
$.price > 50
~~~

là biểu thức JSONPath, không phải SQL:

~~~sql
(doc -> 'price') > '50'::jsonb
~~~

Hai cơ chế có semantics, loại và khả năng dùng index khác nhau. Không thay qua lại chỉ vì cùng dấu `>`.

### 33.4. Kiểm tra plan thực tế

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc @? '$.tags[*] ? (@ == "sale")';
~~~

Tìm `Bitmap Index Scan`, `Index Cond`, `Recheck Cond`, `Filter` và `Buffers` nếu có. Trên 10 dòng, Seq Scan hoàn toàn bình thường.

## 34. Dùng EXPLAIN ANALYZE đúng cách

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb;
~~~

Những trường cần đọc:

| Trường | Ý nghĩa vận hành |
| --- | --- |
| `Seq Scan` | Đọc tuần tự; thường hợp lý cho bảng nhỏ/tỷ lệ khớp lớn |
| `Bitmap Index Scan` | Dùng index tìm những tuple locations phù hợp |
| `Bitmap Heap Scan` | Truy cập các hàng heap từ bitmap |
| `Index Cond` | Điều kiện do access path áp dụng |
| `Recheck Cond` | Điều kiện cần kiểm tra lại theo kế hoạch/index |
| `Filter` | Điều kiện kiểm tra thêm trên hàng |
| `Rows Removed by Filter` | Những hàng đã lọc bỏ tại node |
| `actual rows`, `loops` | Số hàng thực tế trung bình mỗi lượt và số lượt node |
| `Buffers: shared hit/read` | Hoạt động trên blocks/buffers |
| `Planning Time`/`Execution Time` | Thời gian lập và thực thi theo instrumentation |

### 34.1. Tại sao có Recheck Cond?

Một số kiểu GIN/bitmap access cần xác nhận lại các predicate cho những tuple ứng viên, tùy toán tử và độ chính xác bitmap. Không suy GIN “không hoạt động” chỉ vì có `Recheck Cond`.

### 34.2. Buffers không phải số hàng

`shared hit=25` không có nghĩa PostgreSQL đọc đúng 25 sản phẩm. Một block chứa nhiều tuple; index và heap có các truy cập khác nhau.

### 34.3. Execution Time không phải API latency

`EXPLAIN ANALYZE` đo trên server với instrumentation overhead; ứng dụng còn network, driver decode, JSON serialization và xử lý kết quả.

### 34.4. Không đo một lần rồi quyết định

Cần nhiều lần thử trên dữ liệu gần production. Cache, số lượng tài liệu, độ sâu JSON và tỷ lệ key tồn tại ảnh hưởng mạnh tới lợi ích GIN.

## 35. Sinh thêm dữ liệu để quan sát index

Lab 10 hàng quá nhỏ để kết luận về hiệu năng. Nếu muốn thử thêm **20.000 tài liệu giả**, chỉ chạy trong database lab:

~~~sql
INSERT INTO json_lab.products (
    product_id, doc, created_at
)
SELECT
    g + 1000,
    jsonb_build_object(
      'sku', 'AUTO-' || lpad(g::text, 6, '0'),
      'active', g % 5 <> 0,
      'price', 10 + (g % 1000),
      'tags',
        CASE
          WHEN g % 10 = 0
          THEN jsonb_build_array('tech','sale')
          ELSE jsonb_build_array('tech')
        END,
      'vendor', jsonb_build_object(
        'country',
        CASE
          WHEN g % 20 = 0 THEN 'VN'
          ELSE 'US'
        END,
        'name', 'auto-vendor'
      )
    ),
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
       + g * INTERVAL '1 second'
FROM generate_series(1, 20000) AS s(g);

ANALYZE json_lab.products;
~~~

### 35.1. Tỷ lệ dữ liệu được chọn có ý nghĩa

Với dữ liệu sinh:

- Khoảng 10% có tag `sale`.
- Khoảng 5% có `vendor.country = VN`.
- Hầu hết có key `vendor`.

GIN có thể hữu ích hơn khi truy vấn một thuộc tính ít xuất hiện so với thuộc tính có mặt ở gần như mọi hàng.

### 35.2. Dữ liệu giả có hạn chế

Distribution có quy luật và ít cấu trúc đặc biệt. Production có thể có:

- Tài liệu rất lớn với hàng trăm keys.
- Key hiếm, key phổ biến, nested arrays.
- Cập nhật thường xuyên.
- Giá trị nhiều kiểu do nguồn không đồng nhất.

Đo trên dữ liệu thật hoặc dữ liệu đại diện trước khi quyết định giữ index.

### 35.3. So sánh opclasses

Nếu workload gồm containment và key existence, có thể:

1. Đo baseline với tập index hiện có.
2. Đo trong lab với GIN `jsonb_ops`.
3. Đo trong lab với `jsonb_path_ops` cho containment.
4. So sánh query key existence (không được `path_ops` hỗ trợ).
5. Cân nhắc dung lượng index, tốc độ ghi và cache.

Đừng chỉ đo một query `@>` nhanh để kết luận `jsonb_path_ops` tốt hơn cho toàn bộ hệ thống.

## 36. Chọn toán tử theo yêu cầu nghiệp vụ

### 36.1. Có thông tin vendor không?

~~~sql
WHERE doc ? 'vendor'
~~~

Không cần biết vendor nào.

### 36.2. Vendor có quốc gia VN?

~~~sql
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb
~~~

Hoặc so scalar:

~~~sql
WHERE doc #>> '{vendor,country}' = 'VN'
~~~

### 36.3. Có tag sale?

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

Hoặc:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

### 36.4. Có một trong hai key?

~~~sql
WHERE doc ?| ARRAY['notes','vendor']
~~~

### 36.5. Có tất cả key bắt buộc?

~~~sql
WHERE doc ?& ARRAY['sku','active','price']
~~~

**Điều này mới kiểm tra key tồn tại**, không chứng minh kiểu/giá trị của từng key đúng. Nếu cần schema validation, thêm `CHECK`/JSON schema validation phù hợp.

### 36.6. Giá là numeric và lớn hơn 50?

~~~sql
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND (doc -> 'price') > '50'::jsonb
~~~

Khi hệ thống yêu cầu arithmetic chính xác, cột numeric và validation ở ingestion thường là thiết kế an toàn hơn.

### 36.7. Có phần tử sizes thỏa units >= 5?

~~~sql
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
~~~

Đừng tách điều kiện qua hai object array khác nhau nếu nghiệp vụ yêu cầu cùng một phần tử đáp ứng.

## 37. So sánh @>, ?, = trong một ví dụ

Tài liệu:

~~~json
{"a":1,"b":2}
~~~

| Biểu thức | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `doc ? 'a'` | true | Có key a |
| `doc ? 'c'` | false | Không có key c |
| `doc @> '{"a":1}'` | true | Có cặp a=1 |
| `doc @> '{"a":3}'` | false | a có nhưng giá trị khác |
| `doc = '{"a":1}'` | false | Toàn object có thêm b |
| `doc = '{"b":2,"a":1}'` | true | Object bằng nhau, không xét thứ tự key |
| `doc <@ '{"a":1,"b":2,"c":3}'` | true | doc là tập con cấu trúc |

### 37.1. Chọn đúng logic trước khi tối ưu

Không thay `doc ? 'a'` thành `doc @> '{"a":null}'` vì toán tử thứ hai chỉ chọn key a **có JSON null**.

Không thay `doc = X` thành `doc @> X` nếu nghiệp vụ đòi **tài liệu không có key dư**.

## 38. Vấn đề kiểu dữ liệu và validation

JSONB linh hoạt cũng có nghĩa cùng key có thể mang kiểu khác:

~~~json
{"price":20}
{"price":"20"}
{"price":null}
{"price":{"amount":20}}
~~~

Một truy vấn:

~~~sql
WHERE doc ? 'price'
~~~

chọn **cả bốn** vì chỉ kiểm tra key tồn tại.

~~~sql
WHERE doc @> '{"price":20}'::jsonb
~~~

chỉ chọn giá trị JSON number khớp `20`, không chọn chuỗi `"20"`.

### 38.1. JSON schema ở tầng ingestion

Nên xác định:

- Field nào bắt buộc?
- Những kiểu JSON nào được phép?
- NULL có nghĩa gì? Có khác missing không?
- Array có thể rỗng không?
- Giá trị số có giới hạn gì?
- Object có cần không cho extra keys không?

### 38.2. CHECK đơn giản

~~~sql
CREATE TABLE json_lab.events_checked (
    event_id bigint PRIMARY KEY,
    payload jsonb NOT NULL,
    CHECK (jsonb_typeof(payload) = 'object'),
    CHECK (payload ?& ARRAY['type','version']),
    CHECK (jsonb_typeof(payload -> 'version') = 'number')
);
~~~

Ví dụ này chỉ kiểm tra một phần schema. Một hàng có `type` là JSON null vẫn có key `type` và có thể vượt qua CHECK thứ hai nếu không có ràng buộc bổ sung.

### 38.3. JSONB không thay thế foreign key

Nếu:

~~~json
{"customer_id":1234}
~~~

được lưu bên trong JSONB, PostgreSQL **không tự kiểm tra** rằng customer 1234 tồn tại trong bảng `customers` như một `FOREIGN KEY` trên cột quan hệ.

Nếu tính toàn vẹn tham chiếu là quan trọng, nên giữ foreign key ở cột có kiểu rõ ràng hoặc thiết kế một cơ chế enforce khác thực sự an toàn.

## 39. Parameterized queries và JSONB

Ứng dụng nên bind parameters thay vì ghép chuỗi JSON vào SQL.

Ví dụ với prepared statement:

~~~sql
PREPARE find_matching_docs(jsonb) AS
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> $1;

EXECUTE find_matching_docs(
    '{"vendor":{"country":"VN"}}'::jsonb
);
~~~

### 39.1. Bind đúng kiểu jsonb

Khi driver nhận input JSON dạng string, cần đảm bảo PostgreSQL hiểu parameter là `jsonb` cho toán tử `@>`. Trong nhiều driver có API riêng để bind JSONB hoặc SQL có thể dùng cast parameter đúng chỗ.

### 39.2. Không tự tạo SQL từ key không đáng tin

Đừng chắp:

~~~text
"... WHERE doc ? '" + userInput + "'"
~~~

vì có thể tạo SQL injection. Sử dụng bind variables với query cố định và validation cho đường dẫn/key của ứng dụng.

### 39.3. Generic plan và selectivity

Prepared statement có thể dùng generic hoặc custom plans tùy tình huống. Nếu một predicate JSONB rất hiếm còn predicate khác rất phổ biến, một plan chung có thể không tối ưu cho mọi JSONB parameter. Kiểm tra workload và plan thực tế thay vì bỏ parameterization.

### 39.4. JSONPath nhận từ người dùng

Nếu cho phép người dùng gửi JSONPath tùy ý, cần giới hạn phạm vi, chi phí và các đường dẫn được phép. Parameterization ngăn SQL injection nhưng **không tự ngăn truy vấn tốn CPU hay quét tài liệu rất lớn**.

## 40. Những lỗi phổ biến

### Lỗi 1. Nghĩ @> chỉ kiểm tra có key

`@> '{"k":1}'` kiểm tra cả giá trị `1`; `? 'k'` mới kiểm tra sự tồn tại của key.

### Lỗi 2. Nghĩ ? đi xuyên mọi cấp JSON

`doc ? 'country'` không tìm country nằm sâu dưới vendor. Dùng `(doc->'vendor') ? 'country'` hoặc containment theo cấu trúc.

### Lỗi 3. Dùng doc ? 'sale' để tìm tag

`sale` nằm trong array `tags`, không phải top-level key. Dùng `(doc->'tags') ? 'sale'` hoặc `@> '{"tags":["sale"]}'`.

### Lỗi 4. Nghĩ ? tìm JSON number trong array

`'[1,2]'::jsonb ? '2'` kiểm tra chuỗi `"2"`, không phải number `2`. Dùng containment JSON number đúng kiểu.

### Lỗi 5. Nhầm ?| và ?&

`?|` cần **ít nhất một**, `?&` cần **tất cả**.

### Lỗi 6. Dùng JSON array thay text[] với ?|/?&

RHS của hai operator là PostgreSQL `text[]`, chẳng hạn `ARRAY['a','b']`.

### Lỗi 7. Coi thứ tự array có ảnh hưởng containment

`["a","b"] @> ["b","a"]` vẫn đúng, trong khi equality của hai array khác thứ tự là sai.

### Lỗi 8. Đếm phần tử trùng với @>

JSONB containment không diễn đạt multiplicity của array theo cách một multiset đầy đủ. Nếu cần “hai lần sale”, phải thiết kế cách đếm phần tử thực.

### Lỗi 9. So object lồng bằng một object cấp ngoài

`{"vendor":{"country":"VN"}} @> {"country":"VN"}` sai. RHS phải phản ánh đường dẫn lồng.

### Lỗi 10. Nhầm key thiếu với JSON null

`doc ? 'notes'` true khi notes là JSON null; còn thiếu key cho false.

### Lỗi 11. Dùng ->> IS NULL để phân biệt missing và JSON null

`->>` có thể trả SQL NULL trong cả hai trường hợp. Kết hợp `?` hoặc `->` khi cần phân biệt.

### Lỗi 12. Nghĩ NOT NULL cột jsonb cấm JSON null

`NOT NULL` cấm SQL NULL của cột; `'null'::jsonb` vẫn là một JSONB value hợp lệ.

### Lỗi 13. So chuỗi số với số

JSON string `"20"` khác JSON number `20`. Query giá phải kiểm tra kiểu hoặc dùng cột numeric.

### Lỗi 14. Dùng ORDER BY doc để sắp giá

JSONB B-tree ordering dựa trên kiểu/cấu trúc JSONB, không phải quy tắc giá tiền nghiệp vụ.

### Lỗi 15. Nghĩ GIN hỗ trợ JSONB = và ORDER BY

GIN `jsonb_ops` tập trung containment/existence/path operators, không thay B-tree equality/range/order index.

### Lỗi 16. Chọn jsonb_path_ops rồi dùng ?

`jsonb_path_ops` không index `?`, `?|`, `?&`. Nếu workload cần các toán tử ấy, cân nhắc `jsonb_ops`.

### Lỗi 17. Nghĩ expression ? dùng GIN toàn doc tự động

`(doc->'tags') ? 'sale'` áp lên expression. Index trên `doc` không nhất thiết phục vụ; cần biểu thức index tương ứng hoặc rewrite containment trên doc.

### Lỗi 18. Nghĩ mọi JSONPath @?/@@ được index

Chỉ một số dạng path có điều kiện phù hợp cho GIN search keys. Với range/path phức tạp, có thể vẫn scan nhiều.

### Lỗi 19. Tạo nhiều GIN indexes không có workload

Mỗi GIN tốn dung lượng, ghi, WAL và bảo trì. Chỉ giữ các index được chứng minh hữu ích.

### Lỗi 20. Đánh giá index từ bảng mười hàng

Seq Scan có thể rẻ nhất khi bảng rất nhỏ. Đo trên dữ liệu đủ đại diện.

### Lỗi 21. Dùng JSONB để thay mọi cột quan hệ

Thiếu constraints/FK/stats rõ ràng có thể làm dữ liệu kém tin cậy và query khó tối ưu.

### Lỗi 22. Ghép JSON từ input vào chuỗi SQL

Tạo SQL injection risk và lỗi quoting. Dùng parameter binding và kiểu `jsonb` đúng.

### Lỗi 23. Dùng @> thay = để kiểm tra tài liệu trùng chính xác

Containment cho phép nhiều key hoặc phần tử thừa. Equality mới kiểm tra cấu trúc giá trị bằng nhau.

### Lỗi 24. So sánh null bằng = NULL

`= NULL` trả unknown. Dùng `IS NULL` hoặc `IS DISTINCT FROM` cho SQL NULL, `'null'::jsonb` cho JSON null.

## 41. Bài tập thực hành

Các bài dùng schema `json_lab`. Với bài yêu cầu index, chỉ tạo trong database lab; trên production cần benchmark và quy trình DDL phù hợp.

### Bài 1. Phân biệt @> và =

Giải thích kết quả:

~~~sql
SELECT
  '{"a":1,"b":2}'::jsonb @> '{"a":1}'::jsonb,
  '{"a":1,"b":2}'::jsonb =  '{"a":1}'::jsonb;
~~~

### Bài 2. Vendor lồng nhau

Viết truy vấn tìm sản phẩm có `vendor.country='VN'` bằng toán tử chứa.

### Bài 3. Top-level key

Viết truy vấn tìm tài liệu có key `vendor` bất kể giá trị.

### Bài 4. Key bên trong vendor

Giải thích vì sao `doc ? 'country'` không tìm được country ở cấp vendor. Viết cách đúng.

### Bài 5. Tag sale

Viết hai cách tìm sản phẩm có tag sale: một cách dùng `@>`, một cách dùng `?` trên array con.

### Bài 6. Một trong hai tag

Viết điều kiện có tag `tech` **hoặc** `office` với `?|`.

### Bài 7. Cả hai tag

Viết điều kiện có tag `tech` **và** `sale` với `?&`.

### Bài 8. Key bắt buộc

Viết điều kiện JSON object có cả ba top-level keys `sku`, `price`, `active`.

### Bài 9. Kiểu RHS của ?|

Vì sao `ARRAY['sku','vendor']` khác `'["sku","vendor"]'::jsonb`? Loại nào dùng với `?|`?

### Bài 10. Array order

`'["a","b"]'::jsonb @> '["b","a"]'::jsonb` là true hay false? Còn dấu `=` thì sao?

### Bài 11. Array duplicate

`'["a"]'::jsonb @> '["a","a"]'::jsonb` có ý nghĩa gì về multiplicity?

### Bài 12. Primitive array

Giải thích kết quả `'[1,2,3]'::jsonb @> '2'::jsonb` và `'[1,2,3]'::jsonb ? '2'`.

### Bài 13. Key thiếu và JSON null

Viết query tìm tài liệu có notes là **JSON null**, phân biệt với key notes thiếu.

### Bài 14. SQL NULL

Vì sao `NULL::jsonb = 'null'::jsonb` không trả false mà trả SQL NULL?

### Bài 15. IS DISTINCT FROM

Viết biểu thức kiểm tra SQL NULL và JSON null là hai trạng thái khác nhau.

### Bài 16. Kiểu price

Viết query liệt kê những sản phẩm có price mang kiểu JSON string, không phải number.

### Bài 17. Lọc numeric price

Viết query tìm sản phẩm có JSON number price lớn hơn 50 và không nhận chuỗi `"20"`.

### Bài 18. ORDER BY giá

Tại sao `ORDER BY doc->>'price'` có thể trả thứ tự sai? Gợi ý viết lại.

### Bài 19. Equality object

Giải thích vì sao hai object có cùng key/value nhưng thứ tự key khác nhau vẫn bằng nhau dưới `jsonb =`.

### Bài 20. JSONPath tags

Viết JSONPath `@?` tìm tài liệu có tag sale.

### Bài 21. JSONPath array objects

Viết JSONPath tìm tài liệu có phần tử `attributes.sizes` với `units >= 5`.

### Bài 22. JSONPath predicate

Viết ví dụ dùng `@@` để kiểm tra JSONB price lớn hơn 50 và mô tả lưu ý về kiểu dữ liệu.

### Bài 23. GIN opclasses

Chỉ ra operator classes hỗ trợ `doc ? 'vendor'` và `doc @> '{"active":true}'`.

### Bài 24. GIN expression index

Tạo GIN index trên `doc -> 'tags'` để hỗ trợ `(doc->'tags') ? 'sale'`.

### Bài 25. B-tree expression index

Tạo B-tree expression index tìm chính xác `doc->>'sku' = 'KB-01'`.

### Bài 26. JSONB equality index

Kiểu index nào có thể hỗ trợ equality toàn tài liệu? Vì sao không tự khuyên dùng nó trên một cột chứa JSONB rất lớn?

### Bài 27. Partial index

Tạo partial index theo `created_at` chỉ chứa tài liệu có key vendor.

### Bài 28. EXPLAIN

Viết câu `EXPLAIN (ANALYZE, BUFFERS)` cho containment vendor.country=VN, và nêu những trường cần xem.

### Bài 29. CHECK type

Viết CHECK đảm bảo `doc` là JSON object và có key price kiểu JSON number.

### Bài 30. Prepared statement

Viết prepared statement nhận một parameter `jsonb` và tìm các tài liệu chứa parameter ấy.

### Bài 31. So sánh <@

Viết hai cách biểu diễn “`{"a":1}` nằm trong `{"a":1,"b":2}`”.

### Bài 32. Dữ liệu quan hệ

Nếu ứng dụng liên tục lọc/sort/aggregate theo `price` và cần FK theo `vendor_id`, bạn chọn giữ tất cả ở JSONB hay tách cột có kiểu? Giải thích.

## 42. Lời giải tham khảo

### Bài 1. @> và =

`@>` trả `true` vì object trái chứa cặp `a=1`; `=` trả `false` vì bên trái có thêm key `b`.

### Bài 2. Vendor country

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb
ORDER BY product_id;
~~~

### Bài 3. Tồn tại vendor

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc ? 'vendor';
~~~

### Bài 4. Nested key

`?` không tự tìm xuyên cấp. Cách đúng:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE (doc -> 'vendor') ? 'country';
~~~

### Bài 5. Tag sale

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"tags":["sale"]}'::jsonb;

SELECT product_id
FROM json_lab.products
WHERE (doc -> 'tags') ? 'sale';
~~~

### Bài 6–7. ANY/ALL

~~~sql
-- Ít nhất một tag:
WHERE (doc -> 'tags') ?| ARRAY['tech','office']

-- Đầy đủ hai tags:
WHERE (doc -> 'tags') ?& ARRAY['tech','sale']
~~~

### Bài 8–9. Key list

~~~sql
WHERE doc ?& ARRAY['sku','price','active']
~~~

`?|`/`?&` nhận PostgreSQL `text[]`, không nhận JSONB array ở RHS.

### Bài 10–11. Array containment

`@>` với array đổi thứ tự trả true, còn equality trả false. Containment không đòi duplicate multiplicity; `["a"] @> ["a","a"]` trả true.

### Bài 12. Primitive và ?

`[1,2,3] @> 2` trả true với JSON number; `[1,2,3] ? '2'` không tìm thấy phần tử JSON string `"2"` nên false.

### Bài 13. Notes JSON null

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc ? 'notes'
  AND doc -> 'notes' = 'null'::jsonb;
~~~

Hoặc dùng containment:

~~~sql
WHERE doc @> '{"notes":null}'::jsonb
~~~

### Bài 14–15. SQL NULL

So sánh thường với SQL NULL cho unknown. Phân biệt bằng:

~~~sql
SELECT
    NULL::jsonb IS DISTINCT FROM 'null'::jsonb;
~~~

Kết quả true.

### Bài 16. Price là string

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'string';
~~~

Trong lab, kết quả có `CB-08`.

### Bài 17. Numeric price

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND doc -> 'price' > '50'::jsonb;
~~~

Điều kiện kiểu ngăn trường hợp chuỗi `"20"` tham gia so sánh số như một JSONB string.

### Bài 18. ORDER BY numeric

`doc->>'price'` là text nên sắp từ điển. Có thể dùng `CASE` để chỉ cast khi JSON number:

~~~sql
SELECT
    product_id,
    CASE
      WHEN jsonb_typeof(doc -> 'price') = 'number'
      THEN (doc ->> 'price')::numeric
    END AS numeric_price
FROM json_lab.products
ORDER BY numeric_price DESC NULLS LAST;
~~~

### Bài 19. Object equality

JSONB chuẩn hóa object key/value nên thứ tự key của JSON text không ảnh hưởng tới equality của object.

### Bài 20–21. JSONPath existence

~~~sql
WHERE doc @? '$.tags[*] ? (@ == "sale")'
~~~

~~~sql
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
~~~

### Bài 22. JSONPath predicate

~~~sql
WHERE doc @@ '$.price > 50'
~~~

Phải hiểu trường price có thể là number, string, null hoặc thiếu, và xác minh semantics/plan. Không suy mọi JSON string số sẽ được tự cast.

### Bài 23. GIN opclass

`jsonb_ops` hỗ trợ `?` và `@>`; `jsonb_path_ops` hỗ trợ `@>` nhưng không hỗ trợ `?`.

### Bài 24. Expression GIN

~~~sql
CREATE INDEX idx_products_tags_answer
ON json_lab.products
USING gin ((doc -> 'tags'));
~~~

### Bài 25. Expression B-tree

~~~sql
CREATE INDEX idx_products_sku_answer
ON json_lab.products ((doc ->> 'sku'));
~~~

### Bài 26. Equality toàn tài liệu

B-tree có thể hỗ trợ `doc = value::jsonb`, nhưng index key lớn, JSONB biến động nhiều và mục tiêu thường là tìm một field. Không mặc định xây B-tree toàn document.

### Bài 27. Partial B-tree

~~~sql
CREATE INDEX idx_products_vendor_recent_answer
ON json_lab.products (created_at)
WHERE doc ? 'vendor';
~~~

### Bài 28. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb;
~~~

Đọc loại scan, `Index Cond`/`Recheck Cond`/`Filter`, `actual rows`, `loops`, `Buffers` và `Execution Time`.

### Bài 29. CHECK JSON structure

~~~sql
CREATE TABLE json_lab.checked_product_docs (
    id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (jsonb_typeof(doc) = 'object'),
    CHECK (
      doc ? 'price'
      AND jsonb_typeof(doc -> 'price') = 'number'
    )
);
~~~

### Bài 30. Prepared statement

~~~sql
PREPARE product_contains(jsonb) AS
SELECT product_id
FROM json_lab.products
WHERE doc @> $1;

EXECUTE product_contains('{"active":true}'::jsonb);
~~~

### Bài 31. Hai hướng containment

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb @> '{"a":1}'::jsonb,
    '{"a":1}'::jsonb <@ '{"a":1,"b":2}'::jsonb;
~~~

Cả hai trả true.

### Bài 32. Tách cột có kiểu

Nếu `price` thường được lọc/sort/tính tiền, nên dùng cột `numeric` có CHECK/precision thích hợp. Nếu `vendor_id` cần foreign key, nên dùng cột quan hệ có FK. JSONB giữ metadata linh hoạt không cần schema cố định. Điều này giúp tránh so sánh dị thể và cung cấp constraints/statistics/index rõ ràng.

## 43. Bảng tra cứu nhanh

| Câu hỏi | Toán tử / biểu thức |
| --- | --- |
| JSONB trái chứa JSONB phải? | `left @> right` |
| JSONB trái nằm trong JSONB phải? | `left <@ right` |
| Có top-level key sku? | `doc ? 'sku'` |
| Có ít nhất một trong hai key? | `doc ?| ARRAY['a','b']` |
| Có cả hai key? | `doc ?& ARRAY['a','b']` |
| Có tag sale? | `doc @> '{"tags":["sale"]}'::jsonb` |
| Có tag sale theo array child? | `(doc->'tags') ? 'sale'` |
| vendor.country = VN? | `doc @> '{"vendor":{"country":"VN"}}'::jsonb` |
| country key trong vendor? | `(doc->'vendor') ? 'country'` |
| Có key notes bất kể value? | `doc ? 'notes'` |
| notes là JSON null? | `doc @> '{"notes":null}'::jsonb` |
| notes key thiếu? | `NOT (doc ? 'notes')` |
| JSONB values bằng nhau? | `doc1 = doc2` |
| JSONB values khác nhau? | `doc1 <> doc2` |
| So sánh xử lý SQL NULL? | `IS [NOT] DISTINCT FROM` |
| Kiểu JSON của price? | `jsonb_typeof(doc->'price')` |
| Duyệt array với JSONPath? | `doc @? '$.tags[*] ? (...)'` |
| Đánh giá JSONPath predicate? | `doc @@ '$.price > 50'` |
| GIN chứa và key existence? | `USING gin (doc jsonb_ops)` |
| GIN tập trung containment/path? | `USING gin (doc jsonb_path_ops)` |
| GIN trên tags expression? | `USING gin ((doc->'tags'))` |
| Tìm chính xác sku scalar? | B-tree trên `(doc->>'sku')` |
| So giá như numeric? | Cast có validation hoặc cột `numeric` |
| Kiểm tra index/plan? | `EXPLAIN (ANALYZE, BUFFERS)` |

## 44. Checklist trước khi đưa truy vấn JSONB vào ứng dụng

1. **Đang hỏi containment, key existence hay equality?** Đã chọn toán tử đúng ngữ nghĩa chưa?
2. **Key nằm cấp nào?** `?` có đang áp lên object/array cần kiểm tra không?
3. **Đường dẫn trong RHS của @> đã đầy đủ?** Có nhầm nested field thành top-level field?
4. **Array có cần thứ tự hoặc số lần lặp phần tử không?** `@>` không thay equality/multiplicity.
5. **Mọi literal có đúng kiểu JSON?** Number `20` khác string `"20"`; true khác `"true"`.
6. **Dữ liệu có thể thiếu key không?** Cần phân biệt missing/JSON null/SQL NULL?
7. **Có schema validation?** `?&` chỉ kiểm tra key, không chứng minh types/values hợp lệ.
8. **Có biến text thành số để ORDER BY không?** Cần quy tắc cast/check hoặc cột numeric.
9. **Query dùng @>, ?, ?|, ?&, @?, @@ hay =/< />?** Opclass đã hỗ trợ đúng operator chưa?
10. **GIN trên doc có khớp biểu thức query?** Hay cần GIN trên `doc->'tags'`?
11. **Đang dùng jsonb_path_ops nhưng cần ? không?** Nếu có, cần đổi lựa chọn index.
12. **JSONPath có được GIN trích search keys hiệu quả không?** Đã kiểm tra `EXPLAIN`?
13. **Có index trùng/ít dùng?** Tác động ghi, WAL và storage đã được cân nhắc?
14. **Bảng nhỏ nên Seq Scan có hợp lý?** Không ép index chỉ để plan đẹp.
15. **Đã đo trên phân bố dữ liệu đại diện?** Key hiếm, phổ biến, nested arrays, size JSON khác nhau.
16. **Truy vấn có được parameterize?** Không ghép input vào SQL trực tiếp.
17. **Có cần FK/constraint/aggregation mạnh trên field?** Nên tách cột quan hệ?
18. **Kết quả null và kiểu có được test ở ứng dụng?** Đặc biệt khi parse JSON từ nhiều nguồn.
19. **Đã đọc cả Index Cond/Filter/Recheck Cond/Buffers?** Không chỉ nhìn Execution Time.
20. **Tối ưu không thay đổi ý nghĩa?** So sánh ngữ nghĩa trước và sau khi rewrite.

## 45. Tổng kết

Toán tử JSONB trong PostgreSQL rất mạnh, nhưng chỉ phát huy hiệu quả khi hiểu **đúng câu hỏi đang hỏi**:

- **`@>` và `<@`** kiểm tra quan hệ chứa theo **cấu trúc**. Một object có thể có thêm keys so với yêu cầu; array containment không đòi cùng thứ tự và không đếm duplicates như một multiset, trong khi equality của array vẫn xét thứ tự và số phần tử.
- **`?`, `?|`, `?&`** kiểm tra sự tồn tại của key object hoặc phần tử chuỗi array **ở cấp đang xét**, tương ứng với một, bất kỳ hoặc tất cả các key trong danh sách. Chúng không tự tìm sâu vào object con.
- **`=`, `<>` và các toán tử thứ tự** so sánh giá trị JSONB theo ngữ nghĩa của PostgreSQL. JSONB number khác JSONB string; SQL NULL khác JSON null; thứ tự B-tree JSONB không phải thứ tự nghiệp vụ của giá tiền hoặc tên sản phẩm.
- **`@?` và `@@`** mở rộng khả năng kiểm tra với JSONPath, nhất là khi cần filter trong arrays/objects lồng nhau, nhưng không phải mọi path đều có chiến lược index hiệu quả.

Về tối ưu, GIN **`jsonb_ops`** hỗ trợ containment, key existence và một số JSONPath patterns; **`jsonb_path_ops`** tập trung containment/path matching, có thể gọn hơn nhưng không hỗ trợ `?`/`?|`/`?&`. B-tree và expression indexes phục vụ equality, scalar comparisons và `ORDER BY` khi cần.

Quy trình nên bắt đầu bằng câu hỏi **“Tôi cần key tồn tại, cấu trúc chứa giá trị này, hay toàn tài liệu bằng nhau?”**. Sau đó xác nhận đường dẫn, kiểu JSON, null semantics, viết điều kiện đúng và cuối cùng kiểm tra index bằng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện. Cách này tránh cả **lỗi kết quả** lẫn **tối ưu nhầm toán tử**.
