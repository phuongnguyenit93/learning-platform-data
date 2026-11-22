# Lưu trữ JSON và kiểm tra tính hợp lệ trong Database SQL

Dữ liệu của một hệ thống không phải lúc nào cũng vừa khít vào các cột cố định. Một đơn hàng có nhiều dòng hàng, một bản ghi nhật ký có phần metadata tùy loại sự kiện, hoặc một ứng dụng nhận webhook với những thuộc tính có thể thay đổi theo phiên bản. **JSON (JavaScript Object Notation)** là một định dạng trao đổi dữ liệu phổ biến cho các trường hợp như vậy.

Ví dụ một sự kiện tạo đơn hàng:

```json
{
  "event_type": "ORDER_CREATED",
  "order_id": 1001,
  "tenant_id": 10,
  "items": [
    { "sku": "MOUSE-01", "qty": 2, "unit_price": 350.50 },
    { "sku": "PAD-01", "qty": 1, "unit_price": 80.00 }
  ],
  "metadata": {
    "channel": "web",
    "coupon": null
  }
}
```

Có thể lưu cả tài liệu đó trong **một cột JSON**, nhưng phải phân biệt ít nhất ba câu hỏi:

1. **Đúng cú pháp JSON chưa?** Dấu ngoặc, dấu phẩy, chuỗi, số, escape và literal có hợp lệ không?
2. **Đúng cấu trúc dự kiến chưa?** Có trường `event_type`, `order_id`, `items` không? `order_id` có đúng là số? `items` có là mảng?
3. **Đúng quy tắc nghiệp vụ và bảo mật chưa?** Tenant có quyền tạo đơn này không? SKU tồn tại không? Số lượng dương không? Có dữ liệu cá nhân bị đưa vào log không?

Một hệ quản trị có thể kiểm tra tốt lớp **cú pháp**, nhưng điều đó **không tự chứng minh** lớp cấu trúc hay nghiệp vụ. Bài này thuộc chương **Dữ liệu mở rộng** của module **Database SQL**, giải thích cách lưu JSON và kiểm tra tính hợp lệ trên **PostgreSQL, MySQL, MariaDB, SQL Server, Oracle và SQLite**, có ví dụ thực hành, thiết kế schema, chỉ mục, xử lý `NULL`, giới hạn và bài tập.

> Các phần demo chính sử dụng **PostgreSQL**, có thể chạy trên cơ sở dữ liệu thử với quyền tạo bảng tạm. Ví dụ của DBMS khác được đánh dấu riêng và **không dùng chung một cú pháp SQL**. Khi thử dữ liệu JSON sai, PostgreSQL có thể báo lỗi và hủy statement hiện tại; hãy thực hiện từng thử nghiệm riêng hoặc dùng `SAVEPOINT`/`ROLLBACK` phù hợp.

## 1. JSON là một định dạng dữ liệu, không phải “chuỗi nào trông giống object”

JSON theo chuẩn hiện đại cho phép một **giá trị JSON ở cấp gốc** (*top-level value*) thuộc các loại:

| Loại JSON | Ví dụ JSON | Ý nghĩa |
|---|---|---|
| Object | `{"id": 7, "ok": true}` | Tập các cặp khóa–giá trị |
| Array | `[1, "x", false]` | Danh sách có thứ tự |
| String | `"hello"` | Chuỗi trong dấu nháy kép |
| Number | `42`, `-1.5`, `1e3` | Giá trị số theo cú pháp JSON |
| Boolean | `true`, `false` | Hai literal viết **chữ thường** |
| Null | `null` | Literal null của JSON |

Một JSON object có **key là chuỗi**, nằm trong dấu nháy kép:

```json
{ "name": "An", "age": 22 }
```

Đây **không** phải JSON chuẩn:

```text
{ name: 'An', age: 22 }
```

Đoạn trên giống cú pháp object literal của JavaScript hơn: tên key không có nháy kép và giá trị chuỗi dùng nháy đơn.

### 1.1. Một số quy tắc cú pháp quan trọng

- Khóa object phải là **chuỗi trong dấu nháy kép**.
- Chuỗi JSON dùng dấu nháy kép; dấu nháy đơn không thay thế được.
- Phần tử array và cặp object được ngăn bằng dấu phẩy, nhưng **không có dấu phẩy thừa ở cuối** trong JSON chuẩn.
- Boolean và null viết đúng `true`, `false`, `null`, không phải `True`, `False`, `NULL`.
- **Không có comment** `// ...` hay `/* ... */` trong JSON chuẩn.
- Số JSON **không dùng `NaN`, `Infinity`** hay `+12` ở định dạng chuẩn.
- Số JSON không được có số 0 đứng đầu theo kiểu `0012`, trừ số `0` và dạng thập phân/hàm mũ hợp lệ.
- Dữ liệu văn bản cần được mã hóa hợp lệ, xử lý escape như `\"`, `\\`, `\n`, `\uXXXX` theo chuẩn JSON.

### 1.2. Bảng phân biệt hợp lệ và không hợp lệ

| Dữ liệu | JSON chuẩn? | Giải thích |
|---|---|---|
| `{"id":1}` | Có | Object hợp lệ |
| `[1,2,3]` | Có | Array hợp lệ |
| `"An"` | Có | JSON string, khác chuỗi SQL `'An'` |
| `123` | Có | Top-level number hợp lệ theo RFC 8259 |
| `true` | Có | Top-level boolean hợp lệ |
| `null` | Có | JSON null hợp lệ |
| `{id:1}` | Không | Key chưa đặt trong nháy kép |
| `{'id':1}` | Không | Nháy đơn không phải nháy JSON |
| `{"id":1,}` | Không | Có trailing comma |
| `{"ok":True}` | Không | `True` không phải JSON literal |
| `[1,,2]` | Không | Thiếu giá trị giữa hai dấu phẩy |
| `{"n":NaN}` | Không | `NaN` không thuộc number JSON chuẩn |
| `{"n":01}` | Không | Số có leading zero không hợp lệ |
| `// note\n{"id":1}` | Không | Comment không thuộc JSON chuẩn |

**Lưu ý đặc biệt:** Một số parser hỗ trợ **JSON5** hoặc biến thể “lax”. Chúng có thể chấp nhận comment, dấu nháy đơn và dấu phẩy cuối. **Chấp nhận JSON5 không đồng nghĩa chuỗi đó là JSON chuẩn** để trao đổi với hệ khác.

## 2. JSON hợp lệ về cú pháp chưa chắc hợp lệ về nghiệp vụ

Hai tài liệu sau **đều đúng cú pháp JSON**:

```json
{"event_type":"ORDER_CREATED","order_id":1001,"items":[]}
```

```json
{"event_type":"ORDER_CREATED","order_id":"abc","items":"not an array"}
```

Nhưng nếu nghiệp vụ quy định:

- `event_type` phải là một trong các giá trị cho phép.
- `order_id` phải là số nguyên dương.
- `items` phải là array, có ít nhất một phần tử.
- Mỗi phần tử `items` phải có `sku` và `qty` nguyên dương.

thì tài liệu thứ hai sai cấu trúc; tài liệu thứ nhất còn có thể không hợp lệ vì mảng `items` rỗng.

Ta cần phân biệt các lớp kiểm tra:

| Lớp | Ví dụ câu hỏi | Cơ chế thường dùng |
|---|---|---|
| **Cú pháp** | Dấu ngoặc/phẩy, literal đúng chưa? | Kiểu JSON, parser, `JSON_VALID`, `ISJSON` |
| **Loại gốc** | Root có phải object thay vì array/scalar? | `jsonb_typeof`, `JSON_TYPE`, `IS JSON OBJECT` |
| **Cấu trúc** | Trường bắt buộc có đúng kiểu? | CHECK với JSON operators, JSON Schema, validation service |
| **Miền giá trị** | `status` có thuộc tập cho phép? | CHECK, enum/tables hoặc schema validation |
| **Quan hệ** | `order_id`/`sku` có tồn tại ở bảng khác? | Khóa ngoại trên cột quan hệ, service/trigger |
| **Phân quyền** | Caller có quyền với `tenant_id`? | Authentication, authorization, RLS, permission |
| **Quy mô** | Tài liệu quá lớn hoặc quá sâu? | Giới hạn API, parser, DB, thời gian/tài nguyên |

**Không xem `JSON_VALID(payload) = 1` là bằng chứng `order_id` tồn tại, đúng kiểu hay thuộc tenant của người gọi.**

## 3. Khi nào nên lưu JSON, khi nào nên tách thành cột hoặc bảng?

JSON phù hợp với **thuộc tính linh hoạt**, payload của sự kiện, metadata hoặc nội dung có nhiều phiên bản. Nhưng các trường có vai trò khóa/quan hệ thường nên là **cột quan hệ thông thường**.

### 3.1. Mô hình lưu tất cả trong một JSON

```sql
-- PostgreSQL, chỉ minh họa.
CREATE TABLE raw_events (
    payload jsonb NOT NULL
);
```

Ưu điểm: schema bên ngoài đơn giản, chứa payload đa dạng. Nhược điểm:

- Khó thiết kế khóa chính, tenant, trạng thái và chỉ mục chuyên biệt.
- Khó thiết lập FK dựa trên đường dẫn sâu của JSON.
- Khó đối soát nhiều phiên bản tài liệu.
- Dễ tạo truy vấn lọc bằng hàm JSON ở mọi nơi.

### 3.2. Mô hình kết hợp cột quan hệ và JSON

```sql
CREATE TABLE events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload jsonb NOT NULL
);
```

Ở đây:

- `event_id` là danh tính sự kiện.
- `tenant_id` phục vụ phân quyền, phân vùng và truy vấn.
- `event_type` là trường lọc quan trọng, có thể ràng buộc/đánh index.
- `received_at` là thời điểm hệ thống nhận sự kiện.
- `payload` chứa các phần linh hoạt, tùy phiên bản event.

Mô hình **hybrid** thường dễ bảo trì hơn “mọi thứ trong JSON” khi các trường định danh và phân quyền được dùng thường xuyên.

### 3.3. Dòng hàng đơn: nên tách bảng khi cần FK/aggregate

Một danh sách `items` trong JSON có thể phù hợp để **lưu snapshot sự kiện**, nhưng nếu mỗi dòng hàng phải có FK tới bảng `products` và cần cập nhật tồn kho độc lập, mô hình quan hệ có thể thích hợp hơn:

```text
orders(order_id, tenant_id, ...)
order_items(order_id, line_no, sku, qty, unit_price, ...)
products(sku, ...)
```

Không phải cứ JSON hỗ trợ array là thay thế hoàn toàn được khóa ngoại, normalization và transaction nhiều bảng.

## 4. PostgreSQL: kiểu json và jsonb

PostgreSQL có **hai kiểu dữ liệu riêng**:

| Khía cạnh | `json` | `jsonb` |
|---|---|---|
| Lưu trữ | Giữ nội dung JSON dạng văn bản đầu vào sau khi kiểm tra | Biểu diễn nhị phân đã phân tích |
| Kiểm tra cú pháp khi ghi | Có | Có |
| Whitespace, thứ tự key | Giữ nguyên đầu vào | Không bảo đảm giữ thứ tự/format gốc |
| Key trùng lặp | Có thể giữ các cặp key như đầu vào | Chỉ giữ một giá trị, thường là giá trị cuối |
| Đọc/truy vấn | Thường phải phân tích lại dữ liệu khi xử lý | Thuận tiện cho truy vấn và toán tử nâng cao |
| Indexing | Hạn chế hơn, có thể dùng expression theo bài toán | Hỗ trợ GIN và các chiến lược đặc thù |
| Trường hợp hay dùng | Cần giữ hình thức JSON gốc | Cần tìm kiếm, lọc và xử lý JSON trong DB |

Ví dụ:

```sql
-- PostgreSQL: cả hai đều là dữ liệu JSON hợp lệ.
SELECT '{"name":"An","count":1}'::json  AS as_json;
SELECT '{"name":"An","count":1}'::jsonb AS as_jsonb;
```

Khi giá trị không hợp lệ:

```sql
-- THỬ RIÊNG: lỗi cú pháp JSON.
SELECT '{"name":"An",}'::jsonb;
```

Không có chuyện PostgreSQL tự sửa trailing comma khi ép sang `jsonb`.

### 4.1. Lưu văn bản gốc để làm chứng cứ có cần json?

`json` của PostgreSQL bảo toàn nhiều đặc điểm văn bản như khoảng trắng, thứ tự key và key lặp. `jsonb` chuẩn hóa biểu diễn, nên **không giữ nguyên byte-for-byte chuỗi đầu vào**.

Nếu nghiệp vụ cần **lưu payload chính xác như nhận từ một webhook để đối chiếu chữ ký hoặc audit**, hãy xem xét lưu một cột **raw payload** riêng, có metadata/signature, thời điểm và chính sách bảo mật. Đừng giả định chỉ một cột `jsonb` đủ để tái tạo chữ ký tính trên nội dung byte ban đầu.

### 4.2. jsonb có thêm ràng buộc Unicode/number

PostgreSQL `jsonb` áp các kiểm tra chặt hơn trong một số trường hợp so với `json`, như escape Unicode không hợp lệ, `\u0000` hoặc số ngoài phạm vi số mà kiểu nội bộ hỗ trợ. Với payload ngoại lai, “parser A chấp nhận” không có nghĩa PostgreSQL `jsonb` chắc chắn chấp nhận cùng chuỗi.

Với JSON số cực lớn hoặc dữ liệu số cần giữ **biểu diễn văn bản gốc**, hãy xác định chính sách từ đầu; một số hệ parse số thành kiểu nội bộ với giới hạn/chuẩn hóa khác nhau.

## 5. Bảng mẫu PostgreSQL: bắt buộc object có trường cơ bản

Ta tạo bảng tạm chứa sự kiện `ORDER_CREATED`. Dùng `jsonb` để DB kiểm tra cú pháp JSON ngay khi nhận dữ liệu.

```sql
CREATE TEMP TABLE demo_json_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload JSONB NOT NULL,

    -- Không nhận JSON null, array hay scalar làm root.
    CONSTRAINT chk_payload_object
      CHECK ((jsonb_typeof(payload) = 'object') IS TRUE),

    -- event_type phải có giá trị JSON string hợp lệ.
    CONSTRAINT chk_event_type
      CHECK ((
          jsonb_typeof(payload -> 'event_type') = 'string'
          AND payload ->> 'event_type' = 'ORDER_CREATED'
      ) IS TRUE),

    -- order_id phải là JSON number có dạng số nguyên không âm.
    CONSTRAINT chk_order_id
      CHECK ((
          jsonb_typeof(payload -> 'order_id') = 'number'
          AND (payload ->> 'order_id') ~ '^[0-9]+$'
      ) IS TRUE),

    -- items phải là JSON array.
    CONSTRAINT chk_items_array
      CHECK ((
          jsonb_typeof(payload -> 'items') = 'array'
      ) IS TRUE)
);
```

Vì sao viết `(...) IS TRUE` ở một số CHECK?

- Trong SQL, điều kiện có thể trả **TRUE**, **FALSE** hoặc **UNKNOWN** (`NULL`).
- CHECK constraint PostgreSQL thông thường từ chối **FALSE**, nhưng thường **chấp nhận UNKNOWN**.
- Nếu thiếu key `items`, `payload -> 'items'` trả SQL `NULL`; `jsonb_typeof(...) = 'array'` có thể thành UNKNOWN.
- Gắn `IS TRUE` làm biểu thức CHECK thành **FALSE** khi giá trị thiếu/UNKNOWN, nên không bị lọt qua.

Đây là một bẫy quan trọng khi tạo **CHECK trên đường dẫn JSON**: chỉ viết `CHECK (jsonb_typeof(payload->'items') = 'array')` có thể không đủ để yêu cầu trường `items` tồn tại.

### 5.1. Chèn tài liệu hợp lệ

```sql
INSERT INTO demo_json_events (tenant_id, payload)
VALUES (
    10,
    '{
      "event_type": "ORDER_CREATED",
      "order_id": 1001,
      "items": [
        {"sku":"MOUSE-01","qty":2,"unit_price":350.50},
        {"sku":"PAD-01","qty":1,"unit_price":80}
      ],
      "metadata":{"channel":"web","coupon":null}
    }'::jsonb
);
```

Lệnh tạo một hàng trong bảng tạm. Các trường `items` và `metadata` nằm trong JSON, còn `tenant_id` được lưu ở cột quan hệ để làm khóa phạm vi.

### 5.2. Chèn array ở root: bị chặn

```sql
-- THỬ RIÊNG: cú pháp JSON hợp lệ, nhưng CHECK root object từ chối.
INSERT INTO demo_json_events (tenant_id, payload)
VALUES (10, '[1,2,3]'::jsonb);
```

Điểm đáng nhớ: **`[1,2,3]` là JSON hợp lệ**, nhưng **không hợp lệ với schema của bảng này**.

### 5.3. Chèn JSON hợp lệ nhưng thiếu key: bị chặn

```sql
-- THỬ RIÊNG: không có order_id hoặc items.
INSERT INTO demo_json_events (tenant_id, payload)
VALUES (10, '{"event_type":"ORDER_CREATED"}'::jsonb);
```

Các điều kiện `IS TRUE` được thiết kế để từ chối key bắt buộc khi vắng mặt.

### 5.4. order_id là string thay vì number: bị chặn

```sql
-- THỬ RIÊNG:
INSERT INTO demo_json_events (tenant_id, payload)
VALUES (
  10,
  '{"event_type":"ORDER_CREATED","order_id":"1001","items":[]}'::jsonb
);
```

Dù `"1001"` nhìn giống số, JSON type của nó là **string**. Ràng buộc yêu cầu `jsonb_typeof(...) = 'number'` nên không chấp nhận.

### 5.5. Đừng hiểu các CHECK này là JSON Schema đầy đủ

Bảng demo **chưa kiểm tra**:

- `items` phải có ít nhất một phần tử.
- Từng phần tử `items` phải là object.
- `sku` phải có và là string không rỗng.
- `qty` phải là số nguyên dương.
- `unit_price` phải không âm.
- `order_id` phải tồn tại trong bảng `orders`.
- Tổng tiền từ các phần tử phải đúng với đơn hàng.
- `tenant_id` trong payload có khớp cột tenant và quyền caller không.

Đó là các mức kiểm tra cấu trúc sâu hơn và nghiệp vụ; có thể thực hiện tại ứng dụng, JSON Schema validator hoặc trigger/ràng buộc có thiết kế phù hợp. **Càng nhét nhiều quy tắc liên bảng/array phức tạp vào CHECK, việc bảo trì có thể càng khó**.

## 6. Truy vấn JSON PostgreSQL: đọc giá trị và loại dữ liệu

PostgreSQL có toán tử phổ biến:

| Toán tử/hàm | Ý nghĩa | Kết quả điển hình |
|---|---|---|
| `payload -> 'key'` | Lấy giá trị JSON tại key | `jsonb` |
| `payload ->> 'key'` | Lấy giá trị dưới dạng SQL text | `text` hoặc SQL NULL |
| `payload #> '{a,b}'` | Lấy JSON theo đường dẫn nhiều cấp | `jsonb` |
| `payload #>> '{a,b}'` | Lấy text theo đường dẫn nhiều cấp | `text` |
| `jsonb_typeof(value)` | Loại JSON của value | `object`, `array`, `string`, `number`, `boolean`, `null` |
| `jsonb_array_length(array)` | Số phần tử array | integer, lỗi nếu đầu vào không phải array |
| `payload ? 'key'` | Kiểm tra tồn tại key cấp đầu với object | boolean |
| `payload @> '{"k":"v"}'::jsonb` | Kiểm tra JSON containment | boolean |

Ví dụ:

```sql
SELECT
    event_id,
    payload ->> 'event_type' AS event_type,
    payload -> 'order_id' AS order_id_json,
    payload ->> 'order_id' AS order_id_text,
    payload #>> '{metadata,channel}' AS channel,
    jsonb_array_length(payload -> 'items') AS item_count
FROM demo_json_events
ORDER BY event_id;
```

Tài liệu mẫu có hai phần tử trong `items` nên `item_count = 2`.

### 6.1. Dùng -> hay ->>?

```sql
SELECT
    '{"n":123}'::jsonb -> 'n'  AS json_number,
    '{"n":123}'::jsonb ->> 'n' AS sql_text;
```

`->` giữ giá trị **JSON number**; `->>` trả chuỗi SQL `'123'`. Nếu muốn tính toán số học, phải chuyển sang kiểu SQL số thích hợp:

```sql
SELECT
    (payload ->> 'order_id')::bigint AS order_id
FROM demo_json_events;
```

Trên bảng demo, CHECK hạn chế `order_id` ở dạng chuỗi chữ số, nhưng nó **chưa đặt giới hạn giá trị BIGINT**. Một số JSON number rất lớn có thể qua regex nhưng bị lỗi khi cast. Nếu cần khóa `BIGINT`, nên kiểm tra phạm vi hoặc **tách order_id thành cột bigint riêng**.

### 6.2. Toán tử -> trên đường dẫn không tồn tại

```sql
SELECT '{"a":1}'::jsonb -> 'missing' AS value;
```

Kết quả là **SQL NULL**, không phải JSON object đặc biệt cho key missing. Khi kiểm tra bắt buộc key, dùng thêm `?` hoặc những cách kiểm tra type cho kết quả FALSE rõ ràng.

### 6.3. Kiểm tra phần tử array

```sql
SELECT
    e.event_id,
    item.value ->> 'sku' AS sku,
    item.value ->> 'qty' AS qty_text
FROM demo_json_events AS e
CROSS JOIN LATERAL jsonb_array_elements(e.payload -> 'items') AS item(value)
ORDER BY e.event_id, sku;
```

Lệnh mở rộng mảng thành nhiều hàng. Dữ liệu mẫu có hai dòng hàng; kết quả có SKU và quantity từng dòng.

Không đánh đồng `qty_text` là integer: `->>` trả text, nếu cần số thì cast và kiểm tra dữ liệu trước.

## 7. SQL NULL, JSON null, key không tồn tại và chuỗi "null"

Đây là phần rất dễ gây lỗi trong code.

### 7.1. Bốn tình huống khác nhau

| Tình huống | Ví dụ | Ý nghĩa |
|---|---|---|
| **SQL NULL** | `NULL::jsonb` | Ô SQL không có giá trị |
| **JSON null** | `'null'::jsonb` | Ô có một **giá trị JSON** là null |
| **Key không tồn tại** | `'{}'::jsonb -> 'a'` | Truy cập path thiếu; thường trả SQL NULL |
| **JSON string "null"** | `'"null"'::jsonb` | Chuỗi chứa bốn ký tự n-u-l-l |

Ví dụ:

```sql
SELECT
    jsonb_typeof(NULL::jsonb)      AS sql_null_type,
    jsonb_typeof('null'::jsonb)    AS json_null_type,
    jsonb_typeof('"null"'::jsonb)  AS string_null_type;
```

Kết quả logic:

- `sql_null_type` là **SQL NULL**.
- `json_null_type` là text `'null'`.
- `string_null_type` là text `'string'`.

### 7.2. Truy cập path có thể làm mất phân biệt

```sql
SELECT
    '{"coupon":null}'::jsonb ? 'coupon' AS key_exists,
    '{"coupon":null}'::jsonb -> 'coupon' AS as_json,
    '{"coupon":null}'::jsonb ->> 'coupon' AS as_text;
```

- `key_exists` là TRUE.
- `as_json` là **giá trị JSON null**.
- `as_text` là **SQL NULL**.

Với `'{}'::jsonb`, `? 'coupon'` là FALSE và `-> 'coupon'` là SQL NULL. Nếu nghiệp vụ phân biệt **“client gửi coupon:null”** và **“client không gửi coupon”**, chỉ đọc `->>` là không đủ.

### 7.3. NOT NULL chưa chắc cấm JSON null

Với PostgreSQL:

```sql
CREATE TEMP TABLE demo_not_null_json (
    id INTEGER PRIMARY KEY,
    payload jsonb NOT NULL
);

INSERT INTO demo_not_null_json VALUES (1, 'null'::jsonb);
```

Câu INSERT hợp lệ: cột **không phải SQL NULL**; nó chứa JSON null. Nếu nghiệp vụ đòi root object, phải thêm điều kiện:

```sql
CHECK ((jsonb_typeof(payload) = 'object') IS TRUE)
```

Tương tự, một cột cho phép SQL NULL có thể chứa cả JSON document mang giá trị null. Phải quyết định rõ ý nghĩa của hai trường hợp.

## 8. Key trùng lặp: JSON đúng cú pháp có thể nhập nhằng

Ví dụ:

```json
{"role":"viewer","role":"admin"}
```

Nhiều bộ parse JSON **không coi key trùng là lỗi cú pháp** theo cách mặc định. Nhưng ngữ nghĩa có thể khác:

- PostgreSQL `json` giữ nhiều key trong văn bản.
- PostgreSQL `jsonb` giữ một giá trị cuối khi chuẩn hóa key trùng.
- MySQL lưu JSON ở biểu diễn chuẩn hóa và có chính sách xử lý duplicate keys riêng.
- MariaDB lưu dạng văn bản, một số hàm truy xuất key trùng có cách chọn khác.
- SQL Server `ISJSON` **không kiểm tra key unique** cùng cấp.
- Một số công cụ JSON Schema/parser có tùy chọn strict duplicate detection; cần bật khi chính sách yêu cầu.

### 8.1. Tại sao nguy hiểm?

Một gateway đọc key đầu có thể hiểu `role = viewer`, nhưng dịch vụ ghi DB đọc key cuối và hiểu `role = admin`. Nếu hai lớp đồng thời dùng JSON cho **phân quyền**, sự không nhất quán có thể tạo lỗ hổng.

**Khuyến nghị:** với dữ liệu nhận từ bên ngoài, đặc biệt chứa quyền, giá, tenant, trạng thái hoặc chữ ký, nên **từ chối duplicate keys** theo một parser có chính sách rõ ràng ở cổng nhập, thay vì dựa vào “đằng nào jsonb cũng chuẩn hóa”.

### 8.2. Không phụ thuộc thứ tự object keys

JSON object mang ý nghĩa ánh xạ key–value; không dùng thứ tự key làm quy tắc nghiệp vụ. Nếu cần thứ tự, dùng JSON array hoặc trường thứ tự rõ.

`jsonb` có thể xuất các key theo thứ tự khác đầu vào. Đừng dùng chuỗi JSON tái serialize như bằng chứng chữ ký số nguyên bản trừ khi có chuẩn canonicalization ký được tất cả bên thống nhất.

## 9. Chuỗi, số, ngày giờ và kiểu dữ liệu trong JSON

JSON không có kiểu ngày giờ, DECIMAL với scale định trước hoặc UUID riêng.

```json
{
  "price": 19.95,
  "quantity": 2,
  "sold_at": "2026-11-14T07:30:00Z",
  "external_id": "0000123",
  "active": true
}
```

Những điểm cần phân biệt:

- `price` là **JSON number**; không có thông tin “DECIMAL(12,2)” ngay trong JSON syntax.
- `sold_at` là **JSON string**; ứng dụng phải kiểm tra định dạng ISO 8601, timezone, khả năng parse và ý nghĩa thời điểm.
- `external_id` được lưu dưới dạng **string**, giúp bảo toàn số 0 đầu và tránh chuyển ID định danh thành số.
- `active` là **JSON boolean**, không phải chuỗi `"true"`.
- Với tiền, việc parse number qua kiểu floating-point có thể làm sai độ chính xác; SQL thường dùng `DECIMAL/NUMERIC` trên cột quan hệ hoặc chuyển đổi kiểm soát.

### 9.1. Một trường JSON có thể thay kiểu giữa các bản ghi

Ví dụ:

```json
{"quantity": 3}
```

và:

```json
{"quantity": "3"}
```

đều hợp lệ JSON. Nhưng các query cast sang integer hoặc tổng hợp có thể gặp lỗi/khác ngữ nghĩa. Hãy quyết định xem API có chấp nhận cả hai kiểu hay **chỉ chấp nhận JSON number**.

### 9.2. Bẫy số cực lớn và số thập phân

Một hệ có thể parse số JSON thành số dấu phẩy động, hệ khác thành decimal chính xác hoặc giới hạn độ lớn. Vì vậy đừng dùng số JSON vượt phạm vi kiểu SQL đích mà không kiểm tra; với mã định danh dài, nên truyền **string định danh**.

Nếu dữ liệu tài chính cần 2 chữ số thập phân và phép tính chính xác, cân nhắc lưu `amount NUMERIC(12,2)` ở bảng quan hệ hoặc validate chuỗi biểu diễn tiền theo contract.

## 10. Lọc dữ liệu JSON bằng CHECK và những giới hạn

CHECK constraint là nơi thực thi một số quy tắc đơn giản:

```sql
-- PostgreSQL: ví dụ trên bảng khác, không cần chạy lại demo.
CREATE TABLE webhook_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload jsonb NOT NULL,

    CONSTRAINT chk_root_object
      CHECK ((jsonb_typeof(payload) = 'object') IS TRUE),

    CONSTRAINT chk_kind
      CHECK ((
        jsonb_typeof(payload -> 'kind') = 'string'
        AND payload ->> 'kind' IN ('created', 'updated', 'deleted')
      ) IS TRUE)
);
```

### 10.1. CHECK phù hợp điều kiện không cần tra bảng khác

Ví dụ:

- Root là object.
- Key `kind` phải là string và nằm trong danh sách.
- Key `items` phải là array.
- Một cờ phải là boolean.
- Trường mã có giới hạn chiều dài/format rõ ràng.

Các quy tắc này có thể kiểm tra trên **chính hàng đang ghi**.

### 10.2. CHECK không thay thế FK

Nếu payload có:

```json
{"customer_id": 999999}
```

và `customer_id` phải tồn tại trong bảng `customers`, CHECK trên JSON **không tự tạo quan hệ FK** tới bảng đó. Một giải pháp bền vững là tách thành cột quan hệ:

```sql
customer_id BIGINT REFERENCES customers(customer_id)
```

và có thể lưu phần JSON bổ sung ở cột khác.

Một generated column từ JSON cũng có thể hỗ trợ index/FK trong một số hệ, nhưng cú pháp, tính ổn định biểu thức và việc dùng generated column làm FK **khác nhau theo DBMS**. Không giả định mọi hệ cho FK trực tiếp trên `$.customer_id`.

### 10.3. Kiểm tra tất cả phần tử array khó hơn kiểm tra root

Để đảm bảo **mọi phần tử** trong `items` có `qty > 0` và SKU string, cần một bộ validator biết lặp qua từng phần tử. PostgreSQL có các hàm như `jsonb_array_elements` để truy vấn, nhưng CHECK constraint không được thiết kế đơn giản để chứa một subquery lặp qua bảng hoặc tùy ý gọi set-returning function.

Các lựa chọn:

1. Validate bằng **JSON Schema** và code ứng dụng trước INSERT.
2. Dùng **trigger** hoặc function validation đã được thiết kế, kiểm thử và quản lý quyền cẩn thận.
3. Tách array thành bảng con với `CHECK(qty > 0)` và FK tới SKU.
4. Dùng những tính năng kiểm tra JSON schema riêng của DBMS/extension khi đã xác nhận phiên bản.

Đừng nhét một bộ kiểm tra cấu trúc phức tạp vào SQL không thể bảo trì chỉ để “mọi thứ phải ở database”.

## 11. JSON Schema: kiểm tra cấu trúc chứ không chỉ parse

**JSON Schema** mô tả những tài liệu JSON được phép, ví dụ loại object, các key bắt buộc, kiểu giá trị, khoảng số, mẫu chuỗi và quy tắc array. Đây là lớp hữu ích khi API nhận tài liệu thay đổi theo phiên bản.

Ví dụ JSON Schema giản lược:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_type", "order_id", "items"],
  "properties": {
    "event_type": {
      "type": "string",
      "const": "ORDER_CREATED"
    },
    "order_id": {
      "type": "integer",
      "minimum": 1
    },
    "items": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["sku", "qty"],
        "properties": {
          "sku": {"type": "string", "minLength": 1},
          "qty": {"type": "integer", "minimum": 1},
          "unit_price": {"type": "number", "minimum": 0}
        }
      }
    }
  }
}
```

Một validator đúng phiên bản JSON Schema sẽ kiểm tra nhiều điều kiện mà chỉ một `JSON_VALID` không biết tới.

### 11.1. Những điều JSON Schema vẫn không tự giải quyết

- Tenant của đơn có được người gọi phép sử dụng không.
- SKU có tồn tại trong bảng sản phẩm tại thời điểm ghi không.
- Tồn kho có đủ không và có bị giao dịch khác thay đổi không.
- Một event ID có bị gửi lại không.
- Giá sản phẩm có đúng với hợp đồng tại thời điểm giao dịch không.
- Payload có chứa dữ liệu cá nhân trái chính sách không.

Đó là **quy tắc quan hệ, giao dịch và phân quyền**; cần giải pháp ở DB/service phù hợp.

### 11.2. Khóa schema_version

Một cách thiết kế:

```json
{
  "schema_version": 2,
  "event_type": "ORDER_CREATED",
  "order_id": 1001,
  "items": []
}
```

Khi lưu tài liệu, ghi rõ phiên bản:

- Version 1 yêu cầu `event_type` và `order_id`.
- Version 2 bổ sung `items` với type array.
- Consumer chọn validator/chuyển đổi theo `schema_version`.
- Không viết code giả định mọi dữ liệu lịch sử đều có trường mới.

Có thể để `schema_version` thành cột quan hệ để dễ lọc/migration, đồng thời chứa trong JSON khi cần trao đổi ngoại vi. Nếu lưu cả hai, phải kiểm tra **chúng khớp nhau**.

## 12. PostgreSQL: truy vấn và chỉ mục trên jsonb

Một lợi ích của `jsonb` là nhiều kiểu index. Ví dụ query:

```sql
SELECT event_id
FROM demo_json_events
WHERE payload @> '{"event_type":"ORDER_CREATED"}'::jsonb;
```

`@>` kiểm tra **containment**. Với bảng lớn, GIN index có thể hỗ trợ một số toán tử trên jsonb:

```sql
CREATE INDEX ix_demo_events_payload_gin
ON demo_json_events
USING GIN (payload);
```

### 12.1. GIN trên toàn document không thay mọi index chuyên dụng

Nếu ứng dụng thường tìm theo tenant và event type, một **expression index** có thể phù hợp:

```sql
CREATE INDEX ix_demo_event_type
ON demo_json_events (tenant_id, (payload ->> 'event_type'));
```

Truy vấn:

```sql
SELECT event_id, received_at
FROM demo_json_events
WHERE tenant_id = 10
  AND payload ->> 'event_type' = 'ORDER_CREATED';
```

Index B-tree trên biểu thức có thể phục vụ equality/range/order theo kiểu biểu thức thích hợp. GIN trên toàn JSON thường phục vụ các mẫu containment/path khác. Không nên tạo mọi index theo mọi key chỉ vì chúng có trong document.

### 12.2. jsonb_ops và jsonb_path_ops

PostgreSQL có những operator classes GIN như `jsonb_ops` (mặc định) và `jsonb_path_ops`. Chúng khác về toán tử được hỗ trợ, kích thước và hiệu quả theo mẫu truy vấn.

Ví dụ:

```sql
CREATE INDEX ix_demo_events_path_ops
ON demo_json_events
USING GIN (payload jsonb_path_ops);
```

`jsonb_path_ops` phù hợp một số mẫu containment/path, nhưng **không hỗ trợ mọi toán tử như index GIN mặc định**. Nếu workload cần kiểm tra key-existence `?` thường xuyên, kiểm tra operator class thực tế trước khi dùng. Không giữ hai GIN index lớn trùng mục tiêu trên bảng sản xuất nếu không có lý do đo được.

### 12.3. Dùng EXPLAIN thay vì khẳng định index luôn được chọn

```sql
EXPLAIN
SELECT event_id
FROM demo_json_events
WHERE payload @> '{"event_type":"ORDER_CREATED"}'::jsonb;
```

Bảng tạm chỉ có vài hàng nên PostgreSQL có thể chọn **Seq Scan**; đây không phải bằng chứng index sai. Hãy đánh giá theo tập dữ liệu đủ lớn, statistics và workload đọc/ghi thật.

### 12.4. Index không tự bảo đảm dữ liệu có schema đúng

Index chỉ giúp tìm và có thể thực thi uniqueness nếu là unique index trên key phù hợp; **GIN index trên payload không bắt buộc key `order_id` có mặt hay đúng kiểu**. Những điều đó phải được bảo vệ bằng CHECK, validator hoặc mô hình quan hệ.

## 13. MySQL: kiểu JSON gốc và JSON_VALID

MySQL có **kiểu `JSON`** riêng, được lưu theo định dạng nội bộ tối ưu cho các thao tác JSON. Khi chèn vào cột kiểu này, MySQL **kiểm tra cú pháp** và từ chối văn bản JSON không hợp lệ.

Ví dụ trên MySQL:

```sql
CREATE TABLE demo_mysql_json_events (
    event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    tenant_id INT NOT NULL,
    payload JSON NOT NULL
);

INSERT INTO demo_mysql_json_events (tenant_id, payload)
VALUES (
    10,
    '{"event_type":"ORDER_CREATED","order_id":1001,"items":[]}'
);
```

Dữ liệu sau bị từ chối:

```sql
-- MySQL: THỬ RIÊNG, trailing comma không hợp lệ.
INSERT INTO demo_mysql_json_events (tenant_id, payload)
VALUES (10, '{"event_type":"ORDER_CREATED",}');
```

### 13.1. Hàm JSON_VALID

```sql
SELECT
    JSON_VALID('{"a":1}') AS valid_object,
    JSON_VALID('{"a":1,}') AS invalid_object,
    JSON_VALID('null') AS valid_json_null;
```

Kết quả lần lượt **1, 0, 1** theo kiểm tra cú pháp JSON của MySQL. `JSON_VALID(NULL)` trả SQL NULL; khi dùng trong CHECK phải nhớ logic ba giá trị.

### 13.2. MySQL: JSON_TYPE và điều kiện gốc object

```sql
SELECT JSON_TYPE(CAST('{"id":1}' AS JSON)) AS root_type;
-- OBJECT
```

Khi dùng MySQL 8.0.16+ (CHECK constraints được thực thi theo tính năng hiện hành), có thể viết:

```sql
CREATE TABLE demo_mysql_checked_events (
    event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    payload JSON NOT NULL,
    CONSTRAINT chk_root_object
        CHECK (JSON_TYPE(payload) = 'OBJECT')
);
```

Kiểu `JSON` đã kiểm tra cú pháp. `CHECK` này kiểm tra thêm rằng **root là object**. Nếu muốn key `event_type` có giá trị trong một tập, phải bổ sung điều kiện riêng.

**Lưu ý phiên bản:** các phiên bản MySQL trước 8.0.16 có giai đoạn parser chấp nhận cú pháp CHECK nhưng không thực thi như hiện nay. Đừng nhìn `SHOW CREATE TABLE` và mặc định CHECK đang bảo vệ dữ liệu trên mọi MySQL cũ.

### 13.3. MySQL: JSON_EXTRACT, -> và ->>

```sql
SELECT
    JSON_EXTRACT(payload, '$.order_id') AS order_id_json,
    JSON_UNQUOTE(JSON_EXTRACT(payload, '$.event_type')) AS event_type
FROM demo_mysql_json_events;
```

Với cột JSON, một số cách viết ngắn gọn:

```sql
SELECT
    payload -> '$.order_id' AS order_id_json,
    payload ->> '$.event_type' AS event_type_text
FROM demo_mysql_json_events;
```

Đừng đồng nhất kiểu trả của `JSON_EXTRACT` và `JSON_UNQUOTE`: một bên là JSON value, một bên là SQL string. Khi cần integer, cần chuyển kiểu có kiểm soát.

### 13.4. MySQL JSON_SCHEMA_VALID theo phiên bản

MySQL 8.0.17+ có chức năng `JSON_SCHEMA_VALID` để kiểm tra tài liệu theo JSON Schema trong **phạm vi draft/tính năng MySQL hỗ trợ**.

Ví dụ ý tưởng:

```sql
-- MySQL 8.0.17+, minh họa schema đơn giản.
SELECT JSON_SCHEMA_VALID(
    '{"type":"object","required":["id"],"properties":{"id":{"type":"integer"}}}',
    '{"id":123}'
) AS conforms_to_schema;
```

Kết quả **1** khi tài liệu khớp schema trong phạm vi hỗ trợ. Không được suy rằng MySQL hỗ trợ toàn bộ mọi từ khóa của JSON Schema 2020-12 giống một thư viện validator hiện đại; kiểm tra draft và những hạn chế được tài liệu MySQL công bố.

### 13.5. MySQL JSON vẫn có vấn đề duplicate keys

MySQL có thể chuẩn hóa cách lưu object, kể cả key trùng. Đừng dùng hành vi chọn giá trị từ duplicate keys để thực thi quyền truy cập. Nếu ứng dụng nhận payload từ nhiều service, nên dùng **một chính sách parser thống nhất và từ chối key lặp** khi thuộc tính là nhạy cảm.

## 14. MariaDB: JSON thường là alias cho LONGTEXT

Đây là khác biệt quan trọng: **MariaDB không dùng cùng cơ chế kiểu JSON nhị phân như MySQL**. Trong MariaDB, `JSON` được tài liệu mô tả là alias cho **`LONGTEXT COLLATE utf8mb4_bin`** vì mục tiêu tương thích.

Ví dụ:

```sql
-- MariaDB
CREATE TABLE demo_mariadb_events (
    event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    payload JSON NOT NULL
);
```

Trong nhiều phiên bản MariaDB hiện đại, định nghĩa cột dạng `JSON` đi kèm ràng buộc kiểm tra `JSON_VALID(payload)`; tuy nhiên lịch sử các phiên bản và cách tạo/khôi phục schema có khác biệt. Khi cần bảo đảm ở môi trường thực tế, hãy kiểm tra:

```sql
SHOW CREATE TABLE demo_mariadb_events;
```

Nếu dùng `LONGTEXT` rõ ràng, có thể thêm CHECK:

```sql
CREATE TABLE demo_mariadb_events_text (
    event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    payload LONGTEXT CHARACTER SET utf8mb4
        COLLATE utf8mb4_bin NOT NULL,
    CONSTRAINT chk_payload_valid
        CHECK (JSON_VALID(payload) = 1)
);
```

### 14.1. Tại sao không coi MySQL JSON và MariaDB JSON là cùng kiểu?

| Khía cạnh | MySQL | MariaDB |
|---|---|---|
| `JSON` data type | Kiểu JSON với biểu diễn nội bộ của MySQL | Alias văn bản `LONGTEXT` theo MariaDB |
| Kiểm tra dữ liệu | Kiểu JSON từ chối cú pháp sai | Thường qua `JSON_VALID`/CHECK; kiểm tra schema thật |
| Bảo toàn format đầu vào | Không coi là bản sao byte gốc | Dữ liệu văn bản được giữ theo cơ chế của MariaDB |
| Duplicate keys | Cách chuẩn hóa/đọc riêng | Cách lưu và JSON functions riêng |
| Indexing | Generated columns/functional index theo phiên bản | Indexed generated columns theo phiên bản |

Không dump một kiểu JSON rồi giả định round-trip giữa MySQL và MariaDB luôn giữ nguyên biểu diễn, thứ tự object key, duplicate keys hoặc hiệu năng.

### 14.2. JSON_VALID trả gì?

```sql
SELECT
    JSON_VALID('{"x":1}') AS good,
    JSON_VALID('{"x":}') AS bad;
```

MariaDB trả **1** hoặc **0** cho các ví dụ này. Với SQL NULL, kết quả thường là SQL NULL; nếu cột được phép NULL và chỉ có CHECK `JSON_VALID(payload) = 1`, cần nắm quy tắc CHECK với UNKNOWN và sử dụng `NOT NULL` khi muốn cấm NULL.

## 15. SQL Server: ISJSON, NVARCHAR và native JSON theo phiên bản

SQL Server có hàm xử lý JSON từ **SQL Server 2016 (13.x)**. Trong SQL Server 2016–2022, mô hình phổ biến là lưu JSON trong `NVARCHAR(MAX)` rồi dùng **`ISJSON`** để kiểm tra cú pháp.

```sql
-- SQL Server 2016+.
CREATE TABLE dbo.demo_sqlserver_events (
    event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id INT NOT NULL,
    payload NVARCHAR(MAX) NOT NULL,
    CONSTRAINT chk_payload_json CHECK (ISJSON(payload) = 1)
);
```

### 15.1. ISJSON không có type constraint mặc định kiểm tra object/array

```sql
SELECT
    ISJSON(N'{"id":1}') AS object_ok,
    ISJSON(N'[1,2]') AS array_ok,
    ISJSON(N'123') AS scalar_result;
```

Với dạng không có tham số type constraint, SQL Server kiểm tra JSON **object hoặc array ở cấp gốc**, nên `ISJSON(N'123')` trả **0**, dù `123` là top-level JSON value hợp lệ theo RFC 8259.

SQL Server 2022 (16.x)+ hỗ trợ tham số thứ hai:

```sql
-- SQL Server 2022+
SELECT
    ISJSON(N'123', VALUE) AS number_value_ok,
    ISJSON(N'{"id":1}', OBJECT) AS object_ok,
    ISJSON(N'[1,2]', ARRAY) AS array_ok,
    ISJSON(N'"hello"', SCALAR) AS string_scalar_ok;
```

- `VALUE`: chấp nhận mọi top-level JSON value hợp lệ.
- `OBJECT`: chỉ object.
- `ARRAY`: chỉ array.
- `SCALAR`: top-level string hoặc number theo định nghĩa hàm SQL Server.
- Không phải mọi dịch vụ SQL của Microsoft đều hỗ trợ giống nhau; Azure Synapse dedicated pools có hạn chế đối với tham số thứ hai.

### 15.2. ISJSON không kiểm tra key trùng

```sql
SELECT ISJSON(N'{"id":1,"id":2}') AS is_syntactically_valid;
```

SQL Server `ISJSON` không bảo đảm key trong cùng object là duy nhất. Muốn từ chối duplicate, cần parser hoặc chính sách xác thực khác.

### 15.3. Đọc giá trị bằng JSON_VALUE và JSON_QUERY

```sql
SELECT
    JSON_VALUE(payload, '$.event_type') AS event_type,
    JSON_VALUE(payload, '$.order_id') AS order_id_text,
    JSON_QUERY(payload, '$.items') AS items_json
FROM dbo.demo_sqlserver_events;
```

- `JSON_VALUE` dành cho scalar, thường trả **text SQL**.
- `JSON_QUERY` dành cho object/array.
- Với path thiếu hoặc kiểu không phù hợp trong chế độ mặc định, các hàm có thể trả SQL NULL; `strict/lax` và `ON ERROR` theo từng hàm/phiên bản cần đọc tài liệu.
- Với `order_id`, `TRY_CONVERT(bigint, JSON_VALUE(...))` giúp kiểm tra khả năng chuyển thành số, **nhưng chưa chứng minh đầu vào JSON là number thay vì string chứa chữ số**.

### 15.4. SQL Server 2025 (17.x): native json type

Theo tài liệu Microsoft về **SQL Server 2025 (17.x)**, SQL Server có **kiểu `json` gốc**, lưu biểu diễn nhị phân và hỗ trợ các tính năng JSON mới theo phạm vi sản phẩm/phiên bản.

```sql
-- SQL Server 2025 (17.x) và môi trường hỗ trợ kiểu json.
CREATE TABLE dbo.demo_json_native (
    event_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    payload JSON NOT NULL
);
```

**Khác biệt đáng chú ý:** Kiểu `json` gốc của SQL Server 2025 hiện yêu cầu giá trị JSON ở cấp gốc là **object hoặc array**; không nhận trực tiếp top-level scalar `123`/`"abc"`/`true`/JSON `null` làm document của kiểu này, dù `ISJSON(text, VALUE)` có thể công nhận chúng là giá trị JSON chuẩn. SQL `NULL` vẫn có thể được lưu nếu cột cho phép NULL.

Không áp dụng ví dụ `payload JSON` trên SQL Server 2019/2022, vì các phiên bản đó không có native json type tương ứng.

### 15.5. CHECK trên đường dẫn JSON không bằng JSON Schema toàn phần

Có thể kết hợp:

```sql
-- SQL Server 2016+, trên cột NVARCHAR:
CONSTRAINT chk_payload_json CHECK (ISJSON(payload) = 1)
```

với các CHECK khác theo path/kiểu trả về khi phiên bản hỗ trợ. Nhưng `ISJSON` không tự kiểm tra `items` là array các object có `qty > 0`.

Khi sử dụng native JSON hay `NVARCHAR`, cần xem hướng dẫn index JSON/computed columns theo SQL Server đang chạy. Việc có hàm JSON không tự có index tối ưu trên mọi path.

## 16. Oracle Database: IS JSON và kiểu JSON gốc

Oracle Database hỗ trợ SQL/JSON trên những cột văn bản như `VARCHAR2`/`CLOB`/`BLOB` và có thể dùng điều kiện **`IS JSON`** để ràng buộc tính hợp lệ.

Ví dụ theo Oracle 19c và kiểu dữ liệu lưu JSON dạng text:

```sql
CREATE TABLE demo_oracle_events (
    event_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT chk_oracle_payload_json CHECK (payload IS JSON)
);
```

Oracle từ chối tài liệu không hợp lệ theo điều kiện `IS JSON`, nhưng **không tự đòi key cụ thể như `order_id`**.

### 16.1. IS JSON có các tùy chọn theo phiên bản

Oracle có những từ khóa liên quan tới kiểm tra JSON như **STRICT/LAX**, **WITH UNIQUE KEYS**, và những lựa chọn về scalar ở root trong các phiên bản tương ứng.

Ví dụ ý tưởng:

```sql
-- Oracle: cú pháp cần đối chiếu phiên bản Oracle cụ thể.
CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
```

Mục tiêu là **chỉ nhận JSON đúng cú pháp nghiêm ngặt và không có key trùng**. Hãy xác minh đầy đủ cú pháp và kiểu dữ liệu với phiên bản Oracle đang dùng; không tự chuyển ví dụ này sang PostgreSQL hoặc SQL Server.

### 16.2. Oracle 21c+: kiểu dữ liệu JSON gốc

Từ Oracle Database **21c**, Oracle có native SQL data type `JSON` với điều kiện cấu hình tương thích phù hợp, được hỗ trợ trong các bản mới hơn:

```sql
-- Oracle 21c+ trong môi trường có native JSON type.
CREATE TABLE demo_oracle_json_native (
    event_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSON NOT NULL
);
```

Kiểu JSON gốc bảo đảm tính well-formed của tài liệu theo cách engine lưu trữ; không cần dùng CLOB chỉ để gọi tên dữ liệu JSON. Nhưng việc chọn kiểu gốc, hỗ trợ scalar ở root, JSON Schema validation nâng cao và chức năng SQL/JSON phụ thuộc **phiên bản và tham số COMPATIBLE**.

### 16.3. JSON_VALUE và JSON_EXISTS

Oracle có SQL/JSON functions để truy cập các trường:

```sql
-- Oracle, giả sử payload là CLOB/JSON hợp lệ.
SELECT
    JSON_VALUE(payload, '$.event_type') AS event_type,
    JSON_VALUE(payload, '$.order_id' RETURNING NUMBER) AS order_id
FROM demo_oracle_events;
```

Nếu muốn xác định một path có tồn tại, có thể dùng `JSON_EXISTS` theo cú pháp/semantics Oracle. Khi kiểu không đúng hoặc thiếu key, cần hiểu cách hàm xử lý lỗi (ví dụ các tùy chọn `ON ERROR`/`ON EMPTY`); mặc định có thể làm một lỗi bị chuyển thành NULL, không phải validation nghiêm ngặt.

Oracle thế hệ mới còn có các cơ chế kiểm tra theo JSON Schema; **không coi mọi tính năng Oracle 26 là có sẵn trên 19c**.

## 17. SQLite: TEXT, JSON functions, JSONB và json_valid

SQLite không có một kiểu cột JSON server-side riêng tương đương PostgreSQL `jsonb`. Theo mô hình type affinity của SQLite, JSON thường được lưu bằng **TEXT**; các bản mới có thể lưu **JSONB dạng BLOB** ở định dạng nội bộ của SQLite.

SQLite có JSON functions (thường gọi chung là JSON1), trong đó có:

- `json_valid(X)` kiểm tra JSON text chuẩn.
- `json_extract(X, path)` lấy giá trị ở đường dẫn.
- `json_type(X[, path])` kiểm tra kiểu tại root/path.
- `json_each`/`json_tree` để duyệt dữ liệu.
- `json(X)` tạo biểu diễn JSON chuẩn từ input phù hợp.
- `jsonb(X)` (SQLite 3.45.0+) tạo JSONB nội bộ của SQLite.

### 17.1. Ràng buộc cú pháp khi lưu vào TEXT

```sql
-- SQLite, thực hành trong database thử.
CREATE TABLE demo_sqlite_events (
    event_id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL,
    CONSTRAINT chk_json_valid CHECK (json_valid(payload) = 1)
);
```

Nếu chèn:

```sql
INSERT INTO demo_sqlite_events (event_id, payload)
VALUES (
    1,
    '{"event_type":"ORDER_CREATED","order_id":1001,"items":[]}'
);
```

thì hợp lệ. Câu sau bị CHECK từ chối:

```sql
-- THỬ RIÊNG:
INSERT INTO demo_sqlite_events (event_id, payload)
VALUES (2, '{"event_type":}');
```

Vì `json_valid` là hàm rõ ràng trong CHECK, SQLite kiểm tra mỗi lần dữ liệu được chèn/sửa theo ràng buộc.

### 17.2. Kiểm tra root object và key mà không mắc bẫy UNKNOWN

Trong SQLite, `CHECK` cũng có thể chấp nhận kết quả SQL NULL. Nếu path không tồn tại, `json_type(payload, '$.event_type')` có thể trả SQL NULL. Vì vậy phải biến điều kiện thiếu key thành FALSE rõ ràng.

Một cách xây ràng buộc với `CASE`:

```sql
CREATE TABLE demo_sqlite_checked (
    event_id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL,

    CONSTRAINT chk_json_object
    CHECK (
        CASE
            WHEN json_valid(payload) = 1
            THEN COALESCE(json_type(payload) = 'object', 0)
            ELSE 0
        END
    ),

    CONSTRAINT chk_event_type
    CHECK (
        CASE
            WHEN json_valid(payload) = 1
            THEN COALESCE(
                json_type(payload, '$.event_type') = 'text',
                0
            )
            ELSE 0
        END
    )
);
```

`CASE` giúp chỉ gọi `json_type` khi `json_valid` cho biết payload hợp lệ. Điều này cũng hữu ích vì nhiều JSON functions có thể báo lỗi khi nhận văn bản hỏng.

### 17.3. SQLite JSON5 và cờ của json_valid

SQLite **3.42.0+** có khả năng parse **JSON5** (một tập mở rộng của JSON chuẩn). Nhưng `json_valid(X)` **không có tham số thứ hai** vẫn kiểm tra JSON text chuẩn, không coi mọi tài liệu JSON5 là canonical JSON.

SQLite **3.45.0+** hỗ trợ tham số **flags** cho `json_valid(X, Y)`. Một số giá trị:

| Lời gọi | Ý nghĩa |
|---|---|
| `json_valid(X)` hoặc `json_valid(X, 1)` | Kiểm tra JSON text chuẩn |
| `json_valid(X, 2)` | Chấp nhận JSON5 text theo hỗ trợ SQLite |
| `json_valid(X, 4)` | Kiểm tra sơ bộ BLOB có vẻ là SQLite JSONB |
| `json_valid(X, 8)` | Kiểm tra chặt hơn cấu trúc nội bộ SQLite JSONB |
| `json_valid(X, 6)` | Chấp nhận JSON5 text hoặc BLOB có vẻ là JSONB |

Ví dụ:

```sql
-- SQLite 3.45.0+
SELECT
    json_valid('{"a":1}') AS canonical_ok,
    json_valid('{a:1}', 2) AS json5_ok,
    json_valid('{a:1}') AS canonical_rejects_json5;
```

Kết quả logic: **1, 1, 0** trong môi trường hỗ trợ. Nếu ứng dụng cần JSON **chuẩn để trao đổi với các hệ khác**, vẫn dùng kiểm tra canonical, không tùy ý bật cờ JSON5 rồi đưa raw input sang DBMS nghiêm ngặt.

### 17.4. SQLite JSONB không giống PostgreSQL jsonb

SQLite từ **3.45.0** hỗ trợ biểu diễn **JSONB dạng BLOB** riêng của nó. Đây là định dạng nội bộ được thiết kế cho SQLite, **không tương thích nhị phân** với `jsonb` của PostgreSQL.

```sql
-- SQLite 3.45.0+.
SELECT jsonb('{"a":1,"b":[2,3]}');
```

Không copy BLOB SQLite JSONB vào PostgreSQL và mong PostgreSQL hiểu; cũng không gửi bytes từ `jsonb` PostgreSQL sang SQLite làm JSONB. Khi trao đổi giữa DBMS, dùng JSON text chuẩn hoặc một protocol đã được quy định.

### 17.5. JSON1 và các hàm với dữ liệu malformed

Không phải mọi JSON function SQLite đều có chính sách “trả NULL nếu lỗi”. Nhiều hàm sẽ báo lỗi nếu input không phải JSON hợp lệ. Do đó, với cột TEXT nhận dữ liệu từ bên ngoài:

- Có `CHECK(json_valid(payload) = 1)` hoặc validation trước khi lưu.
- Không cho phép SQL NULL nếu nghiệp vụ yêu cầu document, dùng `NOT NULL`.
- Nếu nhận JSONB, kiểm tra nguồn tạo BLOB và flags phù hợp.
- Không xử lý malformed binary JSONB như một phương thức lưu trữ dữ liệu không kiểm soát.

## 18. So sánh hỗ trợ lưu trữ và kiểm tra JSON theo DBMS

| DBMS | Kiểu lưu trữ thường dùng | Kiểm tra cú pháp | Lưu ý phiên bản/chính sách |
|---|---|---|---|
| **PostgreSQL** | `json`, `jsonb` | Cast/INSERT vào kiểu JSON tự parse; CHECK bổ sung | `jsonb` khác `json` ở whitespace, duplicate keys và indexing |
| **MySQL** | Native `JSON` | Kiểu JSON tự từ chối cú pháp sai; `JSON_VALID` | `CHECK` được thực thi ở MySQL 8.0.16+; JSON_SCHEMA_VALID 8.0.17+ |
| **MariaDB** | `JSON` alias `LONGTEXT`, hoặc LONGTEXT | `JSON_VALID`, CHECK trong schema phù hợp | Kiểm tra `SHOW CREATE TABLE` do khác biệt phiên bản |
| **SQL Server 2016–2022** | `NVARCHAR(MAX)` | `ISJSON` kết hợp CHECK | Không có native json type kiểu SQL Server 2025 |
| **SQL Server 2025** | `json` gốc hoặc NVARCHAR | Native json type / `ISJSON` | Native `json` yêu cầu object/array ở root theo tài liệu hiện hành |
| **Oracle 19c** | `VARCHAR2`/`CLOB`/`BLOB` | `IS JSON` CHECK | STRICT/UNIQUE KEYS theo tính năng phiên bản |
| **Oracle 21c+** | Có thêm native `JSON` | Kiểu JSON và/hoặc IS JSON | Phụ thuộc COMPATIBLE và phiên bản |
| **SQLite** | `TEXT`, SQLite JSONB BLOB từ 3.45+ | `json_valid` + CHECK | JSON5 từ 3.42+, flags json_valid từ 3.45+ |

**Không thể thay SQL của một DBMS bằng SQL của DBMS khác chỉ vì cùng dùng chữ JSON.** Loại root được chấp nhận, NULL, chuẩn hóa duplicate keys, kiểu trả của JSON functions và khả năng indexing đều khác.

## 19. Missing key, JSON null và những khác biệt khi truy vấn

Giả sử có:

```json
{
  "coupon": null,
  "note": "null",
  "items": []
}
```

Các hệ có cách trả giá trị JSON path khác nhau, nhất là khi chuyển giá trị thành SQL scalar.

| Phần dữ liệu | Điều cần phân biệt |
|---|---|
| `coupon` | Key tồn tại, có **JSON null** |
| `note` | Key tồn tại, string `"null"` |
| `missing` | Key **không tồn tại** |
| `items` | Key tồn tại, array rỗng |
| Toàn cột payload SQL NULL | Không có document SQL |
| Root document `null` | Một giá trị JSON null, nếu DBMS/kiểu cột chấp nhận |

Ví dụ PostgreSQL:

```sql
SELECT
    '{"coupon":null}'::jsonb ? 'coupon' AS exists_coupon,
    '{}'::jsonb ? 'coupon' AS exists_missing,
    jsonb_typeof('{"coupon":null}'::jsonb -> 'coupon') AS coupon_type,
    jsonb_typeof('{}'::jsonb -> 'coupon') AS missing_type;
```

Kết quả logic: **TRUE**, **FALSE**, `'null'`, **SQL NULL**.

Với SQL Server `JSON_VALUE`, MySQL `JSON_EXTRACT/JSON_UNQUOTE`, Oracle `JSON_VALUE` hay SQLite `json_extract`, cách diễn giải JSON null/missing và kiểu trả có thể khác. Khi yêu cầu phân biệt **key không có** với **key có nhưng null**, dùng cơ chế kiểm tra tồn tại/type được tài liệu của đúng DBMS mô tả, không chỉ so sánh kết quả scalar với SQL NULL.

## 20. JSON không thay thế các ràng buộc quan hệ

Một hàng JSON chứa:

```json
{"tenant_id":10,"customer_id":9999,"status":"PAID"}
```

có thể hợp lệ về cú pháp và cấu trúc dù `customer_id=9999` **không tồn tại** trong hệ.

Nếu `customer_id` có vai trò FK thực sự, nên cân nhắc lưu thành cột:

```sql
-- PostgreSQL: ví dụ mô hình, cần bảng customers tương ứng.
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

Ưu điểm:

- Khóa chính và FK được DBMS bảo vệ trực tiếp.
- Join/đếm/tổng hợp qua những cột thường có kế hoạch rõ.
- Tenant là cột có thể dùng cho policy/partition/index.
- Những thuộc tính ít ổn định vẫn nằm trong `attributes`.

### 20.1. Dữ liệu bị lặp giữa cột và JSON

Nếu vừa có `tenant_id` ở cột vừa có `tenant_id` trong JSON:

```json
{"tenant_id":20, "metadata":{"source":"web"}}
```

nhưng cột SQL lại là `tenant_id = 10`, phải trả lời: **nguồn nào là sự thật?**

Một số thiết kế:

1. **Bỏ tenant trong JSON** khi tenant đã được xác định bởi cột quan hệ.
2. Đặt **CHECK/trigger/validator** để hai giá trị phải khớp.
3. Xem tenant trong payload là “tenant do đối tác khai báo”, tách rõ với tenant được service xác thực.
4. Không dùng giá trị JSON do client gửi làm căn cứ cấp quyền nếu nó có thể bị sửa.

Không để hai nguồn dữ liệu mâu thuẫn rồi chọn tùy ý tại từng API.

## 21. Sử dụng JSON builder thay vì tự nối chuỗi

Một cách nguy hiểm:

```text
json = '{"name":"' + userName + '","note":"' + note + '"}'
```

Nếu `note` chứa dấu nháy kép, backslash hoặc ký tự control, chuỗi tạo ra có thể **không hợp lệ**. Hơn nữa, nếu dùng string concat trong câu SQL, còn có nguy cơ SQL injection.

### 21.1. PostgreSQL jsonb_build_object

```sql
SELECT jsonb_build_object(
    'event_type', 'ORDER_CREATED',
    'order_id', 1001,
    'items', jsonb_build_array(
        jsonb_build_object('sku', 'MOUSE-01', 'qty', 2)
    ),
    'metadata', jsonb_build_object('channel', 'web')
) AS payload;
```

DBMS tự biểu diễn JSON string, number, array, object và escape theo kiểu dữ liệu tương ứng.

### 21.2. MySQL JSON_OBJECT, JSON_ARRAY

```sql
-- MySQL
SELECT JSON_OBJECT(
    'event_type', 'ORDER_CREATED',
    'order_id', 1001,
    'items', JSON_ARRAY(
        JSON_OBJECT('sku','MOUSE-01','qty',2)
    )
) AS payload;
```

Các DBMS khác có hàm xây JSON như `JSON_OBJECT`/`JSON_ARRAY` hoặc `FOR JSON` theo phương ngữ và phiên bản. Hãy dùng hàm tạo JSON hoặc thư viện serializer đáng tin để tránh lỗi escaping.

### 21.3. Phân biệt JSON encoding và SQL parameterization

- **JSON encoding** bảo đảm giá trị được biểu diễn đúng trong tài liệu JSON.
- **SQL parameterization** bảo đảm giá trị JSON/SQL được gửi tới DB như **tham số**, không bị diễn giải thành cú pháp SQL.
- **Authorization** bảo đảm caller được phép thực hiện thao tác với các bản ghi đích.

Cả ba đều cần ở những luồng nhập JSON từ người dùng; thay thế một lớp bằng lớp khác là sai.

## 22. Java/JDBC: gửi JSON có kiểm tra và tham số

Trong ứng dụng Java, một cách tiếp cận hợp lý là:

1. Parser JSON ở API với cấu hình nghiêm ngặt.
2. Validate cấu trúc theo schema version và rule nghiệp vụ.
3. Truyền dữ liệu đến DB bằng tham số, không nối string SQL.
4. Để DB kiểm tra thêm kiểu JSON, constraint, FK và quyền.
5. Xử lý lỗi SQL trong transaction đúng cách.

Ví dụ JDBC cho PostgreSQL, giả định chuỗi `jsonPayload` đã qua validation ứng dụng:

```java
String sql = """
    INSERT INTO events (tenant_id, event_type, payload)
    VALUES (?, ?, CAST(? AS jsonb))
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, authorizedTenantId);
    ps.setString(2, eventType);
    ps.setString(3, jsonPayload);
    ps.executeUpdate();
}
```

`CAST(? AS jsonb)` yêu cầu PostgreSQL parse JSON; nếu chuỗi hỏng, statement sẽ lỗi. `authorizedTenantId` phải lấy từ ngữ cảnh được **xác thực/ủy quyền phía server**, không chỉ tin một trường `tenant_id` trong JSON client gửi.

### 22.1. Trả lỗi từ API như thế nào?

- JSON syntax lỗi → thường trả phản hồi client error phù hợp (ví dụ HTTP 400).
- Thiếu key/kiểu sai → lỗi validation (ví dụ 422 tùy chuẩn API).
- Vi phạm FK/UNIQUE trong DB → thông báo nghiệp vụ phù hợp, không phơi internal schema/SQL.
- DB timeout/deadlock/serialization error → xử lý retry có giới hạn, không xem là lỗi syntax.
- Payload quá lớn → chặn ở gateway/parser **trước khi** gây áp lực bộ nhớ/DB.

Các mã HTTP là **gợi ý thiết kế API**, không phải ngữ nghĩa tự động của SQL engine.

### 22.2. Không parse rồi serialize mà quên duplicate-key policy

Nếu parser ứng dụng nhận:

```json
{"role":"viewer","role":"admin"}
```

và âm thầm chọn một key, việc reserialize sẽ làm biến mất thông tin rằng đầu vào có key trùng. Với dữ liệu nhạy cảm, bật tùy chọn **strict duplicate detection** hoặc kiểm tra raw payload trước khi chuẩn hóa. Quy tắc này phải được áp dụng tại cổng nhập để các service phía sau nhìn thấy một contract thống nhất.

## 23. Giới hạn kích thước, độ sâu và JSON bomb

Dữ liệu đúng cú pháp vẫn có thể không an toàn về tài nguyên.

Ví dụ một array có hàng triệu phần tử:

```json
{"items":[1,1,1,1,1,1,1,1,1,1]}
```

Đoạn ngắn trên chỉ minh họa cấu trúc; một payload thực tế có thể rất lớn hoặc lồng object/array sâu gây tốn CPU và bộ nhớ khi parse/index/JSON_TABLE.

Những giới hạn nên xác định:

- **Kích thước byte** tối đa của request và document.
- **Độ sâu lồng nhau** tối đa.
- **Số phần tử array** và số key object tối đa.
- Độ dài string và số chữ số của number.
- Thời gian/CPU/memory tối đa để parse và validate.
- Số bản ghi được sinh ra từ một JSON array khi import.
- Tần suất ghi và số bản sao/khóa được lưu trong index.
- Giới hạn packet/LOB/protocol và quota theo DBMS.

### 23.1. Chặn trước khi DB phải parse

Một cột `JSON` có thể từ chối cú pháp sai, nhưng gửi một payload 500 MB đến DB chỉ để nhận lỗi là thiết kế tốn kém. Gateway có thể chặn body size, service có parser streaming/giới hạn nesting, còn DB giữ constraint như **lớp bảo vệ cuối**.

### 23.2. Không dùng JSON làm nơi giấu bí mật

Nếu payload webhook chứa access token, session cookie, số thẻ hoặc dữ liệu cá nhân, việc lưu nguyên JSON có thể làm **lộ qua log, backup, quyền đọc bảng hoặc bản sao analytics**.

Nên có chính sách:

- Chỉ lưu trường thực sự cần.
- Redact/tokenize thông tin nhạy cảm.
- Giới hạn role đọc JSON và audit.
- Mã hóa at rest/in transit theo môi trường.
- Quy định retention và quyền xóa.
- Tránh trả nguyên payload khi client chỉ cần vài field.

Tính hợp lệ JSON **không đồng nghĩa** nội dung an toàn để lưu trữ.

## 24. JSON path, key người dùng và nguy cơ injection

Dữ liệu JSON có thể được truy vấn bằng đường dẫn như `$.items[0].sku`. Nếu ứng dụng cho client chọn đường dẫn tùy ý rồi nối vào SQL, có thể phát sinh:

1. **SQL injection** nếu đường dẫn được ghép thành literal SQL không an toàn.
2. **Path injection / data exposure** dù đã quote đúng, vì caller có thể yêu cầu đọc field nhạy cảm ngoài phạm vi.
3. **DoS** nếu path/phép truy vấn tạo kết quả lớn hoặc xử lý phức tạp.

Ví dụ không an toàn:

```text
SELECT JSON_VALUE(payload, '$.' + userInput) ...
```

Một giải pháp an toàn hơn là **allowlist field nghiệp vụ**:

```text
field "orderId"   -> path "$.order_id"
field "channel"   -> path "$.metadata.channel"
field "eventType" -> path "$.event_type"
```

Rồi gửi giá trị qua bind parameters theo khả năng DBMS và kiểm tra role có quyền xem field đó hay không. **Quote/bind đúng không phải authorization**; một path hợp lệ vẫn có thể trỏ đến secret.

## 25. Cập nhật một phần JSON và vấn đề mất cập nhật

Một ứng dụng có thể sửa chỉ field `metadata.channel`, nhưng vẫn phải hiểu DBMS xử lý ghi đồng thời ra sao.

PostgreSQL có:

```sql
-- PostgreSQL: chỉ minh họa trên bảng demo.
UPDATE demo_json_events
SET payload = jsonb_set(
    payload,
    '{metadata,channel}',
    '"mobile"'::jsonb,
    true
)
WHERE event_id = 1;
```

`jsonb_set` tạo một giá trị jsonb đã cập nhật và gán lại cột. Về mặt logic, đây là cập nhật document; engine vẫn quản lý version hàng, khóa và WAL theo cơ chế của nó.

MySQL có `JSON_SET`, SQL Server có `JSON_MODIFY`/cơ chế sửa JSON native theo phiên bản, Oracle có `JSON_TRANSFORM`, SQLite có `json_set`. **Tên gần giống không bảo đảm semantics giống nhau về path không tồn tại, JSON null và kiểu dữ liệu trả về.**

### 25.1. Cạnh tranh ghi

Hai request cùng đọc document cũ:

```text
Request A đọc payload version 1
Request B đọc payload version 1
A sửa channel = "web"
B sửa status = "PAID" trên bản sao version 1
A ghi cả payload version 2
B ghi cả payload version 2 của B
```

Nếu B thay cả document dựa trên bản sao cũ, thay đổi của A có thể bị ghi đè. Cần:

- Cập nhật một path trên hàng dưới transaction/lock phù hợp.
- Hoặc **optimistic locking** với `version_no`:
  `UPDATE ... WHERE id = ? AND version_no = ?`.
- Kiểm tra affected rows, retry khi version mismatch.
- Định nghĩa quy tắc merge rõ, không tự ghép hai bản JSON không tương thích.

Chỉ lưu JSON không giải quyết mất cập nhật.

## 26. Tài liệu JSON biến đổi theo thời gian: migration và versioning

Lưu JSON rất tiện lúc đầu, nhưng hệ thống lâu dài sẽ có nhiều phiên bản payload:

```json
{"schema_version":1,"order_id":1001}
```

```json
{
  "schema_version": 2,
  "order_id": 1001,
  "items": [],
  "currency": "VND"
}
```

Để tránh code đọc dữ liệu cũ bị lỗi:

1. **Công bố contract theo version**.
2. Chọn validator đúng version khi nhận hoặc đọc.
3. Thêm trường mới với giá trị mặc định/ngữ nghĩa tương thích nếu có thể.
4. Không thay đổi kiểu `order_id` từ number sang object mà không có migration/adapter.
5. Backfill theo lô với transaction, logging và đo hiệu năng.
6. Nếu đổi định dạng lưu `json` sang `jsonb`/native JSON, đánh giá tác động với duplicate keys, whitespace, Unicode và số lớn.
7. Giữ raw payload khi có nghĩa vụ audit/chữ ký.
8. Xác định chiến lược xóa trường cũ và thời gian hỗ trợ consumer.

### 26.1. Backfill JSON nên có điều kiện rõ

Ví dụ PostgreSQL:

```sql
UPDATE demo_json_events
SET payload = jsonb_set(
    payload,
    '{schema_version}',
    '2'::jsonb,
    true
)
WHERE NOT (payload ? 'schema_version');
```

Ví dụ này thêm version 2 vào những document chưa có version, **không chứng minh** document cũ thật sự đã đạt schema version 2. Nếu version 2 yêu cầu các trường mới, cần chuyển đổi/validate trước khi gắn version.

### 26.2. Thay đổi CHECK trên bảng có dữ liệu cũ

Nếu thêm một CHECK yêu cầu key mới:

```sql
-- PostgreSQL: ví dụ ý tưởng.
ALTER TABLE events
ADD CONSTRAINT chk_schema_version
CHECK ((jsonb_typeof(payload -> 'schema_version') = 'number') IS TRUE);
```

câu `ALTER TABLE` có thể thất bại nếu hàng cũ thiếu trường. Cần thống kê, dọn/backfill dữ liệu và có migration được kiểm soát. Với PostgreSQL còn có cơ chế `NOT VALID` và `VALIDATE CONSTRAINT` cho nhiều loại CHECK phù hợp, giúp quản lý rollout trên bảng lớn; nhưng không được xem `NOT VALID` là bảo đảm các hàng lịch sử đã hợp lệ.

### 26.3. Không dựa vào thời điểm ghi làm schema version

Một hàng ghi năm 2025 không mặc nhiên có schema 1, hàng ghi 2026 không mặc nhiên có schema 2. Hàng có thể được import/replay. Hãy lưu **version tường minh**.

## 27. Hiệu năng và lựa chọn index với JSON

| Mẫu truy vấn | Cách tối ưu thường cân nhắc |
|---|---|
| Lọc theo `tenant_id` | B-tree trên cột tenant |
| Tìm `event_id` chính xác | PRIMARY KEY |
| PostgreSQL containment trên nhiều key JSON | GIN jsonb theo operator phù hợp |
| Lọc theo một path hay dùng | Expression/generated/computed column index |
| Tổng hợp theo ngày/tháng | Cột ngày SQL, index/partition thích hợp |
| Lấy top-N events mới nhất | Index trên tenant và received_at |
| Tra SKU trong array JSON rất lớn | Cân nhắc tách bảng con hoặc cấu trúc tìm kiếm chuyên dụng |

### 27.1. JSON index không miễn phí

Mỗi INSERT/UPDATE phải bảo trì index, và index trên toàn bộ tài liệu lớn có thể tiêu tốn dung lượng. Nếu chỉ cần lọc theo `event_type`, index expression có thể đơn giản hơn một GIN trên mọi key.

### 27.2. Đừng cast JSON text bừa bãi trong WHERE

Ví dụ:

```sql
WHERE (payload ->> 'order_id')::bigint = 1001
```

nếu bảng chứa một document lỗi type hoặc số quá lớn, query có thể gặp lỗi cast. Tách `order_id` thành cột bigint được validate/constraint và index có thể là thiết kế tốt hơn nếu đây là khóa truy vấn chính.

### 27.3. Không đo trên 5 hàng rồi kết luận index vô dụng

Optimizer có thể chọn scan trên bảng nhỏ. Cần đủ dữ liệu, thống kê, thực tế query distribution, `EXPLAIN`/execution plan và đo read/write latency.

## 28. Các sai lầm thường gặp

| Sai lầm | Vì sao sai? | Cách xử lý |
|---|---|---|
| Lưu JSON vào TEXT nhưng không có validation | Dữ liệu hỏng cú pháp có thể lọt vào DB | CHECK bằng `JSON_VALID`/`ISJSON` hoặc dùng native JSON |
| Cho rằng `JSON_VALID=1` nghĩa là nghiệp vụ đúng | Không kiểm tra bắt buộc key/type/FK/tenant | JSON Schema, constraints, service validation |
| Coi `{"id":"1"}` giống `{"id":1}` | String và number khác loại JSON | Xác định và kiểm tra JSON type |
| Coi SQL NULL bằng JSON null | Một bên là ô không có giá trị, bên kia là JSON literal | Kiểm tra type/root và null semantics |
| Chỉ viết CHECK `jsonb_typeof(path)='array'` | Key thiếu có thể trả UNKNOWN và CHECK cho qua | Dùng `IS TRUE`/`COALESCE` để chặn key thiếu |
| Coi key trùng là cú pháp lỗi ở mọi parser | Nhiều hệ nhận và chuẩn hóa khác | Từ chối duplicate keys trước khi lưu khi cần |
| Tin vào thứ tự key object | JSON object không phải danh sách có thứ tự | Dùng array hoặc field order |
| Coi jsonb PostgreSQL giữ byte raw payload | Có chuẩn hóa format/keys | Lưu raw payload riêng nếu cần ký/audit |
| Nghĩ MySQL JSON = MariaDB JSON | MySQL native, MariaDB alias LONGTEXT | Kiểm tra DBMS và schema thực |
| Nghĩ SQL Server 2019 có native JSON type | Native type thuộc SQL Server 2025 và môi trường phù hợp | Dùng NVARCHAR + ISJSON ở bản cũ |
| Nghĩ `ISJSON(N'123')` trả 1 ở SQL Server 2016 | Không có type constraint thì chỉ nhận root object/array | SQL Server 2022+ dùng `ISJSON(..., VALUE)` |
| Nghĩ SQLite mặc định chấp nhận JSON5 ở `json_valid(X)` | Một tham số kiểm tra canonical JSON | 3.45+ dùng flags nếu chủ ý hỗ trợ JSON5 |
| Copy SQLite JSONB BLOB sang PostgreSQL | Hai định dạng nhị phân không tương thích | Trao đổi JSON text chuẩn |
| Coi `timestamp` trong JSON là SQL timestamp | JSON chỉ có string/number | Parse/validate timezone và format |
| Dùng JSON number cho mã có số 0 đầu | Mất số 0 hoặc gặp vấn đề precision | Dùng string định danh |
| Dùng JSON array thay bảng con có FK | Không tự có FK cho từng phần tử | Tách bảng con hoặc validation nghiệp vụ |
| Nối raw user string thành JSON/SQL | Lỗi escape, injection | Serializer + SQL parameters |
| Bật mọi GIN/path index | Chi phí lưu trữ/ghi lớn | Đo workload rồi chọn index |
| Bỏ qua kích thước/nesting payload | Có thể gây DoS | Giới hạn ở gateway/parser/DB |
| Lưu token và PII vào metadata JSON | Dễ rò qua log/backup/query | Redaction, phân quyền, retention |
| Ghi đè cả JSON theo bản đọc cũ | Lost update khi concurrent | Version/lock/path update phù hợp |
| Không version hóa tài liệu | Consumer đọc schema mới/cũ bị lỗi | `schema_version` và migration có kiểm soát |

## 29. Bài tập thực hành có đáp án

Các bài PostgreSQL giả định bảng tạm `demo_json_events` từ phần 5 đã được tạo và dữ liệu hợp lệ ban đầu vẫn có. Những lệnh cố ý lỗi là **bài thử riêng**, không chạy nối tiếp trong một transaction đã bị aborted.

### Bài 1. Xác định JSON đúng cú pháp

Trong những chuỗi sau, chuỗi nào đúng JSON chuẩn?

```text
A. {"a":1}
B. {'a':1}
C. {"a":true}
D. {"a":True}
E. [1,2,]
F. "hello"
G. null
```

**Đáp án:** **A, C, F, G**. B dùng nháy đơn, D viết hoa boolean, E có trailing comma.

### Bài 2. Một scalar có phải JSON không?

**Hỏi:** `42` hoặc `"ok"` có là JSON hợp lệ không?

**Đáp án:** có theo RFC 8259, nhưng **một DBMS/kiểu cột cụ thể** có thể giới hạn root object/array, ví dụ `ISJSON` không tham số trên SQL Server hoặc native JSON type của SQL Server 2025.

### Bài 3. PostgreSQL json và jsonb

**Hỏi:** cần giữ nguyên khoảng trắng và key trùng trong raw input, dùng `jsonb` có phù hợp không?

**Đáp án:** không nếu cần bảo toàn biểu diễn gốc. `jsonb` chuẩn hóa và không giữ nhiều key trùng. Cân nhắc `json` hoặc lưu raw bytes/text riêng với chính sách audit phù hợp.

### Bài 4. SQL NULL và JSON null

```sql
SELECT jsonb_typeof(NULL::jsonb), jsonb_typeof('null'::jsonb);
```

**Đáp án:** biểu thức thứ nhất trả **SQL NULL**; biểu thức thứ hai trả text `'null'`.

### Bài 5. Kiểm tra root object PostgreSQL

**Yêu cầu:** cột `payload jsonb NOT NULL` chỉ nhận JSON object.

**Đáp án:**

```sql
CHECK ((jsonb_typeof(payload) = 'object') IS TRUE)
```

Nó loại array, scalar và JSON null ở root.

### Bài 6. Missing key và CHECK UNKNOWN

**Tình huống:** `CHECK (jsonb_typeof(payload->'items') = 'array')` với payload không có key `items`.

**Đáp án:** phép so sánh có thể cho **UNKNOWN** và CHECK thông thường có thể chấp nhận. Dùng:

```sql
CHECK ((jsonb_typeof(payload -> 'items') = 'array') IS TRUE)
```

để chặn cả trường hợp không có key.

### Bài 7. Kiểm tra number và string

**Hỏi:** `{"order_id":1001}` và `{"order_id":"1001"}` có cùng JSON type không?

**Đáp án:** không. Giá trị đầu là **number**, giá trị sau là **string**. `->>` có thể trả text `1001` cho cả hai, nên dùng `jsonb_typeof(payload->'order_id')` khi cần phân biệt.

### Bài 8. PostgreSQL JSON path

**Yêu cầu:** đọc `metadata.channel` từ `demo_json_events` thành SQL text.

**Đáp án:**

```sql
SELECT payload #>> '{metadata,channel}' AS channel
FROM demo_json_events;
```

### Bài 9. Đếm phần tử array PostgreSQL

**Yêu cầu:** đếm số item mỗi event.

**Đáp án:**

```sql
SELECT event_id,
       jsonb_array_length(payload -> 'items') AS item_count
FROM demo_json_events;
```

Câu này giả định constraint bảo đảm `items` luôn là array. Nếu schema không có bảo đảm ấy, hàm có thể lỗi với input sai kiểu.

### Bài 10. MySQL tự kiểm tra syntax không?

**Hỏi:** cột `payload JSON NOT NULL` của MySQL có nhận `{"a":1,}` không?

**Đáp án:** không, JSON type của MySQL kiểm tra cú pháp và từ chối trailing comma hỏng.

### Bài 11. JSON_VALID MySQL/MariaDB

**Yêu cầu:** kiểm tra chuỗi `{"x":1}` có đúng JSON không.

**Đáp án:**

```sql
SELECT JSON_VALID('{"x":1}');
```

Với chuỗi hợp lệ trả **1**. Hàm kiểm tra cú pháp, không xác nhận `x` đúng nghiệp vụ.

### Bài 12. SQL Server 2019

**Yêu cầu:** SQL Server 2019 lưu JSON text vào `NVARCHAR(MAX)` và từ chối syntax hỏng.

**Đáp án:**

```sql
CREATE TABLE dbo.documents (
    id INT PRIMARY KEY,
    payload NVARCHAR(MAX) NOT NULL,
    CONSTRAINT chk_documents_json CHECK (ISJSON(payload) = 1)
);
```

Không dùng native `payload JSON` như SQL Server 2025.

### Bài 13. SQL Server root scalar

**Hỏi:** vì sao `ISJSON(N'123')` có thể trả 0 dù 123 là JSON value đúng?

**Đáp án:** dạng `ISJSON` không có tham số thứ hai kiểm tra root object/array. SQL Server 2022+ hỗ trợ `ISJSON(N'123', VALUE)` để nhận mọi top-level JSON value chuẩn.

### Bài 14. MariaDB JSON alias

**Hỏi:** MariaDB `JSON` có là cùng kiểu nhị phân với MySQL `JSON` không?

**Đáp án:** không. MariaDB mô tả `JSON` là alias cho `LONGTEXT` với collation thích hợp; kiểm tra `SHOW CREATE TABLE` và constraint `JSON_VALID` theo phiên bản.

### Bài 15. Oracle 19c IS JSON

**Yêu cầu:** cột `payload CLOB` chỉ chấp nhận JSON hợp lệ.

**Đáp án:**

```sql
CREATE TABLE demo_docs (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT chk_payload CHECK (payload IS JSON)
);
```

### Bài 16. SQLite TEXT và JSON_VALID

**Yêu cầu:** cột JSON TEXT bắt buộc, kiểm tra cú pháp.

**Đáp án:**

```sql
CREATE TABLE docs (
    id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL CHECK (json_valid(payload) = 1)
);
```

### Bài 17. SQLite JSON5

**Hỏi:** trên SQLite 3.45.0+, làm sao kiểm tra dữ liệu `{x:1}` theo chính sách JSON5?

**Đáp án:**

```sql
SELECT json_valid('{x:1}', 2);
```

Kết quả **1** theo JSON5 SQLite hỗ trợ, nhưng `json_valid('{x:1}')` trả **0** vì không phải JSON text chuẩn.

### Bài 18. SQLite JSONB và PostgreSQL jsonb

**Hỏi:** có thể gửi trực tiếp JSONB BLOB của SQLite 3.45 cho cột `jsonb` PostgreSQL không?

**Đáp án:** không. Hai định dạng nhị phân khác nhau. Trao đổi bằng JSON text chuẩn hoặc protocol phù hợp.

### Bài 19. Duplicate keys

**Tình huống:** `{"role":"user","role":"admin"}` đi qua ba dịch vụ với parser khác nhau.

**Đáp án:** dù nhiều parser vẫn chấp nhận syntax, mỗi nơi có thể chọn một giá trị khác cho key trùng. Với field liên quan quyền, hãy **từ chối duplicate key ở cổng nhập** và dùng cùng policy trên toàn luồng.

### Bài 20. CHECK hay JSON Schema?

**Yêu cầu:** mỗi item phải có `sku` string không rỗng và `qty` integer >= 1.

**Đáp án:** `JSON_VALID` và CHECK chỉ root type không đủ. Dùng JSON Schema validator với `items.items.required`/`properties`, trigger có kiểm tra phù hợp hoặc chuẩn hóa thành bảng `order_items`. Vẫn phải kiểm tra SKU tồn tại/tenant có quyền ở lớp quan hệ/nghiệp vụ.

### Bài 21. Chọn index JSON PostgreSQL

**Tình huống:** lọc thường xuyên theo `tenant_id` và `payload->>'event_type'`.

**Đáp án:**

```sql
CREATE INDEX ix_event_type_tenant
ON demo_json_events (tenant_id, (payload ->> 'event_type'));
```

Index B-tree expression có thể phù hợp hơn GIN toàn document cho truy vấn equality trên path cố định, tùy workload.

### Bài 22. Bảo vệ tenant

**Tình huống:** JSON có `tenant_id = 20`, nhưng người dùng đang thao tác trong tenant 10.

**Đáp án:** JSON đúng cú pháp vẫn không được phép tự quyết định tenant. Dùng tenant ID đã xác thực/ủy quyền từ server, ràng buộc cột quan hệ/RLS theo thiết kế, và xử lý mâu thuẫn giữa cột với payload.

### Bài 23. Chống mất cập nhật JSON

**Tình huống:** hai request cùng đọc document cũ rồi thay cả JSON bằng bản sao đã sửa.

**Đáp án:** có thể mất thay đổi của request ghi trước. Dùng transaction/lock, path update phù hợp hoặc `version_no` với optimistic concurrency.

### Bài 24. Dữ liệu quá lớn

**Tình huống:** client gửi JSON 100 MB có cấu trúc hợp lệ nhưng có nhiều array lồng sâu.

**Đáp án:** chỉ kiểm tra cú pháp ở DB là chưa đủ. Cần giới hạn kích thước, số key, độ sâu, số phần tử và thời gian parse/validate ở gateway/service; DB giữ constraint như lớp bảo vệ bổ sung.

## 30. Tài liệu chính thức tham khảo

Các tài liệu theo DBMS dưới đây giúp kiểm tra lại cú pháp, giới hạn và mốc phiên bản khi triển khai:

- **PostgreSQL — JSON Types:** https://www.postgresql.org/docs/current/datatype-json.html
- **PostgreSQL — JSON Functions and Operators:** https://www.postgresql.org/docs/current/functions-json.html
- **PostgreSQL — JSONB Indexing:** https://www.postgresql.org/docs/current/datatype-json.html#JSON-INDEXING
- **MySQL 8.4 — JSON Data Type:** https://dev.mysql.com/doc/refman/8.4/en/json.html
- **MySQL — JSON Schema Validation Functions:** https://dev.mysql.com/doc/refman/8.4/en/json-validation-functions.html
- **MariaDB — JSON Data Type:** https://mariadb.com/docs/server/reference/data-types/string-data-types/json
- **MariaDB — JSON_VALID:** https://mariadb.com/docs/server/reference/sql-functions/special-functions/json-functions/json_valid
- **SQL Server — Work with JSON Data:** https://learn.microsoft.com/en-us/sql/relational-databases/json/json-data-sql-server
- **SQL Server — ISJSON:** https://learn.microsoft.com/en-us/sql/t-sql/functions/isjson-transact-sql
- **SQL Server 2025 — JSON Data Type:** https://learn.microsoft.com/en-us/sql/t-sql/data-types/json-data-type
- **Oracle — IS JSON condition:** https://docs.oracle.com/en/database/oracle/oracle-database/21/adjsn/conditions-is-json-and-is-not-json.html
- **Oracle — JSON Data Types and Storage:** https://docs.oracle.com/en/database/oracle/oracle-database/21/adjsn/json-data-types.html
- **SQLite — JSON Functions and Operators:** https://www.sqlite.org/json1.html
- **JSON Schema:** https://json-schema.org/learn/getting-started-step-by-step

**Lưu ý:** MySQL/MariaDB, SQL Server 2016/2022/2025, Oracle 19c/21c+ và SQLite 3.42/3.45 khác nhau ở các tính năng JSON. Đừng sao chép một ví dụ theo phiên bản mới vào server cũ mà không xác nhận tài liệu và cấu hình.

## Kết luận

**Lưu JSON thành công chưa có nghĩa dữ liệu đã hợp lệ cho ứng dụng.** Một hệ thống đáng tin cần ít nhất ba lớp bảo vệ:

1. **Hợp lệ về cú pháp:** dùng kiểu JSON/JSONB hoặc `JSON_VALID`, `ISJSON`, `IS JSON`, `json_valid` theo đúng DBMS để từ chối văn bản hỏng.
2. **Hợp lệ về cấu trúc:** yêu cầu root, key, JSON type, miền giá trị và array theo contract; dùng CHECK, JSON Schema validator, trigger hoặc mô hình quan hệ khi phù hợp.
3. **Hợp lệ về nghiệp vụ/bảo mật:** phân quyền tenant, khóa ngoại, chống trùng, giới hạn payload, transaction, audit và quản lý dữ liệu nhạy cảm.

PostgreSQL phân biệt `json` và `jsonb`; MySQL có kiểu JSON gốc; MariaDB dùng alias LONGTEXT; SQL Server trước 2025 thường dùng NVARCHAR cùng ISJSON, còn SQL Server 2025 có native json; Oracle có `IS JSON` và native JSON ở các phiên bản mới; SQLite dùng JSON functions trên TEXT và có JSONB nội bộ từ 3.45. Mỗi hệ có **cách lưu, trả SQL NULL, xử lý key trùng và tối ưu truy vấn khác nhau**.

Khi thiết kế, hãy để các **khóa định danh, tenant, quan hệ và trường lọc quan trọng** ở cột SQL nếu chúng cần ràng buộc/đánh index bền vững; dùng JSON cho phần dữ liệu linh hoạt. Luôn thống nhất policy về **duplicate keys, JSON null, chuẩn hóa số/Unicode, schema_version và giới hạn tài nguyên** để tránh tình trạng “đúng JSON nhưng sai dữ liệu”.

