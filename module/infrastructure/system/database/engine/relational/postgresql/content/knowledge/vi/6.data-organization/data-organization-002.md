# Schema như không gian tên và ranh giới tổ chức đối tượng trong PostgreSQL

Khi một cơ sở dữ liệu PostgreSQL có nhiều bảng, view, hàm và kiểu dữ liệu, việc đặt tất cả vào cùng một không gian tên dễ gây trùng tên và khiến quyền truy cập khó quản lý. PostgreSQL dùng **schema** để nhóm và đặt tên các đối tượng bên trong **một database**. Mỗi schema là một **namespace**: hai schema có thể cùng có bảng tên `customers` mà vẫn phân biệt được thông qua tên đầy đủ như `sales.customers` và `reporting.customers`.

Schema cũng là một **ranh giới tổ chức và phân quyền**: có thể quy định nhóm nào được tạo đối tượng, nhóm nào được sử dụng những đối tượng đã tồn tại, và ứng dụng nào nên thao tác qua schema nào. Nhưng schema **không phải database riêng**, cũng không tự tạo cách ly vật lý, tài nguyên hay bảo mật tuyệt đối.

Bài học minh họa cách tạo và dùng nhiều schema, hiểu `search_path`, phân quyền đúng tầng, tổ chức migration và tránh một số lỗi phát sinh khi ứng dụng hoặc nhiều nhóm cùng làm việc trong PostgreSQL.

## 1. Schema nằm ở đâu trong cấu trúc PostgreSQL?

Có thể hình dung các cấp:

~~~mermaid
flowchart TD
    C["PostgreSQL cluster / instance"] --> D1["Database: commerce"]
    C --> D2["Database: analytics"]
    D1 --> S1["Schema: sales"]
    D1 --> S2["Schema: reporting"]
    D1 --> S3["Schema: audit"]
    S1 --> T1["Table: customers"]
    S1 --> T2["Table: orders"]
    S2 --> T3["View: paid_revenue"]
    S3 --> T4["Table: change_events"]
~~~

Một **database** là tập đối tượng dữ liệu mà mỗi kết nối PostgreSQL lựa chọn khi đăng nhập. Bên trong database đó có nhiều **schema**. Mỗi schema chứa những đối tượng như:

- Bảng (`TABLE`), bảng phân vùng và bảng ngoại.
- View và materialized view.
- Sequence.
- Function, procedure, operator và aggregate.
- Type, domain và một số đối tượng khác.

Một schema không phải bản sao của database. Tạo schema mới **không** tạo thêm database, không tự tạo một PostgreSQL server riêng, và không cho phép kết nối tới database khác thông qua tên schema.

### So sánh database và schema

| Tiêu chí | Database | Schema |
| --- | --- | --- |
| Phạm vi | Thuộc một PostgreSQL cluster | Thuộc đúng một database |
| Ví dụ | `commerce`, `analytics` | `sales`, `reporting` |
| Cách client chọn | Khi mở connection, ví dụ `-d commerce` | Qua tên đầy đủ hoặc `search_path` trong connection |
| Đối tượng | Chứa schema và những đối tượng cấp database | Chứa bảng, view, hàm, kiểu dữ liệu... |
| Không gian tên | Các database có tên riêng trong cluster | Tên schema riêng trong database |
| Truy vấn cùng câu SQL | Không truy cập trực tiếp bảng database khác bằng cú pháp thông thường | Có thể `JOIN` bảng từ nhiều schema trong cùng database |
| Phân quyền | Có quyền `CONNECT`, `CREATE`, `TEMPORARY` ở cấp database | Có quyền `USAGE`, `CREATE` ở cấp schema |
| Cách ly dữ liệu | Có ranh giới database và kết nối riêng | Là ranh giới logic, không cô lập hoàn toàn |

Ví dụ PostgreSQL không hỗ trợ một tên bảng ba cấp kiểu `database.schema.table` để truy cập tùy ý sang database khác trong câu SQL thông thường. Khi cần dữ liệu giữa các database, phải có cơ chế rõ ràng như `postgres_fdw`, `dblink` hoặc luồng đồng bộ dữ liệu; đây là phạm vi khác với việc dùng schema.

## 2. Tên đầy đủ của đối tượng: schema.table

Giả sử có hai bảng:

~~~sql
CREATE SCHEMA sales;
CREATE SCHEMA reporting;

CREATE TABLE sales.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL
);

CREATE TABLE reporting.customers (
    customer_id bigint PRIMARY KEY,
    display_label text NOT NULL
);
~~~

Hai câu `CREATE TABLE` cùng dùng tên `customers` nhưng không xung đột, vì chúng thuộc hai schema khác nhau.

Khi truy vấn bằng **qualified name** (tên có schema):

~~~sql
SELECT customer_id, customer_name
FROM sales.customers;

SELECT customer_id, display_label
FROM reporting.customers;
~~~

PostgreSQL biết chính xác bảng nào được yêu cầu. Trong ứng dụng, cách viết đầy đủ như `sales.customers` hữu ích cho các câu SQL quan trọng, migration, báo cáo có nhiều schema hoặc công cụ quản trị.

### Các đối tượng khác cũng có schema

Ví dụ:

~~~sql
CREATE SEQUENCE sales.invoice_number_seq START WITH 1000;

CREATE VIEW reporting.customer_names AS
SELECT customer_id, customer_name
FROM sales.customers;
~~~

Tên `sales.invoice_number_seq` và `reporting.customer_names` cũng dùng namespace. Với function có overload, PostgreSQL còn xét **tên hàm cùng kiểu tham số**, vì vậy không nên chỉ nhìn tên chữ rồi giả định không có xung đột.

### Không thể tạo hai bảng trùng tên trong cùng một schema

~~~sql
-- Bảng sales.customers đã tồn tại nên câu này sẽ lỗi.
CREATE TABLE sales.customers (
    id integer PRIMARY KEY
);
~~~

Thông báo cụ thể tùy phiên bản và đối tượng đang có, nhưng bản chất là **namespace không cho phép hai quan hệ cùng tên mà xung đột trong cùng schema**. Nếu thật sự cần hai bảng có vai trò khác nhau, chọn tên khác hoặc schema khác tùy ranh giới nghiệp vụ.

## 3. Vai trò của schema public

Khi tạo một database PostgreSQL thông thường, có một schema tên `public`. Nếu người dùng chạy:

~~~sql
CREATE TABLE tasks (
    task_id bigint PRIMARY KEY,
    task_name text NOT NULL
);
~~~

mà không ghi schema, bảng có thể được tạo ở `public.tasks` theo `search_path` của phiên và quyền của role. Nhưng **không được mặc định mọi câu CREATE không có schema đều luôn vào public**: điều đó còn phụ thuộc `search_path` và quyền CREATE.

Một số điều cần phân biệt:

- `public` (chữ thường) là **tên schema** thường có sẵn.
- `PUBLIC` (chữ hoa trong câu `GRANT ... TO PUBLIC`) là **pseudo-role đại diện cho tất cả các role**.
- `public` schema không có nghĩa “mọi người luôn được tạo và đọc mọi đối tượng”.

Trong PostgreSQL 15 trở lên, database mới có các mặc định quyền trên schema `public` khác so với nhiều bản cũ: mặc định thường không cho tất cả role tùy ý tạo đối tượng tại đó. Database nâng cấp từ phiên bản cũ hoặc được cấu hình riêng vẫn có thể giữ quyền rộng. **Luôn kiểm tra quyền thực tế**, không suy đoán chỉ từ version.

Có thể chọn dùng `public` cho bài thử nhỏ, nhưng khi xây ứng dụng nhiều module hoặc nhiều nhóm, việc tạo schema có tên ý nghĩa như `sales`, `billing`, `audit` giúp quản lý đối tượng rõ ràng hơn.

## 4. search_path: cách PostgreSQL tìm tên không có schema

Khi viết:

~~~sql
SELECT *
FROM customers;
~~~

PostgreSQL phải xác định `customers` thuộc schema nào. Cơ chế này dựa trên **`search_path`**, danh sách namespace mà phiên truy vấn xét đến khi tìm tên không có schema.

Xem cấu hình:

~~~sql
SHOW search_path;

SELECT
    current_schema() AS creation_schema,
    current_schemas(true) AS effective_search_schemas;
~~~

Giá trị mặc định thường có dạng:

~~~text
"$user", public
~~~

`"$user"` là placeholder cho schema có tên trùng với role hiện tại khi schema đó tồn tại và người dùng có quyền phù hợp. Nếu không có schema đó, PostgreSQL bỏ qua khi tìm đối tượng. `public` là schema tiếp theo trong danh sách mặc định thường gặp.

### Cách search_path xử lý hai bảng cùng tên

Giả sử `sales.customers` và `reporting.customers` đều tồn tại:

~~~sql
SET search_path TO reporting, sales;

SELECT *
FROM customers;
~~~

Tên `customers` trong ví dụ này được phân giải tới `reporting.customers` vì `reporting` đứng trước `sales` và có bảng phù hợp.

Đổi thứ tự:

~~~sql
SET search_path TO sales, reporting;

SELECT *
FROM customers;
~~~

Cùng câu `SELECT * FROM customers` bây giờ nhắm tới `sales.customers`. Đây là một dạng **thay đổi ý nghĩa SQL mà không cần sửa văn bản truy vấn**.

Khi muốn chắc chắn, dùng tên đầy đủ:

~~~sql
SELECT *
FROM sales.customers;
~~~

Lệnh này không phụ thuộc thứ tự `sales` và `reporting` trong `search_path`, miễn role có quyền thích hợp trên schema và bảng.

### Cách chọn schema khi CREATE đối tượng

Trong truy vấn `CREATE TABLE customers (...)` không có schema, PostgreSQL thường dùng **schema hợp lệ đầu tiên trong search path** làm nơi tạo. Có thể quan sát bằng `current_schema()`.

Nếu schema đầu tiên được chọn không cho role quyền `CREATE`, lệnh có thể lỗi quyền; PostgreSQL không nhất thiết tự chuyển sang một schema khác có quyền chỉ vì bạn mong vậy. Đối với migration, nên dùng tên đầy đủ hoặc cấu hình search path một cách có chủ đích thay vì dựa vào mặc định.

### Khôi phục search_path sau thử nghiệm

~~~sql
RESET search_path;
~~~

`RESET` đưa giá trị về thiết lập được thừa hưởng của session, **không nhất thiết là chuỗi mặc định của mọi PostgreSQL installation**, vì role hoặc database có thể đã cấu hình giá trị riêng.

## 5. Phân biệt SET, SET LOCAL và cấu hình dài hạn

Có nhiều cách thay đổi `search_path`:

~~~sql
-- Áp dụng trong session hiện tại.
SET search_path TO sales, reporting;

-- Kiểm tra giá trị hiện tại.
SHOW search_path;

-- Trả về thiết lập session thừa hưởng.
RESET search_path;
~~~

Khi chỉ cần áp dụng trong một transaction:

~~~sql
BEGIN;

SET LOCAL search_path TO sales, pg_catalog;

-- Những câu SQL trong transaction này dùng search_path trên.
SELECT * FROM customers;

COMMIT;
~~~

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại; sau khi transaction kết thúc, thiết lập session trước đó trở lại. Đây là lựa chọn khi cần cô lập cấu hình cho một đơn vị công việc, nhưng **không được dùng để trông chờ duy trì schema cho một transaction khác trong connection pool**.

Quản trị viên cũng có thể đặt giá trị mặc định cho role hoặc database:

~~~sql
-- Minh họa cú pháp; cần quyền quản trị phù hợp.
ALTER ROLE app_reader SET search_path = sales, public;
ALTER DATABASE commerce SET search_path = sales, public;
~~~

Những câu này chỉ minh họa; `app_reader` và `commerce` phải thực sự tồn tại. Các thiết lập mặc định thường áp dụng cho **kết nối mới**, không tự thay đổi mọi session đang mở.

### search_path còn ảnh hưởng những gì?

Ngoài bảng, PostgreSQL sử dụng schema resolution cho nhiều loại đối tượng như view, sequence, function, type và operator. Việc phụ thuộc search path làm câu SQL ngắn hơn, nhưng cũng tăng nguy cơ trùng tên hoặc bị định tuyến tới đối tượng không mong muốn.

Riêng `pg_catalog` chứa nhiều đối tượng hệ thống và thường được tìm tự động nếu không ghi trong `search_path`. Schema temporary của session cũng có quy tắc ưu tiên riêng đối với tên quan hệ/kiểu. Vì vậy kết quả phân giải không đơn giản là “chỉ tìm đúng hai schema người dùng viết” trong mọi tình huống.

## 6. Bài thực hành có ba schema: sales, reporting, audit

Tạo một **database lab tách biệt** (ví dụ `schema_lab`), sau đó kết nối tới database đó. Các lệnh sau chỉ chạy một lần khi chưa có những schema cùng tên trong lab:

~~~sql
CREATE SCHEMA lab_sales;
CREATE SCHEMA lab_reporting;
CREATE SCHEMA lab_audit;
~~~

Ba namespace có trách nhiệm:

| Schema | Mục đích |
| --- | --- |
| `lab_sales` | Dữ liệu giao dịch cốt lõi: khách hàng, đơn hàng |
| `lab_reporting` | View hoặc materialized view phục vụ báo cáo |
| `lab_audit` | Các bảng ghi sự kiện/audit thuộc bài thực hành |

### Tạo bảng giao dịch

~~~sql
CREATE TABLE lab_sales.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE lab_sales.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lab_sales.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total numeric(12, 2) NOT NULL
        CHECK (total >= 0)
);

INSERT INTO lab_sales.customers
    (customer_id, customer_name, city)
VALUES
    (1, 'An', 'HCM'),
    (2, 'Binh', 'HAN'),
    (3, 'Chi', 'HCM');

INSERT INTO lab_sales.orders
    (order_id, customer_id, status, total)
VALUES
    (101, 1, 'paid', 100.00),
    (102, 1, 'paid', 250.00),
    (103, 2, 'pending', 300.00),
    (104, 3, 'paid', 120.00);
~~~

Các bảng thuộc `lab_sales`, dù chúng có quan hệ khóa ngoại và cùng tham gia những câu JOIN.

### Đặt view báo cáo ở schema khác

~~~sql
CREATE VIEW lab_reporting.paid_revenue AS
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total), 0)::numeric(12, 2) AS revenue
FROM lab_sales.customers AS c
LEFT JOIN lab_sales.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id, c.customer_name;
~~~

Truy vấn:

~~~sql
SELECT *
FROM lab_reporting.paid_revenue
ORDER BY customer_id;
~~~

Kết quả mong đợi:

| customer_id | customer_name | paid_order_count | revenue |
| ---: | --- | ---: | ---: |
| 1 | An | 2 | 350.00 |
| 2 | Binh | 0 | 0.00 |
| 3 | Chi | 1 | 120.00 |

View được đặt trong `lab_reporting`, còn bảng gốc nằm trong `lab_sales`. PostgreSQL cho phép **truy vấn và liên kết xuyên schema trong cùng database**, miễn các ràng buộc quyền và điều kiện thực thi đáp ứng.

Trong ví dụ, điều kiện trạng thái đặt tại `ON` để giữ cả khách hàng không có đơn `paid`. `COUNT(o.order_id)` không đếm hàng `NULL` do `LEFT JOIN` tạo ra.

### Dùng schema audit cho đối tượng có trách nhiệm riêng

~~~sql
CREATE TABLE lab_audit.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_name text NOT NULL,
    entity_id integer NOT NULL,
    event_type text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);
~~~

Bảng audit được tổ chức ở schema khác, nhưng **schema không tự ghi audit event**. Ứng dụng, trigger hoặc một quy trình được thiết kế riêng phải tạo bản ghi theo chính sách audit. Đặt bảng trong `lab_audit` giúp phân biệt mục đích và quản lý quyền dễ hơn.

## 7. Hai schema có thể cùng có tên bảng mà không xung đột

Tạo một bảng đồng tên trong `lab_reporting` để minh họa namespace:

~~~sql
CREATE TABLE lab_reporting.customers (
    customer_id integer PRIMARY KEY,
    display_label text NOT NULL
);

INSERT INTO lab_reporting.customers
    (customer_id, display_label)
VALUES
    (1, 'Khach hang nhom A'),
    (2, 'Khach hang nhom B');
~~~

Truy vấn có schema rõ ràng:

~~~sql
SELECT customer_id, customer_name
FROM lab_sales.customers
ORDER BY customer_id;

SELECT customer_id, display_label
FROM lab_reporting.customers
ORDER BY customer_id;
~~~

Cùng tên `customers` nhưng hai bảng khác nhau về cấu trúc và dữ liệu. Để kiểm tra `search_path`:

~~~sql
SET search_path TO lab_reporting, lab_sales;

SELECT customer_id, display_label
FROM customers;

SET search_path TO lab_sales, lab_reporting;

SELECT customer_id, customer_name
FROM customers;

RESET search_path;
~~~

Đây là lý do **không nên dựa vào tên ngắn** trong các truy vấn/migration cần tính chính xác cao. Nếu sau này có schema mới đặt trước trong search path, câu SQL cũ có thể tìm thấy một đối tượng khác.

## 8. Schema giúp nhóm đối tượng nhưng không cô lập dữ liệu vật lý

Trong ví dụ ba schema, PostgreSQL vẫn dùng:

- Cùng instance và hệ thống quản lý transaction.
- Cùng database và một số tài nguyên vận hành chung.
- Cùng cơ chế WAL/backup theo kiến trúc của database/cluster.
- Cùng hệ thống catalog để quản lý metadata của đối tượng.
- Cùng query planner, có thể thực hiện `JOIN` giữa các schema.

Vì vậy schema thích hợp cho **tổ chức logic và quản lý quyền**, nhưng không mặc nhiên đảm bảo:

- Phân chia CPU/bộ nhớ/IO độc lập cho từng schema.
- Backup/restore hoàn toàn độc lập cho mọi đối tượng của schema.
- Cách ly rủi ro của DDL hoặc transaction đang dùng tài nguyên chung.
- Cấm mọi truy vấn chéo nếu role vẫn có quyền cần thiết.
- Ranh giới tenant đủ an toàn mà không có kiểm soát truy cập.

Nếu cần sự cách ly mạnh hơn về quản trị, vận hành hoặc vòng đời dữ liệu, phải cân nhắc database riêng, cluster riêng hoặc hạ tầng khác tùy yêu cầu.

## 9. Phân quyền hai tầng: schema và object

PostgreSQL quản lý quyền ở **schema** và **đối tượng bên trong schema**. Đây là điểm cần nhớ nhất khi dùng schema làm ranh giới tổ chức.

Quyền schema quan trọng:

| Quyền | Ý nghĩa |
| --- | --- |
| `USAGE` | Cho phép tham chiếu/tìm các đối tượng trong schema theo cơ chế quyền |
| `CREATE` | Cho phép tạo đối tượng mới trong schema |

Quyền trên bảng lại là một tầng khác, ví dụ `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `REFERENCES`, `TRIGGER`.

**Có `USAGE` trên schema không tự cho phép `SELECT` mọi bảng trong schema.** Tương tự, có `SELECT` trên bảng mà thiếu `USAGE` trên schema thường vẫn không thể tham chiếu bảng đó theo cách thông thường.

### Ví dụ role chỉ đọc

Trong môi trường lab và bằng tài khoản có quyền quản lý:

~~~sql
CREATE ROLE lab_sales_reader NOLOGIN;

REVOKE ALL ON SCHEMA lab_sales FROM PUBLIC;

GRANT USAGE ON SCHEMA lab_sales
TO lab_sales_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA lab_sales
TO lab_sales_reader;
~~~

Ý nghĩa:

1. `lab_sales_reader` là role nhóm không đăng nhập trực tiếp (`NOLOGIN`).
2. `REVOKE ALL ... FROM PUBLIC` loại các quyền schema đang được cấp rộng cho pseudo-role PUBLIC, nếu có.
3. `GRANT USAGE` cho phép nhóm tham chiếu đối tượng trong `lab_sales`.
4. `GRANT SELECT ON ALL TABLES` cấp đọc các bảng/view phù hợp **đang tồn tại** trong schema tại thời điểm chạy.

Để một người thực tế dùng quyền nhóm, quản trị viên cần cấp membership cho role đăng nhập phù hợp, ví dụ qua `GRANT lab_sales_reader TO some_login_role` sau khi role đó được tạo và xác minh. Quyền có thể được kế thừa hoặc yêu cầu `SET ROLE` tùy thuộc cấu hình membership/role.

### Ví dụ role ghi

~~~sql
CREATE ROLE lab_sales_writer NOLOGIN;

GRANT USAGE ON SCHEMA lab_sales
TO lab_sales_writer;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA lab_sales
TO lab_sales_writer;
~~~

Một role có quyền ghi bảng không nhất thiết có quyền thay đổi lược đồ. Nếu không cấp `CREATE` trên schema và không sở hữu bảng, role đó không tự có quyền tạo bảng hoặc chạy mọi lệnh `ALTER TABLE`.

Trong hệ thống thật, có thể tách:

- **Migrator/owner:** chịu trách nhiệm tạo và thay đổi schema/DDL.
- **Application writer:** chỉ dùng các quyền DML cần thiết.
- **Report reader:** chỉ đọc bảng hoặc view đã cho phép.
- **Audit reader:** được cấp quyền đọc audit theo chính sách riêng.

Sự phân chia này giúp giới hạn thiệt hại khi ứng dụng hoặc thông tin đăng nhập bị lộ.

### Quyền CREATE ở cấp database khác CREATE ở cấp schema

Để **tạo schema mới** trong database, role cần quyền thích hợp ở cấp database (thường là `CREATE ON DATABASE`). Để **tạo bảng trong một schema đã tồn tại**, role cần quyền `CREATE ON SCHEMA` hoặc là chủ sở hữu đối tượng/được quyền tương ứng.

Ví dụ cú pháp minh họa:

~~~sql
-- Cấp quyền tạo schema mới trong database cho một role
-- đã tồn tại, khi chính sách cho phép.
GRANT CREATE ON DATABASE commerce TO app_migrator;

-- Cấp quyền tạo đối tượng trong schema sales.
GRANT CREATE ON SCHEMA sales TO app_migrator;
~~~

`commerce`, `sales` và `app_migrator` ở đây là tên minh họa. Không cấp rộng quyền `CREATE` cho mọi tài khoản chỉ để giải quyết lỗi một lần chạy migration.

## 10. Default privileges: quyền cho bảng sẽ tạo trong tương lai

`GRANT SELECT ON ALL TABLES IN SCHEMA ...` chỉ áp dụng với các bảng/view hiện có tại thời điểm lệnh chạy. Khi một migration tạo bảng mới, bảng đó **không tự nhận tất cả các quyền đã grant trước đây**.

PostgreSQL có `ALTER DEFAULT PRIVILEGES` để đặt quyền mặc định cho các đối tượng được tạo trong tương lai. Ví dụ, nếu role `lab_migrator` sẽ là role thực sự tạo bảng:

~~~sql
-- Minh họa: lab_migrator cần tồn tại và người thực thi
-- phải có quyền cấu hình default privileges cho role này.
ALTER DEFAULT PRIVILEGES
    FOR ROLE lab_migrator
    IN SCHEMA lab_sales
    GRANT SELECT ON TABLES TO lab_sales_reader;
~~~

Ý nghĩa:

- Chỉ ảnh hưởng đối tượng **tạo sau thời điểm cấu hình**, không retroactively cấp quyền trên bảng cũ.
- Gắn với **role tạo đối tượng** (`FOR ROLE lab_migrator`), chứ không chỉ với tên schema.
- Không đồng nghĩa quyền của một role nhóm khác tự được dùng để xác định default privileges khi thành viên tạo bảng.
- Có thể cần cấu hình riêng cho `SEQUENCES`, `FUNCTIONS` hoặc kiểu đối tượng khác, vì chúng không cùng một tập quyền với TABLES.

Khi dùng Flyway, Liquibase hoặc các công cụ migration, nên xác định chính xác role nào đang chạy migration để cài default privileges phù hợp.

## 11. Chủ sở hữu schema khác chủ sở hữu bảng

Schema và từng đối tượng bên trong có **owner riêng**. Người tạo schema thường sở hữu schema; tuy nhiên việc được phép tạo bảng trong schema không có nghĩa mọi bảng sẽ thuộc về owner của schema.

Ví dụ:

~~~sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS schema_owner
FROM pg_namespace AS n
WHERE n.nspname = 'lab_sales';
~~~

Và xem owner bảng:

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname = 'lab_sales'
ORDER BY tablename;
~~~

Khi quản lý migration, nên quy định role owner nhất quán để tránh tình huống một bảng do tài khoản A tạo, bảng khác do tài khoản B tạo, khiến thao tác sửa DDL bị thiếu quyền.

`GRANT ALL PRIVILEGES` trên bảng không làm người được cấp trở thành **owner** của bảng; một số thao tác DDL và quyền quản lý ownership vẫn có điều kiện riêng.

## 12. search_path là một vấn đề bảo mật, không chỉ tiện gõ SQL

Nếu một ứng dụng dùng tên hàm, bảng hoặc type **không có schema** và đưa schema mà người dùng không tin cậy có quyền `CREATE` lên đầu `search_path`, người đó có thể tạo đối tượng đồng tên để làm thay đổi cách PostgreSQL phân giải tên.

Vì vậy, việc đưa một schema vào search path có ý nghĩa **tin cậy các đối tượng có thể được tạo trong đó**. Đối với ứng dụng cần bảo mật cao:

- Không cấp `CREATE` trong schema mà ứng dụng tìm trước cho những role không tin cậy.
- Ưu tiên tên đối tượng có schema rõ ràng trong SQL quan trọng.
- Kiểm soát cấu hình `search_path` của connection pool, migration và routine.
- Không cho đầu vào người dùng tùy ý quyết định tên schema rồi nối vào SQL.
- Kiểm tra quyền thực tế trên `public`, đặc biệt ở database được nâng cấp hoặc tạo từ template cũ.

### SECURITY DEFINER cần chú ý

Một function khai báo `SECURITY DEFINER` có thể chạy với quyền của **owner function** thay vì người gọi. Nếu function này dựa vào search path không an toàn, đối tượng được phân giải sai có thể tạo lỗ hổng nghiêm trọng.

Ví dụ cấu trúc an toàn hơn là dùng tên bảng đầy đủ và cố định path của function:

~~~sql
CREATE OR REPLACE FUNCTION lab_reporting.customer_count()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, lab_sales, pg_temp
AS $$
    SELECT COUNT(*) FROM lab_sales.customers
$$;
~~~

Đây là ví dụ cú pháp, **không phải khuyến nghị tạo SECURITY DEFINER cho mọi chức năng đếm**. Khi dùng thật, cần đánh giá owner, quyền `EXECUTE`, quyền truy cập tới các bảng, xử lý đối tượng temporary và toàn bộ đường đi của hàm. Nếu không cần nâng quyền, ưu tiên `SECURITY INVOKER` (hành vi thông thường).

`pg_catalog` có quy tắc tìm kiếm hệ thống riêng, còn `pg_temp` cần được đặt cẩn trọng để đối tượng tạm không che khuất đối tượng quan trọng. Cố định `search_path` giúp tránh việc caller điều khiển gián tiếp môi trường phân giải tên của function.

## 13. Schema có phải ranh giới bảo mật tuyệt đối không?

**Không.** Schema có quyền truy cập riêng nhưng vẫn sống trong cùng database. Một số giới hạn cần hiểu:

- Role có đủ quyền vẫn có thể `JOIN` bảng từ `sales` với bảng từ `audit`.
- Role sở hữu đối tượng có các đặc quyền quản lý khác với role chỉ được cấp `SELECT`.
- Superuser và các quyền quản trị mạnh có thể vượt nhiều cơ chế phân quyền thông thường.
- Schema không tự động áp dụng **row-level security (RLS)** cho tất cả các bảng.
- Cùng schema không có nghĩa các bảng bắt buộc dùng chung owner hoặc permission.
- Các function và view có những quy tắc thực thi quyền riêng cần xem xét, không nên dùng như cửa hậu mở dữ liệu.

Nếu muốn phân tách dữ liệu giữa nhiều khách hàng/tenant, phải thiết kế quyền, cơ chế tenant routing, migration, RLS nếu phù hợp, giám sát và kiểm thử truy cập chéo. **Chỉ đặt tenant vào schema khác không đảm bảo chống lộ dữ liệu** nếu role ứng dụng vẫn có quyền đọc nhiều schema.

## 14. Tổ chức theo miền nghiệp vụ hay theo loại kỹ thuật?

Có hai cách chia schema thường gặp.

### Theo miền nghiệp vụ

~~~text
sales.orders
sales.customers

billing.invoices
billing.payments

identity.users
identity.sessions
~~~

Ưu điểm: đối tượng liên quan nghiệp vụ được đặt gần nhau, owner/migration có thể giao theo module và quyền được phân theo trách nhiệm.

### Theo loại đối tượng hoặc mục đích sử dụng

~~~text
core.customers
core.orders

reporting.daily_revenue
reporting.customer_spend

audit.entity_events
audit.access_events
~~~

Ưu điểm: phân biệt bảng gốc, lớp báo cáo và nhật ký. Tuy nhiên một schema `core` quá lớn có thể làm các nhóm phụ thuộc lẫn nhau.

**Không có một sơ đồ schema tối ưu cho mọi dự án.** Cách chia nên dựa vào quyền truy cập, số lượng đối tượng, vòng đời migration, ranh giới trách nhiệm và chi phí vận hành.

### Những câu hỏi nên đặt khi tạo schema

1. Nhóm đối tượng có chung owner và vòng đời không?
2. Có cần phân quyền khác nhau giữa nhóm này với nhóm khác không?
3. Các bảng có cần tham chiếu khóa ngoại và JOIN thường xuyên không?
4. Migration của một nhóm có được triển khai độc lập không?
5. Công cụ backup, restore, BI, ORM và CI có hỗ trợ cách tổ chức này không?
6. Có nguy cơ tên đối tượng bị che khuất bởi `search_path` không?
7. Một schema mới giải quyết vấn đề thật hay chỉ làm tăng số namespace phải quản lý?

Không nên tạo schema riêng cho mọi bảng nếu điều đó không tạo được lợi ích tổ chức hoặc phân quyền tương xứng.

## 15. Khóa ngoại và truy vấn JOIN qua các schema

Vì các schema nằm trong cùng database, có thể khai báo khóa ngoại chéo schema:

~~~sql
CREATE SCHEMA lab_billing;

CREATE TABLE lab_billing.invoices (
    invoice_id integer PRIMARY KEY,
    order_id integer NOT NULL UNIQUE
        REFERENCES lab_sales.orders(order_id),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0)
);
~~~

Một truy vấn tổng hợp:

~~~sql
SELECT
    i.invoice_id,
    o.order_id,
    c.customer_name,
    i.amount
FROM lab_billing.invoices AS i
JOIN lab_sales.orders AS o
    ON o.order_id = i.order_id
JOIN lab_sales.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY i.invoice_id;
~~~

Nếu chưa thêm bản ghi hóa đơn, kết quả là tập rỗng; truy vấn vẫn hợp lệ. Có thể chèn thử trong database lab:

~~~sql
INSERT INTO lab_billing.invoices
    (invoice_id, order_id, amount)
VALUES (9001, 101, 100.00);
~~~

Chạy lại query sẽ trả hóa đơn 9001 của đơn 101, khách hàng An.

### Cross-schema foreign key có ảnh hưởng tới tổ chức?

Có. Schema giúp đặt namespace nhưng **không tách rời dependency**. Nếu xóa hoặc thay đổi `lab_sales.orders`, đối tượng `lab_billing.invoices` có thể bị ảnh hưởng bởi ràng buộc tham chiếu. Một schema không thể tùy ý được “deploy độc lập” nếu schema khác đang có foreign key/view/function phụ thuộc vào nó.

Khi thiết kế các module phải triển khai thực sự độc lập, cần cân nhắc quản lý dependency, thứ tự migration hoặc thay đổi kiến trúc, không mặc định schema đã giải quyết vấn đề.

## 16. Migration: xác định schema đích thay vì đoán

Trong dự án dùng Flyway, Liquibase, Alembic hoặc SQL migration thuần, một lỗi phổ biến là câu:

~~~sql
CREATE TABLE invoices (
    invoice_id bigint PRIMARY KEY
);
~~~

được chạy với `search_path` khác môi trường dự kiến. Bảng có thể được tạo nhầm schema hoặc lệnh thất bại vì thiếu quyền.

Cách rõ ràng hơn:

~~~sql
CREATE TABLE billing.invoices (
    invoice_id bigint PRIMARY KEY
);
~~~

Khi dùng môi trường nhiều schema, cần thiết kế nhất quán:

- **Schema đích:** khai báo rõ nơi tạo bảng và các đối tượng.
- **Role migrator:** có quyền ownership/DDL cần thiết, khác role ứng dụng.
- **Migration history:** công cụ có thể cần schema chứa bảng ghi nhận các lần migration.
- **Thứ tự phụ thuộc:** schema được tạo trước bảng; bảng được tạo trước view/foreign key liên quan.
- **Default privileges:** cấu hình cho role thực sự tạo đối tượng mới.
- **Rollback/forward-fix:** xác định giới hạn của từng loại DDL và dữ liệu đang chuyển đổi.

Một script dùng `CREATE SCHEMA IF NOT EXISTS` có thể chạy lại nếu schema đã tồn tại, nhưng điều đó **không chứng minh** schema đang có đúng owner, quyền hoặc cấu trúc. Tương tự, `CREATE TABLE IF NOT EXISTS` không kiểm tra toàn bộ định nghĩa bảng trùng khớp với thiết kế. Với production, migration cần có version và quy trình kiểm chứng.

### search_path trong công cụ ứng dụng

Một số client/framework có tùy chọn cấu hình schema mặc định. Cần biết nó đặt `search_path` trên session hay chỉ tự thêm tên schema khi sinh SQL. Hai cách có thể có ảnh hưởng khác nhau tới prepared statement, connection pool, function và migration.

Trong connection pool, nếu một request tự thay `search_path` rồi trả connection về pool mà không reset đúng cách, request sau có thể dùng schema còn sót lại. Khi cần thiết lập theo transaction, cân nhắc `SET LOCAL` bên trong một transaction có phạm vi rõ ràng và bảo đảm không dùng connection sai ngữ cảnh.

## 17. Schema trong mô hình đa tenant

Một phương án thiết kế multi-tenancy là **schema per tenant**:

~~~text
tenant_a.customers
tenant_a.orders

tenant_b.customers
tenant_b.orders

shared.countries
shared.product_catalog
~~~

Ưu điểm có thể gồm:

- Tên bảng giống nhau, dữ liệu được tách theo namespace.
- Có thể kiểm soát quyền và migration theo tenant nếu tổ chức đúng.
- Dễ nhìn ranh giới dữ liệu trong catalog.

Nhưng cần đánh giá chi phí:

- Số schema và đối tượng tăng mạnh khi tenant tăng.
- Mỗi tenant cần migration có thứ tự và kiểm soát lỗi.
- Connection pool phải chọn đúng tenant trong mọi transaction.
- Backup/restore và kiểm tra dependency có thể phức tạp hơn.
- Sai `search_path` hoặc role có quyền trên nhiều schema có thể gây đọc/ghi nhầm tenant.
- Catalog và tooling chịu tải quản lý nhiều đối tượng.

Vì vậy schema-per-tenant là **một lựa chọn kiến trúc**, không phải mặc định an toàn nhất hoặc hiệu năng tốt nhất. Một số hệ thống dùng shared tables có `tenant_id` kết hợp RLS, một số dùng database-per-tenant; quyết định phụ thuộc yêu cầu cách ly, quy mô, vận hành và compliance.

### Không nối tên tenant tùy ý vào SQL

Nếu tenant ID xuất phát từ request, không dùng string concatenation không kiểm soát để tạo `SET search_path TO tenant_...` hoặc tên bảng tùy ý. Tên schema phải lấy từ ánh xạ tin cậy, được quote như identifier đúng cách khi cần và gắn chặt với tenant đã xác thực. **Prepared statement placeholder `?` chỉ phù hợp cho giá trị**, không thay thế trực tiếp tên schema/tên bảng trong SQL.

## 18. Những schema hệ thống thường gặp

Khi liệt kê schemas, bạn sẽ thấy một số namespace có mục đích nội bộ.

| Schema | Vai trò |
| --- | --- |
| `pg_catalog` | Chứa catalog và nhiều hàm, type hệ thống của PostgreSQL |
| `information_schema` | Các view chuẩn SQL để tra metadata, chịu ảnh hưởng quyền truy cập |
| `public` | Schema thông thường được tạo sẵn trong nhiều database |
| `pg_toast` | Đối tượng liên quan cơ chế lưu giá trị lớn của PostgreSQL |
| `pg_temp_N` | Schema tạm theo session/backend, tên cụ thể do PostgreSQL quản lý |

Không tạo bảng nghiệp vụ trực tiếp vào `pg_catalog`, `pg_toast` hay những schema hệ thống. Các schema tạm có vòng đời và quy tắc tra cứu riêng, không phải giải pháp lâu dài để chia module.

### Temporary table và search_path

Ví dụ:

~~~sql
CREATE TEMP TABLE scratch (
    id integer PRIMARY KEY
);

INSERT INTO scratch (id) VALUES (1);

SELECT * FROM scratch;
~~~

Bảng tạm được đặt trong temporary schema thuộc session, không phải `sales.scratch` hoặc `public.scratch`. PostgreSQL có quy tắc tìm temporary schema cho tên quan hệ/type không có schema, vì vậy bảng tạm có thể **che khuất** bảng thường trùng tên trong một số tình huống.

Khi cần truy vấn bảng thật không mơ hồ, dùng tên đầy đủ như `lab_sales.orders`. Một bảng temp thường được loại bỏ khi session kết thúc, hoặc theo tùy chọn `ON COMMIT` đã khai báo.

## 19. Quan sát schema và đối tượng trong psql

Trong giao diện `psql` có các meta-command hữu ích:

~~~text
\dn
\dn+
\dt lab_sales.*
\dv lab_reporting.*
\df lab_reporting.*
\d lab_sales.orders
~~~

Ý nghĩa:

- `\dn`: danh sách schemas.
- `\dn+`: thông tin bổ sung như owner và quyền.
- `\dt lab_sales.*`: danh sách tables trong schema chỉ định.
- `\dv lab_reporting.*`: danh sách views.
- `\df lab_reporting.*`: functions trong schema.
- `\d lab_sales.orders`: chi tiết cột, index và constraint của bảng.

Lệnh bắt đầu bằng dấu gạch chéo ngược là meta-command của **psql**, không phải SQL chuẩn gửi qua JDBC.

### Truy vấn bằng SQL

Để đọc danh sách schemas:

~~~sql
SELECT schema_name
FROM information_schema.schemata
ORDER BY schema_name;
~~~

`information_schema` thường chịu ảnh hưởng quyền của role. Muốn khảo sát trực tiếp PostgreSQL catalog:

~~~sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg_%'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname;
~~~

Để xem bảng/view theo schema:

~~~sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'lab_sales',
    'lab_reporting',
    'lab_audit'
)
ORDER BY table_schema, table_name;
~~~

Danh sách từ `information_schema` có thể không đầy đủ nếu role không có quyền nhìn thấy đối tượng tương ứng. Không kết luận schema “trống” chỉ dựa trên truy vấn chạy bằng role bị hạn chế.

## 20. Kiểm tra quyền bằng SQL

PostgreSQL có các hàm kiểm tra quyền, ví dụ:

~~~sql
SELECT
    has_schema_privilege(
        current_user,
        'lab_sales',
        'USAGE'
    ) AS can_use_schema,
    has_schema_privilege(
        current_user,
        'lab_sales',
        'CREATE'
    ) AS can_create_in_schema,
    has_table_privilege(
        current_user,
        'lab_sales.customers',
        'SELECT'
    ) AS can_read_customers;
~~~

Các hàm này kiểm tra quyền cho user đang kết nối. Chúng hữu ích khi ứng dụng báo `permission denied for schema ...` hoặc `permission denied for table ...`.

Nếu `can_use_schema = true` nhưng `can_read_customers = false`, role có thể tham chiếu schema nhưng không được đọc bảng. Ngược lại, có một grant bảng chưa chắc đủ nếu thiếu USAGE schema. Thực tế còn cần xem quyền liên quan tới function, sequence và các đối tượng khác tùy thao tác.

### Sử dụng GRANT tối thiểu

Một ứng dụng chỉ cần đọc view báo cáo có thể được cấp `USAGE` trên `lab_reporting` và `SELECT` trên view phù hợp, thay vì cấp quyền SELECT trên mọi bảng giao dịch. Tuy nhiên, view có **quy tắc thực thi quyền** riêng (mặc định thường dùng quyền của view owner đối với bảng nền; các tùy chọn như `security_invoker` có yêu cầu phiên bản). Phải thiết kế, kiểm tra owner/permission và RLS thực tế trước khi xem view là lớp an toàn hoàn chỉnh.

## 21. Backup, restore và vòng đời schema

Công cụ `pg_dump` hỗ trợ giới hạn theo schema:

~~~bash
pg_dump \
  -Fc \
  -n lab_sales \
  -d schema_lab \
  -f lab_sales.dump
~~~

Tùy chọn `-n` chọn những đối tượng phù hợp với schema được chỉ định; `-Fc` tạo định dạng custom để dùng cùng `pg_restore` theo quy trình thích hợp.

**Cảnh báo quan trọng:** backup một schema không tự đảm bảo chứa đủ mọi dependency nằm ngoài schema đó. Ví dụ `lab_reporting.paid_revenue` tham chiếu bảng trong `lab_sales`; chỉ dump `lab_reporting` có thể không đủ để khôi phục độc lập trên database trống. Quyền, extensions, roles và các đối tượng liên quan cũng cần kế hoạch riêng.

Schema là **ranh giới lựa chọn đối tượng cho thao tác quản trị**, không có nghĩa luôn là đơn vị backup độc lập hoàn chỉnh. Với production, phải thử restore thực tế, xác minh dependency và lưu metadata về phiên bản/hệ thống.

### DROP SCHEMA, RESTRICT và CASCADE

~~~sql
-- Từ chối xóa schema nếu còn đối tượng phụ thuộc
-- theo quy tắc dependency của PostgreSQL.
DROP SCHEMA lab_audit RESTRICT;
~~~

Khi schema còn bảng `events`, lệnh này sẽ không xóa thành công vì còn đối tượng. Lệnh có `CASCADE`:

~~~sql
-- NGUY HIỂM: chỉ thực hành khi chắc chắn đúng schema lab.
DROP SCHEMA lab_audit CASCADE;
~~~

`CASCADE` có thể kéo theo **các đối tượng phụ thuộc ở schema khác** chứ không chỉ bảng bên trong schema được xóa. Vì vậy không thể coi nó là “chỉ xóa một thư mục”. Trong môi trường thực tế cần khảo sát dependency, backup, quyền và kế hoạch khôi phục trước khi thay đổi/xóa schema.

### Đổi tên schema

PostgreSQL hỗ trợ:

~~~sql
ALTER SCHEMA lab_reporting RENAME TO lab_reports;
~~~

Đây là ví dụ cú pháp và cần owner/quyền tương ứng. Dù database có thể cập nhật dependency nội bộ, những câu SQL/ứng dụng có tên schema hard-code có thể bị lỗi sau khi đổi tên; migration cần phối hợp với code và tooling.

## 22. Những lỗi và nhầm lẫn thường gặp

### 22.1. Nhầm schema với database

`sales` và `reporting` trong cùng database có thể JOIN trực tiếp. Hai database khác nhau lại không thể được truy cập xuyên database bằng cùng kiểu tên đầy đủ đơn giản.

### 22.2. Nghĩ bảng không ghi schema luôn là public.table

Câu `CREATE TABLE orders (...)` phụ thuộc `search_path`. Nếu một schema khác đứng đầu, đối tượng có thể được tạo ở nơi khác. Dùng tên đầy đủ cho migration.

### 22.3. Chỉ GRANT SELECT mà quên USAGE

Khi thiếu quyền `USAGE` trên schema, role có thể không tham chiếu được bảng dù đã có `SELECT`. Kiểm tra cả quyền schema và quyền đối tượng.

### 22.4. Chỉ GRANT USAGE mà tưởng đọc được mọi bảng

`USAGE` không thay thế `SELECT`. Muốn đọc, cần quyền bảng/view thích hợp hoặc đường truy cập được thiết kế có kiểm soát.

### 22.5. Dùng GRANT ALL TABLES rồi mong bảng mới tự có quyền

Lệnh đó áp dụng cho bảng hiện tại. Muốn cấp quyền tương lai, cấu hình `ALTER DEFAULT PRIVILEGES` cho đúng role tạo đối tượng.

### 22.6. Cho người dùng không tin cậy CREATE trong schema nằm đầu search_path

Các đối tượng mới có thể che khuất tên mà ứng dụng đang tham chiếu, tạo rủi ro về phân giải SQL. Giữ search path tin cậy và tránh quyền CREATE rộng.

### 22.7. Dùng search_path động trong connection pool rồi quên reset

Request sau có thể đọc nhầm tenant hoặc module. Quản lý đúng vòng đời session/transaction hoặc dùng tên fully qualified.

### 22.8. Coi schema-per-tenant là cách ly bảo mật tuyệt đối

Dữ liệu vẫn trong cùng database và permission có thể cho truy cập chéo. Phải có tenant authorization, role separation và test truy cập chéo.

### 22.9. DROP SCHEMA CASCADE mà không xem dependency

Có thể xóa bảng, view hoặc ràng buộc ở nơi khác theo dependency. Không dùng trong production như thao tác dọn dẹp đơn giản.

### 22.10. Nghĩ chỉ mục schema quyết định hiệu năng

Schema là namespace, không tự làm truy vấn nhanh hơn. Hiệu năng phụ thuộc truy vấn, chỉ mục, thống kê, dữ liệu và kế hoạch thực thi. Chia bảng qua nhiều schema không thay thế tối ưu SQL.

## 23. Bài tập thực hành

Dùng dữ liệu `lab_sales`, `lab_reporting` và `lab_audit` ở phần trước.

### Bài 1: Hai bảng cùng tên

Chạy:

~~~sql
SELECT COUNT(*) AS sales_customers
FROM lab_sales.customers;

SELECT COUNT(*) AS report_customers
FROM lab_reporting.customers;
~~~

**Kết quả dự kiến:** `sales_customers = 3`; `report_customers = 2`. Cùng tên `customers` nhưng không phải cùng đối tượng.

### Bài 2: Đổi search_path và quan sát

~~~sql
SET search_path TO lab_reporting, lab_sales;

SELECT customer_id, display_label
FROM customers
ORDER BY customer_id;

SET search_path TO lab_sales, lab_reporting;

SELECT customer_id, customer_name
FROM customers
ORDER BY customer_id;

RESET search_path;
~~~

Giải thích vì sao hai truy vấn dùng `FROM customers` nhưng đọc bảng khác nhau. Gợi ý: vị trí schema trong `search_path`.

### Bài 3: Truy vấn xuyên schema

~~~sql
SELECT
    c.customer_name,
    o.order_id,
    o.status,
    o.total
FROM lab_sales.customers AS c
JOIN lab_sales.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'paid'
ORDER BY o.order_id;
~~~

**Kết quả:** đơn 101, 102 của An và đơn 104 của Chi. Thử truy vấn `lab_reporting.paid_revenue` và đối chiếu doanh thu 350 của An, 0 của Binh, 120 của Chi.

### Bài 4: Phân tích quyền

Giả sử một role có `USAGE ON SCHEMA lab_sales` và `SELECT ON lab_sales.customers`, nhưng không có `INSERT`. Role có thể thực hiện `SELECT` không? Có thể `INSERT` không?

**Đáp án:** Với các quyền, ownership và policy thông thường phù hợp, role có thể đọc bảng nhưng không có quyền chèn hàng chỉ từ hai grant này.

### Bài 5: Default privileges

Bạn đã chạy `GRANT SELECT ON ALL TABLES IN SCHEMA lab_sales TO lab_sales_reader`. Ngày mai migrator tạo thêm `lab_sales.returns`. Vì sao role reader có thể chưa đọc được bảng mới?

**Đáp án:** Lệnh `GRANT ... ALL TABLES` áp dụng các bảng hiện có. Cần quyền mặc định đúng **role tạo bảng** và schema, hoặc cấp quyền mới sau migration.

### Bài 6: Kiểm tra schema hiện hành

~~~sql
SHOW search_path;

SELECT
    current_schema(),
    current_schemas(true);
~~~

So sánh danh sách trên với output `\dn` trong `psql`. Giải thích vì sao một số schema có thể xuất hiện trong catalog nhưng không có trong effective search path.

### Bài 7: Thiết kế ranh giới mới

Một ứng dụng có các nhóm **orders**, **payments**, **reporting** và **audit**. Hãy đề xuất tên schema, role owner/migrator và quyền đọc/ghi cho từng nhóm. Trả lời: vì sao ứng dụng xử lý thanh toán không nên được cấp `CREATE` vào mọi schema? Có nên cấp quyền đọc toàn bộ audit cho mọi application writer không?

Không có đáp án duy nhất cho tên schema, nhưng thiết kế phải thể hiện rõ trách nhiệm, quyền tối thiểu và các dependency xuyên schema.

## 24. Ghi nhớ khi tổ chức dữ liệu PostgreSQL

- **Schema là namespace bên trong một database**, giúp hai đối tượng cùng tên tồn tại ở những vùng tổ chức khác nhau.
- **Tên đầy đủ `schema.object`** giúp SQL rõ nghĩa và tránh phụ thuộc vào `search_path`.
- **`search_path` là cơ chế phân giải tên và cũng là quyết định tin cậy**, cần kiểm soát ở ứng dụng, migration và function có quyền cao.
- **Quyền schema (`USAGE`, `CREATE`) và quyền bảng/view/function là các tầng riêng**; một grant không tự thay thế tầng còn lại.
- **Default privileges** chỉ tác động đối tượng sẽ tạo theo role tương ứng; cần thiết kế song song với quyền của những bảng hiện có.
- **Schema không phải ranh giới vật lý hay bảo mật tuyệt đối**; các bảng vẫn chia sẻ database và có thể phụ thuộc chéo.
- **Tổ chức tốt** dựa vào miền nghiệp vụ, ownership, migration, quyền truy cập và khả năng vận hành, không chỉ vào số lượng namespace.

Khi dùng schema để biểu diễn rõ trách nhiệm và giới hạn truy cập, PostgreSQL trở nên dễ quản trị hơn. Nhưng cách sử dụng hiệu quả nhất luôn kết hợp namespace với tên đối tượng tường minh, role có quyền tối thiểu, migration có thứ tự và kiểm chứng quyền thực tế.
