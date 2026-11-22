# Thêm, sửa, xóa thành phần JSON và chi phí cập nhật trong PostgreSQL

Một ứng dụng thường lưu cấu hình linh hoạt, thông tin bổ sung hoặc thuộc tính chưa có schema cố định trong cột `jsonb`. Ví dụ một hồ sơ có cấu trúc:

~~~json
{
  "name": "Lan",
  "settings": {
    "theme": "light",
    "notifications": {
      "email": true,
      "sms": false
    }
  },
  "tags": ["vip", "email"],
  "addresses": [
    {"label": "home", "city": "Ha Noi"},
    {"label": "office", "city": "Da Nang"}
  ],
  "metrics": {"visits": 4},
  "nickname": null
}
~~~

Khi người dùng đổi giao diện từ `light` sang `dark`, ứng dụng chỉ muốn **sửa một giá trị lồng nhau**, không muốn thay toàn bộ tài liệu theo cách làm mất những thuộc tính không liên quan. Khi thêm một địa chỉ hay xóa một tag, ứng dụng cần hiểu rõ thao tác trên **JSON object** khác thao tác trên **JSON array** như thế nào.

PostgreSQL có các công cụ như `jsonb_set`, `jsonb_insert`, toán tử `||`, `-` và `#-` để thực hiện những việc đó trực tiếp bằng SQL. Tuy nhiên, **cập nhật một phần về mặt logic không đồng nghĩa cập nhật tại chỗ một vài byte về mặt lưu trữ**. PostgreSQL sử dụng MVCC; một câu `UPDATE` tạo phiên bản hàng mới và có thể phát sinh công việc trên JSONB, TOAST, index, WAL và VACUUM.

Bài học thuộc chương **JSON và mảng** của module **Database Engine Relational PostgreSQL**. Bạn sẽ học:

- Phân biệt `json` và `jsonb`, đặc biệt khi sửa dữ liệu.
- Thêm/sửa/xóa key ở cấp cao nhất và các nhánh lồng nhau.
- Thêm, chèn theo vị trí, thay, xóa phần tử của JSON array.
- Xử lý đường dẫn thiếu, JSON `null`, SQL `NULL` và dữ liệu không đúng kiểu.
- Tránh ghi đè thay đổi của transaction khác khi cập nhật cùng tài liệu.
- Hiểu chi phí ghi của JSONB với MVCC, TOAST, HOT update, B-tree/GIN và WAL.
- Đo lường chi phí thay vì giả định một hàm JSONB nào đó luôn nhanh.
- Biết khi nào nên giữ dữ liệu JSONB và khi nào nên tách thành bảng/cột quan hệ.

## 1. Ba mức của một thao tác chỉnh sửa JSON

Một yêu cầu “đổi theme thành dark” có ba lớp cần phân biệt:

1. **Ngữ nghĩa nghiệp vụ:** chỉ thay `settings.theme`, giữ nguyên tags, addresses và mọi field khác.
2. **Cú pháp SQL:** dùng hàm/toán tử JSONB để tạo tài liệu kết quả đúng.
3. **Lưu trữ và đồng thời:** PostgreSQL cập nhật tuple theo MVCC, duy trì index khi cần và phối hợp với transaction khác.

~~~mermaid
flowchart TD
    A["Yêu cầu: đổi settings.theme"] --> B["jsonb_set: tạo JSONB kết quả"]
    B --> C["UPDATE: phiên bản tuple mới theo MVCC"]
    C --> D["Heap và có thể TOAST"]
    C --> E["Index maintenance nếu liên quan"]
    C --> F["WAL và cleanup về sau"]
    D --> G["COMMIT hoặc ROLLBACK"]
    E --> G
    F --> G
~~~

Không nên kết luận “chỉ đổi 5 ký tự nên PostgreSQL chỉ ghi 5 byte”. SQL thực hiện **chỉnh sửa thành phần về mặt logic**, nhưng khả năng lưu trữ vật lý tùy cấu trúc row/JSONB/index.

## 2. Chọn json hay jsonb?

PostgreSQL có hai kiểu JSON chủ yếu:

| Tiêu chí | `json` | `jsonb` |
| --- | --- | --- |
| Dạng lưu trữ | Lưu biểu diễn văn bản JSON đầu vào | Dạng nhị phân đã phân tích |
| Khoảng trắng/thứ tự khóa input | Giữ lại theo biểu diễn gốc | Không bảo đảm giữ thứ tự khóa/format đầu vào |
| Khóa trùng trong object | Có thể giữ trong văn bản đầu vào | Chuẩn hóa để mỗi key có một giá trị; giá trị cuối có hiệu lực |
| Truy vấn/toán tử | Có các hàm truy xuất, nhưng hạn chế so với JSONB | Nhiều toán tử và hàm thao tác/so sánh |
| GIN index | Không trực tiếp theo cách JSONB | Có operator classes cho những truy vấn JSONB |
| Sửa một nhánh bằng `jsonb_set` | Cần chuyển sang JSONB trước | Hỗ trợ trực tiếp |
| Khi nào chọn | Cần giữ nguyên văn bản gốc vì lý do cụ thể | Phổ biến hơn cho tài liệu ứng dụng cần tìm kiếm, cập nhật |

Ví dụ:

~~~sql
SELECT
    '{"a":1,"a":2}'::json AS original_json,
    '{"a":1,"a":2}'::jsonb AS normalized_jsonb;
~~~

Với `jsonb`, object không giữ hai entry trùng `a` theo biểu diễn gốc. Đừng dùng JSONB nếu nghiệp vụ thật sự phụ thuộc vào thứ tự/format nguyên thủy của văn bản.

### Vì sao bài này dùng jsonb?

Các hàm `jsonb_set` và `jsonb_insert`, toán tử xóa `-`, `#-` và phép nối `||` trong những ví dụ đều thao tác trên `jsonb`. Nếu cột đang là `json`, chuyển kiểu `::jsonb` khi xử lý có thể thay đổi biểu diễn văn bản, rồi cast lại có chi phí và có thể không giữ format ban đầu.

**Với dữ liệu có nhu cầu chỉnh sửa nhiều và tìm kiếm theo thuộc tính, `jsonb` thường là lựa chọn thực dụng hơn.** Nhưng hãy cân nhắc chi phí update và mô hình schema, không chọn chỉ vì nó có chữ “binary”.

## 3. JSON object, JSON array và scalar khác nhau

Đây đều là JSON hợp lệ:

~~~json
{"key": "value"}
~~~

~~~json
["a", "b", 12, null]
~~~

~~~json
"hello"
~~~

~~~json
42
~~~

~~~json
true
~~~

~~~json
null
~~~

Hàm `jsonb_typeof` cho biết kiểu JSON ở giá trị đích:

~~~sql
SELECT
    jsonb_typeof('{"a":1}'::jsonb) AS object_type,
    jsonb_typeof('["a","b"]'::jsonb) AS array_type,
    jsonb_typeof('"abc"'::jsonb) AS string_type,
    jsonb_typeof('null'::jsonb) AS null_type;
~~~

Kết quả lần lượt là `object`, `array`, `string`, `null`.

Một **JSON array** không phải **PostgreSQL SQL array**:

~~~sql
SELECT
    '["vip","new"]'::jsonb AS json_array,
    ARRAY['vip','new']::text[] AS sql_array;
~~~

Cả hai trông giống danh sách, nhưng hỗ trợ hàm, toán tử, kiểu phần tử và indexing khác nhau. Không thể dùng `array_append` của SQL array rồi mặc định nó sửa trực tiếp một giá trị JSONB.

## 4. Chuẩn bị schema thực hành

Các ví dụ dùng schema `json_edit_lab`. Script bắt đầu bằng `DROP SCHEMA ... CASCADE` để dễ chạy lại từ đầu.

**Cảnh báo:** lệnh này xóa toàn bộ đối tượng thuộc schema `json_edit_lab` nếu có. Chỉ chạy trong **database thực hành riêng**, không chạy trên production hay schema chứa dữ liệu cần giữ.

### 4.1. Tạo bảng hồ sơ

~~~sql
-- CHỈ CHẠY TRONG DATABASE LAB.
DROP SCHEMA IF EXISTS json_edit_lab CASCADE;
CREATE SCHEMA json_edit_lab;

CREATE TABLE json_edit_lab.customer_profiles (
    profile_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    doc jsonb NOT NULL
        CHECK (jsonb_typeof(doc) = 'object'),
    version bigint NOT NULL DEFAULT 0
        CHECK (version >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

Thiết kế có chủ đích:

- `profile_id` là định danh quan hệ ổn định, **không phụ thuộc JSON path**.
- `email` có UNIQUE constraint phục vụ định danh và ngăn trùng.
- `doc` là JSONB object, không cho lưu array/scalar ở top-level.
- `version` dùng để minh họa optimistic concurrency control.
- `updated_at` cho biết thời điểm cập nhật nhưng không phải nguồn bảo đảm uniqueness.

Lưu ý `CHECK (jsonb_typeof(doc) = 'object')` **chỉ xác nhận top-level là object**. Nó không bảo đảm `settings` là object hay `tags` là array. Nếu cấu trúc lồng nhau quan trọng, phải kiểm tra riêng bằng constraint, ứng dụng hoặc schema validation phù hợp.

### 4.2. Nạp ba hồ sơ

~~~sql
INSERT INTO json_edit_lab.customer_profiles
    (profile_id, email, doc)
VALUES
(
    101,
    'lan@example.test',
    $json$
    {
      "name": "Lan",
      "settings": {
        "theme": "light",
        "notifications": {"email": true, "sms": false}
      },
      "tags": ["vip", "email"],
      "addresses": [
        {"label": "home", "city": "Ha Noi"},
        {"label": "office", "city": "Da Nang"}
      ],
      "metrics": {"visits": 4},
      "nickname": null
    }
    $json$::jsonb
),
(
    102,
    'minh@example.test',
    $json$
    {
      "name": "Minh",
      "settings": {
        "theme": "dark",
        "notifications": {"email": false}
      },
      "tags": [],
      "addresses": [],
      "metrics": {"visits": 0}
    }
    $json$::jsonb
),
(
    103,
    'hoa@example.test',
    $json$
    {
      "name": "Hoa",
      "tags": ["new"],
      "addresses": [
        {"label": "home", "city": "Hue"}
      ]
    }
    $json$::jsonb
);
~~~

Hai chi tiết cố ý:

- Hồ sơ **101** có đầy đủ object lồng nhau, nhiều tag, nhiều địa chỉ và `nickname: null`.
- Hồ sơ **103** **không có** `settings` hay `metrics`. Nó dùng để minh họa đường dẫn trung gian chưa tồn tại.

### 4.3. Kiểm tra dữ liệu

~~~sql
SELECT
    profile_id,
    email,
    jsonb_typeof(doc) AS root_type,
    jsonb_pretty(doc) AS pretty_doc
FROM json_edit_lab.customer_profiles
ORDER BY profile_id;
~~~

`jsonb_pretty` hữu ích khi xem tài liệu với format dễ đọc; không nên dựa vào thứ tự key trong output để biểu diễn thứ tự nghiệp vụ.

## 5. Đọc dữ liệu trước khi sửa

Những toán tử quan trọng:

| Cú pháp | Ý nghĩa | Kiểu kết quả |
| --- | --- | --- |
| `doc -> 'settings'` | Lấy giá trị JSON ở key top-level | JSONB |
| `doc ->> 'name'` | Lấy giá trị ở key dưới dạng text | text |
| `doc #> '{settings,theme}'` | Lấy giá trị JSONB theo đường dẫn nhiều cấp | JSONB |
| `doc #>> '{settings,theme}'` | Lấy giá trị theo đường dẫn dạng text | text |
| `doc ? 'nickname'` | Có key top-level `nickname` không? | boolean |
| `jsonb_typeof(doc->'tags')` | Kiểm tra kiểu JSON tại nhánh | text |

Ví dụ:

~~~sql
SELECT
    profile_id,
    doc ->> 'name' AS full_name,
    doc #>> '{settings,theme}' AS theme_text,
    doc #> '{settings,notifications,email}' AS email_json,
    doc -> 'tags' AS tags_json,
    doc ? 'nickname' AS has_nickname
FROM json_edit_lab.customer_profiles
ORDER BY profile_id;
~~~

Kết quả dự kiến:

| profile_id | name | theme_text | email_json | tags_json | has_nickname |
| ---: | --- | --- | --- | --- | --- |
| 101 | Lan | light | true | ["vip","email"] | true |
| 102 | Minh | dark | false | [] | false |
| 103 | Hoa | SQL NULL | SQL NULL | ["new"] | false |

Giữa “key không tồn tại” và “key có giá trị JSON null” có khác biệt quan trọng, sẽ được giải thích riêng.

## 6. jsonb_set: hàm trung tâm để thay một giá trị

Cú pháp thường dùng:

~~~sql
jsonb_set(
    target jsonb,
    path text[],
    new_value jsonb,
    create_if_missing boolean DEFAULT true
)
~~~

Các tham số:

1. `target`: tài liệu JSONB ban đầu.
2. `path`: đường dẫn dạng PostgreSQL `text[]`; với object là tên key, với array là vị trí số dưới dạng text.
3. `new_value`: **một giá trị JSONB hợp lệ**, không phải text tùy ý.
4. `create_if_missing`: cho phép tạo **phần tử cuối của path** nếu thiếu trong điều kiện phù hợp; mặc định true.

Ví dụ hàm thuần, chưa ghi database:

~~~sql
SELECT jsonb_set(
    '{"name":"Lan","settings":{"theme":"light"}}'::jsonb,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
) AS edited_doc;
~~~

Kết quả về nghĩa:

~~~json
{"name": "Lan", "settings": {"theme": "dark"}}
~~~

Dữ liệu ở key `name` được giữ nguyên.

### Điểm dễ nhầm: path là SQL text array

~~~sql
'{settings,theme}'::text[]
~~~

biểu diễn hai bước đường dẫn: `settings`, rồi `theme`. Nó **không phải JSON array** và không phải JSONPath kiểu `$.settings.theme`.

## 7. UPDATE một thuộc tính lồng nhau trong bảng

Đổi theme của Lan:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = jsonb_set(
        doc,
        '{settings,theme}',
        '"dark"'::jsonb,
        false
    ),
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
RETURNING
    profile_id,
    doc #>> '{settings,theme}' AS new_theme,
    version;

ROLLBACK;
~~~

Trong transaction, `new_theme = 'dark'`, `version = 1`. Sau `ROLLBACK`, hồ sơ quay lại seed ban đầu.

### Vì sao phải gán lại doc?

`jsonb_set` **trả về giá trị JSONB mới**; bản thân việc gọi hàm không sửa cột đang lưu. Muốn ghi thay đổi, phải:

~~~sql
UPDATE ...
SET doc = jsonb_set(doc, ...)
~~~

Tương tự:

~~~sql
SELECT jsonb_set(doc, ...)
FROM ...;
~~~

chỉ trả kết quả tính toán, không tự cập nhật table.

### Vì sao dùng RETURNING?

`RETURNING` cho biết giá trị sau UPDATE ngay trong cùng statement, không cần gửi thêm một lượt `SELECT` chỉ để xác nhận. Với request update, có thể kiểm tra `UPDATE 0` hoặc kết quả không có hàng để phát hiện ID không tồn tại hay điều kiện optimistic lock không thỏa.

## 8. Truyền text vào JSONB đúng cách

Cú pháp:

~~~sql
'"dark"'::jsonb
~~~

có **hai lớp dấu nháy**:

- Nháy đơn bao quanh SQL string literal.
- Nháy kép nằm bên trong biểu diễn **JSON string**.

Nếu viết:

~~~sql
-- CỐ Ý SAI: dark không phải JSON text hợp lệ.
SELECT 'dark'::jsonb;
~~~

PostgreSQL báo lỗi parse JSON vì token `dark` không phải string JSON được bao bởi nháy kép.

Một cách thích hợp khi nhận dữ liệu từ tham số ứng dụng:

~~~sql
SELECT to_jsonb('dark'::text);
~~~

Đối với object:

~~~sql
SELECT jsonb_build_object(
    'theme', 'dark',
    'enabled', true,
    'max_items', 10
);
~~~

Đối với array:

~~~sql
SELECT jsonb_build_array(
    'vip',
    'email',
    42,
    true
);
~~~

**Không tự ghép JSON bằng nối chuỗi** khi giá trị đến từ input người dùng. Dùng bind parameters, `to_jsonb`, `jsonb_build_object` hoặc `jsonb_build_array` để tránh lỗi escape và cấu trúc JSON sai.

## 9. Thêm key top-level bằng toán tử ||

Toán tử `||` nối hai giá trị JSONB. Với **object + object**, nó hợp nhất các key ở **cấp cao nhất**; nếu key trùng, giá trị từ object bên phải thay thế giá trị bên trái.

~~~sql
SELECT
    '{"name":"Lan","tier":"standard"}'::jsonb
    ||
    '{"tier":"gold","active":true}'::jsonb AS result;
~~~

Kết quả:

~~~json
{"name":"Lan","tier":"gold","active":true}
~~~

Để thêm key `language` vào hồ sơ:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = doc || jsonb_build_object('language', 'vi'),
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
RETURNING doc ->> 'language' AS language;

ROLLBACK;
~~~

### Khi nào dùng ||?

- Thêm một hoặc vài key top-level.
- Ghi đè một vài thuộc tính top-level một cách rõ ràng.
- Nối array với array theo quy tắc JSONB (khác với object merge).

**Cảnh báo:** `||` **không phải deep merge**. Với object lồng nhau, nó thay cả giá trị của key top-level tương ứng, không tự ghép từng key sâu bên trong.

## 10. Bẫy shallow merge làm mất dữ liệu lồng nhau

Tài liệu:

~~~json
{
  "settings": {
    "theme": "light",
    "notifications": {
      "email": true,
      "sms": false
    }
  }
}
~~~

Nếu dùng:

~~~sql
SELECT
    '{"settings":{"theme":"light","notifications":{"email":true,"sms":false}}}'::jsonb
    ||
    '{"settings":{"theme":"dark"}}'::jsonb
    AS result;
~~~

kết quả logic là:

~~~json
{"settings":{"theme":"dark"}}
~~~

Cả nhánh `notifications` đã bị thay thế. Đây có thể là lỗi dữ liệu nghiêm trọng nếu ứng dụng tưởng `||` sẽ deep merge.

### Cách sửa đúng một nhánh

~~~sql
SELECT jsonb_set(
    '{"settings":{"theme":"light","notifications":{"email":true,"sms":false}}}'::jsonb,
    '{settings,theme}',
    '"dark"'::jsonb
);
~~~

Kết quả vẫn giữ `notifications`.

**Quy tắc:** dùng `jsonb_set` khi cần thay đúng một đường dẫn sâu; chỉ dùng `||` cho merge cấp cao nhất khi bạn đã hiểu mọi key bị ghi đè.

## 11. Thêm một key lồng nhau đã có parent

Giả sử `settings.notifications` đã tồn tại ở hồ sơ 101. Thêm cờ `push`:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,notifications,push}',
    'true'::jsonb,
    true
)
WHERE profile_id = 101
RETURNING
    doc #> '{settings,notifications}' AS notifications;

ROLLBACK;
~~~

Kết quả trong transaction:

~~~json
{"email":true,"sms":false,"push":true}
~~~

Vì `settings` và `notifications` đã tồn tại và là object, `create_if_missing = true` cho phép tạo **key cuối `push`**.

### Thêm không đồng nghĩa phải thay một key đã có

Nếu key cuối đã tồn tại, `jsonb_set` **thay giá trị cũ** bằng `new_value`. Nó không phân biệt “create only” và “replace only” chỉ dựa vào tên hàm.

Muốn tránh ghi đè, có thể đặt điều kiện:

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,notifications,push}',
    'true'::jsonb,
    true
)
WHERE profile_id = 101
  AND NOT (
    (doc #> '{settings,notifications}') ? 'push'
  );
~~~

Điều kiện này giả định `settings.notifications` là object; nếu dữ liệu thực có thể thiếu hoặc sai kiểu, cần xử lý rõ ràng thay vì áp dụng trực tiếp toán tử lên giá trị bất kỳ.

## 12. create_if_missing không tự tạo mọi nhánh cha

Đây là lỗi rất phổ biến.

Hồ sơ 103 không có `settings`. Thử:

~~~sql
SELECT jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    true
) AS candidate
FROM json_edit_lab.customer_profiles
WHERE profile_id = 103;
~~~

Không nên kỳ vọng kết quả tự thành:

~~~json
{"name":"Hoa","settings":{"theme":"dark"}, ...}
~~~

Với `jsonb_set`, **các bước trung gian của path phải tồn tại**. `create_if_missing` cho phép thêm phần cuối của đường dẫn, **không phải tự sinh mọi object cha còn thiếu**.

### Cách dựng parent trước

Nếu muốn tạo nhánh `settings` mới khi chưa có, có thể cập nhật key top-level:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings}',
    jsonb_build_object('theme', 'dark'),
    true
)
WHERE profile_id = 103
RETURNING doc -> 'settings' AS settings;

ROLLBACK;
~~~

Bây giờ parent `settings` được tạo trực tiếp, nên không cần truy cập một path trung gian chưa tồn tại.

### Khi parent có thể đã tồn tại

Một cách an toàn hơn là giữ lại object `settings` nếu đã có:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings}',
    (
        CASE
            WHEN jsonb_typeof(doc -> 'settings') = 'object'
                THEN doc -> 'settings'
            ELSE '{}'::jsonb
        END
        ||
        jsonb_build_object('theme', 'dark')
    ),
    true
)
WHERE profile_id IN (101, 103)
RETURNING profile_id, doc -> 'settings';

ROLLBACK;
~~~

Cách này:

- Giữ những key khác của `settings` nếu nhánh đang là object.
- Tạo object mới nếu `settings` thiếu hoặc không phải object.
- Thêm/ghi đè `theme`.

**Lưu ý:** nhánh `ELSE '{}'` có chủ đích **thay thế dữ liệu nếu settings đang là scalar/array/null**. Trên production, bạn có thể nên **báo lỗi validation** thay vì âm thầm thay kiểu dữ liệu. Chọn hành vi theo quy tắc nghiệp vụ.

## 13. Xóa một key top-level bằng toán tử -

Với JSONB object, `- text` xóa key top-level được chỉ định:

~~~sql
SELECT
    '{"name":"Lan","nickname":null,"active":true}'::jsonb
    - 'nickname'
    AS without_nickname;
~~~

Kết quả:

~~~json
{"name":"Lan","active":true}
~~~

Xóa `nickname` trong bảng:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = doc - 'nickname',
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
RETURNING
    doc ? 'nickname' AS key_still_exists,
    doc;

ROLLBACK;
~~~

`key_still_exists` là `false` trong transaction.

### Xóa key khác với đặt JSON null

- `doc - 'nickname'`: **key không còn tồn tại**.
- `jsonb_set(doc,'{nickname}','null'::jsonb,true)`: **key vẫn tồn tại**, giá trị là JSON null.

Sự khác biệt này quan trọng khi API phân biệt “chưa có giá trị”, “được xóa” và “được người dùng chủ động đặt thành null”.

## 14. Xóa một key lồng nhau bằng #-

Toán tử `#- text[]` xóa phần tử ở một đường dẫn nhiều cấp:

~~~sql
SELECT
    '{"settings":{"theme":"light","notifications":{"email":true,"sms":false}}}'::jsonb
    #- '{settings,notifications,sms}'
    AS result;
~~~

Kết quả:

~~~json
{
  "settings": {
    "theme": "light",
    "notifications": {"email": true}
  }
}
~~~

Trong bảng:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = doc #- '{settings,notifications,sms}'
WHERE profile_id = 101
RETURNING doc #> '{settings,notifications}' AS remaining;

ROLLBACK;
~~~

### Điều gì xảy ra nếu path không có?

Nếu không có phần tử tại path cần xóa, việc xóa thường không làm phát sinh phần tử mới; biểu thức có thể trả tài liệu không đổi. Nhưng đừng dùng sự im lặng này làm xác nhận nghiệp vụ “đã xóa một thuộc tính tồn tại”.

Nếu cần biết có key trước đó không, hãy kiểm tra bằng query hoặc thêm điều kiện phù hợp trong `WHERE` và xem `RETURNING`/số hàng tác động.

## 15. JSON array: vị trí bắt đầu từ 0

Trong JSONB path đến phần tử array, chỉ số bắt đầu từ **0**:

~~~json
["vip", "email", "loyal"]
~~~

| Chỉ số | Giá trị |
| ---: | --- |
| 0 | "vip" |
| 1 | "email" |
| 2 | "loyal" |
| -1 | "loyal" (tính từ cuối) |
| -2 | "email" |

Ví dụ:

~~~sql
SELECT
    '["vip","email","loyal"]'::jsonb -> 0 AS first_tag,
    '["vip","email","loyal"]'::jsonb -> -1 AS last_tag;
~~~

Các đường dẫn `text[]` dùng số dưới dạng text:

~~~sql
'{tags,0}'
'{tags,-1}'
'{addresses,0,city}'
~~~

**Không nhầm** chỉ số JSON array bắt đầu từ 0 với chỉ số mặc định của PostgreSQL SQL array thường bắt đầu từ 1.

## 16. Thay phần tử JSON array bằng jsonb_set

Hồ sơ 101 có `tags = ["vip","email"]`.

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags,1}',
    '"priority"'::jsonb,
    false
)
WHERE profile_id = 101
RETURNING doc -> 'tags' AS tags;

ROLLBACK;
~~~

Trong transaction:

~~~json
["vip", "priority"]
~~~

Với index `1`, hàm thay phần tử thứ hai của array.

### Thay phần tử cuối

~~~sql
SELECT jsonb_set(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,-1}',
    '"last-updated"'::jsonb,
    false
);
~~~

Đường dẫn âm giúp chọn phần tử tính từ cuối array.

### Không nên tin index vẫn đúng khi array thay đổi đồng thời

Nếu client A đọc array 2 phần tử, client B chèn phần tử ở đầu, rồi client A gửi “sửa phần tử index 1”, index 1 lúc này có thể là **phần tử khác**.

Khi phần tử có **identity nghiệp vụ** (address_id, item_id), cập nhật theo index rất dễ sai nếu danh sách có thể sắp xếp/chèn/xóa. Cân nhắc lưu array element có ID và thực hiện cập nhật với xác nhận version, hoặc tách thành bảng con.

## 17. Thêm phần tử vào cuối JSON array bằng ||

Nối hai JSONB array:

~~~sql
SELECT
    '["vip","email"]'::jsonb
    ||
    '["priority"]'::jsonb AS merged_tags;
~~~

Kết quả:

~~~json
["vip","email","priority"]
~~~

Trong bảng:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags}',
    (doc -> 'tags') || jsonb_build_array('priority'),
    true
)
WHERE profile_id = 101
RETURNING doc -> 'tags' AS tags;

ROLLBACK;
~~~

### Dùng jsonb_build_array để không mất cấu trúc

Nếu cần thêm object địa chỉ:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{addresses}',
    (doc -> 'addresses')
      || jsonb_build_array(
           jsonb_build_object(
               'label', 'warehouse',
               'city', 'Hai Phong'
           )
         ),
    true
)
WHERE profile_id = 101
RETURNING doc -> 'addresses' AS addresses;

ROLLBACK;
~~~

`jsonb_build_array(jsonb_build_object(...))` tạo **một array có một object**, rồi nối vào array địa chỉ hiện có.

### Nếu tags không tồn tại?

Với hồ sơ 103 có `tags`, nhưng trong dữ liệu chung có thể thiếu. Trường hợp thiếu, có thể dùng:

~~~sql
COALESCE(doc -> 'tags', '[]'::jsonb)
  || jsonb_build_array('priority')
~~~

Điều này xử lý **SQL NULL do key không tồn tại**. Nó **không** tự xác nhận nhánh có kiểu array; nếu giá trị là JSON `null`, object hay scalar, phép `||` có thể mang ngữ nghĩa khác hoặc tạo cấu trúc ngoài mong muốn. Nên kiểm tra `jsonb_typeof` trước khi append.

## 18. Chèn phần tử JSON array vào vị trí với jsonb_insert

`jsonb_insert` được dùng khi muốn **chèn** một phần tử thay vì **ghi đè** phần tử đang có.

Cú pháp:

~~~sql
jsonb_insert(
    target jsonb,
    path text[],
    new_value jsonb,
    insert_after boolean DEFAULT false
)
~~~

Với array:

- `insert_after = false`: chèn **trước** vị trí chỉ định.
- `insert_after = true`: chèn **sau** vị trí chỉ định.

Ví dụ:

~~~sql
SELECT jsonb_insert(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,1}',
    '"priority"'::jsonb,
    false
) AS result;
~~~

Kết quả:

~~~json
{"tags":["vip","priority","email"]}
~~~

Chèn sau index 0:

~~~sql
SELECT jsonb_insert(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,0}',
    '"priority"'::jsonb,
    true
);
~~~

Kết quả logic vẫn là:

~~~json
{"tags":["vip","priority","email"]}
~~~

### Khác jsonb_set

| Hàm | Với path đến array index 1 |
| --- | --- |
| `jsonb_set` | Thay phần tử ở index 1 khi tồn tại |
| `jsonb_insert` | Chèn vào gần vị trí index 1, dịch những phần tử còn lại |

`jsonb_insert` cũng có quy tắc riêng nếu phần tử cuối là object key; nó không giống hàm “merge object tùy ý”. Các nhánh trung gian của path vẫn cần phù hợp.

## 19. Xóa phần tử array theo chỉ số

Có thể dùng `#-` với nested path:

~~~sql
SELECT
    '{"tags":["vip","email","priority"]}'::jsonb
    #- '{tags,1}' AS result;
~~~

Kết quả:

~~~json
{"tags":["vip","priority"]}
~~~

Trong bảng:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = doc #- '{addresses,0}'
WHERE profile_id = 101
RETURNING doc -> 'addresses' AS remaining_addresses;

ROLLBACK;
~~~

Hồ sơ 101 còn địa chỉ `office`.

### Xóa index làm các index phía sau thay đổi

Nếu xóa `addresses[0]`, phần tử trước kia ở `addresses[1]` sẽ trở thành `addresses[0]`. Client lưu “địa chỉ chính = index 1” sẽ không còn ý nghĩa ổn định.

Dùng index số khi thứ tự danh sách thực sự là mô hình nghiệp vụ. Nếu mỗi phần tử cần định danh, nên có `address_id` hoặc một bảng `profile_addresses` với primary key.

## 20. Xóa phần tử array theo giá trị string

Với JSONB array chứa string, toán tử `- text` xóa các phần tử string phù hợp:

~~~sql
SELECT
    '["vip","email","vip","priority"]'::jsonb
    - 'vip' AS remaining_tags;
~~~

Kết quả:

~~~json
["email","priority"]
~~~

Trong bảng, cần lấy nhánh array trước, xử lý, rồi gắn lại:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags}',
    (doc -> 'tags') - 'vip',
    false
)
WHERE profile_id = 101
RETURNING doc -> 'tags' AS tags;

ROLLBACK;
~~~

### Phân biệt hai trường hợp

- `doc - 'vip'` nếu `doc` là top-level object: xóa **key top-level `vip`**, không tìm mọi nơi trong tài liệu.
- `(doc -> 'tags') - 'vip'` khi nhánh tags là array: xóa những phần tử **string** phù hợp trong array đó.

Toán tử này không xóa object trong array chỉ vì object có field `tag` mang giá trị "vip". Với array các object, cần lọc/rebuild có kiểm soát hoặc mô hình quan hệ phù hợp.

## 21. Xóa object trong JSON array theo thuộc tính

Giả sử các địa chỉ có dạng:

~~~json
[
  {"label":"home","city":"Ha Noi"},
  {"label":"office","city":"Da Nang"}
]
~~~

Muốn bỏ mọi object có `label = 'office'`, không thể áp dụng đơn giản `- 'office'` lên array như với string vì object không phải string đó.

Một cách là chuyển array thành các hàng, lọc rồi tổng hợp lại theo thứ tự ban đầu:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles AS p
SET doc = jsonb_set(
    p.doc,
    '{addresses}',
    COALESCE(
        (
            SELECT jsonb_agg(e.value ORDER BY e.ordinality)
            FROM jsonb_array_elements(p.doc -> 'addresses')
                 WITH ORDINALITY AS e(value, ordinality)
            WHERE e.value ->> 'label' IS DISTINCT FROM 'office'
        ),
        '[]'::jsonb
    ),
    false
)
WHERE p.profile_id = 101
  AND jsonb_typeof(p.doc -> 'addresses') = 'array'
RETURNING p.doc -> 'addresses' AS addresses;

ROLLBACK;
~~~

Trong transaction còn:

~~~json
[{"label":"home","city":"Ha Noi"}]
~~~

### Tại sao phải ORDER BY ordinality?

`jsonb_array_elements` mở array thành nhiều hàng. Trong SQL, kết quả của aggregate `jsonb_agg` **không cam kết thứ tự theo nguồn nếu không chỉ rõ**. `WITH ORDINALITY` cho số thứ tự từ 1, rồi `ORDER BY e.ordinality` giữ thứ tự ban đầu của các phần tử còn lại.

### Tại sao dùng COALESCE?

Nếu filter xóa hết mọi phần tử, `jsonb_agg` trả **SQL NULL** khi không có hàng đầu vào. `COALESCE(...,'[]'::jsonb)` bảo đảm nhánh `addresses` trở thành **array rỗng**, không phải SQL NULL.

### Rủi ro

Câu lệnh trên dựng lại toàn bộ mảng; với hàng nghìn object trong một JSON document, CPU/độ rộng giá trị/chi phí UPDATE có thể lớn. Nếu thao tác tìm/xóa địa chỉ theo ID rất thường xuyên, bảng con quan hệ thường thích hợp hơn.

## 22. Sửa thuộc tính của một object trong JSON array

Ví dụ đổi `city` của địa chỉ đầu tiên:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{addresses,0,city}',
    to_jsonb('Hai Phong'::text),
    false
)
WHERE profile_id = 101
RETURNING doc -> 'addresses' AS addresses;

ROLLBACK;
~~~

Kết quả logic trong transaction:

~~~json
[
  {"label":"home","city":"Hai Phong"},
  {"label":"office","city":"Da Nang"}
]
~~~

`{addresses,0,city}` là ba bước:

1. Key `addresses` ở object.
2. Phần tử array index `0`.
3. Key `city` trong object đó.

### Có nên dùng index 0 để cập nhật địa chỉ?

Chỉ khi thứ tự danh sách được định nghĩa rõ và ứng dụng chắc phần tử 0 vẫn là địa chỉ cần sửa. Với nhiều người dùng đồng thời thêm/xóa/reorder địa chỉ, nên dùng một **ID ổn định trong từng phần tử**, rồi kiểm tra version hoặc chuyển sang bảng con có khóa riêng.

## 23. Xử lý JSON null và SQL NULL

Đây là lỗi rất dễ làm mất dữ liệu.

JSON chứa:

~~~json
{"nickname": null}
~~~

và JSON:

~~~json
{}
~~~

**không giống nhau**.

Với hồ sơ 101:

~~~sql
SELECT
    doc ? 'nickname' AS key_present,
    doc -> 'nickname' AS raw_json_value,
    jsonb_typeof(doc -> 'nickname') AS json_value_type,
    doc ->> 'nickname' AS text_value
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

Ý nghĩa:

- `key_present = true`: key tồn tại.
- `raw_json_value` là giá trị JSONB `null`, **khác SQL NULL**.
- `json_value_type = 'null'`: đây là JSON null.
- `text_value` là SQL NULL khi chuyển qua `->>`.

Nếu key không tồn tại, `doc -> 'nickname'` thường trả **SQL NULL**, và `jsonb_typeof(SQL NULL)` cũng là SQL NULL.

### Bảng phân biệt

| Trường hợp | `doc ? 'nickname'` | `jsonb_typeof(doc->'nickname')` |
| --- | --- | --- |
| Không có key | false | SQL NULL |
| Có key và JSON null | true | text `null` |
| Có key và JSON string | true | text `string` |
| Có key và JSON number | true | text `number` |

**Không chỉ dùng `doc->>'nickname' IS NULL` để kết luận key không tồn tại.** Nó có thể NULL vì JSON null hoặc vì thiếu key.

## 24. Đặt JSON null khác xóa key

Đặt giá trị JSON null:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{nickname}',
    'null'::jsonb,
    true
)
WHERE profile_id = 102
RETURNING
    doc ? 'nickname' AS has_key,
    jsonb_typeof(doc -> 'nickname') AS value_type;

ROLLBACK;
~~~

Kết quả `has_key = true`, `value_type = 'null'`.

Xóa key:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = doc - 'nickname'
WHERE profile_id = 101
RETURNING doc ? 'nickname' AS has_key;

ROLLBACK;
~~~

Kết quả `has_key = false`.

### SQL NULL trong tham số new_value

Đừng tùy tiện truyền `NULL::jsonb` vào `jsonb_set` rồi mong nó đồng nghĩa với JSON literal `null`:

~~~sql
-- SQL NULL và JSON null là hai giá trị khác nhau.
SELECT
    NULL::jsonb AS sql_null,
    'null'::jsonb AS json_null;
~~~

`jsonb_set` với new_value là **SQL NULL** có thể tạo kết quả SQL NULL theo tính strict của hàm, dẫn tới làm cột `doc NOT NULL` vi phạm ràng buộc nếu đem gán trực tiếp.

Dùng `'null'::jsonb` hoặc một API xử lý NULL có chủ đích.

## 25. jsonb_set_lax và chính sách với SQL NULL

PostgreSQL có hàm `jsonb_set_lax` trong các phiên bản hỗ trợ. Nó giúp xử lý khi `new_value` là **SQL NULL**:

~~~sql
jsonb_set_lax(
    target jsonb,
    path text[],
    new_value jsonb,
    create_if_missing boolean DEFAULT true,
    null_value_treatment text DEFAULT 'use_json_null'
)
~~~

Các chiến lược thường gặp:

| `null_value_treatment` | Ý nghĩa khi new_value là SQL NULL |
| --- | --- |
| `use_json_null` | Đặt giá trị JSON null |
| `delete_key` | Xóa phần tử ở path |
| `return_target` | Trả tài liệu ban đầu |
| `raise_exception` | Báo lỗi để bắt buộc caller xử lý |

Ví dụ xóa nickname khi tham số mới là SQL NULL:

~~~sql
SELECT jsonb_set_lax(
    '{"nickname":"Lannie","active":true}'::jsonb,
    '{nickname}',
    NULL::jsonb,
    true,
    'delete_key'
);
~~~

Kết quả:

~~~json
{"active":true}
~~~

Khi `new_value` **không** là SQL NULL, `jsonb_set_lax` xử lý tương tự `jsonb_set` về việc thay giá trị tại path.

### Khi nào dùng?

Khi interface cập nhật phân biệt rõ các ý nghĩa:

- Giá trị thật để ghi.
- JSON null để giữ key nhưng biểu thị trống.
- Xóa key.
- Không thay đổi.
- Từ chối SQL NULL không hợp lệ.

Không nên để mọi null từ Java/JDBC tự biến thành “xóa key” nếu API chưa định nghĩa rõ điều đó.

## 26. JSONB subscripting assignment

Trong những PostgreSQL phiên bản hỗ trợ JSONB subscripting assignment (từ PostgreSQL 14), có thể cập nhật path bằng cú pháp gần với truy cập mảng:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc['settings']['theme'] = '"dark"'::jsonb
WHERE profile_id = 101
RETURNING doc #>> '{settings,theme}' AS theme;

ROLLBACK;
~~~

Đây là **một cách diễn đạt cập nhật JSONB khác**, không phải viết trực tiếp vào đúng vài byte trên đĩa.

### Khác biệt cần chú ý

- Các bản PostgreSQL cũ hơn có thể không hỗ trợ cú pháp này.
- Các quy tắc khi nhánh trung gian thiếu, có JSON null, hoặc array index ngoài khoảng **không hoàn toàn giống mọi tùy chọn của `jsonb_set`**.
- Với mảng, subscripting có thể tạo phần tử null ở những vị trí cần điền khi gán ngoài độ dài, tùy trường hợp.
- Giá trị gán phải có kiểu JSONB thích hợp.

Trước khi chuyển code đang chạy ổn từ `jsonb_set` sang subscripting, hãy xác nhận semantics trên **đúng major version** và bộ dữ liệu có missing paths/arrays.

**Đừng chọn cú pháp ngắn hơn rồi giả định chi phí vật lý của UPDATE thấp hơn.** Cả hai đều đi qua cơ chế cập nhật row/JSONB của PostgreSQL.

## 27. Một PATCH nhiều thuộc tính bằng nhiều jsonb_set

Giả sử trong một request, người dùng đổi theme và bật push notification. Có thể lồng các lời gọi:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    jsonb_set(
        doc,
        '{settings,theme}',
        '"dark"'::jsonb,
        false
    ),
    '{settings,notifications,push}',
    'true'::jsonb,
    true
)
WHERE profile_id = 101
RETURNING doc -> 'settings' AS settings;

ROLLBACK;
~~~

Điểm tốt:

- Một SQL `UPDATE` trên một hàng.
- Cả hai thay đổi thuộc cùng một statement/transaction.
- Nếu lỗi constraint/transaction, không tự commit một thay đổi và bỏ thay đổi còn lại.

Điểm cần cân nhắc:

- Mỗi lần gọi hàm tạo kết quả JSONB trung gian để dùng trong biểu thức tiếp theo.
- Với nhiều path khác nhau và tài liệu lớn, có thể tốn CPU/allocations hơn thao tác trên một cấu trúc nhỏ đã được chuẩn hóa.
- Hãy đo với dữ liệu thực nếu request PATCH thường sửa hàng trăm path.

### PATCH top-level đơn giản

Nếu chỉ sửa key top-level có thể dùng:

~~~sql
doc || jsonb_build_object(
    'language', 'vi',
    'timezone', 'Asia/Ho_Chi_Minh'
)
~~~

nhưng không dùng dạng đó cho deep merge nếu muốn giữ toàn bộ object con.

## 28. JSONB không tự xác nhận schema lồng nhau

Kiểu `jsonb` cho phép nhiều cấu trúc:

~~~json
{"tags": ["vip", "new"]}
~~~

~~~json
{"tags": "vip"}
~~~

~~~json
{"tags": null}
~~~

Nếu ứng dụng luôn giả định `tags` là array rồi chạy:

~~~sql
jsonb_array_elements(doc -> 'tags')
~~~

mà thực tế gặp string/scalar hoặc JSON null, câu lệnh có thể lỗi.

### Kiểm tra kiểu trong UPDATE

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags}',
    (doc -> 'tags') || jsonb_build_array('priority'),
    false
)
WHERE profile_id = 101
  AND jsonb_typeof(doc -> 'tags') = 'array';
~~~

Câu này chỉ cập nhật khi `tags` là array.

### Đưa quy tắc vào CHECK khi cần

Ví dụ một table mới bắt buộc `tags` luôn là array:

~~~sql
CREATE TABLE json_edit_lab.strict_profiles (
    profile_id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (
        jsonb_typeof(doc) = 'object'
        AND doc ? 'tags'
        AND jsonb_typeof(doc -> 'tags') = 'array'
    )
);
~~~

Việc kiểm tra đủ fields phức tạp có thể cần một chiến lược schema rõ ràng, các cột quan hệ hoặc validation ở ứng dụng bên cạnh constraint. `CHECK` không phải JSON Schema validator hoàn chỉnh.

**Lưu ý về SQL three-valued logic:** một biểu thức `CHECK` có kết quả UNKNOWN/NULL thường **không** bị coi là vi phạm. Nếu muốn buộc field tồn tại và đúng kiểu, phải diễn đạt điều kiện sao cho missing path không vô tình được chấp nhận, như trong ví dụ dùng `doc ? 'tags'`.

## 29. SQL array khác JSON array khi chỉnh sửa

Giả sử có cột SQL array:

~~~sql
CREATE TABLE json_edit_lab.sql_array_demo (
    id integer PRIMARY KEY,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[]
);

INSERT INTO json_edit_lab.sql_array_demo
    (id, tags)
VALUES
    (1, ARRAY['vip','email']);
~~~

Thêm phần tử SQL array:

~~~sql
UPDATE json_edit_lab.sql_array_demo
SET tags = array_append(tags, 'priority')
WHERE id = 1;
~~~

Xóa giá trị:

~~~sql
UPDATE json_edit_lab.sql_array_demo
SET tags = array_remove(tags, 'vip')
WHERE id = 1;
~~~

Đọc:

~~~sql
SELECT id, tags, tags[1] AS first_tag
FROM json_edit_lab.sql_array_demo;
~~~

Với SQL array, chỉ số mặc định thường bắt đầu từ **1**; với JSON array subscripts, chỉ số phần tử thường bắt đầu từ **0**.

### Nên chọn SQL array hay JSON array?

| Trường hợp | Lựa chọn nên cân nhắc |
| --- | --- |
| Danh sách thuần nhất các giá trị `text`, `int`, ... | SQL array |
| Mảng chứa object có nhiều thuộc tính | JSONB array hoặc bảng con |
| Cần quan hệ giữa phần tử và bảng khác, FK, cập nhật độc lập | Bảng quan hệ |
| Payload linh hoạt từ API với schema thay đổi | JSONB |
| Tìm containment/overlap trên array lớn | Cần xem operator/index phù hợp của SQL array hoặc JSONB |

Không có lựa chọn đúng cho mọi trường hợp. Quyết định phụ thuộc query pattern, cập nhật thường xuyên, ràng buộc và concurrency.

## 30. Một UPDATE JSONB có phải sửa tại chỗ phần nhỏ tài liệu?

**Không theo nghĩa “in-place patch vài byte trong stored JSONB”.**

Giả sử `doc` có 1 MB, trong đó `settings.theme` chỉ dài 5 ký tự. Câu:

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id = 101;
~~~

là cập nhật **giá trị JSONB của cột** trong một phiên bản hàng PostgreSQL mới.

Với MVCC:

1. PostgreSQL phải tính ra giá trị `doc` mới.
2. `UPDATE` tạo một phiên bản tuple mới (trừ những chi tiết triển khai tối ưu riêng).
3. Tùy độ lớn, cột `doc` có thể được lưu inline, nén hoặc ngoài bảng bằng TOAST.
4. Các index liên quan có thể cần entry mới và dọn entry cũ theo cơ chế MVCC.
5. Có thể phát sinh WAL, dirty pages và VACUUM work.

**Không nên tuyên bố PostgreSQL luôn ghi lại chính xác toàn bộ 1 MB xuống đĩa mỗi lần**, vì TOAST/nén, WAL, page management và tối ưu trên những giá trị không đổi làm chi phí thực tế phức tạp hơn. Nhưng cũng không nên nghĩ việc sửa một path đã miễn chi phí tái tạo/ghi JSONB.

## 31. MVCC và phiên bản hàng khi cập nhật

PostgreSQL không ghi đè trực tiếp tuple hiện có theo mô hình làm các snapshot cũ không thể đọc được.

~~~text
T0: doc phiên bản A
    {"settings":{"theme":"light"}, ...}

T1: UPDATE jsonb_set(...)
    tạo phiên bản tuple B
    {"settings":{"theme":"dark"}, ...}

Reader có snapshot cũ có thể còn thấy A.
Reader phù hợp sau COMMIT có thể thấy B.
VACUUM dọn phiên bản đủ điều kiện khi không còn cần thiết.
~~~

Điều này đúng với UPDATE cột số nguyên, text hay JSONB. Nhưng JSONB thường là giá trị phức tạp và có thể rất lớn, khiến việc tạo giá trị mới, nén/TOAST và duy trì index tốn nhiều tài nguyên hơn sửa một cột scalar nhỏ.

### Một hàng chứa nhiều thứ ngoài doc

Nếu table có:

~~~text
profile_id | email | doc | version | updated_at
~~~

và chỉ đổi `doc`, PostgreSQL vẫn quản lý **phiên bản row**. Vì vậy cần hiểu chi phí nằm ở mức tuple/transaction, không chỉ trong một lời gọi `jsonb_set`.

## 32. TOAST và JSONB lớn

PostgreSQL dùng **TOAST** để xử lý giá trị có kích thước lớn vượt khả năng/chiến lược lưu trữ inline của heap tuple. Dữ liệu JSONB lớn có thể được nén, lưu out-of-line, hoặc kết hợp tùy storage settings và kích thước.

Ví dụ một tài liệu chứa:

- 5.000 lịch sử thao tác.
- 3.000 địa chỉ hoặc item.
- Text mô tả hàng trăm KB.
- Một mảng lớn các object.

Chỉ sửa `settings.theme` có thể cần xây dựng lại giá trị JSONB logic đáng kể, và nếu giá trị `doc` thay đổi, cơ chế TOAST có thể phải xử lý giá trị mới. Chi phí thực tế còn phụ thuộc mức nén/kiểu lưu trữ.

### Giá trị TOAST không thay đổi và giá trị JSONB bị sửa khác nhau

Nếu một cột TOAST lớn **không thay đổi** trong một UPDATE chỉ sửa cột khác, PostgreSQL có thể giữ tham chiếu tới giá trị TOAST cũ theo cơ chế lưu trữ.

Nhưng nếu chính **`doc` được thay đổi** bởi `jsonb_set`, không nên mặc định PostgreSQL có thể chỉ vá một fragment của TOAST value tại chỗ. Cần đo IO/WAL/TOAST behavior trên dữ liệu thật.

### Tác động thiết kế

Nếu một trường nhỏ `theme` thay đổi rất thường xuyên còn lịch sử dài hàng MB gần như bất biến, cân nhắc **tách theme thành cột quan hệ** hoặc một bảng cấu hình riêng, thay vì mỗi thao tác theme đều cập nhật một JSONB document khổng lồ.

## 33. HOT update có liên quan gì tới JSONB?

**HOT (Heap-Only Tuple)** là tối ưu PostgreSQL giúp một UPDATE có thể tránh tạo thêm index entries khi các điều kiện thỏa, bao gồm việc không thay đổi cột có liên quan tới các index không thuộc nhóm ngoại lệ và còn không gian phù hợp trên cùng heap page.

Ví dụ chỉ có:

~~~sql
CREATE TABLE json_edit_lab.hot_demo (
    id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    note text
);
~~~

Nếu bảng chỉ index `id`, một UPDATE vào `doc` có thể **đủ điều kiện HOT** khi giá trị index `id` không đổi và có đủ không gian trong heap page.

Nhưng nếu thêm:

~~~sql
CREATE INDEX idx_hot_demo_doc_gin
ON json_edit_lab.hot_demo
USING gin (doc);
~~~

một UPDATE thay đổi `doc` liên quan đến cột được index. Điều này thường làm giảm hoặc loại bỏ khả năng HOT cho những UPDATE doc theo quy tắc index tương ứng.

### Vì sao quan trọng?

Không HOT có thể dẫn tới nhiều entry index phải được duy trì cho tuple version mới. Nếu bảng có nhiều index, write amplification có thể tăng đáng kể.

**Không kết luận mọi UPDATE JSONB không có GIN đều HOT.** Khả năng HOT còn phụ thuộc:

- Không gian trên heap page.
- Độ rộng tuple và row growth.
- Những index khác, bao gồm expression/partial/INCLUDE.
- Kiểu index và các tối ưu phụ thuộc phiên bản.
- Trạng thái bảng và phân bố DML.

## 34. GIN index giúp đọc nhưng làm ghi tốn thêm

JSONB thường được tìm theo containment:

~~~sql
SELECT profile_id
FROM json_edit_lab.customer_profiles
WHERE doc @> '{"settings":{"theme":"dark"}}'::jsonb;
~~~

Có thể tạo GIN index:

~~~sql
CREATE INDEX idx_customer_profiles_doc_gin
ON json_edit_lab.customer_profiles
USING gin (doc);
~~~

GIN có thể phục vụ nhiều toán tử tìm kiếm JSONB khi operator class hỗ trợ.

### Lợi ích

- Tìm object/array chứa những cặp key/value phù hợp.
- Truy vấn các thuộc tính linh hoạt không có cột scalar riêng.
- Có thể giảm đáng kể số row phải kiểm tra trên tập dữ liệu lớn khi predicate đủ chọn lọc.

### Chi phí

- Tăng dung lượng index.
- INSERT/UPDATE JSONB có thể phải duy trì nhiều index entries.
- Có thêm CPU, buffer changes, WAL, VACUUM/maintenance.
- GIN có cơ chế pending-list/fastupdate với những đặc tính latency riêng.
- Một index trên toàn `doc` có thể rất đắt khi tài liệu lớn và thường xuyên thay đổi.

**GIN index không bảo đảm tăng tốc mọi query JSONB**. Với bảng ba hàng trong lab, PostgreSQL có thể vẫn chọn Seq Scan vì đọc toàn bảng quá rẻ.

## 35. jsonb_ops và jsonb_path_ops

Hai operator class thường gặp của GIN JSONB:

~~~sql
CREATE INDEX idx_doc_ops
ON json_edit_lab.customer_profiles
USING gin (doc jsonb_ops);
~~~

~~~sql
CREATE INDEX idx_doc_path_ops
ON json_edit_lab.customer_profiles
USING gin (doc jsonb_path_ops);
~~~

Mỗi operator class hỗ trợ tập toán tử và cách tạo entry khác nhau.

| Operator class | Đặc điểm thực hành |
| --- | --- |
| `jsonb_ops` | Mặc định, hỗ trợ nhiều toán tử JSONB, bao gồm các toán tử existence key phù hợp |
| `jsonb_path_ops` | Thường gọn và hiệu quả hơn cho một số truy vấn containment/jsonpath hỗ trợ, nhưng không hỗ trợ toàn bộ tập toán tử như `jsonb_ops` |

Ví dụ:

~~~sql
WHERE doc @> '{"settings":{"theme":"dark"}}'::jsonb
~~~

là kiểu truy vấn containment cần cân nhắc GIN.

Trong khi:

~~~sql
WHERE doc ? 'tags'
~~~

dùng toán tử existence key top-level. Không tự giả định mọi operator class đều hỗ trợ giống nhau.

### Không tạo cả hai mà không có lý do

Nếu tạo `jsonb_ops` và `jsonb_path_ops` trên cùng cột, ứng dụng phải trả chi phí ghi/duy trì **cả hai index**. Chỉ giữ nếu những nhóm truy vấn thực tế cần và lợi ích đã được đo.

## 36. Expression index cho một JSON path thường tìm

Nếu ứng dụng chủ yếu lọc theo theme, có thể không cần GIN trên toàn JSONB. Cân nhắc B-tree expression index:

~~~sql
CREATE INDEX idx_customer_profiles_theme
ON json_edit_lab.customer_profiles (
    (doc #>> '{settings,theme}')
);
~~~

Query phù hợp:

~~~sql
SELECT profile_id
FROM json_edit_lab.customer_profiles
WHERE doc #>> '{settings,theme}' = 'dark';
~~~

### Lợi ích

- Index theo **một giá trị scalar** thường được truy vấn.
- Có thể nhỏ hơn GIN trên toàn tài liệu.
- Dễ kết hợp trong composite index hoặc partial index khi workload phù hợp.

### Đánh đổi

- `UPDATE doc` vẫn có thể làm cột nguồn của expression index thay đổi theo cơ chế bảo trì index.
- Nếu query không dùng cùng biểu thức/kiểu so sánh phù hợp, planner có thể không dùng index.
- Text comparison/collation có thể ảnh hưởng kế hoạch và thứ tự.
- Một field theme chỉ có hai giá trị, tỷ lệ 50/50 có thể không đủ chọn lọc để index hữu ích.

Đừng tạo expression index chỉ vì path được truy cập trong SELECT. Hãy đo selectivity, frequency và write overhead.

## 37. Lưu JSONB hay cột quan hệ?

Một bảng profile có thể chứa:

~~~text
profile_id
email
doc: {
    "name": ...,
    "theme": ...,
    "tags": [...],
    "addresses": [...],
    "history": [...]
}
~~~

Khi nào nên tách?

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Theme đổi rất thường xuyên | Cột `theme text` hoặc bảng settings nhỏ |
| Địa chỉ cần ID/FK/update riêng | Bảng `profile_addresses` |
| Tags là danh sách ngắn, hiếm sửa | JSONB array hoặc SQL `text[]` có thể đủ |
| History tăng vô hạn | Bảng event/history append-only |
| Metadata từ nhiều provider thay đổi schema | JSONB linh hoạt |
| Cần uniqueness cho từng phần tử bên trong array | Bảng quan hệ với UNIQUE constraint |
| Cần lọc theo một path hot | Expression index hoặc cột typed |
| Cần cập nhật rất nhiều phần tử độc lập | Chuẩn hóa theo hàng để giảm tranh chấp |

**JSONB là công cụ bổ sung cho relational schema, không phải lý do bỏ hết constraints và mô hình quan hệ.**

## 38. Tại sao một JSONB document rất lớn dễ thành “hot row”?

Giả sử bảng có một hàng:

~~~text
profile_id = 101
doc = { settings, tags, addresses, events, history, counters, ... }
~~~

Hai service cùng sửa:

- Service A thay `settings.theme`.
- Service B thêm `history[... ]`.

Dù hai service sửa **hai path khác nhau**, PostgreSQL vẫn thực hiện UPDATE **cùng một row**, nên phải phối hợp row-level locks.

Điều này có thể làm:

- Tăng lock waits.
- Giảm throughput update khi nhiều worker cùng sửa một hồ sơ.
- Tăng nguy cơ client dùng document cũ ghi đè thay đổi mới.
- Khi row lớn, tăng chi phí tạo JSONB mới và TOAST.
- Tăng thời gian transaction nắm khóa nếu cập nhật phức tạp.

### Tách hot counters/history

Nếu `metrics.visits` tăng rất thường xuyên, cân nhắc cột counter hoặc bảng counters tách biệt:

~~~sql
CREATE TABLE json_edit_lab.profile_counters (
    profile_id bigint PRIMARY KEY
        REFERENCES json_edit_lab.customer_profiles(profile_id),
    visits bigint NOT NULL DEFAULT 0
);
~~~

Cập nhật:

~~~sql
UPDATE json_edit_lab.profile_counters
SET visits = visits + 1
WHERE profile_id = 101;
~~~

Lợi ích không chỉ là “integer nhỏ hơn JSONB”, mà còn là **tách vùng tranh chấp, cấu trúc dữ liệu và vòng đời ghi** khỏi tài liệu profile lớn.

## 39. Cạnh tranh cập nhật: client đọc rồi ghi toàn bộ document

Tình huống dễ mất dữ liệu:

~~~text
Ban đầu:
  doc = {"settings":{"theme":"light"},"tags":["vip"]}

Client A đọc toàn bộ doc.
Client B đọc toàn bộ doc.

A sửa theme thành dark, gửi nguyên doc:
  {"settings":{"theme":"dark"},"tags":["vip"]}

B thêm tag priority trên bản cũ rồi gửi nguyên doc:
  {"settings":{"theme":"light"},"tags":["vip","priority"]}

Nếu B ghi sau A, theme của A có thể bị ghi đè về light.
~~~

Đây là mẫu **lost update ở tầng ứng dụng** khi xây lại tài liệu từ snapshot cũ và gửi:

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = $1::jsonb
WHERE profile_id = $2;
~~~

PostgreSQL có thể khóa và tuần tự hóa thao tác ghi cùng hàng, nhưng nó **không biết** bản document do client B gửi đã được tạo từ snapshot cũ và bỏ quên theme mới của A.

### Cách tránh

1. Gửi **chỉ thay đổi path** và tính giá trị mới trong SQL với `jsonb_set(doc,...)` khi semantics phù hợp.
2. Dùng **optimistic locking** bằng cột version, kiểm tra version cũ trong `WHERE`.
3. Khóa hàng `SELECT ... FOR UPDATE` khi nghiệp vụ cần đọc–quyết định–ghi trong cùng transaction.
4. Thiết kế API PATCH phân biệt key không gửi, key gửi null, key muốn xóa.
5. Tách dữ liệu sửa độc lập thành các row quan hệ khác nhau khi cần concurrency cao.

## 40. Hai transaction cùng sửa hai path bằng jsonb_set

Với `READ COMMITTED` và một câu SQL UPDATE trực tiếp trên mỗi transaction:

**Phiên A:**

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id = 101;

-- Giữ transaction A chưa commit.
~~~

**Phiên B:**

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,notifications,sms}',
    'true'::jsonb,
    false
)
WHERE profile_id = 101;

-- B có thể phải chờ A vì cùng row.
~~~

**Phiên A:**

~~~sql
COMMIT;
~~~

Sau khi A commit, ở `READ COMMITTED`, PostgreSQL thường tiếp tục xử lý UPDATE của B trên phiên bản hàng hiện hành khi điều kiện còn phù hợp. Vì B tính `jsonb_set` **từ cột `doc` trong SQL**, hai sửa đổi ở **hai path khác nhau** có thể được giữ cùng nhau.

**Phiên B:**

~~~sql
COMMIT;
~~~

Sau đó:

~~~sql
SELECT
    doc #>> '{settings,theme}' AS theme,
    doc #> '{settings,notifications,sms}' AS sms
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

Trong điều kiện lab, kết quả có thể là `theme='dark'` và `sms=true`.

### Giới hạn của kết luận

- Điều này **không** có nghĩa B không bao giờ chờ; hai UPDATE cùng hàng vẫn tranh row lock.
- Nếu hai transaction sửa **cùng path**, giá trị được commit sau có thể thắng theo thứ tự thực thi/logic ứng dụng.
- Ở `REPEATABLE READ` hoặc `SERIALIZABLE`, một transaction có thể nhận `40001` thay vì tự xử lý lại như `READ COMMITTED`.
- Nếu ứng dụng đã xây nguyên `doc` từ bản cũ rồi gửi `SET doc = $full_document`, lỗi lost update vẫn có thể xảy ra.

**Khi làm lab hai phiên có COMMIT thật, hãy reset schema trước bài khác nếu cần seed ban đầu.**

## 41. Atomic increment bên trong JSONB

Hồ sơ 101 có:

~~~json
"metrics": {"visits": 4}
~~~

Một cách đếm sai trong ứng dụng:

~~~text
A: đọc visits = 4
B: đọc visits = 4
A: gửi visits = 5
B: gửi visits = 5
→ mất một lần tăng
~~~

Cách tính trong một câu UPDATE:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{metrics,visits}',
    to_jsonb(
        (doc #>> '{metrics,visits}')::bigint + 1
    ),
    false
)
WHERE profile_id = 101
RETURNING doc #>> '{metrics,visits}' AS visits;

ROLLBACK;
~~~

Trong lab, visits từ 4 thành 5.

### Khi nhiều transaction cùng tăng

Với một câu UPDATE tính trực tiếp từ giá trị hiện tại và những quy tắc khóa/đánh giá lại của `READ COMMITTED`, các lần tăng được serialize trên cùng row thay vì luôn dùng giá trị client đọc từ trước.

Nhưng:

- Mỗi lần tăng vẫn cập nhật **toàn giá trị JSONB** về mặt logic.
- Nếu visits rất nóng, row contention tăng.
- Đường dẫn `metrics.visits` phải tồn tại và chứa số có thể cast sang bigint trong câu SQL trên.
- Nếu dữ liệu sai kiểu, cast có thể lỗi.

**Trong production có counter tăng hàng nghìn lần mỗi giây, cột/bảng quan hệ chuyên biệt thường tốt hơn việc sửa một JSONB document lớn cho mỗi increment.**

## 42. Optimistic locking bằng version

Cột `version` trong lab giúp phát hiện một client đang dùng dữ liệu cũ.

Client đọc:

~~~sql
SELECT
    profile_id,
    version,
    doc
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

Giả sử thấy `version = 0`. Khi PATCH:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = jsonb_set(
        doc,
        '{settings,theme}',
        '"dark"'::jsonb,
        false
    ),
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
  AND version = 0
RETURNING profile_id, version;

ROLLBACK;
~~~

Nếu không có hàng trong `RETURNING`, có thể:

- ID không tồn tại.
- Version đã thay đổi từ khi client đọc.
- Một điều kiện khác trong `WHERE` không còn khớp.

Ứng dụng phải đọc lại trạng thái hoặc trả conflict phù hợp, không tự khẳng định “UPDATE thành công” chỉ vì SQL không báo lỗi.

### Nếu hai client cùng version 0?

Một client thành công cập nhật thành version 1; client còn lại kiểm tra `WHERE version=0` và sau khi chờ/đánh giá lại có thể cập nhật **0 hàng**. Đó là cách phát hiện stale write để không ghi đè một tài liệu cũ lên thay đổi mới.

**Không được lấy version chỉ ở bên client rồi bỏ điều kiện version trong UPDATE.** Điều kiện phải nằm trong statement ghi có tính nguyên tử.

## 43. Khi nào dùng SELECT FOR UPDATE?

Nếu nghiệp vụ cần:

1. Đọc nhiều path.
2. Kiểm tra một bất biến.
3. Có thể gọi thêm những câu SQL khác trong cùng transaction.
4. Sửa tài liệu dựa vào dữ liệu vừa đọc.

có thể dùng:

~~~sql
BEGIN;

SELECT profile_id, doc, version
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101
FOR UPDATE;

-- Kiểm tra các điều kiện nghiệp vụ trên connection này.
-- Sau đó UPDATE trong CÙNG transaction.

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc, '{settings,theme}', '"dark"'::jsonb, false
)
WHERE profile_id = 101;

COMMIT;
~~~

`FOR UPDATE` giữ khóa hàng tới khi transaction kết thúc theo quy tắc PostgreSQL. Không tự nghĩ một `SELECT FOR UPDATE` chạy trong autocommit rồi đóng connection còn bảo vệ UPDATE được gửi ở transaction khác.

### Không nên giữ row lock khi gọi API mạng lâu

Ví dụ giữ khóa rồi gọi dịch vụ ngoài 30 giây có thể khiến các UPDATE khác cùng profile chờ rất lâu. Cần cân nhắc state machine, outbox/idempotency hoặc phân tách transaction nếu công việc ngoài database kéo dài.

## 44. PATCH API: vắng key, JSON null và yêu cầu xóa

Một API PATCH tốt cần phân biệt ít nhất ba trạng thái:

| Payload request | Ý nghĩa có thể chọn |
| --- | --- |
| Không gửi `nickname` | Giữ nguyên nickname |
| Gửi `"nickname": null` | Đặt giá trị JSON null |
| Gửi một lệnh xóa riêng | Xóa key khỏi JSON object |

Không có một quy tắc chung duy nhất cho mọi API. Ví dụ JSON Merge Patch (RFC 7396) có semantics dùng null để loại bỏ thành viên object; JSON Patch (RFC 6902) có operation `remove` riêng. Nếu API của bạn theo một chuẩn, hãy thực hiện đúng chuẩn đó.

### Tại sao không dùng COALESCE cho mọi PATCH?

Nếu làm:

~~~sql
doc = jsonb_set(
    doc,
    '{nickname}',
    COALESCE($1::jsonb, doc -> 'nickname'),
    true
)
~~~

bạn có thể vô tình đánh đồng **SQL NULL do không gửi** với **ý định đặt JSON null**, tùy cách ứng dụng bind parameter.

Tốt hơn là parse/validate request và gửi **operation có chủ ý**: replace, add, remove hoặc no-op.

## 45. Quan sát kích thước JSONB

Hàm `pg_column_size` cho biết kích thước lưu trữ của một giá trị theo cơ chế PostgreSQL:

~~~sql
SELECT
    profile_id,
    pg_column_size(doc) AS doc_storage_bytes,
    length(doc::text) AS json_text_characters
FROM json_edit_lab.customer_profiles
ORDER BY profile_id;
~~~

Hai số không giống nhau:

- `pg_column_size(doc)` liên quan biểu diễn lưu trữ của giá trị.
- `length(doc::text)` đếm ký tự của biểu diễn text được tạo ra.

Với JSONB lớn, cơ chế nén/TOAST và dữ liệu thực có thể làm số đo khác rất nhiều. Không dùng `length(doc::text)` làm số byte WAL hoặc số byte thực ghi vào disk cho mỗi UPDATE.

### Đo kích thước bảng và index

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size(
            'json_edit_lab.customer_profiles'::regclass
        )
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size(
            'json_edit_lab.customer_profiles'::regclass
        )
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size(
            'json_edit_lab.customer_profiles'::regclass
        )
    ) AS total_size;
~~~

`pg_total_relation_size` cho cái nhìn tổng thể hơn về storage, bao gồm các thành phần liên quan của bảng/index. Theo dõi **trước–sau cùng lượng DML** sẽ hữu ích hơn việc nhìn một con số tại một thời điểm rồi tự kết luận chi phí cập nhật.

## 46. Tạo dữ liệu nhiều hàng để quan sát đường truy cập

Bảng ba hồ sơ phù hợp học thao tác, nhưng quá nhỏ để benchmark index.

Trên **database lab riêng**, có thể tạo bảng phụ:

~~~sql
CREATE TABLE json_edit_lab.profile_bench (
    profile_id bigint PRIMARY KEY,
    doc jsonb NOT NULL
        CHECK (jsonb_typeof(doc) = 'object')
);

INSERT INTO json_edit_lab.profile_bench (
    profile_id, doc
)
SELECT
    g::bigint,
    jsonb_build_object(
        'name', 'Customer ' || g,
        'settings', jsonb_build_object(
            'theme', CASE
                WHEN g % 2 = 0 THEN 'dark'
                ELSE 'light'
            END,
            'language', 'vi'
        ),
        'tags', jsonb_build_array(
            CASE WHEN g % 10 = 0 THEN 'vip' ELSE 'regular' END
        ),
        'metrics', jsonb_build_object(
            'visits', g % 100
        ),
        'description', repeat(md5(g::text), 50)
    )
FROM generate_series(1, 30000) AS s(g);

ANALYZE json_edit_lab.profile_bench;
~~~

Seed này tạo 30.000 hàng và nhiều object/array để thử. Nhưng `repeat(md5(...),50)` có tính lặp và **có thể nén rất tốt**; đừng coi nó là dữ liệu 1,6 KB hoàn toàn khó nén hay đại diện cho một document production lớn trong TOAST.

Muốn benchmark TOAST thực tế, hãy tạo dữ liệu đại diện về **kích thước sau nén, số path, số phần tử, tần suất UPDATE** từ telemetry, và bảo đảm dữ liệu kiểm thử đã khử thông tin nhạy cảm.

## 47. Thí nghiệm cập nhật trước/sau GIN index

### 47.1. Baseline đọc

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT profile_id
FROM json_edit_lab.profile_bench
WHERE doc @> '{"tags":["vip"]}'::jsonb;
~~~

Với khoảng 10% hàng có tag vip, planner có thể chọn Seq Scan trên tập 30.000 hàng, tùy chi phí.

### 47.2. Tạo GIN index

~~~sql
CREATE INDEX idx_profile_bench_doc_gin
ON json_edit_lab.profile_bench
USING gin (doc);

ANALYZE json_edit_lab.profile_bench;
~~~

Đo lại cùng SELECT:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT profile_id
FROM json_edit_lab.profile_bench
WHERE doc @> '{"tags":["vip"]}'::jsonb;
~~~

### 47.3. Đo một UPDATE trong lab

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE json_edit_lab.profile_bench
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id BETWEEN 1001 AND 2000
  AND doc #>> '{settings,theme}' = 'light';

ROLLBACK;
~~~

Tùy chọn `WAL` trong `EXPLAIN` được hỗ trợ ở PostgreSQL 13+. `EXPLAIN ANALYZE UPDATE` **thực sự chạy DML**, dù sau đó rollback.

### Đọc kết quả đúng cách

- `Execution Time`: chi phí statement trong điều kiện đó.
- `Buffers`: shared hits/reads/dirtied/written theo plan và version.
- `WAL records/bytes`: thông tin WAL liên quan thực thi, khi được hỗ trợ.
- Số hàng UPDATE thực tế.
- Có index scan để tìm hàng hay dùng primary key range?
- Index GIN có giúp đọc nhưng tăng công việc ghi không?

**Không so một lần UPDATE trước index với một lần sau index trên dataset đã thay đổi trạng thái khác nhau**. Muốn đo A/B nghiêm túc, cần clone/reset dataset, kiểm soát cache, lượng hàng thực sự thay đổi và concurrency.

## 48. Quan sát HOT update, dead tuples và VACUUM

PostgreSQL cung cấp thống kê trên từng bảng:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'json_edit_lab'
ORDER BY relname;
~~~

Các bộ đếm và estimate có thể cập nhật trễ; đừng đọc ngay sau một câu UPDATE rồi mặc định mọi giá trị là ảnh chụp tức thì chính xác.

Nếu có số UPDATE trong khoảng đo:

\[
\mathrm{HOT\ ratio} =
\frac{\Delta \mathrm{n\_tup\_hot\_upd}}
{\Delta \mathrm{n\_tup\_upd}}
\]

Chỉ tính khi mẫu số lớn hơn 0. Dùng **delta trong khoảng benchmark**, không dùng tổng số liệu từ rất lâu trước đó để quy kết tác động của đúng một index mới.

### VACUUM có vai trò gì?

UPDATE tạo phiên bản hàng cũ có thể trở thành dead tuple khi không còn snapshot cần tới. VACUUM giúp dọn các phiên bản đủ điều kiện và bảo trì index/visibility map/freeze theo cơ chế PostgreSQL.

Đừng dùng `VACUUM FULL` như một bước bắt buộc sau mọi JSONB UPDATE. Nó là thao tác rebuild có tác động khóa và vận hành lớn, khác với autovacuum/VACUUM thường.

## 49. Đo throughput cập nhật JSONB dưới concurrency

Một microbenchmark đơn lẻ:

~~~sql
EXPLAIN (ANALYZE)
UPDATE ...
~~~

không thể hiện đầy đủ:

- Nhiều worker cùng sửa một profile.
- Row lock waits.
- Commit/WAL flush latency.
- Thay đổi TOAST/index theo thời gian.
- Cache eviction.
- Autovacuum và dead tuple buildup.
- Replica lag trong workload ghi dài.
- p95/p99 của application request.

Một benchmark tốt cần:

1. Dataset đủ lớn và có phân bố thực.
2. Workload đọc/ghi đúng tỷ trọng.
3. Cùng số clients và prepared statement strategy.
4. Cùng số hàng update, cùng kích thước tài liệu.
5. Transaction commit trên database disposable để đo vòng đời thật.
6. Quan sát TPS, p50/p95/p99, errors, lock waits.
7. WAL và storage growth, không chỉ latency SQL.
8. Mức độ hot-row contention giống production.

**Không gọi một lần UPDATE 3 ms là đủ để hệ thống chịu được 1.000 update/s trên cùng profile.**

## 50. GIN và query không phải một chiếc “index miễn phí”

Đo index được dùng bằng:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'json_edit_lab'
ORDER BY relname, indexrelname;
~~~

Và đo size:

~~~sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_index AS x
    ON x.indrelid = t.oid
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'json_edit_lab'
  AND t.relname = 'profile_bench'
ORDER BY pg_relation_size(i.oid) DESC;
~~~

Khi đánh giá GIN index:

- Query containment có thật sự thường chạy không?
- Tỷ lệ document khớp bao nhiêu?
- Dữ liệu có nhiều phần tử/key tới mức index rất lớn không?
- Cột doc có được UPDATE thường xuyên không?
- Index có ảnh hưởng HOT và write throughput không?
- Có thể thay bằng expression B-tree index trên một path cụ thể không?

Index ít scan **không tự chứng minh vô dụng** nếu phục vụ một query hiếm nhưng quan trọng; nhưng index không đem lợi ích đáng kể có thể trở thành chi phí ghi hằng ngày.

## 51. Tối ưu dữ liệu JSONB bằng thiết kế nhỏ gọn

Những cách giảm chi phí có thể cân nhắc:

1. **Đừng nhét log/history tăng vô hạn** vào một JSONB field của hàng thường cập nhật.
2. **Tách hot fields** như counter, status, theme ra khỏi tài liệu rất lớn nếu update rate cao.
3. **Chỉ index những query cần thiết**; tránh GIN toàn tài liệu khi expression index nhỏ đủ đáp ứng.
4. **Đừng UPDATE khi không cần thiết**: kiểm tra khác biệt giá trị nếu workload có nhiều request idempotent.
5. **Giữ transaction ngắn**, tránh giữ row lock khi gọi mạng.
6. **Định nghĩa PATCH operations rõ**: add, replace, remove, no-op, set-json-null.
7. **Dùng optimistic version** khi client đọc rồi gửi cập nhật nhiều field.
8. **Không phụ thuộc array index như identity** của object thường được chèn/xóa/sắp xếp.
9. **Dùng constraints/validation** để tránh JSON sai kiểu làm query lỗi.
10. **Đo TOAST, HOT, WAL, VACUUM và lock waits** trước khi kết luận hàm JSONB nào tốt.

### UPDATE chỉ khi giá trị khác

Ví dụ để tránh UPDATE một theme đã là dark:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id = 101
  AND doc #>> '{settings,theme}' IS DISTINCT FROM 'dark'
RETURNING profile_id;

ROLLBACK;
~~~

Với seed, hồ sơ 101 đang là light nên được cập nhật. Nếu đã dark thì statement có thể trả 0 hàng.

**Lưu ý:** `IS DISTINCT FROM` tránh vấn đề SQL NULL trong phép so sánh, nhưng nếu path thiếu, `jsonb_set` với path trung gian thiếu có thể không thêm gì. Khi schema cho phép missing parent, nên thêm logic tạo parent hoặc validation riêng.

## 52. Tối ưu không có nghĩa bỏ hết JSONB

JSONB phù hợp khi:

- Metadata thay đổi theo loại đối tượng.
- Các field không phải lúc nào cũng có.
- Tỷ lệ sửa từng document thấp.
- Cần tìm một số điều kiện containment linh hoạt.
- Không có FK/unique phức tạp cho từng phần tử.
- Tài liệu có kích thước hợp lý.
- Có schema validation ở nơi phù hợp.

JSONB kém phù hợp hơn khi:

- Một document thường xuyên được hàng trăm worker sửa.
- History/mảng tăng không giới hạn.
- Mỗi object trong array cần identity/permission/FK riêng.
- Phải UPDATE các field scalar nóng nhiều lần mỗi giây.
- Cần unique constraint bên trong nhiều phần tử giữa nhiều hàng.
- Một phần nhỏ thay đổi làm toàn tài liệu rất lớn phải được xử lý lại.

Đừng đưa ra quyết định bằng định kiến “JSONB chậm” hay “JSONB linh hoạt nên tốt hơn SQL”. **Mô hình tốt dựa trên query, write patterns và dữ liệu thật.**

## 53. Những lỗi thường gặp

### 53.1. Nhầm json với jsonb

`jsonb_set` làm việc với JSONB. Dữ liệu `json` có thể cần cast và không giữ nguyên biểu diễn văn bản khi chuyển đổi.

### 53.2. Nghĩ || là deep merge

Object ở key `settings` có thể bị ghi đè toàn bộ, làm mất nhánh `notifications`.

### 53.3. Quên jsonb_set trả giá trị mới

`SELECT jsonb_set(...)` không tự UPDATE cột lưu trữ.

### 53.4. Truyền 'dark'::jsonb thay vì '"dark"'::jsonb

`dark` trần không phải JSON string hợp lệ; dùng `to_jsonb($1::text)` hoặc JSON string literal đúng cú pháp.

### 53.5. Nghĩ create_if_missing tạo mọi ancestor

Các bước trung gian phải tồn tại theo quy tắc `jsonb_set`.

### 53.6. Không kiểm tra kiểu array trước jsonb_array_elements

Nếu path chứa object/null/string, hàm mở array có thể báo lỗi.

### 53.7. Dùng jsonb_set khi muốn chèn trước phần tử

`jsonb_set` thay giá trị; `jsonb_insert` chèn theo vị trí.

### 53.8. Nhầm index 0 của JSON array với SQL array 1

Các cấu trúc có quy ước subscripting khác nhau.

### 53.9. Xóa key bằng cách đặt JSON null

`- 'nickname'` làm key biến mất; `jsonb_set(...,'null'::jsonb)` vẫn giữ key.

### 53.10. Không phân biệt SQL NULL với JSON null

`->>` có thể trả SQL NULL khi path thiếu hoặc khi JSON value là null; cần dùng `?`/`jsonb_typeof` nếu phân biệt.

### 53.11. Dùng toán tử - text trên object nhưng nghĩ xóa tag trong nested array

Phải lấy array ở path, sửa nó rồi gắn lại, hoặc dùng `#-` cho path.

### 53.12. Dùng vị trí array như khóa định danh của địa chỉ

Thêm/xóa đầu array làm phần tử phía sau đổi index.

### 53.13. jsonb_agg không ORDER BY khi cần giữ thứ tự

Sau khi mở array thành hàng và lọc, dùng `WITH ORDINALITY`/ORDER BY để tái tạo thứ tự.

### 53.14. Không COALESCE khi jsonb_agg trả SQL NULL

Nếu lọc hết phần tử, kết quả aggregate là NULL, không phải JSON array rỗng.

### 53.15. Ghi toàn bộ tài liệu từ dữ liệu client đọc cũ

Dễ làm mất thay đổi của request khác, dù PostgreSQL có row-level locks.

### 53.16. Nghĩ hai jsonb_set trên hai path không tranh lock

Chúng vẫn UPDATE cùng một row, nên có thể phải chờ nhau.

### 53.17. Retry chỉ một statement cuối sau serialization failure

Khi gặp `40001`, thông thường cần retry **toàn transaction** với dữ liệu đọc lại.

### 53.18. Nghĩ JSONB update là vá vài byte tại chỗ

PostgreSQL tạo JSONB result và row version mới; có chi phí MVCC/TOAST/index/WAL.

### 53.19. Nghĩ mọi UPDATE JSONB đều HOT

HOT phụ thuộc index và không gian trên heap page; GIN index trên doc có thể giảm cơ hội HOT.

### 53.20. Tạo GIN cho mọi doc mà không đo write throughput

GIN giúp một số query đọc nhưng có thể tăng đáng kể index maintenance.

### 53.21. Không đo tài liệu lớn/TOAST

Kết luận từ object vài chục byte có thể không áp dụng cho document hàng trăm KB.

### 53.22. Benchmark trên ba dòng rồi kết luận index chậm

Planner có thể chọn Seq Scan vì bảng rất nhỏ; cần workload đại diện.

### 53.23. Chỉ đo SELECT, bỏ INSERT/UPDATE/DELETE

Một index có thể tăng tốc lọc JSON nhưng làm workload ghi tốn WAL/CPU hơn.

### 53.24. Dùng EXPLAIN ANALYZE UPDATE như dry-run

`ANALYZE` **thực thi DML**; nên dùng database lab/transaction bảo vệ phù hợp.

### 53.25. Không đặt constraints/validation trên JSON

Dữ liệu không đúng kiểu gây lỗi ở các hàm path/array và sai nghĩa nghiệp vụ.

### 53.26. Không thống nhất semantics PATCH với API

Missing key, JSON null và yêu cầu remove có thể bị trộn thành một hành động gây mất dữ liệu.

## 54. Bài tập thực hành có đáp án

Dùng seed trong schema `json_edit_lab` từ mục 4. Các bài có DML nên được đặt trong `BEGIN ... ROLLBACK` khi chỉ thử, tránh làm thay đổi dữ liệu của bài tiếp theo. Với bài bench, chỉ thao tác trên database lab riêng.

### Bài 1. json và jsonb khác nhau ở đâu?

**Đáp án:** `json` lưu văn bản đầu vào; `jsonb` lưu biểu diễn nhị phân đã phân tích, có nhiều toán tử/index và không giữ nguyên thứ tự/format key đầu vào. Với thao tác chỉnh sửa thành phần, `jsonb` thường thuận tiện hơn.

### Bài 2. Đọc theme từ object lồng nhau

~~~sql
SELECT doc #>> '{settings,theme}' AS theme
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

**Đáp án:** Kết quả `light` dưới dạng text.

### Bài 3. Đổi theme của hồ sơ 101

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc, '{settings,theme}', '"dark"'::jsonb, false
)
WHERE profile_id = 101
RETURNING doc #>> '{settings,theme}' AS theme;

ROLLBACK;
~~~

**Đáp án:** Trong transaction theme thành `dark`; rollback phục hồi `light`.

### Bài 4. Vì sao phép || này có thể làm mất dữ liệu?

~~~sql
SELECT
    '{"settings":{"theme":"light","notifications":{"email":true}}}'::jsonb
    ||
    '{"settings":{"theme":"dark"}}'::jsonb;
~~~

**Đáp án:** Vì `||` shallow merge ở top-level. Key `settings` bên phải thay toàn bộ object settings bên trái; nhánh notifications bị mất.

### Bài 5. Thêm language top-level

~~~sql
SELECT
    '{"name":"Lan"}'::jsonb
    || jsonb_build_object('language', 'vi');
~~~

**Đáp án:** Kết quả `{"name":"Lan","language":"vi"}` về mặt nội dung.

### Bài 6. Thêm push trong notifications

~~~sql
SELECT jsonb_set(
    '{"settings":{"notifications":{"email":true}}}'::jsonb,
    '{settings,notifications,push}',
    'true'::jsonb,
    true
);
~~~

**Đáp án:** Nhánh notifications có thêm `"push":true` mà vẫn giữ email.

### Bài 7. Tại sao thêm settings.theme cho hồ sơ 103 có thể không có tác dụng?

**Đáp án:** Hồ sơ 103 không có parent `settings`. `jsonb_set(...,'{settings,theme}',...,true)` không tự tạo toàn bộ các ancestor còn thiếu; phải tạo nhánh settings trước hoặc sử dụng logic xây nhánh.

### Bài 8. Xóa key nickname

~~~sql
SELECT
    '{"name":"Lan","nickname":null}'::jsonb - 'nickname';
~~~

**Đáp án:** `{"name":"Lan"}`. Key bị xóa, không còn tồn tại với giá trị null.

### Bài 9. Xóa sms lồng nhau

~~~sql
SELECT
    '{"settings":{"notifications":{"email":true,"sms":false}}}'::jsonb
    #- '{settings,notifications,sms}';
~~~

**Đáp án:** Notifications còn `{"email":true}`.

### Bài 10. Thay tag thứ hai

~~~sql
SELECT jsonb_set(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,1}',
    '"priority"'::jsonb,
    false
);
~~~

**Đáp án:** `{"tags":["vip","priority"]}`.

### Bài 11. Chèn tag trước index 1

~~~sql
SELECT jsonb_insert(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,1}',
    '"priority"'::jsonb,
    false
);
~~~

**Đáp án:** `{"tags":["vip","priority","email"]}`. Khác với replace ở bài 10.

### Bài 12. Nối một tag mới vào cuối array

~~~sql
SELECT
    '["vip","email"]'::jsonb
    || jsonb_build_array('priority');
~~~

**Đáp án:** `["vip","email","priority"]`.

### Bài 13. Xóa tất cả phần tử string "vip"

~~~sql
SELECT
    '["vip","email","vip","priority"]'::jsonb
    - 'vip';
~~~

**Đáp án:** `["email","priority"]`.

### Bài 14. Xóa phần tử địa chỉ đầu tiên

~~~sql
SELECT
    '{"addresses":[{"city":"Ha Noi"},{"city":"Da Nang"}]}'::jsonb
    #- '{addresses,0}';
~~~

**Đáp án:** Chỉ còn object địa chỉ Da Nang ở phần tử đầu.

### Bài 15. Thay city của object đầu tiên

~~~sql
SELECT jsonb_set(
    '{"addresses":[{"city":"Ha Noi"}]}'::jsonb,
    '{addresses,0,city}',
    to_jsonb('Hai Phong'::text),
    false
);
~~~

**Đáp án:** `{"addresses":[{"city":"Hai Phong"}]}`.

### Bài 16. JSON null và key thiếu có giống không?

**Đáp án:** Không. `{"nickname":null}` có key; `{}` không có. `?` và `jsonb_typeof` giúp phân biệt, còn `->>` có thể trả SQL NULL cho cả hai.

### Bài 17. Đặt nickname thành JSON null

~~~sql
SELECT jsonb_set(
    '{"name":"Minh"}'::jsonb,
    '{nickname}',
    'null'::jsonb,
    true
);
~~~

**Đáp án:** `{"name":"Minh","nickname":null}`. Key vẫn tồn tại.

### Bài 18. Dùng jsonb_set_lax với delete_key

~~~sql
SELECT jsonb_set_lax(
    '{"name":"Lan","nickname":"Lannie"}'::jsonb,
    '{nickname}',
    NULL::jsonb,
    true,
    'delete_key'
);
~~~

**Đáp án:** `{"name":"Lan"}`; việc xử lý SQL NULL được định nghĩa rõ bằng `delete_key`.

### Bài 19. Vì sao UPDATE 1 path của JSONB lớn có thể tốn?

**Đáp án:** `jsonb_set` tạo giá trị JSONB kết quả, `UPDATE` tạo row version mới theo MVCC, có thể phát sinh TOAST work, index maintenance, WAL và cleanup. Không phải vá vài byte tại chỗ.

### Bài 20. GIN index có tác động gì lên HOT?

**Đáp án:** Khi `doc` được GIN-index, UPDATE thay doc liên quan index, có thể giảm cơ hội HOT và tăng công việc ghi. Hiệu ứng cần đo theo workload và PostgreSQL version.

### Bài 21. Làm sao tránh stale client overwrite?

**Đáp án:** Cập nhật path trực tiếp bằng SQL khi thích hợp; hoặc dùng cột `version` và `WHERE version = expected_version`, tăng version bằng cùng UPDATE, kiểm tra số hàng trả về. Với nhiều thao tác liên quan, có thể dùng transaction/`FOR UPDATE`.

### Bài 22. Atomic increment JSONB

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{metrics,visits}',
    to_jsonb(
        (doc #>> '{metrics,visits}')::bigint + 1
    ),
    false
)
WHERE profile_id = 101
RETURNING doc #>> '{metrics,visits}' AS visits;

ROLLBACK;
~~~

**Đáp án:** Trong lab tăng từ 4 lên 5. Khi path có thể thiếu/sai kiểu, cần validate; với counter rất nóng, xem xét bảng/cột quan hệ.

### Bài 23. Vì sao jsonb_agg có thể đổi thứ tự array?

**Đáp án:** Tổng hợp sau `jsonb_array_elements` không bảo đảm thứ tự trừ khi chỉ định `ORDER BY` trong aggregate; có thể dùng `WITH ORDINALITY` để giữ vị trí ban đầu.

### Bài 24. Nếu lọc hết array elements, jsonb_agg trả gì?

**Đáp án:** Thường trả SQL NULL khi không có hàng đầu vào. Dùng `COALESCE(jsonb_agg(...),'[]'::jsonb)` nếu muốn JSON array rỗng.

### Bài 25. So sánh expression index và GIN

**Đáp án:** Expression B-tree phù hợp một path scalar cố định được truy vấn thường xuyên; GIN linh hoạt hơn cho containment/JSONB operators phù hợp. Cả hai có chi phí storage/UPDATE; lựa chọn theo workload và benchmark.

### Bài 26. SQL array và JSON array có cùng index bắt đầu không?

**Đáp án:** Không. SQL array PostgreSQL thường có lower bound 1; JSON array indexing thông thường bắt đầu từ 0.

### Bài 27. Vì sao EXPLAIN ANALYZE UPDATE cần thận trọng?

**Đáp án:** Vì nó **thực thi UPDATE thật**. Dùng database lab hoặc transaction rollback để học; benchmark ghi nghiêm túc cần transaction commit trên dataset disposable.

### Bài 28. Khi nào tách mảng JSON thành bảng con?

**Đáp án:** Khi từng phần tử cần ID ổn định, FK/UNIQUE, truy vấn/cập nhật độc lập, có nhiều writer hoặc array tăng rất lớn. Bảng quan hệ giúp đặt constraints và giảm thao tác rewrite cả document cho mỗi phần tử.

## 55. Checklist áp dụng vào dự án thật

1. **Xác nhận kiểu cột** là `jsonb` và hình dạng document.
2. **Định nghĩa semantics PATCH**: add/replace/remove/no-op/set-json-null.
3. **Dùng bind parameters + to_jsonb/jsonb_build_object/jsonb_build_array**, tránh nối chuỗi JSON từ input.
4. **Đọc path trước khi sửa**, kiểm tra nested object/array type.
5. **Nhớ `||` là shallow merge**, không deep merge.
6. **Dùng `jsonb_set` cho sửa path**, hiểu `create_if_missing` chỉ áp cho phần tử cuối.
7. **Tạo parent rõ ràng** khi path trung gian có thể thiếu.
8. **Dùng `jsonb_insert` khi muốn chèn array element**, không dùng jsonb_set thay cho insert.
9. **Dùng `-` và `#-` cho xóa key/path**; phân biệt với JSON null.
10. **Khi rebuild array, giữ thứ tự** bằng `WITH ORDINALITY`/`ORDER BY` và xử lý aggregate rỗng.
11. **Không dựa array index như business identity** của object thường chèn/xóa.
12. **Validate nested schema** bằng constraint/ứng dụng như yêu cầu.
13. **Không gửi lại toàn bộ document cũ từ client** nếu không có concurrency control.
14. **Dùng SQL atomic update hoặc optimistic version** khi nhiều writer.
15. **Giữ transaction ngắn** và xử lý retry SQLSTATE phù hợp.
16. **Đo tài liệu lớn/TOAST trên dữ liệu đại diện**, không suy từ object vài chục byte.
17. **Hiểu UPDATE tạo row version mới theo MVCC**, không phải vá vài byte tại chỗ.
18. **Đo HOT ratio, WAL, dead tuples, index size và update TPS** khi thêm GIN/expression index.
19. **Xem xét tách hot fields/counters/history** ra khỏi JSONB doc lớn.
20. **Giám sát lock waits** nếu nhiều worker sửa cùng một profile.
21. **Kiểm tra kế hoạch EXPLAIN** cho query thực, không ép dùng GIN vì tên index nghe phù hợp.
22. **Đo cả SELECT và INSERT/UPDATE** trước/sau tạo index.
23. **Không benchmark ghi nặng trên production**, dùng staging/database disposable.
24. **Chỉ kết luận trên workload có phân bố thực**, tham số và concurrency gần ứng dụng.
25. **Giữ khả năng rollback** khi thay schema/index/API PATCH semantics.

## 56. Tài liệu PostgreSQL chính thức

Để xác minh cú pháp và hành vi theo **major version PostgreSQL thực tế**, tham khảo:

- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html) — `json` và `jsonb`, lưu trữ và khác biệt biểu diễn.
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html) — `jsonb_set`, `jsonb_insert`, `jsonb_set_lax`, `||`, `-`, `#-`, subscripting và JSONPath.
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html) — SQL arrays, `array_append`, `array_remove` và sự khác biệt với JSON arrays.
- [JSONB Indexing](https://www.postgresql.org/docs/current/datatype-json.html#JSON-INDEXING) — GIN operator classes, containment và expression indexes.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html) — index theo JSON path scalar.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — B-tree, GIN và các loại khác.
- [Heap-Only Tuple Updates](https://www.postgresql.org/docs/current/storage-hot.html) — điều kiện HOT và ảnh hưởng index.
- [TOAST](https://www.postgresql.org/docs/current/storage-toast.html) — lưu trữ giá trị lớn, nén và out-of-line.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html) — row versions/snapshot.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — SET/WHERE/RETURNING và transaction semantics.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — READ COMMITTED, REPEATABLE READ, SERIALIZABLE.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row-level lock và concurrency.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — phân tích scans, buffers, costs.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — ANALYZE/BUFFERS/WAL.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_user_tables`/`pg_stat_user_indexes` và các bộ đếm.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples và autovacuum.

Đường dẫn `/current/` chỉ tới tài liệu PostgreSQL hiện hành trên website. Khi sử dụng các cú pháp có sự khác biệt theo major version như JSONB subscripting hoặc một số lựa chọn `EXPLAIN`, hãy đối chiếu tài liệu phiên bản server đang chạy.

## 57. Tổng kết

**PostgreSQL cho phép thêm, sửa và xóa thành phần JSONB rất linh hoạt**, nhưng phải phân biệt **đúng nghĩa logic của thao tác** với **chi phí cập nhật vật lý**.

Những nguyên tắc cốt lõi:

1. **`jsonb_set` sửa hoặc thêm giá trị tại một path**; các nhánh trung gian thường phải tồn tại. Đừng kỳ vọng `create_if_missing` tự tạo mọi ancestor.
2. **`||` là shallow merge đối với object**; có thể làm mất object lồng nhau nếu dùng thay deep merge. Với array, `||` có thể nối các phần tử theo quy tắc JSONB.
3. **`jsonb_insert` chèn vào array**, còn `jsonb_set` thay phần tử hiện có. `-` và `#-` xóa key hoặc phần tử theo path.
4. **JSON null, SQL NULL và key không tồn tại khác nhau**. API PATCH phải định nghĩa rõ đặt null, bỏ key và không thay đổi.
5. **JSON arrays có index từ 0 và thay đổi thứ tự khi chèn/xóa**. Nếu phần tử cần identity, đừng lấy vị trí làm khóa nghiệp vụ.
6. **UPDATE JSONB không phải vá vài byte tại chỗ**. MVCC tạo row version mới và có thể cần TOAST, WAL, index maintenance, VACUUM.
7. **GIN/expression index có thể giúp truy vấn JSONB nhưng làm ghi tốn thêm** và ảnh hưởng HOT. Phải đo với dữ liệu lớn và workload đọc–ghi thực.
8. **Nhiều transaction sửa cùng JSON document vẫn tranh cùng row**. Dùng SQL atomic update, version check hoặc khóa trong transaction phù hợp để tránh stale client overwrite.
9. **Tách dữ liệu thành cột/bảng quan hệ** khi field hoặc phần tử cập nhật thường xuyên, cần FK/UNIQUE/ID ổn định hoặc làm cả JSONB document quá lớn.

Khi chọn đúng hàm JSONB, mô hình dữ liệu và chiến lược concurrency, bạn có thể cập nhật từng phần của tài liệu một cách **đúng nghĩa nghiệp vụ**, đồng thời hiểu và kiểm soát được **chi phí lưu trữ, WAL, khóa và bảo trì phát sinh phía PostgreSQL**.
