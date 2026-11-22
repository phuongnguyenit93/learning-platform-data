# Truy xuất đường dẫn JSON và phân biệt thiếu khóa với JSON null

Trong cơ sở dữ liệu quan hệ, một cột JSON thường chứa dữ liệu có cấu trúc linh hoạt: hồ sơ người dùng, cấu hình, thông tin đơn hàng, payload của sự kiện, phản hồi API hoặc thuộc tính bổ sung. Khác với cột SQL cố định, **một thuộc tính JSON có thể tồn tại, có thể không tồn tại, hoặc tồn tại nhưng chứa giá trị `null`**.

Ba payload sau nhìn rất gần nhau, nhưng không có cùng ý nghĩa:

```json
{"profile": {"phone": "0901234567"}}
```

```json
{"profile": {"phone": null}}
```

```json
{"profile": {}}
```

Trường hợp thứ nhất chứa số điện thoại. Trường hợp thứ hai có **khóa `phone` tồn tại** nhưng giá trị là **JSON `null`**. Trường hợp thứ ba **thiếu khóa `phone`**. Đó còn chưa kể trường hợp toàn bộ cột trong database là **SQL `NULL`**, hoặc thuộc tính `phone` chứa chuỗi văn bản `"null"`.

Một truy vấn chỉ lấy giá trị dưới dạng text có thể làm các trường hợp khác nhau **cùng trở thành SQL NULL**. Nếu ứng dụng dùng kết quả đó để quyết định “không cập nhật”, “xóa giá trị”, “giữ giá trị cũ” hoặc “đã nhập nhưng chưa xác minh”, sai lầm sẽ ảnh hưởng đến dữ liệu nghiệp vụ.

> **Quy tắc quan trọng nhất:** khi cần phân biệt **khóa vắng mặt** với **khóa có giá trị JSON `null`**, đừng chỉ đọc text bằng `->>` hoặc `#>>`. Phải kiểm tra **sự hiện diện của đường dẫn/khóa** hoặc giữ dạng JSON trước khi chuyển thành kiểu SQL.

Bài học thuộc **Database SQL → Dữ liệu mở rộng**. Phần thực hành chính sử dụng **PostgreSQL `jsonb`**, gồm `->`, `->>`, `#>`, `#>>`, `?`, `jsonb_typeof`, JSONPath và các thao tác cập nhật. Những mục sau so sánh MySQL, SQL Server, SQLite, Oracle; trình bày kiểu dữ liệu, index, tính đúng của API PATCH và nhiều bài tập thực hành.

## 1. Năm trạng thái phải đặt tên rõ

Khi đọc một thuộc tính trong JSON, có ít nhất năm tình huống:

| Tình huống | Ví dụ | Câu hỏi nghiệp vụ |
| --- | --- | --- |
| **Khóa tồn tại, có giá trị** | `{"phone":"0901"}` | Giá trị là gì? |
| **Khóa tồn tại, chứa JSON null** | `{"phone":null}` | Người gửi có chủ ý để trống/xóa/đánh dấu chưa biết? |
| **Khóa không tồn tại** | `{}` | Người gửi không cung cấp trường này? |
| **Cả cột SQL là NULL** | `payload IS NULL` | Không có tài liệu JSON trong hàng này? |
| **Khóa chứa chuỗi "null"** | `{"phone":"null"}` | Đây là bốn ký tự n-u-l-l, không phải null |

Có thêm nhiều giá trị dễ bị nhầm:

```json
{"count": 0, "active": false, "name": "", "tags": [], "options": {}}
```

`0`, `false`, chuỗi rỗng `""`, mảng rỗng `[]` và object rỗng `{}` đều là **giá trị JSON hiện diện**. Chúng không tương đương với thiếu khóa hay JSON null.

### 1.1. Ví dụ API cập nhật thông tin liên lạc

Giả sử hệ thống nhận ba request:

```json
{"display_name": "An"}
```

```json
{"display_name": "An", "phone": null}
```

```json
{"display_name": "An", "phone": ""}
```

Tùy hợp đồng API:

- **Thiếu `phone`:** có thể mang nghĩa “không thay đổi số điện thoại cũ”.
- **`phone: null`:** có thể mang nghĩa “xóa số”, “chưa cung cấp” hoặc “đánh dấu unknown”.
- **`phone: ""`:** là một chuỗi rỗng được gửi rõ ràng; có thể bị validation từ chối hoặc được lưu theo yêu cầu.

Database không thể tự suy đoán mục đích nghiệp vụ. Điều nó giúp ta làm là **nhận biết đúng trạng thái dữ liệu** để ứng dụng áp dụng hợp đồng.

### 1.2. SQL NULL không phải JSON null

Trong PostgreSQL:

```sql
SELECT
    NULL::jsonb AS sql_null_document,
    'null'::jsonb AS json_null_document,
    '"null"'::jsonb AS json_string_null;
```

Ba biểu thức lần lượt là:

1. **SQL NULL** có kiểu `jsonb`, nghĩa là không có giá trị SQL cho cột/biểu thức.
2. **Giá trị JSON null** được lưu bên trong một giá trị `jsonb` **không phải SQL NULL**.
3. **Giá trị JSON string** có nội dung bốn ký tự `null`.

Nhớ phân biệt ba tầng: **giá trị SQL → tài liệu JSON → trường/đường dẫn bên trong JSON**.

## 2. PostgreSQL: json và jsonb khác gì?

PostgreSQL cung cấp hai kiểu chính để lưu JSON:

| Kiểu | Đặc điểm khái quát | Tình huống thường dùng |
| --- | --- | --- |
| `json` | Giữ nội dung văn bản JSON đã nhập theo biểu diễn gốc gần hơn; được kiểm tra cú pháp JSON | Khi cần giữ biểu diễn ban đầu hoặc tính chất nhập liệu cụ thể |
| `jsonb` | Lưu biểu diễn nhị phân đã phân tích; hỗ trợ nhiều phép toán và index GIN | Phần lớn truy vấn/lọc/cập nhật cấu trúc JSON trong PostgreSQL |

`jsonb` không giữ thứ tự các khóa object theo đúng văn bản đầu vào và không giữ mọi đặc điểm trình bày. Khi văn bản object có **khóa trùng**, `jsonb` chỉ giữ một giá trị tương ứng theo quy tắc của PostgreSQL (thường giá trị cuối). Vì thế, một quy trình cần phát hiện duplicate JSON keys phải xử lý trước khi dữ liệu đã được chuẩn hóa vào `jsonb`.

Trong bài học, ta dùng `jsonb` để có toán tử `?`, `@>`, `jsonb_set` và index hỗ trợ.

### 2.1. JSON object và JSON array là hai cấu trúc khác nhau

```json
{"contact": {"phone": null}}
```

là object có khóa `contact`.

```json
[{"phone": null}, {"phone": "0901"}]
```

là array gồm hai object. Truy xuất array theo chỉ số hoặc qua JSONPath khác truy xuất object theo khóa. Không thể mặc định mọi document có root object hoặc `profile` luôn là object.

### 2.2. JSON null vẫn là một giá trị của jsonb

```sql
SELECT
    'null'::jsonb IS NULL AS json_null_is_sql_null,
    NULL::jsonb IS NULL AS sql_null_is_sql_null,
    jsonb_typeof('null'::jsonb) AS json_null_type,
    jsonb_typeof('"null"'::jsonb) AS json_string_type;
```

Kết quả logic:

| Cột | Kết quả |
| --- | --- |
| `json_null_is_sql_null` | `false` |
| `sql_null_is_sql_null` | `true` |
| `json_null_type` | `null` (chuỗi văn bản chỉ tên JSON type) |
| `json_string_type` | `string` |

Đặc biệt, `jsonb_typeof('null'::jsonb)` trả **text `'null'`**, còn `jsonb_typeof(NULL::jsonb)` trả **SQL NULL**. Đây là nền tảng của nhiều bài phân biệt trạng thái bên dưới.

## 3. Tạo dữ liệu thực hành chứa mọi trạng thái

Chạy trong một session PostgreSQL. Các bảng `TEMP` tồn tại trong phiên hiện tại và không yêu cầu thay đổi schema của ứng dụng.

```sql
CREATE TEMP TABLE demo_json_records (
    record_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    payload JSONB
);

INSERT INTO demo_json_records
    (record_id, tenant_id, description, payload)
VALUES
    (
        1, 10, 'Email có giá trị, phone là JSON null',
        '{
          "profile": {
            "email": "an@example.com",
            "phone": null,
            "preferences": {"theme": "dark", "alerts": false}
          },
          "tags": ["vip", "new"],
          "note": ""
        }'::jsonb
    ),
    (
        2, 10, 'Email JSON null',
        '{
          "profile": {
            "email": null,
            "phone": "0912345678",
            "preferences": {}
          },
          "tags": []
        }'::jsonb
    ),
    (
        3, 10, 'Có profile, thiếu email',
        '{
          "profile": {"name": "Chi"},
          "tags": null
        }'::jsonb
    ),
    (
        4, 10, 'Profile là JSON null',
        '{"profile": null}'::jsonb
    ),
    (
        5, 10, 'Thiếu profile',
        '{"tags": []}'::jsonb
    ),
    (
        6, 10, 'Toàn bộ cột là SQL NULL',
        NULL::jsonb
    ),
    (
        7, 10, 'Toàn bộ tài liệu là JSON null',
        'null'::jsonb
    ),
    (
        8, 10, 'Email là chuỗi null, phone là chuỗi rỗng',
        '{
          "profile": {
            "email": "null",
            "phone": "",
            "preferences": {"theme": null}
          },
          "tags": ["null", null]
        }'::jsonb
    ),
    (
        9, 10, 'Email sai kiểu boolean',
        '{
          "profile": {"email": false},
          "price": 0,
          "active": false
        }'::jsonb
    ),
    (
        10, 10, 'Root là mảng JSON',
        '[]'::jsonb
    ),
    (
        11, 10, 'Root là chuỗi JSON',
        '"hello"'::jsonb
    ),
    (
        12, 10, 'Email nằm ở một nhánh lồng sâu khác',
        '{
          "profile": {
            "contact": {"email": "nested@example.com"}
          },
          "items": [
            {"sku": "A", "qty": 2},
            {"sku": "B", "qty": null}
          ]
        }'::jsonb
    ),
    (
        13, 20, 'Tenant khác có email null',
        '{"profile": {"email": null}}'::jsonb
    );
```

Kiểm tra danh sách:

```sql
SELECT
    record_id,
    tenant_id,
    description,
    jsonb_typeof(payload) AS root_json_type
FROM demo_json_records
ORDER BY record_id;
```

Các trường hợp quan trọng:

| record_id | Tình trạng `profile.email` trực tiếp |
| ---: | --- |
| 1 | Khóa có, kiểu string, giá trị `"an@example.com"` |
| 2 | Khóa có, JSON null |
| 3 | `profile` có nhưng thiếu khóa `email` |
| 4 | `profile` là JSON null, không phải object có khóa email |
| 5 | Thiếu khóa `profile` |
| 6 | Cả cột `payload` là SQL NULL |
| 7 | Root `payload` là JSON null |
| 8 | Khóa có, kiểu string, giá trị `"null"` |
| 9 | Khóa có, kiểu boolean, giá trị `false` |
| 10 | Root là array `[]` |
| 11 | Root là string `"hello"` |
| 12 | Không có `profile.email` trực tiếp, chỉ có `profile.contact.email` |
| 13 | JSON null giống record 2 nhưng thuộc tenant 20 |

**Vì sao có tenant 20?** Khi thiết kế bộ lọc JSON trong ứng dụng nhiều tenant, vẫn phải lọc `tenant_id` bằng cột quan hệ/phân quyền tương ứng. JSONPath không tự bảo vệ quyền truy cập dữ liệu.

## 4. Các toán tử PostgreSQL: `->`, `->>`, `#>`, `#>>`

### 4.1. Lấy một phần tử dưới dạng JSON: `->`

```sql
SELECT
    record_id,
    payload -> 'profile' AS profile_json,
    payload -> 'profile' -> 'email' AS email_json
FROM demo_json_records
WHERE tenant_id = 10
ORDER BY record_id;
```

`->` trả một giá trị JSON/JSONB, vẫn giữ **kiểu JSON** của phần tử. Nếu khóa không tồn tại hoặc cấu trúc không khớp, kết quả truy xuất thường là **SQL NULL**. Nếu khóa tồn tại và có JSON null, kết quả là **giá trị `'null'::jsonb`**, không phải SQL NULL.

Ví dụ cho record 2:

```sql
SELECT
    payload -> 'profile' -> 'email' AS email_json,
    (payload -> 'profile' -> 'email') IS NULL AS is_sql_null,
    jsonb_typeof(payload -> 'profile' -> 'email') AS json_type
FROM demo_json_records
WHERE record_id = 2;
```

Về mặt logic:

- `email_json` là **JSON null**.
- `is_sql_null` = **false**.
- `json_type` = chuỗi text **`'null'`**.

Cho record 3, đường dẫn `profile.email` thiếu khóa `email`, nên `email_json` là **SQL NULL** và `jsonb_typeof(...)` cũng là **SQL NULL**.

### 4.2. Lấy giá trị dưới dạng text: `->>`

```sql
SELECT
    record_id,
    payload -> 'profile' ->> 'email' AS email_text
FROM demo_json_records
WHERE record_id IN (1, 2, 3, 8, 9)
ORDER BY record_id;
```

Ý nghĩa:

| ID | JSON gốc tại `profile.email` | `->>` trả |
| ---: | --- | --- |
| 1 | `"an@example.com"` | text `an@example.com` |
| 2 | JSON `null` | **SQL NULL** |
| 3 | Khóa thiếu | **SQL NULL** |
| 8 | JSON string `"null"` | text `null`, **không phải SQL NULL** |
| 9 | JSON boolean `false` | text `false` |

**Đây là bẫy cốt lõi:** `->>` hợp nhất “khóa thiếu” và “JSON null” thành SQL NULL. Nếu chỉ chọn cột `email_text`, bạn đã mất thông tin liệu khách **không gửi email** hay **gửi email: null**.

Mặt khác, `->>` còn chuyển số, boolean và những giá trị JSON khác thành dạng text khi có thể. Không xác định kiểu JSON bằng cách chỉ xem chuỗi trả về.

### 4.3. Đường dẫn nhiều cấp: `#>` và `#>>`

`#>` nhận một đường dẫn `text[]` và trả JSONB:

```sql
SELECT
    record_id,
    payload #> '{profile,email}' AS email_json,
    payload #>> '{profile,email}' AS email_text
FROM demo_json_records
WHERE record_id IN (1, 2, 3, 8)
ORDER BY record_id;
```

Đây là hai cách lấy cùng đường dẫn với kiểu trả khác nhau:

```sql
payload -> 'profile' -> 'email'
payload #> '{profile,email}'
```

và:

```sql
payload -> 'profile' ->> 'email'
payload #>> '{profile,email}'
```

Khi truy vấn đường dẫn sâu, `#>` hoặc `#>>` có thể dễ đọc hơn chuỗi nhiều dấu mũi tên. Nhưng chúng **không tự kiểm tra tính hiện diện** khác với những quy tắc vừa nêu.

### 4.4. Lấy phần tử array bằng chỉ số

Trong PostgreSQL, có thể dùng chỉ số nguyên với `->`:

```sql
SELECT
    payload -> 'items' -> 0 AS first_item,
    payload -> 'items' -> 0 ->> 'sku' AS first_sku,
    payload #> '{items,1,qty}' AS second_qty_json
FROM demo_json_records
WHERE record_id = 12;
```

Kết quả:

- `first_item` là JSON object `{"sku":"A","qty":2}`.
- `first_sku` là text `A`.
- `second_qty_json` là **JSON null**, vì phần tử thứ hai có khóa `qty` với giá trị null.

Chỉ số array bắt đầu từ **0**. Truy xuất một chỉ số không tồn tại hoặc sai cấu trúc bằng toán tử này thường trả SQL NULL thay vì tạo một object rỗng.

### 4.5. Bảng nhớ nhanh

| Toán tử | Đầu vào thứ hai | Kết quả | Ví dụ |
| --- | --- | --- | --- |
| `->` | Khóa text hoặc chỉ số integer | JSON/JSONB | `payload -> 'profile'` |
| `->>` | Khóa text hoặc chỉ số integer | SQL text | `payload ->> 'active'` |
| `#>` | Đường dẫn text[] | JSON/JSONB | `payload #> '{profile,email}'` |
| `#>>` | Đường dẫn text[] | SQL text | `payload #>> '{profile,email}'` |

## 5. So sánh SQL NULL, JSON null, thiếu khóa và chuỗi "null"

Lệnh sau nhìn trực tiếp sự khác nhau:

```sql
SELECT
    record_id,
    (payload #> '{profile,email}') IS NULL
        AS path_result_is_sql_null,
    (payload #> '{profile,email}') = 'null'::jsonb
        AS path_is_json_null,
    jsonb_typeof(payload #> '{profile,email}')
        AS path_json_type,
    payload #>> '{profile,email}'
        AS path_text
FROM demo_json_records
WHERE record_id IN (1, 2, 3, 6, 8, 9)
ORDER BY record_id;
```

Đọc logic của các cột:

| ID | `IS NULL` trên `#>` | `= 'null'::jsonb` | `jsonb_typeof` | `#>>` |
| ---: | --- | --- | --- | --- |
| 1 | false | false | `string` | `an@example.com` |
| 2 | false | **true** | `null` (text) | **SQL NULL** |
| 3 | **true** | **SQL NULL/UNKNOWN** | **SQL NULL** | **SQL NULL** |
| 6 | **true** | **SQL NULL/UNKNOWN** | **SQL NULL** | **SQL NULL** |
| 8 | false | false | `string` | `null` (text) |
| 9 | false | false | `boolean` | `false` (text) |

### 5.1. `IS NULL` trên đường dẫn JSON phát hiện điều gì?

```sql
WHERE payload #> '{profile,email}' IS NULL
```

trả những hàng mà phép truy xuất cho **SQL NULL**: khóa thiếu, cấu trúc trung gian không khớp, hoặc cột payload SQL NULL. Nó **không** chọn hàng có trường JSON null ở đường dẫn ấy.

Nếu mục tiêu là “khóa email vắng mặt” trong một object profile tồn tại, điều kiện trên còn **quá rộng**: nó có thể chứa cả hàng thiếu profile, root JSON null hoặc payload SQL NULL.

### 5.2. So sánh với JSON null

```sql
WHERE payload #> '{profile,email}' = 'null'::jsonb
```

chọn hàng mà đường dẫn thực sự trả **giá trị JSON null**. Với dữ liệu mẫu tenant 10, đó là **record 2**. Nếu bao gồm mọi tenant, thêm **record 13**.

### 5.3. Chuỗi "null" khác JSON null

```sql
SELECT
    '"null"'::jsonb = 'null'::jsonb AS equal_json_values,
    jsonb_typeof('"null"'::jsonb) AS string_type,
    jsonb_typeof('null'::jsonb) AS null_type;
```

Kết quả `equal_json_values = false`. Không dùng:

```sql
WHERE payload #>> '{profile,email}' = 'null'
```

để tìm JSON null: câu ấy tìm **văn bản `'null'`**, tức record 8 trong dữ liệu lab, chứ không chọn record 2.

### 5.4. Nếu cần chỉ rõ toàn bộ tài liệu SQL NULL

```sql
SELECT record_id
FROM demo_json_records
WHERE payload IS NULL;
-- Record 6.
```

Đừng dùng `payload = 'null'::jsonb` để tìm SQL NULL: biểu thức này tìm **JSON null root**.

## 6. Dùng toán tử `?` để kiểm tra sự tồn tại của khóa

Trong PostgreSQL, `?` là toán tử kiểm tra một **khóa object cấp trên cùng** hoặc **phần tử string của array cấp trên cùng** có tồn tại trong giá trị `jsonb` không.

Ví dụ:

```sql
SELECT
    record_id,
    payload ? 'profile' AS has_profile_key
FROM demo_json_records
WHERE tenant_id = 10
ORDER BY record_id;
```

Với root là object:

- Record 1–4, 8–9, 12 có khóa `profile`.
- Record 5 thiếu `profile`.
- Record 6 có payload SQL NULL, biểu thức `payload ? 'profile'` có thể trả **SQL NULL**.
- Record 7 root JSON null; không có khóa object `profile`.

### 6.1. Có khóa không có nghĩa giá trị khác JSON null

```sql
SELECT
    record_id,
    payload ? 'profile' AS has_profile,
    jsonb_typeof(payload -> 'profile') AS profile_type
FROM demo_json_records
WHERE record_id IN (3, 4, 5);
```

Ở record 4, `has_profile = true` dù `profile` là JSON null. Ở record 5, `has_profile = false` vì khóa không có.

### 6.2. `?` chỉ kiểm tra cấp đang đứng

**Sai nếu muốn kiểm tra khóa lồng sâu:**

```sql
SELECT payload ? 'email'
FROM demo_json_records
WHERE record_id = 1;
```

Truy vấn này kiểm tra `email` ở **root**. Nhưng `email` nằm dưới `profile`, nên cần:

```sql
SELECT
    (payload -> 'profile') ? 'email' AS has_email_key
FROM demo_json_records
WHERE record_id = 1;
```

Hoặc:

```sql
SELECT
    jsonb_typeof(payload -> 'profile') AS parent_type,
    (payload -> 'profile') ? 'email' AS has_email
FROM demo_json_records
WHERE record_id = 2;
```

Giá trị `has_email` là **true** đối với record 2: khóa tồn tại nhưng chứa JSON null.

### 6.3. Cẩn thận khi parent không tồn tại

Nếu `payload -> 'profile'` trả **SQL NULL**, phép `? 'email'` trên SQL NULL cũng trả SQL NULL thay vì false thông thường.

Khi tạo cờ boolean không muốn giá trị UNKNOWN:

```sql
SELECT
    record_id,
    COALESCE(
        (payload -> 'profile') ? 'email',
        FALSE
    ) AS has_direct_email_key
FROM demo_json_records
ORDER BY record_id;
```

Nhưng cờ này **chưa chứng minh parent là object**. Toán tử `?` cũng có nghĩa với array chứa string. Nếu yêu cầu cấu trúc phải là object:

```sql
SELECT
    record_id,
    CASE
        WHEN jsonb_typeof(payload -> 'profile') = 'object'
        THEN COALESCE(
            (payload -> 'profile') ? 'email',
            FALSE
        )
        ELSE FALSE
    END AS has_email_in_profile_object
FROM demo_json_records
ORDER BY record_id;
```

### 6.4. `?` cũng tìm string trong array

```sql
SELECT
    '["vip", "new"]'::jsonb ? 'vip' AS array_has_vip,
    '{"vip": null}'::jsonb ? 'vip' AS object_has_vip_key;
```

Hai biểu thức đều **true**, nhưng ý nghĩa khác nhau:

- Array: có phần tử string `"vip"`.
- Object: có khóa `"vip"`, bất kể giá trị là JSON null.

Vì vậy, nếu muốn **kiểm tra khóa JSON**, hãy bảo đảm giá trị đang xét là **object**, hoặc dùng cấu trúc/schema đã được ràng buộc là object.

## 7. Chẩn đoán đường dẫn thiếu khóa ở cấp nào

Một đường dẫn `profile.contact.email` có thể không tìm thấy vì:

1. Root payload không phải object.
2. Root object không có khóa `profile`.
3. `profile` tồn tại nhưng là JSON null hoặc kiểu khác object.
4. `profile` là object nhưng thiếu `contact`.
5. `contact` là JSON null hoặc không phải object.
6. `contact` là object nhưng thiếu `email`.
7. `email` có tồn tại nhưng chứa JSON null.

Chỉ dùng `payload #>> '{profile,contact,email}' IS NULL` sẽ **gộp quá nhiều trường hợp**.

### 7.1. Phân loại một đường dẫn hai cấp

Ví dụ phân loại `profile.email`:

```sql
SELECT
    record_id,
    CASE
        WHEN payload IS NULL
            THEN 'SQL_NULL_DOCUMENT'
        WHEN jsonb_typeof(payload) = 'null'
            THEN 'JSON_NULL_DOCUMENT'
        WHEN jsonb_typeof(payload) <> 'object'
            THEN 'ROOT_NOT_OBJECT'
        WHEN NOT (payload ? 'profile')
            THEN 'PROFILE_MISSING'
        WHEN jsonb_typeof(payload -> 'profile') = 'null'
            THEN 'PROFILE_JSON_NULL'
        WHEN jsonb_typeof(payload -> 'profile') <> 'object'
            THEN 'PROFILE_NOT_OBJECT'
        WHEN NOT ((payload -> 'profile') ? 'email')
            THEN 'EMAIL_MISSING'
        WHEN jsonb_typeof(payload #> '{profile,email}') = 'null'
            THEN 'EMAIL_JSON_NULL'
        ELSE 'EMAIL_PRESENT_NON_NULL'
    END AS email_state
FROM demo_json_records
WHERE tenant_id = 10
ORDER BY record_id;
```

Ý nghĩa trên dữ liệu mẫu:

| ID | Trạng thái |
| ---: | --- |
| 1 | `EMAIL_PRESENT_NON_NULL` |
| 2 | `EMAIL_JSON_NULL` |
| 3 | `EMAIL_MISSING` |
| 4 | `PROFILE_JSON_NULL` |
| 5 | `PROFILE_MISSING` |
| 6 | `SQL_NULL_DOCUMENT` |
| 7 | `JSON_NULL_DOCUMENT` |
| 8 | `EMAIL_PRESENT_NON_NULL`, dù string là `"null"` |
| 9 | `EMAIL_PRESENT_NON_NULL`, dù kiểu là boolean |
| 10 | `ROOT_NOT_OBJECT` |
| 11 | `ROOT_NOT_OBJECT` |
| 12 | `EMAIL_MISSING` ở đường dẫn trực tiếp |

**Vì sao dùng thứ tự CASE như vậy?** Khi parent không tồn tại, kiểm tra khóa ở con thường cho SQL NULL/UNKNOWN; bằng cách kiểm tra root và parent **trước**, những phép kiểm `?` sau đó chỉ chạy cho cấu trúc đã xác nhận phù hợp.

### 7.2. Có khóa nhưng sai kiểu vẫn là một trạng thái riêng

Record 9 có `{"email":false}`. Dữ liệu **hiện diện** nhưng email là JSON boolean, không phải string email hợp lệ. Nếu ứng dụng chỉ kiểm:

```sql
WHERE payload #> '{profile,email}' IS NOT NULL
```

thì boolean false vẫn lọt qua.

Để yêu cầu email là string:

```sql
SELECT record_id, payload #>> '{profile,email}' AS email
FROM demo_json_records
WHERE jsonb_typeof(payload #> '{profile,email}') = 'string'
  AND tenant_id = 10;
```

Kết quả gồm record 1 và record 8. **Record 8 vẫn có string `"null"`**, vì kiểm kiểu string chưa phải kiểm email hợp lệ. Cần validation định dạng và quy tắc domain riêng.

### 7.3. Đường dẫn lồng sâu

Record 12 có:

```json
{"profile":{"contact":{"email":"nested@example.com"}}}
```

Truy vấn đúng:

```sql
SELECT
    payload #>> '{profile,contact,email}' AS nested_email,
    jsonb_typeof(payload #> '{profile,contact,email}') AS nested_type
FROM demo_json_records
WHERE record_id = 12;
```

Không coi việc `profile.email` thiếu khóa là bằng chứng “tài liệu hoàn toàn không có email”; **đó chỉ là thiếu tại đường dẫn đã được định nghĩa**. Một API/schema phải xác định chính xác đường dẫn nào có ý nghĩa nghiệp vụ.

## 8. Một bảng logic của các phép kiểm

Giả sử `x` là kết quả của `payload #> '{profile,email}'`:

| Trường hợp | `x IS NULL` | `x = 'null'::jsonb` | `jsonb_typeof(x)` | `#>>` |
| --- | --- | --- | --- | --- |
| Khóa có, string `"abc"` | false | false | `string` | text `abc` |
| Khóa có, JSON null | false | true | text `null` | SQL NULL |
| Khóa vắng mặt | true | UNKNOWN | SQL NULL | SQL NULL |
| Parent không đúng cấu trúc | true | UNKNOWN | SQL NULL | SQL NULL |
| Cột SQL NULL | true | UNKNOWN | SQL NULL | SQL NULL |
| Khóa có, JSON string `"null"` | false | false | `string` | text `null` |
| Khóa có, JSON `false` | false | false | `boolean` | text `false` |
| Khóa có, JSON `0` | false | false | `number` | text `0` |

Chú ý `UNKNOWN` trong SQL là giá trị logic ba trạng thái, thường được hiển thị là NULL khi biểu thức boolean so sánh với SQL NULL. Trong `WHERE`, chỉ biểu thức **TRUE** được giữ.

### 8.1. Cách lọc theo mục tiêu

**Chỉ nhận giá trị email JSON string:**

```sql
WHERE jsonb_typeof(payload #> '{profile,email}') = 'string'
```

**Chỉ nhận email JSON null (khóa hiện diện):**

```sql
WHERE payload #> '{profile,email}' = 'null'::jsonb
```

**Chỉ nhận object profile hợp lệ nhưng thiếu email:**

```sql
WHERE jsonb_typeof(payload -> 'profile') = 'object'
  AND NOT ((payload -> 'profile') ? 'email')
```

**Chỉ nhận toàn bộ tài liệu SQL NULL:**

```sql
WHERE payload IS NULL
```

**Chỉ nhận root JSON null:**

```sql
WHERE payload = 'null'::jsonb
```

Kết hợp `tenant_id` và điều kiện phân quyền trên bảng nguồn trong ứng dụng thực.

## 9. Kiểm tra containment bằng `@>` với JSON null

PostgreSQL `jsonb` hỗ trợ toán tử containment `@>`: giá trị bên trái có chứa cấu trúc/giá trị JSON bên phải theo quy tắc `jsonb` không.

Ví dụ:

```sql
SELECT
    record_id,
    payload @> '{"profile":{"email":null}}'::jsonb
        AS has_email_json_null
FROM demo_json_records
WHERE record_id IN (1, 2, 3, 4, 5, 13)
ORDER BY record_id;
```

Kết quả:

- Record 2 và 13: **true**.
- Record 1: email là string → false.
- Record 3: thiếu email → false.
- Record 4: profile là JSON null → false.
- Record 5: thiếu profile → false.

Điều kiện gọn:

```sql
SELECT record_id
FROM demo_json_records
WHERE tenant_id = 10
  AND payload @> '{"profile":{"email":null}}'::jsonb;
-- Chỉ record 2 trong dữ liệu mẫu.
```

### 9.1. Containment khác key existence

```sql
payload @> '{"profile":{"email":null}}'::jsonb
```

kiểm cả **sự hiện diện** lẫn **giá trị JSON null** tại cấu trúc yêu cầu.

```sql
(payload -> 'profile') ? 'email'
```

chỉ kiểm khóa email hiện diện ở parent cấp ấy (nếu parent có cấu trúc phù hợp), bất kể giá trị null, string hay boolean.

### 9.2. Dùng `@>` cho trạng thái phức tạp

```sql
SELECT record_id
FROM demo_json_records
WHERE payload @> '{"profile":{"preferences":{"alerts":false}}}'::jsonb;
```

Kết quả bao gồm record 1. Đây là kiểm JSON boolean `false`, không phải chuỗi `"false"` hoặc khóa thiếu.

### 9.3. Không dùng containment để đoán schema

Một object có thể chứa nhiều cấu trúc hơn phần truy vấn; `@>` không tự kiểm mọi field khác là hợp lệ. Nó cũng có quy tắc riêng cho containment của array. Khi cần ràng buộc đầy đủ schema JSON, hãy dùng validation/checks ở application hoặc constraint phù hợp.

## 10. JSONPath: tìm phần tử theo đường dẫn và điều kiện

PostgreSQL hỗ trợ kiểu `jsonpath` và các hàm/toán tử truy vấn JSONPath, hữu ích khi cấu trúc chứa nhiều object/mảng.

### 10.1. Kiểm tra một đường dẫn có phần tử khớp

```sql
SELECT
    record_id,
    jsonb_path_exists(payload, '$.profile.email')
        AS path_has_result
FROM demo_json_records
WHERE record_id IN (1, 2, 3, 4, 5, 8)
ORDER BY record_id;
```

Trong cấu trúc đơn giản:

- Record 1: có string email → true.
- Record 2: có phần tử JSON null ở email → **true**.
- Record 3: thiếu email → false.
- Record 5: thiếu profile → false.
- Record 8: có string `"null"` → true.

**Điểm quan trọng:** một đường dẫn tồn tại **không có nghĩa giá trị khác null**. JSON null cũng là một phần tử được đường dẫn tìm thấy.

Với `payload` SQL NULL, các hàm truy vấn thường cho SQL NULL ở đầu ra tương ứng, không nên mặc định luôn là false; khi cần boolean rõ, dùng `COALESCE(..., FALSE)` và xác định chính sách dữ liệu.

### 10.2. Truy xuất phần tử đầu tiên dưới dạng JSON

```sql
SELECT
    record_id,
    jsonb_path_query_first(payload, '$.profile.email')
        AS email_json
FROM demo_json_records
WHERE record_id IN (1, 2, 3, 8);
```

Giống `#>` ở ví dụ đơn giản: nếu tìm được JSON null thì kết quả là một giá trị JSONB null, còn không có kết quả thì thường là SQL NULL. Tuy nhiên, **JSONPath có quy tắc lax/strict và xử lý cấu trúc phức tạp** riêng, không đồng nhất một cách máy móc với toán tử đường dẫn.

### 10.3. Tìm trong array

Record 12 có `items`:

```json
[
  {"sku": "A", "qty": 2},
  {"sku": "B", "qty": null}
]
```

Truy vấn:

```sql
SELECT
    record_id,
    jsonb_path_query_array(payload, '$.items[*].sku') AS skus,
    jsonb_path_exists(
        payload,
        '$.items[*] ? (@.qty > 1)'
    ) AS has_item_qty_gt_one
FROM demo_json_records
WHERE record_id = 12;
```

`skus` là một JSON array chứa `"A"` và `"B"`. Điều kiện `qty > 1` khớp dòng A có qty 2. Dòng B có qty JSON null không tương đương một số lớn hơn 1.

### 10.4. Toán tử `@?`

```sql
SELECT record_id
FROM demo_json_records
WHERE payload @? '$.items[*] ? (@.sku == "B")';
-- Record 12 trong dữ liệu mẫu.
```

Toán tử `@?` kiểm xem JSONPath có trả được phần tử phù hợp. Không nhầm với `?` kiểm khóa/phần tử string **cấp trên cùng** của JSONB.

### 10.5. Lax và strict: đừng dùng làm bằng chứng cấu trúc khi chưa hiểu

JSONPath PostgreSQL có chế độ **lax** mặc định và **strict**. Lax có cơ chế thích nghi một số sai khác cấu trúc, ví dụ tự unwrap array trong một số phép duyệt; strict đòi cấu trúc khớp sát hơn và có thể báo lỗi khi không khớp.

Do đó:

- Nếu chỉ cần tìm phần tử trong cấu trúc linh hoạt, JSONPath có thể phù hợp.
- Nếu phải khẳng định **một khóa hiện diện đúng cấp dưới một object**, nên kiểm kiểu parent với `jsonb_typeof` và dùng `?`, hoặc thiết kế JSONPath và semantics chính xác.
- Nếu cần validate đầy đủ schema, **JSONPath path tồn tại không thay thế schema validation**.

Không chuyển truy vấn `payload #> '{profile,email}'` sang một JSONPath lax phức tạp rồi mặc định kết quả luôn tương đương cho mọi root array/object.

## 11. Khi bóc tách JSON ra cột quan hệ, đừng đánh mất trạng thái

Ứng dụng thường muốn biến JSON thành các cột SQL:

```sql
SELECT
    record_id,
    payload #>> '{profile,email}' AS email
FROM demo_json_records;
```

Nhưng cột `email` kết quả không còn phân biệt **missing** với **JSON null**. Nếu cần dùng cho PATCH, audit hoặc validation, hãy giữ thêm cờ/type:

```sql
SELECT
    record_id,
    jsonb_typeof(payload -> 'profile') = 'object'
        AS parent_is_object,
    COALESCE(
        (payload -> 'profile') ? 'email',
        FALSE
    ) AS has_email_key,
    jsonb_typeof(payload #> '{profile,email}')
        AS email_json_type,
    payload #>> '{profile,email}'
        AS email_text
FROM demo_json_records
WHERE tenant_id = 10
ORDER BY record_id;
```

Từ đó phân biệt:

- `has_email_key=false` và parent object → thiếu khóa.
- `has_email_key=true`, `email_json_type='null'` → JSON null.
- `has_email_key=true`, `email_json_type='string'` → chuỗi, kể cả chuỗi `"null"` hoặc `""`.
- `parent_is_object=false` → cấu trúc không đúng hoặc parent vắng mặt; cần xét thêm trạng thái root.

### 11.1. Lưu ý với `jsonb_to_record` và `jsonb_populate_record`

PostgreSQL có các hàm chuyển object JSONB thành record có cột typed, ví dụ:

```sql
SELECT
    d.record_id,
    p.email,
    p.phone
FROM demo_json_records AS d
LEFT JOIN LATERAL jsonb_to_record(
    CASE
        WHEN jsonb_typeof(d.payload -> 'profile') = 'object'
        THEN d.payload -> 'profile'
        ELSE '{}'::jsonb
    END
) AS p(email TEXT, phone TEXT) ON TRUE
WHERE d.tenant_id = 10
ORDER BY d.record_id;
```

Hàm này thuận tiện để **flatten JSON**, nhưng những field JSON null và field thiếu thường được chuyển về **SQL NULL** trong cột record. Khi hợp đồng yêu cầu phân biệt, hãy giữ **thêm thông tin khóa hiện diện trên JSON gốc**.

### 11.2. Flatten không tự xác nhận kiểu email

Với record 9, trường email là JSON boolean false. Khi chuyển sang text, có thể nhận chuỗi `false`. Một ứng dụng email không nên chỉ kiểm `email IS NOT NULL` rồi gửi thư.

Nên tách:

1. **Có khóa không?**
2. **Kiểu JSON là gì?**
3. **Giá trị chuyển được sang kiểu mong muốn không?**
4. **Giá trị có thỏa quy tắc nghiệp vụ không?**

## 12. JSON arrays: phân biệt array thiếu, JSON null và array rỗng

Ba document:

```json
{"tags": []}
```

```json
{"tags": null}
```

```json
{}
```

không có cùng ý nghĩa:

- `[]`: có khóa tags, kiểu array, **không có phần tử**.
- `null`: có khóa tags, giá trị JSON null.
- Thiếu tags: không có khóa.

### 12.1. Kiểm kiểu trước khi tách phần tử

```sql
SELECT
    record_id,
    jsonb_typeof(payload -> 'tags') AS tags_type,
    CASE
        WHEN jsonb_typeof(payload -> 'tags') = 'array'
        THEN jsonb_array_length(payload -> 'tags')
        ELSE NULL
    END AS tags_length
FROM demo_json_records
WHERE record_id IN (1, 2, 3, 5, 8)
ORDER BY record_id;
```

Từ dữ liệu mẫu:

| ID | Trạng thái | `tags_length` |
| ---: | --- | ---: |
| 1 | Array có hai string | 2 |
| 2 | Array rỗng | 0 |
| 3 | JSON null | SQL NULL |
| 5 | Array rỗng | 0 |
| 8 | Array có string `"null"` và JSON null | 2 |

Gọi `jsonb_array_length` trực tiếp trên JSON null/object/string có thể báo lỗi vì đối số không phải array. Với cấu trúc linh hoạt, **guard theo `jsonb_typeof` trước**.

### 12.2. Tách array an toàn với LATERAL

```sql
SELECT
    d.record_id,
    COUNT(item.value) AS item_count
FROM demo_json_records AS d
LEFT JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(d.payload -> 'items') = 'array'
        THEN d.payload -> 'items'
        ELSE '[]'::jsonb
    END
) AS item(value) ON TRUE
WHERE d.tenant_id = 10
GROUP BY d.record_id
ORDER BY d.record_id;
```

`jsonb_array_elements` cần JSON array. `CASE` đưa các giá trị khác array thành `[]` để tránh lỗi trong ví dụ. `LEFT JOIN LATERAL` giữ một hàng cho record không có items, nên **phải dùng `COUNT(item.value)`** thay vì `COUNT(*)` nếu muốn đếm phần tử thực.

**Chú ý:** phần tử JSON null trong array vẫn là một giá trị `jsonb` không phải SQL NULL, nên `COUNT(item.value)` có thể đếm phần tử JSON null. Đó là điều đúng nếu nghiệp vụ hỏi **số phần tử**; nếu cần số phần tử **khác JSON null**, hãy lọc/type-check rõ.

### 12.3. Mảng rỗng và SQL NULL trong kết quả aggregate

Từ một hàm tổng hợp phần tử, không có hàng được group có thể dẫn tới SQL NULL, khác với JSON array rỗng `[]`. Nếu muốn API luôn trả array, có thể dùng:

```sql
COALESCE(jsonb_agg(value), '[]'::jsonb)
```

nhưng phải xác định xem việc quy “không có dữ liệu” thành array rỗng có đúng nghiệp vụ hay không. Không dùng COALESCE để vô tình che trạng thái thiếu khóa mà API cần phân biệt.

## 13. Cập nhật JSON: thêm khóa, ghi JSON null, và xóa khóa là ba việc khác nhau

PostgreSQL `jsonb_set` cập nhật một đường dẫn JSON trong document:

```sql
jsonb_set(target_jsonb, path_text_array, new_value_jsonb, create_if_missing)
```

### 13.1. Thay email có sẵn bằng JSON null

```sql
BEGIN;

UPDATE demo_json_records
SET payload = jsonb_set(
    payload,
    '{profile,email}',
    'null'::jsonb,
    TRUE
)
WHERE record_id = 1
  AND tenant_id = 10;

SELECT
    payload #> '{profile,email}' AS email_json,
    (payload -> 'profile') ? 'email' AS has_key
FROM demo_json_records
WHERE record_id = 1;

ROLLBACK;
```

Trong transaction, `has_key=true` và `email_json` là JSON null. Sau ROLLBACK, email trở lại giá trị ban đầu.

### 13.2. Thêm khóa email đang thiếu trong object hiện hữu

Record 3 có `profile` là object nhưng thiếu email:

```sql
BEGIN;

UPDATE demo_json_records
SET payload = jsonb_set(
    payload,
    '{profile,email}',
    '"chi@example.com"'::jsonb,
    TRUE
)
WHERE record_id = 3;

SELECT payload #> '{profile,email}' AS email_json
FROM demo_json_records
WHERE record_id = 3;

ROLLBACK;
```

Vì parent `profile` **đã tồn tại và là object**, `create_if_missing=TRUE` cho phép tạo khóa email cuối đường dẫn.

### 13.3. `create_if_missing` không tự tạo mọi object trung gian

Record 5 **không có khóa `profile`**. Không nên mặc định:

```sql
jsonb_set(payload, '{profile,email}', '"x@example.com"'::jsonb, TRUE)
```

sẽ tự tạo cả object `profile` rồi thêm email. PostgreSQL `jsonb_set` yêu cầu **các bước đường dẫn trung gian phải tồn tại** theo quy tắc hàm; nếu thiếu, kết quả có thể giữ nguyên target.

Nếu muốn tạo cấu trúc lồng sâu, cần **chủ động dựng parent phù hợp** hoặc dùng chuỗi thao tác cập nhật có kiểm tra kiểu/schema. Ví dụ với root object đã biết:

```sql
BEGIN;

UPDATE demo_json_records
SET payload = jsonb_set(
    payload,
    '{profile}',
    jsonb_build_object('email', 'new@example.com'),
    TRUE
)
WHERE record_id = 5
  AND jsonb_typeof(payload) = 'object'
  AND NOT (payload ? 'profile');

ROLLBACK;
```

Ở đây ta cố ý thêm **toàn bộ object profile** như một giá trị của khóa cấp trên cùng.

### 13.4. Xóa khóa khác với gán JSON null

PostgreSQL dùng `-` và `#-` để xóa thành phần:

```sql
BEGIN;

UPDATE demo_json_records
SET payload = payload #- '{profile,email}'
WHERE record_id = 1;

SELECT
    (payload -> 'profile') ? 'email' AS has_email,
    payload #> '{profile,email}' AS email_json
FROM demo_json_records
WHERE record_id = 1;

ROLLBACK;
```

Sau lệnh xóa trong transaction:

- Khóa `profile.email` **không còn**.
- `has_email=false`.
- `email_json` là SQL NULL vì đường dẫn không tìm thấy.

Trong khi gán JSON null ở mục 13.1 giữ `has_email=true`. Hai thao tác có ý nghĩa khác nhau đối với API, audit và các bộ lọc.

### 13.5. Xóa khóa cấp root

```sql
SELECT '{"profile":{"email":"a"},"active":true}'::jsonb
       - 'profile' AS removed_profile;
```

Kết quả còn `{"active": true}`. Không nhầm thao tác xóa **key** với đặt giá trị key thành JSON null.

## 14. SQL NULL truyền vào hàm cập nhật không phải JSON null

Một lỗi dễ gặp:

```sql
SELECT jsonb_set(
    '{"profile":{"email":"a"}}'::jsonb,
    '{profile,email}',
    NULL::jsonb,
    TRUE
);
```

Đối số `new_value` là **SQL NULL**, không phải `'null'::jsonb`. Với `jsonb_set`, việc truyền SQL NULL có thể làm **cả kết quả hàm thành SQL NULL** do tính strict của hàm, thay vì tạo khóa email có JSON null. Trong một UPDATE thiếu guard, điều này có thể làm **toàn bộ cột JSON bị gán SQL NULL** nếu constraint cho phép.

Muốn ghi rõ JSON null:

```sql
SELECT jsonb_set(
    '{"profile":{"email":"a"}}'::jsonb,
    '{profile,email}',
    'null'::jsonb,
    TRUE
);
```

### 14.1. `jsonb_set_lax` xử lý SQL NULL đầu vào có chủ đích

Trong các phiên bản PostgreSQL hỗ trợ `jsonb_set_lax`, có thể định nghĩa hành vi khi `new_value` là SQL NULL:

```sql
SELECT jsonb_set_lax(
    '{"profile":{"email":"a"}}'::jsonb,
    '{profile,email}',
    NULL::jsonb,
    TRUE,
    'use_json_null'
);
```

Các chế độ xử lý SQL NULL của hàm này có thể bao gồm:

| Chế độ | Ý nghĩa |
| --- | --- |
| `use_json_null` | Ghi JSON null tại đường dẫn |
| `delete_key` | Xóa khóa/giá trị đích theo ngữ nghĩa đường dẫn |
| `return_target` | Trả lại target không thay đổi |
| `raise_exception` | Báo lỗi thay vì tự chọn hành vi |

Chọn chế độ **theo hợp đồng nghiệp vụ**; không mặc định SQL NULL có nghĩa “xóa khóa” hay “ghi null”. Đối chiếu tài liệu/phiên bản PostgreSQL trước khi dùng chức năng nâng cao.

### 14.2. `jsonb_strip_nulls` có thể làm mất thông tin

```sql
SELECT jsonb_strip_nulls(
    '{"a":null,"b":1,"nested":{"c":null,"d":2}}'::jsonb
);
```

Hàm có thể **loại các key trong object** có giá trị JSON null (bao gồm object lồng nhau), để lại những thuộc tính khác. Nếu hợp đồng phân biệt “khóa có JSON null” với “khóa thiếu”, việc strip nulls sẽ **thay ngữ nghĩa**.

Trong các phiên bản khác nhau, tùy chọn xử lý null trong array có thể khác; hãy kiểm tài liệu phiên bản đang dùng. **Không chạy hàm làm sạch JSON null hàng loạt** chỉ để giảm kích thước khi chưa hiểu ý nghĩa dữ liệu.

## 15. INSERT JSON: trường vắng mặt và trường được tạo với SQL NULL

Trong PostgreSQL:

```sql
SELECT
    jsonb_build_object(
        'name', 'An',
        'phone', NULL::text
    ) AS built_json;
```

Kết quả có thể là:

```json
{"name": "An", "phone": null}
```

Việc truyền **SQL NULL làm giá trị cho `jsonb_build_object`** được chuyển thành **JSON null tại khóa được tạo**, không có nghĩa khóa phone tự động bị bỏ.

Muốn thiếu khóa:

```sql
SELECT jsonb_build_object('name', 'An');
```

### 15.1. Tạo JSON từ bảng quan hệ

Ví dụ:

```sql
SELECT jsonb_build_object(
    'record_id', record_id,
    'email', payload #>> '{profile,email}'
)
FROM demo_json_records
WHERE record_id = 3;
```

Vì email text là SQL NULL khi thiếu khóa, `jsonb_build_object` sẽ tạo **`"email":null`**, làm mất thông tin “khóa email vốn thiếu ở tài liệu nguồn”. Nếu muốn bảo toàn sự vắng mặt, phải **xây dựng object có điều kiện** thay vì luôn tạo tất cả các khóa với NULL.

### 15.2. Một mẫu dựng JSON có điều kiện

```sql
SELECT
    jsonb_build_object('record_id', record_id) ||
    CASE
        WHEN jsonb_typeof(payload -> 'profile') = 'object'
             AND ((payload -> 'profile') ? 'email')
        THEN jsonb_build_object(
            'email', payload #> '{profile,email}'
        )
        ELSE '{}'::jsonb
    END AS output_json
FROM demo_json_records
WHERE record_id IN (2, 3)
ORDER BY record_id;
```

Record 2 có khóa email JSON null, nên output **có `"email":null`**. Record 3 thiếu khóa email, nên output **không chứa email**. Đây là cách bảo toàn trạng thái khi serialize ra JSON.

**Chú ý:** phép nối `jsonb || jsonb` ở đây nối hai object cấp trên cùng. Với cấu trúc sâu hoặc khóa trùng, cần quy tắc merge cụ thể; `||` không phải thao tác recursive deep-merge tổng quát.

## 16. API PATCH: thiếu trường khác null theo hợp đồng

Đây là một ví dụ ứng dụng điển hình.

Giả sử hồ sơ đang lưu:

```json
{
  "display_name": "An",
  "phone": "0901234567",
  "newsletter": true
}
```

API nhận bản cập nhật:

```json
{"display_name": "An mới"}
```

Nếu hợp đồng là **partial update**, trường `phone` không xuất hiện thường có nghĩa “giữ nguyên”. Nhưng nếu nhận:

```json
{"phone": null}
```

có thể có nghĩa “xóa số điện thoại” hoặc “đặt trạng thái chưa có số”. Phải định nghĩa rõ điều nào đúng.

### 16.1. JSON Merge Patch có quy tắc riêng

Chuẩn **JSON Merge Patch (RFC 7396)** có semantics đặc biệt: trong patch object, một member có giá trị `null` thường biểu thị **xóa member đó khỏi target**, chứ không phải “lưu một member có JSON null”.

Ví dụ một patch:

```json
{"phone": null}
```

theo JSON Merge Patch có mục tiêu **xóa khóa phone**. Nhưng một API PATCH tự thiết kế có thể chọn nghĩa khác. **Đừng trộn hợp đồng JSON Merge Patch với một PATCH custom**.

### 16.2. JSON Patch là một chuẩn khác

**JSON Patch (RFC 6902)** thể hiện hành động bằng các operation như `add`, `remove`, `replace`:

```json
[
  {"op": "remove", "path": "/phone"}
]
```

khác:

```json
[
  {"op": "replace", "path": "/phone", "value": null}
]
```

Operation đầu tiên **xóa khóa**; operation thứ hai **thay giá trị bằng JSON null** nếu path hợp lệ theo quy tắc JSON Patch. Nhờ đó có thể biểu đạt hai ý định riêng biệt.

### 16.3. Phải kiểm sự hiện diện trước khi ép kiểu

Khi parse request JSON trong application:

```text
if request does not contain key "phone":
    leave stored phone unchanged
else if request["phone"] is JSON null:
    apply explicit "clear / set null" contract
else if request["phone"] is a string:
    validate format and update
else:
    reject invalid type
```

Không gọi `getString("phone")` rồi dùng `null` trả về để suy đoán “không có thay đổi”, vì nhiều thư viện JSON trả cùng null-like value cho key thiếu và JSON null hoặc ánh xạ khác nhau theo API.

## 17. Index JSONB để tìm khóa và giá trị hiệu quả

Khi dữ liệu lớn, các truy vấn JSON có thể cần index phù hợp với toán tử sử dụng.

### 17.1. GIN index cho `jsonb`

PostgreSQL:

```sql
CREATE INDEX idx_demo_json_payload_gin
ON demo_json_records
USING GIN (payload);
```

Index GIN trên `jsonb` có thể hỗ trợ những toán tử containment/key existence phù hợp với operator class (ví dụ `@>`, `?` với `jsonb_ops` mặc định), tùy query và planner.

Truy vấn:

```sql
SELECT record_id
FROM demo_json_records
WHERE tenant_id = 10
  AND payload @> '{"profile":{"email":null}}'::jsonb;
```

về mặt logic chỉ chọn record có giá trị JSON null tại path được nêu. Index có thể giúp tăng tốc trên bộ dữ liệu phù hợp, nhưng nó **không thay ý nghĩa JSON null thành missing**.

### 17.2. `jsonb_ops` và `jsonb_path_ops` không giống nhau

PostgreSQL hỗ trợ những operator class GIN khác nhau:

- `jsonb_ops` (thường mặc định) hỗ trợ phạm vi toán tử rộng hơn, gồm key-existence `?` ở vị trí index phù hợp.
- `jsonb_path_ops` có cách lập chỉ mục tối ưu cho một số truy vấn containment/JSONPath nhưng **không hỗ trợ toán tử `?` theo cùng cách `jsonb_ops`**.

Không chuyển tất cả GIN JSONB index sang `jsonb_path_ops` mà không đối chiếu workload thực tế.

### 17.3. Index biểu thức đường dẫn

Nếu thường xuyên tìm email text:

```sql
CREATE INDEX idx_demo_json_email_text
ON demo_json_records (
    (payload #>> '{profile,email}')
);
```

Truy vấn:

```sql
SELECT record_id
FROM demo_json_records
WHERE tenant_id = 10
  AND payload #>> '{profile,email}' = 'an@example.com';
```

Index expression có thể hữu ích cho so sánh text, nhưng **cả JSON null lẫn đường dẫn thiếu đều cho SQL NULL ở biểu thức `#>>`**. Do đó index text đơn lẻ không thể khôi phục thông tin phân biệt trạng thái.

### 17.4. Index cho điều kiện JSON null

Với workload cần tìm đúng JSON null:

```sql
CREATE INDEX idx_demo_json_email_is_json_null
ON demo_json_records (tenant_id, record_id)
WHERE payload #> '{profile,email}' = 'null'::jsonb;
```

Đây là một **partial index PostgreSQL**. Nó phục vụ một predicate cụ thể; planner có thể dùng khi điều kiện truy vấn phù hợp, nhưng không bảo đảm được chọn trên bảng vài hàng. Tối ưu index cần đo và xét tần suất cập nhật/khối lượng dữ liệu.

### 17.5. Expression index trên parent cho toán tử `?`

Nếu hay kiểm khóa `email` trong object `profile`:

```sql
CREATE INDEX idx_demo_json_profile_gin
ON demo_json_records
USING GIN ((payload -> 'profile'));
```

Truy vấn biểu thức tương ứng:

```sql
SELECT record_id
FROM demo_json_records
WHERE ((payload -> 'profile') ? 'email') IS TRUE;
```

Hiệu quả index phụ thuộc operator class và kiểu query. **GIN trên toàn payload** không mặc nhiên giúp mọi phép `?` nằm bên trong biểu thức `payload -> 'profile'` nếu planner không thể biến nó thành điều kiện indexable phù hợp.

## 18. EXPLAIN chỉ sau khi xác nhận kết quả đúng

Trên PostgreSQL:

```sql
EXPLAIN
SELECT record_id
FROM demo_json_records
WHERE payload @> '{"profile":{"email":null}}'::jsonb;
```

Để đo thực thi:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT record_id
FROM demo_json_records
WHERE payload @> '{"profile":{"email":null}}'::jsonb;
```

Bạn có thể thấy Seq Scan, Bitmap Index Scan hoặc Index Scan tùy số hàng, thống kê và chi phí. Bảng ví dụ có 13 hàng nên Seq Scan thường hợp lý; không thể dùng nó để kết luận index không có ích khi hàng triệu document.

### 18.1. Trước tiên phải kiểm đúng ngữ nghĩa

Hai điều kiện:

```sql
payload #>> '{profile,email}' IS NULL
```

và:

```sql
payload @> '{"profile":{"email":null}}'::jsonb
```

không tương đương. Câu đầu chọn cả nhiều trường hợp thiếu path/SQL NULL; câu sau yêu cầu cấu trúc và giá trị JSON null.

Khi so tốc độ, nếu câu thứ hai nhanh hơn vì trả ít hàng, đó **không phải bằng chứng tối ưu tương đương**. Hãy viết rõ tập kết quả cần lấy trước.

### 18.2. Nên đo những gì?

- Actual rows và estimated rows.
- Buffers/I/O, thời gian thực thi và lập kế hoạch.
- Số document quét, tỷ lệ lọc, kích thước JSONB.
- Chi phí duy trì index khi INSERT/UPDATE.
- Sự thay đổi plan theo tham số và phân bố dữ liệu.
- Tác động đối với transaction/WAL và replication nếu cập nhật nhiều JSON.

### 18.3. `EXPLAIN ANALYZE` chạy statement thật

Với `SELECT` thông thường, có thể đo ở môi trường test. Nhưng `EXPLAIN ANALYZE UPDATE ...` thực sự **thực hiện UPDATE**. Khi thử DML, dùng database thực hành và transaction có ROLLBACK nếu phù hợp; không cho rằng EXPLAIN ANALYZE chỉ mô phỏng.

## 19. Thiết kế schema: JSON linh hoạt nhưng phải có ràng buộc

JSON thích hợp cho thuộc tính thay đổi linh hoạt, nhưng không tự bảo đảm dữ liệu có cấu trúc/kiểu mong muốn.

Trong PostgreSQL:

```sql
ALTER TABLE demo_json_records
ADD CONSTRAINT demo_payload_is_object_or_sql_null
CHECK (
    payload IS NULL
    OR jsonb_typeof(payload) = 'object'
);
```

**Không chạy constraint này trực tiếp trên dữ liệu demo hiện tại**: các record 7, 10, 11 có root JSON null/array/string, nên việc thêm CHECK sẽ thất bại. Nó là **mẫu minh họa** cho một schema mà business chỉ cho phép root object hoặc SQL NULL.

### 19.1. CHECK theo trường hiện diện có đúng kiểu

Giả sử muốn email **nếu có và không phải JSON null thì phải là JSON string**. Một ý tưởng constraint:

```sql
CHECK (
    payload IS NULL
    OR NOT COALESCE(
        (payload -> 'profile') ? 'email',
        FALSE
    )
    OR jsonb_typeof(payload #> '{profile,email}') IN ('string', 'null')
)
```

Constraint trên chỉ là **mẫu một phần**, không chứng minh parent là object hoặc email string hợp lệ. Ngoài ra `CHECK` trong SQL coi biểu thức UNKNOWN là không vi phạm trong nhiều DBMS, nên muốn ép ràng buộc chặt cần **bảo đảm mọi trường hợp NULL/UNKNOWN được tính đúng**.

### 19.2. Cột JSON và cột quan hệ

Những thuộc tính quan trọng cho JOIN, FOREIGN KEY, UNIQUE, phân quyền, lọc liên tục hoặc thống kê có thể phù hợp hơn với **cột typed**:

```text
tenant_id BIGINT NOT NULL
user_id BIGINT PRIMARY KEY
email TEXT NULL
metadata JSONB
```

Ưu điểm: type constraints, index và hợp đồng rõ. JSONB vẫn có thể chứa cấu hình/thuộc tính bổ sung. Không phải cứ linh hoạt là nhét mọi khóa nghiệp vụ vào một blob JSON.

### 19.3. Generated columns và validation

Một số DBMS hỗ trợ generated/computed columns lấy giá trị theo JSON path để index/query. Cần hiểu: nếu biểu thức lấy text gộp JSON null với missing, generated column cũng thường gộp chúng. Nếu nghiệp vụ cần phân biệt, có thể cần thêm một cột flag “has key” hoặc schema validation tương ứng.

## 20. MySQL: JSON_EXTRACT, JSON_TYPE và JSON_CONTAINS_PATH

MySQL có kiểu JSON và bộ hàm riêng. Với document:

```json
{"profile": {"email": null}}
```

Bạn có thể kiểm đường dẫn:

```sql
SELECT
    JSON_CONTAINS_PATH(
        '{"profile":{"email":null}}',
        'one',
        '$.profile.email'
    ) AS email_path_exists;
```

Giá trị dự kiến là **1**: đường dẫn tồn tại dù giá trị là JSON null.

Với khóa thiếu:

```sql
SELECT
    JSON_CONTAINS_PATH(
        '{"profile":{}}',
        'one',
        '$.profile.email'
    ) AS email_path_exists;
-- 0.
```

### 20.1. JSON_EXTRACT và JSON_TYPE

```sql
SELECT
    JSON_EXTRACT(
        '{"profile":{"email":null}}',
        '$.profile.email'
    ) AS email_json,
    JSON_TYPE(
        JSON_EXTRACT(
            '{"profile":{"email":null}}',
            '$.profile.email'
        )
    ) AS json_type;
```

MySQL giữ khả năng phân biệt JSON null và đường dẫn không tồn tại qua những hàm/kiểu JSON phù hợp; `JSON_TYPE` có thể trả tên JSON type **`NULL`** (chuỗi) cho JSON null, trong khi giá trị SQL NULL của biểu thức thiếu đường dẫn được xử lý khác.

**Không đồng nhất cú pháp/type behavior của MySQL với PostgreSQL.** Đặc biệt, kết quả của `JSON_UNQUOTE`, biểu thức `->>` và chuyển JSON sang SQL text cần được kiểm trên phiên bản MySQL đang dùng.

### 20.2. Truy xuất ký pháp mũi tên

MySQL có dạng:

```sql
SELECT
    doc -> '$.profile.email' AS email_json,
    doc ->> '$.profile.email' AS email_unquoted
FROM some_table;
```

Đây là **mẫu trên bảng giả định**. Khác PostgreSQL: đối số bên phải của mũi tên trong MySQL thường là **JSON path dạng string**, không phải key đơn `'profile'` rồi key `'email'` như ví dụ PostgreSQL.

### 20.3. Nếu cần phân biệt missing và JSON null trong MySQL

Ưu tiên kiểm **đường dẫn có tồn tại không**:

```sql
JSON_CONTAINS_PATH(doc, 'one', '$.profile.email')
```

sau đó kiểm **kiểu JSON và giá trị** khi đường dẫn tồn tại. Nếu doc có thể là SQL NULL, xử lý tình huống ấy riêng; không mặc định mọi hàm sẽ trả 0 thay vì SQL NULL.

## 21. SQL Server: JSON_VALUE có thể làm nhiều tình huống thành NULL

SQL Server thường lưu JSON dưới dạng chuỗi NVARCHAR trong những phiên bản phổ biến và cung cấp các hàm JSON.

### 21.1. JSON_VALUE

```sql
DECLARE @doc NVARCHAR(MAX) =
    N'{"profile":{"email":null}}';

SELECT JSON_VALUE(@doc, '$.profile.email') AS email_text;
```

Theo chế độ `lax` mặc định trong các phiên bản hỗ trợ, `JSON_VALUE` thường trả **SQL NULL** cho JSON null và cho đường dẫn không có scalar phù hợp; trường hợp không tồn tại, object/array, hoặc scalar vượt giới hạn chiều dài của JSON_VALUE cũng cần xét riêng.

Vì vậy **không dùng `JSON_VALUE(...) IS NULL` làm bằng chứng khóa vắng mặt**.

### 21.2. OPENJSON có thông tin key/type

```sql
DECLARE @doc NVARCHAR(MAX) =
    N'{"profile":{"email":null,"phone":"0901"}}';

SELECT
    [key],
    value,
    type
FROM OPENJSON(@doc, '$.profile');
```

Ở kết quả `OPENJSON` với schema mặc định, một property có JSON null vẫn hiện thành hàng với `[key] = 'email'` và mã `type` biểu diễn JSON null (trong SQL Server là **0**). Nếu key email **không có**, hàng tương ứng không xuất hiện.

Điều đó giúp phân biệt missing với JSON null khi bạn cần kiểm chính xác parent object.

### 21.3. JSON_PATH_EXISTS

Các phiên bản SQL Server hiện đại có hàm `JSON_PATH_EXISTS` hoặc khả năng kiểm path tương ứng; cần xác minh **phiên bản/edition** trước khi dùng.

Ví dụ định hướng:

```sql
SELECT JSON_PATH_EXISTS(
    N'{"profile":{"email":null}}',
    '$.profile.email'
) AS path_exists;
```

Mục đích là kiểm đường dẫn tồn tại, không chỉ lấy scalar text. Với nền tảng cũ, có thể dùng `OPENJSON`, kiểm theo key và type như ở trên.

### 21.4. Chế độ lax và strict

JSONPath trong SQL Server có chế độ `lax`/`strict` cho một số hàm. Strict có thể báo lỗi khi cấu trúc không khớp thay vì âm thầm trả SQL NULL. Chọn theo hợp đồng ứng dụng; **strict không có nghĩa “mọi key có JSON null phải báo lỗi”**.

## 22. SQLite: json_extract trả SQL NULL cho cả missing và JSON null

SQLite có hệ hàm JSON1 với semantics đáng chú ý:

```sql
SELECT
    json_extract('{"a":null}', '$.a') AS json_null_extract,
    json_extract('{}', '$.a') AS missing_extract;
```

Với **một đường dẫn**, `json_extract` của SQLite thường trả **SQL NULL** cho cả JSON null và khóa thiếu. Nếu chỉ so kết quả này, không phân biệt được.

### 22.1. Dùng json_type để phân biệt

```sql
SELECT
    json_type('{"a":null}', '$.a') AS present_null_type,
    json_type('{}', '$.a') AS missing_type,
    json_type('{"a":"null"}', '$.a') AS string_type;
```

Kết quả:

| Biểu thức | Giá trị |
| --- | --- |
| `present_null_type` | text `'null'` |
| `missing_type` | **SQL NULL** |
| `string_type` | text `'text'` |

Do đó, khi cần giữ hai trạng thái, **`json_type(document, path)`** thường phù hợp hơn chỉ `json_extract`.

### 22.2. json_each và key

SQLite có `json_each` để tách object/array:

```sql
SELECT key, value, type
FROM json_each('{"email":null,"phone":"0901"}');
```

Hàng `email` vẫn hiện với type `null`. Nếu object không có email, không có hàng `key='email'`.

### 22.3. SQLite không có kiểu JSON duy nhất giống PostgreSQL jsonb ở mọi phiên bản

SQLite thường lưu JSON dưới dạng text hoặc biểu diễn JSONB nội bộ mới hơn tùy phiên bản, cùng hệ hàm JSON. `->`/`->>` và JSON1 có đặc tính trả SQL values khác PostgreSQL/MySQL. Cần kiểm `json_valid` và kiểm phiên bản khi dùng tính năng mới.

## 23. Oracle: JSON_EXISTS khác JSON_VALUE

Oracle Database có hệ SQL/JSON, với cách diễn tả path bằng `$.profile.email`.

### 23.1. JSON_EXISTS

```sql
SELECT
    JSON_EXISTS(
        '{"profile":{"email":null}}',
        '$.profile.email'
    ) AS path_exists
FROM dual;
```

Theo ngữ nghĩa SQL/JSON path existence, đường dẫn có phần tử JSON null vẫn được coi là có kết quả khớp ở những chế độ phù hợp. Với path vắng mặt, biểu thức existence thường cho false theo quy tắc lỗi/empty đã cấu hình.

### 23.2. JSON_VALUE

```sql
SELECT
    JSON_VALUE(
        '{"profile":{"email":null}}',
        '$.profile.email'
    ) AS email_text
FROM dual;
```

Hàm trích scalar có thể trả **SQL NULL** cho JSON null và path vắng mặt tùy `ON EMPTY`/`ON ERROR`/returning type. Vì vậy, nếu nghiệp vụ cần phân biệt trạng thái, hãy phối hợp `JSON_EXISTS` với kiểu/giá trị thích hợp.

### 23.3. ON EMPTY và ON ERROR là hai tình huống khác

Tùy phiên bản Oracle, các biểu thức SQL/JSON có thể cho phép quy tắc `NULL ON EMPTY`, `ERROR ON EMPTY`, `DEFAULT ... ON EMPTY` và điều kiện lỗi khác. Đường dẫn không có phần tử, đường dẫn có JSON null, dữ liệu không đúng kiểu và lỗi conversion **không nên bị coi là một sự kiện duy nhất** trong thiết kế API.

### 23.4. Đối chiếu tính năng theo version

Oracle có nhiều khả năng JSON mới theo phiên bản (kiểu JSON native, SQL/JSON extensions, xử lý null/returning). Không dùng một cú pháp PostgreSQL hoặc MySQL nguyên dạng; cần kiểm đúng tài liệu DBMS triển khai.

## 24. Bảng so sánh đa hệ quản trị

| Nhu cầu | PostgreSQL | MySQL | SQL Server | SQLite | Oracle |
| --- | --- | --- | --- | --- | --- |
| Truy xuất JSON giữ kiểu | `->`, `#>` | `JSON_EXTRACT`, `->` | Các hàm JSON/JSON_QUERY theo phiên bản | `->`/JSON functions | SQL/JSON functions |
| Truy xuất scalar text | `->>`, `#>>` | `->>`, JSON_UNQUOTE | `JSON_VALUE` | `json_extract`/`->>` | `JSON_VALUE` |
| Kiểm khóa/đường dẫn có mặt | `?` trên object, JSONPath | `JSON_CONTAINS_PATH` | `OPENJSON`, `JSON_PATH_EXISTS` (phiên bản hỗ trợ) | `json_type(doc,path)`, `json_each` | `JSON_EXISTS` |
| Phân biệt JSON null/missing | `jsonb_typeof` + `?`/`#>` | `JSON_TYPE` + path existence | `OPENJSON` type/key + path existence | `json_type` | `JSON_EXISTS` + chính sách extract |
| Index JSON | GIN, expression, partial | Generated/functional/multivalued tùy trường hợp | Computed columns/index phù hợp | Expression/generated index | JSON/search/function-based index theo phiên bản |
| Lưu ý lớn | JSON null khác SQL NULL; `->>` làm gộp | Path syntax và JSON_EXTRACT type | JSON_VALUE thường làm gộp trong lax | json_extract một path trả SQL scalar | ON EMPTY/ON ERROR/version |

**Không giả định** cùng tên hàm sẽ trả cùng SQL type ở các hệ, hoặc bản DB cũ có đủ mọi chức năng. Trong bài toán di chuyển SQL, hãy viết test cố định ba trường hợp **missing, JSON null, SQL NULL document** trên hệ đích.

## 25. JSON và dữ liệu quan hệ: quyền truy cập, tenant và chất lượng dữ liệu

Một truy vấn JSON đúng về kỹ thuật vẫn có thể sai nghiệp vụ:

```sql
SELECT record_id, payload #>> '{profile,email}' AS email
FROM demo_json_records
WHERE jsonb_typeof(payload #> '{profile,email}') = 'string';
```

Truy vấn này không lọc `tenant_id`, có thể đọc thông tin thuộc các tenant khác nếu quyền database cho phép.

### 25.1. Lọc tenant và quyền trên cột chuẩn

```sql
SELECT record_id, payload #>> '{profile,email}' AS email
FROM demo_json_records
WHERE tenant_id = 10
  AND jsonb_typeof(payload #> '{profile,email}') = 'string';
```

Ứng dụng thật còn cần authentication/authorization hoặc Row-Level Security phù hợp. Không lưu `tenant_id` chỉ bên trong JSON mà bỏ qua ràng buộc quyền ở tầng quan hệ nếu hệ thống cần cách ly tenant đáng tin.

### 25.2. Không log toàn bộ payload khi debug null

JSON có thể chứa email, điện thoại, token, địa chỉ, thuộc tính riêng tư. Khi chẩn đoán trạng thái null, nên log:

```text
request_id
record_id
path = profile.email
path_state = MISSING | JSON_NULL | STRING | ...
schema_version
```

Thường không cần log cả tài liệu JSON. Giới hạn quyền, retention và redact dữ liệu nhạy cảm theo chính sách.

### 25.3. Path do người dùng cung cấp

Nếu API cho phép client chọn path động:

- Chỉ cho phép một tập path đã được **allowlist** theo nghiệp vụ khi phù hợp.
- Dùng bind parameters/API của driver để truyền đường dẫn/khóa; không nối trực tiếp string client vào SQL.
- Kiểm kiểu root/parent và độ sâu/độ dài path.
- Chặn đọc các nhánh nhạy cảm dù document có chứa.

Sự linh hoạt của JSONPath không thay cho quyền truy cập.

## 26. Kiểm thử hồi quy cho quy tắc missing/null

Một bài kiểm thử tốt phải giữ đủ các trạng thái đầu vào:

| Case | JSON/SQL đầu vào | Có khóa? | Kiểu JSON | Text extract | Hành vi kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| A | `{"a":"x"}` | Có | string | x | Nhận giá trị |
| B | `{"a":null}` | Có | null | SQL NULL | Nhận intent null |
| C | `{}` | Không | Không có | SQL NULL | Missing |
| D | `NULL::jsonb` | Không có document | SQL NULL | SQL NULL | Không có tài liệu |
| E | `'null'::jsonb` | Root là JSON null | null ở root | SQL NULL | Sai cấu trúc nếu cần object |
| F | `{"a":"null"}` | Có | string | null (text) | Không phải null |
| G | `{"a":""}` | Có | string | chuỗi rỗng | Giá trị hiện diện |
| H | `{"a":false}` | Có | boolean | false (text) | Kiểm kiểu |
| I | `{"a":0}` | Có | number | 0 (text) | Số không |
| J | `{"a":[]}` | Có | array | biểu diễn JSON text | Mảng rỗng |
| K | `{"parent":null}` với path `parent.a` | Parent có nhưng là JSON null | Không có ở path con | SQL NULL | Parent sai kiểu |

### 26.1. Dùng bảng VALUES để thử nhanh

```sql
WITH cases(case_name, doc) AS (
    VALUES
      ('value', '{"a":"x"}'::jsonb),
      ('json_null', '{"a":null}'::jsonb),
      ('missing', '{}'::jsonb),
      ('sql_null', NULL::jsonb),
      ('root_json_null', 'null'::jsonb),
      ('string_null', '{"a":"null"}'::jsonb),
      ('empty_string', '{"a":""}'::jsonb),
      ('false_value', '{"a":false}'::jsonb),
      ('zero_value', '{"a":0}'::jsonb)
)
SELECT
    case_name,
    doc IS NULL AS sql_null_document,
    jsonb_typeof(doc) AS root_type,
    doc ? 'a' AS has_a,
    jsonb_typeof(doc -> 'a') AS a_type,
    doc ->> 'a' AS a_text
FROM cases
ORDER BY case_name;
```

Khi thay đổi code JSON parsing hay SQL, chạy lại cùng những case này.

### 26.2. Test sâu hơn với nested path

Khi schema có `profile.contact.email`, thêm:

```text
{}
{"profile":null}
{"profile":[]}
{"profile":{}}
{"profile":{"contact":null}}
{"profile":{"contact":{}}}
{"profile":{"contact":{"email":null}}}
{"profile":{"contact":{"email":"a@example.com"}}}
```

Tập này phơi bày nhiều lỗi mà test chỉ có một JSON document “đầy đủ” không thể phát hiện.

### 26.3. Snapshot và concurrent updates

Nếu so sánh hai truy vấn JSON trên database có ghi đồng thời, kết quả khác có thể do dữ liệu thay đổi giữa hai SELECT. Để kiểm equivalence của hai biểu thức, nên chạy chúng trên **cùng statement/snapshot** hoặc trong một transaction isolation phù hợp trong môi trường test. Đừng kết luận rewrite sai chỉ vì tài liệu được người khác sửa giữa hai lần đọc.

## 27. Các sai lầm điển hình

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `->> IS NULL` để kết luận khóa thiếu | Gộp missing với JSON null | Kiểm `?`/JSONPath existence |
| Dùng `#> IS NULL` để tìm JSON null | Bỏ qua JSON null, lại chọn path thiếu | So sánh `= 'null'::jsonb` |
| Dùng `->> = 'null'` để tìm JSON null | Chọn string `"null"` | Dùng JSONB/type |
| Dùng `payload IS NULL` để tìm root JSON null | Chỉ chọn SQL NULL | `payload = 'null'::jsonb` |
| Giả định parent luôn là object | Dữ liệu null/array/string gây sai logic | Kiểm `jsonb_typeof` |
| Dùng `payload ? 'email'` cho `profile.email` | Kiểm sai cấp | `(payload->'profile') ? 'email'` |
| Quên `?` cũng áp dụng array string | Hiểu nhầm “khóa tồn tại” | Guard object type |
| Dùng `COALESCE(value,'')` quá sớm | Mất trạng thái null/missing | Giữ presence/type flags |
| Chuyển JSONB sang text trước validation | Boolean/số bị chấp nhận như email string | Kiểm JSON type trước |
| Dùng `jsonb_set` với SQL NULL làm new_value | Có thể làm cả target thành SQL NULL | Dùng `'null'::jsonb` hoặc set_lax |
| Tưởng create_if_missing tạo cả object trung gian | Path không được cập nhật như kỳ vọng | Tạo parent có chủ đích |
| Gán JSON null để “xóa khóa” | Khóa vẫn tồn tại | Dùng `#-`/operator xóa |
| Gọi jsonb_strip_nulls để dọn dữ liệu vô hại | Mất thông tin JSON null có chủ đích | Rà hợp đồng trước |
| Dùng jsonb_array_length trên scalar | Có thể lỗi | Kiểm array type |
| COUNT(*) sau LEFT JOIN LATERAL | Đếm hàng NULL-extended | COUNT(child.value) |
| Flatten bằng jsonb_to_record rồi quên presence | Missing và JSON null đều SQL NULL | Lưu trạng thái gốc |
| Tạo output với jsonb_build_object và SQL NULL | Biến missing thành key JSON null | Dựng object có điều kiện |
| Xem false/0/""/[] là missing | Mất dữ liệu hợp lệ | Kiểm kiểu, giá trị và khóa riêng |
| Dùng JSONPath lax như schema validator | Có thể thích nghi cấu trúc | Guard/strict/schema validation |
| Bỏ tenant vì dữ liệu trong JSON | Lộ/sai dữ liệu nhiều tenant | Lọc theo quyền và tenant |
| Dùng GIN path_ops để tối ưu mọi toán tử | Có toán tử không được hỗ trợ | Chọn operator class theo workload |
| Chỉ benchmark query nhanh hơn | Rewrite có thể trả khác tập hàng | Kiểm semantics trước EXPLAIN |
| Copy PostgreSQL `->` sang MySQL nguyên dạng | Cú pháp đường dẫn khác | Đọc tài liệu dialect |
| Dùng SQLite json_extract để tìm key presence | NULL và missing cùng SQL NULL | `json_type` |
| Dùng SQL Server JSON_VALUE IS NULL làm missing | Lax có nhiều lý do trả NULL | `OPENJSON`/path existence |
| Đồng nhất JSON Merge Patch null với JSON null lưu trữ | Chuẩn merge patch có nghĩa remove | Định nghĩa protocol rõ |
| Chỉ test JSON không null | Không phát hiện edge cases | Test missing/null/SQL NULL/wrong type |

## 28. Bài tập thực hành

Các bài dùng `demo_json_records` ở mục 3, trừ khi ghi rõ dữ liệu riêng. Chạy trong cùng session PostgreSQL vì bảng `TEMP` chỉ tồn tại trong session ấy. Với bài UPDATE/DELETE, nên dùng `BEGIN ... ROLLBACK` để dữ liệu mẫu không thay đổi cho bài kế tiếp.

### Bài 1 — Bốn loại null

Viết `SELECT` trả:

```sql
NULL::jsonb
'null'::jsonb
'"null"'::jsonb
'{"a":null}'::jsonb
```

So sánh `IS NULL` và `jsonb_typeof`. Vì sao JSON null không phải SQL NULL?

### Bài 2 — Toán tử `->` và `->>`

Lấy email của record 1, 2, 3 bằng cả hai toán tử. Tại sao `->>` làm record 2 và 3 trông như nhau?

### Bài 3 — `#>` và `#>>`

Viết đường dẫn `'{profile,email}'` theo hai toán tử. Khi nào muốn giữ kiểu JSON và khi nào chấp nhận lấy text?

### Bài 4 — Khóa hiện diện nhưng JSON null

Tìm record tenant 10 có `profile.email` tồn tại và là JSON null. Dùng `jsonb_typeof` kết hợp `?` hoặc `@>`. Kết quả mong đợi là record nào?

### Bài 5 — Khóa thiếu trong object profile

Tìm những record có `profile` đúng kiểu object, nhưng **không có khóa email trực tiếp**. Dùng `jsonb_typeof(payload->'profile')='object'` và `NOT (payload->'profile' ? 'email')`. Tại sao record 4 không được xem là “profile object thiếu email”?

### Bài 6 — Phân biệt parent thiếu và parent JSON null

So sánh record 4 và record 5. `payload ? 'profile'` trả gì? `jsonb_typeof(payload->'profile')` khác nhau thế nào?

### Bài 7 — Toàn bộ document SQL NULL

Tìm record 6 bằng `payload IS NULL`. Tìm record 7 bằng `payload='null'::jsonb`. Vì sao hai câu không chọn cùng hàng?

### Bài 8 — Chuỗi "null"

Record 8 có email JSON string `"null"`. Dùng `#>>` đọc giá trị và `jsonb_typeof` xác minh kiểu. Vì sao nó không phải JSON null?

### Bài 9 — Dữ liệu sai kiểu

Record 9 có email boolean false. Viết SELECT phân biệt string/boolean/null/missing, không được biến false thành email text hợp lệ chỉ nhờ cast.

### Bài 10 — Profile lồng sâu

Truy xuất `profile.contact.email` của record 12. Vì sao `profile.email` trả SQL NULL dù tài liệu vẫn có email ở một vị trí khác?

### Bài 11 — Array index

Truy xuất SKU đầu và `qty` của item thứ hai trong record 12 bằng `->` và `#>`. Vì sao `qty` của item thứ hai là JSON null chứ không phải key thiếu?

### Bài 12 — `?` trên array

Kiểm `'["vip","new"]'::jsonb ? 'vip'` và `'{"vip":null}'::jsonb ? 'vip'`. Cả hai có cùng boolean không? Ý nghĩa “tồn tại” trong mỗi trường hợp là gì?

### Bài 13 — JSONPath

Sử dụng `jsonb_path_exists(payload, '$.profile.email')` cho các record 1–5, 8. So sánh với `#>>`. Vì sao đường dẫn hiện diện có JSON null vẫn tồn tại?

### Bài 14 — JSONPath array filter

Record 12 có hai items. Viết JSONPath lọc item có `sku = "B"` và một JSONPath kiểm `qty > 1`. Vì sao item B không thỏa phép so sánh số?

### Bài 15 — Containment

Dùng `@>` tìm record có `profile.preferences.alerts=false`. Tại sao điều kiện này không tìm object có string `"false"` hoặc field thiếu?

### Bài 16 — Set JSON null

Trong BEGIN, dùng `jsonb_set` đổi email record 1 thành `'null'::jsonb`. Kiểm `?` và `jsonb_typeof` trước khi ROLLBACK. Khóa có còn không?

### Bài 17 — Remove key

Trong BEGIN, dùng `#- '{profile,email}'` xóa email record 1. Kiểm kết quả khác bài 16 thế nào rồi ROLLBACK.

### Bài 18 — Tạo parent còn thiếu

Record 5 thiếu profile. Vì sao `jsonb_set(payload,'{profile,email}',... ,true)` không tự bảo đảm tạo đủ object trung gian? Viết cách thêm toàn bộ object `profile` một cách rõ ràng.

### Bài 19 — SQL NULL làm new_value

So sánh truyền `NULL::jsonb` với `'null'::jsonb` vào `jsonb_set`. Kết quả khác gì? Trên phiên bản PostgreSQL hỗ trợ, thử `jsonb_set_lax` với `use_json_null` và `delete_key`.

### Bài 20 — Bảo toàn missing khi xuất JSON

Tạo output từ record 2 và 3, giữ `email:null` cho record 2 nhưng **bỏ khóa email** cho record 3. Dùng `jsonb_build_object`, `CASE` và `||`.

### Bài 21 — LATERAL JSON arrays

Dùng `jsonb_array_elements` để đếm phần tử `items` của mỗi record, guard khi không phải array. Vì sao `COUNT(*)` sau LEFT JOIN LATERAL không phù hợp để đếm phần tử ở document không có items?

### Bài 22 — Index

Tạo GIN index trên `payload` và expression index trên `payload #>> '{profile,email}'`. Cho biết loại query nào có thể hưởng lợi. Vì sao index text không phân biệt missing với JSON null?

### Bài 23 — MySQL

Viết `JSON_CONTAINS_PATH` kiểm `$.profile.email` đối với `{"profile":{"email":null}}` và `{"profile":{}}`. Kết quả boolean khác nhau thế nào?

### Bài 24 — SQL Server và SQLite

Với SQL Server, giải thích vì sao `JSON_VALUE(...) IS NULL` chưa chứng minh path thiếu và cách `OPENJSON` giúp xem key/type. Với SQLite, viết `json_type(doc,'$.a')` cho JSON null và missing.

### Bài 25 — Oracle

Trình bày khác biệt giữa `JSON_EXISTS` và `JSON_VALUE`. Những trường hợp nào khiến scalar extract trả SQL NULL dù đường dẫn có thể tồn tại?

### Bài 26 — API PATCH

Một API update profile nhận ba payload:

```json
{}
```

```json
{"phone":null}
```

```json
{"phone":""}
```

Viết quy tắc xử lý theo **custom partial update**. Sau đó giải thích tại sao **JSON Merge Patch RFC 7396** dùng null để **xóa member**, và cách **JSON Patch RFC 6902** phân biệt remove với replace-to-null.

### Bài 27 — Validation kiểu dữ liệu

Một khách có `{"profile":{"email":false}}`. Vì sao `#>>` trả text `false` nhưng không đủ để coi email hợp lệ? Thiết kế validation theo hai bước: JSON type và định dạng email.

### Bài 28 — Quyền truy cập nhiều tenant

Viết câu tìm email string của tenant 10 mà không đọc tenant 20. Vì sao việc có JSONPath đúng không thay thế kiểm quyền?

### Bài 29 — So sánh hai truy vấn

Một lập trình viên thay:

```sql
WHERE payload @> '{"profile":{"email":null}}'::jsonb
```

bằng:

```sql
WHERE payload #>> '{profile,email}' IS NULL
```

Hãy chỉ ra **ít nhất ba record** trong lab khiến kết quả khác nhau. Truy vấn nào phù hợp khi muốn chọn **JSON null có khóa thực sự**?

### Bài 30 — Thiết kế tổng hợp

Bạn xây hệ thống đồng bộ profile từ nhiều đối tác. Bản JSON có thể thiếu email, email:null, email:"", email:"null", email sai kiểu hoặc root NULL. Hãy thiết kế:

1. Hợp đồng missing/null/empty.
2. Schema cột quan hệ và metadata JSONB.
3. Truy vấn phân loại trạng thái và validation kiểu.
4. Cách PATCH bảo toàn ý định xóa khác thiếu dữ liệu.
5. Chỉ mục theo workload và tenant.
6. Regression tests đủ các trạng thái.
7. Phân loại lỗi/ghi log an toàn, không lộ PII.

## 29. Checklist thao tác JSON an toàn

### Khi đọc

- [ ] Đường dẫn JSON đã được xác định chính xác đến đúng cấp?
- [ ] Kết quả cần là JSONB hay text/SQL scalar?
- [ ] Có cần phân biệt key thiếu với key JSON null?
- [ ] Parent có chắc là object/array đúng kiểu?
- [ ] Có tính tới root SQL NULL, root JSON null và string `"null"`?
- [ ] `false`, `0`, `""`, `[]` có được coi là giá trị hiện diện đúng?

### Khi lọc

- [ ] Dùng `?`/path existence cho sự hiện diện, không chỉ `->> IS NULL`?
- [ ] Nếu kiểm JSON null, có so sánh `'null'::jsonb`/type đúng?
- [ ] Có lọc tenant, authorization và trạng thái dữ liệu theo nghiệp vụ?
- [ ] JSONPath lax/strict có được hiểu đúng?
- [ ] Cách xử lý NULL trong biểu thức boolean đã rõ?

### Khi cập nhật

- [ ] Đã phân biệt **gán JSON null** với **xóa key**?
- [ ] Có bảo vệ `jsonb_set` trước đối số SQL NULL?
- [ ] Những parent path trung gian đã tồn tại và đúng kiểu?
- [ ] Có cần tránh strip nulls hoặc flatten mất trạng thái?
- [ ] Có transaction, kiểm số hàng và xử lý concurrency phù hợp?

### Khi tích hợp ứng dụng

- [ ] PATCH custom, Merge Patch hay JSON Patch được chỉ định rõ?
- [ ] Thư viện JSON có API kiểm `containsKey`/presence riêng không?
- [ ] Deserialization sang DTO có đang gộp missing và null?
- [ ] Có test biên, kiểu sai, chuỗi null, document root array/null?
- [ ] Kết quả JSON/PII có được bảo vệ trong log?

### Khi tối ưu và chuyển DBMS

- [ ] Operator class/index phù hợp với toán tử JSON thực sự dùng?
- [ ] Đã xác nhận correctness trước EXPLAIN/benchmark?
- [ ] Đã kiểm khác biệt JSON_EXTRACT/JSON_VALUE/json_type/JSON_EXISTS theo dialect?
- [ ] Đã kiểm phiên bản, collation, kiểu trả về và giới hạn?
- [ ] Có regression tests giữa hệ nguồn và hệ đích?

## 30. Sơ đồ tư duy: truy xuất một trường JSON

```text
             CẦN ĐỌC payload.profile.email
                           |
                           v
                    payload IS NULL?
                    /            \
                  Có             Không
                  |                |
                  v                v
           SQL NULL document    Root là object?
                                /             \
                              Không           Có
                               |              |
                               v              v
                         JSON null /      Có key profile?
                         array / scalar   /            \
                                        Không          Có
                                          |             |
                                          v             v
                                   PROFILE_MISSING   profile là object?
                                                      /          \
                                                    Không        Có
                                                      |           |
                                                      v           v
                                                null / sai kiểu  Có key email?
                                                                 /        \
                                                               Không      Có
                                                                 |         |
                                                                 v         v
                                                           EMAIL_MISSING  jsonb_typeof?
                                                                            |
                                                +------------+--------------+-----------+
                                                |            |                          |
                                              null         string                number/boolean/
                                                |            |                   array/object
                                                v            v                          v
                                           JSON_NULL      Đọc text và          Validate kiểu hoặc
                                           (key có)       validate email         reject theo schema
```

## 31. Tổng kết

**Truy xuất đường dẫn JSON** không chỉ là nhớ các toán tử `->`, `->>`, `#>` và `#>>`. Điều khó nhất là hiểu **giá trị nào đang được biểu diễn**: một khóa có giá trị bình thường, một khóa có JSON null, một khóa thiếu, một parent sai kiểu, một document SQL NULL, một root JSON null hay một chuỗi thực sự có nội dung `"null"`.

Với PostgreSQL, `->` và `#>` giữ giá trị JSONB nên có thể phân biệt JSON null với SQL NULL khi kết hợp `IS NULL`, `= 'null'::jsonb` và `jsonb_typeof`. Ngược lại, `->>` và `#>>` chuyển JSON null lẫn đường dẫn thiếu thành SQL NULL, phù hợp khi chỉ cần scalar text nhưng **không đủ khi cần biết key có được gửi hay không**. Toán tử `?` và các hàm JSONPath giúp kiểm sự hiện diện, với điều kiện hiểu đúng cấp kiểm tra, parent object và chế độ lax/strict.

Khi cập nhật, **gán `'null'::jsonb` không giống xóa khóa bằng `#-`**, và truyền SQL NULL vào hàm cập nhật không được đánh đồng với JSON null. Khi xuất JSON, flatten ra record hoặc dựng object từ SQL NULL, thông tin “missing” cũng có thể vô tình biến thành “present with null”. Trong API, chuẩn **JSON Merge Patch** và **JSON Patch** còn định nghĩa những hành động khác nhau cho null/remove.

Nguyên tắc bền vững là **kiểm sự hiện diện, kiểm kiểu JSON, rồi mới trích và diễn giải giá trị theo hợp đồng nghiệp vụ**. Thực hiện điều đó cùng test biên, index thích hợp, kiểm quyền/tenant và hiểu khác biệt giữa PostgreSQL, MySQL, SQL Server, SQLite, Oracle sẽ giúp hệ thống giữ đúng ý nghĩa dữ liệu thay vì lặng lẽ biến những trạng thái khác nhau thành một giá trị NULL duy nhất.
