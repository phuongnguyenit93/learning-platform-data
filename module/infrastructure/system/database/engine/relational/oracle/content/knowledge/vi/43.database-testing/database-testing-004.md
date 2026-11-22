# Tạo/reset schema, seed dữ liệu và thứ tự quan hệ khóa ngoại

Kiểm thử ứng dụng dùng Oracle Database cần một môi trường dữ liệu có thể dựng lại, có trạng thái ban đầu rõ ràng và cho kết quả ổn định giữa các lần chạy. Nếu schema còn sót dữ liệu từ test trước, khóa ngoại không được tạo đúng thứ tự hoặc sequence tiếp tục sinh giá trị không dự đoán được, test có thể lúc pass lúc fail dù code không thay đổi.

Ba công việc nền tảng của test database là:

1. **Tạo schema:** chuẩn bị user, quyền, tablespace và các object cần cho ứng dụng.
2. **Reset schema:** đưa môi trường về trạng thái sạch hoặc về một baseline đã biết.
3. **Seed dữ liệu:** nạp dữ liệu kiểm thử theo thứ tự phụ thuộc, đặc biệt là quan hệ primary key/foreign key.

Với Oracle, cần chú ý một khác biệt quan trọng: nhiều câu lệnh DDL như `CREATE`, `ALTER`, `DROP` và `TRUNCATE` gây implicit commit. Vì vậy, không thể dựa vào `ROLLBACK` để hoàn tác một lần reset schema có DDL. Cần thiết kế môi trường test tách biệt và quy trình reset có kiểm soát.

## 1. Schema Oracle và user sở hữu object

Trong Oracle, schema là tập hợp các database object thuộc một database user. Tên schema thường trùng với tên user sở hữu object. Ví dụ user `APP_TEST` sở hữu các bảng `CUSTOMERS`, `ORDERS`, package, sequence, trigger và view của ứng dụng.

Một môi trường kiểm thử có thể dùng:

| User/schema | Mục đích |
|---|---|
| `APP_OWNER` | Schema sở hữu object ứng dụng trong môi trường chuẩn hoặc schema được triển khai từ migration |
| `APP_TEST` | Schema riêng cho integration test |
| `APP_RUNTIME` | User mô phỏng tài khoản kết nối của ứng dụng, chỉ nhận quyền cần thiết |
| `TEST_ADMIN` | Tài khoản quản trị môi trường test, được cấp quyền tạo/reset schema theo phạm vi riêng |

Không nên chạy test bằng `SYS`, `SYSTEM` hoặc tài khoản DBA. Quyền quản trị rộng có thể che giấu lỗi thiếu privilege của ứng dụng và làm test vô tình thay đổi object ngoài phạm vi.

### 1.1. Tạo user/schema test

DBA hoặc tài khoản có quyền phù hợp có thể tạo user riêng cho test. Ví dụ:

```sql
CREATE USER app_test
IDENTIFIED BY "Use-A-Secret-From-The-Test-Environment"
DEFAULT TABLESPACE users
TEMPORARY TABLESPACE temp
QUOTA 500M ON users;
```

Trong môi trường thực tế, password phải lấy từ secret store hoặc cơ chế cấp credential của CI, không ghi vào source control. Tên tablespace và quota phải phù hợp với môi trường. Quota giới hạn dung lượng segment mà schema có thể cấp phát; chỉ grant `CREATE TABLE` mà không có quota thích hợp có thể dẫn đến lỗi khi tạo object.

Cấp các system privilege tối thiểu để schema chạy migration/test:

```sql
GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE VIEW,
      CREATE SEQUENCE,
      CREATE PROCEDURE,
      CREATE TRIGGER,
      CREATE TYPE,
      CREATE SYNONYM
TO app_test;
```

Danh sách trên chỉ là ví dụ cho schema có package, trigger, type và synonym. Nếu ứng dụng không dùng một loại object nào, không cần cấp quyền tương ứng. Một số migration có thể cần thêm quyền đặc thù; hãy xác định theo DDL thực tế thay vì cấp `DBA` hoặc các quyền `ANY` để tránh lỗi.

Nếu test cần tạo object trong schema khác, cần thiết kế quyền riêng và xác nhận chính xác yêu cầu. Không cấp `CREATE ANY TABLE` hoặc `DROP ANY TABLE` cho runtime user chỉ để đơn giản hóa fixture.

### 1.2. Tách quyền owner và runtime

Một test có thể chạy hai nhóm kiểm tra:

- Migration/schema test kết nối bằng `APP_TEST` để tạo và thay đổi object.
- Application integration test kết nối bằng `APP_RUNTIME` để xác nhận đúng quyền mà ứng dụng production sẽ có.

Ví dụ:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON app_test.orders
TO app_runtime;

GRANT SELECT
ON app_test.customers
TO app_runtime;
```

Trong Oracle, object privilege cần được cấp trên từng object hoặc thông qua role thích hợp. Nếu stored PL/SQL chạy với `AUTHID DEFINER`, owner của program unit có thể cần direct grant trên object khác schema; quyền chỉ nhận qua role không đủ cho nhiều trường hợp compile/execute definer-rights code. Test bằng runtime user giúp phát hiện khác biệt giữa quyền DBA và quyền ứng dụng.

## 2. Chọn chiến lược tạo và reset schema

Không có một cách reset phù hợp cho mọi test. Cần chọn dựa trên thời gian chạy, mức cô lập, số lượng object và mức độ an toàn của môi trường.

| Chiến lược | Cách làm | Phù hợp khi |
|---|---|---|
| Schema mới cho mỗi test run | Tạo user/schema riêng, chạy migration, seed và xóa khi kết thúc | CI song song, cần isolation mạnh |
| PDB/database dùng riêng cho test | Tạo hoặc clone môi trường database test rồi chạy test trên đó | Cần môi trường gần production và reset toàn bộ |
| Drop/recreate schema | Xóa user test cùng object rồi tạo lại | Schema test dùng riêng, có quyền quản trị |
| Drop/recreate object | Xóa object theo dependency rồi chạy migration | Muốn giữ user và cấu hình schema |
| Delete/truncate data | Giữ cấu trúc, chỉ xóa dữ liệu rồi seed lại | Test chạy lặp trên schema ổn định |
| Rollback transaction | Chạy DML trong transaction và rollback | Test đơn lẻ không cần commit hoặc kiểm tra trạng thái sau commit |

### 2.1. Môi trường test phải tách khỏi production

Reset schema là thao tác phá hủy dữ liệu. Hãy dùng database/PDB/schema dành riêng cho test, tài khoản riêng, service name riêng và secret riêng. CI nên xác minh database identity hoặc một marker cấu hình trước khi chạy reset.

Không để biến môi trường test mặc định trỏ đến production. Nên fail-fast nếu URL, `DB_UNIQUE_NAME`, PDB hoặc schema không nằm trong allowlist test. Chỉ kiểm tra tên user là chưa đủ: một database production cũng có thể chứa user tên `APP_TEST`.

### 2.2. Drop và tạo lại user

Trong một database test dùng riêng, DBA có thể xóa schema:

```sql
DROP USER app_test CASCADE;
```

`CASCADE` xóa user cùng các object thuộc schema. Đây là thao tác không thể hoàn tác bằng `ROLLBACK`. Chỉ thực hiện sau khi xác nhận đúng database và đúng user test.

Tạo lại user và cấp quyền bằng script bootstrap. Nên lưu DDL user, quota và grant trong repository hoặc migration infrastructure để môi trường có thể dựng lại nhất quán.

### 2.3. Reset bằng cách xóa dữ liệu

Nếu không muốn drop schema mỗi lần, có thể xóa dữ liệu trong các bảng. Với quan hệ khóa ngoại, cần xóa bảng con trước bảng cha nếu foreign key không có `ON DELETE CASCADE`.

Ví dụ thứ tự:

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
DELETE FROM products;
```

Ví dụ này giả định `ORDER_ITEMS` tham chiếu `ORDERS` và `PRODUCTS`, còn `ORDERS` tham chiếu `CUSTOMERS`. Nếu còn bảng con khác, phải đưa chúng vào đúng thứ tự dependency.

`DELETE` là DML nên có thể rollback trước commit. Tuy nhiên, khi chạy trong transaction lớn, lượng undo/redo có thể đáng kể. Trigger delete có thể chạy và làm thay đổi thêm dữ liệu. Hãy xác định rõ reset có cần kích hoạt trigger hay không.

### 2.4. TRUNCATE khác DELETE

`TRUNCATE TABLE` thường nhanh hơn `DELETE` toàn bảng và thu hồi/trả lại segment space theo semantics của Oracle, nhưng là DDL và gây implicit commit. Không thể rollback truncate.

Ví dụ:

```sql
TRUNCATE TABLE app_test.order_items;
TRUNCATE TABLE app_test.orders;
TRUNCATE TABLE app_test.customers;
TRUNCATE TABLE app_test.products;
```

Thứ tự vẫn phải tôn trọng foreign key. Oracle không cho truncate một parent table đang bị tham chiếu bởi foreign key đang enable theo cách thông thường. Chỉ dùng truncate trong schema test và sau khi xác nhận constraint/dependency. Không tắt constraint hàng loạt rồi truncate mà không có bước bật lại và validate.

### 2.5. Không dùng ROLLBACK để reset DDL

Oracle tự commit trước và sau nhiều DDL statement. Ví dụ:

```sql
DELETE FROM app_test.orders;
CREATE TABLE app_test.tmp_test (id NUMBER);
ROLLBACK;
```

`DELETE` trước DDL có thể đã bị commit ngầm trước khi `CREATE TABLE` chạy. `ROLLBACK` cuối không khôi phục các dòng đã xóa. Đây là lý do reset schema cần được xem như một quy trình riêng, không phải một transaction duy nhất.

## 3. Dựng schema theo migration

Trong ứng dụng Spring Boot, schema nên được tạo từ migration có phiên bản thay vì phụ thuộc vào một bản schema thủ công trên máy developer.

Các công cụ phổ biến gồm Flyway và Liquibase. Chúng lưu lịch sử migration và áp dụng script theo thứ tự đã định. Test integration nên dùng cùng migration với môi trường triển khai để phát hiện lỗi DDL, thiếu index, constraint hoặc sequence.

### 3.1. Thứ tự migration

Ví dụ:

```text
V001__create_customers.sql
V002__create_products.sql
V003__create_orders.sql
V004__create_order_items.sql
V005__create_order_indexes.sql
V006__create_order_api.sql
```

Thứ tự này đặt bảng cha trước bảng con, rồi mới tạo index và program unit phụ thuộc vào bảng. Thứ tự thực tế phụ thuộc dependency giữa object, không chỉ giữa bảng.

### 3.2. DDL Oracle và migration transaction

Nhiều DDL của Oracle gây implicit commit. Vì vậy, migration tool không thể giả định mọi DDL được rollback như DML. Nếu migration thất bại giữa chừng, schema có thể ở trạng thái đã áp dụng một phần. Tool migration thường lưu lịch sử và có cơ chế phát hiện failed migration, nhưng cách khôi phục phải tuân theo hướng dẫn của tool và script.

Nên viết migration nhỏ, có thứ tự rõ, dễ xác định trạng thái khi lỗi. Không gộp hàng trăm thao tác DDL không liên quan vào một script khó phục hồi.

### 3.3. Tạo schema trước khi seed

Quy trình chuẩn thường là:

1. Tạo database/PDB/schema test.
2. Cấp quota và privilege.
3. Chạy migration tạo object.
4. Xác nhận migration hoàn tất.
5. Seed dữ liệu reference/master.
6. Seed dữ liệu nghiệp vụ theo dependency.
7. Chạy test.
8. Xóa/reset dữ liệu hoặc hủy schema test.

Không seed dữ liệu vào một schema chưa chạy đủ migration. Nếu schema version thay đổi, seed script cũng cần tương thích với version đó.

## 4. Mô hình ví dụ có quan hệ khóa ngoại

Giả sử hệ thống bán hàng có bốn bảng:

- `CUSTOMERS`: khách hàng.
- `PRODUCTS`: sản phẩm.
- `ORDERS`: đơn hàng, tham chiếu khách hàng.
- `ORDER_ITEMS`: dòng chi tiết đơn hàng, tham chiếu đơn hàng và sản phẩm.

Quan hệ:

```text
CUSTOMERS                 PRODUCTS
    |                         |
    | 1                       | 1
    v                         v
  ORDERS  ----------------> ORDER_ITEMS
       1                         *
```

Sơ đồ dependency của insert:

```text
CUSTOMERS ─────┐
               v
             ORDERS ──────┐
                          v
PRODUCTS ─────────────> ORDER_ITEMS
```

`ORDERS` cần có `CUSTOMERS` trước. `ORDER_ITEMS` cần có cả `ORDERS` và `PRODUCTS` trước. Do đó, thứ tự seed hợp lệ là:

1. `CUSTOMERS`
2. `PRODUCTS`
3. `ORDERS`
4. `ORDER_ITEMS`

Thứ tự xóa dữ liệu theo dependency đảo ngược:

1. `ORDER_ITEMS`
2. `ORDERS`
3. `CUSTOMERS`
4. `PRODUCTS`

`CUSTOMERS` và `PRODUCTS` không phụ thuộc lẫn nhau nên có thể seed theo thứ tự nào trước cũng được. Điều quan trọng là tất cả parent phải tồn tại trước khi insert child.

## 5. Tạo bảng và foreign key

Ví dụ DDL:

```sql
CREATE TABLE customers (
    customer_id   NUMBER(12) CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL,
    email         VARCHAR2(320),
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE products (
    product_id   NUMBER(12) CONSTRAINT pk_products PRIMARY KEY,
    product_name VARCHAR2(200) NOT NULL,
    unit_price   NUMBER(12,2) NOT NULL,
    CONSTRAINT ck_products_price CHECK (unit_price >= 0)
);

CREATE TABLE orders (
    order_id     NUMBER(12) CONSTRAINT pk_orders PRIMARY KEY,
    customer_id  NUMBER(12) NOT NULL,
    order_date   DATE NOT NULL,
    order_status VARCHAR2(20) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id NUMBER(12) CONSTRAINT pk_order_items PRIMARY KEY,
    order_id      NUMBER(12) NOT NULL,
    product_id    NUMBER(12) NOT NULL,
    quantity      NUMBER(10) NOT NULL,
    unit_price    NUMBER(12,2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id),
    CONSTRAINT ck_items_quantity CHECK (quantity > 0)
);
```

Các constraint được đặt tên rõ ràng để test và troubleshooting dễ đọc. Tên constraint cũng giúp xác định lỗi cụ thể khi insert dữ liệu sai. Trong schema lớn, nên có quy ước tên như `PK_`, `FK_`, `UK_`, `CK_` và đặt tên không trùng trong phạm vi Oracle yêu cầu.

### 5.1. Primary key và unique key

Primary key xác định duy nhất mỗi dòng và không cho phép NULL. Unique constraint bảo đảm giá trị hoặc tổ hợp giá trị không trùng theo semantics của Oracle. Với unique key chứa NULL, cần hiểu Oracle cho phép nhiều dòng có NULL trong một số trường hợp; không nên dùng unique constraint như cách bắt buộc mọi dòng phải có giá trị. Nếu cột bắt buộc duy nhất và phải có giá trị, kết hợp `NOT NULL` với `UNIQUE`.

### 5.2. Foreign key

Foreign key bảo đảm giá trị ở child table tham chiếu đến một key hợp lệ ở parent table. Khi insert child, parent key phải tồn tại. Khi xóa parent, Oracle từ chối nếu còn child tham chiếu, trừ khi constraint có `ON DELETE CASCADE` hoặc hành vi khác được khai báo.

Ví dụ:

```sql
INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1001, 501, DATE '2026-11-01', 'NEW');
```

Lệnh này thất bại với lỗi foreign key nếu `CUSTOMERS.CUSTOMER_ID = 501` chưa tồn tại.

### 5.3. Index trên foreign key

Oracle không tự động tạo index trên foreign key chỉ vì constraint được khai báo. Index trên cột FK thường hữu ích cho join và có thể giảm locking/contention trong một số thao tác parent update/delete. Ví dụ:

```sql
CREATE INDEX ix_orders_customer_id
    ON orders(customer_id);

CREATE INDEX ix_items_order_id
    ON order_items(order_id);

CREATE INDEX ix_items_product_id
    ON order_items(product_id);
```

Không phải mọi foreign key đều cần index ngay lập tức; hãy cân nhắc workload và kích thước bảng. Nhưng với bảng child lớn hoặc parent thường xuyên delete/update key, cần đánh giá index FK.

## 6. Seed dữ liệu theo thứ tự parent-child

Seed data là dữ liệu ban đầu được nạp để test có thể chạy với một trạng thái biết trước. Dữ liệu seed nên:

- Có khóa xác định để test tham chiếu được.
- Có giá trị đủ bao phủ các trường hợp nghiệp vụ.
- Có thể nạp lặp hoặc reset được.
- Không phụ thuộc dữ liệu còn sót từ lần chạy trước.
- Không dùng thông tin cá nhân thật nếu không cần thiết.

Ví dụ seed parent trước:

```sql
INSERT INTO customers(customer_id, customer_name, email)
VALUES (501, 'Test Customer A', 'customer-a@example.test');

INSERT INTO customers(customer_id, customer_name, email)
VALUES (502, 'Test Customer B', 'customer-b@example.test');

INSERT INTO products(product_id, product_name, unit_price)
VALUES (9001, 'Test Product A', 125.50);

INSERT INTO products(product_id, product_name, unit_price)
VALUES (9002, 'Test Product B', 80.00);
```

Sau đó insert orders:

```sql
INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1001, 501, DATE '2026-11-01', 'NEW');

INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1002, 502, DATE '2026-11-02', 'PAID');
```

Cuối cùng insert order items:

```sql
INSERT INTO order_items(
    order_item_id, order_id, product_id, quantity, unit_price
)
VALUES (1, 1001, 9001, 2, 125.50);

INSERT INTO order_items(
    order_item_id, order_id, product_id, quantity, unit_price
)
VALUES (2, 1001, 9002, 1, 80.00);

INSERT INTO order_items(
    order_item_id, order_id, product_id, quantity, unit_price
)
VALUES (3, 1002, 9001, 1, 125.50);

COMMIT;
```

Commit ở cuối ví dụ làm dữ liệu seed tồn tại sau khi script hoàn tất. Nếu seed chạy trong test transaction do framework quản lý, có thể không cần commit thủ công; cần chọn một cách nhất quán.

### 6.1. Tại sao không seed child trước?

Nếu insert `ORDER_ITEMS` trước khi insert `ORDERS`, foreign key `FK_ITEMS_ORDER` không tìm thấy parent và Oracle báo `ORA-02291: integrity constraint violated - parent key not found`.

Tương tự, `ORDERS` không thể tham chiếu customer chưa tồn tại. Lỗi này không phải lỗi ngẫu nhiên của Oracle; nó là kết quả đúng của referential integrity.

### 6.2. Dữ liệu seed nên có ý nghĩa

Không nên chỉ tạo các dòng có giá trị `1`, `2`, `3` mà không liên hệ với tình huống test. Hãy chọn dữ liệu có thể diễn đạt nghiệp vụ:

| Customer | Order | Status | Items | Mục tiêu test |
|---|---|---|---|---|
| 501 | 1001 | NEW | 2 dòng | Đơn mới có nhiều sản phẩm |
| 502 | 1002 | PAID | 1 dòng | Đơn đã thanh toán |
| 501 | 1003 | CANCELLED | Không có | Đơn hủy và trường hợp không có item |

Dữ liệu có ý nghĩa giúp assertion dễ đọc và giúp phát hiện lỗi mapping hoặc join.

## 7. Tính dependency order của bảng

Trong schema có nhiều bảng, không nên tự đoán thứ tự seed. Có thể biểu diễn foreign key thành một đồ thị có hướng:

- Mỗi bảng là một node.
- Có cạnh `PARENT -> CHILD` nếu child có foreign key tham chiếu parent.
- Topological sort cho ra một thứ tự insert hợp lệ nếu đồ thị không có cycle.
- Thứ tự delete là thứ tự đảo ngược.

Ví dụ:

```text
COUNTRIES ──> CUSTOMERS ──> ORDERS ──> ORDER_ITEMS
                           ^             ^
                           |             |
PRODUCTS ──────────────────┴─────────────┘
```

Trong ví dụ, `ORDERS` tham chiếu `CUSTOMERS`, còn `ORDER_ITEMS` tham chiếu `ORDERS` và `PRODUCTS`. `COUNTRIES` có thể là parent của `CUSTOMERS`.

### 7.1. Xem foreign key trong data dictionary

`USER_CONSTRAINTS` cho biết constraint của schema hiện tại. Với foreign key, `CONSTRAINT_TYPE = 'R'`; `R_CONSTRAINT_NAME` trỏ đến constraint được tham chiếu ở parent table.

```sql
SELECT child.table_name       AS child_table,
       child.constraint_name  AS fk_name,
       parent.table_name      AS parent_table,
       child.status,
       child.deferrable,
       child.deferred
FROM user_constraints child
JOIN user_constraints parent
  ON parent.constraint_name = child.r_constraint_name
 AND parent.owner = child.r_owner
WHERE child.constraint_type = 'R'
ORDER BY parent.table_name, child.table_name;
```

Trong schema hiện tại, có thể dùng `USER_CONSTRAINTS`; nếu cần cross-schema, dùng `ALL_CONSTRAINTS` hoặc `DBA_CONSTRAINTS` với các cột owner tương ứng. Kiểm tra cả `STATUS` và `VALIDATED` để biết constraint đang enable/disable và dữ liệu hiện có đã được validate hay chưa.

### 7.2. Xem cột của foreign key

```sql
SELECT c.table_name,
       c.constraint_name,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.constraint_type = 'R'
ORDER BY c.table_name, c.constraint_name, cc.position;
```

Với composite foreign key, thứ tự cột rất quan trọng. Phải ánh xạ từng cột child với cột parent theo `POSITION`; không chỉ nhìn tên constraint.

### 7.3. Topological sort

Với đồ thị không có cycle, có thể dùng thuật toán Kahn:

1. Tính indegree của mỗi bảng bằng số parent dependency còn chưa xử lý.
2. Đưa các bảng có indegree bằng 0 vào hàng đợi.
3. Lấy một bảng ra, thêm vào insert order.
4. Với mỗi child của bảng đó, giảm indegree của child.
5. Khi indegree của child về 0, đưa child vào hàng đợi.
6. Nếu cuối cùng chưa xử lý hết node, đồ thị có cycle.

Kết quả là thứ tự seed parent trước child. Để reset bằng delete, đảo ngược thứ tự này.

Không phải mọi schema đều cần tự viết thuật toán. Với vài bảng, danh sách thứ tự trong migration/fixture là đủ. Với schema lớn hoặc test framework tự khám phá dependency, topological sort từ metadata giúp tránh bỏ sót quan hệ.

## 8. Composite foreign key và nhiều parent

Một child table có thể tham chiếu nhiều parent hoặc dùng composite key. Ví dụ:

```sql
CREATE TABLE order_allocations (
    order_id    NUMBER(12) NOT NULL,
    warehouse_id NUMBER(12) NOT NULL,
    allocation_no NUMBER(4) NOT NULL,
    CONSTRAINT pk_order_allocations
        PRIMARY KEY (order_id, warehouse_id, allocation_no),
    CONSTRAINT fk_alloc_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_alloc_warehouse
        FOREIGN KEY (warehouse_id)
        REFERENCES warehouses(warehouse_id)
);
```

Trước khi seed `ORDER_ALLOCATIONS`, phải có cả order và warehouse. Với composite foreign key, phải có parent key tương ứng đúng tổ hợp cột. Việc từng giá trị riêng lẻ tồn tại ở parent chưa đủ nếu tổ hợp không khớp.

Ví dụ:

```sql
FOREIGN KEY (country_code, region_code)
REFERENCES regions(country_code, region_code)
```

Child row phải tham chiếu một cặp `(country_code, region_code)` tồn tại. Cần seed parent với đúng tổ hợp trước.

## 9. Quan hệ vòng và foreign key deferrable

Topological sort chỉ tạo được thứ tự tuyến tính nếu dependency graph không có cycle. Một số schema có quan hệ vòng, ví dụ:

```text
EMPLOYEES.manager_id -> EMPLOYEES.employee_id
DEPARTMENTS.manager_id -> EMPLOYEES.employee_id
EMPLOYEES.department_id -> DEPARTMENTS.department_id
```

Ở đây employee thuộc department, department có manager là employee, và employee có thể tham chiếu manager khác. Nếu các cột đều `NOT NULL` và foreign key immediate, việc seed có thể không có thứ tự insert hợp lệ.

### 9.1. Insert NULL trước rồi UPDATE

Nếu nghiệp vụ cho phép cột tham chiếu ban đầu là NULL, có thể tạo parent trước rồi cập nhật quan hệ sau:

```sql
INSERT INTO employees(employee_id, department_id, manager_id, employee_name)
VALUES (10, 100, NULL, 'Manager A');

INSERT INTO departments(department_id, department_name, manager_id)
VALUES (100, 'Engineering', 10);

INSERT INTO employees(employee_id, department_id, manager_id, employee_name)
VALUES (11, 100, 10, 'Developer B');
```

Đây thường là cách dễ hiểu nếu `MANAGER_ID` được phép NULL trong giai đoạn tạo dữ liệu. Sau đó update khi cả hai phía đã tồn tại.

### 9.2. DEFERRABLE constraint

Oracle hỗ trợ constraint `DEFERRABLE`, cho phép trì hoãn kiểm tra đến cuối transaction nếu constraint được đặt ở trạng thái deferred.

Ví dụ:

```sql
CREATE TABLE departments (
    department_id NUMBER(12) PRIMARY KEY,
    manager_id    NUMBER(12),
    department_name VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_department_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Và constraint tham chiếu ngược:

```sql
CREATE TABLE employees (
    employee_id   NUMBER(12) PRIMARY KEY,
    department_id NUMBER(12) NOT NULL,
    manager_id    NUMBER(12),
    employee_name VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Ví dụ DDL này chỉ minh họa khả năng trì hoãn; trong schema thực tế cần tạo object theo thứ tự phù hợp để tham chiếu object đã tồn tại, hoặc thêm constraint bằng `ALTER TABLE` sau khi tạo cả hai bảng.

Trong transaction:

```sql
SET CONSTRAINTS ALL DEFERRED;

INSERT INTO departments(department_id, manager_id, department_name)
VALUES (100, 10, 'Engineering');

INSERT INTO employees(employee_id, department_id, manager_id, employee_name)
VALUES (10, 100, NULL, 'Manager A');

COMMIT;
```

Các foreign key được kiểm tra khi commit. Nếu đến cuối transaction vẫn không thỏa, commit thất bại. `SET CONSTRAINTS` chỉ có tác dụng với constraint được khai báo `DEFERRABLE`; constraint `NOT DEFERRABLE` không thể chuyển sang deferred.

### 9.3. INITIALLY IMMEDIATE và INITIALLY DEFERRED

- `DEFERRABLE INITIALLY IMMEDIATE`: mặc định kiểm tra ngay, nhưng transaction có thể chuyển sang deferred.
- `DEFERRABLE INITIALLY DEFERRED`: mặc định kiểm tra khi commit.
- `NOT DEFERRABLE`: luôn kiểm tra theo cơ chế immediate và không thể defer.

Deferrable constraint có thể hữu ích cho import/test dữ liệu có quan hệ vòng, nhưng không nên dùng chỉ để che một thứ tự seed chưa được thiết kế. Nó thay đổi thời điểm phát hiện lỗi: câu INSERT có thể thành công nhưng commit mới thất bại.

### 9.4. Tạm disable constraint

Oracle cho phép disable constraint:

```sql
ALTER TABLE order_items
DISABLE CONSTRAINT fk_items_order;
```

Sau khi nạp dữ liệu, bật lại và validate:

```sql
ALTER TABLE order_items
ENABLE VALIDATE CONSTRAINT fk_items_order;
```

`ENABLE VALIDATE` xác nhận toàn bộ dữ liệu hiện có thỏa constraint. Nếu dữ liệu sai, lệnh enable validate thất bại. Có trạng thái `ENABLE NOVALIDATE` cho một số kịch bản chuyển đổi, nhưng khi đó dữ liệu cũ có thể chưa được kiểm tra. Test chuẩn nên ưu tiên constraint enable/validated để phát hiện lỗi tham chiếu sớm.

Không nên tắt foreign key trong mọi lần seed. Điều đó làm mất một lớp kiểm tra quan trọng và có thể khiến test pass với dữ liệu mà production không chấp nhận.

## 10. Sequence và identity khi seed dữ liệu

Nhiều bảng Oracle dùng sequence hoặc identity column để sinh khóa. Test cần quyết định dùng ID cố định hay ID do database sinh.

### 10.1. Seed ID cố định

Để fixture dễ đọc, có thể insert ID xác định nếu cột là cột số thông thường:

```sql
INSERT INTO customers(customer_id, customer_name)
VALUES (501, 'Test Customer A');
```

ID cố định giúp test tham chiếu dữ liệu dễ dàng. Nhưng nếu production schema dùng sequence, cần tránh xung đột giữa ID seed và giá trị sequence tiếp theo.

Ví dụ sequence:

```sql
CREATE SEQUENCE customer_seq START WITH 1000 INCREMENT BY 1 CACHE 20;
```

Nếu seed thủ công `CUSTOMER_ID = 501`, sequence bắt đầu từ 1000 sẽ không đụng ID đó. Khi seed ID lớn hơn sequence next value, cần đồng bộ sequence hoặc dùng cơ chế seed khác.

### 10.2. Lấy ID từ sequence

```sql
INSERT INTO customers(customer_id, customer_name)
VALUES (customer_seq.NEXTVAL, 'Generated Customer');
```

Trong ứng dụng Java, có thể lấy `NEXTVAL` bằng `JdbcTemplate` hoặc dùng sequence trong INSERT. Không nên dựa vào giá trị sequence liên tiếp hoặc không có gap. Rollback transaction không trả lại sequence value đã cấp.

### 10.3. Identity column

Oracle hỗ trợ identity column ở các phiên bản hiện đại:

```sql
CREATE TABLE test_events (
    event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(100) NOT NULL
);
```

`GENERATED ALWAYS AS IDENTITY` yêu cầu database tự sinh giá trị và không cho insert giá trị tùy ý theo cách thông thường. `GENERATED BY DEFAULT` cho phép cung cấp giá trị tường minh khi insert; `BY DEFAULT ON NULL` có semantics riêng khi giá trị đưa vào là NULL.

Nếu test cần ID cố định, chọn identity mode phù hợp hoặc dùng bảng/sequence fixture được thiết kế riêng. Cú pháp thay đổi identity restart phụ thuộc phiên bản Oracle; không nên dùng một câu `ALTER TABLE ... RESTART` giả định cho mọi release. Trong schema test dùng riêng, drop/recreate object hoặc sequence theo quy trình phù hợp thường dễ kiểm soát hơn.

### 10.4. Sequence không reset bằng DELETE

Xóa hết dòng trong bảng không làm sequence quay lại giá trị ban đầu. Sequence là object độc lập và có cache/metadata riêng. Nếu test yêu cầu sequence bắt đầu từ một giá trị cụ thể, phải reset sequence bằng cách được hỗ trợ cho version hoặc drop/recreate trong môi trường test riêng.

Không reset sequence trong khi ứng dụng hoặc test khác đang sử dụng cùng schema. Có thể gây duplicate key hoặc làm các test chạy song song ảnh hưởng nhau.

## 11. Thiết kế seed script lặp lại được

Seed script thường cần chạy trong nhiều ngữ cảnh: dựng môi trường mới, refresh local database, integration test hoặc CI. Nên xác định rõ script nào chỉ chạy một lần và script nào có thể chạy lại.

### 11.1. Insert thuần cho schema sạch

Nếu mỗi lần test tạo schema mới, `INSERT` thuần với khóa cố định là đơn giản và dễ phát hiện duplicate ngoài dự kiến:

```sql
INSERT INTO products(product_id, product_name, unit_price)
VALUES (9001, 'Test Product A', 125.50);
```

Nếu chạy hai lần trên cùng schema, lần thứ hai sẽ vi phạm primary key. Đây có thể là hành vi tốt vì phát hiện reset không hoàn tất.

### 11.2. MERGE cho reference data cần idempotent

Với dữ liệu tham chiếu cần được đảm bảo tồn tại sau mỗi lần bootstrap, `MERGE` có thể làm seed lặp lại:

```sql
MERGE INTO app_test.order_statuses t
USING (
    SELECT 'NEW' AS status_code, 'New order' AS status_name FROM dual
    UNION ALL
    SELECT 'PAID', 'Paid order' FROM dual
    UNION ALL
    SELECT 'CANCELLED', 'Cancelled order' FROM dual
) s
ON (t.status_code = s.status_code)
WHEN MATCHED THEN
    UPDATE SET t.status_name = s.status_name
WHEN NOT MATCHED THEN
    INSERT (status_code, status_name)
    VALUES (s.status_code, s.status_name);
```

`MERGE` giúp seed reference data ổn định, nhưng cần xác định có muốn update giá trị đã tồn tại hay không. Với dữ liệu fixture của test, cập nhật row có thể che trạng thái cũ; schema reset sạch thường dễ hiểu hơn.

### 11.3. Dùng SQL*Plus/SQLcl script

Một script bootstrap có thể gọi các file theo thứ tự:

```sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

PROMPT Seeding customers and products
@seed/01_customers.sql
@seed/02_products.sql
PROMPT Seeding orders
@seed/03_orders.sql
PROMPT Seeding order items
@seed/04_order_items.sql

COMMIT;
PROMPT Seed completed
EXIT SUCCESS
```

`WHENEVER SQLERROR` giúp script dừng khi gặp lỗi SQL. Nhưng nó không hoàn tác DDL đã implicit commit trước đó. Nên tách migration DDL khỏi seed DML và xác định rõ transaction boundary.

## 12. Seed dữ liệu bằng Java/Spring Boot

Ngoài SQL script, test có thể nạp fixture bằng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`. Cách này hữu ích khi dữ liệu được xây dựng từ test object hoặc cần kiểm tra kết quả ngay trong Java.

### 12.1. Seed theo thứ tự rõ ràng

```java
@Component
public class OrderTestDataSeeder {

    private final JdbcTemplate jdbc;

    public OrderTestDataSeeder(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void seed() {
        jdbc.update("""
            INSERT INTO customers(customer_id, customer_name, email)
            VALUES (?, ?, ?)
            """, 501L, "Test Customer A", "customer-a@example.test");

        jdbc.update("""
            INSERT INTO products(product_id, product_name, unit_price)
            VALUES (?, ?, ?)
            """, 9001L, "Test Product A", new BigDecimal("125.50"));

        jdbc.update("""
            INSERT INTO orders(order_id, customer_id, order_date, order_status)
            VALUES (?, ?, ?, ?)
            """, 1001L, 501L,
                Timestamp.valueOf(LocalDateTime.of(2026, 11, 1, 10, 0)), "NEW");

        jdbc.update("""
            INSERT INTO order_items(
                order_item_id, order_id, product_id, quantity, unit_price
            ) VALUES (?, ?, ?, ?, ?)
            """, 1L, 1001L, 9001L, 2,
                new BigDecimal("125.50"));
    }
}
```

Thứ tự lệnh phản ánh dependency. Dữ liệu số tiền dùng `BigDecimal` để giữ precision. Oracle `DATE` chứa cả phần thời gian đến giây; khi dùng timestamp Java, cần xác nhận JDBC mapping đúng với kiểu cột.

### 12.2. Tách fixture khỏi production startup

Không nên tự động nạp test fixture khi ứng dụng production khởi động. Dùng profile riêng như `test`, `@TestConfiguration`, SQL test resources hoặc test framework annotation. Tránh component seeder được bật nhầm ở production.

### 12.3. @Sql trong Spring Test

Spring Test hỗ trợ `@Sql` để chạy script trước/sau test:

```java
@SpringBootTest
@Sql(
    scripts = {
        "/db/test/cleanup.sql",
        "/db/test/seed.sql"
    },
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderRepositoryIT {
    // tests
}
```

`cleanup.sql` cần xóa child trước parent. Nếu test method chạy trong transaction do Spring Test quản lý, script và test có thể tham gia transaction theo cấu hình. Cần kiểm tra transaction mode và execution phase để tránh nghĩ rằng DML đã commit trong khi thực tế sẽ rollback sau test.

### 12.4. Test transaction và commit thật

Spring Test thường rollback transaction của test sau khi method kết thúc nếu test được chạy transactional. Đây là cách nhanh để cô lập DML. Nhưng một số tình huống cần kiểm tra hành vi commit thật, ví dụ:

- Transaction boundary giữa nhiều service call.
- Trigger hoặc job chỉ hoạt động sau commit.
- Visibility của dữ liệu từ connection khác.
- Lock và isolation behavior.
- Outbox hoặc event được phát sau commit.

Trong các test đó, cần cấu hình transaction rõ ràng, có thể dùng `@Commit` hoặc `@Rollback(false)` khi phù hợp và tự cleanup sau test. Không nên bật commit cho toàn bộ test suite một cách tùy tiện.

## 13. Reset dữ liệu theo thứ tự dependency

Khi test dùng chung schema, cleanup phải đảo ngược thứ tự insert. Với ví dụ bán hàng:

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
DELETE FROM products;
COMMIT;
```

Nếu `ORDER_ITEMS` tham chiếu cả `ORDERS` và `PRODUCTS`, phải xóa `ORDER_ITEMS` trước cả hai parent. Sau đó xóa `ORDERS` trước `CUSTOMERS`.

### 13.1. Cleanup nhiều bảng

Với schema lớn, nên lưu dependency order trong script hoặc công cụ fixture. Không nên xóa parent rồi bắt lỗi FK và tiếp tục. Lỗi cleanup cần làm test setup fail để tránh chạy trên trạng thái dữ liệu không rõ.

### 13.2. ON DELETE CASCADE

Nếu foreign key được khai báo `ON DELETE CASCADE`, xóa parent có thể tự xóa child liên quan:

```sql
CONSTRAINT fk_items_order
    FOREIGN KEY (order_id)
    REFERENCES orders(order_id)
    ON DELETE CASCADE
```

Điều này có thể đơn giản hóa cleanup nhưng là một quyết định nghiệp vụ/schema, không nên thêm chỉ để test dễ hơn. Cascade có thể xóa nhiều dòng ngoài dự kiến nếu fixture tham chiếu rộng. Hãy kiểm tra số dòng bị ảnh hưởng và chỉ dùng khi semantics phù hợp.

### 13.3. TRUNCATE và foreign key

Truncate không có semantics cascade giống delete cascade thông thường. Parent table đang bị tham chiếu có thể không truncate được. Thực tế thường truncate child trước, rồi mới parent; hoặc drop/recreate schema trong môi trường test riêng.

Không dùng `TRUNCATE` nếu cần trigger delete chạy hoặc cần rollback. `TRUNCATE` không tạo row-by-row delete trigger như `DELETE`.

## 14. Kiểm tra foreign key và dữ liệu seed

Sau khi seed, nên xác nhận dữ liệu tham chiếu hợp lệ và constraint đang enable/validated.

### 14.1. Kiểm tra constraint status

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred
FROM user_constraints
WHERE constraint_type IN ('P', 'U', 'R')
ORDER BY table_name, constraint_type, constraint_name;
```

`STATUS = ENABLED` cho biết constraint đang bật. `VALIDATED = VALIDATED` cho biết dữ liệu hiện có đã được kiểm tra theo constraint. Với test schema mới, thông thường muốn các constraint cần thiết ở trạng thái `ENABLED` và `VALIDATED`.

### 14.2. Tìm child row mồ côi

Ví dụ kiểm tra order không có customer tương ứng:

```sql
SELECT o.order_id,
       o.customer_id
FROM orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM customers c
    WHERE c.customer_id = o.customer_id
);
```

Nếu foreign key được enable/validated, truy vấn này phải không trả dòng. Nếu trả dòng, cần kiểm tra constraint có bị disable/novalidate hoặc dữ liệu được nạp bằng đường khác không.

### 14.3. Đối soát số lượng seed

```sql
SELECT 'CUSTOMERS' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'PRODUCTS', COUNT(*) FROM products
UNION ALL
SELECT 'ORDERS', COUNT(*) FROM orders
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*) FROM order_items;
```

Trong test, nên kiểm tra số lượng fixture dự kiến và các key quan trọng. Đừng chỉ xác nhận script không ném lỗi; một script có thể chạy thành công nhưng nạp thiếu file hoặc bỏ qua một phần fixture.

## 15. Dữ liệu seed deterministic và test song song

Deterministic seed nghĩa là cùng một setup tạo ra cùng dữ liệu logic và khóa tham chiếu. Điều này giúp test tái lập được.

### 15.1. Tránh dữ liệu phụ thuộc thời điểm hiện tại

Nếu fixture dùng `SYSDATE` hoặc `SYSTIMESTAMP`, kết quả có thể thay đổi giữa lần chạy. Điều này đôi khi cần thiết để test logic “hiện tại”, nhưng nên truyền clock hoặc dùng ngày cố định trong fixture cho test thông thường.

Ví dụ:

```sql
INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1001, 501, DATE '2026-11-01', 'NEW');
```

Literal ANSI `DATE 'YYYY-MM-DD'` không phụ thuộc `NLS_DATE_FORMAT`. Với timestamp có fractional seconds, dùng `TIMESTAMP 'YYYY-MM-DD HH24:MI:SS.FF'` theo cú pháp literal phù hợp.

### 15.2. Không phụ thuộc sequence value liên tiếp

Sequence có thể cache và có gap. Test không nên giả định lần gọi thứ nhất luôn trả 1 hoặc lần gọi thứ hai luôn trả 2. Nếu cần kiểm tra, hãy lấy giá trị được trả về và dùng nó trong các thao tác tiếp theo.

### 15.3. Test chạy song song cần schema/database cô lập

Hai test suite cùng xóa và seed một schema sẽ làm hỏng dữ liệu của nhau. Ví dụ test A đang đọc `ORDERS` trong khi test B chạy cleanup `DELETE FROM ORDERS`. Kết quả phụ thuộc thời điểm và rất khó tái lập.

Các lựa chọn:

- Mỗi worker CI có schema riêng.
- Mỗi test suite có PDB/container database riêng.
- Dùng tenant/test key riêng và mọi query/cleanup đều giới hạn theo key.
- Tuần tự hóa test có quyền reset schema chung nếu không thể cô lập.

Chỉ thêm `@DirtiesContext` không tự tạo database isolation; nó làm mới Spring ApplicationContext, không đảm bảo schema Oracle được reset riêng.

## 16. Kiểm thử bằng container hoặc database test chuyên dụng

Oracle có thể chạy trong môi trường container được hỗ trợ hoặc dùng database test riêng do tổ chức cung cấp. Với Oracle, cần dùng image/edition và điều khoản sử dụng phù hợp; không giả định image database bất kỳ đều được phép dùng trong mọi môi trường.

Testcontainers có thể giúp khởi tạo database phụ thuộc test và hủy sau khi suite kết thúc. Tuy nhiên, thời gian khởi động, dung lượng image, license/terms và cấu hình Oracle version cần được cân nhắc.

Một chiến lược phổ biến:

1. Khởi tạo Oracle test database/PDB.
2. Chạy Flyway/Liquibase migration.
3. Chạy seed script.
4. Thực hiện integration test.
5. Hủy database/container sau khi hoàn tất.

Ưu điểm là mỗi run có baseline độc lập. Nhược điểm là tốn tài nguyên và thời gian hơn dùng một schema dùng chung.

## 17. Dựng lại schema trong CI/CD

CI nên thực hiện một pipeline có thể tái lập:

```text
Provision test database/schema
          |
          v
Create user and grants
          |
          v
Run versioned migrations
          |
          v
Load deterministic seed
          |
          v
Run integration tests
          |
          v
Collect logs and test results
          |
          v
Drop schema / destroy test database
```

### 17.1. Fail-fast trước reset

Trước lệnh reset, script nên kiểm tra:

- JDBC URL/service/PDB đúng test environment.
- Database unique name hoặc marker test đúng allowlist.
- User schema nằm trong danh sách được phép reset.
- CI run ID hoặc worker ID được gắn vào schema nếu chạy song song.
- Credential là test credential.

Nếu một điều kiện không đúng, dừng pipeline trước khi thực hiện DDL phá hủy.

### 17.2. Log và đối soát

Lưu log của migration, seed, cleanup và test. Khi thất bại, cần biết script nào đã chạy, migration nào thành công, seed đã commit chưa và schema còn ở trạng thái nào.

Không chỉ lưu một dòng “database setup failed”. Hãy giữ SQL error code, tên script, migration version và test run ID, nhưng tránh ghi credential hoặc dữ liệu nhạy cảm.

## 18. Các lỗi thường gặp khi dựng schema và seed

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ORA-01031: insufficient privileges` | User thiếu system/object privilege để tạo object hoặc chạy migration | Xác định DDL cần quyền nào; cấp tối thiểu cho schema owner |
| `ORA-01950: no privileges on tablespace` | Schema không có quota trên tablespace | Cấp quota phù hợp hoặc chọn tablespace đúng |
| `ORA-00955: name is already used by an existing object` | Reset không xóa object cũ hoặc migration chạy lặp | Kiểm tra object và migration history; không drop tùy tiện |
| `ORA-02291: parent key not found` | Seed child trước parent hoặc parent key sai | Sửa dependency order và khóa tham chiếu |
| `ORA-02292: child record found` | Xóa parent khi vẫn còn child | Cleanup theo thứ tự child trước parent hoặc semantics cascade phù hợp |
| `ORA-00001: unique constraint violated` | Seed trùng key hoặc script chạy lại | Reset đúng cách, dùng MERGE có chủ đích hoặc ID fixture riêng |
| `ORA-02266`/lỗi truncate do FK | Parent bị tham chiếu bởi foreign key | Truncate child trước hoặc dùng chiến lược reset khác |
| Commit nhưng test vẫn không thấy dữ liệu | Test dùng DataSource/schema/PDB khác hoặc transaction visibility | Kiểm tra connection URL, schema, transaction và service |
| Test chạy riêng pass nhưng suite fail | Dữ liệu rò rỉ giữa test hoặc thứ tự chạy ảnh hưởng | Cô lập schema, cleanup và loại phụ thuộc thứ tự |
| Sequence sinh trùng ID fixture | Sequence next value thấp hơn ID đã seed | Đồng bộ sequence hoặc tách ID fixture khỏi sequence range |
| Test song song fail ngẫu nhiên | Nhiều worker cùng reset schema | Mỗi worker dùng schema/PDB riêng hoặc tuần tự hóa |
| Rollback không phục hồi schema | DDL/Truncate đã implicit commit | Dựng lại schema từ migration; không dựa vào rollback DDL |

## 19. Một bộ script mẫu cho schema test

Một thư mục test database có thể được tổ chức:

```text
src/test/resources/db/oracle/
  migration/
    V001__create_customers.sql
    V002__create_products.sql
    V003__create_orders.sql
    V004__create_order_items.sql
  seed/
    01_customers.sql
    02_products.sql
    03_orders.sql
    04_order_items.sql
  cleanup/
    01_order_items.sql
    02_orders.sql
    03_customers.sql
    04_products.sql
```

Migration chạy parent trước child. Seed cũng theo thứ tự parent trước child. Cleanup theo thứ tự child trước parent.

### 19.1. Seed script có transaction rõ ràng

Ví dụ `seed/01_customers.sql`:

```sql
INSERT INTO customers(customer_id, customer_name, email)
VALUES (501, 'Test Customer A', 'customer-a@example.test');

INSERT INTO customers(customer_id, customer_name, email)
VALUES (502, 'Test Customer B', 'customer-b@example.test');
```

Các script seed tiếp theo insert products, orders và order_items. Script điều phối có thể commit sau khi tất cả seed hoàn tất. Nếu một file seed lỗi trước commit, DML trước đó có thể rollback nếu không có DDL hoặc thao tác commit ngầm xen giữa.

### 19.2. Cleanup script

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
DELETE FROM products;
COMMIT;
```

Nếu dùng `TRUNCATE`, thay đổi là DDL và không thể rollback. Chỉ dùng khi test schema riêng và đã xác nhận thứ tự/constraint.

### 19.3. Xác nhận fixture

```sql
DECLARE
    l_customers NUMBER;
    l_products  NUMBER;
    l_orders    NUMBER;
    l_items     NUMBER;
BEGIN
    SELECT COUNT(*) INTO l_customers FROM customers;
    SELECT COUNT(*) INTO l_products FROM products;
    SELECT COUNT(*) INTO l_orders FROM orders;
    SELECT COUNT(*) INTO l_items FROM order_items;

    IF l_customers <> 2 OR l_products <> 2
       OR l_orders <> 2 OR l_items <> 3 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Unexpected seed row counts');
    END IF;
END;
/
```

Đây là assertion ở mức setup. Test nghiệp vụ vẫn cần kiểm tra kết quả truy vấn và hành vi ứng dụng, không chỉ số lượng dòng.

## 20. Nguyên tắc reset và seed đáng tin cậy

Một môi trường test tốt nên tuân thủ các nguyên tắc:

1. **Cô lập:** test không dùng schema hoặc database production.
2. **Tái lập:** migration và seed có thể chạy từ trạng thái sạch.
3. **Có thứ tự:** object được tạo theo dependency; parent data được seed trước child.
4. **Cleanup đảo chiều:** xóa child trước parent.
5. **Deterministic:** khóa, ngày và dữ liệu fixture được kiểm soát.
6. **Constraint luôn có hiệu lực:** không tắt FK chỉ để seed dễ hơn nếu không có lý do đặc biệt.
7. **Transaction rõ ràng:** hiểu DML rollback được, còn DDL/Truncate có implicit commit.
8. **Sequence riêng:** không giả định sequence không có gap hoặc tự reset theo bảng.
9. **Cô lập song song:** mỗi worker có schema/database riêng hoặc cơ chế khóa/partition dữ liệu.
10. **Kiểm tra đúng user:** test quyền bằng runtime account, không chỉ bằng DBA.
11. **Đối soát:** xác nhận row count, khóa và constraint sau seed.
12. **Có thể điều tra:** log rõ migration, seed batch, database identity và lỗi Oracle.

## 21. Checklist trước khi chạy integration test

| Hạng mục | Câu hỏi |
|---|---|
| Database identity | JDBC URL, service, PDB và DB unique name có đúng test environment không? |
| Schema | User test đã tồn tại, quota và default tablespace phù hợp chưa? |
| Privileges | Schema owner có đúng quyền tạo object; runtime user có đúng object privilege không? |
| Migration | Schema version đã ở trạng thái mong muốn chưa? |
| Dependency | Bảng parent được tạo trước child và object phụ thuộc được tạo sau object nền chưa? |
| Seed | Parent rows có trước child rows; khóa tham chiếu có đúng không? |
| Constraint | PK/FK/UK/CHECK có enable và validate không? |
| Sequence | Sequence/identity có thể xung đột với ID fixture không? |
| Reset | Cleanup có child-first; có DDL implicit commit nào cần lưu ý không? |
| Transaction | Test rollback hay commit; script seed có tham gia transaction không? |
| Parallelism | Test worker có dùng chung schema và xóa dữ liệu của nhau không? |
| Security | Password/secret có nằm ngoài source control; reset có giới hạn đúng schema không? |
| Evidence | Có log migration, seed, row counts và SQL error khi thất bại không? |

Tạo và reset schema đúng cách giúp test Oracle bắt đầu từ trạng thái đã biết. Seed dữ liệu theo dependency bảo đảm các foreign key luôn tham chiếu đến parent tồn tại, còn cleanup theo thứ tự ngược giúp xóa dữ liệu mà không vi phạm referential integrity. Khi kết hợp migration có phiên bản, fixture deterministic, schema cô lập và hiểu rõ implicit commit của DDL, integration test sẽ dễ tái lập, ít phụ thuộc thứ tự chạy và phản ánh gần hơn cách ứng dụng hoạt động trên Oracle thực tế.
