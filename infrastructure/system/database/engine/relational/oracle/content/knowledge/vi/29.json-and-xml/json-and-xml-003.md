# SQL/JSON path, JSON_VALUE, JSON_QUERY và JSON_EXISTS

Oracle cung cấp các hàm SQL/JSON để truy vấn dữ liệu JSON ngay trong câu SQL. Thay vì đọc toàn bộ tài liệu JSON về ứng dụng rồi tự phân tích, database có thể tìm một thuộc tính, chuyển giá trị JSON thành kiểu SQL, trả lại một object/array JSON hoặc kiểm tra xem một đường dẫn có tồn tại hay không.

Ba hàm cần phân biệt:

- **JSON_VALUE**: lấy một giá trị scalar từ JSON và chuyển thành kiểu SQL như VARCHAR2 hoặc NUMBER.
- **JSON_QUERY**: lấy một object hoặc array JSON và trả về dưới dạng JSON text/LOB.
- **JSON_EXISTS**: kiểm tra xem đường dẫn JSON có khớp ít nhất một giá trị hay không; thường dùng trong WHERE.

Các hàm này dùng **SQL/JSON path expression** để chỉ vị trí cần truy cập. Path có cú pháp riêng, bắt đầu từ root bằng dấu $, đi qua thuộc tính object, phần tử array, wildcard và filter. Hiểu đúng path, kiểu trả về và hành vi khi thiếu dữ liệu sẽ giúp tránh nhầm SQL NULL với JSON null, tránh lỗi khi path trả nhiều giá trị và viết truy vấn có thể tận dụng index.

Bài học dùng Oracle Database 19c, JSON lưu trong cột VARCHAR2 hoặc CLOB. Nội dung bao gồm cú pháp path, lax/strict mode, ba hàm truy vấn, PASSING, ON ERROR/ON EMPTY, JSON null, lọc dữ liệu, indexing, lab và các lỗi thường gặp.

## 1. JSON trong Oracle Database

Oracle 19c lưu JSON trong các kiểu dữ liệu SQL như VARCHAR2, CLOB, BLOB hoặc kiểu phù hợp theo giới hạn của phiên bản. Dữ liệu được lưu dưới dạng văn bản/byte; Oracle xác thực và truy vấn nội dung bằng các hàm SQL/JSON.

Ví dụ tài liệu JSON:

~~~json
{
  "orderId": 501,
  "customer": {
    "id": 101,
    "name": "Nguyễn An"
  },
  "status": "PAID",
  "total": 1250.5,
  "items": [
    {
      "sku": "KB-01",
      "name": "Bàn phím",
      "quantity": 2,
      "price": 500
    },
    {
      "sku": "MS-02",
      "name": "Chuột",
      "quantity": 1,
      "price": 250.5
    }
  ],
  "note": null
}
~~~

Đường dẫn JSON giúp lấy các giá trị như:

| Nội dung | SQL/JSON path |
| --- | --- |
| Mã đơn hàng | $.orderId |
| Tên khách hàng | $.customer.name |
| Phần tử đầu tiên của items | $.items[0] |
| SKU của mọi mặt hàng | $.items[*].sku |
| Ghi chú | $.note |

JSON array dùng index bắt đầu từ 0. Điều này khác với index thông thường của nested table hoặc VARRAY trong PL/SQL, thường bắt đầu từ 1.

### 1.1. Xác thực cột JSON

Trong Oracle 19c, có thể thêm CHECK constraint với điều kiện IS JSON:

~~~sql
CREATE TABLE orders_json (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT orders_json_payload_ck
        CHECK (payload IS JSON)
);
~~~

Constraint ngăn nội dung không phải JSON hợp lệ được lưu vào cột. Nếu cột có thể NULL, cần cân nhắc NOT NULL riêng vì CHECK constraint không tự động cấm SQL NULL.

Có thể dùng VARCHAR2 thay CLOB khi tài liệu nhỏ và phù hợp giới hạn kiểu. CLOB phù hợp tài liệu lớn. BLOB có thể lưu JSON dạng byte, nhưng cần tuân thủ encoding JSON mà Oracle hỗ trợ; trong thực tế nên dùng UTF-8 cho JSON trao đổi.

### 1.2. Kiểm tra dữ liệu hiện có

~~~sql
SELECT order_id
FROM orders_json
WHERE payload IS NOT JSON;
~~~

Truy vấn này hữu ích khi kiểm tra bảng cũ chưa có constraint. Với cột chứa SQL NULL, điều kiện IS NOT JSON có thể không trả TRUE như một chuỗi JSON lỗi; hãy kiểm tra NULL riêng:

~~~sql
SELECT order_id
FROM orders_json
WHERE payload IS NULL
   OR payload IS NOT JSON;
~~~

## 2. SQL/JSON path expression

SQL/JSON path là biểu thức chỉ vị trí trong tài liệu JSON. Path thông thường bắt đầu bằng ký hiệu $ đại diện cho root JSON.

### 2.1. Root và object member

~~~text
$
$.orderId
$.customer
$.customer.name
$.customer.id
~~~

- $ chọn toàn bộ tài liệu.
- $.customer chọn thuộc tính customer ở root.
- $.customer.name đi tiếp vào thuộc tính name của object customer.

Tên member phân biệt chữ hoa/chữ thường. Path $.customer.name khác $.Customer.Name.

### 2.2. Array index

~~~text
$.items[0]
$.items[1].sku
$.items[0].quantity
~~~

Index array bắt đầu từ 0. $.items[0] là phần tử đầu tiên; $.items[1] là phần tử thứ hai.

Nếu index không tồn tại, path không có match. Hành vi SQL cụ thể tiếp theo phụ thuộc hàm được gọi và ON ERROR/ON EMPTY.

### 2.3. Wildcard

~~~text
$.items[*]
$.items[*].sku
$.customer.*
~~~

- [*] chọn mọi phần tử của array.
- .* chọn các member của object.

Wildcard có thể trả nhiều giá trị. JSON_VALUE thường yêu cầu một scalar; JSON_QUERY có thể trả object/array hoặc nhiều kết quả khi dùng wrapper; JSON_EXISTS chỉ cần biết có match hay không.

### 2.4. Member name có ký tự đặc biệt

Nếu tên thuộc tính chứa dấu chấm, khoảng trắng hoặc ký tự cần quote, đặt tên member trong dấu nháy kép theo cú pháp path:

~~~text
$."customer-name"
$."display name"
~~~

Không nhầm dấu nháy kép trong path với dấu nháy của SQL string. Khi viết path trong SQL, toàn bộ path vẫn là một string literal.

### 2.5. Filter expression

Filter đặt sau một bước path bằng dấu hỏi và cặp ngoặc:

~~~text
$.items[*]?(@.quantity > 1)
$.items[*]?(@.sku == "KB-01")
~~~

Trong filter:

- @ đại diện cho phần tử hiện tại đang được xét.
- @.quantity lấy thuộc tính quantity của phần tử hiện tại.
- Toán tử so sánh kiểm tra giá trị của phần tử.

Ví dụ JSON_EXISTS dùng filter:

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity > 1)'
);
~~~

Truy vấn trả về đơn hàng có ít nhất một item quantity lớn hơn 1.

### 2.6. Lax và strict mode

Oracle SQL/JSON path mặc định dùng lax mode. Lax mode cho phép một số chuyển đổi linh hoạt giữa object/array, ví dụ tự động bọc hoặc bỏ lớp array trong những trường hợp được quy định.

Có thể yêu cầu strict mode trong path:

~~~text
lax $.items[*].sku
strict $.items[*].sku
~~~

Strict mode yêu cầu cấu trúc khớp chặt hơn. Một path hợp lệ ở lax mode có thể không match trong strict mode nếu kiểu cấu trúc không đúng như mong đợi.

Khi viết API, nên biết rõ dữ liệu JSON có cấu trúc ổn định hay không. Nếu schema tài liệu được kiểm soát chặt, strict path có thể giúp phát hiện sai cấu trúc. Với dữ liệu từ nhiều nguồn không đồng nhất, lax mode có thể thuận tiện nhưng cần kiểm soát kết quả và lỗi.

### 2.7. Path variable

Path có thể dùng biến được truyền qua PASSING:

~~~text
$.items[*]?(@.sku == $wantedSku)
~~~

Tên biến trong path bắt đầu bằng $. Giá trị được bind từ SQL expression trong mệnh đề PASSING:

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.sku == $wantedSku)'
    PASSING 'KB-01' AS "wantedSku"
);
~~~

Tên biến trong path và alias sau AS phải khớp theo quy tắc tên biến SQL/JSON. Dùng PASSING để truyền giá trị thay vì nối chuỗi đầu vào vào path hoặc SQL text.

## 3. JSON_VALUE: lấy scalar thành kiểu SQL

JSON_VALUE trích một giá trị scalar từ tài liệu JSON và chuyển nó sang kiểu SQL được yêu cầu.

Cú pháp khái quát:

~~~sql
JSON_VALUE(
    json_expression,
    path_expression
    [RETURNING sql_type]
    [NULL ON ERROR | ERROR ON ERROR | DEFAULT value ON ERROR]
    [NULL ON EMPTY | ERROR ON EMPTY | DEFAULT value ON EMPTY]
)
~~~

Các lựa chọn ON ERROR và ON EMPTY phụ thuộc cú pháp/phiên bản và vị trí trong câu gọi. Trong Oracle 19c, hãy kiểm tra SQL Language Reference khi dùng default expression hoặc kiểu trả về đặc biệt.

### 3.1. Lấy chuỗi

~~~sql
SELECT
    JSON_VALUE(payload, '$.status') AS order_status
FROM orders_json;
~~~

Mặc định JSON_VALUE trả VARCHAR2 nếu không chỉ định RETURNING. Với scalar dạng string, kết quả là nội dung chuỗi đã được chuyển sang kiểu SQL.

### 3.2. Lấy số

~~~sql
SELECT
    JSON_VALUE(
        payload,
        '$.total'
        RETURNING NUMBER
    ) AS total_amount
FROM orders_json;
~~~

RETURNING NUMBER yêu cầu giá trị JSON có thể chuyển thành NUMBER. Nếu dữ liệu không phải số hoặc path trả object/array, xử lý lỗi phụ thuộc ON ERROR.

### 3.3. Lấy ngày/giờ

Nếu JSON lưu ngày giờ dưới dạng chuỗi ISO, có thể trích thành VARCHAR2 rồi chuyển đổi theo format rõ ràng:

~~~sql
SELECT TO_TIMESTAMP_TZ(
           JSON_VALUE(payload, '$.createdAt'),
           'YYYY-MM-DD"T"HH24:MI:SS.FF TZH:TZM'
       ) AS created_at
FROM orders_json;
~~~

Không dựa vào NLS_DATE_FORMAT mặc định để chuyển một chuỗi JSON có format cố định. Nếu API lưu ngày ở dạng epoch hoặc format riêng, phải định nghĩa quy tắc chuyển đổi tương ứng.

### 3.4. JSON_VALUE chỉ trả scalar

JSON_VALUE phù hợp với string, number, boolean có quy tắc ánh xạ SQL và JSON null. Nó không dùng để trả nguyên object hoặc array.

Ví dụ:

~~~sql
JSON_VALUE(payload, '$.customer.name')
JSON_VALUE(payload, '$.items[0].sku')
~~~

Nhưng path $.customer hoặc $.items chọn object/array, không phải scalar. Mặc định ON ERROR có thể làm kết quả thành SQL NULL; nếu cần phát hiện sai shape, dùng ERROR ON ERROR.

### 3.5. Xử lý khi path không có kết quả

Mặc định JSON_VALUE dùng NULL ON ERROR và NULL ON EMPTY trong các tình huống tương ứng. Điều này thuận tiện cho truy vấn chịu được field tùy chọn nhưng có thể che giấu dữ liệu lỗi.

~~~sql
SELECT
    JSON_VALUE(
        payload,
        '$.customer.id'
        RETURNING NUMBER
        ERROR ON ERROR
        NULL ON EMPTY
    ) AS customer_id
FROM orders_json;
~~~

Ví dụ này yêu cầu lỗi nếu tài liệu/path có lỗi chuyển đổi hoặc cấu trúc không hợp lệ theo ON ERROR, nhưng trả NULL nếu member không tồn tại theo ON EMPTY.

### 3.6. DEFAULT ON ERROR

Có thể chọn giá trị mặc định khi xảy ra lỗi:

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.priority'
           RETURNING NUMBER
           DEFAULT 0 ON ERROR
       ) AS priority
FROM orders_json;
~~~

Chỉ dùng DEFAULT khi giá trị thay thế có ý nghĩa nghiệp vụ. Nếu JSON chứa "high" trong khi cần NUMBER, tự động biến thành 0 có thể che dữ liệu sai. Đối với dữ liệu quan trọng, ERROR ON ERROR thường giúp phát hiện lỗi sớm hơn.

### 3.7. JSON null và SQL NULL

JSON có literal null riêng. Khi JSON_VALUE trích một giá trị JSON null, Oracle ánh xạ nó thành SQL NULL.

Vì vậy các tình huống sau có thể cho kết quả JSON_VALUE là SQL NULL:

- Thuộc tính không tồn tại.
- Thuộc tính tồn tại nhưng giá trị JSON là null.
- Có lỗi path/conversion và ON ERROR chọn NULL.

Nếu cần phân biệt member có tồn tại hay không, dùng JSON_EXISTS. JSON_EXISTS có thể trả TRUE cho path trỏ tới thuộc tính tồn tại với giá trị JSON null, trong khi JSON_VALUE trả SQL NULL.

## 4. JSON_QUERY: lấy object hoặc array

JSON_QUERY trích object hoặc array JSON và trả lại nội dung JSON. Đây là hàm phù hợp khi muốn lấy một nhánh tài liệu mà không chuyển thành scalar SQL.

Cú pháp khái quát:

~~~sql
JSON_QUERY(
    json_expression,
    path_expression
    [RETURNING VARCHAR2 | CLOB | BLOB]
    [WITH WRAPPER | WITHOUT WRAPPER | WITH CONDITIONAL WRAPPER]
    [KEEP QUOTES | OMIT QUOTES]
    [ON ERROR]
)
~~~

Chi tiết các tùy chọn và kiểu trả về cần đối chiếu SQL Language Reference của Oracle release đang dùng. Với tài liệu lớn, chọn CLOB để tránh giới hạn chuỗi SQL nhỏ.

### 4.1. Lấy object customer

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.customer'
           RETURNING CLOB
       ) AS customer_json
FROM orders_json;
~~~

Kết quả là một object JSON, ví dụ:

~~~json
{"id":101,"name":"Nguyễn An"}
~~~

### 4.2. Lấy array items

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.items'
           RETURNING CLOB
       ) AS items_json
FROM orders_json;
~~~

Kết quả là array JSON giữ cấu trúc các item.

### 4.3. Lấy nhiều giá trị với WITH WRAPPER

Path wildcard có thể match nhiều giá trị:

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.items[*].sku'
           WITH WRAPPER
           RETURNING CLOB
       ) AS sku_array
FROM orders_json;
~~~

WITH WRAPPER đóng gói các kết quả match vào một array JSON. Điều này hữu ích khi path chọn nhiều scalar/object riêng lẻ nhưng API cần một tài liệu JSON duy nhất.

Không nhầm WITH WRAPPER với JSON_VALUE: wrapper biến tập kết quả thành JSON array để JSON_QUERY trả về, còn JSON_VALUE vẫn là hàm trích scalar.

### 4.4. WITHOUT WRAPPER

WITHOUT WRAPPER yêu cầu kết quả phù hợp với một object/array JSON đơn theo quy tắc hàm. Nếu path có nhiều match mà không có wrapper, kết quả có thể phát sinh lỗi hoặc được xử lý theo ON ERROR. Khi không chắc số match, dùng WITH WRAPPER hoặc thiết kế path chỉ chọn một cấu trúc.

### 4.5. KEEP QUOTES và OMIT QUOTES

Các tùy chọn quotes ảnh hưởng cách JSON_QUERY trả scalar string trong những trường hợp được hỗ trợ. Mặc định, chuỗi JSON cần giữ dấu ngoặc kép để vẫn là JSON hợp lệ. OMIT QUOTES có thể bỏ dấu quote cho trường hợp phù hợp, nhưng kết quả khi đó không còn là JSON string đầy đủ theo cùng cách. Chỉ dùng khi caller mong đợi đúng dạng đó.

### 4.6. JSON_QUERY không phải công cụ lấy scalar thông thường

Nếu cần giá trị số để cộng, so sánh hoặc join, dùng JSON_VALUE RETURNING NUMBER. JSON_QUERY phù hợp để lấy object/array hoặc một cấu trúc JSON cần chuyển tiếp cho ứng dụng.

## 5. JSON_EXISTS: kiểm tra sự tồn tại của path

JSON_EXISTS là SQL condition trả TRUE khi path expression match ít nhất một giá trị, FALSE khi không match. Nó thường xuất hiện trong WHERE để lọc tài liệu JSON.

Cú pháp:

~~~sql
JSON_EXISTS(
    json_expression,
    path_expression
    [PASSING expr AS "var_name" ...]
    [ERROR ON ERROR]
)
~~~

### 5.1. Kiểm tra member tồn tại

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(o.payload, '$.customer.id');
~~~

Truy vấn trả các tài liệu có đường dẫn customer.id khớp.

### 5.2. Kiểm tra phần tử array

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(o.payload, '$.items[0]');
~~~

Điều kiện đúng nếu phần tử đầu tiên của items tồn tại theo path.

### 5.3. Kiểm tra giá trị bằng filter

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= 2)'
);
~~~

Filter được đánh giá cho các phần tử array. JSON_EXISTS trả TRUE nếu có ít nhất một item quantity lớn hơn hoặc bằng 2.

### 5.4. PASSING để bind giá trị

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.sku == $sku)'
    PASSING :p_sku AS "sku"
);
~~~

:p_sku là bind variable SQL. Giá trị được gán cho biến path $sku. Đây là cách an toàn và rõ ràng để tìm một SKU động.

### 5.5. JSON null vẫn là một giá trị tồn tại

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(o.payload, '$.note');
~~~

Nếu tài liệu có "note": null, path $.note vẫn tồn tại nên JSON_EXISTS trả TRUE. Trong khi đó:

~~~sql
JSON_VALUE(payload, '$.note')
~~~

trả SQL NULL. Đây là khác biệt quan trọng giữa kiểm tra sự tồn tại và lấy giá trị scalar.

### 5.6. Dùng NOT JSON_EXISTS

~~~sql
SELECT order_id
FROM orders_json o
WHERE NOT JSON_EXISTS(o.payload, '$.shipping.address');
~~~

Truy vấn tìm tài liệu không có path shipping.address. Nếu dữ liệu JSON malformed hoặc expression có lỗi, hãy xác định rõ hành vi ON ERROR và constraint IS JSON; không dùng NOT JSON_EXISTS như cách thay thế xác thực tài liệu.

## 6. So sánh ba hàm

| Câu hỏi | Hàm nên dùng | Kiểu kết quả |
| --- | --- | --- |
| Lấy tên khách hàng thành VARCHAR2 | JSON_VALUE | Scalar SQL |
| Lấy tổng tiền thành NUMBER | JSON_VALUE RETURNING NUMBER | Scalar SQL |
| Lấy nguyên object customer | JSON_QUERY | JSON object |
| Lấy array items | JSON_QUERY | JSON array |
| Lấy mọi SKU thành một JSON array | JSON_QUERY WITH WRAPPER | JSON array |
| Tìm tài liệu có customer.id | JSON_EXISTS | Điều kiện TRUE/FALSE |
| Tìm tài liệu có item quantity > 2 | JSON_EXISTS với filter | Điều kiện TRUE/FALSE |
| Phân biệt field không tồn tại với JSON null | JSON_EXISTS kết hợp JSON_VALUE | Điều kiện + scalar |

Ví dụ dùng cả ba trong một truy vấn:

~~~sql
SELECT
    o.order_id,
    JSON_VALUE(o.payload, '$.customer.name') AS customer_name,
    JSON_VALUE(o.payload, '$.total' RETURNING NUMBER) AS total_amount,
    JSON_QUERY(o.payload, '$.items' RETURNING CLOB) AS items_json
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= 2)'
);
~~~

Truy vấn chỉ lấy các đơn có ít nhất một item số lượng từ 2, đồng thời chiếu tên khách hàng, tổng tiền và toàn bộ array items.

## 7. ON ERROR và ON EMPTY

Hai mệnh đề này xử lý hai tình huống khác nhau:

- ON ERROR: xử lý lỗi khi đánh giá JSON/path hoặc chuyển đổi giá trị, tùy hàm.
- ON EMPTY: xử lý trường hợp path không tìm thấy giá trị.

### 7.1. JSON_VALUE mặc định

Nếu không chỉ định, JSON_VALUE thường dùng NULL ON ERROR và NULL ON EMPTY. Điều này giúp truy vấn không dừng vì một tài liệu thiếu field, nhưng có thể làm dữ liệu sai trông giống dữ liệu thiếu.

### 7.2. ERROR ON ERROR

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.total'
           RETURNING NUMBER
           ERROR ON ERROR
       )
FROM orders_json;
~~~

Nếu total không chuyển được thành NUMBER hoặc path trả kiểu không phù hợp, truy vấn báo lỗi thay vì trả NULL.

### 7.3. NULL ON EMPTY

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.optionalField'
           NULL ON EMPTY
       )
FROM orders_json;
~~~

Field không tồn tại được coi là tùy chọn và trả SQL NULL. Nếu field bắt buộc, cân nhắc ERROR ON EMPTY hoặc kiểm tra bằng JSON_EXISTS.

### 7.4. DEFAULT ON EMPTY

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.priority'
           RETURNING NUMBER
           DEFAULT 0 ON EMPTY
       )
FROM orders_json;
~~~

DEFAULT ON EMPTY phù hợp khi hợp đồng dữ liệu định nghĩa rõ giá trị mặc định cho field thiếu. Không dùng nó để che trường hợp sai kiểu; đó là việc của ON ERROR.

### 7.5. Phân biệt field thiếu, JSON null và sai kiểu

Ví dụ JSON:

~~~json
{
  "a": 10,
  "b": null,
  "c": "not-a-number"
}
~~~

Kết quả khái niệm:

| Path | JSON_EXISTS | JSON_VALUE RETURNING NUMBER |
| --- | --- | --- |
| $.a | TRUE | 10 |
| $.b | TRUE | SQL NULL |
| $.missing | FALSE | SQL NULL khi ON EMPTY là NULL |
| $.c | TRUE | lỗi conversion hoặc hành vi ON ERROR được chọn |

Để phân biệt b với missing, kết hợp JSON_EXISTS và JSON_VALUE. Để phân biệt sai kiểu với NULL, dùng ERROR ON ERROR hoặc validate schema/contract trước.

## 8. SQL/JSON path filters chi tiết

Filter expression cho phép chọn phần tử theo điều kiện của nội dung JSON.

### 8.1. So sánh số

~~~text
$.items[*]?(@.quantity > 1)
$.items[*]?(@.price <= 500)
~~~

### 8.2. So sánh chuỗi

~~~text
$.items[*]?(@.sku == "KB-01")
$.items[*]?(@.name != "Chuột")
~~~

Giá trị chuỗi trong path dùng dấu nháy kép JSON-style. SQL string chứa path vẫn có thể dùng dấu nháy đơn bên ngoài.

### 8.3. Kết hợp điều kiện

~~~text
$.items[*]?(@.quantity >= 2 && @.price < 1000)
~~~

Toán tử && biểu diễn AND trong filter. Có thể dùng toán tử logic được SQL/JSON path hỗ trợ để kết hợp điều kiện; cú pháp cụ thể cần theo SQL/JSON path language của Oracle.

### 8.4. PASSING nhiều biến

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= $minQty && @.price <= $maxPrice)'
    PASSING :p_min_qty AS "minQty",
            :p_max_price AS "maxPrice"
);
~~~

PASSING giúp tách path cố định khỏi giá trị tìm kiếm. Dữ liệu đầu vào được bind, không phải ghép vào path string.

### 8.5. Không biến path thành SQL injection

Không nối chuỗi người dùng vào câu SQL hoặc path expression:

~~~sql
-- Tránh xây dựng SQL text từ input không tin cậy.
-- Hãy dùng bind variables và PASSING.
~~~

Nếu ứng dụng cho phép chọn field, hãy whitelist các path được hỗ trợ. PASSING bind giá trị so sánh, không tự động biến một path tùy ý thành an toàn.

## 9. Truy vấn JSON trong WHERE, SELECT và JOIN

### 9.1. Lọc theo scalar

~~~sql
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(
          payload,
          '$.status'
          RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

JSON_VALUE chuyển status thành VARCHAR2 để so sánh với SQL string.

### 9.2. Lọc theo số

~~~sql
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(
          payload,
          '$.total'
          RETURNING NUMBER
          ERROR ON ERROR
      ) >= 1000;
~~~

RETURNING NUMBER tránh so sánh số dưới dạng chuỗi, nơi thứ tự từ điển có thể khác thứ tự số học.

### 9.3. Kết hợp với bảng quan hệ

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    JSON_VALUE(o.payload, '$.total' RETURNING NUMBER) AS total_amount
FROM orders_json o
JOIN customers c
  ON c.customer_id =
     JSON_VALUE(o.payload, '$.customer.id' RETURNING NUMBER);
~~~

JSON_VALUE cho phép dùng field JSON làm khóa nối. Tuy nhiên, nếu field là khóa quan hệ quan trọng, cân nhắc lưu khóa ở cột quan hệ riêng hoặc tạo virtual column/index để tránh parse lặp và hỗ trợ constraint.

### 9.4. JSON_QUERY để trả một nhánh tài liệu

~~~sql
SELECT
    order_id,
    JSON_QUERY(payload, '$.customer' RETURNING CLOB) AS customer_json
FROM orders_json;
~~~

Ứng dụng có thể nhận object JSON mà không cần database chuyển nó thành nhiều cột SQL.

### 9.5. JSON_TABLE khi cần nhiều cột/hàng

JSON_TABLE là hàm SQL/JSON khác, hữu ích khi muốn chiếu nhiều field hoặc unnest array thành các hàng quan hệ:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.quantity,
    jt.price
FROM orders_json o,
     JSON_TABLE(
         o.payload,
         '$.items[*]'
         COLUMNS (
             sku VARCHAR2(30) PATH '$.sku',
             quantity NUMBER PATH '$.quantity',
             price NUMBER PATH '$.price'
         )
     ) jt;
~~~

JSON_VALUE phù hợp một scalar mỗi lần; JSON_QUERY phù hợp một cấu trúc JSON; JSON_EXISTS phù hợp kiểm tra điều kiện; JSON_TABLE phù hợp biến cấu trúc JSON thành hàng/cột SQL.

## 10. Index cho JSON_VALUE và truy vấn JSON

Nếu truy vấn thường xuyên lọc theo một scalar JSON, function-based index trên JSON_VALUE có thể giúp Oracle tránh parse toàn bộ tài liệu cho mọi hàng.

### 10.1. Function-based index

~~~sql
CREATE INDEX orders_json_status_ix
ON orders_json (
    JSON_VALUE(
        payload,
        '$.status'
        RETURNING VARCHAR2(20)
    )
);
~~~

Query nên dùng biểu thức tương thích với biểu thức index:

~~~sql
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(
          payload,
          '$.status'
          RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

Kiểu trả về và path phải khớp cách index được định nghĩa. Optimizer vẫn quyết định có dùng index hay không dựa trên statistics, selectivity và cost.

### 10.2. Virtual column

Có thể tạo virtual column cho field JSON thường dùng:

~~~sql
ALTER TABLE orders_json ADD (
    json_status VARCHAR2(20)
        GENERATED ALWAYS AS (
            JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
        ) VIRTUAL
);

CREATE INDEX orders_json_vstatus_ix
ON orders_json(json_status);
~~~

Ứng dụng có thể truy vấn JSON_STATUS như một cột thông thường. Đây cũng là cách làm rõ field JSON nào được xem là thuộc tính truy vấn quan trọng.

### 10.3. JSON_EXISTS và index

JSON_EXISTS có thể được tối ưu tùy dạng path, index và phiên bản Oracle. Với điều kiện filter phức tạp hoặc tìm kiếm trên nhiều field, cân nhắc JSON search index nếu tính năng và license/cấu hình hệ thống hỗ trợ. Không giả định mọi path expression đều dùng được cùng một index.

Hãy đo execution plan và workload thật:

~~~sql
EXPLAIN PLAN FOR
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'PAID';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

## 11. Dữ liệu JSON tiếng Việt

JSON text có thể chứa Unicode. Với database AL32UTF8, CLOB/VARCHAR2 có thể lưu tiếng Việt đầy đủ. Path member name và string value phân biệt hoa thường theo nội dung JSON.

### 11.1. Lấy tiếng Việt bằng JSON_VALUE

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.customer.name'
           RETURNING VARCHAR2(100)
       ) AS customer_name
FROM orders_json;
~~~

Kết quả là SQL VARCHAR2. Việc hiển thị đúng còn phụ thuộc client encoding/font, nhưng database path không làm mất dấu nếu dữ liệu đã được lưu đúng.

### 11.2. Lấy nguyên object bằng JSON_QUERY

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.customer'
           RETURNING CLOB
       )
FROM orders_json;
~~~

JSON_QUERY giữ nội dung object JSON, bao gồm chuỗi Unicode.

### 11.3. Unicode escape trong JSON

JSON có thể biểu diễn ký tự bằng Unicode escape, ví dụ:

~~~json
{"name":"Nguy\u1ec5n An"}
~~~

Đây là cách biểu diễn JSON hợp lệ tương đương với chuỗi tiếng Việt có dấu tương ứng. Oracle SQL/JSON parser giải mã escape khi trích giá trị.

Không nhầm escape JSON với escape SQL. Nếu tạo JSON literal trong script, cả tầng SQL quoting và JSON escaping đều phải hợp lệ.

## 12. Kiểm soát dữ liệu và hiệu năng

### 12.1. Xác thực JSON đầu vào

Đặt IS JSON constraint để ngăn văn bản không phải JSON hợp lệ. Nếu API có schema nghiệp vụ chặt, cần kiểm tra thêm field bắt buộc, kiểu dữ liệu, giới hạn số lượng array và quy tắc giá trị.

### 12.2. Path cố định

Ưu tiên path cố định trong SQL đã được kiểm thử. Nếu client được phép chọn field, map lựa chọn đó sang danh sách path đã được whitelist. Không nối trực tiếp chuỗi client vào SQL.

### 12.3. Chọn kiểu RETURNING

Chọn kiểu SQL tương ứng ý nghĩa:

- Mã/tên/trạng thái: VARCHAR2.
- Số lượng/giá trị tiền: NUMBER.
- Ngày giờ: kiểu ngày giờ phù hợp hoặc chuyển đổi theo format rõ ràng.
- Object/array: JSON_QUERY RETURNING CLOB.

Không trích số thành VARCHAR2 rồi so sánh từ điển. Không trích ngày giờ rồi phụ thuộc NLS mặc định.

### 12.4. Xử lý lỗi có chủ đích

Đối với dữ liệu đáng tin cậy, NULL ON ERROR có thể thuận tiện. Đối với dữ liệu tích hợp hoặc tài chính, ERROR ON ERROR giúp phát hiện sai kiểu và sai cấu trúc. Chọn ON EMPTY theo quy tắc field bắt buộc hay tùy chọn.

### 12.5. Không trích toàn bộ JSON nếu chỉ cần một field

Nếu chỉ cần total, dùng JSON_VALUE thay vì JSON_QUERY lấy toàn bộ object rồi parse ở ứng dụng. Nếu cần toàn bộ items, JSON_QUERY hoặc JSON_TABLE tùy mục tiêu.

### 12.6. Giới hạn kích thước

Với tài liệu lớn, dùng CLOB và RETURNING CLOB khi phù hợp. Tránh mặc định VARCHAR2 nếu kết quả có thể vượt giới hạn SQL string của cấu hình/phiên bản. Đọc LOB theo streaming ở client nếu nội dung lớn.

## 13. Lab thực hành

Lab tạo bảng đơn hàng có JSON payload, rồi lần lượt dùng JSON_VALUE, JSON_QUERY và JSON_EXISTS.

### 13.1. Tạo bảng

~~~sql
CREATE TABLE lab_orders_json (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT lab_orders_json_ck CHECK (payload IS JSON)
);
~~~

### 13.2. Chèn dữ liệu

~~~sql
INSERT INTO lab_orders_json(order_id, payload)
VALUES (
    501,
    TO_CLOB(q'~{
      "orderId": 501,
      "customer": {"id": 101, "name": "Nguyễn An"},
      "status": "PAID",
      "total": 1250.5,
      "items": [
        {"sku": "KB-01", "name": "Bàn phím", "quantity": 2, "price": 500},
        {"sku": "MS-02", "name": "Chuột", "quantity": 1, "price": 250.5}
      ],
      "note": null
    }~')
);

INSERT INTO lab_orders_json(order_id, payload)
VALUES (
    502,
    TO_CLOB(q'~{
      "orderId": 502,
      "customer": {"id": 102, "name": "Trần Bình"},
      "status": "PENDING",
      "total": 300,
      "items": [
        {"sku": "MS-02", "name": "Chuột", "quantity": 1, "price": 300}
      ]
    }~')
);

COMMIT;
~~~

Các literal có tiếng Việt giả định script được gửi bằng encoding hỗ trợ Unicode và database character set tương thích. Có thể thay bằng UNISTR nếu môi trường tạo file SQL không bảo đảm UTF-8.

### 13.3. JSON_VALUE

~~~sql
SELECT
    order_id,
    JSON_VALUE(payload, '$.customer.name') AS customer_name,
    JSON_VALUE(payload, '$.status') AS status,
    JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
FROM lab_orders_json
ORDER BY order_id;
~~~

Kết quả trả về các scalar dưới kiểu SQL.

### 13.4. JSON_QUERY

~~~sql
SELECT
    order_id,
    JSON_QUERY(payload, '$.customer' RETURNING CLOB) AS customer_json,
    JSON_QUERY(payload, '$.items' RETURNING CLOB) AS items_json
FROM lab_orders_json
ORDER BY order_id;
~~~

Kết quả trả về object customer và array items.

### 13.5. JSON_EXISTS

~~~sql
SELECT order_id
FROM lab_orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= 2)'
);
~~~

Chỉ đơn 501 có item quantity từ 2 trở lên.

### 13.6. PASSING

~~~sql
SELECT order_id
FROM lab_orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.sku == $wantedSku)'
    PASSING 'MS-02' AS "wantedSku"
);
~~~

Kết quả gồm các đơn có SKU MS-02.

### 13.7. Phân biệt null và missing

~~~sql
SELECT
    order_id,
    JSON_EXISTS(payload, '$.note') AS has_note,
    JSON_VALUE(payload, '$.note') AS note_value
FROM lab_orders_json
ORDER BY order_id;
~~~

Đơn 501 có note tồn tại với JSON null: JSON_EXISTS là TRUE, JSON_VALUE trả SQL NULL. Đơn 502 không có note: JSON_EXISTS là FALSE, JSON_VALUE cũng trả SQL NULL theo mặc định.

### 13.8. Kiểm tra lỗi chuyển đổi

Thử JSON_VALUE RETURNING NUMBER với một field string:

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.status'
           RETURNING NUMBER
           ERROR ON ERROR
       )
FROM lab_orders_json;
~~~

Truy vấn phát sinh lỗi chuyển đổi vì status là string như PAID/PENDING, không phải NUMBER. Đây là ví dụ để thấy ERROR ON ERROR phát hiện sai kiểu.

### 13.9. Tạo index

~~~sql
CREATE INDEX lab_orders_status_ix
ON lab_orders_json (
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
);
~~~

Truy vấn theo cùng path và kiểu trả về:

~~~sql
SELECT order_id
FROM lab_orders_json
WHERE JSON_VALUE(
          payload,
          '$.status'
          RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

Dùng EXPLAIN PLAN/DBMS_XPLAN để quan sát optimizer có chọn index hay không.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| JSON_VALUE trả NULL dù field mong đợi | Path không match hoặc ON ERROR/ON EMPTY trả NULL | Kiểm tra JSON_EXISTS, path và dữ liệu |
| JSON_VALUE lỗi khi lấy object | Hàm yêu cầu scalar | Dùng JSON_QUERY |
| JSON_QUERY trả NULL | Path không match, lỗi hoặc ON ERROR | Xem ON ERROR/ON EMPTY và kiểm tra JSON |
| JSON_QUERY lỗi khi path match nhiều giá trị | Thiếu wrapper phù hợp | Dùng WITH WRAPPER hoặc thu hẹp path |
| JSON_EXISTS FALSE với path viết sai | Path không match hoặc xử lý lỗi mặc định | Dùng ERROR ON ERROR và kiểm tra cú pháp |
| JSON_EXISTS TRUE nhưng JSON_VALUE là NULL | Field tồn tại với JSON null | Phân biệt presence và scalar value |
| Lấy sai array item | Nhầm index bắt đầu từ 1 | JSON array index bắt đầu từ 0 |
| Không match tên thuộc tính | Path phân biệt hoa/thường | Dùng đúng tên member trong JSON |
| Lọc số sai | JSON_VALUE trả chuỗi rồi so sánh từ điển | Dùng RETURNING NUMBER |
| Filter không nhận giá trị bind | Sai tên biến PASSING hoặc alias | Đảm bảo $var và AS "var" khớp |
| JSON malformed lọt vào bảng | Thiếu IS JSON constraint | Thêm CHECK constraint và kiểm tra dữ liệu cũ |
| SQL injection qua path | Nối input không tin cậy vào path/SQL | Dùng PASSING và whitelist path |
| Index không được dùng | Biểu thức/path/returning type không khớp hoặc optimizer chọn plan khác | So sánh biểu thức index và execution plan |
| Tiếng Việt hiển thị sai | Client encoding hoặc dữ liệu nguồn sai | Kiểm tra charset và Unicode ở từng ranh giới |

## 15. Checklist khi thiết kế truy vấn SQL/JSON

Trước khi đưa truy vấn vào ứng dụng:

1. Cột JSON đã có IS JSON constraint hoặc validation tương đương chưa?
2. Path có đúng tên member và đúng chữ hoa/thường không?
3. Array index đã dùng hệ 0-based chưa?
4. Path có thể match một scalar hay nhiều giá trị?
5. Dùng JSON_VALUE hay JSON_QUERY đúng mục đích chưa?
6. Có cần JSON_EXISTS để phân biệt missing với JSON null không?
7. RETURNING type có đúng kiểu nghiệp vụ không?
8. ON ERROR và ON EMPTY có phản ánh contract dữ liệu không?
9. Giá trị động đã bind bằng PASSING chưa?
10. Path động có được whitelist không?
11. Truy vấn thường xuyên có cần function-based index hoặc virtual column không?
12. Kết quả CLOB lớn có được đọc streaming không?
13. Dữ liệu tiếng Việt có được truyền qua client đúng encoding không?

## 16. Bài tập thực hành

Sử dụng LAB_ORDERS_JSON trong mục 13.

### Bài 1 — Path cơ bản

Viết JSON_VALUE lấy orderId, customer.id, customer.name và status. Ghi rõ kiểu SQL trả về.

### Bài 2 — Array index và wildcard

Lấy SKU của phần tử đầu tiên bằng JSON_VALUE. Dùng JSON_QUERY WITH WRAPPER để lấy SKU của tất cả item thành một array JSON.

### Bài 3 — JSON_EXISTS filter

Tìm đơn có item quantity lớn hơn 1 và giá thấp hơn 600. Viết filter expression và kiểm tra kết quả.

### Bài 4 — PASSING

Viết truy vấn nhận SKU và min quantity từ bind variables. Dùng PASSING với hai path variables.

### Bài 5 — JSON null và missing

Thêm một đơn có note null và một đơn không có note. Dùng JSON_EXISTS kết hợp JSON_VALUE để phân biệt hai trường hợp.

### Bài 6 — ON ERROR/ON EMPTY

Thử lấy status bằng RETURNING NUMBER. So sánh NULL ON ERROR, DEFAULT ON ERROR và ERROR ON ERROR. Thử path không tồn tại với NULL ON EMPTY và ERROR ON EMPTY.

### Bài 7 — JSON_TABLE

Unnest items thành các hàng gồm sku, quantity, price. Tính tổng tiền các item bằng SQL.

### Bài 8 — Index

Tạo function-based index trên JSON_VALUE status. Chạy EXPLAIN PLAN cho truy vấn lọc status và giải thích khi nào optimizer chọn index.

## 17. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP TABLE lab_orders_json PURGE;
~~~

Không chạy lệnh dọn dẹp trên bảng nghiệp vụ.

## Tổng kết

SQL/JSON path bắt đầu từ root $ và đi qua object member, array index, wildcard hoặc filter. JSON array dùng index từ 0. Oracle mặc định dùng lax mode; strict mode yêu cầu cấu trúc khớp chặt hơn. Tên member phân biệt chữ hoa/thường và giá trị động nên được truyền qua PASSING.

JSON_VALUE lấy scalar và chuyển sang kiểu SQL, thường dùng RETURNING NUMBER hoặc VARCHAR2. JSON_QUERY lấy object/array JSON và có thể dùng WITH WRAPPER khi path trả nhiều kết quả. JSON_EXISTS kiểm tra path có match hay không, rất phù hợp cho WHERE và filter array. JSON null có thể làm JSON_VALUE trả SQL NULL nhưng JSON_EXISTS vẫn TRUE; member thiếu thường làm JSON_EXISTS FALSE và JSON_VALUE trả NULL theo mặc định.

Hãy xác thực JSON đầu vào, chọn ON ERROR/ON EMPTY theo contract, dùng đúng kiểu RETURNING, tránh ghép input vào path, và tạo function-based index hoặc virtual column cho field được truy vấn thường xuyên. Khi cần biến nhiều phần tử JSON thành hàng/cột SQL, cân nhắc JSON_TABLE.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — SQL/JSON Path Expressions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/json-path-expressions.html) — root, member, array, wildcard, filter và lax/strict mode.
- [Oracle Database SQL Language Reference — JSON_VALUE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_VALUE.html) — scalar extraction, RETURNING và error handling.
- [Oracle Database SQL Language Reference — JSON_QUERY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_QUERY.html) — object/array extraction và wrapper.
- [Oracle Database SQL Language Reference — JSON_EXISTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/condition-JSON_EXISTS.html) — kiểm tra path match, filter và PASSING.
- [Oracle Database SQL Language Reference — JSON_TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_TABLE.html) — chuyển JSON thành hàng và cột quan hệ.
- [Oracle Database JSON Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/) — lưu trữ, xác thực, truy vấn và index JSON.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu JSON Developer's Guide và SQL Language Reference đúng phiên bản, đặc biệt path grammar, kiểu RETURNING, ON ERROR/ON EMPTY, wrapper và hỗ trợ index.
