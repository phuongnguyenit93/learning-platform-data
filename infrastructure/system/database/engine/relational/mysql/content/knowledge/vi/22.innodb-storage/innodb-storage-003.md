# Khóa chính tự khai báo, khóa duy nhất phù hợp và hidden row ID

InnoDB lưu dữ liệu theo **clustered index**: các leaf page của clustered index chứa toàn bộ dữ liệu của hàng và được tổ chức theo khóa của index đó. Khóa nào được dùng làm clustered index ảnh hưởng trực tiếp đến cách InnoDB định vị hàng, kích thước các secondary index và chi phí INSERT/UPDATE.

Quy tắc lựa chọn của InnoDB rất quan trọng:

1. Nếu bảng có `PRIMARY KEY`, InnoDB dùng primary key làm clustered index.
2. Nếu không có primary key, InnoDB chọn unique index đầu tiên mà tất cả cột khóa đều khai báo `NOT NULL`.
3. Nếu không có primary key và cũng không có unique index đủ điều kiện, InnoDB tạo clustered index ẩn trên một row ID nội bộ dài 6 byte, thường được gọi là `GEN_CLUST_INDEX`.

Vì vậy, một bảng không khai báo primary key chưa chắc đã dùng hidden row ID: một unique index phù hợp có thể trở thành clustered index. Ngược lại, một unique index có cột nullable không đủ điều kiện, vì MySQL cho phép nhiều hàng có giá trị `NULL` trong unique index. Bài học này giúp bạn chọn primary key ổn định, hiểu vai trò của unique key và nhận biết khi nào InnoDB phải dùng hidden row ID.

## 1. Clustered index lưu trữ hàng như thế nào?

InnoDB dùng B+ tree cho index. Với clustered index, leaf page chứa dữ liệu đầy đủ của hàng, không chỉ chứa khóa và con trỏ tới một nơi lưu dữ liệu khác. Vì vậy, tìm kiếm theo clustered key dẫn trực tiếp tới trang chứa hàng.

Ví dụ bảng có primary key `id`:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;
```

`PRIMARY KEY (id)` là clustered index. Các hàng được tổ chức theo giá trị `id`; leaf page của clustered index chứa cả `email`, `full_name`, `created_at` và các cột còn lại.

Unique index `uq_customers_email` là secondary index. Nó lưu giá trị email cùng khóa chính để InnoDB có thể tìm hàng tương ứng. Khi truy vấn theo email, InnoDB có thể tìm entry trong secondary index rồi dùng `id` để truy cập clustered index.

### Clustered index không đồng nghĩa thứ tự kết quả SELECT

Dữ liệu được tổ chức theo clustered key, nhưng SQL không cam kết thứ tự hàng nếu câu SELECT không có `ORDER BY`. Không dựa vào thứ tự insert, thứ tự page hay primary key để suy ra thứ tự kết quả. Nếu ứng dụng cần thứ tự xác định, hãy viết `ORDER BY` tường minh.

## 2. Quy tắc chọn clustered index của InnoDB

InnoDB chọn clustered index theo thứ tự sau:

| Ưu tiên | Cấu trúc bảng | Clustered index được dùng |
|---:|---|---|
| 1 | Có khai báo `PRIMARY KEY` | Primary key. |
| 2 | Không có primary key, có một hoặc nhiều unique index với tất cả cột khóa `NOT NULL` | Unique index đủ điều kiện đầu tiên. |
| 3 | Không có primary key và không có unique index đủ điều kiện | Hidden row ID 6 byte do InnoDB tạo. |

Quy tắc này có nghĩa:

- Primary key luôn được ưu tiên, kể cả khi bảng còn có unique index khác.
- Một unique index chỉ là ứng viên thay thế khi mọi cột tham gia index đều `NOT NULL`.
- Nếu có nhiều unique index đủ điều kiện và không có primary key, InnoDB chọn unique index đầu tiên đủ điều kiện.
- Unique index có cột nullable không được dùng làm clustered index thay thế.
- Hidden row ID là phương án cuối khi không có khóa duy nhất phù hợp.

## 3. Primary key tự khai báo luôn được ưu tiên

Khi bảng có primary key, InnoDB dùng nó làm clustered index. Các unique index còn lại là secondary index, bất kể unique index đó được tạo trước hay sau primary key.

Ví dụ:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE=InnoDB;
```

Trong bảng này:

- `product_id` là clustered key.
- `sku` được bảo vệ bởi unique secondary index.
- InnoDB dùng `product_id` làm row locator trong secondary index `uq_products_sku`.

Ngay cả khi `sku` là mã nghiệp vụ ổn định và unique, primary key đã khai báo vẫn là clustered key. Unique constraint trên `sku` vẫn có giá trị độc lập: nó ngăn hai sản phẩm có cùng SKU.

### Primary key phải duy nhất và không NULL

MySQL yêu cầu các cột của primary key không được NULL. Với primary key ghép, mọi thành phần của khóa đều không NULL. Primary key cũng là unique constraint duy nhất có tên đặc biệt `PRIMARY`; một bảng chỉ có một primary key, nhưng có thể có nhiều unique index.

Không nhầm `PRIMARY KEY` với `UNIQUE KEY`: cả hai đều đảm bảo tính duy nhất, nhưng primary key còn được InnoDB ưu tiên làm clustered index và không cho phép NULL.

## 4. Khi không có primary key, unique index nào được chọn?

Nếu bảng không khai báo primary key, InnoDB tìm unique index mà tất cả cột khóa đều `NOT NULL`. Unique index đó có thể trở thành clustered index.

Ví dụ:

```sql
CREATE TABLE country_codes (
    country_code CHAR(2) NOT NULL,
    country_name VARCHAR(100) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    UNIQUE KEY uq_country_codes_code (country_code)
) ENGINE=InnoDB;
```

Bảng không có `PRIMARY KEY`, nhưng `uq_country_codes_code` là unique index và `country_code` là `NOT NULL`. InnoDB có thể dùng unique index này làm clustered index. Không cần hidden row ID trong trường hợp này.

Ví dụ khóa ghép:

```sql
CREATE TABLE tenant_external_objects (
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_id VARCHAR(80) NOT NULL,
    object_type VARCHAR(30) NOT NULL,
    payload JSON NOT NULL,
    UNIQUE KEY uq_tenant_external (tenant_id, external_id)
) ENGINE=InnoDB;
```

Không có primary key riêng, nhưng cả `tenant_id` và `external_id` đều `NOT NULL`; unique index ghép là ứng viên clustered index. Tính duy nhất được xét trên cả cặp `(tenant_id, external_id)`, không phải từng cột riêng lẻ.

### Nếu có nhiều unique index đủ điều kiện

Khi không có primary key và có nhiều unique index mà mọi cột đều `NOT NULL`, InnoDB chọn unique index đủ điều kiện đầu tiên. Không nên thiết kế dựa vào thứ tự ngầm này nếu có thể khai báo primary key rõ ràng. Một primary key tự khai báo giúp schema truyền đạt chính xác định danh hàng và tránh phụ thuộc vào lựa chọn thay thế của engine.

## 5. Unique index có cột nullable không đủ điều kiện

MySQL cho phép nhiều hàng có giá trị `NULL` trong unique index. `NULL` không được xem là một giá trị bằng nhau theo quy tắc kiểm tra unique thông thường, nên unique index có cột nullable không bảo đảm mỗi hàng có một khóa duy nhất đầy đủ.

Ví dụ:

```sql
CREATE TABLE imported_contacts (
    email VARCHAR(254) NULL,
    display_name VARCHAR(120) NOT NULL,
    UNIQUE KEY uq_imported_contacts_email (email)
) ENGINE=InnoDB;
```

Có thể chèn nhiều hàng với `email = NULL`:

```sql
INSERT INTO imported_contacts (email, display_name)
VALUES
    (NULL, 'Contact A'),
    (NULL, 'Contact B'),
    ('a@example.test', 'Contact C');
```

Unique index vẫn ngăn hai hàng có cùng email khác NULL, nhưng cho phép nhiều NULL. Vì cột khóa nullable, `uq_imported_contacts_email` không đủ điều kiện làm clustered index thay thế. Nếu bảng không có primary key hoặc unique index đủ điều kiện khác, InnoDB dùng hidden row ID.

Điều tương tự xảy ra với unique index ghép:

```sql
CREATE TABLE tenant_contacts (
    tenant_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NULL,
    display_name VARCHAR(120) NOT NULL,
    UNIQUE KEY uq_tenant_email (tenant_id, email)
) ENGINE=InnoDB;
```

Mặc dù `tenant_id` không NULL, `email` nullable khiến unique index ghép không đủ điều kiện làm clustered index. Có thể tồn tại nhiều hàng trong cùng tenant với email NULL.

Nếu nghiệp vụ bắt buộc email phải có và duy nhất, hãy khai báo `email NOT NULL`. Nếu email thực sự tùy chọn, hãy chọn một primary key riêng hoặc một unique key khác có đầy đủ cột `NOT NULL`.

## 6. Hidden row ID 6 byte là gì?

Khi bảng InnoDB không có primary key và cũng không có unique index đủ điều kiện, engine tự tạo một clustered index ẩn trên cột row ID nội bộ. Index này thường được gọi là `GEN_CLUST_INDEX`.

Đặc điểm của hidden row ID:

- Row ID có độ dài 6 byte.
- InnoDB tự sinh và quản lý giá trị; row ID tăng đơn điệu khi các hàng mới được thêm vào.
- Ứng dụng không khai báo cột này.
- Row ID được dùng làm khóa của hidden clustered index.
- Nó không xuất hiện như một cột SQL mà SELECT có thể đọc hoặc JOIN.
- Ứng dụng không thể dùng hidden row ID làm primary key, foreign key hay khóa API.
- Hidden row ID không phải cột `AUTO_INCREMENT` do người dùng khai báo.

Hidden row ID cho phép InnoDB vẫn có clustered index ngay cả khi schema không cung cấp khóa duy nhất phù hợp. Tuy nhiên, nó không thay thế vai trò của một định danh hàng rõ ràng trong mô hình dữ liệu ứng dụng.

### Hidden row ID không phải giải pháp thiết kế khóa

Nếu một bảng không có primary key hoặc unique key phù hợp:

- Ứng dụng khó tham chiếu một hàng ổn định bằng khóa nghiệp vụ rõ ràng.
- Việc cập nhật hoặc xóa chính xác một bản ghi trùng lặp trở nên khó khăn.
- Các bảng khác không thể tham chiếu hidden row ID bằng foreign key.
- Công cụ đồng bộ, CDC hoặc quy trình đối soát có thể khó xác định duy nhất từng hàng nếu dữ liệu nguồn không có định danh.
- InnoDB vẫn phải lưu một row ID nội bộ, nhưng secondary index không thể dùng một khóa ứng dụng có ý nghĩa.

Khi thiết kế bảng mới, nên khai báo primary key tường minh. Với bảng cũ không có primary key, hãy đánh giá dữ liệu trùng và chọn khóa phù hợp trước khi thêm constraint.

## 7. Hidden row ID không hiển thị trong truy vấn SQL

Giả sử bảng được tạo như sau:

```sql
CREATE TABLE raw_import_rows (
    source_name VARCHAR(40) NOT NULL,
    source_ref VARCHAR(100) NULL,
    imported_at DATETIME NOT NULL,
    raw_payload JSON NOT NULL,
    KEY idx_raw_import_source (source_name)
) ENGINE=InnoDB;
```

Bảng không có primary key. Unique index duy nhất cũng không có; index `idx_raw_import_source` là nonunique. InnoDB cần một clustered index và sẽ dùng hidden row ID.

Bạn có thể chạy:

```sql
SHOW CREATE TABLE raw_import_rows;
SHOW INDEX FROM raw_import_rows;

SELECT *
FROM raw_import_rows;
```

Các câu lệnh trên hiển thị schema, các index do người dùng khai báo và dữ liệu SQL-visible. Hidden row ID không được hiển thị như một cột trong `SELECT *` và không phải một index SQL-visible mà ứng dụng có thể truy vấn.

Vì vậy, không thể viết `WHERE DB_ROW_ID = ...` hoặc tạo foreign key tham chiếu `GEN_CLUST_INDEX`. Muốn mỗi hàng có định danh rõ ràng, hãy thêm primary key do schema quản lý.

## 8. Primary key ảnh hưởng đến mọi secondary index

Trong InnoDB, mỗi secondary index entry chứa các cột của secondary key cùng với primary key để định vị hàng trong clustered index. Nếu primary key gồm nhiều cột hoặc có giá trị dài, các cột đó làm tăng kích thước của mọi secondary index.

Nói tổng quát, secondary index cần mang **clustered key** để định vị hàng. Khi bảng có primary key, clustered key chính là primary key. Nếu không có primary key nhưng InnoDB chọn một unique index đủ điều kiện, các cột của unique index đó đóng vai trò clustered key. Nếu engine phải dùng hidden row ID, secondary index dùng row ID nội bộ làm phần định vị.

Ví dụ:

```sql
CREATE TABLE order_items_wide_pk (
    tenant_code VARCHAR(40) NOT NULL,
    order_code VARCHAR(60) NOT NULL,
    line_number INT NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (tenant_code, order_code, line_number),
    KEY idx_order_items_product (product_id)
) ENGINE=InnoDB;
```

Secondary index `idx_order_items_product` cần lưu `product_id` và các cột primary key để định vị hàng. Primary key ghép dài làm entry của secondary index lớn hơn so với một primary key số ngắn.

Khi PK rộng:

- Secondary index tốn nhiều dung lượng hơn.
- Mỗi page chứa được ít entry hơn, có thể tăng số page và I/O.
- Buffer pool phải chứa nhiều dữ liệu index hơn cho cùng lượng hàng.
- INSERT/UPDATE có thể tạo thêm công việc ghi và bảo trì index.
- Các bảng tham chiếu khóa ghép cũng phải mang các thành phần khóa tương ứng.

Đây là lý do một surrogate primary key ngắn thường có lợi cho bảng OLTP có nhiều secondary index. Tuy nhiên, nếu một khóa tự nhiên ngắn, ổn định và phù hợp với workload, dùng nó làm primary key cũng có thể là lựa chọn tốt.

## 9. Chọn natural key hay surrogate key?

**Natural key** là khóa lấy từ dữ liệu nghiệp vụ, ví dụ mã quốc gia, mã sản phẩm hoặc mã định danh do hệ thống nghiệp vụ cấp. **Surrogate key** là khóa kỹ thuật được tạo riêng để định danh hàng, ví dụ `BIGINT AUTO_INCREMENT`.

| Tiêu chí | Natural key | Surrogate key |
|---|---|---|
| Ý nghĩa nghiệp vụ | Có ý nghĩa trực tiếp | Không mang ý nghĩa nghiệp vụ. |
| Độ ổn định | Có thể thay đổi khi quy tắc nghiệp vụ thay đổi | Thường không đổi trong vòng đời hàng. |
| Kích thước | Có thể dài hoặc ghép nhiều cột | Thường ngắn, ví dụ BIGINT. |
| Tính duy nhất | Phải được bảo đảm bằng constraint | Được bảo đảm bởi primary key. |
| Tham chiếu từ bảng khác | Có thể cần khóa ghép hoặc chuỗi dài | Thường đơn giản bằng một cột. |
| Khả năng đọc | Dễ hiểu khi tra cứu nghiệp vụ | Cần JOIN để lấy thông tin nghiệp vụ. |

Một natural key phù hợp làm primary key khi nó:

- Duy nhất trong toàn bộ phạm vi dữ liệu.
- Luôn có giá trị, không NULL.
- Ngắn và ít tốn dung lượng.
- Ổn định, ít hoặc không thay đổi.
- Có quy tắc chuẩn hóa rõ ràng.

Nếu khóa nghiệp vụ dài, có thể thay đổi hoặc phụ thuộc tenant/phạm vi, một surrogate key thường dễ quản lý hơn. Vẫn giữ unique constraint trên natural key để bảo vệ tính duy nhất nghiệp vụ.

## 10. Mẫu thiết kế surrogate primary key và business unique key

Một mẫu phổ biến là dùng primary key số ngắn cho clustered index, đồng thời đặt unique index cho mã nghiệp vụ:

```sql
CREATE TABLE inventory_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    item_code VARCHAR(80) NOT NULL,
    item_name VARCHAR(160) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_inventory_tenant_item (tenant_id, item_code),
    KEY idx_inventory_created_at (created_at)
) ENGINE=InnoDB;
```

Trong thiết kế này:

- `id` là clustered primary key ngắn và ổn định.
- `(tenant_id, item_code)` bảo đảm mã hàng duy nhất trong từng tenant.
- `created_at` có secondary index phục vụ truy vấn theo thời gian.
- Secondary indexes chứa `id` để định vị hàng trong clustered index.

Không nên bỏ unique constraint nghiệp vụ chỉ vì đã có surrogate primary key. Hai loại khóa giải quyết hai vấn đề khác nhau: surrogate key định danh hàng; business unique key ngăn dữ liệu nghiệp vụ trùng.

## 11. Primary key ghép: khi nào nên dùng?

Primary key có thể gồm nhiều cột:

```sql
CREATE TABLE order_lines (
    order_id BIGINT UNSIGNED NOT NULL,
    line_number INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, line_number),
    KEY idx_order_lines_product (product_id)
) ENGINE=InnoDB;
```

Khóa `(order_id, line_number)` thể hiện rõ một dòng hàng được định danh trong phạm vi đơn hàng. Đây là lựa chọn hợp lý nếu dòng hàng không có định danh độc lập và các truy vấn thường truy cập theo `order_id`.

Nhưng primary key ghép có các tác động:

- Mọi thành phần đều là `NOT NULL`.
- Thứ tự cột ảnh hưởng tới leftmost-prefix lookup.
- Secondary index lưu các thành phần primary key.
- Foreign key tham chiếu primary key phải dùng đúng các thành phần và thứ tự phù hợp.
- Nếu khóa ghép dài, mọi secondary index có thể tăng kích thước.

Chọn primary key ghép khi các cột tạo thành định danh tự nhiên, ổn định và có lợi cho truy vấn. Nếu khóa ghép dài hoặc thường xuyên phải mang qua nhiều bảng, cân nhắc surrogate key cộng unique constraint trên cặp nghiệp vụ.

## 12. Unique key nullable và lựa chọn khóa thay thế

Nếu dữ liệu nghiệp vụ có giá trị tùy chọn, không nên ép `NOT NULL` chỉ để làm unique index đủ điều kiện clustered key. Thay vào đó, hãy tách định danh hàng khỏi thuộc tính tùy chọn.

Ví dụ:

```sql
CREATE TABLE external_accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider VARCHAR(40) NOT NULL,
    external_account_id VARCHAR(120) NULL,
    display_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_provider_external_account (
        provider,
        external_account_id
    )
) ENGINE=InnoDB;
```

`id` luôn xác định một hàng. Unique key ghép bảo vệ các external account ID đã có giá trị theo provider; nhiều hàng có `external_account_id = NULL` vẫn được phép theo semantics unique của MySQL. Đây là cách mô hình hóa rõ ràng khi external ID có thể chưa được cấp.

Nếu yêu cầu nghiệp vụ là mỗi provider chỉ có tối đa một hàng chưa có external ID, unique index ghép nullable không tự bảo đảm quy tắc đó. Cần mô hình hóa trạng thái chưa gán theo cách phù hợp hoặc dùng constraint/logic khác; không dựa vào clustered-key selection để giải quyết tính duy nhất nghiệp vụ.

## 13. Tại sao primary key nên ngắn và ổn định?

Vì primary key được đưa vào secondary index, kích thước và độ ổn định của nó ảnh hưởng tới toàn bộ cấu trúc index.

Các tiêu chí thường phù hợp:

- Chọn kiểu dữ liệu đủ chứa số lượng hàng dự kiến nhưng không quá rộng.
- Dùng `BIGINT UNSIGNED` khi cần miền giá trị lớn; `INT UNSIGNED` có thể đủ cho bảng nhỏ hơn.
- Tránh chuỗi dài làm primary key nếu không có lợi ích nghiệp vụ rõ ràng.
- Hạn chế thay đổi primary key sau khi hàng được tạo.
- Chọn thứ tự cột của composite key theo định danh và access pattern.
- Đánh giá ảnh hưởng của khóa tới secondary index, foreign key và dung lượng lưu trữ.

`AUTO_INCREMENT` là cách phổ biến để tạo surrogate key tăng dần, nhưng không phải lựa chọn duy nhất. Có thể dùng ID do ứng dụng tạo hoặc một khóa tự nhiên nếu đáp ứng yêu cầu. Nếu dùng UUID, cân nhắc biểu diễn `BINARY(16)` thay vì chuỗi `CHAR(36)` để giảm kích thước; UUID ngẫu nhiên vẫn có thể làm insert phân tán hơn so với khóa tăng dần.

Không nên dùng timestamp hoặc email làm primary key chỉ vì chúng có vẻ duy nhất ở thời điểm hiện tại. Email có thể đổi; timestamp có thể trùng; chuỗi nghiệp vụ có thể thay đổi quy tắc hoặc phạm vi duy nhất.

## 14. Thay đổi primary key sau khi bảng đã có dữ liệu

Primary key quyết định clustered index. Khi thêm, xóa hoặc thay đổi primary key, InnoDB có thể phải xây dựng lại clustered index và các secondary index liên quan. Đây có thể là thao tác tốn I/O, CPU, dung lượng tạm và ảnh hưởng tới khả năng ghi của bảng.

Ví dụ thay đổi khóa trên bảng thử nghiệm:

```sql
ALTER TABLE imported_contacts
    ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY;
```

Trước khi chạy trên bảng lớn, cần kiểm tra phiên bản MySQL, thuật toán DDL có thể dùng, metadata lock, thời gian rebuild, dung lượng trống, replica lag và cửa sổ triển khai. Không giả định mọi thay đổi primary key đều là instant hoặc không khóa.

Nếu bảng đã có duplicate dữ liệu, việc thêm primary key mới cần bảo đảm giá trị mới được tạo duy nhất. Với bảng lớn, lập kế hoạch migration riêng, kiểm thử trên bản sao dữ liệu và có phương án rollback.

## 15. Kiểm tra primary key và unique indexes trong schema

### Xem định nghĩa bảng

```sql
SHOW CREATE TABLE customers;
SHOW INDEX FROM customers;
```

`SHOW CREATE TABLE` cho biết primary key, unique key, nullability và các cột. `SHOW INDEX` hiển thị các index SQL-visible, gồm `PRIMARY`, unique secondary indexes và nonunique secondary indexes.

### Xem các index trong INFORMATION_SCHEMA

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

`NON_UNIQUE = 0` cho biết index là unique. `SEQ_IN_INDEX` cho biết thứ tự cột trong index; `SUB_PART` cho biết index có dùng prefix hay không.

### Kiểm tra nullability của cột khóa

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_KEY
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
```

Kết hợp metadata index và metadata cột để xác định unique index nào có tất cả thành phần `NOT NULL`. Chỉ nhìn `SHOW INDEX` thấy `Non_unique = 0` chưa đủ kết luận index đó có thể làm clustered index thay thế.

### Liệt kê unique index có tất cả cột NOT NULL

```sql
SELECT
    s.INDEX_NAME,
    COUNT(*) AS key_parts,
    SUM(c.IS_NULLABLE = 'YES') AS nullable_parts
FROM information_schema.statistics AS s
JOIN information_schema.columns AS c
  ON c.TABLE_SCHEMA = s.TABLE_SCHEMA
 AND c.TABLE_NAME = s.TABLE_NAME
 AND c.COLUMN_NAME = s.COLUMN_NAME
WHERE s.TABLE_SCHEMA = DATABASE()
  AND s.TABLE_NAME = 'tenant_external_objects'
  AND s.NON_UNIQUE = 0
  AND s.INDEX_NAME <> 'PRIMARY'
GROUP BY s.INDEX_NAME
HAVING SUM(c.IS_NULLABLE = 'YES') = 0;
```

Truy vấn giúp tìm các unique index ứng viên trên bảng không có primary key. Hãy xem kết quả cùng thứ tự tạo index và DDL thực tế. Nếu có nhiều ứng viên, InnoDB chọn unique index đủ điều kiện đầu tiên; việc khai báo primary key rõ ràng vẫn dễ bảo trì hơn.

## 16. Có thể nhìn thấy hidden row ID bằng cách nào?

Hidden row ID là chi tiết nội bộ của InnoDB, không phải cột được công bố trong schema SQL. Bạn không thể SELECT trực tiếp giá trị row ID hoặc tham chiếu nó từ ứng dụng.

Có thể suy luận bảng đang cần hidden row ID khi:

1. Bảng dùng InnoDB.
2. `SHOW CREATE TABLE` không có primary key.
3. Không có unique index nào mà tất cả cột tham gia đều `NOT NULL`.
4. Các index còn lại là nonunique hoặc unique index có cột nullable.

Ví dụ:

```sql
SHOW CREATE TABLE raw_import_rows;
SHOW INDEX FROM raw_import_rows;
```

Nếu schema khớp các điều kiện trên, InnoDB dùng clustered index ẩn. `SHOW INDEX` không cung cấp một cột `row_id` để ứng dụng truy vấn; `GEN_CLUST_INDEX` là cấu trúc nội bộ, không phải index do người dùng khai báo.

Không nên cố truy cập hidden row ID qua tên nội bộ, giả định thứ tự SELECT phản ánh row ID hoặc dùng vị trí hàng như định danh. Nếu cần tham chiếu từng hàng, hãy tạo khóa tường minh.

## 17. Quy trình chọn khóa khi thiết kế bảng mới

Khi thiết kế một bảng InnoDB, có thể đi theo trình tự:

1. Xác định grain: một hàng đại diện cho thực thể hoặc sự kiện nào?
2. Xác định thuộc tính nghiệp vụ nào phải duy nhất và trong phạm vi nào.
3. Kiểm tra khóa tự nhiên có luôn tồn tại, ổn định và ngắn không.
4. Nếu natural key phù hợp, cân nhắc dùng làm primary key.
5. Nếu natural key dài, nullable, có thể thay đổi hoặc cần nhiều cột, dùng surrogate primary key và giữ unique constraint nghiệp vụ.
6. Nếu dùng composite key, chọn thứ tự cột theo định danh và access pattern.
7. Bảo đảm mọi primary key column là `NOT NULL`.
8. Đánh giá kích thước primary key vì nó được lưu trong secondary indexes.
9. Kiểm tra foreign key và các bảng con tham chiếu khóa.
10. Dùng `SHOW CREATE TABLE`, `SHOW INDEX` và metadata để xác minh cấu trúc sau khi tạo.

Mục tiêu không chỉ là tránh hidden row ID. Mục tiêu là tạo định danh rõ ràng, ổn định, duy nhất theo nghiệp vụ và hiệu quả cho clustered/secondary indexes.

## 18. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ bảng không có primary key thì không có clustered index | Hiểu sai cấu trúc lưu trữ InnoDB | InnoDB dùng unique NOT NULL phù hợp hoặc hidden row ID. |
| Nghĩ mọi unique index đều là ứng viên clustered key | Bỏ qua unique index có cột nullable | Kiểm tra `IS_NULLABLE` của tất cả key parts. |
| Nghĩ unique nullable không cho phép nhiều NULL | Dữ liệu import bị lỗi hoặc schema thiết kế sai | Hiểu semantics unique của MySQL; dùng PK riêng nếu NULL hợp lệ. |
| Nghĩ unique index thay thế primary key trong mọi khía cạnh | Không có định danh tường minh mang tên PRIMARY | Khai báo primary key khi mô hình cần định danh rõ ràng. |
| Chọn primary key chuỗi dài hoặc composite quá rộng | Secondary indexes lớn và tốn buffer pool | Ưu tiên khóa ngắn, ổn định; giữ business unique key riêng khi cần. |
| Dùng email hoặc thuộc tính có thể đổi làm PK | Thay đổi khóa gây cập nhật index và tham chiếu | Dùng surrogate key hoặc natural key ổn định hơn. |
| Dựa vào hidden row ID trong ứng dụng | Không thể truy vấn/tham chiếu ổn định | Tạo primary key SQL-visible. |
| Nghĩ `AUTO_INCREMENT` luôn liên tục không có khoảng trống | Logic ứng dụng phụ thuộc sai vào số ID | Dùng ID để định danh, không dùng làm bộ đếm nghiệp vụ liên tục. |
| Thêm primary key trên bảng lớn mà không lập kế hoạch | Rebuild tốn tài nguyên và ảnh hưởng DDL | Đánh giá online DDL, metadata lock, dung lượng và thời gian trước. |
| Bỏ unique constraint nghiệp vụ sau khi thêm surrogate PK | Dữ liệu nghiệp vụ trùng vẫn được phép | Giữ unique index theo đúng phạm vi nghiệp vụ. |

## 19. Bài tập thực hành

### Bài tập A — Primary key được ưu tiên

1. Tạo bảng `products` có `PRIMARY KEY (product_id)` và `UNIQUE KEY (sku)`.
2. Chạy `SHOW CREATE TABLE` và `SHOW INDEX`.
3. Giải thích vì sao `product_id` là clustered key còn `sku` là secondary index.
4. Thử truy vấn theo SKU và mô tả bước tra cứu secondary-to-clustered.

### Bài tập B — Unique NOT NULL thay thế primary key

1. Tạo bảng `country_codes` không có primary key nhưng có unique key NOT NULL.
2. Tạo bảng có nhiều unique index đủ điều kiện.
3. Xác định unique index đủ điều kiện đầu tiên.
4. Giải thích vì sao InnoDB không cần hidden row ID trong trường hợp đó.

### Bài tập C — Unique nullable và hidden row ID

1. Tạo bảng `imported_contacts` chỉ có unique index trên cột nullable.
2. Chèn nhiều hàng có giá trị NULL ở cột unique.
3. Xác minh các hàng NULL vẫn được chấp nhận.
4. Kiểm tra `SHOW CREATE TABLE` và `SHOW INDEX`.
5. Giải thích vì sao bảng cần hidden row ID nếu không có unique NOT NULL khác.

### Bài tập D — Ảnh hưởng của primary key tới secondary indexes

1. Tạo một bảng với `BIGINT` primary key.
2. Tạo bảng tương đương với composite primary key gồm nhiều cột chuỗi.
3. Tạo cùng một số secondary indexes trên hai bảng.
4. So sánh kích thước key và giải thích vì sao PK được mang vào secondary index entries.
5. Đề xuất lựa chọn phù hợp cho bảng OLTP có nhiều index.

### Bài tập E — Thiết kế khóa cho dữ liệu đa tenant

1. Tạo bảng có `tenant_id` và `external_id`.
2. Thử unique key ghép khi cả hai cột NOT NULL.
3. Đổi `external_id` thành nullable và kiểm tra unique semantics.
4. Thiết kế lại bằng surrogate primary key cùng unique constraint nghiệp vụ.
5. Giải thích lựa chọn clustered key và phạm vi duy nhất trong tenant.

Bạn hoàn thành bài khi có thể xác định clustered index theo ba quy tắc của InnoDB, nhận biết unique index đủ điều kiện, giải thích hidden row ID 6 byte và thiết kế primary key phù hợp với kích thước secondary index cũng như yêu cầu nghiệp vụ.

## 20. Nguyên tắc cần ghi nhớ

- InnoDB lưu toàn bộ hàng ở leaf page của clustered index.
- Primary key tự khai báo luôn là clustered index.
- Nếu không có primary key, InnoDB chọn unique index đầu tiên có tất cả cột khóa `NOT NULL`.
- Unique index có cột nullable không đủ điều kiện thay thế primary key vì MySQL cho phép nhiều NULL.
- Nếu không có primary key hoặc unique index đủ điều kiện, InnoDB tạo hidden clustered index `GEN_CLUST_INDEX` trên row ID nội bộ 6 byte.
- Hidden row ID không phải cột SQL-visible, không thể SELECT, JOIN hoặc dùng làm foreign key.
- Secondary index entries mang primary key columns để định vị hàng; primary key rộng làm mọi secondary index lớn hơn.
- Chọn primary key ngắn, ổn định, duy nhất và không NULL.
- Natural key phù hợp nếu ngắn, ổn định và duy nhất; nếu không, dùng surrogate key cùng unique constraint nghiệp vụ.
- Composite primary key hợp lý khi các thành phần tạo thành định danh tự nhiên, nhưng cần cân nhắc thứ tự và kích thước.
- Thay đổi primary key có thể rebuild clustered index và secondary indexes; phải lập kế hoạch cho bảng lớn.
- Dùng `SHOW CREATE TABLE`, `SHOW INDEX` và `INFORMATION_SCHEMA` để xác minh cấu trúc và nullability.

Khi chọn primary key tường minh hoặc unique key đủ điều kiện, bạn kiểm soát được clustered index mà InnoDB dùng và tránh phụ thuộc vào hidden row ID. Một khóa ngắn, ổn định và phù hợp nghiệp vụ cũng giúp secondary indexes gọn hơn, truy cập hàng hiệu quả hơn và schema dễ bảo trì hơn.
