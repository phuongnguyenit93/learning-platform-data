# JSON_TABLE để chuyển tài liệu thành dữ liệu dạng bảng

JSON thường được dùng để lưu các thuộc tính linh hoạt hoặc một danh sách phần tử đi kèm với bản ghi chính. Tuy nhiên, nhiều truy vấn phân tích và nghiệp vụ cần làm việc với từng phần tử như một hàng quan hệ: lọc theo mã sản phẩm, tính tổng số lượng, nối với bảng danh mục hoặc nhóm theo thuộc tính.

MySQL cung cấp hàm bảng JSON_TABLE() để chiếu một tài liệu JSON thành các hàng và cột SQL. Hàm này đọc một đường dẫn JSON làm nguồn hàng, sau đó ánh xạ các giá trị ở từng phần tử vào những cột có kiểu dữ liệu SQL.

Ví dụ, một đơn hàng có thể lưu danh sách mặt hàng trong cột JSON. JSON_TABLE() có thể biến từng phần tử của mảng items thành một hàng để tính tổng tiền hoặc nối với bảng sản phẩm.

Bài viết tập trung vào cách dùng JSON_TABLE() trong FROM, khai báo cột bằng PATH, FOR ORDINALITY và EXISTS PATH, xử lý giá trị thiếu bằng ON EMPTY, xử lý lỗi bằng ON ERROR, mở rộng mảng lồng nhau bằng NESTED PATH và kiểm soát tác động của việc mở rộng JSON thành nhiều hàng.

## 1. JSON_TABLE() giải quyết bài toán gì?

Giả sử bảng orders lưu thông tin đơn hàng và một tài liệu JSON mô tả các mặt hàng:

~~~json
{
  "customerId": 501,
  "items": [
    {"sku": "KB-01", "qty": 2, "unitPrice": 350000},
    {"sku": "MS-02", "qty": 1, "unitPrice": 180000}
  ]
}
~~~

Nếu chỉ dùng JSON_EXTRACT(), kết quả thường vẫn là một giá trị JSON. Muốn lấy phần tử mảng thứ nhất, thứ hai hoặc một thuộc tính riêng, câu SQL phải tự xử lý đường dẫn và kiểu dữ liệu.

JSON_TABLE() tạo ra một tập hàng quan hệ:

| sku | qty | unit_price |
|---|---:|---:|
| KB-01 | 2 | 350000.00 |
| MS-02 | 1 | 180000.00 |

Sau khi được chuyển thành hàng và cột SQL, dữ liệu có thể tham gia vào các thao tác quen thuộc:

- WHERE để lọc từng phần tử.
- JOIN để nối mã trong JSON với bảng quan hệ.
- SUM(), AVG(), COUNT() để tổng hợp.
- GROUP BY để thống kê theo thuộc tính.
- ORDER BY để sắp xếp các phần tử.
- Window function để phân tích từng hàng đã bung ra.

JSON_TABLE() là table function: nó cung cấp một nguồn dữ liệu dạng bảng trong câu truy vấn, không tạo một bảng vật lý mới và không sửa tài liệu JSON nguồn.

### 1.1. So sánh JSON_TABLE() với các hàm JSON khác

| Công cụ | Kết quả chính | Khi nên dùng |
|---|---|---|
| JSON_EXTRACT() | Một giá trị JSON | Lấy một thuộc tính hoặc một nhánh JSON |
| JSON_UNQUOTE() | Chuỗi SQL từ một giá trị JSON dạng chuỗi | Bỏ lớp quote JSON khi cần chuỗi |
| JSON_VALUE() | Một giá trị SQL scalar theo đường dẫn | Lấy một giá trị đơn lẻ có kiểu SQL |
| JSON_CONTAINS() | TRUE/FALSE hoặc 1/0 | Kiểm tra tài liệu có chứa giá trị hay không |
| JSON_TABLE() | Nhiều hàng với các cột SQL | Bung mảng hoặc cấu trúc JSON thành dữ liệu dạng bảng |

JSON_TABLE() đặc biệt hữu ích khi cần xử lý từng phần tử trong một mảng. Nếu chỉ cần lấy một giá trị scalar, JSON_VALUE() hoặc JSON_EXTRACT() có thể ngắn gọn hơn.

### 1.2. Phiên bản MySQL

JSON_TABLE() có từ MySQL 8.0.4. Một số hành vi liên quan đến lỗi và giá trị JSON null thay đổi trong các bản 8.0:

- Từ MySQL 8.0.20, cách viết ON ERROR trước ON EMPTY bị deprecated; nên luôn viết ON EMPTY trước ON ERROR.
- Từ MySQL 8.0.21, giá trị JSON null được ánh xạ thành SQL NULL trong cột JSON_TABLE(); các bản trước đó xử lý trường hợp này như lỗi.
- EXPLAIN ANALYZE có từ MySQL 8.0.18; có thể dùng để đo số hàng và thời gian thực tế khi truy vấn JSON_TABLE().

Khi ứng dụng hỗ trợ nhiều phiên bản MySQL, hãy kiểm tra phiên bản server thực tế và thử các trường hợp JSON null, giá trị thiếu và kiểu dữ liệu không phù hợp trên phiên bản mục tiêu.

## 2. Chuẩn bị bảng và tài liệu JSON

Ví dụ xuyên suốt sử dụng bảng đơn hàng:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    document JSON NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE = InnoDB;
~~~

Thêm dữ liệu mẫu:

~~~sql
INSERT INTO orders (order_id, customer_id, created_at, document)
VALUES
(
    1001,
    501,
    '2026-02-10 09:30:00',
    JSON_OBJECT(
        'customerId', 501,
        'items', JSON_ARRAY(
            JSON_OBJECT(
                'sku', 'KB-01',
                'qty', 2,
                'unitPrice', 350000
            ),
            JSON_OBJECT(
                'sku', 'MS-02',
                'qty', 1,
                'unitPrice', 180000
            )
        )
    )
),
(
    1002,
    502,
    '2026-02-11 14:15:00',
    JSON_OBJECT(
        'customerId', 502,
        'items', JSON_ARRAY(
            JSON_OBJECT(
                'sku', 'HD-03',
                'qty', 3,
                'unitPrice', 90000
            )
        )
    )
);
~~~

Cột document có kiểu JSON nên MySQL kiểm tra tính hợp lệ của tài liệu khi ghi. Mỗi hàng trong orders vẫn là một đơn hàng; mảng items chứa các mặt hàng thuộc đơn đó.

## 3. Cú pháp JSON_TABLE()

JSON_TABLE() thường xuất hiện trong mệnh đề FROM:

~~~sql
JSON_TABLE(
    json_expression,
    row_path
    COLUMNS (
        column_definition [, column_definition] ...
    )
) AS table_alias
~~~

Trong đó:

- json_expression là biểu thức tạo ra tài liệu JSON cần đọc.
- row_path là đường dẫn xác định các node sẽ tạo thành hàng.
- COLUMNS mô tả các cột SQL lấy từ mỗi node.
- table_alias là bí danh bắt buộc để tham chiếu các cột do JSON_TABLE() tạo ra.

Các dạng khai báo cột quan trọng:

~~~sql
column_name FOR ORDINALITY

column_name data_type PATH json_path
    [on_empty]
    [on_error]

column_name data_type EXISTS PATH json_path

NESTED [PATH] json_path COLUMNS (
    nested_column_definition [, nested_column_definition] ...
)
~~~

Các mệnh đề xử lý trường hợp đặc biệt:

~~~sql
{NULL | DEFAULT json_string | ERROR} ON EMPTY
{NULL | DEFAULT json_string | ERROR} ON ERROR
~~~

Không phải cột nào cũng cần cả hai mệnh đề. Nếu không chỉ định, MySQL dùng hành vi mặc định tương ứng; trong hệ thống cần hợp đồng dữ liệu rõ ràng, nên khai báo tường minh cho những trường quan trọng.

## 4. Bung một mảng JSON thành nhiều hàng

Đường dẫn hàng thường trỏ đến một mảng bằng ký hiệu [*]. Ví dụ:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty,
    jt.unit_price
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
ORDER BY o.order_id, jt.sku;
~~~

Giải thích:

- o.document là tài liệu JSON của từng đơn hàng.
- '$.items[*]' chọn từng phần tử trong mảng items làm một hàng.
- '$.sku' đọc thuộc tính sku của phần tử hiện tại.
- '$.qty' đọc số lượng.
- '$.unitPrice' đọc đơn giá và chuyển thành DECIMAL(13,2).
- jt là bí danh của bảng do JSON_TABLE() trả về.

Kết quả:

| order_id | sku | qty | unit_price |
|---:|---|---:|---:|
| 1001 | KB-01 | 2 | 350000.00 |
| 1001 | MS-02 | 1 | 180000.00 |
| 1002 | HD-03 | 3 | 90000.00 |

Một hàng orders có thể tạo ra nhiều hàng jt. Khi nối bằng CROSS JOIN, số hàng kết quả là tổng số phần tử của các mảng items được chọn từ những đơn hàng nguồn.

### 4.1. Đường dẫn hàng và đường dẫn cột

Hai loại đường dẫn có vai trò khác nhau:

| Đường dẫn | Vai trò |
|---|---|
| '$.items[*]' | Chọn các node tạo thành hàng |
| '$.sku' | Lấy thuộc tính sku trong node đang tạo hàng |
| '$.qty' | Lấy thuộc tính qty trong node đang tạo hàng |
| '$.unitPrice' | Lấy thuộc tính unitPrice trong node đang tạo hàng |

Đường dẫn cột được đánh giá tương đối với node hiện tại mà row_path đã chọn. Vì vậy, nếu row_path đã là '$.items[*]', đường dẫn cột chỉ cần '$.sku', không cần lặp lại '$.items[*].sku'.

### 4.2. Mảng rỗng hoặc đường dẫn hàng không khớp

Nếu row_path không khớp node nào, JSON_TABLE() không tạo hàng nào cho tài liệu đó.

Với CROSS JOIN, đơn hàng không tạo được hàng JSON sẽ bị loại khỏi kết quả:

~~~sql
SELECT o.order_id, jt.sku
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
    )
) AS jt;
~~~

Đây là hành vi cần cân nhắc khi báo cáo cần giữ cả đơn hàng không có mặt hàng. Phần sau sẽ so sánh CROSS JOIN, LEFT JOIN và NESTED PATH.

## 5. FOR ORDINALITY: đánh số phần tử

FOR ORDINALITY tạo một cột số thứ tự cho các hàng được sinh ra từ row path. Số thứ tự bắt đầu từ 1.

~~~sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
ORDER BY o.order_id, jt.item_no;
~~~

Kết quả:

| order_id | item_no | sku | qty |
|---:|---:|---|---:|
| 1001 | 1 | KB-01 | 2 |
| 1001 | 2 | MS-02 | 1 |
| 1002 | 1 | HD-03 | 3 |

Ordinality phản ánh vị trí phần tử trong mảng của từng tài liệu, không phải số thứ tự toàn cục của toàn bộ kết quả query. Khi mỗi đơn hàng có mảng riêng, item_no có thể bắt đầu lại từ 1 ở đơn hàng tiếp theo.

### 5.1. Dùng ordinality để giữ thứ tự nghiệp vụ

JSON array có thứ tự. Nếu cần giữ thứ tự mặt hàng như tài liệu nguồn, hãy lấy FOR ORDINALITY và ORDER BY theo cột đó:

~~~sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku'
    )
) AS jt
ORDER BY o.order_id, jt.item_no;
~~~

Không dựa vào thứ tự vật lý của hàng hoặc thứ tự JSON_TABLE() tình cờ trả về nếu thứ tự có ý nghĩa với ứng dụng. SQL chỉ bảo đảm thứ tự kết quả khi có ORDER BY.

## 6. EXISTS PATH: kiểm tra thuộc tính có tồn tại

EXISTS PATH tạo một cột chỉ báo đường dẫn có khớp giá trị trong node hiện tại hay không. Kết quả là 1 nếu có và 0 nếu không.

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.has_note
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        has_note INT EXISTS PATH '$.note'
    )
) AS jt;
~~~

EXISTS PATH hữu ích khi cần phân biệt:

- Thuộc tính không có trong object.
- Thuộc tính có tồn tại nhưng giá trị của nó là JSON null.
- Thuộc tính có giá trị cụ thể.

Ví dụ, nếu một item có note: null, đường dẫn '$.note' vẫn tồn tại nên has_note là 1. Cột note được khai báo bằng PATH có thể nhận SQL NULL; cột EXISTS PATH cho biết node có hiện diện hay không.

### 6.1. Dùng EXISTS PATH trong điều kiện

Có thể lọc các phần tử có thuộc tính khuyến mãi:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.discount_code
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        has_discount INT EXISTS PATH '$.discount',
        discount_code VARCHAR(30) PATH '$.discount'
    )
) AS jt
WHERE jt.has_discount = 1;
~~~

EXISTS PATH chỉ trả về cờ tồn tại; nó không trả nội dung của thuộc tính. Nếu cần nội dung, khai báo thêm cột PATH như discount_code.

## 7. ON EMPTY: xử lý đường dẫn không tìm thấy giá trị

Một phần tử JSON có thể thiếu thuộc tính tùy chọn. Ví dụ một item có sku và qty nhưng không có note. ON EMPTY định nghĩa giá trị được gán khi đường dẫn của cột không tìm thấy kết quả.

Ba lựa chọn:

| Mệnh đề | Hành vi |
|---|---|
| NULL ON EMPTY | Gán SQL NULL |
| DEFAULT json_string ON EMPTY | Gán giá trị mặc định được viết dưới dạng JSON string |
| ERROR ON EMPTY | Phát sinh lỗi |

Ví dụ:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty,
    jt.note
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku' ERROR ON EMPTY,
        qty INT PATH '$.qty' DEFAULT '1' ON EMPTY,
        note VARCHAR(200) PATH '$.note'
            DEFAULT '"Không có ghi chú"' ON EMPTY
    )
) AS jt;
~~~

Trong ví dụ:

- Thiếu sku là lỗi vì sku được xem là bắt buộc.
- Thiếu qty thì dùng số 1.
- Thiếu note thì dùng chuỗi Không có ghi chú.

### 7.1. DEFAULT json_string là giá trị JSON

Đối số của DEFAULT được viết dưới dạng chuỗi biểu diễn JSON. Cần phân biệt chuỗi JSON với số JSON:

| DEFAULT | Giá trị JSON được biểu diễn |
|---|---|
| DEFAULT '0' | Số 0 |
| DEFAULT 'true' | Boolean true |
| DEFAULT 'null' | JSON null |
| DEFAULT '"unknown"' | Chuỗi unknown |
| DEFAULT '[]' | Mảng rỗng |
| DEFAULT '{}' | Object rỗng |

Vì vậy, để gán chuỗi unknown, cần đặt dấu quote JSON bên trong chuỗi SQL: DEFAULT '"unknown"'. Nếu viết DEFAULT 'unknown', nội dung không phải một JSON document hợp lệ.

Giá trị mặc định vẫn phải tương thích với kiểu SQL của cột đích. Sau khi nhận giá trị JSON mặc định, MySQL chuyển nó sang kiểu được khai báo trong COLUMNS.

### 7.2. ON EMPTY không có nghĩa là giá trị NULL

ON EMPTY chỉ áp dụng khi đường dẫn không tìm thấy giá trị. Nó không phải phép kiểm tra xem giá trị tìm được có phải JSON null hay không.

Nếu đường dẫn tồn tại và giá trị JSON là null:

- Từ MySQL 8.0.21, JSON_TABLE() ánh xạ JSON null thành SQL NULL.
- Đường dẫn vẫn được xem là đã tìm thấy; ON EMPTY không được kích hoạt.
- EXISTS PATH cho đường dẫn đó trả 1.

Nếu cần phân biệt thuộc tính thiếu với thuộc tính hiện diện có JSON null, kết hợp EXISTS PATH với cột PATH.

## 8. ON ERROR: xử lý lỗi khi ánh xạ giá trị

ON ERROR định nghĩa hành vi khi JSON_TABLE() gặp lỗi trong lúc đưa một giá trị JSON vào cột SQL. Các lựa chọn tương tự ON EMPTY:

| Mệnh đề | Hành vi |
|---|---|
| NULL ON ERROR | Gán SQL NULL |
| DEFAULT json_string ON ERROR | Gán giá trị mặc định |
| ERROR ON ERROR | Phát sinh lỗi |

Một trường hợp điển hình là đường dẫn trả về JSON object hoặc array nhưng cột đích được khai báo là kiểu scalar như VARCHAR, INT hoặc DECIMAL.

Ví dụ tài liệu có cấu trúc không đồng nhất:

~~~json
{
  "items": [
    {"sku": "KB-01", "qty": 2},
    {"sku": {"code": "MS-02"}, "qty": 1}
  ]
}
~~~

Nếu sku được ánh xạ vào VARCHAR, phần tử thứ hai là object thay vì scalar. Có thể quy định cách xử lý:

~~~sql
SELECT
    jt.sku,
    jt.qty
FROM JSON_TABLE(
    '{
      "items": [
        {"sku": "KB-01", "qty": 2},
        {"sku": {"code": "MS-02"}, "qty": 1}
      ]
    }',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
            NULL ON EMPTY
            DEFAULT '"INVALID_SKU"' ON ERROR,
        qty INT PATH '$.qty'
            DEFAULT '0' ON EMPTY
            ERROR ON ERROR
    )
) AS jt;
~~~

Đối với sku là object, ON ERROR gán chuỗi mặc định INVALID_SKU. Nếu qty không thể ánh xạ theo quy tắc lỗi của cột, ERROR ON ERROR yêu cầu câu truy vấn báo lỗi.

### 8.1. ON ERROR không thay thế kiểm tra kiểu dữ liệu

Không nên giả định ON ERROR bắt mọi vấn đề chuyển đổi. Trường hợp JSON object hoặc array được đưa vào cột scalar là ví dụ rõ ràng của lỗi JSON_TABLE xử lý theo ON ERROR. Một số vấn đề chuyển đổi SQL như cắt ngắn giá trị hoặc ép kiểu có thể tạo warning theo quy tắc chuyển đổi dữ liệu của MySQL.

Để bảo vệ dữ liệu:

- Khai báo kiểu cột đủ miền giá trị.
- Dùng ERROR ON ERROR cho trường bắt buộc phải đúng cấu trúc.
- Kiểm tra warning nếu ứng dụng cần phát hiện việc cắt ngắn hoặc chuyển đổi không mong muốn.
- Kiểm tra riêng JSON null, thuộc tính thiếu và giá trị sai kiểu.
- Không xem DEFAULT ON ERROR là cách sửa một tài liệu JSON có cấu trúc sai.

### 8.2. Viết ON EMPTY trước ON ERROR

Khi khai báo cả hai mệnh đề, viết theo thứ tự:

~~~sql
value_col VARCHAR(100) PATH '$.value'
    DEFAULT '"missing"' ON EMPTY
    ERROR ON ERROR
~~~

Từ MySQL 8.0.20, viết ON ERROR trước ON EMPTY bị deprecated. Dùng thứ tự ON EMPTY rồi ON ERROR để tránh cảnh báo và giữ cú pháp nhất quán.

## 9. NESTED PATH: bung mảng JSON lồng nhau

Một phần tử trong mảng có thể chứa một mảng con. Ví dụ một item có nhiều lựa chọn hoặc tùy chọn:

~~~json
{
  "items": [
    {
      "sku": "LAP-01",
      "qty": 1,
      "options": [
        {"code": "RAM-16", "price": 1200000},
        {"code": "SSD-1T", "price": 1800000}
      ]
    },
    {
      "sku": "MOUSE-01",
      "qty": 2,
      "options": []
    }
  ]
}
~~~

NESTED PATH mở rộng các phần tử của mảng con:

~~~sql
SELECT
    jt.item_no,
    jt.sku,
    jt.option_no,
    jt.option_code,
    jt.option_price
FROM JSON_TABLE(
    '{
      "items": [
        {
          "sku": "LAP-01",
          "qty": 1,
          "options": [
            {"code": "RAM-16", "price": 1200000},
            {"code": "SSD-1T", "price": 1800000}
          ]
        },
        {
          "sku": "MOUSE-01",
          "qty": 2,
          "options": []
        }
      ]
    }',
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        NESTED PATH '$.options[*]'
        COLUMNS (
            option_no FOR ORDINALITY,
            option_code VARCHAR(40) PATH '$.code',
            option_price DECIMAL(13, 2) PATH '$.price'
        )
    )
) AS jt
ORDER BY jt.item_no, jt.option_no;
~~~

Kết quả:

| item_no | sku | option_no | option_code | option_price |
|---:|---|---:|---|---:|
| 1 | LAP-01 | 1 | RAM-16 | 1200000.00 |
| 1 | LAP-01 | 2 | SSD-1T | 1800000.00 |
| 2 | MOUSE-01 | NULL | NULL | NULL |

Các cột ở cấp item được lặp lại cho mỗi hàng option. Item không có option vẫn tạo một hàng; các cột thuộc NESTED PATH nhận SQL NULL.

### 9.1. Phân biệt row path và nested path

Trong ví dụ:

- '$.items[*]' là row path chính, tạo hàng cho từng item.
- '$.options[*]' là nested path, tạo các hàng con của item hiện tại.
- sku và qty thuộc cấp item.
- option_code và option_price thuộc cấp option.

NESTED PATH có tính chất giữ hàng cha: khi đường dẫn mảng con không có kết quả, các cột con được đặt NULL và hàng cha vẫn được giữ.

Điều này khác với row path chính không khớp: nếu '$.items[*]' không tìm thấy phần tử nào thì JSON_TABLE() không tạo hàng cho tài liệu đó.

### 9.2. Nhiều NESTED PATH ngang hàng

Một item có thể chứa nhiều mảng con độc lập, chẳng hạn discounts và taxes:

~~~json
{
  "sku": "KB-01",
  "discounts": [
    {"code": "WELCOME", "amount": 20000}
  ],
  "taxes": [
    {"code": "VAT", "rate": 8},
    {"code": "ENV", "rate": 1}
  ]
}
~~~

Khi khai báo nhiều NESTED PATH cùng cấp, MySQL xử lý chúng tuần tự. Các hàng được sinh bởi một nested path có các cột thuộc nested path anh em đặt NULL; kết quả không phải tích Descartes giữa hai mảng.

Ví dụ:

~~~sql
SELECT *
FROM JSON_TABLE(
    '{
      "sku": "KB-01",
      "discounts": [
        {"code": "WELCOME", "amount": 20000}
      ],
      "taxes": [
        {"code": "VAT", "rate": 8},
        {"code": "ENV", "rate": 1}
      ]
    }',
    '$'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        NESTED PATH '$.discounts[*]'
        COLUMNS (
            discount_code VARCHAR(30) PATH '$.code',
            discount_amount DECIMAL(13, 2) PATH '$.amount'
        ),
        NESTED PATH '$.taxes[*]'
        COLUMNS (
            tax_code VARCHAR(30) PATH '$.code',
            tax_rate DECIMAL(5, 2) PATH '$.rate'
        )
    )
) AS jt;
~~~

Mảng discounts tạo hàng có discount_code và discount_amount; các cột tax tương ứng là NULL. Mảng taxes tạo các hàng có tax_code và tax_rate; các cột discount tương ứng là NULL. Nếu nghiệp vụ cần mọi cặp discount-tax, phải nối hoặc kết hợp hai tập kết quả một cách tường minh.

## 10. JSON_TABLE() và JOIN với bảng nguồn

JSON_TABLE() thường cần đọc tài liệu từ từng hàng của một bảng quan hệ. Hàm có thể tham chiếu cột của bảng đứng trước nó trong FROM. Đây là hành vi lateral ngầm định của JSON_TABLE().

Ví dụ:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE;
~~~

JSON_TABLE() được phép tham chiếu o.document vì orders đứng trước nó trong FROM. Không cần và không nên thêm từ khóa LATERAL trước JSON_TABLE(); tính lateral đã được ngầm định và việc viết LATERAL tường minh trước JSON_TABLE() gây lỗi cú pháp.

### 10.1. Kết hợp với bảng danh mục

Giả sử có bảng products:

~~~sql
CREATE TABLE products (
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (sku)
) ENGINE = InnoDB;
~~~

Có thể nối từng mặt hàng trong JSON với danh mục:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    p.product_name,
    jt.qty,
    jt.unit_price
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
JOIN products AS p
    ON p.sku = jt.sku
WHERE p.active = TRUE
ORDER BY o.order_id, jt.sku;
~~~

Sau khi bung thành hàng, sku là một cột SQL nên có thể dùng làm khóa nối với products. Nếu sku trong JSON không khớp bảng products, INNER JOIN sẽ loại mặt hàng đó; dùng LEFT JOIN nếu cần giữ cả mã chưa có trong danh mục.

### 10.2. Giữ đơn hàng không có mảng items

Nếu cần giữ cả đơn hàng có items rỗng hoặc không có đường dẫn items, dùng LEFT JOIN:

~~~sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku,
    jt.qty
FROM orders AS o
LEFT JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
ORDER BY o.order_id, jt.item_no;
~~~

Khi JSON_TABLE() không tạo hàng cho một đơn, LEFT JOIN vẫn giữ hàng orders và các cột jt nhận NULL.

Phân biệt hai trường hợp:

- Row path chính không khớp: JSON_TABLE() tạo 0 hàng; LEFT JOIN mới giữ hàng cha.
- Row path chính khớp một item nhưng nested path của item không khớp: NESTED PATH tự giữ hàng item và đặt các cột con thành NULL.

Đừng chuyển điều kiện trên cột jt vào WHERE một cách tùy tiện nếu muốn giữ hàng cha không có item. Ví dụ WHERE jt.qty > 0 loại hàng có jt.qty là NULL và làm kết quả gần giống INNER JOIN. Nếu điều kiện thuộc phép nối, cân nhắc đặt nó trong ON hoặc xử lý NULL theo đúng nghiệp vụ.

## 11. Truy vấn tổng hợp trên các hàng JSON_TABLE()

Khi mảng đã được bung thành hàng, có thể dùng aggregate như với bảng thông thường.

### 11.1. Tính tổng số lượng và giá trị từng đơn

~~~sql
SELECT
    o.order_id,
    SUM(jt.qty) AS total_quantity,
    SUM(jt.qty * jt.unit_price) AS order_amount
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Mỗi hàng đầu vào của SUM() là một mặt hàng. Biểu thức qty * unit_price tính giá trị dòng; GROUP BY order_id tổng hợp lại thành giá trị đơn hàng.

### 11.2. Thống kê theo SKU

~~~sql
SELECT
    jt.sku,
    SUM(jt.qty) AS units_sold,
    SUM(jt.qty * jt.unit_price) AS gross_amount
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
WHERE o.created_at >= '2026-02-01'
  AND o.created_at <  '2026-03-01'
GROUP BY jt.sku
ORDER BY gross_amount DESC;
~~~

Điều kiện thời gian lọc các đơn hàng nguồn trước khi tính báo cáo theo SKU. Dùng khoảng nửa mở từ đầu tháng đến đầu tháng sau giúp điều kiện thời gian rõ ràng và tránh bỏ sót các giá trị có phần thời gian trong ngày cuối tháng.

### 11.3. Lọc từng phần tử JSON

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE jt.qty >= 2
  AND jt.sku LIKE 'K%';
~~~

Điều kiện jt.qty và jt.sku áp dụng trên các hàng đã được ánh xạ. Nếu một tài liệu có hàng nghìn phần tử, việc bung dữ liệu vẫn có chi phí; hãy lọc bảng nguồn trước nếu có điều kiện chọn đơn hàng đủ chọn lọc.

### 11.4. Kết hợp với CTE

~~~sql
WITH order_items AS (
    SELECT
        o.order_id,
        o.customer_id,
        jt.sku,
        jt.qty,
        jt.unit_price
    FROM orders AS o
    CROSS JOIN JSON_TABLE(
        o.document,
        '$.items[*]'
        COLUMNS (
            sku VARCHAR(40) PATH '$.sku',
            qty INT PATH '$.qty',
            unit_price DECIMAL(13, 2) PATH '$.unitPrice'
        )
    ) AS jt
    WHERE o.created_at >= '2026-02-01'
      AND o.created_at <  '2026-03-01'
)
SELECT
    customer_id,
    SUM(qty * unit_price) AS customer_spend
FROM order_items
GROUP BY customer_id
ORDER BY customer_spend DESC;
~~~

CTE đặt tên cho tập hàng đã bung để câu truy vấn tổng hợp dễ đọc hơn. CTE không đồng nghĩa với việc dữ liệu chắc chắn được ghi ra bảng vật lý; optimizer quyết định cách thực thi theo cấu trúc truy vấn.

## 12. Đường dẫn JSON và ánh xạ kiểu dữ liệu

Đường dẫn JSON xác định node cần đọc. Một số dạng thường gặp:

| Đường dẫn | Ý nghĩa |
|---|---|
| '$' | Node gốc của tài liệu |
| '$.customerId' | Thuộc tính customerId ở cấp gốc |
| '$.items[0]' | Phần tử đầu tiên của mảng items |
| '$.items[*]' | Mọi phần tử trong mảng items |
| '$.items[*].sku' | Thuộc tính sku của các phần tử items |
| '$.profile.address.city' | Thuộc tính city trong object lồng nhau |

Tên key JSON phân biệt chữ hoa và chữ thường. '$.unitPrice' và '$.unitprice' có thể là hai đường dẫn khác nhau.

Nếu tên key chứa khoảng trắng hoặc ký tự đặc biệt, cần dùng cú pháp trích dẫn key của JSON path. Không tự ghép chuỗi đầu vào người dùng vào JSON path; hãy xác thực hoặc giới hạn đường dẫn được phép.

### 12.1. Chọn kiểu SQL cho cột

Kiểu SQL khai báo trong COLUMNS quyết định kiểu dữ liệu mà query nhận được:

| Dữ liệu JSON | Kiểu SQL thường dùng |
|---|---|
| Mã định danh dạng số nguyên | INT hoặc BIGINT |
| Số lượng | INT hoặc BIGINT |
| Giá, tỷ lệ chính xác | DECIMAL(p,s) |
| Mã hoặc tên | VARCHAR(n) |
| Ngày | DATE |
| Thời điểm không kèm múi giờ | DATETIME |
| Cờ số/boolean | TINYINT hoặc BOOLEAN |

Với dữ liệu tiền, dùng DECIMAL thay cho FLOAT/DOUBLE để tránh sai số dấu phẩy động. Chọn precision và scale đủ lớn cho giá trị thực tế.

Ví dụ:

~~~sql
SELECT
    jt.sku,
    jt.qty,
    jt.unit_price,
    jt.is_gift
FROM JSON_TABLE(
    '{
      "items": [
        {
          "sku": "BOOK-01",
          "qty": 2,
          "unitPrice": 125000.50,
          "isGift": false
        }
      ]
    }',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice',
        is_gift TINYINT PATH '$.isGift'
    )
) AS jt;
~~~

MySQL thực hiện chuyển đổi từ giá trị JSON sang kiểu SQL đã khai báo. Không nên coi việc ép kiểu thành công là bằng chứng dữ liệu đúng nghiệp vụ; ví dụ số lượng âm, giá bằng 0 hoặc chuỗi không phải mã hợp lệ vẫn cần quy tắc kiểm tra riêng.

### 12.2. Giá trị thiếu, JSON null và SQL NULL

Ba khái niệm cần phân biệt:

| Trạng thái trong JSON | Kết quả thường gặp ở cột PATH |
|---|---|
| Không có key hoặc path không khớp | Theo ON EMPTY |
| Key tồn tại với JSON null | SQL NULL từ MySQL 8.0.21 |
| Key tồn tại với scalar hợp lệ | Giá trị được chuyển sang kiểu SQL |

SQL NULL không cho biết nguyên nhân là key thiếu hay JSON null. Dùng EXISTS PATH nếu ứng dụng cần phân biệt sự hiện diện của key.

Ví dụ:

~~~sql
SELECT
    jt.has_note,
    jt.note
FROM JSON_TABLE(
    '{
      "items": [
        {"sku": "A-01"},
        {"sku": "A-02", "note": null},
        {"sku": "A-03", "note": "Fragile"}
      ]
    }',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(20) PATH '$.sku',
        has_note INT EXISTS PATH '$.note',
        note VARCHAR(100) PATH '$.note'
    )
) AS jt;
~~~

Kết quả phân biệt được item thiếu note với item có note là JSON null:

- Item A-01: has_note = 0, note = NULL.
- Item A-02: has_note = 1, note = NULL.
- Item A-03: has_note = 1, note = 'Fragile'.

## 13. JSON_TABLE() là table function có tính lateral

JSON_TABLE() thường đọc tài liệu từ cột của bảng xuất hiện trước nó trong FROM:

~~~sql
FROM orders AS o
CROSS JOIN JSON_TABLE(o.document, '$.items[*]' COLUMNS (...)) AS jt
~~~

Table function có thể tham chiếu o.document mà không cần viết LATERAL. Phạm vi tham chiếu phụ thuộc thứ tự trong FROM: biểu thức JSON_TABLE() có thể dùng bảng đứng trước nó, không dùng bảng xuất hiện sau nó.

Điều này giúp bung JSON riêng cho từng hàng của bảng nguồn. Nếu JSON_TABLE() chỉ đọc một literal JSON hoặc một biểu thức độc lập, không cần bảng nguồn đứng trước.

Không nhầm JSON_TABLE() với derived table thông thường. Quy tắc lateral của JSON_TABLE() là hành vi riêng của table function; việc thêm từ khóa LATERAL tường minh trước nó là không hợp lệ.

## 14. Hiệu năng và chiến lược truy vấn

JSON_TABLE() giúp SQL dễ đọc và khai thác dữ liệu JSON theo dạng quan hệ, nhưng việc mở rộng mảng có thể làm tăng số hàng trung gian đáng kể.

Ví dụ 100.000 đơn hàng, mỗi đơn trung bình có 20 mặt hàng có thể tạo khoảng 2 triệu hàng JSON_TABLE() trước khi tổng hợp. Cần xem xét số tài liệu được đọc, kích thước mảng và số cột được trích xuất.

### 14.1. Lọc bảng nguồn trước khi bung JSON

Đặt các điều kiện chọn lọc trên bảng quan hệ vào cùng truy vấn:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE o.customer_id = 501
  AND o.created_at >= '2026-02-01'
  AND o.created_at <  '2026-03-01';
~~~

Index trên customer_id và created_at có thể giúp tìm các đơn phù hợp trước khi xử lý tài liệu JSON. Thứ tự thực thi thực tế do optimizer quyết định; hãy xác nhận bằng EXPLAIN thay vì giả định chỉ vì điều kiện được viết trước hay sau JOIN.

### 14.2. Chỉ chiếu các cột cần thiết

Không khai báo hàng chục cột JSON nếu query chỉ cần sku và qty. Mỗi cột bổ sung làm tăng công việc trích xuất và chuyển đổi.

Tương tự, tránh bung các mảng con lớn nếu truy vấn chỉ cần kiểm tra một điều kiện tồn tại. Các hàm như JSON_CONTAINS(), JSON_OVERLAPS() hoặc MEMBER OF() có thể phù hợp hơn tùy cấu trúc và loại điều kiện.

### 14.3. Dùng generated column hoặc index khi truy vấn scalar lặp lại

Nếu thường xuyên lọc theo một thuộc tính scalar ở cấp gốc, cân nhắc generated column và index:

~~~sql
ALTER TABLE orders
ADD COLUMN document_customer_id BIGINT
    GENERATED ALWAYS AS (
        CAST(
            JSON_UNQUOTE(
                JSON_EXTRACT(document, '$.customerId')
            ) AS UNSIGNED
        )
    ) STORED,
ADD INDEX idx_orders_document_customer (document_customer_id);
~~~

Sau đó có thể lọc bằng cột đã index:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE document_customer_id = 501;
~~~

Ví dụ này chỉ phù hợp khi customerId có định dạng số hợp lệ và quy tắc dữ liệu được bảo đảm. Cần xử lý tài liệu thiếu key, JSON null và giá trị sai kiểu theo hợp đồng dữ liệu của hệ thống.

Generated column giúp tăng tốc truy vấn một thuộc tính scalar được dùng lặp lại. Nó không tự biến toàn bộ mảng items thành bảng quan hệ.

### 14.4. Multi-valued index không thay thế JSON_TABLE()

MySQL hỗ trợ multi-valued index cho một số điều kiện tìm kiếm phần tử trong JSON array, ví dụ MEMBER OF(), JSON_CONTAINS() và JSON_OVERLAPS() trong các điều kiện được hỗ trợ.

Multi-valued index phục vụ tìm kiếm thành viên của mảng. Nó không thay thế việc bung từng phần tử thành các cột SQL để JOIN, tính toán hoặc trả nhiều hàng bằng JSON_TABLE(). Kiểm tra EXPLAIN để biết index có được dùng cho predicate cụ thể hay không.

### 14.5. Đọc kế hoạch thực thi

Sử dụng EXPLAIN để xem kế hoạch:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE o.customer_id = 501;
~~~

Nếu phiên bản MySQL hỗ trợ EXPLAIN ANALYZE, có thể đo số hàng và thời gian thực tế:

~~~sql
EXPLAIN ANALYZE
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE o.customer_id = 501;
~~~

Tập trung quan sát:

- Số hàng orders được đọc.
- Index có được dùng để lọc bảng nguồn hay không.
- Số hàng JSON_TABLE() tạo ra.
- Số hàng bị loại bởi điều kiện sau khi bung JSON.
- Chi phí sort, aggregate và join tiếp theo.
- Ước lượng của optimizer có lệch nhiều so với số hàng thực tế hay không.

### 14.6. Khi nào nên chuẩn hóa mảng thành bảng quan hệ?

Nếu một mảng JSON được truy vấn, cập nhật, join và ràng buộc thường xuyên như dữ liệu cốt lõi, cân nhắc lưu mỗi phần tử thành một hàng trong bảng con.

| Đặc điểm | Lưu mảng trong JSON | Lưu bảng con |
|---|---|---|
| Schema linh hoạt | Tốt | Cần thiết kế cột |
| Đọc toàn bộ tài liệu | Thuận tiện | Cần JOIN hoặc truy vấn nhiều hàng |
| JOIN từng phần tử thường xuyên | Có chi phí bung JSON | Tự nhiên hơn |
| Foreign key cho từng phần tử | Không trực tiếp | Hỗ trợ |
| Index từng thuộc tính phần tử | Hạn chế hơn | Linh hoạt |
| Cập nhật một phần tử | Cần cập nhật tài liệu JSON | UPDATE một hàng |

JSON_TABLE() là cầu nối hữu ích giữa tài liệu JSON và truy vấn quan hệ. Nó không có nghĩa mọi danh sách quan hệ đều nên được lưu lâu dài trong JSON.

## 15. Các lỗi thường gặp khi dùng JSON_TABLE()

### 15.1. Nhầm row path với column path

Khi row path đã chọn từng phần tử của mảng, đường dẫn cột phải được viết tương đối với phần tử hiện tại.

~~~sql
JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
    )
)
~~~

Không lặp lại toàn bộ đường dẫn từ gốc trong mỗi column path. Hãy xác định row path trước, sau đó mới chọn các thuộc tính của node hiện tại.

### 15.2. Quên alias của JSON_TABLE()

JSON_TABLE() phải có table alias:

~~~sql
SELECT jt.sku
FROM JSON_TABLE(
    '{"items":[{"sku":"KB-01"}]}',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
    )
) AS jt;
~~~

Alias giúp tham chiếu cột rõ ràng và tránh trùng tên với cột của bảng khác.

### 15.3. Dùng CROSS JOIN nhưng mong giữ hàng cha

CROSS JOIN loại đơn hàng nếu row path chính không tạo hàng. Nếu báo cáo cần giữ đơn hàng không có items, dùng LEFT JOIN JSON_TABLE() ... ON TRUE hoặc thiết kế truy vấn phù hợp.

Không nhầm điều này với NESTED PATH: nested path không khớp vẫn giữ hàng được tạo bởi row path chính và đặt các cột con thành NULL.

### 15.4. Dùng ON EMPTY để xử lý JSON null

ON EMPTY chỉ áp dụng khi path không tìm thấy. Nếu thuộc tính tồn tại với JSON null, từ MySQL 8.0.21 cột PATH nhận SQL NULL mà không chạy ON EMPTY.

Nếu cần phân biệt hai trạng thái, dùng EXISTS PATH.

### 15.5. Cho rằng ON ERROR bắt mọi lỗi chuyển đổi

ON ERROR không phải bộ xác thực toàn diện cho dữ liệu JSON. Một JSON object/array không thể đưa trực tiếp vào cột scalar là tình huống điển hình; các vấn đề chuyển đổi SQL khác có thể tạo warning hoặc tuân theo quy tắc ép kiểu.

Khai báo kiểu dữ liệu đúng, kiểm tra warning khi cần và xác thực quy tắc nghiệp vụ ở tầng phù hợp.

### 15.6. Quên thứ tự ON EMPTY và ON ERROR

Khi cần cả hai, dùng ON EMPTY trước ON ERROR:

~~~sql
amount DECIMAL(13, 2) PATH '$.amount'
    DEFAULT '0' ON EMPTY
    ERROR ON ERROR
~~~

Không dùng thứ tự ngược vì cú pháp ON ERROR trước ON EMPTY đã bị deprecated từ MySQL 8.0.20.

### 15.7. Dùng INNER JOIN khi cần giữ mã không khớp

Khi nối cột JSON_TABLE() với bảng danh mục:

- INNER JOIN chỉ giữ các mã có trong bảng danh mục.
- LEFT JOIN giữ cả các mã chưa có bản ghi tương ứng.

Chọn theo yêu cầu báo cáo. Nếu cần tìm dữ liệu tham chiếu bị thiếu, LEFT JOIN và kiểm tra khóa bên bảng phải là NULL.

### 15.8. Không kiểm tra dữ liệu JSON đầu vào

Cột JSON của MySQL chỉ nhận tài liệu JSON hợp lệ. Tuy nhiên, JSON_TABLE() cũng có thể nhận biểu thức chuỗi hoặc biểu thức khác tạo ra JSON. Nếu biểu thức không phải tài liệu JSON hợp lệ, câu truy vấn có thể thất bại.

Với payload thô trước khi chuyển vào cột JSON, có thể kiểm tra bằng JSON_VALID():

~~~sql
SELECT
    raw_payload,
    JSON_VALID(raw_payload) AS is_valid_json
FROM incoming_messages;
~~~

Không gọi JSON_TABLE() trên payload chưa được xác thực nếu ứng dụng không có cơ chế xử lý lỗi phù hợp. Tốt nhất là kiểm tra và chuẩn hóa dữ liệu ở ranh giới ingest trước khi đưa vào luồng truy vấn.

### 15.9. Giả định thứ tự kết quả tự động được bảo đảm

JSON array có thứ tự phần tử, nhưng result set SQL không được bảo đảm thứ tự nếu không có ORDER BY. Dùng FOR ORDINALITY để lấy vị trí rồi ORDER BY theo khóa cha và ordinality.

## 16. Ví dụ thực tế: báo cáo doanh thu từ JSON

Giả sử document chứa các mặt hàng, mỗi mặt hàng có sku, qty, unitPrice và có thể có discount. Cần tính doanh thu trước giảm giá theo khách hàng.

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS line_count,
    SUM(jt.qty) AS total_units,
    SUM(jt.qty * jt.unit_price) AS gross_amount
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku' ERROR ON EMPTY,
        qty INT PATH '$.qty'
            DEFAULT '1' ON EMPTY
            ERROR ON ERROR,
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
            ERROR ON EMPTY
            ERROR ON ERROR,
        has_discount INT EXISTS PATH '$.discount'
    )
) AS jt
WHERE o.created_at >= '2026-02-01'
  AND o.created_at <  '2026-03-01'
  AND jt.qty > 0
GROUP BY o.customer_id
ORDER BY gross_amount DESC;
~~~

Quy tắc trong ví dụ:

- Mỗi phần tử items tạo một dòng.
- sku và unitPrice là bắt buộc; thiếu chúng thì truy vấn báo lỗi.
- qty mặc định bằng 1 nếu không có.
- has_discount cho biết thuộc tính discount có tồn tại.
- Chỉ tính số lượng dương.
- Kết quả được nhóm theo khách hàng.

Nếu dữ liệu có thể chứa giá trị sai kiểu, hãy quyết định rõ có muốn truy vấn dừng khi gặp lỗi hay muốn cách ly tài liệu lỗi trước khi chạy báo cáo.

### 16.1. Tách dữ liệu lỗi khỏi dữ liệu hợp lệ

Trong pipeline ingest, nên có bước kiểm tra cấu trúc trước khi chạy truy vấn phân tích:

1. Xác nhận payload là JSON hợp lệ.
2. Kiểm tra node gốc và kiểu của items.
3. Kiểm tra các thuộc tính bắt buộc như sku, qty, unitPrice.
4. Kiểm tra miền giá trị và quy tắc nghiệp vụ.
5. Đưa payload hợp lệ vào luồng xử lý chính.
6. Ghi nhận payload không hợp lệ cùng lý do để xử lý lại hoặc điều tra.

JSON_TABLE() hỗ trợ ánh xạ và phát hiện một số tình huống không phù hợp khi chuyển giá trị sang cột SQL. Nó không thay thế toàn bộ schema validation hoặc quy tắc nghiệp vụ.

## 17. Hướng dẫn chọn cấu trúc truy vấn

| Nhu cầu | Cách dùng |
|---|---|
| Một scalar trong tài liệu | JSON_VALUE() hoặc JSON_EXTRACT() |
| Một hàng cho mỗi phần tử mảng | JSON_TABLE() với row path '$.array[*]' |
| Giữ vị trí phần tử | FOR ORDINALITY |
| Kiểm tra thuộc tính có hiện diện | EXISTS PATH |
| Đặt mặc định khi key thiếu | DEFAULT ... ON EMPTY |
| Báo lỗi khi key bắt buộc thiếu | ERROR ON EMPTY |
| Xử lý object/array không phù hợp cột scalar | ON ERROR |
| Bung mảng con | NESTED PATH |
| Giữ bảng nguồn khi mảng gốc rỗng | LEFT JOIN JSON_TABLE() ... ON TRUE |
| Tổng hợp các phần tử | Aggregate trên cột JSON_TABLE() |
| Lọc thường xuyên theo scalar ở gốc JSON | Generated column hoặc functional index phù hợp |
| Join và cập nhật từng phần tử thường xuyên | Cân nhắc chuẩn hóa thành bảng con |

## 18. Bài thực hành

### 18.1. Lấy từng mặt hàng và vị trí trong đơn

Viết truy vấn trả về order_id, vị trí item, sku và qty. Sắp xếp theo order_id và vị trí item.

Gợi ý:

- Row path: '$.items[*]'.
- Dùng FOR ORDINALITY.
- Dùng ORDER BY trên khóa đơn và ordinality.

### 18.2. Lọc mặt hàng có discount

Thêm cột EXISTS PATH cho đường dẫn '$.discount'. Chỉ trả về các mặt hàng có thuộc tính discount, kể cả khi giá trị của thuộc tính là JSON null.

### 18.3. Xử lý thuộc tính không bắt buộc

Tạo cột note VARCHAR(200), đặt chuỗi mặc định khi path không tồn tại. Thử ba tài liệu:

- Item không có note.
- Item có note là JSON null.
- Item có note là chuỗi thông thường.

Quan sát sự khác nhau giữa ON EMPTY và EXISTS PATH.

### 18.4. Bung mảng lồng nhau

Tạo tài liệu có items và options. Dùng NESTED PATH để trả một hàng cho mỗi option và giữ item không có options với các cột option là NULL.

### 18.5. Tổng hợp theo khách hàng

Dùng JSON_TABLE() để tính tổng qty và tổng qty * unitPrice theo customer_id trong một khoảng thời gian. Dùng EXPLAIN để kiểm tra điều kiện lọc orders.

### 18.6. Câu hỏi tự kiểm tra

1. JSON_TABLE() khác JSON_EXTRACT() ở kiểu kết quả như thế nào?
2. Row path quyết định điều gì?
3. FOR ORDINALITY bắt đầu từ số mấy?
4. EXISTS PATH trả gì khi thuộc tính tồn tại với JSON null?
5. ON EMPTY khác ON ERROR như thế nào?
6. Vì sao DEFAULT '"unknown"' khác DEFAULT 'unknown'?
7. NESTED PATH xử lý ra sao khi mảng con rỗng?
8. Nhiều NESTED PATH ngang hàng có tạo tích Descartes không?
9. Vì sao CROSS JOIN có thể làm mất đơn hàng không có item?
10. Khi nào cần LEFT JOIN JSON_TABLE()?
11. Vì sao JSON_TABLE() có thể tham chiếu bảng đứng trước mà không cần LATERAL?
12. Khi nào nên chuẩn hóa mảng JSON thành bảng quan hệ?

## 19. Checklist trước khi đưa truy vấn vào ứng dụng

- [ ] Phiên bản MySQL hỗ trợ JSON_TABLE() và hành vi tương thích với ứng dụng.
- [ ] JSON expression là tài liệu hợp lệ.
- [ ] Row path trỏ đúng node tạo hàng.
- [ ] Các column path được viết tương đối với node hiện tại.
- [ ] Mỗi cột có kiểu SQL phù hợp và đủ miền giá trị.
- [ ] FOR ORDINALITY được dùng nếu cần giữ vị trí phần tử.
- [ ] EXISTS PATH được dùng khi cần phân biệt key thiếu với key hiện diện có JSON null.
- [ ] ON EMPTY được chọn theo hợp đồng của thuộc tính tùy chọn hoặc bắt buộc.
- [ ] ON ERROR không bị xem là cơ chế bắt mọi warning chuyển đổi.
- [ ] ON EMPTY được viết trước ON ERROR.
- [ ] NESTED PATH giữ đúng hàng cha khi mảng con rỗng.
- [ ] Sibling NESTED PATH được hiểu là các nhánh tuần tự, không phải tích Descartes.
- [ ] CROSS JOIN hay LEFT JOIN phù hợp với yêu cầu giữ hàng nguồn.
- [ ] Điều kiện trên cột JSON_TABLE() không vô tình loại hàng cha cần giữ.
- [ ] Truy vấn chỉ trích xuất các cột cần dùng.
- [ ] EXPLAIN hoặc EXPLAIN ANALYZE đã được xem khi dữ liệu lớn.
- [ ] Đã đánh giá số hàng sau khi bung mảng.
- [ ] Các thuộc tính scalar được lọc thường xuyên đã được xem xét cho generated column/index.
- [ ] Đã cân nhắc bảng con quan hệ nếu cần join, constraint hoặc cập nhật từng phần tử thường xuyên.

## Kết luận

JSON_TABLE() chuyển các node trong tài liệu JSON thành hàng và cột SQL để truy vấn theo cách quan hệ. Row path quyết định hàng được tạo; COLUMNS ánh xạ giá trị; FOR ORDINALITY giữ vị trí; EXISTS PATH kiểm tra sự hiện diện; ON EMPTY và ON ERROR xác định cách xử lý dữ liệu thiếu hoặc không thể ánh xạ; NESTED PATH mở rộng mảng con.

Khi dùng JSON_TABLE(), hãy xác định rõ cardinality sau khi bung mảng, chọn CROSS JOIN hay LEFT JOIN theo yêu cầu giữ hàng cha, và phân biệt key thiếu với JSON null. Với dữ liệu lớn, lọc bảng nguồn, chiếu đúng cột, đọc kế hoạch thực thi và cân nhắc chuẩn hóa nếu từng phần tử JSON đã trở thành thực thể quan hệ được truy vấn thường xuyên.
