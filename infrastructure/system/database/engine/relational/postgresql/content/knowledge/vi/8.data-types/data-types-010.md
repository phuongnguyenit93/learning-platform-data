# json, jsonb và tiêu chí lựa chọn trong PostgreSQL

Trong một hệ thống bán hàng, phần lớn thông tin quan trọng có cấu trúc khá ổn định: mã đơn, khách hàng, tổng tiền, thời điểm tạo và trạng thái. Những trường như vậy thường phù hợp với cột quan hệ có kiểu dữ liệu rõ ràng. Tuy nhiên, một số dữ liệu lại linh hoạt: thuộc tính của sản phẩm thay đổi theo danh mục, cấu hình riêng của từng khách hàng, phản hồi từ dịch vụ bên ngoài, payload sự kiện hoặc bản chụp địa chỉ giao hàng. PostgreSQL cung cấp hai kiểu dữ liệu JSON quan trọng là **`json`** và **`jsonb`** để lưu những cấu trúc này trong database.

Hai kiểu đều biểu diễn dữ liệu JSON hợp lệ, nhưng **không tương đương về cách lưu trữ, tốc độ xử lý, toán tử và khả năng lập chỉ mục**. Khi chỉ nhìn thấy một object như `{"status":"paid"}`, việc chọn kiểu có vẻ không quan trọng. Đến lúc cần lọc hàng triệu dòng theo `status`, cập nhật một khóa lồng nhau, giữ nguyên payload gốc từ đối tác hoặc phát hiện giá trị JSON trùng khóa, khác biệt trở nên đáng kể.

Bài học này giải thích:

- Cách PostgreSQL lưu và chuẩn hóa `json`, `jsonb`.
- Sự khác nhau về **thứ tự khóa, khoảng trắng, khóa trùng lặp, tính hợp lệ và độ chính xác số**.
- Các toán tử truy vấn, hàm dựng JSON, xử lý object/array và SQL/JSON path.
- Chọn chỉ mục GIN, B-tree expression hoặc generated column theo mẫu truy vấn.
- Cách quyết định giữa `json`, `jsonb` và thiết kế bảng quan hệ thông thường.
- Những giới hạn về cập nhật, kiểm soát schema, dữ liệu nhạy cảm, migration và concurrency.

Ví dụ sử dụng PostgreSQL hiện đại, đặc biệt các major từ 14 trở lên. Một số tính năng được giới thiệu ở các phiên bản cụ thể; khi triển khai cần kiểm tra `SHOW server_version;` và đọc tài liệu của đúng major đang chạy.

## 1. JSON là một cấu trúc dữ liệu, không chỉ là chuỗi bất kỳ

JSON (*JavaScript Object Notation*) là cách biểu diễn các giá trị có cấu trúc. Các dạng JSON hợp lệ gồm:

| Dạng | Ví dụ JSON | Ghi chú |
| --- | --- | --- |
| Object | `{"sku":"BOOK-SQL","quantity":2}` | Tập các cặp tên–giá trị; tên khóa là chuỗi. |
| Array | `["sql","database"]` | Danh sách các giá trị JSON. |
| String | `"PostgreSQL"` | Chuỗi JSON dùng dấu nháy kép. |
| Number | `250000.50` | Giá trị số theo cú pháp JSON. |
| Boolean | `true` hoặc `false` | Không phải chuỗi `"true"`. |
| Null | `null` | Giá trị null **bên trong JSON**, khác SQL `NULL`. |

Object có thể lồng object, array; array có thể chứa object và những kiểu JSON khác:

```json
{
  "order_id": 1001,
  "status": "paid",
  "customer": {
    "id": 10,
    "name": "Lan"
  },
  "tags": ["priority", "gift"],
  "shipping": null,
  "items": [
    {"sku": "BOOK-SQL", "quantity": 2},
    {"sku": "NOTE-A5", "quantity": 1}
  ],
  "amount": 250000
}
```

Không phải mọi đoạn văn bản có dấu ngoặc nhọn đều là JSON hợp lệ. Ví dụ `{'status':'paid'}` sai cú pháp JSON vì dùng dấu nháy đơn làm dấu nháy tên khóa và chuỗi; `{"a": 1,}` cũng không hợp lệ vì dấu phẩy cuối object.

**Phân biệt hai lớp dấu nháy:** trong lệnh SQL, một giá trị JSON thường được bao bằng chuỗi SQL dùng dấu nháy đơn, còn bên trong JSON phải dùng dấu nháy kép:

```sql
SELECT '{"status": "paid", "quantity": 2}'::jsonb;
```

Ở đây dấu `'... '` bên ngoài là cú pháp literal của SQL; dấu `"..."` bên trong là cú pháp JSON.

## 2. PostgreSQL có hai kiểu: json và jsonb

PostgreSQL cung cấp:

1. **`json`:** lưu một bản sao dạng **văn bản JSON đầu vào**, sau khi kiểm tra cú pháp JSON. Các phép truy vấn thường cần phân tích nội dung văn bản khi xử lý.
2. **`jsonb`:** chuyển JSON đầu vào thành một **biểu diễn nhị phân đã được phân tích cú pháp**, thuận tiện cho tìm kiếm, so sánh và lập chỉ mục.

Chữ `b` trong `jsonb` gợi đến biểu diễn *binary* của PostgreSQL, **không có nghĩa** đây là một chuẩn “binary JSON” có thể gửi trực tiếp sang mọi hệ database khác mà giữ nguyên format. Nó là định dạng nội bộ của PostgreSQL.

### 2.1. Bảng so sánh khái quát

| Tiêu chí | `json` | `jsonb` |
| --- | --- | --- |
| Lưu trữ | Văn bản JSON đầu vào đã được xác thực cú pháp. | Biểu diễn nhị phân đã phân tích cú pháp và tổ chức lại. |
| Giữ khoảng trắng ban đầu | Có. | Không giữ nguyên. |
| Giữ thứ tự khóa object ban đầu | Có. | Không bảo đảm; PostgreSQL lưu theo cách riêng. |
| Giữ khóa object trùng tên trong bản gốc | Có thể giữ nguyên các cặp lặp. | Chỉ giữ một giá trị của khóa, thường là **giá trị cuối cùng** trong đầu vào. |
| Chi phí nhập dữ liệu | Thường ít công chuyển đổi hơn. | Cần phân tích/chuyển đổi sang biểu diễn nhị phân. |
| Truy vấn lại nhiều lần | Thường phải phân tích văn bản trong quá trình xử lý. | Thường thuận tiện và nhanh hơn cho nhiều thao tác truy vấn. |
| Toán tử containment/existence chuyên biệt | Không có trực tiếp như `jsonb`. | Có `@>`, `?`, `?|`, `?&` và các toán tử khác. |
| GIN index trên dữ liệu JSON | Không hỗ trợ trực tiếp theo cách `jsonb`. | Có thể dùng GIN với `jsonb_ops` hoặc `jsonb_path_ops`. |
| So sánh bằng để GROUP BY/DISTINCT | Không có toán tử bằng phổ quát cho giá trị `json`. | Có các toán tử so sánh/equality thích hợp. |
| Tình huống nổi bật | Muốn giữ hình thức biểu diễn JSON gốc. | Dữ liệu JSON cần tìm kiếm, lọc, cập nhật, kiểm tra và lập chỉ mục thường xuyên. |

Trong nhiều ứng dụng nghiệp vụ có nhu cầu truy vấn thuộc tính JSON, **`jsonb` là lựa chọn khởi đầu hợp lý**. Nhưng không nên mặc định chuyển mọi payload sang `jsonb` nếu hệ thống cần giữ nguyên thứ tự, khóa trùng hoặc hình thức văn bản đầu vào.

### 2.2. Ví dụ kiểm tra cách lưu hiển thị

```sql
SELECT
    '{ "b": 2, "a": 1 }'::json  AS original_json,
    '{ "b": 2, "a": 1 }'::jsonb AS normalized_jsonb;
```

Với `json`, nội dung văn bản đầu vào được giữ ở dạng ban đầu. Với `jsonb`, kết quả hiển thị có thể được chuẩn hóa khoảng trắng và thứ tự khóa, chẳng hạn:

```text
json:   { "b": 2, "a": 1 }
jsonb:  {"a": 1, "b": 2}
```

Không nên dựa vào thứ tự khóa của kết quả `jsonb::text` để định nghĩa ngữ nghĩa nghiệp vụ. JSON object về bản chất không phải một danh sách thứ tự khóa có ý nghĩa logic như JSON array.

## 3. Khóa trùng, thứ tự và yêu cầu giữ nguyên payload

### 3.1. Khóa trùng trong object

Một object JSON có thể xuất hiện nhiều lần cùng một tên khóa trong văn bản đầu vào:

```sql
SELECT
    '{"status":"draft","status":"paid"}'::json
        AS raw_payload,
    '{"status":"draft","status":"paid"}'::jsonb
        AS parsed_payload;
```

Với `json`, dạng văn bản vẫn chứa cả hai cặp `status`. Với `jsonb`, PostgreSQL chỉ lưu một cặp tương ứng khóa `status`; khi có khóa trùng trong đầu vào, **giá trị cuối được giữ**, ở đây là `"paid"`.

Nếu giao thức nhận dữ liệu yêu cầu phát hiện và từ chối object có khóa trùng, cần áp dụng chính sách xác thực thích hợp **trước khi sự khác biệt bị mất khi chuyển sang `jsonb`**. Việc cast `json` sang `jsonb` có thể không báo lỗi chỉ vì có khóa lặp.

### 3.2. Array có thứ tự; object không có thứ tự nghiệp vụ

```sql
SELECT
    '[1,2]'::jsonb = '[2,1]'::jsonb AS arrays_equal,
    '{"a":1,"b":2}'::jsonb = '{"b":2,"a":1}'::jsonb
        AS objects_equal;
```

Kết quả kỳ vọng:

```text
arrays_equal  = false
objects_equal = true
```

Vì array có thứ tự, đổi thứ tự phần tử làm thay đổi ý nghĩa của phép so sánh bằng. Thứ tự các khóa object không làm thay đổi equality của `jsonb`.

### 3.3. Trường hợp bắt buộc giữ payload gốc

Ví dụ tổ chức cần lưu nguyên văn phản hồi do đối tác gửi để điều tra/audit, trong đó khoảng trắng, thứ tự khóa hoặc các khóa trùng có ý nghĩa đối với bằng chứng:

- Lưu bản gốc ở `json` nếu cần **hình thức JSON nguyên văn trong database** và đã chấp nhận hành vi giải mã/nhập dữ liệu theo PostgreSQL.
- Nếu cần giữ **từng byte gốc của HTTP request**, bao gồm encoding, ký tự xuống dòng, chữ ký số tính trên bytes hoặc những phần ngoài JSON, hãy lưu thêm bản byte gốc ở `bytea` hoặc kho đối tượng phù hợp. `json` không phải cơ chế bảo quản mọi chi tiết giao thức truyền tải ngoài JSON.
- Nếu vẫn cần tìm kiếm nhanh theo nội dung, có thể lưu thêm **biểu diễn `jsonb` dẫn xuất** ở một cột riêng, với chính sách đồng bộ và dung lượng được cân nhắc.

Đừng dùng `jsonb` làm bản lưu nguyên bản khi quy trình pháp lý hoặc đối soát yêu cầu so khớp văn bản đầu vào chính xác.

## 4. Kiểm tra cú pháp, Unicode và biểu diễn số

Cả `json` và `jsonb` đều kiểm tra cú pháp đầu vào theo quy tắc của PostgreSQL, không chấp nhận văn bản không đúng JSON:

```sql
-- Hợp lệ:
SELECT '{"enabled":true,"retries":3}'::jsonb;

-- Không hợp lệ: khóa và chuỗi dùng dấu nháy đơn trong JSON.
-- SELECT '{''enabled'': true}'::jsonb;
```

`jsonb` còn áp dụng các giới hạn của biểu diễn nội bộ. Ví dụ:

- Số trong JSON phải nằm trong phạm vi có thể biểu diễn bằng kiểu `numeric` của PostgreSQL khi chuyển thành `jsonb`. `json` dưới dạng văn bản có thể chấp nhận một số literal số mà `jsonb` không thể chuyển thành `numeric`.
- Xử lý escape Unicode ở `jsonb` chặt hơn trong những trường hợp như ký tự null Unicode hoặc các cặp surrogate không hợp lệ; `json` và `jsonb` không hoàn toàn giống nhau về việc chấp nhận một số dạng escape.
- `jsonb` chuyển các escape Unicode hợp lệ thành ký tự được lưu theo biểu diễn thích hợp, không bảo đảm giữ nguyên ký tự escape như lúc nhập.

Vì vậy, nếu pipeline nhận dữ liệu từ hệ thống bên ngoài với Unicode không chuẩn hoặc các số cực lớn, **không nên tự chuyển `json → jsonb` trên production mà chưa thử dữ liệu đại diện**.

### 4.1. JSON number và numeric PostgreSQL

Ví dụ:

```sql
SELECT
    jsonb_typeof('123.45'::jsonb) AS json_type,
    ('123.45'::jsonb)::numeric AS numeric_value;
```

`jsonb` dùng biểu diễn số tương ứng với cơ chế `numeric` của PostgreSQL, nên không xem mọi JSON number là một giá trị dấu chấm động `double precision`.

Tuy nhiên, khi ứng dụng Java dùng `double` để tạo payload rồi gửi sang PostgreSQL, mất chính xác có thể **đã xảy ra trước khi PostgreSQL nhận dữ liệu**. Với tiền, hạn mức hoặc những số cần chính xác thập phân, hãy dùng `BigDecimal` trong Java hoặc cột `numeric` PostgreSQL theo mô hình thích hợp.

## 5. Chuẩn bị môi trường thực hành

Tạo schema và hai bảng để so sánh `json` và `jsonb`:

```sql
CREATE SCHEMA IF NOT EXISTS json_lab;

CREATE TABLE json_lab.raw_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload json NOT NULL
);

CREATE TABLE json_lab.orders (
    order_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    details jsonb NOT NULL
        CHECK (jsonb_typeof(details) = 'object')
);
```

Chèn một bản sự kiện văn bản cần bảo toàn hình thức:

```sql
INSERT INTO json_lab.raw_events (source_name, payload)
VALUES (
    'external_partner',
    '{ "event": "order_created", "id": 1001, "event": "order_received" }'
);
```

Chèn hai đơn với `details` có cấu trúc object:

```sql
INSERT INTO json_lab.orders (order_id, details)
VALUES
(
    1001,
    '{
      "status": "paid",
      "customer": {"id": 10, "name": "Lan"},
      "amount": 250000,
      "tags": ["priority", "gift"],
      "shipping": null,
      "items": [
        {"sku": "BOOK-SQL", "quantity": 2},
        {"sku": "NOTE-A5", "quantity": 1}
      ]
    }'::jsonb
),
(
    1002,
    '{
      "status": "pending",
      "customer": {"id": 20, "name": "Minh"},
      "amount": 80000,
      "tags": ["standard"],
      "items": [
        {"sku": "PEN-BLUE", "quantity": 3}
      ]
    }'::jsonb
);
```

Kể từ đây, những truy vấn minh họa có thể được thử trên `json_lab.orders` mà không phụ thuộc vào schema của hệ thống khác. Nếu thực hành nhiều lần, dùng database/schema lab riêng hoặc dọn dữ liệu có kiểm soát để tránh lỗi khóa chính trùng.

### 5.1. Kiểm tra kiểu đã lưu

```sql
SELECT
    order_id,
    pg_typeof(details) AS details_type,
    jsonb_typeof(details) AS root_json_type,
    details
FROM json_lab.orders
ORDER BY order_id;
```

Ở đây `pg_typeof(details)` trả kiểu SQL `jsonb`; `jsonb_typeof(details)` trả kiểu **giá trị JSON ở gốc**, ví dụ `object`. Hai hàm trả lời hai câu hỏi khác nhau.

## 6. Truy xuất giá trị bằng ->, ->>, #> và #>>

PostgreSQL hỗ trợ các toán tử đọc JSON cho cả `json` và `jsonb`. Cần nắm bốn toán tử cơ bản:

| Toán tử | Công dụng | Kiểu kết quả |
| --- | --- | --- |
| `->` | Lấy phần tử object theo key hoặc array theo vị trí | Giá trị `json` hoặc `jsonb`, giữ kiểu JSON. |
| `->>` | Lấy phần tử thành văn bản | `text`. |
| `#>` | Lấy giá trị theo đường dẫn nhiều cấp | `json` hoặc `jsonb`. |
| `#>>` | Lấy giá trị theo đường dẫn nhiều cấp dưới dạng text | `text`. |

Ví dụ:

```sql
SELECT
    order_id,
    details -> 'status'              AS status_jsonb,
    details ->> 'status'             AS status_text,
    details #> '{customer,id}'       AS customer_id_jsonb,
    details #>> '{customer,name}'    AS customer_name_text
FROM json_lab.orders
ORDER BY order_id;
```

Với đơn 1001:

```text
status_jsonb       = "paid"       -- JSON string
status_text        = paid         -- SQL text
customer_id_jsonb  = 10           -- JSON number
customer_name_text = Lan          -- SQL text
```

Sự khác nhau quan trọng: `details -> 'status'` trả **một chuỗi JSON có dấu nháy kép khi hiển thị**, còn `details ->> 'status'` trả giá trị text để so sánh với literal SQL:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ->> 'status' = 'paid';
```

Không nên viết `WHERE details -> 'status' = 'paid'` rồi kỳ vọng PostgreSQL tự hiểu kiểu JSON giống `text`. Toán tử so sánh và giá trị phía phải cần có kiểu tương thích.

### 6.1. Truy cập phần tử array

Index của JSON array bắt đầu từ **0**:

```sql
SELECT
    order_id,
    details -> 'items' -> 0 AS first_item,
    details #>> '{items,0,sku}' AS first_sku
FROM json_lab.orders;
```

Đối với `order_id = 1001`, phần tử đầu là object chứa `sku = "BOOK-SQL"`. Một số toán tử cũng hỗ trợ chỉ số âm để đếm từ cuối array, ví dụ `-> -1`, theo ngữ nghĩa được tài liệu PostgreSQL mô tả.

### 6.2. Phần tử không tồn tại

```sql
SELECT
    details ->> 'coupon_code' AS coupon_code
FROM json_lab.orders
WHERE order_id = 1001;
```

Khi key không tồn tại, toán tử truy xuất thường trả **SQL NULL** thay vì bắt buộc phát lỗi. Điều này hữu ích cho dữ liệu linh hoạt, nhưng cũng có thể che giấu typo:

```sql
-- Gõ sai "status" thành "stats":
SELECT details ->> 'stats'
FROM json_lab.orders;
```

Nếu key bắt buộc trong nghiệp vụ, cần kiểm soát bằng constraint, validation tại ứng dụng hoặc thiết kế cột quan hệ, thay vì chỉ dựa vào toán tử đọc trả NULL.

## 7. Phân biệt SQL NULL, JSON null và key không tồn tại

Đây là một phần dễ gây lỗi nhất khi truy vấn JSON trong PostgreSQL.

Xét ba tình huống:

```sql
SELECT
    '{"shipping":null}'::jsonb AS json_with_null,
    '{}'::jsonb                AS json_without_key,
    NULL::jsonb                AS sql_null_value;
```

- `'{"shipping":null}'::jsonb` là một object có key `shipping` và giá trị JSON `null`.
- `'{}'::jsonb` là object **không có key** `shipping`.
- `NULL::jsonb` là **giá trị SQL NULL** cho cả cột/biểu thức JSONB, không phải một object JSON.

Thử các phép phân biệt:

```sql
SELECT
    details ? 'shipping' AS has_shipping_key,
    details -> 'shipping' IS NULL AS extraction_is_sql_null,
    jsonb_typeof(details -> 'shipping') AS shipping_json_type,
    details ->> 'shipping' AS shipping_as_text
FROM json_lab.orders
WHERE order_id = 1001;
```

Với đơn 1001, key `shipping` tồn tại nhưng có giá trị JSON null:

- `details ? 'shipping'` là `true`.
- `details -> 'shipping'` là giá trị `jsonb` `null`, **không phải SQL NULL**.
- `jsonb_typeof(details -> 'shipping')` trả text `'null'`.
- `details ->> 'shipping'` trả SQL NULL theo cách trích xuất text của JSON null.

Để tìm object có key nhưng giá trị JSON null:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ? 'shipping'
  AND details -> 'shipping' = 'null'::jsonb;
```

Để tìm object không có key:

```sql
SELECT order_id
FROM json_lab.orders
WHERE NOT (details ? 'shipping');
```

**Không dùng một phép `->> ... IS NULL` để đồng nhất “thiếu key” với “key có JSON null”** nếu nghiệp vụ cần phân biệt hai trường hợp.

### 7.1. JSON null trong CHECK constraint

PostgreSQL cho phép `CHECK` thành công khi biểu thức trả `TRUE` **hoặc SQL NULL**; chỉ `FALSE` mới vi phạm. Vì vậy một constraint viết thiếu điều kiện tồn tại có thể không bắt được key bị thiếu.

Ví dụ:

```sql
-- Chưa đủ nếu status có thể vắng mặt:
-- CHECK (details ->> 'status' IN ('paid', 'pending'))
```

Để bắt buộc key và kiểu:

```sql
CHECK (
    details ? 'status'
    AND jsonb_typeof(details -> 'status') = 'string'
    AND details ->> 'status' IN ('paid', 'pending')
)
```

Khi schema JSON đóng vai trò dữ liệu cốt lõi, hãy thiết kế những điều kiện bắt buộc một cách rõ ràng thay vì để lỗi chỉ được phát hiện lúc đọc.

## 8. Containment: toán tử @> và <@

Một điểm mạnh của `jsonb` là kiểm tra **một JSON value có chứa cấu trúc được mô tả bởi JSON khác hay không**.

Toán tử:

- `left @> right`: giá trị JSONB bên trái **chứa** giá trị bên phải theo quy tắc containment.
- `left <@ right`: giá trị JSONB bên trái **được chứa trong** giá trị bên phải.

Ví dụ:

```sql
SELECT
    '{"status":"paid","amount":250000}'::jsonb
        @> '{"status":"paid"}'::jsonb AS contains_status,
    '{"status":"paid"}'::jsonb
        <@ '{"status":"paid","amount":250000}'::jsonb
        AS is_contained;
```

Cả hai trả `true`.

Ứng dụng thực tế:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;
```

Đối với một object lồng nhau:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"customer":{"id":10}}'::jsonb;
```

PostgreSQL kiểm tra sự hiện diện của cấu trúc phù hợp trong JSONB, không yêu cầu object phải có đúng từng ấy key và không còn key nào khác.

### 8.1. Containment với array

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"tags":["priority"]}'::jsonb;
```

Câu này tìm object có array `tags` chứa phần tử `"priority"`. Đây là mẫu truy vấn thường có thể tận dụng GIN index.

Cần phân biệt **array equality** với **array containment**:

```sql
SELECT
    '[1,2,3]'::jsonb = '[3,2,1]'::jsonb
        AS equal_arrays,
    '[1,2,3]'::jsonb @> '[3,1]'::jsonb
        AS contains_elements;
```

Equality quan tâm thứ tự array; containment của JSONB xem sự chứa các phần tử theo ngữ nghĩa containment, trong đó thứ tự các phần tử array không quyết định kết quả. Không dùng `@>` để kiểm tra “mảng bằng chính xác một mảng mẫu”.

### 8.2. Có nên chuyển json sang jsonb để dùng @>?

Nếu cột đang là `json`:

```sql
SELECT event_id
FROM json_lab.raw_events
WHERE payload::jsonb @> '{"id":1001}'::jsonb;
```

Cú pháp cast có thể thực hiện được với các giá trị chuyển đổi hợp lệ, nhưng mỗi lần xử lý có thể phát sinh chi phí chuyển đổi và thay đổi ngữ nghĩa khóa trùng/biểu diễn. Với workload lọc thường xuyên, cân nhắc lưu `jsonb` hoặc tạo một biểu diễn dẫn xuất phù hợp, thay vì lặp cast tùy tiện trên hàng triệu dòng.

## 9. Kiểm tra sự tồn tại của key và phần tử: ?, ?|, ?&

Toán tử chuyên biệt của `jsonb`:

| Toán tử | Ý nghĩa |
| --- | --- |
| `?` | Có key ở **cấp trên cùng** của object, hoặc phần tử string ở cấp trên cùng của array? |
| `?|` | Có ít nhất một key/phần tử string trong danh sách? |
| `?&` | Có tất cả key/phần tử string trong danh sách? |

Ví dụ:

```sql
SELECT
    details ? 'customer' AS has_customer,
    details ?| ARRAY['status', 'coupon_code'] AS has_any,
    details ?& ARRAY['status', 'amount'] AS has_all
FROM json_lab.orders
WHERE order_id = 1001;
```

Điểm dễ nhầm: toán tử `?` không tự tìm key sâu trong mọi object lồng nhau.

```sql
-- Kiểm tra key "id" ở gốc object:
SELECT details ? 'id'
FROM json_lab.orders
WHERE order_id = 1001;

-- Kiểm tra key "id" bên trong object customer:
SELECT (details -> 'customer') ? 'id'
FROM json_lab.orders
WHERE order_id = 1001;
```

Ở ví dụ này, `id` nằm trong `customer` chứ không ở gốc. Khi lọc key nested, phải truy cập đúng object con hoặc dùng một dạng truy vấn thích hợp khác.

### 9.1. Kiểm tra trong array

```sql
SELECT order_id
FROM json_lab.orders
WHERE (details -> 'tags') ? 'priority';
```

Ở đây `details -> 'tags'` trả JSONB array, và `?` kiểm tra phần tử string ở cấp trên cùng của array ấy.

## 10. SQL/JSON path và các truy vấn lồng nhau

Khi cấu trúc JSON sâu hoặc cần lọc phần tử array theo điều kiện, những phép truy xuất `->` đơn giản có thể dài và khó viết. PostgreSQL từ major 12 có hỗ trợ **SQL/JSON path** với các hàm/toán tử liên quan, gồm `jsonb_path_exists`, `jsonb_path_query`, `jsonb_path_query_first` và các toán tử `@?`, `@@`.

Ví dụ tìm đơn chứa ít nhất một dòng có `quantity >= 2`:

```sql
SELECT order_id
FROM json_lab.orders
WHERE jsonb_path_exists(
    details,
    '$.items[*] ? (@.quantity >= 2)'
);
```

Hoặc dùng toán tử:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @? '$.items[*] ? (@.quantity >= 2)';
```

Trong biểu thức path:

- `$` là giá trị JSON gốc.
- `.items` truy cập key `items`.
- `[*]` xét các phần tử trong array.
- `? (...)` lọc phần tử theo biểu thức điều kiện.
- `@` đại diện giá trị hiện tại đang được đánh giá trong filter.

Lấy ra các dòng hàng thỏa điều kiện:

```sql
SELECT
    order_id,
    jsonb_path_query(
        details,
        '$.items[*] ? (@.quantity >= 2)'
    ) AS matching_item
FROM json_lab.orders
ORDER BY order_id;
```

Hàm `jsonb_path_query` có thể trả **nhiều hàng** từ một JSON document. Nếu một đơn có nhiều item thỏa điều kiện, kết quả có thể có nhiều hàng cho cùng `order_id`.

### 10.1. @? khác @@

- `@?` đánh giá liệu path có trả một mục thích hợp hay không theo ngữ nghĩa tồn tại.
- `@@` đánh giá một **JSONPath predicate/check expression**, với ngữ nghĩa boolean hoặc SQL NULL theo quy tắc PostgreSQL.

Ví dụ predicate:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @@ '$.amount > 100000';
```

Không xem `@?` và `@@` là hai cách viết hoàn toàn có thể thay thế trong mọi biểu thức path. Khi thiết kế logic kiểm tra tồn tại, điều kiện, thiếu thuộc tính và kiểu dữ liệu, cần đọc tài liệu JSONPath của major đang dùng.

### 10.2. Khi nào JSONPath là lựa chọn tốt?

JSONPath hữu ích khi:

- Có nhiều object/array lồng nhau.
- Cần kiểm tra sự tồn tại của một phần tử thỏa điều kiện.
- Muốn tránh viết nhiều phép `jsonb_array_elements` thủ công.
- Biểu thức có thể tận dụng những mẫu index mà PostgreSQL hỗ trợ.

Nhưng **không phải mọi JSONPath predicate đều được tăng tốc bởi GIN**. Khả năng lập chỉ mục phụ thuộc operator, operator class và dạng điều kiện cụ thể có thể được trích xuất. Những phép so sánh phạm vi như `>` trên một trường lồng nhau thường cần đánh giá riêng.

## 11. Biến JSON array thành các hàng SQL

Khi cần thống kê, JOIN hoặc kiểm tra các phần tử trong array, có thể dùng hàm *set-returning* và `LATERAL`.

### 11.1. jsonb_array_elements

```sql
SELECT
    o.order_id,
    item.value ->> 'sku' AS sku,
    (item.value ->> 'quantity')::integer AS quantity
FROM json_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.details -> 'items') AS item(value)
ORDER BY o.order_id, sku;
```

Mỗi phần tử object trong `items` trở thành một hàng SQL. `LATERAL` cho phép hàm tham chiếu cột `details` của hàng `orders` đang được xét.

**Chú ý:** `jsonb_array_elements` mong đợi một JSON array. Nếu key `items` có kiểu object hoặc JSON null, truy vấn có thể lỗi. Với dữ liệu không đồng nhất, hãy kiểm tra `jsonb_typeof` hoặc thiết kế biểu thức an toàn trước khi gọi hàm.

Ví dụ chỉ dùng các hàng chắc chắn có array:

```sql
SELECT
    o.order_id,
    item.value
FROM json_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.details -> 'items') = 'array'
            THEN o.details -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS item(value);
```

Đoạn `CASE` ở trên thay giá trị không phải array bằng mảng rỗng. Tùy nghiệp vụ, việc bỏ qua dữ liệu sai kiểu có thể không phù hợp; nếu `items` là bắt buộc, nên phát hiện và từ chối dữ liệu không hợp lệ tại lúc ghi.

### 11.2. jsonb_to_recordset

Nếu array gồm các object có cấu trúc tương đối ổn định:

```sql
SELECT
    o.order_id,
    i.sku,
    i.quantity
FROM json_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_to_recordset(o.details -> 'items')
        AS i(sku text, quantity integer)
ORDER BY o.order_id, i.sku;
```

`jsonb_to_recordset` chuyển từng object thành record có các cột và kiểu được khai báo. Đây là công cụ tiện lợi cho **trích xuất dữ liệu**, không thay thế việc định nghĩa bảng `order_items` có khóa chính, foreign key và index nếu cần truy vấn/cập nhật từng dòng như thực thể quan hệ thật.

### 11.3. array_length và kiểu giá trị

```sql
SELECT
    order_id,
    jsonb_array_length(details -> 'items') AS item_count
FROM json_lab.orders;
```

Hàm trên chỉ phù hợp khi `details -> 'items'` là JSON array. Không giả định mọi thuộc tính JSON luôn có kiểu đúng nếu ứng dụng cho phép payload tự do.

## 12. Tạo JSON bằng các hàm PostgreSQL

Đừng nối các chuỗi bằng tay như `'{"name":"' || name || '"}'`. Tên khách có thể chứa dấu nháy, ký tự xuống dòng hoặc những ký tự cần escape; nối chuỗi thủ công dễ tạo JSON sai cú pháp và gây rủi ro khi đưa dữ liệu người dùng vào đầu ra.

PostgreSQL có các hàm tạo JSON:

| Hàm | Công dụng |
| --- | --- |
| `json_build_object` | Tạo JSON object từ các cặp key/value, trả `json`. |
| `jsonb_build_object` | Tương tự nhưng trả `jsonb`. |
| `json_build_array` / `jsonb_build_array` | Tạo JSON array. |
| `to_json` / `to_jsonb` | Chuyển giá trị SQL sang biểu diễn JSON phù hợp. |
| `row_to_json` | Chuyển một composite/record SQL thành object JSON. |
| `json_agg` / `jsonb_agg` | Gom nhiều giá trị thành JSON array. |
| `json_object_agg` / `jsonb_object_agg` | Gom các cặp key/value thành object. |

Ví dụ:

```sql
SELECT jsonb_build_object(
    'order_id', 1001,
    'status', 'paid',
    'priority', true,
    'tags', jsonb_build_array('gift', 'priority')
) AS order_payload;
```

Xây object cho từng đơn:

```sql
SELECT jsonb_build_object(
    'order_id', order_id,
    'status', details ->> 'status',
    'amount', details -> 'amount'
) AS summary
FROM json_lab.orders
ORDER BY order_id;
```

Ở đây `details -> 'amount'` giữ kiểu JSON number thay vì chuyển qua text, còn `details ->> 'status'` tạo SQL text rồi được chuyển thành JSON string khi dựng object.

### 12.1. jsonb_agg và thứ tự

```sql
SELECT jsonb_agg(
    jsonb_build_object(
        'order_id', order_id,
        'status', details ->> 'status'
    )
    ORDER BY order_id
) AS order_summaries
FROM json_lab.orders;
```

`ORDER BY order_id` bên **trong** lời gọi aggregate giúp quy định thứ tự phần tử của JSON array kết quả. Nếu bỏ `ORDER BY`, thứ tự hàng đưa vào aggregate không phải cam kết ổn định của SQL.

### 12.2. Nên trả JSON từ database hay từ Java?

Tùy tầng thiết kế:

- PostgreSQL tạo JSON hữu ích cho báo cáo, aggregation hoặc API query cần cấu trúc phức tạp và đã cân nhắc chi phí.
- Java có thể dựng JSON bằng thư viện serialization từ các DTO sau khi truy vấn cột quan hệ.
- Không nên tạo một payload JSON cực lớn trong một truy vấn chỉ để tránh xử lý phân trang hoặc luồng dữ liệu tại application.

Lựa chọn nằm ở ranh giới trách nhiệm và chi phí vận hành, không phải vì PostgreSQL hỗ trợ `jsonb_build_object` thì mọi API nên trả một JSON object được tạo hoàn toàn trong SQL.

## 13. Cập nhật JSONB: jsonb_set, jsonb_insert và toán tử ||

Một giá trị `jsonb` có thể được thay đổi bằng hàm tạo ra **giá trị JSONB mới** rồi gán lại vào cột.

### 13.1. Thay giá trị một key

```sql
UPDATE json_lab.orders
SET details = jsonb_set(
    details,
    '{status}',
    '"shipped"'::jsonb,
    true
)
WHERE order_id = 1001;
```

Giải thích:

- Đối số đầu là JSONB nguồn.
- `'{status}'` là đường dẫn dạng `text[]`.
- `'"shipped"'::jsonb` là một **JSON string**; không phải text `shipped` không có dấu nháy JSON.
- Đối số cuối `true` cho phép tạo **phần tử cuối** của path khi thiếu theo ngữ nghĩa hàm.

Để cập nhật thuộc tính lồng nhau:

```sql
UPDATE json_lab.orders
SET details = jsonb_set(
    details,
    '{customer,name}',
    to_jsonb('Nguyễn Lan'::text),
    false
)
WHERE order_id = 1001;
```

`to_jsonb('Nguyễn Lan'::text)` an toàn hơn tự tạo chuỗi JSON có dấu nháy vì PostgreSQL xử lý việc chuyển và escape.

**Giới hạn quan trọng:** `jsonb_set` không tự động tạo cả chuỗi object trung gian còn thiếu. Nếu `customer` chưa tồn tại và path là `'{customer,name}'`, việc đặt `create_if_missing = true` không có nghĩa PostgreSQL sẽ tạo mọi cấp nested từ đầu. Cần chuẩn bị object cha hoặc dùng biểu thức cập nhật phù hợp.

### 13.2. Xóa một key

```sql
UPDATE json_lab.orders
SET details = details - 'shipping'
WHERE order_id = 1001;
```

Với JSONB object, toán tử `-` có thể loại key ở cấp trên cùng. Cũng có cách xóa theo path sâu bằng toán tử `#-`:

```sql
UPDATE json_lab.orders
SET details = details #- '{customer,name}'
WHERE order_id = 1001;
```

Điều này làm thay đổi ý nghĩa dữ liệu: key không tồn tại khác key chứa JSON null. Cần định nghĩa rõ “xóa thuộc tính” hay “đặt thuộc tính thành null” theo nghiệp vụ.

### 13.3. Nối/merge bằng ||

```sql
SELECT
    '{"status":"draft","customer":{"id":10}}'::jsonb
    ||
    '{"status":"paid","source":"api"}'::jsonb
    AS merged;
```

Ở cấp object, những key trùng sẽ lấy giá trị bên phải. Tuy nhiên, `||` không phải phép **deep merge** tổng quát; một object lồng nhau trùng key có thể bị thay toàn bộ ở cấp key đó.

Ví dụ:

```sql
SELECT
    '{"customer":{"id":10,"name":"Lan"}}'::jsonb
    ||
    '{"customer":{"name":"Minh"}}'::jsonb;
```

Kết quả không nên được hiểu như deep merge giữ lại `customer.id`. Nếu cần cập nhật riêng `customer.name`, dùng `jsonb_set` theo path hoặc logic merge đệ quy đã được định nghĩa rõ.

### 13.4. Chèn phần tử vào array

```sql
SELECT jsonb_insert(
    '["a","c"]'::jsonb,
    '{1}',
    '"b"'::jsonb
) AS inserted_array;
```

Đây là minh họa hàm thêm phần tử vào vị trí trong JSONB array. Trên dữ liệu quan hệ cần thay đổi từng item, một bảng con riêng với khóa và thứ tự rõ ràng có thể dễ kiểm soát hơn việc sửa một JSON array lớn thường xuyên.

## 14. Mỗi UPDATE JSONB có chi phí thực tế

`jsonb_set` cho cảm giác như chỉ sửa một mẩu nhỏ trong document, nhưng PostgreSQL sử dụng MVCC: một `UPDATE` thông thường tạo **phiên bản hàng mới** chứ không sửa một vùng byte của tuple hiện tại ngay tại chỗ theo nghĩa đơn giản.

Khi cập nhật một JSONB document lớn:

- PostgreSQL có thể phải xử lý/tạo biểu diễn giá trị JSONB mới.
- Hàng mới được ghi và phiên bản cũ chờ cơ chế dọn dẹp như VACUUM.
- Có thêm WAL, I/O và có thể cập nhật index liên quan.
- Với giá trị lớn, PostgreSQL có cơ chế TOAST để lưu trữ/nén dữ liệu; việc cập nhật một thành phần không bảo đảm chỉ ghi đúng thành phần đó xuống storage.
- Nếu index phụ thuộc vào JSONB đã thay đổi, chi phí duy trì index có thể đáng kể.

Ví dụ một bảng lưu `items` như JSONB array dài hàng nghìn phần tử và liên tục cập nhật `quantity` của từng item thường không tốt bằng bảng `order_items` tách riêng có khóa `(order_id, line_no)`, nếu mỗi item là đơn vị cập nhật/truy vấn độc lập.

**Quy tắc thực dụng:** dữ liệu chủ yếu được đọc/trả về thành một khối và ít thay đổi có thể hợp với JSONB; dữ liệu cần ghi từng phần tử với tần suất cao, JOIN và ràng buộc quan hệ thường nên nằm ở cột/bảng quan hệ rõ ràng.

## 15. GIN index cho JSONB

Khi có nhiều hàng và thường lọc theo cấu trúc JSON, `jsonb` hỗ trợ **GIN (Generalized Inverted Index)**.

Ví dụ:

```sql
CREATE INDEX idx_orders_details_gin
ON json_lab.orders
USING gin (details);
```

Index trên dùng operator class mặc định `jsonb_ops`. Nó có thể hỗ trợ nhiều mẫu truy vấn kiểu:

```sql
-- Tìm giá trị chứa cặp key/value.
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;

-- Tìm object có key ở cấp gốc.
SELECT order_id
FROM json_lab.orders
WHERE details ? 'shipping';

-- Tìm object có ít nhất một trong hai key.
SELECT order_id
FROM json_lab.orders
WHERE details ?| ARRAY['shipping', 'coupon_code'];
```

GIN không phải một bảng ánh xạ tất cả mọi câu SQL sang truy vấn O(1). Planner chọn dùng index hay không dựa trên thống kê, selectivity và chi phí. Bảng có hai dòng trong lab có thể được quét tuần tự; điều đó không tự chứng minh index sai.

### 15.1. Hai operator class quan trọng

PostgreSQL cung cấp hai operator class GIN đáng chú ý cho JSONB:

| Operator class | Toán tử nổi bật được hỗ trợ cho tìm kiếm | Đánh đổi |
| --- | --- | --- |
| `jsonb_ops` | `?`, `?|`, `?&`, `@>`, `@?`, `@@` | Linh hoạt, hỗ trợ kiểm tra tồn tại key; thường là mặc định. |
| `jsonb_path_ops` | `@>`, `@?`, `@@` | Thường tạo index gọn/chuyên biệt hơn cho containment và một số JSONPath phù hợp; **không hỗ trợ** `?`, `?|`, `?&` như `jsonb_ops`. |

Ví dụ tạo index với `jsonb_path_ops`:

```sql
CREATE INDEX idx_orders_details_path
ON json_lab.orders
USING gin (details jsonb_path_ops);
```

Hai index trên cùng cột trong lab chỉ giúp minh họa cú pháp; **không nên duy trì cả hai trong production chỉ vì thấy hai cách tạo**. Cần chọn theo loại toán tử query thực tế, độ lớn index và chi phí cập nhật.

### 15.2. Khi nào jsonb_path_ops phù hợp?

Một hệ thống chủ yếu truy vấn:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"customer":{"id":10}}'::jsonb;
```

có thể cân nhắc `jsonb_path_ops` để tập trung vào containment. Nhưng nếu truy vấn thường là:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ? 'shipping';
```

thì `jsonb_path_ops` không phải index operator class hỗ trợ trực tiếp toán tử `?` đó. Cần `jsonb_ops`, expression index hoặc cách biểu diễn truy vấn khác phù hợp.

**Lưu ý về JSONPath:** cả hai operator class có thể hỗ trợ một số biểu thức `@?` và `@@`, nhưng việc PostgreSQL trích xuất điều kiện có thể lập chỉ mục phụ thuộc cấu trúc path và so sánh. Không suy luận “có index JSONB” thì mọi hàm hoặc phép kiểm tra JSONPath đều chạy qua index.

### 15.3. GIN index cũng có chi phí

Ưu điểm là giảm số hàng phải kiểm tra khi predicate đủ chọn lọc. Đổi lại:

- Tạo index cần CPU/I/O và dung lượng.
- `INSERT/UPDATE/DELETE` phải bảo trì GIN index.
- Index có thể lớn nếu document có nhiều key/value khác nhau.
- Predicate ít chọn lọc có thể khiến planner ưu tiên seq scan.
- Những truy vấn sorting/range không nhất thiết được phục vụ tốt bởi GIN.

Để quyết định, hãy đo workload thật thay vì tạo GIN mặc định cho mọi cột `jsonb`.

## 16. B-tree expression index cho một đường dẫn thường lọc

Nếu ứng dụng lọc gần như luôn theo một key cố định như `status`, một **B-tree expression index** có thể đơn giản và hiệu quả hơn GIN trên toàn document.

```sql
CREATE INDEX idx_orders_status
ON json_lab.orders ((details ->> 'status'));
```

Truy vấn:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ->> 'status' = 'paid';
```

Expression trong query nên tương thích với expression được index, để planner có cơ hội sử dụng index. Không nên giả định index B-tree trên `details ->> 'status'` sẽ tự tối ưu mọi dạng truy vấn containment:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;
```

Câu này có ngữ nghĩa lọc gần giống trong ví dụ nhưng **hình thức operator khác**; hãy đọc `EXPLAIN` để biết index nào được planner chọn.

### 16.1. Lập chỉ mục số nằm trong JSONB

Nếu muốn lọc theo `customer.id` dạng số:

```sql
CREATE INDEX idx_orders_customer_id
ON json_lab.orders
(((details #>> '{customer,id}')::bigint));
```

Query:

```sql
SELECT order_id
FROM json_lab.orders
WHERE (details #>> '{customer,id}')::bigint = 10;
```

**Cảnh báo quan trọng:** nếu một hàng chứa `customer.id = "abc"` hoặc kiểu dữ liệu không thể chuyển sang `bigint`, việc tạo index hoặc ghi dữ liệu có thể lỗi. Hãy xác thực kiểu/miền giá trị bằng constraint hoặc quy trình nhập trước khi dùng cast trong index.

Đối với key có kiểu và ràng buộc ổn định, một cột `customer_id bigint` quan hệ thông thường thường **rõ ràng và dễ dùng foreign key hơn** so với chôn ID quan trọng trong JSONB rồi liên tục cast.

### 16.2. Index trên một nhánh của JSONB

Ví dụ phần `tags` được truy vấn thường xuyên:

```sql
CREATE INDEX idx_orders_tags_gin
ON json_lab.orders
USING gin ((details -> 'tags'));
```

Query phù hợp:

```sql
SELECT order_id
FROM json_lab.orders
WHERE (details -> 'tags') ? 'priority';
```

Index trên nhánh có thể nhỏ hơn so với index toàn document nếu query chỉ liên quan một phần dữ liệu. Nhưng nếu cùng lúc có nhiều đường dẫn được truy vấn, chi phí nhiều expression indexes có thể lớn hơn một chiến lược GIN phù hợp.

## 17. EXPLAIN và cách kiểm tra index có hiệu quả thật

Sau khi tạo index, dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;
```

Và:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM json_lab.orders
WHERE details ->> 'status' = 'paid';
```

Những thông tin nên đọc:

- `Seq Scan`, `Index Scan`, `Bitmap Index Scan` và `Bitmap Heap Scan`: cách PostgreSQL lấy hàng.
- `Index Cond`: điều kiện được dùng ở bước truy cập index khi có.
- `Filter`: điều kiện được kiểm tra sau khi lấy hàng theo kế hoạch.
- `Rows Removed by Filter`: số hàng bị loại trong một bước.
- `Buffers`: số trang được đọc/hit trong buffer theo mô hình thống kê của EXPLAIN.
- Thời gian thực thi và số hàng thực tế so với số hàng dự kiến.

Với vài hàng trong lab, PostgreSQL có thể chọn `Seq Scan` vì chi phí quét rất nhỏ. Không nên ép index hoặc kết luận index vô dụng dựa vào bảng quá nhỏ.

### 17.1. Đo chi phí đọc và ghi cùng nhau

Một GIN index có thể tăng tốc truy vấn `@>` nhưng làm chậm những transaction cập nhật `details` thường xuyên. Vì thế, đánh giá cả:

1. P95/P99 latency của truy vấn đọc quan trọng.
2. Thời gian `INSERT`/`UPDATE`/`DELETE`.
3. Dung lượng bảng, index và WAL.
4. Độ chọn lọc của key và số hàng thực tế.
5. Tác động của autovacuum, buffer cache, đợt bulk load và concurrency.

Đừng đưa `jsonb` và index vào hệ thống chỉ vì một truy vấn thử với `LIMIT 1` chạy nhanh trên dữ liệu không đại diện.

### 17.2. pg_column_size không phải kết quả benchmark tổng thể

Có thể xem kích thước biểu diễn từng giá trị:

```sql
SELECT
    pg_column_size('{"a":1,"b":2}'::json) AS json_size,
    pg_column_size('{"a":1,"b":2}'::jsonb) AS jsonb_size;
```

Nhưng không có quy tắc rằng `jsonb` **luôn** nhỏ hơn `json` hoặc ngược lại. Kết quả tùy document, cách biểu diễn, nén/TOAST và metadata. `pg_column_size` ở ví dụ không đại diện trực tiếp cho tổng chi phí bảng, chỉ mục, WAL và I/O của cả workload.

## 18. Kiểm soát schema JSONB bằng CHECK và cột quan hệ

JSON có cấu trúc linh hoạt, nhưng “linh hoạt” không nên bị hiểu thành “có thể ghi mọi dữ liệu sai định dạng”.

Giả sử mọi đơn đều phải có:

- `status` thuộc danh sách cho phép.
- `amount` là JSON number.
- `customer` là JSON object có `id` là JSON number.
- `items` là JSON array.

Có thể thêm constraints:

```sql
ALTER TABLE json_lab.orders
ADD CONSTRAINT ck_orders_details_shape
CHECK (
    jsonb_typeof(details) = 'object'
    AND details ? 'status'
    AND jsonb_typeof(details -> 'status') = 'string'
    AND details ->> 'status'
        IN ('pending', 'paid', 'shipped', 'cancelled')
    AND details ? 'amount'
    AND jsonb_typeof(details -> 'amount') = 'number'
    AND details ? 'customer'
    AND jsonb_typeof(details -> 'customer') = 'object'
    AND jsonb_typeof(details #> '{customer,id}') = 'number'
    AND details ? 'items'
    AND jsonb_typeof(details -> 'items') = 'array'
);
```

Ví dụ này kiểm tra **cấu trúc cơ bản**, không phải một JSON Schema validator hoàn chỉnh. Nó chưa kiểm tra mọi item trong array, không enforce `customer.id` tham chiếu tới hàng trong bảng khách, và chưa kiểm soát tất cả quy tắc tiền tệ.

### 18.1. CHECK và SQL NULL

Để buộc trường phải có mặt, `details ? 'status'` cho kết quả boolean rõ. Khi viết constraint chỉ dùng biểu thức trích xuất có thể trả SQL NULL, cần nhớ PostgreSQL `CHECK` không từ chối biểu thức UNKNOWN/NULL như nó từ chối FALSE.

Do đó, với những trường bắt buộc hãy kiểm tra **tồn tại, kiểu và miền giá trị** thay vì chỉ kiểm tra giá trị sau `->>`.

### 18.2. Khi nào cần tách cột quan hệ?

Nếu `status`, `amount` và `customer_id` là những trường quan trọng dùng trong:

- `WHERE`/`JOIN` thường xuyên,
- foreign key và uniqueness,
- phân vùng bảng,
- phân quyền theo cột,
- báo cáo nghiệp vụ nhiều chiều,
- cập nhật độc lập với payload,

thì một schema lai có thể phù hợp hơn:

```sql
CREATE TABLE json_lab.business_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    amount numeric(14, 2) NOT NULL
        CHECK (amount >= 0),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object')
);
```

Các trường xác định danh tính, tiền và trạng thái được đặt vào cột có kiểu và constraint rõ. `attributes` dành cho những thuộc tính thay đổi theo từng loại đơn hoặc nhu cầu mở rộng.

Đây thường là cách thiết kế cân bằng: tận dụng cả **ràng buộc quan hệ** lẫn tính linh hoạt của JSONB, thay vì ép tất cả vào một document.

## 19. JSONB không tự thay thế foreign key và ràng buộc quan hệ

Ví dụ một object chứa:

```json
{"customer":{"id":10},"product_id":100}
```

Việc key `product_id` có mặt trong JSONB **không tạo foreign key tự động** từ giá trị đó sang bảng `products`. PostgreSQL không suy ra rằng một đường dẫn JSON phải tồn tại trong một bảng khác chỉ vì hai giá trị có tên giống nhau.

Nếu đây là quan hệ nghiệp vụ quan trọng:

```sql
CREATE TABLE json_lab.customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE json_lab.order_headers (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES json_lab.customers(customer_id),
    extra_attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

Ở thiết kế này, `customer_id` là cột có foreign key; `extra_attributes` không thay thế trách nhiệm của ràng buộc đó.

### 19.1. Mảng object hay bảng con?

Hai cách biểu diễn dòng hàng:

**Trong JSONB:**

```json
{"items":[{"sku":"BOOK-SQL","quantity":2},{"sku":"NOTE-A5","quantity":1}]}
```

**Trong bảng quan hệ:**

```sql
CREATE TABLE json_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES json_lab.order_headers(order_id),
    line_no integer NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
```

Bảng con thuận tiện hơn nếu phải:

- Cập nhật/hủy từng dòng độc lập.
- Bảo đảm unique theo `(order_id, line_no)`.
- JOIN sản phẩm và kiểm tra foreign key.
- Tìm các đơn có một SKU bằng index quan hệ.
- Tổng hợp số lượng bán theo SKU trên toàn hệ thống.

JSONB array có thể phù hợp với một **snapshot payload ít cập nhật**, chẳng hạn cấu trúc phản hồi nhận từ đối tác hoặc dữ liệu đính kèm mang tính mô tả. Không cần tách mọi object nested thành bảng nếu không có lợi ích rõ ràng, nhưng cũng không được xem một document lớn là mô hình thay thế tốt cho mọi quan hệ một-nhiều.

## 20. Generated column kết hợp JSONB

Khi một key JSONB được truy vấn nhiều và có biểu thức đủ điều kiện, có thể cân nhắc **generated column** để trình bày dưới kiểu SQL rõ ràng.

Ví dụ tạo một bảng mới với trường status dẫn xuất từ JSONB:

```sql
CREATE TABLE json_lab.order_documents (
    order_id bigint PRIMARY KEY,
    details jsonb NOT NULL
        CHECK (jsonb_typeof(details) = 'object'),
    status text GENERATED ALWAYS AS
        (details ->> 'status') STORED
);

CREATE INDEX idx_order_documents_status
ON json_lab.order_documents (status);
```

Ứng dụng có thể truy vấn:

```sql
SELECT order_id
FROM json_lab.order_documents
WHERE status = 'paid';
```

Generated column được PostgreSQL duy trì theo biểu thức khai báo; điều này giảm nguy cơ một writer tự cập nhật `details.status` mà quên cập nhật bản sao status độc lập. Tuy nhiên:

- Biểu thức generated có giới hạn về hàm và khả năng tham chiếu theo phiên bản.
- Dùng generated column không tự tạo foreign key cho mọi trường JSON nested.
- Nếu key vắng mặt, giá trị trích xuất có thể là SQL NULL; cần thêm `NOT NULL` hoặc `CHECK` thích hợp nếu nghiệp vụ bắt buộc.
- Trong PostgreSQL 12–17, generated columns được biết đến phổ biến với dạng stored; các major mới có thể bổ sung lựa chọn khác. Hãy xem đúng manual/version khi dùng cú pháp cụ thể.

Nếu key là trường cốt lõi, có thể đơn giản hơn khi lưu nó ở cột quan hệ ngay từ đầu và chỉ để dữ liệu mở rộng trong JSONB.

## 21. Cập nhật đồng thời và nguy cơ ghi đè document

Một vấn đề không riêng JSONB nhưng dễ gặp với document lớn là **read–modify–write tại ứng dụng**.

Giả sử hai dịch vụ cùng đọc:

```json
{"status":"pending","note":"initial"}
```

Sau đó:

- Dịch vụ A thay `status` thành `paid` trong object Java đã tải về.
- Dịch vụ B thay `note` thành `reviewed` trong object Java đã tải về.
- Cả hai ghi lại **toàn bộ document** từ bản đã đọc ban đầu.

Nếu không có chiến lược concurrency, một lần ghi sau có thể xóa thay đổi của lần trước dù hai dịch vụ sửa hai key khác nhau.

### 21.1. Cập nhật phía database trong một câu SQL

Thay vì ghi lại document do client tự dựng từ phiên bản cũ:

```sql
UPDATE json_lab.orders
SET details = jsonb_set(
    details,
    '{status}',
    to_jsonb('paid'::text),
    true
)
WHERE order_id = 1002;
```

Phép cập nhật tính trên giá trị `details` ở phía PostgreSQL và chịu cơ chế khóa hàng phù hợp. Cách này có thể tránh một số tình huống ghi đè cả document theo dữ liệu cũ, nhưng **không giải quyết mọi race nghiệp vụ**: hai writer cùng sửa `status` vẫn cần quy tắc trạng thái hợp lệ, phiên bản hoặc điều kiện `WHERE`.

### 21.2. Optimistic locking bằng version

Một mô hình tổng quát:

```sql
CREATE TABLE json_lab.versioned_documents (
    document_id bigint PRIMARY KEY,
    version_no bigint NOT NULL DEFAULT 0,
    payload jsonb NOT NULL
);
```

Ứng dụng đọc `version_no` rồi chỉ cập nhật nếu version vẫn như lúc đọc:

```sql
UPDATE json_lab.versioned_documents
SET
    payload = jsonb_set(
        payload,
        '{status}',
        to_jsonb('paid'::text),
        true
    ),
    version_no = version_no + 1
WHERE document_id = 1001
  AND version_no = 7;
```

Nếu số hàng cập nhật bằng 0, có thể document không tồn tại hoặc version đã đổi. Ứng dụng nên đọc lại, đánh giá xung đột và retry theo logic nghiệp vụ; không tự tăng version và ghi đè dữ liệu tùy tiện.

**Không coi MVCC là bảo đảm rằng hai bản document được sửa độc lập trên client sẽ tự động merge đúng từng key.**

## 22. Bảo mật: một cột JSONB có thể chứa nhiều loại dữ liệu

Lưu thông tin cá nhân, token hoặc dữ liệu nghiệp vụ vào một JSONB document có thể làm phạm vi truy cập trở nên rộng hơn dự kiến.

Ví dụ:

```json
{
  "customer_name": "Lan",
  "email": "lan@example.test",
  "internal_note": "VIP",
  "payment_reference": "masked-reference"
}
```

Nếu role được cấp `SELECT` trên cả cột `details`, PostgreSQL **không mặc nhiên giới hạn quyền theo từng JSON key**. Người đọc có thể truy xuất các phần tử của document đã được cấp quyền.

Các nguyên tắc:

1. Không nhét credential, token hoặc bí mật vào payload mà nhiều service có quyền đọc nếu không cần thiết.
2. Dùng cột/bảng riêng cho thông tin nhạy cảm khi cần phân quyền khác nhau.
3. Nếu cung cấp dữ liệu đã lọc qua view, kiểm tra quyền trên view, ngữ nghĩa `SECURITY INVOKER/DEFINER` theo major và những đường truy cập khác.
4. Cân nhắc masking/serialization tại ứng dụng trước khi phát JSON qua API hoặc log.
5. Có chính sách retention/xóa dữ liệu cho cả bản gốc và bản dẫn xuất.

### 22.1. SQL injection không mất đi khi dùng JSONB

Hãy tham số hóa câu SQL. Không tạo truy vấn bằng cách nối trực tiếp JSONPath, key hoặc giá trị do người dùng nhập vào một chuỗi SQL không kiểm soát.

Trong ứng dụng Java, dùng `PreparedStatement` hoặc API tham số hóa của ORM/driver. Với các điều kiện JSON cần tạo từ đầu vào, tách rõ **dữ liệu được bind** với **cú pháp SQL và biểu thức JSONPath**; nếu cần tạo JSONPath động, phải xác thực và sử dụng cơ chế API thích hợp.

JSONB là kiểu lưu trữ, không phải lớp phòng chống injection tự động.

## 23. Di chuyển từ json sang jsonb

Một bảng lịch sử có thể đã khai báo cột `payload json`, sau đó phát sinh nhu cầu tìm kiếm theo nhiều key. Có thể cân nhắc chuyển sang `jsonb`:

```sql
-- MINH HỌA trên môi trường kiểm thử:
-- ALTER TABLE json_lab.raw_events
-- ALTER COLUMN payload TYPE jsonb
-- USING payload::jsonb;
```

**Không chạy nguyên lệnh trên production khi chưa đánh giá dữ liệu và kế hoạch migration.** Các rủi ro:

- Biểu diễn khóa object trùng sẽ bị thu gọn theo ngữ nghĩa `jsonb`; khoảng trắng và thứ tự khóa gốc không còn được giữ.
- Một số giá trị `json` có thể không chuyển được sang `jsonb` do giới hạn Unicode hoặc số.
- `ALTER TABLE ... TYPE` có thể cần rewrite bảng, khóa và I/O đáng kể, ảnh hưởng WAL và thời gian dừng/ghi.
- Các view, hàm, index, prepared statements và code Java phụ thuộc kiểu cột có thể cần thay đổi.
- Một truy vấn có hành vi dựa vào văn bản `payload::text` có thể trả biểu diễn khác sau chuyển kiểu.

### 23.1. Phương án di chuyển có kiểm soát

Nếu cần vừa giữ bản gốc vừa tận dụng JSONB:

```sql
ALTER TABLE json_lab.raw_events
ADD COLUMN parsed_payload jsonb;
```

Sau đó:

1. Kiểm kê giá trị không chuyển đổi được, đặc biệt payload từ hệ thống ngoài.
2. Xác định có cần giữ khóa trùng, thứ tự hay biểu diễn văn bản gốc không.
3. Backfill theo batch và kiểm soát concurrency/writer trong thời gian chuyển đổi.
4. Duy trì đường cập nhật mới, kiểm tra dữ liệu giữa hai cột theo **ngữ nghĩa đã thống nhất**.
5. Thử index, query và các client trên kiểu mới.
6. Chỉ thay đổi đường đọc chính sau khi xác minh độ chính xác và tác động hiệu năng.

Đoạn SQL trên chỉ thêm cột; nó không tự xây dựng cơ chế đồng bộ hai cột. Nếu hai cột cần cùng tồn tại, phải thiết kế rõ trigger/application-write/migration job và cách xử lý lỗi chuyển đổi.

### 23.2. Có nên lưu cả json và jsonb lâu dài?

Có thể nếu hai bản có **mục đích khác nhau**, ví dụ:

- `raw_payload json` để audit hình thức JSON đầu vào.
- `parsed_payload jsonb` để lọc và phân tích.

Đổi lại, cần trả chi phí lưu trữ, đồng bộ và backup cho hai bản. Nếu không có yêu cầu giữ nguyên biểu diễn, việc chỉ lưu `jsonb` có thể đơn giản hơn.

## 24. Chọn json, jsonb hay bảng quan hệ?

Một ma trận quyết định theo workload:

| Yêu cầu | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Lưu nguyên hình thức JSON đối tác gửi để đối chiếu/audit | `json`, hoặc lưu bytes gốc riêng nếu cần chuẩn byte-for-byte | `json` giữ nguyên văn bản JSON trong ngữ cảnh lưu trữ; `jsonb` chuẩn hóa biểu diễn. |
| Lọc nhiều bản ghi theo key/value JSON lồng nhau | `jsonb` | Có containment, JSONPath và GIN index. |
| Cấu hình linh hoạt, đọc/ghi cả document, ít đổi cấu trúc | `jsonb` | Thuận tiện thao tác và query mà không phải mở rộng schema cho mọi thuộc tính. |
| Giá trị thường dùng để JOIN, foreign key hoặc UNIQUE | Cột quan hệ | Ràng buộc và index quan hệ trực tiếp, kiểu rõ ràng. |
| Danh sách item cần cập nhật độc lập nhiều lần | Bảng con quan hệ | Khóa, FK, locking và query theo item rõ ràng. |
| Snapshot phản hồi từ dịch vụ ngoài ít truy vấn | `json` hoặc `jsonb` theo nhu cầu giữ nguyên hình thức | Xác định cần audit nguyên văn hay cần tìm kiếm/index. |
| Log/sự kiện khối lượng lớn chỉ lưu rồi chuyển đi | Có thể cân nhắc `json` nhưng vẫn cần đo | Chi phí nhập và yêu cầu bảo toàn đầu vào có thể quan trọng hơn query. |
| Thuộc tính linh hoạt + khóa nghiệp vụ ổn định | Schema lai: cột quan hệ + `jsonb` | Giữ khả năng mở rộng nhưng không đánh đổi những ràng buộc cốt lõi. |
| Cần dùng `@>`, `?` và GIN trên dữ liệu | `jsonb` | Những toán tử/index này được thiết kế cho JSONB. |

### 24.1. Luồng ra quyết định

```text
Dữ liệu cần lưu là JSON?
          |
          v
Có cần giữ nguyên văn bản JSON đầu vào không?
       /               \
      Có               Không
       |                 |
       v                 v
    Ưu tiên json       Có cần lọc/index nhiều key không?
    hoặc raw bytes       /                  \
                        Có                  Không
                         |                    |
                         v                    v
                      Ưu tiên jsonb      JSONB vẫn phù hợp,
                                         nhưng xét thêm workload
                         |
                         v
Có trường khóa, quan hệ, tiền, status ổn định không?
       /                              \
      Có                              Không
       |                                |
       v                                v
Tách cột/bảng quan hệ;                 JSONB document
JSONB cho thuộc tính linh hoạt        có thể đủ
```

Quy trình này là gợi ý khởi đầu, không thay thế đo benchmark, kiểm soát dữ liệu và yêu cầu pháp lý/audit.

## 25. Những nhầm lẫn phổ biến

**1. “json và jsonb khác nhau chỉ ở tên.”** Không. Khác cách lưu, khóa trùng, thứ tự và khoảng trắng, toán tử so sánh, index và hiệu năng.

**2. “jsonb bảo toàn payload để so sánh chữ ký số gốc.”** Không. `jsonb` có thể thay đổi thứ tự khóa, loại khoảng trắng và chỉ giữ giá trị cuối khi khóa trùng. Nếu cần bytes gốc, phải lưu dữ liệu gốc phù hợp.

**3. “json luôn sai vì chậm.”** Không. Nếu chỉ ghi và xuất nguyên dạng, cần giữ bản gốc, `json` có thể phù hợp.

**4. “jsonb luôn nhỏ hơn json.”** Không có quy tắc tuyệt đối; kích thước phụ thuộc nội dung, biểu diễn, TOAST và index.

**5. “jsonb có index nên mọi điều kiện chạy nhanh.”** Không. Index hỗ trợ những operator/predicate nhất định; planner còn xét selectivity và chi phí.

**6. “jsonb_path_ops hỗ trợ ? giống jsonb_ops.”** Không. `jsonb_path_ops` không hỗ trợ nhóm tồn tại key `?`, `?|`, `?&` như operator class mặc định.

**7. “Toán tử ? tìm key ở mọi cấp.”** Không. Nó kiểm tra key hoặc phần tử string **ở cấp trên cùng** của giá trị JSONB được áp dụng.

**8. “@> kiểm tra array đúng cả thứ tự.”** Không. Array containment khác array equality; containment không dùng thứ tự phần tử theo cách equality.

**9. “-> và ->> cho kết quả cùng kiểu.”** Không. `->` trả giá trị JSON; `->>` trả SQL text.

**10. “Không có key và JSON null là một.”** Không. Dùng `?`, `jsonb_typeof` và chú ý SQL NULL để phân biệt.

**11. “jsonb_set chỉ sửa vài byte trong file dữ liệu.”** Không nên giả định vậy. PostgreSQL dùng MVCC, có thể tạo phiên bản tuple mới, cập nhật TOAST/WAL/index.

**12. “Toán tử || deep merge mọi object nested.”** Không. Merge object theo `||` không phải deep merge đệ quy.

**13. “Mọi trường đều bỏ vào JSONB thì không cần schema.”** Không. Dữ liệu cốt lõi vẫn cần kiểu, constraint, FK và chiến lược truy cập rõ ràng.

**14. “Đặt customer_id trong JSON tự có foreign key.”** Không. PostgreSQL không tự suy ra ràng buộc quan hệ từ tên key JSON.

**15. “CHECK với điều kiện ->> luôn bắt key bị thiếu.”** Không. SQL NULL/UNKNOWN có thể làm CHECK thành công; cần kiểm tra tồn tại và kiểu.

**16. “Đổi json sang jsonb chỉ là đổi metadata.”** Không. Có thể phải rewrite bảng, mất biểu diễn nguyên bản và gặp dữ liệu không chuyển được.

**17. “JSONPath nào cũng được GIN index.”** Không. PostgreSQL chỉ có thể dùng index cho những mẫu điều kiện thích hợp theo operator class và khả năng trích xuất.

**18. “Array JSON là giải pháp tốt nhất cho mọi quan hệ một-nhiều.”** Không. Khi phần tử cần khóa, FK, index, update riêng và thống kê lớn, bảng con có thể tốt hơn.

**19. “SELECT quyền trên JSONB chỉ xem được key mà API hiển thị.”** Không. Quyền SQL trên cột JSONB có thể cho phép đọc toàn document; API masking không thay thế permission database.

**20. “Có jsonb nên không cần nghĩ về concurrency.”** Không. Hai client ghi lại cùng document từ hai bản đọc cũ có thể làm mất thay đổi; cần cập nhật phía database hoặc optimistic locking phù hợp.

## 26. Bài tập thực hành

Các bài dưới đây sử dụng schema `json_lab` đã tạo. Hãy thực hiện trên database thực hành; một số đoạn trong phần cập nhật có thể đã thay đổi dữ liệu. Nếu muốn kết quả khớp ví dụ ban đầu, hãy tạo lại dữ liệu thử trong một schema mới hoặc chuẩn bị dữ liệu về trạng thái thích hợp.

### Bài 1. Kiểu nào giữ khóa trùng?

```sql
SELECT
    '{"a":1,"a":2}'::json  AS raw,
    '{"a":1,"a":2}'::jsonb AS parsed;
```

**Câu hỏi:** trường hợp nào còn giữ cả hai cặp key `a` dưới dạng biểu diễn văn bản? Trường hợp nào chỉ có một?

**Đáp án:** `json` giữ văn bản đầu vào chứa hai cặp; `jsonb` chỉ giữ một key `a` với giá trị cuối là `2`.

### Bài 2. Lấy status và tên khách

Viết truy vấn trả `order_id`, `status` dạng text và tên khách từ object lồng nhau.

**Đáp án gợi ý:**

```sql
SELECT
    order_id,
    details ->> 'status' AS status,
    details #>> '{customer,name}' AS customer_name
FROM json_lab.orders
ORDER BY order_id;
```

### Bài 3. Tìm đơn có tag priority

Viết hai cách truy vấn:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"tags":["priority"]}'::jsonb;

SELECT order_id
FROM json_lab.orders
WHERE (details -> 'tags') ? 'priority';
```

**Câu hỏi:** hai cách sẽ thích hợp với những kiểu index nào?

**Gợi ý:** containment `@>` có thể tận dụng GIN trên document với operator class phù hợp. `(details -> 'tags') ? 'priority'` có thể tận dụng GIN expression index trên nhánh `tags`; không mặc định GIN trên toàn document sẽ được dùng cho mọi biểu thức khác dạng.

### Bài 4. Khác nhau giữa JSON null và thiếu key

```sql
SELECT
    order_id,
    details ? 'shipping' AS key_exists,
    jsonb_typeof(details -> 'shipping') AS json_type
FROM json_lab.orders
ORDER BY order_id;
```

**Câu hỏi:** vì sao đơn 1001 và 1002 có thể khác nhau dù `details ->> 'shipping'` của cả hai đều trả SQL NULL?

**Đáp án:** đơn 1001 có key chứa JSON null; đơn 1002 không có key `shipping`. Khi trích xuất text bằng `->>`, cả hai có thể thành SQL NULL nhưng vẫn khác về cấu trúc.

### Bài 5. Lọc phần tử array bằng JSONPath

Tìm những đơn có item với `quantity >= 2`:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @? '$.items[*] ? (@.quantity >= 2)';
```

**Câu hỏi:** vì sao toán tử `?` đơn giản trên document gốc không thay thế trực tiếp điều kiện này?

**Đáp án:** `?` kiểm tra key/phần tử string ở cấp trên cùng, không tự đi vào từng object trong array và so sánh `quantity`.

### Bài 6. Tạo JSON output cho API

Viết truy vấn trả array JSONB chứa `order_id` và `status`, có thứ tự theo ID:

```sql
SELECT jsonb_agg(
    jsonb_build_object(
        'order_id', order_id,
        'status', details ->> 'status'
    )
    ORDER BY order_id
) AS orders_json
FROM json_lab.orders;
```

**Câu hỏi:** nếu bỏ `ORDER BY` bên trong `jsonb_agg`, thứ tự phần tử array có được SQL bảo đảm không?

**Đáp án:** Không. Phải chỉ định thứ tự khi đó là một phần yêu cầu kết quả.

### Bài 7. Chọn loại index

Một bảng có hàng triệu documents; 90% truy vấn là `details @> '{"status":"paid"}'`, 10% truy vấn là `details ? 'shipping'`.

**Yêu cầu:** so sánh `jsonb_ops`, `jsonb_path_ops` và expression index cho `status`.

**Gợi ý:** `jsonb_ops` hỗ trợ cả containment và existence; `jsonb_path_ops` tập trung vào containment nhưng không hỗ trợ `?`; expression B-tree trên `details->>'status'` hữu ích nếu truy vấn được viết theo biểu thức đó. Chọn dựa trên đo latency, index size và write overhead.

### Bài 8. Quyết định lưu payload audit

Một đối tác yêu cầu bạn xuất lại đúng văn bản JSON đã nhận, giữ nguyên thứ tự khóa và khoảng trắng. Hệ thống cũng cần tìm kiếm nhanh theo `event_id`.

**Phương án:** giữ raw JSON/văn bản/bytes theo mức độ chính xác yêu cầu; lưu thêm `event_id` thành cột quan hệ, hoặc một representation `jsonb` để search nếu thật sự cần. Không để bản `jsonb` chuẩn hóa là bản duy nhất nếu phải xuất đúng văn bản đầu vào.

### Bài 9. JSONB hay bảng quan hệ?

Hệ thống có 10 triệu đơn, mỗi đơn chứa nhiều dòng; người dùng thường lọc theo `sku`, cập nhật số lượng từng dòng và JOIN dữ liệu sản phẩm.

**Đánh giá:** bảng `order_items` quan hệ với khóa riêng và index theo `sku`/`order_id` thường là lựa chọn phù hợp hơn nhúng toàn bộ items vào JSONB rồi sửa cả document mỗi lần. Vẫn có thể lưu một snapshot JSONB nếu nghiệp vụ cần xuất payload gốc.

### Bài 10. Chuyển json sang jsonb có mất thông tin không?

Cho payload:

```json
{ "a": 1, "b": 2, "a": 3 }
```

**Câu hỏi:** sau `payload::jsonb`, có thể tái tạo chính xác chuỗi đầu vào với khoảng trắng, thứ tự và khóa trùng không?

**Đáp án:** Không. `jsonb` chuẩn hóa biểu diễn và chỉ giữ giá trị cuối cho key trùng. Nếu việc giữ nguyên đầu vào là yêu cầu, phải lưu bản gốc ở nơi thích hợp.

## 27. Quy trình chọn kiểu dữ liệu cho hệ thống thực tế

Khi thiết kế một cột mới có thể chứa JSON:

1. **Mô tả dữ liệu và vòng đời:** object/array gì, kích thước trung bình/cực đại, do ai gửi, có cần lịch sử hay không.
2. **Phân loại trường cốt lõi:** ID, foreign key, trạng thái, số tiền và ngày tháng có cần index, constraint hoặc JOIN thường xuyên không?
3. **Xác định yêu cầu lưu nguyên bản:** văn bản JSON, duplicate keys hoặc bytes gốc có cần giữ không?
4. **Liệt kê truy vấn:** lọc theo key nào, containment hay range, array search, sort, aggregation; ước tính tần suất.
5. **Chọn biểu diễn:** `json` cho mục tiêu giữ văn bản, `jsonb` cho document cần khai thác, hoặc schema lai/bảng quan hệ cho dữ liệu có cấu trúc ổn định.
6. **Thiết kế ràng buộc:** `NOT NULL`, `CHECK`, giá trị enum hợp lệ, validation dữ liệu lồng nhau; không trông đợi JSON tự enforce domain.
7. **Thiết kế index theo truy vấn:** `jsonb_ops`, `jsonb_path_ops`, expression B-tree hoặc index trên cột quan hệ; tránh index trùng chức năng.
8. **Đo hiệu năng đọc và ghi:** dùng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện, cùng latency update và chi phí WAL/index.
9. **Thiết kế concurrency:** tránh ghi đè document, dùng `jsonb_set`, điều kiện trạng thái, version hoặc transaction phù hợp.
10. **Chuẩn bị vận hành:** quyền truy cập, dữ liệu nhạy cảm, backup, migration, khả năng xuất dữ liệu và cách xử lý trường thiếu hoặc sai kiểu.

Nếu quyết định dùng JSONB, hãy giải thích được **tại sao các thuộc tính đó thuộc cùng một document**, **những đường truy vấn quan trọng là gì** và **ràng buộc nghiệp vụ nào vẫn cần đưa về cột/bảng quan hệ**.

## 28. Tổng kết

Hai kiểu JSON của PostgreSQL phục vụ hai ưu tiên khác nhau:

- **`json`** lưu bản biểu diễn văn bản JSON đầu vào sau khi kiểm tra cú pháp. Nó hữu ích khi cần giữ khoảng trắng, thứ tự khóa hoặc các khóa trùng trong văn bản gốc, nhưng không có hệ toán tử/index JSONB phong phú.
- **`jsonb`** lưu dạng nhị phân đã phân tích cú pháp, chuẩn hóa object và loại bỏ các cặp khóa trùng theo quy tắc giữ giá trị cuối. Nó thuận tiện cho truy vấn lặp lại, containment, existence, JSONPath và GIN index.
- **`->`/`->>`/`#>`/`#>>`** dùng để trích xuất; `@>` và `?` dùng để kiểm tra cấu trúc/khóa; `jsonb_set` và các toán tử khác hỗ trợ tạo giá trị mới khi cập nhật.
- **GIN `jsonb_ops`** linh hoạt cho nhiều toán tử; **`jsonb_path_ops`** phù hợp với những truy vấn containment/JSONPath được hỗ trợ; **B-tree expression index** hữu ích cho một key cố định lọc thường xuyên.
- **JSON null, SQL NULL và key vắng mặt khác nhau**, có ảnh hưởng tới cách truy vấn và viết constraints.
- **JSONB không thay thế schema quan hệ.** Những trường có foreign key, uniqueness, tiền và trạng thái cốt lõi thường nên nằm trong cột/bảng có kiểu rõ ràng; JSONB dành cho phần dữ liệu linh hoạt hoặc snapshot phù hợp.
- **Cập nhật JSONB không miễn phí** và không tự xử lý concurrency, schema evolution, phân quyền hay bảo toàn payload gốc.

Quy tắc lựa chọn ngắn gọn: **nếu chủ yếu cần giữ nguyên hình thức JSON đầu vào, cân nhắc `json` hoặc dữ liệu gốc ở dạng bytes; nếu cần tìm kiếm và thao tác nội dung JSON thường xuyên, ưu tiên `jsonb`; nếu thuộc tính là quan hệ nghiệp vụ cốt lõi, hãy dùng thiết kế quan hệ và chỉ kết hợp JSONB ở phần thật sự linh hoạt.** Sau cùng, hãy kiểm chứng lựa chọn bằng truy vấn và dữ liệu của chính hệ thống thay vì dựa vào tên kiểu dữ liệu.
