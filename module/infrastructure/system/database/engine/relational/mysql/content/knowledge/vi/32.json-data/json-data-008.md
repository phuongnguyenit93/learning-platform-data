# JSON_CONTAINS, JSON_OVERLAPS và truy vấn thành phần

MySQL cung cấp các hàm JSON để kiểm tra cấu trúc và tìm thành phần bên trong tài liệu JSON. Hai hàm thường dùng là JSON_CONTAINS() và JSON_OVERLAPS(). Chúng đều trả lời câu hỏi về quan hệ giữa hai giá trị JSON, nhưng ý nghĩa khác nhau: JSON_CONTAINS() kiểm tra một tài liệu có chứa toàn bộ cấu trúc ứng viên hay không; JSON_OVERLAPS() kiểm tra hai tài liệu có ít nhất một phần tử hoặc cặp khóa-giá trị chung hay không.

Khi cần đọc sâu dữ liệu JSON, có thể kết hợp JSON_EXTRACT(), toán tử -> và ->>, JSON path và JSON_TABLE(). Các công cụ này cho phép lấy một trường, duyệt mảng hoặc chuyển các phần tử JSON thành hàng và cột để JOIN, lọc, nhóm và tổng hợp bằng SQL.

Trong module **DATABASE_MYSQL**, JSON phù hợp với dữ liệu có cấu trúc linh hoạt nhưng vẫn cần được truy vấn có kiểm soát. Bài học này hướng dẫn phân biệt containment và overlap, truy vấn object/array lồng nhau, chuyển phần tử thành hàng quan hệ và chọn index phù hợp cho workload thực tế.

## 1. Chuẩn bị dữ liệu JSON

MySQL có kiểu dữ liệu JSON. Khi INSERT hoặc UPDATE vào cột JSON, server kiểm tra nội dung có phải JSON hợp lệ hay không và lưu theo định dạng nội bộ tối ưu cho truy cập thành phần.

Ví dụ bảng sản phẩm:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Chèn dữ liệu có object, scalar và array:

```sql
INSERT INTO products (
    product_id,
    product_name,
    attributes
)
VALUES
(
    1,
    'Travel Bottle',
    JSON_OBJECT(
        'brand', 'Northwind',
        'category', 'outdoor',
        'capacity_ml', 750,
        'features', JSON_ARRAY('insulated', 'leakproof'),
        'tags', JSON_ARRAY('travel', 'sale'),
        'dimensions', JSON_OBJECT(
            'height_cm', 25,
            'diameter_cm', 7
        )
    )
),
(
    2,
    'Desk Lamp',
    JSON_OBJECT(
        'brand', 'Contoso',
        'category', 'home',
        'features', JSON_ARRAY('dimmable', 'led'),
        'tags', JSON_ARRAY('office', 'new')
    )
);
```

Có thể xem nội dung:

```sql
SELECT product_id, attributes
FROM products;
```

JSON object chứa các cặp key/value; JSON array chứa các phần tử theo thứ tự; scalar là string, number, boolean hoặc JSON null. Cấu trúc lồng nhau có thể kết hợp cả ba loại.

## 2. JSON_CONTAINS(): kiểm tra một cấu trúc có nằm trong cấu trúc khác

Cú pháp:

```sql
JSON_CONTAINS(target, candidate[, path])
```

Hàm trả về:

- 1 nếu candidate được chứa trong target theo quy tắc containment.
- 0 nếu candidate không được chứa.
- SQL NULL nếu một đối số là SQL NULL.
- Lỗi nếu JSON đầu vào hoặc path không hợp lệ.

Có thể truyền path để giới hạn việc kiểm tra vào một phần của tài liệu. Nếu bỏ path, MySQL kiểm tra toàn bộ target.

### 2.1. Quy tắc containment với object

Với hai object, candidate được chứa trong target nếu mọi cặp key/value của candidate đều có trong target, với giá trị tương ứng được xem là bằng nhau theo quy tắc so sánh JSON.

Ví dụ:

```sql
SELECT JSON_CONTAINS(
    '{"brand":"Northwind","category":"outdoor","capacity_ml":750}',
    '{"brand":"Northwind"}'
) AS is_contained;
```

Kết quả là 1 vì target có cặp brand = Northwind.

Nếu candidate yêu cầu thêm một cặp không có trong target:

```sql
SELECT JSON_CONTAINS(
    '{"brand":"Northwind","category":"outdoor"}',
    '{"brand":"Northwind","color":"blue"}'
) AS is_contained;
```

Kết quả là 0 vì target không có color = blue.

Candidate object có thể là một phần của object lớn hơn. Nó không cần chứa tất cả các key của target.

### 2.2. Quy tắc containment với array

Với candidate là array, mọi phần tử của candidate phải được tìm thấy trong target array theo quy tắc containment. Candidate array vì vậy diễn tả tập điều kiện cần có đầy đủ.

```sql
SELECT JSON_CONTAINS(
    '["travel","sale","featured"]',
    '["travel","sale"]'
) AS contains_all;
```

Kết quả là 1 vì cả travel và sale đều có trong target.

Nếu một phần tử không tồn tại:

```sql
SELECT JSON_CONTAINS(
    '["travel","sale"]',
    '["travel","clearance"]'
) AS contains_all;
```

Kết quả là 0.

Nếu candidate là scalar còn target là array, hàm kiểm tra scalar đó có phải một phần tử của target hay không:

```sql
SELECT JSON_CONTAINS(
    '["travel","sale"]',
    '"sale"'
) AS has_sale;
```

Kết quả là 1.

Lưu ý candidate string phải là một JSON string hợp lệ. SQL literal '"sale"' chứa JSON string "sale"; SQL literal 'sale' không phải JSON document hợp lệ.

### 2.3. Quy tắc containment với array object

Một trường hợp phổ biến là tìm object trong mảng:

```sql
SELECT JSON_CONTAINS(
    '[
        {"sku":"A-100","qty":2,"warehouse":"HCM"},
        {"sku":"B-200","qty":1,"warehouse":"HN"}
    ]',
    '{"sku":"A-100","qty":2}'
) AS item_found;
```

Kết quả là 1 vì có một phần tử object chứa cả sku = A-100 và qty = 2. Candidate không cần liệt kê warehouse.

Có thể áp dụng trực tiếp lên một path của cột JSON:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_CONTAINS(
    attributes,
    JSON_ARRAY('insulated', 'leakproof'),
    '$.features'
);
```

Truy vấn chọn sản phẩm có đủ cả hai feature. Với sản phẩm có features là array, JSON_CONTAINS yêu cầu mọi phần tử candidate đều được chứa.

### 2.4. Tìm một object trong mảng JSON của bảng

Giả sử đơn hàng có danh sách item:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

INSERT INTO orders (order_id, payload)
VALUES
(
    1001,
    JSON_OBJECT(
        'customer_id', 501,
        'items', JSON_ARRAY(
            JSON_OBJECT('sku', 'A-100', 'qty', 2),
            JSON_OBJECT('sku', 'B-200', 'qty', 1)
        )
    )
);
```

Tìm đơn có item SKU A-100:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', 'A-100'),
    '$.items'
);
```

Path $.items trỏ tới array. Candidate object được so với các phần tử của array; chỉ cần một phần tử thỏa candidate object là đủ theo quy tắc containment của array.

Để yêu cầu item có cả SKU và số lượng:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', 'A-100', 'qty', 2),
    '$.items'
);
```

## 3. JSON_OVERLAPS(): kiểm tra có phần tử chung

Cú pháp:

```sql
JSON_OVERLAPS(json_doc1, json_doc2)
```

JSON_OVERLAPS() trả 1 nếu hai tài liệu JSON có ít nhất một thành phần chung theo quy tắc so sánh; trả 0 nếu không có; trả SQL NULL nếu một đối số là SQL NULL.

Khác với JSON_CONTAINS(), hàm không yêu cầu một tài liệu phải chứa toàn bộ tài liệu còn lại. Chỉ cần một phần tử hoặc cặp key/value chung là đủ.

### 3.1. Hai array có ít nhất một phần tử chung

```sql
SELECT JSON_OVERLAPS(
    '["travel","sale","featured"]',
    '["new","sale"]'
) AS has_overlap;
```

Kết quả là 1 vì sale xuất hiện trong cả hai array.

Nếu không có phần tử chung:

```sql
SELECT JSON_OVERLAPS(
    '["travel","sale"]',
    '["office","new"]'
) AS has_overlap;
```

Kết quả là 0.

Dùng JSON_OVERLAPS() khi điều kiện nghiệp vụ là "có bất kỳ tag nào trong danh sách được yêu cầu", thay vì "phải có đủ mọi tag".

### 3.2. Hai object có cặp key/value chung

Với object, hai tài liệu overlap nếu có ít nhất một cặp khóa và giá trị tương ứng chung.

```sql
SELECT JSON_OVERLAPS(
    '{"brand":"Northwind","category":"outdoor"}',
    '{"category":"outdoor","color":"blue"}'
) AS has_overlap;
```

Kết quả là 1 vì cả hai có cặp category = outdoor.

Chỉ trùng key nhưng giá trị khác nhau thì không đủ:

```sql
SELECT JSON_OVERLAPS(
    '{"status":"PAID"}',
    '{"status":"PENDING"}'
) AS has_overlap;
```

Kết quả là 0. Cặp key/value không giống nhau.

### 3.3. Scalar và array

Nếu một đối số là scalar và đối số kia là array, hàm kiểm tra scalar có phải phần tử của array hay không:

```sql
SELECT JSON_OVERLAPS(
    '"sale"',
    '["new","sale","featured"]'
) AS has_overlap;
```

Kết quả là 1.

Hai scalar overlap khi chúng bằng nhau theo quy tắc so sánh JSON:

```sql
SELECT JSON_OVERLAPS('42', '42') AS same_value;
```

Kết quả là 1.

### 3.4. Phép so sánh không tự tìm sâu trong cấu trúc lồng

JSON_OVERLAPS() so sánh các giá trị ở cấp của hai document được truyền vào. Hàm không tự duyệt sâu mọi object hoặc array con để tìm một scalar nằm ở bất kỳ vị trí nào. Nếu cần so sánh một phần lồng nhau, hãy trích xuất đúng path trước:

```sql
SELECT JSON_OVERLAPS(
    payload->'$.tags',
    JSON_ARRAY('sale', 'featured')
)
FROM orders;
```

Nếu tags nằm bên trong từng item của mảng items, hãy dùng JSON_TABLE để tách item và tags theo từng hàng thay vì giả định JSON_OVERLAPS sẽ tự tìm sâu qua mọi cấp.

### 3.5. Dùng với cột JSON chứa tags

Nếu sản phẩm có nhiều tag và truy vấn cần khớp bất kỳ tag nào trong tập yêu cầu:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

Sản phẩm được chọn nếu tags có ít nhất một trong hai giá trị sale hoặc featured.

Nếu nghiệp vụ yêu cầu có đủ cả hai tag, hãy dùng JSON_CONTAINS:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_CONTAINS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

Đây là khác biệt quan trọng nhất giữa hai hàm:

| Nhu cầu | Hàm phù hợp |
|---|---|
| Có tất cả phần tử trong danh sách yêu cầu | JSON_CONTAINS |
| Có ít nhất một phần tử trong danh sách yêu cầu | JSON_OVERLAPS |
| Object chứa tất cả cặp key/value ứng viên | JSON_CONTAINS |
| Hai object có ít nhất một cặp key/value chung | JSON_OVERLAPS |

JSON_OVERLAPS() được bổ sung từ MySQL 8.0.17. Nếu hệ thống chạy phiên bản cũ hơn, kiểm tra version trước khi dùng hàm này hoặc viết điều kiện tương đương theo cấu trúc dữ liệu.

## 4. So sánh kiểu JSON và xử lý NULL

Các hàm JSON so sánh giá trị theo kiểu JSON. Không nên dựa vào chuyển đổi ngầm giữa string, number và boolean.

Ví dụ string "42" khác number 42:

```sql
SELECT
    JSON_CONTAINS('["42"]', '42') AS string_array_contains_number,
    JSON_CONTAINS('[42]', '"42"') AS number_array_contains_string;
```

Cả hai biểu thức đều trả 0. Sử dụng candidate có kiểu phù hợp với dữ liệu.

Đối với scalar số, MySQL cho phép so sánh các giá trị INTEGER và DECIMAL theo quy tắc JSON containment; không nên suy rộng điều đó thành việc mọi kiểu đều được ép về cùng một kiểu.

### 4.1. SQL NULL khác JSON null

Có ba tình huống cần phân biệt:

1. SQL NULL: không có giá trị SQL.
2. JSON null: một giá trị JSON hợp lệ nằm trong document.
3. Path không tồn tại: JSON_EXTRACT thường trả SQL NULL vì không tìm thấy đường dẫn.

Ví dụ:

```sql
SELECT
    JSON_EXTRACT('{"a":null}', '$.a') AS explicit_json_null,
    JSON_EXTRACT('{"b":1}', '$.a') AS missing_path,
    JSON_TYPE(JSON_EXTRACT('{"a":null}', '$.a')) AS json_type;
```

Với path tồn tại và chứa JSON null, kết quả là giá trị JSON null. Với path không tồn tại, JSON_EXTRACT trả SQL NULL. JSON_TYPE của giá trị JSON null trả chuỗi NULL.

Có thể kiểm tra path tồn tại bằng JSON_CONTAINS_PATH:

```sql
SELECT
    JSON_CONTAINS_PATH(
        '{"a":null}',
        'one',
        '$.a'
    ) AS path_exists,
    JSON_CONTAINS_PATH(
        '{"a":null}',
        'one',
        '$.missing'
    ) AS missing_path_exists;
```

JSON_CONTAINS() và JSON_OVERLAPS() trả SQL NULL nếu một đối số SQL là NULL. Vì vậy, khi cột JSON cho phép NULL hoặc biểu thức path có thể trả SQL NULL, hãy xác định rõ cách xử lý trong WHERE, IF hoặc CASE.

### 4.2. Kiểm tra kiểu dữ liệu trước khi so sánh

Có thể dùng JSON_TYPE() để xem kiểu của một thành phần:

```sql
SELECT
    JSON_TYPE(attributes->'$.capacity_ml') AS capacity_type,
    JSON_TYPE(attributes->'$.features') AS features_type,
    JSON_TYPE(attributes->'$.brand') AS brand_type
FROM products
WHERE product_id = 1;
```

Các kiểu thường gặp gồm OBJECT, ARRAY, STRING, INTEGER, DOUBLE, DECIMAL, BOOLEAN và NULL. Kết quả phụ thuộc giá trị JSON thực tế và phiên bản.

Khi ứng dụng gửi candidate, hãy thống nhất schema và kiểu dữ liệu. Ví dụ mã sản phẩm nên luôn là string nếu được lưu dạng string; số lượng nên luôn là number. Đừng lúc gửi "2" lúc gửi 2 nếu logic phụ thuộc so sánh chính xác.

## 5. JSON path để truy cập thành phần

JSON path xác định vị trí cần đọc trong document. Một số dạng thường dùng:

| Path | Ý nghĩa |
|---|---|
| $ | Toàn bộ document |
| $.brand | Key brand ở root object |
| $.dimensions.height_cm | Key lồng nhau |
| $.features[0] | Phần tử đầu tiên của array |
| $.items[*].sku | Trường sku của mọi phần tử trong items |
| $[1] | Phần tử thứ hai của root array |

Chỉ số array bắt đầu từ 0.

Ví dụ lấy dung tích:

```sql
SELECT
    JSON_EXTRACT(attributes, '$.capacity_ml') AS capacity
FROM products;
```

Lấy phần tử đầu của features:

```sql
SELECT
    JSON_EXTRACT(attributes, '$.features[0]') AS first_feature
FROM products;
```

Lấy tất cả SKU trong array:

```sql
SELECT
    JSON_EXTRACT(payload, '$.items[*].sku') AS item_skus
FROM orders;
```

JSON_EXTRACT với wildcard có thể trả về một JSON array chứa các kết quả khớp.

### 5.1. Toán tử -> và ->>

Toán tử -> là shorthand cho JSON_EXTRACT:

```sql
SELECT attributes->'$.brand' AS brand_json
FROM products;
```

Kết quả vẫn là JSON value. Khi cần string SQL đã bỏ dấu quote JSON, dùng ->>:

```sql
SELECT attributes->>'$.brand' AS brand_text
FROM products;
```

->> tương đương việc dùng JSON_UNQUOTE(JSON_EXTRACT(...)).

```sql
SELECT
    JSON_UNQUOTE(
        JSON_EXTRACT(attributes, '$.brand')
    ) AS brand_text
FROM products;
```

Dùng ->> khi cần so sánh với VARCHAR, hiển thị chuỗi hoặc JOIN với cột text. Với giá trị số, cần CAST về kiểu SQL phù hợp nếu thực hiện phép tính hoặc so sánh số học:

```sql
SELECT product_id
FROM products
WHERE CAST(
    attributes->>'$.capacity_ml' AS UNSIGNED
) >= 500;
```

Nếu truy vấn số thường xuyên, cân nhắc generated column có kiểu số và index thay vì CAST lặp lại trên từng hàng.

### 5.2. JSON_CONTAINS với path và giới hạn wildcard

Có thể kiểm tra containment tại một path cụ thể:

```sql
SELECT JSON_CONTAINS(
    attributes,
    '"outdoor"',
    '$.category'
)
FROM products;
```

Path argument của JSON_CONTAINS() không cho phép wildcard * hoặc **. Nếu cần kiểm tra các phần tử trong array, hãy trỏ đến array như $.features hoặc $.items, rồi để quy tắc containment kiểm tra các phần tử của nó.

Với truy vấn trích xuất nhiều phần tử, JSON_EXTRACT hỗ trợ wildcard path phù hợp:

```sql
SELECT JSON_EXTRACT(
    payload,
    '$.items[*].sku'
)
FROM orders;
```

Đừng nhầm khả năng wildcard của JSON_EXTRACT với path argument của JSON_CONTAINS.

## 6. Truy vấn trường lồng nhau và kết hợp điều kiện

Có thể kết hợp JSON_EXTRACT, JSON_CONTAINS và JSON_OVERLAPS trong WHERE:

```sql
SELECT
    product_id,
    product_name,
    attributes->>'$.brand' AS brand
FROM products
WHERE attributes->>'$.category' = 'outdoor'
  AND JSON_OVERLAPS(
      attributes->'$.features',
      JSON_ARRAY('insulated', 'waterproof')
  );
```

Truy vấn lọc category là outdoor và có ít nhất một feature trong danh sách yêu cầu.

Nếu cần đủ tất cả feature:

```sql
SELECT product_id, product_name
FROM products
WHERE attributes->>'$.category' = 'outdoor'
  AND JSON_CONTAINS(
      attributes->'$.features',
      JSON_ARRAY('insulated', 'leakproof')
  );
```

Nếu cần vừa có category, vừa có cấu trúc object cụ thể:

```sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS(
    attributes,
    JSON_OBJECT(
        'category', 'outdoor',
        'dimensions', JSON_OBJECT('height_cm', 25)
    )
);
```

Candidate object phải được chứa theo cấu trúc lồng nhau. Một object lồng nhau không được thay thế bởi một scalar có cùng nội dung hiển thị.

## 7. Chuyển JSON array thành hàng bằng JSON_TABLE

JSON_EXTRACT phù hợp để lấy giá trị. Khi cần JOIN, GROUP BY, lọc nhiều thuộc tính của từng phần tử hoặc tổng hợp, JSON_TABLE() thường dễ dùng hơn.

JSON_TABLE() biến các phần tử được chọn bởi JSON path thành một bảng quan hệ ảo trong câu SELECT. Hàm này có từ MySQL 8.0.4.

Ví dụ payload đơn hàng:

```sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE;
```

Giải thích:

- o.payload: document JSON đầu vào.
- $.items[*]: mỗi phần tử trong array items tạo một hàng.
- FOR ORDINALITY: sinh số thứ tự bắt đầu từ 1.
- PATH '$.sku': lấy sku từ object phần tử.
- PATH '$.qty': lấy qty và chuyển thành kiểu SQL INT.
- AS jt: alias để tham chiếu các cột do JSON_TABLE tạo.

Kết quả có một hàng cho mỗi item. Có thể dùng cột jt.sku trong WHERE, JOIN và GROUP BY như cột của một bảng thông thường.

### 7.1. Kiểm soát dữ liệu thiếu hoặc không chuyển đổi được

JSON_TABLE hỗ trợ ON EMPTY và ON ERROR cho từng cột:

```sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku'
            ERROR ON EMPTY
            ERROR ON ERROR,
        qty INT PATH '$.qty'
            DEFAULT '1' ON EMPTY
            NULL ON ERROR
    )
) AS jt ON TRUE;
```

- ERROR ON EMPTY: phát lỗi khi path của cột không tìm thấy.
- DEFAULT '1' ON EMPTY: dùng giá trị mặc định nếu path không tồn tại.
- NULL ON ERROR: trả SQL NULL khi chuyển đổi hoặc trích xuất gây lỗi theo điều kiện ON ERROR.

Thứ tự khai báo chuẩn là ON EMPTY trước ON ERROR. Hãy chọn chính sách theo hợp đồng dữ liệu: trường bắt buộc nên báo lỗi hoặc được kiểm tra rõ; trường tùy chọn có thể nhận mặc định hoặc NULL.

Không dùng DEFAULT để che dữ liệu sai một cách vô thức. Nếu một giá trị qty có định dạng không hợp lệ, cần quyết định đó là lỗi dữ liệu hay có thể bỏ qua.

### 7.2. Lọc và tổng hợp các phần tử JSON

Sau khi chuyển thành hàng, có thể lọc từng item:

```sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
WHERE jt.qty >= 2;
```

Tổng hợp số lượng theo SKU:

```sql
SELECT
    jt.sku,
    SUM(jt.qty) AS total_qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
GROUP BY jt.sku
ORDER BY total_qty DESC;
```

JSON_TABLE giúp chuyển cấu trúc bán cấu trúc thành quan hệ để dùng các công cụ SQL quen thuộc. Tuy nhiên, mỗi lần chạy vẫn phải đọc và phân tích các document liên quan; nếu truy vấn thành phần là workload nóng, hãy cân nhắc chuẩn hóa thành bảng con hoặc index phù hợp.

### 7.3. NESTED PATH cho array lồng nhau

Một phần tử có thể chứa array con. Dùng NESTED PATH để tạo cột từ cấu trúc lồng:

```sql
SELECT
    o.order_id,
    jt.sku,
    jt.discount_code
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        NESTED PATH '$.discounts[*]'
        COLUMNS (
            discount_code VARCHAR(32) PATH '$'
        )
    )
) AS jt ON TRUE;
```

Mỗi discount trong mỗi item có thể tạo một hàng. Khi nested path không khớp, JSON_TABLE vẫn có thể tạo hàng cha với các cột nested là SQL NULL theo semantics của NESTED PATH. Nếu có nhiều nested array, hãy đánh giá số hàng được nhân lên và khả năng kết quả bị phình lớn.

## 8. Chọn đúng hàm để kiểm tra dữ liệu

Một số hàm thường được dùng cùng JSON_CONTAINS và JSON_OVERLAPS:

| Hàm | Mục đích |
|---|---|
| JSON_CONTAINS | Kiểm tra candidate được chứa trong target |
| JSON_OVERLAPS | Kiểm tra hai document có thành phần chung |
| JSON_CONTAINS_PATH | Kiểm tra một hoặc tất cả JSON path có tồn tại |
| JSON_EXTRACT | Trích xuất giá trị theo JSON path |
| JSON_LENGTH | Đếm phần tử của array/object hoặc độ dài tại path |
| JSON_KEYS | Lấy danh sách key của object |
| JSON_SEARCH | Tìm path chứa string khớp mẫu |
| JSON_TABLE | Chuyển dữ liệu JSON thành hàng/cột quan hệ |
| JSON_TYPE | Xác định kiểu JSON của giá trị |

Ví dụ kiểm tra path tồn tại:

```sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS_PATH(
    attributes,
    'all',
    '$.brand',
    '$.features'
);
```

one nghĩa là ít nhất một path tồn tại; all nghĩa là tất cả path được liệt kê đều tồn tại. Hàm này chỉ kiểm tra sự tồn tại, không xác nhận giá trị bên trong thỏa điều kiện.

Đếm số feature:

```sql
SELECT
    product_id,
    JSON_LENGTH(attributes, '$.features') AS feature_count
FROM products;
```

Tìm tên key của object:

```sql
SELECT JSON_KEYS(attributes)
FROM products;
```

Nếu cần tìm string theo mẫu, JSON_SEARCH() có thể trả về path của giá trị string khớp mẫu. Nó không phải công cụ tìm mọi kiểu JSON value và không thay thế JSON_CONTAINS().

## 9. Index cho truy vấn JSON

Cột JSON không thể được dùng như một B-tree index thông thường để tìm tùy ý mọi path. Nếu workload thường xuyên lọc theo một scalar path, có thể tạo generated column rồi index cột đó.

### 9.1. Generated column cho scalar path

Ví dụ category được truy vấn thường xuyên:

```sql
ALTER TABLE products
    ADD COLUMN category VARCHAR(50)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(
                JSON_EXTRACT(attributes, '$.category')
            )
        ) STORED,
    ADD INDEX idx_products_category (category);
```

Sau đó truy vấn:

```sql
SELECT product_id, product_name
FROM products
WHERE category = 'outdoor';
```

Generated column có kiểu SQL rõ ràng và có thể được index như cột thông thường. Hãy chọn độ dài, charset, collation và kiểu số phù hợp với dữ liệu; nếu path thiếu hoặc có kiểu không đúng, xác định rõ NULL/default/conversion semantics.

### 9.2. Multi-valued index cho JSON array

Từ MySQL 8.0.17, InnoDB hỗ trợ multi-valued index (MVI) để index nhiều scalar element trong một JSON array. MVI hữu ích cho truy vấn membership trên array, gồm các predicate phù hợp dùng JSON_CONTAINS(), JSON_OVERLAPS() và MEMBER OF().

Ví dụ index array tags:

```sql
CREATE INDEX idx_products_tags
ON products (
    (
        CAST(
            attributes->'$.tags'
            AS CHAR(32) ARRAY
        )
    )
);
```

Truy vấn overlap:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

Nếu expression và kiểu dữ liệu của predicate phù hợp với MVI, optimizer có thể sử dụng index để tìm các hàng có phần tử phù hợp. Việc có index không bảo đảm optimizer luôn chọn nó; cần xác nhận bằng EXPLAIN trên dữ liệu đại diện.

MVI có các giới hạn quan trọng:

- Chỉ hỗ trợ InnoDB.
- Mỗi index chỉ có một multi-valued key part.
- MVI không thay thế index B-tree thông thường cho mọi loại truy vấn.
- Không cung cấp thứ tự sắp xếp các phần tử như một B-tree key thông thường.
- Cần chọn kiểu CAST phù hợp với kiểu phần tử JSON và độ dài dữ liệu.
- Predicate phải tương thích với biểu thức index để optimizer có thể khai thác.

Nếu array chứa object phức tạp hoặc cần JOIN nhiều thuộc tính của từng phần tử, bảng con quan hệ thường dễ index và ràng buộc hơn MVI.

### 9.3. Khi nào nên chuẩn hóa JSON array thành bảng con?

JSON array phù hợp khi các phần tử thường được đọc cùng document, cấu trúc thay đổi linh hoạt và không cần ràng buộc quan hệ mạnh.

Nên cân nhắc bảng con khi:

- Cần JOIN thường xuyên theo từng phần tử.
- Cần foreign key hoặc UNIQUE constraint trên phần tử.
- Cần cập nhật/xóa từng phần tử độc lập.
- Cần thống kê, phân trang hoặc sắp xếp trên từng phần tử.
- Mảng lớn hoặc truy vấn thành phần là workload chính.

Ví dụ bảng quan hệ:

```sql
CREATE TABLE product_tags (
    product_id BIGINT UNSIGNED NOT NULL,
    tag VARCHAR(32) NOT NULL,
    PRIMARY KEY (product_id, tag),
    KEY idx_product_tags_tag (tag),
    CONSTRAINT fk_product_tags_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id)
) ENGINE = InnoDB;
```

Tìm sản phẩm có tag sale hoặc featured:

```sql
SELECT DISTINCT product_id
FROM product_tags
WHERE tag IN ('sale', 'featured');
```

Bảng con hỗ trợ index, constraint và JOIN rõ ràng. Đổi lại, ứng dụng cần duy trì tính nhất quán giữa dữ liệu cha và các hàng con trong transaction.

## 10. Tối ưu truy vấn JSON

Một số nguyên tắc:

1. Chỉ trích xuất path cần dùng, không lấy toàn bộ document nếu không cần.
2. Dùng JSON_CONTAINS cho điều kiện phải có đủ candidate; dùng JSON_OVERLAPS khi chỉ cần một phần tử chung.
3. Dùng JSON_TABLE khi cần biến nhiều phần tử thành hàng để JOIN hoặc tổng hợp.
4. Với scalar path truy vấn thường xuyên, cân nhắc generated column và index.
5. Với array scalar, xem xét MVI nếu version và predicate phù hợp.
6. Với quan hệ phức tạp, cân nhắc bảng con thay vì lưu toàn bộ trong JSON.
7. Dùng EXPLAIN để xác nhận index được chọn.
8. Đo trên dữ liệu có kích thước và phân bố gần production.

Ví dụ xem execution plan:

```sql
EXPLAIN FORMAT = JSON
SELECT product_id
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

Kiểm tra access path, key được chọn, số hàng ước lượng và filter. Nếu MVI không được sử dụng, xác nhận biểu thức index, kiểu CAST, kiểu phần tử và phiên bản server.

Không nên tạo MVI hoặc generated column cho mọi path. Mỗi index làm tăng dung lượng và chi phí INSERT/UPDATE; khi JSON document thay đổi, index tương ứng cũng phải được duy trì.

## 11. An toàn khi tạo candidate JSON từ ứng dụng

Không ghép chuỗi JSON từ dữ liệu người dùng bằng cách nối chuỗi thủ công. Hãy dùng parameter binding và các hàm JSON để tránh lỗi escape và giữ đúng kiểu.

Ví dụ dùng JSON_ARRAY:

```sql
SELECT product_id
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY(?, ?)
);
```

Ví dụ dùng JSON_OBJECT:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', ?, 'qty', ?),
    '$.items'
);
```

Nếu ứng dụng truyền một JSON document hoàn chỉnh, bind nó như parameter rồi CAST sang JSON nếu cần:

```sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS(
    attributes,
    CAST(? AS JSON),
    '$.features'
);
```

Không nối trực tiếp giá trị người dùng vào JSON path hoặc dynamic SQL. Nếu path cần thay đổi theo chức năng, dùng danh sách path được cho phép và kiểm tra đầu vào. Path sai có thể làm truy vấn lỗi; path quá rộng cũng có thể khiến truy vấn tốn tài nguyên hơn dự kiến.

## 12. Ví dụ tổng hợp: tìm đơn theo SKU và số lượng

Yêu cầu: tìm các đơn có item SKU A-100 với số lượng ít nhất 2, sau đó liệt kê từng item của đơn.

Dùng JSON_CONTAINS để lọc document:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', 'A-100', 'qty', 2),
    '$.items'
);
```

Lưu ý: candidate object ở đây kiểm tra qty bằng đúng 2. Nếu yêu cầu qty >= 2, JSON_CONTAINS không biểu diễn phép so sánh range. Hãy dùng JSON_TABLE để chuyển qty thành cột số:

```sql
SELECT DISTINCT o.order_id
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
WHERE jt.sku = 'A-100'
  AND jt.qty >= 2;
```

Để xem toàn bộ item của các đơn thỏa điều kiện, có thể dùng CTE:

```sql
WITH matching_orders AS (
    SELECT DISTINCT o.order_id
    FROM orders AS o
    JOIN JSON_TABLE(
        o.payload,
        '$.items[*]'
        COLUMNS (
            sku VARCHAR(64) PATH '$.sku',
            qty INT PATH '$.qty'
        )
    ) AS x ON TRUE
    WHERE x.sku = 'A-100'
      AND x.qty >= 2
)
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM matching_orders AS m
JOIN orders AS o
    ON o.order_id = m.order_id
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
ORDER BY o.order_id, jt.sku;
```

Ví dụ này thể hiện ranh giới giữa hai nhóm công cụ:

- JSON_CONTAINS phù hợp kiểm tra cấu trúc có chứa candidate.
- JSON_TABLE phù hợp so sánh từng trường theo điều kiện SQL như >=, BETWEEN, JOIN hoặc GROUP BY.

## 13. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng JSON_CONTAINS khi chỉ cần một phần tử bất kỳ | Điều kiện quá chặt vì mọi candidate array element phải có mặt | Dùng JSON_OVERLAPS |
| Dùng JSON_OVERLAPS khi cần đủ tất cả phần tử | Trả hàng chỉ có một phần tử chung | Dùng JSON_CONTAINS |
| Nhầm JSON string với SQL string | Candidate không phải JSON hợp lệ hoặc không khớp kiểu | Dùng JSON_ARRAY/JSON_OBJECT hoặc JSON literal đúng |
| So sánh string "42" với number 42 | Không khớp do khác JSON type | Chuẩn hóa kiểu dữ liệu |
| Dùng JSON_CONTAINS path với wildcard | Path không hợp lệ | Trỏ đến array cụ thể hoặc dùng JSON_EXTRACT/JSON_TABLE |
| Dùng JSON_EXTRACT rồi so sánh object như text | So sánh dễ sai do định dạng/kiểu | Dùng JSON_CONTAINS/JSON_OVERLAPS hoặc JSON_TYPE |
| Cho rằng JSON null là SQL NULL | Bỏ sót giá trị JSON null hoặc path thiếu | Phân biệt JSON_TYPE và JSON_CONTAINS_PATH |
| Dùng JSON_CONTAINS để kiểm tra qty >= n | Containment chỉ kiểm tra cấu trúc/giá trị, không phải range | Dùng JSON_TABLE hoặc generated scalar column |
| Dùng JSON_TABLE trên mảng rất lớn trong mọi truy vấn | Tốn CPU và có thể nhân số hàng lớn | Chuẩn hóa bảng con hoặc index theo workload |
| Nghĩ cột JSON tự có index cho mọi path | Query vẫn quét nhiều document | Generated column hoặc MVI |
| Tạo MVI nhưng optimizer không dùng | Predicate không khớp expression/type hoặc plan khác rẻ hơn | Kiểm tra version, CAST và EXPLAIN |
| Ghép JSON từ input bằng string concatenation | Lỗi escape và rủi ro injection | Parameter binding và JSON_OBJECT/JSON_ARRAY |

## 14. Checklist chọn công cụ JSON

Trước khi viết truy vấn:

- Xác định dữ liệu là object, array hay scalar.
- Xác định điều kiện cần tất cả hay chỉ cần bất kỳ phần tử nào.
- Xác định path và kiểu dữ liệu của candidate.
- Phân biệt SQL NULL, JSON null và path không tồn tại.
- Nếu cần so sánh range hoặc tổng hợp từng phần tử, dùng JSON_TABLE.
- Nếu chỉ cần kiểm tra path tồn tại, dùng JSON_CONTAINS_PATH.
- Nếu cần đọc scalar, dùng JSON_EXTRACT hoặc ->>; chọn kiểu SQL phù hợp.
- Nếu dùng JSON_OVERLAPS, kiểm tra MySQL 8.0.17 trở lên.
- Nếu dùng JSON_TABLE, kiểm tra MySQL 8.0.4 trở lên.

Trước khi triển khai:

- Kiểm tra JSON document hợp lệ và schema dữ liệu có nhất quán.
- Bind parameter thay vì ghép chuỗi JSON.
- Cân nhắc generated column cho scalar path truy vấn nóng.
- Cân nhắc MVI cho array scalar nếu predicate được hỗ trợ.
- Cân nhắc bảng con khi cần constraint/JOIN/update từng phần tử.
- Đọc EXPLAIN và benchmark trên dữ liệu đại diện.
- Đo chi phí ghi, dung lượng index và độ trễ truy vấn.
- Có kế hoạch migration khi thay đổi cấu trúc JSON.

## 15. Ghi nhớ

- JSON_CONTAINS(target, candidate[, path]) kiểm tra candidate có được chứa trong target hay không.
- Với object, candidate cần có đủ các cặp key/value; với array, mọi phần tử candidate phải được chứa.
- JSON_OVERLAPS(doc1, doc2) chỉ cần có ít nhất một phần tử hoặc cặp key/value chung.
- Dùng JSON_CONTAINS khi cần match tất cả; dùng JSON_OVERLAPS khi cần match bất kỳ.
- JSON_OVERLAPS có từ MySQL 8.0.17.
- So sánh JSON phải chú ý kiểu; string và number không phải cùng một giá trị.
- SQL NULL, JSON null và path không tồn tại là các trường hợp khác nhau.
- JSON path bắt đầu bằng $, array index bắt đầu từ 0.
- JSON_EXTRACT/-> trả JSON; ->> lấy giá trị đã unquote để dùng như SQL string.
- JSON_CONTAINS path không hỗ trợ wildcard; JSON_EXTRACT và JSON_TABLE phù hợp hơn để đọc nhiều phần tử.
- JSON_TABLE biến JSON array/object thành hàng và cột để JOIN, lọc, nhóm và tổng hợp.
- JSON_CONTAINS không biểu diễn điều kiện range như qty >= 2; dùng JSON_TABLE hoặc cột quan hệ.
- Generated column phù hợp index scalar path; MVI có thể index các scalar element trong JSON array trên InnoDB.
- Nếu cần foreign key, unique constraint hoặc cập nhật từng phần tử độc lập, cân nhắc mô hình bảng con.
- Dùng parameter binding và JSON_ARRAY/JSON_OBJECT để tạo candidate an toàn.

Chọn hàm JSON theo đúng câu hỏi nghiệp vụ: containment để kiểm tra cấu trúc cần có đầy đủ, overlap để kiểm tra phần giao, JSON path để định vị thành phần và JSON_TABLE để đưa phần tử về dạng quan hệ. Sau đó xác nhận hiệu năng bằng execution plan và chọn index hoặc mô hình dữ liệu phù hợp với tần suất truy vấn thực tế.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — JSON Search Functions: https://dev.mysql.com/doc/refman/8.0/en/json-search-functions.html
- MySQL 8.0 Reference Manual — JSON Utility Functions: https://dev.mysql.com/doc/refman/8.0/en/json-utility-functions.html
- MySQL 8.0 Reference Manual — JSON Table Functions: https://dev.mysql.com/doc/refman/8.0/en/json-table-functions.html
- MySQL 8.0 Reference Manual — JSON Path Syntax: https://dev.mysql.com/doc/refman/8.0/en/json-path-syntax.html
- MySQL 8.0 Reference Manual — Multi-Valued Indexes: https://dev.mysql.com/doc/refman/8.0/en/create-index.html#create-index-multi-valued
- MySQL 8.0 Reference Manual — Secondary Indexes and Generated Columns: https://dev.mysql.com/doc/refman/8.0/en/create-table-secondary-indexes.html

