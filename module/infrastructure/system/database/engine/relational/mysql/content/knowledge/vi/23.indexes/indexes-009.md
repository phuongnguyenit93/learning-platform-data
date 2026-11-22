# Functional key part và chỉ mục generated column

Một chỉ mục thông thường lưu giá trị của cột để MySQL tìm kiếm, sắp xếp hoặc nối dữ liệu hiệu quả. Nhưng trong nhiều ứng dụng, điều kiện truy vấn lại áp dụng hàm lên cột: tìm email không phân biệt chữ hoa chữ thường, lọc đơn hàng theo ngày được tách từ DATETIME, hoặc tìm một thuộc tính nằm trong JSON.

Nếu chỉ tạo index trên cột gốc, biểu thức trong WHERE có thể khiến MySQL không tận dụng được index đó theo cách mong muốn. MySQL cung cấp hai cách giải quyết:

- **Functional index** (functional key part): tạo index trực tiếp trên biểu thức.
- **Generated column có index**: tạo cột được tính từ biểu thức, sau đó tạo index trên cột đó.

Hai cách này giúp index phản ánh đúng giá trị mà ứng dụng thường truy vấn. Functional index có cú pháp ngắn và không làm lộ thêm cột trong schema; generated column hữu ích khi cần đặt tên, đọc, kiểm tra hoặc tái sử dụng giá trị đã chuẩn hóa.

Bài viết tập trung vào MySQL 8.0.13 trở lên, là phiên bản bổ sung functional key parts. Các ví dụ cũng nêu rõ cách dùng generated column, biểu thức JSON, index ghép, unique index, giới hạn biểu thức và cách xác nhận optimizer thực sự dùng index.

## 1. Vì sao cần index trên biểu thức?

Giả sử bảng người dùng có email:

~~~sql
CREATE TABLE users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (user_id),
    KEY idx_users_email (email)
) ENGINE = InnoDB;
~~~

Index idx_users_email lưu giá trị email gốc. Truy vấn:

~~~sql
SELECT user_id, email
FROM users
WHERE email = 'An@example.com';
~~~

có thể dùng index trên email để tìm giá trị bằng. Nhưng ứng dụng muốn tìm email không phân biệt hoa thường thường viết:

~~~sql
SELECT user_id, email
FROM users
WHERE LOWER(email) = LOWER('An@example.com');
~~~

Ở đây điều kiện áp dụng LOWER() lên cột. Index thông thường trên email không nhất thiết cung cấp thứ tự phù hợp với giá trị LOWER(email), vì vậy optimizer có thể phải tính biểu thức trên nhiều hàng rồi lọc.

Một functional index trên LOWER(email) lưu giá trị biểu thức đã được lập chỉ mục:

~~~sql
CREATE INDEX idx_users_email_lower
ON users ((LOWER(email)));
~~~

Truy vấn có biểu thức tương ứng có thể dùng index này:

~~~sql
SELECT user_id, email
FROM users
WHERE LOWER(email) = LOWER('An@example.com');
~~~

Functional index không làm thay đổi giá trị email được lưu trong bảng. Nó bổ sung một cấu trúc index để tra cứu kết quả của biểu thức.

## 2. Functional key part là gì?

Functional key part là một phần của index được định nghĩa bằng biểu thức thay vì tên cột đơn lẻ. MySQL hỗ trợ functional key parts từ MySQL 8.0.13.

Cú pháp:

~~~sql
CREATE INDEX index_name
ON table_name ((expression));
~~~

Điểm cần chú ý là biểu thức được đặt trong hai cặp ngoặc:

- Ngoặc ngoài xác định danh sách key parts của index.
- Ngoặc trong bao quanh biểu thức của functional key part.

Ví dụ:

~~~sql
CREATE INDEX idx_products_lower_name
ON products ((LOWER(product_name)));
~~~

Trong index ghép, functional key part có thể đứng cùng key part là cột thông thường:

~~~sql
CREATE INDEX idx_orders_customer_day
ON orders (
    customer_id,
    (DATE(created_at))
);
~~~

Index trên sắp xếp trước theo customer_id, sau đó theo biểu thức DATE(created_at) trong từng giá trị customer_id. Nó có thể hỗ trợ truy vấn có điều kiện khớp customer_id và ngày.

MySQL triển khai functional key part bằng một hidden virtual generated column. Cột ẩn này không xuất hiện như một cột thông thường trong kết quả SELECT *, nhưng giá trị biểu thức được lưu trong secondary index để phục vụ tra cứu.

## 3. Ví dụ functional index cho chuỗi

### 3.1. Tìm kiếm không phân biệt hoa thường

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE INDEX idx_customers_email_lower
ON customers ((LOWER(email)));
~~~

Truy vấn:

~~~sql
SELECT customer_id, email, full_name
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

Điều kiện trên cột và biểu thức trong index phải tương thích để optimizer nhận diện. Nếu biểu thức trong truy vấn khác đáng kể với biểu thức đã lập index, MySQL có thể không dùng functional index đó.

### 3.2. Lưu ý collation

LOWER() chuyển ký tự thành dạng chữ thường theo quy tắc charset/collation. Nhưng tìm kiếm không phân biệt hoa thường vốn có thể được xử lý bằng collation không phân biệt chữ hoa chữ thường, chẳng hạn một collation hậu tố _ci.

Trước khi thêm functional index, kiểm tra collation của cột:

~~~sql
SHOW FULL COLUMNS FROM customers;
~~~

Nếu email đã dùng collation phù hợp, điều kiện email = ? có thể đã không phân biệt hoa thường và index thường trên email có thể đủ. Functional index trên LOWER(email) hữu ích khi nghiệp vụ cần chính xác biểu thức chuẩn hóa đó, hoặc cột gốc dùng collation phân biệt hoa thường.

Không giả định LOWER() xử lý mọi quy tắc so sánh ngôn ngữ giống nhau trên mọi collation. Với định danh người dùng, email và dữ liệu đa ngôn ngữ, hãy xác định rõ quy tắc chuẩn hóa và so sánh trước khi áp dụng unique index.

## 4. Functional index cho ngày và số liệu tính toán

### 4.1. Lọc theo ngày lấy từ DATETIME

Giả sử ứng dụng thường truy vấn đơn hàng theo ngày lịch:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
~~~

Nếu truy vấn thường dùng:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE DATE(created_at) = '2026-05-12';
~~~

có thể tạo functional index:

~~~sql
CREATE INDEX idx_orders_created_date
ON orders ((DATE(created_at)));
~~~

Truy vấn có cùng biểu thức DATE(created_at) có thể dùng index trên biểu thức đó.

Tuy nhiên, nếu có thể thay đổi câu SQL, lọc bằng khoảng thời gian thường đơn giản và tận dụng được index thông thường trên created_at:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);

SELECT order_id, customer_id, created_at
FROM orders
WHERE created_at >= '2026-05-12 00:00:00'
  AND created_at <  '2026-05-13 00:00:00';
~~~

Khoảng nửa mở gồm thời điểm đầu ngày và loại trừ thời điểm đầu ngày kế tiếp. Cách viết này giữ nguyên cột ở dạng trần trong điều kiện và thường là lựa chọn tốt khi truy vấn theo một ngày trên cột DATETIME.

Functional index phù hợp khi biểu thức là một phần tự nhiên của mô hình truy vấn hoặc không thể thay đổi câu SQL ở phía ứng dụng.

### 4.2. Index trên biểu thức số học

Ví dụ bảng hàng hóa có giá niêm yết và giá trị quy đổi:

~~~sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    list_price DECIMAL(12, 2) NOT NULL,
    discount_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE INDEX idx_products_net_price
ON products ((list_price - discount_amount));
~~~

Truy vấn:

~~~sql
SELECT product_id, list_price, discount_amount
FROM products
WHERE list_price - discount_amount >= 500000;
~~~

Index lưu kết quả của biểu thức giá sau giảm. Điều này có thể hỗ trợ điều kiện phạm vi trên giá trị tính toán.

Trước khi tạo index, cần xác nhận kiểu dữ liệu, độ chính xác số học và quy tắc làm tròn của biểu thức. Với DECIMAL, hãy giữ độ chính xác phù hợp nghiệp vụ; tránh chuyển sang FLOAT/DOUBLE nếu không chấp nhận sai số dấu phẩy động.

## 5. Functional index trên JSON

JSON thường chứa thuộc tính được truy vấn như một trường dữ liệu:

~~~sql
CREATE TABLE employee_profiles (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    profile JSON NOT NULL,
    PRIMARY KEY (employee_id)
) ENGINE = InnoDB;
~~~

Ví dụ một profile:

~~~json
{
  "name": "Nguyen An",
  "department": "Engineering",
  "level": 3
}
~~~

Ứng dụng tìm nhân viên theo tên:

~~~sql
SELECT employee_id
FROM employee_profiles
WHERE JSON_UNQUOTE(
    JSON_EXTRACT(profile, '$.name')
) = 'Nguyen An';
~~~

Không thể lập chỉ mục trực tiếp một giá trị JSON tùy ý như thể nó là VARCHAR có độ dài cố định. Cần trích xuất scalar và chuyển sang kiểu dữ liệu có thể lập index.

Functional index:

~~~sql
CREATE INDEX idx_employee_profile_name
ON employee_profiles ((
    CAST(
        JSON_UNQUOTE(JSON_EXTRACT(profile, '$.name'))
        AS CHAR(100) CHARACTER SET utf8mb4
    )
));
~~~

Truy vấn nên dùng cùng biểu thức và kiểu kết quả:

~~~sql
SELECT employee_id
FROM employee_profiles
WHERE CAST(
    JSON_UNQUOTE(JSON_EXTRACT(profile, '$.name'))
    AS CHAR(100) CHARACTER SET utf8mb4
) = 'Nguyen An';
~~~

CAST xác định kiểu chuỗi có độ dài hữu hạn để index. Cần lựa chọn độ dài đủ cho dữ liệu và collation phù hợp với quy tắc so sánh. Nếu cần kiểm soát collation, có thể khai báo COLLATE tương ứng trong biểu thức và giữ cùng ngữ nghĩa trong truy vấn.

Không bỏ qua JSON_UNQUOTE: JSON_EXTRACT trả về giá trị JSON; việc chuyển thành chuỗi SQL và kiểu kết quả phải nhất quán với điều kiện tìm kiếm.

## 6. Generated column là gì?

Generated column là cột có giá trị được tính từ một biểu thức dựa trên các cột khác trong cùng hàng. Ứng dụng không gán trực tiếp giá trị cho generated column; MySQL tính giá trị theo biểu thức đã khai báo.

Có hai loại:

- **VIRTUAL**: giá trị được tính khi cần đọc; không lưu giá trị cột trong clustered record.
- **STORED**: giá trị được tính khi ghi và lưu trong hàng; chiếm thêm dung lượng record.

Nếu không ghi rõ, generated column mặc định là VIRTUAL.

Cú pháp:

~~~sql
column_name data_type
    [GENERATED ALWAYS] AS (expression)
    [VIRTUAL | STORED]
~~~

Ví dụ:

~~~sql
CREATE TABLE people (
    person_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    full_name VARCHAR(201)
        GENERATED ALWAYS AS (
            CONCAT(first_name, ' ', last_name)
        ) STORED,
    PRIMARY KEY (person_id)
) ENGINE = InnoDB;
~~~

full_name được tính từ first_name và last_name. Khi một trong hai cột nguồn thay đổi, MySQL tính lại generated value theo quy tắc của generated column.

## 7. Tạo index trên generated column

Generated column có thể được lập index. Cách này hữu ích khi biểu thức cần được đặt tên rõ ràng hoặc cần dùng trong nhiều truy vấn.

Ví dụ chuẩn hóa email:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320)
        GENERATED ALWAYS AS (LOWER(email)) STORED,
    PRIMARY KEY (account_id),
    KEY idx_accounts_normalized_email (normalized_email)
) ENGINE = InnoDB;
~~~

Truy vấn có thể tham chiếu tên cột:

~~~sql
SELECT account_id, email
FROM accounts
WHERE normalized_email = LOWER('An@example.com');
~~~

Hoặc truy vấn dùng biểu thức tương ứng cũng có thể được optimizer nhận diện và thay bằng generated column đã lập index trong các trường hợp phù hợp:

~~~sql
SELECT account_id, email
FROM accounts
WHERE LOWER(email) = LOWER('An@example.com');
~~~

Để code dễ đọc và ít phụ thuộc việc optimizer nhận diện biểu thức, dùng trực tiếp tên generated column là lựa chọn rõ ràng.

### 7.1. Index generated column VIRTUAL

Generated column VIRTUAL không lưu giá trị trong clustered record, nhưng nếu tạo secondary index trên nó, giá trị biểu thức vẫn được lưu trong cấu trúc index:

~~~sql
CREATE TABLE account_lookup (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320)
        GENERATED ALWAYS AS (LOWER(email)) VIRTUAL,
    PRIMARY KEY (account_id),
    KEY idx_account_lookup_email (normalized_email)
) ENGINE = InnoDB;
~~~

Khi INSERT hoặc UPDATE các cột nguồn, InnoDB vẫn phải tính giá trị cần thiết để duy trì secondary index. Vì vậy, VIRTUAL không có nghĩa index trên nó không tốn dung lượng hoặc không có chi phí ghi.

### 7.2. Index generated column STORED

STORED giữ generated value trong clustered record và index phụ nếu có:

~~~sql
CREATE TABLE account_lookup_stored (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320)
        GENERATED ALWAYS AS (LOWER(email)) STORED,
    PRIMARY KEY (account_id),
    KEY idx_account_lookup_stored_email (normalized_email)
) ENGINE = InnoDB;
~~~

STORED phù hợp khi giá trị được đọc thường xuyên và cần dùng như một thuộc tính hiển thị. Đổi lại, nó tăng kích thước hàng và cần ghi lại generated value khi cột nguồn thay đổi.

| Tiêu chí | VIRTUAL | STORED |
|---|---|---|
| Giá trị trong clustered record | Không lưu | Có lưu |
| Tính khi đọc | Tính khi cần, nếu không lấy từ index | Đọc giá trị đã lưu |
| Tính khi ghi | Cần tính để duy trì index nếu có | Tính và lưu khi ghi |
| Index phụ | Có thể tạo index | Có thể tạo index |
| Dung lượng hàng | Không tăng bởi giá trị generated trong clustered record | Tăng theo giá trị generated |
| Trường hợp dùng | Cần index nhưng muốn tránh lưu thêm trong hàng | Cần giá trị tính sẵn trong hàng và đọc thường xuyên |

Khi một generated column VIRTUAL có index, truy vấn có thể đọc giá trị từ secondary index mà không cần tính lại biểu thức cho mọi hàng khớp. Lựa chọn VIRTUAL hay STORED cần dựa vào kiểu truy vấn, kích thước dữ liệu và chi phí ghi.

## 8. Functional index và generated column khác nhau thế nào?

| Tiêu chí | Functional index | Generated column + index |
|---|---|---|
| Cách khai báo | Index trực tiếp trên biểu thức | Khai báo cột biểu thức rồi tạo index |
| Cột hiển thị trong schema | Không, key part dùng hidden virtual generated column | Có |
| Đọc giá trị tính toán trong SELECT | Không tham chiếu cột ẩn như cột thường | Có thể SELECT generated column |
| Tái sử dụng biểu thức | Lặp biểu thức trong truy vấn | Có tên cột để dùng lại |
| Chọn kiểu dữ liệu/collation | Qua CAST/COLLATE trong biểu thức | Khai báo kiểu và collation ở cột |
| Dùng STORED | Không; functional key part dựa trên hidden virtual generated column | Có |
| Phù hợp | Biểu thức chỉ cần phục vụ index | Giá trị tính toán là một phần hữu ích của mô hình dữ liệu |

Functional index:

~~~sql
CREATE INDEX idx_people_full_name
ON people ((CONCAT(first_name, ' ', last_name)));
~~~

Generated column:

~~~sql
ALTER TABLE people
ADD COLUMN full_name VARCHAR(201)
    GENERATED ALWAYS AS (
        CONCAT(first_name, ' ', last_name)
    ) VIRTUAL,
ADD INDEX idx_people_full_name (full_name);
~~~

Nếu chỉ cần tìm theo biểu thức, functional index ngắn gọn hơn. Nếu ứng dụng cần hiển thị, lọc, sắp xếp và tái sử dụng giá trị đó ở nhiều nơi, generated column có tên thường dễ bảo trì hơn.

## 9. Index ghép có functional key part

Functional key part có thể kết hợp với cột thông thường trong composite index.

Ví dụ ứng dụng tìm đơn hàng của một khách hàng theo ngày:

~~~sql
CREATE INDEX idx_orders_customer_order_day
ON orders (
    customer_id,
    (DATE(created_at))
);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE customer_id = 42
  AND DATE(created_at) = '2026-05-12';
~~~

Thứ tự key parts quan trọng. Index bắt đầu bằng customer_id phù hợp khi truy vấn thường có điều kiện bằng trên customer_id. Nếu truy vấn chỉ lọc ngày mà không có customer_id, index ghép này có thể không phải lựa chọn phù hợp do quy tắc leftmost prefix.

Một ví dụ khác:

~~~sql
CREATE INDEX idx_orders_customer_month
ON orders (
    customer_id,
    (YEAR(created_at)),
    (MONTH(created_at))
);
~~~

Có thể hỗ trợ truy vấn có điều kiện khớp khách hàng, năm và tháng theo đúng các biểu thức đã lập chỉ mục. Nhưng nếu lọc theo một khoảng ngày liên tục, index thông thường trên created_at có thể đơn giản và linh hoạt hơn.

Không thêm functional key part chỉ để biến mọi biểu thức trong SQL thành index. Hãy bắt đầu từ truy vấn thực tế và phân bố dữ liệu.

## 10. Unique functional index

Functional key part có thể tham gia unique index. Điều này hữu ích khi muốn bảo đảm giá trị sau chuẩn hóa không trùng.

Ví dụ:

~~~sql
CREATE TABLE login_accounts (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_login_email_lower ((LOWER(email)))
) ENGINE = InnoDB;
~~~

Unique index trên LOWER(email) ngăn hai hàng có giá trị email sau khi chuyển chữ thường bị trùng theo quy tắc so sánh của biểu thức và collation.

Với dữ liệu:

~~~text
An@example.com
~~~

việc thêm:

~~~text
an@EXAMPLE.com
~~~

có thể bị từ chối vì giá trị index đã tồn tại.

Trước khi áp dụng unique functional index lên bảng có sẵn, hãy tìm dữ liệu trùng sau chuẩn hóa:

~~~sql
SELECT
    LOWER(email) AS normalized_email,
    COUNT(*) AS duplicate_count
FROM login_accounts
GROUP BY LOWER(email)
HAVING COUNT(*) > 1;
~~~

Phải xử lý các nhóm trùng trước khi tạo unique index. Nếu không, ALTER TABLE hoặc CREATE UNIQUE INDEX sẽ thất bại.

Unique index cho phép nhiều giá trị NULL theo quy tắc unique index của MySQL. Với email NOT NULL trong ví dụ, không có ngoại lệ NULL; nếu cột cho phép NULL, hãy xác định nghiệp vụ có chấp nhận nhiều NULL hay không.

Lưu ý rằng collation không phân biệt hoa thường có thể đã coi hai email trên là bằng nhau ngay cả khi không dùng LOWER(). Hãy thiết kế một quy tắc chuẩn hóa nhất quán, tránh tạo thêm index không cần thiết hoặc áp dụng hai quy tắc so sánh khác nhau.

## 11. Giới hạn của functional key part và generated column

Functional key part được triển khai dựa trên generated column ẩn nên chịu các giới hạn quan trọng của generated column và index.

### 11.1. Biểu thức phải phù hợp và xác định

Biểu thức index không được phụ thuộc vào giá trị thay đổi theo từng lần gọi hoặc môi trường thực thi. Các biểu thức không xác định như NOW(), RAND() hoặc UUID() không phù hợp để tạo functional index.

Không dùng trong biểu thức:

- Subquery.
- Biến người dùng hoặc tham số thay đổi ngoài hàng.
- Stored function hoặc loadable function không được phép trong generated expression.
- Hàm không xác định (nondeterministic) như NOW() hoặc RAND().

Biểu thức phải được tính từ dữ liệu của hàng và đáp ứng các quy tắc generated column của MySQL. Một số hàm có thể bị giới hạn theo kiểu dữ liệu hoặc ngữ cảnh.

Ví dụ không phù hợp:

~~~sql
-- Không thể tạo index ổn định theo thời gian hiện tại
CREATE INDEX idx_recent_orders
ON orders ((NOW()));
~~~

Nếu cần tìm đơn trong 30 ngày gần đây, hãy dùng điều kiện thời gian trên cột created_at; không lưu một biểu thức phụ thuộc NOW() trong index.

### 11.2. Không dùng prefix length trực tiếp cho functional key part

Functional key part không hỗ trợ khai báo prefix length theo cú pháp column_name(prefix_length) của index cột. Nếu biểu thức trả về chuỗi dài hoặc kiểu TEXT/BLOB, hãy CAST sang kiểu có độ dài hữu hạn phù hợp.

Ví dụ:

~~~sql
CREATE INDEX idx_profile_city
ON employee_profiles ((
    CAST(
        JSON_UNQUOTE(JSON_EXTRACT(profile, '$.city'))
        AS CHAR(80) CHARACTER SET utf8mb4
    )
));
~~~

Độ dài CAST cần đủ cho dữ liệu hợp lệ và phải phù hợp giới hạn index key theo page size, charset và phiên bản MySQL.

### 11.3. Không dùng functional key part làm PRIMARY KEY

Functional key part không được dùng trong PRIMARY KEY. Nếu cần khóa chính dựa trên một giá trị chuẩn hóa, hãy thiết kế cột generated phù hợp và xem xét các giới hạn khóa chính của generated column trong phiên bản MySQL đang dùng. Một unique secondary index trên biểu thức thường là cách trực tiếp hơn để bảo đảm không trùng giá trị chuẩn hóa.

### 11.4. Kiểu dữ liệu và độ dài biểu thức

Index chỉ lưu được các kiểu dữ liệu được phép làm key part. JSON, BLOB hoặc TEXT không thể được index trực tiếp như một giá trị không giới hạn; cần trích xuất hoặc CAST về kiểu scalar có độ dài xác định.

Hãy tính giới hạn theo byte, không chỉ theo số ký tự. Với utf8mb4, một ký tự có thể chiếm tối đa 4 byte. Index ghép cộng độ dài của tất cả key parts, kể cả functional key parts, phải nằm trong giới hạn của InnoDB cho page size và row format tương ứng.

### 11.5. Quy tắc collation và kiểu trả về

Khi dùng biểu thức chuỗi, kết quả phụ thuộc charset và collation của các đối số. Nếu index biểu thức dùng một kiểu/collation nhưng truy vấn chuyển đổi sang kiểu/collation khác, optimizer có thể không khớp biểu thức với functional key part.

Với biểu thức JSON, hãy CAST rõ ràng sang CHAR với độ dài và charset phù hợp. Nếu nghiệp vụ cần quy tắc so sánh cụ thể, khai báo COLLATE một cách nhất quán trong biểu thức index và truy vấn.

## 12. Optimizer nhận diện biểu thức như thế nào?

Để dùng functional index hoặc index trên generated column, optimizer phải nhận diện điều kiện truy vấn tương thích với biểu thức đã lập chỉ mục.

Ví dụ index:

~~~sql
CREATE INDEX idx_amount_plus_tax
ON invoices ((amount + tax));
~~~

Truy vấn có cùng biểu thức:

~~~sql
SELECT invoice_id
FROM invoices
WHERE amount + tax > 1000000;
~~~

có thể dùng index.

Không nên giả định optimizer biến mọi biểu thức toán học tương đương thành cùng một key part. Chẳng hạn biểu thức tax + amount không nhất thiết được nhận diện như amount + tax. Hãy viết biểu thức nhất quán.

Với generated column:

~~~sql
CREATE TABLE invoices (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    amount DECIMAL(12, 2) NOT NULL,
    tax DECIMAL(12, 2) NOT NULL,
    total_amount DECIMAL(13, 2)
        GENERATED ALWAYS AS (amount + tax) STORED,
    PRIMARY KEY (invoice_id),
    KEY idx_invoices_total (total_amount)
) ENGINE = InnoDB;
~~~

Cách rõ ràng nhất:

~~~sql
SELECT invoice_id
FROM invoices
WHERE total_amount > 1000000;
~~~

MySQL cũng có thể thay biểu thức tương ứng trong truy vấn bằng generated column đã index nếu biểu thức và kiểu kết quả khớp. Việc nhận diện này phụ thuộc cách viết biểu thức; dùng tên generated column tránh phải dựa vào việc optimizer so khớp lại biểu thức.

## 13. Kiểm tra index đã được tạo

### 13.1. SHOW CREATE TABLE

~~~sql
SHOW CREATE TABLE customers;
~~~

Lệnh cho biết DDL của bảng, bao gồm functional key part hoặc generated column và index liên quan.

### 13.2. INFORMATION_SCHEMA.STATISTICS

Trên MySQL 8.0.13 trở lên, có thể xem biểu thức của functional key part qua cột EXPRESSION:

~~~sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    EXPRESSION,
    NON_UNIQUE,
    COLLATION,
    SUB_PART
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Với functional key part, EXPRESSION thể hiện biểu thức; COLUMN_NAME có thể là NULL. Các cột metadata có thể khác giữa phiên bản, nên kiểm tra tài liệu đúng phiên bản khi truy vấn trên hệ thống cũ.

### 13.3. INFORMATION_SCHEMA.COLUMNS

Để kiểm tra generated column:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    EXTRA,
    GENERATION_EXPRESSION
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'accounts'
ORDER BY ORDINAL_POSITION;
~~~

EXTRA cho biết thuộc tính generated column như VIRTUAL GENERATED hoặc STORED GENERATED; GENERATION_EXPRESSION thể hiện biểu thức tính toán.

## 14. Xác nhận optimizer dùng index

Tạo index không đồng nghĩa mọi truy vấn tương ứng chắc chắn dùng index. Optimizer cân nhắc chi phí, độ chọn lọc, số hàng, thống kê và các đường truy cập khác.

Dùng EXPLAIN:

~~~sql
EXPLAIN
SELECT customer_id, email
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

Kiểm tra:

- key: index được chọn.
- possible_keys: các index optimizer có thể xem xét.
- type: kiểu truy cập.
- rows: số hàng ước lượng.
- filtered: tỷ lệ hàng dự kiến còn lại sau lọc.
- Extra: thông tin bổ sung về cách thực thi.

Có thể xem kế hoạch chi tiết hơn:

~~~sql
EXPLAIN FORMAT=JSON
SELECT customer_id, email
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

Trên MySQL 8.0.18 trở lên, EXPLAIN ANALYZE thực thi truy vấn và hiển thị số liệu thực tế:

~~~sql
EXPLAIN ANALYZE
SELECT customer_id, email
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

EXPLAIN ANALYZE chạy câu SELECT thật; hãy dùng với truy vấn có chi phí đã được đánh giá và môi trường phù hợp.

Nếu index không được chọn:

1. Kiểm tra biểu thức trong WHERE có khớp với biểu thức index không.
2. Kiểm tra kiểu dữ liệu và collation của hai biểu thức.
3. Kiểm tra độ chọn lọc; nếu phần lớn bảng khớp, full scan có thể rẻ hơn.
4. Kiểm tra thống kê index và cập nhật thống kê khi cần.
5. Kiểm tra index ghép có tuân thủ leftmost prefix.
6. Thử dữ liệu và tham số đại diện production.

Không ép optimizer bằng hint trước khi hiểu lý do index không được chọn.

## 15. Chi phí bảo trì functional index và generated column

Functional index và index trên generated column đều có chi phí:

- Tốn dung lượng cho secondary index.
- INSERT phải tính biểu thức và cập nhật index.
- UPDATE cột nguồn có thể phải tính lại biểu thức và cập nhật index.
- DELETE phải loại bỏ entry tương ứng.
- Thêm hoặc thay đổi index trên bảng lớn có thể tốn I/O, CPU, dung lượng tạm và metadata lock.
- Index bổ sung làm tăng công việc ghi và có thể ảnh hưởng buffer pool.

Generated column STORED còn chiếm dung lượng trong clustered record. Generated column VIRTUAL không lưu giá trị trong clustered record nhưng secondary index trên nó vẫn lưu key value.

Với functional index, MySQL dùng hidden virtual generated column để triển khai key part. Không có cột hiển thị không có nghĩa là không có chi phí tính toán hoặc lưu trữ.

Trước khi thêm index, xác định:

- Truy vấn nào thực sự cần biểu thức?
- Truy vấn có đủ thường xuyên và đủ nhạy về độ trễ không?
- Biểu thức có chọn lọc đủ tốt không?
- Chi phí ghi tăng bao nhiêu?
- Index có trùng mục đích với index hiện có không?
- Dung lượng tăng thêm có phù hợp không?

## 16. Thay đổi và gỡ index

Tạo functional index:

~~~sql
CREATE INDEX idx_users_email_lower
ON users ((LOWER(email)));
~~~

Gỡ index:

~~~sql
DROP INDEX idx_users_email_lower
ON users;
~~~

Thêm generated column và index vào bảng hiện có:

~~~sql
ALTER TABLE users
ADD COLUMN normalized_email VARCHAR(320)
    GENERATED ALWAYS AS (LOWER(email)) VIRTUAL,
ADD INDEX idx_users_normalized_email (normalized_email);
~~~

Gỡ index và cột generated:

~~~sql
ALTER TABLE users
DROP INDEX idx_users_normalized_email,
DROP COLUMN normalized_email;
~~~

DDL trên bảng lớn có thể cần xây dựng lại index hoặc bảng và có thể chờ metadata lock. Khả năng online phụ thuộc phiên bản, loại thay đổi và cấu trúc bảng. Hãy thử trên bản sao dữ liệu, xem tài liệu DDL của phiên bản và lên kế hoạch dung lượng/giờ triển khai.

Nếu generated column đang được dùng trong view, index, constraint hoặc câu SQL của ứng dụng, cần xác định các phụ thuộc trước khi gỡ.

## 17. Những lỗi thường gặp

**“Chỉ mục trên cột gốc luôn dùng được khi WHERE gọi hàm trên cột.”** Không. Index trên email không tự động là index trên LOWER(email). Dùng functional index hoặc generated column nếu truy vấn cần biểu thức đó.

**“Functional index viết một cặp ngoặc.”** Không. Functional key part cần ngoặc bao biểu thức bên trong danh sách key parts, ví dụ ((LOWER(email))).

**“Functional index là một cột hiển thị.”** Không. MySQL triển khai nó bằng hidden virtual generated column; ứng dụng không truy vấn cột ẩn như cột thường.

**“VIRTUAL generated column không tốn dung lượng khi có index.”** Không. Giá trị được lưu trong secondary index; index vẫn chiếm dung lượng và cần bảo trì khi ghi.

**“STORED luôn nhanh hơn VIRTUAL.”** Không. STORED dùng thêm dung lượng hàng; VIRTUAL có thể tiết kiệm clustered record và vẫn được index. Chọn theo workload.

**“Có thể index trực tiếp JSON hoặc TEXT không giới hạn.”** Không. Hãy trích xuất scalar và CAST về kiểu có độ dài phù hợp.

**“Mọi biểu thức tương đương đều khớp functional index.”** Không. Cách viết biểu thức, kiểu dữ liệu và collation phải tương thích; đừng dựa vào việc optimizer biến đổi đại số tùy ý.

**“NOW() là biểu thức tốt để lập index.”** Không. Giá trị phụ thuộc thời gian hiện tại nên không xác định ổn định cho một hàng. Dùng điều kiện trên cột thời gian gốc.

**“Unique index trên LOWER(email) luôn là quy tắc email đúng.”** Không. Cần thống nhất chuẩn hóa, collation, quy tắc Unicode và dữ liệu trùng trước khi tạo unique index.

**“Tạo index xong là truy vấn chắc chắn dùng nó.”** Không. Kiểm tra EXPLAIN và dữ liệu thực tế; full scan đôi khi có chi phí thấp hơn.

## 18. Quy trình chọn functional index hay generated column

1. Xác định biểu thức xuất hiện thường xuyên trong WHERE, JOIN hoặc ORDER BY.
2. Kiểm tra có thể viết lại truy vấn để dùng index cột gốc hay không. Ví dụ, thay DATE(datetime_col) bằng khoảng thời gian.
3. Nếu biểu thức cần thiết, xác nhận biểu thức được phép và có kiểu kết quả indexable.
4. Chọn functional index nếu chỉ cần index trên biểu thức và không cần hiển thị giá trị.
5. Chọn generated column nếu cần tên cột rõ ràng, cần SELECT giá trị hoặc tái sử dụng trong nhiều truy vấn.
6. Chọn VIRTUAL hoặc STORED dựa trên chi phí lưu trong clustered record và tần suất đọc/ghi.
7. Kiểm tra độ dài key theo byte, charset, collation và page size.
8. Tạo index trên bản sao dữ liệu hoặc môi trường thử nghiệm.
9. Dùng EXPLAIN và EXPLAIN ANALYZE để xác nhận access path và số hàng thực tế.
10. Đo tác động đến INSERT/UPDATE/DELETE và dung lượng trước khi triển khai.

## Kết luận

Functional key part cho phép MySQL lập index trực tiếp trên biểu thức, phù hợp khi truy vấn thường xuyên lọc hoặc sắp xếp theo giá trị tính toán. Generated column tạo một cột có tên từ biểu thức và có thể lập index; nó phù hợp khi giá trị tính toán cần được dùng lại hoặc hiển thị trong ứng dụng.

MySQL triển khai functional index bằng hidden virtual generated column. Generated column VIRTUAL không chiếm chỗ trong clustered record nhưng index trên nó vẫn lưu key value; STORED lưu thêm giá trị trong hàng. Cả hai cách đều có chi phí tính toán và bảo trì khi ghi.

Hãy bảo đảm biểu thức, kiểu dữ liệu và collation khớp với truy vấn, đặc biệt khi index JSON hoặc chuỗi. Ưu tiên cách viết có thể dùng index cột gốc nếu đơn giản hơn, sau đó xác nhận bằng EXPLAIN và benchmark trước khi phát hành.
