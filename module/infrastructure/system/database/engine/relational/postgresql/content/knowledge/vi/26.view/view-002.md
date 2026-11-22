# Tạo, thay thế, đổi tên và xóa view trong PostgreSQL

Trong PostgreSQL, **view** là một đối tượng cơ sở dữ liệu đại diện cho một truy vấn SQL có tên. Thay vì viết lại những câu `SELECT` nhiều lần, người phát triển có thể tạo view một lần và truy vấn nó như một quan hệ:

~~~sql
SELECT *
FROM sales.v_order_summary;
~~~

Giả sử ứng dụng cần báo cáo đơn hàng gồm tên khách hàng, trạng thái, tổng tiền và thời điểm đặt hàng. Truy vấn gốc có thể phải `JOIN` bảng `orders` với `customers`. Một view giúp định nghĩa biểu diễn này tập trung, cho phép các report hoặc API dùng chung giao diện dữ liệu.

Tuy nhiên, view cũng có **vòng đời** như các đối tượng schema khác. Khi yêu cầu nghiệp vụ thay đổi, ta phải biết:

- **Tạo** view bằng `CREATE VIEW`.
- **Thay thế định nghĩa** bằng `CREATE OR REPLACE VIEW` mà không vô tình phá giao diện cột.
- **Đổi tên view hoặc cột** bằng `ALTER VIEW ... RENAME`.
- **Di chuyển view sang schema khác** bằng `ALTER VIEW ... SET SCHEMA` khi cần.
- **Xóa** bằng `DROP VIEW`, hiểu chính xác `RESTRICT`, `CASCADE` và tác động phụ thuộc.

Bài học **“Tạo, thay thế, đổi tên và xóa view”** thuộc chương **View**, module **Database Engine Relational PostgreSQL**. Nội dung đi từ cú pháp và ví dụ SQL thực hành đến quản lý phụ thuộc, quyền truy cập, view updatable, thay đổi tương thích, migration production, kiểm tra metadata và bài tập.

> **Nguyên tắc thực hành:** các lệnh DDL dưới đây dành cho **database thử nghiệm riêng**. Với view trong production, hãy kiểm tra ứng dụng đang sử dụng, dependent objects, quyền, migration và phương án rollback trước khi thay thế/đổi tên/xóa.

---

## 1. View là gì?

Một **view thông thường** là truy vấn được lưu dưới một tên trong schema:

~~~text
Ứng dụng
   |
   v
SELECT ... FROM v_order_summary
   |
   v
View định nghĩa SELECT/JOIN/WHERE
   |
   v
Bảng orders + customers
   |
   v
Kết quả gửi cho ứng dụng
~~~

Ví dụ:

~~~sql
CREATE VIEW sales.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount
FROM sales.orders
WHERE status = 'paid';
~~~

Sau đó:

~~~sql
SELECT *
FROM sales.v_paid_orders;
~~~

PostgreSQL lập kế hoạch để thực hiện logic của view trên các bảng/quan hệ nguồn. **View thông thường không lưu riêng một bản sao dữ liệu kết quả** như materialized view.

### 1.1. View khác bảng như thế nào?

| Thuộc tính | Bảng | View thông thường |
|---|---|---|
| Lưu dữ liệu hàng của chính đối tượng | Có | Không lưu kết quả SELECT riêng |
| Có SQL SELECT trực tiếp | Có | Có |
| Định nghĩa bằng | `CREATE TABLE` | `CREATE VIEW ... AS SELECT` |
| Tác động khi dữ liệu bảng gốc đổi | Chính dữ liệu bảng đổi | Kết quả view thay đổi ở lần truy vấn sau |
| Có thể tạo index trực tiếp | Có | Không trực tiếp trên view thường |
| Có thể INSERT/UPDATE/DELETE | Theo ràng buộc/quyền | Một số view tự cập nhật được, số khác cần cơ chế bổ sung |
| Xóa bằng | `DROP TABLE` | `DROP VIEW` |

Không dùng `DROP TABLE` để xóa view thông thường, và không dùng `DROP VIEW` cho một bảng.

### 1.2. View khác materialized view

**Materialized view** lưu kết quả truy vấn theo dạng được vật hóa và cần được refresh khi muốn cập nhật dữ liệu. Nó dùng các lệnh như `CREATE MATERIALIZED VIEW`, `REFRESH MATERIALIZED VIEW` và `DROP MATERIALIZED VIEW`.

Bài này tập trung vào **view thông thường**. Không mặc định `CREATE OR REPLACE VIEW` có thể áp dụng để thay định nghĩa materialized view.

## 2. Cú pháp cơ bản của CREATE VIEW

Dạng thường gặp:

~~~sql
CREATE VIEW schema_name.view_name AS
SELECT ...
FROM ...
WHERE ...;
~~~

Cú pháp PostgreSQL còn có những phần tùy chọn như:

~~~sql
CREATE [ OR REPLACE ] [ TEMP | TEMPORARY ] VIEW view_name
    [ (column_name [, ...]) ]
    [ WITH (view_option_name [= view_option_value] [, ...]) ]
AS
    query
    [ WITH [ CASCADED | LOCAL ] CHECK OPTION ];
~~~

Đây là sơ đồ cấu trúc cú pháp để đọc, không phải câu SQL chạy nguyên dạng; các dấu ngoặc vuông biểu thị phần tùy chọn.

PostgreSQL còn hỗ trợ **recursive view** trong các phiên bản hỗ trợ, sẽ được đề cập riêng ở phần sau.

### 2.1. Những thành phần quan trọng

- `CREATE VIEW` tạo đối tượng mới.
- `schema_name.view_name` định danh view; nên schema-qualify khi làm migration.
- `(column_name,...)` tùy chọn để đặt tên các cột output.
- `AS query` xác định truy vấn nguồn.
- `WITH (...)` đặt option như `security_barrier` và `security_invoker` ở phiên bản phù hợp.
- `WITH CHECK OPTION` liên quan kiểm tra khi ghi qua view tự cập nhật được.
- `OR REPLACE` cho phép cập nhật định nghĩa của **view đã tồn tại**, với những ràng buộc đặc biệt về cột.

### 2.2. Quyền và tên đối tượng

Để tạo view trong một schema, role cần quyền phù hợp đối với schema và các đối tượng tham chiếu. Một tên view chia sẻ namespace quan hệ với bảng, index, sequence và những đối tượng quan hệ khác trong cùng schema; không thể tạo trùng một tên đang chiếm dụng.

Không coi `CREATE VIEW` là cách vượt qua quyền schema/đối tượng.

## 3. Dựng dữ liệu lab tự chứa

Để các ví dụ nối tiếp nhau, dùng một schema riêng `view_lab`.

Trong **database thực hành trống**, chạy:

~~~sql
CREATE SCHEMA view_lab;

CREATE TABLE view_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE view_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES view_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    total_amount NUMERIC(12,2) NOT NULL
        CHECK (total_amount >= 0),
    placed_at TIMESTAMPTZ NOT NULL
);

INSERT INTO view_lab.customers (
    customer_id, customer_name, active
)
VALUES
    (101, 'Lan', TRUE),
    (102, 'Minh', TRUE),
    (103, 'Hà', FALSE);

INSERT INTO view_lab.orders (
    order_id, customer_id, status,
    total_amount, placed_at
)
VALUES
    (1001, 101, 'paid', 125000.00,
     TIMESTAMPTZ '2026-11-01 09:00:00+00'),
    (1002, 102, 'new',  89000.00,
     TIMESTAMPTZ '2026-11-02 10:00:00+00'),
    (1003, 101, 'cancelled', 50000.00,
     TIMESTAMPTZ '2026-11-03 11:00:00+00'),
    (1004, 103, 'paid', 220000.00,
     TIMESTAMPTZ '2026-11-04 12:00:00+00');

ANALYZE view_lab.customers;
ANALYZE view_lab.orders;
~~~

Bộ dữ liệu có 3 customers và 4 orders. Timestamp được nhập có timezone offset rõ ràng; cách hiển thị phụ thuộc `TimeZone` của session.

### 3.1. Vì sao dùng tên có schema?

Các ví dụ luôn sử dụng `view_lab.orders` thay vì `orders` để:

- Tránh nhầm bảng cùng tên trong schema khác.
- Dễ phân biệt đối tượng của bài thực hành.
- Hạn chế phụ thuộc `search_path`.
- Giúp migration rõ ràng.

Nếu `CREATE SCHEMA view_lab` hoặc bảng đã tồn tại, các lệnh tạo có thể lỗi. Không tự `DROP SCHEMA ... CASCADE` một schema chưa xác định chỉ để chạy lại lab.

## 4. Tạo view đầu tiên từ một bảng

Tạo view các đơn hàng đã thanh toán:

~~~sql
CREATE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status = 'paid';
~~~

Truy vấn:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM view_lab.v_paid_orders
ORDER BY order_id;
~~~

Kết quả logic:

| order_id | customer_id | total_amount |
|---:|---:|---:|
| 1001 | 101 | 125000.00 |
| 1004 | 103 | 220000.00 |

View không cần copy dữ liệu. Nếu một order được UPDATE thành `paid`, kết quả truy vấn view có thể phản ánh thay đổi đó theo quy tắc transaction snapshot.

### 4.1. Tên cột thường xuất phát từ SELECT

Các cột `order_id`, `customer_id`, `total_amount`, `placed_at` trở thành output columns của view.

Nếu dùng một biểu thức không đặt alias:

~~~sql
SELECT total_amount * 1.1
FROM view_lab.orders;
~~~

tên cột sinh ra có thể không phù hợp API/report. Khi tạo view, nên đặt **alias rõ ràng**.

## 5. Tạo view có biểu thức và alias

Ví dụ tạo view cho số tiền sau phí giả định 5%:

~~~sql
CREATE VIEW view_lab.v_order_amounts AS
SELECT
    o.order_id,
    o.total_amount AS base_amount,
    (o.total_amount * 1.05)::NUMERIC(14,2)
        AS amount_with_demo_fee
FROM view_lab.orders AS o;
~~~

Tên `amount_with_demo_fee` rõ ràng hơn tên mặc định của một biểu thức.

Trong ví dụ này, tỷ lệ 5% chỉ dùng để minh họa SQL; không phải quy tắc tài chính hay thuế mặc định.

### 5.1. Dùng danh sách tên cột ngay sau tên view

Có thể đặt tên đầu ra ở phần đầu:

~~~sql
CREATE VIEW view_lab.v_status_counts(
    order_status,
    order_count
) AS
SELECT
    status,
    COUNT(*)
FROM view_lab.orders
GROUP BY status;
~~~

Danh sách này cung cấp tên cho những cột tương ứng theo **thứ tự của SELECT**. Tránh làm danh sách tên lệch thứ tự biểu thức, vì kết quả dễ gây nhầm lẫn.

### 5.2. Chọn kiểu dữ liệu đầu ra có chủ đích

Một view là giao diện schema. Nếu một biểu thức thay đổi kiểu do cast hoặc thay literal, ứng dụng có thể bị ảnh hưởng. Sử dụng các cast rõ ràng khi cần ổn định kiểu đầu ra của view.

## 6. Tạo view có JOIN

Trong lab, báo cáo đơn hàng cần tên khách:

~~~sql
CREATE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Truy vấn:

~~~sql
SELECT *
FROM view_lab.v_order_summary
WHERE status = 'paid'
ORDER BY placed_at DESC;
~~~

Kết quả logic là hai orders đã thanh toán, có `customer_name`.

View có thể ẩn logic JOIN khỏi các consumer, nhưng không tự giảm số bảng mà PostgreSQL phải truy cập. Khi thực thi view, planner vẫn xem logic truy vấn và các bảng nguồn.

### 6.1. View không mặc định lưu kết quả JOIN

Nếu `view_lab.customers.customer_name` thay đổi, kết quả view có thể đổi khi truy vấn lại; không cần `REFRESH` view thông thường.

### 6.2. Không dùng view như một cách che giấu chi phí JOIN

Nếu view JOIN nhiều bảng rất lớn, query dùng view vẫn có thể đắt. View là **trừu tượng logic**, không tự là bộ nhớ đệm dữ liệu.

## 7. Tạo view có GROUP BY và tổng hợp

~~~sql
CREATE VIEW view_lab.v_customer_revenue AS
SELECT
    o.customer_id,
    COUNT(*) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_order_count,
    COALESCE(
        SUM(o.total_amount) FILTER (
            WHERE o.status = 'paid'
        ),
        0::NUMERIC
    ) AS paid_total
FROM view_lab.orders AS o
GROUP BY o.customer_id;
~~~

Query:

~~~sql
SELECT *
FROM view_lab.v_customer_revenue
ORDER BY customer_id;
~~~

Giải thích:

- View tổng hợp có thể cung cấp báo cáo tái sử dụng.
- `FILTER` chỉ tính những đơn `paid`.
- `COALESCE` thay SQL NULL của SUM không có input phù hợp thành 0.
- Các view có `GROUP BY`/aggregate thường **không tự cập nhật được** qua INSERT/UPDATE trực tiếp.

## 8. Không nên dựa vào thứ tự hàng của view

SQL là quan hệ không có thứ tự mặc định. Dù định nghĩa view có `ORDER BY` trong một số trường hợp, consumer vẫn nên nêu yêu cầu thứ tự ở **câu SELECT ngoài cùng**:

~~~sql
SELECT *
FROM view_lab.v_order_summary
ORDER BY placed_at DESC, order_id DESC;
~~~

Điều này đặc biệt quan trọng với:

- Phân trang.
- `LIMIT/OFFSET`.
- Kết quả API ổn định.
- Xuất báo cáo.
- So sánh snapshot.

Không coi thứ tự vật lý của bảng hoặc thứ tự tự nhiên của view là API contract.

## 9. SELECT * khi định nghĩa view

Ví dụ:

~~~sql
CREATE VIEW view_lab.v_orders_all AS
SELECT *
FROM view_lab.orders;
~~~

Khi tạo view, PostgreSQL phân tích truy vấn và thiết lập danh sách output columns. Nếu sau đó thêm một cột mới vào `view_lab.orders`, **view cũ không tự động có cột mới** chỉ vì định nghĩa ban đầu chứa `*`.

Đây là một khác biệt quan trọng so với giả định “view luôn lấy tất cả cột hiện có”.

### 9.1. Tại sao tránh SELECT * trong view công khai?

- Dễ tạo giao diện cột quá rộng.
- Khó xác định hợp đồng API.
- Khi thay đổi schema, có thể phải thay view bằng migration riêng.
- Có nguy cơ lộ trường nội bộ nếu thay view thiếu kiểm soát.
- Khó dự đoán phụ thuộc cột.

Nên liệt kê rõ những cột mà consumer thực sự cần.

## 10. Xem định nghĩa view vừa tạo

PostgreSQL cung cấp `pg_views`:

~~~sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_views
WHERE schemaname = 'view_lab'
ORDER BY viewname;
~~~

Để xem truy vấn định nghĩa một view:

~~~sql
SELECT pg_get_viewdef(
    'view_lab.v_order_summary'::regclass,
    TRUE
) AS view_definition;
~~~

`pg_get_viewdef` trả truy vấn được PostgreSQL tái dựng từ định nghĩa lưu trong system catalogs, không nhất thiết giữ nguyên whitespace, alias layout hay SQL text gốc từng ký tự.

### 10.1. Trong psql

Các meta-command thường dùng:

~~~text
\dv view_lab.*
\d+ view_lab.v_order_summary
~~~

- `\dv` liệt kê views.
- `\d+` mô tả chi tiết view, columns và định nghĩa khi phù hợp.

Đây là lệnh của **psql**, không phải SQL chuẩn để gửi qua JDBC.

## 11. CREATE OR REPLACE VIEW để thay định nghĩa

Cú pháp:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status IN ('paid', 'new');
~~~

Lệnh này thay truy vấn của view đã có nhưng giữ **giao diện các cột hiện có** giống trước: cùng tên, cùng thứ tự, cùng kiểu.

Kết quả mới gồm các đơn có trạng thái `paid` hoặc `new`.

### 11.1. Nếu view chưa tồn tại

`CREATE OR REPLACE VIEW` tạo view mới khi tên chưa có đối tượng view tương ứng. Nó không đòi một lệnh `CREATE VIEW` trước.

### 11.2. Nếu tên đã là table/materialized view

`OR REPLACE` không có nghĩa PostgreSQL sẽ tự biến bảng hoặc materialized view cùng tên thành regular view. Một đối tượng khác loại cùng tên có thể làm lệnh thất bại.

### 11.3. Vì sao chọn OR REPLACE?

Nó có thể thay định nghĩa view mà không cần xóa rồi tạo lại đối tượng, qua đó giảm tác động đến:

- Grants trên view hiện có.
- Identity/ownership của view.
- Dependent views khi giao diện cột vẫn tương thích.
- Comments/metadata được gắn với view.

Tuy nhiên, **phần logic truy vấn đã thay** có thể ảnh hưởng kết quả và quyền trên bảng nguồn. Compatibility về cột **không đồng nghĩa** semantics của ứng dụng không đổi.

## 12. Giới hạn quan trọng của CREATE OR REPLACE VIEW

Đối với view hiện có, định nghĩa mới phải giữ những output columns đang có theo:

1. **Tên cột**.
2. **Thứ tự cột**.
3. **Kiểu dữ liệu cột**.

PostgreSQL cho phép **thêm các output columns mới ở cuối** danh sách hiện có, nhưng không dùng `CREATE OR REPLACE VIEW` để tùy ý thay tên, đổi kiểu hay bỏ cột cũ.

Ví dụ view ban đầu:

~~~text
v_paid_orders:
  order_id       BIGINT
  customer_id    BIGINT
  total_amount   NUMERIC(12,2)
  placed_at      TIMESTAMPTZ
~~~

Định nghĩa mới giữ bốn cột đầu giống hệt và thêm một cột cuối có thể phù hợp.

### 12.1. Vì sao PostgreSQL giới hạn như vậy?

Một view khác hoặc ứng dụng có thể đang phụ thuộc vào danh sách cột cũ. Nếu thay đổi tùy ý một cách âm thầm, câu SQL đang chạy có thể diễn giải sai dữ liệu hoặc mất cột.

Giới hạn này giúp migration tương thích dễ dự đoán hơn, dù không thể bảo đảm mọi truy vấn ứng dụng vẫn đúng về nghiệp vụ.

## 13. Thêm cột mới bằng OR REPLACE

Giả sử cần thêm trạng thái ở **cuối view**:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    placed_at,
    status
FROM view_lab.orders
WHERE status IN ('paid', 'new');
~~~

Bốn cột cũ giữ nguyên thứ tự/kiểu, `status` được thêm ở cuối.

Truy vấn:

~~~sql
SELECT
    order_id,
    total_amount,
    status
FROM view_lab.v_paid_orders
ORDER BY order_id;
~~~

### 13.1. Không chen cột mới vào giữa

Định nghĩa:

~~~sql
-- Mẫu KHÔNG tương thích với cột cũ:
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    status,
    customer_id,
    total_amount,
    placed_at
FROM view_lab.orders;
~~~

có thể bị từ chối vì thứ tự/kiểu/tên của output columns đầu tiên đã khác. Nếu view chưa có cột `status`, nên thêm **ở cuối** để tuân cơ chế OR REPLACE.

### 13.2. Vì sao thêm cột vẫn cần kiểm tra consumer?

Ứng dụng dùng `SELECT *` hoặc ORM mapping theo vị trí có thể bị ảnh hưởng khi view có thêm cột. Vì vậy thay đổi tương thích ở mức PostgreSQL catalog chưa chắc tương thích với mọi consumer.

## 14. Không dùng OR REPLACE để đổi tên cột

Giả sử muốn đổi `customer_id` thành `buyer_id`.

Câu sau **không phải cách đúng** để rename cột của view hiện có:

~~~sql
-- Minh họa lệnh có thể bị PostgreSQL từ chối:
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id AS buyer_id,
    total_amount,
    placed_at,
    status
FROM view_lab.orders;
~~~

Vì cột thứ hai của view hiện tại vẫn mang tên `customer_id`, việc thay tên tại vị trí đó vi phạm contract của `CREATE OR REPLACE VIEW`.

Cách đúng là:

~~~sql
ALTER VIEW view_lab.v_paid_orders
RENAME COLUMN customer_id TO buyer_id;
~~~

Sau rename, những lần `CREATE OR REPLACE VIEW` tiếp theo phải đặt alias tương thích với tên mới:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id AS buyer_id,
    total_amount,
    placed_at,
    status
FROM view_lab.orders
WHERE status IN ('paid','new');
~~~

Đây là một ví dụ về sự khác nhau giữa **sửa định nghĩa truy vấn** và **đổi metadata tên cột**.

## 15. Không dùng OR REPLACE để đổi kiểu cột

Giả sử cột `total_amount` là `NUMERIC(12,2)`.

Nếu định nghĩa mới trả `total_amount::TEXT` ở đúng vị trí đó:

~~~sql
-- Có thể bị từ chối vì thay kiểu cột đang có:
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    buyer_id,
    total_amount::TEXT AS total_amount,
    placed_at,
    status
FROM view_lab.v_paid_orders;
~~~

ví dụ minh họa này còn tham chiếu chính view đang được thay thế, nên **không được chạy** như migration: nó tạo định nghĩa tự tham chiếu không hợp lệ trong trường hợp này. Điều cần hiểu là **đổi kiểu output cũ bằng OR REPLACE không được hỗ trợ tùy ý**.

Cách làm an toàn thường là **tạo view phiên bản mới** có kiểu mong muốn, cập nhật consumer rồi loại bỏ phiên bản cũ theo kế hoạch.

### 15.1. Cast rõ để giữ kiểu

Nếu một biểu thức được viết lại nhưng business semantics không đổi, dùng cast để giữ cột output cùng kiểu:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_order_amounts AS
SELECT
    o.order_id,
    o.total_amount AS base_amount,
    ROUND(o.total_amount * 1.05, 2)::NUMERIC(14,2)
        AS amount_with_demo_fee
FROM view_lab.orders AS o;
~~~

Các alias/cột/kiểu được giữ tương thích với định nghĩa của `v_order_amounts` đã tạo trước đó.

## 16. CREATE OR REPLACE không đồng nghĩa DROP rồi CREATE

So sánh:

**Phương án A — thay định nghĩa:**

~~~sql
CREATE OR REPLACE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status <> 'cancelled';
~~~

**Phương án B — xóa rồi tạo:**

~~~sql
-- Không nên coi là cách tương đương:
DROP VIEW view_lab.v_order_summary;

CREATE VIEW view_lab.v_order_summary AS
SELECT ...;
~~~

Khác biệt:

| Yếu tố | OR REPLACE | DROP + CREATE |
|---|---|---|
| Object identity | Giữ view hiện có | Tạo đối tượng mới |
| Grants/ownership | Thường giữ trên view cũ | Cần tái thiết lập trên đối tượng mới |
| Dependent objects | Giữ được nếu tương thích | DROP có thể bị chặn hoặc cần xử lý phụ thuộc |
| Comments | Gắn với view cũ có thể được giữ | Đối tượng mới cần thiết lập lại |
| Thay tên/kiểu/bỏ cột | Bị giới hạn | Có thể với đối tượng mới nhưng breaking |
| Tính an toàn migration | Thường phù hợp thay đổi tương thích | Có nguy cơ phá phụ thuộc |

Đừng dùng DROP + CREATE theo thói quen chỉ để chỉnh một điều kiện `WHERE`.

## 17. Thay view trong transaction

PostgreSQL hỗ trợ nhiều thao tác DDL một cách transactional.

Ví dụ trong lab:

~~~sql
BEGIN;

CREATE OR REPLACE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status <> 'cancelled';

SELECT COUNT(*) AS visible_orders
FROM view_lab.v_order_summary;

ROLLBACK;
~~~

Với transaction rollback, thay đổi định nghĩa ở ví dụ này không được commit. Đây là cách thử cú pháp và hành vi trong **môi trường lab**.

### 17.1. Transaction không tự làm migration vô hại

DDL vẫn cần lock. Transaction dài có thể giữ lock đến khi COMMIT/ROLLBACK và ảnh hưởng query khác. Trên production, không nên mở transaction DDL rồi chờ người vận hành kiểm tra thủ công quá lâu.

### 17.2. Không dùng ROLLBACK làm thay thế cho staging

Dù rollback có thể hoàn tác nhiều thay đổi schema, việc kiểm tra dependency, lock, tải và ứng dụng vẫn cần thực hiện trước khi triển khai.

## 18. Đổi tên view bằng ALTER VIEW

Cú pháp:

~~~sql
ALTER VIEW schema_name.old_view_name
RENAME TO new_view_name;
~~~

Ví dụ tạo view tạm cho rename:

~~~sql
CREATE VIEW view_lab.v_orders_for_rename AS
SELECT
    order_id,
    status
FROM view_lab.orders;
~~~

Đổi tên:

~~~sql
ALTER VIEW view_lab.v_orders_for_rename
RENAME TO v_order_status;
~~~

Truy vấn theo tên mới:

~~~sql
SELECT *
FROM view_lab.v_order_status
ORDER BY order_id;
~~~

### 18.1. RENAME TO chỉ nhận tên mới, không phải tên schema-qualified

Để rename trong cùng schema, viết:

~~~sql
ALTER VIEW view_lab.v_order_status
RENAME TO v_order_state;
~~~

Không viết tên đích dạng `view_lab.v_order_state` ở vị trí `TO`.

### 18.2. Rename không tạo alias tên cũ

Sau rename, SQL còn gọi `view_lab.v_order_status` có thể lỗi vì tên này không còn. Nếu cần tên cũ và tên mới cùng tồn tại trong giai đoạn chuyển tiếp, hãy tạo **một view wrapper riêng** theo chính sách phù hợp, không giả định RENAME giữ alias tự động.

## 19. Đổi tên cột view bằng ALTER VIEW

Cú pháp:

~~~sql
ALTER VIEW schema_name.view_name
RENAME COLUMN old_column TO new_column;
~~~

Ví dụ sau `v_paid_orders` đã có cột `buyer_id` ở phần trước thì không chạy lại cùng rename đó. Để minh họa độc lập trên view `v_order_state`:

~~~sql
ALTER VIEW view_lab.v_order_state
RENAME COLUMN status TO order_status;
~~~

Sau đó:

~~~sql
SELECT order_id, order_status
FROM view_lab.v_order_state
ORDER BY order_id;
~~~

### 19.1. Đổi tên cột không tự sửa tất cả SQL client

Ứng dụng gọi:

~~~sql
SELECT status FROM view_lab.v_order_state;
~~~

sẽ cần đổi sang `order_status`.

Các dependent views được PostgreSQL quản lý ở mức phụ thuộc nội bộ có thể tiếp tục tham chiếu cùng column identity, nhưng **SQL text bên ngoài DB**, code Java/ORM, dashboard và BI tools không tự được sửa. Phải tìm consumer và có migration plan.

### 19.2. Khác biệt rename với đổi alias trong CREATE OR REPLACE

- `ALTER VIEW ... RENAME COLUMN` thay metadata tên cột.
- `CREATE OR REPLACE VIEW` thay query, phải bảo toàn tên/kiểu/thứ tự các cột hiện có theo quy tắc.

Đây là ranh giới quan trọng khi bảo trì view.

## 20. Đổi tên view có ảnh hưởng dependency ra sao?

PostgreSQL quản lý các dependency nội bộ theo **object identity**, không chỉ chuỗi tên view.

Ví dụ tạo một view con:

~~~sql
CREATE VIEW view_lab.v_order_state_paid AS
SELECT order_id
FROM view_lab.v_order_state
WHERE order_status = 'paid';
~~~

Nếu sau đó đổi tên view cha:

~~~sql
ALTER VIEW view_lab.v_order_state
RENAME TO v_order_state_current;
~~~

view con có thể vẫn hợp lệ vì quan hệ dependency trỏ tới đối tượng cha, và PostgreSQL có thể tái dựng định nghĩa bằng tên mới.

Tuy nhiên:

- SQL trong ứng dụng gọi tên cũ sẽ không hoạt động.
- Các script migration hardcode tên cũ phải sửa.
- Functions dùng dynamic SQL strings có thể không có dependency được PostgreSQL phân tích trước.
- Các report bên ngoài DB không tự cập nhật.

**Object dependency được bảo toàn không đồng nghĩa mọi consumer theo tên đều an toàn.**

## 21. Di chuyển view sang schema khác

Cú pháp:

~~~sql
ALTER VIEW old_schema.view_name
SET SCHEMA new_schema;
~~~

Ví dụ trong lab:

~~~sql
CREATE SCHEMA view_reporting;

ALTER VIEW view_lab.v_order_amounts
SET SCHEMA view_reporting;
~~~

Tên đầy đủ sau khi di chuyển là:

~~~sql
SELECT *
FROM view_reporting.v_order_amounts
ORDER BY order_id;
~~~

### 21.1. Di chuyển schema khác với rename

- `RENAME TO` đổi **tên đối tượng** trong schema.
- `SET SCHEMA` đổi **schema chứa đối tượng**.
- Có thể thực hiện cả hai bằng hai lệnh riêng.

### 21.2. Quyền và consumer

Role thực hiện phải có quyền thích hợp trên view/schema nguồn và đích. Ứng dụng gọi tên đầy đủ `view_lab.v_order_amounts` sẽ phải đổi sang tên mới hoặc có wrapper/chuyển tiếp. `search_path` cũng có thể ảnh hưởng các câu SQL không schema-qualified.

**Không dùng SET SCHEMA chỉ để đổi cách tổ chức folder trong code** mà chưa kiểm tra quyền và consumer SQL.

## 22. Đổi owner của view

Ví dụ cú pháp:

~~~sql
ALTER VIEW view_lab.v_order_summary
OWNER TO reporting_owner;
~~~

`reporting_owner` là một role **giả định**; câu SQL chỉ chạy khi role này đã tồn tại và người thực hiện có quyền chuyển ownership theo quy tắc PostgreSQL.

Owner của view ảnh hưởng quyền quản trị đối tượng và, trong nhiều trường hợp, quyền truy cập các bảng nguồn của view theo chế độ mặc định.

### 22.1. Owner khác với người dùng view

Ứng dụng có thể chỉ được `GRANT SELECT` trên view. Nó không nhất thiết là owner và không có quyền `ALTER VIEW` hoặc `DROP VIEW`.

Nên tách:

- **Migration/owner role:** quản trị định nghĩa view.
- **Application role:** chỉ có quyền đọc/ghi phù hợp.
- **Base-table roles:** chịu quyền và row-level security tương ứng.

Không cấp ownership cho role ứng dụng chỉ để tránh một lỗi quyền tạm thời.

## 23. Tùy chọn WITH khi tạo hoặc thay view

Một số view options quan trọng gồm:

- `security_barrier`.
- `security_invoker` (được hỗ trợ từ PostgreSQL 15).
- `check_option` cho các trường hợp view có thể cập nhật.

Ví dụ:

~~~sql
CREATE VIEW view_lab.v_order_public
WITH (security_barrier = true) AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount
FROM view_lab.orders
WHERE status <> 'cancelled';
~~~

Hoặc điều chỉnh option của view hiện có:

~~~sql
ALTER VIEW view_lab.v_order_public
SET (security_barrier = true);
~~~

### 23.1. Không dùng option để thay đổi tùy ý cột

`ALTER VIEW ... SET (...)` điều chỉnh option, **không phải** thay `SELECT` hay danh sách cột. Muốn sửa định nghĩa query dùng `CREATE OR REPLACE VIEW` với các ràng buộc tương thích.

## 24. security_invoker và quyền trên bảng gốc

Ở những phiên bản PostgreSQL hỗ trợ, tạo view với:

~~~sql
CREATE VIEW view_lab.v_orders_invoker
WITH (security_invoker = true) AS
SELECT
    order_id,
    customer_id,
    status
FROM view_lab.orders;
~~~

Ý nghĩa: trong cơ chế security invoker, việc kiểm tra quyền trên những quan hệ cơ sở liên quan của view dùng quyền của **người gọi** thay vì áp dụng hành vi mặc định của view owner đối với các quan hệ bên dưới.

### 24.1. View mặc định và security_invoker

Theo cơ chế mặc định, người gọi thường cần quyền trên **view**, trong khi việc kiểm tra quyền với các quan hệ được tham chiếu bên dưới thường dựa trên **owner của view**. Vì vậy một view được cấp SELECT có thể giúp cung cấp một giao diện giới hạn cột/hàng mà không cấp SELECT trực tiếp trên toàn bảng nguồn.

Khi `security_invoker=true`, caller cần có quyền thích hợp đối với các đối tượng nguồn mà cơ chế invoker kiểm tra; `GRANT SELECT` chỉ trên view có thể không đủ.

### 24.2. Đây là vấn đề bảo mật, không chỉ cú pháp

Sử dụng security invoker ảnh hưởng cách kiểm tra đặc quyền và có thể tương tác với Row-Level Security (RLS). Hãy xác minh version, owner/role, grants và RLS thực tế trước khi thay đổi option trên view có dữ liệu nhạy cảm.

Không dùng view như giải pháp phân quyền duy nhất mà không kiểm tra các đường truy cập khác tới bảng nguồn.

## 25. security_barrier và giới hạn tối ưu

`security_barrier = true` được thiết kế cho những view cần kiểm soát thứ tự đánh giá một số điều kiện nhằm giảm nguy cơ rò rỉ qua các hàm không đủ tin cậy trong tình huống bảo mật tương ứng.

Nhưng:

- Nó **không** tự biến mọi view thành biên an toàn tuyệt đối.
- Những hàm `LEAKPROOF` và quy tắc planner vẫn có vai trò.
- Có thể ảnh hưởng việc đẩy predicate (predicate pushdown) và hiệu năng.
- Không thay authorization/RLS đã thiết kế.

Với view bảo mật, cần đánh giá **đúng cả hành vi phân quyền lẫn execution plan**, không thêm option chỉ vì nghe “security” là tốt hơn.

## 26. View tự cập nhật được (automatically updatable)

Không phải view nào cũng chỉ đọc.

Một view đơn giản trên một bảng có thể tự cập nhật được nếu thỏa các điều kiện của PostgreSQL:

~~~sql
CREATE VIEW view_lab.v_non_cancelled_orders AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status <> 'cancelled';
~~~

Trong những trường hợp đáp ứng điều kiện auto-updatable, PostgreSQL có thể cho phép:

~~~sql
UPDATE view_lab.v_non_cancelled_orders
SET total_amount = 130000.00
WHERE order_id = 1001;
~~~

Lệnh trên thực sự **thay đổi bảng nguồn**. Không chạy tùy tiện nếu cần giữ dữ liệu lab trước các phép quan sát khác.

### 26.1. Khi nào view không tự cập nhật được?

Những dạng có thể không auto-updatable gồm:

- `GROUP BY` hoặc aggregation.
- `DISTINCT`.
- `UNION`/set operations.
- Một số JOIN và query phức tạp.
- Các điều kiện khác không thỏa khả năng mapping trực tiếp một hàng view sang một hàng base relation.

Có thể dùng `INSTEAD OF` triggers hoặc rules trong những tình huống phù hợp để định nghĩa hành vi ghi, nhưng đó là **thiết kế riêng**, không mặc định.

### 26.2. Quyền INSERT/UPDATE/DELETE

Dù view auto-updatable, role vẫn phải có quyền thích hợp. View không phải một cơ chế bỏ qua grants, constraints hoặc transaction semantics.

## 27. WITH CHECK OPTION khi ghi qua view

Mặc định, nếu một view có:

~~~sql
WHERE status <> 'cancelled'
~~~

một số lệnh UPDATE qua view có thể khiến hàng sau cập nhật **không còn thỏa WHERE của view**, tức biến mất khỏi kết quả view sau khi thao tác.

Để kiểm tra điều kiện hiển thị với những thao tác ghi qua view tự cập nhật, dùng `WITH CHECK OPTION`:

~~~sql
CREATE VIEW view_lab.v_visible_orders AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status <> 'cancelled'
WITH CHECK OPTION;
~~~

Sau đó một UPDATE qua view cố đặt `status='cancelled'` có thể bị từ chối bởi CHECK OPTION, tùy cơ chế updatability và cấu trúc view.

### 27.1. CHECK OPTION khác CHECK constraint

- `CHECK OPTION` gắn với việc ghi **qua view** phù hợp.
- `CHECK (...)` constraint gắn với bảng và được kiểm tra trên các thao tác ghi vào bảng.

Nếu cập nhật trực tiếp bảng nguồn, CHECK OPTION của view không tự áp dụng như table constraint. Những bất biến phải luôn đúng trong mọi đường ghi nên được bảo vệ ở tầng database constraints/RLS/logic thích hợp.

## 28. LOCAL và CASCADED CHECK OPTION

Khi một view dựa trên view khác, có hai cách phạm vi kiểm tra:

- `WITH LOCAL CHECK OPTION` kiểm tra điều kiện của **view hiện tại** theo quy tắc áp dụng.
- `WITH CASCADED CHECK OPTION` kiểm tra cả các điều kiện của những underlying automatically updatable views thích hợp trong chuỗi.
- `WITH CHECK OPTION` mặc định theo chế độ cascaded trong những ngữ cảnh hỗ trợ.

Ví dụ:

~~~sql
CREATE VIEW view_lab.v_non_cancelled_base AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status <> 'cancelled';

CREATE VIEW view_lab.v_large_visible_orders AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.v_non_cancelled_base
WHERE total_amount >= 100000
WITH CASCADED CHECK OPTION;
~~~

Một lệnh ghi qua `v_large_visible_orders` phải xem cả điều kiện tổng tiền và điều kiện trạng thái trong chuỗi automatically updatable view theo các quy tắc CHECK OPTION.

### 28.1. Có những ngoại lệ cần biết

Cơ chế CHECK OPTION có giới hạn đối với những view dùng `INSTEAD OF` triggers/rules và những dạng view không automatically updatable. Vì vậy không dựa vào CHECK OPTION như toàn bộ policy engine cho mọi view complex.

Nếu invariant quan trọng, hãy thực hiện kiểm thử chức năng ghi trong staging và giữ ràng buộc dữ liệu ở nơi thích hợp.

## 29. Tạo temporary view

Một temporary view tồn tại trong phạm vi session theo quy tắc của PostgreSQL:

~~~sql
CREATE TEMP VIEW temp_order_ids AS
SELECT order_id
FROM view_lab.orders
WHERE status = 'paid';
~~~

Truy vấn:

~~~sql
SELECT *
FROM temp_order_ids;
~~~

### 29.1. Khi nào phù hợp?

- Thử nghiệm trong session.
- Phân tích dữ liệu tạm.
- Một số workflow cần object sống ngắn hạn.

Không dùng temporary view làm API contract chia sẻ giữa các connections.

### 29.2. Session khác không tự nhìn thấy

Temporary view gắn với session/temporary schema. Connection pool có nhiều backend sessions; một temp view được tạo ở connection A không xuất hiện như cùng object cho connection B.

### 29.3. Tên và schema

Temporary objects có quy tắc namespace riêng; không nên dùng tên trùng object quan trọng rồi dựa vào `search_path` để đoán PostgreSQL sẽ resolve đối tượng nào.

## 30. Recursive view ở mức khái niệm

PostgreSQL hỗ trợ cú pháp tạo recursive view trong ngữ cảnh phù hợp, ví dụ làm việc với cây phân cấp.

Một cách rõ ràng để học truy vấn đệ quy là trước hết viết:

~~~sql
WITH RECURSIVE nums(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM nums
    WHERE n < 5
)
SELECT n
FROM nums;
~~~

Sau đó có thể đặt định nghĩa truy vấn như vậy trong một view phù hợp:

~~~sql
CREATE VIEW view_lab.v_numbers_1_to_5 AS
WITH RECURSIVE nums(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM nums
    WHERE n < 5
)
SELECT n
FROM nums;
~~~

Đây vẫn là view thông thường; kết quả được tính khi truy vấn. Cần bảo đảm điều kiện dừng recursion để tránh sinh quá nhiều rows.

Chủ đề chính của bài vẫn là **tạo, thay thế, rename và drop**, không phải tối ưu mọi loại recursive query.

## 31. DROP VIEW: xóa view

Cú pháp:

~~~sql
DROP VIEW view_lab.view_name;
~~~

Ví dụ với view độc lập đã tạo:

~~~sql
DROP VIEW view_lab.v_orders_all;
~~~

Lệnh xóa **định nghĩa view**, không xóa dữ liệu trong bảng `view_lab.orders` mà view tham chiếu.

### 31.1. Có thể xóa nhiều views trong một lệnh

~~~sql
DROP VIEW
    view_lab.v_status_counts,
    view_lab.v_customer_revenue;
~~~

Chỉ thực hiện khi đã kiểm tra cả hai view không còn cần thiết và không có dependent objects cần giữ.

### 31.2. DROP VIEW không xóa bảng nguồn

Sau:

~~~sql
DROP VIEW view_lab.v_order_public;
~~~

bảng `view_lab.orders` vẫn tồn tại. Các DML đã thực hiện thông qua view trước đó cũng **không tự rollback** vì việc xóa định nghĩa view.

## 32. DROP VIEW IF EXISTS

Cú pháp:

~~~sql
DROP VIEW IF EXISTS view_lab.v_optional_report;
~~~

Nếu view không tồn tại, PostgreSQL không coi đó là lỗi thiếu đối tượng và có thể phát NOTICE.

Hữu ích trong một số script idempotent, nhưng cần dùng cẩn thận.

### 32.1. IF EXISTS không cho phép xóa nhầm loại đối tượng

Nếu tên đang là một **table** hoặc object khác, `DROP VIEW IF EXISTS` không có nghĩa PostgreSQL sẽ xóa đối tượng đó như view.

### 32.2. IF EXISTS có thể che giấu migration sai

Trong một migration production đáng lẽ phải xóa view tồn tại chắc chắn, `IF EXISTS` có thể bỏ qua một lỗi quản lý schema khi view thiếu.

Hãy dùng `IF EXISTS` khi việc không tồn tại là một trạng thái **được chấp nhận theo thiết kế**, không phải vì muốn bỏ qua mọi lỗi.

## 33. DROP VIEW RESTRICT: mặc định bảo vệ dependency

PostgreSQL mặc định dùng hành vi **RESTRICT** nếu không chỉ rõ CASCADE.

~~~sql
DROP VIEW view_lab.some_view RESTRICT;
~~~

Nếu một view khác phụ thuộc vào view đó, PostgreSQL sẽ từ chối xóa cho tới khi dependent objects được xử lý.

Ví dụ trong lab:

~~~sql
CREATE VIEW view_lab.v_order_summary_paid AS
SELECT
    order_id,
    customer_name,
    total_amount
FROM view_lab.v_order_summary
WHERE status = 'paid';
~~~

`v_order_summary_paid` phụ thuộc `v_order_summary`. Khi đó:

~~~sql
-- Minh họa lệnh bị chặn khi còn dependency:
DROP VIEW view_lab.v_order_summary;
~~~

PostgreSQL có thể báo lỗi vì dependent view vẫn tồn tại.

### 33.1. RESTRICT giúp gì?

Nó tránh việc một thao tác xóa view cha **âm thầm** kéo theo xóa những objects phụ thuộc.

Trong môi trường production, nên mặc định xem lỗi dependency là **tín hiệu cần phân tích**, không phải lý do bật CASCADE ngay.

## 34. DROP VIEW CASCADE: tác động dây chuyền

Cú pháp:

~~~sql
DROP VIEW view_lab.v_order_summary CASCADE;
~~~

Nếu còn dependent views và các dependent database objects được PostgreSQL theo dõi, CASCADE có thể xóa chúng theo quan hệ phụ thuộc.

Ví dụ:

~~~text
v_order_summary
        |
        +--> v_order_summary_paid
                  |
                  +--> v_paid_report_nested
~~~

Xóa `v_order_summary CASCADE` có thể xóa cả những dependent views trong chuỗi.

### 34.1. Rủi ro lớn của CASCADE

- Xóa objects không nằm trong danh sách mong muốn ban đầu.
- Làm hỏng dashboards hoặc ứng dụng sử dụng dependent views.
- Xóa một tầng API contract đang được dùng.
- Phá các migration khác phụ thuộc vào object đó.
- Làm mất metadata/grants/comments gắn với những views bị xóa.

**Không coi CASCADE là công tắc “sửa lỗi dependency”.** Trước khi dùng, cần hiểu **toàn bộ closure của dependent objects** và có phương án phục hồi.

### 34.2. CASCADE không đồng nghĩa xóa mọi bảng gốc

Xóa một view với CASCADE không tự biến các bảng nguồn thành objects phụ thuộc vào view. Bảng nguồn thông thường **vẫn tồn tại**. CASCADE xử lý những objects **phụ thuộc vào view đang bị xóa**, không phải mọi đối tượng mà view đọc.

## 35. Xóa dependent views theo thứ tự thủ công

Khi muốn kiểm soát chính xác các objects bị xóa:

~~~sql
DROP VIEW view_lab.v_order_summary_paid;

DROP VIEW view_lab.v_order_summary;
~~~

Lúc này view con được xóa trước, sau đó view cha.

### 35.1. Tại sao cách thủ công có thể tốt hơn CASCADE?

- Danh sách objects rõ ràng trong migration.
- Code review thấy từng tên view bị xóa.
- Ít bất ngờ nếu xuất hiện dependency mới chưa được duyệt.
- Có thể thêm bước chuyển consumer giữa những lần thay đổi.

Tuy nhiên migration thủ công vẫn cần kiểm tra đầy đủ dependency và thực thi trong transaction khi phù hợp.

## 36. Dependency có thể là view → view, không chỉ view → table

Ví dụ:

~~~text
orders (bảng)
  |
  v
v_paid_orders (view)
  |
  v
v_paid_orders_api (view)
  |
  v
Dashboard/SQL client
~~~

PostgreSQL theo dõi dependency ở cấp database object thông qua system catalogs. Những consumer bên ngoài như source code Java, dashboard URL hay query trong một service khác không phải lúc nào cũng được PostgreSQL biết tới.

Vì vậy cần **hai bản đồ phụ thuộc**:

1. **Database dependency graph**: views/rules/functions/objects được catalog theo dõi.
2. **Application dependency graph**: code, ORM, reports, jobs, BI, migrations.

Một view không còn dependent object trong catalog **chưa chắc** là view không còn ai sử dụng.

## 37. Hậu quả của DROP + CREATE với grants

Giả sử role `app_reader` được cấp quyền:

~~~sql
GRANT SELECT ON view_lab.v_paid_orders TO app_reader;
~~~

`app_reader` là role giả định, lệnh chỉ chạy nếu role đã tồn tại và người thực hiện có quyền.

Nếu thay định nghĩa bằng `CREATE OR REPLACE VIEW` tương thích, grants gắn với view hiện có thường được giữ.

Nếu:

~~~sql
DROP VIEW view_lab.v_paid_orders;
CREATE VIEW view_lab.v_paid_orders AS ...;
~~~

đó là **đối tượng mới** và quyền của view cũ không được tự sao chép đầy đủ sang object mới theo phép DROP/CREATE. Cần kiểm tra và thiết lập lại grants, ownership, comments và các đặc tính cần thiết.

### 37.1. Một migration tốt không chỉ xét câu SELECT

Sau thay đổi view, nên xác nhận:

- Role nào được SELECT?
- Có role nào được INSERT/UPDATE/DELETE?
- Owner có đúng không?
- Có security_invoker/barrier option?
- Có RLS/privilege implications?
- Có object comments cần giữ?
- Có dependent views còn hợp lệ?

## 38. Xem grants và quyền trên view

Có thể dùng `information_schema.table_privileges` trong những ngữ cảnh mà thông tin quyền hiển thị phù hợp:

~~~sql
SELECT
    table_schema,
    table_name,
    grantee,
    privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'view_lab'
ORDER BY table_name, grantee, privilege_type;
~~~

Hoặc xem trong psql:

~~~text
\dp view_lab.*
\d+ view_lab.v_paid_orders
~~~

Lưu ý rằng kết quả visibility của information_schema phụ thuộc các quyền và context người gọi.

### 38.1. Xác minh quyền bằng role ứng dụng

Một query chạy thành công dưới migration owner không chứng minh ứng dụng có quyền. Cần kiểm thử bằng role/connection context gần ứng dụng thật.

Không nâng quyền role ứng dụng quá mức chỉ để làm một view query hoạt động.

## 39. Row-Level Security và view

Nếu bảng `view_lab.orders` được áp dụng Row-Level Security, các policy có thể tương tác với cách view kiểm tra quyền:

- View mặc định có những quy tắc quyền/policy liên quan owner.
- View `security_invoker=true` trong những phiên bản hỗ trợ dùng context người gọi cho các kiểm tra liên quan.

Điều này có thể khiến hai views chứa **cùng SELECT** trả dữ liệu khác nhau theo role và RLS configuration.

### 39.1. Không dùng view làm ranh giới tenant duy nhất khi thiếu kiểm chứng

Ví dụ một view:

~~~sql
CREATE VIEW view_lab.v_customer_101_orders AS
SELECT
    order_id,
    customer_id,
    status
FROM view_lab.orders
WHERE customer_id = 101;
~~~

Đây là điều kiện lọc hiển thị, nhưng không thay toàn bộ logic authorization/tenant scoping của hệ thống. Cần kiểm tra grants, RLS và việc người dùng có thể truy cập bảng nguồn/đối tượng khác hay không.

## 40. Gắn COMMENT cho view và cột

PostgreSQL cho phép lưu mô tả:

~~~sql
COMMENT ON VIEW view_lab.v_paid_orders IS
'Giao diện đơn hàng trạng thái paid hoặc new cho ví dụ học tập';
~~~

Có thể comment cột:

~~~sql
COMMENT ON COLUMN view_lab.v_paid_orders.total_amount IS
'Số tiền của đơn hàng tính theo đơn vị tiền tệ hệ thống';
~~~

Comments giúp người quản trị hiểu mục đích và contract.

### 40.1. Comment không phải constraint

Mô tả cột là tài liệu, không tự kiểm tra giá trị. Ràng buộc nghiệp vụ cần CHECK/NOT NULL/FK, logic hoặc policy tương ứng.

### 40.2. DROP + CREATE mất metadata cũ

Nếu xóa và tạo đối tượng mới, cần thiết lập lại comments. Vì thế khi thay định nghĩa tương thích, `CREATE OR REPLACE VIEW` thường đơn giản và ít phá hoại hơn.

## 41. View trong system catalogs

PostgreSQL quản lý view trong hệ thống metadata.

Một số catalog:

- `pg_class`: đối tượng relation, bao gồm view với `relkind='v'`.
- `pg_namespace`: schema chứa view.
- `pg_attribute`: các cột output và kiểu.
- `pg_rewrite`: rule biểu diễn định nghĩa truy vấn view.
- `pg_depend`: quan hệ phụ thuộc object.
- `pg_description`: comments.

Xem các view trong `view_lab`:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    c.oid AS view_oid,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'view_lab'
  AND c.relkind = 'v'
ORDER BY c.relname;
~~~

`relkind='v'` biểu thị regular view. Materialized view có mã relkind khác.

### 41.1. Không tự sửa pg_catalog

Đừng UPDATE trực tiếp `pg_class`, `pg_rewrite` hoặc `pg_depend` để rename/xóa/replace view. Dùng lệnh DDL chính thức để PostgreSQL duy trì metadata và dependency nhất quán.

## 42. Xem cột view qua information_schema

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    ordinal_position,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'view_lab'
  AND table_name = 'v_paid_orders'
ORDER BY ordinal_position;
~~~

Truy vấn giúp xác nhận:

- Tên cột.
- Vị trí cột.
- Kiểu.
- Một phần metadata chuẩn.

Khi cần kiểu PostgreSQL cụ thể (ví dụ `NUMERIC(12,2)` hoặc kiểu tự định nghĩa), có thể dùng metadata phong phú hơn từ `pg_catalog` hoặc `format_type`.

### 42.1. Một query nhìn kiểu cột cụ thể

~~~sql
SELECT
    a.attnum AS column_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS sql_type
FROM pg_attribute AS a
WHERE a.attrelid = 'view_lab.v_paid_orders'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Đây là một cách quan sát giao diện cột hiện tại trước khi viết `CREATE OR REPLACE VIEW`.

## 43. Xem view definition bằng pg_get_viewdef

~~~sql
SELECT pg_get_viewdef(
    'view_lab.v_paid_orders'::regclass,
    TRUE
);
~~~

Phù hợp khi:

- Muốn biết logic `WHERE`/`JOIN` thực tế.
- Kiểm tra migration đã thay query chưa.
- So định nghĩa view trước/sau.
- Tìm base tables theo cú pháp có thể đọc.

### 43.1. Không mặc định output giống nguyên văn CREATE VIEW

PostgreSQL có thể tái dựng/chuẩn hóa cách hiển thị truy vấn. `pg_get_viewdef` không nhất thiết trả lại y nguyên SQL text migration, options, grants hay comments.

Muốn tái tạo đầy đủ một view trong migration, cần quản lý **định nghĩa SQL nguồn** cùng options, grants, comments và dependencies, không chỉ sao chép một chuỗi từ `pg_get_viewdef`.

## 44. Phụ thuộc trong pg_depend

Trong catalog PostgreSQL, định nghĩa một view thông thường được lưu dưới dạng rewrite rule; dependencies vào bảng/cột nguồn có thể được gắn với rule đó.

Vì vậy khi tìm dependency, không phải lúc nào chỉ tìm `pg_depend.objid = view_oid` là thấy mọi tham chiếu bảng bên dưới.

### 44.1. Truy vấn ví dụ nhìn relation dependencies của rule view

~~~sql
SELECT
    vn.nspname AS view_schema,
    vc.relname AS view_name,
    r.rulename,
    rn.nspname AS referenced_schema,
    rc.relname AS referenced_relation,
    d.refobjsubid AS referenced_column_number
FROM pg_rewrite AS r
JOIN pg_class AS vc
    ON vc.oid = r.ev_class
JOIN pg_namespace AS vn
    ON vn.oid = vc.relnamespace
JOIN pg_depend AS d
    ON d.classid = 'pg_rewrite'::regclass
   AND d.objid = r.oid
JOIN pg_class AS rc
    ON d.refclassid = 'pg_class'::regclass
   AND d.refobjid = rc.oid
JOIN pg_namespace AS rn
    ON rn.oid = rc.relnamespace
WHERE vn.nspname = 'view_lab'
  AND vc.relkind = 'v'
  AND r.rulename = '_RETURN'
  AND rc.oid <> vc.oid
ORDER BY vc.relname, rc.relname, d.refobjsubid;
~~~

Truy vấn này nhằm **quan sát một tập dependencies vào relations** của rewrite rules. Nó không phải công cụ vẽ đồ thị đầy đủ mọi loại object dependency, và có thể xuất hiện nhiều hàng cho cùng referenced table khi phụ thuộc nhiều cột.

Không tự suy rằng chỉ cần query này là an toàn dùng `DROP ... CASCADE` trong production. Cần xem toàn bộ dependency closure, cả consumer bên ngoài DB.

## 45. information_schema.views và pg_views

Có thể xem views qua giao diện tương đối chuẩn:

~~~sql
SELECT
    table_schema,
    table_name,
    view_definition,
    check_option,
    is_updatable
FROM information_schema.views
WHERE table_schema = 'view_lab'
ORDER BY table_name;
~~~

`information_schema` có quy tắc visibility theo quyền, nên kết quả của role hạn chế có thể khác metadata PostgreSQL-specific từ system catalogs.

`pg_views` thuận tiện cho metadata views PostgreSQL; `pg_get_viewdef` giúp xem định nghĩa theo object cụ thể.

### 45.1. Phân biệt view không tồn tại và không có quyền xem

Nếu role ứng dụng không thấy một view trong truy vấn metadata, đừng lập tức kết luận object bị xóa. Kiểm tra schema, `search_path`, role/privileges và visibility của metadata.

## 46. Hiệu năng khi sửa view

Vì regular view lưu định nghĩa query chứ không cache kết quả, thay đổi `SELECT` trong view có thể tác động execution plan của mọi consumer.

Ví dụ thêm filter:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status IN ('paid','new');
~~~

Sau đó:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_lab.v_order_summary
WHERE total_amount >= 100000;
~~~

Có thể thấy planner dùng `Seq Scan`, `Index Scan`, `Hash Join`, `Nested Loop` hoặc chiến lược khác. View không bảo đảm một execution plan cố định.

### 46.1. Index đặt ở bảng nguồn

Với regular view, tối ưu đọc thường đến từ index trên các base tables hoặc thay đổi truy vấn, không phải tạo index trực tiếp trên view thông thường:

~~~sql
CREATE INDEX idx_orders_status_amount
ON view_lab.orders(status, total_amount);
~~~

Không mặc định index này chắc chắn được dùng. Đo `EXPLAIN`/`BUFFERS` và chi phí DML trước khi triển khai index production.

### 46.2. security_barrier có thể ảnh hưởng planner

Nếu bật barrier, một số predicate pushdown có thể khác. Với view phục vụ phân quyền, phải kiểm cả tính đúng bảo mật lẫn latency.

## 47. Tạo view mới để thay giao diện không tương thích

Khi phải:

- Xóa cột đang dùng.
- Đổi tên cột public.
- Đổi kiểu từ BIGINT sang TEXT hoặc ngược lại.
- Đổi ý nghĩa của cột.
- Thay thứ tự cột mà consumer dựa vào.

`CREATE OR REPLACE VIEW` thường **không** giải quyết được theo cách an toàn.

Một chiến lược rõ hơn:

~~~sql
CREATE VIEW view_lab.v_order_summary_v2 AS
SELECT
    o.order_id,
    o.customer_id AS buyer_id,
    c.customer_name,
    o.total_amount::NUMERIC(14,2) AS amount_v2
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Giữ `v_order_summary` cũ trong thời gian chuyển ứng dụng sang `v_order_summary_v2`. Sau khi chắc chắn consumer cũ không còn, mới xóa view cũ và những dependency liên quan theo kế hoạch.

### 47.1. Ưu điểm của versioned views

- Consumer có thời gian chuyển đổi.
- Không phải đổi tên/kiểu cột dưới chân ứng dụng.
- Có thể chạy song song old/new để so kết quả.
- Dễ rollback consumer về tên cũ.
- Có thể cấp grants cho v2 trước khi cutover.

Đổi lại phải quản lý vòng đời cả hai phiên bản và kiểm tra việc giữ đồng bộ semantics theo yêu cầu.

## 48. Expand–migrate–contract cho view

Một chiến lược thay đổi schema an toàn thường chia giai đoạn:

**Expand:**

~~~text
Tạo view v2 hoặc bổ sung cột tương thích vào view cũ.
Giữ consumer cũ hoạt động.
~~~

**Migrate:**

~~~text
Cập nhật ứng dụng/dashboard/job dùng cột hoặc view mới.
Đo tính đúng, quyền và hiệu năng.
~~~

**Contract:**

~~~text
Sau khi không còn consumer cũ,
xóa compatibility view/column cũ theo migration có kiểm soát.
~~~

### 48.1. Không đổi tên đồng thời với deploy thiếu phối hợp

Nếu một deployment mới gọi `v_order_summary_v2` nhưng database migration chưa tạo view, ứng dụng lỗi. Ngược lại, nếu rename view cũ quá sớm, phiên bản ứng dụng chưa nâng cấp cũng lỗi.

Cần sắp xếp migration/deploy theo khả năng tồn tại song song nhiều phiên bản ứng dụng.

## 49. ALTER VIEW RENAME và rolling deployments

Giả sử production có hai phiên bản ứng dụng cùng hoạt động:

- App A truy vấn `v_order_summary`.
- App B truy vấn `v_order_summary_v2`.

Nếu chỉ chạy:

~~~sql
ALTER VIEW view_lab.v_order_summary
RENAME TO v_order_summary_v2;
~~~

thì App A có thể mất tên cũ ngay, gây lỗi. Rename là **thay tên object**, không tạo hai endpoints.

Một đường di chuyển nhẹ nhàng hơn có thể là:

1. Tạo v2 dưới tên mới.
2. Cấp quyền v2.
3. Deploy B dùng v2.
4. Xác nhận không còn A.
5. Drop v1 sau khi kiểm tra dependencies.

Không dựa vào đặc tính nhanh của `ALTER VIEW RENAME` để cho rằng nó luôn an toàn với zero-downtime rollout.

## 50. Locks và concurrent queries khi thao tác DDL

Các lệnh `CREATE OR REPLACE VIEW`, `ALTER VIEW` và `DROP VIEW` cần lock phù hợp để PostgreSQL cập nhật metadata nhất quán.

Tác động vận hành có thể gồm:

- DDL chờ queries/transactions khác.
- Queries đồng thời chờ DDL.
- Migration giữ lock đến transaction end.
- Connection pool có những prepared statements cần reparse/replan.
- Chậm hoặc lỗi nếu consumer dùng object trong lúc chuyển schema.

### 50.1. Đặt timeout có chủ đích

Một ví dụ migration test:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER VIEW view_lab.v_order_state_current
RENAME TO v_order_state_final;

COMMIT;
~~~

Đoạn này **chỉ chạy nếu view `v_order_state_current` đang tồn tại** theo trình tự ví dụ. Với môi trường production, timeout và rollback policy cần phù hợp SLO.

### 50.2. Không mở transaction DDL rồi để idle lâu

Một transaction sau DDL có thể giữ locks đến commit/rollback. Hãy chuẩn bị script reviewable, run đúng thời điểm và kết thúc transaction nhanh.

## 51. Backup và rollback trước thay đổi view

Trong migration production, cần lưu:

- Định nghĩa CREATE VIEW đang chạy.
- Owner/grants.
- Comments.
- View options.
- Danh sách dependent objects.
- Ứng dụng/queries đang sử dụng.
- Kế hoạch khôi phục tên/định nghĩa cũ.
- Rollback strategy tương thích dữ liệu/schema mới.

### 51.1. Rollback DDL khác rollback ứng dụng

Nếu migration đã COMMIT rồi app deploy thất bại, không thể đơn giản ROLLBACK transaction cũ. Cần **migration khôi phục** hoặc chiến lược versioned views để ứng dụng quay lại.

Nếu một cột nguồn đã bị xóa hoặc dữ liệu thay đổi không tương thích, khôi phục view cũ có thể không còn đơn giản. Vì vậy phải xét dependency theo cả hai chiều.

## 52. Tên chữ hoa, dấu cách và quoting identifiers

PostgreSQL chuyển identifier không đặt trong dấu nháy kép thành chữ thường theo quy tắc chuẩn.

~~~sql
CREATE VIEW view_lab.V_My_Report AS
SELECT order_id
FROM view_lab.orders;
~~~

Tên thực tế được normalize theo quy tắc identifier không quote, thường là `v_my_report`.

Nếu tạo tên có quote:

~~~sql
CREATE VIEW view_lab."V_My_Report" AS
SELECT order_id
FROM view_lab.orders;
~~~

thì cần tham chiếu đúng case:

~~~sql
SELECT *
FROM view_lab."V_My_Report";
~~~

### 52.1. Khuyến nghị đặt tên

Nên chọn `snake_case` chữ thường không quote, ví dụ:

- `v_order_summary`.
- `v_paid_orders`.
- `v_customer_revenue`.

Cách này giảm lỗi trong SQL migrations, ORM mapping và scripts.

### 52.2. Không ghép identifier từ input chưa tin cậy

Binds như `$1`/`?` là **giá trị**, không thay tên view/schema/cột. Nếu ứng dụng cần chọn một trong vài view, sử dụng whitelist các tên được phép hoặc định nghĩa SQL templates cố định; không nối trực tiếp input người dùng vào DDL.

## 53. Lỗi thường gặp khi CREATE VIEW

### 53.1. Schema chưa tồn tại

~~~sql
CREATE VIEW not_existing_schema.v_report AS
SELECT 1 AS id;
~~~

sẽ thất bại nếu schema chưa được tạo hoặc không thể truy cập. Cần có bước `CREATE SCHEMA` hợp lệ trước.

### 53.2. Tên view đã tồn tại

~~~sql
CREATE VIEW view_lab.v_paid_orders AS
SELECT ...;
~~~

nếu view đã tồn tại có thể lỗi duplicate relation. Khi chỉ thay định nghĩa tương thích, dùng `CREATE OR REPLACE VIEW`.

### 53.3. Cột tên trùng

Nếu hai biểu thức tạo cùng tên cột không phân biệt được trong định nghĩa view, có thể lỗi hoặc gây nhầm lẫn. Hãy đặt alias duy nhất và rõ nghĩa.

### 53.4. Query sai quyền hoặc tham chiếu đối tượng

Role cần quyền tạo và tham chiếu các đối tượng phù hợp. Không sửa bằng cách cấp superuser cho ứng dụng.

### 53.5. SELECT * sau khi bảng nguồn đổi

View cũ không tự thêm cột mới. Cần migration thay định nghĩa khi muốn expose trường đó.

## 54. Lỗi thường gặp khi CREATE OR REPLACE VIEW

### 54.1. Đổi tên một cột đã tồn tại

Thông báo kiểu “cannot change name of view column” cho thấy cần `ALTER VIEW ... RENAME COLUMN`, hoặc thiết kế view version mới nếu là thay đổi public breaking.

### 54.2. Đổi kiểu một cột

Nếu view cũ trả NUMERIC và định nghĩa mới trả TEXT, OR REPLACE có thể bị từ chối. Giữ kiểu với cast thích hợp hoặc tạo v2.

### 54.3. Đổi thứ tự cột

Giữ mọi cột cũ theo đúng thứ tự; chỉ thêm cột mới ở cuối.

### 54.4. Vô tình đổi semantics

Một SELECT mới có đủ tên/kiểu cột vẫn có thể thay điều kiện WHERE/JOIN, tăng gấp đôi rows hoặc trả dữ liệu nhạy cảm.

### 54.5. Không kiểm tra quyền sau khi sửa

View owner, security options và quyền bảng nguồn có thể ảnh hưởng kết quả với role ứng dụng; đừng chỉ chạy bằng owner.

## 55. Lỗi thường gặp khi ALTER VIEW

### 55.1. Rename bằng CREATE OR REPLACE

Dùng `ALTER VIEW ... RENAME TO` hoặc `RENAME COLUMN` thay vì đổi tên alias trực tiếp trong OR REPLACE cho cột cũ.

### 55.2. Đổi tên khiến client lỗi

PostgreSQL không tạo compatibility alias cho tên cũ. Cần migrate consumers hoặc versioned view.

### 55.3. SET SCHEMA rồi quên schema-qualified SQL

Ứng dụng vẫn gọi `old_schema.view_name`. Phải cập nhật hoặc tạo wrapper phù hợp.

### 55.4. Role không có quyền ALTER

Ownership và quyền trên schema đích phải phù hợp. Không nhầm SELECT privilege với quyền thay cấu trúc.

### 55.5. Thay security_invoker không kiểm thử RLS

Có thể làm câu SELECT trả thiếu dữ liệu hoặc lỗi permission khi role ứng dụng chưa được cấp quyền nguồn.

## 56. Lỗi thường gặp khi DROP VIEW

### 56.1. DROP VIEW bị từ chối vì phụ thuộc

Đây là hành vi RESTRICT nhằm bảo vệ dependent objects. Kiểm tra dependency và lựa chọn xóa/sửa đối tượng con một cách có chủ đích.

### 56.2. Bật CASCADE ngay khi gặp lỗi

Có thể kéo theo nhiều view khác. Trước khi dùng CASCADE, xem chính xác những objects sẽ bị ảnh hưởng.

### 56.3. DROP VIEW nhầm bảng/materialized view

Dùng đúng lệnh cho từng object type. `IF EXISTS` không phải cách cho phép xóa nhầm loại.

### 56.4. DROP rồi CREATE mà quên GRANT

Đối tượng mới không tự kế thừa toàn bộ grants/comments/owner của view cũ. Người dùng ứng dụng có thể nhận permission denied.

### 56.5. Không biết consumer bên ngoài

Một view không có catalog dependents vẫn có thể được gọi từ ứng dụng Java, cron job hoặc BI dashboard. Cần quan sát thực tế và tìm SQL trong repository/config có liên quan.

## 57. Kiểm tra toàn bộ view lifecycle trong một lab riêng

Một lab nhỏ biệt lập, không liên quan các tên trong ví dụ chính:

~~~sql
-- Tạo view:
CREATE VIEW view_lab.v_lifecycle AS
SELECT
    order_id,
    status
FROM view_lab.orders;

-- Thay logic, giữ tên/kiểu/thứ tự 2 cột:
CREATE OR REPLACE VIEW view_lab.v_lifecycle AS
SELECT
    order_id,
    status
FROM view_lab.orders
WHERE status <> 'cancelled';

-- Thêm một cột cuối:
CREATE OR REPLACE VIEW view_lab.v_lifecycle AS
SELECT
    order_id,
    status,
    total_amount
FROM view_lab.orders
WHERE status <> 'cancelled';

-- Đổi tên một cột:
ALTER VIEW view_lab.v_lifecycle
RENAME COLUMN status TO order_status;

-- Đổi tên view:
ALTER VIEW view_lab.v_lifecycle
RENAME TO v_lifecycle_v2;

-- Xem định nghĩa:
SELECT pg_get_viewdef(
    'view_lab.v_lifecycle_v2'::regclass,
    TRUE
);

-- Xem dữ liệu:
SELECT *
FROM view_lab.v_lifecycle_v2
ORDER BY order_id;

-- Xóa view:
DROP VIEW view_lab.v_lifecycle_v2;
~~~

### 57.1. Vì sao đây là bài lab tốt?

Nó minh họa một vòng đời trọn vẹn:

~~~text
CREATE
  |
  v
CREATE OR REPLACE (sửa WHERE)
  |
  v
CREATE OR REPLACE (thêm cột ở cuối)
  |
  v
ALTER VIEW RENAME COLUMN
  |
  v
ALTER VIEW RENAME TO
  |
  v
pg_get_viewdef / SELECT
  |
  v
DROP VIEW
~~~

Nó không cần dùng CASCADE, không làm thay đổi dữ liệu base tables, và các tên view mới dành riêng cho lab.

### 57.2. Không chạy lặp mà không reset

Nếu bị ngắt giữa các bước, tên view đang tồn tại có thể khác. Kiểm tra trạng thái bằng `pg_views`/`\dv` trước khi chạy tiếp. Không dùng DROP CASCADE để “dọn nhanh” nếu chưa rõ object đã được tạo.

## 58. Thử dependency trước khi drop

Một lab riêng:

~~~sql
CREATE VIEW view_lab.v_parent_demo AS
SELECT order_id, status
FROM view_lab.orders;

CREATE VIEW view_lab.v_child_demo AS
SELECT order_id
FROM view_lab.v_parent_demo
WHERE status = 'paid';
~~~

Lệnh:

~~~sql
-- Dự kiến bị từ chối vì child vẫn còn:
DROP VIEW view_lab.v_parent_demo RESTRICT;
~~~

Thay vì CASCADE, xóa có kiểm soát:

~~~sql
DROP VIEW view_lab.v_child_demo;

DROP VIEW view_lab.v_parent_demo;
~~~

### 58.1. Bài học

- `RESTRICT` bảo vệ phụ thuộc.
- `CASCADE` có phạm vi rộng, phải biết consequences.
- Xóa child trước parent là chiến lược có thể review.
- Base table `view_lab.orders` không bị xóa.

## 59. Migration script nên có tính lặp lại ở đâu?

Không phải mọi lệnh cần `IF EXISTS` hay `OR REPLACE`.

- Migration tạo object **mới** thường nên thất bại nếu object bất ngờ đã có, giúp phát hiện sai state.
- Migration có chủ đích cập nhật view tương thích dùng `CREATE OR REPLACE VIEW`.
- Cleanup optional object có thể dùng `DROP VIEW IF EXISTS` khi việc thiếu object là expected state.
- Migration breaking nên thể hiện rõ create v2, deploy/migrate consumers, drop v1.
- Đổi tên phải dùng `ALTER VIEW RENAME`, với đường chuyển consumer được thiết kế rõ.

**Idempotency** không đồng nghĩa “bỏ qua mọi lỗi”. Nó là thuộc tính có chủ đích của từng bước trong quy trình deployment.

## 60. Quản lý view bằng migration tools

Ứng dụng Java thường dùng các công cụ migration như Flyway hoặc Liquibase. Dù công cụ nào, SQL DDL lõi vẫn là:

~~~sql
CREATE VIEW ... AS SELECT ...;

CREATE OR REPLACE VIEW ... AS SELECT ...;

ALTER VIEW ... RENAME TO ...;

ALTER VIEW ... RENAME COLUMN ... TO ...;

DROP VIEW ...;
~~~

Một migration cần:

1. Chạy theo thứ tự xác định.
2. Được review như code.
3. Được kiểm thử với schema/dữ liệu gần production.
4. Kiểm tra dependent views và consumer.
5. Ghi grants/ownership/options/comments.
6. Có rollback/fallback được đánh giá trước.
7. Không tự động CASCADE nếu chưa được chấp nhận.

### 60.1. SQL view definition là code

Nên lưu định nghĩa đầy đủ trong version control, không chỉ xem view là một đối tượng sửa bằng UI quản trị. Điều này giúp giải thích vì sao logic thay đổi và tái hiện schema ở môi trường mới.

## 61. Đánh giá độ tương thích của một thay đổi view

Một bảng quyết định nhanh:

| Thay đổi | Lệnh thường phù hợp | Rủi ro cần xem |
|---|---|---|
| Sửa WHERE, giữ cột | `CREATE OR REPLACE VIEW` | Kết quả/hiệu năng/quyền |
| Sửa JOIN, giữ cột | `CREATE OR REPLACE VIEW` | Cardinality, duplicate rows |
| Thêm cột ở cuối | `CREATE OR REPLACE VIEW` | SELECT */ORM consumer |
| Đổi tên view | `ALTER VIEW ... RENAME TO` | SQL client dùng tên cũ |
| Đổi tên cột | `ALTER VIEW ... RENAME COLUMN` | API/ORM dùng tên cũ |
| Đổi schema chứa view | `ALTER VIEW ... SET SCHEMA` | search_path, grants, tên đầy đủ |
| Sửa owner | `ALTER VIEW ... OWNER TO` | Privilege/security behavior |
| Thay security options | `ALTER VIEW ... SET (...)` | Quyền/RLS/planner |
| Đổi kiểu/bỏ cột cũ | Tạo view v2, migrate consumers | Breaking change, dependencies |
| Xóa view không còn dùng | `DROP VIEW ... RESTRICT` | Dependencies ngoài/ trong DB |
| Xóa cả cây view đã xác nhận | `DROP VIEW ... CASCADE` trong tình huống có kiểm soát | Xóa dependent objects ngoài dự kiến |

Đây là định hướng lựa chọn, không phải quy tắc tự động áp dụng không cần xem trạng thái thực tế.

## 62. Checklist trước khi CREATE/REPLACE/RENAME/DROP

**Trước khi CREATE:**

- Schema đích tồn tại?
- Tên view đã bị đối tượng khác dùng?
- Cột output có tên/kiểu rõ?
- Query đúng semantics/row count?
- Role tạo có quyền?
- Có cần security options/check option?
- Có cần cấp GRANT và COMMENT sau tạo?

**Trước khi REPLACE:**

- Những cột cũ giữ tên, thứ tự, kiểu?
- Cột mới chỉ được thêm cuối?
- View con có tiếp tục sử dụng được?
- Kết quả query trước/sau thay đổi như mong đợi?
- Plan/performance có thay đáng kể?
- Role ứng dụng có còn quyền?
- Có transaction và rollback plan?

**Trước khi RENAME:**

- Tên mới có trùng object?
- App/ORM/report nào dùng tên cũ?
- Có cần hai phiên bản song song?
- Có đổi column name trong mapping?
- Search_path và schema-qualified SQL có cập nhật?
- Cần điều chỉnh tài liệu, migration/monitoring?

**Trước khi DROP:**

- View không còn được dùng trong DB và ngoài DB?
- Catalog dependents có gì?
- `RESTRICT` có an toàn?
- Nếu CASCADE, tất cả dependent objects đã được xác nhận?
- Có bản definition/grants/comments để khôi phục?
- Lệnh có chạy trong window phù hợp và giới hạn lock?
- Có theo dõi lỗi ứng dụng sau deployment?

## 63. Bài tập thực hành

### Bài 1 — View đơn giản

Tạo view `v_new_orders` chỉ hiển thị các đơn có status `new`.

**Gợi ý:** `CREATE VIEW ... AS SELECT ... WHERE status='new'`.

### Bài 2 — View JOIN

Tạo view trả `order_id`, `customer_name` và `total_amount`.

**Gợi ý:** JOIN orders với customers theo customer_id.

### Bài 3 — View GROUP BY

Tạo view tổng tiền đã thanh toán theo customer_id.

**Gợi ý:** `SUM(...) FILTER (WHERE status='paid')`.

### Bài 4 — Alias

Một expression `total_amount*1.05` cần tên `amount_with_fee`. Viết lệnh CREATE VIEW với alias thích hợp.

**Gợi ý:** `AS amount_with_fee`.

### Bài 5 — Danh sách tên cột

Dùng `CREATE VIEW name(col1,col2) AS SELECT ...` để đặt tên hai cột.

**Gợi ý:** tên trong danh sách theo thứ tự SELECT.

### Bài 6 — Lý do không SELECT *

Vì sao thêm cột mới vào base table không tự bảo đảm view tạo bằng `SELECT *` có thêm cột?

**Gợi ý:** định nghĩa view lưu danh sách output được phân tích khi tạo.

### Bài 7 — OR REPLACE

Sửa WHERE của view có sẵn mà giữ nguyên tên/kiểu/thứ tự cột.

**Gợi ý:** `CREATE OR REPLACE VIEW`.

### Bài 8 — Thêm cột

Muốn thêm `status` vào view cũ có bốn cột. Thêm ở đâu?

**Gợi ý:** cuối danh sách.

### Bài 9 — Rename cột

Đổi `customer_id` thành `buyer_id` trên view.

**Gợi ý:** `ALTER VIEW ... RENAME COLUMN customer_id TO buyer_id`.

### Bài 10 — Đổi kiểu

Có thể đổi `total_amount NUMERIC` thành TEXT ở cùng vị trí bằng OR REPLACE không?

**Gợi ý:** không tùy ý; tạo v2 khi breaking.

### Bài 11 — Rename view

Đổi `v_report_old` thành `v_report_new`.

**Gợi ý:** `ALTER VIEW ... RENAME TO v_report_new`.

### Bài 12 — Tên sau rename

Sau RENAME, client dùng tên cũ có tự hoạt động không?

**Gợi ý:** không có alias tự động.

### Bài 13 — SET SCHEMA

Di chuyển view từ `view_lab` sang `view_reporting`.

**Gợi ý:** `ALTER VIEW view_lab.view_name SET SCHEMA view_reporting`.

### Bài 14 — Ownership

Vì sao GRANT SELECT không cho role tùy ý ALTER VIEW?

**Gợi ý:** ownership/quyền quản trị khác SELECT privilege.

### Bài 15 — security_invoker

`security_invoker=true` ảnh hưởng quyền nguồn theo context nào?

**Gợi ý:** người gọi; kiểm tra version và RLS.

### Bài 16 — security_barrier

Vì sao không nên bật barrier trên mọi view mà không đo?

**Gợi ý:** ảnh hưởng bảo mật/predicate pushdown/performance.

### Bài 17 — Auto-updatable

Một view đơn giản một bảng có thể UPDATE được không?

**Gợi ý:** có nếu thỏa điều kiện.

### Bài 18 — GROUP BY view

Một view tổng hợp GROUP BY có tự UPDATE hàng của bảng nguồn thông thường không?

**Gợi ý:** thường không tự cập nhật được.

### Bài 19 — WITH CHECK OPTION

CHECK OPTION của view bảo vệ điều gì khi ghi qua view?

**Gợi ý:** kiểm tra điều kiện hiển thị tương ứng.

### Bài 20 — CHECK OPTION vs CHECK constraint

Vì sao CHECK OPTION không thay mọi table CHECK constraint?

**Gợi ý:** phạm vi ghi qua view khác ghi trực tiếp bảng.

### Bài 21 — Temp view

Một temp view tạo ở connection A có tự tồn tại ở connection B không?

**Gợi ý:** không, session scope.

### Bài 22 — DROP VIEW

DROP VIEW có xóa rows của bảng gốc không?

**Gợi ý:** không, xóa định nghĩa view.

### Bài 23 — IF EXISTS

Lợi ích và rủi ro của `DROP VIEW IF EXISTS` là gì?

**Gợi ý:** tránh lỗi khi optional view thiếu, nhưng có thể che trạng thái migration sai.

### Bài 24 — RESTRICT

Một view cha có view con phụ thuộc. DROP view cha mặc định có thể bị gì?

**Gợi ý:** từ chối vì dependency.

### Bài 25 — CASCADE

Vì sao `DROP VIEW ... CASCADE` nguy hiểm?

**Gợi ý:** có thể xóa dependent database objects.

### Bài 26 — Manual order

Nếu view con phụ thuộc view cha và muốn xóa cả hai, xóa cái nào trước?

**Gợi ý:** child trước parent.

### Bài 27 — External consumers

Không thấy catalog dependency có chứng minh view không còn được ứng dụng dùng không?

**Gợi ý:** không; xem code, BI, jobs.

### Bài 28 — GRANT sau DROP/CREATE

Vì sao app có thể gặp permission denied sau khi xóa và tạo view cùng tên?

**Gợi ý:** object mới không tự giữ mọi grants của object cũ.

### Bài 29 — pg_views

Viết query lấy definition của views trong schema `view_lab`.

**Gợi ý:** `SELECT ... FROM pg_views WHERE schemaname='view_lab'`.

### Bài 30 — pg_get_viewdef

Cách xem định nghĩa một view theo tên qualified?

**Gợi ý:** `pg_get_viewdef('schema.view'::regclass, true)`.

### Bài 31 — View relkind

Trong `pg_class`, regular view thường có `relkind` gì?

**Gợi ý:** `'v'`.

### Bài 32 — Rewrite dependency

Vì sao tìm dependency chỉ bằng view OID có thể thiếu tham chiếu từ query?

**Gợi ý:** view definition qua `pg_rewrite`/rule.

### Bài 33 — EXPLAIN

Tạo view mới có tự cache kết quả và làm JOIN nhanh hơn không?

**Gợi ý:** view thường là stored query, không vật hóa kết quả.

### Bài 34 — Migration tương thích

Vì sao thêm một output cột cuối có thể hợp lệ nhưng vẫn làm ORM dùng SELECT * lỗi?

**Gợi ý:** consumer phụ thuộc shape/column count.

### Bài 35 — Versioned view

Khi cần đổi kiểu/bỏ cột, tại sao tạo v2 thường an toàn hơn drop v1 ngay?

**Gợi ý:** cho consumers chuyển dần, hỗ trợ rollback.

### Bài 36 — Rolling deploy

Rename view trong khi hai phiên bản app cùng hoạt động có nguy cơ gì?

**Gợi ý:** app cũ vẫn dùng tên cũ.

### Bài 37 — Lock timeout

Đặt `SET LOCAL lock_timeout` trước ALTER VIEW trong transaction có lợi ích gì?

**Gợi ý:** hạn chế thời gian chờ lock ngoài ý muốn.

### Bài 38 — Quoting

Sự khác nhau giữa `V_Report` không quote và `"V_Report"` có quote?

**Gợi ý:** case folding vs case-sensitive identifier.

### Bài 39 — Comment

Viết COMMENT ON VIEW mô tả mục đích một view.

**Gợi ý:** `COMMENT ON VIEW schema.view IS '...';`.

### Bài 40 — Review migration

Liệt kê ít nhất bảy yếu tố kiểm tra trước khi xóa một view production.

**Gợi ý:** dependents, consumers, grants, schema, backup, lock, rollback, monitoring.

## 64. Câu hỏi thường gặp

### VIEW có tự lưu kết quả SELECT không?

Regular view lưu định nghĩa query, không lưu một bản kết quả riêng. Materialized view là đối tượng khác với lifecycle REFRESH riêng.

### Nếu sửa dữ liệu trong bảng gốc, có cần tạo lại view không?

Không. Regular view dùng dữ liệu ở thời điểm truy vấn theo transaction snapshot. Chỉ cần thay view khi muốn thay **logic/giao diện SELECT** hoặc options/metadata.

### CREATE OR REPLACE VIEW có thay được tất cả không?

Không. Cột cũ phải giữ tên, thứ tự và kiểu, trừ việc có thể thêm cột mới ở cuối. Rename dùng ALTER VIEW; thay kiểu/bỏ cột thường cần chiến lược migration khác.

### OR REPLACE có xóa quyền GRANT không?

Nó thay định nghĩa trên view hiện có, do đó thường giữ grants/ownership của đối tượng view. DROP + CREATE là một đối tượng mới nên cần thiết lập lại metadata phù hợp.

### Có được rename một view đang có dependent views?

PostgreSQL quản lý nội bộ nhiều dependencies theo object identity nên rename có thể giữ dependent views hợp lệ. Nhưng ứng dụng SQL ngoài database dùng tên cũ sẽ không tự được cập nhật.

### ALTER VIEW RENAME TO có đổi schema không?

Không. Dùng `SET SCHEMA` cho việc di chuyển schema.

### DROP VIEW mặc định có CASCADE không?

Không. Mặc định là `RESTRICT`: xóa bị từ chối khi còn dependent objects cần bảo vệ.

### DROP VIEW CASCADE có xóa bảng nguồn không?

Không mặc định. Nó xóa những đối tượng phụ thuộc vào view theo catalog dependencies; bảng nguồn thường không phải dependent của view.

### Khi nào nên dùng DROP VIEW IF EXISTS?

Khi một view optional có thể hợp lệ không tồn tại, như cleanup được thiết kế cho nhiều trạng thái. Không dùng để âm thầm bỏ qua mọi sai lệch migration.

### View có thể cập nhật trực tiếp bảng không?

Một số simple views tự cập nhật được; views tổng hợp/JOIN phức tạp thường không. Có thể dùng INSTEAD OF triggers/rules trong những trường hợp thiết kế phù hợp. Quyền/constraints vẫn áp dụng.

### security_invoker=true có dùng trên mọi phiên bản PostgreSQL không?

Không. Đây là option được hỗ trợ từ PostgreSQL 15. Cần kiểm tra version đang chạy và semantics quyền/RLS trước khi sử dụng.

### ALTER VIEW có làm hệ thống chờ lock không?

DDL cần lock; nếu có transactions dài hoặc truy vấn đồng thời, có thể chờ hoặc gây chờ. Lập kế hoạch migration, timeout và thời gian thực hiện phù hợp.

### VIEW có tự dùng index không?

Regular view không có index riêng. Planner có thể dùng indexes của những bảng nguồn qua truy vấn view; phải xác minh bằng EXPLAIN.

### Có nên dùng DROP + CREATE trong mỗi migration view?

Không nên mặc định. Với thay đổi tương thích, `CREATE OR REPLACE VIEW` thường ít phá phụ thuộc/grants hơn. Với breaking changes, cân nhắc v2 và chuyển consumers dần.

## 65. Tổng kết

Các lệnh trọng tâm:

~~~sql
-- Tạo:
CREATE VIEW schema_name.view_name AS
SELECT ...;

-- Thay định nghĩa tương thích:
CREATE OR REPLACE VIEW schema_name.view_name AS
SELECT ...;

-- Đổi tên view:
ALTER VIEW schema_name.old_name
RENAME TO new_name;

-- Đổi tên cột:
ALTER VIEW schema_name.view_name
RENAME COLUMN old_column TO new_column;

-- Di chuyển schema:
ALTER VIEW old_schema.view_name
SET SCHEMA new_schema;

-- Xóa (mặc định RESTRICT):
DROP VIEW schema_name.view_name;

-- Bỏ qua nếu không tồn tại:
DROP VIEW IF EXISTS schema_name.view_name;

-- Xóa cả dependent objects (chỉ khi đã xác nhận):
DROP VIEW schema_name.view_name CASCADE;
~~~

Những nguyên tắc cần ghi nhớ:

1. **Regular view là truy vấn được đặt tên**, không phải bản dữ liệu được vật hóa.
2. **`CREATE VIEW`** tạo giao diện đọc/tính toán có thể tái sử dụng từ một hoặc nhiều bảng.
3. **`CREATE OR REPLACE VIEW`** phù hợp khi sửa logic SQL mà giữ tên, thứ tự và kiểu các cột hiện có; có thể thêm cột mới ở **cuối**.
4. **Đổi tên view/cột** dùng `ALTER VIEW ... RENAME`, không dùng OR REPLACE để thay tên cột cũ.
5. **Đổi kiểu hoặc loại bỏ cột cũ** là thay đổi breaking; nên đánh giá view v2 và expand–migrate–contract.
6. **`DROP VIEW` mặc định RESTRICT**; lỗi dependency cần được phân tích, không bật CASCADE theo phản xạ.
7. **`DROP VIEW ... CASCADE`** có thể xóa những views/objects phụ thuộc, nhưng **không mặc định xóa bảng nguồn**.
8. **DROP + CREATE không tương đương OR REPLACE**: grants, ownership, comments, dependencies và object identity có thể thay đổi.
9. **Regular view không có index riêng**; cần xem EXPLAIN và index các bảng nguồn khi tối ưu.
10. **View permissions, security_invoker, security_barrier và RLS** có thể ảnh hưởng dữ liệu mà role ứng dụng thấy.
11. **DDL có lock và transaction semantics**, cần migration/rollback có kiểm soát trên production.
12. **Catalog dependencies chưa thấy hết consumer bên ngoài database**; hãy tra cả ứng dụng, job, report và BI.
13. **Versioned views** cho phép đổi giao diện có kế hoạch trong rolling deployment thay vì rename/drop đột ngột.
14. **Metadata** qua `pg_views`, `pg_get_viewdef`, `information_schema` và `pg_catalog` giúp kiểm tra thực trạng view trước/sau khi thay đổi.

Một vòng đời an toàn:

~~~text
Định nghĩa nhu cầu và cột output
              |
              v
      CREATE VIEW
              |
              v
  Dùng SELECT / GRANT / COMMENT
              |
              v
      Nhu cầu thay đổi?
        /             \
       /               \
 Thay tương thích   Thay breaking
       |               |
 CREATE OR REPLACE   Tạo view v2
       |               |
       |          Migrate consumers
       \               /
        \             /
         Kiểm tra quyền, kết quả,
         hiệu năng và dependencies
                  |
                  v
        Khi view cũ không còn dùng:
        DROP VIEW ... RESTRICT
                  |
                  v
           Theo dõi sau deploy
~~~

Khi nắm chắc sự khác biệt giữa **thay định nghĩa**, **đổi metadata tên** và **xóa đối tượng**, bạn có thể quản lý views PostgreSQL như một giao diện schema ổn định, đồng thời triển khai thay đổi có chủ đích và tránh tác động ngoài ý muốn tới những truy vấn đang phụ thuộc vào chúng.
