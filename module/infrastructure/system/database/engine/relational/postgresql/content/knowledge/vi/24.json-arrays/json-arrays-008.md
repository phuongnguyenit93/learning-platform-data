# Kiểm tra dữ liệu JSON và bảo vệ các trường quan trọng trong PostgreSQL

## 1. Vì sao JSON hợp lệ chưa có nghĩa là dữ liệu hợp lệ?

PostgreSQL hỗ trợ hai kiểu dữ liệu JSON phổ biến: `json` và `jsonb`. Khi một ứng dụng lưu cấu trúc linh hoạt vào cột `jsonb`, database có thể kiểm tra cú pháp JSON, truy vấn từng khóa, tạo chỉ mục và cập nhật một phần tài liệu. Tuy nhiên, **một giá trị JSON hợp lệ về cú pháp chưa chắc đúng hợp đồng nghiệp vụ**.

Ví dụ bốn tài liệu sau đều là JSON hợp lệ:

```json
{"external_id":"ORD-1001","status":"NEW","amount_cents":150000}
```

```json
{"external_id":null,"status":"NEW","amount_cents":150000}
```

```json
{"external_id":"ORD-1001","status":123,"amount_cents":-99}
```

```json
{"status":"PAID","amount_cents":"one hundred"}
```

Nhưng hệ thống có thể yêu cầu:

- `external_id` bắt buộc là **chuỗi không rỗng**, không được đổi sau khi tạo.
- `status` chỉ là một trong các trạng thái `NEW`, `PAID`, `CANCELLED`.
- `amount_cents` phải là **số nguyên không âm** và nằm trong giới hạn cho phép.
- `items` phải là **mảng không rỗng**, mỗi phần tử chứa mã sản phẩm và số lượng hợp lệ.
- `external_id` phải **duy nhất trong từng tenant**.
- Một đơn `PAID` không được tự ý quay lại `NEW`.
- Người dùng thuộc tenant A không được cập nhật tài liệu của tenant B.

Lưu JSON vào một cột không miễn cho hệ thống trách nhiệm bảo vệ các quy tắc đó.

> **Nguyên tắc cốt lõi:** phân biệt **kiểm tra cú pháp JSON**, **kiểm tra cấu trúc**, **kiểm tra bất biến nghiệp vụ** và **kiểm soát quyền ghi**. Mỗi lớp giải quyết một loại vấn đề khác nhau.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt `json` và `jsonb`, JSON `null` và SQL `NULL`.
2. Kiểm tra khóa bắt buộc, kiểu dữ liệu, giá trị cho phép và cấu trúc lồng nhau.
3. Hiểu vì sao PostgreSQL `CHECK` **chấp nhận UNKNOWN/NULL**, và cách viết constraint không bỏ lọt trường thiếu.
4. Bảo vệ trường định danh bằng `UNIQUE` trên biểu thức hoặc bằng cột quan hệ.
5. Kiểm tra số nguyên/số tiền JSON mà không phụ thuộc vào cast thiếu an toàn.
6. Kiểm tra mảng JSON bằng SQL, hàm validation thuần và JSONPath thích hợp.
7. Thiết kế thao tác cập nhật bằng `jsonb_set` với điều kiện trạng thái và kiểm soát concurrency.
8. Chặn sửa trường bất biến hoặc chuyển trạng thái sai bằng trigger khi cần.
9. Phân biệt bảo đảm của `CHECK`, `UNIQUE`, `FOREIGN KEY`, trigger, RLS và quyền cột.
10. Hiểu khi nào nên tách trường quan trọng ra cột thường thay vì giữ toàn bộ trong JSON.
11. Dùng GIN/expression index để truy vấn JSONB hiệu quả.
12. Triển khai ràng buộc dần dần trên bảng đang có dữ liệu.
13. Kiểm chứng các trường hợp lỗi và dữ liệu hợp lệ bằng bài tập thực hành.

---

## 2. JSON, JSONB và trách nhiệm của từng lớp

### 2.1. Kiểu json

`json` lưu văn bản JSON đã được kiểm tra cú pháp, bảo toàn nhiều đặc điểm biểu diễn đầu vào như khoảng trắng, thứ tự khóa và việc lặp khóa trong văn bản.

Ví dụ:

```sql
SELECT
    '{"a":1, "a":2}'::json AS as_json;
```

Dữ liệu JSON có thể chứa hai khóa `a` trong bản biểu diễn. Khi một ứng dụng dựa vào “khóa cuối cùng thắng” hoặc “khóa đầu tiên thắng”, việc có khóa trùng có thể gây hiểu nhầm giữa các thành phần của hệ thống.

### 2.2. Kiểu jsonb

`jsonb` lưu dạng nhị phân đã được phân tích, hỗ trợ nhiều toán tử và index hơn. Nó không giữ nguyên thứ tự khóa, khoảng trắng hoặc các khóa trùng như văn bản đầu vào; với khóa trùng, giá trị còn lại có thể là giá trị xuất hiện cuối cùng trong đối tượng đầu vào.

```sql
SELECT
    '{"a":1, "a":2}'::jsonb AS as_jsonb;
```

Vì vậy, nếu **chính việc gửi khóa trùng phải bị từ chối**, chỉ lưu vào `jsonb` rồi kiểm tra sau không đủ để khôi phục thông tin về khóa đã bị gộp. Việc từ chối duplicate keys cần thực hiện **ở lúc parse/nhận đầu vào**, với cơ chế parser phù hợp.

### 2.3. JSONB bảo đảm gì và không bảo đảm gì?

| Điều cần kiểm tra | Chỉ dùng cột jsonb đã đủ chưa? |
|---|---|
| Văn bản đầu vào là JSON hợp lệ | Có, ở bước chuyển/cast vào jsonb |
| Root phải là object | Chưa; JSONB có thể là array, number, string, boolean, null |
| Có khóa external_id | Chưa |
| external_id là chuỗi không rỗng | Chưa |
| status thuộc tập trạng thái hợp lệ | Chưa |
| amount_cents không âm | Chưa |
| items là mảng các object hợp lệ | Chưa |
| ID duy nhất theo tenant | Chưa |
| Không sửa external_id sau INSERT | Chưa |
| Phân quyền theo tenant | Chưa |

Ngoài ra, `jsonb` có giới hạn và quy tắc xử lý chuỗi/Unicode, số theo khả năng của PostgreSQL. Không nên mô tả nó chỉ như “cột text có kiểm tra dấu ngoặc”.

### 2.4. Mặc định thường chọn jsonb khi cần truy vấn

Nếu hệ thống thường đọc khóa, lọc theo trạng thái, cập nhật tài liệu và lập chỉ mục, `jsonb` là lựa chọn phổ biến. Nếu cần giữ biểu diễn JSON gốc từng ký tự, hãy xem xét `json` hoặc lưu riêng bản raw có chủ đích. Quyết định dựa trên yêu cầu audit, hiệu năng và ngữ nghĩa dữ liệu.

## 3. Phân biệt SQL NULL, JSON null và khóa không tồn tại

Đây là nền tảng để viết ràng buộc đúng.

Xét các giá trị:

```sql
SELECT
    NULL::jsonb                   AS sql_null,
    'null'::jsonb                 AS json_null,
    '{}'::jsonb                   AS empty_object,
    '{"status":null}'::jsonb       AS object_with_json_null;
```

Ba trường hợp có ý nghĩa khác nhau:

1. **SQL NULL:** bản thân giá trị cột là NULL hoặc biểu thức trả SQL NULL.
2. **JSON null:** tài liệu JSON có giá trị JSON `null`.
3. **Khóa thiếu:** object không có thuộc tính được yêu cầu.

### 3.1. Toán tử -> và ->>

```sql
SELECT
    '{"status":null}'::jsonb -> 'status'  AS json_value,
    '{"status":null}'::jsonb ->> 'status' AS text_value,
    '{}'::jsonb -> 'status'              AS missing_json,
    '{}'::jsonb ->> 'status'             AS missing_text;
```

Ý nghĩa:

- `->` trả một giá trị kiểu `jsonb`; với khóa chứa JSON null, kết quả là giá trị JSONB `null`.
- `->>` trả dạng text; JSON null thường được biểu diễn thành **SQL NULL**.
- Khóa không tồn tại khiến các phép trích xuất trả SQL NULL, không phải lỗi.

Vì vậy:

```sql
doc ->> 'status' IS NULL
```

không phân biệt được **status thiếu** với **status có JSON null**.

### 3.2. jsonb_typeof

```sql
SELECT
    jsonb_typeof('null'::jsonb)     AS json_null_type,
    jsonb_typeof('"hello"'::jsonb)  AS string_type,
    jsonb_typeof('123'::jsonb)      AS number_type,
    jsonb_typeof('[1,2]'::jsonb)    AS array_type,
    jsonb_typeof('{"a":1}'::jsonb)  AS object_type;
```

Hàm có thể trả các chuỗi kiểu:

```text
null
string
number
array
object
```

Ngoài ra còn `boolean`.

Điểm rất quan trọng: `jsonb_typeof('null'::jsonb)` trả **chuỗi text 'null'**, không phải SQL NULL. Nếu đối số là SQL NULL hoặc khóa được trích xuất không tồn tại, kết quả thường là **SQL NULL**.

### 3.3. Kiểm tra khóa có tồn tại

```sql
SELECT
    '{"status":null}'::jsonb ? 'status' AS key_present,
    '{}'::jsonb ? 'status'             AS key_missing;
```

`?` kiểm tra sự tồn tại của khóa **ở cấp trên cùng của object** trong trường hợp này.

Kết quả:

```text
key_present = true
key_missing = false
```

Nhưng `? 'status'` không kiểm tra nội dung: JSON null, chuỗi rỗng hoặc kiểu sai vẫn được coi là **khóa tồn tại**.

## 4. Bẫy quan trọng: CHECK chấp nhận UNKNOWN

Trong PostgreSQL, một `CHECK` constraint được coi là thỏa khi biểu thức trả `TRUE` **hoặc NULL/UNKNOWN**. Nó từ chối hàng khi biểu thức trả `FALSE`.

Ví dụ constraint chưa đủ chặt:

```sql
CHECK (length(doc ->> 'external_id') > 0)
```

Với tài liệu:

```json
{"status":"NEW"}
```

khóa `external_id` thiếu, nên:

```text
doc ->> 'external_id' = SQL NULL
length(NULL)         = SQL NULL
NULL > 0             = UNKNOWN
```

CHECK **không từ chối** chỉ vì biểu thức trả UNKNOWN.

### 4.1. Dùng COALESCE khi muốn NULL là không hợp lệ

```sql
CHECK (
    COALESCE(
        length(btrim(doc ->> 'external_id')) > 0,
        FALSE
    )
)
```

Khi khóa thiếu hoặc JSON null, điều kiện bên trong là SQL NULL, và `COALESCE(...,FALSE)` trả FALSE nên CHECK từ chối.

### 4.2. Dùng IS TRUE

Một cách khác:

```sql
CHECK (
    (length(btrim(doc ->> 'external_id')) > 0) IS TRUE
)
```

`IS TRUE` trả TRUE **chỉ khi** biểu thức là TRUE; với FALSE hoặc UNKNOWN, nó trả FALSE.

### 4.3. Dùng kết hợp tồn tại + kiểu + giá trị

```sql
CHECK (
    doc ? 'external_id'
    AND jsonb_typeof(doc -> 'external_id') = 'string'
    AND length(btrim(doc ->> 'external_id')) > 0
)
```

Khi khóa thiếu, `doc ? 'external_id'` là FALSE. Kết hợp `FALSE AND UNKNOWN` vẫn là FALSE. Khi khóa có JSON null, phép so kiểu trả FALSE.

Để tránh phụ thuộc cách suy luận ba giá trị trong biểu thức phức tạp, có thể viết chặt hơn bằng `IS TRUE` hoặc `COALESCE` ở đầu.

### 4.4. Không chỉ kiểm tra NOT NULL của cột JSONB

`doc jsonb NOT NULL` bảo đảm **toàn bộ cột** không phải SQL NULL; nó **không** bảo đảm mọi khóa bên trong tồn tại hoặc khác JSON null.

Bảo vệ tài liệu phải được làm ở cả cấp cột và cấp thuộc tính theo nghiệp vụ.

## 5. Xây dựng schema lab cho đơn hàng JSONB

Chạy ví dụ trong database thực hành. Dữ liệu và lệnh UPDATE/ALTER có mục đích minh họa; không áp dụng trực tiếp lên production.

### 5.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS json313;
```

### 5.2. Tài liệu đơn hàng chuẩn

Trong bài, một đơn có dạng:

```json
{
  "external_id": "ORD-2026-0001",
  "status": "NEW",
  "amount_cents": 250000,
  "currency": "VND",
  "items": [
    {
      "sku": "SKU-A",
      "qty": 2,
      "unit_price_cents": 100000
    },
    {
      "sku": "SKU-B",
      "qty": 1,
      "unit_price_cents": 50000
    }
  ],
  "shipping": {
    "city": "Da Nang",
    "note": null
  },
  "metadata": {
    "source": "web"
  }
}
```

Đây là tài liệu **ví dụ**, chưa phải JSON Schema đầy đủ. Các quy tắc nghiệp vụ sẽ được chuyển thành các constraint/hàm trong bài.

### 5.3. Tạo bảng lưu JSONB

```sql
CREATE TABLE json313.orders (
    order_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    doc jsonb NOT NULL,
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT order_doc_root_object
        CHECK (jsonb_typeof(doc) = 'object')
);
```

Tại bước này, chỉ có:

- `order_pk` là định danh vật lý của hàng.
- `tenant_id` là cột quan hệ riêng.
- `doc` phải là JSONB không SQL NULL và có root là object.
- `version` dùng để minh họa optimistic concurrency.
- `created_at` được lưu dưới kiểu thời gian chuẩn.

Các constraint trên thuộc tính sẽ được bổ sung từng phần để dễ quan sát.

### 5.4. Chèn một tài liệu hợp lệ

```sql
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{
      "external_id":"ORD-2026-0001",
      "status":"NEW",
      "amount_cents":250000,
      "currency":"VND",
      "items":[
        {"sku":"SKU-A","qty":2,"unit_price_cents":100000},
        {"sku":"SKU-B","qty":1,"unit_price_cents":50000}
      ],
      "shipping":{"city":"Da Nang","note":null},
      "metadata":{"source":"web"}
    }'::jsonb
)
RETURNING order_pk, tenant_id, doc;
```

Lệnh trên cần chạy **một lần** trong fixture lab để tránh tạo nhiều đơn cùng external_id trước khi unique index được thêm.

### 5.5. Xem từng thuộc tính

```sql
SELECT
    order_pk,
    tenant_id,
    doc ->> 'external_id' AS external_id,
    doc ->> 'status' AS status,
    doc -> 'amount_cents' AS amount_json,
    doc ->> 'amount_cents' AS amount_text,
    doc -> 'items' AS items_json
FROM json313.orders;
```

Lưu ý `doc ->> 'amount_cents'` có **kiểu text**, dù giá trị JSON gốc là number.

## 6. Kiểm tra root object

JSONB cho phép root là:

```sql
SELECT
    jsonb_typeof('{}'::jsonb) AS object_type,
    jsonb_typeof('[]'::jsonb) AS array_type,
    jsonb_typeof('42'::jsonb) AS number_type,
    jsonb_typeof('true'::jsonb) AS boolean_type,
    jsonb_typeof('"abc"'::jsonb) AS string_type,
    jsonb_typeof('null'::jsonb) AS null_type;
```

Nếu nghiệp vụ yêu cầu một **object**:

```sql
CHECK (jsonb_typeof(doc) = 'object')
```

Vì cột `doc` được khai báo `NOT NULL`, giá trị SQL NULL đã bị chặn. JSON null cũng không vượt qua điều kiện object.

### 6.1. Vì sao root validation cần thiết?

Nếu không kiểm tra root:

```sql
INSERT INTO json313.orders(tenant_id, doc)
VALUES (7, '[]'::jsonb);
```

có thể tạo hàng mà những truy vấn `doc->>'status'` trả SQL NULL. Các tầng ứng dụng vốn tưởng `doc` luôn là object sẽ phải xử lý một trường hợp ngoài dự kiến.

### 6.2. JSONB không phải schema validation engine toàn năng

Root object mới chỉ là lớp đầu. Object ấy có thể thiếu khóa bắt buộc, có khóa sai kiểu, chứa mảng lẫn số/chuỗi, hoặc một trạng thái không hợp lệ.

Cần xác định rõ **hợp đồng dữ liệu** trước khi thêm constraint.

## 7. Kiểm tra các khóa bắt buộc

Giả sử mọi đơn cần:

```text
external_id
status
amount_cents
currency
items
```

Với JSONB object, kiểm tra đồng thời một số khóa ở cấp trên cùng:

```sql
SELECT
    '{
      "external_id":"ORD-1",
      "status":"NEW",
      "amount_cents":0,
      "currency":"VND",
      "items":[]
    }'::jsonb
    ?& ARRAY[
        'external_id',
        'status',
        'amount_cents',
        'currency',
        'items'
    ] AS has_all_keys;
```

`?&` kiểm tra **tất cả** chuỗi trong mảng text đều hiện diện như khóa trên cùng của object.

Thêm constraint:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_required_keys
CHECK (
    doc ?& ARRAY[
        'external_id',
        'status',
        'amount_cents',
        'currency',
        'items'
    ]
);
```

### 7.1. Các toán tử tồn tại

| Toán tử | Ý nghĩa đơn giản |
|---|---|
| `doc ? 'x'` | Có khóa x ở object cấp trên cùng, hoặc chuỗi phù hợp ở trường hợp array |
| `doc ?\| ARRAY['a','b']` | Có **ít nhất một** khóa/giá trị được hỏi |
| `doc ?& ARRAY['a','b']` | Có **tất cả** khóa/giá trị được hỏi |

Các toán tử này không tự tìm đệ quy toàn bộ object lồng nhau. Ví dụ `doc ? 'city'` không có nghĩa có `shipping.city`.

### 7.2. Tồn tại chưa đủ

Một tài liệu:

```json
{"external_id":null,"status":null,"amount_cents":null,"currency":null,"items":null}
```

vẫn có **đủ tên khóa**. Nó phải bị các ràng buộc **kiểu và giá trị** từ chối.

## 8. Kiểm tra chuỗi không rỗng và định dạng

Yêu cầu của `external_id`:

- Phải tồn tại.
- Phải là JSON string.
- Không chỉ có khoảng trắng.
- Chỉ gồm ký tự cho phép.
- Giới hạn độ dài.

Ví dụ constraint:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_external_id_valid
CHECK (
    (
        jsonb_typeof(doc -> 'external_id') = 'string'
        AND length(btrim(doc ->> 'external_id'))
            BETWEEN 1 AND 64
        AND (doc ->> 'external_id')
            ~ '^ORD-[A-Za-z0-9-]+$'
    ) IS TRUE
);
```

Các dạng không hợp lệ:

```json
{"external_id":null}
```

```json
{"external_id":""}
```

```json
{"external_id":"    "}
```

```json
{"external_id":123}
```

```json
{"external_id":"INVALID CODE"}
```

### 8.1. Vì sao cần jsonb_typeof trước khi dùng ->>?

Toán tử `->>` chuyển các giá trị JSON thành text. Vì thế JSON number `123` có thể được trích thành chuỗi `'123'`.

Nếu chỉ kiểm tra regex hoặc độ dài text mà không kiểm tra kiểu JSON gốc, bạn có thể vô tình chấp nhận number ở trường vốn phải là string.

### 8.2. btrim không tự chuẩn hóa dữ liệu được lưu

`btrim(doc->>'external_id')` trong CHECK chỉ dùng để kiểm tra. Nó **không sửa** `" ORD-1 "` thành `"ORD-1"`.

Nếu muốn tự trim/lowercase trước lưu, hãy xác định rõ chính sách:

- Chuẩn hóa tại ứng dụng rồi ghi.
- Dùng một lớp ghi/hàm có kiểm soát.
- Dùng trigger chuẩn hóa nếu phù hợp.

Không mặc định phép kiểm tra đã sửa giá trị JSON.

### 8.3. Regex chưa phải xác thực ID toàn diện

Regex chỉ kiểm tra hình dạng ký tự theo mẫu. Nó không chứng minh ID tồn tại ở hệ thống bên ngoài, không bảo đảm uniqueness và không tự chặn thay đổi ID sau khi tạo.

## 9. Kiểm tra enum và trạng thái

Trường `status` chỉ được nhận:

```text
NEW
PAID
CANCELLED
```

Constraint:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_status_valid
CHECK (
    (
        jsonb_typeof(doc -> 'status') = 'string'
        AND doc ->> 'status' IN ('NEW','PAID','CANCELLED')
    ) IS TRUE
);
```

Lưu ý dấu ngoặc quanh phép truy cập và điều kiện; trong PostgreSQL, cú pháp với `->>` và `IN` nên được viết rõ để tránh nhầm khi đọc biểu thức.

### 9.1. Vì sao IS TRUE là lựa chọn dễ đọc?

Nếu `status` không tồn tại, `doc->>'status'` trả SQL NULL; `NULL IN (...)` trả UNKNOWN. `(...) IS TRUE` đảm bảo chỉ TRUE mới được chấp nhận.

Nếu `status` là JSON null, `jsonb_typeof` trả text `'null'`, nên điều kiện kiểu sai.

Nếu `status` là number, điều kiện kiểu cũng sai dù text từ `->>` tình cờ trùng một chuỗi được phép.

### 9.2. Danh sách enum có thể phát triển

Nếu trạng thái nghiệp vụ thay đổi thường xuyên hoặc có luồng chuyển trạng thái phức tạp, cân nhắc chuyển `status` thành cột quan hệ riêng hoặc bảng trạng thái/định nghĩa workflow.

Một CHECK enum cố định dễ hiểu nhưng mọi lần thêm trạng thái có thể cần migration. Hãy đặt trạng thái ở nơi có hợp đồng rõ ràng, thay vì giữ trong JSON chỉ vì “linh hoạt”.

## 10. Số nguyên trong JSONB: đừng tin phép cast thiếu kiểm tra

JSON có một kiểu chung là **number**. Nó không phân biệt integer và decimal như các kiểu `integer`, `bigint`, `numeric` của PostgreSQL.

Ví dụ đều là JSON number:

```json
100
```

```json
100.25
```

```json
-10
```

Nhưng `amount_cents` yêu cầu **số nguyên không âm**.

### 10.1. Chỉ kiểm tra jsonb_typeof='number' chưa đủ

```sql
CHECK (jsonb_typeof(doc -> 'amount_cents') = 'number')
```

vẫn cho phép `-10`, `100.25` và những giá trị vượt ngưỡng tiền nghiệp vụ.

### 10.2. CASE để chỉ cast khi đúng kiểu

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_amount_valid
CHECK (
    CASE
        WHEN jsonb_typeof(doc -> 'amount_cents') = 'number'
        THEN
            (doc ->> 'amount_cents')::numeric >= 0
            AND (doc ->> 'amount_cents')::numeric
                <= 1000000000000
            AND (doc ->> 'amount_cents')::numeric
                = trunc((doc ->> 'amount_cents')::numeric)
        ELSE FALSE
    END
);
```

Giải thích:

1. Nếu JSON type không phải `number`, trả FALSE.
2. Nếu đúng kiểu number, chuyển sang `numeric` để so giới hạn.
3. `value = trunc(value)` chỉ chấp nhận giá trị toán học nguyên.
4. Phạm vi tiền được đặt theo giới hạn nghiệp vụ ví dụ.
5. Nếu khóa thiếu, nhánh WHEN không TRUE nên đi vào ELSE FALSE.

### 10.3. Vì sao tránh cast trực tiếp trước kiểm tra?

Câu:

```sql
CHECK ((doc ->> 'amount_cents')::integer >= 0)
```

có thể gây lỗi parse hoặc overflow với dữ liệu JSON string như `"abc"` hoặc số lớn. Việc kiểm tra kiểu và dùng một cấu trúc `CASE` phù hợp giúp thể hiện rõ đường đi kiểm tra.

Quan trọng: **không dựa vào thứ tự đánh giá AND của SQL** như một bảo đảm rằng database luôn thử `jsonb_typeof` trước, rồi mới cast. PostgreSQL có quyền biến đổi thứ tự đánh giá biểu thức boolean khi hợp lệ. Khi có cast có thể lỗi, dùng `CASE` có nhánh guard rõ ràng.

### 10.4. Vì sao numeric thay vì integer?

`jsonb` nhận các JSON number theo quy tắc số của PostgreSQL. Nếu ép thẳng sang `integer` hoặc `bigint`, có thể lỗi khi giá trị nằm ngoài miền kiểu đó.

Dùng `numeric` để kiểm tra phạm vi trước là cách dễ biểu đạt bài học; trong schema production, cân nhắc lưu số tiền ở cột quan hệ `bigint` hoặc `numeric(p,s)` và kiểm tra giới hạn tương ứng.

## 11. Kiểm tra currency

Tiền tệ của đơn chỉ được nhận `VND` hoặc `USD` trong ví dụ:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_currency_valid
CHECK (
    (
        jsonb_typeof(doc -> 'currency') = 'string'
        AND doc ->> 'currency' IN ('VND', 'USD')
    ) IS TRUE
);
```

### 11.1. Một giá trị currency hợp lệ chưa đủ xác minh tiền

Nếu nghiệp vụ cần tính tiền chính xác, phải quyết định:

- Đơn vị nhỏ nhất của từng loại tiền.
- Giới hạn amount cho mỗi currency.
- Tỷ giá được lấy ở thời điểm nào.
- Quy tắc hoàn tiền, giảm giá, thuế.
- Tổng tiền có bắt buộc bằng tổng các dòng item không.

Một CHECK đơn giản trên `currency` chỉ bảo vệ tập mã được phép, không giải quyết kế toán.

### 11.2. Đừng trộn dữ liệu động với CHECK cứng

Nếu danh sách currency, hạn mức hoặc trạng thái nằm ở bảng cấu hình có thể thay đổi, PostgreSQL không cho phép một CHECK tùy ý tra bảng khác và mặc nhiên bảo đảm tính đúng lâu dài.

Có thể cần cột quan hệ và FOREIGN KEY đến bảng currency, transaction/service protocol phù hợp hoặc thiết kế mô hình dữ liệu khác.

## 12. Kiểm tra JSON array và độ dài

Trường `items` phải:

1. Tồn tại.
2. Có kiểu JSON array.
3. Có ít nhất một phần tử.
4. Không vượt quá số phần tử giới hạn theo ví dụ.

Đơn giản:

```sql
SELECT
    jsonb_typeof('[1,2,3]'::jsonb) AS t,
    jsonb_array_length('[1,2,3]'::jsonb) AS n;
```

Nhưng `jsonb_array_length` kỳ vọng một JSON array. Áp dụng cho object/string có thể gây lỗi.

### 12.1. Dùng CASE để bảo vệ lệnh lấy độ dài

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_items_array_valid
CHECK (
    CASE
        WHEN jsonb_typeof(doc -> 'items') = 'array'
        THEN jsonb_array_length(doc -> 'items')
            BETWEEN 1 AND 100
        ELSE FALSE
    END
);
```

Với:

```json
{"items":{}}
```

nhánh ELSE trả FALSE.

Với:

```json
{"items":[]}
```

nhánh THEN đánh giá `0 BETWEEN 1 AND 100`, trả FALSE.

Với:

```json
{"items":[null]}
```

array có một phần tử nên vượt qua kiểm tra **độ dài**, nhưng phần tử chưa hợp lệ. Ta cần tầng validation tiếp theo.

### 12.2. Mảng JSON khác mảng SQL

PostgreSQL có kiểu native SQL array như `integer[]`, `text[]`, nhưng `items` ở đây là **JSON array**, có thể chứa object nhiều thuộc tính.

Không dùng `cardinality(items)` như với SQL array để kiểm tra trực tiếp một cột `jsonb`; dùng `jsonb_array_length` cho JSON array.

## 13. Kiểm tra các phần tử của JSON array

Giả sử mỗi phần tử `items` phải là object có:

```json
{
  "sku":"SKU-A",
  "qty":2,
  "unit_price_cents":100000
}
```

Yêu cầu:

- Mỗi item là JSON object.
- `sku` là string không rỗng.
- `qty` là number có giá trị nguyên dương.
- `unit_price_cents` là number nguyên không âm.
- Tất cả item đều hợp lệ, **không chỉ một item**.

### 13.1. Tách phần tử với jsonb_array_elements

```sql
SELECT
    e.ordinality,
    e.item ->> 'sku' AS sku,
    e.item -> 'qty' AS qty_json
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.doc -> 'items')
    WITH ORDINALITY AS e(item, ordinality)
WHERE o.tenant_id = 7
  AND o.doc ->> 'external_id' = 'ORD-2026-0001'
ORDER BY e.ordinality;
```

`WITH ORDINALITY` bổ sung thứ tự phần tử từ 1 trong kết quả. Không dùng thứ tự hàng không có ORDER BY như một bảo đảm lâu dài cho API.

### 13.2. Tìm item không hợp lệ để điều tra

Truy vấn dưới đây **giả sử items đã được xác nhận là array** bởi schema. Nó tìm những item sai kiểu cơ bản:

```sql
SELECT
    o.order_pk,
    e.ordinality,
    e.item
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.doc -> 'items')
    WITH ORDINALITY AS e(item, ordinality)
WHERE
    jsonb_typeof(e.item) IS DISTINCT FROM 'object'
    OR jsonb_typeof(e.item -> 'sku') IS DISTINCT FROM 'string'
    OR nullif(btrim(e.item ->> 'sku'), '') IS NULL
    OR jsonb_typeof(e.item -> 'qty') IS DISTINCT FROM 'number'
    OR jsonb_typeof(e.item -> 'unit_price_cents')
       IS DISTINCT FROM 'number';
```

`IS DISTINCT FROM` là so sánh có kết quả boolean rõ cho trường hợp SQL NULL: nếu `sku` thiếu thì kiểu trả SQL NULL, và `NULL IS DISTINCT FROM 'string'` là TRUE.

Đây mới là kiểm tra kiểu và chuỗi; chưa kiểm tra `qty` nguyên dương và giá không âm. Ta sẽ đóng gói logic đầy đủ hơn.

## 14. Viết hàm SQL validation thuần cho mảng lồng nhau

Một `CHECK` thông thường không chứa trực tiếp subquery tùy ý đọc từng phần tử. Ta có thể xây dựng một **hàm SQL thuần** kiểm tra JSON array, rồi gọi hàm trong CHECK.

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION json313.valid_items(p_items jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN jsonb_typeof(p_items) <> 'array'
        THEN FALSE

        WHEN jsonb_array_length(p_items) = 0
        THEN FALSE

        ELSE NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(p_items) AS e(item)
            WHERE
                jsonb_typeof(e.item) IS DISTINCT FROM 'object'

                OR jsonb_typeof(e.item -> 'sku')
                    IS DISTINCT FROM 'string'

                OR nullif(btrim(e.item ->> 'sku'), '')
                    IS NULL

                OR jsonb_typeof(e.item -> 'qty')
                    IS DISTINCT FROM 'number'

                OR NOT (
                    CASE
                        WHEN jsonb_typeof(e.item -> 'qty') = 'number'
                        THEN
                            (e.item ->> 'qty')::numeric > 0
                            AND
                            (e.item ->> 'qty')::numeric =
                                trunc((e.item ->> 'qty')::numeric)
                        ELSE FALSE
                    END
                )

                OR jsonb_typeof(e.item -> 'unit_price_cents')
                    IS DISTINCT FROM 'number'

                OR NOT (
                    CASE
                        WHEN jsonb_typeof(
                            e.item -> 'unit_price_cents'
                        ) = 'number'
                        THEN
                            (e.item ->> 'unit_price_cents')::numeric >= 0
                            AND
                            (e.item ->> 'unit_price_cents')::numeric =
                                trunc(
                                  (e.item ->> 'unit_price_cents')::numeric
                                )
                        ELSE FALSE
                    END
                )
        )
    END;
$$;
```

### 14.1. Vì sao NOT EXISTS phù hợp cho “mọi item hợp lệ”?

Quy tắc:

```text
Mọi phần tử hợp lệ
    <=>
Không tồn tại bất kỳ phần tử không hợp lệ nào
```

Hàm dùng `NOT EXISTS (SELECT ... WHERE điều_kiện_sai)`.

Nếu chỉ dùng:

```sql
EXISTS (
    SELECT 1 FROM jsonb_array_elements(items) ...
    WHERE item hợp lệ
)
```

thì một array gồm một item đúng và mười item sai vẫn có thể được chấp nhận; đó là kiểm tra **ít nhất một item hợp lệ**, không phải **tất cả item hợp lệ**.

### 14.2. Vì sao IMMUTABLE và STRICT?

- `IMMUTABLE`: kết quả phụ thuộc duy nhất vào tham số JSON đầu vào, không đọc bảng khác hoặc đồng hồ hệ thống.
- `STRICT`: với đối số SQL NULL, hàm trả SQL NULL mà không chạy thân hàm.

Đây là các thuộc tính phù hợp với hàm validation thuần như ví dụ. **Chỉ đánh dấu IMMUTABLE nếu hàm thật sự bất biến**. Không khai báo sai một hàm đọc bảng cấu hình hoặc `now()` là IMMUTABLE để ép PostgreSQL cho phép đưa vào CHECK/index.

### 14.3. Đưa hàm vào CHECK

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_items_elements_valid
CHECK (
    COALESCE(
        json313.valid_items(doc -> 'items'),
        FALSE
    )
);
```

Kết hợp với constraint kiểu array trước đó, các trường hợp `items` thiếu, JSON null, object, array rỗng hoặc item sai định dạng bị từ chối.

### 14.4. Cẩn thận khi thay đổi định nghĩa hàm

PostgreSQL giả định những hàm dùng trong CHECK có hành vi bất biến cho cùng dữ liệu. Nếu bạn thay đổi logic của một hàm validation đã dùng trong CHECK, **các hàng cũ không tự động bị kiểm tra lại**.

Một migration sửa quy tắc validation cần:

- Xác định hàng cũ nào bị ảnh hưởng.
- Quét/đối soát dữ liệu theo logic mới.
- Bổ sung hoặc validate constraint phù hợp.
- Xử lý backup/restore và phụ thuộc theo quy trình.
- Không chỉ dùng `CREATE OR REPLACE FUNCTION` rồi tuyên bố mọi dữ liệu lịch sử đều hợp lệ.

## 15. Tính nhất quán giữa amount và items

Giả sử `amount_cents` phải bằng tổng:

```text
SUM(item.qty * item.unit_price_cents)
```

Đây là một **bất biến xuyên các thuộc tính trong cùng JSON document**, không chỉ là một phép kiểm tra kiểu.

Ví dụ:

```json
{
  "amount_cents": 250000,
  "items": [
    {"sku":"SKU-A","qty":2,"unit_price_cents":100000},
    {"sku":"SKU-B","qty":1,"unit_price_cents":50000}
  ]
}
```

Tổng = 250000, hợp lệ nếu business không áp dụng thuế, phí hoặc giảm giá ngoài các dòng item.

### 15.1. Tính tổng bằng SQL để quan sát

```sql
SELECT
    o.order_pk,
    o.doc ->> 'external_id' AS external_id,
    SUM(
        (e.item ->> 'qty')::numeric
        *
        (e.item ->> 'unit_price_cents')::numeric
    ) AS calculated_items_total
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.doc -> 'items') AS e(item)
WHERE json313.valid_items(o.doc -> 'items') IS TRUE
GROUP BY o.order_pk, o.doc ->> 'external_id'
ORDER BY o.order_pk;
```

Truy vấn minh họa trên giả định các item đã hợp lệ trước khi cast. Với dữ liệu nguồn chưa được kiểm tra, cần tránh cast bừa các chuỗi không hợp lệ.

### 15.2. Có nên CHECK tổng tiền bằng tổng item?

Chỉ khi quy tắc nghiệp vụ **thực sự là như vậy**. Nếu còn shipping, voucher, tax, rounding hoặc partial order, một CHECK cố định đơn giản sẽ từ chối các đơn hợp lệ.

Khi cần, viết hàm validator thuần cho tổng tiền trên JSON đã xác thực; hoặc chuyển các dòng hàng sang bảng quan hệ riêng và thiết kế invariant phù hợp.

Không tự nâng một quy ước tính tiền ví dụ thành quy tắc kế toán của mọi hệ thống.

## 16. JSONPath để kiểm tra đường dẫn và điều kiện

PostgreSQL hỗ trợ SQL/JSON path qua kiểu `jsonpath` và những hàm/toán tử như:

- `jsonb_path_exists`.
- `jsonb_path_query`.
- `jsonb_path_query_first`.
- `@?` và `@@` với ngữ nghĩa phù hợp.

Ví dụ tìm đơn có ít nhất một item có SKU-A:

```sql
SELECT order_pk, doc ->> 'external_id' AS external_id
FROM json313.orders
WHERE doc @? '$.items[*] ? (@.sku == "SKU-A")';
```

Ý nghĩa: có **ít nhất một đường dẫn** trong JSON thỏa filter với SKU-A.

### 16.1. Phân biệt existence với kiểm tra tất cả

Câu:

```sql
doc @? '$.items[*] ? (@.qty >= 1)'
```

không chứng minh **mọi item** có qty >= 1. Nó chỉ cần tìm **một item** thỏa điều kiện.

Nếu một array có item qty=2 và item qty=-10, biểu thức có thể TRUE dù dữ liệu tổng thể không hợp lệ.

Đối với quy tắc “tất cả phần tử đúng”, dùng kiểm tra phủ định sự tồn tại item sai hoặc một hàm validation được thiết kế đầy đủ như phần trước.

### 16.2. Cẩn thận chế độ lax và strict

SQL/JSON path có các quy tắc đánh giá, bao gồm hành vi lax/strict và xử lý mismatch cấu trúc. Đừng mặc định một JSONPath tự tương đương kiểm tra kiểu chặt như JSON Schema.

Cần xác định rõ:

- Đường dẫn thiếu trả kết quả thế nào.
- Có tự unwrap array trong một số trường hợp hay không.
- So sánh kiểu khác nhau được xử lý ra sao.
- Những lỗi nào bị suppress trong các toán tử/hàm phù hợp.

Với những trường định danh/tài chính bắt buộc, CHECK kiểu rõ ràng hoặc cột quan hệ thường dễ kiểm chứng hơn một JSONPath phức tạp viết ngắn.

## 17. Nested object: bảo vệ shipping.city

Trường `shipping` có thể là object lồng nhau:

```json
{
  "shipping": {
    "city": "Da Nang",
    "note": null
  }
}
```

Lấy dữ liệu:

```sql
SELECT
    doc #>  '{shipping,city}' AS city_json,
    doc #>> '{shipping,city}' AS city_text
FROM json313.orders;
```

- `#>` truy cập đường dẫn JSON, trả `jsonb`.
- `#>>` truy cập đường dẫn và chuyển kết quả sang text.
- Nếu một thành phần của đường dẫn không tồn tại, kết quả thường là SQL NULL.

### 17.1. Constraint cho nested field bắt buộc

Nếu nghiệp vụ quy định mọi đơn phải có `shipping.city` dạng string không rỗng:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_shipping_city_valid
CHECK (
    (
        jsonb_typeof(doc -> 'shipping') = 'object'
        AND jsonb_typeof(doc #> '{shipping,city}') = 'string'
        AND length(btrim(doc #>> '{shipping,city}')) > 0
    ) IS TRUE
);
```

Trong fixture, city=Da Nang nên hợp lệ.

### 17.2. Nếu shipping là optional?

Không thêm constraint bắt buộc nếu một số loại đơn là dịch vụ điện tử không có địa chỉ giao hàng. Thay vào đó, xác định predicate:

```text
Nếu cần giao hàng vật lý:
    shipping.city phải có.
Nếu giao nội dung số:
    shipping có thể vắng mặt.
```

Những quy tắc điều kiện này có thể được kiểm tra bằng CASE/validation function, nhưng phải xuất phát từ mô hình nghiệp vụ, không chỉ từ hình dạng JSON mẫu.

## 18. Khóa bắt buộc và khóa không được phép

Một hệ thống có thể chọn giữa hai chính sách.

**Chính sách mở rộng:**

```text
Các khóa quan trọng phải đúng,
nhưng cho phép metadata tùy ý.
```

**Chính sách đóng:**

```text
Chỉ các khóa được liệt kê mới được xuất hiện.
```

### 18.1. Vì sao không luôn cấm khóa ngoài danh sách?

JSONB thường được dùng vì cần mở rộng metadata theo phiên bản, đối tác, nguồn dữ liệu hoặc cờ tính năng. Cấm mọi khóa mới làm schema kém linh hoạt và có thể gây lỗi khi ứng dụng triển khai lệch phiên bản.

### 18.2. Khi cấm khóa lạ

Cần liệt kê top-level keys bằng `jsonb_object_keys` và kiểm tra không tồn tại khóa ngoài danh sách được phép.

Khuôn mẫu truy vấn điều tra:

```sql
SELECT
    o.order_pk,
    k.key
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_object_keys(o.doc) AS k(key)
WHERE k.key NOT IN (
    'external_id',
    'status',
    'amount_cents',
    'currency',
    'items',
    'shipping',
    'metadata'
);
```

Nếu muốn cưỡng chế bằng CHECK, có thể đóng gói validation trong hàm SQL thuần, IMMUTABLE, hoặc sử dụng cơ chế xác thực JSON Schema phù hợp.

**Không** chỉ viết CHECK đơn giản trên một danh sách khóa rồi quên rằng JSON có thể thêm nested keys hoặc các phiên bản khác.

## 19. Duy nhất theo tenant: UNIQUE trên biểu thức JSON

Mỗi tenant cần `external_id` duy nhất, nhưng hai tenant khác nhau có thể cùng dùng một mã.

Quy tắc:

```text
UNIQUE (tenant_id, external_id)
```

Trong bảng lab, external_id nằm trong JSON, nên có thể tạo **unique expression index**:

```sql
CREATE UNIQUE INDEX uq_json313_orders_tenant_external
ON json313.orders(
    tenant_id,
    (doc ->> 'external_id')
);
```

Chỉ mục này dùng giá trị text trích xuất từ JSON để kiểm tra trùng.

### 19.1. Vì sao vẫn cần CHECK bắt buộc external_id?

Với unique index thông thường, các giá trị SQL NULL có semantics riêng: nhiều hàng có giá trị NULL có thể được chấp nhận nếu không dùng quy tắc khác.

Nếu `external_id` thiếu hoặc JSON null, biểu thức `doc->>'external_id'` là SQL NULL. Không được dùng UNIQUE index như lý do bỏ constraint trường bắt buộc.

Kết hợp đúng:

- CHECK external_id tồn tại, đúng kiểu, không rỗng.
- UNIQUE(tenant_id, external_id expression).

### 19.2. Test trùng mã trong cùng tenant

Sau khi đã tạo chỉ mục và đơn `ORD-2026-0001` của tenant 7 tồn tại:

```sql
-- Chạy riêng để quan sát unique_violation mong đợi:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{
      "external_id":"ORD-2026-0001",
      "status":"NEW",
      "amount_cents":0,
      "currency":"VND",
      "items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],
      "shipping":{"city":"Hue"}
    }'::jsonb
);
```

Lệnh dự kiến bị từ chối vì cặp tenant 7 + external_id đã tồn tại.

### 19.3. Hai tenant khác nhau

Một hàng với tenant_id=8 và cùng external_id có thể được chấp nhận vì unique key khác cặp.

Điều này đúng nếu yêu cầu là **duy nhất trong tenant**. Nếu cần external_id duy nhất toàn hệ thống, index phải được thiết kế theo phạm vi khác.

### 19.4. Vì sao không chỉ SELECT NOT EXISTS trước INSERT?

Hai transaction có thể đồng thời đọc “chưa có external_id” rồi cùng INSERT. Unique index là ràng buộc database hỗ trợ kiểm tra tranh chấp đồng thời; pre-check ở ứng dụng **không thay thế** được.

## 20. Dùng generated column cho thuộc tính JSON quan trọng

Một cách thiết kế khác là đưa giá trị trích xuất thành cột dễ truy vấn.

Ví dụ dùng generated column:

```sql
ALTER TABLE json313.orders
ADD COLUMN external_id text
GENERATED ALWAYS AS (doc ->> 'external_id') STORED;
```

Cột được tính từ `doc`; ứng dụng không ghi giá trị external_id trực tiếp theo cách một cột thường được ghi.

Có thể lập chỉ mục:

```sql
CREATE INDEX idx_json313_orders_external_id
ON json313.orders(external_id);
```

### 20.1. Expression index hay generated column?

| Tiêu chí | Expression index | Generated column |
|---|---|---|
| Truy vấn theo thuộc tính | Có thể dùng expression khớp | Dùng cột tên rõ |
| Tên cột trong SQL/ORM | Thường lặp biểu thức | Có tên cột riêng |
| Bảo đảm dữ liệu đầu vào | Vẫn cần CHECK | Vẫn cần CHECK nếu kiểu/giá trị chưa được bảo vệ |
| Dữ liệu lưu trữ | Giá trị biểu thức trong index | Generated value lưu cùng hàng, và index nếu tạo |
| Quy tắc tính | Theo expression | Theo biểu thức generated tuân thủ giới hạn PostgreSQL |
| Schema migration | Tạo/sửa index | Thêm cột và tác động lưu trữ/migration |

Không nhất thiết tạo **cả expression unique index và generated unique index** cho cùng khóa; ví dụ hai hướng để lựa chọn theo nhu cầu, tránh index trùng.

### 20.2. Có nên lưu external_id thành cột thường?

Nếu external_id là **khóa nghiệp vụ quan trọng**, cân nhắc đặt nó ở cột quan hệ có:

```sql
external_id text NOT NULL
```

và một `UNIQUE(tenant_id, external_id)` thông thường. Dữ liệu JSON vẫn chứa metadata linh hoạt.

Ưu điểm:

- FOREIGN KEY và quan hệ tham chiếu rõ ràng.
- Truy vấn, index và thống kê dễ thiết kế.
- Ràng buộc thay đổi giá trị dễ quản lý hơn.
- ORM/API có hợp đồng kiểu rõ ràng.

Đừng nhồi mọi khóa quan trọng vào JSONB chỉ để giảm số cột bảng.

## 21. Bảo vệ trường bất biến: CHECK không so OLD với NEW

Một CHECK chỉ nhìn **trạng thái hàng mới** và xác nhận giá trị hợp lệ.

Ví dụ:

```sql
CHECK (
    (doc ->> 'external_id') ~ '^ORD-[A-Za-z0-9-]+$'
)
```

không chặn:

```text
Trước: external_id = ORD-1001
Sau:   external_id = ORD-9999
```

vì cả hai giá trị có thể cùng hợp lệ về định dạng.

Nếu yêu cầu **mã đơn không được đổi sau khi tạo**, phải kiểm tra **OLD vs NEW** hoặc thiết kế quyền ghi/API sao cho mã không thể bị sửa.

### 21.1. Trigger BEFORE UPDATE bảo vệ identity

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION json313.guard_order_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN

        IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
            RAISE EXCEPTION
                'tenant_id cannot be changed'
                USING ERRCODE = '23514';
        END IF;

        IF (NEW.doc -> 'external_id')
            IS DISTINCT FROM (OLD.doc -> 'external_id') THEN
            RAISE EXCEPTION
                'external_id cannot be changed'
                USING ERRCODE = '23514';
        END IF;

        IF (OLD.doc ->> 'status') = 'PAID'
           AND (NEW.doc ->> 'status') = 'NEW' THEN
            RAISE EXCEPTION
                'PAID order cannot return to NEW'
                USING ERRCODE = '23514';
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_json313_guard_order_fields
BEFORE UPDATE ON json313.orders
FOR EACH ROW
EXECUTE FUNCTION json313.guard_order_fields();
```

### 21.2. Trigger có phạm vi gì?

Trigger trên bảng này xử lý các cập nhật hàng của `json313.orders` theo quy tắc kích hoạt.

Nó không tự:

- Xác thực người gọi có quyền thuộc tenant.
- Bảo đảm toàn bộ luồng trạng thái nghiệp vụ khi chỉ mới chặn PAID→NEW.
- Chặn DELETE nếu không có rule/trigger/policy riêng.
- Giải quyết mọi side effect ngoài database.
- Bảo đảm dữ liệu trong hệ thống ngoài PostgreSQL đồng bộ.

Muốn bảo vệ trạng thái, cần định nghĩa **sơ đồ chuyển trạng thái đầy đủ** và kiểm tra mọi cạnh được phép.

### 21.3. Vì sao IS DISTINCT FROM phù hợp?

SQL có `NULL`. So sánh `NEW.doc->'external_id' <> OLD.doc->'external_id'` có thể trả UNKNOWN nếu một bên thiếu.

`IS DISTINCT FROM` luôn phân biệt rõ các trường hợp:

- Cùng giá trị → FALSE.
- Giá trị khác → TRUE.
- Một bên SQL NULL, bên còn lại không → TRUE.
- Cả hai SQL NULL → FALSE.

Các constraint khác vẫn phải bảo đảm external_id bắt buộc; trigger chỉ so sự thay đổi.

## 22. Trạng thái nghiệp vụ và state machine

Ràng buộc:

```text
status thuộc {NEW, PAID, CANCELLED}
```

chỉ là **kiểm tra giá trị hiện tại**.

Quy tắc chuyển trạng thái có thể là:

```text
NEW ------> PAID
  \          |
   \         +------> REFUNDED
    \
     +-----> CANCELLED
```

Không cho:

```text
PAID -> NEW
CANCELLED -> PAID
REFUNDED -> NEW
```

### 22.1. Giá trị hợp lệ không có nghĩa chuyển đổi hợp lệ

Một UPDATE đổi `NEW` thành `PAID` và một UPDATE đổi `PAID` thành `NEW` đều đặt giá trị trong tập enum. CHECK enum **không biết lịch sử**.

Nếu state machine cần được bảo vệ tại database:

- Dùng trigger so OLD/NEW.
- Hoặc mô hình state transition ở service được cưỡng chế qua một API ghi duy nhất và quyền hạn thích hợp.
- Với trạng thái phức tạp, có thể tách trạng thái thành cột chuẩn, bảng chuyển trạng thái, lịch sử audit, outbox và workflow.

### 22.2. Không dùng một rule quá hẹp làm state machine hoàn chỉnh

Trigger ở phần trước chỉ minh họa chặn **PAID → NEW**, chưa chặn mọi chuyển đổi sai. Đừng mang nó vào production và tuyên bố đã bảo vệ toàn bộ quy trình thanh toán.

### 22.3. Audit quan trọng

Khi status thay đổi, có thể cần ghi:

```text
order_id
old_status
new_status
actor
changed_at
request_id
```

Một thiết kế có thể dùng bảng sự kiện/trạng thái audit và transactional outbox, để không mất dấu thay đổi khi transaction commit. Hạn chế lưu thông tin nhạy cảm không cần thiết vào log.

## 23. jsonb_set: cập nhật một đường dẫn trong JSONB

PostgreSQL hỗ trợ `jsonb_set` để xây dựng tài liệu JSONB mới với một đường dẫn được thay đổi.

Cú pháp khái quát:

```sql
jsonb_set(target_jsonb, path_text_array, new_jsonb_value, create_if_missing)
```

Ví dụ đổi trạng thái sang PAID:

```sql
UPDATE json313.orders
SET
    doc = jsonb_set(
        doc,
        '{status}',
        '"PAID"'::jsonb,
        false
    ),
    version = version + 1
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001'
  AND doc ->> 'status' = 'NEW'
RETURNING
    order_pk,
    doc ->> 'status' AS new_status,
    version;
```

### 23.1. Vì sao điều kiện status='NEW' nằm trong WHERE?

Đây là một dạng **conditional state transition**:

```text
Chỉ cập nhật nếu trạng thái hiện tại là NEW.
```

Hai request cập nhật cùng hàng có thể phải đợi nhau do row lock. Ở `READ COMMITTED`, PostgreSQL có thể đánh giá lại WHERE trên phiên bản hàng hiện hành sau khi transaction cạnh tranh commit. Request sau có thể cập nhật 0 hàng nếu trạng thái không còn NEW.

Ứng dụng phải kiểm tra **số hàng trả bởi RETURNING**:

- 1 hàng: chuyển trạng thái đã được thực hiện trong transaction thành công.
- 0 hàng: không tìm thấy hàng, sai tenant hoặc trạng thái hiện tại không hợp lệ; cần phản hồi đúng nghiệp vụ.

### 23.2. jsonb_set không sửa tại chỗ từng byte trong cột

Một UPDATE đặt `doc = jsonb_set(...)` tạo ra một **giá trị JSONB mới** ở mức SQL/MVCC; không có lời hứa chỉ ghi vài byte bên trong tài liệu lớn mà không tốn chi phí.

Với document lớn và cập nhật thường xuyên, tách những thuộc tính nóng như status, counters, timestamps ra cột riêng có thể tiết kiệm công việc ghi/WAL/index.

### 23.3. Cẩn trọng đường dẫn thiếu

`create_if_missing = false` giúp tránh tự tạo khóa cuối nếu đường dẫn cuối không tồn tại. Tuy nhiên xử lý những bước trung gian không tồn tại, kiểu object/array và chỉ số array có quy tắc riêng.

Vì vậy không dùng `jsonb_set` như một hệ thống validation schema. Constraint vẫn kiểm tra dữ liệu sau UPDATE.

## 24. Bảo vệ trước lost update khi ứng dụng gửi lại cả document

Một lỗi thường gặp:

1. A đọc `doc` phiên bản v1.
2. B đọc cùng `doc` v1.
3. A thay `shipping.city` và gửi lại **toàn bộ doc**.
4. B thay `metadata.source` trên bản v1 và gửi lại **toàn bộ doc**.
5. B ghi sau, có thể làm mất cập nhật shipping của A.

Nếu ứng dụng thực hiện:

```sql
UPDATE json313.orders
SET doc = $1::jsonb
WHERE order_pk = $2;
```

với tài liệu được xây từ một snapshot cũ, transaction sau có thể ghi đè các thay đổi trước, dù các request định sửa hai trường khác nhau.

### 24.1. Cập nhật đường dẫn trong database

Với những thay đổi cục bộ, dùng:

```sql
UPDATE json313.orders
SET doc = jsonb_set(
    doc,
    '{metadata,source}',
    '"mobile"'::jsonb,
    true
)
WHERE order_pk = 1;
```

Câu UPDATE sử dụng giá trị `doc` trong row hiện hành được xử lý bởi PostgreSQL, thay vì một bản sao JSON cũ được gửi lại từ client.

Nhưng vẫn phải kiểm tra:

- Có quyền sửa đường dẫn này không?
- Bản ghi thuộc tenant nào?
- Trường đó có được phép thay đổi trong trạng thái hiện tại không?
- Có yêu cầu version hoặc idempotency không?
- Có trigger/constraint kiểm tra dữ liệu sau cập nhật không?

### 24.2. Optimistic locking bằng version

Với mỗi request, client gửi version đã đọc.

```sql
UPDATE json313.orders
SET
    doc = jsonb_set(
        doc,
        '{metadata,source}',
        '"mobile"'::jsonb,
        true
    ),
    version = version + 1
WHERE order_pk = 1
  AND tenant_id = 7
  AND version = 0
RETURNING order_pk, version;
```

Nếu một transaction khác đã tăng version, lần UPDATE này sẽ không còn khớp version=0; ứng dụng nhận 0 hàng và cần đọc lại/retry theo nghiệp vụ.

### 24.3. Retry toàn bộ quyết định khi cần

Nếu một giao dịch SERIALIZABLE bị hủy với SQLSTATE `40001` hoặc deadlock với `40P01`, ứng dụng phải rollback và retry **toàn transaction** khi nghiệp vụ cho phép. Không lặp lại quyết định cũ từ document đã lỗi thời mà không đọc lại.

## 25. jsonb_set_lax và xử lý SQL NULL

Một điều tinh tế: giá trị mới đưa vào JSON có thể là **SQL NULL** hoặc JSONB `null`.

```sql
-- JSON null:
SELECT jsonb_set(
    '{"x":1}'::jsonb,
    '{x}',
    'null'::jsonb
);
```

Đây là thao tác đặt thuộc tính x thành **JSON null**, không phải xóa khóa.

Trong các phiên bản PostgreSQL hỗ trợ, `jsonb_set_lax` cung cấp lựa chọn hành vi khi đối số `new_value` là **SQL NULL**, chẳng hạn chuyển thành JSON null, xóa khóa, giữ nguyên hoặc báo lỗi theo tùy chọn.

### 25.1. Đừng nhầm đặt null với xóa khóa

```text
{"x":null}
```

và:

```text
{}
```

khác nhau khi kiểm tra `? 'x'`, mặc dù `->> 'x'` đều có thể trả SQL NULL.

Nếu x là trường bắt buộc, cả hai có thể phải bị từ chối: một trường hợp do sai kiểu/JSON null, một trường hợp do thiếu khóa.

### 25.2. Không dùng NULL để “bỏ qua validation”

Một ứng dụng gửi JSON null cho amount, rồi hy vọng CHECK bị UNKNOWN và tự được chấp nhận, là dấu hiệu constraint chưa được thiết kế đúng. Các quy tắc ở phần 4 và 10 nhằm chặn tình huống này.

## 26. Xóa khóa JSONB và bảo vệ trường bắt buộc

Toán tử `-` có thể xóa một khóa ở cấp object:

```sql
SELECT
    '{"external_id":"ORD-1","note":"hello"}'::jsonb
    - 'note';
```

Kết quả mong đợi chỉ còn external_id.

Nếu xóa `external_id`:

```sql
SELECT
    '{"external_id":"ORD-1","note":"hello"}'::jsonb
    - 'external_id';
```

thì document không còn khóa định danh.

### 26.1. Constraint phải chặn đường ghi này

Nếu `external_id` là bắt buộc, CHECK `order_doc_external_id_valid` và `order_doc_required_keys` khiến một UPDATE bỏ khóa quan trọng bị từ chối.

Trigger so OLD/NEW cũng có thể chặn khi identity thay đổi. Đây là ví dụ **phòng thủ nhiều lớp**:

- CHECK chặn dữ liệu cuối không hợp lệ.
- Trigger chặn thay đổi định danh.
- Quyền ghi/API giới hạn ai được thao tác.

### 26.2. Tại sao không chỉ tin vào frontend?

Frontend có thể bị bỏ qua bởi batch job, script DBA, job migration, API cũ hoặc đường ghi trực tiếp. Nếu một trường là invariant quan trọng, database constraint giúp bảo vệ thêm những đường ghi ngoài service thông thường.

Tuy nhiên người có quyền thay đổi schema, disable trigger hoặc quản trị superuser vẫn có thể làm thay đổi cấu hình bảo vệ. Không coi constraint là cơ chế ngăn mọi hành vi của tài khoản có quyền quản trị cao nhất.

## 27. Quyền theo cột không đồng nghĩa quyền theo khóa JSON

PostgreSQL hỗ trợ quyền ở cấp bảng/cột và Row Level Security ở cấp hàng. Nhưng một cột:

```text
doc jsonb
```

vẫn là **một cột duy nhất** dù chứa hàng chục thuộc tính.

### 27.1. Không thể đơn giản GRANT UPDATE một đường dẫn JSON

Chính sách:

```text
Role A được cập nhật doc.metadata
nhưng không được cập nhật doc.external_id
```

không thể được biểu diễn chỉ bằng quyền UPDATE ở mức **một cột doc** thông thường. Quyền cột không hiểu `metadata` và `external_id` là hai cột độc lập.

### 27.2. Các hướng kiểm soát

- Tách trường quan trọng thành cột riêng.
- Chỉ cho ứng dụng gọi hàm ghi có kiểm tra đường dẫn được phép.
- Dùng trigger so sánh OLD/NEW để chặn thay đổi.
- Thiết lập role least privilege và không cấp UPDATE trực tiếp trên cột JSONB cho role không tin cậy.
- RLS hạn chế phạm vi **hàng** mà role được đọc/ghi.
- Ghi audit các thay đổi nhạy cảm.

### 27.3. Ví dụ quyền cột là khuôn mẫu, không chạy nguyên xi

```sql
-- Giả định app_role đã được DBA tạo và cấp quyền thích hợp:
REVOKE UPDATE (doc) ON json313.orders FROM app_role;
```

Lưu ý: nếu role vẫn có quyền `UPDATE` ở **cấp bảng** hoặc qua role khác, một REVOKE ở cấp cột không đủ để bảo đảm không thể sửa doc. Phải đánh giá toàn bộ quyền thừa hưởng và vai trò.

Đừng tự tạo tài khoản quyền cao hoặc thay quyền production chỉ để chạy một ví dụ học tập.

## 28. RLS bảo vệ tenant, không thay kiểm tra JSON

Trong hệ thống nhiều tenant, `tenant_id` nên được kiểm soát đáng tin cậy, thường là một cột quan hệ ngoài JSON.

### 28.1. Vì sao tenant_id không nên chỉ ở doc?

Nếu chỉ có:

```json
{"tenant_id":7,"external_id":"ORD-1"}
```

thì mọi kiểm tra phân quyền, index, constraint và join liên quan tenant đều phải trích xuất JSON. Dễ gặp sai kiểu, thiếu khóa hoặc nhầm nơi lấy tenant_id.

Một cột:

```sql
tenant_id integer NOT NULL
```

giúp viết unique composite, foreign key, filter và RLS rõ hơn.

### 28.2. RLS bảo vệ hàng

RLS có thể hạn chế những hàng mà role được SELECT/UPDATE/DELETE hoặc INSERT theo các biểu thức policy phù hợp.

Nhưng RLS **không** kiểm tra:

- external_id có string không rỗng không.
- amount_cents có âm không.
- items có object hợp lệ không.
- status có chuyển từ PAID về NEW trái phép không.

RLS, CHECK, UNIQUE và trigger phục vụ các chức năng khác nhau, cần phối hợp.

### 28.3. Không lấy tenant_id từ tham số không được tin cậy

Một query:

```sql
UPDATE json313.orders
SET doc = ...
WHERE tenant_id = 7;
```

chỉ an toàn trong ngữ cảnh tenant 7 đã được xác thực và người gọi có quyền tương ứng. Client có thể tự gửi số 7 hoặc 8; ứng dụng phải liên kết tenant với danh tính/ủy quyền, không chỉ tin payload JSON.

## 29. JSON Schema: PostgreSQL core và extension

JSON Schema là một cách mô tả hợp đồng JSON theo các khái niệm như:

- Kiểu object/array/string/number/integer.
- Trường bắt buộc.
- Enum.
- Regex pattern.
- Giới hạn min/max.
- Cấu trúc object lồng nhau.
- Quy tắc item trong array.
- Một số điều kiện kết hợp.

Ví dụ một phần JSON Schema minh họa:

```json
{
  "type": "object",
  "required": [
    "external_id",
    "status",
    "amount_cents",
    "currency",
    "items"
  ],
  "properties": {
    "external_id": {
      "type": "string",
      "minLength": 1
    },
    "status": {
      "enum": ["NEW", "PAID", "CANCELLED"]
    },
    "amount_cents": {
      "type": "integer",
      "minimum": 0
    },
    "items": {
      "type": "array",
      "minItems": 1
    }
  }
}
```

**Đây là phần schema minh họa**, chưa mô tả toàn bộ item, uniqueness, trạng thái chuyển đổi và business rules.

### 29.1. PostgreSQL có built-in JSON Schema validator không?

Kiểu `jsonb` và các SQL/JSON functions **không đồng nghĩa PostgreSQL core cung cấp sẵn một bộ kiểm định toàn bộ tiêu chuẩn JSON Schema** cho mỗi cột.

Có các extension hoặc thư viện ngoài, ví dụ những extension theo hướng `pg_jsonschema`, nhưng:

- Không mặc định extension có mặt.
- Cần kiểm tra quyền cài đặt.
- Cần xác nhận phiên bản và JSON Schema dialect được hỗ trợ.
- Cần kiểm tra hiệu năng của validation.
- Cần quản lý migration khi schema thay đổi.

Không sao chép một lệnh gọi hàm của extension bất kỳ vào production khi chưa xác minh API trên hệ thống thật.

### 29.2. Khi nào CHECK thủ công đủ?

Nếu chỉ có vài trường ổn định, CHECK rõ ràng có thể dễ vận hành và truy lỗi.

Nếu JSON có cấu trúc lồng nhau lớn, hàng chục quy tắc tùy chọn và nhiều phiên bản schema, một JSON Schema validator được tích hợp đúng cách có thể tiện hơn.

Dù chọn cách nào, **business invariants xuyên hàng** như external_id unique vẫn cần UNIQUE/transaction phù hợp; JSON Schema thường chỉ xác thực một tài liệu đơn lẻ.

## 30. Version hóa cấu trúc JSON

Một document có thể có `schema_version`:

```json
{
  "schema_version": 2,
  "external_id": "ORD-2026-0001",
  "status": "NEW"
}
```

Nó giúp phân biệt hợp đồng dữ liệu giữa các phiên bản.

### 30.1. Hai chiến lược phổ biến

**Nâng cấp toàn bộ tài liệu cũ:**

- Migration sửa những document phiên bản trước.
- Sau đó đặt constraint theo schema mới.
- Ít nhánh xử lý runtime hơn nếu đã nâng cấp xong.

**Hỗ trợ song song nhiều phiên bản:**

- Validator chọn rule tương ứng schema_version.
- Ứng dụng đọc dữ liệu cũ và mới.
- Migration diễn ra dần.
- Cần test đủ mọi phiên bản.

### 30.2. Đừng chỉ kiểm tra phiên bản có mặt

Nếu `schema_version` là JSON string `"2"` ở một tài liệu và JSON number `2` ở tài liệu khác, phải xác định có chấp nhận cả hai không.

Ví dụ nếu yêu cầu number nguyên:

```sql
CHECK (
    CASE
      WHEN jsonb_typeof(doc -> 'schema_version') = 'number'
      THEN (doc ->> 'schema_version')::numeric
           = trunc((doc ->> 'schema_version')::numeric)
      ELSE FALSE
    END
)
```

Đây mới là kiểm tra kiểu/nguyên; chưa giới hạn phiên bản nằm trong tập 1,2,... hay nhánh validator tương ứng.

### 30.3. Không vô tình làm mất thông tin khi đổi schema

Nếu cần audit, trước khi chuyển đổi JSONB từ v1 sang v2 hãy xác định:

- Trường nào được đổi tên.
- Trường nào bị xóa.
- Giá trị mặc định nào được gán.
- NULL và khóa thiếu được xử lý ra sao.
- Có cần lưu bản gốc hay sự kiện migration không.

## 31. Thêm constraint vào bảng đang có dữ liệu

Với bảng đã có nhiều hàng, thêm CHECK có thể phải kiểm tra dữ liệu cũ và phát hiện lỗi.

Một kỹ thuật hữu ích là **thêm constraint NOT VALID**, rồi kiểm tra lịch sử và validate sau.

Ví dụ một ràng buộc mới:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_metadata_object
CHECK (
    CASE
        WHEN doc ? 'metadata'
        THEN jsonb_typeof(doc -> 'metadata') = 'object'
        ELSE TRUE
    END
)
NOT VALID;
```

### 31.1. NOT VALID nghĩa là gì?

Với CHECK/FK được hỗ trợ:

- PostgreSQL **không yêu cầu kiểm tra toàn bộ hàng cũ ngay tại bước ADD**.
- Các INSERT/UPDATE mới vẫn phải thỏa constraint theo ngữ nghĩa PostgreSQL.
- Constraint chưa được đánh dấu đã kiểm chứng toàn bộ dữ liệu lịch sử.

Đây **không** phải cách tắt validation cho dữ liệu mới.

### 31.2. Tìm dữ liệu cũ vi phạm

```sql
SELECT order_pk, tenant_id, doc -> 'metadata' AS metadata_json
FROM json313.orders
WHERE doc ? 'metadata'
  AND jsonb_typeof(doc -> 'metadata') IS DISTINCT FROM 'object';
```

Sửa những hàng thực sự sai theo nghiệp vụ. Không tự chuyển metadata sai kiểu thành object rỗng nếu làm mất thông tin mà các consumer cần.

### 31.3. VALIDATE CONSTRAINT

Khi đã xử lý dữ liệu lịch sử:

```sql
ALTER TABLE json313.orders
VALIDATE CONSTRAINT order_doc_metadata_object;
```

PostgreSQL kiểm tra dữ liệu để đánh dấu constraint valid nếu thành công.

### 31.4. Có phải mọi constraint đều dùng NOT VALID như nhau?

Không. UNIQUE, PRIMARY KEY, NOT NULL và các loại constraint/DDL khác có cơ chế triển khai riêng. Không suy luận cứ thêm `NOT VALID` vào bất kỳ constraint nào cũng hợp lệ.

Với bảng rất lớn, lập kế hoạch lock/scan/transaction theo phiên bản PostgreSQL và ảnh hưởng production.

## 32. Kiểm chứng constraint và định nghĩa index

Xem các CHECK/PK/FK đã khai báo:

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'json313.orders'::regclass
ORDER BY conname;
```

Một số giá trị `contype`:

- `c`: CHECK.
- `p`: PRIMARY KEY.
- `u`: UNIQUE constraint.
- `f`: FOREIGN KEY.

Expression unique index như `uq_json313_orders_tenant_external` **không nhất thiết hiển thị như một UNIQUE constraint hàng-cột thông thường trong pg_constraint**, vì nó là chỉ mục được tạo trực tiếp. Kiểm tra thêm:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'json313'
  AND tablename = 'orders'
ORDER BY indexname;
```

### 32.1. Xem trạng thái valid của index

```sql
SELECT
    c.relname AS index_name,
    i.indisunique,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c ON c.oid = i.indexrelid
WHERE i.indrelid = 'json313.orders'::regclass
ORDER BY c.relname;
```

Không khẳng định một index đang bảo vệ dữ liệu khi nó còn invalid hoặc đang ở trạng thái migration chưa hoàn tất.

## 33. Tìm hàng có dữ liệu đáng nghi

Trong một bảng legacy chứa JSONB chưa ràng buộc chặt, có thể viết các truy vấn đối soát.

### 33.1. Trường thiếu hoặc sai kiểu

```sql
SELECT
    order_pk,
    tenant_id,
    doc
FROM json313.orders
WHERE
    jsonb_typeof(doc) IS DISTINCT FROM 'object'
    OR jsonb_typeof(doc -> 'external_id')
       IS DISTINCT FROM 'string'
    OR jsonb_typeof(doc -> 'status')
       IS DISTINCT FROM 'string'
    OR jsonb_typeof(doc -> 'amount_cents')
       IS DISTINCT FROM 'number';
```

Sau khi các constraint được thêm và valid, query lý tưởng không trả hàng. Trên dữ liệu cũ, nó giúp nhận diện bản ghi cần xử lý.

### 33.2. Trạng thái ngoài tập

```sql
SELECT order_pk, doc -> 'status' AS status_json
FROM json313.orders
WHERE (doc ->> 'status') NOT IN ('NEW','PAID','CANCELLED')
   OR (doc ->> 'status') IS NULL;
```

Lưu ý `NOT IN` không tự bắt SQL NULL, vì vậy phải thêm điều kiện `IS NULL` nếu dùng kiểu đối soát này.

### 33.3. Kiểm tra trùng external_id theo tenant

```sql
SELECT
    tenant_id,
    doc ->> 'external_id' AS external_id,
    COUNT(*) AS occurrences
FROM json313.orders
GROUP BY tenant_id, doc ->> 'external_id'
HAVING COUNT(*) > 1
ORDER BY occurrences DESC, tenant_id;
```

Một query kiểm tra như vậy chỉ giúp **phát hiện** trùng trong snapshot; để **ngăn** ghi trùng đồng thời cần UNIQUE index/constraint thích hợp.

### 33.4. Đối soát JSON null

```sql
SELECT order_pk
FROM json313.orders
WHERE doc ? 'external_id'
  AND doc -> 'external_id' = 'null'::jsonb;
```

Phép so sánh này tìm JSON null được lưu **bên trong** khóa external_id, không dùng `IS NULL` đối với text extracted.

## 34. Chỉ mục JSONB: GIN và B-tree expression

Validation và query performance là hai vấn đề khác nhau.

### 34.1. B-tree trên thuộc tính trích xuất

Tìm một external_id:

```sql
SELECT order_pk, tenant_id
FROM json313.orders
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

Unique expression index:

```sql
ON json313.orders(tenant_id, (doc ->> 'external_id'))
```

có thể phục vụ cả uniqueness và phép tìm equality theo hai thành phần.

### 34.2. GIN cho containment JSONB

Ví dụ truy vấn:

```sql
SELECT order_pk
FROM json313.orders
WHERE doc @> '{"status":"NEW"}'::jsonb;
```

Một index GIN có thể hữu ích:

```sql
CREATE INDEX idx_json313_orders_doc_gin
ON json313.orders
USING gin (doc);
```

Đây là GIN với operator class mặc định `jsonb_ops`, hỗ trợ nhiều toán tử JSONB như containment và một số key-existence operations.

### 34.3. jsonb_ops và jsonb_path_ops

Một lựa chọn khác:

```sql
CREATE INDEX idx_json313_orders_doc_path_gin
ON json313.orders
USING gin (doc jsonb_path_ops);
```

`jsonb_path_ops` tập trung vào nhóm phép tìm phù hợp như `@>` và một số dạng JSONPath theo phiên bản, thường có cấu trúc index khác. Nó **không** cung cấp cùng phạm vi hỗ trợ cho mọi toán tử tồn tại khóa `?` như `jsonb_ops`.

Đừng tạo cả hai GIN indexes chỉ vì ví dụ; chọn operator class theo workload và đo chi phí lưu trữ/ghi.

### 34.4. GIN không thay CHECK hay UNIQUE

Một GIN index giúp tìm kiếm JSON; nó **không** bảo đảm:

- external_id luôn tồn tại.
- status là một string hợp lệ.
- amount_cents không âm.
- external_id duy nhất theo tenant.
- không thể sửa identity sau INSERT.

Bảo vệ dữ liệu cần constraint/trigger/mô hình cột phù hợp, không phải chỉ lập chỉ mục.

## 35. EXPLAIN với truy vấn JSONB

Sau khi tạo dữ liệu lab:

```sql
ANALYZE json313.orders;
```

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_pk, tenant_id
FROM json313.orders
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

Và:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_pk
FROM json313.orders
WHERE doc @> '{"status":"NEW"}'::jsonb;
```

Quan sát:

- `Seq Scan`, `Index Scan` hoặc `Bitmap Index Scan`.
- `Index Cond` và `Filter`.
- Estimated rows so với actual rows.
- `Buffers`, thời gian và số lần truy cập.

### 35.1. Bảng lab nhỏ có thể dùng Seq Scan

Nếu chỉ có một vài orders, Seq Scan có thể rẻ hơn Index Scan. Việc planner không chọn GIN/B-tree trên bảng vài hàng **không chứng minh index sai**.

Muốn đánh giá hiệu năng thực, cần dữ liệu đại diện cho sản lượng và phân bố production.

### 35.2. Chỉ mục có chi phí

Mỗi index cần:

- Dung lượng.
- Bảo trì trên INSERT/UPDATE/DELETE.
- WAL và I/O.
- Thời gian build/rebuild.
- Quản lý migration.

Với JSONB lớn và nhiều update, thêm nhiều index trên toàn doc có thể làm chi phí ghi tăng đáng kể.

## 36. JSONB hay mô hình quan hệ: ranh giới thực dụng

Một cách thiết kế thường hợp lý:

**Cột quan hệ** cho:

- Khóa chính.
- Tenant ID.
- External ID.
- Trạng thái giao dịch.
- Số tiền/timestamp cần lọc/sắp xếp.
- Các foreign keys.
- Những giá trị được cập nhật thường xuyên hoặc cần constraint mạnh.

**JSONB** cho:

- Metadata tùy chọn.
- Payload từ nhà cung cấp có cấu trúc linh hoạt.
- Thuộc tính mở rộng ít cần join.
- Dữ liệu bổ sung có phiên bản schema rõ.
- Các object nhỏ cần lưu gần nguyên dạng cho một workflow.

### 36.1. Vì sao không để mọi thứ trong JSONB?

Nếu `amount_cents`, `currency`, `tenant_id` và `status` đều nằm trong JSON:

- Mỗi phép kiểm tra phải trích xuất/cast.
- FK trên thuộc tính khó mô hình hóa.
- Indexing phức tạp.
- Quyền theo cột không phân biệt từng JSON key.
- Update thuộc tính nóng có thể làm thay đổi toàn JSONB value.
- ORM và consumer có thể hiểu sai kiểu/NULL.

### 36.2. Vì sao cũng không cần chuẩn hóa mọi thuộc tính?

Các metadata không ổn định có thể không đáng tách thành nhiều bảng/cột riêng. JSONB cung cấp lợi ích thực tế khi cấu trúc thay đổi theo nguồn dữ liệu và ít nằm trong ràng buộc quan trọng.

Quyết định dựa trên **vai trò nghiệp vụ và pattern truy cập**, không theo một khẩu hiệu “JSON luôn xấu” hay “schema-less luôn nhanh”.

## 37. Trigger và constraint có giới hạn gì dưới concurrency?

Một CHECK kiểm tra **một hàng** với các hàm immutable trên dữ liệu hàng là cơ chế tốt cho nhiều quy tắc nội bộ của JSON.

Nhưng một số yêu cầu phụ thuộc **nhiều hàng**:

```text
Mỗi tenant + external_id chỉ xuất hiện một lần.
```

Nên dùng UNIQUE.

Hoặc:

```text
Tổng các đơn PAID của một tenant không vượt quá hạn mức.
```

Đây là invariant tổng hợp xuyên hàng, không thể chỉ thêm một CHECK trích JSON rồi xem là đã an toàn.

### 37.1. Trigger SELECT COUNT có thể gặp race

Nếu một trigger đọc:

```text
COUNT(orders cùng external_id)
```

rồi cho phép INSERT khi count=0, hai transaction đồng thời có thể đều đọc count=0 theo snapshot của mình.

Unique index là cơ chế đáng tin cậy cho tính duy nhất. Với invariant phức tạp hơn, cần transaction isolation, locking protocol hoặc thiết kế bảng tổng hợp phù hợp, cùng retry.

### 37.2. Không coi RLS là validation

RLS phân quyền hàng, không thay `CHECK`, `UNIQUE` hay xác thực kiểu của JSON.

### 37.3. Không coi trigger là lớp bảo vệ tuyệt đối với quyền DBA

Tài khoản có quyền đủ cao có thể thay schema/disable trigger. Bảo vệ vận hành cần quản lý quyền, kiểm toán migration và quy trình deploy đáng tin cậy.

## 38. Bảo vệ dữ liệu nhạy cảm trong JSON và log

JSONB có thể chứa email, địa chỉ, mã xác nhận, payload thanh toán hoặc dữ liệu định danh khác.

Nếu một trường nhạy cảm nằm trong doc:

- Tránh `SELECT doc` cho mọi consumer khi chỉ cần hai cột.
- Không ghi toàn bộ JSON vào log lỗi validation.
- Không lộ payload của tenant khác qua câu query thiếu tenant_id.
- Xem xét mã hóa/tokenization phù hợp với yêu cầu bảo mật.
- Quản lý bản sao, backup, môi trường thử nghiệm và dữ liệu demo.
- Kiểm tra các chỉ mục/search vectors có thể chứa nội dung nhạy cảm.
- Đánh giá quyền xem thống kê, audit và log của người vận hành.

### 38.1. Thông điệp lỗi constraint

Một lỗi SQLSTATE `23514` có thể cho biết tên constraint và trong một số ngữ cảnh có thông tin về hàng vi phạm. Không nên trả nguyên exception kèm tài liệu JSON cho client.

Thay vào đó:

```text
HTTP 422:
  code = INVALID_ORDER_DOCUMENT
  field = amount_cents
  message = "Số tiền không hợp lệ"
```

Thông tin ví dụ ở trên là thiết kế API, không phải định dạng lỗi tự động của PostgreSQL.

### 38.2. Mã lỗi từ database

| SQLSTATE | Tên thường dùng | Ví dụ |
|---|---|---|
| `22P02` | invalid_text_representation | JSON text/cast không hợp lệ trong tình huống liên quan |
| `23502` | not_null_violation | doc hoặc tenant_id là SQL NULL |
| `23514` | check_violation | JSON sai kiểu/giá trị theo CHECK |
| `23505` | unique_violation | Trùng tenant + external_id |
| `23503` | foreign_key_violation | Tham chiếu không hợp lệ khi mô hình có FK |
| `40001` | serialization_failure | Transaction cần rollback/retry theo nghiệp vụ |
| `40P01` | deadlock_detected | Transaction bị hủy do deadlock |

Một số lỗi cast sai kiểu/range có SQLSTATE khác. Ứng dụng nên đọc mã lỗi thực tế, không bắt lỗi chỉ bằng cách tìm một đoạn văn bản exception.

## 39. Bài kiểm tra thực hành theo dữ liệu hợp lệ và không hợp lệ

Chỉ chạy trong database lab. Các ví dụ **cố ý sai** dự kiến bị từ chối; nếu đang ở explicit transaction bị abort, hãy ROLLBACK hoặc dùng savepoint phù hợp trước thử nghiệm tiếp theo.

### 39.1. Khóa thiếu

```sql
-- Dự kiến bị từ chối:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"status":"NEW","amount_cents":0,"currency":"VND","items":[]}'
);
```

Vi phạm required keys và các constraint khác.

### 39.2. JSON null

```sql
-- Dự kiến bị từ chối:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":null,"status":"NEW","amount_cents":0,
      "currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

Khóa có tên nhưng kiểu không phải string.

### 39.3. Status sai kiểu

```sql
-- Dự kiến bị từ chối:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD1","status":3,"amount_cents":0,
      "currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

JSON number status không hợp lệ.

### 39.4. Amount âm

```sql
-- Dự kiến bị từ chối:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD2","status":"NEW",
      "amount_cents":-1,"currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

### 39.5. Amount fractional

```sql
-- Dự kiến bị từ chối:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD3","status":"NEW",
      "amount_cents":10.5,"currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

### 39.6. Items không phải array

```sql
-- Dự kiến bị từ chối:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD4","status":"NEW",
      "amount_cents":0,"currency":"VND","items":{},
      "shipping":{"city":"Hue"}}'
);
```

### 39.7. Một item sai làm toàn document không hợp lệ

```sql
-- Dự kiến bị từ chối:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD5","status":"NEW",
      "amount_cents":100,"currency":"VND",
      "items":[
        {"sku":"SKU-A","qty":1,"unit_price_cents":100},
        {"sku":"SKU-B","qty":-2,"unit_price_cents":100}
      ],
      "shipping":{"city":"Hue"}}'
);
```

Kiểm tra `NOT EXISTS (item sai)` phải phát hiện item thứ hai có qty âm.

### 39.8. Trùng external_id trong cùng tenant

Sau khi tạo unique expression index:

```sql
-- Dự kiến unique_violation nếu external_id này đã tồn tại:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-0001","status":"NEW",
      "amount_cents":0,"currency":"VND",
      "items":[{"sku":"SKU-Z","qty":1,"unit_price_cents":0}],
      "shipping":{"city":"Hue"}}'
);
```

### 39.9. Đổi external_id sau khi tạo

```sql
-- Dự kiến bị trigger từ chối:
UPDATE json313.orders
SET doc = jsonb_set(
    doc, '{external_id}', '"ORD-CHANGED"'::jsonb, false
)
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

### 39.10. Chuyển PAID về NEW

Sau khi một đơn hợp lệ đã chuyển thành PAID, thử:

```sql
-- Dự kiến bị trigger từ chối:
UPDATE json313.orders
SET doc = jsonb_set(
    doc, '{status}', '"NEW"'::jsonb, false
)
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

Trigger minh họa chặn riêng PAID→NEW.

## 40. Bài tập tự luyện có lời giải

### Bài 1. Cột jsonb NOT NULL có cho phép JSON null không?

**Trả lời:** `NOT NULL` trên cột chặn **SQL NULL**, không tự chặn giá trị JSONB `'null'::jsonb`. Muốn root object, thêm CHECK `jsonb_typeof(doc)='object'`.

### Bài 2. Vì sao CHECK(length(doc->>'x')>0) bỏ lọt khóa thiếu?

**Trả lời:** `doc->>'x'` trả SQL NULL khi thiếu; phép so trả UNKNOWN, mà PostgreSQL CHECK chấp nhận UNKNOWN.

### Bài 3. Sửa CHECK để khóa x bắt buộc không rỗng

```sql
CHECK (
    (length(btrim(doc ->> 'x')) > 0) IS TRUE
)
```

**Trả lời:** FALSE và UNKNOWN đều bị từ chối.

### Bài 4. Làm sao biết khóa có mặt dù giá trị là JSON null?

```sql
SELECT '{"x":null}'::jsonb ? 'x';
```

**Trả lời:** TRUE.

### Bài 5. Phân biệt thiếu khóa với JSON null

```sql
SELECT
    '{}'::jsonb ? 'x' AS missing,
    '{"x":null}'::jsonb ? 'x' AS present_null,
    jsonb_typeof('{"x":null}'::jsonb -> 'x') AS type_of_x;
```

**Trả lời:** missing=FALSE, present_null=TRUE, type_of_x là chuỗi `'null'`.

### Bài 6. Vì sao jsonb_typeof(...)=number chưa đủ cho amount_cents?

**Trả lời:** number có thể âm hoặc có phần thập phân; cần kiểm tra range và integer-ness.

### Bài 7. Tại sao dùng CASE trước numeric cast?

**Trả lời:** để chỉ cast sau khi xác nhận đúng JSON type; không dựa vào thứ tự đánh giá AND làm guard.

### Bài 8. items=[] có hợp lệ theo bài không?

**Trả lời:** không. Bài yêu cầu mảng có từ 1 đến 100 phần tử.

### Bài 9. items=[null] có được constraint độ dài bắt lỗi không?

**Trả lời:** không. Array length=1 hợp lệ về số phần tử, cần validation từng item.

### Bài 10. Dùng EXISTS(item hợp lệ) có đủ kiểm tra tất cả item?

**Trả lời:** không. Cần `NOT EXISTS(item không hợp lệ)` hoặc validator tương đương.

### Bài 11. jsonb_array_elements áp dụng cho object có an toàn không?

**Trả lời:** không. Phải xác nhận input là array bằng CASE/constraint trước khi gọi.

### Bài 12. jsonb_path_exists tìm ít nhất một SKU-A có nghĩa gì?

**Trả lời:** có **ít nhất một** item thỏa filter. Nó không bảo đảm tất cả item đều hợp lệ.

### Bài 13. Cách kiểm tra nested city là string?

```sql
jsonb_typeof(doc #> '{shipping,city}') = 'string'
```

**Trả lời:** dùng kết hợp `IS TRUE` và kiểm tra nonempty nếu city bắt buộc.

### Bài 14. Unique external_id theo tenant dùng chỉ mục gì?

```sql
CREATE UNIQUE INDEX ...
ON json313.orders(tenant_id, (doc ->> 'external_id'));
```

**Trả lời:** unique expression index trên tenant và thuộc tính JSON. Vẫn cần CHECK required/type.

### Bài 15. Có thể dùng SELECT NOT EXISTS trước INSERT thay UNIQUE không?

**Trả lời:** không an toàn cho mọi lịch đồng thời; hai transaction có thể cùng thấy chưa tồn tại. Unique index là lớp cưỡng chế chính.

### Bài 16. CHECK định dạng external_id có ngăn đổi ORD-1 thành ORD-2 không?

**Trả lời:** không, vì cả hai có thể đúng định dạng. Cần OLD/NEW trigger hoặc quyền/mô hình ghi phù hợp.

### Bài 17. Dùng IS DISTINCT FROM có lợi gì trong trigger?

**Trả lời:** so sánh rõ khi một bên NULL; kết quả không UNKNOWN như phép `<>`.

### Bài 18. status thuộc enum có đủ bảo vệ state transition không?

**Trả lời:** không. CHECK enum bảo vệ giá trị hiện tại, không bảo vệ mọi chuyển trạng thái lịch sử.

### Bài 19. jsonb_set tự bảo đảm người gọi có quyền sửa trường không?

**Trả lời:** không. Cần kiểm soát role/tenant, CHECK, trigger và API phù hợp.

### Bài 20. Vì sao cập nhật lại toàn doc từ snapshot cũ nguy hiểm?

**Trả lời:** có thể ghi đè thay đổi của transaction khác, gây lost update. Dùng update đường dẫn và/hoặc version check theo nghiệp vụ.

### Bài 21. version optimistic locking hoạt động thế nào?

**Trả lời:** UPDATE kèm `WHERE version = expected`, tăng version khi thành công và kiểm tra RETURNING/row count.

### Bài 22. REVOKE UPDATE(doc) ở cấp cột có tự cấm sửa mọi JSON key không?

**Trả lời:** chỉ có ý nghĩa trong tổng thể quyền PostgreSQL. Nếu role có UPDATE cấp bảng qua grant khác thì vẫn có thể sửa. Không có grant per-key tự nhiên trên doc.

### Bài 23. RLS có xác thực amount_cents không?

**Trả lời:** không. RLS kiểm soát hàng theo policy; CHECK/validation đảm bảo thuộc tính JSON hợp lệ.

### Bài 24. PostgreSQL core jsonb có tự triển khai toàn bộ JSON Schema không?

**Trả lời:** không chỉ vì cột dùng jsonb. Có thể dùng CHECK/custom functions hoặc extension/library phù hợp.

### Bài 25. Khi đổi hàm validator IMMUTABLE trong CHECK, dữ liệu cũ có tự recheck không?

**Trả lời:** không tự động. Migration phải đối soát/validate dữ liệu theo logic mới.

### Bài 26. ADD CONSTRAINT ... NOT VALID có bỏ kiểm tra hàng mới không?

**Trả lời:** không. Nó chủ yếu tránh kiểm tra toàn bộ hàng cũ ngay ở bước ADD cho các loại constraint được hỗ trợ.

### Bài 27. GIN index có thay UNIQUE không?

**Trả lời:** không. GIN hỗ trợ tìm kiếm JSONB, không chứng minh uniqueness của external_id.

### Bài 28. Khi nào B-tree expression phù hợp hơn GIN toàn doc?

**Trả lời:** khi truy vấn thường tìm equality theo một thuộc tính scalar như tenant+external_id, và cần unique/lookup theo khóa cụ thể.

### Bài 29. Những thuộc tính nào nên tách thành cột quan hệ?

**Trả lời:** thường là tenant ID, business ID, FK, trạng thái và số tiền quan trọng, timestamp, các giá trị truy vấn/cập nhật thường xuyên.

### Bài 30. CHECK có bảo đảm tổng đơn PAID toàn tenant không vượt quota không?

**Trả lời:** không tự bảo vệ bất biến xuyên nhiều hàng; cần mô hình counter/khóa hoặc isolation/constraint phù hợp.

### Bài 31. Vì sao JSON null khác xóa khóa?

**Trả lời:** `{"x":null}` vẫn có x; `{}` không có x. `? 'x'` phân biệt, còn `->>` có thể trả SQL NULL cho cả hai.

### Bài 32. Trước khi trả lỗi validation cho client cần lưu ý gì?

**Trả lời:** không lộ toàn document nhạy cảm. Trả mã lỗi ổn định và field/description an toàn.

## 41. Những lỗi thường gặp

### Lỗi 1 — Nghĩ jsonb đồng nghĩa JSON Schema

`jsonb` kiểm tra định dạng JSON, không tự bảo vệ các trường nghiệp vụ.

### Lỗi 2 — Không kiểm tra root object

JSONB có thể lưu array, string, number, boolean hoặc JSON null ở root.

### Lỗi 3 — Chỉ kiểm tra doc NOT NULL

Không ngăn khóa bên trong thiếu hoặc chứa JSON null.

### Lỗi 4 — CHECK biểu thức có thể trả UNKNOWN

PostgreSQL CHECK chấp nhận UNKNOWN; dùng `IS TRUE`, `COALESCE` hoặc điều kiện bắt buộc khác.

### Lỗi 5 — Dùng ->> mà quên kiểu JSON gốc

`->>` trả text cho nhiều loại JSON; numeric/boolean có thể bị đối xử như string.

### Lỗi 6 — Chỉ kiểm tra khóa tồn tại

`doc ? 'status'` là TRUE cả khi status=JSON null hoặc số sai kiểu.

### Lỗi 7 — Cast integer trực tiếp trên dữ liệu chưa kiểm tra

Có thể gặp lỗi parse/overflow; kiểm tra kiểu/range trước và dùng CASE.

### Lỗi 8 — Gọi jsonb_array_length trên object

Có thể lỗi; cần xác nhận JSON array trước.

### Lỗi 9 — Dùng một item hợp lệ để chứng minh cả mảng

Cần kiểm tra **không tồn tại phần tử sai**, không chỉ EXISTS một phần tử đúng.

### Lỗi 10 — Tưởng JSONPath existence kiểm tra toàn bộ schema

Có một path match không chứng minh mọi field và nested array item đều đúng.

### Lỗi 11 — UNIQUE expression nhưng thiếu CHECK required

Trường bị thiếu/JSON null trích thành SQL NULL, có thể làm uniqueness hoạt động ngoài kỳ vọng.

### Lỗi 12 — CHECK hợp lệ định dạng nhưng không chặn đổi identity

CHECK không so OLD/NEW; cần trigger hoặc mô hình ghi thích hợp.

### Lỗi 13 — Enum CHECK thay thế state machine

Hai trạng thái đều thuộc enum nhưng chuyển đổi giữa chúng có thể sai.

### Lỗi 14 — Cấp quyền UPDATE cho doc rồi tưởng chặn được từng key

Quyền cấp cột không phân biệt đường dẫn JSON.

### Lỗi 15 — Dùng RLS thay validation

RLS bảo vệ phạm vi hàng, không thay constraint kiểu/giá trị.

### Lỗi 16 — UPDATE toàn tài liệu từ bản đọc cũ

Có thể làm mất thay đổi của transaction khác. Cần jsonb_set/version/locking phù hợp.

### Lỗi 17 — Thay hàm validator rồi không kiểm tra hàng cũ

Các hàng lịch sử không tự được revalidate chỉ vì hàm trong CHECK đổi nội dung.

### Lỗi 18 — Dùng NOT VALID và tưởng constraint không chạy nữa

Các lệnh ghi mới vẫn phải thỏa constraint.

### Lỗi 19 — GIN index thay thế UNIQUE

Index tìm kiếm không tự bảo vệ tính duy nhất.

### Lỗi 20 — Đưa tất cả trường quan trọng vào JSONB

Khó dùng FK, constraint, quyền theo cột và cập nhật thường xuyên; cân nhắc mô hình hybrid.

### Lỗi 21 — Quên tenant_id trong query/update/unique

Có thể gây xung đột sai tenant hoặc làm lộ dữ liệu.

### Lỗi 22 — Lưu thông tin nhạy cảm nguyên document trong log

Lỗi constraint không phải lý do lộ payload.

### Lỗi 23 — Không xử lý retry/transaction

Một thao tác nhiều bước có thể rollback; các side effect ngoài DB phải được điều phối đúng.

### Lỗi 24 — Tự tin dữ liệu cũ hợp lệ vì dữ liệu mới có CHECK

Khi mới thêm NOT VALID, các hàng cũ có thể vẫn sai cho tới khi được đối soát và VALIDATE.

## 42. Quy trình thiết kế validation cho một JSON document

Một quy trình có thể áp dụng:

1. **Viết hợp đồng nghiệp vụ:** trường bắt buộc, kiểu, giới hạn, enum, nested objects, tính duy nhất và điều kiện đổi trạng thái.
2. **Chọn ranh giới dữ liệu:** giá trị nào nên là cột quan hệ, giá trị nào có thể lưu JSONB.
3. **Kiểm tra cú pháp:** cast/parse JSONB khi nhận dữ liệu.
4. **Kiểm tra root:** object/array theo mục đích.
5. **Kiểm tra tồn tại:** required keys đúng cấp.
6. **Kiểm tra kiểu:** jsonb_typeof hoặc validator tương đương.
7. **Kiểm tra miền giá trị:** nonempty, enum, range, integer, regex.
8. **Kiểm tra nested arrays:** mọi phần tử, không chỉ một.
9. **Kiểm tra liên trường:** amount vs items, currency vs amount nếu nghiệp vụ quy định.
10. **Bảo vệ xuyên hàng:** UNIQUE/FK/constraint tương thích.
11. **Bảo vệ chuyển trạng thái:** trigger hoặc giao thức ghi có quyền hạn.
12. **Giới hạn cập nhật:** conditional UPDATE, optimistic version hoặc transaction phù hợp.
13. **Kiểm soát truy cập:** least privilege, RLS theo tenant khi cần.
14. **Version hóa schema:** có migration/compatibility rõ ràng.
15. **Đối soát dữ liệu cũ:** NOT VALID và VALIDATE nếu thích hợp.
16. **Quan sát vận hành:** error codes, metrics, index usage và audit an toàn.
17. **Kiểm thử:** valid, missing, JSON null, SQL NULL, wrong type, overflow, duplicate, concurrent write.
18. **Tối ưu:** chỉ thêm index dựa trên workload và EXPLAIN thực tế.

Đây không phải một checklist để “chạy Content QA” của worker; nó là nội dung kiến thức cho người học triển khai PostgreSQL thực tế.

## 43. Bảng tra cứu nhanh

| Yêu cầu | Công cụ/mẫu PostgreSQL | Điều cần nhớ |
|---|---|---|
| JSON cú pháp hợp lệ | `jsonb` / cast `::jsonb` | Chưa bảo đảm schema |
| Root là object | `CHECK (jsonb_typeof(doc)='object')` | doc cần NOT NULL |
| Khóa cấp trên cùng tồn tại | `doc ? 'key'` | Không bảo đảm khác JSON null |
| Nhiều khóa bắt buộc | `doc ?& ARRAY[...]` | Chỉ kiểm tra sự hiện diện |
| Kiểu của giá trị | `jsonb_typeof(doc->'key')` | Trả SQL NULL nếu thiếu |
| String không rỗng | `length(btrim(doc->>'x'))>0` với `IS TRUE` | CHECK UNKNOWN là bẫy |
| Enum | `doc->>'status' IN (...)` và type check | Chưa kiểm tra chuyển trạng thái |
| Number integer/range | `CASE` + `::numeric` + `trunc` | Tránh cast dữ liệu sai kiểu |
| Array đúng kiểu | `jsonb_typeof(...)= 'array'` | jsonb_array_length chỉ dùng cho array |
| Array có item hợp lệ | `NOT EXISTS(jsonb_array_elements(...) item sai)` | Kiểm tra tất cả |
| Nested path | `#>` và `#>>` | Phân biệt JSONB/text/NULL |
| Tìm một giá trị trong array | `@?` / `jsonb_path_exists` | Existence không phải ALL |
| Duy nhất ID theo tenant | Unique expression index | Kết hợp required/type CHECK |
| Khóa quan trọng không đổi | OLD/NEW trigger, quyền ghi | CHECK chỉ thấy hàng mới |
| Cập nhật một trường | `jsonb_set` | Không thay validation |
| Optimistic concurrency | `WHERE version=?` + increment | Check row count |
| Truy vấn scalar JSON | B-tree expression index | Phù hợp equality/range |
| Truy vấn containment JSON | GIN `jsonb_ops`/`jsonb_path_ops` | Theo operator class |
| Thêm CHECK từng bước | `ADD CONSTRAINT ... NOT VALID` | Dữ liệu mới vẫn bị kiểm tra |
| Kiểm tra hàng cũ | `VALIDATE CONSTRAINT` | Cần sửa dữ liệu sai |
| Phân quyền tenant | RLS + auth context | Không thay JSON validation |
| Hợp đồng JSON phức tạp | JSON Schema + validator tương thích | Extension không tự có sẵn |

## 44. Tài liệu PostgreSQL để tra cứu

Hãy đọc tài liệu đúng **phiên bản PostgreSQL** và cấu hình thật của hệ thống:

- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): khác biệt `json` và `jsonb`, cách lưu trữ/kiểm tra cú pháp.
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): `->`, `->>`, `#>`, `?`, `?&`, `jsonb_set`, JSONPath.
- [SQL/JSON Path Expressions](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-SQLJSON-PATH): JSONPath và hành vi khi tìm nested data.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `CHECK`, `NOT NULL`, `UNIQUE` và `FOREIGN KEY`.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): unique/expression B-tree.
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html): index cho JSONB và operator classes.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): giới hạn truy cập theo hàng.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html): quyền bảng/cột.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): bảo vệ thay đổi bằng OLD/NEW.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): thêm và validate constraint.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): đọc kế hoạch truy vấn.

Kiểm tra môi trường:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

Các ví dụ trong bài là code học tập, không phải kết quả đã được chạy trên server cụ thể. Với production, cần xác minh DDL, ràng buộc, quyền và migration trên bản sao dữ liệu phù hợp.

## 45. Tổng kết

Một tài liệu JSONB có thể **đúng cú pháp** nhưng **sai hợp đồng dữ liệu**. PostgreSQL có nhiều công cụ bảo vệ các trường quan trọng:

```text
Ứng dụng gửi JSON
       |
       v
Parse/cast sang jsonb
       |
       v
NOT NULL + root type check
       |
       v
Required keys + type + value checks
       |
       v
Nested arrays/objects validation
       |
       v
UNIQUE/FK cho quy tắc giữa các hàng
       |
       v
Trigger/quyền cho trường không được đổi
       |
       v
Transaction + concurrency + audit
       |
       v
Dữ liệu đã commit thỏa hợp đồng
```

Các điểm cần nhớ:

1. **`jsonb` không phải JSON Schema validator mặc định.** Nó bảo vệ cú pháp, không tự xác thực mọi trường.
2. **JSON null, SQL NULL và khóa thiếu là ba trường hợp khác nhau.** Chọn toán tử phù hợp để phân biệt.
3. **CHECK chấp nhận UNKNOWN.** Dùng `IS TRUE`, `COALESCE` và điều kiện tồn tại/kiểu để chặn trường thiếu.
4. **Kiểm tra kiểu gốc bằng `jsonb_typeof` trước khi cast** các trường number/string quan trọng.
5. **JSON array cần kiểm tra toàn bộ phần tử**, không chỉ độ dài hoặc có ít nhất một item đúng.
6. **Khóa định danh cần UNIQUE phù hợp**, không chỉ regex hoặc SELECT NOT EXISTS.
7. **CHECK không bảo vệ tính bất biến qua thời gian.** Dùng trigger OLD/NEW, quyền ghi hoặc mô hình cột phù hợp để chặn thay đổi trường quan trọng.
8. **State machine khác enum.** Trạng thái hiện tại hợp lệ không có nghĩa mọi chuyển trạng thái đều hợp lệ.
9. **jsonb_set và optimistic version** giúp cập nhật có điều kiện, nhưng không tự thay quyền/constraint.
10. **RLS và quyền cột không thay validation JSON**; quyền cột cũng không hiểu từng JSON key.
11. **Có thể triển khai constraint từng bước bằng NOT VALID/VALIDATE** để xử lý dữ liệu lịch sử.
12. **Chọn JSONB cho phần linh hoạt, cột quan hệ cho những invariants quan trọng** khi điều đó giúp schema rõ và an toàn.

**Một câu để nhớ:** JSONB cho phép lưu dữ liệu linh hoạt, nhưng những trường quyết định danh tính, tiền bạc, trạng thái và quyền truy cập vẫn phải được PostgreSQL bảo vệ bằng **các ràng buộc có ngữ nghĩa rõ ràng**, không chỉ dựa vào việc tài liệu là JSON hợp lệ.

