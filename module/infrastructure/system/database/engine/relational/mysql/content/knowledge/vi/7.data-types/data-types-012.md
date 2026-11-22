# JSON và kiểu dữ liệu không gian

Một ứng dụng MySQL thường có dữ liệu quan hệ rõ ràng như mã khách hàng, trạng thái đơn hàng và số tiền. Tuy nhiên, một số thuộc tính thay đổi theo từng loại bản ghi, hoặc dữ liệu mô tả vị trí trên bản đồ, khó biểu diễn gọn bằng các cột scalar thông thường. MySQL cung cấp kiểu `JSON` để lưu tài liệu có cấu trúc và các kiểu không gian như `POINT`, `LINESTRING`, `POLYGON` để lưu hình học.

Hai nhóm kiểu dữ liệu này giải quyết những bài toán khác nhau. JSON phù hợp với thuộc tính bán cấu trúc cần đọc và cập nhật theo đường dẫn; kiểu không gian phù hợp với tọa độ, vùng địa lý và phép toán hình học. Chọn đúng kiểu, kiểm soát cấu trúc và lập chỉ mục phù hợp giúp truy vấn hiệu quả mà vẫn giữ được tính nhất quán của dữ liệu.

## 1. Khi nào nên dùng JSON và kiểu không gian?

### 1.1. JSON cho dữ liệu bán cấu trúc

Giả sử một hệ thống thương mại điện tử có nhiều loại sản phẩm. Điện thoại có `screen_size`, `ram_gb`, `storage_gb`; áo có `size`, `material`, `color`; đồ gia dụng có `capacity_liter` và `power_watt`. Có thể tạo rất nhiều cột nullable trong một bảng chung, hoặc tách từng loại sản phẩm thành nhiều bảng. Một lựa chọn khác là giữ các thuộc tính thay đổi trong một cột JSON:

```json
{
  "screen_size": 6.7,
  "ram_gb": 12,
  "storage_gb": 256,
  "colors": ["black", "blue"]
}
```

JSON giúp biểu diễn object, array, string, number, boolean và null lồng nhau. MySQL có thể truy vấn từng phần tử, cập nhật một đường dẫn và chuyển các phần tử array thành hàng bằng `JSON_TABLE`.

JSON không nên thay thế mọi cột quan hệ. Những thuộc tính có kiểu và quy tắc ổn định, thường được lọc/join/sắp xếp, cần ràng buộc hoặc được nhiều bảng tham chiếu vẫn nên là cột quan hệ thông thường. Một thiết kế phổ biến là giữ cột quan trọng như `product_id`, `category_id`, `price`, `created_at` ở dạng scalar và chỉ lưu thuộc tính linh hoạt trong JSON.

### 1.2. Kiểu không gian cho tọa độ và hình học

Ứng dụng giao hàng có thể cần lưu vị trí cửa hàng, điểm giao hàng, tuyến đường hoặc vùng phục vụ. Lưu kinh độ và vĩ độ trong hai cột `DECIMAL` có thể đáp ứng việc hiển thị đơn giản, nhưng không cung cấp trực tiếp các phép toán hình học và chỉ mục không gian.

Kiểu không gian của MySQL lưu các hình học như điểm, đường và đa giác. Các hàm không gian cho phép tính khoảng cách, kiểm tra một điểm có nằm trong vùng hay hai hình có giao nhau. Spatial index giúp tìm các đối tượng nằm trong vùng ứng viên mà không phải quét toàn bộ bảng.

## 2. Kiểu JSON trong MySQL

### 2.1. JSON là kiểu dữ liệu gốc

MySQL có kiểu `JSON` riêng từ MySQL 5.7.8. Khi ghi vào cột JSON, server kiểm tra nội dung có phải tài liệu JSON hợp lệ hay không và lưu theo định dạng nội bộ đã tối ưu để truy cập các phần tử. Đây không đơn thuần là cột `VARCHAR` chứa chuỗi JSON. Các hàm JSON và khả năng lập chỉ mục được bổ sung qua nhiều phiên bản, vì vậy cần kiểm tra phiên bản server trước khi dùng tính năng mới.

Ví dụ tạo bảng sự kiện:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(40) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_event_type_created (event_type, created_at)
) ENGINE=InnoDB;
```

Thêm một tài liệu JSON:

```sql
INSERT INTO events (event_type, payload)
VALUES (
    'order.created',
    '{"order_id": 9001, "customer": {"id": 120}, "items": [{"sku": "KB-01", "quantity": 2}], "source": "web"}'
);
```

Nếu chuỗi không phải JSON hợp lệ, MySQL từ chối giá trị thay vì lưu một tài liệu sai định dạng vào cột JSON. Với cột văn bản thông thường, nếu muốn bảo đảm nội dung là JSON, cần tự kiểm tra hoặc dùng constraint phù hợp như `CHECK (JSON_VALID(column))` trên phiên bản hỗ trợ CHECK.

MySQL chuẩn hóa tài liệu JSON khi lưu. Không dựa vào thứ tự khóa trong object để biểu diễn thứ tự nghiệp vụ; object JSON là tập cặp key/value. Với các khóa trùng nhau trong cùng object, quá trình chuẩn hóa giữ giá trị cuối cùng theo quy tắc của MySQL. Nếu thứ tự phần tử quan trọng, hãy dùng array.

### 2.2. Các giá trị JSON

JSON hỗ trợ các loại giá trị cơ bản:

| Loại | Ví dụ |
|---|---|
| Object | `{"name": "An", "active": true}` |
| Array | `["red", "blue"]` |
| String | `"MySQL"` |
| Number | `12`, `3.14` |
| Boolean | `true`, `false` |
| Null của JSON | `null` |

Phân biệt SQL `NULL` với JSON `null`. SQL `NULL` nghĩa là cột không có giá trị theo ngữ nghĩa SQL; JSON `null` là một giá trị nằm bên trong tài liệu JSON. Một cột JSON có thể chứa tài liệu `null` mà bản thân cột không phải SQL NULL.

### 2.3. Kiểm tra JSON và kiểu của phần tử

```sql
SELECT
    JSON_VALID('{"name":"An","age":28}') AS valid_document,
    JSON_TYPE(JSON_EXTRACT('{"age":28}', '$.age')) AS age_type,
    JSON_TYPE(JSON_EXTRACT('{"active":true}', '$.active')) AS active_type;
```

Một số hàm thường dùng:

| Hàm | Công dụng |
|---|---|
| `JSON_VALID(doc)` | Kiểm tra chuỗi/tài liệu có phải JSON hợp lệ |
| `JSON_TYPE(value)` | Trả về loại giá trị JSON như `OBJECT`, `ARRAY`, `INTEGER`, `STRING`, `BOOLEAN`, `NULL` |
| `JSON_OBJECT(k, v, ...)` | Tạo object JSON |
| `JSON_ARRAY(v, ...)` | Tạo array JSON |
| `JSON_LENGTH(doc[, path])` | Đếm phần tử object hoặc array tại đường dẫn |
| `JSON_KEYS(doc[, path])` | Lấy danh sách khóa của object |
| `JSON_DEPTH(doc)` | Độ sâu lớn nhất của tài liệu |
| `JSON_PRETTY(doc)` | In tài liệu với định dạng dễ đọc |

## 3. Truy xuất giá trị bằng JSON path

JSON path xác định vị trí một phần tử trong tài liệu. `$` là gốc; `.key` đi vào thuộc tính object; `[index]` truy cập phần tử array, bắt đầu từ 0.

Ví dụ tài liệu:

```json
{
  "order_id": 9001,
  "customer": {"id": 120, "name": "An"},
  "items": [
    {"sku": "KB-01", "quantity": 2},
    {"sku": "MS-02", "quantity": 1}
  ]
}
```

Các đường dẫn tương ứng:

| JSON path | Giá trị được chọn |
|---|---|
| `$.order_id` | `9001` |
| `$.customer.id` | `120` |
| `$.items[0].sku` | `"KB-01"` |
| `$.items[1].quantity` | `1` |

### 3.1. JSON_EXTRACT và toán tử rút gọn

```sql
SELECT
    JSON_EXTRACT(payload, '$.order_id') AS order_id_json,
    payload->'$.customer.id' AS customer_id_json,
    payload->>'$.customer.name' AS customer_name_text,
    payload->>'$.items[0].sku' AS first_sku
FROM events
WHERE id = 1;
```

`JSON_EXTRACT(doc, path)` trả về giá trị JSON. Toán tử `->` là cách viết rút gọn của `JSON_EXTRACT`. Toán tử `->>` tương đương lấy giá trị theo path rồi bỏ lớp trích dẫn JSON bằng `JSON_UNQUOTE`, thuận tiện khi cần chuỗi SQL để hiển thị hoặc so sánh.

Khi so sánh giá trị số, hãy chú ý kiểu dữ liệu. `JSON_EXTRACT` trả JSON number, trong khi `->>` trả chuỗi đã bỏ trích dẫn. Có thể dùng `CAST` để chuyển về kiểu số rõ ràng khi cần tính toán:

```sql
SELECT id
FROM events
WHERE CAST(payload->>'$.customer.id' AS UNSIGNED) = 120;
```

Truy vấn này có thể phải đọc và chuyển đổi nhiều tài liệu nếu không có chỉ mục thích hợp. Phần lập chỉ mục JSON sẽ trình bày cách đưa giá trị thường truy vấn ra generated column.

### 3.2. Phân biệt đường dẫn không tồn tại và JSON null

Nếu path không tồn tại, `JSON_EXTRACT` trả về SQL `NULL`. Nếu path tồn tại và chứa JSON `null`, hàm trả về giá trị JSON null. Có thể kiểm tra sự tồn tại của path bằng `JSON_CONTAINS_PATH`:

```sql
SELECT
    JSON_CONTAINS_PATH('{"nickname": null}', 'one', '$.nickname') AS has_nickname,
    JSON_CONTAINS_PATH('{"nickname": null}', 'one', '$.missing') AS has_missing,
    JSON_TYPE(JSON_EXTRACT('{"nickname": null}', '$.nickname')) AS nickname_type;
```

Phân biệt này quan trọng với API cập nhật hồ sơ. Thiếu thuộc tính có thể có nghĩa người dùng chưa gửi trường; JSON null có thể có nghĩa người dùng muốn xóa giá trị; SQL NULL có thể có nghĩa toàn bộ payload chưa được cung cấp.

### 3.3. Truy vấn mảng

Các hàm như `JSON_LENGTH`, `JSON_CONTAINS`, `JSON_SEARCH` và `JSON_OVERLAPS` hỗ trợ kiểm tra nội dung array/object. Ví dụ kiểm tra một tag có nằm trong mảng `tags`:

```sql
SELECT id
FROM products
WHERE JSON_CONTAINS(attributes, JSON_QUOTE('sale'), '$.tags');
```

`JSON_QUOTE` biến chuỗi SQL thành giá trị string JSON hợp lệ. Từ MySQL 8.0.17, `JSON_OVERLAPS` kiểm tra hai tài liệu có phần tử chung; hàm này hữu ích khi so sánh tập tag:

```sql
SELECT id
FROM products
WHERE JSON_OVERLAPS(attributes->'$.tags', JSON_ARRAY('sale', 'clearance'));
```

Hãy xác nhận phiên bản server trước khi dùng hàm mới. Nếu ứng dụng cần lọc array thường xuyên trên tập dữ liệu lớn, hãy xem xét multi-valued index hoặc chuẩn hóa array thành bảng con.

## 4. Tạo và cập nhật JSON

### 4.1. Tạo tài liệu bằng SQL

Thay vì tự ghép chuỗi JSON trong ứng dụng, có thể dùng hàm tạo JSON để tránh lỗi dấu nháy và escaping:

```sql
SELECT JSON_OBJECT(
    'order_id', 9001,
    'status', 'PAID',
    'items', JSON_ARRAY(
        JSON_OBJECT('sku', 'KB-01', 'quantity', 2),
        JSON_OBJECT('sku', 'MS-02', 'quantity', 1)
    )
);
```

### 4.2. Thay đổi một phần tài liệu

Các hàm cập nhật JSON thường dùng:

| Hàm | Hành vi |
|---|---|
| `JSON_SET(doc, path, value, ...)` | Thêm hoặc thay thế giá trị tại path |
| `JSON_INSERT(doc, path, value, ...)` | Chỉ thêm khi path chưa tồn tại |
| `JSON_REPLACE(doc, path, value, ...)` | Chỉ thay thế khi path đã tồn tại |
| `JSON_REMOVE(doc, path, ...)` | Xóa phần tử tại path |
| `JSON_ARRAY_APPEND(doc, path, value, ...)` | Thêm phần tử vào cuối array |
| `JSON_ARRAY_INSERT(doc, path, value, ...)` | Chèn phần tử vào vị trí array được chỉ định |
| `JSON_MERGE_PATCH(doc, patch)` | Áp dụng quy tắc merge patch cho object |

Ví dụ cập nhật trạng thái và số lần thử:

```sql
UPDATE events
SET payload = JSON_SET(
    payload,
    '$.status', 'processed',
    '$.attempts', 2
)
WHERE id = 1;
```

Thêm một tag:

```sql
UPDATE products
SET attributes = JSON_ARRAY_APPEND(attributes, '$.tags', 'featured')
WHERE id = 42;
```

Xóa một thuộc tính:

```sql
UPDATE events
SET payload = JSON_REMOVE(payload, '$.temporary_token')
WHERE id = 1;
```

Các hàm trên tạo ra tài liệu JSON mới theo quy tắc của từng hàm. Khi cập nhật tài liệu lớn, hãy đo lượng dữ liệu, tần suất ghi và lock contention; không giả định thay đổi một path luôn chỉ ghi đúng vài byte vật lý.

### 4.3. Merge patch và giá trị null

`JSON_MERGE_PATCH` tuân theo ngữ nghĩa JSON Merge Patch: một thuộc tính trong patch có giá trị JSON null có thể biểu thị yêu cầu xóa thuộc tính khỏi object đích. Điều này khác với `JSON_SET`, nơi giá trị JSON null có thể được ghi vào path. Chọn hàm theo ý nghĩa cập nhật mà API yêu cầu.

## 5. Chuyển JSON thành hàng quan hệ với JSON_TABLE

JSON thuận tiện để lưu payload, nhưng báo cáo thường cần mỗi phần tử array trở thành một hàng để join, nhóm và tổng hợp. `JSON_TABLE` (MySQL 8.0.4 trở lên) chuyển tài liệu JSON thành một bảng quan hệ trong câu truy vấn.

Ví dụ lấy các dòng hàng trong payload sự kiện:

```sql
SELECT
    e.id AS event_id,
    e.payload->>'$.order_id' AS order_id,
    item.sku,
    item.quantity
FROM events AS e
JOIN JSON_TABLE(
    e.payload,
    '$.items[*]' COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        quantity INT PATH '$.quantity'
    )
) AS item ON TRUE
WHERE e.event_type = 'order.created';
```

Mỗi phần tử của `items` tạo ra một hàng trong kết quả. Có thể dùng `NULL ON EMPTY`, `ERROR ON EMPTY`, `NULL ON ERROR` hoặc `ERROR ON ERROR` trong định nghĩa cột `JSON_TABLE` để kiểm soát cách xử lý path thiếu hoặc giá trị không chuyển đổi được. Hãy chọn rõ hành vi thay vì để dữ liệu sai định dạng bị diễn giải ngoài ý muốn.

`JSON_TABLE` hữu ích cho báo cáo, import và chuyển đổi dữ liệu. Nếu ứng dụng thường xuyên join từng phần tử array với bảng khác, hãy cân nhắc lưu các phần tử đó thành bảng con quan hệ để có khóa ngoại, chỉ mục và ràng buộc rõ ràng.

## 6. Lập chỉ mục cho dữ liệu JSON

MySQL không tạo một B-tree thông thường cho mọi key bên trong một cột JSON. Nếu truy vấn thường xuyên lọc theo một thuộc tính, cần đưa giá trị đó vào cấu trúc có thể lập chỉ mục.

### 6.1. Generated column kết hợp index

Giả sử ứng dụng thường lọc sản phẩm theo `category` bên trong JSON:

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(160) NOT NULL,
    attributes JSON NOT NULL,
    category_code VARCHAR(40)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.category'))
        ) STORED,
    PRIMARY KEY (id),
    KEY idx_category_code (category_code)
) ENGINE=InnoDB;
```

Truy vấn có thể dùng generated column:

```sql
SELECT id, name
FROM products
WHERE category_code = 'phone';
```

Generated column có thể là `VIRTUAL` hoặc `STORED`; việc lập chỉ mục có thể làm được với cả hai trong những trường hợp được MySQL hỗ trợ. Chọn kiểu dựa trên chi phí tính toán, dung lượng và mẫu truy vấn. Dùng `EXPLAIN` để xác nhận optimizer thực sự chọn index.

### 6.2. Functional index

MySQL 8.0.13 trở lên hỗ trợ functional key parts. Có thể tạo index trên biểu thức thay vì khai báo một generated column hiển thị:

```sql
CREATE INDEX idx_priority
ON tasks ((CAST(payload->>'$.priority' AS UNSIGNED)));
```

Biểu thức trong truy vấn phải tương thích với biểu thức index để optimizer nhận diện. Với biểu thức phức tạp, generated column có tên thường dễ đọc, dễ kiểm tra metadata và dễ dùng nhất quán trong mã ứng dụng.

### 6.3. Multi-valued index cho JSON array

MySQL 8.0.17 trở lên hỗ trợ multi-valued index, cho phép một hàng đóng góp nhiều giá trị index từ một JSON array. Ví dụ:

```sql
CREATE INDEX idx_product_tags
ON products ((CAST(attributes->'$.tags' AS CHAR(32) ARRAY)));
```

Loại index này hữu ích cho một số phép kiểm tra membership trên array. Nó có các giới hạn về kiểu, biểu thức và toán tử được hỗ trợ; không thay thế hoàn toàn bảng con có một hàng cho mỗi tag. Nếu cần join, foreign key, metadata riêng cho từng tag hoặc truy vấn phức tạp, mô hình quan hệ thường dễ quản lý hơn.

### 6.4. Khi nào nên chuẩn hóa thay vì giữ JSON?

Hãy tách thuộc tính thành cột/bảng quan hệ khi:

- Thuộc tính có kiểu ổn định và là một phần bắt buộc của nghiệp vụ.
- Cần `NOT NULL`, `UNIQUE`, `CHECK` hoặc foreign key để bảo vệ dữ liệu.
- Thuộc tính thường xuyên được dùng trong join, group, sort hoặc filter.
- Array có phần tử cần định danh, cập nhật độc lập hoặc được tham chiếu từ bảng khác.
- Cần phân quyền theo thuộc tính hoặc quản lý lịch sử thay đổi chi tiết.

JSON phù hợp để mở rộng dữ liệu linh hoạt; nó không phải cách né thiết kế schema. Hãy giữ ranh giới rõ giữa dữ liệu cốt lõi và thuộc tính mở rộng.

## 7. Các kiểu dữ liệu không gian của MySQL

### 7.1. Hệ phân cấp Geometry

MySQL cung cấp kiểu cơ sở `GEOMETRY` và các kiểu con:

| Kiểu | Mô tả | Ví dụ sử dụng |
|---|---|---|
| `POINT` | Một điểm | Vị trí cửa hàng, thiết bị, khách hàng |
| `LINESTRING` | Một chuỗi điểm nối thành đường | Tuyến đường, lộ trình di chuyển |
| `POLYGON` | Vùng được bao bởi các vòng khép kín | Khu vực giao hàng, ranh giới quận |
| `MULTIPOINT` | Tập hợp nhiều điểm | Các điểm đo hoặc điểm đón |
| `MULTILINESTRING` | Tập hợp nhiều đường | Nhiều đoạn đường |
| `MULTIPOLYGON` | Tập hợp nhiều vùng | Khu vực gồm nhiều phần tách rời |
| `GEOMETRYCOLLECTION` | Tập hợp nhiều geometry khác loại | Tập dữ liệu hình học hỗn hợp |

Các kiểu này dùng biểu diễn hình học, không tự mang ý nghĩa nghiệp vụ. Ví dụ một `POINT` có thể là cửa hàng hoặc vị trí tài xế; ứng dụng cần xác định ý nghĩa bằng bảng, cột hoặc thuộc tính liên quan.

### 7.2. Spatial Reference System (SRS) và SRID

SRID (Spatial Reference System Identifier) xác định hệ tham chiếu không gian của một geometry. SRS mô tả hệ tọa độ, thứ tự trục, đơn vị và các thông tin cần thiết để diễn giải tọa độ.

Một số điểm quan trọng:

- SRID `0` là hệ tọa độ Cartesian mặc định, không gắn với một hệ tọa độ địa lý cụ thể.
- SRID `4326` thường được dùng cho WGS 84, phổ biến trong dữ liệu GPS và GeoJSON.
- Không so sánh hoặc tính toán geometry thuộc các SRS khác nhau một cách tùy tiện.
- Cùng một cặp số có thể mang ý nghĩa khác nhau nếu SRID hoặc thứ tự trục khác nhau.

Từ MySQL 8.0, server có hỗ trợ SRS địa lý được định nghĩa trong data dictionary. Có thể tra cứu SRS bằng `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS` trên các phiên bản hỗ trợ.

### 7.3. Thứ tự trục tọa độ

Một lỗi phổ biến là nhầm kinh độ/vĩ độ. Nhiều API bản đồ truyền tọa độ theo thứ tự longitude, latitude; một số SRS như EPSG:4326 định nghĩa thứ tự trục latitude, longitude. MySQL mặc định có thể tuân theo thứ tự trục được khai báo trong SRS.

Khi dữ liệu đầu vào được xác định rõ là longitude trước latitude, có thể chỉ định tùy chọn `axis-order=long-lat` trong hàm tạo geometry. Tùy chọn axis-order cho các hàm không gian được hỗ trợ từ MySQL 8.0.12:

```sql
SET @store_point = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);
```

Ví dụ minh họa một vị trí gần trung tâm TP. Hồ Chí Minh, với kinh độ `106.7009` và vĩ độ `10.7769`. Luôn xác nhận định dạng đầu vào của nguồn dữ liệu và dùng cùng quy ước khi đọc/ghi. Đảo thứ tự trục có thể tạo geometry hợp lệ về cú pháp nhưng nằm sai vị trí trên bản đồ.

## 8. Lưu và đọc dữ liệu không gian

### 8.1. Tạo bảng vị trí

Với MySQL 8.0, có thể giới hạn cột chỉ chứa geometry thuộc SRID 4326 bằng thuộc tính `SRID`:

```sql
CREATE TABLE stores (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (id),
    SPATIAL INDEX idx_location (location)
) ENGINE=InnoDB;
```

`POINT NOT NULL SRID 4326` buộc cột chứa điểm không NULL và dùng đúng SRID. Spatial index của InnoDB dùng cấu trúc R-tree cho dữ liệu không gian. Cột được giới hạn SRID và khai báo NOT NULL là điều kiện quan trọng để optimizer có thể tận dụng spatial index theo các quy tắc của MySQL.

### 8.2. Thêm điểm

```sql
INSERT INTO stores (name, location)
VALUES (
    'Cửa hàng trung tâm',
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    )
);
```

Đọc tọa độ dưới dạng WKT (Well-Known Text):

```sql
SELECT
    id,
    name,
    ST_AsText(location) AS location_wkt,
    ST_SRID(location) AS srid,
    ST_GeometryType(location) AS geometry_type
FROM stores;
```

`ST_AsText` chuyển geometry thành chuỗi WKT; `ST_SRID` trả SRID; `ST_GeometryType` trả loại geometry. Nếu trao đổi với ứng dụng bản đồ, có thể dùng `ST_AsGeoJSON` và `ST_GeomFromGeoJSON` ở các phiên bản hỗ trợ. Cần thống nhất SRID và axis order giữa MySQL và ứng dụng.

### 8.3. Gán SRID không giống chuyển hệ tọa độ

`ST_SRID(geometry, srid)` dùng để gán SRID cho geometry; nó không tự chuyển đổi các con số tọa độ sang hệ tham chiếu mới. Nếu tọa độ hiện đang ở một hệ khác, chỉ đổi nhãn SRID sẽ làm dữ liệu bị diễn giải sai.

Với MySQL 8.0.13 trở lên, `ST_Transform` có thể thực hiện phép biến đổi tọa độ thực sự khi cần chuyển giữa các SRS tương thích:

```sql
SELECT ST_Transform(location, 3857)
FROM stores;
```

Hãy kiểm tra phiên bản, SRS nguồn/đích và đơn vị trước khi dùng. Không phải mọi SRID đều có đủ thông tin hoặc phép biến đổi được hỗ trợ.

## 9. Hàm và phép toán không gian

### 9.1. Kiểm tra hình học

Các hàm thường dùng:

| Hàm | Ý nghĩa |
|---|---|
| `ST_GeomFromText(wkt, srid)` | Tạo geometry từ WKT |
| `ST_AsText(g)` | Chuyển geometry thành WKT |
| `ST_GeomFromGeoJSON(doc)` | Tạo geometry từ GeoJSON trên phiên bản hỗ trợ |
| `ST_AsGeoJSON(g)` | Chuyển geometry thành GeoJSON trên phiên bản hỗ trợ |
| `ST_SRID(g)` | Đọc SRID của geometry |
| `ST_GeometryType(g)` | Đọc loại geometry |
| `ST_IsValid(g)` | Kiểm tra geometry có hợp lệ theo quy tắc hình học không |
| `ST_Envelope(g)` | Lấy hình chữ nhật bao nhỏ nhất (minimum bounding rectangle) |

Geometry hợp lệ về cú pháp chưa chắc phản ánh đúng vị trí địa lý hoặc quy tắc nghiệp vụ. Ví dụ một polygon có thể tự cắt hoặc có vòng không hợp lệ; hãy kiểm tra tính hợp lệ và quy tắc dữ liệu trước khi dùng trong tính toán.

### 9.2. Quan hệ giữa các hình học

Các hàm không gian chính xác thường dùng:

- `ST_Contains(a, b)`: hình `a` chứa hình `b` theo quan hệ hình học.
- `ST_Within(a, b)`: hình `a` nằm trong hình `b`.
- `ST_Intersects(a, b)`: hai hình có giao nhau.
- `ST_Disjoint(a, b)`: hai hình không giao nhau.
- `ST_Touches(a, b)`: hai hình chạm nhau ở biên nhưng phần trong không giao nhau.
- `ST_Equals(a, b)`: hai hình biểu diễn cùng một tập điểm.
- `ST_Distance(a, b)`: tính khoảng cách theo SRS và quy tắc của hàm.

Ví dụ kiểm tra cửa hàng có nằm trong vùng giao hàng:

```sql
SET @delivery_zone = ST_GeomFromText(
    'POLYGON((106.60 10.70, 106.82 10.70, 106.82 10.86, 106.60 10.86, 106.60 10.70))',
    4326,
    'axis-order=long-lat'
);

SELECT id, name
FROM stores
WHERE ST_Contains(@delivery_zone, location);
```

Đây là ví dụ hình chữ nhật đơn giản; vùng phục vụ thực tế thường cần polygon theo ranh giới địa lý chính xác. Hai geometry phải có SRS tương thích và tọa độ đúng thứ tự trục.

### 9.3. Khoảng cách và đơn vị

Khoảng cách phải được diễn giải theo hệ tham chiếu và hàm được chọn. Không lấy kết quả của phép tính trên tọa độ kinh/vĩ độ rồi mặc định đó là mét hoặc kilomet.

`ST_Distance_Sphere(g1, g2)` tính khoảng cách theo mô hình hình cầu và trả kết quả theo mét. Đây là phép tính xấp xỉ, phù hợp cho một số bài toán tìm kiếm gần đúng. Với yêu cầu độ chính xác cao hoặc vùng địa lý rộng, hãy chọn phép tính phù hợp với SRS địa lý, ellipsoid và phiên bản MySQL; kiểm tra đơn vị đầu ra trong tài liệu hàm.

Ví dụ so sánh khoảng cách gần đúng từ một điểm:

```sql
SET @origin = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);

SELECT
    id,
    name,
    ST_Distance_Sphere(location, @origin) AS distance_meters
FROM stores
ORDER BY distance_meters
LIMIT 10;
```

Truy vấn này sắp xếp theo khoảng cách nhưng có thể phải tính cho nhiều hàng. Với bảng lớn, hãy lọc trước bằng bounding box/spatial index rồi mới tính khoảng cách chính xác hoặc xấp xỉ cho các ứng viên.

## 10. Spatial index và tối ưu truy vấn không gian

### 10.1. Spatial index hoạt động thế nào?

Spatial index của MySQL dùng R-tree để tổ chức các minimum bounding rectangle (MBR) của geometry. MBR là hình chữ nhật nhỏ nhất bao quanh hình học. Chỉ mục này giúp tìm nhanh các đối tượng có vùng bao giao với vùng tìm kiếm.

MBR chỉ là bộ lọc ứng viên. Hai hình có MBR giao nhau chưa chắc bản thân hai hình giao nhau. Với các truy vấn cần quan hệ hình học chính xác, cần dùng predicate chính xác như `ST_Contains` hoặc `ST_Intersects` sau bước lọc phù hợp.

### 10.2. Tạo spatial index

```sql
ALTER TABLE stores
ADD SPATIAL INDEX idx_location (location);
```

Trước khi tạo index, kiểm tra cột geometry có `NOT NULL`, SRID có được giới hạn phù hợp và storage engine có hỗ trợ spatial index. InnoDB hỗ trợ spatial index bằng R-tree. Với cột không giới hạn SRID, optimizer có thể không sử dụng index theo cách mong muốn; kiểm tra điều kiện cụ thể theo phiên bản MySQL.

### 10.3. Lọc theo bounding rectangle

Ví dụ tìm các điểm trong vùng chữ nhật ứng viên:

```sql
SET @search_box = ST_GeomFromText(
    'POLYGON((106.60 10.70, 106.82 10.70, 106.82 10.86, 106.60 10.86, 106.60 10.70))',
    4326,
    'axis-order=long-lat'
);

SELECT id, name
FROM stores
WHERE MBRContains(@search_box, location);
```

`MBRContains` xét hình chữ nhật bao. Nếu vùng tìm kiếm là polygon phức tạp, kết quả có thể chứa điểm nằm trong bounding rectangle nhưng ngoài polygon thật. Khi cần chính xác, thêm điều kiện hình học:

```sql
SELECT id, name
FROM stores
WHERE MBRContains(@search_box, location)
  AND ST_Contains(@delivery_zone, location);
```

Trong ví dụ này, `@delivery_zone` là polygon nghiệp vụ đã được tạo với SRID và axis order đúng. Điều kiện MBR giúp thu hẹp ứng viên; `ST_Contains` kiểm tra quan hệ thực.

### 10.4. Xác nhận kế hoạch thực thi

```sql
EXPLAIN
SELECT id, name
FROM stores
WHERE MBRContains(@search_box, location);
```

Kiểm tra `key`, `type`, số hàng ước lượng và phần điều kiện lọc. Optimizer có thể không chọn spatial index nếu bảng nhỏ, điều kiện không phù hợp, thống kê hoặc cấu hình khiến một kế hoạch khác rẻ hơn. Không kết luận index hỏng chỉ vì một truy vấn không dùng nó; hãy kiểm tra DDL, SRID, nullability, dữ liệu và `EXPLAIN`.

## 11. Kết hợp JSON với dữ liệu không gian

Một ứng dụng giao hàng có thể nhận sự kiện từ thiết bị dưới dạng JSON, trong đó có trạng thái và tọa độ:

```json
{
  "device_id": "DRV-100",
  "status": "moving",
  "position": {"longitude": 106.7009, "latitude": 10.7769},
  "speed_kmh": 28.5,
  "recorded_at": "2026-11-19T09:30:00Z"
}
```

Nếu cần lưu payload gốc để audit hoặc tương thích với nhiều phiên bản thiết bị, có thể lưu JSON. Nếu cần tìm tài xế trong một vùng, nên chuyển tọa độ thành `POINT` có SRID rõ ràng và lập spatial index:

```sql
CREATE TABLE driver_positions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id VARCHAR(40) NOT NULL,
    payload JSON NOT NULL,
    location POINT NOT NULL SRID 4326,
    recorded_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_device_time (device_id, recorded_at),
    SPATIAL INDEX idx_driver_location (location)
) ENGINE=InnoDB;
```

Khi nhận payload, ứng dụng hoặc pipeline ghi cả JSON và geometry:

```sql
INSERT INTO driver_positions (device_id, payload, location, recorded_at)
VALUES (
    'DRV-100',
    '{"status":"moving","speed_kmh":28.5}',
    ST_GeomFromText('POINT(106.7009 10.7769)', 4326, 'axis-order=long-lat'),
    '2026-11-19 09:30:00'
);
```

Trong hệ thống thực tế, cần chuyển timestamp theo timezone rõ ràng, xác thực latitude/longitude nằm trong miền hợp lệ, kiểm tra payload và tránh để JSON cùng các cột scalar bị lệch nhau. Nếu một giá trị được dùng thường xuyên cho truy vấn, hãy cân nhắc đưa nó ra cột riêng thay vì chỉ lưu trong JSON.

## 12. Những sai lầm thường gặp

- **Lưu JSON vào `TEXT` rồi xem như JSON native:** cột `JSON` có kiểm tra hợp lệ và cách lưu nội bộ riêng; text cần tự kiểm tra.
- **Dùng JSON cho mọi thuộc tính:** dữ liệu cốt lõi cần khóa, join và ràng buộc thường nên là cột/bảng quan hệ.
- **So sánh JSON number với chuỗi tùy tiện:** dùng kiểu dữ liệu rõ ràng và `CAST` khi cần.
- **Không phân biệt SQL NULL, JSON null và path không tồn tại:** ba trường hợp có ý nghĩa khác nhau.
- **Cho rằng JSON tự có index trên mọi key:** dùng generated column, functional index hoặc multi-valued index phù hợp.
- **Coi `VIRTUAL` là miễn phí:** biểu thức vẫn cần tính khi đọc và index vẫn có chi phí.
- **Đảo longitude/latitude:** luôn xác nhận axis order và SRID của nguồn dữ liệu.
- **Đổi SRID nhưng không transform tọa độ:** `ST_SRID` không phải phép chiếu tọa độ.
- **Coi MBR predicate là quan hệ hình học chính xác:** dùng predicate `ST_...` phù hợp để xác nhận kết quả.
- **Coi kết quả khoảng cách luôn là mét:** xác nhận SRS và đơn vị của hàm; `ST_Distance_Sphere` trả mét.
- **Tạo spatial index trên cột không phù hợp:** kiểm tra `NOT NULL`, SRID restriction, engine và kế hoạch thực thi.

## 13. Checklist trước khi thiết kế

- Dữ liệu là thuộc tính quan hệ ổn định, tài liệu JSON linh hoạt hay hình học không gian?
- Nếu dùng JSON, phần nào cần lọc/join thường xuyên và có nên đưa ra cột quan hệ không?
- Ứng dụng phân biệt SQL NULL, JSON null và thuộc tính không tồn tại như thế nào?
- Có cần `JSON_TABLE`, generated column, functional index hoặc multi-valued index không?
- Phiên bản MySQL hiện tại có hỗ trợ các hàm và index đang dự định dùng không?
- Với dữ liệu không gian, SRID, SRS, đơn vị và thứ tự trục là gì?
- Tọa độ đầu vào là longitude-latitude hay latitude-longitude?
- Cột geometry có `NOT NULL` và giới hạn SRID phù hợp để dùng spatial index không?
- Truy vấn cần bounding-box filtering hay quan hệ hình học chính xác?
- Đã kiểm tra `EXPLAIN`, dữ liệu mẫu và các trường hợp tọa độ/JSON sai định dạng chưa?

## Kết luận

Kiểu `JSON` giúp lưu dữ liệu bán cấu trúc và truy vấn theo path; generated column, functional index, multi-valued index và `JSON_TABLE` kết nối tài liệu JSON với truy vấn quan hệ. Các kiểu không gian như `POINT`, `LINESTRING` và `POLYGON` biểu diễn tọa độ/hình học; SRID xác định hệ tham chiếu, spatial function thực hiện phép toán và R-tree index tăng tốc lọc vùng. Hãy giữ thuộc tính nghiệp vụ ổn định trong cột quan hệ, kiểm soát cấu trúc JSON, xác định rõ SRID/axis order và đo kế hoạch thực thi trước khi triển khai trên dữ liệu lớn.
