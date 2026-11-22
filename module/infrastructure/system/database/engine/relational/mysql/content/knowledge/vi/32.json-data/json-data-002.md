# JSON object, array, scalar và khác biệt JSON null/SQL NULL

MySQL hỗ trợ lưu trữ và xử lý dữ liệu JSON bằng kiểu cột `JSON` cùng các hàm dựng, kiểm tra, trích xuất và sửa tài liệu JSON. Trước khi truy vấn JSON, cần hiểu cấu trúc của một JSON document: **object**, **array** và **scalar**. Cũng cần phân biệt rõ JSON literal `null`, SQL `NULL` và trường hợp một JSON path không tồn tại. Ba trường hợp này có ý nghĩa khác nhau và ảnh hưởng trực tiếp đến điều kiện lọc, cập nhật dữ liệu và logic ứng dụng.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **JSON**, bài này tập trung vào JSON object, array, scalar và khác biệt giữa JSON `null` với SQL `NULL`. `SPECIAL_NOTE` được cung cấp rỗng, vì vậy không có ràng buộc riêng bổ sung cho bài.

## 1. JSON document gồm những kiểu giá trị nào?

JSON định nghĩa sáu kiểu giá trị cơ bản:

| Kiểu | Ví dụ JSON | Ý nghĩa |
|---|---|---|
| Object | `{"id": 10, "name": "Lan"}` | Tập hợp các cặp key/value, key là chuỗi. |
| Array | `["red", "green", "blue"]` | Danh sách giá trị có thứ tự. |
| String | `"MySQL"` | Chuỗi ký tự, luôn đặt trong dấu ngoặc kép JSON. |
| Number | `42`, `19.95`, `-3` | Giá trị số, không đặt trong dấu ngoặc kép. |
| Boolean | `true`, `false` | Giá trị logic JSON, viết thường. |
| Null | `null` | Giá trị rỗng theo mô hình dữ liệu JSON. |

Object và array là hai cấu trúc container; string, number, boolean và null là các scalar. Một document có thể chứa các container lồng nhau và các scalar ở bất kỳ vị trí hợp lệ nào.

Ví dụ một document kết hợp nhiều kiểu:

```json
{
  "customerId": 1001,
  "name": "Lan Nguyen",
  "active": true,
  "nickname": null,
  "tags": ["premium", "newsletter"],
  "address": {
    "city": "Da Nang",
    "postalCode": "550000"
  }
}
```

Giá trị gốc của document này là object. Bên trong object có number, string, boolean, JSON null, array và một object lồng nhau.

## 2. JSON object

Object là tập hợp các cặp key/value đặt trong `{}`. Key phải là string JSON và được ngăn cách với value bằng dấu hai chấm `:`. Các cặp được phân cách bằng dấu phẩy:

```json
{
  "productId": 501,
  "productName": "Mechanical Keyboard",
  "price": 1250000,
  "inStock": true
}
```

Các quy tắc cần nhớ:

- Key là chuỗi và phải đặt trong dấu ngoặc kép kép `"` theo cú pháp JSON.
- Value có thể là object, array hoặc bất kỳ scalar JSON nào.
- Key/value được phân cách bằng `:`, các cặp phân cách bằng `,`.
- Không dùng dấu phẩy thừa sau phần tử cuối.
- JSON phân biệt chữ hoa/chữ thường trong tên key; `name` và `Name` là hai key khác nhau.
- Thứ tự các key trong object không mang ý nghĩa như thứ tự phần tử array. Không viết logic phụ thuộc vào thứ tự key sau khi MySQL lưu và chuẩn hóa document.

Tên key trùng lặp nên được tránh vì gây khó hiểu cho ứng dụng. Khi MySQL chuẩn hóa JSON object có key trùng, giá trị xuất hiện sau cùng được giữ lại trong document đã chuẩn hóa.

Ví dụ không nên dùng:

```json
{
  "status": "NEW",
  "status": "PAID"
}
```

Hãy bảo đảm mỗi key chỉ xuất hiện một lần trong object được ứng dụng gửi tới database.

## 3. JSON array

Array là danh sách giá trị có thứ tự, đặt trong `[]`. Mỗi phần tử có thể thuộc bất kỳ kiểu JSON nào:

```json
[
  "mysql",
  8,
  true,
  null,
  {"topic": "index"}
]
```

Array dùng chỉ số bắt đầu từ 0 trong JSON path:

| Phần tử | JSON path |
|---|---|
| Phần tử đầu tiên | `$[0]` |
| Phần tử thứ hai | `$[1]` |
| Phần tử thứ ba | `$[2]` |

Ví dụ array lồng nhau:

```json
{
  "orderId": 9001,
  "items": [
    {"sku": "KB-200", "quantity": 1},
    {"sku": "MS-100", "quantity": 2}
  ]
}
```

`items` là array gồm hai object. Phần tử đầu tiên có path `$.items[0]`; thuộc tính SKU của phần tử đầu tiên có path `$.items[0].sku`.

Thứ tự phần tử array là có ý nghĩa. Nếu cần giữ thứ tự hiển thị hoặc thứ tự ưu tiên, array phù hợp hơn object.

## 4. JSON scalar

Scalar là một giá trị đơn, không chứa key/value hay danh sách con. Bốn kiểu scalar của JSON là string, number, boolean và null.

### 4.1. String

String JSON luôn nằm trong dấu ngoặc kép kép:

```json
"MySQL"
```

Chuỗi rỗng `""` khác JSON null và khác SQL NULL. Chuỗi `"null"` cũng là một string gồm bốn ký tự, không phải JSON null.

### 4.2. Number

Number không được đặt trong dấu ngoặc kép:

```json
125
19.95
-3
1.25e3
```

`"125"` là string, còn `125` là number. Không nên lưu số cần tính toán dưới dạng chuỗi nếu ứng dụng mong muốn xử lý nó như giá trị số.

### 4.3. Boolean

JSON chỉ có hai literal boolean viết thường:

```json
true
false
```

`"true"` là string; `TRUE` không phải cách viết literal boolean hợp lệ trong JSON.

### 4.4. Null

JSON null là literal viết thường:

```json
null
```

JSON null biểu thị một giá trị null nằm bên trong tài liệu JSON. Nó không đồng nghĩa với SQL NULL của cột trong bảng.

## 5. Object, array và scalar ở vị trí gốc

Một JSON document hợp lệ có thể có object, array hoặc scalar làm giá trị gốc:

```json
{"kind": "object"}
```

```json
["mysql", "json"]
```

```json
"a scalar string"
```

```json
123
```

```json
true
```

```json
null
```

Không phải mọi document đều phải bắt đầu bằng `{`. Nếu ứng dụng cần metadata có nhiều thuộc tính, object thường là lựa chọn thuận tiện. Nếu dữ liệu chỉ là danh sách, array có thể phù hợp. Scalar ở gốc hợp lệ nhưng cần thống nhất hợp đồng dữ liệu để mọi client biết kiểu gốc mong đợi.

## 6. JSON text và JSON string là hai khái niệm khác nhau

JSON text là biểu diễn văn bản của một JSON value. Bản thân JSON value có thể là string. Vì vậy, JSON string ở gốc phải có dấu ngoặc kép bên trong JSON text:

```sql
-- JSON document là một object.
SELECT JSON_TYPE('{"name": "Lan"}');

-- JSON document là một scalar string.
SELECT JSON_TYPE('"Lan"');

-- JSON document là một scalar number.
SELECT JSON_TYPE('42');
```

Trong câu SQL, literal được bao bằng dấu nháy đơn của SQL; dấu ngoặc kép bên trong là cú pháp JSON. Đừng nhầm chuỗi SQL `'Lan'` (không phải JSON text hợp lệ nếu dùng trực tiếp làm document) với JSON text `'"Lan"'`.

## 7. Kiểu dữ liệu JSON native của MySQL

MySQL cung cấp kiểu cột `JSON`. Khi ghi một giá trị vào cột JSON, MySQL kiểm tra văn bản đầu vào có phải JSON hợp lệ hay không. Giá trị được lưu dưới định dạng nội bộ dạng nhị phân để server có thể truy cập các phần tử mà không cần phân tích lại toàn bộ văn bản ở mỗi lần đọc.

Ví dụ tạo bảng:

```sql
CREATE TABLE customer_profiles (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    profile JSON NOT NULL
) ENGINE = InnoDB;
```

Chèn object:

```sql
INSERT INTO customer_profiles (customer_id, profile)
VALUES (
    1001,
    '{"name": "Lan Nguyen", "active": true, "tags": ["vip", "email"]}'
);
```

Chèn bằng hàm dựng JSON:

```sql
INSERT INTO customer_profiles (customer_id, profile)
VALUES (
    1002,
    JSON_OBJECT(
        'name', 'Minh Tran',
        'active', CAST('true' AS JSON),
        'tags', JSON_ARRAY('new', 'mobile')
    )
);
```

Hàm `JSON_OBJECT()` tạo object; `JSON_ARRAY()` tạo array. Các hàm này giúp tạo JSON mà không phải tự ghép chuỗi và tự xử lý escape ký tự.

Lưu ý:

- Cột JSON chỉ nhận JSON hợp lệ hoặc SQL NULL nếu cột cho phép NULL.
- Chuỗi JSON sai cú pháp bị từ chối khi ghi vào cột JSON.
- MySQL chuẩn hóa cách biểu diễn JSON; không nên kỳ vọng văn bản được trả ra giữ nguyên khoảng trắng hoặc thứ tự key như đầu vào.
- JSON native không thay thế thiết kế quan hệ cho các thuộc tính cần khóa ngoại, constraint, join thường xuyên hoặc index B-tree trực tiếp.

## 8. Kiểm tra kiểu JSON bằng JSON_TYPE và JSON_VALID

`JSON_TYPE()` trả về kiểu của JSON value:

```sql
SELECT JSON_TYPE('{"name": "Lan"}') AS value_type;
SELECT JSON_TYPE('["mysql", "json"]') AS value_type;
SELECT JSON_TYPE('"MySQL"') AS value_type;
SELECT JSON_TYPE('42') AS value_type;
SELECT JSON_TYPE('true') AS value_type;
SELECT JSON_TYPE('null') AS value_type;
```

Các kết quả tương ứng là OBJECT, ARRAY, STRING, INTEGER, BOOLEAN và NULL. Ở đây chuỗi kết quả `'NULL'` (không phân biệt hoa thường khi so sánh chuỗi theo collation thích hợp) là tên kiểu JSON null, không phải SQL NULL.

`JSON_VALID()` kiểm tra một chuỗi có biểu diễn JSON hợp lệ hay không:

```sql
SELECT JSON_VALID('{"id": 10, "active": true}') AS valid_document;
SELECT JSON_VALID('{"id": 10,}') AS invalid_document;
SELECT JSON_VALID('"plain string"') AS valid_scalar;
SELECT JSON_VALID('plain string') AS invalid_text;
```

`JSON_VALID()` trả 1 nếu đối số là JSON hợp lệ, 0 nếu không hợp lệ; nếu đối số SQL là NULL, kết quả là SQL NULL. Hàm này hữu ích khi dữ liệu đang nằm trong cột TEXT hoặc khi kiểm tra input trước khi chuyển sang kiểu JSON.

Với cột JSON native, MySQL đã kiểm tra tính hợp lệ lúc ghi. Vì vậy, không cần gọi `JSON_VALID(profile)` ở mọi câu SELECT chỉ để xác nhận lại invariant của cột JSON.

## 9. JSON null và SQL NULL

Hai khái niệm có tên gần giống nhưng thuộc hai lớp khác nhau:

- **JSON null** là một giá trị JSON hợp lệ nằm trong document, ví dụ `{"nickname": null}`.
- **SQL NULL** là giá trị NULL của cột SQL, biểu thị cột không có giá trị theo ngữ nghĩa SQL.

Một cột JSON nullable có thể chứa cả một document JSON có giá trị gốc là null và SQL NULL:

```sql
CREATE TABLE json_null_demo (
    id INT NOT NULL PRIMARY KEY,
    payload JSON NULL
) ENGINE = InnoDB;

INSERT INTO json_null_demo (id, payload)
VALUES
    (1, 'null'),
    (2, NULL),
    (3, '{"nickname": null}'),
    (4, '{"name": "Lan"}');
```

Diễn giải:

| id | Giá trị payload | Ý nghĩa |
|---:|---|---|
| 1 | `null` | JSON document có giá trị gốc là JSON null. |
| 2 | SQL NULL | Cột SQL không có giá trị. |
| 3 | `{"nickname": null}` | Object tồn tại; thuộc tính nickname có JSON null. |
| 4 | `{"name": "Lan"}` | Object không có thuộc tính nickname. |

Do đó, không thể chỉ nhìn từ "null" trong output dạng văn bản rồi kết luận đó là SQL NULL. Cần kiểm tra bằng toán tử SQL và hàm JSON phù hợp.

## 10. Phân biệt SQL NULL, JSON null và path không tồn tại

Giả sử bảng `json_null_demo` ở trên:

| Trạng thái | `payload IS NULL` | `JSON_TYPE(payload)` | `JSON_CONTAINS_PATH(payload, 'one', '$.nickname')` |
|---|---:|---|---:|
| SQL NULL ở id 2 | 1 | SQL NULL | SQL NULL |
| JSON null ở gốc, id 1 | 0 | `NULL` (tên kiểu JSON) | 0 |
| Object có nickname:null, id 3 | 0 | OBJECT | 1 |
| Object không có nickname, id 4 | 0 | OBJECT | 0 |

Trường hợp object không có path và object có path chứa JSON null đều khác SQL NULL của cả cột. `JSON_CONTAINS_PATH()` giúp kiểm tra thuộc tính có tồn tại hay không, kể cả khi giá trị thuộc tính là JSON null.

Có thể kiểm tra riêng từng hàng:

```sql
SELECT
    id,
    payload IS NULL AS sql_null,
    JSON_TYPE(payload) AS root_json_type,
    JSON_CONTAINS_PATH(payload, 'one', '$.nickname') AS has_nickname,
    JSON_TYPE(JSON_EXTRACT(payload, '$.nickname')) AS nickname_json_type
FROM json_null_demo
ORDER BY id;
```

Lưu ý cách đọc:

- `payload IS NULL` kiểm tra SQL NULL ở cấp cột.
- `JSON_TYPE(payload)` cho biết kiểu JSON gốc nếu payload không phải SQL NULL.
- `JSON_CONTAINS_PATH(...)` kiểm tra path có tồn tại.
- `JSON_TYPE(JSON_EXTRACT(...))` cho biết kiểu của giá trị được trích xuất; nếu path không tồn tại hoặc đối số là SQL NULL, kết quả có thể là SQL NULL.

Đối với id 3, path tồn tại và kiểu giá trị trích xuất là JSON NULL. Đối với id 4, path không tồn tại và phép trích xuất trả SQL NULL. Muốn phân biệt chắc chắn hai trường hợp này, hãy kết hợp kiểm tra path tồn tại.

## 11. JSON path để truy cập object và array

JSON path trong MySQL bắt đầu bằng ký hiệu `$`, đại diện cho document gốc. Sau đó dùng cú pháp truy cập key hoặc chỉ số array:

| Cấu trúc | JSON path | Ý nghĩa |
|---|---|---|
| Key cấp đầu | `$.name` | Thuộc tính name ở object gốc. |
| Key lồng nhau | `$.address.city` | Thuộc tính city trong address. |
| Phần tử array | `$.items[0]` | Phần tử đầu tiên của items. |
| Thuộc tính trong array | `$.items[0].sku` | SKU của object đầu tiên trong items. |
| Key có dấu cách | `$."display name"` | Key có khoảng trắng. |
| Tất cả phần tử array | `$.items[*]` | Các phần tử của array items. |

Ví dụ trích xuất:

```sql
SELECT
    JSON_EXTRACT(
        '{"name": "Lan", "address": {"city": "Da Nang"}}',
        '$.address.city'
    ) AS city;

SELECT
    JSON_EXTRACT(
        '{"items": [{"sku": "KB-200"}, {"sku": "MS-100"}]}',
        '$.items[0].sku'
    ) AS first_sku;
```

`JSON_EXTRACT()` trả về JSON value. Nếu path không khớp với document, kết quả là SQL NULL. Nếu path khớp với một thuộc tính có giá trị JSON null, kết quả là JSON null. Đây là lý do cần kết hợp `JSON_CONTAINS_PATH()` khi cần biết thuộc tính có tồn tại hay không.

## 12. Hàm dựng JSON và xử lý scalar

### 12.1. JSON_OBJECT

`JSON_OBJECT(key, value, ...)` tạo object từ các cặp key/value:

```sql
SELECT JSON_OBJECT(
    'customerId', 1001,
    'name', 'Lan Nguyen',
    'active', CAST('true' AS JSON),
    'nickname', NULL
) AS customer_json;
```

Các giá trị SQL NULL được chuyển thành JSON null bên trong object. Mỗi key phải có value tương ứng; số đối số phải là một số chẵn và key không được là SQL NULL.

### 12.2. JSON_ARRAY

`JSON_ARRAY(value, ...)` tạo array; các giá trị được giữ theo thứ tự truyền vào:

```sql
SELECT JSON_ARRAY(
    'mysql',
    8,
    CAST('true' AS JSON),
    NULL,
    JSON_OBJECT('topic', 'json')
) AS values_json;
```

SQL NULL truyền vào JSON_ARRAY được biểu diễn thành phần tử JSON null, không làm toàn bộ array trở thành SQL NULL.

### 12.3. JSON_QUOTE và JSON_UNQUOTE

`JSON_QUOTE()` chuyển một chuỗi SQL thành JSON string text hợp lệ, bao gồm dấu ngoặc kép và escape ký tự đặc biệt:

```sql
SELECT JSON_QUOTE('A "quoted" value');
```

`JSON_UNQUOTE()` bỏ lớp dấu ngoặc kép JSON của một JSON string:

```sql
SELECT JSON_UNQUOTE('"MySQL"') AS plain_text;
```

Không dùng JSON_UNQUOTE để kiểm tra kiểu dữ liệu. Nếu cần biết một giá trị là string, number, boolean hay JSON null, hãy dùng `JSON_TYPE()`.

## 13. JSON_EXTRACT, toán tử -> và ->>

MySQL cung cấp `JSON_EXTRACT(document, path)` để lấy giá trị theo JSON path. Có thể dùng toán tử `->` như cách viết tắt khi truy cập một cột JSON:

```sql
SELECT
    profile->'$.name' AS name_json,
    JSON_EXTRACT(profile, '$.active') AS active_json
FROM customer_profiles;
```

`->` trả về giá trị JSON, nên string vẫn mang biểu diễn JSON có dấu ngoặc kép. Toán tử `->>` kết hợp trích xuất và unquote để trả giá trị dưới dạng chuỗi SQL:

```sql
SELECT
    profile->>'$.name' AS name_text
FROM customer_profiles;
```

Chọn cách dùng theo mục đích:

- Cần giữ kiểu JSON để truyền tiếp cho hàm JSON: dùng `JSON_EXTRACT()` hoặc `->`.
- Cần chuỗi đã bỏ dấu ngoặc kép JSON để hiển thị hoặc so sánh text: dùng `->>` hoặc `JSON_UNQUOTE(JSON_EXTRACT(...))`.
- Cần kiểm tra kiểu: dùng `JSON_TYPE()`.
- Cần kiểm tra path tồn tại kể cả khi giá trị là JSON null: dùng `JSON_CONTAINS_PATH()`.

Không mặc định rằng mọi giá trị trích xuất đều là string. Một path có thể trả object, array, number, boolean hoặc JSON null.

## 14. Viết điều kiện SQL với JSON null và SQL NULL

Không dùng phép so sánh = NULL hoặc <> NULL trong SQL. SQL NULL phải được kiểm tra bằng `IS NULL` hoặc `IS NOT NULL`:

```sql
SELECT *
FROM json_null_demo
WHERE payload IS NULL;

SELECT *
FROM json_null_demo
WHERE payload IS NOT NULL;
```

Để tìm document có giá trị gốc là JSON null, kiểm tra kiểu JSON:

```sql
SELECT *
FROM json_null_demo
WHERE payload IS NOT NULL
  AND JSON_TYPE(payload) = 'NULL';
```

Để tìm object có thuộc tính nickname và thuộc tính đó là JSON null:

```sql
SELECT *
FROM json_null_demo
WHERE JSON_CONTAINS_PATH(payload, 'one', '$.nickname') = 1
  AND JSON_TYPE(JSON_EXTRACT(payload, '$.nickname')) = 'NULL';
```

Để tìm object không có thuộc tính nickname:

```sql
SELECT *
FROM json_null_demo
WHERE payload IS NOT NULL
  AND JSON_TYPE(payload) = 'OBJECT'
  AND JSON_CONTAINS_PATH(payload, 'one', '$.nickname') = 0;
```

Thứ tự kiểm tra giúp tránh nhầm lẫn giữa SQL NULL và JSON null. Nếu dữ liệu có thể chứa nhiều kiểu root khác nhau, hãy kiểm tra kiểu root trước khi áp dụng path dành cho object.

## 15. CASE để phân loại các trạng thái

Có thể dùng CASE để đưa các trạng thái thành nhãn rõ ràng:

```sql
SELECT
    id,
    CASE
        WHEN payload IS NULL THEN 'SQL NULL'
        WHEN JSON_TYPE(payload) = 'NULL' THEN 'JSON null at root'
        WHEN JSON_CONTAINS_PATH(payload, 'one', '$.nickname') = 0
            THEN 'nickname missing'
        WHEN JSON_TYPE(JSON_EXTRACT(payload, '$.nickname')) = 'NULL'
            THEN 'nickname is JSON null'
        ELSE 'nickname has a value'
    END AS nickname_state
FROM json_null_demo
ORDER BY id;
```

CASE kiểm tra SQL NULL trước khi gọi hàm JSON để làm rõ ý nghĩa và tránh dựa vào kết quả của hàm trên SQL NULL. Với id 1, document gốc là JSON null nên không có nickname; id 2 là SQL NULL; id 3 có nickname với JSON null; id 4 thiếu nickname.

## 16. JSON null khác với xóa một thuộc tính

Trong object, hai trạng thái sau không giống nhau:

```json
{"nickname": null}
```

```json
{}
```

Document thứ nhất có key `nickname` với giá trị JSON null. Document thứ hai không có key đó. Sự khác biệt này quan trọng nếu API dùng việc thiếu key để biểu thị “không gửi thay đổi”, còn JSON null để biểu thị “xóa giá trị hiện tại” hoặc “giá trị chưa biết”.

MySQL có hàm `JSON_REMOVE()` để loại bỏ path:

```sql
SELECT JSON_REMOVE(
    '{"name": "Lan", "nickname": null}',
    '$.nickname'
) AS without_nickname;
```

Kết quả là object không còn key nickname. Trong khi đó, object có key với JSON null vẫn có thể được tạo bằng `JSON_SET()`:

```sql
SELECT JSON_SET(
    '{"name": "Lan"}',
    '$.nickname',
    CAST('null' AS JSON)
) AS nickname_set_to_json_null;
```

Khi cập nhật JSON từ ứng dụng, hãy thống nhất hợp đồng: key bị bỏ qua, key có JSON null và cột SQL NULL có ý nghĩa nghiệp vụ nào.

## 17. Lưu object, array và scalar trong cột JSON

Kiểu cột JSON có thể lưu nhiều loại JSON value, không chỉ object:

```sql
CREATE TABLE json_root_values (
    id INT NOT NULL PRIMARY KEY,
    document JSON NOT NULL
) ENGINE = InnoDB;

INSERT INTO json_root_values (id, document)
VALUES
    (1, '{"kind": "object"}'),
    (2, '["mysql", "json"]'),
    (3, '"scalar string"'),
    (4, '123'),
    (5, 'true'),
    (6, 'null');

SELECT
    id,
    JSON_TYPE(document) AS root_type,
    document
FROM json_root_values
ORDER BY id;
```

Kết quả kiểu gốc lần lượt là OBJECT, ARRAY, STRING, INTEGER, BOOLEAN và NULL. Với cột `document JSON NOT NULL`, hàng số 6 vẫn hợp lệ vì `'null'` là một JSON document có giá trị gốc là JSON null, không phải SQL NULL.

Nếu thử chèn SQL NULL vào cột `document NOT NULL`, MySQL từ chối vì vi phạm thuộc tính NOT NULL của cột:

```sql
INSERT INTO json_root_values (id, document)
VALUES (7, NULL);
```

Nếu cột được khai báo nullable, SQL NULL có thể được lưu riêng biệt với JSON null.

## 18. Kiểm tra JSON lỗi và các lỗi cú pháp phổ biến

JSON parser của MySQL kiểm tra cú pháp. Một số lỗi thường gặp:

| Input | Vấn đề |
|---|---|
| `{name: "Lan"}` | Key không đặt trong dấu ngoặc kép. |
| `{"name": "Lan",}` | Có dấu phẩy thừa ở cuối object. |
| `{"active": True}` | Boolean viết hoa, không đúng literal JSON. |
| `{'name': 'Lan'}` | JSON dùng dấu ngoặc kép kép cho string/key. |
| `[1, 2,]` | Có dấu phẩy thừa ở cuối array. |

Thử kiểm tra:

```sql
SELECT JSON_VALID('{"name": "Lan"}') AS valid_json;
SELECT JSON_VALID('{name: "Lan"}') AS invalid_key;
SELECT JSON_VALID('{"active": True}') AS invalid_boolean;
SELECT JSON_VALID('[1, 2,]') AS invalid_array;
```

Khi ghi một chuỗi JSON không hợp lệ vào cột JSON, MySQL phát lỗi thay vì lưu chuỗi đó như một document hợp lệ. Nếu muốn lưu văn bản tự do không cần tuân thủ JSON, hãy dùng VARCHAR hoặc TEXT.

## 19. Chọn JSON hay mô hình quan hệ?

JSON hữu ích khi dữ liệu có cấu trúc linh hoạt, các thuộc tính thay đổi theo loại bản ghi hoặc cần lưu một payload có cấu trúc từ hệ thống khác. Tuy nhiên, không nên đưa toàn bộ dữ liệu vào một cột JSON chỉ vì MySQL hỗ trợ kiểu này.

| Đặc điểm dữ liệu | Hướng thiết kế nên cân nhắc |
|---|---|
| Thuộc tính ổn định, cần NOT NULL/UNIQUE/FK | Cột quan hệ thông thường. |
| Cần JOIN thường xuyên với bảng khác | Bảng quan hệ và khóa ngoại. |
| Một nhóm thuộc tính tùy chọn thay đổi theo loại entity | Có thể dùng JSON. |
| Danh sách con cần truy vấn, lọc, cập nhật độc lập | Cân nhắc bảng con thay vì array JSON. |
| Payload ngoài hệ thống cần lưu gần nguyên cấu trúc | JSON column có thể phù hợp. |
| Giá trị cần index và lọc thường xuyên | Cột quan hệ hoặc generated column/index theo biểu thức JSON phù hợp. |

JSON không tự tạo khóa ngoại cho các ID nằm trong document và không tự bảo đảm các giá trị bên trong có cùng kiểu nghiệp vụ giữa mọi bản ghi. Ứng dụng cần xác định schema mong đợi, validate input và thiết kế cách nâng cấp cấu trúc JSON.

## 20. Những lưu ý khi làm việc với JSON

- Dùng object cho các thuộc tính có tên; dùng array cho danh sách có thứ tự.
- Dùng number cho giá trị cần tính toán; không lưu số dưới dạng string nếu không có lý do.
- Dùng boolean JSON `true`/`false`, không dùng chuỗi `"true"`/`"false"` để thay thế.
- Chọn rõ ý nghĩa của JSON null, SQL NULL và key không tồn tại.
- Dùng JSON_OBJECT/JSON_ARRAY thay vì ghép JSON bằng nối chuỗi thủ công.
- Dùng JSON_TYPE để kiểm tra kiểu, JSON_VALID để kiểm tra văn bản đầu vào và JSON_CONTAINS_PATH để kiểm tra path tồn tại.
- Không phụ thuộc vào thứ tự key object sau khi MySQL chuẩn hóa document.
- Tránh key trùng lặp trong object.
- Chỉ lưu vào JSON những thuộc tính thực sự cần tính linh hoạt; thuộc tính cốt lõi nên có cột quan hệ.
- Nếu thường xuyên lọc theo một thuộc tính JSON, đánh giá generated column hoặc functional index phù hợp với phiên bản MySQL.

## 21. Lab tổng hợp

Lab sau tạo bảng lưu hồ sơ khách hàng, bao gồm object, array, scalar lồng nhau, JSON null và thuộc tính không tồn tại. Chạy trong schema thực hành; nếu bảng đã tồn tại, kiểm tra dữ liệu trước khi tạo lại.

### 21.1. Tạo bảng và dữ liệu

```sql
CREATE TABLE json_profile_lab (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    profile JSON NULL
) ENGINE = InnoDB;

INSERT INTO json_profile_lab (customer_id, profile)
VALUES
    (
        1001,
        JSON_OBJECT(
            'name', 'Lan Nguyen',
            'active', CAST('true' AS JSON),
            'nickname', NULL,
            'tags', JSON_ARRAY('vip', 'email'),
            'address', JSON_OBJECT('city', 'Da Nang')
        )
    ),
    (
        1002,
        '{"name": "Minh Tran", "active": false, "tags": [], "address": {"city": "Hue"}}'
    ),
    (1003, 'null'),
    (1004, NULL);
```

### 21.2. Xem kiểu gốc

```sql
SELECT
    customer_id,
    profile IS NULL AS is_sql_null,
    JSON_TYPE(profile) AS root_type
FROM json_profile_lab
ORDER BY customer_id;
```

Hàng 1003 có root type NULL (kiểu JSON); hàng 1004 có SQL NULL nên `JSON_TYPE(profile)` trả SQL NULL.

### 21.3. Trích xuất thuộc tính lồng nhau

```sql
SELECT
    customer_id,
    profile->>'$.name' AS customer_name,
    profile->>'$.address.city' AS city,
    JSON_TYPE(JSON_EXTRACT(profile, '$.active')) AS active_type,
    JSON_EXTRACT(profile, '$.tags[0]') AS first_tag
FROM json_profile_lab
WHERE profile IS NOT NULL
  AND JSON_TYPE(profile) = 'OBJECT'
ORDER BY customer_id;
```

Điều kiện lọc loại bỏ SQL NULL và document gốc không phải object trước khi truy cập các path của object.

### 21.4. Phân biệt nickname null và nickname thiếu

```sql
SELECT
    customer_id,
    JSON_CONTAINS_PATH(profile, 'one', '$.nickname') AS has_nickname,
    JSON_TYPE(JSON_EXTRACT(profile, '$.nickname')) AS nickname_type
FROM json_profile_lab
WHERE profile IS NOT NULL
  AND JSON_TYPE(profile) = 'OBJECT'
ORDER BY customer_id;
```

Khách hàng 1001 có key nickname với JSON null. Khách hàng 1002 không có key nickname. Kết hợp cột has_nickname và nickname_type để phân biệt hai trường hợp.

### 21.5. Kiểm tra và xóa thuộc tính

```sql
SELECT JSON_REMOVE(profile, '$.nickname') AS profile_without_nickname
FROM json_profile_lab
WHERE customer_id = 1001;
```

Hàm trên trả document đã bỏ key nickname. Đây là phép biến đổi trả về giá trị JSON; nó không tự cập nhật hàng trong bảng. Muốn ghi kết quả trở lại, phải dùng câu UPDATE riêng và xác định rõ nghiệp vụ.

## 22. Bài tập tự luyện

### Bài tập 1: Nhận diện kiểu JSON

Dùng `JSON_TYPE()` để xác định kiểu của object, array, string, integer, decimal, boolean và null.

**Yêu cầu:** giải thích vì sao `"42"` và `42` có kiểu khác nhau.

### Bài tập 2: Dựng object và array

Tạo một object khách hàng có id, tên, trạng thái active, danh sách tags và địa chỉ lồng nhau.

**Yêu cầu:** dùng `JSON_OBJECT()` và `JSON_ARRAY()`, không ghép chuỗi JSON thủ công.

### Bài tập 3: Truy cập JSON path

Cho document có array items chứa các object sku và quantity.

**Yêu cầu:** lấy SKU phần tử đầu tiên, quantity phần tử thứ hai và kiểu dữ liệu của từng giá trị.

### Bài tập 4: Phân biệt ba trạng thái null

Tạo ba hàng: cột SQL NULL, document JSON null ở gốc, object có thuộc tính nickname JSON null; thêm một hàng object không có nickname.

**Yêu cầu:** viết một câu SELECT phân loại cả bốn trạng thái bằng `IS NULL`, `JSON_TYPE()` và `JSON_CONTAINS_PATH()`.

### Bài tập 5: JSON null hay key bị xóa?

Dùng `JSON_SET()` để đặt nickname thành JSON null, sau đó dùng `JSON_REMOVE()` để xóa key.

**Yêu cầu:** chứng minh hai document có cấu trúc khác nhau bằng `JSON_CONTAINS_PATH()`.

### Bài tập 6: Kiểm tra JSON không hợp lệ

Thử các chuỗi có key không quote, dấu phẩy thừa, boolean viết hoa và dấu nháy đơn.

**Yêu cầu:** dùng `JSON_VALID()` phân loại và giải thích lỗi.

### Bài tập 7: Chọn mô hình dữ liệu

Một đơn hàng có customer_id, created_at, total_amount và một nhóm metadata tùy chọn.

**Yêu cầu:** đề xuất thuộc tính nào nên là cột quan hệ, thuộc tính nào có thể lưu JSON; giải thích nhu cầu JOIN, constraint và index.

## 23. Checklist khi thiết kế và truy vấn JSON

- [ ] Đã xác định kiểu gốc mong đợi: object, array hay scalar.
- [ ] Key object là string hợp lệ và không bị trùng.
- [ ] Array được dùng khi thứ tự phần tử có ý nghĩa.
- [ ] Number, boolean và string được biểu diễn đúng kiểu JSON.
- [ ] Đã phân biệt JSON string `"null"` với JSON null `null`.
- [ ] Đã phân biệt JSON null với SQL NULL của cột.
- [ ] Đã phân biệt thuộc tính có giá trị JSON null với path không tồn tại.
- [ ] Dùng `IS NULL`/`IS NOT NULL` để kiểm tra SQL NULL.
- [ ] Dùng `JSON_TYPE()` để kiểm tra kiểu JSON.
- [ ] Dùng `JSON_CONTAINS_PATH()` để kiểm tra key/path tồn tại.
- [ ] Dùng `JSON_VALID()` khi cần xác thực chuỗi đầu vào.
- [ ] Dùng `JSON_OBJECT()`/`JSON_ARRAY()` để dựng document an toàn.
- [ ] Không phụ thuộc thứ tự key object sau chuẩn hóa.
- [ ] Đã cân nhắc cột quan hệ, constraint và generated column trước khi đưa thuộc tính vào JSON.
- [ ] Đã thống nhất ý nghĩa nghiệp vụ của key bị bỏ qua, JSON null và SQL NULL.

## 24. Ghi nhớ

JSON có sáu kiểu giá trị: object, array, string, number, boolean và null. Object lưu các cặp key/value; array lưu danh sách có thứ tự; scalar là string, number, boolean hoặc null. Một JSON document có thể có object, array hoặc scalar làm giá trị gốc.

MySQL dùng kiểu cột JSON để kiểm tra và lưu document theo định dạng nội bộ. Dùng JSON_TYPE để xác định kiểu, JSON_VALID để kiểm tra văn bản, JSON_OBJECT/JSON_ARRAY để tạo document và JSON_EXTRACT cùng JSON path để truy cập dữ liệu.

SQL NULL, JSON null và path không tồn tại là ba trạng thái khác nhau. Dùng IS NULL để kiểm tra SQL NULL, JSON_TYPE(...)= 'NULL' để nhận diện JSON null và JSON_CONTAINS_PATH để xác nhận thuộc tính có tồn tại. Khi thiết kế, giữ các thuộc tính cốt lõi trong mô hình quan hệ; dùng JSON cho phần dữ liệu thực sự linh hoạt và có hợp đồng rõ ràng với ứng dụng.
