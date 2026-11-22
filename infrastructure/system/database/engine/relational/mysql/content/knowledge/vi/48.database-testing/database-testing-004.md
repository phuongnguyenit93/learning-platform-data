# Tạo/reset schema, seed dữ liệu và thứ tự khóa ngoại

Một bài kiểm thử MySQL đáng tin cậy cần bắt đầu từ schema có thể tái tạo, dữ liệu đầu vào có thể dự đoán và trạng thái database được dọn sạch sau khi chạy. Nếu test dùng chung một schema lâu ngày, dữ liệu cũ có thể làm test lúc pass lúc fail; nếu seed sai thứ tự khóa ngoại, lệnh insert sẽ thất bại; nếu reset bằng cách bỏ qua kiểm tra foreign key, database có thể chứa dữ liệu mồ côi mà test không phát hiện.

Bài học này trình bày cách tạo schema kiểm thử, áp dụng migration, seed dữ liệu xác định, sắp xếp thao tác theo quan hệ khóa ngoại và reset database an toàn. Ví dụ dùng MySQL/InnoDB. Các câu lệnh phá hủy schema chỉ nên chạy trên database kiểm thử được cô lập và có tên rõ ràng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Tạo schema kiểm thử với charset, collation và cấu hình tương tự môi trường cần kiểm thử.
- Dùng migration để dựng schema từ trạng thái rỗng.
- Chọn cách reset phù hợp: tạo lại schema, rollback transaction hoặc xóa dữ liệu theo thứ tự phụ thuộc.
- Seed dữ liệu xác định và có thể tái tạo.
- Sắp xếp insert theo thứ tự cha trước con, cleanup theo thứ tự con trước cha.
- Xử lý quan hệ tự tham chiếu, chu trình khóa ngoại và dữ liệu bulk import.
- Hiểu giới hạn của `FOREIGN_KEY_CHECKS`, `TRUNCATE` và transaction trong MySQL.
- Cô lập dữ liệu giữa các test chạy song song.

## 1. Schema kiểm thử phải được cô lập

Không nên chạy test phá hủy trên schema đang chứa dữ liệu dùng chung của developer hoặc môi trường khác. Tạo schema riêng, tên thể hiện rõ mục đích và môi trường:

```sql
CREATE DATABASE mysql_app_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

`utf8mb4_0900_ai_ci` là collation phổ biến trên MySQL 8.0. Nếu ứng dụng production dùng collation khác, hãy dùng đúng collation đó để test phản ánh quy tắc so sánh, sắp xếp và unique index thực tế. Không chọn collation chỉ vì nó là mặc định trên máy phát triển.

Sau khi tạo schema, cấu hình test connection trỏ đúng database:

```text
jdbc:mysql://localhost:3306/mysql_app_test
```

Tài khoản test chỉ nên có quyền trên schema kiểm thử. Tài khoản chạy migration có thể cần quyền DDL; tài khoản chạy test nghiệp vụ chỉ cần quyền DML phù hợp. Tách hai vai trò giúp test không vô tình dùng quyền quản trị rộng.

### 1.1. Một schema cho suite hay một schema cho từng test?

Có một số chiến lược cô lập:

| Chiến lược | Cách dùng | Phù hợp khi |
|---|---|---|
| Schema mới cho mỗi test suite | Drop/create schema trước suite, chạy migration, seed fixture | Muốn test bắt đầu từ trạng thái sạch và cần kiểm thử migration |
| Schema riêng cho mỗi test class/worker | Mỗi nhóm test có database riêng | Test chạy song song hoặc có dữ liệu phá hủy lẫn nhau |
| Transaction rollback cho mỗi test | Mở transaction, seed và chạy test, rollback cuối test | Test chỉ thay đổi dữ liệu transactional và dùng cùng connection/transaction |
| Delete/truncate dữ liệu sau test | Xóa fixture hoặc toàn bộ bảng theo thứ tự phụ thuộc | Cần tái sử dụng schema và reset nhanh |

Với test migration, schema mới từ đầu thường là lựa chọn rõ ràng nhất: chạy toàn bộ migration lên database rỗng rồi xác minh schema. Với test repository/service, có thể dùng transaction rollback nếu mọi thao tác nằm trong cùng transaction và không có side effect bên ngoài.

Không để nhiều test worker cùng drop, truncate hoặc seed một schema dùng chung. Nếu cần chạy song song, tạo schema riêng theo worker hoặc database container riêng.

## 2. Dựng schema bằng migration

Schema test nên được tạo bằng cùng migration mà ứng dụng dùng khi triển khai, chẳng hạn Flyway hoặc Liquibase. Không duy trì một bộ `CREATE TABLE` riêng chỉ dành cho test vì hai bộ schema có thể lệch nhau theo thời gian.

Ví dụ migration tạo ba bảng có quan hệ khóa ngoại:

```sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(255) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  order_number VARCHAR(40) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_orders_order_number (order_number),
  KEY idx_orders_customer_id (customer_id),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id BIGINT UNSIGNED NOT NULL,
  sku VARCHAR(60) NOT NULL,
  quantity INT UNSIGNED NOT NULL,
  unit_price DECIMAL(12, 2) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_order_items_order_id (order_id),
  CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id) REFERENCES orders (id)
) ENGINE = InnoDB;
```

Quan hệ là:

```text
customers
    |
    | customers.id <- orders.customer_id
    v
  orders
    |
    | orders.id <- order_items.order_id
    v
order_items
```

`orders` là bảng con của `customers`; `order_items` là bảng con của `orders`. Khi insert dữ liệu, cần có customer trước order, và order trước order item. Khi xóa dữ liệu, thực hiện theo chiều ngược lại.

### 2.1. Vì sao dùng InnoDB?

InnoDB hỗ trợ transaction và foreign key. Test nghiệp vụ cần kiểm tra đúng hành vi của engine production; nếu test bằng engine khác hoặc H2, các quy tắc khóa, constraint, collation và SQL có thể khác MySQL.

Kiểm tra engine và constraint sau migration:

```sql
SHOW TABLE STATUS FROM mysql_app_test;
SHOW CREATE TABLE mysql_app_test.orders\G
```

Integration test nên dùng MySQL cùng major version và cấu hình gần production, chẳng hạn qua container MySQL. Việc chỉ kiểm tra trên H2 không đủ để chứng minh migration hoặc foreign key hoạt động giống MySQL.

## 3. Xác định thứ tự khóa ngoại

### 3.1. Insert theo thứ tự cha trước con

Một hàng ở bảng con chỉ có thể tham chiếu tới hàng cha đã tồn tại khi foreign key được kiểm tra. Với ví dụ trên, thứ tự seed đúng là:

1. `customers`
2. `orders`
3. `order_items`

Seed dữ liệu có ID và giá trị cố định giúp test dễ dự đoán:

```sql
INSERT INTO customers (id, email, display_name)
VALUES
  (1001, 'an@example.test', 'An Nguyen'),
  (1002, 'binh@example.test', 'Binh Tran');

INSERT INTO orders (id, customer_id, order_number, created_at)
VALUES
  (2001, 1001, 'TEST-ORDER-001', '2025-01-10 09:00:00'),
  (2002, 1002, 'TEST-ORDER-002', '2025-01-10 10:00:00');

INSERT INTO order_items (id, order_id, sku, quantity, unit_price)
VALUES
  (3001, 2001, 'SKU-RED-01', 2, 19.90),
  (3002, 2001, 'SKU-BLUE-02', 1, 29.50),
  (3003, 2002, 'SKU-GREEN-03', 3, 12.00);
```

Các ID cố định giúp test tham chiếu fixture rõ ràng, ví dụ kiểm tra order `2001` thuộc customer `1001`. Chỉ dùng ID cố định trong schema test đã cô lập; không seed ID dễ xung đột vào dữ liệu dùng chung.

### 3.2. Xây dựng thứ tự từ đồ thị phụ thuộc

Với nhiều bảng, không nên sắp thứ tự theo tên bảng hoặc theo thứ tự file. Hãy mô hình hóa quan hệ foreign key thành đồ thị có hướng:

- Mỗi bảng là một node.
- Có cạnh từ bảng cha tới bảng con nếu bảng con tham chiếu bảng cha.
- Thứ tự topological của đồ thị là thứ tự insert hợp lệ.
- Cleanup theo thứ tự ngược lại.

Ví dụ một hệ thống có `departments`, `employees`, `projects` và `employee_projects`:

```text
departments -----> employees
      |                |
      v                v
   projects ------> employee_projects
```

Nếu `employees.department_id` tham chiếu `departments.id`, `projects.department_id` tham chiếu `departments.id`, và `employee_projects` tham chiếu cả employee lẫn project, thì seed theo thứ tự `departments`, rồi `employees`/`projects`, cuối cùng `employee_projects`.

Có thể truy vấn metadata foreign key để lập danh sách phụ thuộc:

```sql
SELECT
  TABLE_NAME AS child_table,
  COLUMN_NAME AS child_column,
  REFERENCED_TABLE_NAME AS parent_table,
  REFERENCED_COLUMN_NAME AS parent_column,
  CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'mysql_app_test'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY REFERENCED_TABLE_NAME, TABLE_NAME, CONSTRAINT_NAME;
```

Kết quả cho biết bảng con, cột tham chiếu và bảng cha. Dùng danh sách này để xây thứ tự seed/cleanup hoặc phát hiện quan hệ mà fixture cần cung cấp.

### 3.3. Cleanup theo thứ tự con trước cha

Với các bảng ở ví dụ, thứ tự xóa đúng là `order_items`, `orders`, `customers`:

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
```

Nếu xóa customer trước khi xóa order tham chiếu, MySQL sẽ từ chối thao tác theo foreign key mặc định. Có thể dùng `ON DELETE CASCADE` nếu đó là quy tắc nghiệp vụ thực sự, nhưng không nên thêm cascade chỉ để làm test cleanup ngắn hơn.

Nếu quan hệ có nhiều nhánh, cleanup theo thứ tự topological đảo ngược. Bảng con sâu nhất được xóa trước, bảng cha gốc được xóa cuối cùng.

## 4. Quan hệ tự tham chiếu và chu trình khóa ngoại

### 4.1. Bảng tự tham chiếu

Một bảng có thể tham chiếu chính nó, ví dụ cây danh mục:

```sql
CREATE TABLE categories (
  id BIGINT UNSIGNED NOT NULL,
  parent_id BIGINT UNSIGNED NULL,
  category_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_categories_parent (parent_id),
  CONSTRAINT fk_categories_parent
    FOREIGN KEY (parent_id) REFERENCES categories (id)
) ENGINE = InnoDB;
```

Node gốc có `parent_id = NULL`; node con tham chiếu node cha đã tồn tại. Seed cha trước con:

```sql
INSERT INTO categories (id, parent_id, category_name)
VALUES (1, NULL, 'Electronics');

INSERT INTO categories (id, parent_id, category_name)
VALUES (2, 1, 'Computers');

INSERT INTO categories (id, parent_id, category_name)
VALUES (3, 2, 'Laptops');
```

Khi xóa, xóa node con trước node cha nếu không có `ON DELETE CASCADE`. Với quan hệ cây, có thể dùng một câu delete theo thứ tự phù hợp hoặc cascade nếu chính sách xóa toàn nhánh là đúng với nghiệp vụ.

### 4.2. Hai bảng tham chiếu lẫn nhau

Một chu trình có thể xuất hiện khi bảng A tham chiếu B và B cũng tham chiếu A. MySQL InnoDB kiểm tra foreign key ngay trong câu lệnh; không hỗ trợ `DEFERRABLE` để trì hoãn kiểm tra đến cuối transaction như một số hệ quản trị khác.

Nếu cả hai khóa ngoại đều bắt buộc, không thể insert hàng đầu tiên theo cách thông thường khi hàng bên kia chưa tồn tại. Các hướng thiết kế thường dùng:

- Làm một phía nullable, insert bản ghi cha trước rồi update khóa ngoại còn lại sau.
- Tách quan hệ vòng thành bảng liên kết nếu mô hình nghiệp vụ phù hợp.
- Tạo dữ liệu theo một quy trình nhiều bước với constraint được thiết kế rõ ràng.

Ví dụ quan hệ nhân viên và nhân viên quản lý có thể dùng `manager_id` nullable: insert nhân viên trước, sau đó cập nhật manager khi cả hai hàng đã tồn tại. Không tắt kiểm tra khóa ngoại như giải pháp mặc định cho một mô hình dữ liệu có chu trình.

## 5. Seed dữ liệu xác định và có thể tái tạo

Seed data là dữ liệu mẫu để kiểm thử. Dữ liệu tốt cần ổn định, đủ đại diện cho các trường hợp nghiệp vụ và không phụ thuộc thời điểm chạy test.

### 5.1. Dùng dữ liệu cố định

Nên xác định trước:

- ID hoặc khóa nghiệp vụ của từng fixture.
- Email, mã đơn hàng, SKU và các giá trị unique.
- Ngày giờ cụ thể thay vì `NOW()` nếu test cần kết quả thời gian ổn định.
- Giá trị số dùng `DECIMAL` và literal có quy mô phù hợp.
- Các trạng thái nghiệp vụ bao phủ happy path và edge case.

Ví dụ, nếu test cần một đơn đã thanh toán và một đơn đang chờ xử lý, hãy seed hai trạng thái rõ ràng. Không dùng dữ liệu ngẫu nhiên nếu test mong đợi kết quả cố định, trừ khi seed ghi lại seed value để có thể tái tạo.

### 5.2. Idempotent seed

Một seed script idempotent có thể chạy lại mà không tạo dữ liệu trùng hoặc làm thay đổi kết quả ngoài dự kiến. Cách đơn giản nhất trong schema test mới là reset sạch rồi chạy `INSERT` xác định.

Nếu cần chạy lại trên schema đang có dữ liệu, có thể:

- Xóa đúng các fixture theo `test_run_id` hoặc khóa định danh riêng rồi insert lại.
- Dùng upsert theo unique key nếu quy tắc cập nhật đã được định nghĩa rõ.
- Lưu batch ID và trạng thái seed để job biết phần nào đã hoàn thành.

Không dùng `INSERT IGNORE` để che mọi duplicate hoặc lỗi dữ liệu. `INSERT IGNORE` có thể bỏ qua bản ghi không hợp lệ và làm test tiếp tục với fixture thiếu. `ON DUPLICATE KEY UPDATE` cũng cần cẩn thận nếu bảng có nhiều unique key vì xung đột có thể đến từ một khóa khác với khóa bạn định dùng.

### 5.3. Tách fixture theo mục đích

Không nên dùng một bộ seed rất lớn cho mọi test. Chia fixture theo mục đích:

- Fixture tối thiểu cho test repository và CRUD.
- Fixture có nhiều bảng liên quan cho test join, cascade và constraint.
- Fixture biên cho NULL, chuỗi rỗng, số lớn, ngày nhuận và dữ liệu Unicode.
- Fixture xung đột cho duplicate key, thiếu parent và vi phạm CHECK/FK.
- Fixture hiệu năng có số lượng lớn hơn, được nạp trong benchmark riêng.

Mỗi test nên chỉ seed những dữ liệu cần thiết để giảm phụ thuộc ẩn giữa test.

## 6. Reset schema và dữ liệu

Có nhiều cách reset, mỗi cách có phạm vi và giới hạn khác nhau.

### 6.1. Drop và tạo lại schema

Với integration test cần kiểm tra migration từ đầu, tạo database mới thường dễ hiểu nhất:

```sql
DROP DATABASE IF EXISTS mysql_app_test;

CREATE DATABASE mysql_app_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Sau đó chạy toàn bộ migration và seed. Chỉ chạy trên database test được chỉ định rõ. Lệnh `DROP DATABASE` xóa toàn bộ bảng và dữ liệu trong schema; không đưa tên schema lấy từ input không tin cậy vào script phá hủy.

DDL như `CREATE DATABASE`, `DROP DATABASE`, `CREATE TABLE`, `ALTER TABLE`, `TRUNCATE TABLE` có thể gây implicit commit. Không bọc chuỗi lệnh DDL reset trong transaction rồi kỳ vọng `ROLLBACK` khôi phục schema cũ.

### 6.2. Xóa dữ liệu bằng DELETE

Khi muốn giữ schema và reset dữ liệu, dùng `DELETE` theo thứ tự con trước cha:

```sql
START TRANSACTION;

DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;

COMMIT;
```

Với InnoDB, các thao tác delete trong transaction có thể rollback nếu có lỗi trước commit. `DELETE` không tự reset `AUTO_INCREMENT`; nếu test dùng ID cố định, điều này thường không thành vấn đề.

Nếu cần reset bộ đếm sau khi bảng đã rỗng, có thể đặt lại `AUTO_INCREMENT`:

```sql
ALTER TABLE order_items AUTO_INCREMENT = 1;
ALTER TABLE orders AUTO_INCREMENT = 1;
ALTER TABLE customers AUTO_INCREMENT = 1;
```

`ALTER TABLE` là DDL và có thể implicit commit. Chỉ thực hiện khi bảng rỗng và test thực sự phụ thuộc vào giá trị sinh tiếp theo. Cách ổn định hơn thường là seed ID cố định hoặc không kiểm thử bằng giả định ID tự tăng phải liên tục.

### 6.3. Dùng TRUNCATE có giới hạn

`TRUNCATE TABLE` xóa toàn bộ hàng nhanh và thường đặt lại `AUTO_INCREMENT`, nhưng đây là DDL với implicit commit. InnoDB không cho truncate một bảng đang bị foreign key của bảng khác tham chiếu, kể cả khi bảng con hiện không có hàng tham chiếu. Vì vậy, không thể thay toàn bộ lệnh `DELETE` theo thứ tự bằng một danh sách `TRUNCATE` tùy ý.

Có thể dùng `TRUNCATE` cho bảng không bị bảng khác tham chiếu, hoặc sau khi đã xử lý schema/constraint theo một quy trình riêng. Với các bảng quan hệ chặt chẽ, `DELETE` theo thứ tự phụ thuộc hoặc tạo lại schema thường an toàn và dễ dự đoán hơn.

## 7. `FOREIGN_KEY_CHECKS` và những điều không nên giả định

MySQL có biến `foreign_key_checks` để bật/tắt kiểm tra foreign key trong session hoặc global. Một số công cụ bulk load tạm tắt kiểm tra để nạp dữ liệu theo thứ tự khác, nhưng đây không phải cách reset mặc định cho test.

Ví dụ phạm vi session:

```sql
SET SESSION foreign_key_checks = 0;

-- Các thao tác bulk load có kiểm soát ở đây.

SET SESSION foreign_key_checks = 1;
```

Có một điểm rất quan trọng: khi bật lại `foreign_key_checks=1`, MySQL không quét lại dữ liệu đã được nạp trong thời gian kiểm tra bị tắt để xác minh các hàng có thỏa mãn constraint hay không. Vì vậy, việc bật lại biến không chứng minh dữ liệu không có orphan row.

Nếu bulk load cần tắt kiểm tra, phải có bước validation riêng trước khi dữ liệu được dùng. Ví dụ tìm order không có customer:

```sql
SELECT o.id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c ON c.id = o.customer_id
WHERE c.id IS NULL;
```

Tìm order item không có order:

```sql
SELECT i.id, i.order_id
FROM order_items AS i
LEFT JOIN orders AS o ON o.id = i.order_id
WHERE o.id IS NULL;
```

Nếu query trả về hàng, dữ liệu đang vi phạm quan hệ dự kiến. Cần sửa hoặc loại bỏ dữ liệu lỗi trước khi tiếp tục test.

Không tắt `foreign_key_checks` ở phạm vi global cho một test. Biến session chỉ ảnh hưởng connection hiện tại; nếu dùng connection pool, phải bảo đảm trạng thái session được khôi phục trước khi trả connection về pool. Một connection còn `foreign_key_checks=0` có thể làm test sau chạy với hành vi không mong muốn.

## 8. Transaction rollback trong test

Một test có thể bắt đầu transaction, seed fixture, gọi logic cần kiểm thử rồi rollback để dọn dữ liệu:

```sql
START TRANSACTION;

INSERT INTO customers (id, email, display_name)
VALUES (9001, 'rollback@example.test', 'Rollback Test');

SELECT * FROM customers WHERE id = 9001;

ROLLBACK;
```

Cách này nhanh và hữu ích khi:

- Các bảng dùng InnoDB hoặc engine transactional.
- Test và seed dùng cùng transaction/connection.
- Code không tự commit hoặc chuyển sang connection khác.
- Không có DDL hoặc side effect bên ngoài transaction.

Nếu ứng dụng mở connection riêng, gọi `REQUIRES_NEW`, dùng async worker hoặc chạy tác vụ qua queue, transaction của test không bao phủ những thao tác đó. Test có thể rollback transaction chính nhưng dữ liệu từ connection khác đã commit vẫn tồn tại.

Với Spring test có `@Transactional`, transaction test thường được rollback sau test. Tuy nhiên, nếu test gọi service dùng transaction propagation khác, chạy thread khác hoặc dùng DDL, cần xác minh ranh giới transaction thực tế. Không giả định mọi thao tác trong test đều được rollback chỉ vì method test có annotation.

## 9. Reset trong test chạy song song

Hai test cùng dùng một schema có thể gây race condition:

- Test A seed customer `1001`.
- Test B reset bảng `customers`.
- Test A đọc order nhưng customer đã bị xóa.
- Test C dùng cùng order number và gặp duplicate key.

Để tránh xung đột:

- Dùng database/schema riêng cho từng test worker hoặc test class có thao tác phá hủy.
- Nếu dùng một schema chung, gắn fixture với namespace hoặc `test_run_id` và không truncate/drop dữ liệu dùng chung.
- Không chạy reset toàn schema đồng thời với test khác.
- Đặt timeout và cleanup trong `finally`/lifecycle hook, nhưng vẫn ghi nhận cleanup thất bại.
- Dùng container database riêng nếu cần isolation mạnh và môi trường tái tạo được.

Tên schema có thể được sinh từ run ID, nhưng chỉ ghép identifier do test harness tạo và kiểm soát; identifier SQL không thể bind bằng JDBC placeholder như giá trị dữ liệu. Không nối trực tiếp tên database từ input bên ngoài vào câu `DROP DATABASE`.

## 10. Kiểm tra schema và dữ liệu seed

Sau khi migration và seed, không chỉ kiểm tra số dòng tổng. Xác minh schema, foreign key và các quan hệ cần thiết.

Kiểm tra bảng và engine:

```sql
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'mysql_app_test'
ORDER BY TABLE_NAME;
```

Kiểm tra foreign key:

```sql
SELECT
  TABLE_NAME,
  CONSTRAINT_NAME,
  COLUMN_NAME,
  REFERENCED_TABLE_NAME,
  REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'mysql_app_test'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

Kiểm tra số lượng fixture:

```sql
SELECT COUNT(*) AS customer_count FROM customers;
SELECT COUNT(*) AS order_count FROM orders;
SELECT COUNT(*) AS item_count FROM order_items;
```

Kiểm tra quan hệ:

```sql
SELECT o.id, o.order_number, c.email
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
ORDER BY o.id;

SELECT i.id, i.sku, o.order_number
FROM order_items AS i
JOIN orders AS o ON o.id = i.order_id
ORDER BY i.id;
```

Đối với test cần chứng minh constraint hoạt động, viết test âm: thử insert order với `customer_id` không tồn tại và xác nhận MySQL trả lỗi foreign key. Sau test âm, rollback hoặc dọn trạng thái để không làm nhiễm fixture tiếp theo.

## 11. Quy trình thực tế cho một test suite

Một quy trình có thể tự động hóa:

1. Khởi tạo MySQL test instance hoặc schema cô lập.
2. Tạo database với charset/collation tương thích.
3. Chạy Flyway/Liquibase từ migration đầu tiên đến phiên bản hiện tại.
4. Kiểm tra bảng, index và foreign key đã được tạo.
5. Seed bảng cha trước, bảng con sau theo đồ thị phụ thuộc.
6. Xác minh số lượng và quan hệ fixture.
7. Chạy test; ưu tiên transaction rollback cho test DML độc lập.
8. Với test cần commit hoặc test migration, cleanup theo thứ tự con trước cha hoặc drop schema riêng.
9. Thu thập log lỗi và trạng thái cleanup; không bỏ qua cleanup thất bại.
10. Hủy container/schema test sau khi suite hoàn tất.

Nên tách test migration khỏi test repository/service. Test migration cần bắt đầu từ schema rỗng hoặc phiên bản cũ được chuẩn bị rõ ràng; test repository thường cần fixture nhỏ và chạy nhanh.

## 12. Bài thực hành

Một ứng dụng bán hàng có các bảng `customers`, `orders`, `order_items` và `payments`. `orders.customer_id` tham chiếu `customers.id`; `order_items.order_id` và `payments.order_id` cùng tham chiếu `orders.id`. Nhóm muốn chạy integration test trên MySQL 8.0 với nhiều worker song song.

Hãy thiết kế quy trình và trả lời:

1. Viết lệnh tạo schema test với `utf8mb4` và collation giống môi trường ứng dụng.
2. Vì sao nên chạy migration chung thay vì duy trì DDL riêng cho test?
3. Xác định thứ tự seed bốn bảng và thứ tự cleanup ngược lại.
4. Viết một bộ seed có ID, email, order number và timestamp cố định.
5. Nếu một test chỉ cần thay đổi DML và dùng InnoDB, khi nào transaction rollback phù hợp?
6. Vì sao `TRUNCATE customers` có thể bị từ chối dù bảng `orders` đang rỗng?
7. Vì sao bật lại `foreign_key_checks=1` không xác minh những hàng được nạp khi kiểm tra bị tắt?
8. Viết query tìm order không có customer và payment không có order.
9. Làm thế nào reset `AUTO_INCREMENT` mà không giả định ID luôn liên tục?
10. Đề xuất cách cô lập schema để hai worker không xóa dữ liệu của nhau.
11. Thiết kế một test âm chứng minh foreign key từ chối bản ghi con không có bản ghi cha.

Một lời giải tốt phải chỉ rõ nơi chạy DDL, quyền tài khoản test, thứ tự phụ thuộc, ranh giới transaction và cách dọn dữ liệu khi test thất bại giữa chừng.

## Kết luận

Test MySQL ổn định cần schema cô lập, migration dùng chung với ứng dụng, fixture xác định và thứ tự thao tác theo đồ thị khóa ngoại. Insert theo thứ tự cha trước con, cleanup theo thứ tự con trước cha. Dùng transaction rollback cho test DML khi mọi thao tác thực sự nằm trong cùng transaction; dùng schema riêng hoặc migration reset cho test DDL. `TRUNCATE` có implicit commit và bị giới hạn bởi foreign key; tắt `foreign_key_checks` không làm MySQL kiểm tra lại dữ liệu khi bật lên. Hãy xác minh schema, số lượng, quan hệ và khả năng chạy song song trước khi coi test suite là đáng tin cậy.
