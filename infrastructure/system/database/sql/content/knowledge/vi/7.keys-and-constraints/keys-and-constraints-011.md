# Đặt tên, thêm, xóa và kiểm tra lỗi vi phạm ràng buộc

Trong cơ sở dữ liệu quan hệ, **ràng buộc** (*constraint*) giúp hệ quản trị từ chối những thay đổi làm dữ liệu không còn đáp ứng quy tắc đã khai báo. Ví dụ: mã đơn hàng không được trùng, đơn hàng phải thuộc một khách hàng tồn tại, số lượng mua phải lớn hơn 0 và trạng thái đơn chỉ được nằm trong danh sách cho phép.

Khai báo được ràng buộc mới chỉ là một phần công việc. Khi vận hành lược đồ thực tế, chúng ta còn cần **đặt tên dễ hiểu**, **thêm ràng buộc vào bảng đang có dữ liệu**, **xóa hoặc đổi tên khi quy tắc thay đổi**, và **đọc đúng lỗi vi phạm** để xử lý tại nơi phát sinh. Đặc biệt, thao tác thêm ràng buộc có thể thất bại nếu dữ liệu cũ chưa hợp lệ.

Bài học nằm trong chương **Khóa và ràng buộc** của module **Database SQL**. Ví dụ thực hành chính dùng **PostgreSQL 15 trở lên** với một schema riêng tên **constraint_lab**. Phần cuối nêu những khác biệt cần lưu ý khi làm việc với MySQL, SQL Server và SQLite.

## 1. Mục tiêu thực hành

Sau bài này, bạn có thể:

1. Phân biệt ràng buộc **PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK, NOT NULL** và vai trò của **DEFAULT**.
2. Tự đặt tên ràng buộc theo quy ước nhất quán, có thể đọc hiểu khi gặp thông báo lỗi.
3. Khai báo ràng buộc ngay khi **CREATE TABLE** hoặc bổ sung bằng **ALTER TABLE**.
4. Đổi tên và xóa ràng buộc một cách có kiểm soát.
5. Phát hiện dữ liệu cũ vi phạm ràng buộc, sau đó sửa và xác nhận tính hợp lệ.
6. Tra cứu ràng buộc đã được cài đặt trong metadata của cơ sở dữ liệu.
7. Nhận biết các mã lỗi **SQLSTATE** phổ biến của PostgreSQL và phân biệt nguyên nhân vi phạm.

Đây là bài tập trên dữ liệu giả lập. Chỉ dùng các lệnh làm thay đổi lược đồ trong **database thực hành riêng**, tránh chạy trực tiếp trên bảng đang phục vụ ứng dụng thật.

## 2. Có những loại ràng buộc nào?

| Loại | Mục đích | Ví dụ | Trường hợp lỗi |
| --- | --- | --- | --- |
| **PRIMARY KEY** | Định danh duy nhất từng hàng; không được NULL | orders.order_id | Thêm hai đơn có cùng order_id |
| **UNIQUE** | Ngăn giá trị hoặc tổ hợp giá trị trùng nhau | customers.email | Hai khách có cùng email |
| **FOREIGN KEY** | Bảo đảm giá trị tham chiếu đến hàng hợp lệ ở bảng cha | orders.customer_id → customers.customer_id | Tạo đơn cho khách không tồn tại |
| **CHECK** | Chỉ chấp nhận dữ liệu thỏa điều kiện khai báo | quantity > 0 | Thêm số lượng bằng 0 |
| **NOT NULL** | Bắt buộc cột có giá trị | customers.full_name | Chèn tên khách NULL |

**DEFAULT** thường xuất hiện cạnh các ràng buộc, nhưng nó là **quy tắc cung cấp giá trị khi không nhập**, không phải phép kiểm tra tính hợp lệ tương đương CHECK hay FOREIGN KEY. Ví dụ:

~~~sql
status TEXT NOT NULL DEFAULT 'pending'
~~~

Nếu bỏ status khỏi INSERT, PostgreSQL sử dụng 'pending'. Nếu cố tình chèn NULL, **NOT NULL** vẫn từ chối. DEFAULT không tự biến mọi NULL do người dùng nhập thành 'pending'.

### PRIMARY KEY và UNIQUE không hoàn toàn giống nhau

- Bảng có thể có **một ràng buộc PRIMARY KEY**, gồm một hoặc nhiều cột.
- Bảng có thể có **nhiều ràng buộc UNIQUE** ở những cột hoặc tổ hợp cột khác nhau.
- Các cột trong PRIMARY KEY phải có giá trị, nên về ngữ nghĩa chúng **không được NULL**.
- Trong PostgreSQL, UNIQUE thông thường cho phép **nhiều NULL** vì NULL không được xem là bằng một giá trị xác định trong kiểu kiểm tra duy nhất mặc định. PostgreSQL 15+ hỗ trợ lựa chọn **NULLS NOT DISTINCT** khi muốn xem NULL là trùng nhau.

Ví dụ khóa chính ghép cho chi tiết đơn hàng:

~~~sql
CONSTRAINT pk_order_items PRIMARY KEY (order_id, product_id)
~~~

Nó ngăn một sản phẩm xuất hiện hai dòng trong cùng một đơn, nhưng sản phẩm đó vẫn có thể xuất hiện ở nhiều đơn khác nhau.

### CHECK và NULL là một bẫy thường gặp

Trong SQL, **CHECK** chỉ từ chối giá trị khi biểu thức điều kiện cho **FALSE**. Nếu biểu thức cho **UNKNOWN** vì NULL, PostgreSQL không coi đó là vi phạm CHECK:

~~~sql
price NUMERIC(12, 2) CHECK (price > 0)
~~~

Định nghĩa trên **chưa cấm price = NULL**. Muốn giá luôn có và lớn hơn 0, cần:

~~~sql
price NUMERIC(12, 2) NOT NULL
    CONSTRAINT ck_items_price_positive CHECK (price > 0)
~~~

Trong thực tế, tên ràng buộc CHECK nên mô tả **quy tắc**, còn NOT NULL mô tả yêu cầu **phải có giá trị**.

## 3. Đặt tên ràng buộc có chủ đích

Nếu không đặt tên, hệ quản trị có thể tự sinh tên như **orders_customer_id_fkey** hoặc **products_price_check**. Những tên tự động này hợp lệ nhưng dễ thay đổi khi đổi bảng, thêm nhiều phép kiểm tra hoặc di chuyển sang phương ngữ khác.

Khi tự đặt tên, nên dùng một quy ước ổn định:

| Tiền tố đề xuất | Loại | Ví dụ |
| --- | --- | --- |
| **pk_** | PRIMARY KEY | pk_customers, pk_order_items |
| **uq_** | UNIQUE | uq_customers_email, uq_products_sku |
| **fk_** | FOREIGN KEY | fk_orders_customer, fk_order_items_product |
| **ck_** | CHECK | ck_items_quantity_positive, ck_orders_status |

Có thể bổ sung tên bảng và mô tả ngắn về cột hoặc quy tắc. Ví dụ **fk_orders_customer** đọc được là “khóa ngoại từ orders tới customer”, trong khi **ck_orders_status** nói rõ CHECK đang kiểm tra trạng thái đơn hàng.

**Nguyên tắc thực tế:**

1. Dùng chữ thường và dấu gạch dưới để tránh phải đặt tên trong dấu nháy kép.
2. Giữ tên đủ cụ thể nhưng không quá dài; PostgreSQL mặc định giới hạn định danh **63 byte**, nên tên quá dài có thể bị cắt.
3. Tránh tên chung chung như **constraint1**, **check_valid** hay **fk_id**.
4. Cân nhắc quy ước chung cho toàn dự án; nhiều công cụ migration cần tham chiếu **chính xác** tên ràng buộc.
5. Không giả định mọi hệ quản trị có cùng phạm vi duy nhất của tên. Trong PostgreSQL, tên constraint có thể được dùng lại ở bảng khác, nhưng một số constraint sinh chỉ mục, và **tên chỉ mục phải phù hợp phạm vi tên trong schema**. Đặt tên có kèm bảng thường tránh va chạm.

Trong PostgreSQL, định danh không đặt dấu nháy kép được chuyển về chữ thường. Ví dụ **CK_Orders_Status** và **ck_orders_status** khi không dùng dấu nháy kép được hiểu cùng một tên. Nếu khai báo tên phân biệt hoa/thường bằng dấu nháy kép, các lệnh quản lý sau đó phải tiếp tục trích dẫn đúng; thường không cần thiết cho mục tiêu bài này.

## 4. Tạo bộ dữ liệu thực hành với các ràng buộc đã đặt tên

Tạo một database thực hành và mở kết nối tới nó. Trong database ấy, chạy khối SQL sau **một lần**. Ví dụ sử dụng schema riêng để tránh trùng tên bảng của những bài trước:

~~~sql
CREATE SCHEMA constraint_lab;

CREATE TABLE constraint_lab.customers (
    customer_id INTEGER NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_email UNIQUE (email),
    CONSTRAINT ck_customers_name_nonempty
        CHECK (LENGTH(BTRIM(full_name)) > 0)
);

CREATE TABLE constraint_lab.products (
    product_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (product_id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price_nonnegative
        CHECK (unit_price >= 0)
);

CREATE TABLE constraint_lab.orders (
    order_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    placed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES constraint_lab.customers (customer_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_orders_status
        CHECK (status IN ('pending', 'paid', 'completed', 'cancelled'))
);

CREATE TABLE constraint_lab.order_items (
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES constraint_lab.orders (order_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES constraint_lab.products (product_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_items_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_items_price_nonnegative CHECK (unit_price >= 0)
);
~~~

Điểm đáng chú ý: bảng **products** cố ý **chưa có CHECK cho stock_quantity**, dù cột đó đã NOT NULL. Ta sẽ thêm ràng buộc này sau để minh họa cách xử lý dữ liệu cũ vi phạm.

Nhập dữ liệu giả lập theo đúng thứ tự phụ thuộc: bảng cha trước, bảng con sau.

~~~sql
INSERT INTO constraint_lab.customers
    (customer_id, full_name, email, phone)
VALUES
    (1, 'Nguyễn An', 'an@example.test', '0900000001'),
    (2, 'Trần Bình', 'binh@example.test', NULL),
    (3, 'Lê Chi', 'chi@example.test', '0900000003');

INSERT INTO constraint_lab.products
    (product_id, sku, product_name, unit_price, stock_quantity)
VALUES
    (101, 'SKU-101', 'Bàn phím', 850000, 20),
    (102, 'SKU-102', 'Chuột', 250000, 50),
    (103, 'SKU-103', 'Tai nghe', 500000, 0);

INSERT INTO constraint_lab.orders
    (order_id, customer_id, status, placed_at)
VALUES
    (1001, 1, 'paid', '2026-02-01 09:00:00+07'),
    (1002, 2, 'pending', '2026-02-02 10:00:00+07');

INSERT INTO constraint_lab.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 101, 1, 850000),
    (1001, 102, 2, 250000),
    (1002, 103, 1, 500000);
~~~

Các email thuộc miền **example.test** chỉ để minh họa. Dữ liệu có **3 khách hàng, 3 sản phẩm, 2 đơn hàng và 3 dòng chi tiết**. Bộ dữ liệu nhỏ giúp quan sát chính xác ràng buộc nào chặn một thao tác.

### Phân biệt ràng buộc cấp cột và cấp bảng

Một cột đơn lẻ có thể khai báo CHECK ngay sau kiểu dữ liệu:

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
~~~

Hoặc dùng ràng buộc cấp bảng có tên:

~~~sql
quantity INTEGER NOT NULL,
CONSTRAINT ck_items_quantity_positive CHECK (quantity > 0)
~~~

Hai dạng đều kiểm tra cùng một điều kiện. Dạng cấp bảng thường thuận tiện khi muốn **đặt tên rõ ràng**, dùng biểu thức trên **nhiều cột**, hoặc quản lý qua ALTER TABLE.

Ràng buộc nhiều cột, chẳng hạn PRIMARY KEY ghép, phải nêu rõ tổ hợp:

~~~sql
CONSTRAINT pk_order_items PRIMARY KEY (order_id, product_id)
~~~

Trong PostgreSQL 15–17, **NOT NULL** được quản lý như thuộc tính của cột, thường thêm/xóa bằng **ALTER COLUMN ... SET/DROP NOT NULL** thay vì dùng chung cú pháp ADD/DROP CONSTRAINT của CHECK, UNIQUE hoặc FOREIGN KEY.

## 5. Tra cứu tên và định nghĩa ràng buộc đang tồn tại

Không nên đoán tên ràng buộc từ thông báo cũ hoặc từ quy ước. Có thể xem metadata hiện tại trước khi ALTER TABLE.

### 5.1. Tra cứu qua INFORMATION_SCHEMA

~~~sql
SELECT
    table_name,
    constraint_name,
    constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'constraint_lab'
ORDER BY table_name, constraint_type, constraint_name;
~~~

Truy vấn liệt kê các ràng buộc chính như **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY** và **CHECK** mà INFORMATION_SCHEMA cung cấp. Phạm vi và chi tiết kết quả còn phụ thuộc vào hệ quản trị và quyền của tài khoản đang kết nối.

Muốn biết cột tham gia khóa:

~~~sql
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    kcu.ordinal_position
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON kcu.constraint_catalog = tc.constraint_catalog
 AND kcu.constraint_schema = tc.constraint_schema
 AND kcu.constraint_name = tc.constraint_name
 AND kcu.table_catalog = tc.table_catalog
 AND kcu.table_schema = tc.table_schema
 AND kcu.table_name = tc.table_name
WHERE tc.table_schema = 'constraint_lab'
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
~~~

**CHECK** không nhất thiết có dòng tương ứng trong **key_column_usage** theo cách khóa chính hoặc khóa ngoại có. Vì vậy, truy vấn này phù hợp nhất khi khảo sát các ràng buộc gắn với cột khóa; để xem **biểu thức CHECK**, dùng truy vấn riêng ở phần tiếp theo.

### 5.2. Xem định nghĩa thực tế trong PostgreSQL

~~~sql
SELECT
    tbl.relname AS table_name,
    c.conname AS constraint_name,
    c.contype AS constraint_kind,
    c.convalidated AS is_validated,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint AS c
JOIN pg_class AS tbl
    ON tbl.oid = c.conrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'constraint_lab'
ORDER BY tbl.relname, c.conname;
~~~

Trong catalog PostgreSQL, **contype** là mã loại: **p** = PRIMARY KEY, **u** = UNIQUE, **f** = FOREIGN KEY, **c** = CHECK, và một số loại khác khi được hỗ trợ. **convalidated** cho biết ràng buộc đã được xác nhận trên dữ liệu cũ hay chưa; trường này đặc biệt hữu ích với **CHECK/FK được thêm bằng NOT VALID**.

Để kiểm tra cột bắt buộc dữ liệu:

~~~sql
SELECT
    table_name,
    column_name,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'constraint_lab'
ORDER BY table_name, ordinal_position;
~~~

**is_nullable = 'NO'** thường cho biết cột không chấp nhận NULL theo metadata. Đừng chỉ tìm NOT NULL trong pg_constraint của PostgreSQL 15–17 rồi kết luận rằng cột không có kiểm soát NULL.

Trong **psql**, lệnh tiện ích:

~~~text
\d constraint_lab.orders
~~~

giúp xem cột, khóa, chỉ mục và ràng buộc ngay trên terminal. Đây là **lệnh của psql**, không phải SQL chuẩn; không dán lệnh này vào Query Tool chỉ chấp nhận câu SQL.

## 6. Thêm CHECK vào bảng đang có dữ liệu

Giả sử có yêu cầu mới: **stock_quantity không được âm**. Vì bảng products hiện chưa có CHECK này, bạn có thể bổ sung:

~~~sql
ALTER TABLE constraint_lab.products
ADD CONSTRAINT ck_products_stock_nonnegative
CHECK (stock_quantity >= 0);
~~~

Nếu mọi hàng hiện có hợp lệ, lệnh thành công. Sau đó các thao tác INSERT hoặc UPDATE làm tồn kho âm sẽ bị chặn.

### 6.1. Khi dữ liệu cũ đã vi phạm: ADD CONSTRAINT thất bại

Để minh họa một migration gặp dữ liệu lỗi, hãy bắt đầu lại phần này từ trạng thái **chưa tạo CHECK stock_quantity**, sau đó cố ý đặt tồn kho âm:

~~~sql
UPDATE constraint_lab.products
SET stock_quantity = -3
WHERE product_id = 102;
~~~

Lúc này:

~~~sql
SELECT product_id, sku, stock_quantity
FROM constraint_lab.products
WHERE stock_quantity < 0;
~~~

sẽ trả về sản phẩm **102**. Nếu thử:

~~~sql
ALTER TABLE constraint_lab.products
ADD CONSTRAINT ck_products_stock_nonnegative
CHECK (stock_quantity >= 0);
~~~

PostgreSQL từ chối, vì bảng đang có ít nhất một hàng vi phạm. **Không có ràng buộc mới nào được thêm thành công bởi lệnh thất bại đó**. Nếu môi trường thực thi bọc các lệnh trong một giao dịch, cần xử lý giao dịch bị lỗi trước khi chạy bước kế tiếp.

Trong thực tế, nên **tìm và sửa các bản ghi lỗi trước**, rồi thêm ràng buộc để hệ quản trị xác nhận toàn bộ dữ liệu:

~~~sql
UPDATE constraint_lab.products
SET stock_quantity = 0
WHERE stock_quantity < 0;

ALTER TABLE constraint_lab.products
ADD CONSTRAINT ck_products_stock_nonnegative
CHECK (stock_quantity >= 0);
~~~

Ở đây việc đổi -3 thành 0 **chỉ là quyết định sửa dữ liệu mẫu**. Với hệ thống thật, tồn kho âm có thể liên quan đến nghiệp vụ bán trước hàng hoặc lệch kho, nên cần điều tra trước khi sửa.

### 6.2. NOT VALID và VALIDATE CONSTRAINT

PostgreSQL cho phép đưa **CHECK** và **FOREIGN KEY** vào bảng lớn bằng hai giai đoạn:

1. **ADD CONSTRAINT ... NOT VALID:** tạo ràng buộc nhưng chưa quét xác nhận tất cả hàng cũ.
2. **VALIDATE CONSTRAINT:** kiểm tra các hàng đã có; chỉ đánh dấu hợp lệ khi không còn vi phạm.

Ví dụ sau **thay thế** đường đi “sửa rồi ADD” ở trên, không phải chạy thêm sau khi ràng buộc cùng tên đã tồn tại. Trong tình huống bảng có stock_quantity = -3 và chưa có CHECK:

~~~sql
ALTER TABLE constraint_lab.products
ADD CONSTRAINT ck_products_stock_nonnegative
CHECK (stock_quantity >= 0) NOT VALID;
~~~

Lệnh này có thể thành công dù bản ghi 102 đang có stock_quantity âm. Tuy nhiên, ràng buộc **đã có hiệu lực đối với dữ liệu mới và những hàng được INSERT/UPDATE**. **NOT VALID không có nghĩa là tắt kiểm tra cho những thay đổi mới.**

Thử xác nhận ngay:

~~~sql
ALTER TABLE constraint_lab.products
VALIDATE CONSTRAINT ck_products_stock_nonnegative;
~~~

Việc xác nhận sẽ thất bại nếu vẫn có hàng vi phạm. Sau khi sửa:

~~~sql
UPDATE constraint_lab.products
SET stock_quantity = 0
WHERE product_id = 102;

ALTER TABLE constraint_lab.products
VALIDATE CONSTRAINT ck_products_stock_nonnegative;
~~~

Lúc này convalidated trong pg_constraint sẽ là **TRUE**.

~~~sql
SELECT c.conname, c.convalidated
FROM pg_constraint AS c
JOIN pg_class AS t ON t.oid = c.conrelid
JOIN pg_namespace AS n ON n.oid = t.relnamespace
WHERE n.nspname = 'constraint_lab'
  AND t.relname = 'products'
  AND c.conname = 'ck_products_stock_nonnegative';
~~~

**Lưu ý:** trong PostgreSQL, cách thêm **UNIQUE** và **PRIMARY KEY** không có cùng lựa chọn NOT VALID như CHECK/FK. Với bảng lớn cần UNIQUE, một hướng migration khác là tạo **unique index** có kiểm soát rồi gắn thành constraint nếu thỏa yêu cầu; không áp dụng máy móc NOT VALID cho mọi loại ràng buộc.

## 7. Thêm UNIQUE và FOREIGN KEY bằng ALTER TABLE

### 7.1. Thêm UNIQUE cho cột mới

Giả sử cần lưu một mã khách hàng trong hệ thống đối tác, nhưng không phải khách nào cũng đã có mã:

~~~sql
ALTER TABLE constraint_lab.customers
ADD COLUMN external_code TEXT;

UPDATE constraint_lab.customers
SET external_code = 'EXT-001'
WHERE customer_id = 1;

UPDATE constraint_lab.customers
SET external_code = 'EXT-002'
WHERE customer_id = 2;

ALTER TABLE constraint_lab.customers
ADD CONSTRAINT uq_customers_external_code UNIQUE (external_code);
~~~

Sau đó, hai khách hàng **không thể cùng có external_code = 'EXT-001'**. Cột chưa có mã có thể để NULL. UNIQUE thông thường của PostgreSQL cho phép nhiều NULL; nếu nghiệp vụ không cho nhiều NULL, cần quy tắc khác phù hợp, ví dụ **UNIQUE NULLS NOT DISTINCT** trên PostgreSQL 15+ hoặc kết hợp ràng buộc bắt buộc.

Trước khi thêm UNIQUE vào một cột đã có dữ liệu, có thể tìm giá trị trùng:

~~~sql
SELECT external_code, COUNT(*) AS occurrences
FROM constraint_lab.customers
WHERE external_code IS NOT NULL
GROUP BY external_code
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn có hàng kết quả, cần xác minh và xử lý các mã trùng trước khi thêm UNIQUE.

### 7.2. Thêm FOREIGN KEY sau khi bảng đã tồn tại

Tạo một bảng ghi chú khách hàng, ban đầu chưa khai báo khóa ngoại để minh họa quá trình thêm sau:

~~~sql
CREATE TABLE constraint_lab.customer_notes (
    note_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    note_text TEXT NOT NULL,
    CONSTRAINT pk_customer_notes PRIMARY KEY (note_id)
);

INSERT INTO constraint_lab.customer_notes
    (note_id, customer_id, note_text)
VALUES
    (1, 1, 'Khách ưu tiên'),
    (2, 999, 'Mã khách hàng không tồn tại');
~~~

Khách hàng **999 không tồn tại**. Nếu thêm khóa ngoại bình thường:

~~~sql
ALTER TABLE constraint_lab.customer_notes
ADD CONSTRAINT fk_customer_notes_customer
FOREIGN KEY (customer_id)
REFERENCES constraint_lab.customers (customer_id);
~~~

PostgreSQL từ chối do dữ liệu đang có vi phạm tham chiếu. Có thể tìm các hàng mồ côi:

~~~sql
SELECT n.note_id, n.customer_id
FROM constraint_lab.customer_notes AS n
LEFT JOIN constraint_lab.customers AS c
    ON c.customer_id = n.customer_id
WHERE c.customer_id IS NULL;
~~~

Nếu chọn chiến lược hai giai đoạn, thêm khóa ngoại **NOT VALID** trước:

~~~sql
ALTER TABLE constraint_lab.customer_notes
ADD CONSTRAINT fk_customer_notes_customer
FOREIGN KEY (customer_id)
REFERENCES constraint_lab.customers (customer_id)
NOT VALID;
~~~

Sau đó sửa ví dụ ghi chú sai bằng cách chuyển về mã khách hàng có thật (chỉ để mô phỏng thao tác làm sạch):

~~~sql
UPDATE constraint_lab.customer_notes
SET customer_id = 3
WHERE note_id = 2;

ALTER TABLE constraint_lab.customer_notes
VALIDATE CONSTRAINT fk_customer_notes_customer;
~~~

Đây là cùng nguyên tắc **thêm, sửa dữ liệu cũ, xác nhận** như CHECK. Cần xác định quan hệ đúng từ nghiệp vụ trước khi gán mã khách thật; không nên tự gán một khách ngẫu nhiên trong dữ liệu thật.

### 7.3. Thêm và bỏ NOT NULL

Với PostgreSQL 15–17, NOT NULL thường quản lý ở cấp thuộc tính cột:

~~~sql
ALTER TABLE constraint_lab.customer_notes
ADD COLUMN note_category TEXT;

UPDATE constraint_lab.customer_notes
SET note_category = 'general'
WHERE note_category IS NULL;

ALTER TABLE constraint_lab.customer_notes
ALTER COLUMN note_category SET NOT NULL;
~~~

Nếu vẫn có note_category NULL, thao tác SET NOT NULL thất bại. Khi yêu cầu kinh doanh thay đổi và cột được phép thiếu giá trị:

~~~sql
ALTER TABLE constraint_lab.customer_notes
ALTER COLUMN note_category DROP NOT NULL;
~~~

**ALTER COLUMN ... DROP NOT NULL** chỉ bỏ yêu cầu không được NULL; nó không xóa dữ liệu đã có và cũng không tự xóa các CHECK khác có thể chặn NULL.

## 8. Đổi tên, xóa và khôi phục ràng buộc

### 8.1. Đổi tên: RENAME CONSTRAINT

PostgreSQL hỗ trợ đổi tên một constraint đang tồn tại:

~~~sql
ALTER TABLE constraint_lab.products
RENAME CONSTRAINT ck_products_stock_nonnegative
TO ck_products_stock_min_zero;
~~~

Lệnh đổi tên **không thay đổi biểu thức kiểm tra** stock_quantity >= 0. Nó đổi tên đối tượng để metadata và thông báo lỗi nhất quán với quy ước mới. Nếu có migration, mã giám sát hoặc tài liệu tham chiếu tên cũ, cần cập nhật phần tham chiếu đó.

### 8.2. Xóa: DROP CONSTRAINT

~~~sql
ALTER TABLE constraint_lab.products
DROP CONSTRAINT ck_products_stock_min_zero;
~~~

Sau khi xóa, hệ quản trị **không còn kiểm tra ràng buộc này** khi ghi dữ liệu mới. Các CHECK, khóa khác và NOT NULL vẫn còn hiệu lực. DROP CONSTRAINT không xóa các hàng dữ liệu chỉ vì chúng từng được kiểm tra bởi constraint đó.

Nếu muốn tránh lỗi khi ràng buộc không tồn tại:

~~~sql
ALTER TABLE constraint_lab.products
DROP CONSTRAINT IF EXISTS ck_products_stock_min_zero;
~~~

Trong PostgreSQL, DROP CONSTRAINT mặc định ứng xử như **RESTRICT** khi có đối tượng phụ thuộc; dùng **CASCADE** có thể xóa thêm các đối tượng phụ thuộc. Không nên dùng CASCADE chỉ để “cho lệnh chạy qua” khi chưa biết những đối tượng nào bị ảnh hưởng.

### 8.3. Khôi phục CHECK sau ví dụ xóa

~~~sql
ALTER TABLE constraint_lab.products
ADD CONSTRAINT ck_products_stock_nonnegative
CHECK (stock_quantity >= 0);
~~~

Lệnh này chỉ thành công khi tồn kho hiện tại không âm. Sau khi khôi phục, tên trở về quy ước ban đầu.

### 8.4. Xóa khóa chính, khóa ngoại hoặc UNIQUE cần cân nhắc phụ thuộc

Không nên xóa **pk_customers** khi các đơn hàng còn tham chiếu customers.customer_id: việc thay đổi khóa cha có thể ảnh hưởng đến khóa ngoại của bảng con. Cũng không nên bỏ **fk_orders_customer** trong hệ thống có giao dịch đang chạy chỉ để chèn một đơn chưa có khách.

Ví dụ **cú pháp minh họa**, không thực hiện trên bộ dữ liệu đang sử dụng nếu không có kế hoạch migration:

~~~sql
-- Minh họa cú pháp; có thể phá vỡ bảo vệ tính toàn vẹn:
ALTER TABLE constraint_lab.orders
DROP CONSTRAINT fk_orders_customer;
~~~

Nếu bắt buộc thay ràng buộc, hãy lập kế hoạch thay đổi trên bảng cha/bảng con, đánh giá khóa và thời gian thực thi, và bảo đảm ràng buộc mới được xác nhận sau khi dữ liệu được sửa.

## 9. Nhận diện lỗi vi phạm bằng SQLSTATE của PostgreSQL

PostgreSQL phát sinh **mã lỗi SQLSTATE gồm 5 ký tự**. Những lỗi vi phạm tính toàn vẹn thường thuộc **lớp 23** (*integrity constraint violation*).

| SQLSTATE | Tên thường gặp trong PostgreSQL | Nguyên nhân phổ biến |
| --- | --- | --- |
| **23505** | unique_violation | Trùng PRIMARY KEY hoặc UNIQUE |
| **23503** | foreign_key_violation | FK trỏ tới hàng cha không có, hoặc xóa/sửa hàng cha đang được tham chiếu |
| **23514** | check_violation | Dữ liệu làm CHECK thành FALSE |
| **23502** | not_null_violation | Chèn hoặc cập nhật NULL vào cột NOT NULL |
| **23P01** | exclusion_violation | Vi phạm EXCLUDE constraint của PostgreSQL |

**23505** dùng cho cả lỗi PRIMARY KEY và UNIQUE. Vì vậy, mã lỗi **chưa đủ để biết ràng buộc nào bị vi phạm**; cần đọc thêm **tên constraint** và thông tin về bảng/cột.

Một thông báo PostgreSQL cho lỗi trùng email thường có hình thức:

~~~text
ERROR:  duplicate key value violates unique constraint "uq_customers_email"
DETAIL: Key (email)=(an@example.test) already exists.
SQLSTATE: 23505
~~~

Thông báo có thể được trình bày khác nhau theo **psql**, pgAdmin, thư viện driver hoặc phiên bản máy chủ. Điều quan trọng cần tìm là **SQLSTATE**, **constraint name**, **DETAIL** và những giá trị liên quan.

### 9.1. UNIQUE: cố ý chèn email trùng

~~~sql
-- Dự kiến lỗi 23505 tại uq_customers_email.
INSERT INTO constraint_lab.customers
    (customer_id, full_name, email)
VALUES
    (99, 'Khách kiểm thử', 'an@example.test');
~~~

customer_id = 99 chưa có, nên lỗi cần quan sát là **email trùng**, không phải PRIMARY KEY. Hàng khách 99 không được thêm thành công.

### 9.2. PRIMARY KEY: cố ý chèn mã đơn trùng

~~~sql
-- Dự kiến lỗi 23505 tại pk_orders.
INSERT INTO constraint_lab.orders
    (order_id, customer_id, status)
VALUES
    (1001, 1, 'paid');
~~~

Mã **1001** đã tồn tại. Cả hai ví dụ 9.1 và 9.2 có thể cùng SQLSTATE 23505 nhưng **constraint name khác nhau**, nhờ cách đặt tên từ đầu.

### 9.3. FOREIGN KEY: mã khách hàng không tồn tại

~~~sql
-- Dự kiến lỗi 23503 tại fk_orders_customer.
INSERT INTO constraint_lab.orders
    (order_id, customer_id, status)
VALUES
    (1099, 999, 'pending');
~~~

Đơn 1099 tham chiếu customer_id = 999 chưa có trong customers. Đây là lỗi **quan hệ tham chiếu**, không phải lỗi kiểu dữ liệu.

Ví dụ khác cho cùng nhóm lỗi:

~~~sql
-- Dự kiến lỗi 23503: khách 1 đang có đơn 1001 tham chiếu.
DELETE FROM constraint_lab.customers
WHERE customer_id = 1;
~~~

Ràng buộc **ON DELETE RESTRICT** ngăn xóa khách vẫn đang được đơn hàng tham chiếu. Quy tắc xóa có thể được định nghĩa khác (CASCADE, SET NULL, NO ACTION...) tùy nghiệp vụ, nhưng không thể tự suy ra rằng cứ có FK thì hành động xóa luôn giống nhau.

### 9.4. CHECK: trạng thái ngoài danh sách

~~~sql
-- Dự kiến lỗi 23514 tại ck_orders_status.
INSERT INTO constraint_lab.orders
    (order_id, customer_id, status)
VALUES
    (1098, 1, 'returned');
~~~

Vì CHECK chỉ cho phép **pending, paid, completed, cancelled**, giá trị 'returned' bị từ chối. Nếu nghiệp vụ đã có trạng thái trả hàng, cách sửa lâu dài có thể là **cập nhật mô hình trạng thái và ràng buộc** theo một quy trình migration, thay vì tự thay chuỗi dữ liệu không đúng ý nghĩa.

### 9.5. CHECK: số lượng không hợp lệ

~~~sql
-- Dự kiến lỗi 23514 tại ck_items_quantity_positive.
INSERT INTO constraint_lab.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1002, 102, 0, 250000);
~~~

Cặp khóa **(1002, 102)** chưa có nên ví dụ này tập trung vào **CHECK quantity > 0**. Nếu chọn cặp khóa đã có, có thể gặp lỗi PRIMARY KEY trước; vì vậy nên tạo **mỗi ví dụ chỉ vi phạm một quy tắc** để dễ nhận diện nguyên nhân.

### 9.6. NOT NULL: không nhập tên khách

~~~sql
-- Dự kiến lỗi 23502 cho cột full_name.
INSERT INTO constraint_lab.customers
    (customer_id, full_name, email)
VALUES
    (98, NULL, 'new@example.test');
~~~

Với PostgreSQL 15–17, thông báo có thể nêu cột **full_name** dù NOT NULL không được khai báo bằng tên ràng buộc giống CHECK. Điều này vẫn là vi phạm ràng buộc về tính toàn vẹn.

### 9.7. Dùng giao dịch và SAVEPOINT khi thử lỗi

Khi một câu lệnh lỗi **bên trong BEGIN ... COMMIT** trên PostgreSQL, giao dịch chuyển sang trạng thái thất bại. Các câu lệnh tiếp theo không chạy bình thường cho đến khi **ROLLBACK** hoặc **ROLLBACK TO SAVEPOINT** thích hợp.

Để thử riêng một lỗi và tiếp tục trong cùng giao dịch, thao tác theo từng bước:

~~~sql
BEGIN;
SAVEPOINT before_test;

-- Chạy câu INSERT cố ý vi phạm từ một ví dụ phía trên.
-- Nếu lỗi, thực thi câu sau để phục hồi đến savepoint:
ROLLBACK TO SAVEPOINT before_test;

-- Có thể tiếp tục tạo savepoint mới và thử lỗi khác.
ROLLBACK;
~~~

Các dòng này minh họa **trình tự thao tác**, không phải một script tự phát sinh lỗi: cần chạy câu INSERT lỗi **ở giữa SAVEPOINT và ROLLBACK TO SAVEPOINT**, rồi chủ động tiếp tục. Nếu công cụ SQL dừng toàn bộ lô khi gặp lỗi (ví dụ chế độ dừng theo lỗi), hãy thực thi từng câu riêng biệt. **ROLLBACK cuối cùng** hủy thay đổi của giao dịch thử nghiệm.

Nếu không dùng giao dịch tường minh và công cụ đang ở **autocommit**, một câu INSERT thất bại thường chỉ hủy chính câu đó; những câu khác vẫn có thể được thực thi tiếp.

## 10. Kiểm tra hàng vi phạm trước khi thêm ràng buộc

Trong migration thật, nên biến **định nghĩa constraint dự kiến** thành **truy vấn phát hiện vi phạm**, sau đó xử lý từng nhóm.

| Ràng buộc sắp thêm | Truy vấn phát hiện |
| --- | --- |
| stock_quantity >= 0 | WHERE stock_quantity < 0 |
| email NOT NULL | WHERE email IS NULL |
| UNIQUE(email) | GROUP BY email HAVING COUNT(*) > 1, cân nhắc NULL theo quy tắc UNIQUE |
| FK orders.customer_id → customers.customer_id | LEFT JOIN customers, lọc các hàng không có khách khớp |
| status IN (...) | WHERE status NOT IN (...) OR status IS NULL nếu yêu cầu cấm cả NULL |

Ví dụ tìm tồn kho âm:

~~~sql
SELECT product_id, sku, stock_quantity
FROM constraint_lab.products
WHERE stock_quantity < 0;
~~~

Ví dụ tìm email trùng khi định thêm UNIQUE:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM constraint_lab.customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Ví dụ tìm đơn tham chiếu khách không tồn tại:

~~~sql
SELECT o.order_id, o.customer_id
FROM constraint_lab.orders AS o
LEFT JOIN constraint_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Các truy vấn phát hiện này không thay thế constraint: chúng chỉ cung cấp **ảnh chụp dữ liệu tại thời điểm chạy**. Sau khi kiểm tra, giao dịch khác vẫn có thể chèn dữ liệu vi phạm nếu chưa có ràng buộc bảo vệ. Cần lập kế hoạch migration sao cho dữ liệu không bị thay đổi ngoài dự kiến trong khoảng giữa bước rà soát và bước áp constraint.

### NOT NULL và UNIQUE cần đối chiếu đúng ngữ nghĩa NULL

Một cột với CHECK:

~~~sql
CHECK (discount_percent BETWEEN 0 AND 100)
~~~

có thể nhận NULL vì biểu thức cho UNKNOWN. Nếu discount_percent bắt buộc có giá trị, cần thêm NOT NULL. Nếu là cột UNIQUE cho phép NULL, việc có nhiều dòng NULL có thể là **hợp lệ** trên PostgreSQL mặc định. Vì vậy, một truy vấn tìm “trùng” phải được viết theo đúng quy tắc ràng buộc sẽ áp dụng.

## 11. Thay ràng buộc khi quy tắc nghiệp vụ thay đổi

Giả sử đơn hàng bổ sung trạng thái **returned**. Với một CHECK kiểu IN đã tạo trước đó, PostgreSQL không cung cấp lệnh sửa trực tiếp nội dung biểu thức CHECK như chỉnh sửa một đoạn văn. Một cách rõ ràng là **thay ràng buộc cũ bằng ràng buộc mới**:

~~~sql
BEGIN;

ALTER TABLE constraint_lab.orders
DROP CONSTRAINT ck_orders_status;

ALTER TABLE constraint_lab.orders
ADD CONSTRAINT ck_orders_status
CHECK (status IN (
    'pending',
    'paid',
    'completed',
    'cancelled',
    'returned'
));

COMMIT;
~~~

Trong PostgreSQL, các lệnh thay đổi lược đồ như trên tham gia giao dịch. Nếu việc thêm CHECK mới thất bại và transaction bị rollback, việc xóa ràng buộc cũ trong cùng giao dịch cũng được rollback. Cách dùng giao dịch này hữu ích để tránh khoảng trống bảo vệ khi thay quy tắc, nhưng **thao tác ALTER TABLE có thể khóa bảng** và ảnh hưởng giao dịch đồng thời. Với bảng lớn, cần lên kế hoạch triển khai phù hợp.

Nếu chỉ **đổi tên** để thống nhất quy ước, dùng RENAME CONSTRAINT là đủ; không cần DROP rồi ADD làm thay đổi đối tượng.

### Có nên tạm bỏ constraint để nhập dữ liệu?

Trong môi trường thử nghiệm, bỏ constraint có thể giúp tái tạo một tình huống dữ liệu lỗi. Nhưng trong vận hành thật, việc tháo bảo vệ chỉ để nhập “cho xong” có thể tạo ra hàng mồ côi, trùng mã hoặc số lượng âm. Giải pháp thường tốt hơn là **sửa nguồn dữ liệu, cách nhập hoặc trình tự ghi**, rồi để constraint tiếp tục bảo vệ database.

Một ngoại lệ có kế hoạch là migration hai giai đoạn với **NOT VALID/VALIDATE** của PostgreSQL. Cách này vẫn kiểm tra thay đổi mới, đồng thời cho phép xử lý dữ liệu cũ có kiểm soát.

## 12. Hiểu cơ chế khóa ngoại khi thêm, xóa hoặc sửa hàng

Với một khóa ngoại:

~~~sql
CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES constraint_lab.customers(customer_id)
ON DELETE RESTRICT
~~~

có ít nhất hai hướng lỗi cần phân biệt:

1. **Chèn/sửa bảng con:** order.customer_id không có bản ghi tương ứng ở customers.
2. **Xóa/sửa bảng cha:** khách hàng đang được đơn hàng tham chiếu và quy tắc tham chiếu không cho phép thao tác đó.

Các lựa chọn phổ biến cho hành động khi xóa hàng cha:

| Quy tắc | Ý nghĩa khái quát |
| --- | --- |
| **RESTRICT** | Chặn xóa hàng cha khi còn hàng con tham chiếu |
| **NO ACTION** | Nếu cuối thời điểm kiểm tra còn vi phạm thì từ chối; có thể khác RESTRICT khi constraint được trì hoãn |
| **CASCADE** | Xóa các hàng con tham chiếu theo hành động xóa cha |
| **SET NULL** | Chuyển cột tham chiếu phía con thành NULL nếu thiết kế cột cho phép |
| **SET DEFAULT** | Chuyển cột tham chiếu phía con thành giá trị mặc định; giá trị đó vẫn phải thỏa khóa ngoại |

**CASCADE** không có nghĩa là “an toàn hơn”; nó có thể xóa nhiều dữ liệu liên quan. **SET NULL** cũng không hợp lệ nếu cột phía con là NOT NULL. Cần chọn quy tắc theo vòng đời dữ liệu của ứng dụng.

### Ràng buộc có thể kiểm tra ngay hoặc trì hoãn

Trong PostgreSQL, một số loại ràng buộc (đặc biệt **FOREIGN KEY**, cùng một số dạng UNIQUE/PRIMARY KEY) có thể khai báo **DEFERRABLE**. Khi được đặt ở chế độ deferred, việc kiểm tra có thể dời tới cuối giao dịch.

~~~sql
-- Cú pháp minh họa cho một FK mới:
CONSTRAINT fk_example_parent
FOREIGN KEY (parent_id)
REFERENCES parent_table(parent_id)
DEFERRABLE INITIALLY DEFERRED
~~~

**CHECK** và **NOT NULL** thông thường không có cùng cơ chế trì hoãn như FK trong PostgreSQL. Cần hiểu thời điểm kiểm tra để giải thích lỗi phát sinh ngay ở INSERT hay chỉ xuất hiện khi COMMIT. Trong bài này, các FK được tạo theo chế độ mặc định **không trì hoãn**.

## 13. Giới hạn và khác biệt phương ngữ SQL

Các ví dụ chính bên trên là PostgreSQL. Phần lớn ý tưởng về PRIMARY KEY, UNIQUE, FOREIGN KEY và CHECK có trong nhiều RDBMS, nhưng lệnh quản lý constraint **không hoàn toàn giống nhau**.

| Hệ quản trị | Điểm đáng chú ý khi thêm/xóa/kiểm tra |
| --- | --- |
| **PostgreSQL 15+** | ALTER TABLE ... ADD/DROP/RENAME CONSTRAINT; CHECK/FK có thể dùng NOT VALID và VALIDATE CONSTRAINT; lỗi có SQLSTATE lớp 23 |
| **MySQL 8.0** | Cú pháp DROP FOREIGN KEY, DROP CHECK và xử lý UNIQUE qua chỉ mục có khác biệt; việc thực thi CHECK có lịch sử thay đổi theo phiên bản, từ MySQL 8.0.16 mới bắt đầu thực thi CHECK |
| **SQL Server** | ADD/DROP CONSTRAINT qua ALTER TABLE; có các trạng thái ENABLE/DISABLE hoặc CHECK/NOCHECK đặc thù; cần phân biệt ràng buộc đã kiểm chứng (*trusted*) với chưa kiểm chứng |
| **SQLite** | Khả năng ALTER TABLE trực tiếp để thêm/xóa các loại constraint bị hạn chế; nhiều thay đổi cần quy trình tạo bảng mới, chép dữ liệu, thay bảng và tạo lại đối tượng phụ thuộc |

Ví dụ **không thể coi** câu PostgreSQL:

~~~sql
ALTER TABLE constraint_lab.products
DROP CONSTRAINT ck_products_stock_nonnegative;
~~~

là cú pháp thay thế nguyên văn cho mọi lệnh xóa CHECK trên MySQL, SQLite hoặc SQL Server. Một migration dùng chung nhiều hệ cần nhánh lệnh cho từng phương ngữ, kiểm tra phiên bản và cơ chế transaction/locking tương ứng.

### Đặt tên ràng buộc giúp việc chuyển đổi dễ kiểm soát hơn

Quy ước **pk_**, **uq_**, **fk_**, **ck_** có thể giữ ở mức thiết kế cho nhiều hệ. Tuy vậy, **độ dài định danh, phạm vi trùng tên, cú pháp đặt tên và tên chỉ mục hỗ trợ** có thể khác. Do đó, nên giữ tên ngắn, có ý nghĩa, và định nghĩa chúng trong công cụ migration thay vì dựa hoàn toàn vào tên hệ quản trị tự phát sinh.

## 14. Làm việc với lỗi ràng buộc trong ứng dụng

Ràng buộc là tuyến bảo vệ cuối cùng ở database. Ứng dụng vẫn nên kiểm tra dữ liệu sớm để đưa ra thông báo rõ ràng, nhưng kiểm tra ở ứng dụng **không thay thế** UNIQUE/FK/CHECK/NOT NULL vì nhiều yêu cầu có thể được gửi đồng thời.

Ví dụ hai tiến trình cùng làm việc:

1. Tiến trình A kiểm tra email **an@example.test** chưa tồn tại.
2. Tiến trình B cũng kiểm tra email đó chưa tồn tại.
3. Cả hai cùng thử INSERT.
4. **UNIQUE** ở database chỉ cho phép trạng thái cuối hợp lệ; một yêu cầu phải được xử lý là trùng email.

Đây là lý do không nên viết ứng dụng theo giả định “đã SELECT kiểm tra nên INSERT chắc chắn thành công”.

Trong PostgreSQL, khi bắt lỗi từ driver, nên ưu tiên **SQLSTATE** và metadata cấu trúc của lỗi thay vì chỉ so khớp nguyên chuỗi thông báo. Ví dụ trong Java/JDBC, **SQLException.getSQLState()** có thể cung cấp mã SQLSTATE. Tên constraint có thể được truy xuất qua API đặc thù của driver khi hỗ trợ.

| SQLSTATE | Hướng phản hồi nghiệp vụ |
| --- | --- |
| 23505 | Giá trị bắt buộc duy nhất đã tồn tại; chỉ rõ trường liên quan |
| 23503 | Khóa tham chiếu không hợp lệ hoặc bản ghi đang được tham chiếu |
| 23514 | Một quy tắc kiểm tra bị vi phạm; rà soát miền giá trị |
| 23502 | Thiếu trường bắt buộc |

Không nên trả nguyên thông báo database cho người dùng cuối nếu nó chứa tên bảng nội bộ hay dữ liệu nhạy cảm. Có thể ghi chi tiết kỹ thuật trong log nội bộ, còn giao diện trình bày thông báo phù hợp như “Email đã được sử dụng” hoặc “Sản phẩm không tồn tại”.

**Tên constraint giúp nối giữa lỗi kỹ thuật và quy tắc nghiệp vụ.** Ví dụ 23505 + **uq_customers_email** cho phép ứng dụng nhận diện trùng email; 23505 + **pk_orders** lại chỉ sự cố khác.

## 15. Quy trình an toàn khi thay ràng buộc trên bảng có dữ liệu

Một quy trình hợp lý thường gồm:

1. **Nêu quy tắc bằng câu đơn giản.** Ví dụ: “Số lượng tồn kho không âm”.
2. **Chọn loại constraint phù hợp.** CHECK cho biểu thức trong hàng, FK cho quan hệ, UNIQUE cho tính duy nhất, NOT NULL cho trường bắt buộc.
3. **Chọn tên nhất quán.** Ví dụ ck_products_stock_nonnegative.
4. **Kiểm tra dữ liệu cũ.** Viết SELECT tìm hàng vi phạm và xác định cách xử lý đúng nghiệp vụ.
5. **Lập migration và cân nhắc khóa bảng.** Với PostgreSQL, có thể dùng NOT VALID/VALIDATE cho CHECK/FK khi cần.
6. **Thêm hoặc thay constraint.** Đảm bảo câu lệnh đúng phương ngữ và thứ tự thao tác.
7. **Đọc lại metadata.** Kiểm tra tên, định nghĩa và trạng thái xác nhận để bảo đảm cơ sở dữ liệu đã phản ánh thay đổi.
8. **Theo dõi lỗi từ các thao tác ghi thực tế.** Dùng SQLSTATE và tên constraint để phân loại và sửa nguyên nhân.

Một ràng buộc mới chỉ có ý nghĩa khi **dữ liệu hiện có đã được xử lý** và **những thay đổi mới tiếp tục bị kiểm soát**.

## 16. Bài tập thực hành

Các bài dưới đây sử dụng schema **constraint_lab** đã tạo ở phần 4. Với bài có chủ đích gây lỗi, hãy thực hiện trong môi trường riêng; có thể dùng SAVEPOINT hoặc quay lại dữ liệu mẫu khi cần.

1. Dùng INFORMATION_SCHEMA liệt kê toàn bộ ràng buộc của **constraint_lab.orders**. Tên nào là PRIMARY KEY, FOREIGN KEY và CHECK?
2. Tra pg_constraint để xem định nghĩa của **ck_orders_status** và **fk_orders_customer**.
3. Thêm CHECK **stock_quantity >= 0** cho bảng products với tên **ck_products_stock_nonnegative**.
4. Trước khi thêm CHECK ở bài 3, thử cố ý cập nhật stock_quantity của sản phẩm 102 thành -3. Giải thích vì sao ADD CONSTRAINT bình thường thất bại. Sau đó thực hành con đường **NOT VALID → sửa dữ liệu → VALIDATE**.
5. Thêm cột **external_code** vào customers, gán hai mã khác nhau, rồi tạo **uq_customers_external_code**. Dự đoán điều gì xảy ra nếu khách thứ ba nhận mã đã dùng.
6. Tạo bảng customer_notes, nhập một ghi chú tham chiếu customer_id = 999, rồi thử thêm FK. Viết truy vấn LEFT JOIN tìm dòng mồ côi; sửa dữ liệu và xác nhận constraint.
7. Đổi tên CHECK stock_quantity thành **ck_products_stock_min_zero**, kiểm tra metadata, sau đó đổi lại tên ban đầu.
8. Xóa CHECK stock_quantity trên **bảng thực hành**, thử cập nhật số lượng âm, sau đó sửa dữ liệu và thêm lại CHECK. Giải thích vì sao thao tác xóa ràng buộc trên bảng thật cần kế hoạch.
9. Thử INSERT một khách có **email trùng**, một đơn có **customer_id không tồn tại**, và một dòng đơn có **quantity = 0**. Ghi SQLSTATE và tên constraint tương ứng.
10. Thử INSERT một khách có **full_name = NULL**. So sánh thông báo lỗi với trường hợp full_name là chuỗi toàn dấu cách.
11. Chạy câu DELETE khách hàng đang có đơn. Đọc thông báo FK và giải thích vai trò của **ON DELETE RESTRICT**.
12. Thay CHECK trạng thái để bổ sung **'returned'** trong một giao dịch. Đọc metadata trước và sau thay đổi.
13. Giải thích tại sao **CHECK (unit_price >= 0)** không nhất thiết loại NULL và khi nào cần dùng thêm NOT NULL.
14. Tìm hiểu hệ quản trị bạn đang sử dụng ngoài PostgreSQL: cú pháp **DROP CHECK**, **DROP FOREIGN KEY** và cơ chế xác minh constraint mới khác như thế nào?

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Nếu tạo UNIQUE mà dữ liệu cũ có hai email giống nhau thì chuyện gì xảy ra?

**Trả lời:** Lệnh tạo UNIQUE thường thất bại vì dữ liệu hiện tại vi phạm. Cần phát hiện và sửa trùng trước khi thêm ràng buộc.

**Câu 2:** CHECK (stock_quantity >= 0) NOT VALID có cho phép cập nhật mới một hàng stock_quantity = -5 không?

**Trả lời:** **Không.** Trong PostgreSQL, NOT VALID bỏ qua bước xác minh toàn bộ dữ liệu cũ ở thời điểm thêm; các hàng mới hoặc cập nhật vẫn phải đáp ứng CHECK.

**Câu 3:** SQLSTATE 23505 đủ để khẳng định lỗi là trùng email không?

**Trả lời:** **Không.** Mã đó còn bao gồm vi phạm PRIMARY KEY hoặc UNIQUE khác. Cần đọc thêm tên ràng buộc và thông tin bảng/cột.

**Câu 4:** Xóa constraint có tự động xóa dữ liệu đang nằm trong bảng không?

**Trả lời:** **Không.** Xóa constraint chỉ bỏ cơ chế kiểm tra đó, trừ những tác động phụ thuộc đặc thù khi dùng CASCADE cho đối tượng lược đồ. Dữ liệu hàng không bị xóa đơn thuần vì DROP CONSTRAINT.

**Câu 5:** Có thể dùng cùng cú pháp DROP CONSTRAINT của PostgreSQL để xóa mọi loại ràng buộc trên SQLite không?

**Trả lời:** **Không.** SQLite có giới hạn ALTER TABLE; một số thay đổi phải xây dựng lại bảng.

**Câu 6:** Vì sao cần đặt tên thay vì để hệ quản trị tự sinh tên?

**Trả lời:** Tên ổn định và có ý nghĩa giúp đọc lỗi, viết migration, tra cứu metadata và phân biệt những quy tắc có cùng mã lỗi.

## 18. Ghi nhớ cốt lõi

**Ràng buộc là hợp đồng kiểm soát tính hợp lệ của dữ liệu tại database.** Đặt tên theo quy ước **pk_/uq_/fk_/ck_** giúp hợp đồng ấy có thể đọc hiểu và quản lý. **CREATE TABLE** định nghĩa ràng buộc ngay từ đầu; **ALTER TABLE ADD/DROP/RENAME CONSTRAINT** giúp thay đổi lược đồ khi yêu cầu phát triển, còn **SET/DROP NOT NULL** xử lý tính bắt buộc của cột trong PostgreSQL 15–17.

Khi thêm constraint trên bảng đã có dữ liệu, phải xem xét **dữ liệu cũ**, đặc biệt với CHECK, FK và UNIQUE. PostgreSQL hỗ trợ **NOT VALID rồi VALIDATE CONSTRAINT** cho một số loại ràng buộc nhằm triển khai theo giai đoạn. Khi thao tác ghi thất bại, hãy đọc **SQLSTATE**, **tên constraint** và thông tin lỗi để hiểu nguyên nhân; không bỏ constraint chỉ để che vấn đề dữ liệu.
