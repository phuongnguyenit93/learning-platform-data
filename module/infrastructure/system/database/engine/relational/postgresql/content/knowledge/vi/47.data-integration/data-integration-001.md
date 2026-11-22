# Foreign Data Wrapper và mô hình bảng dữ liệu ngoài trong PostgreSQL

PostgreSQL có thể truy vấn dữ liệu nằm ngoài database hiện tại thông qua **Foreign Data Wrapper (FDW)**. Với FDW, một bảng ở hệ thống khác có thể được biểu diễn trong PostgreSQL như một foreign table. Ứng dụng gửi SQL tới PostgreSQL; planner và executor phối hợp với FDW để dịch phần công việc phù hợp thành thao tác trên nguồn dữ liệu bên ngoài.

Mô hình này hữu ích khi cần tích hợp nhiều database, đọc dữ liệu từ hệ thống cũ, kết hợp dữ liệu operational với nguồn ngoài hoặc truy cập file/object/service thông qua wrapper phù hợp. Người dùng có thể truy vấn foreign table bằng SQL quen thuộc mà không cần tự viết một connector cho từng câu query.

Tuy nhiên, foreign table không giống một table local. Dữ liệu thường vẫn nằm ở remote source; latency, availability, permissions, transaction semantics, type mapping và query pushdown phụ thuộc FDW và nguồn dữ liệu. Thiết kế tốt cần hiểu rõ phần nào chạy ở PostgreSQL local, phần nào chạy ở remote system, và cách giới hạn chi phí truy cập.

Bài học này trình bày kiến trúc FDW, các đối tượng cấu hình, cách triển khai `postgres_fdw`, import schema, truy vấn và ghi dữ liệu ngoài, tối ưu query pushdown, bảo mật, vận hành, giới hạn và các bài tập thực hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Foreign Data Wrapper và kiến trúc foreign table.
2. Phân biệt local table, foreign table, view và materialized view.
3. Nhận biết vai trò của FDW handler, validator, foreign server và user mapping.
4. Cài đặt, cấu hình và sử dụng `postgres_fdw`.
5. Import foreign schema hoặc khai báo foreign table thủ công.
6. Truy vấn, join, filter, aggregate và ghi dữ liệu qua foreign table.
7. Hiểu query pushdown và đọc `EXPLAIN VERBOSE` để xác nhận remote SQL.
8. Tối ưu fetch size, remote estimates, batch writes và network round trips.
9. Quản lý credentials, user mapping, privileges và network security.
10. Hiểu transaction behavior, consistency và các giới hạn distributed transaction.
11. Theo dõi latency, remote sessions, errors và availability.
12. Chọn giữa FDW, ETL/ELT, replication, API và materialization.
13. Thiết kế lab/runbook cho tích hợp dữ liệu an toàn.

## 2. Foreign Data Wrapper là gì?

### 2.1. Khái niệm

Foreign Data Wrapper là một extension/interface trong PostgreSQL cho phép truy cập dữ liệu bên ngoài thông qua foreign tables. FDW che giấu chi tiết giao tiếp với nguồn dữ liệu, cung cấp metadata để PostgreSQL planner/executor biết cách đọc hoặc ghi dữ liệu đó.

Ví dụ, `postgres_fdw` cho phép một PostgreSQL database truy cập tables nằm trong một PostgreSQL server khác. Từ local database, người dùng có thể chạy:

~~~sql
SELECT customer_id, email
FROM remote_crm.customers
WHERE active = true;
~~~

Foreign table `remote_crm.customers` không phải bản copy của remote table. Khi query được thực thi, FDW có thể gửi SQL tới remote server và trả kết quả về local executor.

### 2.2. FDW không phải replication

| Đặc điểm | FDW | Replication |
| --- | --- | --- |
| Dữ liệu | Thường đọc/ghi trực tiếp nguồn ngoài | Có bản sao ở subscriber/replica |
| Thời điểm lấy dữ liệu | Khi query chạy | Theo stream/schedule |
| Query local | Có thể cần network round trip | Đọc từ local copy |
| Availability | Phụ thuộc remote source/network | Có thể tiếp tục đọc bản sao khi source unavailable, tùy setup |
| Freshness | Gần thời điểm query, theo remote consistency | Có replication lag |
| Storage local | Metadata, không nhất thiết lưu data | Lưu bản sao dữ liệu |
| Phù hợp | Federation, lookup, tích hợp trực tiếp | Read scaling, DR, data distribution |

FDW không tự tạo bản sao bền vững. Nếu cần query nhanh và ổn định khi remote source down, cân nhắc materialize/copy dữ liệu hoặc dùng replication.

### 2.3. FDW không phải ETL

ETL/ELT thường extract dữ liệu, transform và load vào một hệ thống đích để phục vụ analytics hoặc application. FDW cho phép query liên kết trực tiếp trong lúc chạy. Có thể dùng FDW làm nguồn cho ETL, nhưng FDW không tự cung cấp orchestration, retry policy, data quality pipeline hoặc historical snapshots.

### 2.4. Foreign table

Foreign table là relation local có schema/columns nhưng dữ liệu do FDW cung cấp. Nó có thể xuất hiện trong SQL như table, join hoặc view. Catalog lưu metadata; dữ liệu thường ở nguồn ngoài.

Foreign table có thể được khai báo thủ công hoặc import từ remote schema. PostgreSQL kiểm tra column names/types đã khai báo so với khả năng FDW; mapping sai có thể gây lỗi hoặc dữ liệu bị cast không như mong đợi.

### 2.5. Các loại nguồn dữ liệu

Tùy wrapper, foreign data có thể đến từ:

- PostgreSQL hoặc database quan hệ khác;
- CSV/text files;
- ODBC/JDBC-accessible sources qua wrapper phù hợp;
- Key-value/document stores;
- REST/API hoặc hệ thống chuyên biệt;
- Object storage hoặc external services.

Không có một FDW core duy nhất hỗ trợ mọi nguồn. Mỗi wrapper có prerequisites, feature set, security model và compatibility riêng.

## 3. Kiến trúc FDW và các đối tượng

### 3.1. Luồng xử lý tổng quát

~~~text
Application / SQL client
        |
        v
Local PostgreSQL parser and planner
        |
        v
Foreign table metadata
        |
        v
FDW planner callbacks
        |
        +---- pushable filters / joins / sorts ----> Remote source
        |                                              |
        <------------- rows / remote results ----------+
        |
        v
Local executor: remaining filters / joins / projection
        |
        v
Query result
~~~

Planner quyết định phần nào có thể gửi remote dựa trên khả năng của FDW, biểu thức, options và type/collation compatibility. Phần không pushdown sẽ chạy ở local PostgreSQL sau khi dữ liệu được chuyển qua network.

### 3.2. FDW handler

Handler là function do extension cung cấp, trả về function pointers cho các callbacks mà PostgreSQL dùng trong planning/execution. Tùy wrapper, callbacks có thể hỗ trợ scan, modify, explain, analyze, import schema, parallel execution hoặc asynchronous execution.

### 3.3. FDW validator

Validator kiểm tra options được truyền khi tạo foreign server, user mapping hoặc foreign table. Ví dụ validator có thể kiểm tra tên option, format hoặc giá trị có hợp lệ hay không.

### 3.4. Foreign-data wrapper object

Wrapper là đối tượng database gắn với extension/library:

~~~sql
CREATE FOREIGN DATA WRAPPER wrapper_name
HANDLER handler_function
VALIDATOR validator_function;
~~~

Thông thường extension cài đặt wrapper bằng `CREATE EXTENSION`; DBA không cần tự định nghĩa handler cho wrapper có sẵn.

### 3.5. Foreign server

Foreign server là cấu hình đại diện cho một nguồn dữ liệu bên ngoài. Với `postgres_fdw`, options thường gồm host, port và database name:

~~~sql
CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm'
);
~~~

`CREATE SERVER` không tạo kết nối liên tục tới remote database. Kết nối được thiết lập khi query/operation cần dùng foreign server.

### 3.6. User mapping

User mapping ánh xạ local PostgreSQL user sang credentials/identity ở remote source:

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER crm_server
OPTIONS (
    user 'crm_readonly',
    password 'replace-with-secret'
);
~~~

Không đưa password thật vào source control, migration scripts công khai hoặc logs. Ví dụ trên chỉ dùng placeholder; dùng secret management và quyền truy cập catalog phù hợp trong production.

### 3.7. Foreign table

Foreign table định nghĩa columns và mapping đến object remote:

~~~sql
CREATE FOREIGN TABLE remote_customers (
    customer_id bigint,
    email text,
    active boolean
)
SERVER crm_server
OPTIONS (
    schema_name 'public',
    table_name 'customers'
);
~~~

### 3.8. Schema local và schema remote

Schema local chứa foreign table có thể khác schema của object remote. `schema_name`/`table_name` options của `postgres_fdw` xác định remote relation; local schema chỉ tổ chức namespace trong database hiện tại.

### 3.9. Privileges

Quyền được kiểm tra ở cả hai phía:

- Local user cần quyền USAGE trên foreign server;
- Local user cần quyền USAGE trên foreign-data wrapper nếu policy yêu cầu;
- Local user cần quyền SELECT/INSERT/UPDATE/DELETE trên foreign table tương ứng;
- User mapping phải tồn tại cho local user hoặc PUBLIC;
- Remote identity cần quyền trên remote database/schema/table.

Local GRANT không tự cấp remote privileges.

### 3.10. Catalogs quan trọng

Các catalog views hữu ích:

| Catalog/view | Mục đích |
| --- | --- |
| `pg_foreign_data_wrapper` | Wrapper đã đăng ký |
| `pg_foreign_server` | Foreign servers |
| `pg_user_mappings` | User mappings; thông tin nhạy cảm có thể bị che theo quyền |
| `pg_foreign_table` | Foreign table options |
| `information_schema.foreign_tables` | Foreign tables theo information schema |
| `pg_class`/`pg_attribute` | Relation và column metadata |

## 4. Cài đặt và cấu hình postgres_fdw

### 4.1. Khi nào dùng postgres_fdw?

Dùng `postgres_fdw` khi local PostgreSQL cần truy cập dữ liệu từ một PostgreSQL database khác và muốn query federation bằng SQL. Cả hai server cần network connectivity và version/feature compatibility phù hợp.

### 4.2. Kiểm tra extension

Trên local database:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
~~~

Package/library của extension phải được cài trên host/container database server. Trong managed PostgreSQL, provider phải hỗ trợ extension và có thể yêu cầu allowlist hoặc quyền đặc biệt.

### 4.3. Tạo foreign server

~~~sql
CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm',
    application_name 'local-fdw-crm'
);
~~~

`application_name` giúp nhận diện remote connections trong `pg_stat_activity` nếu remote server hỗ trợ nhận giá trị này từ libpq options.

### 4.4. Tạo user mapping

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER crm_server
OPTIONS (
    user 'crm_readonly',
    password 'use-a-secret-manager'
);
~~~

Có thể tạo mapping cho một local role cụ thể hoặc PUBLIC. Mapping PUBLIC làm rộng phạm vi identity dùng chung; chỉ chọn khi policy/security model cho phép.

### 4.5. Cấp quyền local

~~~sql
GRANT USAGE ON FOREIGN SERVER crm_server TO app_reader;
GRANT USAGE ON FOREIGN DATA WRAPPER postgres_fdw TO app_reader;
~~~

Khi foreign tables được tạo, cấp quyền trên schema/table:

~~~sql
GRANT USAGE ON SCHEMA remote_crm TO app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA remote_crm TO app_reader;
~~~

`GRANT SELECT ON ALL TABLES` tác động các tables hiện có. Default privileges cần cấu hình riêng nếu foreign tables mới sẽ được tạo về sau.

### 4.6. Tạo local schema

~~~sql
CREATE SCHEMA IF NOT EXISTS remote_crm;
GRANT USAGE ON SCHEMA remote_crm TO app_reader;
~~~

### 4.7. Import foreign schema

`IMPORT FOREIGN SCHEMA` đọc metadata remote và tạo foreign tables local:

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders, order_items)
FROM SERVER crm_server
INTO remote_crm;
~~~

Có thể dùng `EXCEPT` để bỏ qua một số tables:

~~~sql
IMPORT FOREIGN SCHEMA public
EXCEPT (audit_log, internal_secrets)
FROM SERVER crm_server
INTO remote_crm;
~~~

Import chỉ tạo metadata foreign tables; không copy data. Kiểm tra privileges remote và quyền tạo objects trong local schema.

### 4.8. Kiểm tra foreign tables đã tạo

~~~sql
SELECT
    foreign_table_schema,
    foreign_table_name,
    foreign_server_name
FROM information_schema.foreign_tables
WHERE foreign_table_schema = 'remote_crm'
ORDER BY foreign_table_name;
~~~

### 4.9. Kiểm tra server và mapping

~~~sql
SELECT
    srvname,
    fdwname,
    srvoptions
FROM pg_foreign_server AS s
JOIN pg_foreign_data_wrapper AS w ON w.oid = s.srvfdw
ORDER BY srvname;

SELECT
    srvname,
    usename,
    umoptions
FROM pg_user_mappings;
~~~

Các credentials trong catalog không nên được đưa vào output/logs chia sẻ. Quyền xem user mappings có thể làm lộ options nhạy cảm; giới hạn quyền đọc.

### 4.10. Kết nối thử

~~~sql
SELECT *
FROM remote_crm.customers
LIMIT 10;
~~~

Query đầu tiên có thể chịu chi phí khởi tạo network connection/authentication. Kiểm tra lỗi DNS, firewall, TLS, remote role, schema/table name và type mapping nếu không kết nối được.

## 5. Truy vấn foreign tables

### 5.1. SELECT cơ bản

Foreign table được dùng trong FROM như local table:

~~~sql
SELECT customer_id, email
FROM remote_crm.customers
WHERE active
ORDER BY customer_id
LIMIT 100;
~~~

Phần filter/order/limit có được gửi remote hay không tùy FDW và khả năng pushdown. Không mặc định mọi clause đều chạy trên remote.

### 5.2. Join local và foreign tables

~~~sql
SELECT
    o.order_id,
    o.created_at,
    c.email
FROM public.local_orders AS o
JOIN remote_crm.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= current_date - interval '7 days';
~~~

Nếu join không được pushdown, PostgreSQL có thể đọc một tập rows từ remote rồi join local. Điều này có thể rất tốn network nếu foreign side lớn. Kiểm tra plan trước khi đưa query vào production.

### 5.3. Join giữa foreign tables cùng server

Khi cả hai foreign tables cùng foreign server và cùng user mapping/compatible options, `postgres_fdw` có thể pushdown join sang remote server trong các điều kiện hỗ trợ. Remote join thường giảm lượng dữ liệu truyền về local.

~~~sql
SELECT
    c.customer_id,
    c.email,
    o.order_id,
    o.total_amount
FROM remote_crm.customers AS c
JOIN remote_crm.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.created_at >= date '2026-01-01';
~~~

Xác nhận bằng `EXPLAIN VERBOSE`; không suy luận pushdown chỉ từ việc cả hai tables là foreign.

### 5.4. Aggregate pushdown

`postgres_fdw` có thể pushdown một số aggregate queries khi expressions và semantics tương thích. Ví dụ:

~~~sql
SELECT status, count(*), sum(total_amount)
FROM remote_crm.orders
GROUP BY status;
~~~

Nếu aggregate chạy remote, chỉ các group rows được truyền về. Nếu không pushdown, có thể toàn bộ qualifying rows phải đi qua network để aggregate local.

### 5.5. ORDER BY và LIMIT

~~~sql
SELECT order_id, created_at
FROM remote_crm.orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Pushdown ORDER BY/LIMIT có thể giảm transfer đáng kể. Collation, NULL ordering, expressions hoặc semantics không tương thích có thể ngăn pushdown.

### 5.6. Filter pushdown

Các predicates đơn giản trên columns foreign thường có cơ hội pushdown. Ví dụ:

~~~sql
SELECT *
FROM remote_crm.orders
WHERE customer_id = 1001
  AND created_at >= timestamp '2026-01-01 00:00:00';
~~~

Local PostgreSQL có thể vẫn giữ một số filters nếu biểu thức không được FDW đánh giá là safe hoặc không thể chuyển đổi tương đương.

### 5.7. Projection pushdown

Chỉ chọn các columns cần dùng. Tránh `SELECT *` khi remote table có nhiều columns lớn, JSON/BLOB hoặc text payload. Projection pushdown giảm bytes truyền qua network nếu FDW hỗ trợ.

~~~sql
SELECT order_id, status
FROM remote_crm.orders
WHERE customer_id = 1001;
~~~

### 5.8. Subqueries và CTE

Planner có thể flatten/inlining hoặc materialize subqueries/CTEs theo query semantics và version. Không giả định một CTE luôn chạy remote hoặc luôn được materialize local. Đọc execution plan và đo thực tế.

### 5.9. Functions và expressions

Một function local hoặc expression không được remote hỗ trợ có thể ngăn pushdown. Chuyển đổi timezone/collation, user-defined functions và casts cần đặc biệt chú ý. Có thể tính expression local sau khi lấy dữ liệu, nhưng điều này làm tăng network transfer.

### 5.10. EXPLAIN VERBOSE

Dùng:

~~~sql
EXPLAIN (VERBOSE, COSTS, SETTINGS)
SELECT order_id, status
FROM remote_crm.orders
WHERE customer_id = 1001
ORDER BY created_at DESC
LIMIT 50;
~~~

Trong plan của `postgres_fdw`, tìm `Foreign Scan` và `Remote SQL`. Remote SQL cho thấy predicates/projection/order/limit nào đã được gửi sang remote. `EXPLAIN` không thực thi query; thêm `ANALYZE` để đo runtime, nhưng lưu ý query sẽ thực sự chạy.

### 5.11. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS, SETTINGS)
SELECT count(*)
FROM remote_crm.orders
WHERE created_at >= current_date - 30;
~~~

`BUFFERS` chủ yếu mô tả buffers local; nó không thay thế remote server metrics. Để hiểu remote cost, xem plan/log/statistics ở remote server cùng lúc.

### 5.12. Query timeout

Local `statement_timeout` có thể hủy query đang chờ remote operation. Cũng cần cấu hình timeout/network behavior phù hợp ở client/remote side. Kiểm tra cách FDW propagate cancellation và remote query state trong version đang chạy.

## 6. Query pushdown và planner costing

### 6.1. Pushdown là gì?

Pushdown là việc chuyển một phần công việc từ local PostgreSQL sang remote source. Ví dụ filter, projection, sort, limit, aggregate hoặc join được tính ở nơi dữ liệu đang nằm.

### 6.2. Vì sao pushdown quan trọng?

Giả sử remote table có 50 triệu rows nhưng query chỉ cần 200 rows. Nếu filter chạy remote, network chỉ chuyển 200 rows. Nếu filter chạy local, hàng triệu rows có thể phải được chuyển về rồi mới loại bỏ.

### 6.3. Predicate không pushdown

Các nguyên nhân phổ biến:

- Function/expression local không có remote equivalent;
- Cast hoặc operator semantics khác nhau;
- Collation không tương thích;
- Query dùng nhiều foreign servers;
- Join conditions không đáp ứng điều kiện pushdown;
- FDW version/implementation chưa hỗ trợ clause đó;
- FDW option hoặc planner cost khiến plan khác được chọn.

### 6.4. Remote estimates

`postgres_fdw` có option `use_remote_estimate`. Khi bật, planner có thể hỏi remote server để lấy estimates/cost thay vì chỉ dựa trên local assumptions. Điều này có thể cải thiện plan cho remote tables lớn nhưng thêm round trips/planning overhead.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD use_remote_estimate 'true');
~~~

Hoặc đặt trên foreign table theo supported options. Thử bật/tắt và so sánh planning time, chosen plan và execution time; remote estimates không luôn tốt hơn nếu network latency cao hoặc remote statistics stale.

### 6.5. fdw_startup_cost và fdw_tuple_cost

Các options costing như `fdw_startup_cost` và `fdw_tuple_cost` giúp planner ước lượng chi phí kết nối/nhận rows từ foreign server. Giá trị quá thấp có thể khiến planner chọn remote path quá thường xuyên; quá cao có thể khiến planner tránh pushdown có lợi.

~~~sql
ALTER SERVER crm_server
OPTIONS (
    ADD fdw_startup_cost '100',
    ADD fdw_tuple_cost '0.2'
);
~~~

Các con số chỉ minh họa. Đo latency/network/row width và calibrate bằng workload thật.

### 6.6. fetch_size

`fetch_size` quy định số rows mà `postgres_fdw` lấy mỗi lần fetch từ remote cursor. Giá trị lớn giảm số round trips nhưng dùng nhiều memory/buffer hơn; giá trị nhỏ giảm memory mỗi fetch nhưng tăng network overhead.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD fetch_size '10000');
~~~

Có thể đặt option ở foreign table nếu cần điều chỉnh cho relation cụ thể. Chọn theo row width, network latency và concurrent query count.

### 6.7. batch_size cho writes

`batch_size` điều khiển số rows được gửi trong một batch cho một số remote INSERT paths. Giá trị lớn có thể giảm round trips; đồng thời tăng payload/memory và có thể ảnh hưởng error handling. Tùy version và DML pattern, option có thể không áp dụng cho mọi writes.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD batch_size '1000');
~~~

### 6.8. async_capable

Một số phiên bản `postgres_fdw` hỗ trợ asynchronous execution cho các foreign scans phù hợp. Option `async_capable` cho phép planner xem xét khả năng này. Async execution không biến một remote query đơn thành nhanh hơn một cách thần kỳ; lợi ích chủ yếu có thể đến từ việc chạy các foreign scans độc lập đồng thời.

~~~sql
ALTER SERVER crm_server
OPTIONS (ADD async_capable 'true');
~~~

Xác minh major version, plan và remote connection capacity trước khi bật.

### 6.9. Parallel execution

Khả năng parallel scan phụ thuộc FDW, version, query plan và remote source. Không mặc định foreign table scan có thể dùng parallel workers. Kiểm tra plan và tài liệu của wrapper cụ thể.

### 6.10. Local statistics

Planner cần estimates cho foreign table. Có thể chạy:

~~~sql
ANALYZE remote_crm.orders;
~~~

FDW có thể cung cấp sampling/analysis method để local statistics phản ánh remote data. Với `postgres_fdw`, ANALYZE foreign table đọc sample từ remote. Tần suất cập nhật phụ thuộc data change rate và query planning sensitivity.

### 6.11. Stale statistics

Remote data thay đổi nhưng local foreign table statistics không tự cập nhật tức thời. Nếu local estimates stale, planner có thể chọn join order/scan path kém. Đặt lịch ANALYZE hoặc dùng remote estimates khi phù hợp.

### 6.12. Planner pushdown không thay remote indexing

Predicate đã được pushdown vẫn có thể chạy chậm nếu remote table thiếu index hoặc remote plan xấu. Kiểm tra `EXPLAIN` ở remote database và tối ưu indexes/statistics tại nơi lưu dữ liệu.

## 7. Ghi dữ liệu qua foreign tables

### 7.1. DML hỗ trợ

`postgres_fdw` hỗ trợ các thao tác ghi phổ biến trên foreign tables, gồm INSERT, UPDATE và DELETE, khi remote server, user mapping và quyền cho phép. Khả năng cụ thể của các FDW khác nhau; một số wrappers chỉ hỗ trợ đọc.

### 7.2. INSERT

~~~sql
INSERT INTO remote_crm.customers (customer_id, email, active)
VALUES (90001, 'new@example.com', true);
~~~

Lệnh được gửi tới remote database. Remote constraints, triggers, defaults và permissions được áp dụng theo semantics của remote table.

### 7.3. UPDATE

~~~sql
UPDATE remote_crm.customers
SET active = false
WHERE customer_id = 90001;
~~~

Filter có thể được pushdown để remote server tìm rows cần sửa. Kiểm tra remote execution và số rows affected; tránh update rộng nếu chưa xác minh predicate.

### 7.4. DELETE

~~~sql
DELETE FROM remote_crm.customers
WHERE customer_id = 90001;
~~~

DELETE trên foreign table là thay đổi dữ liệu remote. Cần quyền remote tương ứng, audit trail và quy trình xác nhận cho thao tác destructive.

### 7.5. INSERT SELECT

~~~sql
INSERT INTO remote_crm.order_archive (order_id, customer_id, archived_at)
SELECT order_id, customer_id, now()
FROM public.orders
WHERE status = 'CLOSED'
  AND closed_at < current_date - interval '1 year';
~~~

Local PostgreSQL đọc nguồn local rồi ghi rows sang remote. Đây có thể tạo lượng network transfer/WAL đáng kể và không phải tự động là một bulk load tối ưu. Chia batch, kiểm soát retries và kiểm tra duplicate behavior.

### 7.6. Batch INSERT

`batch_size` là option của `postgres_fdw` cho một số INSERT paths. Nó có thể gộp nhiều rows trong remote statement để giảm network round trips. Xác minh version, plan, row size và error behavior trước khi đặt batch lớn.

### 7.7. UPDATE/DELETE không luôn được batch

Không giả định `batch_size` áp dụng đồng đều cho UPDATE/DELETE. Nếu cần giới hạn tác động, chia target rows theo primary-key ranges hoặc time windows và commit từng batch.

### 7.8. RETURNING

Khả năng hỗ trợ `RETURNING` và việc đẩy biểu thức về remote phụ thuộc wrapper/version. Với `postgres_fdw`, kiểm tra documentation hiện hành và thử đúng DML pattern; không thiết kế pipeline dựa trên assumption chưa kiểm chứng.

### 7.9. Triggers và defaults ở remote

Remote triggers/defaults chạy tại remote database theo semantics của nó. Local PostgreSQL không nhất thiết biết đầy đủ side effects phát sinh từ remote triggers; thiết kế audit, generated values và application expectations cẩn thận.

### 7.10. Upsert

Không mặc định mọi FDW hỗ trợ `INSERT ... ON CONFLICT` giống local table. Kiểm tra wrapper và PostgreSQL version trước khi sử dụng. Nếu upsert không được hỗ trợ, thiết kế thao tác ở remote server (ví dụ remote function/API) hoặc pipeline có idempotency key.

### 7.11. TRUNCATE

Không giả định foreign table hỗ trợ mọi table utility command như local table. Kiểm tra tài liệu FDW; với `postgres_fdw`, các DML commands được hỗ trợ khác với utility operations. Tránh dùng `TRUNCATE` trên foreign relation nếu wrapper không công bố hỗ trợ.

### 7.12. DML quyền và audit

Local GRANT INSERT/UPDATE/DELETE chỉ cho phép user thao tác foreign table local; remote identity vẫn phải có quyền thực hiện DML. Audit cả local request và remote actor để truy vết thay đổi.

## 8. Transaction semantics và consistency

### 8.1. Local transaction và remote transaction

Khi transaction local truy cập foreign server qua `postgres_fdw`, wrapper mở/duy trì remote transaction tương ứng. Nhiều statements trong cùng local transaction có thể dùng cùng remote transaction theo behavior của FDW.

### 8.2. Commit và rollback

Local COMMIT/ROLLBACK được chuyển tiếp tới remote transaction. Nếu local transaction rollback, remote changes chưa commit được rollback theo FDW behavior. Tuy nhiên, lỗi network/remote crash trong thời điểm commit tạo ra tình huống outcome không rõ ràng cho client; cần reconciliation/idempotency cho workflows quan trọng.

### 8.3. Nhiều foreign servers

Một local transaction có thể truy cập nhiều foreign servers. Không nên mặc định các remote commits và local commit tạo thành một distributed atomic commit protocol hoàn chỉnh trong mọi failure scenario. `postgres_fdw` có transaction coordination riêng và behavior phụ thuộc version; kiểm tra tài liệu trước khi dựa vào atomicity xuyên nhiều hệ thống.

### 8.4. Two-phase commit

Không coi FDW là giải pháp thay thế XA/2PC hoặc distributed transaction coordinator. Nếu nghiệp vụ đòi hỏi atomic commit xuyên nhiều databases trong mọi crash scenario, thiết kế transaction protocol chuyên biệt, saga/outbox hoặc một hệ thống coordinator phù hợp.

### 8.5. Isolation level

Local transaction isolation và remote transaction snapshot có thể có semantics khác nhau tùy isolation level và FDW. `postgres_fdw` có các giới hạn liên quan remote transaction isolation; xem documentation đúng version để hiểu cách snapshot/remote transaction được duy trì.

### 8.6. Snapshot consistency

Một câu query foreign table có thể đọc snapshot từ remote server. Khi query nhiều foreign servers, không có một global snapshot đồng nhất tự động cho toàn hệ thống. Dữ liệu ở các nguồn có thể phản ánh các thời điểm khác nhau.

### 8.7. Long-running transactions

Transaction local mở lâu trong khi giữ remote transaction có thể giữ remote snapshots/locks, chiếm connection và ảnh hưởng vacuum ở remote PostgreSQL. Commit/rollback sớm; không giữ transaction trong khi người dùng suy nghĩ hoặc chờ external API.

### 8.8. Savepoints

`postgres_fdw` hỗ trợ savepoint/subtransaction mapping trong các tình huống được tài liệu hóa. Dù vậy, test rollback-to-savepoint, remote errors và nested transaction behavior trên version đang chạy trước khi dùng trong workflow phức tạp.

### 8.9. Prepared transactions

Không giả định remote FDW transaction có thể được điều khiển như local prepared transaction trong mọi trường hợp. Nếu ứng dụng cần `PREPARE TRANSACTION`/2PC, xác minh rõ hỗ trợ của wrapper và transaction coordinator; không để prepared transactions tồn tại lâu vì chúng có thể giữ resources.

### 8.10. Retry và exactly-once

Network disconnect có thể khiến client không biết remote statement đã commit hay chưa. Exactly-once delivery không tự có từ FDW. Dùng idempotency keys, unique constraints, durable job state và reconciliation khi retry DML.

### 8.11. Remote availability

Nếu remote database unavailable, query foreign table có thể fail hoặc timeout. Xác định application fallback: fail closed, serve cached/materialized copy hoặc trả degraded response. Không biến remote failure thành empty result nếu điều đó có thể bị hiểu nhầm là không có dữ liệu.

## 9. Type mapping, collation và schema drift

### 9.1. Khai báo type tương thích

Foreign table column definitions phải tương thích với remote columns. Với `postgres_fdw`, `IMPORT FOREIGN SCHEMA` giúp lấy metadata, nhưng sau import vẫn cần kiểm tra type mapping, precision và nullability.

### 9.2. Numeric precision

Remote `numeric(p,s)` và local `numeric`/integer declarations cần tương thích. Tránh khai báo local precision nhỏ hơn remote nếu có thể làm overflow/rounding.

### 9.3. Timestamp và timezone

Phân biệt `timestamp without time zone` với `timestamp with time zone` (`timestamptz`). Local/remote `TimeZone` settings có thể làm output display khác nhau dù instant không đổi. Dùng explicit timezone conversions khi business semantics yêu cầu.

### 9.4. Text encoding

Hai PostgreSQL databases có encoding khác nhau có thể không chuyển mọi characters được. Kiểm tra server/database encodings và client encoding. Dữ liệu không representable có thể gây lỗi khi truyền.

### 9.5. Collation

String comparison/order có thể khác theo collation/version. Điều này ảnh hưởng pushdown safety, sort, joins và uniqueness. Không so sánh local/remote text semantics như nhau nếu collation khác.

### 9.6. Domains và enums

Remote domain/enum có thể được biểu diễn theo type mapping của FDW. Kiểm tra catalog metadata, labels và behavior khi remote thêm enum value hoặc đổi domain constraints. Local schema không tự đồng bộ mọi thay đổi remote.

### 9.7. Arrays, ranges và custom types

Custom types, arrays, ranges, composites và extension-defined types có hỗ trợ phụ thuộc wrapper/version. Kiểm tra import mapping và round-trip values. Khi không chắc, dùng scalar/text representation rõ ràng và conversion layer.

### 9.8. Schema drift

Nếu remote column được rename/drop/type-change, foreign table local có thể vẫn giữ metadata cũ và query bắt đầu lỗi hoặc mapping sai. Cần quy trình schema change coordination giữa owner remote và owner local.

### 9.9. Import schema không tự refresh

`IMPORT FOREIGN SCHEMA` tạo foreign table definitions tại thời điểm chạy. Nếu remote schema thay đổi sau đó, local foreign tables không tự cập nhật. Re-import có thể xung đột với objects hiện có; plan alter/recreate có kiểm soát.

### 9.10. Schema contract

Định nghĩa contract cho remote source: owner, schema version, backward compatibility window, deprecation notice và change process. Với nhiều consumers, tránh drop/rename columns đột ngột.

## 10. Bảo mật và quản lý truy cập

### 10.1. Least privilege ở hai phía

Tạo remote role riêng cho từng integration với quyền tối thiểu. Ví dụ, reporting user chỉ cần SELECT trên một số tables/views; không dùng remote superuser cho ứng dụng local.

~~~sql
-- Chạy ở remote database bằng role quản trị phù hợp
CREATE ROLE crm_fdw_reader LOGIN PASSWORD 'set-through-secret-management';
GRANT CONNECT ON DATABASE crm TO crm_fdw_reader;
GRANT USAGE ON SCHEMA public TO crm_fdw_reader;
GRANT SELECT ON public.customers, public.orders TO crm_fdw_reader;
~~~

Ví dụ chỉ minh họa cấu trúc quyền. Quản lý mật khẩu qua secret manager/controlled provisioning; không lưu password thật trong repository hoặc bài migration.

### 10.2. Local role riêng

Tạo local role cho application/analyst, chỉ cấp quyền trên foreign schema và foreign tables cần thiết. Không cấp quyền CREATE trên schema tích hợp cho user chỉ cần đọc.

### 10.3. User mapping scope

User mapping có thể gắn với một local role hoặc PUBLIC. Mapping per-role giúp audit và phân tách remote identity; mapping PUBLIC đơn giản hơn nhưng mở rộng quyền sử dụng mapping. Chọn theo threat model.

### 10.4. Credentials trong catalog

User mapping options có thể chứa credentials. Hạn chế quyền quản trị foreign servers/mappings, quyền xem catalog và quyền tạo/alter user mappings. Tránh dump catalog options vào logs/tickets.

### 10.5. Network security

Giới hạn firewall/security groups chỉ cho phép local PostgreSQL host kết nối remote endpoint/port cần thiết. Dùng private network/VPN/peering phù hợp và tránh expose remote database công khai.

### 10.6. TLS

Với PostgreSQL remote, cấu hình SSL/TLS theo libpq parameters, ví dụ `sslmode` phù hợp và CA verification. `verify-full` xác minh certificate chain và hostname; cần cài CA certificate đúng trên database host. Không hạ TLS verification chỉ để làm connection hoạt động.

~~~sql
CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm',
    sslmode 'verify-full',
    sslrootcert '/etc/ssl/certs/company-ca.pem'
);
~~~

Các connection options phải được FDW/libpq version hỗ trợ. Bảo vệ file CA/key và kiểm tra hostname/certificate rotation.

### 10.7. Application identity và audit

Đặt `application_name` để nhận diện nguồn connection trên remote server. Kết hợp remote logs, `pg_stat_activity`, role identity và local job/request ID để trace. Không ghi credentials hoặc sensitive row values.

### 10.8. SQL injection và dynamic SQL

Foreign table không tự tạo SQL injection, nhưng code tạo dynamic SQL/DDL cho foreign server, schema/table names và options vẫn có nguy cơ. Dùng identifier quoting/parameterization đúng API, allowlist object names và không ghép user input thành connection options.

### 10.9. Server-side file access

Với wrappers đọc file trên database host, quyền filesystem/server-program có thể mở rộng đáng kể. Chỉ cho phép role được tin cậy, giới hạn paths và không cho user tùy ý chạy chương trình qua FDW.

### 10.10. Secret rotation

Lập quy trình rotate remote password/certificate, cập nhật user mapping và xác nhận connection mới hoạt động. Một số sessions đã cache remote connections; cần kiểm tra cách FDW quản lý connection cache và thời điểm connections được đóng/re-established.

### 10.11. Drop và revoke

Khi integration hết dùng, revoke local grants, drop user mapping, foreign tables/server và extension nếu không còn dependencies. Kiểm tra object dependencies trước khi `DROP ... CASCADE`; tránh CASCADE mù làm mất objects không liên quan.

## 11. Connection lifecycle và options của postgres_fdw

### 11.1. Connection cache

`postgres_fdw` có thể giữ remote connection trong local backend session để tái sử dụng giữa các statements. Điều này giảm connection setup cost nhưng remote server có thể thấy nhiều connections theo số local backend sessions và foreign servers được dùng.

### 11.2. keep_connections

Server option `keep_connections` kiểm soát việc giữ connections để tái sử dụng; behavior/default phụ thuộc version. Đóng connections có thể giảm remote connection count nhưng tăng authentication/connection overhead cho query kế tiếp. Kiểm tra documentation và workload.

### 11.3. Remote connection capacity

Tính toán số local application sessions, connection pool size, số foreign servers và remote connection limit. Nếu nhiều local backends cùng truy vấn remote, có thể tạo connection storm dù local connection pool có vẻ bình thường.

### 11.4. Connection pooler

Kết hợp FDW với PgBouncer/remote pooler cần hiểu pooling mode và session features. `postgres_fdw` có thể cần session-level state/transaction semantics; kiểm tra compatibility với transaction pooling và test prepared statements/session behavior.

### 11.5. connect_timeout

Có thể cấu hình `connect_timeout` trong server options nếu libpq/FDW hỗ trợ. Timeout kết nối khác statement timeout; nó giới hạn thời gian thiết lập connection, không phải thời gian remote query.

### 11.6. application_name

Đặt application name theo integration/service để remote DBA lọc connections. Tránh đặt giá trị động có cardinality quá cao nếu logging/monitoring dùng label.

### 11.7. Option scope

Options có thể áp dụng ở foreign-data wrapper, server, user mapping hoặc foreign table tùy wrapper và option. `ALTER SERVER`, `ALTER USER MAPPING` và `ALTER FOREIGN TABLE` dùng để thay đổi cấu hình; validator sẽ từ chối option không hợp lệ.

### 11.8. Thay đổi options

~~~sql
ALTER SERVER crm_server
OPTIONS (
    SET fetch_size '5000',
    SET use_remote_estimate 'true'
);
~~~

Thay đổi options ảnh hưởng các lần planning/connection tiếp theo theo semantics của option. Nếu connection đã cache, xác minh liệu cần disconnect/reconnect hoặc reconnect session để nhận cấu hình mới.

### 11.9. Drop option

~~~sql
ALTER SERVER crm_server
OPTIONS (DROP use_remote_estimate);
~~~

Kiểm tra options hiện tại trước khi DROP/SET để tránh thay đổi nhầm cấu hình dùng chung.

### 11.10. Đọc options an toàn

Catalog options có thể chứa hostnames, usernames hoặc secrets. Chỉ hiển thị phần cần thiết cho troubleshooting và redact sensitive values khi gửi output ra ticket/chat.

## 12. Các FDW và nguồn dữ liệu khác

### 12.1. file_fdw

`file_fdw` là extension được PostgreSQL cung cấp để đọc dữ liệu từ file trên filesystem của database server, thường dùng với text/CSV. Nó phù hợp cho staging/import nhẹ hoặc truy vấn file có cấu trúc; nó không phải một general-purpose remote database connector.

~~~sql
CREATE EXTENSION IF NOT EXISTS file_fdw;

CREATE SERVER csv_files
FOREIGN DATA WRAPPER file_fdw;

CREATE FOREIGN TABLE staging_external_customers (
    customer_id bigint,
    email text,
    active boolean
)
SERVER csv_files
OPTIONS (
    filename '/srv/postgresql/import/customers.csv',
    format 'csv',
    header 'true'
);
~~~

File path được đọc trên host chạy PostgreSQL server, không phải máy psql client. OS user của PostgreSQL phải có quyền đọc file; quyền database để truy cập server-side files bị giới hạn theo role đặc biệt/superuser policy.

### 12.2. file_fdw security

Không cho user không tin cậy tùy ý chọn paths trên server. Cấp quyền tối thiểu, giới hạn directory, kiểm tra symlinks/permissions và không expose sensitive files. Option `program` có thể chạy chương trình server-side và cần privilege đặc biệt; chỉ sử dụng với command cố định được review, không ghép user input.

### 12.3. Foreign table trên file không phải data copy

Đọc CSV qua foreign table vẫn phụ thuộc file tồn tại, encoding, delimiter, header và schema. Nếu file thay đổi giữa các queries, kết quả cũng có thể thay đổi. Với pipeline cần snapshot/transactional ingestion, load vào staging table rồi validate/commit.

### 12.4. Các FDW cộng đồng

Có các wrappers cộng đồng cho Oracle, MySQL, ODBC, MongoDB, Redis, HTTP/API, S3 và nhiều nguồn khác. Tên package, license, support matrix, write capabilities và maintenance quality khác nhau. Đánh giá project activity, security advisories, PostgreSQL major version compatibility và SLA trước khi production use.

### 12.5. Wrapper read-only và read-write

Một số wrappers chỉ hỗ trợ SELECT; một số hỗ trợ INSERT/UPDATE/DELETE; một số có giới hạn pushdown hoặc transaction support. Không suy ra feature của `postgres_fdw` áp dụng cho wrapper khác. Đọc docs/README/release notes của đúng extension.

### 12.6. ODBC/JDBC

ODBC/JDBC là driver interfaces; chúng không tự trở thành FDW. Cần một wrapper tích hợp driver tương ứng và cấu hình client libraries trên server host. Quản lý driver version, DSN, TLS, credentials và type mapping.

### 12.7. REST/API wrappers

API thường có pagination, rate limits, retries, authentication expiry và response schema evolution. FDW có thể không phù hợp cho query patterns đòi hỏi arbitrary joins/transactions qua API. Cân nhắc ingest/cache dữ liệu vào local tables để kiểm soát reliability.

### 12.8. Chọn wrapper

Đánh giá:

- PostgreSQL major version compatibility;
- Source protocol/driver version;
- Read/write support;
- Predicate/join/aggregate pushdown;
- Transaction semantics;
- Type mapping;
- TLS/authentication;
- Parallel/async capabilities;
- Maintenance/community support;
- Observability và error handling.

## 13. Performance và thiết kế workload

### 13.1. Network latency là một phần của query cost

Foreign scan có chi phí network round trips, connection setup, serialization và remote execution. Một query local vài milliseconds có thể trở thành hàng trăm milliseconds khi remote ở region khác.

### 13.2. Giảm rows và columns trước khi truyền

Ưu tiên predicates/select list có thể pushdown, tránh lấy toàn bộ remote table rồi lọc local. Không dùng `SELECT *` nếu chỉ cần vài columns.

### 13.3. Join location

Nếu join hai foreign tables cùng server có thể pushdown, để remote database thực hiện join thường tiết kiệm transfer. Nếu join foreign với local table lớn, xem plan và cân nhắc staging/materialization nếu remote transfer quá nhiều.

### 13.4. Chọn fetch_size

Đo row width và latency. Fetch size lớn giúp network latency cao nhưng có thể tăng memory. Test nhiều mức dưới concurrent workload; không tune bằng một query đơn độc.

### 13.5. Chọn batch_size

Với bulk inserts qua `postgres_fdw`, batch size lớn có thể giảm round trips. Nhưng cần cân bằng remote statement size, memory, transaction duration, WAL và error recovery.

### 13.6. Remote indexes

Tối ưu indexes ở remote source theo pushed predicates, join keys và order. Local foreign table không có local index lưu rows như ordinary table; index cần ở nơi dữ liệu thực sự nằm.

### 13.7. ANALYZE local foreign table

Statistics local giúp planner chọn join order và estimate cardinality. Chạy ANALYZE sau khi remote data thay đổi lớn hoặc theo lịch; đo chi phí lấy sample qua network.

### 13.8. use_remote_estimate

Bật remote estimates khi local stats không đủ hoặc remote data distribution thay đổi nhanh; tắt nếu planning round trips làm latency cao và local stats đủ tốt. So sánh cả planning time và execution time.

### 13.9. Materialized view làm cache

Nếu remote source không cần được đọc real-time, có thể materialize kết quả:

~~~sql
CREATE MATERIALIZED VIEW reporting.customer_summary AS
SELECT
    customer_id,
    count(*) AS order_count,
    sum(total_amount) AS lifetime_value
FROM remote_crm.orders
GROUP BY customer_id;
~~~

Refresh:

~~~sql
REFRESH MATERIALIZED VIEW reporting.customer_summary;
~~~

Materialized view lưu local copy; dữ liệu có thể stale cho tới lần refresh. Với concurrent refresh cần unique index phù hợp và operation có giới hạn riêng. Lập lịch refresh, freshness SLA và cách xử lý remote outage.

### 13.10. Staging table

Đối với ETL, load remote data vào staging local theo batch rồi validate/transform/merge. Staging giúp tách network dependency khỏi application queries, kiểm soát data quality và giữ snapshot lịch sử.

### 13.11. Cache và freshness

Định nghĩa freshness requirement: real-time, vài phút, hàng giờ hay daily. Không dùng FDW trực tiếp cho request path nếu remote latency/availability không đáp ứng SLO và không có fallback.

### 13.12. N+1 remote queries

Tránh loop trong application chạy một foreign query cho từng local row. Gom keys vào một query/join có thể pushdown, hoặc batch-fetch. Mỗi round trip nhỏ lặp lại có thể đắt hơn một query lớn.

### 13.13. Network payload

Large text, JSON, bytea hoặc wide rows làm tăng serialization/transfer. Chỉ chọn columns cần thiết, giới hạn rows và tránh kéo blob qua FDW khi không cần.

### 13.14. Remote workload isolation

Foreign queries tiêu thụ resources trên remote production database. Dùng read replica/reporting endpoint nếu phù hợp, remote role có resource controls và rate limit. Tuy nhiên replica lag có thể làm dữ liệu không mới nhất.

### 13.15. Cạnh tranh connections

Connection cache giảm setup overhead nhưng nhiều local backends có thể mở nhiều remote sessions. Đặt local pool limits, theo dõi remote max_connections và cân nhắc dedicated integration role/application name.

### 13.16. Không dùng FDW thay query design

Một foreign query không tự tối ưu chỉ vì cú pháp SQL ngắn. Hiểu data volume, filter selectivity, remote plan, transfer size và join location. Nếu query cần scan phần lớn remote dataset thường xuyên, ingestion/replication có thể phù hợp hơn.

## 14. Observability và troubleshooting

### 14.1. Quan sát local foreign scans

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS, SETTINGS)
SELECT customer_id, email
FROM remote_crm.customers
WHERE active;
~~~

Ghi lại planning time, execution time, actual rows, loops và `Remote SQL`. So sánh với query chạy trực tiếp trên remote để phân biệt network/FDW overhead và remote execution cost.

### 14.2. Quan sát remote sessions

Trên remote PostgreSQL:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS query_age,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE application_name = 'local-fdw-crm'
ORDER BY query_start;
~~~

`application_name` filter chỉ hiệu quả nếu đã cấu hình và remote server nhận giá trị đó.

### 14.3. Remote logs

Cấu hình remote logging theo policy để ghi duration/errors và identify FDW workload. Cân nhắc `log_min_duration_statement`/log sampling, tránh ghi quá nhiều query literals nhạy cảm.

### 14.4. Statistics reset

Các statistics counters ở remote/local có thể reset sau restart hoặc reset command. Lưu reset timestamp cùng snapshots để không hiểu nhầm counter nhỏ là workload mới.

### 14.5. Lỗi connection refused/timeout

Kiểm tra:

1. DNS/host/port;
2. Firewall/security group/routing;
3. Remote PostgreSQL listen address;
4. `pg_hba.conf`/authentication;
5. TLS mode/certificate;
6. Remote connection limits;
7. `connect_timeout` và network health.

### 14.6. Lỗi password authentication

Kiểm tra local user mapping, remote username/password, password rotation, remote role login status và authentication method. Không in password ra logs để debug.

### 14.7. Permission denied

Phân biệt lỗi local USAGE/SELECT trên foreign server/table với lỗi remote CONNECT/USAGE/SELECT trên remote object. Xác định remote identity mà user mapping chọn.

### 14.8. Relation/column does not exist

Kiểm tra local foreign table options, remote schema/table names, case-sensitive quoted identifiers và schema drift. Import schema không tự cập nhật khi remote DDL thay đổi.

### 14.9. Type conversion error

Kiểm tra local foreign table column types, remote column types, precision, encoding, timezone và custom types. Không sửa type local tùy tiện mà không so với remote schema contract.

### 14.10. Query chậm dù filter có trong SQL

Dùng EXPLAIN VERBOSE xác nhận filter có trong Remote SQL. Nếu không, xem expression/cast/collation có ngăn pushdown không. Nếu có, kiểm tra remote plan/indexes/statistics và network latency.

### 14.11. Nhiều rows được kéo về

Kiểm tra projection, filter, LIMIT, join/aggregate pushdown và row estimates. Tối ưu remote query hoặc materialize data nếu workload cần local joins lặp lại.

### 14.12. Deadlock/lock waits

Foreign DML có thể lock rows ở remote; local transaction có thể đồng thời lock local rows. Xem deadlock logs ở cả local và remote, giữ transaction ngắn và thống nhất thứ tự lock trong application.

### 14.13. Remote transaction còn mở

Kiểm tra local backend state/transaction age và remote `pg_stat_activity`. Một local idle-in-transaction session có thể giữ remote transaction/connection. Đóng transaction và xử lý connection pool/session leaks.

### 14.14. Remote server restart

Remote restart làm connections cache bị mất. Query tiếp theo có thể lỗi và cần retry sau khi connection được tái lập. Ứng dụng phải xử lý lỗi transient theo idempotency policy.

### 14.15. FDW errors trong logs

Bật logging đủ để xác định server, local role, remote identity (không lộ secret), query duration và SQLSTATE. Redact credentials và sensitive data trước khi chia sẻ logs.

## 15. Khi nào nên dùng FDW?

### 15.1. FDW phù hợp

FDW thường phù hợp khi:

- Cần lookup/join một lượng dữ liệu ngoài có chọn lọc;
- Muốn query federation mà không cần copy toàn bộ source;
- Remote source là hệ thống có owner rõ ràng và availability đáp ứng yêu cầu;
- Workload có thể pushdown tốt;
- Latency/network cost chấp nhận được;
- Transaction semantics và security model đã được hiểu.

### 15.2. Khi nên cân nhắc replication

Replication phù hợp hơn khi cần read throughput cao, local availability khi remote source gián đoạn hoặc cần dữ liệu gần local để giảm network latency. Cần chấp nhận replication lag, storage và operational complexity.

### 15.3. Khi nên dùng ETL/ELT

ETL/ELT phù hợp khi cần historical snapshots, transformations nhiều bước, data quality checks, retry/reconciliation và analytics trên lượng lớn dữ liệu. Nó cũng giúp tách production source khỏi reporting workload.

### 15.4. Khi nên dùng materialized view

Materialized view phù hợp khi query remote tốn kém nhưng dữ liệu có thể stale trong một khoảng xác định. Cần freshness SLA, refresh schedule, unique index cho concurrent refresh nếu cần và quy trình khi remote source unavailable.

### 15.5. Khi nên gọi API trực tiếp

API phù hợp khi source có business operations/authentication/rate limits cần được thực thi qua service contract. FDW không thay thế service layer hoặc business validation ở API.

### 15.6. Ma trận quyết định

| Nhu cầu | Lựa chọn thường phù hợp | Câu hỏi quyết định |
| --- | --- | --- |
| Lookup vài rows khi query | FDW | Remote latency có đáp ứng SLO? |
| Join tables cùng PostgreSQL remote | postgres_fdw | Join/filter có pushdown? |
| File CSV trên database host | file_fdw hoặc staging load | File access có an toàn và ổn định? |
| Local read scaling | Replication | Có chấp nhận lag và copy storage? |
| Lịch sử/analytics lớn | ETL/ELT | Có cần snapshots và transformation? |
| Query cache theo lịch | Materialized view | Freshness interval là bao lâu? |
| Business operation qua service | API/service integration | Có cần service authorization/rules? |

### 15.7. Hybrid architecture

Một hệ thống có thể dùng FDW cho lookup nhỏ, CDC/replication cho operational read model và ETL cho analytics. Không bắt buộc chọn một công nghệ duy nhất cho mọi data integration.

## 16. Ví dụ end-to-end: tích hợp CRM PostgreSQL

Tình huống: database local `appdb` cần đọc customers/orders từ remote database `crm`. Application chỉ cần đọc dữ liệu CRM để hiển thị customer profile và order history.

### 16.1. Remote prerequisites

Remote DBA tạo role read-only và cấp quyền:

~~~sql
CREATE ROLE crm_fdw_reader LOGIN;
GRANT CONNECT ON DATABASE crm TO crm_fdw_reader;
GRANT USAGE ON SCHEMA public TO crm_fdw_reader;
GRANT SELECT ON public.customers, public.orders TO crm_fdw_reader;
~~~

Provision credentials qua secret manager; cấu hình network allowlist và TLS.

### 16.2. Local extension và server

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER crm_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'crm-db.internal.example',
    port '5432',
    dbname 'crm',
    application_name 'appdb-fdw-crm',
    sslmode 'verify-full',
    sslrootcert '/etc/ssl/certs/company-ca.pem'
);
~~~

### 16.3. User mapping và schema

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER crm_server
OPTIONS (
    user 'crm_fdw_reader',
    password 'managed-outside-source-control'
);

CREATE SCHEMA remote_crm;
GRANT USAGE ON FOREIGN SERVER crm_server TO app_reader;
GRANT USAGE ON SCHEMA remote_crm TO app_reader;
~~~

### 16.4. Import selected tables

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders)
FROM SERVER crm_server
INTO remote_crm;

GRANT SELECT ON ALL TABLES IN SCHEMA remote_crm TO app_reader;
~~~

### 16.5. Query profile

~~~sql
SELECT
    c.customer_id,
    c.email,
    o.order_id,
    o.created_at,
    o.total_amount
FROM remote_crm.customers AS c
JOIN remote_crm.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 90001
ORDER BY o.created_at DESC
LIMIT 20;
~~~

Vì hai foreign tables cùng server, `postgres_fdw` có thể pushdown join/order/limit nếu các điều kiện tương thích. Dùng `EXPLAIN VERBOSE` xác nhận remote SQL.

### 16.6. ANALYZE và plan

~~~sql
ANALYZE remote_crm.customers;
ANALYZE remote_crm.orders;

EXPLAIN (VERBOSE, COSTS)
SELECT customer_id, email
FROM remote_crm.customers
WHERE customer_id = 90001;
~~~

So sánh plan local với remote plan, kiểm tra indexes trên remote primary key/customer_id và latency thực tế.

### 16.7. Grant application

~~~sql
GRANT SELECT ON remote_crm.customers, remote_crm.orders TO app_reader;
~~~

Không cấp DML nếu ứng dụng chỉ đọc. Remote role vẫn chỉ có SELECT.

### 16.8. Verify và operationalize

- Xác nhận connection TLS/authentication;
- Xác nhận local/remote privileges;
- Kiểm tra Remote SQL và query plan;
- Đo latency p95 và bytes transferred;
- Theo dõi remote connection count;
- Test behavior khi CRM unavailable;
- Đặt alert cho connection failures/timeouts;
- Tài liệu hóa schema owner và change notice.

## 17. Vận hành foreign data integration

### 17.1. Trước khi đưa vào production

1. Xác định owner và SLA của remote source;
2. Kiểm tra PostgreSQL/FDW versions và supported options;
3. Thiết kế local/remote roles và user mappings;
4. Thiết lập TLS, firewall và secrets;
5. Import/define foreign tables có chọn lọc;
6. Test query pushdown bằng EXPLAIN VERBOSE;
7. Đo latency, throughput và remote connection load;
8. Test remote outage, timeout, retry và cancellation;
9. Xác định consistency/freshness semantics;
10. Viết runbook và alert ownership.

### 17.2. Daily checks

- Remote endpoint reachable;
- Authentication errors;
- Query latency/timeouts;
- Remote connection count;
- Remote server CPU/I/O/load;
- Local application error rate;
- Remote schema change notifications.

### 17.3. Weekly checks

- Slow foreign queries và top Remote SQL patterns;
- Foreign table local statistics age;
- Remote indexes/statistics cho pushed predicates;
- Connection pool/remote max_connections;
- Network throughput/errors;
- Credentials/certificate expiry.

### 17.4. Schema change coordination

Remote owner thông báo trước khi rename/drop/type-change. Local owner kiểm tra dependencies, test staging và cập nhật foreign table metadata/app code theo rollout tương thích. Không re-import schema tự động rồi overwrite local definitions trong production.

### 17.5. Credential rotation

Rotate remote credential theo quy trình:

1. Tạo/rotate remote credential;
2. Cập nhật secret manager;
3. Cập nhật user mapping;
4. Xác minh connection mới;
5. Đóng/recycle sessions cache theo hướng dẫn;
6. Revoke credential cũ;
7. Ghi audit event.

### 17.6. Remote outage runbook

Khi remote source down:

- Xác định phạm vi affected queries/services;
- Kiểm tra network/authentication/remote health;
- Pause jobs retry dồn dập;
- Dùng cache/materialized view nếu business policy cho phép;
- Không trả empty rows giả như dữ liệu hợp lệ;
- Theo dõi remote recovery và connection reconnect;
- Reconcile writes/outcomes nếu DML bị disconnect lúc commit.

### 17.7. Retiring integration

Trước khi xóa integration, tìm dependencies trong views/functions/jobs/application. Revoke app grants, remove mappings, foreign tables/server theo thứ tự dependency, sau đó drop extension nếu không còn dùng. Lưu audit/config metadata cần cho history.

### 17.8. Change management

Mọi thay đổi remote server options, user mapping, FDW extension version, TLS settings hoặc fetch/batch tuning cần owner, change record, validation và rollback plan. Đừng đổi server options dùng chung trong giờ peak nếu chưa biết consumers.

## 18. Giới hạn và trade-offs cần nhớ

### 18.1. FDW không làm remote data thành local data

Foreign table là metadata mapping; mỗi query vẫn có thể cần remote connection, execution và network transfer. Không đánh giá performance bằng cách nhìn SQL syntax giống local table.

### 18.2. Remote availability là dependency

Remote source down có thể làm query local fail. Nếu endpoint nằm trên critical request path, cần fallback/cache/replica hoặc thay đổi architecture.

### 18.3. Không có global snapshot mặc định

Nhiều remote systems có thể trả dữ liệu từ những thời điểm khác nhau. Không giả định query federated phản ánh một transaction snapshot toàn cục.

### 18.4. Distributed atomicity có giới hạn

Một local transaction truy cập nhiều remote servers không tự cung cấp guarantee atomic commit xuyên tất cả hệ thống trong mọi crash scenario. Thiết kế idempotency, outbox/saga hoặc coordinator khi cần.

### 18.5. Pushdown phụ thuộc wrapper

Không phải mọi filter, join, aggregate, sort, LIMIT hoặc DML đều pushdown. Một wrapper cộng đồng có thể chỉ hỗ trợ một subset nhỏ của SQL.

### 18.6. Type mapping có thể mất thông tin

Numeric precision, timestamp timezone, text encoding, collations và custom types cần được kiểm tra. Foreign table definition không tự bảo đảm round-trip lossless.

### 18.7. Statistics có thể stale

Local planner statistics không tự phản ánh mọi thay đổi remote. Cần ANALYZE hoặc remote estimates theo workload.

### 18.8. Schema drift không tự đồng bộ

Remote DDL không tự cập nhật local foreign table definitions. Có thể gây query errors sau rename/drop/type change.

### 18.9. Credentials và connection count

User mappings có thể lưu secrets; local backend sessions có thể mở remote connections. Cần least privilege, secret rotation và capacity planning.

### 18.10. FDW không thay ETL/CDC cho mọi use case

Historical snapshots, large-scale transformations, replay, lineage, quality checks và analytics thường cần pipeline/materialized data riêng.

### 18.11. Resource isolation

Local query có thể làm remote database quá tải. Giới hạn concurrency, chọn read replica khi phù hợp và monitor remote resource consumption.

### 18.12. Extension maintenance

FDW cộng đồng cần theo dõi release/security/compatibility. PostgreSQL upgrade có thể yêu cầu build lại extension hoặc migrate configuration.

## 19. Thực hành trong lab

Các bước dưới đây dùng hai PostgreSQL databases có thể kết nối được với nhau. Dùng credentials lab; không mở network hoặc cấp quyền rộng trên production.

### 19.1. Chuẩn bị remote database

Trên remote database, tạo dữ liệu mẫu:

~~~sql
CREATE TABLE public.lab_customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE public.lab_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.lab_customers (customer_id, email)
VALUES
    (1, 'one@example.test'),
    (2, 'two@example.test'),
    (3, 'three@example.test');

INSERT INTO public.lab_orders (order_id, customer_id, total_amount)
VALUES
    (101, 1, 120.00),
    (102, 1, 80.00),
    (103, 2, 250.00);
~~~

Tạo role remote chỉ đọc và cấp quyền trên hai tables.

### 19.2. Cấu hình local

Trên local database:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER lab_remote
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host '127.0.0.1',
    port '5433',
    dbname 'remote_lab'
);

CREATE USER MAPPING FOR CURRENT_USER
SERVER lab_remote
OPTIONS (
    user 'lab_reader',
    password 'lab-only-secret'
);

CREATE SCHEMA lab_remote;
~~~

Thay host/port/database/credentials theo lab thực tế. Không dùng password ví dụ trong bất kỳ môi trường chia sẻ nào.

### 19.3. Import schema

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (lab_customers, lab_orders)
FROM SERVER lab_remote
INTO lab_remote;
~~~

### 19.4. Query foreign tables

~~~sql
SELECT *
FROM lab_remote.lab_customers;

SELECT
    c.email,
    count(o.order_id) AS order_count,
    coalesce(sum(o.total_amount), 0) AS total_spent
FROM lab_remote.lab_customers AS c
LEFT JOIN lab_remote.lab_orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email
ORDER BY total_spent DESC;
~~~

### 19.5. Quan sát pushdown

~~~sql
EXPLAIN (VERBOSE, COSTS)
SELECT order_id, total_amount
FROM lab_remote.lab_orders
WHERE customer_id = 1
ORDER BY created_at DESC
LIMIT 10;
~~~

Tìm Remote SQL và xác nhận filter/order/limit được pushdown nếu plan hỗ trợ.

### 19.6. Thử DML

Chỉ thực hiện nếu lab remote role được cấp quyền write:

~~~sql
INSERT INTO lab_remote.lab_customers (customer_id, email, active)
VALUES (4, 'four@example.test', true);

UPDATE lab_remote.lab_customers
SET active = false
WHERE customer_id = 4;

DELETE FROM lab_remote.lab_customers
WHERE customer_id = 4;
~~~

Kiểm tra remote data sau mỗi thao tác và test rollback transaction.

### 19.7. Thử fetch_size

Đặt các mức fetch size khác nhau trên foreign server/table trong lab, chạy cùng một query có nhiều rows và đo execution time/memory. Chỉ so sánh khi dataset, network và cache conditions tương đương.

### 19.8. Thử remote outage

Tạm dừng remote service trong lab, chạy foreign query và quan sát error/timeout. Khởi động lại, xác nhận connections được tái lập và query hoạt động.

### 19.9. Thử schema drift

Đổi tên hoặc thay đổi một remote column trong lab. Query foreign table local để quan sát behavior; cập nhật local definition/import theo change process.

### 19.10. Cleanup

~~~sql
DROP SCHEMA lab_remote CASCADE;
DROP USER MAPPING FOR CURRENT_USER SERVER lab_remote;
DROP SERVER lab_remote;
DROP EXTENSION postgres_fdw;
~~~

Chỉ drop extension nếu không còn FDW objects/dependencies khác trong lab database.

## 20. Bài tập thực hành: Foreign Data Wrapper

Thực hiện trên lab/staging. Với câu hỏi phụ thuộc wrapper hoặc PostgreSQL major version, xác minh documentation tương ứng trước khi kết luận.

### Bài 1 — FDW concept

Giải thích Foreign Data Wrapper và vai trò của foreign table. Nêu sự khác nhau giữa foreign table và local table.

### Bài 2 — FDW vs replication

So sánh FDW với logical replication về freshness, availability, storage, latency và use cases.

### Bài 3 — FDW vs ETL

Một báo cáo cần dữ liệu lịch sử nhiều năm và transformations nhiều bước. Giải thích vì sao ETL/ELT có thể phù hợp hơn truy vấn FDW trực tiếp.

### Bài 4 — Architecture

Vẽ luồng parser/planner, FDW callbacks, remote source và local executor. Xác định filter nào có thể chạy local/remote.

### Bài 5 — Foreign server

Viết CREATE SERVER cho remote PostgreSQL với host, port và dbname.

### Bài 6 — User mapping

Viết CREATE USER MAPPING cho local role. Nêu lý do credentials không nên nằm trong source control.

### Bài 7 — Privileges

Liệt kê quyền cần ở local và remote để user chỉ đọc được một foreign table.

### Bài 8 — Import schema

Viết IMPORT FOREIGN SCHEMA chỉ lấy hai tables và một ví dụ dùng EXCEPT.

### Bài 9 — Manual foreign table

Viết CREATE FOREIGN TABLE cho remote customers với schema_name/table_name options.

### Bài 10 — Basic query

Viết SELECT trên foreign table với WHERE, ORDER BY và LIMIT. Giải thích vì sao cần EXPLAIN để xác nhận pushdown.

### Bài 11 — Local/foreign join

Join một local orders table với foreign customers. Nêu rủi ro nếu foreign table có nhiều rows và join không pushdown.

### Bài 12 — Remote join

Viết query join hai foreign tables cùng server. Xác định Remote SQL trong EXPLAIN VERBOSE.

### Bài 13 — Aggregate pushdown

Viết GROUP BY count/sum trên foreign orders. Nêu các yếu tố có thể ngăn aggregate pushdown.

### Bài 14 — Projection pushdown

Một remote table có 80 columns và vài JSON payload lớn. Viết query chỉ lấy ba columns cần thiết và giải thích lợi ích.

### Bài 15 — Remote estimates

Bật use_remote_estimate và giải thích trade-off giữa estimate quality với planning round trips.

### Bài 16 — fetch_size

Giải thích fetch_size. Thiết kế test ba giá trị khác nhau, đo throughput và memory.

### Bài 17 — batch_size

Giải thích batch_size trong postgres_fdw và vì sao không nên giả định option này áp dụng giống nhau cho mọi DML.

### Bài 18 — INSERT/UPDATE/DELETE

Viết ba DML statements qua foreign table và nêu local/remote privileges cần có.

### Bài 19 — Transaction

Một local transaction ghi foreign table rồi rollback. Mô tả expected behavior và nêu tình huống network failure khi commit làm outcome không rõ.

### Bài 20 — Multiple foreign servers

Một transaction ghi vào hai remote PostgreSQL servers. Giải thích vì sao không được giả định global atomic commit trong mọi failure scenario.

### Bài 21 — Type mapping

So sánh timestamp without time zone và timestamptz. Nêu cách timezone settings có thể làm display khác nhau.

### Bài 22 — Schema drift

Remote DBA rename một column. Foreign table local có tự cập nhật không? Thiết kế quy trình phối hợp schema changes.

### Bài 23 — Security

Thiết kế least-privilege remote role, local role, user mapping, TLS và firewall policy cho reporting integration.

### Bài 24 — Connection capacity

Local PostgreSQL có 300 backend sessions và mỗi session truy vấn ba foreign servers. Nêu cách ước lượng remote connection pressure và biện pháp kiểm soát.

### Bài 25 — file_fdw

Viết foreign table đọc CSV qua file_fdw. File được đọc trên host nào và cần kiểm soát quyền gì?

### Bài 26 — Query performance

Một query kéo 5 triệu remote rows về local rồi filter còn 100 rows. Đề xuất cách xác nhận và cải thiện pushdown.

### Bài 27 — Remote outage

Thiết kế fallback khi CRM database unavailable cho một API customer profile. Vì sao không nên trả empty result như thể khách hàng không tồn tại?

### Bài 28 — Materialized view

Tạo materialized view từ foreign orders để cache daily summary. Định nghĩa freshness SLA và refresh strategy.

### Bài 29 — Observability

Viết query trên remote pg_stat_activity lọc application_name của FDW. Nêu các metrics local/remote cần dashboard.

### Bài 30 — Capstone: federated customer data

Một application PostgreSQL cần kết hợp local orders, remote CRM customers, remote billing invoices và một file CSV chứa mapping quốc gia. Remote CRM/Billing thuộc hai team khác nhau; CRM có 20 triệu customers, Billing có 200 triệu invoices. API profile cần p95 dưới 250 ms, remote billing có thể unavailable ngắn hạn và reporting team cần dữ liệu lịch sử theo tháng.

**Yêu cầu:**

1. Chọn FDW, replication, ETL hoặc materialization cho từng nguồn và giải thích.
2. Thiết kế foreign servers, user mappings, roles và TLS/firewall.
3. Chọn tables/columns được import, không import toàn bộ schema tùy tiện.
4. Viết query customer profile và xác nhận query pushdown.
5. Thiết kế local/foreign joins để giới hạn rows/bytes truyền.
6. Chọn fetch_size, remote estimates và connection pool limits bằng benchmark.
7. Thiết kế cache/materialized view hoặc degraded response cho remote outage.
8. Định nghĩa transaction/idempotency policy cho DML nếu có.
9. Thiết kế schema-change contract giữa các team.
10. Xây dashboard remote latency, connections, failures, query duration và freshness.
11. Thiết kế ETL/staging cho reporting lịch sử, retention và data quality.
12. Viết runbook cho credential rotation, schema drift, network outage và remote overload.

**Tiêu chí đạt:** architecture đáp ứng latency/freshness, giới hạn tải lên remote systems, không phụ thuộc một global transaction snapshot, bảo vệ credentials và có fallback/operational ownership rõ ràng.

## 21. Câu hỏi thường gặp

### 21.1. Foreign table có lưu dữ liệu local không?

Thông thường không. Foreign table lưu metadata/mapping; dữ liệu được đọc từ nguồn ngoài khi query chạy. Muốn local copy, dùng table/staging/materialized view hoặc replication.

### 21.2. FDW có phải extension không?

FDW là cơ chế mở rộng của PostgreSQL. Các wrappers như postgres_fdw/file_fdw được cung cấp dưới dạng extensions và cần được cài/enable theo môi trường.

### 21.3. postgres_fdw có kết nối remote liên tục không?

Không nhất thiết. Nó thường mở connection khi cần và có thể cache/reuse connection trong local backend session theo option/version.

### 21.4. IMPORT FOREIGN SCHEMA có copy rows không?

Không. Nó tạo foreign table definitions từ metadata remote; data vẫn ở remote source.

### 21.5. Có thể tạo foreign table thủ công không?

Có. Dùng CREATE FOREIGN TABLE với columns, foreign server và options mapping đến remote schema/table.

### 21.6. Foreign table có thể JOIN với local table không?

Có. Planner có thể join local/foreign data, nhưng nếu join không pushdown, nhiều remote rows có thể được truyền về local. Kiểm tra EXPLAIN VERBOSE.

### 21.7. Filter trong WHERE luôn được pushdown?

Không. FDW chỉ pushdown biểu thức an toàn và được hỗ trợ. Functions, casts, collation hoặc operator semantics có thể khiến filter chạy local.

### 21.8. Làm sao biết pushdown hoạt động?

Chạy EXPLAIN VERBOSE và xem Foreign Scan/Remote SQL. Dùng EXPLAIN ANALYZE để đo thực tế và remote monitoring để xem remote query.

### 21.9. use_remote_estimate có luôn tốt hơn?

Không. Nó có thể cải thiện cardinality/cost estimates nhưng thêm remote planning round trips. Benchmark với local statistics và workload thật.

### 21.10. fetch_size lớn có luôn nhanh hơn?

Không. Nó giảm round trips nhưng tăng memory/buffer use và payload size. Chọn bằng benchmark theo row width, latency và concurrency.

### 21.11. batch_size có áp dụng cho UPDATE và DELETE?

Không nên giả định. Option của postgres_fdw chủ yếu liên quan batch INSERT paths; kiểm tra version/docs và chia UPDATE/DELETE theo batches nếu cần.

### 21.12. Có thể INSERT/UPDATE/DELETE foreign table không?

Có với postgres_fdw trong các điều kiện hỗ trợ và khi remote user có quyền tương ứng. FDW khác có thể read-only.

### 21.13. Local GRANT SELECT có đủ không?

Không. Local user cần quyền trên foreign server/schema/table và user mapping; remote identity cần CONNECT/USAGE/SELECT trên remote database/schema/table.

### 21.14. User mapping PUBLIC có an toàn không?

Nó mở rộng mapping cho mọi local users đủ quyền dùng server. Ưu tiên per-role mapping khi cần identity separation và audit.

### 21.15. Password user mapping được lưu ở đâu?

User mapping options được lưu trong catalog; quyền đọc thông tin có thể bị giới hạn nhưng credentials vẫn là dữ liệu nhạy cảm. Quản lý quyền catalog, secret rotation và logs.

### 21.16. FDW có hỗ trợ TLS không?

Với postgres_fdw, có thể dùng libpq connection options cho SSL/TLS như sslmode và CA certificate. Xác minh support/version và dùng hostname verification.

### 21.17. Một transaction ghi hai remote servers có atomic không?

Không nên giả định có global atomic commit trong mọi failure scenario. Dùng idempotency, outbox/saga hoặc distributed transaction coordinator nếu nghiệp vụ cần guarantees mạnh hơn.

### 21.18. Remote database down thì sao?

Foreign query có thể fail/timeout. Application cần fallback/cache/degraded behavior hoặc fail closed tùy nghiệp vụ. Không biến remote failure thành empty result giả.

### 21.19. ANALYZE foreign table làm gì?

Nó cập nhật local planner statistics bằng sampling/analysis mà FDW hỗ trợ. Điều này giúp local planner estimate rows và chọn join path tốt hơn.

### 21.20. Remote schema đổi thì local foreign table có tự đổi không?

Không. Local metadata có thể stale. Cần schema change contract và migration local có kiểm soát.

### 21.21. Có thể dùng file_fdw đọc file từ laptop không?

Không trực tiếp. file_fdw đọc file trên host chạy PostgreSQL server. File từ client cần được upload/stage ở server hoặc dùng client-side import workflow.

### 21.22. file_fdw có ghi CSV không?

file_fdw chủ yếu phục vụ đọc file; không giả định nó hỗ trợ DML. Dùng COPY/ETL/staging hoặc wrapper khác cho writes.

### 21.23. FDW có thay thế API không?

Không. API thực thi business logic, authorization và service contract. FDW phù hợp truy cập data source; không tự thay service layer.

### 21.24. FDW có phù hợp analytics lớn không?

Có thể dùng cho query chọn lọc/federation, nhưng scan lớn thường bị giới hạn bởi network và remote workload. ETL/ELT, replication hoặc local materialization thường phù hợp hơn cho analytics nặng/lặp lại.

### 21.25. Khi nào nên chọn materialized view?

Khi remote data có thể stale trong một khoảng xác định và cần query local nhanh/ổn định. Định nghĩa refresh schedule, freshness SLA và xử lý refresh failure.

### 21.26. FDW có tự đồng bộ data giữa hai databases không?

Không. FDW cho phép truy cập/ghi remote theo query. Replication/CDC/ETL mới là các cơ chế đồng bộ liên tục hoặc theo lịch.

### 21.27. Có thể dùng PgBouncer với postgres_fdw không?

Cần test theo pooling mode, connection/session semantics và transaction behavior. Không mặc định transaction pooling tương thích với mọi cách dùng FDW.

### 21.28. Làm sao giới hạn remote load?

Giới hạn local concurrency/pool, dùng role/replica riêng, filter/projection pushdown, fetch/batch tuning, rate limit và monitor remote resource consumption.

### 21.29. Có một FDW hỗ trợ mọi database không?

Không. Mỗi wrapper hỗ trợ một hoặc một nhóm nguồn, có feature set/version/dependency riêng. Chọn và đánh giá wrapper cụ thể.

### 21.30. Checklist trước production là gì?

Xác nhận version/support, source owner/SLA, least privilege, TLS/network, schema contract, pushdown plan, latency/connection capacity, transaction/fallback semantics, monitoring và runbook.

## 22. Tài liệu tham khảo chính thức

Chọn tài liệu đúng PostgreSQL major version đang chạy; options, pushdown capabilities và transaction behavior có thể thay đổi:

- [Foreign Data Wrappers](https://www.postgresql.org/docs/current/ddl-foreign-data.html): khái niệm foreign tables, wrappers và server mappings.
- [CREATE FOREIGN DATA WRAPPER](https://www.postgresql.org/docs/current/sql-createforeigndatawrapper.html): đăng ký FDW.
- [CREATE SERVER](https://www.postgresql.org/docs/current/sql-createserver.html): khai báo foreign server.
- [CREATE USER MAPPING](https://www.postgresql.org/docs/current/sql-createusermapping.html): ánh xạ local users sang remote identities.
- [CREATE FOREIGN TABLE](https://www.postgresql.org/docs/current/sql-createforeigntable.html): khai báo foreign table.
- [IMPORT FOREIGN SCHEMA](https://www.postgresql.org/docs/current/sql-importforeignschema.html): import remote schema metadata.
- [postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html): cấu hình, options, pushdown, DML và transaction behavior.
- [file_fdw](https://www.postgresql.org/docs/current/file-fdw.html): đọc file CSV/text từ server filesystem.
- [Foreign Data Wrapper Functions](https://www.postgresql.org/docs/current/fdwhandler.html): FDW handler APIs và callbacks cho extension authors.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): đọc execution plans và remote SQL.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity, locks và statistics.
- [libpq Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html): connection parameters, TLS và service files.
- [Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html): lưu kết quả query local và refresh.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): phương án thay thế khi cần local copies.

## 23. Tổng kết

Foreign Data Wrapper cho phép PostgreSQL truy cập dữ liệu bên ngoài qua foreign tables và giữ cú pháp SQL quen thuộc. Với postgres_fdw, local database có thể kết nối PostgreSQL remote, import schema, query/join và thực hiện một số DML. Query pushdown giúp giảm dữ liệu truyền qua network; EXPLAIN VERBOSE cho biết phần SQL được gửi remote.

| Thành phần | Vai trò |
| --- | --- |
| FDW | Adapter giao tiếp với nguồn dữ liệu |
| Foreign server | Cấu hình endpoint/nguồn ngoài |
| User mapping | Identity/credentials remote cho local user |
| Foreign table | Metadata local ánh xạ remote relation |
| Pushdown | Chạy filter/join/aggregate/order ở remote khi hỗ trợ |
| ANALYZE | Cập nhật local planner statistics |
| Connection options | Điều chỉnh estimate, fetch, batch và lifecycle |
| Monitoring | Theo dõi local plan, remote sessions, latency và errors |

FDW không tạo local copy, không tự đồng bộ dữ liệu và không bảo đảm global transaction snapshot/atomic commit qua nhiều systems. Remote availability, network, schema drift, credentials và query pushdown đều ảnh hưởng trực tiếp đến ứng dụng.

Chọn FDW khi truy cập trực tiếp nguồn ngoài đem lại lợi ích và latency/freshness phù hợp. Dùng replication, ETL/ELT, staging hoặc materialized views khi cần local availability, lịch sử, transformation hay query analytics lớn. Luôn thiết kế least privilege, TLS, schema contracts, monitoring và fallback.

**Một tích hợp FDW tốt không chỉ làm foreign table truy vấn được; nó còn phải kiểm soát được nơi query chạy, dữ liệu nào đi qua network, remote identity nào được dùng và ứng dụng sẽ phản ứng ra sao khi nguồn ngoài thay đổi hoặc mất kết nối.**
