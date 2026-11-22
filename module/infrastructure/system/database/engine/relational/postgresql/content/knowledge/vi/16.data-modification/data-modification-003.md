# UPDATE, biểu thức gán và điều kiện chọn hàng trong PostgreSQL

`UPDATE` là lệnh SQL dùng để **thay đổi giá trị của các cột trong những hàng đã tồn tại**. Nếu `INSERT` tạo hàng mới và `DELETE` loại hàng, thì `UPDATE` chỉnh sửa thông tin hiện có mà không cần thay thế toàn bộ bảng.

Trong ứng dụng PostgreSQL, lệnh này xuất hiện ở nhiều nghiệp vụ:

- Đổi tên, địa chỉ, trạng thái hoặc phân khúc khách hàng.
- Chuyển đơn hàng từ `pending` sang `paid` theo quy tắc trạng thái.
- Tăng/giảm tồn kho dựa trên giá trị hiện tại.
- Tính lại số tiền từ nhiều cột hoặc từ dữ liệu ở bảng liên quan.
- Cập nhật thuộc tính trong cột `jsonb`.
- Đồng bộ giá trị từ bảng khác bằng `UPDATE ... FROM`.
- Ghi nhận những hàng thực sự được sửa qua `RETURNING`.

Ba thành phần quan trọng nhất của câu lệnh là:

~~~sql
UPDATE table_name
SET column_name = expression
WHERE condition;
~~~

**`UPDATE`** xác định bảng đích; **`SET`** xác định giá trị mới; **`WHERE`** chọn những hàng được phép thay đổi. Trong các thao tác ghi dữ liệu, hiểu đúng `WHERE` thường quan trọng hơn việc biết nhiều cú pháp: thiếu hoặc sai điều kiện có thể biến một lần sửa một đơn hàng thành cập nhật hàng triệu hàng.

Bài học sẽ đi từ cách gán giá trị cơ bản đến biểu thức, xử lý `NULL`, `CASE`, `COALESCE`, cập nhật từ bảng khác, truy vấn con, `RETURNING`, concurrency, kiểm soát transaction và các lỗi thực tế.

## 1. Phân biệt ba câu hỏi của UPDATE

Trước khi viết một lệnh UPDATE, hãy trả lời:

1. **Sửa bảng nào?** Một statement `UPDATE` có một bảng đích trực tiếp; các thao tác lan truyền do trigger/foreign key là hệ quả riêng.
2. **Sửa những cột nào, theo công thức gì?** Cột mới có thể nhận hằng số, giá trị cột cũ, phép tính, `CASE`, `DEFAULT`, truy vấn con hoặc dữ liệu từ bảng `FROM`.
3. **Sửa những hàng nào?** `WHERE` chọn các hàng thỏa điều kiện tại thời điểm câu lệnh xử lý theo cơ chế transaction của PostgreSQL.

Ví dụ:

~~~sql
UPDATE update_lab.products
SET stock_qty = stock_qty - 2
WHERE product_id = 101
  AND stock_qty >= 2;
~~~

Câu lệnh có ý nghĩa:

- Bảng đích: `update_lab.products`.
- Cột thay đổi: `stock_qty`.
- Giá trị mới: tồn kho hiện tại trừ 2.
- Hàng được chọn: sản phẩm 101 **và** hiện còn ít nhất 2 đơn vị.

Biểu thức `stock_qty = stock_qty - 2` **không** tự có nghĩa “lấy giá trị cũ từ lúc người dùng mở giao diện”. Nó được PostgreSQL đánh giá trên phiên bản hàng được câu lệnh xử lý, có tính đến các quy tắc khóa hàng và isolation phù hợp.

## 2. Chuẩn bị một bộ dữ liệu thực hành an toàn

Toàn bộ ví dụ dùng schema `update_lab` trong **database PostgreSQL riêng cho thực hành**. Phần chuẩn bị có `DROP SCHEMA ... CASCADE` để kết quả tái lập được. **Không chạy đoạn này trong database sản xuất hoặc schema chứa dữ liệu cần giữ.**

### 2.1. Tạo bảng

~~~sql
-- Chỉ chạy sau khi xác nhận đang ở database lab.
DROP SCHEMA IF EXISTS update_lab CASCADE;
CREATE SCHEMA update_lab;

CREATE TABLE update_lab.customers (
    customer_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    city text,
    tier text NOT NULL DEFAULT 'standard'
        CHECK (tier IN ('standard', 'silver', 'gold')),
    loyalty_points integer NOT NULL DEFAULT 0
        CHECK (loyalty_points >= 0),
    phone text,
    is_active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE update_lab.products (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    list_price numeric(12,2) NOT NULL CHECK (list_price >= 0),
    sale_price numeric(12,2)
        CHECK (sale_price IS NULL OR sale_price >= 0),
    stock_qty integer NOT NULL CHECK (stock_qty >= 0),
    is_active boolean NOT NULL DEFAULT true,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE update_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES update_lab.customers(customer_id),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    total_amount numeric(12,2) NOT NULL DEFAULT 0
        CHECK (total_amount >= 0),
    note text,
    created_at timestamptz NOT NULL,
    paid_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE update_lab.order_items (
    order_id integer NOT NULL
        REFERENCES update_lab.orders(order_id),
    product_id integer NOT NULL
        REFERENCES update_lab.products(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE update_lab.product_discounts (
    product_id integer PRIMARY KEY
        REFERENCES update_lab.products(product_id),
    discount_percent numeric(5,2) NOT NULL
        CHECK (discount_percent BETWEEN 0 AND 100)
);
~~~

Các bảng có mục đích rõ ràng:

| Bảng | Vai trò |
| --- | --- |
| `customers` | Cập nhật hằng, `NULL`, `DEFAULT`, `CASE`, điều kiện chọn khách |
| `products` | Phép toán số học, giảm tồn kho, cập nhật `jsonb`, giá bán |
| `orders` | Điều kiện trạng thái, cập nhật từ dữ liệu chi tiết, `RETURNING` |
| `order_items` | Nguồn 1:N để minh họa `UPDATE ... FROM` và tổng hợp |
| `product_discounts` | Nguồn một hàng cho mỗi sản phẩm khi cập nhật giá |

Các `CHECK`, khóa chính và khóa ngoại bảo vệ một số bất biến. Một câu `UPDATE` hợp lệ về cú pháp vẫn có thể thất bại nếu kết quả vi phạm các ràng buộc này.

### 2.2. Nạp dữ liệu cố định

~~~sql
INSERT INTO update_lab.customers
    (customer_id, email, full_name, city, tier,
     loyalty_points, phone, is_active)
VALUES
    (1, 'an@example.test',   'An',   'HCM', 'gold',     120, NULL, true),
    (2, 'binh@example.test', 'Binh', 'HAN', 'silver',    60, NULL, true),
    (3, 'chi@example.test',  'Chi',  'DNG', 'standard',   0, NULL, false),
    (4, 'dung@example.test', 'Dung', 'HCM', 'standard',  10, NULL, true);

INSERT INTO update_lab.products
    (product_id, product_name, list_price,
     sale_price, stock_qty, is_active, attributes)
VALUES
    (101, 'Coffee', 30.00, NULL, 10, true,
     '{"category":"beverage","color":"brown"}'::jsonb),
    (102, 'Tea',    20.00, NULL,  5, true,
     '{"category":"beverage","color":"green"}'::jsonb),
    (103, 'Cup',    12.00, NULL,  0, false,
     '{"category":"accessory","color":"white"}'::jsonb);

INSERT INTO update_lab.orders
    (order_id, customer_id, status, total_amount,
     note, created_at, paid_at)
VALUES
    (1001, 1, 'pending',   80.00, NULL,
     '2026-11-01 08:00:00+00', NULL),
    (1002, 1, 'paid',      35.00, 'Paid at counter',
     '2026-11-02 09:00:00+00', '2026-11-02 09:20:00+00'),
    (1003, 2, 'pending',   60.00, NULL,
     '2026-11-03 10:00:00+00', NULL),
    (1004, 3, 'cancelled', 20.00, NULL,
     '2026-11-04 11:00:00+00', NULL);

INSERT INTO update_lab.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 101, 2, 30.00),
    (1001, 102, 1, 20.00),
    (1002, 101, 1, 35.00),
    (1003, 102, 3, 20.00),
    (1004, 103, 1, 20.00);

INSERT INTO update_lab.product_discounts
    (product_id, discount_percent)
VALUES
    (101, 10.00),
    (102,  5.00);
~~~

Dữ liệu khởi tạo:

| Đơn | Khách | Trạng thái | Tổng | Số dòng chi tiết |
| ---: | ---: | --- | ---: | ---: |
| 1001 | 1 (An) | pending | 80.00 | 2 |
| 1002 | 1 (An) | paid | 35.00 | 1 |
| 1003 | 2 (Binh) | pending | 60.00 | 1 |
| 1004 | 3 (Chi) | cancelled | 20.00 | 1 |

Sản phẩm 101 có tồn kho 10, sản phẩm 102 có tồn kho 5 và sản phẩm 103 có tồn kho 0.

**Quy ước thực hành:** tất cả ví dụ làm thay đổi dữ liệu sau phần seed nên được chạy **riêng từng ví dụ** trong `BEGIN; ... ROLLBACK;`, trừ khi bạn cố ý muốn lưu kết quả. Như vậy các bài tiếp theo luôn xuất phát từ dữ liệu mẫu ban đầu.

## 3. Cú pháp UPDATE trong PostgreSQL

Dạng đơn giản:

~~~sql
UPDATE update_lab.customers
SET city = 'Hue'
WHERE customer_id = 2;
~~~

Dạng có alias, nhiều phép gán và trả kết quả:

~~~sql
UPDATE update_lab.customers AS c
SET
    city = 'Hue',
    updated_at = now()
WHERE c.customer_id = 2
RETURNING
    c.customer_id,
    c.full_name,
    c.city,
    c.updated_at;
~~~

Cấu trúc tổng quát thường dùng:

~~~sql
WITH optional_cte AS (
    SELECT ...
)
UPDATE target_table AS t
SET
    column_a = expression_a,
    column_b = expression_b
FROM optional_source AS s
WHERE selection_condition
RETURNING t.column_a, t.column_b;
~~~

Không phải câu UPDATE nào cũng cần `WITH`, `FROM` hoặc `RETURNING`. Nhưng **`SET` là bắt buộc**, và **`WHERE` phải được chủ động cân nhắc**.

### UPDATE không có WHERE

~~~sql
-- NGUY HIỂM nếu không thật sự muốn sửa mọi hàng.
UPDATE update_lab.customers
SET tier = 'standard';
~~~

Câu này chọn **toàn bộ hàng** của bảng khách hàng. Không có `WHERE` không phải lỗi cú pháp; đó là một lệnh cập nhật hàng loạt hoàn toàn hợp lệ.

Nếu nhiệm vụ chỉ muốn sửa khách hàng 2, thiếu `WHERE customer_id = 2` là một lỗi nghiệp vụ nghiêm trọng.

## 4. SET với một giá trị hằng

Thử đổi thành phố của Binh:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET city = 'Hue'
WHERE customer_id = 2;

SELECT customer_id, full_name, city
FROM update_lab.customers
WHERE customer_id = 2;

ROLLBACK;
~~~

Trong transaction trước `ROLLBACK`, Binh có `city = 'Hue'`. Sau rollback, thành phố ban đầu `HAN` được khôi phục.

### UPDATE giữ nguyên các cột không nêu trong SET

Nếu chỉ gán `city`, những cột như `email`, `tier`, `loyalty_points` không tự thay đổi — ngoại trừ các thay đổi do **trigger/rules** được cấu hình riêng trong hệ thống.

Không cần truyền lại toàn bộ hàng để sửa một cột. Đây là một ưu điểm của `UPDATE` so với việc ứng dụng cố dựng lại một bản ghi mới từ các giá trị đã đọc trước đó.

## 5. SET nhiều cột cùng lúc

Có thể gán nhiều cột trong một statement:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET
    full_name = 'Binh Tran',
    city = 'Hue',
    tier = 'gold',
    loyalty_points = loyalty_points + 20,
    updated_at = now()
WHERE c.customer_id = 2
RETURNING
    c.customer_id,
    c.full_name,
    c.city,
    c.tier,
    c.loyalty_points;

ROLLBACK;
~~~

Với seed, trước cập nhật Binh có 60 điểm, nên `loyalty_points` tạm trở thành **80**.

Mỗi cột mục tiêu chỉ nên xuất hiện một lần trong danh sách `SET`. Các biểu thức phía phải có thể kết hợp hằng số, tham số ứng dụng, cột hiện tại và hàm PostgreSQL.

### Không đặt alias ở bên trái dấu bằng trong SET

Cú pháp đúng:

~~~sql
UPDATE update_lab.customers AS c
SET city = 'Hue'
WHERE c.customer_id = 2;
~~~

Cách viết sai trong PostgreSQL:

~~~sql
-- Cố ý sai: không được dùng c.city làm tên cột đích.
UPDATE update_lab.customers AS c
SET c.city = 'Hue'
WHERE c.customer_id = 2;
~~~

Bên trái `=` ở danh sách `SET` phải là **tên cột đích không có tiền tố alias**. Alias vẫn dùng được để tham chiếu hàng/cột trong `WHERE`, `FROM`, `RETURNING` và biểu thức bên phải.

## 6. Biểu thức gán được đánh giá từ hàng trước cập nhật

Giả sử có hai cột số `a`, `b` và muốn hoán đổi giá trị:

~~~sql
CREATE TABLE update_lab.swap_demo (
    demo_id integer PRIMARY KEY,
    a integer NOT NULL,
    b integer NOT NULL
);

INSERT INTO update_lab.swap_demo (demo_id, a, b)
VALUES (1, 10, 20);
~~~

Dùng:

~~~sql
BEGIN;

UPDATE update_lab.swap_demo
SET
    a = b,
    b = a
WHERE demo_id = 1
RETURNING a, b;

ROLLBACK;
~~~

Kết quả là **a = 20, b = 10**.

Trong một câu `UPDATE`, các biểu thức gán đọc các giá trị của **phiên bản hàng trước khi câu UPDATE áp dụng các phép gán cho hàng đó**, không vận hành kiểu “gán a rồi lấy a mới để gán b”.

Do vậy:

~~~sql
SET
    a = a + 1,
    b = a + 1
~~~

đặt cả hai cột dựa vào **a cũ** (không phải b = a mới rồi lại cộng). Đây là tính chất cần nhớ khi có nhiều công thức gán liên quan nhau.

### Gán theo danh sách cột

PostgreSQL cũng hỗ trợ cú pháp dạng hàng:

~~~sql
BEGIN;

UPDATE update_lab.swap_demo
SET (a, b) = (b, a)
WHERE demo_id = 1
RETURNING a, b;

ROLLBACK;
~~~

Kết quả vẫn là hoán đổi 20 và 10. Cách này hữu ích khi các cột đi cùng nhau và có thể được tính từ một nguồn tuple hoặc subquery.

## 7. Phép toán số học trong SET

Biểu thức gán có thể dùng các phép tính thông thường:

~~~sql
BEGIN;

UPDATE update_lab.products
SET
    list_price = ROUND(list_price * 1.10, 2),
    updated_at = now()
WHERE product_id = 101
RETURNING product_id, list_price;

ROLLBACK;
~~~

Giá Coffee từ **30.00** lên **33.00**.

Các ví dụ thường thấy:

~~~sql
SET stock_qty = stock_qty + 5
SET stock_qty = stock_qty - 2
SET loyalty_points = loyalty_points + 10
SET list_price = ROUND(list_price * 0.95, 2)
~~~

Hãy dùng kiểu dữ liệu phù hợp: tiền nên được tính với `numeric` khi cần độ chính xác thập phân có kiểm soát; tránh chuyển sang phép tính floating-point tùy tiện cho nghiệp vụ tài chính.

### Kiểm tra ràng buộc kết quả

Bảng `products` khai báo:

~~~sql
stock_qty integer NOT NULL CHECK (stock_qty >= 0)
~~~

Nếu chạy `SET stock_qty = stock_qty - 100` cho hàng chỉ còn 10, PostgreSQL sẽ từ chối vì vi phạm `CHECK`. Tuy nhiên, việc để lỗi constraint xảy ra không phải giao diện nghiệp vụ tốt bằng kiểm tra điều kiện trước khi gán.

Ta sẽ dùng `WHERE stock_qty >= requested_qty` để mô hình hóa nghiệp vụ xuất kho rõ ràng ở mục sau.

## 8. WHERE chọn hàng; điều kiện đúng mới được cập nhật

Giả sử chỉ giảm 3 đơn vị của sản phẩm Coffee:

~~~sql
BEGIN;

UPDATE update_lab.products
SET stock_qty = stock_qty - 3
WHERE product_id = 101
  AND stock_qty >= 3
RETURNING product_id, stock_qty;

ROLLBACK;
~~~

Trong lab, tồn kho Coffee từ 10 còn **7**.

Nếu đổi `product_id` thành 103, sản phẩm Cup có `stock_qty = 0`, nên `WHERE stock_qty >= 3` không thỏa; kết quả UPDATE là **0 hàng**. Không phải lỗi SQL.

### WHERE là điều kiện lựa chọn hàng, không phải điều kiện về giá trị sau UPDATE

Câu:

~~~sql
UPDATE update_lab.products
SET stock_qty = stock_qty - 3
WHERE stock_qty >= 3;
~~~

chọn các hàng **đang** có tồn kho từ 3 trở lên rồi trừ 3. Nếu một hàng có stock 3, hàng đó **được cập nhật thành 0** và không bị loại khỏi tập cập nhật chỉ vì giá trị mới không còn thỏa `stock_qty >= 3`.

Điểm này khác với suy luận sai rằng PostgreSQL sẽ cứ kiểm tra `WHERE` lại sau mỗi phép gán và “rút” hàng khỏi UPDATE.

## 9. AND, OR và dấu ngoặc trong WHERE

Cần phân biệt thứ tự ưu tiên logic:

~~~sql
WHERE condition_a AND condition_b OR condition_c
~~~

Trong SQL, `AND` có độ ưu tiên cao hơn `OR`. Biểu thức trên tương đương:

~~~sql
WHERE (condition_a AND condition_b) OR condition_c
~~~

không phải:

~~~sql
WHERE condition_a AND (condition_b OR condition_c)
~~~

### Ví dụ nguy hiểm

Yêu cầu: chỉ đổi trạng thái các đơn **của khách hàng 1** đang `pending` hoặc `cancelled`.

Không nên viết:

~~~sql
-- Sai ý nghĩa: có thể chọn mọi đơn cancelled,
-- kể cả đơn của khách hàng khác.
UPDATE update_lab.orders
SET status = 'paid'
WHERE customer_id = 1
  AND status = 'pending'
   OR status = 'cancelled';
~~~

Với seed, điều kiện có thể bao gồm cả đơn **1004 của Chi**, vì `status = 'cancelled'` thỏa nhánh `OR` độc lập.

Viết đúng:

~~~sql
BEGIN;

UPDATE update_lab.orders
SET status = 'paid'
WHERE customer_id = 1
  AND status IN ('pending', 'cancelled')
RETURNING order_id, customer_id, status;

ROLLBACK;
~~~

Hoặc dùng dấu ngoặc:

~~~sql
WHERE customer_id = 1
  AND (status = 'pending' OR status = 'cancelled')
~~~

**Lưu ý nghiệp vụ:** việc chuyển đơn `cancelled` thành `paid` có thể không hợp lệ trong hệ thống thật; ví dụ này chỉ nhằm minh họa logic lựa chọn hàng. Trong workflow thực tế phải giới hạn các bước chuyển trạng thái được phép.

## 10. WHERE với NULL: dùng IS NULL và IS NOT NULL

Trong SQL, `NULL` biểu diễn giá trị chưa biết hoặc không có, chứ không phải một chuỗi rỗng. So sánh thông thường với `NULL` không trả TRUE:

~~~sql
-- Sai: không tìm các hàng phone NULL.
WHERE phone = NULL
~~~

Đúng:

~~~sql
WHERE phone IS NULL
~~~

Thực hành điền số điện thoại **chỉ cho khách hàng chưa có số**:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET phone = '000-EXAMPLE'
WHERE customer_id = 1
  AND phone IS NULL
RETURNING customer_id, phone;

ROLLBACK;
~~~

Nếu `phone` đã có giá trị, câu lệnh cập nhật 0 hàng.

### Three-valued logic

Một điều kiện SQL có thể đánh giá thành **TRUE, FALSE hoặc UNKNOWN (NULL)**. `UPDATE ... WHERE` chỉ chọn hàng có điều kiện là **TRUE**. FALSE và UNKNOWN đều không được chọn.

Ví dụ:

~~~sql
WHERE phone <> '000-EXAMPLE'
~~~

không chọn khách hàng có `phone IS NULL`, vì phép `NULL <> '000-EXAMPLE'` không trả TRUE.

Nếu muốn xét cả trường hợp NULL, `IS DISTINCT FROM` thường là công cụ tốt hơn.

## 11. IS DISTINCT FROM: so sánh có xét NULL

Giả sử muốn đặt `city = 'HCM'` cho khách hàng 4 nếu giá trị hiện tại khác HCM. Ta có thể dùng:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET city = 'HCM'
WHERE customer_id = 4
  AND city IS DISTINCT FROM 'HCM'
RETURNING customer_id, city;

ROLLBACK;
~~~

Với seed, khách hàng 4 đã ở HCM nên **0 hàng** được cập nhật.

`IS DISTINCT FROM` có ngữ nghĩa rõ ràng khi một trong hai vế là NULL:

| Giá trị hiện tại | Giá trị mới | `IS DISTINCT FROM` |
| --- | --- | --- |
| HCM | HCM | FALSE |
| HAN | HCM | TRUE |
| NULL | HCM | TRUE |
| NULL | NULL | FALSE |

Trong khi đó `city <> 'HCM'` trả UNKNOWN cho hàng có `city IS NULL`.

### Tránh UPDATE khi dữ liệu không thực sự cần thay đổi

~~~sql
BEGIN;

UPDATE update_lab.customers
SET
    city = 'HCM',
    updated_at = now()
WHERE customer_id = 1
  AND city IS DISTINCT FROM 'HCM'
RETURNING customer_id, city, updated_at;

ROLLBACK;
~~~

Khách hàng An đã có city HCM nên query không cập nhật, cũng không đụng `updated_at`.

Đây là mô hình hữu ích khi cần tránh ghi lại hàng không đổi, tránh chạy trigger `UPDATE` không cần thiết và giảm overhead. Tuy nhiên không nên thêm `IS DISTINCT FROM` một cách máy móc nếu nghiệp vụ **muốn** ghi dấu một sự kiện “đã xác nhận lại” dù giá trị không đổi.

## 12. SET NULL và SET DEFAULT

### 12.1. Đặt một cột về NULL

~~~sql
BEGIN;

UPDATE update_lab.customers
SET phone = NULL
WHERE customer_id = 2
RETURNING customer_id, phone;

ROLLBACK;
~~~

Câu này hợp lệ vì `phone` được phép NULL.

Nếu thử:

~~~sql
-- Cố ý lỗi: full_name khai báo NOT NULL.
UPDATE update_lab.customers
SET full_name = NULL
WHERE customer_id = 2;
~~~

PostgreSQL sẽ báo lỗi vi phạm `NOT NULL`. Không thể dùng SET để bỏ qua constraint của bảng.

### 12.2. Trả cột về DEFAULT

Giả sử khách hàng 1 đang ở tier `gold`, muốn đưa về mặc định `standard`:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET tier = DEFAULT
WHERE customer_id = 1
RETURNING customer_id, tier;

ROLLBACK;
~~~

Bảng khai báo `tier text NOT NULL DEFAULT 'standard'` nên giá trị mới là `standard`.

**DEFAULT không phải “giá trị gốc của hàng lúc vừa INSERT”.** Nó là biểu thức mặc định của **cột theo schema hiện tại**. Nếu default bị thay đổi qua migration, `SET column = DEFAULT` dùng định nghĩa đang có.

Nếu cột không có default tường minh, `DEFAULT` thường tương đương `NULL`; điều đó sẽ thất bại nếu cột có `NOT NULL` hoặc constraint không cho phép.

## 13. CASE: gán giá trị khác nhau cho từng hàng

Một câu UPDATE có thể chọn nhiều hàng nhưng áp dụng các nhánh gán khác nhau bằng `CASE`.

Ví dụ phân khúc khách hàng dựa vào điểm tích lũy:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET
    tier = CASE
        WHEN c.loyalty_points >= 100 THEN 'gold'
        WHEN c.loyalty_points >= 50 THEN 'silver'
        ELSE 'standard'
    END,
    updated_at = now()
WHERE c.is_active = true
RETURNING
    c.customer_id,
    c.loyalty_points,
    c.tier;

ROLLBACK;
~~~

Kết quả với khách hàng đang hoạt động:

| customer_id | points | tier sau cập nhật |
| ---: | ---: | --- |
| 1 | 120 | gold |
| 2 | 60 | silver |
| 4 | 10 | standard |

Khách hàng Chi (3) không hoạt động nên không được chọn.

### Thứ tự WHEN rất quan trọng

Nếu viết:

~~~sql
CASE
    WHEN loyalty_points >= 50 THEN 'silver'
    WHEN loyalty_points >= 100 THEN 'gold'
    ELSE 'standard'
END
~~~

thì người có 120 điểm đã khớp nhánh `>= 50`, do đó bị gán `silver` thay vì `gold`. `CASE` kiểm tra các nhánh theo thứ tự và chọn nhánh phù hợp đầu tiên.

### Không có ELSE thì sao?

~~~sql
CASE
    WHEN loyalty_points >= 100 THEN 'gold'
END
~~~

Với hàng không thỏa điều kiện, biểu thức trả **NULL**. Nếu cột `tier` là `NOT NULL`, UPDATE sẽ lỗi. Khi dùng `CASE` cho cột bắt buộc, nên xác định đầy đủ các trường hợp hoặc có `ELSE` đúng nghiệp vụ.

## 14. COALESCE: ưu tiên giá trị không NULL

`COALESCE` trả biểu thức **không NULL đầu tiên** trong danh sách.

Ví dụ chỉ ghi đè số điện thoại nếu ứng dụng cung cấp giá trị mới:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET phone = COALESCE('0900000000'::text, phone)
WHERE customer_id = 1
RETURNING customer_id, phone;

ROLLBACK;
~~~

Nếu đối số đầu là NULL, biểu thức giữ `phone` cũ:

~~~sql
SET phone = COALESCE(NULL::text, phone)
~~~

### COALESCE không thay được mọi quy tắc cập nhật tùy chọn

Một API thường có ba ý nghĩa khác nhau:

1. Trường không được gửi → giữ nguyên.
2. Trường được gửi với chuỗi mới → cập nhật.
3. Trường được gửi với `null` tường minh → **xóa giá trị cũ**.

Nếu luôn viết:

~~~sql
SET phone = COALESCE(:new_phone, phone)
~~~

thì trường hợp (3) **không thể xóa số điện thoại** vì NULL dẫn tới giữ lại giá trị cũ. Ứng dụng phải phân biệt “trường vắng mặt” với “trường gửi NULL” nếu hợp đồng PATCH yêu cầu như vậy.

Dùng `CASE` với một cờ `field_present`, xây dựng statement có điều kiện hoặc một chiến lược DTO/SQL phù hợp. Không dùng `COALESCE` một cách mù quáng.

## 15. Một statement UPDATE có thể trả về các hàng đã thay đổi

`RETURNING` trả dữ liệu từ những hàng thực sự được statement xử lý.

~~~sql
BEGIN;

UPDATE update_lab.orders AS o
SET
    status = 'paid',
    paid_at = now(),
    updated_at = now()
WHERE o.order_id = 1001
  AND o.status = 'pending'
RETURNING
    o.order_id,
    o.customer_id,
    o.status,
    o.paid_at;

ROLLBACK;
~~~

Với seed, kết quả có **một hàng** và `status = 'paid'`.

Nếu đổi điều kiện sang:

~~~sql
WHERE o.order_id = 1002 AND o.status = 'pending'
~~~

thì không có hàng nào được cập nhật vì đơn 1002 đã `paid`, và `RETURNING` trả **0 hàng**.

### RETURNING khác SELECT lại bảng

- `UPDATE ... RETURNING` là kết quả trực tiếp từ những hàng mà UPDATE đã xử lý.
- `SELECT` chạy riêng sau UPDATE có thể thấy trạng thái mới trong cùng transaction, nhưng không tự chỉ ra những hàng **được sửa bởi statement trước** nếu không lưu danh sách khóa.
- `RETURNING` giúp ứng dụng kiểm tra số hàng, nhận giá trị mới, lấy thời gian thực và tiếp tục tạo audit/outbox khi cần.

Trong PostgreSQL, `RETURNING` có thể chứa biểu thức như:

~~~sql
RETURNING order_id, total_amount * 0.10 AS reference_amount
~~~

**Lưu ý:** với cú pháp phổ biến `UPDATE ... RETURNING column`, cột tham chiếu là **giá trị sau cập nhật**. Để ghi cả old/new value theo khả năng từng phiên bản, cần cú pháp phiên bản phù hợp hoặc một cơ chế audit riêng; không mặc định rằng alias `old_value` làm một cột trở thành dữ liệu trước UPDATE.

## 16. RETURNING không chứng minh giá trị thật sự đã khác

Câu:

~~~sql
UPDATE update_lab.orders
SET status = 'paid'
WHERE order_id = 1002
RETURNING order_id, status;
~~~

vẫn có thể trả một hàng, mặc dù đơn 1002 vốn đã có trạng thái `paid`. PostgreSQL xử lý hàng theo điều kiện `WHERE` và có thể tạo phiên bản hàng mới cùng giá trị ở các cột đã gán.

Nếu nghiệp vụ cần **chỉ phát sự kiện khi chuyển trạng thái**, điều kiện phải mô tả trạng thái nguồn hợp lệ:

~~~sql
BEGIN;

UPDATE update_lab.orders
SET
    status = 'paid',
    paid_at = now()
WHERE order_id = 1002
  AND status = 'pending'
RETURNING order_id, status;

ROLLBACK;
~~~

Kết quả **0 hàng** là đúng. Không nên dùng “có hàng RETURNING” như chứng cứ mọi thuộc tính đã đổi nếu không có điều kiện xác minh.

## 17. UPDATE với IN và EXISTS

Khi cần chọn hàng theo dữ liệu khác, có thể dùng `IN` hoặc `EXISTS` trong `WHERE`.

Ví dụ: đánh dấu active cho những khách hàng từng đặt đơn pending:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET
    is_active = true,
    updated_at = now()
WHERE EXISTS (
    SELECT 1
    FROM update_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'pending'
)
RETURNING c.customer_id, c.is_active;

ROLLBACK;
~~~

Với seed, khách hàng 1 và 2 có đơn pending nên được chọn.

`EXISTS` hỏi **có ít nhất một hàng khớp** hay không. Ngay cả khi khách hàng có ba đơn pending, mỗi hàng khách hàng đích vẫn chỉ là một hàng của UPDATE, không bị “cập nhật ba lần” do ba hàng nguồn.

### IN tương tự khi chỉ cần tập khóa

~~~sql
BEGIN;

UPDATE update_lab.customers
SET is_active = true
WHERE customer_id IN (
    SELECT customer_id
    FROM update_lab.orders
    WHERE status = 'pending'
)
RETURNING customer_id;

ROLLBACK;
~~~

Cách diễn đạt này thích hợp khi subquery tạo tập ID được lựa chọn. Với các biểu thức nullable, phải cẩn thận ngữ nghĩa `NULL` của `IN`/`NOT IN`; `EXISTS`/`NOT EXISTS` thường dễ diễn đạt điều kiện tồn tại hơn.

## 18. UPDATE ... FROM: gán từ bảng liên quan

PostgreSQL có cú pháp `UPDATE ... FROM`, cho phép đọc một nguồn dữ liệu trong khi cập nhật bảng đích.

Ví dụ tính giá bán `sale_price` dựa trên bảng giảm giá:

~~~sql
BEGIN;

UPDATE update_lab.products AS p
SET
    sale_price = ROUND(
        p.list_price * (1 - d.discount_percent / 100),
        2
    ),
    updated_at = now()
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id
RETURNING
    p.product_id,
    p.product_name,
    p.list_price,
    p.sale_price;

ROLLBACK;
~~~

Kết quả với seed:

| product_id | list_price | sale_price |
| ---: | ---: | ---: |
| 101 | 30.00 | 27.00 |
| 102 | 20.00 | 19.00 |

Sản phẩm 103 không có hàng tương ứng trong `product_discounts` nên **không được cập nhật**.

Cách đọc câu SQL:

1. `UPDATE ... AS p` xác định **bảng đích**.
2. `FROM ... AS d` cung cấp **dữ liệu nguồn**.
3. `WHERE d.product_id = p.product_id` ghép hàng đích với hàng nguồn.
4. `SET sale_price = ...` tính giá mới theo biểu thức chứa cả `p` và `d`.
5. `RETURNING` trả kết quả sau UPDATE.

`FROM` không có nghĩa PostgreSQL sẽ tự tìm khóa liên hệ. Nếu thiếu điều kiện nối, một phép kết hợp không chủ đích có thể khiến cập nhật sai hàng.

## 19. UPDATE ... FROM không phải UPDATE hai bảng cùng lúc

Với câu:

~~~sql
UPDATE update_lab.products AS p
SET sale_price = p.list_price * 0.9
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id;
~~~

chỉ `products` là **bảng đích của UPDATE**. `product_discounts` được **đọc** để phục vụ phép gán/điều kiện.

Nếu muốn đổi đồng thời `products.sale_price` và `product_discounts.discount_percent`, không thể viết tùy ý:

~~~sql
-- Sai: d.discount_percent không phải cột của target table.
UPDATE update_lab.products AS p
SET
    sale_price = 10,
    d.discount_percent = 5
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id;
~~~

Thông thường, cần hai lệnh UPDATE trong cùng transaction, hoặc một mô hình DML phù hợp với tính nhất quán của nghiệp vụ. Trigger/foreign-key action có thể tạo side effect nhưng đó là cơ chế riêng.

## 20. Bẫy lớn của UPDATE ... FROM: nhiều nguồn cho một hàng đích

PostgreSQL cho phép ghép bảng đích với nguồn trong `FROM`. Nhưng nếu **một hàng đích khớp nhiều hàng nguồn**, PostgreSQL **không bảo đảm hàng nguồn nào sẽ được dùng cho biểu thức SET**. Đừng dựa vào thứ tự chèn hoặc thứ tự physical scan.

Giả sử muốn cập nhật `orders.total_amount` từ `order_items`:

~~~sql
-- KHÔNG NÊN DÙNG: đơn 1001 có hai order_items!
UPDATE update_lab.orders AS o
SET total_amount = i.quantity * i.unit_price
FROM update_lab.order_items AS i
WHERE i.order_id = o.order_id;
~~~

Với đơn 1001:

- Có dòng Coffee: 2 × 30.00 = 60.00.
- Có dòng Tea: 1 × 20.00 = 20.00.

Hàng đơn 1001 khớp **hai** dòng nguồn. Câu UPDATE kiểu này không tính tổng 80.00; PostgreSQL có thể chọn một hàng nguồn để cập nhật, và **không có bảo đảm sẽ chọn dòng nào**. Nó không cập nhật đơn 1001 hai lần để cộng dồn qua từng item như một vòng lặp ứng dụng.

### Quy tắc an toàn

**Trước khi dùng UPDATE ... FROM, hãy xác nhận nguồn có tối đa một hàng cho mỗi khóa bảng đích.**

Có thể đạt được bằng:

- Ràng buộc `PRIMARY KEY`/`UNIQUE` ở bảng nguồn, như `product_discounts(product_id)`.
- Dùng `GROUP BY` để tổng hợp một hàng theo khóa.
- Dùng `DISTINCT ON` hoặc `ROW_NUMBER()` với `ORDER BY` và tie-breaker rõ ràng khi muốn chọn một hàng đại diện.
- Dùng scalar subquery theo ngữ nghĩa chính xác, với lỗi nếu trả nhiều hàng trong trường hợp cần đúng một giá trị.

Không giải quyết vấn đề bằng cách tùy tiện thêm `ORDER BY` ở một truy vấn nguồn rồi mong UPDATE tự chọn hàng “đầu tiên”. Thứ tự hàng nguồn không phải hợp đồng để chọn giá trị cho UPDATE khi tồn tại nhiều match.

## 21. UPDATE từ nguồn đã GROUP BY

Để tính đúng tổng đơn từ các dòng chi tiết, tổng hợp trước:

~~~sql
BEGIN;

WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price)::numeric(12,2)
            AS calculated_total
    FROM update_lab.order_items
    GROUP BY order_id
)
UPDATE update_lab.orders AS o
SET
    total_amount = t.calculated_total,
    updated_at = now()
FROM totals AS t
WHERE t.order_id = o.order_id
  AND o.total_amount IS DISTINCT FROM t.calculated_total
RETURNING
    o.order_id,
    o.total_amount;

ROLLBACK;
~~~

Ở seed, tổng các đơn đều đã bằng tổng item nên điều kiện `IS DISTINCT FROM` giúp câu UPDATE trả **0 hàng**. Đây là kết quả đúng: không có đơn nào cần sửa.

Muốn quan sát một lần đồng bộ thực sự, có thể tạo sai lệch **tạm thời trong lab** rồi tính lại:

~~~sql
BEGIN;

UPDATE update_lab.orders
SET total_amount = 55.00
WHERE order_id = 1003;

WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price)::numeric(12,2)
            AS calculated_total
    FROM update_lab.order_items
    GROUP BY order_id
)
UPDATE update_lab.orders AS o
SET
    total_amount = t.calculated_total,
    updated_at = now()
FROM totals AS t
WHERE t.order_id = o.order_id
  AND o.total_amount IS DISTINCT FROM t.calculated_total
RETURNING o.order_id, o.total_amount;

ROLLBACK;
~~~

Trong transaction, đơn 1003 được đưa từ 55.00 về **60.00** vì có 3 item Tea × 20.00.

### Vì sao GROUP BY giải quyết nguồn trùng?

`GROUP BY order_id` cho **một hàng tổng hợp duy nhất cho mỗi order_id**. Do đó, nếu bảng đích có `order_id PRIMARY KEY`, mỗi hàng đích tìm được tối đa một hàng tổng theo khóa.

**Lưu ý:** chỉ các đơn có ít nhất một dòng item mới xuất hiện trong CTE `totals`. Nếu nghiệp vụ cần đơn không có item được gán tổng 0, phải thiết kế nguồn qua `LEFT JOIN` với bảng đơn, hoặc dùng scalar subquery với `COALESCE` để xử lý tập rỗng. Không mặc định CTE hiện tại bao phủ mọi đơn trong mọi hệ thống.

## 22. UPDATE bằng scalar subquery

Không phải lúc nào cũng cần `FROM`. Có thể gán giá trị bằng subquery trả **một giá trị**.

~~~sql
BEGIN;

UPDATE update_lab.orders AS o
SET
    total_amount = COALESCE(
        (
            SELECT SUM(i.quantity * i.unit_price)
            FROM update_lab.order_items AS i
            WHERE i.order_id = o.order_id
        ),
        0
    ),
    updated_at = now()
WHERE o.order_id = 1001
RETURNING o.order_id, o.total_amount;

ROLLBACK;
~~~

Subquery trong `SET` được liên kết với hàng đích `o` qua `o.order_id`. `SUM` luôn trả một hàng tổng hợp cho một tập, có giá trị NULL nếu tập rỗng; `COALESCE(..., 0)` biến trường hợp không có item thành 0.

Nếu dùng scalar subquery không có aggregate:

~~~sql
-- Cố ý sai khi đơn có nhiều item:
UPDATE update_lab.orders AS o
SET total_amount = (
    SELECT quantity * unit_price
    FROM update_lab.order_items AS i
    WHERE i.order_id = o.order_id
)
WHERE o.order_id = 1001;
~~~

subquery sẽ trả **nhiều hàng** và PostgreSQL báo lỗi kiểu “more than one row returned by a subquery used as an expression”. Đây là một cảnh báo hữu ích: câu truy vấn không mô tả rõ phải lấy giá trị nguồn nào.

### Subquery trả 0 hàng

Một scalar subquery trả 0 hàng thường cho `NULL` trong ngữ cảnh gán. Nếu cột đích là `NOT NULL`, câu UPDATE có thể lỗi. Khi nghiệp vụ cho phép, dùng `COALESCE` hoặc xử lý không có dữ liệu một cách tường minh.

## 23. Gán nhiều cột từ một subquery

PostgreSQL cho phép dùng subquery để cung cấp nhiều giá trị cho một nhóm cột:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET (city, tier) = (
    SELECT 'Hue'::text, 'gold'::text
)
WHERE c.customer_id = 2
RETURNING c.customer_id, c.city, c.tier;

ROLLBACK;
~~~

Ví dụ này minh họa dạng tuple assignment. Trong thực tế, subquery có thể đọc từ một bảng cấu hình hoặc tính biểu thức, nhưng phải trả đúng số lượng cột và số hàng phù hợp.

Cần phân biệt:

- `SET (a, b) = (expr_a, expr_b)`: hai biểu thức lấy từ hàng cũ/đối số.
- `SET (a, b) = (SELECT x, y FROM source ...)`: một hàng kết quả cung cấp hai giá trị.
- Nếu subquery trả nhiều hơn một hàng khi cần một hàng, câu UPDATE lỗi; không tự chọn một hàng tùy ý.

Với dữ liệu nguồn 1:N, trước tiên hãy tổng hợp hoặc định nghĩa quy tắc lựa chọn hàng nguồn rõ ràng.

## 24. Dùng DISTINCT ON để chọn một hàng đại diện từ nguồn

Đôi khi một hàng đích có nhiều bản ghi lịch sử, nhưng chỉ muốn cập nhật theo bản ghi **mới nhất**.

Giả sử muốn tạo một bảng sự kiện khách hàng để thực hành:

~~~sql
CREATE TABLE update_lab.customer_city_events (
    event_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES update_lab.customers(customer_id),
    new_city text NOT NULL,
    effective_at timestamptz NOT NULL
);

INSERT INTO update_lab.customer_city_events
    (event_id, customer_id, new_city, effective_at)
VALUES
    (1, 2, 'Hue', '2026-11-01 10:00:00+00'),
    (2, 2, 'HCM', '2026-11-05 10:00:00+00'),
    (3, 1, 'DNG', '2026-11-03 09:00:00+00');
~~~

Không nên JOIN thẳng `customer_city_events` với customers: khách hàng 2 có hai bản ghi nguồn và không được xác định nên dùng thành phố nào.

Chọn một hàng mỗi khách hàng bằng `DISTINCT ON`:

~~~sql
BEGIN;

WITH latest_city AS (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        new_city
    FROM update_lab.customer_city_events
    ORDER BY
        customer_id,
        effective_at DESC,
        event_id DESC
)
UPDATE update_lab.customers AS c
SET
    city = l.new_city,
    updated_at = now()
FROM latest_city AS l
WHERE l.customer_id = c.customer_id
  AND c.city IS DISTINCT FROM l.new_city
RETURNING c.customer_id, c.city;

ROLLBACK;
~~~

Với dữ liệu mẫu, khách hàng 2 nhận `HCM` (event 2 mới hơn event 1), còn khách hàng 1 nhận `DNG`.

`event_id DESC` là **tie-breaker** nếu có hai sự kiện cùng `effective_at`. Quy tắc này làm việc chọn đại diện xác định và dễ giải thích. Nếu chỉ cần thay đổi một hàng theo khóa có unique, không cần dùng `DISTINCT ON`.

## 25. UPDATE với CASE trong câu FROM

Có thể kết hợp `UPDATE ... FROM` và `CASE` để áp dụng quy tắc khác nhau từ bảng nguồn.

Ví dụ cập nhật tier dựa trên tổng số tiền các đơn đã `paid`:

~~~sql
BEGIN;

WITH paid_totals AS (
    SELECT
        c.customer_id,
        COALESCE(
            SUM(o.total_amount) FILTER (WHERE o.status = 'paid'),
            0
        ) AS lifetime_paid
    FROM update_lab.customers AS c
    LEFT JOIN update_lab.orders AS o
        ON o.customer_id = c.customer_id
    GROUP BY c.customer_id
)
UPDATE update_lab.customers AS c
SET
    tier = CASE
        WHEN p.lifetime_paid >= 200 THEN 'gold'
        WHEN p.lifetime_paid >= 50 THEN 'silver'
        ELSE 'standard'
    END,
    updated_at = now()
FROM paid_totals AS p
WHERE p.customer_id = c.customer_id
RETURNING c.customer_id, c.tier;

ROLLBACK;
~~~

Bởi vì CTE `paid_totals` bắt đầu từ **customers** và dùng `LEFT JOIN`, mỗi khách hàng có một dòng tổng hợp, kể cả người chưa có đơn `paid`. `FILTER (WHERE ...)` chỉ tính các đơn đã paid; `COALESCE` chuyển tổng rỗng thành 0.

Đây chỉ là ví dụ logic phân hạng để học kỹ thuật UPDATE. Trong hệ thống thật, việc đổi tier có thể cần các quy tắc phức tạp hơn, chẳng hạn hoàn tiền, hạn mức thời gian, loại tiền và quyền sửa dữ liệu.

### Chỉ cập nhật khi tier thật sự đổi

Có thể tính tier đích trong một CTE khác rồi dùng:

~~~sql
WHERE c.tier IS DISTINCT FROM target_tier
~~~

Việc này giúp tránh ghi lại những hàng vốn đã có tier đúng. Đừng quên `updated_at` chỉ nên thay đổi theo chính sách cập nhật dữ liệu mà ứng dụng đã định nghĩa.

## 26. Cập nhật JSONB bằng jsonb_set

PostgreSQL có kiểu `jsonb`, cho phép lưu dữ liệu dạng đối tượng JSON đã phân tích và thao tác với các khóa bên trong.

Bảng `products` có cột:

~~~sql
attributes jsonb NOT NULL DEFAULT '{}'::jsonb
~~~

Ví dụ với Coffee:

~~~json
{"category":"beverage","color":"brown"}
~~~

Muốn đổi màu thành `black` mà giữ nguyên các thuộc tính khác:

~~~sql
BEGIN;

UPDATE update_lab.products
SET
    attributes = jsonb_set(
        attributes,
        '{color}',
        to_jsonb('black'::text),
        true
    ),
    updated_at = now()
WHERE product_id = 101
RETURNING product_id, attributes;

ROLLBACK;
~~~

`jsonb_set(target, path, new_value, create_if_missing)` tạo một giá trị `jsonb` mới dựa trên dữ liệu cũ:

- `attributes` là giá trị JSONB ban đầu.
- `'{color}'` là đường dẫn tới khóa `color` ở mức gốc.
- `to_jsonb('black'::text)` tạo JSON string `"black"`, không phải một token SQL text chưa chuyển kiểu.
- `true` cho phép tạo khóa cuối nếu chưa tồn tại theo quy tắc hàm.

Kết quả gồm `category = beverage` và `color = black`.

### Xóa một khóa JSONB

~~~sql
BEGIN;

UPDATE update_lab.products
SET attributes = attributes - 'color'
WHERE product_id = 101
RETURNING attributes;

ROLLBACK;
~~~

Toán tử `- 'color'` xóa khóa `color` ở cấp gốc trong đối tượng JSONB, không xóa toàn bộ hàng sản phẩm.

### Đặt cả object mới

~~~sql
UPDATE update_lab.products
SET attributes = '{"category":"beverage"}'::jsonb
WHERE product_id = 101;
~~~

Khác với `jsonb_set`, câu này **thay thế toàn bộ giá trị của cột `attributes`**, làm mất các khóa khác không có trong object mới. Đây có thể là chủ đích, nhưng cũng là lỗi khi ứng dụng chỉ muốn cập nhật một thuộc tính nhỏ.

## 27. UPDATE có thể sửa khóa chính, nhưng thường không nên

Về mặt SQL, nếu constraint cho phép, có thể viết:

~~~sql
UPDATE update_lab.customers
SET customer_id = 10
WHERE customer_id = 1;
~~~

Tuy nhiên, trong schema lab, `orders.customer_id` là foreign key tới customers mà không khai báo `ON UPDATE CASCADE`, nên việc đổi khóa của khách hàng 1 đang có đơn sẽ bị từ chối.

Nếu khóa cha được phép đổi và FK khai báo `ON UPDATE CASCADE`, PostgreSQL có thể cập nhật khóa ngoại ở bảng con. Dù vậy, với primary key kỹ thuật như UUID hoặc identity, quy tắc thiết kế phổ biến là **giữ ID ổn định**, còn các mã nghiệp vụ có thể đổi được đặt ở cột riêng.

Không dùng UPDATE khóa chính như một cách “sửa ID cho đẹp” mà chưa kiểm tra đầy đủ foreign key, external API, cache, event, log và dữ liệu liên kết.

## 28. UPDATE không tự sắp xếp theo ORDER BY hay giới hạn bằng LIMIT

PostgreSQL không hỗ trợ trực tiếp cú pháp kiểu:

~~~sql
-- KHÔNG PHẢI CÚ PHÁP UPDATE THÔNG THƯỜNG CỦA POSTGRESQL.
UPDATE update_lab.orders
SET status = 'cancelled'
WHERE status = 'pending'
ORDER BY order_id
LIMIT 1;
~~~

Muốn cập nhật một tập được chọn theo tiêu chí có thứ tự, hãy **chọn khóa trước** trong CTE/subquery, rồi UPDATE theo những khóa đó.

Ví dụ chỉ chọn **một đơn pending có ID nhỏ nhất**:

~~~sql
BEGIN;

WITH chosen AS (
    SELECT order_id
    FROM update_lab.orders
    WHERE status = 'pending'
    ORDER BY order_id
    LIMIT 1
)
UPDATE update_lab.orders AS o
SET
    status = 'cancelled',
    updated_at = now()
FROM chosen AS c
WHERE o.order_id = c.order_id
  AND o.status = 'pending'
RETURNING o.order_id, o.status;

ROLLBACK;
~~~

Với seed, đơn 1001 được chọn.

Lệnh `SELECT ... ORDER BY ... LIMIT 1` tạo một khóa mục tiêu ổn định theo dữ liệu đọc tại thời điểm đó. `UPDATE` sau cùng vẫn có điều kiện `o.status = 'pending'` để tránh xử lý không hợp lệ nếu trạng thái đã thay đổi trong thời gian xử lý đồng thời.

### Batching với nhiều worker

Với queue xử lý chung, có thể kết hợp `FOR UPDATE SKIP LOCKED` trong bước chọn khóa để các worker tránh tranh chấp một số hàng đang bị khóa:

~~~sql
BEGIN;

WITH picked AS (
    SELECT o.order_id
    FROM update_lab.orders AS o
    WHERE o.status = 'pending'
    ORDER BY o.order_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE update_lab.orders AS o
SET
    status = 'cancelled',
    updated_at = now()
FROM picked AS p
WHERE p.order_id = o.order_id
RETURNING o.order_id;

ROLLBACK;
~~~

`SKIP LOCKED` đặc biệt phù hợp với một số kiểu queue/worker; nó cố ý bỏ qua các hàng đang bị khóa, nên **không nên dùng làm cách thông thường để đọc một danh sách đầy đủ, nhất quán**.

Trong ví dụ ta dùng trạng thái `cancelled` làm đích để học UPDATE, không khuyến nghị dùng lệnh hủy đơn thật làm queue worker. Với production, cần trạng thái xử lý riêng, deadline/retry và khả năng phục hồi worker.

## 29. UPDATE với CTE và các biểu thức phức tạp

`WITH` có thể làm câu SQL dễ đọc hơn bằng cách tách tính toán nguồn và thao tác ghi.

Ví dụ tính tổng tiền theo khách hàng rồi cập nhật điểm thưởng theo một quy tắc thử nghiệm:

~~~sql
BEGIN;

WITH paid_amounts AS (
    SELECT
        customer_id,
        COALESCE(
            SUM(total_amount) FILTER (WHERE status = 'paid'),
            0
        ) AS paid_total
    FROM update_lab.orders
    GROUP BY customer_id
),
calculated_points AS (
    SELECT
        customer_id,
        FLOOR(paid_total / 10)::integer AS target_points
    FROM paid_amounts
)
UPDATE update_lab.customers AS c
SET
    loyalty_points = p.target_points,
    updated_at = now()
FROM calculated_points AS p
WHERE p.customer_id = c.customer_id
  AND c.loyalty_points IS DISTINCT FROM p.target_points
RETURNING c.customer_id, c.loyalty_points;

ROLLBACK;
~~~

Đây là ví dụ hướng dẫn tách phép tính thành hai CTE đọc dữ liệu, giúp `UPDATE` cuối đơn giản.

**Giới hạn:** CTE `paid_amounts` nhóm chỉ các khách hàng có ít nhất một đơn. Khách hàng không có đơn sẽ không được cập nhật, thay vì tự được đặt điểm 0. Nếu nghiệp vụ yêu cầu tất cả khách hàng, hãy bắt đầu từ bảng `customers` và `LEFT JOIN` nguồn đơn rồi tổng hợp.

**Lưu ý quan trọng về nghiệp vụ:** ví dụ `SET loyalty_points = target_points` thay toàn bộ điểm hiện tại. Nếu ứng dụng lưu điểm đã tiêu, hoàn tiền hoặc các điều chỉnh thủ công, công thức này có thể sai. SQL đúng cú pháp nhưng quy tắc tính điểm vẫn cần thiết kế riêng.

## 30. Tránh lost update khi nhiều phiên cùng ghi

Một tình huống thường gặp:

1. Phiên A đọc `stock_qty = 10`.
2. Phiên B cũng đọc `stock_qty = 10`.
3. A tính 10 - 3 = 7 rồi ghi 7.
4. B tính 10 - 2 = 8 rồi ghi 8.
5. Kết quả cuối là 8 thay vì 5, nếu hai phiên ghi đè từ các giá trị đã đọc cũ mà không đồng bộ.

Đây là dạng **lost update** ở tầng logic ứng dụng.

### Đừng làm phép trừ ngoài rồi ghi giá trị tính từ dữ liệu cũ

~~~text
SELECT stock_qty FROM products WHERE product_id = 101;
-- Ứng dụng tính new_qty = old_qty - requested_qty.
UPDATE products SET stock_qty = :new_qty WHERE product_id = 101;
~~~

Nếu không có khóa/kiểm tra version phù hợp, `:new_qty` có thể đã cũ khi UPDATE xảy ra.

### Đưa phép tính vào chính UPDATE

~~~sql
BEGIN;

UPDATE update_lab.products
SET stock_qty = stock_qty - 3
WHERE product_id = 101
  AND stock_qty >= 3
RETURNING product_id, stock_qty;

ROLLBACK;
~~~

Với các cập nhật đồng thời vào **cùng một hàng**, PostgreSQL quản lý khóa hàng. Ở mức isolation `READ COMMITTED`, nếu một UPDATE phải chờ transaction khác sửa hàng, PostgreSQL có cơ chế kiểm tra lại điều kiện trên phiên bản hàng phù hợp sau khi khóa được giải quyết. Điều kiện `stock_qty >= 3` nằm ngay trong UPDATE giúp tránh trừ khi hàng không còn đủ số lượng.

Đây là một mẫu an toàn hơn đáng kể so với ghi đè một số lượng đã tính trước bên ngoài. Tuy nhiên, nghiệp vụ nhiều sản phẩm, nhiều kho, tồn kho giữ chỗ hoặc yêu cầu xuyên bảng có thể cần transaction/locking phức tạp hơn.

## 31. Optimistic locking bằng version column

Một kỹ thuật khác là thêm cột `version` để kiểm tra bản ghi còn ở phiên bản ứng dụng đã đọc không.

~~~sql
CREATE TABLE update_lab.version_demo (
    item_id integer PRIMARY KEY,
    item_name text NOT NULL,
    quantity integer NOT NULL CHECK (quantity >= 0),
    row_version integer NOT NULL DEFAULT 0
);

INSERT INTO update_lab.version_demo
    (item_id, item_name, quantity)
VALUES (1, 'Sample item', 10);
~~~

Giả sử ứng dụng đọc `quantity = 10`, `row_version = 0`. Khi ghi:

~~~sql
BEGIN;

UPDATE update_lab.version_demo
SET
    quantity = 7,
    row_version = row_version + 1
WHERE item_id = 1
  AND row_version = 0
RETURNING item_id, quantity, row_version;

ROLLBACK;
~~~

Nếu một transaction khác đã cập nhật trước và tăng `row_version` thành 1, điều kiện `row_version = 0` không khớp; câu lệnh trả 0 hàng thay vì âm thầm ghi đè kết quả người khác.

### Cần làm gì khi nhận 0 hàng?

Ứng dụng có thể:

- Đọc lại phiên bản mới rồi hỏi người dùng xác nhận.
- Tính lại thao tác dựa trên dữ liệu mới.
- Trả lỗi xung đột nghiệp vụ.
- Thực hiện retry có giới hạn khi thao tác có thể lặp an toàn.

Không tự retry vô hạn và ghi đè bất kể version; như vậy mất ý nghĩa optimistic locking.

## 32. Transaction giúp thử UPDATE an toàn

Một quy trình tối thiểu khi chuẩn bị sửa nhiều hàng:

~~~sql
BEGIN;

-- 1. Xem những hàng đang thỏa điều kiện.
SELECT order_id, customer_id, status, total_amount
FROM update_lab.orders
WHERE status = 'pending'
ORDER BY order_id;

-- 2. Cập nhật cùng điều kiện đã xét.
UPDATE update_lab.orders
SET
    status = 'cancelled',
    updated_at = now()
WHERE status = 'pending'
RETURNING order_id, status;

-- 3. Kiểm tra kết quả trong cùng transaction.
SELECT order_id, status
FROM update_lab.orders
ORDER BY order_id;

-- 4. Chỉ để học: quay lại trạng thái ban đầu.
ROLLBACK;
~~~

Trong production, **đừng tự giả định rằng SELECT kiểm tra rồi UPDATE ngay sau đó luôn chọn chính xác cùng tập hàng** nếu có các transaction khác đang ghi đồng thời. Phải xét isolation, khóa, điều kiện và cách xử lý concurrent updates. `SELECT` trước khi UPDATE là phương pháp giúp người viết nhìn rõ phạm vi dự kiến, nhưng không phải khóa bảo đảm dữ liệu không thay đổi.

### SAVEPOINT khi thử thao tác có thể lỗi

~~~sql
BEGIN;

SAVEPOINT before_try;

-- Trong lab, câu này cố ý vi phạm CHECK(stock_qty >= 0).
UPDATE update_lab.products
SET stock_qty = -1
WHERE product_id = 101;

-- Khi đang chạy tương tác và lệnh trên báo lỗi:
ROLLBACK TO SAVEPOINT before_try;

-- Có thể tiếp tục các câu SQL trong transaction.
SELECT product_id, stock_qty
FROM update_lab.products
WHERE product_id = 101;

ROLLBACK;
~~~

Nếu một lệnh SQL lỗi trong transaction, PostgreSQL thường đặt transaction vào trạng thái aborted; các lệnh tiếp theo không thực thi bình thường cho tới khi `ROLLBACK` hoặc quay lại `SAVEPOINT` phù hợp. Với script bật `ON_ERROR_STOP`, công cụ có thể dừng ngay tại lệnh cố ý lỗi; hãy tách các ví dụ lỗi ra khỏi luồng chạy tự động.

## 33. Tác động của UPDATE tới MVCC và chỉ mục

PostgreSQL dùng **MVCC** để quản lý các phiên bản hàng. Một UPDATE thường tạo một phiên bản hàng mới và đánh dấu phiên bản cũ không còn là phiên bản hiện hành theo quy tắc visibility.

Hệ quả:

- UPDATE không đơn giản là ghi đè vài byte tại chỗ trong một file.
- Có thể tạo WAL và công việc cho VACUUM.
- Các index có thể cần được duy trì khi khóa index thay đổi.
- Nếu cập nhật những cột không tham gia index và các điều kiện khác phù hợp, PostgreSQL có thể dùng cơ chế **HOT (Heap-Only Tuple)** để giảm nhu cầu cập nhật index.
- Một lệnh UPDATE nhiều hàng có thể giữ lock và tiêu thụ tài nguyên đáng kể.

Ví dụ:

~~~sql
UPDATE update_lab.customers
SET updated_at = now()
WHERE customer_id = 1;
~~~

Ngay cả khi nghiệp vụ không thay đổi tên/thành phố, câu UPDATE này vẫn tác động hàng theo `WHERE`, có thể tạo phiên bản hàng và kích hoạt trigger liên quan.

### Tại sao nên tránh ghi không cần thiết?

Với workload lớn, bỏ qua các hàng vốn đã có giá trị đích giúp giảm số lần ghi và tác động lên trigger/WAL. Có thể dùng:

~~~sql
UPDATE update_lab.customers
SET city = 'HCM'
WHERE customer_id = 1
  AND city IS DISTINCT FROM 'HCM';
~~~

Nhưng tránh ghi không cần thiết không phải mục tiêu duy nhất. Nếu cần lưu hành động người dùng dù giá trị không đổi, ghi event/audit theo thiết kế nghiệp vụ có thể là lựa chọn đúng.

## 34. Constraint, trigger, quyền và RLS vẫn áp dụng

`UPDATE` không bỏ qua các ràng buộc:

- `NOT NULL`: không được gán NULL cho cột bắt buộc.
- `CHECK`: giá trị mới phải thỏa điều kiện, ví dụ `stock_qty >= 0`.
- `UNIQUE`: không thể sửa email để trùng với khách hàng khác.
- `FOREIGN KEY`: thay `customer_id` trong orders phải trỏ tới một khách hàng tồn tại.
- `ON UPDATE CASCADE/RESTRICT/NO ACTION`: quy định hành vi khi khóa được tham chiếu thay đổi.
- Trigger: có thể tự thực thi khi UPDATE, kể cả logic audit/timestamp.
- Row-level security (RLS): có thể giới hạn hàng được UPDATE và giá trị mới hợp lệ theo policy.
- Quyền SQL: role phải có quyền UPDATE trên bảng/cột đích và quyền SELECT thích hợp với các cột đọc trong biểu thức/WHERE/RETURNING.

Ví dụ này sẽ lỗi vì email đã có:

~~~sql
-- CỐ Ý LỖI: trùng UNIQUE(email) với khách hàng An.
UPDATE update_lab.customers
SET email = 'an@example.test'
WHERE customer_id = 2;
~~~

Đừng sửa constraint chỉ để câu UPDATE chạy nếu dữ liệu cần được bảo vệ. Cần xác định liệu hai khách hàng thực sự phải có email trùng, đang nhập sai dữ liệu hay phải hợp nhất tài khoản theo quy trình riêng.

## 35. UPDATE và bảng phân vùng

Trong PostgreSQL, khi bảng đích là **partitioned table**, một UPDATE làm thay đổi khóa phân vùng có thể khiến hàng phải chuyển sang partition khác. Đây là trường hợp đặc biệt so với một bảng thường.

Hệ thống có thể thực hiện việc di chuyển hàng giữa partition theo cơ chế nội bộ, với các tác động tới concurrency, trigger và khả năng phát sinh lỗi serialization trong tình huống đồng thời. Nếu ứng dụng cập nhật khóa partition hoặc khoảng ngày phân vùng, cần tham khảo tài liệu đúng phiên bản PostgreSQL và kiểm thử trên môi trường tương đương production.

Ví dụ cập nhật một đơn hàng thông thường **không** đòi hỏi người viết phải tự di chuyển hàng giữa partitions, nhưng cũng không được xem việc đổi partition key là một UPDATE “nhẹ” mặc định.

## 36. RETURNING và thao tác JDBC

Trong Java với pgJDBC, một `UPDATE ... RETURNING` có thể được đọc qua `ResultSet`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class StockRepository {
    public static boolean deductStock(
        Connection connection,
        int productId,
        int quantity
    ) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        String sql = """
            UPDATE update_lab.products
            SET
                stock_qty = stock_qty - ?,
                updated_at = now()
            WHERE product_id = ?
              AND stock_qty >= ?
            RETURNING product_id, stock_qty
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setInt(1, quantity);
            statement.setInt(2, productId);
            statement.setInt(3, quantity);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return false;
                }

                int remaining = rs.getInt("stock_qty");
                System.out.println(
                    "Remaining stock: " + remaining
                );
                return true;
            }
        }
    }
}
~~~

Với `UPDATE ... RETURNING`, pgJDBC thông dụng cho phép dùng `executeQuery()` để đọc tập kết quả trả về. Nếu dùng UPDATE không có RETURNING, `executeUpdate()` là cách phổ biến để lấy số hàng bị tác động.

### Vì sao bind parameter?

Dùng `?` và `PreparedStatement` giúp truyền kiểu dữ liệu đúng và tránh việc nối chuỗi SQL từ input không tin cậy:

~~~java
// Không nên ghép chuỗi SQL:
// "... WHERE product_id = " + userInput
~~~

Tuy nhiên, binding không tự kiểm tra role/tenant. Nếu API cho phép người dùng trừ kho, ứng dụng vẫn phải kiểm tra quyền thực hiện và quy tắc nghiệp vụ.

### Transaction boundary thuộc về service

Phương thức trên không tự gọi `commit()` hoặc `rollback()`. Trong ứng dụng thật, repository có thể tham gia transaction lớn hơn bao gồm tạo đơn, giảm tồn kho và ghi lịch sử. Không nên tự thay đổi autocommit của một connection đang do transaction manager quản lý mà không có hợp đồng rõ ràng.

## 37. Khi nào cần UPDATE ... FROM, subquery, CTE hay CASE?

| Nhu cầu | Mẫu SQL phù hợp | Lý do |
| --- | --- | --- |
| Đổi thành phố một khách hàng | `UPDATE ... SET city=... WHERE id=...` | Đơn giản, rõ khóa |
| Tăng điểm dựa giá trị hiện tại | `SET points = points + :delta` | Tính trên hàng ở thời điểm cập nhật |
| Chọn giá trị theo điều kiện từng hàng | `SET tier = CASE ... END` | Quy tắc phân nhánh |
| Giữ cột nếu tham số là NULL | `SET col = COALESCE(:value,col)` | Chỉ đúng nếu NULL nghĩa là “không đổi” |
| Xóa giá trị nullable | `SET phone = NULL` | NULL có ngữ nghĩa riêng |
| Đưa về mặc định schema | `SET tier = DEFAULT` | Không cần lặp hằng mặc định |
| Chỉ cập nhật khi thực sự khác | `WHERE col IS DISTINCT FROM new_value` | Xử lý cả NULL đúng |
| Cập nhật từ một bảng ánh xạ 1:1 | `UPDATE ... FROM source` | Sử dụng các cột nguồn |
| Cập nhật từ nguồn 1:N | `WITH totals AS (... GROUP BY ...) UPDATE ... FROM totals` | Bảo đảm một nguồn cho một đích |
| Một giá trị tổng hợp theo mỗi hàng | Scalar subquery với `SUM`/`COALESCE` | Biểu thức gán rõ ràng |
| Một hàng đại diện mới nhất | `DISTINCT ON` có `ORDER BY` và tie-breaker | Chọn nguồn xác định |
| Giới hạn tập hàng được sửa | CTE chọn khóa rồi UPDATE | PostgreSQL không có UPDATE ORDER BY LIMIT trực tiếp |
| Cần danh sách hàng thực sự thay đổi | `RETURNING` | Nhận dữ liệu ngay từ DML |
| Tránh ghi đè bởi phiên khác | Điều kiện trạng thái, version hoặc row locks | Kiểm soát concurrency |

Cùng một yêu cầu có thể viết bằng nhiều cú pháp. Hãy ưu tiên mẫu dễ chứng minh **đúng tập hàng**, **đúng phép gán** và **có kết quả xác định khi dữ liệu không như mong đợi**.

## 38. Các sai lầm thường gặp

### 38.1. Bỏ WHERE

~~~sql
UPDATE update_lab.orders
SET status = 'cancelled';
~~~

Tất cả đơn được chọn, không chỉ một đơn. Phải xác định phạm vi trước khi chạy.

### 38.2. WHERE thiếu dấu ngoặc với AND/OR

`customer_id = 1 AND status = 'pending' OR status = 'cancelled'` có thể chọn đơn cancelled của khách hàng khác. Dùng dấu ngoặc hoặc `IN` đúng ý nghĩa.

### 38.3. So sánh NULL bằng =

`phone = NULL` không tìm được giá trị NULL. Dùng `phone IS NULL`.

### 38.4. Chỉ dùng <> để tránh cập nhật giá trị giống nhau

`city <> 'HCM'` bỏ sót hàng có `city NULL`. Dùng `IS DISTINCT FROM` khi cần so sánh kể cả NULL.

### 38.5. Nghĩ các phép SET chạy tuần tự

`SET a=b, b=a` hoán đổi giá trị; không có nghĩa cả hai cột nhận cùng giá trị `b` cũ hoặc `a` mới. Các biểu thức lấy từ hàng trước cập nhật.

### 38.6. Dùng alias ở bên trái SET

`SET p.list_price = 10` không đúng cú pháp cột đích thông thường. Viết `SET list_price = 10`.

### 38.7. Dùng COALESCE để biểu diễn cả ba trạng thái PATCH

`COALESCE(NULL, old_value)` không xóa giá trị cũ. Cần phân biệt trường vắng mặt với NULL tường minh.

### 38.8. Quên ELSE trong CASE

Khi không nhánh nào khớp, `CASE` trả NULL. Với cột NOT NULL, UPDATE có thể lỗi.

### 38.9. UPDATE FROM nguồn 1:N không xác định

Một đơn có nhiều dòng hàng; lấy một dòng `order_items` bất kỳ để gán total_amount không phải tính tổng. Dùng GROUP BY hoặc quy tắc chọn duy nhất.

### 38.10. Nghĩ UPDATE FROM sửa được mọi bảng trong FROM

Chỉ target table trong `UPDATE` được sửa trực tiếp. Bảng nguồn `FROM` để đọc.

### 38.11. Dùng scalar subquery trả nhiều hàng

PostgreSQL báo lỗi nếu biểu thức cần một giá trị mà subquery trả nhiều hàng. Phải tính aggregate hoặc chọn một hàng có quy tắc rõ ràng.

### 38.12. Nghĩ RETURNING chỉ trả các cột thực sự đổi giá trị

RETURNING trả giá trị từ các hàng UPDATE đã xử lý. Nếu `SET status='paid'` trên hàng đã paid, vẫn có thể có một hàng được UPDATE.

### 38.13. Dùng giá trị đã đọc ở application để ghi đè

`SET stock_qty = :new_stock_from_old_read` có nguy cơ lost update. Đưa phép tăng/giảm vào UPDATE hoặc dùng optimistic locking/transaction thích hợp.

### 38.14. Cho rằng 0 hàng là lỗi SQL

Nếu `WHERE` không khớp, PostgreSQL thực hiện statement thành công với 0 hàng. Ứng dụng phải phân biệt không tồn tại, trạng thái không hợp lệ và lỗi constraint.

### 38.15. Tưởng ROLLBACK hoàn tác mọi side effect

`ROLLBACK` đảo ngược dữ liệu transaction trong PostgreSQL, nhưng sequence đã cấp, lệnh/side effect ở dịch vụ ngoài hoặc các thao tác phi transaction không nhất thiết quay lại.

### 38.16. Quên transaction bị aborted sau lỗi

Một lỗi constraint trong transaction khiến các lệnh sau không chạy bình thường cho tới khi rollback hoặc rollback về savepoint.

### 38.17. Nhầm LIMIT ngoài CTE với giới hạn UPDATE

Nếu đặt UPDATE trong data-modifying CTE rồi `SELECT ... LIMIT 1` ở ngoài, DML CTE vẫn thực thi toàn bộ những hàng nó chọn. Cần giới hạn ở nguồn chọn khóa trước UPDATE, không giới hạn output.

### 38.18. Tạo index mà không xét mẫu WHERE

Index trên khóa được lọc nhiều có thể giúp cập nhật tìm hàng nhanh hơn, nhưng index cũng tốn chi phí duy trì khi UPDATE. Cần xem workload và `EXPLAIN`.

### 38.19. Thay khóa chính mà không xét FK

Đổi `customer_id` có thể bị FK chặn hoặc lan truyền, ảnh hưởng dữ liệu bên ngoài. Ưu tiên khóa kỹ thuật ổn định.

### 38.20. UPDATE quá nhiều hàng trong một giao dịch mà không tính lock/WAL

Một statement rất ngắn vẫn có thể sửa hàng triệu hàng, giữ lock lâu và tạo WAL lớn. Cần batching/maintenance plan khi dữ liệu lớn.

## 39. Bài tập thực hành có đáp án

Hãy chạy các bài độc lập trên dữ liệu seed mục 2. Với các bài thay đổi dữ liệu, sử dụng `BEGIN` và `ROLLBACK` nếu chưa muốn lưu kết quả.

### Bài 1. Sửa một thành phố

Đổi `city` của khách hàng Binh (2) thành `Hue`.

~~~sql
BEGIN;
UPDATE update_lab.customers
SET city = 'Hue'
WHERE customer_id = 2
RETURNING customer_id, city;
ROLLBACK;
~~~

**Đáp án:** Một hàng với `customer_id = 2` và `city = Hue`.

### Bài 2. Tăng 30 điểm cho An

~~~sql
BEGIN;
UPDATE update_lab.customers
SET loyalty_points = loyalty_points + 30
WHERE customer_id = 1
RETURNING customer_id, loyalty_points;
ROLLBACK;
~~~

**Đáp án:** Điểm mới là **150**.

### Bài 3. Giảm 4 đơn vị Coffee khi đủ kho

~~~sql
BEGIN;
UPDATE update_lab.products
SET stock_qty = stock_qty - 4
WHERE product_id = 101
  AND stock_qty >= 4
RETURNING product_id, stock_qty;
ROLLBACK;
~~~

**Đáp án:** Một hàng, tồn kho mới là **6**.

### Bài 4. Nếu thử xuất 2 đơn vị Cup thì sao?

~~~sql
BEGIN;
UPDATE update_lab.products
SET stock_qty = stock_qty - 2
WHERE product_id = 103
  AND stock_qty >= 2
RETURNING product_id, stock_qty;
ROLLBACK;
~~~

**Đáp án:** **0 hàng** được cập nhật vì stock của Cup là 0.

### Bài 5. Reset tier về DEFAULT

~~~sql
BEGIN;
UPDATE update_lab.customers
SET tier = DEFAULT
WHERE customer_id = 1
RETURNING tier;
ROLLBACK;
~~~

**Đáp án:** `standard`, theo default của cột.

### Bài 6. Chỉ cập nhật phone nếu đang NULL

~~~sql
BEGIN;
UPDATE update_lab.customers
SET phone = '0123456789'
WHERE customer_id = 2
  AND phone IS NULL
RETURNING customer_id, phone;
ROLLBACK;
~~~

**Đáp án:** Một hàng. Nếu phone đã khác NULL, không có cập nhật.

### Bài 7. Loại khỏi cập nhật các thành phố vốn đã là HCM

~~~sql
BEGIN;
UPDATE update_lab.customers
SET city = 'HCM'
WHERE is_active = true
  AND city IS DISTINCT FROM 'HCM'
RETURNING customer_id, city;
ROLLBACK;
~~~

**Đáp án:** Với seed, chỉ Binh (2) từ HAN được đổi sang HCM; An (1) và Dung (4) đã ở HCM; Chi (3) không active.

### Bài 8. Phân loại tier theo points

~~~sql
BEGIN;
UPDATE update_lab.customers
SET tier = CASE
    WHEN loyalty_points >= 100 THEN 'gold'
    WHEN loyalty_points >= 50 THEN 'silver'
    ELSE 'standard'
END
WHERE is_active
RETURNING customer_id, tier;
ROLLBACK;
~~~

**Đáp án:** An gold, Binh silver, Dung standard; Chi không được chọn.

### Bài 9. Tính sale_price từ bảng giảm giá

~~~sql
BEGIN;
UPDATE update_lab.products AS p
SET sale_price =
    ROUND(p.list_price * (1 - d.discount_percent / 100), 2)
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id
RETURNING p.product_id, p.sale_price;
ROLLBACK;
~~~

**Đáp án:** Coffee 27.00, Tea 19.00; Cup không có dòng discount nên không thay đổi.

### Bài 10. Vì sao UPDATE FROM order_items trực tiếp sai?

~~~sql
UPDATE update_lab.orders AS o
SET total_amount = i.quantity * i.unit_price
FROM update_lab.order_items AS i
WHERE i.order_id = o.order_id;
~~~

**Đáp án:** Một đơn có thể có nhiều dòng item. Với đơn 1001 có hai dòng, PostgreSQL không bảo đảm dùng dòng nào để gán, và không tự tính tổng. Phải GROUP BY `order_id` trước.

### Bài 11. Tính lại tổng của đơn 1001

~~~sql
BEGIN;
UPDATE update_lab.orders AS o
SET total_amount = COALESCE(
    (
        SELECT SUM(i.quantity * i.unit_price)
        FROM update_lab.order_items AS i
        WHERE i.order_id = o.order_id
    ),
    0
)
WHERE o.order_id = 1001
RETURNING o.order_id, o.total_amount;
ROLLBACK;
~~~

**Đáp án:** 2 × 30 + 1 × 20 = **80.00**.

### Bài 12. Chuyển đơn pending thành paid có điều kiện

~~~sql
BEGIN;
UPDATE update_lab.orders
SET
    status = 'paid',
    paid_at = now(),
    updated_at = now()
WHERE order_id = 1003
  AND status = 'pending'
RETURNING order_id, status, paid_at;
ROLLBACK;
~~~

**Đáp án:** Một hàng, đơn 1003 chuyển từ pending sang paid.

### Bài 13. Nếu đơn đã paid, UPDATE có điều kiện trả gì?

Thay `order_id = 1003` bằng `order_id = 1002` trong bài 12.

**Đáp án:** **0 hàng** vì đơn 1002 vốn đã paid, không thỏa `status = 'pending'`.

### Bài 14. Cập nhật thuộc tính JSONB

~~~sql
BEGIN;
UPDATE update_lab.products
SET attributes = jsonb_set(
    attributes,
    '{color}',
    to_jsonb('black'::text),
    true
)
WHERE product_id = 101
RETURNING attributes;
ROLLBACK;
~~~

**Đáp án:** `color = black`, `category = beverage` vẫn còn.

### Bài 15. Hoán đổi hai cột

~~~sql
BEGIN;
UPDATE update_lab.swap_demo
SET (a, b) = (b, a)
WHERE demo_id = 1
RETURNING a, b;
ROLLBACK;
~~~

**Đáp án:** a = 20, b = 10.

### Bài 16. Vì sao điều kiện dưới đây nguy hiểm?

~~~sql
WHERE customer_id = 1 AND status = 'pending'
   OR status = 'cancelled'
~~~

**Đáp án:** Do `AND` ưu tiên hơn `OR`, điều kiện có thể chọn đơn cancelled của mọi khách hàng. Cần `customer_id = 1 AND status IN ('pending','cancelled')` nếu đúng nghiệp vụ.

### Bài 17. Dùng CTE để cập nhật một đơn pending

~~~sql
BEGIN;
WITH chosen AS (
    SELECT order_id
    FROM update_lab.orders
    WHERE status = 'pending'
    ORDER BY order_id
    LIMIT 1
)
UPDATE update_lab.orders AS o
SET status = 'cancelled'
FROM chosen AS c
WHERE c.order_id = o.order_id
  AND o.status = 'pending'
RETURNING o.order_id, o.status;
ROLLBACK;
~~~

**Đáp án:** Theo seed, đơn 1001 được chọn.

### Bài 18. Optimistic locking chống ghi đè

~~~sql
BEGIN;
UPDATE update_lab.version_demo
SET
    quantity = 7,
    row_version = row_version + 1
WHERE item_id = 1
  AND row_version = 0
RETURNING quantity, row_version;
ROLLBACK;
~~~

**Đáp án:** Khi bản ghi còn version 0, có một hàng mới quantity 7, version 1. Nếu version đã đổi, UPDATE trả 0 hàng để báo xung đột.

## 40. Quy trình an toàn khi chuẩn bị UPDATE trong dự án thật

Trước khi thực thi một câu UPDATE có tác động đáng kể, hãy đi qua các bước:

1. **Xác định bảng đích và cột cần sửa.** Không thay những cột không liên quan.
2. **Viết điều kiện WHERE trước.** Ưu tiên khóa chính, khóa nghiệp vụ/tenant và trạng thái đầu vào phù hợp.
3. **Chạy SELECT thăm dò cùng điều kiện** để hiểu phạm vi dự kiến; nhớ dữ liệu có thể thay đổi đồng thời.
4. **Kiểm tra NULL và logic AND/OR.** Dùng dấu ngoặc và `IS DISTINCT FROM` nếu cần.
5. **Xác định biểu thức gán:** hằng, toán học, CASE, COALESCE, DEFAULT, subquery hoặc FROM.
6. **Nếu dùng UPDATE FROM, đảm bảo một nguồn mỗi hàng đích.** Sử dụng constraint, GROUP BY, DISTINCT ON hoặc scalar subquery đúng ngữ nghĩa.
7. **Đánh giá constraint/FK/trigger/RLS.** Điều kiện mới phải hợp lệ với tất cả ràng buộc liên quan.
8. **Đưa concurrency vào thiết kế:** điều kiện trạng thái, tăng/giảm trực tiếp, optimistic locking, row locks hoặc isolation phù hợp.
9. **Sử dụng RETURNING** để biết những hàng thực sự được cập nhật và giá trị mới.
10. **Đặt transaction boundary rõ ràng.** Xử lý lỗi và rollback; không để một nửa workflow ứng dụng được commit ngoài ý muốn.
11. **Với dữ liệu lớn, xem kế hoạch và quy mô:** index lọc, lock, WAL, trigger, vacuum và khả năng chia batch.
12. **Thử dữ liệu biên:** 0 hàng, một hàng, nhiều hàng, NULL, giá trị bằng nhau, trùng nguồn, constraint violation.
13. **Không tự coi UPDATE=0 là thành công nghiệp vụ.** Chuyển kết quả đó thành phản hồi API phù hợp.
14. **Không chạy thử destructive SQL trên production.** Dùng database lab/backup/quy trình migration.

Ví dụ mẫu cho một cập nhật có điều kiện, có thể kiểm tra kết quả:

~~~sql
BEGIN;

UPDATE update_lab.orders AS o
SET
    status = 'paid',
    paid_at = now(),
    updated_at = now()
WHERE o.order_id = 1001
  AND o.status = 'pending'
RETURNING
    o.order_id,
    o.customer_id,
    o.status,
    o.paid_at;

-- Trong lab, dùng ROLLBACK. Trong nghiệp vụ thật,
-- service phải quyết định COMMIT theo transaction boundary.
ROLLBACK;
~~~

## 41. Tài liệu PostgreSQL chính thức

Khi triển khai trong hệ thống thật, nên đối chiếu tài liệu đúng phiên bản server:

- [PostgreSQL — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): cú pháp `UPDATE`, `FROM`, `WHERE`, `RETURNING` và các lưu ý nhiều hàng nguồn.
- [PostgreSQL — Conditional Expressions](https://www.postgresql.org/docs/current/functions-conditional.html): `CASE`, `COALESCE`, `NULLIF`.
- [PostgreSQL — Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): `IS DISTINCT FROM`, `IS NULL` và so sánh.
- [PostgreSQL — JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): `jsonb_set`, các toán tử JSONB.
- [PostgreSQL — WITH Queries](https://www.postgresql.org/docs/current/queries-with.html): CTE và câu lệnh thay đổi dữ liệu.
- [PostgreSQL — Concurrency Control](https://www.postgresql.org/docs/current/mvcc.html): MVCC, transaction và hiệu ứng đồng thời.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): khóa hàng và các loại lock.
- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): quan sát kế hoạch và chi phí truy vấn.

Các liên kết `/current/` trỏ đến tài liệu phiên bản PostgreSQL hiện hành trên website. Với server chạy major version khác, mở tài liệu tương ứng để kiểm tra cú pháp và hành vi cụ thể.

## 42. Tổng kết

`UPDATE` là câu lệnh **chọn những hàng cần sửa rồi gán giá trị mới cho các cột của chúng**:

~~~sql
UPDATE target_table
SET
    column_a = expression_a,
    column_b = expression_b
WHERE selection_condition
RETURNING column_a, column_b;
~~~

Những quy tắc quan trọng nhất:

- **`WHERE` quyết định phạm vi:** thiếu `WHERE` có thể cập nhật toàn bảng.
- **`SET` có thể là biểu thức:** dùng cột cũ, phép toán, `CASE`, `COALESCE`, `DEFAULT`, subquery, dữ liệu nguồn hoặc hàm PostgreSQL.
- **Các phép gán đọc giá trị của hàng trước khi cập nhật**, không xử lý cột này xong rồi dùng ngay giá trị mới cho cột khác trong cùng SET.
- **NULL cần được xử lý tường minh:** `IS NULL`, `IS NOT NULL` và `IS DISTINCT FROM`.
- **`UPDATE ... FROM` phải có nguồn xác định:** một hàng đích khớp nhiều hàng nguồn có thể cho kết quả gán không dự đoán được.
- **`RETURNING` trả những hàng UPDATE đã xử lý**, giúp ứng dụng kiểm tra kết quả thay vì đoán.
- **Transaction, constraints và concurrency vẫn quan trọng:** một câu SQL đúng cú pháp chưa đủ bảo đảm quy tắc nghiệp vụ.

Trước khi sửa dữ liệu, hãy luôn biết **hàng nào được chọn, giá trị nào được gán, dữ liệu nguồn nào được dùng và kết quả sẽ được xác nhận ra sao**. Khi bốn điều này rõ ràng, `UPDATE` trở thành công cụ mạnh mẽ nhưng vẫn kiểm soát được trong PostgreSQL.
