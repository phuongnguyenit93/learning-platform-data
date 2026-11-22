# Phụ thuộc view, thay đổi schema và kiểm tra định nghĩa

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích quan hệ phụ thuộc giữa view, view khác và các bảng nền.
- Kiểm tra danh sách view, định nghĩa SQL, cột đầu ra, quyền thực thi và metadata của view.
- Nhận diện tác động của `ALTER TABLE`, đổi tên hoặc xóa cột/bảng lên các view đang sử dụng chúng.
- Hiểu vì sao `SELECT *` trong định nghĩa view không tự mở rộng khi bảng nền thêm cột.
- Cập nhật view bằng `CREATE OR REPLACE VIEW` hoặc `ALTER VIEW` theo đúng thứ tự phụ thuộc.
- Lập kế hoạch migration schema có nhiều view phụ thuộc lẫn nhau.
- Kiểm tra view bị lỗi bằng `CHECK TABLE`, `SHOW CREATE VIEW` và `INFORMATION_SCHEMA`.
- Đánh giá `ALGORITHM`, `SQL SECURITY`, `DEFINER` và khả năng cập nhật của view sau thay đổi.
- Hiểu giới hạn khi view tương tác với temporary table.

Các ví dụ hướng tới MySQL 8.0/8.4. Hãy xác nhận cú pháp, quyền và metadata trên đúng phiên bản server trước khi triển khai.

## 1. View phụ thuộc vào những đối tượng nào?

View là một đối tượng schema lưu định nghĩa truy vấn `SELECT`. Khi ứng dụng đọc view, MySQL phân giải định nghĩa đó và truy cập các bảng hoặc view được tham chiếu bên trong.

Ví dụ:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE = InnoDB;

CREATE VIEW v_active_products AS
SELECT product_id, sku, product_name, price
FROM products
WHERE status = 'ACTIVE';
```

`v_active_products` phụ thuộc vào bảng `products` và các cột `product_id`, `sku`, `product_name`, `price`, `status`. Nếu một view khác truy vấn `v_active_products`, view đó lại phụ thuộc vào view này.

### 1.1. Phụ thuộc trực tiếp và phụ thuộc gián tiếp

Có thể hình dung chuỗi:

```text
products
   |
   v
v_active_products
   |
   v
v_active_product_names
   |
   v
v_product_catalog
```

Tạo các view theo chuỗi:

```sql
CREATE VIEW v_active_product_names AS
SELECT product_id, product_name
FROM v_active_products;

CREATE VIEW v_product_catalog AS
SELECT product_id, product_name
FROM v_active_product_names;
```

`v_product_catalog` không tham chiếu trực tiếp `products`, nhưng phụ thuộc gián tiếp vào bảng đó thông qua hai view trung gian. Khi đổi tên hoặc xóa cột trong `products`, cần kiểm tra toàn bộ chuỗi view, không chỉ view đầu tiên.

### 1.2. View không phải bản sao dữ liệu

View thông thường không lưu bản sao kết quả truy vấn như materialized view. MySQL lưu định nghĩa và thực thi nó khi truy vấn. Thay đổi dữ liệu trong bảng nền được phản ánh qua view theo transaction và isolation semantics của truy vấn.

MySQL không cung cấp materialized view tích hợp theo cách tự động lưu và làm mới kết quả. Nếu cần snapshot tổng hợp, cần thiết kế bảng summary hoặc cơ chế materialization riêng.

### 1.3. View là hợp đồng schema với ứng dụng

Ứng dụng có thể dựa vào tên view, tên cột, kiểu dữ liệu, thứ tự cột và ngữ nghĩa lọc. Vì vậy, view nên được quản lý như API database:

- Khai báo danh sách cột rõ ràng.
- Giữ tên và ý nghĩa cột ổn định.
- Tránh thay đổi kiểu dữ liệu hoặc thứ tự cột gây ảnh hưởng client.
- Kiểm tra các view phụ thuộc trước khi đổi schema nền.
- Đưa định nghĩa view vào migration/version control của dự án.

## 2. Khai báo view với danh sách cột tường minh

Nên chọn rõ các cột trong định nghĩa view:

```sql
CREATE VIEW v_active_products (
    product_id,
    product_sku,
    product_name,
    unit_price
) AS
SELECT
    product_id,
    sku,
    product_name,
    price
FROM products
WHERE status = 'ACTIVE';
```

Danh sách sau tên view đặt tên cột đầu ra. Nó giúp tách tên cột mà ứng dụng sử dụng khỏi tên cột vật lý của bảng nền.

### 2.1. Vì sao nên tránh SELECT *?

Ví dụ:

```sql
CREATE VIEW v_products AS
SELECT *
FROM products;
```

MySQL xác định danh sách cột của view tại thời điểm tạo hoặc định nghĩa lại view. Nếu sau đó bảng `products` được thêm cột `category_id`, view hiện tại không tự động mở rộng để trả cột mới.

Điều này có hai hệ quả:

- Ứng dụng có thể không nhìn thấy cột mới dù bảng nền đã có.
- Người bảo trì có thể hiểu nhầm rằng `SELECT *` luôn được đánh giá lại theo schema hiện tại.

Nếu muốn view xuất thêm cột mới, hãy cập nhật định nghĩa bằng `CREATE OR REPLACE VIEW` hoặc `ALTER VIEW` với danh sách cột mới.

### 2.2. Tên cột trùng và biểu thức tính toán

Mỗi cột đầu ra của view cần có tên duy nhất. Khi dùng biểu thức hoặc nhiều bảng có cột cùng tên, hãy đặt alias rõ ràng:

```sql
CREATE VIEW v_order_summary AS
SELECT
    o.order_id,
    o.customer_id,
    COUNT(i.item_id) AS item_count,
    SUM(i.quantity * i.unit_price) AS calculated_total
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.customer_id;
```

Tên alias trở thành một phần giao diện của view. Đổi alias có thể làm hỏng truy vấn của client hoặc view phụ thuộc.

## 3. Kiểm tra danh sách view trong schema

### 3.1. SHOW FULL TABLES

Liệt kê bảng và view:

```sql
SHOW FULL TABLES FROM sales;
```

Cột `Table_type` cho biết đối tượng là `BASE TABLE` hay `VIEW`.

Chỉ lọc view:

```sql
SHOW FULL TABLES FROM sales
WHERE Table_type = 'VIEW';
```

### 3.2. INFORMATION_SCHEMA.VIEWS

`INFORMATION_SCHEMA.VIEWS` cung cấp metadata của view:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    VIEW_DEFINITION,
    CHECK_OPTION,
    IS_UPDATABLE,
    DEFINER,
    SECURITY_TYPE,
    CHARACTER_SET_CLIENT,
    COLLATION_CONNECTION
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'sales'
ORDER BY TABLE_NAME;
```

Các trường thường cần kiểm tra:

| Trường | Ý nghĩa |
|---|---|
| `TABLE_SCHEMA`, `TABLE_NAME` | Schema và tên view |
| `VIEW_DEFINITION` | Phần định nghĩa SELECT được lưu |
| `CHECK_OPTION` | `NONE`, `LOCAL` hoặc `CASCADED` |
| `IS_UPDATABLE` | Cho biết view có được đánh giá là updatable hay không |
| `DEFINER` | Tài khoản định nghĩa view |
| `SECURITY_TYPE` | `DEFINER` hoặc `INVOKER` |
| `CHARACTER_SET_CLIENT` | Character set của client khi tạo view |
| `COLLATION_CONNECTION` | Collation connection khi tạo view |

`VIEW_DEFINITION` có thể không hiển thị đầy đủ nếu tài khoản không có quyền cần thiết. Khi cần xác minh định nghĩa, dùng tài khoản được cấp `SHOW VIEW` phù hợp.

### 3.3. SHOW CREATE VIEW

Đây là cách trực tiếp để xem câu lệnh tạo view:

```sql
SHOW CREATE VIEW sales.v_active_products;
```

Kết quả cho biết định nghĩa `SELECT`, `ALGORITHM`, `DEFINER`, `SQL SECURITY` và `CHECK OPTION` nếu có. Hãy lưu output này trong quy trình migration hoặc đối chiếu với định nghĩa trong source control.

### 3.4. DESCRIBE và SHOW COLUMNS

Kiểm tra schema đầu ra:

```sql
DESCRIBE sales.v_active_products;

SHOW FULL COLUMNS FROM sales.v_active_products;
```

Có thể đối chiếu với metadata cột:

```sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'v_active_products'
ORDER BY ORDINAL_POSITION;
```

Kiểu dữ liệu của cột view được suy ra từ biểu thức SELECT. Thay đổi kiểu cột bảng nền có thể làm kiểu đầu ra của view thay đổi sau khi định nghĩa được cập nhật hoặc được phân giải lại; hãy kiểm tra schema đầu ra thay vì giả định client không bị ảnh hưởng.

## 4. Kiểm tra quan hệ phụ thuộc bằng VIEW_TABLE_USAGE

MySQL cung cấp `INFORMATION_SCHEMA.VIEW_TABLE_USAGE` để xem bảng hoặc view được sử dụng trong định nghĩa view.

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME,
    TABLE_SCHEMA,
    TABLE_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE VIEW_SCHEMA = 'sales'
ORDER BY VIEW_NAME, TABLE_SCHEMA, TABLE_NAME;
```

Kết quả biểu diễn quan hệ sử dụng trực tiếp giữa view và đối tượng được tham chiếu. Đối tượng ở cột `TABLE_NAME` có thể là base table hoặc một view khác.

### 4.1. Tìm view tham chiếu một bảng cụ thể

Ví dụ tìm view tham chiếu `sales.products`:

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'products'
ORDER BY VIEW_SCHEMA, VIEW_NAME;
```

Truy vấn này giúp xác định các view phụ thuộc trực tiếp vào bảng `products`.

### 4.2. Tìm view tham chiếu một view khác

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'v_active_products';
```

Kết quả cho biết các view sử dụng `v_active_products`. Có thể tiếp tục truy vấn để lần theo chuỗi phụ thuộc.

### 4.3. Phụ thuộc gián tiếp cần lần theo nhiều cấp

Nếu `v_catalog` tham chiếu `v_active_product_names`, và view này tham chiếu `v_active_products`, thì truy vấn lọc trực tiếp `products` chỉ tìm được view tham chiếu `products` nếu view đó có quan hệ trực tiếp trong metadata. Để lập đồ thị đầy đủ, cần lần theo các cạnh view-to-view qua nhiều cấp.

Khi số lượng view lớn, xuất danh sách cạnh từ `VIEW_TABLE_USAGE` rồi xây dựng thứ tự triển khai trong công cụ migration hoặc script quản trị. Không chỉ dựa vào tên view hoặc thứ tự alphabet.

### 4.4. Quyền và phạm vi metadata

Khả năng nhìn thấy metadata có thể phụ thuộc quyền của tài khoản. Nếu kết quả thiếu view mà bạn biết tồn tại, kiểm tra quyền `SHOW VIEW` và quyền truy cập schema liên quan trước khi kết luận không có dependency.

## 5. Tác động của thay đổi schema bảng nền

View lưu một định nghĩa phụ thuộc vào tên đối tượng và cột. DDL trên bảng nền có thể làm view không còn hợp lệ hoặc làm thay đổi dữ liệu/kiểu đầu ra mà client nhận được.

### 5.1. Thêm cột mới

Giả sử view hiện tại:

```sql
CREATE VIEW v_product_list AS
SELECT product_id, sku, product_name
FROM products;
```

Sau đó thêm cột:

```sql
ALTER TABLE products
    ADD COLUMN category_id BIGINT UNSIGNED NULL;
```

View vẫn có thể hoạt động vì các cột nó tham chiếu chưa bị thay đổi, nhưng `category_id` không tự xuất hiện trong kết quả view. Muốn công bố cột mới, cần thay đổi định nghĩa view.

### 5.2. Đổi tên cột được view tham chiếu

Giả sử view tham chiếu `sku`. Nếu chạy:

```sql
ALTER TABLE products
    RENAME COLUMN sku TO product_code;
```

định nghĩa view vẫn chứa tên cột cũ và có thể trở thành invalid. Những truy vấn sử dụng view hoặc kiểm tra view có thể báo lỗi tham chiếu cột không hợp lệ.

Trước khi đổi tên, hãy tìm mọi view phụ thuộc, chuẩn bị định nghĩa mới và triển khai theo thứ tự an toàn. Không giả định MySQL tự sửa tất cả view phụ thuộc theo tên cột mới.

### 5.3. Xóa cột được view tham chiếu

```sql
ALTER TABLE products
    DROP COLUMN product_name;
```

Nếu view hoặc view phụ thuộc cần `product_name`, định nghĩa đó không còn hợp lệ. Cần cập nhật hoặc xóa view phụ thuộc trước khi xóa cột, hoặc thực hiện migration theo giai đoạn tương thích.

### 5.4. Thay đổi kiểu dữ liệu

Ví dụ:

```sql
ALTER TABLE products
    MODIFY price DECIMAL(18,4) NOT NULL;
```

View có thể vẫn phân giải được nhưng kiểu đầu ra, độ chính xác, quy tắc chuyển đổi hoặc kết quả biểu thức có thể thay đổi. Client dựa vào kiểu cũ có thể cần cập nhật. Hãy kiểm tra `SHOW CREATE VIEW`, `DESCRIBE view` và kết quả mẫu sau DDL.

### 5.5. Đổi tên hoặc di chuyển bảng

Đổi tên bảng hoặc chuyển bảng sang schema khác có thể làm tên tham chiếu trong định nghĩa view không còn đúng. Hãy coi thao tác này là thay đổi dependency cần migration view tường minh. Kiểm tra `VIEW_TABLE_USAGE`, định nghĩa lưu bằng `SHOW CREATE VIEW` và chạy `CHECK TABLE` sau khi triển khai.

### 5.6. Thêm index hoặc đổi index

Thay đổi index thường không làm view invalid vì định nghĩa view phụ thuộc vào cột và biểu thức, không phụ thuộc vào tên index. Tuy nhiên, execution plan của truy vấn qua view có thể thay đổi. Dùng `EXPLAIN` trên truy vấn view để xác nhận hiệu năng sau thay đổi index hoặc statistics.

## 6. CREATE OR REPLACE VIEW và ALTER VIEW

Khi schema nền thay đổi, cần cập nhật view bằng DDL view.

### 6.1. CREATE OR REPLACE VIEW

`CREATE OR REPLACE VIEW` tạo view nếu chưa tồn tại hoặc thay thế định nghĩa view hiện tại:

```sql
CREATE OR REPLACE VIEW v_product_list AS
SELECT
    product_id,
    product_code,
    product_name,
    category_id
FROM products;
```

Lệnh này hữu ích cho migration có định nghĩa mong muốn rõ ràng. Tuy nhiên, thay đổi danh sách cột, alias hoặc kiểu đầu ra có thể ảnh hưởng client và các view phụ thuộc. Phải kiểm tra downstream dependency trước khi thay thế.

### 6.2. ALTER VIEW

`ALTER VIEW` thay đổi định nghĩa của một view đã tồn tại:

```sql
ALTER VIEW v_product_list AS
SELECT
    product_id,
    product_code,
    product_name,
    category_id
FROM products;
```

`ALTER VIEW` không tạo view mới nếu view chưa tồn tại. Nếu migration cần chạy lặp lại theo kiểu create-or-replace, dùng cú pháp tương ứng và kiểm tra quyền.

### 6.3. Khai báo đầy đủ thuộc tính view

Có thể khai báo rõ algorithm, definer và security:

```sql
CREATE OR REPLACE
    ALGORITHM = UNDEFINED
    DEFINER = CURRENT_USER
    SQL SECURITY INVOKER
VIEW v_product_list (
    product_id,
    product_code,
    product_name,
    category_id
) AS
SELECT
    product_id,
    product_code,
    product_name,
    category_id
FROM products;
```

Trong môi trường triển khai nhiều server, cần kiểm soát `DEFINER` và quyền của tài khoản đó. `CURRENT_USER` lấy tài khoản hiện tại khi thực thi câu lệnh; không sao chép một definer cụ thể từ môi trường phát triển sang production nếu tài khoản đó không tồn tại hoặc không được cấp quyền tương ứng.

### 6.4. Thay đổi view có thể làm hỏng view phụ thuộc

Giả sử `v_active_product_names` tham chiếu `v_active_products`. Nếu thay thế `v_active_products` và bỏ cột `product_name`, view phía trên có thể trở thành invalid.

Triển khai thay đổi theo thứ tự dependency:

1. Cập nhật view gần bảng nền trước.
2. Cập nhật các view tham chiếu view đó.
3. Tiếp tục lên các view cấp cao hơn.
4. Kiểm tra toàn bộ chuỗi và các client.

Khi loại bỏ cột, có thể cần triển khai tương thích theo hai giai đoạn: thêm cột/alias mới trước, chuyển client và view phụ thuộc sang tên mới, sau đó mới xóa cột cũ.

## 7. ALGORITHM của view và tác động thực thi

MySQL hỗ trợ các lựa chọn `ALGORITHM`:

- `MERGE`: cố gắng gộp định nghĩa view vào truy vấn ngoài để optimizer xử lý như một truy vấn kết hợp.
- `TEMPTABLE`: materialize kết quả view vào một bảng tạm nội bộ trước khi xử lý phần còn lại.
- `UNDEFINED`: để MySQL chọn thuật toán phù hợp.

Ví dụ:

```sql
CREATE OR REPLACE ALGORITHM = MERGE VIEW v_active_products AS
SELECT product_id, sku, product_name, price
FROM products
WHERE status = 'ACTIVE';
```

### 7.1. MERGE

Với view có thể merge, điều kiện từ truy vấn bên ngoài có thể được đẩy xuống bảng nền và optimizer có thể chọn index của bảng nền. Điều này thường giúp tránh materialize trung gian.

Không phải view nào cũng merge được. Các cấu trúc như aggregate, `GROUP BY`, `DISTINCT`, `UNION`, một số subquery hoặc biểu thức hạn chế khả năng merge.

### 7.2. TEMPTABLE

`TEMPTABLE` tạo bảng trung gian chứa kết quả view trước khi truy vấn ngoài tiếp tục. Nó có thể hữu ích trong một số tình huống, nhưng tạo chi phí materialization và thường làm view không updatable.

Không nhầm bảng tạm nội bộ dùng để thực thi view với `CREATE TEMPORARY TABLE` do ứng dụng tạo. Chúng có vòng đời và mục đích khác nhau.

### 7.3. UNDEFINED

`UNDEFINED` cho optimizer quyền chọn. Đây thường là lựa chọn mặc định phù hợp nếu không có lý do rõ ràng để ép algorithm. Đọc `SHOW CREATE VIEW` để kiểm tra thuộc tính đang lưu và dùng `EXPLAIN` trên truy vấn thực tế để hiểu kế hoạch.

## 8. SQL SECURITY và DEFINER

View có thể thực thi dưới quyền của người định nghĩa hoặc người gọi.

### 8.1. SQL SECURITY DEFINER

`DEFINER` là mặc định nếu không chỉ định khác. Truy vấn view sử dụng quyền của tài khoản definer để truy cập các đối tượng nền.

Điều này cho phép cấp cho ứng dụng quyền SELECT trên view mà không cần cấp trực tiếp SELECT trên mọi bảng nền. Tuy nhiên, definer phải được quản lý cẩn thận:

- Tài khoản definer cần tồn tại và có quyền cần thiết trên các đối tượng được tham chiếu.
- Quyền của definer phải ở mức tối thiểu cần thiết.
- Không dùng tài khoản DBA/root làm definer cho view ứng dụng thông thường.
- Khi triển khai sang môi trường khác, phải xử lý sự khác nhau về tài khoản và quyền.

### 8.2. SQL SECURITY INVOKER

`INVOKER` dùng quyền của tài khoản đang gọi view:

```sql
CREATE OR REPLACE
    SQL SECURITY INVOKER
VIEW v_public_products AS
SELECT product_id, sku, product_name
FROM products
WHERE status = 'ACTIVE';
```

Người gọi cần có quyền cần thiết trên các đối tượng được truy cập qua view. Cách này tránh phụ thuộc quyền của một definer, nhưng không tạo lớp ủy quyền che giấu bảng nền theo cách DEFINER thường được dùng.

### 8.3. Kiểm tra definer và security type

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'sales'
ORDER BY TABLE_NAME;
```

Hoặc:

```sql
SHOW CREATE VIEW sales.v_public_products;
```

Nếu view hoạt động ở development nhưng lỗi ở production, kiểm tra definer, quyền SELECT trên bảng nền, quyền truy cập view và sự tồn tại của tài khoản definer.

## 9. CHECK OPTION và khả năng cập nhật view

Một số view có thể cập nhật được. `WITH CHECK OPTION` yêu cầu các hàng được INSERT/UPDATE thông qua view vẫn phải thỏa điều kiện của view.

Ví dụ:

```sql
CREATE OR REPLACE VIEW v_active_products AS
SELECT product_id, sku, product_name, status
FROM products
WHERE status = 'ACTIVE'
WITH CASCADED CHECK OPTION;
```

Nếu ứng dụng cập nhật `status` thành `INACTIVE` qua view, thao tác sẽ bị từ chối vì hàng mới không còn thỏa điều kiện view.

### 9.1. LOCAL và CASCADED

- `LOCAL`: kiểm tra điều kiện của view hiện tại.
- `CASCADED`: kiểm tra điều kiện của view hiện tại và các view nền trong chuỗi view có liên quan theo quy tắc check option.

Nếu không chỉ định, mặc định là `CASCADED` khi có `CHECK OPTION`.

### 9.2. Thay đổi schema có thể ảnh hưởng updatability

Một view có thể chuyển từ updatable sang non-updatable nếu định nghĩa được thay đổi để chứa aggregate, `DISTINCT`, `GROUP BY`, `UNION` hoặc các cấu trúc không cho phép cập nhật. Kiểm tra:

```sql
SELECT
    TABLE_NAME,
    IS_UPDATABLE,
    CHECK_OPTION
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'sales';
```

Không giả định view vẫn cập nhật được chỉ vì trước đây nó cho phép UPDATE. Sau migration, kiểm tra cả metadata và thử thao tác trên môi trường kiểm thử.

## 10. Kiểm tra view sau thay đổi schema

### 10.1. CHECK TABLE

MySQL hỗ trợ `CHECK TABLE` để kiểm tra view:

```sql
CHECK TABLE sales.v_active_products;
```

Lệnh có thể phát hiện view tham chiếu bảng, cột hoặc routine không còn hợp lệ. Nếu view invalid, kết quả có thể nêu nguyên nhân như tham chiếu table/column/function không hợp lệ hoặc vấn đề quyền của definer/invoker.

Có thể kiểm tra nhiều view:

```sql
CHECK TABLE
    sales.v_active_products,
    sales.v_active_product_names,
    sales.v_product_catalog;
```

`CHECK TABLE` là bước kiểm tra metadata; nó không thay thế kiểm thử truy vấn và quyền ứng dụng.

### 10.2. SHOW CREATE VIEW

```sql
SHOW CREATE VIEW sales.v_active_products;
```

So sánh định nghĩa với source control hoặc migration mong đợi. Kiểm tra tên bảng/cột, alias, algorithm, definer và security type.

### 10.3. DESCRIBE view

```sql
DESCRIBE sales.v_active_products;
```

Đảm bảo danh sách cột, kiểu dữ liệu và nullability phù hợp với hợp đồng mà client đang sử dụng.

### 10.4. SELECT thử

```sql
SELECT *
FROM sales.v_active_products
LIMIT 10;
```

Chạy truy vấn dưới tài khoản ứng dụng thực tế, không chỉ tài khoản DBA. Việc DBA đọc được view không chứng minh tài khoản runtime có đủ quyền hoặc definer đang hợp lệ.

### 10.5. EXPLAIN truy vấn qua view

```sql
EXPLAIN FORMAT=JSON
SELECT product_id, product_name
FROM sales.v_active_products
WHERE product_id = 1001;
```

Kiểm tra view được merge hay materialize, index nào trên bảng nền được chọn, số hàng ước lượng và điều kiện có được đẩy xuống hay không. Một view hợp lệ về metadata vẫn có thể tạo execution plan không phù hợp.

## 11. Thay đổi schema an toàn với nhiều view phụ thuộc

Không nên thực hiện một chuỗi DDL tùy tiện khi nhiều view đang sử dụng bảng nền. Hãy lập migration theo đồ thị phụ thuộc.

### 11.1. Bước 1: lập danh sách dependency

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME,
    TABLE_SCHEMA,
    TABLE_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'sales'
   OR VIEW_SCHEMA = 'sales'
ORDER BY VIEW_SCHEMA, VIEW_NAME, TABLE_SCHEMA, TABLE_NAME;
```

Lưu ý: điều kiện trên giúp tìm các cạnh có view hoặc đối tượng được tham chiếu thuộc schema `sales`; nếu dependency đi qua schema khác, cần mở rộng phạm vi truy vấn.

### 11.2. Bước 2: lưu định nghĩa hiện tại

Với mỗi view quan trọng, lưu `SHOW CREATE VIEW` vào migration repository hoặc artifact triển khai. Ghi lại cột đầu ra và thuộc tính security.

### 11.3. Bước 3: phân loại thay đổi

Phân biệt:

- Thêm cột mới mà view hiện tại không sử dụng.
- Đổi tên hoặc xóa cột đang được view tham chiếu.
- Đổi kiểu dữ liệu, nullability hoặc collation.
- Đổi tên bảng hoặc di chuyển schema.
- Thay đổi index chỉ ảnh hưởng execution plan.
- Thay đổi định nghĩa view và hợp đồng đầu ra.

Mỗi loại có phạm vi kiểm thử khác nhau.

### 11.4. Bước 4: triển khai theo hướng tương thích

Ví dụ cần đổi `sku` thành `product_code`. Có thể chia thành giai đoạn:

1. Thêm cột mới `product_code` hoặc tạo cơ chế đồng bộ tương thích.
2. Cập nhật dữ liệu và xác nhận hai cột đồng nhất theo quy tắc nghiệp vụ.
3. Tạo/cập nhật view công bố alias `product_code`.
4. Chuyển client và view phụ thuộc sang cột mới.
5. Xác nhận không còn dependency tới `sku`.
6. Sau thời gian tương thích, mới xóa cột cũ.

Đây là mẫu expand-and-contract. Cách đồng bộ hai cột phải được thiết kế theo hệ thống thực tế; không tự động thêm trigger nếu chưa đánh giá transaction, replication và thứ tự cập nhật.

### 11.5. Bước 5: cập nhật theo thứ tự dependency

Nếu `v_low` phụ thuộc bảng nền, `v_mid` phụ thuộc `v_low`, `v_top` phụ thuộc `v_mid`, thứ tự an toàn thường là:

1. Cập nhật bảng nền.
2. Tạo lại `v_low`.
3. Tạo lại `v_mid`.
4. Tạo lại `v_top`.
5. Kiểm tra và kiểm thử client.

Nếu cần drop một view để thay đổi cấu trúc, drop từ view phụ thuộc cấp cao xuống trước, sau đó tạo lại từ nền lên. Không xóa view nền khi view cấp trên vẫn cần nó.

### 11.6. Bước 6: kiểm tra và phát hành

```sql
CHECK TABLE
    sales.v_low,
    sales.v_mid,
    sales.v_top;

SHOW CREATE VIEW sales.v_low;
SHOW CREATE VIEW sales.v_mid;
SHOW CREATE VIEW sales.v_top;
```

Sau đó chạy SELECT/EXPLAIN dưới tài khoản runtime và kiểm tra các chức năng ứng dụng phụ thuộc view.

## 12. DDL, transaction và kế hoạch rollback

Các lệnh DDL như `ALTER TABLE`, `CREATE VIEW`, `ALTER VIEW`, `DROP VIEW` có quy tắc commit riêng của MySQL. Không giả định có thể bọc toàn bộ migration view/schema trong transaction rồi rollback tất cả bằng `ROLLBACK`.

Trước khi chạy migration:

- Chuẩn bị DDL ngược hoặc phương án khôi phục định nghĩa cũ.
- Lưu `SHOW CREATE VIEW` trước thay đổi.
- Xác định thứ tự triển khai và phụ thuộc downstream.
- Kiểm tra metadata lock và thời gian DDL trên bảng lớn.
- Chạy thử trong môi trường staging với dữ liệu và quyền gần production.
- Triển khai theo bước tương thích nếu client được phát hành độc lập.

MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác được hỗ trợ, nhưng atomic DDL không có nghĩa một chuỗi nhiều DDL khác nhau trở thành transaction có thể rollback cùng nhau. Migration phải được thiết kế để phục hồi ở cấp quy trình.

## 13. View và temporary table

View là đối tượng schema có định nghĩa được lưu lâu dài. Temporary table do session tạo chỉ tồn tại trong connection hiện tại. Vì khác vòng đời và phạm vi, view không thể được định nghĩa để tham chiếu temporary table.

Ví dụ sau không phải thiết kế hợp lệ:

```sql
CREATE TEMPORARY TABLE tmp_active_products (
    product_id BIGINT NOT NULL,
    product_name VARCHAR(160) NOT NULL
);

-- Không thể tạo view schema bền vững dựa trên temporary table này.
```

Nếu cần view cho ứng dụng, hãy tham chiếu bảng nền bền vững. Nếu cần dữ liệu trung gian theo session, truy vấn trực tiếp temporary table trong session đó hoặc đưa dữ liệu vào bảng staging có vòng đời được quản lý.

Không nhầm temporary table do ứng dụng tạo với bảng tạm nội bộ mà optimizer có thể dùng để thực thi một view có aggregate/materialization.

## 14. Bảo mật và quyền kiểm tra định nghĩa

Một số thao tác kiểm tra cần quyền riêng:

- `SHOW CREATE VIEW` cần quyền `SHOW VIEW` trên view.
- Đọc dữ liệu qua view cần quyền phù hợp theo `SQL SECURITY DEFINER` hoặc `INVOKER`.
- `CREATE VIEW`, `ALTER VIEW` và `DROP VIEW` yêu cầu quyền quản trị tương ứng trên schema/đối tượng.
- Tài khoản definer cần quyền trên bảng hoặc view nền theo định nghĩa.

Ví dụ cấp quyền xem định nghĩa cho một tài khoản đã tồn tại:

```sql
GRANT SHOW VIEW ON sales.* TO 'report_reader'@'localhost';
```

Đây là ví dụ tên tài khoản. Hãy thay bằng account thực tế theo chính sách phân quyền; không cấp quyền rộng hơn nhu cầu. `SHOW VIEW` cho phép xem định nghĩa, không tự cấp quyền SELECT dữ liệu qua view.

Khi kiểm tra sự cố, cần tách ba câu hỏi:

1. View có định nghĩa hợp lệ không?
2. Definer/invoker có đủ quyền trên đối tượng nền không?
3. Tài khoản ứng dụng có quyền sử dụng view và các thao tác cần thiết không?

Một lỗi quyền không nhất thiết là lỗi dependency schema; cần đọc thông báo lỗi và kiểm tra từng lớp.

## 15. Thực hành: phát hiện và sửa view sau thay đổi schema

### 15.1. Tạo bảng và chuỗi view

```sql
DROP VIEW IF EXISTS v_product_names;
DROP VIEW IF EXISTS v_active_products;
DROP TABLE IF EXISTS products;

CREATE TABLE products (
    product_id BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE VIEW v_active_products AS
SELECT product_id, sku, product_name
FROM products
WHERE status = 'ACTIVE';

CREATE VIEW v_product_names AS
SELECT product_id, product_name
FROM v_active_products;
```

### 15.2. Kiểm tra dependency và định nghĩa

```sql
SELECT
    VIEW_SCHEMA,
    VIEW_NAME,
    TABLE_SCHEMA,
    TABLE_NAME
FROM information_schema.VIEW_TABLE_USAGE
WHERE VIEW_SCHEMA = DATABASE()
ORDER BY VIEW_NAME, TABLE_NAME;

SHOW CREATE VIEW v_active_products;
SHOW CREATE VIEW v_product_names;
```

### 15.3. Thêm cột mới

```sql
ALTER TABLE products
    ADD COLUMN category_id BIGINT NULL;
```

Kiểm tra:

```sql
DESCRIBE v_active_products;
```

`category_id` không tự xuất hiện trong view. Cập nhật view:

```sql
CREATE OR REPLACE VIEW v_active_products AS
SELECT product_id, sku, product_name, category_id
FROM products
WHERE status = 'ACTIVE';
```

Nếu view `v_product_names` không cần `category_id`, nó có thể tiếp tục hoạt động vì các cột mà nó tham chiếu vẫn còn. Dù vậy, cần chạy `CHECK TABLE` và SELECT để xác nhận.

### 15.4. Đổi tên cột và cập nhật dependency

Giả sử đổi `sku` thành `product_code`. Trước tiên, xác định mọi view phụ thuộc. Sau DDL:

```sql
ALTER TABLE products
    RENAME COLUMN sku TO product_code;
```

View `v_active_products` vẫn tham chiếu `sku` nên có thể bị invalid. Cập nhật view nền:

```sql
CREATE OR REPLACE VIEW v_active_products AS
SELECT product_id, product_code, product_name, category_id
FROM products
WHERE status = 'ACTIVE';
```

View `v_product_names` chỉ dùng `product_id` và `product_name`; kiểm tra lại:

```sql
CHECK TABLE v_active_products, v_product_names;
SELECT * FROM v_active_products LIMIT 5;
SELECT * FROM v_product_names LIMIT 5;
```

### 15.5. Xác minh schema đầu ra và quyền

```sql
SHOW CREATE VIEW v_active_products;
DESCRIBE v_active_products;

SELECT
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    IS_UPDATABLE
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = DATABASE();
```

Thực hiện SELECT dưới tài khoản ứng dụng có quyền tương ứng để xác minh hành vi thực tế.

## 16. Lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| View lỗi sau khi đổi tên cột | Định nghĩa còn tham chiếu tên cũ | Tìm dependency, cập nhật view theo thứ tự từ nền lên |
| Thêm cột nhưng view không trả cột mới | Danh sách cột của view được xác định khi tạo/định nghĩa lại | Dùng CREATE OR REPLACE VIEW hoặc ALTER VIEW |
| DROP COLUMN thất bại hoặc view invalid | Cột còn được view tham chiếu hoặc view không còn phân giải được | Tìm view phụ thuộc và triển khai migration tương thích |
| View cấp cao lỗi dù view nền chạy được | View cấp cao phụ thuộc tên/cột đã thay đổi ở view nền | Lần theo dependency nhiều cấp và tạo lại downstream view |
| SHOW CREATE VIEW không xem được định nghĩa | Thiếu quyền SHOW VIEW | Yêu cầu cấp quyền tối thiểu phù hợp |
| View chạy ở dev nhưng lỗi ở production | Definer không tồn tại hoặc quyền khác nhau | Kiểm tra DEFINER, SECURITY_TYPE và quyền đối tượng nền |
| View vẫn chạy nhưng ứng dụng lỗi | Kiểu dữ liệu, alias hoặc thứ tự cột đầu ra đã thay đổi | DESCRIBE, kiểm tra contract và test client |
| View đổi thành non-updatable | Định nghĩa mới có aggregate, DISTINCT, GROUP BY hoặc cấu trúc hạn chế | Kiểm tra IS_UPDATABLE và thiết kế lại thao tác ghi |
| CHECK TABLE báo invalid reference | Bảng/cột/routine được tham chiếu không còn hợp lệ | Đọc SHOW CREATE VIEW, sửa dependency rồi CHECK lại |
| DDL migration không rollback được | DDL có implicit commit/atomic DDL riêng | Dùng migration theo bước và có DDL khôi phục |
| View tham chiếu temporary table | Temporary table có vòng đời session, không phải đối tượng bền vững | Dùng bảng nền hoặc staging table phù hợp |

## 17. Checklist triển khai thay đổi schema có view

- [ ] Đã liệt kê view trong các schema liên quan.
- [ ] Đã truy vấn `INFORMATION_SCHEMA.VIEW_TABLE_USAGE` để lập dependency trực tiếp.
- [ ] Đã lần theo dependency gián tiếp giữa các view.
- [ ] Đã lưu `SHOW CREATE VIEW` của các view bị ảnh hưởng.
- [ ] Đã kiểm tra cột đầu ra, kiểu dữ liệu, alias và thứ tự cột.
- [ ] Đã xác định DDL có thêm, đổi tên, xóa cột/bảng hoặc thay đổi kiểu dữ liệu không.
- [ ] Đã tránh phụ thuộc không cần thiết vào `SELECT *`.
- [ ] Đã chuẩn bị thứ tự cập nhật view từ dependency thấp lên cao.
- [ ] Đã kiểm tra `ALGORITHM`, `DEFINER`, `SQL SECURITY` và `CHECK OPTION`.
- [ ] Đã kiểm tra tài khoản definer và quyền của ứng dụng.
- [ ] Đã chạy `CHECK TABLE`, `SHOW CREATE VIEW`, `DESCRIBE` và SELECT thử.
- [ ] Đã dùng EXPLAIN để kiểm tra execution plan qua view quan trọng.
- [ ] Đã kiểm thử client phụ thuộc view sau migration.
- [ ] Đã có kế hoạch phục hồi vì chuỗi DDL không phải một transaction rollback được.
- [ ] Không tạo view phụ thuộc temporary table.

## 18. Kết luận

View phụ thuộc vào tên bảng, tên cột, biểu thức và các view khác được tham chiếu trong định nghĩa. Thay đổi schema nền có thể làm view invalid hoặc thay đổi hợp đồng cột đầu ra. Thêm cột không tự mở rộng view đã tạo bằng `SELECT *`; đổi tên/xóa cột đang được tham chiếu có thể làm view và các view phụ thuộc lỗi.

Hãy dùng `INFORMATION_SCHEMA.VIEWS`, `VIEW_TABLE_USAGE`, `SHOW CREATE VIEW`, `DESCRIBE` và `CHECK TABLE` để kiểm kê, kiểm tra định nghĩa và lần theo dependency. Khi migration, lưu định nghĩa hiện tại, cập nhật view theo thứ tự từ nền lên, xác minh `DEFINER`/`SQL SECURITY`, kiểm thử bằng tài khoản ứng dụng và chuẩn bị phương án phục hồi cho chuỗi DDL. Quản lý view như một hợp đồng schema giúp thay đổi bảng nền an toàn và tránh lỗi lan truyền tới nhiều tầng ứng dụng.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: CREATE VIEW Statement](https://dev.mysql.com/doc/refman/8.4/en/create-view.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA VIEWS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-views-table.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA VIEW_TABLE_USAGE Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-view-table-usage-table.html)
- [MySQL 8.4 Reference Manual: CHECK TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/check-table.html)
