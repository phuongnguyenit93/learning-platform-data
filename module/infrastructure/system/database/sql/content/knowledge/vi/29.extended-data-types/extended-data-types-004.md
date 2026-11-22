# Trích xuất giá trị JSON theo kiểu dữ liệu

Một cột JSON có thể lưu nhiều loại thông tin trong cùng một tài liệu:

```json
{
  "order_id": 1001,
  "total": 120.50,
  "paid": true,
  "created_at": "2026-08-01",
  "customer": {"id": 27, "name": "An"},
  "items": [{"sku": "A", "qty": 2, "price": 60.25}],
  "note": null
}
```

Người đọc nhìn thấy `total` là số, `paid` là Boolean, `created_at` trông giống ngày và `items` là mảng. Nhưng khi dùng chúng trong SQL, một câu hỏi rất quan trọng xuất hiện: **kết quả lấy ra có kiểu dữ liệu SQL gì?**

Ví dụ, nếu lấy `total` thành chuỗi `'120.50'` rồi so sánh với `'90'`, phép so sánh chuỗi có thể cho kết quả khác so sánh số. Nếu chuyển một chuỗi `'N/A'` thành `NUMERIC`, câu SQL có thể lỗi. Nếu `note` là JSON `null`, một thao tác trích xuất có thể cho ra **SQL `NULL`** chứ không còn một giá trị JSON riêng.

Bài học **“Trích xuất giá trị JSON theo kiểu dữ liệu”**, thuộc chương **Dữ liệu mở rộng** của module **Database SQL**, hướng dẫn cách lấy dữ liệu JSON và chuyển thành **giá trị SQL có kiểu đúng**, biết cách xử lý dữ liệu thiếu, không đồng nhất và không hợp lệ.

Nội dung sử dụng **PostgreSQL**, tập trung vào `json`/`jsonb`, các toán tử `->`, `->>`, `#>`, `#>>`, `jsonb_typeof`, ép kiểu SQL, truy xuất mảng, chuyển object thành bản ghi và những kỹ thuật xác thực dữ liệu. Một số kỹ thuật có ý tưởng tương đương trong MySQL, SQL Server và Oracle nhưng cú pháp không hoàn toàn giống nhau.

> **Nguyên tắc trung tâm:** JSON có **kiểu bên trong tài liệu**, SQL có **kiểu của biểu thức truy vấn**. Phải xác định cả hai, kiểm tra dữ liệu đầu vào và chỉ chuyển kiểu khi phép chuyển có ý nghĩa.

## 1. Phân biệt kiểu JSON và kiểu SQL

Chuẩn JSON có các loại giá trị cơ bản:

| Loại JSON | Ví dụ | Ý nghĩa |
|---|---|---|
| Object | `{"id": 1}` | Tập cặp khóa–giá trị |
| Array | `[1, 2, 3]` | Danh sách có thứ tự |
| String | `"120.50"` | Chuỗi ký tự, dù nội dung trông giống số |
| Number | `120.50` | Số JSON |
| Boolean | `true`, `false` | Giá trị logic JSON |
| Null | `null` | Giá trị null theo JSON |

JSON **không có kiểu ngày/giờ gốc**. Giá trị `"2026-08-01"` là **JSON string**, không phải JSON date.

SQL lại có các kiểu như:

```text
text / varchar
integer / bigint / numeric
boolean
date / timestamp / timestamptz
json / jsonb
text[] / numeric[]
```

Giả sử:

```sql
SELECT
    '{"total":120.50}'::jsonb -> 'total'  AS json_value,
    '{"total":120.50}'::jsonb ->> 'total' AS text_value;
```

Hai biểu thức có thể hiển thị giống nhau trong SQL client, nhưng kiểu khác nhau:

```text
json_value → jsonb
text_value → text
```

### 1.1. Hai câu hỏi phải hỏi khi trích xuất

1. **Giá trị nguồn là JSON number/string/boolean/object/array/null hay khóa không tồn tại?**
2. **Biểu thức SQL sau khi trích xuất là `jsonb`, `text`, `numeric`, `boolean` hay kiểu khác?**

Việc giá trị nhìn như `120.50` trên màn hình **không chứng minh** nó đang là số SQL.

### 1.2. Mục tiêu chuyển kiểu

```text
JSON number 120.50
    ├─ ->  → jsonb scalar 120.50
    └─ ->> → text '120.50' → ::numeric → numeric 120.50

JSON string "120.50"
    ├─ ->  → jsonb string "120.50"
    └─ ->> → text '120.50' → ::numeric → numeric 120.50

JSON string "N/A"
    └─ ->> → text 'N/A' → ::numeric → LỖI chuyển kiểu
```

**Được phép chuyển kiểu** không đồng nghĩa **nên chấp nhận dữ liệu**. Một API yêu cầu `total` là JSON number có thể cần từ chối `"120.50"` dù PostgreSQL chuyển chuỗi đó sang số thành công.

## 2. `json` và `jsonb` trong PostgreSQL

PostgreSQL có hai kiểu lưu tài liệu JSON:

- **`json`:** lưu biểu diễn văn bản JSON đã qua kiểm tra cú pháp. Cách trình bày, thứ tự khóa và các khóa lặp trong văn bản có thể còn được bảo toàn ở mức lưu trữ.
- **`jsonb`:** lưu biểu diễn nhị phân đã phân tích, phù hợp cho nhiều phép truy vấn, so sánh, chứa (`@>`) và chỉ mục GIN. `jsonb` không bảo toàn cùng cách trình bày văn bản/khóa lặp ban đầu.

Ví dụ:

```sql
SELECT
    pg_typeof('{"a":1}'::json) AS json_sql_type,
    pg_typeof('{"a":1}'::jsonb) AS jsonb_sql_type;
```

### 2.1. Khi nào chọn `jsonb`?

Với dữ liệu ứng dụng cần lọc theo khóa, truy cập đường dẫn lồng nhau, dùng containment hoặc xây index, `jsonb` thường là lựa chọn thực tế.

Nhưng nếu bài toán phải giữ **nguyên biểu diễn văn bản** như một payload phục vụ đối soát chữ ký, lưu log thô hoặc cần xem thông tin khóa trùng ban đầu, không được giả định `jsonb` giữ nguyên mọi ký tự và thứ tự.

### 2.2. Không nhầm `jsonb` với schema đã được kiểm soát

Một cột `jsonb` có thể lưu:

```json
{"total": 120.50}
```

và:

```json
{"total": "N/A"}
```

trong hai dòng khác nhau, nếu không có ràng buộc bổ sung. `jsonb` xác nhận cấu trúc **JSON hợp lệ**, nhưng không tự bảo đảm các khóa bên trong tuân thủ **hợp đồng kiểu dữ liệu của ứng dụng**.

### 2.3. Khi nào dùng cột SQL có kiểu cố định?

Nếu `total_amount` là trường bắt buộc, thường xuyên dùng để tính tiền, truy vấn theo khoảng và cần ràng buộc chính xác, một cột SQL kiểu `NUMERIC(12,2)` có thể thích hợp hơn để **chứa giá trị chuẩn hóa**.

JSON có ích cho dữ liệu linh hoạt hoặc thuộc tính mở rộng, nhưng không buộc mọi trường cốt lõi phải được truy cập qua JSON mãi mãi.

## 3. Toán tử trích xuất: `->`, `->>`, `#>`, `#>>`

Bốn toán tử được sử dụng thường xuyên trong PostgreSQL:

| Toán tử | Mục đích | Kiểu SQL kết quả với `jsonb` |
|---|---|---|
| `doc -> 'key'` | Lấy giá trị tại khóa của object | `jsonb` |
| `doc -> 0` | Lấy phần tử mảng ở vị trí 0 | `jsonb` |
| `doc ->> 'key'` | Lấy giá trị khóa ở dạng văn bản | `text` |
| `doc ->> 0` | Lấy phần tử mảng ở dạng văn bản | `text` |
| `doc #> '{a,b}'` | Lấy giá trị theo đường dẫn nhiều cấp | `jsonb` |
| `doc #>> '{a,b}'` | Lấy giá trị theo đường dẫn nhiều cấp thành text | `text` |

`#>` và `#>>` sử dụng **đường dẫn kiểu `text[]`**; dạng `'{a,b}'` là cú pháp literal mảng PostgreSQL.

### 3.1. Ví dụ cơ bản

```sql
SELECT
    '{"id":101,"name":"An","vip":true}'::jsonb -> 'id'
        AS id_json,
    '{"id":101,"name":"An","vip":true}'::jsonb ->> 'id'
        AS id_text,
    '{"id":101,"name":"An","vip":true}'::jsonb -> 'vip'
        AS vip_json,
    '{"id":101,"name":"An","vip":true}'::jsonb ->> 'vip'
        AS vip_text;
```

Các dạng hiển thị:

```text
id_json  → 101   (jsonb)
id_text  → '101' (text)
vip_json → true  (jsonb)
vip_text → 'true' (text)
```

### 3.2. Kiểm tra kiểu bằng `pg_typeof`

```sql
SELECT
    pg_typeof(('{"x":12}'::jsonb -> 'x')) AS with_arrow,
    pg_typeof(('{"x":12}'::jsonb ->> 'x')) AS with_double_arrow,
    pg_typeof((('{"x":12}'::jsonb ->> 'x')::integer))
        AS after_cast;
```

Kết quả:

```text
with_arrow       jsonb
with_double_arrow text
after_cast       integer
```

### 3.3. Khi nào dùng toán tử nào?

**Cần truy cập tiếp object hoặc array?** Giữ kiểu JSON bằng `->`/`#>`.

**Cần hiển thị chuỗi?** Dùng `->>`/`#>>`.

**Cần so sánh số, cộng tiền, lọc ngày hoặc xử lý Boolean theo kiểu SQL?** Trích xuất rồi **chuyển kiểu có kiểm soát**.

Không cố `SUM(doc ->> 'total')`: kết quả toán tử `->>` là text, còn `SUM(text)` không phải phép cộng số hợp lệ của PostgreSQL.

## 4. Dữ liệu thực hành: JSON hợp lệ nhưng kiểu không đồng nhất

Ta tạo bảng tạm để mọi ví dụ không đụng bảng sản xuất:

```sql
CREATE TEMP TABLE json_lab_events (
    event_id INTEGER PRIMARY KEY,
    payload JSONB NOT NULL
);
```

Nạp dữ liệu. Cố ý có những giá trị **hợp lệ về JSON nhưng sai hợp đồng nghiệp vụ** để học cách chuyển kiểu an toàn.

```sql
INSERT INTO json_lab_events (event_id, payload)
VALUES
(1, '{
  "event_type":"checkout",
  "user":{"id":101,"name":"An","vip":true},
  "order":{
    "total":120.50,"currency":"VND",
    "created_at":"2026-08-01","paid":true,
    "items":[
      {"sku":"A","qty":2,"unit_price":30.25},
      {"sku":"B","qty":1,"unit_price":60.00}
    ]
  },
  "tags":["web","promo"]
}'::jsonb),
(2, '{
  "event_type":"checkout",
  "user":{"id":"102","name":"Binh","vip":"false"},
  "order":{
    "total":"80.00","currency":"VND",
    "created_at":"2026-08-02","paid":"true",
    "items":[{"sku":"C","qty":"4","unit_price":"20"}]
  },
  "tags":["app"]
}'::jsonb),
(3, '{
  "event_type":"checkout",
  "user":{"id":103,"vip":null},
  "order":{"total":null,"created_at":null,"paid":false,"items":[]},
  "tags":[]
}'::jsonb),
(4, '{
  "event_type":"checkout",
  "user":{"id":"104a","name":"Chi"},
  "order":{
    "total":"N/A","created_at":"2026-02-30",
    "paid":"unknown",
    "items":[{"sku":"D","qty":"two","unit_price":15.5}]
  }
}'::jsonb),
(5, '{
  "event_type":"checkout",
  "order":{"total":0,"created_at":"2026-08-04","paid":false}
}'::jsonb),
(6, '{
  "event_type":"checkout",
  "order":{
    "total":-10.25,"created_at":"2026-08-05",
    "paid":false,"items":null
  }
}'::jsonb),
(7, '{
  "event_type":"visit",
  "user":{"id":105},
  "context":{"page":"home"}
}'::jsonb),
(8, '{
  "event_type":"checkout",
  "user":{"id":106},
  "order":{
    "total":" 42.75 ","created_at":"2026-08-07",
    "paid":true,
    "items":[{"sku":"E","qty":1,"unit_price":42.75}]
  },
  "tags":"web"
}'::jsonb),
(9, '{
  "event_type":"checkout",
  "user":{"id":107},
  "order":{
    "total":"1e3","created_at":"2026-08-08",
    "paid":true,
    "items":[{"sku":"F","qty":1,"unit_price":1000}]
  },
  "tags":["api",null]
}'::jsonb),
(10, '{
  "event_type":"checkout",
  "user":{"id":108},
  "order":{
    "total":true,"created_at":"2026-08-09",
    "paid":true,"items":{}
  }
}'::jsonb),
(11, '{
  "event_type":"checkout",
  "user":{"id":109},
  "order":{
    "total":"12,50","created_at":"08/10/2026","paid":true
  }
}'::jsonb),
(12, '{
  "event_type":"checkout",
  "user":{"id":110},
  "order":{"total":null,"created_at":"","paid":null,"items":[]}
}'::jsonb),
(13, '{
  "event_type":"checkout",
  "user":null,
  "order":{"total":25,"created_at":"2026-08-12","paid":true}
}'::jsonb),
(14, '{
  "event_type":"checkout",
  "user":{"id":111},
  "order":{
    "total":15.5,"created_at":"2026-08-13",
    "paid":true,
    "items":[{"sku":"G","qty":1,"unit_price":15.5}]
  },
  "metadata":{"channel":"app","priority":2}
}'::jsonb),
(15, '{
  "event_type":"checkout",
  "user":{"id":"999999999999999999999"},
  "order":{
    "total":"99999999999999.99",
    "created_at":"2026-08-14","paid":true,"items":[]
  }
}'::jsonb);
```

### 4.1. Đọc toàn bộ payload của một dòng

```sql
SELECT event_id, payload
FROM json_lab_events
WHERE event_id = 1;
```

Cột `payload` trả về dữ liệu `jsonb`, không phải các cột SQL đã tách sẵn.

### 4.2. Các kiểu dữ liệu được cố ý trộn

| `event_id` | `order.total` | Kiểu JSON | Ghi chú |
|---:|---|---|---|
| 1 | `120.50` | number | Hợp lệ để tính số |
| 2 | `"80.00"` | string | Chuỗi số, phải quyết định có chấp nhận không |
| 3 | `null` | null | JSON null |
| 4 | `"N/A"` | string | Không phải số |
| 5 | `0` | number | Số 0 hợp lệ |
| 6 | `-10.25` | number | Chuyển kiểu được, nhưng có thể vi phạm quy tắc “tiền không âm” |
| 7 | Không có `order` | — | Đường dẫn không tồn tại |
| 8 | `" 42.75 "` | string | Có khoảng trắng |
| 9 | `"1e3"` | string | Dạng khoa học, số 1000 nếu cho phép chuyển |
| 10 | `true` | boolean | Không phải tiền |
| 11 | `"12,50"` | string | Dấu phẩy không phải định dạng số PostgreSQL mặc định |
| 12 | `null` | null | JSON null |
| 13 | `25` | number | Hợp lệ |
| 14 | `15.5` | number | Hợp lệ |
| 15 | `"99999999999999.99"` | string | Có thể ép sang `numeric`, nhưng **vượt** `numeric(12,2)` |

Mục tiêu là không viết một phép cast mù quáng áp dụng lên mọi dòng.

## 5. Trích xuất khóa ở cấp cao nhất

```sql
SELECT
    event_id,
    payload -> 'event_type'  AS event_type_json,
    payload ->> 'event_type' AS event_type_text
FROM json_lab_events
ORDER BY event_id;
```

`payload -> 'event_type'` là `jsonb` chứa JSON string, ví dụ `"checkout"`. `payload ->> 'event_type'` là text SQL `checkout`.

Khi so sánh với literal SQL:

```sql
SELECT event_id
FROM json_lab_events
WHERE payload ->> 'event_type' = 'visit';
-- event_id = 7.
```

### 5.1. Phân biệt literal SQL và JSON

```sql
payload ->> 'event_type' = 'checkout'
```

so sánh **text** với **text**.

```sql
payload -> 'event_type' = '"checkout"'::jsonb
```

so sánh **jsonb scalar** với **jsonb scalar**.

Hai cách có thể cùng tìm được dòng, nhưng có hợp đồng kiểu khác nhau. Khi cần kết hợp các phép logic theo cấu trúc JSON, giữ `jsonb`; khi chỉ cần chuỗi, dùng `->>`.

### 5.2. Trích xuất sai khóa

```sql
SELECT
    payload ->> 'event_typo' AS missing_key
FROM json_lab_events
WHERE event_id = 1;
```

Kết quả là **SQL `NULL`**, không phải lỗi cú pháp và không phải chuỗi `'null'`. Điều này khiến lỗi đánh máy tên khóa dễ bị bỏ qua nếu truy vấn không kiểm tra dữ liệu.

## 6. Truy xuất object lồng nhau bằng `->` và `#>>`

Từ dữ liệu:

```json
{
  "user": {"id": 101, "name": "An"},
  "order": {"total": 120.50}
}
```

ta có thể viết:

```sql
SELECT
    event_id,
    payload -> 'user' -> 'id'      AS user_id_json,
    payload -> 'user' ->> 'id'     AS user_id_text,
    payload #> '{user,id}'        AS id_by_path_json,
    payload #>> '{user,id}'       AS id_by_path_text,
    payload #>> '{order,total}'   AS total_text
FROM json_lab_events
WHERE event_id = 1;
```

### 6.1. Hai cách tương đương về mục đích lấy text

```sql
payload -> 'user' ->> 'id'
```

và:

```sql
payload #>> '{user,id}'
```

đều lấy giá trị `user.id` ở dạng text khi cấu trúc phù hợp.

### 6.2. Vì sao không dùng `->>` quá sớm?

Sai kiểu:

```sql
-- Minh họa sai, không dùng:
payload ->> 'user' ->> 'id'
```

Phép `payload ->> 'user'` trả **text**, nên phía sau không còn đối tượng JSONB để áp tiếp toán tử `->>` theo ngữ nghĩa JSON.

Đúng:

```sql
payload -> 'user' ->> 'id'
```

hoặc:

```sql
payload #>> '{user,id}'
```

**Quy tắc:** Giữ `jsonb` ở các bước trung gian, chỉ lấy thành text hoặc ép kiểu tại bước cuối.

### 6.3. Đường dẫn có phần tử mảng

```sql
SELECT
    payload #>> '{order,items,0,sku}' AS first_sku,
    payload #>> '{order,items,0,qty}' AS first_qty_text
FROM json_lab_events
WHERE event_id = 1;
-- first_sku='A', first_qty_text='2'.
```

Phần tử `"0"` trong đường dẫn được hiểu như vị trí đầu tiên của mảng khi đường dẫn đi vào một JSON array. Vị trí mảng JSON/PostgreSQL ở đây bắt đầu từ **0**.

## 7. Phân biệt giá trị JSON bằng `jsonb_typeof`

Với `jsonb`, hàm:

```sql
jsonb_typeof(jsonb_value)
```

trả về **text** mô tả kiểu JSON: `object`, `array`, `string`, `number`, `boolean`, `null`.

```sql
SELECT
    event_id,
    jsonb_typeof(payload #> '{order,total}') AS total_json_type,
    payload #>> '{order,total}' AS total_as_text
FROM json_lab_events
ORDER BY event_id;
```

Một số kết quả dự kiến:

| event_id | `total_json_type` | `total_as_text` |
|---:|---|---|
| 1 | `number` | `120.50` |
| 2 | `string` | `80.00` |
| 3 | `null` | SQL `NULL` |
| 4 | `string` | `N/A` |
| 5 | `number` | `0` |
| 7 | SQL `NULL` | SQL `NULL` |
| 10 | `boolean` | `true` |

### 7.1. `jsonb_typeof` không phải `pg_typeof`

```sql
SELECT
    jsonb_typeof('120.50'::jsonb) AS json_type,
    pg_typeof('120.50'::jsonb) AS sql_type;
```

`jsonb_typeof` trả `number` — kiểu **giá trị bên trong JSON**. `pg_typeof` trả `jsonb` — kiểu **biểu thức SQL**.

### 7.2. Giá trị khóa không tồn tại

Nếu đường dẫn không tìm thấy:

```sql
jsonb_typeof(payload -> 'missing_key')
```

trả **SQL `NULL`**, không phải chữ `null`.

### 7.3. JSON null

```sql
SELECT jsonb_typeof('null'::jsonb);
-- text 'null'.
```

JSON null là một **giá trị JSON có thật**, còn SQL `NULL` nói rằng biểu thức SQL không có giá trị. Sự khác biệt này quyết định cách kiểm tra trường thiếu và trường có null.

## 8. Bốn tình huống khác nhau: thiếu, JSON null, chuỗi rỗng và số 0

Hãy đặt cạnh nhau:

```json
{}
```

```json
{"value": null}
```

```json
{"value": ""}
```

```json
{"value": 0}
```

Chúng **không đồng nghĩa**.

### 8.1. Bảng kết quả

| JSON gốc | `doc ? 'value'` | `jsonb_typeof(doc -> 'value')` | `doc ->> 'value'` |
|---|---|---|---|
| `{}` | `false` | SQL `NULL` | SQL `NULL` |
| `{"value":null}` | `true` | text `'null'` | SQL `NULL` |
| `{"value":""}` | `true` | text `'string'` | text rỗng `''` |
| `{"value":0}` | `true` | text `'number'` | text `'0'` |

### 8.2. Ví dụ chạy trực tiếp

```sql
WITH examples(doc) AS (
    VALUES
      ('{}'::jsonb),
      ('{"value":null}'::jsonb),
      ('{"value":""}'::jsonb),
      ('{"value":0}'::jsonb)
)
SELECT
    doc,
    doc ? 'value' AS has_key,
    jsonb_typeof(doc -> 'value') AS json_type,
    doc ->> 'value' AS extracted_text
FROM examples;
```

### 8.3. Khi nào dùng `?`

Với một `jsonb` object:

```sql
payload ? 'order'
```

kiểm tra sự tồn tại của khóa `order` **ở cấp ngoài cùng**. Nó không tự tìm khóa `total` ở mọi tầng.

Muốn kiểm tra `total` trong `order`, dùng:

```sql
(payload -> 'order') ? 'total'
```

khi `payload -> 'order'` thực sự là object, hoặc dùng điều kiện kiểm tra kiểu kết hợp. Toán tử `?` cũng có ngữ nghĩa với string element cấp cao nhất của JSON array; không coi nó là phép dò đệ quy.

### 8.4. JSON null và SQL NULL khi `->`

```sql
SELECT
    '{"x":null}'::jsonb -> 'x' AS json_null,
    '{}'::jsonb -> 'x' AS missing_value;
```

Biểu thức đầu là **JSONB null**; biểu thức sau là **SQL NULL**. Khi dùng `->>`, cả hai thường thành SQL NULL. Nếu cần phân biệt chúng trong phân tích dữ liệu, kiểm tra **trước khi đổi thành text**.

### 8.5. Đừng biến thiếu dữ liệu thành 0 một cách tùy tiện

```sql
COALESCE((payload #>> '{order,total}')::numeric, 0)
```

có thể:

- Không phù hợp nếu `total` chưa được gửi.
- Che lỗi thu thập dữ liệu.
- Đồng nhất JSON null, khóa thiếu và một số trường hợp khác với giá trị **0 có thật**.
- Vẫn **lỗi** trên chuỗi `'N/A'` trước khi `COALESCE` có cơ hội áp dụng.

Chỉ dùng `COALESCE(..., 0)` khi nghiệp vụ thực sự định nghĩa “không có giá trị” là 0 và dữ liệu đã được kiểm tra hợp lệ.

## 9. Lấy JSON number thành SQL `NUMERIC`

Một nhu cầu thường gặp:

```sql
SELECT
    event_id,
    (payload #>> '{order,total}')::numeric AS total_amount
FROM json_lab_events
WHERE event_id IN (1, 2, 5, 6, 8, 9, 13, 14)
ORDER BY event_id;
```

Các dòng được chọn đều có giá trị chuyển được sang số, bao gồm một số **chuỗi biểu diễn số**.

| event_id | Văn bản trích xuất | Kết quả `::numeric` |
|---:|---|---:|
| 1 | `120.50` | `120.50` |
| 2 | `80.00` | `80.00` |
| 5 | `0` | `0` |
| 6 | `-10.25` | `-10.25` |
| 8 | ` 42.75 ` | `42.75` |
| 9 | `1e3` | `1000` |
| 13 | `25` | `25` |
| 14 | `15.5` | `15.5` |

### 9.1. Dấu ngoặc là một thói quen tốt

```sql
(payload #>> '{order,total}')::numeric
```

giúp làm rõ rằng **kết quả trích xuất text** được cast thành numeric.

### 9.2. Tại sao `NUMERIC` phù hợp với tiền?

`NUMERIC` hỗ trợ tính toán thập phân chính xác theo phạm vi và độ chính xác được cấu hình, tránh nhiều bất ngờ thường gặp khi dùng các kiểu số dấu phẩy động cho tiền.

Tuy nhiên `NUMERIC` không tự quyết định:

- Có cho phép tổng âm không?
- Đơn vị tiền là gì?
- Có cần đúng hai chữ số thập phân không?
- Có cần quy tắc làm tròn cụ thể không?

Những điều đó thuộc về **hợp đồng dữ liệu/nghiệp vụ**.

### 9.3. Dữ liệu lỗi sẽ làm câu truy vấn thất bại

Nếu chạy trực tiếp:

```sql
-- KHÔNG chạy trên toàn dữ liệu mẫu nếu chưa xử lý giá trị sai:
-- SELECT (payload #>> '{order,total}')::numeric
-- FROM json_lab_events;
```

PostgreSQL có thể gặp `'N/A'`, `'true'` hoặc `'12,50'` và báo **invalid input syntax for type numeric**.

**Một dòng xấu có thể khiến cả câu truy vấn thất bại**, kể cả khi những dòng khác có số hợp lệ.

### 9.4. Không so sánh số dưới dạng text

```sql
SELECT
    '100' > '9' AS text_comparison,
    100::numeric > 9::numeric AS numeric_comparison;
```

Trong phép so sánh text theo thứ tự ký tự/collation thích hợp, `'100'` không được hiểu là số 100; kết quả có thể trái với so sánh numeric. Đừng dùng:

```sql
WHERE payload #>> '{order,total}' > '90'
```

để thay cho một điều kiện **số lớn hơn 90**.

## 10. `INTEGER`, `BIGINT` và giới hạn miền giá trị

`user.id` trong JSON có thể là:

```json
{"id":101}
```

hoặc:

```json
{"id":"102"}
```

Cả hai có thể được lấy thành text rồi cast:

```sql
SELECT
    event_id,
    (payload #>> '{user,id}')::integer AS user_id
FROM json_lab_events
WHERE event_id IN (1, 2, 3, 8, 9, 14)
ORDER BY event_id;
```

### 10.1. Không phải mọi chuỗi số đều là integer

Các đầu vào có thể lỗi:

```text
"104a"                 → sai cú pháp số nguyên
"12.5"                 → không phải integer literal
"999999999999999999999" → vượt phạm vi integer/bigint
```

Phải xác thực cả **cú pháp** và **phạm vi**.

### 10.2. Đừng chuyển số có thập phân thành integer để “cho tiện”

`total` là tiền nên:

```sql
(payload #>> '{order,total}')::numeric
```

khác với:

```sql
(payload #>> '{order,total}')::integer
```

Ép kiểu từ một giá trị số thập phân sang số nguyên có thể có quy tắc làm tròn/chuyển đổi không phù hợp với nghiệp vụ; không dùng integer để tính tiền chỉ vì SQL cho phép ép kiểu trong một số trường hợp.

### 10.3. Số lớn và `NUMERIC(p,s)`

Một chuỗi như:

```text
99999999999999.99
```

có thể chuyển thành `numeric` không giới hạn precision tương ứng nhưng **không vừa** `numeric(12,2)` vì kiểu đó chỉ cho phép tối đa mười chữ số trước dấu thập phân.

```sql
-- Có thể thành công:
SELECT '99999999999999.99'::numeric;

-- Có thể báo numeric field overflow:
-- SELECT '99999999999999.99'::numeric(12,2);
```

Kiểm tra chuỗi “có phải số” **chưa đủ** để xác nhận nó phù hợp với kiểu đích và ràng buộc nghiệp vụ.

## 11. Boolean: không nhầm JSON boolean với string

Dữ liệu:

```json
{"paid": true}
```

khác về kiểu JSON với:

```json
{"paid": "true"}
```

Dù `->>` đều có thể hiển thị `true`:

```sql
SELECT
    event_id,
    jsonb_typeof(payload #> '{order,paid}') AS json_kind,
    payload #>> '{order,paid}' AS paid_text
FROM json_lab_events
WHERE event_id IN (1, 2, 3, 4, 5, 12)
ORDER BY event_id;
```

### 11.1. Cast khi nguồn đúng cú pháp

```sql
SELECT
    event_id,
    (payload #>> '{order,paid}')::boolean AS paid
FROM json_lab_events
WHERE event_id IN (1, 2, 3, 5, 8, 9, 14)
ORDER BY event_id;
```

PostgreSQL có khả năng nhận các chuỗi Boolean trong những dạng cú pháp được hỗ trợ. Nhưng ứng dụng có thể cần **hợp đồng chặt hơn**: chỉ chấp nhận JSON boolean `true`/`false`, không chấp nhận text `"true"`.

### 11.2. Chỉ chấp nhận JSON boolean

```sql
SELECT
    event_id,
    CASE
        WHEN jsonb_typeof(payload #> '{order,paid}') = 'boolean'
        THEN (payload #>> '{order,paid}')::boolean
        ELSE NULL::boolean
    END AS paid_strict
FROM json_lab_events
ORDER BY event_id;
```

`event_id=1` trả `true`, `event_id=5` trả `false`. `event_id=2` có JSON string `"true"` nên trả SQL NULL theo **chính sách strict**.

### 11.3. Nếu phải chấp nhận chuỗi `true`/`false`

```sql
SELECT
    event_id,
    CASE
        WHEN jsonb_typeof(payload #> '{order,paid}') = 'boolean'
        THEN (payload #>> '{order,paid}')::boolean

        WHEN jsonb_typeof(payload #> '{order,paid}') = 'string'
         AND LOWER(BTRIM(payload #>> '{order,paid}'))
             IN ('true', 'false')
        THEN LOWER(BTRIM(payload #>> '{order,paid}'))::boolean

        ELSE NULL::boolean
    END AS paid_normalized
FROM json_lab_events
ORDER BY event_id;
```

Ở đây chỉ nhận hai chuỗi đã được **whitelist**. Không tự dùng mọi dạng PostgreSQL có thể nhận (`yes`, `on`, `1`...) nếu API định nghĩa chỉ chấp nhận `true` và `false`.

### 11.4. Không dùng sự thật/giả của SQL để đoán sự tồn tại

```sql
WHERE (payload #>> '{order,paid}')::boolean
```

không diễn tả chính xác việc “khóa `paid` có tồn tại hay không”. Nếu giá trị là `false`, câu `WHERE` loại dòng; nếu `NULL`, `WHERE` cũng không giữ dòng. Đó là logic lọc theo **giá trị**, khác với kiểm tra sự tồn tại của key.

## 12. Ngày tháng: JSON chỉ có string, SQL có `DATE`

Trong JSON:

```json
{"created_at":"2026-08-01"}
```

`created_at` là **JSON string**. Khi muốn so sánh theo ngày SQL:

```sql
SELECT
    event_id,
    (payload #>> '{order,created_at}')::date AS created_date
FROM json_lab_events
WHERE event_id IN (1, 2, 5, 6, 8, 9, 10, 13, 14)
ORDER BY event_id;
```

### 12.1. Những dữ liệu có thể gây lỗi

- `"2026-02-30"`: ngày 30/2 không tồn tại.
- `""`: chuỗi rỗng không phải một ngày.
- `"08/10/2026"`: phụ thuộc cách phân tích ngày của môi trường, dễ mơ hồ giữa tháng/ngày và ngày/tháng.
- JSON `null` hoặc khóa thiếu: sau `#>>` là SQL NULL, khi cast `NULL::date` vẫn là SQL NULL.

### 12.2. Ưu tiên hợp đồng ISO 8601 không mơ hồ

Với trường ngày đơn giản, một hợp đồng có thể là:

```text
YYYY-MM-DD
```

Ví dụ `2026-08-01`. Nếu nguồn dùng định dạng khác, hãy chuẩn hóa tại **tầng ingestion/validation** thay vì để mỗi báo cáo tự đoán.

### 12.3. Kiểu `DATE` không giữ giờ hoặc múi giờ

Nếu nguồn thực ra là timestamp:

```json
{"created_at":"2026-08-01T23:30:00+07:00"}
```

thì cast thẳng thành `date` có thể làm mất thông tin về giờ/múi giờ, và ngày theo UTC có thể khác ngày theo Việt Nam. Hãy xác định **ý nghĩa thời điểm** trước khi chọn kiểu SQL đích.

## 13. Timestamp và múi giờ: `TIMESTAMP` khác `TIMESTAMPTZ`

Trong PostgreSQL:

- `timestamp without time zone`: biểu diễn ngày–giờ **không gắn thông tin múi giờ**.
- `timestamp with time zone` (`timestamptz`): biểu diễn **thời điểm tuyệt đối**, input có offset được chuẩn hóa nội bộ; cách hiển thị phụ thuộc múi giờ session.

### 13.1. Nếu JSON có offset

```sql
SELECT
    ('2026-08-01T23:30:00+07:00')::timestamptz
        AS event_instant;
```

Muốn lấy ngày theo Việt Nam:

```sql
SELECT
    (
      ('2026-08-01T23:30:00+07:00')::timestamptz
      AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS local_date;
```

### 13.2. Lưu timestamp trong JSON rồi trích ra

```sql
SELECT
    (
      '{"occurred_at":"2026-08-01T23:30:00+07:00"}'::jsonb
      ->> 'occurred_at'
    )::timestamptz AS occurred_at;
```

Nếu nguồn không có offset (`"2026-08-01T23:30:00"`), database có thể phải diễn giải theo múi giờ session khi cast sang `timestamptz`. Điều đó cần được xác định bằng hợp đồng API, không mặc định mọi server dùng UTC.

### 13.3. Unix timestamp dạng giây và mili-giây

Một API có thể gửi:

```json
{"occurred_at_ms": 1785605400000}
```

Nếu hợp đồng nói đơn vị là **mili-giây từ epoch**, có thể dùng:

```sql
SELECT
    TO_TIMESTAMP(
        ('{"occurred_at_ms":1785605400000}'::jsonb
         ->> 'occurred_at_ms')::double precision / 1000.0
    ) AS occurred_at;
```

`to_timestamp(double precision)` trong PostgreSQL nhận số **giây** kể từ Unix epoch. Nếu quên chia `1000`, thời gian sẽ sai nghiêm trọng hoặc ra ngoài phạm vi cho phép.

Với timestamp cần độ chính xác dưới mili-giây/những dải cực trị, cân nhắc giới hạn của chuyển sang `double precision` và yêu cầu độ chính xác thực tế.

### 13.4. Không định dạng ngày quá sớm

```sql
TO_CHAR(created_at, 'DD/MM/YYYY')
```

trả về **text để hiển thị**, không phải kiểu `date`. Nếu định dạng trước rồi dùng kết quả để `ORDER BY`, có thể tạo thứ tự chuỗi thay vì thứ tự thời gian.

Nên lưu và tính toán ở kiểu `date`/`timestamptz`, chỉ định dạng ở tầng cuối.

## 14. Chuyển kiểu thất bại: phải xác thực trước

Một API thường gửi dữ liệu không đồng nhất theo thời gian. Có thể không biết trước liệu `total` là số, chuỗi số, chuỗi `"N/A"` hay Boolean.

Không nên:

```sql
SELECT (payload #>> '{order,total}')::numeric
FROM json_lab_events;
```

trên toàn bảng mẫu vì một giá trị lỗi có thể làm thất bại toàn query.

### 14.1. Xác thực theo kiểu JSON

Nếu API chỉ chấp nhận **JSON number**:

```sql
SELECT
    event_id,
    CASE
        WHEN jsonb_typeof(payload #> '{order,total}') = 'number'
        THEN (payload #>> '{order,total}')::numeric
        ELSE NULL::numeric
    END AS total_strict
FROM json_lab_events
ORDER BY event_id;
```

Query không cố cast JSON string hoặc Boolean. Trên dữ liệu mẫu, các dòng số JSON gồm `1`, `5`, `6`, `13`, `14`.

**Cần thêm quy tắc nghiệp vụ:** nếu total phải không âm, `-10.25` của dòng 6 dù là JSON number vẫn không hợp lệ.

### 14.2. Phân loại thay vì chỉ trả NULL

```sql
SELECT
    event_id,
    CASE
        WHEN payload -> 'order' IS NULL THEN 'MISSING_ORDER'
        WHEN (payload -> 'order') IS NOT NULL
         AND jsonb_typeof(payload -> 'order') <> 'object'
            THEN 'BAD_ORDER_SHAPE'
        WHEN (payload -> 'order') ? 'total' IS NOT TRUE
            THEN 'MISSING_TOTAL'
        WHEN jsonb_typeof(payload #> '{order,total}') = 'null'
            THEN 'NULL_TOTAL'
        WHEN jsonb_typeof(payload #> '{order,total}') = 'number'
            THEN 'NUMBER_TOTAL'
        WHEN jsonb_typeof(payload #> '{order,total}') = 'string'
            THEN 'STRING_TOTAL'
        ELSE 'OTHER_TYPE'
    END AS total_category
FROM json_lab_events
ORDER BY event_id;
```

Mục tiêu là giữ thông tin **vì sao** không có số, thay vì biến tất cả thành một SQL NULL không thể giải thích.

### 14.3. Dữ liệu thiếu không nhất thiết là dữ liệu lỗi

`event_id=7` là sự kiện `visit`, không phải đơn hàng, nên không có `order.total` có thể **hoàn toàn hợp lệ**. Trước khi xác thực `order.total`, phải xét `event_type` và hợp đồng của từng loại sự kiện.

Một schema linh hoạt nhưng có nhiều loại sự kiện thường cần **schema riêng theo `event_type` hoặc `schema_version`**.

## 15. `pg_input_is_valid`: kiểm tra có cast được không (PostgreSQL 16+)

PostgreSQL từ phiên bản **16** có hàm kiểm tra đầu vào theo kiểu:

```sql
pg_input_is_valid(value_text, type_name)
```

Hàm giúp hỏi liệu văn bản có hợp lệ cho một kiểu SQL hay không **mà không phải cast trực tiếp trong trường hợp hỗ trợ**.

### 15.1. Ví dụ

```sql
SELECT
    pg_input_is_valid('120.50', 'numeric') AS valid_money,
    pg_input_is_valid('N/A', 'numeric') AS invalid_money,
    pg_input_is_valid('104a', 'integer') AS invalid_id,
    pg_input_is_valid('2026-02-30', 'date') AS invalid_date;
```

### 15.2. Chỉ cast ở nhánh được xác nhận

```sql
WITH extracted AS (
    SELECT
        event_id,
        BTRIM(payload #>> '{order,total}') AS total_text
    FROM json_lab_events
    WHERE payload ->> 'event_type' = 'checkout'
)
SELECT
    event_id,
    total_text,
    CASE
        WHEN pg_input_is_valid(total_text, 'numeric')
        THEN total_text::numeric
        ELSE NULL::numeric
    END AS total_numeric
FROM extracted
ORDER BY event_id;
```

Ở đây `'N/A'`, `'true'`, `'12,50'` không bị cast trong nhánh hợp lệ. `NULL` không được xem là số và trả NULL.

### 15.3. Cần hiểu giới hạn

- Hàm này **không có trên mọi phiên bản PostgreSQL**, nhất là môi trường cũ hơn 16.
- Một số kiểu/input routine có những giới hạn hỗ trợ báo lỗi mềm theo phiên bản; không mặc định đây là “try cast” vạn năng cho mọi kiểu tùy biến.
- `pg_input_is_valid(text,'numeric')` chỉ nói text có thể là một **numeric**, không có nghĩa giá trị phù hợp với `numeric(12,2)`, không âm, hoặc đúng tiền tệ.
- Với `date`, hàm kiểm tra cú pháp đầu vào theo kiểu SQL và quy tắc parser; nó không bảo đảm chuỗi tuân một format API bắt buộc nếu parser hỗ trợ nhiều format.

Khi cần nhập dữ liệu có hợp đồng nghiêm ngặt, nên kiểm tra **kiểu JSON**, **cú pháp**, **miền giá trị** và **ý nghĩa nghiệp vụ** riêng biệt.

## 16. Chiến lược khi không có `pg_input_is_valid`

Trên PostgreSQL cũ hoặc hệ quản trị không hỗ trợ hàm tương đương, có thể dùng:

1. Xác thực ở tầng ứng dụng/ingestion trước khi lưu.
2. Kiểm tra kiểu JSON và **định dạng ký tự được phép** bằng biểu thức chính quy.
3. Dùng hàm chuyển kiểu tự xây có bắt lỗi ở PL/pgSQL nếu thật sự cần ETL linh hoạt.
4. Tách dữ liệu không hợp lệ sang vùng kiểm tra thay vì bắt báo cáo xử lý tất cả lỗi.

### 16.1. Ví dụ regex cho số thập phân không âm

```sql
WITH extracted AS (
    SELECT
        event_id,
        BTRIM(payload #>> '{order,total}') AS total_text
    FROM json_lab_events
)
SELECT
    event_id,
    CASE
        WHEN total_text ~ '^[0-9]+([.][0-9]+)?$'
        THEN total_text::numeric
        ELSE NULL::numeric
    END AS total_decimal
FROM extracted
ORDER BY event_id;
```

Biểu thức trên chỉ chấp nhận một **định dạng con** có các chữ số và phần thập phân tùy chọn. Nó từ chối số âm, dấu `+`, dạng khoa học `1e3`, dấu phẩy và các biểu diễn khác.

### 16.2. Regex không bảo đảm mọi điều kiện cast

Ngay cả khi chuỗi khớp cú pháp số, nó có thể:

- Quá lớn đối với `integer`, `bigint` hoặc `numeric(p,s)`.
- Có quá nhiều chữ số gây chi phí/giới hạn tài nguyên.
- Không nằm trong miền nghiệp vụ.

Đừng diễn giải regex là phương án kiểm soát đầy đủ và không bao giờ gây lỗi.

### 16.3. Kiểm tra ngày không thể chỉ bằng regex

```text
2026-02-30
```

khớp biểu thức định dạng `YYYY-MM-DD`, nhưng **không phải ngày hợp lệ**. Cần bộ phân tích ngày có thể báo invalid date, và có thể thêm kiểm tra format chính xác.

## 17. Phân biệt dữ liệu không hợp lệ và dữ liệu có thể chuẩn hóa

Một pipeline có thể chọn hai chính sách:

**Chính sách strict:** `order.total` phải là JSON number không âm, có giới hạn độ lớn, không `NULL`. Khi dữ liệu không đúng, **reject**.

**Chính sách tolerant:** chấp nhận JSON number hoặc JSON string có cú pháp số hợp lệ, trim khoảng trắng, nhưng vẫn reject `'N/A'`, Boolean và giá trị ngoài giới hạn.

### 17.1. Bảng quyết định

| Đầu vào | Strict number | Tolerant numeric text | Giải thích |
|---|---|---|---|
| `120.50` | Chấp nhận | Chấp nhận | JSON number |
| `"120.50"` | Từ chối | Có thể chấp nhận | JSON string nhưng parse được |
| `" 42.75 "` | Từ chối | Có thể chấp nhận sau trim | Quy tắc chuẩn hóa rõ ràng |
| `"1e3"` | Từ chối | Tùy hợp đồng | Dạng khoa học |
| `"12,50"` | Từ chối | Thường từ chối | Dấu phẩy không có hợp đồng locale |
| `"N/A"` | Từ chối | Từ chối | Không phải numeric |
| `true` | Từ chối | Từ chối | Boolean |
| `null` | Tùy trường bắt buộc | Tùy hợp đồng | Không có số |
| `-10.25` | Có thể từ chối theo miền | Có thể từ chối | JSON number hợp lệ nhưng tiền âm |

**Không có chính sách chung duy nhất** cho mọi API. Quan trọng là quy tắc được viết rõ, kiểm thử được và áp dụng nhất quán.

### 17.2. Mô hình ba trạng thái đầu ra

Một kết quả ETL tốt đôi khi không chỉ có:

```text
total_numeric
```

mà còn:

```text
raw_total
total_numeric
total_validation_status
```

Ví dụ `VALID`, `MISSING`, `JSON_NULL`, `BAD_TYPE`, `BAD_FORMAT`, `OUT_OF_RANGE`. Như vậy dữ liệu không hợp lệ không bị **âm thầm biến thành 0** hoặc bị xóa mất dấu vết.

## 18. Trích xuất object thành bản ghi bằng `jsonb_to_record`

Khi một object JSON có nhiều khóa, thay vì viết `->>` cho từng cột, PostgreSQL có thể tạo một record có kiểu cột khai báo:

```sql
SELECT *
FROM jsonb_to_record(
    '{"total":120.50,
      "paid":true,
      "created_at":"2026-08-01"}'::jsonb
) AS x(
    total NUMERIC,
    paid BOOLEAN,
    created_at DATE
);
```

Kết quả là các cột SQL:

| total (`numeric`) | paid (`boolean`) | created_at (`date`) |
|---:|---|---|
| 120.50 | true | 2026-08-01 |

### 18.1. Ưu điểm

- Khai báo rõ **kiểu SQL** ngay tại điểm đọc JSON.
- Trả nhiều cột chỉ qua một thao tác chuyển object thành record.
- Thuận tiện với các cấu trúc tương đối ổn định.

### 18.2. Cần cảnh giác

`jsonb_to_record` vẫn phải **chuyển giá trị** theo kiểu đã khai báo. Nếu gặp:

```json
{"total":"N/A"}
```

và cột `total NUMERIC`, nó có thể **báo lỗi chuyển kiểu**. Hàm không phải một bộ validator tự bỏ qua mọi giá trị xấu.

### 18.3. Cột JSON thiếu

```sql
SELECT *
FROM jsonb_to_record(
    '{"total":25}'::jsonb
) AS x(
    total NUMERIC,
    paid BOOLEAN
);
```

`paid` không có trong object nên cột SQL tương ứng là NULL. Điều này không tự phân biệt **khóa thiếu** với **JSON null**; nếu cần, hãy giữ tài liệu gốc và kiểm tra sự tồn tại trước.

### 18.4. Kết hợp với bảng

Trong dữ liệu đã được xác thực sạch, có thể dùng `LATERAL`:

```sql
SELECT
    e.event_id,
    x.total,
    x.paid,
    x.created_at
FROM json_lab_events AS e
CROSS JOIN LATERAL jsonb_to_record(
    e.payload -> 'order'
) AS x(
    total NUMERIC,
    paid BOOLEAN,
    created_at DATE
)
WHERE e.event_id = 1;
```

Ví dụ chỉ chọn dòng 1 có kiểu phù hợp. Khi áp dụng toàn bộ bảng dữ liệu bẩn, cần **xác thực trước** hoặc tách các dòng không đạt ra; không kỳ vọng `WHERE` phía ngoài sẽ luôn cứu mọi cast không hợp lệ nếu bộ tối ưu thay đổi thứ tự đánh giá.

## 19. Trích xuất mảng JSON theo vị trí

Với:

```json
{
  "tags": ["web", "promo"],
  "order": {
    "items": [
      {"sku":"A","qty":2,"unit_price":30.25},
      {"sku":"B","qty":1,"unit_price":60.00}
    ]
  }
}
```

có thể lấy phần tử theo chỉ số:

```sql
SELECT
    payload -> 'tags' ->> 0 AS first_tag,
    payload -> 'tags' ->> 1 AS second_tag,
    payload #>> '{order,items,0,sku}' AS first_sku,
    payload #>> '{order,items,1,sku}' AS second_sku
FROM json_lab_events
WHERE event_id = 1;
```

Kết quả:

```text
first_tag  = web
second_tag = promo
first_sku  = A
second_sku = B
```

### 19.1. Mảng bắt đầu từ vị trí 0

Vị trí đầu tiên là `0`, thứ hai là `1`. Đây là **chỉ số trong JSON array**, khác với cách đánh số mặc định của nhiều SQL array PostgreSQL được tạo từ literal SQL.

### 19.2. Truy cập phần tử không tồn tại

```sql
SELECT payload -> 'tags' ->> 99
FROM json_lab_events
WHERE event_id = 1;
```

Không có phần tử vị trí 99, biểu thức trích xuất trả SQL NULL, không tự ném lỗi chỉ vì vượt giới hạn.

### 19.3. Một field có thể không phải array

Trong dữ liệu mẫu, `event_id=8` có:

```json
{"tags": "web"}
```

thay vì:

```json
{"tags":["web"]}
```

Nếu cần xử lý `tags` là array, nên kiểm tra:

```sql
jsonb_typeof(payload -> 'tags') = 'array'
```

trước khi dùng các hàm chỉ nhận mảng.

## 20. Biến mảng JSON thành nhiều dòng: `jsonb_array_elements`

Đây là bước quan trọng khi muốn tính toán trên từng phần tử của mảng.

```sql
SELECT
    e.event_id,
    i.item ->> 'sku' AS sku,
    (i.item ->> 'qty')::integer AS qty,
    (i.item ->> 'unit_price')::numeric AS unit_price
FROM json_lab_events AS e
CROSS JOIN LATERAL jsonb_array_elements(
    e.payload #> '{order,items}'
) AS i(item)
WHERE e.event_id = 1
ORDER BY sku;
```

Với dòng 1:

| event_id | sku | qty | unit_price |
|---:|---|---:|---:|
| 1 | A | 2 | 30.25 |
| 1 | B | 1 | 60.00 |

### 20.1. `CROSS JOIN LATERAL` làm gì?

Với từng dòng sự kiện `e`, hàm `jsonb_array_elements` nhận mảng từ chính dòng đó và sinh **một dòng SQL cho mỗi phần tử**.

```text
event_id=1
items = [item A, item B]
        │
        ▼
SQL row (1, item A)
SQL row (1, item B)
```

**Độ hạt dữ liệu đã thay đổi**: một sự kiện → nhiều dòng item. Nếu sau đó `SUM(order.total)` trực tiếp, tổng tiền đơn có thể bị **nhân theo số item**.

### 20.2. Mảng rỗng

```sql
SELECT *
FROM jsonb_array_elements('[]'::jsonb);
```

trả **0 dòng**. Vì vậy, `CROSS JOIN LATERAL` với mảng rỗng sẽ không giữ dòng sự kiện đầu vào.

### 20.3. `NULL`, object và string

`jsonb_array_elements` yêu cầu đầu vào là JSON array (hoặc SQL NULL tùy ngữ cảnh). Nếu nhận JSON object, JSON string hay JSON null không phù hợp, nó có thể lỗi vì **không thể extract elements from a non-array/scalar**.

Không chạy mù quáng trên `event_id=10`, nơi `order.items={}`, hoặc `event_id=6`, nơi `order.items=null`.

## 21. Lấy phần tử mảng an toàn khi dữ liệu không đồng nhất

Để không gọi `jsonb_array_elements` với non-array, có thể chuẩn hóa tham số thành mảng rỗng nếu không đúng kiểu:

```sql
SELECT
    e.event_id,
    i.item
FROM json_lab_events AS e
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(e.payload #> '{order,items}') = 'array'
        THEN e.payload #> '{order,items}'
        ELSE '[]'::jsonb
    END
) AS i(item)
ORDER BY e.event_id;
```

### 21.1. Chính sách trên cố ý bỏ các non-array

Với `items={}` hoặc `items=null`, biểu thức `CASE` thay bằng `[]`, khiến sự kiện tạo **0 item**. Điều này **an toàn về kỹ thuật truy vấn**, nhưng có thể **che lỗi dữ liệu** nếu schema yêu cầu `items` phải là array.

Tốt hơn trong pipeline quan trọng:

```text
items_kind = array / missing / json_null / wrong_shape
items_rows = các item hợp lệ được bóc tách
```

để giữ khả năng điều tra.

### 21.2. Dùng `LEFT JOIN LATERAL` để giữ sự kiện không có item

```sql
SELECT
    e.event_id,
    i.item ->> 'sku' AS sku
FROM json_lab_events AS e
LEFT JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(e.payload #> '{order,items}') = 'array'
        THEN e.payload #> '{order,items}'
        ELSE '[]'::jsonb
    END
) AS i(item) ON TRUE
ORDER BY e.event_id, sku;
```

Với event không có item, `LEFT JOIN LATERAL` vẫn có thể giữ **một dòng sự kiện** với `sku` NULL.

**Khác biệt:** `CROSS JOIN LATERAL` loại outer row nếu hàm không trả dòng; `LEFT JOIN LATERAL ... ON TRUE` giữ outer row. Điều này quyết định độ hạt và số dòng khi tổng hợp.

### 21.3. Dùng `WITH ORDINALITY`

```sql
SELECT
    e.event_id,
    i.position,
    i.item ->> 'sku' AS sku
FROM json_lab_events AS e
CROSS JOIN LATERAL jsonb_array_elements(
    e.payload #> '{order,items}'
) WITH ORDINALITY AS i(item, position)
WHERE e.event_id = 1
ORDER BY i.position;
```

`WITH ORDINALITY` gắn vị trí kiểu SQL **bắt đầu từ 1** cho các dòng do hàm sinh, khác với chỉ số JSON array bắt đầu từ 0.

## 22. Chuyển kiểu từng item và tính tổng chi tiết

Khi mỗi item có:

```json
{"sku":"A","qty":2,"unit_price":30.25}
```

ta có thể tính:

```text
line_amount = quantity × unit_price
```

Trên các event có item hợp lệ:

```sql
WITH item_rows AS (
    SELECT
        e.event_id,
        i.item ->> 'sku' AS sku,
        (i.item ->> 'qty')::integer AS qty,
        (i.item ->> 'unit_price')::numeric AS unit_price
    FROM json_lab_events AS e
    CROSS JOIN LATERAL jsonb_array_elements(
        e.payload #> '{order,items}'
    ) AS i(item)
    WHERE e.event_id IN (1, 2, 14)
)
SELECT
    event_id,
    sku,
    qty,
    unit_price,
    qty * unit_price AS line_amount
FROM item_rows
ORDER BY event_id, sku;
```

Kết quả:

| event_id | sku | qty | unit_price | line_amount |
|---:|---|---:|---:|---:|
| 1 | A | 2 | 30.25 | 60.50 |
| 1 | B | 1 | 60.00 | 60.00 |
| 2 | C | 4 | 20.00 | 80.00 |
| 14 | G | 1 | 15.50 | 15.50 |

### 22.1. Tổng từng đơn

```sql
WITH item_rows AS (
    SELECT
        e.event_id,
        (i.item ->> 'qty')::numeric AS qty,
        (i.item ->> 'unit_price')::numeric AS unit_price
    FROM json_lab_events AS e
    CROSS JOIN LATERAL jsonb_array_elements(
        e.payload #> '{order,items}'
    ) AS i(item)
    WHERE e.event_id IN (1, 2, 14)
)
SELECT event_id, SUM(qty * unit_price) AS items_total
FROM item_rows
GROUP BY event_id
ORDER BY event_id;
```

Dự kiến:

```text
event_id=1  → 120.50
event_id=2  →  80.00
event_id=14 →  15.50
```

### 22.2. Tránh nhân tổng đơn sau khi explode mảng

Nếu một đơn có hai item, một phép:

```sql
SUM((payload #>> '{order,total}')::numeric)
```

trên bảng sau khi `jsonb_array_elements` có thể cộng **cùng tổng đơn hai lần**. Muốn so `order.total` với `SUM(line_amount)`, hãy tổng item **về một dòng mỗi event_id**, rồi mới join với bảng sự kiện.

### 22.3. Xác thực item bẩn

`event_id=4` có `qty="two"`. Cast thẳng thành integer sẽ lỗi. Với dữ liệu lớn, cần chuẩn hóa từng item, kiểm tra `qty` là integer, `unit_price` là decimal hợp lệ, `qty > 0`, `unit_price >= 0`, đồng thời giữ thông tin lỗi theo từng phần tử.

## 23. `jsonb_to_recordset`: khai báo kiểu cho cả mảng object

Nếu mảng gồm các object đồng nhất:

```sql
SELECT *
FROM jsonb_to_recordset(
    '[
      {"sku":"A","qty":2,"unit_price":30.25},
      {"sku":"B","qty":1,"unit_price":60.00}
    ]'::jsonb
) AS x(
    sku TEXT,
    qty INTEGER,
    unit_price NUMERIC
);
```

Kết quả đã có cột SQL `text`, `integer`, `numeric`, không cần viết `->>` cho từng field.

### 23.1. So sánh với `jsonb_array_elements`

| Cách | Phù hợp khi |
|---|---|
| `jsonb_array_elements` | Cần giữ item là JSONB để kiểm tra cấu trúc, loại phần tử, xử lý linh hoạt |
| `jsonb_array_elements_text` | Mảng scalar và chỉ cần text từng phần tử |
| `jsonb_to_recordset` | Mảng object có **schema cột khá ổn định**, dữ liệu đã đủ sạch |
| `jsonb_to_record` | Một object JSON cần chuyển thành một bản ghi có kiểu SQL |

### 23.2. Cảnh báo bản ghi không đồng nhất

Nếu một item có `qty="two"`, `jsonb_to_recordset(... qty INTEGER)` có thể lỗi cho cả lệnh, giống một cast trực tiếp.

Nó không tự tạo một cột `is_valid` và bỏ qua dòng xấu. Muốn ETL chịu lỗi từng dòng, hãy giữ item `jsonb`, xác thực rồi chuyển theo chính sách.

## 24. Chuyển JSON array thành SQL array

Một JSON array:

```json
["web", "promo"]
```

không tự động là SQL `text[]`. Đôi khi cần một SQL array để dùng hàm SQL:

```sql
SELECT ARRAY(
    SELECT jsonb_array_elements_text(
        '["web","promo"]'::jsonb
    )
) AS tags_sql_array;
```

Kết quả là một SQL `text[]` có hai phần tử. Trong trường hợp chỉ muốn kiểm tra JSON array có phần tử cụ thể, có thể giữ `jsonb` và dùng toán tử containment phù hợp, thay vì chuyển thành SQL array.

### 24.1. Mảng JSON số

```sql
SELECT ARRAY(
    SELECT value::integer
    FROM jsonb_array_elements_text('[1,2,3]'::jsonb) AS t(value)
) AS integer_array;
```

Kết quả SQL là mảng integer `{1,2,3}` (cách hiển thị thường gặp). Nếu mảng JSON có chuỗi `"two"` hoặc object, phép cast `::integer` phải được kiểm soát.

### 24.2. Không nhầm mảng JSON với chuỗi chứa JSON

```json
{"tags":"[\"web\",\"promo\"]"}
```

`tags` ở đây là **JSON string** chứa ký tự nhìn giống mảng JSON. Không thể xử lý nó như JSON array trước khi có bước parse thêm và xác thực. **Double encoding** là một lỗi thiết kế API đáng tránh.

## 25. JSONPath: truy vấn theo đường dẫn và điều kiện

PostgreSQL hỗ trợ **SQL/JSON path** cho nhiều thao tác với `jsonb`, qua các hàm như `jsonb_path_exists`, `jsonb_path_query`, `jsonb_path_query_first` (tùy phiên bản; PostgreSQL 12+ có nền tảng JSONPath).

Ví dụ hỏi có item với giá lớn hơn 50 hay không:

```sql
SELECT
    event_id,
    jsonb_path_exists(
        payload,
        '$.order.items[*] ? (@.unit_price > 50)'
    ) AS has_expensive_item
FROM json_lab_events
WHERE event_id = 1;
```

Trong event 1 có item B với `unit_price=60.00`, nên biểu thức có thể trả `true`.

### 25.1. JSONPath vẫn giữ ngữ nghĩa kiểu JSON

JSON string `"60"` và JSON number `60` không nên bị coi là cùng kiểu trong mọi phép so sánh JSONPath. Nếu dữ liệu có cả number và string, cần chuẩn hóa rõ chứ không dựa vào phép so sánh ngầm.

### 25.2. Lấy một giá trị JSON theo JSONPath

```sql
SELECT jsonb_path_query_first(
    '{"order":{"items":[{"sku":"A"},{"sku":"B"}]}}'::jsonb,
    '$.order.items[0].sku'
) AS first_sku_json;
```

Hàm trả một giá trị **jsonb**, ví dụ JSON string `"A"`, không phải text SQL thuần. Nếu cần một giá trị text, có thể dùng đường dẫn đơn giản:

```sql
payload #>> '{order,items,0,sku}'
```

hoặc cách chuyển có chủ đích khác.

### 25.3. Khi nào JSONPath có ích?

- Dò các phần tử mảng phù hợp một điều kiện.
- Điều hướng đường dẫn phức tạp hơn khóa cố định.
- Diễn đạt điều kiện trên nhiều phần tử lồng nhau.
- Kết hợp một số dạng truy vấn với các cơ chế chỉ mục hỗ trợ phù hợp.

Nhưng `#>>` và `->>` thường **dễ đọc hơn** cho một đường dẫn tĩnh lấy một scalar. Không cần dùng JSONPath cho mọi khóa.

## 26. Lọc JSON bằng containment `@>` và kiểm tra key

Toán tử `@>` trên `jsonb` kiểm tra tài liệu trái **chứa** cấu trúc JSON phải theo quy tắc containment.

```sql
SELECT event_id
FROM json_lab_events
WHERE payload @> '{"event_type":"checkout"}'::jsonb
ORDER BY event_id;
```

Nó có thể thay biểu thức:

```sql
WHERE payload ->> 'event_type' = 'checkout'
```

trong trường hợp muốn tìm giá trị JSON string đúng cấu trúc.

### 26.1. Containment phân biệt kiểu

```sql
SELECT
    '{"value":10}'::jsonb @> '{"value":10}'::jsonb
        AS same_number,
    '{"value":"10"}'::jsonb @> '{"value":10}'::jsonb
        AS string_vs_number;
```

Giá trị JSON string `"10"` khác JSON number `10`. Đây có thể là lợi thế khi muốn **kiểm tra đúng schema**, thay vì so text đã chuẩn hóa.

### 26.2. Kiểm tra object lồng nhau

```sql
SELECT event_id
FROM json_lab_events
WHERE payload @> '{"order":{"paid":true}}'::jsonb
ORDER BY event_id;
```

Truy vấn này yêu cầu `order.paid` là **JSON boolean true**. Nó không coi JSON string `"true"` là Boolean true.

### 26.3. `?` và `@>` không thay thế nhau mọi lúc

- `payload ? 'order'` hỏi khóa cấp ngoài có tồn tại không (đối với object).
- `payload @> '{"order":{}}'::jsonb` hỏi cấu trúc chứa object `order` phù hợp.
- `payload ->> 'order' IS NOT NULL` chỉ hỏi kết quả text không SQL NULL; có thể đồng nhất missing với JSON null ở những trường hợp khác.

Phải chọn phép kiểm tra dựa vào **ý nghĩa thực sự**.

## 27. Lọc theo giá trị có kiểu: tránh so sánh chuỗi

Giả sử yêu cầu:

> Tìm các checkout có tổng tiền **lớn hơn 100** và đã thanh toán.

Với dữ liệu được bảo đảm hợp đồng strict:

```sql
SELECT
    event_id,
    (payload #>> '{order,total}')::numeric AS total_amount
FROM json_lab_events
WHERE jsonb_typeof(payload #> '{order,total}') = 'number'
  AND jsonb_typeof(payload #> '{order,paid}') = 'boolean'
  AND (payload #>> '{order,paid}')::boolean IS TRUE
  AND (payload #>> '{order,total}')::numeric > 100
ORDER BY event_id;
```

**Lưu ý về dữ liệu bẩn và optimizer:** Không nên coi việc đặt `jsonb_typeof(...)='number'` ở cùng `WHERE` với phép cast luôn là hàng rào thực thi tuyệt đối trong mọi truy vấn/phép tối ưu. Khi cần robust trước dữ liệu xấu, dùng một biểu thức `CASE` được thiết kế an toàn cho phép cast, hoặc chuẩn hóa dữ liệu trước.

### 27.1. Mẫu `CASE` để tạo số có kiểu

```sql
WITH normalized AS (
    SELECT
        event_id,
        payload ->> 'event_type' AS event_type,
        CASE
            WHEN jsonb_typeof(payload #> '{order,total}') = 'number'
            THEN (payload #>> '{order,total}')::numeric
            ELSE NULL::numeric
        END AS total_amount,
        CASE
            WHEN jsonb_typeof(payload #> '{order,paid}') = 'boolean'
            THEN (payload #>> '{order,paid}')::boolean
            ELSE NULL::boolean
        END AS is_paid
    FROM json_lab_events
)
SELECT event_id, total_amount
FROM normalized
WHERE event_type = 'checkout'
  AND is_paid IS TRUE
  AND total_amount > 100
ORDER BY event_id;
```

Chỉ JSON number được cast thành `numeric` và chỉ JSON boolean được cast thành `boolean`. Vì vậy, các dòng string `'N/A'`, `'true'` không trở thành phép cast không hợp lệ.

Trong bộ dữ liệu mẫu, dòng có tổng lớn hơn 100 và `paid=true` ở chế độ strict gồm event **1**. Dòng 9 có `"1e3"` là JSON string nên không được nhận; dòng 15 cũng là string.

### 27.2. `CASE` tạo ra SQL NULL khi không hợp lệ

Đây là cách **bỏ qua giá trị không đạt** trong phần báo cáo, chưa phải pipeline xác thực hoàn chỉnh. Nếu cần biết bao nhiêu dòng sai và vì sao, hãy tạo cột `validation_status` thay vì chỉ dùng NULL.

## 28. Kiểm tra cấu trúc JSON khi ghi dữ liệu

Nếu dùng JSONB như payload sự kiện, có thể bổ sung ràng buộc đảm bảo tối thiểu về cấu trúc.

Ví dụ tạo một bảng thử khác:

```sql
CREATE TEMP TABLE json_lab_strict_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL,

    CONSTRAINT payload_must_be_object
        CHECK (jsonb_typeof(payload) = 'object'),

    CONSTRAINT total_must_be_number
        CHECK (
            jsonb_typeof(payload #> '{order,total}') = 'number'
        ),

    CONSTRAINT paid_must_be_boolean
        CHECK (
            jsonb_typeof(payload #> '{order,paid}') = 'boolean'
        )
);
```

### 28.1. Bẫy `CHECK` với SQL NULL

Trong SQL, `CHECK` **thường cho phép biểu thức là TRUE hoặc UNKNOWN (`NULL`)**; nó chỉ từ chối khi biểu thức là FALSE.

Vì vậy, ràng buộc:

```sql
CHECK (jsonb_typeof(payload #> '{order,total}') = 'number')
```

có thể **không từ chối khóa `total` bị thiếu**, vì `jsonb_typeof(...)` thành SQL NULL và so sánh cho UNKNOWN.

### 28.2. Ràng buộc thực sự yêu cầu khóa và kiểu

Muốn từ chối cả missing và JSON null:

```sql
CREATE TEMP TABLE json_lab_strict_orders_v2 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL,

    CHECK (jsonb_typeof(payload) = 'object'),
    CHECK (
        (
          jsonb_typeof(payload #> '{order,total}') = 'number'
        ) IS TRUE
    ),
    CHECK (
        (
          jsonb_typeof(payload #> '{order,paid}') = 'boolean'
        ) IS TRUE
    )
);
```

`IS TRUE` yêu cầu biểu thức đánh giá **đúng TRUE**, chứ không cho UNKNOWN vượt qua. Trong hệ thống thực, có thể thêm điều kiện `total >= 0`, giới hạn giá trị, tên tiền tệ và các khóa quan trọng khác.

### 28.3. Thử dữ liệu hợp lệ và thiếu

```sql
INSERT INTO json_lab_strict_orders_v2 (payload)
VALUES ('{"order":{"total":120.50,"paid":true}}'::jsonb);
-- Hợp lệ.

-- Minh họa dữ liệu bị từ chối, không cần chạy chung script:
-- INSERT INTO json_lab_strict_orders_v2 (payload)
-- VALUES ('{"order":{"paid":true}}'::jsonb);
-- total thiếu → CHECK không đạt.
```

### 28.4. `CHECK` không thay thế JSON Schema hoàn chỉnh

Với payload phức tạp có nhiều loại sự kiện, array object lồng nhau, ràng buộc liên trường và version, có thể cần schema validation ở tầng ứng dụng/ingestion, JSON Schema hoặc quy trình kiểm tra chuyên dụng.

Một vài `CHECK` chỉ kiểm soát được những bất biến được biểu diễn rõ trong SQL.

## 29. Tạo cột SQL có kiểu từ JSON: generated column

Khi thường xuyên lọc/tính toán trên `order.total`, có thể cân nhắc lưu một **cột SQL sinh từ JSON**.

Ví dụ với bảng **chỉ nhận payload đã xác thực**:

```sql
CREATE TEMP TABLE json_lab_typed_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL,
    total_amount NUMERIC(12,2)
        GENERATED ALWAYS AS (
            (payload #>> '{order,total}')::numeric(12,2)
        ) STORED,
    paid BOOLEAN
        GENERATED ALWAYS AS (
            (payload #>> '{order,paid}')::boolean
        ) STORED
);
```

### 29.1. Lợi ích

- Truy vấn có cột `total_amount` kiểu `NUMERIC(12,2)` rõ ràng.
- Có thể tạo index, dùng thống kê và ràng buộc trên cột có kiểu.
- Ít lặp biểu thức trích xuất dài trong các báo cáo.

### 29.2. Rủi ro

Khi `INSERT`/`UPDATE`, biểu thức generated phải **cast thành công**. Payload chứa `"N/A"` hoặc giá trị vượt `numeric(12,2)` có thể làm lệnh ghi **thất bại**. Đây có thể là hành vi **mong muốn** để chặn dữ liệu sai ở cửa vào, nhưng cần thiết kế thông báo lỗi và pipeline xử lý.

### 29.3. Dữ liệu JSON string có thể vẫn được cast

Generated column trên **không tự cưỡng chế** `total` phải là JSON number; `"80.00"` vẫn có thể được cast thành numeric. Nếu muốn schema strict, thêm `CHECK (jsonb_typeof(...)='number') IS TRUE` phù hợp.

### 29.4. Đừng dùng generated column cho mọi thứ

Mỗi cột được tính/lưu có chi phí ghi, storage và migration. Với trường hiếm truy vấn, giữ trong JSONB có thể hợp lý hơn. Chỉ nên chuẩn hóa mạnh những thuộc tính **quan trọng và có truy vấn/ràng buộc rõ ràng**.

## 30. Chỉ mục trên JSONB và biểu thức đã trích xuất

JSONB có thể được lập chỉ mục theo hai hướng phổ biến:

1. **GIN trên tài liệu JSONB** để hỗ trợ các dạng truy vấn containment và một số toán tử JSON.
2. **B-tree expression index** trên khóa/cột được trích xuất để hỗ trợ lọc/sắp xếp theo giá trị SQL.

### 30.1. GIN cho containment

```sql
CREATE INDEX idx_json_lab_payload_gin
    ON json_lab_events
    USING GIN (payload);
```

Truy vấn có thể hưởng lợi:

```sql
SELECT event_id
FROM json_lab_events
WHERE payload @> '{"event_type":"checkout"}'::jsonb;
```

Tùy kích thước dữ liệu và selectivity, planner có thể dùng GIN hoặc quét bảng. **Có index không bảo đảm nó được chọn**.

### 30.2. B-tree trên text trích xuất

```sql
CREATE INDEX idx_json_lab_event_type
    ON json_lab_events ((payload ->> 'event_type'));
```

Phù hợp để planner cân nhắc với:

```sql
WHERE payload ->> 'event_type' = 'checkout'
```

### 30.3. Index trên số có kiểu cần dữ liệu sạch

Ví dụ ý tưởng:

```sql
-- Chỉ tạo trên bảng được bảo đảm total luôn cast được!
-- CREATE INDEX idx_orders_total
-- ON some_validated_table (
--     ((payload #>> '{order,total}')::numeric)
-- );
```

Trên bảng `json_lab_events` chứa `"N/A"` và Boolean, biểu thức cast có thể **lỗi ngay lúc xây index**. Dùng cột normalized đã xác thực, generated column phù hợp, hoặc expression index chỉ áp dụng tập giá trị hợp lệ theo thiết kế đã đánh giá.

### 30.4. Coi chừng index text cho số

```sql
CREATE INDEX idx_json_lab_total_text
    ON json_lab_events ((payload #>> '{order,total}'));
```

Index này sắp theo **text**, không phải thứ tự numeric. Nó không tự thay thế index trên `NUMERIC` cho truy vấn:

```sql
WHERE total_amount > 100
ORDER BY total_amount
```

Nếu nhu cầu là range/sort số, cần cột/index với kiểu **numeric** phù hợp.

### 30.5. JSONB GIN operator class

PostgreSQL hỗ trợ các cấu hình operator class như `jsonb_ops` và `jsonb_path_ops` với tập toán tử được hỗ trợ khác nhau. Ví dụ `jsonb_path_ops` hữu ích với một số containment/JSONPath nhưng **không hỗ trợ mọi phép kiểm tra khóa `?` giống `jsonb_ops`**.

Không chọn operator class chỉ từ tên; cần xem truy vấn thật, toán tử dùng và kế hoạch thực thi.

## 31. Performance: vì sao cast JSON trong `WHERE` có thể tốn kém?

Ví dụ:

```sql
SELECT event_id
FROM json_lab_events
WHERE (payload #>> '{order,total}')::numeric > 100;
```

Trong dữ liệu sạch, câu này cần:

1. Đọc payload.
2. Trích `order.total` thành text.
3. Parse text thành numeric.
4. So sánh với 100.

Nếu chạy trên nhiều triệu dòng mà không có index phù hợp, phép parse/cast có thể lặp rất nhiều lần. Trên dữ liệu bẩn, câu còn có nguy cơ lỗi.

### 31.1. Tối ưu đúng cách

- Kiểm tra truy vấn thực tế bằng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu/thời điểm thích hợp.
- Chuẩn hóa những thuộc tính thường dùng thành cột SQL có kiểu.
- Cân nhắc expression index **chỉ khi dữ liệu sạch và biểu thức được bảo đảm hợp lệ**.
- Lọc theo điều kiện có index phù hợp trước, nếu semantics và kế hoạch cho phép.
- Tránh trích cùng một đường dẫn nhiều lần trong báo cáo rất lớn khi có giải pháp lưu/chuẩn hóa hợp lý.

### 31.2. View không tự vật liệu hóa kết quả cast

```sql
CREATE VIEW v_orders AS
SELECT (payload #>> '{order,total}')::numeric AS total
FROM json_lab_events;
```

Với view thường, không nên mặc định phép chuyển kiểu đã được tính sẵn và lưu như một cột số. View thường là định nghĩa truy vấn; optimizer quyết định thực thi khi đọc.

### 31.3. Trả về text để hiển thị khác dùng text để tính

Một API có thể trả `total_amount` số hoặc string có định dạng:

```text
120.50
"120,50 VND"
```

Tính toán phải dùng giá trị số có kiểu; hiển thị theo locale là trách nhiệm tầng trình bày. Không lưu chuỗi đã format như nguồn số để cộng/trừ.

## 32. Nhiều phiên bản schema trong cùng cột JSON

Một hệ thống có thể thay đổi payload theo thời gian:

**Version 1**

```json
{
  "schema_version": 1,
  "order": {"total": 120.50}
}
```

**Version 2**

```json
{
  "schema_version": 2,
  "order": {
    "total": {"value": 120.50, "currency": "VND"}
  }
}
```

Nếu query cố:

```sql
payload #>> '{order,total}'
```

trên version 2, kết quả không còn là một scalar numeric. `->>` trên object có thể cho biểu diễn JSON dạng **text**, không phải giá trị `120.50`.

### 32.1. Chuẩn hóa theo `schema_version`

```sql
WITH examples(doc) AS (
    VALUES
      ('{"schema_version":1,"order":{"total":120.50}}'::jsonb),
      ('{"schema_version":2,"order":{"total":{"value":120.50,"currency":"VND"}}}'::jsonb)
)
SELECT
    CASE (doc ->> 'schema_version')::integer
        WHEN 1 THEN (doc #>> '{order,total}')::numeric
        WHEN 2 THEN (doc #>> '{order,total,value}')::numeric
        ELSE NULL::numeric
    END AS total_amount
FROM examples;
```

### 32.2. Khi có dữ liệu không tin cậy

Ví dụ trên giả định schema version và các giá trị số đúng kiểu. Với dữ liệu bẩn, phải xác thực `schema_version` và hai đường dẫn tương ứng trước cast.

### 32.3. Không âm thầm đổi ý nghĩa cột

Nếu version 2 chuyển đơn vị từ “đồng” sang “nghìn đồng”, một phép cast vẫn thành công nhưng kết quả **sai đơn vị**. Trích xuất có kiểu đúng mới chỉ là một phần; còn cần quản lý **đơn vị, phiên bản, múi giờ, precision và các quy tắc tính toán**.

## 33. Thiết kế pipeline: raw → validated → typed

Trong hệ thống dữ liệu thực, một kiến trúc phổ biến:

```text
API / message / file JSON
           │
           ▼
Raw events (payload JSONB + metadata nguồn)
           │
           ▼
Validation
   ├── schema_version
   ├── loại JSON của từng khóa
   ├── cú pháp text được phép
   ├── giới hạn số/ngày/thời gian
   └── quy tắc nghiệp vụ
           │
       ┌───┴─────────┐
       ▼             ▼
Valid rows       Rejected / quarantine
       │             │
       ▼             └── raw payload + reason
Typed SQL columns
       │
       ▼
JOIN / GROUP BY / index / báo cáo
```

### 33.1. Vì sao tách ba tầng?

- **Raw:** giữ payload ban đầu để có thể điều tra khi quy tắc thay đổi.
- **Validated:** biết dòng nào đúng schema và vì sao dòng khác bị từ chối.
- **Typed:** dữ liệu đã có `numeric`, `date`, `boolean`, `bigint`, giúp SQL tính toán và tối ưu ổn định.

### 33.2. Cột metadata gợi ý

| Cột | Ý nghĩa |
|---|---|
| `source_event_id` | Định danh sự kiện từ nguồn |
| `received_at` | Lúc hệ thống nhận payload |
| `schema_version` | Phiên bản định dạng nguồn |
| `raw_payload` | Tài liệu JSON gốc |
| `validation_status` | `VALID` / `INVALID` / `MISSING`... |
| `validation_error` | Lý do lỗi có kiểm soát |
| `total_amount` | Số SQL đã chuẩn hóa |
| `paid` | Boolean SQL |
| `order_date` | Ngày SQL |
| `currency` | Đơn vị tiền tệ rõ ràng |

Đừng để downstream BI tiếp tục tự thực hiện những phép cast không nhất quán nếu quy tắc định dạng có thể được chuẩn hóa ngay tại cửa vào.

## 34. Phân biệt trích xuất, lọc và kiểm chứng sau trích xuất

Một biểu thức:

```sql
payload #>> '{order,total}'
```

chỉ làm việc **trích xuất text**. Nó không tự:

- Đảm bảo trường có thật.
- Đảm bảo kiểu JSON nguồn đúng.
- Đảm bảo chuỗi có thể chuyển thành số.
- Đảm bảo số không âm.
- Đảm bảo tiền tệ đúng.
- Đảm bảo đơn hàng chưa bị hoàn hoặc hủy.

Một truy vấn:

```sql
SELECT
    event_id,
    (payload #>> '{order,total}')::numeric AS amount
FROM json_lab_events
WHERE payload ->> 'event_type' = 'checkout';
```

có thể thất bại hoặc tạo số không mong muốn tùy dữ liệu.

### 34.1. Một chuỗi quyết định rõ ràng hơn

```text
event_type có phù hợp?
      │
      ▼
order có phải object?
      │
      ▼
total có tồn tại?
      │
      ▼
total là number/string/null?
      │
      ▼
cú pháp có được chấp nhận?
      │
      ▼
giá trị có nằm trong miền?
      │
      ▼
cast thành SQL NUMERIC
      │
      ▼
áp quy tắc tiền tệ, trạng thái, nghiệp vụ
```

Sự khác biệt giữa một câu query “có vẻ chạy được” và một pipeline đáng tin cậy nằm ở những quyết định này.

## 35. Những lỗi thường gặp và cách nhận biết

| Sai lầm | Tác động | Cách đúng |
|---|---|---|
| Nghĩ `->>` trả kiểu số vì JSON là number | So sánh/sắp xếp dạng text | Cast có kiểm soát sang `numeric`/`integer` |
| Cast toàn bộ `->>` khi nguồn không sạch | Một dòng `'N/A'` làm query lỗi | Kiểm tra kiểu/format hoặc chuẩn hóa trước |
| Cho rằng JSON string `"120"` chính là JSON number `120` | Mất kiểm soát schema | Xác định strict/tolerant policy |
| Nhầm `jsonb_typeof` với `pg_typeof` | Đọc sai kiểu nguồn và kiểu biểu thức | Dùng cả hai đúng ngữ cảnh |
| Dùng `->>` ở giữa đường dẫn rồi tiếp tục `->` | Không còn JSONB để đi sâu | Dùng `->` trung gian, `->>` cuối |
| Nghĩ JSON có kiểu date | Không kiểm soát format và timezone | Cast sang `date`/`timestamptz` theo hợp đồng |
| So `total` theo chuỗi | Thứ tự/điều kiện số sai | So numeric |
| Đồng nhất missing và JSON null | Mất thông tin dữ liệu | Kiểm tra key, JSON type trước lấy text |
| Đồng nhất `NULL`, `''` và `0` | Báo cáo số liệu sai | Định nghĩa ý nghĩa từng trạng thái |
| Dùng `COALESCE(cast,0)` để chữa `'N/A'` | Cast lỗi trước `COALESCE` | Validation, `CASE`, quarantine |
| Regex ngày hợp lệ về hình thức là đủ | `"2026-02-30"` vẫn sai | Parser date và kiểm tra format |
| Tin `pg_input_is_valid` hỗ trợ mọi phiên bản | Query lỗi vì hàm không tồn tại | Kiểm tra PostgreSQL >=16 và hạn chế |
| Kiểm tra numeric nhưng không kiểm tra `numeric(12,2)` | Overflow khi ép kiểu đích | Kiểm tra miền/precision |
| Bỏ qua `NULL` trong `CHECK` | Missing key vượt constraint | Dùng `IS TRUE` hoặc ràng buộc rõ |
| `jsonb_array_elements` trên object | Lỗi không phải mảng | Kiểm tra `jsonb_typeof='array'` |
| `CROSS JOIN LATERAL` rồi quên outer bị loại nếu array rỗng | Mất sự kiện khi đếm | Chọn `LEFT JOIN LATERAL` nếu cần giữ |
| SUM tổng đơn sau explode item | Nhân tổng tiền | Tổng item về khóa event trước |
| Nhầm JSON array index 0 với `WITH ORDINALITY` 1 | Sai vị trí | Nêu rõ hệ đánh số |
| Cho `jsonb_to_recordset` là validator chống lỗi | Cast vẫn có thể thất bại | Xác thực trước |
| Index text rồi so như số | Range/sort sai ngữ nghĩa | Dùng numeric expression/typed column |
| Tạo index cast numeric trên dữ liệu bẩn | Lỗi khi xây index | Chuẩn hóa dữ liệu trước |
| Dùng GIN cho mọi loại query JSON | Index không phù hợp toán tử/range | Chọn theo query và operator class |
| Bỏ qua schema version | Lấy nhầm object thành scalar | Chuẩn hóa theo phiên bản |
| Dùng mọi dữ liệu timestamp như UTC | Sai ngày/giờ theo múi | Xác định offset và timezone |
| Đưa dữ liệu nhạy cảm vào payload không kiểm soát | Rủi ro lộ PII | Phân quyền, mã hóa/masking, chỉ xuất cột cần |

## 36. Bài tập tự luyện

Các bài tập sau dùng bảng `json_lab_events` đã tạo ở mục 4, trừ khi đề cung cấp JSON literal riêng. Đừng thay đổi các dòng mẫu nếu muốn đối chiếu kết quả. Những bài có JSON sai kiểu yêu cầu **giải thích/viết truy vấn phòng lỗi**, không bắt buộc chạy câu cast cố ý gây lỗi.

### Bài 1 — Kiểu SQL sau trích xuất

Cho:

```sql
'{"value":120.50}'::jsonb -> 'value'
'{"value":120.50}'::jsonb ->> 'value'
('{"value":120.50}'::jsonb ->> 'value')::numeric
```

Hãy nêu kiểu SQL của từng biểu thức.

### Bài 2 — Kiểu JSON và SQL

Phân biệt ý nghĩa của `jsonb_typeof(payload -> 'event_type')` và `pg_typeof(payload ->> 'event_type')`.

### Bài 3 — Trích xuất object lồng nhau

Viết hai cách lấy `user.id` ở dạng text từ event 1: chuỗi `->`/`->>` và toán tử đường dẫn `#>>`.

### Bài 4 — Lấy số

Viết câu SELECT lấy `order.total` thành SQL `numeric` cho các event `1, 2, 5, 8, 9`. Vì sao không nên mở rộng câu cast trực tiếp ra toàn bảng?

### Bài 5 — Numeric vs text

Vì sao điều kiện:

```sql
payload #>> '{order,total}' > '90'
```

không tương đương:

```sql
(payload #>> '{order,total}')::numeric > 90
```

khi dữ liệu hợp lệ?

### Bài 6 — Missing và JSON null

Event 3 có `order.total=null`; event 7 không có `order`. Dùng `jsonb_typeof` và phép kiểm tra khóa để phân biệt chúng.

### Bài 7 — Chuỗi rỗng

JSON `{ "x": "" }` khác `{ "x": null }` và `{}` như thế nào sau `->>`? Tại sao không nên tự đổi cả ba thành 0?

### Bài 8 — Boolean strict

Viết `CASE` chỉ chấp nhận `order.paid` là JSON boolean, trả SQL boolean. Event 2 có `paid="true"` được nhận không?

### Bài 9 — Boolean tolerant

Viết một nhánh kiểm tra thêm cho JSON string chỉ có giá trị `true` hoặc `false` (không phân biệt hoa/thường), rồi cast Boolean.

### Bài 10 — Ngày hợp lệ

Trong dữ liệu mẫu, event 4 có `created_at="2026-02-30"`. Vì sao kiểm tra định dạng `YYYY-MM-DD` bằng regex chưa đủ? Đề xuất cách kiểm tra ở PostgreSQL 16+.

### Bài 11 — `TIMESTAMPTZ`

Một JSON chứa `"2026-08-01T23:30:00+07:00"`. Viết SQL lấy thành `timestamptz`, rồi lấy ngày theo `Asia/Ho_Chi_Minh`. Vì sao không nên tùy tiện cast thẳng sang `timestamp without time zone`?

### Bài 12 — Unix milliseconds

API gửi timestamp ở đơn vị mili-giây. Viết câu SQL chuyển sang `timestamptz` bằng `to_timestamp` và giải thích vai trò `/ 1000.0`.

### Bài 13 — Kiểu JSON number strict

Viết `CASE` chỉ chuyển `order.total` thành numeric khi `jsonb_typeof(...)= 'number'`. Event 2, 4, 9 được nhận không?

### Bài 14 — `pg_input_is_valid`

PostgreSQL 16+: viết truy vấn kiểm tra text của `order.total` có thể chuyển sang `numeric` trước khi cast. Tại sao chưa đủ để bảo đảm phù hợp `numeric(12,2)`?

### Bài 15 — Regex

Biểu thức `^[0-9]+([.][0-9]+)?$` chấp nhận `'120.50'` và từ chối `'1e3'`. Đây là lỗi hay là lựa chọn chính sách? Còn giới hạn gì?

### Bài 16 — Đọc item đầu

Viết SQL lấy `sku` và `qty` của item đầu tiên trong event 1. JSON array bắt đầu từ chỉ số bao nhiêu?

### Bài 17 — Mảng không đồng nhất

Event 8 có `"tags":"web"` thay vì mảng. Vì sao `jsonb_array_elements(payload->'tags')` không phải truy vấn an toàn trên mọi dòng?

### Bài 18 — `CROSS JOIN LATERAL`

Viết SQL bung `order.items` của event 1 thành các dòng `sku, qty, unit_price`. Kết quả có bao nhiêu dòng?

### Bài 19 — Tổng item

Tính `qty * unit_price` và tổng item cho event 1. Giải thích tại sao không nên SUM `order.total` sau khi bung item mà chưa xét độ hạt.

### Bài 20 — `LEFT JOIN LATERAL`

Viết câu lấy toàn bộ event và `sku` nếu có; những event có mảng trống hoặc không phải mảng vẫn cần có **một dòng**. Làm sao tránh lỗi khi `items` là object/null?

### Bài 21 — `WITH ORDINALITY`

So sánh vị trí đầu tiên của JSON array khi dùng `-> 0` với số thứ tự từ `WITH ORDINALITY`. Chúng bắt đầu từ số mấy?

### Bài 22 — `jsonb_to_record`

Viết SQL chuyển object `{"total":120.50,"paid":true,"created_at":"2026-08-01"}` thành các cột `numeric`, `boolean`, `date`. Hàm này có tự bỏ qua `"total":"N/A"` không?

### Bài 23 — `jsonb_to_recordset`

Viết cách chuyển mảng hai item thành bảng có các cột `sku text`, `qty integer`, `unit_price numeric`. Nêu rủi ro nếu một item có `qty="two"`.

### Bài 24 — Containment

Viết query tìm event có `order.paid` là **JSON boolean true** bằng `@>`. Event 2 với chuỗi `"true"` có thỏa không?

### Bài 25 — SQL NULL trong CHECK

Vì sao:

```sql
CHECK (jsonb_typeof(payload -> 'total') = 'number')
```

chưa chắc từ chối JSON thiếu khóa `total`? Viết cách dùng `IS TRUE`.

### Bài 26 — Generated column

Một bảng có `payload jsonb` và generated column `total_amount numeric(12,2)` lấy từ payload. Việc chèn `"total":"N/A"` có thể xảy ra điều gì? Kiểu JSON nguồn đã được strict kiểm soát chưa?

### Bài 27 — Index cho JSON

So sánh ba nhu cầu: lọc `event_type` bằng text, kiểm tra containment `@>`, và sắp `total_amount` theo số. Bạn cân nhắc index nào cho từng nhu cầu?

### Bài 28 — Schema version

Version 1 chứa `order.total` là số, version 2 chứa `order.total.value`. Viết `CASE` chọn đường dẫn thích hợp theo `schema_version`. Vì sao cần xác thực version trước?

### Bài 29 — Tổng hợp số hợp lệ

Viết một truy vấn `CASE` chỉ lấy JSON number ở `order.total`, loại NULL, rồi tính `COUNT` và `SUM`. Giải thích vì sao dòng 6 có số âm có thể vẫn cần kiểm tra nghiệp vụ.

### Bài 30 — Thiết kế kết quả ETL

Đề xuất các cột để lưu dữ liệu đã chuẩn hóa từ JSON và lý do từ chối payload. Vì sao lưu mỗi `total_amount NULL` không đủ để điều tra?

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** Lần lượt `jsonb`, `text`, `numeric`. Có thể kiểm tra bằng `pg_typeof(...)`.

**Bài 2:** `jsonb_typeof` trả tên **kiểu JSON bên trong** dưới dạng text, ví dụ `'string'`. `pg_typeof(payload->>'event_type')` trả **kiểu SQL của biểu thức**, là `text`.

**Bài 3:**

```sql
SELECT
    payload -> 'user' ->> 'id' AS way_1,
    payload #>> '{user,id}' AS way_2
FROM json_lab_events
WHERE event_id = 1;
-- '101' và '101', đều là text.
```

**Bài 4:**

```sql
SELECT event_id,
       (payload #>> '{order,total}')::numeric AS total
FROM json_lab_events
WHERE event_id IN (1,2,5,8,9)
ORDER BY event_id;
```

Toàn bảng có `'N/A'`, Boolean true và chuỗi `'12,50'` không cast được sang numeric theo hợp đồng ví dụ.

**Bài 5:** `#>>` trả text, so sánh theo thứ tự ký tự/collation; `::numeric` so sánh theo giá trị số. Ví dụ text `'100'` và `'9'` cho thứ tự không giống 100 và 9.

**Bài 6:**

```sql
SELECT
    event_id,
    jsonb_typeof(payload -> 'order') AS order_kind,
    jsonb_typeof(payload #> '{order,total}') AS total_kind,
    (payload -> 'order') ? 'total' AS has_total
FROM json_lab_events
WHERE event_id IN (3,7);
```

Event 3 có `total_kind='null'` (text) và `has_total=true`; event 7 không có order, nên đường dẫn và điều kiện có thể trả SQL NULL.

**Bài 7:** JSON string rỗng cho text `''`; JSON null và missing khi dùng `->>` thường đều ra SQL NULL. Nhưng nguồn khác nhau, có thể ảnh hưởng xác thực, tính bắt buộc của trường và phân tích dữ liệu.

**Bài 8:**

```sql
CASE WHEN jsonb_typeof(payload #> '{order,paid}')='boolean'
     THEN (payload #>> '{order,paid}')::boolean
     ELSE NULL::boolean END
```

Event 2 có JSON string nên không được nhận trong strict policy.

**Bài 9:**

```sql
WHEN jsonb_typeof(payload #> '{order,paid}') = 'string'
 AND LOWER(BTRIM(payload #>> '{order,paid}'))
     IN ('true','false')
THEN LOWER(BTRIM(payload #>> '{order,paid}'))::boolean
```

Ghép với nhánh JSON boolean strict trong `CASE`.

**Bài 10:** Ngày 30/2 không tồn tại dù chuỗi đúng khuôn mẫu. PostgreSQL 16+ có thể kiểm tra `pg_input_is_valid(text, 'date')`, kết hợp kiểm tra format ISO mong muốn.

**Bài 11:**

```sql
SELECT
    ('{"x":"2026-08-01T23:30:00+07:00"}'::jsonb ->> 'x')
        ::timestamptz AS instant,
    (
      ('{"x":"2026-08-01T23:30:00+07:00"}'::jsonb ->> 'x')
        ::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS local_day;
```

`timestamp without time zone` không bảo toàn ngữ nghĩa thời điểm có offset.

**Bài 12:**

```sql
SELECT TO_TIMESTAMP(
    ('{"t_ms":1785605400000}'::jsonb ->> 't_ms')
        ::double precision / 1000.0
);
```

Đầu vào là milliseconds, trong khi `to_timestamp(double precision)` dùng seconds từ Unix epoch.

**Bài 13:**

```sql
CASE
  WHEN jsonb_typeof(payload #> '{order,total}')='number'
  THEN (payload #>> '{order,total}')::numeric
  ELSE NULL::numeric
END
```

Event 2, 4, 9 đều chứa **string**, không được nhận ở strict mode.

**Bài 14:**

```sql
WITH x AS (
  SELECT event_id,
         BTRIM(payload #>> '{order,total}') AS total_text
  FROM json_lab_events
)
SELECT
  event_id,
  CASE
    WHEN pg_input_is_valid(total_text, 'numeric')
    THEN total_text::numeric
    ELSE NULL::numeric
  END AS total
FROM x;
```

Numeric hợp lệ về cú pháp vẫn có thể vượt `numeric(12,2)` hoặc không thỏa ràng buộc như không âm.

**Bài 15:** Đây là **lựa chọn định dạng**: regex cố ý chỉ cho decimal không âm. Nó không chấp nhận dạng khoa học, dấu cộng/trừ; ngoài ra regex không thay việc kiểm tra độ lớn, precision và miền nghiệp vụ.

**Bài 16:**

```sql
SELECT
    payload #>> '{order,items,0,sku}' AS sku,
    (payload #>> '{order,items,0,qty}')::integer AS qty
FROM json_lab_events
WHERE event_id=1;
```

JSON array bắt đầu từ 0; kết quả `A`, `2`.

**Bài 17:** `tags` ở event 8 là JSON string, không phải array. Hàm `jsonb_array_elements` cần array; phải kiểm tra `jsonb_typeof` và chọn chính sách reject hoặc normalize.

**Bài 18:**

```sql
SELECT
  i.item ->> 'sku' AS sku,
  (i.item ->> 'qty')::integer AS qty,
  (i.item ->> 'unit_price')::numeric AS unit_price
FROM json_lab_events AS e
CROSS JOIN LATERAL jsonb_array_elements(
  e.payload #> '{order,items}'
) AS i(item)
WHERE e.event_id=1
ORDER BY sku;
```

Có hai dòng: A và B.

**Bài 19:** A: `2 * 30.25 = 60.50`; B: `1 * 60 = 60`; tổng item event 1 là **120.50**. Nếu SUM `order.total` sau khi đã bung hai item, có thể cộng cùng 120.50 hai lần.

**Bài 20:**

```sql
SELECT e.event_id, i.item ->> 'sku' AS sku
FROM json_lab_events AS e
LEFT JOIN LATERAL jsonb_array_elements(
    CASE
      WHEN jsonb_typeof(e.payload #> '{order,items}')='array'
      THEN e.payload #> '{order,items}'
      ELSE '[]'::jsonb
    END
) AS i(item) ON TRUE;
```

Nhánh ELSE tránh gọi hàm với non-array; LEFT JOIN giữ outer row. Cần ghi trạng thái invalid riêng nếu `items` bắt buộc là array.

**Bài 21:** Chỉ số mảng JSON ở toán tử `-> 0` bắt đầu từ **0**; `WITH ORDINALITY` đánh số dòng sinh từ **1**.

**Bài 22:**

```sql
SELECT *
FROM jsonb_to_record(
    '{"total":120.50,"paid":true,"created_at":"2026-08-01"}'::jsonb
) AS x(total numeric, paid boolean, created_at date);
```

Không. `total="N/A"` có thể khiến ép kiểu numeric thất bại.

**Bài 23:**

```sql
SELECT *
FROM jsonb_to_recordset(
    '[{"sku":"A","qty":2,"unit_price":30.25},
      {"sku":"B","qty":1,"unit_price":60.00}]'::jsonb
) AS x(sku text, qty integer, unit_price numeric);
```

Chuỗi `"two"` không chuyển được sang integer, có thể làm lỗi toàn câu.

**Bài 24:**

```sql
SELECT event_id
FROM json_lab_events
WHERE payload @> '{"order":{"paid":true}}'::jsonb
ORDER BY event_id;
```

Event 2 có JSON string `"true"`, nên không thỏa phép containment yêu cầu JSON boolean true.

**Bài 25:** `CHECK` chấp nhận UNKNOWN do SQL NULL. Dùng:

```sql
CHECK (
    (jsonb_typeof(payload -> 'total')='number') IS TRUE
)
```

để từ chối cả missing và non-number khi `total` là khóa cấp ngoài.

**Bài 26:** Cột generated phải cast thành công khi ghi; `"N/A"` có thể khiến `INSERT`/`UPDATE` lỗi. Nhưng một chuỗi hợp lệ `"80.00"` vẫn có thể được cast, nên cần kiểm tra JSON type nếu contract strict.

**Bài 27:** Với `event_type` text, cân nhắc B-tree expression index `(payload->>'event_type')`. Với `@>`, cân nhắc GIN index `payload`. Với range/sort số, cân nhắc B-tree trên cột SQL `numeric` đã chuẩn hóa hoặc expression cast an toàn trên dữ liệu sạch.

**Bài 28:**

```sql
CASE (doc->>'schema_version')::integer
  WHEN 1 THEN (doc #>> '{order,total}')::numeric
  WHEN 2 THEN (doc #>> '{order,total,value}')::numeric
  ELSE NULL::numeric
END
```

Ví dụ giả định version hợp lệ; trong dữ liệu thực cần validate `schema_version` trước cast và reject version chưa hỗ trợ.

**Bài 29:**

```sql
WITH normalized AS (
    SELECT
      CASE
        WHEN jsonb_typeof(payload #> '{order,total}')='number'
        THEN (payload #>> '{order,total}')::numeric
        ELSE NULL::numeric
      END AS total_amount
    FROM json_lab_events
)
SELECT
    COUNT(total_amount) AS valid_numeric_count,
    SUM(total_amount) AS numeric_total
FROM normalized;
```

Trong strict JSON-type, dòng 6 có `-10.25` vẫn là numeric hợp lệ nhưng có thể vi phạm tiền không âm. Nếu nghiệp vụ cần số không âm, thêm validation riêng.

**Bài 30:** Nên lưu raw payload, source event ID, schema version, thời điểm nhận, validation status/error, `total_amount numeric`, `paid boolean`, `order_date date`, currency và metadata nguồn. Chỉ lưu NULL không thể phân biệt missing, JSON null, wrong type, lỗi format và vượt miền.

</details>

## 37. Sổ tay trích xuất nhanh

| Mục tiêu | Biểu thức PostgreSQL | Kết quả / lưu ý |
|---|---|---|
| Lấy khóa dưới dạng JSONB | `doc -> 'key'` | `jsonb` |
| Lấy khóa dưới dạng text | `doc ->> 'key'` | `text` |
| Lấy đường dẫn lồng nhau JSONB | `doc #> '{a,b}'` | `jsonb` |
| Lấy đường dẫn lồng nhau text | `doc #>> '{a,b}'` | `text` |
| Kiểm tra kiểu bên trong JSON | `jsonb_typeof(doc -> 'key')` | text `'number'`, `'string'`... |
| Kiểm tra kiểu của biểu thức SQL | `pg_typeof(expr)` | `jsonb`, `text`, `numeric`... |
| Lấy số | `(doc->>'amount')::numeric` | Chỉ khi dữ liệu cast được |
| Lấy integer | `(doc->>'id')::integer` | Kiểm tra format và range |
| Lấy Boolean | `(doc->>'paid')::boolean` | Kiểm soát kiểu/policy |
| Lấy ngày | `(doc->>'day')::date` | JSON không có date native |
| Lấy thời điểm có offset | `(doc->>'at')::timestamptz` | Xác định timezone |
| Kiểm tra khóa cấp ngoài | `doc ? 'key'` | Boolean, không đệ quy |
| JSON null | `jsonb_typeof(doc->'key')='null'` | Khác SQL NULL |
| Truy cập item đầu | `doc->'items'->0` | Index JSON bắt đầu từ 0 |
| Bung mảng | `jsonb_array_elements(doc->'items')` | Một dòng mỗi item |
| Bung mảng thành text | `jsonb_array_elements_text(...)` | Text từng phần tử |
| Object thành record | `jsonb_to_record(...)` | Khai báo kiểu cột |
| Mảng object thành recordset | `jsonb_to_recordset(...)` | Dữ liệu bẩn vẫn có thể lỗi |
| Đường dẫn JSON phức tạp | `jsonb_path_exists(...)` | JSONPath |
| Containment | `doc @> '{"a":1}'::jsonb` | Phân biệt JSON string/number |
| Kiểm tra text cast được | `pg_input_is_valid(text,'numeric')` | PostgreSQL 16+ và các giới hạn |
| Lấy scalar an toàn hơn | `CASE WHEN type_ok THEN text::type END` | Cần kiểm soát thêm miền |

### 37.1. Ba mẫu quan trọng nhất

**Mẫu 1 — Trích xuất số đã biết schema sạch:**

```sql
SELECT
    event_id,
    (payload #>> '{order,total}')::numeric AS total_amount
FROM json_lab_events
WHERE event_id IN (1, 5, 14);
```

**Mẫu 2 — Không cast sai kiểu JSON:**

```sql
SELECT
    event_id,
    CASE
        WHEN jsonb_typeof(payload #> '{order,total}') = 'number'
        THEN (payload #>> '{order,total}')::numeric
        ELSE NULL::numeric
    END AS total_amount
FROM json_lab_events;
```

**Mẫu 3 — Bung array, giữ dấu vết event:**

```sql
SELECT
    e.event_id,
    i.item ->> 'sku' AS sku
FROM json_lab_events AS e
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(e.payload #> '{order,items}') = 'array'
        THEN e.payload #> '{order,items}'
        ELSE '[]'::jsonb
    END
) AS i(item);
```

## 38. Kết luận

Trích xuất JSON theo kiểu dữ liệu không chỉ là biết cú pháp `->>` hoặc `#>>`. Điểm quan trọng nhất là **nối chính xác ba tầng ý nghĩa**:

```text
Giá trị trong JSON
    │
    ├── number / string / boolean / object / array / null / missing
    │
    ▼
Biểu thức trích xuất PostgreSQL
    │
    ├── ->, #>   → JSONB
    └── ->>, #>> → TEXT
    │
    ▼
Giá trị SQL đúng kiểu
    │
    ├── numeric / integer / boolean
    ├── date / timestamptz
    ├── record / các dòng phần tử array
    └── NULL có ý nghĩa đã được định nghĩa
    │
    ▼
Validation + logic nghiệp vụ + báo cáo
```

Hãy nhớ bốn nguyên tắc:

1. **Biết kiểu nguồn và kiểu đích:** JSON number chưa tự là SQL numeric, JSON string dạng ngày chưa tự là SQL date. `->>` luôn trả text, còn `->` giữ giá trị JSON.
2. **Đừng cast dữ liệu không tin cậy một cách mù quáng:** phân biệt missing, JSON null, empty string, sai kiểu, sai định dạng và vượt miền; dùng schema validation, `CASE`, hoặc `pg_input_is_valid` khi phiên bản hỗ trợ.
3. **Giữ đúng độ hạt khi xử lý mảng:** `jsonb_array_elements` biến một sự kiện thành nhiều dòng; tổng hợp theo item phải được ghép trở lại đúng khóa trước khi cộng các giá trị cấp đơn.
4. **Thiết kế dữ liệu có kiểu cho những gì cần tính toán:** JSONB phù hợp dữ liệu linh hoạt, nhưng trường số/ngày/Boolean quan trọng nên có hợp đồng, kiểm soát chất lượng và chỉ mục phù hợp với cách truy vấn thực.

Khi bạn biết một trường JSON đang là **number hay string**, khi nào chuyển thành **SQL `NUMERIC`**, và làm sao **tách một giá trị sai thành lý do lỗi thay vì làm hỏng cả câu truy vấn**, bạn đã có nền tảng để sử dụng dữ liệu JSON mở rộng một cách chính xác, dễ truy vết và đáng tin cậy.
