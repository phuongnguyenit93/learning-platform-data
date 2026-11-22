# INSERT ON DUPLICATE KEY UPDATE và ý nghĩa của khóa xung đột

MySQL cung cấp \`INSERT ... ON DUPLICATE KEY UPDATE\` để thực hiện thao tác upsert: thử thêm một hàng mới; nếu giá trị khóa chính hoặc unique key bị trùng với hàng hiện có, chuyển sang cập nhật hàng xung đột. Cú pháp này thường được dùng để đồng bộ dữ liệu, nhập dữ liệu lặp lại, cập nhật hồ sơ theo mã nghiệp vụ và duy trì các bảng tổng hợp.

Điểm quan trọng là MySQL không cho chỉ định một conflict target cụ thể trong cú pháp này. Bất kỳ vi phạm PRIMARY KEY hoặc UNIQUE index nào cũng có thể kích hoạt nhánh UPDATE. Vì vậy, thiết kế khóa trong bảng quyết định trực tiếp hàng nào có thể bị cập nhật.

Bài học thuộc phạm vi DATABASE_MYSQL: thay đổi dữ liệu an toàn, hiểu khóa chính và khóa duy nhất, xử lý xung đột khi ghi đồng thời, kiểm soát dữ liệu nhập từ hệ thống khác và sử dụng prepared statement trong ứng dụng.

## 1. Upsert là gì?

Upsert là cách gọi kết hợp giữa UPDATE và INSERT. Về mặt nghiệp vụ, một thao tác upsert thường có ý nghĩa:

- Nếu bản ghi chưa tồn tại theo khóa định danh, tạo bản ghi mới.
- Nếu bản ghi đã tồn tại theo khóa định danh, cập nhật các thuộc tính được chỉ định.

Trong MySQL, cú pháp phổ biến:

~~~sql
INSERT INTO table_name (column_a, column_b, column_c)
VALUES (value_a, value_b, value_c)
ON DUPLICATE KEY UPDATE
    column_b = value_b,
    column_c = value_c;
~~~

Ví dụ bảng lưu hồ sơ đồng bộ:

~~~sql
CREATE TABLE customer_sync (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_sync_email (email)
) ENGINE = InnoDB;
~~~

Thử ghi một khách hàng:

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyễn An', 1, NOW(6))
ON DUPLICATE KEY UPDATE
    display_name = 'Nguyễn An',
    source_version = 1,
    updated_at = NOW(6);
~~~

Nếu chưa có hàng xung đột, MySQL INSERT hàng mới. Nếu customer_id đã tồn tại hoặc email đã được dùng bởi một hàng khác, nhánh UPDATE được kích hoạt theo unique key vi phạm. Phần sau sẽ giải thích vì sao có nhiều unique key thì cần đặc biệt cẩn thận.

## 2. Điều gì được xem là khóa xung đột?

Nhánh ON DUPLICATE KEY UPDATE được kích hoạt khi INSERT gây duplicate key trên:

- PRIMARY KEY.
- Bất kỳ UNIQUE index nào của bảng.

Các loại index không unique như INDEX thông thường không kích hoạt nhánh này. Hai hàng có cùng giá trị ở một cột chỉ có index thường vẫn có thể được chèn.

Ví dụ:

~~~sql
CREATE TABLE product_catalog (
    product_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(50) NOT NULL,
    barcode VARCHAR(50) NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_product_sku (sku),
    UNIQUE KEY uq_product_barcode (barcode),
    KEY idx_product_name (product_name)
) ENGINE = InnoDB;
~~~

Một INSERT có thể xung đột do product_id, sku hoặc barcode. Index idx_product_name không phải unique nên trùng tên sản phẩm không tự kích hoạt nhánh UPDATE.

### 2.1. Xung đột PRIMARY KEY

~~~sql
INSERT INTO product_catalog
    (product_id, sku, barcode, product_name)
VALUES
    (1, 'SKU-001', '893000000001', 'Bàn phím cơ')
ON DUPLICATE KEY UPDATE
    product_name = 'Bàn phím cơ phiên bản mới';
~~~

Nếu product_id = 1 đã tồn tại, MySQL chuyển sang UPDATE hàng đó.

### 2.2. Xung đột UNIQUE index

~~~sql
INSERT INTO product_catalog
    (product_id, sku, barcode, product_name)
VALUES
    (2, 'SKU-001', '893000000002', 'Bàn phím khác')
ON DUPLICATE KEY UPDATE
    product_name = 'Bàn phím được cập nhật';
~~~

Dù product_id = 2 chưa tồn tại, sku = 'SKU-001' đã được sử dụng. Unique key sku tạo xung đột và nhánh UPDATE được thực hiện trên hàng hiện có có sku đó.

Đây là điểm khác với cách nhiều người hình dung: nhánh UPDATE không nhất thiết cập nhật hàng có cùng primary key được gửi vào. Một unique key khác cũng có thể tìm ra hàng đích.

## 3. MySQL không có conflict target trong cú pháp này

Một số hệ quản trị cho phép chỉ định rõ constraint nào được dùng làm mục tiêu xung đột. Cú pháp MySQL \`ON DUPLICATE KEY UPDATE\` không có phần như \`ON CONFLICT (column_name)\`.

Điều đó có nghĩa:
- MySQL xét các PRIMARY KEY và UNIQUE index.
- Bất kỳ khóa duy nhất nào bị vi phạm đều có thể kích hoạt nhánh UPDATE.
- Người viết không thể yêu cầu cú pháp chỉ xử lý xung đột ở uq_product_sku và bỏ qua xung đột ở uq_product_barcode.

Vì vậy, nếu bảng có nhiều unique key, hãy xác định mọi đường dẫn xung đột có thể xảy ra và bảo đảm chúng đều dẫn tới cùng một hàng nghiệp vụ hoặc cùng một cách xử lý an toàn.

### 3.1. Rủi ro khi nhiều unique key trỏ tới hai hàng khác nhau

Giả sử bảng có hai hàng:

| product_id | sku | barcode |
|---:|---|---|
| 1 | SKU-A | BAR-A |
| 2 | SKU-B | BAR-B |

Ứng dụng gửi một hàng mới:

~~~sql
INSERT INTO product_catalog
    (product_id, sku, barcode, product_name)
VALUES
    (1, 'SKU-B', 'BAR-C', 'Sản phẩm mới')
ON DUPLICATE KEY UPDATE
    product_name = 'Đã cập nhật';
~~~

Dữ liệu mới trùng product_id của hàng 1 nhưng sku của hàng 2. Câu lệnh không thể diễn đạt rằng ứng dụng muốn xử lý riêng xung đột product_id hay riêng xung đột sku; không nên dựa vào một thứ tự ưu tiên unique index để chọn hàng đích. Nếu nhánh UPDATE thay đổi một cột unique thành giá trị đang thuộc hàng khác, thao tác cập nhật có thể tiếp tục vi phạm unique key và thất bại với duplicate key error. Hãy xử lý trường hợp các khóa nhận diện hai thực thể khác nhau trước khi thực hiện upsert.

Không thiết kế logic nghiệp vụ dựa vào giả định MySQL sẽ chọn đúng unique key mà ứng dụng mong muốn. Nếu các unique key có thể nhận diện các thực thể khác nhau, cần kiểm tra và giải quyết xung đột trước, hoặc dùng transaction với các bước SELECT/UPDATE/INSERT được kiểm soát rõ ràng.

### 3.2. Thiết kế khóa để upsert có ý nghĩa duy nhất

Một mô hình upsert tốt thường có một khóa định danh nghiệp vụ rõ ràng, chẳng hạn:

- Mã khách hàng từ hệ thống nguồn.
- Mã sản phẩm duy nhất của nhà cung cấp.
- Mã sự kiện bên ngoài.
- Khóa tenant_id + external_id.

Ví dụ:

~~~sql
CREATE TABLE imported_customer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_system VARCHAR(40) NOT NULL,
    external_customer_id VARCHAR(100) NOT NULL,
    email VARCHAR(254) NULL,
    display_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_source_customer (
        source_system,
        external_customer_id
    )
) ENGINE = InnoDB;
~~~

Ứng dụng upsert theo khóa nguồn:

~~~sql
INSERT INTO imported_customer
    (source_system, external_customer_id, email, display_name)
VALUES
    ('CRM_A', 'C-1001', 'an@example.com', 'Nguyễn An')
ON DUPLICATE KEY UPDATE
    email = 'an@example.com',
    display_name = 'Nguyễn An';
~~~

Ở đây unique key ghép thể hiện rõ một khách hàng trong một hệ thống nguồn. Nếu email cũng cần unique toàn cục, hãy xác định xung đột email có thể chỉ ra một khách hàng khác hay không. Nếu có, phải xử lý riêng thay vì để upsert tự quyết định bản ghi đích.

## 4. NULL trong unique key và upsert

MySQL cho phép nhiều giá trị NULL trong unique index. Do đó, NULL trong cột unique thường không tạo duplicate key.

Ví dụ:

~~~sql
CREATE TABLE optional_reference (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    external_code VARCHAR(80) NULL,
    description VARCHAR(150) NOT NULL,
    UNIQUE KEY uq_external_code (external_code)
);
~~~

Hai lệnh sau có thể tạo hai hàng khác nhau:

~~~sql
INSERT INTO optional_reference (external_code, description)
VALUES (NULL, 'Chưa có mã');

INSERT INTO optional_reference (external_code, description)
VALUES (NULL, 'Vẫn chưa có mã');
~~~

Vì NULL không được xem là một giá trị trùng trong unique index, nhánh ON DUPLICATE KEY UPDATE không được kích hoạt chỉ vì cột external_code của hai hàng đều NULL.

Với unique key ghép, nếu một hoặc nhiều thành phần là NULL, nhiều tổ hợp có thể cùng tồn tại. Nếu ứng dụng muốn dùng cột làm khóa upsert, cần bảo đảm khóa đó thực sự có giá trị, thường bằng NOT NULL.

Không dùng nullable unique key làm khóa định danh duy nhất cho upsert khi bản ghi có thể không cung cấp giá trị khóa.

## 5. Cập nhật bằng giá trị hàng mới

Khi duplicate key xảy ra, nhánh UPDATE có thể dùng:
- Giá trị hiện có trong hàng đích.
- Giá trị của hàng đang được INSERT.
- Biểu thức tính toán kết hợp cả hai.

Cần phân biệt rõ hai phía để tránh cập nhật nhầm.

### 5.1. Dùng alias hàng mới trong MySQL 8.0.19+

Cú pháp alias cho hàng mới được hỗ trợ từ MySQL 8.0.19:

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyễn An mới', 2, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    email = incoming.email,
    display_name = incoming.display_name,
    source_version = incoming.source_version,
    updated_at = incoming.updated_at;
~~~

Alias incoming đại diện cho hàng đang được đưa vào. Khi có xung đột, các biểu thức incoming.email, incoming.display_name... đọc giá trị của hàng mới để gán vào hàng hiện có.

Đây là cách viết nên ưu tiên trên MySQL hiện đại vì nó rõ ràng và tránh phụ thuộc vào hàm VALUES() đã deprecated.

### 5.2. VALUES(column) trong cú pháp cũ

Trước khi hỗ trợ row alias, cách viết phổ biến là:

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyễn An mới', 2, NOW(6))
ON DUPLICATE KEY UPDATE
    email = VALUES(email),
    display_name = VALUES(display_name),
    source_version = VALUES(source_version),
    updated_at = VALUES(updated_at);
~~~

Hàm VALUES(column) trả về giá trị mà INSERT định chèn cho cột tương ứng.

Từ MySQL 8.0.20, việc dùng VALUES() trong mệnh đề ON DUPLICATE KEY UPDATE đã bị deprecated. Nó vẫn tồn tại trong các bản MySQL hiện tại để tương thích, nhưng nên chuyển sang row alias. Với MySQL 5.7, row alias chưa được hỗ trợ và VALUES(column) là cách thường dùng.

Không nhầm VALUES(column) trong ngữ cảnh này với cú pháp VALUES của phần INSERT. Tài liệu MySQL đánh dấu hàm tham chiếu giá trị hàng mới này là deprecated.

### 5.3. Dùng tên cột hiện có và alias hàng mới

~~~sql
INSERT INTO inventory (
    product_id,
    quantity,
    updated_at
)
VALUES (10, 5, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity,
    updated_at = incoming.updated_at;
~~~

Khi duplicate:
- inventory.quantity là số lượng đang lưu trong hàng đích.
- incoming.quantity là số lượng của lần nhập mới.
- Giá trị mới là tổng hai số lượng.

Tên bảng trước cột giúp phân biệt giá trị cũ với giá trị mới. Nếu dùng alias bảng trong INSERT, hãy dùng đúng cú pháp alias được MySQL hỗ trợ và tránh đặt tên gây mơ hồ.

## 6. Gán lại, cộng dồn hay chỉ cập nhật khi dữ liệu mới hơn?

ON DUPLICATE KEY UPDATE không tự quyết định chính sách cập nhật. Người viết phải chọn biểu thức đúng với nghiệp vụ.

### 6.1. Ghi đè bằng giá trị mới

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyễn An mới', 2, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    email = incoming.email,
    display_name = incoming.display_name,
    source_version = incoming.source_version,
    updated_at = incoming.updated_at;
~~~

Dùng khi dữ liệu từ nguồn gửi tới được xem là bản chính thức mới nhất.

### 6.2. Cộng dồn số lượng

~~~sql
INSERT INTO inventory (
    product_id,
    quantity,
    updated_at
)
VALUES (10, 5, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity,
    updated_at = incoming.updated_at;
~~~

Dùng khi mỗi lần ghi biểu diễn một lượng tăng thêm. Cần nhớ rằng lặp lại cùng một yêu cầu có thể cộng số lượng nhiều lần; đây là vấn đề idempotency, được giải thích ở mục 12.

### 6.3. Chỉ nhận phiên bản mới hơn

~~~sql
INSERT INTO customer_sync (
    customer_id,
    email,
    display_name,
    source_version,
    updated_at
)
VALUES (
    101,
    'an@example.com',
    'Nguyễn An phiên bản 3',
    3,
    NOW(6)
) AS incoming
ON DUPLICATE KEY UPDATE
    email = IF(
        incoming.source_version > customer_sync.source_version,
        incoming.email,
        customer_sync.email
    ),
    display_name = IF(
        incoming.source_version > customer_sync.source_version,
        incoming.display_name,
        customer_sync.display_name
    ),
    updated_at = IF(
        incoming.source_version > customer_sync.source_version,
        incoming.updated_at,
        customer_sync.updated_at
    ),
    source_version = GREATEST(
        customer_sync.source_version,
        incoming.source_version
    );
~~~

Ví dụ minh họa quy tắc chỉ chấp nhận phiên bản cao hơn. Khi dùng nhiều phép gán phụ thuộc vào cùng một cột đang cập nhật, cần chú ý thứ tự đánh giá phép gán của UPDATE trong MySQL. Để tránh biểu thức sau đọc giá trị đã bị thay đổi bởi phép gán trước, hãy sắp xếp assignment cẩn thận hoặc thiết kế câu lệnh sao cho điều kiện được tính từ các cột không bị sửa trước đó. Với logic phức tạp, nên dùng transaction và một câu UPDATE rõ ràng sau khi xác định hàng đích.

### 6.4. Giữ giá trị cũ nếu giá trị mới là NULL

Nếu email mới NULL có nghĩa là nguồn không cung cấp thay đổi, có thể viết:

~~~sql
email = COALESCE(incoming.email, customer_sync.email)
~~~

Nhưng nếu NULL có nghĩa “xóa email”, COALESCE sẽ làm mất khả năng xóa. Cần phân biệt:
- NULL có nghĩa không gửi trường.
- NULL có nghĩa xóa giá trị.
- Trường bị bỏ khỏi INSERT.
- Trường được gửi với giá trị cụ thể.

Một cột nullable đơn lẻ không thể biểu diễn cả “không thay đổi” và “xóa thành NULL” nếu không có thêm trạng thái. Hãy dùng cờ cập nhật, staging table hoặc câu lệnh UPDATE riêng khi cần semantics rõ ràng.

## 7. Nhiều hàng trong một câu INSERT

ON DUPLICATE KEY UPDATE hoạt động với INSERT nhiều hàng:

~~~sql
INSERT INTO inventory (
    product_id,
    quantity,
    updated_at
)
VALUES
    (10, 5, NOW(6)),
    (11, 3, NOW(6)),
    (10, 2, NOW(6))
AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity,
    updated_at = incoming.updated_at;
~~~

MySQL xử lý từng hàng trong danh sách:
- Nếu product_id chưa tồn tại, hàng được thêm.
- Nếu product_id đã tồn tại, hàng tương ứng được cập nhật.
- Các hàng sau trong cùng câu lệnh có thể tiếp tục gặp hàng vừa được thêm hoặc cập nhật trước đó.

Trong ví dụ, nếu product_id 10 chưa tồn tại, hàng đầu tạo quantity 5; hàng thứ ba sau đó trùng khóa và cộng thêm 2, kết quả là 7. Nếu product_id 10 đã có quantity 4, hai hàng xung đột lần lượt cộng 5 và 2, kết quả là 11.

### 7.1. Một câu lệnh nhiều hàng vẫn có thể thất bại

Giả sử UPDATE của một hàng làm vi phạm unique key khác, câu lệnh có thể lỗi. Với InnoDB và một INSERT nhiều hàng thông thường, lỗi constraint thường làm statement bị rollback; không giả định các hàng trước đã được ghi thành công.

Nếu thêm IGNORE:

~~~sql
INSERT IGNORE INTO ...
VALUES (...)
ON DUPLICATE KEY UPDATE ...;
~~~

một số lỗi duplicate phát sinh trong nhánh UPDATE có thể được chuyển thành warning và MySQL tiếp tục xử lý các hàng sau. Điều này thay đổi semantics lỗi và có thể tạo kết quả một phần theo quy tắc IGNORE. Chỉ dùng IGNORE khi đã xác định rõ cách ứng dụng kiểm tra warning và chấp nhận việc bỏ qua lỗi.

## 8. Số hàng bị ảnh hưởng và cách kiểm tra kết quả

Với mỗi hàng được xử lý bởi INSERT ... ON DUPLICATE KEY UPDATE, quy tắc affected rows thông thường là:

| Trường hợp | Số hàng bị ảnh hưởng |
|---|---:|
| Hàng mới được INSERT | 1 |
| Hàng cũ được UPDATE và giá trị thực sự thay đổi | 2 |
| Hàng cũ được UPDATE nhưng giá trị không đổi | 0 |

Nếu client kết nối bật cờ CLIENT_FOUND_ROWS, trường hợp UPDATE nhưng không thay đổi có thể được báo là 1 thay vì 0.

Với INSERT nhiều hàng, số affected rows là tổng theo từng hàng được xử lý. Vì vậy, không nên hiểu affected rows đơn giản là số bản ghi mới tạo.

### 8.1. Không dùng affected rows như bằng chứng duy nhất về nhánh nghiệp vụ

Affected rows chịu ảnh hưởng bởi:
- Hàng được thêm hay cập nhật.
- Giá trị có thực sự thay đổi hay không.
- Cờ CLIENT_FOUND_ROWS của client.
- Số hàng trong câu lệnh nhiều hàng.
- Cách driver JDBC diễn giải update count.

Nếu ứng dụng cần biết bản ghi đã tồn tại hay mới được tạo, hãy thiết kế cơ chế trả trạng thái rõ ràng hoặc đọc lại dữ liệu theo khóa sau thao tác. Không suy luận trạng thái nghiệp vụ chỉ từ một con số affected rows nếu không kiểm soát cấu hình client.

## 9. AUTO_INCREMENT và LAST_INSERT_ID()

Nếu bảng có AUTO_INCREMENT, thao tác upsert có thể ảnh hưởng tới bộ đếm AUTO_INCREMENT ngay cả khi đi vào nhánh UPDATE. Vì vậy, không giả định các giá trị ID tăng liên tục hoặc mỗi giá trị đã cấp tương ứng một hàng INSERT mới.

Ví dụ:

~~~sql
CREATE TABLE device_registry (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_key VARCHAR(100) NOT NULL,
    device_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_device_key (device_key)
) ENGINE = InnoDB;
~~~

Upsert:

~~~sql
INSERT INTO device_registry (device_key, device_name)
VALUES ('DEVICE-001', 'Thiết bị phòng họp')
ON DUPLICATE KEY UPDATE
    device_name = 'Thiết bị phòng họp';
~~~

Nếu device_key đã tồn tại, hàng hiện tại được cập nhật; ID của hàng đó không đổi. Tuy nhiên, bộ đếm AUTO_INCREMENT có thể đã cấp hoặc tiêu thụ một giá trị trong quá trình thử INSERT. Khoảng trống trong dãy ID là hành vi bình thường, không phải lỗi dữ liệu.

MySQL hỗ trợ LAST_INSERT_ID() với INSERT ... ON DUPLICATE KEY UPDATE. Khi bảng có AUTO_INCREMENT và câu lệnh INSERT hoặc UPDATE hàng, LAST_INSERT_ID() có thể trả giá trị AUTO_INCREMENT liên quan tới hàng đó. Nếu cần dựa vào hành vi này trong ứng dụng, hãy kiểm thử với phiên bản server và driver đang sử dụng, đặc biệt với lệnh nhiều hàng.

Một kỹ thuật thường gặp là:

~~~sql
INSERT INTO device_registry (device_key, device_name)
VALUES ('DEVICE-001', 'Thiết bị phòng họp')
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id),
    device_name = 'Thiết bị phòng họp';

SELECT LAST_INSERT_ID();
~~~

Phép gán id = LAST_INSERT_ID(id) giúp đặt giá trị LAST_INSERT_ID của connection thành ID của hàng được cập nhật, nhờ đó ứng dụng có thể lấy ID hiện có sau upsert. Hãy bảo đảm connection không bị trả về pool hoặc dùng đồng thời cho câu lệnh khác giữa hai thao tác.

## 10. INSERT ... ON DUPLICATE KEY UPDATE so với REPLACE

REPLACE cũng có hành vi xử lý khi gặp duplicate key, nhưng semantics khác đáng kể.

| Tiêu chí | INSERT ... ON DUPLICATE KEY UPDATE | REPLACE |
|---|---|---|
| Khi trùng khóa | UPDATE hàng hiện có | Xóa hàng xung đột rồi INSERT hàng mới |
| Giữ các cột không được cập nhật | Có, nếu không gán lại | Có thể mất giá trị cũ và dùng DEFAULT |
| AUTO_INCREMENT | Hàng cũ thường giữ ID khi UPDATE | Có thể tạo ID mới |
| Trigger/foreign key | Kích hoạt hành vi INSERT và UPDATE tương ứng | Có hành vi DELETE rồi INSERT |
| Rủi ro cascade | Theo UPDATE | DELETE có thể kích hoạt ON DELETE |
| Mục tiêu | Cập nhật hàng hiện có | Thay thế hàng bằng hàng mới |

Không dùng REPLACE như một cách viết ngắn thay cho upsert nếu muốn giữ nguyên hàng hiện tại. Vì REPLACE có thể xóa rồi chèn lại, nó có thể kích hoạt cascade delete, thay đổi AUTO_INCREMENT và làm mất các cột không được cung cấp.

## 11. Tác động tới trigger, constraint và khóa ngoại

ON DUPLICATE KEY UPDATE vẫn phải tuân thủ các ràng buộc của bảng:
- NOT NULL.
- CHECK constraint được thực thi.
- FOREIGN KEY.
- Các UNIQUE index còn lại.
- Kiểu dữ liệu và quy tắc chuyển đổi.

Nếu nhánh UPDATE tạo ra giá trị vi phạm một constraint, câu lệnh có thể thất bại.

Trigger cũng cần được kiểm tra. Với mỗi hàng được xử lý, BEFORE INSERT chạy trước; nếu không có duplicate và hàng được thêm, nhánh INSERT hoàn tất với AFTER INSERT. Nếu phát hiện duplicate và chuyển sang cập nhật, MySQL chạy BEFORE UPDATE và AFTER UPDATE cho hàng được cập nhật. Vì vậy, một upsert có thể đi qua trigger INSERT trước rồi đến trigger UPDATE tùy kết quả kiểm tra khóa. Nếu trigger ghi audit, cập nhật timestamp hoặc phát sinh tác dụng phụ, hãy kiểm thử cả hai đường đi trên môi trường thử nghiệm.

## 12. Tính nguyên tử, đồng thời và idempotency

### 12.1. Vì sao upsert hữu ích khi có ghi đồng thời?

Mẫu xử lý thủ công thường gặp:

~~~sql
SELECT id
FROM customer_sync
WHERE customer_id = 101;

-- Nếu không có hàng thì INSERT.
-- Nếu có hàng thì UPDATE.
~~~

Giữa SELECT và INSERT, một transaction khác có thể thêm cùng customer_id. Khi đó cả hai tiến trình đều nghĩ rằng hàng chưa tồn tại và cùng INSERT; một tiến trình sẽ gặp duplicate key.

Với InnoDB, một câu INSERT ... ON DUPLICATE KEY UPDATE kết hợp unique constraint xử lý tình huống xung đột trong một thao tác ghi. Nó thường phù hợp hơn cho trường hợp “ghi nếu chưa có, nếu có thì cập nhật”.

Tuy nhiên, atomic statement không có nghĩa là không thể gặp deadlock, lock wait timeout hoặc lỗi do nhiều unique key. Ứng dụng vẫn cần xử lý lỗi transaction và retry theo chính sách phù hợp.

### 12.2. Atomic không đồng nghĩa idempotent

Một thao tác idempotent là thao tác có thể được thực hiện lặp lại mà trạng thái cuối vẫn như khi thực hiện một lần.

Ví dụ ghi đè:

~~~sql
ON DUPLICATE KEY UPDATE
    display_name = incoming.display_name
~~~

Nếu gửi lại cùng dữ liệu, kết quả cuối thường giống nhau. Đây là dạng dễ làm idempotent hơn.

Ngược lại, phép cộng dồn:

~~~sql
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity
~~~

Nếu ứng dụng gửi lại cùng yêu cầu do timeout hoặc retry, quantity sẽ được cộng hai lần. Upsert bảo đảm xử lý xung đột khóa, nhưng không tự chống xử lý lặp sự kiện.

### 12.3. Dùng event ID để chống ghi nhận lặp

Nếu mỗi lần nhập kho là một sự kiện riêng, hãy lưu event_id duy nhất:

~~~sql
CREATE TABLE inventory_event (
    event_id BINARY(16) NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity_delta INT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_inventory_event_product (product_id)
) ENGINE = InnoDB;
~~~

Trong một transaction:
1. INSERT event với event_id.
2. Chỉ khi event mới được ghi thành công, cập nhật inventory.
3. Nếu event_id đã tồn tại, không cộng lại số lượng.
4. Commit cả hai thay đổi cùng nhau.

Ví dụ khung xử lý:

~~~sql
START TRANSACTION;

INSERT INTO inventory_event
    (event_id, product_id, quantity_delta, created_at)
VALUES
    (?, ?, ?, NOW(6));

UPDATE inventory
SET quantity = quantity + ?
WHERE product_id = ?;

COMMIT;
~~~

Nếu INSERT event bị duplicate, ứng dụng nhận lỗi và xử lý như sự kiện đã được tiếp nhận trước đó; không chạy UPDATE cộng dồn lần nữa. Có thể dùng một mẫu upsert riêng để ghi trạng thái sự kiện, nhưng phải bảo đảm nhánh duplicate không lặp tác dụng phụ.

Cần bảo đảm transaction rollback nếu UPDATE inventory thất bại để event không bị đánh dấu đã xử lý trong khi tồn kho chưa thay đổi.

### 12.4. Deadlock và retry

Khi nhiều transaction upsert nhiều khóa theo thứ tự khác nhau, InnoDB có thể phát hiện deadlock và hủy một transaction. Ứng dụng nên:
- Bắt lỗi deadlock (thường MySQL error 1213) và lock wait timeout theo chính sách.
- Rollback transaction bị lỗi.
- Retry toàn bộ transaction với giới hạn số lần và backoff.
- Giữ thứ tự truy cập khóa nhất quán nếu có thể.
- Không retry mù quáng các lỗi dữ liệu như duplicate ở unique key không mong muốn.

Nếu thao tác có tác dụng phụ bên ngoài database (gửi email, gọi API), không thực hiện lặp lại tác dụng phụ chỉ vì retry transaction. Dùng outbox hoặc cơ chế phối hợp phù hợp.

## 13. Upsert với điều kiện và biểu thức

Nhánh UPDATE có thể dùng IF(), CASE, GREATEST(), LEAST() hoặc các biểu thức khác.

### 13.1. Chỉ cập nhật khi dữ liệu mới hơn

~~~sql
INSERT INTO device_state (
    device_key,
    state_value,
    observed_at
)
VALUES (
    'DEVICE-001',
    'ONLINE',
    '2025-04-01 10:00:00'
) AS incoming
ON DUPLICATE KEY UPDATE
    state_value = IF(
        incoming.observed_at > device_state.observed_at,
        incoming.state_value,
        device_state.state_value
    ),
    observed_at = GREATEST(
        device_state.observed_at,
        incoming.observed_at
    );
~~~

Mục tiêu là không để sự kiện cũ ghi đè trạng thái mới. Khi viết nhiều assignment phụ thuộc cùng một cột, cần chú ý thứ tự đánh giá assignment và dùng biểu thức cẩn thận. Có thể dùng một câu lệnh UPDATE riêng trong transaction nếu cần logic nhiều bước phức tạp.

### 13.2. Tăng bộ đếm

~~~sql
INSERT INTO page_view_counter (page_id, view_count)
VALUES (100, 1) AS incoming
ON DUPLICATE KEY UPDATE
    view_count = page_view_counter.view_count + incoming.view_count;
~~~

Đây là phép tăng bộ đếm nguyên tử ở cấp hàng. Nhưng nếu một request bị retry, số đếm có thể tăng lặp. Nếu cần đếm chính xác theo request, hãy lưu request/event ID duy nhất để khử trùng.

### 13.3. Không cập nhật khi giá trị giống nhau

Có thể dùng điều kiện để giữ giá trị cũ nếu không có thay đổi:

~~~sql
INSERT INTO customer_sync
    (customer_id, display_name, updated_at)
VALUES
    (101, 'Nguyễn An', NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    updated_at = IF(
        customer_sync.display_name <> incoming.display_name,
        incoming.updated_at,
        customer_sync.updated_at
    ),
    display_name = incoming.display_name;
~~~

Với cột nullable, phép so sánh <> có thể cho UNKNOWN. Nếu NULL cũng cần được so sánh an toàn, dùng toán tử NULL-safe <=> để xác định khác nhau:

~~~sql
NOT (customer_sync.display_name <=> incoming.display_name)
~~~

Toán tử <=> trả TRUE khi cả hai vế đều NULL, FALSE khi chỉ một vế NULL hoặc giá trị khác nhau, và TRUE khi hai giá trị bằng nhau theo quy tắc so sánh áp dụng.

## 14. Dùng INSERT ... ON DUPLICATE KEY UPDATE với JDBC

PreparedStatement cho phép bind giá trị đầu vào và giữ câu lệnh tách biệt khỏi dữ liệu.

Ví dụ:

~~~java
String sql = """
    INSERT INTO customer_sync
        (customer_id, email, display_name, source_version, updated_at)
    VALUES (?, ?, ?, ?, NOW(6)) AS incoming
    ON DUPLICATE KEY UPDATE
        email = incoming.email,
        display_name = incoming.display_name,
        source_version = incoming.source_version,
        updated_at = incoming.updated_at
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, email);
    ps.setString(3, displayName);
    ps.setLong(4, sourceVersion);

    int affectedRows = ps.executeUpdate();
}
~~~

Các placeholder chỉ đại diện cho giá trị. Không thể dùng placeholder để bind tên bảng, tên cột hoặc từ khóa SQL. Nếu tên bảng phải thay đổi theo tenant hoặc loại nguồn, hãy chọn từ whitelist do ứng dụng định nghĩa.

### 14.1. Lấy ID sau upsert

Nếu dùng kỹ thuật LAST_INSERT_ID(id), có thể đọc trên cùng connection:

~~~java
try (PreparedStatement upsert = connection.prepareStatement(sql)) {
    // Bind tham số và thực thi.
    upsert.executeUpdate();
}

try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery("SELECT LAST_INSERT_ID()")) {
    if (rs.next()) {
        long id = rs.getLong(1);
    }
}
~~~

Hai thao tác phải chạy trên cùng physical connection và không bị lệnh khác xen vào. Với connection pool, giữ connection trong cùng phạm vi thao tác. Đừng lấy LAST_INSERT_ID từ connection khác.

### 14.2. Phiên bản hỗ trợ row alias

Cú pháp incoming row alias dùng trong ví dụ yêu cầu MySQL 8.0.19 trở lên. Nếu ứng dụng kết nối MySQL 5.7, dùng cú pháp VALUES(column) cũ. Từ MySQL 8.0.20, VALUES(column) trong ON DUPLICATE KEY UPDATE bị deprecated; nên chuyển dần sang row alias khi nâng cấp.

Kiểm tra server:

~~~sql
SELECT VERSION();
~~~

Hãy kiểm thử cú pháp trên đúng phiên bản MySQL và driver đang triển khai, đặc biệt khi dùng MariaDB hoặc dịch vụ tương thích MySQL vì lịch sử hỗ trợ cú pháp có thể khác.

## 15. Khi nào không nên dùng ON DUPLICATE KEY UPDATE?

Không nên dùng trực tiếp khi:

- Bảng có nhiều unique key và một hàng mới có thể xung đột với các hàng nghiệp vụ khác nhau.
- Bạn chỉ muốn xử lý duplicate trên một unique key cụ thể nhưng MySQL có thể kích hoạt từ khóa khác.
- Cần kiểm tra nhiều quy tắc nghiệp vụ trước khi quyết định INSERT hay UPDATE.
- Cần trả về trạng thái tạo mới/cập nhật một cách rõ ràng cho nhiều nhánh.
- Phép cập nhật có tác dụng phụ không idempotent và yêu cầu chống xử lý lặp.
- Cần phân giải xung đột bằng dữ liệu từ nhiều bảng hoặc nguồn bên ngoài.

Trong những trường hợp đó, có thể dùng transaction:
1. Kiểm tra hàng theo khóa nghiệp vụ rõ ràng.
2. Khóa hàng hoặc phạm vi cần thiết bằng SELECT ... FOR UPDATE nếu phù hợp.
3. Quyết định INSERT hay UPDATE.
4. Xử lý duplicate race bằng unique constraint và bắt lỗi.
5. Commit hoặc rollback toàn bộ.

SELECT ... FOR UPDATE không khóa một hàng chưa tồn tại theo cách đơn giản trong mọi isolation level và access path. Cần hiểu InnoDB locking, gap/next-key locks và mức cô lập đang dùng. Unique constraint vẫn là hàng rào cuối cùng để bảo vệ tính duy nhất.

## 16. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ chỉ PRIMARY KEY kích hoạt UPDATE | UNIQUE index cũng kích hoạt | Liệt kê tất cả unique key của bảng |
| Nghĩ có thể chỉ định conflict target | MySQL không có cú pháp target riêng | Thiết kế khóa và giải quyết xung đột rõ ràng |
| Cập nhật nhầm hàng theo email | Email trùng hàng khác với primary key đầu vào | Kiểm tra mọi unique key trước upsert |
| Nhiều NULL không kích hoạt upsert | UNIQUE cho phép nhiều NULL | Dùng khóa NOT NULL nếu cần định danh |
| VALUES(column) có cảnh báo deprecated | Cú pháp cũ từ MySQL 8.0.20 | Dùng row alias từ 8.0.19+ |
| Ghi đè dữ liệu bằng NULL | Hàng mới có NULL và UPDATE gán trực tiếp | Xác định semantics NULL, dùng COALESCE hoặc cờ cập nhật |
| Bộ đếm tăng hai lần sau retry | Upsert cộng dồn không idempotent | Dùng event/request ID duy nhất |
| Affected rows = 2 bị hiểu là hai hàng | UPDATE có changed row count là 2 | Hiểu quy tắc 1/2/0 và CLIENT_FOUND_ROWS |
| AUTO_INCREMENT có khoảng trống | Giá trị có thể tiêu thụ khi gặp duplicate | Không dùng ID liên tục làm quy tắc nghiệp vụ |
| Câu lệnh nhiều hàng thất bại | Một hàng UPDATE vi phạm unique/check/FK | Kiểm tra dữ liệu trước và xử lý transaction |
| IGNORE che lỗi | Duplicate update error có thể thành warning | Chỉ dùng khi xử lý warning có chủ đích |
| Upsert vẫn deadlock | Nhiều transaction khóa theo thứ tự khác nhau | Retry transaction có giới hạn, sắp thứ tự khóa |

## 17. Quy trình thiết kế upsert an toàn

Trước khi đưa câu lệnh vào production:

1. Xác định khóa nghiệp vụ dùng để nhận diện một thực thể.
2. Kiểm tra PRIMARY KEY và toàn bộ UNIQUE index của bảng.
3. Bảo đảm các unique key khác không thể vô tình trỏ tới thực thể khác.
4. Xác định cột khóa có cho phép NULL không; khóa upsert thường nên NOT NULL.
5. Quyết định chính sách khi trùng: ghi đè, cộng dồn, chỉ nhận phiên bản mới hơn hay bỏ qua.
6. Dùng row alias cho giá trị hàng mới trên MySQL 8.0.19+.
7. Tránh VALUES(column) trong MySQL 8.0.20+ vì đã deprecated.
8. Xác định NULL có nghĩa không thay đổi, xóa dữ liệu hay thiếu thông tin.
9. Kiểm tra affected rows, AUTO_INCREMENT và LAST_INSERT_ID nếu ứng dụng dựa vào chúng.
10. Với INSERT nhiều hàng, kiểm tra từng hàng có thể xung đột với unique key nào.
11. Xử lý deadlock, lock timeout và retry.
12. Nếu thao tác cộng dồn hoặc có tác dụng phụ, thiết kế event ID để chống xử lý lặp.
13. Dùng transaction khi cần cập nhật nhiều bảng như một đơn vị.
14. Dùng PreparedStatement và bind giá trị.
15. Kiểm thử trên phiên bản MySQL, engine và driver thực tế.

## 18. Bài tập thực hành

### Bài 1: Upsert theo PRIMARY KEY

Tạo bảng customer_sync. Chèn customer_id 101 lần đầu, sau đó chạy lại với display_name mới. Kiểm tra số hàng và giá trị cuối.

### Bài 2: Upsert theo UNIQUE phụ

Thử INSERT một customer_id mới nhưng dùng email đã tồn tại. Xác định hàng nào bị cập nhật. Giải thích vì sao email UNIQUE cũng kích hoạt nhánh UPDATE.

### Bài 3: Nhiều unique key xung đột

Tạo bảng có primary key, unique email và unique username. Tạo hai hàng khác nhau, sau đó gửi một hàng mới trùng primary key của hàng thứ nhất và email của hàng thứ hai. Quan sát lỗi và giải thích vì sao thiết kế upsert không còn có một hàng đích rõ ràng.

### Bài 4: NULL trong unique key

Tạo bảng có external_code UNIQUE NULL. Chèn nhiều hàng NULL rồi thử upsert với NULL. Xác định vì sao nhánh UPDATE không được kích hoạt chỉ bởi NULL.

### Bài 5: Giá trị hàng mới

Viết một câu upsert dùng alias incoming để ghi đè email và display_name. Chạy trên MySQL 8.0.19+ rồi viết lại bằng VALUES(column) trên môi trường tương thích cũ. Kiểm tra warning deprecation nếu phiên bản hỗ trợ.

### Bài 6: Cộng dồn inventory

Tạo bảng inventory có product_id PRIMARY KEY và quantity. Dùng upsert để cộng số lượng. Gửi cùng một request hai lần và quan sát kết quả. Đề xuất event_id để tránh cộng trùng.

### Bài 7: Affected rows

Chạy ba trường hợp: INSERT mới, UPDATE thay đổi dữ liệu và UPDATE không đổi dữ liệu. Ghi nhận affected rows từ SQL client/JDBC. Nếu có thể, thử với CLIENT_FOUND_ROWS.

### Bài 8: LAST_INSERT_ID

Tạo bảng AUTO_INCREMENT có unique device_key. Thử kỹ thuật id = LAST_INSERT_ID(id) trong nhánh UPDATE và lấy LAST_INSERT_ID() trên cùng connection.

### Bài 9: Đồng thời

Dùng hai connection gửi upsert cùng một khóa gần như đồng thời. Xác nhận unique constraint bảo đảm không tạo hai hàng trùng khóa. Mở rộng với transaction cập nhật nhiều bảng và quan sát deadlock/retry nếu có.

### Bài 10: JDBC

Viết PreparedStatement cho upsert nhiều cột. Bind giá trị đúng kiểu, kiểm tra update count và xử lý duplicate key ngoài ý muốn từ unique index phụ.

## 19. Checklist trước khi triển khai

- [ ] Đã xác định khóa nghiệp vụ dùng để upsert.
- [ ] Đã kiểm tra tất cả PRIMARY KEY và UNIQUE index.
- [ ] Đã phân tích khả năng các unique key khác nhau trỏ tới hai hàng khác nhau.
- [ ] Khóa upsert có NOT NULL khi nghiệp vụ yêu cầu định danh bắt buộc.
- [ ] Đã hiểu NULL trong unique index không tạo xung đột như giá trị thông thường.
- [ ] Đã quyết định ghi đè, cộng dồn hay cập nhật có điều kiện.
- [ ] Đã dùng alias hàng mới trên phiên bản hỗ trợ.
- [ ] Đã có kế hoạch thay VALUES(column) deprecated.
- [ ] Đã kiểm tra semantics khi đầu vào NULL hoặc bỏ qua một cột.
- [ ] Đã hiểu affected rows và CLIENT_FOUND_ROWS.
- [ ] Đã đánh giá AUTO_INCREMENT và LAST_INSERT_ID.
- [ ] Đã kiểm tra INSERT nhiều hàng và lỗi constraint ở một hàng.
- [ ] Đã hiểu tác động của IGNORE và warning nếu dùng.
- [ ] Đã thiết kế idempotency cho thao tác cộng dồn hoặc có side effect.
- [ ] Đã xử lý deadlock và retry transaction có giới hạn.
- [ ] Đã dùng PreparedStatement trong ứng dụng.
- [ ] Đã kiểm thử trên đúng phiên bản server, storage engine và JDBC driver.

## 20. Kết luận

\`INSERT ... ON DUPLICATE KEY UPDATE\` thực hiện INSERT nếu không có xung đột PRIMARY KEY hoặc UNIQUE key; nếu có, MySQL chuyển sang UPDATE hàng xung đột. Vì bất kỳ unique index nào cũng có thể kích hoạt nhánh cập nhật và MySQL không cho chỉ định conflict target, thiết kế khóa quyết định trực tiếp tính an toàn của upsert.

Hãy dùng một khóa nghiệp vụ rõ ràng, kiểm tra tất cả unique key, hiểu hành vi NULL và xác định chính sách cập nhật. Trên MySQL 8.0.19 trở lên, ưu tiên row alias để tham chiếu giá trị hàng mới; VALUES(column) trong nhánh UPDATE bị deprecated từ 8.0.20. Với ghi đồng thời, upsert giúp xử lý xung đột trong một statement nhưng vẫn cần xử lý deadlock. Với thao tác cộng dồn, atomic không đồng nghĩa idempotent: hãy dùng event ID hoặc request ID để tránh áp dụng một sự kiện nhiều lần.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – INSERT Statement](https://dev.mysql.com/doc/refman/8.4/en/insert.html)
- [MySQL 8.4 Reference Manual – INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL 8.4 Reference Manual – INSERT Syntax and Row Aliases](https://dev.mysql.com/doc/refman/8.4/en/insert.html)
- [MySQL 8.4 Reference Manual – InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [MySQL 8.4 Reference Manual – Information Functions: LAST_INSERT_ID()](https://dev.mysql.com/doc/refman/8.4/en/information-functions.html#function_last-insert-id)
- [MySQL 8.4 Reference Manual – InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [MySQL 8.4 Reference Manual – InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual – Prepared Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-prepared-statements.html)

