# Kiểu JSON gốc, kiểm tra hợp lệ và cấu trúc lưu trữ

MySQL cung cấp kiểu dữ liệu `JSON` gốc để lưu tài liệu JSON trong một cột có kiểm tra cú pháp tự động. Khi ghi vào cột JSON, MySQL phân tích giá trị đầu vào, từ chối tài liệu không hợp lệ và lưu nội dung theo định dạng JSON nhị phân nội bộ thay vì giữ nguyên chuỗi văn bản như một cột `TEXT` thông thường.

Kiểu JSON phù hợp khi một phần dữ liệu có cấu trúc linh hoạt, ví dụ payload webhook, thuộc tính mở rộng hoặc metadata thay đổi theo loại sự kiện. Các thuộc tính quan trọng, thường dùng để JOIN, lọc, sắp xếp hoặc ràng buộc nên được cân nhắc lưu thành cột quan hệ có kiểu rõ ràng. JSON không thay thế mô hình quan hệ; nó bổ sung một cách lưu trữ cho phần dữ liệu có cấu trúc biến đổi.

Bài học tập trung vào kiểu JSON gốc, cú pháp hợp lệ, khác biệt giữa JSON và TEXT, phân biệt SQL `NULL` với JSON `null`, cách MySQL chuẩn hóa và lưu trữ JSON nhị phân, các công cụ kiểm tra kích thước và những giới hạn cần tính đến khi thiết kế bảng.

## 1. JSON là kiểu dữ liệu gốc trong MySQL

MySQL hỗ trợ kiểu `JSON` từ MySQL 5.7.8. Đây là kiểu dữ liệu có ngữ nghĩa JSON, không đơn thuần là bí danh cho `VARCHAR` hoặc `TEXT`.

Khi khai báo:

```sql
CREATE TABLE webhook_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
```

cột `payload` chỉ nhận giá trị có cú pháp JSON hợp lệ. MySQL phân tích nội dung khi ghi và lưu giá trị theo biểu diễn JSON nhị phân nội bộ. Ứng dụng vẫn có thể gửi JSON dưới dạng chuỗi qua giao thức SQL; việc chuỗi được chuyển thành kiểu JSON diễn ra khi MySQL xử lý giá trị cho cột.

Kiểu JSON hỗ trợ các loại giá trị JSON như object, array, string, number, boolean và JSON `null`. Không bắt buộc mọi tài liệu phải có root là object, trừ khi schema ứng dụng hoặc constraint của bảng quy định như vậy.

## 2. JSON document gồm những cấu trúc nào?

JSON có sáu nhóm giá trị cơ bản:

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Object | `{"id": 10, "name": "Lan"}` | Tập cặp key/value |
| Array | `["mysql", "sql", "json"]` | Danh sách có thứ tự |
| String | `"payment.created"` | Chuỗi Unicode đặt trong dấu nháy kép |
| Number | `42`, `19.95`, `-3` | Giá trị số |
| Boolean | `true`, `false` | Giá trị logic |
| Null | `null` | Giá trị rỗng theo JSON |

Ví dụ object lồng nhau:

```json
{
  "eventType": "payment.created",
  "eventId": "evt_1001",
  "occurredAt": "2026-11-19T09:30:00Z",
  "attempt": 1,
  "test": false,
  "customer": {
    "id": 42,
    "region": "VN"
  },
  "tags": ["checkout", "card"],
  "metadata": null
}
```

JSON object có key là chuỗi; key và string value phải dùng dấu nháy kép. Các giá trị số/boolean/null không đặt trong dấu nháy nếu muốn giữ đúng kiểu JSON. Ví dụ `"attempt": "1"` là string, còn `"attempt": 1` là number.

## 3. Tạo cột JSON và ghi dữ liệu hợp lệ

Tạo bảng ví dụ:

```sql
CREATE TABLE integration_messages (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source VARCHAR(80) NOT NULL,
    message_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    received_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (message_id),
    KEY idx_messages_type_time (message_type, received_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Ghi một object JSON:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES (
    'billing-service',
    'payment.created',
    '{"paymentId":"pay_9001","amount":125000,"currency":"VND"}'
);
```

Ghi một array hoặc scalar cũng hợp lệ về mặt cú pháp JSON:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES
    ('catalog-service', 'catalog.tags', '["database", "mysql"]'),
    ('system', 'system.flag', 'true'),
    ('system', 'system.note', '"maintenance"');
```

Trong thiết kế ứng dụng, nên thống nhất root document là object nếu payload đại diện một entity/event có nhiều thuộc tính. Chọn root array/scalar khi hợp đồng dữ liệu thực sự yêu cầu và tất cả consumer hiểu rõ cấu trúc đó.

## 4. MySQL kiểm tra cú pháp JSON khi ghi

Nếu gán chuỗi không phải JSON hợp lệ vào cột JSON, câu lệnh ghi bị từ chối:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES ('legacy-client', 'broken.event', '{"id": 1,}');
```

Đoạn trên không hợp lệ vì có dấu phẩy thừa trước dấu đóng object. MySQL phát lỗi chuyển đổi/parse JSON (thường là lỗi 3140, `Invalid JSON text`) và không ghi giá trị sai vào cột JSON.

Một số lỗi cú pháp thường gặp:

```text
{"name": 'Lan'}          -- JSON string phải dùng dấu nháy kép
{"enabled": True}        -- boolean JSON là true/false chữ thường
{"value": undefined}     -- JSON không có undefined
{"items": [1, 2,]}       -- không có dấu phẩy thừa cuối array
{id: 10}                  -- key phải là string trong dấu nháy kép
```

Việc cột JSON tự kiểm tra cú pháp giúp bảo vệ dữ liệu trước mọi client ghi vào bảng, kể cả client không dùng Java hoặc bỏ qua validation ở tầng ứng dụng.

## 5. JSON_VALID(): kiểm tra chuỗi JSON trước khi lưu

`JSON_VALID()` kiểm tra một giá trị có biểu diễn JSON hợp lệ hay không:

```sql
SELECT JSON_VALID('{"id": 10, "active": true}') AS is_valid;
-- 1

SELECT JSON_VALID('{"id": 10,}') AS is_valid;
-- 0

SELECT JSON_VALID(NULL) AS is_valid;
-- NULL
```

Kết quả:

- `1`: giá trị là JSON hợp lệ.
- `0`: giá trị không phải JSON hợp lệ.
- `NULL`: đầu vào SQL là `NULL`.

`JSON_VALID()` hữu ích khi dữ liệu đang nằm trong `VARCHAR`/`TEXT`, khi import dữ liệu cũ hoặc khi cần kiểm tra trước một thao tác chuyển đổi. Với cột JSON gốc, MySQL đã xác thực cú pháp khi ghi; gọi lại `JSON_VALID(payload)` thường không cần thiết để chứng minh giá trị trong cột vẫn hợp lệ.

## 6. Cú pháp JSON hợp lệ khác với cấu trúc nghiệp vụ hợp lệ

Một tài liệu có thể hợp lệ theo cú pháp JSON nhưng không đáp ứng hợp đồng nghiệp vụ:

```json
{"amount": "a lot", "currency": 123}
```

Đây là JSON hợp lệ về cú pháp, nhưng có thể sai hợp đồng nếu `amount` phải là số và `currency` phải là chuỗi mã tiền tệ.

Cần phân biệt ba lớp kiểm tra:

1. **Cú pháp JSON:** dấu ngoặc, dấu phẩy, dấu nháy và literal có đúng JSON hay không. Cột JSON gốc tự kiểm tra lớp này.
2. **Cấu trúc/schema:** root có phải object, thuộc tính bắt buộc có tồn tại, kiểu của từng thuộc tính có đúng không.
3. **Quy tắc nghiệp vụ:** số tiền dương, trạng thái nằm trong tập cho phép, mã tenant tồn tại, timestamp phù hợp và các trường có quan hệ logic với nhau.

Không nên cho rằng cột `JSON` tự hiểu toàn bộ schema nghiệp vụ. Việc xác thực cấu trúc và nghiệp vụ cần được thiết kế riêng ở ứng dụng, constraint hoặc cơ chế JSON Schema phù hợp với phiên bản.

## 7. JSON_SCHEMA_VALID() trong MySQL 8.0.17+

MySQL 8.0.17 bổ sung `JSON_SCHEMA_VALID()` và `JSON_SCHEMA_VALIDATION_REPORT()` để kiểm tra tài liệu theo JSON Schema (hỗ trợ JSON Schema Draft 4). Ví dụ:

```sql
SET @payment_schema = '{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "required": ["paymentId", "amount", "currency"],
  "properties": {
    "paymentId": {"type": "string"},
    "amount": {"type": "number", "minimum": 0},
    "currency": {"type": "string", "minLength": 3, "maxLength": 3}
  },
  "additionalProperties": false
}';

SELECT JSON_SCHEMA_VALID(
    @payment_schema,
    '{"paymentId":"pay_9001","amount":125000,"currency":"VND"}'
) AS schema_valid;
```

`JSON_SCHEMA_VALID()` trả `1` nếu tài liệu đáp ứng schema và `0` nếu không. `JSON_SCHEMA_VALIDATION_REPORT()` cung cấp báo cáo chi tiết hơn về lỗi validation.

JSON Schema giúp kiểm tra kiểu, thuộc tính bắt buộc, giới hạn và cấu trúc lồng nhau. Nó không thay thế mọi quy tắc nghiệp vụ cần truy vấn database hoặc gọi dịch vụ khác. Nếu hệ thống chạy MySQL trước 8.0.17, không giả định hai hàm này tồn tại; kiểm tra schema ở ứng dụng hoặc dùng cơ chế tương thích phù hợp.

## 8. CHECK constraint cho quy tắc đơn giản

MySQL thực thi `CHECK` constraint từ phiên bản 8.0.16. Trước phiên bản này, cú pháp CHECK được chấp nhận nhưng constraint không được thực thi như kỳ vọng.

Ví dụ bắt buộc root JSON là object:

```sql
CREATE TABLE object_documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payload JSON NOT NULL,
    PRIMARY KEY (document_id),
    CONSTRAINT chk_payload_is_object
        CHECK (JSON_TYPE(payload) = 'OBJECT')
) ENGINE=InnoDB;
```

Cột JSON tự kiểm tra cú pháp; CHECK ở đây kiểm tra thêm root value phải có loại `OBJECT`. Một JSON array hoặc scalar dù hợp lệ cú pháp vẫn bị constraint từ chối.

CHECK phù hợp với quy tắc cục bộ, xác định trên cùng hàng. Không dùng nó để thay thế kiểm tra cần truy vấn bảng khác, gọi routine hoặc áp dụng logic phức tạp. Khi hỗ trợ nhiều phiên bản MySQL, xác nhận phiên bản thực thi CHECK trước khi dựa vào constraint.

## 9. JSON column và TEXT column khác nhau

| Tiêu chí | Kiểu `JSON` | `TEXT`/`LONGTEXT` chứa JSON |
| --- | --- | --- |
| Kiểm tra cú pháp khi ghi | MySQL tự parse và từ chối JSON sai | Không tự xác thực JSON |
| Biểu diễn lưu trữ | Định dạng JSON nhị phân nội bộ | Chuỗi ký tự theo charset/collation của cột |
| Truy cập thành phần | JSON functions làm việc với giá trị JSON đã parse | Thường phải parse/convert chuỗi trước khi xử lý JSON |
| Chuẩn hóa | MySQL chuẩn hóa tài liệu khi parse/lưu | Chuỗi gốc có thể giữ khoảng trắng/thứ tự key như nhập |
| Mục đích | Dữ liệu cần ngữ nghĩa JSON trong database | Lưu nguyên văn payload, archive hoặc tương thích legacy |
| Kiểm tra schema | Có thể kết hợp JSON Schema/constraint | Cần validation riêng; có thể thêm CHECK JSON_VALID trên phiên bản hỗ trợ |

Nếu cột `TEXT` được dùng như một kho JSON, có thể thêm constraint:

```sql
CREATE TABLE legacy_payloads (
    payload_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    raw_payload LONGTEXT NOT NULL,
    PRIMARY KEY (payload_id),
    CONSTRAINT chk_raw_payload_json
        CHECK (JSON_VALID(raw_payload))
) ENGINE=InnoDB;
```

Constraint trên chỉ được thực thi từ MySQL 8.0.16. Với phiên bản cũ hơn, cần kiểm tra ở ứng dụng hoặc trigger phù hợp; không dựa vào CHECK bị bỏ qua.

Dùng TEXT khi mục tiêu là giữ nguyên byte/chuỗi payload theo hợp đồng lưu trữ hoặc cần tương thích hệ thống cũ. Dùng JSON khi muốn MySQL hiểu, xác thực và xử lý dữ liệu như tài liệu JSON.

## 10. Cấu trúc lưu trữ JSON nhị phân

MySQL không lưu cột JSON gốc như một chuỗi JSON văn bản nguyên vẹn. Khi nhận giá trị, server parse tài liệu và chuyển nó sang biểu diễn JSON nhị phân nội bộ.

Ở mức khái niệm, biểu diễn này chứa thông tin để MySQL nhận biết loại giá trị và định vị thành phần:

- Object/array có thông tin cấu trúc và số lượng phần tử.
- Object có key và value; key được biểu diễn cùng thông tin vị trí/độ dài.
- Array giữ thứ tự phần tử và thông tin định vị phần tử.
- Giá trị có type tag để phân biệt string, number, literal, object hoặc array.
- Offset/length giúp truy cập thành phần mà không phải quét và parse lại toàn bộ chuỗi văn bản từ đầu theo cách của TEXT.

Định dạng nhị phân được thiết kế để truy cập thành phần hiệu quả hơn. Đây là định dạng nội bộ của MySQL; ứng dụng không nên tự phân tích byte JSON nội bộ hoặc phụ thuộc vào layout cụ thể giữa các phiên bản.

## 11. Object và array được tổ chức trong binary JSON

Object JSON là tập cặp key/value. Biểu diễn nhị phân cần lưu key, loại value và vị trí của value để có thể tìm thuộc tính theo key. Array lưu các value theo thứ tự, cùng thông tin cần thiết để truy cập phần tử theo index.

Một object:

```json
{
  "customerId": 42,
  "region": "VN",
  "verified": true
}
```

và một array:

```json
[42, "VN", true]
```

được biểu diễn với cấu trúc khác nhau vì object phải quản lý tên key còn array chỉ cần vị trí phần tử. MySQL dùng type và offset nội bộ để hỗ trợ truy cập; không nên giả định mỗi thành phần được lưu như một chuỗi độc lập.

Lợi ích là JSON functions có thể truy cập một phần tài liệu mà không cần ứng dụng tự deserialize toàn bộ payload. Tuy nhiên, truy cập JSON vẫn có chi phí CPU, thao tác trên tài liệu lớn có thể tốn tài nguyên và truy vấn theo thuộc tính thường xuyên cần thiết kế cột/index phù hợp.

## 12. MySQL chuẩn hóa JSON khi parse

Khi một tài liệu được parse thành giá trị JSON, MySQL có thể chuẩn hóa biểu diễn, bao gồm loại bỏ khoảng trắng không có ý nghĩa và sắp xếp key của object theo quy tắc nội bộ. Nếu object đầu vào có key trùng nhau, MySQL giữ giá trị cuối cùng của key trùng trong quá trình chuẩn hóa.

Ví dụ đầu vào:

```json
{"status":"pending", "status":"paid", "amount":100}
```

không nên được dùng làm cách biểu diễn nhiều giá trị cho cùng một thuộc tính. Sau khi parse, giá trị key trùng không được bảo toàn như một danh sách các cặp key lặp; giá trị cuối cùng được giữ lại.

Vì chuẩn hóa có thể làm thay đổi cách hiển thị so với chuỗi ban đầu:

- Không dựa vào thứ tự key khi so sánh JSON object.
- Không dùng whitespace hoặc cách format để xác định hai tài liệu khác nhau.
- Không gửi object có key trùng; kiểm tra và từ chối ở producer/serializer.
- Nếu cần lưu nguyên văn request để phục vụ pháp lý hoặc chữ ký số, lưu thêm raw payload dạng binary/text riêng bên cạnh cột JSON đã parse.

## 13. JSON object không phải hợp đồng về thứ tự key

Object JSON về mặt ngữ nghĩa là tập cặp tên/giá trị; consumer không nên dựa vào thứ tự key. MySQL có thể sắp xếp key khi chuẩn hóa biểu diễn nội bộ. Vì vậy, kết quả đọc/serialize có thể không giữ thứ tự key như chuỗi đã gửi.

Array khác object: thứ tự phần tử array là một phần dữ liệu và cần được giữ theo ngữ nghĩa JSON.

Nếu ứng dụng ký số payload theo byte nguyên bản, phải giữ raw bytes/chuỗi đúng như nhận được và xác định canonicalization algorithm rõ ràng. Không ký trên chuỗi JSON đã được MySQL trả ra với giả định nó giống byte đầu vào.

## 14. SQL NULL khác JSON null

Đây là hai giá trị khác nhau:

- SQL `NULL`: cột không có giá trị SQL.
- JSON `null`: một giá trị JSON hợp lệ nằm trong tài liệu.

Ví dụ:

```sql
CREATE TABLE nullable_json_examples (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sql_null_doc JSON NULL,
    json_null_doc JSON NULL,
    PRIMARY KEY (id)
);

INSERT INTO nullable_json_examples (sql_null_doc, json_null_doc)
VALUES (NULL, 'null');
```

Kiểm tra:

```sql
SELECT
    sql_null_doc IS NULL AS is_sql_null,
    json_null_doc IS NULL AS json_column_is_sql_null,
    JSON_TYPE(sql_null_doc) AS sql_null_type,
    JSON_TYPE(json_null_doc) AS json_value_type
FROM nullable_json_examples;
```

`sql_null_doc IS NULL` trả `1`; `json_null_doc IS NULL` trả `0`; `JSON_TYPE(json_null_doc)` trả chuỗi `NULL` để biểu thị loại JSON null. `JSON_TYPE(sql_null_doc)` trả SQL NULL.

Sự khác biệt này ảnh hưởng điều kiện lọc, default, validation và cách Java map dữ liệu. Hãy quyết định rõ “không có payload” có nghĩa là SQL NULL hay payload JSON có giá trị null.

## 15. Kiểm tra kiểu root bằng JSON_TYPE()

`JSON_TYPE()` trả loại JSON của một giá trị:

```sql
SELECT JSON_TYPE('{"id": 1}') AS value_type; -- OBJECT
SELECT JSON_TYPE('[1, 2]') AS value_type;      -- ARRAY
SELECT JSON_TYPE('42') AS value_type;          -- INTEGER
SELECT JSON_TYPE('true') AS value_type;        -- BOOLEAN
SELECT JSON_TYPE('null') AS value_type;        -- NULL
```

Điều này hữu ích khi kiểm tra root document trước khi áp dụng logic chỉ phù hợp với object hoặc array. Ví dụ:

```sql
SELECT message_id
FROM integration_messages
WHERE JSON_TYPE(payload) = 'OBJECT';
```

Không nhầm chuỗi JSON `"42"` với số JSON `42`: loại thứ nhất là `STRING`, loại thứ hai là `INTEGER` (hoặc loại số phù hợp với giá trị). Kiểu dữ liệu có ý nghĩa đối với so sánh và validation.

## 16. Đo kích thước JSON bằng JSON_STORAGE_SIZE()

MySQL cung cấp `JSON_STORAGE_SIZE()` để xem số byte mà biểu diễn JSON sử dụng:

```sql
SELECT
    message_id,
    JSON_STORAGE_SIZE(payload) AS json_storage_bytes
FROM integration_messages
ORDER BY message_id;
```

Hàm này đo kích thước biểu diễn JSON nội bộ của giá trị, không phải kích thước toàn bộ row InnoDB, index, page overhead hay số byte truyền trên network. Khi so sánh với độ dài chuỗi JSON đầu vào, hãy nhớ binary representation có metadata/offset và chuẩn hóa riêng.

Có thể dùng `OCTET_LENGTH()` trên chuỗi JSON văn bản để đo số byte của chuỗi:

```sql
SELECT OCTET_LENGTH('{"name":"Nguyễn An"}') AS input_bytes;
```

Không so sánh hai con số rồi kết luận binary JSON luôn nhỏ hơn TEXT. Định dạng nhị phân được thiết kế để truy cập hiệu quả; kích thước thực tế phụ thuộc cấu trúc, key, string, number và overhead.

## 17. JSON_STORAGE_FREE() và partial update

Từ MySQL 5.7.22, `JSON_STORAGE_FREE()` có thể cho biết dung lượng đã được giải phóng bên trong giá trị JSON sau một số partial update đủ điều kiện.

Ví dụ minh họa:

```sql
CREATE TABLE json_storage_lab (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    doc JSON NOT NULL
) ENGINE=InnoDB;

INSERT INTO json_storage_lab (id, doc)
VALUES (1, '{"name":"Lan","description":"A long description for update test"}');

UPDATE json_storage_lab
SET doc = JSON_REMOVE(doc, '$.description')
WHERE id = 1;

SELECT
    JSON_STORAGE_SIZE(doc) AS storage_bytes,
    JSON_STORAGE_FREE(doc) AS free_bytes
FROM json_storage_lab
WHERE id = 1;
```

MySQL có thể tối ưu một số thao tác `JSON_SET()`, `JSON_REPLACE()` hoặc `JSON_REMOVE()` bằng partial in-place update nếu thỏa điều kiện của engine/phiên bản, chẳng hạn thao tác sửa trực tiếp cột JSON và giá trị mới phù hợp với vùng lưu trữ hiện có. Không phải mọi thay đổi đều được cập nhật tại chỗ; thay đổi làm tài liệu lớn hơn hoặc biểu thức không đủ điều kiện có thể cần ghi lại giá trị.

`JSON_STORAGE_FREE()` không phải phép đo dung lượng file InnoDB đã trả lại cho hệ điều hành. Nó mô tả khoảng trống trong biểu diễn JSON của giá trị sau tối ưu partial update. Đừng dùng nó như chỉ số duy nhất để đánh giá phân mảnh tablespace.

## 18. Lưu trữ JSON trong InnoDB và tài liệu lớn

Kiểu JSON là kiểu dữ liệu ở lớp SQL; cách lưu trên page và record còn chịu ảnh hưởng của InnoDB, row format, page size và kích thước giá trị. Tài liệu nhỏ có thể được lưu cùng record; giá trị lớn có thể cần cơ chế lưu trữ ngoài trang tương tự các giá trị lớn khác. Không nên giả định mọi JSON luôn nằm trọn trong record hoặc mọi JSON luôn được lưu ngoài trang.

Các hệ quả thiết kế:

- JSON lớn có thể tăng I/O khi truy vấn lấy toàn bộ payload.
- `SELECT *` có thể kéo theo dữ liệu JSON không cần thiết.
- Nhiều tài liệu lớn làm tăng dung lượng bảng, backup và thời gian truyền.
- Cập nhật một phần tài liệu có thể vẫn cần parse/validate và có chi phí ghi.
- Tài liệu JSON không nên trở thành nơi nhét file nhị phân lớn; dùng object storage hoặc BLOB theo yêu cầu lưu trữ.

Nếu ứng dụng thường chỉ cần `event_type`, `tenant_id`, `created_at` và một vài thuộc tính lọc, hãy lưu các thuộc tính đó thành cột quan hệ riêng. JSON nên giữ phần metadata mở rộng hoặc payload thực sự linh hoạt.

## 19. Giới hạn kích thước và max_allowed_packet

Kích thước tài liệu JSON chịu giới hạn của cơ chế packet/client/server và tài nguyên xử lý. `max_allowed_packet` giới hạn kích thước packet mà server/client chấp nhận; giá trị cụ thể phụ thuộc cấu hình và phiên bản.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'max_allowed_packet';
```

Khi gửi JSON rất lớn, lỗi có thể xuất hiện ở client driver, packet protocol, server memory hoặc giới hạn lưu trữ. Không giải quyết bằng cách tăng `max_allowed_packet` vô hạn; hãy xem payload có nên tách file/object lớn sang object storage, chia batch hoặc gửi theo luồng hay không.

Kích thước JSON không chỉ là số ký tự. Unicode có thể chiếm nhiều byte hơn số ký tự; JSON binary representation còn có metadata. Đo byte thực tế và kiểm thử bằng driver giống production.

## 20. Charset, Unicode và chuỗi trong JSON

JSON text dùng Unicode; MySQL xử lý chuỗi JSON theo charset phù hợp với `utf8mb4`. Dùng `utf8mb4` cho schema/connection để hỗ trợ đầy đủ ký tự ngoài BMP, tiếng Việt và emoji.

Ví dụ:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES (
    'profile-service',
    'profile.updated',
    '{"displayName":"Nguyễn Ánh 🌱","city":"Hồ Chí Minh"}'
);
```

Kiểm tra charset của connection và cột khi dữ liệu bị lỗi dấu hoặc thay thế ký tự. Không sửa chuỗi bằng cách encode/decode nhiều lần; xác định encoding ở ranh giới ứng dụng và kết nối.

## 21. Lưu JSON qua Java/JDBC

Ứng dụng Java thường serialize object thành JSON string bằng thư viện JSON rồi bind giá trị vào cột JSON bằng prepared statement:

```java
String sql = "INSERT INTO integration_messages "
        + "(source, message_type, payload) VALUES (?, ?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "billing-service");
    statement.setString(2, "payment.created");
    statement.setString(3, jsonMapper.writeValueAsString(payload));
    statement.executeUpdate();
}
```

MySQL sẽ kiểm tra chuỗi bind có phải JSON hợp lệ khi gán vào cột `payload`. Dùng parameter binding thay vì nối chuỗi JSON vào SQL để tránh lỗi quoting và SQL injection.

Ở Java, tránh serialize số tiền thành `double` nếu cần độ chính xác thập phân; dùng `BigDecimal` và cấu hình serializer phù hợp. Thống nhất cách biểu diễn timestamp (thường ISO-8601 với timezone/offset rõ ràng) và quy tắc null/field missing giữa producer và consumer.

## 22. Thiết kế cột quan hệ và JSON cùng nhau

Một mô hình lai thường hiệu quả:

```sql
CREATE TABLE webhook_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    payload JSON NOT NULL,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id),
    KEY idx_webhook_tenant_type_time (tenant_id, event_type, occurred_at)
) ENGINE=InnoDB;
```

`tenant_id`, `event_type`, `occurred_at` là cột quan hệ vì thường cần lọc, phân vùng, thống kê và lập chỉ mục. `payload` giữ phần nội dung thay đổi theo event type.

Không đưa mọi thuộc tính vào JSON chỉ vì schema linh hoạt. Nếu `tenant_id` chỉ nằm trong JSON, việc phân quyền, join, index và ràng buộc có thể khó hơn. Ngược lại, không cần tạo hàng chục cột nullable cho các thuộc tính hiếm và khác nhau giữa từng loại event nếu JSON phù hợp hơn.

## 23. Index trên thuộc tính JSON là chủ đề riêng

Không tạo index B-tree trực tiếp trên toàn bộ document JSON như trên cột số/ngày thông thường. Khi cần lọc theo một thuộc tính JSON thường xuyên, có thể trích xuất scalar sang generated column rồi index cột đó, hoặc dùng functional index phù hợp với phiên bản MySQL.

Ví dụ định hướng:

```sql
ALTER TABLE webhook_events
ADD COLUMN payload_customer_id BIGINT
    GENERATED ALWAYS AS (
        CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.customerId')) AS UNSIGNED)
    ) STORED,
ADD INDEX idx_webhook_customer (payload_customer_id);
```

Ví dụ này chỉ minh họa ranh giới giữa lưu document và lập chỉ mục thuộc tính. Cần kiểm tra kiểu dữ liệu, giá trị thiếu/NULL, giá trị không chuyển đổi được và phân bố trước khi tạo generated column/index. Nội dung tối ưu JSON path và index được học ở bài chuyên sâu tương ứng.

## 24. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| JSON chỉ nhận object | MySQL chấp nhận các JSON value hợp lệ như object, array và scalar | Dùng CHECK/JSON Schema nếu root phải là object |
| Cột JSON giữ nguyên chuỗi đã gửi | MySQL parse và lưu biểu diễn nhị phân, có chuẩn hóa | Lưu raw payload riêng nếu cần giữ nguyên văn |
| JSON_VALID kiểm tra quy tắc nghiệp vụ | Nó kiểm tra cú pháp JSON | Dùng JSON Schema và validation nghiệp vụ |
| JSON null giống SQL NULL | Đây là hai giá trị khác nhau | Dùng `IS NULL` và `JSON_TYPE()` đúng mục đích |
| TEXT tự xác thực JSON | TEXT chỉ lưu chuỗi | Dùng cột JSON hoặc CHECK JSON_VALID trên phiên bản hỗ trợ |
| Binary JSON luôn nhỏ hơn văn bản | Binary format có metadata/offset; kích thước phụ thuộc nội dung | Đo bằng JSON_STORAGE_SIZE và byte đầu vào |
| Thứ tự key object được giữ nguyên | MySQL có thể chuẩn hóa/sắp xếp key | Không phụ thuộc thứ tự object key |
| Duplicate key được giữ thành nhiều thuộc tính | MySQL chuẩn hóa và giữ giá trị cuối cùng của key trùng | Từ chối key trùng ở producer |
| JSON column tự hiểu schema nghiệp vụ | Native type chỉ bảo đảm cú pháp JSON | Dùng CHECK, JSON_SCHEMA_VALID và validation ứng dụng |
| JSON document có kích thước vô hạn | Packet, bộ nhớ và giới hạn lưu trữ vẫn áp dụng | Kiểm soát kích thước payload và `max_allowed_packet` |
| JSON là nơi phù hợp cho mọi thuộc tính | Thuộc tính lọc/join thường xuyên nên có cột quan hệ | Dùng mô hình lai relational + JSON |

## 25. Quy trình thiết kế và kiểm tra JSON column

1. Xác định phần dữ liệu nào thực sự linh hoạt và phần nào là thuộc tính quan hệ ổn định.
2. Chọn kiểu root (thường là object cho event/entity) và mô tả schema payload.
3. Tạo cột `JSON` nếu muốn MySQL xác thực cú pháp và xử lý JSON native.
4. Dùng `NOT NULL` nếu payload bắt buộc tồn tại; phân biệt SQL NULL với JSON null.
5. Dùng CHECK để ràng buộc đơn giản như root type trên MySQL 8.0.16+.
6. Dùng JSON Schema functions từ MySQL 8.0.17+ khi cần kiểm tra cấu trúc Draft 4 trong database.
7. Validate quy tắc nghiệp vụ ở tầng sở hữu use case.
8. Không gửi object có key trùng và không dựa vào thứ tự key.
9. Đo `JSON_STORAGE_SIZE()` và byte payload thực tế; kiểm tra `max_allowed_packet`.
10. Dùng `utf8mb4` và parameter binding ở client.
11. Đưa thuộc tính thường xuyên lọc/join ra cột quan hệ hoặc generated column có index phù hợp.
12. Kiểm thử dữ liệu lớn, NULL, JSON null, scalar, array, Unicode và payload không hợp lệ.

## 26. Bài tập thực hành

1. Tạo bảng có cột `JSON NOT NULL`; insert object, array, string, number, boolean và JSON null.
2. Thử insert JSON sai cú pháp; ghi lại lỗi MySQL và xác nhận không có hàng sai được lưu.
3. Dùng `JSON_VALID()` để phân biệt JSON hợp lệ, không hợp lệ và SQL NULL.
4. Tạo bảng TEXT chứa JSON; so sánh khả năng tự kiểm tra của TEXT với cột JSON.
5. Trên MySQL 8.0.16+, tạo CHECK yêu cầu root JSON là OBJECT; thử insert array và scalar.
6. Trên MySQL 8.0.17+, dùng `JSON_SCHEMA_VALID()` để kiểm tra một payment payload; thử thiếu field bắt buộc và sai kiểu.
7. So sánh SQL NULL với JSON null bằng `IS NULL` và `JSON_TYPE()`.
8. Ghi object có key trùng và quan sát kết quả sau khi đọc lại; giải thích vì sao producer không nên gửi key trùng.
9. So sánh thứ tự key và whitespace của JSON đầu vào với kết quả MySQL trả về.
10. Dùng `JSON_STORAGE_SIZE()` để đo các payload ngắn, dài, nhiều key và nhiều array element.
11. Thử `JSON_STORAGE_FREE()` sau một partial update đủ điều kiện; phân biệt free space trong document với dung lượng tablespace.
12. Lưu payload có tiếng Việt và emoji; kiểm tra charset connection/schema.
13. Dùng Java/JDBC bind JSON string vào cột JSON; thử payload hợp lệ và không hợp lệ.
14. Thiết kế bảng lai với `tenant_id`, `event_type`, `occurred_at` và `payload`; giải thích vì sao các cột lọc chính không nên chỉ nằm trong JSON.

## 27. Ghi nhớ

Kiểu `JSON` gốc của MySQL (từ 5.7.8) tự parse và xác thực cú pháp khi ghi, rồi lưu tài liệu theo biểu diễn JSON nhị phân nội bộ. JSON có thể là object, array hoặc scalar; nếu nghiệp vụ yêu cầu root object hay schema cụ thể, cần thêm CHECK (được thực thi từ MySQL 8.0.16), JSON Schema functions (MySQL 8.0.17+) hoặc validation ở ứng dụng.

JSON nhị phân chứa type và thông tin định vị thành phần để hỗ trợ truy cập; MySQL có thể chuẩn hóa whitespace và key của object, đồng thời giữ giá trị cuối cùng khi gặp key trùng. Không dựa vào thứ tự key hoặc dùng cột JSON để giữ nguyên byte payload. SQL NULL khác JSON null; `JSON_VALID`, `JSON_TYPE`, `JSON_STORAGE_SIZE` và `JSON_STORAGE_FREE` phục vụ các mục đích kiểm tra/đo khác nhau. Tài liệu lớn còn chịu giới hạn packet, bộ nhớ và cách InnoDB lưu giá trị lớn. Thiết kế mô hình lai: cột quan hệ cho thuộc tính ổn định, thường lọc/join; JSON cho payload linh hoạt. Dùng `utf8mb4`, bind parameter, kiểm tra schema và đo kích thước với dữ liệu thực tế.
