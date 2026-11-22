# Khóa chính, khóa ngoại, ràng buộc duy nhất và tính toàn vẹn dữ liệu

## 1. Mục tiêu và bối cảnh

Sau bài này, bạn có thể:

- Phân biệt `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL` và `CHECK`; chọn ràng buộc tương ứng với từng quy tắc dữ liệu.
- Thiết kế quan hệ cha–con, khóa đơn/khóa ghép và hành vi khi cập nhật hoặc xóa bản ghi được tham chiếu.
- Giải thích vì sao kiểm tra ở Java/Spring không thay thế được ràng buộc trong cơ sở dữ liệu, đặc biệt khi có nhiều request đồng thời.
- Tạo và kiểm thử lược đồ SQL, nhận diện lỗi ràng buộc, xử lý chúng qua Spring JDBC hoặc JPA, và triển khai thay đổi schema an toàn.

Giả sử ứng dụng quản lý khách hàng, đơn hàng, dòng hàng. Mỗi khách hàng có định danh riêng; email không được trùng; mỗi đơn hàng thuộc về một khách hàng có thật; trong một đơn, số thứ tự dòng hàng không được lặp; số lượng dòng hàng phải dương. Nếu chỉ kiểm tra bằng một câu `SELECT` trước khi `INSERT`, dữ liệu vẫn có thể sai khi hai request chạy đồng thời. Nơi bảo vệ cuối cùng cho các bất biến này là cơ sở dữ liệu (DB).

**Tính toàn vẹn dữ liệu (data integrity)** là trạng thái trong đó dữ liệu tuân thủ các quy tắc đã công bố ở mọi thao tác hợp lệ, kể cả khi ứng dụng gặp lỗi, request chạy song song hoặc có chương trình khác cùng ghi vào DB.

## 2. Các lớp toàn vẹn cần phân biệt

| Nhóm | Câu hỏi cần bảo đảm | Công cụ thường dùng |
| --- | --- | --- |
| Toàn vẹn thực thể | Bản ghi được nhận diện duy nhất bằng gì? | `PRIMARY KEY` |
| Toàn vẹn tham chiếu | Bản ghi con có tham chiếu đến bản ghi cha hợp lệ không? | `FOREIGN KEY` |
| Tính duy nhất nghiệp vụ | Email/mã đơn hàng có được trùng không? | `UNIQUE`, unique index |
| Toàn vẹn miền giá trị | Giá trị có bắt buộc và nằm trong miền hợp lệ không? | `NOT NULL`, `CHECK`, kiểu dữ liệu |
| Tính nhất quán qua nhiều thao tác | Hoặc tất cả thao tác cùng thành công, hoặc cùng hủy? | Transaction, `@Transactional` |
| Quy tắc xuyên nhiều hàng/bảng | Tổng, số dư, hạn mức hay trạng thái có hợp lệ? | Transaction, khóa đồng thời, đôi khi trigger/constraint chuyên biệt |

DB constraint bảo vệ một bất biến được khai báo. Transaction bảo đảm một nhóm thay đổi được commit/rollback cùng nhau; hai khái niệm bổ sung cho nhau. Validation của API giúp báo lỗi sớm và rõ hơn, nhưng không thay thế DB constraint.

## 3. Primary key: định danh duy nhất của mỗi hàng

`PRIMARY KEY` (PK) xác định một hàng trong bảng. Theo mô hình quan hệ và cách triển khai thông dụng, PK bắt buộc **duy nhất** và **không NULL**. Một bảng có tối đa một ràng buộc PK, nhưng PK đó có thể gồm nhiều cột.

Ví dụ khóa đơn:

```sql
CREATE TABLE categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

`id` là khóa thay thế (surrogate key) do DB cấp; không nên coi tính liên tục của ID là bảo đảm nghiệp vụ vì sequence có thể bỏ số khi transaction rollback. So với khóa tự nhiên (natural key, như số định danh đã được kiểm soát), surrogate key thường ổn định hơn khi thuộc tính nghiệp vụ có thể thay đổi.

Ví dụ khóa ghép:

```sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_enrollment PRIMARY KEY (student_id, course_id)
);
```

Cặp `(student_id, course_id)` mới là định danh; riêng `student_id` hoặc `course_id` có thể lặp. Ví dụ chỉ minh họa PK: nếu hệ thống có bảng `students` và `courses`, phải thêm FK tương ứng để bảo đảm hai ID thực sự tồn tại. PK **không tự** tạo quan hệ tham chiếu.

Trong PostgreSQL, khai báo PK tự tạo unique B-tree index phục vụ kiểm tra duy nhất và tra cứu khóa. Index không làm PK trở thành một quy tắc nghiệp vụ; việc chọn PK cần xét tính ổn định, khả năng tham chiếu và kích thước khóa.

**Cân nhắc khi thiết kế:** nếu một bảng có `id` làm PK nhưng nghiệp vụ yêu cầu `(tenant_id, external_code)` duy nhất, cần thêm `UNIQUE (tenant_id, external_code)`. PK trên `id` không tự bảo vệ tính duy nhất của cặp này.

## 4. UNIQUE: quy tắc không trùng ngoài khóa chính

`UNIQUE` ngăn hai hàng có cùng tổ hợp giá trị thuộc các cột được khai báo. Một bảng có thể có nhiều ràng buộc `UNIQUE`.

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL,
    tenant_id BIGINT NOT NULL,
    CONSTRAINT uq_accounts_tenant_username UNIQUE (tenant_id, username)
);
```

Trong ví dụ, username có thể giống nhau ở hai tenant khác nhau, nhưng không được lặp trong **cùng** tenant. Nếu muốn username duy nhất toàn hệ thống, ràng buộc phải chỉ trên `username`.

### 4.1. UNIQUE không giống PRIMARY KEY

- `PRIMARY KEY`: duy nhất, không NULL; là định danh chính của hàng; tối đa một PK mỗi bảng.
- `UNIQUE`: độc lập với PK; có thể nhiều ràng buộc mỗi bảng; quy tắc với `NULL` phụ thuộc DBMS và cách khai báo.
- `UNIQUE (a, b)` xét cả cặp `(a, b)`; không có nghĩa là `a` và `b` phải duy nhất riêng rẽ.

**Điểm dễ sai về NULL:** trong PostgreSQL, `UNIQUE (email)` mặc định cho phép nhiều hàng có `email IS NULL`, vì giá trị NULL được xem là phân biệt khi kiểm tra uniqueness. Muốn email bắt buộc và duy nhất, khai báo **`email ... NOT NULL UNIQUE`**. PostgreSQL 15+ còn hỗ trợ `UNIQUE NULLS NOT DISTINCT` nếu muốn coi nhiều NULL là trùng. Các hệ quản trị khác có thể có ngữ nghĩa khác; không suy diễn từ một DBMS sang DBMS khác.

### 4.2. Chuẩn hóa và uniqueness theo nghiệp vụ

Nếu `Alice@Example.test` và `alice@example.test` phải được coi là cùng một email, `UNIQUE (email)` trên chuỗi thô có thể chưa đáp ứng quy tắc; kết quả phụ thuộc collation/kiểu dữ liệu. Một lựa chọn riêng cho PostgreSQL là unique expression index:

```sql
CREATE UNIQUE INDEX uq_accounts_username_lower
    ON accounts (tenant_id, lower(username));
```

Lệnh này bổ sung quy tắc không trùng tên theo dạng lowercase trong cùng tenant. Phải quyết định chính sách chuẩn hóa Unicode, khoảng trắng và phạm vi so sánh trước khi triển khai; lowercase không giải quyết mọi bài toán chuẩn hóa quốc tế.

Với soft delete, yêu cầu “chỉ các hàng còn hoạt động mới không được trùng” thường dùng **partial unique index** của PostgreSQL, chẳng hạn `CREATE UNIQUE INDEX ... ON ... (email) WHERE deleted_at IS NULL`. Đây là tính năng theo DBMS, không phải cú pháp `UNIQUE` chuẩn áp dụng ở mọi hệ.

## 5. Foreign key: bảo vệ quan hệ tham chiếu

`FOREIGN KEY` (FK) yêu cầu giá trị ở bảng con trỏ đến giá trị hợp lệ của khóa được tham chiếu ở bảng cha. Trong PostgreSQL, cột được tham chiếu thường là PK, UNIQUE constraint hoặc một unique index không phải partial phù hợp. FK bảo vệ quan hệ; nó **không ngụ ý** bảng con và bảng cha được cập nhật trong cùng transaction, và cũng không quyết định tự động mọi chính sách xóa nếu ta chưa khai báo.

```sql
CREATE TABLE departments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE employees (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_employees_department
        FOREIGN KEY (department_id) REFERENCES departments (id)
        ON DELETE RESTRICT
);
```

Nhân viên không thể lưu `department_id = 999` nếu không có phòng ban `id = 999`. Khi còn nhân viên tham chiếu, `ON DELETE RESTRICT` ngăn xóa phòng ban. `department_id NOT NULL` còn ngăn “nhân viên chưa có phòng ban”; chỉ FK mà không có `NOT NULL` vẫn có thể cho phép giá trị NULL.

### 5.1. Các hành động khi xóa cha

| Tùy chọn | Tác động lên hàng con khi xóa cha | Khi nào cân nhắc |
| --- | --- | --- |
| `NO ACTION` (thường là mặc định) | Vi phạm FK nếu cuối thời điểm kiểm tra vẫn còn tham chiếu; có thể hoãn kiểm tra nếu FK được khai báo deferrable và DB hỗ trợ | Không muốn xóa khi còn phụ thuộc |
| `RESTRICT` | Chặn thao tác xóa đang bị tham chiếu; trong PostgreSQL không thể hoãn kiểm tra theo cách của `NO ACTION` | Quan hệ cần bảo vệ chặt ngay khi thao tác |
| `CASCADE` | Tự xóa các hàng con tham chiếu | Thành phần phụ thuộc vòng đời của cha, như dòng hàng thuộc đơn |
| `SET NULL` | Đặt FK của hàng con thành NULL | Quan hệ tùy chọn; cột FK phải cho phép NULL |
| `SET DEFAULT` | Gán giá trị mặc định vào FK | Chỉ hợp lệ nếu giá trị mặc định thỏa FK |

Đối với `ON UPDATE`, cơ chế tương tự áp dụng khi khóa được tham chiếu thay đổi. Thực tế nên tránh cập nhật định danh PK khi không cần; việc chọn `CASCADE` là quyết định vòng đời dữ liệu, không phải cách “làm hết lỗi FK”.

**Đặc biệt:** `ON DELETE CASCADE` của DB khác với `CascadeType.REMOVE` trong JPA. Một bên được DB thi hành khi thực hiện câu SQL xóa cha; bên kia là cơ chế lan truyền thao tác trên entity trong persistence context. Không mặc định hai bên tương đương về thời điểm chạy, lifecycle callback và cache.

### 5.2. Khóa ngoại ghép và NULL

FK ghép phải tham chiếu đúng tập cột khóa có tính duy nhất ở bảng cha, theo đúng thứ tự ánh xạ. Với FK nhiều cột, PostgreSQL mặc định `MATCH SIMPLE`: có thể bỏ qua kiểm tra tham chiếu nếu bất kỳ thành phần nào là NULL. `MATCH FULL` chỉ chấp nhận tất cả thành phần NULL hoặc tất cả hợp lệ; muốn bắt buộc liên kết tồn tại thì vẫn nên khai báo `NOT NULL` cho các cột liên quan. Đây là một lý do không nên coi FK tự động thay thế `NOT NULL`.

## 6. NOT NULL, CHECK và phạm vi của các ràng buộc

`NOT NULL` bảo đảm cột có giá trị (không bảo đảm chuỗi không rỗng). `CHECK` đánh giá biểu thức trên hàng; ví dụ `CHECK (quantity > 0)` ngăn số lượng bằng 0 hoặc âm. Với PostgreSQL, `CHECK` được coi là thỏa nếu biểu thức là TRUE **hoặc NULL/UNKNOWN**; vì vậy cần kết hợp `NOT NULL` khi cột bắt buộc.

```sql
CREATE TABLE prices (
    sku VARCHAR(40) PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    CONSTRAINT ck_prices_amount CHECK (amount >= 0),
    CONSTRAINT ck_prices_currency CHECK (currency IN ('VND', 'USD'))
);
```

Có thể dùng `CHECK` cho quy tắc trong một hàng (ví dụ `end_at > start_at`), nhưng quy tắc liên quan tổng nhiều hàng hay nhiều bảng thường không thể mô hình hóa bằng một `CHECK` thông thường. Khi đó cần thiết kế thao tác có transaction, cơ chế đồng thời/khóa phù hợp, đôi khi trigger hoặc mô hình dữ liệu khác. Bean Validation ở Java như `@NotBlank`, `@Email`, `@Positive` cải thiện trải nghiệm nhập liệu; chỉ DB mới bảo vệ dữ liệu khỏi mọi client.

## 7. Ví dụ hoàn chỉnh: schema PostgreSQL cho đơn hàng

Các lệnh sau chạy trên **một schema/database thử nghiệm trống**, dùng cú pháp PostgreSQL. Bảng cha được tạo trước bảng con. Các tên constraint đặt rõ ràng để dễ đọc log và quản lý migration.

```sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (id),
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (id),
    CONSTRAINT uq_orders_number UNIQUE (order_number),
    CONSTRAINT ck_orders_total_amount CHECK (total_amount >= 0),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
        ON DELETE RESTRICT
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(50) NOT NULL,
    qty INTEGER NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_order_items_qty CHECK (qty > 0),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders (id)
        ON DELETE CASCADE
);

CREATE INDEX idx_orders_customer_id ON orders (customer_id);
```

**Giải thích thiết kế:**

- `customers.id` và `orders.id` là surrogate PK; `order_items` dùng PK ghép `(order_id, line_no)` vì số thứ tự chỉ duy nhất trong một đơn.
- `uq_customers_email` và `uq_orders_number` là hai bất biến nghiệp vụ độc lập với PK.
- `fk_orders_customer` không cho phép đơn hàng mồ côi; `RESTRICT` bảo vệ lịch sử đơn khi xóa khách.
- `fk_order_items_order` chọn `CASCADE` vì dòng hàng phụ thuộc trực tiếp đơn; xóa một đơn sẽ xóa các dòng của chính đơn đó.
- `qty`, `total_amount` có cả `NOT NULL` và `CHECK`; không có hai ràng buộc này, có thể lọt giá trị NULL hoặc sai miền.
- `idx_orders_customer_id` tăng hiệu quả truy vấn theo khách và kiểm tra quan hệ khi xóa/cập nhật khách. Trong PostgreSQL, FK **không tự tạo index ở phía bảng con**. PK ghép `(order_id, line_no)` đã tạo index có tiền tố `order_id` phù hợp nhiều truy vấn theo đơn.

### 7.1. Dữ liệu hợp lệ và kết quả dự kiến

Chạy theo đúng thứ tự trong database trống vừa tạo:

```sql
INSERT INTO customers (email, full_name)
VALUES ('an@example.test', 'An Nguyen'),
       ('binh@example.test', 'Binh Tran');

INSERT INTO orders (customer_id, order_number, total_amount)
VALUES (1, 'ORD-001', 120.00);

INSERT INTO order_items (order_id, line_no, sku, qty)
VALUES (1, 1, 'SKU-01', 2);

SELECT c.email, o.order_number, i.line_no, i.sku, i.qty
FROM customers c
JOIN orders o ON o.customer_id = c.id
JOIN order_items i ON i.order_id = o.id
ORDER BY o.id, i.line_no;
```

Kết quả logic của `SELECT` là **một hàng**: `an@example.test | ORD-001 | 1 | SKU-01 | 2`. ID = 1 ở ví dụ này dựa trên bảng mới và sequence mới; trong môi trường thực, lấy ID trả về từ `INSERT ... RETURNING id` thay vì hard-code.

### 7.2. Kiểm thử các tình huống bị từ chối

**Chạy từng câu độc lập** sau dữ liệu hợp lệ bên trên. Nếu chạy trong cùng transaction PostgreSQL rồi có một lỗi SQL, transaction đó bị đánh dấu aborted; phải `ROLLBACK` hoặc dùng savepoint trước khi chạy câu tiếp theo.

```sql
-- Trùng email: uq_customers_email
INSERT INTO customers (email, full_name)
VALUES ('an@example.test', 'Another An');

-- Khách hàng không tồn tại: fk_orders_customer
INSERT INTO orders (customer_id, order_number, total_amount)
VALUES (999, 'ORD-002', 10.00);

-- Không được để email NULL
INSERT INTO customers (email, full_name)
VALUES (NULL, 'No Email');

-- Số lượng không hợp lệ: ck_order_items_qty
INSERT INTO order_items (order_id, line_no, sku, qty)
VALUES (1, 2, 'SKU-02', 0);

-- Trùng PK ghép (order_id, line_no)
INSERT INTO order_items (order_id, line_no, sku, qty)
VALUES (1, 1, 'SKU-OTHER', 1);

-- Không được xóa khách 1 khi vẫn có đơn tham chiếu
DELETE FROM customers WHERE id = 1;
```

Kết quả mong đợi: tất cả câu trên đều bị DB từ chối, dữ liệu hợp lệ trước đó vẫn tồn tại (nếu mỗi câu chạy trong transaction riêng). Với PostgreSQL, SQLSTATE thường gặp: `23505` = trùng PK/UNIQUE; `23503` = vi phạm FK; `23502` = vi phạm NOT NULL; `23514` = vi phạm CHECK. SQLSTATE và thông tin tên constraint hữu ích hơn việc parse nguyên văn lỗi tiếng Anh từ DB.

Để kiểm tra cascade, sau khi hoàn tất các thử nghiệm trên:

```sql
DELETE FROM orders WHERE id = 1;
SELECT COUNT(*) AS remaining_items FROM order_items WHERE order_id = 1;
```

`remaining_items` bằng `0`: khi xóa đơn, DB xóa dòng hàng tương ứng. Sau đó khách `id = 1` không còn bị chính đơn này ngăn xóa, trừ khi có quan hệ khác.

## 8. Tính toàn vẹn khi có nhiều request đồng thời

Một cách triển khai dễ mắc lỗi:

```text
Request A: SELECT kiểm tra email X chưa tồn tại -> TRUE
Request B: SELECT kiểm tra email X chưa tồn tại -> TRUE
Request A: INSERT email X -> thành công
Request B: INSERT email X -> ?
```

Nếu không có `UNIQUE` ở DB, cả hai request có thể ghi trùng. Nếu có `UNIQUE`, DB quyết định một thao tác thành công và thao tác còn lại bị từ chối hoặc phải xử lý xung đột theo ngữ nghĩa giao dịch. Câu `existsByEmail(...)` hữu ích để hiển thị thông báo sớm nhưng **không thể dùng làm khóa bảo vệ tính duy nhất**.

Với PostgreSQL, khi nghiệp vụ muốn tạo nếu chưa có, có thể cân nhắc `INSERT ... ON CONFLICT (...) DO NOTHING/DO UPDATE`. Đây là một chiến lược idempotency/upsert theo SQL và điều kiện nghiệp vụ, không có nghĩa là nên bỏ `UNIQUE`. Nếu cần phân biệt “tạo mới” và “đã tồn tại”, kiểm tra kết quả thực sự của lệnh ghi.

Ràng buộc còn tương tác với transaction: một đơn và các dòng hàng phải được ghi cùng transaction để tránh trạng thái chỉ có đơn mà thiếu dòng do thao tác sau thất bại. Tuy nhiên transaction **không tự tạo** uniqueness hay FK; phải dùng cả hai.

## 9. Áp dụng trong Spring JDBC

Spring `JdbcTemplate` giúp bind tham số, quản lý tài nguyên JDBC và chuyển nhiều lỗi SQL thành nhóm `DataAccessException`. Ví dụ dưới đây là **một class dùng trong dự án Spring Boot 3.x/Spring Framework 6.x có cấu hình DataSource PostgreSQL và `spring-boot-starter-jdbc`**; đây không phải chương trình Java thuần chạy bằng `javac` không cần dependency.

Tệp `OrderWriter.java`:

```java
package example.orders;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWriter {

    public record ItemInput(int lineNo, String sku, int quantity) {}

    private final JdbcTemplate jdbc;

    public OrderWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public long createOrder(
            long customerId,
            String number,
            BigDecimal total,
            List<ItemInput> items
    ) {
        Long orderId = jdbc.queryForObject(
                """
                INSERT INTO orders (customer_id, order_number, total_amount)
                VALUES (?, ?, ?)
                RETURNING id
                """,
                Long.class,
                customerId,
                number,
                total
        );
        if (orderId == null) {
            throw new IllegalStateException("Database did not return order id");
        }

        for (ItemInput item : items) {
            jdbc.update(
                    """
                    INSERT INTO order_items (order_id, line_no, sku, qty)
                    VALUES (?, ?, ?, ?)
                    """,
                    orderId,
                    item.lineNo(),
                    item.sku(),
                    item.quantity()
            );
        }
        return orderId;
    }
}
```

**Diễn giải luồng chạy:**

1. Spring gọi phương thức qua bean/proxy quản lý transaction; `@Transactional` mở hoặc tham gia transaction theo cấu hình.
2. Lệnh `INSERT ... RETURNING id` lấy ID thật từ DB (cú pháp PostgreSQL); không tự đoán ID theo thứ tự.
3. Các `INSERT` dòng hàng dùng ID vừa nhận, nên FK đến `orders` hợp lệ.
4. Nếu khách không tồn tại, mã đơn bị trùng, `qty <= 0` hoặc PK dòng bị trùng, DB từ chối thao tác. Khi lỗi được chuyển thành unchecked exception và thoát khỏi phương thức, transaction mặc định rollback cả đơn lẫn các dòng đã thêm.
5. Nếu thành công, transaction commit. Nếu muốn tổng đơn chính xác bằng tổng dòng, cần thêm cấu trúc giá/logic tính toán thích hợp; schema minh họa trên **chưa** tự bảo đảm quy tắc tổng này.

`JdbcTemplate.update(sql, args...)` trả về số hàng bị tác động khi dùng `INSERT/UPDATE/DELETE` thông thường. Với `RETURNING`, ví dụ dùng `queryForObject` để nhận hàng kết quả. Dấu `?` là bind parameter, tránh ghép giá trị đầu vào vào chuỗi SQL.

**Lưu ý proxy:** lời gọi `this.createOrder(...)` từ một phương thức khác ngay trong cùng đối tượng có thể không đi qua proxy Spring, khiến `@Transactional` không được áp dụng như mong đợi ở cấu hình proxy tiêu chuẩn. Đặt transaction tại service được gọi từ bean khác hoặc cấu hình phù hợp.

## 10. Ánh xạ JPA/Hibernate và giới hạn của annotation

Trong Spring Data JPA, `@Id` biểu thị định danh entity; `@Table(uniqueConstraints = ...)` hoặc `@Column(unique = true)` có thể mô tả ý định tạo schema, còn `@JoinColumn` mô tả FK ở quan hệ entity. Ví dụ **đoạn ánh xạ nằm trong entity của một dự án JPA**, không phải ứng dụng độc lập:

```java
import jakarta.persistence.*;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_customers_email",
        columnNames = "email"
    )
)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, length = 254)
    private String email;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {}

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }
}
```

Trong entity `Order`, có thể khai báo phần quan hệ như sau:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "customer_id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_orders_customer")
)
private Customer customer;
```

Đoạn thứ hai **chỉ là field mapping**, cần đặt trong một class `@Entity` hợp lệ với PK và các thuộc tính khác. `optional = false` là ý định ở mô hình entity; `nullable = false` phản ánh yêu cầu cột không NULL khi sinh DDL. Hành vi `ON DELETE RESTRICT/CASCADE` phải được chốt trong migration của DB; không suy ra từ `@ManyToOne` hay `CascadeType`.

Trong production, nên quản lý DDL bằng **Flyway/Liquibase** (hoặc quy trình migration được kiểm soát), kiểm tra schema thật sau deploy, và không dựa hoàn toàn vào `hibernate.hbm2ddl.auto=update` để suy diễn constraint trên hệ thống đã có dữ liệu.

`JpaRepository.save(...)` có thể chỉ xếp thao tác vào persistence context; lỗi constraint có thể xuất hiện tại `flush` hoặc `commit`, không nhất thiết ngay dòng `save`. `saveAndFlush(...)` đẩy thay đổi xuống DB sớm hơn nhưng **không đồng nghĩa commit**. Vì vậy hãy thiết kế xử lý ngoại lệ ở ngoài ranh giới transaction phù hợp, đừng giả định `try/catch` quanh `save` luôn bắt được mọi lỗi uniqueness.

## 11. Phân loại lỗi dữ liệu trong Spring

Khi dùng Spring JDBC, exception translation thường chuyển vi phạm constraint thành `org.springframework.dao.DataIntegrityViolationException` (hoặc lớp con như `DuplicateKeyException` tùy driver/translator). Với JPA, kiểu và thời điểm exception còn phụ thuộc provider cùng cơ chế translation; không hard-code một đường đi duy nhất.

Luồng xử lý hợp lý:

```text
HTTP request
  -> validate dữ liệu nhập (DTO/Bean Validation)
  -> Service @Transactional
  -> Repository/JdbcTemplate
  -> DB kiểm tra PK, FK, UNIQUE, NOT NULL, CHECK
  -> DB chấp nhận hoặc trả constraint violation
  -> Spring dịch lỗi khi được hỗ trợ
  -> transaction rollback
  -> API chuyển lỗi thành phản hồi an toàn, rõ nghĩa
```

- **Trùng khóa nghiệp vụ**: thường trả `409 Conflict`, ví dụ email đã được sử dụng.
- **Tham chiếu không tồn tại**: trả `400/404/422` tùy thiết kế resource và hợp đồng API, sau khi xác định đúng trường hợp.
- **Dữ liệu sai miền**: thường `400 Bad Request` hoặc `422 Unprocessable Content`; validate trước để gửi phản hồi hữu ích.
- **Vi phạm bất biến nội bộ bất ngờ**: ghi log có tên constraint, correlation ID và nguyên nhân; không trả stack trace/SQL thô hay thông tin nhạy cảm cho client.

Không ánh xạ mọi `DataIntegrityViolationException` thành “email trùng”: lớp lỗi này có thể đại diện cả FK, CHECK, NOT NULL. Ưu tiên phân biệt bằng **tên constraint đã chủ động đặt**, SQLSTATE/vendor code khi thực sự cần, và ngữ cảnh nghiệp vụ. Không parse nguyên văn thông báo phụ thuộc phiên bản hoặc locale. Trong transaction PostgreSQL, sau khi câu SQL thất bại, thường phải rollback toàn transaction; catch rồi tiếp tục ghi trên cùng transaction đã lỗi không tự làm nó phục hồi.

## 12. Migration và vận hành trên dữ liệu thật

Trên database trống, `CREATE TABLE ... CONSTRAINT ...` đơn giản. Với bảng đã có hàng triệu bản ghi, thêm ràng buộc yêu cầu kiểm tra và chuẩn bị:

1. **Xác định bất biến** bằng ngôn ngữ nghiệp vụ: “email duy nhất toàn hệ thống” hay “duy nhất trong tenant”? “xóa khách có được xóa lịch sử đơn không”?
2. **Tìm dữ liệu vi phạm trước**: các nhóm bị trùng, FK mồ côi, giá trị NULL, số lượng âm. Chốt chính sách sửa dữ liệu với chủ sở hữu hệ thống.
3. **Thiết kế migration** có thứ tự: làm sạch/backfill, tạo index khi phù hợp, thêm constraint, xác minh thành công. Với bảng lớn, kiểm tra khả năng lock và cơ chế như `NOT VALID`/`VALIDATE CONSTRAINT` của PostgreSQL cho những loại ràng buộc hỗ trợ; không mặc định áp dụng cho mọi loại.
4. **Triển khai tương thích**: code mới và cũ có thể cùng chạy trong đợt rolling deployment. Không thêm `NOT NULL` trước khi mọi đường ghi đáp ứng nó.
5. **Kiểm thử bằng DBMS thực tế**: dùng integration test (ví dụ Testcontainers PostgreSQL) cho PK/FK/UNIQUE/CHECK, thứ tự xóa và transaction rollback. DB nhúng khác có thể khác ngữ nghĩa NULL, constraint, DDL và lock.
6. **Quan sát hậu triển khai**: tỷ lệ lỗi theo constraint, độ trễ ghi, lock contention và query plan của những truy vấn ảnh hưởng bởi index mới.

Một số truy vấn kiểm tra trước migration (chỉnh tên bảng/cột cho schema thực tế):

```sql
-- Email trùng trong bảng có dữ liệu
SELECT email, COUNT(*) AS occurrences
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;

-- Đơn hàng mồ côi trước khi thêm FK (nếu schema cũ chưa có FK)
SELECT o.id, o.customer_id
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE c.id IS NULL;

-- Dòng hàng sai miền trước khi thêm CHECK
SELECT order_id, line_no, qty
FROM order_items
WHERE qty IS NULL OR qty <= 0;
```

Đừng xóa dữ liệu trùng hoặc mồ côi tự động chỉ để migration chạy được. Phải biết bản ghi nào là đúng, có cần hợp nhất, lưu lịch sử hay thông báo cho hệ thống liên quan.

## 13. Lỗi phổ biến và cách tự kiểm tra

| Lỗi thiết kế/lập trình | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `existsByEmail` rồi `save` | Race condition giữa hai request | Đặt `UNIQUE` ở DB và xử lý conflict |
| Chỉ đặt `@NotNull` trên DTO/entity | Client khác có thể bỏ qua validation | Thêm `NOT NULL` tại DB |
| Cho rằng FK tự chặn NULL | FK thường cho phép NULL | Dùng `NOT NULL` nếu quan hệ bắt buộc |
| Đặt `UNIQUE(a,b)` nhưng muốn `a` riêng lẻ duy nhất | Unique ghép kiểm tra tổ hợp | Đặt đúng unique key theo bất biến |
| Cho rằng FK tự sinh index ở bảng con | PostgreSQL không tự tạo index đó | Xem query pattern, thêm index phù hợp |
| Dùng `ON DELETE CASCADE` cho dữ liệu cần lưu lịch sử | Xóa cha kéo theo xóa con ngoài ý muốn | Chọn `RESTRICT` hoặc mô hình lưu trữ phù hợp |
| Chỉ dùng transaction, không có constraint | Atomicity không ngăn email trùng | Kết hợp transaction và DB constraint |
| Xem `save` trong JPA là đã ghi/commit | JPA có thể trì hoãn SQL đến flush/commit | Kiểm thử thời điểm exception và ranh giới transaction |
| Bắt lỗi rồi tiếp tục SQL trong PostgreSQL transaction bị abort | Transaction cần được rollback hoặc dùng savepoint | Để rollback xảy ra đúng mức; thiết kế retry có kiểm soát |
| Tự cập nhật schema production bằng JPA | Rủi ro lệch DDL và constraint | Quản lý migration, xác minh schema thật |

## 14. Bài tập thực hành

**Bài tập 1 — thiết kế:** Ứng dụng quản lý tài liệu đa tenant có `tenant_id`, `document_code`, `owner_id`, `status`. Yêu cầu mã tài liệu duy nhất **trong tenant**, owner bắt buộc tồn tại, status chỉ nhận `DRAFT`, `PUBLISHED` hoặc `ARCHIVED`. Hãy chọn PK, UNIQUE ghép, FK, NOT NULL, CHECK; giải thích hành vi khi xóa owner.

**Bài tập 2 — concurrency:** hai request đồng thời tạo khách hàng bằng cùng email. Viết timeline cho phép cả hai qua bước `SELECT`, sau đó giải thích kết quả khi DB có `UNIQUE` và cách API nên thông báo xung đột.

**Bài tập 3 — kiểm thử integration:** dùng schema ở mục 7 và test bốn trường hợp: tạo đúng, trùng `order_number`, `customer_id` không có thật, `qty = 0`. Tạo đơn và dòng trong một transaction, cố tình gây lỗi ở dòng thứ hai, xác nhận không còn đơn được commit. Kiểm tra riêng hành vi `RESTRICT` và `CASCADE`.

**Gợi ý đáp án:** Bài 1 có thể dùng surrogate `id` làm PK, `UNIQUE(tenant_id, document_code)`, `FOREIGN KEY(owner_id)` tới PK của bảng owner, `owner_id NOT NULL` và `CHECK(status IN (...))`; chính sách xóa owner phụ thuộc quy tắc lưu tài liệu và thường cần cân nhắc `RESTRICT`. Bài 2 cho thấy `UNIQUE` là điểm chốt bảo vệ concurrency. Bài 3 phải quan sát trạng thái DB **sau rollback/commit**, không chỉ kiểm tra có exception.

## 15. Checklist quyết định trước khi triển khai

- Mỗi bảng có khóa nhận diện ổn định chưa? Khóa ghép có thật sự là định danh nghiệp vụ không?
- Mọi quan hệ bắt buộc có `FK + NOT NULL` và hành vi `ON DELETE/UPDATE` đã được chốt chưa?
- Tính duy nhất đang áp dụng toàn bảng, theo tenant, theo trạng thái hay theo một biểu thức chuẩn hóa?
- DB có quy tắc đúng với NULL, collation, soft delete và xử lý concurrency không?
- Điều kiện miền giá trị đã có `NOT NULL/CHECK`; thao tác nhiều bảng đã có transaction phù hợp chưa?
- Index cho khóa được tra cứu và phía tham chiếu FK có phù hợp truy vấn thực tế không?
- Migration đã dò dữ liệu vi phạm, thử trên DBMS thật và có kế hoạch rollback/quan sát chưa?
- Lỗi gửi ra client có rõ nghĩa mà không rò rỉ SQL, stack trace hoặc dữ liệu nhạy cảm không?

**Ghi nhớ:** PK trả lời “hàng này là ai?”, UNIQUE trả lời “giá trị/tổ hợp nào không được trùng?”, FK trả lời “quan hệ này có hợp lệ?”, NOT NULL/CHECK trả lời “giá trị này có nằm trong miền cho phép?”, còn transaction trả lời “cả nhóm thay đổi có nhất quán khi commit/rollback?”. Hãy mô tả bất biến trước, triển khai constraint trong DB, rồi xây validation và xử lý lỗi trong Spring để cung cấp trải nghiệm phù hợp.

## Tài liệu tham khảo

- PostgreSQL — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- Spring Framework — JDBC core và exception translation: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transactional annotations và rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA — JpaRepository (flush, saveAndFlush): https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
