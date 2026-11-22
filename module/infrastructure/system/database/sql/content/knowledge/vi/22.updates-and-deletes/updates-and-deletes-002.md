# Cập nhật nhiều cột và quy tắc đánh giá theo hệ quản trị

## 1. Vì sao thứ tự đánh giá trong UPDATE quan trọng?

Lệnh `UPDATE` thay đổi những hàng đã tồn tại trong bảng. Một câu lệnh có thể sửa nhiều cột:

~~~sql
UPDATE inventory_products
SET
    unit_price = 115.00,
    stock_qty = 8,
    product_status = 'ACTIVE'
WHERE product_id = 1;
~~~

Ví dụ này đơn giản vì mọi vế phải của `SET` là những giá trị độc lập. Câu hỏi khó hơn xuất hiện khi biểu thức gán **tham chiếu tới cột đang được sửa bởi một phép gán khác trong cùng câu UPDATE**:

~~~sql
UPDATE swap_demo
SET
    a = b,
    b = a
WHERE id = 1;
~~~

Nếu giá trị ban đầu là `a = 10`, `b = 20`, liệu kết quả có phải `a = 20`, `b = 10` không?

**Không có câu trả lời chung cho tất cả các hệ quản trị.** Trong PostgreSQL, các biểu thức vế phải của `SET` đọc giá trị hàng **trước khi cập nhật**, nên câu trên hoán đổi được. Với MySQL khi cập nhật **một bảng**, các phép gán thường được đánh giá **từ trái sang phải**, vì vậy câu trên thường cho `a = 20`, `b = 20`. MySQL với cập nhật **nhiều bảng** còn **không bảo đảm thứ tự đánh giá các phép gán** như khi cập nhật một bảng.

Đây là lý do một câu SQL chạy được nhưng vẫn có thể âm thầm làm sai dữ liệu khi chuyển DBMS.

Bài học thuộc module **Database SQL**, chương **Cập nhật và xóa**, tập trung vào các kỹ năng:

1. Viết `UPDATE ... SET` cập nhật nhiều cột trong một lệnh.
2. Hiểu giá trị cũ, giá trị mới và sự phụ thuộc chéo giữa các phép gán.
3. Phân biệt PostgreSQL, MySQL, SQL Server, SQLite và Oracle về cú pháp, cách cập nhật từ nguồn khác và các giới hạn.
4. Sử dụng `CASE`, `NULL`, `DEFAULT` và phép tính số học đúng cách.
5. Tránh cập nhật không xác định khi `UPDATE ... FROM` hoặc `UPDATE ... JOIN` khớp nhiều hàng nguồn.
6. Quản lý transaction, cập nhật đồng thời, ràng buộc, số hàng được sửa và lấy dữ liệu sau UPDATE.

## 2. Tạo dữ liệu mẫu

Các câu DDL và ví dụ chung dưới đây sử dụng **PostgreSQL**. Ví dụ dành cho DBMS khác sẽ được ghi nhãn rõ. Nên thực hành trên database riêng, không chạy tùy tiện trên dữ liệu thật.

### 2.1. Bảng sản phẩm

~~~sql
CREATE TABLE inventory_products (
    product_id     INTEGER PRIMARY KEY,
    sku            VARCHAR(30) NOT NULL UNIQUE,
    product_name   VARCHAR(100) NOT NULL,
    category_id    INTEGER NOT NULL,
    unit_price     NUMERIC(12, 2) NOT NULL,
    previous_price NUMERIC(12, 2),
    stock_qty      INTEGER NOT NULL,
    reorder_level  INTEGER NOT NULL,
    product_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    version_no     INTEGER NOT NULL DEFAULT 1,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_inventory_price CHECK (unit_price >= 0),
    CONSTRAINT chk_inventory_stock CHECK (stock_qty >= 0),
    CONSTRAINT chk_inventory_reorder CHECK (reorder_level >= 0),
    CONSTRAINT chk_inventory_version CHECK (version_no >= 1),
    CONSTRAINT chk_inventory_status CHECK (
        product_status IN (
            'ACTIVE', 'OUT_OF_STOCK', 'ARCHIVED'
        )
    )
);
~~~

Các cột cần lưu ý:

| Cột | Ý nghĩa |
| --- | --- |
| `product_id` | Khóa chính, dùng để cập nhật đúng sản phẩm |
| `unit_price` | Giá bán hiện tại, phải không âm |
| `previous_price` | Giá cũ được lưu lại; có thể là `NULL` |
| `stock_qty` | Tồn kho hiện tại, không âm |
| `reorder_level` | Ngưỡng cảnh báo nhập hàng |
| `product_status` | ACTIVE, OUT_OF_STOCK hoặc ARCHIVED |
| `version_no` | Số phiên bản dùng trong optimistic locking |
| `updated_at` | Thời gian cần được chủ động cập nhật trong các câu `UPDATE` |

Thêm năm sản phẩm:

~~~sql
INSERT INTO inventory_products (
    product_id, sku, product_name, category_id,
    unit_price, previous_price, stock_qty,
    reorder_level, product_status
)
VALUES
    (1, 'BK-01', 'So A',      10, 100.00, NULL,  5, 2, 'ACTIVE'),
    (2, 'BK-02', 'So B',      10, 200.00, NULL,  0, 3, 'OUT_OF_STOCK'),
    (3, 'PN-01', 'But A',     20,  50.00, NULL, 12, 5, 'ACTIVE'),
    (4, 'KB-01', 'Ban phim',  30, 800.00, NULL,  2, 2, 'ACTIVE'),
    (5, 'PN-02', 'But B',     20,  40.00, NULL,  1, 2, 'ARCHIVED');
~~~

| ID | SKU | Nhóm | Giá | Giá cũ | Tồn | Ngưỡng | Trạng thái |
| ---: | --- | ---: | ---: | --- | ---: | ---: | --- |
| 1 | BK-01 | 10 | 100.00 | NULL | 5 | 2 | ACTIVE |
| 2 | BK-02 | 10 | 200.00 | NULL | 0 | 3 | OUT_OF_STOCK |
| 3 | PN-01 | 20 | 50.00 | NULL | 12 | 5 | ACTIVE |
| 4 | KB-01 | 30 | 800.00 | NULL | 2 | 2 | ACTIVE |
| 5 | PN-02 | 20 | 40.00 | NULL | 1 | 2 | ARCHIVED |

### 2.2. Bảng quy tắc điều chỉnh giá

~~~sql
CREATE TABLE price_rules (
    category_id    INTEGER PRIMARY KEY,
    percent_change NUMERIC(7, 2) NOT NULL
);

INSERT INTO price_rules (category_id, percent_change)
VALUES
    (10,  10.00),
    (20, -10.00),
    (30,   5.00);
~~~

Phòng ban kinh doanh muốn tăng giá 10% cho nhóm 10, giảm giá 10% cho nhóm 20, và tăng 5% cho nhóm 30. Tương ứng:

~~~text
Nhóm 10: 100 → 110; 200 → 220
Nhóm 20:  50 →  45;  40 →  36
Nhóm 30: 800 → 840
~~~

Nhưng khi chỉ cập nhật `product_status = 'ACTIVE'`, các sản phẩm 2 và 5 sẽ **không đổi**. Khóa chính `price_rules.category_id` bảo đảm **tối đa một quy tắc** cho mỗi nhóm hàng.

### 2.3. Tránh làm thay đổi dữ liệu qua các ví dụ

Các phép UPDATE trong bài nên được thực hành **riêng biệt**. Với PostgreSQL, có thể bao quanh ví dụ bằng:

~~~sql
BEGIN;

UPDATE inventory_products
SET unit_price = 115.00
WHERE product_id = 1;

SELECT product_id, unit_price
FROM inventory_products
WHERE product_id = 1;

ROLLBACK;
~~~

Trong transaction, câu SELECT thấy giá thay đổi; sau ROLLBACK, dữ liệu bảng trở về trạng thái trước ví dụ nếu không có side effect ngoài giao dịch. Không dùng kỹ thuật này trên production khi chưa xét trigger, transaction, quyền và các hoạt động đồng thời. Mọi kết quả kỳ vọng ở bài học đều dựa trên **bảng mẫu ban đầu**, trừ khi có ghi chú khác.

## 3. Cú pháp SET nhiều cột

Cấu trúc cơ bản:

~~~sql
UPDATE ten_bang
SET
    cot_1 = bieu_thuc_1,
    cot_2 = bieu_thuc_2,
    cot_3 = bieu_thuc_3
WHERE dieu_kien_chon_hang;
~~~

Trong một câu lệnh:

- `UPDATE` xác định bảng đích.
- `SET` liệt kê những cột cần thay đổi và biểu thức giá trị mới.
- `WHERE` chọn **hàng** cần cập nhật, không chọn cột.
- Những cột **không có trong `SET`** thường giữ nguyên, ngoại trừ cơ chế tự sinh, trigger hoặc quy tắc schema liên quan.
- Mọi giá trị sau cập nhật phải thỏa `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` và ràng buộc khác.

### 3.1. Cập nhật nhiều hằng số độc lập

~~~sql
BEGIN;

UPDATE inventory_products
SET
    unit_price = 115.00,
    stock_qty = 8,
    product_status = 'ACTIVE',
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 1
RETURNING
    product_id, sku, unit_price,
    stock_qty, product_status, updated_at;

ROLLBACK;
~~~

Với sản phẩm 1, kết quả có `unit_price = 115`, `stock_qty = 8`, `product_status = 'ACTIVE'`. `RETURNING` là cú pháp PostgreSQL cho giá trị của hàng sau UPDATE. Thời gian cụ thể phụ thuộc thời điểm thực thi.

Không bắt buộc liệt kê các cột trong `SET` theo đúng thứ tự khai báo ở `CREATE TABLE`.

### 3.2. Biểu thức tự tham chiếu chính cột

~~~sql
BEGIN;

UPDATE inventory_products
SET
    stock_qty = stock_qty + 3,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 1
RETURNING product_id, stock_qty, version_no;

ROLLBACK;
~~~

Sản phẩm 1 ban đầu có `stock_qty = 5`, `version_no = 1`, nên kết quả là `8` và `2`. Hai phép gán này **tự tham chiếu chính cột** và không đọc cột đã được sửa bởi phép gán khác.

### 3.3. Không có WHERE có thể sửa toàn bảng

~~~sql
-- NGUY HIỂM: có thể sửa tất cả các hàng!
UPDATE inventory_products
SET
    product_status = 'ARCHIVED',
    stock_qty = 0;
~~~

Đây là cú pháp hợp lệ nếu dữ liệu mới không vi phạm constraint. Không có `WHERE`, DBMS có thể cập nhật toàn bộ bảng.

Trước khi sửa dữ liệu, có thể xem phạm vi:

~~~sql
SELECT
    product_id, sku, stock_qty, product_status
FROM inventory_products
WHERE category_id = 10
  AND product_status = 'ACTIVE';
~~~

Sau đó dùng **cùng điều kiện** trong UPDATE. Với thao tác có tác động lớn, cần transaction, backup hoặc kế hoạch khôi phục, và theo dõi số hàng thực sự được sửa.

## 4. Giá trị cũ và giá trị mới trong biểu thức SET

### 4.1. Ví dụ: lưu giá cũ rồi tăng giá

Sản phẩm 1 có giá cũ `100.00`. Muốn lưu `previous_price = 100.00` và đặt `unit_price = 110.00`:

~~~sql
BEGIN;

UPDATE inventory_products
SET
    previous_price = unit_price,
    unit_price = ROUND(unit_price * 1.10, 2)
WHERE product_id = 1
RETURNING
    product_id, previous_price, unit_price;

ROLLBACK;
~~~

Trong PostgreSQL, kết quả:

| product_id | previous_price | unit_price |
| ---: | ---: | ---: |
| 1 | 100.00 | 110.00 |

Tư duy logic:

~~~text
Hàng cũ:
    previous_price = NULL
    unit_price     = 100

Tính các biểu thức RHS từ hàng cũ:
    new_previous_price = old_unit_price
                       = 100
    new_unit_price     = ROUND(old_unit_price * 1.10, 2)
                       = 110

Hàng sau UPDATE:
    previous_price = 100
    unit_price     = 110
~~~

PostgreSQL không coi các phép gán trong một `SET` là những câu UPDATE nhỏ được chạy nối tiếp từ trên xuống; mọi RHS thông thường đọc dữ liệu **trước cập nhật** của hàng đó.

### 4.2. Phép hoán đổi hai cột trên PostgreSQL

Tạo bảng thử:

~~~sql
CREATE TABLE swap_demo (
    id INTEGER PRIMARY KEY,
    a INTEGER NOT NULL,
    b INTEGER NOT NULL
);

INSERT INTO swap_demo (id, a, b)
VALUES (1, 10, 20);
~~~

Thử hoán đổi:

~~~sql
BEGIN;

UPDATE swap_demo
SET
    a = b,
    b = a
WHERE id = 1
RETURNING a, b;

ROLLBACK;
~~~

Kết quả PostgreSQL:

~~~text
Trước: a = 10, b = 20
Sau:   a = 20, b = 10
~~~

Vế phải của `a = b` đọc `b` cũ (20), còn vế phải của `b = a` đọc `a` cũ (10).

PostgreSQL còn có cú pháp gán nhiều cột dưới dạng bộ:

~~~sql
BEGIN;

UPDATE swap_demo
SET (a, b) = (b, a)
WHERE id = 1
RETURNING a, b;

ROLLBACK;
~~~

Cú pháp này thể hiện ý định hoán đổi tường minh, nhưng không được mọi hệ quản trị hỗ trợ theo cùng dạng.

### 4.3. MySQL single-table UPDATE: gán trái sang phải trong nhiều trường hợp

Trong MySQL, tài liệu mô tả các phép gán trong **single-table UPDATE** thường được đánh giá **từ trái sang phải**. Vì vậy cùng câu:

~~~sql
-- MySQL single-table, với a = 10 và b = 20.
UPDATE swap_demo
SET
    a = b,
    b = a
WHERE id = 1;
~~~

thường có diễn tiến:

~~~text
a = b  → a trở thành 20
b = a  → b đọc a đã được gán, nên thành 20

Kết quả: a = 20, b = 20
~~~

Đây **không phải phép hoán đổi**.

Ví dụ thứ hai:

~~~sql
UPDATE swap_demo
SET
    a = a + 1,
    b = a
WHERE id = 1;
~~~

Nếu bắt đầu từ `(a,b) = (10,20)`:

| Hệ | a sau UPDATE | b sau UPDATE | Giải thích |
| --- | ---: | ---: | --- |
| PostgreSQL | 11 | 10 | `b = a` đọc `a` cũ |
| MySQL, cập nhật một bảng | Thường 11 | Thường 11 | `b = a` có thể đọc `a` mới |

Điểm mấu chốt là **không suy quy tắc PostgreSQL áp dụng cho MySQL**, và ngược lại.

### 4.4. MySQL UPDATE nhiều bảng có quy tắc khác

MySQL hỗ trợ dạng UPDATE có join hoặc cập nhật nhiều bảng:

~~~sql
UPDATE target_table AS t
JOIN source_table AS s
  ON s.key_id = t.key_id
SET
    t.col_1 = s.value_1,
    t.col_2 = s.value_2
WHERE ...;
~~~

Với **multiple-table UPDATE**, MySQL **không bảo đảm thứ tự đánh giá các phép gán**. Do đó không nên dựa vào việc viết `previous_price` trước `unit_price` sẽ chắc chắn lưu được giá cũ khi UPDATE dùng JOIN.

Ngay cả khi chỉ định sửa cột của một bảng đích, hãy xem cấu trúc UPDATE JOIN theo tài liệu MySQL thay vì mặc định áp dụng quy tắc của single-table `UPDATE table SET ... WHERE ...`.

### 4.5. Phân biệt thứ tự gán và thứ tự xử lý hàng

Hai khái niệm khác nhau:

- **Thứ tự các phép gán trong SET:** vế phải của cột này có nhìn thấy giá trị cột kia vừa đổi không?
- **Thứ tự các hàng được cập nhật:** hàng có ID nhỏ hay lớn được xử lý trước?

Một số dialect như MySQL có hỗ trợ `ORDER BY`/`LIMIT` trong dạng UPDATE một bảng ở những điều kiện nhất định. Chức năng đó **không phải một cách phổ quát** để kiểm soát ngữ nghĩa các biểu thức `SET` trên mọi DBMS.

Với SQL đa hệ, đừng dùng `ORDER BY` như một cách chữa phụ thuộc chéo trong `SET`.

## 5. Thiết kế khi cần giá trị cũ và mới

### 5.1. Trên PostgreSQL: dùng RHS của hàng cũ

~~~sql
BEGIN;

UPDATE inventory_products
SET
    previous_price = unit_price,
    unit_price = ROUND(unit_price * 1.10, 2),
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 1
RETURNING
    product_id, previous_price,
    unit_price, version_no;

ROLLBACK;
~~~

Giá trị kỳ vọng: `previous_price = 100`, `unit_price = 110` và `version_no = 2`.

Các biểu thức đều hợp lệ theo quy tắc đánh giá giá trị cũ của PostgreSQL.

### 5.2. Tránh phụ thuộc vào thứ tự gán khi chuyển nhiều DBMS

Nếu sản phẩm phải sửa trên PostgreSQL và MySQL, một chiến lược rõ ràng là:

1. Chọn và khóa hàng trong một transaction bằng cơ chế DBMS hỗ trợ, hoặc dùng kiểm tra phiên bản.
2. Đọc dữ liệu cũ một cách nhất quán.
3. Tính `new_price` và `old_price` từ snapshot đó.
4. Ghi một UPDATE với các giá trị **đã xác định** và điều kiện khóa/version.
5. Kiểm tra row count, sau đó commit hoặc rollback.

Ví dụ khái niệm trên PostgreSQL hoặc MySQL với transaction và `FOR UPDATE`:

~~~sql
BEGIN;

SELECT a, b
FROM swap_demo
WHERE id = 1
FOR UPDATE;

-- Giả sử đọc được old_a=10, old_b=20.
-- Ứng dụng bind các tham số old_b và old_a:
UPDATE swap_demo
SET a = 20, b = 10
WHERE id = 1;

COMMIT;
~~~

Trong ứng dụng thực, `20` và `10` là **tham số đã được đọc và tính từ transaction**, không phải hằng số cứng. SQL Server và SQLite có cú pháp/mô hình khóa riêng, không chép nguyên `FOR UPDATE` qua mọi engine.

Dùng snapshot nguồn riêng cũng đòi hỏi bảo đảm **mỗi hàng đích tương ứng tối đa một giá trị nguồn**, và kiểm soát cập nhật đồng thời giữa lúc đọc và lúc ghi.

### 5.3. Không dùng thủ thuật session variable mơ hồ

Các thủ thuật lưu giá trị cũ trong biến tùy ý ngay trong phép gán có thể dựa vào một thứ tự đánh giá không được bảo đảm, đặc biệt trong UPDATE JOIN. Khi sửa tiền/tồn kho, không đánh đổi tính đúng đắn lấy câu lệnh ngắn hơn. Dùng **transaction, source snapshot, row assignment được hỗ trợ, khóa hàng hoặc optimistic locking** theo đặc tính DBMS.

### 5.4. Một UPDATE nhiều cột khác hai UPDATE riêng biệt

~~~sql
-- Một câu UPDATE:
UPDATE inventory_products
SET
    unit_price = 120.00,
    stock_qty = 9
WHERE product_id = 1;
~~~

không hoàn toàn giống:

~~~sql
-- Hai câu lệnh riêng:
UPDATE inventory_products
SET unit_price = 120.00
WHERE product_id = 1;

UPDATE inventory_products
SET stock_qty = 9
WHERE product_id = 1;
~~~

Hai câu riêng có thể kích hoạt trigger hai lần, tạo trạng thái trung gian, có ranh giới lỗi/lock khác và có thể bị quan sát xen kẽ nếu không nằm trong transaction phù hợp. Một statement cập nhật nhiều cột thường diễn đạt rõ **một thay đổi logic thống nhất**. Nhưng transaction cũng không tự sửa **logic SET sai**.

## 6. Cập nhật nhiều cột bằng CASE

`CASE` cho phép chọn giá trị theo điều kiện trên hàng. Ví dụ cập nhật trạng thái theo tồn kho:

~~~sql
BEGIN;

UPDATE inventory_products
SET
    product_status = CASE
        WHEN product_status = 'ARCHIVED'
            THEN 'ARCHIVED'
        WHEN stock_qty = 0
            THEN 'OUT_OF_STOCK'
        ELSE 'ACTIVE'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id IN (1, 2, 3, 4, 5)
RETURNING product_id, stock_qty, product_status;

ROLLBACK;
~~~

Theo thứ tự nhánh:

- Nếu sản phẩm đã `ARCHIVED`, giữ nguyên ARCHIVED.
- Nếu không ARCHIVED và tồn bằng 0, chọn OUT_OF_STOCK.
- Ngược lại chọn ACTIVE.

Trong dữ liệu mẫu, `product_id = 2` là OUT_OF_STOCK, `5` vẫn ARCHIVED, và các sản phẩm 1, 3, 4 là ACTIVE.

**Thứ tự các nhánh WHEN có ý nghĩa riêng**: nếu kiểm tra `stock_qty=0` trước ARCHIVED thì một sản phẩm ARCHIVED với tồn 0 có thể bị chuyển sang OUT_OF_STOCK. Đây là thứ tự xét các điều kiện của `CASE`, khác với thứ tự các phép gán trong `SET`.

### 6.1. Dùng tồn sau cập nhật: lỗi phổ biến

Sản phẩm 4 có `stock_qty=2`. Bán 2 chiếc, mong muốn:

~~~text
stock_qty sau = 0
product_status sau = OUT_OF_STOCK
~~~

Câu PostgreSQL đúng:

~~~sql
BEGIN;

UPDATE inventory_products
SET
    stock_qty = stock_qty - 2,
    product_status = CASE
        WHEN stock_qty - 2 = 0 THEN 'OUT_OF_STOCK'
        ELSE 'ACTIVE'
    END,
    version_no = version_no + 1
WHERE product_id = 4
  AND stock_qty >= 2
RETURNING
    product_id, stock_qty, product_status, version_no;

ROLLBACK;
~~~

`CASE` dùng `stock_qty - 2` vì nó đọc **stock_qty cũ**, rồi tự tính lượng tồn dự kiến **sau khi bán**.

Câu dễ viết sai trong PostgreSQL:

~~~sql
-- Không đúng mục tiêu trên PostgreSQL:
UPDATE inventory_products
SET
    stock_qty = stock_qty - 2,
    product_status = CASE
        WHEN stock_qty = 0 THEN 'OUT_OF_STOCK'
        ELSE 'ACTIVE'
    END
WHERE product_id = 4
  AND stock_qty >= 2;
~~~

`CASE` đọc `stock_qty=2` nên cho ACTIVE, dù kết quả tồn là 0. Khi chuyển câu lệnh này sang MySQL single-table, việc đọc giá trị mới/cũ có thể khác theo thứ tự gán; không coi một cách viết phụ thuộc chéo là SQL khả chuyển.

### 6.2. Tính giá trị mới ở một nguồn rồi sử dụng lại

Trên PostgreSQL có thể viết rõ `new_stock`:

~~~sql
BEGIN;

WITH computed AS (
    SELECT
        product_id,
        stock_qty - 2 AS new_stock
    FROM inventory_products
    WHERE product_id = 4
      AND stock_qty >= 2
)
UPDATE inventory_products AS p
SET
    stock_qty = c.new_stock,
    product_status = CASE
        WHEN c.new_stock = 0 THEN 'OUT_OF_STOCK'
        ELSE 'ACTIVE'
    END,
    version_no = p.version_no + 1
FROM computed AS c
WHERE p.product_id = c.product_id
RETURNING
    p.product_id, p.stock_qty, p.product_status;

ROLLBACK;
~~~

Hai phép gán đọc cùng **cột nguồn `c.new_stock`**. Cách viết này mô tả rõ mục đích, nhưng cú pháp `WITH ... UPDATE ... FROM` và cách đọc hàng đích từ CTE không tự giống nhau ở mọi DBMS. Khi có ghi đồng thời, vẫn phải xét transaction/isolation thích hợp.

## 7. NULL, DEFAULT và constraint trong UPDATE

### 7.1. Gán NULL

`previous_price` cho phép `NULL`:

~~~sql
BEGIN;

UPDATE inventory_products
SET
    previous_price = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 1
RETURNING product_id, previous_price;

ROLLBACK;
~~~

Đây là thao tác hợp lệ. Nhưng `unit_price` và `stock_qty` được khai báo `NOT NULL`:

~~~sql
-- Lỗi NOT NULL:
UPDATE inventory_products
SET
    unit_price = NULL,
    stock_qty = 0
WHERE product_id = 1;
~~~

Trong DBMS có statement atomicity theo giao dịch, việc một phép gán vi phạm constraint thường làm **cả câu UPDATE thất bại**, không phải chỉ bỏ qua cột bị lỗi rồi tiếp tục sửa cột khác.

### 7.2. SET col = DEFAULT

~~~sql
BEGIN;

UPDATE inventory_products
SET
    product_status = DEFAULT,
    version_no = version_no + 1
WHERE product_id = 2
RETURNING product_id, product_status, version_no;

ROLLBACK;
~~~

Trong schema mẫu, `product_status DEFAULT 'ACTIVE'`. Vì vậy sản phẩm 2 đang OUT_OF_STOCK có thể được đặt về ACTIVE, dù `stock_qty=0`. Lệnh có thể hợp lệ theo constraint hiện tại nhưng **sai nghiệp vụ**. `DEFAULT` chỉ là biểu thức mặc định của schema, không phải “trạng thái nên có sau mọi loại cập nhật”.

Khi `UPDATE` **không liệt kê cột** trong SET, cột đó thường **giữ nguyên giá trị cũ**. Nó không tự dùng DEFAULT như khi `INSERT` bỏ qua cột.

### 7.3. COALESCE và giá trị thiếu

~~~sql
UPDATE inventory_products
SET previous_price = COALESCE(previous_price, unit_price)
WHERE product_id = 1;
~~~

`COALESCE` dùng `previous_price` nếu khác `NULL`, nếu không thì dùng `unit_price`. Đây là một phép tính dựa trên dữ liệu hàng, **không phải** cơ chế áp dụng giá trị `DEFAULT` của schema.

### 7.4. So sánh với NULL trong WHERE

~~~sql
-- Sai mục tiêu: previous_price = NULL không TRUE.
UPDATE inventory_products
SET previous_price = 0
WHERE previous_price = NULL;
~~~

Viết:

~~~sql
BEGIN;

UPDATE inventory_products
SET previous_price = 0
WHERE previous_price IS NULL
RETURNING product_id, previous_price;

ROLLBACK;
~~~

Với dữ liệu ban đầu, cả năm hàng có `previous_price IS NULL`. Việc gán 0 chỉ phục vụ minh họa; một giá chưa biết không tự có nghĩa là giá bằng 0.

### 7.5. CHECK vẫn áp dụng cho giá trị sau UPDATE

Sản phẩm 4 có tồn 2. Câu sau định ghi tồn −1:

~~~sql
-- Vi phạm CHECK stock_qty >= 0.
UPDATE inventory_products
SET
    stock_qty = stock_qty - 3,
    product_status = 'OUT_OF_STOCK'
WHERE product_id = 4;
~~~

Một điều kiện bảo vệ:

~~~sql
UPDATE inventory_products
SET
    stock_qty = stock_qty - 2,
    version_no = version_no + 1
WHERE product_id = 4
  AND stock_qty >= 2;
~~~

Nếu không đủ tồn, câu lệnh cập nhật **0 hàng**. Ứng dụng phải kiểm tra kết quả và xử lý nghiệp vụ “không đủ hàng” thay vì tự coi việc chạy SQL không báo lỗi là bán hàng thành công.

## 8. UPDATE nhiều cột từ bảng khác trên PostgreSQL

Khi giá trị mới nằm trong bảng nguồn, PostgreSQL hỗ trợ `UPDATE ... FROM`:

~~~sql
UPDATE target_table AS t
SET
    col_1 = source.expression_1,
    col_2 = source.expression_2
FROM source_table AS source
WHERE t.key_id = source.key_id
  AND dieu_kien_khac;
~~~

### 8.1. Điều chỉnh giá theo nhóm hàng

~~~sql
BEGIN;

UPDATE inventory_products AS p
SET
    previous_price = p.unit_price,
    unit_price = ROUND(
        p.unit_price * (1 + r.percent_change / 100.0),
        2
    ),
    version_no = p.version_no + 1,
    updated_at = CURRENT_TIMESTAMP
FROM price_rules AS r
WHERE p.category_id = r.category_id
  AND p.product_status = 'ACTIVE'
RETURNING
    p.product_id,
    p.sku,
    p.previous_price,
    p.unit_price,
    p.version_no;

ROLLBACK;
~~~

Kết quả trên bảng gốc:

| ID | SKU | Giá cũ được lưu | Giá mới | Version mới |
| ---: | --- | ---: | ---: | ---: |
| 1 | BK-01 | 100.00 | 110.00 | 2 |
| 3 | PN-01 | 50.00 | 45.00 | 2 |
| 4 | KB-01 | 800.00 | 840.00 | 2 |

Sản phẩm 2 và 5 không thay đổi vì không ACTIVE.

Các điều kiện bảo đảm ý nghĩa:

- `p.category_id = r.category_id` nối sản phẩm với quy tắc giá của nhóm.
- `p.product_status = 'ACTIVE'` giới hạn hàng đích.
- `price_rules.category_id PRIMARY KEY` bảo đảm mỗi hàng đích khớp **tối đa một quy tắc**.
- Trên PostgreSQL, cả `p.unit_price` trong phép gán `previous_price` và trong công thức tính giá đều đọc **giá cũ**.

**Lưu ý PostgreSQL:** ở vế trái của SET, không viết `SET p.unit_price = ...`. Tên cột đích thường để **không có tiền tố alias** như `SET unit_price = ...`; RHS và WHERE có thể tham chiếu `p.unit_price`.

### 8.2. Nguồn có nhiều hàng khớp: không thể tùy ý chọn

Tạo bảng khuyến mãi:

~~~sql
CREATE TABLE category_promotions (
    promotion_id   INTEGER PRIMARY KEY,
    category_id    INTEGER NOT NULL,
    percent_change NUMERIC(7, 2) NOT NULL
);

INSERT INTO category_promotions (
    promotion_id, category_id, percent_change
)
VALUES
    (1, 10, -5.00),
    (2, 10, -8.00);
~~~

Với một sản phẩm nhóm 10, câu sau khớp **hai hàng khuyến mãi**:

~~~sql
-- KHÔNG AN TOÀN về ngữ nghĩa:
UPDATE inventory_products AS p
SET unit_price = ROUND(
    p.unit_price * (1 + cp.percent_change / 100.0),
    2
)
FROM category_promotions AS cp
WHERE p.category_id = cp.category_id;
~~~

PostgreSQL không cam kết hàng nguồn nào được chọn khi nhiều hàng cùng khớp một hàng đích. Không thể khẳng định nó sẽ giảm 5% hay 8%. Một số DBMS khác có quy tắc hoặc lỗi khác trong tình huống tương tự; không dựa vào kết quả ngẫu nhiên của join.

### 8.3. Cách xác định nguồn đơn trị bằng GROUP BY

Giả sử chính sách là “dùng mức giảm sâu nhất”, ta chọn `MIN(percent_change)` cho mỗi nhóm:

~~~sql
BEGIN;

WITH chosen_promotion AS (
    SELECT
        category_id,
        MIN(percent_change) AS selected_percent
    FROM category_promotions
    GROUP BY category_id
)
UPDATE inventory_products AS p
SET
    previous_price = p.unit_price,
    unit_price = ROUND(
        p.unit_price * (1 + cp.selected_percent / 100.0),
        2
    )
FROM chosen_promotion AS cp
WHERE p.category_id = cp.category_id
  AND p.product_status = 'ACTIVE'
RETURNING
    p.product_id, p.previous_price, p.unit_price;

ROLLBACK;
~~~

Nhóm 10 chọn `MIN(-5,-8) = -8`, vì vậy sản phẩm 1 giảm từ `100` còn `92`.

`GROUP BY category_id` giúp tạo **một hàng nguồn mỗi nhóm**. Tuy nhiên `MIN` chỉ đúng vì ta đã **định nghĩa quy tắc nghiệp vụ** “giảm sâu nhất”. Nếu chính sách dùng ngày hiệu lực hoặc độ ưu tiên, phải chọn theo tiêu chí đó.

### 8.4. Cách chọn một hàng nguồn bằng ROW_NUMBER

~~~sql
WITH ranked_promotions AS (
    SELECT
        promotion_id,
        category_id,
        percent_change,
        ROW_NUMBER() OVER (
            PARTITION BY category_id
            ORDER BY percent_change ASC, promotion_id ASC
        ) AS rn
    FROM category_promotions
),
chosen_promotion AS (
    SELECT category_id, percent_change
    FROM ranked_promotions
    WHERE rn = 1
)
UPDATE inventory_products AS p
SET unit_price = ROUND(
    p.unit_price * (1 + cp.percent_change / 100.0),
    2
)
FROM chosen_promotion AS cp
WHERE p.category_id = cp.category_id
  AND p.product_status = 'ACTIVE';
~~~

Đây là ví dụ chọn “mức thay đổi nhỏ nhất, hòa thì promotion ID nhỏ nhất”. `rn = 1` bảo đảm mỗi nhóm có tối đa một hàng nguồn. Hãy đảm bảo cách phá hòa đúng nghiệp vụ, không dùng `ROW_NUMBER` chỉ để che đi lỗi dữ liệu trùng.

## 9. UPDATE FROM khác scalar subquery như thế nào?

### 9.1. UPDATE FROM chỉ sửa hàng khớp nguồn

Trong câu PostgreSQL:

~~~sql
UPDATE inventory_products AS p
SET unit_price = ROUND(
    p.unit_price * (1 + r.percent_change / 100.0),
    2
)
FROM price_rules AS r
WHERE p.category_id = r.category_id;
~~~

một hàng sản phẩm không có `category_id` trong `price_rules` **không khớp join**, nên thường không được cập nhật.

### 9.2. Scalar subquery có thể trả 0 hoặc nhiều hàng

Một dạng khác:

~~~sql
BEGIN;

UPDATE inventory_products AS p
SET unit_price = (
    SELECT ROUND(
        p.unit_price * (1 + r.percent_change / 100.0),
        2
    )
    FROM price_rules AS r
    WHERE r.category_id = p.category_id
)
WHERE p.product_id = 1
RETURNING product_id, unit_price;

ROLLBACK;
~~~

Vì nhóm 10 có đúng một quy tắc, kết quả là 110.

Nhưng nếu subquery trả **0 hàng**, biểu thức scalar thường nhận `NULL`; gán vào `unit_price NOT NULL` sẽ bị từ chối. Nếu trả **nhiều hơn một hàng**, nhiều DBMS báo lỗi subquery trả nhiều hàng, thay vì chọn một giá trị bất kỳ.

Một cách PostgreSQL có thêm kiểm tra tồn tại:

~~~sql
BEGIN;

UPDATE inventory_products AS p
SET unit_price = (
    SELECT ROUND(
        p.unit_price * (1 + r.percent_change / 100.0),
        2
    )
    FROM price_rules AS r
    WHERE r.category_id = p.category_id
)
WHERE p.product_status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM price_rules AS r
      WHERE r.category_id = p.category_id
  )
RETURNING product_id, unit_price;

ROLLBACK;
~~~

`EXISTS` giúp chỉ chọn hàng có nguồn phù hợp. `PRIMARY KEY` ở `price_rules.category_id` bảo đảm truy vấn con trả tối đa một giá trị.

### 9.3. Gán nhiều cột từ một row subquery

Trên PostgreSQL có thể dùng:

~~~sql
BEGIN;

UPDATE inventory_products AS p
SET (previous_price, unit_price) = (
    SELECT
        p.unit_price,
        ROUND(
            p.unit_price * (1 + r.percent_change / 100.0),
            2
        )
    FROM price_rules AS r
    WHERE r.category_id = p.category_id
)
WHERE p.product_id = 1
RETURNING product_id, previous_price, unit_price;

ROLLBACK;
~~~

Vế trái có hai cột; subquery trả hai biểu thức tương ứng và **tối đa một hàng**. Kết quả là giá cũ 100 và giá mới 110.

Không tự coi dạng `SET (a,b) = (SELECT ...)` khả dụng y hệt trong MySQL, SQL Server hay mọi phiên bản DBMS. Khi viết SQL đa hệ, nên tách cách biểu diễn theo dialect.

## 10. So sánh cú pháp theo hệ quản trị

### 10.1. PostgreSQL

~~~sql
UPDATE inventory_products AS p
SET
    previous_price = p.unit_price,
    unit_price = ROUND(
        p.unit_price * (1 + r.percent_change / 100.0),
        2
    )
FROM price_rules AS r
WHERE p.category_id = r.category_id
  AND p.product_status = 'ACTIVE'
RETURNING
    p.product_id,
    p.previous_price,
    p.unit_price;
~~~

Điểm chính:

- Có `UPDATE ... FROM`.
- RHS của SET đọc hàng trước UPDATE, giúp lưu giá cũ.
- Cột đích trong SET không dùng tiền tố alias.
- `RETURNING` cho phép lấy giá trị của hàng sau UPDATE.
- Khi một hàng đích khớp nhiều hàng nguồn, lựa chọn giá trị nguồn **không nên được coi là xác định**.

### 10.2. MySQL

MySQL dùng cú pháp `UPDATE ... JOIN ... SET ...`:

~~~sql
-- MySQL: chỉ thay đổi một cột để tránh phụ thuộc chéo.
UPDATE inventory_products AS p
JOIN price_rules AS r
  ON r.category_id = p.category_id
SET p.unit_price = ROUND(
    p.unit_price * (1 + r.percent_change / 100.0),
    2
)
WHERE p.product_status = 'ACTIVE';
~~~

Điểm chính:

- `UPDATE` một bảng thường đánh giá phép gán trái sang phải.
- Dạng multiple-table UPDATE không bảo đảm thứ tự các phép gán.
- Không giả định `UPDATE JOIN` vừa sửa `previous_price` vừa sửa `unit_price` sẽ có kết quả của PostgreSQL.
- Nếu cần giữ giá trước và sau, thiết kế snapshot có khóa/transaction hoặc bước trung gian rõ ràng.
- MySQL có những cú pháp `ORDER BY`/`LIMIT` với single-table UPDATE tùy điều kiện, nhưng không mang nguyên chúng sang các DBMS khác.

### 10.3. SQL Server

Trong T-SQL có thể dùng:

~~~sql
-- SQL Server:
UPDATE p
SET
    previous_price = p.unit_price,
    unit_price = ROUND(
        p.unit_price * (1 + r.percent_change / 100.0),
        2
    )
FROM dbo.inventory_products AS p
JOIN dbo.price_rules AS r
  ON r.category_id = p.category_id
WHERE p.product_status = 'ACTIVE';
~~~

Khác PostgreSQL:

- Dạng `UPDATE alias ... FROM ... JOIN` đặc trưng T-SQL.
- `OUTPUT INSERTED...` và `OUTPUT DELETED...` có thể cho biết giá mới/cũ.
- Nguồn join có nhiều khớp có thể khiến kết quả cập nhật **không xác định**; phải đảm bảo nguồn đơn trị.
- Các hạn chế về target, trigger, hint, locking và expression khác theo SQL Server.

### 10.4. SQLite

SQLite hỗ trợ `UPDATE ... FROM` từ phiên bản **3.33.0**:

~~~sql
-- SQLite phiên bản hỗ trợ UPDATE FROM:
UPDATE inventory_products AS p
SET unit_price = ROUND(
    p.unit_price * (1 + r.percent_change / 100.0),
    2
)
FROM price_rules AS r
WHERE p.category_id = r.category_id
  AND p.product_status = 'ACTIVE';
~~~

SQLite thường đánh giá các biểu thức SET dựa trên giá trị trước khi ghi hàng, nhưng chi tiết version/feature và kiểu số khác với PostgreSQL. SQLite có hành vi riêng khi `UPDATE FROM` khớp nhiều hàng nguồn: không được phụ thuộc vào hàng bất kỳ được chọn. Dùng khóa duy nhất hoặc tập nguồn đã được chuẩn hóa.

### 10.5. Oracle

Trên các phiên bản Oracle truyền thống, có thể dùng scalar subquery và `EXISTS`:

~~~sql
-- Ý tưởng Oracle:
UPDATE inventory_products p
SET p.unit_price = (
    SELECT ROUND(
        p.unit_price * (1 + r.percent_change / 100),
        2
    )
    FROM price_rules r
    WHERE r.category_id = p.category_id
)
WHERE p.product_status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM price_rules r
      WHERE r.category_id = p.category_id
  );
~~~

Oracle cũng có `MERGE` để thực hiện cập nhật từ nguồn khác, với các điều kiện về một hàng đích khớp nguồn. Một số phiên bản Oracle mới bổ sung các dạng `UPDATE ... FROM`; không giả định mọi phiên bản có cùng cú pháp PostgreSQL. Kiểm tra Oracle Database đích trước khi chuyển câu SQL.

### 10.6. MariaDB

MariaDB có cú pháp và tính năng tương đồng với một phần hệ sinh thái MySQL, nhưng không được coi hoàn toàn giống MySQL về các chi tiết cập nhật nhiều cột và thứ tự đánh giá. Khi cần dựa vào hành vi cụ thể của multi-table UPDATE, phải kiểm tra tài liệu và phiên bản MariaDB đang triển khai.

### Bảng tổng hợp

| Hệ quản trị | Cập nhật từ bảng khác | Điều cần kiểm tra |
| --- | --- | --- |
| PostgreSQL | `UPDATE ... SET ... FROM ... WHERE ...` | RHS giá trị cũ; không gắn alias cột đích SET; source phải đơn trị |
| MySQL | `UPDATE ... JOIN ... SET ... WHERE ...` | Single-table thường trái→phải; multiple-table không bảo đảm thứ tự gán |
| SQL Server | `UPDATE alias SET ... FROM target JOIN source ...` | Nguồn nhiều khớp gây kết quả không xác định; OUTPUT old/new |
| SQLite 3.33.0+ | `UPDATE ... FROM` | Hành vi nguồn trùng, kiểu dữ liệu và phiên bản |
| Oracle | Scalar subquery/MERGE; cú pháp bổ sung theo phiên bản | Đảm bảo số hàng nguồn, cú pháp riêng |
| MariaDB | UPDATE và JOIN theo dialect MariaDB | Phiên bản, thứ tự gán và tính năng khác MySQL |

## 11. Trigger, generated column và ảnh hưởng phụ

### 11.1. Trigger có thể thay đổi giá trị cuối

Một `BEFORE UPDATE` trigger có thể chuẩn hóa `product_status` hoặc tự đặt `updated_at`. Vì vậy giá trị lưu có thể khác với những gì tác giả `SET` trực tiếp dự đoán nếu có trigger hoặc cơ chế xử lý khác.

Phải phân biệt:

- **Ngữ nghĩa biểu thức SET** (các RHS được đánh giá từ nguồn nào);
- **Thực thi trigger** và thứ tự xử lý của engine;
- **Kiểm tra constraint**;
- **Giá trị thực sự được ghi** và trả về.

Không suy từ ví dụ “PostgreSQL RHS dùng giá trị cũ” rằng mọi trigger hoặc generated column cũng luôn nhìn cùng một phiên bản của hàng ở mọi giai đoạn.

### 11.2. Cột generated/computed không phải cột SET thường

Giả sử có:

~~~sql
-- Cột tính toán trong bảng minh họa invoice_lines:
line_total NUMERIC(14, 2)
    GENERATED ALWAYS AS (quantity * unit_price) STORED
~~~

Không tự ý gán một giá trị tùy chọn vào `line_total` nếu DBMS đã định nghĩa nó là generated ALWAYS. Thay vào đó, cập nhật các cột đầu vào:

~~~sql
-- Giả định bảng invoice_lines đã tồn tại.
UPDATE invoice_lines
SET
    quantity = 3,
    unit_price = 15000.00
WHERE line_id = 1;
~~~

DBMS tính lại `line_total` theo định nghĩa schema. Bảng `invoice_lines` chỉ là ví dụ khái niệm, **không nằm trong schema mẫu đã tạo**. Cú pháp generated columns và khả năng cập nhật chúng khác nhau theo hệ quản trị.

### 11.3. DEFAULT trên updated_at không tự chạy mỗi lần UPDATE

`updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP` có default **khi thêm hàng**. Nếu muốn ghi thời điểm sửa:

~~~sql
UPDATE inventory_products
SET
    unit_price = 125.00,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 1;
~~~

Đừng giả định chỉ vì đã khai báo DEFAULT mà `updated_at` tự đổi mỗi lần UPDATE. Một số hệ dùng trigger hoặc thuộc tính riêng để làm việc đó. `CURRENT_TIMESTAMP` cũng có quy tắc thời điểm đánh giá khác nhau theo DBMS, transaction và kiểu dữ liệu.

## 12. Cập nhật đồng thời và tránh mất dữ liệu

### 12.1. Lost update từ ứng dụng

Giả sử sản phẩm 1 tồn 5:

~~~text
Ứng dụng A đọc stock_qty=5; bán 2 → định ghi 3.
Ứng dụng B cũng đọc stock_qty=5; bán 1 → định ghi 4.

Nếu A ghi 3 rồi B ghi 4 từ dữ liệu đã cũ,
kết quả cuối là 4 thay vì 2.
~~~

Đây là dạng **lost update** do tính ở client trên snapshot cũ rồi ghi đè mà không có bảo vệ.

### 12.2. Cập nhật tương đối với điều kiện

~~~sql
UPDATE inventory_products
SET
    stock_qty = stock_qty - 2,
    version_no = version_no + 1
WHERE product_id = 1
  AND stock_qty >= 2;
~~~

Việc tính `stock_qty - 2` ngay trong `UPDATE` và kiểm tra tồn có thể giảm rủi ro ghi đè giá trị tính từ client đã cũ, theo cơ chế transaction/locking của DBMS. Nhưng ứng dụng vẫn phải kiểm tra **0 hàng được sửa** và xử lý tranh chấp.

### 12.3. Optimistic locking bằng version

Nếu client đã đọc sản phẩm 1 ở `version_no=1`:

~~~sql
UPDATE inventory_products
SET
    unit_price = 115.00,
    stock_qty = 8,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 1
  AND version_no = 1;
~~~

Nếu `version_no` đã thay đổi hoặc hàng không còn tồn tại, điều kiện sẽ không khớp. Ứng dụng cần phát hiện trường hợp này và yêu cầu đọc lại/giải quyết xung đột, thay vì thầm ghi đè.

### 12.4. Pessimistic locking

Trong PostgreSQL hoặc MySQL với engine transactional hỗ trợ:

~~~sql
BEGIN;

SELECT
    product_id, stock_qty, version_no
FROM inventory_products
WHERE product_id = 1
FOR UPDATE;

-- Kiểm tra dữ liệu và UPDATE trong cùng transaction.

COMMIT;
~~~

`FOR UPDATE` khóa hàng theo cơ chế DBMS. SQL Server và SQLite có cách thực hiện tương ứng khác. Không tự giả định cùng cú pháp, mức cô lập hoặc khả năng ngăn mọi race condition ở mọi hệ.

Transaction giúp bảo đảm nhóm thay đổi và xử lý đồng thời; nó **không chữa được lỗi hiểu nhầm thứ tự gán trong SET**. Một câu UPDATE với biểu thức sai vẫn có thể commit hoàn toàn thành công nhưng lưu dữ liệu sai nghiệp vụ.

## 13. Lấy kết quả cũ/mới sau UPDATE

### 13.1. PostgreSQL RETURNING

~~~sql
BEGIN;

UPDATE inventory_products
SET
    previous_price = unit_price,
    unit_price = ROUND(unit_price * 1.10, 2)
WHERE product_id = 1
RETURNING
    product_id, previous_price, unit_price;

ROLLBACK;
~~~

Kết quả gồm `previous_price=100` và `unit_price=110`. `RETURNING` trong mẫu này trả **các giá trị sau UPDATE**; `previous_price` chứa giá cũ do ta vừa gán vào. Không suy rằng mọi phiên bản PostgreSQL đều có cùng cú pháp độc lập để truy cập cả hai trạng thái old/new của mọi cột.

### 13.2. SQL Server OUTPUT INSERTED và DELETED

T-SQL có cơ chế nhận giá trị trước và sau DML:

~~~sql
-- SQL Server:
UPDATE dbo.inventory_products
SET unit_price = unit_price * 1.10
OUTPUT
    DELETED.product_id,
    DELETED.unit_price AS old_price,
    INSERTED.unit_price AS new_price
WHERE product_id = 1;
~~~

`DELETED.unit_price` đại diện giá trị trước UPDATE và `INSERTED.unit_price` đại diện giá trị sau UPDATE theo quy tắc `OUTPUT`. Có các giới hạn riêng với trigger/`OUTPUT INTO` và những trường hợp DML khác.

### 13.3. JDBC và số hàng bị tác động

~~~java
String sql = """
    UPDATE inventory_products
    SET unit_price = ?,
        stock_qty = ?,
        version_no = version_no + 1
    WHERE product_id = ?
      AND version_no = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new java.math.BigDecimal("115.00"));
    ps.setInt(2, 8);
    ps.setInt(3, 1);
    ps.setInt(4, 1);

    int affected = ps.executeUpdate();

    if (affected != 1) {
        throw new IllegalStateException(
            "Khong tim thay hang hoac version da thay doi"
        );
    }
}
~~~

Khi cập nhật theo khóa chính và version, kỳ vọng là **đúng một hàng**. Tùy DBMS/driver, số hàng báo về có thể liên quan tới **hàng khớp** hoặc **hàng thật sự thay đổi**, cùng các chi tiết cấu hình/trigger. Không diễn giải row count như “số cột được sửa”.

Câu SQL có thể hợp lệ nhưng ảnh hưởng 0 hàng; ứng dụng vẫn phải xử lý trường hợp không tìm thấy/xung đột. Trong ứng dụng có transaction tự quản, cần xử lý commit/rollback ở tầng kết nối.

## 14. Hiệu năng và an toàn khi UPDATE nhiều cột

### 14.1. Xác định phạm vi từ WHERE

~~~sql
BEGIN;

UPDATE inventory_products
SET
    unit_price = ROUND(unit_price * 1.05, 2),
    version_no = version_no + 1
WHERE category_id = 10
  AND product_status = 'ACTIVE'
RETURNING product_id, unit_price;

ROLLBACK;
~~~

Với dữ liệu mẫu, chỉ sản phẩm 1 thuộc nhóm 10 và ACTIVE. Sản phẩm 2 cùng nhóm nhưng OUT_OF_STOCK nên không cập nhật.

Nếu bỏ điều kiện trạng thái, phạm vi thay đổi. Không xem điều kiện `WHERE` là chi tiết chỉ nhằm tăng tốc: nó định nghĩa **đối tượng được phép sửa**.

### 14.2. Chỉ mục và chi phí ghi

Chỉ mục ứng viên cho bảng lớn:

~~~sql
CREATE INDEX idx_inventory_category_status
ON inventory_products (category_id, product_status);
~~~

Chỉ mục có thể hỗ trợ tìm hàng theo điều kiện của `UPDATE`. Nhưng:

- Trên bảng năm hàng, DBMS có thể chọn quét bảng.
- UPDATE nhiều cột được lập index làm tăng chi phí duy trì index.
- Mức chọn lọc, phân phối dữ liệu, số hàng và transaction ảnh hưởng hiệu năng.

Không tạo hàng loạt index chỉ dựa vào một câu SQL ví dụ. Kiểm tra execution plan và workload thực.

### 14.3. EXPLAIN và cảnh báo ANALYZE

Trong PostgreSQL:

~~~sql
EXPLAIN
UPDATE inventory_products
SET unit_price = ROUND(unit_price * 1.05, 2)
WHERE product_id = 1;
~~~

`EXPLAIN` cho kế hoạch dự kiến; `EXPLAIN ANALYZE` **thực sự chạy câu UPDATE**. Không chạy `EXPLAIN ANALYZE UPDATE` trên production mà không có biện pháp bảo vệ dữ liệu và kiểm soát transaction.

Với `UPDATE ... FROM`, xem đặc biệt số hàng join và sự **duy nhất của nguồn**. Nếu source có nhiều khớp cho một hàng đích, đó trước hết là **lỗi ngữ nghĩa**, không chỉ vấn đề tối ưu.

### 14.4. Cập nhật theo lô

Cập nhật hàng triệu hàng có thể giữ lock lâu, sinh log và tranh chấp. Chia batch đôi khi hữu ích nhưng cần:

- Chọn phạm vi bằng khóa ổn định;
- Kiểm soát transaction và retry;
- Không bỏ hoặc cập nhật lặp do dữ liệu thay đổi giữa batch;
- Bảo đảm mỗi batch xử lý cùng một quy tắc nguồn;
- Không giả định mọi DBMS hỗ trợ `ORDER BY`/`LIMIT` trong UPDATE.

Thứ tự hàng được sửa không phải thứ tự đánh giá những phép gán trong SET.

### 14.5. Bảo vệ đầu vào và tên cột

Trong JDBC, dùng prepared statements:

~~~java
String sql = """
    UPDATE inventory_products
    SET unit_price = ?,
        product_status = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE product_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new java.math.BigDecimal("125.00"));
    ps.setString(2, "ACTIVE");
    ps.setInt(3, 1);
    ps.executeUpdate();
}
~~~

Không nối trực tiếp input người dùng thành `SET col = ... WHERE id = ...`. Nếu API cho phép chọn động cột muốn sửa, hãy dùng **danh sách tên cột được cho phép (whitelist)** và vẫn bind giá trị bằng placeholder. Placeholder đại diện **giá trị**, không tự biến thành tên cột hoặc cú pháp SQL.

Trong API PATCH, thuộc tính **không gửi** có thể nghĩa là “không sửa cột”, trong khi thuộc tính có `null` có thể nghĩa là “gán NULL”. Đây là hợp đồng API cần xác định rõ; `UPDATE` không tự biết ý định người dùng.

## 15. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “`SET a=b, b=a` luôn hoán đổi.” | MySQL single-table thường cho (b,b) | Hiểu quy tắc của DBMS, dùng snapshot khi cần |
| “Mọi RHS đều đọc giá trị mới.” | Sai trên PostgreSQL | PostgreSQL dùng hàng cũ trong RHS |
| “Mọi RHS đều đọc giá trị cũ.” | Sai với MySQL single-table có phụ thuộc chéo | Không dựa vào cùng hành vi đa hệ |
| Dùng thứ tự gán MySQL single-table cho UPDATE JOIN | MySQL multiple-table không bảo đảm thứ tự | Tách nguồn giá trị cũ và mới |
| Quên WHERE | Có thể sửa toàn bộ bảng | Preview bằng SELECT, kiểm tra affected rows |
| CASE đọc tồn cũ nhưng tưởng tồn mới | Trạng thái sai sau khi bán | Tính rõ `stock_qty - quantity` |
| Hai nguồn cùng khớp một hàng ở UPDATE FROM | Chọn giá trị không xác định | UNIQUE/GROUP BY/ROW_NUMBER có tiêu chí |
| Scalar subquery trả 0 hàng | Gán NULL hoặc lỗi NOT NULL | EXISTS hoặc đảm bảo nguồn khớp |
| Scalar subquery trả nhiều hàng | Lỗi hoặc không xác định theo dạng cú pháp | Ràng buộc số hàng nguồn |
| `= NULL` trong WHERE | Không tìm được hàng NULL | `IS NULL` |
| Dùng SET DEFAULT tưởng là trạng thái nghiệp vụ đúng | Có thể ACTIVE dù tồn 0 | Kiểm tra quy tắc nghiệp vụ |
| UPDATE bỏ cột sẽ lấy DEFAULT như INSERT | Cột cũ thường giữ nguyên | Ghi `SET col = DEFAULT` nếu thực sự muốn |
| Dùng nhiều UPDATE mà không xét transaction/trigger | Trạng thái trung gian, tác động phụ | Cân nhắc một UPDATE và transaction |
| Coi transaction tự chữa SQL sai | Câu UPDATE sai vẫn có thể commit | Kiểm tra RHS/dialect/nguồn |
| Không xét lost update | Ghi đè dữ liệu concurrent | Version hoặc khóa hàng |
| Không xem số hàng cập nhật | Không phát hiện không tìm thấy | Kiểm tra row count/RETURNING |
| Coi thứ tự output của UPDATE là cam kết | Sai báo cáo | Chọn/sắp dữ liệu khi đọc lại |
| Chạy EXPLAIN ANALYZE UPDATE vô ý | Thực sự sửa dữ liệu | Chỉ đo khi đã bảo vệ |
| Đưa trực tiếp input vào SQL | SQL injection | Prepared statement và whitelist |

## 16. Bài tập thực hành

Sử dụng bảng `inventory_products`, `price_rules` và `swap_demo` từ phần 2 và 4. Mỗi bài có đáp án tham khảo; đối với những bài thực thi UPDATE, nên dùng transaction và `ROLLBACK` để dữ liệu về trạng thái ban đầu trước bài kế tiếp.

### Bài 1 — Cập nhật ba cột

Đặt sản phẩm 3 có `unit_price=55`, `stock_qty=15` và `product_status='ACTIVE'`.

**Đáp án:**

~~~sql
BEGIN;

UPDATE inventory_products
SET
    unit_price = 55.00,
    stock_qty = 15,
    product_status = 'ACTIVE'
WHERE product_id = 3
RETURNING product_id, unit_price, stock_qty, product_status;

ROLLBACK;
~~~

Câu lệnh cập nhật đúng một hàng theo khóa chính.

### Bài 2 — Lưu giá cũ, tăng 10%

Sản phẩm 1 có giá 100. Viết UPDATE PostgreSQL để lưu `previous_price=100` và giá mới 110.

**Đáp án:**

~~~sql
BEGIN;

UPDATE inventory_products
SET
    previous_price = unit_price,
    unit_price = ROUND(unit_price * 1.10, 2)
WHERE product_id = 1
RETURNING previous_price, unit_price;

ROLLBACK;
~~~

Cả hai biểu thức RHS đọc giá cũ trên PostgreSQL.

### Bài 3 — Swap trên PostgreSQL

Với `swap_demo` có `a=10,b=20`, chạy:

~~~sql
UPDATE swap_demo
SET a = b, b = a
WHERE id = 1;
~~~

**Đáp án:** `a=20,b=10` trong PostgreSQL.

### Bài 4 — Swap trên MySQL

Cùng câu trong bài 3, kết quả thông thường của MySQL single-table là gì?

**Đáp án:** thường là `a=20,b=20` do thứ tự gán trái→phải. Không phải phép swap đúng.

### Bài 5 — Hai phép gán phụ thuộc chéo

Với `a=10,b=20`, xem:

~~~sql
UPDATE swap_demo
SET a = a + 1, b = a
WHERE id = 1;
~~~

**Đáp án:** PostgreSQL cho `(11,10)`; MySQL single-table thường cho `(11,11)`.

### Bài 6 — Bán hết tồn sản phẩm 4

Sản phẩm 4 có tồn 2. Bán 2, đặt trạng thái OUT_OF_STOCK nếu tồn mới bằng 0.

**Đáp án PostgreSQL:**

~~~sql
BEGIN;

UPDATE inventory_products
SET
    stock_qty = stock_qty - 2,
    product_status = CASE
        WHEN stock_qty - 2 = 0 THEN 'OUT_OF_STOCK'
        ELSE 'ACTIVE'
    END
WHERE product_id = 4
  AND stock_qty >= 2
RETURNING product_id, stock_qty, product_status;

ROLLBACK;
~~~

Kết quả `stock_qty=0`, trạng thái OUT_OF_STOCK. Điều kiện CASE dùng tồn cũ trừ lượng bán.

### Bài 7 — Không bán quá tồn

Muốn bán 3 ở sản phẩm 4 nhưng tồn chỉ có 2. Viết UPDATE không làm tồn âm.

**Đáp án:**

~~~sql
UPDATE inventory_products
SET stock_qty = stock_qty - 3
WHERE product_id = 4
  AND stock_qty >= 3;
~~~

Không có hàng khớp nên ảnh hưởng 0 hàng. Ứng dụng phải thông báo hết/thiếu hàng.

### Bài 8 — Điều chỉnh giá từ bảng quy tắc

Viết PostgreSQL UPDATE để lưu giá cũ và áp dụng phần trăm giá mới cho sản phẩm ACTIVE.

**Đáp án:**

~~~sql
BEGIN;

UPDATE inventory_products AS p
SET
    previous_price = p.unit_price,
    unit_price = ROUND(
        p.unit_price * (1 + r.percent_change / 100.0),
        2
    )
FROM price_rules AS r
WHERE p.category_id = r.category_id
  AND p.product_status = 'ACTIVE'
RETURNING p.product_id, p.previous_price, p.unit_price;

ROLLBACK;
~~~

Kết quả: sản phẩm 1 `100→110`; 3 `50→45`; 4 `800→840`.

### Bài 9 — Nguồn join trùng khóa

Vì sao dùng `category_promotions` có hai hàng giảm 5% và 8% cho nhóm 10 trong `UPDATE ... FROM` là nguy hiểm?

**Đáp án:** một hàng đích khớp nhiều hàng nguồn. PostgreSQL không cam kết giá trị từ hàng khuyến mãi nào sẽ được dùng. Cần chọn một promotion theo tiêu chí hoặc tổng hợp về một hàng mỗi nhóm.

### Bài 10 — Scalar subquery không khớp nguồn

Nếu subquery trong `SET unit_price = (SELECT ... FROM price_rules ...)` trả không hàng, điều gì có thể xảy ra?

**Đáp án:** subquery scalar có thể trả `NULL`. Vì `unit_price NOT NULL`, UPDATE có thể lỗi. Nếu muốn chỉ sửa hàng có nguồn, thêm `WHERE EXISTS` hoặc dùng join đúng ngữ nghĩa.

### Bài 11 — DEFAULT khác bỏ cột

Sản phẩm 2 đang OUT_OF_STOCK, tồn 0:

~~~sql
-- A
UPDATE inventory_products
SET unit_price = 210.00
WHERE product_id = 2;

-- B
UPDATE inventory_products
SET unit_price = 210.00,
    product_status = DEFAULT
WHERE product_id = 2;
~~~

**Đáp án:** A giữ OUT_OF_STOCK, còn B đặt lại ACTIVE theo default của schema; B có thể sai nghiệp vụ dù không vi phạm CHECK.

### Bài 12 — Optimistic locking

Client thấy `version_no=1` của sản phẩm 1. Viết cập nhật giá 105 chỉ khi version chưa đổi.

**Đáp án:**

~~~sql
UPDATE inventory_products
SET
    unit_price = 105.00,
    version_no = version_no + 1
WHERE product_id = 1
  AND version_no = 1;
~~~

Nếu ảnh hưởng 0 hàng, client cần xử lý conflict/not found.

### Bài 13 — SQL Server OUTPUT

Cần lấy giá trước và sau UPDATE trên SQL Server.

**Đáp án:**

~~~sql
UPDATE dbo.inventory_products
SET unit_price = unit_price * 1.10
OUTPUT
    DELETED.unit_price AS old_price,
    INSERTED.unit_price AS new_price
WHERE product_id = 1;
~~~

`DELETED` và `INSERTED` là pseudo-table của T-SQL, không phải PostgreSQL.

### Bài 14 — MySQL UPDATE JOIN

Viết MySQL UPDATE chỉ sửa giá từ `price_rules` cho sản phẩm ACTIVE, không phụ thuộc chéo giữa nhiều phép gán.

**Đáp án:**

~~~sql
UPDATE inventory_products AS p
JOIN price_rules AS r
  ON r.category_id = p.category_id
SET p.unit_price = ROUND(
    p.unit_price * (1 + r.percent_change / 100.0),
    2
)
WHERE p.product_status = 'ACTIVE';
~~~

Nếu muốn lưu giá cũ cùng lúc, cần thiết kế một nguồn giá cũ đã xác định và transaction/cơ chế theo MySQL; không dựa vào thứ tự SET của multiple-table UPDATE.

### Bài 15 — Số hàng cập nhật

~~~sql
UPDATE inventory_products
SET unit_price = 999.00
WHERE product_id = 999;
~~~

**Đáp án:** không có product_id 999 nên 0 hàng được cập nhật. Câu lệnh không nhất thiết báo lỗi cú pháp. Với yêu cầu sửa đúng một sản phẩm, phải kiểm tra row count.

### Bài 16 — UPDATE nhiều cột so với nhiều câu UPDATE

Tại sao hai câu UPDATE liên tiếp không đương nhiên tương đương một UPDATE sửa cả hai cột?

**Đáp án:** có thể xuất hiện trạng thái trung gian, trigger chạy nhiều lượt, cơ chế khóa/transaction khác và nguy cơ một câu thành công câu sau lỗi. Một UPDATE nhiều cột rõ hơn cho một thay đổi logic, nhưng vẫn phải viết đúng biểu thức SET.

### Bài 17 — IS NULL

Viết UPDATE chỉ chọn những hàng có `previous_price` chưa biết.

**Đáp án:**

~~~sql
BEGIN;

UPDATE inventory_products
SET previous_price = 0
WHERE previous_price IS NULL
RETURNING product_id, previous_price;

ROLLBACK;
~~~

Với dữ liệu gốc, cả năm hàng có previous_price NULL. Đây chỉ là ví dụ điều kiện; không nên gán 0 cho giá cũ không biết nếu 0 không đúng nghiệp vụ.

### Bài 18 — Đề xuất thiết kế đa DBMS

Ứng dụng vừa chạy trên PostgreSQL vừa chạy trên MySQL cần cập nhật giá mới từ bảng khuyến mãi, đồng thời lưu đúng giá cũ. Bạn sẽ làm gì?

**Đáp án gợi ý:** chọn **tối đa một khuyến mãi** mỗi hàng đích theo khóa/ưu tiên; tạo giá cũ và giá mới từ một snapshot nhất quán; dùng transaction và khóa hoặc optimistic version; triển khai SQL theo dialect phù hợp; kiểm tra số hàng cập nhật và giá trị được trả. Trên PostgreSQL, `UPDATE ... FROM` và RHS đọc hàng cũ hỗ trợ việc đó trực tiếp. Trên MySQL multi-table, không phụ thuộc vào thứ tự các phép gán.

## 17. Checklist trước khi triển khai

1. **WHERE:** Chính xác hàng nào được sửa? Có thiếu bộ lọc tenant/quyền/trạng thái không?
2. **SET:** Những cột nào đổi, giá trị nào giữ nguyên?
3. **Giá trị cũ/mới:** Có RHS nào đọc cột vừa được gán ở phép khác không?
4. **Dialect:** PostgreSQL và MySQL có dùng cùng ngữ nghĩa thứ tự gán không?
5. **Nguồn join:** Mỗi hàng đích có tối đa một hàng nguồn phù hợp không?
6. **Scalar subquery:** Có thể trả 0 hoặc nhiều hàng? Hậu quả với NULL/NOT NULL?
7. **CASE:** Thứ tự WHEN và giá trị tham chiếu có đúng nghiệp vụ?
8. **DEFAULT/NULL:** Có đang nhầm default với trạng thái hợp lệ hoặc nhầm NULL với 0?
9. **Constraint:** Giá trị sau UPDATE có thỏa CHECK/NOT NULL/UNIQUE/FK không?
10. **Trigger/generated:** Có cơ chế nào thay đổi kết quả ngoài SET không?
11. **Concurrency:** Có optimistic version, row lock hoặc transaction phù hợp không?
12. **Quan sát:** Kiểm tra affected rows, RETURNING, OUTPUT hoặc API kết quả như thế nào?
13. **Hiệu năng:** Index phục vụ WHERE/JOIN, thời gian khóa và batch có phù hợp không?
14. **An toàn:** Bind tham số, whitelist identifier và kiểm soát quyền sửa chưa?
15. **Khả chuyển:** UPDATE FROM/JOIN, row assignment, ORDER BY/LIMIT và returning/output có trong đúng phiên bản DBMS không?

## 18. Tổng kết

Một câu **`UPDATE ... SET`** có thể thay đổi nhiều cột trong một thao tác. Nhưng ngoài việc chọn đúng hàng bằng `WHERE`, người viết còn phải hiểu **mỗi biểu thức vế phải được đánh giá từ trạng thái nào**.

Trong PostgreSQL, những phép gán như `SET a=b, b=a` dùng giá trị trước cập nhật và có thể hoán đổi hai cột. Trong MySQL với UPDATE một bảng, các phép gán **thường** được xử lý từ trái sang phải, nên cùng câu lệnh có thể không hoán đổi; trong UPDATE nhiều bảng, MySQL **không bảo đảm** thứ tự gán tương tự. Vì thế, không nên chuyển SQL quan trọng giữa các hệ với giả định mọi engine có cùng quy tắc.

Khi cập nhật giá/tồn kho từ bảng khác, luôn bảo đảm **mỗi hàng đích có nguồn giá trị rõ ràng và đơn trị**. Khi dùng `CASE`, tính đúng giá trị **sau cập nhật** thay vì vô tình kiểm tra giá trị cũ. Khi có dữ liệu đồng thời, dùng transaction, khóa hoặc version để tránh ghi đè kết quả của người khác. Cuối cùng, quan sát số hàng tác động và giá trị trả về trước khi xác nhận thao tác.

**Nguyên tắc cốt lõi:** trước khi viết UPDATE nhiều cột, xác định rõ **hàng nào sẽ đổi, mỗi RHS đọc giá trị cũ hay mới, phép gán có phụ thuộc chéo không và mỗi hàng đích khớp bao nhiêu hàng nguồn**. Bốn câu hỏi này giúp tránh những lỗi nguy hiểm nhất: SQL chạy thành công nhưng dữ liệu bị cập nhật sai.
