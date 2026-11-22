# JSON_TABLE và chuyển cấu trúc JSON thành bảng quan hệ

JSON thường biểu diễn dữ liệu dưới dạng object, array và scalar. Trong khi đó, SQL làm việc với hàng, cột và kiểu dữ liệu quan hệ. Oracle cung cấp hàm SQL/JSON JSON_TABLE để ánh xạ một tài liệu JSON thành một tập hàng và cột ảo, từ đó có thể SELECT, JOIN, GROUP BY, lọc và chuyển dữ liệu vào bảng quan hệ.

JSON_TABLE đặc biệt hữu ích khi:

- Một cột BLOB/CLOB/VARCHAR2 chứa tài liệu JSON.
- JSON có một mảng phần tử cần biến thành nhiều hàng.
- Mỗi phần tử có object con hoặc array lồng nhau.
- Cần kết hợp dữ liệu JSON với bảng khách hàng, sản phẩm, đơn hàng hoặc danh mục.
- Cần nạp dữ liệu JSON vào các bảng quan hệ bằng INSERT ... SELECT hoặc MERGE.

Ý tưởng cốt lõi: **row path xác định mỗi hàng JSON được sinh ra từ đâu; COLUMNS và column path xác định giá trị nào trở thành cột SQL.** Sau khi JSON_TABLE tạo bảng ảo, SQL xử lý nó như một row source bình thường.

## 1. Từ JSON document đến quan hệ

Ví dụ tài liệu JSON:

~~~json
{
  "orderId": 7001,
  "customerId": 101,
  "status": "NEW",
  "items": [
    {"productId": 501, "sku": "KB-01", "quantity": 2, "unitPrice": 125000},
    {"productId": 502, "sku": "MS-02", "quantity": 1, "unitPrice": 250000}
  ]
}
~~~

JSON có một object đơn chứa thông tin đơn hàng và một array items có hai object. Nếu cần phân tích từng mặt hàng, kết quả quan hệ mong muốn có thể là:

| ORDER_ID | CUSTOMER_ID | STATUS | PRODUCT_ID | SKU | QUANTITY | UNIT_PRICE |
|---:|---:|---|---:|---|---:|---:|
| 7001 | 101 | NEW | 501 | KB-01 | 2 | 125000 |
| 7001 | 101 | NEW | 502 | MS-02 | 1 | 250000 |

Các giá trị orderId, customerId và status được lặp lại trên mỗi dòng item. Đây là phép flatten array: một object cha được kết hợp với từng phần tử trong array con.

JSON_TABLE tạo ra row source ảo để SQL đọc. Nó không tự động tạo table vật lý hoặc ghi dữ liệu vào database.

## 2. Cú pháp cơ bản của JSON_TABLE

Cú pháp khái quát:

~~~sql
JSON_TABLE(
    json_expression,
    row_path_expression
    COLUMNS (
        column_definition,
        ...
    )
    error_handling_clause
)
~~~

Trong đó:

- json_expression: cột, biến hoặc biểu thức chứa JSON.
- row_path_expression: JSON path xác định các node sinh hàng.
- COLUMNS: khai báo các cột SQL cần trích xuất.
- column_definition: tên cột, kiểu dữ liệu, path và cách xử lý lỗi/giá trị thiếu.
- error_handling_clause: cách xử lý lỗi ở cấp JSON_TABLE nếu được chỉ định.

Ví dụ JSON_TABLE cho object đơn:

~~~sql
SELECT jt.order_id,
       jt.customer_id,
       jt.status
FROM JSON_TABLE(
    '{
       "orderId": 7001,
       "customerId": 101,
       "status": "NEW"
     }',
    '$'
    COLUMNS (
        order_id    NUMBER        PATH '$.orderId',
        customer_id NUMBER        PATH '$.customerId',
        status      VARCHAR2(20)  PATH '$.status'
    )
) jt;
~~~

Kết quả là một hàng:

| ORDER_ID | CUSTOMER_ID | STATUS |
|---:|---:|---|
| 7001 | 101 | NEW |

Path '$' chọn root object. Mỗi column path được đánh giá tương đối với node hiện tại mà row path đã chọn.

## 3. JSON_TABLE hoạt động theo hai lớp path

JSON_TABLE có hai lớp path cần phân biệt:

1. Row path: chọn các JSON node để tạo hàng.
2. Column path: lấy trường trong node của hàng hiện tại để tạo cột.

Ví dụ:

~~~sql
SELECT jt.product_id,
       jt.quantity
FROM JSON_TABLE(
    '{
       "items": [
         {"productId": 501, "quantity": 2},
         {"productId": 502, "quantity": 1}
       ]
     }',
    '$.items[*]'
    COLUMNS (
        product_id NUMBER PATH '$.productId',
        quantity   NUMBER PATH '$.quantity'
    )
) jt;
~~~

Row path $.items[*] chọn từng phần tử trong array items, vì vậy JSON_TABLE tạo hai hàng. Column path $.productId và $.quantity đọc field từ mỗi phần tử đang xét.

Nếu dùng row path '$' thay vì '$.items[*]', JSON_TABLE chỉ tạo một hàng cho root object. Khi đó column path phải truy cập tới cấu trúc items theo cách phù hợp, hoặc dùng NESTED PATH để bung mảng.

### 3.1 Path '$'

'$' biểu diễn root của tài liệu JSON.

Ví dụ:

~~~sql
JSON_TABLE(
    payload,
    '$'
    COLUMNS (
        document_id NUMBER PATH '$.id'
    )
)
~~~

### 3.2 Path '$.field'

Truy cập một thuộc tính của object:

~~~text
$.customerId
$.address.city
$.metadata.createdBy
~~~

Ví dụ $.address.city đi từ root tới object address rồi lấy field city.

### 3.3 Path '$.array[*]'

Chọn mọi phần tử của array:

~~~text
$.items[*]
$.orders[*]
$.events[*]
~~~

Nếu array có N phần tử phù hợp, row path thường tạo N hàng.

### 3.4 Path index cụ thể

Có thể chọn phần tử theo chỉ số mảng:

~~~text
$.items[0]
$.items[1]
~~~

JSON array index bắt đầu từ 0. Điều này khác với FOR ORDINALITY của JSON_TABLE, vốn đánh số hàng bắt đầu từ 1.

### 3.5 Wildcard và path phức tạp

JSON path hỗ trợ các biểu thức chọn node phong phú hơn, tùy phiên bản Oracle và SQL/JSON path syntax. Khi viết API ổn định, ưu tiên path rõ ràng, tránh biểu thức quá phức tạp khó kiểm soát kiểu và cardinality.

## 4. Khai báo cột SQL trong COLUMNS

Mỗi cột có thể khai báo tên, kiểu dữ liệu và JSON path:

~~~sql
COLUMNS (
    order_id    NUMBER         PATH '$.orderId',
    customer_id NUMBER         PATH '$.customerId',
    status      VARCHAR2(20)   PATH '$.status',
    created_at  TIMESTAMP      PATH '$.createdAt'
)
~~~

Nên khai báo kiểu dữ liệu SQL tường minh để kết quả có schema rõ ràng.

### 4.1 NUMBER

Dùng NUMBER cho dữ liệu số:

~~~sql
quantity NUMBER PATH '$.quantity'
~~~

Nếu JSON chứa chuỗi "2" thay vì số 2, Oracle có thể chuyển đổi theo quy tắc kiểu đích và error handling. Không nên dựa vào conversion ngầm nếu định dạng JSON không thống nhất.

### 4.2 VARCHAR2

Dùng VARCHAR2 cho chuỗi có giới hạn:

~~~sql
sku VARCHAR2(40 CHAR) PATH '$.sku'
~~~

Xác định độ dài theo character semantics nếu dữ liệu có Unicode. Nếu chuỗi vượt giới hạn cột, kết quả phụ thuộc error handling và có thể phát sinh lỗi chuyển đổi/kích thước.

### 4.3 DATE và TIMESTAMP

JSON thường biểu diễn thời gian dưới dạng string, ví dụ ISO 8601:

~~~json
{"createdAt": "2026-11-14T09:30:00"}
~~~

Khi chuyển sang DATE/TIMESTAMP, phải xác định format và quy tắc timezone. JSON_TABLE column projection có thể chuyển đổi theo kiểu SQL, nhưng với format không chuẩn hoặc timezone quan trọng, nên trích xuất chuỗi rồi chuyển đổi tường minh bằng TO_TIMESTAMP/TO_TIMESTAMP_TZ theo format mask phù hợp.

Ví dụ trích chuỗi:

~~~sql
SELECT jt.created_at_text
FROM JSON_TABLE(
    '{"createdAt":"2026-11-14T09:30:00"}',
    '$'
    COLUMNS (
        created_at_text VARCHAR2(40) PATH '$.createdAt'
    )
) jt;
~~~

Sau đó chuyển đổi:

~~~sql
TO_TIMESTAMP(
    jt.created_at_text,
    'YYYY-MM-DD"T"HH24:MI:SS'
)
~~~

Không bỏ qua timezone nếu chuỗi đầu vào có offset hoặc vùng thời gian. Dùng TIMESTAMP WITH TIME ZONE và TO_TIMESTAMP_TZ khi cần giữ ngữ nghĩa thời điểm đa múi giờ.

### 4.4 Cột không chỉ định PATH

Có thể khai báo path mặc định theo tên cột trong một số dạng cú pháp, nhưng cách này dễ gây nhầm lẫn khi tên cột SQL khác tên field JSON hoặc cần phân biệt chữ hoa/thường. Trong tài liệu và code production, khai báo PATH tường minh giúp schema dễ đọc và ít bất ngờ.

## 5. FOR ORDINALITY: tạo số thứ tự cho hàng

FOR ORDINALITY tạo một cột số thứ tự cho mỗi hàng được sinh ra từ row path:

~~~sql
SELECT jt.item_no,
       jt.product_id,
       jt.quantity
FROM JSON_TABLE(
    '{
       "items": [
         {"productId": 501, "quantity": 2},
         {"productId": 502, "quantity": 1},
         {"productId": 503, "quantity": 4}
       ]
     }',
    '$.items[*]'
    COLUMNS (
        item_no    FOR ORDINALITY,
        product_id NUMBER PATH '$.productId',
        quantity   NUMBER PATH '$.quantity'
    )
) jt
ORDER BY jt.item_no;
~~~

Kết quả:

| ITEM_NO | PRODUCT_ID | QUANTITY |
|---:|---:|---:|
| 1 | 501 | 2 |
| 2 | 502 | 1 |
| 3 | 503 | 4 |

FOR ORDINALITY hữu ích khi:

- Cần giữ vị trí phần tử trong JSON array.
- Cần sắp xếp kết quả theo thứ tự ban đầu.
- Cần ghi số thứ tự vào bảng quan hệ.
- Cần đối chiếu lỗi với phần tử nguồn.

Số thứ tự bắt đầu từ 1 cho row source tương ứng. JSON array index trong path bắt đầu từ 0, nên không nhầm hai quy ước này.

## 6. NESTED PATH: bung array lồng nhau

JSON thực tế thường có object cha và các array con. NESTED PATH cho phép khai báo cột cho phần tử con ngay trong COLUMNS.

Ví dụ:

~~~json
{
  "orderId": 7001,
  "customerId": 101,
  "status": "NEW",
  "items": [
    {"productId": 501, "sku": "KB-01", "quantity": 2},
    {"productId": 502, "sku": "MS-02", "quantity": 1}
  ]
}
~~~

Truy vấn:

~~~sql
SELECT jt.order_id,
       jt.customer_id,
       jt.status,
       jt.item_no,
       jt.product_id,
       jt.sku,
       jt.quantity
FROM JSON_TABLE(
    '{
       "orderId": 7001,
       "customerId": 101,
       "status": "NEW",
       "items": [
         {"productId": 501, "sku": "KB-01", "quantity": 2},
         {"productId": 502, "sku": "MS-02", "quantity": 1}
       ]
     }',
    '$'
    COLUMNS (
        order_id    NUMBER        PATH '$.orderId',
        customer_id NUMBER        PATH '$.customerId',
        status      VARCHAR2(20)  PATH '$.status',
        NESTED PATH '$.items[*]'
        COLUMNS (
            item_no    FOR ORDINALITY,
            product_id NUMBER        PATH '$.productId',
            sku        VARCHAR2(40)  PATH '$.sku',
            quantity   NUMBER        PATH '$.quantity'
        )
    )
) jt
ORDER BY jt.item_no;
~~~

Các cột cha được lặp lại cho từng hàng con. Kết quả là một hàng cho mỗi item.

### 6.1 Quan hệ cha-con trong JSON_TABLE

JSON_TABLE tổ chức nested columns thành quan hệ cha-con:

- Row path ở ngoài tạo hàng cha.
- NESTED PATH tạo các hàng con theo path tương đối với node cha.
- Cột cha được ghép với hàng con.
- Nested path không khớp vẫn có thể giữ hàng cha với các cột con NULL theo ngữ nghĩa outer join của quan hệ cha-con.

Điểm này khác với việc chọn trực tiếp row path '$.items[*]' rồi cross join JSON_TABLE, nơi không có item phù hợp thì row source không tạo hàng cho document đó.

### 6.2 Nhiều cấp NESTED PATH

JSON có thể lồng nhiều cấp:

~~~json
{
  "orderId": 7001,
  "items": [
    {
      "productId": 501,
      "options": [
        {"name": "color", "value": "black"},
        {"name": "layout", "value": "US"}
      ]
    }
  ]
}
~~~

Truy vấn:

~~~sql
SELECT jt.order_id,
       jt.product_id,
       jt.option_no,
       jt.option_name,
       jt.option_value
FROM JSON_TABLE(
    '{
       "orderId": 7001,
       "items": [
         {
           "productId": 501,
           "options": [
             {"name": "color", "value": "black"},
             {"name": "layout", "value": "US"}
           ]
         }
       ]
     }',
    '$'
    COLUMNS (
        order_id NUMBER PATH '$.orderId',
        NESTED PATH '$.items[*]'
        COLUMNS (
            product_id NUMBER PATH '$.productId',
            NESTED PATH '$.options[*]'
            COLUMNS (
                option_no    FOR ORDINALITY,
                option_name  VARCHAR2(40) PATH '$.name',
                option_value VARCHAR2(100) PATH '$.value'
            )
        )
    )
) jt
ORDER BY jt.option_no;
~~~

Các cột ở cấp sâu nhất mô tả từng option. Cột order_id và product_id được đưa xuống các hàng con tương ứng.

### 6.3 Nhiều NESTED PATH cùng cấp không phải Cartesian product

Một điểm dễ nhầm: các sibling NESTED PATH ở cùng cấp trong một COLUMNS clause được kết hợp theo ngữ nghĩa union join của Oracle, không phải nhân mọi phần tử của hai array thành Cartesian product.

Ví dụ JSON có arrays tags và notes. Hai sibling nested path tạo các hàng theo nhánh tương ứng, với các cột của nhánh còn lại NULL trên hàng không thuộc nhánh đó. Nếu cần kết hợp mọi tag với mọi note, phải viết phép join/JSON_TABLE riêng một cách tường minh.

Không giả định hai sibling arrays sẽ tạo N × M hàng. Hãy kiểm tra cấu trúc kết quả và dùng truy vấn riêng khi nghiệp vụ cần Cartesian combination.

## 7. JSON_TABLE trên cột của bảng quan hệ

Trong thực tế, JSON thường được lưu trong một cột:

~~~sql
CREATE TABLE order_documents (
    document_id NUMBER PRIMARY KEY,
    payload     CLOB CHECK (payload IS JSON)
);
~~~

Có thể kết hợp từng document với JSON_TABLE:

~~~sql
SELECT d.document_id,
       jt.order_id,
       jt.customer_id,
       jt.status
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id    NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             status      VARCHAR2(20) PATH '$.status'
         )
     ) jt;
~~~

JSON_TABLE có thể tham chiếu cột từ row source đứng trước trong FROM. Đây là cách dùng correlated row source thường gặp.

### 7.1 Mỗi document có một hàng

Với row path '$', một object hợp lệ thường tạo một hàng. Nếu cột payload NULL hoặc JSON không có cấu trúc phù hợp, kết quả phụ thuộc cách xử lý lỗi/empty và loại dữ liệu.

### 7.2 Mỗi document có nhiều hàng

Nếu row path là '$.items[*]', mỗi item có thể tạo một hàng:

~~~sql
SELECT d.document_id,
       jt.item_no,
       jt.product_id,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             item_no    FOR ORDINALITY,
             product_id NUMBER PATH '$.productId',
             quantity   NUMBER PATH '$.quantity'
         )
     ) jt;
~~~

Document có 5 item phù hợp tạo 5 hàng. Document không có item phù hợp không tạo hàng trong row source này; khi dùng comma join/cross join, document đó không xuất hiện trong kết quả.

### 7.3 Giữ lại document dù array rỗng

Nếu cần giữ document cha ngay cả khi không có phần tử con, dùng row path root và NESTED PATH:

~~~sql
SELECT d.document_id,
       jt.order_id,
       jt.product_id,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 product_id NUMBER PATH '$.productId',
                 quantity   NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

Với array rỗng hoặc không khớp, hàng root có thể vẫn được giữ và các cột con là NULL theo quan hệ outer join cha-con.

## 8. Chuyển JSON thành nhiều bảng quan hệ

Một document có thể chứa entity cha và nhiều entity con. Không nhất thiết phải đưa tất cả vào một bảng phẳng.

Ví dụ JSON:

~~~json
{
  "orderId": 7001,
  "customerId": 101,
  "createdAt": "2026-11-14T09:30:00",
  "items": [
    {"lineNo": 1, "productId": 501, "quantity": 2, "unitPrice": 125000},
    {"lineNo": 2, "productId": 502, "quantity": 1, "unitPrice": 250000}
  ]
}
~~~

Bảng đích:

~~~sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    created_at TIMESTAMP
);

CREATE TABLE order_items (
    order_id NUMBER NOT NULL,
    line_no NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity NUMBER(12,3) NOT NULL,
    unit_price NUMBER(14,2) NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY(order_id, line_no)
);
~~~

Nạp header:

~~~sql
INSERT INTO orders(order_id, customer_id, created_at)
SELECT jt.order_id,
       jt.customer_id,
       TO_TIMESTAMP(
           jt.created_at_text,
           'YYYY-MM-DD"T"HH24:MI:SS'
       )
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id        NUMBER PATH '$.orderId',
             customer_id     NUMBER PATH '$.customerId',
             created_at_text VARCHAR2(40) PATH '$.createdAt'
         )
     ) jt
WHERE d.document_id = :document_id;
~~~

Nạp detail:

~~~sql
INSERT INTO order_items(
    order_id,
    line_no,
    product_id,
    quantity,
    unit_price
)
SELECT jt.order_id,
       jt.line_no,
       jt.product_id,
       jt.quantity,
       jt.unit_price
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 line_no    NUMBER PATH '$.lineNo',
                 product_id NUMBER PATH '$.productId',
                 quantity   NUMBER PATH '$.quantity',
                 unit_price NUMBER PATH '$.unitPrice'
             )
         )
     ) jt
WHERE d.document_id = :document_id;
~~~

Hai thao tác INSERT phải được thực hiện trong cùng transaction nếu header và detail là một đơn vị nghiệp vụ. Caller hoặc procedure cấp cao quyết định COMMIT sau khi cả hai thành công.

## 9. Kết hợp JSON_TABLE với JOIN

Sau khi JSON_TABLE tạo row source, có thể join với bảng quan hệ:

~~~sql
SELECT jt.order_id,
       jt.product_id,
       p.product_name,
       jt.quantity,
       p.category_id
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             order_id   NUMBER PATH '$.orderId',
             product_id NUMBER PATH '$.productId',
             quantity   NUMBER PATH '$.quantity'
         )
     ) jt
JOIN products p
  ON p.product_id = jt.product_id;
~~~

Ví dụ này giả định mỗi item chứa orderId. Nếu orderId ở object cha, dùng row path '$' và NESTED PATH '$.items[*]' để lấy cả cột cha và cột con.

### 9.1 Join với khách hàng

~~~sql
SELECT d.document_id,
       jt.order_id,
       c.customer_name
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId'
         )
     ) jt
JOIN customers c
  ON c.customer_id = jt.customer_id;
~~~

### 9.2 Lọc theo cột JSON đã chiếu

~~~sql
SELECT jt.order_id,
       jt.status
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(20) PATH '$.status'
         )
     ) jt
WHERE jt.status = 'PAID';
~~~

Predicate được áp dụng trên cột SQL do JSON_TABLE tạo. Optimizer có thể thực hiện các biến đổi phù hợp, nhưng hiệu năng thực tế cần xem execution plan.

## 10. JSON_TABLE với điều kiện và aggregation

Có thể GROUP BY các cột được chiếu:

~~~sql
SELECT jt.status,
       COUNT(*) AS order_count
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             status VARCHAR2(20) PATH '$.status'
         )
     ) jt
GROUP BY jt.status;
~~~

Tính tổng quantity theo product:

~~~sql
SELECT jt.product_id,
       SUM(jt.quantity) AS total_quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId',
             quantity NUMBER PATH '$.quantity'
         )
     ) jt
GROUP BY jt.product_id;
~~~

Tính tổng tiền:

~~~sql
SELECT jt.order_id,
       SUM(jt.quantity * jt.unit_price) AS order_total
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 quantity NUMBER PATH '$.quantity',
                 unit_price NUMBER PATH '$.unitPrice'
             )
         )
     ) jt
GROUP BY jt.order_id;
~~~

Với dữ liệu tài chính, cần xác định precision/scale, quy tắc làm tròn, currency và validation. JSON_TABLE chuyển dữ liệu sang NUMBER nhưng không tự thực thi đầy đủ quy tắc nghiệp vụ tiền tệ.

## 11. Xử lý giá trị thiếu, JSON null và lỗi chuyển đổi

Một field trong JSON có thể:

1. Có giá trị đúng kiểu.
2. Không xuất hiện.
3. Xuất hiện với JSON null.
4. Có kiểu không tương thích, ví dụ chuỗi thay vì số.
5. Path không khớp hoặc cấu trúc không đúng.
6. Có nhiều giá trị trong khi cột SQL mong một scalar.

Các trường hợp này không nên bị coi là giống nhau.

### 11.1 ON ERROR

JSON_TABLE hỗ trợ xử lý lỗi ở cấp bảng và ở từng cột. Các lựa chọn thường gặp:

- NULL ON ERROR: trả NULL khi gặp lỗi thuộc phạm vi clause.
- ERROR ON ERROR: phát sinh lỗi.
- DEFAULT expr ON ERROR: trả giá trị mặc định khi lỗi.

Ví dụ:

~~~sql
SELECT jt.quantity
FROM JSON_TABLE(
    '{"quantity":"not-a-number"}',
    '$'
    COLUMNS (
        quantity NUMBER PATH '$.quantity'
            DEFAULT 0 ON ERROR
    )
) jt;
~~~

Ví dụ dùng DEFAULT 0 chỉ phù hợp nếu nghiệp vụ thật sự coi lỗi dữ liệu là 0. Trong dữ liệu tài chính hoặc tồn kho, việc biến dữ liệu sai thành 0 có thể che lỗi và làm sai kết quả. Thường nên dùng ERROR ON ERROR trong bước ingestion cần kiểm soát chặt, hoặc NULL ON ERROR rồi ghi nhận lỗi theo chính sách.

### 11.2 ON EMPTY

ON EMPTY điều khiển trường hợp path không tìm thấy giá trị:

~~~sql
SELECT jt.discount
FROM JSON_TABLE(
    '{"orderId":7001}',
    '$'
    COLUMNS (
        discount NUMBER PATH '$.discount'
            NULL ON ERROR
            DEFAULT 0 ON EMPTY
    )
) jt;
~~~

Nếu field discount không có, ví dụ trả 0 theo ON EMPTY. Nếu field có giá trị nhưng không chuyển được sang NUMBER, ON ERROR được áp dụng.

Thứ tự clause trong cú pháp Oracle đặt ON ERROR trước ON EMPTY. Hãy xác nhận cú pháp chính xác theo phiên bản database khi dùng các dạng DEFAULT.

### 11.3 JSON null khác field không tồn tại

JSON:

~~~json
{"discount": null}
~~~

khác với:

~~~json
{"orderId": 7001}
~~~

Trường hợp đầu có field discount nhưng giá trị JSON null; trường hợp sau không có field. Khi chiếu vào cột SQL scalar, cả hai có thể trở thành SQL NULL trong nhiều tình huống. Nếu nghiệp vụ phải phân biệt, cần kiểm tra sự tồn tại/loại node bằng biểu thức SQL/JSON phù hợp hoặc kiểm tra payload ở bước validation.

Không dùng một cột SQL NULL duy nhất để khẳng định nguyên nhân là field thiếu, JSON null hay conversion error nếu error policy cũng trả NULL.

### 11.4 ON ERROR mặc định không thay thế validation

Nếu không khai báo rõ, Oracle áp dụng mặc định của SQL/JSON function và clause tương ứng. Mặc định thường có thể làm lỗi trở thành NULL. Đối với ingestion quan trọng, nên chỉ định policy tường minh để tránh dữ liệu lỗi bị âm thầm bỏ qua.

### 11.5 Row path không khớp

Nếu row path không tìm thấy node phù hợp, JSON_TABLE có thể tạo zero rows. Đây là khác biệt với một row đã được tạo nhưng column path trả NULL.

Ví dụ:

~~~sql
SELECT COUNT(*)
FROM JSON_TABLE(
    '{"items":[]}',
    '$.items[*]'
    COLUMNS (
        item_id NUMBER PATH '$.id'
    )
);
~~~

Array rỗng tạo zero rows. COUNT(*) trả 0.

## 12. Kiểm soát dữ liệu JSON trước khi chiếu

JSON_TABLE giả định đầu vào là JSON hợp lệ theo quy tắc được áp dụng. Với cột lưu JSON trong CLOB/VARCHAR2/BLOB, có thể dùng IS JSON constraint:

~~~sql
CREATE TABLE inbound_messages (
    message_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_inbound_payload_json
        CHECK (payload IS JSON)
);
~~~

Constraint giúp ngăn văn bản không phải JSON hợp lệ được lưu vào cột.

### 12.1 IS JSON không kiểm tra toàn bộ business schema

JSON hợp lệ về cú pháp vẫn có thể sai nghiệp vụ:

- orderId thiếu.
- customerId không tồn tại.
- quantity âm.
- status không nằm trong danh sách cho phép.
- items không phải array theo hợp đồng.
- field có kiểu đúng nhưng miền giá trị sai.

Sau khi kiểm tra cú pháp JSON, cần kiểm tra schema và business rule bằng JSON_TABLE, constraint quan hệ hoặc validation ở tầng ứng dụng.

### 12.2 Lưu raw JSON và dữ liệu quan hệ

Một kiến trúc ingestion có thể:

1. Lưu payload gốc để audit/replay.
2. Kiểm tra JSON hợp lệ.
3. Dùng JSON_TABLE chiếu dữ liệu.
4. Validate kiểu và quy tắc nghiệp vụ.
5. Nạp bảng header/detail.
6. Đánh dấu trạng thái xử lý.

Nếu bước 5 thất bại, transaction phải đảm bảo trạng thái ingestion nhất quán. Có thể giữ raw payload với trạng thái REJECTED và thông tin lỗi theo thiết kế nghiệp vụ.

## 13. Chuyển đổi array JSON thành nhiều hàng

Đây là trường hợp phổ biến nhất của JSON_TABLE.

JSON:

~~~json
{
  "events": [
    {"eventId": 1, "type": "LOGIN"},
    {"eventId": 2, "type": "PURCHASE"},
    {"eventId": 3, "type": "LOGOUT"}
  ]
}
~~~

Truy vấn:

~~~sql
SELECT jt.event_no,
       jt.event_id,
       jt.event_type
FROM JSON_TABLE(
    :payload,
    '$.events[*]'
    COLUMNS (
        event_no   FOR ORDINALITY,
        event_id   NUMBER PATH '$.eventId',
        event_type VARCHAR2(30) PATH '$.type'
    )
) jt
ORDER BY jt.event_no;
~~~

Mỗi object trong events tạo một hàng. Đây là phép chuyển array thành rowset.

### 13.1 Array scalar

JSON array không nhất thiết chứa object:

~~~json
{"tags": ["new", "priority", "export"]}
~~~

Có thể chiếu từng scalar bằng row path:

~~~sql
SELECT jt.tag_no,
       jt.tag
FROM JSON_TABLE(
    '{"tags":["new","priority","export"]}',
    '$.tags[*]'
    COLUMNS (
        tag_no FOR ORDINALITY,
        tag VARCHAR2(30) PATH '$'
    )
) jt;
~~~

Trong mỗi row source, path '$' trỏ tới scalar hiện tại được chọn bởi row path.

### 13.2 Array object thiếu field

JSON:

~~~json
{
  "items": [
    {"productId": 501, "quantity": 2},
    {"productId": 502},
    {"productId": 503, "quantity": 4}
  ]
}
~~~

Với quantity của phần tử thứ hai bị thiếu, cột quantity có thể là SQL NULL theo empty handling mặc định hoặc clause được khai báo. Cần quyết định field đó bắt buộc hay tùy chọn. Nếu bắt buộc, validation phải phát hiện thay vì để NULL đi vào bảng đích có thể cho phép NULL.

## 14. JSON_TABLE và nhiều array độc lập

Giả sử JSON:

~~~json
{
  "orderId": 7001,
  "items": [
    {"productId": 501},
    {"productId": 502}
  ],
  "payments": [
    {"method": "CARD"},
    {"method": "VOUCHER"}
  ]
}
~~~

Nếu cần lấy item và payment thành hai quan hệ riêng, nên dùng hai JSON_TABLE riêng:

~~~sql
SELECT d.document_id,
       i.product_id
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId'
         )
     ) i;
~~~

~~~sql
SELECT d.document_id,
       p.method
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.payments[*]'
         COLUMNS (
             method VARCHAR2(30) PATH '$.method'
         )
     ) p;
~~~

Hai truy vấn tạo hai rowset độc lập. Nếu join cả hai rowset chỉ theo document_id, kết quả có thể nhân số hàng items × số hàng payments. Chỉ làm vậy nếu nghiệp vụ thực sự cần mọi cặp kết hợp.

### 14.1 Sibling nested paths và union join

Nếu khai báo nhiều NESTED PATH cùng cấp trong một JSON_TABLE, Oracle kết hợp các nhánh theo union join semantics. Điều này khác với hai JSON_TABLE độc lập được cross join. Hãy chọn cấu trúc theo quan hệ nghiệp vụ:

- Parent-child: NESTED PATH.
- Hai collection độc lập: hai JSON_TABLE/row source riêng.
- Cartesian product có chủ đích: join tường minh.

## 15. JSON_TABLE và JSON_QUERY

JSON_TABLE dùng để tạo rowset và các cột SQL. JSON_QUERY dùng để lấy object/array JSON dưới dạng JSON text hoặc kiểu trả về được hỗ trợ.

| Hàm | Mục đích |
|---|---|
| JSON_VALUE | Lấy scalar thành kiểu SQL |
| JSON_QUERY | Lấy object/array JSON |
| JSON_EXISTS | Kiểm tra path có tồn tại/match |
| JSON_TABLE | Chuyển JSON thành hàng/cột quan hệ |

Ví dụ:

~~~sql
SELECT JSON_VALUE(payload, '$.status') AS status
FROM order_documents;
~~~

Nếu chỉ cần một scalar, JSON_VALUE thường trực tiếp hơn. Nếu cần nhiều field hoặc array thành nhiều hàng, JSON_TABLE phù hợp hơn.

### 15.1 Tránh nhiều lần JSON_VALUE không cần thiết

Ví dụ:

~~~sql
SELECT JSON_VALUE(payload, '$.orderId'),
       JSON_VALUE(payload, '$.customerId'),
       JSON_VALUE(payload, '$.status')
FROM order_documents;
~~~

Khi cần nhiều field từ cùng document, JSON_TABLE có thể gom các path vào một row source:

~~~sql
SELECT jt.order_id,
       jt.customer_id,
       jt.status
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             status VARCHAR2(20) PATH '$.status'
         )
     ) jt;
~~~

Optimizer có thể biến đổi các biểu thức SQL/JSON, nên không kết luận chỉ từ số lần viết hàm trong source. Hãy xem execution plan và đo trên phiên bản Oracle thực tế.

## 16. JSON_TABLE và INSERT/MERGE

JSON_TABLE thường được dùng làm nguồn dữ liệu cho DML.

### 16.1 INSERT ... SELECT

~~~sql
INSERT INTO order_items(
    order_id,
    line_no,
    product_id,
    quantity
)
SELECT jt.order_id,
       jt.line_no,
       jt.product_id,
       jt.quantity
FROM inbound_messages m,
     JSON_TABLE(
         m.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 line_no NUMBER PATH '$.lineNo',
                 product_id NUMBER PATH '$.productId',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt
WHERE m.message_id = :message_id;
~~~

Một câu INSERT có thể nạp nhiều hàng từ một JSON document.

### 16.2 MERGE

~~~sql
MERGE INTO product_inventory target
USING (
    SELECT jt.product_id,
           jt.available_qty
    FROM inbound_messages m,
         JSON_TABLE(
             m.payload,
             '$.inventory[*]'
             COLUMNS (
                 product_id NUMBER PATH '$.productId',
                 available_qty NUMBER PATH '$.availableQty'
             )
         ) jt
    WHERE m.message_id = :message_id
) source
ON (target.product_id = source.product_id)
WHEN MATCHED THEN
    UPDATE SET target.available_qty = source.available_qty
WHEN NOT MATCHED THEN
    INSERT (product_id, available_qty)
    VALUES (source.product_id, source.available_qty);
~~~

MERGE phù hợp khi nguồn JSON có thể chứa bản ghi đã tồn tại hoặc mới. Cần bảo đảm nguồn không có nhiều hàng trùng khóa đích nếu điều đó khiến một hàng đích bị cập nhật nhiều lần; hãy validate hoặc deduplicate nguồn theo quy tắc rõ ràng.

## 17. Xây dựng view trên JSON_TABLE

Nếu nhiều truy vấn cần cùng một cấu trúc JSON, có thể tạo view:

~~~sql
CREATE OR REPLACE VIEW v_order_document_items AS
SELECT d.document_id,
       jt.order_id,
       jt.customer_id,
       jt.item_no,
       jt.product_id,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_no FOR ORDINALITY,
                 product_id NUMBER PATH '$.productId',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

Caller có thể query view như bảng quan hệ:

~~~sql
SELECT product_id,
       SUM(quantity) AS total_qty
FROM v_order_document_items
GROUP BY product_id;
~~~

View không nhất thiết materialize kết quả. Mỗi lần query có thể cần evaluate JSON_TABLE trên các document liên quan. Với workload lớn, cần xem plan và cân nhắc relational projection/materialized view hoặc bảng chuẩn hóa.

## 18. JSON data type và lưu trữ JSON theo phiên bản

JSON_TABLE có thể làm việc với các kiểu đầu vào được Oracle hỗ trợ cho SQL/JSON, thường gồm VARCHAR2, CLOB, BLOB và kiểu JSON native ở các phiên bản có hỗ trợ.

### 18.1 Oracle 19c

Ở Oracle 19c, JSON thường được lưu trong VARCHAR2, CLOB hoặc BLOB với IS JSON constraint. Ví dụ:

~~~sql
CREATE TABLE api_messages (
    message_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_api_messages_json
        CHECK (payload IS JSON)
);
~~~

### 18.2 Native JSON data type

Oracle Database 21c giới thiệu kiểu dữ liệu JSON native, dùng định dạng nhị phân OSON để lưu JSON. Các phiên bản sau tiếp tục mở rộng hỗ trợ. Cú pháp DDL và khả năng cụ thể cần đối chiếu phiên bản đang triển khai.

Nếu hệ thống cần tương thích nhiều phiên bản, thiết kế schema và code dựa trên kiểu dữ liệu được hỗ trợ ở phiên bản thấp nhất trong phạm vi triển khai.

### 18.3 BLOB JSON và encoding

Khi JSON được lưu trong BLOB, cần xác định encoding theo quy tắc Oracle SQL/JSON. Thực tế thường dùng UTF-8 cho JSON BLOB. Không lưu byte text với encoding tùy ý rồi giả định Oracle sẽ tự nhận dạng chính xác trong mọi trường hợp.

## 19. Hiệu năng JSON_TABLE

JSON_TABLE có thể tạo rowset lớn từ một document. Hiệu năng phụ thuộc:

- Kích thước tài liệu JSON.
- Số phần tử trong array.
- Số lượng path/cột được chiếu.
- Độ sâu nested path.
- Kiểu dữ liệu và conversion.
- Số document được scan.
- Predicate và join sau khi flatten.
- Storage format và phiên bản Oracle.

### 19.1 Chỉ chiếu các cột cần dùng

Không khai báo hàng chục cột JSON nếu truy vấn chỉ dùng ba cột. Việc trích xuất không cần thiết có thể tăng công việc parse/conversion.

### 19.2 Lọc document trước khi flatten

Nếu có thể, lọc tập document bằng điều kiện quan hệ trước khi mở rộng array:

~~~sql
SELECT d.document_id,
       jt.product_id
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId'
         )
     ) jt
WHERE d.document_id BETWEEN :from_id AND :to_id;
~~~

Predicate pushdown và thứ tự thực thi do optimizer quyết định; xem actual plan để xác nhận. Không giả định thứ tự viết FROM/WHERE đảm bảo thứ tự xử lý vật lý.

### 19.3 Cẩn thận với array cardinality

Một document có 10.000 phần tử có thể tạo 10.000 hàng. Nếu query scan 100.000 documents, tổng row source có thể rất lớn.

Ước lượng:

~~~text
Rows produced ≈ number of documents × average matching array elements
~~~

Đây là ước lượng sơ bộ; nested paths và cấu trúc dữ liệu có thể làm cardinality khác đi. Cần kiểm tra A-Rows và E-Rows trong execution plan.

### 19.4 Search index và function-based index

Oracle hỗ trợ JSON search index cho các truy vấn JSON phù hợp:

~~~sql
CREATE SEARCH INDEX order_payload_search_ix
ON order_documents(payload)
FOR JSON;
~~~

Search index có thể giúp một số truy vấn path/JSON_EXISTS/JSON_VALUE tùy biểu thức và phiên bản. Nó không tự động tối ưu mọi JSON_TABLE projection hoặc mọi phép flatten array.

Với scalar path được truy vấn thường xuyên, có thể cân nhắc function-based index:

~~~sql
CREATE INDEX order_status_json_ix
ON order_documents (
    JSON_VALUE(
        payload,
        '$.status'
        RETURNING VARCHAR2(20)
    )
);
~~~

Truy vấn cần tương thích với biểu thức index để optimizer có thể dùng. Hãy kiểm tra plan, thống kê và chi phí duy trì index khi payload thay đổi.

### 19.5 Materialize dữ liệu quan hệ khi cần truy vấn thường xuyên

Nếu cùng một mảng JSON được flatten cho nhiều báo cáo hoặc join thường xuyên, có thể nạp dữ liệu vào bảng quan hệ chuẩn hóa thay vì tính JSON_TABLE ở mỗi truy vấn.

Cân nhắc:

- Tần suất đọc so với ghi.
- Kích thước JSON.
- Độ trễ đồng bộ.
- Khả năng replay payload.
- Cách xử lý cập nhật/xóa item.
- Chi phí lưu trữ dữ liệu trùng lặp.

JSON_TABLE rất phù hợp cho ingestion và projection; không nhất thiết là lựa chọn tối ưu cho mọi truy vấn phân tích lặp lại.

## 20. Kiểm soát schema và dữ liệu không đồng nhất

JSON linh hoạt, nhưng nếu cùng một field có nhiều kiểu khác nhau thì SQL projection trở nên khó dự đoán:

~~~json
{"quantity": 2}
~~~

~~~json
{"quantity": "2"}
~~~

~~~json
{"quantity": null}
~~~

~~~json
{}
~~~

Một schema JSON tốt nên quy định:

- Field bắt buộc/tùy chọn.
- Kiểu dữ liệu.
- Miền giá trị.
- Format ngày giờ.
- Quy tắc null.
- Version của payload.
- Cấu trúc array và object.

Có thể lưu schema_version trong document:

~~~json
{
  "schemaVersion": 2,
  "orderId": 7001,
  "items": []
}
~~~

Khi thay đổi cấu trúc JSON, JSON_TABLE có thể cần xử lý nhiều version. Có thể dùng view/package khác nhau theo version hoặc chuyển payload cũ về schema chuẩn trước khi nạp.

### 20.1 Default không thay thế migration

Nếu field mới thiếu trong payload cũ, DEFAULT ON EMPTY có thể giúp tương thích. Nhưng nếu ý nghĩa field thay đổi, gán mặc định có thể làm sai nghiệp vụ. Cần xác định rõ default nào là an toàn và khi nào phải từ chối payload cũ.

## 21. Lỗi thường gặp khi dùng JSON_TABLE

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không có hàng kết quả | Row path không match hoặc array rỗng | Kiểm tra row path và cấu trúc JSON |
| Có hàng nhưng cột NULL | Column path thiếu, JSON null hoặc ON ERROR trả NULL | Phân biệt empty/null/conversion error |
| Lỗi chuyển kiểu NUMBER | JSON field là chuỗi không hợp lệ hoặc vượt precision | Chuẩn hóa payload, chọn kiểu và ON ERROR rõ |
| Chỉ có một hàng thay vì nhiều | Row path chọn root object thay vì array[*] | Đặt row path vào array cần bung |
| Hàng cha biến mất khi array rỗng | Cross join JSON_TABLE dùng row path array | Dùng root row path với NESTED PATH nếu cần giữ cha |
| Số hàng tăng bất ngờ | Nhiều row sources bị cross join | Xác định quan hệ cha-con và cardinality |
| Sibling arrays tạo kết quả khó hiểu | Nhầm union join với Cartesian product | Tách JSON_TABLE hoặc join rõ ràng |
| Thứ tự hàng thay đổi | Không ORDER BY | Dùng FOR ORDINALITY và ORDER BY |
| Ngày giờ lệch | Chuyển string sang DATE/TIMESTAMP không có format/timezone rõ | Trích string và chuyển đổi tường minh |
| Query chậm trên nhiều document | Parse/flatten nhiều JSON hoặc thiếu filter/index phù hợp | Xem plan, lọc document, search/function-based index |
| MERGE lỗi nhiều hàng nguồn cùng match | JSON array có key trùng | Validate/deduplicate nguồn |
| Dữ liệu sai lọt vào bảng | NULL ON ERROR che lỗi hoặc chỉ kiểm tra JSON syntax | Thêm validation schema và business rules |

## 22. Quy trình ingestion JSON vào bảng quan hệ

Một pipeline có thể gồm:

1. Nhận payload và gắn request/message ID.
2. Kiểm tra kích thước, encoding và cú pháp JSON.
3. Xác định schema version.
4. Dùng JSON_TABLE chiếu header và array con.
5. Kiểm tra field bắt buộc, kiểu, miền giá trị và tham chiếu FK.
6. Nạp header/detail trong transaction phù hợp.
7. Ghi trạng thái xử lý hoặc lỗi.
8. Dùng idempotency key để tránh nạp trùng.
9. Giữ raw payload nếu cần audit/replay.
10. Theo dõi số hàng được tạo, lỗi conversion và thời gian xử lý.

Không nên chỉ chạy JSON_TABLE rồi INSERT mà không xác định chính sách với payload lỗi hoặc duplicate.

## 23. Ví dụ tổng hợp: đọc đơn hàng JSON và join danh mục

JSON:

~~~json
{
  "schemaVersion": 1,
  "orderId": 7001,
  "customerId": 101,
  "status": "NEW",
  "items": [
    {"lineNo": 1, "productId": 501, "quantity": 2},
    {"lineNo": 2, "productId": 502, "quantity": 1}
  ]
}
~~~

Truy vấn:

~~~sql
SELECT d.document_id,
       jt.order_id,
       jt.customer_id,
       jt.status,
       jt.line_no,
       jt.product_id,
       p.product_name,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             schema_version NUMBER PATH '$.schemaVersion',
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             status VARCHAR2(20) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 line_no NUMBER PATH '$.lineNo',
                 product_id NUMBER PATH '$.productId',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt
JOIN products p
  ON p.product_id = jt.product_id
WHERE d.document_id = :document_id
  AND jt.schema_version = 1
ORDER BY jt.line_no;
~~~

Truy vấn thực hiện:

- Chọn một document theo khóa quan hệ.
- Chiếu thông tin order ở cấp cha.
- Bung items thành nhiều hàng.
- Join product_id với bảng PRODUCTS.
- Lọc theo schema version.
- Sắp xếp theo line_no.

## 24. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm với payload có cấu trúc tương tự ví dụ.

### Bài 1 — JSON object thành một hàng

Tạo JSON có orderId, customerId và status. Dùng JSON_TABLE với row path '$' để chiếu ba cột SQL.

### Bài 2 — Array thành nhiều hàng

Tạo document có array items gồm năm object. Dùng row path '$.items[*]' và đếm số hàng kết quả.

### Bài 3 — FOR ORDINALITY

Thêm cột FOR ORDINALITY. Sắp xếp theo số thứ tự và so sánh với index 0-based trong JSON path.

### Bài 4 — NESTED PATH

Tạo JSON order có items. Dùng row path root và NESTED PATH để đưa order header và item vào cùng rowset.

### Bài 5 — Array rỗng

Thử row path '$.items[*]' với array rỗng rồi thử root path + NESTED PATH. So sánh việc giữ hàng cha.

### Bài 6 — Hai array độc lập

Tạo JSON có items và payments. Dùng hai JSON_TABLE riêng. Quan sát cardinality khi cross join và giải thích khi nào Cartesian product là sai.

### Bài 7 — Scalar array

Dùng JSON array gồm các tag string. Chiếu mỗi scalar bằng path '$' và FOR ORDINALITY.

### Bài 8 — Missing, JSON null và conversion error

Thử field không tồn tại, field JSON null, field có string không chuyển được sang NUMBER. So sánh NULL ON EMPTY, ERROR ON ERROR và DEFAULT ON ERROR.

### Bài 9 — Ngày giờ

Trích createdAt dạng ISO string, chuyển bằng TO_TIMESTAMP và TO_TIMESTAMP_TZ. Giải thích khác biệt khi có offset.

### Bài 10 — INSERT header/detail

Dùng hai câu INSERT ... SELECT với JSON_TABLE để nạp header và item vào hai bảng quan hệ trong cùng transaction.

### Bài 11 — MERGE

Dùng JSON_TABLE làm nguồn MERGE vào bảng inventory. Thử payload có productId trùng và xử lý nguồn trước MERGE.

### Bài 12 — Index và execution plan

Tạo nhiều JSON documents. So sánh truy vấn JSON_VALUE/JSON_TABLE không index, function-based index và JSON search index phù hợp. Dùng actual plan và buffers để đánh giá.

## 25. Checklist thiết kế JSON_TABLE

**Cấu trúc**

- Row path có chọn đúng node sinh hàng?
- Column path có tương đối với node hiện tại?
- Array nào cần bung thành nhiều hàng?
- NESTED PATH có giữ hàng cha khi child array rỗng?
- Các sibling arrays có đang bị hiểu nhầm thành Cartesian product?
- Có cần FOR ORDINALITY để giữ vị trí?

**Kiểu dữ liệu**

- NUMBER/VARCHAR2/DATE/TIMESTAMP đã chọn rõ?
- Độ dài chuỗi có đủ và dùng BYTE/CHAR semantics phù hợp?
- Format ngày giờ và timezone đã xác định?
- Có phân biệt byte và character?

**Lỗi và validation**

- ON ERROR và ON EMPTY có được quy định tường minh?
- Có phân biệt field thiếu, JSON null và conversion error?
- Có kiểm tra cú pháp JSON?
- Có validation schema version và business rules?
- Có xử lý duplicate key và FK?

**Hiệu năng**

- Chỉ chiếu các field cần thiết?
- Có lọc document theo khóa/điều kiện quan hệ?
- Đã kiểm tra actual cardinality?
- Có cần JSON search index/function-based index?
- Có nên materialize projection vào bảng quan hệ cho workload đọc lặp?

**Nạp dữ liệu**

- Header/detail có cùng transaction?
- Có idempotency key?
- Có lưu raw payload và trạng thái lỗi?
- MERGE source có khóa trùng không?
- Có log số hàng và lỗi theo request ID?

## 26. Ghi nhớ

| Thành phần | Vai trò |
|---|---|
| JSON_TABLE | Chuyển JSON thành row source quan hệ |
| Row path | Chọn node sinh hàng |
| COLUMNS | Định nghĩa cột SQL đầu ra |
| Column PATH | Lấy field từ node hiện tại |
| FOR ORDINALITY | Đánh số hàng bắt đầu từ 1 |
| NESTED PATH | Bung array/object con theo quan hệ cha-con |
| ON ERROR | Quy định hành vi khi có lỗi |
| ON EMPTY | Quy định hành vi khi path không có giá trị |
| JSON null | Giá trị null trong JSON |
| Missing field | Path không tìm thấy field |
| CROSS JOIN row source | Document không có hàng JSON phù hợp có thể bị loại khỏi kết quả |
| Nested parent-child | Child không khớp có thể giữ parent với cột con NULL |
| JSON_VALUE | Trích scalar |
| JSON_QUERY | Trích object/array |
| JSON_EXISTS | Kiểm tra path |
| IS JSON | Kiểm tra cú pháp JSON |
| INSERT ... SELECT | Nạp nhiều hàng từ JSON |
| MERGE | Đồng bộ rowset JSON với bảng quan hệ |
| JSON search index | Hỗ trợ một số truy vấn JSON phù hợp |
| Function-based index | Tăng tốc truy vấn scalar path cụ thể |

JSON_TABLE là cầu nối giữa mô hình document và mô hình quan hệ. Hãy chọn row path đúng cấp dữ liệu, dùng column path tường minh, bung array bằng NESTED PATH, giữ thứ tự bằng FOR ORDINALITY và quy định rõ cách xử lý lỗi/giá trị thiếu. Sau khi được chiếu thành row source, dữ liệu JSON có thể join, aggregate, INSERT hoặc MERGE như dữ liệu quan hệ. Với workload lớn, luôn kiểm tra cardinality và execution plan, đồng thời cân nhắc materialize dữ liệu nếu cùng một projection được truy vấn thường xuyên.
