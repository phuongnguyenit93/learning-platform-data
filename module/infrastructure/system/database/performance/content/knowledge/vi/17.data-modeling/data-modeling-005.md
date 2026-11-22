# Quan hệ, JSON và mô hình thuộc tính linh hoạt: chi phí truy vấn

Khi thiết kế dữ liệu, có ba cách biểu diễn thường gặp: đặt thuộc tính thành các cột quan hệ có kiểu rõ ràng, lưu một phần dữ liệu trong tài liệu JSON, hoặc dùng mô hình thuộc tính linh hoạt như Entity-Attribute-Value (EAV). Mỗi cách giải quyết một nhu cầu khác nhau. Cột quan hệ thuận lợi cho lọc, nối, ràng buộc và thống kê; JSON giúp lưu cấu trúc thay đổi theo loại đối tượng; EAV biểu diễn tập thuộc tính thưa hoặc do người dùng định nghĩa. Tuy nhiên, sự linh hoạt ở tầng lưu trữ có thể chuyển thành chi phí ở tầng truy vấn.

Trong chương **Mô hình dữ liệu**, bài học này phân tích quan hệ, JSON và mô hình thuộc tính linh hoạt dưới góc nhìn chi phí truy vấn. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta sẽ xem một thuộc tính được lưu ở đâu ảnh hưởng thế nào đến predicate, index, JOIN, aggregation, cập nhật, kích thước dữ liệu và khả năng optimizer ước lượng số dòng.

Không có mô hình nào tốt nhất cho mọi dữ liệu. Quyết định hợp lý bắt đầu từ workload: thuộc tính nào được lọc và nối thường xuyên, thuộc tính nào chỉ hiển thị, dữ liệu thay đổi ra sao, và hệ thống cần kiểm tra tính hợp lệ ở mức nào. Một thiết kế tốt thường kết hợp các mô hình có chủ đích, giữ các thuộc tính truy vấn quan trọng ở dạng dễ lập chỉ mục và dùng cấu trúc linh hoạt cho phần thực sự cần linh hoạt.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt mô hình quan hệ, JSON/document và EAV theo cách lưu trữ và truy vấn.
- Giải thích ảnh hưởng của kiểu dữ liệu, NULL, thuộc tính thiếu, cardinality và thống kê đến optimizer.
- Đánh giá chi phí lọc, JOIN, sắp xếp, nhóm và cập nhật với thuộc tính nằm trong cột, JSON hoặc EAV.
- Chọn index phù hợp cho cột quan hệ, JSON path và cặp thuộc tính/giá trị.
- Nhận diện khi nào nên tách một JSON path thành cột quan hệ hoặc generated column.
- Hiểu vì sao truy vấn EAV thường cần nhiều JOIN hoặc GROUP BY và cách thiết kế index cho nó.
- Thiết kế mô hình lai phù hợp với thuộc tính ổn định và thuộc tính biến động.
- Kiểm chứng lựa chọn mô hình bằng execution plan và benchmark workload đọc/ghi đại diện.

## 1. Ba cách biểu diễn dữ liệu

### 1.1. Mô hình quan hệ: thuộc tính là cột có kiểu

Trong mô hình quan hệ, mỗi loại thực thể thường được biểu diễn bằng bảng; thuộc tính có tên và kiểu dữ liệu xác định.

~~~sql
CREATE TABLE products (
    product_id   BIGINT PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    category_id  BIGINT NOT NULL,
    price        DECIMAL(12, 2) NOT NULL,
    is_active    BOOLEAN NOT NULL,
    created_at   TIMESTAMP NOT NULL
);
~~~

Các thuộc tính như category_id, price và is_active có kiểu rõ ràng. DBMS có thể kiểm tra kiểu, áp dụng NOT NULL, CHECK, UNIQUE và FOREIGN KEY, thu thập thống kê theo cột và sử dụng index trực tiếp.

Ví dụ truy vấn:

~~~sql
SELECT product_id, name, price
FROM products
WHERE category_id = 12
  AND is_active = TRUE
  AND price BETWEEN 100 AND 500
ORDER BY price;
~~~

Các predicate tương ứng trực tiếp với cột. Optimizer có thể ước lượng số dòng dựa trên statistics và cân nhắc index ghép, index đơn, partition pruning hoặc scan.

Mô hình quan hệ thường phù hợp với dữ liệu có cấu trúc ổn định, thuộc tính được lọc/nối/sắp xếp thường xuyên và cần ràng buộc toàn vẹn rõ ràng.

### 1.2. JSON: một phần thuộc tính nằm trong tài liệu

JSON biểu diễn object, array, scalar và cấu trúc lồng nhau. Ví dụ một sản phẩm có thông số khác nhau theo loại:

~~~json
{
  "material": "aluminum",
  "dimensions": {
    "width_mm": 120,
    "height_mm": 80
  },
  "wireless": true,
  "supported_protocols": ["wifi", "bluetooth"]
}
~~~

Có thể lưu tài liệu này trong cột JSON/JSONB tùy DBMS:

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,
    category_id BIGINT NOT NULL,
    attributes JSON
);
~~~

Kiểu cột trong ví dụ mang tính khái quát: MySQL dùng JSON; PostgreSQL có cả JSON và JSONB. Các ví dụ GIN bên dưới yêu cầu cột PostgreSQL có kiểu JSONB, vì vậy khi dùng PostgreSQL hãy khai báo attributes JSONB nếu cần các index/operator đó.

JSON phù hợp khi một tập thuộc tính thay đổi theo loại sản phẩm hoặc do nguồn dữ liệu bên ngoài cung cấp. Nó giúp tránh thêm nhiều cột hiếm khi dùng hoặc thay đổi schema cho mỗi thuộc tính mới.

Tuy nhiên, việc đọc một thuộc tính JSON thường cần dùng toán tử hoặc hàm truy xuất path. Nếu thuộc tính đó được lọc thường xuyên, cần expression index, generated column hoặc cơ chế index JSON phù hợp. Nếu không, DBMS có thể phải đọc tài liệu, trích xuất giá trị rồi mới lọc.

### 1.3. EAV: thuộc tính được lưu thành các dòng

Mô hình Entity-Attribute-Value lưu mỗi thuộc tính thành một dòng, thay vì một cột cố định. Ví dụ:

| entity_id | attribute_name | value |
|---:|---|---|
| 101 | material | aluminum |
| 101 | width_mm | 120 |
| 101 | wireless | true |
| 102 | material | steel |
| 102 | capacity_l | 30 |

Mô hình EAV có thể biểu diễn nhiều loại thực thể với các thuộc tính khác nhau mà không cần thay đổi schema mỗi khi có thuộc tính mới. Nó hữu ích trong một số hệ thống cấu hình động, biểu mẫu do người dùng định nghĩa hoặc metadata có tập thuộc tính rất thưa.

Đổi lại, thuộc tính trở thành dữ liệu trong các dòng. Một truy vấn cần nhiều thuộc tính của cùng một entity có thể phải self-join bảng EAV nhiều lần, dùng GROUP BY/HAVING hoặc pivot. Kiểu dữ liệu và ràng buộc cũng phức tạp hơn nếu mọi giá trị cùng nằm trong một cột text.

### 1.4. So sánh khái quát

| Tiêu chí | Cột quan hệ | JSON | EAV |
|---|---|---|---|
| Schema | Rõ ràng, kiểu xác định | Cột tài liệu, cấu trúc bên trong linh hoạt | Schema thuộc tính được biểu diễn bằng dữ liệu |
| Thêm thuộc tính | Có thể cần migration | Thường không cần thêm cột | Thêm metadata/attribute, rồi thêm dòng |
| Lọc thuộc tính ổn định | Trực tiếp trên cột | Cần JSON path và index phù hợp | Lọc theo attribute và value |
| JOIN | Tự nhiên qua khóa | Khó hơn nếu khóa nằm trong tài liệu | Có thể cần nhiều self-join |
| Kiểu và constraint | Mạnh, rõ ràng | Tùy DBMS, thường cần kiểm tra bổ sung | Phải quản lý kiểu/metadata riêng |
| Index | B-tree và loại index theo cột | JSON index, expression hoặc generated column | Index theo entity/attribute/value |
| Thống kê | Thường đầy đủ theo cột | Có thể hạn chế ở path lồng nhau | Phân bố giá trị theo attribute khó hơn |
| Đọc một entity | Thường ít cột rõ ràng | Có thể lấy cả document | Có thể cần nhiều dòng |
| Đọc nhiều thuộc tính để lọc | Predicate và JOIN chuẩn | Nhiều phép trích xuất path | Nhiều JOIN hoặc aggregation |
| Thay đổi cấu trúc | Migration có kiểm soát | Linh hoạt ở document | Linh hoạt nhưng logic truy vấn phức tạp |

Bảng này mô tả xu hướng. DBMS hiện đại có thể hỗ trợ JSON index, expression statistics, generated columns hoặc tối ưu EAV ở mức nhất định. Cần kiểm tra tính năng của phiên bản và execution plan thực tế.

## 2. Workload quyết định thuộc tính nên được lưu ở đâu

### 2.1. Phân loại thuộc tính theo cách sử dụng

Trước khi chọn mô hình, lập danh sách thuộc tính và phân loại theo workload:

- **Thuộc tính định danh:** khóa chính, mã nghiệp vụ, tenant, quan hệ tham chiếu.
- **Thuộc tính lọc thường xuyên:** trạng thái, loại, vùng, thời gian, giá trị số trong điều kiện WHERE.
- **Thuộc tính nối:** khóa ngoại hoặc khóa dùng để liên kết bảng.
- **Thuộc tính sắp xếp/phân trang:** created_at, sequence, priority.
- **Thuộc tính tổng hợp:** giá, số lượng, điểm, nhóm báo cáo.
- **Thuộc tính hiển thị:** chỉ lấy để trình bày, ít khi lọc hoặc nối.
- **Thuộc tính hiếm/biến động:** thông số theo loại sản phẩm, metadata nguồn ngoài hoặc cấu hình mở rộng.

Thuộc tính được dùng trong predicate, JOIN, ORDER BY hoặc GROUP BY thường cần một biểu diễn mà DBMS có thể lập chỉ mục và thống kê tốt. Thuộc tính chỉ dùng để hiển thị có thể phù hợp hơn với JSON nếu document được đọc cùng entity và không cần truy vấn sâu thường xuyên.

### 2.2. Tần suất và độ quan trọng của truy vấn

Không nên quyết định dựa trên một truy vấn đơn lẻ. Hãy thu thập:

- Query fingerprint và số lần chạy.
- Tổng thời gian, p95/p99 và CPU.
- Số dòng đọc/trả về.
- Buffer reads, physical I/O và dữ liệu tạm.
- Số lần JOIN hoặc JSON path extraction.
- Tần suất cập nhật thuộc tính.
- Mức độ quan trọng của nghiệp vụ và yêu cầu độ chính xác.

Một JSON path được lọc vài lần mỗi tháng có thể không cần tách thành cột. Nhưng nếu API tìm kiếm dùng path đó hàng nghìn lần mỗi giây, chi phí trích xuất và thiếu thống kê có thể trở thành nút thắt.

### 2.3. Độ chọn lọc và phân bố dữ liệu

Một thuộc tính có thể được lưu trong bất kỳ mô hình nào, nhưng khả năng tối ưu còn phụ thuộc selectivity và skew.

Ví dụ, thuộc tính status có ba giá trị nhưng 95% bản ghi ở trạng thái ACTIVE. Index chỉ trên status có thể ít chọn lọc. Kết hợp tenant_id và status có thể hữu ích hơn nếu tenant là điều kiện bắt buộc. Với JSON, expression index trên status path có thể giúp tìm kiếm, nhưng optimizer vẫn cần thống kê phù hợp.

Nếu một giá trị rất phổ biến còn các giá trị khác hiếm, cần kiểm tra nhiều tham số đại diện. Một plan tốt cho giá trị hiếm có thể kém cho giá trị phổ biến.

## 3. Chi phí truy vấn với cột quan hệ

### 3.1. Lọc và truy cập bằng index

Predicate trên cột có kiểu rõ ràng thường dễ lập chỉ mục:

~~~sql
SELECT product_id, price
FROM products
WHERE category_id = 12
  AND is_active = TRUE
  AND price >= 100;
~~~

Một index ghép có thể được đánh giá:

~~~sql
CREATE INDEX idx_products_category_active_price
ON products (category_id, is_active, price);
~~~

Hai điều kiện bằng có thể tạo prefix; điều kiện range trên price xác định vùng quét tiếp theo. Thứ tự cuối cùng phải xét các truy vấn khác, cardinality và ORDER BY.

Cột quan hệ còn giúp optimizer dùng statistics để ước lượng số dòng. Nếu histogram và thống kê tương quan được cập nhật, DBMS có thể lựa chọn index scan hoặc sequential scan phù hợp hơn.

### 3.2. JOIN và ràng buộc

Quan hệ giữa bảng được biểu diễn bằng khóa ngoại:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL
);
~~~

JOIN trên khóa có kiểu tương thích và index rõ ràng:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
~~~

Optimizer có thể dùng nested loop với index lookup, hash join hoặc merge join tùy cardinality và access path. Ràng buộc UNIQUE/PRIMARY KEY cũng cung cấp thông tin về tính duy nhất để ước lượng số dòng.

### 3.3. Aggregation và thống kê

Cột quan hệ có thể được nhóm hoặc tổng hợp trực tiếp:

~~~sql
SELECT category_id, AVG(price)
FROM products
WHERE is_active = TRUE
GROUP BY category_id;
~~~

DBMS có thể dùng hash aggregate hoặc sort/group aggregate. Statistics trên category_id và is_active giúp ước lượng số nhóm và số dòng đầu vào. Nếu cột nằm sâu trong JSON hoặc EAV, việc trích xuất/ghép dữ liệu trước khi aggregate có thể làm tăng công việc.

## 4. Chi phí truy vấn với JSON

### 4.1. Truy xuất path

Cách lấy một thuộc tính phụ thuộc DBMS. Ví dụ PostgreSQL JSONB:

~~~sql
SELECT product_id
FROM products
WHERE attributes ->> 'material' = 'aluminum';
~~~

Với MySQL JSON:

~~~sql
SELECT product_id
FROM products
WHERE JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.material')) = 'aluminum';
~~~

Nếu không có index phù hợp, DBMS có thể phải đọc nhiều row hoặc document, thực hiện trích xuất path và so sánh. Khi tài liệu lớn, chi phí CPU và bộ nhớ có thể tăng. Predicate trên JSON path không tự động có cùng access path như một cột B-tree thông thường.

### 4.2. Kiểu dữ liệu và chuyển đổi

JSON hỗ trợ string, number, boolean, null, array và object. Nhưng khi truy vấn, cần quan tâm kiểu trả về của toán tử hoặc hàm JSON. Một con số được lưu dưới dạng chuỗi có thể cần chuyển kiểu; so sánh lexical khác so sánh số.

Ví dụ, các giá trị "100" và "20" nếu so sánh như chuỗi có thứ tự khác với so sánh số. Khi lọc theo khoảng số, hãy bảo đảm dữ liệu có kiểu nhất quán và biểu thức truy vấn trả về kiểu số phù hợp.

Cần phân biệt:
- Path không tồn tại.
- Path tồn tại với JSON null.
- SQL NULL của cả cột attributes.
- Giá trị sai kiểu hoặc không thể chuyển đổi.

Các trường hợp này có semantics khác nhau trong toán tử JSON và có thể ảnh hưởng kết quả lọc.

### 4.3. JSON index trong PostgreSQL

PostgreSQL cung cấp JSONB và các operator class cho GIN. Ví dụ:

~~~sql
CREATE INDEX idx_products_attributes_gin
ON products USING GIN (attributes);
~~~

GIN với operator class mặc định jsonb_ops cho JSONB hỗ trợ nhiều dạng toán tử hơn so với jsonb_path_ops. Với truy vấn containment:

~~~sql
SELECT product_id
FROM products
WHERE attributes @> '{"material":"aluminum"}';
~~~

Có thể cân nhắc:

~~~sql
CREATE INDEX idx_products_attributes_path
ON products USING GIN (attributes jsonb_path_ops);
~~~

jsonb_path_ops thường nhỏ hơn và phù hợp với một số truy vấn containment, nhưng không hỗ trợ mọi toán tử JSONB mà operator class mặc định hỗ trợ, chẳng hạn các phép kiểm tra key tồn tại dạng dấu hỏi. Hãy chọn operator class theo chính xác các toán tử workload sử dụng.

GIN không phải lúc nào cũng thay thế B-tree. Nếu truy vấn lọc một scalar path bằng nhau hoặc theo range và cần ORDER BY, expression B-tree index có thể phù hợp hơn.

Ví dụ expression index:

~~~sql
CREATE INDEX idx_products_material
ON products ((attributes ->> 'material'));
~~~

Truy vấn cần dùng biểu thức tương thích:

~~~sql
SELECT product_id
FROM products
WHERE attributes ->> 'material' = 'aluminum';
~~~

Với giá trị số, cần biểu thức cast an toàn và nhất quán. Nếu tài liệu có giá trị sai kiểu, cast có thể lỗi; cần kiểm soát schema của document trước khi dùng expression index.

### 4.4. JSON index trong MySQL

MySQL có thể dùng generated column để trích xuất JSON path thành cột có kiểu và lập index trên cột đó:

~~~sql
ALTER TABLE products
ADD COLUMN material VARCHAR(40)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.material'))
    ) STORED,
ADD INDEX idx_products_material (material);
~~~

Truy vấn có thể lọc trên generated column:

~~~sql
SELECT product_id
FROM products
WHERE material = 'aluminum';
~~~

Một số phiên bản MySQL hỗ trợ functional index trên biểu thức, nhưng kiểu, giới hạn biểu thức và cách optimizer khớp biểu thức phụ thuộc phiên bản. Generated column giúp biểu đạt kiểu và index rõ ràng, nhưng cột STORED cần dung lượng và được tính khi dữ liệu thay đổi.

Với thuộc tính được truy vấn thường xuyên, generated column có thể là bước chuyển tiếp giữa JSON linh hoạt và mô hình quan hệ. Cần đo chi phí ghi và kích thước index.

### 4.5. JSON path, thống kê và optimizer

Optimizer có thể không có histogram chi tiết cho mọi path lồng nhau. Khi không có thống kê phù hợp, ước lượng số dòng có thể kém chính xác. Một expression index hoặc generated column thường giúp đưa path thành biểu thức/cột mà DBMS có thể thu thập statistics rõ hơn.

Khi plan chọn scan không mong muốn, hãy so sánh estimated rows với actual rows. Đừng kết luận JSON chậm chỉ vì một truy vấn không có index; cũng đừng kết luận GIN luôn nhanh hơn B-tree. Hãy xét toán tử, độ chọn lọc, kiểu truy vấn và kết quả thực tế.

### 4.6. Kích thước document và chi phí cập nhật

Một JSON document lớn có thể chứa nhiều thuộc tính không cần cho mỗi truy vấn. Việc đọc hoặc truyền toàn bộ document có thể tăng bytes, memory và network cost. Một số DBMS lưu giá trị lớn ngoài trang hoặc dùng cơ chế lưu trữ riêng; cập nhật document có thể tạo thêm công việc ghi, log và phiên bản dữ liệu.

Nếu một thuộc tính nhỏ thay đổi thường xuyên trong một document lớn, cần đo chi phí cập nhật và contention trên row chứa document. JSON không tự tạo một đơn vị khóa độc lập cho từng key; cơ chế khóa và cập nhật phụ thuộc DBMS và cách lưu trữ.

## 5. Chi phí truy vấn với EAV và thuộc tính linh hoạt

### 5.1. Cấu trúc EAV cơ bản

Một thiết kế đơn giản có thể gồm:

~~~sql
CREATE TABLE entity_attribute (
    entity_id     BIGINT NOT NULL,
    attribute_id  BIGINT NOT NULL,
    value_text    VARCHAR(500),
    PRIMARY KEY (entity_id, attribute_id)
);
~~~

Bảng metadata định nghĩa thuộc tính:

~~~sql
CREATE TABLE attribute_definition (
    attribute_id BIGINT PRIMARY KEY,
    attribute_name VARCHAR(100) NOT NULL UNIQUE,
    value_type VARCHAR(20) NOT NULL
);
~~~

Khóa chính (entity_id, attribute_id) trong ví dụ giả định mỗi entity có tối đa một giá trị cho mỗi thuộc tính. Nếu thuộc tính đa trị, cần thêm value_id/ordinal vào khóa và xác định rõ cách đếm, loại trùng và sắp xếp các giá trị.

Mô hình này cho phép mỗi entity có tập thuộc tính khác nhau. Tuy nhiên, value_text là chuỗi nên truy vấn số hoặc ngày cần chuyển kiểu hoặc cần thiết kế bảng/cột giá trị theo kiểu dữ liệu.

Nếu mọi giá trị được lưu chung trong text, điều kiện như value_text > '100' có thể so sánh theo thứ tự chuỗi, không phải số. Cast khi truy vấn có thể tốn CPU và làm khó sử dụng index. Một hệ thống EAV nghiêm túc cần quản lý kiểu dữ liệu, validation và index theo kiểu phù hợp.

### 5.2. Lọc một thuộc tính

Tìm sản phẩm có material = aluminum:

~~~sql
SELECT entity_id
FROM entity_attribute
WHERE attribute_id = 10
  AND value_text = 'aluminum';
~~~

Một index có thể hỗ trợ:

~~~sql
CREATE INDEX idx_eav_attribute_value_entity
ON entity_attribute (attribute_id, value_text, entity_id);
~~~

Thứ tự cột có ích khi truy vấn lọc attribute_id và value_text rồi lấy entity_id. Nếu workload thường lấy tất cả thuộc tính của một entity, index bắt đầu bằng (entity_id, attribute_id) hoặc primary key hiện có sẽ phù hợp hơn.

Một index duy nhất hiếm khi tối ưu mọi chiều truy cập. Cần xác định truy vấn chính là tìm entity theo thuộc tính hay lấy thuộc tính theo entity.

### 5.3. Lọc theo nhiều thuộc tính cần self-join

Tìm sản phẩm vừa có material = aluminum vừa có wireless = true:

~~~sql
SELECT m.entity_id
FROM entity_attribute AS m
JOIN entity_attribute AS w
  ON w.entity_id = m.entity_id
WHERE m.attribute_id = 10
  AND m.value_text = 'aluminum'
  AND w.attribute_id = 25
  AND w.value_text = 'true';
~~~

Bảng EAV được nối với chính nó để xác nhận hai thuộc tính cùng thuộc một entity. Với 5 điều kiện, truy vấn có thể cần nhiều alias/self-join. Số phép nối và cardinality trung gian tăng theo số điều kiện.

Optimizer phải ước lượng phân bố giá trị theo từng attribute_id. Nếu một thuộc tính chỉ có vài giá trị phổ biến hoặc có skew mạnh, thống kê toàn cột value_text có thể không đủ mô tả phân bố trong từng attribute_id.

### 5.4. Lọc nhiều thuộc tính bằng GROUP BY/HAVING

Một cách khác là lọc các cặp attribute/value rồi nhóm theo entity:

~~~sql
SELECT entity_id
FROM entity_attribute
WHERE (attribute_id = 10 AND value_text = 'aluminum')
   OR (attribute_id = 25 AND value_text = 'true')
GROUP BY entity_id
HAVING COUNT(DISTINCT attribute_id) = 2;
~~~

Cách này cần bảo đảm mỗi attribute chỉ có một giá trị cho mỗi entity hoặc semantics đếm đã được thiết kế đúng. Nếu dữ liệu cho phép nhiều dòng cùng attribute_id, COUNT(DISTINCT) giúp đếm thuộc tính phân biệt nhưng có thể cần sort/hash. Cần kiểm tra duplicate và constraint.

### 5.5. Chi phí lấy nhiều thuộc tính để hiển thị

Một entity có 20 thuộc tính có thể cần 20 dòng EAV. Để trả về dạng một hàng, ứng dụng có thể pivot bằng conditional aggregation:

~~~sql
SELECT
    entity_id,
    MAX(CASE WHEN attribute_id = 10 THEN value_text END) AS material,
    MAX(CASE WHEN attribute_id = 25 THEN value_text END) AS wireless,
    MAX(CASE WHEN attribute_id = 31 THEN value_text END) AS capacity
FROM entity_attribute
WHERE entity_id IN (101, 102, 103)
GROUP BY entity_id;
~~~

Cách này có thể hiệu quả cho tập entity nhỏ và tập thuộc tính cố định. Nhưng nếu ứng dụng cần nhiều entity, nhiều thuộc tính và gọi liên tục, việc đọc nhiều dòng, group và pivot có thể tốn CPU, memory và I/O.

### 5.6. Index EAV theo hai hướng truy cập

Hai mẫu phổ biến:

- Tìm entity theo attribute/value: (attribute_id, value, entity_id).
- Lấy toàn bộ thuộc tính của entity: (entity_id, attribute_id).

Nếu có nhiều kiểu giá trị, có thể tách bảng theo kiểu hoặc dùng các cột value_number, value_date, value_text với quy tắc chỉ một cột được dùng. Điều này giúp tránh so sánh số/ngày như chuỗi, nhưng schema và validation phức tạp hơn.

Không tạo index cho mọi tổ hợp attribute/value. Mỗi index tăng chi phí ghi và dung lượng. Hãy dùng query statistics để tìm tổ hợp được truy vấn thường xuyên.

## 6. Mô hình lai: cột quan hệ cộng JSON hoặc thuộc tính mở rộng

Một thiết kế thực tế thường đặt các thuộc tính quan trọng ở cột quan hệ và phần mở rộng trong JSON.

Ví dụ:

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL,
    attributes JSON
);
~~~

Trong thiết kế này:

- product_id, tenant_id và category_id hỗ trợ định danh, JOIN và phân vùng truy cập.
- price và is_active phục vụ lọc/sắp xếp thường xuyên.
- attributes chứa thông số thay đổi theo loại sản phẩm.
- Một số path quan trọng có thể được biểu diễn thêm bằng generated column hoặc expression index.

Mô hình lai tránh việc đưa mọi thuộc tính vào cột, nhưng cũng không đẩy mọi thứ vào JSON. Nó phù hợp khi có một lõi thuộc tính ổn định và một vùng mở rộng có cấu trúc thay đổi.

### 6.1. Khi nào nên tách JSON path thành cột?

Cân nhắc tách path thành cột quan hệ hoặc generated column khi thuộc tính:

- Được dùng thường xuyên trong WHERE hoặc JOIN.
- Cần ORDER BY, GROUP BY hoặc range query.
- Có kiểu dữ liệu cần validation rõ.
- Cần UNIQUE, NOT NULL, CHECK hoặc FOREIGN KEY.
- Có cardinality/skew quan trọng với optimizer.
- Xuất hiện trong nhiều truy vấn và cần thống kê ổn định.
- Là một phần của khóa phân vùng hoặc chính sách truy cập.

Nếu path chỉ hiển thị hoặc chỉ được truy vấn hiếm, giữ trong JSON có thể hợp lý hơn. Tần suất truy vấn và chi phí cập nhật quyết định điểm cân bằng.

### 6.2. Không lưu trùng mà thiếu quy tắc đồng bộ

Nếu cùng một thuộc tính được lưu ở cột quan hệ và trong JSON, cần xác định nguồn dữ liệu có thẩm quyền. Nếu ứng dụng cập nhật một nơi nhưng quên nơi còn lại, kết quả truy vấn có thể không nhất quán.

Có thể dùng generated column để dẫn xuất từ JSON nếu DBMS hỗ trợ và semantics phù hợp, hoặc chọn cột quan hệ làm nguồn chính rồi tạo document ở tầng ứng dụng. Tránh hai bản sao được cập nhật độc lập nếu không có transaction hoặc cơ chế đồng bộ rõ ràng.

### 6.3. Ranh giới document

JSON phù hợp khi các thuộc tính thường được đọc/cập nhật cùng một entity và không cần JOIN độc lập nhiều lần. Nếu một phần tử trong array có vòng đời riêng, được tham chiếu từ nhiều bảng hoặc cần constraint quan hệ, có thể nên tách thành bảng con.

Ví dụ danh sách hình ảnh của sản phẩm có thể để trong JSON nếu chỉ là metadata hiển thị; nhưng nếu mỗi ảnh có trạng thái xử lý, quyền sở hữu, lịch sử và được truy vấn độc lập, bảng product_images có thể phù hợp hơn.

## 7. Chuẩn hóa, phi chuẩn hóa và chi phí JOIN

### 7.1. Chuẩn hóa để giảm dư thừa

Chuẩn hóa tách dữ liệu thành các bảng theo thực thể và quan hệ. Nó giảm cập nhật trùng lặp và giúp ràng buộc dữ liệu. Đổi lại, truy vấn đọc cần JOIN để ghép thông tin.

Ví dụ, lưu category_id trong products và tên category trong categories tránh lặp tên danh mục ở mọi sản phẩm. Truy vấn cần tên category phải JOIN, nhưng index trên khóa và thống kê tốt thường giúp xử lý hiệu quả.

### 7.2. Phi chuẩn hóa có chủ đích

Nếu một truy vấn rất thường xuyên cần dữ liệu từ nhiều bảng và JOIN trở thành chi phí đáng kể, có thể lưu một số thuộc tính dẫn xuất hoặc bản sao. Ví dụ lưu category_name_snapshot trong đơn hàng để giữ tên danh mục tại thời điểm mua.

Phi chuẩn hóa có thể giảm JOIN, nhưng tạo chi phí:

- Dữ liệu lặp và tăng storage.
- Cần quy tắc đồng bộ khi dữ liệu nguồn thay đổi.
- Ghi có thể cập nhật nhiều nơi.
- Dữ liệu snapshot có semantics khác dữ liệu hiện tại.
- Cache và index của các bản sao cũng cần bảo trì.

Chỉ phi chuẩn hóa khi có workload và số đo chứng minh lợi ích, đồng thời xác định rõ consistency model.

### 7.3. JSON không tự động loại bỏ JOIN

Đưa dữ liệu liên quan vào một JSON document có thể giảm JOIN khi đọc toàn bộ aggregate. Nhưng nếu cần lọc theo thuộc tính của nhiều entity, kiểm tra quan hệ hoặc tổng hợp chéo, JSON có thể làm truy vấn phức tạp hơn. Một document lớn cũng có thể phải đọc nhiều dữ liệu không cần thiết.

Hãy chọn ranh giới aggregate theo cách dữ liệu được đọc, ghi và bảo đảm nhất quán. Không nhúng toàn bộ dữ liệu liên quan chỉ để tránh một phép JOIN.

## 8. So sánh các mẫu truy vấn

Giả sử cần tìm sản phẩm có material = aluminum và price dưới 500.

### 8.1. Thuộc tính quan hệ

~~~sql
SELECT product_id
FROM products
WHERE material = 'aluminum'
  AND price < 500;
~~~

Có thể tạo index ghép:

~~~sql
CREATE INDEX idx_products_material_price
ON products (material, price);
~~~

Optimizer có thể dùng equality prefix trên material và range trên price.

### 8.2. Thuộc tính JSON

PostgreSQL:

~~~sql
SELECT product_id
FROM products
WHERE attributes ->> 'material' = 'aluminum'
  AND price < 500;
~~~

Có thể dùng expression index trên path material, hoặc GIN nếu truy vấn dùng toán tử containment phù hợp. Nếu cần range trên một JSON number, cần cast an toàn và index biểu thức số tương ứng.

MySQL có thể dùng generated column material và index trên nó. Truy vấn nên tham chiếu generated column hoặc biểu thức mà optimizer có thể khớp với functional index.

### 8.3. Thuộc tính EAV

~~~sql
SELECT p.product_id
FROM products AS p
JOIN entity_attribute AS a
  ON a.entity_id = p.product_id
WHERE a.attribute_id = 10
  AND a.value_text = 'aluminum'
  AND p.price < 500;
~~~

Cần index trên (attribute_id, value_text, entity_id) để tìm entity trước, cộng index phù hợp trên products. Nếu thêm điều kiện thuộc tính thứ hai, truy vấn có thể cần thêm self-join.

### 8.4. Cách đánh giá

Không thể kết luận mô hình quan hệ luôn nhanh hơn JSON hoặc EAV chỉ từ số JOIN trong SQL. Hãy so sánh:

- Số dòng và trang thực tế được đọc.
- Số lần trích xuất JSON path.
- Số self-join hoặc aggregate của EAV.
- Khả năng sử dụng index và covering access.
- Độ chính xác estimated rows.
- Kích thước dữ liệu trung gian.
- CPU, memory, temp I/O và network bytes.
- Chi phí cập nhật và đồng bộ.

## 9. Chi phí ghi và tính nhất quán

### 9.1. Cột quan hệ

INSERT/UPDATE cột quan hệ có thể làm thay đổi index liên quan, constraint và khóa ngoại. Kiểu dữ liệu rõ ràng giúp validation nhưng mọi index bổ sung đều có write amplification. Cập nhật một cột không nằm trong index có thể rẻ hơn cập nhật cột khóa, tùy engine.

### 9.2. JSON document

Một UPDATE thay đổi JSON có thể làm DBMS tạo phiên bản row/document mới, ghi log và cập nhật các index expression hoặc GIN liên quan. Nếu một key được index, thay đổi key đó có thể cần bảo trì index. Cách cập nhật partial document và mức độ ghi thực tế phụ thuộc DBMS; không giả định thay một key luôn chỉ ghi vài byte.

Nếu document lớn và cập nhật thường xuyên, đo:
- WAL/transaction log bytes.
- Row/page writes.
- Kích thước index JSON.
- CPU khi serialize/parse.
- Lock wait và transaction duration.
- Bloat hoặc chi phí dọn phiên bản cũ theo engine.

### 9.3. EAV

Một entity có 20 thuộc tính có thể cần 20 dòng INSERT hoặc UPDATE. Điều này làm tăng số row operation, index entries, log records và khả năng lock nhiều dòng. Nếu thay đổi một thuộc tính, chỉ cần cập nhật một dòng EAV nhưng đọc cả entity lại cần nhiều dòng.

Mô hình EAV có thể giảm schema migration nhưng tăng write/read amplification ở mức row và index. Cần so sánh tổng số dòng và transaction chứ không chỉ số câu SQL.

### 9.4. Đồng bộ summary và dữ liệu dẫn xuất

Nếu tạo cột dẫn xuất, generated column, bảng tổng hợp hoặc bản sao JSON, phải xác định ai cập nhật và trong transaction nào. Nếu cập nhật bất đồng bộ, ứng dụng cần chấp nhận độ trễ và có cơ chế reconcile. Nếu yêu cầu nhất quán tức thời, cần thiết kế transaction phù hợp và đo chi phí ghi.

## 10. Thống kê và khả năng ước lượng của optimizer

### 10.1. Cột quan hệ

DBMS thường thu thập statistics trên cột, histogram, distinct count và một số tương quan. Những số liệu này giúp ước lượng selectivity và cardinality. Khi dữ liệu thay đổi mạnh, thống kê cũ có thể dẫn đến plan không phù hợp.

### 10.2. JSON path

Một path lồng nhau có thể không có thống kê độc lập như cột thường. Expression index hoặc generated column có thể cho phép DBMS lập thống kê trên giá trị được trích xuất. Điều này hữu ích khi path là predicate quan trọng.

Cần kiểm tra cách DBMS thu thập statistics cho expression hoặc generated column và tần suất cập nhật. Index có thể giúp truy cập nhưng không bảo đảm mọi ước lượng tự động chính xác.

### 10.3. EAV và phân bố theo attribute

Trong EAV, cùng cột value_text chứa giá trị của nhiều loại thuộc tính. Histogram toàn cột có thể trộn material, status, color, region hoặc giá trị khác. Phân bố của value_text không có ý nghĩa nếu không xét attribute_id.

Optimizer cần ước lượng kết hợp attribute_id và value. Nếu DBMS hỗ trợ extended/multicolumn statistics, có thể cải thiện một số ước lượng. Nhưng khả năng thống kê tương quan theo cặp attribute/value phụ thuộc engine. Hãy so sánh estimated rows với actual rows và kiểm tra plan của các attribute phổ biến lẫn hiếm.

### 10.4. Skew và parameter sensitivity

Một thuộc tính linh hoạt có thể có giá trị phổ biến áp đảo. Query tìm material = 'aluminum' có thể trả 70% sản phẩm, còn material = 'titanium' chỉ trả 0,1%. Cùng một câu SQL nhưng index access và scan có chi phí khác nhau.

Benchmark phải dùng nhiều nhóm giá trị. Nếu DBMS cache plan, kiểm tra khả năng parameter-sensitive plan hoặc cơ chế recompile/plan variant theo sản phẩm. Không cố định một plan dựa trên một giá trị tham số duy nhất.

## 11. Chọn mô hình theo loại truy vấn

| Nhu cầu | Mô hình thường phù hợp | Lý do |
|---|---|---|
| Lọc/join/sort thường xuyên trên thuộc tính ổn định | Cột quan hệ | Index và statistics trực tiếp, constraint rõ |
| Lưu metadata thay đổi, chủ yếu đọc cùng entity | JSON | Linh hoạt, tránh schema rộng với nhiều cột hiếm |
| Tìm theo một vài JSON path quan trọng | JSON + expression/generated index | Giữ linh hoạt nhưng tạo access path cụ thể |
| Tập thuộc tính do người dùng định nghĩa rất thưa | EAV có metadata và index phù hợp | Không cần cột cho mọi thuộc tính |
| Nhiều truy vấn kết hợp nhiều thuộc tính EAV | Cân nhắc chuyển thuộc tính nóng thành cột/JSON có index | Tránh self-join và aggregation lặp |
| Quan hệ có khóa ngoại và quy tắc toàn vẹn | Mô hình quan hệ | Constraint và JOIN tự nhiên |
| Document thường được đọc/ghi như một aggregate | JSON hoặc document model | Gom dữ liệu thường dùng cùng nhau |
| Báo cáo nhiều chiều, filter/range/aggregate liên tục | Cột quan hệ hoặc bảng phân tích chuyên biệt | Statistics và access path rõ ràng |

Đây là hướng dẫn ban đầu. Mô hình thực tế còn phụ thuộc DBMS, dữ liệu, tính nhất quán và tần suất thay đổi schema.

## 12. Quy trình thiết kế và kiểm chứng

### Bước 1: Thu thập workload

Dùng query statistics, slow query log và trace để xác định thuộc tính được lọc, nối, sắp xếp, nhóm và trả về. Ghi tần suất, latency, rows read và chi phí ghi.

### Bước 2: Lập bản đồ thuộc tính

Với từng thuộc tính, ghi:

- Tính ổn định của schema.
- Kiểu dữ liệu và ràng buộc.
- Tần suất đọc/ghi.
- Có tham gia WHERE/JOIN/ORDER/GROUP không?
- Có cần UNIQUE, FK, CHECK hoặc NOT NULL không?
- Có được đọc cùng entity hay truy vấn độc lập?
- Có giá trị phân biệt và skew thế nào?

### Bước 3: Chọn cách biểu diễn ban đầu

Đưa thuộc tính lõi vào cột quan hệ. Giữ metadata ít truy vấn trong JSON nếu phù hợp. Chỉ dùng EAV khi nhu cầu thuộc tính động/thưa đủ mạnh và đã chấp nhận chi phí truy vấn nhiều thuộc tính.

### Bước 4: Xác định access path

Chọn B-tree, GIN hoặc expression/generated index cho JSON path; chọn index theo entity/attribute/value cho EAV. Với cột quan hệ, xem equality, range, join, order và covering. Không tạo index trước khi biết truy vấn cần hỗ trợ.

### Bước 5: Viết truy vấn đại diện

Dùng các truy vấn thực tế, gồm lọc một thuộc tính, kết hợp nhiều thuộc tính, JOIN, aggregation, sort và cập nhật. Kiểm tra dữ liệu thiếu, NULL, sai kiểu và duplicate.

### Bước 6: Đọc execution plan

So sánh estimated/actual rows, access path, số loops, buffer reads, JSON extraction, self-join, sort/hash aggregate, temp I/O và kích thước intermediate result.

### Bước 7: Benchmark đọc và ghi

Dùng cùng snapshot, tham số, cache state và mức concurrency. Đo p50/p95/p99, throughput, CPU, memory, I/O, log bytes và lock wait. Bao gồm cả cập nhật JSON/EAV và thao tác ghi các cột quan hệ liên quan.

### Bước 8: Đánh giá toàn workload

Một mô hình có thể làm truy vấn tìm kiếm nhanh hơn nhưng làm cập nhật, đồng bộ hoặc báo cáo khác chậm hơn. So sánh các query fingerprint quan trọng và transaction nghiệp vụ.

### Bước 9: Theo dõi sau triển khai

Theo dõi index usage, kích thước document, số dòng EAV, query latency và plan regression. Nếu workload thay đổi, đánh giá lại thuộc tính nào cần chuyển sang cột hoặc cần index riêng.

## 13. Ví dụ xuyên suốt: danh mục sản phẩm nhiều loại thuộc tính

Giả sử một cửa hàng có nhiều loại sản phẩm. Mọi sản phẩm đều có product_id, tenant_id, category_id, name, price và status. Sản phẩm điện tử có warranty_months, wireless và protocol; sản phẩm nội thất có material, width và height; sản phẩm thực phẩm có expiry_date và storage_temperature.

### 13.1. Thiết kế chỉ dùng cột quan hệ

Một bảng có thể có nhiều cột nullable:

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    warranty_months INT,
    wireless BOOLEAN,
    protocol VARCHAR(40),
    material VARCHAR(40),
    width_mm INT,
    height_mm INT,
    expiry_date DATE,
    storage_temperature DECIMAL(5,2)
);
~~~

Ưu điểm là lọc, constraint và statistics rõ ràng. Nhược điểm là nhiều cột chỉ dùng cho một số loại sản phẩm; schema có thể rộng và cần migration khi thêm thuộc tính. Cột nullable không tự gây chậm, nhưng nhiều thuộc tính hiếm có thể làm schema và logic ứng dụng khó quản lý.

### 13.2. Thiết kế lõi quan hệ cộng JSON

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attributes JSON
);
~~~

Các trường ổn định và được truy vấn thường xuyên nằm ở cột; thông số theo loại nằm trong attributes. Nếu API thường lọc wireless, có thể tạo generated column hoặc expression index. Nếu chỉ hiển thị thông số khi mở trang chi tiết, không nhất thiết cần index cho mọi path.

### 13.3. Thiết kế EAV

Bảng products giữ thông tin lõi; thuộc tính mở rộng nằm trong entity_attribute. Có thể thêm metadata cho kiểu dữ liệu và category được phép dùng thuộc tính nào.

Khi truy vấn sản phẩm có material = aluminum và width_mm >= 100, hệ thống phải tìm hai attribute tương ứng, chuyển kiểu số an toàn và kết hợp entity_id. Nếu workload tìm kiếm kết hợp nhiều thuộc tính chạy thường xuyên, số self-join và aggregation có thể tăng. Các thuộc tính nóng có thể cần được chuyển thành cột hoặc JSON path có index.

### 13.4. Quyết định theo workload

Giả sử 80% truy vấn tìm sản phẩm lọc tenant, category, status và price; 15% truy vấn lọc wireless hoặc material; 5% chỉ hiển thị metadata.

Một thiết kế hợp lý có thể:
- Đặt tenant_id, category_id, status và price ở cột quan hệ.
- Lưu thông số hiếm trong JSON.
- Tạo expression/generated index cho wireless hoặc material nếu số đo chứng minh chúng là predicate nóng.
- Không dùng EAV cho các thuộc tính mà truy vấn thường kết hợp nhiều điều kiện nếu chi phí self-join vượt lợi ích linh hoạt.

Tỷ lệ 80/15/5 chỉ là ví dụ. Quyết định cuối cần query statistics và benchmark thực tế, không dựa vào tỷ lệ minh họa.

## 14. Những sai lầm thường gặp

**Đưa mọi thuộc tính vào JSON vì muốn tránh migration.** Các thuộc tính được lọc và nối thường xuyên có thể mất access path và statistics rõ ràng.

**Cho rằng JSON luôn chậm.** JSON có thể hiệu quả khi document được đọc cùng entity, cấu trúc phù hợp và path quan trọng có index.

**Dùng GIN cho mọi truy vấn JSON.** GIN phù hợp với một số toán tử containment/key search; scalar equality, range và ORDER BY có thể cần expression B-tree hoặc generated column.

**Lưu mọi giá trị EAV dưới dạng text.** So sánh số/ngày có thể sai semantics hoặc cần cast tốn kém. Phải quản lý kiểu dữ liệu.

**Cho rằng EAV giảm chi phí vì không cần thêm cột.** Một truy vấn nhiều thuộc tính có thể cần nhiều self-join, GROUP BY và sort/hash.

**Đưa mọi dữ liệu liên quan vào một JSON document để tránh JOIN.** Truy vấn độc lập, ràng buộc và cập nhật từng phần tử có thể trở nên khó hơn.

**Lưu trùng thuộc tính ở cột và JSON mà không có nguồn dữ liệu chính.** Dữ liệu có thể lệch nhau và gây kết quả không nhất quán.

**Tạo index trên mọi JSON path hoặc mọi cặp EAV.** Index làm tăng storage, cache pressure và chi phí ghi.

**Benchmark chỉ một giá trị tham số.** Skew có thể khiến plan và chi phí thay đổi mạnh.

**Không kiểm tra execution plan.** Cùng một cú pháp có thể dùng access path khác nhau giữa DBMS và phiên bản.

## 15. Checklist chọn mô hình và tối ưu chi phí truy vấn

- [ ] Đã phân loại thuộc tính theo lọc, JOIN, sort, group, hiển thị và tần suất cập nhật chưa?
- [ ] Đã xác định thuộc tính nào ổn định và cần constraint rõ ràng chưa?
- [ ] Đã đo query fingerprint, latency, rows read và tần suất workload chưa?
- [ ] Đã đánh giá selectivity, cardinality, NULL, missing path và skew chưa?
- [ ] Đã cân nhắc cột quan hệ cho thuộc tính truy vấn nóng chưa?
- [ ] Nếu dùng JSON, đã xác định toán tử/path và index phù hợp chưa?
- [ ] Nếu dùng EAV, đã có metadata kiểu dữ liệu và index theo entity/attribute/value chưa?
- [ ] Đã đánh giá số self-join, GROUP BY và pivot cần thiết chưa?
- [ ] Đã xác định nguồn dữ liệu chính nếu có thuộc tính dẫn xuất/lưu trùng chưa?
- [ ] Đã xem chi phí cập nhật document, index và nhiều dòng EAV chưa?
- [ ] Đã đọc actual plan và so sánh estimated rows với actual rows chưa?
- [ ] Đã benchmark đọc/ghi hỗn hợp trên dữ liệu và tham số đại diện chưa?
- [ ] Đã kiểm tra consistency, transaction, lock và khả năng reconcile chưa?
- [ ] Đã có kế hoạch theo dõi và chuyển đổi mô hình khi workload thay đổi chưa?

## Kết luận

Mô hình quan hệ, JSON và EAV là các lựa chọn biểu diễn dữ liệu với đặc tính truy vấn khác nhau. Cột quan hệ phù hợp với thuộc tính ổn định cần lọc, JOIN, sắp xếp, tổng hợp và ràng buộc. JSON phù hợp với metadata có cấu trúc thay đổi, đặc biệt khi thường được đọc cùng entity; path được truy vấn thường xuyên có thể cần expression index, GIN hoặc generated column tùy DBMS. EAV phù hợp với tập thuộc tính rất linh hoạt và thưa, nhưng truy vấn nhiều thuộc tính thường phải self-join, aggregate và quản lý kiểu dữ liệu cẩn thận.

Chi phí thực tế phụ thuộc workload, selectivity, thống kê, index, kích thước dữ liệu, số lần cập nhật và concurrency. Hãy giữ thuộc tính truy vấn nóng ở dạng DBMS có thể lọc và thống kê hiệu quả; dùng cấu trúc linh hoạt cho phần thật sự cần linh hoạt; đo cả đọc lẫn ghi và kiểm tra actual plan. Mô hình dữ liệu tốt là mô hình đáp ứng đúng semantics nghiệp vụ với chi phí toàn workload có thể đo và kiểm soát.

