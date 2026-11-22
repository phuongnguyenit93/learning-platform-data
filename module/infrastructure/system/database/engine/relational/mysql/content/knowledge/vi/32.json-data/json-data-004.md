# JSON_VALUE và điều kiện hỗ trợ theo phiên bản

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Xác định phiên bản MySQL tối thiểu hỗ trợ JSON_VALUE.
- Dùng JSON_VALUE để lấy một giá trị scalar từ JSON document theo JSON path.
- Chuyển giá trị JSON sang kiểu SQL bằng RETURNING.
- Phân biệt giá trị bị thiếu, JSON null, SQL NULL và lỗi chuyển đổi.
- Chọn hành vi phù hợp bằng ON EMPTY và ON ERROR.
- Hiểu kiểu trả về mặc định VARCHAR(512), character set và collation.
- Phân biệt JSON_VALUE với JSON_EXTRACT, toán tử -> và ->>.
- Tạo functional index trên biểu thức JSON_VALUE và xác minh bằng EXPLAIN.
- Chọn giải pháp thay thế khi chạy MySQL cũ hơn 8.0.21.
- Tránh các lỗi về JSON path, kiểu trả về, dữ liệu không đồng nhất và giả định sai về xử lý lỗi.

JSON thường được dùng để lưu các thuộc tính linh hoạt như thông tin giao hàng, cấu hình, metadata hoặc dữ liệu tích hợp từ hệ thống khác. Khi cần lọc theo một thuộc tính nằm trong JSON, ứng dụng phải trích xuất giá trị và so sánh theo kiểu dữ liệu phù hợp.

JSON_VALUE là hàm MySQL dùng để lấy một giá trị scalar từ JSON document. Hàm có thể chuyển giá trị đó sang kiểu SQL cụ thể bằng RETURNING, đồng thời cho phép quy định hành vi khi path không tìm thấy dữ liệu hoặc khi giá trị không thể chuyển đổi bằng ON EMPTY và ON ERROR.

Điểm quan trọng về tương thích: JSON_VALUE được giới thiệu trong MySQL 8.0.21. MySQL 8.0.22 bổ sung YEAR vào danh sách kiểu RETURNING. Các nhánh MySQL 8.4 và 9.7 hiện có hàm này trong Reference Manual. MySQL 5.7 và MySQL 8.0.20 trở về trước không hỗ trợ JSON_VALUE.

## 1. JSON_VALUE dùng để làm gì?

JSON_VALUE nhận một JSON document và một JSON path, sau đó trả về giá trị tại vị trí được chọn. Nếu cần, hàm chuyển kết quả sang kiểu SQL như DECIMAL, UNSIGNED, DATE hoặc CHAR.

Ví dụ:

~~~sql
SELECT JSON_VALUE(
    '{"customer":{"name":"Nguyen An","tier":"GOLD"}}',
    '$.customer.name'
) AS customer_name;
~~~

Kết quả là chuỗi Nguyen An.

Lấy một giá trị số và chuyển thành DECIMAL:

~~~sql
SELECT JSON_VALUE(
    '{"item":"Keyboard","price":"1299.90"}',
    '$.price'
    RETURNING DECIMAL(10, 2)
) AS price;
~~~

Kết quả là số SQL 1299.90, có thể dùng trong phép so sánh số học:

~~~sql
SELECT
    JSON_VALUE('{"price":"1299.90"}', '$.price'
        RETURNING DECIMAL(10, 2)) * 2 AS double_price;
~~~

JSON_VALUE đặc biệt hữu ích khi ứng dụng cần:

- So sánh thuộc tính JSON như số, ngày hoặc chuỗi.
- Chuẩn hóa kiểu trả về thay vì giữ giá trị JSON.
- Đặt quy tắc rõ ràng cho thuộc tính bị thiếu hoặc sai kiểu.
- Tạo functional index để truy vấn theo một scalar path trong JSON.

JSON_VALUE dành cho một giá trị scalar. Nếu cần lấy object, array hoặc nhiều phần tử cùng lúc, hãy cân nhắc JSON_EXTRACT hoặc JSON_TABLE.

## 2. Điều kiện hỗ trợ theo phiên bản MySQL

JSON_VALUE không có trong mọi phiên bản MySQL. Cần kiểm tra phiên bản server thực tế trước khi đưa hàm vào schema, view, query hoặc migration.

| Phiên bản | Hỗ trợ JSON_VALUE | Ghi chú |
|---|---|---|
| MySQL 5.7 | Không | Dùng JSON_EXTRACT, JSON_UNQUOTE, toán tử JSON hoặc generated column |
| MySQL 8.0.0 đến 8.0.20 | Không | Chưa có JSON_VALUE |
| MySQL 8.0.21 | Có | Phiên bản đầu tiên giới thiệu JSON_VALUE; chưa hỗ trợ RETURNING YEAR |
| MySQL 8.0.22 trở lên | Có | Bổ sung RETURNING YEAR |
| MySQL 8.4 LTS | Có | Được tài liệu hóa trong Reference Manual 8.4 |
| MySQL 9.7 | Có | Được tài liệu hóa trong Reference Manual 9.7 |

### 2.1. Kiểm tra phiên bản server

~~~sql
SELECT VERSION() AS mysql_version;
~~~

Có thể kiểm tra nhanh bằng:

~~~sql
SHOW VARIABLES LIKE 'version';
~~~

Nếu môi trường chạy nhiều server hoặc có replica, hãy kiểm tra từng node có thể nhận query. Một query hợp lệ trên primary mới có thể thất bại khi ứng dụng gửi đến replica cũ hơn.

### 2.2. Mốc 8.0.21

MySQL 8.0.21 bổ sung JSON_VALUE. Mục tiêu quan trọng của hàm là trích xuất scalar có kiểu rõ ràng và đơn giản hóa việc tạo index trên JSON column.

Từ phiên bản này, có thể tạo index trên biểu thức JSON_VALUE, ví dụ:

~~~sql
CREATE TABLE inventory_demo (
    attributes JSON NOT NULL,
    INDEX ix_item_name (
        (JSON_VALUE(attributes, '$.name' RETURNING CHAR(40)))
    )
);
~~~

### 2.3. Mốc 8.0.22: RETURNING YEAR

MySQL 8.0.22 bổ sung YEAR vào các kiểu có thể chỉ định trong RETURNING.

Ví dụ:

~~~sql
SELECT JSON_VALUE(
    '{"manufactured_year":2024}',
    '$.manufactured_year'
    RETURNING YEAR
) AS manufactured_year;
~~~

YEAR không chấp nhận giá trị năm có một hoặc hai chữ số trong ngữ cảnh JSON_VALUE. Hãy lưu năm dưới dạng bốn chữ số và kiểm tra dữ liệu đầu vào trước khi chuyển đổi.

### 2.4. Phiên bản hàm và vòng đời hỗ trợ là hai việc khác nhau

Một phiên bản có hàm JSON_VALUE không có nghĩa nhánh phát hành đó vẫn còn trong thời gian hỗ trợ. Tài liệu Release Notes MySQL 8.0 hiện ghi nhận nhánh 8.0 đã kết thúc vòng đời vào tháng 4 năm 2026, sau phiên bản 8.0.46.

Khi chọn phiên bản triển khai, hãy kiểm tra cả hai điều kiện:

1. Phiên bản có hỗ trợ cú pháp và tính năng ứng dụng cần dùng hay không.
2. Nhánh phiên bản còn phù hợp với chính sách hỗ trợ, vá lỗi và vận hành của tổ chức hay không.

Với triển khai mới, ưu tiên nhánh MySQL còn được duy trì theo chính sách nền tảng, chẳng hạn 8.4 LTS hoặc nhánh Innovation hiện hành phù hợp với yêu cầu vận hành.

## 3. Cú pháp JSON_VALUE

Cú pháp tổng quát:

~~~text
JSON_VALUE(
    json_doc,
    path
    [RETURNING type]
    [{NULL | ERROR | DEFAULT value} ON EMPTY]
    [{NULL | ERROR | DEFAULT value} ON ERROR]
)
~~~

Có thể viết trên một dòng:

~~~text
JSON_VALUE(json_doc, path [RETURNING type] [on_empty] [on_error])
~~~

Trong đó:

- json_doc: JSON document cần đọc. Giá trị phải là JSON hợp lệ; nếu biểu thức là SQL NULL, kết quả là SQL NULL.
- path: JSON path trỏ đến vị trí cần lấy. MySQL yêu cầu path argument là string literal.
- RETURNING type: kiểu SQL mà kết quả được chuyển đổi sang.
- ON EMPTY: hành vi khi path không tìm thấy dữ liệu.
- ON ERROR: hành vi khi giá trị được chọn không thể trả về như scalar theo kiểu đã yêu cầu hoặc có lỗi chuyển đổi/truncation thuộc phạm vi xử lý của hàm.

Một ví dụ đầy đủ:

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"25"}',
    '$.quantity'
    RETURNING UNSIGNED
    DEFAULT 0 ON EMPTY
    ERROR ON ERROR
) AS quantity;
~~~

Ví dụ trên trả về số nguyên không dấu. Nếu thuộc tính quantity không tồn tại, hàm trả về 0. Nếu giá trị có tồn tại nhưng không chuyển được sang UNSIGNED, câu lệnh phát lỗi.

### 3.1. Path phải là string literal

JSON_VALUE yêu cầu path argument là chuỗi literal trong câu SQL. Không nên giả định có thể truyền một cột, biến hoặc parameter động làm path.

Ví dụ dùng literal:

~~~sql
SELECT JSON_VALUE(attributes, '$.customer.id' RETURNING UNSIGNED)
FROM order_event;
~~~

Nếu ứng dụng cần chọn path theo người dùng, hãy thiết kế whitelist path và tạo câu SQL phù hợp ở tầng ứng dụng. Không ghép trực tiếp chuỗi path tùy ý từ đầu vào không tin cậy.

### 3.2. JSON path bắt đầu từ $

Ký tự $ biểu diễn gốc của JSON document.

Ví dụ document:

~~~json
{
  "order": {
    "id": 501,
    "status": "PAID",
    "items": [
      {"sku": "KB-01", "quantity": 2},
      {"sku": "MS-02", "quantity": 1}
    ]
  }
}
~~~

Một số path:

| JSON path | Giá trị được chọn |
|---|---|
| $ | Toàn bộ document |
| $.order | Object order |
| $.order.id | Scalar 501 |
| $.order.status | Scalar PAID |
| $.order.items[0].sku | Scalar KB-01 |
| $.order.items[1].quantity | Scalar 1 |

JSON_VALUE phù hợp nhất với path trỏ tới một scalar như số, chuỗi, boolean hoặc giá trị có thể chuyển đổi sang kiểu SQL. Path trỏ tới object hoặc array sẽ kích hoạt xử lý ON ERROR.

## 4. RETURNING và kiểu dữ liệu

Nếu không ghi RETURNING, JSON_VALUE trả về VARCHAR(512).

Các kiểu RETURNING được hỗ trợ trong MySQL 8.4:

- FLOAT
- DOUBLE
- DECIMAL
- SIGNED
- UNSIGNED
- DATE
- TIME
- DATETIME
- YEAR
- CHAR
- JSON

Các kiểu này tương ứng với các kiểu không phải ARRAY mà CAST hỗ trợ trong ngữ cảnh JSON_VALUE. YEAR có từ MySQL 8.0.22.

### 4.1. Chuỗi với mặc định VARCHAR(512)

~~~sql
SELECT JSON_VALUE(
    '{"name":"Mechanical Keyboard"}',
    '$.name'
) AS product_name;
~~~

Nếu không có RETURNING, kiểu trả về là VARCHAR(512). Character set mặc định là utf8mb4 và collation là binary, do đó so sánh chuỗi phân biệt chữ hoa/chữ thường.

Khi chỉ định character set utf8mb4 cho kiểu CHAR, server dùng collation mặc định của character set này, thường không phân biệt hoa thường theo cấu hình mặc định của MySQL 8.0/8.4.

Ví dụ:

~~~sql
SELECT JSON_VALUE(
    '{"name":"Mechanical Keyboard"}',
    '$.name'
    RETURNING CHAR(80) CHARACTER SET utf8mb4
) AS product_name;
~~~

Chọn độ dài CHAR phù hợp với miền dữ liệu nếu giá trị được dùng trong index.

### 4.2. Số nguyên có dấu và không dấu

~~~sql
SELECT
    JSON_VALUE('{"id":"-25"}', '$.id' RETURNING SIGNED)
        AS signed_id,
    JSON_VALUE('{"quantity":"25"}', '$.quantity' RETURNING UNSIGNED)
        AS quantity;
~~~

SIGNED phù hợp với miền số có dấu. UNSIGNED phù hợp với số nguyên không âm như số lượng hoặc mã định danh số.

Không dùng UNSIGNED nếu dữ liệu có thể âm. Nếu giá trị không chuyển đổi được, ON ERROR sẽ quyết định kết quả.

### 4.3. DECIMAL cho tiền và tỷ lệ

~~~sql
SELECT JSON_VALUE(
    '{"unit_price":"1999.95"}',
    '$.unit_price'
    RETURNING DECIMAL(12, 2)
) AS unit_price;
~~~

Dùng DECIMAL khi cần phép tính thập phân chính xác, ví dụ tiền, thuế hoặc tỷ lệ. Không nên dùng FLOAT/DOUBLE cho dữ liệu tiền nếu nghiệp vụ yêu cầu độ chính xác thập phân.

### 4.4. FLOAT và DOUBLE

~~~sql
SELECT
    JSON_VALUE('{"temperature":"36.5"}', '$.temperature'
        RETURNING FLOAT) AS temperature_float,
    JSON_VALUE('{"ratio":"0.875"}', '$.ratio'
        RETURNING DOUBLE) AS ratio_double;
~~~

FLOAT và DOUBLE là kiểu số gần đúng. Chúng phù hợp với dữ liệu đo lường hoặc khoa học khi sai số dấu phẩy động được chấp nhận.

### 4.5. DATE, TIME và DATETIME

~~~sql
SELECT
    JSON_VALUE('{"date":"2026-11-19"}', '$.date'
        RETURNING DATE) AS event_date,
    JSON_VALUE('{"time":"09:30:00"}', '$.time'
        RETURNING TIME) AS event_time,
    JSON_VALUE('{"created_at":"2026-11-19 09:30:00"}', '$.created_at'
        RETURNING DATETIME) AS created_at;
~~~

Dữ liệu JSON cần có định dạng chuyển đổi được sang kiểu ngày giờ tương ứng. Giá trị sai định dạng hoặc không hợp lệ có thể kích hoạt ON ERROR.

### 4.6. JSON

RETURNING JSON trả về kiểu JSON. Kiểu này hữu ích khi muốn giữ một scalar dưới dạng JSON value hoặc tiếp tục truyền nó cho hàm JSON khác.

~~~sql
SELECT JSON_VALUE(
    '{"feature":true}',
    '$.feature'
    RETURNING JSON
) AS feature_value;
~~~

Nếu mục tiêu là so sánh boolean, hãy thử nghiệm cách chuyển đổi và kiểu dữ liệu của biểu thức trên đúng phiên bản server. Nếu mục tiêu là lấy object hoặc array, dùng JSON_EXTRACT thay vì JSON_VALUE.

## 5. ON EMPTY: khi path không tìm thấy dữ liệu

ON EMPTY điều khiển kết quả khi JSON path không khớp vị trí nào trong document.

Có ba lựa chọn:

| Cú pháp | Hành vi |
|---|---|
| NULL ON EMPTY | Trả về SQL NULL; đây là mặc định |
| DEFAULT value ON EMPTY | Trả về giá trị mặc định |
| ERROR ON EMPTY | Phát lỗi |

Ví dụ document không có thuộc tính discount:

~~~sql
SELECT JSON_VALUE(
    '{"price":100}',
    '$.discount'
    RETURNING DECIMAL(8, 2)
    DEFAULT 0.00 ON EMPTY
) AS discount;
~~~

Kết quả là 0.00.

Nếu thuộc tính bắt buộc phải có, dùng ERROR ON EMPTY:

~~~sql
SELECT JSON_VALUE(
    '{"price":100}',
    '$.customer_id'
    RETURNING UNSIGNED
    ERROR ON EMPTY
) AS customer_id;
~~~

Câu lệnh phát lỗi nếu path không có dữ liệu.

### 5.1. DEFAULT phải phù hợp kiểu trả về

Giá trị DEFAULT phải chuyển đổi phù hợp với kiểu RETURNING.

~~~sql
SELECT JSON_VALUE(
    '{"name":"Keyboard"}',
    '$.sku'
    RETURNING CHAR(30)
    DEFAULT 'UNKNOWN' ON EMPTY
) AS sku;
~~~

Với kiểu số:

~~~sql
SELECT JSON_VALUE(
    '{"name":"Keyboard"}',
    '$.stock'
    RETURNING UNSIGNED
    DEFAULT 0 ON EMPTY
) AS stock;
~~~

Không dùng giá trị mặc định sai kiểu. Nếu RETURNING là UNSIGNED, hãy dùng giá trị mặc định số không âm.

### 5.2. ON EMPTY không xử lý JSON null literal

Cần phân biệt hai trường hợp:

- Path không tồn tại: ON EMPTY được kích hoạt.
- Path tồn tại và giá trị là JSON null: JSON_VALUE trả SQL NULL.

Ví dụ:

~~~sql
SELECT
    JSON_VALUE('{"status":null}', '$.status'
        RETURNING CHAR(20) DEFAULT 'MISSING' ON EMPTY) AS explicit_null,
    JSON_VALUE('{}', '$.status'
        RETURNING CHAR(20) DEFAULT 'MISSING' ON EMPTY) AS missing_value;
~~~

Kết quả:

- explicit_null là SQL NULL vì path tồn tại và chứa JSON null.
- missing_value là MISSING vì path không tồn tại và ON EMPTY được kích hoạt.

Nếu ứng dụng cần phân biệt JSON null với thuộc tính bị thiếu, hãy kiểm tra sự tồn tại của path bằng JSON_CONTAINS_PATH.

~~~sql
SELECT
    JSON_CONTAINS_PATH('{"status":null}', 'one', '$.status')
        AS status_exists,
    JSON_CONTAINS_PATH('{}', 'one', '$.status')
        AS missing_status_exists;
~~~

Kết quả lần lượt là 1 và 0.

## 6. ON ERROR: khi không thể trả về scalar theo kiểu yêu cầu

ON ERROR điều khiển các lỗi xử lý giá trị mà JSON_VALUE nhận diện, gồm:

- Path chọn một object hoặc array thay vì scalar.
- Path có wildcard hoặc range dẫn đến nhiều vị trí kết quả.
- Không thể chuyển giá trị sang kiểu RETURNING.
- Giá trị bị truncation trong quá trình xử lý.

Có ba lựa chọn:

| Cú pháp | Hành vi |
|---|---|
| NULL ON ERROR | Trả SQL NULL; đây là mặc định |
| DEFAULT value ON ERROR | Trả giá trị mặc định |
| ERROR ON ERROR | Phát lỗi |

### 6.1. NULL ON ERROR

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"many"}',
    '$.quantity'
    RETURNING UNSIGNED
    NULL ON ERROR
) AS quantity;
~~~

Giá trị many không chuyển được sang UNSIGNED nên kết quả là SQL NULL. Lỗi chuyển đổi vẫn phát warning; NULL ON ERROR không có nghĩa là mọi dấu hiệu dữ liệu sai đều biến mất.

### 6.2. DEFAULT ON ERROR

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"many"}',
    '$.quantity'
    RETURNING UNSIGNED
    DEFAULT 0 ON ERROR
) AS quantity;
~~~

Nếu chuyển đổi thất bại, kết quả là 0.

Không nên đặt DEFAULT tùy tiện chỉ để query luôn trả về dữ liệu. Giá trị mặc định có thể che giấu lỗi chất lượng dữ liệu nếu ứng dụng không theo dõi warning hoặc không có quy trình kiểm tra dữ liệu nguồn.

### 6.3. ERROR ON ERROR

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"many"}',
    '$.quantity'
    RETURNING UNSIGNED
    ERROR ON ERROR
) AS quantity;
~~~

Câu lệnh phát lỗi khi giá trị không thể chuyển đổi. Đây là lựa chọn phù hợp khi dữ liệu phải tuân thủ schema nghiêm ngặt và caller cần biết ngay khi dữ liệu không hợp lệ.

### 6.4. Path trỏ tới object hoặc array

~~~sql
SELECT JSON_VALUE(
    '{"customer":{"id":101}}',
    '$.customer'
    RETURNING CHAR(100)
    ERROR ON ERROR
);
~~~

Path $.customer chọn một object, không phải scalar. ON ERROR được kích hoạt.

Nếu cần lấy object:

~~~sql
SELECT JSON_EXTRACT(
    '{"customer":{"id":101}}',
    '$.customer'
) AS customer_object;
~~~

Nếu cần chuyển các phần tử array thành hàng quan hệ, hãy xem xét JSON_TABLE.

### 6.5. Path trả về nhiều vị trí

~~~sql
SELECT JSON_VALUE(
    '[{"id":10},{"id":20}]',
    '$[*].id'
    RETURNING UNSIGNED
    ERROR ON ERROR
);
~~~

Path wildcard khớp nhiều giá trị. JSON_VALUE cần một scalar nên trường hợp nhiều kết quả kích hoạt ON ERROR.

Nếu cần tất cả phần tử, dùng JSON_EXTRACT hoặc JSON_TABLE:

~~~sql
SELECT JSON_EXTRACT(
    '[{"id":10},{"id":20}]',
    '$[*].id'
) AS ids;
~~~

## 7. Phân biệt lỗi JSON input và ON ERROR

ON ERROR không phải bộ bắt mọi lỗi liên quan đến JSON.

MySQL kiểm tra tính hợp lệ của JSON document và JSON path. Nếu JSON input hoặc path không hợp lệ, server phát SQL error mà không kích hoạt ON ERROR.

Ví dụ minh họa JSON document không hợp lệ:

~~~sql
SELECT JSON_VALUE(
    '{bad json',
    '$.id'
    RETURNING UNSIGNED
    NULL ON ERROR
);
~~~

Câu lệnh này vẫn phát lỗi do JSON document không hợp lệ. NULL ON ERROR không biến JSON syntax error thành NULL.

Một JSON column đã lưu thành công trong MySQL luôn chứa JSON hợp lệ. Trường hợp input không hợp lệ thường xuất hiện khi truyền chuỗi từ ứng dụng vào hàm hoặc khi xử lý cột VARCHAR chứa văn bản JSON chưa được kiểm tra.

Path sai cú pháp cũng phát SQL error. Hãy kiểm tra path bằng test case trước khi đưa vào ứng dụng.

## 8. Thứ tự ON EMPTY và ON ERROR

Nếu khai báo cả hai clause, ON EMPTY phải đứng trước ON ERROR.

Cú pháp đúng:

~~~sql
SELECT JSON_VALUE(
    '{"price":"invalid"}',
    '$.price'
    RETURNING DECIMAL(10, 2)
    DEFAULT 0.00 ON EMPTY
    ERROR ON ERROR
);
~~~

Cú pháp sai:

~~~sql
SELECT JSON_VALUE(
    '{"price":"invalid"}',
    '$.price'
    RETURNING DECIMAL(10, 2)
    ERROR ON ERROR
    DEFAULT 0.00 ON EMPTY
);
~~~

Thứ tự sai gây syntax error. Hãy giữ quy ước thống nhất trong query và code review.

### 8.1. Mặc định của hai clause

Nếu không chỉ định ON EMPTY, hành vi mặc định là NULL ON EMPTY.

Nếu không chỉ định ON ERROR, hành vi mặc định là NULL ON ERROR.

Ví dụ:

~~~sql
SELECT JSON_VALUE(
    '{"price":"49.95"}',
    '$.price'
    RETURNING DECIMAL(8, 2)
);
~~~

Câu lệnh trên dùng cả hai mặc định. Khi path thiếu hoặc chuyển đổi lỗi, hàm trả SQL NULL theo quy tắc tương ứng; tuy nhiên JSON document/path không hợp lệ vẫn phát lỗi SQL.

### 8.2. Conversion warning vẫn cần được theo dõi

Khi lỗi chuyển đổi xảy ra, MySQL phát warning ngay cả khi đã chỉ định NULL ON ERROR hoặc DEFAULT ... ON ERROR.

Trong môi trường phát triển, có thể kiểm tra warning ngay sau câu lệnh:

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"not-a-number"}',
    '$.quantity'
    RETURNING UNSIGNED
    NULL ON ERROR
);

SHOW WARNINGS;
~~~

Trong ứng dụng, hãy cân nhắc ghi nhận dữ liệu nguồn sai kiểu hoặc từ chối bản ghi ở tầng ingest. Không nên dựa vào NULL ON ERROR để thay thế quy trình kiểm soát chất lượng dữ liệu.

## 9. JSON_VALUE so với JSON_EXTRACT, -> và ->>

Các hàm và toán tử này đều đọc dữ liệu từ JSON nhưng có kiểu kết quả và mục đích khác nhau.

| Công cụ | Kết quả | Phù hợp khi |
|---|---|---|
| JSON_EXTRACT(doc, path) | JSON value | Cần giữ cấu trúc JSON, object hoặc array |
| doc -> path | Tương đương JSON_EXTRACT | Muốn viết ngắn khi lấy JSON value |
| doc ->> path | JSON_UNQUOTE(JSON_EXTRACT(...)) | Cần chuỗi đã bỏ dấu quote JSON |
| JSON_VALUE(doc, path) | SQL scalar, mặc định VARCHAR(512) hoặc kiểu RETURNING | Cần giá trị scalar với kiểu SQL rõ ràng |

Ví dụ JSON_EXTRACT trả JSON string có dấu quote:

~~~sql
SELECT JSON_EXTRACT(
    '{"name":"Keyboard"}',
    '$.name'
) AS extracted_json;
~~~

Kết quả hiển thị là "Keyboard" với dấu quote của JSON.

JSON_UNQUOTE hoặc toán tử ->> trả chuỗi đã bỏ quote:

~~~sql
SELECT
    JSON_UNQUOTE(JSON_EXTRACT('{"name":"Keyboard"}', '$.name'))
        AS unquoted_name,
    ('{"name":"Keyboard"}' ->> '$.name')
        AS operator_name;
~~~

JSON_VALUE có thể trả trực tiếp kiểu SQL:

~~~sql
SELECT JSON_VALUE(
    '{"price":"49.95"}',
    '$.price'
    RETURNING DECIMAL(8, 2)
) AS price;
~~~

Ngoại trừ các trường hợp JSON_VALUE trả NULL, biểu thức có RETURNING type tương đương về ý tưởng với:

~~~sql
SELECT CAST(
    JSON_UNQUOTE(JSON_EXTRACT(json_doc, path))
    AS type
);
~~~

JSON_VALUE thêm ON EMPTY và ON ERROR, giúp định nghĩa rõ cách xử lý path không tồn tại và lỗi chuyển đổi. Hành vi NULL của JSON_VALUE có thể khác cách CAST xử lý một số giá trị; không thay thế máy móc nếu query hiện tại phụ thuộc vào NULL hoặc warning.

## 10. JSON_VALUE và functional index

JSON column không được index trực tiếp như một scalar column thông thường. Khi ứng dụng thường xuyên lọc theo một scalar path, có thể tạo index trên biểu thức JSON_VALUE.

Functional key parts có từ MySQL 8.0.13. Vì JSON_VALUE chỉ có từ MySQL 8.0.21, kết hợp hai tính năng để index JSON_VALUE cần MySQL 8.0.21 trở lên.

Ví dụ:

~~~sql
CREATE TABLE json_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (order_id),
    INDEX ix_customer_id (
        (JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED))
    ),
    INDEX ix_amount (
        (JSON_VALUE(attributes, '$.amount' RETURNING DECIMAL(10, 2)))
    ),
    INDEX ix_status (
        (JSON_VALUE(attributes, '$.status' RETURNING CHAR(16)))
    )
) ENGINE = InnoDB;
~~~

Mỗi functional key part đặt biểu thức trong một cặp ngoặc riêng bên trong phần khai báo index. Trong ví dụ, ba index trích xuất ba scalar khác nhau.

### 10.1. Nạp dữ liệu mẫu

~~~sql
INSERT INTO json_order_demo (order_id, attributes)
VALUES
(
    1001,
    JSON_OBJECT(
        'customer_id', 101,
        'amount', 125.50,
        'status', 'PAID'
    )
),
(
    1002,
    JSON_OBJECT(
        'customer_id', 102,
        'amount', 980.00,
        'status', 'PENDING'
    )
),
(
    1003,
    JSON_OBJECT(
        'customer_id', 101,
        'amount', 2500.00,
        'status', 'PAID'
    )
),
(
    1004,
    JSON_OBJECT(
        'customer_id', 103,
        'amount', 75.25,
        'status', 'CANCELLED'
    )
);
~~~

### 10.2. Truy vấn theo biểu thức tương ứng

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.customer_id'
    RETURNING UNSIGNED
) = 101;
~~~

Biểu thức trong WHERE khớp với biểu thức index ix_customer_id: cùng cột JSON, cùng path và cùng kiểu RETURNING.

Truy vấn theo số tiền:

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.amount'
    RETURNING DECIMAL(10, 2)
) >= 1000.00;
~~~

Truy vấn theo trạng thái:

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.status'
    RETURNING CHAR(16)
) = 'PAID';
~~~

### 10.3. Xác minh index bằng EXPLAIN

~~~sql
EXPLAIN
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.customer_id'
    RETURNING UNSIGNED
) = 101;
~~~

Kiểm tra các cột possible_keys và key trong execution plan. Nếu optimizer chọn ix_customer_id, cột key sẽ hiển thị tên index đó.

Có index không đồng nghĩa mọi query đều bắt buộc dùng index. Optimizer có thể chọn table scan khi bảng nhỏ, điều kiện lọc không chọn lọc hoặc chi phí dùng index cao hơn.

### 10.4. Biểu thức truy vấn phải khớp biểu thức index

Khi tạo functional index, hãy dùng cùng JSON path và cùng kiểu RETURNING trong WHERE.

Ví dụ key part trong khai báo index:

~~~text
INDEX ix_customer_id (
    (JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED))
)
~~~

Query phù hợp:

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED) = 101;
~~~

Nếu query bỏ RETURNING hoặc đổi sang CHAR, biểu thức không còn giống biểu thức index. Không nên giả định optimizer sẽ tự chuyển đổi mọi cách viết về cùng một functional key part.

Với biểu thức chuỗi, character set và collation cũng có thể ảnh hưởng khả năng khớp biểu thức. Hãy xác minh bằng EXPLAIN trên đúng phiên bản và schema thật.

### 10.5. Khi nào dùng generated column?

Generated column vẫn hữu ích khi:

- Cần đặt tên thuộc tính JSON đã trích xuất để query dễ đọc.
- Muốn dùng cùng một scalar ở nhiều query.
- Cần tương thích phiên bản không có JSON_VALUE.
- Muốn kiểm soát kiểu dữ liệu, NULL hoặc constraint tại schema.

Ví dụ với MySQL có JSON_VALUE:

~~~sql
CREATE TABLE json_order_generated_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    customer_id BIGINT UNSIGNED
        GENERATED ALWAYS AS (
            JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED)
        ) STORED,
    PRIMARY KEY (order_id),
    INDEX ix_customer_id (customer_id)
) ENGINE = InnoDB;
~~~

Generated column làm rõ scalar được trích xuất và cho phép query bằng tên customer_id.

## 11. Cách thay thế trên MySQL cũ hơn 8.0.21

Nếu server chưa hỗ trợ JSON_VALUE, có thể dùng các hàm JSON đã có trong MySQL 5.7 và các bản MySQL 8.0 trước 8.0.21.

### 11.1. JSON_EXTRACT

~~~sql
SELECT JSON_EXTRACT(
    '{"customer_id":101}',
    '$.customer_id'
) AS customer_id_json;
~~~

JSON_EXTRACT trả JSON value. Khi so sánh số hoặc chuỗi, hãy hiểu rõ kiểu JSON và quy tắc so sánh của MySQL.

### 11.2. JSON_UNQUOTE kết hợp CAST

~~~sql
SELECT CAST(
    JSON_UNQUOTE(
        JSON_EXTRACT('{"customer_id":"101"}', '$.customer_id')
    )
    AS UNSIGNED
) AS customer_id;
~~~

Cách này tương tự phần chuyển đổi kiểu của JSON_VALUE, nhưng không có ON EMPTY và ON ERROR của JSON_VALUE.

Nếu cần mặc định khi path thiếu, có thể dùng COALESCE:

~~~sql
SELECT COALESCE(
    CAST(
        JSON_UNQUOTE(
            JSON_EXTRACT('{"customer_id":"101"}', '$.customer_id')
        )
        AS UNSIGNED
    ),
    0
) AS customer_id;
~~~

COALESCE chỉ xử lý NULL ở kết quả. Nó không thay thế đầy đủ các quy tắc lỗi chuyển đổi và warning của JSON_VALUE.

### 11.3. Generated column trên phiên bản cũ

~~~sql
CREATE TABLE legacy_json_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    customer_id BIGINT UNSIGNED
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(
                    JSON_EXTRACT(attributes, '$.customer_id')
                )
                AS UNSIGNED
            )
        ) STORED,
    PRIMARY KEY (order_id),
    INDEX ix_customer_id (customer_id)
) ENGINE = InnoDB;
~~~

Generated column giúp tạo index trên scalar được trích xuất từ JSON. Hãy kiểm thử dữ liệu thiếu thuộc tính, JSON null và dữ liệu sai kiểu vì CAST có thể phát warning hoặc trả NULL theo quy tắc chuyển đổi.

### 11.4. Chọn giải pháp theo phiên bản

| Môi trường | Cách triển khai |
|---|---|
| MySQL 5.7 | JSON_EXTRACT, JSON_UNQUOTE, CAST, generated column |
| MySQL 8.0.0–8.0.20 | JSON_EXTRACT, JSON_UNQUOTE, CAST, generated column |
| MySQL 8.0.21 | JSON_VALUE; functional index trên biểu thức JSON_VALUE |
| MySQL 8.0.22 trở lên | JSON_VALUE và RETURNING YEAR |
| MySQL 8.4 / 9.7 | JSON_VALUE, RETURNING và index expression theo tài liệu phiên bản |

Không triển khai query chứa JSON_VALUE lên server cũ hơn 8.0.21. Hãy kiểm tra version trước migration và trong pipeline phát hành.

## 12. Những lỗi và hiểu nhầm thường gặp

| Lỗi hoặc hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| JSON_VALUE có từ MySQL 8.0.0 | Hàm được giới thiệu ở 8.0.21 | Kiểm tra VERSION() |
| MySQL 5.7 dùng được JSON_VALUE | Không hỗ trợ | Dùng JSON_EXTRACT và CAST |
| RETURNING YEAR có từ 8.0.21 | YEAR có từ 8.0.22 | Kiểm tra version nếu dùng YEAR |
| JSON_VALUE trả JSON document nguyên vẹn | Hàm hướng đến một scalar | Dùng JSON_EXTRACT cho object/array |
| Path không tồn tại là lỗi chuyển đổi | Đây là ON EMPTY | Chọn NULL, DEFAULT hoặc ERROR ON EMPTY |
| JSON null giống path không tồn tại | JSON null trả SQL NULL; path thiếu kích hoạt ON EMPTY | Dùng JSON_CONTAINS_PATH nếu cần phân biệt |
| ON ERROR bắt mọi lỗi JSON | JSON document/path không hợp lệ phát SQL error riêng | Validate JSON và path trước |
| NULL ON ERROR không phát warning | Lỗi chuyển đổi vẫn phát warning | Kiểm tra warning và chất lượng dữ liệu |
| ON ERROR có thể đứng trước ON EMPTY | Thứ tự đó sai cú pháp | Đặt ON EMPTY trước ON ERROR |
| Mặc định trả kiểu JSON | Mặc định là VARCHAR(512) | Chỉ định RETURNING khi cần kiểu rõ |
| Path có thể truyền bằng biến tùy ý | Path phải là string literal | Whitelist path ở ứng dụng |
| JSON column có thể index trực tiếp | Cần index trên biểu thức hoặc generated column | Dùng JSON_VALUE functional index hoặc generated column |
| Có index là query chắc chắn dùng index | Optimizer quyết định theo chi phí | Xem EXPLAIN |
| Functional index không cần khớp biểu thức | Path và RETURNING type cần khớp biểu thức index | Dùng cùng biểu thức trong WHERE |
| Dùng UNSIGNED cho mọi giá trị số | Giá trị âm không phù hợp | Chọn SIGNED hoặc DECIMAL theo miền dữ liệu |
| DEFAULT ON ERROR thay thế kiểm tra dữ liệu | Giá trị sai có thể bị che thành mặc định | Theo dõi warning và xác thực dữ liệu nguồn |

## 13. Quy trình áp dụng JSON_VALUE trong ứng dụng

Khi thêm JSON_VALUE vào một query hoặc schema:

1. Kiểm tra phiên bản MySQL của tất cả server nhận query.
2. Xác định path trỏ đến scalar hay object/array.
3. Xác định kiểu SQL thật của giá trị: CHAR, UNSIGNED, DECIMAL, DATE hoặc kiểu khác.
4. Chọn RETURNING rõ ràng nếu giá trị được dùng trong so sánh hoặc tính toán.
5. Quyết định path thiếu có được phép hay không.
6. Chọn ON EMPTY phù hợp với hợp đồng dữ liệu.
7. Chọn ON ERROR để phát lỗi, trả NULL hoặc dùng DEFAULT.
8. Nhớ rằng JSON null trả SQL NULL và không kích hoạt ON EMPTY.
9. Kiểm tra warning sau lỗi chuyển đổi.
10. Nếu query thường xuyên lọc theo path, cân nhắc functional index hoặc generated column.
11. Dùng cùng path, RETURNING type và character set/collation khi truy vấn biểu thức đã index.
12. Chạy EXPLAIN để xác nhận optimizer có chọn index.
13. Kiểm thử document thiếu thuộc tính, null, sai kiểu, array/object và JSON input không hợp lệ.
14. Kiểm tra tương thích trên replica, môi trường staging và pipeline migration.

Sơ đồ quyết định:

~~~mermaid
flowchart TD
    A[Đọc thuộc tính JSON] --> B{MySQL từ 8.0.21?}
    B -->|Không| C[JSON_EXTRACT + CAST hoặc generated column]
    B -->|Có| D{Path trả về scalar?}
    D -->|Không| E[JSON_EXTRACT hoặc JSON_TABLE]
    D -->|Có| F[Chọn RETURNING type]
    F --> G{Path có thể thiếu?}
    G -->|Có| H[Chọn ON EMPTY]
    G -->|Không| I[ERROR ON EMPTY]
    H --> J[Chọn ON ERROR]
    I --> J
    J --> K{Query lọc thường xuyên?}
    K -->|Có| L[Functional index hoặc generated column]
    K -->|Không| M[Dùng trực tiếp trong query]
    L --> N[EXPLAIN và kiểm thử]
    M --> N
    C --> N
    E --> N
~~~

## 14. Bài tập thực hành

### Bài 1: Kiểm tra hỗ trợ phiên bản

Dùng SELECT VERSION() để kiểm tra server. Xác định JSON_VALUE có được hỗ trợ hay không. Giải thích khác biệt giữa MySQL 8.0.20, 8.0.21 và 8.0.22.

### Bài 2: Trích xuất chuỗi

Cho document chứa tên khách hàng và email. Dùng JSON_VALUE lấy từng thuộc tính bằng RETURNING CHAR.

### Bài 3: Chuyển đổi số

Cho thuộc tính quantity lưu dưới dạng chuỗi. Dùng RETURNING UNSIGNED và thử giá trị hợp lệ, giá trị âm và chuỗi không phải số.

### Bài 4: ON EMPTY

Tạo document không có thuộc tính discount. So sánh NULL ON EMPTY, DEFAULT 0 ON EMPTY và ERROR ON EMPTY.

### Bài 5: JSON null

So sánh document có status là JSON null với document không có status. Dùng JSON_CONTAINS_PATH để phân biệt hai trường hợp.

### Bài 6: ON ERROR

Thử chuyển chuỗi invalid-number sang DECIMAL. So sánh NULL ON ERROR, DEFAULT 0 ON ERROR và ERROR ON ERROR. Kiểm tra warning sau câu lệnh.

### Bài 7: Object và array

Dùng JSON_VALUE với path trỏ đến object, array và wildcard nhiều kết quả. Sau đó viết lại bằng JSON_EXTRACT.

### Bài 8: Thứ tự clause

Viết câu JSON_VALUE có cả ON EMPTY và ON ERROR. Đổi thứ tự hai clause để quan sát syntax error.

### Bài 9: Functional index

Tạo bảng có cột JSON attributes, tạo index trên JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED), nạp dữ liệu và dùng EXPLAIN để kiểm tra query lọc theo customer_id.

### Bài 10: Generated column tương thích cũ

Viết lại bài 9 bằng generated column sử dụng JSON_EXTRACT, JSON_UNQUOTE và CAST. So sánh cách query và cách quản lý schema.

### Bài 11: Phân biệt kiểu trả về

So sánh JSON_EXTRACT, ->>, JSON_VALUE mặc định và JSON_VALUE RETURNING DECIMAL trên cùng một thuộc tính.

### Bài 12: Thiết kế hợp đồng dữ liệu

Thiết kế quy tắc cho ba thuộc tính JSON: customer_id bắt buộc, discount tùy chọn, created_at phải là DATETIME. Chọn RETURNING, ON EMPTY và ON ERROR cho từng thuộc tính và giải thích lựa chọn.

## Kết luận

JSON_VALUE trích xuất một scalar từ JSON document và có thể chuyển đổi kết quả sang kiểu SQL bằng RETURNING. Hàm được giới thiệu trong MySQL 8.0.21; RETURNING YEAR được hỗ trợ từ 8.0.22. Nếu không ghi RETURNING, kết quả mặc định là VARCHAR(512).

ON EMPTY xử lý path không tìm thấy dữ liệu; ON ERROR xử lý object/array, nhiều kết quả, lỗi chuyển đổi hoặc truncation thuộc phạm vi hàm. JSON null trả SQL NULL, còn JSON document hoặc path không hợp lệ phát SQL error riêng. Khi khai báo cả hai clause, ON EMPTY phải đứng trước ON ERROR.

Với query lọc thường xuyên theo scalar trong JSON, có thể tạo functional index trên biểu thức JSON_VALUE và xác minh bằng EXPLAIN. Khi cần tương thích server cũ hơn 8.0.21, dùng JSON_EXTRACT kết hợp JSON_UNQUOTE, CAST hoặc generated column.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Functions That Search JSON Values: https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html
- MySQL 9.7 Reference Manual — Functions That Search JSON Values: https://dev.mysql.com/doc/refman/9.7/en/json-search-functions.html
- MySQL 8.0 Reference Manual — Functions That Search JSON Values: https://dev.mysql.com/doc/refman/8.0/en/json-search-functions.html
- MySQL 8.0 Release Notes — Changes in MySQL 8.0.21: https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-21.html
- MySQL 8.0 Release Notes — Changes in MySQL 8.0.22: https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-22.html
- MySQL 8.4 Reference Manual — CREATE INDEX Statement and Functional Key Parts: https://dev.mysql.com/doc/refman/8.4/en/create-index.html
- MySQL 8.4 Reference Manual — Generated Columns and JSON Indexing: https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html
- MySQL 8.4 Reference Manual — JSON Data Type and JSON Path Syntax: https://dev.mysql.com/doc/refman/8.4/en/json.html

