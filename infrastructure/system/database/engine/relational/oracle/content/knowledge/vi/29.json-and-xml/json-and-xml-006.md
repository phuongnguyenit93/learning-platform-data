# ON ERROR, ON EMPTY và phân biệt JSON null với SQL NULL trong Oracle Database

Khi truy vấn JSON bằng SQL, một kết quả NULL có thể xuất hiện vì nhiều lý do: cột chứa tài liệu JSON đang là SQL NULL, field được hỏi không có trong object, field có giá trị JSON null, hoặc phép trích xuất gặp lỗi. Nếu gom tất cả trường hợp này thành một giá trị SQL NULL, ứng dụng có thể bỏ qua dữ liệu sai định dạng, hiểu nhầm field bị thiếu thành field được gửi rõ ràng là null, hoặc áp dụng sai quy tắc mặc định.

Oracle cung cấp các mệnh đề **ON ERROR** và **ON EMPTY** cho SQL/JSON query functions để quyết định cách xử lý lỗi và field không tồn tại. Hai mệnh đề có mục đích khác nhau:

- ON ERROR quy định kết quả khi quá trình đánh giá SQL/JSON gặp lỗi runtime, ví dụ JSON không hợp lệ, path trả về nhiều giá trị trong JSON_VALUE, hoặc giá trị không thể chuyển sang kiểu SQL yêu cầu.
- ON EMPTY quy định kết quả khi path hợp lệ nhưng không tìm thấy field/giá trị được yêu cầu trong JSON.

Để phân biệt **JSON null** với **SQL NULL**, cần hiểu kiểu dữ liệu đầu vào và hàm được dùng. JSON_VALUE trích scalar JSON thành scalar SQL; khi scalar đó là JSON null, kết quả mặc định là SQL NULL. JSON_EXISTS có thể kiểm tra field có tồn tại hay không và trả TRUE ngay cả khi giá trị field là JSON null. JSON_QUERY trả dữ liệu JSON, nên có thể giữ lại JSON null dưới dạng JSON hoặc văn bản JSON tùy kiểu dữ liệu và phiên bản.

Tài liệu này tập trung vào SQL/JSON functions của Oracle Database, đặc biệt JSON_VALUE, JSON_QUERY, JSON_EXISTS và JSON_TABLE. Các ví dụ chính dùng cú pháp tương thích với dòng Oracle 19c/21c; phần ghi chú nêu những khác biệt quan trọng khi dùng kiểu dữ liệu SQL JSON và các tính năng mới ở các phiên bản sau.

## 1. Ba khái niệm không được nhầm lẫn

Trước khi dùng ON ERROR và ON EMPTY, cần phân biệt ba trạng thái của dữ liệu JSON cùng một trạng thái ở tầng SQL.

### 1.1 SQL NULL ở cột chứa JSON

Đây là trường hợp cột database không chứa tài liệu JSON nào:

~~~sql
payload IS NULL
~~~

Ví dụ một dòng có payload là SQL NULL. Không có tài liệu để SQL/JSON path truy vấn.

### 1.2 Field không tồn tại trong tài liệu JSON

Tài liệu có hợp lệ nhưng object không chứa field được yêu cầu:

~~~json
{}
~~~

Path $.status không tìm thấy field status. Đây là trường hợp **empty/missing match** mà ON EMPTY được thiết kế để xử lý.

### 1.3 Field tồn tại và có giá trị JSON null

Tài liệu có field status, và giá trị của field là literal JSON null:

~~~json
{"status":null}
~~~

JSON null là một giá trị hợp lệ của ngôn ngữ JSON. Field tồn tại; giá trị không phải là một field bị thiếu.

### 1.4 Lỗi khi đánh giá JSON

Ví dụ tài liệu không phải JSON hợp lệ:

~~~text
{"status":
~~~

Hoặc path hợp lệ về cú pháp nhưng JSON_VALUE nhận nhiều giá trị hay nhận một object/array trong khi yêu cầu scalar. Đây là lỗi runtime được xử lý bởi ON ERROR (nếu là lỗi thuộc phạm vi của mệnh đề).

### 1.5 Bảng phân biệt

| Trạng thái | Ví dụ | Bản chất |
|---|---|---|
| SQL NULL | Cột payload là SQL NULL | Không có giá trị SQL chứa tài liệu JSON |
| Field missing | {} và truy vấn $.status | Tài liệu tồn tại, nhưng path không tìm thấy field |
| JSON null | {"status":null} | Field tồn tại, giá trị JSON là null |
| Runtime error | JSON hỏng hoặc path trả kiểu/số lượng không phù hợp | SQL/JSON evaluation gặp lỗi |

ON EMPTY không có nghĩa là “giá trị JSON rỗng”. Nó không đồng nghĩa với chuỗi JSON "", object {}, array [], hay SQL NULL. Nó nói về trường hợp path không tìm thấy kết quả.

## 2. ON ERROR là gì?

ON ERROR là error-handling clause của các SQL/JSON function và condition có hỗ trợ. Nó định nghĩa hành vi khi đánh giá JSON phát sinh lỗi runtime.

Các lựa chọn phổ biến:

| Mệnh đề | Hành vi |
|---|---|
| NULL ON ERROR | Trả SQL NULL thay vì raise lỗi |
| ERROR ON ERROR | Raise lỗi Oracle tương ứng |
| DEFAULT literal ON ERROR | Trả literal mặc định khi có lỗi; literal phải tương thích kiểu trả về |

Không phải mọi hàm đều hỗ trợ tất cả lựa chọn. Ví dụ JSON_QUERY còn hỗ trợ EMPTY ARRAY ON ERROR và EMPTY OBJECT ON ERROR; JSON_EXISTS dùng TRUE ON ERROR hoặc FALSE ON ERROR, mặc định là FALSE trong các phiên bản thông dụng.

### 2.1 NULL ON ERROR

Đây là hành vi mặc định của JSON_VALUE và nhiều SQL/JSON query functions:

~~~sql
SELECT JSON_VALUE(
         '{"amount":"not-a-number"}',
         '$.amount' RETURNING NUMBER
         NULL ON ERROR
       ) AS amount
FROM dual;
~~~

Giá trị JSON là string "not-a-number", không thể chuyển thành SQL NUMBER; với NULL ON ERROR, kết quả là SQL NULL.

Ưu điểm là truy vấn có thể tiếp tục khi gặp một số dữ liệu không đúng kỳ vọng. Nhược điểm là lỗi dữ liệu có thể bị che giấu nếu ứng dụng không kiểm tra hoặc ghi nhận trạng thái.

### 2.2 ERROR ON ERROR

Khi muốn dữ liệu sai cấu trúc phải làm truy vấn thất bại, dùng:

~~~sql
SELECT JSON_VALUE(
         '{"amount":"not-a-number"}',
         '$.amount' RETURNING NUMBER
         ERROR ON ERROR
       ) AS amount
FROM dual;
~~~

Oracle raise lỗi chuyển đổi thay vì trả NULL. Cách này hữu ích khi kiểm tra dữ liệu đầu vào, chạy batch cần fail-fast, hoặc trong giai đoạn phát triển để phát hiện path/kiểu dữ liệu không đúng.

### 2.3 DEFAULT ... ON ERROR

Có thể trả giá trị thay thế:

~~~sql
SELECT JSON_VALUE(
         '{"amount":"not-a-number"}',
         '$.amount' RETURNING NUMBER
         DEFAULT 0 ON ERROR
       ) AS amount
FROM dual;
~~~

Giá trị 0 phải phù hợp với kiểu trả về NUMBER. Literal mặc định được xác định tại thời điểm biên dịch câu SQL; không dùng biểu thức động tùy ý như một biến bind để thay cho literal mặc định.

Không chọn giá trị mặc định tùy tiện. Nếu 0 là giá trị nghiệp vụ hợp lệ, dùng DEFAULT 0 ON ERROR có thể làm dữ liệu lỗi trông giống dữ liệu hợp lệ. Chỉ dùng fallback khi quy tắc nghiệp vụ xác định rõ ý nghĩa của nó.

### 2.4 Lỗi nào thuộc phạm vi ON ERROR?

Các lỗi runtime thường gặp:

- Đầu vào không phải JSON well-formed.
- JSON_VALUE nhận object hoặc array trong khi cần một scalar.
- Path trả nhiều giá trị trong ngữ cảnh cần một scalar.
- Chuyển giá trị JSON sang kiểu SQL trong RETURNING không thành công.
- Buffer kiểu trả về không đủ chứa dữ liệu.

Mệnh đề ON ERROR không sửa lỗi cú pháp của chính câu SQL hoặc path expression. Một path expression viết sai cú pháp có thể bị phát hiện khi parse/compile câu lệnh; nó không được biến thành NULL ON ERROR.

## 3. ON EMPTY là gì?

ON EMPTY được dùng khi path expression hợp lệ nhưng không tìm thấy field hoặc giá trị cần lấy. Nó cho phép xử lý trường hợp thiếu field khác với những lỗi runtime còn lại.

Các lựa chọn thường dùng:

| Mệnh đề | Hành vi khi không có match |
|---|---|
| NULL ON EMPTY | Trả SQL NULL |
| ERROR ON EMPTY | Raise lỗi Oracle |
| DEFAULT literal ON EMPTY | Trả literal mặc định phù hợp kiểu kết quả |

### 3.1 NULL ON EMPTY

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.customerName'
         NULL ON EMPTY
         ERROR ON ERROR
       ) AS customer_name
FROM dual;
~~~

Field customerName không có trong tài liệu nên kết quả là SQL NULL. Nếu có lỗi runtime khác, ERROR ON ERROR vẫn được áp dụng.

### 3.2 ERROR ON EMPTY

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.customerName'
         ERROR ON EMPTY
         NULL ON ERROR
       ) AS customer_name
FROM dual;
~~~

Field customerName bị thiếu là lỗi theo hợp đồng dữ liệu; Oracle raise lỗi. Các lỗi runtime khác được xử lý bằng NULL ON ERROR.

Đây là cách hữu ích khi một field là bắt buộc, ví dụ orderId, tenantId hoặc createdAt. Nếu field bắt buộc biến mất, dữ liệu đầu vào nên bị từ chối thay vì âm thầm nhận NULL.

### 3.3 DEFAULT ... ON EMPTY

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.currency'
         RETURNING VARCHAR2(3)
         DEFAULT 'VND' ON EMPTY
         ERROR ON ERROR
       ) AS currency
FROM dual;
~~~

Nếu field currency không xuất hiện, kết quả là VND. Nếu path gặp lỗi runtime khác, truy vấn raise lỗi.

Literal mặc định phải tương thích kiểu trả về. Ví dụ DEFAULT 0 ON EMPTY cho RETURNING NUMBER, hoặc DEFAULT 'UNKNOWN' ON EMPTY cho RETURNING VARCHAR2.

## 4. Quan hệ ưu tiên giữa ON EMPTY và ON ERROR

Đây là quy tắc quan trọng:

**Nếu field bị thiếu và câu SQL có cả ON EMPTY lẫn ON ERROR, ON EMPTY quyết định kết quả cho riêng trường hợp missing-field.** ON ERROR xử lý các lỗi runtime khác.

Ví dụ:

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.customerName'
         RETURNING VARCHAR2(100)
         DEFAULT 'UNKNOWN' ON EMPTY
         ERROR ON ERROR
       ) AS customer_name
FROM dual;
~~~

- customerName không tồn tại: trả UNKNOWN.
- JSON hỏng, path trả object/array hoặc lỗi runtime khác: raise lỗi.
- customerName tồn tại với giá trị scalar hợp lệ: trả giá trị đó.
- customerName tồn tại với JSON null: JSON_VALUE trả SQL NULL theo semantics của scalar extraction; đây không phải trường hợp ON EMPTY.

### 4.1 Nếu chỉ có ON ERROR

~~~sql
JSON_VALUE(payload, '$.optionalField' ERROR ON ERROR)
~~~

Nếu path không tìm thấy field, trường hợp missing được xử lý theo ON ERROR, vì không có ON EMPTY riêng ghi đè. Do đó ERROR ON ERROR có thể khiến một field không có mặt làm phát sinh lỗi.

### 4.2 Nếu chỉ có ON EMPTY

~~~sql
JSON_VALUE(payload, '$.optionalField' NULL ON EMPTY)
~~~

Missing-field trả SQL NULL. Các lỗi runtime khác dùng hành vi mặc định của JSON_VALUE, thông thường là NULL ON ERROR.

### 4.3 Nếu bỏ cả hai mệnh đề

~~~sql
JSON_VALUE(payload, '$.optionalField')
~~~

Mặc định của JSON_VALUE là NULL ON ERROR; nếu path không tìm thấy field, kết quả cũng là SQL NULL. Do đó chỉ nhìn kết quả NULL không thể biết field bị thiếu, field chứa JSON null, đầu vào SQL NULL hay có lỗi bị xử lý bằng mặc định.

## 5. JSON_VALUE: trích scalar và các trường hợp NULL

JSON_VALUE lấy một scalar JSON và chuyển thành một giá trị SQL. Scalar có thể là string, number, Boolean hoặc null. Nếu path trỏ tới object hoặc array trong khi hàm cần scalar, đó là lỗi theo semantics của hàm.

### 5.1 Ví dụ cơ bản

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42,"name":"Lan"}}',
         '$.customer.name'
         RETURNING VARCHAR2(100)
       ) AS customer_name
FROM dual;
~~~

Kết quả là SQL string Lan.

### 5.2 Path không tìm thấy field

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42}}',
         '$.customer.name'
         RETURNING VARCHAR2(100)
         NULL ON EMPTY
       ) AS customer_name
FROM dual;
~~~

Kết quả là SQL NULL do NULL ON EMPTY.

### 5.3 Field có JSON null

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42,"name":null}}',
         '$.customer.name'
         RETURNING VARCHAR2(100)
       ) AS customer_name
FROM dual;
~~~

Kết quả cũng là SQL NULL, nhưng nguyên nhân khác: path đã tìm thấy scalar JSON null, và JSON_VALUE ánh xạ JSON null sang SQL NULL.

### 5.4 Field có object hoặc array

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42,"name":"Lan"}}',
         '$.customer'
         RETURNING VARCHAR2(100)
         ERROR ON ERROR
       )
FROM dual;
~~~

Path $.customer trỏ tới object. JSON_VALUE yêu cầu scalar nên phát sinh lỗi; ERROR ON ERROR làm lỗi được trả về caller thay vì biến thành SQL NULL.

### 5.5 Kiểu trả về và lỗi chuyển đổi

~~~sql
SELECT JSON_VALUE(
         '{"quantity":"abc"}',
         '$.quantity'
         RETURNING NUMBER
         DEFAULT 0 ON EMPTY
         ERROR ON ERROR
       ) AS quantity
FROM dual;
~~~

Field tồn tại nhưng string abc không thể chuyển thành NUMBER. Đây là lỗi kiểu/convert, không phải missing-field; ERROR ON ERROR xử lý lỗi đó. DEFAULT 0 ON EMPTY không áp dụng.

## 6. Phân biệt JSON null với SQL NULL

Hai từ null có ý nghĩa khác nhau:

- **JSON null** là một literal và là một giá trị trong ngôn ngữ JSON.
- **SQL NULL** là trạng thái null của kiểu dữ liệu SQL, thường biểu diễn giá trị không có, chưa biết hoặc không áp dụng.

Trong SQL, chữ NULL thường được viết hoa để phân biệt với literal JSON null.

### 6.1 JSON null trong tài liệu JSON văn bản

Với cột VARCHAR2, CLOB hoặc BLOB chứa JSON dạng văn bản:

~~~json
{"status":null}
~~~

Toàn bộ tài liệu là một SQL value không null. Nhưng khi gọi:

~~~sql
JSON_VALUE(payload, '$.status')
~~~

Oracle trả SQL NULL. JSON null không được trả thành chuỗi SQL 'null'.

### 6.2 SQL NULL trong cột chứa JSON

~~~sql
SELECT JSON_VALUE(
         CAST(NULL AS VARCHAR2(100)),
         '$.status'
       ) AS status
FROM dual;
~~~

Đầu vào là SQL NULL, không có tài liệu JSON để đọc. Kết quả là SQL NULL.

### 6.3 Missing field và JSON null có thể cùng cho JSON_VALUE = SQL NULL

Hai tài liệu:

~~~json
{}
~~~

~~~json
{"status":null}
~~~

Khi dùng JSON_VALUE(payload, '$.status') với cách xử lý mặc định, cả hai có thể cho kết quả SQL NULL. JSON_VALUE trả scalar SQL, nên nó không thể biểu diễn sự khác biệt giữa field bị thiếu và scalar JSON null bằng chính giá trị trả về đó.

### 6.4 JSON_EXISTS giúp nhận biết field có tồn tại

JSON_EXISTS kiểm tra path có match một giá trị JSON hay không. JSON null vẫn là một giá trị, vì vậy path tới field chứa JSON null vẫn tồn tại:

~~~sql
SELECT
    CASE
        WHEN JSON_EXISTS('{"status":null}', '$.status')
        THEN 'PRESENT'
        ELSE 'MISSING'
    END AS status_presence
FROM dual;
~~~

Kết quả là PRESENT.

Với object rỗng:

~~~sql
SELECT
    CASE
        WHEN JSON_EXISTS('{}', '$.status')
        THEN 'PRESENT'
        ELSE 'MISSING'
    END AS status_presence
FROM dual;
~~~

Kết quả là MISSING.

### 6.5 Dùng JSON_EXISTS và JSON_VALUE cùng nhau

Đây là mẫu hữu ích để tách field bị thiếu khỏi field có mặt nhưng được trích ra thành SQL NULL:

~~~sql
SELECT
    CASE
        WHEN payload IS NULL THEN
            'SQL NULL DOCUMENT'
        WHEN NOT JSON_EXISTS(payload, '$.status') THEN
            'FIELD MISSING'
        WHEN JSON_VALUE(
                 payload,
                 '$.status'
                 RETURNING VARCHAR2(100)
             ) IS NULL THEN
            'FIELD PRESENT, SQL EXTRACTION IS NULL'
        ELSE
            'FIELD PRESENT WITH VALUE'
    END AS status_state
FROM json_documents;
~~~

Kết quả FIELD PRESENT, SQL EXTRACTION IS NULL có thể bao gồm JSON null; với kiểu trả về ký tự, chuỗi JSON rỗng "" cũng cần được xem xét vì Oracle SQL xem chuỗi ký tự có độ dài zero là SQL NULL. Nếu nghiệp vụ phải phân biệt JSON null với empty JSON string, hãy giữ dữ liệu ở dạng JSON hoặc kiểm tra JSON type thay vì chỉ dựa vào JSON_VALUE trả VARCHAR2.

## 7. JSON_EXISTS: kiểm tra sự tồn tại, không trích giá trị

JSON_EXISTS phù hợp khi câu hỏi chỉ là field/path có tồn tại hay không. Nó không trả scalar value.

~~~sql
SELECT id
FROM json_documents
WHERE JSON_EXISTS(payload, '$.status');
~~~

Điều kiện này trả TRUE khi path match, kể cả khi giá trị tại path là JSON null.

### 7.1 JSON_EXISTS không dùng ON EMPTY

JSON_EXISTS là condition, không phải function trích field theo kiểu JSON_VALUE. Nó không có ON EMPTY như JSON_VALUE/JSON_QUERY. Với lỗi đánh giá, nó có FALSE ON ERROR hoặc TRUE ON ERROR tùy nhu cầu; mặc định thông dụng là FALSE ON ERROR.

~~~sql
SELECT id
FROM json_documents
WHERE JSON_EXISTS(
        payload,
        '$.status'
        FALSE ON ERROR
      );
~~~

Không dùng FALSE ON ERROR để che dữ liệu JSON hỏng nếu ứng dụng cần từ chối dữ liệu sai. Khi cần xác thực dữ liệu, dùng constraint IS JSON, quy trình validation hoặc truy vấn với ERROR ON ERROR phù hợp.

### 7.2 EXISTS không cho biết giá trị là null

JSON_EXISTS(payload, '$.status') trả TRUE cho cả:

- {"status":"ACTIVE"}
- {"status":0}
- {"status":false}
- {"status":[]}
- {"status":{}}
- {"status":null}

Nếu cần biết giá trị có phải JSON null hay không, cần kiểm tra thêm kiểu JSON hoặc giữ lại biểu diễn JSON bằng JSON_QUERY/kiểu SQL JSON.

## 8. JSON_QUERY: trả lại dữ liệu JSON

JSON_QUERY được dùng để lấy object, array hoặc một tập giá trị JSON theo path. Khác với JSON_VALUE, nó trả JSON data dưới dạng văn bản JSON hoặc kiểu SQL JSON trong phiên bản/cấu hình hỗ trợ.

### 8.1 Trích một object

~~~sql
SELECT JSON_QUERY(
         '{"customer":{"id":42,"name":"Lan"}}',
         '$.customer'
         RETURNING CLOB
       ) AS customer_json
FROM dual;
~~~

Kết quả là một đoạn JSON biểu diễn object customer.

### 8.2 JSON null được giữ dưới dạng JSON khi kiểu trả về hỗ trợ

Với Oracle Database hỗ trợ SQL data type JSON và JSON_QUERY ... RETURNING JSON, có thể giữ JSON null như một JSON value:

~~~sql
SELECT JSON_QUERY(
         JSON('{"status":null}'),
         '$.status'
         RETURNING JSON
       ) AS status_json
FROM dual;
~~~

Kết quả là một giá trị JSON null, không phải SQL NULL. Đây là khác biệt quan trọng khi làm việc với native JSON data type.

Với JSON lưu dưới dạng VARCHAR2/CLOB hoặc khi trả về dạng văn bản, JSON_QUERY có thể trả văn bản JSON null nếu cấu hình/phiên bản cho phép trả scalar. Trước Oracle Database 21c, hỗ trợ RFC 8259 cho scalar JSON ở top level có giới hạn; có thể cần WITH WRAPPER để trả scalar trong một array.

### 8.3 Dùng WITH WRAPPER cho scalar trên phiên bản cũ

~~~sql
SELECT JSON_QUERY(
         '{"status":null}',
         '$.status'
         WITH WRAPPER
         RETURNING VARCHAR2(100)
       ) AS status_json
FROM dual;
~~~

WITH WRAPPER đặt kết quả vào một array JSON. Với JSON null, nội dung JSON được bọc tương ứng như [null]. Cú pháp và khả năng trả scalar không wrapper phụ thuộc COMPATIBLE và phiên bản Oracle.

### 8.4 ON ERROR và ON EMPTY của JSON_QUERY

JSON_QUERY có các cách xử lý lỗi như NULL ON ERROR, ERROR ON ERROR, EMPTY ARRAY ON ERROR và EMPTY OBJECT ON ERROR trong các phiên bản hỗ trợ. ON EMPTY có thể trả NULL, raise lỗi, hoặc trả empty array/object tùy cú pháp/phiên bản.

~~~sql
SELECT JSON_QUERY(
         payload,
         '$.preferences'
         RETURNING CLOB
         EMPTY ARRAY ON EMPTY
         ERROR ON ERROR
       ) AS preferences_json
FROM json_documents;
~~~

Nếu path không match, kết quả là []. Nếu xảy ra lỗi runtime khác, truy vấn raise lỗi. Hãy kiểm tra cú pháp được hỗ trợ trong release đang chạy, đặc biệt với EMPTY ARRAY ON EMPTY và EMPTY OBJECT ON EMPTY.

## 9. JSON_TABLE: xử lý JSON theo hàng và cột

JSON_TABLE chuyển JSON thành một bảng quan hệ ảo. Nó có hai tầng path:

1. **Row path:** xác định JSON value nào tạo ra một dòng.
2. **Column path:** lấy field từ mỗi row source để đưa vào các cột quan hệ.

Vì có hai tầng, cần hiểu rõ lỗi ở row path khác lỗi ở column path.

### 9.1 Ví dụ cơ bản

Giả sử tài liệu:

~~~json
{
  "orderId": 1001,
  "items": [
    {"sku": "A10", "quantity": 2},
    {"sku": "B20", "quantity": 5}
  ]
}
~~~

Có thể tách các phần tử trong items thành các dòng:

~~~sql
SELECT jt.order_id,
       jt.sku,
       jt.quantity
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             sku      VARCHAR2(30) PATH '$.sku',
             quantity NUMBER PATH '$.quantity'
         )
     ) jt;
~~~

Mỗi phần tử array tạo một row source. Các cột được lấy tương đối từ row source; nếu muốn lấy field cha, có thể dùng nested path hoặc thiết kế path phù hợp.

### 9.2 Row-level ON ERROR

Mệnh đề ở cấp JSON_TABLE xử lý đầu vào JSON không hợp lệ và row path không tìm được match:

~~~sql
SELECT jt.sku
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         ERROR ON ERROR
         COLUMNS (
             sku VARCHAR2(30) PATH '$.sku'
         )
     ) jt;
~~~

Với ERROR ON ERROR, JSON không hợp lệ hoặc row path không tìm được match sẽ raise lỗi. Với NULL ON ERROR (mặc định), dữ liệu không hợp lệ không tạo thêm rows; row path không match cũng trả về không có dòng. Do JSON_TABLE có thể đánh giá theo streaming, trong một số trường hợp rows đã được trả trước khi phần lỗi của tài liệu được phát hiện.

### 9.3 Row-level ON EMPTY

Có thể chỉ định cách xử lý khi row path không tìm thấy row source:

~~~sql
SELECT jt.sku
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         ERROR ON ERROR
         NULL ON EMPTY
         COLUMNS (
             sku VARCHAR2(30) PATH '$.sku'
         )
     ) jt;
~~~

ON EMPTY ghi đè hành vi ON ERROR cho riêng trường hợp row path không có match. Ở ví dụ này, lỗi JSON/runtime khác vẫn được raise; không có row source thì dùng NULL ON EMPTY theo semantics của JSON_TABLE. Lưu ý rằng row path không tạo row có thể biểu hiện thành không có rows trong result set; nó không phải một row mới có tất cả cột NULL.

### 9.4 Column-level error handling

JSON_TABLE cho phép định nghĩa cách xử lý lỗi cho từng cột. Handler ở column level có thể ghi đè hành vi mặc định được kế thừa từ row-level clause.

~~~sql
SELECT jt.sku,
       jt.quantity
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         NULL ON ERROR
         COLUMNS (
             sku      VARCHAR2(30) PATH '$.sku' ERROR ON ERROR,
             quantity NUMBER       PATH '$.quantity' NULL ON ERROR
         )
     ) jt;
~~~

Trong ví dụ:

- Lỗi khi trích sku được raise.
- Lỗi khi trích quantity trả SQL NULL.
- NULL ON ERROR ở cấp JSON_TABLE là mặc định chung cho các cột không có handler riêng và xử lý row-level.

### 9.5 Column-level ON EMPTY theo phiên bản

Các phiên bản Oracle mới có thể cho phép ON EMPTY ngay trong định nghĩa JSON_VALUE_COLUMN của JSON_TABLE. Ví dụ theo cú pháp được hỗ trợ ở release tương ứng:

~~~sql
SELECT jt.customer_name
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             customer_name VARCHAR2(100)
                 PATH '$.customer.name'
                 DEFAULT 'UNKNOWN' ON EMPTY
                 ERROR ON ERROR
         )
     ) jt;
~~~

Ở đây customer.name bị thiếu thì trả UNKNOWN, còn lỗi runtime khác thì raise lỗi. Cú pháp chi tiết của column-level ON EMPTY thay đổi theo release; hãy đối chiếu SQL Language Reference của phiên bản database trước khi dùng trên hệ thống cũ.

## 10. Dùng JSON_TABLE để phân biệt field missing và JSON null

JSON_TABLE hỗ trợ EXISTS column, dùng semantics của JSON_EXISTS, và value column, dùng semantics của JSON_VALUE. Kết hợp hai loại cột cho phép thấy sự khác nhau giữa field không tồn tại và field có giá trị JSON null.

~~~sql
SELECT jt.status_exists,
       jt.status_value
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             status_exists VARCHAR2(5)
                 EXISTS PATH '$.status',
             status_value VARCHAR2(100)
                 PATH '$.status'
         )
     ) jt;
~~~

Với tài liệu {}:

- status_exists là false.
- status_value là SQL NULL.

Với tài liệu {"status":null}:

- status_exists là true.
- status_value là SQL NULL.

Như vậy EXISTS giữ thông tin field có tồn tại; value column cung cấp scalar SQL nhưng có thể trả NULL cho JSON null. Đây là một mẫu quan trọng khi mapping JSON sang relational columns.

## 11. Ma trận kết quả theo từng hàm

Giả sử path là $.status, đầu vào lần lượt là SQL NULL, object rỗng và object có status:null.

| Đầu vào | JSON_EXISTS | JSON_VALUE mặc định | JSON_QUERY |
|---|---|---|---|
| SQL NULL document | FALSE/không có match theo điều kiện | SQL NULL | SQL NULL |
| {} | FALSE | SQL NULL (missing/error default) | SQL NULL theo ON EMPTY mặc định |
| {"status":null} | TRUE | SQL NULL | Giữ JSON null khi kiểu JSON/RETURNING cho phép; textual JSON null khi scalar return được hỗ trợ |

Đối với JSON_VALUE, ba trường hợp đầu có thể cùng cho SQL NULL. Vì vậy không dùng một phép IS NULL trên kết quả JSON_VALUE để kết luận field bị thiếu hay JSON null.

## 12. ON ERROR không thay thế kiểm tra JSON hợp lệ

Nếu cột chứa JSON văn bản, nên có constraint xác nhận dữ liệu là JSON:

~~~sql
CREATE TABLE json_documents (
    id      NUMBER PRIMARY KEY,
    payload CLOB,
    CONSTRAINT json_documents_payload_ck
        CHECK (payload IS JSON)
);
~~~

Constraint IS JSON ngăn tài liệu JSON văn bản sai cú pháp được ghi vào cột (SQL NULL vẫn có semantics riêng của constraint). Điều này giảm số lỗi runtime do dữ liệu không well-formed.

ON ERROR vẫn cần thiết vì:

- Path có thể trả nhiều kết quả khi hàm yêu cầu một scalar.
- JSON value có thể không chuyển được sang kiểu SQL yêu cầu.
- Kết quả có thể vượt giới hạn kiểu trả về.
- Các lỗi runtime khác vẫn có thể xuất hiện khi xử lý dữ liệu.

Lưu ý: ON ERROR không phải cách thay thế validation ở thời điểm ghi. Nếu dữ liệu sai, cần quyết định từ đầu là từ chối, cách ly, ghi log hay cho phép một fallback rõ ràng.

## 13. Strict và lax path mode

SQL/JSON path của Oracle hỗ trợ strict và lax mode. Mặc định thường là lax:

- **Lax mode** cho phép một số chuyển đổi/điều chỉnh cấu trúc để path truy cập dữ liệu linh hoạt hơn, ví dụ tự unwrap array trong một số trường hợp.
- **Strict mode** yêu cầu cấu trúc được truy cập phù hợp với path expression chặt chẽ hơn.

Hai chế độ ảnh hưởng đến việc path match và loại lỗi runtime có thể xảy ra. ON ERROR điều khiển cách xử lý lỗi runtime trong quá trình match path; nó không biến path expression sai cú pháp thành hợp lệ.

Khi dữ liệu đầu vào có schema rõ, strict path giúp phát hiện cấu trúc lệch sớm hơn. Khi cần tương thích nhiều hình dạng JSON, lax path có thể thuận tiện nhưng phải kiểm tra kỹ kết quả match.

## 14. Phân biệt ON EMPTY với các dạng rỗng khác

Những trường hợp dưới đây không tương đương:

| Giá trị/trạng thái | Ý nghĩa |
|---|---|
| Field missing | Không có member được path yêu cầu |
| JSON null | Có member, giá trị JSON là null |
| JSON "" | Có member, giá trị là empty JSON string |
| JSON [] | Có member, giá trị là array rỗng |
| JSON {} | Có member, giá trị là object rỗng |
| SQL NULL | Không có giá trị SQL |
| NULL ON EMPTY | Chính sách trả SQL NULL khi path không có match |

EMPTY ARRAY ON EMPTY hoặc EMPTY OBJECT ON EMPTY của JSON_QUERY tạo JSON array/object rỗng cho trường hợp path không match; nó không có nghĩa field hiện hữu chứa array/object rỗng.

## 15. Không nhầm ON EMPTY với NULL ON NULL khi tạo JSON

Khi tạo JSON từ dữ liệu quan hệ, Oracle có các mệnh đề NULL ON NULL và ABSENT ON NULL. Chúng thuộc SQL/JSON generation functions như JSON_OBJECT, JSON_ARRAY, JSON_OBJECTAGG và JSON_ARRAYAGG, không phải ON EMPTY của hàm truy vấn.

Ví dụ:

~~~sql
SELECT JSON_OBJECT(
         'name' VALUE CAST(NULL AS VARCHAR2(20))
         NULL ON NULL
       ) AS json_with_null
FROM dual;
~~~

Kết quả có member "name": null.

~~~sql
SELECT JSON_OBJECT(
         'name' VALUE CAST(NULL AS VARCHAR2(20))
         ABSENT ON NULL
       ) AS json_without_member
FROM dual;
~~~

Kết quả không có member name.

Thông thường:

- JSON_OBJECT và JSON_OBJECTAGG mặc định dùng NULL ON NULL.
- JSON_ARRAY và JSON_ARRAYAGG mặc định dùng ABSENT ON NULL.

Khi đọc JSON, ON EMPTY quyết định cách xử lý một path không tìm thấy. Khi sinh JSON, NULL ON NULL/ABSENT ON NULL quyết định cách SQL NULL đầu vào được biểu diễn trong tài liệu kết quả.

## 16. Ví dụ thực hành: tạo dữ liệu và quan sát bốn trạng thái

### 16.1 Tạo bảng thử nghiệm

~~~sql
CREATE TABLE json_state_lab (
    id      NUMBER PRIMARY KEY,
    payload CLOB,
    CONSTRAINT json_state_lab_ck CHECK (payload IS JSON)
);
~~~

### 16.2 Nạp các trường hợp

~~~sql
INSERT INTO json_state_lab VALUES (1, NULL);
INSERT INTO json_state_lab VALUES (2, '{}');
INSERT INTO json_state_lab VALUES (3, '{"status":null}');
INSERT INTO json_state_lab VALUES (4, '{"status":"ACTIVE"}');
INSERT INTO json_state_lab VALUES (5, '{"status":""}');
INSERT INTO json_state_lab VALUES (6, '{"status":[]}');
INSERT INTO json_state_lab VALUES (7, '{"status":{}}');
COMMIT;
~~~

### 16.3 So sánh EXISTS và VALUE

~~~sql
SELECT id,
       CASE
           WHEN payload IS NULL THEN 'SQL NULL DOCUMENT'
           WHEN JSON_EXISTS(payload, '$.status') THEN 'FIELD PRESENT'
           ELSE 'FIELD MISSING'
       END AS field_state,
       JSON_VALUE(
           payload,
           '$.status'
           RETURNING VARCHAR2(100)
           NULL ON EMPTY
           NULL ON ERROR
       ) AS status_value
FROM json_state_lab
ORDER BY id;
~~~

Quan sát:

- ID 1: input document là SQL NULL.
- ID 2: document tồn tại nhưng field thiếu.
- ID 3: field tồn tại, giá trị JSON null.
- ID 4: field tồn tại, có scalar string.
- ID 5: field tồn tại, JSON empty string; khi chuyển sang SQL character value có thể trở thành SQL NULL theo semantics chuỗi rỗng của Oracle.
- ID 6 và 7: path trỏ đến array/object, không phải scalar phù hợp với JSON_VALUE; với NULL ON ERROR, kết quả có thể là SQL NULL.

### 16.4 Dùng ERROR ON EMPTY để phát hiện field thiếu

~~~sql
SELECT JSON_VALUE(
         payload,
         '$.status'
         RETURNING VARCHAR2(100)
         ERROR ON EMPTY
         ERROR ON ERROR
       )
FROM json_state_lab
WHERE id = 2;
~~~

Truy vấn này raise lỗi vì field status không tồn tại. Nếu đổi id = 3, path tìm thấy JSON null nên ON EMPTY không được kích hoạt; JSON_VALUE trả SQL NULL theo semantics của JSON null.

### 16.5 Dùng JSON_QUERY để xem biểu diễn JSON

Với phiên bản và kiểu trả về hỗ trợ scalar JSON:

~~~sql
SELECT JSON_QUERY(
         payload,
         '$.status'
         RETURNING CLOB
         WITH WRAPPER
         EMPTY ARRAY ON EMPTY
         ERROR ON ERROR
       ) AS status_json
FROM json_state_lab
WHERE id IN (2, 3, 4, 5);
~~~

WITH WRAPPER bọc match trong một JSON array để xử lý scalar ổn định trên các phiên bản có giới hạn scalar return. EMPTY ARRAY ON EMPTY trả [] nếu field thiếu. Field JSON null có thể được biểu diễn thành [null]; string rỗng thành [""]; string thường thành ["ACTIVE"].

Trước khi chạy trên phiên bản cũ, kiểm tra khả năng trả scalar và cú pháp EMPTY ARRAY ON EMPTY của release đó. Nếu không hỗ trợ, dùng JSON_EXISTS để xác định presence và một truy vấn tương thích với phiên bản để hiển thị dữ liệu.

### 16.6 Dọn dữ liệu lab

~~~sql
DROP TABLE json_state_lab PURGE;
~~~

Chỉ chạy câu lệnh dọn dẹp nếu đây là bảng lab vừa tạo và không chứa dữ liệu cần giữ.

## 17. Chọn chính sách phù hợp với nghiệp vụ

Không có một lựa chọn ON ERROR/ON EMPTY đúng cho mọi ứng dụng. Chính sách phụ thuộc ý nghĩa của field.

| Loại field | Chính sách gợi ý | Lý do |
|---|---|---|
| ID bắt buộc | ERROR ON EMPTY ERROR ON ERROR | Thiếu ID hoặc dữ liệu sai phải bị từ chối |
| Field tùy chọn | NULL ON EMPTY ERROR ON ERROR | Cho phép không gửi field, nhưng dữ liệu sai phải được phát hiện |
| Field có default nghiệp vụ | DEFAULT ... ON EMPTY ERROR ON ERROR | Chỉ áp dụng default khi field vắng mặt |
| Field số cần fallback | NULL ON EMPTY DEFAULT ... ON ERROR chỉ khi có quy tắc rõ | Phân biệt thiếu field với lỗi convert |
| JSON fragment/object | Dùng JSON_QUERY, chọn wrapper và ON EMPTY phù hợp | Không ép object/array thành scalar |
| Kiểm tra presence | Dùng JSON_EXISTS | Phân biệt field thiếu với field chứa JSON null |
| Dữ liệu cần giữ JSON null | Dùng kiểu SQL JSON/JSON_QUERY RETURNING JSON khi được hỗ trợ | Tránh chuyển JSON null thành SQL NULL |

### 17.1 Không dùng DEFAULT để che lỗi dữ liệu

Ví dụ DEFAULT 0 ON ERROR có thể làm "abc" trở thành 0. Nếu 0 là số hợp lệ, hệ thống không còn biết input ban đầu bị sai. Với field bắt buộc, ERROR ON ERROR thường phù hợp hơn.

### 17.2 Tách validation khỏi extraction

Một pipeline dữ liệu tốt thường có các bước:

1. Xác nhận cột đầu vào có tài liệu JSON (không phải SQL NULL nếu bắt buộc).
2. Xác nhận JSON well-formed.
3. Xác nhận các field bắt buộc tồn tại.
4. Xác nhận kiểu và miền giá trị.
5. Trích xuất sang kiểu SQL.
6. Ghi nhận lỗi theo row/document để có thể xử lý lại.

Không nên gom mọi bước vào một JSON_VALUE(... NULL ON ERROR) rồi xem kết quả NULL như dữ liệu hợp lệ.

## 18. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ ON EMPTY bắt JSON null | JSON null là một giá trị được match | Dùng JSON_EXISTS để kiểm tra presence |
| Nghĩ ON ERROR và ON EMPTY giống nhau | Missing field và runtime error là hai trường hợp khác nhau | Đặt chính sách riêng cho từng trường hợp |
| Nghĩ JSON_VALUE trả chuỗi 'null' | JSON null được ánh xạ thành SQL NULL | Dùng JSON_EXISTS/JSON_QUERY khi cần giữ JSON representation |
| Dùng IS NULL để suy ra field bị thiếu | JSON null và missing đều có thể thành SQL NULL | Kết hợp JSON_EXISTS và JSON_VALUE |
| Dùng JSON_VALUE để lấy object | JSON_VALUE yêu cầu scalar | Dùng JSON_QUERY hoặc JSON_TABLE |
| Để mặc định NULL ON ERROR cho dữ liệu bắt buộc | Lỗi có thể bị che thành SQL NULL | Dùng ERROR ON ERROR và kiểm tra ON EMPTY |
| Dùng DEFAULT ON ERROR cho mọi field | Dữ liệu sai có thể bị biến thành giá trị hợp lệ giả | Chỉ dùng fallback khi nghiệp vụ quy định |
| Nghĩ JSON "" luôn khác SQL NULL sau extraction | Oracle xem empty character string là SQL NULL | Giữ JSON representation hoặc kiểm tra type |
| Nhầm ON EMPTY với EMPTY ARRAY | ON EMPTY là policy; EMPTY ARRAY là một kết quả JSON cụ thể của JSON_QUERY | Đọc đúng clause và function |
| Nghĩ JSON_EXISTS trả FALSE cho JSON null | JSON null vẫn là giá trị tồn tại | JSON_EXISTS trả TRUE khi path match null |
| Dùng ERROR ON ERROR để bắt path syntax sai | Path syntax có thể lỗi ở compile time | Kiểm tra path trước khi chạy |
| Nhầm JSON_TABLE row path với column path | Hai tầng xử lý có handler khác nhau | Phân tích row-level và column-level riêng |
| Cho rằng JSON_TABLE no match luôn tạo row NULL | Row path không match thường tạo zero rows | Dùng outer join/nested clause khi cần giữ parent row |
| Không kiểm tra phiên bản | Scalar return, SQL JSON type và một số clause thay đổi theo release | Đối chiếu SQL Language Reference đúng version |

## 19. Checklist triển khai

Trước khi triển khai truy vấn JSON vào ứng dụng, hãy xác định:

1. Cột đầu vào là SQL JSON, VARCHAR2, CLOB hay BLOB?
2. Cột có thể là SQL NULL không?
3. Field được truy vấn là bắt buộc hay tùy chọn?
4. Field bị thiếu có phải lỗi nghiệp vụ không?
5. JSON null có được phép và có ý nghĩa riêng không?
6. Có cần phân biệt JSON null với empty JSON string không?
7. JSON_VALUE có đúng vì field luôn là scalar không?
8. Có nên dùng JSON_QUERY để giữ lại JSON object/array/null không?
9. Có nên dùng JSON_EXISTS để kiểm tra field presence không?
10. ON EMPTY đã được đặt độc lập với ON ERROR chưa?
11. Default literal có đúng kiểu và đúng nghiệp vụ không?
12. JSON_TABLE có cần row-level và column-level error policy riêng không?
13. Đầu vào đã được xác thực JSON well-formed chưa?
14. Path expression có hợp lệ và đã được thử với các dạng JSON đại diện chưa?
15. Cú pháp có tương thích phiên bản Oracle đang chạy không?
16. Lỗi bị chuyển thành NULL có được log hoặc thống kê không?
17. Truy vấn có giữ được row cha khi JSON_TABLE không tìm thấy row source không?
18. Test có bao gồm SQL NULL, missing, JSON null, scalar, object, array và JSON hỏng không?

## 20. Tổng kết

ON ERROR và ON EMPTY giúp SQL/JSON query xử lý dữ liệu không hoàn chỉnh theo chính sách rõ ràng:

- ON ERROR xử lý lỗi runtime trong quá trình đánh giá JSON.
- ON EMPTY xử lý path hợp lệ nhưng không tìm thấy field/value; nếu có cả hai, ON EMPTY quyết định riêng cho trường hợp missing.
- JSON_VALUE trích scalar sang SQL; JSON null mặc định trở thành SQL NULL.
- JSON_EXISTS kiểm tra field có tồn tại; field có JSON null vẫn được xem là tồn tại.
- JSON_QUERY trả JSON representation và có thể giữ JSON null khi kiểu dữ liệu/phiên bản hỗ trợ.
- JSON_TABLE có row path và column path; cần phân biệt row-level với column-level error handling.
- SQL NULL ở cột tài liệu, field missing và JSON null là ba trạng thái khác nhau. Kết quả SQL NULL từ một phép trích xuất không đủ để phân biệt chúng.
- NULL ON NULL/ABSENT ON NULL thuộc generation functions; chúng khác ON EMPTY của query functions.

Hãy chọn ON EMPTY theo tính bắt buộc của field, chọn ON ERROR theo mức nghiêm ngặt của validation, và dùng JSON_EXISTS hoặc JSON-preserving extraction khi cần giữ sự khác biệt giữa field missing, JSON null và SQL NULL.

## 21. Tài liệu Oracle tham khảo

- Oracle Database 19c JSON Developer's Guide, “Clauses Used in SQL Query Functions and Conditions”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/clauses-used-in-functions-and-conditions-for-json.html
- Oracle Database 19c JSON Developer's Guide, “SQL/JSON Function JSON_VALUE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_VALUE.html
- Oracle Database 21c SQL Language Reference, “JSON_TABLE”: https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/JSON_TABLE.html
- Oracle Database 26c JSON Developer's Guide, “Overview of JSON in Oracle AI Database” (JSON null and SQL NULL): https://docs.oracle.com/en/database/oracle/oracle-database/26/adjsn/overview-json-oracle-ai-database.html
- Oracle Database 26c JSON Developer's Guide, “Error Clause for SQL Functions and Conditions”: https://docs.oracle.com/en/database/oracle/oracle-database/26/adjsn/error-clause-sql-query-functions-and-conditions.html
- Oracle Database 26c JSON Developer's Guide, “Overview of JSON Generation”: https://docs.oracle.com/en/database/oracle/oracle-database/26/adjsn/overview-json-generation.html
