# So sánh mô hình quan hệ với `jsonb` trên cùng yêu cầu

PostgreSQL hỗ trợ cả mô hình dữ liệu quan hệ truyền thống và kiểu dữ liệu `jsonb`. Hai cách lưu trữ có thể cùng đáp ứng một yêu cầu nghiệp vụ, nhưng khác nhau về cách biểu diễn cấu trúc, ràng buộc toàn vẹn, truy vấn, index, cập nhật và thay đổi schema. Muốn chọn đúng, cần so sánh chúng trên cùng dữ liệu, cùng truy vấn và cùng điều kiện tải.

Bài thực hành này dùng một catalog sản phẩm có hai nhóm hàng: laptop và điện thoại. Mỗi sản phẩm có các trường chung như SKU, tên, giá, tiền tệ và trạng thái kinh doanh. Mỗi nhóm có thông số riêng: laptop có RAM, dung lượng lưu trữ và kích thước màn hình; điện thoại có dung lượng pin và độ phân giải camera. Hệ thống cần tìm sản phẩm theo nhóm, trạng thái, giá và thông số; cập nhật một thông số; đồng thời tạo báo cáo tổng hợp.

Ta triển khai cùng yêu cầu bằng hai mô hình:

- **Mô hình quan hệ:** các thuộc tính đã biết được lưu trong các cột có kiểu dữ liệu rõ ràng và constraint.
- **Mô hình tài liệu `jsonb`:** các trường chung vẫn là cột quan hệ, còn thông số theo từng nhóm được lưu trong một object JSONB.

Đây là hai phương án thay thế cho cùng use case. Phần cuối cũng trình bày cách kết hợp chúng khi hệ thống có cả thuộc tính ổn định và thuộc tính thay đổi thường xuyên.

## 1. Xác định yêu cầu trước khi thiết kế

Một thiết kế chỉ có thể được so sánh công bằng khi hai phương án phải đáp ứng cùng hợp đồng dữ liệu và cùng truy vấn.

### Dữ liệu sản phẩm

Mỗi sản phẩm có các trường chung:

| Trường | Kiểu logic | Quy tắc |
|---|---|---|
| `id` | Số nguyên 64 bit | Khóa chính |
| `sku` | Chuỗi | Bắt buộc, duy nhất |
| `category` | Chuỗi mã nhóm | `laptop` hoặc `phone` trong ví dụ |
| `name` | Chuỗi | Bắt buộc |
| `price` | Số thập phân | Không âm |
| `currency` | Mã tiền tệ | Bắt buộc |
| `available` | Boolean | Mặc định `true` |

Thông số riêng:

| Nhóm | Thuộc tính | Kiểu logic | Ví dụ |
|---|---|---|---|
| Laptop | `ram_gb` | Số nguyên | 16 |
| Laptop | `storage_gb` | Số nguyên | 512 |
| Laptop | `screen_inches` | Số thập phân | 14.0 |
| Phone | `battery_mah` | Số nguyên | 5000 |
| Phone | `camera_mp` | Số thập phân | 50.0 |

Các thao tác cần hỗ trợ:

1. Thêm sản phẩm và bảo đảm SKU duy nhất.
2. Kiểm tra dữ liệu thông số phù hợp với nhóm sản phẩm.
3. Tìm laptop đang bán có giá tối đa 1.500 USD và RAM từ 16 GB trở lên.
4. Tìm điện thoại có pin từ 5.000 mAh trở lên và camera từ 50 MP trở lên.
5. Cập nhật RAM của một laptop.
6. Thống kê số sản phẩm và giá trung bình theo nhóm.
7. Mở rộng mô hình khi xuất hiện thông số mới.

## 2. Phương án A: mô hình quan hệ

Với các thuộc tính đã biết và có kiểu dữ liệu rõ ràng, có thể đặt chúng thành các cột. Trong ví dụ nhỏ này, một bảng chứa trường chung và trường riêng của cả hai nhóm. Constraint bảo đảm mỗi hàng có đúng nhóm thông số phù hợp.

### Tạo bảng

```sql
CREATE SCHEMA IF NOT EXISTS catalog_rel;

CREATE TABLE catalog_rel.product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category text NOT NULL
        CHECK (category IN ('laptop', 'phone')),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,

    ram_gb integer,
    storage_gb integer,
    screen_inches numeric(5, 2),
    battery_mah integer,
    camera_mp numeric(6, 2),

    CHECK (
        (
            category = 'laptop'
            AND ram_gb IS NOT NULL AND ram_gb BETWEEN 1 AND 512
            AND storage_gb IS NOT NULL AND storage_gb BETWEEN 32 AND 32768
            AND screen_inches IS NOT NULL AND screen_inches BETWEEN 8 AND 30
            AND battery_mah IS NULL
            AND camera_mp IS NULL
        )
        OR
        (
            category = 'phone'
            AND battery_mah IS NOT NULL AND battery_mah BETWEEN 500 AND 30000
            AND camera_mp IS NOT NULL AND camera_mp BETWEEN 1 AND 500
            AND ram_gb IS NULL
            AND storage_gb IS NULL
            AND screen_inches IS NULL
        )
    )
);
```

Constraint cuối cùng yêu cầu laptop có đủ ba thông số laptop và không có thông số phone; phone có đủ hai thông số phone và không có thông số laptop. Các điều kiện `IS NOT NULL` rất quan trọng vì biểu thức `CHECK` của PostgreSQL được xem là đạt khi kết quả là `TRUE` hoặc `NULL`. Chỉ viết `ram_gb BETWEEN 1 AND 512` sẽ không đủ để cấm `NULL`.

Đây là cách phù hợp khi tập thuộc tính theo nhóm tương đối nhỏ và ổn định. Khi có nhiều nhóm với hàng chục hoặc hàng trăm cột riêng, bảng sẽ thưa, constraint phức tạp và mỗi thay đổi cấu trúc có thể cần migration. Khi đó có thể tách bảng subtype hoặc dùng bảng thuộc tính có kiểu.

### Thêm dữ liệu mẫu

```sql
INSERT INTO catalog_rel.product (
    sku, category, name, price, currency, available,
    ram_gb, storage_gb, screen_inches
)
VALUES
    ('LAP-001', 'laptop', 'Notebook A', 1299.00, 'USD', true,
     16, 512, 14.00),
    ('LAP-002', 'laptop', 'Notebook B', 999.00, 'USD', true,
     32, 1024, 16.00);

INSERT INTO catalog_rel.product (
    sku, category, name, price, currency, available,
    battery_mah, camera_mp
)
VALUES
    ('PHN-001', 'phone', 'Phone A', 799.00, 'USD', true,
     5000, 50.00),
    ('PHN-002', 'phone', 'Phone B', 599.00, 'USD', true,
     4500, 48.00);
```

Nếu chèn laptop mà thiếu `ram_gb`, hoặc gán `battery_mah` cho laptop, constraint sẽ từ chối hàng. PostgreSQL kiểm tra dữ liệu tại database nên các client khác nhau vẫn phải tuân thủ cùng quy tắc.

## 3. Phương án B: trường thông số trong `jsonb`

Ở phương án tài liệu, các trường chung vẫn là cột quan hệ để có khóa, kiểu dữ liệu và index quen thuộc. Các thông số riêng được đặt trong object `attributes`.

### Tạo bảng

```sql
CREATE SCHEMA IF NOT EXISTS catalog_doc;

CREATE TABLE catalog_doc.product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category text NOT NULL
        CHECK (category IN ('laptop', 'phone')),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,
    attributes jsonb NOT NULL,

    CHECK (jsonb_typeof(attributes) = 'object'),

    CHECK (
        CASE category
            WHEN 'laptop' THEN
                CASE
                    WHEN jsonb_typeof(attributes -> 'ram_gb') = 'number'
                     AND jsonb_typeof(attributes -> 'storage_gb') = 'number'
                     AND jsonb_typeof(attributes -> 'screen_inches') = 'number'
                    THEN
                        (attributes ->> 'ram_gb')::numeric BETWEEN 1 AND 512
                        AND (attributes ->> 'ram_gb')::numeric =
                            trunc((attributes ->> 'ram_gb')::numeric)
                        AND (attributes ->> 'storage_gb')::numeric BETWEEN 32 AND 32768
                        AND (attributes ->> 'storage_gb')::numeric =
                            trunc((attributes ->> 'storage_gb')::numeric)
                        AND (attributes ->> 'screen_inches')::numeric BETWEEN 8 AND 30
                    ELSE false
                END
            WHEN 'phone' THEN
                CASE
                    WHEN jsonb_typeof(attributes -> 'battery_mah') = 'number'
                     AND jsonb_typeof(attributes -> 'camera_mp') = 'number'
                    THEN
                        (attributes ->> 'battery_mah')::numeric BETWEEN 500 AND 30000
                        AND (attributes ->> 'battery_mah')::numeric =
                            trunc((attributes ->> 'battery_mah')::numeric)
                        AND (attributes ->> 'camera_mp')::numeric BETWEEN 1 AND 500
                    ELSE false
                END
            ELSE false
        END
    )
);
```

Constraint dùng `jsonb_typeof` để kiểm tra kiểu JSON trước khi chuyển giá trị sang `numeric`. Các nhánh `CASE` giúp không ép kiểu khi key bị thiếu hoặc chứa kiểu JSON không phù hợp. Trong ví dụ, các key bắt buộc phải tồn tại và đúng kiểu; key bổ sung vẫn được chấp nhận. Nếu hợp đồng yêu cầu cấm key ngoài danh sách, cần bổ sung kiểm tra tập key được phép.

`jsonb` lưu dữ liệu theo dạng nhị phân đã phân tích. Nó không giữ nguyên khoảng trắng, thứ tự key hoặc các key trùng lặp như văn bản JSON đầu vào. Nếu cần giữ nguyên payload gốc để audit hoặc chữ ký số, hãy lưu riêng chuỗi gốc theo yêu cầu.

### Thêm dữ liệu mẫu

```sql
INSERT INTO catalog_doc.product (
    sku, category, name, price, currency, available, attributes
)
VALUES
    (
        'LAP-001', 'laptop', 'Notebook A', 1299.00, 'USD', true,
        '{"ram_gb": 16, "storage_gb": 512, "screen_inches": 14.00}'::jsonb
    ),
    (
        'LAP-002', 'laptop', 'Notebook B', 999.00, 'USD', true,
        '{"ram_gb": 32, "storage_gb": 1024, "screen_inches": 16.00}'::jsonb
    ),
    (
        'PHN-001', 'phone', 'Phone A', 799.00, 'USD', true,
        '{"battery_mah": 5000, "camera_mp": 50.00}'::jsonb
    ),
    (
        'PHN-002', 'phone', 'Phone B', 599.00, 'USD', true,
        '{"battery_mah": 4500, "camera_mp": 48.00}'::jsonb
    );
```

Một điểm quan trọng là constraint trong database vẫn cần được thiết kế. Việc dùng JSONB không tự động bảo đảm rằng `ram_gb` là số nguyên, `battery_mah` có giá trị hợp lệ hoặc laptop luôn có đủ key cần thiết.

## 4. So sánh cùng truy vấn tìm laptop

Yêu cầu: tìm tối đa 50 laptop đang bán, giá không quá 1.500 USD và RAM ít nhất 16 GB; sắp xếp theo giá tăng dần.

### Truy vấn trên mô hình quan hệ

```sql
SELECT
    id,
    sku,
    name,
    price,
    ram_gb,
    storage_gb,
    screen_inches
FROM catalog_rel.product
WHERE category = 'laptop'
  AND available
  AND currency = 'USD'
  AND price <= 1500
  AND ram_gb >= 16
ORDER BY price, id
LIMIT 50;
```

Điều kiện trên cột có kiểu dữ liệu cụ thể. Planner có thể dùng thống kê cột, B-tree index và constraint thông thường. Truy vấn không cần chuyển chuỗi thành số ở thời điểm chạy.

### Truy vấn trên mô hình JSONB

```sql
SELECT
    id,
    sku,
    name,
    price,
    (attributes ->> 'ram_gb')::integer AS ram_gb,
    (attributes ->> 'storage_gb')::integer AS storage_gb,
    (attributes ->> 'screen_inches')::numeric AS screen_inches
FROM catalog_doc.product
WHERE category = 'laptop'
  AND available
  AND currency = 'USD'
  AND price <= 1500
  AND (attributes ->> 'ram_gb')::integer >= 16
ORDER BY price, id
LIMIT 50;
```

`->>` trích xuất giá trị JSONB thành text, sau đó truy vấn chuyển thành kiểu số để so sánh. Constraint bảo đảm giá trị RAM là số nguyên trong miền hợp lệ. Nếu dữ liệu cũ chưa được xác thực hoặc constraint không có, phép cast có thể thất bại khi gặp giá trị không phải số.

Hai truy vấn trả cùng ý nghĩa dữ liệu. Để so sánh công bằng, cần nạp cùng tập sản phẩm vào cả hai bảng, giữ cùng index tương đương, chạy cùng tham số và cùng mức tải.

## 5. So sánh truy vấn tìm điện thoại

Yêu cầu: tìm điện thoại đang bán có pin tối thiểu 5.000 mAh, camera ít nhất 50 MP và giá dưới 1.000 USD.

### Mô hình quan hệ

```sql
SELECT id, sku, name, price, battery_mah, camera_mp
FROM catalog_rel.product
WHERE category = 'phone'
  AND available
  AND currency = 'USD'
  AND price < 1000
  AND battery_mah >= 5000
  AND camera_mp >= 50
ORDER BY price, id;
```

### Mô hình JSONB

```sql
SELECT
    id,
    sku,
    name,
    price,
    (attributes ->> 'battery_mah')::integer AS battery_mah,
    (attributes ->> 'camera_mp')::numeric AS camera_mp
FROM catalog_doc.product
WHERE category = 'phone'
  AND available
  AND currency = 'USD'
  AND price < 1000
  AND (attributes ->> 'battery_mah')::integer >= 5000
  AND (attributes ->> 'camera_mp')::numeric >= 50
ORDER BY price, id;
```

Sự khác biệt về cú pháp nhỏ, nhưng mô hình quan hệ biểu diễn kiểu dữ liệu trực tiếp trong schema. JSONB đòi hỏi ứng dụng và database cùng tuân thủ quy ước tên key, kiểu JSON và cách cast. Nếu một client ghi `"5000"` thay vì `5000`, constraint mẫu sẽ từ chối vì kiểu JSON string khác JSON number.

## 6. Index cho mô hình quan hệ

Index cần phản ánh điều kiện lọc, thứ tự sắp xếp và tần suất truy vấn. Với truy vấn laptop, có thể thử partial index:

```sql
CREATE INDEX product_rel_laptop_search_idx
ON catalog_rel.product (price, ram_gb, id)
WHERE category = 'laptop'
  AND available
  AND currency = 'USD';
```

Với điện thoại:

```sql
CREATE INDEX product_rel_phone_search_idx
ON catalog_rel.product (price, battery_mah, camera_mp, id)
WHERE category = 'phone'
  AND available
  AND currency = 'USD';
```

Partial index chỉ lưu các hàng thỏa predicate, giảm kích thước khi truy vấn luôn lọc cùng điều kiện. Thứ tự cột B-tree rất quan trọng: cột đầu tiên quyết định phạm vi scan hiệu quả; khi có điều kiện range ở cột đầu, các cột sau có thể chủ yếu dùng để lọc hoặc cung cấp thứ tự. Hãy so sánh các thứ tự index bằng `EXPLAIN`, không giả định một index duy nhất tối ưu cho mọi điều kiện.

Các index thông thường cũng có thể phục vụ lookup theo SKU:

```sql
-- Đã có UNIQUE constraint trên sku nên PostgreSQL đã tạo unique index.
SELECT id, name, price
FROM catalog_rel.product
WHERE sku = 'LAP-001';
```

Không tạo thêm một index trùng với unique index đã có.

## 7. Index cho JSONB

JSONB có nhiều chiến lược index. Chọn loại index theo toán tử truy vấn.

### GIN cho containment và key search

```sql
CREATE INDEX product_doc_attributes_gin_idx
ON catalog_doc.product
USING gin (attributes jsonb_path_ops);
```

GIN với `jsonb_path_ops` phù hợp cho các truy vấn containment `@>` và một số truy vấn JSONPath được hỗ trợ. Ví dụ kiểm tra sản phẩm có đúng một tập key/value:

```sql
SELECT id, sku, name
FROM catalog_doc.product
WHERE category = 'laptop'
  AND attributes @> '{"ram_gb": 16}'::jsonb;
```

Truy vấn containment trên so sánh giá trị tương đương, không diễn đạt điều kiện số `ram_gb >= 16`. Ngoài ra, `jsonb_path_ops` không hỗ trợ mọi toán tử JSONB; ví dụ toán tử key-exists `?` cần operator class phù hợp khác như `jsonb_ops`.

### B-tree expression index cho điều kiện range

GIN không phải lựa chọn tự động tốt nhất cho phép so sánh số lớn hơn/nhỏ hơn. Với truy vấn RAM tối thiểu, có thể tạo expression index:

```sql
CREATE INDEX product_doc_laptop_ram_price_idx
ON catalog_doc.product (
    ((attributes ->> 'ram_gb')::integer),
    price,
    id
)
WHERE category = 'laptop'
  AND available
  AND currency = 'USD';
```

Biểu thức index phải khớp với biểu thức truy vấn. Constraint ở trên bảo đảm RAM là số nguyên hợp lệ trước khi index được tạo. Nếu dữ liệu không hợp lệ tồn tại, việc tạo expression index có thể thất bại khi cast.

Với truy vấn phone, tạo expression index tương ứng:

```sql
CREATE INDEX product_doc_phone_battery_price_idx
ON catalog_doc.product (
    ((attributes ->> 'battery_mah')::integer),
    price,
    id
)
WHERE category = 'phone'
  AND available
  AND currency = 'USD';
```

Nếu truy vấn thường lọc đồng thời camera, có thể cân nhắc thêm expression index cho `camera_mp`, nhưng mỗi index làm tăng dung lượng và chi phí ghi. Cần benchmark để xác định lợi ích thực tế.

### Generated column để đơn giản hóa truy vấn

Nếu một key JSONB được truy vấn thường xuyên, có thể biểu diễn nó bằng generated column:

```sql
ALTER TABLE catalog_doc.product
ADD COLUMN ram_gb integer
GENERATED ALWAYS AS ((attributes ->> 'ram_gb')::integer) STORED;

CREATE INDEX product_doc_ram_gb_idx
ON catalog_doc.product (ram_gb)
WHERE category = 'laptop';
```

Generated column lưu giá trị được tính từ JSONB, giúp truy vấn và index dễ đọc hơn. Phép cast vẫn cần dữ liệu nguồn hợp lệ; trong ví dụ constraint đã bảo đảm điều đó. Generated column stored chiếm dung lượng và cần tính đến khi cập nhật JSONB. Hỗ trợ và các giới hạn của generated column phụ thuộc phiên bản PostgreSQL; kiểm tra tài liệu phiên bản đang triển khai.

## 8. Cập nhật một thuộc tính

### Cập nhật trên mô hình quan hệ

```sql
UPDATE catalog_rel.product
SET ram_gb = 32
WHERE sku = 'LAP-001'
  AND category = 'laptop';
```

Kiểu dữ liệu và constraint được kiểm tra trực tiếp. Nếu giá trị vượt miền cho phép, câu lệnh thất bại. Cột có thể được tham chiếu trong index, constraint, view và báo cáo bằng tên rõ ràng.

### Cập nhật một key trong JSONB

```sql
UPDATE catalog_doc.product
SET attributes = jsonb_set(
    attributes,
    '{ram_gb}',
    to_jsonb(32),
    false
)
WHERE sku = 'LAP-001'
  AND category = 'laptop';
```

Tham số cuối `false` có nghĩa không tạo key nếu key chưa tồn tại. Nếu đường dẫn không tồn tại, `jsonb_set` trả về giá trị ban đầu. Dùng `true` nếu chủ đích cho phép tạo key mới. `to_jsonb(32)` tạo JSON number; nếu truyền `'32'::text` qua `to_jsonb`, kết quả sẽ là JSON string và constraint mẫu từ chối.

### Cập nhật nhiều key

```sql
UPDATE catalog_doc.product
SET attributes = attributes ||
    '{"ram_gb": 32, "storage_gb": 1024}'::jsonb
WHERE sku = 'LAP-001'
  AND category = 'laptop';
```

Toán tử `||` ghép hai object ở mức top-level; với key trùng, giá trị bên phải thay thế giá trị bên trái. Đây không phải phép merge đệ quy cho các object lồng nhau. Nếu cần cập nhật sâu, dùng `jsonb_set` với đường dẫn cụ thể hoặc xử lý ở tầng ứng dụng.

### Chi phí cập nhật

PostgreSQL dùng MVCC: `UPDATE` tạo phiên bản tuple mới. Cập nhật một key trong JSONB không có nghĩa chỉ ghi vài byte của key đó vào vị trí cũ. Giá trị JSONB có thể phải được tạo lại; nếu JSONB được index GIN hoặc expression index, index liên quan cũng cần cập nhật. Với tài liệu lớn và cập nhật thường xuyên, chi phí WAL, bloat và index maintenance cần được đo.

Trong mô hình quan hệ, cập nhật một cột có thể tận dụng HOT update khi các điều kiện của PostgreSQL được đáp ứng, chẳng hạn không thay đổi cột được index và còn chỗ trên page. HOT không phải lúc nào cũng xảy ra; nó phụ thuộc bố trí dữ liệu, index và fillfactor. JSONB cũng có thể tham gia HOT nếu các cột được index không thay đổi và điều kiện khác thỏa mãn, nhưng cập nhật một key nằm trong GIN/expression index thường làm phát sinh cập nhật index.

## 9. Constraint và tính toàn vẹn dữ liệu

### Mô hình quan hệ

Mô hình quan hệ có các cơ chế rõ ràng:

- `NOT NULL` cho trường bắt buộc.
- `CHECK` cho miền giá trị.
- `UNIQUE` cho SKU hoặc khóa nghiệp vụ.
- `PRIMARY KEY` cho định danh.
- `FOREIGN KEY` cho quan hệ giữa các bảng.
- Kiểu dữ liệu như `integer`, `numeric`, `date`, `timestamptz` để từ chối dữ liệu sai kiểu.

Các ràng buộc được database áp dụng cho mọi client. Với dữ liệu quan hệ hóa thành nhiều bảng, foreign key giúp ngăn bản ghi mồ côi và có thể hỗ trợ hành động `ON DELETE`/`ON UPDATE` phù hợp.

### Mô hình JSONB

Các trường chung như `id`, `sku`, `category` vẫn có thể dùng kiểu quan hệ và constraint. Với key bên trong JSONB, cần xác định:

- Key có bắt buộc hay không.
- Kiểu JSON được chấp nhận là number, string, boolean, array, object hay null.
- Giá trị có giới hạn nào.
- Có được phép xuất hiện key không biết trước hay không.
- Key có phải duy nhất hoặc tham chiếu đến bảng khác không.
- Khi key đổi tên, dữ liệu cũ được migrate như thế nào.

`CHECK` có thể bảo vệ các quy tắc này, nhưng constraint phức tạp hơn và có thể phải lặp lại logic cast. JSONB không cung cấp foreign key trực tiếp từ một phần tử trong object tới một bảng khác. Nếu thuộc tính cần quan hệ tham chiếu, thường nên đưa nó thành cột hoặc bảng quan hệ riêng.

### Kiểm tra key bị thiếu, JSON null và SQL NULL

JSONB phân biệt object không có key với object có key mang giá trị JSON `null`. Có thể dùng:

```sql
SELECT
    attributes ? 'ram_gb' AS key_exists,
    jsonb_typeof(attributes -> 'ram_gb') AS json_value_type,
    attributes ->> 'ram_gb' AS text_value
FROM catalog_doc.product
WHERE category = 'laptop';
```

`?` kiểm tra key tồn tại ở top-level. Nếu key thiếu, toán tử trích xuất thường trả SQL `NULL`; nếu key có JSON `null`, `jsonb_typeof` trả chuỗi `'null'`. Hãy xác định rõ semantics trong API và ETL: thiếu key có nghĩa “chưa biết”, “không áp dụng” hay “mặc định”; JSON null có ý nghĩa gì; và SQL NULL ở toàn bộ cột `attributes` có được phép hay không.

## 10. Báo cáo và tổng hợp

Yêu cầu: đếm số sản phẩm và tính giá trung bình theo nhóm.

### Quan hệ

```sql
SELECT
    category,
    count(*) AS product_count,
    avg(price) AS average_price
FROM catalog_rel.product
GROUP BY category
ORDER BY category;
```

### JSONB

```sql
SELECT
    category,
    count(*) AS product_count,
    avg(price) AS average_price
FROM catalog_doc.product
GROUP BY category
ORDER BY category;
```

Vì trường chung được giữ ở cột quan hệ trong cả hai phương án, truy vấn tổng hợp này gần như giống nhau. Đây là một lý do thực tế để không đưa mọi thứ vào JSONB: các thuộc tính ổn định và thường dùng cho join, filter, group, sort vẫn có thể là cột bình thường.

Nếu cần tính RAM trung bình của laptop, truy vấn quan hệ dùng `avg(ram_gb)`, còn JSONB cần trích xuất và cast:

```sql
-- Quan hệ
SELECT avg(ram_gb)
FROM catalog_rel.product
WHERE category = 'laptop';

-- JSONB
SELECT avg((attributes ->> 'ram_gb')::numeric)
FROM catalog_doc.product
WHERE category = 'laptop';
```

Nếu các báo cáo này chạy thường xuyên, có thể tạo view/materialized view hoặc generated column/index phù hợp. Đừng lặp lại các biểu thức JSONB phức tạp ở hàng chục dashboard mà không có một lớp dữ liệu dùng chung.

## 11. Thay đổi schema khi có thông số mới

Giả sử laptop cần thêm thuộc tính `weight_kg`.

### Quan hệ

Có thể thêm cột:

```sql
ALTER TABLE catalog_rel.product
ADD COLUMN weight_kg numeric(5, 2);
```

Sau đó cập nhật ứng dụng, backfill dữ liệu cũ và thêm constraint phù hợp khi đã xử lý xong dữ liệu lịch sử. Với bảng lớn, cần lập kế hoạch lock, default và validation theo phiên bản PostgreSQL. Một cột mới có thể tác động đến mọi consumer đọc `SELECT *` hoặc mapping theo vị trí.

### JSONB

Có thể thêm key vào tài liệu mới mà không cần thêm cột:

```sql
UPDATE catalog_doc.product
SET attributes = jsonb_set(
    attributes,
    '{weight_kg}',
    to_jsonb(1.45),
    true
)
WHERE category = 'laptop'
  AND sku = 'LAP-001';
```

Không cần DDL chỉ để lưu key mới, nhưng ứng dụng vẫn phải thống nhất tên, kiểu, đơn vị và semantics. Nếu truy vấn cần lọc/sắp xếp theo `weight_kg`, cần xem xét expression index hoặc generated column. Nếu key bắt buộc, cần cập nhật constraint và backfill các tài liệu cũ.

### Versioning hợp đồng JSON

Với tài liệu có cấu trúc thay đổi theo thời gian, có thể lưu `schema_version` trong document hoặc ở cột riêng. Khi đọc, ứng dụng biết phiên bản nào cần chuyển đổi. Không nên thay đổi ý nghĩa key mà giữ nguyên tên nếu consumer cũ vẫn đang đọc.

## 12. Tách bảng subtype thay cho cột thưa

Nếu số nhóm sản phẩm tăng và mỗi nhóm có nhiều trường ổn định, có thể tách bảng subtype:

```sql
CREATE TABLE catalog_rel.product_base (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category text NOT NULL CHECK (category IN ('laptop', 'phone')),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,
    UNIQUE (id, category)
);

CREATE TABLE catalog_rel.laptop_spec (
    product_id bigint PRIMARY KEY,
    category text NOT NULL DEFAULT 'laptop' CHECK (category = 'laptop'),
    ram_gb integer NOT NULL CHECK (ram_gb BETWEEN 1 AND 512),
    storage_gb integer NOT NULL CHECK (storage_gb BETWEEN 32 AND 32768),
    screen_inches numeric(5, 2) NOT NULL CHECK (screen_inches BETWEEN 8 AND 30),
    FOREIGN KEY (product_id, category)
        REFERENCES catalog_rel.product_base (id, category)
        ON DELETE CASCADE
);
```

Composite foreign key bảo đảm một hàng `laptop_spec` chỉ tham chiếu sản phẩm có category `laptop`. Nó chưa tự bảo đảm mọi sản phẩm laptop đều có một hàng `laptop_spec`; nếu tính bắt buộc này cần được bảo vệ ở database, có thể dùng constraint trigger phù hợp hoặc quy trình ghi trong transaction có kiểm soát. Một bảng subtype giúp mỗi nhóm có schema rõ, nhưng truy vấn chung cần join các bảng subtype hoặc tạo view hợp nhất.

## 13. Đưa dữ liệu quan hệ sang JSONB và ngược lại

### Tạo JSON từ cột quan hệ

PostgreSQL có thể tạo JSONB từ dữ liệu cột:

```sql
SELECT jsonb_build_object(
    'sku', sku,
    'name', name,
    'ram_gb', ram_gb,
    'storage_gb', storage_gb,
    'screen_inches', screen_inches
) AS product_document
FROM catalog_rel.product
WHERE category = 'laptop';
```

Đây là cách tạo payload cho API hoặc export. Không nhất thiết phải lưu lại payload nếu nó có thể được tạo từ dữ liệu quan hệ khi cần.

### Trích xuất JSONB thành cột

```sql
SELECT
    sku,
    attributes ->> 'ram_gb' AS ram_gb_text,
    (attributes ->> 'ram_gb')::integer AS ram_gb,
    (attributes ->> 'screen_inches')::numeric AS screen_inches
FROM catalog_doc.product
WHERE category = 'laptop';
```

Khi chuyển dữ liệu, cần xác định cách xử lý key thiếu, JSON null, kiểu sai, giá trị ngoài miền và tài liệu có schema version cũ. Không ép kiểu hàng loạt trước khi thống kê số lượng dữ liệu lỗi.

## 14. So sánh hiệu năng một cách công bằng

Không thể kết luận quan hệ nhanh hơn hay JSONB nhanh hơn chỉ từ số lượng dòng SQL hoặc một truy vấn mẫu. Cần dùng cùng dữ liệu và cùng điều kiện chạy.

### Chuẩn bị dataset giống nhau

Tạo một nguồn dữ liệu chuẩn, sau đó nạp cùng các bản ghi vào `catalog_rel.product` và `catalog_doc.product`. Kiểm tra:

- Cùng số lượng sản phẩm.
- Cùng tập SKU và khóa định danh nghiệp vụ.
- Cùng category, giá, currency và available.
- Cùng giá trị thông số và cùng đơn vị đo.
- Cùng tỷ lệ sản phẩm thiếu hoặc không áp dụng thông số.
- Cùng phân bố hot/cold, nếu có tenant hoặc nhóm dữ liệu lệch.

Nếu dữ liệu được sinh ngẫu nhiên riêng cho hai bảng, chúng có thể khác phân bố và khiến kết quả benchmark không còn công bằng.

### Cập nhật thống kê

Sau khi nạp dữ liệu và tạo index:

```sql
ANALYZE catalog_rel.product;
ANALYZE catalog_doc.product;
```

Nếu dataset lớn và vừa có nhiều update/delete, có thể cần vacuum phù hợp trước khi đo. Không thay đổi `work_mem`, `shared_buffers`, cache state hoặc concurrency giữa hai lần benchmark.

### Đo kế hoạch và buffer

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, sku, price
FROM catalog_rel.product
WHERE category = 'laptop'
  AND available
  AND price <= 1500
  AND ram_gb >= 16
ORDER BY price, id
LIMIT 50;
```

Chạy truy vấn tương đương trên JSONB:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, sku, price
FROM catalog_doc.product
WHERE category = 'laptop'
  AND available
  AND price <= 1500
  AND (attributes ->> 'ram_gb')::integer >= 16
ORDER BY price, id
LIMIT 50;
```

So sánh:

- Estimated rows với actual rows.
- Loại scan và index được sử dụng.
- Có sort hay không và sort có spill ra đĩa không.
- Shared buffer hit/read và temp blocks.
- Planning time và execution time.
- Kích thước heap/index và chi phí cập nhật.

`EXPLAIN ANALYZE` thực thi truy vấn thật. Dùng trên môi trường benchmark và không chạy DML nguy hiểm trên production chỉ để lấy plan.

### Đo nhiều loại workload

| Workload | Điều cần so sánh |
|---|---|
| Insert hàng mới | Throughput, WAL, constraint cost, index maintenance |
| Update trường chung | HOT update, index và lock |
| Update một thông số | Cột riêng so với thay đổi JSONB và index liên quan |
| Filter bằng equality | B-tree, GIN containment và selectivity |
| Filter bằng range | B-tree cột so với expression index |
| Join với category/brand | Khả năng join bằng khóa và cardinality |
| Aggregate | CPU, cast, scan, memory và thời gian |
| Truy vấn document đầy đủ | Kích thước payload, TOAST và bytes truyền |
| Concurrent workload | p95/p99, throughput, connection và I/O |

Nên chạy nhiều vòng có warm-up, lấy percentile và lưu cấu hình server. Một lần chạy nhanh nhất không phải kết quả đủ tin cậy.

## 15. Đánh giá dung lượng lưu trữ

JSONB không nhất thiết luôn nhỏ hơn hoặc lớn hơn mô hình quan hệ. Kích thước phụ thuộc số key, độ dài tên key, kiểu giá trị, TOAST, mức lặp lại, index và cách bố trí bảng. Mô hình quan hệ có thể tốn dung lượng cho cột thưa; JSONB có thể lặp tên key ở nhiều hàng và có thêm overhead cấu trúc.

Đo kích thước thực tế:

```sql
SELECT
    'relational' AS model,
    pg_size_pretty(pg_relation_size('catalog_rel.product')) AS heap,
    pg_size_pretty(pg_indexes_size('catalog_rel.product')) AS indexes,
    pg_size_pretty(pg_total_relation_size('catalog_rel.product')) AS total
UNION ALL
SELECT
    'jsonb' AS model,
    pg_size_pretty(pg_relation_size('catalog_doc.product')) AS heap,
    pg_size_pretty(pg_indexes_size('catalog_doc.product')) AS indexes,
    pg_size_pretty(pg_total_relation_size('catalog_doc.product')) AS total;
```

Đo sau khi dữ liệu và index đã được tạo đầy đủ, cùng trạng thái vacuum và cùng số hàng. Nếu bảng JSONB chứa object lớn, hãy xem thêm ảnh hưởng TOAST và kích thước WAL khi cập nhật một key.

## 16. Tính nhất quán và quan hệ giữa các thực thể

Mô hình quan hệ đặc biệt phù hợp khi sản phẩm tham chiếu đến category, brand, supplier, warehouse hoặc bảng giá. Foreign key có thể bảo đảm các tham chiếu hợp lệ và transaction có thể cập nhật nhiều bảng với tính nguyên tử.

JSONB phù hợp hơn cho một nhóm thuộc tính nằm cùng aggregate, được đọc và cập nhật cùng nhau, không cần foreign key độc lập cho từng key. Nếu nhúng ID category hoặc supplier vào JSONB, database không tự tạo foreign key cho giá trị đó. Có thể lưu thêm cột quan hệ làm nguồn chuẩn và chỉ lặp dữ liệu trong JSONB khi có lý do rõ ràng.

### Ví dụ quan hệ category

```sql
CREATE TABLE catalog_rel.category (
    category_code text PRIMARY KEY,
    category_name text NOT NULL UNIQUE
);

ALTER TABLE catalog_rel.product
ADD CONSTRAINT product_category_fk
FOREIGN KEY (category)
REFERENCES catalog_rel.category (category_code);
```

Nếu dùng JSONB cho attributes, vẫn có thể giữ category dưới dạng cột và tạo foreign key như trên. Điều này cho thấy hai cách lưu trữ có thể kết hợp; JSONB không yêu cầu toàn bộ bản ghi phải trở thành document.

## 17. Xử lý null, default và dữ liệu thiếu

Trong mô hình quan hệ, `NULL` có semantics SQL rõ ràng. Constraint `NOT NULL`, `DEFAULT`, `CHECK` và các phép so sánh ba giá trị quyết định cách xử lý. Cần phân biệt `NULL` nghĩa là chưa biết, không áp dụng hay chưa được nhập.

Trong JSONB có nhiều trạng thái:

- Cột `attributes` là SQL `NULL` (nếu cột cho phép).
- Object không có key `ram_gb`.
- Object có key `ram_gb` với JSON `null`.
- Object có key với giá trị đúng kiểu, ví dụ number `16`.
- Object có key với kiểu sai, ví dụ string `"16"`.

API cần quy định rõ semantics cho từng trạng thái. Đặc biệt, không dùng `COALESCE(attributes->>'x', '0')` nếu giá trị thiếu không thực sự có nghĩa là số 0. Default sai có thể làm báo cáo sai mà không phát sinh lỗi.

## 18. Bảo mật và kiểm soát dữ liệu

Không nên coi JSONB là nơi để lưu mọi dữ liệu tùy ý mà không kiểm soát. JSONB vẫn nằm trong database, chịu quyền truy cập bảng, backup, replication và log như các cột khác. Nếu payload có thông tin nhạy cảm, cần phân loại và giới hạn quyền đọc.

Một số nguyên tắc:

- Không lưu secret, password hoặc token truy cập trong attributes sản phẩm.
- Dùng role tối thiểu và view để giới hạn trường được đọc.
- Kiểm tra key và kiểu dữ liệu ở database hoặc application boundary.
- Tránh log toàn bộ JSONB nếu có dữ liệu cá nhân hoặc thông tin nội bộ.
- Kiểm soát kích thước document để tránh payload bất thường.
- Dùng migration và quy trình versioning cho hợp đồng JSON.

## 19. Khi nào chọn mô hình quan hệ?

Mô hình quan hệ thường phù hợp khi:

- Các thuộc tính có cấu trúc ổn định và được truy vấn thường xuyên.
- Cần lọc, sắp xếp, join và aggregate theo nhiều thuộc tính.
- Cần kiểu dữ liệu chặt và constraint ở database.
- Các thuộc tính tham gia khóa, foreign key hoặc uniqueness.
- Dữ liệu được nhiều ứng dụng sử dụng như một hợp đồng chung.
- Báo cáo cần thống kê chính xác theo cột.
- Cần kiểm soát thay đổi schema bằng migration rõ ràng.

Các bảng quan hệ giúp planner thu thập thống kê theo cột và hỗ trợ các kiểu index quen thuộc. Đổi lại, thay đổi cấu trúc thường cần migration và phối hợp consumer.

## 20. Khi nào chọn JSONB?

JSONB thường phù hợp khi:

- Thuộc tính thay đổi thường xuyên giữa các loại đối tượng.
- Phần lớn payload được đọc/ghi cùng nhau như một document.
- Nhiều key ít được truy vấn riêng lẻ.
- Ứng dụng cần lưu cấu trúc lồng nhau hoặc mảng có tính chất tài liệu.
- Schema được quản lý như một hợp đồng ứng dụng và có versioning rõ.
- Có thể chấp nhận việc tự xây constraint/index cho các key quan trọng.

JSONB giúp thêm key mới mà không phải thêm cột cho mỗi thay đổi. Nhưng nếu key đó trở thành điều kiện lọc chính, join key hoặc chỉ số báo cáo quan trọng, nó có thể cần expression index, generated column hoặc tách thành cột quan hệ.

## 21. Mô hình kết hợp quan hệ và JSONB

Trong nhiều hệ thống, cách thực tế là giữ các trường ổn định ở dạng cột và chỉ dùng JSONB cho phần mở rộng.

Ví dụ:

```sql
CREATE TABLE catalog.product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category_id bigint NOT NULL REFERENCES catalog.category(id),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Các cột chung có constraint, foreign key và index thông thường. `attributes` chứa các thông số mở rộng ít ổn định. Với key được truy vấn nhiều, có thể tạo expression index hoặc chuyển key thành generated column/cột vật lý.

Quyết định đưa một key từ JSONB thành cột nên dựa trên tần suất truy vấn, nhu cầu constraint, join, báo cáo, độ ổn định của hợp đồng và chi phí migration. Không cần chuyển mọi key chỉ vì một dashboard truy vấn nó một lần; cũng không nên để key quan trọng nằm trong document mãi nếu nó đã trở thành phần cốt lõi của mô hình nghiệp vụ.

## 22. Lộ trình chuyển đổi giữa hai mô hình

Khi cần chuyển từ JSONB sang cột quan hệ, hoặc ngược lại, nên dùng quy trình nhiều bước để giảm rủi ro.

### Từ JSONB sang cột

1. Xác định key cần chuẩn hóa, kiểu dữ liệu và quy tắc null/default.
2. Thêm cột mới ở dạng nullable hoặc với default phù hợp.
3. Cập nhật ứng dụng để ghi đồng thời hoặc ưu tiên cột mới theo giai đoạn.
4. Backfill dữ liệu JSONB cũ theo batch, có kiểm soát lỗi cast.
5. Đối chiếu giá trị cột và JSONB theo khóa sản phẩm.
6. Tạo index và constraint sau khi dữ liệu đã phù hợp.
7. Chuyển truy vấn đọc sang cột mới.
8. Ngừng ghi key cũ, sau đó mới xóa key hoặc ngừng sử dụng cột JSONB.

### Từ cột sang JSONB

1. Xác định document contract và version.
2. Thêm key JSONB được sinh từ cột hiện tại.
3. Chạy dual-read/dual-write có thời hạn nếu cần rolling deployment.
4. Đối chiếu dữ liệu và kiểm tra consumer.
5. Chuyển truy vấn sang JSONB, tạo index cần thiết.
6. Loại bỏ cột cũ chỉ sau khi không còn consumer phụ thuộc.

Trong cả hai hướng, cần xác định nguồn dữ liệu chuẩn trong giai đoạn dual-write để tránh hai bản sao lệch nhau. Nên có metric đếm số hàng thiếu key, cast lỗi hoặc giá trị không khớp.

## 23. Bảng so sánh theo cùng yêu cầu

| Tiêu chí | Mô hình quan hệ | Mô hình JSONB |
|---|---|---|
| Trường chung | Cột có kiểu dữ liệu | Có thể giữ nguyên cột |
| Thuộc tính theo nhóm | Cột/subtype table/bảng thuộc tính | Key trong object JSONB |
| Kiểu dữ liệu | Được khai báo trực tiếp | Kiểu JSON cần được kiểm tra/cast |
| Required/range | `NOT NULL`, `CHECK` | `CHECK` trên `jsonb_typeof` và giá trị trích xuất |
| Uniqueness | `UNIQUE`/index | Thường cần expression index hoặc cột riêng |
| Foreign key | Hỗ trợ trực tiếp | Không có FK trực tiếp cho key bên trong document |
| Equality search | B-tree, partial index | GIN containment hoặc expression index |
| Numeric range | B-tree trên cột | B-tree expression/generated column thường phù hợp |
| Join | Cột khóa có kiểu rõ | Thường cần trích xuất/cast; nên đưa khóa join ra cột |
| Thêm thuộc tính | Migration schema | Thêm key, nhưng cần version/validation |
| Cập nhật một trường | Update cột | `jsonb_set`, vẫn tạo tuple mới theo MVCC |
| Thống kê planner | Thống kê từng cột | Thống kê JSONB và expression/index phụ thuộc truy vấn |
| Đọc toàn bộ payload | Có thể cần join nhiều bảng | Có thể đọc một document |
| Báo cáo đa chiều | Thuận tiện với cột quan hệ | Cần trích xuất key hoặc tạo lớp mô hình |
| Hợp đồng dữ liệu | Schema database rõ ràng | Cần quy ước và validation rõ ràng |

## 24. Quy trình thực hành so sánh end-to-end

Để kết luận cho hệ thống cụ thể, hãy thực hiện một bài đo có thể tái lập:

1. **Chốt use case:** danh sách truy vấn đọc, thao tác ghi, báo cáo và yêu cầu consistency.
2. **Tạo hai schema:** `catalog_rel` và `catalog_doc` với cùng trường chung và cùng thông số.
3. **Sinh một nguồn fixture chuẩn:** cùng SKU, giá, category, attributes, tỷ lệ null và phân bố giá trị.
4. **Nạp cả hai mô hình:** ghi lại số hàng và xác nhận các kết quả nghiệp vụ tương đương.
5. **Tạo index tương ứng:** unique SKU, partial B-tree và GIN/expression index cần thiết.
6. **Chạy `ANALYZE`:** cập nhật thống kê cho cả hai bảng.
7. **Đo truy vấn equality và range:** tham số phổ biến, hiếm, kết hợp nhiều điều kiện.
8. **Đo update và insert:** cùng số hàng, cùng transaction size và cùng concurrency.
9. **Đo báo cáo:** group by, aggregate, join và truy vấn theo thuộc tính riêng.
10. **Đo dung lượng:** heap, index, TOAST và WAL phát sinh.
11. **Đánh giá vận hành:** migration, validation, backup/restore, schema evolution và quyền.
12. **Ghi quyết định:** nêu workload nào ưu tiên, trade-off nào chấp nhận và vì sao.

Không chỉ chọn phương án có execution time thấp nhất trong một truy vấn. Hãy cân nhắc tổng chi phí: ghi dữ liệu, bảo trì index, dung lượng, độ phức tạp constraint, phát triển ứng dụng và số consumer cần phối hợp.

## 25. Bài tập thực hành

### Bài 1: Xây dựng hai mô hình

Tạo hai bảng theo các ví dụ trong bài. Nạp ít nhất 100.000 sản phẩm vào mỗi mô hình từ cùng một fixture. Đối chiếu số hàng, SKU và giá trị thông số.

### Bài 2: Thử dữ liệu sai

Thử insert laptop thiếu RAM, phone có `ram_gb`, JSONB dùng string thay vì number và giá âm. Ghi nhận constraint nào từ chối từng trường hợp.

### Bài 3: So sánh truy vấn range

Chạy truy vấn laptop có RAM từ 16 GB và giá dưới 1.500 USD trên cả hai mô hình. Dùng `EXPLAIN (ANALYZE, BUFFERS)` và so sánh plan trước/sau index.

### Bài 4: So sánh GIN với expression B-tree

Tạo GIN `jsonb_path_ops`, sau đó tạo expression B-tree trên RAM. So sánh containment equality với điều kiện `ram_gb >= 16`. Giải thích vì sao hai loại index phục vụ các dạng truy vấn khác nhau.

### Bài 5: Đo cập nhật một thuộc tính

Chạy 10.000 cập nhật RAM ở mô hình quan hệ và JSONB. Đo thời gian, WAL, index size và bloat sau workload. Lặp lại khi JSONB có GIN index.

### Bài 6: Thêm thuộc tính mới

Thêm `weight_kg` cho laptop. Triển khai bằng cột quan hệ và bằng key JSONB. Mô tả migration, backfill, validation và cách consumer cũ tiếp tục hoạt động.

### Bài 7: Phân biệt key thiếu và JSON null

Tạo ba document: thiếu `ram_gb`, `ram_gb: null`, `ram_gb: 16`. Dùng `?`, `->` và `jsonb_typeof` để phân biệt kết quả.

### Bài 8: Xây mô hình kết hợp

Giữ SKU, category, price, currency và available ở cột; chuyển một số thông số hiếm dùng sang JSONB. Tạo expression index cho một key thường lọc. Đánh giá sự cân bằng giữa tính linh hoạt và truy vấn.

## 26. Câu hỏi ôn tập

**1. Vì sao phải so sánh hai mô hình trên cùng một fixture?**

Để loại bỏ sai lệch do số lượng, phân bố và giá trị dữ liệu khác nhau. Chỉ khi dữ liệu và workload tương đương mới có thể so sánh chi phí truy vấn và lưu trữ.

**2. JSONB có tự kiểm tra kiểu dữ liệu của key không?**

Không theo hợp đồng ứng dụng mong muốn. JSONB có kiểu JSON cơ bản, nhưng muốn RAM là số nguyên trong một miền cụ thể thì cần constraint hoặc validation ở ứng dụng/database.

**3. Khi nào GIN phù hợp với JSONB?**

Khi truy vấn dùng containment hoặc các toán tử JSONB được operator class hỗ trợ. Numeric range thường cần expression B-tree hoặc generated column để lập chỉ mục phù hợp.

**4. Vì sao expression index cần biểu thức khớp truy vấn?**

Planner cần nhận diện biểu thức truy vấn tương ứng với biểu thức đã index. Cast, hàm và cách viết khác nhau có thể khiến index không được dùng như dự kiến.

**5. Cập nhật một key JSONB có phải ghi lại duy nhất key đó không?**

Không. PostgreSQL dùng MVCC và cập nhật giá trị JSONB có thể tạo tuple mới, phát sinh WAL và cập nhật index liên quan.

**6. JSONB có hỗ trợ foreign key cho một key bên trong object không?**

Không trực tiếp. Nếu key cần tham chiếu và đảm bảo toàn vẹn, nên đưa nó thành cột hoặc bảng quan hệ.

**7. Khi nào nên chuyển một key JSONB thành cột?**

Khi key ổn định, thường xuyên được filter/join/group/sort, cần constraint mạnh hoặc là một phần quan trọng của hợp đồng dữ liệu.

**8. Có thể dùng quan hệ và JSONB trong cùng một bảng không?**

Có. Giữ trường ổn định ở cột quan hệ và dùng JSONB cho phần mở rộng là mô hình kết hợp phổ biến.

**9. Vì sao cần phân biệt key thiếu với JSON null?**

Hai trạng thái có thể mang ý nghĩa nghiệp vụ khác nhau. Nếu không định nghĩa rõ, default hoặc báo cáo có thể diễn giải sai dữ liệu.

**10. Chỉ số nào cần so sánh ngoài execution time?**

Throughput, p95/p99, buffer, I/O, WAL, index/heap size, chi phí update/insert, lock, thời gian migration và độ phức tạp vận hành.

## 27. Tài liệu tham khảo PostgreSQL

- PostgreSQL Documentation — JSON Types: https://www.postgresql.org/docs/current/datatype-json.html
- PostgreSQL Documentation — JSON Functions and Operators: https://www.postgresql.org/docs/current/functions-json.html
- PostgreSQL Documentation — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- PostgreSQL Documentation — Index Types: https://www.postgresql.org/docs/current/indexes-types.html
- PostgreSQL Documentation — GIN Indexes: https://www.postgresql.org/docs/current/gin.html
- PostgreSQL Documentation — Indexes on Expressions: https://www.postgresql.org/docs/current/indexes-expressional.html
- PostgreSQL Documentation — Generated Columns: https://www.postgresql.org/docs/current/ddl-generated-columns.html
- PostgreSQL Documentation — `EXPLAIN`: https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL Documentation — Routine Vacuuming: https://www.postgresql.org/docs/current/routine-vacuuming.html
- PostgreSQL Documentation — `INSERT ... ON CONFLICT`: https://www.postgresql.org/docs/current/sql-insert.html

So sánh quan hệ với JSONB cần dựa trên chính yêu cầu truy vấn, cập nhật và toàn vẹn dữ liệu. Cột quan hệ cung cấp kiểu dữ liệu, constraint, foreign key và thống kê trực tiếp; JSONB phù hợp với phần thuộc tính linh hoạt nhưng cần validation, cast và index được thiết kế theo từng kiểu truy vấn. Với nhiều hệ thống, mô hình kết hợp giữ dữ liệu cốt lõi ở cột quan hệ và dùng JSONB cho phần mở rộng là lựa chọn cân bằng, miễn là hợp đồng dữ liệu và quy trình chuyển đổi được quản lý rõ ràng.
