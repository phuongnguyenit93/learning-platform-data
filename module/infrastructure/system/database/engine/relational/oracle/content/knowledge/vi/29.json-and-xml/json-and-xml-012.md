# Thiết kế hợp đồng JSON/XML, kiểm soát kích thước và dữ liệu không hợp lệ

JSON và XML là hai định dạng phổ biến để trao đổi dữ liệu giữa ứng dụng, dịch vụ và Oracle Database. Một payload có thể hợp lệ về cú pháp nhưng vẫn sai hợp đồng nghiệp vụ: thiếu trường bắt buộc, sai kiểu, giá trị vượt miền, cấu trúc lồng quá sâu, chứa quá nhiều phần tử hoặc có kích thước vượt khả năng xử lý. Vì vậy, thiết kế JSON/XML không chỉ là chọn tên field và tag; cần xác định schema, phiên bản, quy tắc null/missing, encoding, giới hạn tài nguyên, cách validate và cách xử lý dữ liệu lỗi.

Một hợp đồng dữ liệu tốt làm rõ điều gì được gửi, điều gì được nhận, kiểu và miền giá trị của từng trường, cách mở rộng tương thích, kích thước tối đa và phản hồi khi payload không hợp lệ. Oracle cung cấp các kiểu dữ liệu và SQL operators để lưu, truy vấn, sinh và kiểm tra JSON/XML; ứng dụng vẫn cần thiết kế quy trình xác thực và giới hạn tài nguyên trước khi đưa payload vào luồng xử lý chính.

Sau bài học, bạn có thể:

- Thiết kế contract JSON/XML có schema, version và quy tắc tương thích.
- Phân biệt field bị thiếu, JSON null, empty string và giá trị mặc định.
- Kiểm tra cú pháp JSON/XML và kiểm tra dữ liệu theo schema/nghiệp vụ.
- Hiểu JSON datatype, IS JSON, JSON_VALUE, JSON_EXISTS, JSON_TABLE và XMLType.
- Xử lý XML namespace, XML Schema và XMLTABLE.
- Đặt giới hạn kích thước payload, độ sâu lồng, số phần tử, độ dài chuỗi và số byte.
- Chọn VARCHAR2, CLOB, BLOB, JSON hoặc XMLType phù hợp.
- Phát hiện duplicate JSON keys, sai encoding, sai number/date và dữ liệu không hợp lệ.
- Phân loại lỗi cú pháp, lỗi schema, lỗi nghiệp vụ và lỗi tài nguyên.
- Thiết kế reject/quarantine, logging, retry và idempotency.
- Giảm rủi ro parser abuse, XML external entity và payload độc hại.
- Xây dựng bài lab kiểm tra contract và xử lý payload lỗi trong Oracle.

> JSON datatype và một số SQL/JSON syntax phụ thuộc phiên bản Oracle. Oracle Database 21c giới thiệu native JSON data type ở dạng JSON binary; các bản trước thường lưu JSON trong VARCHAR2/CLOB/BLOB kèm constraint IS JSON. Hãy kiểm tra Oracle SQL Language Reference đúng release, compatibility setting và client driver.

## 1. Hợp đồng dữ liệu là gì?

### 1.1. Contract mô tả cấu trúc và ý nghĩa

Một data contract xác định cách hai hệ thống trao đổi dữ liệu. Contract không chỉ liệt kê tên trường; tối thiểu cần mô tả:

- Tên và ý nghĩa của từng trường.
- Kiểu dữ liệu và miền giá trị hợp lệ.
- Trường bắt buộc, tùy chọn hoặc nullable.
- Quy tắc format ngày giờ, số, tiền tệ, mã định danh và enum.
- Quy tắc lồng object/array và cardinality.
- Phiên bản contract và chính sách tương thích.
- Giới hạn kích thước và tài nguyên.
- Cách xử lý field không biết, field trùng hoặc dữ liệu sai.
- Mã lỗi, correlation ID và hành vi retry.

Ví dụ contract cho đơn hàng:

```json
{
  "schemaVersion": "1.0",
  "orderId": "ORD-2026-000123",
  "createdAt": "2026-11-14T08:30:00Z",
  "currency": "VND",
  "items": [
    {
      "sku": "KB-001",
      "quantity": 2,
      "unitPrice": 450000
    }
  ]
}
```

Contract cần nói rõ orderId là bắt buộc và duy nhất trong phạm vi nào; createdAt phải là timestamp UTC hay chấp nhận offset; quantity là số nguyên dương; unitPrice là số thập phân với scale/precision nào; items có thể rỗng hay phải có ít nhất một phần tử.

### 1.2. Cú pháp hợp lệ chưa đủ

Payload sau là JSON hợp lệ về cú pháp:

```json
{
  "orderId": 123,
  "createdAt": "yesterday",
  "items": "keyboard"
}
```

Nhưng nếu contract yêu cầu orderId là string, createdAt là ISO-8601 timestamp và items là array, payload này không hợp lệ theo contract.

Phân biệt bốn lớp kiểm tra:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Syntax | Có parse được không? | JSON thiếu dấu phẩy |
| Structure/schema | Có đúng shape và kiểu không? | items phải là array |
| Domain/business | Giá trị có hợp lệ nghiệp vụ không? | quantity phải lớn hơn 0 |
| Operational/resource | Có nằm trong giới hạn hệ thống không? | payload 200 MB khi giới hạn 10 MB |

Một payload phải vượt qua tất cả lớp cần thiết trước khi được chấp nhận.

### 1.3. Contract là ranh giới giữa producer và consumer

Producer tạo dữ liệu; consumer đọc và xử lý. Hai bên có thể phát hành phiên bản độc lập. Contract giúp xác định:

- Producer được phép thêm trường nào?
- Consumer có bỏ qua trường chưa biết không?
- Consumer có bắt buộc hiểu schemaVersion không?
- Khi đổi kiểu hoặc đổi ý nghĩa field, cần version mới hay không?
- Dữ liệu cũ được đọc trong bao lâu?
- Ai chịu trách nhiệm validate và trả lỗi?

Không để contract chỉ tồn tại trong code của một service. Nên lưu schema/specification cùng source control, review thay đổi và có test tương thích.

## 2. Chọn JSON hay XML

### 2.1. JSON

JSON thường phù hợp với API web, message event và dữ liệu object/array. Cấu trúc gọn, phổ biến trong JavaScript và được Oracle hỗ trợ bằng SQL/JSON operators.

Ưu điểm:

- Cú pháp nhẹ, dễ đọc với object/array.
- Hỗ trợ string, number, boolean, null, object và array.
- Phù hợp API REST và event payload.
- Oracle có JSON datatype ở các release hiện đại và các hàm SQL/JSON.

Giới hạn:

- Không có comment trong chuẩn JSON.
- Không có kiểu date riêng; ngày giờ thường biểu diễn bằng string theo contract.
- Number không tự mang precision/scale nghiệp vụ.
- Quy tắc duplicate object key cần được quy định và xử lý nghiêm.

### 2.2. XML

XML phù hợp với tài liệu có cấu trúc, namespace, schema validation, hệ thống enterprise/SOAP và một số chuẩn trao đổi ngành.

Ưu điểm:

- Có XML Schema (XSD) để mô tả element, attribute, kiểu và cardinality.
- Namespace hỗ trợ phân biệt vocabulary.
- Có thể biểu diễn document-centric và mixed content.
- Oracle XML DB hỗ trợ XMLType, XMLQuery, XMLExists và XMLTable.

Giới hạn:

- Verbose hơn JSON.
- Namespace và schema có thể làm query phức tạp.
- Cần kiểm soát DTD/external entity và parser resource.
- Encoding/character set và whitespace cần được xác định rõ.

### 2.3. Chọn theo contract và hệ sinh thái

| Tiêu chí | JSON | XML |
| --- | --- | --- |
| API web hiện đại | Thường thuận tiện | Dùng khi API/chuẩn yêu cầu |
| Schema | JSON Schema thường dùng ở tầng ứng dụng; Oracle hỗ trợ kiểm tra SQL/JSON và các cơ chế riêng | XSD có chuẩn và tích hợp XML DB |
| Namespace | Không có namespace chuẩn | Có namespace |
| Document/mixed content | Hạn chế hơn | Mạnh |
| SQL trong Oracle | JSON datatype, SQL/JSON | XMLType, XQuery/XMLTABLE |
| Kích thước | Thường gọn | Thường verbose |
| Security parser | Kiểm soát parser và độ sâu/size | Cần thêm phòng chống XXE/entity expansion |

Định dạng không tự quyết định chất lượng contract. JSON có thể được thiết kế rất chặt; XML cũng có thể lỏng lẻo nếu không có schema và validation.

## 3. Thiết kế version và tương thích

### 3.1. Đưa version vào contract

Có thể dùng một trường rõ ràng:

```json
{
  "schemaVersion": "2.1",
  "eventType": "OrderCreated",
  "eventId": "evt-8f1c",
  "payload": {}
}
```

Hoặc dùng media type/version trong HTTP header hay topic/event metadata. Điều quan trọng là consumer có thể xác định phiên bản trước khi diễn giải payload.

### 3.2. Thay đổi thường tương thích

Trong contract có quy ước consumer bỏ qua field không biết:

- Thêm field optional thường có thể tương thích ngược.
- Thêm enum value có thể làm consumer cũ lỗi nếu code chỉ chấp nhận danh sách đóng.
- Thêm field required thường phá consumer cũ.
- Đổi tên field, xóa field hoặc đổi kiểu thường là breaking change.
- Đổi đơn vị hoặc ý nghĩa field dù giữ nguyên kiểu cũng là breaking change.

Ví dụ amount đổi từ VND sang USD là breaking change về ý nghĩa dù JSON vẫn hợp lệ.

### 3.3. Forward và backward compatibility

- Backward compatible: consumer mới đọc được payload do producer cũ tạo.
- Forward compatible: consumer cũ vẫn xử lý được payload do producer mới tạo.

Hai khái niệm phụ thuộc quy ước field unknown, required/optional và enum. Không tuyên bố một thay đổi tương thích chỉ vì schema parser vẫn parse được.

### 3.4. Quy tắc phát hành

Nên quy định:

1. Khi nào tăng minor version, khi nào tăng major version.
2. Thời gian hỗ trợ version cũ.
3. Chính sách deprecation và ngày ngừng nhận.
4. Consumer contract test trước khi producer phát hành.
5. Cách xử lý payload chưa có schema version hoặc version không hỗ trợ.
6. Cách lưu raw payload để điều tra trong thời hạn cho phép.

### 3.5. Không dùng thứ tự field làm version

JSON object không nên phụ thuộc thứ tự key. XML element có thể có thứ tự theo XSD, nhưng không dùng việc sắp xếp field như một cơ chế version. Dùng version tường minh.

## 4. Required, optional, missing, null và empty

### 4.1. Các trạng thái khác nhau

Trong JSON, những trạng thái sau không giống nhau:

```json
{}
```

```json
{"middleName": null}
```

```json
{"middleName": ""}
```

```json
{"middleName": " "}
```

- Missing: field không xuất hiện.
- Null: field xuất hiện và giá trị là JSON null.
- Empty string: field là chuỗi rỗng.
- Whitespace string: field chứa khoảng trắng.

Contract phải chỉ rõ cách hiểu từng trạng thái. Ví dụ, missing có nghĩa không thay đổi giá trị hiện tại trong PATCH; null có nghĩa xóa giá trị; empty string là giá trị rỗng được chấp nhận hoặc bị từ chối.

### 4.2. SQL NULL và JSON null

SQL NULL là trạng thái null của cột/biểu thức SQL. JSON null là giá trị null bên trong JSON document. Khi dùng SQL/JSON functions, cách ánh xạ giữa JSON null, path không tồn tại và SQL NULL phụ thuộc function cùng các clause ON EMPTY/ON ERROR.

Không mặc định rằng field missing và field JSON null có cùng ý nghĩa. Dùng JSON_EXISTS để kiểm tra field có tồn tại; dùng JSON_VALUE với quy tắc null/error rõ ràng để lấy giá trị scalar.

### 4.3. Empty string trong Oracle SQL

Trong Oracle SQL, chuỗi ký tự rỗng được xử lý như NULL đối với kiểu character thông thường. Điều này có thể làm mất khác biệt giữa empty string và SQL NULL khi đưa dữ liệu JSON/XML sang VARCHAR2. Nếu cần bảo toàn khác biệt, giữ raw JSON/XML hoặc dùng quy tắc biểu diễn riêng và kiểm thử round-trip.

### 4.4. PATCH semantics

Một contract PATCH có thể quy định:

| Input | Ý nghĩa cập nhật |
| --- | --- |
| Field missing | Giữ nguyên giá trị hiện tại |
| Field có giá trị | Thay bằng giá trị gửi lên |
| Field null | Xóa giá trị nếu field nullable |
| Field empty string | Từ chối hoặc lưu giá trị rỗng theo quy tắc |

Nếu không ghi rõ, producer và consumer có thể diễn giải khác nhau, gây xóa dữ liệu ngoài ý muốn.

### 4.5. Default value

Default nên được định nghĩa ở một nơi có thẩm quyền. Không để producer mặc định 0 trong khi consumer mặc định NULL. Nếu field missing được thay bằng default, cần xác định đó là default ở thời điểm nhận hay default động theo cấu hình hiện tại.

## 5. Định nghĩa kiểu và miền giá trị

### 5.1. Number

JSON number không phân biệt integer và decimal như kiểu SQL riêng. Contract cần mô tả:

- Số nguyên hay số thập phân.
- Precision và scale.
- Miền min/max.
- Có chấp nhận số âm không?
- Có chấp nhận exponent notation không?
- Quy tắc rounding.
- Đơn vị tiền tệ/đo lường.

Ví dụ tiền:

```json
{
  "currency": "VND",
  "amount": 1250000.00
}
```

Không truyền tiền bằng floating point nếu ứng dụng có thể phát sinh sai số nhị phân; ở tầng ứng dụng dùng decimal type, trong Oracle dùng NUMBER với precision/scale phù hợp. Không chuyển số lớn qua JavaScript Number nếu vượt miền integer chính xác của binary64; cân nhắc string decimal theo contract.

### 5.2. Date và timestamp

JSON không có date/time primitive. Quy định format rõ, ví dụ RFC 3339/ISO-8601:

```json
{
  "createdAt": "2026-11-14T08:30:00Z",
  "localDate": "2026-11-14"
}
```

Phân biệt:

- DATE: ngày lịch, không có giờ.
- Local date-time: giờ địa phương không có offset.
- Timestamp with offset: thời điểm có offset.
- UTC instant: thời điểm chuẩn UTC.

Không bỏ timezone khi ý nghĩa là một instant. Trong Oracle, chọn DATE, TIMESTAMP hoặc TIMESTAMP WITH TIME ZONE theo contract; parse bằng format mask tường minh, không phụ thuộc NLS_DATE_FORMAT.

### 5.3. Boolean và enum

Contract phải xác định boolean chỉ nhận true/false, không chấp nhận chuỗi "true", 1, "Y" trừ khi có quy tắc mapping. Enum nên có chính sách unknown value: reject, map sang UNKNOWN hay giữ nguyên chuỗi để forward compatibility.

### 5.4. Identifier

ID dạng mã nghiệp vụ thường nên là string để bảo toàn số 0 đầu, dấu gạch và không bị giới hạn precision số. Không dùng JSON number cho mã tài khoản hoặc mã đơn hàng nếu nó không mang ý nghĩa số học.

### 5.5. Array cardinality

Với mỗi array, xác định:

- Min items và max items.
- Phần tử có được trùng không?
- Thứ tự có ý nghĩa không?
- Có cho phép array rỗng không?
- Mỗi phần tử có khóa duy nhất nào?

Ví dụ items có max 500 phần tử và sku không được trùng trong một order. Đây là quy tắc schema/nghiệp vụ cần được kiểm tra rõ.

## 6. Thiết kế JSON contract

### 6.1. Object và array

Object biểu diễn một thực thể có field đặt tên; array biểu diễn danh sách có thứ tự. Không dùng object key động làm nơi chứa danh sách nếu consumer cần lặp theo phần tử và xác thực cardinality.

Ví dụ:

```json
{
  "customer": {
    "customerId": "C-100",
    "name": "Nguyen An"
  },
  "addresses": [
    {
      "type": "BILLING",
      "countryCode": "VN"
    },
    {
      "type": "SHIPPING",
      "countryCode": "VN"
    }
  ]
}
```

### 6.2. Quy tắc tên field

Chọn một convention nhất quán, ví dụ camelCase hoặc snake_case. Không đổi convention tùy endpoint. Tên field nên mô tả ý nghĩa, tránh abbreviation khó hiểu và tránh dùng tên SQL reserved word nếu thường xuyên map trực tiếp.

### 6.3. Không nhồi nhiều kiểu vào một field

Tránh contract kiểu customerId lúc là number, lúc là string. Consumer phải đoán kiểu. Nếu định dạng identifier thay đổi, phát hành version mới hoặc field mới có migration rõ ràng.

### 6.4. Tách metadata khỏi payload nghiệp vụ

Một envelope có thể chứa:

```json
{
  "schemaVersion": "1.0",
  "eventId": "evt-123",
  "eventType": "DocumentUploaded",
  "occurredAt": "2026-11-14T08:30:00Z",
  "correlationId": "corr-456",
  "payload": {
    "documentId": "DOC-100",
    "fileName": "manual.pdf"
  }
}
```

Metadata hỗ trợ routing, deduplication, tracing và versioning. Không nhét credential, secret hoặc thông tin xác thực vào payload/log.

### 6.5. JSON Schema ở tầng contract

JSON Schema thường được dùng ở API gateway hoặc application layer để mô tả type, required, enum, pattern, min/max, array cardinality và nested structure. Ví dụ:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schemaVersion", "orderId", "items"],
  "additionalProperties": false,
  "properties": {
    "schemaVersion": {"type": "string", "const": "1.0"},
    "orderId": {"type": "string", "minLength": 1, "maxLength": 40},
    "items": {
      "type": "array",
      "minItems": 1,
      "maxItems": 500,
      "items": {
        "type": "object",
        "required": ["sku", "quantity"],
        "properties": {
          "sku": {"type": "string", "maxLength": 40},
          "quantity": {"type": "integer", "minimum": 1}
        },
        "additionalProperties": false
      }
    }
  }
}
```

Đây là ví dụ JSON Schema ở tầng contract; không giả định mọi phiên bản Oracle có hàm SQL built-in thực thi trực tiếp JSON Schema draft này. Oracle SQL/JSON có thể kiểm tra cú pháp và trích xuất/kiểm tra một số kiểu; validation schema đầy đủ có thể nằm ở application/gateway hoặc cơ chế được hỗ trợ riêng.

## 7. Kiểm soát JSON trong Oracle Database

### 7.1. Lưu JSON bằng VARCHAR2/CLOB/BLOB

Ở các phiên bản chưa có native JSON datatype, có thể lưu JSON trong VARCHAR2, CLOB hoặc BLOB và thêm constraint IS JSON:

```sql
CREATE TABLE lab_json_events (
    event_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_lab_json_events_payload
        CHECK (payload IS JSON)
);
```

Constraint giúp database từ chối document không parse được theo quy tắc IS JSON. Nó không thay thế validation nghiệp vụ như required field, min/max, enum hoặc cross-field rule.

### 7.2. STRICT và UNIQUE KEYS

Oracle IS JSON hỗ trợ các tùy chọn kiểm tra cú pháp nghiêm ngặt và key duy nhất trong object:

```sql
CREATE TABLE lab_json_strict (
    id NUMBER PRIMARY KEY,
    payload CLOB,
    CONSTRAINT ck_lab_json_strict
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
```

STRICT yêu cầu cú pháp JSON nghiêm ngặt hơn chế độ lax mặc định của Oracle trong một số ngữ cảnh. WITH UNIQUE KEYS yêu cầu object không có duplicate key. Điều này quan trọng vì các parser khác nhau có thể xử lý duplicate key khác nhau (lấy key đầu, key cuối hoặc báo lỗi); contract nên từ chối duplicate keys để tránh diễn giải khác nhau giữa producer, gateway và database.

Kiểm tra:

```sql
SELECT id
FROM lab_json_strict
WHERE payload IS JSON STRICT WITH UNIQUE KEYS;
```

### 7.3. Native JSON datatype

Oracle Database 21c giới thiệu kiểu JSON native, lưu biểu diễn JSON nhị phân tối ưu (OSON) trong database:

```sql
CREATE TABLE lab_json_native (
    event_id NUMBER PRIMARY KEY,
    payload JSON
);
```

Native JSON datatype tự đảm bảo dữ liệu lưu là JSON hợp lệ theo khả năng của kiểu; không cần constraint IS JSON như khi lưu raw text. Cú pháp, storage behavior và khả năng client binding phụ thuộc phiên bản/driver.

Nếu cần tương thích nhiều release hoặc trao đổi raw text, CLOB/BLOB kèm IS JSON vẫn là lựa chọn phổ biến.

### 7.4. JSON trong BLOB và encoding

Khi lưu JSON trong BLOB, contract cần xác định encoding. Oracle SQL/JSON xử lý JSON trong BLOB theo yêu cầu encoding được hỗ trợ (thông thường UTF-8). Không đưa byte từ encoding tùy ý vào BLOB rồi giả định parser sẽ tự đoán đúng.

Nếu ứng dụng nhận HTTP body dạng byte, giữ nguyên bytes cho đến khi xác định encoding hợp lệ; decode đúng một lần và reject byte sequence không hợp lệ. Tránh decode bằng replacement character rồi tiếp tục vì payload có thể bị thay đổi âm thầm.

### 7.5. Không coi IS JSON là schema validation

IS JSON kiểm tra tính hợp lệ JSON theo điều kiện đã chọn. Nó không chứng minh:

- Có field orderId.
- orderId là string không rỗng.
- items là array có ít nhất một phần tử.
- quantity là integer dương.
- currency nằm trong danh sách hỗ trợ.
- Các trường có quan hệ logic đúng.

Kết hợp JSON Schema ở tầng ứng dụng hoặc kiểm tra bằng SQL/PLSQL có chủ đích.

## 8. SQL/JSON functions: trích xuất và kiểm tra

### 8.1. JSON_VALUE

JSON_VALUE trích xuất một scalar từ JSON path:

```sql
SELECT JSON_VALUE(
           payload,
           '$.orderId'
           RETURNING VARCHAR2(40)
           ERROR ON ERROR
           NULL ON EMPTY
       ) AS order_id
FROM lab_json_events;
```

RETURNING xác định kiểu kết quả SQL. ERROR ON ERROR giúp không âm thầm biến dữ liệu sai thành NULL; NULL ON EMPTY quy định field không có path trả NULL. Chọn ON ERROR/ON EMPTY theo contract, không dựa vào default ngầm.

### 8.2. JSON_EXISTS

JSON_EXISTS kiểm tra path có tồn tại và có match:

```sql
SELECT event_id
FROM lab_json_events
WHERE JSON_EXISTS(payload, '$.orderId');
```

Dùng JSON_EXISTS để phân biệt field missing với một số trường hợp JSON null. Nếu cần phân biệt sâu hơn, kết hợp JSON_VALUE/JSON_QUERY và quy tắc ON EMPTY/ON ERROR, rồi kiểm tra trên release cụ thể.

### 8.3. JSON_QUERY

JSON_QUERY lấy object hoặc array:

```sql
SELECT JSON_QUERY(
           payload,
           '$.items'
           RETURNING CLOB
           ERROR ON ERROR
       ) AS items_json
FROM lab_json_events;
```

JSON_QUERY hữu ích khi cần giữ nguyên một cấu trúc JSON con thay vì ép thành scalar.

### 8.4. JSON_TABLE

JSON_TABLE biến JSON document thành hàng/cột quan hệ:

```sql
SELECT
    e.event_id,
    jt.order_id,
    jt.item_sku,
    jt.quantity
FROM lab_json_events e,
     JSON_TABLE(
         e.payload,
         '$'
         COLUMNS (
             order_id VARCHAR2(40)
                 PATH '$.orderId'
                 ERROR ON ERROR,
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_sku VARCHAR2(40) PATH '$.sku',
                 quantity NUMBER PATH '$.quantity'
                     ERROR ON ERROR
             )
         )
     ) jt;
```

JSON_TABLE hỗ trợ chiếu cấu trúc nested thành quan hệ SQL, thuận tiện cho join, filter và insert. Đặt RETURNING/column datatype và error handling rõ ràng để tránh ép kiểu không mong muốn.

### 8.5. JSON_VALUE và kiểu number

Nếu field quantity phải là NUMBER:

```sql
SELECT JSON_VALUE(
           payload,
           '$.quantity'
           RETURNING NUMBER
           ERROR ON ERROR
       )
FROM lab_json_events;
```

Sau khi parse được NUMBER, vẫn cần kiểm tra miền nghiệp vụ, ví dụ quantity > 0 và không vượt ngưỡng. JSON_VALUE không thay thế CHECK constraint hoặc business validation.

### 8.6. ON ERROR và ON EMPTY

Các hành vi phổ biến gồm:

| Clause | Ý nghĩa |
| --- | --- |
| ERROR ON ERROR | Báo lỗi nếu JSON/path/type conversion có lỗi theo điều kiện |
| NULL ON ERROR | Trả SQL NULL trong trường hợp lỗi được clause xử lý |
| DEFAULT ... ON ERROR | Trả default khi lỗi, nếu cú pháp/release hỗ trợ |
| ERROR ON EMPTY | Báo lỗi nếu path không tìm thấy giá trị |
| NULL ON EMPTY | Trả NULL khi path không tồn tại |
| DEFAULT ... ON EMPTY | Trả default khi path không tồn tại |

Nếu dùng NULL ON ERROR cho mọi field, dữ liệu sai có thể biến thành NULL rồi lọt vào hệ thống. Với trường bắt buộc hoặc dữ liệu tài chính, ưu tiên ERROR ON ERROR và ERROR ON EMPTY hoặc validate riêng trước khi lưu.

### 8.7. JSON_OBJECT và JSON_ARRAY

Oracle có các hàm sinh JSON từ SQL:

```sql
SELECT JSON_OBJECT(
           'orderId' VALUE order_id,
           'status' VALUE status,
           'amount' VALUE total_amount
           RETURNING CLOB
       ) AS order_json
FROM lab_orders;
```

RETURNING CLOB phù hợp khi output có thể vượt giới hạn VARCHAR2. Dùng FORMAT JSON khi một giá trị đầu vào đã là JSON và cần nhúng dưới dạng JSON object/array thay vì quote thành string; chỉ dùng khi nguồn đã được xác thực.

## 9. Kiểm tra cấu trúc JSON và quy tắc nghiệp vụ

### 9.1. Kiểm tra field bắt buộc

Có thể kết hợp JSON_EXISTS:

```sql
SELECT event_id
FROM lab_json_events
WHERE NOT JSON_EXISTS(payload, '$.orderId')
   OR NOT JSON_EXISTS(payload, '$.items');
```

Đây là kiểm tra sự hiện diện. Tiếp theo phải kiểm tra type, null, length và domain.

### 9.2. Kiểm tra array

Có thể dùng JSON_TABLE để đếm số phần tử:

```sql
SELECT e.event_id, COUNT(jt.sku) AS item_count
FROM lab_json_events e,
     JSON_TABLE(
         e.payload,
         '$.items[*]'
         COLUMNS (
             sku VARCHAR2(40) PATH '$.sku'
         )
     ) jt
GROUP BY e.event_id
HAVING COUNT(jt.sku) > 500;
```

Nếu cần reject array rỗng, kiểm tra count bằng 0 hoặc JSON_EXISTS path phù hợp. Cẩn thận outer/inner semantics của JSON_TABLE: document không có array có thể tạo 0 row hoặc NULL row tùy cách viết NESTED PATH.

### 9.3. Kiểm tra domain

Ví dụ quantity phải là số dương:

```sql
SELECT e.event_id, jt.quantity
FROM lab_json_events e,
     JSON_TABLE(
         e.payload,
         '$.items[*]'
         COLUMNS (
             quantity NUMBER PATH '$.quantity'
                 ERROR ON ERROR
         )
     ) jt
WHERE jt.quantity <= 0;
```

Trong production, không nên để một query báo lỗi conversion cho toàn batch mà không biết document nào sai. Có thể validate từng payload ở ingress, hoặc dùng pipeline staging để phân loại lỗi theo event_id.

### 9.4. Duplicate keys

JSON object không nên có key trùng. Ví dụ:

```json
{"role": "user", "role": "admin"}
```

Các parser có thể xử lý khác nhau. Một layer có thể lấy giá trị đầu, layer khác lấy giá trị cuối. Dùng STRICT WITH UNIQUE KEYS khi lưu raw text ở Oracle và cấu hình parser/gateway từ chối duplicate key ngay khi nhận.

### 9.5. Unknown fields

Contract phải quy định unknown field:

- Reject nếu muốn contract khép kín và tránh typo.
- Ignore nếu muốn forward compatibility.
- Preserve nếu cần round-trip hoặc proxy payload.

Không mặc định Oracle JSON parser sẽ thực thi quy tắc additionalProperties như JSON Schema. Đây là quyết định của validator/application contract.

### 9.6. Kiểm tra cross-field

Ví dụ totalAmount phải bằng tổng quantity × unitPrice:

```sql
SELECT e.event_id
FROM lab_json_events e
WHERE JSON_VALUE(e.payload, '$.totalAmount' RETURNING NUMBER)
      <>
      (
          SELECT SUM(jt.quantity * jt.unit_price)
          FROM JSON_TABLE(
              e.payload,
              '$.items[*]'
              COLUMNS (
                  quantity NUMBER PATH '$.quantity',
                  unit_price NUMBER PATH '$.unitPrice'
              )
          ) jt
      );
```

Đây là ví dụ logic; cần xác định rounding, currency scale, empty array và null behavior. Với giá trị tiền, dùng NUMBER và quy tắc rounding rõ ràng.

## 10. Thiết kế XML contract

### 10.1. Element và attribute

XML có thể biểu diễn dữ liệu bằng element hoặc attribute:

```xml
<Order orderId="ORD-100">
  <CreatedAt>2026-11-14T08:30:00Z</CreatedAt>
  <Items>
    <Item>
      <Sku>KB-001</Sku>
      <Quantity>2</Quantity>
    </Item>
  </Items>
</Order>
```

Quy định nhất quán field nào là element, field nào là attribute. Dữ liệu lặp thường biểu diễn bằng nhiều element cùng tên; không encode danh sách bằng chuỗi phân cách dấu phẩy nếu cần kiểm tra kiểu và cardinality.

### 10.2. XML declaration và encoding

XML có thể khai báo version và encoding:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Order>
  <OrderId>ORD-100</OrderId>
</Order>
```

Encoding trong declaration phải khớp byte stream thực tế. Nếu HTTP header, BOM và XML declaration mâu thuẫn, parser có thể từ chối hoặc diễn giải khác nhau. Chuẩn hóa một encoding được hỗ trợ, thường UTF-8, và validate byte sequence trước khi xử lý.

### 10.3. Namespace

Namespace phân biệt các vocabulary XML có cùng local name:

```xml
<Order xmlns="urn:example:orders:v1">
  <OrderId>ORD-100</OrderId>
</Order>
```

Khi query XML bằng XPath/XQuery, namespace phải được khai báo và gắn đúng prefix. Prefix trong document không nhất thiết phải giống prefix trong query; namespace URI mới là định danh.

### 10.4. XSD

XML Schema (XSD) mô tả:

- Element/attribute và kiểu dữ liệu.
- MinOccurs/MaxOccurs.
- Required/optional.
- Simple type restriction, pattern, min/max.
- Sequence/choice và thứ tự element.
- Namespace/targetNamespace.
- Nillable và quy tắc xsi:nil.

Ví dụ XSD đơn giản:

```xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           xmlns="urn:example:orders:v1"
           elementFormDefault="qualified">
  <xs:element name="Order">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="OrderId" type="xs:string"/>
        <xs:element name="Quantity" type="xs:positiveInteger"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

XSD xác thực cấu trúc và kiểu; business rules như order thuộc customer nào hoặc tổng tiền có đúng không vẫn có thể cần validation riêng.

### 10.5. Missing, empty element và xsi:nil

Các dạng sau có ý nghĩa khác nhau:

```xml
<Order/>
```

```xml
<Order><Note/></Order>
```

```xml
<Order xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Note xsi:nil="true"/>
</Order>
```

- Element missing: không có node Note.
- Empty element: có node Note nhưng nội dung rỗng.
- xsi:nil="true": element có mặt và được khai báo nil nếu XSD cho phép nillable.

Contract cần quy định ý nghĩa từng trường hợp. Không coi empty element tự động là NULL.

### 10.6. XML whitespace và canonicalization

Whitespace có thể có ý nghĩa trong text node, mixed content, signature hoặc canonicalization. Không xóa whitespace toàn document một cách mù quáng. Nếu chữ ký XML hoặc hash dựa trên canonical form, phải dùng quy trình canonicalization đúng chuẩn và giữ namespace/attribute semantics.

## 11. Oracle XMLType và XML DB

### 11.1. Lưu XML bằng XMLType

Oracle cung cấp XMLType để lưu và xử lý XML:

```sql
CREATE TABLE lab_xml_messages (
    message_id NUMBER PRIMARY KEY,
    payload XMLTYPE,
    received_at TIMESTAMP
);
```

XMLType có thể được lưu theo các mô hình storage khác nhau tùy release và DDL. Khi thiết kế bảng lớn, cân nhắc binary XML, SecureFiles LOB hoặc storage model được hỗ trợ; không mặc định mọi XMLType đều được lưu giống CLOB.

### 11.2. Tạo XMLType từ string

```sql
INSERT INTO lab_xml_messages (
    message_id,
    payload,
    received_at
)
VALUES (
    1,
    XMLTYPE(
        '<Order><OrderId>ORD-100</OrderId></Order>'
    ),
    SYSTIMESTAMP
);
```

Trong hệ thống thật, bind payload qua driver thay vì nối string vào SQL text. Nếu đầu vào không tin cậy, validate XML và parser policy trước khi lưu.

### 11.3. Kiểm tra XML well-formed

XMLType constructor/parser kiểm tra well-formedness khi tạo XMLType từ nội dung XML. Document sai tag nesting, ký tự không hợp lệ hoặc cấu trúc XML không hợp lệ sẽ gây lỗi parse.

Well-formed không có nghĩa valid theo XSD hay đúng nghiệp vụ.

### 11.4. XMLIsValid và schema validation

Oracle XML DB hỗ trợ XML Schema-based XMLType và các API kiểm tra schema. Quy trình thường gồm đăng ký XML Schema trong XML DB, tạo XMLType schema-based hoặc validate document theo schema đã đăng ký. API cụ thể (XMLIsValid, schemaValidate hoặc phương thức XMLType) có khác biệt theo release; kiểm tra SQL Reference/XML DB Developer's Guide của phiên bản.

Không tự viết một hàm chỉ kiểm tra tag tồn tại rồi gọi đó là XSD validation. Nếu contract yêu cầu XSD, dùng validator XML Schema thực sự.

### 11.5. Trích xuất bằng XMLQuery/XMLCast

XMLQuery thực thi XQuery trên XMLType; XMLCast chuyển kết quả XML sang kiểu SQL:

```sql
SELECT XMLCAST(
           XMLQUERY(
               'declare default element namespace "urn:example:orders:v1";
                /Order/OrderId/text()'
               PASSING payload
               RETURNING CONTENT
           )
           AS VARCHAR2(40)
       ) AS order_id
FROM lab_xml_messages;
```

Ví dụ giả định document có default namespace URI tương ứng. Nếu không khai báo namespace đúng, XPath có thể không match dù local name nhìn giống nhau.

### 11.6. XMLExists

XMLExists kiểm tra XQuery có trả về item nào không:

```sql
SELECT message_id
FROM lab_xml_messages
WHERE XMLEXISTS(
    'declare default element namespace "urn:example:orders:v1";
     /Order/OrderId'
    PASSING payload
);
```

XMLExists hữu ích trong WHERE; nó không thay thế schema validation.

### 11.7. XMLTable

XMLTable ánh xạ XML nodes thành hàng/cột:

```sql
SELECT
    m.message_id,
    x.order_id,
    x.quantity
FROM lab_xml_messages m,
     XMLTABLE(
         XMLNAMESPACES(
             DEFAULT 'urn:example:orders:v1'
         ),
         '/Order'
         PASSING m.payload
         COLUMNS
             order_id VARCHAR2(40) PATH 'OrderId',
             quantity NUMBER PATH 'Quantity'
     ) x;
```

XMLTable phù hợp để chuyển XML thành quan hệ SQL, join với bảng khác và nạp dữ liệu. Định nghĩa datatype cột và xử lý conversion/error rõ ràng.

## 12. Kiểm soát kích thước và tài nguyên

### 12.1. Giới hạn ở nhiều tầng

Một giới hạn payload an toàn cần áp dụng ở nhiều tầng:

1. HTTP/API gateway: giới hạn Content-Length và streaming bytes.
2. Application ingress: giới hạn byte, timeout, rate và concurrent uploads.
3. Parser: giới hạn nesting depth, token count, element count và string length.
4. Contract validator: giới hạn array cardinality, field length và domain.
5. Database: chọn datatype/storage, constraint, quota và transaction policy.
6. Downstream: giới hạn số hàng được tạo từ JSON_TABLE/XMLTABLE và kích thước output.

Chỉ kiểm tra sau khi đã đọc toàn bộ payload vào RAM là quá muộn đối với payload cực lớn. Áp dụng byte limit trong lúc streaming.

### 12.2. Kích thước byte và ký tự khác nhau

Một string 1000 ký tự Unicode có thể cần nhiều hơn 1000 bytes khi mã hóa UTF-8. Vì vậy cần phân biệt:

- Wire size: số byte nhận qua network.
- Character length: số ký tự theo semantics contract.
- Database byte length: số byte sau khi chuyển character set.
- Serialized size: kích thước JSON/XML sau khi serialize/escape.

Giới hạn API thường cần byte limit để bảo vệ network/memory và character limit để bảo vệ field semantics.

### 12.3. VARCHAR2 và CLOB

Trong SQL, giới hạn VARCHAR2 phụ thuộc MAX_STRING_SIZE:

- STANDARD: tối đa 4000 bytes cho VARCHAR2 SQL.
- EXTENDED: có thể tới 32767 bytes cho VARCHAR2 SQL, tùy cấu hình.

PL/SQL VARCHAR2 có giới hạn tối đa 32767 bytes. Không dùng VARCHAR2 để giữ toàn bộ payload lớn hơn giới hạn. CLOB phù hợp cho văn bản lớn; BLOB phù hợp cho bytes/raw payload.

Khi dùng JSON/XML output, chọn RETURNING CLOB hoặc datatype phù hợp nếu có thể vượt VARCHAR2. Tránh implicit conversion cắt cụt hoặc phát sinh ORA-06502/ORA-01489.

### 12.4. JSON native datatype

Native JSON datatype ở Oracle 21c+ dùng biểu diễn binary JSON và không bị giới hạn như một VARCHAR2 scalar. Tuy nhiên vẫn phải đặt application-level payload size, document complexity, number of fields và resource budget. Kiểu dữ liệu lớn không có nghĩa payload vô hạn là an toàn.

### 12.5. Giới hạn độ sâu lồng

JSON/XML có thể lồng nhiều cấp. Độ sâu quá lớn làm tăng chi phí parser, recursive traversal, stack và memory. Đặt max depth theo contract, ví dụ 32 hoặc 64 cấp tùy ứng dụng, và reject trước khi chạy logic đệ quy nặng.

Không chọn max depth chỉ theo parser tối đa; cần chọn theo cấu trúc nghiệp vụ thực tế và kiểm thử.

### 12.6. Giới hạn số phần tử và token

Một payload nhỏ về byte vẫn có thể chứa hàng trăm nghìn object rất nhỏ. Giới hạn:

- Tổng số JSON nodes/tokens.
- Số phần tử trong mỗi array.
- Tổng số XML elements/attributes.
- Số object con.
- Số hàng JSON_TABLE/XMLTABLE tạo ra.

Điều này bảo vệ database khỏi fan-out quá lớn khi một document biến thành nhiều hàng quan hệ.

### 12.7. Giới hạn string và attribute

Đặt max length cho:

- ID, code, name và description.
- URL, email và external reference.
- XML attribute và text node.
- Error message và metadata.

Không cho một field description nhận hàng MB nếu nghiệp vụ chỉ cần vài trăm ký tự. Nội dung lớn nên chuyển sang LOB/document storage riêng.

### 12.8. Timeout và concurrency

Giới hạn payload cần đi cùng timeout parse/validation, request timeout, maximum concurrent requests và rate limit theo caller. Nếu chỉ có byte limit mà không có timeout, payload chậm (slow upload) vẫn có thể giữ connection và resource lâu.

### 12.9. Output size

Query sinh JSON/XML cũng có thể tạo output lớn hơn input, đặc biệt khi join tạo lặp dữ liệu hoặc XML/JSON aggregate. Đặt giới hạn result size, paging, streaming và max rows. Không serialize toàn bộ bảng vào một CLOB chỉ vì database có thể làm được.

## 13. Lưu payload lớn và streaming

### 13.1. Chọn datatype theo nội dung

| Nội dung | Kiểu lưu phù hợp |
| --- | --- |
| JSON nhỏ cần truy vấn thường xuyên | JSON native hoặc VARCHAR2/CLOB kèm IS JSON |
| JSON lớn dạng text | CLOB hoặc BLOB UTF-8 theo contract |
| XML lớn | XMLType hoặc CLOB tùy nhu cầu XML DB/query |
| File nhị phân | BLOB |
| File bên ngoài database chỉ cần tham chiếu | BFILE |
| Dữ liệu trung gian để ghép/transform | Temporary CLOB/BLOB |

Đánh giá indexing, query patterns, retention, backup, compression, SecureFiles và driver support.

### 13.2. Streaming thay vì materialize toàn bộ

Ứng dụng nên stream payload từ HTTP body tới parser/LOB API theo buffer giới hạn. Tránh:

1. Đọc toàn bộ file vào byte array.
2. Decode toàn bộ thành string.
3. Tạo thêm bản sao khi serialize.
4. Bind thêm một bản sao vào database.

Chuỗi các bản sao có thể làm memory usage tăng gấp nhiều lần payload.

### 13.3. Temporary LOB

Temporary LOB có thể dùng để tạo nội dung trung gian:

```sql
DECLARE
    l_json CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_json,
        cache => TRUE,
        dur => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_json,
        LENGTH('{"status":"ready"}'),
        '{"status":"ready"}'
    );

    -- Dùng l_json cho bước tiếp theo.
    DBMS_LOB.FREETEMPORARY(l_json);
END;
/
```

Giải phóng temporary LOB trong cả đường thành công và exception. Với nội dung lớn, theo dõi TEMP usage và không giữ SESSION-duration LOB không cần thiết.

### 13.4. Staging table

Với payload lớn hoặc cần kiểm tra nhiều bước, dùng staging table:

```sql
CREATE TABLE lab_payload_stage (
    payload_id NUMBER PRIMARY KEY,
    payload_type VARCHAR2(10) NOT NULL,
    payload_body CLOB,
    validation_status VARCHAR2(20) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    error_code VARCHAR2(50),
    error_detail VARCHAR2(1000)
);
```

Nạp raw payload vào staging, validate cú pháp/schema/domain/resource, sau đó chuyển dữ liệu hợp lệ vào bảng nghiệp vụ. Dữ liệu lỗi được giữ ở trạng thái REJECTED/QUARANTINED theo chính sách retention.

## 14. Xử lý dữ liệu không hợp lệ

### 14.1. Phân loại lỗi

Không gom mọi trường hợp vào một mã lỗi INVALID_DATA. Phân loại giúp caller sửa payload đúng cách:

| Nhóm lỗi | Ví dụ | Có nên retry nguyên payload? |
| --- | --- | --- |
| Syntax | JSON thiếu dấu ngoặc, XML sai nesting | Không; producer phải sửa |
| Encoding | UTF-8 byte sequence không hợp lệ | Không; gửi lại đúng encoding |
| Schema/structure | Thiếu orderId, items sai kiểu | Không; sửa contract payload |
| Domain | quantity âm, currency không hỗ trợ | Không nếu dữ liệu nghiệp vụ không đổi |
| Reference | customerId không tồn tại | Có thể retry nếu dependency được tạo sau, theo policy |
| Conflict | version đã thay đổi, event trùng | Xử lý theo idempotency/concurrency |
| Resource | payload vượt size/depth/timeout | Chỉ retry sau khi giảm payload hoặc thay đổi giới hạn có kiểm soát |
| Infrastructure | database unavailable, network timeout | Có thể retry với backoff và idempotency |

### 14.2. Reject sớm

Kiểm tra ở ingress trước khi:

- Nạp toàn bộ payload vào memory.
- Parse nested structure lớn.
- Gọi SQL/JSON hoặc XMLTable tạo hàng.
- Lấy row lock hoặc mở transaction dài.
- Gọi service phụ thuộc.

Reject sớm giúp tiết kiệm CPU, memory, TEMP, undo và connection.

### 14.3. Validate theo thứ tự

Một pipeline hợp lý:

1. Kiểm tra HTTP content type, encoding và byte limit.
2. Parse syntax JSON/XML an toàn.
3. Kiểm tra document depth, token/element count và string length.
4. Validate schema/version.
5. Validate type, required/null, format và cardinality.
6. Validate domain và cross-field rules.
7. Kiểm tra reference, uniqueness và authorization.
8. Chuyển dữ liệu vào staging hoặc bảng nghiệp vụ trong transaction có kiểm soát.

Không chạy bước tốn kém trước khi biết payload có vượt giới hạn cơ bản hay không.

### 14.4. Error response có cấu trúc

Ví dụ response lỗi:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Payload does not match the order contract.",
    "correlationId": "corr-456",
    "details": [
      {
        "path": "$.items[0].quantity",
        "rule": "minimum",
        "expected": ">= 1"
      }
    ]
  }
}
```

Không trả raw stack trace, SQL text, filesystem path, schema internals hoặc thông tin nhạy cảm cho caller. Có thể trả nhiều lỗi validation nếu an toàn và hữu ích, nhưng giới hạn số lỗi để response không phình lớn.

### 14.5. Không biến lỗi thành default âm thầm

Ví dụ JSON_VALUE NULL ON ERROR có thể khiến quantity sai kiểu trở thành NULL. Nếu sau đó code dùng NVL(quantity, 1), một payload sai có thể được chấp nhận như quantity = 1.

Chỉ dùng default khi contract định nghĩa rõ; không dùng default để che lỗi parse, conversion hoặc field bắt buộc bị thiếu.

### 14.6. Reject hay quarantine?

- Reject: từ chối ngay, trả lỗi cho producer.
- Quarantine: giữ raw payload trong vùng cách ly để điều tra hoặc retry có kiểm soát.
- Accept with warning: chỉ dùng khi contract cho phép và warning được ghi rõ.

Quarantine cần retention, access control, encryption, masking và quy trình xóa. Không lưu vô hạn payload chứa dữ liệu cá nhân hoặc bí mật.

## 15. Duplicate, idempotency và dữ liệu lặp

### 15.1. Duplicate event

Producer có thể retry do timeout dù consumer đã commit. Nếu không có idempotency, cùng một event có thể tạo đơn hàng hoặc thanh toán hai lần.

Contract event nên có eventId duy nhất trong phạm vi xác định. Database có thể bảo vệ bằng unique constraint:

```sql
CREATE TABLE lab_processed_events (
    event_id VARCHAR2(100) PRIMARY KEY,
    payload_hash VARCHAR2(128),
    processed_at TIMESTAMP NOT NULL
);
```

Trong transaction xử lý event, insert eventId trước hoặc cùng với business DML; unique violation cho biết event đã được xử lý hoặc đang tranh chấp. Cần định nghĩa cách so sánh payload hash nếu cùng eventId nhưng nội dung khác nhau.

### 15.2. Idempotent processing

Một thao tác idempotent có thể được lặp lại mà không tạo thêm hiệu ứng nghiệp vụ ngoài mong muốn. Thiết kế thường gồm:

- eventId/requestId ổn định qua retry.
- Unique constraint ở database.
- Trạng thái xử lý và kết quả đã commit.
- Payload hash để phát hiện cùng ID nhưng khác nội dung.
- Transaction bao gồm đánh dấu processed và business update.

Không chỉ kiểm tra SELECT trước INSERT; hai session có thể cùng thấy chưa có hàng. Unique constraint là lớp bảo vệ concurrency cuối cùng.

### 15.3. Duplicate keys trong JSON

Duplicate object keys khác duplicate eventId. Ví dụ cùng object có hai key orderId. Từ chối duplicate keys trước khi diễn giải để mọi parser thống nhất.

### 15.4. Duplicate XML elements

XML có thể có nhiều element cùng tên hợp lệ nếu XSD cho phép maxOccurs lớn hơn 1. Phải phân biệt:

- Repeated element được contract cho phép (ví dụ nhiều Item).
- Element trùng không được phép (ví dụ chỉ một OrderId).
- Attribute trùng tên trong cùng element không well-formed XML.

XSD cardinality và application validation quyết định điều gì hợp lệ.

## 16. Encoding, Unicode và normalization

### 16.1. UTF-8

Với API JSON/XML, UTF-8 thường là lựa chọn tốt vì tương thích rộng. Contract nên ghi rõ encoding và quy tắc nhận byte stream. Không tự đoán encoding theo nội dung nếu có thể xác định qua protocol/declaration.

### 16.2. Character count và byte count

Ký tự Unicode có thể chiếm nhiều byte. Ví dụ tiếng Việt có dấu có thể được biểu diễn bằng ký tự dựng sẵn hoặc chuỗi combining mark; hai chuỗi có thể nhìn giống nhau nhưng byte sequence khác.

Nếu contract so sánh độ dài:

- Giới hạn request bằng byte để bảo vệ transport/memory.
- Giới hạn field bằng ký tự theo quy tắc rõ.
- Xác định có chuẩn hóa Unicode NFC/NFD hay không.
- Không tự thay đổi nội dung nếu chữ ký/hash phụ thuộc byte gốc.

### 16.3. Unicode normalization

Hai chuỗi nhìn giống nhau có thể khác code point sequence. Nếu identifier/email/name cần so sánh ổn định, xác định normalization ở tầng contract/application và lưu canonical value phù hợp. Giữ raw value nếu cần audit hoặc chứng minh dữ liệu ban đầu.

### 16.4. Escaping

JSON dùng escape cho quote, backslash và control characters. XML dùng escaping cho các ký tự đặc biệt trong text/attribute; không nối string trực tiếp để tự tạo document. Dùng serializer chuẩn để escape đúng và tránh injection.

### 16.5. Không decode/re-encode tùy tiện

Nếu payload được ký số hoặc có checksum, bất kỳ bước decode, normalize newline, reorder property hay reserialize nào cũng có thể làm thay đổi bytes. Xác định chữ ký được tính trên raw bytes, canonical JSON/XML hay semantic object; dùng đúng canonicalization scheme và không tự tạo quy tắc riêng.

## 17. Bảo mật parser JSON/XML

### 17.1. JSON parser limits

JSON parser cần giới hạn:

- Tổng byte đầu vào.
- Maximum nesting depth.
- Tổng số token/node.
- Số phần tử array.
- Độ dài string/key.
- Thời gian parse và số request đồng thời.

Không để payload có object lồng hàng nghìn cấp hoặc array khổng lồ làm cạn stack/memory. Kiểm tra duplicate keys và từ chối key không hợp lệ theo contract.

### 17.2. XML External Entity (XXE)

XML parser có thể hỗ trợ DTD và external entity. Nếu parser cho phép resolve external entity từ URL/file, payload không tin cậy có thể cố đọc file nội bộ, truy cập endpoint nội bộ hoặc gây SSRF.

Với XML nhận từ bên ngoài:

- Tắt DTD nếu không cần.
- Tắt external general entities và external parameter entities.
- Không cho parser tự tải external schema/stylesheet từ URL không tin cậy.
- Dùng allowlist schema URI và resolver nội bộ được kiểm soát.
- Giới hạn entity expansion và parser resource.
- Cập nhật thư viện/parser và kiểm thử cấu hình thực tế.

### 17.3. Billion laughs và entity expansion

Một XML document nhỏ có thể khai báo entity lồng nhau khiến parser mở rộng thành lượng nội dung khổng lồ. Đây là dạng resource exhaustion. Tắt DTD/external entity và đặt expansion limit; không chỉ kiểm tra kích thước file gốc.

### 17.4. XInclude và external schema

Kiểm tra parser có bật XInclude, schema location auto-fetch hoặc XSLT document access không. Một tính năng tiện lợi có thể mở ra đường truy cập filesystem/network. Chỉ bật khi thật sự cần và có resolver/allowlist.

### 17.5. XML namespace và signature

XML Signature có thể bị tấn công nếu ứng dụng xác minh một node nhưng xử lý node khác (signature wrapping). Dùng thư viện XML Signature chuẩn, kiểm tra reference URI, node được ký và node được xử lý phải là cùng đối tượng theo contract.

### 17.6. Không log toàn bộ payload theo mặc định

Payload có thể chứa PII, access token, địa chỉ, thông tin tài chính hoặc tài liệu nhạy cảm. Log metadata đủ điều tra như eventId, correlationId, payload size, schemaVersion, hash, error code và path lỗi. Mask hoặc loại bỏ field nhạy cảm; chỉ lưu raw payload ở quarantine có kiểm soát.

## 18. JSON/XML trong transaction Oracle

### 18.1. Validate trước khi ghi dữ liệu chính

Nếu payload cần nhiều bước parse và validate, xử lý trước khi cập nhật bảng nghiệp vụ. Tránh giữ transaction/row lock trong khi parse file lớn hoặc chờ network.

### 18.2. Staging và publish

Một mô hình:

1. Nhận payload vào staging với trạng thái RECEIVED.
2. Ghi byte size, encoding, schema version, event ID và hash.
3. Validate syntax và resource limits.
4. Validate schema/type/domain.
5. Ghi validation result.
6. Chuyển dữ liệu hợp lệ vào bảng nghiệp vụ bằng transaction ngắn.
7. Đánh dấu PUBLISHED/PROCESSED cùng transaction với business DML.
8. Quarantine payload lỗi và áp dụng retention.

### 18.3. Atomicity

Nếu dữ liệu nghiệp vụ được sinh từ JSON_TABLE/XMLTABLE, có thể INSERT ... SELECT vào các bảng đích trong cùng transaction. Nếu một bước thất bại, rollback theo transaction policy để tránh trạng thái nửa vời.

Nếu cần xử lý hàng trăm nghìn phần tử, cân nhắc batch/chunk và trạng thái tiến độ; nhưng khi chia commit, contract cần thể hiện rõ dữ liệu đang xử lý và cách reader tránh nhìn thấy trạng thái chưa hoàn tất.

### 18.4. Không dùng DDL trong transaction ingest

CREATE TABLE, ALTER TABLE và các DDL thường có implicit commit. Không tạo bảng staging động cho từng request trong transaction nghiệp vụ. Chuẩn bị schema staging trước và dùng metadata/request ID để phân vùng logic.

### 18.5. Lock và concurrency

Khi cập nhật cùng một business entity từ nhiều payload, dùng unique key, version column hoặc SELECT FOR UPDATE theo yêu cầu. Không giả định JSON/XML payload lớn tự tạo một đơn vị atomicity độc lập; transaction của database vẫn là ranh giới commit.

## 19. Logging, metrics và observability

### 19.1. Ghi nhận metadata

Một bản ghi ingest log có thể lưu:

- eventId/requestId.
- correlationId/traceId.
- producer và schemaVersion.
- payload format (JSON/XML).
- byte size và số phần tử sau parse.
- checksum/hash.
- trạng thái validate/process.
- error code, error path và timestamp.
- thời gian parse, validate, persist và publish.

### 19.2. Không ghi raw payload vô điều kiện

Raw payload chỉ nên lưu khi có lý do nghiệp vụ/điều tra và có policy bảo vệ. Áp dụng encryption, access control, masking, retention và deletion. Không đưa password, token hoặc dữ liệu thanh toán nhạy cảm vào error log.

### 19.3. Metrics cần theo dõi

- Số payload nhận theo format/version/producer.
- Tỷ lệ syntax/schema/business rejection.
- Phân bố payload size (p50/p95/p99/max).
- Parse/validation latency.
- Số payload bị quarantine.
- Số retry và duplicate event.
- TEMP/PGA/LOB usage và database wait.
- Số hàng được tạo bởi JSON_TABLE/XMLTABLE.

### 19.4. Error path

Path như $.items[3].quantity hoặc XPath /Order/Items/Item[4]/Quantity giúp producer sửa dữ liệu. Không đưa toàn bộ raw value vào log nếu nó có thể chứa PII hoặc secret. Có thể ghi rule name, expected type và vị trí lỗi.

## 20. Bài thực hành JSON trong Oracle

Các ví dụ chạy trong schema lab. Kiểm tra phiên bản Oracle và quyền tạo table trước khi chạy.

### 20.1. Tạo bảng JSON text

```sql
CREATE TABLE lab_contract_json (
    payload_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    received_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_lab_contract_json
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
```

### 20.2. Nạp payload hợp lệ

```sql
INSERT INTO lab_contract_json (payload_id, payload)
VALUES (
    1,
    '{
       "schemaVersion":"1.0",
       "orderId":"ORD-100",
       "items":[
         {"sku":"KB-001","quantity":2,"unitPrice":450000}
       ]
     }'
);
COMMIT;
```

### 20.3. Thử payload sai cú pháp

```sql
INSERT INTO lab_contract_json (payload_id, payload)
VALUES (2, '{"orderId":"ORD-101", "items":[}');
```

Constraint IS JSON phải từ chối payload không parse được. Trong client, ghi nhận lỗi statement cụ thể; không coi insert thất bại là row đã lưu.

### 20.4. Trích xuất scalar

```sql
SELECT
    payload_id,
    JSON_VALUE(
        payload,
        '$.orderId'
        RETURNING VARCHAR2(40)
        ERROR ON ERROR
        NULL ON EMPTY
    ) AS order_id
FROM lab_contract_json;
```

### 20.5. Biến JSON thành rows

```sql
SELECT
    p.payload_id,
    jt.sku,
    jt.quantity,
    jt.unit_price
FROM lab_contract_json p,
     JSON_TABLE(
         p.payload,
         '$.items[*]'
         COLUMNS (
             sku VARCHAR2(40) PATH '$.sku',
             quantity NUMBER PATH '$.quantity' ERROR ON ERROR,
             unit_price NUMBER PATH '$.unitPrice' ERROR ON ERROR
         )
     ) jt;
```

### 20.6. Kiểm tra field bắt buộc và array limit

```sql
SELECT payload_id
FROM lab_contract_json
WHERE NOT JSON_EXISTS(payload, '$.orderId')
   OR NOT JSON_EXISTS(payload, '$.items');

SELECT p.payload_id, COUNT(*) AS item_count
FROM lab_contract_json p,
     JSON_TABLE(
         p.payload,
         '$.items[*]'
         COLUMNS (sku VARCHAR2(40) PATH '$.sku')
     ) jt
GROUP BY p.payload_id
HAVING COUNT(*) > 500;
```

Hai truy vấn minh họa kiểm tra presence và cardinality. Trong pipeline ingest, nên ghi kết quả validation vào trạng thái theo từng payload thay vì chỉ chạy truy vấn phát hiện sau khi đã trộn dữ liệu.

## 21. Bài thực hành XML trong Oracle

### 21.1. Tạo bảng XMLType

```sql
CREATE TABLE lab_contract_xml (
    message_id NUMBER PRIMARY KEY,
    payload XMLTYPE,
    received_at TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

### 21.2. Insert XML well-formed

```sql
INSERT INTO lab_contract_xml (message_id, payload)
VALUES (
    1,
    XMLTYPE(
        '<Order xmlns="urn:example:orders:v1">
           <OrderId>ORD-200</OrderId>
           <Items>
             <Item>
               <Sku>KB-001</Sku>
               <Quantity>2</Quantity>
             </Item>
           </Items>
         </Order>'
    )
);
COMMIT;
```

### 21.3. Trích xuất bằng XMLTable

```sql
SELECT
    m.message_id,
    x.order_id,
    x.sku,
    x.quantity
FROM lab_contract_xml m,
     XMLTABLE(
         XMLNAMESPACES(
             DEFAULT 'urn:example:orders:v1'
         ),
         '/Order'
         PASSING m.payload
         COLUMNS
             order_id VARCHAR2(40) PATH 'OrderId',
             sku VARCHAR2(40) PATH 'Items/Item/Sku',
             quantity NUMBER PATH 'Items/Item/Quantity'
     ) x;
```

### 21.4. Thử sai namespace

Chạy XMLTable với namespace URI khác để quan sát query không match. Local name OrderId giống nhau không đủ; namespace URI phải đúng.

### 21.5. Well-formed và XSD valid

Tạo một document có đủ tag nhưng Quantity bằng số âm. Document có thể well-formed nhưng sai XSD nếu type được khai báo positiveInteger; nếu XSD chỉ khai báo integer thì vẫn cần business validation để kiểm tra > 0.

## 22. Lỗi thường gặp và hướng xử lý

| Triệu chứng/lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| IS JSON constraint fail | JSON syntax không hợp lệ hoặc strict/unique-key rule không thỏa | Parse/validate tại ingress và trả error path |
| JSON_VALUE trả NULL | Field missing, JSON null hoặc NULL ON ERROR/EMPTY | Dùng JSON_EXISTS và error clauses rõ ràng |
| JSON_VALUE conversion error | Scalar sai kiểu hoặc vượt precision | Validate type/domain và chọn RETURNING phù hợp |
| Duplicate JSON key | Producer gửi cùng key nhiều lần | Reject bằng unique-key validation |
| ORA-40441 / JSON parse error | JSON syntax/encoding không hợp lệ | Kiểm tra raw bytes và parser error |
| ORA-06502 | Buffer/variable không đủ hoặc conversion | Dùng CLOB/JSON, buffer đúng và explicit cast |
| ORA-01489 | Kết quả nối chuỗi vượt giới hạn | Dùng CLOB/LOB aggregation phù hợp |
| XML parse error | XML không well-formed hoặc encoding sai | Kiểm tra declaration, byte stream và nesting |
| XMLTable không trả hàng | Namespace URI hoặc XPath sai | Khai báo XMLNAMESPACES và path đúng |
| XSD validation fail | Sai type, required element, cardinality hoặc namespace | Trả validation path và schema version |
| ORA-31011/XML parser error | XML parser không xử lý được document | Kiểm tra well-formedness, encoding và parser settings |
| Payload nhỏ nhưng parse rất lâu | Nesting/entity expansion/token explosion | Đặt depth/token/timeout và XML entity limits |
| Memory/TEMP tăng cao | Materialize payload lớn hoặc temporary LOB không giải phóng | Streaming, batch, free temporary LOB |
| Consumer hiểu khác nhau | Null/missing/duplicate/unknown field chưa được quy định | Siết contract và contract tests |
| Event bị xử lý hai lần | Retry không có idempotency key | eventId unique và transaction deduplication |
| Dữ liệu cũ ghi đè mới | Không có version/concurrency check | Optimistic locking hoặc row lock phù hợp |

## 23. Checklist thiết kế contract

Trước khi đưa một contract JSON/XML vào production, xác nhận:

- [ ] Có owner, producer, consumer và mục đích dữ liệu.
- [ ] Có schemaVersion và chính sách compatibility/deprecation.
- [ ] Có định nghĩa required/optional/nullable.
- [ ] Phân biệt missing, null, empty và default.
- [ ] Có kiểu, format, precision, scale, enum và domain.
- [ ] Có max byte size và max character length.
- [ ] Có max nesting depth, token/node count và array cardinality.
- [ ] Có quy tắc unknown field và duplicate key.
- [ ] Có encoding và Unicode normalization policy.
- [ ] Có JSON Schema/XSD hoặc validator tương ứng.
- [ ] Có validation cross-field và reference.
- [ ] Có parser timeout, concurrency limit và rate limit.
- [ ] XML parser đã tắt DTD/external entity nếu không cần.
- [ ] Có reject/quarantine và retention policy.
- [ ] Có eventId/idempotency và payload hash khi cần.
- [ ] Có error code, error path, correlation ID và metrics.
- [ ] Có test compatibility giữa producer/consumer.
- [ ] Có test payload sát giới hạn và payload độc hại.
- [ ] Có kế hoạch streaming/staging cho payload lớn.
- [ ] Có quyền truy cập, encryption và masking phù hợp.

## 24. Câu hỏi tự kiểm tra

1. Data contract khác kiểm tra JSON syntax như thế nào?
2. Vì sao JSON hợp lệ vẫn có thể sai schema hoặc business rule?
3. Khi nào chọn JSON và khi nào chọn XML?
4. Backward compatibility và forward compatibility khác nhau thế nào?
5. Field missing, JSON null và empty string khác nhau ra sao?
6. Vì sao Oracle SQL có thể làm empty string thành NULL?
7. JSON number cần contract thêm những quy tắc nào cho tiền và identifier?
8. Vì sao phải xác định timezone cho timestamp?
9. IS JSON kiểm tra điều gì và không kiểm tra điều gì?
10. STRICT WITH UNIQUE KEYS giúp tránh vấn đề nào?
11. JSON_VALUE, JSON_EXISTS, JSON_QUERY và JSON_TABLE khác nhau thế nào?
12. ON EMPTY và ON ERROR cần được chọn theo nguyên tắc nào?
13. Vì sao JSON Schema ở application layer không đồng nghĩa Oracle tự validate schema đó?
14. XML well-formed khác XSD valid thế nào?
15. Vì sao namespace URI quan trọng hơn prefix?
16. Missing element, empty element và xsi:nil khác nhau thế nào?
17. XMLType, XMLQuery, XMLExists và XMLTable có vai trò gì?
18. Vì sao giới hạn byte khác giới hạn ký tự?
19. Vì sao cần giới hạn depth, token count và array cardinality?
20. XXE và entity expansion có thể gây rủi ro gì?
21. Vì sao không nên log raw payload theo mặc định?
22. Quarantine khác reject thế nào?
23. eventId và unique constraint hỗ trợ idempotency ra sao?
24. Vì sao staging và streaming hữu ích với payload lớn?
25. Vì sao commit từng chunk cần upload state và publish state?

## 25. Mô hình ghi nhớ

```text
JSON / XML DATA CONTRACT
        |
        v
  Schema + Version + Semantics
        |
        +-- Required / Optional / Null
        +-- Type / Format / Domain
        +-- Compatibility / Unknown fields
        |
        v
  RESOURCE LIMITS
        |
        +-- Bytes / Characters
        +-- Depth / Tokens / Elements
        +-- Array count / String length
        +-- Timeout / Concurrency / Rate
        |
        v
  VALIDATION PIPELINE
        |
        +-- Encoding and syntax
        +-- Schema and type
        +-- Business and reference
        +-- Duplicate / Idempotency
        |
        v
  ORACLE STORAGE / QUERY
        |
        +-- JSON / CLOB / BLOB
        +-- XMLType
        +-- JSON_VALUE / JSON_TABLE
        +-- XMLQuery / XMLTable
        |
        v
  ACCEPT / REJECT / QUARANTINE
        |
        +-- Error code and path
        +-- Correlation ID and metrics
        +-- Staging and atomic publish
        +-- Retention, masking and access control
```

**Điểm cần nhớ:** contract phải định nghĩa cả cấu trúc lẫn ý nghĩa và giới hạn tài nguyên. Parse thành công chỉ chứng minh cú pháp; cần kiểm tra schema, domain, size, depth, cardinality, encoding và concurrency trước khi publish dữ liệu. Trong Oracle, dùng JSON/XML types và SQL operators phù hợp, giữ payload lớn trong LOB/streaming, và tách dữ liệu lỗi vào reject/quarantine có kiểm soát.
