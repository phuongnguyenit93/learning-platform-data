# Cập nhật JSON và kiểm tra cú pháp JSON_TRANSFORM/JSON_MERGEPATCH theo phiên bản

JSON thường được lưu như một tài liệu trong cột VARCHAR2, CLOB hoặc BLOB. Khi một phần thông tin thay đổi, ứng dụng không nhất thiết phải đọc toàn bộ tài liệu, sửa ở tầng client rồi ghi đè lại toàn bộ nội dung. Oracle cung cấp hai SQL function để cập nhật JSON theo cách khai báo: **JSON_TRANSFORM** và **JSON_MERGEPATCH**.

Hai function có mục tiêu gần nhau nhưng cách mô tả thay đổi khác nhau. JSON_TRANSFORM nhận các thao tác cụ thể như SET, REPLACE, INSERT, REMOVE, APPEND, RENAME và KEEP, mỗi thao tác nhắm đến một SQL/JSON path. JSON_MERGEPATCH nhận một tài liệu patch theo chuẩn RFC 7396 và hợp nhất patch đó với tài liệu đích. Merge Patch rất thuận tiện khi cập nhật các object, nhưng có quy tắc đặc biệt: một member trong patch có giá trị null được hiểu là yêu cầu xóa member đó. Nó không dùng để đặt một property thành JSON null và không thể sửa riêng một phần tử array.

Điểm cần kiểm tra trước khi triển khai là phiên bản database. JSON_MERGEPATCH được giới thiệu trong Oracle Database 19c, Release 19.1. JSON_TRANSFORM có trong Oracle Database 21c và được backport về Oracle Database 19c từ Release Update 19.10; database 19.3 ban đầu không có function này. Vì vậy, chỉ thấy tài liệu 19c có trang JSON_TRANSFORM không đủ để kết luận mọi bản cài 19c đều hỗ trợ. Cần xác nhận RU/patch level thực tế và thử compile/chạy một câu lệnh tối thiểu.

Bài học thuộc nhóm **JSON và XML** của Database Engine Relational Oracle. Nội dung tập trung vào cách cập nhật tài liệu JSON, cú pháp và semantics của JSON_TRANSFORM/JSON_MERGEPATCH, cách dùng trong SELECT và UPDATE, khác biệt giữa null và remove, xử lý array, return type, kiểm tra phiên bản, phương án thay thế trên bản cũ, concurrency và bài thực hành.

Sau bài này, bạn có thể:

- Phân biệt JSON_TRANSFORM với JSON_MERGEPATCH.
- Xác định phiên bản/RU hỗ trợ từng function.
- Dùng JSON_TRANSFORM để thêm, thay, xóa, đổi tên và giữ lại các path cần thiết.
- Dùng SET, REPLACE, INSERT, REMOVE, APPEND, RENAME và KEEP đúng semantics.
- Kiểm soát ON EXISTING, ON MISSING và ON NULL.
- Dùng FORMAT JSON để chèn object, array hoặc boolean thay vì một JSON string.
- Cập nhật JSON object và array theo SQL/JSON path.
- Dùng JSON_MERGEPATCH theo RFC 7396 và hiểu quy tắc null/array.
- Chọn RETURNING CLOB/BLOB khi kết quả có thể vượt VARCHAR2(4000).
- Phân biệt function tạo tài liệu JSON mới với UPDATE ghi kết quả trở lại bảng.
- Kiểm tra feature availability trên database thật thay vì suy luận từ nhãn 19c/21c.
- Dùng PL/SQL JSON object types làm phương án thay thế khi JSON_TRANSFORM chưa có.
- Bảo vệ cập nhật khỏi lost update và kiểm tra số hàng được cập nhật.

> **Phạm vi ví dụ:** Các ví dụ cơ bản dùng VARCHAR2/CLOB JSON và cú pháp tương thích Oracle Database 19c khi có function tương ứng. JSON_MERGEPATCH có từ 19.1. JSON_TRANSFORM có từ 21c và được backport vào 19c RU 19.10; không có trên Oracle 19.3 nguyên bản. Native JSON datatype là tính năng khác, có từ 21c, và không phải điều kiện bắt buộc để dùng các function trên với VARCHAR2/CLOB/BLOB.

## 1. Mô hình cập nhật tài liệu JSON

Giả sử bảng lưu đơn hàng:

~~~sql
CREATE TABLE order_document_lab (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT ck_order_document_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

Một hàng có thể lưu tài liệu:

~~~json
{
  "orderId": 9001,
  "status": "NEW",
  "customer": {
    "customerId": 501,
    "name": "Nguyen An"
  },
  "total": 125.50,
  "note": null,
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 205, "quantity": 1}
  ]
}
~~~

Yêu cầu nghiệp vụ có thể là:

- Đổi status từ NEW sang PAID.
- Cập nhật customer.name.
- Thêm thuộc tính paidAt.
- Xóa thuộc tính legacyCode.
- Đặt note thành JSON null.
- Thêm một sản phẩm vào cuối items.
- Xóa một phần tử array hoặc thay phần tử ở vị trí cụ thể.

Với cách đọc-sửa-ghi ở client, ứng dụng thường phải:

1. SELECT toàn bộ payload.
2. Parse JSON ở ứng dụng.
3. Sửa object/array.
4. Serialize toàn bộ tài liệu.
5. UPDATE cột payload.

Quy trình đó có thể truyền nhiều dữ liệu qua mạng và tạo rủi ro ghi đè thay đổi của session khác nếu không có concurrency control. JSON_TRANSFORM và JSON_MERGEPATCH cho phép mô tả thay đổi ngay trong SQL, để database tạo tài liệu kết quả và ghi nó bằng một câu UPDATE.

## 2. Function chỉ trả tài liệu mới; UPDATE mới lưu thay đổi

Đây là điểm quan trọng nhất khi học hai function.

### 2.1. Dùng trong SELECT: chỉ tạo bản đã sửa trong kết quả

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.status' = 'PAID'
       ) AS updated_payload
FROM order_document_lab
WHERE order_id = 9001;
~~~

SELECT trả về tài liệu đã sửa cho query result. Cột PAYLOAD trong bảng vẫn giữ nguyên.

### 2.2. Dùng trong UPDATE: ghi tài liệu mới vào bảng

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              )
WHERE order_id = 9001;
~~~

Ở đây kết quả của JSON_TRANSFORM được gán lại cho cột PAYLOAD. Đây mới là thao tác cập nhật dữ liệu lưu trữ.

### 2.3. Cùng nguyên tắc với JSON_MERGEPATCH

Chỉ xem kết quả:

~~~sql
SELECT JSON_MERGEPATCH(
           payload,
           '{"status":"PAID"}'
       ) AS patched_payload
FROM order_document_lab
WHERE order_id = 9001;
~~~

Ghi kết quả:

~~~sql
UPDATE order_document_lab
SET payload = JSON_MERGEPATCH(
                  payload,
                  '{"status":"PAID"}'
              )
WHERE order_id = 9001;
~~~

### 2.4. Function không tự COMMIT

JSON_TRANSFORM và JSON_MERGEPATCH là SQL functions trả về giá trị. Chúng không tự COMMIT transaction. UPDATE vẫn tuân theo transaction semantics thông thường:

- UPDATE thành công tạo thay đổi chưa commit.
- COMMIT xác nhận thay đổi.
- ROLLBACK hủy thay đổi chưa commit.
- Row lock được giữ theo transaction cho đến khi transaction kết thúc.

Không nhầm tính atomic của một lần gọi JSON_TRANSFORM với việc transaction chứa câu UPDATE đã được commit.

## 3. JSON_TRANSFORM là gì?

JSON_TRANSFORM là SQL function nhận một JSON document và một hoặc nhiều modification operations. Mỗi operation có path xác định phần dữ liệu cần sửa và mô tả cách sửa.

### 3.1. Đặc điểm chính

- Có thể sửa nhiều vị trí trong một lần gọi.
- Các operation được thực hiện tuần tự theo thứ tự viết.
- Operation sau nhìn thấy kết quả của operation trước.
- Function tạo bản JSON đã sửa và trả về cho SQL.
- Nếu một operation phát sinh lỗi, toàn bộ lần gọi JSON_TRANSFORM thất bại; không có kết quả sửa dở dang được trả về.
- Có thể dùng trong SELECT để biến đổi tạm thời hoặc trong UPDATE để lưu kết quả.

### 3.2. Cú pháp khái quát

~~~sql
JSON_TRANSFORM(
    json_document,
    operation_1,
    operation_2,
    ...
    RETURNING return_type
    PASSING bind_value AS "variable_name"
)
~~~

RETURNING và PASSING là các phần tùy chọn theo cú pháp hỗ trợ. RETURNING xác định kiểu SQL của kết quả. PASSING truyền SQL values để tham chiếu trong SQL/JSON path expressions.

### 3.3. Các operation chính

| Operation | Mục đích | Hành vi mặc định đáng nhớ |
| --- | --- | --- |
| SET | Gán giá trị vào path | Thay giá trị nếu đã có; tạo path nếu thiếu |
| REPLACE | Thay giá trị đã tồn tại | Bỏ qua nếu path không tồn tại |
| INSERT | Chèn field/array element | Lỗi nếu object field đã tồn tại |
| REMOVE | Xóa field/array element | Bỏ qua nếu path không tồn tại |
| APPEND | Thêm phần tử vào cuối array | Lỗi nếu path không trỏ đến array |
| RENAME | Đổi tên object field | Bỏ qua nếu field không tồn tại |
| KEEP | Chỉ giữ các path được nêu | Xóa phần còn lại của tài liệu |

Không dùng tên operation thay cho việc đọc handler mặc định. SET và REPLACE gần nhau nhưng khác cách xử lý khi path không tồn tại.

## 4. SET: tạo mới hoặc thay giá trị

SET có hành vi giống UPSERT đối với path:

- Nếu path đã tồn tại, thay giá trị hiện tại.
- Nếu path chưa tồn tại, tạo dữ liệu tại vị trí được chỉ định khi có thể.

### 4.1. Thay status

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              )
WHERE order_id = 9001;
~~~

Nếu status đang là NEW, kết quả thành PAID. SQL string PAID được biểu diễn thành JSON string "PAID".

### 4.2. Thêm field mới

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.paidAt' = SYSTIMESTAMP
              )
WHERE order_id = 9001;
~~~

Nếu paidAt chưa tồn tại, SET tạo field. Nếu đã tồn tại, SET thay giá trị cũ.

### 4.3. SET với ERROR ON EXISTING

Nếu chỉ muốn tạo field mới và xem field đã tồn tại là lỗi:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.externalReference' = 'EXT-9001'
               ERROR ON EXISTING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Nếu externalReference đã tồn tại, operation phát sinh lỗi. Đây là cách biểu đạt rõ ràng hơn việc đọc trước rồi mới quyết định chèn.

### 4.4. SET với IGNORE ON MISSING

Nếu chỉ muốn thay field khi field đã có:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.customer.name' = 'An Nguyen'
               IGNORE ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Nếu path không khớp, tài liệu giữ nguyên ở operation này.

### 4.5. SET không đồng nghĩa thêm mọi cấp object cha

Nếu path cha như customer không tồn tại, việc tạo một nested path có thể phụ thuộc handler/path semantics và dữ liệu đầu vào. Hãy kiểm thử trường hợp thiếu object cha. Nếu cần tạo cả object cha, có thể SET object cha bằng FORMAT JSON trước, rồi sửa field con ở operation tiếp theo.

## 5. REPLACE: chỉ thay khi path tồn tại

REPLACE thay giá trị tại path đã có. Nếu path không tồn tại, mặc định bỏ qua thay vì tạo field mới.

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  REPLACE '$.status' = 'SHIPPED'
              )
WHERE order_id = 9001;
~~~

Nếu status tồn tại, giá trị thành SHIPPED. Nếu status không tồn tại, operation không thêm field.

### 5.1. REPLACE với ERROR ON MISSING

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REPLACE '$.status' = 'SHIPPED'
               ERROR ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Dùng khi sự tồn tại của path là điều kiện bắt buộc. Nếu field thiếu, lỗi giúp phát hiện document không đúng trạng thái mong đợi.

### 5.2. SET hay REPLACE?

| Nhu cầu | Operation |
| --- | --- |
| Có thì thay, chưa có thì tạo | SET |
| Chỉ thay nếu đã tồn tại | REPLACE |
| Bắt lỗi nếu path chưa tồn tại | REPLACE ... ERROR ON MISSING |
| Bắt lỗi nếu field đã tồn tại khi muốn tạo mới | SET ... ERROR ON EXISTING hoặc INSERT |

## 6. INSERT: chèn field hoặc phần tử array

INSERT yêu cầu vị trí đích phù hợp. Với object field, mặc định lỗi nếu field đã tồn tại. Với array, path chỉ định vị trí cần chèn.

### 6.1. Thêm field mới

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           INSERT '$.sourceSystem' = 'ERP'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Nếu sourceSystem đã tồn tại, mặc định operation lỗi. Nếu mục tiêu là tạo mới và cần phát hiện duplicate, hành vi mặc định này hữu ích.

### 6.2. INSERT array element

JSON array dùng chỉ số bắt đầu từ 0 trong SQL/JSON path.

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           INSERT '$.items[0]' =
               '{"productId":999,"quantity":1}'
               FORMAT JSON
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Phần tử mới được chèn vào vị trí đầu và các phần tử cũ dịch sang phải. FORMAT JSON khiến giá trị SQL string được parse thành JSON object. Không có FORMAT JSON thì nội dung đó được lưu thành một JSON string.

### 6.3. Chèn ở vị trí sau cuối array

Có thể dùng path array position sau phần tử cuối theo cú pháp SQL/JSON path được hỗ trợ, hoặc dùng APPEND để diễn đạt rõ mục tiêu thêm cuối mảng.

### 6.4. Chèn vượt quá cuối array

Theo semantics JSON_TRANSFORM, INSERT vào vị trí array vượt quá chỉ số cuối có thể kéo dài array; các vị trí trung gian được lấp bằng JSON null. Cần cẩn thận vì kết quả có thể chứa null ở những vị trí mà nghiệp vụ không mong muốn.

## 7. APPEND: thêm phần tử cuối array

APPEND phù hợp khi muốn thêm một phần tử vào cuối array.

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  APPEND '$.items' =
                      '{"productId":310,"quantity":3}'
                      FORMAT JSON
              )
WHERE order_id = 9001;
~~~

Nếu items là array, object mới được thêm vào cuối. Nếu path không trỏ tới array, mặc định phát sinh lỗi.

### 7.1. Tạo array nếu path chưa tồn tại

Có thể chọn CREATE ON MISSING cho APPEND trong những trường hợp cú pháp cho phép:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           APPEND '$.tags' = 'priority'
               CREATE ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

CREATE ON MISSING tạo một singleton array tại path nếu path chưa có. Hãy phân biệt tình huống path không tồn tại với path đã tồn tại nhưng không phải array.

### 7.2. APPEND khác INSERT

- APPEND diễn đạt rõ việc thêm vào cuối array.
- INSERT cho phép chọn vị trí cụ thể và có thể làm các phần tử hiện có dịch chuyển.
- SET tại một array index thay thế hoặc tạo phần tử theo handler.

## 8. REMOVE: xóa field hoặc array element

REMOVE xóa dữ liệu khớp path.

### 8.1. Xóa field

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  REMOVE '$.legacyCode'
              )
WHERE order_id = 9001;
~~~

Nếu legacyCode không tồn tại, mặc định không phát sinh lỗi.

### 8.2. Xóa phần tử array

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REMOVE '$.items[1]'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Phần tử ở vị trí 1 bị loại bỏ và các phần tử phía sau dịch chuyển. Chỉ số array bắt đầu từ 0.

### 8.3. Bắt lỗi khi path không tồn tại

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REMOVE '$.legacyCode' ERROR ON MISSING
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Dùng ERROR ON MISSING khi việc không tìm thấy field là dấu hiệu document không đúng contract.

### 8.4. Không REMOVE root

Không thể dùng REMOVE '$' để xóa toàn bộ document root. Nếu cần thay tài liệu hoàn toàn, hãy gán document mới bằng UPDATE hoặc dùng operation phù hợp.

## 9. RENAME: đổi tên object field

RENAME đổi tên field được path chỉ định. Giá trị field được giữ nguyên.

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           RENAME '$.customer.fullName' = 'name'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Expression sau dấu bằng phải là SQL string làm tên mới. Nếu path không tồn tại, mặc định bỏ qua; có thể dùng ERROR ON MISSING khi cần.

RENAME áp dụng cho object field, không phải đổi tên phần tử array. Nếu muốn đổi cấu trúc array, dùng SET/INSERT/REMOVE phù hợp.

## 10. KEEP: chỉ giữ các path được chọn

KEEP xóa những phần dữ liệu không được các path chỉ định giữ lại. Root object/array không bị xóa; nó trở thành object/array rỗng nếu không còn thành phần phù hợp.

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           KEEP '$.orderId',
                '$.status',
                '$.total'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Kết quả chỉ giữ orderId, status và total cùng phần cấu trúc cha cần thiết. KEEP hữu ích khi tạo bản JSON đã lọc field trước khi gửi cho client.

### 10.1. KEEP cần được dùng cẩn thận

KEEP là thao tác loại bỏ phần lớn dữ liệu ngoài các path được liệt kê. Nếu bỏ sót field cần thiết, field đó sẽ biến mất khỏi kết quả. Trước khi dùng để xuất dữ liệu, hãy kiểm tra output schema bằng test cases.

## 11. ON EXISTING, ON MISSING và ON NULL

Các handler cho phép định nghĩa hành vi khi path tồn tại, path không tồn tại hoặc SQL expression tạo ra NULL.

### 11.1. ON EXISTING

Áp dụng khi path khớp dữ liệu hiện có:

| Handler | Hành vi |
| --- | --- |
| ERROR ON EXISTING | Phát sinh lỗi |
| IGNORE ON EXISTING | Không thay đổi dữ liệu đã có |
| REPLACE ON EXISTING | Thay dữ liệu hiện có bằng giá trị mới |
| REMOVE ON EXISTING | Xóa dữ liệu đã có |

Không phải operation nào cũng hỗ trợ tất cả handler. Ví dụ INSERT mặc định ERROR ON EXISTING; SET mặc định REPLACE ON EXISTING.

### 11.2. ON MISSING

Áp dụng khi path không khớp:

| Handler | Hành vi |
| --- | --- |
| ERROR ON MISSING | Phát sinh lỗi |
| IGNORE ON MISSING | Không thay đổi dữ liệu |
| CREATE ON MISSING | Tạo dữ liệu tại path nếu operation hỗ trợ |

Ví dụ:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REPLACE '$.status' = 'PAID'
               ERROR ON MISSING
       )
FROM order_document_lab;
~~~

### 11.3. ON NULL

Áp dụng khi SQL result expression sau dấu bằng trả về SQL NULL:

| Handler | Hành vi |
| --- | --- |
| NULL ON NULL | Ghi JSON null tại vị trí đích |
| ERROR ON NULL | Phát sinh lỗi |
| IGNORE ON NULL | Không thay đổi dữ liệu |
| REMOVE ON NULL | Xóa dữ liệu tại vị trí đích |

Với các operation hỗ trợ ON NULL, mặc định thường là NULL ON NULL.

### 11.4. SQL NULL khác JSON null

Khi dùng SET:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.note' = NULL
               NULL ON NULL
       )
FROM order_document_lab;
~~~

Kết quả đặt property note thành JSON null.

Nếu dùng:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.note' = NULL
               REMOVE ON NULL
       )
FROM order_document_lab;
~~~

thì property note bị xóa.

Nếu dùng IGNORE ON NULL, giá trị hiện tại được giữ nguyên. Ba hành vi này khác nhau về ý nghĩa nghiệp vụ.

## 12. FORMAT JSON: chèn JSON value thay vì string

SQL string được chuyển thành JSON string nếu không chỉ định FORMAT JSON.

### 12.1. Không có FORMAT JSON

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.customer' =
               '{"customerId":501,"name":"An"}'
       )
FROM order_document_lab;
~~~

Giá trị customer trở thành một JSON string chứa văn bản có dấu ngoặc nhọn, không phải JSON object lồng nhau.

### 12.2. Có FORMAT JSON

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.customer' =
               '{"customerId":501,"name":"An"}'
               FORMAT JSON
       )
FROM order_document_lab;
~~~

Lúc này customer là JSON object.

### 12.3. Gán JSON boolean

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.allowPartialShipment' = 'true'
               FORMAT JSON
       )
FROM order_document_lab;
~~~

FORMAT JSON khiến string true được diễn giải thành JSON boolean true. Nếu bỏ FORMAT JSON, kết quả là JSON string "true".

### 12.4. Gán array

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.tags' = '["priority","online"]'
               FORMAT JSON
       )
FROM order_document_lab;
~~~

Không dùng FORMAT JSON cho dữ liệu không được kiểm soát hoặc không phải JSON well-formed. FORMAT JSON là lời khẳng định của người viết SQL rằng biểu thức chứa JSON hợp lệ.

## 13. Nhiều operation trong một lần JSON_TRANSFORM

Các operation được thực hiện tuần tự. Operation sau thấy kết quả operation trước.

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID',
                  SET '$.paidAt' = SYSTIMESTAMP,
                  REMOVE '$.temporaryFlag',
                  APPEND '$.history' = 'PAID'
              )
WHERE order_id = 9001;
~~~

Ví dụ này:

1. Đặt status thành PAID.
2. Thêm hoặc thay paidAt.
3. Xóa temporaryFlag nếu tồn tại.
4. Thêm PAID vào cuối history array.

Nếu operation thứ tư thất bại vì history không phải array, toàn bộ lần gọi JSON_TRANSFORM lỗi. Các operation trước không tạo ra một kết quả cập nhật dở dang.

### 13.1. Thứ tự operation có ý nghĩa

Ví dụ:

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.status' = 'PAID',
           RENAME '$.status' = 'paymentStatus'
       )
FROM order_document_lab;
~~~

Operation RENAME được áp dụng sau SET nên nó nhìn thấy field status vừa được cập nhật. Kết quả cuối có paymentStatus với giá trị PAID.

### 13.2. Đường dẫn phải phù hợp với cấu trúc tại thời điểm operation chạy

Nếu operation trước xóa object cha, operation sau sửa field con của object đó có thể không còn match. Hãy sắp xếp operation theo thứ tự tạo/đổi dữ liệu trước, xóa dữ liệu sau.

### 13.3. Atomicity của function và transaction của UPDATE

JSON_TRANSFORM atomic ở phạm vi một lần gọi function: hoặc mọi operation thành công, hoặc function không trả bản sửa dở. Câu UPDATE chứa function vẫn là một statement trong transaction; nếu statement thất bại, statement bị rollback theo SQL semantics. COMMIT/ROLLBACK vẫn do caller điều khiển.

## 14. RETURNING và kích thước kết quả

Kiểu dữ liệu trả về mặc định phụ thuộc kiểu input và release. Với input VARCHAR2, tài liệu Oracle 19c ghi mặc định kết quả là VARCHAR2(4000), ngay cả khi input column khai báo dài hơn. Với CLOB/BLOB, mặc định giữ kiểu đầu vào theo tài liệu 19c. Có thể chỉ định RETURNING rõ ràng.

### 14.1. Trả CLOB

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           SET '$.status' = 'PAID'
           RETURNING CLOB
       )
FROM order_document_lab;
~~~

RETURNING CLOB phù hợp khi kết quả có thể lớn hơn giới hạn VARCHAR2.

### 14.2. Trả BLOB

~~~sql
SELECT JSON_TRANSFORM(
           payload,
           REMOVE '$.internalNotes'
           RETURNING BLOB
       )
FROM order_document_lab;
~~~

BLOB JSON text phải tuân theo encoding UTF-8 theo quy tắc Oracle JSON.

### 14.3. Pretty output

Một số JSON SQL functions hỗ trợ PRETTY để định dạng output dễ đọc. Pretty-print có thể tăng kích thước chuỗi; không bật nếu output dùng cho storage hoặc truyền tải tối ưu mà không cần định dạng.

### 14.4. JSON native type

Từ Oracle Database 21c, có native JSON SQL datatype. Khi input là JSON type, output có thể giữ native JSON type theo quy tắc của release. Tuy nhiên, JSON_TRANSFORM vẫn có thể nhận VARCHAR2/CLOB/BLOB trên những phiên bản hỗ trợ function. Không cần chuyển cột sang native JSON chỉ để sử dụng JSON_TRANSFORM.

## 15. JSON_MERGEPATCH là gì?

JSON_MERGEPATCH áp dụng một tài liệu patch vào một tài liệu JSON đích theo chuẩn IETF RFC 7396.

- Target document: tài liệu hiện tại.
- Patch document: object mô tả những member cần thêm, thay hoặc xóa.
- Kết quả: tài liệu mới sau khi hợp nhất patch.

### 15.1. Cú pháp cơ bản

~~~sql
JSON_MERGEPATCH(target_document, patch_document)
~~~

Ví dụ:

~~~sql
SELECT JSON_MERGEPATCH(
           payload,
           '{"status":"PAID","source":"WEB"}'
       )
FROM order_document_lab
WHERE order_id = 9001;
~~~

Status được thay bằng PAID và source được thêm mới.

### 15.2. Dùng trong UPDATE

~~~sql
UPDATE order_document_lab
SET payload = JSON_MERGEPATCH(
                  payload,
                  '{"status":"PAID","source":"WEB"}'
              )
WHERE order_id = 9001;
~~~

Patch document là một JSON object. Các member của patch được áp dụng đệ quy với object đích theo RFC 7396.

## 16. Quy tắc null đặc biệt của JSON_MERGEPATCH

Đây là điểm dễ gây lỗi nghiệp vụ nhất.

### 16.1. Patch member bằng null nghĩa là xóa

Target:

~~~json
{
  "status": "NEW",
  "note": "Call customer",
  "priority": "HIGH"
}
~~~

Patch:

~~~json
{
  "note": null
}
~~~

Kết quả:

~~~json
{
  "status": "NEW",
  "priority": "HIGH"
}
~~~

Property note bị xóa.

### 16.2. Không thể dùng Merge Patch để đặt property thành JSON null

Nếu yêu cầu là giữ property note nhưng giá trị của nó phải là JSON null, patch:

~~~json
{
  "note": null
}
~~~

không làm điều đó; nó xóa note theo RFC 7396.

Dùng JSON_TRANSFORM:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.note' = NULL NULL ON NULL
              )
WHERE order_id = 9001;
~~~

### 16.3. Null ở patch khác SQL NULL ở tham số

JSON null là token null trong patch document. SQL NULL truyền vào target hoặc patch expression là một giá trị SQL NULL; theo tài liệu Oracle, nếu target hoặc patch document là SQL NULL thì kết quả JSON_MERGEPATCH cũng là SQL NULL.

Hãy kiểm tra riêng ba tình huống:

- SQL column là NULL.
- JSON document là literal null.
- Patch object có member mang JSON null.

Chúng không có cùng semantics.

## 17. JSON_MERGEPATCH xử lý array như thế nào?

JSON Merge Patch phù hợp nhất với JSON object. Với array, patch thay thế toàn bộ array tại member đó; không có thao tác chuẩn để sửa riêng một array element.

Target:

~~~json
{
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 205, "quantity": 1}
  ]
}
~~~

Patch:

~~~json
{
  "items": [
    {"productId": 101, "quantity": 3}
  ]
}
~~~

Kết quả:

~~~json
{
  "items": [
    {"productId": 101, "quantity": 3}
  ]
}
~~~

Phần tử productId 205 biến mất vì toàn bộ array bị thay thế.

### 17.1. Khi cần sửa một phần tử array

Dùng JSON_TRANSFORM:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.items[0].quantity' = 3
              )
WHERE order_id = 9001;
~~~

### 17.2. Khi cần append array

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  APPEND '$.items' =
                      '{"productId":310,"quantity":1}'
                      FORMAT JSON
              )
WHERE order_id = 9001;
~~~

### 17.3. Chọn Merge Patch hay Transform?

| Trường hợp | JSON_MERGEPATCH | JSON_TRANSFORM |
| --- | --- | --- |
| Thay nhiều object fields | Rất phù hợp | Phù hợp |
| Thêm member vào object | Phù hợp | Phù hợp |
| Xóa member bằng patch null | Có | Có REMOVE |
| Đặt field thành JSON null | Không trực tiếp | Có SET ... NULL ON NULL |
| Sửa riêng một array element | Không | Có |
| Append array element | Không | Có APPEND |
| Chèn array element vào vị trí | Không | Có INSERT |
| Nhận patch document sinh từ client | Rất phù hợp | Không cùng mô hình |
| Nhiều thao tác path cụ thể trong một lệnh | Patch mô tả bằng object | Rất phù hợp |

## 18. RETURNING và lỗi trong JSON_MERGEPATCH

JSON_MERGEPATCH có RETURNING clause để xác định SQL datatype của kết quả. Tài liệu Oracle 19c ghi mặc định RETURNING là VARCHAR2(4000). Nếu tài liệu lớn, hãy chỉ định kiểu LOB phù hợp.

### 18.1. Trả CLOB

~~~sql
SELECT JSON_MERGEPATCH(
           payload,
           '{"status":"PAID"}'
           RETURNING CLOB
       )
FROM order_document_lab;
~~~

### 18.2. Kiểm soát lỗi

JSON_MERGEPATCH hỗ trợ error clause:

- NULL ON ERROR: trả SQL NULL khi gặp lỗi; đây là default trong tài liệu Oracle 19c.
- ERROR ON ERROR: phát sinh Oracle error tương ứng.

Với dữ liệu nghiệp vụ quan trọng, ERROR ON ERROR giúp lỗi dữ liệu không bị chuyển thành NULL rồi tiếp tục âm thầm. Nếu chọn NULL ON ERROR, ứng dụng phải có cách phân biệt lỗi xử lý với document SQL NULL hợp lệ.

### 18.3. Target hoặc patch là SQL NULL

Nếu target expression hoặc patch expression là SQL NULL, JSON_MERGEPATCH trả SQL NULL. Hãy xử lý rõ trước khi gọi function nếu nghiệp vụ yêu cầu giữ tài liệu hiện tại, tạo object rỗng hoặc bỏ qua hàng.

## 19. So sánh JSON_TRANSFORM và JSON_MERGEPATCH

| Tiêu chí | JSON_TRANSFORM | JSON_MERGEPATCH |
| --- | --- | --- |
| Cách mô tả thay đổi | Operation và SQL/JSON path | Tài liệu patch JSON |
| Chuẩn | Oracle SQL function | RFC 7396 |
| Thao tác nhiều field | Có, theo thứ tự | Có, theo object merge |
| Array element | Sửa/chèn/xóa/append | Chỉ thay cả array |
| Set explicit JSON null | Có | Member null được hiểu là xóa |
| Xóa field | REMOVE | Patch member null |
| Conditional missing/existing | Handler theo operation | Semantics merge patch |
| Phù hợp patch do client gửi | Có thể nhưng client phải tạo operation | Rất phù hợp |
| Phù hợp sửa path cụ thể | Rất phù hợp | Ít linh hoạt hơn |
| Atomicity | Toàn bộ operation trong một lần gọi | Áp dụng patch như một phép merge |
| Phiên bản | 21c; backport 19c RU 19.10 | 19c Release 19.1 |

### 19.1. Quy tắc chọn nhanh

- Dùng JSON_MERGEPATCH nếu client đã gửi một merge-patch document và cấu trúc chủ yếu là object.
- Dùng JSON_TRANSFORM nếu cần sửa path chính xác, xử lý array hoặc phân biệt set-null với remove.
- Dùng SQL thuần nếu thay đổi chỉ là một field quan hệ được tách thành cột.
- Dùng PL/SQL JSON object types nếu database chưa có JSON_TRANSFORM hoặc logic sửa tài liệu phức tạp.

## 20. Phiên bản Oracle: mốc hỗ trợ cần nhớ

### 20.1. JSON_MERGEPATCH

Oracle Database 19c Release 19.1 liệt kê JSON_MERGEPATCH là SQL function mới để cập nhật JSON document một cách khai báo.

| Phiên bản | JSON_MERGEPATCH |
| --- | --- |
| Oracle 12.2/18c | Không có SQL function JSON_MERGEPATCH |
| Oracle 19c 19.1 trở lên | Có |
| Oracle 21c | Có |
| Oracle 23c/23ai | Có |

### 20.2. JSON_TRANSFORM

JSON_TRANSFORM là một phần của tính năng JSON trong Oracle 21c. Oracle backport function này vào Oracle Database 19c RU 19.10. Vì vậy:

| Phiên bản | JSON_TRANSFORM |
| --- | --- |
| Oracle 19c 19.3 ban đầu | Không có |
| Oracle 19c RU 19.10 trở lên | Có theo backport; xác nhận patch/RU thực tế |
| Oracle 21c | Có |
| Oracle 23c/23ai | Có |

Tài liệu Oracle 19c hiện có trang JSON_TRANSFORM và hướng dẫn sử dụng, nhưng trang tham chiếu chung không ghi rõ RU backport. Vì thế không nên chỉ nhìn URL tài liệu 19c để kết luận một database 19c cũ có function này.

### 20.3. Native JSON datatype là một mốc khác

Native SQL JSON datatype được giới thiệu từ Oracle Database 21c. Điều này không đồng nghĩa JSON_TRANSFORM cũng chỉ chạy từ 21c: function được backport về 19c RU 19.10 để xử lý VARCHAR2/CLOB/BLOB JSON.

### 20.4. Release Update và patch level

Khi nói database là 19c, phải biết chính xác RU:

- 19.3 là bản 19c ban đầu thường gặp trong các hệ thống cũ.
- 19.10 trở lên có backport JSON_TRANSFORM theo thông tin Oracle SQL Developer Advocate và hành vi được xác nhận trong các môi trường 19c RU mới.
- Các patch one-off hoặc bundle patch cũng có thể ảnh hưởng khả năng thực tế.

Không nâng cấp database chỉ để dùng một function nếu chưa đánh giá patch policy, support matrix và compatibility. Hãy kiểm tra với DBA và tài liệu RU được triển khai.

## 21. Kiểm tra khả năng hỗ trợ trên database thật

### 21.1. Xem version

~~~sql
SELECT banner
FROM v$version;
~~~

Hoặc:

~~~sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

### 21.2. Xem RU/patch level

DBA có thể xem inventory/patch level bằng công cụ OPatch ở máy Oracle Home:

~~~text
opatch lsinventory
~~~

Trong database, DBA cũng có thể kiểm tra SQL patch registry:

~~~sql
SELECT patch_id, patch_type, action, status, action_time, description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

DBA_REGISTRY_SQLPATCH cần quyền xem dictionary phù hợp. Version banner chỉ cho biết release, không phải lúc nào cũng cho biết đầy đủ mọi one-off patch.

### 21.3. Kiểm tra JSON_MERGEPATCH

~~~sql
SELECT JSON_MERGEPATCH(
           '{"a":1,"b":2}',
           '{"b":3}'
       ) AS result
FROM dual;
~~~

Kết quả mong đợi:

~~~json
{"a":1,"b":3}
~~~

### 21.4. Kiểm tra JSON_TRANSFORM

~~~sql
SELECT JSON_TRANSFORM(
           '{"a":1}',
           SET '$.b' = 2
       ) AS result
FROM dual;
~~~

Kết quả mong đợi:

~~~json
{"a":1,"b":2}
~~~

Nếu database báo function không tồn tại hoặc lỗi phân tích cú pháp, kiểm tra version/RU và patch inventory. Không kết luận function bị thiếu chỉ vì một ví dụ có cú pháp sai.

### 21.5. Kiểm tra từng operation

Một database có JSON_TRANSFORM không có nghĩa mọi path/operation bạn định dùng đều đã được kiểm thử. Hãy chạy test cho:

- SET trên path có sẵn và path thiếu.
- REMOVE trên path có sẵn và path thiếu.
- SET SQL NULL với NULL ON NULL và REMOVE ON NULL.
- FORMAT JSON với object/array/boolean.
- APPEND vào array.
- INSERT tại index cụ thể.
- RETURNING CLOB với tài liệu lớn.

## 22. Phương án thay thế khi JSON_TRANSFORM chưa có

Trên Oracle 19c dưới RU 19.10, JSON_MERGEPATCH vẫn có sẵn để cập nhật object theo RFC 7396. Nếu cần sửa array hoặc đặt field thành JSON null, có thể dùng PL/SQL JSON object types hoặc cập nhật tài liệu đầy đủ từ ứng dụng.

### 22.1. PL/SQL JSON_OBJECT_T

Oracle hỗ trợ các PL/SQL JSON object types như:

- JSON_ELEMENT_T: kiểu cơ sở cho JSON values.
- JSON_OBJECT_T: JSON object.
- JSON_ARRAY_T: JSON array.
- JSON_SCALAR_T: JSON scalar.

Có thể parse CLOB thành object, sửa field rồi serialize lại.

~~~sql
DECLARE
    l_doc CLOB;
    l_json JSON_OBJECT_T;
BEGIN
    SELECT payload
    INTO l_doc
    FROM order_document_lab
    WHERE order_id = 9001
    FOR UPDATE;

    l_json := JSON_OBJECT_T.parse(l_doc);
    l_json.put('status', 'PAID');
    l_json.remove('legacyCode');

    UPDATE order_document_lab
    SET payload = l_json.to_clob()
    WHERE order_id = 9001;

    COMMIT;
END;
/
~~~

Ví dụ minh họa API object types. Với production code, hãy xử lý SQL NULL, parse errors, object root type và transaction exceptions rõ ràng. FOR UPDATE giữ row lock trong khi document được parse và cập nhật; giữ transaction ngắn.

### 22.2. Sửa array bằng JSON_ARRAY_T

Có thể lấy array từ object bằng GET_ARRAY, rồi dùng các method của JSON_ARRAY_T như APPEND, PUT hoặc REMOVE theo API của release:

~~~sql
DECLARE
    l_doc CLOB;
    l_json JSON_OBJECT_T;
    l_items JSON_ARRAY_T;
BEGIN
    SELECT payload
    INTO l_doc
    FROM order_document_lab
    WHERE order_id = 9001
    FOR UPDATE;

    l_json := JSON_OBJECT_T.parse(l_doc);
    l_items := l_json.get_array('items');

    l_items.append(JSON_OBJECT_T.parse(
        '{"productId":310,"quantity":1}'
    ));

    l_json.put('items', l_items);

    UPDATE order_document_lab
    SET payload = l_json.to_clob()
    WHERE order_id = 9001;

    COMMIT;
END;
/
~~~

Nếu property items không tồn tại hoặc không phải array, GET_ARRAY có thể trả NULL hoặc phát sinh hành vi cần xử lý theo API. Production code cần kiểm tra trước khi gọi APPEND.

### 22.3. Ưu và nhược điểm PL/SQL object types

Ưu điểm:

- Có thể sửa object và array theo thủ tục.
- Có thể dùng trên release cũ hơn JSON_TRANSFORM nếu PL/SQL JSON types đã có.
- Hỗ trợ logic điều kiện phức tạp.

Nhược điểm:

- Code dài hơn SQL expression.
- Cần parse/serialize document.
- Có thể phải giữ row lock trong suốt quá trình xử lý.
- Cần xử lý object/array/scalar root và lỗi parse.

### 22.4. Không dùng hai câu UPDATE thay thế nếu cần một statement atomic

Nếu dùng JSON_MERGEPATCH hai lần để xóa field rồi thêm giá trị mới, hai UPDATE có thể là hai statement trong cùng transaction. Chúng có thể cùng transaction nếu không COMMIT ở giữa, nhưng cần lưu ý round-trip và error handling. Nếu chỉ một statement được yêu cầu và function phù hợp, JSON_TRANSFORM hoặc PL/SQL object manipulation có thể rõ ràng hơn.

## 23. Concurrency và lost update

JSON_TRANSFORM và JSON_MERGEPATCH giúp cập nhật ở database, nhưng row lock vẫn hoạt động ở cấp hàng của bảng. Chúng không tạo lock riêng cho từng JSON property.

### 23.1. Cập nhật cùng một hàng

Session A:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              )
WHERE order_id = 9001;
~~~

Session B muốn UPDATE cùng order_id sẽ phải chờ row lock của A được giải phóng theo transaction semantics.

### 23.2. Cập nhật theo cột hiện tại trong database

Điểm mạnh của biểu thức:

~~~sql
SET payload = JSON_TRANSFORM(payload, ...)
~~~

là function nhận giá trị cột hiện tại trong statement đang thực thi. Không cần client gửi lại toàn bộ tài liệu cũ đã đọc trước đó. Điều này giúp tránh một dạng lost update phổ biến do client ghi đè snapshot cũ.

### 23.3. Optimistic locking bằng version

Nếu ứng dụng đã đọc document trước đó và cần phát hiện bất kỳ thay đổi nào kể từ lần đọc:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID'
              ),
    version_no = version_no + 1
WHERE order_id = 9001
  AND version_no = :old_version;
~~~

Sau UPDATE, kiểm tra SQL%ROWCOUNT:

- 1: cập nhật thành công.
- 0: hàng không tồn tại hoặc version đã thay đổi; caller cần đọc lại và xử lý conflict.

### 23.4. Hai client sửa hai field khác nhau

Nếu cả hai client cùng gửi bản document đầy đủ đã đọc từ trước, client sau có thể ghi đè thay đổi của client trước. Nếu mỗi client gửi thao tác path và database chạy JSON_TRANSFORM trên cột hiện tại, khả năng giữ thay đổi độc lập tốt hơn, nhưng row-level transaction serialization vẫn áp dụng.

### 23.5. Không bỏ qua điều kiện WHERE

Luôn lọc đúng hàng cần cập nhật:

~~~sql
UPDATE order_document_lab
SET payload = JSON_TRANSFORM(payload, SET '$.status' = 'PAID')
WHERE order_id = :order_id
  AND JSON_VALUE(payload, '$.status') = 'NEW';
~~~

Điều kiện status có thể bảo vệ chuyển trạng thái theo optimistic business rule. Kiểm tra SQL%ROWCOUNT để biết có hàng nào thực sự được chuyển.

## 24. Index, constraint và dữ liệu sau cập nhật

### 24.1. CHECK IS JSON vẫn được áp dụng

Nếu cột có CHECK constraint:

~~~sql
CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
~~~

thì giá trị do JSON_TRANSFORM/JSON_MERGEPATCH trả về vẫn phải đáp ứng constraint khi UPDATE. Function không bỏ qua validation của cột.

### 24.2. JSON_TRANSFORM không đảm bảo business schema

Function có thể tạo tài liệu hợp lệ về cú pháp nhưng sai nghiệp vụ. Ví dụ SET status = 'UNKNOWN' vẫn có thể tạo JSON hợp lệ. Cần thêm business validation ở SQL/application layer.

### 24.3. Function-based index

Nếu có index trên JSON_VALUE(payload, '$.status'), UPDATE payload có thể làm index entry liên quan được duy trì theo cơ chế Oracle. DML update JSON vẫn có chi phí index maintenance.

### 24.4. JSON search index

JSON search index cũng cần cập nhật khi document thay đổi. Nếu workload cập nhật JSON thường xuyên và search index lớn, đo chi phí DML cùng chi phí query. Không chỉ đo thời gian function riêng lẻ.

### 24.5. LOB storage

Với CLOB/BLOB, kích thước document và kiểu storage có thể ảnh hưởng I/O, redo, undo và thời gian cập nhật. JSON_TRANSFORM mô tả thay đổi theo path nhưng không nên giả định mọi kiểu storage/release đều thực hiện cập nhật vật lý theo cùng một cách. Benchmark trên dữ liệu thực tế.

## 25. Lỗi thường gặp và cách chẩn đoán

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Function JSON_TRANSFORM không được nhận diện | Database 19c thấp hơn RU 19.10 hoặc patch chưa có | Kiểm tra RU/SQL patch registry và thử câu lệnh tối thiểu |
| JSON_MERGEPATCH không được nhận diện | Database trước 19c hoặc compatibility/environment không phù hợp | Kiểm tra release và SQL reference |
| ORA-40441 / JSON parse error | Input hoặc patch không phải JSON hợp lệ | Kiểm tra document, escape và JSON constraint |
| ORA-40442 / path expression error | SQL/JSON path sai cú pháp | Kiểm tra path và index array |
| Operation ERROR ON EXISTING | Path đã có dữ liệu | Chọn SET/REPLACE hoặc đổi handler |
| ERROR ON MISSING | Path không tồn tại | Kiểm tra document shape hoặc dùng IGNORE/CREATE nếu đúng nghiệp vụ |
| APPEND báo lỗi | Path không trỏ tới array | Xác minh path và datatype |
| JSON string xuất hiện thay cho object | Thiếu FORMAT JSON | Thêm FORMAT JSON cho JSON text expression |
| Field bị xóa khi muốn đặt null | Dùng JSON_MERGEPATCH member null | Dùng JSON_TRANSFORM SET ... NULL ON NULL |
| Array bị thay toàn bộ | Dùng JSON_MERGEPATCH cho member array | Dùng JSON_TRANSFORM để sửa phần tử |
| ORA-02290 | Kết quả vi phạm IS JSON/CHECK constraint | Kiểm tra output và constraint |
| ORA-12899 hoặc lỗi độ dài | Return type quá nhỏ | Dùng RETURNING CLOB/BLOB phù hợp |
| UPDATE không sửa hàng | WHERE không khớp hoặc business predicate sai | Kiểm tra SQL%ROWCOUNT và predicate |
| Client ghi đè thay đổi mới | Lost update từ snapshot cũ | Dùng path update trên cột hiện tại hoặc version predicate |

## 26. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Gọi JSON_TRANSFORM là tự lưu tài liệu | Function trả tài liệu mới; phải UPDATE cột để lưu |
| Gọi JSON_MERGEPATCH là tự lưu tài liệu | Cũng cần UPDATE để ghi kết quả |
| JSON_MERGEPATCH và JSON_TRANSFORM giống nhau | Cách mô tả thay đổi và null/array semantics khác nhau |
| Merge Patch null đặt field thành JSON null | Theo RFC 7396, member null trong patch có nghĩa xóa |
| Merge Patch có thể sửa một array element | Nó thay toàn bộ array tại member đó |
| JSON_TRANSFORM SET và REPLACE giống hệt | SET tạo path thiếu; REPLACE mặc định bỏ qua path thiếu |
| INSERT luôn thay field cũ | INSERT mặc định lỗi khi object field đã tồn tại |
| APPEND hoạt động với mọi kiểu path | APPEND yêu cầu target là array, trừ handler tạo array khi missing |
| SQL string chứa object tự thành JSON object | Cần FORMAT JSON |
| SQL NULL và JSON null là một | SQL NULL là null của SQL; JSON null là scalar trong document |
| JSON_TRANSFORM chỉ có từ 21c | Có từ 21c và backport về 19c RU 19.10 |
| Mọi Oracle 19c đều có JSON_TRANSFORM | 19c 19.3 ban đầu không có; phải kiểm tra RU |
| JSON_MERGEPATCH chỉ có từ 21c | Có từ Oracle 19c Release 19.1 |
| Có native JSON type mới dùng được JSON_TRANSFORM | Function xử lý được VARCHAR2/CLOB/BLOB trên release hỗ trợ |
| Atomic function nghĩa là tự COMMIT | Atomicity của function không thay transaction control |

## 27. Checklist chọn function và triển khai

**Phiên bản**

- Database có đúng release/RU hỗ trợ không?
- JSON_MERGEPATCH có sẵn trên baseline 19c không?
- JSON_TRANSFORM có RU 19.10+ hoặc database 21c+ không?
- Đã chạy capability test trên database mục tiêu chưa?

**Semantics**

- Thay field, tạo field hay chỉ thay nếu field tồn tại?
- Field null cần xóa hay giữ JSON null?
- Có cần sửa một phần tử array hay thay cả array?
- Operation có cần ERROR ON MISSING/EXISTING không?
- SQL string có cần FORMAT JSON không?

**Datatype**

- Input là VARCHAR2, CLOB, BLOB hay native JSON?
- Kết quả có thể vượt VARCHAR2(4000) không?
- Có cần RETURNING CLOB/BLOB không?
- Constraint IS JSON và business validation có phù hợp không?

**Concurrency**

- WHERE có chọn đúng hàng không?
- Có cần version_no hoặc status predicate không?
- Đã kiểm tra SQL%ROWCOUNT chưa?
- Có giữ transaction ngắn không?

**Hiệu năng**

- Có index/search index cần maintenance không?
- Đã benchmark với document size thực tế chưa?
- Có thể chuyển field thường xuyên truy vấn thành relational column không?
- Có nên dùng SQL thuần thay vì sửa JSON không?

## 28. Bài thực hành tổng hợp

Lab này tạo tài liệu JSON, dùng cả hai function và so sánh null/array semantics.

### Bước 1 — Tạo bảng

~~~sql
CREATE TABLE json_update_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT ck_json_update_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

### Bước 2 — Nạp document

~~~sql
INSERT INTO json_update_lab(id, payload)
VALUES (
    1,
    '{
       "status":"NEW",
       "note":"Call customer",
       "customer":{"id":501,"name":"An"},
       "items":[
         {"productId":101,"quantity":2},
         {"productId":205,"quantity":1}
       ]
     }'
);

COMMIT;
~~~

### Bước 3 — JSON_TRANSFORM thay status và thêm timestamp

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.status' = 'PAID',
                  SET '$.paidAt' = SYSTIMESTAMP
              ),
    version_no = version_no + 1
WHERE id = 1;
~~~

### Bước 4 — Đặt note thành JSON null

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.note' = NULL NULL ON NULL
              )
WHERE id = 1;
~~~

### Bước 5 — Append một item

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  APPEND '$.items' =
                      '{"productId":310,"quantity":3}'
                      FORMAT JSON
              )
WHERE id = 1;
~~~

### Bước 6 — Sửa quantity của item đầu tiên

~~~sql
UPDATE json_update_lab
SET payload = JSON_TRANSFORM(
                  payload,
                  SET '$.items[0].quantity' = 5
              )
WHERE id = 1;
~~~

### Bước 7 — Dùng JSON_MERGEPATCH để xóa note và thêm source

~~~sql
UPDATE json_update_lab
SET payload = JSON_MERGEPATCH(
                  payload,
                  '{"note":null,"source":"PORTAL"}'
              )
WHERE id = 1;
~~~

Lúc này note bị xóa, không còn là JSON null.

### Bước 8 — Kiểm tra kết quả

~~~sql
SELECT
    id,
    JSON_VALUE(payload, '$.status') AS status,
    JSON_VALUE(payload, '$.source') AS source,
    JSON_VALUE(payload, '$.note') AS note,
    JSON_QUERY(payload, '$.items' RETURNING CLOB) AS items,
    version_no
FROM json_update_lab;
~~~

### Bước 9 — Kiểm tra tài liệu và constraint

~~~sql
SELECT id
FROM json_update_lab
WHERE payload IS NOT JSON STRICT WITH UNIQUE KEYS;

SELECT constraint_name, status, validated
FROM user_constraints
WHERE table_name = 'JSON_UPDATE_LAB';
~~~

### Bước 10 — Dọn lab (tùy chọn)

~~~sql
DROP TABLE json_update_lab PURGE;
~~~

Chỉ chạy nếu chắc chắn bảng thuộc lab và không cần dữ liệu nữa. DROP là DDL có implicit commit.

## 29. Câu hỏi tự kiểm tra

1. JSON_TRANSFORM nhận những thành phần nào?
2. JSON_MERGEPATCH dựa trên chuẩn nào?
3. Gọi JSON_TRANSFORM trong SELECT có lưu thay đổi vào bảng không?
4. Cần làm gì để lưu kết quả function?
5. SET khác REPLACE ở hành vi khi path thiếu thế nào?
6. INSERT xử lý thế nào nếu object field đã tồn tại?
7. APPEND dùng cho cấu trúc nào?
8. REMOVE xử lý thế nào nếu path không tồn tại?
9. RENAME đổi giá trị hay đổi tên field?
10. KEEP làm gì với phần dữ liệu không nằm trong các path được giữ?
11. Các operation trong JSON_TRANSFORM được thực hiện theo thứ tự nào?
12. Điều gì xảy ra nếu một operation trong lần gọi JSON_TRANSFORM lỗi?
13. NULL ON NULL khác REMOVE ON NULL thế nào?
14. Vì sao cần FORMAT JSON?
15. Array index trong SQL/JSON path bắt đầu từ số nào?
16. JSON_MERGEPATCH xử lý patch member null ra sao?
17. Vì sao Merge Patch không dùng để đặt property thành JSON null?
18. Merge Patch cập nhật array như thế nào?
19. Khi nào JSON_TRANSFORM phù hợp hơn JSON_MERGEPATCH?
20. RETURNING CLOB giải quyết vấn đề gì?
21. JSON_MERGEPATCH được giới thiệu từ release nào?
22. JSON_TRANSFORM có trong Oracle 19c từ RU nào?
23. Vì sao không thể kết luận mọi 19c đều hỗ trợ JSON_TRANSFORM?
24. Native JSON datatype và JSON_TRANSFORM có cùng mốc phiên bản không?
25. Làm thế nào kiểm tra feature availability trên database thật?
26. Dùng gì thay JSON_TRANSFORM trên 19c RU cũ?
27. JSON_TRANSFORM có tạo row lock riêng cho từng property không?
28. Làm sao phát hiện lost update từ client dùng snapshot cũ?
29. Vì sao cần kiểm tra SQL%ROWCOUNT sau UPDATE?
30. CHECK IS JSON có kiểm tra quy tắc nghiệp vụ không?

**Gợi ý trả lời:**

1. JSON input, một hoặc nhiều modification operations, tùy chọn RETURNING/PASSING.
2. RFC 7396.
3. Không; SELECT chỉ trả bản đã sửa.
4. Gán kết quả function vào cột trong UPDATE.
5. SET tạo path thiếu; REPLACE mặc định bỏ qua path thiếu.
6. Mặc định lỗi.
7. JSON array.
8. Mặc định bỏ qua.
9. Đổi tên field, giữ giá trị.
10. Xóa dữ liệu ngoài các path được chỉ định.
11. Theo thứ tự viết; mỗi operation thấy kết quả trước đó.
12. Toàn bộ lần gọi function thất bại, không có kết quả sửa dở.
13. NULL ON NULL đặt JSON null; REMOVE ON NULL xóa path.
14. Để SQL string được diễn giải là JSON object/array/boolean thay vì JSON string.
15. 0.
16. Xóa member tương ứng.
17. RFC 7396 định nghĩa null trong patch là remove.
18. Thay toàn bộ array ở member đó.
19. Khi cần path operations cụ thể, sửa array hoặc set JSON null.
20. Tránh giới hạn kết quả VARCHAR2(4000) khi tài liệu lớn.
21. Oracle Database 19c Release 19.1.
22. Backport vào Oracle Database 19c RU 19.10.
23. 19c 19.3 nguyên bản chưa có function; phải kiểm tra RU/patch.
24. Không; JSON_TRANSFORM được backport 19c RU 19.10, native JSON type từ 21c.
25. Kiểm tra version/RU và chạy một câu SQL thử tối thiểu.
26. JSON_MERGEPATCH cho object-centric patch hoặc PL/SQL JSON_OBJECT_T/JSON_ARRAY_T.
27. Không; row lock vẫn ở cấp hàng.
28. Dùng update path trên cột hiện tại, hoặc version predicate.
29. Để biết có hàng nào thực sự khớp điều kiện và được cập nhật.
30. Không; chỉ xác thực cú pháp JSON, business validation cần riêng.

## Tài liệu Oracle và tiêu chuẩn tham khảo

- [Oracle Database 19c SQL Language Reference — JSON_MERGEPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_MERGEPATCH.html): cú pháp, return type và error clause của JSON_MERGEPATCH.
- [Oracle Database 19c JSON Developer's Guide — Updating a JSON Document with JSON Merge Patch](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/updating-a-json-document-with-json-merge-patch.html): ví dụ và giới hạn RFC 7396.
- [Oracle Database 19c JSON Developer's Guide — Oracle SQL Function JSON_TRANSFORM](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/oracle-sql-function-json_transform.html): operation, handler và ví dụ JSON_TRANSFORM.
- [Oracle Database 19c SQL Language Reference — JSON_TRANSFORM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/json_transform.html): cú pháp SQL function và RETURNING clause.
- [Oracle Database 19c JSON Developer's Guide — Overview of Inserting, Updating, and Loading JSON Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/overview-of-inserting-updating-loading-JSON-data.html): lựa chọn JSON_TRANSFORM, JSON_MERGEPATCH và PL/SQL JSON object types.
- [Oracle Database 19c New Features Guide — JSON_MERGEPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/newft/application-development.html): JSON_MERGEPATCH là tính năng mới của Oracle 19c.
- [Oracle Database 21c SQL Language Reference — JSON_TRANSFORM](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/JSON_TRANSFORM.html): function trong SQL Reference của 21c.
- [IETF RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): chuẩn mô tả semantics của JSON Merge Patch.

**Nguyên tắc cần nhớ:** JSON_TRANSFORM mô tả chính xác các thao tác trên path và phù hợp khi cần sửa array, đặt JSON null hoặc kết hợp nhiều thay đổi. JSON_MERGEPATCH nhận một patch document theo RFC 7396, thuận tiện cho object nhưng member null có nghĩa xóa và array bị thay toàn bộ. Cả hai function chỉ trả tài liệu đã biến đổi; muốn lưu phải dùng UPDATE. JSON_MERGEPATCH có từ Oracle 19c 19.1; JSON_TRANSFORM có từ 21c và được backport về 19c RU 19.10. Hãy xác nhận RU trên database mục tiêu, kiểm tra semantics null/array và chọn RETURNING phù hợp với kích thước tài liệu.
