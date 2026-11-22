# Phụ thuộc đối tượng, RESTRICT và CASCADE trong PostgreSQL

Khi thiết kế cơ sở dữ liệu quan hệ, một bảng thường không tồn tại độc lập. Bảng đơn hàng có thể chứa khóa ngoại tham chiếu bảng khách hàng; một view đọc dữ liệu từ cả hai bảng; một view báo cáo khác lại đọc từ view đầu tiên; chỉ mục, ràng buộc và sequence còn có những quan hệ gắn với bảng hoặc cột.

Vì thế, câu lệnh tưởng đơn giản như:

~~~sql
DROP TABLE customers;
~~~

có thể bị PostgreSQL từ chối với thông báo rằng những đối tượng khác vẫn phụ thuộc vào bảng. Hệ quản trị cần ngăn một thao tác DDL vô tình khiến những đối tượng được giữ lại trở nên không hợp lệ.

PostgreSQL cho phép kiểm soát việc xóa đối tượng thông qua hai chế độ quan trọng:

- **`RESTRICT`:** không cho xóa nếu còn phụ thuộc cần xử lý; yêu cầu người quản trị chủ động giải quyết các đối tượng liên quan.
- **`CASCADE`:** đồng ý xóa tiếp những đối tượng phụ thuộc theo cơ chế PostgreSQL, có thể vượt ra ngoài phạm vi nhìn thấy ngay trong câu lệnh.

Bài học giải thích mô hình phụ thuộc đối tượng (*object dependency*), phân biệt các kiểu phụ thuộc, thử nghiệm `DROP ... RESTRICT` và `DROP ... CASCADE` với bảng, khóa ngoại, view, cột và schema, đồng thời hướng dẫn kiểm tra bằng catalog hệ thống và triển khai thay đổi DDL an toàn.

## 1. Phụ thuộc đối tượng là gì?

Một đối tượng **A phụ thuộc vào B** khi định nghĩa hoặc tính toàn vẹn của A yêu cầu B tồn tại. Khi B bị xóa hoặc thay đổi không tương thích, A có thể không còn hợp lệ.

Ví dụ:

~~~text
      dep_lab.customers
           │
           ├──────────────────┐
           │                  │
           ▼                  ▼
  FK fk_orders_customer   dep_lab.v_order_summary
      (thuộc orders)          ▲
           ▲                  │
           │                  │
      dep_lab.orders ─────────┘
                                  │
                                  ▼
                         dep_lab.v_paid_orders
~~~

Để đọc sơ đồ chính xác:

1. Ràng buộc khóa ngoại `fk_orders_customer` thuộc bảng `orders` và tham chiếu khóa chính ở `customers`.
2. `v_order_summary` là view sử dụng cả bảng `customers` lẫn `orders`.
3. `v_paid_orders` là view tiếp tục đọc từ `v_order_summary`, nên phụ thuộc gián tiếp vào những đối tượng phía dưới.
4. Nếu có view nằm trong schema khác nhưng đọc `customers`, quan hệ phụ thuộc vẫn tồn tại dù hai đối tượng nằm ở hai schema khác nhau.

PostgreSQL lưu metadata các mối quan hệ này trong catalog hệ thống. Hệ quản trị dùng chúng để quyết định nên chặn thao tác, xóa kèm đối tượng nào hoặc thực hiện việc dọn dẹp tự động.

### Phụ thuộc không chỉ là khóa ngoại

| Đối tượng | Ví dụ quan hệ phụ thuộc |
| --- | --- |
| **Foreign key** | Ràng buộc trên `orders` cần khóa được tham chiếu ở `customers` |
| **View** | `v_order_summary` đọc cột của `orders` và `customers` |
| **View lồng nhau** | `v_paid_orders` đọc dữ liệu từ `v_order_summary` |
| **Index** | Chỉ mục thuộc bảng và các cột được lập chỉ mục |
| **Constraint** | `CHECK`, `UNIQUE`, `PRIMARY KEY` gắn với bảng/cột |
| **Identity/owned sequence** | Sequence đi cùng cột có cơ chế ownership/phụ thuộc |
| **Materialized view** | Định nghĩa phụ thuộc vào các quan hệ nguồn |
| **Schema** | Các bảng, view, sequence, hàm... thuộc schema |
| **Function/type** | Một số chữ ký hàm, kiểu trả về hoặc biểu thức SQL phụ thuộc vào type, function, operator khác |

**Không phải mọi liên kết về mặt nghiệp vụ đều được PostgreSQL nhận diện tự động.** Ví dụ, một ứng dụng Java chứa chuỗi SQL `SELECT * FROM customers` không trở thành một đối tượng trong catalog `pg_depend`. Một số tham chiếu được tạo qua dynamic SQL hoặc nội dung hàm ở dạng chuỗi cũng có thể không được theo dõi giống định nghĩa view. Vì vậy, kiểm tra dependency trong database là cần thiết nhưng **chưa đủ** để bảo đảm ứng dụng không bị ảnh hưởng.

## 2. RESTRICT và CASCADE: hai cách xử lý quan hệ phụ thuộc

Với nhiều lệnh `DROP`, PostgreSQL hỗ trợ:

~~~sql
DROP TABLE ten_bang RESTRICT;

DROP TABLE ten_bang CASCADE;
~~~

### RESTRICT

`RESTRICT` yêu cầu PostgreSQL **từ chối thao tác** nếu vẫn có đối tượng phụ thuộc mà hệ quản trị không thể tự dọn như thành phần thuộc sở hữu nội bộ của đối tượng bị xóa.

Ví dụ, muốn xóa bảng khách hàng nhưng bảng đơn hàng có khóa ngoại tham chiếu tới nó, hoặc còn một view dùng bảng này, PostgreSQL sẽ báo lỗi phụ thuộc. Người quản trị phải quyết định xóa hoặc thay đổi những đối tượng liên quan trước.

### CASCADE

`CASCADE` cho phép PostgreSQL **xóa thêm các đối tượng phụ thuộc cần thiết**. Một thao tác có thể tạo thành chuỗi:

~~~text
DROP TABLE customers CASCADE
               │
               ├── Bỏ khóa ngoại của orders tham chiếu customers
               │
               ├── Bỏ view v_order_summary
               │          │
               │          └── Bỏ view v_paid_orders
               │
               └── Bỏ những đối tượng phụ thuộc khác nếu có
~~~

**`CASCADE` không có nghĩa PostgreSQL sẽ xóa mọi bảng từng có quan hệ với bảng đang xóa.** Ví dụ `DROP TABLE customers CASCADE` có thể bỏ **ràng buộc khóa ngoại** ở bảng `orders` mà vẫn giữ **bảng `orders` và dữ liệu đơn hàng**. Tuy nhiên, view phụ thuộc vào `customers` có thể bị xóa hoàn toàn.

### RESTRICT là mặc định của DROP trong nhiều trường hợp

~~~sql
DROP TABLE dep_lab.customers;
~~~

về mặt chính sách phụ thuộc tương đương cách dùng `RESTRICT` cho lệnh `DROP TABLE`. Viết tường minh `RESTRICT` giúp người đọc thấy rõ ý đồ thận trọng.

| Tiêu chí | `RESTRICT` | `CASCADE` |
| --- | --- | --- |
| Khi tồn tại phụ thuộc bình thường | Chặn thao tác và báo lỗi | Cho phép xóa kèm những đối tượng phụ thuộc |
| Mức kiểm soát thủ công | Cao | Phải đặc biệt kiểm tra tác động |
| Khả năng xóa dây chuyền | Không tự thực hiện chuỗi xóa phụ thuộc bình thường | Có thể đi qua nhiều cấp view/constraint |
| Phạm vi schema | Kiểm tra cả phụ thuộc ngoài schema | Có thể xóa cả đối tượng ở schema khác |
| Khi nên cân nhắc | Thay đổi có kiểm soát, migration production | Dọn dẹp lab, hoặc thay đổi đã kiểm tra toàn bộ dependency |

`RESTRICT` và `CASCADE` không phải “an toàn tuyệt đối” và “nguy hiểm tuyệt đối”; chúng là lựa chọn **chính sách xử lý dependency**. Việc chọn đúng phụ thuộc mục tiêu thay đổi, phạm vi kiểm soát và phương án khôi phục.

## 3. Tạo dữ liệu mẫu để quan sát dependency

Các thí nghiệm sau dành cho **PostgreSQL lab** với quyền tạo schema, bảng và view. Không thực hiện trên database chứa dữ liệu thật.

Chúng ta tạo hai schema để minh họa việc phụ thuộc có thể vượt qua ranh giới schema:

~~~sql
CREATE SCHEMA dep_lab;
CREATE SCHEMA dep_reports;
~~~

### 3.1. Tạo bảng khách hàng và đơn hàng

~~~sql
CREATE TABLE dep_lab.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL UNIQUE
);

CREATE TABLE dep_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES dep_lab.customers (customer_id)
);

CREATE INDEX idx_orders_customer
    ON dep_lab.orders (customer_id);
~~~

Điểm cần chú ý:

- `customers.customer_id` là khóa chính.
- `orders.customer_id` chứa khóa ngoại sang `customers.customer_id`.
- `idx_orders_customer` là chỉ mục phụ trợ phục vụ truy vấn theo khách hàng; không phải điều kiện bắt buộc để PostgreSQL cho phép tạo foreign key.
- Hai cột `GENERATED ALWAYS AS IDENTITY` có sequence gắn với cột theo cơ chế PostgreSQL.
- Ràng buộc `CHECK (amount >= 0)` và `PRIMARY KEY` cũng là các đối tượng schema liên quan tới bảng.

Thêm vài dòng:

~~~sql
INSERT INTO dep_lab.customers (customer_name)
VALUES ('An'), ('Binh'), ('Chi');

INSERT INTO dep_lab.orders (customer_id, status, amount)
VALUES
    (1, 'paid',    120000.00),
    (1, 'pending',  80000.00),
    (2, 'paid',    150000.00);
~~~

Đoạn `INSERT` giả định các identity ID lần lượt bắt đầu từ 1 trên database lab mới. Nếu bảng đã tồn tại hoặc sequence đã chạy trước đó, hãy lấy ID khách hàng thực tế thay vì dựa vào thứ tự mẫu.

### 3.2. Tạo view phụ thuộc vào bảng

~~~sql
CREATE VIEW dep_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.amount
FROM dep_lab.orders AS o
JOIN dep_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

View này không lưu bản sao các hàng như một bảng thông thường. Nó có **định nghĩa truy vấn**, tham chiếu cả `orders` và `customers`.

Tạo view phụ thuộc vào view trước:

~~~sql
CREATE VIEW dep_lab.v_paid_orders AS
SELECT
    order_id,
    customer_name,
    amount
FROM dep_lab.v_order_summary
WHERE status = 'paid';
~~~

Quan hệ phụ thuộc tạo thành:

~~~text
orders + customers
         │
         ▼
v_order_summary
         │
         ▼
v_paid_orders
~~~

### 3.3. Tạo view báo cáo ở schema khác

~~~sql
CREATE VIEW dep_reports.v_customer_totals AS
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.amount), 0) AS total_amount
FROM dep_lab.customers AS c
LEFT JOIN dep_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

Mặc dù view thuộc schema `dep_reports`, nó vẫn phụ thuộc vào các đối tượng trong `dep_lab`.

Kiểm tra dữ liệu mẫu:

~~~sql
SELECT * FROM dep_lab.v_order_summary ORDER BY order_id;
SELECT * FROM dep_lab.v_paid_orders ORDER BY order_id;
SELECT * FROM dep_reports.v_customer_totals ORDER BY customer_id;
~~~

Trong những phần sau, chúng ta sẽ dùng `BEGIN` và `ROLLBACK` để thử thao tác xóa mà **không giữ lại thay đổi phá hủy** sau khi kết thúc thí nghiệm.

## 4. Thử DROP TABLE ... RESTRICT

Giả sử muốn xóa `customers`:

~~~sql
BEGIN;

DROP TABLE dep_lab.customers RESTRICT;

-- Lệnh DROP dự kiến thất bại vì còn dependency.
ROLLBACK;
~~~

PostgreSQL sẽ báo lỗi phụ thuộc, thường có dạng ý nghĩa:

~~~text
ERROR: cannot drop table dep_lab.customers because other objects depend on it
DETAIL: constraint fk_orders_customer on table dep_lab.orders depends on table dep_lab.customers
DETAIL: view dep_lab.v_order_summary depends on table dep_lab.customers
...
HINT: Use DROP ... CASCADE to drop the dependent objects too.
~~~

Thông báo trên là **minh họa ý nghĩa**, không cam kết thứ tự và toàn bộ dòng lỗi giống nhau ở mọi phiên bản.

**Điểm quan trọng khi dùng psql:** trong transaction PostgreSQL, một câu lệnh lỗi thường khiến transaction chuyển sang trạng thái *aborted*. Sau lỗi, hãy chạy `ROLLBACK` rồi mới thử các câu lệnh khác. Nếu công cụ đang bật chế độ dừng script ngay khi lỗi, bạn có thể cần thực hiện rollback thủ công trong kết nối vẫn mở.

Vì `RESTRICT` chặn thao tác, bảng `customers` vẫn tồn tại. Các bảng `orders`, các view và dữ liệu cũng được giữ nguyên.

### RESTRICT giúp phát hiện những nơi đang phụ thuộc

Đây là một lợi ích vận hành của `RESTRICT`: PostgreSQL có thể cho biết **một số đối tượng chặn việc xóa**. Tuy nhiên, không nên dùng lỗi như phương pháp duy nhất để lập danh sách toàn bộ tác động, đặc biệt với hệ thống production. Kiểm tra catalog và định nghĩa schema trước khi triển khai vẫn là bước cần thiết.

## 5. Thử DROP TABLE ... CASCADE

Sau khi có sơ đồ phụ thuộc, thử cùng thao tác nhưng cho phép xóa theo chuỗi:

~~~sql
BEGIN;

DROP TABLE dep_lab.customers CASCADE;

SELECT to_regclass('dep_lab.customers') AS customers_table;
SELECT to_regclass('dep_lab.orders') AS orders_table;
SELECT to_regclass('dep_lab.v_order_summary') AS summary_view;
SELECT to_regclass('dep_lab.v_paid_orders') AS paid_view;
SELECT to_regclass('dep_reports.v_customer_totals') AS report_view;

ROLLBACK;
~~~

Khi `DROP TABLE ... CASCADE` được thực hiện **trong transaction đang mở**, các truy vấn `to_regclass(...)` giúp kiểm tra những đối tượng còn tồn tại ở thời điểm đó:

| Đối tượng | Kết quả dự kiến trước `ROLLBACK` | Giải thích |
| --- | --- | --- |
| `dep_lab.customers` | `NULL` | Bảng được yêu cầu xóa |
| `dep_lab.orders` | Vẫn tồn tại | Bảng chứa FK không tự bị xóa theo bảng cha |
| `fk_orders_customer` trên `orders` | Không còn | FK phụ thuộc khóa của bảng `customers` đã bị bỏ |
| `dep_lab.v_order_summary` | `NULL` | View tham chiếu bảng `customers` |
| `dep_lab.v_paid_orders` | `NULL` | View phụ thuộc vào `v_order_summary` |
| `dep_reports.v_customer_totals` | `NULL` | View ở schema khác tham chiếu `customers` |

Chú ý `to_regclass(text)` trả về tên đối tượng nếu tìm thấy, hoặc `NULL` nếu quan hệ không tồn tại. Nó tiện cho thí nghiệm vì tránh lỗi khi tên bảng/view đã bị xóa.

Trong thí nghiệm, **bảng `orders` vẫn còn các cột và những dòng đơn hàng**, nhưng **ràng buộc kiểm tra tính hợp lệ của `customer_id` đã bị bỏ**. Đây là rủi ro dữ liệu rất lớn nếu thao tác được commit trên hệ thống thật: ứng dụng có thể tiếp tục ghi các đơn với `customer_id` không còn được bảo đảm tham chiếu.

Cuối cùng:

~~~sql
ROLLBACK;
~~~

đã đặt ở cuối khối thí nghiệm sẽ hoàn nguyên thao tác DDL và khôi phục lại cấu trúc trước khi xóa. PostgreSQL hỗ trợ DDL có tính transaction đối với những thao tác như `DROP TABLE` trong ví dụ. Tuy nhiên, DDL vẫn có thể giữ khóa trong lúc transaction mở và ảnh hưởng các session khác; không nên thử trên production chỉ vì nghĩ rằng có thể rollback.

### CASCADE không tự đưa ra quyết định nghiệp vụ

PostgreSQL biết view nào phụ thuộc vào bảng và constraint nào cần loại bỏ. Nhưng nó **không biết** ứng dụng Java nào đang gọi view đó, đội báo cáo nào cần dữ liệu, hay ràng buộc nào quan trọng cho quy trình bán hàng. Vì vậy, một lệnh `CASCADE` hợp lệ về cú pháp vẫn có thể gây sự cố nghiệp vụ nghiêm trọng.

## 6. Phụ thuộc gián tiếp qua nhiều tầng view

Giả sử chỉ muốn xóa view `v_order_summary`, không xóa bảng dữ liệu:

~~~sql
BEGIN;

DROP VIEW dep_lab.v_order_summary RESTRICT;

ROLLBACK;
~~~

Lệnh `RESTRICT` dự kiến thất bại vì `v_paid_orders` vẫn phụ thuộc vào `v_order_summary`.

Nếu thay bằng:

~~~sql
BEGIN;

DROP VIEW dep_lab.v_order_summary CASCADE;

SELECT to_regclass('dep_lab.v_order_summary') AS summary_view;
SELECT to_regclass('dep_lab.v_paid_orders') AS paid_view;
SELECT to_regclass('dep_lab.customers') AS customers_table;
SELECT to_regclass('dep_lab.orders') AS orders_table;

ROLLBACK;
~~~

thì:

- `v_order_summary` được xóa theo yêu cầu.
- `v_paid_orders` cũng được xóa vì phụ thuộc vào view đầu.
- `customers` và `orders` vẫn tồn tại: chúng là **nguồn dữ liệu được view tham chiếu**, không phải đối tượng phụ thuộc vào view.
- `dep_reports.v_customer_totals` vẫn tồn tại vì view đó đọc trực tiếp hai bảng, **không đọc từ `v_order_summary`**.

Điều này minh họa **hướng của phụ thuộc**:

~~~text
Bảng nguồn  ──►  View A  ──►  View B

DROP View A CASCADE:
      xóa View A, View B
      không xóa Bảng nguồn
~~~

Khi dùng `CASCADE`, PostgreSQL theo các quan hệ phụ thuộc trong catalog, **không tự lan ngược về mọi đối tượng từng được truy vấn trong định nghĩa view**.

## 7. ALTER TABLE ... DROP COLUMN và ảnh hưởng đến view

Không phải lúc nào cũng muốn xóa cả bảng. Một migration có thể yêu cầu bỏ cột `status` khỏi `orders`.

Tuy nhiên, `v_order_summary` đang đọc `orders.status`, và `v_paid_orders` còn lọc bằng cột `status` lấy từ view.

### 7.1. Không cho xóa cột khi còn đối tượng phụ thuộc

~~~sql
BEGIN;

ALTER TABLE dep_lab.orders
DROP COLUMN status RESTRICT;

ROLLBACK;
~~~

Khi PostgreSQL phát hiện view đang phụ thuộc vào cột này, lệnh dự kiến bị từ chối.

### 7.2. Cho phép xóa các đối tượng phụ thuộc của cột

~~~sql
BEGIN;

ALTER TABLE dep_lab.orders
DROP COLUMN status CASCADE;

SELECT to_regclass('dep_lab.orders') AS orders_table;
SELECT to_regclass('dep_lab.v_order_summary') AS summary_view;
SELECT to_regclass('dep_lab.v_paid_orders') AS paid_view;
SELECT to_regclass('dep_reports.v_customer_totals') AS totals_view;

ROLLBACK;
~~~

Kết quả mong đợi:

- Bảng `orders` vẫn tồn tại nhưng không còn cột `status` trong transaction thử nghiệm.
- View `v_order_summary` phụ thuộc cột `status` bị xóa.
- View `v_paid_orders` phụ thuộc tiếp theo cũng bị xóa.
- `dep_reports.v_customer_totals` không tham chiếu `status` nên vẫn tồn tại nếu không có phụ thuộc khác bị ảnh hưởng.

**Bài học:** `DROP COLUMN ... CASCADE` có thể xóa **cả view**, không chỉ “bỏ cột đó khỏi định nghĩa view”. PostgreSQL không tự viết lại mọi truy vấn để làm cho view vẫn chạy được sau khi một cột nguồn bị xóa.

### Một số thành phần tự được xử lý khi cột bị xóa

Khi xóa một cột, các đối tượng gắn chặt với cột như một số index/constraint liên quan có thể tự bị loại bỏ theo cơ chế dependency nội bộ hoặc tự động. Việc này không có nghĩa PostgreSQL luôn yêu cầu bạn viết `CASCADE` cho từng index thuộc cột.

Nếu cột nằm trong primary key, unique constraint hoặc được bảng khác tham chiếu bằng foreign key, hãy kiểm tra toàn bộ ràng buộc trước khi thay đổi. Không nên tự giả định các khóa và view sẽ được sửa theo đúng mong muốn ứng dụng.

## 8. DROP SCHEMA và tác động vượt qua ranh giới schema

Xóa schema là một trong những thao tác dễ gây hiểu lầm nhất:

~~~sql
DROP SCHEMA dep_lab RESTRICT;
~~~

Trong lab hiện có nhiều bảng và view bên trong `dep_lab`, nên lệnh mặc định/`RESTRICT` sẽ bị chặn. `RESTRICT` không cho xóa một schema vẫn chứa các đối tượng cần xử lý.

Thử `CASCADE` trong một transaction:

~~~sql
BEGIN;

DROP SCHEMA dep_lab CASCADE;

SELECT EXISTS (
    SELECT 1
    FROM pg_namespace
    WHERE nspname = 'dep_lab'
) AS dep_lab_exists;

SELECT EXISTS (
    SELECT 1
    FROM pg_namespace
    WHERE nspname = 'dep_reports'
) AS dep_reports_exists;

SELECT to_regclass('dep_reports.v_customer_totals')
       AS totals_view;

ROLLBACK;
~~~

Giải thích:

- Schema `dep_lab` và các đối tượng thuộc nó bị xóa trong transaction.
- View `dep_reports.v_customer_totals`, dù ở **schema khác**, vẫn bị xóa vì phụ thuộc các bảng của `dep_lab`.
- Schema `dep_reports` **vẫn tồn tại**, vì bản thân schema này không phải đối tượng phụ thuộc cần xóa chỉ vì một view trong nó bị xóa.

Chính vì vậy, `DROP SCHEMA some_schema CASCADE` không nhất thiết chỉ tác động trong phạm vi `some_schema`. Một dependency từ bên ngoài có thể làm chuỗi xóa lan sang **đối tượng thuộc schema khác**.

Để dọn dẹp lab sau khi đã xác minh không còn cần dữ liệu, người học có thể xóa các schema do mình tạo. Nhưng **không chạy lệnh dọn dẹp có `CASCADE` nếu chưa kiểm tra hết phụ thuộc ngoài schema**.

## 9. Khóa ngoại: DROP CASCADE không phải ON DELETE CASCADE

Hai cú pháp dùng cùng từ `CASCADE` nhưng giải quyết hai bài toán **hoàn toàn khác nhau**.

### 9.1. ON DELETE CASCADE là hành vi DML theo hàng

~~~sql
CREATE TABLE parent_demo (
    id integer PRIMARY KEY
);

CREATE TABLE child_demo (
    id integer PRIMARY KEY,
    parent_id integer REFERENCES parent_demo(id)
        ON DELETE CASCADE
);
~~~

Trong ví dụ này, khi xóa một **hàng** ở `parent_demo`, PostgreSQL có thể tự xóa các hàng ở `child_demo` tham chiếu tới hàng cha, theo ràng buộc foreign key.

~~~sql
DELETE FROM parent_demo WHERE id = 10;
~~~

Đây là thao tác **DML trên dữ liệu trong bảng**, không xóa định nghĩa của bảng `parent_demo` hay `child_demo`.

### 9.2. DROP TABLE ... CASCADE là hành vi DDL theo đối tượng

~~~sql
DROP TABLE parent_demo CASCADE;
~~~

Lệnh này yêu cầu xóa **đối tượng bảng** và các đối tượng phụ thuộc cần thiết. Nếu `child_demo` có foreign key tham chiếu `parent_demo`, PostgreSQL có thể bỏ **foreign key constraint** ở `child_demo` nhưng vẫn giữ `child_demo` và những hàng bên trong.

| Cú pháp | Đối tượng bị tác động chính | Ý nghĩa |
| --- | --- | --- |
| `DELETE FROM parent_demo ...` | Hàng dữ liệu | Xóa những hàng phù hợp điều kiện |
| `ON DELETE CASCADE` | Hàng con có khóa ngoại | Tự xóa hàng con khi xóa hàng cha |
| `DROP TABLE parent_demo CASCADE` | Định nghĩa bảng và đối tượng phụ thuộc | Xóa bảng cha, constraint/view phụ thuộc theo quy tắc |

Tương tự, **`ON DELETE RESTRICT`** trong định nghĩa foreign key liên quan tới hành vi **xóa hàng cha**, không phải chính sách phụ thuộc của lệnh `DROP TABLE ... RESTRICT`.

Đừng nhầm hai tầng này khi đọc thông báo lỗi hoặc thiết kế migration.

## 10. Những phụ thuộc được dọn tự động

PostgreSQL không đòi hỏi `CASCADE` để xóa **mọi đối tượng con thuộc cấu trúc nội bộ** của một bảng.

Ví dụ:

~~~sql
CREATE TABLE dep_lab.logs (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message text NOT NULL
);

CREATE INDEX idx_logs_message
    ON dep_lab.logs (message);
~~~

Khi xóa bảng:

~~~sql
BEGIN;
DROP TABLE dep_lab.logs RESTRICT;
ROLLBACK;
~~~

thì PostgreSQL vẫn có thể xóa bảng cùng những thành phần **thuộc sở hữu/được tạo để phục vụ chính bảng đó**, chẳng hạn index trên bảng và sequence gắn với identity column, ngay cả khi dùng `RESTRICT`.

Đây không phải mâu thuẫn với quy tắc `RESTRICT`. Những thành phần như index thuộc bảng có quan hệ phụ thuộc **tự động hoặc nội bộ**, khác với một view độc lập tham chiếu dữ liệu của bảng hay một foreign key từ **bảng khác**.

### Identity sequence và owned sequence

Trong ví dụ `GENERATED ALWAYS AS IDENTITY`, PostgreSQL quản lý sequence liên quan theo mô hình identity. Khi cột/bảng bị xóa, sequence thuộc cột cũng được xử lý theo quan hệ dependency tương ứng.

Với sequence tạo thủ công, có thể quản lý quan hệ ownership:

~~~sql
CREATE TABLE dep_lab.events (
    event_id bigint PRIMARY KEY,
    description text NOT NULL
);

CREATE SEQUENCE dep_lab.events_event_id_seq;

ALTER SEQUENCE dep_lab.events_event_id_seq
OWNED BY dep_lab.events.event_id;
~~~

Quan hệ `OWNED BY` là cách yêu cầu sequence gắn vòng đời vào cột tương ứng. Nếu cột hoặc bảng bị xóa theo cách phù hợp, PostgreSQL tự quản lý việc xóa sequence thuộc sở hữu ấy.

Một sequence **không có ownership** không nhất thiết được xóa chỉ vì ứng dụng từng dùng `nextval()` trên nó. Điều này nhắc lại rằng **dependency được hệ quản trị ghi nhận** mới quyết định hành vi DDL, không phải mọi thói quen dùng đối tượng trong ứng dụng.

## 11. Các nhóm dependency trong catalog PostgreSQL

PostgreSQL có nhiều kiểu phụ thuộc trong catalog `pg_depend`. Cột `deptype` cho biết ý nghĩa của quan hệ; một số giá trị phổ biến:

| `deptype` | Tên thường gặp | Trực giác vận hành |
| --- | --- | --- |
| `n` | Normal | Đối tượng phụ thuộc có thể được xóa riêng; xóa đối tượng được tham chiếu cần `CASCADE` nếu vẫn còn phụ thuộc |
| `a` | Automatic | Đối tượng phụ thuộc có thể được xóa tự động khi đối tượng được tham chiếu bị xóa |
| `i` | Internal | Thành phần nội bộ của đối tượng khác; không được xem như đối tượng độc lập có thể tự ý xóa theo mọi cách |
| `e` | Extension | Đối tượng là thành viên của một extension; vòng đời chịu quy tắc quản lý extension |
| `P` / `S` | Partition dependencies | Những phụ thuộc liên quan cấu trúc partition, có quy tắc quản lý riêng |

Người học không cần thuộc lòng toàn bộ catalog để dùng `DROP`, nhưng việc biết có **nhiều loại dependency** giúp lý giải tại sao:

- Một view chặn `DROP TABLE ... RESTRICT`.
- Một index thuộc bảng lại bị xóa cùng bảng mà không đòi `CASCADE` riêng.
- Một đối tượng thuộc extension có thể không được cho phép xóa trực tiếp; cần xử lý ở cấp extension.
- Các cấu trúc partition có thể có quy tắc chặt hơn so với bảng thông thường.

**Không tự sửa trực tiếp `pg_depend`.** Đây là catalog hệ thống quan trọng để PostgreSQL bảo đảm tính nhất quán lược đồ. Hãy thao tác qua DDL chính thức và để PostgreSQL duy trì dependency.

### View có một chi tiết catalog dễ bỏ qua

Một view trong PostgreSQL gắn với **rewrite rule** lưu định nghĩa truy vấn. Khi tra `pg_depend`, quan hệ tới bảng nguồn thường được biểu diễn qua **rule `_RETURN` trong `pg_rewrite`**, thay vì mọi dòng dependency đều trực tiếp gắn `objid` với OID của view.

Đó là lý do một truy vấn ngây thơ chỉ dò “OID view → OID bảng nguồn” có thể bỏ sót phụ thuộc, dù PostgreSQL vẫn biết và xử lý đúng khi `DROP`.

## 12. Xem dependency của khóa ngoại bằng pg_constraint

Đối với foreign key, truy vấn từ `pg_constraint` thường dễ hiểu hơn việc tự giải mã mọi dòng `pg_depend`:

~~~sql
SELECT
    conname AS constraint_name,
    conrelid::regclass AS referencing_table,
    confrelid::regclass AS referenced_table,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'f'
  AND confrelid = 'dep_lab.customers'::regclass
ORDER BY conname;
~~~

Ý nghĩa các cột:

| Cột | Ý nghĩa |
| --- | --- |
| `conname` | Tên constraint |
| `conrelid` | Bảng **chứa** foreign key |
| `confrelid` | Bảng **được tham chiếu** |
| `pg_get_constraintdef(oid)` | Định nghĩa constraint dưới dạng dễ đọc |

Với ví dụ, kết quả dự kiến có `fk_orders_customer`, `referencing_table = dep_lab.orders` và `referenced_table = dep_lab.customers`.

Để tìm tất cả foreign key trên bảng `orders` bất kể tham chiếu tới đâu, có thể đổi điều kiện thành:

~~~sql
WHERE contype = 'f'
  AND conrelid = 'dep_lab.orders'::regclass
~~~

Hãy xem đây là câu tìm metadata, không phải lệnh thay đổi quyền hay schema.

## 13. Xem view nào tham chiếu một bảng

Trong `psql`, cách dễ bắt đầu là:

~~~text
\d+ dep_lab.customers
\d+ dep_lab.orders
\dv dep_lab.*
~~~

Để xem định nghĩa của một view:

~~~sql
SELECT pg_get_viewdef(
    'dep_lab.v_order_summary'::regclass,
    true
) AS view_definition;
~~~

Trong một số trường hợp, `psql` cũng hiển thị những đối tượng phụ thuộc dưới phần thông tin bảng; khả năng hiển thị tùy loại đối tượng và phiên bản.

### Dò view phụ thuộc trực tiếp bằng pg_depend và pg_rewrite

Ví dụ dưới đây minh họa việc tìm các view có rewrite rule tham chiếu bảng `dep_lab.orders`:

~~~sql
SELECT DISTINCT
    dep_ns.nspname AS dependent_schema,
    dep_rel.relname AS dependent_view,
    src_ns.nspname AS referenced_schema,
    src_rel.relname AS referenced_relation
FROM pg_depend AS d
JOIN pg_rewrite AS rw
    ON rw.oid = d.objid
JOIN pg_class AS dep_rel
    ON dep_rel.oid = rw.ev_class
JOIN pg_namespace AS dep_ns
    ON dep_ns.oid = dep_rel.relnamespace
JOIN pg_class AS src_rel
    ON src_rel.oid = d.refobjid
JOIN pg_namespace AS src_ns
    ON src_ns.oid = src_rel.relnamespace
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_class'::regclass
  AND d.deptype = 'n'
  AND rw.rulename = '_RETURN'
  AND dep_rel.relkind IN ('v', 'm')
  AND src_rel.oid = 'dep_lab.orders'::regclass
ORDER BY dependent_schema, dependent_view;
~~~

Trên dữ liệu mẫu, các view phụ thuộc **trực tiếp** vào `dep_lab.orders` thường gồm:

- `dep_lab.v_order_summary`.
- `dep_reports.v_customer_totals`.

`dep_lab.v_paid_orders` đọc **view `v_order_summary`**, không trực tiếp đọc `orders`, nên một truy vấn chỉ tìm quan hệ phụ thuộc trực tiếp vào `orders` có thể không liệt kê nó. Muốn đánh giá toàn bộ **chuỗi phụ thuộc gián tiếp**, phải lần theo các cấp quan hệ hoặc dùng công cụ có khả năng dựng đồ thị dependency.

**Giới hạn cần nhớ:** truy vấn trên nhắm tới **view/materialized view thông qua rule `_RETURN`**. Nó không phải phép liệt kê đầy đủ mọi loại phụ thuộc như FK, function, sequence, trigger, extension hoặc dependency phát sinh qua những cấu trúc khác.

### Tra cứu các đối tượng thuộc schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname IN ('dep_lab', 'dep_reports')
ORDER BY n.nspname, c.relkind, c.relname;
~~~

Một số `relkind` hay gặp: `r` cho bảng thường, `v` cho view, `m` cho materialized view, `i` cho index, `S` cho sequence, `p` cho partitioned table. Truy vấn này hỗ trợ kiểm kê quan hệ trong schema, **không thể thay thế đồ thị dependency**.

## 14. RESTRICT/CASCADE với DROP FUNCTION, TYPE và EXTENSION

Hai tùy chọn không chỉ dành cho bảng và view.

### 14.1. Hàm được view sử dụng

Ví dụ tạo một hàm SQL đơn giản và một view gọi hàm:

~~~sql
CREATE FUNCTION dep_lab.double_amount(x numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
RETURN x * 2;

CREATE VIEW dep_lab.v_amount_preview AS
SELECT
    order_id,
    dep_lab.double_amount(amount) AS doubled_amount
FROM dep_lab.orders;
~~~

`RETURN x * 2` là cú pháp SQL function body kiểu SQL-standard của các bản PostgreSQL hiện đại hỗ trợ dạng này. Với định nghĩa view, PostgreSQL ghi nhận phụ thuộc vào hàm được dùng.

Thử:

~~~sql
BEGIN;
DROP FUNCTION dep_lab.double_amount(numeric) RESTRICT;
ROLLBACK;
~~~

Lệnh dự kiến bị từ chối vì còn view dùng hàm. Nếu viết `CASCADE`:

~~~sql
BEGIN;
DROP FUNCTION dep_lab.double_amount(numeric) CASCADE;
SELECT to_regclass('dep_lab.v_amount_preview') AS preview_view;
ROLLBACK;
~~~

view phụ thuộc có thể bị xóa theo chuỗi.

**Quan trọng:** khi xóa function overload, cần chỉ rõ **chữ ký kiểu tham số**, ví dụ `double_amount(numeric)`. PostgreSQL cho phép nhiều hàm cùng tên nhưng khác kiểu tham số, nên chỉ xem tên hàm là chưa đủ.

Không phải mọi tham chiếu tới hàm hay bảng nằm trong một chuỗi SQL động đều được theo dõi theo cách này. Dependency catalog bảo vệ tốt các tham chiếu mà PostgreSQL phân tích được trong định nghĩa đối tượng, nhưng không thể thay thế việc kiểm tra mã ứng dụng và dynamic SQL.

### 14.2. Type và domain

Một cột có thể dùng kiểu tùy chỉnh hoặc domain. Nếu muốn xóa type đang được cột hoặc hàm sử dụng, `RESTRICT` có thể chặn; `CASCADE` có thể xóa những đối tượng phụ thuộc theo cơ chế PostgreSQL.

Ví dụ cú pháp:

~~~sql
DROP TYPE some_schema.some_type RESTRICT;
DROP TYPE some_schema.some_type CASCADE;
~~~

Đây là **minh họa**, không chạy khi chưa tạo type và kiểm kê các đối tượng đang dùng nó. Xóa type có thể kéo theo đối tượng quan trọng hơn nhiều so với bản thân type.

### 14.3. Extension

Một extension như `hstore` hoặc `pg_trgm` có thể tạo function, operator, type, index operator class và những đối tượng phụ trợ. Các đối tượng là thành viên extension chịu quy tắc quản lý vòng đời của extension.

~~~sql
-- Chỉ minh họa cú pháp, không chạy trên môi trường thật
-- nếu chưa đánh giá toàn bộ phụ thuộc:
DROP EXTENSION pg_trgm RESTRICT;
DROP EXTENSION pg_trgm CASCADE;
~~~

`CASCADE` có thể gỡ những đối tượng bên ngoài extension đang phụ thuộc vào đối tượng do extension cung cấp, theo quy tắc PostgreSQL. Đây là thao tác cần xem xét đặc biệt kỹ khi nâng cấp hoặc gỡ extension của ứng dụng.

## 15. Xóa phụ thuộc theo thứ tự thủ công thay vì CASCADE

Nếu muốn thao tác có thể kiểm soát và review từng bước, có thể **xóa những đối tượng phụ thuộc từ ngoài vào trong**, rồi mới xóa đối tượng nguồn.

Với `customers` trong lab, ví dụ sau chỉ ra một thứ tự xóa có chủ đích:

~~~sql
BEGIN;

-- 1. Xóa view ở tầng phụ thuộc cao nhất.
DROP VIEW dep_lab.v_paid_orders;

-- 2. Xóa view đọc trực tiếp các bảng.
DROP VIEW dep_lab.v_order_summary;
DROP VIEW dep_reports.v_customer_totals;

-- 3. Bỏ FK của bảng còn được giữ lại.
ALTER TABLE dep_lab.orders
DROP CONSTRAINT fk_orders_customer;

-- 4. Giờ mới xóa bảng khách hàng.
DROP TABLE dep_lab.customers RESTRICT;

-- 5. Chỉ kiểm tra, không giữ thay đổi phá hủy.
ROLLBACK;
~~~

Ưu điểm:

- Mỗi lệnh nêu rõ **đối tượng dự định xóa**.
- Dễ đưa từng bước vào code review của database migration.
- Dễ tách quyết định giữ bảng `orders` và thay đổi FK thành lựa chọn nghiệp vụ.
- Dễ lập kế hoạch dựng lại những view cần thay đổi định nghĩa.

Nhược điểm: phải kiểm kê đủ mọi đối tượng phụ thuộc. Nếu có view hoặc constraint mới được tạo ở nơi khác trong lúc chuẩn bị migration, `RESTRICT` vẫn có thể báo lỗi; đó thường là tín hiệu tốt để xem lại tác động thay vì tự thêm `CASCADE`.

**Tránh giả định rằng thứ tự xóa thủ công tự bảo đảm dữ liệu nghiệp vụ đúng.** Nếu bỏ foreign key nhưng vẫn giữ cột `orders.customer_id`, ứng dụng cần phương án duy trì tính toàn vẹn tham chiếu khi thay đổi thiết kế quan hệ.

## 16. Thay đổi schema có cần transaction không?

PostgreSQL hỗ trợ **DDL transactional** đối với nhiều thao tác như tạo/xóa bảng, view và constraint. Điều đó giúp thử trong môi trường riêng và rollback nếu bước dự kiến gây lỗi.

~~~sql
BEGIN;

DROP VIEW dep_lab.v_paid_orders;
DROP VIEW dep_lab.v_order_summary;

-- Nếu chưa thực sự muốn thay đổi, hủy transaction:
ROLLBACK;
~~~

Sau `ROLLBACK`, hai view được khôi phục về trạng thái trước transaction, với điều kiện chúng chỉ bị thay đổi trong transaction đó.

Tuy nhiên, không phải **mọi** thao tác quản trị PostgreSQL đều được phép thực hiện trong transaction block; chẳng hạn `DROP DATABASE` có những hạn chế riêng. Ngoài ra, khi DDL chạy trong transaction, PostgreSQL vẫn có thể giữ **lock** trên đối tượng cho tới khi transaction kết thúc.

### Thử lỗi RESTRICT trong transaction

Trong PostgreSQL, nếu một lệnh bị lỗi sau `BEGIN`, transaction thường chuyển sang trạng thái aborted. Chỉ các lệnh như `ROLLBACK` hoặc rollback về savepoint phù hợp mới giúp thoát trạng thái này.

Một mẫu dành cho thử nghiệm tương tác:

~~~sql
BEGIN;
SAVEPOINT before_drop;

-- Dự kiến thất bại vì phụ thuộc:
DROP TABLE dep_lab.customers RESTRICT;

-- Chạy lệnh này sau lỗi nếu client tiếp tục nhận lệnh:
ROLLBACK TO SAVEPOINT before_drop;

-- Có thể tiếp tục các kiểm tra trong transaction:
SELECT COUNT(*) FROM dep_lab.customers;

ROLLBACK;
~~~

Nếu chạy trong pipeline dùng `psql -v ON_ERROR_STOP=1` hoặc công cụ tự ngắt script khi gặp lỗi, những lệnh sau lỗi có thể **không được thực hiện**; hãy bảo đảm transaction được rollback trước khi dùng lại kết nối.

**Dù có transaction, vẫn nên thử trên một bản sao/staging có thể phục hồi.** Một câu `DROP ... CASCADE` vô tình commit có thể làm mất cả cấu trúc và dữ liệu. Transaction không phải cơ chế backup và không giải quyết lỗi vận hành xảy ra sau commit.

## 17. Quy trình migration an toàn khi có dependency

Trước khi thực hiện `DROP TABLE`, `DROP VIEW` hoặc `ALTER TABLE DROP COLUMN` trên production, có thể dùng quy trình:

1. **Xác định đối tượng nguồn**: tên đầy đủ gồm schema, bảng, view, cột, function signature; tránh nhầm do `search_path`.
2. **Kiểm kê dependency trong PostgreSQL**: khóa ngoại, view, materialized view, sequence, index, constraint, extension và các đối tượng liên quan.
3. **Kiểm tra dependency ngoài database**: SQL trong Java, ORM mappings, stored application queries, báo cáo, BI, job, ETL và các contract dữ liệu.
4. **Dự kiến tác động của RESTRICT/CASCADE**: đối tượng nào bị chặn, đối tượng nào bị xóa, bảng nào vẫn tồn tại nhưng mất ràng buộc.
5. **Thiết kế migration có thể review**: ưu tiên xác định rõ từng đối tượng; nếu dùng `CASCADE` phải có danh sách những đối tượng kỳ vọng bị loại bỏ.
6. **Chuẩn bị khôi phục**: có backup/snapshot phù hợp, thử restore và phương án dựng lại đối tượng khi cần.
7. **Thử trên staging**: chạy migration và các câu truy vấn nghiệp vụ; kiểm tra thứ tự DDL và thời lượng lock.
8. **Triển khai có kiểm soát**: xét cửa sổ bảo trì, lock timeout, các session đang truy vấn và cách ứng dụng triển khai schema phiên bản mới.
9. **Xác minh sau thay đổi**: kiểm tra catalog, constraint, view, query ứng dụng, kết quả nghiệp vụ và log lỗi.

### Ví dụ kiểu thay đổi “mở rộng trước, thu hẹp sau”

Nếu cần bỏ cột `status` nhưng view đang dùng nó, một chiến lược an toàn hơn việc xóa ngay thường là:

~~~text
Giai đoạn 1: Tạo cấu trúc thay thế, ví dụ cột/trạng thái mới
Giai đoạn 2: Cập nhật ứng dụng và view sang cấu trúc mới
Giai đoạn 3: Xác minh không còn consumer cũ
Giai đoạn 4: Bỏ view/cột cũ theo migration đã kiểm tra
~~~

Chiến lược này thường gọi là **expand–migrate–contract**, giúp tránh làm ứng dụng phiên bản cũ bị lỗi trong thời gian triển khai nhiều service.

### Không dùng IF EXISTS như một lớp bảo vệ mất dữ liệu

~~~sql
DROP TABLE IF EXISTS dep_lab.customers CASCADE;
~~~

`IF EXISTS` chỉ làm PostgreSQL không báo lỗi nếu bảng **không tồn tại** (thường phát notice). Khi bảng **có tồn tại**, câu lệnh vẫn thực hiện `CASCADE` và có thể xóa dây chuyền các đối tượng phụ thuộc. Nó không phải chế độ “dry run” và không yêu cầu xác nhận.

## 18. Bài tập thực hành

Dùng các đối tượng `dep_lab` và `dep_reports` được tạo ở phần 3. Nếu chỉ muốn phân tích, không cần chạy những câu `DROP`.

### Bài 1. Dự đoán hành vi RESTRICT

Bảng `orders` có khóa ngoại tham chiếu `customers`, đồng thời view `v_order_summary` đọc `customers`. Điều gì xảy ra khi chạy:

~~~sql
DROP TABLE dep_lab.customers RESTRICT;
~~~

Vì sao PostgreSQL không chỉ bỏ constraint rồi tiếp tục?

### Bài 2. Dự đoán hành vi CASCADE

Giả sử không có đối tượng ngoài những đối tượng lab:

~~~sql
DROP TABLE dep_lab.customers CASCADE;
~~~

Hãy cho biết số phận của:

1. Bảng `dep_lab.orders`.
2. Constraint `fk_orders_customer`.
3. View `dep_lab.v_order_summary`.
4. View `dep_lab.v_paid_orders`.
5. View `dep_reports.v_customer_totals`.

### Bài 3. Phụ thuộc nhiều tầng view

Cho `v_paid_orders` đọc `v_order_summary`, còn `v_order_summary` đọc hai bảng nguồn. Lệnh:

~~~sql
DROP VIEW dep_lab.v_order_summary CASCADE;
~~~

có xóa bảng `orders` không? Vì sao?

### Bài 4. DROP COLUMN CASCADE

`v_order_summary` tham chiếu cột `orders.status`. Nếu chạy:

~~~sql
ALTER TABLE dep_lab.orders
DROP COLUMN status CASCADE;
~~~

PostgreSQL có tự xóa cột `status` khỏi định nghĩa view và giữ view hoạt động không? Những đối tượng nào có thể bị xóa theo dependency?

### Bài 5. Schema khác nhưng vẫn phụ thuộc

View `dep_reports.v_customer_totals` đọc bảng từ schema `dep_lab`. Nếu chạy `DROP SCHEMA dep_lab CASCADE`, schema `dep_reports` có bị xóa không? View bên trong thì sao?

### Bài 6. Hai loại CASCADE

Giải thích sự khác nhau giữa:

~~~sql
DELETE FROM parent_demo WHERE id = 10;
-- Foreign key ở child_demo có ON DELETE CASCADE.

DROP TABLE parent_demo CASCADE;
~~~

Lệnh nào liên quan tới xóa **hàng dữ liệu**, lệnh nào liên quan tới xóa **định nghĩa đối tượng**?

### Bài 7. Tìm khóa ngoại tham chiếu customers

Viết truy vấn catalog hiển thị tên foreign key, bảng chứa FK và bảng được tham chiếu, dành cho những FK trỏ tới `dep_lab.customers`.

### Bài 8. Thứ tự xóa thủ công

Hãy sắp các thao tác thành trình tự có thể dùng `RESTRICT` thay vì `CASCADE` khi muốn xóa `customers`:

- Bỏ constraint `fk_orders_customer`.
- Xóa `v_paid_orders`.
- Xóa `v_order_summary`.
- Xóa `dep_reports.v_customer_totals`.
- Xóa `customers`.

Giải thích vì sao phải xử lý view cấp trên trước view cấp dưới.

### Bài 9. Dependency không được catalog phát hiện

Ứng dụng Java có SQL `SELECT status FROM dep_lab.orders` nhưng không có view/function PostgreSQL nào chứa SQL đó. Query `pg_depend` có đủ để khẳng định bỏ cột `status` không làm hỏng ứng dụng không?

### Bài 10. RESTRICT và transaction

Trong một transaction, lệnh `DROP TABLE ... RESTRICT` bị lỗi do dependency. Vì sao câu `SELECT` tiếp theo có thể bị từ chối? Phải dùng lệnh nào để tiếp tục?

### Gợi ý đáp án

| Bài | Đáp án chính |
| --- | --- |
| 1 | Bị từ chối vì FK và view phụ thuộc bình thường vẫn tồn tại; `RESTRICT` không tự chấp thuận loại bỏ chúng |
| 2 | `orders` còn; FK bị bỏ; `v_order_summary`, `v_paid_orders` và `v_customer_totals` bị xóa theo chuỗi |
| 3 | Không. Bảng `orders` là nguồn được view đọc, không phải đối tượng phụ thuộc của view cần xóa |
| 4 | PostgreSQL không tự viết lại view để bỏ cột; các view liên quan có thể bị xóa theo `CASCADE` |
| 5 | Schema `dep_reports` còn; view `v_customer_totals` phụ thuộc bảng trong `dep_lab` nên bị loại bỏ |
| 6 | `ON DELETE CASCADE` gắn với hàng dữ liệu; `DROP ... CASCADE` gắn với đối tượng schema |
| 7 | Dùng `pg_constraint` với `contype = 'f'` và `confrelid = 'dep_lab.customers'::regclass` |
| 8 | Xóa `v_paid_orders`, `v_order_summary`, `v_customer_totals`, bỏ FK, rồi xóa `customers`; có thể đổi thứ tự những thao tác độc lập |
| 9 | Không. Dependency của SQL trong ứng dụng không tự xuất hiện trong catalog |
| 10 | Transaction chuyển sang trạng thái lỗi; dùng `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` phù hợp |

Ví dụ lời giải bài 7:

~~~sql
SELECT
    conname,
    conrelid::regclass AS referencing_table,
    confrelid::regclass AS referenced_table
FROM pg_constraint
WHERE contype = 'f'
  AND confrelid = 'dep_lab.customers'::regclass
ORDER BY conname;
~~~

## 19. Bảng tra cứu nhanh

| Tác vụ | Câu lệnh minh họa | Điều cần nhớ |
| --- | --- | --- |
| Xóa bảng nhưng chặn nếu có phụ thuộc bình thường | `DROP TABLE dep_lab.customers RESTRICT;` | Phù hợp để tránh xóa dây chuyền ngoài ý muốn |
| Xóa bảng và các đối tượng phụ thuộc | `DROP TABLE dep_lab.customers CASCADE;` | Có thể bỏ FK ở bảng khác và xóa view |
| Xóa view mà chặn view con | `DROP VIEW dep_lab.v_order_summary RESTRICT;` | View khác đang tham chiếu có thể chặn |
| Xóa view và view con | `DROP VIEW dep_lab.v_order_summary CASCADE;` | Không xóa ngược các bảng nguồn |
| Bỏ cột và các đối tượng phụ thuộc | `ALTER TABLE dep_lab.orders DROP COLUMN status CASCADE;` | Có thể xóa cả view |
| Xóa schema và các phụ thuộc | `DROP SCHEMA dep_lab CASCADE;` | Tác động có thể vượt qua ranh giới schema |
| Xóa FK nhưng giữ bảng | `ALTER TABLE dep_lab.orders DROP CONSTRAINT fk_orders_customer;` | Dữ liệu còn nhưng mất quy tắc tham chiếu |
| Xem FK tham chiếu một bảng | `pg_constraint`, `confrelid` | Kiểm kê ràng buộc |
| Xem view tham chiếu bảng | `pg_depend` + `pg_rewrite` | Chỉ là một phần của đồ thị dependency |
| Thử DDL có thể rollback | `BEGIN; ... ROLLBACK;` | Vẫn có lock, không thay thế backup |

**Ghi nhớ:** PostgreSQL quản lý dependency để bảo vệ tính nhất quán của schema. `RESTRICT` buộc người quản trị xử lý các đối tượng phụ thuộc bình thường trước khi xóa, còn `CASCADE` chấp thuận một chuỗi xóa có thể đi qua nhiều cấp view, constraint, cột và thậm chí schema khác. Khi quyết định xóa đối tượng, hãy kiểm tra **hướng dependency, phạm vi đối tượng sẽ bị ảnh hưởng, các tham chiếu từ ứng dụng** và phương án khôi phục. Một câu DDL chạy thành công về mặt cú pháp chưa đủ để kết luận hệ thống vẫn an toàn về mặt nghiệp vụ.
