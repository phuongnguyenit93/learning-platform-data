# Lưu JSON trong VARCHAR2/CLOB/BLOB và kiểm tra IS JSON

JSON là định dạng trao đổi dữ liệu phổ biến cho API, event, cấu hình và tài liệu nghiệp vụ. Trong Oracle Database, ứng dụng có thể lưu JSON dưới dạng văn bản trong VARCHAR2 hoặc CLOB, hoặc lưu các byte UTF-8 trong BLOB. Khi dùng các kiểu lưu trữ văn bản/LOB này, database không tự biến mọi giá trị thành JSON hợp lệ chỉ vì cột được đặt tên là JSON_PAYLOAD. Cần kiểm tra cú pháp JSON bằng điều kiện SQL **IS JSON**, thường được đặt trong CHECK constraint để dữ liệu sai không thể được ghi vào bảng.

Lựa chọn kiểu cột ảnh hưởng giới hạn kích thước, cách client truyền dữ liệu, bộ nhớ và thao tác LOB. VARCHAR2 phù hợp với tài liệu nhỏ và có giới hạn độ dài; CLOB phù hợp với JSON văn bản lớn; BLOB phù hợp khi muốn lưu byte JSON theo UTF-8. Từ Oracle Database 21c, database có kiểu JSON native lưu theo định dạng nhị phân OSON; các hệ thống Oracle 19c vẫn thường dùng VARCHAR2/CLOB/BLOB.

Bài học thuộc nhóm **JSON và XML** của Database Engine Relational Oracle. Nội dung tập trung vào lưu JSON trong ba kiểu dữ liệu VARCHAR2, CLOB, BLOB; cú pháp IS JSON; strict/lax syntax; unique object keys; CHECK constraint; NULL semantics; kiểm tra dữ liệu cũ; truy vấn tài liệu JSON; khác biệt theo phiên bản và bài thực hành.

Sau bài này, bạn có thể:

- Chọn VARCHAR2, CLOB hoặc BLOB cho JSON payload theo kích thước và cách ứng dụng sử dụng dữ liệu.
- Hiểu giới hạn VARCHAR2 trong cấu hình STANDARD và EXTENDED.
- Giải thích yêu cầu UTF-8 khi lưu JSON trong BLOB.
- Dùng IS JSON để kiểm tra cú pháp tài liệu.
- Phân biệt lax syntax và strict syntax.
- Dùng WITH UNIQUE KEYS khi không chấp nhận object key trùng lặp.
- Đặt CHECK constraint để bảo vệ dữ liệu khi INSERT/UPDATE.
- Kết hợp NOT NULL với IS JSON để phân biệt SQL NULL và JSON null.
- Kiểm tra và làm sạch dữ liệu cũ trước khi thêm constraint.
- Dùng JSON_VALUE, JSON_QUERY, JSON_EXISTS và JSON_TABLE để đọc dữ liệu đã lưu.
- Hiểu IS JSON không thay thế validation cấu trúc và quy tắc nghiệp vụ.
- Nhận biết native JSON data type từ Oracle Database 21c và khác biệt với 19c.

> **Phạm vi ví dụ:** Cú pháp chính theo Oracle Database 19c, nơi JSON thường được lưu dưới dạng VARCHAR2/CLOB/BLOB. Các ghi chú về kiểu JSON native và SQL BOOLEAN được phân biệt theo release; hãy kiểm tra version/RU trước khi triển khai.

## 1. JSON được lưu như thế nào trong Oracle?

JSON là văn bản có cấu trúc gồm object, array, string, number, boolean và null. Ví dụ:

~~~json
{
  "orderId": 9001,
  "status": "NEW",
  "total": 125.50,
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 205, "quantity": 1}
  ]
}
~~~

Trong Oracle 19c, có thể lưu nội dung này trong:

- VARCHAR2: chuỗi ký tự có giới hạn độ dài.
- CLOB: large object chứa ký tự.
- BLOB: large object chứa byte; JSON được lưu dưới dạng byte UTF-8.

Database có thể kiểm tra nội dung của các kiểu này bằng điều kiện IS JSON.

### 1.1. JSON trong cột không tự động được xác thực

Ví dụ:

~~~sql
CREATE TABLE api_event_lab (
    event_id NUMBER PRIMARY KEY,
    payload VARCHAR2(4000)
);
~~~

Cột PAYLOAD chỉ là VARCHAR2. Nếu không có constraint, ứng dụng có thể ghi:

~~~sql
INSERT INTO api_event_lab(event_id, payload)
VALUES (1, '{"event":"created","id":101}');

INSERT INTO api_event_lab(event_id, payload)
VALUES (2, '{this is not json}');
~~~

Cả hai giá trị đều là chuỗi hợp lệ đối với datatype VARCHAR2. Database không tự biết chuỗi thứ hai sai cú pháp JSON nếu không có validation.

### 1.2. IS JSON xác nhận cú pháp

Có thể kiểm tra trực tiếp:

~~~sql
SELECT payload
FROM api_event_lab
WHERE payload IS JSON;
~~~

IS JSON là SQL condition dùng để xác định giá trị có phải JSON hợp lệ theo chế độ cú pháp được chọn hay không. Nó không tự sửa, chuẩn hóa hoặc chuyển chuỗi sai thành JSON.

### 1.3. JSON syntax khác business validation

Một tài liệu có thể hợp lệ về cú pháp nhưng sai nghiệp vụ:

~~~json
{
  "orderId": -1,
  "status": "UNKNOWN",
  "total": -500
}
~~~

Đây vẫn là JSON hợp lệ về cú pháp. IS JSON không biết orderId phải dương, status chỉ được nhận NEW/PAID/CANCELLED hoặc total không được âm. Những quy tắc đó cần được kiểm tra ở tầng ứng dụng, constraint phù hợp hoặc validation chuyên biệt.

## 2. Chọn VARCHAR2, CLOB hay BLOB

Ba kiểu dữ liệu có mục tiêu sử dụng khác nhau.

| Kiểu cột | Nội dung | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- | --- |
| VARCHAR2 | JSON text | Tài liệu nhỏ, kích thước có giới hạn | Giới hạn byte/character và MAX_STRING_SIZE |
| CLOB | JSON text lớn | Tài liệu lớn, xử lý theo character/LOB API | LOB storage, locator và thao tác LOB |
| BLOB | JSON bytes | Cần lưu byte JSON UTF-8 hoặc payload lớn dạng binary | Phải cung cấp JSON encoded bằng UTF-8 |

### 2.1. VARCHAR2 cho JSON nhỏ

Ví dụ:

~~~sql
CREATE TABLE small_json_lab (
    event_id NUMBER PRIMARY KEY,
    payload VARCHAR2(4000 BYTE)
        CONSTRAINT ck_small_json_lab CHECK (payload IS JSON)
);
~~~

Ưu điểm:

- Cấu trúc đơn giản.
- Dễ bind từ ứng dụng dưới dạng string.
- Thuận tiện cho payload nhỏ.
- Không cần thao tác LOB locator.

Hạn chế:

- Có giới hạn kích thước.
- Cần phân biệt BYTE và CHAR semantics.
- Một payload vượt giới hạn sẽ không thể ghi vào cột.

### 2.2. Giới hạn VARCHAR2 trong SQL

Với MAX_STRING_SIZE = STANDARD, giới hạn VARCHAR2 trong SQL thường là tối đa 4000 bytes. Với MAX_STRING_SIZE = EXTENDED, giới hạn tối đa có thể là 32767 bytes. Giá trị thực tế còn phụ thuộc khai báo độ dài, byte/char semantics và database character set.

Kiểm tra cấu hình:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'max_string_size';
~~~

Quyền truy cập V$PARAMETER phụ thuộc cấu hình và grants. Không tự thay đổi MAX_STRING_SIZE chỉ để lưu một JSON payload lớn; đây là cấu hình database cần quy trình DBA và có tác động rộng.

### 2.3. BYTE và CHAR semantics

~~~sql
payload_bytes VARCHAR2(4000 BYTE)
payload_chars VARCHAR2(4000 CHAR)
~~~

BYTE giới hạn theo số byte; CHAR giới hạn theo số ký tự. Với ký tự UTF-8 nhiều byte, một ký tự có thể chiếm nhiều byte. Khai báo CHAR không có nghĩa cột luôn có thể lưu 4000 ký tự trong mọi database character set nếu bị giới hạn byte tối đa của datatype.

Với JSON chứa tiếng Việt hoặc nhiều ngôn ngữ, hãy kiểm tra character set, độ dài thực tế và cách driver bind dữ liệu.

### 2.4. CLOB cho JSON văn bản lớn

~~~sql
CREATE TABLE document_json_lab (
    document_id NUMBER PRIMARY KEY,
    payload CLOB
        CONSTRAINT ck_document_json_lab
        CHECK (payload IS JSON)
);
~~~

CLOB lưu dữ liệu ký tự lớn hơn giới hạn VARCHAR2. Nó phù hợp với:

- API request/response lớn.
- Tài liệu JSON có nhiều phần tử.
- Event hoặc message payload dài.
- Tài liệu cần đọc/ghi bằng character LOB APIs.

CLOB được quản lý như LOB, thường thông qua locator và DBMS_LOB hoặc driver LOB support. Không nên giả định mọi thao tác CLOB có chi phí giống VARCHAR2.

### 2.5. BLOB cho JSON UTF-8

~~~sql
CREATE TABLE binary_json_text_lab (
    document_id NUMBER PRIMARY KEY,
    payload BLOB
        CONSTRAINT ck_binary_json_text_lab
        CHECK (payload IS JSON)
);
~~~

Khi lưu JSON trong BLOB, nội dung JSON phải được mã hóa UTF-8 theo quy tắc Oracle JSON. BLOB lưu byte, không tự biết charset. Ứng dụng phải gửi đúng byte UTF-8; không thể đưa chuỗi ở charset tùy ý vào BLOB rồi kỳ vọng database tự đoán chính xác.

BLOB phù hợp khi:

- Ứng dụng đã có JSON dưới dạng UTF-8 bytes.
- Cần giữ byte payload theo định dạng truyền nhận.
- Dùng LOB API/driver làm việc tự nhiên với binary data.
- Cần xử lý tài liệu lớn mà không muốn chuyển đổi qua character LOB.

Nếu ứng dụng chủ yếu xử lý chuỗi ký tự, CLOB thường dễ dùng hơn BLOB.

### 2.6. BLOB không có nghĩa JSON nhị phân native

BLOB trong ví dụ này vẫn chứa JSON text được mã hóa thành byte UTF-8. Nó không phải cùng khái niệm với kiểu JSON native dùng OSON của Oracle Database 21c trở lên. Tên datatype BLOB không tự chuyển nội dung thành OSON.

## 3. IS JSON condition

IS JSON là điều kiện SQL xác định một giá trị có chứa JSON hợp lệ hay không.

### 3.1. Cú pháp cơ bản

~~~sql
expression IS JSON
~~~

Hoặc:

~~~sql
expression IS NOT JSON
~~~

Có thể bổ sung chế độ cú pháp và yêu cầu unique keys:

~~~sql
expression IS JSON STRICT
expression IS JSON LAX
expression IS JSON WITH UNIQUE KEYS
expression IS JSON STRICT WITH UNIQUE KEYS
~~~

Mặc định Oracle dùng lax syntax nếu không chỉ định STRICT/LAX. Khi cần JSON theo cú pháp nghiêm ngặt, hãy ghi STRICT rõ ràng trong constraint.

### 3.2. IS JSON dùng được với VARCHAR2/CLOB/BLOB

Ví dụ bảng có ba kiểu cột:

~~~sql
CREATE TABLE json_storage_lab (
    id NUMBER PRIMARY KEY,
    json_short VARCHAR2(4000),
    json_text CLOB,
    json_bytes BLOB,
    CONSTRAINT ck_json_short_lab CHECK (json_short IS JSON),
    CONSTRAINT ck_json_text_lab CHECK (json_text IS JSON),
    CONSTRAINT ck_json_bytes_lab CHECK (json_bytes IS JSON)
);
~~~

Với BLOB, dữ liệu phải theo encoding UTF-8 được Oracle hỗ trợ cho JSON. Với CLOB/VARCHAR2, nội dung là character data theo database character set.

### 3.3. IS NOT JSON

IS NOT JSON hữu ích khi tìm giá trị không hợp lệ:

~~~sql
SELECT id, json_short
FROM json_storage_lab
WHERE json_short IS NOT JSON;
~~~

Lưu ý SQL NULL: phép kiểm tra trên NULL cho kết quả UNKNOWN, không phải TRUE. Vì vậy truy vấn này không trả các hàng có SQL NULL. Muốn tìm cả NULL lẫn JSON sai:

~~~sql
SELECT id, json_short
FROM json_storage_lab
WHERE json_short IS NULL
   OR json_short IS NOT JSON;
~~~

### 3.4. IS JSON không chuyển đổi dữ liệu

Điều kiện IS JSON chỉ kiểm tra. Nó không:

- Chuyển chuỗi JSON sang object type.
- Chuẩn hóa thứ tự key.
- Xóa khoảng trắng.
- Sửa dấu nháy hoặc dấu phẩy sai.
- Tự thêm field bắt buộc.
- Ép kiểu string thành number.

Nếu dữ liệu sai, ứng dụng phải sửa payload trước khi ghi hoặc migration phải xử lý riêng.

## 4. Strict JSON và lax JSON

Oracle hỗ trợ strict syntax và lax syntax cho JSON text trong các ngữ cảnh được hỗ trợ.

### 4.1. Strict syntax

Strict syntax tuân theo quy tắc JSON chuẩn: tên field và string dùng dấu nháy kép, không có extension ngoài cú pháp JSON.

~~~json
{
  "customerId": 501,
  "name": "Nguyen An",
  "active": true
}
~~~

Kiểm tra:

~~~sql
SELECT '{"customerId":501,"name":"Nguyen An","active":true}' IS JSON STRICT
FROM dual;
~~~

### 4.2. Lax syntax

Lax syntax cho phép một số dạng biểu diễn mở rộng mà Oracle chấp nhận ngoài strict JSON. Ví dụ minh họa:

~~~text
{customerId: 501, name: 'Nguyen An'}
~~~

Đây không phải JSON strict vì tên field không đặt trong dấu nháy kép và string dùng dấu nháy đơn. Oracle lax mode có thể chấp nhận một số extension kiểu này.

### 4.3. Kiểm tra strict và lax

~~~sql
SELECT
    CASE
        WHEN '{customerId:501,name:''Nguyen An''}' IS JSON LAX
        THEN 'VALID LAX'
        ELSE 'INVALID LAX'
    END AS lax_result
FROM dual;
~~~

Đối với payload do API bên ngoài gửi, thường nên thống nhất strict JSON để tăng khả năng tương thích với client, message broker và hệ thống khác.

### 4.4. Chọn strict trong CHECK constraint

~~~sql
CREATE TABLE strict_json_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_strict_json_lab
        CHECK (payload IS JSON STRICT)
);
~~~

Constraint này yêu cầu payload không NULL và nội dung phải là strict JSON.

### 4.5. Khi nào dùng lax?

Lax có thể hữu ích khi tiếp nhận nguồn JSON cũ hoặc dữ liệu Oracle JSON được tạo theo cú pháp mở rộng. Tuy nhiên, nếu hệ thống trao đổi với nhiều nền tảng, strict thường dễ dự đoán hơn.

Không bật lax chỉ để làm cho dữ liệu sai từ upstream lọt qua mà chưa hiểu nguồn sai và ảnh hưởng downstream.

## 5. WITH UNIQUE KEYS

Một object JSON có thể xuất hiện cùng một tên field nhiều lần trong một object:

~~~json
{
  "status": "NEW",
  "status": "PAID"
}
~~~

Đây là JSON có cú pháp hợp lệ trong nhiều parser, nhưng ý nghĩa khi có duplicate key không nhất quán giữa các consumer. Một parser có thể lấy giá trị đầu, parser khác lấy giá trị cuối hoặc giữ cả hai.

### 5.1. Mặc định không nên giả định key luôn duy nhất

Chỉ dùng IS JSON cơ bản không đồng nghĩa đã yêu cầu mọi object không có key trùng. Nếu unique field names là một phần contract, hãy khai báo WITH UNIQUE KEYS.

### 5.2. Constraint với unique keys

~~~sql
CREATE TABLE unique_json_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_unique_json_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

Điều kiện này yêu cầu:

- Payload là JSON strict.
- Object keys không bị lặp theo quy tắc unique keys của Oracle.

### 5.3. Unique keys khác primary key

WITH UNIQUE KEYS chỉ kiểm tra tên field trong từng JSON object. Nó không tạo relational primary key và không bảo đảm:

- Mỗi document có customerId duy nhất trong toàn bảng.
- Một field bắt buộc phải tồn tại.
- Một giá trị phải duy nhất giữa nhiều hàng.
- Giá trị phải thuộc domain nghiệp vụ.

Nếu cần unique theo customerId trên toàn bảng, hãy trích xuất giá trị bằng JSON_VALUE vào virtual column/function-based index hoặc lưu thành cột quan hệ có unique constraint phù hợp.

### 5.4. Khi nào không nên bật unique keys?

Nếu phải tiếp nhận dữ liệu legacy có duplicate keys, thêm WITH UNIQUE KEYS ngay có thể khiến INSERT/UPDATE mới thất bại. Trước migration, hãy kiểm tra và chuẩn hóa dữ liệu nguồn. Không dựa vào parser behavior khác nhau để xử lý duplicate key.

## 6. CHECK constraint kết hợp IS JSON

Đặt validation ngay tại database giúp mọi đường ghi dữ liệu tuân thủ cùng một quy tắc, dù dữ liệu đến từ ứng dụng, batch job hay SQL client.

### 6.1. Tạo bảng với CHECK

~~~sql
CREATE TABLE order_json_lab (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_order_json_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

### 6.2. INSERT JSON hợp lệ

~~~sql
INSERT INTO order_json_lab(order_id, payload)
VALUES (
    9001,
    '{"orderId":9001,"status":"NEW","total":125.50}'
);
~~~

### 6.3. INSERT JSON sai cú pháp

~~~sql
INSERT INTO order_json_lab(order_id, payload)
VALUES (
    9002,
    '{"orderId":9002,"status":NEW}'
);
~~~

Giá trị NEW thiếu dấu nháy kép nên không phải strict JSON string. CHECK constraint từ chối hàng này và Oracle báo lỗi vi phạm constraint, thường là ORA-02290.

### 6.4. INSERT duplicate keys

~~~sql
INSERT INTO order_json_lab(order_id, payload)
VALUES (
    9003,
    '{"orderId":9003,"status":"NEW","status":"PAID"}'
);
~~~

Constraint WITH UNIQUE KEYS từ chối document có duplicate object field name.

### 6.5. CHECK và SQL NULL

CHECK constraint không tự thay thế NOT NULL. Trong SQL, CHECK chỉ loại hàng khi điều kiện là FALSE; UNKNOWN không bị xem như FALSE. Với payload SQL NULL, biểu thức payload IS JSON cho kết quả UNKNOWN, vì vậy CHECK có thể vẫn cho phép hàng.

Do đó, nếu bắt buộc phải có document:

~~~sql
payload CLOB NOT NULL,
CONSTRAINT ck_payload_json CHECK (payload IS JSON STRICT)
~~~

Hoặc:

~~~sql
CHECK (payload IS NOT NULL AND payload IS JSON STRICT)
~~~

Khai báo NOT NULL riêng thường dễ đọc và dễ quản lý hơn.

### 6.6. SQL NULL khác JSON null

Hai trường hợp sau khác nhau:

- SQL NULL: cột không có giá trị SQL.
- JSON null: payload chứa văn bản JSON literal null hoặc một property có giá trị null.

Ví dụ document:

~~~json
{"orderId":9001,"note":null}
~~~

đây là một JSON document có field NOTE với JSON null. Nó khác một cột PAYLOAD có SQL NULL.

## 7. Thêm IS JSON constraint cho bảng đã có dữ liệu

Khi bảng đã chứa payload, không nên thêm constraint ngay mà chưa kiểm tra dữ liệu cũ.

### 7.1. Tìm SQL NULL

~~~sql
SELECT COUNT(*) AS null_count
FROM legacy_json_lab
WHERE payload IS NULL;
~~~

### 7.2. Tìm JSON không hợp lệ

~~~sql
SELECT id, payload
FROM legacy_json_lab
WHERE payload IS NOT NULL
  AND payload IS NOT JSON;
~~~

Nếu cần strict:

~~~sql
SELECT id, payload
FROM legacy_json_lab
WHERE payload IS NOT NULL
  AND payload IS NOT JSON STRICT;
~~~

Nếu cần unique keys:

~~~sql
SELECT id, payload
FROM legacy_json_lab
WHERE payload IS NOT JSON STRICT WITH UNIQUE KEYS;
~~~

### 7.3. Làm sạch dữ liệu trước

Quy trình migration thường gồm:

1. Thống kê số hàng NULL, invalid và duplicate keys.
2. Xác định nguồn tạo dữ liệu sai.
3. Sửa payload bằng ứng dụng/migration có kiểm soát.
4. Xác nhận mọi hàng đáp ứng policy mới.
5. Thêm constraint với ENABLE VALIDATE.

Không tự động sửa JSON bằng replace chuỗi đơn giản. Ví dụ thay dấu nháy đơn bằng dấu nháy kép có thể phá nội dung string hoặc escape sequence. Dùng JSON parser/generator phù hợp để parse và serialize lại.

### 7.4. Thêm constraint và validate

~~~sql
ALTER TABLE legacy_json_lab
ADD CONSTRAINT ck_legacy_json_lab
CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
ENABLE VALIDATE;
~~~

ENABLE VALIDATE yêu cầu dữ liệu hiện có đáp ứng constraint và các DML mới tiếp tục bị kiểm tra. Nếu có hàng không hợp lệ, thao tác thêm/validate constraint sẽ thất bại cho đến khi dữ liệu được sửa.

### 7.5. ENABLE NOVALIDATE

Trong migration nhiều giai đoạn, có thể dùng:

~~~sql
ALTER TABLE legacy_json_lab
ADD CONSTRAINT ck_legacy_json_lab
CHECK (payload IS JSON STRICT)
ENABLE NOVALIDATE;
~~~

ENABLE NOVALIDATE bắt đầu enforce constraint đối với DML mới nhưng không xác nhận tất cả hàng cũ đã hợp lệ. Đây là trạng thái chuyển tiếp, không phải bằng chứng dữ liệu lịch sử đã sạch.

Sau khi sửa dữ liệu cũ:

~~~sql
ALTER TABLE legacy_json_lab
ENABLE VALIDATE CONSTRAINT ck_legacy_json_lab;
~~~

### 7.6. Disable constraint

~~~sql
ALTER TABLE legacy_json_lab
DISABLE CONSTRAINT ck_legacy_json_lab;
~~~

Khi constraint bị disable, database không còn enforce quy tắc đó theo trạng thái disabled. Chỉ disable trong migration/maintenance có phê duyệt; bật lại và validate sau khi hoàn tất.

## 8. IS JSON và kiểm tra cấu trúc nghiệp vụ

IS JSON chỉ trả lời câu hỏi: giá trị có đúng cú pháp JSON theo policy hay không?

### 8.1. Kiểm tra property bắt buộc

Ví dụ payload đơn hàng phải có orderId:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_EXISTS(payload, '$.orderId');
~~~

JSON_EXISTS kiểm tra path có khớp dữ liệu hay không. Có thể kết hợp với CHECK constraint nếu expression được hỗ trợ và semantics rõ, nhưng cần kiểm tra lỗi chuyển đổi và dữ liệu cũ.

### 8.2. Kiểm tra datatype của property

~~~sql
SELECT
    order_id,
    JSON_VALUE(
        payload,
        '$.total'
        RETURNING NUMBER
        NULL ON ERROR
    ) AS total_amount
FROM order_json_lab;
~~~

JSON_VALUE trích xuất scalar. RETURNING NUMBER yêu cầu giá trị chuyển đổi được sang NUMBER; NULL ON ERROR khiến lỗi chuyển đổi trả NULL thay vì làm hỏng toàn query. Với dữ liệu quan trọng, không dùng NULL ON ERROR để âm thầm che mọi lỗi mà không có giám sát.

### 8.3. Phân biệt field thiếu và field null

Một property có thể:

- Không tồn tại.
- Tồn tại với JSON null.
- Tồn tại với string rỗng.
- Tồn tại với number/boolean/object/array.

JSON_VALUE thường trả SQL NULL trong nhiều trường hợp thiếu hoặc JSON null theo default behavior. Nếu cần phân biệt, dùng JSON_EXISTS/path condition hoặc JSON_QUERY với các error/empty clauses thích hợp.

### 8.4. Kiểm tra quy tắc nghiệp vụ

Ví dụ total phải không âm:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_VALUE(
          payload,
          '$.total' RETURNING NUMBER NULL ON ERROR
      ) < 0;
~~~

IS JSON không thay thế các quy tắc kiểu dữ liệu, miền giá trị, field bắt buộc hoặc quan hệ giữa các field.

### 8.5. Validation ở đúng tầng

Một thiết kế thường kết hợp:

- IS JSON STRICT để xác thực syntax.
- WITH UNIQUE KEYS để cấm duplicate keys.
- NOT NULL để bắt buộc có document.
- CHECK/JSON functions hoặc application validation cho một số quy tắc shape.
- Relational columns và constraints cho dữ liệu cần join, index, foreign key hoặc unique business key.

Không nhồi toàn bộ mô hình quan hệ vào một JSON CLOB chỉ vì JSON linh hoạt.

## 9. Đọc JSON đã lưu

Sau khi dữ liệu được lưu và kiểm tra, Oracle SQL/JSON functions có thể truy vấn nội dung.

### 9.1. JSON_VALUE

Lấy một scalar:

~~~sql
SELECT
    order_id,
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) AS status
FROM order_json_lab;
~~~

### 9.2. JSON_QUERY

Lấy object hoặc array:

~~~sql
SELECT JSON_QUERY(payload, '$.items' RETURNING CLOB)
FROM order_json_lab;
~~~

JSON_QUERY phù hợp khi kết quả path là JSON object/array. Có thể chỉ định wrapper/empty/error behavior theo cú pháp SQL/JSON của release.

### 9.3. JSON_EXISTS

Kiểm tra property/path tồn tại:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_EXISTS(payload, '$.items');
~~~

### 9.4. JSON_TABLE

Chuyển JSON thành các hàng/cột quan hệ:

~~~sql
SELECT
    o.order_id,
    j.product_id,
    j.quantity
FROM order_json_lab o,
     JSON_TABLE(
         o.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId',
             quantity NUMBER PATH '$.quantity'
         )
     ) j;
~~~

JSON_TABLE hữu ích khi một JSON array chứa nhiều phần tử và cần join/filter/aggregate bằng SQL.

### 9.5. Dùng JSON functions không làm mất vai trò IS JSON

JSON_VALUE/JSON_QUERY/JSON_TABLE có error handling riêng. Nếu dữ liệu được bảo vệ bởi IS JSON constraint, các function có thể dựa vào giả định cú pháp hợp lệ hơn. Nếu không có constraint, từng query phải quyết định ON ERROR/ON EMPTY và cách xử lý payload sai.

## 10. Index và hiệu năng khi lưu JSON

Lưu JSON trong CLOB/BLOB không có nghĩa mọi truy vấn path đều nhanh như truy vấn cột quan hệ có B-tree index.

### 10.1. Function-based index trên JSON_VALUE

Nếu thường xuyên lọc theo một scalar field:

~~~sql
CREATE INDEX ix_order_json_status_lab
ON order_json_lab (
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
);
~~~

Truy vấn tương ứng:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_VALUE(
          payload,
          '$.status' RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

Expression trong query nên khớp với index definition và kiểu trả về. Hãy kiểm tra execution plan để xác nhận optimizer dùng index.

### 10.2. JSON search index

Oracle hỗ trợ JSON search index cho các trường hợp cần tìm kiếm linh hoạt trên nội dung JSON:

~~~sql
CREATE SEARCH INDEX ix_order_json_search_lab
ON order_json_lab(payload)
FOR JSON;
~~~

Search index phù hợp với nhiều dạng path/filter nhưng có chi phí storage, DML maintenance và indexing. Không tạo index này nếu workload chỉ truy vấn một field đơn giản; cân nhắc function-based index hoặc relational projection.

### 10.3. Cột quan hệ cho field truy vấn thường xuyên

Nếu STATUS, CUSTOMER_ID hoặc CREATED_AT luôn được dùng để join/filter/sort, có thể lưu thêm cột quan hệ:

~~~sql
CREATE TABLE order_document_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    payload CLOB NOT NULL,
    CONSTRAINT ck_order_document_json_lab
        CHECK (payload IS JSON STRICT)
);

CREATE INDEX ix_order_document_customer_lab
ON order_document_lab(customer_id);
~~~

Giữ các field quan trọng thành cột có kiểu và constraint rõ ràng, còn JSON lưu phần mở rộng linh hoạt. Cần bảo đảm các giá trị lặp giữa cột quan hệ và JSON được đồng bộ.

### 10.4. Chọn kiểu lưu trữ không thay thế thiết kế index

VARCHAR2, CLOB và BLOB quyết định cách lưu payload. Hiệu năng truy vấn còn phụ thuộc:

- Path expression.
- Số lượng tài liệu và kích thước document.
- Selectivity của predicate.
- Function-based/search index.
- Optimizer statistics.
- Tần suất INSERT/UPDATE.
- LOB storage và buffer/cache behavior.

Benchmark bằng workload thực tế thay vì chọn BLOB/CLOB với giả định một kiểu luôn nhanh hơn.

## 11. BLOB JSON và UTF-8

BLOB lưu byte, do đó client và database phải thống nhất encoding.

### 11.1. UTF-8 là yêu cầu quan trọng

JSON trong BLOB phải được mã hóa UTF-8. Nếu client gửi dữ liệu theo encoding khác rồi lưu nguyên byte, Oracle có thể không nhận diện đúng JSON hoặc ký tự có thể bị hỏng.

Với nội dung chỉ gồm ASCII, byte ASCII có cùng giá trị trong UTF-8 nên ví dụ đơn giản có thể hoạt động. Với tiếng Việt, emoji và các ký tự ngoài ASCII, phải encode rõ AL32UTF8.

### 11.2. Ghi BLOB bằng PL/SQL

Ví dụ tạo temporary BLOB, ghi byte UTF-8 rồi insert:

~~~sql
DECLARE
    l_blob BLOB;
    l_raw  RAW(32767);
    l_text VARCHAR2(1000) :=
        '{"message":"Xin chao","status":"NEW"}';
BEGIN
    l_raw := UTL_I18N.STRING_TO_RAW(l_text, 'AL32UTF8');

    DBMS_LOB.CREATETEMPORARY(l_blob, TRUE);
    DBMS_LOB.WRITE(
        l_blob,
        UTL_RAW.LENGTH(l_raw),
        1,
        l_raw
    );

    INSERT INTO binary_json_text_lab(document_id, payload)
    VALUES (1, l_blob);

    COMMIT;
    DBMS_LOB.FREETEMPORARY(l_blob);
END;
/
~~~

Ví dụ này giả định bảng BINARY_JSON_TEXT_LAB đã được tạo với cột PAYLOAD BLOB có IS JSON constraint. Với payload lớn hơn giới hạn RAW trong một lần ghi, hãy chia thành nhiều chunk hoặc dùng streaming LOB API/driver.

### 11.3. Đọc BLOB JSON

Khi truy vấn JSON trong BLOB, Oracle SQL/JSON functions có thể xử lý BLOB theo các quy tắc JSON và encoding được hỗ trợ. Không tự chuyển BLOB sang VARCHAR2 ngắn bằng CAST nếu payload có thể vượt giới hạn hoặc có ký tự đa byte.

### 11.4. Client driver

Ứng dụng Java/JDBC, .NET, Python hoặc OCI cần bind đúng loại LOB/binary:

- CLOB: bind character stream/Clob phù hợp.
- BLOB: bind binary stream/Blob chứa byte UTF-8.
- VARCHAR2: bind string có độ dài phù hợp.

Kiểm tra encoding tại biên ứng dụng; không giả định database tự sửa byte sai encoding.

## 12. Oracle JSON native type và khác biệt phiên bản

### 12.1. Oracle 19c

Trong Oracle Database 19c, JSON thường được lưu trong VARCHAR2, CLOB hoặc BLOB. Có thể dùng IS JSON constraint để xác nhận nội dung và dùng SQL/JSON functions để truy vấn.

Ví dụ:

~~~sql
CREATE TABLE json_19c_lab (
    id NUMBER PRIMARY KEY,
    doc CLOB NOT NULL,
    CONSTRAINT ck_json_19c_lab CHECK (doc IS JSON STRICT)
);
~~~

### 12.2. Oracle 21c trở lên

Oracle Database 21c giới thiệu kiểu dữ liệu JSON native. Kiểu này lưu JSON bằng định dạng nhị phân OSON được Oracle tối ưu cho xử lý JSON. Đây là kiểu dữ liệu JSON thực sự ở mức database, khác với BLOB chứa JSON text UTF-8.

Ví dụ khái niệm trên release hỗ trợ:

~~~sql
CREATE TABLE native_json_lab (
    id NUMBER PRIMARY KEY,
    doc JSON
);
~~~

Không chạy DDL này trên Oracle 19c; 19c không có native SQL JSON datatype như ví dụ.

### 12.3. OSON khác BLOB

| Đặc điểm | BLOB chứa JSON text | Native JSON |
| --- | --- | --- |
| Lưu trữ | Byte UTF-8 của JSON text | Binary OSON |
| Định dạng | Văn bản JSON được mã hóa | Định dạng nội bộ tối ưu |
| Đọc trực tiếp như text | Có thể giải mã UTF-8 | Không coi như JSON text thông thường |
| Phiên bản | Được hỗ trợ trong 19c | Từ 21c |
| Mục tiêu | Lưu payload text dạng byte | Tối ưu lưu trữ/xử lý JSON native |

Không gọi mọi cột BLOB chứa JSON là OSON. BLOB JSON text vẫn cần tuân thủ UTF-8 và IS JSON.

### 12.4. Oracle 23c/23ai

Oracle Database 23c, được thương mại hóa với tên Oracle Database 23ai, tiếp tục hỗ trợ native JSON và bổ sung các khả năng SQL/JSON. Các cú pháp, JSON schema validation, JSON relational duality và tính năng mới có thể phụ thuộc release/RU. Khi cần portability, kiểm tra tài liệu phiên bản thay vì suy ra từ tên datatype.

### 12.5. Lộ trình migration

Khi nâng cấp từ 19c:

1. Kiểm kê cột JSON hiện tại và tỷ lệ VARCHAR2/CLOB/BLOB.
2. Kiểm tra IS JSON constraints và strict/lax policy.
3. Kiểm tra client driver có hỗ trợ native JSON datatype không.
4. Đo workload trên release mới.
5. Xác định có lợi ích khi chuyển sang JSON native hay tiếp tục dùng LOB.
6. Chuẩn bị migration/rollback và kiểm thử application compatibility.

Không chuyển tất cả JSON CLOB sang native JSON chỉ vì kiểu mới tồn tại; cần đo lợi ích và kiểm tra compatibility của ứng dụng.

## 13. Quản lý constraint trong data dictionary

### 13.1. Xem CHECK constraints

~~~sql
SELECT
    constraint_name,
    table_name,
    status,
    validated,
    search_condition
FROM user_constraints
WHERE constraint_type = 'C'
ORDER BY table_name, constraint_name;
~~~

USER_CONSTRAINTS cho biết trạng thái ENABLE/DISABLE và VALIDATED/NOVALIDATED. SEARCH_CONDITION có kiểu dữ liệu dictionary phụ thuộc release; với câu query dài, dùng view/cột thích hợp như SEARCH_CONDITION_VC nếu có.

### 13.2. Xem cột và datatype

~~~sql
SELECT
    table_name,
    column_name,
    data_type,
    data_length,
    char_length,
    nullable
FROM user_tab_columns
WHERE table_name IN (
    'ORDER_JSON_LAB',
    'DOCUMENT_JSON_LAB',
    'BINARY_JSON_TEXT_LAB'
)
ORDER BY table_name, column_id;
~~~

### 13.3. Xem constraint theo bảng

~~~sql
SELECT
    constraint_name,
    constraint_type,
    status,
    validated
FROM user_constraints
WHERE table_name = 'ORDER_JSON_LAB';
~~~

### 13.4. Kiểm tra invalid rows trước khi bật constraint

~~~sql
SELECT COUNT(*) AS invalid_count
FROM legacy_json_lab
WHERE payload IS NOT NULL
  AND payload IS NOT JSON STRICT WITH UNIQUE KEYS;
~~~

Nếu INVALID_COUNT khác 0, cần xử lý dữ liệu trước khi ENABLE VALIDATE.

## 14. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-02290 | INSERT/UPDATE vi phạm IS JSON CHECK constraint | Kiểm tra payload, strict/lax và duplicate keys |
| ORA-01400 | Cột JSON khai báo NOT NULL nhưng nhận SQL NULL | Gửi document hoặc xử lý trường hợp thiếu payload |
| ORA-12899 | JSON vượt giới hạn VARCHAR2 | Chuyển sang CLOB/BLOB hoặc thiết kế payload nhỏ hơn |
| IS JSON trả FALSE | Nội dung sai cú pháp theo mode đang dùng | Kiểm tra quote, escape, dấu phẩy, encoding |
| JSON hợp lệ nhưng ứng dụng báo sai | Syntax đúng nhưng thiếu field/sai type/sai business rule | Bổ sung validation shape và nghiệp vụ |
| Duplicate key được chấp nhận | Constraint không dùng WITH UNIQUE KEYS | Bổ sung unique-key policy sau khi làm sạch dữ liệu |
| BLOB không nhận JSON | Byte không phải UTF-8 hoặc payload không hợp lệ | Encode rõ AL32UTF8 và kiểm tra byte |
| Thêm constraint thất bại | Dữ liệu lịch sử không đáp ứng rule | Tìm invalid rows, làm sạch, rồi validate |
| ENABLE NOVALIDATE nhưng dữ liệu cũ vẫn sai | NOVALIDATE không kiểm tra lại toàn bộ dữ liệu cũ | Làm sạch và ENABLE VALIDATE |
| JSON_VALUE trả NULL | Field thiếu, JSON null hoặc lỗi chuyển đổi theo ON ERROR | Dùng JSON_EXISTS/JSON_QUERY và error clauses để phân biệt |
| Truy vấn JSON chậm | Không có index phù hợp hoặc scan/LOB cost lớn | Xem plan, function-based index, JSON search index hoặc relational columns |
| Native JSON DDL lỗi trên 19c | Native JSON datatype chưa có trong 19c | Dùng VARCHAR2/CLOB/BLOB trên 19c |

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Cột tên JSON_PAYLOAD tự kiểm tra JSON | Phải dùng IS JSON hoặc validation khác |
| IS JSON kiểm tra quy tắc nghiệp vụ | Nó kiểm tra cú pháp JSON |
| CHECK IS JSON tự cấm SQL NULL | CHECK nhận UNKNOWN cho NULL; dùng NOT NULL |
| JSON null và SQL NULL giống nhau | JSON null là giá trị trong document; SQL NULL là absence của giá trị cột |
| IS JSON mặc định luôn là strict | Oracle mặc định lax nếu không chỉ định STRICT |
| IS JSON đồng nghĩa unique object keys | Cần WITH UNIQUE KEYS nếu policy yêu cầu |
| WITH UNIQUE KEYS tạo unique key giữa các hàng | Nó kiểm tra duplicate field names trong object, không phải unique constraint quan hệ |
| BLOB JSON là OSON | BLOB có thể chỉ chứa JSON text UTF-8 |
| CLOB luôn nhanh hơn BLOB | Hiệu năng phụ thuộc workload, encoding, LOB access và index |
| VARCHAR2 luôn chứa được JSON lớn | Có giới hạn STANDARD/EXTENDED |
| ENABLE NOVALIDATE xác nhận toàn bộ dữ liệu cũ | Nó enforce DML mới nhưng chưa validate toàn bộ hàng hiện tại |
| JSON_VALUE thay thế IS JSON constraint | Function trích xuất dữ liệu; constraint bảo vệ mọi đường ghi |
| Oracle 19c có native JSON datatype | Native JSON datatype được giới thiệu từ 21c |

## 16. Checklist chọn kiểu và validation policy

**Kiểu lưu trữ**

- Payload có nhỏ và có giới hạn rõ để dùng VARCHAR2 không?
- Có cần lưu JSON text lớn dưới dạng CLOB không?
- Ứng dụng có sẵn UTF-8 bytes và cần BLOB không?
- Database version có hỗ trợ native JSON type không?
- Driver có bind đúng datatype/LOB không?

**Validation**

- Có cần strict JSON không?
- Có cấm duplicate object keys không?
- Cột có bắt buộc NOT NULL không?
- Có cần kiểm tra required fields, datatype và business values không?
- Dữ liệu cũ đã được kiểm tra trước khi thêm constraint chưa?
- Constraint đang ENABLE VALIDATE hay ENABLE NOVALIDATE?

**Truy vấn**

- Field nào được filter/join/sort thường xuyên?
- Có nên tách field đó thành relational column không?
- Có cần function-based index hay JSON search index không?
- Đã xem execution plan và benchmark chưa?

**Vận hành**

- Có quy trình xử lý payload sai từ upstream không?
- Có log lỗi validation mà không lưu secret không?
- Có kiểm tra encoding UTF-8 ở biên BLOB không?
- Có migration plan khi nâng cấp 19c lên 21c/23ai không?

## 17. Bài thực hành tổng hợp

Lab này tạo ba bảng để so sánh kiểu lưu trữ, áp dụng IS JSON và đọc JSON bằng SQL/JSON functions.

### Bước 1 — VARCHAR2

~~~sql
CREATE TABLE json_varchar_lab (
    id NUMBER PRIMARY KEY,
    payload VARCHAR2(4000 BYTE) NOT NULL,
    CONSTRAINT ck_json_varchar_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);

INSERT INTO json_varchar_lab(id, payload)
VALUES (
    1,
    '{"customerId":501,"status":"NEW","total":125.50}'
);
~~~

### Bước 2 — CLOB

~~~sql
CREATE TABLE json_clob_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_json_clob_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);

INSERT INTO json_clob_lab(id, payload)
VALUES (
    1,
    '{"customerId":501,"status":"NEW","items":[{"productId":101,"qty":2}]}'
);
~~~

### Bước 3 — BLOB

~~~sql
CREATE TABLE json_blob_lab (
    id NUMBER PRIMARY KEY,
    payload BLOB NOT NULL,
    CONSTRAINT ck_json_blob_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

Ghi payload UTF-8:

~~~sql
DECLARE
    l_blob BLOB;
    l_raw RAW(32767);
    l_text VARCHAR2(1000) :=
        '{"customerId":501,"status":"NEW","note":"Xin chao"}';
BEGIN
    l_raw := UTL_I18N.STRING_TO_RAW(l_text, 'AL32UTF8');
    DBMS_LOB.CREATETEMPORARY(l_blob, TRUE);
    DBMS_LOB.WRITE(l_blob, UTL_RAW.LENGTH(l_raw), 1, l_raw);

    INSERT INTO json_blob_lab(id, payload)
    VALUES (1, l_blob);

    COMMIT;
    DBMS_LOB.FREETEMPORARY(l_blob);
END;
/
~~~

### Bước 4 — Thử dữ liệu sai

~~~sql
INSERT INTO json_varchar_lab(id, payload)
VALUES (2, '{"customerId":502,status:"NEW"}');
~~~

Lệnh phải bị từ chối vì payload không phải strict JSON.

### Bước 5 — Thử duplicate keys

~~~sql
INSERT INTO json_clob_lab(id, payload)
VALUES (
    2,
    '{"customerId":502,"status":"NEW","status":"PAID"}'
);
~~~

Lệnh phải bị từ chối vì constraint WITH UNIQUE KEYS.

### Bước 6 — Đọc JSON

~~~sql
SELECT
    id,
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) AS status,
    JSON_VALUE(payload, '$.customerId' RETURNING NUMBER) AS customer_id
FROM json_varchar_lab;
~~~

### Bước 7 — Kiểm tra trạng thái constraint

~~~sql
SELECT constraint_name, status, validated
FROM user_constraints
WHERE table_name IN (
    'JSON_VARCHAR_LAB',
    'JSON_CLOB_LAB',
    'JSON_BLOB_LAB'
)
ORDER BY table_name, constraint_name;
~~~

### Bước 8 — Dọn lab (tùy chọn)

~~~sql
DROP TABLE json_varchar_lab PURGE;
DROP TABLE json_clob_lab PURGE;
DROP TABLE json_blob_lab PURGE;
~~~

Chỉ chạy nếu chắc chắn các bảng thuộc lab và không cần dữ liệu nữa. DROP là DDL có implicit commit.

## Câu hỏi tự kiểm tra

1. Oracle 19c có thể lưu JSON trong những datatype nào?
2. Khi nào nên chọn VARCHAR2?
3. VARCHAR2 SQL có giới hạn nào với MAX_STRING_SIZE STANDARD và EXTENDED?
4. BYTE và CHAR semantics khác nhau ra sao?
5. Khi lưu JSON trong BLOB cần encoding gì?
6. CLOB khác BLOB ở dạng dữ liệu lưu trữ nào?
7. IS JSON kiểm tra điều gì?
8. IS JSON có tự sửa JSON sai cú pháp không?
9. Strict và lax syntax khác nhau thế nào?
10. Oracle mặc định dùng mode nào khi không ghi STRICT/LAX?
11. WITH UNIQUE KEYS giải quyết vấn đề gì?
12. WITH UNIQUE KEYS có tạo unique constraint trên dữ liệu giữa các hàng không?
13. Vì sao CHECK IS JSON nên kết hợp NOT NULL?
14. SQL NULL khác JSON null thế nào?
15. IS NOT JSON có trả các hàng SQL NULL không?
16. ENABLE NOVALIDATE khác ENABLE VALIDATE thế nào?
17. IS JSON có kiểm tra field bắt buộc và business rule không?
18. JSON_VALUE và JSON_QUERY khác nhau thế nào?
19. JSON_TABLE dùng để làm gì?
20. Khi nào cân nhắc function-based index trên JSON_VALUE?
21. JSON search index phù hợp với loại truy vấn nào?
22. Vì sao không nên lưu mọi field thường xuyên join/filter chỉ trong JSON?
23. Oracle native JSON datatype xuất hiện từ phiên bản nào?
24. BLOB JSON text khác native JSON OSON thế nào?
25. Cần kiểm tra gì khi migration từ 19c lên 21c/23ai?

**Gợi ý trả lời:**

1. VARCHAR2, CLOB và BLOB.
2. Khi document nhỏ, kích thước có giới hạn và client xử lý string thuận tiện.
3. STANDARD tối đa thường 4000 bytes; EXTENDED tối đa có thể 32767 bytes, tùy khai báo và character set.
4. BYTE giới hạn byte; CHAR giới hạn ký tự nhưng vẫn chịu giới hạn byte của datatype.
5. UTF-8.
6. CLOB lưu character data; BLOB lưu byte.
7. Cú pháp JSON theo mode được chỉ định.
8. Không.
9. Strict theo JSON chuẩn; lax cho phép một số extension Oracle chấp nhận.
10. Lax.
11. Ngăn duplicate field names trong object.
12. Không; nó không phải relational unique constraint.
13. CHECK với SQL NULL cho UNKNOWN và không loại hàng; NOT NULL bắt buộc có giá trị.
14. JSON null nằm trong document; SQL NULL là giá trị cột không có.
15. Không; điều kiện trên SQL NULL là UNKNOWN.
16. NOVALIDATE enforce dữ liệu mới nhưng chưa xác nhận mọi hàng cũ; VALIDATE kiểm tra dữ liệu hiện có.
17. Không; cần validation shape và nghiệp vụ riêng.
18. JSON_VALUE lấy scalar; JSON_QUERY lấy object/array hoặc JSON fragment.
19. Chuyển JSON structure thành rows/columns để dùng SQL.
20. Khi một scalar path được filter thường xuyên và expression phù hợp.
21. Tìm kiếm linh hoạt trên nhiều path/field trong JSON.
22. Vì relational columns hỗ trợ type, constraint, join và index rõ ràng hơn.
23. Oracle Database 21c.
24. BLOB chứa JSON text UTF-8; native JSON lưu binary OSON.
25. Client/driver, datatype support, constraints, workload, migration và rollback plan.

## Tài liệu Oracle tham khảo

- [Oracle Database JSON Developer's Guide — JSON Data Types and Storage](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/json-data-types.html): lưu JSON trong VARCHAR2, CLOB và BLOB.
- [Oracle Database SQL Language Reference — JSON Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SQL-JSON-Conditions.html): IS JSON, strict/lax và unique keys.
- [Oracle Database JSON Developer's Guide — JSON Constraints](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/creating-a-table-with-a-json-column.html): CHECK constraint để bảo đảm JSON hợp lệ.
- [Oracle Database SQL Language Reference — JSON_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_VALUE.html): trích xuất scalar từ JSON.
- [Oracle Database SQL Language Reference — JSON_QUERY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_QUERY.html): trích xuất object/array.
- [Oracle Database SQL Language Reference — JSON_TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_TABLE.html): ánh xạ JSON thành rows và columns.
- [Oracle Database SQL Language Reference — JSON_EXISTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_EXISTS.html): kiểm tra path tồn tại.
- [Oracle Database JSON Developer's Guide — JSON Search Index](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/indexes-for-json-data.html): index cho truy vấn JSON.
- [Oracle Database 21c JSON Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/21/adjsn/): native JSON data type và OSON.

**Nguyên tắc cần nhớ:** VARCHAR2 phù hợp với JSON nhỏ; CLOB lưu JSON văn bản lớn; BLOB lưu JSON bytes theo UTF-8. Dùng IS JSON để bảo vệ cú pháp, STRICT để yêu cầu JSON chuẩn, WITH UNIQUE KEYS để cấm duplicate object keys và NOT NULL để bắt buộc có document. IS JSON không xác thực cấu trúc nghiệp vụ. Oracle 19c dùng VARCHAR2/CLOB/BLOB; native JSON type với OSON bắt đầu từ 21c. Hãy chọn kiểu lưu trữ theo payload và workload, kiểm tra dữ liệu cũ trước khi bật constraint, rồi đo hiệu năng truy vấn bằng SQL/JSON functions và index phù hợp.
