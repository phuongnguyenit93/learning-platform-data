# Cung cấp dữ liệu báo cáo qua view và phân quyền tối thiểu

Một ứng dụng báo cáo thường chỉ cần một phần dữ liệu của hệ thống: vài cột có tên ổn định, một số phép tính, bộ lọc nghiệp vụ và quyền đọc. Nếu cấp cho tài khoản báo cáo quyền SELECT trên toàn bộ bảng nguồn, người dùng có thể đọc những cột hoặc bảng không cần thiết, đồng thời ứng dụng bị phụ thuộc vào cấu trúc nội bộ của database.

Một **view** (khung nhìn) cho phép định nghĩa một tập kết quả có tên bằng câu SELECT. Ta có thể tạo view riêng cho báo cáo, chỉ đưa ra những cột được phép sử dụng, sau đó cấp quyền SELECT trên view cho một role đọc báo cáo. Role đó không nhất thiết phải có quyền đọc trực tiếp các bảng nguồn.

~~~text
Bảng nghiệp vụ
     |
     v
View báo cáo có cột và logic được chọn
     |
     v
Role chỉ có SELECT trên view
     |
     v
Tài khoản báo cáo / BI / dashboard
~~~

View giúp đóng gói truy vấn và kiểm soát bề mặt dữ liệu được công bố. Quyền truy cập vẫn phải được thiết kế đúng: ai sở hữu view, quyền trên bảng nguồn được kiểm tra dưới danh tính nào, row-level security có được áp dụng không và role báo cáo có nhận quyền gián tiếp qua role khác hay không.

Bài học thuộc module **Database SQL**, chương **Thực hành tổng hợp**, chủ đề **“Cung cấp dữ liệu báo cáo qua view và phân quyền tối thiểu”**. Phần thực hành chính dùng PostgreSQL; cuối bài so sánh cách triển khai ở MySQL/MariaDB, SQL Server, Oracle và SQLite.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích view là gì, dữ liệu được lưu ở đâu và khi nào query của view được thực thi.
2. Thiết kế view báo cáo với alias, kiểu dữ liệu và grain ổn định.
3. Phân biệt view thường và materialized view.
4. Tạo schema báo cáo tách khỏi schema nghiệp vụ.
5. Tổ chức role owner không đăng nhập và role reader chỉ đọc.
6. Cấp đúng USAGE trên schema và SELECT trên view.
7. Giới hạn quyền trên bảng nguồn theo nguyên tắc least privilege.
8. Hiểu quyền truy cập bảng nguồn của view theo semantics từng DBMS.
9. Nhận biết tác động của RLS, security_invoker và security_barrier trong PostgreSQL.
10. Kiểm tra quyền hiệu lực, quyền kế thừa và quyền PUBLIC.
11. Tránh các lỗi do SELECT *, view updatable, function không an toàn và materialized data.
12. Thiết kế kiểm thử xác nhận tài khoản báo cáo đọc được view nhưng không đọc được bảng gốc.
13. Xử lý thay đổi view và quyền khi triển khai migration.
14. Hoàn thành các bài tập thực hành có lời giải.

## 2. View là gì?

View là một đối tượng database có tên, định nghĩa bằng một câu truy vấn. Ví dụ:

~~~sql
CREATE VIEW reporting.v_order_report AS
SELECT
    o.id AS order_id,
    o.created_at AS order_date,
    c.display_name AS customer_name,
    o.status AS order_status,
    o.total_amount
FROM app.orders AS o
JOIN app.customers AS c
    ON c.id = o.customer_id;
~~~

Sau đó ứng dụng có thể truy vấn:

~~~sql
SELECT
    order_id,
    order_date,
    customer_name,
    order_status,
    total_amount
FROM reporting.v_order_report
WHERE order_date >= DATE '2026-01-01'
ORDER BY order_date DESC, order_id DESC;
~~~

Ứng dụng không cần lặp lại JOIN giữa orders và customers. Tên view trở thành một hợp đồng dữ liệu có thể được dùng bởi dashboard, công cụ BI, export job hoặc repository.

### 2.1. View thường không lưu bản sao kết quả

Với view thông thường, database lưu định nghĩa query. Khi truy vấn view, DBMS kết hợp định nghĩa đó với câu SELECT của caller và thực thi theo kế hoạch phù hợp.

View không tự tạo một bảng chứa kết quả đã tính sẵn. Nếu bảng nguồn thay đổi, lần truy vấn view tiếp theo thường nhìn thấy dữ liệu mới theo snapshot/transaction hiện tại.

Điều này có nghĩa:

- View giảm việc lặp lại SQL và tạo một giao diện dữ liệu có tên.
- View không tự động làm query nhanh hơn.
- View không phải bản sao độc lập của dữ liệu.
- Hiệu năng phụ thuộc query bên trong, index, statistics và bộ lọc của caller.

### 2.2. View không phải một bảng mới chứa dữ liệu

~~~sql
SELECT COUNT(*)
FROM reporting.v_order_report;
~~~

DBMS đọc các bảng nguồn theo định nghĩa view. Nếu view JOIN bảng lớn hoặc chứa aggregate phức tạp, query vẫn có thể tốn tài nguyên như truy vấn gốc.

### 2.3. View có thể được lồng

Một view có thể truy vấn view khác:

~~~sql
CREATE VIEW reporting.v_paid_orders AS
SELECT order_id, order_date, customer_name, total_amount
FROM reporting.v_order_report
WHERE order_status = 'PAID';
~~~

Cách này giúp phân lớp logic, nhưng cần quản lý dependency và tránh tạo quá nhiều tầng view khó theo dõi. Khi debug, hãy kiểm tra định nghĩa và execution plan của toàn chuỗi.

## 3. Phân biệt view, materialized view và bảng báo cáo

| Đặc điểm | View thường | Materialized view | Bảng báo cáo tự nạp |
|---|---|---|---|
| Lưu kết quả dữ liệu | Không | Có | Có |
| Đọc dữ liệu nguồn khi truy vấn | Thường có | Không cần tính lại mỗi lần | Không cần tính lại mỗi lần |
| Độ mới dữ liệu | Theo snapshot hiện tại | Có thể cũ đến lần refresh | Theo lịch/job nạp |
| Chi phí đọc | Phụ thuộc query nguồn | Thường thấp hơn cho phép tính đã lưu | Thường thấp nếu thiết kế tốt |
| Chi phí cập nhật | Chủ yếu ở lúc đọc | Refresh/recompute | ETL/ELT hoặc application job |
| Quyền truy cập | Grant trên view | Grant trên materialized view | Grant trên bảng |

### 3.1. Khi nào dùng view thường?

- Báo cáo cần dữ liệu gần thời gian thực.
- Logic JOIN/filter không quá nặng.
- Muốn công bố một tập cột ổn định.
- Muốn tách quyền đọc khỏi bảng nguồn.
- Muốn tránh sao chép dữ liệu nhạy cảm sang một bảng báo cáo khác.

### 3.2. Khi nào dùng materialized view?

- Báo cáo có aggregate tốn kém.
- Dữ liệu không cần cập nhật ngay sau mỗi transaction.
- Có thể chấp nhận lịch refresh.
- Cần tối ưu truy vấn dashboard đọc lặp lại.

PostgreSQL:

~~~sql
CREATE MATERIALIZED VIEW reporting.mv_monthly_sales AS
SELECT
    date_trunc('month', o.created_at)::date AS sales_month,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS gross_amount
FROM app.orders AS o
WHERE o.status = 'PAID'
GROUP BY date_trunc('month', o.created_at)::date;
~~~

Refresh:

~~~sql
REFRESH MATERIALIZED VIEW reporting.mv_monthly_sales;
~~~

PostgreSQL hỗ trợ REFRESH MATERIALIZED VIEW CONCURRENTLY khi materialized view đã được populate và có unique index phù hợp bao phủ toàn bộ hàng theo yêu cầu của PostgreSQL. Cần đọc tài liệu đúng phiên bản trước khi chọn cách refresh.

Materialized view lưu bản sao dữ liệu đã tính. Nếu chứa thông tin nhạy cảm, quyền SELECT trên materialized view cũng cần được kiểm soát. Quyền trên view không thay thế việc kiểm soát quyền refresh và ownership.

### 3.3. Khi nào dùng bảng báo cáo?

Nếu cần snapshot theo kỳ, lịch sử báo cáo bất biến hoặc dữ liệu được hợp nhất từ nhiều nguồn, một bảng báo cáo do pipeline nạp có thể phù hợp hơn. Khi đó phải quản lý lịch nạp, tính lặp an toàn, lineage, thời điểm dữ liệu và quyền truy cập.

## 4. Thiết kế view như một hợp đồng báo cáo

View nên công bố đúng dữ liệu mà consumer cần. Hãy xác định:

- Một hàng đại diện cho điều gì (grain)?
- Cột nào được phép lộ ra?
- Alias có ổn định không?
- Cột nào có thể NULL?
- Kiểu dữ liệu và precision là gì?
- Bộ lọc nghiệp vụ có thuộc định nghĩa view không?
- Caller có được phép tự lọc theo ngày, trạng thái hoặc đơn vị không?
- View có được dùng cho nhiều báo cáo hay chỉ một báo cáo cụ thể?

### 4.1. Liệt kê cột tường minh

Không nên dùng:

~~~sql
CREATE VIEW reporting.v_orders AS
SELECT *
FROM app.orders;
~~~

Nếu bảng orders được thêm cột email, token, internal_note hoặc thông tin nhạy cảm, SELECT * có thể vô tình đưa cột mới vào bề mặt dữ liệu báo cáo.

Nên viết:

~~~sql
CREATE VIEW reporting.v_orders AS
SELECT
    id AS order_id,
    created_at AS order_date,
    status AS order_status,
    total_amount
FROM app.orders;
~~~

### 4.2. Dùng alias có ý nghĩa

Tên cột báo cáo nên mô tả ý nghĩa business:

~~~sql
SELECT
    o.id AS order_id,
    o.total_amount AS gross_amount,
    o.created_at AS ordered_at
FROM app.orders AS o;
~~~

Tránh alias chung chung như value, data, result nếu view có nhiều metric. Alias là một phần contract của view và consumer.

### 4.3. Đặt grain rõ ràng

Ví dụ:

- v_order_report: một hàng mỗi order.
- v_customer_order_summary: một hàng mỗi customer.
- v_monthly_sales: một hàng mỗi tháng và trạng thái.
- v_product_sales: một hàng mỗi product và kỳ báo cáo.

Nếu JOIN bảng order_items vào view một hàng mỗi order, kết quả có thể chuyển thành một hàng mỗi item. Khi đó tổng tiền order có thể bị lặp. Aggregate dữ liệu con trước khi JOIN hoặc giữ grain chi tiết có tên riêng.

### 4.4. Không dựa vào ORDER BY trong view

Một view không nên được coi là có thứ tự cố định. Consumer cần chỉ định ORDER BY trong câu SELECT:

~~~sql
SELECT *
FROM reporting.v_orders
ORDER BY order_date DESC, order_id DESC;
~~~

Ngay cả khi một định nghĩa view chứa ORDER BY trong một số DBMS/ngữ cảnh, query bên ngoài vẫn phải yêu cầu thứ tự mà báo cáo cần.

## 5. Ví dụ schema nghiệp vụ

Giả sử ứng dụng có hai schema:

- app: bảng nghiệp vụ, gồm customers và orders.
- reporting: các view được công bố cho người làm báo cáo.

Schema mẫu:

~~~sql
CREATE TABLE app.customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    tax_identifier VARCHAR(50)
);

CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES app.customers(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL
);
~~~

Thông tin email và tax_identifier không cần thiết cho báo cáo tổng hợp doanh thu. Không đưa chúng vào view chỉ vì chúng có sẵn trong bảng.

### 5.1. View chi tiết đơn hàng

~~~sql
CREATE VIEW reporting.v_order_report AS
SELECT
    o.id AS order_id,
    o.created_at AS order_created_at,
    c.display_name AS customer_name,
    o.status AS order_status,
    o.total_amount
FROM app.orders AS o
JOIN app.customers AS c
    ON c.id = o.customer_id;
~~~

View này có một hàng cho mỗi order nếu mỗi order tham chiếu đúng một customer và customer.id là khóa duy nhất.

### 5.2. View doanh thu theo tháng

~~~sql
CREATE VIEW reporting.v_monthly_sales AS
SELECT
    date_trunc('month', o.created_at)::date AS sales_month,
    o.status AS order_status,
    COUNT(*)::bigint AS order_count,
    SUM(o.total_amount)::numeric(16,2) AS gross_amount
FROM app.orders AS o
WHERE o.status IN ('PAID', 'SHIPPED')
GROUP BY
    date_trunc('month', o.created_at)::date,
    o.status;
~~~

Báo cáo:

~~~sql
SELECT
    sales_month,
    order_status,
    order_count,
    gross_amount
FROM reporting.v_monthly_sales
WHERE sales_month >= DATE '2026-01-01'
ORDER BY sales_month, order_status;
~~~

View đã giới hạn trạng thái được đưa vào báo cáo. Nếu người dùng cần phân tích cả đơn bị hủy, nên tạo contract/view riêng hoặc thay đổi logic theo yêu cầu nghiệp vụ đã duyệt.

### 5.3. Cẩn thận với timezone trong báo cáo tháng

Ví dụ dùng date_trunc('month', created_at) trên timestamptz của PostgreSQL. Kết quả phụ thuộc timezone của session khi xác định tháng. Nếu báo cáo quy định tháng theo múi giờ Việt Nam hoặc theo múi giờ tài chính riêng, hãy chuyển timezone rõ trước khi nhóm.

~~~sql
SELECT
    date_trunc(
        'month',
        o.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS sales_month,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS gross_amount
FROM app.orders AS o
WHERE o.status = 'PAID'
GROUP BY 1;
~~~

Đừng để timezone mặc định của connection quyết định kỳ báo cáo mà không có quy định.

## 6. Nguyên tắc least privilege

Least privilege (quyền tối thiểu) nghĩa là mỗi principal chỉ được cấp các quyền cần để hoàn thành nhiệm vụ của mình.

Một tài khoản báo cáo thường cần:

- Kết nối database.
- Truy cập schema chứa view.
- SELECT trên những view được công bố.
- Có thể đọc một số materialized view đã được duyệt.

Tài khoản đó thường không cần:

- SELECT trên mọi bảng nghiệp vụ.
- INSERT, UPDATE, DELETE hoặc TRUNCATE.
- CREATE/ALTER/DROP schema hoặc table.
- Quyền sở hữu bảng.
- Quyền tạo role hoặc cấp quyền cho người khác.
- Quyền superuser, DBA hoặc BYPASSRLS.

### 6.1. Phân biệt CONNECT, USAGE và SELECT

Trong PostgreSQL:

- CONNECT cho phép kết nối vào database.
- USAGE trên schema cho phép tra cứu/định danh các object trong schema theo quyền object tương ứng.
- SELECT trên view cho phép đọc kết quả view.
- SELECT trên bảng nguồn cho phép đọc trực tiếp bảng đó.

USAGE trên schema không tự cấp SELECT trên mọi object. SELECT trên view cũng không tự cấp SELECT trên tất cả bảng trong schema.

### 6.2. Quyền hiệu lực có thể đến từ nhiều nơi

Một role có thể nhận quyền qua:

- GRANT trực tiếp.
- Membership trong role khác.
- Quyền được cấp cho PUBLIC.
- Quyền mặc định của database/schema/object.
- Quyền ownership.
- Cơ chế đặc thù như ownership chaining hoặc security-definer execution.

Chỉ nhìn một lệnh GRANT mới thêm là chưa đủ. Phải kiểm tra quyền hiệu lực của tài khoản thật.

## 7. Mô hình role đề xuất trong PostgreSQL

~~~text
report_owner  NOLOGIN
    | sở hữu schema/view báo cáo
    | có SELECT tối thiểu trên bảng nguồn
    v
reporting.v_order_report
reporting.v_monthly_sales
    ^
    | GRANT SELECT
report_reader  NOLOGIN
    ^
    | membership
analyst_login  LOGIN
~~~

Ý nghĩa:

- report_owner: role sở hữu view, không dùng để đăng nhập hằng ngày.
- report_reader: role nhóm, chỉ nhận quyền đọc view.
- analyst_login: tài khoản cá nhân hoặc service account được gán membership vào report_reader.

Không dùng tài khoản superuser làm tài khoản dashboard. Không dùng cùng một tài khoản owner cho cả việc tạo view và truy vấn báo cáo thường ngày.

## 8. Cấp quyền theo từng bước trong PostgreSQL

Ví dụ dưới đây giả định database đã có schema app, hai bảng app.orders, app.customers và tài khoản triển khai có quyền quản trị phù hợp.

### 8.1. Tạo role

~~~sql
CREATE ROLE report_owner NOLOGIN;
CREATE ROLE report_reader NOLOGIN;
CREATE ROLE analyst_login LOGIN;
~~~

Không ghi mật khẩu thật vào migration hoặc source control. Cấp credential cho login bằng secret manager hoặc quy trình provisioning của môi trường.

### 8.2. Tạo schema báo cáo do report_owner sở hữu

~~~sql
CREATE SCHEMA reporting AUTHORIZATION report_owner;
~~~

Schema riêng giúp phân biệt object được công bố cho consumer với bảng nghiệp vụ.

### 8.3. Cấp quyền tối thiểu cho owner trên schema nguồn

~~~sql
GRANT USAGE ON SCHEMA app TO report_owner;

GRANT SELECT
ON TABLE app.orders, app.customers
TO report_owner;
~~~

Nếu view dùng thêm bảng ở schema khác, cấp USAGE trên schema đó và SELECT trên đúng bảng cần thiết. Không cấp SELECT ALL TABLES nếu view chỉ cần hai bảng.

report_owner không cần quyền UPDATE/DELETE trên bảng nghiệp vụ để tạo view đọc.

### 8.4. Tạo view dưới danh tính owner

Trong phiên triển khai có quyền phù hợp:

~~~sql
SET ROLE report_owner;

CREATE VIEW reporting.v_order_report AS
SELECT
    o.id AS order_id,
    o.created_at AS order_created_at,
    c.display_name AS customer_name,
    o.status AS order_status,
    o.total_amount
FROM app.orders AS o
JOIN app.customers AS c
    ON c.id = o.customer_id;

CREATE VIEW reporting.v_monthly_sales AS
SELECT
    date_trunc('month', o.created_at)::date AS sales_month,
    o.status AS order_status,
    COUNT(*)::bigint AS order_count,
    SUM(o.total_amount)::numeric(16,2) AS gross_amount
FROM app.orders AS o
WHERE o.status IN ('PAID', 'SHIPPED')
GROUP BY
    date_trunc('month', o.created_at)::date,
    o.status;

RESET ROLE;
~~~

View được tạo dưới role report_owner. Role này phải có quyền truy cập cần thiết vào bảng nguồn và schema nguồn.

Trong quy trình migration thực tế, có thể kết nối trực tiếp bằng role owner hoặc dùng cơ chế deploy role đã được kiểm soát. Không để tài khoản ứng dụng thường ngày sở hữu view.

### 8.5. Cấp quyền cho role đọc

~~~sql
REVOKE ALL ON SCHEMA reporting FROM PUBLIC;

REVOKE ALL
ON reporting.v_order_report, reporting.v_monthly_sales
FROM PUBLIC;

GRANT USAGE ON SCHEMA reporting TO report_reader;

GRANT SELECT
ON reporting.v_order_report, reporting.v_monthly_sales
TO report_reader;

GRANT report_reader TO analyst_login;
~~~

Nếu database đã thu hồi CONNECT khỏi PUBLIC, cấp CONNECT rõ cho role cần dùng:

~~~sql
GRANT CONNECT ON DATABASE reporting_db TO report_reader;
~~~

Tên database phải được thay bằng database thực tế.

### 8.6. Không cấp quyền bảng nguồn cho report_reader

Trong mô hình view mặc định của PostgreSQL, quyền truy cập các quan hệ nền của view được kiểm tra theo owner của view. Vì vậy, consumer có thể được cấp SELECT trên view mà không được cấp SELECT trực tiếp trên các bảng nguồn.

Đây là điểm quan trọng giúp view làm lớp công bố dữ liệu. Cơ chế này phụ thuộc semantics security của view; không áp dụng nguyên xi cho mọi DBMS.

## 9. Vì sao view owner và reader phải là hai role riêng?

Nếu tài khoản analyst vừa sở hữu view vừa truy vấn view, nó có thể có quyền quản trị hoặc quyền trên object mà consumer thông thường không cần.

Tách owner và reader giúp:

- Consumer không thể sửa định nghĩa view.
- Consumer không thể cấp quyền cho người khác.
- Tài khoản owner không cần LOGIN.
- Có thể audit rõ ai tạo object và ai chỉ đọc.
- Có thể thay đổi view qua migration mà không cấp DDL cho analyst.

Owner role nên được giữ tối thiểu: chỉ có SELECT trên các bảng nguồn cần thiết và quyền CREATE trên schema reporting. Không cấp BYPASSRLS hoặc superuser.

## 10. Quyền trên view và quyền trên bảng nguồn trong PostgreSQL

PostgreSQL view mặc định dùng semantics tương tự security definer cho việc kiểm tra quyền trên các quan hệ nền: quyền trên bảng nguồn được kiểm tra theo owner của view. Caller cần quyền phù hợp trên chính view và schema chứa view.

| Principal | Schema app | Bảng app.orders | View reporting.v_order_report |
|---|---|---|---|
| report_owner | USAGE | SELECT | OWNER |
| report_reader | Không cần USAGE nếu chỉ truy cập view | Không có SELECT | SELECT |
| analyst_login | Qua role report_reader | Không có SELECT | SELECT qua membership |

Bảng là mô hình quyền dự kiến trong môi trường không có grant khác qua PUBLIC hoặc role membership.

### 10.1. Schema nguồn không cần được mở cho consumer chỉ đọc view

Nếu view trong schema reporting truy vấn bảng app.orders, reader cần USAGE trên reporting và SELECT trên view. Trong mô hình PostgreSQL view mặc định, reader không cần quyền đọc trực tiếp app.orders.

Nếu view hoặc function có semantics khác, kiểm tra tài liệu và test với tài khoản thật.

### 10.2. Ownership là một quyền mạnh

Owner của view có thể ALTER hoặc DROP view và quản lý quyền trên object. Không cấp role owner cho người dùng báo cáo chỉ để họ chạy SELECT.

### 10.3. Quyền PUBLIC cần được kiểm tra

Một user không có GRANT trực tiếp vẫn có thể đọc bảng nếu quyền đã được cấp cho PUBLIC hoặc role khác mà user là thành viên. REVOKE từ một role không tự xóa các nguồn quyền còn lại.

## 11. Kiểm tra quyền hiệu lực

Sau khi cấp quyền, xác minh bằng catalog functions:

~~~sql
SELECT
    has_schema_privilege(
        'report_reader',
        'reporting',
        'USAGE'
    ) AS can_use_reporting_schema,
    has_table_privilege(
        'report_reader',
        'reporting.v_order_report',
        'SELECT'
    ) AS can_read_report_view,
    has_schema_privilege(
        'report_reader',
        'app',
        'USAGE'
    ) AS can_use_app_schema,
    has_table_privilege(
        'report_reader',
        'app.orders',
        'SELECT'
    ) AS can_read_orders;
~~~

Trong mô hình tối thiểu đã nêu, kết quả mong muốn:

| Kiểm tra | Kết quả |
|---|---|
| USAGE reporting | true |
| SELECT reporting.v_order_report | true |
| USAGE app | false (nếu không có grant khác) |
| SELECT app.orders | false (nếu không có grant khác) |

Các hàm has_*_privilege kiểm tra quyền hiệu lực, bao gồm các nguồn quyền có liên quan. Kết quả thực tế có thể khác nếu role có membership hoặc PUBLIC đã được cấp quyền.

### 11.1. Thử truy vấn bằng role reader

~~~sql
SET ROLE report_reader;

SELECT *
FROM reporting.v_order_report
LIMIT 10;

SELECT *
FROM app.orders;
-- Mong đợi: permission denied nếu không có quyền khác.

RESET ROLE;
~~~

Kiểm thử tốt hơn là mở connection bằng đúng tài khoản analyst_login của ứng dụng hoặc BI tool. SET ROLE là phép thử hữu ích trong phiên quản trị, nhưng không thay thế xác minh cấu hình đăng nhập, membership và database CONNECT của môi trường thật.

### 11.2. Kiểm tra role membership

~~~sql
SELECT
    member.rolname AS member_role,
    granted.rolname AS granted_role
FROM pg_auth_members AS m
JOIN pg_roles AS member
    ON member.oid = m.member
JOIN pg_roles AS granted
    ON granted.oid = m.roleid
WHERE member.rolname = 'analyst_login';
~~~

Nếu analyst_login thuộc một role khác có quyền SELECT trên app.orders, việc chỉ kiểm tra GRANT report_reader là chưa đủ.

### 11.3. Kiểm tra quyền PUBLIC và default privileges

Có thể dùng catalog/psql meta-command để kiểm tra ACL. Trong psql:

~~~text
\dp app.*
\dp reporting.*
\dn+
\du+
~~~

PUBLIC là pseudo-role đại diện mọi role. Quyền được cấp cho PUBLIC cần được xem như quyền cấp cho tất cả tài khoản trong database.

## 12. View lọc cột và lọc hàng

View có thể giới hạn dữ liệu theo hai cách:

- **Column projection:** chỉ chọn các cột được phép công bố.
- **Row predicate:** chỉ chọn những hàng thuộc phạm vi báo cáo.

Ví dụ view bỏ email và tax_identifier:

~~~sql
CREATE VIEW reporting.v_customer_directory AS
SELECT
    id AS customer_id,
    display_name AS customer_name
FROM app.customers;
~~~

View này không công bố các cột không được SELECT vào định nghĩa.

### 12.1. View lọc trạng thái

~~~sql
CREATE VIEW reporting.v_paid_orders AS
SELECT
    id AS order_id,
    customer_id,
    created_at,
    total_amount
FROM app.orders
WHERE status = 'PAID';
~~~

Reader chỉ nhìn thấy các hàng được view chọn khi truy vấn view. Tuy nhiên, phải kiểm tra mọi đường truy cập khác: reader có thể được cấp quyền trên bảng gốc, view khác hoặc function trả dữ liệu rộng hơn hay không.

### 12.2. Không xem view là cơ chế duy nhất cho tenant isolation

Một view cố định với điều kiện WHERE có thể giới hạn tập dữ liệu công bố. Nhưng nếu nhiều tenant dùng chung một view, điều kiện phải xác định tenant một cách đáng tin cậy. Không dựa vào một tham số session mà chính người dùng có thể tùy ý thay đổi rồi coi đó là cơ chế xác thực tenant.

Row-level security, danh tính database, trusted application context và thiết kế role cần được xem xét cùng nhau.

## 13. PostgreSQL Row-Level Security và view

RLS cho phép định nghĩa policy lọc hàng trên bảng:

~~~sql
ALTER TABLE app.orders ENABLE ROW LEVEL SECURITY;
~~~

Ví dụ policy minh họa theo một thuộc tính tenant:

~~~sql
CREATE POLICY orders_tenant_policy
ON app.orders
USING (tenant_id = current_setting('app.tenant_id', true)::bigint);
~~~

Policy này chỉ minh họa biểu thức so sánh tenant. Trong hệ thống thực, cần xác định nguồn app.tenant_id có đáng tin cậy không. Một custom setting mà client được tự do SET không phải bằng chứng xác thực tenant. Context phải được thiết lập từ backend tin cậy hoặc cơ chế danh tính được kiểm soát; cần có hành vi an toàn khi context không tồn tại.

### 13.1. RLS áp dụng dưới danh tính nào khi đọc view?

Với PostgreSQL view mặc định, quyền trên bảng nền và việc áp dụng RLS thường được đánh giá theo owner của view. Nếu view owner là owner của bảng, owner thường có thể bypass RLS, trừ khi bảng bật FORCE ROW LEVEL SECURITY. Role có BYPASSRLS cũng có thể bỏ qua policy.

Do đó, một view có WHERE hoặc một bảng đã bật RLS không tự động chứng minh reader chỉ nhìn thấy hàng theo policy của chính reader.

### 13.2. security_invoker

PostgreSQL 15 trở lên hỗ trợ tùy chọn:

~~~sql
CREATE VIEW reporting.v_orders_invoker
WITH (security_invoker = true)
AS
SELECT
    id AS order_id,
    tenant_id,
    total_amount
FROM app.orders;
~~~

Với security_invoker = true, quyền trên quan hệ nền và RLS được xét theo invoking user. Điều này có nghĩa caller cần các quyền cần thiết trên bảng/schema nguồn. Vì vậy, cấu hình này thường không phù hợp với mục tiêu ẩn hoàn toàn bảng gốc trong mô hình chỉ cấp SELECT trên view.

Hãy chọn semantics dựa trên mô hình quyền thực tế và kiểm thử bằng các role tenant khác nhau. Đừng bật tùy chọn này chỉ vì tên có chữ security.

### 13.3. security_barrier

PostgreSQL hỗ trợ view option security_barrier:

~~~sql
CREATE VIEW reporting.v_visible_orders
WITH (security_barrier = true)
AS
SELECT
    id AS order_id,
    tenant_id,
    total_amount
FROM app.orders
WHERE is_reportable = true;
~~~

Security barrier yêu cầu DBMS giữ ranh giới đánh giá điều kiện view trước các điều kiện từ caller không được coi là leakproof trong những trường hợp liên quan. Nó giúp giảm nguy cơ một hàm do caller cung cấp quan sát dữ liệu bị lọc qua side channel.

security_barrier không thay thế GRANT, RLS, kiểm soát function, quyền sở hữu hoặc kiểm tra tenant. Đây không phải nút bật bảo mật toàn diện.

### 13.4. Thiết kế RLS và view phải được kiểm thử cùng nhau

Kiểm tra ít nhất:

- Owner của view có phải owner bảng nguồn không?
- Owner có BYPASSRLS không?
- Bảng đã ENABLE RLS và có FORCE ROW LEVEL SECURITY khi cần chưa?
- Policy được đánh giá theo role nào trong đường truy cập view?
- Caller có quyền trực tiếp trên bảng không?
- Context tenant được xác thực và thiết lập ở đâu?
- Có view khác hoặc function nào bỏ qua ranh giới này không?

## 14. View có thể cho phép ghi dữ liệu không?

Một số view đơn giản có thể updatable. Ví dụ view trên một bảng với projection đơn giản có thể cho phép UPDATE tùy DBMS và cấu trúc query. View có JOIN, aggregate, GROUP BY hoặc DISTINCT thường bị hạn chế hoặc không tự động updatable.

Vì bài này xây view báo cáo, chỉ cấp SELECT:

~~~sql
GRANT SELECT ON reporting.v_order_report TO report_reader;
~~~

Không cấp INSERT, UPDATE, DELETE, TRUNCATE hoặc quyền DDL cho role reader.

### 14.1. WITH CHECK OPTION

Với view updatable có điều kiện, WITH CHECK OPTION có thể ngăn thao tác ghi qua view tạo hàng không còn thỏa predicate của view:

~~~sql
CREATE VIEW app.v_active_customers AS
SELECT id, display_name, is_active
FROM app.customers
WHERE is_active = true
WITH CHECK OPTION;
~~~

Cú pháp và mức hỗ trợ khác theo DBMS. CHECK OPTION không biến view thành hệ thống phân quyền đầy đủ; quyền ghi trên view và bảng vẫn phải được kiểm soát.

### 14.2. Read-only view và read-only transaction là hai khái niệm khác

Grant SELECT trên view hạn chế quyền object. Read-only transaction là thuộc tính của transaction/connection. Một BI tool có thể mở transaction read-only để giảm nguy cơ ghi, nhưng điều đó không thay thế GRANT và ownership.

## 15. Bảo vệ định nghĩa và dependency của view

View là một phần API nội bộ. Khi sửa view, có thể ảnh hưởng consumer.

### 15.1. Không đổi alias tùy tiện

Nếu dashboard đang dùng gross_amount, đổi alias thành revenue có thể làm dashboard lỗi. Hãy coi tên cột, kiểu dữ liệu, nullability và grain là contract.

### 15.2. Thay đổi tương thích

Khi thêm cột, kiểm tra consumer có phụ thuộc SELECT * hay không. Khi đổi kiểu hoặc ý nghĩa cột, cân nhắc tạo view version mới:

- v_order_report_v1
- v_order_report_v2

Giữ v1 trong thời gian consumer chuyển đổi rồi mới loại bỏ theo kế hoạch.

### 15.3. Dependency và quyền owner

Role owner cần quyền trên bảng nguồn để view hoạt động. Nếu bảng bị đổi tên, drop hoặc đổi kiểu, view có thể không còn hợp lệ hoặc cần migration tương ứng. Không cấp DDL trên schema nguồn cho reader để họ tự sửa dependency.

### 15.4. Không đưa function nguy hiểm vào view tùy tiện

View có thể gọi function. Nếu function chạy với quyền definer, có dynamic SQL hoặc side effect, bề mặt quyền của view có thể rộng hơn dự kiến. Kiểm tra function owner, SECURITY DEFINER, search_path và EXECUTE grants. Không coi mọi function được gọi trong view là vô hại.

## 16. Default privileges cho view mới

Trong PostgreSQL, có thể thiết lập quyền mặc định cho object được một role tạo trong schema:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE report_owner
IN SCHEMA reporting
GRANT SELECT ON TABLES TO report_reader;
~~~

Lưu ý:

- Default privileges áp dụng cho object được tạo bởi role được nêu, không tự áp dụng cho mọi owner.
- ON TABLES bao gồm nhiều loại relation như table và view trong PostgreSQL.
- Nếu schema reporting có thể chứa bảng nội bộ, grant mặc định có thể công bố rộng hơn mong muốn.
- Default privileges không tự sửa quyền của object đã tồn tại.
- Membership/role inheritance và PUBLIC vẫn phải được kiểm tra.

Nếu schema reporting chỉ chứa view được duyệt, default grant có thể tiện. Nếu schema có nhiều loại object, cấp quyền tường minh cho từng view thường dễ kiểm soát hơn.

## 17. Materialized view và quyền refresh

Ví dụ PostgreSQL:

~~~sql
CREATE MATERIALIZED VIEW reporting.mv_monthly_sales AS
SELECT
    date_trunc('month', created_at)::date AS sales_month,
    COUNT(*) AS order_count,
    SUM(total_amount) AS gross_amount
FROM app.orders
WHERE status = 'PAID'
GROUP BY date_trunc('month', created_at)::date;
~~~

Cấp đọc:

~~~sql
GRANT SELECT
ON reporting.mv_monthly_sales
TO report_reader;
~~~

Role reader không cần quyền SELECT trên bảng nguồn chỉ để đọc materialized view đã lưu, nếu không có nguồn quyền khác. Việc refresh là thao tác riêng, thường cần owner của materialized view trong PostgreSQL; không cấp quyền refresh cho analyst chỉ vì họ cần đọc dashboard.

### 17.1. Quy trình refresh

Một job vận hành có thể:

1. Kết nối bằng role được phép refresh.
2. Chạy REFRESH theo lịch.
3. Ghi log thời điểm bắt đầu/kết thúc và trạng thái.
4. Giám sát lỗi và độ trễ dữ liệu.
5. Thông báo hoặc hiển thị thời điểm dữ liệu được cập nhật.

### 17.2. Hiển thị freshness

Nếu dashboard dùng materialized view, nên công bố thời điểm dữ liệu được refresh, chẳng hạn qua một bảng metadata riêng hoặc cột trong pipeline. Người dùng cần biết báo cáo phản ánh dữ liệu đến thời điểm nào.

### 17.3. Bảo vệ bản sao dữ liệu

Materialized view có thể giữ lại thông tin nhạy cảm ngay cả khi bảng nguồn đã thay đổi hoặc bị xóa. Phải đưa nó vào quy trình retention, backup, quyền truy cập và xóa dữ liệu phù hợp.

## 18. Khác biệt giữa các DBMS

Mô hình cấp SELECT trên view và hạn chế bảng nguồn có thể triển khai trên nhiều DBMS, nhưng semantics quyền và cách thực thi không hoàn toàn giống nhau.

### 18.1. PostgreSQL

- View thông thường mặc định kiểm tra quyền trên bảng nền theo owner của view.
- Consumer cần quyền trên view và schema chứa view.
- security_invoker được hỗ trợ từ PostgreSQL 15.
- RLS cần được kiểm tra cùng owner, BYPASSRLS và FORCE ROW LEVEL SECURITY.
- security_barrier là option phục vụ ranh giới đánh giá predicate.
- Materialized view lưu kết quả và có quyền refresh riêng.

### 18.2. MySQL và MariaDB

MySQL/MariaDB hỗ trợ view với chế độ bảo mật:

~~~sql
CREATE
    ALGORITHM = UNDEFINED
    SQL SECURITY DEFINER
VIEW reporting.v_order_report AS
SELECT
    o.id AS order_id,
    o.created_at AS order_date,
    o.status AS order_status,
    o.total_amount
FROM app.orders AS o;
~~~

SQL SECURITY DEFINER dùng quyền của definer khi kiểm tra truy cập bảng nền; SQL SECURITY INVOKER dùng quyền của caller. Mặc định thường là DEFINER, nhưng hãy kiểm tra tài liệu phiên bản và metadata view.

Cấp quyền đọc view:

~~~sql
GRANT SELECT
ON reporting.v_order_report
TO 'analyst'@'%';
~~~

Các lưu ý:

- Definer phải được quản lý an toàn và không nên là tài khoản DBA rộng quyền.
- Tài khoản consumer cần SELECT trên view.
- Với SQL SECURITY INVOKER, caller cần quyền nền tương ứng.
- Kiểm tra definer tồn tại sau khi backup/restore hoặc migration.
- MySQL/MariaDB có quy tắc riêng về view updatability và CHECK OPTION.
- Tên tài khoản có host component; không bỏ qua phạm vi host khi cấp quyền.

### 18.3. SQL Server

Tạo view:

~~~sql
CREATE VIEW reporting.v_order_report
AS
SELECT
    o.Id AS order_id,
    o.CreatedAt AS order_date,
    c.DisplayName AS customer_name,
    o.Status AS order_status,
    o.TotalAmount AS total_amount
FROM dbo.Orders AS o
JOIN dbo.Customers AS c
    ON c.Id = o.CustomerId;
~~~

Cấp quyền:

~~~sql
GRANT SELECT
ON OBJECT::reporting.v_order_report
TO report_reader;
~~~

SQL Server có ownership chaining. Khi view và các object nguồn có cùng owner theo quy tắc ownership chain, caller có thể được phép truy vấn view mà không cần quyền trực tiếp trên bảng nền. Nếu ownership chain bị ngắt do owner khác nhau hoặc truy vấn truy cập object khác, kiểm tra lại quyền. Không giả định mọi dynamic SQL hoặc function đều nằm trong cùng chain.

Các schema/role nên có owner rõ ràng. SQL Server cũng có các cơ chế module signing và EXECUTE AS, nhưng cần thiết kế riêng; không dùng quyền sysadmin cho tài khoản báo cáo.

### 18.4. Oracle

Tạo view:

~~~sql
CREATE OR REPLACE VIEW reporting.v_order_report AS
SELECT
    o.id AS order_id,
    o.created_at AS order_date,
    c.display_name AS customer_name,
    o.status AS order_status,
    o.total_amount
FROM app.orders o
JOIN app.customers c
    ON c.id = o.customer_id;
~~~

Cấp quyền:

~~~sql
GRANT SELECT
ON reporting.v_order_report
TO report_reader;
~~~

Owner của view cần quyền phù hợp trên các object được tham chiếu; khi tạo view, quyền trên object nguồn cần được cấp trực tiếp cho owner theo quy tắc Oracle, không chỉ thông qua role. Consumer được cấp SELECT trên view có thể truy vấn theo quyền view được định nghĩa.

Oracle hỗ trợ WITH READ ONLY cho view phù hợp khi muốn ngăn DML qua view. Kiểm tra edition/version, grants và object dependency theo môi trường.

### 18.5. SQLite

SQLite có view:

~~~sql
CREATE VIEW v_order_report AS
SELECT
    o.id AS order_id,
    o.created_at AS order_date,
    o.status AS order_status,
    o.total_amount
FROM orders AS o;
~~~

Nhưng SQLite không có mô hình server-side user/role và GRANT/REVOKE như PostgreSQL, MySQL, SQL Server hay Oracle. Quyền truy cập file database và quyền của tiến trình ứng dụng là lớp bảo vệ chính. Ứng dụng có thể dùng authorizer API để giới hạn thao tác theo connection, nhưng đó là thiết kế ở lớp nhúng/application, không phải hệ thống role SQL tương đương.

SQLite view thường không tự updatable; có thể dùng INSTEAD OF triggers để định nghĩa hành vi ghi. Với báo cáo chỉ đọc, ứng dụng vẫn cần kiểm soát file, connection và API truy cập.

## 19. Các lỗi bảo mật thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Cấp SELECT trên toàn schema nguồn | Reader xem được cột/bảng không cần thiết | Grant trên view cụ thể |
| Dùng SELECT * trong view | Cột mới có thể vô tình bị lộ | Liệt kê cột |
| Cho analyst sở hữu view | Có thể ALTER/DROP hoặc cấp quyền | Owner role NOLOGIN |
| Dùng owner là superuser | View có thể truy cập quá rộng | Owner chuyên dụng, quyền nguồn tối thiểu |
| Quên quyền PUBLIC | Mọi role có thể được hưởng quyền | Audit và REVOKE phù hợp |
| Bỏ qua role membership | Quyền gián tiếp vẫn mở bảng gốc | Kiểm tra quyền hiệu lực |
| Nhầm security_barrier là authorization | Vẫn có thể cấu hình quyền sai | GRANT/RLS/ownership đúng |
| Nhầm RLS luôn chạy theo reader | View owner có thể là principal của RLS | Kiểm tra security_invoker và owner |
| Dùng session variable do client tự đặt làm tenant proof | Client có thể đổi phạm vi dữ liệu | Trusted context hoặc danh tính được xác thực |
| Cho quyền UPDATE trên view báo cáo | Consumer có thể ghi qua view updatable | Chỉ GRANT SELECT |
| Materialized view chứa dữ liệu nhạy cảm không được bảo vệ | Bản sao dữ liệu bị đọc ngoài ý muốn | Grant, retention và refresh controls |
| View gọi SECURITY DEFINER function không an toàn | Có thể mở rộng quyền truy cập | Audit function owner/search_path/EXECUTE |

## 20. Kiểm thử end-to-end với tài khoản báo cáo

Kiểm thử không chỉ xác nhận view trả dữ liệu. Cần chứng minh quyền hoạt động đúng.

### 20.1. Các trường hợp phải thành công

- Tài khoản report_reader kết nối được database.
- Tài khoản có thể tra cứu schema reporting.
- Tài khoản có thể SELECT view đã được cấp.
- Bộ lọc và alias trả đúng contract.
- View không lộ cột nhạy cảm.
- View trả đúng số hàng/grain theo dữ liệu fixture.

### 20.2. Các trường hợp phải bị từ chối

- SELECT trực tiếp app.orders.
- SELECT trực tiếp app.customers.
- INSERT/UPDATE/DELETE trên view báo cáo.
- CREATE/ALTER/DROP view hoặc bảng.
- GRANT quyền cho role khác.
- Đọc view khác chưa được cấp.
- Truy cập schema nội bộ không được công bố.

### 20.3. Kiểm thử bằng SQL

~~~sql
-- Chạy bằng analyst_login hoặc SET ROLE report_reader
SELECT * FROM reporting.v_order_report LIMIT 5;

-- Các câu sau phải bị từ chối trong mô hình tối thiểu
SELECT * FROM app.orders;
INSERT INTO reporting.v_order_report (...) VALUES (...);
UPDATE reporting.v_order_report SET ...;
DELETE FROM reporting.v_order_report;
~~~

Không cần thực hiện DML phá dữ liệu trong production để chứng minh quyền. Có thể kiểm thử trên database test hoặc dùng catalog functions để xác minh quyền bị từ chối.

### 20.4. Kiểm tra cột được công bố

PostgreSQL:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'reporting'
  AND table_name = 'v_order_report'
ORDER BY ordinal_position;
~~~

So sánh metadata với contract mong đợi. Đặc biệt kiểm tra không có email, tax_identifier hoặc cột nội bộ bị thêm ngoài ý muốn.

### 20.5. Kiểm tra dữ liệu đối chiếu

Nếu view một hàng mỗi order:

~~~sql
SELECT
    COUNT(*) AS report_rows,
    COUNT(DISTINCT order_id) AS distinct_orders
FROM reporting.v_order_report;
~~~

Hai số cần bằng nhau nếu order_id không NULL và view được thiết kế một hàng/order. Đối chiếu tổng tiền với nguồn trong cùng scope và snapshot.

## 21. Hiệu năng của view báo cáo

View không tự làm query nhanh. Hãy xem execution plan của câu SELECT qua view, không chỉ nhìn định nghĩa.

### 21.1. Index trên bảng nguồn

Ví dụ query lọc theo thời gian và trạng thái:

~~~sql
CREATE INDEX ix_orders_status_created_at
ON app.orders(status, created_at);
~~~

Index phù hợp phụ thuộc predicate, cardinality, phân bố dữ liệu và DBMS. Không tạo index chỉ vì một cột xuất hiện trong view; xem query thực tế và plan.

### 21.2. Đẩy bộ lọc vào query

Consumer:

~~~sql
SELECT *
FROM reporting.v_order_report
WHERE order_date >= TIMESTAMPTZ '2026-01-01 00:00:00+00';
~~~

Optimizer có thể đẩy predicate qua view khi an toàn. Nhưng function, cast hoặc cấu trúc query có thể làm việc dùng index khó hơn. Xem plan thay vì giả định.

### 21.3. Không tạo view quá rộng

Một view có nhiều JOIN, subquery, window function và aggregate có thể khó tối ưu cho mọi dashboard. Tách view theo grain và use case giúp query rõ hơn, đồng thời dễ cấp quyền theo mục đích.

### 21.4. Theo dõi consumer

Khi view được dùng bởi nhiều dashboard, một thay đổi nhỏ có thể ảnh hưởng nhiều query. Theo dõi query duration, rows scanned, plan regressions và consumer trước khi thay đổi logic.

## 22. Quy trình triển khai và thay đổi view

Một quy trình migration an toàn:

1. Xác định consumer và contract hiện tại.
2. Viết định nghĩa view với cột tường minh.
3. Cấp quyền nguồn tối thiểu cho owner.
4. Tạo/replace view bằng migration.
5. Cấp SELECT cho role reader.
6. Kiểm tra quyền hiệu lực và membership.
7. Chạy test đọc được view, không đọc được bảng nguồn.
8. Kiểm tra metadata, grain, NULL và aggregate.
9. Chạy execution plan trên dữ liệu đại diện.
10. Triển khai consumer và theo dõi lỗi.

### 22.1. Thêm cột

Thêm cột mới vào view có thể tương thích nếu consumer chỉ chọn cột tường minh. Consumer dùng SELECT * có thể thay đổi hành vi khi cột mới xuất hiện. Tránh thiết kế dashboard phụ thuộc vào thứ tự cột không được ghi thành contract.

### 22.2. Đổi kiểu hoặc ý nghĩa

Đổi NUMERIC sang FLOAT, đổi timestamp local sang timestamp with time zone hoặc đổi grain từ order sang item là thay đổi lớn hơn đổi tên. Cần versioning hoặc migration đồng bộ consumer.

### 22.3. Thu hồi view cũ

Trước khi DROP:

- Tìm consumer còn dùng không.
- Kiểm tra dependency của view khác.
- Thu hồi grants phù hợp.
- Có kế hoạch rollback hoặc compatibility window.
- Không drop bảng nguồn chỉ vì view đã thay thế một phần truy vấn.

## 23. Ví dụ hoàn chỉnh: cung cấp báo cáo chỉ đọc

Giả sử bảng nguồn đã tồn tại trong schema app. Script dưới minh họa thiết lập role, schema, view và quyền:

~~~sql
-- 1. Roles
CREATE ROLE report_owner NOLOGIN;
CREATE ROLE report_reader NOLOGIN;
CREATE ROLE analyst_login LOGIN;

-- 2. Schema
CREATE SCHEMA reporting AUTHORIZATION report_owner;

-- 3. Owner chỉ được đọc đúng bảng nguồn
GRANT USAGE ON SCHEMA app TO report_owner;
GRANT SELECT ON app.orders, app.customers TO report_owner;

-- 4. Tạo view dưới role owner
SET ROLE report_owner;

CREATE VIEW reporting.v_order_report AS
SELECT
    o.id AS order_id,
    o.created_at AS order_created_at,
    c.display_name AS customer_name,
    o.status AS order_status,
    o.total_amount
FROM app.orders AS o
JOIN app.customers AS c
    ON c.id = o.customer_id;

CREATE VIEW reporting.v_monthly_sales AS
SELECT
    date_trunc('month', o.created_at)::date AS sales_month,
    o.status AS order_status,
    COUNT(*)::bigint AS order_count,
    SUM(o.total_amount)::numeric(16,2) AS gross_amount
FROM app.orders AS o
WHERE o.status IN ('PAID', 'SHIPPED')
GROUP BY
    date_trunc('month', o.created_at)::date,
    o.status;

RESET ROLE;

-- 5. Chỉ công bố các view
REVOKE ALL ON SCHEMA reporting FROM PUBLIC;
REVOKE ALL ON reporting.v_order_report,
              reporting.v_monthly_sales
FROM PUBLIC;

GRANT USAGE ON SCHEMA reporting TO report_reader;
GRANT SELECT ON reporting.v_order_report,
                reporting.v_monthly_sales
TO report_reader;

-- 6. Gán role reader cho tài khoản đăng nhập
GRANT report_reader TO analyst_login;

-- 7. Nếu CONNECT không được cấp qua PUBLIC
GRANT CONNECT ON DATABASE reporting_db TO report_reader;
~~~

Đây là ví dụ cho database mới hoặc môi trường test có tên object chưa tồn tại. Trong migration production, xử lý idempotency, role đã tồn tại, ownership hiện tại và grants cũ theo quy trình riêng; không chạy lặp nguyên xi CREATE ROLE/CREATE SCHEMA.

### 23.1. Xác minh

~~~sql
SELECT
    has_table_privilege(
        'report_reader',
        'reporting.v_order_report',
        'SELECT'
    ) AS can_read_view,
    has_table_privilege(
        'report_reader',
        'app.orders',
        'SELECT'
    ) AS can_read_base_table;
~~~

Mong đợi can_read_view = true và can_read_base_table = false, với điều kiện không có quyền bổ sung qua PUBLIC hoặc membership khác.

### 23.2. Truy vấn báo cáo

~~~sql
SELECT
    sales_month,
    order_status,
    order_count,
    gross_amount
FROM reporting.v_monthly_sales
WHERE sales_month >= DATE '2026-01-01'
ORDER BY sales_month, order_status;
~~~

Tài khoản analyst_login sử dụng view đã công bố mà không cần biết JOIN nội bộ giữa orders và customers.

## 24. Bài tập thực hành có lời giải

### Bài 1. View thường lưu dữ liệu hay lưu định nghĩa?

**Đáp án:** view thường lưu định nghĩa truy vấn; khi được truy vấn, DBMS thực thi logic dựa trên bảng nguồn. Materialized view mới lưu kết quả đã tính.

### Bài 2. Vì sao nên dùng view cho báo cáo?

**Đáp án:** view tạo contract có tên, gom logic JOIN/filter và cho phép cấp quyền trên tập cột/hàng đã chọn thay vì mở toàn bộ bảng nguồn.

### Bài 3. Có nên dùng SELECT * trong view báo cáo?

**Đáp án:** không nên. Cột mới trong bảng nguồn có thể vô tình được công bố. Liệt kê cột và alias tường minh.

### Bài 4. Một view có cần ORDER BY để dashboard nhận đúng thứ tự không?

**Đáp án:** consumer phải chỉ định ORDER BY trong SELECT. View không nên được coi là bảo đảm thứ tự.

### Bài 5. Role NOLOGIN dùng để làm gì?

**Đáp án:** làm role nhóm hoặc role sở hữu object mà không cho đăng nhập trực tiếp. Tài khoản cá nhân/service được cấp membership phù hợp.

### Bài 6. Role reader cần quyền nào để đọc view trong PostgreSQL?

**Đáp án:** USAGE trên schema chứa view và SELECT trên view, cùng CONNECT database nếu database đã giới hạn CONNECT. Trong mô hình view mặc định, caller không cần SELECT trực tiếp trên bảng nền.

### Bài 7. Vì sao report_owner cần SELECT trên bảng nguồn?

**Đáp án:** PostgreSQL kiểm tra quyền truy cập quan hệ nền theo owner của view trong semantics mặc định. Owner cần quyền nguồn để view thực thi.

### Bài 8. Có nên dùng superuser làm owner của view?

**Đáp án:** không. Dùng role NOLOGIN chuyên dụng, chỉ cấp SELECT trên các bảng nguồn cần thiết và quyền CREATE phù hợp trên schema reporting.

### Bài 9. USAGE trên schema có cấp SELECT bảng không?

**Đáp án:** không. USAGE cho phép truy cập tên object trong schema theo các quyền object riêng; SELECT phải được cấp riêng.

### Bài 10. GRANT SELECT ON ALL TABLES IN SCHEMA có luôn an toàn không?

**Đáp án:** không. Nó có thể cấp quyền trên cả table và view trong schema. Chỉ dùng khi toàn bộ object trong schema đều được phép công bố; nếu không, grant từng view.

### Bài 11. Vì sao phải kiểm tra PUBLIC?

**Đáp án:** quyền cấp cho PUBLIC áp dụng cho mọi role. Một REVOKE khỏi report_reader không loại bỏ quyền mà role vẫn nhận qua PUBLIC.

### Bài 12. Vì sao kiểm tra membership?

**Đáp án:** analyst có thể là thành viên của role khác được cấp SELECT trên bảng gốc. Quyền hiệu lực là hợp của nhiều nguồn grant và ownership.

### Bài 13. View có thể lọc cột email không?

**Đáp án:** có. Chỉ đưa các cột được phép vào SELECT của view. Đồng thời kiểm tra reader không có đường truy cập khác tới bảng chứa email.

### Bài 14. View có tự bảo vệ tenant isolation không?

**Đáp án:** không tự động. Cần predicate đáng tin cậy, RLS hoặc mô hình danh tính/role phù hợp. Không dùng một session variable do client tự đặt làm bằng chứng tenant.

### Bài 15. PostgreSQL security_invoker có tác dụng gì?

**Đáp án:** từ PostgreSQL 15, view có thể dùng security_invoker để quyền trên quan hệ nền và RLS được xét theo caller. Caller cần quyền nền tương ứng, nên không phù hợp nếu muốn ẩn hoàn toàn bảng gốc.

### Bài 16. security_barrier có thay GRANT/RLS không?

**Đáp án:** không. Nó kiểm soát thứ tự đánh giá predicate liên quan tới hàm không leakproof; không thay thế quyền object hoặc row-level policy.

### Bài 17. View có thể ghi được không?

**Đáp án:** một số view đơn giản updatable tùy DBMS. View có JOIN/aggregate thường bị hạn chế. Với báo cáo chỉ đọc, chỉ cấp SELECT.

### Bài 18. WITH CHECK OPTION làm gì?

**Đáp án:** với view updatable có predicate, nó ngăn thao tác ghi qua view tạo hàng không thỏa điều kiện của view. Nó không thay thế GRANT hoặc RLS.

### Bài 19. Khi nào materialized view phù hợp?

**Đáp án:** khi query tính toán nặng, consumer đọc lặp lại và có thể chấp nhận dữ liệu cũ đến lần refresh. Phải kiểm soát quyền, lịch refresh và freshness.

### Bài 20. Reader có cần quyền refresh materialized view không?

**Đáp án:** không nếu họ chỉ cần đọc. Refresh là thao tác vận hành riêng, cấp cho role/job được kiểm soát.

### Bài 21. MySQL SQL SECURITY DEFINER nghĩa là gì?

**Đáp án:** quyền truy cập bảng nền được kiểm tra theo definer trong phạm vi semantics view. Definer phải được quản lý an toàn và không nên là tài khoản admin rộng quyền.

### Bài 22. SQL Server ownership chaining có vai trò gì?

**Đáp án:** khi owner của view và object nguồn khớp theo ownership chain, caller có thể truy vấn view mà không cần quyền trực tiếp trên bảng nguồn. Chain có thể bị ngắt khi owner khác nhau hoặc có dynamic SQL/module khác.

### Bài 23. SQLite có GRANT SELECT ON VIEW không?

**Đáp án:** SQLite không có mô hình user/role và GRANT/REVOKE server-side tương tự các DBMS server. Bảo vệ chủ yếu ở file, process và application/authorizer.

### Bài 24. Vì sao phải kiểm tra metadata view sau migration?

**Đáp án:** để phát hiện cột bị thêm/lộ, alias đổi, kiểu dữ liệu hoặc nullability thay đổi so với contract báo cáo.

### Bài 25. Test quyền tối thiểu cần chứng minh điều gì?

**Đáp án:** tài khoản báo cáo kết nối được, đọc được view được cấp, không đọc được bảng nguồn hoặc view khác, không ghi dữ liệu và không thể sửa/cấp quyền trên object.

## 25. Checklist trước khi công bố view báo cáo

1. Grain của mỗi hàng đã được xác định chưa?
2. View chỉ đưa ra cột cần thiết chưa?
3. Alias, kiểu dữ liệu, precision và nullability có ổn định không?
4. Có SELECT * hoặc cột nhạy cảm bị lộ không?
5. Predicate lọc hàng có đúng nghiệp vụ không?
6. Timezone và kỳ báo cáo đã được quy định rõ chưa?
7. View có JOIN gây nhân hàng hoặc aggregate sai không?
8. View owner có phải role NOLOGIN chuyên dụng không?
9. Owner chỉ có quyền cần thiết trên bảng nguồn không?
10. Owner có phải superuser, table owner hoặc BYPASSRLS không?
11. Reader có USAGE schema và SELECT đúng view không?
12. Reader có vô tình nhận SELECT bảng nguồn qua PUBLIC hoặc role membership không?
13. Có quyền DML/DDL nào được cấp ngoài ý muốn không?
14. RLS được đánh giá dưới danh tính nào?
15. security_invoker/security_barrier có được chọn theo semantics đã hiểu không?
16. Function trong view có SECURITY DEFINER hoặc side effect không?
17. Materialized view có dữ liệu nhạy cảm và freshness được kiểm soát không?
18. Tài khoản thật của BI/dashboard đã được kiểm thử chưa?
19. View metadata có khớp contract sau migration không?
20. Consumer và kế hoạch versioning/deprecation đã được xác định chưa?

## 26. Tổng kết

View là một lớp công bố dữ liệu hữu ích cho báo cáo. Nó cho phép gom logic truy vấn, định nghĩa rõ cột/hàng được công bố và tách quyền đọc khỏi các bảng nghiệp vụ.

- **Thiết kế view theo grain và contract:** liệt kê cột, đặt alias ổn định, kiểm soát NULL, kiểu và timezone; tránh SELECT *.
- **Tách schema và role:** owner NOLOGIN có quyền đọc tối thiểu trên nguồn; reader NOLOGIN chỉ nhận SELECT trên view; tài khoản cá nhân/service nhận membership.
- **Phân biệt quyền schema và quyền object:** USAGE không phải SELECT. Consumer cần quyền trên view, và quyền bảng nền được kiểm tra theo semantics của DBMS.
- **Kiểm tra quyền hiệu lực:** tính đến PUBLIC, role membership, ownership, default privileges và quyền gián tiếp.
- **Hiểu RLS và security options:** PostgreSQL view mặc định dùng quyền owner cho quan hệ nền; security_invoker thay đổi principal và thường yêu cầu quyền nguồn; security_barrier không thay GRANT/RLS.
- **Chỉ đọc thì chỉ cấp SELECT:** không cấp DML hoặc DDL cho role báo cáo. Materialized view cần quản lý refresh riêng.
- **Kiểm thử như một hợp đồng bảo mật:** xác nhận tài khoản thật đọc được view nhưng không thể truy cập bảng gốc, dữ liệu ngoài phạm vi hoặc thao tác ghi.
- **Quản lý thay đổi có chủ đích:** alias, grain, kiểu và nullability là contract của dashboard và BI consumer.

Một luồng triển khai rõ ràng là **bảng nghiệp vụ → role owner tối thiểu → view báo cáo → role reader → kiểm tra quyền hiệu lực → kiểm thử consumer**. Khi mỗi lớp chỉ có quyền cần thiết, báo cáo có thể sử dụng dữ liệu nhất quán mà không phải mở toàn bộ schema nghiệp vụ cho người đọc.
