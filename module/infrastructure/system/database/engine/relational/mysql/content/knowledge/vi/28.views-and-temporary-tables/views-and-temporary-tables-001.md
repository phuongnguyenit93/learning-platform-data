# CREATE VIEW và sử dụng view làm ranh giới truy vấn

View trong MySQL là một đối tượng schema lưu định nghĩa của một câu `SELECT` và cho phép ứng dụng truy vấn định nghĩa đó như một bảng logic. View giúp đặt tên cho logic truy vấn dùng chung, che bớt cấu trúc bảng nền, chuẩn hóa cách lọc dữ liệu và tạo ranh giới giữa giao diện truy vấn của ứng dụng với mô hình lưu trữ.

View thông thường không lưu sẵn kết quả truy vấn. Khi ứng dụng đọc view, MySQL xử lý câu `SELECT` được định nghĩa trong view cùng truy vấn bên ngoài. Tùy cấu trúc, optimizer có thể merge view vào query block ngoài hoặc materialize kết quả trung gian bằng temporary table nội bộ. Vì vậy, view là ranh giới về tổ chức và ngữ nghĩa truy vấn; nó không tự động là cache, bảng vật lý hay cam kết tăng tốc.

Bài học tập trung vào `CREATE VIEW`, cách thiết kế view như một query boundary, khả năng cập nhật, `WITH CHECK OPTION`, algorithm `MERGE`/`TEMPTABLE`, quyền `SQL SECURITY`, kiểm tra metadata và cách đo hiệu năng. Phần bảng tạm chỉ được nhắc để phân biệt với view; bảng tạm có vòng đời và hành vi lưu trữ khác.

## 1. View là gì?

View là một đối tượng có tên trong schema, được định nghĩa bằng câu `SELECT`. Ứng dụng có thể đọc view gần giống như đọc bảng:

```sql
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN';
```

View không nhất thiết có dữ liệu riêng. Nó cung cấp một lớp truy vấn logic dựa trên một hoặc nhiều bảng, view khác và các biểu thức được phép trong định nghĩa `SELECT`.

Một view thường được dùng để:

- Đóng gói điều kiện lọc hoặc phép JOIN lặp lại.
- Cung cấp tên cột và cấu trúc kết quả ổn định cho ứng dụng.
- Ẩn một số cột nội bộ hoặc dữ liệu nhạy cảm.
- Tạo giao diện đọc đơn giản trên schema nhiều bảng.
- Tái sử dụng logic truy vấn và giảm sự lặp lại giữa nhiều service/report.
- Kiểm soát quyền truy cập thông qua `SQL SECURITY DEFINER` hoặc `INVOKER`.

View không thay thế ràng buộc dữ liệu, transaction, index hay thiết kế schema. Nếu một truy vấn trong view sai hoặc tốn kém, mọi truy vấn gọi view có thể kế thừa vấn đề đó.

## 2. Chuẩn bị bảng ví dụ

Các ví dụ dùng bảng khách hàng và đơn hàng:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY idx_customers_region_status (region_code, status)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_status (customer_id, status),
    KEY idx_orders_created (created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
) ENGINE=InnoDB;
```

Thêm dữ liệu nhỏ để thử:

```sql
INSERT INTO customers
    (customer_name, email, region_code, status)
VALUES
    ('An', 'an@example.test', 'VN', 'active'),
    ('Bình', 'binh@example.test', 'VN', 'inactive'),
    ('Chi', 'chi@example.test', 'SG', 'active');

INSERT INTO orders (customer_id, status, total_amount)
VALUES
    (1, 'paid', 120000.00),
    (1, 'pending', 80000.00),
    (3, 'paid', 250000.00);
```

Trong môi trường thật, bảo đảm ID được tạo như dự kiến hoặc lấy generated key từ driver; các ID cố định trong ví dụ chỉ nhằm minh họa dữ liệu lab vừa tạo.

## 3. Tạo view cơ bản

Cú pháp tổng quát:

```sql
CREATE
    [OR REPLACE]
    [ALGORITHM = {UNDEFINED | MERGE | TEMPTABLE}]
    [DEFINER = user]
    [SQL SECURITY {DEFINER | INVOKER}]
VIEW view_name [(column_list)]
AS select_statement
[WITH [CASCADED | LOCAL] CHECK OPTION];
```

Ví dụ tạo view chỉ hiển thị khách hàng đang hoạt động:

```sql
CREATE VIEW v_active_customers AS
SELECT
    customer_id,
    customer_name,
    email,
    region_code,
    created_at
FROM customers
WHERE status = 'active';
```

Đọc view:

```sql
SELECT customer_id, customer_name, region_code
FROM v_active_customers
WHERE region_code = 'VN'
ORDER BY customer_name;
```

Ứng dụng không cần lặp lại điều kiện `status = 'active'` ở mọi nơi. Nếu logic lọc thay đổi, có thể cập nhật định nghĩa view để các consumer dùng cùng một ranh giới truy vấn.

## 4. Đặt tên cột rõ ràng cho view

View có thể khai báo danh sách tên cột sau tên view hoặc dùng alias trong `SELECT`:

```sql
CREATE VIEW v_customer_contact (
    id,
    display_name,
    contact_email,
    region
) AS
SELECT
    customer_id,
    customer_name,
    email,
    region_code
FROM customers;
```

Danh sách cột giúp view cung cấp tên giao diện ổn định, không phụ thuộc tên cột nội bộ. Số lượng cột khai báo phải khớp với số cột trong kết quả `SELECT` và tên không được trùng.

Nên liệt kê cột cụ thể thay vì `SELECT *`. View là hợp đồng giữa schema và consumer; việc thêm cột vào bảng nền không nên vô tình làm thay đổi giao diện mà ứng dụng đang dựa vào.

Alias cũng giúp tránh trùng tên khi view JOIN nhiều bảng:

```sql
CREATE VIEW v_order_details AS
SELECT
    o.order_id,
    o.created_at AS order_created_at,
    o.status AS order_status,
    o.total_amount,
    c.customer_id,
    c.customer_name,
    c.region_code
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id;
```

## 5. View như một ranh giới truy vấn

Một query boundary có trách nhiệm cung cấp tập cột, phép lọc và quan hệ dữ liệu mà consumer cần. Ví dụ ứng dụng báo cáo chỉ cần thông tin khách hàng và tổng tiền đơn đã thanh toán:

```sql
CREATE VIEW v_customer_paid_totals AS
SELECT
    c.customer_id,
    c.customer_name,
    c.region_code,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total_amount), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
GROUP BY
    c.customer_id,
    c.customer_name,
    c.region_code;
```

Consumer có thể dùng:

```sql
SELECT customer_id, customer_name, paid_total
FROM v_customer_paid_totals
WHERE region_code = 'VN'
ORDER BY paid_total DESC;
```

View giúp consumer không cần biết phép JOIN, điều kiện trạng thái và phép tổng hợp. Tuy nhiên, vì view có `GROUP BY` và aggregate, nó không phải view có thể cập nhật trực tiếp. Mục tiêu của view này là đọc và tổng hợp.

Một ranh giới truy vấn tốt nên có:

- Tên phản ánh ý nghĩa nghiệp vụ.
- Danh sách cột tối thiểu và ổn định.
- Quy tắc lọc/JOIN được định nghĩa rõ.
- Kiểu dữ liệu và alias dễ hiểu.
- Quyền truy cập được giới hạn theo consumer.
- Kế hoạch thực thi được kiểm tra với truy vấn thật.

## 6. View không phải materialized view hay cache

MySQL không có native materialized view tự lưu kết quả của `CREATE VIEW`. Một view thông thường lưu định nghĩa `SELECT`; mỗi lần truy vấn, MySQL xử lý định nghĩa đó cùng câu truy vấn bên ngoài.

Điều này có nghĩa:

- Thay đổi dữ liệu trong bảng nền có thể xuất hiện ngay trong lần đọc view tiếp theo theo isolation/snapshot của transaction.
- View không có lịch refresh và không lưu snapshot kết quả độc lập.
- Không có index riêng được tạo trực tiếp trên view như một bảng vật lý thông thường.
- Hiệu năng phụ thuộc bảng nền, index, optimizer và cấu trúc truy vấn.

Nếu cần kết quả tổng hợp được lưu sẵn, có thể thiết kế summary table và quy trình cập nhật theo batch/event. Khi đó ứng dụng phải quản lý độ mới dữ liệu, tính nhất quán, refresh, khóa và phục hồi. Không gọi summary table là view thông thường.

## 7. ALGORITHM=MERGE và ALGORITHM=TEMPTABLE

MySQL có các thuật toán xử lý view:

| Algorithm | Cách hoạt động | Hệ quả |
| --- | --- | --- |
| `MERGE` | Gộp phần định nghĩa view vào query block bên ngoài | Optimizer có thể đẩy điều kiện và chọn access path trên bảng nền |
| `TEMPTABLE` | Materialize kết quả view vào temporary table nội bộ cho lần thực thi | Có thể cần tạo kết quả trung gian; view không cập nhật được |
| `UNDEFINED` | Để MySQL chọn cách xử lý phù hợp | Đây là lựa chọn mặc định nếu không chỉ định algorithm |

Ví dụ:

```sql
CREATE ALGORITHM = MERGE VIEW v_active_customers_merge AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

Với `MERGE`, truy vấn ngoài có thể được tối ưu cùng điều kiện trong view. Không có nghĩa MySQL chỉ thay chuỗi SQL bằng văn bản; đây là quá trình biến đổi query block ở optimizer.

Ví dụ yêu cầu `TEMPTABLE`:

```sql
CREATE ALGORITHM = TEMPTABLE VIEW v_paid_customer_totals AS
SELECT customer_id, SUM(total_amount) AS paid_total
FROM orders
WHERE status = 'paid'
GROUP BY customer_id;
```

Kết quả tổng hợp được materialize vào temporary table nội bộ khi view được sử dụng. Temporary table này phục vụ quá trình thực thi, không phải dữ liệu được lưu lâu dài giữa các câu lệnh.

## 8. Khi nào view không thể MERGE?

Một số cấu trúc làm view không thể được merge vào query block bên ngoài, ví dụ:

- Aggregate functions như `SUM()`, `COUNT()`.
- `DISTINCT`.
- `GROUP BY` hoặc `HAVING`.
- `LIMIT`.
- `UNION` hoặc `UNION ALL`.
- Window functions.
- Một số subquery hoặc biểu thức khác không tương thích với merge.

Khi không thể merge, MySQL có thể materialize view hoặc dùng cách xử lý khác theo algorithm và phiên bản. Nếu khai báo `ALGORITHM=MERGE` nhưng cấu trúc không hỗ trợ, MySQL có thể cảnh báo và xử lý theo `UNDEFINED`; hãy đọc warning và kiểm tra kế hoạch thay vì giả định yêu cầu MERGE đã được đáp ứng.

Đừng viết view tổng hợp thành `MERGE` chỉ để mong truy vấn nhanh. `GROUP BY` và aggregate thường yêu cầu một ranh giới kết quả riêng; optimizer phải giữ đúng ngữ nghĩa đó.

## 9. Điều kiện WHERE bên ngoài và predicate pushdown

Với view có thể merge, điều kiện của truy vấn ngoài có thể được kết hợp với điều kiện trong view để optimizer chọn access path tốt hơn.

Ví dụ:

```sql
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN'
  AND customer_id >= 1000;
```

Về mặt logic, truy vấn cần các khách hàng active ở VN có ID từ 1000. Nếu view merge được, optimizer có thể xử lý các điều kiện này cùng bảng `customers` và dùng index phù hợp.

Với view materialized, điều kiện bên ngoài có thể không được đẩy xuống qua ranh giới materialization theo cùng cách; kết quả trung gian có thể được tạo trước rồi mới lọc. Hành vi cụ thể phụ thuộc cấu trúc và phiên bản.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN'
  AND customer_id >= 1000;
```

So sánh với truy vấn trực tiếp trên `customers`. Đừng mặc định view luôn tạo overhead hoặc luôn miễn phí; kiểm tra plan và actual execution trên dữ liệu đại diện.

## 10. View có thể cập nhật hay chỉ đọc?

Một view có thể updatable nếu MySQL xác định được quan hệ đủ rõ giữa mỗi hàng view và hàng trong bảng nền. View đơn giản dựa trên một bảng thường có thể cập nhật:

```sql
CREATE VIEW v_customer_status AS
SELECT customer_id, customer_name, status
FROM customers;
```

Có thể thực hiện:

```sql
UPDATE v_customer_status
SET status = 'inactive'
WHERE customer_id = 1;
```

Lệnh này cập nhật bảng `customers` nền. View không lưu một bản sao riêng của hàng.

Không phải view nào cũng updatable. Các cấu trúc thường làm view không thể cập nhật gồm:

- Aggregate functions hoặc window functions.
- `DISTINCT`.
- `GROUP BY` hoặc `HAVING`.
- `UNION`/`UNION ALL`.
- Một số subquery trong select list hoặc cấu trúc không ánh xạ được về một hàng bảng nền.
- `ALGORITHM=TEMPTABLE`.

View JOIN nhiều bảng có các giới hạn riêng: một câu `UPDATE` qua join view chỉ có thể cập nhật một bảng nền tại một thời điểm; khả năng `INSERT` cũng bị giới hạn. Hãy kiểm tra khả năng updatable của định nghĩa view cụ thể, không suy luận chỉ từ việc câu `SELECT` chạy được.

## 11. WITH CHECK OPTION: giữ hàng được ghi nằm trong view

View có điều kiện lọc có thể updatable, nhưng một thao tác ghi qua view có thể làm hàng không còn thỏa điều kiện của view. `WITH CHECK OPTION` ngăn việc đó.

Tạo view chỉ chứa khách hàng active:

```sql
CREATE OR REPLACE VIEW v_active_customers AS
SELECT customer_id, customer_name, status, region_code
FROM customers
WHERE status = 'active'
WITH CASCADED CHECK OPTION;
```

Thao tác sau sẽ bị từ chối vì hàng sau cập nhật không còn thỏa `status = 'active'`:

```sql
UPDATE v_active_customers
SET status = 'inactive'
WHERE customer_id = 1;
```

`WITH CHECK OPTION` hữu ích khi view đóng vai trò ranh giới nghiệp vụ, chẳng hạn consumer chỉ được thao tác trên tập hàng active hoặc thuộc một khu vực.

Nó không thay thế authorization. Người dùng vẫn cần quyền phù hợp trên view; view và bảng nền phải được cấu hình quyền đúng.

## 12. LOCAL và CASCADED CHECK OPTION

Khi view được xây dựng trên một view khác, `CHECK OPTION` có thể có phạm vi khác nhau:

- `LOCAL`: kiểm tra điều kiện của view hiện tại.
- `CASCADED`: kiểm tra điều kiện của view hiện tại và các view nền có liên quan.
- Nếu không ghi `LOCAL` hoặc `CASCADED`, mặc định là `CASCADED`.

Ví dụ:

```sql
CREATE VIEW v_vn_customers AS
SELECT customer_id, customer_name, status, region_code
FROM customers
WHERE region_code = 'VN';

CREATE VIEW v_active_vn_customers AS
SELECT customer_id, customer_name, status, region_code
FROM v_vn_customers
WHERE status = 'active'
WITH CASCADED CHECK OPTION;
```

Ghi qua `v_active_vn_customers` phải giữ cả điều kiện `status = 'active'` lẫn `region_code = 'VN'` trong chuỗi view.

Khi dùng `LOCAL`, view ngoài kiểm tra điều kiện của chính nó; điều kiện của view nền không nhất thiết được áp dụng bởi check option ở lớp ngoài. Hãy thiết kế và kiểm thử rõ các lớp view nếu dùng view lồng nhau để làm ranh giới ghi.

## 13. SQL SECURITY DEFINER và INVOKER

View có thể thực thi kiểm tra quyền trên bảng nền theo danh tính của người định nghĩa hoặc người gọi:

| Chế độ | Danh tính dùng khi kiểm tra quyền đối với đối tượng nền | Ý nghĩa |
| --- | --- | --- |
| `SQL SECURITY DEFINER` | Definer của view | Consumer có thể được cấp quyền trên view mà không cần quyền trực tiếp trên mọi bảng nền |
| `SQL SECURITY INVOKER` | User gọi view | Consumer cần quyền phù hợp trên các đối tượng nền được truy cập |

Nếu không chỉ định, mặc định là `DEFINER`.

Ví dụ tạo view chạy theo quyền người gọi:

```sql
CREATE ALGORITHM = MERGE
SQL SECURITY INVOKER
VIEW v_public_customer_directory AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

Với `INVOKER`, user truy vấn view phải có quyền cần thiết trên bảng nền. Với `DEFINER`, MySQL kiểm tra quyền nền theo definer; tài khoản definer cần tồn tại và có quyền cần thiết.

## 14. View như một lớp phân quyền

Một view có thể chỉ công bố các cột cần thiết, chẳng hạn không đưa email hoặc dữ liệu nội bộ vào giao diện dành cho nhóm báo cáo:

```sql
CREATE DEFINER = 'report_viewer'@'localhost'
SQL SECURITY DEFINER
VIEW v_customer_public AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

Sau đó cấp quyền đọc view cho role/user phù hợp:

```sql
GRANT SELECT ON app_db.v_customer_public
TO 'report_reader'@'%';
```

Consumer chỉ được cấp `SELECT` trên view nếu không cần truy cập trực tiếp bảng nền. Cách này giúp tạo một bề mặt dữ liệu nhỏ hơn, nhưng phải quản lý definer cẩn thận.

Các nguyên tắc bảo mật:

- Dùng definer có quyền tối thiểu cần cho định nghĩa view.
- Không dùng tài khoản quản trị mạnh làm definer nếu không cần.
- Kiểm tra tài khoản definer còn tồn tại sau migration hoặc đổi user.
- Không đưa cột nhạy cảm vào view chỉ vì consumer hiện tại chưa chọn chúng.
- Kiểm tra quyền `SELECT`, `SHOW VIEW` và quyền cần thiết khi tạo/sửa view.
- Xác minh quyền với đúng user/role ứng dụng, không chỉ bằng tài khoản DBA.

View không phải cơ chế che giấu tuyệt đối nếu người dùng vẫn có quyền truy cập trực tiếp bảng nền hoặc có các đường truy cập khác. Quyền cần được thiết kế tổng thể.

## 15. CREATE OR REPLACE, ALTER VIEW và DROP VIEW

Khi cần thay đổi định nghĩa view, có thể dùng `CREATE OR REPLACE VIEW`:

```sql
CREATE OR REPLACE VIEW v_active_customers AS
SELECT customer_id, customer_name, email, region_code
FROM customers
WHERE status = 'active';
```

Hoặc:

```sql
ALTER VIEW v_active_customers AS
SELECT customer_id, customer_name, email, region_code
FROM customers
WHERE status = 'active';
```

Xóa view:

```sql
DROP VIEW IF EXISTS v_active_customers;
```

`CREATE OR REPLACE` thay định nghĩa view hiện có; cần quyền phù hợp, thường gồm quyền tạo view và quyền xóa đối tượng cũ. Không dùng nó như cách cập nhật bảng nền. Trước khi thay đổi view đang được nhiều ứng dụng sử dụng, kiểm tra các consumer và tính tương thích của danh sách cột.

Đổi tên cột, bỏ cột hoặc thay kiểu kết quả có thể làm ứng dụng lỗi dù view vẫn tạo được. Hãy xem view như API/schema contract và quản lý thay đổi có version hoặc migration phù hợp.

## 16. Xem định nghĩa và metadata của view

Xem định nghĩa view:

```sql
SHOW CREATE VIEW v_active_customers\G
```

Liệt kê view trong schema:

```sql
SHOW FULL TABLES
WHERE Table_type = 'VIEW';
```

Hoặc truy vấn metadata:

```sql
SELECT
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE();
```

`VIEW_DEFINITION` có thể bị giới hạn hoặc không hiển thị đầy đủ tùy quyền. `IS_UPDATABLE` là thông tin hữu ích để kiểm tra nhưng vẫn nên thử thao tác phù hợp trên môi trường kiểm thử.

Nếu bảng nền thay đổi, view có thể trở nên invalid hoặc không còn phù hợp với consumer. Dùng `SHOW CREATE VIEW`, kiểm tra metadata và kiểm thử lại truy vấn sau migration schema.

## 17. ORDER BY trong view không bảo đảm thứ tự kết quả cuối

Có thể định nghĩa `ORDER BY` trong một view, nhưng consumer không nên dựa vào đó như hợp đồng thứ tự cuối cùng. Nếu truy vấn ngoài có `ORDER BY` riêng, thứ tự của truy vấn ngoài được áp dụng; optimizer cũng có thể bỏ qua thứ tự bên trong view khi không cần thiết để giữ ngữ nghĩa.

Không nên:

```sql
CREATE VIEW v_recent_orders AS
SELECT order_id, customer_id, created_at
FROM orders
ORDER BY created_at DESC;
```

rồi giả định mọi câu:

```sql
SELECT * FROM v_recent_orders;
```

luôn trả về cùng thứ tự. Hãy đặt thứ tự ở truy vấn tiêu thụ:

```sql
SELECT order_id, customer_id, created_at
FROM v_recent_orders
ORDER BY created_at DESC, order_id DESC;
```

`ORDER BY` trong view chỉ là một phần của định nghĩa truy vấn; thứ tự ổn định cần được yêu cầu ở câu `SELECT` ngoài cùng.

## 18. View không nhận tham số

View không có tham số đầu vào như stored procedure/function. Không thể tạo view có cú pháp kiểu `v_orders(customer_id)` để truyền customer ID lúc gọi.

Thay vào đó, consumer thêm điều kiện:

```sql
SELECT order_id, status, total_amount
FROM v_order_details
WHERE customer_id = 42;
```

Nếu cần logic có tham số, có thể dùng stored procedure, function phù hợp hoặc để ứng dụng truyền bind parameter vào truy vấn trên view. Không nối chuỗi SQL từ input người dùng; luôn dùng prepared statement/parameter binding để tránh SQL injection.

## 19. View lồng nhau và quản lý phụ thuộc

View có thể tham chiếu view khác để tạo các lớp logic. Ví dụ:

```sql
CREATE VIEW v_vn_customers AS
SELECT customer_id, customer_name, status, region_code
FROM customers
WHERE region_code = 'VN';

CREATE VIEW v_active_vn_customers AS
SELECT customer_id, customer_name, region_code
FROM v_vn_customers
WHERE status = 'active';
```

Phân lớp có thể làm logic dễ tái sử dụng, nhưng quá nhiều tầng làm khó theo dõi dependency và đọc execution plan. Khi sửa bảng nền hoặc view ở lớp dưới, phải kiểm tra các view phía trên và consumer.

Không tạo vòng tham chiếu giữa các view. Đặt tên có quy ước, quản lý định nghĩa bằng migration và lưu script tạo view trong source control. Khi deploy, tạo hoặc cập nhật đối tượng theo thứ tự dependency.

## 20. View và temporary table khác nhau thế nào?

| Tiêu chí | View thông thường | Temporary table |
| --- | --- | --- |
| Đối tượng | Định nghĩa SELECT lưu trong schema | Bảng vật lý tạm được tạo trong session |
| Dữ liệu | Không lưu kết quả riêng | Lưu các hàng được insert hoặc materialize |
| Vòng đời | Tồn tại đến khi DROP/đổi schema | `CREATE TEMPORARY TABLE` tồn tại trong session, tự mất khi session kết thúc |
| Tái sử dụng | Nhiều session có thể truy vấn theo quyền | Chỉ session tạo bảng tạm nhìn thấy bảng đó |
| Index | Dùng index của bảng nền | Có thể tạo index trên temporary table |
| Mục tiêu | Đóng gói logic và giao diện truy vấn | Lưu tập dữ liệu trung gian theo session |
| Làm mới | Đọc dữ liệu nền theo snapshot của transaction | Dữ liệu tạm giữ theo thao tác đã ghi vào bảng |

View phù hợp khi muốn đặt tên cho logic truy vấn dùng chung. Temporary table phù hợp khi cần lưu kết quả trung gian để dùng qua nhiều câu lệnh trong một session hoặc cần index riêng cho tập dữ liệu tạm.

`ALGORITHM=TEMPTABLE` của view không biến view thành `CREATE TEMPORARY TABLE` do người dùng quản lý. Đó là temporary result nội bộ cho quá trình thực thi view, có vòng đời theo câu truy vấn.

## 21. Đo hiệu năng của view

Không thể kết luận view nhanh hay chậm chỉ từ việc có thêm một lớp tên. Hãy xem truy vấn được tối ưu thành kế hoạch nào:

```sql
EXPLAIN
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN';
```

So sánh với truy vấn trực tiếp:

```sql
EXPLAIN
SELECT customer_id, customer_name
FROM customers
WHERE status = 'active'
  AND region_code = 'VN';
```

Kiểm tra:

- View được merge hay materialize.
- Điều kiện ngoài có được đẩy xuống bảng nền không.
- Index nào được chọn và bao nhiêu hàng ước lượng cần đọc.
- Có temporary table, sort hoặc aggregate tốn kém không.
- Kết quả `EXPLAIN ANALYZE` có actual rows/loops khác estimate đáng kể không.

Trên MySQL 8.0.18 trở lên, có thể dùng `EXPLAIN ANALYZE` với truy vấn đọc phù hợp:

```sql
EXPLAIN ANALYZE
SELECT customer_id, customer_name
FROM v_active_customers
WHERE region_code = 'VN';
```

Lệnh này thực thi truy vấn. Chỉ chạy trên SELECT an toàn và cân nhắc tải nếu dữ liệu lớn hoặc production nhạy cảm.

## 22. Index thuộc bảng nền, không thuộc view

Không tạo index trực tiếp trên view thông thường trong MySQL. Nếu truy vấn qua view chậm do lọc hoặc JOIN, xem index của bảng nền.

Ví dụ view lọc khách hàng theo vùng và trạng thái:

```sql
CREATE VIEW v_active_customers AS
SELECT customer_id, customer_name, region_code
FROM customers
WHERE status = 'active';
```

Truy vấn consumer lọc thêm `region_code`. Index `(region_code, status)` có thể phù hợp với access pattern này:

```sql
SHOW INDEX FROM customers;
```

Trong DDL ở mục 2, index `(region_code, status)` đã được tạo dưới tên `idx_customers_region_status`. Dùng `SHOW INDEX` để xác nhận index hiện có trước khi thay đổi schema; không tạo lại index đã tồn tại. Thứ tự index phải dựa trên điều kiện thực tế, cardinality và workload. View chỉ cung cấp lớp truy vấn; index vẫn được quản lý ở bảng nền.

## 23. Các giới hạn và lưu ý khi thiết kế view

- View không nhận parameter; consumer phải lọc ở truy vấn ngoài hoặc dùng routine phù hợp.
- View không lưu kết quả lâu dài và không có index riêng.
- View có aggregate, `DISTINCT`, `GROUP BY`, `HAVING`, `UNION`, `LIMIT` hoặc window function thường không updatable và có thể không merge được.
- `TEMPTABLE` materialize kết quả cho lần thực thi và làm view không updatable.
- View JOIN nhiều bảng có giới hạn cập nhật; một câu UPDATE qua join view chỉ cập nhật một bảng nền tại một thời điểm.
- `ORDER BY` bên trong view không thay thế `ORDER BY` ở truy vấn ngoài.
- `SELECT *` làm giao diện view khó kiểm soát khi schema thay đổi.
- Definer có thể mất quyền hoặc bị xóa, khiến view lỗi khi thực thi.
- View lồng nhau quá sâu làm dependency và plan khó theo dõi.
- Quyền trên view không có ý nghĩa bảo mật nếu consumer vẫn được cấp quyền rộng trên bảng nền.

## 24. Quy trình thiết kế và triển khai view

1. Xác định consumer và dữ liệu họ thực sự cần.
2. Chốt tên view, danh sách cột và alias ổn định.
3. Viết `SELECT` nền và xác nhận kết quả đúng với NULL, duplicate và cardinality.
4. Quyết định view chỉ đọc hay cần updatable.
5. Nếu updatable, kiểm tra điều kiện hỗ trợ và cân nhắc `WITH CHECK OPTION`.
6. Chọn `SQL SECURITY DEFINER` hoặc `INVOKER` theo mô hình quyền.
7. Chọn algorithm mặc định trước; chỉ chỉ định MERGE/TEMPTABLE khi có lý do và đã đo.
8. Tạo view bằng migration và quản lý trong source control.
9. Cấp quyền tối thiểu cho consumer và kiểm tra definer.
10. Chạy `SHOW CREATE VIEW`, kiểm tra `INFORMATION_SCHEMA.VIEWS`.
11. Dùng `EXPLAIN`/`EXPLAIN ANALYZE` với các truy vấn consumer quan trọng.
12. Kiểm tra dependency sau migration bảng nền và triển khai có kế hoạch rollback.

## 25. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| View lưu sẵn kết quả SELECT | View thông thường lưu định nghĩa truy vấn | Dùng summary table nếu cần dữ liệu materialized |
| View luôn làm truy vấn chậm | View có thể merge vào query block ngoài | Kiểm tra EXPLAIN và execution plan |
| ALGORITHM=TEMPTABLE là bảng tạm do ứng dụng quản lý | Đó là kết quả trung gian nội bộ theo lần thực thi | Dùng CREATE TEMPORARY TABLE nếu cần lưu dữ liệu qua nhiều câu lệnh |
| View có GROUP BY vẫn cập nhật như bảng | Aggregate/GROUP BY thường làm view không updatable | Dùng view chỉ đọc hoặc cập nhật bảng nền bằng DML riêng |
| WITH CHECK OPTION là cơ chế cấp quyền | Nó kiểm tra hàng sau ghi vẫn thỏa điều kiện view | Thiết kế GRANT và SQL SECURITY riêng |
| DEFINER và INVOKER giống nhau | Chúng dùng danh tính khác nhau để kiểm tra quyền nền | Chọn theo mô hình least privilege |
| ORDER BY trong view bảo đảm thứ tự mọi lần đọc | Truy vấn ngoài cần ORDER BY của chính nó | Sắp xếp ở SELECT cuối |
| Có thể truyền tham số vào view | View không nhận tham số | Dùng bind parameter ở query ngoài hoặc routine |
| Có thể tạo index trực tiếp trên view | Index thuộc bảng nền | Tối ưu index/access path ở bảng nền |
| CREATE OR REPLACE luôn an toàn với consumer | Thay đổi cột có thể phá hợp đồng ứng dụng | Kiểm tra dependency và version schema |

## 26. Bài tập thực hành

1. Tạo bảng `customers` và `orders` theo ví dụ; tạo view `v_active_customers`.
2. Dùng view trong truy vấn có điều kiện `region_code`; so sánh kết quả với truy vấn trực tiếp trên bảng.
3. Tạo view có danh sách cột/alias riêng và kiểm tra `SHOW CREATE VIEW`.
4. Tạo view tổng hợp đơn đã thanh toán theo khách hàng; giải thích vì sao view này không updatable.
5. Tạo view đơn giản updatable; cập nhật một hàng qua view và kiểm tra bảng nền.
6. Thêm `WITH CASCADED CHECK OPTION`; thử cập nhật hàng để nó không còn thỏa điều kiện view và quan sát lỗi.
7. Tạo hai tầng view với điều kiện khác nhau; so sánh `LOCAL` và `CASCADED CHECK OPTION`.
8. Tạo một view với `SQL SECURITY INVOKER` và một view với `DEFINER`; thử bằng user có quyền khác nhau.
9. So sánh `ALGORITHM=MERGE` và `TEMPTABLE` bằng `EXPLAIN`; ghi nhận khác biệt kế hoạch.
10. Đặt `ORDER BY` trong view, sau đó truy vấn ngoài có `ORDER BY` khác; giải thích thứ tự kết quả.
11. Kiểm tra `INFORMATION_SCHEMA.VIEWS`, `IS_UPDATABLE`, `DEFINER` và `SECURITY_TYPE`.
12. So sánh view với `CREATE TEMPORARY TABLE` cho một tập kết quả trung gian được dùng qua nhiều câu lệnh.
13. Thử thay đổi schema bảng nền trên môi trường lab; xác minh view và consumer sau migration.

## 27. Ghi nhớ

View là đối tượng schema lưu định nghĩa `SELECT`, giúp đóng gói logic và tạo query boundary có tên, danh sách cột và quyền truy cập rõ ràng. View thông thường không lưu kết quả, không có index riêng và không phải cache/materialized view. Optimizer có thể merge view vào truy vấn ngoài hoặc materialize kết quả tạm theo algorithm; `MERGE`, `TEMPTABLE` và `UNDEFINED` có hành vi khác nhau.

View đơn giản trên một bảng có thể updatable; aggregate, `DISTINCT`, `GROUP BY`, `HAVING`, `UNION`, window function và `TEMPTABLE` thường làm view không updatable. `WITH CHECK OPTION` giữ hàng được ghi thỏa điều kiện view; `LOCAL` và `CASCADED` khác nhau ở phạm vi kiểm tra view nền. `SQL SECURITY DEFINER` dùng quyền definer, còn `INVOKER` dùng quyền người gọi; chọn definer tối thiểu và quản lý tài khoản đó cẩn thận. `ORDER BY` trong view không bảo đảm thứ tự cuối, view không nhận parameter và index phải được thiết kế trên bảng nền. Hãy quản lý view như hợp đồng truy vấn: liệt kê cột rõ ràng, quản lý migration/dependency, kiểm tra quyền và dùng `EXPLAIN`/`EXPLAIN ANALYZE` để xác nhận kế hoạch thực thi.
