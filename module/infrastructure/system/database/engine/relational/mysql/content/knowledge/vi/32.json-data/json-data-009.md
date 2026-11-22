# Generated column, functional index và chỉ mục cho đường dẫn JSON

MySQL lưu tài liệu JSON trong kiểu dữ liệu JSON, nhưng không tạo một B-tree tự động cho mọi thuộc tính hoặc đường dẫn bên trong tài liệu. Nếu truy vấn thường xuyên lọc theo \`$.brand\`, \`$.price\` hoặc kiểm tra một phần tử trong mảng \`$.tags\`, chỉ gọi JSON_EXTRACT trong WHERE có thể khiến MySQL phải đọc và đánh giá biểu thức trên nhiều hàng.

Có ba kỹ thuật quan trọng:

- **Generated column**: tạo một cột từ biểu thức, thường là đường dẫn JSON, rồi lập chỉ mục cho cột đó.
- **Functional index**: lập chỉ mục trực tiếp một biểu thức mà không cần khai báo cột sinh hiển thị trong schema.
- **Multi-valued index**: lập chỉ mục nhiều giá trị của một mảng JSON, để tìm hàng chứa một phần tử cụ thể.

Ba kỹ thuật có mục đích và giới hạn khác nhau. Generated column phù hợp khi đường dẫn JSON trở thành thuộc tính nghiệp vụ ổn định. Functional index phù hợp khi biểu thức được dùng lặp lại nhưng không cần cột phụ có tên. Multi-valued index phù hợp với mảng scalar có nhu cầu kiểm tra thành viên. Không kỹ thuật nào tự động thay thế mô hình quan hệ chuẩn hóa khi dữ liệu cần khóa ngoại, ràng buộc hoặc JOIN phức tạp.

Bài học thuộc phạm vi \`DATABASE_MYSQL\`: thiết kế index cho đường dẫn JSON, chọn kiểu dữ liệu và collation đúng, hiểu leftmost prefix và điều kiện biểu thức khớp index, đọc EXPLAIN để xác minh optimizer, đồng thời đánh giá chi phí ghi và giới hạn theo phiên bản MySQL.

## 1. Vì sao index thông thường không lập chỉ mục trực tiếp mọi thuộc tính JSON?

Ví dụ bảng sản phẩm:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(150) NOT NULL,
    attributes JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
~~~

Một tài liệu JSON có thể chứa nhiều thuộc tính:

~~~json
{
  "brand": "Northwind",
  "price": 129.90,
  "active": true,
  "tags": ["sale", "outdoor"],
  "warehouse": {
    "city": "Da Nang",
    "code": "DN-01"
  }
}
~~~

Truy vấn tìm sản phẩm theo brand:

~~~sql
SELECT product_id, product_name
FROM product
WHERE JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand')) = 'Northwind';
~~~

JSON column bảo đảm dữ liệu được lưu dưới dạng JSON hợp lệ, nhưng không tạo index riêng cho từng đường dẫn. Nếu không có cấu trúc index phù hợp, MySQL có thể phải đọc nhiều hàng rồi đánh giá JSON_EXTRACT.

Có thể xem kế hoạch:

~~~sql
EXPLAIN
SELECT product_id, product_name
FROM product
WHERE JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand')) = 'Northwind';
~~~

Nếu không có access path phù hợp, cột \`type\` có thể là \`ALL\`, cho biết optimizer dự kiến quét bảng. Với bảng lớn và truy vấn thường xuyên, đây là dấu hiệu nên đánh giá generated column hoặc functional index.

## 2. Ba kỹ thuật lập chỉ mục cho JSON

| Kỹ thuật | Cách hoạt động | Phù hợp với |
|---|---|---|
| Generated column + index | Trích một giá trị JSON thành cột có kiểu dữ liệu SQL rồi tạo index | Đường dẫn scalar ổn định, cần tên cột rõ ràng hoặc tái sử dụng trong nhiều truy vấn |
| Functional index | Index trực tiếp biểu thức, MySQL triển khai bằng hidden virtual generated column | Biểu thức cố định, không cần cột phụ hiển thị trong schema |
| Multi-valued index | Một hàng JSON array có thể tạo nhiều entry trong index | Tìm hàng chứa một phần tử trong mảng scalar |

Trước khi chọn, xác định:
- JSON path có ổn định hay thay đổi theo request?
- Giá trị là string, number, boolean, date hay array?
- Có cần JOIN, foreign key hoặc constraint trên giá trị đó không?
- Truy vấn là equality, range, membership hay sort?
- Có cần cột trích xuất xuất hiện trong SELECT và nhiều truy vấn khác?
- Phiên bản MySQL có hỗ trợ tính năng cần dùng không?

## 3. Generated column là gì?

Generated column là cột có giá trị được tính từ một biểu thức. Ứng dụng không cần tự ghi giá trị vào cột này như cột thông thường; MySQL tính giá trị theo biểu thức được khai báo.

Cú pháp:

~~~sql
column_name data_type
    [GENERATED ALWAYS] AS (expression)
    [VIRTUAL | STORED]
~~~

Hai loại:

- \`VIRTUAL\`: giá trị được tính khi đọc cột; không lưu giá trị trong phần hàng clustered record như cột STORED.
- \`STORED\`: giá trị được tính khi ghi và lưu trong hàng.

Nếu không chỉ định VIRTUAL hoặc STORED, generated column mặc định là VIRTUAL.

Ví dụ trích brand từ JSON:

~~~sql
ALTER TABLE product
    ADD COLUMN brand VARCHAR(64)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) VIRTUAL;
~~~

Cột brand là scalar SQL có kiểu VARCHAR. Ta có thể truy vấn như cột thông thường:

~~~sql
SELECT product_id, product_name, brand
FROM product
WHERE brand = 'Northwind';
~~~

### 3.1. Vì sao cần kiểu dữ liệu rõ ràng?

JSON_EXTRACT trả về giá trị JSON. Để index theo scalar, cần chuyển giá trị sang kiểu SQL thích hợp.

Ví dụ:
- Mã thương hiệu: VARCHAR.
- Giá tiền: DECIMAL.
- Số lượng: UNSIGNED hoặc kiểu integer phù hợp.
- Cờ trạng thái: TINYINT/BOOLEAN theo quy ước.
- Ngày: DATE hoặc DATETIME nếu dữ liệu có định dạng hợp lệ.

Không trích mọi giá trị thành VARCHAR nếu nghiệp vụ cần so sánh số hoặc ngày. So sánh chuỗi có thể cho thứ tự khác số học: \`'100'\` đứng trước \`'20'\` theo thứ tự từ điển.

### 3.2. VIRTUAL hay STORED?

| Tiêu chí | VIRTUAL | STORED |
|---|---|---|
| Giá trị trong clustered row | Không lưu như cột thường | Có lưu |
| Tính toán | Tính khi cần đọc, trừ trường hợp được materialize qua index | Tính khi ghi và lưu |
| Dung lượng hàng | Ít hơn | Tăng theo kích thước giá trị |
| Index | Có thể tạo secondary index trên virtual generated column với InnoDB | Có thể tạo index |
| Chi phí ghi | Vẫn phải tính và cập nhật index nếu có index | Tính giá trị và lưu cột, đồng thời cập nhật index nếu có |
| Khi phù hợp | Cột phụ chủ yếu phục vụ index hoặc truy vấn | Giá trị được đọc thường xuyên, tính toán tốn kém hoặc cần lưu rõ trong hàng |

Một điểm dễ nhầm: index trên VIRTUAL generated column vẫn lưu key value trong cấu trúc secondary index. VIRTUAL chỉ nói giá trị không được lưu trong clustered row như cột STORED; nó không có nghĩa index phải tính lại biểu thức bằng cách quét JSON cho mọi lần lookup.

STORED không mặc nhiên nhanh hơn trong mọi trường hợp. Nó tăng kích thước hàng và chi phí ghi. Hãy đo theo workload thực tế.

## 4. Tạo index trên generated column trích xuất JSON

Sau khi thêm brand, tạo index:

~~~sql
CREATE INDEX idx_product_brand
ON product (brand);
~~~

Truy vấn:

~~~sql
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind';
~~~

Optimizer có thể dùng idx_product_brand để định vị các hàng có brand phù hợp.

Kiểm tra:

~~~sql
EXPLAIN
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind';
~~~

Xem index:

~~~sql
SHOW INDEX FROM product;
~~~

### 4.1. Trích giá tiền thành DECIMAL

Thêm generated column cho giá:

~~~sql
ALTER TABLE product
    ADD COLUMN price DECIMAL(12, 2)
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.price'))
                AS DECIMAL(12, 2)
            )
        ) VIRTUAL,
    ADD INDEX idx_product_price (price);
~~~

Truy vấn range:

~~~sql
SELECT product_id, product_name, price
FROM product
WHERE price >= 100.00
  AND price < 200.00
ORDER BY price;
~~~

Index B-tree trên price có thể hỗ trợ equality, range và một số thứ tự truy cập. Khả năng tránh filesort còn phụ thuộc predicate, ORDER BY và kế hoạch thực tế.

### 4.2. Trích boolean

Ví dụ thuộc tính active:

~~~sql
ALTER TABLE product
    ADD COLUMN is_active TINYINT
        GENERATED ALWAYS AS (
            CASE
                WHEN JSON_EXTRACT(attributes, '$.active') = CAST('true' AS JSON)
                    THEN 1
                WHEN JSON_EXTRACT(attributes, '$.active') = CAST('false' AS JSON)
                    THEN 0
                ELSE NULL
            END
        ) VIRTUAL,
    ADD INDEX idx_product_active (is_active);
~~~

Cách này phân biệt true, false và trường hợp thiếu/không đúng kiểu bằng NULL. Có thể cần xác thực JSON schema ở tầng ghi để bảo đảm active luôn là boolean.

Không dùng phép CAST tùy tiện mà không xác định cách xử lý giá trị JSON sai kiểu. Dữ liệu không hợp lệ có thể dẫn đến warning, chuyển đổi ngoài dự kiến hoặc lỗi tùy expression và SQL mode.

## 5. Missing path, JSON null và SQL NULL

Khi index đường dẫn JSON, phải quyết định rõ cách biểu diễn các trường hợp:

1. Đường dẫn không tồn tại trong document.
2. Đường dẫn tồn tại với JSON null.
3. Đường dẫn tồn tại với giá trị scalar đúng kiểu.
4. Đường dẫn tồn tại nhưng sai kiểu, ví dụ string thay vì number.
5. Cột JSON nguồn là SQL NULL nếu schema cho phép.

Các trường hợp này không nên bị gom chung một cách vô thức. Ví dụ JSON_EXTRACT trả SQL NULL khi path không tồn tại; JSON null là một giá trị JSON và cách chuyển đổi qua JSON_UNQUOTE/CAST có thể khác với SQL NULL.

Có thể kiểm tra:

~~~sql
SELECT
    JSON_EXTRACT(attributes, '$.brand') AS brand_json,
    JSON_TYPE(JSON_EXTRACT(attributes, '$.brand')) AS brand_type,
    JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand')) AS brand_text
FROM product;
~~~

Nếu cần phân biệt missing với JSON null, dùng JSON_CONTAINS_PATH và JSON_TYPE:

~~~sql
SELECT
    JSON_CONTAINS_PATH(attributes, 'one', '$.brand') AS path_exists,
    JSON_TYPE(JSON_EXTRACT(attributes, '$.brand')) AS brand_type
FROM product;
~~~

Hãy thiết kế generated expression sao cho các trường hợp NULL có semantics đúng nghiệp vụ. Đặc biệt, kiểm thử document có path thiếu, JSON null và sai kiểu trước khi tạo index trên bảng production.

## 6. Functional index là gì?

Functional index cho phép lập chỉ mục trực tiếp một biểu thức thay vì phải tạo một generated column có tên hiển thị.

MySQL hỗ trợ functional key parts từ MySQL 8.0.13. Functional index được triển khai nội bộ bằng hidden virtual generated column.

Ví dụ:

~~~sql
CREATE INDEX idx_product_brand_expr
ON product (
    (
        CAST(
            attributes->>'$.brand'
            AS CHAR(64) CHARACTER SET utf8mb4
        ) COLLATE utf8mb4_0900_ai_ci
    )
);
~~~

Lưu ý cú pháp có hai cặp ngoặc quanh biểu thức key part. Phần biểu thức phải được đặt trong ngoặc riêng.

Truy vấn cần dùng biểu thức khớp với biểu thức index:

~~~sql
SELECT product_id, product_name
FROM product
WHERE (
    CAST(
        attributes->>'$.brand'
        AS CHAR(64) CHARACTER SET utf8mb4
    ) COLLATE utf8mb4_0900_ai_ci
) = 'Northwind';
~~~

Trong MySQL, \`->>\` là dạng rút gọn của JSON_UNQUOTE(JSON_EXTRACT()). Tuy nhiên, để optimizer nhận diện functional index ổn định, hãy dùng biểu thức tương ứng cùng kiểu kết quả và collation như lúc tạo index. Không tự ý đổi CAST, chiều dài CHAR hoặc COLLATE rồi kỳ vọng index luôn được nhận diện.

### 6.1. Vì sao phải CAST kết quả JSON?

Biểu thức JSON_UNQUOTE/->> có thể có kiểu kết quả chuỗi dài như LONGTEXT. Functional key part không thể dùng kiểu không phù hợp với giới hạn index như vậy. CAST sang CHAR với độ dài hữu hạn giúp xác định kiểu key có thể lập chỉ mục.

Độ dài phải được chọn theo miền dữ liệu:
- Quá ngắn có thể cắt giá trị và làm thay đổi semantics.
- Quá dài làm index rộng và tăng chi phí lưu trữ.
- Charset và collation ảnh hưởng so sánh và kích thước key.

Nếu brand có giới hạn 64 ký tự theo nghiệp vụ, CHAR(64) có thể hợp lý. Nếu giá trị dài hoặc cần prefix semantics, xem xét generated column và kiểu dữ liệu phù hợp; functional key part không hỗ trợ khai báo prefix length như index cột thông thường.

### 6.2. Functional index hay generated column?

| Tiêu chí | Functional index | Generated column + index |
|---|---|---|
| Cột phụ hiển thị | Không; hidden virtual generated column | Có cột được đặt tên |
| Truy vấn | Cần dùng biểu thức tương ứng để optimizer nhận diện | Có thể truy vấn trực tiếp bằng tên cột |
| Tái sử dụng | Biểu thức có thể lặp lại trong SQL | Cột có thể dùng trong SELECT, JOIN, WHERE và ORDER BY |
| Kiểu dữ liệu | Phải xác định trong biểu thức, thường cần CAST | Khai báo kiểu cột rõ ràng |
| Bảo trì schema | Ít cột phụ hơn | Dễ đọc schema và mô tả ý nghĩa thuộc tính |
| Phù hợp | Một biểu thức cố định, ít cần expose như thuộc tính | Đường dẫn JSON là thuộc tính nghiệp vụ dùng ở nhiều nơi |

Functional index không phải cách để index bất kỳ stored function tùy ý. Biểu thức functional key part chịu các giới hạn tương tự generated column: không dùng subquery, biến, tham số, stored function hoặc loadable function không được phép, và phải tuân thủ các hạn chế về kiểu/độ dài key.

## 7. Điều kiện biểu thức phải khớp functional index

Optimizer chỉ có thể dùng functional index khi biểu thức truy vấn tương ứng với key part được index theo các quy tắc nhận diện biểu thức và kiểu kết quả của MySQL.

Ví dụ index:

~~~sql
CREATE INDEX idx_product_price_expr
ON product (
    (
        CAST(
            attributes->>'$.price'
            AS DECIMAL(12, 2)
        )
    )
);
~~~

Biểu thức truy vấn:

~~~sql
SELECT product_id
FROM product
WHERE CAST(
    attributes->>'$.price'
    AS DECIMAL(12, 2)
) >= 100.00;
~~~

Nếu truy vấn viết thành:

~~~sql
WHERE CAST(attributes->>'$.price' AS CHAR(30)) >= '100'
~~~

thì kiểu dữ liệu và semantics đã khác; functional index trên DECIMAL không phải access path tương ứng.

Các thay đổi có thể khiến optimizer không nhận diện biểu thức:
- Thay JSON path.
- Thay CAST type hoặc precision/scale.
- Thay collation.
- Thay cách chuẩn hóa string.
- Dùng hàm bọc khác.
- Thay thứ tự hoặc hình thức biểu thức trong cách không được optimizer xem là tương đương.

Khi biểu thức là logic dùng chung, generated column có tên thường dễ bảo trì hơn. Truy vấn \`WHERE price >= 100\` tránh lặp lại expression dài và giảm nguy cơ lệch cú pháp.

## 8. Chỉ mục cho đường dẫn JSON lồng nhau

JSON path có thể trỏ tới thuộc tính lồng nhau:

~~~json
{
  "warehouse": {
    "city": "Da Nang",
    "code": "DN-01"
  }
}
~~~

Trích city:

~~~sql
ALTER TABLE product
    ADD COLUMN warehouse_city VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(
                JSON_EXTRACT(attributes, '$.warehouse.city')
            )
        ) VIRTUAL,
    ADD INDEX idx_product_warehouse_city (warehouse_city);
~~~

Truy vấn:

~~~sql
SELECT product_id, product_name
FROM product
WHERE warehouse_city = 'Da Nang';
~~~

JSON path trong generated expression là hằng số. Nếu ứng dụng cần tìm theo nhiều path tùy ý, một index cho một path cố định không thể tự động phục vụ mọi path.

### 8.1. Chỉ mục cho nhiều đường dẫn

Nếu truy vấn thường xuyên dùng brand, price và warehouse.city, có thể tạo nhiều generated columns/index:

~~~sql
ALTER TABLE product
    ADD COLUMN brand VARCHAR(64)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) VIRTUAL,
    ADD COLUMN price DECIMAL(12, 2)
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.price'))
                AS DECIMAL(12, 2)
            )
        ) VIRTUAL,
    ADD COLUMN warehouse_city VARCHAR(80)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.warehouse.city'))
        ) VIRTUAL,
    ADD INDEX idx_product_brand (brand),
    ADD INDEX idx_product_price (price),
    ADD INDEX idx_product_city (warehouse_city);
~~~

Không lập chỉ mục mọi path chỉ vì nó tồn tại trong JSON. Mỗi index làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE. Chỉ index các path có truy vấn thường xuyên và có lợi ích đo được.

### 8.2. Composite index trên các generated columns

Nếu truy vấn luôn lọc brand và price:

~~~sql
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind'
  AND price >= 100.00
  AND price < 200.00;
~~~

Có thể đánh giá composite index:

~~~sql
CREATE INDEX idx_product_brand_price
ON product (brand, price);
~~~

Index ghép theo equality trước, range sau có thể định vị brand rồi quét khoảng price. Quy tắc leftmost prefix vẫn áp dụng như index trên cột thường.

Nếu truy vấn chỉ lọc price mà không có brand, index (brand, price) không có tiền tố trái phù hợp để định vị trực tiếp theo price. Có thể cần index riêng nếu workload thực sự cần.

## 9. Multi-valued index cho JSON array

Generated column scalar và functional index thường phù hợp khi mỗi hàng có một giá trị cho một path. Nhưng JSON array có nhiều phần tử:

~~~json
{
  "tags": ["sale", "outdoor", "featured"]
}
~~~

Nếu cần tìm sản phẩm có tag sale, index scalar thông thường trên toàn JSON document không giải quyết trực tiếp bài toán membership.

InnoDB hỗ trợ multi-valued index từ MySQL 8.0.17. Một hàng có thể tạo nhiều entry index, tương ứng các phần tử trong JSON array.

Ví dụ:

~~~sql
CREATE INDEX idx_product_tags
ON product (
    (
        CAST(attributes->'$.tags' AS CHAR(32) ARRAY)
    )
);
~~~

Biểu thức CAST ... AS ... ARRAY đánh dấu key part là multi-valued. Ví dụ này giả định tags là mảng JSON chứa các string có độ dài phù hợp.

Truy vấn membership:

~~~sql
SELECT product_id, product_name
FROM product
WHERE 'sale' MEMBER OF (attributes->'$.tags');
~~~

Optimizer có thể dùng multi-valued index để tìm hàng có phần tử phù hợp. Cú pháp và khả năng tối ưu phụ thuộc phiên bản MySQL; xác minh bằng EXPLAIN trên đúng server.

### 9.1. JSON_CONTAINS và JSON_OVERLAPS

Các predicate kiểm tra phần tử/mảng cũng có thể tận dụng multi-valued index trong các hình thức được MySQL hỗ trợ.

Tìm một phần tử:

~~~sql
SELECT product_id
FROM product
WHERE JSON_CONTAINS(
    attributes->'$.tags',
    JSON_QUOTE('sale')
);
~~~

Tìm hàng có ít nhất một phần tử trùng:

~~~sql
SELECT product_id
FROM product
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
~~~

JSON_CONTAINS kiểm tra candidate có được chứa trong target theo quy tắc JSON containment. JSON_OVERLAPS kiểm tra hai tài liệu có ít nhất một giá trị chung. Không thay thế hai hàm bằng nhau một cách máy móc.

### 9.2. Kiểu phần tử phải phù hợp

Nếu tags là mảng số:

~~~json
{
  "tag_ids": [10, 20, 30]
}
~~~

Có thể lập index theo UNSIGNED ARRAY:

~~~sql
CREATE INDEX idx_product_tag_ids
ON product (
    (
        CAST(attributes->'$.tag_ids' AS UNSIGNED ARRAY)
    )
);
~~~

Predicate cần dùng giá trị số đúng kiểu:

~~~sql
SELECT product_id
FROM product
WHERE 20 MEMBER OF (attributes->'$.tag_ids');
~~~

Không trộn string "20" và number 20 trong cùng một mảng nếu ứng dụng cần semantics nhất quán. Kiểu CAST, kiểu literal và kiểu JSON array cần được thiết kế thống nhất.

### 9.3. Multi-valued index không phải index covering thông thường

Một hàng có thể tạo nhiều index entry, nên multi-valued index có giới hạn khác secondary index B-tree thông thường. Nó chủ yếu giúp tìm hàng theo membership. Không giả định có thể dùng nó để trả toàn bộ cột SELECT mà không truy cập hàng gốc, hoặc để cung cấp thứ tự ORDER BY.

Nếu truy vấn cần trả nhiều thuộc tính và sắp xếp theo cột khác, EXPLAIN có thể cho thấy bước truy cập hàng bổ sung hoặc filesort.

## 10. Giới hạn của multi-valued index

Các giới hạn cần ghi nhớ khi thiết kế:
- Chỉ hỗ trợ InnoDB.
- Cần MySQL 8.0.17 trở lên.
- Mỗi index chỉ có một multi-valued key part.
- Mảng cần được CAST sang một kiểu scalar phù hợp.
- Không phải index covering/index-only scan.
- Không dùng để hỗ trợ range scan thông thường hoặc thứ tự sắp xếp như B-tree scalar.
- Không dùng làm foreign key.
- Không biến mảng JSON thành quan hệ có constraint/unique cho từng phần tử.
- Phải kiểm tra các kiểu JSON và giá trị NULL/mảng rỗng theo đúng phiên bản.

Với mảng chứa object phức tạp, quan hệ nhiều-nhiều hoặc cần thuộc tính riêng cho từng phần tử, bảng con chuẩn hóa thường phù hợp hơn:

~~~sql
CREATE TABLE product_tag (
    product_id BIGINT UNSIGNED NOT NULL,
    tag VARCHAR(32) NOT NULL,
    PRIMARY KEY (product_id, tag),
    KEY idx_product_tag_tag_product (tag, product_id),
    CONSTRAINT fk_product_tag_product
        FOREIGN KEY (product_id)
        REFERENCES product(product_id)
) ENGINE = InnoDB;
~~~

Mô hình quan hệ hỗ trợ foreign key, unique constraint, JOIN và truy vấn tổng hợp linh hoạt. Multi-valued index là lựa chọn tối ưu truy vấn membership trên JSON array, không phải lý do để đưa mọi quan hệ nhiều-nhiều vào JSON.

## 11. JSON path và kiểu dữ liệu: những lựa chọn quan trọng

| Dữ liệu trong JSON | Kiểu generated column/index thường cân nhắc | Lưu ý |
|---|---|---|
| Mã/tên | VARCHAR với charset/collation rõ | Chọn chiều dài phù hợp và thống nhất collation |
| Giá tiền | DECIMAL(p,s) | Tránh so sánh số dưới dạng chuỗi |
| Số lượng/ID | INT/BIGINT UNSIGNED nếu miền giá trị phù hợp | Xác thực giá trị âm và overflow |
| Boolean | TINYINT hoặc kiểu biểu diễn rõ | Phân biệt false, missing và JSON null |
| Ngày | DATE/DATETIME | Kiểm tra format và timezone |
| Danh sách tag string | Multi-valued CHAR ARRAY | Kiểm tra độ dài và collation |
| Danh sách ID số | Multi-valued UNSIGNED ARRAY | Dùng literal số và JSON number nhất quán |

### 11.1. String và collation

Khi trích JSON string, cần xác định so sánh có phân biệt hoa/thường và dấu hay không. Ví dụ:
- utf8mb4_0900_ai_ci: accent-insensitive, case-insensitive.
- utf8mb4_0900_as_cs: accent-sensitive, case-sensitive.
- Collation khác có thể có quy tắc khác.

Generated column khai báo collation tường minh giúp semantics của index và predicate rõ ràng. Nếu ứng dụng yêu cầu mã định danh phân biệt hoa thường, không dùng collation case-insensitive một cách vô tình.

### 11.2. Numeric conversion

Không index giá tiền như VARCHAR nếu truy vấn dùng phép so sánh số:

~~~sql
-- So sánh chuỗi có thể khác thứ tự số:
WHERE price_text >= '100'
~~~

Dùng DECIMAL:

~~~sql
WHERE price >= 100.00
~~~

Chọn precision/scale đủ miền giá trị. CAST có thể làm tròn hoặc báo warning khi dữ liệu đầu vào không hợp lệ; cần validate document ở nơi ghi.

### 11.3. Date và timezone

JSON có thể lưu ngày dưới dạng chuỗi ISO. Nếu cần lọc theo ngày, trích sang DATE hoặc DATETIME bằng biểu thức được hỗ trợ và định dạng chuẩn. Nếu giá trị mang timezone, hãy thống nhất chuẩn lưu (thường UTC) trước khi CAST. Không dựa vào implicit conversion của chuỗi tùy định dạng.

## 12. Index JSON với generated column và leftmost prefix

Generated column là cột SQL nên mọi quy tắc index thông thường vẫn áp dụng.

Ví dụ:

~~~sql
ALTER TABLE product
    ADD COLUMN brand VARCHAR(64)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) VIRTUAL,
    ADD COLUMN price DECIMAL(12, 2)
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.price'))
                AS DECIMAL(12, 2)
            )
        ) VIRTUAL,
    ADD INDEX idx_product_brand_price (brand, price);
~~~

Index (brand, price):
- Hỗ trợ lọc brand.
- Hỗ trợ lọc brand và price.
- Có thể hỗ trợ range trên price sau equality brand.
- Không có tiền tố trái price riêng.

Nếu có truy vấn chỉ lọc price, đánh giá index (price) riêng. Không thêm index trước khi xem workload.

## 13. Covering index và truy vấn JSON

Ví dụ:

~~~sql
SELECT product_id, brand, price
FROM product
WHERE brand = 'Northwind'
  AND price >= 100.00;
~~~

Index (brand, price) trên InnoDB secondary index chứa primary key của hàng. Vì product_id là PRIMARY KEY và brand/price nằm trong index, kế hoạch có thể trở thành covering cho truy vấn này. EXPLAIN có thể hiển thị \`Using index\`.

Nhưng nếu SELECT thêm product_name không nằm trong index:

~~~sql
SELECT product_id, product_name, brand, price
FROM product
WHERE brand = 'Northwind';
~~~

MySQL có thể phải truy cập clustered row để lấy product_name. Không nên mở rộng index bằng mọi cột chỉ để tránh một lần lookup nếu đổi lại index quá rộng và tăng chi phí ghi.

Functional index cũng có thể phục vụ access path, nhưng việc covering và cách EXPLAIN thể hiện phụ thuộc biểu thức và phiên bản. Generated column có tên thường dễ đọc hơn khi cần trả giá trị trích xuất trong nhiều truy vấn.

## 14. Kiểm tra optimizer có dùng index hay không

Sau khi tạo generated column hoặc functional index, đừng dừng ở việc DDL thành công. Cần kiểm tra kế hoạch.

### 14.1. EXPLAIN

~~~sql
EXPLAIN
SELECT product_id, product_name
FROM product
WHERE brand = 'Northwind';
~~~

Các trường cần xem:
- \`type\`: access type, ví dụ ref/range hay ALL.
- \`possible_keys\`: index có thể được cân nhắc.
- \`key\`: index được chọn.
- \`key_len\`: độ dài phần khóa được dùng.
- \`rows\`: số hàng ước lượng.
- \`filtered\`: tỷ lệ hàng còn lại ước lượng.
- \`Extra\`: Using index, Using where, Using filesort và ghi chú khác.

Index có trong possible_keys nhưng không nằm ở key nghĩa là optimizer không chọn index đó cho kế hoạch hiện tại. Đây không nhất thiết là lỗi; full scan có thể rẻ hơn nếu bảng nhỏ hoặc predicate trả về nhiều hàng.

### 14.2. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT product_id
FROM product
WHERE price >= 100.00
  AND price < 200.00;
~~~

TREE giúp xem iterator và thứ tự thực thi. Dùng nó để xác nhận range scan có diễn ra trên index price hay không.

### 14.3. EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT product_id
FROM product
WHERE brand = 'Northwind'
  AND price >= 100.00;
~~~

EXPLAIN ANALYZE thực thi câu SELECT và báo số hàng/thời gian thực tế. So sánh estimated rows với actual rows để biết thống kê có phản ánh phân bố dữ liệu không.

Chỉ chạy trên môi trường phù hợp nếu truy vấn nặng. EXPLAIN ANALYZE không phải lệnh chỉ đọc kế hoạch; nó thực thi truy vấn.

### 14.4. ANALYZE TABLE

Sau khi nạp lượng dữ liệu lớn hoặc thay đổi phân bố JSON đáng kể:

~~~sql
ANALYZE TABLE product;
~~~

Lệnh cập nhật thống kê optimizer. Sau đó chạy lại EXPLAIN để kiểm tra ước lượng và lựa chọn index. ANALYZE TABLE không bảo đảm optimizer sẽ chọn index mới; nó chỉ cập nhật thông tin phục vụ ước lượng chi phí.

## 15. Generated column và functional index có thể không được dùng khi predicate không khớp

Ví dụ generated column brand được định nghĩa:

~~~sql
brand VARCHAR(64)
GENERATED ALWAYS AS (
    JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
) VIRTUAL
~~~

Truy vấn rõ ràng nhất:

~~~sql
WHERE brand = 'Northwind'
~~~

Optimizer cũng có thể nhận diện biểu thức tương ứng trong một số trường hợp, nhưng cách an toàn và dễ bảo trì là truy vấn trực tiếp generated column.

Nếu query dùng path khác:

~~~sql
WHERE JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.manufacturer')) = 'Northwind'
~~~

thì đó là thuộc tính khác; index brand không thể thay thế.

Nếu query bọc thêm hàm:

~~~sql
WHERE LOWER(brand) = 'northwind'
~~~

index brand thông thường có thể không phục vụ trực tiếp biểu thức LOWER(brand), trừ khi có functional index phù hợp hoặc thiết kế chuẩn hóa khác. Hãy kiểm tra EXPLAIN thay vì suy đoán.

## 16. Dữ liệu JSON không đồng nhất và chiến lược validation

Index trên JSON path giả định dữ liệu ở path đó có miền giá trị phù hợp. Nếu một số hàng lưu:

~~~json
{"price": 129.90}
~~~

nhưng hàng khác lưu:

~~~json
{"price": "unknown"}
~~~

CAST sang DECIMAL có thể tạo warning hoặc kết quả chuyển đổi ngoài dự kiến. Điều này làm semantics truy vấn khó kiểm soát.

Các biện pháp:
- Validate JSON ở tầng ứng dụng trước khi ghi.
- Dùng JSON Schema validation nếu phù hợp phiên bản và yêu cầu.
- Dùng CHECK constraint để kiểm tra điều kiện đơn giản khi có thể.
- Định nghĩa rõ kiểu JSON cho từng path.
- Quy định cách xử lý missing và JSON null.
- Kiểm tra dữ liệu cũ trước khi thêm generated column/index.
- Theo dõi warning và lỗi khi migrate.

Ví dụ kiểm tra kiểu:

~~~sql
SELECT product_id
FROM product
WHERE JSON_TYPE(JSON_EXTRACT(attributes, '$.price')) NOT IN ('INTEGER', 'DOUBLE', 'DECIMAL');
~~~

Predicate này là ví dụ kiểm tra dữ liệu; cần bổ sung xử lý path missing/NULL tùy quy tắc dữ liệu. Không giả định mọi giá trị JSON số có cùng JSON_TYPE trên mọi cách tạo document.

## 17. Chi phí ghi và vận hành

Mỗi generated column/index bổ sung đều có chi phí.

### 17.1. INSERT

Khi thêm sản phẩm, MySQL cần:
- Ghi JSON document.
- Tính generated expression.
- Ghi entry vào secondary index.
- Với multi-valued index, ghi entry cho từng phần tử array.

Một document có mảng 50 phần tử có thể tạo nhiều entry index hơn document có mảng 2 phần tử.

### 17.2. UPDATE

Khi cập nhật attributes:
- Generated expressions liên quan có thể cần đánh giá lại.
- Các index tương ứng phải được duy trì nếu giá trị key thay đổi.
- Multi-valued index có thể phải cập nhật nhiều entry khi array thay đổi.

Đừng giả định chỉ thay một thuộc tính JSON thì chi phí luôn nhỏ; cần đo theo kích thước document và số index.

### 17.3. Dung lượng

Generated column STORED làm tăng dung lượng hàng. Secondary index làm tăng dung lượng index. Functional index cũng cần lưu key entry dù không có cột phụ hiển thị. Multi-valued index có thể tăng mạnh theo tổng số phần tử trong các array.

Theo dõi:
- DATA_LENGTH và INDEX_LENGTH.
- Kích thước bảng trước/sau.
- Thời gian INSERT/UPDATE.
- Buffer pool pressure.
- Thời gian build index và lock/DDL impact.

## 18. Khi nào nên dùng bảng con thay vì JSON array?

Multi-valued index tiện cho membership đơn giản, nhưng JSON array không phải quan hệ nhiều-nhiều đầy đủ.

Dùng bảng con khi:
- Mỗi phần tử cần ID riêng.
- Cần foreign key.
- Cần unique constraint trên cặp product/tag.
- Cần thuộc tính cho từng liên kết.
- Cần JOIN, aggregate hoặc cập nhật từng phần tử thường xuyên.
- Cần kiểm soát quyền hoặc lifecycle của phần tử độc lập.

Ví dụ product_tag ở mục 10 có thể hỗ trợ index (tag, product_id), foreign key và unique key. Nếu chỉ cần lưu một danh sách nhãn ít thay đổi và truy vấn membership đơn giản, multi-valued index có thể là lựa chọn gọn hơn.

Quyết định dựa trên yêu cầu dữ liệu và truy vấn, không chỉ số lượng phần tử.

## 19. Version và khả năng hỗ trợ

| Tính năng | Phiên bản MySQL |
|---|---|
| Generated columns | MySQL 5.7 trở lên |
| Functional key parts | MySQL 8.0.13 trở lên |
| Multi-valued indexes | MySQL 8.0.17 trở lên |
| JSON_OVERLAPS | MySQL 8.0.17 trở lên |
| EXPLAIN ANALYZE | MySQL 8.0.18 trở lên |

Các bản MySQL 8.0 và 8.4 có khác biệt nhỏ theo phiên bản về cú pháp, optimizer và giới hạn. Với MariaDB hoặc dịch vụ tương thích MySQL, không suy luận tính năng tương đương chỉ từ cú pháp gần giống.

Kiểm tra runtime:

~~~sql
SELECT VERSION();
~~~

Trước khi triển khai functional index hoặc multi-valued index, kiểm tra tài liệu của đúng phiên bản server và chạy DDL thử trên staging.

## 20. Quy trình chọn kỹ thuật index JSON

1. Thu thập truy vấn thực tế và xác định JSON path được dùng trong WHERE/JOIN/ORDER BY.
2. Xác định path là scalar hay array.
3. Xác định kiểu dữ liệu và miền giá trị của JSON path.
4. Xác định semantics của missing path, JSON null và SQL NULL.
5. Nếu path scalar ổn định và dùng ở nhiều nơi, tạo generated column có kiểu SQL rõ ràng.
6. Nếu biểu thức cố định và không cần cột phụ, cân nhắc functional index (MySQL 8.0.13+).
7. Nếu path là mảng scalar và truy vấn membership, cân nhắc multi-valued index (MySQL 8.0.17+).
8. Nếu array cần foreign key, unique constraint hoặc thuộc tính từng phần tử, dùng bảng con quan hệ.
9. Chọn charset/collation cho string và precision/scale cho số.
10. Kiểm tra dữ liệu hiện có trước khi thêm CAST/index.
11. Tạo index trên staging và kiểm tra EXPLAIN.
12. Dùng EXPLAIN ANALYZE để so estimated rows với actual rows.
13. Đánh giá ORDER BY, covering, range và leftmost prefix.
14. Đo chi phí INSERT/UPDATE và dung lượng index.
15. Chỉ triển khai production sau khi có kế hoạch DDL, backup và theo dõi.
16. Theo dõi kế hoạch sau khi phân bố JSON thay đổi.

## 21. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| JSON column tự có index cho mọi path | JSON type chỉ bảo đảm lưu JSON hợp lệ | Tạo generated column, functional index hoặc multi-valued index |
| Index JSON_EXTRACT trả về JSON trực tiếp | Kiểu JSON không phải scalar key thông thường | CAST/unquote sang kiểu SQL phù hợp |
| Dùng VARCHAR cho giá tiền | So sánh theo chuỗi thay vì số | Dùng DECIMAL |
| Generated column VIRTUAL không thể index | Nhầm VIRTUAL với không có index storage | InnoDB hỗ trợ secondary index trên virtual generated column |
| STORED luôn nhanh hơn VIRTUAL | Bỏ qua dung lượng và chi phí ghi | Chọn theo read/write workload |
| Functional index chấp nhận mọi biểu thức | Functional key part có giới hạn như generated column | Kiểm tra expression restrictions |
| Functional index không cần CAST JSON string | Biểu thức có thể là kiểu chuỗi dài không indexable | CAST sang CHAR có độ dài và collation rõ |
| Biểu thức truy vấn khác vẫn dùng functional index | Optimizer cần nhận diện expression và result type phù hợp | Dùng biểu thức khớp hoặc generated column có tên |
| Một index scalar phục vụ JSON array | Mảng có nhiều phần tử | Dùng multi-valued index hoặc bảng con |
| Multi-valued index có thể dùng cho ORDER BY | Nó phục vụ membership, không cung cấp thứ tự nghiệp vụ | Dùng index scalar phù hợp cho sort |
| MVI thay thế bảng nhiều-nhiều | Không có đầy đủ FK/constraint và quan hệ từng phần tử | Chuẩn hóa thành bảng liên kết khi cần |
| Index được tạo nghĩa là optimizer sẽ dùng | Cost model có thể chọn full scan hoặc access path khác | Kiểm tra EXPLAIN/EXPLAIN ANALYZE |
| JSON null giống missing path | Hai trường hợp có semantics khác | Kiểm tra JSON_CONTAINS_PATH và JSON_TYPE |
| Thêm nhiều index không ảnh hưởng ghi | Mỗi index phải được duy trì | Đo INSERT/UPDATE, dung lượng và cache |
| Functional index có sẵn ở mọi MySQL 8.0 | Cần ít nhất 8.0.13 | Kiểm tra VERSION() |
| Multi-valued index có sẵn từ MySQL 8.0.13 | Cần ít nhất 8.0.17 | Kiểm tra VERSION() và engine |

## 22. Bài tập thực hành

### Bài 1: Generated column cho brand

Tạo bảng product với attributes JSON. Thêm generated column brand kiểu VARCHAR và index. Chèn ít nhất 100.000 sản phẩm, chạy truy vấn theo brand và so sánh EXPLAIN trước/sau index.

### Bài 2: Generated column cho price

Trích price thành DECIMAL(12,2), tạo index và chạy truy vấn range. Thử dữ liệu price là number, string số, string không hợp lệ và path thiếu. Ghi lại warning/error và quyết định validation.

### Bài 3: VIRTUAL so với STORED

Tạo hai bảng có cùng JSON document, một bảng dùng VIRTUAL generated column và một bảng dùng STORED. Đo dung lượng, thời gian đọc và ghi trên workload đại diện. Tạo index ở cả hai để so sánh.

### Bài 4: Functional index cho JSON path

Trên MySQL 8.0.13+, tạo functional index cho brand bằng CAST và collation tường minh. Viết truy vấn dùng đúng biểu thức. Sau đó thay CAST/collation/path và quan sát EXPLAIN.

### Bài 5: Composite index trên generated columns

Tạo brand và price generated columns, tạo index (brand, price). So sánh truy vấn brand-only, brand + price range và price-only. Giải thích leftmost prefix.

### Bài 6: JSON path lồng nhau

Trích warehouse.city thành generated column. Tạo index và truy vấn theo city. Kiểm tra document thiếu warehouse, thiếu city và city là JSON null.

### Bài 7: Multi-valued index cho tags

Trên MySQL 8.0.17+, tạo MVI trên CAST(attributes->'$.tags' AS CHAR(32) ARRAY). Chạy MEMBER OF, JSON_CONTAINS và JSON_OVERLAPS. Dùng EXPLAIN để kiểm tra access path.

### Bài 8: Multi-valued index cho số

Tạo mảng tag_ids gồm JSON number. Tạo MVI với UNSIGNED ARRAY và truy vấn membership bằng literal số. Thử dữ liệu có string thay vì number và đánh giá tính nhất quán.

### Bài 9: So sánh MVI với bảng liên kết

Tạo product_tag với primary/foreign key và index tag/product. So sánh truy vấn membership, cập nhật danh sách, constraint và chi phí ghi với MVI.

### Bài 10: Chi phí index

Đo INSERT/UPDATE trên bảng chỉ có JSON, bảng có generated columns/index và bảng có MVI. So sánh dung lượng, thời gian ghi và độ trễ truy vấn.

### Bài 11: Đọc kế hoạch

Chạy EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE cho mỗi kiểu index. Ghi lại key, estimated rows, actual rows, loops, filesort và số hàng trả về.

### Bài 12: Thiết kế production

Chọn ba JSON path trong một workload thực tế. Đề xuất generated column, functional index, MVI hoặc bảng con cho từng path. Giải thích kiểu dữ liệu, collation, version, truy vấn, chi phí ghi và phương án migration.

## 23. Checklist trước khi triển khai

- [ ] Đã xác định các JSON path được truy vấn thường xuyên.
- [ ] Đã phân biệt scalar path với JSON array.
- [ ] Đã chọn generated column, functional index hoặc multi-valued index theo đúng bài toán.
- [ ] Đã xác định kiểu dữ liệu SQL và miền giá trị của path.
- [ ] Đã kiểm tra missing path, JSON null, SQL NULL và sai kiểu.
- [ ] Đã chọn charset/collation cho string.
- [ ] Đã chọn DECIMAL/integer thay vì string cho giá trị số.
- [ ] Đã biết VIRTUAL là mặc định và STORED lưu giá trị trong hàng.
- [ ] Đã hiểu index trên VIRTUAL generated column vẫn có entry trong secondary index.
- [ ] Đã kiểm tra biểu thức functional index khớp predicate truy vấn.
- [ ] Đã kiểm tra giới hạn functional key parts và CAST chiều dài hữu hạn.
- [ ] Đã xác minh phiên bản hỗ trợ functional index.
- [ ] Đã xác minh phiên bản và InnoDB hỗ trợ multi-valued index.
- [ ] Đã kiểm tra mảng chứa scalar đúng kiểu.
- [ ] Đã hiểu MVI không phải covering index và không thay thế foreign key.
- [ ] Đã cân nhắc bảng con quan hệ khi cần constraint/JOIN phức tạp.
- [ ] Đã kiểm tra leftmost prefix nếu tạo composite index trên generated columns.
- [ ] Đã chạy EXPLAIN và EXPLAIN ANALYZE trên dữ liệu đại diện.
- [ ] Đã đo chi phí INSERT/UPDATE và dung lượng.
- [ ] Đã kiểm tra DDL, backup và kế hoạch theo dõi sau triển khai.

## 24. Kết luận

MySQL không tự tạo B-tree cho mọi đường dẫn trong JSON document. Với một scalar path ổn định, generated column có kiểu SQL rõ ràng rồi lập index thường dễ đọc và bảo trì. Functional index (MySQL 8.0.13+) giúp index biểu thức cố định mà không cần cột phụ hiển thị, nhưng truy vấn phải dùng biểu thức và kiểu kết quả tương ứng. Với JSON array chứa scalar, multi-valued index của InnoDB (MySQL 8.0.17+) có thể tăng tốc MEMBER OF, JSON_CONTAINS hoặc JSON_OVERLAPS trong các trường hợp được hỗ trợ.

Chọn kiểu dữ liệu và collation trước khi tạo index; phân biệt path thiếu, JSON null và SQL NULL; xác thực dữ liệu để CAST không tạo kết quả ngoài ý muốn. Generated column/index vẫn phải trả chi phí ghi và dung lượng. Multi-valued index hỗ trợ membership nhưng không thay thế bảng quan hệ khi cần foreign key, unique constraint hoặc quản lý từng phần tử. Cuối cùng, xác minh bằng EXPLAIN và EXPLAIN ANALYZE trên dữ liệu thực tế thay vì chỉ dựa vào việc DDL tạo index thành công.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – JSON Data Type](https://dev.mysql.com/doc/refman/8.4/en/json.html)
- [MySQL 8.4 Reference Manual – JSON Search Functions](https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html)
- [MySQL 8.4 Reference Manual – Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html)
- [MySQL 8.4 Reference Manual – Secondary Indexes and Generated Columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html)
- [MySQL 8.4 Reference Manual – Functional Key Parts](https://dev.mysql.com/doc/refman/8.4/en/create-index.html)
- [MySQL 8.4 Reference Manual – Multi-Valued Indexes](https://dev.mysql.com/doc/refman/8.4/en/create-index.html#create-index-multi-valued)
- [MySQL 8.4 Reference Manual – JSON Table Functions and Operators](https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Index Types](https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html)

