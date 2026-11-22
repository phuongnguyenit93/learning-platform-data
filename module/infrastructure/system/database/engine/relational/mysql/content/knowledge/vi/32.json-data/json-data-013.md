# Chọn mô hình quan hệ, tài liệu hoặc kết hợp theo nhu cầu truy vấn

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Khi lưu dữ liệu có cấu trúc linh hoạt, câu hỏi quan trọng không chỉ là dùng cột JSON hay thêm bảng mới. Cần chọn mô hình sao cho dữ liệu dễ bảo đảm đúng, truy vấn thường gặp có thể dùng index, cập nhật không tạo ra bất nhất và hệ thống vẫn tiến hóa được khi yêu cầu thay đổi.

MySQL hỗ trợ cả mô hình quan hệ và kiểu dữ liệu JSON. Mô hình quan hệ biểu diễn thực thể, quan hệ và ràng buộc bằng bảng, khóa và foreign key. Mô hình tài liệu lưu một aggregate có cấu trúc lồng nhau trong một JSON document. Mô hình kết hợp giữ dữ liệu cốt lõi, quan hệ và thuộc tính cần truy vấn thường xuyên trong các cột quan hệ, đồng thời dùng JSON cho phần thuộc tính linh hoạt hoặc snapshot có ranh giới rõ.

Không có một mô hình tốt nhất cho mọi hệ thống. Hãy bắt đầu từ cách ứng dụng đọc, lọc, join, cập nhật và bảo đảm tính nhất quán. Sau đó chọn nơi lưu dữ liệu, thiết kế index, kiểm tra execution plan và đo trên dữ liệu đại diện.

## 1. Ba cách tổ chức dữ liệu

### 1.1. Mô hình quan hệ

Mô hình quan hệ tách dữ liệu thành các bảng có cấu trúc xác định. Mỗi loại thực thể có khóa chính; quan hệ giữa các thực thể được biểu diễn bằng khóa ngoại hoặc khóa tham chiếu do ứng dụng quản lý.

Ví dụ hệ thống bán hàng:

~~~text
customers
  customer_id PK
  name
  email

orders
  order_id PK
  customer_id FK -> customers.customer_id
  created_at
  status

order_items
  order_item_id PK
  order_id FK -> orders.order_id
  product_id FK -> products.product_id
  quantity
  unit_price

products
  product_id PK
  sku
  name
  price
~~~

Mô hình này phù hợp khi các thực thể có ý nghĩa độc lập, được nhiều luồng nghiệp vụ tham chiếu, cần unique constraint, foreign key, join, aggregate và cập nhật từng phần.

### 1.2. Mô hình tài liệu

Mô hình tài liệu lưu một đối tượng nghiệp vụ cùng các thuộc tính lồng nhau trong một JSON document. Ví dụ một cấu hình giao diện có thể chứa theme, danh sách widget, vị trí và tùy chọn riêng cho từng widget.

~~~json
{
  "theme": "dark",
  "layout": {
    "columns": 2,
    "density": "compact"
  },
  "widgets": [
    {
      "kind": "sales-chart",
      "position": 1,
      "options": {
        "period": "month",
        "showLegend": true
      }
    },
    {
      "kind": "alerts",
      "position": 2,
      "options": {
        "severity": ["high", "critical"]
      }
    }
  ]
}
~~~

Nếu ứng dụng thường tải và lưu toàn bộ cấu hình như một đơn vị, cấu trúc lồng nhau phản ánh tốt ranh giới aggregate. Các widget không nhất thiết cần được join với nhiều thực thể khác.

### 1.3. Mô hình kết hợp

Mô hình kết hợp dùng cột quan hệ cho dữ liệu ổn định và cần ràng buộc; dùng JSON cho phần linh hoạt, ít tham gia join hoặc chỉ được đọc cùng thực thể sở hữu nó.

Ví dụ bảng products:

~~~sql
CREATE TABLE products (
    product_id BIGINT NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    category_id BIGINT NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku),
    KEY ix_products_category (category_id)
) ENGINE = InnoDB;
~~~

Các cột sku, name, price và category_id có kiểu, index và ràng buộc rõ ràng. attributes chứa các thuộc tính thay đổi theo loại sản phẩm, chẳng hạn kích thước màn hình, chất liệu, dung lượng hoặc thông số kỹ thuật.

Mô hình kết hợp thường phù hợp khi phần lõi của domain có cấu trúc ổn định nhưng một số thuộc tính mở rộng thay đổi theo nhóm sản phẩm hoặc theo phiên bản.

## 2. Chọn mô hình từ workload

Trước khi tạo bảng, hãy viết ra các thao tác ứng dụng thực sự cần:

- Đọc một thực thể theo ID hay tải cả aggregate?
- Lọc theo thuộc tính nào?
- Có cần join thuộc tính đó với bảng khác không?
- Có cần unique constraint hoặc foreign key không?
- Có cần group, sort, range scan hoặc báo cáo trên thuộc tính không?
- Một thay đổi cập nhật một giá trị hay nhiều thực thể liên quan?
- Dữ liệu có cần được chia sẻ và cập nhật độc lập bởi nhiều luồng nghiệp vụ không?

### 2.1. Khi mô hình quan hệ phù hợp

Ưu tiên cột quan hệ và bảng riêng khi:

- Thuộc tính có ý nghĩa nghiệp vụ ổn định và xuất hiện trong nhiều truy vấn.
- Cần lọc, join, group, sort hoặc range scan thường xuyên.
- Giá trị phải có kiểu dữ liệu, NOT NULL, UNIQUE, CHECK hoặc foreign key.
- Nhiều thực thể tham chiếu cùng một giá trị, ví dụ customer, product, category hoặc account.
- Một tập con của dữ liệu cần được cập nhật độc lập và có transaction riêng.
- Cần kiểm soát dữ liệu trùng hoặc bảo đảm toàn vẹn ở cấp database.

Ví dụ email khách hàng cần duy nhất và được dùng để đăng nhập. Đặt email trong cột VARCHAR có unique index rõ ràng hơn việc tìm và kiểm tra một đường dẫn JSON ở mỗi thao tác.

### 2.2. Khi mô hình tài liệu phù hợp

Ưu tiên JSON document khi:

- Dữ liệu thường được đọc hoặc ghi như một aggregate.
- Thuộc tính lồng nhau có cấu trúc thay đổi theo loại đối tượng.
- Phần lớn thuộc tính chỉ được đọc cùng đối tượng cha.
- Không cần join từng phần tử lồng nhau với bảng khác.
- Không cần foreign key hoặc unique constraint độc lập trên từng phần tử JSON.
- Ứng dụng có thể xác thực cấu trúc document trước khi ghi.

Ví dụ một cấu hình cá nhân có các tùy chọn riêng của từng người dùng. Nếu ứng dụng luôn đọc cả cấu hình, một document có thể đơn giản hơn nhiều bảng con.

### 2.3. Khi mô hình kết hợp phù hợp

Chọn kết hợp khi:

- Một số thuộc tính ổn định và cần index, ràng buộc hoặc join.
- Phần mở rộng có cấu trúc khác nhau giữa các loại đối tượng.
- JSON được truy cập chủ yếu cùng hàng sở hữu nó.
- Chỉ một số đường dẫn JSON cần lọc; có thể tạo generated column hoặc functional index cho các đường dẫn đó.
- Cần lưu snapshot hoặc metadata gắn với một thực thể quan hệ.

Ví dụ đơn hàng có customer_id, status, created_at và total_amount ở cột quan hệ; địa chỉ giao hàng đã chốt tại thời điểm đặt hàng có thể lưu thành JSON snapshot. Địa chỉ snapshot không nhất thiết phải join với địa chỉ hiện tại của khách hàng.

## 3. Ma trận quyết định

| Tiêu chí | Quan hệ | JSON document | Kết hợp |
|---|---|---|---|
| Cấu trúc | Ổn định, khai báo rõ | Linh hoạt, lồng nhau | Lõi ổn định, phần mở rộng linh hoạt |
| Join | Mạnh, trực tiếp | Khó hơn, thường cần trích xuất | Dùng cột quan hệ cho join chính |
| Foreign key | Có | Không áp dụng trực tiếp cho đường dẫn JSON | Có cho phần quan hệ |
| Unique constraint | Trực tiếp | Cần trích xuất hoặc kiểm tra riêng | Trực tiếp cho lõi, bổ sung index cho JSON scalar |
| Aggregate và báo cáo | Thuận lợi | Cần JSON_TABLE hoặc biểu thức JSON | Thuận lợi cho chỉ tiêu chính |
| Thay đổi schema | Migration rõ ràng | Dễ thêm thuộc tính, khó kiểm soát biến thể | Thêm thuộc tính linh hoạt, giữ lõi ổn định |
| Cập nhật độc lập | Theo hàng hoặc bảng | Thường cập nhật document | Theo thực thể và phần mở rộng |
| Phù hợp | Nghiệp vụ có quan hệ dày | Aggregate được đọc/ghi cùng nhau | Domain hỗn hợp |

Đây là hướng dẫn để đặt câu hỏi, không phải bảng xếp hạng hiệu năng. Một mô hình quan hệ được index sai vẫn có thể chậm; một document lớn phải cập nhật thường xuyên cũng có thể gây chi phí đáng kể.

## 4. Thiết kế lõi quan hệ trước

Hãy nhận diện các khái niệm có vòng đời và quy tắc riêng trước khi quyết định đưa dữ liệu vào JSON.

Ví dụ:

- Customer có định danh, email và trạng thái riêng.
- Product có SKU, giá và category riêng.
- Order có trạng thái, thời gian tạo và customer sở hữu.
- Order item có số lượng, giá tại thời điểm mua và quan hệ với order.

Đây là các thực thể quan hệ. Nếu nhúng toàn bộ chúng vào JSON của một order, sẽ khó bảo đảm customer tồn tại, SKU duy nhất, thống kê theo product và cập nhật product độc lập.

### 4.1. Một schema quan hệ cơ bản

~~~sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE products (
    product_id BIGINT NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT NOT NULL AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_date (customer_id, created_at),
    KEY ix_orders_status_date (status, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT NOT NULL AUTO_INCREMENT,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY ix_order_items_order (order_id),
    KEY ix_order_items_product (product_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT chk_order_items_quantity
        CHECK (quantity > 0)
) ENGINE = InnoDB;
~~~

Giá trị unit_price trong order_items là giá đã chốt cho đơn hàng. Nó không nhất thiết luôn bằng giá hiện tại trong products. Đây là ví dụ về snapshot nghiệp vụ có chủ đích: vẫn lưu thành cột quan hệ vì cần kiểu số, aggregate và truy vấn thường xuyên.

### 4.2. Không biến JSON thành nơi chứa mọi thứ

Nếu mọi thuộc tính đều nằm trong một cột JSON, ứng dụng phải tự chịu trách nhiệm nhiều việc mà database vốn hỗ trợ tốt:

- Xác thực kiểu và sự hiện diện của từng thuộc tính.
- Kiểm tra unique giữa các document.
- Bảo đảm quan hệ tham chiếu.
- Tạo index cho các đường dẫn cần truy vấn.
- Cập nhật đồng thời các thuộc tính của cùng document.
- Xử lý báo cáo và join qua nhiều document.

JSON không loại bỏ schema; nó chuyển một phần schema từ DDL database sang hợp đồng dữ liệu của ứng dụng hoặc cơ chế validation.

## 5. JSON trong MySQL là gì?

MySQL có kiểu dữ liệu JSON riêng. Khi ghi một giá trị vào cột JSON, MySQL kiểm tra cú pháp JSON và lưu ở dạng biểu diễn nội bộ đã được tối ưu để truy cập thành phần. Cột JSON không đơn giản là VARCHAR chứa chuỗi JSON nguyên bản.

Ví dụ:

~~~sql
CREATE TABLE user_preferences (
    user_id BIGINT NOT NULL,
    preferences JSON NOT NULL,
    PRIMARY KEY (user_id)
) ENGINE = InnoDB;
~~~

Có thể lưu object:

~~~sql
INSERT INTO user_preferences (user_id, preferences)
VALUES (
    1,
    JSON_OBJECT(
        'theme', 'dark',
        'language', 'vi',
        'notifications', JSON_OBJECT(
            'email', TRUE,
            'push', FALSE
        )
    )
);
~~~

MySQL kiểm tra dữ liệu là JSON hợp lệ. Tuy nhiên, việc JSON hợp lệ về cú pháp không đồng nghĩa document thỏa quy tắc nghiệp vụ. Ví dụ theme có thể nhận giá trị không được ứng dụng hỗ trợ nếu không có validation bổ sung.

### 5.1. Object, array và scalar

JSON hỗ trợ các loại giá trị:

- Object: tập cặp key/value.
- Array: danh sách có thứ tự.
- String: chuỗi Unicode.
- Number: số.
- Boolean: true hoặc false.
- Null: giá trị null của JSON.

Một cột JSON có thể chứa object, array hoặc scalar hợp lệ. Để thiết kế dữ liệu nghiệp vụ, nên quy định rõ root document là object hay array và cấu trúc con mong đợi.

### 5.2. JSON không giữ nguyên định dạng văn bản đầu vào

MySQL phân tích và lưu JSON theo biểu diễn nội bộ. Không dựa vào khoảng trắng, thứ tự key hoặc cách định dạng ban đầu để so sánh chuỗi JSON. Nếu cần chữ ký số trên payload gốc, cần lưu chuỗi gốc riêng hoặc canonicalize theo quy tắc ứng dụng trước khi ký.

### 5.3. SQL NULL khác JSON null

SQL NULL biểu thị không có giá trị SQL. JSON null là một giá trị bên trong document. Hai trường hợp cần được phân biệt khi lọc:

- Cột JSON là SQL NULL.
- Đường dẫn không tồn tại trong document.
- Đường dẫn tồn tại và chứa JSON null.

~~~sql
SELECT
    JSON_EXTRACT(preferences, '$.nickname') AS nickname_value,
    JSON_TYPE(JSON_EXTRACT(preferences, '$.nickname')) AS nickname_type
FROM user_preferences;
~~~

Nếu đường dẫn không tồn tại, JSON_EXTRACT trả SQL NULL. Nếu đường dẫn tồn tại với JSON null, kết quả là giá trị JSON null. Hãy định nghĩa rõ ý nghĩa của missing, null và chuỗi rỗng trong hợp đồng dữ liệu.

## 6. Đọc và trích xuất JSON

MySQL cung cấp các hàm JSON để lấy, kiểm tra và cập nhật thành phần document.

### 6.1. JSON_EXTRACT

~~~sql
SELECT JSON_EXTRACT(
    preferences,
    '$.notifications.email'
) AS email_notification
FROM user_preferences
WHERE user_id = 1;
~~~

JSON_EXTRACT trả về giá trị JSON tại path. Nếu cần một scalar SQL string để hiển thị hoặc so sánh, dùng JSON_UNQUOTE hoặc toán tử ->>.

### 6.2. Toán tử -> và ->>

~~~sql
SELECT
    preferences->'$.theme' AS theme_json,
    preferences->>'$.theme' AS theme_text
FROM user_preferences;
~~~

-> tương đương cách viết rút gọn của JSON_EXTRACT. ->> tương đương JSON_UNQUOTE(JSON_EXTRACT(...)) và trả biểu diễn scalar đã bỏ dấu quote JSON.

### 6.3. JSON_CONTAINS_PATH

Kiểm tra một hay nhiều path có tồn tại:

~~~sql
SELECT JSON_CONTAINS_PATH(
    preferences,
    'one',
    '$.theme',
    '$.notifications.email'
) AS has_required_path
FROM user_preferences;
~~~

one nghĩa là ít nhất một path tồn tại; all nghĩa là tất cả path được nêu phải tồn tại.

### 6.4. JSON_CONTAINS

Kiểm tra một candidate có nằm trong document hoặc tại path hay không:

~~~sql
SELECT user_id
FROM user_preferences
WHERE JSON_CONTAINS(
    preferences,
    JSON_QUOTE('dark'),
    '$.theme'
);
~~~

Với array:

~~~sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS(
    attributes,
    JSON_QUOTE('sale'),
    '$.tags'
);
~~~

JSON_CONTAINS so sánh theo semantics JSON. Đừng giả định nó giống phép LIKE trên chuỗi văn bản.

### 6.5. JSON_TYPE và JSON_LENGTH

~~~sql
SELECT
    JSON_TYPE(attributes) AS root_type,
    JSON_LENGTH(attributes, '$.tags') AS tag_count
FROM products;
~~~

JSON_TYPE giúp xác định loại giá trị JSON; JSON_LENGTH trả số phần tử object/array hoặc độ dài scalar theo semantics của hàm. Có thể dùng để kiểm tra cấu trúc trước khi xử lý, nhưng không thay thế validation đầy đủ.

## 7. Cập nhật document

### 7.1. JSON_SET

JSON_SET thêm path chưa có hoặc thay giá trị path đã có:

~~~sql
UPDATE user_preferences
SET preferences = JSON_SET(
    preferences,
    '$.theme', 'light',
    '$.notifications.email', FALSE
)
WHERE user_id = 1;
~~~

### 7.2. JSON_REPLACE

JSON_REPLACE chỉ thay path đã tồn tại:

~~~sql
UPDATE user_preferences
SET preferences = JSON_REPLACE(
    preferences,
    '$.theme', 'contrast'
)
WHERE user_id = 1;
~~~

Nếu path không tồn tại, JSON_REPLACE không thêm path đó.

### 7.3. JSON_INSERT

JSON_INSERT chỉ thêm path chưa tồn tại:

~~~sql
UPDATE user_preferences
SET preferences = JSON_INSERT(
    preferences,
    '$.density', 'compact'
)
WHERE user_id = 1;
~~~

### 7.4. JSON_REMOVE

~~~sql
UPDATE user_preferences
SET preferences = JSON_REMOVE(
    preferences,
    '$.legacyOption'
)
WHERE user_id = 1;
~~~

### 7.5. JSON_ARRAY_APPEND và JSON_ARRAY_INSERT

Thêm phần tử vào array:

~~~sql
UPDATE products
SET attributes = JSON_ARRAY_APPEND(
    attributes,
    '$.tags',
    'featured'
)
WHERE product_id = 10;
~~~

Chèn vào vị trí array được chỉ định:

~~~sql
UPDATE products
SET attributes = JSON_ARRAY_INSERT(
    attributes,
    '$.tags[0]',
    'new'
)
WHERE product_id = 10;
~~~

Trước khi cập nhật array, hãy quyết định có cho phép duplicate hay không và ai chịu trách nhiệm loại trùng. JSON array không tự có unique constraint trên từng phần tử.

### 7.6. Cập nhật một path vẫn là UPDATE hàng

Các hàm JSON giúp diễn đạt cập nhật một phần document. MySQL có thể tối ưu một số trường hợp partial in-place update, nhưng không nên giả định mọi JSON_SET đều chỉ ghi đúng vài byte hoặc không tạo chi phí row update. InnoDB vẫn khóa và quản lý phiên bản của hàng theo transaction; cập nhật cùng một hàng từ nhiều session vẫn có thể tranh chấp.

Nếu nhiều luồng thường xuyên cập nhật các thuộc tính độc lập của cùng một document lớn, hãy xem xét tách phần dữ liệu có vòng đời riêng thành các hàng hoặc bảng riêng.

## 8. Index cho thuộc tính JSON

Một cột JSON không thể được index như một B-tree thông thường trên toàn bộ document để phục vụ mọi path. Cần chọn rõ scalar path hoặc array membership cần truy vấn.

Các lựa chọn phổ biến:

1. Generated column trích xuất scalar path rồi tạo index.
2. Functional index trên biểu thức trích xuất JSON nếu phiên bản hỗ trợ.
3. Multi-valued index cho một số dạng JSON array từ MySQL 8.0.17.
4. Chuẩn hóa giá trị thành bảng con khi cần join, foreign key, unique constraint hoặc báo cáo phong phú.

### 8.1. Generated column cho scalar path

Giả sử products.attributes chứa:

~~~json
{
  "brand": "Acme",
  "color": "black",
  "weight_grams": 850
}
~~~

Nếu truy vấn thường xuyên lọc theo brand, tạo generated column:

~~~sql
ALTER TABLE products
ADD COLUMN brand VARCHAR(80)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
    ) STORED,
ADD INDEX ix_products_brand (brand);
~~~

Truy vấn có thể dùng cột brand:

~~~sql
SELECT product_id, sku, name
FROM products
WHERE brand = 'Acme';
~~~

Generated column giúp đưa một path thường xuyên truy vấn vào schema có kiểu và index rõ ràng. Cần quyết định VARCHAR length, character set/collation và xử lý path thiếu hoặc giá trị không đúng kiểu.

### 8.2. Generated column cho số

Khi trích xuất số, ép kiểu SQL rõ ràng:

~~~sql
ALTER TABLE products
ADD COLUMN weight_grams INT
    GENERATED ALWAYS AS (
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.weight_grams'))
            AS UNSIGNED
        )
    ) STORED,
ADD INDEX ix_products_weight (weight_grams);
~~~

Không dùng cột số dưới dạng chuỗi nếu cần range comparison. So sánh chuỗi có thể cho thứ tự khác so với số, ví dụ '100' và '20'.

### 8.3. Functional index

Trên MySQL 8.0.13 trở lên, có thể tạo functional index:

~~~sql
CREATE INDEX ix_products_brand_expr
ON products (
    (CAST(attributes->>'$.brand' AS CHAR(80)))
);
~~~

Biểu thức truy vấn cần khớp với biểu thức index theo quy tắc optimizer. Generated column có tên thường dễ đọc, tái sử dụng và kiểm soát kiểu hơn khi nhiều câu truy vấn cùng dùng path đó.

### 8.4. Unique index cho scalar JSON path

Nếu một giá trị trong JSON phải duy nhất, có thể trích xuất thành generated column rồi tạo unique index:

~~~sql
ALTER TABLE products
ADD COLUMN external_code VARCHAR(64)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.external_code'))
    ) STORED,
ADD UNIQUE KEY uq_products_external_code (external_code);
~~~

Phải xác định rõ hành vi khi path thiếu hoặc JSON null. Unique index cho phép nhiều SQL NULL trong MySQL, vì vậy nếu mọi sản phẩm bắt buộc có external_code, hãy thêm validation phù hợp, ví dụ CHECK về sự tồn tại của path và quy tắc kiểu.

Generated column có thể được index, nhưng không biến mọi đường dẫn JSON thành một quan hệ đầy đủ. Không dựa vào generated column để thay thế foreign key qua một path JSON; hãy lưu khóa tham chiếu thành cột quan hệ khi cần toàn vẹn tham chiếu.

### 8.5. Multi-valued index cho JSON array

MySQL 8.0.17+ hỗ trợ multi-valued index cho một số biểu thức array JSON. Ví dụ tags là một array chuỗi:

~~~json
{
  "tags": ["sale", "featured", "summer"]
}
~~~

Có thể tạo index:

~~~sql
CREATE INDEX ix_products_tags
ON products (
    (CAST(attributes->'$.tags' AS CHAR(32) ARRAY))
);
~~~

Truy vấn membership:

~~~sql
SELECT product_id, sku, name
FROM products
WHERE 'sale' MEMBER OF (attributes->'$.tags');
~~~

Multi-valued index tạo nhiều index entry cho một hàng, tương ứng các phần tử của array theo biểu thức được khai báo. Nó có giới hạn về kiểu và biểu thức, không phải index tổng quát cho mọi cấu trúc JSON.

### 8.6. Giới hạn của multi-valued index

- Mỗi hàng có thể sinh nhiều index entry; array lớn làm index tăng kích thước.
- Không thể dùng như một index B-tree thông thường để cung cấp mọi thứ tự sắp xếp hoặc range query.
- Không thay thế bảng quan hệ khi phần tử array cần foreign key, thuộc tính riêng, cập nhật độc lập hoặc unique constraint.
- Cần dùng biểu thức truy vấn được hỗ trợ để optimizer có thể tận dụng index.
- Hãy kiểm tra EXPLAIN trên đúng phiên bản MySQL và dữ liệu thực tế.

Nếu tags cần join với tag catalog, quản lý trạng thái từng tag hoặc thống kê quan hệ nhiều-nhiều, bảng product_tags thường rõ ràng và dễ ràng buộc hơn JSON array.

## 9. JSON_TABLE: biến document thành hàng quan hệ

JSON_TABLE cho phép chiếu dữ liệu JSON thành một tập hàng và cột để JOIN, lọc hoặc aggregate. MySQL hỗ trợ JSON_TABLE từ 8.0.4.

Giả sử một document có mảng items:

~~~json
{
  "order_id": 9001,
  "items": [
    {"sku": "KB-01", "quantity": 2, "unit_price": 35.50},
    {"sku": "MS-02", "quantity": 1, "unit_price": 18.00}
  ]
}
~~~

Trích xuất các item:

~~~sql
SELECT
    jt.sku,
    jt.quantity,
    jt.unit_price
FROM order_documents AS d,
JSON_TABLE(
    d.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        quantity INT PATH '$.quantity',
        unit_price DECIMAL(12,2) PATH '$.unit_price'
    )
) AS jt
WHERE d.document_id = 1;
~~~

JSON_TABLE biến mỗi phần tử trong $.items[*] thành một hàng. Các cột được trích xuất theo path đã khai báo. Có thể dùng kết quả đó để tính tổng:

~~~sql
SELECT
    d.document_id,
    SUM(jt.quantity * jt.unit_price) AS document_total
FROM order_documents AS d,
JSON_TABLE(
    d.document,
    '$.items[*]'
    COLUMNS (
        quantity INT PATH '$.quantity',
        unit_price DECIMAL(12,2) PATH '$.unit_price'
    )
) AS jt
GROUP BY d.document_id;
~~~

JSON_TABLE hữu ích cho migration, báo cáo hoặc đọc document có mảng. Tuy nhiên, nếu mọi truy vấn thường xuyên phải bung một mảng lớn, join với bảng khác và aggregate theo từng phần tử, đó là tín hiệu nên cân nhắc chuẩn hóa array thành bảng con.

### 9.1. Xử lý path thiếu và lỗi chuyển kiểu

JSON_TABLE cho phép định nghĩa hành vi khi path không tồn tại hoặc chuyển đổi lỗi bằng các mệnh đề ON EMPTY và ON ERROR. Hãy quyết định trường nào được phép thiếu, trường nào phải có và giá trị mặc định nào có ý nghĩa.

Ví dụ khai báo cột bắt buộc:

~~~sql
JSON_TABLE(
    d.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku' ERROR ON EMPTY ERROR ON ERROR,
        quantity INT PATH '$.quantity' ERROR ON EMPTY ERROR ON ERROR
    )
) AS jt
~~~

Validation cần phù hợp với hợp đồng document. Không dùng DEFAULT tùy tiện để biến dữ liệu lỗi thành một giá trị hợp lệ giả tạo.

## 10. Ràng buộc cấu trúc JSON

MySQL kiểm tra cú pháp JSON khi ghi vào cột JSON, nhưng nghiệp vụ thường cần thêm quy tắc:

- Root phải là object.
- Một số key phải tồn tại.
- Kiểu của key phải đúng.
- Giá trị thuộc enum cho phép.
- Số phải nằm trong miền hợp lệ.
- Array có giới hạn số phần tử hoặc không được trùng.

### 10.1. Kiểm tra kiểu và path bằng CHECK

~~~sql
CREATE TABLE product_metadata (
    product_id BIGINT NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id),
    CONSTRAINT chk_attributes_object
        CHECK (JSON_TYPE(attributes) = 'OBJECT'),
    CONSTRAINT chk_attributes_brand
        CHECK (
            JSON_CONTAINS_PATH(attributes, 'one', '$.brand')
        )
) ENGINE = InnoDB;
~~~

CHECK constraint được thực thi từ MySQL 8.0.16. Trước phiên bản này, cú pháp CHECK có thể được parse nhưng không được thực thi như ràng buộc. Khi hỗ trợ nhiều phiên bản, cần xác minh version và hành vi thực tế.

### 10.2. JSON Schema validation

MySQL 8.0.17+ cung cấp JSON_SCHEMA_VALID để kiểm tra document theo JSON Schema được hỗ trợ:

~~~sql
CREATE TABLE user_profiles (
    user_id BIGINT NOT NULL,
    profile JSON NOT NULL,
    PRIMARY KEY (user_id),
    CONSTRAINT chk_profile_schema
        CHECK (
            JSON_SCHEMA_VALID(
                '{
                  "type": "object",
                  "required": ["tier"],
                  "properties": {
                    "tier": {
                      "type": "string",
                      "enum": ["basic", "pro", "enterprise"]
                    }
                  }
                }',
                profile
            )
        )
) ENGINE = InnoDB;
~~~

JSON Schema validation giúp tập trung một phần hợp đồng dữ liệu ở database. Cần kiểm tra dialect và các keyword được MySQL hỗ trợ; không giả định mọi tính năng của JSON Schema hiện đại đều có sẵn.

### 10.3. Validation ở ứng dụng vẫn cần thiết

Database constraint bảo vệ dữ liệu kể cả khi có nhiều client ghi. Ứng dụng vẫn cần validation để trả lỗi dễ hiểu, kiểm tra quyền và áp dụng quy tắc theo ngữ cảnh người dùng. Không nên chỉ dựa vào UI hoặc một service duy nhất nếu còn batch job, import hoặc công cụ quản trị ghi trực tiếp.

## 11. Khi nào nên tách JSON array thành bảng quan hệ?

Một array nên trở thành bảng con nếu phần tử của nó có một hoặc nhiều đặc điểm:

- Có định danh riêng.
- Được cập nhật độc lập.
- Được nhiều document hoặc thực thể tham chiếu.
- Cần unique constraint hoặc foreign key.
- Cần lọc, join, group, sort hoặc báo cáo thường xuyên.
- Có thể tăng kích thước lớn và không cần tải cùng document cha.
- Nhiều transaction cập nhật các phần tử khác nhau và cần giảm tranh chấp trên cùng hàng cha.

### 11.1. Ví dụ chuyển tags thành quan hệ nhiều-nhiều

Nếu tag chỉ là nhãn hiển thị nhỏ, ít truy vấn, JSON array có thể đủ. Nếu tag có catalog và được dùng trong báo cáo:

~~~sql
CREATE TABLE tags (
    tag_id BIGINT NOT NULL AUTO_INCREMENT,
    tag_name VARCHAR(80) NOT NULL,
    PRIMARY KEY (tag_id),
    UNIQUE KEY uq_tags_name (tag_name)
) ENGINE = InnoDB;

CREATE TABLE product_tags (
    product_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (product_id, tag_id),
    KEY ix_product_tags_tag (tag_id, product_id),
    CONSTRAINT fk_product_tags_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT fk_product_tags_tag
        FOREIGN KEY (tag_id)
        REFERENCES tags (tag_id)
) ENGINE = InnoDB;
~~~

Giờ có thể tìm sản phẩm theo tag, đếm sản phẩm mỗi tag và bảo đảm tag tồn tại:

~~~sql
SELECT p.product_id, p.sku, p.name
FROM products AS p
JOIN product_tags AS pt
  ON pt.product_id = p.product_id
JOIN tags AS t
  ON t.tag_id = pt.tag_id
WHERE t.tag_name = 'sale';
~~~

Mô hình quan hệ rõ ràng hơn khi mỗi phần tử array đã trở thành thực thể nghiệp vụ.

### 11.2. Ví dụ order items

Nếu order items cần:

- Tổng doanh thu theo SKU.
- Kiểm tra product còn tồn tại.
- Cập nhật từng dòng.
- Join với kho hàng.
- Đếm số lượng theo sản phẩm.

thì bảng order_items phù hợp hơn việc lưu toàn bộ items trong JSON của orders.

Có thể vẫn lưu JSON snapshot của request hoặc payload bên ngoài để audit, nhưng dữ liệu nghiệp vụ cần ràng buộc và báo cáo nên nằm ở bảng quan hệ.

## 12. Snapshot, lịch sử và dữ liệu nguồn

Không phải mọi dữ liệu trùng lặp đều là denormalization sai. Snapshot có thể là quyết định nghiệp vụ đúng nếu nó biểu diễn giá trị tại một thời điểm.

Ví dụ đơn hàng cần lưu địa chỉ giao hàng tại lúc đặt:

~~~sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    shipping_address_snapshot JSON NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_date (customer_id, created_at)
) ENGINE = InnoDB;
~~~

Địa chỉ snapshot không tự thay đổi khi khách hàng cập nhật địa chỉ hồ sơ. Đây là bản chụp tại thời điểm giao dịch. Nếu cần tra cứu địa chỉ hiện tại, vẫn tham chiếu bảng customer_addresses riêng.

### 12.1. JSON snapshot không phải nguồn dữ liệu chuẩn cho mọi truy vấn

Nếu ứng dụng lưu một bản copy của tên sản phẩm, giá và địa chỉ trong JSON để hiển thị hóa đơn, hãy xác định:

- Snapshot được tạo tại thời điểm nào?
- Ai có quyền cập nhật?
- Có được sửa sau khi đơn đã hoàn tất không?
- Báo cáo doanh thu dùng giá snapshot hay giá hiện tại?
- Có cần lưu version hoặc checksum không?

Không dùng snapshot thay cho bảng nguồn khi cần cập nhật trạng thái hiện tại hoặc bảo đảm tham chiếu.

### 12.2. Event payload và audit

JSON phù hợp để lưu payload sự kiện bên ngoài có schema thay đổi theo version. Tuy nhiên, nếu cần truy vấn thường xuyên theo event_type, tenant_id, occurred_at hoặc actor_id, hãy cân nhắc đưa các trường đó ra cột quan hệ và giữ payload còn lại trong JSON.

## 13. Cập nhật đồng thời và ranh giới aggregate

JSON document gom nhiều thuộc tính vào một hàng. Điều này thuận lợi khi các thuộc tính được đọc/ghi cùng nhau, nhưng có thể làm tăng tranh chấp nếu nhiều luồng cập nhật những phần độc lập trong cùng document.

### 13.1. Một document, nhiều writer

Giả sử một profile có:

~~~json
{
  "notification_settings": {"email": true},
  "display_settings": {"theme": "dark"}
}
~~~

Một request cập nhật email notification, request khác cập nhật theme. Cả hai cùng UPDATE một hàng. InnoDB vẫn điều phối khóa hàng và transaction; các cập nhật có thể phải chờ nhau.

Nếu hai nhóm thuộc tính có tần suất cập nhật cao và độc lập, tách thành bảng riêng có thể giảm tranh chấp và giúp mỗi transaction khóa phạm vi nhỏ hơn.

### 13.2. Cập nhật có điều kiện

Khi ghi JSON dựa trên trạng thái đã đọc, có thể dùng optimistic concurrency bằng version:

~~~sql
ALTER TABLE user_preferences
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
~~~

Ứng dụng đọc version rồi cập nhật:

~~~sql
UPDATE user_preferences
SET preferences = JSON_SET(preferences, '$.theme', 'light'),
    version = version + 1
WHERE user_id = 1
  AND version = 7;
~~~

Nếu affected rows bằng 0, version đã thay đổi hoặc hàng không tồn tại; ứng dụng cần đọc lại và giải quyết xung đột. Cơ chế này hữu ích khi muốn phát hiện lost update theo hợp đồng ứng dụng.

### 13.3. JSON không thay thế transaction nhiều bảng

Nếu một hành động cập nhật JSON document và đồng thời trừ tồn kho, ghi payment hoặc tạo order item, hãy dùng transaction InnoDB để bảo đảm các thay đổi liên quan được commit hoặc rollback cùng nhau.

## 14. Kích thước document và chi phí vận hành

Document càng lớn, càng nhiều thuộc tính và array thì càng cần quan tâm:

- Kích thước hàng và chi phí đọc/ghi.
- Số lượng path ứng dụng phải hiểu.
- Chi phí trích xuất JSON trong truy vấn.
- Số index bổ sung và dung lượng.
- Số writer cập nhật cùng một hàng.
- Khả năng log, backup, replication và truyền payload qua mạng.

### 14.1. Không gom dữ liệu không giới hạn vào một document

Không nên đưa lịch sử giao dịch, hàng nghìn log entry hoặc danh sách item tăng vô hạn vào một JSON array của một hàng. Việc tải hoặc cập nhật document có thể ngày càng tốn kém; một hàng lớn cũng trở thành điểm tranh chấp.

Hãy tách collection có kích thước không giới hạn thành bảng con với khóa cha và index theo thời gian hoặc thứ tự nghiệp vụ.

### 14.2. Giới hạn độ sâu và validation

MySQL áp dụng giới hạn độ sâu lồng nhau của JSON và có thể từ chối document quá sâu. Ứng dụng nên đặt giới hạn nhỏ hơn theo hợp đồng domain để dữ liệu không trở thành cấu trúc lồng nhau khó xử lý.

### 14.3. Không dùng JSON cho dữ liệu nhị phân

JSON phù hợp với dữ liệu có cấu trúc văn bản. Nội dung nhị phân lớn nên được lưu bằng BLOB hoặc object storage; document có thể giữ metadata và định danh tham chiếu.

## 15. Lưu ý về phiên bản MySQL

Một số tính năng JSON và index được bổ sung theo từng phiên bản. Khi triển khai, kiểm tra SELECT VERSION() và tài liệu đúng phiên bản.

| Tính năng | Phiên bản MySQL tối thiểu |
|---|---|
| Kiểu dữ liệu JSON | 5.7.8 |
| Toán tử JSON -> | 5.7.9 |
| Toán tử JSON ->> | 5.7.13 |
| JSON_TABLE | 8.0.4 |
| Functional index | 8.0.13 |
| CHECK constraint được thực thi | 8.0.16 |
| Multi-valued index | 8.0.17 |
| JSON_SCHEMA_VALID | 8.0.17 |
| JSON_VALUE | 8.0.21 |

Các ví dụ trong bài hướng đến MySQL 8.0 hiện đại. Nếu hệ thống dùng phiên bản cũ hơn, có thể cần generated column thay functional index, validation ở ứng dụng thay CHECK được thực thi hoặc thiết kế khác cho JSON array.

## 16. Đọc execution plan cho truy vấn JSON

Đừng giả định JSON path tự động được index. Hãy kiểm tra plan của truy vấn thực tế.

### 16.1. Truy vấn chưa có index cho path

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM products
WHERE attributes->>'$.brand' = 'Acme';
~~~

Nếu không có functional index hoặc generated column tương ứng, MySQL có thể phải đọc nhiều hàng rồi trích xuất path để lọc.

### 16.2. Truy vấn qua generated column

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM products
WHERE brand = 'Acme';
~~~

Quan sát possible_keys, key, rows, filtered và Extra. Nếu optimizer chọn ix_products_brand, truy vấn có thể tìm qua index thay vì đánh giá path trên mọi hàng.

### 16.3. EXPLAIN ANALYZE

Trên MySQL 8.0.18+:

~~~sql
EXPLAIN ANALYZE
SELECT product_id, sku, name
FROM products
WHERE brand = 'Acme';
~~~

EXPLAIN ANALYZE thực thi truy vấn và báo actual rows, loops cùng thời gian iterator. Chạy trên dữ liệu đại diện; bảng lab quá nhỏ không thể chứng minh index sẽ cải thiện workload production.

### 16.4. Theo dõi cả chi phí ghi

Thêm generated column hoặc index giúp một số truy vấn đọc, nhưng tăng chi phí INSERT/UPDATE và dung lượng. Nếu attributes thay đổi thường xuyên, mỗi index phụ thuộc JSON path cũng cần được duy trì.

Đo cả:

- Latency và throughput truy vấn đọc.
- Thời gian ghi và số hàng cập nhật.
- Dung lượng index.
- Tỷ lệ path thiếu hoặc sai kiểu.
- Số lượng hàng thực tế được đọc.

## 17. Quy trình thiết kế mô hình

Áp dụng quy trình sau cho mỗi nhóm dữ liệu:

1. Liệt kê thực thể và xác định vòng đời độc lập.
2. Xác định grain của mỗi hàng và quan hệ một-một, một-nhiều hoặc nhiều-nhiều.
3. Liệt kê truy vấn đọc/ghi chính, cột lọc, join, group, sort và range.
4. Đưa khóa, quan hệ, thuộc tính cần unique và chỉ tiêu báo cáo vào mô hình quan hệ.
5. Nhóm các thuộc tính linh hoạt được đọc/ghi cùng aggregate vào JSON.
6. Xác định các JSON path cần lọc; tạo generated column, functional index hoặc multi-valued index nếu phù hợp.
7. Tách array thành bảng con nếu phần tử cần khóa, foreign key, cập nhật độc lập hoặc báo cáo thường xuyên.
8. Xác định validation ở database và ứng dụng.
9. Xác định kích thước tối đa, version document và chính sách dữ liệu thiếu/null.
10. Dùng EXPLAIN và EXPLAIN ANALYZE để xác minh access path.
11. Đo cả read workload, write workload, contention và storage.
12. Ghi rõ nguồn dữ liệu chuẩn và cách đồng bộ mọi snapshot hoặc dữ liệu dẫn xuất.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Đưa email hoặc SKU vào JSON dù cần unique | Khó bảo đảm duy nhất | Dùng cột quan hệ và unique index |
| Nhúng product IDs vào array nhưng cần FK | Database không kiểm tra tham chiếu từng phần tử | Dùng bảng liên kết |
| Lưu số dưới dạng JSON string | So sánh và ép kiểu dễ sai | Chuẩn hóa kiểu hoặc generated column có CAST |
| Query nhiều JSON path không index | Đọc nhiều hàng và tính biểu thức lặp lại | Generated column hoặc functional index |
| Một document chứa lịch sử không giới hạn | Hàng lớn, cập nhật và đọc tốn kém | Tách bảng con theo thời gian hoặc khóa |
| Dùng JSON array cho quan hệ nhiều-nhiều có báo cáo | Khó join, group và kiểm tra duplicate | Chuẩn hóa thành bảng liên kết |
| Giả định JSON hợp lệ là dữ liệu hợp lệ nghiệp vụ | Có key sai kiểu hoặc giá trị không hợp lệ | CHECK, JSON Schema và validation ứng dụng |
| Dùng snapshot làm nguồn dữ liệu hiện tại | Dữ liệu hiện tại và snapshot lệch ý nghĩa | Định nghĩa nguồn chuẩn và thời điểm snapshot |
| Nhiều writer cập nhật cùng document lớn | Tranh chấp trên cùng hàng | Tách aggregate hoặc dùng version check |
| Tạo index cho mọi JSON path | Tăng dung lượng và chi phí ghi | Chỉ index path có workload rõ |
| Nghĩ JSON_TABLE là miễn phí | Chi phí bung array và xử lý hàng vẫn tồn tại | Đo plan; cân nhắc bảng quan hệ |
| Dùng JSON cho file hoặc blob lớn | Payload khó truy vấn và truyền tải | BLOB hoặc object storage, JSON giữ metadata |

## 19. Bài thực hành: chọn mô hình cho catalog sản phẩm

Thực hiện trên MySQL 8.0 trong database lab. Bài tập minh họa ba mô hình: quan hệ, JSON và kết hợp. Dùng schema riêng, không chạy trên bảng production.

### 19.1. Tạo bảng kết hợp

~~~sql
CREATE TABLE lab_products (
    product_id BIGINT NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    attributes JSON NOT NULL,
    brand VARCHAR(80)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) STORED,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_lab_products_sku (sku),
    KEY ix_lab_products_brand (brand)
) ENGINE = InnoDB;
~~~

sku, name và price là dữ liệu lõi. brand được trích xuất thành generated column để có thể lọc bằng index; các thuộc tính khác có thể linh hoạt trong JSON.

### 19.2. Nạp dữ liệu

~~~sql
INSERT INTO lab_products (sku, name, price, attributes)
VALUES
    (
        'KB-01',
        'Mechanical Keyboard',
        79.90,
        JSON_OBJECT(
            'brand', 'Acme',
            'switch', 'brown',
            'layout', 'US',
            'tags', JSON_ARRAY('office', 'featured')
        )
    ),
    (
        'MS-02',
        'Wireless Mouse',
        29.50,
        JSON_OBJECT(
            'brand', 'Acme',
            'dpi', 1600,
            'color', 'black',
            'tags', JSON_ARRAY('office', 'sale')
        )
    ),
    (
        'HD-03',
        'Headset',
        59.00,
        JSON_OBJECT(
            'brand', 'Northwind',
            'wireless', TRUE,
            'color', 'black',
            'tags', JSON_ARRAY('audio')
        )
    );
~~~

### 19.3. Truy vấn scalar JSON

~~~sql
SELECT
    product_id,
    sku,
    attributes->>'$.color' AS color
FROM lab_products
WHERE attributes->>'$.color' = 'black';
~~~

Đọc EXPLAIN và quan sát truy vấn có dùng index hay không. Hiện tại chưa có index cho color.

### 19.4. Truy vấn qua generated column

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM lab_products
WHERE brand = 'Acme';
~~~

Quan sát key có thể là ix_lab_products_brand. So sánh với truy vấn trực tiếp trên JSON path:

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM lab_products
WHERE attributes->>'$.brand' = 'Acme';
~~~

### 19.5. Truy vấn array

~~~sql
SELECT product_id, sku
FROM lab_products
WHERE JSON_CONTAINS(
    attributes,
    JSON_QUOTE('sale'),
    '$.tags'
);
~~~

Nếu workload membership theo tags thường xuyên và MySQL từ 8.0.17, thử multi-valued index trên môi trường lab. Nếu tag cần catalog và quan hệ nhiều-nhiều, tạo bảng tags/product_tags thay vì giữ array.

### 19.6. Tạo bảng quan hệ cho tags

~~~sql
CREATE TABLE lab_tags (
    tag_id BIGINT NOT NULL AUTO_INCREMENT,
    tag_name VARCHAR(50) NOT NULL,
    PRIMARY KEY (tag_id),
    UNIQUE KEY uq_lab_tags_name (tag_name)
) ENGINE = InnoDB;

CREATE TABLE lab_product_tags (
    product_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (product_id, tag_id),
    KEY ix_lab_product_tags_tag (tag_id, product_id),
    CONSTRAINT fk_lab_product_tags_product
        FOREIGN KEY (product_id)
        REFERENCES lab_products (product_id),
    CONSTRAINT fk_lab_product_tags_tag
        FOREIGN KEY (tag_id)
        REFERENCES lab_tags (tag_id)
) ENGINE = InnoDB;
~~~

Nạp tags và quan hệ:

~~~sql
INSERT INTO lab_tags (tag_name)
VALUES ('office'), ('featured'), ('sale'), ('audio');

INSERT INTO lab_product_tags (product_id, tag_id)
SELECT p.product_id, t.tag_id
FROM lab_products AS p
JOIN lab_tags AS t
  ON JSON_CONTAINS(
       p.attributes,
       JSON_QUOTE(t.tag_name),
       '$.tags'
     );
~~~

So sánh truy vấn JSON_CONTAINS với JOIN qua bảng quan hệ. Đánh giá tính dễ đọc, index, khả năng kiểm tra tham chiếu và chi phí đồng bộ nếu vẫn giữ tags trong JSON.

### 19.7. JSON_TABLE cho báo cáo

~~~sql
SELECT
    p.sku,
    jt.tag
FROM lab_products AS p,
JSON_TABLE(
    p.attributes,
    '$.tags[*]'
    COLUMNS (
        tag VARCHAR(50) PATH '$'
    )
) AS jt
ORDER BY p.sku, jt.tag;
~~~

Quan sát cách một array được chuyển thành nhiều hàng. Nếu báo cáo và join theo tag xuất hiện thường xuyên, bảng lab_product_tags có thể phù hợp hơn.

### 19.8. Dọn bảng lab

~~~sql
DROP TABLE lab_product_tags;
DROP TABLE lab_tags;
DROP TABLE lab_products;
~~~

Chỉ xóa các bảng lab vừa tạo.

### 19.9. Kết quả cần đạt

- Giải thích vì sao SKU phải là cột quan hệ có unique index.
- Xác định khi nào thuộc tính linh hoạt phù hợp với JSON.
- Tạo generated column và đọc EXPLAIN cho truy vấn brand.
- Giải thích vì sao JSON array không tự có foreign key hoặc unique constraint cho từng phần tử.
- So sánh JSON_CONTAINS, multi-valued index và bảng liên kết.
- Dùng JSON_TABLE để bung array thành hàng.
- Chọn mô hình phù hợp theo query workload, consistency và khả năng cập nhật.

## 20. Checklist trước khi chốt schema

### Dữ liệu và domain

- Mỗi thực thể có định danh và vòng đời riêng chưa?
- Thuộc tính nào là bắt buộc, duy nhất hoặc có miền giá trị?
- Giá trị nào là snapshot tại thời điểm giao dịch?
- Missing, SQL NULL, JSON null và giá trị mặc định có ý nghĩa gì?

### Truy vấn

- Cột nào xuất hiện trong WHERE, JOIN, GROUP BY và ORDER BY?
- Đường dẫn JSON nào được truy vấn thường xuyên?
- Array có cần membership, join hoặc aggregate không?
- Query có thể dùng generated column, functional index hoặc multi-valued index không?

### Tính toàn vẹn

- Có cần foreign key tới từng phần tử không?
- Có cần unique giữa các document không?
- Có cần CHECK hoặc JSON Schema validation không?
- Có nhiều writer cập nhật cùng một document không?

### Vận hành

- Document có thể tăng kích thước không giới hạn không?
- Có version schema hoặc quy trình migrate document không?
- Có thể rebuild generated data hoặc index không?
- Backup, replication và logging có chịu được payload không?
- Có cần giới hạn quyền đọc các trường nhạy cảm trong JSON không?

## 21. Nguyên tắc cần ghi nhớ

- Chọn mô hình từ query workload, quan hệ nghiệp vụ, consistency và vòng đời dữ liệu.
- Dùng mô hình quan hệ cho thực thể độc lập, khóa, foreign key, unique constraint và báo cáo thường xuyên.
- Dùng JSON document cho aggregate có cấu trúc linh hoạt, thường được đọc/ghi cùng nhau và không cần quan hệ độc lập cho từng phần tử.
- Mô hình kết hợp giữ cột lõi có kiểu và index rõ ràng, dùng JSON cho thuộc tính mở rộng hoặc snapshot.
- JSON hợp lệ về cú pháp chưa chắc hợp lệ theo nghiệp vụ; cần validation ở database và ứng dụng.
- SQL NULL, path thiếu và JSON null là các trạng thái khác nhau.
- Không dựa vào thứ tự key hoặc whitespace của JSON để xác định nội dung.
- Index cho JSON path cần generated column, functional index hoặc multi-valued index phù hợp; không có một index tổng quát cho mọi path.
- Dùng cột quan hệ cho giá trị cần foreign key; không giả định JSON path tự có referential integrity.
- Tách JSON array thành bảng con khi phần tử cần định danh, cập nhật độc lập, unique, foreign key, join hoặc báo cáo.
- JSON_TABLE hữu ích để biến document thành hàng, nhưng không miễn phí; đo chi phí nếu dùng thường xuyên.
- Một document lớn có thể tăng chi phí đọc/ghi và tranh chấp nếu nhiều writer cập nhật cùng hàng.
- Snapshot là dữ liệu tại một thời điểm; xác định rõ nguồn dữ liệu chuẩn và quy tắc đồng bộ.
- Kiểm tra phiên bản MySQL trước khi dùng functional index, CHECK enforcement, multi-valued index, JSON Schema validation hoặc JSON_TABLE.
- Dùng EXPLAIN và EXPLAIN ANALYZE để xác minh access path và thời gian trên dữ liệu đại diện.
- Đo cả workload đọc, ghi, index storage, contention và vận hành trước khi chốt mô hình.

Thiết kế tốt không phụ thuộc vào việc dùng JSON hay bảng quan hệ nhiều hơn. Điều quan trọng là đặt mỗi dữ liệu ở nơi có thể bảo đảm đúng và truy vấn hiệu quả: quan hệ cho thực thể, khóa và kết nối; JSON cho cấu trúc linh hoạt thuộc một aggregate; mô hình kết hợp cho hệ thống có cả hai nhu cầu. Hãy để query workload và ràng buộc nghiệp vụ quyết định ranh giới, rồi xác nhận lựa chọn bằng execution plan và phép đo thực tế.
