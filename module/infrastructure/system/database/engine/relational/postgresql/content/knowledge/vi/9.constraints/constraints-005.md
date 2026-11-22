# FOREIGN KEY và bảo toàn quan hệ tham chiếu trong PostgreSQL

Trong một hệ thống bán hàng, đơn hàng phải thuộc về khách hàng có thật; mỗi dòng đơn hàng phải tham chiếu tới đơn và sản phẩm tồn tại. Nếu một lập trình viên chèn đơn với `customer_id = 999` trong khi bảng khách hàng không có mã đó, dữ liệu có thể bị **mồ côi** (*orphan record*). Nếu người khác xóa một sản phẩm đã được bán, các dòng lịch sử có còn hợp lệ không? Đây là những bài toán về **bảo toàn quan hệ tham chiếu** (*referential integrity*).

PostgreSQL giải quyết lớp bài toán này bằng **`FOREIGN KEY`**: một hoặc nhiều cột trong bảng **con** phải tham chiếu tới khóa hợp lệ trong bảng **cha**, ngoại trừ những trường hợp giá trị `NULL` được cho phép theo quy tắc của ràng buộc. Khóa ngoại không chỉ giúp vẽ sơ đồ quan hệ; nó được PostgreSQL kiểm tra khi ghi dữ liệu và phối hợp với transaction, khóa và các hành động `ON DELETE`/`ON UPDATE`.

Bài học trình bày cách khai báo khóa ngoại, dữ liệu mẫu để kiểm chứng, tác động khi xóa hoặc sửa bản ghi cha, khóa ngoại nhiều cột, `MATCH SIMPLE`/`MATCH FULL`, `DEFERRABLE`, quy trình thêm khóa ngoại cho bảng lớn bằng `NOT VALID`, vấn đề chỉ mục và xử lý lỗi. Ví dụ dùng PostgreSQL hiện đại, chạy trong **schema thực hành riêng**. Các lệnh cố ý gây lỗi được ghi rõ; không chạy trên production.

## 1. Mục tiêu và mô hình quan hệ

Sau bài học, người học cần:

1. Nhận ra được **bảng tham chiếu** (*referencing/child table*) và **bảng được tham chiếu** (*referenced/parent table*).
2. Tạo `FOREIGN KEY` ở mức cột hoặc ở mức bảng và giải thích sự khác biệt với `PRIMARY KEY`, `UNIQUE`, `CHECK`.
3. Biết khi nào PostgreSQL từ chối `INSERT`, `UPDATE` và `DELETE` với mã lỗi `23503`.
4. Chọn đúng `ON DELETE`/`ON UPDATE` thay vì mặc định dùng `CASCADE` cho mọi quan hệ.
5. Hiểu cách `NULL` và khóa ngoại nhiều cột tác động đến tính toàn vẹn.
6. Sử dụng `DEFERRABLE` khi cần tạm thời đảo thứ tự thao tác trong **cùng transaction**, nhưng vẫn phải hợp lệ trước commit.
7. Kiểm tra metadata ràng buộc, phát hiện tham chiếu mồ côi trong dữ liệu cũ và quản lý hiệu năng của các thao tác liên quan.

### 1.1. Sơ đồ ví dụ

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : ordered_product

    CUSTOMERS {
        bigint customer_id PK
        text customer_code UK
        text full_name
    }
    PRODUCTS {
        bigint product_id PK
        text sku UK
        numeric list_price
    }
    ORDERS {
        bigint order_id PK
        text order_no UK
        bigint customer_id FK
        text order_status
    }
    ORDER_ITEMS {
        bigint order_id PK,FK
        bigint product_id PK,FK
        integer quantity
        numeric unit_price
    }
~~~

Mỗi khách hàng có thể có nhiều đơn. Mỗi đơn có thể có nhiều dòng. Một sản phẩm có thể xuất hiện ở nhiều đơn; bảng `order_items` biến quan hệ **nhiều–nhiều** giữa đơn và sản phẩm thành hai quan hệ một–nhiều.

**Khóa ngoại nằm ở bảng con.** Ví dụ:

~~~text
customers.customer_id  <---- orders.customer_id
  khóa chính cha                 khóa ngoại con

orders.order_id         <---- order_items.order_id
products.product_id     <---- order_items.product_id
~~~

Khóa chính của `order_items` là **cặp `(order_id, product_id)`**. Điều đó ngăn một sản phẩm xuất hiện hai dòng trong cùng một đơn, nhưng không ngăn sản phẩm đó xuất hiện trong nhiều đơn khác.

## 2. FOREIGN KEY thực sự đảm bảo điều gì?

Một khai báo cơ bản:

~~~sql
CREATE TABLE child (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL
        REFERENCES parent(parent_id)
);
~~~

Giả sử `parent.parent_id` là khóa chính. Khi chèn một dòng con có `parent_id = 15`, PostgreSQL yêu cầu **tồn tại một dòng cha có khóa bằng 15**. Nếu không tồn tại, thao tác ghi thất bại.

Tính toàn vẹn được kiểm tra theo cả hai hướng thay đổi:

- **Chèn/cập nhật bảng con:** có đang tham chiếu tới một khóa cha tồn tại không?
- **Xóa/cập nhật khóa ở bảng cha:** phải xử lý thế nào với những dòng con hiện còn trỏ đến khóa đó?

Ràng buộc được quản lý trong database, vì vậy nó bảo vệ dữ liệu ngay cả khi có nhiều ứng dụng, job batch hoặc phiên `psql` ghi đồng thời. Nếu chỉ kiểm tra bằng một câu `SELECT` ở ứng dụng rồi mới `INSERT`, giữa hai thao tác một transaction khác có thể thay đổi dữ liệu cha; kiểm tra ở application **không thay thế** khóa ngoại của database.

### 2.1. FOREIGN KEY khác những ràng buộc khác

| Ràng buộc | Kiểm tra điều gì? | Ví dụ |
| --- | --- | --- |
| `PRIMARY KEY` | Định danh duy nhất, không `NULL` cho một bảng | `customers.customer_id` |
| `UNIQUE` | Giá trị hoặc tổ hợp giá trị không trùng theo ngữ nghĩa unique | `products.sku` |
| `NOT NULL` | Cột bắt buộc có giá trị khác `NULL` | `orders.customer_id` |
| `CHECK` | Biểu thức điều kiện áp trên hàng | `quantity > 0` |
| **`FOREIGN KEY`** | Giá trị cột/tổ hợp cột con trỏ tới khóa hợp lệ ở bảng cha | `orders.customer_id → customers.customer_id` |

Một `FOREIGN KEY` **không tự đảm bảo** rằng mọi khách hàng phải có đơn, hoặc mọi đơn phải có ít nhất một dòng. Khóa ngoại bảo vệ hướng **con trỏ tới cha**, không buộc cha phải có con.

### 2.2. Một số quy tắc không thuộc phạm vi FOREIGN KEY

Khóa ngoại không tự xác nhận:

- Tổng tiền thanh toán bằng tổng chi tiết đơn.
- Một đơn `PAID` bắt buộc có dòng hàng và đã thu đủ tiền.
- Sản phẩm còn đủ tồn kho.
- Một khách hàng chỉ đặt tối đa ba đơn trong ngày.
- Một danh mục sản phẩm không có vòng lặp cha–con.

Các quy tắc trên có thể cần ràng buộc khác, transaction, trigger, exclusion constraint hoặc logic nghiệp vụ được thiết kế phù hợp.

## 3. Tạo lược đồ thực hành có khóa ngoại

Hãy chạy các lệnh dưới đây **một lần trên database lab có schema mới**. Không dùng schema production. Nếu `fk_lab_119` đã tồn tại và chứa dữ liệu, hãy chọn một tên thực hành khác thay vì tự ý xóa.

### 3.1. Tạo bảng cha: customers và products

~~~sql
CREATE SCHEMA fk_lab_119;

CREATE TABLE fk_lab_119.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);

CREATE TABLE fk_lab_119.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL
        CHECK (list_price > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
~~~

Ở đây sử dụng ID kiểu `BIGINT` được chèn rõ ràng để dữ liệu mẫu dễ kiểm chứng. Trong ứng dụng thực, ID thường được cấp bằng `GENERATED ... AS IDENTITY` hoặc một cơ chế ổn định tương đương; ngữ nghĩa khóa ngoại không thay đổi.

### 3.2. Tạo bảng orders với FOREIGN KEY

~~~sql
CREATE TABLE fk_lab_119.orders (
    order_id BIGINT PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'NEW',
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT orders_status_check
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES fk_lab_119.customers (customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);
~~~

`CONSTRAINT fk_orders_customer` là **tên ràng buộc** do ta đặt. Tên rõ ràng giúp đọc thông báo lỗi, chạy migration và truy vấn system catalog.

`ON DELETE RESTRICT` có nghĩa không được xóa khách hàng nếu vẫn còn đơn tham chiếu. `ON UPDATE RESTRICT` ngăn thay đổi khóa khách hàng theo cách làm hỏng những liên kết này. Trong hệ thống giao dịch, thường **không cần đổi khóa ID**; nếu khách thay đổi tên hoặc email thì sửa các thuộc tính, không phải đổi `customer_id`.

### 3.3. Tạo bảng order_items với hai khóa ngoại

~~~sql
CREATE TABLE fk_lab_119.order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price > 0),

    CONSTRAINT order_items_pk
        PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES fk_lab_119.orders (order_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES fk_lab_119.products (product_id)
        ON DELETE RESTRICT
);
~~~

Bảng này cố tình sử dụng **hai chính sách xóa khác nhau**:

- `fk_items_order ON DELETE CASCADE`: nếu chủ động xóa một **đơn** thì các dòng hàng trực thuộc đơn cũng bị xóa theo.
- `fk_items_product ON DELETE RESTRICT`: nếu một **sản phẩm** đã xuất hiện trong chi tiết đơn, không được xóa sản phẩm đó.

Đây là mô hình **giảng dạy** để quan sát từng hành động. Trong production, xóa vật lý đơn hàng và lịch sử bán hàng thường cần hạn chế mạnh hơn vì yêu cầu kế toán, kiểm toán và khôi phục. Việc dùng `CASCADE` không phải mặc định nên áp dụng cho lịch sử giao dịch.

### 3.4. Nạp dữ liệu mẫu

~~~sql
INSERT INTO fk_lab_119.customers
    (customer_id, customer_code, full_name)
VALUES
    (1, 'C001', 'Nguyễn An'),
    (2, 'C002', 'Trần Bình'),
    (3, 'C003', 'Lê Chi');

INSERT INTO fk_lab_119.products
    (product_id, sku, product_name, list_price)
VALUES
    (10, 'BOOK-01', 'Sách PostgreSQL', 150000.00),
    (20, 'PEN-01', 'Bút bi xanh',        20000.00),
    (30, 'MOUSE-01', 'Chuột không dây', 280000.00);

INSERT INTO fk_lab_119.orders
    (order_id, order_no, customer_id, order_status)
VALUES
    (100, 'SO-100', 1, 'PAID'),
    (200, 'SO-200', 2, 'NEW');

INSERT INTO fk_lab_119.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (100, 10, 2, 150000.00),
    (100, 20, 3,  20000.00),
    (200, 30, 1, 280000.00);
~~~

Mọi khóa ngoại đều hợp lệ: các khách hàng `1`, `2` tồn tại; các đơn `100`, `200` tồn tại; các sản phẩm `10`, `20`, `30` tồn tại.

### 3.5. Kiểm tra kết quả seed

~~~sql
SELECT
    (SELECT COUNT(*) FROM fk_lab_119.customers) AS customers,
    (SELECT COUNT(*) FROM fk_lab_119.products) AS products,
    (SELECT COUNT(*) FROM fk_lab_119.orders) AS orders,
    (SELECT COUNT(*) FROM fk_lab_119.order_items) AS order_items;
~~~

Kỳ vọng lần lượt: **3 khách, 3 sản phẩm, 2 đơn, 3 dòng đơn**.

~~~sql
SELECT
    o.order_no,
    c.customer_code,
    c.full_name,
    COUNT(oi.product_id) AS line_count,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS order_total
FROM fk_lab_119.orders AS o
JOIN fk_lab_119.customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN fk_lab_119.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id, o.order_no, c.customer_code, c.full_name
ORDER BY o.order_id;
~~~

| Đơn | Khách hàng | Dòng hàng | Tổng tiền |
| --- | --- | ---: | ---: |
| `SO-100` | `C001` | 2 | 360.000 |
| `SO-200` | `C002` | 1 | 280.000 |

Giá lịch sử đặt trong `order_items.unit_price`, không tính lại bằng `products.list_price` sau khi sản phẩm đổi giá. Dùng `LEFT JOIN` giúp đơn chưa có dòng vẫn xuất hiện; khóa ngoại không bắt buộc đơn phải có dòng hàng.

## 4. Ba cách viết FOREIGN KEY

### 4.1. Cú pháp mức cột

Nếu mỗi khóa ngoại chỉ có một cột:

~~~sql
CREATE TABLE fk_lab_119.simple_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES fk_lab_119.customers (customer_id)
);
~~~

Từ khóa `REFERENCES` xuất hiện ngay sau định nghĩa cột. Không chỉ định `ON DELETE` sẽ dùng hành động mặc định là `NO ACTION`.

### 4.2. Cú pháp mức bảng

~~~sql
CREATE TABLE fk_lab_119.simple_orders_2 (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_simple_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES fk_lab_119.customers (customer_id)
);
~~~

Mức bảng thuận tiện khi có nhiều cột, cần đặt tên rõ ràng hoặc thêm tùy chọn `MATCH`/`ON DELETE`/`DEFERRABLE`.

**Chỉ dùng một trong hai bảng ví dụ nếu muốn thực hành**; `simple_orders` và `simple_orders_2` là bảng bổ sung, không tham gia bộ dữ liệu chính.

### 4.3. Thêm khóa ngoại bằng ALTER TABLE

Khi bảng con đã tồn tại:

~~~sql
ALTER TABLE fk_lab_119.simple_orders
ADD CONSTRAINT fk_simple_orders_customer
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers (customer_id);
~~~

Câu này giả định bảng `simple_orders` đã tạo ở mục 4.1 **mà không có ràng buộc inline**. Nếu chạy đúng DDL ở mục 4.1, bảng đã có một FK tương đương; thêm lại sẽ tạo thêm một ràng buộc trùng ý nghĩa và gây overhead không cần thiết. Để minh họa `ALTER TABLE` thật sự trên bảng cũ, dùng một bảng mới **chưa khai báo FK**:

~~~sql
CREATE TABLE fk_lab_119.import_orders (
    import_order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
);

ALTER TABLE fk_lab_119.import_orders
ADD CONSTRAINT fk_import_orders_customer
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers (customer_id);
~~~

Khi thêm FK theo cách thông thường, PostgreSQL phải đảm bảo dữ liệu đã có ở bảng con phù hợp. Nếu có dòng mồ côi, việc thêm ràng buộc sẽ thất bại. Cơ chế `NOT VALID` dành cho dữ liệu lịch sử lớn được trình bày ở mục 13.

## 5. Khóa được tham chiếu phải có tính duy nhất phù hợp

Một FK không thể chỉ tham chiếu **bất kỳ cột có giá trị trùng nhau**. PostgreSQL cần một khóa ở bảng cha đảm bảo rằng mỗi tổ hợp giá trị tham chiếu trỏ đến một bản ghi cha hợp lệ theo quy định.

Thông thường mục tiêu là:

- `PRIMARY KEY` của bảng cha; hoặc
- Các cột có **`UNIQUE` constraint không hoãn kiểm tra** phù hợp; hoặc
- Tập cột được bảo đảm bằng **unique index không partial** đủ điều kiện để làm đích tham chiếu.

Ví dụ FK trỏ tới **mã nghiệp vụ unique**:

~~~sql
CREATE TABLE fk_lab_119.customer_notes (
    note_id BIGINT PRIMARY KEY,
    customer_code TEXT NOT NULL,
    content TEXT NOT NULL,

    CONSTRAINT fk_notes_customer_code
        FOREIGN KEY (customer_code)
        REFERENCES fk_lab_119.customers (customer_code)
);
~~~

Vì `customers.customer_code` có `UNIQUE`, nó có thể được tham chiếu. Mặc dù vậy, mã nghiệp vụ thường dễ thay đổi hơn surrogate ID; cần cân nhắc `ON UPDATE` và vòng đời dữ liệu trước khi quyết định dùng làm FK.

### 5.1. Vì sao không tham chiếu cột tên?

Nếu tên khách là `Nguyễn An`, có thể có nhiều người cùng tên. Một FK tới `full_name` sẽ không đủ bảo đảm tính duy nhất và không thể dựa vào tên hiển thị để xác định chính xác khách hàng. **Không cố thêm unique constraint cho tên chỉ để khóa ngoại tạo được** nếu nghiệp vụ cho phép tên trùng.

### 5.2. Unique partial index không thay khóa tham chiếu tổng quát

Một index unique có điều kiện:

~~~sql
-- Ví dụ khái niệm:
-- CREATE UNIQUE INDEX uq_active_sku
-- ON products(sku) WHERE is_active;
~~~

chỉ đảm bảo duy nhất cho tập con thỏa `WHERE`. Nó **không đủ** để FK chung tham chiếu cột `sku` ở mọi trạng thái vì một số dòng ngoài predicate không được bảo đảm như yêu cầu của FK. Đích FK cần khóa/index unique phù hợp và không partial.

### 5.3. Kiểu và thứ tự cột phải tương thích

PostgreSQL phải có cơ chế so sánh bằng nhau phù hợp giữa giá trị FK và khóa cha. Không nên dùng kiểu dữ liệu hoặc collation tùy tiện khác nhau rồi mong FK tự ép mọi thứ an toàn. Với schema mới, cách dễ kiểm soát là để cột con cùng kiểu logic với khóa cha; ví dụ đều là `BIGINT`.

Trong khóa nhiều cột, **cặp tương ứng được xác định theo thứ tự khai báo**. Sai thứ tự có thể khiến ràng buộc không hợp lệ hoặc kiểm tra sai ý định.

## 6. Thử vi phạm khóa ngoại khi ghi bảng con

Trong các phép thử dưới đây, **mục tiêu là quan sát lỗi có chủ ý**, không phải nạp dữ liệu mẫu mới. Chạy từng phép thử trên database lab. Trong PostgreSQL, một statement lỗi bên trong transaction có thể khiến transaction chuyển sang trạng thái aborted; sau đó cần `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` trước khi tiếp tục.

### 6.1. INSERT với customer_id không tồn tại

~~~sql
BEGIN;
SAVEPOINT before_invalid_insert;

INSERT INTO fk_lab_119.orders
    (order_id, order_no, customer_id)
VALUES
    (900, 'SO-INVALID-900', 999);
-- Dự kiến: ERROR, SQLSTATE 23503 (foreign_key_violation).

ROLLBACK TO SAVEPOINT before_invalid_insert;
ROLLBACK;
~~~

Không có khách hàng `999`. PostgreSQL từ chối dòng đơn trước khi transaction có thể commit một trạng thái vi phạm FK.

Một thông báo điển hình có nội dung gần như:

~~~text
ERROR:  insert or update on table "orders"
        violates foreign key constraint "fk_orders_customer"
DETAIL: Key (customer_id)=(999) is not present in table "customers".
SQLSTATE: 23503
~~~

Nội dung chi tiết/đường dẫn schema có thể khác theo client, phiên bản và ngữ cảnh. `23503` là mã SQLSTATE để ứng dụng phân loại lỗi tham chiếu.

### 6.2. UPDATE cột FK sang khóa không tồn tại

~~~sql
BEGIN;
SAVEPOINT before_invalid_update;

UPDATE fk_lab_119.orders
SET customer_id = 999
WHERE order_id = 100;
-- Dự kiến: SQLSTATE 23503.

ROLLBACK TO SAVEPOINT before_invalid_update;
ROLLBACK;
~~~

Không chỉ `INSERT`, cả `UPDATE` thay đổi FK cũng phải giữ quan hệ hợp lệ. Sau rollback, đơn `100` vẫn thuộc khách `1`.

### 6.3. INSERT chi tiết đơn với sản phẩm không tồn tại

~~~sql
BEGIN;
SAVEPOINT before_invalid_item;

INSERT INTO fk_lab_119.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (100, 999, 1, 100000.00);
-- Dự kiến: SQLSTATE 23503 do fk_items_product.

ROLLBACK TO SAVEPOINT before_invalid_item;
ROLLBACK;
~~~

Đơn `100` tồn tại, nhưng sản phẩm `999` không tồn tại. **Một dòng có nhiều FK phải thỏa tất cả FK liên quan**. Nếu đơn và sản phẩm đều không tồn tại, không nên dựa vào việc PostgreSQL “luôn báo lỗi khóa nào trước” để quyết định logic nghiệp vụ.

### 6.4. Phân biệt lỗi FK với lỗi khác

| SQLSTATE | Lỗi điển hình | Ví dụ |
| --- | --- | --- |
| `23503` | `foreign_key_violation` | Khách hàng tham chiếu không tồn tại |
| `23505` | `unique_violation` | Trùng `order_no` hoặc trùng PK |
| `23502` | `not_null_violation` | `orders.customer_id = NULL` |
| `23514` | `check_violation` | `quantity = 0` |

Ứng dụng Java dùng PostgreSQL JDBC có thể lấy SQLSTATE từ `SQLException.getSQLState()`, sau đó ánh xạ thành lỗi nghiệp vụ phù hợp. Không nên trả nguyên thông báo SQL chứa chi tiết database ra API công khai.

**Lưu ý thực hành:** một số client hoặc script `psql` cấu hình dừng ngay khi statement lỗi sẽ không tự chạy các dòng `ROLLBACK TO SAVEPOINT` tiếp theo. Khi đó phải chủ động rollback hoặc để framework test bắt exception và quản lý transaction.

## 7. Xóa bản ghi cha: NO ACTION, RESTRICT, CASCADE, SET NULL, SET DEFAULT

Một quan hệ FK phải xác định hành vi khi **xóa hoặc đổi khóa** ở bảng cha. PostgreSQL có các lựa chọn chính:

| Hành động | Khi khóa cha bị xóa/cập nhật | Tình huống sử dụng |
| --- | --- | --- |
| `NO ACTION` | Nếu cuối thời điểm kiểm tra còn tham chiếu không hợp lệ thì từ chối; là hành động mặc định | Cần bảo toàn tham chiếu, có thể kết hợp defer khi được phép |
| `RESTRICT` | Từ chối thao tác làm ảnh hưởng dòng cha đang được tham chiếu theo cơ chế kiểm tra ngay | Bảo vệ lịch sử không cho xóa/sửa khóa cha |
| `CASCADE` | Xóa dòng con theo xóa cha, hoặc cập nhật giá trị FK khi khóa cha đổi | Dữ liệu con thật sự phụ thuộc vòng đời cha |
| `SET NULL` | Đặt FK của con thành `NULL` | Quan hệ tùy chọn; cho phép giữ dòng con không gắn cha |
| `SET DEFAULT` | Đặt FK của con về giá trị mặc định đã khai báo | Chuyển sang một giá trị mặc định hợp lệ theo nghiệp vụ |

Các hành động có thể được khai báo riêng:

~~~sql
FOREIGN KEY (parent_id)
REFERENCES some_schema.parent_table(id)
ON DELETE CASCADE
ON UPDATE RESTRICT
~~~

Không được suy ra `ON DELETE` mặc định là `CASCADE`. Trong PostgreSQL, mặc định là **`NO ACTION`**.

### 7.1. RESTRICT: giữ khách hàng khi còn đơn

Trong lược đồ đã tạo:

~~~sql
CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers(customer_id)
ON DELETE RESTRICT
~~~

Thử:

~~~sql
BEGIN;
SAVEPOINT before_delete_customer;

DELETE FROM fk_lab_119.customers
WHERE customer_id = 1;
-- Dự kiến: SQLSTATE 23503, vì đơn 100 đang tham chiếu khách 1.

ROLLBACK TO SAVEPOINT before_delete_customer;
ROLLBACK;
~~~

Vì còn đơn `SO-100`, PostgreSQL từ chối xóa khách `C001`. Đây là lựa chọn phù hợp khi lịch sử giao dịch cần giữ và ứng dụng không cho xóa vật lý khách đang có đơn.

### 7.2. CASCADE: xóa các dòng chi tiết khi xóa đơn

`order_items.order_id` được khai báo `ON DELETE CASCADE`. Hãy kiểm tra trong transaction rồi rollback:

~~~sql
BEGIN;

SELECT COUNT(*) AS before_delete
FROM fk_lab_119.order_items
WHERE order_id = 100;
-- 2

DELETE FROM fk_lab_119.orders
WHERE order_id = 100;
-- Xóa đơn 100 và tự động xóa hai dòng chi tiết liên quan.

SELECT COUNT(*) AS after_delete
FROM fk_lab_119.order_items
WHERE order_id = 100;
-- 0 trong transaction hiện tại.

ROLLBACK;
~~~

Sau rollback, cả đơn `100` lẫn hai dòng chi tiết trở lại như ban đầu. Lệnh `DELETE FROM orders` ở đây không bị FK từ `customers` ngăn, vì ta đang **xóa bảng con orders** đối với quan hệ khách–đơn; đồng thời hành động CASCADE áp dụng cho quan hệ đơn–chi tiết.

**Cẩn trọng:** CASCADE có thể lan qua nhiều tầng quan hệ. Một câu `DELETE` với điều kiện sai có thể xóa rất nhiều dữ liệu liên quan, gây tải và lock kéo dài. Trong bảng có dữ liệu quan trọng, hãy cân nhắc xóa mềm (*soft delete*), chính sách lưu trữ và việc có thực sự nên xóa lịch sử hay không.

### 7.3. RESTRICT bảo vệ sản phẩm đã xuất hiện trong đơn

~~~sql
BEGIN;
SAVEPOINT before_delete_product;

DELETE FROM fk_lab_119.products
WHERE product_id = 10;
-- Dự kiến: SQLSTATE 23503 do fk_items_product.

ROLLBACK TO SAVEPOINT before_delete_product;
ROLLBACK;
~~~

Sản phẩm `10` đã có trong đơn `100`. Nếu doanh nghiệp ngừng bán, thường hợp lý hơn khi cập nhật `is_active = FALSE` mà vẫn giữ bản ghi để lịch sử bán hàng tra cứu được:

~~~sql
BEGIN;

UPDATE fk_lab_119.products
SET is_active = FALSE
WHERE product_id = 10;

ROLLBACK;
~~~

FK không tự cấm tham chiếu một sản phẩm đã `is_active = FALSE`. Nếu chỉ cho phép bán sản phẩm đang hoạt động, ứng dụng phải kiểm tra nghiệp vụ trong transaction hoặc thiết kế thêm cơ chế kiểm soát phù hợp.

### 7.4. SET NULL: quan hệ tùy chọn

Ví dụ một bài viết có người biên tập phụ trách, nhưng khi người đó rời hệ thống bài viết vẫn cần tồn tại:

~~~sql
CREATE TABLE fk_lab_119.editors (
    editor_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE fk_lab_119.articles (
    article_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    editor_id BIGINT NULL,
    CONSTRAINT fk_articles_editor
        FOREIGN KEY (editor_id)
        REFERENCES fk_lab_119.editors(editor_id)
        ON DELETE SET NULL
);
~~~

Sau khi xóa người biên tập, `articles.editor_id` được đặt thành `NULL`. **Cột phải cho phép NULL** nếu muốn hành động này thành công. Nếu cột được khai báo `NOT NULL`, thao tác đặt NULL sẽ gặp lỗi; PostgreSQL không tự bỏ ràng buộc NOT NULL.

Đối với khóa ngoại tổng hợp, các phiên bản PostgreSQL hiện đại có cú pháp chọn một số cột nhận `SET NULL` trong hành động `ON DELETE` khi cần; đây là khả năng đặc thù cần dùng thận trọng để giữ các cột bắt buộc khác.

### 7.5. SET DEFAULT: giá trị mặc định vẫn phải tham chiếu hợp lệ

Giả sử khi một nhóm phụ trách bị xóa, bản ghi được chuyển sang nhóm “Chưa phân loại” có ID bằng 0:

~~~sql
CREATE TABLE fk_lab_119.groups (
    group_id BIGINT PRIMARY KEY,
    group_name TEXT NOT NULL
);

INSERT INTO fk_lab_119.groups(group_id, group_name)
VALUES (0, 'Chưa phân loại');

CREATE TABLE fk_lab_119.group_documents (
    document_id BIGINT PRIMARY KEY,
    group_id BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_documents_group
        FOREIGN KEY (group_id)
        REFERENCES fk_lab_119.groups(group_id)
        ON DELETE SET DEFAULT
);
~~~

`SET DEFAULT` **không bỏ qua FK**. Nếu giá trị mặc định là 0 nhưng không có nhóm `0`, thao tác xóa cha dẫn đến giá trị không hợp lệ và có thể thất bại. Nếu cột không có `DEFAULT`, giá trị mặc định thường là `NULL`, cũng phải phù hợp với `NOT NULL` và các ràng buộc khác.

### 7.6. Chọn chính sách xóa theo ý nghĩa dữ liệu

| Quan hệ nghiệp vụ | Chính sách có thể phù hợp | Cần đánh giá |
| --- | --- | --- |
| Khách hàng → đơn hàng đã phát sinh | `RESTRICT`/`NO ACTION` | Không vô tình xóa lịch sử, dữ liệu kế toán |
| Đơn tạm → dòng giỏ hàng tạm | `CASCADE` | Dòng con không có ý nghĩa độc lập |
| Người phụ trách → bài viết | `SET NULL` | Có cho phép bài viết chưa được gán người? |
| Nhóm → tài liệu | `SET DEFAULT` | Có bản ghi mặc định hợp lệ? |
| Sản phẩm → lịch sử bán hàng | `RESTRICT` hoặc ngừng bán mềm | Cần bảo toàn SKU/giá lịch sử |

Đừng biến mọi quan hệ thành CASCADE chỉ để xóa dữ liệu cho “tiện”. Quyết định cần xuất phát từ **vòng đời của thực thể và yêu cầu lưu lịch sử**.

## 8. ON UPDATE: khi khóa cha đổi

`ON UPDATE` xử lý khi **giá trị khóa được tham chiếu ở bảng cha thay đổi**. Việc sửa một cột thông thường không nằm trong khóa được tham chiếu (như `full_name`) không làm phát sinh vấn đề thay đổi FK theo nghĩa này.

Ví dụ:

~~~sql
CREATE TABLE fk_lab_119.regions (
    region_code TEXT PRIMARY KEY,
    region_name TEXT NOT NULL
);

CREATE TABLE fk_lab_119.stores (
    store_id BIGINT PRIMARY KEY,
    region_code TEXT NOT NULL,
    CONSTRAINT fk_stores_region
        FOREIGN KEY (region_code)
        REFERENCES fk_lab_119.regions(region_code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

INSERT INTO fk_lab_119.regions
    (region_code, region_name)
VALUES ('NORTH', 'Miền Bắc');

INSERT INTO fk_lab_119.stores
    (store_id, region_code)
VALUES (1, 'NORTH');
~~~

Nếu đổi mã vùng trong transaction:

~~~sql
BEGIN;

UPDATE fk_lab_119.regions
SET region_code = 'NORTH-V2'
WHERE region_code = 'NORTH';

SELECT store_id, region_code
FROM fk_lab_119.stores
WHERE store_id = 1;
-- region_code của store 1 đã thành NORTH-V2.

ROLLBACK;
~~~

`ON UPDATE CASCADE` tự đổi khóa ngoại ở bảng con thành giá trị mới. Tuy nhiên, việc thay khóa chính/mã nghiệp vụ sau khi đã được tham chiếu rộng rãi có thể tốn chi phí, khóa nhiều hàng và tác động hệ thống khác; với surrogate key không thay đổi, thường không cần dựa vào cascade cập nhật thường xuyên.

## 9. NO ACTION khác RESTRICT ở thời điểm kiểm tra

Trong nhiều trường hợp bình thường, `NO ACTION` và `RESTRICT` đều làm người dùng thấy một câu `DELETE` bị từ chối khi còn dòng con. Sự khác biệt quan trọng là **khả năng trì hoãn kiểm tra**.

- **`NO ACTION`** là mặc định. Với constraint không deferrable hoặc đang ở chế độ immediate, kiểm tra xảy ra tại thời điểm thích hợp của statement. Nếu FK được khai báo `DEFERRABLE` và đang ở chế độ deferred, việc xác nhận tham chiếu hợp lệ có thể được trì hoãn đến cuối transaction.
- **`RESTRICT`** không cho trì hoãn **hành động hạn chế tương ứng** theo cách đó; PostgreSQL ngăn việc xóa/sửa khóa cha đang được tham chiếu ngay trong ngữ cảnh hành động.
- **`CASCADE`/`SET NULL`/`SET DEFAULT`** là các hành động tham chiếu làm thay đổi dữ liệu con. Không nên giả định hành động này được hoãn tới `COMMIT` chỉ vì constraint khai báo `DEFERRABLE`.

### 9.1. Tình huống cần hoãn kiểm tra

Giả sử muốn chuyển quan hệ từ khóa cha cũ sang khóa cha mới trong **cùng transaction**. Tại một thời điểm trung gian, cặp dữ liệu có thể chưa hợp lệ, nhưng cuối giao dịch mọi tham chiếu được sửa xong.

Với `NO ACTION DEFERRABLE`, ứng dụng có thể dùng `SET CONSTRAINTS ... DEFERRED` để trì hoãn phép kiểm tra thuộc nhóm được phép. `RESTRICT` không phải lựa chọn thích hợp nếu chủ đích là cho phép trạng thái tham chiếu tạm thời chưa hợp lệ trong transaction.

**Đây không phải cách cho phép dữ liệu mồ côi được commit.** Việc trì hoãn chỉ đổi **thời điểm kiểm tra**, không xóa quy tắc toàn vẹn.

## 10. DEFERRABLE và SET CONSTRAINTS trong một transaction

PostgreSQL cho phép một số constraint, trong đó có foreign key, được khai báo:

~~~sql
DEFERRABLE INITIALLY IMMEDIATE
~~~

hoặc:

~~~sql
DEFERRABLE INITIALLY DEFERRED
~~~

| Khai báo | Mặc định kiểm tra | Có thể dùng SET CONSTRAINTS để đổi? |
| --- | --- | --- |
| `NOT DEFERRABLE` | Immediate | Không |
| `DEFERRABLE INITIALLY IMMEDIATE` | Immediate | Có, sang deferred trong transaction |
| `DEFERRABLE INITIALLY DEFERRED` | Deferred | Có, sang immediate trong transaction |

### 10.1. Tạo ví dụ riêng để kiểm tra FK trì hoãn

~~~sql
CREATE TABLE fk_lab_119.deferred_parents (
    parent_id BIGINT PRIMARY KEY
);

CREATE TABLE fk_lab_119.deferred_children (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL,
    CONSTRAINT fk_deferred_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES fk_lab_119.deferred_parents(parent_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Trong transaction:

~~~sql
BEGIN;

SET CONSTRAINTS fk_deferred_child_parent DEFERRED;

-- Tạm thời chưa có parent_id = 700:
INSERT INTO fk_lab_119.deferred_children
    (child_id, parent_id)
VALUES (1, 700);

-- Bổ sung cha trước khi commit:
INSERT INTO fk_lab_119.deferred_parents(parent_id)
VALUES (700);

COMMIT;
~~~

Vì ràng buộc đã chuyển sang deferred trong transaction và dòng cha được chèn trước `COMMIT`, quan hệ cuối cùng hợp lệ.

Nếu bỏ lệnh chèn cha, `COMMIT` sẽ **bị từ chối** bằng `23503`. Khi đó transaction không commit dữ liệu mồ côi. Đây là cơ chế kiểm tra tính toàn vẹn **tại thời điểm kết thúc**, không phải bỏ FK.

### 10.2. Chuyển từ DEFERRED về IMMEDIATE

~~~sql
BEGIN;
SET CONSTRAINTS fk_deferred_child_parent DEFERRED;

-- Các thao tác cần trì hoãn ở đây.

SET CONSTRAINTS fk_deferred_child_parent IMMEDIATE;
-- PostgreSQL kiểm tra các vi phạm đang bị hoãn ngay tại đây.

ROLLBACK;
~~~

`SET CONSTRAINTS ... IMMEDIATE` kiểm tra hồi tố những vi phạm đã được tạm hoãn. Nếu kiểm tra thất bại, việc chuyển trạng thái không thành công và ứng dụng cần xử lý lỗi/rollback theo quy tắc transaction.

### 10.3. Khi nào nên dùng DEFERRABLE?

Phù hợp khi:

- Nhập dữ liệu có quan hệ vòng trong cùng transaction và đã có mô hình/đường kiểm tra rõ.
- Hoán đổi hoặc tái cấu trúc các quan hệ mà trạng thái trung gian chưa hợp lệ.
- Thực hiện batch nhiều bước có thể sắp xếp lại thứ tự nhưng vẫn bảo đảm commit hợp lệ.

Không nên bật deferred cho mọi FK chỉ để tránh lỗi import. Lỗi có thể dồn tới `COMMIT`, khiến transaction lớn phải rollback muộn hơn và khó xác định dòng nguyên nhân. Nếu có thể nạp **cha trước, con sau**, đó thường là cách đơn giản hơn.

## 11. NULL trong khóa ngoại: MATCH SIMPLE và MATCH FULL

Một khóa ngoại **không đồng nghĩa cột bắt buộc khác NULL**. Nếu cột con cho phép `NULL`, quy tắc tham chiếu phụ thuộc `MATCH`.

### 11.1. FK một cột có thể NULL

~~~sql
CREATE TABLE fk_lab_119.optional_orders (
    optional_order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NULL,
    CONSTRAINT fk_optional_customer
        FOREIGN KEY (customer_id)
        REFERENCES fk_lab_119.customers(customer_id)
);

INSERT INTO fk_lab_119.optional_orders
    (optional_order_id, customer_id)
VALUES
    (1, NULL),
    (2, 1);
~~~

Dòng `customer_id = NULL` được phép vì quan hệ là tùy chọn. Dòng `customer_id = 1` được phép vì khách 1 tồn tại. Nhưng `customer_id = 999` sẽ bị từ chối.

Nếu nghiệp vụ yêu cầu **mọi đơn phải có khách**, đặt `customer_id BIGINT NOT NULL` như bảng `orders`. Chính `NOT NULL` chặn việc bỏ trống; `FOREIGN KEY` chặn giá trị **không có cha**.

### 11.2. MATCH SIMPLE: mặc định của khóa ngoại nhiều cột

Giả sử khóa ngoại tham chiếu tới một khóa ghép `(tenant_id, product_code)`. Với `MATCH SIMPLE`, nếu **ít nhất một thành phần FK là NULL**, hàng đó thường không phải thỏa điều kiện tồn tại của cả cặp.

Điều này có thể là chủ đích nếu quan hệ tùy chọn, nhưng cũng dễ tạo dữ liệu “nửa có tenant, nửa thiếu product” khi nghiệp vụ không cho phép.

### 11.3. MATCH FULL: hoặc cả cặp NULL, hoặc cả cặp hợp lệ

Tạo bảng cha có khóa tổng hợp:

~~~sql
CREATE TABLE fk_lab_119.tenant_products (
    tenant_id BIGINT NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    CONSTRAINT tenant_products_pk
        PRIMARY KEY (tenant_id, product_code)
);

INSERT INTO fk_lab_119.tenant_products
    (tenant_id, product_code, product_name)
VALUES
    (1, 'A', 'Sản phẩm A của tenant 1'),
    (2, 'A', 'Sản phẩm A của tenant 2');
~~~

Bảng con với hai cột nullable:

~~~sql
CREATE TABLE fk_lab_119.optional_tenant_items (
    item_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NULL,
    product_code TEXT NULL,
    CONSTRAINT fk_optional_tenant_product
        FOREIGN KEY (tenant_id, product_code)
        REFERENCES fk_lab_119.tenant_products
            (tenant_id, product_code)
        MATCH FULL
);
~~~

Các tình huống:

| `tenant_id` | `product_code` | Với MATCH FULL | Lý do |
| ---: | --- | --- | --- |
| 1 | `A` | Hợp lệ | Cặp (1, A) tồn tại |
| 2 | `A` | Hợp lệ | Cặp (2, A) tồn tại |
| `NULL` | `NULL` | Hợp lệ | Toàn bộ khóa ngoại không được cung cấp |
| 1 | `NULL` | **Không hợp lệ** | Chỉ một phần cặp bị NULL |
| `NULL` | `A` | **Không hợp lệ** | Chỉ một phần cặp bị NULL |
| 1 | `X` | **Không hợp lệ** | Cặp (1, X) không tồn tại |

Kiểm tra:

~~~sql
INSERT INTO fk_lab_119.optional_tenant_items
    (item_id, tenant_id, product_code)
VALUES
    (1, 1, 'A'),
    (2, NULL, NULL);

-- Trên lab, chạy riêng để thấy lỗi:
-- INSERT INTO fk_lab_119.optional_tenant_items
--     (item_id, tenant_id, product_code)
-- VALUES (3, 1, NULL);
~~~

`MATCH PARTIAL` có xuất hiện trong cú pháp SQL tiêu chuẩn nhưng **không được PostgreSQL triển khai** như một chế độ FK thông thường. Trong PostgreSQL, lựa chọn thực tế cần quan tâm chủ yếu là **MATCH SIMPLE** mặc định và **MATCH FULL**.

### 11.4. Nếu tất cả thành phần bắt buộc, dùng NOT NULL

Với một sản phẩm luôn thuộc tenant nhất định:

~~~sql
CREATE TABLE fk_lab_119.tenant_order_items (
    tenant_id BIGINT NOT NULL,
    product_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    CONSTRAINT fk_tenant_item_product
        FOREIGN KEY (tenant_id, product_code)
        REFERENCES fk_lab_119.tenant_products
            (tenant_id, product_code)
);
~~~

Do cả hai thành phần đã `NOT NULL`, vấn đề “cặp nửa NULL” không còn xảy ra. Khóa ngoại tổng hợp đảm bảo **sản phẩm A được tìm đúng trong tenant tương ứng**, thay vì chỉ kiểm tra riêng `product_code` tồn tại ở tenant khác.

## 12. Khóa ngoại nhiều cột bảo vệ quan hệ theo cặp

Lấy ví dụ `tenant_products`:

~~~text
tenant_products
-----------------------------------------
tenant_id    product_code    product_name
1            A               Sản phẩm A / tenant 1
2            A               Sản phẩm A / tenant 2
~~~

Nếu tạo **hai FK riêng lẻ**:

~~~text
FOREIGN KEY (tenant_id)    -> một khóa tenant ở bảng khác
FOREIGN KEY (product_code) -> một mã sản phẩm chung
~~~

thì cả hai giá trị riêng lẻ có thể tồn tại nhưng **tổ hợp tenant–product lại không hợp lệ**. FK tổng hợp:

~~~sql
FOREIGN KEY (tenant_id, product_code)
REFERENCES fk_lab_119.tenant_products(tenant_id, product_code)
~~~

kiểm tra cặp như **một quan hệ**.

### 12.1. Cẩn trọng thứ tự cột

Giả sử khóa cha là `PRIMARY KEY (tenant_id, product_code)`. Cặp con phải được ánh xạ đúng từng cột:

~~~sql
FOREIGN KEY (tenant_id, product_code)
REFERENCES fk_lab_119.tenant_products(tenant_id, product_code)
~~~

Không tự đổi thứ tự con hoặc cha trong câu FK chỉ vì cả hai cột là text ở một schema khác. Công cụ migration cần so cả tên và **vị trí tương ứng** của từng thành phần.

### 12.2. Không được dùng khóa chính riêng lẻ thay cho điều kiện ghép

Trong hệ thống multi-tenant, có thể có `product_id` trùng nhau giữa tenant nếu ID chỉ duy nhất trong mỗi tenant. Khi đó chỉ dùng `FOREIGN KEY (product_id)` là không đủ. Khóa tham chiếu phải bao gồm `tenant_id` nếu đó là một phần danh tính nghiệp vụ, hoặc cần một global surrogate ID thực sự duy nhất để liên kết an toàn.

FK là một hàng rào quan trọng nhưng **không thay thế toàn bộ kiểm tra phân quyền theo tenant**. Ứng dụng vẫn cần xác thực user được phép thao tác tenant nào.

## 13. Thêm FOREIGN KEY vào bảng đã có dữ liệu: NOT VALID và VALIDATE

Trong production, nhiều bảng được tạo trước khi áp dụng ràng buộc đầy đủ hoặc có dữ liệu lịch sử được nhập từ hệ thống cũ. Thêm FK theo cách thông thường có thể phải **quét và xác thực toàn bộ dữ liệu hiện có**, gây chi phí và tác động khóa.

PostgreSQL hỗ trợ quy trình hai bước:

1. `ADD CONSTRAINT ... NOT VALID`: đăng ký ràng buộc nhưng **chưa quét để chứng minh tất cả hàng cũ đều hợp lệ**.
2. `VALIDATE CONSTRAINT`: sau khi dữ liệu cũ được sửa, PostgreSQL quét/kiểm tra để đánh dấu ràng buộc đã hợp lệ.

Điểm quan trọng: **`NOT VALID` không có nghĩa cho phép các bản ghi mới vi phạm**. Sau khi tạo ràng buộc, những thao tác ghi mới/việc sửa hàng liên quan vẫn chịu kiểm tra theo cơ chế của ràng buộc.

### 13.1. Ví dụ dữ liệu lịch sử có FK mồ côi

Tạo bảng import tạm để minh họa (không có FK ngay từ đầu):

~~~sql
CREATE TABLE fk_lab_119.import_lines (
    import_line_id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO fk_lab_119.import_lines
    (import_line_id, product_id, quantity)
VALUES
    (1, 10, 2),
    (2, 999, 1);  -- Dòng cũ sai: không có product 999.
~~~

Nếu thêm FK được kiểm tra toàn bộ:

~~~sql
-- Chỉ để minh họa câu có thể thất bại trên dữ liệu hiện tại:
-- ALTER TABLE fk_lab_119.import_lines
-- ADD CONSTRAINT fk_import_lines_product
-- FOREIGN KEY (product_id)
-- REFERENCES fk_lab_119.products(product_id);
~~~

vì dòng `product_id=999` không có cha.

### 13.2. Đăng ký khóa ngoại chưa validate

~~~sql
ALTER TABLE fk_lab_119.import_lines
ADD CONSTRAINT fk_import_lines_product
FOREIGN KEY (product_id)
REFERENCES fk_lab_119.products(product_id)
NOT VALID;
~~~

Trong PostgreSQL, constraint lúc này đã tồn tại nhưng **`convalidated = false`** trong catalog. Các dòng cũ chưa được quét xác nhận.

Không được kết luận rằng vì `ALTER TABLE ... NOT VALID` thành công nên tất cả dữ liệu đã đúng.

### 13.3. Tìm dòng mồ côi trong dữ liệu cũ

~~~sql
SELECT
    il.import_line_id,
    il.product_id
FROM fk_lab_119.import_lines AS il
LEFT JOIN fk_lab_119.products AS p
    ON p.product_id = il.product_id
WHERE p.product_id IS NULL
ORDER BY il.import_line_id;
~~~

Kỳ vọng tìm thấy dòng `import_line_id = 2`, `product_id = 999`.

Khi các cột FK cho phép `NULL`, truy vấn đối soát phải xét đúng ngữ nghĩa `MATCH SIMPLE`/`MATCH FULL` trước khi kết luận dòng thiếu cha. Ở ví dụ `product_id NOT NULL` nên truy vấn anti-join đơn giản là đủ.

### 13.4. Sửa dữ liệu, rồi VALIDATE

Trong lab ta đã biết dòng số 2 cần gắn với sản phẩm 10:

~~~sql
UPDATE fk_lab_119.import_lines
SET product_id = 10
WHERE import_line_id = 2;

ALTER TABLE fk_lab_119.import_lines
VALIDATE CONSTRAINT fk_import_lines_product;
~~~

Sau khi validate thành công, hệ thống xác nhận dữ liệu hiện có phù hợp với ràng buộc theo quy trình này.

Trên production, **đừng tự thay `999` thành một ID hợp lệ bất kỳ** chỉ để qua FK. Cần truy nguồn dữ liệu, sửa mapping hoặc đưa dòng lỗi vào vùng cách ly để được xử lý nghiệp vụ. Một FK đúng về kỹ thuật nhưng trỏ sang **sản phẩm sai** vẫn là dữ liệu nghiệp vụ sai.

### 13.5. Vì sao NOT VALID có lợi cho migration lớn?

Thêm FK theo dạng `NOT VALID` tránh bước quét toàn bộ bảng con ngay trong thao tác đăng ký ràng buộc; `VALIDATE CONSTRAINT` có thể được thực hiện sau với chiến lược khóa khác, thường ít cản trở cập nhật đồng thời hơn việc thêm FK và validate toàn bộ trong một thao tác.

Tuy nhiên:

- `ADD CONSTRAINT` vẫn cần lock thích hợp trên các bảng tham gia.
- `VALIDATE CONSTRAINT` vẫn cần I/O, CPU, lock và thời gian.
- Với bảng lớn cần thử trên staging, quan sát lock waits và chọn cửa sổ triển khai phù hợp.
- Nếu validate thất bại, ràng buộc vẫn ở trạng thái **not validated**, cần sửa dữ liệu rồi thử lại.

**NOT VALID không phải cách vô hiệu hóa FK vĩnh viễn.** Đó là công cụ migration để có thể chuyển từ dữ liệu cũ chưa sạch sang trạng thái toàn vẹn được kiểm chứng.

## 14. Index và hiệu năng của FOREIGN KEY

Ràng buộc FK cần tìm khóa cha và đôi khi phải tìm **tất cả dòng con đang tham chiếu** khi khóa cha được thay đổi/xóa. Chỉ mục ảnh hưởng lớn đến chi phí của các thao tác này.

### 14.1. Index phía cha

Khóa `PRIMARY KEY` hoặc `UNIQUE` ở phía cha đã có một index hỗ trợ sự duy nhất. Ví dụ `customers(customer_id)` có index phục vụ `PRIMARY KEY`.

PostgreSQL dùng cấu trúc đảm bảo tính duy nhất đó để xác nhận mục tiêu tham chiếu hợp lệ. Không cần tự tạo thêm một index B-tree giống hệt `customers(customer_id)` chỉ để FK hoạt động.

### 14.2. Index phía con không được tạo tự động chỉ vì FK

Khai báo:

~~~sql
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers(customer_id)
~~~

**không tự tạo index trên `orders(customer_id)`**. Đây là khác biệt quan trọng khi thiết kế hiệu năng.

Tại sao index cột con có thể có ích?

1. Truy vấn nghiệp vụ thường tìm đơn theo khách.
2. Khi xóa/cập nhật khóa khách, PostgreSQL cần kiểm tra có những đơn nào còn tham chiếu.
3. Nếu bảng con có hàng triệu dòng mà thiếu index phù hợp, việc kiểm tra có thể tốn nhiều I/O.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_id
ON fk_lab_119.orders(customer_id);
~~~

Chỉ tạo một lần trên lab. Nếu hệ thống đã có index với `customer_id` làm tiền tố hữu ích, chẳng hạn `(customer_id, ordered_at)`, có thể không cần index đơn cột mới; phải xét kế hoạch thực thi và các truy vấn khác.

### 14.3. Kiểm tra index cho cả hai FK của order_items

`order_items` có `PRIMARY KEY(order_id, product_id)`. B-tree index phục vụ PK bắt đầu bằng `order_id`, thường hỗ trợ tốt tra cứu các dòng theo `order_id`. Nhưng truy vấn chỉ lọc `product_id` hoặc việc kiểm tra có dòng con tham chiếu tới **một sản phẩm** có thể cần index riêng:

~~~sql
CREATE INDEX idx_order_items_product_id
ON fk_lab_119.order_items(product_id);
~~~

Không phải mọi FK đều đòi **bằng mọi giá** một index riêng: index tốn dung lượng, chi phí cập nhật và bộ nhớ đệm. Nguyên tắc là kiểm tra dữ liệu, tần suất `DELETE`/`UPDATE` ở cha, các truy vấn `JOIN` và kế hoạch thực thi thực tế.

### 14.4. FK và tình trạng chờ khóa

PostgreSQL phải bảo đảm một transaction không thể commit dòng con trỏ tới cha đã bị xóa hoặc đổi khóa bởi transaction đồng thời. Để thực hiện tính toàn vẹn, nó phối hợp khóa hàng/các kiểm tra tham chiếu nội bộ.

Điều này có thể dẫn đến:

- `INSERT` vào bảng con phải chờ một thay đổi khóa ở cha đang diễn ra.
- `DELETE` trên bảng cha phải chờ hoặc kiểm tra các dòng con.
- Các thao tác cập nhật/xóa nhiều dòng theo quan hệ phức tạp gây lock contention.
- Dùng nhiều bảng FK trong thứ tự khóa không nhất quán có thể góp phần tạo **deadlock**.

Không nên “chữa” hiện tượng chờ bằng cách tắt ràng buộc. Cần quan sát workload, giao dịch mở lâu, thiết kế index và thứ tự cập nhật trong application.

## 15. FOREIGN KEY trong transaction và đồng thời

Một câu kiểm tra thủ công:

~~~sql
SELECT EXISTS (
    SELECT 1
    FROM fk_lab_119.customers
    WHERE customer_id = 1
);
~~~

không thay thế được FK, vì sau câu `SELECT` có thể có transaction khác xóa hoặc thay đổi dòng cha trước khi chương trình chèn đơn.

### 15.1. Hai phiên cùng thao tác với một bản ghi cha

Giả sử:

~~~text
Session A                         Session B
------------------------------------------------------
BEGIN
INSERT orders(customer_id=3)
                                  BEGIN
                                  DELETE customers WHERE id=3
                                  (có thể phải chờ/đụng FK)
COMMIT hoặc ROLLBACK
                                  tiếp tục theo kết quả đã xác định
~~~

PostgreSQL dùng cơ chế khóa và kiểm tra phù hợp để không commit một trạng thái vi phạm FK. Kết quả thứ tự chờ/được phép phụ thuộc thời điểm và trạng thái transaction, không đơn giản là “SELECT thấy cha nên chắc chắn INSERT luôn hợp lệ”.

### 15.2. Ràng buộc không thay transaction nghiệp vụ

Giả sử tạo đơn gồm ba bước:

1. Tạo `orders`.
2. Tạo các `order_items`.
3. Trừ tồn kho.

FK bảo đảm dòng hàng tham chiếu đơn/sản phẩm hợp lệ, nhưng **không tự rollback việc trừ kho nếu ứng dụng tách ba bước thành những transaction độc lập**. Nghiệp vụ nhiều bước phải nằm trong một transaction thích hợp:

~~~sql
BEGIN;

-- Thêm đơn.
-- Thêm dòng chi tiết có FK hợp lệ.
-- Cập nhật tồn kho có điều kiện và kiểm tra số dòng.

COMMIT;
~~~

Nếu một bước bắt buộc thất bại, application phải rollback toàn bộ thay vì commit phần còn lại. Với `DEFERRABLE`, ứng dụng còn phải chuẩn bị xử lý lỗi tại thời điểm `COMMIT`.

### 15.3. Deadlock và retry

FK không loại trừ hoàn toàn deadlock. Nếu có nhiều transaction khóa cùng tập bảng/dòng theo thứ tự trái ngược, PostgreSQL có thể báo `SQLSTATE 40P01` (*deadlock_detected*). Khi đó cần rollback và, nếu nghiệp vụ an toàn để làm lại, **retry toàn bộ transaction** có giới hạn và backoff phù hợp.

Không xử lý mọi lỗi PostgreSQL bằng retry mù: lỗi `23503` thường là dữ liệu/quan hệ không hợp lệ, không phải deadlock.

## 16. Giới hạn phạm vi: cùng database, khác schema và quan hệ vòng

### 16.1. Có thể tham chiếu sang schema khác trong cùng database

~~~sql
FOREIGN KEY (customer_id)
REFERENCES fk_lab_119.customers(customer_id)
~~~

Nếu bảng con nằm trong `app` và cha nằm trong `reference` của **cùng database**, việc khai báo FK khác schema được PostgreSQL hỗ trợ khi có quyền phù hợp. Viết tiền tố schema rõ ràng giúp tránh phụ thuộc vào `search_path`.

Nhưng PostgreSQL **không cho khai báo FK SQL thông thường trực tiếp sang một database khác** trong cùng instance. Khi dữ liệu nằm ở hai database hoặc hai dịch vụ độc lập, cần quy trình toàn vẹn ở tầng tích hợp/ứng dụng; FDW không tự biến quan hệ chéo database thành FK native được kiểm tra như một bảng local.

### 16.2. Khóa ngoại tự tham chiếu

Ví dụ cây danh mục:

~~~sql
CREATE TABLE fk_lab_119.categories (
    category_id BIGINT PRIMARY KEY,
    parent_category_id BIGINT NULL,
    category_name TEXT NOT NULL,

    CONSTRAINT fk_category_parent
        FOREIGN KEY (parent_category_id)
        REFERENCES fk_lab_119.categories(category_id)
        ON DELETE RESTRICT
);
~~~

Một danh mục gốc có `parent_category_id = NULL`; danh mục con trỏ tới ID của một danh mục tồn tại.

**FK tự tham chiếu không tự cấm chu trình**, ví dụ A trỏ B và B trỏ A có thể vẫn thỏa điều kiện “cha tồn tại” nếu được tạo/cập nhật theo thứ tự hợp lệ. Nếu nghiệp vụ yêu cầu cây không chu trình, cần thêm kiểm tra quan hệ tổ tiên/phát hiện vòng với transaction, truy vấn đệ quy hoặc cơ chế phù hợp khác.

### 16.3. Quan hệ vòng giữa hai bảng

Hai bảng có thể cùng tham chiếu nhau, ví dụ department trỏ lead employee và employee trỏ department. Muốn seed dữ liệu, có thể:

- Tạo bảng và thêm một FK sau qua `ALTER TABLE`.
- Cho phép một phía tạm `NULL` nếu mô hình cho phép.
- Dùng constraint `DEFERRABLE` để nạp các dòng trong cùng transaction rồi commit khi đã đủ quan hệ.

Không được dùng tính năng defer để commit dữ liệu thiếu cha; nó chỉ giúp thay đổi thứ tự tạo/sửa trong quá trình giao dịch.

## 17. DELETE khác TRUNCATE: đừng kỳ vọng ON DELETE CASCADE áp dụng giống nhau

Trong PostgreSQL, `DELETE FROM parent WHERE ...` thực hiện xóa dòng và kích hoạt các hành động khóa ngoại tương ứng như `ON DELETE CASCADE`.

Ngược lại, `TRUNCATE` là thao tác dọn bảng theo cơ chế khác, không phải một tập hợp các lệnh `DELETE` trên từng dòng. Khi bảng có FK từ bảng khác, PostgreSQL thường không cho `TRUNCATE` chỉ bảng cha nếu bảng con tham chiếu không cùng được đưa vào tập bảng truncate, trừ khi sử dụng `CASCADE` ở chính lệnh truncate.

~~~sql
-- KHÔNG CHẠY: ví dụ nguy hiểm có thể xóa toàn bộ dữ liệu lab.
-- TRUNCATE TABLE fk_lab_119.orders CASCADE;
~~~

`TRUNCATE ... CASCADE` có thể **xóa dữ liệu của các bảng phụ thuộc liên quan**, không đơn thuần áp dụng từng hành động `ON DELETE` như `DELETE`. Vì vậy, không nên dùng trên production để “tiết kiệm thời gian” khi chưa kiểm tra đầy đủ phạm vi bảng sẽ bị ảnh hưởng.

### 17.1. DROP TABLE ... CASCADE cũng không phải ON DELETE CASCADE

`DROP TABLE ... CASCADE` xử lý **phụ thuộc object ở mức schema**. Ví dụ khi drop bảng cha, PostgreSQL có thể loại bỏ FK constraint phụ thuộc trong bảng con, nhưng không nhất thiết drop chính bảng con đó. Đây không phải cùng ý nghĩa với xóa các dòng con của `ON DELETE CASCADE`.

**Ba loại CASCADE cần phân biệt:**

| Cú pháp | Phạm vi chính |
| --- | --- |
| `ON DELETE CASCADE` | Dòng dữ liệu con của một quan hệ FK khi xóa dòng cha |
| `TRUNCATE ... CASCADE` | Các bảng có quan hệ tham chiếu cần được truncate cùng |
| `DROP ... CASCADE` | Các object phụ thuộc trong hệ thống catalog |

Tránh dùng `CASCADE` theo phản xạ mà chưa xác định loại thao tác và tác động.

## 18. Partitioning, inheritance và những trường hợp nâng cao

PostgreSQL hiện đại hỗ trợ foreign key liên quan tới **partitioned tables** theo khả năng và giới hạn của từng phiên bản. Khi triển khai, cần xem kỹ:

- FK trỏ tới bảng phân vùng hay FK từ bảng phân vùng.
- Ràng buộc unique/primary key của bảng partitioned có đủ điều kiện theo partition key không.
- Cách thêm/đính kèm partition và thời điểm kiểm tra ràng buộc.
- Chi phí check/xóa/cascade qua nhiều partition.

Trong khi đó, **table inheritance truyền thống** không tự cho mọi ràng buộc FK trên bảng cha được áp dụng theo cùng ý nghĩa tới mọi bảng con kế thừa. Không nhầm declarative partitioning với inheritance khi thiết kế toàn vẹn tham chiếu.

Nếu dự án dùng partitioning, hãy chạy thử DDL trên **đúng major version** và đúng cấu trúc partition; không lấy một ví dụ FK trên bảng thường làm bằng chứng rằng toàn bộ topology partition đều hoạt động giống hệt.

## 19. Xem FOREIGN KEY đang có trong schema

### 19.1. Dùng psql

Trong `psql`:

~~~text
\d fk_lab_119.orders
\d fk_lab_119.order_items
\d+ fk_lab_119.import_lines
~~~

`\d` là **meta-command của psql**, không phải SQL có thể gửi qua JDBC nguyên xi. Nó giúp quan sát ràng buộc, index và các mối quan hệ được PostgreSQL ghi nhận.

### 19.2. Dùng information_schema

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    rc.update_rule,
    rc.delete_rule,
    rc.match_option
FROM information_schema.table_constraints AS tc
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_catalog = tc.constraint_catalog
   AND rc.constraint_schema = tc.constraint_schema
   AND rc.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'fk_lab_119'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name, tc.constraint_name;
~~~

`information_schema` là cách tra cứu metadata tương đối gần chuẩn SQL, nhưng kết quả có thể bị lọc theo quyền và không cung cấp mọi chi tiết đặc thù PostgreSQL.

### 19.3. Dùng pg_catalog để xem đầy đủ định nghĩa

~~~sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    con.conname AS constraint_name,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    con.condeferrable AS is_deferrable,
    con.condeferred AS initially_deferred,
    con.convalidated AS is_validated,
    pg_catalog.pg_get_constraintdef(con.oid, TRUE)
        AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
WHERE con.contype = 'f'
  AND child_ns.nspname = 'fk_lab_119'
ORDER BY child.relname, con.conname;
~~~

Các trường đáng chú ý:

- `conrelid`: bảng con.
- `confrelid`: bảng cha.
- `contype = 'f'`: foreign key.
- `condeferrable`: constraint cho phép trì hoãn hay không.
- `condeferred`: ban đầu có deferred hay không.
- `convalidated`: dữ liệu cũ đã được validate theo quy trình ràng buộc hay chưa.
- `pg_get_constraintdef`: dựng lại định nghĩa của constraint để đọc.

### 19.4. Kiểm tra FK có đang NOT VALID

~~~sql
SELECT
    child.relname AS table_name,
    con.conname,
    con.convalidated,
    pg_get_constraintdef(con.oid, TRUE) AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = child.relnamespace
WHERE con.contype = 'f'
  AND ns.nspname = 'fk_lab_119'
  AND NOT con.convalidated
ORDER BY table_name, con.conname;
~~~

Nếu đã chạy `VALIDATE CONSTRAINT` trong mục 13 thành công, query này thường **không còn trả dòng `fk_import_lines_product`**. Trên hệ thống lớn, danh sách FK chưa validate là một tín hiệu cần đưa vào quy trình theo dõi migration.

### 19.5. Tìm cột ở cả hai đầu FOREIGN KEY tổng hợp

PostgreSQL ghi số cột tham gia trong mảng `pg_constraint.conkey` và `confkey`. Truy vấn sau ghép từng vị trí để tránh mất thứ tự:

~~~sql
SELECT
    child.relname AS child_table,
    con.conname AS constraint_name,
    pos.n AS pair_position,
    child_col.attname AS child_column,
    parent.relname AS parent_table,
    parent_col.attname AS parent_column
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS child
    ON child.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = child.relnamespace
JOIN pg_catalog.pg_class AS parent
    ON parent.oid = con.confrelid
CROSS JOIN LATERAL
    generate_subscripts(con.conkey, 1) AS pos(n)
JOIN pg_catalog.pg_attribute AS child_col
    ON child_col.attrelid = con.conrelid
   AND child_col.attnum = con.conkey[pos.n]
JOIN pg_catalog.pg_attribute AS parent_col
    ON parent_col.attrelid = con.confrelid
   AND parent_col.attnum = con.confkey[pos.n]
WHERE con.contype = 'f'
  AND ns.nspname = 'fk_lab_119'
ORDER BY child.relname, con.conname, pos.n;
~~~

Đây là một cách đáng tin cậy để dựng sơ đồ quan hệ khi có khóa ngoại nhiều cột. `OID` là định danh nội bộ của catalog trong database hiện tại, không phải khóa nghiệp vụ ổn định để lưu giữa dev/staging/production.

## 20. Phát hiện và xử lý dữ liệu tham chiếu mồ côi

Khi FK đã được kiểm tra hợp lệ và không bị vô hiệu bằng cơ chế đặc biệt, database sẽ ngăn những thao tác mới làm phát sinh tham chiếu không hợp lệ. Tuy nhiên, dữ liệu cũ hoặc dữ liệu nhập qua những quy trình đặc biệt có thể vẫn cần đối soát.

### 20.1. Anti-join

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM fk_lab_119.orders AS o
LEFT JOIN fk_lab_119.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
~~~

Với dữ liệu mẫu, kết quả phải là **0 dòng**.

### 20.2. NOT EXISTS

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM fk_lab_119.orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM fk_lab_119.customers AS c
    WHERE c.customer_id = o.customer_id
);
~~~

Với cột FK `NOT NULL`, truy vấn này phù hợp tìm các dòng mồ côi. Nếu FK nullable và `NULL` nghĩa là “không có quan hệ”, cần loại trừ các dòng có `NULL` khi mục tiêu chỉ tìm tham chiếu **sai**, không phải quan hệ **chưa được gán**.

Ví dụ:

~~~sql
-- Với foreign key nullable:
-- WHERE child.parent_id IS NOT NULL
--   AND NOT EXISTS (
--       SELECT 1 FROM parent
--       WHERE parent.id = child.parent_id
--   )
~~~

### 20.3. Không tự sửa dữ liệu sai bằng ID ngẫu nhiên

Nếu thấy `customer_id = 999` không tồn tại, có nhiều nguyên nhân:

- Dữ liệu cha chưa được import.
- Mapping ID giữa hệ thống cũ và mới không đúng.
- Bản ghi cha bị xóa trước khi có FK.
- Dữ liệu được đưa vào bằng công cụ/quy trình đã bỏ qua kiểm tra.

Giải pháp là tìm nguyên nhân, đối chiếu nguồn và xác định bản ghi cha thực tế. Gán mọi dòng sang “khách hàng mặc định” chỉ để qua constraint có thể làm mất tính đúng đắn nghiệp vụ hoặc che dấu lỗi tích hợp.

## 21. Không vô hiệu FOREIGN KEY để “nhập nhanh” một cách tùy tiện

Trong PostgreSQL, ràng buộc FK được thực thi thông qua các cơ chế trigger nội bộ. Một số cách quản trị đặc biệt có thể làm thay đổi hành vi trigger hoặc replication. **Không dùng chúng như một nút tắt kiểm tra toàn vẹn dữ liệu** trong quy trình ứng dụng thường ngày.

Nếu cần import quy mô lớn, ưu tiên:

1. Tạo bảng đích với PK/FK đúng thiết kế khi có thể.
2. Nạp bảng cha trước bảng con.
3. Dùng staging tables để làm sạch và ánh xạ khóa.
4. Dùng `NOT VALID`/`VALIDATE CONSTRAINT` theo quy trình migration khi phù hợp.
5. Tách batch, đo khóa và I/O, và ghi nhận số hàng lỗi.
6. Chạy đối soát và hoàn tất validation trước khi coi dữ liệu production đáng tin cậy.

Một số cơ chế như thay đổi `session_replication_role` hoặc vô hiệu trigger có thể khiến kiểm tra FK không chạy như mặc định, đòi quyền cao và mang rủi ro để lại dữ liệu mồ côi. Không áp dụng chúng chỉ để “cho script chạy qua” hoặc để tránh lỗi `23503`.

## 22. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `INSERT` con báo `23503` | Giá trị FK không có cha | Xác minh mã/ID cha, thứ tự seed |
| `DELETE` cha báo `23503` | Còn bản ghi con, hành động RESTRICT/NO ACTION | Tìm bảng con theo FK và đếm các tham chiếu |
| `UPDATE` khóa cha báo `23503` | Có dòng con đang trỏ khóa cũ | Cân nhắc giữ surrogate ID ổn định; không sửa khóa tùy tiện |
| Thêm FK báo “no unique constraint matching” | Đích không có khóa unique phù hợp | Xem PK/UNIQUE/non-partial unique index của cha |
| Thêm FK cho bảng cũ thất bại | Có dữ liệu mồ côi | Anti-join, sửa mapping, cân nhắc NOT VALID rồi VALIDATE |
| `VALIDATE CONSTRAINT` thất bại | Dòng cũ còn vi phạm | Đối soát và sửa dữ liệu theo nghiệp vụ |
| FK nhiều cột cho kết quả khó hiểu | Sai thứ tự cột hoặc một phần NULL | Kiểm tra `MATCH`, `NOT NULL` và cặp con–cha |
| `SET NULL` khi xóa cha thất bại | Cột con `NOT NULL` hoặc ràng buộc khác | Xem DDL/constraint của con |
| `SET DEFAULT` khi xóa cha thất bại | Default không tham chiếu bản ghi cha hợp lệ | Kiểm tra bản ghi mặc định và miền giá trị |
| `CASCADE` xóa nhiều dòng bất ngờ | Chuỗi quan hệ phụ thuộc rộng | Xem DDL và thống kê số con trước khi DELETE |
| Thao tác xóa cha chậm | Thiếu index hữu ích ở con hoặc lock contention | `pg_stat_activity`, index, số lượng dòng con |
| `ALTER TABLE ADD FK` chờ lâu | Lock hoặc quét validate bảng lớn | Kiểm tra transaction lâu, thử NOT VALID và kế hoạch migration |
| `TRUNCATE` cha bị chặn | FK phụ thuộc dù ON DELETE đặt CASCADE | Phân biệt TRUNCATE với DELETE |
| `COMMIT` mới báo lỗi FK | Constraint được đặt DEFERRABLE DEFERRED | Kiểm tra dữ liệu cuối transaction, rollback và sửa quy trình |
| FK có nhưng dữ liệu vẫn sai nghiệp vụ | FK chỉ xác nhận tồn tại khóa | Bổ sung quy tắc nghiệp vụ, transaction và đối soát |

### 22.1. Quan sát constraint được lưu trong PostgreSQL

Khi gặp lỗi, nên lấy **tên constraint** từ thông báo/SQLSTATE và truy vấn `pg_constraint`, thay vì suy đoán từ tên bảng:

~~~sql
SELECT
    con.conname,
    pg_get_constraintdef(con.oid, TRUE) AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS rel
    ON rel.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'fk_lab_119'
  AND con.contype = 'f'
  AND con.conname = 'fk_orders_customer';
~~~

Tên constraint được đặt rõ ràng giúp lập trình viên và DBA xác định đúng chính sách `ON DELETE`/`ON UPDATE` đang chạy.

### 22.2. Điều tra khóa khi xóa/cập nhật

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY pid;
~~~

Một lệnh chờ lock không đồng nghĩa bản thân FK “bị lỗi”. Cần xem transaction nào đang giữ lock, kéo dài bao lâu và luồng nghiệp vụ nào tạo ra tình huống; không tự động terminate session production khi chưa xác nhận tác động.

## 23. Bài tập thực hành có hướng dẫn

### Bài 1 — Chèn đơn với khách hàng không tồn tại

Dựa vào schema lab, thử chèn `orders(customer_id=999)` và quan sát SQLSTATE.

~~~sql
BEGIN;
SAVEPOINT s1;
INSERT INTO fk_lab_119.orders
    (order_id, order_no, customer_id)
VALUES (901, 'SO-BAD-901', 999);
ROLLBACK TO SAVEPOINT s1;
ROLLBACK;
~~~

**Kỳ vọng:** `23503` do `fk_orders_customer`. Hãy giải thích vì sao kiểm tra FK ở database mạnh hơn một lần `SELECT` ở ứng dụng.

### Bài 2 — Xóa khách đã có đơn

Xóa thử khách `customer_id=1` trong transaction và giải thích vì sao `RESTRICT` từ chối. Sau đó kiểm tra khách `customer_id=3` chưa có đơn:

~~~sql
BEGIN;

DELETE FROM fk_lab_119.customers
WHERE customer_id = 3;
-- Có thể xóa trong transaction vì không có đơn tham chiếu.

ROLLBACK;
~~~

**Câu hỏi:** FK có bắt buộc mọi khách hàng phải có đơn không? Vì sao dòng khách 3 vẫn được phép tồn tại trước khi xóa?

### Bài 3 — Quan sát CASCADE và ROLLBACK

Trong transaction, đếm dòng `order_items` của đơn `100`, xóa đơn `100`, đếm lại, rồi rollback. Sau rollback xác nhận đơn và dòng hàng còn tồn tại. Giải thích tại sao CASCADE vẫn tham gia transaction.

### Bài 4 — Chọn đúng hành động khi xóa

Thiết kế chính sách cho các quan hệ:

1. Người dùng → phiên đăng nhập tạm.
2. Khách hàng → hóa đơn đã phát sinh.
3. Người quản lý → một tài liệu không bắt buộc có người quản lý.
4. Nhóm phân loại → hồ sơ được chuyển sang nhóm mặc định.

Hãy chọn `CASCADE`, `RESTRICT`/`NO ACTION`, `SET NULL` hoặc `SET DEFAULT`, rồi nêu điều kiện cột/giá trị mặc định cần có.

### Bài 5 — Quan hệ tenant nhiều cột

Với `tenant_products`:

~~~text
(1, A) tồn tại
(2, A) tồn tại
(1, X) không tồn tại
~~~

Thử dùng `tenant_order_items` tham chiếu `(1, X)`. Giải thích vì sao kiểm tra riêng `tenant_id` và `product_code` không đủ, và vì sao cần cặp FK tổng hợp.

### Bài 6 — So MATCH SIMPLE và MATCH FULL

Tạo một bảng con có `tenant_id`, `product_code` nullable và `MATCH SIMPLE`, sau đó so hành vi với `optional_tenant_items MATCH FULL` đã có. Kiểm tra hai giá trị:

~~~text
(NULL, NULL)
(1, NULL)
~~~

**Gợi ý:** `MATCH SIMPLE` bỏ qua kiểm tra cả cặp khi có một phần NULL; `MATCH FULL` yêu cầu tất cả NULL hoặc tất cả có giá trị khớp.

### Bài 7 — Trì hoãn FK đến COMMIT

Từ `deferred_parents` và `deferred_children`:

1. Dùng `SET CONSTRAINTS ... DEFERRED`.
2. Chèn con trước cha.
3. Chèn cha sau.
4. Commit và kiểm tra kết quả.
5. Lặp lại trên dữ liệu ID khác nhưng **không chèn cha**, quan sát lỗi ở commit.

**Gợi ý:** constraint không biến mất; tính hợp lệ phải được thỏa khi commit.

### Bài 8 — Thêm FK cho bảng cũ

Tạo `import_lines` với một product ID tồn tại và một ID không tồn tại. Thêm constraint `NOT VALID`, tìm orphan bằng `LEFT JOIN` hoặc `NOT EXISTS`, sửa dữ liệu sau khi xác định mapping đúng, rồi `VALIDATE CONSTRAINT`. Kiểm tra `pg_constraint.convalidated` trước và sau.

### Bài 9 — Quyết định index cho cột FK

Liệt kê index của `fk_lab_119.orders` và `fk_lab_119.order_items`:

~~~sql
SELECT
    schemaname, tablename, indexname, indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'fk_lab_119'
  AND tablename IN ('orders', 'order_items')
ORDER BY tablename, indexname;
~~~

Giải thích:

- Vì sao `orders(customer_id)` không tự có index chỉ vì FK?
- Vì sao `PRIMARY KEY(order_id, product_id)` thường hỗ trợ tìm theo `order_id` tốt hơn tìm chỉ theo `product_id`?
- Khi nào nên tạo thêm index phía con, và chi phí của index là gì?

### Bài 10 — Phân biệt DELETE, TRUNCATE, DROP

Với mô hình đơn và chi tiết, hãy mô tả:

1. `DELETE FROM orders WHERE order_id=100` với `ON DELETE CASCADE`.
2. `TRUNCATE orders CASCADE`.
3. `DROP TABLE orders CASCADE`.

**Không chạy hai lệnh cuối chỉ để thử trên dữ liệu có giá trị.** Giải thích phạm vi xóa **dòng**, truncate **bảng** và drop **đối tượng schema**.

### Bài 11 — Kiểm tra mọi FOREIGN KEY trong schema

Dùng `pg_catalog.pg_constraint` lọc `contype='f'` rồi hiển thị tên bảng con, bảng cha, định nghĩa và `convalidated`. Tìm ràng buộc nào được khai báo DEFERRABLE.

**Kỳ vọng:** constraint `fk_deferred_child_parent` có `condeferrable = true`; constraint import sau khi validate thành công có `convalidated = true`.

### Bài 12 — Thiết kế tích hợp dữ liệu an toàn

Một job nhận 100.000 dòng đơn hàng, trong đó có 200 dòng tham chiếu sản phẩm chưa tồn tại. Hãy đề xuất quy trình:

1. Nạp dữ liệu thô vào staging.
2. Đối chiếu mã sản phẩm với bảng cha.
3. Chia dòng hợp lệ và dòng cần xử lý.
4. Nạp cha nếu có dữ liệu hợp lệ được cấp từ nguồn đáng tin cậy.
5. Chèn các dòng con hợp lệ trong transaction/batch có giới hạn.
6. Đối soát số dòng và trạng thái constraint.

Giải thích vì sao không nên tắt FK hoặc tự gán tất cả ID lỗi thành một sản phẩm bất kỳ.

## 24. Bảng ghi nhớ khi thiết kế khóa ngoại

| Câu hỏi trước khi tạo FK | Quyết định cần rõ |
| --- | --- |
| Đây có đúng là quan hệ “con phải trỏ tới cha tồn tại”? | FK phù hợp nếu database có thể thực thi quan hệ đó |
| Khóa cha có unique/primary phù hợp không? | Đích tham chiếu phải có tính duy nhất đủ điều kiện |
| Cột con có cho phép không có cha? | `NOT NULL` hay nullable theo nghiệp vụ |
| FK có nhiều thành phần? | `MATCH SIMPLE`/`MATCH FULL` và thứ tự cột |
| Bản ghi cha có thể bị xóa vật lý? | Chọn `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL` hoặc `SET DEFAULT` |
| Có cần đổi giá trị khóa cha không? | Quyết định `ON UPDATE`, ưu tiên ID ổn định khi có thể |
| Có cần trạng thái tạm chưa hợp lệ trong transaction? | Cân nhắc `DEFERRABLE` có chủ đích |
| Bảng đã có dữ liệu lớn? | Kiểm tra orphan, `NOT VALID`/`VALIDATE` và kế hoạch lock |
| Có index hỗ trợ FK ở con chưa? | Xem truy vấn JOIN, xóa/sửa cha và PK/index hiện có |
| Có hệ thống ngoài database phụ thuộc dữ liệu? | FK không thay cơ chế tích hợp, event và phân quyền |
| Có yêu cầu giữ lịch sử? | Không dùng CASCADE tùy tiện với dữ liệu kế toán/giao dịch |
| Có bằng chứng ràng buộc đã validate? | Tra `pg_constraint.convalidated` và migration history |

## 25. Tài liệu PostgreSQL chính thức

Khi làm việc với các phiên bản PostgreSQL khác nhau, nên kiểm tra cú pháp và giới hạn theo **đúng major version**:

- [PostgreSQL — Constraints / Foreign Keys](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK): khai báo FK, hành động tham chiếu, null semantics và khóa tổng hợp.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): thêm/xóa/validate constraint và những cân nhắc khóa.
- [PostgreSQL — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): trì hoãn kiểm tra các ràng buộc được phép.
- [PostgreSQL — pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html): metadata FK, `conkey`, `confkey`, `convalidated` và `condeferrable`.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): tương tác giữa transaction, khóa và thao tác dữ liệu.

Các URL `/docs/current/` trỏ tới tài liệu của bản ổn định hiện hành. Nếu đang dùng một major version cụ thể, thay `current` bằng số major phù hợp để tra đúng hành vi của bản đó, đặc biệt với khả năng partitioning và các tính năng FK mở rộng.

## 26. Tổng kết

**`FOREIGN KEY` là ràng buộc giữ cho quan hệ giữa bảng con và bảng cha có ý nghĩa:** một giá trị hoặc tổ hợp giá trị ở con phải trỏ tới khóa hợp lệ ở cha theo quy tắc `NULL` đã chọn. PostgreSQL kiểm tra nó không chỉ khi chèn con mà cả khi cập nhật khóa con, xóa cha hoặc đổi khóa cha. Những hành động `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL` và `SET DEFAULT` phải được chọn theo vòng đời và nhu cầu lưu lịch sử của thực thể.

Với quan hệ phức tạp, cần hiểu **khóa ngoại tổng hợp**, `MATCH SIMPLE` so với `MATCH FULL` và **`DEFERRABLE`** để điều chỉnh thời điểm kiểm tra trong transaction mà không làm mất điều kiện toàn vẹn tại commit. Với hệ thống cũ có dữ liệu lớn, quy trình **`NOT VALID` → làm sạch dữ liệu → `VALIDATE CONSTRAINT`** giúp chuyển đổi có kiểm soát. Chỉ mục ở bảng con cần được cân nhắc vì PostgreSQL **không tự tạo index chỉ vì cột đó là FK**.

Khóa ngoại là lớp bảo vệ quan trọng ở tầng database, nhưng không thay thế transaction nghiệp vụ, phân quyền, đối soát dữ liệu hoặc chính sách xóa an toàn. Khi kết hợp đúng các thành phần này, PostgreSQL có thể giữ quan hệ tham chiếu nhất quán ngay cả khi nhiều ứng dụng và nhiều transaction cùng ghi dữ liệu.
