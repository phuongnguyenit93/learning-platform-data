# View như giao diện truy vấn và mức trừu tượng dữ liệu trong PostgreSQL

Một ứng dụng thương mại điện tử lưu thông tin đơn hàng trong bảng `orders` và thông tin khách hàng trong bảng `customers`. Mỗi lần hiển thị danh sách đơn hàng, ứng dụng phải JOIN hai bảng, đổi tên cột, loại các trường nội bộ, lọc dữ liệu theo trạng thái và định dạng giá trị để trả về cho giao diện.

Nếu nhiều service và báo cáo cùng tự viết câu JOIN này, việc đổi tên cột hay chuyển thông tin khách hàng sang bảng mới có thể khiến hàng chục truy vấn phải sửa đồng loạt. Một số service lại quên bộ lọc tenant, chọn nhầm trường nhạy cảm hoặc tính chỉ số không thống nhất.

**View** trong PostgreSQL giải quyết một phần vấn đề đó bằng cách biến một câu `SELECT` đã đặt tên thành **giao diện truy vấn có thể sử dụng như một quan hệ**:

```sql
CREATE VIEW reporting.v_order_summary AS
SELECT
    o.order_id,
    o.ordered_at,
    c.display_name AS customer_name,
    o.status,
    o.amount
FROM application.orders AS o
JOIN application.customers AS c
  ON c.customer_id = o.customer_id;
```

Ứng dụng sau đó truy vấn:

```sql
SELECT order_id, customer_name, status, amount
FROM reporting.v_order_summary
WHERE status = 'PAID'
ORDER BY ordered_at DESC
LIMIT 20;
```

View đóng vai trò **hợp đồng dữ liệu đọc** giữa nơi lưu trữ và nơi sử dụng. Người tiêu thụ không cần lặp lại mọi chi tiết JOIN, tên bảng vật lý và công thức cột tính toán.

Tuy nhiên, cần hiểu chính xác:

- View thông thường **không lưu trước toàn bộ kết quả SELECT** và **không phải cache**.
- View không tự làm truy vấn nhanh hơn hay làm cho một truy vấn sai trở nên đúng.
- View không tự cung cấp kiểm soát quyền đầy đủ nếu quyền trên bảng nền, ownership hoặc Row-Level Security được cấu hình không phù hợp.
- Không phải view nào cũng cập nhật được bằng `INSERT`, `UPDATE` hoặc `DELETE`.
- Giao diện view có thể ổn định qua một số thay đổi schema, nhưng vẫn có **phụ thuộc kiểu dữ liệu, tên cột, quyền và ngữ nghĩa**.

Bài học này thuộc chương **View** của module **Database Engine Relational PostgreSQL**, tập trung vào **view như giao diện truy vấn và mức trừu tượng dữ liệu**: xây dựng hợp đồng SELECT, tách biệt mô hình lưu trữ với mô hình đọc, quản lý thay đổi và quyền truy cập, hiểu tính cập nhật/hiệu năng và tổ chức các view để ứng dụng dùng lâu dài.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích view là gì, PostgreSQL xử lý view thông thường như thế nào và phân biệt nó với bảng vật lý.
2. Dùng `CREATE VIEW`, `CREATE OR REPLACE VIEW`, `ALTER VIEW` và `DROP VIEW` đúng phạm vi.
3. Thiết kế một **read model** từ nhiều bảng, đồng nhất tên cột và che chi tiết schema nội bộ.
4. Tạo cột dẫn xuất, điều kiện lọc và phép tổng hợp có ý nghĩa nghiệp vụ trong view.
5. Phân biệt **giao diện ổn định về cấu trúc** với **giao diện ổn định về ngữ nghĩa**.
6. Hiểu phụ thuộc của view đối với bảng/cột/hàm bên dưới, đặc biệt khi thay đổi schema.
7. Nhận biết giới hạn của `CREATE OR REPLACE VIEW` đối với tên, thứ tự và kiểu cột hiện có.
8. Giải thích sự khác nhau giữa view **tự động cập nhật được** và view chỉ đọc theo cấu trúc truy vấn.
9. Dùng `WITH LOCAL CHECK OPTION` và `WITH CASCADED CHECK OPTION` trong tình huống phù hợp.
10. Hiểu cơ chế quyền mặc định của view, `security_invoker`, `security_barrier` và các vấn đề Row-Level Security.
11. Sử dụng view như một lớp cấp quyền đọc tối thiểu, nhưng không nhầm nó với cơ chế bảo mật hoàn chỉnh.
12. Dùng `EXPLAIN (ANALYZE, BUFFERS)` để quan sát cách planner thực thi truy vấn qua view.
13. Phân biệt view thường, materialized view, CTE, SQL function và bảng tổng hợp vật lý.
14. Thiết kế chiến lược đặt tên, versioning, kiểm thử và migration an toàn cho view phục vụ nhiều ứng dụng.
15. Biết khi nào view giúp giảm coupling và khi nào quá nhiều lớp view làm hệ thống khó hiểu.

**Phạm vi:** PostgreSQL hiện đại. Một số tính năng như `security_invoker` có giới hạn phiên bản (được hỗ trợ từ PostgreSQL 15). Mọi ví dụ liên quan đến tạo role, cấp quyền hay thao tác DDL cần chạy trên môi trường được phép. Các ví dụ lab có thể tạo lại từ đầu trong schema riêng; không áp dụng lệnh xóa schema lên production.

---

## 2. View là gì?

View là một **đối tượng schema được định nghĩa bằng câu truy vấn**. Người sử dụng có thể tham chiếu tên view trong nhiều vị trí giống như tham chiếu một bảng:

```sql
SELECT * FROM some_schema.some_view;
```

Nhưng phía sau tên view không nhất thiết có một heap chứa các hàng kết quả. Với **view thường**, PostgreSQL lưu **định nghĩa truy vấn và metadata**, rồi xử lý truy vấn dựa trên dữ liệu nền khi statement được thực thi.

Sơ đồ:

```text
Ứng dụng / JDBC / báo cáo
           |
           | SELECT ... FROM api.v_order_read_model
           v
+-------------------------------------------+
| View: api.v_order_read_model               |
| - tên và danh sách cột công khai           |
| - định nghĩa SELECT                       |
| - quyền và các tùy chọn view              |
+-------------------------------------------+
           |
           | Planner/rewrite xử lý truy vấn
           v
+-----------------+      +------------------+
| internal.orders | JOIN | internal.customers|
+-----------------+      +------------------+
           |
           v
     Hàng kết quả theo snapshot của SELECT
```

### 2.1. View như một tên cho câu truy vấn

Nếu ba báo cáo phải tự viết:

```sql
SELECT
    o.order_id,
    c.display_name,
    o.status,
    o.amount
FROM internal.orders AS o
JOIN internal.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id;
```

thì view có thể tập trung phần định nghĩa JOIN đó một lần.

### 2.2. View như lớp trừu tượng

Trừu tượng ở đây có nghĩa ứng dụng phụ thuộc vào:

- Tên view ổn định.
- Tên, thứ tự, kiểu và ý nghĩa cột mà view công bố.
- Quyền truy cập vào view.
- Hợp đồng về đơn vị, timezone, trạng thái và độ đầy đủ của dữ liệu.

Ứng dụng **không nhất thiết** phải biết tên bảng vật lý, cấu trúc quan hệ nhiều bảng hay trường dùng để tính toán cột dẫn xuất.

### 2.3. View không phải ảnh chụp bất biến

Khi base table thay đổi và transaction commit, truy vấn view ở snapshot thích hợp có thể thấy dữ liệu mới. Một view thường không phải nơi lưu dữ liệu cũ từ lần tạo view.

### 2.4. Tên view không bảo đảm tính đúng

Nếu view định nghĩa JOIN sai khóa tenant, sử dụng bộ lọc sai hoặc tính SUM bị nhân bởi JOIN một-nhiều, mọi người sử dụng view đều có thể nhận kết quả sai giống nhau. **Tập trung logic giúp thống nhất, nhưng logic được tập trung vẫn phải đúng.**

---

## 3. So sánh bảng, view thường và materialized view

| Đặc điểm | Bảng vật lý | View thường | Materialized view |
| --- | --- | --- | --- |
| Lưu các hàng kết quả như một relation vật lý | Có | Không | Có |
| Định nghĩa bằng SELECT của các bảng khác | Không bắt buộc | Có | Có |
| Dữ liệu mới ở base table tự có thể hiện trong SELECT tiếp theo | Không áp dụng | Có, theo snapshot/transaction | Không; cần refresh |
| Có thể tạo index trên chính đối tượng | Có | Không trực tiếp | Có |
| Hỗ trợ DML thông thường | Có, tùy quyền/constraint | Một số view tự động cập nhật được; loại khác cần trigger/rule | Không như một bảng DML thông thường |
| Chi phí mỗi lần SELECT | Trên bảng/index | Phụ thuộc truy vấn nền đã mở rộng | Trên kết quả vật hóa/index |
| Use case chính | Lưu dữ liệu | Trừu tượng và giao diện truy vấn | Snapshot báo cáo/tính toán đắt cần refresh |

**View thường không materialize kết quả chỉ vì có `CREATE VIEW`.**

### 3.1. Một view có JOIN vẫn có thể truy vấn nhanh

PostgreSQL có optimizer có thể đẩy nhiều điều kiện và chọn index trên các bảng nền. Vì thế một view có JOIN không nhất thiết luôn quét toàn bộ bảng trước rồi mới lọc.

### 3.2. Một view có GROUP BY vẫn phải aggregate khi cần

Nếu gọi một view tổng hợp trên hàng triệu đơn hàng, PostgreSQL thường phải tính toán phép tổng hợp từ dữ liệu nền theo kế hoạch truy vấn. View không tự có cache của COUNT/SUM.

### 3.3. Materialized view có hợp đồng độ tươi khác

Materialized view có dữ liệu vật lý tại thời điểm nạp/refresh. Việc chọn nó để tăng tốc báo cáo cũng đồng nghĩa phải thiết kế **lịch refresh, quyền truy cập, dữ liệu trễ và bảo trì chỉ mục**.

---

## 4. Bộ dữ liệu lab: khách hàng và đơn hàng nhiều tenant

Để xem view như một hợp đồng dữ liệu, ta cần bảng nền có cả trường công khai và trường nội bộ.

> **Cảnh báo:** Những câu `DROP SCHEMA ... CASCADE` sau xóa **toàn bộ** đối tượng trong schema thực hành cùng tên. Chỉ chạy trong database lab riêng được phép reset. Không chạy trên database có dữ liệu cần giữ.

### 4.1. Tạo schema thực hành

```sql
DROP SCHEMA IF EXISTS view_contract_lab CASCADE;

CREATE SCHEMA view_contract_lab;
```

Ta dùng một schema cho ngắn gọn. Trong production có thể tách `internal` và `api`/`reporting` thành các schema riêng để quản lý quyền và vòng đời.

### 4.2. Bảng khách hàng

```sql
CREATE TABLE view_contract_lab.customers (
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL,
    region TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);
```

### 4.3. Bảng đơn hàng

```sql
CREATE TABLE view_contract_lab.orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED', 'REFUNDED')),
    amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL,
    internal_note TEXT,
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES view_contract_lab.customers(tenant_id, customer_id)
);
```

Điểm quan trọng:

- `tenant_id` nằm trong cả khóa và foreign key.
- `orders.internal_note` chỉ dành cho thao tác nội bộ.
- `customers.email` có thể là dữ liệu cá nhân cần giới hạn người đọc.
- `amount` là giá trị đơn hàng theo ví dụ; không mặc định đồng nhất nó với tiền đã thực thu hoặc doanh thu sau hoàn tiền.

### 4.4. Nạp khách hàng

```sql
INSERT INTO view_contract_lab.customers (
    tenant_id, customer_id, display_name, email, region
)
VALUES
    (10, 101, 'An',    'an@example.test',    'NORTH'),
    (10, 102, 'Binh',  'binh@example.test',  'SOUTH'),
    (20, 101, 'Chi',   'chi@example.test',   'CENTRAL'),
    (20, 103, 'Dung',  'dung@example.test',  'NORTH');
```

Hai tenant có thể cùng `customer_id=101`. Vì thế JOIN chỉ theo customer_id là **sai** nếu không đồng thời xét tenant_id.

### 4.5. Nạp đơn hàng

```sql
INSERT INTO view_contract_lab.orders (
    tenant_id, order_id, customer_id, status,
    amount, ordered_at, internal_note
)
VALUES
    (10, 1001, 101, 'PAID',     120.00,
     TIMESTAMPTZ '2026-01-10 09:00:00+00', 'Call before shipping'),
    (10, 1002, 101, 'PENDING',   80.00,
     TIMESTAMPTZ '2026-01-11 10:00:00+00', 'Manual review'),
    (10, 1003, 102, 'PAID',      50.00,
     TIMESTAMPTZ '2026-01-12 11:00:00+00', NULL),
    (10, 1004, 102, 'CANCELED',  30.00,
     TIMESTAMPTZ '2026-01-13 12:00:00+00', 'Customer canceled'),
    (20, 1001, 101, 'PAID',     300.00,
     TIMESTAMPTZ '2026-01-11 09:00:00+00', 'Special pricing'),
    (20, 1002, 103, 'PAID',      75.00,
     TIMESTAMPTZ '2026-01-14 09:00:00+00', NULL),
    (20, 1003, 103, 'REFUNDED',  40.00,
     TIMESTAMPTZ '2026-01-15 09:00:00+00', 'Refund requested');

ANALYZE view_contract_lab.customers;
ANALYZE view_contract_lab.orders;
```

Kiểm tra:

```sql
SELECT tenant_id, order_id, customer_id, status, amount
FROM view_contract_lab.orders
ORDER BY tenant_id, order_id;
```

Có **bảy đơn hàng**: bốn thuộc tenant 10 và ba thuộc tenant 20.

---

## 5. View đầu tiên: giao diện đọc đơn hàng

Mục tiêu: cho ứng dụng một mô hình đọc rõ ràng, có tên khách hàng, khu vực và giá trị đơn mà không phải tự JOIN.

```sql
CREATE VIEW view_contract_lab.v_order_read_model AS
SELECT
    o.tenant_id,
    o.order_id,
    o.customer_id,
    c.display_name AS customer_name,
    c.region AS customer_region,
    o.status,
    o.amount AS gross_amount,
    o.ordered_at,
    (o.status = 'PAID') AS is_paid
FROM view_contract_lab.orders AS o
JOIN view_contract_lab.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id;
```

### 5.1. Truy vấn qua view

```sql
SELECT
    order_id,
    customer_name,
    status,
    gross_amount
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
ORDER BY ordered_at DESC, order_id DESC;
```

Không cần lặp lại JOIN khách hàng. View đã quyết định các cột công bố và cách khớp khóa.

### 5.2. Kiểm tra kết quả

Với tenant 10:

| order_id | customer_name | status | gross_amount |
| ---: | --- | --- | ---: |
| 1004 | Binh | CANCELED | 30.00 |
| 1003 | Binh | PAID | 50.00 |
| 1002 | An | PENDING | 80.00 |
| 1001 | An | PAID | 120.00 |

Cột `internal_note` và `email` **không có trong giao diện view**. Đây là một bước giảm phơi lộ dữ liệu qua hợp đồng SELECT; tuy nhiên muốn bảo đảm người đọc không xem được dữ liệu nền, còn phải cấu hình quyền phù hợp.

### 5.3. Vai trò của alias

```sql
o.amount AS gross_amount
c.display_name AS customer_name
```

Alias là một phần của **hợp đồng giao diện**. Tên `gross_amount` có thể được giữ ổn định dù bên dưới sau này tên cột thay đổi hoặc dữ liệu được lấy từ cấu trúc khác.

### 5.4. Tên cột là hợp đồng với client

Khi ứng dụng ánh xạ:

```text
order_id        -> orderId
customer_name   -> customerName
gross_amount    -> grossAmount
```

việc đổi alias trong view có thể làm hỏng mapper/JDBC/ORM/BI tool. Vì vậy quản lý thay đổi view giống như quản lý thay đổi API.

---

## 6. Trừu tượng hóa không chỉ là viết câu SQL ngắn hơn

Một view tốt có thể tập trung nhiều quy ước:

- JOIN đúng khóa và cardinality.
- Chuẩn hóa tên trường.
- Cách giải thích status nghiệp vụ.
- Quy tắc loại các trường nội bộ.
- Cách chuyển đổi đơn vị hoặc biểu diễn một trường dẫn xuất.
- Phân định read model với transactional model.
- Những điều kiện quyền/tenant được kiến trúc bảo đảm đúng.

### 6.1. Chỉ công bố dữ liệu cần thiết

View có thể giảm khả năng người dùng vô tình chọn `SELECT *` rồi đưa trường nhạy cảm lên client:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10;
```

Kết quả không chứa `customers.email` và `orders.internal_note`, vì định nghĩa view không công bố chúng.

**Giới hạn:** nếu role còn quyền SELECT trực tiếp trên bảng nền, role vẫn có thể truy vấn các trường đó. Chỉ tạo view không tự thu hồi quyền nền.

### 6.2. Tập trung JOIN đa tenant

Sai:

```sql
JOIN view_contract_lab.customers AS c
  ON c.customer_id = o.customer_id
```

vì tenant 10 và tenant 20 đều có khách `101`.

Đúng:

```sql
JOIN view_contract_lab.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
```

Đặt JOIN đúng ở view giúp mọi consumer tái sử dụng. Tuy nhiên, **đây không phải thay thế cho quyền tenant**: câu truy vấn view vẫn phải lọc tenant phù hợp hoặc dựa trên RLS đáng tin cậy.

### 6.3. View không thể thay hợp đồng xác thực

Không tin một `tenant_id` do client tùy ý truyền là bằng chứng quyền truy cập. Quyền phải dựa trên identity/session được xác thực, chính sách server, RLS hoặc cơ chế tương đương. View chỉ là một phần của kiến trúc.

---

## 7. Cột dẫn xuất trong view

View có thể tạo trường nghiệp vụ mà không lưu thêm vào bảng nền.

Ví dụ:

```sql
CREATE VIEW view_contract_lab.v_order_flags AS
SELECT
    tenant_id,
    order_id,
    status,
    amount,
    (status = 'PAID') AS is_paid,
    (status = 'CANCELED') AS is_canceled,
    CASE
        WHEN status = 'PAID' THEN 'COMPLETED'
        WHEN status = 'PENDING' THEN 'IN_PROGRESS'
        ELSE 'CLOSED'
    END AS lifecycle_group
FROM view_contract_lab.orders;
```

Dùng:

```sql
SELECT
    order_id,
    is_paid,
    lifecycle_group
FROM view_contract_lab.v_order_flags
WHERE tenant_id = 10
ORDER BY order_id;
```

### 7.1. Một trường dẫn xuất không mặc định được lưu

`is_paid` và `lifecycle_group` được tính theo biểu thức SELECT của view. Khi status của đơn thay đổi, truy vấn view sau khi thay đổi đã commit có thể trả giá trị mới theo snapshot.

### 7.2. Cần cẩn thận với biểu thức biến động

Một view có thể gọi hàm phụ thuộc thời gian, cấu hình session hoặc hàm do ứng dụng định nghĩa. Khi đó kết quả có thể khác nhau giữa các lần SELECT ngay cả khi không đổi bảng nguồn.

Ví dụ:

```sql
CREATE VIEW view_contract_lab.v_order_age AS
SELECT
    tenant_id,
    order_id,
    ordered_at,
    CURRENT_TIMESTAMP - ordered_at AS order_age
FROM view_contract_lab.orders;
```

Trường `order_age` thay đổi theo thời gian. Không coi nó là một cột vật lý được chụp cố định lúc tạo view.

### 7.3. Không làm mất ý nghĩa đơn vị

Nếu view chuyển `amount` sang đơn vị khác, cần đặt tên rõ, ví dụ `amount_in_minor_units` hoặc `amount_vnd`, và hiểu chính sách làm tròn. Hợp đồng view không chỉ là kiểu `NUMERIC` mà còn là **đơn vị và ngữ nghĩa**.

---

## 8. View tổng hợp dùng cho báo cáo

Một view có thể đóng gói `GROUP BY` để báo cáo sử dụng thống nhất một định nghĩa.

Ví dụ: số đơn đã PAID và tổng giá trị các đơn đang PAID theo ngày UTC và tenant.

```sql
CREATE VIEW view_contract_lab.v_daily_paid_orders AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::DATE AS order_day_utc,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_order_value
FROM view_contract_lab.orders
WHERE status = 'PAID'
GROUP BY
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::DATE;
```

Dùng:

```sql
SELECT *
FROM view_contract_lab.v_daily_paid_orders
WHERE tenant_id = 10
ORDER BY order_day_utc;
```

### 8.1. Tại sao view báo cáo cần định nghĩa metric rõ?

`paid_order_value` ở đây nghĩa là **tổng amount của các order có status PAID**, nhóm theo **ngày đặt đơn theo UTC**. Nó không phải:

- Dòng tiền thanh toán trong ngày.
- Doanh thu ròng sau hoàn tiền.
- Giá trị đơn theo ngày status chuyển sang PAID.
- Doanh thu theo múi giờ địa phương.

Nếu đặt tên view là `v_revenue` mà không ghi rõ ngữ nghĩa, nhiều team có thể dùng sai.

### 8.2. View tổng hợp thường không tự động cập nhật được

View có `GROUP BY` và các aggregate không thuộc dạng đơn giản mà PostgreSQL có thể tự ánh xạ một thao tác UPDATE trên kết quả trở về đúng một hàng bảng nền.

Do đó, view này nên được xem là **giao diện đọc báo cáo**, không phải bảng nhận DML như orders.

### 8.3. View tổng hợp không tự tăng tốc

Mỗi truy vấn trên `v_daily_paid_orders` thường vẫn cần thực thi logic tổng hợp trên dữ liệu nền theo một plan phù hợp. Nếu chi phí tổng hợp quá lớn và dashboard gọi thường xuyên, có thể cân nhắc materialized view hoặc bảng summary, nhưng khi đó phải có hợp đồng độ tươi dữ liệu.

---

## 9. View như một hợp đồng ổn định qua thay đổi schema

Đây là một lý do quan trọng để dùng view.

Giả sử ứng dụng từng lưu tên khách trong cột `customers.display_name`. Sau migration, backend có thể lưu thông tin dưới cấu trúc khác, ví dụ hai cột `given_name` và `family_name`.

Không có view, mỗi client phải đổi:

```text
customers.display_name
    |
    v
concat_ws(' ', given_name, family_name)
```

Với view, backend có thể tiếp tục công bố:

```sql
... AS customer_name
```

cho consumer trong khi thực hiện migration cấu trúc dữ liệu nội bộ.

### 9.1. View là lớp anti-corruption của dữ liệu

Một read model có thể giúp tách:

```text
Physical schema:
    tên bảng, cột, cấu trúc chuẩn hóa, FK

View contract:
    tên trường, loại dữ liệu, mức chi tiết, bộ lọc, semantics

Consumer:
    JDBC mapper, báo cáo, dashboard, export, API
```

Khi physical schema thay đổi, chỉ cần giữ view trả lại dữ liệu có cùng ý nghĩa và kiểu phù hợp để consumer không phải thay đổi theo mọi bước migration.

### 9.2. Nhưng view không tự vượt qua mọi thay đổi

Nếu đã drop cột nền mà view còn phụ thuộc vào nó, PostgreSQL có thể chặn DDL hoặc yêu cầu thao tác CASCADE làm mất các đối tượng phụ thuộc. Không thể kỳ vọng view tự tái lập JOIN hoặc chuyển từ kiểu `TEXT` sang `INTEGER`.

Các bước thay đổi schema vẫn cần quản lý dependencies và migration.

### 9.3. Ổn định cấu trúc khác ổn định ngữ nghĩa

Một view vẫn trả cột `amount NUMERIC` nhưng đổi từ “giá trị đơn trước thuế” sang “giá trị đã trừ hoàn tiền” là **breaking change về ngữ nghĩa** dù ứng dụng không báo lỗi kiểu dữ liệu.

Hợp đồng view nên có tài liệu mô tả đơn vị, timezone, trạng thái, NULL, quy tắc tính và quyền truy cập.

---

## 10. CREATE OR REPLACE VIEW: cập nhật định nghĩa

PostgreSQL hỗ trợ thay đổi truy vấn của view bằng:

```sql
CREATE OR REPLACE VIEW view_contract_lab.v_order_flags AS
SELECT
    tenant_id,
    order_id,
    status,
    amount,
    (status = 'PAID') AS is_paid,
    (status = 'CANCELED') AS is_canceled,
    CASE
        WHEN status = 'PAID' THEN 'COMPLETED'
        WHEN status = 'PENDING' THEN 'IN_PROGRESS'
        ELSE 'CLOSED'
    END AS lifecycle_group
FROM view_contract_lab.orders;
```

Lệnh trên định nghĩa lại nội dung SELECT mà không nhất thiết phải drop view.

### 10.1. Hạn chế về cột đã tồn tại

Với một view đã có, `CREATE OR REPLACE VIEW` yêu cầu những cột đã tồn tại được giữ **cùng tên, cùng thứ tự và cùng kiểu dữ liệu**; có thể bổ sung cột mới ở cuối theo khả năng hỗ trợ của PostgreSQL.

Không nên dùng nó để tùy tiện:

- Xóa một cột cũ.
- Đổi tên một cột cũ ngay trong định nghĩa thay thế.
- Đổi kiểu trả về một cột cũ.
- Đảo thứ tự những cột cũ.

Những thay đổi đó có thể bị từ chối hoặc yêu cầu chiến lược migration khác.

### 10.2. Bổ sung cột ở cuối

Ví dụ thêm cột `currency_code` cho view flags:

```sql
CREATE OR REPLACE VIEW view_contract_lab.v_order_flags AS
SELECT
    tenant_id,
    order_id,
    status,
    amount,
    (status = 'PAID') AS is_paid,
    (status = 'CANCELED') AS is_canceled,
    CASE
        WHEN status = 'PAID' THEN 'COMPLETED'
        WHEN status = 'PENDING' THEN 'IN_PROGRESS'
        ELSE 'CLOSED'
    END AS lifecycle_group,
    'VND'::TEXT AS currency_code
FROM view_contract_lab.orders;
```

Ở đây những cột cũ giữ nguyên, cột mới được thêm cuối. Mã tiền tệ chỉ minh họa cấu trúc; hệ thống thực phải lấy currency theo dữ liệu đúng, không gắn VND cho tất cả giao dịch nếu có nhiều currency.

### 10.3. Khi cần đổi tên một cột

PostgreSQL cung cấp:

```sql
ALTER VIEW view_contract_lab.v_order_flags
RENAME COLUMN currency_code TO settlement_currency_code;
```

Tuy nhiên, đổi tên cột có thể làm hỏng consumer đang dùng tên cũ. Cú pháp DDL cho phép không có nghĩa thay đổi đã an toàn ở mức API contract.

### 10.4. Khi cần đổi kiểu hoặc xóa cột

Thường phải tạo view phiên bản mới hoặc tổ chức migration có kiểm soát; không drop/cascade view đang được hàng chục consumer dùng mà không biết dependencies.

---

## 11. Versioning view như versioning API

Một hệ thống có thể công bố:

```text
api.v_orders_v1
api.v_orders_v2
```

Ví dụ:

```sql
CREATE VIEW view_contract_lab.v_orders_v1 AS
SELECT
    tenant_id,
    order_id,
    status,
    amount
FROM view_contract_lab.orders;

CREATE VIEW view_contract_lab.v_orders_v2 AS
SELECT
    tenant_id,
    order_id,
    status,
    amount AS gross_amount,
    ordered_at,
    (status = 'PAID') AS is_paid
FROM view_contract_lab.orders;
```

### 11.1. Tại sao tạo v2?

V2 có thể đổi tên trường và bổ sung semantics mới mà không ép mọi consumer chuyển cùng lúc.

Quy trình:

1. Tạo v2 và kiểm tra output contract.
2. Cấp quyền cho các consumer cần dùng.
3. Chuyển client lần lượt sang v2.
4. Quan sát việc sử dụng và lỗi.
5. Chỉ gỡ v1 khi các consumer còn lại đã được xử lý.

### 11.2. Tên phiên bản không thay kiểm thử

Một view có hậu tố `_v2` vẫn có thể JOIN sai hoặc lộ cột nhạy cảm. Versioning giúp quản lý thay đổi, không chứng nhận chất lượng.

### 11.3. Tránh phụ thuộc vào SELECT *

Client có thể viết:

```sql
SELECT *
FROM view_contract_lab.v_orders_v1;
```

Nếu view thay đổi thêm cột, mapper dựa trên vị trí cột hoặc export định dạng cố định có thể bất ngờ nhận thêm trường. Với interface lâu dài, nên chỉ rõ các cột client cần dùng và kiểm thử kiểu/tên từng cột.

---

## 12. View có dependency vào đối tượng nền

View thường phụ thuộc vào bảng, cột, hàm, operator và các đối tượng cần thiết cho định nghĩa truy vấn.

### 12.1. Khi đổi cấu trúc bảng

Ví dụ view đã dùng `orders.status`. Một thao tác cố xóa cột này khỏi bảng nền có thể bị PostgreSQL từ chối vì các view đang phụ thuộc.

```sql
-- Không chạy trên lab nếu còn muốn giữ các view đang dùng.
ALTER TABLE view_contract_lab.orders
DROP COLUMN status;
```

Thông thường PostgreSQL báo có đối tượng phụ thuộc, trừ khi DDL được điều chỉnh theo cơ chế phù hợp như CASCADE. Nhưng `CASCADE` có thể xóa các view và đối tượng phụ thuộc khác — không sử dụng tùy tiện trong production.

### 12.2. Đổi tên cột nền khác đổi cột giao diện

PostgreSQL theo dõi những tham chiếu view vào đối tượng qua metadata/dependency. Một `ALTER TABLE ... RENAME COLUMN` ở bảng nền có thể được hệ thống xử lý mà không nhất thiết đổi alias đã công bố trong view.

Nhưng không nên dựa vào trực giác để khẳng định migration tương thích: hãy kiểm tra `pg_get_viewdef`, các tên output của view và truy vấn consumer.

### 12.3. Xem định nghĩa view bằng pg_get_viewdef

```sql
SELECT pg_get_viewdef(
    'view_contract_lab.v_order_read_model'::REGCLASS,
    TRUE
) AS view_definition;
```

Đây là cách lấy định nghĩa SELECT mà PostgreSQL lưu, thường đã được deparse/chuẩn hóa; nó không nhất thiết giống 100% chuỗi DDL bạn từng gõ.

### 12.4. Danh sách view trong schema

```sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_views
WHERE schemaname = 'view_contract_lab'
ORDER BY viewname;
```

### 12.5. Thông tin các cột công bố

```sql
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
  AND table_name = 'v_order_read_model'
ORDER BY ordinal_position;
```

Đây là thông tin metadata có thể phục vụ contract test. `information_schema` có phạm vi hiển thị tùy quyền của role.

### 12.6. Xem trong psql

Nếu dùng client `psql`:

```text
\dv
\dv+ view_contract_lab.*
\d+ view_contract_lab.v_order_read_model
```

Đây là **lệnh meta của psql**, không phải SQL để chạy trong mọi JDBC client.

---

## 13. View thường không lưu kết quả: góc nhìn hiệu năng

Giả sử ứng dụng chạy:

```sql
SELECT order_id, customer_name
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00';
```

PostgreSQL có thể tối ưu dựa trên biểu thức nền, JOIN, index, thống kê và độ chọn lọc.

### 13.1. View không bắt buộc làm hai lần SELECT

Không nên hình dung PostgreSQL luôn:

1. Chạy SELECT của view và lưu toàn bộ kết quả.
2. Sau đó lọc WHERE bên ngoài.

Với view thông thường, query rewrite/planning có thể cho optimizer cơ hội tối ưu điều kiện xuyên ranh giới view.

### 13.2. Có thể sử dụng index trên bảng nền

Ví dụ:

```sql
CREATE INDEX idx_orders_tenant_date
ON view_contract_lab.orders (tenant_id, ordered_at);

CREATE INDEX idx_orders_customer
ON view_contract_lab.orders (tenant_id, customer_id);

ANALYZE view_contract_lab.orders;
```

Những index này nằm trên **bảng nền**, không phải trên chính view thường.

Truy vấn view lọc tenant/time có thể được lên kế hoạch sử dụng index phù hợp trên `orders`, tùy quy mô và dữ liệu. Trên lab bảy hàng, `Seq Scan` có thể rẻ hơn.

### 13.3. VIEW không tự hỗ trợ CREATE INDEX

Không thể tạo B-tree hay GIN trực tiếp trên kết quả của view thường theo cách tạo index trên bảng vật lý. Nếu truy vấn view chậm, xem:

- Index ở bảng nền.
- Cách viết JOIN và WHERE.
- GROUP BY/DISTINCT/LIMIT trong view.
- Ước lượng hàng và statistics.
- Có thực sự cần materialized view hoặc summary table không?

### 13.4. View không chữa JOIN fan-out

Nếu JOIN một bảng orders với hai bảng con mỗi bảng có nhiều hàng, SUM của `orders.amount` có thể bị nhân lên. Đặt JOIN đó vào view chỉ làm lỗi trở nên được tái sử dụng rộng hơn.

Khi cần metric ở grain đơn hàng, phải tổng hợp bảng con trước JOIN hoặc thiết kế đúng grain.

---

## 14. Dùng EXPLAIN qua view

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    customer_name,
    gross_amount
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
  AND status = 'PAID';
```

Trong plan bạn có thể thấy scan các bảng nền như `orders` và `customers`, các node JOIN hoặc index scans. Không nhất thiết thấy node riêng tên “Scan on View” như một heap relation vật lý.

### 14.1. Đọc các thông tin chính

| Trường trong EXPLAIN | Ý nghĩa |
| --- | --- |
| `Seq Scan` | Quét bảng nền tuần tự |
| `Index Scan` | Tìm hàng bằng index và truy cập heap |
| `Index Only Scan` | Có thể giảm heap visits khi điều kiện visibility phù hợp |
| `Hash Join` | JOIN bằng cấu trúc hash |
| `Nested Loop` | JOIN lặp theo input bên ngoài |
| `Merge Join` | JOIN tận dụng/sắp xếp thứ tự theo keys |
| `HashAggregate`/`GroupAggregate` | Tổng hợp khi view/query có GROUP BY |
| `Filter`/`Index Cond` | Điều kiện được áp dụng ở đâu |
| `actual rows` | Số hàng thực tế của mỗi node |
| `Buffers` | Số buffer hit/read/temp liên quan |
| `Planning Time` | Thời gian lên kế hoạch |
| `Execution Time` | Thời gian thực thi |

### 14.2. Không kết luận view nhanh hay chậm từ tên đối tượng

Một view có thể nhanh với WHERE chọn lọc nhưng chậm khi consumer chạy:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model;
```

trên toàn bộ lịch sử hàng tỷ rows. Vấn đề là phạm vi và hình dạng truy vấn, không phải chỉ vì view.

### 14.3. Predicate pushdown có giới hạn

Các cấu trúc như:

- GROUP BY.
- DISTINCT.
- LIMIT/OFFSET.
- Một số window functions.
- Một số subquery/set operation.
- Security barriers và điều kiện bảo mật.
- Các biểu thức volatile hoặc không an toàn để di chuyển.

có thể giới hạn việc planner đẩy filter xuống. Không coi view luôn được “inline” giống một SELECT phẳng.

### 14.4. Trên dữ liệu nhỏ, Seq Scan là bình thường

Bảy orders và bốn customers không đủ để thấy rõ lợi ích index. PostgreSQL có thể chọn Seq Scan do chi phí thấp. Không ép dùng index trên production chỉ để plan nhìn “đẹp”.

---

## 15. WHERE ở phía ngoài view: có đẩy xuống được không?

Giả sử:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
  AND status = 'PAID';
```

Với view JOIN đơn giản, PostgreSQL thường có khả năng kết hợp điều kiện `tenant_id` và `status` với thao tác ở bảng nền trong quá trình tối ưu.

### 15.1. View giúp người gọi đặt filter riêng

Thay vì tạo một view cho mỗi tenant, có thể có một view read model chung, còn service xác định phạm vi tenant khi truy vấn theo identity đáng tin cậy.

Nhưng **lọc tenant do application tự viết không thay cơ chế bảo mật server**. Nếu bất kỳ consumer nào có quyền gọi view mà quên WHERE tenant, họ có thể thấy nhiều tenant nếu view/permission không hạn chế điều đó.

### 15.2. View có sẵn filter là một contract khác

```sql
CREATE VIEW view_contract_lab.v_paid_orders AS
SELECT
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
FROM view_contract_lab.orders
WHERE status = 'PAID';
```

View này luôn có điều kiện status PAID trong định nghĩa. Nhưng điều kiện **không giới hạn tenant**; quyền/tenant vẫn cần xử lý riêng.

### 15.3. Nhiều lớp view có thể làm khó truy vết

```text
v_dashboard
   -> v_order_export
       -> v_paid_orders
           -> orders
```

Một chuỗi view có thể giúp tổ chức hợp đồng, nhưng nếu mỗi lớp thay đổi ngữ nghĩa và có nhiều CTE/JOIN/aggregation, việc đọc query plan và rà lỗi sẽ khó hơn.

Chỉ xếp chồng view khi mỗi lớp có nhiệm vụ rõ ràng và được kiểm thử.

---

## 16. View có ORDER BY có bảo đảm thứ tự đầu ra không?

Một câu hỏi thường gặp:

```sql
CREATE VIEW view_contract_lab.v_latest_orders AS
SELECT
    tenant_id, order_id, status, ordered_at
FROM view_contract_lab.orders
ORDER BY ordered_at DESC;
```

Trong thiết kế API, **không nên dựa vào thứ tự bên trong view để bảo đảm hợp đồng sắp xếp của mọi SELECT bên ngoài**.

Người gọi nên chỉ rõ:

```sql
SELECT *
FROM view_contract_lab.v_latest_orders
WHERE tenant_id = 10
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

### 16.1. Vì sao thêm order_id?

Nếu nhiều đơn có cùng ordered_at, `ORDER BY ordered_at DESC` có thể không tạo thứ tự toàn phần. Thêm khóa định danh ổn định giúp kết quả nhất quán hơn, đặc biệt khi phân trang.

### 16.2. ORDER BY trong view có thể tốn chi phí

Nếu view buộc một bước sort không cần thiết cho phần lớn consumer, nó có thể gây thêm công việc hoặc giới hạn optimizer trong một số trường hợp. Không mặc định đặt ORDER BY vào mọi view cho “dễ đọc”.

### 16.3. LIMIT trong view đổi nghĩa dữ liệu

```sql
CREATE VIEW view_contract_lab.v_recent_ten AS
SELECT *
FROM view_contract_lab.orders
ORDER BY ordered_at DESC, tenant_id, order_id
LIMIT 10;
```

View này công bố **chỉ mười hàng toàn hệ thống** theo tiêu chí đã định; người dùng lọc tenant sau đó không có nghĩa nhận mười đơn gần nhất của tenant đó. Nếu cần “10 đơn gần nhất theo tenant”, thiết kế query với filter tenant trước LIMIT hoặc dùng mô hình thích hợp.

Đây là thay đổi ngữ nghĩa, không phải chỉ là tối ưu hiệu năng.

---

## 17. View tự động cập nhật được là gì?

PostgreSQL có thể tự ánh xạ DML trên **một số view đơn giản** xuống bảng nền.

Ví dụ:

```sql
CREATE VIEW view_contract_lab.v_order_edit AS
SELECT
    tenant_id,
    order_id,
    customer_id,
    status,
    amount,
    ordered_at
FROM view_contract_lab.orders;
```

View này chọn cột trực tiếp từ **một bảng nền** và không có JOIN/GROUP BY/DISTINCT. Nó thuộc dạng có thể **tự động cập nhật** theo các điều kiện PostgreSQL hỗ trợ.

### 17.1. UPDATE qua view đơn giản

Chỉ để thử trong transaction lab:

```sql
BEGIN;

UPDATE view_contract_lab.v_order_edit
SET amount = 130.00
WHERE tenant_id = 10 AND order_id = 1001
RETURNING tenant_id, order_id, amount;

ROLLBACK;
```

Thao tác có thể cập nhật hàng tương ứng ở bảng `orders`. `ROLLBACK` bảo đảm không thay đổi dữ liệu gốc sau ví dụ.

### 17.2. INSERT qua view đơn giản

```sql
BEGIN;

INSERT INTO view_contract_lab.v_order_edit (
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
)
VALUES (
    10, 1099, 101,
    'PENDING', 99.00,
    TIMESTAMPTZ '2026-01-16 10:00:00+00'
)
RETURNING tenant_id, order_id, status;

ROLLBACK;
```

Dữ liệu vẫn phải thỏa PRIMARY KEY, FOREIGN KEY, CHECK, NOT NULL và các constraint của bảng nền.

### 17.3. Không phải mọi cột view đều có thể ghi

Một view có expression:

```sql
SELECT amount * 2 AS double_amount
```

không tự có một ánh xạ ngược duy nhất từ `double_amount` sang cột `amount` trong mọi trường hợp.

View có JOIN, GROUP BY, DISTINCT, UNION, aggregate hoặc các cấu trúc khác thường không thỏa điều kiện **automatically updatable** toàn phần. Có thể xem khả năng từng cột qua catalog/information schema và tài liệu phiên bản đang dùng.

### 17.4. Tính cập nhật không phải lý do mặc định dùng view để ghi

Một read model thường chủ ý **chỉ cấp SELECT**, ngay cả khi PostgreSQL có thể tự động UPDATE nó. Khả năng DML là một đặc tính SQL, còn quyền ghi là quyết định kiến trúc.

---

## 18. WITH CHECK OPTION: giữ predicate khi ghi qua view

Giả sử có một view chỉ hiển thị đơn PAID của tenant 10:

```sql
CREATE VIEW view_contract_lab.v_tenant10_paid_edit AS
SELECT
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
FROM view_contract_lab.orders
WHERE tenant_id = 10
  AND status = 'PAID'
WITH CASCADED CHECK OPTION;
```

View này đơn giản, dựa trên một bảng và có khả năng cập nhật tự động trong các điều kiện phù hợp.

**CHECK OPTION** dùng để bảo đảm thao tác INSERT/UPDATE qua view không tạo một hàng nằm ngoài điều kiện được view chấp nhận, theo phạm vi LOCAL/CASCADED.

### 18.1. Ví dụ UPDATE hợp lệ

```sql
BEGIN;

UPDATE view_contract_lab.v_tenant10_paid_edit
SET amount = 125.00
WHERE tenant_id = 10 AND order_id = 1001
RETURNING order_id, status, amount;

ROLLBACK;
```

Order vẫn ở tenant 10 và status PAID.

### 18.2. Ví dụ thay đổi làm hàng biến mất khỏi view

Nếu thực hiện:

```sql
-- Thử riêng trong môi trường lab; câu này dự kiến bị từ chối
-- vì tạo ra hàng không thỏa predicate của view.
UPDATE view_contract_lab.v_tenant10_paid_edit
SET status = 'PENDING'
WHERE tenant_id = 10 AND order_id = 1001;
```

với CHECK OPTION, PostgreSQL không cho thao tác ghi qua view tạo hàng không còn thỏa điều kiện tương ứng.

### 18.3. Nếu không có CHECK OPTION?

Một view cập nhật được với `WHERE status='PAID'` nhưng không có CHECK OPTION có thể cho phép UPDATE làm hàng rời khỏi phạm vi SELECT của view, tùy cấu trúc và quyền. Sau khi cập nhật, hàng có thể “biến mất” khỏi kết quả view.

Điều này không luôn là lỗi: có nghiệp vụ muốn chuyển trạng thái qua một view lọc. Nhưng phải chọn có chủ đích.

### 18.4. CHECK OPTION không phải ràng buộc toàn hệ thống

CHECK OPTION áp dụng cho **DML qua view phù hợp**, không thay thế CHECK constraint của bảng nền và không kiểm soát mọi UPDATE thực hiện trực tiếp trên bảng.

Nếu quy tắc “không được có amount âm” phải luôn đúng, hãy dùng constraint bảng nền, không chỉ view.

---

## 19. LOCAL và CASCADED CHECK OPTION

Khi có nhiều lớp view cập nhật được:

```sql
CREATE VIEW view_contract_lab.v_tenant10_orders AS
SELECT
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
FROM view_contract_lab.orders
WHERE tenant_id = 10;

CREATE VIEW view_contract_lab.v_tenant10_paid_local AS
SELECT *
FROM view_contract_lab.v_tenant10_orders
WHERE status = 'PAID'
WITH LOCAL CHECK OPTION;
```

### 19.1. LOCAL

`LOCAL CHECK OPTION` kiểm tra điều kiện của **view hiện tại** trong những trường hợp được hỗ trợ, không tự yêu cầu kiểm tra mọi điều kiện của các view bên dưới nếu chúng không có CHECK OPTION riêng.

Trong ví dụ này, local view có điều kiện `status='PAID'`. Ràng buộc `tenant_id=10` thuộc view bên dưới và không nên mặc định được enforce bởi LOCAL nếu view dưới chưa có CHECK OPTION riêng.

### 19.2. CASCADED

`CASCADED CHECK OPTION` mở rộng việc kiểm tra qua các điều kiện của các view tự động cập nhật được nằm bên dưới theo quy tắc PostgreSQL áp dụng.

```sql
CREATE VIEW view_contract_lab.v_tenant10_paid_cascaded AS
SELECT *
FROM view_contract_lab.v_tenant10_orders
WHERE status = 'PAID'
WITH CASCADED CHECK OPTION;
```

Khi này cả predicate status và predicate tenant của chuỗi view tự động cập nhật được có thể được kiểm tra.

### 19.3. Giới hạn với trigger/rule

Đối với view dùng `INSTEAD OF` trigger hoặc cơ chế rewrite phức tạp, CHECK OPTION có những giới hạn và cách tương tác riêng; không giả định mọi điều kiện của mọi lớp đều được enforce giống trường hợp đơn giản.

### 19.4. Dùng CASCADED không thay authorization

Một người có quyền trực tiếp trên bảng orders vẫn có thể đi đường bảng nền. CHECK OPTION chỉ giới hạn hành vi **qua view tương ứng**. Nếu mục tiêu là phân quyền tenant, phải bảo vệ bằng quyền và RLS/tenant guard có cơ sở xác thực phù hợp.

---

## 20. INSTEAD OF trigger cho view phức tạp

Một view JOIN không có ánh xạ ghi rõ ràng. Ví dụ:

```sql
SELECT
    o.order_id,
    c.display_name,
    o.amount
FROM orders o
JOIN customers c ON ...;
```

Nếu người dùng chạy:

```sql
UPDATE view_name
SET display_name = 'New name',
    amount = 200
WHERE order_id = 1001;
```

PostgreSQL cần biết có nên cập nhật customers, orders hay cả hai, và xử lý trường hợp một customer có nhiều orders. Không thể suy ra một chiến lược duy nhất cho mọi view JOIN.

### 20.1. INSTEAD OF trigger

PostgreSQL cho phép định nghĩa trigger `INSTEAD OF INSERT/UPDATE/DELETE` trên view trong những trường hợp hỗ trợ. Trigger function có thể giải mã thao tác ở lớp view thành các DML trên bảng nền theo quy tắc bạn thiết kế.

Mô hình:

```text
UPDATE trên view
      |
      v
INSTEAD OF trigger
      |
      +--> kiểm tra quyền/nghiệp vụ
      +--> UPDATE orders
      +--> UPDATE customers (nếu phù hợp)
      +--> RETURN NEW / NULL theo trigger contract
      |
      v
Transaction trên database
```

### 20.2. Không tự biến mọi view read model thành writable

Trigger cần xử lý:

- Khóa tenant/authorization.
- Concurrency và stale update.
- Transaction atomicity.
- Ràng buộc FK/unique/check.
- Số hàng bị ảnh hưởng.
- INSERT với dữ liệu thiếu.
- Cách xử lý cập nhật nhiều bảng.
- Lỗi và rollback.
- RETURNING/trigger return value.

Độ phức tạp có thể cao hơn việc expose API mutation riêng, có kiểm soát rõ.

### 20.3. Rule và INSTEAD OF trigger khác nhau

PostgreSQL cũng có rewrite rules, nhưng với business DML phức tạp, trigger thường dễ xác định hành vi từng row hơn. Không sử dụng rule như một “hàm cập nhật view” tùy tiện nếu chưa hiểu query rewriting và các tác động phụ.

---

## 21. Quyền SELECT trên view và quyền bảng nền

Một lợi ích của view là có thể cấp quyền đọc một giao diện giới hạn mà **không cấp quyền trực tiếp vào mọi bảng/cột nền** theo cơ chế mặc định của view.

Mô hình:

```text
Role: report_reader
      |
      | SELECT trên api.v_order_read_model
      v
View (owner có quyền đọc bảng nền)
      |
      +--> internal.orders
      +--> internal.customers

report_reader không nhất thiết có SELECT trực tiếp
trên internal.orders hoặc internal.customers
```

### 21.1. Thử role trong môi trường được phép

Các câu sau chỉ mang tính minh họa về quản trị quyền; cần quyền CREATE ROLE/GRANT phù hợp và không chạy tùy tiện trên production.

```sql
CREATE ROLE view_lab_reader NOLOGIN;

GRANT USAGE ON SCHEMA view_contract_lab
TO view_lab_reader;

GRANT SELECT ON view_contract_lab.v_order_read_model
TO view_lab_reader;
```

Khi đó role có thể được cấp quyền dùng view mà không nhất thiết được cấp SELECT trên các bảng nền. Tuy nhiên, hiệu quả thực tế còn phụ thuộc view owner, đối tượng nền, RLS và các tùy chọn view.

### 21.2. Không cấp quyền quá rộng chỉ vì “đơn giản”

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA view_contract_lab
TO view_lab_reader;
```

khác hẳn việc cấp quyền trên **một view**. Câu trên có thể mở quyền đọc cả bảng nền và những view khác trong schema, làm mất ý nghĩa giới hạn bề mặt dữ liệu.

### 21.3. Quyền ở cấp cột của view

PostgreSQL hỗ trợ một số hình thức GRANT theo cột, ví dụ:

```sql
GRANT SELECT (
    tenant_id, order_id, status, gross_amount
)
ON view_contract_lab.v_order_read_model
TO view_lab_reader;
```

Nếu role **đã được cấp SELECT trên toàn view** thì GRANT giới hạn cột bổ sung này **không thu hẹp** quyền trước đó. Muốn chỉ cho phép một số cột, phải thiết kế lại grants/revokes phù hợp và kiểm tra quyền hiệu lực.

Thực tế thường rõ hơn khi tạo một view riêng chỉ chứa các cột được phép, rồi chỉ cấp quyền cho view đó.

---

## 22. Mặc định view dùng quyền của ai?

Trong PostgreSQL, view thông thường có cơ chế kiểm tra quyền đối tượng nền theo **view owner** trong các trường hợp mặc định. Điều này cho phép một role có quyền đọc view nhưng không có quyền đọc trực tiếp bảng nền.

Tuy nhiên:

- Người gọi vẫn cần quyền truy cập view và USAGE trên schema thích hợp.
- Owner cần có quyền thích hợp trên các đối tượng view tham chiếu.
- Các hàm gọi bên trong view có cơ chế kiểm tra quyền thực thi riêng và tùy đặc tính security definer/invoker của hàm.
- Row-Level Security có thể áp dụng khác nhau tùy owner, security_invoker, FORCE RLS, BYPASSRLS và cấu hình.
- Các thay đổi quyền của owner hoặc view có thể làm ảnh hưởng consumer.

### 22.1. View không mặc định là security definer function

Không đồng nhất view với `SECURITY DEFINER` SQL function. Chúng là những cơ chế PostgreSQL khác nhau, dù đều có thể làm việc với quyền và đối tượng nền.

### 22.2. Ownership là thành phần của kiến trúc

Nếu view được sở hữu bởi superuser hoặc role có quyền quá rộng, một số chính sách bảo vệ bảng nền có thể bị vượt qua theo quy tắc owner/BYPASSRLS. Với các view dùng để công bố dữ liệu nhạy cảm, nên có role owner chuyên dụng và kiểm tra quyền tối thiểu.

### 22.3. Cấp SELECT view không phải cách cấp quyền không cần nghĩ tới RLS

Một view lọc tenant bằng WHERE và một base table có RLS là hai lớp khác nhau. Cần thiết kế rõ chính sách nào quyết định người đọc được thấy hàng nào; không cho rằng VIEW tự kế thừa “user identity” theo cách người viết API hình dung.

---

## 23. security_invoker: thực thi quyền bảng nền theo người gọi

Từ PostgreSQL 15, view có tùy chọn `security_invoker`.

Cú pháp ví dụ:

```sql
CREATE VIEW view_contract_lab.v_orders_invoker
WITH (security_invoker = true)
AS
SELECT
    tenant_id, order_id, status, amount
FROM view_contract_lab.orders;
```

Ý tưởng: khi truy vấn một security-invoker view, quyền đối với các quan hệ nền và chính sách RLS được xét theo **người gọi** theo cơ chế tính năng này, thay vì theo view owner như mặc định.

### 23.1. Sự khác biệt quan trọng

| Tình huống | View mặc định | View security_invoker |
| --- | --- | --- |
| Caller có SELECT view nhưng không có quyền bảng nền | Có thể đọc qua quyền của view owner | Thường bị từ chối vì thiếu quyền bảng nền |
| RLS trên bảng nền | Phụ thuộc owner/thiết lập áp dụng | Thường dựa trên caller |
| Dùng view để công bố cột được chọn mà không cấp quyền bảng nền | Có thể phù hợp | Cần cân nhắc vì caller vẫn cần quyền nền |
| Dùng view như cách tái sử dụng SQL nhưng giữ quyền người gọi | Không mặc định như vậy | Thường phù hợp hơn |

Các trường hợp quyền/hàm/nested views vẫn cần kiểm tra phiên bản và cấu hình thật.

### 23.2. Không chuyển mọi view sang invoker một cách máy móc

Nếu một dashboard chỉ được cấp SELECT trên view mà không được cấp SELECT trên bảng nền, bật `security_invoker=true` có thể khiến dashboard gặp lỗi permission denied.

Ngược lại, nếu kiến trúc yêu cầu RLS của từng caller được thực thi trên bảng nền, view mặc định có thể không có semantics mong đợi.

**Đây là lựa chọn bảo mật**, không phải một tùy chọn chỉ để tối ưu.

### 23.3. Kiểm tra quyền thực tế

Khi thử trên staging, nên có ít nhất:

- Role chỉ có SELECT view.
- Role có SELECT view và đủ quyền bảng nền.
- Role có chính sách RLS giới hạn tenant.
- View owner khác với caller.
- Trường hợp owner của bảng/bypass RLS có thể ảnh hưởng.
- Kiểm tra xem mỗi role thực sự đọc được bao nhiêu hàng.

Không kết luận từ việc một session superuser chạy SELECT thành công.

---

## 24. security_barrier: hạn chế một loại rủi ro đẩy điều kiện

Một view dùng để ẩn hàng nhạy cảm có thể cần quan tâm tới **thứ tự đánh giá điều kiện** và các hàm không an toàn khi được optimizer đẩy xuống.

PostgreSQL hỗ trợ:

```sql
CREATE VIEW view_contract_lab.v_tenant10_barrier
WITH (security_barrier = true)
AS
SELECT
    tenant_id, order_id, status, amount
FROM view_contract_lab.orders
WHERE tenant_id = 10;
```

`security_barrier` được thiết kế nhằm ngăn một số biểu thức **không leakproof** do người gọi cung cấp được đẩy qua hàng rào điều kiện của view theo cách có thể làm rò rỉ thông tin từ các hàng bị lọc.

### 24.1. Không đồng nhất với RLS

`security_barrier` không tự xác định tenant từ token đăng nhập, không tự cấp/thu quyền bảng nền và không thay thế RLS.

### 24.2. Vì sao có thể ảnh hưởng hiệu năng?

Hàng rào bảo mật có thể giới hạn predicate pushdown. Một số điều kiện và index path có thể không được áp dụng như ở view đơn giản, đặc biệt nếu biểu thức không leakproof. Vì vậy cần cân bằng an toàn và chi phí, đồng thời thử `EXPLAIN` với role/query thật.

### 24.3. Không bảo đảm chặn mọi kênh thông tin

Security barrier là một tính năng bảo vệ trong mô hình SQL executor/optimizer, **không phải lời bảo đảm tuyệt đối loại bỏ mọi side channel** (chẳng hạn timing, thống kê hoặc các hành vi ngoài phạm vi cơ chế). Bảo mật thực tế còn cần permissions, RLS, chính sách dữ liệu và kiểm thử.

### 24.4. security_invoker và security_barrier không cùng chức năng

- `security_invoker`: quyết định **ngữ nghĩa quyền của người gọi đối với bảng nền**.
- `security_barrier`: kiểm soát **một số tối ưu có thể vượt qua ranh giới lọc bảo mật**.

Có thể cần một, cả hai hoặc không cái nào tùy mục tiêu. Không xem hai tùy chọn là từ đồng nghĩa.

---

## 25. View và Row-Level Security

Row-Level Security (RLS) có thể được dùng để hạn chế các hàng một role được đọc/sửa tại **bảng nền**.

Ví dụ minh họa cấu hình:

```sql
ALTER TABLE view_contract_lab.orders
ENABLE ROW LEVEL SECURITY;
```

RLS cần các policies được thiết kế theo identity đáng tin cậy. Ví dụ khái niệm:

```sql
-- Chỉ minh họa ý tưởng: không triển khai policy thực
-- dựa vào một giá trị tenant do client tùy ý SET.
--
-- CREATE POLICY ... ON orders
-- USING (tenant_id = trusted_tenant_context);
```

### 25.1. Những câu hỏi phải trả lời

- PostgreSQL role nào đại diện cho caller?
- Tenant context lấy từ đâu, có thể bị người dùng tự sửa không?
- View được sở hữu bởi role nào?
- View đang là security_invoker hay mặc định?
- Role owner/bảng có bypass RLS không?
- Chính sách có áp dụng với SELECT, UPDATE, INSERT và DELETE khác nhau?
- Các hàm trong view thực thi bằng quyền ai?

### 25.2. Cảnh báo với current_setting trong multi-tenant

Một mẫu phổ biến:

```sql
WHERE tenant_id = current_setting('app.tenant_id')::INTEGER
```

chỉ an toàn khi kiến trúc chứng minh giá trị session này được thiết lập bởi tầng tin cậy, người gọi không thể giả mạo, connection pool không làm rò context giữa request và mọi đường truy cập được bảo vệ.

Nếu client SQL bất kỳ có thể tự `SET app.tenant_id` sang một tenant khác, dùng giá trị đó làm ranh giới phân quyền là không đủ.

### 25.3. RLS ở bảng nền vẫn phải đúng ngay cả khi view có filter

Đừng đặt một view lọc tenant rồi cấp SELECT toàn bộ bảng nền; đường truy vấn trực tiếp có thể bỏ qua view.

Một mô hình an toàn hơn thường dùng:

- Bảo vệ bảng nền bằng quyền/RLS phù hợp.
- View công bố đúng cột và semantics.
- Role API chỉ có quyền thật sự cần.
- Kiểm thử từ nhiều role và nhiều tenant.
- Tránh owner không phù hợp làm bỏ qua chính sách RLS.

---

## 26. Một view không phải tự động là API bảo mật

View có thể đóng vai trò một **database-facing API**, nhưng không thay thế:

- Authentication.
- Authorization.
- Validation input.
- Rate limiting.
- Audit logging.
- Application/business transactions.
- Phân loại dữ liệu cá nhân.
- Kiểm soát việc công bố dữ liệu qua reports/exports.
- Quản trị đặc quyền và credential.

### 26.1. Tránh tên trường gây hiểu nhầm

Một view đặt tên `v_public_orders` nhưng chứa `customer_email` không tự trở thành an toàn chỉ vì có chữ “public”.

### 26.2. Đừng sử dụng SELECT * không kiểm soát

View hợp đồng nên công bố danh sách cột tường minh:

```sql
SELECT
    tenant_id,
    order_id,
    customer_id,
    status,
    amount
FROM view_contract_lab.orders;
```

thay vì:

```sql
SELECT * FROM view_contract_lab.orders;
```

trong lớp hợp đồng dài hạn.

PostgreSQL lưu định nghĩa view tại thời điểm tạo; `SELECT *` trong CREATE VIEW không nên được hiểu là cam kết tự động bổ sung mọi cột mới của bảng nền về sau. Tên các cột có thể tình cờ thành phụ thuộc hợp đồng khi schema thay đổi. Viết rõ danh sách cột giúp review và kiểm soát việc công bố thông tin.

### 26.3. Hạn chế quyền thực thi các hàm

View có thể gọi SQL functions. Nếu một hàm có tác dụng phụ hoặc đặc tính quyền khác thường, người gọi view có thể gây ra hành vi không mong đợi. Cần đánh giá function volatility, SECURITY DEFINER/INVOKER, quyền EXECUTE và search_path trong các hàm do hệ thống tự viết.

---

## 27. View không nhận tham số như hàm

Không có cú pháp view thông thường:

```sql
SELECT *
FROM v_orders(tenant_id => 10);
```

nếu `v_orders` được tạo bằng `CREATE VIEW`, không phải hàm.

Người tiêu thụ thường truyền điều kiện qua:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = $1
  AND ordered_at >= $2
  AND ordered_at < $3;
```

### 27.1. Khi nào cần SQL function?

Nếu muốn một giao diện **có tham số** với hợp đồng riêng, có thể dùng function:

```sql
CREATE FUNCTION view_contract_lab.get_orders_in_range(
    p_tenant_id INTEGER,
    p_start TIMESTAMPTZ,
    p_end TIMESTAMPTZ
)
RETURNS TABLE (
    tenant_id INTEGER,
    order_id BIGINT,
    status TEXT,
    gross_amount NUMERIC,
    ordered_at TIMESTAMPTZ
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        v.tenant_id,
        v.order_id,
        v.status,
        v.gross_amount,
        v.ordered_at
    FROM view_contract_lab.v_order_read_model AS v
    WHERE v.tenant_id = p_tenant_id
      AND v.ordered_at >= p_start
      AND v.ordered_at < p_end;
$$;
```

Gọi:

```sql
SELECT *
FROM view_contract_lab.get_orders_in_range(
    10,
    TIMESTAMPTZ '2026-01-01 00:00:00+00',
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
);
```

### 27.2. Function có thêm trách nhiệm

Một function có thể có:

- Tham số và default arguments.
- Quyền EXECUTE.
- Volatility và parallel safety metadata.
- SECURITY INVOKER/DEFINER.
- Search path và dependency.
- Khả năng inline trong những điều kiện cụ thể.

Vì vậy function có thể phù hợp với API có tham số, nhưng không thay thế view trong mọi trường hợp.

### 27.3. Đừng dùng function tham số tenant mà bỏ authorization

`p_tenant_id=10` chỉ là một tham số. Nếu người gọi có thể truyền 20, function vẫn phải có quyền và chính sách phù hợp. Thêm tham số không tự biến một query thành thao tác được phân quyền.

---

## 28. View và CTE: hai mức tái sử dụng khác nhau

CTE (*Common Table Expression*):

```sql
WITH paid_orders AS (
    SELECT *
    FROM view_contract_lab.orders
    WHERE status = 'PAID'
)
SELECT tenant_id, COUNT(*)
FROM paid_orders
GROUP BY tenant_id;
```

CTE chỉ tồn tại trong phạm vi **một câu statement**. Nó không tự tạo một đối tượng schema có tên, quyền và lifecycle độc lập như view.

### 28.1. Khi dùng CTE

- Chia một truy vấn phức tạp thành bước dễ đọc.
- Tính một tập trung gian.
- Tổ chức query duy nhất cho report.
- Dùng recursive query khi cần.

### 28.2. Khi dùng view

- Nhiều consumer dùng cùng một hợp đồng.
- Muốn cấp quyền ở cấp đối tượng schema.
- Muốn che JOIN/schema bên dưới.
- Muốn có tên và dependency được quản lý.
- Muốn versioning read model.

### 28.3. CTE cũng không mặc định là cache

Với PostgreSQL hiện đại, một số CTE có thể được inline hoặc materialize tùy điều kiện và từ khóa `MATERIALIZED/NOT MATERIALIZED`. Không đánh giá view là nhanh/chậm chỉ vì CTE “tốt hơn” hay “kém hơn” theo khẩu quyết.

---

## 29. View và materialized view: ví dụ thực hành

Từ view báo cáo thường:

```sql
SELECT *
FROM view_contract_lab.v_daily_paid_orders;
```

có thể tạo một materialized view lưu kết quả của định nghĩa tổng hợp:

```sql
CREATE MATERIALIZED VIEW view_contract_lab.mv_daily_paid_orders
AS
SELECT *
FROM view_contract_lab.v_daily_paid_orders
WITH DATA;
```

Query:

```sql
SELECT *
FROM view_contract_lab.mv_daily_paid_orders
WHERE tenant_id = 10
ORDER BY order_day_utc;
```

### 29.1. Thay đổi ở bảng nền không cập nhật tự động materialized view

Ví dụ sau khi một đơn chuyển từ PENDING sang PAID, query trên view thường có thể thấy metric mới ở snapshot thích hợp; materialized view vẫn giữ kết quả cũ cho đến khi refresh.

```sql
REFRESH MATERIALIZED VIEW
    view_contract_lab.mv_daily_paid_orders;
```

### 29.2. Index trên materialized view

Khác view thường, materialized view có dữ liệu vật lý nên có thể tạo index:

```sql
CREATE UNIQUE INDEX idx_mv_daily_paid_tenant_day
ON view_contract_lab.mv_daily_paid_orders (
    tenant_id, order_day_utc
);
```

Chỉ dùng UNIQUE khi thực sự có một hàng cho mỗi cặp khóa; với định nghĩa GROUP BY của lab, cặp đó là grain của kết quả.

### 29.3. Refresh concurrently

Trong các điều kiện PostgreSQL hỗ trợ, ví dụ materialized view đã populate và có unique index hợp lệ chỉ dùng tên cột, phủ tất cả hàng, có thể:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    view_contract_lab.mv_daily_paid_orders;
```

Lệnh không có nghĩa refresh miễn phí hoặc tự incremental. Nó giảm một số hình thức chặn reader trong khi refresh, với chi phí và hạn chế riêng.

### 29.4. Lựa chọn theo nhu cầu

| Yêu cầu | Lựa chọn đáng xem |
| --- | --- |
| Luôn đọc dữ liệu mới theo snapshot DB | View thường |
| Hợp đồng cột ổn định, JOIN đơn giản | View thường |
| Truy vấn aggregate đắt, dashboard chấp nhận trễ | Materialized view |
| Tăng từng event với cập nhật gần thời gian thực | Summary table/pipeline có idempotency |
| Query dùng một lần | SELECT/CTE |
| Giao diện truy vấn cần tham số | SQL function hoặc query có bind parameters |

---

## 30. Dữ liệu đọc qua view và MVCC

PostgreSQL dùng **Multi-Version Concurrency Control (MVCC)**. View không tạo một vùng nhất quán độc lập ngoài transaction.

### 30.1. Một SELECT là một truy vấn

Khi ứng dụng thực thi:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10;
```

nó thấy dữ liệu theo snapshot và isolation level của transaction/statement.

### 30.2. Hai SELECT có thể khác nhau

Ở `READ COMMITTED`, mỗi SELECT trong cùng transaction có thể lấy snapshot mới theo quy tắc isolation. Nếu một transaction khác COMMIT UPDATE giữa hai statement, kết quả qua view có thể thay đổi.

### 30.3. Một transaction đọc nhất quán

Nếu cần nhiều báo cáo cùng một snapshot, có thể cân nhắc `REPEATABLE READ` trong transaction đọc ngắn, theo yêu cầu nghiệp vụ và đặc điểm hệ thống.

Không giữ transaction mở nhiều giờ chỉ để “khóa view”: nó không phải cơ chế snapshot cache, và các transaction lâu có thể ảnh hưởng VACUUM/MVCC cleanup.

### 30.4. View trên standby có thể trễ

Nếu ứng dụng truy vấn view ở **asynchronous replica**, dữ liệu có thể chậm hơn primary do replication lag. View không tự sửa độ trễ này.

### 30.5. Nhiều view trong một statement

Khi một SELECT JOIN nhiều views, các bảng nền được xử lý theo snapshot áp dụng cho statement đó. Đừng xây dashboard bằng nhiều HTTP requests độc lập rồi mặc định chúng đều đọc chính xác cùng thời điểm.

---

## 31. Ứng dụng Java/JDBC đọc view

Trong Java, view có thể là nguồn dữ liệu được ánh xạ về DTO giống một query đọc bảng.

Ví dụ:

```java
import java.math.BigDecimal;
import java.time.OffsetDateTime;

public record OrderReadDto(
    int tenantId,
    long orderId,
    String customerName,
    String status,
    BigDecimal grossAmount,
    OffsetDateTime orderedAt
) {}
```

Repository:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class OrderReadRepository {

    public List<OrderReadDto> listPaidOrders(
            Connection connection,
            int authenticatedTenantId) throws SQLException {

        String sql = """
            SELECT
                tenant_id,
                order_id,
                customer_name,
                status,
                gross_amount,
                ordered_at
            FROM view_contract_lab.v_order_read_model
            WHERE tenant_id = ?
              AND status = 'PAID'
            ORDER BY ordered_at DESC, order_id DESC
            """;

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setInt(1, authenticatedTenantId);

            List<OrderReadDto> results = new ArrayList<>();

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    results.add(new OrderReadDto(
                        rs.getInt("tenant_id"),
                        rs.getLong("order_id"),
                        rs.getString("customer_name"),
                        rs.getString("status"),
                        rs.getBigDecimal("gross_amount"),
                        rs.getObject(
                            "ordered_at",
                            OffsetDateTime.class
                        )
                    ));
                }
            }

            return results;
        }
    }
}
```

### 31.1. VIEW không thay bind parameters

Vẫn phải dùng `PreparedStatement`. Không nối dữ liệu từ người dùng vào WHERE/ORDER BY một cách không an toàn.

### 31.2. Tham số tenant phải đáng tin

`authenticatedTenantId` phải đến từ ngữ cảnh được xác thực trên server, không lấy nguyên một chuỗi từ request rồi giả định đó là quyền hợp lệ. Và nếu client SQL có thể tự bỏ WHERE, chính sách quyền ở database vẫn phải đủ mạnh.

### 31.3. Map theo tên cột ổn định

Đổi `gross_amount` thành `amount` trong view có thể khiến `rs.getBigDecimal("gross_amount")` lỗi. Đó là lý do metadata và contract tests cần bảo vệ tên/kiểu cột.

### 31.4. Trong ORM

Có thể map view như một entity chỉ đọc hoặc DTO/projection tùy thư viện. Không mặc định một view có JOIN và computed columns trở thành đối tượng ORM có thể UPDATE/DELETE an toàn.

Cần định nghĩa key ổn định, read-only intent và transaction/flush behavior rõ ràng.

---

## 32. Hợp đồng NULL, timezone và kiểu dữ liệu

Một view có thể thay đổi cách trình bày dữ liệu nhưng phải làm rõ contract.

### 32.1. NULL do LEFT JOIN

Nếu muốn giữ đơn ngay cả khi không có bản ghi phụ liên quan, view có thể dùng LEFT JOIN. Khi đó cột phía phải có thể NULL.

Consumer phải biết:

```text
customer_name có thể NULL?
NULL nghĩa thiếu dữ liệu hay không được phép xem?
```

Đừng tự `COALESCE(customer_name,'Unknown')` nếu nó che giấu sự khác biệt nghiệp vụ giữa khách chưa có dữ liệu và dữ liệu bị hạn chế.

### 32.2. TIMESTAMPTZ và ngày báo cáo

View:

```sql
SELECT (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc
```

công bố **ngày UTC**, khác ngày theo `Asia/Ho_Chi_Minh`. Nếu report theo ngày địa phương, cần nêu rõ timezone và boundary.

### 32.3. NUMERIC và tiền tệ

`NUMERIC(14,2)` phù hợp cho số thập phân chính xác theo quy tắc làm tròn; view không nên tự trộn tiền tệ khác nhau vào một SUM mà không định nghĩa tỷ giá.

### 32.4. ENUM/TEXT và evolution

Nếu `status` là TEXT với CHECK constraint, việc thêm giá trị mới có thể làm consumer có `switch`/`CASE` không xử lý. View vẫn trả TEXT nhưng business contract đã mở rộng. Hãy kiểm thử cả bộ giá trị status hợp lệ, không chỉ kiểu dữ liệu.

---

## 33. Migration view theo mô hình expand–migrate–contract

Một chiến lược an toàn khi đổi schema:

### Giai đoạn A — Expand

Bổ sung bảng/cột mới và cơ chế ghi tương thích nếu cần, không phá view đang được consumer sử dụng.

Ví dụ thêm một cột mới vào bảng nền:

```sql
ALTER TABLE view_contract_lab.orders
ADD COLUMN currency_code TEXT;
```

Lúc này view cũ vẫn công bố bộ cột như trước.

### Giai đoạn B — Backfill và xác nhận

Dữ liệu cũ cần được điền giá trị đúng. Không gán currency mặc định VND nếu hệ thống có nhiều tiền tệ và không thể suy ra từ dữ liệu.

Chạy data migration, xác minh constraints, JOIN/row counts và độ đúng trước khi chuyển view.

### Giai đoạn C — Tạo view interface mới hoặc thêm cột ở cuối

Ví dụ v2 công bố currency:

```sql
CREATE VIEW view_contract_lab.v_order_amount_v2 AS
SELECT
    tenant_id,
    order_id,
    status,
    amount AS gross_amount,
    currency_code
FROM view_contract_lab.orders;
```

### Giai đoạn D — Migrate consumers

Cập nhật DTO/BI report/ETL, cấp quyền SELECT view mới, kiểm tra query plans, metric và quyền từ từng role.

### Giai đoạn E — Contract

Chỉ khi đã biết không còn consumer phụ thuộc interface cũ mới tính tới drop/rename, revoke quyền hoặc xóa các cột nền cũ.

### 33.1. Vì sao không DROP CASCADE trước?

`DROP VIEW ... CASCADE` có thể xóa các view phụ thuộc. Nếu nhiều đội dùng một schema chung, hậu quả vượt ra khỏi một ứng dụng. Phải lập bản đồ dependencies trước migration.

### 33.2. Thử trên staging

Một migration tốt cần chạy:

- DDL thực tế theo đúng thứ tự.
- Query contract trước/sau.
- Kiểm tra quyền.
- EXPLAIN truy vấn quan trọng.
- Kiểm tra rollback/recovery.
- Test kết nối từ các version ứng dụng cũ/mới.

---

## 34. Khi nào nên tạo view và khi nào không?

| Tình huống | View có phù hợp? | Lý do |
| --- | --- | --- |
| Nhiều service cần cùng JOIN và tên cột | Có | Giao diện đọc thống nhất |
| Hạn chế các cột công bố cho report role | Có, cùng quyền đúng | Thu hẹp bề mặt dữ liệu |
| Ẩn cấu trúc normalization nội bộ | Có | Giảm coupling |
| Các metric báo cáo cùng định nghĩa | Có, nếu công thức đúng | Tập trung ngữ nghĩa |
| Muốn cache COUNT(*) của tỷ dòng | View thường không đủ | Cần vật hóa/summary |
| Muốn INSERT/UPDATE vào JOIN phức tạp | Cần thiết kế khác hoặc trigger | Không tự động writable |
| Giao diện truy vấn cần tham số | Có thể dùng view+WHERE hoặc SQL function | View không có tham số nội tại |
| Một query đơn giản chỉ dùng một lần | Không nhất thiết | SELECT trực tiếp/CTE đủ |
| Cần quyền tenant cho user không tin cậy | View chỉ là một phần | Phải có auth/RLS/permissions |
| Cần gửi dữ liệu sang hệ thống khác | Không đủ | Cần API/export/replication riêng |
| Cần tìm kiếm toàn văn, JSONB GIN | Có thể expose view | Nhưng index nằm ở bảng nền |
| Nhiều lớp view trừu tượng trùng lặp | Cân nhắc | Có thể tăng độ khó debug |
| Dữ liệu thay đổi nhanh nhưng dashboard chấp nhận trễ | Cân nhắc materialized view | Đổi chi phí tính toán lấy freshness |

### 34.1. View không phải một loại “bảng tốt hơn”

View là công cụ tổ chức logic truy vấn và quyền; bảng nền là nơi lưu dữ liệu và ràng buộc. Nên dùng cả hai đúng chức năng.

### 34.2. Đừng tạo một view cho mọi câu SELECT nhỏ

Nếu mỗi API endpoint tạo thêm ba lớp view nhưng không tái sử dụng hay giữ contract rõ, số đối tượng tăng, dependencies chồng chéo và việc thay đổi schema khó hơn.

### 34.3. Không biến view thành nơi đặt mọi business logic

Những workflow cần trạng thái, nhiều bước ghi, gọi API ngoài, queue, idempotency, tranh chấp cập nhật và audit thường thuộc service/transaction/procedure phù hợp. Một view SELECT không giải quyết toàn bộ vòng đời nghiệp vụ.

---

## 35. Chuẩn đặt tên và quản lý vòng đời view

Một quy ước hữu ích:

```text
internal.orders
internal.customers

api.v_order_read_model
api.v_customer_overview_v1

reporting.v_daily_paid_order_value
reporting.mv_daily_paid_order_value
```

### 35.1. Tên mô tả ý nghĩa

Tên nên cho biết:

- Đối tượng chính: order, customer, invoice.
- Grain: một hàng/đơn, một hàng/khách, một hàng/ngày.
- Phạm vi: active, paid, historical.
- Đơn vị/thời điểm quan trọng: order value, captured payments, UTC day.
- Version contract khi có consumer ngoài team.

Tránh các tên quá chung như `v_data`, `v_final`, `v_temp2`.

### 35.2. Ghi chú bằng COMMENT ON VIEW

```sql
COMMENT ON VIEW view_contract_lab.v_daily_paid_orders
IS 'One row per tenant and UTC order day. Paid order count and sum of amount for orders whose current status is PAID; not a cash-flow metric.';
```

Đây là metadata hữu ích để người dùng hiểu ngữ nghĩa, đặc biệt với báo cáo tài chính.

### 35.3. Quyền sở hữu và thay đổi DDL

Nên có quy trình:

- Ai được CREATE/REPLACE/DROP?
- Ai là owner của view?
- Ai được GRANT SELECT?
- Ai xét security_invoker/security_barrier?
- Ai kiểm tra việc thay đổi tên/kiểu cột?
- Version nào có thể deprecated?
- Ai quản lý migration trong CI/CD?

### 35.4. Không tự tạo view bằng quyền superuser nếu không cần

Dùng role sở hữu chuyên dụng, nguyên tắc quyền tối thiểu và migration pipeline nhất quán. Việc owner có đặc quyền lớn có thể làm thay đổi semantics bảo mật.

---

## 36. Kiểm thử contract của view

Một view có thể vẫn tồn tại sau migration nhưng trả dữ liệu sai. Vì vậy cần nhiều lớp test.

### 36.1. Test cột, thứ tự và kiểu

Truy vấn metadata:

```sql
SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
  AND table_name = 'v_order_read_model'
ORDER BY ordinal_position;
```

Đối chiếu với schema DTO hoặc contract API mong đợi.

### 36.2. Test số hàng và JOIN

Với lab, mỗi order chỉ có một customer đúng tenant. Số hàng từ view read model nên bằng số hàng orders:

```sql
SELECT
    (SELECT COUNT(*)
     FROM view_contract_lab.orders) AS base_orders,
    (SELECT COUNT(*)
     FROM view_contract_lab.v_order_read_model) AS view_orders;
```

Nếu view trả nhiều hơn, có thể JOIN nhân hàng. Nếu ít hơn, có thể JOIN làm mất đơn khi dữ liệu liên quan không tồn tại hoặc bộ lọc cố ý loại bỏ.

### 36.3. Test tenant isolation về mặt ngữ nghĩa

```sql
SELECT
    tenant_id,
    COUNT(*) AS orders
FROM view_contract_lab.v_order_read_model
GROUP BY tenant_id
ORDER BY tenant_id;
```

Lab dự kiến 4 đơn tenant 10 và 3 đơn tenant 20. Đó là kiểm tra mô hình JOIN, **không phải security test** cho quyền tenant.

Security test phải chạy từ role có quyền bị giới hạn và xác nhận không thể truy cập tenant khác theo policy thực tế.

### 36.4. Test cột nhạy cảm không xuất hiện

Truy vấn `information_schema.columns` để xác nhận view công bố không có `email` hoặc `internal_note` nếu contract yêu cầu vậy.

### 36.5. Test ngữ nghĩa metric

Đối chiếu số liệu view `v_daily_paid_orders` với truy vấn trên bảng nền bằng tập dữ liệu đã biết. Kiểm tra trạng thái REFUNDED, CANCELED và PENDING.

### 36.6. Test EXPLAIN với dữ liệu đủ lớn

Dùng dữ liệu gần workload thật để xem planner có thể lọc tenant/time ở bảng nền không, index có phù hợp không và aggregation có tạo spill không. Trên lab bảy hàng, thời gian đo không đại diện production.

---

## 37. Những lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Thực tế |
| --- | --- |
| “CREATE VIEW lưu sẵn tất cả hàng.” | View thường lưu định nghĩa, không materialize kết quả |
| “View luôn nhanh hơn SELECT nền.” | Planner vẫn phải xử lý logic nền; không có cache tự động |
| “Có VIEW thì không cần index.” | Index thường nằm ở bảng nền |
| “CREATE INDEX trực tiếp trên normal view.” | Normal view không có heap kết quả để index như bảng |
| “View có ORDER BY thì mọi client tự được sắp đúng.” | Consumer nên ORDER BY theo contract |
| “LIMIT trong view chỉ tối ưu truy vấn.” | LIMIT có thể đổi tập dữ liệu mà view công bố |
| “SELECT * trong CREATE VIEW tự thêm mọi cột mới của bảng.” | Định nghĩa view không tự phát triển theo kiểu đó |
| “Đổi alias không ảnh hưởng client.” | Tên cột là contract |
| “Thay đổi kiểu cột trong CREATE OR REPLACE VIEW tùy ý.” | Bị ràng buộc bởi kiểu/tên/thứ tự cột cũ |
| “Bỏ một cột khỏi view là thay đổi không phá vỡ.” | Có thể phá DTO, BI report và view phụ thuộc |
| “DROP ... CASCADE chỉ xóa view mục tiêu.” | Có thể xóa nhiều đối tượng phụ thuộc |
| “View với JOIN tự cập nhật được.” | Nhiều JOIN views không automatically updatable |
| “View GROUP BY có thể UPDATE summary như bảng.” | Thường là giao diện đọc |
| “CHECK OPTION ngăn mọi DML không hợp lệ trên bảng.” | Chỉ bảo vệ DML qua view phù hợp |
| “LOCAL kiểm tra mọi lớp view bên dưới.” | LOCAL và CASCADED khác nhau |
| “View có WHERE tenant là đủ bảo mật.” | Cần auth, quyền, RLS, owner semantics |
| “GRANT SELECT view luôn cần GRANT SELECT bảng nền.” | Mặc định có thể dùng quyền view owner; invoker khác |
| “security_invoker và security_barrier là một.” | Một cái liên quan quyền, một cái liên quan predicate pushdown |
| “security_invoker luôn giúp role view-only hoạt động.” | Có thể cần quyền trên bảng nền và gặp permission denied |
| “View owner không ảnh hưởng RLS.” | Owner/BYPASSRLS/FORCE RLS có thể ảnh hưởng |
| “Đặt current_setting tenant là an toàn với mọi client.” | Context cần xuất phát từ tầng tin cậy và không bị giả mạo |
| “View không lộ email nên role không thể đọc email.” | Nếu role vẫn có quyền bảng nền, có thể đọc trực tiếp |
| “View đọc snapshot bất biến suốt thời gian mở ứng dụng.” | Mỗi truy vấn theo isolation/snapshot |
| “View trên read replica luôn là dữ liệu mới nhất.” | Replica có thể lag |
| “View có tham số như SQL function.” | View thường nhận filter từ WHERE của caller |
| “CTE và view có cùng lifecycle.” | CTE ở phạm vi statement, view ở schema |
| “Materialized view tự refresh sau mỗi UPDATE.” | Cần REFRESH theo cơ chế được thiết kế |
| “REFRESH CONCURRENTLY không cần unique index.” | Có các điều kiện unique index/populated view |
| “Một view có metric revenue là đủ để hiểu doanh thu.” | Phải ghi rõ trạng thái, thời điểm, đơn vị và refunds |
| “View nhiều bảng không bao giờ làm nhân số hàng.” | JOIN fan-out vẫn gây sai metrics |
| “Tất cả view phải được thiết kế ghi.” | Read-only contract thường an toàn/rõ ràng hơn |
| “Tạo hàng chục lớp view luôn là trừu tượng tốt.” | Có thể làm dependency, debugging, performance khó hơn |
| “Một SELECT view thành công bằng superuser chứng minh quyền đúng.” | Cần thử từ role thực |
| “Đổi schema mà view vẫn SELECT được nghĩa là contract không đổi.” | Semantics/NULL/timezone có thể đã thay |

---

## 38. Bài tập thực hành

### Bài 1 — Giải thích view

Hãy mô tả dữ liệu nào được lưu trong bảng `orders` và metadata nào được lưu cho `v_order_read_model`. Vì sao view thường không phải cache?

### Bài 2 — Tạo view đơn giản

Tạo view công bố `tenant_id`, `order_id`, `status` và `amount` từ orders. Chạy SELECT có bộ lọc tenant 10.

### Bài 3 — Join đúng tenant

Viết view JOIN orders và customers theo `(tenant_id,customer_id)`. Nếu chỉ JOIN customer_id, hàng nào của lab có nguy cơ gắn nhầm khách từ tenant khác?

### Bài 4 — Hợp đồng cột

Tạo view có alias `customer_name` và `gross_amount`. Vì sao đổi alias thành `name` và `amount` có thể làm hỏng consumer?

### Bài 5 — Che cột nội bộ

Tạo view đọc đơn nhưng không công bố `email` và `internal_note`. Giải thích tại sao cần thêm quản lý quyền trên bảng nền.

### Bài 6 — Cột dẫn xuất

Tạo view với `is_paid` và `lifecycle_group` bằng CASE. Nếu status chuyển từ PENDING sang PAID, dữ liệu qua view thay đổi khi nào?

### Bài 7 — View tổng hợp

Tạo view tính số đơn PAID theo tenant và ngày UTC. Nêu grain đầu ra và lý do không được gọi SUM(amount) trong view này là “net captured revenue” nếu chưa có bảng payment.

### Bài 8 — WHERE ngoài view

Truy vấn `v_order_read_model` theo tenant và khoảng thời gian. Dự đoán optimizer có thể áp dụng điều kiện ở bước nào, sau đó dùng EXPLAIN để quan sát.

### Bài 9 — ORDER BY và pagination

Viết query lấy 20 đơn mới nhất của tenant 10. Vì sao phải có ORDER BY ở consumer và thêm order_id làm tie-breaker?

### Bài 10 — LIMIT trong view

Một view lấy 10 đơn mới nhất **toàn hệ thống** rồi application lọc tenant 10. Vì sao kết quả khác với “10 đơn mới nhất của tenant 10”?

### Bài 11 — CREATE OR REPLACE VIEW

Sửa định nghĩa view, giữ nguyên các cột đã tồn tại và thêm một cột mới cuối danh sách. Những thay đổi nào không được phép theo quy tắc replace thông thường?

### Bài 12 — Đổi tên cột view

Dùng `ALTER VIEW ... RENAME COLUMN` trên view thử nghiệm. Những consumer nào có thể bị ảnh hưởng?

### Bài 13 — Versioning

Thiết kế `v_orders_v1` và `v_orders_v2` với tên cột mới. Mô tả các bước chuyển consumer mà không buộc tất cả deploy cùng một lúc.

### Bài 14 — Dependency

Giả sử view dùng cột `orders.status`. Điều gì có thể xảy ra khi chạy `ALTER TABLE orders DROP COLUMN status`? Vì sao `CASCADE` cần được xem rất cẩn thận?

### Bài 15 — pg_get_viewdef

Dùng `pg_get_viewdef` để xem SELECT của view, so với `CREATE VIEW` đã viết. Tại sao chuỗi in ra không nhất thiết giữ nguyên format?

### Bài 16 — information_schema

Liệt kê thứ tự, tên và kiểu cột của `v_order_read_model` từ `information_schema.columns`. Dùng kết quả làm một phần contract test.

### Bài 17 — pg_views

Liệt kê các view của schema lab và owner của chúng. Làm sao phát hiện một view được sở hữu bởi role không phù hợp?

### Bài 18 — EXPLAIN view có JOIN

Chạy `EXPLAIN (ANALYZE, BUFFERS)` trên query lọc tenant/status. Những bảng nền và node JOIN nào xuất hiện? Tại sao một lab bảy hàng có thể dùng Seq Scan?

### Bài 19 — Index ở bảng nền

Tạo index trên `orders(tenant_id,ordered_at)`, chạy EXPLAIN với query view. Vì sao không tạo index trực tiếp lên normal view?

### Bài 20 — View đơn giản có thể UPDATE

Tạo một view SELECT cột trực tiếp từ orders, chạy UPDATE trong transaction và ROLLBACK. Dữ liệu thay đổi ở đâu?

### Bài 21 — View JOIN có UPDATE được không?

Dùng `UPDATE` trên một view JOIN orders/customers không có INSTEAD OF trigger. Giải thích vì sao ánh xạ thao tác sang các bảng nền không hiển nhiên.

### Bài 22 — CHECK OPTION

Tạo view chỉ gồm đơn PAID của tenant 10 với CASCADED CHECK OPTION. Thử đổi status thành PENDING qua view. Vì sao câu UPDATE bị từ chối?

### Bài 23 — LOCAL và CASCADED

Tạo view tầng dưới lọc tenant và view tầng trên lọc status. Giải thích khác biệt khi dùng LOCAL/CASCADED CHECK OPTION. Vì sao chúng không thay quyền tenant?

### Bài 24 — INSTEAD OF trigger

Vẽ sơ đồ xử lý một UPDATE view JOIN muốn thay thông tin ở hai bảng nền. Những kiểm tra transaction/quyền/concurrency nào phải nằm trong trigger hoặc service?

### Bài 25 — GRANT SELECT trên view

Trong môi trường lab có quyền tạo role, cấp SELECT chỉ trên một view và USAGE trên schema. Vì sao role có thể đọc view mặc định nhưng không nhất thiết được SELECT các bảng nền?

### Bài 26 — SECURITY INVOKER

Tạo view `WITH (security_invoker=true)` trong PostgreSQL phiên bản hỗ trợ. Role có SELECT view nhưng thiếu SELECT base table sẽ gặp vấn đề gì?

### Bài 27 — SECURITY BARRIER

Giải thích vì sao một view lọc hàng nhạy cảm có thể dùng `security_barrier` và tại sao tùy chọn này có thể ảnh hưởng predicate pushdown. Nó có thay RLS không?

### Bài 28 — RLS và owner

Mô tả trường hợp view owner có quyền khác caller. Vì sao test bằng superuser không chứng minh caller thật sẽ chỉ thấy đúng tenant?

### Bài 29 — Session tenant context

Nếu RLS dựa vào `current_setting('app.tenant_id')` nhưng client tự SET được giá trị, rủi ro là gì? Nêu cách đảm bảo tenant context đáng tin trong kiến trúc.

### Bài 30 — View so với CTE

Một query chỉ dùng một lần cần chia thành hai bước logic. Vì sao CTE có thể đủ? Khi nào nên nâng phần logic tái sử dụng thành view có tên?

### Bài 31 — View so với SQL function

Thiết kế một hàm nhận tenant_id và khoảng ngày, trả danh sách đơn. Vì sao quyền EXECUTE function vẫn không thay kiểm tra authorization?

### Bài 32 — View so với materialized view

Tạo materialized view từ `v_daily_paid_orders`, thêm unique index và refresh. Khi một đơn chuyển trạng thái, kết quả của view thường và materialized view khác nhau thế nào trước khi refresh?

### Bài 33 — REFRESH CONCURRENTLY

Nêu điều kiện của unique index cho concurrent refresh trong PostgreSQL hiện đại. Vì sao concurrent refresh không đồng nghĩa dữ liệu luôn mới?

### Bài 34 — MVCC

Trong READ COMMITTED, hai SELECT cùng view ở hai thời điểm khác nhau có thể thấy số đơn khác nhau không? Khi nào REPEATABLE READ có ích cho nhiều báo cáo cần một snapshot?

### Bài 35 — JDBC mapping

Viết PreparedStatement SELECT từ view, map các cột theo tên vào DTO. Vì sao đổi alias gross_amount có thể làm mapper lỗi?

### Bài 36 — NULL và LEFT JOIN

Thiết kế view dùng LEFT JOIN để giữ các order chưa có dữ liệu liên quan. Test xem customer_name có thể NULL và COUNT(*) có bị hiểu sai không.

### Bài 37 — Semantic contract

Một view đổi từ “tổng giá trị đơn PAID” sang “tổng tiền đã thu trừ hoàn”, nhưng vẫn trả NUMERIC. Vì sao đây là breaking change ngay cả khi kiểu và tên cột không đổi?

### Bài 38 — Expand–migrate–contract

Lập kế hoạch chuyển từ cột tên khách cũ sang schema tên khách mới mà vẫn duy trì consumer sử dụng view v1; bao gồm backfill, view v2, quyền, kiểm thử và giai đoạn loại bỏ v1.

### Bài 39 — Lỗi JOIN fan-out

Một view báo cáo JOIN orders với nhiều order_items rồi SUM(o.amount). Vì sao kết quả có thể nhân đôi? Đề xuất pre-aggregate đúng grain.

### Bài 40 — Thiết kế view production

Một hệ thống đa tenant có hàng trăm triệu đơn, nhiều ứng dụng cần read model, dashboard mỗi ngày và một số role chỉ được xem dữ liệu không nhạy cảm. Thiết kế sơ đồ schema/view/materialized view, quyền/RLS, index, API versioning và bộ kiểm thử. Giải thích ranh giới chức năng từng thành phần.

---

## 39. Checklist thiết kế view làm giao diện dữ liệu

| Câu hỏi | Cách đánh giá |
| --- | --- |
| View phục vụ ai? | API, Java DTO, BI, export, nội bộ |
| Consumer cần grain nào? | Một hàng/order, customer hay day |
| Có tái sử dụng logic không? | JOIN/metric xuất hiện ở nhiều nơi |
| Danh sách cột công bố rõ không? | Không SELECT * tùy tiện |
| Tên/kiểu/thứ tự cột có là contract? | Metadata và contract tests |
| Cột nào nhạy cảm? | Chỉ công bố thứ cần thiết |
| JOIN có đủ khóa tenant không? | Không ghép sai khách giữa tenants |
| JOIN có làm nhân hàng không? | Kiểm tra cardinality/fan-out |
| Metric có định nghĩa rõ? | Trạng thái, ngày, amount, refunds |
| Có NULL/left join? | Consumer biết ý nghĩa NULL |
| Có timezone/đơn vị? | UTC/local day, currency, scale |
| View có được phép ghi không? | Phân biệt read-only và updatable |
| CHECK OPTION có cần không? | LOCAL/CASCADED khi DML qua view |
| View JOIN cần INSTEAD OF trigger? | Chỉ khi thực sự có contract ghi |
| Owner là role nào? | Quyền tối thiểu, không superuser tùy tiện |
| Caller có quyền bảng nền không? | GRANT/REVOKE kiểm tra |
| Có RLS? | Quyền owner/invoker, FORCE/BYPASSRLS |
| Có security_invoker? | PostgreSQL version và quyền nền |
| Có security_barrier? | Rủi ro leakproof/pushdown |
| Tenant context có đáng tin? | Identity server-side/DB policy |
| Có test với role thật? | Không chỉ chạy bằng superuser |
| CREATE OR REPLACE có đổi cột cũ không? | Hạn chế tên/kiểu/thứ tự |
| Có breaking semantic change? | Version mới/migration |
| Có view phụ thuộc? | Kiểm tra trước DROP/ALTER |
| Có cần ORDER BY trong caller? | Thứ tự deterministic |
| Có LIMIT trong view không? | Xác định ảnh hưởng semantics |
| Có index ở base tables? | EXPLAIN và selectivity |
| View có GROUP BY lớn? | Chi phí aggregate |
| Materialized view cần không? | Tần suất đọc, refresh latency |
| Có freshness contract? | MVCC, replica lag, REFRESH |
| Cần tham số? | View+WHERE hoặc SQL function |
| Có JDBC/ORM mapping? | DTO projection và read-only |
| Có quản lý migration CI/CD? | Versioning và rollback |
| Có COMMENT ON VIEW? | Tài liệu grain/metric |
| Có contract test? | Cột/kiểu, row count, permissions |
| Có benchmark? | Planning/Execution Time, Buffers |
| Có quá nhiều lớp view? | Complexity và plan readability |
| Có review quyền định kỳ? | Least privilege và data exposure |

## Kết luận

**View như giao diện truy vấn và mức trừu tượng dữ liệu** giúp PostgreSQL trở thành một lớp cung cấp dữ liệu ổn định cho ứng dụng, reporting và tích hợp giữa các hệ thống. Thay vì mỗi consumer hiểu toàn bộ bảng nền, một view có thể tập trung JOIN, đổi tên cột, biểu thức tính toán và một phần quy tắc công bố dữ liệu.

Những nguyên tắc cốt lõi:

1. **View thường lưu định nghĩa SELECT, không lưu sẵn kết quả.** Truy vấn view đọc dữ liệu nền theo snapshot và planner của PostgreSQL.
2. **View là hợp đồng dữ liệu.** Tên cột, kiểu, thứ tự, grain, timezone, NULL và ý nghĩa nghiệp vụ đều quan trọng.
3. **Trừu tượng hóa giúp giảm coupling nhưng không tự giữ đúng logic.** JOIN sai tenant hoặc SUM sau JOIN fan-out vẫn có thể sai dù được đóng gói trong view.
4. **CREATE OR REPLACE VIEW có giới hạn.** Không tùy tiện đổi tên/kiểu/thứ tự cột cũ; khi thay đổi lớn nên có migration/versioning.
5. **Không phải view nào cũng ghi được.** View đơn giản có thể automatically updatable; view JOIN/aggregate thường cần cách thiết kế khác. CHECK OPTION chỉ kiểm soát DML qua view phù hợp.
6. **Bảo mật phải thiết kế riêng.** Quyền view, owner, security_invoker, security_barrier và RLS có vai trò khác nhau; tạo view không tự là authorization.
7. **View không phải index hay cache.** Khi chậm cần EXPLAIN và index trên bảng nền; khi report đắt được gọi lặp lại có thể cân nhắc materialized view/summary với hợp đồng freshness.
8. **Phân biệt view, CTE và function.** View là đối tượng schema tái sử dụng, CTE trong phạm vi statement, function có tham số và quyền thực thi riêng.
9. **Kiểm thử cả cấu trúc lẫn ngữ nghĩa.** Dùng metadata, số hàng, EXPLAIN, role/tenant tests và đối chiếu metrics để phát hiện breaking changes.
10. **Quản lý vòng đời như API.** Đặt tên rõ, ghi COMMENT, giữ quyền tối thiểu, versioning khi cần, và dùng expand–migrate–contract để đổi schema an toàn.

Một view tốt không chỉ làm SQL ngắn hơn. Nó cho ứng dụng một **bề mặt dữ liệu rõ nghĩa, có thể kiểm thử, cấp quyền và thay đổi có kiểm soát**, trong khi PostgreSQL tiếp tục chịu trách nhiệm về tính đúng, tối ưu truy vấn và nhất quán giao dịch trên các bảng nền.
