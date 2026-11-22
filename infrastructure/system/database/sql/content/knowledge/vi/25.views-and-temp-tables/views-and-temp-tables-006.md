# Quyền truy cập qua view và ngữ cảnh thực thi

Trong **Database SQL**, `VIEW` không chỉ là cách đặt tên cho một câu `SELECT` dài. Ở nhiều hệ quản trị cơ sở dữ liệu (DBMS), view còn là **điểm truy cập có thể cấp quyền riêng**: ứng dụng hoặc người dùng được phép đọc kết quả của view nhưng không nhất thiết được phép đọc bảng gốc. Tuy nhiên, câu hỏi “ai có quyền gì?” không dừng ở `GRANT SELECT ON view`. Kết quả thực tế phụ thuộc vào **ngữ cảnh thực thi**, chủ sở hữu đối tượng, cơ chế *definer/invoker*, quyền trên schema, chính sách bảo mật theo hàng, các hàm được gọi và đặc điểm của từng DBMS.

Bài học thuộc chương **View và bảng trung gian**, tập trung vào **quyền truy cập qua view và ngữ cảnh thực thi**: hiểu mô hình phân quyền, viết kịch bản kiểm thử bằng PostgreSQL, nhận diện chỗ dễ nhầm khi chuyển sang MySQL/MariaDB, SQL Server, Oracle và SQLite, đồng thời phân biệt view thông thường với bảng tạm và materialized view.

> **Giới hạn:** Các ví dụ tạo role, schema, table, view và cấp quyền chỉ nên chạy trong **cơ sở dữ liệu học tập do bạn quản lý**. Không dùng tài khoản quản trị quyền cao cho kết nối ứng dụng thật; không chạy lệnh thu hồi quyền trên bảng sản xuất nếu chưa kiểm tra các phụ thuộc.

## 1. Vì sao cần phân quyền thông qua view?

Giả sử có bảng `orders` chứa:

| order_id | region | customer_name | customer_email | amount | status |
| ---: | --- | --- | --- | ---: | --- |
| 1 | Bắc | An | an@example.invalid | 120.00 | PAID |
| 2 | Bắc | Bình | binh@example.invalid | 80.00 | PAID |
| 3 | Bắc | Chi | chi@example.invalid | 60.00 | CANCELLED |
| 4 | Nam | Dũng | dung@example.invalid | 200.00 | PAID |

Nhân viên báo cáo chỉ cần xem **doanh thu đơn đã thanh toán theo khu vực**, không cần tên hay email khách hàng. Nếu cấp:

```sql
-- Chỉ minh họa về ý tưởng; cú pháp và quyền cấp phụ thuộc DBMS.
GRANT SELECT ON orders TO report_reader;
```

thì role báo cáo có thể đọc cả các cột thông tin cá nhân, trừ khi có cơ chế hạn chế khác.

Thay vào đó, tạo view:

```sql
CREATE VIEW v_paid_revenue AS
SELECT
    region,
    COUNT(*) AS paid_orders,
    SUM(amount) AS paid_amount
FROM orders
WHERE status = 'PAID'
GROUP BY region;
```

và chỉ cho phép người đọc xem `v_paid_revenue`.

Khi đó ứng dụng nhìn thấy dữ liệu có hình dạng:

| region | paid_orders | paid_amount |
| --- | ---: | ---: |
| Bắc | 2 | 200.00 |
| Nam | 1 | 200.00 |

View cung cấp **giao diện dữ liệu hẹp hơn bảng nguồn**:

- **Hạn chế cột:** không trả `customer_name` và `customer_email`.
- **Hạn chế hàng:** chỉ dùng đơn có `status = 'PAID'`.
- **Hạn chế độ chi tiết:** tổng hợp thành chỉ tiêu theo khu vực, không trả từng đơn.
- **Ổn định giao diện:** ứng dụng truy vấn tên view thay vì phụ thuộc trực tiếp vào mọi cột của bảng gốc.

Tuy nhiên, view **không tự bảo đảm bí mật** nếu người dùng vẫn có quyền truy vấn bảng gốc, có đường truy cập khác tới dữ liệu, hoặc ngữ cảnh thực thi được cấu hình không đúng.

## 2. Phân biệt ba lớp quyền

Khi người dùng chạy:

```sql
SELECT region, paid_amount
FROM reporting.v_paid_revenue;
```

cần xem xét ít nhất ba lớp.

| Lớp | Câu hỏi kiểm tra | Ví dụ |
| --- | --- | --- |
| Kết nối và schema | Người dùng có thể kết nối database, tham chiếu schema chứa view không? | `CONNECT`, `USAGE ON SCHEMA` trong PostgreSQL |
| Đối tượng view | Người dùng có quyền thực hiện thao tác trên view không? | `GRANT SELECT ON reporting.v_paid_revenue` |
| Đối tượng bên dưới | DBMS kiểm tra quyền đọc bảng nguồn dưới danh tính ai? | Chủ view, người gọi, hoặc chuỗi sở hữu tùy DBMS và cấu hình |

Dưới góc độ bảo mật, câu hỏi cốt lõi là:

**Khi `report_reader` chạy `SELECT` trên view, DBMS dùng quyền của `report_reader` hay quyền của chủ sở hữu/definer của view để truy cập bảng nguồn?**

Không có một câu trả lời đúng cho **mọi** DBMS và **mọi** cấu hình.

### Mô hình ý niệm

```text
Người dùng / ứng dụng: report_reader
              |
              | quyền nhìn thấy schema + SELECT trên view
              v
        reporting.v_paid_revenue
              |
              | DBMS xác định ngữ cảnh kiểm tra
              | quyền trên quan hệ bên dưới
              v
        private_data.orders
              |
              v
        Các dòng/cột kết quả view
```

Một mô hình phổ biến là **người đọc có quyền SELECT view nhưng không có quyền SELECT bảng gốc**. Mô hình đó chỉ hoạt động khi DBMS cho phép view đọc bảng gốc bằng quyền của chủ view/definer hoặc thông qua cơ chế tương đương.

## 3. Từ vựng nền tảng: principal, role, owner, grant

**Principal** là danh tính được hệ thống phân quyền nhận diện: user, login, role hoặc danh tính liên quan, tùy DBMS.

**Role** là tập quyền có thể được cấp cho người dùng hoặc role khác. Thông thường nên cấp quyền cho **role ứng dụng**, không phân tán quyền trực tiếp cho hàng trăm tài khoản cá nhân.

**Owner / chủ sở hữu** là principal sở hữu đối tượng. Owner thường có quyền quản lý đặc biệt đối với đối tượng do mình sở hữu.

**GRANT** cấp quyền; **REVOKE** thu hồi quyền đã cấp. Nhưng thu hồi một đường cấp **không nhất thiết thu hồi được mọi quyền hiệu lực**, vì tài khoản có thể nhận cùng quyền qua role khác, qua `PUBLIC` hoặc qua vai trò quản trị.

**PUBLIC** thường chỉ tập hợp mọi user/role theo cơ chế của DBMS; không phải role báo cáo riêng. Một quyền cấp cho PUBLIC có thể khiến việc chỉ `REVOKE` từ một role cụ thể trở nên không đủ.

**Definer** là danh tính mà quyền hoặc ngữ cảnh của nó được áp dụng khi thực thi đối tượng theo cơ chế *definer*. **Invoker** là người/role gọi đối tượng theo cơ chế *invoker*. Hai khái niệm thường được nhắc ở view, procedure và function, nhưng **mức độ áp dụng khác nhau theo loại đối tượng và DBMS**.

Một ví dụ chính sách tối thiểu:

| Principal | View báo cáo | Bảng dữ liệu riêng | Quyền tạo/sửa cấu trúc |
| --- | --- | --- | --- |
| `report_reader` | `SELECT` | Không có `SELECT` trực tiếp | Không |
| `report_view_owner` | Sở hữu view | Có đủ quyền cần thiết để tạo/thực thi view | Chỉ trên schema được giao |
| Quản trị viên | Theo nhiệm vụ quản trị | Theo nhiệm vụ quản trị | Theo nhiệm vụ quản trị |

Đây là mục tiêu thiết kế, **không phải kết quả mặc định** của lệnh `CREATE VIEW` trên mọi hệ thống.

## 4. View thường khác bảng trung gian thế nào về bảo mật?

| Đối tượng | Dữ liệu nằm ở đâu? | Có thể cấp quyền riêng? | Điểm cần kiểm tra |
| --- | --- | --- | --- |
| **View thông thường** | Thường lưu định nghĩa truy vấn, không tạo bản sao dữ liệu riêng của kết quả | Có trên nhiều DBMS | Quyền của người gọi, chủ view và các đối tượng nguồn |
| **Materialized view** | Lưu **kết quả đã vật chất hóa** tại thời điểm refresh | Thường có quyền đọc riêng tùy DBMS | Ai được đọc bản sao, ai refresh, dữ liệu có cũ hoặc nhạy cảm không |
| **Bảng staging/trung gian thường** | Dữ liệu được ghi vào bảng vật lý | Có | Quyền trên bảng staging, vòng đời, dữ liệu sao chép |
| **Temporary table** | Bảng/dữ liệu tạm theo session hoặc phạm vi khác tùy DBMS | Cơ chế riêng, thường gắn với session | Quyền tạo bảng, quyền đọc nguồn khi tạo, thời gian tồn tại |
| **CTE / derived table** | Phạm vi trong câu SQL; engine có thể xử lý trung gian | Không phải một đối tượng độc lập để `GRANT SELECT` | Quyền của câu truy vấn và các bảng/hàm được tham chiếu |

Ví dụ:

```sql
WITH paid AS (
    SELECT region, amount
    FROM orders
    WHERE status = 'PAID'
)
SELECT region, SUM(amount)
FROM paid
GROUP BY region;
```

CTE `paid` chỉ thuộc truy vấn đó. Không thể coi `paid` là một view độc lập để cấp cho role khác trong database.

Nếu tạo:

```sql
-- Minh họa ý tưởng; cú pháp CREATE TEMP TABLE khác nhau theo DBMS.
CREATE TEMP TABLE paid_snapshot AS
SELECT region, amount
FROM orders
WHERE status = 'PAID';
```

thì **người thực thi** phải đủ quyền đọc dữ liệu nguồn lúc tạo bảng, nhưng sau đó truy vấn `paid_snapshot` đọc bản sao, không tự “chạy lại” quyền truy cập bảng `orders` mỗi lần. Bản sao có thể tồn tại sau khi quyền nguồn bị thay đổi cho tới khi kết thúc vòng đời bảng tạm. Do đó **sao chép dữ liệu không đồng nghĩa với quản lý quyền tập trung qua view**.

## 5. Thực hành PostgreSQL: chuẩn bị hai role và hai schema

Phần này dùng **PostgreSQL**. Kịch bản phải chạy bằng tài khoản quản trị của database học tập có quyền `CREATE ROLE`, `CREATE SCHEMA` và được phép `SET ROLE` tới các role tạo ra. Không thực hiện trên database sản xuất.

Ta tạo:

- `sql316_owner`: role **không đăng nhập**, sở hữu bảng và view mẫu.
- `sql316_reader`: role **không đăng nhập**, chỉ được xem view công khai.
- `sql316_private`: schema chứa bảng nguồn nhạy cảm.
- `sql316_api`: schema chứa view dành cho báo cáo.

Việc dùng role `NOLOGIN` giúp mô phỏng chức năng bằng `SET ROLE` trong một session quản trị; ứng dụng thật thường dùng một login role được cấp membership hoặc các quyền thích hợp, không dùng chung tài khoản sở hữu bảng.

### 5.1. Tạo role và schema

```sql
-- PostgreSQL; chạy một lần trong database học tập,
-- bằng tài khoản có đủ quyền quản trị.

CREATE ROLE sql316_owner NOLOGIN;
CREATE ROLE sql316_reader NOLOGIN;

CREATE SCHEMA sql316_private AUTHORIZATION sql316_owner;
CREATE SCHEMA sql316_api AUTHORIZATION sql316_owner;
```

Nếu các role/schema đã tồn tại từ lần chạy trước, lệnh tạo có thể báo lỗi. Hãy hoàn tất bài thực hành hoặc dọn đúng những đối tượng thử nghiệm đó trước khi chạy lại; không xóa đối tượng chỉ vì trùng tên mà chưa xác nhận chủ sở hữu.

### 5.2. Chuyển sang role sở hữu đối tượng và tạo bảng

```sql
SET ROLE sql316_owner;

CREATE TABLE sql316_private.orders (
    order_id INTEGER PRIMARY KEY,
    sold_on DATE NOT NULL,
    region TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED'))
);

INSERT INTO sql316_private.orders
    (order_id, sold_on, region, customer_name, customer_email,
     amount, status)
VALUES
    (1, DATE '2026-01-03', 'Bắc',   'An',   'an@example.invalid',
     120.00, 'PAID'),
    (2, DATE '2026-01-04', 'Bắc',   'Bình', 'binh@example.invalid',
      80.00, 'PAID'),
    (3, DATE '2026-01-05', 'Bắc',   'Chi',  'chi@example.invalid',
      60.00, 'CANCELLED'),
    (4, DATE '2026-01-07', 'Nam',   'Dũng', 'dung@example.invalid',
     200.00, 'PAID'),
    (5, DATE '2026-01-08', 'Nam',   'Hà',   'ha@example.invalid',
     100.00, 'PAID'),
    (6, DATE '2026-01-09', 'Trung', 'Lan',  'lan@example.invalid',
      70.00, 'PENDING');
```

Các địa chỉ `example.invalid` là dữ liệu giả để học, không phải email thực.

### 5.3. Tạo hai view cho hai mức độ chi tiết

**View A:** danh sách đơn PAID nhưng **không lộ tên/email**.

```sql
CREATE VIEW sql316_api.v_paid_orders
WITH (security_barrier = true)
AS
SELECT
    order_id,
    sold_on,
    region,
    amount
FROM sql316_private.orders
WHERE status = 'PAID';
```

**View B:** tổng hợp doanh thu PAID theo khu vực.

```sql
CREATE VIEW sql316_api.v_paid_by_region
WITH (security_barrier = true)
AS
SELECT
    region,
    COUNT(*) AS paid_orders,
    SUM(amount) AS paid_amount
FROM sql316_private.orders
WHERE status = 'PAID'
GROUP BY region;
```

Tùy DBMS, tùy chọn `security_barrier` không tồn tại hoặc có cú pháp khác. Ở PostgreSQL, đây là thuộc tính riêng được giới thiệu kỹ hơn trong mục 10. **Nó không phải công tắc tự động thay thế mọi thiết kế phân quyền.**

Kết quả mong đợi của `v_paid_by_region`:

| region | paid_orders | paid_amount |
| --- | ---: | ---: |
| Bắc | 2 | 200.00 |
| Nam | 2 | 300.00 |

Không có hàng Trung vì bảng nguồn chỉ có giao dịch PENDING ở Trung.

## 6. Cấp quyền chỉ trên lớp view

Vẫn đang ở `SET ROLE sql316_owner`, thực hiện:

```sql
-- Thu hồi các quyền có thể đã cấp cho PUBLIC trên đối tượng mẫu.
-- Bước này mang tính minh họa chủ động phòng vệ;
-- PostgreSQL thường không tự cấp SELECT bảng mới cho PUBLIC.
REVOKE ALL ON SCHEMA sql316_private FROM PUBLIC;
REVOKE ALL ON TABLE sql316_private.orders FROM PUBLIC;
REVOKE ALL ON TABLE sql316_api.v_paid_orders,
                    sql316_api.v_paid_by_region
FROM PUBLIC;

-- Cho phép role người đọc tham chiếu schema chứa view.
GRANT USAGE ON SCHEMA sql316_api TO sql316_reader;

-- Cho phép SELECT hai view.
GRANT SELECT ON sql316_api.v_paid_orders,
                sql316_api.v_paid_by_region
TO sql316_reader;

-- Không GRANT USAGE trên sql316_private.
-- Không GRANT SELECT trên sql316_private.orders.

RESET ROLE;
```

Đường đi quyền mong muốn:

```text
sql316_reader
   |
   +-- USAGE --> sql316_api
   |                  |
   +-- SELECT --------+--> v_paid_orders
   |                  +--> v_paid_by_region
   |
   X-- USAGE --> sql316_private
   X-- SELECT --> sql316_private.orders

sql316_owner: sở hữu các view và bảng nguồn.
PostgreSQL mặc định kiểm tra quyền đọc quan hệ nguồn
theo chủ view khi view không đặt security_invoker=true.
```

Một **role không có quyền đọc bảng gốc** vẫn có thể truy vấn view vì PostgreSQL mặc định kiểm tra quyền đối với các **quan hệ nền** bằng quyền của chủ view. Đây là điểm quan trọng nhất của ví dụ.

Đừng suy diễn từ đó rằng bất cứ hàm nào được gọi trong view cũng đều tự động “chạy như chủ view”; quyền hàm và `SECURITY DEFINER` của function là câu chuyện riêng (mục 12).

## 7. Kiểm thử đúng quyền bằng SET ROLE

Sử dụng lại session quản trị đủ quyền `SET ROLE`, chạy:

```sql
SET ROLE sql316_reader;

SELECT order_id, sold_on, region, amount
FROM sql316_api.v_paid_orders
ORDER BY order_id;
```

Kết quả có bốn đơn PAID: order 1, 2, 4, 5. Không có `customer_name`, `customer_email` hay `status` trong danh sách cột view.

```sql
SELECT region, paid_orders, paid_amount
FROM sql316_api.v_paid_by_region
ORDER BY region;
```

Kết quả là Bắc: 2 đơn, 200; Nam: 2 đơn, 300.

**Cố ý kiểm thử truy cập trái phép bằng lệnh riêng:**

```sql
-- Dự kiến: lỗi permission denied
-- (có thể ở schema hoặc table tùy điểm kiểm tra).
SELECT *
FROM sql316_private.orders;
```

Kết quả mong đợi là **lỗi quyền truy cập**, không phải bảng hiển thị dữ liệu cá nhân. Không chạy phép thử lỗi này ở giữa một transaction dài trong client có cơ chế dừng transaction sau lỗi; hãy thực hiện trong một câu riêng hoặc reset transaction đúng cách.

Có thể thử thêm:

```sql
-- Dự kiến không thể truy vấn cột không được công bố qua view.
SELECT customer_email
FROM sql316_api.v_paid_orders;
```

Kết quả là lỗi vì view không có cột `customer_email`. Đây là **lỗi cột không tồn tại trong giao diện view**, khác về bản chất với lỗi quyền khi truy cập bảng gốc.

Trả lại vai trò session sau khi thử:

```sql
RESET ROLE;
```

### Kiểm thử quyền hiệu lực bằng hàm PostgreSQL

Tài khoản quản trị có thể hỏi quyền hiệu lực của `sql316_reader`:

```sql
SELECT
    has_schema_privilege(
        'sql316_reader', 'sql316_api', 'USAGE'
    ) AS can_use_api_schema,
    has_table_privilege(
        'sql316_reader', 'sql316_api.v_paid_orders', 'SELECT'
    ) AS can_select_view,
    has_table_privilege(
        'sql316_reader', 'sql316_private.orders', 'SELECT'
    ) AS can_select_base_table;
```

Mong đợi:

| can_use_api_schema | can_select_view | can_select_base_table |
| --- | --- | --- |
| true | true | false |

Các hàm kiểm tra **quyền hiện có của role**, nhưng vẫn cần thử truy vấn thực tế để phát hiện thiếu quyền khác, chính sách RLS, hàm phụ trợ hoặc vấn đề ngữ cảnh trong view phức tạp.

## 8. Schema USAGE không giống table SELECT

Trong PostgreSQL, để gọi:

```sql
SELECT * FROM sql316_api.v_paid_orders;
```

role cần có **`USAGE` trên schema `sql316_api`** và **`SELECT` trên view** (ngoài khả năng kết nối database).

Ví dụ nếu chỉ:

```sql
GRANT SELECT ON sql316_api.v_paid_orders TO sql316_reader;
```

mà quên `GRANT USAGE ON SCHEMA sql316_api`, truy vấn qua tên đầy đủ vẫn có thể bị từ chối vì không có quyền tham chiếu schema.

Trong mô hình view quyền chủ sở hữu mặc định, role đọc view **không cần được cấp quyền trực tiếp vào schema chứa bảng gốc** chỉ để đọc qua view. Đó là lý do `sql316_private` và `sql316_api` được tách riêng.

**Đừng cấp `USAGE` hoặc `SELECT` “cho chắc” vào toàn bộ schema riêng.** Làm như vậy có thể phá mục đích giảm quyền của lớp API.

### Không quên quyền qua membership và PUBLIC

Nếu `sql316_reader` là thành viên của role khác có quyền trên bảng gốc, hoặc có quyền gián tiếp khác, lệnh:

```sql
REVOKE SELECT ON sql316_private.orders FROM sql316_reader;
```

không nhất thiết đủ để chặn truy cập. Cần xem **quyền hiệu lực** qua các đường cấp, role membership, PUBLIC và quyền quản trị, thay vì chỉ tìm một câu `GRANT` trực tiếp.

## 9. Ngữ cảnh thực thi: ai đăng nhập, ai đang thực thi?

Trong PostgreSQL, hai biểu thức rất hữu ích:

```sql
SELECT session_user, current_user;
```

- `session_user`: danh tính session gốc, thường là role đăng nhập.
- `current_user`: role hiện đang áp dụng để kiểm tra phần lớn quyền trong ngữ cảnh SQL thông thường; có thể đổi bởi `SET ROLE` hoặc trong ngữ cảnh chạy function đặc biệt.

Thử:

```sql
SELECT session_user, current_user;

SET ROLE sql316_reader;

SELECT session_user, current_user;

RESET ROLE;

SELECT session_user, current_user;
```

Khi `SET ROLE sql316_reader`, `current_user` thường trở thành `sql316_reader`, còn `session_user` giữ nguyên role của phiên ban đầu.

**Điểm dễ nhầm:** PostgreSQL có thể kiểm tra quyền truy cập quan hệ nguồn của view bằng **chủ view**, trong khi `current_user` của một biểu thức SQL thông thường không nhất thiết đổi thành chủ view. Đừng dùng việc in `current_user` làm bằng chứng duy nhất về cơ chế quyền của view; cần phân biệt **danh tính session** và **danh tính được dùng cho từng phép kiểm tra quyền**.

Ví dụ, nếu một view gọi function có kiểm tra quyền riêng, hoặc function `SECURITY DEFINER`, thì phải xét thêm cơ chế bảo mật của function đó.

## 10. PostgreSQL: mặc định theo chủ view và tùy chọn security_invoker

Ở PostgreSQL, view thông thường có hai tình huống quan trọng.

### 10.1. Cơ chế mặc định

Với view thông thường **không bật** `security_invoker`:

- Người gọi cần quyền `SELECT` đối với view.
- Quyền truy cập **bảng/quan hệ nguồn** thường được kiểm tra theo **chủ sở hữu view**.
- Vì vậy người gọi không nhất thiết cần `SELECT` trực tiếp trên bảng nguồn.

Bài thực hành `sql316_api.v_paid_orders` hoạt động theo mô hình này.

Mô hình rất hữu ích để công bố các cột đã chọn và dữ liệu đã lọc cho role báo cáo **không được đọc bảng gốc**.

### 10.2. security_invoker = true (PostgreSQL 15+)

PostgreSQL 15 trở lên hỗ trợ tùy chọn:

```sql
-- Chỉ chạy trên PostgreSQL 15+.
SET ROLE sql316_owner;

CREATE VIEW sql316_api.v_paid_orders_invoker
WITH (security_invoker = true)
AS
SELECT order_id, sold_on, region, amount
FROM sql316_private.orders
WHERE status = 'PAID';

GRANT SELECT ON sql316_api.v_paid_orders_invoker
TO sql316_reader;

RESET ROLE;
```

Sau đó thử bằng role đọc:

```sql
SET ROLE sql316_reader;

-- Dự kiến bị từ chối vì role không có quyền
-- cần thiết trên bảng nguồn.
SELECT *
FROM sql316_api.v_paid_orders_invoker;

RESET ROLE;
```

`security_invoker = true` yêu cầu kiểm tra quyền đối với quan hệ nền bằng quyền của **người gọi view**, thay vì chỉ dựa trên quyền chủ view. Vì `sql316_reader` không có `SELECT` trên `sql316_private.orders`, câu truy vấn bị từ chối.

**Không nhầm mục đích:** `security_invoker = true` **không** phải lựa chọn tốt nếu mục tiêu duy nhất là “reader không có quyền trên bảng gốc nhưng vẫn đọc được view”. Nó phục vụ tình huống muốn quyền và chính sách ở bảng nguồn đi theo **invoker**.

Nếu cấp quyền đọc bảng nguồn cho reader để security-invoker view chạy được, phải thiết kế thêm hạn chế phù hợp ở nguồn; không thể mặc định rằng reader chỉ đọc được phần dữ liệu mà view lọc.

### 10.3. So sánh ngắn

| Vấn đề | View mặc định | `security_invoker = true` |
| --- | --- | --- |
| Ai cần SELECT trên view? | Người gọi | Người gọi |
| Ai được kiểm tra quyền bảng nguồn? | Thông thường là chủ view | Người gọi |
| Reader không có SELECT bảng nguồn có truy vấn view được? | Có thể, nếu chủ view có quyền thích hợp | Thông thường không |
| Chính sách RLS bảng nguồn theo ai? | Thường theo ngữ cảnh chủ view | Theo ngữ cảnh người gọi |
| Phù hợp công bố báo cáo hạn quyền bảng nguồn? | Thường có | Chỉ nếu thiết kế nguồn cho phép |

**Chú ý phiên bản:** SQL có `security_invoker` không chạy trên những phiên bản PostgreSQL cũ hơn 15. Không coi thuộc tính này là cú pháp SQL chung của MySQL hay SQL Server.

## 11. security_barrier: rào cản tối ưu hóa, không phải quyền SELECT

Khi view có điều kiện bảo mật, chẳng hạn:

```sql
CREATE VIEW sql316_api.v_paid_orders
WITH (security_barrier = true)
AS
SELECT order_id, sold_on, region, amount
FROM sql316_private.orders
WHERE status = 'PAID';
```

PostgreSQL có thể tối ưu hóa truy vấn bằng cách **đưa điều kiện từ truy vấn bên ngoài vào bên trong view**. Trong những tình huống nhất định, một biểu thức hoặc function do người gọi đưa vào có thể phát sinh lỗi/thông tin phụ dựa trên dữ liệu mà điều kiện view dự định che đi.

Thuộc tính `security_barrier = true` hạn chế một số phép đẩy điều kiện qua ranh giới view, nhằm hỗ trợ view lọc hàng như một **ranh giới bảo mật** trước các biểu thức có khả năng rò rỉ (*leaky expressions*). PostgreSQL có các quy tắc riêng đối với hàm/toán tử được đánh dấu `LEAKPROOF`.

Phân biệt:

| Thuộc tính | Giải quyết câu hỏi |
| --- | --- |
| `GRANT SELECT` | Người gọi có được đọc view không? |
| `security_invoker` | Quyền trên quan hệ nền và RLS dùng ngữ cảnh chủ view hay người gọi? |
| `security_barrier` | Optimizer có được phép tái sắp xếp một số điều kiện có nguy cơ tiết lộ dữ liệu qua biên view không? |

Hai thuộc tính `security_invoker` và `security_barrier` **độc lập về ý nghĩa**. Bật cái này không tự bật cái kia.

**Giới hạn:** `security_barrier` không mã hóa dữ liệu, không thay thế phân quyền, không ngăn mọi kiểu suy luận từ kết quả hợp lệ và có thể ảnh hưởng cơ hội tối ưu hóa. Khi cần bảo vệ tenant hoặc hàng nhạy cảm, hãy kết hợp thiết kế quyền, row-level security khi phù hợp, kiểm thử và đánh giá rò rỉ thông tin.

## 12. Function trong view: SECURITY DEFINER là cơ chế khác

Trong PostgreSQL, function mặc định chạy theo cơ chế **`SECURITY INVOKER`**. Function có thể được khai báo **`SECURITY DEFINER`** để thực thi bằng quyền chủ function.

Điều này **khác** cơ chế view mặc định kiểm tra quyền quan hệ nguồn theo chủ view.

Một view gọi function có thể phát sinh thêm các câu hỏi:

- Caller có quyền `EXECUTE` function không?
- Function được tạo theo `SECURITY INVOKER` hay `SECURITY DEFINER`?
- Function có đọc thêm bảng nào mà view không biểu lộ trong `FROM` không?
- Function có dùng SQL động, tên đối tượng không đủ schema hoặc dữ liệu từ người dùng không?
- Ngữ cảnh `search_path` có cho phép tên object bị điều khiển/bóng tên không?

### 12.1. Function đọc doanh thu với quyền của chủ function

Ví dụ PostgreSQL, sau khi tạo role và bảng như trên:

```sql
BEGIN;

SET ROLE sql316_owner;

CREATE FUNCTION sql316_api.paid_total_for_region(p_region TEXT)
RETURNS NUMERIC
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sql316_private, pg_temp
AS $$
    SELECT COALESCE(SUM(amount), 0)
    FROM sql316_private.orders
    WHERE status = 'PAID'
      AND region = p_region;
$$;

-- PostgreSQL thường cho PUBLIC EXECUTE function mới theo mặc định.
-- Thu hồi và cấp lại trong cùng transaction để tránh cửa sổ hở quyền.
REVOKE ALL ON FUNCTION sql316_api.paid_total_for_region(TEXT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sql316_api.paid_total_for_region(TEXT)
TO sql316_reader;

RESET ROLE;

COMMIT;
```

Kiểm thử:

```sql
SET ROLE sql316_reader;

SELECT sql316_api.paid_total_for_region('Bắc')
    AS north_paid_total;

RESET ROLE;
```

Kết quả mong đợi: **200.00**.

Giải thích:

- Reader có `USAGE` trên schema API và được `EXECUTE` function.
- Function chạy với quyền của `sql316_owner`, là chủ bảng nguồn.
- Reader vẫn không có `SELECT` trực tiếp trên `sql316_private.orders`.
- Function chỉ trả giá trị đã thiết kế.

### 12.2. Rủi ro của SECURITY DEFINER

**SECURITY DEFINER là cơ chế có đặc quyền, không nên áp dụng bừa.** Nếu function tạo SQL động từ chuỗi do caller cung cấp, tham chiếu tên bảng/hàm không đủ schema trong `search_path` không an toàn hoặc không kiểm soát đầu vào, caller có thể tận dụng quyền của chủ function để truy cập ngoài ý muốn.

Các nguyên tắc:

1. Chủ function chỉ nên có **quyền tối thiểu** cần để hoàn thành nhiệm vụ.
2. Giữ `search_path` kiểm soát và không để schema mà caller ghi được nằm trước schema tin cậy; ví dụ đặt `pg_temp` cuối và nêu rõ tên bảng bằng schema.
3. Dùng tham số kiểu dữ liệu đúng, không nối thẳng dữ liệu chưa kiểm soát vào SQL động.
4. Thu hồi `EXECUTE` khỏi `PUBLIC` và chỉ cấp role cần dùng, lý tưởng trong cùng transaction với `CREATE FUNCTION`.
5. Xác thực **phạm vi nghiệp vụ**: function trên cho caller tùy ý truyền `'Bắc'` hay `'Nam'`. Nếu chỉ được thấy doanh thu khu vực của chính mình, phải thêm quy tắc xác thực quyền, không tin vào tham số `p_region` do caller tự chọn.
6. Kiểm thử với role ít quyền, không chỉ kiểm thử bằng superuser.

**Không cần biến tất cả view thành function SECURITY DEFINER.** Nếu view trực tiếp đã đáp ứng API đọc an toàn, việc bổ sung function đặc quyền có thể chỉ tăng bề mặt rủi ro.

## 13. Row-Level Security (RLS) và chủ sở hữu view

RLS (*Row-Level Security*) dùng chính sách tại bảng nguồn để quy định **hàng nào một role được phép thấy hoặc sửa**, tùy thao tác. Trong hệ đa khách hàng (*multi-tenant*), RLS có thể là lớp phòng vệ quan trọng.

Ở PostgreSQL, các điểm đặc biệt cần ghi nhớ:

1. View mặc định thường kiểm tra quyền quan hệ nguồn theo **chủ view**; các chính sách RLS liên quan cũng thường được áp dụng trong ngữ cảnh đó.
2. View `security_invoker = true` khiến quyền và chính sách RLS ở bảng nguồn được kiểm tra theo **người gọi**.
3. **Chủ bảng** thường có thể **bỏ qua RLS** trên bảng mình sở hữu, trừ các trường hợp cấu hình như `FORCE ROW LEVEL SECURITY`; superuser và role có quyền `BYPASSRLS` có cơ chế ngoại lệ riêng.
4. Vì vậy nếu chủ view **đồng thời là chủ bảng** và view dùng cơ chế mặc định, **không được tự giả định RLS của từng người gọi sẽ bảo vệ dữ liệu như khi họ SELECT trực tiếp**.
5. Bảo mật tenant cần được thiết kế/kiểm thử tổng thể: chủ sở hữu, chính sách RLS, cách xác định tenant, quyền trực tiếp, function đặc quyền và view.

### Ví dụ suy nghĩ đúng về RLS

Nếu user A chỉ được xem đơn hàng tenant A và user B chỉ được xem tenant B, đừng viết một view mặc định thuộc owner có thể đọc mọi tenant rồi nghĩ rằng policy RLS của từng caller tự động chặn dữ liệu.

Thay vào đó, hãy quyết định rõ:

- Dùng **RLS ở bảng nguồn theo danh tính caller** và view phù hợp với `security_invoker` (người gọi cần các quyền nguồn tương ứng), **hoặc**
- Dùng **view theo chủ sở hữu** có điều kiện lọc được bảo vệ chặt chẽ, không lấy tiêu chí bảo mật từ giá trị mà caller tự giả mạo, **hoặc**
- Dùng một API function/procedure kiểm tra tenant và vai trò với cơ chế đáng tin, kèm quyền tối thiểu.

**Cẩn thận với biến session do client tự đặt** như “tenant_id hiện tại”: nếu client có thể thay đổi giá trị tùy ý mà database vẫn tin đó là danh tính được xác thực, chỉ thêm điều kiện `WHERE tenant_id = current_setting(...)` có thể không đủ để cách ly tenant.

Bài thực hành ở mục 5–7 **chưa bật RLS** để tập trung vào quyền qua view. Không được lấy kết quả bài lab đó làm minh chứng rằng một hệ thống nhiều tenant đã được bảo vệ.

## 14. Lọc hàng và ẩn cột không phải lúc nào cũng đủ

View:

```sql
CREATE VIEW v_public_orders AS
SELECT order_id, region, amount
FROM orders
WHERE status = 'PAID';
```

có thể chỉ trả một tập con của dữ liệu, nhưng phải xem xét các nguồn rò rỉ:

- **Quyền trực tiếp khác:** user có thể còn `SELECT` bảng gốc qua role khác.
- **View hoặc API khác:** có thể có view khác trả cột email, hoặc function đặc quyền trả toàn bộ bản ghi.
- **Thống kê nhóm quá nhỏ:** doanh thu nhóm chỉ có một khách có thể tiết lộ giá trị đơn.
- **Sai khác giữa báo cáo:** so sánh nhiều tổng ở các thời điểm/bộ lọc khác nhau có thể suy ra thông tin cá nhân (*differencing*).
- **Thông báo lỗi và thời gian chạy:** trong một số tình huống biểu thức/hàm có thể tạo kênh suy luận ngoài dữ liệu trả trực tiếp.
- **Dữ liệu sao chép:** materialized view, bảng export hoặc cache có thể giữ dữ liệu sau khi view/bảng nguồn đã thay đổi chính sách.

Với dữ liệu nhạy cảm, câu hỏi cần hỏi không chỉ là “có lộ cột email không?” mà còn là **người nhận có thể suy ra điều cấm biết từ các kết quả hợp lệ không?**

Các cơ chế như ngưỡng kích thước nhóm, giới hạn khả năng lọc, audit và chính sách truy cập theo mục đích có thể cần thiết, nhưng một ngưỡng `HAVING COUNT(*) >= 5` đơn lẻ **không bảo đảm** chống suy luận nếu người dùng vẫn thực hiện được nhiều truy vấn chênh lệch nhau.

## 15. Vì sao SELECT * trong view không nên là hợp đồng bảo mật?

Một cách định nghĩa dễ viết:

```sql
CREATE VIEW v_all_orders AS
SELECT *
FROM orders;
```

Nhưng nếu bảng chứa hoặc được thêm cột nhạy cảm, cách tạo view với `SELECT *` khiến người đọc khó xác định rõ **những cột nào là phần được công bố**. Các DBMS có thể lưu/diễn giải danh sách cột trong view khác nhau khi schema nền thay đổi.

Nên ưu tiên:

```sql
CREATE VIEW v_paid_orders AS
SELECT
    order_id,
    sold_on,
    region,
    amount
FROM orders
WHERE status = 'PAID';
```

Lợi ích:

- Danh sách cột được **chấp thuận minh bạch**.
- Có thể review thay đổi bằng diff.
- Tránh vô tình đưa email/số định danh mới vào API dữ liệu.
- Giảm phụ thuộc của client vào toàn bộ cấu trúc bảng nguồn.

Đổi tên/sửa kiểu cột nguồn vẫn có thể ảnh hưởng view; cần quản lý schema migration. View giúp **giảm coupling**, không loại bỏ mọi phụ thuộc.

## 16. Có thể cấp quyền trên từng cột view không?

Một số DBMS, trong đó có PostgreSQL, hỗ trợ quyền `SELECT` ở mức cột. Ví dụ ý tưởng PostgreSQL:

```sql
-- Chỉ là ví dụ mô hình quyền; sử dụng trên view có sẵn.
GRANT SELECT (region, paid_amount)
ON sql316_api.v_paid_by_region
TO sql316_reader;
```

Nhưng trong lab, `sql316_reader` **đã được cấp SELECT toàn view**, nên cấp thêm quyền cột **không làm thu hẹp** quyền toàn view. Muốn chỉ cấp theo cột phải **thu hồi quyền toàn view trước**, đồng thời kiểm tra các đường quyền khác.

Một cách khác dễ bảo trì là tạo **view riêng cho nhóm độc giả khác nhau**, mỗi view có đúng danh sách cột và mức tổng hợp mong muốn.

**Lưu ý:** Quyền trên cột là cơ chế DBMS; nó không tự quyết định chính sách row-level, không thay thế `WHERE`/RLS.

## 17. View có cho INSERT, UPDATE, DELETE không?

View được dùng để báo cáo thường chỉ cần `SELECT`. Nhưng một số **view đơn giản có thể cập nhật** (*updatable view*) cho phép thao tác `INSERT`, `UPDATE` hoặc `DELETE` khi DBMS hỗ trợ và người gọi có quyền thích hợp.

Ví dụ PostgreSQL, chỉ minh họa với view đơn giản trên bảng thực hành; người đọc `sql316_reader` **không được cấp quyền UPDATE**:

```sql
SET ROLE sql316_owner;

CREATE VIEW sql316_api.v_paid_for_edit AS
SELECT
    order_id,
    sold_on,
    region,
    customer_name,
    customer_email,
    amount,
    status
FROM sql316_private.orders
WHERE status = 'PAID'
WITH LOCAL CHECK OPTION;

RESET ROLE;
```

`WITH CHECK OPTION` yêu cầu những thay đổi thực hiện **thông qua view** phải tiếp tục thỏa điều kiện hiển thị của view, trong phạm vi quy tắc update được DBMS hỗ trợ.

Ví dụ nếu được phép cập nhật qua view:

```sql
-- Chỉ là tình huống minh họa cho người có quyền UPDATE.
UPDATE sql316_api.v_paid_for_edit
SET status = 'PENDING'
WHERE order_id = 1;
```

Vì hàng sau khi update không còn thỏa `status = 'PAID'`, thao tác trên có thể bị `WITH CHECK OPTION` từ chối.

**Điểm mấu chốt:**

- `WITH CHECK OPTION` **không thay thế quyền `GRANT/REVOKE`**.
- Nó **không ngăn** tài khoản khác có quyền trên bảng gốc sửa qua đường trực tiếp.
- View chứa `GROUP BY`, aggregate hoặc nhiều phép biến đổi thường **không tự động cập nhật được** như view đơn giản.
- Quy tắc `LOCAL`/`CASCADED`, `INSTEAD OF` trigger và khả năng update qua view có khác biệt giữa DBMS.

Với view chỉ để đọc, **không cấp `INSERT/UPDATE/DELETE`** cho role báo cáo là lựa chọn đơn giản và rõ ràng.

## 18. MySQL và MariaDB: SQL SECURITY DEFINER / INVOKER

MySQL/MariaDB cho phép chỉ rõ ngữ cảnh bảo mật của view:

```sql
-- Minh họa cú pháp MySQL/MariaDB.
-- Cần có schema, bảng và tài khoản/quyền phù hợp.
CREATE SQL SECURITY DEFINER VIEW reporting.v_paid_orders AS
SELECT
    order_id,
    region,
    amount
FROM sales_private.orders
WHERE status = 'PAID';
```

Hoặc:

```sql
CREATE SQL SECURITY INVOKER VIEW reporting.v_paid_orders_invoker AS
SELECT
    order_id,
    region,
    amount
FROM sales_private.orders
WHERE status = 'PAID';
```

Ý nghĩa chung:

- `SQL SECURITY DEFINER`: quyền truy cập các đối tượng được view tham chiếu dựa trên **DEFINER**.
- `SQL SECURITY INVOKER`: quyền dựa trên **người gọi view**.
- View vẫn cần được cấp quyền cho người truy vấn; `SQL SECURITY` không có nghĩa là bất cứ ai cũng được gọi.
- Với `DEFINER`, việc **tài khoản definer tồn tại và có đủ quyền** là quan trọng. Xóa/đổi tài khoản hoặc thu hồi quyền có thể khiến view không hoạt động như trước.
- Để định nghĩa một `DEFINER` khác người tạo view có thể cần quyền quản trị đặc biệt; không giả định ứng dụng thường được phép chỉ định tùy ý.

Mẫu định nghĩa có khai báo definer:

```sql
-- Chỉ minh họa; account report_owner phải tồn tại
-- và account tạo view cần quyền thích hợp.
CREATE
    DEFINER = 'report_owner'@'localhost'
    SQL SECURITY DEFINER
VIEW reporting.v_paid_orders AS
SELECT order_id, region, amount
FROM sales_private.orders
WHERE status = 'PAID';
```

**Không sao chép account literal** `'report_owner'@'localhost'` sang môi trường khác nếu chưa kiểm tra cách cấu hình host/user. MySQL dùng cú pháp account gồm user và host; PostgreSQL không có dạng role tương đương trong `CREATE VIEW`.

Ở MySQL, `CURRENT_USER()` trong ngữ cảnh đối tượng `SQL SECURITY DEFINER` có thể phản ánh danh tính definer theo quy tắc của server, trong khi thông tin login kết nối có thể được kiểm tra bằng hàm khác. Khi debug, phân biệt **người kết nối** và **tài khoản được dùng để kiểm tra quyền đối tượng**.

## 19. SQL Server: quyền trên view và ownership chaining

SQL Server có cơ chế quan trọng gọi là **ownership chaining** (*chuỗi sở hữu*). Khi view truy cập bảng bên dưới **cùng chủ sở hữu** theo quy tắc của SQL Server, DBMS thường kiểm tra quyền trên view nhưng **không cần kiểm tra lại quyền SELECT của người gọi trên bảng nguồn** trong đoạn chuỗi sở hữu liên tục.

Ví dụ ý tưởng:

```sql
-- SQL Server: tạo view trong database đã chuẩn bị schema.
CREATE VIEW report.v_paid_orders
AS
SELECT
    order_id,
    region,
    amount
FROM private_data.orders
WHERE status = 'PAID';
GO

GRANT SELECT ON OBJECT::report.v_paid_orders
TO report_reader;
```

`GO` là dấu phân tách batch do một số công cụ SQL Server nhận diện, **không phải câu lệnh T-SQL của engine**. `CREATE VIEW` thường cần ở vị trí thích hợp trong batch, vì vậy ví dụ tách bằng `GO` khi dùng SSMS/sqlcmd.

Cần phân biệt:

- **Cùng owner:** ownership chain có thể giúp caller xem view mà không có SELECT bảng nguồn.
- **Khác owner:** chuỗi sở hữu có thể bị đứt; DBMS có thể yêu cầu quyền bổ sung trên đối tượng bên dưới.
- **Dynamic SQL** và một số loại truy cập khác không nhất thiết đi theo ownership chain theo cách tương tự.
- `EXECUTE AS CALLER`, `EXECUTE AS OWNER`... thường gắn với **module như stored procedure/function** theo quy tắc SQL Server; **không dùng như một lựa chọn `SQL SECURITY` đặt trực tiếp vào câu `CREATE VIEW` tương tự MySQL**.
- SQL Server cũng có Row-Level Security, quyền schema/object, module signing và các cơ chế khác; không được suy rằng ownership chain giải quyết tất cả chính sách hàng.

Khi chuyển một thiết kế từ PostgreSQL/MySQL sang SQL Server, cần kiểm tra **chủ sở hữu thực tế của các schema/đối tượng** thay vì chỉ nhìn tên login đã tạo view.

## 20. Oracle Database: quyền trực tiếp để tạo view

Oracle thường kiểm tra quyền dựa trên **chủ view** đối với những bảng được view tham chiếu. Một điểm rất quan trọng khi triển khai là **quyền cần thiết để định nghĩa view trên đối tượng người khác** thường phải được cấp **trực tiếp cho user tạo view**, không chỉ nhận qua role đang bật.

Ví dụ về quan hệ cấp quyền:

```text
private_owner.orders
        |
        | quyền SELECT cấp trực tiếp đủ điều kiện
        v
report_owner.v_paid_orders
        |
        | GRANT SELECT trên view
        v
    report_reader
```

Nếu chủ view không sở hữu bảng nguồn và muốn tiếp tục cấp quyền trên view cho người khác, cần xem kỹ yêu cầu Oracle về quyền nguồn và **WITH GRANT OPTION** trong trường hợp thích hợp, cùng các giới hạn của hệ thống. Không suy rằng một role có `SELECT` bảng là đủ để user tạo/cấp view của mình.

Oracle còn có cú pháp **`BEQUEATH DEFINER` / `BEQUEATH CURRENT_USER`** đối với ngữ cảnh của một số function được gọi qua view; cơ chế này **không đơn giản tương đương** việc chuyển tất cả quyền truy cập bảng nguồn của view sang caller như `SQL SECURITY INVOKER` trong MySQL.

Hãy dùng tài liệu đúng **phiên bản Oracle đang chạy** cho cú pháp và quy tắc đặc biệt; không ghép cơ học các từ khóa `DEFINER`, `INVOKER` của nhiều DBMS vào một câu `CREATE VIEW`.

## 21. SQLite: view không phải ranh giới role như DBMS server

SQLite là hệ cơ sở dữ liệu nhúng; **không có cơ chế user/role và `GRANT SELECT ON VIEW` tích hợp theo mô hình phổ biến của PostgreSQL, MySQL, SQL Server hay Oracle**.

Bạn có thể:

```sql
CREATE VIEW v_paid_orders AS
SELECT order_id, region, amount
FROM orders
WHERE status = 'PAID';
```

nhưng **chỉ tạo view không ngăn** một ứng dụng có quyền truy cập database file thực hiện:

```sql
SELECT *
FROM orders;
```

Với SQLite, việc tách quyền thường phụ thuộc **quyền truy cập file, thiết kế ứng dụng, các kết nối và cơ chế authorizer/đóng gói API thích hợp**. Không dùng view như biện pháp duy nhất để bảo vệ dữ liệu nhạy cảm trước một client được phép tự chạy SQL vào database file.

### Bảng so sánh tổng hợp

| DBMS | Cơ chế chính khi SELECT view | Ghi nhớ |
| --- | --- | --- |
| PostgreSQL | View mặc định dùng quyền chủ view cho quan hệ nguồn; `security_invoker=true` từ PostgreSQL 15+ | `security_barrier` là chủ đề riêng; chú ý RLS và function |
| MySQL/MariaDB | `SQL SECURITY DEFINER` hoặc `INVOKER` | Quản lý definer account và quyền của nó |
| SQL Server | Object permissions và ownership chaining | Cùng/khác owner có thể thay đổi quyền cần thiết |
| Oracle | Quyền tạo view và quyền nguồn của chủ view; các quy tắc grant trực tiếp | Kiểm tra `WITH GRANT OPTION` khi cấp quyền view cho bên khác; `BEQUEATH` có phạm vi riêng |
| SQLite | Không có `GRANT`/role SQL tích hợp tương đương | View chủ yếu là trừu tượng hóa truy vấn, không là biên phân quyền người dùng |

## 22. Vòng đời view: thay chủ sở hữu, đổi schema, thu hồi quyền

Một triển khai view an toàn cần quản lý **toàn bộ vòng đời**, không chỉ ngày tạo đầu tiên.

### 22.1. Đổi định nghĩa view có thể mở rộng quyền dữ liệu

Giả sử ban đầu view chỉ gồm:

```sql
SELECT order_id, region, amount
FROM private_data.orders;
```

Sau một lần sửa thành:

```sql
SELECT order_id, region, amount, customer_email
FROM private_data.orders;
```

người có `SELECT` toàn view có thể bắt đầu nhận thêm email (tùy cơ chế cập nhật định nghĩa và quyền DBMS). Vì vậy **migration của view là thay đổi API và có thể là thay đổi bảo mật**, cần review các cột được công bố.

Ở PostgreSQL, `CREATE OR REPLACE VIEW` có các ràng buộc với cột hiện hữu; không phải mọi phép đổi cấu trúc đều thay ngay được. Thiết kế công bố dữ liệu nên có kiểm tra schema của view sau migration, không chỉ “câu lệnh chạy không lỗi”.

### 22.2. Đổi owner/definer có thể đổi quyền thực thi

View do một role nhiều quyền sở hữu có thể tiếp cận nhiều bảng hơn dự định. Đổi owner/definer có thể khiến view bắt đầu lỗi hoặc thay đổi tập dữ liệu/quy tắc RLS được áp dụng.

Nên dùng **role riêng, không đăng nhập, có quyền tối thiểu** để sở hữu object API khi DBMS hỗ trợ, thay vì dùng superuser cho mọi view.

### 22.3. Thu hồi quyền không chắc đã xóa bản sao dữ liệu

Nếu người dùng đã:

- Export kết quả view ra CSV;
- Chép dữ liệu vào bảng staging;
- Đưa dữ liệu vào cache;
- Tạo báo cáo hoặc materialized view được phép;

thì `REVOKE SELECT ON view` **không xóa dữ liệu đã bị sao chép**. Kiểm soát vòng đời dữ liệu, lưu trữ và quyền cache cần được xử lý riêng.

### 22.4. Materialized view cần chính sách refresh

Một materialized view là **dữ liệu lưu vật lý**: người đọc có thể thấy bản kết quả lần refresh gần nhất. Cần kiểm tra:

- Ai được quyền `SELECT` bản vật chất hóa?
- Ai được phép refresh, refresh chạy bằng quyền nào?
- Kết quả có lẫn dữ liệu mà chính sách nguồn đã cấm sau lần refresh không?
- Việc thu hồi quyền nguồn hoặc cập nhật RLS có được phản ánh sau refresh không?
- Có giới hạn thời gian lưu và cơ chế dọn bản sao không?

Không suy rằng SELECT materialized view sẽ kiểm tra lại toàn bộ quyền và RLS trên bảng nguồn cho mỗi lần đọc; nó là một đối tượng chứa kết quả vật chất hóa, khác view truy vấn trực tiếp.

## 23. Checklist thiết kế quyền thực tế

Trước khi đưa view vào ứng dụng, nên trả lời:

1. **Ai gọi?** Login/service account nào? Họ thuộc những role nào?
2. **Giao diện nào?** View trả đúng những cột và mức chi tiết được phép hay không?
3. **Schema công bố?** Caller có quyền truy cập schema view nhưng không được mở rộng quyền không cần thiết sang schema riêng?
4. **Quyền view?** `SELECT` hay có cả `UPDATE/INSERT/DELETE`?
5. **Quyền nguồn?** Chủ view/definer/invoker nào được kiểm tra? Có đường SELECT trực tiếp khác không?
6. **RLS?** Chính sách áp dụng theo owner hay caller? Có owner/bypass/force nào làm khác dự kiến?
7. **Function?** Có `SECURITY DEFINER`, SQL động, tên object không đủ schema, `EXECUTE` công khai hoặc ngữ cảnh đặc quyền không?
8. **Optimizer?** View được dùng làm hàng rào lọc dữ liệu nhạy cảm có cần `security_barrier` hoặc cơ chế tương ứng?
9. **Tổng hợp?** Báo cáo có để lộ giá trị riêng lẻ qua nhóm nhỏ hoặc kết hợp nhiều báo cáo không?
10. **Vòng đời?** Migration, thay owner, thay definer, thu hồi quyền, copy/cache và refresh đã có quy trình kiểm soát chưa?
11. **Kiểm thử?** Có thử với **role đúng như ứng dụng**, kiểm cả truy vấn hợp lệ và truy cập bị từ chối không?
12. **Vận hành?** Có log/audit truy cập phù hợp và tách biệt quyền tài khoản triển khai với tài khoản runtime không?

Với một role API chỉ đọc, mục tiêu mặc định là **chỉ cấp những quyền mà truy vấn API thật sự cần**, thay vì cấp quyền trên mọi bảng cùng schema để tránh lỗi lúc phát triển.

## 24. Lỗi thường gặp

| Hiện tượng hoặc hiểu nhầm | Vì sao sai/dễ rủi ro | Cách xử lý |
| --- | --- | --- |
| “GRANT SELECT view là bảo mật xong” | User có thể còn quyền qua bảng gốc, role khác hoặc function | Kiểm tra mọi đường quyền hiệu lực |
| Có SELECT view nhưng vẫn báo permission denied | Thiếu quyền schema, nguồn dưới cơ chế invoker, function hoặc ownership chain bị đứt | Xác định chính xác đối tượng và ngữ cảnh gây lỗi |
| Reader không có SELECT bảng nhưng đọc được view | Có thể đúng theo cơ chế owner/definer | Kiểm tra view thực sự chỉ trả dữ liệu cho phép |
| Bật `security_invoker` để “ẩn” bảng nguồn | Invoker view thường đòi người gọi có quyền đọc bảng nguồn | Chọn mô hình quyền phù hợp; xem RLS, quyền cột |
| Bật `security_barrier` để thay GRANT | Nó không cấp/tước quyền | Kết hợp phân quyền và bảo vệ điều kiện lọc |
| Dựa hoàn toàn vào RLS caller qua view mặc định | View owner/table owner có thể làm chính sách khác dự kiến | Kiểm tra mô hình RLS theo owner/invoker |
| Dùng `current_user` kết luận mọi phép kiểm tra view theo caller | PostgreSQL có cơ chế kiểm tra quyền nguồn của view độc lập với giá trị role session thông thường | Phân biệt session identity và object privilege context |
| Function đặc quyền có thể dùng SQL động không kiểm soát | Dẫn tới thực thi ngoài ý muốn bằng quyền owner | Ràng buộc input, search_path và quyền tối thiểu |
| `SELECT *` trong view báo cáo | Không rõ hợp đồng cột; khó review dữ liệu công bố | Liệt kê cột |
| `COUNT`/`SUM` theo nhóm nhỏ được coi là vô hại | Có thể suy ra dữ liệu từ một nhóm nhỏ hoặc truy vấn chênh lệch | Đánh giá rủi ro suy luận và giới hạn báo cáo |
| Materialized view luôn áp dụng quyền mới của bảng nguồn | Dữ liệu đã được lưu; đọc không phải lúc nào kiểm lại nguồn | Thiết kế policy trên bản sao và refresh |
| Coi SQLite view như role-boundary | SQLite không có `GRANT` như DBMS server | Kiểm soát ở file/application/authorizer |
| Sao chép một câu `CREATE VIEW` giữa các DBMS | `DEFINER`, `PIVOT`, `security_invoker`, ownership chaining khác nhau | Chọn cú pháp/semantics đúng dialect và phiên bản |

## 25. Bài tập thực hành

Các câu hỏi sử dụng bộ dữ liệu `sql316_private.orders` và hai view `sql316_api` ở mục 5–7, trừ khi có ghi chú riêng. Không cần cấp thêm quyền thật cho người dùng khác để trả lời các câu lý thuyết.

### Bài 1 — Đọc biểu đồ quyền

Với mô hình lab, `sql316_reader` có `USAGE ON SCHEMA sql316_api` và `SELECT ON sql316_api.v_paid_orders`, nhưng không có `SELECT` trên `sql316_private.orders`. Vì sao reader vẫn đọc được `v_paid_orders`? Trong trường hợp nào điều này không còn đúng?

### Bài 2 — Thiếu USAGE

Một role đã có `SELECT` trên view thuộc schema `sql316_api` nhưng truy vấn qua tên đầy đủ vẫn báo không có quyền trên schema. Cần thêm lệnh PostgreSQL nào? Có cần cấp USAGE trên `sql316_private` không nếu view vẫn chạy theo mô hình owner mặc định?

### Bài 3 — Lọc đơn PAID

Truy vấn `v_paid_orders` ở lab sẽ trả bao nhiêu dòng? Tại sao không có đơn số 3 và 6? Vì sao không thể `SELECT customer_email` trực tiếp từ view này?

### Bài 4 — Kết quả tổng hợp

Truy vấn `v_paid_by_region` cho khu vực Bắc và Nam trả giá trị `paid_orders`, `paid_amount` là bao nhiêu? Vì sao không có khu vực Trung?

### Bài 5 — security_invoker

Tạo một view dùng `security_invoker=true` cùng câu SELECT với `v_paid_orders` trên PostgreSQL 15+. Chỉ cấp `SELECT` view cho reader, không cấp quyền nguồn. Khi reader truy vấn, kết quả mong đợi là gì? Nếu muốn view invoker chạy được thì phải xem xét điều gì?

### Bài 6 — security_barrier và RLS

Trả lời đúng/sai và giải thích: “Bật `security_barrier=true` thì PostgreSQL sẽ kiểm tra quyền bảng nguồn bằng người gọi, đồng thời luôn áp dụng RLS của người gọi.”

### Bài 7 — SET ROLE

Đăng nhập bằng một account quản trị có thể `SET ROLE sql316_reader`. Sau `SET ROLE`, `session_user` và `current_user` khác nhau như thế nào? Điều đó có tự chứng minh mọi quyền truy cập quan hệ nguồn của view theo reader không?

### Bài 8 — SECURITY DEFINER

Function `paid_total_for_region` chạy bằng quyền của ai? Vì sao nên `REVOKE ... FROM PUBLIC`, đặt `search_path` được kiểm soát và không cho phép người gọi chọn tenant tùy ý nếu chức năng phải cách ly tenant?

### Bài 9 — Khác biệt DBMS

Ghép DBMS và cơ chế: (a) ownership chaining, (b) `SQL SECURITY DEFINER/INVOKER` ở view, (c) `security_invoker=true` từ PostgreSQL 15+, (d) không có `GRANT SELECT ON VIEW` tích hợp như DBMS server.

### Bài 10 — Bảng tạm so với view

Vì sao việc đọc một bảng staging đã lưu bản sao dữ liệu khác với việc SELECT view thường? Nếu thu hồi quyền đọc bảng nguồn thì bản sao staging có tự biến mất không?

### Bài 11 — Quyền theo nhóm

User có quyền SELECT bảng nguồn do membership ở role `data_admin`. Nếu thu hồi `SELECT` khỏi user trực tiếp rồi chỉ cấp view, liệu đã ngăn được truy cập bảng nguồn chưa? Phải kiểm tra gì?

### Bài 12 — Thiết kế API báo cáo

Hệ thống có bảng chứa `order_id`, `tenant_id`, `email`, `amount` và `status`; mỗi tenant chỉ được xem tổng doanh thu của mình. Hãy nêu một thiết kế bảo mật hợp lý, chỉ rõ chỗ cần xác thực danh tính tenant, quyền trên view/bảng và vì sao không nên tin giá trị tenant do client tự gửi là bằng chứng quyền truy cập.

## 26. Gợi ý đáp án

**Bài 1.** PostgreSQL view mặc định kiểm tra quyền trên quan hệ nền theo **chủ view**, nên reader chỉ cần quyền phù hợp trên view/schema công bố. Điều này thay đổi với `security_invoker=true` (PostgreSQL 15+) hoặc khi có hàm/quyền phụ trợ, view owner thiếu quyền, chính sách khác tác động.

**Bài 2.**

```sql
GRANT USAGE ON SCHEMA sql316_api TO sql316_reader;
```

Không cần cấp quyền trực tiếp vào `sql316_private` chỉ vì view mặc định tham chiếu bảng nằm trong schema đó.

**Bài 3.** Có **4** đơn PAID: số 1, 2, 4, 5. Đơn 3 `CANCELLED`, đơn 6 `PENDING`. View không công bố cột `customer_email` nên tên cột đó không nằm trong giao diện của view.

**Bài 4.** Bắc: `paid_orders = 2`, `paid_amount = 200`. Nam: `paid_orders = 2`, `paid_amount = 300`. Trung không có đơn PAID nên phép `GROUP BY region` trên tập đã lọc không tạo nhóm Trung.

**Bài 5.** Truy vấn invoker view bị từ chối do reader thiếu quyền nguồn. Để chạy được, phải thiết kế quyền đọc bảng nguồn phù hợp và kiểm tra RLS/giới hạn cột, tránh vô tình mở quyền truy vấn thẳng toàn bộ dữ liệu.

**Bài 6.** **Sai.** `security_barrier` điều chỉnh cách một số điều kiện bị đẩy/tái sắp xếp qua view. `security_invoker` mới là tùy chọn liên quan tới việc kiểm tra quyền quan hệ nền theo người gọi, đồng thời ảnh hưởng ngữ cảnh RLS.

**Bài 7.** `session_user` giữ role login gốc, `current_user` đổi thành `sql316_reader` sau `SET ROLE`. Giá trị này không thay thế kiểm tra quy tắc quyền riêng của view, function và chính sách RLS.

**Bài 8.** Function `SECURITY DEFINER` chạy với quyền chủ function (`sql316_owner`). Thu hồi `EXECUTE` công khai, kiểm soát `search_path` và xác thực tenant để không cho caller biến function thành lối đọc ngoài phạm vi được phép.

**Bài 9.** (a) **SQL Server**; (b) **MySQL/MariaDB**; (c) **PostgreSQL**; (d) **SQLite**.

**Bài 10.** View thông thường dùng định nghĩa truy vấn khi được đọc, còn staging lưu dữ liệu như một đối tượng vật lý; cấp/thu hồi quyền nguồn không tự xóa bản sao cũ, cần chính sách và thao tác dọn riêng.

**Bài 11.** **Chưa.** User có thể còn quyền hiệu lực qua role `data_admin` và các nguồn khác. Cần kiểm tra membership, quyền hiệu lực, PUBLIC, quyền quản trị, schema và quyền trên bảng nguồn.

**Bài 12.** Một thiết kế có thể gồm: bảng nguồn không cấp SELECT tự do cho role ứng dụng; sử dụng RLS theo danh tính đã xác thực hoặc view/function server-side kiểm soát chặt tenant; cấp chỉ quyền gọi API cần thiết; kiểm soát role owner/definer và quyền bypass; trả tổng hợp không chứa email; kiểm thử bằng account thật của tenant A/B, bao gồm cố gắng truy cập chéo. **Tenant ID client gửi chỉ là dữ liệu đầu vào**, phải được ràng buộc với danh tính/quyền đã xác thực ở phía tin cậy.

## 27. Dọn môi trường thực hành

Sau khi hoàn thành, chỉ dọn các đối tượng **do chính bài thực hành tạo**, trong database học tập và bằng tài khoản quản trị phù hợp. Nếu đã tạo function, invoker view và view thử update ở các mục tùy chọn, lệnh xóa schema theo `CASCADE` dưới đây cũng xóa các đối tượng đó. **Đừng chạy trên schema có đối tượng thật khác.**

```sql
-- PostgreSQL: chỉ trong môi trường thực hành đã xác nhận.
RESET ROLE;

DROP SCHEMA sql316_api CASCADE;
DROP SCHEMA sql316_private CASCADE;

DROP ROLE sql316_reader;
DROP ROLE sql316_owner;
```

Nếu role còn được tham chiếu/cấp quyền ở nơi khác, `DROP ROLE` có thể báo lỗi và cần kiểm tra dependency. Không dùng `DROP OWNED` hoặc `CASCADE` trên role/schema dùng chung chỉ để ép lệnh dọn thành công.

## 28. Kết luận

**View là một giao diện truy vấn có thể phân quyền độc lập trên nhiều DBMS**, nhưng an toàn hay không phụ thuộc vào cơ chế kiểm tra quyền của hệ đang chạy. Ở PostgreSQL, view mặc định thường đọc quan hệ nền bằng quyền chủ view, trong khi `security_invoker=true` từ phiên bản 15 chuyển quyền nguồn sang invoker; `security_barrier` lại phục vụ một mục đích khác về an toàn của điều kiện lọc. MySQL/MariaDB cung cấp `SQL SECURITY DEFINER/INVOKER`; SQL Server cần hiểu ownership chaining; Oracle có quy tắc cấp quyền trực tiếp cho chủ view; SQLite không có mô hình SQL role/GRANT tương tự.

Khi thiết kế, hãy bắt đầu từ **dữ liệu được phép công bố**, đặt view ở schema API, **GRANT tối thiểu**, kiểm tra cả **quyền hiệu lực ở bảng nguồn**, hiểu ngữ cảnh **owner/definer/invoker**, và thử bằng **role ít quyền thực tế**. Với dữ liệu nhiều tenant hoặc nhạy cảm, phải kết hợp chính sách hàng, ngữ cảnh function, rủi ro suy luận và vòng đời bản sao dữ liệu. **View giúp tạo một ranh giới truy cập có chủ đích; nó không thay thế việc thiết kế và kiểm thử bảo mật toàn hệ thống.**
