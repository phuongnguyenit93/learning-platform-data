# Tạo bảng từ truy vấn và giới hạn sao chép cấu trúc

Một câu `SELECT` có thể tạo ra một bảng kết quả gồm những cột và dòng mà ta cần phân tích. Khi muốn **lưu kết quả đó thành một bảng vật lý mới**, nhiều hệ quản trị cơ sở dữ liệu hỗ trợ cách viết `CREATE TABLE ... AS SELECT ...`, thường gọi là **CTAS** (*Create Table As Select*).

Tuy nhiên, tạo bảng từ truy vấn **không đồng nghĩa sao chép nguyên vẹn cấu trúc của bảng nguồn**. Bảng mới thường có các cột và dữ liệu theo kết quả `SELECT`, nhưng nhiều đặc tính quan trọng như khóa chính, khóa ngoại, `UNIQUE`, `CHECK`, giá trị mặc định, cột tự sinh, chỉ mục và trigger có thể không được chuyển sang.

Bài học thuộc chủ đề **Database SQL → Bảng và lược đồ**. Nội dung chính là thực hiện CTAS, đọc đúng lược đồ tạo ra, nhận diện những gì không được sao chép và lựa chọn cách tạo bảng thích hợp khi cần giữ cấu trúc.

Các ví dụ thực hành dùng **PostgreSQL** để có một bộ cú pháp và kết quả nhất quán. Phần cuối nêu khác biệt đáng chú ý với MySQL, SQL Server và SQLite.

## 1. Phân biệt kết quả truy vấn với bảng mới

Hãy xem ba lệnh sau:

~~~sql
-- 1. Chỉ đọc dữ liệu: không tạo bảng.
SELECT sku, price
FROM lab_products;

-- 2. Tạo một bảng mới rồi lưu kết quả truy vấn vào bảng đó.
CREATE TABLE lab_product_prices AS
SELECT sku, price
FROM lab_products;

-- 3. Tạo bảng theo cấu trúc do ta khai báo rõ.
CREATE TABLE lab_product_prices_manual (
    sku VARCHAR(20) NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);
~~~

Đây là **ba tình huống minh họa độc lập**, chưa phải đoạn script để chạy ngay: bảng `lab_products` cần được tạo trước, còn hai lệnh tạo bảng đích có thể xung đột tên nếu cùng chạy trong một database. Phần 2 sẽ chuẩn bị bảng nguồn trước khi thực hiện CTAS.

| Cách làm | Tạo bảng vật lý? | Có chèn dữ liệu ngay? | Cấu trúc cột đến từ đâu? |
| --- | --- | --- | --- |
| `SELECT ...` | Không | Không | Kết quả truy vấn tạm thời |
| `CREATE TABLE ... AS SELECT ...` | Có | Có, trừ khi chỉ định không lấy dữ liệu | Danh sách cột/kiểu của kết quả `SELECT` |
| `CREATE TABLE ... (column definitions)` | Có | Không | Các khai báo cột và ràng buộc do người viết định nghĩa |

CTAS kết hợp hai ý tưởng: **tạo đối tượng bảng** và **nạp dữ liệu từ truy vấn**. Bảng mới là một đối tượng độc lập, có thể được truy vấn, cập nhật hoặc cấp quyền riêng. Nó không tự động duy trì mối liên hệ đồng bộ với bảng nguồn.

## 2. Chuẩn bị bảng nguồn có ràng buộc để thực hành

Trong một database PostgreSQL thử nghiệm, tạo một bảng sản phẩm mang tên `lab_products`. Chỉ chạy đoạn khởi tạo này **một lần trên database chưa có bảng cùng tên**:

~~~sql
CREATE TABLE lab_products (
    product_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(20) NOT NULL UNIQUE,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    status VARCHAR(12) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

CREATE INDEX lab_products_price_idx
    ON lab_products (price);

INSERT INTO lab_products (sku, price, stock, status)
VALUES
    ('BOOK-01', 120000.00, 5, 'ACTIVE'),
    ('PEN-02',   10000.00, 0, 'ACTIVE'),
    ('BAG-03',  350000.00, 2, 'INACTIVE'),
    ('NOTE-04',  45000.00, 3, 'ACTIVE');
~~~

Đoạn này tạo bảng với những thuộc tính mà ta cần kiểm tra sau khi sao chép:

- `product_id`: cột số nguyên tự sinh bằng `IDENTITY`, đồng thời là **khóa chính**.
- `sku`: chuỗi mã sản phẩm, bắt buộc có giá trị và **không trùng** nhờ `NOT NULL UNIQUE`.
- `price`: số có hai chữ số thập phân, không âm nhờ `CHECK (price >= 0)`.
- `stock`: số nguyên, không âm, có giá trị mặc định `0` khi không cung cấp.
- `status`: mặc định `ACTIVE`, chỉ cho phép `ACTIVE` hoặc `INACTIVE`.
- `lab_products_price_idx`: một chỉ mục được khai báo riêng trên cột giá.

Xem bảng nguồn:

~~~sql
SELECT product_id, sku, price, stock, status
FROM lab_products
ORDER BY product_id;
~~~

Nếu tạo bảng mới từ đầu, các ID do `IDENTITY` cấp sẽ lần lượt là 1 đến 4:

| product_id | sku | price | stock | status |
| ---: | --- | ---: | ---: | --- |
| 1 | BOOK-01 | 120000.00 | 5 | ACTIVE |
| 2 | PEN-02 | 10000.00 | 0 | ACTIVE |
| 3 | BAG-03 | 350000.00 | 2 | INACTIVE |
| 4 | NOTE-04 | 45000.00 | 3 | ACTIVE |

Nguồn có bốn sản phẩm nhưng chỉ hai sản phẩm vừa ở trạng thái `ACTIVE` vừa có tồn kho dương.

## 3. Tạo bảng trực tiếp từ SELECT bằng CTAS

### 3.1. Cú pháp chung

Mẫu cú pháp phổ biến:

~~~sql
CREATE TABLE ten_bang_moi AS
SELECT cot_1, cot_2, bieu_thuc AS cot_moi
FROM ten_bang_nguon
WHERE dieu_kien;
~~~

Tên bảng đứng sau `CREATE TABLE` là đối tượng sẽ được tạo; mọi phần sau `AS` là truy vấn xác định **danh sách cột và tập hàng ban đầu** của bảng đó.

### 3.2. Một ví dụ có điều kiện lọc và cột tính toán

Chạy:

~~~sql
CREATE TABLE lab_active_inventory AS
SELECT
    product_id,
    sku,
    price,
    stock,
    status,
    price * stock AS inventory_value
FROM lab_products
WHERE status = 'ACTIVE'
  AND stock > 0;
~~~

Sau đó đọc bảng mới:

~~~sql
SELECT
    product_id,
    sku,
    price,
    stock,
    status,
    inventory_value
FROM lab_active_inventory
ORDER BY product_id;
~~~

Kết quả dự kiến:

| product_id | sku | price | stock | status | inventory_value |
| ---: | --- | ---: | ---: | --- | ---: |
| 1 | BOOK-01 | 120000.00 | 5 | ACTIVE | 600000.00 |
| 4 | NOTE-04 | 45000.00 | 3 | ACTIVE | 135000.00 |

Nhìn vào kết quả có thể rút ra bốn điều:

1. **Chỉ những hàng thỏa `WHERE` được chèn** vào bảng mới. Hai sản phẩm PEN-02 và BAG-03 không có trong bảng đích.
2. **Chỉ những cột được `SELECT` trả về xuất hiện** trong bảng đích. Nếu bỏ `status` khỏi danh sách chọn, bảng mới sẽ không có cột đó.
3. Biểu thức `price * stock AS inventory_value` tạo một cột mới có tên `inventory_value`, kiểu dữ liệu được hệ quản trị suy ra từ biểu thức. Đây là **giá trị đã tính khi chạy truy vấn**, không phải một công thức luôn tự tính lại khi `price` thay đổi.
4. `product_id` ở bảng đích nhận các số 1 và 4 từ **dữ liệu** bảng nguồn. Điều đó **không** có nghĩa bảng mới còn định nghĩa khóa chính hay cơ chế cấp ID tự động.

Sơ đồ:

~~~text
lab_products (4 hàng)
  product_id, sku, price, stock, status
                 |
                 | SELECT ... WHERE status='ACTIVE' AND stock>0
                 |          + (price * stock) AS inventory_value
                 v
lab_active_inventory (2 hàng)
  product_id, sku, price, stock, status, inventory_value

=> Kết quả SELECT được ghi thành bảng mới tại thời điểm chạy.
=> Các quy tắc cấu trúc của bảng nguồn không tự động đi theo.
~~~

## 4. CTAS sao chép được gì, và không sao chép được gì?

Với **PostgreSQL `CREATE TABLE AS SELECT`**, bảng đích có **các cột, kiểu dữ liệu suy ra và dữ liệu** của kết quả truy vấn. Nó không phải bản sao lược đồ đầy đủ của bảng nguồn.

| Thành phần | `lab_products` (nguồn) | `lab_active_inventory` tạo bằng CTAS | Điều cần hiểu |
| --- | --- | --- | --- |
| Tên và thứ tự cột | Theo `CREATE TABLE` nguồn | Theo danh sách biểu thức trong `SELECT` | Có thể chọn ít cột, đổi tên, đổi thứ tự |
| Kiểu cột | Do DDL nguồn khai báo | Suy ra từ kiểu kết quả mỗi biểu thức | Cột tính toán có kiểu từ biểu thức, không có “cột nguồn” tương ứng |
| Dữ liệu | Bốn hàng ban đầu | Hai hàng thỏa `WHERE` | Có thể lọc, nối, nhóm hoặc biến đổi dữ liệu |
| `PRIMARY KEY` | `product_id` | **Không có** | Giá trị hiện tại trông duy nhất không biến nó thành khóa chính |
| `UNIQUE` | `sku` | **Không có** | Bảng đích có thể nhận mã trùng |
| `NOT NULL` | Nhiều cột | **Không được mang theo** | Cột đích không tự kế thừa yêu cầu bắt buộc có giá trị |
| `CHECK` | Giá, tồn kho và trạng thái | **Không có** | Không tự chặn giá âm hay trạng thái ngoài danh sách |
| `DEFAULT` | `stock = 0`, `status = 'ACTIVE'` | **Không có** | Bỏ cột khi `INSERT` có thể tạo `NULL` nếu không khai báo lại |
| `IDENTITY` | `product_id` tự sinh | **Không có** | Chọn giá trị ID chỉ là chép **giá trị** |
| Index tạo riêng | `lab_products_price_idx` | **Không có chỉ mục này** | Kế hoạch truy vấn và hiệu năng có thể thay đổi |
| Foreign key, trigger, quyền | Phụ thuộc bảng nguồn | **Không tự sao chép đầy đủ** | Phải thiết lập theo yêu cầu bảng đích |

Điểm quan trọng nhất: **cùng tên cột và cùng dữ liệu hiện tại chưa đủ để gọi hai bảng có cùng cấu trúc**. Ràng buộc và chỉ mục là metadata của bảng, không phải những hàng do `SELECT` trả về.

### 4.1. Quan sát bằng một thao tác thử rồi ROLLBACK

Trong bảng nguồn, không thể ghi giá âm vì `CHECK (price >= 0)`; cũng không thể để `product_id` là `NULL` do ràng buộc khóa chính/identity. Trong bảng đích CTAS, các ràng buộc đó không tồn tại.

Có thể kiểm chứng trong **database thử nghiệm PostgreSQL** bằng transaction để không để lại hàng sai:

~~~sql
BEGIN;

INSERT INTO lab_active_inventory
    (product_id, sku, price, stock, status, inventory_value)
VALUES
    (NULL, 'INVALID-TEST', -5.00, -1, NULL, 5.00);

SELECT product_id, sku, price, stock, status
FROM lab_active_inventory
WHERE sku = 'INVALID-TEST';

ROLLBACK;
~~~

Trong transaction, câu `INSERT` có thể thành công: các giá trị vẫn phù hợp **kiểu cột**, nhưng những quy tắc `PRIMARY KEY`, `NOT NULL` và `CHECK` của bảng nguồn không có tại bảng đích. `ROLLBACK` hủy hàng thử nghiệm chưa commit. Trên hệ quản trị khác, hành vi DDL/transaction có thể khác; ví dụ này dành cho PostgreSQL.

Ví dụ minh họa rằng **kiểu dữ liệu** và **ràng buộc dữ liệu** là hai tầng kiểm soát khác nhau. Cột giá nhận số âm vẫn là kiểu số hợp lệ; chỉ khi có `CHECK` thì quy tắc “giá không âm” mới được bảo vệ.

### 4.2. Xem metadata thay vì đoán theo tên cột

Có thể so sánh thông tin cột của hai bảng trong PostgreSQL:

~~~sql
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default,
    is_identity
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name IN ('lab_products', 'lab_active_inventory')
ORDER BY table_name, ordinal_position;
~~~

Kết quả sẽ cho biết các cột, khả năng nhận `NULL`, giá trị mặc định và thuộc tính identity. Chỉ xem `SELECT *` của hai bảng không thể thấy đầy đủ sự khác biệt này.

Để xem chỉ mục trong PostgreSQL:

~~~sql
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename IN ('lab_products', 'lab_active_inventory')
ORDER BY tablename, indexname;
~~~

Trên bảng nguồn sẽ có chỉ mục cho khóa chính, cho ràng buộc duy nhất `sku` và chỉ mục giá được tạo riêng. Bảng đích CTAS không tự có các chỉ mục đó.

Trong `psql`, lệnh meta `\d lab_products` và `\d lab_active_inventory` cũng cho phép xem cấu trúc, nhưng `\d` là **lệnh của chương trình `psql`**, không phải SQL có thể chạy trong mọi công cụ.

## 5. Tạo bảng chỉ với cấu trúc cột từ SELECT, không chèn hàng

PostgreSQL cho phép thêm `WITH NO DATA` vào CTAS:

~~~sql
CREATE TABLE lab_active_inventory_empty AS
SELECT
    product_id,
    sku,
    price,
    stock,
    status,
    price * stock AS inventory_value
FROM lab_products
WHERE status = 'ACTIVE'
  AND stock > 0
WITH NO DATA;
~~~

Kiểm tra:

~~~sql
SELECT COUNT(*) AS so_hang
FROM lab_active_inventory_empty;
~~~

Kết quả bằng **0**. Bảng mới vẫn có các cột từ danh sách `SELECT`, nhưng chưa chứa dữ liệu. Tên `WITH NO DATA` dễ khiến người đọc nghĩ là “sao chép schema gốc”; thực ra nó chỉ có nghĩa **không lấy hàng của truy vấn khi tạo bảng**. Ràng buộc, mặc định, identity và chỉ mục của `lab_products` vẫn không tự đi theo.

Một cách phổ biến ở hệ quản trị không có `WITH NO DATA` cho CTAS là chọn điều kiện luôn sai:

~~~sql
-- Mot mau thuong gap, nhung van can kiem tra SQL dialect.
CREATE TABLE lab_products_empty_query AS
SELECT product_id, sku, price, stock, status
FROM lab_products
WHERE 1 = 0;
~~~

Cách này giúp tạo bảng không có hàng trong nhiều hệ quản trị; nó cũng **chỉ sao chép cấu trúc của kết quả SELECT**, không bảo đảm mang theo mọi thuộc tính của bảng nguồn.

## 6. Khi muốn giữ lược đồ, dùng cách khác CTAS

### 6.1. Tạo bảng bằng DDL rõ ràng rồi mới chèn dữ liệu

Nếu bảng mới cần giữ các quy tắc riêng, định nghĩa chúng trước:

~~~sql
CREATE TABLE lab_active_inventory_checked (
    product_id INTEGER PRIMARY KEY,
    sku VARCHAR(20) NOT NULL UNIQUE,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    status VARCHAR(12) NOT NULL
        CHECK (status IN ('ACTIVE', 'INACTIVE')),
    inventory_value NUMERIC(20, 2) NOT NULL
);

INSERT INTO lab_active_inventory_checked
    (product_id, sku, price, stock, status, inventory_value)
SELECT
    product_id,
    sku,
    price,
    stock,
    status,
    price * stock
FROM lab_products
WHERE status = 'ACTIVE'
  AND stock > 0;
~~~

Với cách này, **DDL của bảng đích** chịu trách nhiệm về cấu trúc và ràng buộc; câu `INSERT ... SELECT` chỉ chịu trách nhiệm đưa dữ liệu vào. Ta có thể chọn kiểu `NUMERIC(20, 2)` cho giá trị tồn kho vì phép nhân giá với số lượng có thể cần phạm vi lớn hơn kiểu của giá đơn vị.

Bảng đích trong ví dụ được thiết kế để giữ `product_id` giống dữ liệu nguồn. Nếu mục tiêu là tạo mã ID mới cho mỗi bản ghi, cách khai báo và danh sách cột `INSERT` cần thay đổi theo thiết kế, không nên sao chép ID một cách máy móc.

### 6.2. PostgreSQL CREATE TABLE ... LIKE ... INCLUDING ALL

Khi cần tạo một bảng có cấu trúc gần giống bảng hiện có, PostgreSQL hỗ trợ:

~~~sql
CREATE TABLE lab_products_like (
    LIKE lab_products INCLUDING ALL
);
~~~

Khác với CTAS, lệnh `LIKE` này là cơ chế **sao chép định nghĩa cột và nhiều thuộc tính schema**. Với `INCLUDING ALL`, PostgreSQL yêu cầu sao chép các nhóm thuộc tính được hỗ trợ, như giá trị mặc định, ràng buộc `CHECK`, định nghĩa identity/generated, chỉ mục và các thuộc tính cột liên quan. Các ràng buộc `NOT NULL` cũng được sao chép. Riêng identity trong bảng mới được tạo với cơ chế sequence riêng.

Tuy nhiên, `INCLUDING ALL` **không phải bản sao tuyệt đối của toàn bộ đối tượng**: khóa ngoại, trigger, quyền truy cập, quan hệ phụ thuộc và nhiều đối tượng liên quan không tự động được nhân bản chỉ bằng cú pháp này. Đặc biệt, kiểu mặc định dựa trên sequence kiểu cũ như `SERIAL` có thể cần kiểm tra để tránh chia sẻ sequence ngoài ý muốn.

Sau khi đã tạo bảng, dùng `INSERT ... SELECT` để lấy dữ liệu:

~~~sql
-- Bo product_id de IDENTITY cua bang moi tu cap gia tri.
INSERT INTO lab_products_like (sku, price, stock, status)
SELECT sku, price, stock, status
FROM lab_products;
~~~

Ở đây bảng đích tự cấp `product_id` mới. Với dữ liệu thử nghiệm mới tạo, các giá trị có thể tình cờ giống ID nguồn, nhưng **không được xem đó là cam kết sao chép định danh**. Nếu cần giữ nguyên ID nguồn, cần thiết kế thao tác chèn tường minh và quản lý sequence/identity thích hợp.

So sánh nhanh:

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| Lưu nhanh một tập kết quả, có thể thay đổi cột/tính toán/tổng hợp | `CREATE TABLE ... AS SELECT ...` |
| Tạo bảng trống với cột của kết quả truy vấn | CTAS `WITH NO DATA` (PostgreSQL) |
| Tạo bảng có ràng buộc, chỉ mục, kiểu, mặc định theo thiết kế rõ ràng | `CREATE TABLE` định nghĩa cột rồi `INSERT ... SELECT` |
| Nhân bản nhiều thuộc tính lược đồ từ bảng nguồn trong PostgreSQL | `CREATE TABLE ... (LIKE ... INCLUDING ALL)`; sau đó chèn dữ liệu nếu cần |
| Sao chép gần như toàn bộ đối tượng có khóa ngoại, trigger, quyền và cấu hình liên quan | Dùng DDL/migration hoặc công cụ sao lưu schema được thiết kế cho hệ quản trị cụ thể; kiểm tra từng đối tượng |

## 7. CTAS từ biểu thức, JOIN và GROUP BY

CTAS không yêu cầu truy vấn chỉ lấy nguyên cột từ một bảng. Bất cứ truy vấn `SELECT` hợp lệ nào trả về một tập cột xác định đều có thể là nguồn tạo bảng, trong phạm vi hỗ trợ của hệ quản trị.

### 7.1. Tổng hợp dữ liệu thành bảng báo cáo

Ví dụ muốn có bảng tổng hợp tồn kho theo trạng thái:

~~~sql
CREATE TABLE lab_inventory_by_status AS
SELECT
    status,
    COUNT(*) AS product_count,
    SUM(price * stock) AS total_inventory_value
FROM lab_products
GROUP BY status;
~~~

Đọc theo thứ tự rõ ràng:

~~~sql
SELECT status, product_count, total_inventory_value
FROM lab_inventory_by_status
ORDER BY status;
~~~

Kết quả dự kiến:

| status | product_count | total_inventory_value |
| --- | ---: | ---: |
| ACTIVE | 3 | 735000.00 |
| INACTIVE | 1 | 700000.00 |

Cột `product_count` đến từ `COUNT(*)`, còn `total_inventory_value` đến từ `SUM(price * stock)`. Hai cột này có kiểu theo kết quả **hàm tổng hợp**, không nhất thiết trùng kiểu của bất kỳ cột đơn lẻ nào từ bảng nguồn.

Đây là một **bảng dữ liệu tổng hợp đã vật chất hóa tại thời điểm tạo**, không phải định nghĩa báo cáo tự động cập nhật mỗi khi thay đổi giá hoặc số lượng.

### 7.2. Tạo bảng từ JOIN và tên cột bị trùng

Trong truy vấn có nhiều bảng, `SELECT *` có thể trả về nhiều cột cùng tên như `id` hoặc `status`. Một bảng đích phải có **tên cột hợp lệ và không trùng**; PostgreSQL có thể từ chối CTAS nếu kết quả chứa tên trùng nhau.

Mẫu đúng khi nối các bảng nên chọn và đặt bí danh rõ ràng:

~~~sql
-- Vi du minh hoa khi co bang orders va customers trong database.
CREATE TABLE lab_order_customer_report AS
SELECT
    o.order_id,
    o.customer_id,
    c.full_name AS customer_name,
    o.amount AS order_amount
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

Ví dụ này **chỉ chạy được nếu môi trường có các bảng `orders` và `customers` với những cột đã nêu**; nó độc lập với bảng `lab_products` của bài thực hành. Điểm cần học là dùng tên cột có định danh rõ, kiểm soát cấu trúc bảng đích và tránh `SELECT *` trong những bảng báo cáo lâu dài.

Ngay cả khi không trùng tên, dùng `SELECT *` khiến cấu trúc bảng đích thay đổi theo các cột mà truy vấn nguồn trả về vào thời điểm tạo bảng. Việc chủ động liệt kê cột giúp hạn chế sai lệch do thay đổi schema nguồn sau này.

## 8. Bảng CTAS có tự cập nhật theo dữ liệu nguồn không?

**Không.** CTAS sao chép dữ liệu theo kết quả truy vấn **tại thời điểm câu lệnh được thực thi**. Đây là một bản dữ liệu độc lập.

Sau khi tạo `lab_active_inventory`, thử trên PostgreSQL bằng transaction:

~~~sql
BEGIN;

UPDATE lab_products
SET price = 130000.00
WHERE sku = 'BOOK-01';

SELECT sku, price
FROM lab_products
WHERE sku = 'BOOK-01';

SELECT sku, price, inventory_value
FROM lab_active_inventory
WHERE sku = 'BOOK-01';

ROLLBACK;
~~~

Trong transaction, truy vấn nguồn thấy giá `130000.00`, nhưng bảng `lab_active_inventory` vẫn giữ giá cũ `120000.00` và `inventory_value = 600000.00`. `ROLLBACK` trả giá nguồn về ban đầu; bản sao không hề thay đổi.

Điều này khác với **view**:

~~~sql
CREATE VIEW lab_active_inventory_view AS
SELECT
    product_id,
    sku,
    price,
    stock,
    status,
    price * stock AS inventory_value
FROM lab_products
WHERE status = 'ACTIVE'
  AND stock > 0;
~~~

Một view thông thường lưu **định nghĩa truy vấn**. Khi đọc view, database thực thi logic truy vấn trên dữ liệu nguồn hiện hành (theo ngữ nghĩa transaction/isolation), thay vì đọc một bản sao CTAS được cố định từ trước.

PostgreSQL còn có **materialized view**: dữ liệu được lưu vật lý nhưng cần cơ chế như `REFRESH MATERIALIZED VIEW` để làm mới. CTAS, view và materialized view phục vụ các nhu cầu khác nhau; đừng giả định bảng CTAS tự có chức năng refresh.

Nếu cần tái tạo bảng báo cáo theo lịch, hãy thiết kế quy trình nạp hoặc thay thế dữ liệu có kiểm soát, xử lý lỗi, khóa và mức độ nhất quán. Chạy `CREATE TABLE ... AS SELECT` lần nữa trên **cùng tên bảng** thường gây lỗi “bảng đã tồn tại”; dùng `IF NOT EXISTS` (nếu dialect hỗ trợ) cũng không làm cho bảng cũ tự cập nhật.

## 9. Khác biệt cú pháp và khả năng sao chép giữa các hệ quản trị

Tên kỹ thuật CTAS thường dùng trong tài liệu về cơ sở dữ liệu, nhưng cú pháp và các chi tiết thực thi **không đồng nhất**.

| Hệ quản trị | Cách tạo bảng từ kết quả truy vấn | Ghi chú |
| --- | --- | --- |
| **PostgreSQL** | `CREATE TABLE new_table AS SELECT ...;` | Hỗ trợ `WITH NO DATA`; CTAS không mang theo index/ràng buộc/default/identity của nguồn. PostgreSQL có dạng `SELECT ... INTO new_table` lịch sử, nhưng tài liệu thường ưu tiên CTAS. |
| **MySQL** | `CREATE TABLE new_table AS SELECT ...;` hoặc `CREATE TABLE new_table SELECT ...;` | Nhiều thuộc tính như index, khóa, `AUTO_INCREMENT`, mặc định và các quy tắc bảng nguồn không được bảo toàn theo cách của `CREATE TABLE ... LIKE ...`; cần xem tài liệu phiên bản cụ thể. `CREATE TABLE ... LIKE source_table` hữu ích khi cần nhiều thuộc tính schema, rồi `INSERT ... SELECT` để thêm dữ liệu. |
| **SQL Server** | `SELECT col1, col2 INTO new_table FROM source_table;` | Là cách phổ biến để tạo bảng mới từ truy vấn trong SQL Server Database Engine. Không tự sao chép các index, khóa và trigger; riêng thuộc tính `IDENTITY` có thể được chuyển trong một số trường hợp chọn cột trực tiếp, tùy dạng truy vấn. |
| **SQLite** | `CREATE TABLE new_table AS SELECT ...;` | Bảng tạo bằng CTAS không có các ràng buộc định nghĩa cột như `PRIMARY KEY`, `UNIQUE`, `NOT NULL` và `CHECK`; kiểu khai báo được xác định theo affinity của kết quả truy vấn. Nếu cần quy tắc rõ ràng, định nghĩa bảng đích trước rồi `INSERT ... SELECT`. |

Chẳng hạn, trong **SQL Server**:

~~~sql
SELECT product_id, sku, price
INTO product_prices
FROM products;
~~~

Đây là ví dụ cú pháp dành riêng cho SQL Server, không phải câu để chạy ngay trong database PostgreSQL của bài. Ngược lại, trong PostgreSQL `SELECT ... INTO` ở ngữ cảnh hàm PL/pgSQL thường mang ý nghĩa gán kết quả vào biến. Cũng không nên nhầm `SELECT ... INTO OUTFILE` trong công cụ MySQL với tạo bảng: nó liên quan xuất dữ liệu ra tệp.

Với MySQL, một cách tách việc định nghĩa cấu trúc và lấy dữ liệu thường có dạng:

~~~sql
CREATE TABLE products_copy LIKE products;
INSERT INTO products_copy SELECT * FROM products;
~~~

Mẫu MySQL này giả định hai bảng có thứ tự cột tương thích; với công việc thực tế nên **liệt kê tường minh các cột**. `LIKE` ở MySQL cũng không bảo đảm nhân bản tất cả đối tượng liên quan, chẳng hạn ràng buộc khóa ngoại; vì vậy phải kiểm tra trước khi coi bảng đích tương đương nguồn.

**Quan trọng:** so sánh các dialect để chọn câu lệnh phù hợp với hệ quản trị bạn đang sử dụng. Không lấy một script chứa `WITH NO DATA`, `LIKE INCLUDING ALL`, `SELECT INTO` và `AUTO_INCREMENT` rồi kỳ vọng nó chạy nguyên vẹn ở mọi database.

## 10. Các tình huống dễ sai khi tạo bảng bằng truy vấn

### 10.1. Nhầm “dữ liệu giống nhau” với “lược đồ giống nhau”

Ví dụ bảng CTAS có cột `product_id` gồm các giá trị duy nhất. Điều này là sự thật về **dữ liệu đang có**, không phải một ràng buộc khóa chính. Khi cần bảo vệ dữ liệu tương lai, phải khai báo và kiểm tra khóa/chỉ mục/ràng buộc phù hợp.

### 10.2. Tưởng giá trị DEFAULT cũng được sao chép

Chọn một cột `stock` có giá trị `0` từ nguồn chỉ sao chép **con số 0 ở các dòng đã chọn**. Nó không tạo ra quy tắc `DEFAULT 0` cho những dòng được thêm sau này vào bảng đích.

### 10.3. Tưởng biểu thức SELECT trở thành cột sinh tự động

`price * stock AS inventory_value` tính giá trị trong lần CTAS. Nếu sau này cập nhật `price` trong **chính bảng đích**, giá trị `inventory_value` đã lưu cũng không tự thay đổi. Muốn duy trì công thức, cần dùng cơ chế cột sinh (*generated column*), view hoặc logic cập nhật thích hợp, tùy hệ quản trị.

### 10.4. Coi thứ tự bản ghi là cố định

Ngay cả khi truy vấn tạo bảng có `ORDER BY` và kết quả ban đầu trông được sắp xếp, **bảng SQL không hứa trả lại các hàng theo thứ tự lưu vật lý**. Khi đọc kết quả cho người dùng, luôn thêm `ORDER BY` vào `SELECT` của lần đọc.

### 10.5. Quên quyền, schema và tên bảng đã tồn tại

CTAS là lệnh DDL có tác động thật: tài khoản cần quyền tạo bảng tại schema đích và quyền đọc nguồn. Nếu tên bảng đã tồn tại, câu lệnh thông thường sẽ thất bại. Nếu database có nhiều schema, tên chưa chỉ rõ schema có thể tạo hoặc tìm đối tượng ở nơi khác dự kiến. Trong môi trường chia sẻ, nên xác định schema đích rõ ràng và tuân thủ quy ước đặt tên.

### 10.6. Cho rằng mọi hệ quản trị đều xử lý transaction như nhau

PostgreSQL hỗ trợ nhiều dạng DDL trong transaction; ví dụ tạo bảng có thể hoàn tác khi chưa commit. MySQL có nhiều lệnh DDL gây implicit commit. Việc bọc một script tạo bảng bằng `BEGIN` và `ROLLBACK` **không phải bảo đảm chung** cho mọi hệ quản trị. Hãy dựa vào tài liệu của hệ đang dùng, nhất là khi chạy thao tác trên dữ liệu cần giữ.

## 11. Bài tập thực hành

Các bài dưới đây giả định dữ liệu `lab_products` ở mục 2 và các bảng CTAS đã được tạo theo từng ví dụ. Nếu tự chạy lại bài, hãy tạo một database thử nghiệm mới hoặc dùng tên bảng khác để tránh xung đột đối tượng đã tồn tại.

### Bài 1 — Tạo bảng từ truy vấn có cột đổi tên

Yêu cầu: tạo bảng `lab_affordable_products` chỉ gồm cột `sku` và cột `listed_price` (lấy từ `price`) đối với các sản phẩm có `price < 50000`.

**Đáp án tham khảo:**

~~~sql
CREATE TABLE lab_affordable_products AS
SELECT
    sku,
    price AS listed_price
FROM lab_products
WHERE price < 50000;
~~~

Tập dữ liệu ban đầu có PEN-02 và NOTE-04. Bảng đích có hai cột `sku` và `listed_price`; không tự có `UNIQUE` của `sku`.

### Bài 2 — Tạo bảng rỗng có các cột của truy vấn

Yêu cầu: tạo bảng `lab_inventory_draft` có các cột `product_id`, `sku` và `inventory_value = price * stock`, nhưng không lấy hàng ban đầu.

**Đáp án tham khảo (PostgreSQL):**

~~~sql
CREATE TABLE lab_inventory_draft AS
SELECT
    product_id,
    sku,
    price * stock AS inventory_value
FROM lab_products
WITH NO DATA;
~~~

`SELECT COUNT(*) FROM lab_inventory_draft;` trả về 0. Dù bảng trống, nó vẫn không có khóa chính/`UNIQUE` gốc.

### Bài 3 — Phân biệt sao chép dữ liệu và sao chép ràng buộc

Giả sử đã tạo `lab_active_inventory` bằng CTAS. Trong những phát biểu sau, phát biểu nào đúng?

1. Các giá trị `product_id` đã chọn có thể giống ID nguồn.
2. Cột `product_id` của bảng mới tự động là khóa chính.
3. `lab_active_inventory` có thể có thêm cột `inventory_value` không xuất hiện trong bảng nguồn.
4. Nếu đổi giá ở `lab_products`, `inventory_value` trong bảng CTAS lập tức được tính lại.
5. Có thể tạo cấu trúc bảng đích bằng DDL tường minh rồi `INSERT ... SELECT` khi cần ràng buộc.

**Đáp án:** 1, 3 và 5 đúng; 2 và 4 sai. **Giá trị dữ liệu**, **định nghĩa ràng buộc** và **quy tắc cập nhật** là ba vấn đề khác nhau.

### Bài 4 — Chọn cách tạo bảng cho từng yêu cầu

| Yêu cầu | Lựa chọn phù hợp |
| --- | --- |
| Muốn lưu nhanh báo cáo doanh số tại một thời điểm | CTAS từ truy vấn tổng hợp |
| Muốn bảng rỗng với cột kết quả tính toán, không cần dữ liệu | CTAS `WITH NO DATA` trên PostgreSQL |
| Muốn một bảng giao dịch độc lập có khóa ngoại, chỉ mục và quy tắc dữ liệu đã được phê duyệt | Định nghĩa DDL đầy đủ rồi nạp bằng `INSERT ... SELECT` |
| Muốn kết quả luôn phản ánh dữ liệu nguồn khi truy vấn | View phù hợp, nếu không có yêu cầu đặc biệt về lưu vật lý |
| Muốn sao chép các thuộc tính schema phổ biến trong PostgreSQL | `CREATE TABLE ... (LIKE source INCLUDING ALL)`, rồi kiểm tra và bổ sung những gì chưa được sao chép |

## 12. Ghi nhớ

**CTAS tạo một bảng mới từ kết quả của `SELECT`.** Nó có thể chọn cột, đặt bí danh, lọc hàng, tính toán biểu thức, nối bảng và tổng hợp dữ liệu. Bảng được tạo lưu dữ liệu riêng tại thời điểm thực thi truy vấn.

**CTAS không phải công cụ sao chép nguyên vẹn lược đồ.** Trong PostgreSQL, khóa chính, khóa ngoại, `UNIQUE`, `CHECK`, `NOT NULL`, `DEFAULT`, identity, chỉ mục, trigger và các thuộc tính/quyền liên quan của bảng nguồn không tự được mang sang bảng đích CTAS. Khi cần các quy tắc đó, phải chủ động định nghĩa hoặc dùng cơ chế sao chép schema phù hợp rồi kiểm tra kết quả.

Trước khi quyết định cách tạo bảng, hãy tự hỏi: **“Mình muốn một bản chụp dữ liệu của truy vấn, một bảng rỗng có các cột kết quả, hay một đối tượng dữ liệu phải giữ đầy đủ ràng buộc và hành vi của lược đồ?”** Câu trả lời sẽ quyết định nên dùng `CREATE TABLE AS SELECT`, `WITH NO DATA`, `CREATE TABLE ... LIKE` hay `CREATE TABLE` tường minh kết hợp `INSERT ... SELECT`.
