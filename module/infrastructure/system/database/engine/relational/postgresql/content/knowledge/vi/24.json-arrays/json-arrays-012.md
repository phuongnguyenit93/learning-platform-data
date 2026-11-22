# Phân biệt JSON null, SQL NULL và thành phần không tồn tại trong PostgreSQL

Giả sử một API nhận ba payload:

```json
{"email": null}
```

```json
{}
```

```json
{"email": "null"}
```

Ba payload này **không giống nhau**. Payload thứ nhất có khóa `email` với **giá trị JSON null**; payload thứ hai **không có khóa `email`**; payload thứ ba có khóa `email` chứa **chuỗi text bốn ký tự `null`**. Bên cạnh đó, một cột kiểu `jsonb` trong PostgreSQL còn có thể chứa **SQL NULL**, nghĩa là *bản thân giá trị cột không có giá trị SQL*, chứ không phải một tài liệu JSON chứa từ khóa `null`.

Khác biệt ấy liên quan trực tiếp tới logic API PATCH, cập nhật hồ sơ khách hàng, lọc dữ liệu JSONB, kiểm tra schema, đồng bộ sự kiện và xử lý kết quả trong Java/JDBC. Nếu hiểu nhầm, hệ thống có thể ghi đè một giá trị hợp lệ thành NULL, coi một field được chủ động xóa giống field không được gửi, hoặc dùng `COALESCE` làm mất thông tin cần thiết.

Bài học trình bày riêng ba trạng thái **SQL NULL**, **JSON null** và **thành phần không tồn tại (missing key/path/index)**; sau đó phân tích chính xác cách PostgreSQL xử lý chúng qua các toán tử JSON/JSONB, hàm kiểm tra kiểu, logic NULL của SQL, cập nhật và ràng buộc.

> **Thông điệp cốt lõi:** `'null'::jsonb` là **một giá trị JSONB có tồn tại**, còn `NULL::jsonb` là **SQL NULL**. Khi tra một khóa không tồn tại bằng `->`, PostgreSQL thường trả **SQL NULL**; khi khóa có giá trị JSON null, `->` trả về **JSONB null**. Nhưng `->>` chuyển sang text nên cả hai trường hợp đều trả **SQL NULL**, làm mất khả năng phân biệt nếu chỉ nhìn kết quả text.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa được SQL NULL, JSON null, khóa vắng mặt, phần tử mảng có JSON null và chỉ số mảng vượt giới hạn.
2. Phân biệt kết quả của `->` với `->>`, `#>` với `#>>` khi gặp JSON null hoặc missing.
3. Dùng `IS NULL`, `= 'null'::jsonb`, `jsonb_typeof` và `?` để kiểm tra đúng điều kiện.
4. Hiểu vì sao SQL dùng **logic ba giá trị**: TRUE, FALSE và UNKNOWN khi so sánh với SQL NULL.
5. Không vô tình gộp các trạng thái bằng `COALESCE` hoặc cast sang text.
6. Phân biệt khóa có giá trị JSON null với khóa không tồn tại trong đối tượng JSONB lồng nhau.
7. Hiểu cách JSON arrays xử lý `null`, chỉ số không có phần tử và chỉ số âm.
8. Biết khi nào dùng `jsonb_set`, `jsonb_set_lax`, toán tử `-` và `#-` để cập nhật hoặc xóa.
9. Thiết kế `CHECK`, `NOT NULL`, default và unique/index phù hợp với semantics thiếu field/JSON null/SQL NULL.
10. Xây dựng quy tắc xử lý JSON PATCH/API và giải mã trong Java mà không làm mất thông tin về việc field có xuất hiện hay không.

## 2. Ba trạng thái cần phân biệt

| Trạng thái | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **SQL NULL** | `NULL::jsonb` | Biểu thức hoặc cột SQL không có giá trị. Không phải JSON document chứa literal null. |
| **JSON null** | `'null'::jsonb` hoặc `'{"email":null}'::jsonb` | Giá trị JSON thực sự tồn tại và có kiểu JSON là `null`. |
| **Missing** | `'{}'::jsonb` không có `email` | Bên trong một object, khóa không tồn tại; hoặc trong array, index không hợp lệ. |

Ngoài ra, các giá trị sau **không phải NULL**:

```json
{"email": ""}
```

```json
{"email": "null"}
```

```json
{"email": false}
```

```json
{"email": 0}
```

```json
{"email": []}
```

```json
{"email": {}}
```

Các giá trị này lần lượt thuộc kiểu JSON string, string, boolean, number, array và object. Không được coi chuỗi rỗng, số 0, boolean false hay collection rỗng là JSON null chỉ vì chúng có thể đại diện “không có thông tin” trong một nghiệp vụ cụ thể.

### 2.1. SQL NULL là cấp độ biểu thức SQL

```sql
SELECT
    NULL::jsonb AS sql_null,
    'null'::jsonb AS json_null,
    '{}'::jsonb AS empty_object,
    '[]'::jsonb AS empty_array;
```

`NULL::jsonb` chỉ định **SQL NULL được gắn kiểu jsonb**. Ngược lại `'null'::jsonb` là một **giá trị jsonb scalar** đại diện JSON null.

Với cột `doc jsonb`, cả hai đều có thể lưu được nếu cột không có constraint `NOT NULL`.

### 2.2. Missing chỉ có nghĩa khi nói tới thành phần trong cấu trúc

Với:

```json
{"customer":{"name":"Lan"}}
```

`customer` tồn tại; `customer.name` tồn tại; `customer.email` không tồn tại. Bản thân tài liệu JSON **không phải missing** vì nó là giá trị đã được cung cấp.

Khi dùng toán tử PostgreSQL để tìm một path không có, kết quả thường được biểu diễn bằng **SQL NULL**. Điều này không làm hai trạng thái trở thành đồng nhất về ngữ nghĩa: ta vẫn có thể kiểm tra **sự tồn tại của khóa** trên object bằng toán tử phù hợp.

### 2.3. JSON null là giá trị chứ không phải dấu hiệu xóa tự động

`{"email":null}` nghĩa là JSON object chứa trường email với JSON null. Trong một số giao thức (chẳng hạn JSON Merge Patch) null có ngữ nghĩa *yêu cầu xóa field*, nhưng đó là **quy tắc giao thức ứng dụng**, không phải hành vi mặc định của PostgreSQL khi lưu hoặc cập nhật JSONB.

Chạy:

```sql
SELECT '{"email": null}'::jsonb;
```

PostgreSQL không tự loại bỏ khóa email. Khi nào xóa khóa là do SQL/application của bạn quyết định.

## 3. json và jsonb: sự phân biệt này tồn tại ở cả hai

PostgreSQL có hai kiểu JSON phổ biến:

- `json`: lưu biểu diễn văn bản JSON đã kiểm tra tính hợp lệ, có những đặc tính bảo toàn biểu diễn nguồn riêng.
- `jsonb`: biểu diễn nhị phân đã phân tích cú pháp, thuận tiện cho nhiều toán tử, kiểm tra membership, cập nhật và index.

Cả hai đều có khái niệm **JSON null** khác với **SQL NULL**; cả hai đều có thể được truy cập bằng các toán tử lấy trường. Bài học ưu tiên `jsonb` vì nó phù hợp hơn cho phân tích tồn tại khóa, containment, JSON path và cập nhật trong PostgreSQL.

### 3.1. Hai cách lấy kiểu JSON

```sql
SELECT
    json_typeof('null'::json) AS type_from_json,
    jsonb_typeof('null'::jsonb) AS type_from_jsonb;
```

Cả hai trả **chuỗi SQL text `null`** (không phải SQL NULL), biểu thị tên kiểu JSON.

So với:

```sql
SELECT
    json_typeof(NULL::json) AS sql_null_json_type,
    jsonb_typeof(NULL::jsonb) AS sql_null_jsonb_type;
```

Hai giá trị trả về đều là **SQL NULL**.

### 3.2. Đừng nhầm tên kiểu text "null" với giá trị JSON null

`jsonb_typeof` trả về **text**, vì vậy:

```sql
SELECT
    jsonb_typeof('null'::jsonb) = 'null'
        AS is_json_null,
    jsonb_typeof('null'::jsonb) IS NULL
        AS is_sql_null;
```

Kết quả tương ứng TRUE và FALSE.

Ngược lại:

```sql
SELECT
    jsonb_typeof(NULL::jsonb) = 'null'
        AS comparison_with_sql_null,
    jsonb_typeof(NULL::jsonb) IS NULL
        AS is_sql_null;
```

Biểu thức đầu cho SQL UNKNOWN/NULL, biểu thức thứ hai TRUE. Muốn dùng chúng trong `WHERE`, phải nhớ SQL chỉ giữ các dòng có predicate TRUE.

## 4. Bộ dữ liệu thực hành: bao quát các trạng thái

Các câu SQL sau chỉ dành cho **database lab**; không sửa dữ liệu sản xuất.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS json_null_lab;

CREATE TABLE json_null_lab.documents (
    id integer PRIMARY KEY,
    description text NOT NULL,
    doc jsonb
);
```

Cột `doc` cố ý **cho phép SQL NULL** để học cách phân biệt với JSON null. Trong hệ thống sản xuất, nên cân nhắc `NOT NULL` khi nghiệp vụ luôn yêu cầu có JSON document.

### 4.2. Chèn dữ liệu

```sql
INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    ( 1, 'SQL NULL document', NULL::jsonb),
    ( 2, 'JSON null document', 'null'::jsonb),
    ( 3, 'Empty object', '{}'::jsonb),
    ( 4, 'Email JSON null', '{"email":null}'::jsonb),
    ( 5, 'Email string null', '{"email":"null"}'::jsonb),
    ( 6, 'Email empty string', '{"email":""}'::jsonb),
    ( 7, 'Email normal string',
          '{"email":"a@example.com"}'::jsonb),
    ( 8, 'Email false', '{"email":false}'::jsonb),
    ( 9, 'Nested empty profile', '{"profile":{}}'::jsonb),
    (10, 'Nested email JSON null',
          '{"profile":{"email":null}}'::jsonb),
    (11, 'Profile JSON null', '{"profile":null}'::jsonb),
    (12, 'Nested email normal',
          '{"profile":{"email":"p@example.com"}}'::jsonb),
    (13, 'Empty array document', '[]'::jsonb),
    (14, 'Array with JSON null', '[null]'::jsonb),
    (15, 'Array with string null', '["null"]'::jsonb),
    (16, 'Mixed array', '[null,7,false,""]'::jsonb),
    (17, 'Email number zero', '{"email":0}'::jsonb),
    (18, 'Email empty object', '{"email":{}}'::jsonb);
```

Chèn một lần trên bảng rỗng. Nếu chạy lại, primary key `id` sẽ báo lỗi trùng. Các chuỗi JSON là dữ liệu giả lập, không chứa thông tin người dùng thật.

### 4.3. Kiểm tra loại tài liệu ở cấp cao nhất

```sql
SELECT
    id,
    description,
    doc IS NULL AS is_sql_null,
    jsonb_typeof(doc) AS json_type
FROM json_null_lab.documents
ORDER BY id;
```

Một số kết quả đáng chú ý:

| id | doc | `doc IS NULL` | `jsonb_typeof(doc)` |
| ---: | --- | --- | --- |
| 1 | SQL NULL | TRUE | SQL NULL |
| 2 | `null` | FALSE | `null` (text) |
| 3 | `{}` | FALSE | `object` |
| 4 | `{"email":null}` | FALSE | `object` |
| 13 | `[]` | FALSE | `array` |
| 14 | `[null]` | FALSE | `array` |

**Quan sát quan trọng:** một object chứa trường JSON null vẫn có **kiểu object** ở cấp tài liệu. Nếu muốn biết `email` có null hay không, phải lấy trường trước khi gọi `jsonb_typeof`.

### 4.4. Tài liệu null và object không có trường

So:

```sql
SELECT
    id,
    doc IS NULL AS sql_null_document,
    doc = 'null'::jsonb AS json_null_document,
    doc = '{}'::jsonb AS empty_json_object
FROM json_null_lab.documents
WHERE id IN (1, 2, 3)
ORDER BY id;
```

Ở dòng id=1, hai phép so sánh `doc = ...` trả SQL NULL, **không phải FALSE**, vì toán tử so sánh thông thường với SQL NULL cho UNKNOWN. Muốn kết quả boolean rõ ràng, dùng `IS NULL`, `IS DISTINCT FROM` hoặc CASE tùy ý định.

## 5. Toán tử ->: lấy giá trị JSON mà chưa chuyển thành text

Toán tử:

```sql
document -> 'key'
```

trả `json` hoặc `jsonb` tùy kiểu đầu vào. Đây là công cụ quan trọng để **giữ khả năng phân biệt JSON null và missing**.

### 5.1. Khi khóa tồn tại với JSON null

```sql
SELECT '{"email":null}'::jsonb -> 'email' AS email_json;
```

Kết quả là **giá trị JSONB null**. Nghĩa là biểu thức không phải SQL NULL:

```sql
SELECT
    ('{"email":null}'::jsonb -> 'email') IS NULL
        AS is_sql_null,
    ('{"email":null}'::jsonb -> 'email') = 'null'::jsonb
        AS is_json_null;
```

Kết quả:

| `is_sql_null` | `is_json_null` |
| --- | --- |
| FALSE | TRUE |

### 5.2. Khi khóa không tồn tại

```sql
SELECT '{}'::jsonb -> 'email' AS email_json;
```

Không có key email, nên kết quả là **SQL NULL**:

```sql
SELECT
    ('{}'::jsonb -> 'email') IS NULL
        AS is_missing_extraction,
    ('{}'::jsonb -> 'email') = 'null'::jsonb
        AS equals_json_null;
```

Kết quả tương ứng TRUE và SQL NULL/UNKNOWN. Phép so sánh với `'null'::jsonb` không cho FALSE ở đây vì phía bên trái là SQL NULL.

### 5.3. Khi tài liệu gốc là SQL NULL

```sql
SELECT NULL::jsonb -> 'email' AS extracted_value;
```

Kết quả cũng là **SQL NULL**. Như vậy chỉ với một phép `->`, ta chưa phân biệt được:

1. Tài liệu cột `doc` có SQL NULL.
2. Tài liệu object không có khóa email.
3. Một path lồng nhau bị thiếu hoặc không tiếp tục được.

Nếu cần phân biệt ba trường hợp, phải kiểm tra **cấp gốc** và **sự tồn tại của khóa** trước/sau truy xuất.

### 5.4. Khi khóa tồn tại với chuỗi "null"

```sql
SELECT
    '{"email":"null"}'::jsonb -> 'email' AS json_string,
    '{"email":null}'::jsonb -> 'email' AS json_null;
```

Hai giá trị đầu ra là **JSONB string `"null"`** và **JSONB null `null`**, khác kiểu, khác ngữ nghĩa.

## 6. Toán tử ->>: trích xuất thành SQL text và điểm mất thông tin

Toán tử:

```sql
document ->> 'key'
```

trả **SQL text** thay vì jsonb. Đây là thao tác thường dùng khi lấy dữ liệu JSON để hiển thị, lọc so sánh text hoặc chuyển sang Java String.

### 6.1. Cùng một text result cho JSON null và missing

```sql
SELECT
    '{"email":null}'::jsonb ->> 'email'
        AS explicit_json_null,
    '{}'::jsonb ->> 'email'
        AS missing_email,
    NULL::jsonb ->> 'email'
        AS sql_null_document;
```

Cả ba cột trả **SQL NULL**.

Do đó:

```sql
WHERE doc ->> 'email' IS NULL
```

không nói riêng “email có mặt với giá trị JSON null”. Nó cũng chấp nhận email missing hoặc cả document SQL NULL (nếu không có điều kiện hạn chế).

### 6.2. Chuỗi chữ "null" vẫn là text thật

```sql
SELECT
    '{"email":"null"}'::jsonb ->> 'email'
        AS string_null,
    '{"email":null}'::jsonb ->> 'email'
        AS json_null;
```

Cột đầu là SQL text có nội dung `null`; cột thứ hai là SQL NULL. Khi hiển thị bằng GUI hoặc xuất CSV, hai giá trị có thể **trông giống nhau** nếu ứng dụng dùng cùng cách biểu diễn NULL và text, nhưng trong SQL chúng khác nhau.

### 6.3. Các scalar khác khi chuyển sang text

```sql
SELECT
    '{"v":false}'::jsonb ->> 'v' AS false_text,
    '{"v":0}'::jsonb ->> 'v' AS zero_text,
    '{"v":""}'::jsonb ->> 'v' AS empty_text,
    '{"v":{}}'::jsonb ->> 'v' AS object_text;
```

Kết quả tương ứng là text `false`, `0`, chuỗi rỗng và biểu diễn text của object, **không phải SQL NULL**. Toán tử `->>` chuyển kiểu dữ liệu sang text, vì vậy muốn biết dữ liệu gốc có phải boolean/number/object phải truy xuất JSON trước khi chuyển hoặc gọi `jsonb_typeof`.

### 6.4. So sánh nhanh

| Nguồn JSON | `-> 'email'` | `->> 'email'` |
| --- | --- | --- |
| `{"email":null}` | JSONB null | SQL NULL |
| `{}` | SQL NULL | SQL NULL |
| `{"email":"null"}` | JSONB string `"null"` | SQL text `null` |
| `{"email":""}` | JSONB string rỗng | SQL text rỗng |
| `{"email":false}` | JSONB boolean false | SQL text `false` |
| Document SQL NULL | SQL NULL | SQL NULL |

**Quy tắc:** nếu cần phân biệt JSON null và missing, **đừng chỉ giữ kết quả của `->>`**.

## 7. jsonb_typeof: phân biệt kiểu JSON và SQL NULL

Hàm `jsonb_typeof(value)` trả về một **text** chứa một trong các tên kiểu JSON:

| Giá trị đầu vào | Kết quả |
| --- | --- |
| `'null'::jsonb` | `'null'` |
| `'"hello"'::jsonb` | `'string'` |
| `'0'::jsonb` | `'number'` |
| `'false'::jsonb` | `'boolean'` |
| `'[]'::jsonb` | `'array'` |
| `'{}'::jsonb` | `'object'` |
| `NULL::jsonb` | SQL NULL |

### 7.1. Phân loại một trường object

```sql
SELECT
    id,
    description,
    jsonb_typeof(doc -> 'email') AS email_json_type
FROM json_null_lab.documents
WHERE id IN (3, 4, 5, 6, 7, 8, 17, 18)
ORDER BY id;
```

Kết quả mong đợi:

| id | Trường email | `jsonb_typeof(doc -> 'email')` |
| ---: | --- | --- |
| 3 | Missing | SQL NULL |
| 4 | JSON null | Text `null` |
| 5 | JSON string `"null"` | Text `string` |
| 6 | JSON string rỗng | Text `string` |
| 7 | JSON email thật | Text `string` |
| 8 | JSON false | Text `boolean` |
| 17 | JSON number 0 | Text `number` |
| 18 | JSON object rỗng | Text `object` |

### 7.2. Kiểm tra JSON null rõ ràng

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE jsonb_typeof(doc -> 'email') = 'null';
```

Với dữ liệu nguyên trạng, câu này trả **id=4**. Lưu ý `jsonb_typeof` chạy trên **giá trị email**, không phải trên cả document.

### 7.3. Kiểm tra thiếu trường theo kết quả trích xuất

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE (doc -> 'email') IS NULL;
```

Đoạn này trả các document không có email **và cả document SQL NULL hoặc JSON root không có dạng object chứa email**. Nếu muốn “khóa email không có trong object” một cách chính xác, cần thêm điều kiện kiểu object và toán tử kiểm tra khóa, thay vì dựa riêng vào `IS NULL` của biểu thức trích xuất.

### 7.4. Tránh so sánh kiểu JSON với SQL NULL bằng dấu bằng

Sai:

```sql
-- Không tìm SQL NULL:
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc -> 'email') = NULL;
```

Mọi phép so sánh `= NULL` trả UNKNOWN theo logic SQL thông thường, nên `WHERE` không chọn dòng nào vì điều kiện không TRUE. Đúng nếu mục tiêu là kiểm tra kết quả hàm không có giá trị:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc -> 'email') IS NULL;
```

Nhưng nhớ rằng SQL NULL của kết quả hàm có nhiều nguyên nhân, gồm thiếu khóa và document SQL NULL.

## 8. Toán tử ?: khóa có tồn tại hay không?

Với đối tượng `jsonb`, toán tử:

```sql
document ? 'email'
```

hỏi **key `email` có tồn tại ở cấp ngoài cùng hay không**, bất kể giá trị của key là gì.

```sql
SELECT
    '{"email":null}'::jsonb ? 'email'
        AS json_null_field_present,
    '{}'::jsonb ? 'email'
        AS missing_field,
    '{"email":"null"}'::jsonb ? 'email'
        AS string_null_field_present;
```

Kết quả:

| JSON null | Missing | String "null" |
| --- | --- | --- |
| TRUE | FALSE | TRUE |

### 8.1. Kết hợp sự tồn tại với kiểu JSON

Muốn tách ba nhóm:

```sql
SELECT
    id,
    CASE
        WHEN doc IS NULL THEN 'SQL NULL document'
        WHEN jsonb_typeof(doc) <> 'object'
            THEN 'Root is not an object'
        WHEN NOT (doc ? 'email')
            THEN 'Missing email key'
        WHEN jsonb_typeof(doc -> 'email') = 'null'
            THEN 'Present JSON null'
        ELSE 'Present non-null JSON value'
    END AS email_state
FROM json_null_lab.documents
ORDER BY id;
```

Trong ví dụ này, thứ tự nhánh `CASE` rất quan trọng. Nếu không kiểm tra document SQL NULL và kiểu root trước, có thể gộp nhầm “không có object để tra” với “object có tồn tại nhưng thiếu khóa”.

### 8.2. ? không tìm sâu tự động

```sql
SELECT
    '{"profile":{"email":null}}'::jsonb ? 'email'
        AS top_level_email,
    '{"profile":{"email":null}}'::jsonb ? 'profile'
        AS top_level_profile,
    (
        '{"profile":{"email":null}}'::jsonb -> 'profile'
    ) ? 'email' AS nested_email;
```

Kết quả lần lượt FALSE, TRUE, TRUE. Toán tử `?` trên object kiểm tra **cấp của đối tượng đang nhận toán tử**.

### 8.3. ? còn có ngữ nghĩa với array

Với một JSONB array, `?` có thể kiểm tra **string array element** ở cấp ngoài cùng:

```sql
SELECT
    '["postgres","jsonb"]'::jsonb ? 'jsonb'
        AS has_string_element,
    '[null,"jsonb"]'::jsonb ? 'null'
        AS has_text_null,
    '["null"]'::jsonb ? 'null'
        AS has_string_null;
```

Kết quả là TRUE, FALSE, TRUE. `? 'null'` tìm chuỗi JSON `"null"`, **không** tìm literal JSON null. Đừng áp dụng ngữ nghĩa object key một cách mù quáng cho array.

### 8.4. Khi tài liệu là SQL NULL

```sql
SELECT NULL::jsonb ? 'email' AS exists_result;
```

Kết quả là **SQL NULL**, không phải FALSE. Nếu muốn một boolean nghiệp vụ “có field email trong object hay không”, có thể chuẩn hóa:

```sql
SELECT
    id,
    COALESCE(
        jsonb_typeof(doc) = 'object'
            AND doc ? 'email',
        FALSE
    ) AS has_email_field
FROM json_null_lab.documents
ORDER BY id;
```

Biểu thức này cố ý coi document SQL NULL và root không phải object là không có email. Đó là **quy tắc phân loại** dành cho ví dụ, không có nghĩa mọi SQL NULL đều về mặt dữ liệu tương đương object thiếu key.

### 8.5. ?| và ?&

PostgreSQL còn có toán tử cho kiểm tra nhiều khóa/chuỗi ở cấp ngoài cùng:

```sql
SELECT
    '{"email":null,"phone":"123"}'::jsonb
        ?| ARRAY['email','address'] AS has_any,
    '{"email":null,"phone":"123"}'::jsonb
        ?& ARRAY['email','phone'] AS has_all;
```

Hai kết quả TRUE. Những toán tử này kiểm tra sự hiện diện của key/string element, **không yêu cầu giá trị JSON khác null**.

## 9. Toán tử @>: JSONB containment và JSON null

`@>` kiểm tra JSONB bên trái **có chứa** cấu trúc JSONB bên phải theo quy tắc containment.

### 9.1. Object chứa JSON null

```sql
SELECT
    '{"email":null}'::jsonb
        @> '{"email":null}'::jsonb AS true_case,
    '{}'::jsonb
        @> '{"email":null}'::jsonb AS false_case,
    '{"email":"null"}'::jsonb
        @> '{"email":null}'::jsonb AS different_type;
```

Kết quả lần lượt TRUE, FALSE, FALSE.

Vì vậy predicate:

```sql
WHERE doc @> '{"email":null}'::jsonb
```

có thể xác định object có key email với **giá trị JSON null ở đúng vị trí yêu cầu**. Nó không chọn object thiếu email hoặc có email dạng chuỗi `"null"`.

### 9.2. Containment của object rỗng

```sql
SELECT
    '{}'::jsonb @> '{}'::jsonb AS empty_contains_empty,
    '{"email":null}'::jsonb @> '{}'::jsonb
        AS nonempty_contains_empty;
```

Cả hai TRUE. Vì thế:

```sql
WHERE doc @> '{}'::jsonb
```

**không đồng nghĩa** “document phải là object rỗng”. Nếu cần chính xác object rỗng:

```sql
WHERE doc = '{}'::jsonb
```

Trong đó SQL NULL không chọn dòng do phép bằng trả UNKNOWN.

### 9.3. Containment đối với path lồng nhau

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc @> '{"profile":{"email":null}}'::jsonb;
```

Trên dữ liệu lab, kết quả là **id=10**, không phải id=9 (profile không có email) hoặc id=11 (profile là JSON null).

### 9.4. Indexing có thể hỗ trợ containment

JSONB có thể dùng GIN index với operator class phù hợp cho một số truy vấn containment và existence:

```sql
CREATE INDEX idx_json_null_lab_doc_gin
ON json_null_lab.documents
USING GIN (doc);
```

Trên bảng 18 hàng, planner hoàn toàn có thể chọn Seq Scan, vì index traversal không đáng chi phí. Khi dùng GIN, `jsonb_ops` và `jsonb_path_ops` có tập toán tử được hỗ trợ **khác nhau**; đặc biệt `jsonb_path_ops` không hỗ trợ `?` kiểu key-exists như `jsonb_ops`. Thiết kế phải bám vào queries cần tối ưu, không mặc định mọi toán tử JSONB đều được mọi GIN operator class tăng tốc.

## 10. #> và #>>: trích xuất path lồng nhau

Hai toán tử:

```sql
document #>  '{profile,email}'
document #>> '{profile,email}'
```

tương ứng với lấy **giá trị JSON/JSONB** và lấy **text** tại một path gồm nhiều thành phần. Path viết dưới dạng `text[]`; PostgreSQL có thể nhận array literal như `'{profile,email}'` với ngữ cảnh kiểu phù hợp.

### 10.1. Path kết thúc ở JSON null

```sql
SELECT
    '{"profile":{"email":null}}'::jsonb
        #> '{profile,email}' AS email_json,
    '{"profile":{"email":null}}'::jsonb
        #>> '{profile,email}' AS email_text;
```

Kết quả `email_json` là JSONB null; `email_text` là SQL NULL.

### 10.2. Path không tồn tại

```sql
SELECT
    '{"profile":{}}'::jsonb
        #> '{profile,email}' AS missing_json,
    '{"profile":{}}'::jsonb
        #>> '{profile,email}' AS missing_text;
```

Cả hai là SQL NULL.

### 10.3. Thành phần trung gian là JSON null

```sql
SELECT
    '{"profile":null}'::jsonb
        #> '{profile,email}' AS nested_under_null,
    '{"profile":null}'::jsonb
        -> 'profile' AS profile_value;
```

Biểu thức đầu không thể đi tiếp đến email dưới một JSON scalar null nên trả SQL NULL; biểu thức thứ hai trả JSONB null hiện hữu tại key profile. Đây là một khác biệt cần ghi nhớ:

- **Path kết thúc** tại JSON null: trả JSON null với `#>`.
- **Path phải đi xuyên qua** JSON null đến thành phần tiếp theo: không tìm được giá trị con nên trả SQL NULL.

### 10.4. Không diễn giải mọi SQL NULL từ #> là field bị xóa

Kết quả SQL NULL có thể do:

- Document SQL NULL.
- Root có kiểu không phù hợp.
- Một key của path bị thiếu.
- Một intermediate value không phải object/array phù hợp.
- Chỉ số array không tồn tại.

Nếu API cần phân biệt chính xác các nguyên nhân, phải kiểm tra từng cấp thay vì chỉ `#> ... IS NULL`.

## 11. Tách hai câu hỏi: field có tồn tại và field có giá trị gì?

Với một object, hai câu hỏi độc lập:

1. **Field có được cung cấp không?**
2. **Nếu có, kiểu/giá trị của field là gì?**

Một query rõ ràng:

```sql
SELECT
    id,
    doc ? 'email' AS email_present,
    jsonb_typeof(doc -> 'email') AS email_type,
    doc ->> 'email' AS email_text
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
ORDER BY id;
```

Các trường hợp:

| Dữ liệu | `email_present` | `email_type` | `email_text` |
| --- | --- | --- | --- |
| `{}` | FALSE | SQL NULL | SQL NULL |
| `{"email":null}` | TRUE | Text `null` | SQL NULL |
| `{"email":"null"}` | TRUE | Text `string` | Text `null` |
| `{"email":""}` | TRUE | Text `string` | Chuỗi rỗng |
| `{"email":false}` | TRUE | Text `boolean` | Text `false` |

Lợi ích của việc hiển thị **cả ba thuộc tính** là code review và debug sẽ không mắc lỗi “thấy NULL ở cột text, kết luận người gửi đã chủ động đặt JSON null”.

### 11.1. Dùng CASE với thứ tự kiểm tra rõ ràng

```sql
SELECT
    id,
    CASE
        WHEN doc IS NULL THEN 'DOCUMENT_SQL_NULL'
        WHEN jsonb_typeof(doc) = 'null'
            THEN 'DOCUMENT_JSON_NULL'
        WHEN jsonb_typeof(doc) <> 'object'
            THEN 'DOCUMENT_NOT_OBJECT'
        WHEN NOT (doc ? 'email')
            THEN 'EMAIL_MISSING'
        WHEN jsonb_typeof(doc -> 'email') = 'null'
            THEN 'EMAIL_JSON_NULL'
        WHEN jsonb_typeof(doc -> 'email') = 'string'
            THEN 'EMAIL_STRING'
        ELSE 'EMAIL_OTHER_JSON_TYPE'
    END AS classification
FROM json_null_lab.documents
ORDER BY id;
```

Những tên trạng thái được tạo để phục vụ **ngữ nghĩa ứng dụng**; đây không phải enum được PostgreSQL định nghĩa sẵn.

### 11.2. Khi chỉ cần object có email không NULL

```sql
SELECT id, doc ->> 'email' AS email
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'string';
```

Câu này vẫn chọn text rỗng hoặc text `"null"` vì chúng thuộc kiểu string. Nếu nghiệp vụ yêu cầu email hợp lệ, cần validation về chuỗi rỗng/định dạng/normalization riêng. Kiểm tra JSON type **chưa phải** kiểm tra hợp lệ của địa chỉ email.

## 12. Mảng JSON: phần tử null khác chỉ số không tồn tại

Object dùng key; array dùng vị trí. Với:

```json
[null, "null", 0, false]
```

mảng có **bốn phần tử**, trong đó phần tử ở index 0 là JSON null.

### 12.1. Truy cập index

```sql
SELECT
    '[null,"null",0,false]'::jsonb -> 0 AS first_json,
    '[null,"null",0,false]'::jsonb -> 1 AS second_json,
    '[null,"null",0,false]'::jsonb -> 10 AS outside_json;
```

Kết quả:

- `-> 0`: JSONB null.
- `-> 1`: JSONB string `"null"`.
- `-> 10`: SQL NULL vì index ngoài phạm vi.

### 12.2. ->> với array mất sự phân biệt

```sql
SELECT
    '[null]'::jsonb ->> 0 AS present_json_null,
    '[null]'::jsonb ->> 5 AS missing_index,
    '["null"]'::jsonb ->> 0 AS string_null;
```

Hai giá trị đầu là SQL NULL; giá trị cuối là SQL text `null`.

### 12.3. Mảng rỗng và mảng chỉ có JSON null

```sql
SELECT
    jsonb_array_length('[]'::jsonb) AS empty_length,
    jsonb_array_length('[null]'::jsonb) AS one_null_length,
    jsonb_array_length('[null,null]'::jsonb)
        AS two_null_length;
```

Kết quả **0, 1, 2**. JSON null vẫn là **một phần tử có vị trí**; không được coi nó như “phần tử không tồn tại” rồi loại khỏi độ dài mảng.

### 12.4. Chỉ số âm

PostgreSQL hỗ trợ lấy phần tử array JSON bằng chỉ số âm tính từ cuối:

```sql
SELECT
    '[1,2,null]'::jsonb -> -1 AS last_json,
    '[1,2,null]'::jsonb -> -4 AS outside_json;
```

`-> -1` trả JSON null ở cuối; `-> -4` trả SQL NULL vì ngoài phạm vi. Đây là ngữ nghĩa của toán tử truy cập JSON trong PostgreSQL, **không áp nguyên sang cú pháp SQL array native**.

### 12.5. SQL array và JSON array là hai kiểu khác nhau

```sql
SELECT
    ARRAY[NULL::integer, 7] AS native_sql_array,
    '[null,7]'::jsonb AS json_array;
```

`ARRAY[NULL::integer,7]` là **mảng SQL integer** có một phần tử SQL NULL; `'[null,7]'::jsonb` là **giá trị JSONB array** có phần tử JSON null. Cả hai được hiển thị giống về ý tưởng nhưng dùng toán tử, indexing, kiểm tra kiểu và conversion khác nhau.

### 12.6. Không gọi jsonb_array_length lên object một cách mù quáng

`jsonb_array_length` yêu cầu giá trị JSONB kiểu array. Với object hoặc scalar không phù hợp, có thể báo lỗi, không phải luôn trả 0 hoặc SQL NULL.

Nếu input không được đảm bảo, kiểm tra:

```sql
SELECT id,
       CASE
           WHEN jsonb_typeof(doc) = 'array'
               THEN jsonb_array_length(doc)
           ELSE NULL
       END AS array_length_or_sql_null
FROM json_null_lab.documents
ORDER BY id;
```

CASE giúp tránh gọi hàm lên loại JSON không phù hợp trong luồng đơn giản này; phần tử array JSON null vẫn được tính vào length.

## 13. Logic ba giá trị của SQL: TRUE, FALSE và UNKNOWN

SQL có logic ba giá trị khi đánh giá nhiều biểu thức boolean: **TRUE**, **FALSE** và **UNKNOWN** (trên kết quả SQL thường được biểu diễn bằng NULL). Đây là lý do một phép so sánh giữa SQL NULL và một giá trị không trả FALSE.

### 13.1. So sánh với SQL NULL

```sql
SELECT
    NULL::jsonb = 'null'::jsonb AS compare_equal,
    NULL::jsonb <> 'null'::jsonb AS compare_not_equal,
    NULL::jsonb IS NULL AS sql_null_check;
```

Hai biểu thức so sánh đầu là SQL NULL/UNKNOWN; biểu thức thứ ba TRUE.

Đối với JSON null **không phải SQL NULL**, phép so sánh jsonb bình thường có thể trả TRUE/FALSE:

```sql
SELECT
    'null'::jsonb = 'null'::jsonb AS both_json_null,
    '"null"'::jsonb = 'null'::jsonb AS string_vs_null,
    'false'::jsonb = 'null'::jsonb AS boolean_vs_null;
```

Kết quả TRUE, FALSE, FALSE.

### 13.2. WHERE chỉ giữ những dòng có predicate TRUE

Giả sử:

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc -> 'email' <> 'null'::jsonb;
```

Đây **không phải** truy vấn “mọi document trừ document có email JSON null”. Với key email missing hoặc document SQL NULL, biểu thức `doc -> 'email'` là SQL NULL; so sánh khác `<>` trả UNKNOWN nên dòng không được chọn.

Nếu muốn chọn **mọi object có email tồn tại và khác JSON null**:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND doc -> 'email' <> 'null'::jsonb;
```

Nếu muốn chọn object **thiếu email hoặc có email khác JSON null**:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND (
      NOT (doc ? 'email')
      OR doc -> 'email' <> 'null'::jsonb
  );
```

Hai câu trả lời hai câu hỏi khác nhau; không có điều kiện duy nhất “loại bỏ null” đúng cho mọi nghiệp vụ.

### 13.3. AND, OR và UNKNOWN

Một số kết quả quan trọng:

| Biểu thức logic | Kết quả |
| --- | --- |
| TRUE AND UNKNOWN | UNKNOWN |
| FALSE AND UNKNOWN | FALSE |
| TRUE OR UNKNOWN | TRUE |
| FALSE OR UNKNOWN | UNKNOWN |
| NOT UNKNOWN | UNKNOWN |

Vì vậy `WHERE (doc->>'email' = 'a@example.com') OR FALSE` không chọn document có email JSON null/missing, còn `OR TRUE` thì chọn mọi dòng. Đây là logic SQL, không phải hành vi riêng của JSONB.

### 13.4. IS DISTINCT FROM cho so sánh NULL-safe

`IS DISTINCT FROM` xử lý SQL NULL như một giá trị riêng cho mục đích so sánh khác nhau, trả boolean TRUE/FALSE thay vì UNKNOWN:

```sql
SELECT
    NULL::jsonb IS DISTINCT FROM 'null'::jsonb
        AS sql_vs_json_null,
    NULL::jsonb IS NOT DISTINCT FROM NULL::jsonb
        AS two_sql_nulls,
    'null'::jsonb IS NOT DISTINCT FROM 'null'::jsonb
        AS two_json_nulls;
```

Cả ba trả TRUE.

Muốn phân biệt rõ kết quả truy xuất:

```sql
SELECT
    id,
    doc -> 'email' IS DISTINCT FROM 'null'::jsonb
        AS differs_from_json_null
FROM json_null_lab.documents
ORDER BY id;
```

Biểu thức này trả TRUE **cả khi email missing** (do SQL NULL khác giá trị JSONB null) lẫn khi email là giá trị JSON khác null; nó không kiểm tra key có tồn tại.

### 13.5. IS NULL trên giá trị JSON và trên text khác nhau

```sql
SELECT
    ('{"k":null}'::jsonb -> 'k') IS NULL
        AS json_extraction_is_sql_null,
    ('{"k":null}'::jsonb ->> 'k') IS NULL
        AS text_extraction_is_sql_null;
```

Kết quả FALSE, TRUE.

**Đây là một phép thử ngắn rất hữu ích khi review câu SQL xử lý JSON.**

## 14. COALESCE: tiện lợi nhưng dễ làm mất khác biệt

`COALESCE(x, default)` trả phần tử **không phải SQL NULL** đầu tiên. Nó **không coi JSONB null là SQL NULL**.

### 14.1. COALESCE với ->: JSON null vẫn được giữ

```sql
SELECT
    COALESCE(
        '{"email":null}'::jsonb -> 'email',
        '"fallback"'::jsonb
    ) AS json_null_preserved,
    COALESCE(
        '{}'::jsonb -> 'email',
        '"fallback"'::jsonb
    ) AS missing_replaced;
```

Kết quả:

- `json_null_preserved` = JSONB null.
- `missing_replaced` = JSONB string `"fallback"`.

Vì giá trị JSONB null đã **hiện hữu**, COALESCE không thay thế nó.

### 14.2. COALESCE với ->>: missing và JSON null cùng fallback

```sql
SELECT
    COALESCE(
        '{"email":null}'::jsonb ->> 'email',
        '<fallback>'
    ) AS json_null_fallback,
    COALESCE(
        '{}'::jsonb ->> 'email',
        '<fallback>'
    ) AS missing_fallback;
```

Cả hai trả text `<fallback>`. Nếu chỉ lưu kết quả, bạn đã **làm mất thông tin field có được gửi hay không**.

### 14.3. Không sử dụng COALESCE trước khi quyết định nghiệp vụ

Ví dụ câu lệnh:

```sql
UPDATE customer_profiles
SET email = COALESCE(
    :payload::jsonb ->> 'email',
    email
);
```

được đưa ra như **mẫu minh họa**, không chạy vì chưa có bảng/bind parameters. Nó mang ngữ nghĩa “nếu email thiếu hoặc JSON null, giữ email cũ”, **không** cho phép người dùng chủ động xóa email bằng cách gửi JSON null.

Nếu yêu cầu là:

- Missing → giữ nguyên.
- JSON null → xóa giá trị (SQL NULL).
- JSON string → cập nhật text.

thì phải kiểm tra key presence trước rồi xử lý JSON null riêng.

### 14.4. COALESCE và giá trị chuỗi "null"

`{"email":"null"}` qua `->>` tạo SQL text `null` **không phải SQL NULL**, nên COALESCE **không thay** bằng fallback.

Đừng viết `NULLIF(email_text,'null')` trừ khi nghiệp vụ thật sự muốn coi chuỗi `null` là giá trị đặc biệt. Việc gộp literal text với NULL có thể phá dữ liệu hợp lệ.

## 15. Phân loại đầy đủ bằng CASE trước khi chuẩn hóa

Để giữ trọn ý nghĩa ba trạng thái, hãy phân loại trước:

```sql
SELECT
    id,
    CASE
        WHEN doc IS NULL
            THEN 'SQL_NULL_DOCUMENT'
        WHEN jsonb_typeof(doc) <> 'object'
            THEN 'NOT_AN_OBJECT'
        WHEN NOT (doc ? 'email')
            THEN 'MISSING'
        WHEN jsonb_typeof(doc -> 'email') = 'null'
            THEN 'JSON_NULL'
        WHEN jsonb_typeof(doc -> 'email') = 'string'
             AND doc ->> 'email' = ''
            THEN 'EMPTY_STRING'
        WHEN jsonb_typeof(doc -> 'email') = 'string'
            THEN 'STRING'
        ELSE 'OTHER_JSON_VALUE'
    END AS email_state,
    doc ->> 'email' AS email_as_text
FROM json_null_lab.documents
ORDER BY id;
```

### 15.1. Bảng tình huống

| ID | Trạng thái dự kiến |
| ---: | --- |
| 1 | `SQL_NULL_DOCUMENT` |
| 2 | `NOT_AN_OBJECT` |
| 3 | `MISSING` |
| 4 | `JSON_NULL` |
| 5 | `STRING` |
| 6 | `EMPTY_STRING` |
| 7 | `STRING` |
| 8 | `OTHER_JSON_VALUE` |
| 9–12 | `MISSING` vì email không có ở top-level |
| 13–16 | `NOT_AN_OBJECT` |
| 17–18 | `OTHER_JSON_VALUE` |

Với mục tiêu phân loại **email top-level**, những object chứa `profile.email` nhưng không có `email` top-level đúng là MISSING. Nếu nghiệp vụ cần profile.email, phải dùng path tương ứng.

### 15.2. Vì sao CASE có lợi?

- Quy định rõ thứ tự ưu tiên của các trạng thái.
- Không lệ thuộc vào hiển thị NULL của công cụ SQL.
- Dễ kiểm thử đầu vào của API.
- Tránh gộp nhầm các trường hợp trong `COALESCE`.
- Cho phép định nghĩa mapping có chủ đích sang kiểu dữ liệu ứng dụng.

### 15.3. Phân biệt “có giá trị” với “hợp lệ”

Nếu email là số 0 hoặc object rỗng, nó **có tồn tại và không phải JSON null**, nhưng không phải địa chỉ email hợp lệ. Truy vấn xác định presence/nullness không thay thế validation định dạng, độ dài, Unicode hay quy tắc tên miền.

## 16. jsonb_each và jsonb_each_text: khi bung object thành nhiều hàng

PostgreSQL hỗ trợ duyệt cặp key/value trong JSONB object:

```sql
SELECT key, value, jsonb_typeof(value) AS json_type
FROM jsonb_each(
    '{"a":null,"b":"null","c":false}'::jsonb
)
ORDER BY key;
```

Kết quả logic:

| key | value (JSONB) | json_type |
| --- | --- | --- |
| `a` | JSON null | Text `null` |
| `b` | JSON string `"null"` | Text `string` |
| `c` | JSON boolean false | Text `boolean` |

### 16.1. Missing key không sinh hàng

Với `jsonb_each('{}'::jsonb)`, kết quả là **0 hàng**, không phải một hàng có key=NULL và value=NULL. Đây là khác biệt giữa:

- Một key tồn tại với JSON null → có hàng duyệt key, value là JSONB null.
- Key không tồn tại → không có hàng tương ứng.

### 16.2. jsonb_each_text chuyển JSON null sang SQL NULL

```sql
SELECT key, value, value IS NULL AS is_sql_null
FROM jsonb_each_text(
    '{"a":null,"b":"null"}'::jsonb
)
ORDER BY key;
```

Với `a`, value là SQL NULL. Với `b`, value là SQL text `null`. Dù `jsonb_each_text` giữ được **key** trong tập hàng, riêng cột text value không còn mang kiểu JSON gốc.

### 16.3. Với cột doc chưa chắc là object

`jsonb_each` yêu cầu root là object; gọi trực tiếp lên JSON array/scalar có thể báo lỗi. Có thể minh họa an toàn:

```sql
SELECT
    d.id,
    p.key,
    p.value,
    jsonb_typeof(p.value) AS value_type
FROM json_null_lab.documents AS d
LEFT JOIN LATERAL jsonb_each(
    CASE
        WHEN jsonb_typeof(d.doc) = 'object'
            THEN d.doc
        ELSE '{}'::jsonb
    END
) AS p(key, value)
    ON TRUE
ORDER BY d.id, p.key;
```

Với `LEFT JOIN LATERAL`, document không có cặp key/value có thể sinh **hàng đệm** với `p.key` và `p.value` là SQL NULL. Không diễn giải hàng đệm ấy là một key thực có JSON null; phải dùng `p.key IS NOT NULL` để nhận biết row thật từ `jsonb_each`.

### 16.4. Khi nào nên duyệt object?

Duyệt key/value hữu ích khi:

- Audit field nào được gửi.
- Thực thi validation theo danh sách field được phép.
- Xây báo cáo thống kê về JSON field presence.
- Biến JSON object sang quan hệ cho một bước ETL.

Nhưng nếu cấu trúc JSON rất lớn và query chạy trên hàng triệu rows, việc bung hết keys có thể tốn CPU/bộ nhớ. Khi chỉ cần một field cụ thể, toán tử `?`/`->` thường đơn giản hơn.

## 17. JSONPath: tồn tại path khác với giá trị của path

Từ PostgreSQL 12, các kiểu/toán tử SQL/JSON path cho phép tìm đường dẫn trong JSONB. Một cách biểu đạt trực tiếp:

```sql
SELECT
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email'
    ) AS present_null,
    jsonb_path_exists(
        '{}'::jsonb,
        '$.email'
    ) AS missing;
```

Kết quả TRUE và FALSE. **Path tồn tại** ngay cả khi giá trị kết thúc path là JSON null.

### 17.1. Kiểm tra JSON null bằng filter JSONPath

```sql
SELECT
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email ? (@ == null)'
    ) AS explicit_null,
    jsonb_path_exists(
        '{}'::jsonb,
        '$.email ? (@ == null)'
    ) AS missing_null;
```

Kết quả TRUE và FALSE. Predicate `@ == null` ở đây là **JSONPath comparison với JSON null**, không phải SQL so sánh `= NULL`.

### 17.2. JSONPath trên path nested

```sql
SELECT
    id,
    jsonb_path_exists(
        doc,
        '$.profile.email'
    ) AS nested_email_present,
    jsonb_path_exists(
        doc,
        '$.profile.email ? (@ == null)'
    ) AS nested_email_json_null
FROM json_null_lab.documents
WHERE id IN (9, 10, 11, 12)
ORDER BY id;
```

Với dữ liệu lab:

- ID 9: profile là object rỗng → nested email không tồn tại.
- ID 10: nested email tồn tại, có JSON null.
- ID 11: profile là JSON null, không có child email để tìm.
- ID 12: nested email tồn tại, là string.

### 17.3. SQL NULL document khi dùng JSONPath

Nếu truyền `NULL::jsonb` vào `jsonb_path_exists`, kết quả theo tính nghiêm ngặt NULL của hàm là SQL NULL, không phải một boolean FALSE về field membership. Nếu nghiệp vụ muốn coi document SQL NULL như một object không có path, phải chọn quy tắc rõ, ví dụ `COALESCE(jsonb_path_exists(doc,'$.email'),FALSE)`.

### 17.4. Lax và strict path evaluation

JSONPath của PostgreSQL có mode mặc định dạng **lax** và tùy chọn **strict** với cách xử lý/khả năng phát sinh lỗi khác nhau khi cấu trúc không đúng. Mặc định lax có thể bỏ qua/suy giảm một số lỗi cấu trúc và tự điều chỉnh truy cập ở những tình huống phù hợp.

Nếu muốn validation schema chặt chẽ, đừng chỉ dựa vào một path expression lax rồi kết luận dữ liệu có đúng loại object/array. Kiểm tra `jsonb_typeof` tại các cấp cần thiết và chọn strict behavior theo nhu cầu.

### 17.5. @? và @@ không cùng ý nghĩa

PostgreSQL có những toán tử JSONPath như `@?` và `@@` với ngữ nghĩa:

- `@?`: đường dẫn có cho ra mục phù hợp hay không.
- `@@`: kiểm tra kết quả của JSONPath predicate.

Chúng không hoàn toàn thay thế nhau cho mọi biểu thức. Một điều kiện thử path existence:

```sql
SELECT
    '{"email":null}'::jsonb @? '$.email'
        AS has_email_path,
    '{}'::jsonb @? '$.email'
        AS no_email_path;
```

Kết quả TRUE và FALSE trong trường hợp này.

### 17.6. Dùng JSONPath khi nào?

Với một key top-level, `doc ? 'email'` thường dễ đọc. JSONPath hữu ích khi cấu trúc lồng nhau hoặc array phức tạp, cần tìm “có phần tử thỏa điều kiện ở sâu trong document” và khi chọn toán tử/GIN index phù hợp.

Chọn công cụ đơn giản nhất đáp ứng semantics thay vì biến mọi phép kiểm tra email thành một JSONPath expression dài.

## 18. jsonb_to_record và jsonb_populate_record: khi chuyển JSON thành cột SQL

Khi JSON được chuyển thành một record typed, JSON null có thể trở thành **SQL NULL** trong cột đích.

### 18.1. Hai payload cho cùng một kết quả typed

```sql
SELECT *
FROM jsonb_to_record(
    '{"email":null}'::jsonb
) AS x(email text);

SELECT *
FROM jsonb_to_record(
    '{}'::jsonb
) AS x(email text);
```

Hai câu đều cho cột `email` = **SQL NULL**. Một bên trường có mặt với JSON null, bên còn lại không có trường. Khi đã chuyển vào một cột nullable đơn thuần, **presence bit đã mất**.

### 18.2. Muốn giữ thông tin presence, lấy riêng trước

```sql
SELECT
    d.id,
    d.doc ? 'email' AS email_was_provided,
    x.email
FROM json_null_lab.documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    CASE
        WHEN jsonb_typeof(d.doc) = 'object'
            THEN d.doc
        ELSE '{}'::jsonb
    END
) AS x(email text)
WHERE d.id IN (3, 4, 5, 6, 7)
ORDER BY d.id;
```

Lúc này:

- `email_was_provided=FALSE`, `x.email=SQL NULL` → missing.
- `email_was_provided=TRUE`, `x.email=SQL NULL` → explicit JSON null.
- `email_was_provided=TRUE`, `x.email='null'` → JSON string literal "null".

### 18.3. jsonb_populate_record với base record

`jsonb_populate_record(base, jsonb)` có semantics quan trọng: giá trị từ JSON được chuyển sang các cột typed; field JSON null thành SQL NULL. Với field **không xuất hiện**, giá trị của base record có thể được giữ nếu base được cung cấp; nếu base là SQL NULL record, field missing kết quả thường là SQL NULL.

Vì vậy, dùng `jsonb_populate_record` cho update có thể mang semantics khác việc tự viết `doc ->> ...` theo từng field. Cần xác định rõ muốn “missing giữ cũ” hay “missing thành NULL”.

### 18.4. Conversion không đồng nghĩa validation đầy đủ

JSON string, number, boolean hoặc object có thể được chuyển sang SQL type theo những quy tắc cast/coercion; dữ liệu không tương thích có thể báo lỗi. Kiểm tra kiểu JSON và định dạng nghiệp vụ trước khi giả định `jsonb_to_record` an toàn với mọi payload.

Đặc biệt, việc ghi vào cột `text` không thể đảm bảo giá trị là email hợp lệ, chỉ vì phép chuyển kiểu thành công.

## 19. Cập nhật JSONB: đặt null không giống xóa khóa

Khi một document đang có:

```json
{"email":"old@example.com","active":true}
```

ta có ít nhất ba thao tác khác nhau:

1. Đổi email thành chuỗi mới.
2. Giữ khóa email nhưng đổi giá trị thành **JSON null**.
3. **Xóa khóa email** khỏi object.

PostgreSQL có những toán tử/hàm riêng cho từng việc.

### 19.1. Đặt khóa thành JSON null bằng jsonb_set

```sql
SELECT jsonb_set(
    '{"email":"old@example.com","active":true}'::jsonb,
    '{email}',
    'null'::jsonb,
    true
) AS result;
```

Kết quả tương đương:

```json
{"active": true, "email": null}
```

Khóa email **vẫn tồn tại**. Trật tự hiển thị keys của jsonb không phải một phần ngữ nghĩa JSON object và có thể khác ví dụ.

### 19.2. Xóa khóa bằng toán tử -

```sql
SELECT
    '{"email":"old@example.com","active":true}'::jsonb
        - 'email' AS result;
```

Kết quả:

```json
{"active": true}
```

Toán tử `- 'email'` trên JSONB object xóa key ở **cấp ngoài cùng**. Không chỉ đặt value thành JSON null.

### 19.3. Đặt field thiếu thành JSON null

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{email}',
    'null'::jsonb,
    true
) AS result;
```

Kết quả `{"email":null}`. Tham số cuối `true` cho phép tạo phần tử path cuối khi phù hợp.

Nếu dùng `false`:

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{email}',
    'null'::jsonb,
    false
) AS result;
```

Kết quả vẫn là `{}` vì field cuối không tồn tại và không được phép tạo mới.

### 19.4. Cẩn thận new_value là SQL NULL

```sql
SELECT jsonb_set(
    '{"email":"old@example.com"}'::jsonb,
    '{email}',
    NULL::jsonb,
    true
) AS result;
```

Với `jsonb_set`, **SQL NULL new_value** không tương đương JSON null; lời gọi hàm theo ngữ nghĩa NULL đầu vào có thể cho ra **SQL NULL toàn biểu thức**, chứ không phải object chứa email JSON null.

Nếu dùng biểu thức đó để cập nhật cột `doc jsonb NOT NULL`, câu UPDATE có thể vi phạm constraint hoặc làm mất cả document nếu cột nullable. Khi muốn JSON null, truyền **`'null'::jsonb`**.

### 19.5. Path lồng nhau và thành phần trung gian

```sql
SELECT jsonb_set(
    '{"profile":{"email":"old@example.com"}}'::jsonb,
    '{profile,email}',
    'null'::jsonb,
    true
) AS result;
```

Đổi profile.email thành JSON null.

Nhưng:

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{profile,email}',
    '"new@example.com"'::jsonb,
    true
) AS result;
```

không có nghĩa `jsonb_set` luôn tự tạo **mọi intermediate object** còn thiếu. Với path không tồn tại ở bước trung gian, PostgreSQL có thể giữ nguyên target thay vì tạo cả cấu trúc `profile`.

Nếu cần thiết lập nested object từ chỗ chưa có, phải xây dựng path cha một cách rõ ràng và tính đến trường hợp path cha là scalar/JSON null.

## 20. jsonb_set_lax: điều khiển rõ SQL NULL new_value

Từ PostgreSQL 13, `jsonb_set_lax` mở rộng `jsonb_set` để xử lý tình huống đối số `new_value` là **SQL NULL** với lựa chọn hành vi được khai báo tường minh.

### 20.1. Các chế độ thường dùng

Với JSONB object:

```sql
SELECT
    jsonb_set_lax(
        '{"email":"old@example.com"}'::jsonb,
        '{email}',
        NULL::jsonb,
        true,
        'use_json_null'
    ) AS set_json_null,

    jsonb_set_lax(
        '{"email":"old@example.com"}'::jsonb,
        '{email}',
        NULL::jsonb,
        true,
        'delete_key'
    ) AS remove_key,

    jsonb_set_lax(
        '{"email":"old@example.com"}'::jsonb,
        '{email}',
        NULL::jsonb,
        true,
        'return_target'
    ) AS unchanged;
```

Kết quả tương ứng:

| Mode | Hiệu ứng |
| --- | --- |
| `use_json_null` | Field email có JSON null. |
| `delete_key` | Field email bị xóa. |
| `return_target` | Target giữ nguyên. |
| `raise_exception` | Báo lỗi khi new_value SQL NULL. |

### 20.2. Điểm khác biệt quan trọng

- `jsonb_set(..., 'null'::jsonb)`: new_value **JSON null**, thực hiện cập nhật như JSON value.
- `jsonb_set_lax(..., NULL::jsonb, ..., 'use_json_null')`: new_value **SQL NULL**, được diễn giải có chủ đích thành JSON null.
- `jsonb_set_lax(..., NULL::jsonb, ..., 'delete_key')`: new_value **SQL NULL**, được diễn giải thành yêu cầu xóa phần tử.

`jsonb_set_lax` không tự biết nghiệp vụ muốn xóa hay giữ; mode do người viết SQL chọn. Nếu `new_value` **không phải SQL NULL**, nó thường hành xử như `jsonb_set` tương ứng, bất kể mode.

### 20.3. Không dùng trên phiên bản không hỗ trợ

Nếu server PostgreSQL cũ hơn 13, không có `jsonb_set_lax`. Khi đó cần dùng `CASE` và các thao tác `jsonb_set`/`-`/`#-` tương ứng, không sao chép cú pháp mới rồi giả định mọi major đều hỗ trợ.

## 21. Xóa nested path bằng #- và bỏ JSON null bằng jsonb_strip_nulls

### 21.1. Xóa nested key

```sql
SELECT
    '{"profile":{"email":null,"phone":"123"},"active":true}'::jsonb
        #- '{profile,email}' AS result;
```

Kết quả:

```json
{"active": true, "profile": {"phone": "123"}}
```

`#-` xóa giá trị tại path chỉ định, khác `#>` là trích xuất.

### 21.2. jsonb_strip_nulls

PostgreSQL có hàm loại các **object fields có giá trị JSON null**:

```sql
SELECT jsonb_strip_nulls(
    '{"email":null,"profile":{"phone":null,"name":"Lan"},"items":[null,1]}'::jsonb
) AS result;
```

Với dạng gọi một tham số phổ biến, kết quả có ý nghĩa:

```json
{"profile":{"name":"Lan"},"items":[null,1]}
```

Hàm xóa các trường null trong object, kể cả object lồng nhau, nhưng **mặc định không xem JSON null trong array là object field cần xóa**. Một số major mới có tùy chọn bổ sung để kiểm soát xử lý mảng; khi dùng phải đọc tài liệu của major cụ thể.

### 21.3. Trường hợp top-level JSON null

`jsonb_strip_nulls('null'::jsonb)` không tự biến toàn bộ JSON scalar null thành SQL NULL hoặc object rỗng. Công dụng chính là xóa **các cặp key/value** mà value JSON null trong những object.

### 21.4. Cẩn thận khi chuẩn hóa inbound payload

Nếu hệ thống chạy `jsonb_strip_nulls` **ngay khi nhận dữ liệu API**:

```json
{"email":null}
```

có thể biến thành:

```json
{}
```

và làm mất khác biệt giữa “client chủ động gửi JSON null” với “client không gửi email”. Chỉ strip nulls khi đó là **quy tắc nghiệp vụ đã được xác nhận**.

## 22. COUNT, COUNT(*), DISTINCT và aggregate với JSON null

Một dạng lỗi khó nhận ra là thống kê số lượng phần tử có mặt.

### 22.1. COUNT bỏ SQL NULL nhưng không bỏ JSONB null

Trong PostgreSQL:

- `COUNT(*)` đếm mọi dòng đầu vào.
- `COUNT(expression)` đếm số dòng có expression **không phải SQL NULL**.

Với cột `doc`:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(doc) AS non_sql_null_documents
FROM json_null_lab.documents;
```

Trên dữ liệu 18 dòng: `COUNT(*)=18` và `COUNT(doc)=17` vì chỉ id=1 có SQL NULL document. **ID=2 là JSON null và vẫn được COUNT(doc) đếm**.

### 22.2. COUNT theo -> khác COUNT theo ->>

```sql
SELECT
    COUNT(doc -> 'email') AS json_value_count,
    COUNT(doc ->> 'email') AS text_value_count
FROM json_null_lab.documents;
```

Trong bảng lab nguyên trạng:

- `COUNT(doc -> 'email')=7`: các id 4, 5, 6, 7, 8, 17, 18 có email top-level; **JSON null id=4 được đếm**.
- `COUNT(doc ->> 'email')=6`: tất cả như trên trừ id=4, vì JSON null chuyển thành SQL NULL khi dùng `->>`.

Hai COUNT này trả lời hai câu hỏi khác nhau:

1. Có bao nhiêu **giá trị JSON tại field** mà biểu thức `->` trả không phải SQL NULL?
2. Có bao nhiêu **biểu diễn text không SQL NULL**?

### 22.3. Đếm presence bằng ? với điều kiện object

```sql
SELECT
    COUNT(*) FILTER (
        WHERE jsonb_typeof(doc) = 'object'
          AND doc ? 'email'
    ) AS email_field_present,
    COUNT(*) FILTER (
        WHERE jsonb_typeof(doc) = 'object'
          AND jsonb_typeof(doc -> 'email') = 'null'
    ) AS email_explicit_json_null
FROM json_null_lab.documents;
```

Kết quả với lab là 7 và 1.

### 22.4. COUNT(DISTINCT ...) không phục hồi missing

```sql
SELECT COUNT(DISTINCT doc -> 'email')
FROM json_null_lab.documents;
```

Hàm tổng hợp loại SQL NULL của expression, đồng thời coi JSONB null là một giá trị có thể phân biệt với JSON string `"null"`. Nhưng missing và SQL NULL document đều đã thành SQL NULL của expression, không thể tách lại chỉ từ kết quả này.

### 22.5. Aggregate JSON có thể gộp biểu diễn

Khi đưa dữ liệu từ SQL sang JSON qua hàm xây dựng JSON, SQL NULL **có thể được biểu diễn thành JSON null** trong object/array đầu ra. Nếu ứng dụng cần bảo toàn khác biệt “field không được cung cấp” và “field được cung cấp với null”, cần lưu riêng metadata/presence hoặc chủ động loại key khi serialization.

Đừng suy luận rằng thấy `null` trong JSON response là đủ biết nguồn dữ liệu ban đầu là JSON null chứ không phải SQL NULL.

## 23. Xây JSON từ SQL: null trong kết quả không tiết lộ nguồn gốc

Ví dụ:

```sql
SELECT
    jsonb_build_object(
        'email', NULL::text
    ) AS from_sql_null,
    jsonb_build_object(
        'email', 'null'::jsonb
    ) AS from_json_null,
    jsonb_build_object(
        'email', 'null'::text
    ) AS from_text_null;
```

Ba kết quả tương ứng:

```json
{"email":null}
```

```json
{"email":null}
```

```json
{"email":"null"}
```

Hai trường hợp đầu **có JSON output giống nhau**, dù giá trị nguồn lần lượt là SQL NULL và JSON null. Khi xây JSON response, nếu đã chọn biểu diễn cả hai thành `{"email":null}`, thông tin nguồn gốc đã bị gộp; không thể suy ra ngược từ response.

### 23.1. Bỏ key nếu thiếu là quyết định của ứng dụng

Một cách xây output có điều kiện:

```sql
SELECT
    CASE
        WHEN TRUE
            THEN jsonb_build_object('email', 'a@example.com')
        ELSE '{}'::jsonb
    END AS object_with_email;
```

`CASE` này chỉ minh họa cấu trúc: khi field không được cung cấp, output có thể là `{}` thay vì `{"email":null}`. Điều kiện thật phải lấy từ metadata **presence**, không phải cố suy diễn từ một giá trị text nullable đã qua `->>`.

### 23.2. Bảo toàn hình dạng đầu ra

Nếu giao diện cần biết sự khác nhau giữa “không có field” và “field có null”, API cần thiết kế schema response/payload nhất quán. Có hai hướng:

- Giữ nguyên object JSONB với sự hiện diện của key khi trả dữ liệu.
- Trả dữ liệu typed cộng metadata về fields đã được cung cấp.

Không nên tùy tiện xóa tất cả null khi xuất response nếu clients dựa vào null để hiển thị trạng thái “chưa xác minh”.

## 24. SQL NULL column so với JSON null column trong INSERT/UPDATE

Một cột `jsonb` có thể nhận:

```sql
INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    (19, 'Explicit SQL NULL', NULL::jsonb),
    (20, 'Explicit JSON null', 'null'::jsonb);
```

Hai row có trạng thái khác nhau:

```sql
SELECT
    id,
    doc IS NULL AS sql_null,
    doc = 'null'::jsonb AS json_null
FROM json_null_lab.documents
WHERE id IN (19, 20);
```

Đây là phần lab **tùy chọn**, nếu chạy thì các COUNT ở phần 22 không còn dựa trên 18 row ban đầu. Để thử mà không đổi dataset:

```sql
BEGIN;

INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    (21, 'SQL NULL within transaction', NULL::jsonb),
    (22, 'JSON null within transaction', 'null'::jsonb);

SELECT
    id,
    doc IS NULL AS is_sql_null,
    jsonb_typeof(doc) AS json_type
FROM json_null_lab.documents
WHERE id IN (21, 22);

ROLLBACK;
```

Nếu muốn giữ lab gốc đúng 18 hàng, **chỉ chạy phiên bản BEGIN/ROLLBACK**, không chạy ví dụ INSERT 19–20 trước đó.

### 24.1. NOT NULL không loại JSON null

```sql
CREATE TABLE json_null_lab.required_docs (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL
);

INSERT INTO json_null_lab.required_docs (id, doc)
VALUES (1, 'null'::jsonb);
```

Lệnh hợp lệ. `NOT NULL` cấm **SQL NULL**, không cấm JSON scalar null. Nếu nghiệp vụ muốn document luôn là object, cần thêm constraint kiểm tra JSON type.

### 24.2. DEFAULT '{}' không xóa được JSON null đầu vào

```sql
CREATE TABLE json_null_lab.default_docs (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL DEFAULT '{}'::jsonb
);

INSERT INTO json_null_lab.default_docs (id)
VALUES (1);

INSERT INTO json_null_lab.default_docs (id, doc)
VALUES (2, 'null'::jsonb);
```

ID=1 nhận object rỗng theo DEFAULT; id=2 nhận JSON null vì client **đã gửi giá trị**. DEFAULT không thay explicit JSON null bằng object rỗng, cũng không thay explicit SQL NULL nếu cột NOT NULL — trường hợp sau sẽ lỗi.

## 25. CHECK constraints: lỗi UNKNOWN làm dữ liệu lọt kiểm tra

Trong PostgreSQL, `CHECK` không từ chối một row khi biểu thức là SQL NULL/UNKNOWN; nó từ chối khi biểu thức đánh giá thành **FALSE**. Đây là lý do nhiều biểu thức JSON validation tưởng đúng nhưng chưa đủ.

### 25.1. Constraint sai: chỉ kiểm tra text khác rỗng

Ví dụ:

```sql
CREATE TABLE json_null_lab.bad_profiles (
    id integer PRIMARY KEY,
    doc jsonb,
    CHECK (doc ->> 'email' <> '')
);
```

Constraint này **không bảo đảm email tồn tại**. Với `doc='{}'::jsonb` hoặc `doc='{"email":null}'::jsonb`:

- `doc ->> 'email'` là SQL NULL.
- `SQL_NULL <> ''` là UNKNOWN.
- `CHECK` có thể **chấp nhận row** vì không FALSE.

Nó cũng không ngăn cả document SQL NULL nếu không có `NOT NULL`.

### 25.2. Constraint rõ ràng cho required nonempty email

```sql
CREATE TABLE json_null_lab.validated_profiles (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CONSTRAINT ck_document_is_object
        CHECK (jsonb_typeof(doc) = 'object'),
    CONSTRAINT ck_email_required_string
        CHECK (
            doc ? 'email'
            AND jsonb_typeof(doc -> 'email') = 'string'
            AND length(doc ->> 'email') > 0
        )
);
```

Ở đây:

1. `NOT NULL` cấm SQL NULL document.
2. Constraint object cấm JSON null document, array, scalar.
3. `doc ? 'email'` yêu cầu khóa hiện diện.
4. `jsonb_typeof(...)= 'string'` cấm JSON null/number/boolean/object ở email.
5. `length(...) > 0` cấm text rỗng.

Validation email thật vẫn cần quy tắc định dạng phù hợp. SQL constraint trên chỉ minh họa sự khác biệt của các trạng thái.

### 25.3. Email optional nhưng nếu có thì phải là string hoặc JSON null

```sql
CREATE TABLE json_null_lab.optional_profiles (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CONSTRAINT ck_optional_doc_object
        CHECK (jsonb_typeof(doc) = 'object'),
    CONSTRAINT ck_optional_email_type
        CHECK (
            NOT (doc ? 'email')
            OR jsonb_typeof(doc -> 'email')
                IN ('string', 'null')
        )
);
```

Phép kiểm tra này cho phép:

- `{}` — email missing.
- `{"email":null}` — JSON null được phép.
- `{"email":"a@example.com"}` — string được phép.

Và từ chối `{"email":false}` hoặc `{"email":0}`. Nó không yêu cầu email phải luôn có.

### 25.4. Thử một số INSERT

```sql
INSERT INTO json_null_lab.optional_profiles (id, doc)
VALUES
    (1, '{}'::jsonb),
    (2, '{"email":null}'::jsonb),
    (3, '{"email":"a@example.com"}'::jsonb);
```

Nếu thử nhập boolean:

```sql
-- Dự kiến vi phạm CHECK, không chạy giữa một transaction
-- đang thực hiện công việc khác:
-- INSERT INTO json_null_lab.optional_profiles
-- VALUES (4, '{"email":false}'::jsonb);
```

### 25.5. Không đặt niềm tin vào CHECK chỉ vì có IS NOT NULL?

`CHECK ((doc->>'email') IS NOT NULL)` có thể cấm cả missing và JSON null ở email, nhưng **chưa bảo đảm email có kiểu JSON string**. JSON boolean false hay JSON number 0 đều được chuyển thành text không NULL. Khi cần đúng JSON schema, kiểm tra cả `jsonb_typeof`.

## 26. Indexing cho ba trạng thái

Việc truy vấn thường xuyên theo JSON field có thể cần index, nhưng **index cũng phải phù hợp semantics**.

### 26.1. Index trên biểu thức text

```sql
CREATE INDEX idx_documents_email_text
ON json_null_lab.documents
    ((doc ->> 'email'));
```

Index này hữu ích với query dạng:

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc ->> 'email' = 'a@example.com';
```

Nhưng biểu thức `doc ->> 'email'` trả SQL NULL với cả:

- Email JSON null.
- Email missing.
- Document SQL NULL.

Nếu mục tiêu index/query là phân biệt các trạng thái trên, **index trên biểu thức text không tự mang thông tin presence**.

### 26.2. GIN cho top-level key existence

```sql
CREATE INDEX idx_documents_jsonb_gin_ops
ON json_null_lab.documents
USING GIN (doc jsonb_ops);
```

Truy vấn:

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc ? 'email';
```

có thể được hỗ trợ bởi GIN operator class `jsonb_ops` khi bảng và tính chọn lọc phù hợp. Đừng tự động mong Index Scan trên lab 18 hàng; PostgreSQL có thể chọn Seq Scan hợp lý.

### 26.3. Partial index cho explicit JSON null

```sql
CREATE INDEX idx_documents_email_json_null
ON json_null_lab.documents (id)
WHERE jsonb_typeof(doc -> 'email') = 'null';
```

Index chỉ chứa những row mà predicate trên là TRUE. Một query có cùng predicate có thể được hưởng lợi khi workload đủ lớn và planner nhận ra điều kiện tương thích.

Không tạo một index cho mọi biến thể email state trong production nếu không có bằng chứng query frequency và lợi ích.

### 26.4. jsonb_path_ops và key existence

GIN `jsonb_path_ops` có thể hiệu quả cho một số queries containment/JSONPath nhưng **không cung cấp hỗ trợ cho toán tử `?`** như `jsonb_ops`. Nếu workload chính là hỏi “key có tồn tại không?”, đừng chọn operator class chỉ dựa vào kích thước index mà bỏ qua operator support.

### 26.5. Index không biến ba trạng thái thành một

Index là cấu trúc truy cập. Việc phân biệt SQL NULL, JSON null và missing nằm ở **biểu thức SQL và kiểu dữ liệu đầu ra**. Một index phù hợp giúp tăng tốc truy vấn được viết đúng, không sửa được query sai ngữ nghĩa như dùng `->> IS NULL` để khẳng định “JSON null đã được gửi”.

## 27. API PATCH: missing, JSON null và giá trị thực là ba yêu cầu khác nhau

Giả sử hệ thống quản lý profile có email hiện tại:

```json
{"email":"old@example.com","displayName":"Lan"}
```

Client gửi một trong ba payload:

```json
{}
```

```json
{"email":null}
```

```json
{"email":"new@example.com"}
```

Một quy tắc PATCH **do ứng dụng định nghĩa** có thể là:

| Payload | Ý định cập nhật email |
| --- | --- |
| `{}` | Không sửa email. |
| `{"email":null}` | Xóa/clear email hiện có. |
| `{"email":"new@example.com"}` | Đổi email sang giá trị mới. |

Đó là một chính sách phổ biến, nhưng **không phải mọi HTTP PATCH đều mặc định theo chính sách này**. Ngữ nghĩa cụ thể phụ thuộc Content-Type và giao thức PATCH đang sử dụng.

### 27.1. JSON Merge Patch khác JSON Patch

Hai chuẩn thường gặp có hành vi khác nhau:

- **JSON Merge Patch (RFC 7396, `application/merge-patch+json`):** object chứa key với JSON null thường biểu thị yêu cầu loại bỏ member tương ứng khỏi target object. Key vắng mặt nghĩa là không tác động key ấy. Mô hình này không phù hợp nếu muốn phân biệt “đặt giá trị null thật” với “xóa member” bằng cùng một null marker đơn giản.
- **JSON Patch (RFC 6902, `application/json-patch+json`):** thao tác được biểu diễn rõ bằng các operation như `add`, `replace`, `remove` trên path. JSON null có thể là value của `add/replace`; `remove` là thao tác riêng.

Nếu API chỉ nhận body JSON thông thường trong `PATCH /profile` mà không công bố chuẩn cụ thể, đội phát triển phải **quy định và kiểm thử** semantics của missing/null/replace.

### 27.2. PUT không nên bị xử lý y như PATCH

`PUT` thường mang ý nghĩa thay thế representation của resource theo contract API, còn `PATCH` sửa một phần. Dù ứng dụng có thể có thiết kế khác nhau, không nên áp dụng “missing giữ nguyên” cho mọi PUT một cách vô thức. Cần tài liệu API rõ ràng.

### 27.3. Không gọi ->> quá sớm

Nếu parser chuyển payload thành:

```text
email: nullable String
```

thì cả `{}` lẫn `{"email":null}` đều có thể cho Java field `email == null`. Sau khi mất presence flag, database không còn biết client có chủ động clear email hay không.

Giải pháp là mô hình hóa trạng thái:

```text
EmailPatch =
    Absent
  | PresentNull
  | PresentString(value)
```

hoặc giữ JSON tree và kiểm tra key presence trước khi convert.

## 28. SQL mẫu PATCH cho một cột relational nullable

Tạo bảng thực hành:

```sql
CREATE TABLE json_null_lab.customer_profiles (
    profile_id integer PRIMARY KEY,
    email text,
    display_name text NOT NULL
);

INSERT INTO json_null_lab.customer_profiles (
    profile_id, email, display_name
)
VALUES (1, 'old@example.com', 'Lan');
```

Yêu cầu:

- Email field missing: giữ nguyên cột email.
- Email JSON null: đặt email SQL NULL.
- Email JSON string: cập nhật text tương ứng.
- Email JSON number/boolean/object/array: không chấp nhận trong API.

### 28.1. UPDATE giữ nguyên khi missing

```sql
BEGIN;

WITH incoming AS (
    SELECT '{}'::jsonb AS patch_doc
)
UPDATE json_null_lab.customer_profiles AS p
SET email =
    CASE
        WHEN incoming.patch_doc ? 'email'
            THEN incoming.patch_doc ->> 'email'
        ELSE p.email
    END
FROM incoming
WHERE p.profile_id = 1
  AND jsonb_typeof(incoming.patch_doc) = 'object'
  AND (
      NOT (incoming.patch_doc ? 'email')
      OR jsonb_typeof(incoming.patch_doc -> 'email')
          IN ('string', 'null')
  )
RETURNING p.profile_id, p.email;

ROLLBACK;
```

Kết quả email vẫn là `old@example.com` trong transaction, vì field **không được cung cấp**. `ROLLBACK` giữ dữ liệu lab nguyên trạng.

### 28.2. UPDATE clear email khi JSON null

```sql
BEGIN;

WITH incoming AS (
    SELECT '{"email":null}'::jsonb AS patch_doc
)
UPDATE json_null_lab.customer_profiles AS p
SET email =
    CASE
        WHEN incoming.patch_doc ? 'email'
            THEN incoming.patch_doc ->> 'email'
        ELSE p.email
    END
FROM incoming
WHERE p.profile_id = 1
  AND jsonb_typeof(incoming.patch_doc) = 'object'
  AND (
      NOT (incoming.patch_doc ? 'email')
      OR jsonb_typeof(incoming.patch_doc -> 'email')
          IN ('string', 'null')
  )
RETURNING p.profile_id, p.email;

ROLLBACK;
```

Kết quả email là **SQL NULL** trong transaction, vì email được gửi và `->>` chuyển JSON null thành SQL NULL. `ROLLBACK` trả dữ liệu về giá trị cũ.

### 28.3. UPDATE bằng JSON string

```sql
BEGIN;

WITH incoming AS (
    SELECT '{"email":"new@example.com"}'::jsonb AS patch_doc
)
UPDATE json_null_lab.customer_profiles AS p
SET email =
    CASE
        WHEN incoming.patch_doc ? 'email'
            THEN incoming.patch_doc ->> 'email'
        ELSE p.email
    END
FROM incoming
WHERE p.profile_id = 1
  AND jsonb_typeof(incoming.patch_doc) = 'object'
  AND (
      NOT (incoming.patch_doc ? 'email')
      OR jsonb_typeof(incoming.patch_doc -> 'email')
          IN ('string', 'null')
  )
RETURNING p.profile_id, p.email;

ROLLBACK;
```

Kết quả email trong transaction là `new@example.com`.

### 28.4. Vì sao WHERE kiểm tra kiểu?

Nếu không kiểm tra, `{"email":false}` qua `->>` biến thành SQL text `false` và có thể lưu sai vào cột email. Điều kiện kiểm tra chỉ cho phép JSON string hoặc JSON null ở field đã xuất hiện.

Trong API thực tế, payload sai phải được xử lý bằng lỗi rõ (ví dụ HTTP 400/422 theo contract), **không chỉ âm thầm UPDATE 0 rows**. Mẫu SQL dùng WHERE đơn giản để minh họa validation; application phải xác nhận row count và lý do không cập nhật.

### 28.5. Khi nhiều field cùng PATCH

Mỗi field có thể cần presence logic riêng:

```text
email:       Absent | PresentNull | PresentString
displayName: Absent | PresentNull | PresentString
preferences: Absent | PresentNull | PresentObject
```

Không gộp tất cả thành một câu `COALESCE(patch_doc->>field, old_value)` nếu null và missing có ngữ nghĩa khác nhau. Với những field bắt buộc như displayName, JSON null có thể **bị từ chối** thay vì clear.

## 29. SQL mẫu PATCH cho cột JSONB

Giả sử document hiện tại:

```json
{"email":"old@example.com","theme":"dark"}
```

Muốn:

- Missing email trong patch → giữ nguyên email.
- Email JSON null → lưu JSON null nếu nghiệp vụ cho phép.
- Email JSON string → ghi string mới.

### 29.1. Giữ JSON null thay vì xóa

```sql
SELECT
    CASE
        WHEN patch_doc ? 'email'
            THEN jsonb_set(
                current_doc,
                '{email}',
                patch_doc -> 'email',
                true
            )
        ELSE current_doc
    END AS updated_doc
FROM (
    SELECT
        '{"email":"old@example.com","theme":"dark"}'::jsonb
            AS current_doc,
        '{"email":null}'::jsonb AS patch_doc
) AS input;
```

Kết quả có `"email":null` và giữ `theme`.

Nếu patch là `{}`, CASE giữ nguyên current_doc. Biểu thức `patch_doc -> 'email'` là JSON null **không phải SQL NULL**, nên `jsonb_set` tạo field JSON null như mong muốn.

### 29.2. Diễn giải null thành xóa key

Nếu contract API nói JSON null nghĩa là xóa email:

```sql
SELECT
    CASE
        WHEN NOT (patch_doc ? 'email')
            THEN current_doc
        WHEN jsonb_typeof(patch_doc -> 'email') = 'null'
            THEN current_doc - 'email'
        ELSE jsonb_set(
            current_doc,
            '{email}',
            patch_doc -> 'email',
            true
        )
    END AS updated_doc
FROM (
    SELECT
        '{"email":"old@example.com","theme":"dark"}'::jsonb
            AS current_doc,
        '{"email":null}'::jsonb AS patch_doc
) AS input;
```

Kết quả chỉ còn `{"theme":"dark"}`.

### 29.3. Vì sao cần validation ở cả hai ví dụ?

Với code ở 29.1/29.2, nếu client gửi `{"email":false}`, JSONB boolean false được lưu trực tiếp. Nếu contract chỉ cho phép string/null thì phải có bước từ chối dữ liệu sai trước khi UPDATE. Ngoài ra phải xử lý:

- `patch_doc` có phải SQL NULL không?
- Root có phải JSON object không?
- Current document có phải object như ứng dụng kỳ vọng không?
- Bản ghi được cập nhật có thuộc đúng tenant/user không?
- Concurrent PATCH của hai clients có thể làm mất cập nhật của nhau không?

Thông tin null/missing chỉ là **một phần** của tính đúng đắn khi cập nhật.

## 30. Java/JDBC và Jackson: không để mất presence bit

Trong Java, việc parse JSON sang một POJO có field nullable đơn thuần có thể gộp missing với explicit JSON null. Khi cần semantics PATCH, dùng JSON tree hoặc DTO có mô hình trạng thái ba nhánh.

### 30.1. Jackson JsonNode.get

Đoạn Java dùng Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(requestBody);

if (!root.isObject()) {
    throw new IllegalArgumentException(
        "Expected a JSON object"
    );
}

JsonNode email = root.get("email");

if (email == null) {
    // Key "email" không có trong object.
    // PATCH policy: không thay đổi email cũ.
} else if (email.isNull()) {
    // Key "email" tồn tại với JSON null.
    // PATCH policy: clear email (SQL NULL)
    // hoặc xóa key JSONB tùy contract.
} else if (email.isTextual()) {
    String newEmail = email.textValue();
    // Validate và cập nhật.
} else {
    throw new IllegalArgumentException(
        "email must be a string or JSON null"
    );
}
```

Trong Jackson tree API:

- `get("email")` trên object không có field trả **Java null**.
- `get("email")` khi field có JSON null trả một node đại diện **NullNode**, không phải Java null.
- `isNull()` kiểm tra node có kiểu JSON null.
- `isTextual()` kiểm tra JSON string.

Đoạn Java là một ví dụ minh họa xử lý request body, không phải một controller hoàn chỉnh hoặc thay thế validation và security.

### 30.2. Jackson path và MissingNode

Jackson còn có:

```java
JsonNode emailByPath = root.path("email");

if (emailByPath.isMissingNode()) {
    // Key không có.
} else if (emailByPath.isNull()) {
    // JSON null được gửi.
}
```

`path(...)` thay missing bằng **MissingNode** thay vì Java null. Không đồng nhất MissingNode với NullNode trong bất kỳ bước serialize/map DTO nào nếu contract cần phân biệt.

### 30.3. JDBC: SQL NULL khác chuỗi JSON "null"

Ví dụ truy vấn:

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE id IN (1, 2, 3)
ORDER BY id;
```

Một ứng dụng Java dùng JDBC:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, doc " +
        "FROM json_null_lab.documents " +
        "WHERE id IN (1, 2, 3) ORDER BY id"
    );
    ResultSet rs = ps.executeQuery()) {

    ObjectMapper mapper = new ObjectMapper();

    while (rs.next()) {
        int id = rs.getInt("id");
        String jsonText = rs.getString("doc");

        if (jsonText == null) {
            // SQL NULL cột doc.
            System.out.println(id + ": SQL NULL document");
            continue;
        }

        JsonNode docNode = mapper.readTree(jsonText);

        if (docNode.isNull()) {
            // JSON text 'null' từ jsonb document.
            System.out.println(id + ": JSON null document");
        } else if (docNode.isObject()) {
            // Đọc từng field và kiểm tra presence.
            System.out.println(id + ": JSON object");
        }
    }
}
```

Giả định `connection` hợp lệ, driver PostgreSQL và Jackson có mặt, method xử lý exceptions phù hợp. Trường hợp `getString` trả Java `null` ứng với SQL NULL, còn JSON document `'null'::jsonb` được biểu diễn bằng text `null` (chuỗi có bốn ký tự), rồi Jackson parse thành NullNode.

### 30.4. ResultSet.wasNull()

Với JDBC, nhiều getter cho kiểu primitive như `getInt` trả một giá trị mặc định khi cột là SQL NULL; cần dùng `wasNull()` ngay sau getter để biết nguồn là SQL NULL.

Ví dụ:

```java
int quantity = rs.getInt("quantity");
boolean sqlNull = rs.wasNull();
```

Với `getString("doc")`, Java null thường đủ để nhận biết SQL NULL của cột; dùng `wasNull()` cũng có thể giúp làm rõ. **Không so sánh chuỗi `"null"` với Java `null` như thể chúng tương đương.**

### 30.5. Lưu lại JSONB qua JDBC

Khi ghi JSONB parameter, cần phân biệt:

- SQL NULL parameter: đặt JDBC parameter thành SQL NULL với kiểu phù hợp.
- JSON null document: gửi JSON text `null` và cast/bind thành JSONB.
- Object có field JSON null: gửi JSON text `{"email":null}`.
- Object missing field: gửi `{}` nếu đó là representation mong muốn.

Lệnh ví dụ:

```sql
INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    (1001, 'SQL NULL', NULL::jsonb),
    (1002, 'JSON null', 'null'::jsonb),
    (1003, 'Missing email', '{}'::jsonb),
    (1004, 'Email JSON null', '{"email":null}'::jsonb);
```

Đây là mẫu SQL để minh họa semantics; khi dùng PreparedStatement thật, bind parameters theo driver và kiểm tra quyền, validation. Không chạy nhiều lần trên lab vì trùng primary key; có thể bọc thử bằng transaction rồi ROLLBACK.

## 31. Data pipelines và event processing: missing không giống clear

Một hệ thống CDC/ETL nhận sự kiện:

```json
{"entityId":42,"changes":{"phone":null}}
```

và:

```json
{"entityId":42,"changes":{}}
```

Nếu contract là **partial changes**:

- Sự kiện đầu yêu cầu clear phone.
- Sự kiện sau không nhắc đến phone.

Nếu pipeline chuyển cả hai thành SQL NULL trong một cột staging `phone text` mà không lưu metadata presence, downstream không thể biết phải clear hay giữ giá trị cũ.

### 31.1. Staging nên lưu raw JSON hoặc presence

Một thiết kế:

```sql
CREATE TABLE json_null_lab.change_events (
    event_id bigint PRIMARY KEY,
    entity_id bigint NOT NULL,
    received_at timestamptz NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    changes jsonb NOT NULL,
    CONSTRAINT ck_changes_object
        CHECK (jsonb_typeof(changes) = 'object')
);
```

Chèn:

```sql
INSERT INTO json_null_lab.change_events
    (event_id, entity_id, changes)
VALUES
    (1, 42, '{"phone":null}'::jsonb),
    (2, 42, '{}'::jsonb),
    (3, 42, '{"phone":"0987654321"}'::jsonb);
```

Phân loại:

```sql
SELECT
    event_id,
    entity_id,
    CASE
        WHEN NOT (changes ? 'phone')
            THEN 'UNCHANGED'
        WHEN jsonb_typeof(changes -> 'phone') = 'null'
            THEN 'CLEAR'
        WHEN jsonb_typeof(changes -> 'phone') = 'string'
            THEN 'SET'
        ELSE 'INVALID_TYPE'
    END AS phone_action,
    changes ->> 'phone' AS phone_value
FROM json_null_lab.change_events
ORDER BY event_id;
```

Kết quả hành động: UNCHANGED, CLEAR, SET. `phone_value` của hai sự kiện đầu là SQL NULL nhưng **phone_action khác nhau**.

### 31.2. Idempotency không chỉ là JSON null

Một sự kiện SET/CLEAR có thể bị phát lại. Muốn áp dụng an toàn cần có event ID hoặc version, quy tắc thứ tự và transaction/idempotency phù hợp. JSON field presence chỉ giúp hiểu **ý định thay đổi**, không tự giải quyết vấn đề duplicate delivery hay out-of-order events.

### 31.3. Audit phải giữ được trạng thái ban đầu

Nếu audit chỉ ghi “giá trị email sau cập nhật = NULL”, không biết nguyên nhân là:

- Client gửi JSON null.
- Client không gửi email, nhưng code đã sai và ghi NULL.
- Dữ liệu nguồn là SQL NULL từ trước.
- Pipeline dùng mapping SQL nullable làm mất presence.

Muốn truy nguyên, audit cần lưu sự kiện, các trường có mặt, version/actor/timestamp và kết quả xử lý theo chính sách bảo mật.

## 32. Truy vấn dữ liệu bẩn và phân loại sai lệch

Khi nhận JSON từ nhiều nguồn, một field có thể mang nhiều kiểu không mong đợi:

```json
{"price":10}
```

```json
{"price":"10"}
```

```json
{"price":null}
```

```json
{}
```

Không thể dùng duy nhất:

```sql
WHERE doc ->> 'price' IS NOT NULL
```

để xác nhận price là number. Nó cũng cho TRUE với JSON string `"10"`, boolean false và các scalar khác chuyển được thành text.

### 32.1. Lọc đúng JSON number

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'number';
```

Trên bộ dữ liệu lab, trả **id=17**. Đổi field email thành price là cùng cách tư duy; key presence và JSON type phải được kiểm tra trước khi cast.

### 32.2. Cast text thành numeric có thể lỗi

Nếu giá trị JSON string là `"not-a-number"`:

```sql
-- Không nên cast mà không validate:
-- SELECT (doc ->> 'price')::numeric FROM ...;
```

PostgreSQL có thể báo invalid input syntax. Phải định nghĩa contract rằng price cần JSON number hay được phép string dạng số, và kiểm tra/cast phù hợp. JSON null và missing thành SQL NULL không phải vấn đề duy nhất.

### 32.3. Tài liệu JSON không hợp lệ

Các chuỗi sau không phải JSON hợp lệ:

```text
{email:null}        -- Key không có dấu ngoặc kép
{"email":undefined} -- JSON không có literal undefined
{"email":NaN}       -- JSON chuẩn không có NaN literal kiểu này
```

Nếu ứng dụng JavaScript phân biệt `undefined` với `null`, khi serialize sang JSON phải hiểu rằng **undefined không phải literal JSON**. Nhiều serializer bỏ key có giá trị undefined trong object, khiến phía PostgreSQL thấy **missing**, không phải JSON null. Hành vi cụ thể tùy serializer và cấu hình.

### 32.4. Duplicate keys trong JSONB

`jsonb` không giữ nhiều member trùng tên key như một danh sách độc lập. Khi parse JSON object có key lặp lại, biểu diễn jsonb thông thường giữ giá trị tương ứng với lần xuất hiện sau, ví dụ:

```sql
SELECT
    '{"email":null,"email":"new@example.com"}'::jsonb
        AS parsed_document;
```

Kết quả mang một key email với giá trị string mới. Nếu một API cần phát hiện duplicate keys như lỗi input, phải thực hiện kiểm tra ở lớp parse/validation thích hợp; sau khi đã chuẩn hóa thành jsonb, không thể dựa vào document để đếm số lần xuất hiện key gốc.

### 32.5. Giá trị đặc biệt "null" có thể hợp lệ

Một string `"null"` đôi khi là nội dung thật (ví dụ mã sản phẩm hoặc tên do người dùng nhập). Không tự convert sang NULL bằng:

```sql
NULLIF(doc ->> 'code', 'null')
```

trừ khi định nghĩa dữ liệu nguồn nói rõ literal ấy là sentinel cần chuẩn hóa. Nếu không, hệ thống sẽ phá tính toàn vẹn thông tin.

## 33. Bảng quyết định: dùng công cụ nào cho câu hỏi nào?

| Mục tiêu cần kiểm tra | Biểu thức gợi ý | Giới hạn cần biết |
| --- | --- | --- |
| Cả cột JSONB có SQL NULL? | `doc IS NULL` | Không chọn document JSON null. |
| Document có literal JSON null ở root? | `jsonb_typeof(doc) = 'null'` | Với SQL NULL document, biểu thức là UNKNOWN. |
| Root là object? | `jsonb_typeof(doc) = 'object'` | Nên đi kèm `NOT NULL` nếu dùng trong CHECK. |
| Key email có trong object? | `doc ? 'email'` | Kiểm tra top-level; với array có semantics tìm string element. |
| Key email có JSON null? | `jsonb_typeof(doc -> 'email') = 'null'` | Không tự khẳng định document có kiểu object nếu chưa kiểm tra root. |
| Key email có string bất kỳ? | `jsonb_typeof(doc -> 'email') = 'string'` | String rỗng và chữ "null" vẫn là string. |
| Lấy text email để hiển thị | `doc ->> 'email'` | Gộp JSON null và missing thành SQL NULL. |
| Nested profile.email có JSON null? | `jsonb_typeof(doc #> '{profile,email}') = 'null'` | Muốn biết vì sao path thiếu cần kiểm tra từng cấp. |
| Nested path có tồn tại? | `jsonb_path_exists(doc,'$.profile.email')` | PostgreSQL 12+; cần xét lax/strict và root type. |
| Object chứa đúng email JSON null? | `doc @> '{"email":null}'::jsonb` | Containment không đồng nghĩa kiểm tra sự tồn tại chung cho mọi kiểu. |
| Xóa key email | `doc - 'email'` | Thao tác trên object top-level; khác JSON null. |
| Đặt key thành JSON null | `jsonb_set(doc,'{email}','null'::jsonb,true)` | Path trung gian phải phù hợp. |
| Xử lý new_value SQL NULL theo chế độ | `jsonb_set_lax(...)` | PostgreSQL 13+ và mode được chọn. |
| Bỏ object fields có JSON null | `jsonb_strip_nulls(doc)` | Có thể làm mất thông tin explicit null; array xử lý khác. |
| So sánh JSONB với SQL NULL không UNKNOWN | `IS DISTINCT FROM` | Không tự trả lời key có hiện diện hay không. |
| Đếm giá trị JSON tại key | `COUNT(doc -> 'email')` | JSON null được đếm; missing bị loại. |
| Đếm text value không SQL NULL | `COUNT(doc ->> 'email')` | JSON null và missing đều bị loại. |

### 33.1. Câu hỏi mẫu “email chưa khai báo”

Nếu nghiệp vụ định nghĩa *chưa khai báo* là object có key email **không xuất hiện**, dùng:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND NOT (doc ? 'email');
```

Đừng dùng `doc ->> 'email' IS NULL` vì nó còn nhận explicit JSON null và những root khác.

### 33.2. Câu hỏi mẫu “email được gửi nhưng null”

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'null';
```

Trên lab, trả id=4.

### 33.3. Câu hỏi mẫu “email có nội dung string”

```sql
SELECT id, doc ->> 'email' AS email
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND jsonb_typeof(doc -> 'email') = 'string'
  AND length(doc ->> 'email') > 0;
```

Lưu ý chuỗi `"null"` có bốn ký tự nên vẫn được trả. Muốn kiểm tra email thực, còn phải validation định dạng và policy riêng.

## 34. Những hiểu nhầm phổ biến

### Hiểu nhầm 1. “JSON null và SQL NULL giống nhau”

Không. `'null'::jsonb IS NULL` là FALSE, còn `NULL::jsonb IS NULL` là TRUE.

### Hiểu nhầm 2. “Object có email:null là object không có key email”

Không. `'{"email":null}'::jsonb ? 'email'` là TRUE.

### Hiểu nhầm 3. “Toán tử -> luôn trả SQL NULL nếu JSON field là null”

Không. `->` trả JSONB null khi key tồn tại với JSON null; chỉ missing/một số tình huống không truy xuất được mới trả SQL NULL.

### Hiểu nhầm 4. “->> cũng giữ nguyên kiểu JSON”

Không. `->>` trả SQL text; nó làm JSON null và missing trở thành SQL NULL giống nhau.

### Hiểu nhầm 5. “jsonb_typeof('null'::jsonb) trả SQL NULL”

Không. Nó trả **SQL text `null`**, là tên kiểu JSON.

### Hiểu nhầm 6. “jsonb_typeof(NULL::jsonb) = 'null' trả TRUE”

Không. Phép so sánh trên SQL NULL cho UNKNOWN/SQL NULL; cần `IS NULL` để kiểm tra kết quả hàm thiếu giá trị.

### Hiểu nhầm 7. “WHERE doc->'k' <> 'null'::jsonb chọn cả key thiếu”

Không. Với key thiếu, `doc->'k'` là SQL NULL; phép `<>` trả UNKNOWN nên dòng bị loại khỏi WHERE.

### Hiểu nhầm 8. “COALESCE tự thay JSON null trong jsonb”

Không. `COALESCE('null'::jsonb, '{}'::jsonb)` trả JSONB null, vì JSONB null **không phải SQL NULL**.

### Hiểu nhầm 9. “COALESCE(doc->>'k', old) giữ được phân biệt missing/null”

Không. Cả missing và explicit JSON null đều được thay thành old. Điều đó chỉ đúng nếu API muốn xử lý hai trạng thái giống nhau.

### Hiểu nhầm 10. “JSON string 'null' là JSON null”

Không. JSON string là `"null"` có kiểu `string`, JSON null là `null` có kiểu `null`.

### Hiểu nhầm 11. “Chuỗi rỗng, false và 0 là null”

Không. Chúng là các JSON scalar có giá trị và kiểu khác. Có thể bị từ chối theo nghiệp vụ, nhưng không đồng nghĩa null.

### Hiểu nhầm 12. “IS NULL trên ->> chỉ chọn người dùng muốn clear”

Không. Nó cũng chọn key không được cung cấp và document SQL NULL, nếu không có điều kiện khác.

### Hiểu nhầm 13. “Toán tử ? tìm mọi cấp của JSON”

Không. Với object, `?` tìm key top-level; với array, nó có thể tìm string element top-level. Nested key cần truy xuất cấp cha hoặc JSONPath.

### Hiểu nhầm 14. “? 'null' trong JSON array tìm phần tử JSON null”

Không. Toán tử ấy tìm **JSON string element `"null"`**, không phải JSON scalar null.

### Hiểu nhầm 15. “Array [null] giống []”

Không. `jsonb_array_length('[null]'::jsonb)=1`, còn array rỗng có length=0.

### Hiểu nhầm 16. “Chỉ số JSON array ngoài phạm vi và phần tử null là một”

Không. `[null] -> 0` trả JSON null, `[null] -> 1` trả SQL NULL.

### Hiểu nhầm 17. “SQL array NULL và JSON array null dùng chung một kiểu”

Không. Native SQL array chứa SQL-typed elements, JSONB array chứa JSON values; toán tử và semantics conversion khác.

### Hiểu nhầm 18. “#> và #>> cùng kiểu output”

Không. `#>` giữ JSON/JSONB, `#>>` trả SQL text và làm JSON null/missing cùng thành SQL NULL.

### Hiểu nhầm 19. “profile:null và profile:{} là cùng một cấu trúc”

Không. Một bên profile là JSON scalar null; bên kia là JSON object rỗng, có thể thêm key con.

### Hiểu nhầm 20. “jsonb_set(doc,'{k}',NULL::jsonb) nghĩa đặt k=null”

Không. SQL NULL argument không giống JSONB null; dùng `'null'::jsonb` nếu muốn value JSON null, hoặc `jsonb_set_lax` với mode có chủ đích.

### Hiểu nhầm 21. “jsonb_set sẽ tạo đủ mọi object trung gian còn thiếu”

Không. `create_if_missing=true` không hứa dựng trọn mọi thành phần path trung gian. Cần có cấu trúc cha phù hợp.

### Hiểu nhầm 22. “jsonb_set_lax delete_key giống use_json_null”

Không. Một mode xóa key, một mode giữ key và ghi JSON null.

### Hiểu nhầm 23. “jsonb_strip_nulls không làm mất thông tin”

Không. Nó có thể biến `{"email":null}` thành `{}`, đánh mất sự phân biệt explicit null với missing.

### Hiểu nhầm 24. “COUNT(doc->'k') không đếm JSON null”

Không. COUNT loại **SQL NULL**, trong khi `doc->'k'` trả JSONB null (không SQL NULL) khi field có explicit JSON null.

### Hiểu nhầm 25. “COUNT(doc->'k') và COUNT(doc->>'k') luôn giống nhau”

Không. Trường JSON null được tính ở dạng JSONB `->` nhưng không được tính khi đã đổi sang text `->>`.

### Hiểu nhầm 26. “NOT NULL cấm cột jsonb chứa literal null”

Không. `doc jsonb NOT NULL` vẫn cho phép `'null'::jsonb`. Muốn object phải thêm CHECK về `jsonb_typeof`.

### Hiểu nhầm 27. “CHECK(doc->>'email' <> '') bảo đảm email hiện diện”

Không. Với missing hoặc JSON null, biểu thức có thể là UNKNOWN, và CHECK chấp nhận UNKNOWN. Phải kết hợp NOT NULL, presence/type tests phù hợp.

### Hiểu nhầm 28. “GIN jsonb_path_ops giúp tăng tốc mọi toán tử jsonb”

Không. Operator classes khác nhau có bộ toán tử được hỗ trợ khác nhau, đặc biệt `?` không được `jsonb_path_ops` hỗ trợ như `jsonb_ops`.

### Hiểu nhầm 29. “JSONPath tồn tại path nghĩa value khác JSON null”

Không. Path có thể tồn tại mà giá trị cuối là JSON null.

### Hiểu nhầm 30. “JSONPath @ == null giống SQL = NULL”

Không. Trong JSONPath, predicate so sánh JSON null có semantics riêng; SQL `= NULL` theo logic ba giá trị không trả TRUE.

### Hiểu nhầm 31. “Khi parse JSON thành text/POJO nullable vẫn biết field có xuất hiện”

Không. Nếu bỏ presence metadata, missing và explicit JSON null có thể đã gộp thành cùng Java/SQL null.

### Hiểu nhầm 32. “Jackson get('email') trả Java null cho explicit JSON null”

Không. Nó trả một NullNode; Java null của `get` biểu thị key không tìm thấy trong object tương ứng.

### Hiểu nhầm 33. “Jackson path('email') và get('email') giống hoàn toàn”

Không. `path` thường biểu diễn missing bằng MissingNode thay vì Java null, giúp kiểm tra `isMissingNode()`.

### Hiểu nhầm 34. “JSON Merge Patch dùng null để lưu JSON null”

Không trong cách diễn giải merge-patch thông thường: null member là dấu hiệu remove. Nếu muốn lưu JSON null như một giá trị khác remove, cần chọn contract/giao thức cho phép biểu diễn khác biệt, ví dụ JSON Patch operation.

### Hiểu nhầm 35. “Mọi HTTP PATCH có nghĩa null=xóa”

Không. Content-Type và hợp đồng API mới quyết định semantics. JSON object PATCH tự thiết kế phải ghi rõ missing/null/value.

### Hiểu nhầm 36. “JSONB giữ mọi duplicate object key”

Không. JSONB chuẩn hóa object key và không giữ nhiều bản ghi cùng tên như một danh sách; phải phát hiện duplicates trước nếu chúng là lỗi input.

### Hiểu nhầm 37. “SELECT jsonb_build_object('x',SQL_NULL) cho biết nguồn đã là JSON null”

Không. JSON builder có thể biểu diễn SQL NULL thành JSON null, nên output không tiết lộ kiểu NULL ở nguồn.

### Hiểu nhầm 38. “Một index expression trả SQL NULL vẫn phân biệt missing/JSON null”

Không. Index trên `doc->>'email'` chỉ lưu giá trị của biểu thức text; hai trạng thái có cùng SQL NULL expression không tự được phân biệt nhờ index.

### Hiểu nhầm 39. “Sửa query bằng IS DISTINCT FROM là đủ biết field tồn tại”

Không. NULL-safe comparison giúp so giá trị SQL nhưng không thay thế presence test `?`.

### Hiểu nhầm 40. “Chỉ cần một cột nullable staging để lưu patch event”

Không nếu missing và clear có nghĩa khác nhau. Nên giữ raw JSON hoặc explicit presence/action metadata.

## 35. Bài tập thực hành

Các bài sử dụng bảng `json_null_lab.documents` đã chèn 18 dòng ở phần 4 và các bảng lab khác ở những phần tương ứng. Bài nào có thao tác UPDATE/DELETE nên dùng transaction rồi `ROLLBACK` để không làm thay đổi dữ liệu thử nghiệm. Với câu SQL về phiên bản, đọc ghi chú PostgreSQL 12+/13+ ở các phần trước.

### Bài 1. Phân loại ba khái niệm

Nêu rõ khác biệt của `NULL::jsonb`, `'null'::jsonb` và `'{}'::jsonb` khi truy cập khóa email.

### Bài 2. IS NULL ở root

Tính kết quả:

```sql
SELECT
    NULL::jsonb IS NULL AS a,
    'null'::jsonb IS NULL AS b,
    '{}'::jsonb IS NULL AS c;
```

### Bài 3. jsonb_typeof

`jsonb_typeof('null'::jsonb)` trả gì? `jsonb_typeof(NULL::jsonb)` trả gì? Vì sao hai kết quả khác nhau?

### Bài 4. JSON string "null"

Viết biểu thức để phân biệt `'{"k":"null"}'::jsonb` với `'{"k":null}'::jsonb` dựa trên kiểu JSON của key k.

### Bài 5. -> với key có JSON null

Tính:

```sql
SELECT
    ('{"k":null}'::jsonb -> 'k') IS NULL AS a,
    ('{}'::jsonb -> 'k') IS NULL AS b;
```

### Bài 6. ->> làm mất khác biệt

Vì sao hai biểu thức sau đều trả SQL NULL?

```sql
'{"k":null}'::jsonb ->> 'k'
'{}'::jsonb ->> 'k'
```

### Bài 7. Kiểm tra key existence

Viết câu SQL chọn những row `doc` là object có **key email xuất hiện**, bất kể giá trị của nó là JSON null, string, boolean hay number.

### Bài 8. Chọn riêng JSON null

Viết câu SQL chọn những document có **email top-level** được cung cấp và có **JSON null**. Với lab nguyên trạng, ID nào được chọn?

### Bài 9. Chọn riêng key missing

Viết câu SQL chọn những document thuộc kiểu object nhưng **không có email top-level**. Có chọn id=1 và id=2 không?

### Bài 10. SQL UNKNOWN khi so sánh

Với `doc='{}'::jsonb`, predicate `doc->'email' <> 'null'::jsonb` là TRUE, FALSE hay UNKNOWN? WHERE có chọn dòng đó không?

### Bài 11. IS DISTINCT FROM

`NULL::jsonb IS DISTINCT FROM 'null'::jsonb` trả gì? Nó có chứng minh field tồn tại không?

### Bài 12. COALESCE với ->

Kết quả của:

```sql
SELECT COALESCE(
    '{"k":null}'::jsonb -> 'k',
    '"fallback"'::jsonb
);
```

là JSON null hay fallback? Vì sao?

### Bài 13. COALESCE với ->>

Nếu đổi toán tử ở bài 12 thành `->>` và fallback thành SQL text `fallback`, kết quả là gì? Thông tin nào đã mất?

### Bài 14. Nested path

So sánh kết quả của `#> '{profile,email}'` cho:

```json
{"profile":{"email":null}}
```

```json
{"profile":{}}
```

```json
{"profile":null}
```

### Bài 15. ? chỉ ở cấp nào?

Tính:

```sql
SELECT
    '{"profile":{"email":null}}'::jsonb ? 'email'
        AS a,
    ('{"profile":{"email":null}}'::jsonb
        -> 'profile') ? 'email'
        AS b;
```

### Bài 16. JSON array

Tính kiểu của các biểu thức:

```sql
'[null]'::jsonb -> 0
'[null]'::jsonb -> 1
'["null"]'::jsonb -> 0
```

### Bài 17. Độ dài array

`jsonb_array_length('[null,null]'::jsonb)` bằng bao nhiêu? Có được coi các phần tử null như bị thiếu khỏi mảng không?

### Bài 18. ? trên array

`'[null,"null"]'::jsonb ? 'null'` có trả TRUE không? Vì sao?

### Bài 19. COUNT với JSON null

Với bảng 18 dòng nguyên trạng, tính:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(doc) AS non_sql_null_docs,
    COUNT(doc -> 'email') AS json_values,
    COUNT(doc ->> 'email') AS text_values
FROM json_null_lab.documents;
```

### Bài 20. Containment

Predicate nào có thể tìm object chứa top-level email là JSON null bằng `@>`? Nó có chọn object thiếu email không?

### Bài 21. jsonb_each

`jsonb_each('{"k":null}'::jsonb)` trả bao nhiêu hàng? `jsonb_each('{}'::jsonb)` trả bao nhiêu hàng? Kết quả đầu có value là SQL NULL không?

### Bài 22. jsonb_to_record

Vì sao chuyển `{}` và `{"email":null}` vào một record với `email text` có thể cho cùng email SQL NULL? Cần lưu metadata gì nếu muốn phân biệt?

### Bài 23. jsonb_set vs xóa key

Viết hai biểu thức biến `{"email":"old"}` thành:

1. `{"email":null}`.
2. `{}`.

### Bài 24. jsonb_set_lax

Với `new_value=NULL::jsonb`, phân biệt mode `use_json_null`, `delete_key` và `return_target`.

### Bài 25. jsonb_strip_nulls

Biến đổi `{"email":null,"a":[null],"profile":{"phone":null}}` bằng `jsonb_strip_nulls` một tham số. Vì sao thao tác này có thể gây lỗi semantics PATCH?

### Bài 26. CHECK sai

Vì sao constraint `CHECK (doc->>'email' <> '')` không đảm bảo field email xuất hiện và không phải JSON null?

### Bài 27. CHECK đúng kiểu object

Viết khai báo cột/constraint sao cho `doc` không thể là SQL NULL, JSON null root, array hoặc scalar string — chỉ được là object.

### Bài 28. Email optional

Viết một `CHECK` cho object `doc` có key email tùy chọn; nếu có thì chỉ được JSON string hoặc JSON null.

### Bài 29. NOT NULL với JSON null

Một cột `doc jsonb NOT NULL` có cho phép INSERT `'null'::jsonb` không? Khi nào cần thêm CHECK?

### Bài 30. API PATCH

Với profile email hiện tại `old@example.com`, hãy mô tả tác động của ba body:

```json
{}
```

```json
{"email":null}
```

```json
{"email":"new@example.com"}
```

theo contract “missing giữ cũ, null clear, string set”.

### Bài 31. Jackson

Trong Java Jackson, khác nhau thế nào giữa `root.get("email")` và `root.path("email")` khi email missing? Khi email explicit JSON null thì nên kiểm tra method nào?

### Bài 32. JDBC

Giải thích tại sao Java `String jsonText = rs.getString("doc")` có thể là Java null khi cột SQL NULL, nhưng có thể là chuỗi `"null"` khi cột chứa JSONB null.

### Bài 33. JSONPath

Viết hai biểu thức dùng `jsonb_path_exists`:

1. Kiểm tra path `$.email` có tồn tại.
2. Kiểm tra path ấy có giá trị JSON null.

### Bài 34. GIN operator classes

Nếu hot query luôn dùng `doc ? 'email'`, việc chọn GIN `jsonb_path_ops` thay cho `jsonb_ops` có vấn đề gì?

### Bài 35. Native SQL array

`ARRAY[NULL::integer,7]` và `'[null,7]'::jsonb` có cùng kiểu không? Có nên dùng `jsonb_array_length` cho array SQL integer?

### Bài 36. Data pipeline

Cho ba events:

```json
{"changes":{}}
```

```json
{"changes":{"phone":null}}
```

```json
{"changes":{"phone":"123"}}
```

Theo contract patch, đặt tên ba hành động tương ứng và nêu vì sao cột `phone text NULL` riêng lẻ không đủ lưu ý định.

### Bài 37. jsonb_build_object

So sánh output:

```sql
jsonb_build_object('email', NULL::text)
jsonb_build_object('email', 'null'::jsonb)
jsonb_build_object('email', 'null'::text)
```

Từ output có suy ra được nguồn SQL NULL hay JSON null không?

### Bài 38. Text false và number 0

Vì sao `doc->>'email' IS NOT NULL` không đủ bảo đảm email là JSON string? Viết điều kiện dùng `jsonb_typeof`.

### Bài 39. Phân tích lỗi SQL

Một developer viết:

```sql
UPDATE profiles
SET email = COALESCE(patch_doc ->> 'email', email);
```

và mong `{"email":null}` xóa email. Hãy giải thích sai ở đâu và nêu cách sửa.

### Bài 40. Thiết kế test cases

Thiết kế tối thiểu tám test cases cho endpoint nhận JSONB field email, để bảo đảm API không gộp SQL NULL, JSON null, missing, string `"null"`, string rỗng, boolean false, number 0 và nested field thành một trạng thái.

## 36. Gợi ý lời giải

### Đáp án 1. Ba khái niệm

- `NULL::jsonb`: SQL NULL của cả document, không có giá trị JSON ở biểu thức.
- `'null'::jsonb`: một document JSON hợp lệ có root kiểu JSON null.
- `'{}'::jsonb`: một JSON object rỗng, có tồn tại nhưng không có key email.

Tra `->'email'` trên cả ba trường hợp trả SQL NULL nhưng vì **ba nguyên nhân khác nhau**. Cần xem root type/presence để phân biệt.

### Đáp án 2. IS NULL

`a=TRUE`, `b=FALSE`, `c=FALSE`. JSON null và object rỗng đều là **giá trị jsonb không SQL NULL**.

### Đáp án 3. jsonb_typeof

`jsonb_typeof('null'::jsonb)` trả SQL text `null`. `jsonb_typeof(NULL::jsonb)` trả SQL NULL vì không có đối tượng JSONB đầu vào để xác định kiểu.

### Đáp án 4. JSON string vs JSON null

```sql
SELECT
    jsonb_typeof('{"k":"null"}'::jsonb -> 'k')
        AS string_type,
    jsonb_typeof('{"k":null}'::jsonb -> 'k')
        AS null_type;
```

Kết quả là text `string` và `null`; chúng không bằng nhau.

### Đáp án 5. -> IS NULL

`a=FALSE` vì `->` trả JSONB null đã tồn tại. `b=TRUE` vì key k missing và `->` trả SQL NULL.

### Đáp án 6. ->> thành text

`->>` trả SQL text. JSON null được chuyển thành SQL NULL, còn missing cũng không có giá trị nên trả SQL NULL. Khi đã chỉ có một text nullable, không biết trường có xuất hiện hay không.

### Đáp án 7. Key presence

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
ORDER BY id;
```

ID 4, 5, 6, 7, 8, 17, 18.

### Đáp án 8. Explicit JSON null

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'null';
```

Chỉ id=4 trong bảng lab gốc.

### Đáp án 9. Email missing trên object

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND NOT (doc ? 'email')
ORDER BY id;
```

ID 3, 9, 10, 11, 12. **Không** bao gồm id=1 (document SQL NULL) hoặc id=2 (JSON scalar null), vì root không phải object.

### Đáp án 10. UNKNOWN

`'{}'::jsonb -> 'email'` là SQL NULL. So sánh khác với `'null'::jsonb` trả UNKNOWN, và `WHERE` không chọn dòng vì predicate không TRUE.

### Đáp án 11. IS DISTINCT FROM

Kết quả TRUE, vì SQL NULL khác một giá trị JSONB null. Tuy nhiên biểu thức này chỉ so sánh hai giá trị, không chứng minh key đã được cung cấp trong object.

### Đáp án 12. COALESCE với ->

Trả **JSON null**. Kết quả `-> 'k'` là JSONB null đã tồn tại, không phải SQL NULL, nên COALESCE dừng ở giá trị đầu.

### Đáp án 13. COALESCE với ->>

Trả SQL text `fallback`, vì `->>` đổi JSON null thành SQL NULL. Nếu đầu vào thiếu key, cũng nhận fallback; thông tin explicit null vs missing bị mất.

### Đáp án 14. Nested path

- `{"profile":{"email":null}}` → JSONB null.
- `{"profile":{}}` → SQL NULL vì email missing.
- `{"profile":null}` → SQL NULL vì không thể đi sâu qua JSON null scalar để tìm email.

### Đáp án 15. ? top-level và nested

`a=FALSE`, `b=TRUE`. Key email không nằm top-level của document gốc mà nằm trong object profile.

### Đáp án 16. Array indexing

- `'[null]'::jsonb -> 0`: JSONB null.
- `'[null]'::jsonb -> 1`: SQL NULL vì index ngoài mảng.
- `'["null"]'::jsonb -> 0`: JSONB string `"null"`.

### Đáp án 17. Length

Kết quả là 2. JSON null vẫn là phần tử mảng hiện hữu và góp vào `jsonb_array_length`.

### Đáp án 18. ? trên array

TRUE, vì array có JSON string `"null"`. Nếu array chỉ chứa literal JSON null và không chứa string này, biểu thức `? 'null'` sẽ FALSE.

### Đáp án 19. COUNT trong lab

Với 18 hàng chưa bị thay đổi:

| Aggregate | Kết quả |
| --- | ---: |
| `COUNT(*)` | 18 |
| `COUNT(doc)` | 17 |
| `COUNT(doc -> 'email')` | 7 |
| `COUNT(doc ->> 'email')` | 6 |

`->` giữ JSON null là một giá trị, `->>` đổi JSON null thành SQL NULL. COUNT(expression) không đếm SQL NULL.

### Đáp án 20. Containment

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc @> '{"email":null}'::jsonb;
```

Trên lab chọn id=4. Một object thiếu key email không chứa cấu trúc `{"email":null}`, nên không được chọn.

### Đáp án 21. jsonb_each

`jsonb_each('{"k":null}'::jsonb)` trả một hàng với key `k` và value **JSONB null**; `jsonb_each('{}'::jsonb)` trả 0 hàng. Nếu đổi sang `jsonb_each_text`, value của k trở thành SQL NULL.

### Đáp án 22. Record conversion

Khi cast/extract vào một cột SQL `email text`, field missing hoặc explicit JSON null có thể đều thành SQL NULL. Để phân biệt, lưu thêm cờ `email_present = doc ? 'email'`, action enum hoặc raw JSON payload.

### Đáp án 23. Đặt JSON null vs xóa

```sql
SELECT
    jsonb_set(
        '{"email":"old"}'::jsonb,
        '{email}',
        'null'::jsonb,
        true
    ) AS keep_key_with_json_null,
    '{"email":"old"}'::jsonb - 'email'
        AS remove_key;
```

Kết quả lần lượt là `{"email":null}` và `{}`. Đây là hai thay đổi khác ngữ nghĩa.

### Đáp án 24. jsonb_set_lax

Trên PostgreSQL 13+:

- `use_json_null`: chuyển SQL NULL new_value thành JSON null ở key.
- `delete_key`: xóa key/path khi phù hợp.
- `return_target`: giữ nguyên JSON document.

`raise_exception` là lựa chọn để từ chối new_value SQL NULL bằng lỗi. Những mode này chỉ phát huy ngữ nghĩa riêng khi đối số `new_value` là SQL NULL.

### Đáp án 25. jsonb_strip_nulls

Với cách gọi một tham số thông thường:

```json
{"a":[null],"profile":{}}
```

Trường email và profile.phone bị xóa vì là object fields có JSON null; JSON null phần tử array vẫn còn. Nếu payload là PATCH, email được gửi explicit null có thể đã bị biến thành missing, làm mất yêu cầu clear/delete theo contract.

### Đáp án 26. CHECK sai

Với email missing hoặc JSON null, `doc->>'email'` là SQL NULL, nên `NULL <> ''` là UNKNOWN. `CHECK` chỉ từ chối FALSE, vì vậy những trường hợp này có thể qua constraint. Nếu muốn email bắt buộc, cần kiểm tra presence, type và giá trị cùng `doc NOT NULL`.

### Đáp án 27. Chỉ cho phép object

```sql
CREATE TABLE json_null_lab.only_objects (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (jsonb_typeof(doc) = 'object')
);
```

`NOT NULL` cấm SQL NULL; CHECK cấm JSONB scalar null, array, string, number hoặc boolean.

### Đáp án 28. Optional email

```sql
CREATE TABLE json_null_lab.optional_email_example (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (jsonb_typeof(doc) = 'object'),
    CHECK (
        NOT (doc ? 'email')
        OR jsonb_typeof(doc -> 'email')
            IN ('string', 'null')
    )
);
```

Như vậy email missing hợp lệ, email JSON null hợp lệ, email JSON string hợp lệ; boolean/number/object/array ở email không hợp lệ.

### Đáp án 29. NOT NULL

Có. `'null'::jsonb` là một giá trị JSONB nên không vi phạm `NOT NULL`. Muốn chỉ nhận JSON object, thêm `CHECK(jsonb_typeof(doc)='object')`.

### Đáp án 30. PATCH

Theo contract đã nêu:

- `{}` → email vẫn là `old@example.com`.
- `{"email":null}` → email trở thành SQL NULL trong cột relational nullable hoặc có thao tác clear tương ứng.
- `{"email":"new@example.com"}` → email thành `new@example.com`.

Phải dùng presence check trước khi chuyển `->>`; không thể chỉ dựa vào `COALESCE`.

### Đáp án 31. Jackson

- `root.get("email")` trả Java null khi field missing.
- `root.path("email")` trả MissingNode khi field missing.
- Khi field có JSON null, cả hai trả node tương ứng NullNode; kiểm tra `isNull()`.

Nếu dùng `get`, cần kiểm tra `email != null` trước khi gọi method trên node.

### Đáp án 32. JDBC

SQL NULL ở cột `doc` được driver phản ánh qua Java null khi gọi `getString`. JSONB null là giá trị hợp lệ, khi chuyển sang JSON text được biểu diễn bằng bốn ký tự `null`. JSON parser như Jackson có thể parse nó thành NullNode. Không dùng `"null".equals(jsonText)` để suy ra SQL NULL.

### Đáp án 33. JSONPath

Trên PostgreSQL 12+:

```sql
SELECT
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email'
    ) AS path_exists,
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email ? (@ == null)'
    ) AS path_has_json_null;
```

Cả hai TRUE. Với document `{}`, cả hai FALSE.

### Đáp án 34. GIN operator class

`jsonb_ops` hỗ trợ một số toán tử key-exists như `?`; `jsonb_path_ops` không hỗ trợ `?` theo cùng cách. Vì thế chọn path_ops cho hot query chủ yếu `?` có thể khiến index không được dùng cho toán tử quan trọng ấy. Cần xét operator support và đo plan.

### Đáp án 35. Native SQL array

Không cùng kiểu. `ARRAY[NULL::integer,7]` là `integer[]` của SQL; `'[null,7]'::jsonb` là giá trị jsonb array. `jsonb_array_length` nhận jsonb array, không phải native `integer[]`. Với native array, dùng hàm/biểu thức mảng PostgreSQL tương ứng như `array_length` hoặc `cardinality`.

### Đáp án 36. Pipeline

- `{"changes":{}}` → UNCHANGED.
- `{"changes":{"phone":null}}` → CLEAR.
- `{"changes":{"phone":"123"}}` → SET.

Nếu chỉ lưu một cột `phone text` nullable, hai trường hợp đầu có thể cùng SQL NULL nhưng có hành động khác nhau. Lưu raw JSON/presence/action.

### Đáp án 37. jsonb_build_object

```sql
SELECT
    jsonb_build_object('email', NULL::text)
        AS from_sql_null,
    jsonb_build_object('email', 'null'::jsonb)
        AS from_json_null,
    jsonb_build_object('email', 'null'::text)
        AS from_text;
```

Hai kết quả đầu là `{"email":null}`, kết quả cuối là `{"email":"null"}`. Chỉ từ hai output giống nhau đầu tiên không biết nguồn từng là SQL NULL hay JSON null.

### Đáp án 38. Kiểm tra JSON string

`->>` chuyển JSON boolean/number thành text, vì vậy điều kiện text không NULL nhận cả các giá trị không phải string. Nên dùng:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND jsonb_typeof(doc -> 'email') = 'string';
```

Nếu cần không rỗng, thêm `length(doc ->> 'email') > 0`. Nếu cần địa chỉ email hợp lệ, còn phải validation nghiệp vụ.

### Đáp án 39. PATCH với COALESCE

`patch_doc ->> 'email'` là SQL NULL với cả JSON null lẫn missing; `COALESCE(...,email)` giữ email cũ trong cả hai trường hợp. Nó vì thế **không thực hiện clear** khi nhận `{"email":null}`.

Mẫu đúng theo contract:

```sql
SET email =
    CASE
        WHEN patch_doc ? 'email'
            THEN patch_doc ->> 'email'
        ELSE email
    END
```

Chỉ là phần `SET` minh họa; câu UPDATE thật còn cần kiểm tra patch là object, type email là string/null, quyền cập nhật và target row.

### Đáp án 40. Bộ test cases

| Input | Kỳ vọng phân loại | Ý nghĩa |
| --- | --- | --- |
| SQL NULL document | `SQL_NULL_DOCUMENT` | Không có document SQL. |
| JSON document `null` | `NOT_AN_OBJECT` hoặc `DOCUMENT_JSON_NULL` | Root JSON null, không phải object patch. |
| `{}` | `MISSING` | Không có email. |
| `{"email":null}` | `JSON_NULL` | Client gửi explicit JSON null. |
| `{"email":"null"}` | `STRING` | Chuỗi chữ "null", không clear tự động. |
| `{"email":""}` | `EMPTY_STRING` | Có field string rỗng; policy cho phép hoặc từ chối riêng. |
| `{"email":false}` | `OTHER_JSON_VALUE` | JSON boolean, thường từ chối với email. |
| `{"email":0}` | `OTHER_JSON_VALUE` | JSON number, thường từ chối. |
| `{"profile":{"email":null}}` | Top-level email `MISSING` | Nested email không phải top-level email. |
| `{"email":{}}` | `OTHER_JSON_VALUE` | JSON object rỗng không phải email string. |

Khi viết automated tests, nên khẳng định **giá trị lưu sau UPDATE**, **trạng thái có/không có key** và **HTTP error policy** cho từng input, không chỉ khẳng định cột text kết quả SQL NULL.

## 37. Checklist xử lý JSON null, SQL NULL và missing trong dự án

1. **Xác định tầng dữ liệu:** đang xét cả cột SQL, root JSON, object key, nested path hay array index?
2. **Đừng nhầm literal:** `null` JSON khác `"null"` JSON string.
3. **Đừng nhầm root:** `NULL::jsonb` khác `'null'::jsonb` và `'{}'::jsonb`.
4. **Chọn toán tử đúng:** `->`/`#>` giữ JSONB type; `->>`/`#>>` trả SQL text.
5. **Kiểm tra root type khi cần:** `jsonb_typeof(doc)='object'` trước khi xử lý key object.
6. **Kiểm tra key presence trước:** dùng `doc ? 'key'` hoặc cơ chế path phù hợp khi missing khác null.
7. **Kiểm tra JSON type:** `jsonb_typeof(doc->'key')='null'` cho JSON null, `='string'` cho string.
8. **Không dùng = NULL:** dùng `IS NULL` cho SQL NULL, và so sánh JSONB với `'null'::jsonb` khi cần.
9. **Đọc UNKNOWN đúng:** `WHERE` không chọn predicate UNKNOWN; `CHECK` lại có thể chấp nhận UNKNOWN.
10. **Dùng COALESCE có chủ đích:** nó xử lý SQL NULL, không tự thay giá trị JSONB null.
11. **Giữ presence trước khi convert:** `jsonb_to_record` và DTO nullable có thể làm mất trạng thái missing.
12. **Đếm đúng:** `COUNT(doc->'key')` và `COUNT(doc->>'key')` có thể khác khi gặp JSON null.
13. **Phân biệt array positions:** phần tử JSON null có tồn tại và được tính độ dài; out-of-range index không tồn tại.
14. **Không dùng ? để tìm nested keys bừa bãi:** chọn truy xuất object cha hoặc JSONPath.
15. **Đừng dùng JSONPath lax như schema validator duy nhất:** kiểm tra kiểu tại các cấp cần thiết.
16. **Đặt null và xóa key khác nhau:** `jsonb_set(...,'null'::jsonb)` so với `-`/`#-`.
17. **Cẩn thận SQL NULL new_value:** dùng `jsonb_set_lax` với mode rõ trên major hỗ trợ.
18. **Không strip nulls vô điều kiện:** có thể làm mất explicit null từ request hoặc event.
19. **Ràng buộc đủ lớp:** `NOT NULL` cho SQL NULL, CHECK object type, CHECK field presence/type/format.
20. **Index theo semantics thật:** GIN `jsonb_ops` cho một số `?` queries, expression index cho `->>` khi phù hợp.
21. **Giao thức PATCH rõ:** JSON Merge Patch/JSON Patch/custom PATCH có hành vi khác nhau với null.
22. **Lớp Java rõ:** phân biệt Java null, Jackson NullNode và MissingNode.
23. **JDBC rõ:** `getString` SQL NULL không phải JSON text `null`.
24. **Pipelines không đánh mất ý định:** lưu presence/action khi missing ≠ clear.
25. **Test toàn bộ trạng thái:** SQL NULL, JSON null, missing, "null", "", false, 0, arrays, nested và object sai kiểu.
26. **Bảo mật và concurrency:** field presence đúng chưa đủ; còn cần authorization, validation, versioning và transaction.

## 38. Tổng kết

Trong PostgreSQL, **SQL NULL**, **JSON null** và **thành phần JSON không tồn tại** là ba khái niệm khác nhau:

- **SQL NULL**: không có giá trị SQL. Ví dụ `NULL::jsonb` hoặc kết quả truy xuất một key/path không tồn tại.
- **JSON null**: một giá trị JSON có thật, kiểu `null`. Ví dụ `'null'::jsonb` hoặc `'{"email":null}'::jsonb -> 'email'`.
- **Missing**: object không có key hoặc array không có index. PostgreSQL thường biểu diễn kết quả trích xuất missing bằng **SQL NULL**, nhưng thông tin presence có thể xác định bằng `?`, kiểm tra cấu trúc hoặc JSONPath.

Những quy tắc cần nhớ:

- **`->` và `#>` giữ kiểu JSON**: JSON null vẫn là giá trị JSONB không SQL NULL.
- **`->>` và `#>>` chuyển sang text**: JSON null và missing đều trở thành SQL NULL.
- **`jsonb_typeof(...)= 'null'`** kiểm tra kiểu JSON null; `IS NULL` kiểm tra SQL NULL của biểu thức.
- **`doc ? 'key'`** phân biệt key hiện hữu với key missing ở top-level object; giá trị JSON null vẫn được coi là có key.
- **`@> '{"key":null}'::jsonb`** có thể kiểm tra containment của JSON null, khác hoàn toàn việc hỏi chung key có tồn tại.
- **`COALESCE` xử lý SQL NULL**, không thay giá trị JSONB null; dùng nó sau `->>` có thể gộp missing và JSON null.
- **`jsonb_set` đặt giá trị**, `-`/`#-` xóa key/path, `jsonb_set_lax` cho phép chọn hành vi khi new_value SQL NULL ở phiên bản phù hợp.
- **CHECK và COUNT dùng semantics SQL NULL**, không tự hiểu JSON null theo mục đích nghiệp vụ.
- **API PATCH và data pipelines cần presence bit** nếu missing nghĩa “không thay đổi” còn JSON null nghĩa “clear/xóa”.

Một nguyên tắc đơn giản để tránh lỗi:

> **Trước khi đổi JSON thành text hoặc một DTO nullable, hãy xác định field có được cung cấp không; sau đó mới kiểm tra kiểu và giá trị của field.**

Nếu luôn tách hai câu hỏi **“thành phần có tồn tại không?”** và **“nếu tồn tại thì chứa giá trị JSON nào?”**, bạn sẽ xử lý đúng JSONB trong các truy vấn SQL, ràng buộc dữ liệu và luồng cập nhật ứng dụng.
