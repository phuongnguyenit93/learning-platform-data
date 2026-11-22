# JSONPath và truy vấn điều kiện trong tài liệu PostgreSQL

Khi một ứng dụng lưu đơn hàng, cấu hình, nhật ký sự kiện hoặc dữ liệu từ API bên ngoài dưới dạng `jsonb`, câu hỏi thường không còn là “đọc trường `status` như thế nào?”, mà là:

- Đơn hàng **có bất kỳ sản phẩm nào** có `sku` bằng `SKU-RED` không?
- Có **cùng một sản phẩm** vừa thuộc nhóm `sale`, vừa có số lượng từ 2 trở lên không?
- Khách hàng có thuộc nhóm VIP **và** giao hàng tới Hà Nội không?
- Trong một tài liệu có cấu trúc thay đổi giữa các phiên bản API, có trường `shipping.city` không?
- Làm sao gắn tham số từ Java mà không nối chuỗi thành biểu thức JSONPath nguy hiểm?
- Câu truy vấn JSONPath nào có cơ hội sử dụng **GIN index**?

PostgreSQL hỗ trợ kiểu `jsonpath` và các phép toán/hàm để duyệt, lọc và kiểm tra dữ liệu JSON. **JSONPath** là ngôn ngữ diễn đạt đường đi và điều kiện *bên trong tài liệu JSON*, không phải tên gọi khác của một câu SQL `WHERE`.

Bài học thuộc chương **JSON và mảng**, trình bày những cơ chế quan trọng:

1. Cấu trúc JSONPath: `$`, `@`, truy cập thuộc tính, mảng, wildcard và bộ lọc `? (...)`.
2. Phân biệt **toán tử `@?`** với **toán tử `@@`**; hiểu bẫy dùng biểu thức trả Boolean với `@?`.
3. Các hàm `jsonb_path_exists`, `jsonb_path_match`, `jsonb_path_query`, `jsonb_path_query_first` và `jsonb_path_query_array`.
4. Điều kiện ghép `&&`, `||`, `!`, so sánh số/chuỗi, regex và điều kiện trên cùng phần tử mảng.
5. Xử lý **trường thiếu, JSON `null`, SQL `NULL`, dữ liệu sai kiểu**, chế độ `lax`/`strict`.
6. Biến `$sku`/`$min_qty` trong JSONPath, tham số JDBC và các lựa chọn index.
7. Bài thực hành, cách đọc `EXPLAIN` và các lỗi thường gặp trong ứng dụng.

> **Phạm vi phiên bản:** Các toán tử/hàm JSONPath cơ bản được PostgreSQL hỗ trợ từ phiên bản 12. Từng tính năng SQL/JSON mới hơn có thể khác theo major version; luôn đối chiếu tài liệu của server bạn đang dùng.

## 1. Vì sao cần JSONPath khi đã có -> và ->>?

PostgreSQL có những toán tử truy cập JSON quen thuộc:

```sql
SELECT
    '{"customer":{"id":"C001"},"status":"paid"}'::jsonb
        -> 'customer' AS customer_json,
    '{"customer":{"id":"C001"},"status":"paid"}'::jsonb
        -> 'customer' ->> 'id' AS customer_id;
```

- `->` trả về một giá trị JSON/JSONB.
- `->>` trả về biểu diễn văn bản của giá trị được trích.
- `#>` và `#>>` truy cập theo mảng đường dẫn gồm nhiều thành phần.
- `jsonb_array_elements` có thể mở rộng một mảng JSON thành các hàng SQL.

Đó là công cụ rất tốt cho **truy cập đường dẫn cố định**. Nhưng nếu muốn hỏi “có ít nhất một phần tử trong mảng thỏa nhiều điều kiện cùng lúc?”, JSONPath thường diễn đạt mục tiêu rõ ràng hơn:

```sql
SELECT
    '{"items":[{"sku":"SKU-RED","qty":2},{"sku":"SKU-BLUE","qty":1}]}'::jsonb
      @? '$.items[*] ? (@.sku == "SKU-RED" && @.qty >= 2)'
    AS has_requested_item;
```

Kết quả là `true` vì có **một phần tử** trong `items` vừa có SKU mong muốn vừa có số lượng ít nhất 2.

JSONPath không thay thế toàn bộ SQL. SQL vẫn đảm nhận `JOIN`, `GROUP BY`, `ORDER BY`, window functions, transactions và thiết kế index; JSONPath giúp **mô tả điều kiện bên trong từng giá trị JSON**.

## 2. Bộ dữ liệu thực hành

Ví dụ dùng một schema riêng `jsonpath_lab` trên database thử nghiệm. Các câu `INSERT` chỉ nên chạy một lần sau khi tạo bảng thành công.

### 2.1. Tạo bảng chứa tài liệu jsonb

```sql
CREATE SCHEMA IF NOT EXISTS jsonpath_lab;

CREATE TABLE jsonpath_lab.orders (
    order_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    CONSTRAINT document_is_object
        CHECK (jsonb_typeof(document) = 'object')
);
```

Một cột `jsonb` chứa tài liệu có dạng:

```json
{
  "status": "paid",
  "customer": {
    "id": "C001",
    "vip": true,
    "email": "ana@example.test"
  },
  "shipping": {
    "city": "Hanoi",
    "country": "VN",
    "express": true
  },
  "items": [
    {"sku": "SKU-RED", "qty": 2, "unit_price": 120, "tags": ["sale", "new"]},
    {"sku": "SKU-BLUE", "qty": 1, "unit_price": 40, "tags": ["clearance"]}
  ],
  "total": 280,
  "coupons": ["WELCOME10"]
}
```

### 2.2. Thêm sáu tài liệu với cấu trúc đa dạng

```sql
INSERT INTO jsonpath_lab.orders (order_id, created_at, document)
VALUES
(
    1,
    TIMESTAMPTZ '2026-10-01 09:00:00+00',
    $json$
    {
      "status": "paid",
      "customer": {"id": "C001", "vip": true, "email": "ana@example.test"},
      "shipping": {"city": "Hanoi", "country": "VN", "express": true},
      "items": [
        {"sku": "SKU-RED", "qty": 2, "unit_price": 120, "tags": ["sale", "new"]},
        {"sku": "SKU-BLUE", "qty": 1, "unit_price": 40, "tags": ["clearance"]}
      ],
      "total": 280,
      "coupons": ["WELCOME10"]
    }
    $json$::jsonb
),
(
    2,
    TIMESTAMPTZ '2026-10-02 10:00:00+00',
    $json$
    {
      "status": "pending",
      "customer": {"id": "C002", "vip": false, "email": "binh@example.test"},
      "shipping": {"city": "Ho Chi Minh City", "country": "VN", "express": false},
      "items": [
        {"sku": "SKU-GREEN", "qty": 3, "unit_price": 80, "tags": ["new"]}
      ],
      "total": 240,
      "coupons": []
    }
    $json$::jsonb
),
(
    3,
    TIMESTAMPTZ '2026-10-03 11:00:00+00',
    $json$
    {
      "status": "paid",
      "customer": {"id": "C003", "vip": true, "email": "chi@example.test"},
      "shipping": {"city": "Da Nang", "country": "VN", "express": true},
      "items": [
        {"sku": "SKU-RED", "qty": 1, "unit_price": 120, "tags": ["sale"]},
        {"sku": "SKU-GOLD", "qty": 2, "unit_price": 200, "tags": ["premium"]}
      ],
      "total": 520,
      "coupons": ["VIP20"]
    }
    $json$::jsonb
),
(
    4,
    TIMESTAMPTZ '2026-10-04 12:00:00+00',
    $json$
    {
      "status": "cancelled",
      "customer": {"id": "C004", "vip": false},
      "shipping": null,
      "items": [],
      "total": 0
    }
    $json$::jsonb
),
(
    5,
    TIMESTAMPTZ '2026-10-05 13:00:00+00',
    $json$
    {
      "status": "paid",
      "customer": {"id": "C005", "vip": false},
      "shipping": {"city": "Hanoi", "country": "VN"},
      "items": [
        {"sku": "SKU-BLUE", "qty": "3", "unit_price": "40", "tags": ["sale"]}
      ],
      "total": "120"
    }
    $json$::jsonb
),
(
    6,
    TIMESTAMPTZ '2026-10-06 14:00:00+00',
    $json$
    {
      "status": "pending",
      "customer": {"id": "C006", "vip": null},
      "items": [
        {"sku": "SKU-BLACK", "qty": 1, "unit_price": 300, "tags": []}
      ],
      "total": 300
    }
    $json$::jsonb
);

ANALYZE jsonpath_lab.orders;
```

Những khác biệt là **có chủ đích**:

| Order | Đặc điểm dùng để thử |
| --- | --- |
| **1** | VIP, giao Hà Nội, SKU-RED qty 2, có tag `sale` |
| **2** | Đang xử lý, SKU-GREEN qty 3 |
| **3** | VIP, SKU-RED qty 1 và SKU-GOLD qty 2 |
| **4** | `shipping` là JSON `null`, mảng `items` rỗng |
| **5** | `qty`, `unit_price`, `total` được lưu thành **chuỗi**, không phải số |
| **6** | **Thiếu trường `shipping`**, `customer.vip` là JSON `null` |

Bản ghi số 5 rất quan trọng: `"3"` và `3` không phải cùng kiểu JSON. Không được ngầm coi dữ liệu JSON gửi từ bên ngoài luôn đúng schema.

### 2.3. Xem dữ liệu ở dạng dễ đọc

```sql
SELECT
    order_id,
    jsonb_pretty(document) AS pretty_document
FROM jsonpath_lab.orders
ORDER BY order_id;
```

`jsonb_pretty` trả text trình bày JSON dễ đọc. Nó hữu ích khi học/debug; ứng dụng thường nên xử lý kiểu JSONB trực tiếp thay vì parse văn bản đã pretty-print.

## 3. Cấu trúc nền tảng của JSONPath

Một biểu thức JSONPath có điểm khởi đầu và các bước duyệt:

```text
$               toàn bộ tài liệu gốc
$.customer      trường customer ở gốc
$.customer.id   trường id trong customer
$.items         mảng items
$.items[0]      phần tử đầu tiên (index từ 0)
$.items[*]      mọi phần tử trực tiếp của mảng
$.items[*].sku  trường sku của mọi phần tử
```

Những ký hiệu thường gặp:

| JSONPath | Ý nghĩa |
| --- | --- |
| `$` | Tài liệu JSON gốc |
| `@` | Mục JSON hiện tại trong biểu thức filter |
| `.key` | Truy cập trường đối tượng |
| `."special key"` | Trường có tên cần đặt trong dấu ngoặc kép |
| `[0]` | Phần tử mảng đầu tiên |
| `[*]` | Mọi phần tử của mảng |
| `[last]` | Phần tử cuối mảng theo cú pháp JSONPath |
| `.*` | Các giá trị của thành viên đối tượng ở cấp hiện tại |
| `.**` | Duyệt các mức lồng nhau theo khả năng path engine |
| `? (condition)` | Chỉ giữ những mục thỏa bộ lọc |
| `==`, `!=`, `>`, `>=`, `<`, `<=` | So sánh trong JSONPath |
| `&&`, `||`, `!` | Kết hợp/đảo điều kiện |

Chú ý: JSONPath dùng `==` để so sánh bằng, khác SQL vốn thường dùng `=`.

### 3.1. $ và @ không cùng ý nghĩa

Ví dụ:

```sql
SELECT jsonb_path_query_array(
    '{
       "items": [
         {"sku":"SKU-RED","qty":2},
         {"sku":"SKU-BLUE","qty":1}
       ]
     }'::jsonb,
    '$.items[*] ? (@.qty >= 2)'
) AS selected_items;
```

- `$` chỉ tài liệu gốc.
- `$.items[*]` tạo dãy các **object sản phẩm**.
- Filter được áp dụng lần lượt lên từng object.
- `@.qty` là `qty` của **chính object đang xét**.
- Chỉ object có `qty >= 2` được giữ.

Nếu dùng `$.items[*].qty` ở những vị trí không phù hợp, điều kiện có thể được đánh giá trên **toàn tập item**, không bảo đảm cùng một phần tử với SKU đang xét.

### 3.2. Trường chứa khoảng trắng hoặc ký tự đặc biệt

Khi key không thể viết thuận tiện dưới dạng `.identifier`, dùng JSONPath string member syntax:

```sql
SELECT jsonb_path_query_first(
    '{"delivery address":{"postal code":"100000"}}'::jsonb,
    '$."delivery address"."postal code"'
);
```

Dấu ngoặc kép là cú pháp **bên trong JSONPath**, trong khi dấu nháy đơn bao ngoài là cú pháp **SQL string literal**.

### 3.3. Mảng bắt đầu từ chỉ số 0

```sql
SELECT
    jsonb_path_query_first(
        '{"items":["A","B","C"]}'::jsonb,
        '$.items[0]'
    ) AS first_item,
    jsonb_path_query_first(
        '{"items":["A","B","C"]}'::jsonb,
        '$.items[last]'
    ) AS last_item;
```

Kỳ vọng JSON string `"A"` và `"C"`. JSONPath có cú pháp `last` dùng cho chỉ số cuối mảng; không tự dùng cú pháp SQL `array_length(...) - 1` trong path string.

## 4. Filter ? (...) — tìm phần tử thỏa điều kiện

Đây là dạng thực hành quan trọng nhất:

```text
$.items[*] ? (@.qty >= 2)
│         │ │
│         │ └─ điều kiện áp dụng cho phần tử hiện tại
│         └─── chọn lọc những phần tử đã duyệt
└───────────── bắt đầu từ mảng items
```

Truy vấn tìm order có ít nhất một sản phẩm số lượng từ 2:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.qty >= 2)'
ORDER BY order_id;
```

Với dữ liệu mẫu có giá trị số đúng kiểu, các order **1, 2 và 3** khớp. Bản ghi 5 có `qty` là JSON string nên **không được coi tự động như JSON number 3**.

### 4.1. Filter có thể áp dụng lên giá trị scalar

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.status ? (@ == "paid")'
ORDER BY order_id;
```

Ở đây `$.status` tạo giá trị JSON string, và `@` đại diện chính string đó. Kết quả mong đợi là order 1, 3, 5.

### 4.2. Filter trên object chứa nhiều trường

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.customer ? (@.vip == true)'
ORDER BY order_id;
```

Phần tử đang xét là object `customer`, do đó `@.vip` truy cập boolean `vip` của object ấy. Kết quả: order 1 và 3.

### 4.3. Có thể lọc trực tiếp một mảng JSON số

```sql
SELECT jsonb_path_query_array(
    '{"scores":[55,80,92,37]}'::jsonb,
    '$.scores[*] ? (@ >= 80)'
) AS high_scores;
```

Kỳ vọng: `[80, 92]`.

Không cần chuyển mảng thành bảng SQL nếu mục tiêu chỉ là lấy các giá trị thỏa điều kiện và trả JSON array.

## 5. Phân biệt @? và @@ — quan trọng nhất của bài

PostgreSQL có hai toán tử rất giống nhau về ký hiệu nhưng khác **ngữ nghĩa trả kết quả**.

| Toán tử | Phía trái | Phía phải | Câu hỏi |
| --- | --- | --- | --- |
| `@?` | `jsonb` | `jsonpath` | **Path trả về ít nhất một mục hay không?** |
| `@@` | `jsonb` | `jsonpath` dạng predicate | **Biểu thức kiểm tra trả về Boolean gì?** |

### 5.1. @? dùng với path trả các mục đã lọc

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")'
ORDER BY order_id;
```

Path duyệt các item rồi chỉ giữ item có SKU-RED. Toán tử `@?` trả true nếu còn **ít nhất một** item sau filter.

Kết quả: order 1 và 3.

### 5.2. @@ dùng với biểu thức kiểm tra Boolean

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @@ '$.customer.vip == true'
ORDER BY order_id;
```

Phía phải là một **predicate check expression**, có kết quả Boolean, chứ không phải đường dẫn trả về danh sách khách hàng.

Kết quả: order 1 và 3.

Cách viết khác với mục tiêu tương ứng:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @@ '$.items[*].sku == "SKU-RED"'
ORDER BY order_id;
```

Trong PostgreSQL, so sánh với chuỗi item từ mảng có thể kiểm tra xem có mục phù hợp theo semantics JSONPath. Kết quả mong đợi: order 1 và 3.

### 5.3. Bẫy: dùng predicate trả false bên trong @?

Đây là ví dụ **sai về ý định**:

```sql
SELECT
    '{"total":100}'::jsonb @? '$.total > 400'
        AS wrong_existence_test;
```

Biểu thức `$.total > 400` là **predicate check** có kết quả Boolean `false`. Tuy nhiên `@?` chỉ hỏi **path trả về mục nào không**. Predicate trả về một mục Boolean `false` cũng là **một mục**!

Vì vậy câu trên có thể trả **true**, trái với ý định “total lớn hơn 400”.

Hai cách **đúng**:

```sql
-- Cách 1: @@ kiểm tra chính Boolean predicate.
SELECT '{"total":100}'::jsonb @@ '$.total > 400'
       AS correct_predicate;
```

```sql
-- Cách 2: @? tìm root item thỏa filter.
SELECT '{"total":100}'::jsonb @? '$ ? (@.total > 400)'
       AS correct_filtered_existence;
```

**Quy tắc dễ nhớ:**

- `@? '$.items[*] ? (@.qty > 2)'` — đúng: path tạo các item **đã lọc**.
- `@@ '$.items[*].qty > 2'` — đúng: JSONPath là **Boolean predicate**.
- `@? '$.items[*].qty > 2'` — **sai ý định**: predicate có thể trả `false` nhưng `@?` vẫn chỉ thấy “một kết quả”.

### 5.4. @@ dùng với path trả item thay vì Boolean

Ngược lại, câu:

```sql
SELECT
    '{"items":[{"sku":"SKU-RED"}]}'::jsonb
        @@ '$.items[*].sku' AS wrong_boolean_test;
```

không phải cách hỏi “có SKU hay không”. `@@` cần kết quả predicate Boolean; nếu kết quả không phải một Boolean đơn lẻ, nó trả SQL `NULL`.

Đúng hơn:

```sql
SELECT
    '{"items":[{"sku":"SKU-RED"}]}'::jsonb
        @? '$.items[*].sku' AS has_sku_field;
```

Câu sau hỏi có ít nhất một item `sku` trong dãy path result.

## 6. Điều kiện trên CÙNG một phần tử mảng

Một trường hợp dễ sinh bug nghiệp vụ: cần tìm order có một sản phẩm **vừa** là SKU-RED **vừa** có số lượng ít nhất 2.

Cách đúng:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (
        @.sku == "SKU-RED"
        && @.qty >= 2
    )
'
ORDER BY order_id;
```

Bộ lọc đặt **sau `$.items[*]`**, nên hai biểu thức đều áp dụng cho **một object item hiện tại**.

Kết quả: **chỉ order 1**. Order 3 có SKU-RED nhưng qty chỉ 1; một item khác là SKU-GOLD qty 2.

### 6.1. Sai: hai điều kiện EXISTS độc lập

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")'
  AND document @? '$.items[*] ? (@.qty >= 2)'
ORDER BY order_id;
```

Hai toán tử `@?` này chỉ yêu cầu:

1. Tồn tại **một item nào đó** có SKU-RED.
2. Tồn tại **một item nào đó** có qty ≥ 2.

Chúng **không bắt buộc cùng một item**. Vì thế **order 3** cũng khớp: SKU-RED qty 1, nhưng SKU-GOLD qty 2.

Đây là lỗi tương tự một phép JOIN/EXISTS bị tách điều kiện tương quan không đúng.

### 6.2. Nhiều điều kiện ghép trong cùng filter

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (
        @.qty >= 2
        && @.unit_price >= 100
        && @.tags[*] == "sale"
    )
'
ORDER BY order_id;
```

Ý nghĩa: tồn tại một item có số lượng ≥ 2, giá đơn vị ≥ 100 và trong tags có `sale`. Với bộ dữ liệu mẫu, **order 1** khớp.

Điều kiện `@.tags[*] == "sale"` được đánh giá từ **mảng tags của chính item đang lọc**.

### 6.3. Kết hợp OR trong filter

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (
        @.sku == "SKU-GOLD" || @.sku == "SKU-BLACK"
    )
'
ORDER BY order_id;
```

Kết quả: order 3 và 6.

Dấu `||` và `&&` ở đây là **toán tử logic JSONPath** bên trong chuỗi path, không phải phép nối chuỗi SQL. Đọc kỹ dấu nháy đơn bên ngoài và dấu nháy kép bao giá trị JSON bên trong.

### 6.4. Đảo điều kiện bằng !

Có thể viết điều kiện phủ định trong filter:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (!(@.sku == "SKU-RED"))
'
ORDER BY order_id;
```

Nó tìm order có **ít nhất một item không phải SKU-RED**. Nó **không có nghĩa “không có bất kỳ SKU-RED nào”**.

Order 1 vẫn khớp vì còn SKU-BLUE, dù order này cũng chứa SKU-RED.

## 7. Kiểm tra “không có item nào” và “tất cả item đều”

Giả sử muốn tìm đơn **không có item SKU-RED**. Cần đặt phủ định **bên ngoài điều kiện tồn tại**:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE NOT (
    document @? '$.items[*] ? (@.sku == "SKU-RED")'
)
ORDER BY order_id;
```

Kết quả: order 2, 4, 5 và 6.

Câu này khác với `$.items[*] ? (!(@.sku == "SKU-RED"))` ở phần trước.

### 7.1. Mọi item có qty >= 1

Dùng phép biến đổi logic:

> Tất cả item thỏa P tương đương không tồn tại item vi phạm P.

Ví dụ:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE NOT (
    document @? '$.items[*] ? (@.qty < 1)'
)
ORDER BY order_id;
```

**Nhưng phải cẩn thận với dữ liệu sai kiểu hoặc thiếu trường.** Nếu `qty` là chuỗi hoặc field không tồn tại, điều kiện `@.qty < 1` có thể không trả true do error suppression/unknown. Khi đó phép phủ định đơn giản **không bảo đảm mọi item có qty số hợp lệ ≥ 1**.

Một thiết kế đáng tin cậy hơn cần xác thực schema đầu vào khi ghi dữ liệu hoặc kiểm tra kiểu/field trong logic phù hợp.

### 7.2. Mảng rỗng và tính đúng hiển nhiên

Order 4 có `items=[]`. Mệnh đề “không tồn tại item vi phạm P” là true với mảng rỗng.

Nếu nghiệp vụ yêu cầu **phải có ít nhất một sản phẩm** và mọi sản phẩm đạt điều kiện, cần thêm phép kiểm tra mảng không rỗng:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[0]'
  AND NOT (
      document @? '$.items[*] ? (@.qty < 1)'
  )
ORDER BY order_id;
```

Khi áp dụng trên dữ liệu nghiệp vụ thật, cũng cần xác thực `items` thực sự là array và `qty` đúng kiểu, tránh coi một giá trị scalar do lax wrapping là mảng hợp lệ.

## 8. Truy vấn trường ở cấp sâu và mảng lồng nhau

JSONPath mạnh ở các cấu trúc có nhiều tầng object và array.

Ví dụ đơn giản:

```sql
SELECT jsonb_path_query_array(
    '{
       "departments": [
         {
           "name": "engineering",
           "teams": [
             {"name":"backend","members":[{"name":"An"},{"name":"Binh"}]},
             {"name":"data","members":[{"name":"Chi"}]}
           ]
         }
       ]
     }'::jsonb,
    '$.departments[*].teams[*].members[*].name'
) AS member_names;
```

Kết quả JSON array gồm ba tên `"An"`, `"Binh"`, `"Chi"`.

### 8.1. Filter tại đúng cấp

Tìm tên của những thành viên trong team `backend`:

```sql
SELECT jsonb_path_query_array(
    '{
       "teams": [
         {"name":"backend","members":[{"name":"An"},{"name":"Binh"}]},
         {"name":"frontend","members":[{"name":"Dung"}]}
       ]
     }'::jsonb,
    '$.teams[*] ? (@.name == "backend").members[*].name'
) AS backend_members;
```

Path trước tiên chọn object team, lọc theo `@.name` rồi mới đi xuống `members`. Nếu đặt filter sau `members[*]`, `@` sẽ đại diện cho **member object** và điều kiện `@.name == "backend"` hỏi một vấn đề khác.

### 8.2. Wildcard * và recursive descent **

`.*` truy cập các giá trị của thành viên object ở cấp hiện tại. `.**` có thể duyệt nhiều cấp lồng nhau.

```sql
SELECT jsonb_path_query_array(
    '{
       "a": {"id": 1},
       "b": {"nested": {"id": 2}}
     }'::jsonb,
    'strict $.**.id'
) AS all_ids;
```

Ví dụ dùng `strict` để tránh một số vấn đề lặp kết quả do **lax auto-unwrapping** khi áp dụng recursive descent.

Lưu ý `.**` hữu ích cho khám phá dữ liệu không đồng nhất nhưng có thể đi qua rất nhiều node và tăng chi phí. Nó cũng có khả năng được index hỗ trợ khác với đường dẫn cố định; không xem toàn bộ recursive searches là rẻ.

## 9. Các toán tử so sánh và dữ liệu kiểu JSON

JSONPath thường dùng:

| Biểu thức | Kiểu kiểm tra |
| --- | --- |
| `@.qty == 2` | Bằng |
| `@.qty != 2` | Khác |
| `@.qty > 2` | Lớn hơn |
| `@.qty >= 2` | Lớn hơn hoặc bằng |
| `@.qty < 2` | Nhỏ hơn |
| `@.qty <= 2` | Nhỏ hơn hoặc bằng |
| `@.vip == true` | JSON boolean true |
| `@.status == "paid"` | JSON string |
| `@.shipping == null` | JSON null |

Ví dụ:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @@ '$.total >= 300'
ORDER BY order_id;
```

Với các giá trị số đúng kiểu, kết quả bao gồm order 3 và 6. Order 5 có `"total":"120"` là chuỗi chứ không phải numeric 120.

### 9.1. Không tự động coi "3" và 3 là cùng kiểu

```sql
SELECT
    jsonb_typeof('3'::jsonb) AS numeric_type,
    jsonb_typeof('"3"'::jsonb) AS string_type;
```

Kỳ vọng là `number` và `string`.

JSONPath có những quy tắc thích ứng cấu trúc trong `lax`, nhưng **không được dùng điều đó như một bước làm sạch và xác thực kiểu dữ liệu**. Các phép toán số trên dữ liệu string có thể không trả true, trả unknown hoặc bị suppress error tùy biểu thức.

Đối với dữ liệu tài chính, tiền tệ và số lượng, nên:

- Chuẩn hóa schema và kiểu khi ingest.
- Dùng ràng buộc/validation thích hợp.
- Giữ số ở JSON numeric hoặc tách sang cột SQL có kiểu rõ ràng.
- Không trông chờ comparator trong JSONPath tự biến mọi chuỗi thành số đúng ý.

### 9.2. Biểu thức số học

JSONPath có thể dùng biểu thức số học với những giá trị số hợp lệ:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (@.qty * @.unit_price >= 200)
'
ORDER BY order_id;
```

Ở dữ liệu hợp lệ, phép kiểm tra đang xét tổng giá trị của **một item line**, không phải tổng cả đơn hàng. Với order 5, `qty` và `unit_price` là string, nên không nên kỳ vọng xử lý như số mà chưa chuẩn hóa.

Đối với tính tổng tiền theo các item phức tạp, `jsonb_array_elements` kết hợp SQL `SUM` có thể minh bạch và dễ kiểm soát kiểu hơn.

## 10. like_regex: kiểm tra chuỗi theo mẫu

Filter hỗ trợ `like_regex` để kiểm tra mẫu văn bản:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (@.sku like_regex "^SKU-(RED|BLUE)$")
'
ORDER BY order_id;
```

Dạng này chọn những order có ít nhất một item `SKU-RED` hoặc `SKU-BLUE`.

Có thể bật cờ không phân biệt hoa thường, ví dụ:

```sql
SELECT jsonb_path_query_array(
    '{"names":["An","Binh","anna","CHI"]}'::jsonb,
    '$.names[*] ? (@ like_regex "^an" flag "i")'
) AS names_starting_with_an;
```

JSONPath `like_regex` có các quy tắc biểu thức chính quy riêng theo SQL/JSON và cách PostgreSQL diễn giải bằng engine regex. Nó **không đồng nhất tuyệt đối** với một biểu thức chính quy JavaScript, Java `Pattern` hay mọi trường hợp của toán tử PostgreSQL `~`.

### 10.1. Tránh regex không được kiểm soát

Regex phức tạp trên tài liệu rất lớn có thể tốn CPU. Không cho người dùng tự do cung cấp JSONPath hay pattern phức tạp rồi thực thi trên bảng khổng lồ mà không có ràng buộc quyền, độ dài, timeout và kiểm soát chi phí.

Nếu chỉ kiểm tra một chuỗi chính xác, dùng equality:

```sql
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")'
```

thường rõ nghĩa hơn regex và có cơ hội nhận hỗ trợ index tốt hơn.

## 11. JSON null, SQL NULL và trường không tồn tại

Đây là nguồn bug phổ biến nhất khi tài liệu không đồng nhất.

Xem ba tài liệu:

```json
{"shipping": null}
```

```json
{}
```

```json
{"shipping": {"city": "Hanoi"}}
```

Chúng khác nhau:

1. `shipping` **tồn tại và có giá trị JSON null**.
2. `shipping` **không tồn tại**.
3. `shipping` **tồn tại và là object**.

### 11.1. Truy vấn kiểm tra có trường hay không

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.shipping'
ORDER BY order_id;
```

`@?` kiểm tra đường dẫn `$.shipping` trả mục nào không. Trong dữ liệu mẫu, order **1–5** có trường `shipping`, kể cả order 4 với giá trị JSON null. Order 6 không có trường này.

### 11.2. Kiểm tra trường có giá trị JSON null

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.shipping ? (@ == null)'
ORDER BY order_id;
```

Trong dữ liệu mẫu, order 4 có `shipping` bằng JSON null.

Có thể dùng SQL extraction để nhìn rõ khác biệt:

```sql
SELECT
    order_id,
    document ? 'shipping' AS key_exists,
    document -> 'shipping' AS shipping_json,
    jsonb_typeof(document -> 'shipping') AS shipping_json_type,
    document ->> 'shipping' AS shipping_text
FROM jsonpath_lab.orders
ORDER BY order_id;
```

- `document ? 'shipping'` kiểm tra **key ở cấp gốc** của object.
- `document -> 'shipping'` trả SQL NULL nếu field không tồn tại; nếu field có JSON null thì trả **giá trị jsonb null**.
- `jsonb_typeof(...)` trả chuỗi `'null'` cho JSON null, nhưng SQL NULL khi không có giá trị JSON để xét.
- `->>` thường trả SQL NULL cho cả trường thiếu và giá trị JSON null.

### 11.3. Kiểm tra trường con tồn tại

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.shipping.city'
ORDER BY order_id;
```

Kết quả mong đợi: order 1, 2, 3, 5; order 4 là JSON null tại `shipping`, còn order 6 thiếu `shipping`.

### 11.4. JSONPath có ba-valued logic

Các so sánh và filter JSONPath có thể sinh `true`, `false` hoặc `unknown` tùy dữ liệu, kiểu và biểu thức. Toán tử SQL `@@` có thể trả SQL NULL khi kết quả predicate không là Boolean thích hợp hoặc khi gặp những lỗi bị suppress theo quy tắc operator.

Trong `WHERE` SQL, chỉ hàng mà điều kiện là **true** mới được giữ. `false` và `NULL` đều không làm hàng được chọn, nhưng chúng **không phải cùng một trạng thái dữ liệu**.

Khi cần phân loại “thiếu field”, “field null”, “field sai kiểu” và “giá trị không đạt”, nên viết bước kiểm tra rõ ràng thay vì cố biến tất cả thành một phép so sánh.

## 12. strict và lax: cấu trúc JSON không đồng nhất

Một JSONPath có thể chạy ở chế độ:

- **`lax`** — mặc định: engine có thể tự điều chỉnh một số khác biệt cấu trúc, tự wrap/unwrap trong những ngữ cảnh nhất định và bỏ qua lỗi cấu trúc còn lại dưới dạng không khớp.
- **`strict`** — cấu trúc cần phù hợp với path rõ ràng; thiếu trường hoặc sai cấu trúc có thể tạo lỗi.

Ví dụ dữ liệu JSON không có `shipping`:

```sql
SELECT jsonb_path_query_array(
    '{"status":"pending"}'::jsonb,
    'lax $.shipping.city'
);
```

Trong `lax`, path không khớp thường cho dãy rỗng, nên kết quả có thể là `[]`.

Thử strict:

```sql
SELECT jsonb_path_query_array(
    '{"status":"pending"}'::jsonb,
    'strict $.shipping.city'
);
```

Ở đây, truy cập member không tồn tại gây lỗi cấu trúc theo strict mode.

### 12.1. Lax không đồng nghĩa xác thực dữ liệu

Giả sử API đôi khi gửi `items` là object và đôi khi là array. `lax` có thể thích ứng một số bước duyệt thay vì báo lỗi ngay.

Điều đó hữu ích khi khám phá JSON không đồng nhất, nhưng cũng **có thể che giấu việc upstream gửi sai schema**.

Nếu ứng dụng đòi `items` luôn là array, nên xác thực:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_typeof(document -> 'items') = 'array'
ORDER BY order_id;
```

và xem xét ràng buộc schema khi lưu dữ liệu.

### 12.2. Lax có thể tạo kết quả trùng ở recursive descent

Với path `.**`, lax mode có cơ chế automatic unwrapping ở một số trường hợp. Duyệt recursive rồi unwrapping có thể đưa cùng giá trị vào dãy kết quả nhiều lần.

Khi cần hiểu chính xác cấp lồng nhau, sử dụng đường dẫn tường minh hoặc `strict` khi cấu trúc phù hợp; không mặc định kết quả của `.**` là một tập giá trị duy nhất.

### 12.3. Vì sao @? có thể không báo lỗi dù path strict?

Hai operator `@?` và `@@` **suppress một số loại lỗi** như field/array element thiếu, loại JSON không mong đợi, lỗi số và ngày giờ.

```sql
SELECT
    '{"status":"paid"}'::jsonb
        @? 'strict $.shipping.city' AS safe_match_test;
```

Dù path viết `strict`, operator `@?` có cơ chế suppress lỗi được định nghĩa cho nó. Vì thế kết quả có thể là false thay vì exception.

Trong khi đó:

```sql
SELECT jsonb_path_query(
    '{"status":"paid"}'::jsonb,
    'strict $.shipping.city'
);
```

hàm `jsonb_path_query` mặc định có thể **phát sinh lỗi** strict structural access. Đừng suy toàn bộ các hàm/toán tử có hành vi lỗi giống nhau.

## 13. Các hàm jsonb_path_*: chọn đúng đầu ra

Bên cạnh `@?` và `@@`, PostgreSQL cung cấp các hàm làm việc với `jsonpath`.

| Hàm | Ý nghĩa | Kiểu kết quả thông thường |
| --- | --- | --- |
| `jsonb_path_exists(target, path [, vars [, silent]])` | Path có trả mục nào không? | `boolean` |
| `jsonb_path_match(target, path [, vars [, silent]])` | Kết quả predicate check | `boolean` hoặc SQL NULL |
| `jsonb_path_query(target, path [, vars [, silent]])` | Trả **nhiều hàng**, một hàng cho mỗi mục khớp | `SETOF jsonb` |
| `jsonb_path_query_first(target, path [, vars [, silent]])` | Trả mục khớp đầu tiên | `jsonb` hoặc SQL NULL |
| `jsonb_path_query_array(target, path [, vars [, silent]])` | Gộp toàn bộ mục khớp thành JSON array | `jsonb` |

Đối số `vars` là object `jsonb` cung cấp các biến `$name`. Đối số `silent` là boolean yêu cầu suppress những loại lỗi phù hợp. Những hàm này không phải API bảo đảm toàn bộ loại lỗi có thể xảy ra đều bị bỏ qua.

### 13.1. jsonb_path_exists — kiểm tra tồn tại

```sql
SELECT
    order_id,
    jsonb_path_exists(
        document,
        '$.items[*] ? (@.sku == "SKU-RED")'
    ) AS contains_red
FROM jsonpath_lab.orders
ORDER BY order_id;
```

Về mục tiêu cơ bản, nó tương ứng phép toán `document @? '$.items[*] ? (...)'`.

### 13.2. jsonb_path_match — kiểm tra Boolean predicate

```sql
SELECT
    order_id,
    jsonb_path_match(
        document,
        '$.customer.vip == true'
    ) AS is_vip
FROM jsonpath_lab.orders
ORDER BY order_id;
```

Đây là dạng hàm tương ứng với `@@`. Đừng truyền một path chỉ trả object vào `jsonb_path_match` rồi coi giá trị khác NULL là Boolean true.

### 13.3. jsonb_path_query — trả nhiều hàng

```sql
SELECT
    o.order_id,
    item.item_json
FROM jsonpath_lab.orders AS o
CROSS JOIN LATERAL jsonb_path_query(
    o.document,
    '$.items[*] ? (@.qty >= 2)'
) AS item(item_json)
ORDER BY o.order_id;
```

Mỗi item thỏa filter được trả thành **một hàng SQL**. `CROSS JOIN LATERAL` khiến hàm được gọi theo tài liệu của hàng order tương ứng.

Nếu không có item khớp, order không xuất hiện trong kết quả của **CROSS JOIN**. Muốn giữ cả những order không có kết quả, cân nhắc `LEFT JOIN LATERAL ... ON TRUE`.

### 13.4. jsonb_path_query_array — gộp thành JSON array

```sql
SELECT
    order_id,
    jsonb_path_query_array(
        document,
        '$.items[*] ? (@.qty >= 2).sku'
    ) AS matching_skus
FROM jsonpath_lab.orders
ORDER BY order_id;
```

Kỳ vọng dạng JSON array, ví dụ order 1 có `["SKU-RED"]` và order 3 có `["SKU-GOLD"]`; order không có item đủ điều kiện trả `[]`.

Hàm này phù hợp khi API muốn trả danh sách những giá trị JSON trích từ mỗi document.

### 13.5. jsonb_path_query_first — mục đầu tiên

```sql
SELECT
    order_id,
    jsonb_path_query_first(
        document,
        '$.items[*].sku'
    ) AS first_sku_json
FROM jsonpath_lab.orders
ORDER BY order_id;
```

Nếu path không tìm được mục, hàm trả **SQL NULL**. Nếu mục khớp đầu tiên là JSON null, giá trị trả về là **JSONB null** — hai trường hợp khác nhau.

Không nên coi `jsonb_path_query_first` là thay thế cho quy tắc “sản phẩm rẻ nhất” hoặc “sản phẩm mới nhất”. Muốn có thứ tự nghiệp vụ thì phải xác định và thực hiện sorting phù hợp.

## 14. Lấy các giá trị ra SQL để join, aggregate và sort

JSONPath mạnh về chọn lọc cấu trúc; SQL vẫn là công cụ tốt cho việc tính tổng.

Ví dụ trích SKU thành các hàng:

```sql
SELECT
    o.order_id,
    sku.sku_json #>> '{}' AS sku
FROM jsonpath_lab.orders AS o
CROSS JOIN LATERAL jsonb_path_query(
    o.document,
    '$.items[*].sku'
) AS sku(sku_json)
ORDER BY o.order_id, sku;
```

`#>> '{}'` ở đây chuyển một **giá trị JSON scalar** thành text theo cách của toán tử JSONB. Cần hiểu kiểu dữ liệu: nếu path trả object/array, cách chuyển thành text có thể không phù hợp với nghiệp vụ.

### 14.1. Tính tổng có kiểm soát kiểu bằng SQL

Nếu cần tổng số lượng trong những order có JSON numeric hợp lệ:

```sql
SELECT
    o.order_id,
    SUM((item.elem ->> 'qty')::integer) AS total_qty
FROM jsonpath_lab.orders AS o
CROSS JOIN LATERAL jsonb_array_elements(
    o.document -> 'items'
) AS item(elem)
WHERE jsonb_typeof(item.elem -> 'qty') = 'number'
GROUP BY o.order_id
ORDER BY o.order_id;
```

Truy vấn chọn những item có `qty` kiểu number rồi chuyển sang integer trong SQL. Tuy vậy, **JSON number có thể là số thập phân hoặc vượt miền integer**, nên đây vẫn là ví dụ cho bộ dữ liệu hiện tại, chưa phải bước validation production đầy đủ.

Nếu dữ liệu bên ngoài không ổn định, nên validate giá trị numeric trước, chọn `numeric` hoặc kiểu SQL khác phù hợp và xác định cách xử lý lỗi/giá trị thiếu.

### 14.2. JSONPath và jsonb_array_elements nên dùng khi nào?

- **Chỉ hỏi tồn tại:** `@?` hoặc `jsonb_path_exists` thường gọn.
- **Lọc nhiều tầng rồi trả JSON array:** `jsonb_path_query_array` hữu ích.
- **Cần nhiều hàng để join/group:** `jsonb_path_query` hoặc `jsonb_array_elements`.
- **Trích vài field cố định:** `->`, `->>`, `#>>` có thể dễ đọc hơn.
- **Cần tính toán nghiệp vụ và ràng buộc dữ liệu:** cân nhắc tách field quan trọng thành cột SQL có kiểu rõ ràng.

Không mặc định JSONPath luôn nhanh hơn mọi toán tử JSON khác; cần xem plan, workload và index.

## 15. Sử dụng biến $name trong JSONPath

Một lỗi ứng dụng phổ biến là nối chuỗi dữ liệu người dùng vào JSONPath:

```text
'$.items[*] ? (@.sku == "' + userInput + '")'
```

Nếu đầu vào có dấu ngoặc kép, ký tự escape hoặc đoạn cú pháp path, biểu thức có thể bị hỏng hoặc thay đổi ý nghĩa. Dùng **biến JSONPath** thay vì tự ghép string.

### 15.1. jsonb_path_exists với vars

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_path_exists(
    document,
    '$.items[*] ? (@.sku == $sku)',
    jsonb_build_object('sku', 'SKU-RED')
)
ORDER BY order_id;
```

- `$sku` là biến bên trong JSONPath.
- `jsonb_build_object('sku', 'SKU-RED')` cung cấp JSON string tương ứng.
- PostgreSQL thực hiện việc gắn biến cho JSONPath engine; không phải nối giá trị vào cú pháp path.

Kết quả: order 1 và 3.

### 15.2. Nhiều biến trong cùng filter

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_path_exists(
    document,
    '$.items[*] ? (@.sku == $sku && @.qty >= $min_qty)',
    jsonb_build_object(
        'sku', 'SKU-RED',
        'min_qty', 2
    )
)
ORDER BY order_id;
```

Kết quả: order 1.

Giá trị `$min_qty` được truyền thành **JSON number**, còn `$sku` thành JSON string. Truyền nhầm `'2'` dạng text thay vì số 2 có thể làm phép so sánh hoạt động khác.

### 15.3. Tham số JSONPath không phải SQL placeholder

Có hai lớp độc lập:

- **SQL parameter:** `?` trong JDBC prepared statement, được driver bind cho câu SQL.
- **JSONPath variable:** `$sku` bên trong giá trị kiểu `jsonpath`, được giải quyết từ object `vars`.

Ví dụ dùng cả hai lớp là cách rõ ràng nhất để xử lý input của ứng dụng.

### 15.4. silent để xử lý cấu trúc không nhất quán

```sql
SELECT
    order_id,
    jsonb_path_exists(
        document,
        'strict $.shipping.city ? (@ == "Hanoi")',
        '{}'::jsonb,
        true
    ) AS hanoi_in_strict_silent_mode
FROM jsonpath_lab.orders
ORDER BY order_id;
```

Đối số thứ tư `true` yêu cầu suppress những lỗi JSONPath phù hợp, hữu ích với tài liệu thiếu `shipping.city`.

**Không dùng `silent=true` để che mọi lỗi dữ liệu.** Nếu schema đòi trường bắt buộc, hãy kiểm tra và ghi nhận lỗi nhập liệu theo chính sách riêng.

## 16. JDBC: truy vấn JSONPath với tham số an toàn

Ví dụ Java/PgJDBC dùng SQL bind parameters và JSONPath variables:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public class OrderSearchRepository {
    private final DataSource dataSource;

    public OrderSearchRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Long> findOrdersWithItem(
            String sku, int minimumQuantity) throws SQLException {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (minimumQuantity < 1) {
            throw new IllegalArgumentException("minimumQuantity must be positive");
        }

        String sql = """
            SELECT order_id
            FROM jsonpath_lab.orders
            WHERE jsonb_path_exists(
                document,
                '$.items[*] ? (@.sku == $sku && @.qty >= $min_qty)',
                jsonb_build_object(
                    'sku', CAST(? AS text),
                    'min_qty', CAST(? AS integer)
                )
            )
            ORDER BY order_id
            """;

        List<Long> ids = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, sku);
            ps.setInt(2, minimumQuantity);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("order_id"));
                }
            }
        }

        return ids;
    }
}
```

Trong câu SQL:

- JSONPath string là **hằng số do ứng dụng kiểm soát**.
- `sku` và `minimumQuantity` là **SQL bind parameters**.
- `jsonb_build_object` xây object cung cấp biến `$sku` và `$min_qty` cho JSONPath.
- Không nối dữ liệu người dùng thành path string.
- `try-with-resources` đóng connection, prepared statement và result set.

### 16.1. Lưu ý về index với tham số

Việc một expression `document @? '...constant...'` có thể dùng GIN index **không đảm bảo** một cách viết tương đương bằng `jsonb_path_exists(document, path, vars)` cũng có cùng khả năng tận dụng index. Truy vấn bằng hàm và truy vấn qua toán tử indexable có thể tạo plan khác nhau.

Hãy đo với `EXPLAIN` và chọn chiến lược phù hợp. Nếu dùng JSONPath literal có giá trị cố định cho điều kiện index, không đưa dữ liệu người dùng vào literal bằng cách nối chuỗi.

### 16.2. Prepared statements và generic/custom plans

PostgreSQL có thể dùng custom hoặc generic plan tùy cách ứng dụng gửi query và tình huống thực thi. Cùng một SQL bind có thể dẫn đến lựa chọn scan khác khi giá trị thay đổi.

Khi tối ưu:

- Ghi PostgreSQL version, index definitions và thống kê.
- Dùng các tham số đại diện cho workload thực.
- Kiểm tra `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp.
- Không kết luận index không hoạt động chỉ vì một tham số rất ít chọn lọc dùng Seq Scan.

## 17. GIN index cho truy vấn JSONPath

Không có index, PostgreSQL có thể phải kiểm tra JSONPath trên rất nhiều hàng trong bảng.

GIN là một access method phù hợp để index nhiều thành phần của `jsonb`. PostgreSQL cung cấp hai operator classes thông dụng:

- **`jsonb_ops`:** mặc định, linh hoạt, hỗ trợ nhiều toán tử.
- **`jsonb_path_ops`:** tối ưu cho một số phép containment/JSONPath, thường gọn và có tính chọn lọc tốt trong những tình huống phù hợp, nhưng không hỗ trợ toàn bộ toán tử mà `jsonb_ops` có.

### 17.1. Index jsonb_ops

```sql
CREATE INDEX idx_orders_document_gin_ops
ON jsonpath_lab.orders
USING GIN (document jsonb_ops);
```

### 17.2. Index jsonb_path_ops

```sql
CREATE INDEX idx_orders_document_gin_path
ON jsonpath_lab.orders
USING GIN (document jsonb_path_ops);
```

Trong một hệ thống thật, thường **không tạo cả hai kiểu GIN trên cùng cột chỉ vì muốn có nhiều index**. Mỗi index đều tăng dung lượng và chi phí DML. Bộ dữ liệu ví dụ rất nhỏ nên planner có thể chọn Seq Scan dù index được tạo thành công.

### 17.3. Ma trận hỗ trợ toán tử

| Toán tử trên jsonb | `jsonb_ops` | `jsonb_path_ops` |
| --- | :---: | :---: |
| `@>` — containment | ✓ | ✓ |
| `@?` — JSONPath exists | ✓ | ✓ |
| `@@` — JSONPath predicate | ✓ | ✓ |
| `?` — tồn tại key/top-level array string | ✓ | ✕ |
| `?|` — tồn tại ít nhất một key trong danh sách | ✓ | ✕ |
| `?&` — tồn tại tất cả key trong danh sách | ✓ | ✕ |

**Đọc đúng phạm vi:** bảng mô tả hỗ trợ operator class. Một toán tử được hỗ trợ **không có nghĩa mọi JSONPath expression đều có thể được index phục vụ hiệu quả**.

### 17.4. Dạng JSONPath dễ trích điều kiện vào GIN

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

GIN có thể trích những điều kiện dạng **accessor chain == constant** từ JSONPath, chẳng hạn đường dẫn tới `sku` và giá trị `SKU-RED`, để tìm candidate rows.

Sau khi tìm candidate bằng index, PostgreSQL vẫn phải kiểm tra điều kiện theo ngữ nghĩa chính xác khi cần. Index không chứng minh được mọi phần logic của JSONPath chỉ bằng một phép tra.

### 17.5. Dạng so sánh range không nhất thiết được index hóa

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.qty >= 2)';
```

GIN JSONPath extraction tập trung vào một số điều kiện **equality với hằng số** trong path. Một điều kiện chỉ gồm `>=` hoặc regex không tự trở thành tìm kiếm index hiệu quả nhờ việc bảng đã có GIN.

Nếu kết hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (@.sku == "SKU-RED" && @.qty >= 2)
';
```

PostgreSQL có thể dùng equality trên SKU để giảm candidate rows, sau đó kiểm tra phần qty, tùy planner và index. **Không giả định mọi điều kiện trong filter đều được GIN pushdown.**

### 17.6. Wildcard recursive và operator class

GIN `jsonb_ops` hỗ trợ việc trích một số accessor chain có `.*` hoặc `.**` trong JSONPath. `jsonb_path_ops` không hỗ trợ những dạng wildcard này trong cơ chế trích điều kiện tương ứng.

Vì vậy, nếu workload thường dùng recursive wildcard paths, đừng chọn `jsonb_path_ops` chỉ vì một benchmark containment cụ thể nhanh hơn; cần xem toàn bộ loại truy vấn thực tế.

### 17.7. jsonb_path_ops và cấu trúc không có giá trị

`jsonb_path_ops` lưu thông tin index khác với `jsonb_ops` và có những giới hạn với cấu trúc không chứa giá trị như object rỗng trong một số truy vấn. Nó không phù hợp cho mọi kiểu tra cứu “có key này” hoặc tìm cấu trúc rỗng.

Đọc rõ predicate và dữ liệu trước khi chọn operator class.

## 18. Expression index và B-tree khi điều kiện đơn giản

Không phải mọi truy vấn liên quan JSON đều nên dùng JSONPath và GIN.

Nếu phần lớn query chỉ lọc `status`:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document ->> 'status' = 'paid';
```

Có thể tạo index expression B-tree:

```sql
CREATE INDEX idx_orders_status_text
ON jsonpath_lab.orders ((document ->> 'status'));
```

Index này nhằm hỗ trợ **biểu thức SQL tương ứng**. Nó không có nghĩa PostgreSQL tự biến mọi predicate `document @? '$.status ...'` thành đúng biểu thức B-tree `document ->> 'status'`.

Một thiết kế khác: nếu `status` được truy cập/lọc thường xuyên, cân nhắc lưu nó dưới dạng cột SQL có kiểu và ràng buộc rõ ràng, thay vì trích từ JSONB ở mọi query.

### 18.1. Index partial theo điều kiện SQL rõ ràng

Ví dụ:

```sql
CREATE INDEX idx_orders_pending_created
ON jsonpath_lab.orders (created_at)
WHERE document ->> 'status' = 'pending';
```

Truy vấn:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document ->> 'status' = 'pending'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00';
```

có cơ hội dùng partial index khi planner chứng minh được predicate của query khớp với predicate index.

Việc diễn đạt lại điều kiện `status = pending` bằng JSONPath không tự đảm bảo planner suy ra partial-index predicate viết bằng `->>`. Không nên dựa vào sự tương đương ngữ nghĩa “nhìn bằng mắt” nếu chưa xem plan.

### 18.2. Containment @> có thể đơn giản hơn JSONPath

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @> '{"status":"paid"}'::jsonb
ORDER BY order_id;
```

Với điều kiện containment đơn giản, `@>` vừa dễ đọc vừa được các GIN jsonb operator classes hỗ trợ.

Đối với mảng object:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @> '{"items":[{"sku":"SKU-RED"}]}'::jsonb
ORDER BY order_id;
```

Đây là cách diễn đạt ngắn để kiểm tra containment phù hợp. Khi cần các điều kiện range, regex hoặc điều kiện ghép phức tạp trong **cùng một item**, JSONPath thường biểu đạt trực tiếp hơn.

## 19. Đọc EXPLAIN cho JSONPath

Sau khi tạo index và chạy `ANALYZE`:

```sql
ANALYZE jsonpath_lab.orders;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

Một số plan có thể thấy:

- `Seq Scan` với `Filter: (document @? ...)`.
- `Bitmap Index Scan` dùng GIN.
- `Bitmap Heap Scan` với `Recheck Cond` trên JSONPath.
- Các node khác do planner lựa chọn.

**Không coi Seq Scan trên bảng 6 hàng là lỗi index.** Planner có thể thấy quét 6 hàng rẻ hơn việc truy cập GIN. Muốn đánh giá index, dùng bảng có kích thước, phân bố SKU và tỷ lệ lọc đại diện workload thật.

### 19.1. Index candidate và recheck

Một GIN index có thể chỉ giúp tìm tập hàng **ứng viên** theo các điều kiện trích từ JSONPath. Các phần phức tạp khác, ví dụ số lượng >= 2 hay nhiều nhánh OR, có thể cần được đánh giá lại.

Do vậy, việc plan hiển thị `Recheck Cond` hoặc `Filter` không chứng minh GIN “không hoạt động”; nó có thể phản ánh quy trình kiểm tra chính xác sau khi tìm ứng viên.

### 19.2. BUFFERS và cache

`EXPLAIN (ANALYZE, BUFFERS)` cho biết shared hit/read và temp I/O theo cơ chế đo của PostgreSQL. `shared read` không tự chứng minh thiết bị SSD/HDD đã thực hiện physical I/O, vì OS page cache có thể phục vụ.

Nếu benchmark các phương án index:

1. Dùng cùng dữ liệu và phân bố.
2. Chạy nhiều lượt sau warm-up phù hợp.
3. Đo các tham số tìm kiếm đại diện.
4. So latency p50/p95 và I/O, không chỉ planner cost.
5. Quan sát ảnh hưởng GIN maintenance khi `INSERT/UPDATE`.

### 19.3. Chi phí ghi của GIN

GIN index giúp tra cứu nhưng có chi phí:

- Dung lượng index.
- CPU/I/O khi dữ liệu jsonb mới được ghi.
- WAL và hoạt động bảo trì index.
- GIN pending list tùy cấu hình/cơ chế và ảnh hưởng tới độ trễ một số thao tác.

Không thêm index cho mọi cột JSONB theo thói quen. Nếu query chủ yếu dùng một vài field cố định, index expression nhỏ hơn có thể phù hợp hơn.

## 20. SQL/JSONPath khác SQL WHERE ở đâu?

JSONPath được thực thi **trên từng giá trị JSON**. SQL `WHERE` quyết định **hàng** nào được giữ.

Ví dụ:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

Điều kiện bên ngoài JSONPath:

- `created_at >= ...` là điều kiện SQL trên cột có kiểu `timestamptz`.
- `document @? ...` là điều kiện SQL Boolean sinh từ kiểm tra nội dung JSONB.
- Bên trong JSONPath, `? (...)` đánh giá các JSON items.

Có thể kết hợp cả hai để tận dụng B-tree trên `created_at` và GIN trên `document` trong những plan phù hợp. Planner không bắt buộc phải dùng cả hai index.

### 20.1. Không tự coi JSONPath là một SQL subquery

Ký hiệu `$` trong JSONPath là **tài liệu gốc**, không phải SQL parameter placeholder hoặc alias trong `FROM`. Ký hiệu `@` trong JSONPath là mục đang lọc, không phải operator `@?`.

Một biểu thức path thường được PostgreSQL **parse như giá trị kiểu `jsonpath`**, không phải câu SQL được thực thi động có thể tự chọn bảng, join hay ghi dữ liệu.

## 21. Kiểm tra sự tồn tại của key: ? và @? khác nhau

Toán tử JSONB `?` và JSONPath operator `@?` có phạm vi khác:

```sql
SELECT
    '{"customer":{"email":"a@example.test"}}'::jsonb
        ? 'customer' AS has_top_level_customer_key,
    '{"customer":{"email":"a@example.test"}}'::jsonb
        ? 'email' AS has_top_level_email_key,
    '{"customer":{"email":"a@example.test"}}'::jsonb
        @? '$.customer.email' AS has_nested_email_path;
```

Dự kiến:

- `? 'customer'` trả true, vì key ở cấp gốc.
- `? 'email'` trả false, vì `email` nằm bên trong `customer`.
- `@? '$.customer.email'` trả true, vì JSONPath đi được xuống field lồng nhau.

`?` cũng có ngữ nghĩa cho string element ở cấp gốc của array JSONB. Nó **không tự tìm key ở mọi tầng lồng nhau**.

### 21.1. Toán tử ?| và ?&

```sql
SELECT
    '{"a":1,"b":2}'::jsonb
        ?| ARRAY['a', 'x'] AS has_any_key,
    '{"a":1,"b":2}'::jsonb
        ?& ARRAY['a', 'b'] AS has_all_keys;
```

- `?|`: ít nhất một key trong danh sách tồn tại.
- `?&`: tất cả key trong danh sách tồn tại.

Các toán tử này thuộc `jsonb_ops` cho GIN, không được `jsonb_path_ops` hỗ trợ trực tiếp. Dùng chúng khi cần kiểm tra key cấp gốc mà không cần bộ lọc JSONPath phức tạp.

## 22. Giá trị trả về của JSONPath và cách biểu diễn an toàn

Ví dụ:

```sql
SELECT
    jsonb_path_query_first(
        '{"total":280}'::jsonb,
        '$.total'
    ) AS total_json;
```

Đầu ra là một giá trị `jsonb` đại diện số 280, không phải cột SQL kiểu `numeric` do PostgreSQL tự quyết định từ schema JSON.

Nếu muốn dùng phép toán SQL:

```sql
SELECT
    (document ->> 'total')::numeric AS total_numeric
FROM jsonpath_lab.orders
WHERE jsonb_typeof(document -> 'total') = 'number'
ORDER BY order_id;
```

Trong dữ liệu mẫu, bản ghi 5 có total là string nên bị loại. Chuyển kiểu vẫn cần kiểm soát miền giá trị (overflow, dạng thập phân, cấu trúc data).

### 22.1. JSONPath query trả nhiều mục

`jsonb_path_query` là set-returning function, có thể tạo **nhiều hàng cho một document**. Nếu join với bảng khác mà không ý thức về số lượng item, kết quả có thể bị nhân bản và gây tổng hợp sai.

Ví dụ một order có hai item thì join lateral với `jsonb_path_query(document, '$.items[*]')` tạo hai dòng order. Nếu sau đó `SUM(total)` ở cấp order mà không xử lý quan hệ one-to-many, có thể đếm `total` hai lần.

Phân biệt:

- Tổng theo order: tính trên **một dòng order**.
- Tổng theo item: mở rộng item rồi tính trên từng item.
- Khi join trở lại các bảng khác: xác định cardinality và khóa liên hệ.

## 23. JSONPath và yêu cầu bảo mật

Dữ liệu JSON thường đến từ API ngoài hoặc request người dùng; cần thiết kế hai lớp bảo vệ.

### 23.1. Không ghép input vào cú pháp path

Sai:

```java
String path = "$.items[*] ? (@.sku == \\"" + skuFromUser + "\\")";
```

Biểu thức này phụ thuộc dữ liệu đầu vào và có thể bị lỗi quoting/escape. Thay bằng SQL bind + `jsonb_build_object` như phần JDBC.

### 23.2. Không cấp quyền truy vấn JSON tùy ý cho người dùng không tin cậy

Ngay cả khi không có SQL injection, một JSONPath phức tạp vẫn có thể:

- Duyệt sâu với `.**`.
- Chạy regex tốn CPU.
- Sinh rất nhiều kết quả trung gian.
- Gây tải trên nhiều hàng JSONB lớn.
- Tạo response quá lớn.

Nếu ứng dụng cho phép query builder động, hãy định nghĩa **một tập phép lọc được cho phép**, giới hạn kích thước/path complexity, dùng statement timeout, pagination và giới hạn số hàng.

### 23.3. Thông tin nhạy cảm trong JSON

Không tự ghi toàn bộ JSON document vào log/APM khi đang debug, nhất là nếu chứa email, số điện thoại, token hoặc dữ liệu người dùng. Giữ query mẫu với dữ liệu giả như `example.test`, ẩn thông tin nhạy cảm trong log và chỉ cấp quyền xem trường phù hợp.

## 24. Kiểm tra JSON schema: JSONPath không thay CHECK constraint

Một query JSONPath có thể tìm ra những tài liệu không đúng mẫu, nhưng nó không tự buộc writer mới phải tuân thủ schema.

Ví dụ tìm những row có `items` không phải array:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_typeof(document -> 'items') IS DISTINCT FROM 'array'
ORDER BY order_id;
```

Có thể thêm ràng buộc đơn giản:

```sql
-- Chỉ minh họa; trước khi áp dụng vào dữ liệu thật,
-- phải xác nhận mọi document hiện hữu thỏa điều kiện.
ALTER TABLE jsonpath_lab.orders
ADD CONSTRAINT items_must_be_array
CHECK (jsonb_typeof(document -> 'items') = 'array');
```

**Lưu ý quan trọng về CHECK:** `CHECK` trong SQL chỉ vi phạm khi biểu thức là **false**; SQL NULL không tự bị coi là false. Nếu mục tiêu là bắt buộc có field `items`, viết điều kiện bảo đảm **field tồn tại** cùng với kiểu.

Ví dụ:

```sql
ALTER TABLE jsonpath_lab.orders
ADD CONSTRAINT items_required
CHECK (
    document ? 'items'
    AND jsonb_typeof(document -> 'items') = 'array'
);
```

Trên bộ dữ liệu mẫu, tất cả order đều có `items` kiểu array nên constraint phù hợp. Nếu field có thể bị thiếu trong hệ thống thật, cần làm sạch dữ liệu trước khi thêm constraint.

### 24.1. Tách cột quan trọng khỏi JSON khi cần

Nếu ứng dụng cần:

- UNIQUE trên mã đơn hàng.
- Foreign key tới khách hàng.
- Range query lớn theo thời gian.
- Aggregate doanh thu theo số thực.
- Tìm kiếm SKU với điều kiện phức tạp mỗi giây.

thì thiết kế quan hệ chuẩn hóa một phần có thể hợp lý:

```text
orders(order_id, created_at, status, customer_id, total_amount, metadata jsonb)
order_items(order_id, sku, qty, unit_price, tags jsonb)
```

JSONB thích hợp cho metadata biến thiên và dữ liệu linh hoạt; không bắt buộc đưa mọi bất biến quan hệ quan trọng vào JSON chỉ vì JSONPath truy vấn được.

## 25. Những lỗi phổ biến khi viết JSONPath

| Hiểu nhầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `@? '$.total > 400'` là kiểm tra total > 400 | Predicate có thể trả một Boolean false nhưng `@?` vẫn thấy kết quả tồn tại | Dùng `@@ '$.total > 400'` hoặc `@? '$ ? (@.total > 400)'` |
| `@@ '$.items[*].sku'` là kiểm tra key tồn tại | `@@` cần một Boolean predicate | Dùng `@? '$.items[*].sku'` |
| Hai điều kiện EXISTS trên items bảo đảm cùng item | Chúng có thể được thỏa bởi **hai item khác nhau** | Gộp điều kiện trong cùng filter sau `items[*]` |
| `!(@.sku == "RED")` nghĩa không có RED ở mọi item | Filter phủ định xét từng item, vẫn tồn tại item khác có thể khớp | Dùng `NOT (doc @? '$.items[*] ? (@.sku == "RED")')` |
| JSON `"3"` luôn bằng JSON `3` | Khác kiểu string/number | Chuẩn hóa và xác thực |
| JSON null giống field thiếu | Một bên có key, bên kia không | Dùng `?`, `@? '$.key'` và `jsonb_typeof` |
| SQL NULL giống JSON null | SQL NULL biểu thị không có giá trị SQL; JSON null là một giá trị JSON | Kiểm tra extraction/type |
| `lax` bảo đảm input hợp lệ | Lax có thể sửa/ẩn khác biệt cấu trúc | Validate schema khi ingest |
| `strict` luôn báo lỗi khi dùng `@?` | Operators có error suppression riêng | Hiểu ngữ nghĩa từng operator/hàm |
| GIN hỗ trợ `@?` nên mọi path đều chạy bằng index | Index chỉ trích được một số điều kiện | Đọc `EXPLAIN` |
| `jsonb_path_ops` hỗ trợ `?` | Operator class này không hỗ trợ key-exists operators | Dùng `jsonb_ops` hoặc index khác |
| `.**` được index hỗ trợ như mọi path cố định | Khả năng trích path khác theo opclass | Xem accessors và workload |
| `jsonb_path_exists(...vars)` chắc chắn dùng cùng GIN như `@?` | Hàm và toán tử có cơ chế tối ưu có thể khác | Đo plan thực tế |
| Regex luôn tốt hơn equality | Regex có overhead và ít cơ hội index extraction | Dùng equality khi phù hợp |
| `jsonb_path_query` luôn trả một hàng | Có thể nhiều items hoặc không có items | Hiểu JOIN LATERAL cardinality |
| `JSONPath` tự thay SQL JOIN/GROUP BY | Chỉ chọn lọc/điều hướng trong JSON | Kết hợp SQL đúng vai trò |
| `EXPLAIN ANALYZE` không chạy câu SQL | Nó **thực thi** query | Thận trọng với DML/chi phí |
| Càng nhiều GIN index càng nhanh | Index có chi phí ghi/disk/WAL | Chọn index theo workload |

## 26. Runbook chẩn đoán một truy vấn JSONPath chậm hoặc sai

**Bước 1 — Xác nhận JSON thực tế.** Lấy một số tài liệu đại diện (đã ẩn dữ liệu nhạy cảm), kiểm tra field có tồn tại không, array hay object, numeric hay string, JSON null hay thiếu trường.

**Bước 2 — Nêu lại điều kiện nghiệp vụ.** Hỏi “tồn tại một item thỏa tất cả điều kiện” hay “có ít nhất một item cho từng điều kiện”? Hai câu này không tương đương.

**Bước 3 — Chọn `@?` hay `@@`.** Nếu path chọn item bằng `? (...)` thì thường dùng `@?`; nếu path là Boolean predicate thì dùng `@@`.

**Bước 4 — Thử trên một JSON literal nhỏ.** Tạo tài liệu đúng/sai/empty/missing/null và kiểm tra biểu thức, tránh suy từ output lớn của production.

**Bước 5 — Kiểm tra `lax`/`strict` và lỗi bị suppress.** Không để dữ liệu sai kiểu được xem là “không có kết quả” mà không có logging/validation.

**Bước 6 — Đặt biến đúng kiểu.** Với input động, dùng `vars` và bind parameters; không nối JSONPath text.

**Bước 7 — Xem query plan.** `EXPLAIN` cho biết Seq Scan/GIN Bitmap path, `EXPLAIN ANALYZE` cho thấy runtime khi an toàn. Phân biệt equality index extraction với range/regex phải recheck.

**Bước 8 — Đánh giá index phù hợp.** So sánh `jsonb_ops`, `jsonb_path_ops`, containment `@>` và B-tree expression index; không tạo mọi loại cùng lúc.

**Bước 9 — Kiểm tra cardinality khi mở rộng JSON.** `jsonb_path_query` trả nhiều hàng; tránh nhân bản dữ liệu khi join/aggregate.

**Bước 10 — Đo trên workload đại diện.** Dùng nhiều tham số, data size, cache, concurrency; đo p95 và ảnh hưởng DML/GIN maintenance.

**Bước 11 — Đưa ra thay đổi có kế hoạch rollback.** Ghi query/index definitions, phiên bản PostgreSQL, kết quả kiểm tra và phương án phục hồi nếu regression.

## 27. Bài thực hành

Sử dụng schema `jsonpath_lab` ở phần 2. Mỗi bài tập yêu cầu giải thích **vì sao** biểu thức có ngữ nghĩa như vậy, không chỉ chạy được SQL.

### Bài 1 — Chọn đường dẫn cơ bản

Dùng `jsonb_path_query_first` lấy `customer.id` của order 1 và `items[0].sku`. Sau đó thử `items[last].sku`.

Vì sao một path có thể trả SQL NULL nếu không có mục khớp?

### Bài 2 — Tìm SKU bằng @?

Viết query tìm order có ít nhất một `items[*].sku` bằng `SKU-RED`. Đối chiếu kết quả với order 1 và 3.

Giải thích vai trò của `$`, `@` và `? (...)`.

### Bài 3 — Điều kiện Boolean bằng @@

Tìm order có `customer.vip == true` bằng `@@`. Viết lại bằng `@?` kết hợp filter trên `customer`.

Vì sao không nên dùng `@? '$.customer.vip == true'`?

### Bài 4 — Bẫy predicate với @?

```sql
SELECT
    '{"total":100}'::jsonb @? '$.total > 400' AS a,
    '{"total":100}'::jsonb @@ '$.total > 400' AS b;
```

Dự đoán `a` và `b` rồi giải thích cách hai toán tử xử lý kết quả JSONPath khác nhau.

### Bài 5 — Điều kiện trên cùng item

Tìm order có **cùng một item** SKU-RED và qty >= 2. Sau đó tách thành hai điều kiện `@?` độc lập.

Tại sao order 3 có thể xuất hiện ở query thứ hai nhưng không xuất hiện ở query thứ nhất?

### Bài 6 — Phủ định tồn tại

Viết hai query:

1. Có **một item không phải SKU-RED**.
2. **Không có item nào** là SKU-RED.

Thử trên order 1 (có cả SKU-RED lẫn SKU-BLUE) và giải thích vì sao kết quả khác nhau.

### Bài 7 — Mảng rỗng

Order 4 có `items=[]`. Viết điều kiện yêu cầu:

- Không có item với qty < 1.
- Có ít nhất một item.
- Nếu có item thì tất cả item phải qty >= 1 và đúng JSON number.

Vì sao mệnh đề “không tồn tại item vi phạm” chưa đủ để đảm bảo mảng không rỗng?

### Bài 8 — JSON null và missing

Với order 4 và 6, kiểm tra:

```sql
SELECT
    order_id,
    document ? 'shipping' AS has_key,
    document -> 'shipping' AS shipping_json,
    jsonb_typeof(document -> 'shipping') AS json_type,
    document @? '$.shipping' AS path_exists
FROM jsonpath_lab.orders
WHERE order_id IN (4, 6)
ORDER BY order_id;
```

Đâu là JSON null, đâu là SQL NULL và đâu là field không tồn tại?

### Bài 9 — Sai kiểu số

So sánh `qty = 3` ở order 2 với `qty = "3"` ở order 5. Viết query dùng `jsonb_typeof` để tìm item có trường qty không phải JSON number.

Vì sao không nên để JSONPath comparison kiêm luôn công việc validation schema?

### Bài 10 — strict và lax

Dùng tài liệu thiếu `shipping` và đường dẫn `$.shipping.city`. Chạy hai hàm `jsonb_path_query_array` ở lax và strict.

Sau đó dùng `@?` với strict path và giải thích ý nghĩa error suppression của toán tử.

### Bài 11 — Trích nhiều mục

Dùng `jsonb_path_query_array` lấy tất cả SKU của order 1. Dùng `jsonb_path_query` cùng `CROSS JOIN LATERAL` để trả mỗi SKU thành một dòng SQL.

Trong câu JOIN tổng hợp số đơn, bạn cần cẩn trọng điều gì về số hàng được tạo thêm?

### Bài 12 — Regex

Tìm những item SKU bắt đầu bằng `SKU-` và kết thúc bằng `RED` hoặc `BLUE` bằng `like_regex`. Thử flag `i` trên một mảng tên có chữ hoa/thường.

Khi nào equality tốt hơn regex?

### Bài 13 — Biến JSONPath

Viết `jsonb_path_exists(document, path, vars)` với biến `$sku = "SKU-RED"` và `$min_qty = 2`.

Vì sao `vars` an toàn và rõ kiểu hơn nối chuỗi user input vào JSONPath?

### Bài 14 — GIN opclasses

Tạo `jsonb_ops` hoặc `jsonb_path_ops` trên `document` trong môi trường học tập. So sánh ma trận hỗ trợ `@>`, `@?`, `@@` và `?`.

Vì sao `jsonb_path_ops` không thay được `jsonb_ops` nếu ứng dụng thường xuyên kiểm tra key với `?`?

### Bài 15 — EQ và range indexability

So sánh hai query:

```sql
EXPLAIN
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

```sql
EXPLAIN
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.qty >= 2)';
```

Điều kiện nào dễ trích equality để GIN lookup hơn? Vì sao không thể khẳng định index đang giúp nếu bảng chỉ có 6 hàng?

### Bài 16 — Expression index hay JSONPath?

Giả sử 95% query lọc theo `status` và chỉ 5% lọc các item lồng nhau. Đề xuất:

- B-tree expression index cho `document ->> 'status'`.
- GIN jsonb index nếu có đủ workload lồng nhau.
- Hoặc tách `status` thành cột SQL chuẩn.

Giải thích trade-off ghi/disk và lợi ích từ type constraints.

### Bài 17 — JDBC PreparedStatement

Viết phương thức Java tìm order theo SKU và minimum qty, dùng SQL bind parameters kết hợp JSONPath `vars`. Không nối dữ liệu người dùng thành JSONPath literal.

Nếu method trả về hàng trăm nghìn order IDs, cần thêm cơ chế gì cho phân trang và giới hạn tải?

### Bài 18 — Query tất cả item thỏa điều kiện

Giả sử nghiệp vụ yêu cầu **mỗi item phải có qty kiểu numeric và >= 1**, đồng thời `items` là array không rỗng.

Hãy thiết kế chiến lược kiểm tra bao gồm:

- Xác minh `items` là mảng.
- Xác minh ít nhất một phần tử.
- Kiểm tra mọi phần tử có field `qty` đúng kiểu.
- Kiểm tra không có phần tử `qty < 1`.
- Xác định cách xử lý lỗi/giá trị lớn ngoài miền nghiệp vụ.

Vì sao chỉ `NOT (document @? '$.items[*] ? (@.qty < 1)')` là chưa đủ?

### Bài 19 — So sánh containment và JSONPath

Viết hai truy vấn tương đương để tìm đơn chứa SKU-RED:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @> '{"items":[{"sku":"SKU-RED"}]}'::jsonb;
```

và:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

Sau đó thêm điều kiện qty >= 2 trên cùng item. Dạng nào diễn đạt điều kiện range trực tiếp hơn?

### Bài 20 — Runbook production

Một service lưu triệu tài liệu `jsonb`, trong đó `items` đôi khi là array, đôi khi null, và `qty` có thể là number hoặc string. API cần query sản phẩm theo SKU/qty với SLA thấp.

Hãy lập runbook gồm:

1. Thu thập schema variants và cách validate.
2. Chọn `@?` hay `@@` đúng ngữ nghĩa.
3. Bảo đảm điều kiện SKU và qty trên **cùng item**.
4. Bind biến vào JSONPath an toàn.
5. So `jsonb_ops`, `jsonb_path_ops`, expression index và schema normalization.
6. Dùng `EXPLAIN` trên dữ liệu/độ chọn lọc đại diện.
7. Đo latency p95, write overhead, cache và GIN size.
8. Chuẩn bị phương án rollout/rollback có kiểm soát.

## 28. Tổng kết

**JSONPath là ngôn ngữ để điều hướng và đặt điều kiện bên trong tài liệu JSON**, đặc biệt hữu ích khi dữ liệu có các mảng và object lồng nhau. Trong PostgreSQL:

- `$` đại diện **tài liệu gốc**, còn `@` đại diện **item đang được filter**.
- `$.items[*] ? (@.qty >= 2)` chọn những item có số lượng từ 2 trở lên.
- **`@?` kiểm tra có ít nhất một JSONPath result**, nên nên dùng với path chứa filter hoặc truy cập field; không dùng trực tiếp một predicate Boolean với `@?`.
- **`@@` dùng kết quả Boolean của predicate check**, ví dụ `document @@ '$.customer.vip == true'`.
- Muốn các điều kiện áp dụng cho **cùng một item**, đặt chúng bên trong **cùng filter** sau `items[*]`.
- Muốn “không có item nào thỏa P”, phủ định **toán tử tồn tại ở ngoài**; khác với “tồn tại một item không thỏa P”.
- Phân biệt **JSON null, SQL NULL và field missing**; xác thực các kiểu dữ liệu số/chuỗi khi ingest.
- `lax` mặc định giúp xử lý cấu trúc không đồng nhất nhưng có thể che giấu schema sai; `strict` phát hiện lỗi cấu trúc, còn `@?`/`@@` có cơ chế suppress một số lỗi.
- Dùng `jsonb_path_exists`, `jsonb_path_match`, `jsonb_path_query`, `jsonb_path_query_first` và `jsonb_path_query_array` theo dạng kết quả cần lấy.
- Dùng `vars` và JDBC binding thay vì nối dữ liệu người dùng thành JSONPath.
- GIN `jsonb_ops` và `jsonb_path_ops` có thể hỗ trợ `@?`/`@@`, đặc biệt với những điều kiện equality có thể trích xuất; **không phải mọi biểu thức JSONPath đều indexable**.
- Với field đơn giản truy cập thường xuyên, `->>` kết hợp B-tree expression index hoặc cột SQL có kiểu rõ ràng có thể phù hợp hơn.
- Hiệu năng cần được đo bằng `EXPLAIN`, workload và chi phí ghi, không chỉ dựa vào việc có GIN index.

Khi thiết kế truy vấn điều kiện trong JSON, hãy luôn hỏi: **điều kiện được áp dụng lên mục nào, tồn tại hay Boolean, đúng kiểu hay không, và kết quả có giữ nguyên ngữ nghĩa nghiệp vụ không?** Trả lời được bốn câu hỏi này sẽ tránh phần lớn sai sót khi xử lý JSONPath trên PostgreSQL.

## 29. Tài liệu PostgreSQL tham khảo

- [JSON Functions and Operators — JSONPath, @?, @@, jsonb_path_*](https://www.postgresql.org/docs/current/functions-json.html)
- [JSON Types — jsonb indexing, jsonb_ops và jsonb_path_ops](https://www.postgresql.org/docs/current/datatype-json.html)
- [JSONPath Type — cú pháp, biểu thức, phương thức và bộ lọc](https://www.postgresql.org/docs/current/datatype-json.html#DATATYPE-JSONPATH)
- [GIN Indexes — các operator classes và cơ chế index lookup](https://www.postgresql.org/docs/current/gin.html)
- [EXPLAIN — đọc kế hoạch và các tùy chọn](https://www.postgresql.org/docs/current/sql-explain.html)
- [Index Types — chọn B-tree, GIN và access method phù hợp](https://www.postgresql.org/docs/current/indexes-types.html)

Các đường dẫn `current` trỏ tới tài liệu PostgreSQL mới nhất. Trước khi dùng tính năng trên môi trường thật, hãy kiểm tra `SHOW server_version;` rồi đối chiếu tài liệu **đúng major version**, đặc biệt khi áp dụng SQL/JSON functions mới hơn, GIN operator classes hoặc tối ưu của planner.
